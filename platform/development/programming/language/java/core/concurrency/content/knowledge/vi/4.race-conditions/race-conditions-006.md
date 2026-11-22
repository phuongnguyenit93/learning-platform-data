# Broken invariant khi cập nhật nhiều biến liên quan trong Java Concurrency

## 1. Vấn đề: từng biến đúng nhưng trạng thái tổng thể sai

Một đối tượng có thể chứa nhiều trường dữ liệu mà **ý nghĩa nghiệp vụ chỉ đúng khi các trường thỏa một quan hệ với nhau**. Quan hệ bắt buộc đó gọi là **bất biến (invariant)**.

Ví dụ một sổ cái có hai số dư:

- `left = 70`, `right = 30`;
- tổng tiền phải luôn bằng `100`;
- chuyển `20` từ `left` sang `right` phải biến trạng thái `(70, 30)` thành `(50, 50)`.

Bất biến ở đây là:

```text
left >= 0
right >= 0
left + right == 100
```

Nếu mã thực hiện tuần tự hai phép gán:

```java
left -= 20;  // Trạng thái trung gian: left=50, right=30
right += 20; // Trạng thái cuối: left=50, right=50
```

thì sau phép gán đầu, tổng tạm thời bằng `80`. Khi hai thread chạy đồng thời, **reader có thể quan sát trạng thái trung gian** `(50, 30)` và thấy tổng không còn bằng `100`. Đây là hiện tượng **broken invariant khi cập nhật nhiều biến liên quan**.

Các ví dụ gần gũi khác:

| Dữ liệu liên quan | Bất biến cần duy trì | Trạng thái sai có thể bị nhìn thấy |
| --- | --- | --- |
| `start` và `end` | `start <= end` | Reader thấy `start` mới và `end` cũ, thành `start > end` |
| `used` và `capacity` | `0 <= used <= capacity` | Tăng `used` trước khi tăng `capacity` khiến `used > capacity` |
| `items` và `itemCount` | `itemCount == items.size()` | Danh sách đã thay đổi nhưng số lượng chưa cập nhật |
| `debit` và `credit` | Tổng ghi nợ/ghi có của giao dịch cân bằng | Reader chỉ thấy một vế giao dịch |
| `configVersion` và `configData` | Dữ liệu ứng với đúng phiên bản | Đọc version mới với data cũ |

Trọng tâm không nằm ở cú pháp `+=` hoặc `-=`. Ngay cả khi **mỗi phép đọc/ghi một trường đều nguyên tử**, việc đọc/ghi **một nhóm nhiều trường** vẫn chưa chắc nguyên tử. Hệ thống cần một cơ chế khiến các thread khác chỉ nhìn thấy **những trạng thái nhất quán**.

## 2. Race condition liên quan đến bất biến là gì?

**Race condition** xuất hiện khi kết quả hoặc tính đúng đắn phụ thuộc vào thứ tự xen kẽ không được kiểm soát giữa các hoạt động đồng thời. Với invariant nhiều trường, trình tự sau gây lỗi:

```text
Trạng thái ban đầu: left=70, right=30, tổng=100

Thread writer                          Thread reader
----------------------------           -----------------------------
left = 50
                                       đọc left  -> 50
                                       đọc right -> 30
                                       tính tổng -> 80 (SAI)
right = 50

Trạng thái cuối: left=50, right=50, tổng=100
```

Nhìn riêng từng phép gán, không có giá trị nào bị “ghi nửa chừng”. Tuy nhiên, **reader đã thấy một tổ hợp chưa được công bố như một giao dịch hoàn chỉnh**.

Cần phân biệt ba khái niệm:

1. **Atomicity của từng trường**: một thao tác đọc/ghi đơn lẻ có thể nguyên tử theo Java Memory Model, nhưng điều đó không khiến cả chuỗi `left -= amount; right += amount` thành một thao tác nguyên tử.
2. **Visibility (khả năng nhìn thấy)**: khi writer ghi, reader có được bảo đảm quan sát bản cập nhật hay không? `volatile`, monitor hoặc các biến atomic cung cấp quan hệ bộ nhớ nhất định.
3. **Consistency (tính nhất quán)**: các giá trị reader nhìn thấy có cùng thuộc **một trạng thái hợp lệ** hay không? Đây là yêu cầu mạnh hơn visibility của từng trường.

Ví dụ reader thấy chính xác `left = 50` và `right = 30`. Hai phép đọc đều có thể được thực hiện “đúng” về mặt từng giá trị, nhưng snapshot tổng thể vẫn sai.

## 3. Minh chứng có thể chạy: `volatile` từng trường vẫn bị broken invariant

Ví dụ dưới sử dụng hai trường `volatile` và `CountDownLatch` để cố ý dừng writer **giữa hai phép cập nhật**. Đây là cách chứng minh một snapshot không nhất quán mà không phụ thuộc may rủi của bộ lập lịch.

Tạo tệp `BrokenInvariantDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class BrokenInvariantDemo {
    private static final class Balances {
        volatile int left = 70;
        volatile int right = 30;
    }

    public static void main(String[] args) throws InterruptedException {
        Balances balances = new Balances();
        CountDownLatch firstWriteDone = new CountDownLatch(1);
        CountDownLatch allowSecondWrite = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            balances.left -= 20;
            firstWriteDone.countDown();

            try {
                allowSecondWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            balances.right += 20;
        }, "writer");

        writer.start();
        firstWriteDone.await();

        System.out.println("Trong lúc cập nhật: "
                + balances.left + " + " + balances.right
                + " = " + (balances.left + balances.right));

        allowSecondWrite.countDown();
        writer.join();

        System.out.println("Sau khi cập nhật: "
                + balances.left + " + " + balances.right
                + " = " + (balances.left + balances.right));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BrokenInvariantDemo.java
java BrokenInvariantDemo
```

Kết quả khi không có yêu cầu interrupt bên ngoài:

```text
Trong lúc cập nhật: 50 + 30 = 80
Sau khi cập nhật: 50 + 50 = 100
```

**Giải thích bằng thứ tự sự kiện:**

1. Writer cập nhật `left` từ `70` thành `50`.
2. `firstWriteDone.countDown()` cho main biết phép ghi thứ nhất đã hoàn thành. `main` được đánh thức ở `await()`.
3. Writer đứng ở `allowSecondWrite.await()` nên **chưa thể cập nhật `right`**.
4. Main đọc `(left, right) = (50, 30)`. Tổng `80` phá vỡ bất biến `left + right == 100`.
5. Main phát tín hiệu cho writer, rồi đợi `join()`; sau khi worker hoàn tất, cặp số dư là `(50, 50)` và tổng trở lại `100`.

Hai latch tạo các quan hệ *happens-before* cần thiết; do đó lỗi không chỉ là do cache hay đọc dữ liệu cũ. `volatile` buộc các truy cập trường riêng lẻ tuân theo các bảo đảm về visibility và thứ tự của volatile, **nhưng không kết hợp hai trường thành một cập nhật nguyên tử**.

**Điểm cần lưu ý:** `balances.left -= 20` và `balances.right += 20` là các phép đọc–sửa–ghi (read-modify-write), vốn cũng không nguyên tử nếu có nhiều writer. Trong ví dụ này cố ý chỉ có một writer để tách rõ lỗi **snapshot nhiều trường** khỏi lỗi **lost update** do nhiều writer.

Ví dụ ngăn writer tiếp tục để minh họa lỗi một cách xác định. Trong hệ thống thực tế, hai lệnh ghi có thể xảy ra rất sát nhau, nhưng sự xen kẽ của reader ở giữa **vẫn có thể xảy ra**; “thử nhiều lần chưa thấy sai” không phải bằng chứng an toàn.

## 4. Broken invariant khác gì lost update?

Hai lỗi thường xuất hiện gần nhau, nhưng cần xử lý ở đúng cấp độ:

**Lost update** là khi nhiều writer cạnh tranh cập nhật cùng một giá trị. Ví dụ hai thread cùng thực hiện `counter++`, cả hai đọc `10` và cuối cùng chỉ lưu `11` thay vì `12`. Một `AtomicInteger.incrementAndGet()` hoặc khóa phù hợp có thể sửa riêng thao tác tăng đó.

**Broken invariant nhiều trường** là khi một trạng thái hợp lệ đòi hỏi **nhiều giá trị phải thay đổi như một đơn vị logic**. Kể cả hai trường độc lập được lưu dưới dạng `AtomicInteger`, reader vẫn có thể nhìn thấy `left` đã trừ mà `right` chưa cộng. Hai thao tác:

```java
left.addAndGet(-20);
right.addAndGet(20);
```

vẫn là **hai thao tác atomic riêng biệt**. `AtomicInteger` ngăn mất cập nhật trên từng trường (khi dùng nhất quán), nhưng không biến chúng thành một giao dịch nhiều trường.

Với các ứng dụng cần chuyển nhiều giá trị có quan hệ, luôn đặt câu hỏi: **“Đơn vị nhất quán cần bảo vệ là từng giá trị hay cả tập giá trị?”** Nếu yêu cầu là cả tập, cơ chế đồng bộ phải bao phủ cả lúc cập nhật lẫn lúc đọc snapshot.

## 5. Sửa bằng `synchronized`: cùng một monitor bảo vệ thao tác cập nhật và đọc

Giải pháp dễ kiểm chứng là dùng **một monitor duy nhất** cho cả thao tác chuyển tiền và thao tác lấy snapshot. Khi writer vào `synchronized`, reader cần cùng monitor phải chờ đến khi writer rời vùng bảo vệ.

Hai điều kiện bắt buộc:

- **Writer** phải cập nhật toàn bộ nhóm trường liên quan trong một vùng được bảo vệ.
- **Reader** phải đọc toàn bộ nhóm trường đó trong một vùng được bảo vệ **bởi cùng monitor**.

Chỉ khóa writer mà để reader đọc các trường tự do vẫn có thể nhìn thấy trạng thái trung gian. Chỉ khóa reader mà writer không tuân thủ cùng cơ chế cũng không có tác dụng bảo vệ bất biến.

Tạo tệp `SynchronizedInvariantDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class SynchronizedInvariantDemo {
    private static final class Ledger {
        private int left = 70;
        private int right = 30;

        synchronized void transferLeftToRight(int amount) {
            if (amount < 0 || amount > left) {
                throw new IllegalArgumentException("invalid transfer");
            }
            left -= amount;
            right += amount;
        }

        synchronized void transferRightToLeft(int amount) {
            if (amount < 0 || amount > right) {
                throw new IllegalArgumentException("invalid transfer");
            }
            right -= amount;
            left += amount;
        }

        synchronized int total() {
            return left + right;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();
        CountDownLatch start = new CountDownLatch(1);
        AtomicBoolean invariantBroken = new AtomicBoolean(false);

        Thread writer = new Thread(() -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    ledger.transferLeftToRight(1);
                    ledger.transferRightToLeft(1);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        Thread reader = new Thread(() -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    if (ledger.total() != 100) {
                        invariantBroken.set(true);
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "reader");

        writer.start();
        reader.start();
        start.countDown();

        writer.join();
        reader.join();

        System.out.println("Broken: " + invariantBroken.get());
        System.out.println("Final total: " + ledger.total());
    }
}
```

```bash
javac SynchronizedInvariantDemo.java
java SynchronizedInvariantDemo
```

Kết quả khi các thread không bị interrupt:

```text
Broken: false
Final total: 100
```

Mỗi thao tác chuyển tiền cập nhật hai trường khi giữ monitor của `Ledger`. `total()` lấy **chính monitor đó**, nên không thể đọc xen giữa hai phép cập nhật bên trong một lần `transfer...()`. Chương trình có thể xen kẽ thứ tự gọi giữa writer và reader, nhưng mọi giá trị tổng được đọc đều hợp lệ. `AtomicBoolean` chỉ dùng để chuyển kết quả kiểm tra từ reader sang main một cách an toàn; nó **không** phải cơ chế chính bảo vệ hai số dư.

Cách triển khai bằng `synchronized` có đặc điểm:

- Không cần `volatile` cho các trường nếu **mọi truy cập** đều được bảo vệ nhất quán bằng monitor này.
- Monitor có tính loại trừ lẫn nhau: tại một thời điểm, một thread giữ monitor, thread khác muốn lấy monitor phải chờ.
- Khi nhả monitor rồi thread khác lấy lại cùng monitor, Java Memory Model cung cấp quan hệ *happens-before* cho khả năng nhìn thấy dữ liệu.
- Kiểm tra hợp lệ phải nằm **cùng vùng khóa** với việc cập nhật. Nếu kiểm tra `amount <= left` bên ngoài khóa, giá trị `left` có thể thay đổi trước lúc thực hiện giao dịch.
- Không trả về tham chiếu tới một đối tượng nội bộ có thể bị sửa tự do bên ngoài khóa. Trả một snapshot bất biến hoặc giá trị sao chép.

### Vì sao reader không nên đọc từng trường bằng hai getter đồng bộ độc lập?

Giả sử `getLeft()` và `getRight()` đều `synchronized` nhưng caller thực hiện:

```java
int a = ledger.getLeft();
int b = ledger.getRight();
```

Đây là đoạn minh họa (không phải chương trình hoàn chỉnh). Khóa được nhả sau `getLeft()`, nên writer có thể chuyển tiền **giữa hai lời gọi getter**. Lúc đó caller ghép `a` ở trạng thái cũ với `b` ở trạng thái mới, tạo tổng sai dù **mỗi getter riêng lẻ đều thread-safe**.

Cách đúng là cung cấp **một phương thức snapshot** đọc cả hai trường trong cùng một critical section:

```java
record Balances(int left, int right) {}

synchronized Balances snapshot() {
    return new Balances(left, right);
}
```

Đoạn này minh họa phương thức được đặt **bên trong lớp chứa hai trường `left/right`**; `record Balances` là kiểu dữ liệu bất biến được định nghĩa ngoài phương thức. `record` yêu cầu Java 16+ và phù hợp với Java 17+. Caller nhận được một cặp giá trị cùng thuộc một thời điểm được bảo vệ bởi khóa. Sau khi khóa nhả, snapshot vẫn không đổi dù dữ liệu gốc tiếp tục được cập nhật.

## 6. Sửa bằng một immutable snapshot được công bố nguyên tử

Một cách khác là **không cập nhật lần lượt các trường công khai**. Thay vào đó:

1. Đọc một trạng thái bất biến hiện tại.
2. Tính toàn bộ trạng thái kế tiếp trong bộ nhớ cục bộ.
3. Kiểm tra các invariant trên trạng thái mới.
4. Công bố **một tham chiếu** tới trạng thái mới bằng cơ chế atomic/volatile phù hợp.

Reader chỉ lấy **một tham chiếu snapshot** rồi truy cập các trường của cùng snapshot. Vì đối tượng snapshot bất biến, reader không thể quan sát một nửa cập nhật bên trong nó.

### Ví dụ với `AtomicReference` và `record`

Tạo tệp `AtomicSnapshotDemo.java` (Java 17+):

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Balances(int left, int right) {
        Balances {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("broken invariant");
            }
        }

        int total() {
            return left + right;
        }
    }

    public static void main(String[] args) {
        AtomicReference<Balances> state =
                new AtomicReference<>(new Balances(70, 30));

        state.updateAndGet(current ->
                new Balances(current.left() - 20, current.right() + 20));

        Balances snapshot = state.get();
        System.out.println("left=" + snapshot.left());
        System.out.println("right=" + snapshot.right());
        System.out.println("total=" + snapshot.total());
    }
}
```

```bash
javac AtomicSnapshotDemo.java
java AtomicSnapshotDemo
```

Kết quả:

```text
left=50
right=50
total=100
```

`record Balances` tạo một giá trị bất biến biểu diễn **cả cặp**. Constructor kiểm tra trạng thái trước khi đối tượng hợp lệ được công bố. `AtomicReference.updateAndGet` thực hiện cập nhật tham chiếu theo cơ chế atomic; nếu nhiều writer cạnh tranh, hàm tính trạng thái kế tiếp có thể bị gọi lại. Vì vậy lambda cập nhật phải **không có side effect** như gửi email, ghi log nghiệp vụ không thể lặp lại hoặc gọi hệ thống bên ngoài.

Lưu ý: thay thế một tham chiếu `volatile Balances snapshot` cũng có thể cung cấp công bố nguyên tử **cho một writer** nếu writer tạo trạng thái mới hoàn chỉnh rồi gán vào trường volatile. Nhưng nếu nhiều writer đồng thời đọc trạng thái cũ và cùng gán trạng thái mới, một cập nhật có thể ghi đè kết quả của cập nhật khác. `AtomicReference` với CAS/retry giải quyết dạng cạnh tranh cập nhật đó ở cấp tham chiếu khi mọi writer dùng đúng giao thức.

**Bẫy khi đọc:** không làm thế này nếu cần snapshot nhất quán:

```java
int a = state.get().left();
int b = state.get().right();
```

Hai lần `state.get()` có thể trả về hai thế hệ snapshot khác nhau khi writer công bố cập nhật giữa chúng. Dù mỗi snapshot tự nó hợp lệ, ghép hai trường từ hai snapshot khác nhau vẫn có thể sai. Hãy lấy `Balances snapshot = state.get();` **một lần**, rồi đọc `snapshot.left()` và `snapshot.right()`.

## 7. Còn dùng `ReentrantLock` hoặc `ReadWriteLock` thì sao?

`ReentrantLock` có khả năng bảo vệ cùng một invariant giống `synchronized` nếu tất cả reader và writer cùng tuân thủ giao thức khóa. Ưu điểm là hỗ trợ thử lấy khóa, thời hạn chờ, một số cơ chế `Condition` và khả năng điều khiển hủy trong lúc đợi khóa.

Mẫu cơ bản:

```java
lock.lock();
try {
    validateTransfer();
    updateAllRelatedFields();
} finally {
    lock.unlock();
}
```

Đây là **mã minh họa**, trong đó `lock` là `ReentrantLock`, còn hai phương thức là logic của ứng dụng. Cả phương thức đọc snapshot cũng phải lấy **cùng khóa**; khóa viết mà đọc không khóa vẫn không an toàn. Luôn mở khóa trong `finally`.

`ReentrantReadWriteLock` có thể cho phép nhiều reader đồng thời lấy read lock và chỉ một writer giữ write lock. Nó có thể hữu ích khi đọc nhiều, ghi ít, critical section có chi phí đáng kể; nhưng có thêm độ phức tạp và không mặc nhiên nhanh hơn `synchronized`. Không thay đổi loại khóa chỉ vì một microbenchmark ngắn.

Dù dùng khóa nào, yêu cầu về invariant vẫn như nhau: một cập nhật logic phải được thực hiện và quan sát như **một đơn vị nhất quán**.

## 8. Không thể chỉ thêm `volatile` hoặc từng `AtomicInteger`

### 8.1. `volatile` giải quyết điều gì?

Một trường `volatile` có những bảo đảm về visibility và thứ tự theo Java Memory Model. Ví dụ luồng khác đọc lại cùng trường volatile có thể nhìn thấy giá trị được công bố phù hợp với thứ tự đồng bộ. Nhưng hai trường:

```java
volatile int left;
volatile int right;
```

không tạo thành “cặp volatile”. Reader vẫn có thể quan sát `left` mới và `right` cũ. Đó chính là điều ví dụ `BrokenInvariantDemo` chứng minh.

Tương tự, một `volatile boolean ready` chỉ báo hiệu trạng thái đã được công bố **nếu giao thức writer/reader được thiết kế đúng**, chẳng hạn writer ghi toàn bộ dữ liệu rồi đặt `ready = true` và reader chỉ đọc sau khi thấy cờ. Nó không tự khắc phục việc writer tiếp tục cập nhật nhiều trường trong lúc reader đang đọc, và không thay thế synchronization nếu có nhiều lần cập nhật hay nhiều writer.

### 8.2. Vì sao mỗi trường atomic vẫn không đủ?

`AtomicInteger left` và `AtomicInteger right` bảo vệ các phép cập nhật riêng. Tuy nhiên, một reader lấy `left.get()` rồi `right.get()` vẫn có thể thấy dữ liệu từ hai thời điểm khác nhau. Không có một thao tác `getBothAtomically()` chung giữa hai `AtomicInteger` độc lập.

Muốn đảm bảo một snapshot nhất quán, dùng cùng monitor quanh cả cập nhật và đọc, hoặc gộp trạng thái vào một đối tượng bất biến rồi cập nhật tham chiếu nguyên tử.

### 8.3. Khóa writer mà không khóa reader

```java
synchronized (lock) {
    left -= amount;
    right += amount;
}
// Ở thread khác:
int total = left + right; // Đọc ngoài khóa: không có snapshot nhất quán.
```

Các dòng trên minh họa hai ngữ cảnh khác nhau. Với kiểu trường thường (`non-volatile`), đọc ngoài khóa còn thiếu bảo đảm visibility và có thể tạo data race. Ngay cả khi đổi hai trường thành volatile, việc đọc tách rời vẫn có nguy cơ broken invariant. **Hai phía của giao thức phải thống nhất**.

### 8.4. Khóa từng phép gán riêng lẻ

```java
synchronized (lock) {
    left -= amount;
}
synchronized (lock) {
    right += amount;
}
```

Mỗi phép gán được bảo vệ nhưng khóa được nhả **ở giữa**, cho reader cơ hội vào và quan sát trạng thái sai. Khóa phải bao trùm **toàn bộ nhóm thay đổi liên quan**, không chỉ từng phép đơn lẻ.

## 9. Exception, validation và bất biến ngay trong critical section

Một `synchronized` block không tự “rollback” trạng thái khi mã ném exception. Nếu writer cập nhật trường thứ nhất, rồi phép tính hoặc gọi API thứ hai ném lỗi, writer sẽ rời vùng khóa và nhả monitor — **trạng thái sai có thể trở thành trạng thái công khai lâu dài**.

Ví dụ nguy hiểm:

```java
synchronized (lock) {
    left -= amount;        // Đã thay đổi.
    checkExternalRule();   // Nếu ném exception...
    right += amount;       // ...không chạy.
}
```

Đoạn trên là mã minh họa. Để tránh, **kiểm tra mọi điều kiện có thể kiểm tra trước khi bắt đầu công bố thay đổi**, tính giá trị đích bằng biến cục bộ, rồi mới commit cả nhóm trường khi biết trạng thái mới hợp lệ:

```java
synchronized (lock) {
    if (amount < 0 || amount > left) {
        throw new IllegalArgumentException("invalid amount");
    }

    int nextLeft = Math.subtractExact(left, amount);
    int nextRight = Math.addExact(right, amount);

    if (nextLeft < 0 || nextRight < 0) {
        throw new IllegalStateException("invalid balance");
    }

    left = nextLeft;
    right = nextRight;
}
```

Đây là đoạn minh họa nằm trong phương thức của đối tượng sở hữu `left`, `right` và `lock`. `Math.subtractExact` và `Math.addExact` phát hiện overflow thay vì âm thầm tràn số. Mọi kiểm tra và phép tính có thể ném exception diễn ra **trước hai phép gán**, nên nếu lỗi, không trường nào thay đổi. Hai phép gán cuối vẫn có một trạng thái trung gian ở mức nội bộ, nhưng khi mọi reader đều lấy cùng lock, trạng thái đó không thể bị quan sát từ các thread khác theo giao thức này.

Nếu cần gọi dịch vụ ngoài, ghi tệp hoặc phát sự kiện trong giao dịch, hãy xem xét tính nguyên tử của **toàn bộ hệ thống**; `synchronized` chỉ điều phối thread trong JVM chứ không rollback tài nguyên bên ngoài.

## 10. Quan hệ với Java Memory Model

Java Memory Model (JMM) cung cấp các quy tắc để quyết định những thao tác nào có bảo đảm về thứ tự/visibility giữa thread. Với invariant nhiều trường, một số nguyên tắc then chốt:

- **Happens-before**: thao tác nhả một monitor xảy ra trước thao tác lấy tiếp theo trên cùng monitor; do đó reader lấy cùng monitor sẽ quan sát các ghi cần thiết của writer đã hoàn thành.
- **Volatile**: bảo đảm visibility/thứ tự ở cấp các thao tác volatile, nhưng không tạo tự động một “transaction” trên nhiều biến.
- **AtomicReference**: có thể công bố một snapshot bất biến thành một thao tác cập nhật tham chiếu atomic; nếu reader lấy tham chiếu **một lần**, nó đọc tất cả trường từ cùng snapshot.
- **Thread.start / Thread.join**: tạo các quan hệ happens-before nhất định, hữu ích khi chuyển trạng thái giữa giai đoạn trước/sau một worker. Nhưng nếu reader và writer thực sự đang chạy đồng thời, `join()` không bảo vệ các lần đọc giữa hai phép gán của writer.

Một cách diễn đạt khác là **linearizability**: từ góc nhìn của các lời gọi đồng thời, thao tác chuyển tiền nên có vẻ xảy ra tại một **điểm commit duy nhất**. Khi `transfer` và `snapshot` được bảo vệ cùng một monitor, các lời gọi đó có thể được sắp thứ tự thành các trạng thái hợp lệ. Khi dùng immutable snapshot + atomic CAS, điểm công bố tham chiếu là điểm chuyển trạng thái.

**Không nhầm linearizability của một thao tác trong một đối tượng Java với tính nguyên tử của giao dịch phân tán**. Nếu thao tác vừa sửa RAM vừa yêu cầu ngân hàng, mạng hay cơ sở dữ liệu khác cập nhật, các hệ thống đó cần cơ chế giao dịch/bù trừ của riêng chúng.

## 11. Thiết kế API khó dùng sai

Một số cải tiến giúp invariant dễ được giữ đúng ngay từ cấu trúc chương trình:

1. **Đóng gói trường liên quan** trong một lớp như `Ledger`. Không để caller sửa trực tiếp `left` hoặc `right`.
2. **Định nghĩa invariant thành câu rõ ràng**: ví dụ “mọi snapshot công khai phải có tổng tiền đúng và số dư không âm”.
3. **Expose thao tác nghiệp vụ** như `transfer(amount)` thay vì cho caller gọi `setLeft()` rồi `setRight()`.
4. **Expose một snapshot đầy đủ** thay vì hai getter đọc ở hai thời điểm khác nhau khi caller cần tính toán liên quan giữa chúng.
5. **Dùng một chiến lược đồng bộ nhất quán**. Không có nghĩa chỉ dùng một khóa cho toàn hệ thống; khóa nên bảo vệ đúng nhóm dữ liệu có cùng invariant.
6. **Kiểm tra lỗi trước khi commit** và bảo đảm exception không để lại trạng thái công khai sai.
7. **Kiểm thử bằng lịch chạy có kiểm soát** (latch/barrier) để chủ động lộ race condition, rồi bổ sung stress test khi cần. Stress test không thay thế lập luận về tính đúng đắn.

Chọn giải pháp theo phạm vi sở hữu dữ liệu: một đối tượng chia sẻ trong JVM có thể dùng monitor, một trạng thái nhỏ bất biến nhiều reader có thể dùng `AtomicReference`, còn tài nguyên nằm ngoài JVM cần cơ chế nhất quán của tầng lưu trữ/giao tiếp đó.

## 12. Chẩn đoán khi nghi ngờ broken invariant

Nếu thấy giá trị tổng, cặp `start/end`, phiên bản cấu hình hoặc số lượng không khớp trong log, hãy kiểm tra theo thứ tự:

- **Invariant là gì?** Viết dưới dạng mệnh đề có thể đánh giá: `left + right == 100`, `version == payload.version()`, v.v.
- **Có bao nhiêu trường phải thay đổi cùng nhau?** Vẽ các phép ghi theo thứ tự thực thi và liệt kê trạng thái trung gian.
- **Ai đọc những trường đó?** Reader có lấy từng getter tách rời? Có giữ cùng monitor không? Có lấy nhiều lần một tham chiếu thay đổi được không?
- **Tất cả writer có tuân theo cùng giao thức không?** Một đường cập nhật bỏ qua khóa là đủ tạo lỗ hổng.
- **Có exception giữa chừng không?** Mã có tính hết trạng thái mới trước khi commit không?
- **Có nhiều writer cạnh tranh không?** Nếu có, một phép gán volatile hay một cặp atomic đơn lẻ chưa giải quyết được lost update.
- **Có giới hạn ngoài JVM không?** Khóa Java chỉ bảo vệ các thread cùng dùng khóa đó, không thể khóa một tiến trình khác chỉ bằng cách tạo `new Object()`.

Cần phân biệt log bị thu thập ở hai thời điểm (ví dụ log `left` trước và `right` sau cập nhật) với snapshot thật sự mà chương trình sử dụng. Nếu muốn log tổng thể nhất quán, log một snapshot đầy đủ được đọc theo cùng giao thức đồng bộ.

## 13. Bài tập tự kiểm tra

**Tình huống A.** Hai trường `volatile int min`, `volatile int max` phải bảo đảm `min <= max`. Writer cập nhật `min = 8` rồi `max = 10` từ trạng thái `(1, 5)`. Reader có thể thấy `min=8,max=5` không?

**Trả lời:** Có. Mỗi trường volatile riêng lẻ không khiến hai phép ghi thành một thao tác. Nếu invariant phải luôn đúng với reader, cần đồng bộ nhóm cập nhật và nhóm đọc, hoặc công bố một snapshot bất biến `(8,10)`.

**Tình huống B.** `left` và `right` đều là `AtomicInteger`. Writer gọi `left.addAndGet(-20)` rồi `right.addAndGet(20)`. Invariant tổng có được bảo đảm không?

**Trả lời:** Không. Hai phép cộng/trừ riêng được thực hiện nguyên tử nhưng có một khoảng giữa chúng mà tổng bị lệch. Gộp dữ liệu và bảo vệ giao dịch/snapshot như một đơn vị logic.

**Tình huống C.** Writer thực hiện cả hai phép cập nhật trong `synchronized(lock)`, reader chỉ gọi hai getter mà mỗi getter `synchronized(lock)` riêng. Reader có thể nhìn thấy hai thế hệ khác nhau không?

**Trả lời:** Có. Monitor được nhả giữa hai getter; writer có thể cập nhật trong khoảng đó. Cần một getter `snapshot()` lấy cả hai dưới **một lần giữ lock**.

**Tình huống D.** Writer đã khóa đúng và kiểm tra input ban đầu, nhưng sau khi gán `left` thì một hàm bên ngoài ném exception. Khóa có tự rollback `left` không?

**Trả lời:** Không. Monitor vẫn được nhả khi thoát do exception nhưng không hoàn tác phép ghi đã xảy ra. Tính toán/kiểm tra trước commit; không thực hiện thao tác ngoài có thể thất bại giữa các phép gán trạng thái liên quan.

**Tình huống E.** `AtomicReference<Balances>` giữ một record bất biến. Reader gọi `state.get().left()` và `state.get().right()` tại hai thời điểm. Có chắc chắn snapshot nhất quán không?

**Trả lời:** Không. Hai lần `get()` có thể trả về hai record khác nhau. Lấy một biến cục bộ `Balances snapshot = state.get();` rồi đọc tất cả trường từ biến đó.

**Tình huống F.** Khi nào invariant có thể tạm sai ở bên trong `synchronized` mà API vẫn bảo đảm cho caller thấy trạng thái đúng?

**Trả lời:** Khi mọi lần quan sát trạng thái có liên quan đều phải lấy cùng monitor, không có callback/rò rỉ trạng thái giữa chừng, và mọi đường thoát (kể cả exception) chỉ công bố trạng thái hợp lệ. Reader không thể xen vào giữa các phép gán khi writer giữ monitor; tuy nhiên vẫn nên tính/kiểm tra trước khi gán để tránh lỗi để lại trạng thái sai.

## 14. Tổng kết

**Broken invariant khi cập nhật nhiều biến liên quan** xảy ra vì một thay đổi logic được triển khai bằng nhiều phép đọc/ghi, cho phép các thread khác nhìn thấy một tổ hợp giá trị không thuộc trạng thái hợp lệ. Từng phép gán đúng, từng trường `volatile` hoặc từng `AtomicInteger` **không bảo đảm** toàn bộ nhóm trường nhất quán.

Có hai hướng sửa thường dùng trong Java: **khóa toàn bộ thao tác cập nhật và đọc snapshot bằng cùng monitor/lock**, hoặc **tạo một snapshot bất biến và công bố nguyên tử tham chiếu tới snapshot đó**. Trước khi commit, phải kiểm tra đầu vào, xử lý khả năng exception, và xác định rõ tất cả writer/reader tuân theo cùng giao thức. Hãy bảo vệ **invariant của đối tượng như một đơn vị**, thay vì chỉ bảo vệ từng biến đơn lẻ.
