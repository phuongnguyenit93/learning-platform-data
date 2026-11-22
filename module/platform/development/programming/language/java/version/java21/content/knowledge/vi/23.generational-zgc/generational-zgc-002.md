# Allocation rate, live set và lý do phân thế hệ

Generational ZGC chia heap thành Young Generation và Old Generation để tập trung thu gom thường xuyên vào nhóm object mới được cấp phát, vì phần lớn object trong nhiều ứng dụng trở thành unreachable khá sớm. Để hiểu vì sao cách tổ chức này hữu ích, cần phân biệt hai đặc điểm của workload: **allocation rate** cho biết ứng dụng tạo object nhanh đến mức nào, còn **live set** cho biết lượng object vẫn còn reachable và phải tiếp tục được giữ lại.

Hai đại lượng này trả lời hai câu hỏi khác nhau. Allocation rate ảnh hưởng đến tốc độ heap được sử dụng và lượng bộ nhớ cần dự phòng trong khi GC làm việc. Live set quyết định phần bộ nhớ nền mà collector không thể thu hồi. Phân thế hệ tận dụng thêm thông tin về thời gian sống của object để giảm công việc thu gom lặp lại trên những object đã tồn tại lâu.

## 1. Allocation rate là gì?

Allocation rate là lượng bộ nhớ heap mà ứng dụng cấp phát trong một đơn vị thời gian, thường biểu diễn bằng MB/s hoặc GB/s. Có thể ước lượng bằng:

\[
\text{Allocation rate} \approx
\frac{\text{Tổng byte được cấp phát trong khoảng đo}}
{\text{Thời gian đo}}
\]

Ví dụ, nếu một dịch vụ cấp phát khoảng 600 MB trong 2 giây thì allocation rate trung bình trong khoảng đó là khoảng 300 MB/s.

Allocation rate cao thường xuất hiện ở các workload tạo nhiều object tạm:

- Xử lý request HTTP, tạo request/response object và buffer.
- Parse JSON, XML hoặc dữ liệu giao thức.
- Xây dựng chuỗi, collection trung gian và kết quả truy vấn.
- Xử lý message, event hoặc batch có vòng đời ngắn.

Allocation rate không cho biết có bao nhiêu object còn sống sau GC. Một ứng dụng có thể cấp phát hàng GB mỗi giây nhưng phần lớn object trở thành unreachable ngay sau khi xử lý request. Ngược lại, ứng dụng cấp phát chậm vẫn có thể giữ một lượng lớn object lâu dài trong cache hoặc cấu trúc dữ liệu nghiệp vụ.

## 2. Live set là gì?

Live set là lượng bộ nhớ đang được các object reachable chiếm giữ và do đó không thể thu hồi tại thời điểm xem xét. Object vẫn được tham chiếu trực tiếp hoặc gián tiếp từ GC roots, chẳng hạn static field, stack của thread đang hoạt động hoặc các object reachable khác, thuộc về live set.

Live set không đồng nghĩa với toàn bộ heap đang được sử dụng trước một chu kỳ GC:

- Heap used có thể bao gồm object đã unreachable nhưng chưa được thu gom.
- Live set gồm object vẫn reachable và phải được giữ lại.
- Sau khi GC thu gom garbage, lượng heap đã dùng thường giảm về gần mức live set, cộng với phần cấp phát và biến động xảy ra trong lúc GC chạy.

Ví dụ, một service có cache giữ ổn định 5 GB object và mỗi giây tạo thêm 200 MB object tạm. Cache tạo nên phần lớn live set; object tạm làm tăng allocation rate nhưng phần lớn có thể được thu hồi sau khi xử lý xong.

Live set cao thường đến từ:

- Cache hoặc map giữ nhiều entry lâu dài.
- Object graph của session, user hoặc domain model đang hoạt động.
- Buffer pool, queue hoặc backlog giữ dữ liệu chưa xử lý.
- Dữ liệu được giữ bởi static field, listener, callback hoặc tham chiếu ngoài dự kiến.

Nếu live set tăng liên tục theo thời gian, cần điều tra khả năng giữ object quá lâu hoặc memory leak. Tăng heap có thể trì hoãn áp lực bộ nhớ nhưng không sửa được nguyên nhân giữ tham chiếu không cần thiết.

## 3. Vì sao garbage collector phân thế hệ?

Generational GC dựa trên weak generational hypothesis: trong nhiều workload, phần lớn object trở thành unreachable không lâu sau khi được tạo, trong khi chỉ một phần nhỏ tồn tại lâu dài.

Vì vậy, heap được chia thành hai thế hệ:

- **Young Generation:** nơi object mới được cấp phát. Collector thu gom vùng này thường xuyên hơn vì đây là nơi có xác suất tìm thấy nhiều object đã chết cao.
- **Old Generation:** chứa object đã sống qua đủ số chu kỳ và được xem là có vòng đời dài hơn. Collector thu gom vùng này ít thường xuyên hơn.

~~~text
Object mới được cấp phát
          |
          v
     Young Generation
          |
          +---- Object đã unreachable
          |             |
          |             v
          |        Thu hồi bộ nhớ
          |
          +---- Object còn reachable qua nhiều chu kỳ
                        |
                        v
                  Old Generation
                        |
                        v
             Thu gom theo chu kỳ phù hợp
~~~

Lợi ích chính là không phải xử lý toàn bộ object sống lâu mỗi khi cần thu gom lượng lớn object tạm. Young Generation được thu gom thường xuyên; Old Generation vẫn được theo dõi và thu gom khi cần, nhưng không phải chịu cùng tần suất như vùng chứa object mới.

Phân thế hệ không có nghĩa object trong Old Generation sẽ không bao giờ được thu gom. Nếu object cũ trở thành unreachable, nó vẫn có thể được thu hồi trong chu kỳ thu gom Old Generation.

## 4. Generational ZGC áp dụng ý tưởng này như thế nào?

ZGC vốn được thiết kế cho độ trễ thấp và thực hiện phần lớn công việc GC đồng thời với ứng dụng. Generational ZGC bổ sung việc phân loại object theo thế hệ để tập trung công việc thường xuyên vào object mới, vốn có xác suất chết sớm cao hơn.

Ở mức khái niệm:

1. Object mới được cấp phát vào Young Generation.
2. Các chu kỳ young collection thường xuyên xác định object nào không còn reachable để thu hồi.
3. Object còn sống qua đủ thời gian/chu kỳ được chuyển sang Old Generation.
4. Old Generation được thu gom với tần suất thấp hơn, phù hợp với đặc điểm của object sống lâu.

Generational ZGC vẫn là ZGC: nó dùng cơ chế quản lý heap và thực hiện phần lớn công việc đồng thời, hướng đến pause time ngắn. Việc phân thế hệ bổ sung thông tin về tuổi object để GC tránh phải xử lý thường xuyên những object đã sống lâu khi mục tiêu chính là thu hồi garbage mới tạo.

Không nên hình dung Young/Old của ZGC như một bản sao nguyên xi của bố cục Eden, Survivor và Tenured trong một số collector khác. ZGC quản lý heap theo page và tự điều chỉnh thế hệ theo workload; ứng dụng không cần tự quản lý vùng Eden hoặc Survivor.

## 5. Allocation rate và live set tác động cùng nhau

Để chọn heap phù hợp, không thể chỉ nhìn một trong hai đại lượng:

| Allocation rate | Live set | Đặc điểm workload | Điều cần chú ý |
|---|---|---|---|
| Cao | Thấp | Tạo nhiều object tạm, phần lớn chết trẻ | Young collection cần theo kịp tốc độ cấp phát; generational collection có thể thu hồi hiệu quả |
| Thấp | Cao | Giữ cache hoặc dữ liệu nghiệp vụ lâu dài | Heap cần đủ chỗ cho live set dù allocation không nhiều |
| Cao | Cao | Vừa tạo nhiều object mới vừa giữ nhiều dữ liệu lâu dài | Cần heap lớn hơn, đủ CPU cho GC và theo dõi tốc độ object được promote |
| Thấp | Thấp | Ít dữ liệu và ít cấp phát | Áp lực GC thường thấp; cần đo trước khi chọn collector chỉ vì pause time |

Hai ứng dụng có cùng heap occupancy vẫn có thể có hành vi GC khác nhau. Một ứng dụng có heap used cao do nhiều garbage đang chờ thu gom có thể giải phóng được nhiều bộ nhớ. Ứng dụng khác có heap used tương tự nhưng phần lớn là live set thì GC có ít bộ nhớ để thu hồi hơn.

### Ví dụ: allocation rate cao nhưng live set thấp

Một API xử lý 20.000 request mỗi giây. Mỗi request tạo khoảng 12 KB object tạm, tương đương allocation rate xấp xỉ 234 MB/s. Phần lớn object chỉ tồn tại trong thời gian xử lý request; sau khi trả response, chúng không còn reachable.

Đây là workload có nhiều garbage ngắn hạn. Generational ZGC có thể tập trung các chu kỳ young collection vào nhóm object này thay vì thường xuyên làm cùng một lượng công việc trên toàn bộ object sống lâu.

### Ví dụ: allocation rate thấp nhưng live set cao

Một service khởi tạo cache 10 GB và chỉ cập nhật một lượng nhỏ entry mỗi giây. Allocation rate có thể thấp, nhưng live set vẫn lớn vì cache cần được giữ trong bộ nhớ.

Generational collection không thể thu hồi cache khi các entry vẫn reachable. Heap phải có đủ dung lượng cho live set và phần headroom cần thiết; nếu live set quá lớn, cần xem lại chính sách cache, giới hạn dữ liệu hoặc cấu hình bộ nhớ.

## 6. Vì sao ZGC cần headroom khi chạy đồng thời?

ZGC thực hiện phần lớn công việc thu gom trong khi ứng dụng tiếp tục chạy và tiếp tục cấp phát object. Vì vậy, heap phải có đủ dung lượng để:

1. Chứa live set mà ứng dụng cần giữ.
2. Phục vụ các allocation mới trong lúc chu kỳ GC đang diễn ra.
3. Hấp thụ các đợt allocation tăng đột biến và biến động trong quá trình thu gom.

Một cách ước lượng sơ bộ phần headroom cho thời gian GC cần để tạo lại vùng nhớ có thể sử dụng:

\[
\text{Headroom tham khảo} \approx
\text{Allocation rate} \times
\text{Thời gian cần để thu hồi bộ nhớ}
\]

Ví dụ, nếu allocation rate khoảng 250 MB/s và cần khoảng 1,5 giây trước khi lượng bộ nhớ có thể sử dụng được thu hồi, ứng dụng có thể cấp phát thêm khoảng 375 MB trong khoảng đó. Đây chỉ là phép ước lượng để hiểu áp lực bộ nhớ, không phải công thức đặt Xmx: thời điểm thu hồi thực tế, allocation burst, live set, fragmentation và hoạt động đồng thời của GC đều ảnh hưởng đến nhu cầu headroom.

Nếu allocation rate duy trì cao hơn khả năng GC thu hồi trong thời gian dài, heap occupancy có xu hướng tăng. Khi không còn đủ vùng nhớ để đáp ứng allocation, ứng dụng có thể gặp allocation stall, tức thread phải chờ GC làm cho bộ nhớ có thể sử dụng trở lại. Generational collection giúp phân bổ công việc hiệu quả hơn, nhưng không thể làm cho bộ nhớ hoặc CPU trở nên vô hạn.

## 7. Khi object sống lâu hơn dự kiến

Generational GC có lợi nhất khi phần lớn object chết trong Young Generation. Nếu tỷ lệ object sống qua nhiều chu kỳ cao, nhiều object sẽ được promote sang Old Generation.

Các dấu hiệu cần điều tra:

- Live set tăng theo thời gian dù lưu lượng request không tăng tương ứng.
- Object tạm bị giữ bởi cache, queue hoặc collection không có giới hạn.
- Nhiều object được promote vì vòng đời thực tế dài hơn dự kiến.
- Old Generation tăng nhanh và cần thu gom thường xuyên hơn.
- GC dùng nhiều CPU nhưng lượng bộ nhớ thu hồi được thấp.

Khi đó, hãy xem object nào đang được giữ lại và vì sao. Tăng heap có thể tạo thêm thời gian hoạt động, nhưng nếu ứng dụng giữ dữ liệu không cần thiết thì live set vẫn tiếp tục tăng.

## 8. Đo allocation rate, live set và GC pressure

Không nên chọn cấu hình chỉ từ một lần chụp heap hoặc một con số heap used. Hãy quan sát workload trong cả giai đoạn bình thường, cao điểm và sau khi tải giảm.

Các dữ liệu nên thu thập:

| Dữ liệu | Điều cần biết | Nguồn quan sát |
|---|---|---|
| Allocation rate trung bình và peak | Ứng dụng cấp phát bao nhiêu byte mỗi giây và có burst hay không | Java Flight Recorder, allocation profiling |
| Live set sau GC | Bao nhiêu bộ nhớ vẫn được object reachable giữ lại | GC log và phân tích heap/JFR phù hợp |
| Heap occupancy và headroom | Còn bao nhiêu dung lượng để phục vụ allocation trong lúc GC chạy | GC log, JVM metrics |
| Young/Old generation behavior | Tần suất collection và xu hướng object sống lâu/promote | ZGC GC log và JFR |
| Allocation stall | Ứng dụng có phải chờ GC để cấp phát hay không | GC log, JFR và latency metrics |
| CPU của GC | Công việc concurrent GC chiếm bao nhiêu tài nguyên CPU | JFR, process/container metrics |

Có thể bật GC logging để thu thập dữ liệu:

~~~shell
java -XX:+UseZGC -Xmx8g -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Xmx8g trong ví dụ chỉ là giá trị minh họa, cần thay bằng giới hạn phù hợp với workload và giới hạn bộ nhớ của môi trường chạy. GC log giúp quan sát chu kỳ, heap usage, allocation stall và thống kê ZGC; JFR bổ sung góc nhìn về allocation theo ứng dụng và hoạt động GC.

Khi đọc dữ liệu:

- So sánh allocation rate trung bình với peak; các đợt burst ngắn có thể gây áp lực dù trung bình thấp.
- Quan sát live set sau các chu kỳ thu gom, không dùng heap used trước GC làm đại diện cho live set.
- Theo dõi xu hướng Old Generation và tỷ lệ object sống sót qua nhiều chu kỳ.
- Ghép GC metrics với request rate, latency, CPU và giới hạn memory của container.
- Chạy workload đại diện đủ lâu để thấy cả cache warm-up, tải cao và giai đoạn giảm tải.

## 9. Điều chỉnh heap theo live set và allocation rate

Với ZGC, tùy chọn quan trọng nhất để bắt đầu điều chỉnh là giới hạn heap tối đa Xmx. Oracle khuyến nghị chọn heap đủ chứa live set và có thêm headroom cho allocation trong khi GC chạy. ZGC tự thích ứng bằng cách thay đổi kích thước generation, số GC thread và ngưỡng tenuring theo workload.

Có thể đặt soft limit bằng XX:SoftMaxHeapSize:

~~~shell
java -XX:+UseZGC -Xmx8g -XX:SoftMaxHeapSize=7g -jar app.jar
~~~

Soft max là mục tiêu mà ZGC cố gắng không vượt qua. Khi cần tránh ứng dụng bị stall vì thiếu vùng nhớ, ZGC vẫn có thể sử dụng heap vượt soft max nhưng không vượt Xmx. Vì vậy, SoftMaxHeapSize không phải hard limit.

Không nên mặc định tự đặt kích thước Young Generation hoặc Old Generation theo tỷ lệ cố định. Generational ZGC được thiết kế để tự điều chỉnh các generation; hãy bắt đầu bằng Xmx phù hợp, quan sát allocation rate, live set và GC behavior rồi mới cân nhắc thêm cấu hình.

## 10. Phân biệt cấu hình Java 21 và JDK hiện hành

Generational ZGC được đưa vào Java 21 qua JEP 439. Cách bật chế độ này thay đổi theo các bản JDK:

| Phiên bản JDK | Trạng thái Generational ZGC | Cách sử dụng |
|---|---|---|
| Java 21 | Có thể chọn generational mode; chế độ này chưa phải mặc định | Dùng -XX:+UseZGC -XX:+ZGenerational |
| JDK 23 | Generational mode trở thành mặc định; non-generational mode bị deprecated | Dùng -XX:+UseZGC; không cần bật cờ generational |
| JDK 24 trở lên | Chỉ còn generational mode; non-generational mode đã bị loại bỏ | Dùng -XX:+UseZGC; không truyền -XX:+ZGenerational |

Ví dụ Java 21 ở bảng là hướng dẫn theo đúng phiên bản. Với JDK hiện hành từ 24 trở lên, chỉ cần chọn ZGC; tùy chọn ZGenerational đã bị loại bỏ nên không đưa nó vào cấu hình mới.

## 11. Khi nào lý do phân thế hệ tạo khác biệt rõ nhất?

Generational ZGC có lợi thế rõ khi ứng dụng có allocation rate đáng kể và phần lớn object mới có vòng đời ngắn. Collector có thể thường xuyên tập trung vào Young Generation để thu hồi lượng lớn object tạm, trong khi object sống lâu được theo dõi trong Old Generation với tần suất phù hợp hơn.

Lợi ích có thể ít rõ hơn khi:

- Workload cấp phát rất ít object.
- Phần lớn object sống lâu và nhanh chóng trở thành live set.
- Ứng dụng bị giới hạn bởi CPU hoặc I/O thay vì GC.
- Live set chiếm gần hết heap, không còn đủ headroom cho concurrent collection.

Phân thế hệ là một tối ưu hóa dựa trên đặc điểm vòng đời object, không phải bảo đảm mọi workload đều nhanh hơn. Cần đánh giá bằng cùng workload, cùng giới hạn CPU/bộ nhớ và các chỉ số latency, throughput, allocation stall, GC CPU trước và sau khi thay đổi.

## 12. Checklist đánh giá workload

- [ ] Đo allocation rate trung bình, peak và các đợt burst.
- [ ] Xác định live set sau GC và xu hướng tăng theo thời gian.
- [ ] Phân biệt object tạm với object được giữ bởi cache, queue hoặc session.
- [ ] Theo dõi tỷ lệ object sống qua nhiều chu kỳ và xu hướng promote sang Old Generation.
- [ ] Bảo đảm heap có headroom để phục vụ allocation trong khi GC chạy.
- [ ] Quan sát allocation stall, GC CPU, request latency và throughput cùng lúc.
- [ ] Dùng Xmx làm giới hạn heap chính; cân nhắc SoftMaxHeapSize như soft limit.
- [ ] Để ZGC tự điều chỉnh kích thước generation trước khi thử tinh chỉnh sâu.
- [ ] Dùng đúng cờ theo JDK: Java 21 cần -XX:+ZGenerational; JDK 24+ chỉ cần -XX:+UseZGC.
- [ ] Đánh giá bằng tải đại diện và kiểm tra cả giai đoạn cao điểm lẫn lúc tải giảm.

Allocation rate cho biết tốc độ ứng dụng tiêu thụ heap; live set cho biết lượng bộ nhớ không thể thu hồi vì object vẫn reachable. Generational ZGC tận dụng sự khác biệt về thời gian sống của object để thu gom Young Generation thường xuyên và Old Generation ít thường xuyên hơn. Khi hiểu cả hai đại lượng, có thể giải thích đúng vì sao workload cần headroom, vì sao live set lớn làm tăng nhu cầu heap và vì sao phân thế hệ đặc biệt hữu ích với ứng dụng tạo nhiều object ngắn hạn.

## Tài liệu tham khảo

- [Oracle Java 21 — Significant Changes in JDK 21: Generational ZGC](https://docs.oracle.com/en/java/javase/21/migrate/significant-changes-jdk-release.html)
- [Oracle Java SE 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html)
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [JEP 490 — ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490)
- [Oracle Java 24 — Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
