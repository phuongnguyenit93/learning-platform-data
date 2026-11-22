# 10.3. Lấy thread dump có virtual thread bằng `jcmd Thread.dump_to_file` (plain và JSON)

## Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích vì sao thread dump kiểu truyền thống có thể bỏ sót virtual thread đang tạm ngừng chạy.
2. Xác định đúng tiến trình Java, tạo hai bản dump `plain` và `json` bằng `jcmd`.
3. Tìm stack trace của một virtual thread trong file, đọc cấu trúc JSON và nhận diện dấu hiệu cần điều tra tiếp.
4. Hiểu giới hạn của snapshot và xử lý các lỗi thường gặp khi thu thập dump trên máy chủ/container.

> **Phân biệt tên gọi:** `Thread.dump_to_file` ở đây là **diagnostic command của HotSpot/JVM**, được gọi qua công cụ dòng lệnh `jcmd`. Đây **không phải** phương thức `java.lang.Thread.dump_to_file()` để gọi trong mã Java.

## 1. Bối cảnh: virtual thread thay đổi cách quan sát ứng dụng

- **Platform thread** thường gắn với một thread hệ điều hành trong suốt vòng đời.
- **Virtual thread** (chính thức từ Java 21, JEP 444) được JVM lên lịch chạy trên một platform thread gọi là **carrier**. Khi gặp thao tác chờ có thể unmount (ví dụ I/O hỗ trợ hoặc `LockSupport.park`), virtual thread được tạm dừng và carrier có thể phục vụ việc khác.
- Vì vậy một ứng dụng có thể có rất nhiều virtual thread đang chờ dù số carrier/platform thread ít. Dump truyền thống như `jstack` hoặc `jcmd <PID> Thread.print` không phải cách đầy đủ để liệt kê các virtual thread đã unmount.
- `jcmd <PID> Thread.dump_to_file` được thiết kế để ghi stack của **cả platform thread lẫn virtual thread** ra file. Cách này phù hợp khi cần tìm vị trí đang đợi I/O, lock, latch, queue hay truy vết một tác vụ bị treo.

**Thread dump là ảnh chụp trạng thái tại thời điểm thu thập**, không phải lịch sử thực thi. Một frame `await`, `park` hoặc `sleep` chưa đủ chứng minh deadlock hay bug; cần liên hệ với tải thực tế và so sánh nhiều lần lấy mẫu.

### Phạm vi và điều kiện

- Dùng **JDK 21 trở lên** cho ứng dụng minh họa và cho diagnostic command này; phải có tiện ích `jcmd` từ JDK.
- `jcmd` phải chạy trên **cùng máy/không gian tiến trình có thể attach** tới JVM đích và thường cần cùng người dùng hiệu lực (effective user/group). Trong container, PID nhìn từ host có thể khác PID bên trong container.
- Tiến trình JVM phải đang chạy, hỗ trợ diagnostic command và có quyền **tạo file ở đường dẫn đích**. File dump được ghi bởi **JVM đích**, không phải bởi shell đang gõ `jcmd`.
- Tên lệnh và lựa chọn chính xác có thể kiểm tra trực tiếp bằng `jcmd <PID> help Thread.dump_to_file`.

## 2. Cú pháp của `Thread.dump_to_file`

```bash
jcmd <PID> Thread.dump_to_file [-format=plain|-format=json] [-overwrite] <duong-dan-file>
```

Ví dụ trên Linux/macOS (thay `<PID>` bằng số PID thực; đảm bảo thư mục `/tmp` ghi được bởi JVM đích):

```bash
# Plain (mặc định); hai lệnh sau có cùng ý định:
jcmd <PID> Thread.dump_to_file /tmp/vthreads-plain.txt
jcmd <PID> Thread.dump_to_file -format=plain /tmp/vthreads-plain-2.txt

# JSON cho chương trình phân tích:
jcmd <PID> Thread.dump_to_file -format=json /tmp/vthreads-json.json
```

Trên Windows, dùng đường dẫn tồn tại và cho phép JVM ghi, ví dụ:

```powershell
jcmd <PID> Thread.dump_to_file -format=plain "C:\temp\vthreads-plain.txt"
jcmd <PID> Thread.dump_to_file -format=json "C:\temp\vthreads-json.json"
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `<PID>` | Mã tiến trình JVM cần quan sát; không phải thread ID. |
| `-format=plain` | Văn bản đọc trực tiếp, là kiểu mặc định trong trợ giúp diagnostic command. |
| `-format=json` | JSON có cấu trúc để lọc bằng script/công cụ phân tích. |
| `-overwrite` | Cho phép thay thế file đã tồn tại; mặc định **không ghi đè**. Chỉ dùng khi thực sự muốn mất bản cũ. |
| `<duong-dan-file>` | Vị trí file **trong hệ thống file của tiến trình JVM đích**. |

Một số bài viết của Oracle dùng cách ghi `-format=text` để chỉ dạng văn bản. Trên HotSpot, trợ giúp trực tiếp của `Thread.dump_to_file` mô tả hai lựa chọn là **`plain` và `json`**. Để dễ kiểm chứng và đồng nhất, hãy dùng `-format=plain` hoặc bỏ hẳn `-format` cho văn bản.

Đường dẫn **tuyệt đối** giúp tránh nhầm lẫn. Nếu dùng đường dẫn tương đối, JVM giải quyết nó dựa trên thư mục làm việc của **tiến trình đích**; do đó file có thể không nằm trong thư mục terminal gọi `jcmd`.

## 3. Thực hành: tạo ba virtual thread có tên dễ tìm

Tạo file **`VirtualThreadDumpDemo.java`** với toàn bộ chương trình Java 21 sau:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class VirtualThreadDumpDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> threads = new ArrayList<>();

        for (int i = 1; i <= 3; i++) {
            Thread thread = Thread.ofVirtual()
                    .name("vt-demo-" + i)
                    .start(() -> {
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
            threads.add(thread);
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("3 virtual threads are waiting.");
        System.out.println("Press Enter to stop...");
        System.in.read();

        release.countDown();
        for (Thread thread : threads) {
            thread.join();
        }
        System.out.println("Done.");
    }
}
```

**Vì sao ví dụ này phù hợp để lấy dump?** `Thread.ofVirtual()` tạo virtual thread thật; `name("vt-demo-" + i)` đặt tên `vt-demo-1` đến `vt-demo-3`. Mỗi thread đứng ở `CountDownLatch.await()` cho đến khi main gọi `countDown()`. Main chờ người dùng nhấn Enter, nên có khoảng thời gian đủ dài để thu thập dump trong một terminal khác. `join()` đảm bảo chương trình kết thúc sau khi cả ba virtual thread hoàn thành.

### Terminal A — khởi động chương trình

```bash
javac --release 21 VirtualThreadDumpDemo.java
java VirtualThreadDumpDemo
```

Đầu ra mẫu (số PID phụ thuộc máy):

```text
PID=12345
3 virtual threads are waiting.
Press Enter to stop...
```

**Giữ nguyên terminal A và chưa nhấn Enter.** Chương trình đang chạy, các virtual thread vẫn chờ trên latch.

### Terminal B — xác định JVM và thu thập hai định dạng

```bash
jcmd -l
jcmd 12345 help Thread.dump_to_file
jcmd 12345 Thread.dump_to_file -format=plain /tmp/vthreads-demo.txt
jcmd 12345 Thread.dump_to_file -format=json /tmp/vthreads-demo.json
```

Ở đây `12345` **chỉ là PID minh họa**: thay bằng PID thực in ra ở terminal A. Hai file phải có tên khác nhau để bảo toàn cả hai kết quả. Khi `jcmd` báo tạo file thành công, kiểm tra trên **máy/container nơi JVM đích đang chạy**:

```bash
ls -lh /tmp/vthreads-demo.txt /tmp/vthreads-demo.json
grep -n "vt-demo-" /tmp/vthreads-demo.txt
```

Sau khi hoàn tất, quay lại terminal A, **nhấn Enter**. Dòng cuối dự kiến:

```text
Done.
```

Nếu bạn sử dụng Windows, thay đường dẫn `/tmp/...` bằng đường dẫn Windows như ở mục 2. Nếu JVM chạy trong Docker/Kubernetes, hãy thực hiện lệnh trong đúng container hoặc dùng cơ chế attach phù hợp, sau đó lấy file ra khỏi filesystem của container khi cần.

## 4. Cách đọc dump `plain`

Mở file bằng `less`, `grep`, trình soạn thảo hoặc công cụ tìm kiếm văn bản. Tập trung vào:

1. **Tên thread**: tìm `vt-demo-1`, `vt-demo-2`, `vt-demo-3` hoặc quy ước tên task/request của ứng dụng.
2. **Dấu hiệu virtual thread**: định dạng plain có thể thể hiện nhãn `virtual`; cách trình bày chi tiết phụ thuộc bản JDK.
3. **Stack trace**: đọc từ frame trên xuống để tìm hàm đang chờ và các hàm nghiệp vụ đã gọi tới đó. Với demo, hãy tìm `CountDownLatch.await` (có thể có thêm `LockSupport.park` hay frame nội bộ của JVM).
4. **Mẫu lặp lại**: nhiều thread cùng dừng tại một lời gọi JDBC, HTTP, queue hay latch có thể cho thấy điểm nghẽn, nhưng chưa đủ để khẳng định nguyên nhân.

Ví dụ tìm tên thread trong dump bằng công cụ Unix:

```bash
grep -n -A 15 "vt-demo-" /tmp/vthreads-demo.txt
```

`-n` thêm số dòng, `-A 15` hiện 15 dòng theo sau một kết quả khớp. Số frame cần đọc tùy trường hợp; không suy ra tình trạng deadlock chỉ từ một kết quả `grep`.

**Không nhầm:** `Thread.print -l` có ích khi cần phân tích platform thread/monitor và một số thông tin JVM truyền thống, nhưng nó không thay thế được `Thread.dump_to_file` khi mục tiêu là tìm **virtual thread chưa được mount**. Với một sự cố phức tạp, hai loại dump có thể bổ trợ cho nhau.

## 5. Cách đọc dump `JSON`

JSON thích hợp khi một JVM có hàng nghìn virtual thread, vì bạn có thể lọc dữ liệu theo thread container, tên và stack mà không phải dò thủ công toàn file.

Trong JDK 21, các trường thường thấy bao gồm:

| Đường dẫn JSON | Ý nghĩa |
| --- | --- |
| `threadDump.processId` | PID JVM tạo dump. |
| `threadDump.time` | Thời điểm thu thập. |
| `threadDump.runtimeVersion` | Phiên bản JVM tạo dump. |
| `threadDump.threadContainers[]` | Các nhóm/container chứa thread, thường có `container`, `parent`, `owner`. |
| `threadContainers[].threads[]` | Các thread thuộc từng nhóm; thường có `tid`, `name`, `stack`. |
| `threadContainers[].threadCount` | Số lượng thread được ghi nhận trong container. |

Trong các bản JDK 21–26, một số giá trị như `processId`, `tid`, `threadCount` có thể là **chuỗi chứa số**; các bản JDK mới hơn có thể dùng kiểu số và thêm trường mới. Vì thế, parser nên chịu được thay đổi theo phiên bản, thay vì coi tất cả trường/tình trạng của các bản JDK là bất biến. Đặc biệt, **đừng mặc định JSON của JDK 21 có các trường `state`, lock-owner hoặc timestamp riêng cho từng thread** như các bản JDK mới.

Dùng tiện ích `jq` (cài riêng, không phải thành phần JDK) để kiểm tra metadata:

```bash
jq '.threadDump | {processId, time, runtimeVersion}' /tmp/vthreads-demo.json
```

Liệt kê các container và số thread:

```bash
jq -r '
  .threadDump.threadContainers[]
  | [.container, .threadCount]
  | @tsv
' /tmp/vthreads-demo.json
```

Lọc ba thread đã đặt tên và lấy frame đầu tiên của stack:

```bash
jq -r '
  .threadDump.threadContainers[]
  | .container as $container
  | .threads[]?
  | select((.name // "") | startswith("vt-demo-"))
  | [$container, .tid, .name, (.stack[0] // "")]
  | @tsv
' /tmp/vthreads-demo.json
```

**Giải thích truy vấn:** duyệt từng `threadContainer`; lấy từng phần tử `threads`; chỉ giữ tên bắt đầu bằng `vt-demo-`; xuất tên container, thread ID, tên thread và frame đầu tiên dưới dạng tab-separated text. Các chuỗi/tên container và ID cụ thể thay đổi giữa những lần chạy.

Nếu không có `jq`, có thể dùng công cụ kiểm tra cú pháp JSON thông dụng, chẳng hạn:

```bash
python3 -m json.tool /tmp/vthreads-demo.json > /dev/null
```

Lệnh Python trên chỉ xác minh file là JSON hợp lệ, không phân tích nguyên nhân treo. Để điều tra nội dung sâu hơn, có thể viết parser JSON với thư viện tương ứng hoặc nạp file vào công cụ phân tích phù hợp với phiên bản JDK.

## 6. Dùng dump để điều tra một hiện tượng thực tế

Giả sử một dịch vụ xử lý request bằng virtual thread và nhiều request bị chậm:

1. **Xác nhận đúng PID và thời điểm có triệu chứng.** Ghi lại tải, endpoint liên quan và mốc thời gian; tránh lấy dump của JVM khác.
2. **Lấy ít nhất hai hoặc ba mẫu cách nhau một khoảng ngắn**, với tên file khác nhau, ví dụ `vthreads-01.json`, `vthreads-02.json`, `vthreads-03.json`. Mỗi lần là một snapshot riêng.
3. **Nhóm stack theo lời gọi nghiệp vụ**: nhiều thread dừng tại `socketRead`, `Future.get`, `CountDownLatch.await`, pool connection hay một chỗ giữ lock có thể gợi ý nơi cần kiểm tra; hãy xác định ai tạo điều kiện để chờ kết thúc.
4. **So sánh qua các mẫu**: stack luôn ở cùng một điểm có thể là chờ dài hoặc bế tắc, nhưng cũng có thể là hoạt động bình thường của worker. Kiểm tra timeout, queue depth, thời lượng I/O, dependency và log.
5. **Kết hợp bằng chứng khác** khi cần: JFR (nhất là sự kiện `jdk.VirtualThreadPinned` khi điều tra pinning), log ứng dụng, metrics, hoặc `jcmd <PID> Thread.print -l` để khảo sát phần platform thread/lock.

Không gán nhãn `BLOCKED`/`WAITING` chỉ bằng việc đoán từ một frame stack trong dump JDK 21; trạng thái đầy đủ và thông tin lock tùy phiên bản JDK. Một dump không phải phép đo CPU, profiling hay công cụ tự động tìm deadlock.

### Hai mẫu lệnh hữu ích khác

```bash
# Liệt kê các JVM mà jcmd thấy trên máy:
jcmd -l

# Dump platform-thread theo kiểu truyền thống vào file do shell ghi:
jcmd <PID> Thread.print -l > /tmp/platform-threads.txt
```

Phân biệt hai kiểu ghi file: dấu `>` ở lệnh `Thread.print` khiến **shell gọi lệnh** tạo file; còn `<duong-dan-file>` ở `Thread.dump_to_file` được gửi tới **JVM đích** để JVM tự ghi.

## 7. Giới hạn, tác động và an toàn vận hành

- **Không phải snapshot hoàn toàn đồng bộ:** các thread có thể tiến triển trong lúc dump được thu thập; thứ tự/stack không đại diện cho một “thời điểm dừng toàn JVM” tuyệt đối.
- **Dung lượng và overhead:** hàng chục nghìn đến hàng triệu virtual thread có thể tạo file rất lớn và làm công cụ lấy dump tốn thời gian/tài nguyên; tránh thu thập dồn dập trên hệ thống đang quá tải.
- **Không thay thế dump truyền thống:** ở JDK 21, định dạng này tập trung vào thông tin thread/stack, không mang đầy đủ chi tiết địa chỉ đối tượng, JNI, heap, monitor/lock hoặc tự động dò deadlock như một số công cụ khác.
- **Bảo mật:** tên lớp/phương thức, đường dẫn và các thông tin thực thi trong dump có thể nhạy cảm. Lưu file với quyền hạn phù hợp, che dữ liệu trước khi chia sẻ và xoá theo chính sách lưu giữ.
- **Phiên bản JDK:** format, trường JSON, khả năng trình bày lock và thread state thay đổi theo bản phát hành. Kiểm tra `runtimeVersion`, `jcmd <PID> help Thread.dump_to_file` và schema công cụ phân tích sau khi nâng JDK.
- **File tồn tại:** mặc định không ghi đè; tốt nhất dùng tên mới có mốc thời gian. Chỉ thêm `-overwrite` khi thực sự muốn thay thế.

## 8. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `Thread.dump_to_file` không được nhận diện | JVM đích quá cũ, không hỗ trợ lệnh hoặc dùng VM khác HotSpot | Kiểm tra `java -version` của JVM đích và `jcmd <PID> help`; dùng JDK 21+ có hỗ trợ. |
| `jcmd -l` không thấy PID | JVM ở container/PID namespace khác, chạy người dùng khác hoặc đã thoát | Xác nhận tiến trình thực và chạy `jcmd` trong môi trường có thể nhìn/attach tới JVM. |
| Attach thất bại hoặc thiếu quyền | Người dùng/nhóm không phù hợp, cấu hình attach bị vô hiệu hóa hoặc giới hạn OS/container | Chạy với quyền hợp lệ trên đúng máy/container và kiểm tra chính sách attach. |
| Báo file đã tồn tại | Mặc định không ghi đè | Chọn tên mới; cân nhắc `-overwrite` chỉ khi được phép mất bản cũ. |
| Không thấy file tại terminal B | File được JVM đích tạo ở đường dẫn của nó | Dùng đường dẫn tuyệt đối; kiểm tra filesystem/working directory của JVM, đặc biệt trong container. |
| Không tìm thấy `vt-demo-` | Nhấn Enter quá sớm, chọn sai PID, chương trình đã thoát | Chạy lại demo, giữ terminal A mở và dump trước khi `countDown()`. |
| `jq` báo lỗi hoặc thiếu field | File chưa hoàn tất, chọn sai file hoặc schema JDK khác dự kiến | Đợi `jcmd` hoàn tất, kiểm tra `runtimeVersion`/cấu trúc thực; không giả định mọi phiên bản có cùng field. |

## 9. Tự kiểm tra kiến thức

1. Vì sao `Thread.print` có thể không thể hiện đầy đủ virtual thread đang chờ? **Vì virtual thread có thể đã unmount khỏi carrier**, trong khi dump truyền thống tập trung vào platform thread.
2. `-format=plain` và `-format=json` khác gì? **Plain** thuận tiện đọc trực tiếp; **JSON** thuận tiện xử lý và lọc tự động theo nhóm/thread/stack.
3. Tại sao không thấy file trong thư mục terminal đang gọi `jcmd`? Vì `Thread.dump_to_file` yêu cầu **JVM đích ghi file** theo filesystem và working directory của JVM đó.
4. Một virtual thread nằm tại `CountDownLatch.await()` có chắc chắn deadlock không? **Không**; trong demo đó là chờ có chủ đích, được giải phóng khi nhấn Enter. Cần ngữ cảnh và nhiều snapshot.
5. Vì sao cần giữ `runtimeVersion` khi phân tích JSON? Vì các trường và kiểu dữ liệu thread dump có thể khác giữa các phiên bản JDK.

## Tài liệu tham khảo

- [Oracle Java 21 — Virtual Threads, mục Viewing Virtual Threads in jcmd Thread Dumps](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle — `jcmd` command (cách liệt kê PID, chạy diagnostic command và kiểm tra help)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle — `jcmd` ở các JDK mới hơn, mô tả tùy chọn `-format`/`-overwrite`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Inside Java — thay đổi kiểu trường số trong JSON thread dump ở JDK 27](https://inside.java/2026/05/20/quality-heads-up/)
