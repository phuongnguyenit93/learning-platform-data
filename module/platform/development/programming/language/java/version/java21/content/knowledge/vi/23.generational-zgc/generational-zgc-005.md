# Xác minh collector thực tế bằng startup log và GC log

Khi bật Generational ZGC, cần xác minh JVM đã khởi tạo đúng collector và đúng chế độ generational. Chỉ nhìn thấy cờ cấu hình trong file deploy hoặc dòng `Using The Z Garbage Collector` chưa đủ để kết luận cả hai điều đó: dòng startup này xác nhận ZGC được chọn, nhưng không phân biệt chế độ generational với non-generational trên Java 21.

Với Java 21, cấu hình rõ ràng để bật Generational ZGC là `-XX:+UseZGC -XX:+ZGenerational`. Sau khi khởi động, kiểm tra startup log, giá trị flags thực tế của tiến trình và các GC events. GC log có `Minor Collection` và `Major Collection` là dấu hiệu runtime đang thực hiện thu gom theo hai thế hệ.

## 1. Xác định đúng chế độ theo phiên bản JDK

Trong Java 21, ZGC có hai chế độ. `-XX:+UseZGC` chọn ZGC; để bật Generational ZGC phải thêm `-XX:+ZGenerational`:

```shell
java -XX:+UseZGC -XX:+ZGenerational -jar application.jar
```

Nếu chạy Java 21 chỉ với `-XX:+UseZGC`, JVM dùng ZGC non-generational. Vì vậy, không thể chỉ kiểm tra `UseZGC=true` rồi kết luận đang dùng Generational ZGC.

| Runtime | Cách hiểu cấu hình ZGC |
| --- | --- |
| JDK 21 | Dùng `-XX:+UseZGC -XX:+ZGenerational` để bật Generational ZGC. Chỉ `-XX:+UseZGC` là chế độ non-generational. |
| JDK 23 | Generational ZGC trở thành mặc định khi bật ZGC; chế độ non-generational bị deprecated. |
| JDK 24 trở lên | ZGC chỉ còn chế độ generational; cờ `ZGenerational` đã bị loại bỏ. Dùng `-XX:+UseZGC` và không truyền cờ cũ. |

Đây là khác biệt theo phiên bản runtime, không phải khác biệt giữa các cấu hình ứng dụng. Khi điều tra môi trường, luôn xác định chính xác JDK mà tiến trình đang chạy; `java` trong terminal có thể không phải binary được service, container hoặc launcher sử dụng.

## 2. Bật startup log và GC log

Trong Java 21, GC logging dùng Unified JVM Logging. Dùng `-Xlog:gc*` để ghi thông tin GC, gồm thông tin khởi tạo và các sự kiện thu gom:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc* -jar application.jar
```

Để lưu log ra file và xoay vòng file theo kích thước:

```shell
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar application.jar
```

Ví dụ này ghi log vào `gc.log`, kèm thời gian thực, uptime, level và tags; giữ tối đa năm file luân phiên với kích thước mục tiêu khoảng 20 MB mỗi file. Thư mục đích phải tồn tại và tài khoản chạy JVM phải có quyền ghi.

Nếu cần chi tiết hơn để điều tra một vấn đề cụ thể, có thể tăng level:

```shell
-Xlog:gc*=debug,safepoint=info:file=gc-debug.log:time,uptime,level,tags:filecount=5,filesize=20M
```

Không nên bật mức `trace` liên tục ở production nếu chưa đánh giá lượng log, I/O và dung lượng lưu trữ. Hãy bắt đầu với `-Xlog:gc*`, sau đó tăng mức chi tiết trong khoảng thời gian cần điều tra.

## 3. Đọc startup banner: xác nhận ZGC đã được chọn

Khi ZGC khởi tạo thành công, log thường có dòng tương tự:

```text
[0.007s][info][gc] Using The Z Garbage Collector
```

Dòng này cho biết JVM đã chọn ZGC. Nếu startup log cho thấy collector khác, hoặc JVM dừng vì `Unrecognized VM option`, cần kiểm tra lại runtime và JVM arguments.

Tuy nhiên, banner không ghi rõ Generational hay non-generational. Trong Java 21, cả hai chế độ đều có thể in cùng dòng `Using The Z Garbage Collector`. Vì vậy, hãy dùng banner để xác nhận collector, sau đó xác minh `ZGenerational` và quan sát GC events.

## 4. Xác minh giá trị flags đang có hiệu lực

### Kiểm tra lúc khởi động

Có thể yêu cầu JVM in giá trị cuối cùng của các flags:

```shell
java -XX:+UseZGC -XX:+ZGenerational -XX:+PrintFlagsFinal -version
```

Trong output, tìm `UseZGC` và `ZGenerational`. Với tiến trình Java 21 đang dùng Generational ZGC, giá trị cuối cùng của cả hai phải là `true`. Phần origin của flag cũng hữu ích để biết giá trị đến từ command line hay nguồn khác; chi tiết format có thể khác giữa các bản JDK.

### Kiểm tra một tiến trình đang chạy

Nếu service đã chạy, dùng `jcmd` đi kèm JDK tương ứng:

```shell
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
```

- `VM.version` xác nhận phiên bản JVM của đúng process.
- `VM.command_line` cho biết lệnh và đối số khởi chạy.
- `VM.flags -all` cho biết các giá trị flags hiện tại; tìm `UseZGC` và `ZGenerational`.

Với Java 21, muốn xác nhận Generational ZGC thì cần thấy `UseZGC = true` và `ZGenerational = true`. Nếu chỉ thấy `UseZGC = true` còn `ZGenerational = false`, tiến trình đang chạy ZGC non-generational.

Trên Linux/macOS có thể lọc output bằng `grep`; trên Windows có thể dùng `findstr`. Ví dụ:

```shell
jcmd <pid> VM.flags -all | grep -E 'UseZGC|ZGenerational'
```

```powershell
jcmd <pid> VM.flags -all | findstr /I "UseZGC ZGenerational"
```

`VM.command_line` giúp tìm cấu hình được truyền lúc khởi chạy; `VM.flags -all` mới là nơi kiểm tra giá trị flag cuối cùng. Không dùng riêng file cấu hình hoặc biến môi trường làm bằng chứng runtime đã áp dụng cấu hình đó.

## 5. Nhận diện Generational ZGC qua GC events

Sau startup, cần để ứng dụng chạy đủ workload để GC có cơ hội thực hiện collection. Trong log của Generational ZGC, các sự kiện thường được ghi rõ theo loại collection:

```text
[0.007s][info][gc] Using The Z Garbage Collector
[0.255s][info][gc] GC(0) Major Collection (Warmup)
[0.381s][info][gc] GC(0) Major Collection (Warmup) 26M(10%)->106M(41%) 0.126s
[0.512s][info][gc] GC(1) Minor Collection (Allocation Rate)
[0.517s][info][gc] GC(1) Minor Collection (Allocation Rate) 162M(63%)->10M(4%) 0.005s
```

Đây là output minh họa; thời điểm, GC ID, nguyên nhân và số liệu thay đổi theo workload, JDK update và môi trường. Cần đọc tên sự kiện:

- `Minor Collection` thu gom young generation. Đây là collection thường xuyên để thu hồi các object ngắn hạn.
- `Major Collection` xử lý cả young và old generation. Nó không đồng nghĩa với một stop-the-world full GC kéo dài như cách gọi ở một số collector khác; phần lớn công việc của ZGC diễn ra đồng thời với ứng dụng.
- `Allocation Rate`, `Warmup` hoặc các nguyên nhân khác giải thích vì sao collection được khởi động. Không nên giả định mọi ứng dụng sẽ có cùng chuỗi nguyên nhân.

Sự xuất hiện của `Minor Collection` cùng `Major Collection` là bằng chứng GC log đang thể hiện hai thế hệ. Nếu log chỉ có startup banner mà chưa có collection event, điều đó chưa đủ để kết luận chế độ generational chưa hoạt động: workload có thể chưa tạo đủ áp lực cấp phát để GC chạy.

## 6. Dùng log chi tiết để hiểu từng thế hệ

Khi cần phân tích sâu, `-Xlog:gc*` cung cấp các tag chi tiết hơn, ví dụ `gc,phases`, `gc,heap` và `gc,init`. Có thể tăng level cho toàn bộ nhóm GC:

```shell
-Xlog:gc*=debug:file=gc-debug.log:uptime,level,tags:filecount=5,filesize=20M
```

Trong log Generational ZGC, các phase có thể được gắn với young hoặc old generation. Hãy xem tag và nội dung phase cùng GC ID để biết phase thuộc collection nào. Đừng chỉ tìm từ `Young` hoặc `Old` trong một dòng rời rạc; đối chiếu GC ID, loại collection và các dòng bắt đầu/kết thúc tương ứng.

Các log phase rất hữu ích khi cần hiểu collection nào đang chiếm thời gian, nhưng format log là chi tiết triển khai và có thể thay đổi giữa các JDK update. Công cụ phân tích log nên chịu được thay đổi format và không nên phụ thuộc vào một chuỗi cố định duy nhất.

## 7. Kiểm tra đúng JVM trong service, container và Kubernetes

Một lỗi phổ biến là kiểm tra `java -version` trong terminal của người vận hành rồi suy ra service dùng cùng runtime. Service có thể chạy từ một JDK khác, nhận flags từ script hoặc cấu hình môi trường, hoặc chạy trong container riêng.

Quy trình thực tế:

1. Xác định PID của process Java trong đúng host hoặc container.
2. Chạy `jcmd <pid> VM.version` để xác nhận JDK thực tế.
3. Chạy `jcmd <pid> VM.command_line` để xem arguments của process.
4. Chạy `jcmd <pid> VM.flags -all` để xác minh giá trị cuối cùng của `UseZGC` và `ZGenerational`.
5. Đọc GC log của đúng process, kiểm tra startup banner và collection events.

Với container, chạy `jcmd` bên trong cùng container hoặc môi trường process namespace có thể attach được. Nếu Java chạy ở PID 1 trong container, PID đó có thể là `1` bên trong container nhưng là PID khác trên host. Công cụ attach cũng cần quyền truy cập process và user phù hợp.

Nếu không thể attach bằng `jcmd`, hãy bật `-Xlog:gc*` ngay từ cấu hình khởi động của service, sau đó restart theo quy trình triển khai và thu log từ đúng instance. Kiểm tra cả `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, script entrypoint và cấu hình JVM của application server nếu có.

## 8. Những kết luận không nên rút ra từ GC log

| Quan sát | Kết luận có thể rút ra | Kết luận chưa thể rút ra |
| --- | --- | --- |
| `Using The Z Garbage Collector` | JVM đã chọn ZGC. | Chưa chứng minh đó là Generational ZGC. |
| `UseZGC = true` | Flag chọn ZGC đang bật. | Trên Java 21, chưa chứng minh `ZGenerational` đang bật. |
| `UseZGC = true`, `ZGenerational = true` trên Java 21 | Các flags runtime xác nhận đã chọn chế độ Generational ZGC. | Chưa nói lên GC có đạt mục tiêu latency/throughput hay không. |
| Có `Minor Collection` và `Major Collection` | Log đang thể hiện collection của young và cả hai thế hệ. | Chưa chứng minh cấu hình heap hoặc hiệu năng phù hợp workload. |
| Chưa thấy `Minor Collection` | Chưa có event đó trong khoảng log đang quan sát. | Không chứng minh Generational ZGC không hoạt động; workload có thể chưa kích hoạt GC. |
| Không thấy startup banner trong file | File đó không chứa dòng startup tương ứng. | Không chứng minh ZGC không được chọn; có thể log đang đi sang stdout/stderr hoặc file khác. |

GC log là công cụ xác minh collector và phân tích hoạt động. Để đánh giá hiệu năng, cần xem thêm allocation rate, live set, heap headroom, CPU, thời gian pause, thời gian collection và latency của ứng dụng dưới workload đại diện.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có `Using The Z Garbage Collector` nhưng không thấy `Minor Collection` | Banner chỉ xác nhận ZGC; có thể thiếu `ZGenerational`, hoặc workload chưa kích hoạt GC. | Kiểm tra `ZGenerational` bằng `jcmd`; tiếp tục quan sát dưới workload phù hợp. |
| `UseZGC=true`, `ZGenerational=false` trên Java 21 | Chỉ bật collector ZGC. | Thêm `-XX:+ZGenerational` vào JVM arguments và khởi động lại. |
| Log không có startup banner | Logging được cấu hình muộn hoặc output nằm ở nơi khác. | Đặt `-Xlog:gc*` ngay từ startup và kiểm tra stdout, stderr, file log. |
| Service chạy G1 dù cấu hình mong muốn ZGC | Service không nhận JVM arguments hoặc dùng runtime khác. | Kiểm tra `VM.version`, `VM.command_line`, `VM.flags -all` của đúng PID. |
| `Unrecognized VM option: ZGenerational` | Runtime có thể cũ hơn Java 21 hoặc mới hơn Java 23 nơi flag đã bị loại bỏ ở JDK 24. | Xác định JDK thực tế; dùng đúng flags theo phiên bản. |
| GC log bị thiếu đoạn đầu | File bị xoay vòng, bị ghi đè hoặc chỉ thu thập từ sau startup. | Kiểm tra log rotation và giữ file chứa startup của từng process. |
| Không thể chạy `jcmd` | Sai PID/container, khác user hoặc attach bị giới hạn. | Chạy trong đúng process namespace với quyền phù hợp; bật GC log từ startup nếu không attach được. |
| Có Minor/Major events nhưng ứng dụng vẫn chậm | Collector đang hoạt động không có nghĩa workload đã được tối ưu. | Phân tích pause, concurrent cycle, CPU, allocation, live set và latency ứng dụng. |

## 10. Checklist xác minh

1. Xác nhận đúng JDK và đúng process đang chạy.
2. Với Java 21, kiểm tra command line có `-XX:+UseZGC -XX:+ZGenerational`.
3. Bật Unified GC logging bằng `-Xlog:gc*` từ lúc JVM khởi động.
4. Kiểm tra startup banner `Using The Z Garbage Collector`.
5. Dùng `jcmd <pid> VM.flags -all` hoặc `-XX:+PrintFlagsFinal` để xác nhận giá trị cuối cùng của hai flags.
6. Quan sát workload đủ lâu để có collection events; tìm `Minor Collection` và `Major Collection`.
7. Giữ GC log có rotation và gắn PID/thời gian nếu chạy nhiều instance.
8. Đánh giá hiệu năng bằng metrics của ứng dụng, không chỉ dựa vào tên collector.

## 11. Tài liệu tham khảo chính thức

- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): thiết kế Generational ZGC được đưa vào JDK 21.
- [Java SE 21 — Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html): cách bật ZGC và Generational ZGC trong Java 21.
- [Java SE 21 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html): hành vi và cấu hình ZGC.
- [Java SE 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): Unified Logging `-Xlog`, tag, level, output và log rotation.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): gửi diagnostic command đến JVM đang chạy.
- [Oracle JDK 21 Release Notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): Generational ZGC và flags kích hoạt trong JDK 21.
- [Java SE 24 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): từ JDK 24 ZGC luôn generational và flag `ZGenerational` đã bị loại bỏ.
