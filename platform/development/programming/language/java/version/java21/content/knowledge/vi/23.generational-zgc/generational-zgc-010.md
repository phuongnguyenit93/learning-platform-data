# Đo đạc trước khi điều chỉnh số GC thread hoặc tham số chuyên sâu

Generational ZGC được thiết kế để tự điều chỉnh theo tải, nên phần lớn ứng dụng không cần tự đặt số GC thread hoặc thay đổi hàng loạt JVM flag. Trước khi tinh chỉnh, hãy đo thời gian phản hồi của ứng dụng, allocation rate, heap headroom, hoạt động của các chu kỳ young/old, allocation stall và lượng CPU GC tiêu thụ. Chỉ thay đổi một tham số khi số liệu cho thấy vấn đề cụ thể mà tham số đó có thể giải quyết.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), Generational ZGC được giới thiệu qua JEP 439. Với JDK 21, cần bật chế độ này bằng `-XX:+UseZGC -XX:+ZGenerational`; chỉ `-XX:+UseZGC` vẫn chọn ZGC không phân thế hệ. Đây là khác biệt theo phiên bản: từ JDK 23, generational mode trở thành mặc định; từ JDK 24, chế độ không phân thế hệ và tùy chọn `ZGenerational` đã bị loại bỏ. Khi vận hành trên JDK mới hơn, không sao chép cờ chuyển tiếp của JDK 21 vào cấu hình mới.

## Vì sao không nên chỉnh GC thread ngay từ đầu?

ZGC thực hiện phần lớn công việc thu gom đồng thời với ứng dụng. GC worker cần CPU để đánh dấu, di chuyển và thu hồi bộ nhớ trong khi các thread ứng dụng vẫn tiếp tục cấp phát. HotSpot tự chọn số thread phục vụ GC dựa trên năng lực CPU và đặc điểm runtime.

Thay đổi số GC thread có một đánh đổi rõ ràng:

- Tăng số thread chạy đồng thời có thể giúp GC hoàn thành công việc nhanh hơn và theo kịp allocation rate, nhưng cũng lấy thêm CPU khỏi ứng dụng.
- Giảm số thread có thể dành thêm CPU cho ứng dụng khi GC đang chạy, nhưng GC có thể không thu hồi bộ nhớ đủ nhanh; khi heap thiếu headroom, ứng dụng có thể gặp allocation stall.
- Trên container có giới hạn CPU, cấu hình thread dựa trên số core của máy host thay vì quota mà container thực sự được cấp có thể làm tăng tranh chấp CPU.

Vì vậy, không thể kết luận “nhiều GC thread hơn luôn tốt hơn”. Cần xác định bottleneck là GC thiếu CPU, ứng dụng đang bão hòa CPU, heap thiếu headroom hay allocation rate tăng đột biến.

## Generational ZGC cần được quan sát như thế nào?

Generational ZGC tách heap thành hai thế hệ:

- **Young generation:** nơi object mới được cấp phát; được thu gom thường xuyên vì phần lớn object thường chết sớm.
- **Old generation:** nơi object sống lâu được giữ lại; chu kỳ thu gom diễn ra ít thường xuyên hơn.

Trong log và số liệu, cần phân biệt hoạt động young với old. Một ứng dụng có thể có nhiều minor/young cycle nhưng rất ít major/old cycle; đó không tự động là dấu hiệu bất thường. Hãy xem thời lượng chu kỳ, lượng bộ nhớ thu hồi, allocation rate và tác động lên request latency cùng nhau.

Đặc biệt, không chỉ nhìn vào stop-the-world pause. ZGC có các pha làm việc đồng thời; khi GC không theo kịp cấp phát, thread ứng dụng có thể phải chờ bộ nhớ được thu hồi. Allocation stall có thể làm tăng latency dù biểu đồ GC pause vẫn rất thấp.

## Thu thập baseline trước khi thay đổi cấu hình

Một baseline có ích cần được thu thập dưới tải đại diện và trong điều kiện có thể so sánh. Ghi nhận ít nhất các nhóm chỉ số sau:

| Nhóm chỉ số | Cần quan sát | Câu hỏi cần trả lời |
| --- | --- | --- |
| Application latency | p50, p95, p99, p99.9; timeout và error rate | Người dùng có thực sự gặp latency spike không? |
| Throughput | Request/transaction mỗi giây; số tác vụ hoàn tất | GC có làm giảm năng lực xử lý tổng thể không? |
| Allocation | Allocation rate, lượng object tạo theo thời gian, burst | Ứng dụng có cấp phát nhanh hơn mức GC theo kịp không? |
| Heap | Heap used, live set, committed memory, headroom tới `-Xmx` | Có đủ chỗ cho cấp phát trong lúc GC chạy không? |
| Generational cycles | Số lượng và thời lượng young/old cycle, pause tương ứng | Thế hệ nào đang tạo chi phí đáng kể? |
| Allocation stalls | Số lần, tổng thời gian và độ dài stall | Thread ứng dụng có phải chờ GC giải phóng bộ nhớ không? |
| CPU | CPU của process/container, CPU throttling, thời gian GC và application | GC thiếu CPU hay đang cạnh tranh CPU với ứng dụng? |
| Bộ nhớ ngoài heap | RSS/container memory, native memory, metaspace, direct buffer | Áp lực bộ nhớ có đến từ ngoài Java heap không? |

Không dùng riêng số lần GC hoặc tổng thời gian pause để đánh giá. Ví dụ, tăng số young cycle có thể là phản ứng bình thường trước allocation rate cao; điều cần biết là các cycle đó có thu hồi đủ bộ nhớ và giữ latency trong SLO hay không.

## Bật GC log và Java Flight Recorder

Unified logging là cách trực tiếp để xem các chu kỳ GC, pause, allocation stall và các thông tin liên quan. Trên JDK 21, có thể bật log GC chi tiết bằng:

```bash
java \
  -XX:+UseZGC -XX:+ZGenerational \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar application.jar
```

Đường dẫn log cần được cấu hình để có dung lượng và chính sách rotation phù hợp với môi trường triển khai. Khi cần ít thông tin hơn, bắt đầu với `-Xlog:gc:file=gc.log` rồi tăng mức chi tiết khi điều tra. Đừng bật logging quá rộng trong thời gian dài mà không kiểm soát dung lượng file và chi phí I/O.

Java Flight Recorder (JFR) bổ sung góc nhìn về GC, allocation, CPU và hoạt động của JVM. Có thể ghi một profile trong lúc chạy ứng dụng:

```bash
java \
  -XX:+UseZGC -XX:+ZGenerational \
  -XX:StartFlightRecording=filename=gc-profile.jfr,settings=profile,dumponexit=true \
  -jar application.jar
```

Phân tích file JFR bằng Java Mission Control hoặc công cụ tương thích. JFR giúp liên hệ thời điểm GC với allocation và hoạt động của ứng dụng; GC log cung cấp chuỗi sự kiện chi tiết theo thời gian. Hai nguồn dữ liệu bổ sung cho nhau.

Khi cần xác nhận JVM thực sự chạy với các flag nào, có thể dùng `jcmd`:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
```

Thay `<pid>` bằng process ID của JVM. Hãy kiểm tra cả command line, cờ được JVM chấp nhận và cấu hình runtime thực tế; file manifest hoặc startup script có thể khác với tiến trình đang chạy.

## Đọc allocation stall thay vì chỉ nhìn pause

Allocation stall xảy ra khi thread ứng dụng cần cấp phát nhưng GC chưa kịp tạo đủ vùng nhớ có thể sử dụng. Đây là dấu hiệu cần điều tra allocation rate, heap headroom và tốc độ thu gom.

Khi thấy stall, kiểm tra theo thứ tự:

1. Heap có đang tiến gần `-Xmx` không?
2. Live set có tăng bất thường hoặc có memory leak không?
3. Allocation rate có tăng đột biến so với baseline không?
4. GC cycle có kéo dài do thiếu CPU hoặc do workload thay đổi không?
5. Container có bị CPU throttling hoặc cạnh tranh CPU với workload khác không?
6. Ứng dụng có giữ quá nhiều object, buffer hoặc cache khiến live set không thể giảm không?

Nếu live set đã chiếm phần lớn heap, tăng GC thread không thể thu hồi object còn reachable. Nếu container thiếu CPU, thêm GC thread có thể làm throttling nặng hơn. Nếu allocation burst là nguyên nhân, cần xem lại workload, batching, object churn và heap headroom thay vì chỉ đổi số worker.

## Đánh giá `-XX:ConcGCThreads`

`-XX:ConcGCThreads` điều khiển số thread được dùng cho công việc GC đồng thời. Nếu không đặt cờ, HotSpot tự chọn giá trị dựa trên số CPU khả dụng và chính sách của collector. Heuristic này thường là điểm bắt đầu phù hợp.

Chỉ thử đặt cờ khi dữ liệu cho thấy GC thiếu năng lực xử lý hoặc đang dùng quá nhiều CPU so với mục tiêu ứng dụng. Ví dụ cú pháp:

```bash
java -XX:+UseZGC -XX:+ZGenerational -XX:ConcGCThreads=4 -jar application.jar
```

Giá trị `4` chỉ là ví dụ minh họa cú pháp, không phải khuyến nghị mặc định. Số phù hợp phụ thuộc vào quota CPU, số request đồng thời, allocation rate, live set và các workload khác trên cùng máy.

Khi benchmark, so sánh ít nhất cấu hình mặc định với một vài giá trị có cơ sở. Giữ nguyên workload, heap, giới hạn CPU và dữ liệu đầu vào; thay đổi một biến mỗi lần. Đánh giá đồng thời:

- GC cycle có ngắn hơn hoặc giảm allocation stall không?
- p99/p99.9 latency và throughput của ứng dụng có cải thiện không?
- CPU ứng dụng có bị giảm do GC chiếm thêm thời gian không?
- Container có xuất hiện throttling, context switching hoặc queueing tăng không?

Nếu GC cycle nhanh hơn nhưng p99 latency hoặc throughput xấu đi, thay đổi đó không đạt mục tiêu vận hành. Trả lại giá trị tự động là lựa chọn đúng nếu không có cải thiện tổng thể.

## Kiểm tra heap headroom trước khi chỉnh tham số khác

Với collector đồng thời như ZGC, heap cần đủ chỗ chứa live set và các allocation phát sinh trong lúc GC đang làm việc. `-Xmx` là giới hạn heap tối đa và thường là tham số quan trọng nhất cần đánh giá.

Ví dụ, `-XX:SoftMaxHeapSize` đặt một giới hạn mềm mà ZGC cố gắng duy trì. Đây không phải hard limit; ZGC vẫn có thể vượt giới hạn mềm, tối đa đến `-Xmx`, nếu cần để tránh ứng dụng bị stall do thiếu bộ nhớ.

```bash
java \
  -XX:+UseZGC -XX:+ZGenerational \
  -Xms2g -Xmx8g -XX:SoftMaxHeapSize=6g \
  -jar application.jar
```

Các con số chỉ minh họa cách kết hợp giới hạn heap cứng và mềm. Hãy chọn chúng dựa trên live set, allocation burst, memory limit của container và bộ nhớ dành cho native memory; không cấp `-Xmx` bằng toàn bộ RAM container nếu JVM còn cần bộ nhớ ngoài heap.

Nếu heap headroom thiếu, trước tiên xác định có thể tăng `-Xmx` trong giới hạn tài nguyên hay giảm allocation/live set. Tăng `ConcGCThreads` không thể thay thế việc cấp đủ bộ nhớ cho workload.

## Các tham số chuyên sâu và trade-off

Chỉ xem xét các cờ dưới đây khi số liệu chỉ ra đúng vấn đề tương ứng:

| Tham số | Tác động chính | Khi nào mới nên thử |
| --- | --- | --- |
| `-XX:SoftMaxHeapSize` | Đặt mục tiêu mềm cho kích thước heap; ZGC vẫn có thể vượt để tránh allocation problem | Cần cân bằng giữa footprint và headroom |
| `-XX:-ZUncommit` | Tắt việc trả các trang heap không dùng về hệ điều hành | Đã đo thấy commit/uncommit gây latency và có đủ ngân sách RAM |
| `-XX:ZUncommitDelay` | Điều chỉnh thời gian bộ nhớ phải không được dùng trước khi đủ điều kiện uncommit | Muốn cân bằng footprint với chi phí commit lại |
| `-XX:+AlwaysPreTouch` | Chạm các trang heap trước khi ứng dụng nhận chúng; tăng thời gian startup | Muốn chuyển chi phí page fault/chuẩn bị bộ nhớ về startup và đã đo lợi ích latency |
| `-XX:ZAllocationSpikeTolerance` | Đặt hệ số cho mức allocation spike mà ZGC cần dự liệu | Đã đo được burst cấp phát có tính lặp lại và hiểu rõ tác động lên heap |
| `-XX:ZCollectionInterval` | Đặt khoảng thời gian tối đa giữa các chu kỳ GC | Chỉ khi có yêu cầu đặc thù được tài liệu hóa; không dùng như cách chữa allocation stall |

Các tham số này có thể ảnh hưởng đến bộ nhớ, CPU, startup hoặc tần suất GC. Không bật/tắt hàng loạt trong cùng một lần triển khai vì sẽ không biết thay đổi nào tạo ra kết quả.

Đặc biệt, không sao chép cấu hình thế hệ của G1 hoặc Parallel GC như `-Xmn`, `-XX:NewSize`, `-XX:MaxNewSize` hay `-XX:NewRatio` để điều khiển young/old generation của Generational ZGC. ZGC tự quản lý kích thước thế hệ; hãy dùng các API và flag được tài liệu hóa cho đúng collector và JDK đang chạy.

## Phân biệt cấu hình theo phiên bản JDK

Generational ZGC có một thay đổi quan trọng giữa các bản JDK. Bảng dưới đây giúp tránh giữ lại flag chuyển tiếp sau khi nâng cấp:

| Phiên bản | Cách bật/chế độ mặc định |
| --- | --- |
| JDK 21–22 | `-XX:+UseZGC -XX:+ZGenerational` để bật Generational ZGC; chỉ `-XX:+UseZGC` vẫn chọn chế độ không phân thế hệ |
| JDK 23 | Generational ZGC trở thành mặc định khi dùng `-XX:+UseZGC`; chế độ không phân thế hệ bị deprecated |
| JDK 24 trở lên | Chỉ còn Generational ZGC; tùy chọn `ZGenerational` đã bị loại bỏ |

Do đó, trong tài liệu Java 21, cờ `-XX:+ZGenerational` là cần thiết để mô tả cách chạy đúng trên JDK 21. Khi triển khai bằng JDK mới hơn, kiểm tra tài liệu phiên bản đó và loại bỏ cờ đã bị gỡ. Không thêm `-XX:+UnlockExperimentalVMOptions` theo các hướng dẫn ZGC rất cũ từ thời ZGC còn experimental ở những JDK đầu tiên; ZGC đã trở thành tính năng production từ JDK 15.

## Quy trình benchmark có thể so sánh

1. **Xác nhận collector và phiên bản.** Ghi lại vendor/build JDK, xác nhận Generational ZGC đang chạy và lưu toàn bộ JVM flags.
2. **Tạo baseline.** Dùng cùng dữ liệu, concurrency, thời lượng, warm-up và giới hạn CPU/RAM như môi trường mục tiêu.
3. **Thu thập GC log và JFR.** Lưu allocation rate, young/old cycles, pause, allocation stalls, CPU và heap headroom.
4. **Đối chiếu với SLO.** Xác định latency percentile, throughput hoặc footprint nào đang không đạt mục tiêu.
5. **Tìm nguyên nhân.** Phân biệt thiếu heap, allocation burst, GC thiếu CPU, CPU throttling, live set lớn và memory leak.
6. **Đưa ra một giả thuyết.** Ví dụ: tăng nhẹ `ConcGCThreads` có thể giúp GC theo kịp allocation trong khi CPU còn dư.
7. **Thay đổi một tham số.** Giữ nguyên các điều kiện khác và chạy lại nhiều lần để giảm ảnh hưởng của nhiễu.
8. **So sánh toàn bộ kết quả.** Xem p99/p99.9 latency, throughput, allocation stalls, GC CPU, heap và container memory; không chỉ so pause.
9. **Giữ hoặc hoàn tác.** Chỉ giữ thay đổi khi cải thiện mục tiêu mà không gây hồi quy đáng kể ở chỉ số khác.
10. **Lưu cấu hình đã xác nhận.** Ghi lại JDK build, flags, workload và số liệu để lần nâng cấp sau có thể so sánh lại.

## Khi nào nên dừng tinh chỉnh?

Nếu latency và throughput đã đạt SLO, không có allocation stall đáng kể, heap có headroom hợp lý và footprint nằm trong giới hạn, việc tiếp tục chỉnh GC thread hoặc flag chuyên sâu có thể chỉ làm hệ thống khó vận hành hơn. Mục tiêu là đáp ứng yêu cầu ứng dụng với cấu hình dễ hiểu và ổn định, không phải tối ưu mọi chỉ số GC riêng lẻ.

Generational ZGC có cơ chế tự điều chỉnh số GC thread và kích thước thế hệ. Hãy bắt đầu bằng cấu hình đơn giản, đo bằng GC log/JFR dưới tải thật, kiểm tra heap headroom và allocation stall, rồi mới thử `ConcGCThreads` hoặc các tham số chuyên sâu. Với Java 21, nhớ bật đúng chế độ generational; khi nâng cấp lên JDK 23/24 trở lên, cập nhật flag theo thay đổi mặc định và loại bỏ tùy chọn đã bị gỡ.

## Tài liệu tham khảo

- [Oracle: The Z Garbage Collector — JDK 21](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html)
- [Inside Java: Introducing Generational ZGC](https://inside.java/2023/11/28/gen-zgc-explainer/)
- [Oracle: The java Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle: JDK 23 Release Notes — Generational ZGC by Default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
- [Oracle: Significant Changes in JDK 24 — Remove Non-Generational ZGC](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
