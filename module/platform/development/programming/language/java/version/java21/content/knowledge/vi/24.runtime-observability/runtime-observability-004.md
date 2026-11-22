# `Thread.dump_to_file` qua `jcmd` và lựa chọn định dạng dump

## 1. `Thread.dump_to_file` dùng để làm gì?

Trong Java 21, `jcmd` cung cấp diagnostic command `Thread.dump_to_file` để ghi thread dump ra một file. Điểm quan trọng của lệnh này là nó liệt kê cả **platform thread và virtual thread**, giúp điều tra ứng dụng sử dụng virtual thread với số lượng lớn.

Thread dump chứa thông tin về các thread và stack trace của chúng tại thời điểm thu thập. Khi ứng dụng bị treo, phản hồi chậm hoặc có quá nhiều tác vụ đang chờ, dump giúp trả lời các câu hỏi như:

- Thread nào đang chạy và đang ở stack frame nào?
- Virtual thread nào đang chờ I/O, lock hoặc một synchronizer?
- Có nhiều tác vụ cùng dừng ở một đoạn code hoặc một lời gọi thư viện không?
- Các thread có đang chờ tại cùng một điểm nghẽn hay phân tán ở nhiều tầng xử lý?

Lệnh này đặc biệt hữu ích khi cần quan sát virtual thread. Một thread dump truyền thống không cung cấp cùng phạm vi quan sát cho số lượng lớn virtual thread. Tuy nhiên, dump từ `Thread.dump_to_file` có mục tiêu và tập thông tin riêng; không nên xem nó là bản thay thế đầy đủ cho mọi loại thread dump truyền thống.

## 2. Xác định tiến trình Java cần lấy dump

Trước tiên, tìm PID của JVM đang gặp vấn đề:

```bash
jcmd -l
```

Lệnh liệt kê các tiến trình JVM mà `jcmd` có thể phát hiện, kèm main class và một phần thông tin khởi chạy. Nếu đã biết PID, có thể yêu cầu JVM hiển thị các diagnostic command mà nó hỗ trợ:

```bash
jcmd 12345 help Thread.dump_to_file
```

Thay `12345` bằng PID thực tế. Việc hỏi help trên chính JVM đích giúp xác nhận command và các tùy chọn mà runtime đó chấp nhận. Đây là bước hữu ích khi làm việc với nhiều bản phân phối JDK hoặc môi trường có bản cập nhật khác nhau.

`jcmd` cần chạy trên cùng máy với JVM đích và dưới cùng effective user/group đã dùng để khởi chạy JVM. Nếu không tìm thấy tiến trình hoặc bị từ chối attach, hãy kiểm tra PID, user, quyền truy cập và môi trường chạy trước khi kết luận command không được hỗ trợ.

Trong container, PID hiển thị từ host có thể khác PID bên trong container. `jcmd -l` cũng không liệt kê JVM đang chạy trong một Docker process riêng biệt ở một số cấu hình. Khi đó, hãy chạy `jcmd` trong đúng container hoặc dùng PID namespace mà tiến trình đích nhìn thấy. Đường dẫn file dump cũng phải tồn tại và có quyền ghi trong filesystem mà JVM đích sử dụng.

## 3. Tạo dump dạng text

Để tạo dump dễ đọc trực tiếp trong terminal hoặc editor, chọn định dạng `text`:

```bash
jcmd 12345 Thread.dump_to_file -format=text /var/tmp/app-threads.txt
```

Trong Java 21, giá trị định dạng được tài liệu hóa là `text` hoặc `json`. Dạng `text` phù hợp khi người vận hành cần mở file, tìm kiếm stack trace bằng `grep`, so sánh thủ công hoặc đính kèm vào báo cáo sự cố.

Ví dụ quy trình cơ bản:

1. Xác định đúng PID bằng `jcmd -l` hoặc công cụ quản lý tiến trình.
2. Chọn một đường dẫn tuyệt đối mà user chạy JVM có quyền ghi.
3. Chạy `Thread.dump_to_file -format=text`.
4. Xác nhận file được tạo và có nội dung.
5. Lưu timestamp, PID và tình trạng ứng dụng cùng với file để tiện đối chiếu.

Không nên dùng một đường dẫn tương đối nếu chưa xác định rõ thư mục làm việc của tiến trình đích. Đường dẫn tuyệt đối giúp tránh nhầm file được tạo ở host, container hoặc working directory khác.

## 4. Tạo dump dạng JSON

Khi cần phân tích bằng công cụ hoặc xử lý tự động, chọn JSON:

```bash
jcmd 12345 Thread.dump_to_file -format=json /var/tmp/app-threads.json
```

JSON phù hợp để đưa vào công cụ phân tích, parser hoặc pipeline chẩn đoán. Ví dụ, hệ thống nội bộ có thể đọc file JSON để nhóm thread theo trạng thái, tên, stack frame hoặc các thuộc tính được phiên bản JDK đó xuất ra.

Định dạng JSON hữu ích khi:

- Cần phân tích hàng nghìn hoặc hàng chục nghìn virtual thread.
- Muốn lọc hoặc nhóm thread tự động thay vì đọc thủ công toàn bộ file.
- Muốn tích hợp dữ liệu dump vào dashboard hoặc hệ thống điều tra sự cố.
- Cần giữ cấu trúc dữ liệu để xử lý lặp lại bằng script.

JSON không tự động làm cho dump có nhiều thông tin runtime hơn text. Hai định dạng phục vụ cách đọc và xử lý khác nhau; chúng không làm thay đổi phạm vi thông tin mà command thu thập.

Khi viết parser, hãy kiểm tra dữ liệu theo đúng JDK đang chạy và xử lý trường hợp field không xuất hiện. Không nên giả định cấu trúc JSON nội bộ sẽ giống hệt giữa mọi phiên bản JDK hoặc dùng parser phụ thuộc vào field chưa được tài liệu hóa.

## 5. So sánh text và JSON

| Tiêu chí | `-format=text` | `-format=json` |
|---|---|---|
| Mục tiêu chính | Con người đọc trực tiếp | Công cụ hoặc chương trình phân tích |
| Mở bằng editor | Dễ đọc ngay | Có thể cần formatter hoặc JSON viewer |
| Tìm stack trace | Dùng editor, `grep`, `findstr` | Dùng parser, `jq` hoặc code |
| Nhóm và thống kê hàng loạt thread | Có thể làm nhưng khó xử lý cấu trúc | Thuận tiện hơn cho xử lý có cấu trúc |
| Tích hợp tự động | Cần phân tích văn bản | Phù hợp hơn với pipeline dữ liệu |
| Thông tin runtime | Theo nội dung dump của command | Cùng phạm vi dữ liệu, biểu diễn dưới dạng JSON |

Quy tắc chọn nhanh:

- Chọn **text** khi người trực vận hành cần xem ngay stack trace và chia sẻ với người đang xử lý sự cố.
- Chọn **JSON** khi cần lọc, nhóm, so sánh hoặc tích hợp dump vào công cụ.
- Nếu chưa biết công cụ tiếp nhận hỗ trợ gì, kiểm tra định dạng đầu vào trước khi thu thập dump production.

## 6. Tùy chọn `-overwrite`

Mặc định, không nên giả định lệnh sẽ ghi đè một file đã tồn tại. Nếu chủ động muốn ghi đè, có thể dùng `-overwrite`:

```bash
jcmd 12345 Thread.dump_to_file -overwrite -format=json /var/tmp/app-threads.json
```

Chỉ sử dụng tùy chọn này khi đã xác nhận file cũ không còn cần thiết. Khi điều tra sự cố, nên đặt tên file có PID và timestamp để giữ được nhiều snapshot và so sánh sự thay đổi theo thời gian.

Ví dụ tên file:

```text
threads-12345-2026-11-16T101500Z.txt
threads-12345-2026-11-16T101530Z.txt
threads-12345-2026-11-16T101600Z.txt
```

Các tên trên chỉ là quy ước đặt tên file. Hãy chọn định dạng thời gian và múi giờ thống nhất với log của ứng dụng để đối chiếu thuận tiện.

## 7. Phạm vi thông tin và giới hạn của dump trong Java 21

`Thread.dump_to_file` liệt kê cả platform thread và virtual thread. Đây là lợi thế khi ứng dụng tạo nhiều virtual thread và cần xem các tác vụ đang hoạt động hoặc chờ.

Tuy nhiên, tài liệu Java 21 nêu rõ dump này không bao gồm một số thông tin có trong traditional thread dump, chẳng hạn:

- Object address.
- Thông tin lock/monitor ownership như traditional dump.
- JNI statistics.
- Heap statistics.

Do đó, không dùng riêng file `Thread.dump_to_file` để kết luận deadlock do monitor hoặc xác định đầy đủ thread nào đang sở hữu một object monitor. Command này cũng không thay thế heap dump, GC log hoặc Java Flight Recorder.

Dump là dữ liệu quan sát phục vụ chẩn đoán, không phải snapshot nhất quán của toàn bộ JVM tại một thời điểm duy nhất. Việc thu thập không dừng toàn bộ ứng dụng theo kiểu stop-the-world thread dump truyền thống; trạng thái thread có thể thay đổi trong lúc command đang lấy thông tin. Khi cần hiểu diễn biến, hãy lấy nhiều dump cách nhau một khoảng thời gian và đối chiếu với timestamp, log cùng metrics.

## 8. Phân biệt `Thread.dump_to_file` với `Thread.print`

Hai command phục vụ các cách quan sát khác nhau:

| Command | Cách xuất | Khi phù hợp |
|---|---|---|
| `Thread.print` | In thread dump ra output của `jcmd` | Xem nhanh thông tin thread truyền thống và các tùy chọn mở rộng được command hỗ trợ |
| `Thread.dump_to_file` | Ghi dump vào file theo định dạng text hoặc JSON | Thu thập thread dump có cả virtual thread và lưu thành artifact để phân tích |

Ví dụ:

```bash
jcmd 12345 Thread.print
jcmd 12345 Thread.dump_to_file -format=text /var/tmp/threads.txt
jcmd 12345 Thread.dump_to_file -format=json /var/tmp/threads.json
```

Nếu cần thông tin lock/monitor chi tiết, kiểm tra khả năng của `Thread.print` và các công cụ quản lý phù hợp. Nếu cần xem toàn bộ virtual thread, dùng `Thread.dump_to_file` theo hướng dẫn Java 21. Hai command có thể bổ sung cho nhau trong cùng một lần điều tra.

## 9. Quy trình thu thập nhiều dump để tìm thread bị kẹt

Một file dump đơn lẻ chỉ cho biết trạng thái quan sát được trong lần thu thập đó. Để nhận ra thread nào bị kẹt lâu hoặc liên tục quay lại cùng stack trace, nên thu thập một chuỗi snapshot.

Ví dụ trên Linux/macOS:

```bash
jcmd 12345 Thread.dump_to_file -format=text /var/tmp/threads-1.txt
sleep 10
jcmd 12345 Thread.dump_to_file -format=text /var/tmp/threads-2.txt
sleep 10
jcmd 12345 Thread.dump_to_file -format=text /var/tmp/threads-3.txt
```

Hoặc dùng JSON nếu cần phân tích tự động:

```bash
jcmd 12345 Thread.dump_to_file -format=json /var/tmp/threads-1.json
sleep 10
jcmd 12345 Thread.dump_to_file -format=json /var/tmp/threads-2.json
```

Khi so sánh, chú ý:

1. Thread nào xuất hiện trong nhiều snapshot với stack trace gần như không đổi?
2. Có nhiều virtual thread cùng chờ tại một API, semaphore hoặc client pool không?
3. Số lượng thread ở cùng trạng thái có tăng theo thời gian không?
4. Có task mới được tạo nhưng không thấy task cũ kết thúc không?
5. Stack trace có trỏ đến lời gọi blocking, queue, lock hoặc dịch vụ ngoài không?

Không kết luận thread bị kẹt chỉ vì stack trace giống nhau ở hai snapshot. Một tác vụ có thể hợp lệ khi chờ database hoặc socket trong thời gian dài. Cần đối chiếu với request age, timeout, pool metrics và log ở tầng phụ thuộc.

## 10. Kết hợp với JFR và metrics

Thread dump cho thấy thread đang ở đâu; JFR và metrics giúp giải thích điều gì đã xảy ra trước đó hoặc vì sao thread phải chờ.

Với ứng dụng Java 21 sử dụng virtual thread, có thể ghi JFR để quan sát các event liên quan:

```bash
jcmd 12345 JFR.start name=virtual-thread-check settings=profile duration=2m filename=/var/tmp/virtual-thread-check.jfr
```

Sau khi recording kết thúc, có thể xem các event virtual thread:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed /var/tmp/virtual-thread-check.jfr
```

JFR bổ sung thông tin về vòng đời virtual thread, pinning và các sự kiện runtime. Khi điều tra request chậm, hãy kết hợp thêm:

- Request latency và tuổi của request đang chạy.
- Số lượng task đang chờ trong executor hoặc semaphore.
- Database pool: active, idle, pending và acquisition timeout.
- HTTP client: request pending, timeout, lỗi kết nối và thời gian response.
- GC pause, allocation rate và heap occupancy nếu nghi ngờ áp lực bộ nhớ.
- Distributed trace để xác định span nào đang chiếm phần lớn thời gian.

Không dùng thread dump để thay thế metrics của database, HTTP client hoặc hệ thống bên ngoài. Một virtual thread có thể đang chờ trong lời gọi JDBC, nhưng nguyên nhân thật sự là database lock wait hoặc connection pool exhaustion.

## 11. Lỗi thường gặp khi dùng `Thread.dump_to_file`

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| `jcmd -l` không thấy JVM trong container | PID namespace hoặc tiến trình nằm trong Docker process riêng | Chạy `jcmd` trong container hoặc xác định PID đúng namespace |
| Attach bị từ chối | Khác effective user/group hoặc giới hạn attach | Chạy với đúng user và kiểm tra quyền của môi trường |
| Không tạo được file | Đường dẫn không tồn tại, không có quyền ghi hoặc filesystem đầy | Dùng đường dẫn tuyệt đối có thể ghi và kiểm tra dung lượng |
| File đã tồn tại | Command không được yêu cầu ghi đè | Dùng tên file mới hoặc `-overwrite` khi thực sự cần |
| Dùng `-format=plain` trên Java 21 | Giá trị tài liệu Java 21 là `text` hoặc `json` | Dùng `-format=text` hoặc `-format=json` |
| Không thấy lock ownership trong dump | `Thread.dump_to_file` không chứa lock information như traditional dump | Thu thập thêm dump/công cụ có thông tin lock phù hợp |
| JSON parser lỗi sau khi nâng JDK | Cấu trúc dữ liệu có thể thay đổi theo phiên bản | Kiểm tra schema/format của runtime và làm parser chịu được field tùy chọn |
| Dump quá lớn | Ứng dụng có rất nhiều virtual thread | Dùng JSON và công cụ lọc; lưu file ở nơi đủ dung lượng |
| Kết luận deadlock từ một snapshot | Dump không thực hiện deadlock detection và không phải snapshot nhất quán | Đối chiếu nhiều snapshot, lock diagnostics và metrics tài nguyên |

## 12. Bảo vệ file dump

Thread dump có thể chứa tên thread, tên class, package nội bộ, đường dẫn file, URL, tên queue, thông tin request hoặc dữ liệu được nhúng trong tên tác vụ. Vì vậy:

- Lưu dump trong thư mục chỉ người vận hành cần thiết mới có quyền đọc.
- Không tự động tải dump lên ticket hoặc dịch vụ bên ngoài nếu chưa kiểm tra chính sách dữ liệu.
- Không ghi đè snapshot đang được dùng làm bằng chứng điều tra.
- Xóa hoặc lưu trữ theo thời hạn retention của hệ thống.
- Khi chia sẻ để hỗ trợ, rà soát thông tin nhạy cảm trong tên thread, stack trace và đường dẫn.

Với ứng dụng có hàng chục nghìn hoặc hàng trăm nghìn virtual thread, file dump có thể lớn. Hãy bảo đảm dung lượng đĩa trước khi thu thập, đặc biệt trong container có ephemeral storage giới hạn.

## 13. Checklist chọn định dạng và thu thập

Trước khi chạy lệnh, hãy xác định:

1. Đã xác định đúng PID của JVM Java 21 chưa?
2. `jcmd` đang chạy trên cùng máy/container và dưới đúng user/group chưa?
3. Đường dẫn output có tồn tại, có quyền ghi và đủ dung lượng không?
4. Người điều tra cần đọc trực tiếp hay cần parser/công cụ tự động?
5. Đã chọn `-format=text` hoặc `-format=json` đúng nhu cầu chưa?
6. File output đã tồn tại chưa; có cần dùng `-overwrite` không?
7. Có cần thu thập nhiều snapshot để so sánh không?
8. Có cần thêm `Thread.print`, JFR, GC log, database/HTTP metrics hoặc distributed trace không?
9. File dump có được lưu và chia sẻ theo đúng chính sách bảo mật không?

## 14. Tài liệu tham khảo chính thức

- [Java SE 21 — Virtual Threads, Viewing Virtual Threads in jcmd Thread Dumps](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): cách tạo dump `text` và `json`, phạm vi thread được liệt kê và giới hạn thông tin.
- [Java SE 21 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cách xác định PID, gửi diagnostic command, điều kiện attach và cú pháp `jcmd`.
- [Java SE 21 API — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): mô hình platform thread và virtual thread.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): thiết kế virtual thread và các công cụ hỗ trợ quan sát trong Java 21.

Trong Java 21, dùng `jcmd <pid> Thread.dump_to_file -format=text <file>` khi cần đọc stack trace trực tiếp, hoặc `-format=json` khi cần phân tích có cấu trúc. Command này liệt kê cả platform và virtual thread, nhưng không chứa đầy đủ lock, JNI hoặc heap information như traditional dump. Hãy xác định đúng tiến trình và quyền ghi file, thu thập nhiều snapshot khi cần theo dõi diễn biến, rồi kết hợp với JFR và metrics để tìm nguyên nhân thay vì kết luận chỉ từ một dump.
