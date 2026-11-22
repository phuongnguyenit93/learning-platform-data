# WatchService trong Java: Đóng dịch vụ, ngắt chờ và dừng có kiểm soát

## 1. Vấn đề thực tế: một luồng đang chờ sự kiện thì làm sao dừng?

Một ứng dụng Java theo dõi thư mục nhận tệp mới và đẩy chúng vào hàng đợi xử lý. Ở phần lớn thời gian, thư mục không thay đổi và luồng consumer đang bị chặn tại:

```java
WatchKey key = watchService.take();
```

Đây là **câu lệnh minh họa trong phương thức có xử lý `InterruptedException`**, với `watchService` đã được mở và còn hợp lệ. Nếu người vận hành yêu cầu shutdown, chỉ thay một biến `running = false` có thể **không đủ**: luồng đang chờ trong `take()` không thức dậy chỉ vì một biến ứng dụng thay đổi.

Java NIO.2 cung cấp hai cơ chế cốt lõi để thoát khỏi phép chờ:

1. **Đóng dịch vụ** bằng `WatchService.close()`: làm dịch vụ không còn hoạt động, các đăng ký bị vô hiệu hóa và các luồng đang chờ lấy key được đánh thức bằng `ClosedWatchServiceException`.
2. **Ngắt thread đang chờ** bằng `Thread.interrupt()`: phép `take()` hoặc `poll(timeout,unit)` đang chờ có thể kết thúc bằng `InterruptedException`. Việc ngắt luồng **không tự đóng `WatchService`**, cũng không mặc định hủy các `WatchKey`.

Có lựa chọn thứ ba: dùng **`poll(timeout,unit)`** để định kỳ thức dậy và đọc cờ shutdown. Tùy ứng dụng, có thể phối hợp các cách này.

Những API trong phạm vi bài — `WatchService`, `WatchKey`, `take`, `poll`, `close`, `cancel`, `reset`, `ClosedWatchServiceException` — đều có từ **Java 7** và vẫn áp dụng trong Java hiện đại. Ví dụ chạy độc lập được kiểm thử bằng **JDK 17**.

**Kết luận cần nhớ ngay:** “Đóng dịch vụ”, “ngắt một thread” và “hủy một key” là **ba hành động khác nhau**. Chọn cơ chế đúng với phạm vi muốn dừng và với trách nhiệm sở hữu tài nguyên.

## 2. Bốn đối tượng và phạm vi trách nhiệm

| Đối tượng/cơ chế | Nó quản lý gì? | Khi dừng/đóng thì ảnh hưởng gì? |
| --- | --- | --- |
| `WatchService` | Hàng đợi các key được signal và những đăng ký đang liên kết với service | `close()` đóng cả dịch vụ, vô hiệu hóa các key được đăng ký |
| `WatchKey` | Một đăng ký theo dõi và tập sự kiện đang chờ của nó | `cancel()` hủy **một đăng ký**, không mặc định đóng service |
| Thread gọi `take()`/`poll(timeout)` | Luồng tiêu thụ thông báo | `interrupt()` đánh thức phép chờ theo cơ chế `InterruptedException`; service có thể tiếp tục dùng |
| Cờ shutdown của ứng dụng | Ý định nghiệp vụ: nên tiếp tục hay ngừng vòng lặp | Không tự khiến thread đang blocking trên `take()` thức dậy |

Các khái niệm này không hoán đổi được. Ví dụ, một watcher đăng ký ba thư mục, người dùng chỉ bỏ theo dõi một thư mục: gọi `cancel()` của key tương ứng là hợp lý hơn đóng toàn bộ service. Ngược lại, khi ứng dụng đóng hẳn subsystem giám sát, `WatchService.close()` là bước quản lý tài nguyên thích hợp.

### 2.1. Tạo một service và đăng ký thư mục

```java
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

Path directory = Path.of("incoming");

// Đoạn minh họa nằm trong phương thức khai báo throws IOException.
try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
    WatchKey registered = directory.register(
            watcher, StandardWatchEventKinds.ENTRY_CREATE);
    System.out.println(registered.isValid());
}
```

`Path.of` có từ **Java 11**; trên Java 7/8 có thể dùng `Paths.get`. Trong chương trình thật, thư mục phải tồn tại và provider phải hỗ trợ đăng ký; khối `try-with-resources` phải bao trùm **toàn bộ vòng đời giám sát**, không kết thúc ngay sau lệnh register như đoạn nhỏ minh họa ở trên.

`Files.exists` hoặc việc tạo `Path` không bảo đảm `register` sẽ thành công. Đăng ký có thể gặp `IOException`, `UnsupportedOperationException` hoặc lỗi khác theo điều kiện/provider. Xử lý lỗi ở lời gọi thực tế thay vì chỉ kiểm tra đường dẫn một lần rồi tin là an toàn.

## 3. Các cách lấy key và hành vi khi không có sự kiện

`WatchService` có ba cách lấy key thường gặp:

| API | Khi chưa có key | Giá trị trả về | Phản ứng với shutdown |
| --- | --- | --- | --- |
| `take()` | Chờ cho đến khi có key hoặc xảy ra điều kiện ngắt/đóng | `WatchKey` | Có thể ném `InterruptedException` hoặc `ClosedWatchServiceException` |
| `poll()` | **Không chờ** | `WatchKey` hoặc `null` | Khi service đóng, có thể ném `ClosedWatchServiceException` |
| `poll(timeout, unit)` | Chờ tối đa khoảng thời gian yêu cầu | `WatchKey` hoặc `null` nếu hết hạn | Có thể ném `InterruptedException` hoặc `ClosedWatchServiceException` |

### 3.1. `take()` là phép chờ có thể bị ngắt

```java
WatchKey key = watcher.take();
```

Đây là đoạn minh họa trong phương thức có `throws InterruptedException` hoặc một `catch` tương ứng. Không có key không có nghĩa phương thức trả `null`: với service còn mở, `take()` sẽ chờ thay vì trả `null` vì timeout.

Vì vậy mã sau **không phải shutdown an toàn**:

```java
while (running) {
    WatchKey key = watcher.take();
    // Khi không có event, không bao giờ quay lại đầu while để thấy running=false.
}
```

Đoạn trên là **ví dụ thiếu cơ chế đánh thức**. `running` dù là `volatile` hoặc `AtomicBoolean` vẫn chỉ cung cấp khả năng quan sát trạng thái khi thread thực thi tiếp; biến không tự mở khóa một phép chờ của WatchService.

### 3.2. `poll()` không chờ nhưng dễ thành busy loop

```java
WatchKey key = watcher.poll();
if (key == null) {
    // Hiện chưa có key.
}
```

Đây là đoạn minh họa trong phương thức có `watcher`. Nếu chạy liên tục trong `while` không sleep/không có công việc khác, có thể gây **busy waiting** và tiêu tốn CPU. `poll()` phù hợp nếu ứng dụng đã có event loop khác và chủ động kiểm tra queue theo một nhịp được điều phối.

### 3.3. `poll(timeout, unit)` giúp kiểm tra cờ shutdown

```java
while (!stopRequested.get()) {
    WatchKey key = watcher.poll(
            500, java.util.concurrent.TimeUnit.MILLISECONDS);

    if (key == null) {
        continue; // Hết thời gian chờ; kiểm tra cờ lần nữa.
    }
    // Lấy event, xử lý, reset key.
}
```

Đây là đoạn minh họa có `stopRequested` kiểu `AtomicBoolean` và cần xử lý `InterruptedException`, `ClosedWatchServiceException`; **chưa phải vòng lặp production hoàn chỉnh**. Giá trị 500 ms chỉ là **chính sách độ trễ shutdown** của ứng dụng, không phải ngưỡng do JDK bắt buộc.

Khi `poll(timeout, unit)` trả `null`, đó **không phải** bằng chứng directory bị xóa hoặc WatchKey mất hiệu lực: chỉ là không nhận key trong khoảng thời gian đó.

## 4. `WatchService.close()`: đóng toàn bộ dịch vụ

`WatchService` implement `Closeable` và có thể đóng bằng:

```java
watcher.close();
```

Đây là lệnh nằm trong phương thức có xử lý `IOException`. Khi đóng:

- Các đăng ký đang gắn với service không còn hiệu lực: `WatchKey.isValid()` trở thành `false` cho các key liên quan.
- Những thread đang blocking trong `take()` hoặc timed `poll` được đánh thức theo hợp đồng của service; các phép chờ/đọc queue trên service đã đóng có thể kết thúc bằng **`ClosedWatchServiceException`**.
- Không thể mở lại cùng object `WatchService` bằng `register` hay `reset` trên key đã bị invalid. Muốn theo dõi lại, tạo **service mới** và đăng ký lại.
- `close()` có thể được gọi nhiều lần; một service đã đóng thì lần đóng tiếp không có tác dụng hữu ích, nhưng vẫn nên thiết kế ownership rõ ràng.

**Điểm quan trọng:** `close()` là cơ chế giải phóng **nguồn event**. Nó không có nghĩa các tệp được theo dõi bị xóa, dữ liệu đầu ra đã flush xong, hay mọi tác vụ ứng dụng phát sinh từ event đã hoàn thành.

### 4.1. Đóng từ thread khác có thể đánh thức `take()`

Ví dụ ý tưởng gồm hai thread:

```java
// Thread A: consumer
try {
    watcher.take();
} catch (ClosedWatchServiceException ex) {
    // WatchService đã đóng; dừng vòng tiêu thụ.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Rời khỏi worker theo chính sách hủy.
}

// Thread B: chủ sở hữu WatchService quyết định shutdown.
watcher.close();
```

Đây là **hai đoạn mã minh họa ở hai ngữ cảnh thực thi**, không phải chương trình được ghép và chạy như một khối; `watcher` phải được chia sẻ đúng cách và thao tác `close()` xử lý `IOException`. Chương trình đầy đủ ở mục 11 kiểm thử hành vi này bằng hai thread thực tế.

### 4.2. `ClosedWatchServiceException` là unchecked

`ClosedWatchServiceException` thuộc `java.nio.file` và là **unchecked exception**, không phải `IOException`. Nếu chỉ catch `IOException` hoặc chỉ catch `InterruptedException`, bạn **không** tự động bắt được trường hợp WatchService đã đóng.

```java
try {
    WatchKey key = watcher.take();
    // ...
} catch (ClosedWatchServiceException closed) {
    // Phân biệt shutdown có chủ đích và đóng ngoài dự kiến.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Dừng theo chính sách interruption.
}
```

Đây là đoạn minh họa trong phương thức đã có `watcher` hợp lệ, với các import tương ứng. **Không coi mọi `ClosedWatchServiceException` là “thành công”**: nếu ứng dụng chưa yêu cầu shutdown mà service đã đóng, đó có thể là lỗi lifecycle cần được báo cáo.

### 4.3. Đóng trong `try-with-resources`

Với **một watcher chỉ được một component sở hữu**, cách quản lý phổ biến:

```java
try (WatchService watcher =
             java.nio.file.FileSystems.getDefault().newWatchService()) {
    // Register và chạy vòng tiêu thụ trong phạm vi này.
} // WatchService được đóng khi ra khỏi phạm vi.
```

Đây là đoạn minh họa trong phương thức có `throws IOException`. Nếu một worker thread khác đang `take()`, việc owner rời khối try đóng watcher sẽ yêu cầu worker kết thúc phép chờ. Sau đó **vẫn cần join/await worker** nếu component phải bảo đảm worker đã chấm dứt trước khi được xem là shutdown hoàn tất.

Đóng resource không tự đảm bảo một thread khác đã kịp chạy catch/finally và giải phóng mọi resource **do thread ấy sở hữu**.

## 5. `Thread.interrupt()`: ngắt thread mà không đóng WatchService

Cơ chế interruption của Java là một yêu cầu hợp tác gửi tới thread. Với các phương thức chờ có hỗ trợ interruption như `WatchService.take()` và `WatchService.poll(timeout,unit)`, thread có thể nhận **`InterruptedException`** và thoát khỏi phép chờ.

```java
Thread worker = /* thread đang chạy vòng lặp WatchService */;
worker.interrupt();
```

Đây là mã minh họa cần một đối tượng `worker` thật; không phải Java có cú pháp gán `/* ... */` thành giá trị. Khi viết code chạy được, `worker` phải được khởi tạo với một `Runnable`/`Thread` cụ thể.

**`interrupt` khác `close`:**

- Thread bị ngắt có thể dừng vòng chờ của nó.
- WatchService **không tự bị đóng** chỉ vì một thread bị interrupt.
- Một `WatchKey` đang valid **không tự bị hủy** chỉ vì consumer thread nhận `InterruptedException`.
- Thread khác có thể tiếp tục dùng watcher nếu lifecycle của ứng dụng cho phép.
- Nếu owner quyết định shutdown toàn bộ subsystem, nó vẫn phải đóng watcher khi hết vòng đời.

### 5.1. Trả lại interrupt status trong `catch`

Khi một phương thức blocking ném `InterruptedException`, interrupt status của thread thường đã được **xóa** như một phần của việc nhận interruption. Nếu tầng gọi cần biết yêu cầu hủy đã xảy ra, code thường khôi phục cờ:

```java
try {
    watcher.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là đoạn minh họa **nằm trong một phương thức trả `void`**; `watcher` phải được khai báo. Tùy thiết kế API, có thể truyền `InterruptedException` lên caller bằng `throws InterruptedException` thay vì bắt. Không nên vừa nuốt exception vừa chạy tiếp một vòng lặp vô hạn, vì việc đó có thể làm tín hiệu shutdown bị mất.

### 5.2. Interruption không ép thread dừng ngay lập tức

`interrupt()` không phải một lệnh “kill thread”. Nó yêu cầu hợp tác; hiệu quả phụ thuộc thread đang làm gì. Khi thread đang gọi `take()`/timed `poll`, cơ chế blocking hỗ trợ `InterruptedException`. Nếu thread đang xử lý nội dung file hoặc chạy phép tính không kiểm tra cờ, nó có thể chưa dừng ngay.

Đừng sử dụng các kỹ thuật dừng thread cưỡng bức đã lỗi thời hoặc nguy hiểm. Hãy thiết kế vòng lặp tôn trọng interruption, trạng thái shutdown, timeout và ownership của tài nguyên.

### 5.3. Không tự đánh đồng interrupt với một lỗi I/O

`InterruptedException` là tín hiệu về **luồng thực thi**, không phải bằng chứng rằng file thiếu hoặc quyền truy cập thất bại. Tương tự, `ClosedWatchServiceException` cho biết lifecycle của watcher, không phải một event `ENTRY_DELETE`.

Báo cáo trạng thái hợp lý có thể gồm:

```text
RUNNING
STOP_REQUESTED
STOPPED
FAILED
```

Đây là mô hình trạng thái minh họa của ứng dụng, **không phải enum do `WatchService` trả về**. Khi worker nhận interrupt trong quá trình shutdown, kết quả có thể là STOPPED; nếu interrupt bất ngờ làm mất dữ liệu bắt buộc, cần báo cáo theo hợp đồng nghiệp vụ.

## 6. So sánh ba chiến lược dừng

| Chiến lược | Cách thực hiện | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| **Close service** | `watcher.close()` từ owner | Đánh thức phép chờ, vô hiệu hóa mọi registration, giải phóng watcher | Dừng **toàn bộ** WatchService; phải tạo service mới nếu muốn watch tiếp |
| **Interrupt worker** | `worker.interrupt()` | Đánh thức phép chờ của **một thread**; service có thể còn dùng được | Worker phải xử lý `InterruptedException`; owner vẫn cần quản lý watcher |
| **Timed poll + flag** | `poll(timeout,unit)` và `AtomicBoolean` | Có cơ hội kiểm tra shutdown/health định kỳ, không cần close ngay | Độ trễ tối đa phụ thuộc timeout, phải tránh busy loop và xử lý lỗi/interrupt |

Các cách có thể phối hợp. Ví dụ, trong một subsystem có **WatchService thuộc sở hữu của worker**, lúc dừng: đặt cờ stop, đóng watcher để đánh thức `take()`, rồi chờ thread hoàn thành. Với một watcher được dùng chung cho nhiều directory và nhiều consumer, phải xác định ownership trước khi đóng: đóng service vì một tác vụ nhỏ sẽ làm các tác vụ khác mất toàn bộ registration.

### 6.1. Chọn cách nào cho một worker duy nhất?

Nếu worker và watcher có vòng đời như nhau, **close service + join worker** là chiến lược đơn giản, dễ làm rõ cleanup. Nếu dịch vụ cần tiếp tục cho luồng khác, **interrupt riêng worker** hoặc timed poll có thể phù hợp hơn.

### 6.2. Vì sao không chỉ `cancel`?

`WatchKey.cancel()` hủy **một registration**. Nó không mặc định gửi một thông báo shutdown tới thread đang blocking trong `watcher.take()`. Nếu watcher không có key khác được signal, thread có thể vẫn chờ.

Do đó, **`cancel()` không phải cách chung để đánh thức `take()`** khi ứng dụng đóng toàn bộ subsystem. Nếu muốn chỉ bỏ theo dõi một directory trong watcher dùng chung, cancel là đúng; muốn worker không chờ nữa thì phải có cơ chế đánh thức/dừng tương ứng.

### 6.3. Vì sao không chỉ `key.reset()`?

`reset()` phục hồi vòng đời **signal** của key valid sau khi consumer lấy event. Nó không có nghĩa gửi tín hiệu shutdown, không mở lại key invalid và không đảm bảo đánh thức một thread chờ khi không có event. Nhánh lifecycle cần được quản lý độc lập.

## 7. Quy trình shutdown có kiểm soát cho một component

Một chiến lược có thể dùng trong service backend:

1. **Định nghĩa owner** của `WatchService`, worker thread và các đăng ký.
2. Khi nhận yêu cầu shutdown, **đánh dấu `STOP_REQUESTED`** bằng trạng thái thread-safe.
3. **Ngừng nhận công việc mới** từ event consumer theo chính sách. Nếu task đang xử lý dở, quyết định có hoàn tất, hủy hoặc đưa vào hàng đợi bền vững không.
4. **Đánh thức phép chờ:** đóng WatchService nếu toàn subsystem dừng; hoặc interrupt worker/timed poll nếu watcher còn dùng cho thành phần khác.
5. Worker xử lý `ClosedWatchServiceException` hoặc `InterruptedException` **như tín hiệu dừng khi đã có yêu cầu shutdown**; nếu xảy ra ngoài dự kiến, báo lifecycle failure.
6. Đóng/cleanup các resource khác do worker sở hữu trong `finally` hoặc `try-with-resources`.
7. **Chờ worker kết thúc** bằng `Thread.join(timeout)` hoặc cơ chế tương đương, có chính sách nếu vượt giới hạn thời gian.
8. Đánh dấu `STOPPED` chỉ khi điều kiện dừng mà ứng dụng hứa hẹn đã được đáp ứng. Không coi gọi `close()` là đủ để khẳng định tất cả task phụ đã hoàn thành.

Một ví dụ khái niệm cho owner:

```java
// Ví dụ đặt trong component có watcher, worker, stopRequested.
void requestStop() throws java.io.IOException {
    stopRequested.set(true);
    watcher.close();  // Đánh thức consumer và đóng registration.
}

// Sau requestStop: code điều phối chờ worker dừng.
// Không gọi join vô hạn nếu hệ thống yêu cầu deadline shutdown.
```

Đây là **đoạn minh họa chưa độc lập**, vì `stopRequested`, `watcher`, `worker` và phương thức giám sát worker là phần của lớp ứng dụng; không phải code chạy trực tiếp từ một file.

### 7.1. Khi đã quyết định shutdown thì có cần gọi `reset()` nữa?

Tùy chính sách. Trong loop thông thường, sau khi xử lý pending events cần `reset()` để tiếp tục nhận notification. Nhưng khi owner đã yêu cầu shutdown và sắp đóng watcher, **không nên coi `reset()==true` là điều kiện để hủy shutdown**. Key có thể đã invalid sau `close()`.

Nếu code đang xử lý một batch event trong lúc shutdown đến, cần xác định: hoàn tất batch, xếp lại phần chưa làm, hay dừng ngay. Kết quả reset chỉ phản ánh registration còn valid, không phản ánh tình trạng tác vụ nghiệp vụ.

### 7.2. Shutdown graceful khác với “đóng ngay, bỏ pending events”

`close()` đóng cơ chế notification và các registration; nó **không phải thao tác drain có bảo đảm**. Nếu bắt buộc không mất một tác vụ đã nhận, cần tách rõ:

- **Event đã nhận:** đã đưa vào queue/DB hay chưa? Có thể xử lý tiếp sau khi watcher đóng không?
- **Event đang pending nhưng chưa đọc:** có thể bị bỏ khi service đóng; không được giả định sẽ được replay sau restart.
- **Thay đổi xảy ra giữa shutdown và restart:** không có watcher để quan sát, cần rescan/đối soát trạng thái thư mục.
- **Kết quả downstream:** muốn chờ hoàn tất, phải quản lý worker pool và queue riêng.

WatchService không phải hệ thống message queue bền vững, và không thay thế một giao thức publish tệp an toàn hoặc file-system snapshot nếu nghiệp vụ yêu cầu tính chính xác cao.

## 8. Event loop mẫu: catch đúng exception và reset đúng lúc

Khung một watcher có **một consumer thread**:

```java
static void consume(WatchService watcher) {
    for (;;) {
        WatchKey key;
        try {
            key = watcher.take();
        } catch (ClosedWatchServiceException closed) {
            break; // Nếu shutdown có chủ đích; nếu không, cần báo lỗi.
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            break;
        }

        try {
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                    // Đánh dấu chỉ mục cần đối soát lại.
                    continue;
                }
                // Đưa event vào hệ thống xử lý, không làm việc quá nặng ở đây.
            }
        } finally {
            if (!key.reset()) {
                // Key invalid: cập nhật mapping và quyết định có
                // đăng ký lại hoặc dừng, tùy ứng dụng.
            }
        }
    }
}
```

Đây là **phương thức minh họa để đặt trong lớp có import tương ứng**. Nó còn cần trạng thái shutdown, lifecycle của watcher, chính sách xử lý lỗi và quản lý nhiều key trước khi dùng như production code. Đặt `reset()` trong `finally` giúp thử rearm key khi xử lý một batch bị ngắt bất thường, nhưng **không được nuốt lỗi từ xử lý event** và không nên reset mù quáng rồi tiếp tục nếu trạng thái nghiệp vụ đã hỏng.

### 8.1. Không gộp exception với `IOException`

`take()` khai báo `InterruptedException`, trong khi đóng service gây `ClosedWatchServiceException` **unchecked**. `key.pollEvents()` lấy pending events, `key.reset()` có boolean về tính hợp lệ; mỗi API trả một kiểu tín hiệu khác nhau.

Phân biệt bốn trường hợp:

| Tình huống | Tín hiệu | Ý nghĩa |
| --- | --- | --- |
| WatchService đã đóng | `ClosedWatchServiceException` | Đóng toàn bộ nguồn notification |
| Thread bị interrupt khi chờ | `InterruptedException` | Yêu cầu hủy/điều phối thread, watcher có thể vẫn mở |
| Registration invalid | `key.reset() == false` | Không dùng tiếp key đó; service có thể còn hoạt động |
| Hết thời gian chờ nhưng watcher mở | `poll(timeout)==null` | Chưa có key, không phải lỗi |

### 8.2. `OVERFLOW` không biến mất chỉ vì shutdown đúng

Kể cả khi đóng watcher đúng quy trình, bạn có thể đã bỏ lỡ event trước đó vì `OVERFLOW`, event coalescing hoặc directory bị thay đổi khi không có registration. Nếu hệ thống phải tái dựng trạng thái tệp đáng tin, thiết kế **rescan/reconciliation** khi startup và sau overflow; không đồng nhất graceful shutdown với việc không mất event.

### 8.3. Lỗi callback/consumer phải được phân loại

Nếu code xử lý event ném unchecked exception, ví dụ lỗi parser hoặc lỗi mapping, `finally` có thể reset key nhưng **ngoại lệ vẫn truyền ra** và worker chấm dứt. Đây có thể là hành vi đúng nếu cần fail-fast; owner phải biết worker đã chết bất thường. Nếu muốn tiếp tục, cần catch cụ thể, kiểm tra idempotency và báo lỗi đầy đủ.

Không dùng một `catch (Exception)` chung để bỏ qua tất cả, vì nó có thể che lỗi lập trình và khiến người vận hành tin watcher vẫn khỏe trong khi event bị mất.

## 9. Thread interruption, cờ stop và thứ tự thao tác

### 9.1. `AtomicBoolean` phù hợp để truyền ý định shutdown

```java
private final java.util.concurrent.atomic.AtomicBoolean stopRequested =
        new java.util.concurrent.atomic.AtomicBoolean();
```

Đây là **field minh họa trong một lớp**, không phải câu lệnh độc lập ở top-level Java. `stopRequested.set(true)` tạo tín hiệu trạng thái có thể đọc từ thread khác. Nhưng nếu consumer đang `take()`, vẫn cần một cơ chế đánh thức.

### 9.2. Thứ tự: báo stop trước, đánh thức sau

Một trình tự thường dễ điều tra:

```java
stopRequested.set(true);
watcher.close();
```

Khi consumer catch `ClosedWatchServiceException`, có thể xem `stopRequested.get()` để xác định đóng có chủ đích hay bất ngờ. Đây vẫn không phải chứng minh tuyệt đối mọi race đã biến mất, nhưng giúp phân biệt trạng thái nghiệp vụ.

Nếu đảo thứ tự và đóng trước khi đặt cờ, consumer có thể thức dậy, thấy chưa có yêu cầu stop và báo lỗi shutdown “bất ngờ” một cách không cần thiết.

### 9.3. `Thread.interrupt` và cờ stop có thể kết hợp

```java
stopRequested.set(true);
worker.interrupt();
```

Đây là đoạn minh họa với worker đã được khởi tạo. Cờ stop diễn đạt **ý định**, interruption đánh thức **phép chờ hiện tại**. Nếu watcher vẫn dùng chung, owner không nhất thiết đóng service. Nếu worker chính là owner duy nhất, vẫn cần đóng service trong cleanup để không rò rỉ tài nguyên.

### 9.4. Không reset interrupt status một cách tùy tiện

Khi catch `InterruptedException` trong worker, thường khôi phục status rồi thoát. Tuy nhiên, có những API quản lý interruption khác nhau; caller phải quyết định **truyền exception lên** hay **tự xử lý rồi dừng**. Không gọi `Thread.interrupted()` chỉ để “xóa cờ ngắt” rồi tiếp tục vòng lặp giám sát nếu không có hợp đồng rõ, vì `Thread.interrupted()` đọc và **xóa** status của thread hiện tại.

## 10. Tài nguyên: service owner, executor và luồng kết thúc

### 10.1. WatchService đóng không đồng nghĩa worker đã join

`watcher.close()` có thể đánh thức thread chờ, nhưng thread vẫn cần được scheduler cho chạy, thực hiện `catch`, dọn dẹp và kết thúc. Vì vậy nếu một component cần cam kết “không còn worker thread sống” khi trả về từ shutdown, phải **chờ**:

```java
worker.join(3000);
if (worker.isAlive()) {
    throw new IllegalStateException("Worker did not stop");
}
```

Đây là đoạn minh họa trong phương thức có `throws InterruptedException` và một `Thread worker` đã được tạo. `3000` ms là thời hạn của ứng dụng, không phải thời hạn mặc định của JVM. Nếu worker còn sống sau timeout, phải có chính sách báo lỗi/giám sát, không tuyên bố shutdown hoàn tất.

### 10.2. Tránh deadlock khi shutdown

Nếu worker đang giữ một lock mà owner cần để gọi close, và owner lại giữ một lock khác rồi `join()` worker, có thể tạo deadlock. Thiết kế shutdown nên tránh giữ lock dài hạn trong lúc chờ thread. Không gọi `join()` trên **chính thread hiện tại**.

Nếu worker đang làm công việc nặng ngoài `take`, `close` không tự hủy công việc đó. Hãy thiết kế task có thể bị hủy, deadline phù hợp và cơ chế đóng các resource nội bộ.

### 10.3. ExecutorService cũng cần xử lý shutdown

Nếu watcher chạy trong `ExecutorService`:

- `shutdown()` ngừng nhận task mới nhưng **không nhất thiết interrupt** một task đang blocked ở `take()`.
- `shutdownNow()` cố gắng interrupt các task đang chạy nhưng **không bảo đảm** chúng đã dừng; vẫn cần chờ bằng `awaitTermination` và xử lý task không hợp tác.
- Một `Future.cancel(true)` có thể gửi yêu cầu interrupt task chạy dưới `ExecutorService`, nhưng hiệu quả phụ thuộc trạng thái/task và không thay thế việc đóng WatchService do component sở hữu.
- Nếu việc xử lý event được đẩy sang pool khác, cần quyết định có ngừng nhận task mới, drain queue, hay hủy task còn chạy; đóng watcher **không tự dừng pool xử lý**.

Không xem một lời gọi shutdown đơn lẻ là transaction đảm bảo mọi byte file đã được xử lý.

### 10.4. Vòng đời dài hạn

Trong server, gắn watcher vào lifecycle của module hoặc service rõ ràng. Khi module đóng, giải phóng đăng ký, đóng service, chờ worker, rồi cập nhật health/status. Không chỉ dựa vào JVM shutdown hook để hoàn thành mọi công việc quan trọng: hook có giới hạn thời gian và không đảm bảo chạy trong mọi tình huống dừng tiến trình.

## 11. Ví dụ Java 17+ hoàn chỉnh: đóng để đánh thức, interrupt để thoát, rồi tiếp tục watcher

Chương trình này thực hiện **hai kiểm thử độc lập** trên một thư mục tạm:

1. Tạo watcher thứ nhất, register `ENTRY_CREATE`, khởi chạy thread gọi `watcher.take()`.
2. Từ thread điều phối, gọi `watcher.close()`; consumer kết thúc bằng `ClosedWatchServiceException`, key mất hiệu lực.
3. Tạo watcher thứ hai, register trên cùng directory; khởi chạy thread khác gọi `take()`.
4. Điều phối gọi `worker.interrupt()`; consumer kết thúc bằng `InterruptedException` và khôi phục interrupt flag. **Key của watcher thứ hai vẫn valid**.
5. Gọi `poll(timeout)` trước khi tạo file để minh họa trả `null` khi chưa có event.
6. Tạo `created.txt`, nhận `ENTRY_CREATE`, gọi `pollEvents()` và `reset()` thành công: watcher thứ hai vẫn dùng được sau khi một consumer bị interrupt.
7. Đóng service thứ hai qua `try-with-resources`, xóa tệp và thư mục tạm, không sửa dữ liệu có sẵn.

Cả hai thread phụ đều có **`CountDownLatch`** để báo đã bắt đầu và **`join` có timeout** để test không chờ vô hạn. `CountDownLatch` không phải công cụ tự chứng minh thread đã ở đúng trạng thái scheduler WAITING khi owner tác động; nó xác nhận luồng được khởi chạy, còn kết quả exception và event được kiểm tra trực tiếp.

Tạo tệp **`WatchShutdownDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class WatchShutdownDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void joinOrFail(Thread worker) throws InterruptedException {
        worker.join(3000);
        check(!worker.isAlive(), "watcher thread did not stop");
    }

    private static void demonstrateClose(Path dir)
            throws IOException, InterruptedException {
        WatchService watcher = FileSystems.getDefault().newWatchService();
        try {
            WatchKey key = dir.register(
                    watcher, StandardWatchEventKinds.ENTRY_CREATE);
            CountDownLatch started = new CountDownLatch(1);
            AtomicReference<String> result = new AtomicReference<>("not started");

            Thread worker = new Thread(() -> {
                started.countDown();
                try {
                    watcher.take();
                    result.set("unexpected key");
                } catch (ClosedWatchServiceException expected) {
                    result.set("service closed");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    result.set("interrupted");
                }
            }, "close-waiter");

            worker.start();
            check(started.await(2, TimeUnit.SECONDS), "worker not started");
            watcher.close();
            joinOrFail(worker);
            check("service closed".equals(result.get()), "close outcome");
            check(!key.isValid(), "key invalid after close");
            System.out.println("close wakes take = " + result.get());
            System.out.println("key valid after close = " + key.isValid());
        } finally {
            watcher.close();
        }
    }

    private static void demonstrateInterrupt(Path dir, Path entry)
            throws IOException, InterruptedException {
        try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
            WatchKey registered = dir.register(
                    watcher, StandardWatchEventKinds.ENTRY_CREATE);
            CountDownLatch started = new CountDownLatch(1);
            AtomicReference<String> result = new AtomicReference<>("not started");
            AtomicBoolean flagRestored = new AtomicBoolean();

            Thread worker = new Thread(() -> {
                started.countDown();
                try {
                    watcher.take();
                    result.set("unexpected key");
                } catch (InterruptedException expected) {
                    Thread.currentThread().interrupt();
                    flagRestored.set(Thread.currentThread().isInterrupted());
                    result.set("interrupted");
                } catch (ClosedWatchServiceException closed) {
                    result.set("service closed");
                }
            }, "interrupt-waiter");

            worker.start();
            check(started.await(2, TimeUnit.SECONDS), "worker not started");
            worker.interrupt();
            joinOrFail(worker);
            check("interrupted".equals(result.get()), "interrupt outcome");
            check(flagRestored.get(), "interrupt flag lost");
            check(registered.isValid(), "interrupt should not cancel key");

            System.out.println("interrupt wakes take = " + result.get());
            System.out.println("interrupt flag restored = " + flagRestored.get());
            System.out.println("key valid after interrupt = " + registered.isValid());

            boolean timeout = watcher.poll(100, TimeUnit.MILLISECONDS) == null;
            check(timeout, "unexpected event before creating a file");
            System.out.println("timed poll empty = " + timeout);

            Files.createFile(entry);
            WatchKey signalled = watcher.poll(3, TimeUnit.SECONDS);
            check(signalled == registered, "missing registered key");
            boolean createSeen = false;
            for (WatchEvent<?> event : signalled.pollEvents()) {
                if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                    throw new IOException("overflow requires rescan");
                }
                if (event.kind() == StandardWatchEventKinds.ENTRY_CREATE
                        && event.context() instanceof Path relative
                        && relative.getFileName().equals(entry.getFileName())) {
                    createSeen = true;
                }
            }
            check(signalled.reset(), "key invalid before reset");
            check(createSeen, "entry create was not observed");
            System.out.println("event after interrupt = " + createSeen);
        }
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {
        Path dir = Files.createTempDirectory("watch-shutdown-");
        Path entry = dir.resolve("created.txt");
        try {
            demonstrateClose(dir);
            demonstrateInterrupt(dir, entry);
        } finally {
            Files.deleteIfExists(entry);
            Files.deleteIfExists(dir);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 WatchShutdownDemo.java
java WatchShutdownDemo
```

**Stdout chính xác đã kiểm thử trên Windows với file-system provider mặc định hỗ trợ `ENTRY_CREATE`:**

```text
close wakes take = service closed
key valid after close = false
interrupt wakes take = interrupted
interrupt flag restored = true
key valid after interrupt = true
timed poll empty = true
event after interrupt = true
cleanup = done
```

### 11.1. Vì sao ví dụ đóng watcher thứ nhất theo cách tường minh?

Mục tiêu kiểm thử là gọi `close()` **trong lúc worker vẫn đang sử dụng service** rồi xác minh kết quả. Vì thế phương thức `demonstrateClose` chủ động gọi `watcher.close()` và đặt một lần đóng bảo đảm trong `finally`. Điều này cũng tránh cảnh báo của `javac -Xlint:try` về việc gọi `close` tường minh **ngay bên trong một khối `try-with-resources` đang quản lý cùng resource**.

Với code production mà không cần chủ động đóng trước thời điểm kết thúc scope, `try-with-resources` vẫn là cách quản lý watcher tốt. Trong cả hai phương án, owner phải hiểu khi nào scope watcher kết thúc.

### 11.2. Vì sao `key valid after close = false`?

`WatchService.close()` làm mọi registration gắn với service không còn hợp lệ. `WatchKey.reset()` không thể hồi sinh key invalid. Nếu ứng dụng cần theo dõi lại, phải tạo WatchService mới, đăng ký lại và đối soát những thay đổi trong khoảng thời gian không watch.

### 11.3. Vì sao sau interrupt khóa thứ hai vẫn valid?

`worker.interrupt()` tác động vào thread đang chờ; code catch `InterruptedException`, khôi phục status rồi kết thúc. WatchService thứ hai **chưa bị đóng**, và key đăng ký thư mục vẫn tồn tại.

Chính vì vậy sau đó chương trình có thể tạo một file mới, dùng `watcher.poll(3,SECONDS)` để nhận key, drain event, reset và in `event after interrupt = true`. Trường hợp này minh họa rõ rằng **interrupt thread không đồng nghĩa cancel key**.

### 11.4. Vì sao `timed poll empty = true`?

Tại bước này test chưa tạo file và không có sự kiện khác trong fixture. `poll(100,MILLISECONDS)` đợi tối đa 100 ms, rồi trả `null` khi không có key. Đó là hành vi timeout hợp lệ, **không phải watcher hỏng**.

Trong môi trường có sự kiện ngoài dự kiến hoặc provider khác, test có thể nhận key bất ngờ và kết thúc với assertion; kết quả stdout được nêu là kết quả thực tế của môi trường đã kiểm thử, không phải mọi provider đều phát đúng sự kiện và thời điểm như nhau.

### 11.5. Vì sao `joinOrFail` quan trọng?

Không thể kết luận thread phụ đã chết chỉ vì owner vừa gọi `watcher.close()` hoặc `worker.interrupt()`. `joinOrFail` chờ tối đa 3 giây rồi kiểm tra `!worker.isAlive()`; nếu worker còn sống, test thất bại thay vì in thành công giả.

Ngưỡng 3 giây là chính sách test, không phải cam kết Java về thời gian thực thi/scheduler. Trong ứng dụng thực, có thể cần thời hạn dài hơn, báo cáo timeout, hủy các task phụ hoặc đưa sự cố vào giám sát.

### 11.6. Vì sao dùng `AtomicReference` và `AtomicBoolean`?

Các biến này chứa kết quả **được viết bởi worker và đọc từ thread điều phối**. Chúng cung cấp khả năng truy cập thread-safe rõ ràng, và `join` cũng tạo quan hệ đồng bộ cần thiết khi thread đã kết thúc. Dùng các biến thường mà không có đồng bộ rõ ràng có thể dẫn tới logic shutdown khó chứng minh trong code nhiều thread phức tạp.

### 11.7. Giới hạn môi trường và cleanup

Thí nghiệm dùng thư mục tạm do chương trình tạo, không thao tác dữ liệu người dùng. Nếu provider không hỗ trợ đăng ký/watch hoặc không gửi `ENTRY_CREATE` trong thời hạn, chương trình có thể ném lỗi và không in stdout như ví dụ. Đây là giới hạn môi trường/event delivery, không phải một khác biệt về cú pháp Java.

Phần `finally` cố xóa file và thư mục tạm. Nếu hệ điều hành từ chối xóa hoặc có một tác nhân khác tạo thêm file trong fixture, cleanup có thể ném `IOException`; ứng dụng không nên tự nuốt rồi báo thành công.

## 12. Một watcher nhiều thư mục: dừng một phần hay dừng toàn bộ?

Giả sử cùng một service có:

```text
WatchService
  ├── keyA → incoming/orders
  ├── keyB → incoming/images
  └── keyC → incoming/logs
```

Cần phân biệt ba yêu cầu:

| Yêu cầu | Thao tác thường hợp lý |
| --- | --- |
| Ngừng theo dõi **orders** nhưng vẫn nhận images/logs | `keyA.cancel()`, loại mapping; không đóng service |
| Dừng **consumer thread** nhưng giữ service cho consumer khác | `worker.interrupt()` hoặc timed poll + cờ stop, phối hợp ownership |
| Ngừng toàn bộ bộ phận theo dõi | `watcher.close()`, đánh thức phép chờ, chờ worker kết thúc và cleanup |

`WatchKey.cancel()` có thể làm key invalid nhưng nếu key đã được queue trước lúc cancel, consumer vẫn có thể nhận nó về sau. **Nhận key từ queue không chứng minh key đang valid**. Kiểm tra `key.isValid()`, `reset()` và ngữ cảnh trạng thái registration.

Nếu owner close toàn bộ service, **mọi key của service đó mất hiệu lực**. Không cố “giữ keyB để dùng tiếp” sau khi watcher đóng; phải tạo service và registration mới.

### 12.1. Mapping key–directory

Ứng dụng nhiều directory thường quản lý:

```java
Map<WatchKey, Path> registrations = new HashMap<>();
```

Đây là field/biến minh họa cần import `Map`, `HashMap`, `WatchKey`, `Path`. Khi `reset() == false`, loại key tương ứng khỏi map và quyết định có đăng ký lại. Khi dừng một key có chủ đích, xóa mapping **theo chính sách thread-safety** nếu nhiều luồng cùng truy cập.

Đừng đóng WatchService chỉ vì một key invalid nếu những directory khác vẫn đang được giám sát và nghiệp vụ yêu cầu tiếp tục.

## 13. Vì sao `close` không phải bảo đảm xử lý đủ event?

`WatchService` là cơ chế **nhận notification**, không phải event log có thể replay mọi thay đổi một cách bền vững. Khi shutdown, có thể xuất hiện:

- Event đã được queue vào WatchService nhưng consumer chưa `take()`.
- Một WatchKey đang SIGNALLED, consumer đã lấy key nhưng chưa gọi `pollEvents()`.
- Event đã được lấy nhưng chưa đưa vào hàng đợi xử lý nghiệp vụ.
- File đang ghi dở, event `ENTRY_CREATE` đã có nhưng nội dung chưa sẵn sàng.
- Thay đổi xảy ra sau khi service đóng và trước khi watcher mới đăng ký.
- `OVERFLOW` trước shutdown khiến event bị mất dù key vẫn valid.

Vì vậy, nếu hệ thống cần **không bỏ sót file mới**, không thể coi `close()` hay `interrupt()` là cơ chế bảo đảm toàn vẹn dữ liệu. Cần:

1. Có nguồn sự thật về file hiện tồn tại, không chỉ lịch sử notification.
2. Quét/đối soát bằng `Files.walkFileTree` hoặc API phù hợp vào lúc startup và sau restart/overflow.
3. Tách ingestion event với xử lý nội dung file qua queue/DB có cơ chế xác nhận nếu cần bảo đảm.
4. Dùng chiến lược **idempotent** để xử lý được các event trùng/coalesced mà không tạo dữ liệu trùng.
5. Xác định thời điểm file được coi “sẵn sàng” theo giao thức producer/consumer.
6. Ghi nhận trạng thái partial khi không thể bảo đảm đã quan sát mọi thay đổi.

### 13.1. Stop-accepting khác stop-processing

Một dịch vụ có thể ngừng **nhận event mới** bằng cách đóng watcher, nhưng cho phép những task đã nhận chạy đến hết. Cũng có thể yêu cầu hủy task đang chạy nếu SLA shutdown bắt buộc. Hai chính sách có sự đánh đổi:

- **Drain có kiểm soát:** giảm công việc dở dang, nhưng mất thời gian và cần deadline.
- **Cancel nhanh:** giảm độ trễ shutdown, nhưng phải có retry/recovery khi khởi động lại.
- **Stop ngay bằng close:** ngắt nguồn notification, không đảm bảo cả hai mục trên đã xong.

Không gọi toàn bộ ba thao tác bằng một tên “graceful shutdown” nếu không xác định cụ thể đã bảo đảm điều gì.

## 14. Những trường hợp biên và rủi ro khi shutdown

### 14.1. Close và interrupt có thể chạy cạnh tranh

Một thread gọi `watcher.close()` đồng thời thread khác gọi `worker.interrupt()`. Kết quả quan sát bởi consumer có thể phụ thuộc thời điểm: nó có thể nhận `ClosedWatchServiceException` hoặc `InterruptedException`. Không nên viết unit test yêu cầu **một loại exception cố định** khi cả hai tín hiệu được kích hoạt cạnh tranh.

Nếu cả hai đều là tín hiệu shutdown hợp lệ, consumer nên xử lý cả hai như kết quả dừng theo chính sách, đồng thời bảo toàn interrupt status khi bắt `InterruptedException`.

### 14.2. Close không chờ worker hoàn thành mọi callback

`close()` làm WatchService đóng; nó không thay `Thread.join()` hay `ExecutorService.awaitTermination()`. Thread có thể còn đang xử lý event hoặc bị nghẽn bởi I/O khác. Nếu hệ thống đòi hỏi hết worker trước khi báo stop, phải chờ/hạn chế thời gian và kiểm tra kết quả.

### 14.3. Interrupt khi không có blocking call

Nếu thread đang xử lý CPU mà không kiểm tra `Thread.currentThread().isInterrupted()`, `interrupt()` chỉ đặt cờ, không cưỡng bức dừng ngay. Tích hợp cancellation checks ở các bước xử lý dài khi thích hợp, không tự ý dùng thread stop/suspend cưỡng bức.

### 14.4. Exception từ xử lý event và mất reset

Một callback xử lý event có thể ném `RuntimeException`. Nếu vòng lặp dự định tiếp tục nhưng không reset key do exit bất ngờ, WatchService có thể mất nhịp thông báo. Hãy quản lý reset với `try/finally` khi lựa chọn **tiếp tục consumer**, và có chính sách fail-fast hợp lý nếu callback bị lỗi nghiêm trọng.

### 14.5. Provider không hỗ trợ watcher

Tạo watcher hoặc đăng ký directory có thể thất bại hoặc có giới hạn theo file system. Không phải mọi môi trường gửi event theo cùng độ trễ, thứ tự hoặc mức độ đầy đủ. Hệ thống cần cân nhắc fallback polling file metadata, reconciliation và báo trạng thái không hỗ trợ thay vì retry vô hạn.

### 14.6. Shutdown hook không phải nguồn đảm bảo duy nhất

JVM shutdown hook hữu ích để yêu cầu đóng tài nguyên khi kết thúc thông thường, nhưng không nên dựa vào nó làm cơ chế duy nhất để bảo đảm dữ liệu đã ghi xong: không phải mọi cách tiến trình bị chấm dứt đều chạy hook thành công. Phần mềm nên có **lifecycle shutdown rõ ràng ngay trong ứng dụng**.

### 14.7. Không dùng `System.exit` để giải quyết một thread stuck

Gọi `System.exit` vì không biết cách đánh thức `take()` là lựa chọn quá rộng, có thể bỏ qua cleanup hoặc hủy tác vụ khác. Thay vào đó, dùng `watcher.close` hoặc interruption đúng scope, rồi chờ thread theo deadline và quản lý lỗi.

## 15. Bảng lỗi hiểu sai thường gặp

| Nhận định sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Đặt `running=false` sẽ đánh thức `take` | Biến không giải phóng blocking call | Dùng close/interrupt hoặc timed poll |
| `take()` trả `null` khi không có event | Nó chờ thay vì timeout | Nếu cần timeout, dùng `poll(timeout,unit)` |
| `poll(timeout)==null` nghĩa watcher bị đóng | Chỉ hết hạn chờ | Phân biệt timeout và ClosedWatchServiceException |
| `WatchService.close` chỉ hủy một key | Nó đóng toàn bộ service | Dùng `key.cancel` để hủy một registration |
| `key.cancel` luôn đánh thức thread đang take | Không phải tín hiệu shutdown tổng quát | Dùng close/interrupt |
| `key.reset` giúp thoát take | Reset quản lý vòng đời signal của key | Chọn cơ chế đánh thức thực sự |
| `interrupt()` cũng đóng WatchService | Không tự đóng watcher | Owner vẫn cần đóng khi hết lifecycle |
| `InterruptedException` không cần xử lý status | Có thể mất tín hiệu hủy | Rethrow hoặc restore interrupt rồi dừng |
| `ClosedWatchServiceException` là `IOException` | Đây là unchecked exception | Bắt/nhận diện riêng ở worker boundary |
| `close` đồng nghĩa worker đã kết thúc | Thread cần chạy catch/finally/join | Chờ worker, kiểm tra timeout |
| `close` đồng nghĩa pending events đã được xử lý hết | Nguồn notification đã đóng, chưa bảo đảm drain | Quản lý queue và đối soát |
| `reset()==true` bảo đảm file đã xử lý xong | Chỉ key vẫn valid | Tách state nghiệp vụ khỏi WatchKey |
| `isValid()==false` luôn vì directory bị xóa | Có thể cancel/close/mất provider | Xem ngữ cảnh và chính sách |
| Hễ catch ClosedWatchServiceException là thành công | Có thể là close bất ngờ | Kiểm tra có stop request hay không |
| `shutdownNow` của executor bảo đảm mọi task đã dừng | Chỉ gửi yêu cầu best effort | awaitTermination và kiểm tra trạng thái |
| Dừng watcher một lần nghĩa là không mất file | Không có notification trong khoảng downtime | Rescan sau restart, xử lý idempotent |
| Bỏ qua `OVERFLOW` vì đã reset key | Reset không khôi phục event đã mất | Đánh dấu dirty và reconcile |
| Dùng loop `poll()` không pause là tối ưu shutdown | Có thể busy spin CPU | Timed poll hoặc blocking wait |
| Cho rằng mọi provider gửi notification như test Windows | Event delivery phụ thuộc file system | Test tích hợp trên môi trường thực |
| Đóng watcher khi một component nhỏ ngừng | Làm các registration khác mất hiệu lực | Xác định ownership/service sharing |
| Chỉ dựa vào shutdown hook | Không bảo đảm ở mọi kiểu dừng tiến trình | Thiết kế lifecycle và recovery |
| Dùng thread stop cưỡng bức | Rủi ro trạng thái không nhất quán | Interruption/close hợp tác |

## 16. Bài tập có đáp án

### Bài 1 — Vì sao vòng lặp không dừng?

Code chỉ dùng `while (!stopRequested.get())` rồi gọi `watcher.take()`. Owner set `stopRequested=true` nhưng không có file thay đổi. Vì sao thread vẫn có thể đứng im?

**Đáp án:** `take()` đang blocking và không nhận thông báo chỉ vì biến đổi cờ. Cần đánh thức bằng `watcher.close()` hoặc `worker.interrupt()`, hoặc đổi sang timed poll để kiểm tra cờ theo chu kỳ.

### Bài 2 — Close và loại exception

Owner đóng `WatchService` khi thread consumer đang `take()`. Loại exception nào consumer cần xử lý?

**Đáp án:** `ClosedWatchServiceException`, một **unchecked** exception. Không coi nó là `IOException` hoặc `InterruptedException`. Nếu đang shutdown có chủ đích, có thể coi đây là tín hiệu thoát worker; nếu watcher đóng bất ngờ thì cần báo lifecycle failure.

### Bài 3 — Interrupt có hủy key không?

Thread consumer đang `watcher.take()` bị `interrupt`. Sau khi catch `InterruptedException`, `key.isValid()` có bắt buộc trở thành false không?

**Đáp án:** Không. Interruption tác động thread chờ, không tự đóng service hoặc cancel registration. Nếu key vẫn valid, watcher có thể được sử dụng bởi consumer khác hoặc tiếp tục theo lifecycle của ứng dụng.

### Bài 4 — Cờ interrupt

Trong catch `InterruptedException`, khi muốn xử lý tại tầng hiện tại rồi thoát thread, vì sao thường gọi `Thread.currentThread().interrupt()`?

**Đáp án:** Vì interrupt status có thể đã được xóa khi phương thức chờ ném `InterruptedException`. Khôi phục status cho tầng điều phối biết yêu cầu hủy đã xảy ra; sau đó **thoát hoặc chuyển điều khiển** đúng hợp đồng.

### Bài 5 — Watcher nhiều thư mục

Một service theo dõi ba directory, chỉ muốn ngừng theo dõi một directory. Dùng `watcher.close()` hay `key.cancel()`?

**Đáp án:** `key.cancel()` cho registration tương ứng, giữ những registration khác nếu service còn dùng. `close()` đóng toàn bộ WatchService.

### Bài 6 — Timed poll trả `null`

`watcher.poll(500, MILLISECONDS)` trả `null`. Có thể kết luận directory đã bị xóa hoặc key invalid không?

**Đáp án:** Không. Nó chỉ cho biết chưa có key được trả trong khoảng chờ đó. Thư mục/key có thể vẫn bình thường.

### Bài 7 — Close đã đủ graceful chưa?

Ứng dụng gọi `watcher.close()` rồi in “đã xử lý xong tất cả tệp” mà không kiểm tra worker/queue. Vấn đề gì?

**Đáp án:** `close` chỉ đóng nguồn notification. Worker đang xử lý, queue downstream và pending events có thể chưa hoàn tất; thiếu đối soát sau downtime. Cần quản lý task, join/await, trạng thái và quy trình reconciliation.

### Bài 8 — Dừng và timeout

Owner gọi `worker.join(3000)` nhưng sau 3 giây `worker.isAlive() == true`. Có thể báo shutdown thành công không?

**Đáp án:** Không theo hợp đồng “worker đã dừng”. Phải báo timeout hoặc áp dụng chính sách escalation, không giả định thread đã kết thúc. Không dùng `Thread.stop` cưỡng bức.

### Bài 9 — Close và interrupt đồng thời

Hai thread lần lượt gọi `watcher.close()` và `worker.interrupt()` gần như cùng lúc. Consumer có chắc luôn nhận `ClosedWatchServiceException` không?

**Đáp án:** Không. Race có thể dẫn đến nhận `InterruptedException` hoặc `ClosedWatchServiceException`, tùy thứ tự diễn ra. Chính sách shutdown nên xử lý cả hai.

### Bài 10 — Restart watcher

Watcher đã đóng vì deploy lại ứng dụng. Có thể sử dụng WatchKey cũ bằng `key.reset()` không?

**Đáp án:** Không. Key gắn với service đã đóng sẽ invalid, reset không làm nó valid lại. Cần tạo WatchService mới, đăng ký directory và đối soát thay đổi trong khoảng không được theo dõi.

### Bài 11 — ExecutorService

Một task watcher đang `take()` trong executor. Caller gọi `executor.shutdown()` rồi thấy thread không thoát. Vì sao?

**Đáp án:** `shutdown()` thường chỉ ngừng nhận task mới, không tự interrupt task đang chạy. Cần cơ chế dừng watcher/task riêng như đóng service, interrupt/cancel phù hợp và `awaitTermination` có timeout.

### Bài 12 — Event bị mất sau close

Vì sao khi restart cần quét lại directory thay vì tin WatchService sẽ replay mọi event xảy ra lúc nó đóng?

**Đáp án:** WatchService là nguồn notification thời gian chạy, không phải transaction log bền vững. Những thay đổi trong khoảng downtime hoặc lúc overflow không tự được replay; quét đối soát và xử lý idempotent giúp xây dựng lại trạng thái.

### Bài 13 — Khác biệt với `reset()`

Một `WatchKey` invalid vì watcher đóng. Gọi `key.reset()` liên tục có giải quyết được không?

**Đáp án:** Không. `reset` quản lý việc signal lại của key còn valid; invalid registration không sống lại bằng reset. Muốn theo dõi lại cần service và key mới.

### Bài 14 — Test hai chiến lược

Vì sao `WatchShutdownDemo` kiểm tra riêng watcher thứ nhất đóng service và watcher thứ hai interrupt thread?

**Đáp án:** Để tách tác động: close vô hiệu hóa registration và làm waiting take kết thúc với ClosedWatchServiceException; interrupt làm thread thoát qua InterruptedException nhưng watcher thứ hai vẫn nhận sự kiện tạo file sau đó.

## 17. Checklist triển khai

- [ ] Xác định watcher thuộc component nào và ai chịu trách nhiệm gọi `close()`.
- [ ] Xác định mong muốn dừng **một key**, **một worker** hay **toàn bộ WatchService**.
- [ ] Nếu dùng `take()`, có cách đánh thức khi stop: `close` hoặc `interrupt`.
- [ ] Nếu dùng timed `poll`, có timeout hợp lý và xử lý kết quả `null` đúng nghĩa.
- [ ] Phân biệt `ClosedWatchServiceException` và `InterruptedException`; không đồng nhất với lỗi thiếu file.
- [ ] Nếu catch `InterruptedException` để thoát, khôi phục interrupt status hoặc truyền exception theo hợp đồng.
- [ ] Không nghĩ `interrupt()` tự đóng watcher hay hủy key.
- [ ] Không nghĩ `cancel()` của một key đóng cả service hoặc luôn đánh thức `take()`.
- [ ] Dùng `key.pollEvents()` và `key.reset()` khi tiếp tục theo dõi, đồng thời xử lý `reset()==false`.
- [ ] Có xử lý `OVERFLOW` và đối soát lại trạng thái khi cần đầy đủ dữ liệu.
- [ ] Đặt cờ `STOP_REQUESTED` trước khi đánh thức worker để phân biệt shutdown có chủ đích.
- [ ] Khi watcher dùng chung nhiều directory, tránh đóng toàn bộ vì một registration.
- [ ] Quản lý worker thread bằng `join`/`awaitTermination` với deadline và kiểm tra có thực sự dừng.
- [ ] Không giữ lock tùy tiện khi chờ worker, tránh deadlock.
- [ ] Quản lý queue/worker downstream; close notification source không bảo đảm xử lý hết công việc.
- [ ] Phân biệt dừng graceful có drain với dừng nhanh có cancellation.
- [ ] Test close khi chờ, interrupt khi chờ, timed poll rỗng, key invalid sau close, key còn valid sau interrupt.
- [ ] Dùng fixture directory tạm, không xóa/sửa file người dùng trong demo.
- [ ] Nếu môi trường không hỗ trợ `WatchService`, có fallback/monitoring phù hợp.
- [ ] Ghi rõ API nền tảng từ Java 7; chương trình hoàn chỉnh dùng cú pháp Java 17 (pattern matching `instanceof`) và biên dịch với `--release 17`.

## 18. Kết luận

Đối với `WatchService` trong Java, một luồng đang `take()` không tự thức dậy khi ta chỉ đổi cờ trạng thái. **`WatchService.close()`** là cơ chế đóng toàn bộ service, làm những key đã đăng ký mất hiệu lực và đánh thức các phép chờ bằng **`ClosedWatchServiceException`**. **`Thread.interrupt()`** là cơ chế yêu cầu hủy **một thread**, có thể làm `take()` ném **`InterruptedException`** nhưng không tự đóng watcher hoặc cancel key. **`poll(timeout, unit)`** là lựa chọn khác để kiểm tra cờ stop có chu kỳ.

Shutdown có kiểm soát còn đòi hỏi **ownership rõ ràng, thông báo ý định dừng, deadline, chờ worker hoàn thành, giải phóng tài nguyên và quản lý event/tác vụ chưa xử lý**. `WatchService` không phải log bền vững để replay mọi thay đổi, nên nếu yêu cầu độ đầy đủ cao cần **rescan/reconciliation** sau restart và overflow. Những nguyên tắc này dùng được từ Java 7 đến Java hiện đại và giúp các hệ thống theo dõi thư mục dừng sạch, ít rò rỉ tài nguyên, không nhầm tín hiệu ngắt thread với lỗi file-system và có hành vi phục hồi rõ ràng.