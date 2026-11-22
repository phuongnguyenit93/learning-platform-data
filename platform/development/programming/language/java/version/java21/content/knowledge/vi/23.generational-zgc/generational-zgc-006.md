# Thiết lập heap có đủ headroom cho thu gom đồng thời

Generational ZGC thực hiện phần lớn công việc thu gom rác đồng thời với ứng dụng. Trong lúc GC đang đánh dấu và thu hồi object, ứng dụng vẫn tiếp tục cấp phát object mới. Vì vậy, heap phải có đủ chỗ cho **live set** và lượng cấp phát phát sinh trong thời gian GC hoàn thành một chu kỳ cần thiết. Phần dung lượng còn lại đó được gọi là **headroom**.

Nếu chỉ đặt heap vừa bằng lượng object còn sống, ứng dụng có thể cấp phát nhanh hơn GC thu hồi và dẫn tới allocation stall hoặc hết bộ nhớ. Cấu hình heap vì thế cần dựa trên live set, allocation rate, thời gian chu kỳ GC, các đợt tăng tải và ngân sách bộ nhớ của container hoặc máy chủ.

## 1. Vì sao Generational ZGC cần headroom?

ZGC là garbage collector có tính đồng thời: ứng dụng tiếp tục chạy trong khi GC thực hiện các công việc tốn thời gian. Generational ZGC chia object theo thế hệ để ưu tiên thu gom các object trẻ thường chết sớm, giảm lượng công việc và chi phí GC trong nhiều workload.

ZGC tự điều chỉnh kích thước các thế hệ, số GC thread và ngưỡng tenuring theo workload. Vì vậy, bước tuning heap đầu tiên thường là cung cấp -Xmx đủ headroom và đo kết quả; không nên tự đặt kích thước young/old generation theo một tỷ lệ cố định nếu chưa có số liệu chứng minh cần thiết.

Tuy nhiên, GC đồng thời không thể thu hồi ngay mọi object đã trở nên không còn được tham chiếu. Trong khi chu kỳ GC diễn ra:

- Ứng dụng tiếp tục tạo object mới.
- Một số object cũ vẫn còn được tham chiếu và thuộc live set.
- Object sống lâu có thể được giữ lại hoặc chuyển sang thế hệ cũ.
- GC cần thời gian và tài nguyên CPU để hoàn thành công việc thu gom.

Heap phải đủ lớn để các allocation tiếp tục được đáp ứng trong khoảng thời gian GC đang làm việc. Generational ZGC giảm áp lực bộ nhớ so với ZGC không phân thế hệ trong nhiều trường hợp, nhưng không loại bỏ yêu cầu headroom.

## 2. Phân biệt live set, heap occupancy và headroom

Ba khái niệm này không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| **Live set** | Dung lượng object còn được ứng dụng tham chiếu và phải giữ lại |
| **Heap occupancy** | Dung lượng heap đang được sử dụng tại một thời điểm, gồm cả object sẽ được thu hồi |
| **Headroom** | Dung lượng heap còn khả dụng để đáp ứng allocation trước khi GC thu hồi đủ bộ nhớ |

Ví dụ, heap có giới hạn 8 GB, live set ổn định khoảng 4 GB và đang có 2 GB object chờ được thu hồi. Nếu 2 GB còn lại chưa được GC thu hồi, heap occupancy có thể gần 6 GB. Không thể kết luận rằng live set là 6 GB chỉ từ một lần quan sát heap đang dùng.

Khi sizing, hãy quan sát lượng dữ liệu còn sống sau các chu kỳ thu gom phù hợp, thay vì lấy một con số heap used ở thời điểm tải cao làm live set. Với Generational ZGC, cần đọc log và số liệu theo thế hệ để hiểu áp lực ở young generation và old generation.

## 3. Ước lượng headroom từ allocation rate và thời gian GC

Một ước lượng ban đầu hữu ích là:

**Heap mục tiêu ≈ Live set + Headroom + Khoảng dự phòng**

Trong đó:

**Headroom ước lượng ≈ Allocation rate × Thời gian GC cần để thu hồi bộ nhớ**

Ví dụ minh họa:

- Live set ở tải cao: khoảng 4,5 GB.
- Allocation rate quan sát được: 0,8 GB/giây.
- Thời gian chu kỳ GC liên quan: 1,5 giây.
- Dự phòng cho burst allocation và dao động workload: 0,8 GB.

Headroom cơ sở ước lượng là 0,8 × 1,5 = 1,2 GB. Tổng dung lượng ban đầu cần tính đến là 4,5 + 1,2 + 0,8 = 6,5 GB. Có thể bắt đầu thử nghiệm với **-Xmx8g**, sau đó đo lại dưới workload thực tế.

Đây là mô hình ước lượng để chọn cấu hình thử nghiệm, không phải công thức bảo đảm chính xác. Allocation rate, thời gian GC, tỷ lệ object sống sót và burst có thể thay đổi theo tải. Hãy dùng các giá trị đo ở giai đoạn xấu nhất có tính đại diện, rồi kiểm chứng bằng load test.

Không chỉ dùng allocation rate trung bình. Một đợt burst ngắn có thể tạo nhiều object hơn mức trung bình trong khoảng thời gian GC đang thu gom. Cần quan sát cả peak allocation rate và phân bố thời gian chu kỳ GC.

## 4. Đặt giới hạn heap bằng -Xmx

**-Xmx** là giới hạn tối đa của Java heap và là nút cấu hình quan trọng nhất khi tuning ZGC. Heap tối đa phải chứa được live set cùng headroom cần thiết cho allocation trong lúc GC chạy.

Ví dụ cấu hình Java 21:

~~~bash
java \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  -Xms4g \
  -Xmx8g \
  -jar application.jar
~~~

Trong ví dụ:

- **-XX:+UseZGC** chọn ZGC.
- **-XX:+ZGenerational** bật Generational ZGC trên JDK 21.
- **-Xms4g** đặt kích thước heap tối thiểu ban đầu là 4 GB.
- **-Xmx8g** giới hạn heap tối đa ở 8 GB.

Nếu -Xmx quá sát live set, ứng dụng dễ thiếu chỗ cho allocation khi GC chưa thu hồi xong. Nếu -Xmx quá lớn so với nhu cầu và ngân sách bộ nhớ, tiến trình có thể chiếm dụng tài nguyên không cần thiết hoặc gây áp lực lên các workload khác.

Không đặt -Xmx bằng tổng RAM của máy hoặc container. JVM còn cần bộ nhớ ngoài heap.

## 5. Dùng SoftMaxHeapSize như một giới hạn mềm

**-XX:SoftMaxHeapSize** đặt mục tiêu mềm cho kích thước heap. ZGC cố gắng giữ heap không vượt mức này, nhưng vẫn được phép tăng vượt SoftMaxHeapSize tới giới hạn cứng -Xmx nếu cần để tránh ứng dụng bị stall vì chờ GC thu hồi bộ nhớ.

~~~bash
java \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  -Xms4g \
  -Xmx8g \
  -XX:SoftMaxHeapSize=7g \
  -jar application.jar
~~~

Với cấu hình trên, 7 GB là mục tiêu mềm cho các heuristic của ZGC; 8 GB vẫn là giới hạn tối đa. SoftMaxHeapSize không phải giới hạn cứng và không thay thế -Xmx.

Chỉ nên đặt SoftMaxHeapSize sau khi đã đo được live set và headroom. Nếu đặt quá thấp, ZGC có thể thường xuyên phải dùng phần dung lượng vượt soft limit. Nếu cần dùng phần vượt này trong thời gian dài, hãy đánh giá lại soft limit hoặc giảm live set/allocation rate thay vì dựa vào nó như một heap tối đa thứ hai.

## 6. Tách ngân sách heap khỏi bộ nhớ của tiến trình

**-Xmx** chỉ giới hạn Java heap. Tổng bộ nhớ tiến trình còn bao gồm:

- Metaspace và class metadata.
- JIT code cache.
- Thread stack của platform thread.
- Direct buffer và các vùng native memory.
- Thư viện native, cấu trúc nội bộ của JVM và dữ liệu phục vụ GC.
- Bộ nhớ khác do ứng dụng hoặc thư viện cấp phát ngoài heap.

Trong container, tổng RSS hoặc mức memory usage có thể cao hơn heap occupancy đáng kể. Nếu đặt -Xmx sát memory limit của container, tiến trình có thể bị hệ điều hành kết thúc vì vượt giới hạn bộ nhớ dù Java heap chưa chạm -Xmx.

Ví dụ minh họa với container giới hạn 10 GiB:

| Thành phần | Ngân sách ví dụ |
|---|---:|
| Java heap tối đa | 7 GiB |
| Metaspace, code cache, stack và native memory | 2 GiB |
| Dự phòng cho biến động và bộ nhớ hệ thống | 1 GiB |
| Tổng | 10 GiB |

Các con số trên chỉ minh họa cách chia ngân sách. Hãy đo mức sử dụng native memory và RSS của ứng dụng thật; không mặc định mọi ứng dụng đều cần đúng 2 GiB ngoài heap.

## 7. Chọn Xms, uncommit và AlwaysPreTouch theo mục tiêu vận hành

ZGC có thể trả lại vùng heap không còn cần thiết cho hệ điều hành bằng cơ chế **uncommit**. Điều này giảm memory footprint khi tải giảm, nhưng việc commit/uncommit trong lúc ứng dụng chạy có thể ảnh hưởng latency.

Các tùy chọn cần biết:

| Tùy chọn | Ý nghĩa |
|---|---|
| **-Xms** | Kích thước heap tối thiểu |
| **-Xmx** | Kích thước heap tối đa |
| **-XX:-ZUncommit** | Tắt việc ZGC trả lại bộ nhớ heap không dùng cho hệ điều hành |
| **-XX:ZUncommitDelay** | Đặt thời gian chờ uncommit theo giây; mặc định là 300 giây |
| **-XX:+AlwaysPreTouch** | Chạm vào các trang heap trước khi ứng dụng bắt đầu chạy để giảm công việc page-in về sau |

Nếu ưu tiên latency rất thấp và máy/container có đủ ngân sách, có thể đặt **-Xms bằng -Xmx** để giữ heap ở kích thước cố định. Khi Xms bằng Xmx, ZGC không uncommit heap xuống thấp hơn mức đó; có thể kết hợp AlwaysPreTouch để page-in bộ nhớ trước khi xử lý request.

~~~bash
java \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  -Xms8g \
  -Xmx8g \
  -XX:+AlwaysPreTouch \
  -jar application.jar
~~~

Cấu hình heap cố định làm tăng mức bộ nhớ được giữ trong suốt vòng đời tiến trình và có thể làm startup lâu hơn. Nếu ưu tiên giảm memory footprint trong môi trường dùng chung, giữ Xms thấp hơn Xmx và để ZGC uncommit bộ nhớ không dùng có thể phù hợp hơn. Không tắt uncommit hoặc pre-touch chỉ vì đó là cấu hình được dùng trong một workload khác.

## 8. Đo live set và allocation rate trước khi tăng heap

Trước khi thay đổi -Xmx, cần có số liệu đại diện cho production:

1. Chạy workload có tỷ lệ request, payload, cache và thời gian sống object gần với thực tế.
2. Warm up ứng dụng và JVM trước khi lấy baseline.
3. Quan sát heap sau các chu kỳ GC thích hợp để ước lượng live set.
4. Đo allocation rate trong cả tải bình thường và burst.
5. Ghi thời gian các chu kỳ GC và mức heap còn trống khi GC đang chạy.
6. Theo dõi p95/p99 latency, throughput và allocation stall cùng với GC.

Có thể dùng unified logging để thu thập thông tin GC:

~~~bash
java \
  -XX:+UseZGC \
  -XX:+ZGenerational \
  -Xmx8g \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar application.jar
~~~

Trong quá trình chạy, **jcmd** có thể cung cấp thông tin heap và flags đang hoạt động:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.flags
~~~

Java Flight Recorder có thể bổ sung dữ liệu về allocation, GC và hoạt động của ứng dụng. Hãy dùng log/JFR để đối chiếu thời điểm allocation tăng với chu kỳ GC, thay vì chỉ lấy một ảnh chụp heap đơn lẻ.

## 9. Dấu hiệu heap thiếu headroom

Một số tín hiệu cho thấy cấu hình heap có thể quá sát nhu cầu:

| Dấu hiệu | Điều cần kiểm tra |
|---|---|
| Allocation stall hoặc ứng dụng phải chờ GC thu hồi bộ nhớ | Headroom còn lại, allocation rate và thời gian GC |
| Heap thường xuyên tiến sát -Xmx | Live set, burst allocation, SoftMaxHeapSize và Xmx |
| GC chạy liên tục nhưng heap sau thu gom vẫn cao | Live set tăng, cache giữ object hoặc memory leak |
| p99 tăng trong lúc CPU GC tăng | GC cần thêm CPU hoặc đang cạnh tranh CPU với ứng dụng |
| Container bị OOMKilled khi heap chưa chạm -Xmx | Native memory, direct buffer, stack, metaspace và memory limit |
| Heap giảm sau khi tải kết thúc nhưng latency tăng khi tải quay lại | Uncommit/commit và chính sách Xms, ZUncommitDelay |

Không phải mọi latency spike đều do thiếu headroom. CPU throttling, lock contention, I/O, network và dịch vụ phụ thuộc cũng có thể gây chậm. Luôn đối chiếu GC logs với metrics của ứng dụng và container.

## 10. Điều chỉnh headroom theo workload

Khi kết quả đo cho thấy thiếu headroom, thực hiện thay đổi theo từng bước:

- Tăng -Xmx nếu container hoặc máy chủ còn đủ ngân sách ngoài heap.
- Giảm allocation rate bằng cách tránh tạo object không cần thiết, tái sử dụng dữ liệu phù hợp hoặc giảm copy payload.
- Giảm live set bằng cách giới hạn cache, rút ngắn thời gian giữ tham chiếu và loại bỏ dữ liệu không cần thiết.
- Kiểm tra CPU có đủ để GC hoàn tất công việc đồng thời đúng thời gian hay không.
- Điều chỉnh SoftMaxHeapSize nếu soft limit đang quá thấp so với nhu cầu thực tế.
- Kiểm tra workload burst và giới hạn concurrency để tránh tạo lượng allocation vượt khả năng hệ thống.

Không tăng -Xmx nếu container đã gần memory limit. Trong trường hợp đó, hãy xem xét giảm live set, allocation rate hoặc concurrency; nếu vẫn cần headroom lớn hơn, phải tăng ngân sách memory của môi trường triển khai.

## 11. Phân biệt cấu hình Generational ZGC theo phiên bản JDK

Generational ZGC được giới thiệu trong Java 21. Tùy chọn bật chế độ generational thay đổi theo phiên bản:

| Runtime | Cách dùng |
|---|---|
| **JDK 21** | Bật bằng **-XX:+UseZGC -XX:+ZGenerational** |
| **JDK 23** | Generational mode trở thành mặc định của ZGC; chế độ không phân thế hệ bị deprecated |
| **JDK 24 trở lên** | ZGC luôn là generational; tùy chọn **ZGenerational** đã bị loại bỏ |

Các ví dụ lệnh trong bài có cả **-XX:+ZGenerational** là dành cho JDK 21. Khi chạy trên JDK 24 hoặc mới hơn, bỏ tùy chọn đó và dùng **-XX:+UseZGC**. Không đưa cờ đã bị loại bỏ vào cấu hình runtime mới.

Điểm cốt lõi của việc sizing heap vẫn giữ nguyên ở các phiên bản: heap phải chứa live set và có đủ headroom cho allocation trong khi GC chạy. Tên hoặc mặc định của chế độ GC thay đổi không làm mất yêu cầu này.

## 12. Quy trình sizing heap có headroom

1. Xác nhận JDK/runtime thực tế và chế độ Generational ZGC đang chạy.
2. Đo live set trong workload đại diện, gồm cả giờ cao điểm.
3. Đo allocation rate và thời gian chu kỳ GC liên quan.
4. Ước lượng headroom từ allocation trong thời gian GC, cộng dự phòng cho burst.
5. Chọn -Xmx theo live set + headroom + khoảng dự phòng.
6. Trừ riêng ngân sách metaspace, code cache, stack, direct buffer và native memory khỏi memory limit của container.
7. Chọn -Xms, SoftMaxHeapSize và uncommit theo mục tiêu latency hay memory footprint.
8. Load test ở tải bình thường, peak và burst; kiểm tra p95/p99, GC logs, allocation stalls và container RSS.
9. Điều chỉnh từng biến một và giữ lại cấu hình có kết quả đo đáp ứng SLO.

## 13. Checklist cấu hình Generational ZGC

- [ ] Dùng Generational ZGC trên runtime mục tiêu; với JDK 21 bật rõ **-XX:+UseZGC -XX:+ZGenerational**.
- [ ] Đo live set thay vì sizing theo heap occupancy tại một thời điểm bất kỳ.
- [ ] Đo allocation rate và thời gian GC để ước lượng headroom.
- [ ] Có dự phòng cho burst allocation và biến động workload.
- [ ] Đặt -Xmx đủ cho live set cùng headroom.
- [ ] Giữ ngân sách cho native memory và phần ngoài heap trong container.
- [ ] Dùng SoftMaxHeapSize như giới hạn mềm, không nhầm với -Xmx.
- [ ] Chọn Xms/uncommit/AlwaysPreTouch theo yêu cầu latency và memory footprint.
- [ ] Theo dõi GC logs, JFR, heap info, allocation stalls và container RSS.
- [ ] Không dùng cờ ZGenerational trên JDK 24 trở lên.

## Tài liệu tham khảo

- [Java SE 21: The Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html)
- [Java SE 21: Available Garbage Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html)
- [JEP 439: Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 474: ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [Oracle: Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
