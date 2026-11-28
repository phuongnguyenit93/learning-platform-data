# Tách cải tiến có từ Java 16 khỏi các thế hệ ZGC của JDK hiện đại

Java 16 cải tiến Z Garbage Collector (ZGC) bằng cách chuyển xử lý thread stack sang giai đoạn concurrent, theo JEP 376. Thay đổi này giảm phần công việc phải thực hiện trong safepoint, đặc biệt hữu ích với ứng dụng có nhiều thread hoặc stack lớn. Đây là cải tiến về cách ZGC xử lý root references; nó chưa phải Generational ZGC.

Generational ZGC xuất hiện sau đó trong JDK 21 theo JEP 439. Từ JDK 23, chế độ generational trở thành mặc định của ZGC; JDK 24 loại bỏ chế độ non-generational. Vì vậy, khi sử dụng ZGC trên JDK hiện đại, cần hiểu đúng cải tiến Java 16 trong lịch sử phát triển, đồng thời cấu hình và vận hành theo mô hình generational hiện hành.

## 1. ZGC hướng đến mục tiêu gì?

ZGC là garbage collector của HotSpot được thiết kế cho ứng dụng cần độ trễ thấp, kể cả khi heap lớn. ZGC thực hiện phần lớn công việc đánh dấu và thu hồi bộ nhớ đồng thời với các thread ứng dụng. Mục tiêu là giữ các lần dừng ứng dụng ngắn và ít phụ thuộc vào kích thước heap.

Cần phân biệt ba khái niệm:

- **GC pause:** khoảng thời gian các thread ứng dụng bị dừng để JVM thực hiện một công việc cần safepoint.
- **GC cycle:** toàn bộ chu trình thu gom, gồm cả các pha concurrent và các pha cần dừng ngắn.
- **Application latency:** thời gian người dùng hoặc hệ thống phải chờ một thao tác hoàn tất.

GC pause ngắn có thể giúp giảm tail latency, nhưng không bảo đảm mọi request đều nhanh. Request vẫn có thể chậm do CPU contention, lock, I/O, scheduling, allocation stall, network hoặc code ứng dụng.

ZGC hướng đến giảm tác động của garbage collection lên độ trễ. Nó không biến ứng dụng thành hệ thống không có pause hoặc không có giới hạn bộ nhớ.

## 2. Cải tiến của Java 16: Concurrent Thread-Stack Processing

Theo JEP 376, Java 16 chuyển việc xử lý thread stack của ZGC từ safepoint sang giai đoạn concurrent.

Trước thay đổi này, xử lý stack của các thread là một phần công việc cần thực hiện khi JVM đưa ứng dụng tới safepoint. Thời gian xử lý có thể phụ thuộc vào số lượng thread và lượng dữ liệu cần quét trên stack. Với ứng dụng có nhiều thread, phần việc này có thể đóng góp đáng kể vào pause.

Java 16 cho phép ZGC xử lý thread stack đồng thời với ứng dụng. Nhờ đó, công việc quét stack không còn phải thực hiện toàn bộ trong một safepoint như trước. Thay đổi này giúp giảm thời gian pause và làm pause ít phụ thuộc hơn vào số lượng thread.

Ý nghĩa thực tế:

- Ứng dụng có nhiều thread có thể giảm phần pause liên quan đến xử lý stack.
- Thread stack lớn không còn khiến toàn bộ công việc quét stack nằm trong cùng một khoảng dừng như trước.
- ZGC có thể tiếp tục xử lý stack trong pha concurrent, trong khi thread ứng dụng vẫn hoạt động.
- Đây là cải tiến nội bộ của HotSpot; ứng dụng không cần gọi API mới hoặc thay đổi cách viết Java.

JEP 376 tập trung vào thread-stack processing. Không nên diễn giải thành việc mọi hoạt động của GC đều chạy concurrent hoặc ZGC không cần safepoint nữa. Một số công việc vẫn cần các điểm đồng bộ ngắn và JVM vẫn có thể dừng thread ứng dụng cho các hoạt động khác.

## 3. Vì sao xử lý thread stack ảnh hưởng đến độ trễ?

Thread stack chứa các tham chiếu tới object mà thread đang sử dụng. Khi GC đánh dấu object còn sống, JVM phải nhận diện các tham chiếu gốc (root references) để không thu hồi nhầm object vẫn có thể được truy cập.

Các nguồn root references gồm:

- Tham chiếu trong stack frame của thread đang chạy.
- Tham chiếu trong thanh ghi được JVM quản lý tại các điểm phù hợp.
- Static fields và các cấu trúc runtime liên quan.
- Những root khác do JVM quản lý.

Nếu việc xử lý stack phải diễn ra trong safepoint, pause có thể tăng khi số thread hoặc lượng stack cần xử lý tăng. Chuyển công việc này sang concurrent phase giúp giảm lượng công việc phải hoàn thành trong khoảng dừng.

Có thể hình dung sự khác nhau:

```text
Trước cải tiến:
Ứng dụng chạy ---------[ Safepoint: xử lý thread stacks ]---------> chạy tiếp
                         <------ pause ------>

Từ Java 16 với ZGC:
Ứng dụng chạy --[ safepoint ngắn ]-- chạy và GC xử lý stacks concurrent
                                      [ concurrent work ]
```

Sơ đồ chỉ minh họa việc chuyển phần xử lý thread stack ra khỏi safepoint. Nó không mô tả đầy đủ mọi pha của chu trình ZGC.

## 4. Cải tiến Java 16 không đồng nghĩa Generational ZGC

Đây là điểm cần tách bạch khi đọc tài liệu về ZGC qua nhiều phiên bản.

Java 16 cải tiến **cách ZGC xử lý thread stack**. Generational ZGC thay đổi **cách tổ chức và thu gom heap theo thế hệ object**. Hai cải tiến giải quyết hai vấn đề khác nhau:

| Nội dung | Cải tiến Java 16 | Generational ZGC |
|---|---|---|
| Thay đổi chính | Concurrent thread-stack processing | Chia heap thành young generation và old generation |
| Mục tiêu | Giảm công việc trong safepoint | Thu gom object ngắn hạn hiệu quả hơn |
| JEP | JEP 376 | JEP 439 |
| Phiên bản đầu tiên | Java 16 | JDK 21 |
| Phạm vi | Thread-stack processing trong ZGC | Chiến lược quản lý và thu gom object theo tuổi |

Một JVM hiện đại có thể sử dụng các cải tiến thread-stack processing được đưa vào từ Java 16 cùng với mô hình Generational ZGC được bổ sung sau đó. Không nên gọi tính năng concurrent thread-stack processing là Generational ZGC.

## 5. Generational ZGC xuất hiện trong JDK 21

JEP 439 đưa Generational ZGC vào JDK 21. Ý tưởng cốt lõi dựa trên đặc điểm phổ biến của object trong ứng dụng:

- Nhiều object chỉ sống trong thời gian ngắn.
- Một phần nhỏ object tồn tại lâu và được giữ qua nhiều chu kỳ GC.
- Thu gom object trẻ thường xuyên có thể hiệu quả hơn việc xử lý toàn bộ heap theo cùng một cách.

Generational ZGC chia heap thành hai thế hệ:

- **Young generation:** chứa object mới tạo và các object còn trẻ. Thế hệ này được thu gom thường xuyên hơn.
- **Old generation:** chứa object sống lâu hơn và được giữ qua các lần thu gom young generation.

Việc tách thế hệ giúp GC tập trung công việc vào object trẻ, vốn thường có tỷ lệ thu hồi cao. Object sống lâu được xử lý theo chu kỳ phù hợp với old generation.

Theo mục tiêu của JEP 439, Generational ZGC hướng đến giảm allocation stalls, heap memory overhead và CPU overhead cho GC, đồng thời duy trì mục tiêu pause rất thấp của ZGC.

## 6. Các mốc phát triển cần nhớ

| Phiên bản JDK | Thay đổi liên quan đến ZGC | Ý nghĩa hiện nay |
|---|---|---|
| Java 16 | JEP 376: concurrent thread-stack processing | Cải tiến nền tảng giúp giảm phần pause do xử lý stack |
| JDK 21 | JEP 439: Generational ZGC được giới thiệu | Bắt đầu mô hình young/old generation |
| JDK 23 | JEP 474: Generational ZGC trở thành chế độ mặc định | Hành vi mặc định chuyển sang generational |
| JDK 24 | JEP 490: loại bỏ non-generational mode | ZGC tiếp tục theo mô hình generational |

Mốc Java 16 giúp giải thích vì sao pause của ZGC được cải thiện. Khi triển khai mới, nên dùng JDK còn được hỗ trợ và theo dõi tài liệu của phiên bản đó. Trên JDK 24 trở lên, không còn lựa chọn quay lại non-generational ZGC.

## 7. Cấu hình ZGC trên JDK hiện đại

Với JDK hiện đại có Generational ZGC, lựa chọn collector bằng tùy chọn:

```bash
java -XX:+UseZGC -jar application.jar
```

Từ JDK 24, ZGC chỉ còn chế độ generational. Vì vậy, không cần thêm một cờ chuyển chế độ generational khi chạy trên các JDK này.

Nếu cần đặt giới hạn heap, dùng các tùy chọn heap thông thường phù hợp với workload và giới hạn container/máy chủ, ví dụ:

```bash
java -XX:+UseZGC -Xms2g -Xmx8g -jar application.jar
```

Các con số trên chỉ là minh họa. Không sao chép dung lượng heap vào production khi chưa đo nhu cầu thực tế. `-Xms` và `-Xmx` cần phù hợp với tổng memory limit, native memory, thread stacks, direct buffers và các thành phần khác của tiến trình.

Không nên dựa vào các cờ chuyển tiếp từng được dùng để bật thử nghiệm Generational ZGC ở các JDK đầu tiên. Hãy kiểm tra phiên bản runtime và tài liệu option của đúng JDK đang triển khai trước khi đưa JVM flags vào cấu hình production.

## 8. Quan sát GC pause và safepoint

Unified Logging là cách hiện hành để thu thập log GC và safepoint. Ví dụ:

```bash
java -XX:+UseZGC -Xlog:gc*,safepoint -jar application.jar
```

Log giúp phân tích:

- Thời điểm bắt đầu và kết thúc GC cycle.
- Các pha GC và thời gian của chúng.
- Thời lượng safepoint.
- Heap occupancy trước và sau các pha thu gom.
- Allocation rate và những dấu hiệu GC không theo kịp tốc độ cấp phát.

Không chỉ nhìn dòng tổng kết GC. Hãy so sánh pause và safepoint với latency của ứng dụng trong cùng khoảng thời gian. Nếu request chậm nhưng GC pause ngắn, nguyên nhân có thể nằm ở CPU, lock, I/O, network hoặc allocation stall.

Định dạng chi tiết của log có thể thay đổi giữa các phiên bản JDK. Khi viết bộ phân tích log tự động, nên xác định phiên bản runtime và tránh phụ thuộc vào một chuỗi log duy nhất.

## 9. Dùng jcmd và JFR để điều tra

`jcmd` là công cụ gửi diagnostic command tới JVM đang chạy. Có thể xem các lệnh mà JVM hỗ trợ:

```bash
jcmd <pid> help
```

Một số lệnh hữu ích tùy phiên bản JDK:

```bash
jcmd <pid> GC.heap_info
```

```bash
jcmd <pid> VM.flags
```

`GC.heap_info` cung cấp thông tin heap mà JVM công bố; `VM.flags` giúp xác nhận các tùy chọn đang có hiệu lực. Không phải mọi collector hoặc mọi bản JDK đều trình bày cùng một bộ chỉ số.

Java Flight Recorder (JFR) hỗ trợ thu thập sự kiện runtime để đối chiếu GC với hoạt động ứng dụng. Có thể bắt đầu một recording theo cấu hình có sẵn:

```bash
jcmd <pid> JFR.start name=latency settings=profile duration=5m filename=latency.jfr
```

Lệnh mẫu tạo recording trong năm phút; cú pháp và tùy chọn cần kiểm tra bằng help của JFR.start trên JDK thực tế. Khi phân tích, xem các sự kiện GC, safepoint, thread scheduling, allocation và CPU để tìm tương quan với latency.

Có thể xem cú pháp chính xác của command này trên tiến trình đang chạy bằng:

~~~bash
jcmd <pid> help JFR.start
~~~

## 10. Khi nào nên cân nhắc ZGC?

ZGC phù hợp để đánh giá khi ứng dụng có yêu cầu latency chặt, heap lớn hoặc thời gian dừng GC là một phần đáng kể trong tail latency.

Các trường hợp có thể thử nghiệm:

- Dịch vụ xử lý request cần p99/p999 ổn định.
- Ứng dụng giữ heap lớn và không chấp nhận pause dài.
- Hệ thống có allocation rate cao.
- Ứng dụng có nhiều object sống ngắn và có thể hưởng lợi từ Generational ZGC.
- Workload có biến động mạnh và cần quan sát GC pause trong điều kiện thực tế.

Tuy nhiên, chọn ZGC không tự động làm ứng dụng nhanh hơn. ZGC sử dụng CPU cho công việc concurrent. Nếu CPU đã bão hòa, GC concurrent có thể cạnh tranh tài nguyên với application threads. Một collector khác có thể phù hợp hơn với workload, throughput target hoặc giới hạn tài nguyên cụ thể.

Hãy benchmark bằng cùng dữ liệu, cùng tải, cùng heap budget và cùng điều kiện máy/container. So sánh throughput, p50/p95/p99/p999 latency, GC pause, CPU utilization, allocation stalls và memory footprint.

## 11. Đánh giá cải tiến Java 16 trong hệ thống hiện đại

Để xác định cải tiến thread-stack processing có ý nghĩa với ứng dụng, hãy tìm bằng chứng thay vì chỉ nhìn vào phiên bản JDK.

Một quy trình đo:

1. Ghi nhận số thread và kích thước stack trong workload đại diện.
2. Thu thập GC log và safepoint log.
3. Đo p95/p99/p999 latency của request cùng khoảng thời gian.
4. Kiểm tra thời gian safepoint và các pha ZGC.
5. So sánh kết quả trên các JDK được hỗ trợ, giữ nguyên workload và cấu hình phù hợp.
6. Kiểm tra CPU overhead và throughput để tránh tối ưu pause bằng cách làm giảm năng lực xử lý tổng thể.

JEP 376 giải quyết một thành phần của pause. Nếu pause còn lại đã rất ngắn nhưng request vẫn chậm, tiếp tục điều tra các nguồn latency khác thay vì kỳ vọng GC có thể xử lý mọi vấn đề.

## 12. Các hiểu lầm thường gặp

**Cho rằng Java 16 đã giới thiệu Generational ZGC.** Java 16 đưa concurrent thread-stack processing vào ZGC. Generational ZGC được giới thiệu ở JDK 21.

**Cho rằng concurrent thread-stack processing loại bỏ mọi safepoint.** Thay đổi chuyển phần xử lý stack sang concurrent phase; ZGC vẫn có những điểm đồng bộ ngắn.

**Đồng nhất GC pause với request latency.** Pause ngắn không loại trừ allocation stall, CPU contention, lock hoặc I/O chậm.

**Cho rằng ZGC luôn nhanh hơn collector khác.** ZGC tối ưu cho mục tiêu latency thấp; throughput và CPU cost cần được đo theo workload.

**Dùng cấu hình chuyển tiếp từ JDK 21/22 trên JDK hiện đại.** Các tùy chọn thử nghiệm hoặc chuyển chế độ của giai đoạn đầu không còn là cấu hình cần thiết. Trên JDK 24 trở lên, ZGC chỉ còn generational mode.

**Chỉ xem heap occupancy.** Cần theo dõi GC cycle, safepoint, CPU, allocation rate và latency ứng dụng.

**Tăng heap để giải quyết mọi vấn đề GC.** Heap lớn hơn có thể thay đổi tần suất GC nhưng không sửa CPU saturation, allocation pressure hoặc classloader/resource leak.

**Kết luận thành công chỉ từ một lần benchmark.** Cần nhiều lần chạy ổn định, tải đại diện và cùng điều kiện so sánh.

## 13. Ghi nhớ

- Java 16 cải tiến ZGC bằng concurrent thread-stack processing theo JEP 376.
- Thay đổi này chuyển việc xử lý thread stack khỏi safepoint, giúp giảm phần pause liên quan đến stack.
- JEP 376 không phải Generational ZGC và không loại bỏ toàn bộ safepoint.
- Generational ZGC được giới thiệu trong JDK 21 theo JEP 439.
- Chế độ generational trở thành mặc định trong JDK 23 theo JEP 474.
- JDK 24 loại bỏ non-generational mode theo JEP 490.
- Trên JDK hiện đại, dùng `-XX:+UseZGC` để chọn ZGC; không cần cờ chuyển tiếp để bật generational mode.
- Dùng Unified Logging, `jcmd` và JFR để quan sát GC, safepoint và tác động tới ứng dụng.
- Đo cả pause, tail latency, throughput, CPU và allocation stalls.
- Chọn collector theo workload và mục tiêu vận hành, không chỉ dựa vào tên hoặc phiên bản JDK.

Cải tiến Java 16 là một bước quan trọng giúp ZGC giảm phần công việc phải thực hiện khi ứng dụng dừng tại safepoint. Generational ZGC bổ sung sau đó một chiến lược thu gom theo tuổi object. Khi vận hành trên JDK hiện đại, hãy hiểu hai lớp cải tiến này riêng biệt, dùng cấu hình hiện hành và đo tác động trên workload thực tế.

## Tài liệu tham khảo

- [JEP 376 – ZGC: Concurrent Thread-Stack Processing](https://openjdk.org/jeps/376) — cải tiến thread-stack processing trong Java 16.
- [JEP 439 – Generational ZGC](https://openjdk.org/jeps/439) — giới thiệu young và old generations trong JDK 21.
- [JEP 474 – ZGC: Generational Mode by Default](https://openjdk.org/jeps/474) — chuyển generational mode thành mặc định trong JDK 23.
- [JEP 490 – ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490) — loại bỏ non-generational mode trong JDK 24.
- [Z Garbage Collector – Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html) — hướng dẫn sử dụng và quan sát ZGC trên JDK hiện đại.

