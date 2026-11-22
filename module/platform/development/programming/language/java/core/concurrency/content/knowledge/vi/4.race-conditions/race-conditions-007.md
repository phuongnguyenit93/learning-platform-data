# TOCTOU và lỗi đồng thời theo thời điểm trong Java

## 1. TOCTOU là gì?

**TOCTOU (Time Of Check To Time Of Use)** là một loại race condition xảy ra khi chương trình **kiểm tra một điều kiện tại thời điểm T1** rồi **dùng kết quả kiểm tra để hành động tại T2**, trong khi trạng thái có thể đã thay đổi giữa hai thời điểm đó.

Ví dụ: kiểm tra “kho còn ít nhất một sản phẩm”, sau đó trừ một sản phẩm. Hai thread đều thấy số lượng là 1; trước khi thread nào trừ, cả hai đều vượt qua phép kiểm tra. Nếu mỗi thread tiếp tục trừ theo kết quả cũ, số lượng có thể xuống -1 và hai yêu cầu đều được chấp nhận dù chỉ có một đơn vị hàng.

```text
Trạng thái ban đầu: stock = 1

Thread A                   Thread B
---------                  ---------
check stock > 0 → true
                           check stock > 0 → true
                           ... trạng thái có thể đổi ...
stock = stock - 1
                           stock = stock - 1

Kết quả có thể sai: hai lượt thành công, stock = -1
```

**Lỗi cốt lõi không nằm ở việc phép kiểm tra sai tại T1**. Kiểm tra có thể hoàn toàn đúng vào lúc thực hiện, nhưng **không còn là căn cứ hợp lệ cho thao tác ở T2**. Độ dài của khoảng cách T1–T2 không cần lớn: một lệnh máy khác, một lần chuyển ngữ cảnh, thao tác I/O hoặc lời gọi phương thức đều có thể mở cơ hội thay đổi trạng thái.

TOCTOU có thể xảy ra giữa các thread trong cùng JVM, giữa các tiến trình, giữa ứng dụng và hệ thống tệp, hoặc giữa nhiều ứng dụng truy cập một tài nguyên chung. Chủ đề bài này là **cơ chế đồng thời nói chung trong Java** và cách xử lý bằng API Java/JDK; không phụ thuộc vào framework.

## 2. Phân biệt TOCTOU với data race và stale read

- **TOCTOU** mô tả lỗi ở cấp **logic kiểm tra–sử dụng**: điều kiện từng đúng nhưng trở nên lỗi thời trước khi hành động. Nó có thể xảy ra ngay cả khi từng phép đọc hoặc ghi riêng lẻ là atomic.
- **Data race theo Java Memory Model** xuất hiện khi hai hành động truy cập cùng biến, ít nhất một hành động ghi, không có quan hệ happens-before thích hợp và không phải đều là thao tác volatile. Data race có thể dẫn tới hành vi quan sát khó suy luận theo mô hình bộ nhớ.
- **Stale read** là việc thread quan sát giá trị cũ hoặc dùng một snapshot đã cũ. Stale read có thể góp phần gây TOCTOU, nhưng không phải tất cả lỗi TOCTOU đều do vi phạm visibility.
- **Atomicity (tính nguyên tử)** ở đây là yêu cầu xem toàn bộ quyết định “nếu hợp lệ thì thực hiện” như **một thao tác logic không bị chen ngang ở điểm có thể làm sai bất biến**.

Ví dụ `AtomicInteger.get()` và `AtomicInteger.decrementAndGet()` đều là thao tác atomic riêng lẻ, nhưng tổ hợp “`get() > 0` rồi `decrementAndGet()`” **không tự trở thành một thao tác atomic**. Tương tự, `volatile` có thể giải quyết visibility cho một biến tín hiệu, nhưng không khóa trạng thái trong khoảng giữa kiểm tra và sử dụng.

Không thể sửa một lỗi TOCTOU chỉ bằng cách đặt `Thread.sleep()`, `Thread.yield()` hoặc tăng priority: các thao tác đó không tạo ra nguyên tử tính cho toàn bộ đoạn quyết định.

## 3. Ví dụ Java 17+: tái hiện lỗi bằng lịch chạy có kiểm soát

Ví dụ dưới đây dùng `CountDownLatch` để **cố ý bảo đảm cả hai thread đều kiểm tra trước khi thread nào thực hiện hành động**. Nhờ vậy đầu ra của phần lỗi được tái hiện xác định thay vì phải “hy vọng” scheduler vô tình tạo ra race.

Tạo tệp `TocTouInventory.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TocTouInventory {

    private static boolean reserveWithCas(AtomicInteger stock) {
        while (true) {
            int observed = stock.get();
            if (observed <= 0) {
                return false;
            }
            if (stock.compareAndSet(observed, observed - 1)) {
                return true;
            }
            // Trạng thái đã đổi: đọc lại và thử lần nữa.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger unsafeStock = new AtomicInteger(1);
        AtomicInteger unsafeAccepted = new AtomicInteger();

        CountDownLatch bothChecked = new CountDownLatch(2);
        CountDownLatch continueAfterCheck = new CountDownLatch(1);

        Runnable unsafeReservation = () -> {
            boolean wasAvailable = unsafeStock.get() > 0;
            bothChecked.countDown();

            try {
                continueAfterCheck.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            if (wasAvailable) {
                unsafeStock.decrementAndGet();
                unsafeAccepted.incrementAndGet();
            }
        };

        Thread a = new Thread(unsafeReservation, "unsafe-A");
        Thread b = new Thread(unsafeReservation, "unsafe-B");
        a.start();
        b.start();

        bothChecked.await();
        continueAfterCheck.countDown();
        a.join();
        b.join();

        System.out.println("Unsafe accepted: " + unsafeAccepted.get());
        System.out.println("Unsafe stock: " + unsafeStock.get());

        AtomicInteger safeStock = new AtomicInteger(1);
        AtomicInteger safeAccepted = new AtomicInteger();

        Runnable safeReservation = () -> {
            if (reserveWithCas(safeStock)) {
                safeAccepted.incrementAndGet();
            }
        };

        Thread c = new Thread(safeReservation, "safe-C");
        Thread d = new Thread(safeReservation, "safe-D");
        c.start();
        d.start();
        c.join();
        d.join();

        System.out.println("CAS accepted: " + safeAccepted.get());
        System.out.println("CAS stock: " + safeStock.get());
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac TocTouInventory.java
java TocTouInventory
```

Khi chương trình hoàn tất bình thường, đầu ra xác định:

```text
Unsafe accepted: 2
Unsafe stock: -1
CAS accepted: 1
CAS stock: 0
```

**Giải thích phần lỗi:**

1. `unsafeStock` khởi đầu bằng 1. Hai thread cùng đọc `unsafeStock.get() > 0` trước khi vượt qua `continueAfterCheck.await()`.
2. `bothChecked.await()` ở `main` bảo đảm cả hai đã lưu `wasAvailable = true`. Sau đó `main` mới mở chốt cho cả hai tiếp tục.
3. Hai lần `decrementAndGet()` đều atomic; vì thế chúng lần lượt đưa số lượng từ 1 xuống 0 rồi -1. Lỗi vẫn xảy ra vì **quyết định có được trừ hay không dựa trên hai kết quả kiểm tra đã cũ**.
4. `unsafeAccepted` trở thành 2. Không có yêu cầu nào bị từ chối mặc dù chỉ tồn tại một đơn vị hàng.

**Giải thích phần sửa:** `compareAndSet(observed, observed - 1)` chỉ ghi khi giá trị hiện tại còn đúng bằng giá trị đã đọc. Nếu thread khác đã thay đổi `stock`, CAS trả về `false`; vòng lặp đọc lại. Chỉ một thread có thể chuyển 1 → 0 thành công; thread còn lại quan sát 0 và trả về `false`. Thao tác làm giảm và điều kiện “đã quan sát giá trị nào” được liên kết ở **điểm tuyến tính hóa (linearization point)** của CAS thành công.

Lưu ý: `safeAccepted.incrementAndGet()` được gọi sau CAS thành công; đây là bộ đếm thống kê của ví dụ. Trong ứng dụng cần cập nhật **nhiều trường dữ liệu như một transaction**, chỉ CAS trên số lượng không tự bảo đảm mọi trường đều cập nhật nguyên tử với nhau.

## 4. Vì sao `check-then-act` nguy hiểm?

Mẫu phổ biến:

```java
if (conditionIsTrue()) {
    performAction();
}
```

Đây là **đoạn minh họa**, chưa có định nghĩa cho hai phương thức. Nó chỉ an toàn khi ít nhất một trong các điều kiện dưới đây được chứng minh:

- Trạng thái liên quan là **bất biến** trong khoảng cần quan sát.
- Chỉ có một tác nhân được phép thay đổi trạng thái trong phạm vi cần xét.
- Có **lock đồng nhất** bảo vệ cả phép kiểm tra và hành động, và mọi tác nhân có quyền sửa đều tuân thủ cùng giao thức lock.
- Có API **atomic check-and-act** (như CAS hoặc `putIfAbsent`) thực hiện quyết định bằng một thao tác có bảo đảm.
- Hệ thống tài nguyên bên ngoài cung cấp giao thức bảo đảm tương đương, chẳng hạn ràng buộc duy nhất hoặc một transaction phù hợp.

Nếu chỉ bảo vệ phép `check` mà thả lock trước `act`, lỗ hổng vẫn còn. Tương tự, **hai khối `synchronized` tách rời** trên cùng monitor chưa chắc đủ nếu giữa chúng có đoạn nhường monitor cho thread khác. Cần bảo vệ **toàn bộ bất biến**, không chỉ từng lời gọi API.

### Ví dụ với `synchronized`

```java
final class Stock {
    private int remaining = 1;

    public synchronized boolean reserveOne() {
        if (remaining == 0) {
            return false;
        }
        remaining--;
        return true;
    }

    public synchronized int remaining() {
        return remaining;
    }
}
```

Đây là **class độc lập có thể dùng trong một chương trình khác**, không có `main`. Khi mọi truy cập cập nhật `remaining` đều đi qua monitor của **cùng đối tượng `Stock`**, check và decrement là một critical section; hai thread tranh cùng đơn vị hàng không thể đều thành công. Với ví dụ này, điều kiện `remaining == 0` đủ vì `remaining` khởi đầu không âm và chỉ giảm qua `reserveOne()`; trong thiết kế tổng quát, dùng `remaining <= 0` phòng trạng thái đầu vào không hợp lệ.

**Giới hạn:** `synchronized` của JVM chỉ phối hợp các thread dùng cùng monitor trong JVM đó. Nó không khóa được tiến trình khác, JVM khác hoặc một dịch vụ bên ngoài không tham gia cùng giao thức.

## 5. TOCTOU với cấu trúc dữ liệu concurrent

Một `ConcurrentHashMap` bảo đảm an toàn cho các thao tác được tài liệu hóa, **không có nghĩa tổ hợp nhiều lời gọi độc lập đều nguyên tử**.

### Cách dễ sai: kiểm tra rồi ghi

```java
// Minh họa, giả sử map đã được khai báo:
if (!map.containsKey("invoice-7")) {
    map.put("invoice-7", "processing");
}
```

Giữa `containsKey` và `put`, thread khác có thể đã đặt cùng key. Hai thread đều tưởng rằng mình là người đầu tiên. Thậm chí khi các thao tác trên map đều thread-safe, **quy tắc “chỉ một người được đăng ký”** vẫn có thể bị vi phạm ở mức logic.

### Cách đúng khi cần đăng ký một key duy nhất

Dùng `putIfAbsent` để gộp phép “chưa có thì đặt” thành thao tác nguyên tử theo key.

Tạo tệp `PutIfAbsentExample.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class PutIfAbsentExample {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> registrations =
                new ConcurrentHashMap<>();
        AtomicInteger winners = new AtomicInteger();

        Runnable register = () -> {
            String previous = registrations.putIfAbsent(
                    "invoice-7", Thread.currentThread().getName());
            if (previous == null) {
                winners.incrementAndGet();
            }
        };

        Thread a = new Thread(register, "A");
        Thread b = new Thread(register, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Successful registrations: " + winners.get());
        System.out.println("Key exists: "
                + registrations.containsKey("invoice-7"));
    }
}
```

Chạy:

```bash
javac PutIfAbsentExample.java
java PutIfAbsentExample
```

Đầu ra:

```text
Successful registrations: 1
Key exists: true
```

Owner thực tế có thể là `A` hoặc `B`, tùy lịch chạy; ví dụ chủ ý **không in owner** vì không thể dự đoán ai thắng. `putIfAbsent` là đúng cho **quy tắc có một giá trị được đăng ký cho key** trong map. Nó không tạo một transaction bao gồm cả các side effect bên ngoài map.

**Cẩn thận với `computeIfAbsent`:** API có thể phù hợp để tạo giá trị theo key, nhưng mapping function không nên thực hiện những tác dụng phụ khó lặp lại, gọi API có thể tái nhập cập nhật map hoặc chạy tác vụ lâu; cần xem hợp đồng cụ thể của `ConcurrentHashMap` và cách xử lý lỗi. Đừng chuyển một quy tắc cần transaction đa tài nguyên thành “một hàm lambda trong map” rồi cho rằng toàn bộ đều atomic.

## 6. TOCTOU với file system: `exists()` rồi thao tác

Đây là một trong những trường hợp điển hình, bởi hệ thống tệp có thể bị thay đổi bởi **process khác**, không chỉ thread trong JVM.

### Cách dễ sai

```java
// Minh họa: path đã được khai báo.
if (!java.nio.file.Files.exists(path)) {
    java.nio.file.Files.writeString(path, "new file");
}
```

Một tiến trình khác có thể tạo `path` **sau** `exists(path)` nhưng **trước** `writeString(path, ...)`. Nếu lời gọi ghi sử dụng tùy chọn mặc định phù hợp với hành vi tạo hoặc cắt ngắn tệp, thao tác có thể tác động lên tệp mà tiến trình khác vừa tạo. Ngược lại, khi `exists(path)` trả về `true`, file có thể đã bị xóa hoặc thay thế ngay trước lần sử dụng.

**Hai lưu ý quan trọng:**

- `Files.exists(path)` trả về `false` không đồng nghĩa chắc chắn “file không tồn tại”: nếu không xác định được sự tồn tại vì lỗi truy cập hoặc I/O, kết quả có thể là `false`. `Files.notExists(path)` không phải phủ định logic tuyệt đối của `exists(path)`; cả hai có thể cùng `false`.
- Việc kiểm tra quyền, loại file, thuộc tính, tên đích hoặc symbolic link trước một thao tác sau đó cũng có thể tạo TOCTOU khi đối tượng tại đường dẫn bị thay thế.

### Dùng thao tác nguyên tử “chỉ tạo nếu chưa tồn tại”

Trong Java NIO, `Files.createFile(path)` yêu cầu việc kiểm tra file chưa tồn tại và tạo file là một thao tác atomic đối với các hoạt động hệ thống tệp có thể tác động tới thư mục theo hợp đồng API. Nếu file đã tồn tại, `FileAlreadyExistsException` là kết quả cần xử lý, thay vì tự kiểm tra trước rồi ghi.

Tạo tệp `CreateOnlyOnce.java`:

```java
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateOnlyOnce {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("toc-demo-");
        Path file = directory.resolve("receipt.txt");

        try {
            Files.createFile(file);
            System.out.println("First creation succeeded");

            try {
                Files.createFile(file);
                System.out.println("Unexpected duplicate");
            } catch (FileAlreadyExistsException e) {
                System.out.println("Duplicate rejected");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CreateOnlyOnce.java
java CreateOnlyOnce
```

Đầu ra nếu hệ thống tệp cho phép các thao tác và không có tác nhân bên ngoài can thiệp vào thư mục tạm:

```text
First creation succeeded
Duplicate rejected
```

Ví dụ tạo **thư mục tạm mới**, không thao tác trên file thật của người học. Việc dọn dẹp có thể ném `IOException` nếu môi trường không cho xóa hoặc file bị thay đổi; đó là lỗi I/O cần xử lý theo yêu cầu ứng dụng.

Nếu mục tiêu là mở file **chỉ khi file chưa tồn tại**, `StandardOpenOption.CREATE_NEW` trong API mở kênh/ghi file có ngữ nghĩa tạo mới có điều kiện tương tự. Nếu cần cập nhật nội dung nhiều bước, việc “tạo tên duy nhất” **không** tự biến mọi lần ghi tiếp theo thành transaction. Cần thiết kế ghi tạm, xác nhận, commit, đồng bộ và xử lý lỗi theo ngữ nghĩa mong muốn.

### TOCTOU có yếu tố bảo mật

Giả sử chương trình kiểm tra một đường dẫn nằm trong thư mục cho phép rồi mới mở file. Nếu giữa hai thao tác có người thay đổi liên kết hoặc thành phần đường dẫn, chương trình có thể sử dụng **đối tượng khác** với đối tượng đã kiểm tra. Đây là vấn đề **check-path-then-open**, có thể nghiêm trọng khi mã có quyền truy cập file lớn hơn người điều khiển đường dẫn.

Biện pháp phụ thuộc hệ điều hành và nhà cung cấp file system: giới hạn quyền thư mục, không tin path do đối tượng không tin cậy kiểm soát, ưu tiên thao tác gắn với **đối tượng đã mở** hoặc directory handle thay vì kiểm tra tên rồi mở lại, sử dụng lựa chọn không theo symbolic link khi phù hợp, và cân nhắc `SecureDirectoryStream` nếu provider có hỗ trợ. `NOFOLLOW_LINKS` trên **một** phép kiểm tra hoặc thao tác không mặc nhiên làm an toàn toàn bộ chuỗi thao tác đa bước; cần xét cả thành phần đường dẫn, quyền sửa thư mục và phạm vi bảo đảm của API.

## 7. TOCTOU khi nhiều process hoặc dịch vụ cùng dùng tài nguyên

Lock trên đối tượng Java giải quyết tranh chấp giữa những thread **cùng tuân thủ lock đó** trong cùng JVM. Nó không tự cung cấp điều kiện atomic xuyên JVM hoặc xuyên dịch vụ.

Các ví dụ thường gặp:

| Quy tắc nghiệp vụ | Cách kiểm tra rồi hành động dễ lỗi | Điểm bảo đảm cần có |
| --- | --- | --- |
| Một định danh chỉ được tạo một lần | `exists(id)` rồi `insert(id)` | Ràng buộc unique, ghi có điều kiện hoặc giao thức atomic của nơi lưu trữ |
| Không bán quá số lượng tồn | `read(stock) > 0` rồi `write(stock-1)` | Atomic conditional update, compare-and-swap hoặc transaction phù hợp |
| Mỗi job chỉ một worker nhận | `isPending(job)` rồi `markRunning(job)` | Atomic claim có điều kiện, lease hoặc cơ chế queue có bảo đảm |
| File chỉ được tạo một lần | `Files.exists` rồi `writeString` | Atomic create-if-absent như `createFile` hoặc `CREATE_NEW` |
| Một người dùng được truy cập tài nguyên | `checkPermission` rồi sử dụng handle/tài nguyên | Quyền được kiểm tra ở thao tác có hiệu lực hoặc trên đối tượng đã xác định |

Một **transaction** chỉ có ích nếu mức cô lập, lock, điều kiện cập nhật và ràng buộc của nơi lưu trữ thực sự bảo vệ bất biến. Không thể kết luận “đã ở trong transaction” là hết TOCTOU mà không xem chính xác loại thao tác và mức isolation.

**Idempotency** và unique key cũng có tác dụng hữu ích đối với xử lý retry; tuy nhiên idempotency cần được áp dụng tại điểm ghi hoặc tại nơi được dùng làm nguồn chân lý. Một cache kiểm tra rồi gửi request không bảo đảm ngăn trùng tác vụ nếu nhiều tác nhân đồng thời.

## 8. Cách lựa chọn cơ chế khắc phục

### 8.1. Gộp phép kiểm tra và hành động thành một thao tác atomic

Đây thường là cách rõ ràng nhất nếu API hỗ trợ:

- `AtomicInteger.compareAndSet(expected, update)` hoặc `AtomicReference.compareAndSet(...)` khi cập nhật một trạng thái đơn có thể biểu diễn bằng giá trị/đối tượng atomic.
- `ConcurrentHashMap.putIfAbsent`, `replace(key, expected, newValue)`, `compute` hoặc `merge` khi cập nhật theo key trong map, tuân theo hợp đồng cụ thể của từng API.
- `Files.createFile` hoặc mở với `CREATE_NEW` khi cần tạo file nếu chưa tồn tại.
- Conditional update hoặc unique constraint của chính tài nguyên bên ngoài khi có nhiều JVM/process.

Một phép atomic giải quyết **đúng bất biến nó bao phủ**. CAS trên một trường không bảo đảm atomic cho đồng thời một file, một request mạng và một bản ghi khác.

### 8.2. Giữ lock xuyên toàn bộ đoạn quyết định

Nếu một đối tượng mutable có nhiều trường liên quan, dùng cùng một `synchronized` monitor hoặc `Lock` để bảo vệ check và update có thể đơn giản hơn việc cố ghép nhiều atomic variables. Tất cả đường ghi phải tuân theo cùng cơ chế; nếu có tác nhân bên ngoài thay đổi dữ liệu, lock cục bộ không đủ.

Trong đoạn critical section, hạn chế I/O chậm hoặc gọi code không kiểm soát để tránh giữ lock quá lâu, tăng tranh chấp hoặc tạo deadlock. Đừng “tách khóa” bằng cách mở khóa giữa check và update nếu chưa có cơ chế xác thực lại khi cập nhật.

### 8.3. Dùng version hoặc optimistic concurrency

Khi một đối tượng có nhiều trường, có thể đọc trạng thái kèm **version**, chuẩn bị thay đổi và chỉ ghi nếu version vẫn khớp. Nếu thất bại, đọc lại và thử lại theo giới hạn. Đây là cơ chế lạc quan dựa trên **điểm cập nhật có điều kiện** ở nguồn chân lý; chỉ so sánh version trong JVM rồi ghi không điều kiện vào hệ thống ngoài vẫn có TOCTOU.

### 8.4. Xử lý trường hợp điều kiện không còn đúng

TOCTOU không biến mất nếu chỉ phát hiện lỗi rồi tiếp tục như thành công. Phải định nghĩa:

1. Khi claim thất bại: trả thông báo “đã có người nhận”, retry với dữ liệu mới, hay bỏ qua?
2. Khi timeout hoặc interrupt: có thể xác định thao tác đã xảy ra chưa; có cần reconcile?
3. Khi phát sinh side effect một phần: có cơ chế rollback, bù trừ hoặc idempotency không?
4. Khi nhiều tài nguyên tham gia: bất biến nằm ở đâu, tác nhân nào có quyền thay đổi, và thao tác nào quyết định thành công?

Đối với CAS loop, tránh retry vô hạn nếu yêu cầu có thời hạn và áp lực cạnh tranh cao; đo độ tranh chấp và dùng backoff/giới hạn phù hợp khi cần.

## 9. Kiểm thử và phát hiện TOCTOU

Lỗi timing thường hiếm xuất hiện ở máy phát triển nhưng bùng phát khi tăng tải. **Không thể chứng minh chương trình hết race chỉ bằng việc chạy một lần hoặc thêm `sleep()`.**

Cách kiểm thử có giá trị:

1. Xác định **bất biến** cần giữ: số lượng không âm, mỗi key có tối đa một chủ sở hữu, file không bị ghi đè, chỉ người có quyền được sử dụng tài nguyên.
2. Liệt kê **khe thời gian**: sau khi đọc trạng thái, sau khi kiểm tra điều kiện, trước khi ghi hoặc trước khi mở file.
3. Dùng `CountDownLatch`/`CyclicBarrier` trong test để buộc các thread tiến đến cùng một mốc rồi mới tiếp tục, giống ví dụ tồn kho.
4. Thực hiện stress tests trên nhiều thread và nhiều kích thước đầu vào; theo dõi sai bất biến, ngoại lệ, bế tắc, throughput và tỉ lệ retry.
5. Với hệ thống ngoài JVM, thử **nhiều tiến trình độc lập** cùng truy cập, kể cả trên file system hoặc nơi lưu trữ tương ứng. Lock cục bộ không mô phỏng được các tác nhân ngoài.
6. Kiểm tra từng cơ chế khắc phục ở **điểm atomic thực tế**, thay vì chỉ tin vào tên phương thức “thread-safe”. Phải xem cả toàn bộ chuỗi logic.
7. Dùng JFR, thread dump, logging có thread name và thông tin tranh chấp để tìm đường chạy; nhưng không dựa vào log để bắt buộc thứ tự thực thi, vì quan sát cũng có thể thay đổi timing.

Ví dụ `CountDownLatch` trong bài tạo lịch xen kẽ **có chủ đích**, giúp test TOCTOU lặp lại được. Tập hợp kiểm thử vẫn chỉ bổ trợ cho thiết kế đúng; chứng cứ mạnh nhất đến từ việc chứng minh bất biến được bảo vệ bởi một thao tác/giao thức có bảo đảm.

## 10. Những sai lầm thường gặp

- **“Đã dùng `AtomicInteger` nên không có TOCTOU.”** Sai nếu check và act là hai thao tác atomic riêng: `get()` rồi `decrementAndGet()` vẫn có khe thời gian.
- **“Đã dùng `ConcurrentHashMap` nên `containsKey` rồi `put` là atomic.”** Sai: an toàn của từng phương thức không tự hợp thành tính nguyên tử cho cặp lời gọi.
- **“Thêm `volatile` là đủ.”** `volatile` xử lý visibility/order nhất định, không biến mọi logic nhiều bước thành atomic.
- **“Chèn `sleep(100)` sẽ tránh race.”** Sleep thay đổi lịch chạy, có thể che lỗi hoặc làm lỗi dễ xảy ra hơn; nó không bảo vệ bất biến.
- **“Bọc mỗi bước trong `synchronized` riêng là đủ.”** Sai nếu lock được thả giữa check và act; thread khác có thể sửa trạng thái trong khoảng hở.
- **“Lock Java xử lý được tác nhân ngoài JVM.”** Sai: process khác không bị ràng buộc bởi monitor Java cục bộ.
- **“`Files.exists(path)` bảo đảm lần mở tiếp theo dùng đúng file đó.”** Sai: đối tượng tại đường dẫn có thể thay đổi hoặc không thể kiểm tra chính xác.
- **“Thử lại ngay là vô hại.”** Retry có thể tạo side effect trùng nếu không biết lần đầu đã commit hay chưa; cần idempotency và giao thức xác nhận rõ.
- **“Không thấy lỗi trong 10.000 lần chạy thì an toàn.”** Không đủ: lịch chạy khác và workload khác vẫn có thể lộ race.

## 11. Checklist áp dụng vào mã Java

Trước bất kỳ đoạn **check → use**, tự hỏi:

1. **Trạng thái nào đang được kiểm tra?** Đó là biến trong JVM, một map, file, bản ghi hay tài nguyên dịch vụ?
2. **Ai có thể thay đổi nó?** Thread cùng JVM, process khác, hệ thống tệp, dịch vụ từ xa hay người dùng khác?
3. **Khoảng T1–T2 có cho phép thay đổi không?** Nếu có, kết quả kiểm tra đã cũ có gây vi phạm bất biến không?
4. **Điểm atomic nằm ở đâu?** CAS, `synchronized` xuyên toàn bộ đoạn, `putIfAbsent`, create-if-absent, unique constraint hay conditional update?
5. **Các thành phần cùng tham gia có dùng đúng giao thức đó không?** Một khóa cục bộ không bảo vệ một tài nguyên do bên ngoài quản lý.
6. **Khi tranh chấp hoặc thất bại sẽ làm gì?** Retry, từ chối, timeout, rollback, bù trừ, idempotency và kiểm tra lại kết quả.
7. **Có kiểm thử chứng minh bất biến không?** Cố ý tạo interleaving, stress test, và kiểm tra hiệu quả dưới nhiều tác nhân.

**Ghi nhớ:** một điều kiện **đúng lúc kiểm tra** không bảo đảm còn đúng **lúc sử dụng**. Sửa TOCTOU bằng cách bảo vệ **toàn bộ quyết định** tại nơi sở hữu trạng thái và xử lý trường hợp điều kiện thay đổi, thay vì cố đoán hoặc điều khiển tốc độ scheduler.