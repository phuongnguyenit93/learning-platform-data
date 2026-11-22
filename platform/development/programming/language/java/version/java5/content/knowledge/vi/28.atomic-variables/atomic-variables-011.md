# Giới hạn của biến nguyên tử với bất biến gồm nhiều trường

## 1. Bất biến thuộc về cả trạng thái, không chỉ từng biến

Một đối tượng khoảng giá trị có hai trường:

```text
lower = 0
upper = 10
```

Điều kiện phải giữ là `lower <= upper`. Điều kiện này gọi là **bất biến (invariant)** của đối tượng: mọi trạng thái được công bố cho bên sử dụng phải thỏa mãn nó.

Nếu thay từng trường bằng `AtomicInteger`, ta có thể đọc, ghi hoặc CAS từng số nguyên một cách nguyên tử. Tuy nhiên, bất biến vẫn phụ thuộc vào **cặp** giá trị. Tính nguyên tử ở mỗi trường không tự tạo ra tính nguyên tử cho cả cặp.

Đây là vấn đề thường gặp trong thực tế:

- `used <= capacity`: lượng đã sử dụng không vượt dung lượng.
- `start <= end`: thời điểm bắt đầu không sau thời điểm kết thúc.
- `status == COMPLETED` kéo theo kết quả đã được gán.
- Tổng của nhiều số dư phải được bảo toàn khi chuyển giữa các tài khoản.
- Một phiên bản cấu hình phải đi cùng tập tham số tương ứng.

Bài này dùng các cơ chế còn phù hợp trong Java hiện đại: `AtomicInteger`, `synchronized` và `AtomicReference`. Các chương trình dùng Java 17+; `record` được dùng để biểu diễn trạng thái bất biến một cách gọn và rõ.

## 2. Vì sao kiểm tra từng trường rồi ghi vẫn sai?

Xét hai phương thức dưới đây. Đây là đoạn minh họa chưa an toàn khi có nhiều luồng:

```java
private final AtomicInteger lower = new AtomicInteger(0);
private final AtomicInteger upper = new AtomicInteger(10);

void setLower(int value) {
    if (value > upper.get()) {
        throw new IllegalArgumentException("lower > upper");
    }
    lower.set(value);
}

void setUpper(int value) {
    if (value < lower.get()) {
        throw new IllegalArgumentException("upper < lower");
    }
    upper.set(value);
}
```

Đoạn này cần import `java.util.concurrent.atomic.AtomicInteger` khi đặt vào một lớp. Lỗi không nằm ở phép đọc hay phép ghi riêng lẻ. Lỗi nằm ở khoảng thời gian giữa **kiểm tra** và **cập nhật**.

Hai yêu cầu đồng thời là đặt `lower = 8` và `upper = 5`:

| Thứ tự | Luồng A | Luồng B |
| --- | --- | --- |
| 1 | Đọc upper = 10; chấp nhận lower mới bằng 8 | |
| 2 | | Đọc lower = 0; chấp nhận upper mới bằng 5 |
| 3 | Ghi lower = 8 | |
| 4 | | Ghi upper = 5 |

Kết quả là `lower = 8, upper = 5`. Mỗi luồng đều đã kiểm tra một điều kiện đúng lúc kiểm tra. Hai kết luận riêng ấy không tạo thành một quyết định chung đúng.

Đây là lỗi **kiểm tra rồi hành động (check-then-act)**: trạng thái làm cơ sở cho quyết định có thể đổi trước khi hành động hoàn tất. Một lớp có thể không có truy cập dữ liệu thiếu đồng bộ ở cấp trường nhưng vẫn sai ở cấp thuật toán.

### Thí nghiệm buộc hai phép kiểm tra cùng thành công

Lưu thành `BrokenInvariantDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class BrokenInvariantDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger lower = new AtomicInteger(0);
        AtomicInteger upper = new AtomicInteger(10);
        CountDownLatch checked = new CountDownLatch(2);
        CountDownLatch writeAllowed = new CountDownLatch(1);

        Thread setLower = new Thread(() -> {
            if (8 <= upper.get()) {
                checked.countDown();
                await(writeAllowed);
                lower.set(8);
            }
        });

        Thread setUpper = new Thread(() -> {
            if (5 >= lower.get()) {
                checked.countDown();
                await(writeAllowed);
                upper.set(5);
            }
        });

        setLower.start();
        setUpper.start();

        checked.await();
        writeAllowed.countDown();
        setLower.join();
        setUpper.join();

        int low = lower.get();
        int high = upper.get();
        System.out.println("lower=" + low + ", upper=" + high);
        System.out.println("Valid: " + (low <= high));
    }
}
```

Chạy:

```shell
javac BrokenInvariantDemo.java
java BrokenInvariantDemo
```

Stdout khi không có ngắt luồng từ bên ngoài:

```text
lower=8, upper=5
Valid: false
```

Latch `checked` đợi cả hai luồng kiểm tra xong; `writeAllowed` chỉ cho phép ghi sau đó. Thí nghiệm cố ý tạo ra một lịch xen kẽ hợp lệ để lộ lỗi, không dùng độ trễ thời gian để đoán bộ lập lịch.

## 3. Thêm CAS từng trường không giải quyết được quan hệ chung

Giả sử luồng A dùng:

```java
// Vẫn chưa bảo vệ quan hệ giữa lower và upper.
int oldLower = lower.get();
if (8 <= upper.get()) {
    lower.compareAndSet(oldLower, 8);
}
```

CAS chỉ kiểm tra `lower` có còn bằng `oldLower` hay không. Nó không kiểm tra `upper` có còn là giá trị từng dùng để chấp nhận 8. Luồng B vẫn có thể sửa `upper` mà không làm CAS trên `lower` thất bại.

Tương tự, hai CAS liên tiếp không phải một CAS trên hai trường. CAS đầu có thể thành công còn CAS sau thất bại; người đọc có thể quan sát trạng thái ở giữa. Thực hiện thêm vài lần đọc để “kiểm tra lại” cũng chưa phải một chứng minh đúng: cần xác định toàn bộ giao thức, lúc nào thay đổi có hiệu lực, và cách xử lý tranh chấp.

Không nên tự xây dựng giao dịch nhiều trường bằng sửa trước rồi hoàn tác sau. Luồng khác có thể đã đọc hoặc sửa trạng thái trung gian; hoàn tác không thể đơn giản xóa mọi ảnh hưởng đó.

## 4. Giải pháp dùng khóa: kiểm tra, ghi và đọc cùng một giao thức

Khi trạng thái có quan hệ chặt, cách trực tiếp là đặt các trường thường bên trong đối tượng và giữ một khóa chung cho tất cả thao tác liên quan.

Lưu thành `LockedRange.java`:

```java
public final class LockedRange {
    public record Snapshot(int lower, int upper) {}

    private final Object lock = new Object();
    private int lower = 0;
    private int upper = 10;

    public boolean trySetLower(int value) {
        synchronized (lock) {
            if (value > upper) {
                return false;
            }
            lower = value;
            return true;
        }
    }

    public boolean trySetUpper(int value) {
        synchronized (lock) {
            if (value < lower) {
                return false;
            }
            upper = value;
            return true;
        }
    }

    public Snapshot snapshot() {
        synchronized (lock) {
            return new Snapshot(lower, upper);
        }
    }
}
```

Trong thiết kế này, hai thao tác xung đột được sắp thứ tự:

- Nếu đặt lower bằng 8 thành công trước, yêu cầu đặt upper bằng 5 bị từ chối.
- Nếu đặt upper bằng 5 thành công trước, yêu cầu đặt lower bằng 8 bị từ chối.

Cả hai kết quả đều giữ `lower <= upper`. Không nên yêu cầu lịch chạy cố định giữa hai luồng; điều cần chứng minh là mọi thứ tự được giao thức cho phép đều giữ bất biến.

Bảo đảm phụ thuộc vào bốn điều:

1. Các trường là `private`, không có đường ghi trực tiếp từ bên ngoài.
2. Điều kiện kiểm tra và lần ghi nằm trong cùng khối khóa.
3. Hai phương thức cập nhật dùng **cùng đối tượng khóa**.
4. Phương thức trả một cặp dữ liệu cũng lấy khóa ấy.

Theo [Java Language Specification, chương 17](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5), monitor cung cấp loại trừ lẫn nhau; mở khóa và lần khóa tiếp theo trên cùng monitor tạo quan hệ happens-before. Nhờ cùng giao thức, người đọc thấy dữ liệu được công bố đúng khi lấy khóa.

Không cần biến các trường thành `AtomicInteger` khi tất cả truy cập liên quan đã được bảo vệ đúng bằng khóa. Làm vậy chỉ thêm một cơ chế mà không thay thế được quy tắc sở hữu trạng thái.

Nếu nghiệp vụ cần đổi đồng thời cả hai đầu mút, nên cung cấp một phương thức `setRange(newLower, newUpper)`: kiểm tra cặp tham số, rồi cập nhật cả hai trong cùng khối khóa. Hai lần gọi setter từ bên ngoài vẫn là hai thao tác riêng.

## 5. Giải pháp dùng một trạng thái bất biến và AtomicReference

Một hướng khác là thay đổi **đơn vị nguyên tử**: đưa các trường có liên hệ vào một giá trị bất biến, rồi thay toàn bộ tham chiếu tới giá trị đó.

Lưu thành `AtomicRange.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicRange {
    public record Range(int lower, int upper) {
        public Range {
            if (lower > upper) {
                throw new IllegalArgumentException("lower > upper");
            }
        }
    }

    private final AtomicReference<Range> state =
            new AtomicReference<>(new Range(0, 10));

    public boolean trySetLower(int value) {
        while (true) {
            Range before = state.get();
            if (value > before.upper()) {
                return false;
            }

            Range after = new Range(value, before.upper());
            if (state.compareAndSet(before, after)) {
                return true;
            }
        }
    }

    public boolean trySetUpper(int value) {
        while (true) {
            Range before = state.get();
            if (value < before.lower()) {
                return false;
            }

            Range after = new Range(before.lower(), value);
            if (state.compareAndSet(before, after)) {
                return true;
            }
        }
    }

    public Range snapshot() {
        return state.get();
    }
}
```

Cơ chế của một lần cập nhật:

1. `before` giữ một cặp nhất quán, được lấy bằng một lần đọc tham chiếu.
2. Kiểm tra điều kiện dựa trên đúng cặp đó.
3. Tạo `after` riêng tư, cũng là một cặp hợp lệ.
4. CAS chỉ công bố `after` nếu trạng thái hiện hành vẫn là chính `before`.
5. Nếu luồng khác đã công bố trạng thái khác, đọc lại và kiểm tra lại từ đầu.

**Điểm tuyến tính hóa (linearization point)** của cập nhật thành công là lần CAS thành công: đó là thời điểm có thể xem thay đổi như có hiệu lực tức thì. Với yêu cầu bị từ chối, điều kiện không hợp lệ được quan sát tại lần đọc `before`; trạng thái có thể đổi sau đó mà không làm quyết định ấy sai về lịch sử thao tác.

Hai luồng cùng bắt đầu từ `Range(0, 10)` không thể cùng công bố các kết quả dựa trên trạng thái cũ ấy. Một luồng thắng; luồng còn lại đọc lại trạng thái và từ chối giá trị xung đột.

`AtomicReference.compareAndSet` so sánh **tham chiếu bằng `==`**, không gọi `equals` để so các trường. Hai đối tượng `Range` có nội dung bằng nhau vẫn có thể là hai tham chiếu khác nhau.

`Range` chỉ chứa hai `int` và các trường của record là final, nên đối tượng này phù hợp làm snapshot bất biến. Một record chứa `List`, mảng hay đối tượng có thể sửa không tự làm dữ liệu bên trong bất biến; cần bảo vệ hoặc sao chép các thành phần đó.

### Vì sao không thay CAS bằng set?

Đoạn minh họa sau thiếu kiểm tra trạng thái đã thay đổi:

```java
Range before = state.get();
if (value <= before.upper()) {
    state.set(new Range(value, before.upper()));
}
```

Nếu người ghi khác sửa upper sau lần đọc, phép `set` có thể công bố lại upper cũ và làm mất cập nhật của người kia. Mỗi cặp vẫn có thể hợp lệ nhưng lịch sử cập nhật đã sai. Giữ bất biến và tránh mất cập nhật là hai yêu cầu phải cùng xem xét.

Với nhiều người ghi thực hiện chuyển đổi dựa trên trạng thái cũ, CAS kết hợp đọc lại và tính lại giải quyết điều kiện “cơ sở của phép chuyển đổi chưa bị thay thế”. Với một người ghi duy nhất đã được bảo đảm bằng kiến trúc, giao thức có thể đơn giản hơn, nhưng cần nêu rõ giả thiết đó.

### Các giới hạn vẫn còn

- Dưới tranh chấp, vòng lặp CAS có thể chạy lại nhiều lần; không bảo đảm một luồng cụ thể hoàn thành trong một số lần thử cố định.
- Mỗi lần thử tạo đối tượng mới; cần cân nhắc chi phí cấp phát và GC.
- Các trường độc lập nhưng đặt chung một trạng thái vẫn tranh chấp trên một tham chiếu.
- Hàm dùng với `updateAndGet` có thể được thực hiện lại; phải tránh tác dụng phụ trong phần tính toán có thể thử lại.
- Không sửa trạng thái đã công bố hoặc đem đối tượng cũ ra sửa rồi công bố lại. Việc tái sử dụng tham chiếu cần phân tích thêm vấn đề thay đổi rồi quay về tham chiếu cũ; mẫu trên luôn tạo phiên bản mới.
- Một CAS trong JVM không bao trùm cập nhật cơ sở dữ liệu, gửi HTTP hay gửi thông báo. Những hiệu ứng đó thuộc một giao thức nghiệp vụ khác.

Hợp đồng CAS, truy cập tham chiếu và khả năng thực hiện lại hàm cập nhật nằm trong [AtomicReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).

## 6. Chạy thử hai thiết kế đúng

Lưu thành `SafeRangeDemo.java`, cùng thư mục với `LockedRange.java` và `AtomicRange.java`:

```java
public class SafeRangeDemo {
    public static void main(String[] args) {
        LockedRange locked = new LockedRange();
        System.out.println("Locked lower accepted: "
                + locked.trySetLower(8));
        System.out.println("Locked upper accepted: "
                + locked.trySetUpper(5));
        LockedRange.Snapshot first = locked.snapshot();
        System.out.println("Locked valid: "
                + (first.lower() <= first.upper()));

        AtomicRange atomic = new AtomicRange();
        System.out.println("CAS lower accepted: "
                + atomic.trySetLower(8));
        System.out.println("CAS upper accepted: "
                + atomic.trySetUpper(5));
        AtomicRange.Range second = atomic.snapshot();
        System.out.println("CAS valid: "
                + (second.lower() <= second.upper()));
    }
}
```

Biên dịch và chạy với Java 17+:

```shell
javac LockedRange.java AtomicRange.java SafeRangeDemo.java
java SafeRangeDemo
```

Stdout:

```text
Locked lower accepted: true
Locked upper accepted: false
Locked valid: true
CAS lower accepted: true
CAS upper accepted: false
CAS valid: true
```

Ví dụ chạy này cố định thứ tự yêu cầu để kết quả dễ đối chiếu. Tính đúng khi có nhiều luồng đến từ giao thức khóa/CAS đã phân tích, không thể chỉ suy ra từ một lần chạy cho stdout đúng.

## 7. Đọc riêng từng trường cũng có thể làm mất tính nhất quán

Ngay cả khi người ghi dùng `AtomicReference<Range>` đúng, người đọc vẫn có thể tự trộn hai phiên bản:

```java
// Hai lần get có thể lấy hai phiên bản khác nhau.
int low = state.get().lower();
int high = state.get().upper();
```

Ví dụ trạng thái đang là `Range(8, 10)`. Người đọc lấy lower bằng 8. Trong lúc đó, các cập nhật hợp lệ chuyển lần lượt sang `Range(0, 10)` rồi `Range(0, 5)`. Người đọc lấy upper bằng 5 và tự ghép ra cặp `(8, 5)`. Không phiên bản nào đã công bố vi phạm bất biến; lỗi nằm ở việc ghép hai lần đọc.

Cách đúng khi cần xử lý một cặp:

```java
Range snapshot = state.get();
int low = snapshot.lower();
int high = snapshot.upper();
```

Trong thiết kế dùng khóa cũng vậy: hai getter riêng, mỗi getter khóa đúng, chưa tự bảo đảm kết quả của hai lần gọi thuộc cùng một trạng thái. Hãy có phương thức trả snapshot gồm cả hai trường.

Snapshot nhất quán có thể trở nên cũ ngay sau khi được đọc. Nếu cần hành động dựa trên một điều kiện của snapshot, điều kiện đó phải được xác minh trong cùng lần chuyển trạng thái có bảo vệ; đừng chụp xong rồi mặc định điều kiện còn đúng mãi.

## 8. Những cách bổ sung không tự giải quyết vấn đề

| Cách làm | Điều nó bảo vệ | Vì sao chưa đủ cho bất biến nhiều trường |
| --- | --- | --- |
| Mỗi trường là volatile | Quy tắc quan sát và thứ tự bộ nhớ cho trường | Không gộp kiểm tra với ghi; không gộp nhiều trường |
| Mỗi trường là AtomicInteger | Thao tác nguyên tử theo từng biến | Quan hệ giữa các biến nằm ngoài một thao tác đơn |
| Mỗi setter khóa một đối tượng khác | Từng vùng khóa riêng | Hai setter vẫn chạy đồng thời |
| Chỉ khóa người ghi | Thứ tự giữa người ghi tuân thủ khóa | Người đọc ngoài giao thức có thể thấy trạng thái trung gian |
| Getter trả thẳng đối tượng có thể sửa | Chỉ việc lấy tham chiếu | Bên gọi có thể sửa dữ liệu sau khi rời khóa/CAS |
| Kiểm tra lại sau khi đã ghi | Phát hiện một số trạng thái sai | Không xóa việc trạng thái sai đã bị quan sát |
| Chạy thử nhiều lần không thấy lỗi | Một tập lịch đã xảy ra | Không chứng minh mọi lịch xen kẽ đều đúng |

Ngoài đồng thời, hãy xét cả lỗi giữa chừng. Với thao tác có thể ném ngoại lệ, nên xác minh đầu vào và tính các giá trị có thể thất bại trước khi ghi một phần trạng thái. Khóa ngăn người khác xen vào, nhưng không tự hoàn tác những lần gán đã xảy ra nếu chính phương thức ném lỗi.

## 9. Chọn giải pháp từ bất biến

Dùng một quy trình ngắn khi thiết kế đối tượng:

1. Viết rõ điều kiện cần giữ, chẳng hạn `0 <= used && used <= capacity`.
2. Xác định toàn bộ trường tham gia và mọi đường đọc/ghi chúng.
3. Chọn một đơn vị đồng bộ chung: một khóa hoặc một trạng thái bất biến được công bố qua một tham chiếu.
4. Đặt kiểm tra điều kiện, tính kết quả và công bố kết quả trong giao thức ấy.
5. Cung cấp API snapshot cho những người đọc cần quan hệ giữa nhiều trường.
6. Xác định hành vi khi yêu cầu không hợp lệ, khi gặp tranh chấp và khi có ngoại lệ.

Khóa thường dễ đọc khi thao tác phức tạp hoặc có nhiều nhánh. Trạng thái bất biến qua CAS phù hợp khi chuyển trạng thái ngắn, có thể tính lại và chi phí tạo phiên bản chấp nhận được. Không nên chuyển sang CAS chỉ vì giả định rằng nó luôn nhanh hơn; cần đo trên tải thực tế và giữ được lập luận về tính đúng.

## 10. Tự kiểm tra

**Hai AtomicInteger riêng có tự giữ lower <= upper không?**  
Không. Chúng bảo vệ thao tác riêng từng trường; bất biến yêu cầu phối hợp cả hai.

**CAS trên lower có phát hiện upper đổi không?**  
Không. Nó chỉ kiểm tra biến là đích CAS.

**Tại sao khóa phải bao cả bước kiểm tra?**  
Nếu kiểm tra ở ngoài khóa, quyết định có thể đã dựa trên trạng thái lỗi thời trước khi bắt đầu ghi có khóa.

**Một AtomicReference tới record có đủ không?**  
Chỉ khi trạng thái thực sự bất biến, chuyển đổi được phối hợp đúng và người đọc lấy một snapshot chung. CAS không tự làm các thành phần có thể sửa bên trong trở thành bất biến.

**Mọi snapshot đều hợp lệ thì hai lần lấy snapshot có thể ghép thành cặp sai không?**  
Có. Hai lần đọc có thể thuộc hai phiên bản khác nhau.

Điểm cần nhớ là chọn đúng phạm vi bảo vệ: biến nguyên tử xử lý một đơn vị dữ liệu; bất biến nhiều trường cần một giao thức chung cho toàn bộ trạng thái liên quan.
