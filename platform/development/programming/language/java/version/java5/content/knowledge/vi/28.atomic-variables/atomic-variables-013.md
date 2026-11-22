# Lựa chọn khóa hoặc biến nguyên tử theo phạm vi cập nhật

## 1. Bắt đầu từ điều gì phải luôn đúng

Khi nhiều luồng cùng dùng một trạng thái, câu hỏi đầu tiên không phải là “khóa hay CAS nhanh hơn?”. Hãy xác định **toàn bộ quy tắc cần được giữ nhất quán trong một lần thao tác**.

Ví dụ:

- Tăng số yêu cầu đã xử lý: một phép tăng độc lập.
- Giữ chỗ trong kho: chỉ trừ số lượng khi còn đủ, đồng thời tăng số lượng đã giữ.
- Đọc cấu hình: cần thấy cả nhóm thuộc tính thuộc cùng một phiên bản.
- Chờ hàng đợi có phần tử: cần cơ chế chờ theo điều kiện và đánh thức.

Một điều kiện phải luôn đúng tại các ranh giới quan sát hợp lệ được gọi là bất biến (invariant). Chẳng hạn, khi chuyển hàng từ “còn sẵn” sang “đã giữ”, tổng hai số không đổi.

Phạm vi đồng bộ phải bao trùm mọi lần đọc, kiểm tra và ghi cần thiết để bảo vệ bất biến đó. Số dòng mã ngắn hay dài và số trường khai báo không tự quyết định được công cụ.

## 2. Một thao tác nguyên tử không làm cả chuỗi nguyên tử

Với một biến:

```java
AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
```

Phép tăng được thực hiện như một cập nhật nguyên tử. Nhưng viết lại thành:

```java
// SAI nếu muốn tăng an toàn giữa nhiều luồng.
counter.set(counter.get() + 1);
```

thì việc đọc và việc ghi là hai thao tác riêng. Hai luồng có thể cùng đọc `0` rồi cùng ghi `1`.

Một lỗi khác là kiểm tra rồi hành động:

```java
// SAI: điều kiện và phép trừ không phải một thao tác chung.
if (remaining.get() > 0) {
    remaining.decrementAndGet();
}
```

Khi chỉ còn một suất, hai luồng đều có thể qua điều kiện và làm số lượng âm. Chỉ một biến vẫn có thể cần **một phép chuyển có điều kiện**, không chỉ một lần gọi phương thức nguyên tử bất kỳ.

Để giữ điều kiện trên một biến, có thể dùng vòng lặp so sánh và đặt (compare-and-set, CAS):

```java
// Phương thức minh họa để đặt vào một lớp có sẵn.
static boolean tryTakeOne(AtomicInteger remaining) {
    for (;;) {
        int observed = remaining.get();
        if (observed <= 0) {
            return false;
        }
        if (remaining.compareAndSet(observed, observed - 1)) {
            return true;
        }
    }
}
```

CAS thành công là thời điểm ghi nhận phép lấy suất. Khi thất bại, đọc lại và kiểm tra lại điều kiện. Giả định mọi đường cập nhật khác cũng giữ quy tắc số lượng không âm.

## 3. Nhiều biến nguyên tử không hợp thành một giao dịch

Giả sử trạng thái kho gồm:

```java
AtomicInteger available = new AtomicInteger(100);
AtomicInteger reserved = new AtomicInteger(0);
```

Việc giữ một sản phẩm bằng hai lời gọi riêng:

```java
available.decrementAndGet();
reserved.incrementAndGet();
```

cho phép một luồng đọc chen vào giữa hai cập nhật và thấy `available + reserved == 99`, dù tổng hợp lệ cần là `100`.

Thêm CAS cho từng biến cũng chưa tạo giao dịch cho cả cặp. CAS thứ nhất có thể thành công còn CAS thứ hai thất bại. Việc “hoàn tác” bằng một CAS khác lại có thể tranh chấp tiếp và không tự mang lại tính đúng.

Điều cần bảo vệ là chuyển trạng thái:

```text
(available, reserved) → (available - amount, reserved + amount)
```

Cả phép kiểm tra `available >= amount` và hai phép ghi phải thuộc cùng phạm vi bảo vệ. Hai hướng thường dùng là:

1. Giữ các trường dưới cùng một khóa.
2. Gộp chúng vào một đối tượng bất biến, rồi cập nhật một tham chiếu nguyên tử.

Hai hướng bảo vệ cùng một quy tắc bằng cách tổ chức trạng thái khác nhau.

## 4. Khi khóa là lựa chọn trực tiếp

Khóa thích hợp khi một thao tác cần nhiều bước có liên quan: kiểm tra điều kiện, đọc nhiều trường, cập nhật nhiều trường và trả ảnh chụp nhất quán.

Với `synchronized`, các luồng cùng sử dụng một monitor sẽ không đồng thời đi vào vùng được bảo vệ bằng monitor đó. Việc nhả rồi lấy lại cùng monitor cũng cung cấp quan hệ hiển thị bộ nhớ cần thiết giữa các luồng.

Điều kiện quan trọng là **mọi đường truy cập liên quan phải theo cùng một quy ước khóa**. Khóa chỉ có ở phương thức ghi trong khi getter đọc các trường thường ngoài khóa vẫn là thiết kế sai.

Một đối tượng có hai getter riêng, dù từng getter đều khóa, cũng không tự cung cấp ảnh chụp cặp:

```text
getAvailable() → luồng khác giữ chỗ → getReserved()
```

Nếu người gọi cần cả hai số của cùng trạng thái, cung cấp một phương thức `snapshot()` đọc và trả cả cặp dưới cùng khóa.

## 5. Ví dụ chạy được: bộ đếm độc lập và trạng thái kho

Chương trình dùng biến nguyên tử cho số vòng công việc đã chạy; khóa cho phép giữ chỗ liên quan đến hai trường kho.

Lưu thành `UpdateScopeDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class UpdateScopeDemo {
    record Snapshot(int available, int reserved) {}

    static final class Inventory {
        private int available;
        private int reserved;

        Inventory(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial must be nonnegative");
            }
            available = initial;
        }

        synchronized boolean tryReserve(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (available < amount) {
                return false;
            }
            available -= amount;
            reserved += amount;
            return true;
        }

        synchronized Snapshot snapshot() {
            return new Snapshot(available, reserved);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory(1000);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger successes = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 1000; i++) {
                attempts.incrementAndGet();
                if (inventory.tryReserve(1)) {
                    successes.incrementAndGet();
                }
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot result = inventory.snapshot();
        System.out.println("attempts=" + attempts.get());
        System.out.println("successes=" + successes.get());
        System.out.println("available=" + result.available());
        System.out.println("reserved=" + result.reserved());
        System.out.println("total="
                + (result.available() + result.reserved()));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 UpdateScopeDemo.java
java UpdateScopeDemo
```

Stdout khi hai luồng hoàn tất bình thường:

```text
attempts=2000
successes=1000
available=0
reserved=1000
total=1000
```

Vì sao cách chia phạm vi này đúng?

- `attempts` chỉ đếm các lần lặp. Từng phép tăng không cần làm chung với một lần giữ chỗ.
- `available` và `reserved` thuộc cùng quy tắc kho. Cả kiểm tra lẫn cập nhật nằm trong một phương thức khóa trên cùng đối tượng `Inventory`.
- `snapshot()` sử dụng cùng khóa, nên người đọc tuân thủ giao thức không thấy trạng thái giữa hai phép gán.
- Số lượng ban đầu là `1000`; chỉ có chuyển từ còn sẵn sang đã giữ. Vì vậy các phép tính trong ví dụ không vượt miền `int`.
- Hai luồng có thể được lập lịch theo bất kỳ thứ tự nào; kết quả cuối vẫn như trên.

Có một giới hạn có chủ ý: `successes` không cùng giao dịch bộ nhớ với kho. Trong khi các luồng đang chạy, có thể kho đã giữ chỗ nhưng bộ đếm thành công chưa tăng. Ví dụ chỉ đối chiếu kết quả sau `join()`. Nếu một yêu cầu khác đòi hỏi `successes == reserved` tại mọi ảnh chụp, phải đưa số liệu đó vào cùng phạm vi trạng thái hoặc suy ra nó từ ảnh chụp kho.

“Đếm số lần” và “là thành phần của một bất biến” là hai vai trò khác nhau, dù cùng biểu diễn bằng số nguyên.

## 6. Khi một tham chiếu nguyên tử có thể thay khóa

Nhiều trường không nhất thiết bắt buộc có khóa. Có thể đóng gói trạng thái liên quan trong một đối tượng bất biến rồi công bố bằng một `AtomicReference`.

Đoạn dưới là các thành phần đặt trong một lớp có sẵn; cần import `java.util.concurrent.atomic.AtomicReference`:

```java
record Stock(int available, int reserved) {}

static boolean tryReserve(
        AtomicReference<Stock> state,
        int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    for (;;) {
        Stock observed = state.get();
        if (observed.available() < amount) {
            return false;
        }

        Stock next = new Stock(
                observed.available() - amount,
                Math.addExact(observed.reserved(), amount));

        if (state.compareAndSet(observed, next)) {
            return true;
        }
    }
}
```

Khởi tạo bằng một trạng thái hợp lệ:

```java
AtomicReference<Stock> state =
        new AtomicReference<>(new Stock(1000, 0));

Stock snapshot = state.get();
int total = snapshot.available() + snapshot.reserved();
```

Chỉ đọc tham chiếu một lần rồi dùng chính đối tượng đó để lấy hai trường. Không gọi `state.get()` riêng cho từng trường nếu cần cùng một phiên bản.

Điểm ghi nhận chuyển trạng thái là CAS thành công của toàn bộ tham chiếu. Nếu một luồng khác đã thay tham chiếu, đề xuất cũ bị từ chối và vòng lặp tính lại.

Cách này phù hợp khi:

- Có thể biểu diễn toàn bộ trạng thái liên quan trong một giá trị bất biến.
- Phép tạo trạng thái mới ngắn và an toàn khi thực hiện lại.
- Không cần giữ độc quyền trong lúc làm một chuỗi thao tác ngoài phạm vi đối tượng trạng thái.

Chi phí là tạo đối tượng đề xuất và tính lại khi tranh chấp. `AtomicReference<MutableStock>` không tự bảo vệ việc sửa trường trong `MutableStock`; thay tham chiếu nguyên tử và sửa nội dung đối tượng là hai vấn đề khác nhau.

Hàm cập nhật của `updateAndGet` cũng có thể được gọi lại. Không gửi email, ghi hóa đơn hoặc gọi thanh toán trong phần tính toán có thể thử lại. CAS không hoàn tác các tác dụng phụ đã xảy ra.

## 7. synchronized hay ReentrantLock?

Cả hai có thể bảo vệ một bất biến nhiều trường. Chọn theo yêu cầu điều khiển việc lấy khóa, không chỉ theo số dòng mã.

`synchronized` thường là điểm bắt đầu rõ ràng khi cần vào một vùng độc quyền và tự nhả monitor khi rời vùng, kể cả khi có ngoại lệ.

`ReentrantLock` hữu ích khi cần khả năng như thử lấy khóa, thời gian chờ, hoặc lấy khóa có thể bị ngắt. Mẫu cơ bản:

```java
// Mã minh họa bên trong một phương thức;
// lock là ReentrantLock dùng chung đã được khởi tạo.
lock.lock();
try {
    // Đọc, kiểm tra và cập nhật các trường cùng phạm vi.
} finally {
    lock.unlock();
}
```

`unlock()` phải nằm trong `finally` sau khi đã lấy khóa thành công. Với `tryLock()`, chỉ nhả khi lời gọi thực sự lấy được khóa.

Không dùng `synchronized(lock)` ở một nơi và `lock.lock()` ở nơi khác rồi cho rằng chúng phối hợp. Monitor của đối tượng `lock` và cơ chế khóa do `ReentrantLock` quản lý là hai giao thức khác nhau.

Nếu một luồng phải chờ một điều kiện nghiệp vụ, các cơ chế chờ theo điều kiện hoặc cấu trúc sẵn có như `BlockingQueue` thường phù hợp hơn một vòng lặp liên tục đọc biến nguyên tử. Khi dùng chờ điều kiện, kiểm tra điều kiện trong vòng lặp theo đúng giao thức của cơ chế đã chọn.

## 8. Tính đúng trước, hiệu năng sau

### Có khóa không đồng nghĩa luôn chậm

Một vùng khóa ngắn, ít tranh chấp có thể rất hiệu quả và dễ kiểm chứng. Một vòng CAS có phép tính dài có thể bỏ đi nhiều công sức khi các luồng cùng cạnh tranh.

### Có CAS không đồng nghĩa mỗi luồng hoàn tất nhanh

CAS có thể thất bại lặp lại. Không suy ra tính công bằng hoặc giới hạn số lần thử cho từng luồng chỉ từ việc dùng biến nguyên tử. Tính tiến triển của cả thuật toán còn phụ thuộc phần tính toán và các bước xung quanh.

### Khóa cũng có rủi ro khi mở rộng phạm vi

Giữ khóa quá lâu làm tăng thời gian chờ. Lấy nhiều khóa theo thứ tự không nhất quán có thể gây bế tắc (deadlock). Khi một thao tác phải lấy nhiều khóa, thiết lập thứ tự lấy khóa chung hoặc tổ chức lại trạng thái.

Lời gọi mạng, I/O chậm hoặc mã gọi ngược vào hệ thống khác trong lúc giữ khóa cần được thiết kế cẩn thận. Đưa chúng ra ngoài khóa cũng không tự bảo toàn mọi điều kiện; có thể phải đọc trạng thái, thực hiện thao tác, rồi xác nhận lại theo một giao thức rõ ràng.

### Đồng bộ bộ nhớ không phải giao dịch ngoài tiến trình

Khóa Java chỉ phối hợp các luồng tuân thủ khóa trong tiến trình. Nó không làm việc sửa cơ sở dữ liệu và gửi yêu cầu sang dịch vụ khác thành một giao dịch nguyên tử. Tương tự, một CAS thành công không tạo cam kết “gửi đúng một lần” cho email hay thanh toán.

Nếu yêu cầu nhất quán vượt ranh giới bộ nhớ, cần công cụ ở chính ranh giới đó, chẳng hạn giao dịch cơ sở dữ liệu, cơ chế chống xử lý lặp hoặc giao thức phối hợp phù hợp.

## 9. Bảng quyết định theo phạm vi cập nhật

| Phạm vi hoặc yêu cầu | Hướng chọn |
| --- | --- |
| Tăng/giảm độc lập một số | Phương thức nguyên tử thích hợp như `incrementAndGet` |
| Kiểm tra rồi cập nhật một giá trị | CAS/vòng cập nhật đúng hợp đồng, hoặc khóa nếu dễ lập luận hơn |
| Nhiều trường có bất biến chung | Một khóa chung hoặc một trạng thái bất biến dưới một tham chiếu nguyên tử |
| Cần đọc nhiều trường của cùng phiên bản | `snapshot()` dưới khóa, hoặc một lần đọc trạng thái bất biến |
| Cần chờ điều kiện, giới hạn thời gian lấy khóa hoặc phản ứng với ngắt | Chọn cơ chế khóa/chờ hoặc cấu trúc đồng thời có hợp đồng phù hợp |
| Cần bảo vệ nhiều tài nguyên ngoài tiến trình | Cơ chế giao dịch/phối hợp ở cấp tài nguyên |

Không dùng `volatile` như cách thay thế tự động cho hai lựa chọn trên: nó hỗ trợ hiển thị và thứ tự theo hợp đồng bộ nhớ, nhưng không làm `count++` hay nhiều phép gán thành một cập nhật chung.

Một kiểu dữ liệu có tên “concurrent” cũng không làm mọi chuỗi thao tác của người dùng nguyên tử. Ví dụ, đọc rồi ghi vào một cấu trúc đồng thời bằng hai lời gọi riêng vẫn phải xét hợp đồng cho cả chuỗi.

## 10. Cách tự kiểm tra thiết kế

Trước khi chọn công cụ, trả lời lần lượt:

1. Bất biến nào phải giữ đúng? Viết nó bằng điều kiện cụ thể.
2. Một lần thao tác cần đọc, kiểm tra và ghi những dữ liệu nào?
3. Người đọc cần từng trường độc lập hay ảnh chụp nhất quán của nhiều trường?
4. Mọi đường truy cập có cùng tuân thủ một giao thức không?
5. Nếu dùng CAS, phần tính toán có an toàn khi chạy lại không?
6. Nếu dùng khóa, có đường quên nhả khóa, lấy khóa khác thứ tự hoặc giữ khóa khi làm việc chậm không?
7. Yêu cầu có vượt ranh giới bộ nhớ của tiến trình không?

Ví dụ tự luyện: ứng dụng lưu `lower` và `upper`, yêu cầu `lower <= upper`. Thay từng trường bằng `AtomicInteger` chưa đủ. Một lời gọi đổi khoảng và một lời gọi đọc cả khoảng cần cùng nhìn nhận hai trường như một trạng thái. Hãy thử thiết kế cả `synchronized snapshot/update` và `AtomicReference<Range>`, rồi so sánh độ rõ của bất biến, chi phí tạo trạng thái và khả năng tranh chấp.

Công cụ phù hợp là công cụ bao trùm đúng phạm vi của quy tắc cần giữ, với một giao thức mà cả người ghi lẫn người đọc đều tuân thủ.

## Tài liệu đối chiếu

- [Java Language Specification, Chương 17](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): monitor và mô hình bộ nhớ.
- [Lock — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html): hợp đồng lấy/nhả khóa và mẫu `try/finally`.
- [AtomicReference — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cập nhật tham chiếu và yêu cầu đối với hàm có thể thử lại.
