# Hạ cấp từ khóa ghi sang khóa đọc

## 1. Hạ cấp giải quyết tình huống nào?

Giả sử một luồng vừa cập nhật dữ liệu dùng chung và muốn tiếp tục kiểm tra hoặc xử lý dữ liệu vừa cập nhật. Trong lúc cập nhật, nó cần quyền ghi độc quyền; sau đó, nó chỉ cần bảo đảm dữ liệu không bị luồng khác sửa.

Giữ khóa ghi suốt cả hai giai đoạn sẽ chặn cả những luồng chỉ muốn đọc. Nhả khóa ghi rồi mới xin khóa đọc lại tạo ra một khoảng trống: một luồng ghi khác có thể chen vào, làm dữ liệu thay đổi trước khi luồng ban đầu đọc tiếp.

**Hạ cấp khóa (lock downgrading)** giải quyết tình huống này bằng cách chuyển từ giữ khóa ghi sang chỉ giữ khóa đọc, với một đoạn chồng lấp:

1. Luồng đang giữ khóa ghi.
2. Chính luồng đó lấy thêm khóa đọc, trong khi vẫn giữ khóa ghi.
3. Luồng nhả khóa ghi nhưng tiếp tục giữ khóa đọc.
4. Sau khi đọc xong, luồng nhả khóa đọc.

Nhờ không có khoảng thời gian bỏ toàn bộ quyền bảo vệ, luồng ghi khác không thể chen vào giữa bước cập nhật và giai đoạn đọc được bảo vệ. Khi khóa ghi đã được nhả, các luồng đọc khác có thể cùng đọc theo chính sách cấp khóa.

Bài này dùng `ReentrantReadWriteLock`. Đây là lớp triển khai cụ thể của `ReadWriteLock` cho phép luồng sở hữu khóa ghi lấy khóa đọc. Không nên suy rộng khả năng hạ cấp này cho mọi lớp triển khai `ReadWriteLock`: giao diện không cung cấp một phương thức chuyển đổi khóa chung và yêu cầu kiểm tra hợp đồng của từng lớp triển khai.

## 2. Ba trạng thái cần phân biệt

| Giai đoạn | Khóa do luồng hiện tại giữ | Luồng khác có thể ghi? | Luồng khác có thể đọc? |
|---|---|---|---|
| Đang cập nhật | Ghi | Không | Không |
| Vừa lấy thêm khóa đọc | Ghi và đọc | Không | Không, vì khóa ghi vẫn được giữ |
| Đã hạ cấp xong | Đọc | Không | Có thể, theo chính sách cấp khóa |
| Đã đọc xong | Không còn giữ khóa | Có thể tranh quyền | Có thể tranh quyền |

Hạ cấp không làm khóa ghi tự biến thành khóa đọc. Hai đối tượng khóa vẫn có cách lấy và nhả riêng. Ta chủ động tạo trạng thái giữ đồng thời cả hai, rồi nhả quyền ghi.

Cũng không có một lần gọi `unlock()` nào tự nhả cả hai khóa. Mỗi lần lấy khóa thành công phải được cân bằng bằng lần nhả đúng loại khóa, trên đúng luồng sở hữu.

### Thứ tự đúng và khoảng trống bảo vệ

Mã minh họa thứ tự đúng:

```text
write.lock()
    cập nhật dữ liệu
    read.lock()       ← vẫn đang giữ write
write.unlock()
    xử lý chỉ đọc
read.unlock()
```

Thứ tự sau **không bảo đảm giữ nguyên phiên bản dữ liệu giữa hai giai đoạn**:

```text
write.lock()
    cập nhật dữ liệu
write.unlock()
    ← một luồng ghi khác có thể chen vào đây
read.lock()
    đọc dữ liệu, có thể đã là phiên bản khác
read.unlock()
```

Trường hợp thứ hai vẫn có thể dùng khóa hợp lệ cho từng giai đoạn riêng. Vấn đề nằm ở yêu cầu liên tục: nếu cần đọc đúng trạng thái mình vừa tạo ra, khoảng trống đó phá vỡ yêu cầu.

## 3. Mẫu mã hạ cấp với try/finally

Đoạn dưới minh họa cấu trúc bên trong một phương thức, không phải chương trình độc lập:

```java
writeLock.lock();
try {
    updateSharedState();
    readLock.lock();
} finally {
    writeLock.unlock();
}

try {
    inspectSharedState();
} finally {
    readLock.unlock();
}
```

Hai phần `try/finally` có vai trò khác nhau:

- Phần đầu bảo đảm nhả khóa ghi, kể cả khi cập nhật thất bại.
- Nếu cập nhật thất bại trước khi lấy khóa đọc, ngoại lệ truyền ra; chương trình không đi tiếp vào phần đọc.
- Khi phần đầu hoàn tất bình thường, luồng đã giữ khóa đọc; phần thứ hai bảo đảm nhả khóa đọc nếu xử lý đọc gặp ngoại lệ.

Đặt giai đoạn đọc ngay sau cấu trúc nhả khóa ghi. Không chèn một lời gọi có thể ném ngoại lệ vào khoảng giữa khi đã giữ khóa đọc nhưng chưa vào `try/finally` bảo vệ việc nhả khóa đọc.

`finally` bảo đảm giải phóng khóa, nhưng không hoàn tác dữ liệu. Nếu cập nhật có thể thất bại giữa chừng, mã cập nhật còn phải giữ các điều kiện nhất quán của dữ liệu, chẳng hạn chuẩn bị kết quả mới trong biến cục bộ rồi mới thay thế trạng thái dùng chung.

Mẫu trên giả định luồng vào phương thức chưa giữ thêm các lượt khóa ghi khác. Nếu trước đó luồng đã lấy khóa ghi nhiều lần do tái nhập, nhả một lượt chưa chắc đã hết quyền ghi. Phải cân bằng toàn bộ số lượt lấy khóa ghi mà thiết kế yêu cầu nhả thì các luồng đọc khác mới có cơ hội vào.

## 4. Chương trình kiểm chứng trạng thái sau khi hạ cấp

Chương trình sau cập nhật giá trị thành `42`, lấy khóa đọc trước khi nhả khóa ghi, rồi dùng một luồng khác kiểm tra hai việc:

- Luồng khác lấy được khóa đọc và thấy giá trị `42`.
- Luồng khác chưa lấy được khóa ghi khi luồng chính còn giữ khóa đọc.

Sau khi luồng chính nhả khóa đọc, luồng làm việc lấy khóa ghi và cập nhật thành `43`.

Lưu thành `DowngradeDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class DowngradeDemo {
    private static final ReentrantReadWriteLock RW =
            new ReentrantReadWriteLock();
    private static final Lock READ = RW.readLock();
    private static final Lock WRITE = RW.writeLock();
    private static int value;

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            WRITE.lock();
            try {
                value = 42;
                READ.lock();
            } finally {
                WRITE.unlock();
            }

            try {
                System.out.println("main.writeHeld="
                        + RW.isWriteLockedByCurrentThread());
                System.out.println("main.readHolds="
                        + RW.getReadHoldCount());

                String readerResult = worker.submit(() -> {
                    if (!READ.tryLock()) {
                        return "reader.blocked";
                    }
                    try {
                        return "reader.value=" + value;
                    } finally {
                        READ.unlock();
                    }
                }).get();
                System.out.println(readerResult);

                boolean writerAcquired = worker.submit(() -> {
                    if (!WRITE.tryLock()) {
                        return false;
                    }
                    try {
                        return true;
                    } finally {
                        WRITE.unlock();
                    }
                }).get();
                System.out.println("writer.acquired=" + writerAcquired);
            } finally {
                READ.unlock();
            }

            int updated = worker.submit(() -> {
                WRITE.lock();
                try {
                    value = 43;
                    return value;
                } finally {
                    WRITE.unlock();
                }
            }).get();
            System.out.println("afterRelease.value=" + updated);
        } finally {
            worker.shutdown();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 DowngradeDemo.java
java DowngradeDemo
```

Stdout:

```text
main.writeHeld=false
main.readHolds=1
reader.value=42
writer.acquired=false
afterRelease.value=43
```

Kết quả có thứ tự xác định vì luồng chính chờ từng tác vụ hoàn tất bằng `get()`, và chỉ luồng chính in ra màn hình. Tác vụ thử ghi dùng `tryLock()` nên trả kết quả ngay; nó không bị treo chờ khóa đọc mà luồng chính đang giữ.

Nếu thay phép thử đó bằng `WRITE.lock()` rồi vẫn gọi `get()` trong lúc luồng chính giữ khóa đọc, ta tạo ra vòng chờ: luồng chính chờ tác vụ hoàn tất, còn tác vụ chờ luồng chính nhả khóa đọc. Không cần đổi khóa trên cùng một luồng mới có thể tạo ra bế tắc.

Các phương thức như `getReadHoldCount()` phục vụ giải thích/quan sát ở đây. Trong ứng dụng, không dùng kết quả quan sát trạng thái khóa để thay cho thao tác lấy khóa: trạng thái có thể thay đổi giữa lúc kiểm tra và lúc hành động.

## 5. Hạ cấp trong bộ nhớ đệm: đọc → ghi → đọc

Một trường hợp thường gặp là bộ nhớ đệm có dữ liệu hợp lệ hoặc đã bị đánh dấu cần nạp lại:

- Phần lớn lời gọi chỉ đọc, nên bắt đầu bằng khóa đọc.
- Nếu dữ liệu không còn hợp lệ, phải nhả khóa đọc trước khi lấy khóa ghi.
- Sau khi lấy được khóa ghi, phải kiểm tra lại tính hợp lệ.
- Nếu cần, nạp dữ liệu mới dưới khóa ghi.
- Lấy khóa đọc khi vẫn giữ khóa ghi, sau đó nhả khóa ghi.
- Sử dụng dữ liệu dưới khóa đọc hoặc tạo ảnh chụp an toàn để trả về.

Điểm dễ nhầm: **đọc → ghi** và **ghi → đọc** trong chuỗi này có cách xử lý khác nhau. Với `ReentrantReadWriteLock`, không giữ khóa đọc rồi chờ lấy khóa ghi. Nhưng khi đang giữ khóa ghi, luồng có thể lấy khóa đọc để hạ cấp.

### Vì sao phải kiểm tra lại sau khi lấy khóa ghi?

Giả sử A và B cùng thấy dữ liệu hết hạn dưới khóa đọc. Cả hai nhả khóa đọc để xin khóa ghi. A được quyền trước, nạp dữ liệu và hạ cấp. Khi B cuối cùng lấy được khóa ghi, dữ liệu có thể đã hợp lệ.

Nếu B chỉ dựa trên lần kiểm tra cũ, nó sẽ nạp lại không cần thiết, hoặc ghi đè một kết quả mới hơn tùy nghiệp vụ. Vì đã có một khoảng trống khi chuyển từ đọc sang ghi, quyết định ghi phải được kiểm tra lại trong vùng ghi độc quyền.

Khoảng trống đó thuộc chiều đọc → ghi. Chiều hạ cấp ghi → đọc vẫn dùng đoạn giữ chồng lấp để bảo vệ liên tục.

### Chương trình bộ nhớ đệm

Lưu thành `DowngradedCacheDemo.java`:

```java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class DowngradedCacheDemo {
    private record Snapshot(int version, String text) {
    }

    private static final class Cache {
        private final ReentrantReadWriteLock rw =
                new ReentrantReadWriteLock();
        private final Lock read = rw.readLock();
        private final Lock write = rw.writeLock();

        // All accesses to these fields use the associated locks.
        private boolean valid;
        private int generation;
        private Snapshot current;

        Snapshot readSnapshot() {
            read.lock();

            if (!valid) {
                read.unlock();
                write.lock();
                try {
                    // Another writer may already have refreshed the cache.
                    if (!valid) {
                        int nextGeneration = generation + 1;
                        Snapshot loaded = new Snapshot(
                                nextGeneration, "data-" + nextGeneration);
                        current = loaded;
                        generation = nextGeneration;
                        valid = true;
                    }

                    // Downgrade: acquire read before releasing write.
                    read.lock();
                } finally {
                    write.unlock();
                }
            }

            try {
                // Snapshot contains only immutable components.
                return new Snapshot(current.version(), current.text());
            } finally {
                read.unlock();
            }
        }

        void invalidate() {
            write.lock();
            try {
                valid = false;
            } finally {
                write.unlock();
            }
        }
    }

    public static void main(String[] args) {
        Cache cache = new Cache();

        Snapshot first = cache.readSnapshot();
        Snapshot second = cache.readSnapshot();
        cache.invalidate();
        Snapshot third = cache.readSnapshot();

        System.out.println("first=" + first.version() + ":" + first.text());
        System.out.println("second=" + second.version() + ":" + second.text());
        System.out.println("third=" + third.version() + ":" + third.text());
    }
}
```

Lệnh chạy:

```shell
javac --release 17 DowngradedCacheDemo.java
java DowngradedCacheDemo
```

Stdout:

```text
first=1:data-1
second=1:data-1
third=2:data-2
```

Lời gọi thứ hai đọc dữ liệu đang hợp lệ nên không tăng phiên bản. Sau `invalidate()`, lời gọi thứ ba tạo phiên bản mới.

Trong `readSnapshot()`, nếu phần tạo dữ liệu mới ném ngoại lệ trước khi lấy lại khóa đọc, `finally` nhả khóa ghi rồi ngoại lệ truyền ra. Luồng không chạy đến `try/finally` ở phần trả kết quả, vì vậy không nhả nhầm khóa đọc đã được nhả trước đó.

Chương trình `main` minh họa kết quả chức năng theo thứ tự; nó không phải phép thử bao phủ mọi cách xen kẽ luồng. Cơ chế đồng thời dựa vào khóa và lần kiểm tra lại dưới khóa ghi.

Bản ghi `Snapshot` ở đây chứa `int` và `String`, nên dữ liệu trả ra có thể sử dụng sau khi nhả khóa. Một `record` có trường `List` hay đối tượng sửa được không tự trở thành bất biến sâu; cần sao chép phù hợp hoặc một hợp đồng sở hữu rõ ràng.

Ví dụ cố ý giữ cùng đường đọc cho cả dữ liệu có sẵn và dữ liệu vừa nạp để thể hiện mẫu hạ cấp. Nếu toàn bộ trạng thái đã là một đối tượng bất biến và chỉ cần trả tham chiếu, có thể thiết kế đường ghi trả luôn kết quả bất biến sau khi nhả khóa ghi; khi đó không nhất thiết cần một giai đoạn hạ cấp.

## 6. Quy tắc nhìn thấy dữ liệu và phạm vi bảo vệ

Cặp khóa đọc/ghi gắn với cùng một `ReentrantReadWriteLock` không chỉ điều phối quyền truy cập. Hợp đồng `ReadWriteLock` còn bảo đảm rằng luồng lấy thành công khóa đọc thấy được các cập nhật xảy ra trước lần nhả khóa ghi trước đó.

Trong chuỗi hạ cấp:

- Luồng đang cập nhật giữ quyền ghi độc quyền.
- Nó lấy khóa đọc trước khi nhả khóa ghi, nên luôn còn quyền bảo vệ dữ liệu.
- Luồng đọc khác khi vào sau lúc nhả khóa ghi nhìn thấy trạng thái được công bố qua cơ chế khóa.
- Chừng nào khóa đọc hạ cấp còn được giữ, luồng ghi khác không được cấp quyền ghi.

Các bảo đảm này đòi hỏi mọi đường truy cập trạng thái dùng chung tuân thủ cùng một quy tắc. Nếu một phương thức sửa dữ liệu bỏ qua khóa, việc hạ cấp ở phương thức khác không ngăn được đường sửa đó.

Không cần thêm `volatile` cho từng trường chỉ vì nhiều luồng sử dụng, nếu mọi truy cập đã được bảo vệ đúng bằng cặp khóa này. Ngược lại, thêm `volatile` cho một cờ không tự bảo vệ tính nhất quán của cả một nhóm trường.

Sau khi nhả khóa đọc, không còn quyền yêu cầu dữ liệu dùng chung giữ nguyên. Có thể dùng tiếp một ảnh chụp bất biến đã lấy ra; không nên trả một cấu trúc sửa được rồi mặc nhiên cho rằng khóa đã bảo vệ mọi lần sử dụng về sau.

## 7. Những lỗi thường gặp

### Lấy khóa đọc sau khi đã nhả khóa ghi

Không có gì buộc trạng thái còn giống lúc vừa cập nhật. Nếu cần sự liên tục, đổi thứ tự để lấy khóa đọc trước khi nhả khóa ghi.

Nếu yêu cầu chỉ là “đọc trạng thái mới nhất tại thời điểm lấy được khóa đọc”, khoảng trống có thể chấp nhận được. Cần xác định yêu cầu trước khi chọn mẫu.

### Giữ khóa đọc rồi lấy khóa ghi

`ReentrantReadWriteLock` cho phép luồng sở hữu khóa ghi lấy khóa đọc; chiều ngược lại không có cơ chế nâng cấp trực tiếp. Luồng chỉ giữ khóa đọc mà gọi `writeLock().lock()` sẽ không thể tiến tiếp trong khi vẫn giữ lượt đọc đó.

Để chuyển sang ghi, phải nhả các lượt đọc mà mình đang giữ, lấy khóa ghi và kiểm tra lại điều kiện. Không dùng `tryLock()` trong vòng lặp mà vẫn giữ khóa đọc để “đợi nâng cấp”: làm vậy không loại bỏ rào cản do chính lượt đọc đang giữ tạo ra.

### Tiếp tục sửa dữ liệu sau khi đã hạ cấp

Sau khi nhả hết lượt ghi, luồng chỉ còn quyền đọc. Các luồng đọc khác có thể đang đọc đồng thời, nên sửa dữ liệu trong giai đoạn này vi phạm giao thức.

Các thao tác có vẻ là đọc nhưng âm thầm sửa trạng thái, chẳng hạn cập nhật bộ đếm dùng chung hoặc làm mới một trường lười, cũng phải được xem xét. Không đặt chúng dưới khóa đọc chỉ vì tên phương thức có chữ “get”.

### Nhả khóa đọc trên luồng khác

Khóa thuộc quyền sở hữu của luồng đã lấy nó. Không lấy khóa ở luồng A rồi giao `unlock()` cho tác vụ chạy ở luồng B. Mẫu hạ cấp phải giữ các lần lấy/nhả tương ứng trên cùng luồng.

### Giữ khóa đọc quá lâu sau khi hạ cấp

Hạ cấp cho phép các luồng đọc khác cùng vào, nhưng vẫn chặn luồng ghi. Nếu xử lý đọc chạy lâu, gọi mạng, đợi tác vụ khác hoặc gọi mã ngoài có thể lấy thêm khóa, thời gian chờ ghi vẫn có thể lớn hoặc xuất hiện vòng chờ.

Khi có thể, tạo một ảnh chụp bất biến dưới khóa rồi nhả khóa để xử lý tiếp ngoài vùng bảo vệ. Đây là lựa chọn thiết kế khác với yêu cầu đọc liên tục trên trạng thái dùng chung.

### Cho rằng chế độ công bằng biến hạ cấp thành xếp hàng lại

Hạ cấp dựa vào quyền tái nhập của luồng đang sở hữu khóa ghi. Nó không yêu cầu nhả toàn bộ khóa rồi quay lại cuối hàng.

Chế độ công bằng ảnh hưởng việc tranh quyền giữa các luồng, nhưng không đặt ra thời gian chờ tối đa và không buộc luồng đang giữ khóa đọc phải sớm nhả khóa. Không dùng `fair=true` để bù cho vùng đọc kéo dài tùy ý.

## 8. Tự kiểm tra hiểu bài

1. **Vì sao phải lấy khóa đọc trước khi nhả khóa ghi?**  
   Để không có khoảng trống cho luồng ghi khác thay đổi dữ liệu giữa cập nhật và đọc tiếp.

2. **Sau khi hạ cấp, luồng khác có thể đọc không?**  
   Có thể tranh quyền đọc theo chính sách cấp khóa, vì không còn khóa ghi được giữ; quyền ghi vẫn bị chặn bởi lượt đọc còn giữ.

3. **Vì sao bộ nhớ đệm phải kiểm tra lại `valid` dưới khóa ghi?**  
   Luồng khác có thể đã làm mới dữ liệu trong lúc luồng hiện tại nhả khóa đọc và chờ khóa ghi.

4. **Hạ cấp có cho phép sửa tiếp dưới khóa đọc không?**  
   Không. Khi không còn giữ khóa ghi, giai đoạn đó phải tuân thủ giao thức chỉ đọc.

5. **Có luôn cần hạ cấp sau khi cập nhật không?**  
   Không. Chỉ cần khi còn một giai đoạn đọc phải được bảo vệ liên tục; nếu có thể sử dụng ảnh chụp bất biến ngoài khóa thì có thể chọn thiết kế đơn giản hơn.

## 9. Tài liệu chính thức

- [ReentrantReadWriteLock — tái nhập, hạ cấp và ví dụ bộ nhớ đệm](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)
- [ReadWriteLock — hợp đồng truy cập và nhìn thấy dữ liệu](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html)
- [Lock — giao thức lấy/nhả khóa và đồng bộ bộ nhớ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html)

Các ví dụ dùng API còn áp dụng trong Java hiện đại và chỉ cần JDK 17 trở lên.
