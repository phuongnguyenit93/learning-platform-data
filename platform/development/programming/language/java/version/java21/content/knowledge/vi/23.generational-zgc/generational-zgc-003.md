# Các pha xử lý đồng thời và tác động đến ứng dụng

Generational ZGC chia heap thành hai thế hệ: **young generation** dành cho đối tượng mới tạo và **old generation** dành cho đối tượng sống lâu hơn. Collector có thể thu gom young generation thường xuyên, trong khi old generation được xử lý theo nhịp ít thường xuyên hơn. Cách tổ chức này tận dụng thực tế rằng phần lớn object trong nhiều ứng dụng có vòng đời ngắn.

ZGC thực hiện phần lớn công việc đánh dấu và di chuyển object đồng thời với ứng dụng (concurrently). Ứng dụng vẫn chạy trong nhiều pha GC, nhưng phải chia sẻ CPU và băng thông bộ nhớ với collector; một số điểm đồng bộ vẫn tạo ra các khoảng dừng ngắn (stop-the-world pauses). Vì vậy, “concurrent” không có nghĩa là GC hoàn toàn không ảnh hưởng đến ứng dụng.

## 1. Chu kỳ thu gom nhìn ở mức tổng quát

Một chu kỳ thu gom có thể được hiểu qua các công việc chính sau:

1. **Bắt đầu đánh dấu:** JVM đồng bộ nhanh với application threads và ghi nhận trạng thái gốc cần thiết để bắt đầu mark.
2. **Đánh dấu đồng thời:** GC duyệt đồ thị object có thể truy cập để xác định object còn sống trong khi application threads tiếp tục chạy.
3. **Hoàn tất đánh dấu và xử lý reference:** JVM hoàn tất thông tin mark, xử lý các loại reference đặc biệt và xác định vùng nhớ có thể thu hồi.
4. **Chọn relocation set:** collector chọn các vùng chứa object sống cần di chuyển để thu hồi được vùng nhớ hiệu quả.
5. **Bắt đầu relocation:** JVM đồng bộ ngắn để chuẩn bị cho việc di chuyển object.
6. **Di chuyển đồng thời:** GC chuyển object còn sống sang vị trí mới trong khi ứng dụng vẫn có thể chạy.
7. **Thu hồi vùng cũ:** khi các tham chiếu được xử lý phù hợp, vùng nhớ cũ được đưa trở lại khả năng cấp phát.

Đây là mô hình khái niệm để hiểu luồng công việc. Tên pha, số pha và cách chúng được nhóm trong GC log có thể khác nhau theo phiên bản JDK, loại collection (young hoặc old) và tình trạng heap.

## 2. Marking: xác định object còn sống

Marking xác định object nào còn reachable từ các GC roots, chẳng hạn stack của thread, static fields và các tham chiếu gốc do JVM quản lý. Những object không còn reachable có thể được thu hồi khi vùng chứa chúng được xử lý.

Trong Generational ZGC, marking được thực hiện riêng theo nhu cầu của các thế hệ. Young collection tập trung vào object thuộc young generation; old collection xử lý old generation. Việc tách thế hệ giúp collector tránh phải quét toàn bộ heap cho mọi chu kỳ ngắn.

Phần lớn marking diễn ra đồng thời. Application threads vẫn có thể tạo object và thay đổi tham chiếu trong khi GC đang duyệt heap. ZGC dùng các barrier và metadata tham chiếu để duy trì tính đúng đắn của quá trình này; collector không đơn giản quét một heap đứng yên rồi giả định ứng dụng không thay đổi dữ liệu.

Các điểm pause ngắn ở đầu hoặc cuối pha marking cho phép JVM đồng bộ trạng thái cần thiết. Thời gian pause thực tế phụ thuộc vào số lượng root, số thread, cấu trúc heap và workload; không nên giả định mọi pause đều có cùng độ dài.

## 3. Reference processing

Java có các loại reference đặc biệt như `SoftReference`, `WeakReference` và `PhantomReference`. Việc xử lý chúng cần tuân theo semantics của Java và có thể tạo thêm công việc cho collector.

Generational ZGC xử lý các reference này như một phần của chu kỳ GC. Một số công việc có thể chạy đồng thời, nhưng các bước cần đồng bộ với trạng thái marking vẫn có thể góp phần vào pause. Ứng dụng tạo quá nhiều reference đặc biệt hoặc dùng chúng như cơ chế quản lý cache không có giới hạn có thể làm tăng chi phí GC.

Không dùng `System.gc()` để điều khiển chính xác thời điểm reference được xử lý. Đây chỉ là gợi ý cho JVM và không thay thế thiết kế vòng đời object rõ ràng.

## 4. Relocation set: chọn vùng cần di chuyển

Sau khi biết object nào còn sống, ZGC chọn các vùng nhớ phù hợp để relocate. Vùng có tỷ lệ object chết cao thường có thể thu hồi nhiều dung lượng bằng cách di chuyển số object còn sống sang nơi khác.

Relocation set là tập các vùng được chọn cho một chu kỳ di chuyển. Việc lựa chọn cân bằng giữa lượng bộ nhớ có thể thu hồi, số object cần di chuyển, chi phí CPU và áp lực cấp phát của ứng dụng.

Không phải mọi object sống đều cần được di chuyển trong mọi chu kỳ. Collector có thể để lại một số vùng nếu chi phí di chuyển không hợp lý hoặc vùng đó không thuộc tập được chọn.

## 5. Concurrent relocation: di chuyển object khi ứng dụng tiếp tục chạy

Trong pha relocation, ZGC chuyển object còn sống từ vùng được chọn sang vùng mới. Ứng dụng vẫn có thể truy cập object trong lúc di chuyển; load barriers giúp phát hiện và xử lý tham chiếu cần được cập nhật khi application thread đọc một reference.

Có thể hình dung quá trình như sau:

```text
Application thread đọc reference
             |
             v
       Load barrier
             |
     Kiểm tra trạng thái reference
             |
       +-----+-----+
       |           |
  Reference     Reference
  còn hợp lệ    cần remap/fix
       |           |
       v           v
     Dùng object ở vị trí hiện hành
```

Barrier là một phần của chi phí thực thi ứng dụng. Nó giúp GC và application threads phối hợp an toàn, nhưng các lần đọc/ghi reference có thể tốn thêm công việc so với trường hợp không có GC đồng thời.

Khi relocation hoàn tất và các tham chiếu cũ không còn cần thiết, vùng nhớ cũ có thể được thu hồi và đưa trở lại pool cấp phát. Cách cập nhật tham chiếu chi tiết là cơ chế nội bộ của ZGC; ứng dụng không cần tự sửa reference hoặc giữ địa chỉ object.

## 6. Generational ZGC xử lý young và old generation

Young generation nhận phần lớn object mới được tạo. Nhiều object chết sớm, vì vậy young collection có thể chạy thường xuyên và xử lý một phần heap tương đối nhỏ.

Object sống qua nhiều chu kỳ young collection có thể được promote sang old generation. Old collection xảy ra ít thường xuyên hơn và xử lý các object sống lâu. Khi cần theo dõi tham chiếu từ old object đến young object, collector duy trì thông tin qua các write barriers/metadata phù hợp để young collection không bỏ sót object còn reachable.

| Hoạt động | Young generation | Old generation |
|---|---|---|
| Mục tiêu | Thu gom object mới tạo, phần lớn có vòng đời ngắn | Thu gom object sống lâu hơn |
| Nhịp thu gom | Thường xuyên hơn | Ít thường xuyên hơn |
| Phạm vi công việc | Tập trung vào young objects và thông tin tham chiếu liên thế hệ | Tập trung vào old objects |
| Tác động thường thấy | Giúp thu hồi nhanh vùng cấp phát mới | Kiểm soát tăng trưởng của tập object sống lâu |

Phân thế hệ không bảo đảm mọi young collection đều rẻ hoặc old collection luôn hiếm. Nếu ứng dụng giữ lại nhiều object mới tạo, có lượng tham chiếu liên thế hệ lớn hoặc old generation tăng nhanh, collector vẫn cần xử lý lượng công việc đáng kể.

## 7. Các barrier và chi phí ứng dụng phải trả

GC đồng thời cần phối hợp với application threads. Generational ZGC dùng các barrier để duy trì thông tin tham chiếu và xử lý object trong quá trình marking/relocation.

- **Load barriers:** được thực thi khi ứng dụng đọc reference; chúng giúp phát hiện reference cần xử lý, ví dụ reference đến object đã relocate.
- **Store barriers:** được thực thi khi ứng dụng ghi reference; chúng giúp collector theo dõi các thay đổi cần thiết, bao gồm thông tin tham chiếu giữa các thế hệ.
- **Metadata và remembered information:** hỗ trợ collector biết những vùng hoặc object nào cần xem xét khi thu gom một thế hệ riêng lẻ.

Barrier thường được tối ưu để chi phí trên mỗi thao tác nhỏ, nhưng tổng chi phí có thể đáng kể với workload có mật độ đọc/ghi reference cao. Ứng dụng cũng chia sẻ CPU, cache và memory bandwidth với các GC threads.

Do đó, Generational ZGC có thể giảm pause nhưng không đồng nghĩa mọi workload đều tăng throughput. Hãy đánh giá cả latency lẫn tổng tài nguyên tiêu thụ.

## 8. Những khoảng dừng stop-the-world còn tồn tại

Generational ZGC là concurrent collector, nhưng vẫn có các pha cần dừng application threads trong thời gian ngắn để đồng bộ. Các pause thường liên quan đến việc bắt đầu/kết thúc marking hoặc chuẩn bị relocation.

Đặc điểm quan trọng:

- Phần lớn thời gian marking và relocation có thể chạy đồng thời với ứng dụng.
- Pause không biến mất hoàn toàn; số lượng thread, root set, trạng thái heap và công việc đồng bộ ảnh hưởng đến thời gian pause.
- Concurrent work có thể làm giảm thời gian dừng nhưng vẫn tiêu thụ CPU trong lúc ứng dụng đang chạy.
- Nếu hệ thống thiếu CPU hoặc GC không theo kịp tốc độ cấp phát, ứng dụng có thể gặp allocation stalls dù pause ngắn.

Không đánh giá ZGC chỉ bằng một con số “max pause”. Cần xem thêm allocation stalls, throughput, CPU, heap occupancy và độ trễ đầu-cuối của request.

## 9. Allocation stalls và áp lực bộ nhớ

Ứng dụng cấp phát object liên tục. Nếu tốc độ cấp phát cao hơn khả năng thu hồi và bổ sung vùng nhớ, JVM có thể phải chờ GC giải phóng đủ không gian trước khi tiếp tục cấp phát. Thời gian chờ này được gọi là allocation stall.

Allocation stall không giống stop-the-world pause. Nó có thể xảy ra khi collector đang chạy đồng thời nhưng chưa kịp cung cấp vùng nhớ cho nhu cầu cấp phát hiện tại.

Các nguyên nhân thường gặp:

- Heap quá nhỏ so với live set và tốc độ cấp phát.
- Tạo object tạm thời với tốc độ rất cao.
- GC threads thiếu CPU vì ứng dụng hoặc tiến trình khác chiếm phần lớn CPU.
- Old generation tăng nhanh do object được giữ tham chiếu lâu hơn dự kiến.
- Workload có peak allocation lớn nhưng cấu hình heap hoặc headroom không đủ.

Khi gặp allocation stalls, cần xem lại heap sizing, tốc độ cấp phát, live set, CPU headroom và vòng đời object. Chỉ tăng số GC threads hoặc giảm pause target không chắc giải quyết được nguyên nhân gốc.

## 10. Ảnh hưởng đến latency và throughput

| Thành phần | Tác động tích cực có thể có | Chi phí hoặc giới hạn |
|---|---|---|
| Concurrent marking | Giảm lượng công việc phải thực hiện trong pause | Dùng CPU và băng thông bộ nhớ khi ứng dụng vẫn chạy |
| Young collection | Thu hồi object chết sớm thường xuyên | Workload tạo nhiều object vẫn cần cấp phát và xử lý barrier liên tục |
| Concurrent relocation | Giảm thời gian dừng do di chuyển object | Load barriers và di chuyển object tiêu tốn tài nguyên |
| Short pauses | Hỗ trợ workload nhạy với latency | Pause vẫn tồn tại và không phải giới hạn cứng cho mọi tình huống |
| Old generation collection | Kiểm soát tập object sống lâu | Live set lớn có thể làm tăng công việc marking/relocation |

ZGC thường phù hợp khi mục tiêu quan trọng là độ trễ GC thấp, đặc biệt với heap lớn hoặc ứng dụng nhạy với pause. Nếu ưu tiên throughput tối đa và ứng dụng chịu được pause dài hơn, hãy benchmark với các collector khác trên workload thật thay vì mặc định ZGC luôn tốt hơn.

## 11. Theo dõi các pha bằng unified GC logging

Java 21 dùng unified logging để ghi thông tin GC. Có thể bật log khi khởi chạy:

```bash
java -XX:+UseZGC -XX:+ZGenerational -Xms4g -Xmx4g -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
```

Các tag `gc` và `safepoint` giúp quan sát chu kỳ GC, các pha và thời gian pause. Tùy nhu cầu, có thể tăng mức chi tiết của log khi điều tra trên môi trường thử nghiệm; tránh bật log quá chi tiết trong production nếu chưa đánh giá chi phí I/O và dung lượng log.

Khi đọc log, hãy tìm:

- Loại collection đang chạy: young hay old.
- Thời gian các pha concurrent và các pause.
- Heap occupancy trước/sau collection và lượng bộ nhớ thu hồi.
- Dấu hiệu allocation stall hoặc GC liên tục không theo kịp cấp phát.
- Các thay đổi về CPU và latency ứng dụng trong cùng khoảng thời gian.

Không so sánh trực tiếp tên pha hoặc số liệu giữa các JDK khác nhau nếu chưa đối chiếu định dạng log và implementation của từng phiên bản.

## 12. Đo bằng Java Flight Recorder và workload thực tế

Java Flight Recorder (JFR) có thể bổ sung dữ liệu về GC, allocation và hoạt động của ứng dụng. Có thể bắt đầu recording khi chạy ứng dụng:

```bash
java -XX:StartFlightRecording=filename=zgc.jfr,settings=profile,dumponexit=true -XX:+UseZGC -XX:+ZGenerational -jar app.jar
```

Phân tích recording cùng GC log để trả lời các câu hỏi:

- Allocation rate và live set có ổn định không?
- Young collection diễn ra với nhịp nào và thu hồi được bao nhiêu?
- Old generation có tăng liên tục hay không?
- CPU có đủ headroom cho concurrent GC không?
- Latency p95/p99 có thay đổi khi GC chạy không?
- Có allocation stalls hoặc thời gian chờ cấp phát đáng kể không?

Benchmark cần dùng dữ liệu và concurrency gần với production. Một microbenchmark nhỏ không đại diện cho workload có heap lớn, nhiều thread, cache nóng và nhiều object sống lâu.

## 13. Cấu hình theo phiên bản JDK

Generational ZGC được giới thiệu trong JDK 21 qua JEP 439. Trên JDK 21, cần bật rõ chế độ generational:

```bash
java -XX:+UseZGC -XX:+ZGenerational -jar app.jar
```

Các bản JDK mới đã thay đổi mặc định: JDK 23 đặt Generational ZGC làm chế độ mặc định của ZGC (JEP 474), và JDK 24 loại bỏ chế độ non-generational (JEP 490). Vì vậy, khi chạy JDK mới, không nên sao chép cấu hình cũ để tắt generational mode hoặc dựa vào tùy chọn của chế độ non-generational đã bị loại bỏ.

Luôn kiểm tra tài liệu của đúng JDK triển khai. `--release 21` khi biên dịch chỉ đặt mức ngôn ngữ/API mục tiêu; nó không quyết định collector hay các mặc định của JVM lúc chạy.

## 14. Nguyên tắc vận hành

1. Xác định mục tiêu chính là latency, throughput hay chi phí CPU trước khi chọn collector.
2. Đo allocation rate, live set và heap headroom bằng workload đại diện.
3. Bật GC logging có kiểm soát và phân biệt pause với concurrent phase.
4. Theo dõi allocation stalls; pause ngắn không đảm bảo ứng dụng không phải chờ cấp phát.
5. Giữ CPU headroom cho GC threads để concurrent work theo kịp tốc độ cấp phát.
6. Đánh giá cả young và old collection, đặc biệt khi old generation tăng liên tục.
7. Benchmark lại sau khi đổi heap size, concurrency, JDK hoặc cấu hình GC.
8. Dùng cấu hình Generational ZGC tương ứng với runtime; tránh các tùy chọn non-generational đã bị loại bỏ ở JDK mới.

## 15. Biên dịch và chạy với Java 21

Generational ZGC là tính năng được giới thiệu trong Java 21. Ví dụ dưới đây bật ZGC generational trên JDK 21:

```bash
javac --release 21 -d out src/ZgcWorkload.java
java -XX:+UseZGC -XX:+ZGenerational -Xms4g -Xmx4g -Xlog:gc*,safepoint -cp out ZgcWorkload
```

Không cần `--enable-preview`. Khi chạy trên JDK 23 trở lên, kiểm tra mặc định và tùy chọn theo tài liệu runtime tương ứng; không giả định cấu hình JDK 21 phải được giữ nguyên.

## 16. Tài liệu tham khảo

- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490)
- [Oracle — Z Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector.html)
- [Oracle — Available Garbage Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html)
- [Java SE 21 — Unified Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
