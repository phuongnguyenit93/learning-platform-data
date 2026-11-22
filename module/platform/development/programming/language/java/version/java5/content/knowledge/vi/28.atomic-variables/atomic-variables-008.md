# Tính nguyên tử từng phần tử so với toàn bộ mảng

## 1. Đơn vị nguyên tử là gì?

Giả sử mảng hai phần tử biểu diễn số dư của hai tài khoản:

```text
[100, 100]
```

Yêu cầu nghiệp vụ là chuyển 10 đơn vị từ tài khoản 0 sang tài khoản 1, đồng thời giữ tổng bằng 200. Trạng thái hợp lệ sau chuyển là `[90, 110]`.

Một thao tác **nguyên tử (atomic)** có hiệu lực như một thao tác không thể bị quan sát ở trạng thái dở dang đối với đơn vị mà nó bảo vệ. Câu hỏi quan trọng là: **đơn vị ấy là một phần tử, một tham chiếu, hay cả một trạng thái nghiệp vụ?**

`AtomicIntegerArray` hỗ trợ cập nhật nguyên tử tại từng chỉ số. Điều đó không biến chuỗi cập nhật nhiều chỉ số thành một giao dịch. Bảo đảm tương tự ở mức phần tử áp dụng cho `AtomicLongArray` và `AtomicReferenceArray`. Đây là các API còn phù hợp trên Java hiện đại; ví dụ dưới đây chạy với Java 17+.

| Cách biểu diễn | Đơn vị được thao tác nguyên tử bảo vệ | Điều vẫn phải tự thiết kế |
| --- | --- | --- |
| `AtomicIntegerArray` | Một phần tử được truy cập qua phương thức phù hợp | Quan hệ giữa nhiều phần tử; ảnh chụp nhất quán |
| `AtomicReferenceArray<T>` | Tham chiếu tại một chỉ số | Trạng thái bên trong đối tượng; quan hệ giữa các chỉ số |
| `AtomicReference<int[]>` | Một tham chiếu tới phiên bản mảng | Không sửa mảng đã công bố; tạo phiên bản mới đúng cách |
| Mảng thường và một khóa chung | Cả vùng thao tác tuân thủ khóa | Mọi đường đọc/ghi liên quan đều phải dùng cùng khóa |

Đừng đánh đồng tên lớp chứa chữ `Atomic` với bảo đảm cho mọi thao tác nghiệp vụ dùng lớp ấy. [Tài liệu gói atomic](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html) mô tả phạm vi của các lớp nguyên tử.

## 2. Nguyên tử tại một chỉ số không ghép thành nguyên tử trên nhiều chỉ số

Với `AtomicIntegerArray balances = new AtomicIntegerArray(new int[]{100, 100});`, hai lệnh sau vẫn là hai thao tác tách biệt:

```java
balances.addAndGet(0, -10);
balances.addAndGet(1, 10);
```

Một luồng đọc có thể chạy giữa chúng:

| Thứ tự | Luồng chuyển tiền | Luồng đọc |
| --- | --- | --- |
| 1 | Chỉ số 0 đổi từ 100 thành 90 | |
| 2 | | Đọc chỉ số 0: 90 |
| 3 | | Đọc chỉ số 1: 100 |
| 4 | Chỉ số 1 đổi từ 100 thành 110 | |

Kết quả đọc là `[90, 100]`, tổng 190. Không có lần ghi nào bị “xé” ở cấp phần tử; vấn đề là bất biến nghiệp vụ chưa được bảo vệ trên toàn bộ thao tác chuyển tiền.

**Bất biến (invariant)** là điều kiện phải đúng ở những thời điểm mà bên ngoài được phép quan sát trạng thái, chẳng hạn “tổng số dư luôn bằng 200”. Nếu thuật toán cho phép bên ngoài quan sát giữa hai cập nhật thì `AtomicIntegerArray` tự nó không bảo đảm bất biến ấy.

Không thể ghép hai `compareAndSet(index, expected, update)` thành một CAS hai phần tử chỉ bằng cách gọi liên tiếp. CAS đầu thành công, CAS thứ hai có thể thất bại; người đọc vẫn có thể thấy cập nhật đầu. Tự hoàn tác sau thất bại cũng có thể đụng cập nhật của luồng khác. Cần một giao thức chung phù hợp thay vì coi hai lần CAS là một giao dịch.

### Chương trình tái hiện chắc chắn trạng thái trung gian

Lưu thành `ElementAtomicityDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class ElementAtomicityDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicIntegerArray balances =
                new AtomicIntegerArray(new int[]{100, 100});
        CountDownLatch debited = new CountDownLatch(1);
        CountDownLatch observed = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            balances.addAndGet(0, -10);
            debited.countDown();
            try {
                observed.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            balances.addAndGet(1, 10);
        });

        writer.start();
        debited.await();
        try {
            int first = balances.get(0);
            int second = balances.get(1);
            System.out.println("During: " + first + ", " + second);
            System.out.println("During total: " + (first + second));
        } finally {
            observed.countDown();
        }

        writer.join();
        System.out.println("After: " + balances.get(0)
                + ", " + balances.get(1));
    }
}
```

Chạy:

```shell
javac ElementAtomicityDemo.java
java ElementAtomicityDemo
```

Stdout khi chạy bình thường, không ngắt luồng từ bên ngoài:

```text
During: 90, 100
During total: 190
After: 90, 110
```

Hai `CountDownLatch` chủ động buộc luồng ghi dừng giữa hai lần cập nhật. Ví dụ chứng minh một thứ tự xen kẽ hợp lệ, không phụ thuộc may rủi của bộ lập lịch hay `Thread.sleep`. Các latch chỉ phục vụ thí nghiệm, không phải cách triển khai chuyển tiền.

## 3. “Đọc từng phần tử đúng” vẫn chưa tạo ra ảnh chụp đúng

**Ảnh chụp nhất quán (consistent snapshot)** biểu diễn trạng thái như tại một thời điểm chung. Vòng lặp gọi `get(i)` đọc mỗi phần tử ở một thời điểm riêng:

```java
// Đoạn minh họa; không bảo đảm một ảnh chụp của toàn mảng.
int total = 0;
for (int i = 0; i < balances.length(); i++) {
    total += balances.get(i);
}
```

Ngay cả khi luồng đọc không chạy đúng giữa hai lệnh cập nhật, nó vẫn có thể trộn giá trị từ các thời điểm khác nhau: đọc phần tử đầu trước chuyển tiền rồi đọc phần tử sau sau chuyển tiền, thu được `[100, 110]`. Tổng 210 không đại diện cho trạng thái nghiệp vụ hợp lệ trước hoặc sau chuyển.

Không nên dùng một vòng đọc như vậy để quyết định thanh toán, kiểm tra tổng hạn mức hoặc xác nhận một điều kiện liên quan nhiều vị trí. Nó có thể phù hợp với màn hình thống kê cho phép dữ liệu xấp xỉ, nếu yêu cầu đó được xác định rõ.

`toString()` không phải API chụp ảnh nguyên tử của toàn mảng. Sao chép bằng cách đọc lần lượt phần tử cũng không tự tạo giao dịch đọc. Hai lần quét thấy cùng kết quả chưa đủ để tự nhận là một thuật toán snapshot đúng trong mọi trường hợp; cần chứng minh giao thức đồng bộ, khả năng thay đổi rồi quay về giá trị cũ và điều kiện tiến triển.

Theo [AtomicIntegerArray](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html), `get(i)` và `set(i, value)` có hiệu ứng bộ nhớ tương ứng với truy cập volatile. Khả năng quan sát bộ nhớ ấy không gộp các lần gọi riêng thành một thao tác chung. Bài này dùng `get`, `set`, `addAndGet` và CAS thông thường; các biến thể truy cập yếu hơn cần được phân tích theo hợp đồng riêng.

## 4. Ngay trong một phần tử, chuỗi get rồi set vẫn có thể mất cập nhật

Đây cũng là một lỗi về chọn sai đơn vị nguyên tử:

```java
// Không phải phép tăng nguyên tử.
balances.set(0, balances.get(0) + 1);
```

Hai luồng cùng đọc 100 rồi cùng ghi 101: hai yêu cầu tăng nhưng giá trị chỉ tăng một lần. Từng lần đọc/ghi riêng lẻ vẫn đúng theo hợp đồng của chúng.

Khi chỉ cần tăng một phần tử độc lập, dùng:

```java
int after = balances.incrementAndGet(0);
```

Phương thức này ghép đọc–sửa–ghi của **một chỉ số**. Nó không bảo vệ một điều kiện liên quan đến chỉ số khác. Tương tự, `updateAndGet(i, f)` vẫn chỉ cập nhật vị trí `i`; không nên sửa các vị trí khác hoặc gửi thông báo trong hàm `f`, vì hàm cập nhật có thể được thực hiện lại khi có tranh chấp.

## 5. Cách bảo vệ nhiều phần tử: cùng dùng một khóa

Nếu nhiều phần tử thuộc cùng một bất biến, giải pháp trực tiếp là giữ mảng ở bên trong một đối tượng và dùng cùng một khóa cho cả đọc lẫn ghi.

Đây là một lớp hoàn chỉnh, có thể biên dịch riêng trong `LockedBalances.java`:

```java
public final class LockedBalances {
    private final Object lock = new Object();
    private final int[] balances = {100, 100};

    public void transfer(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        synchronized (lock) {
            if (balances[0] < amount) {
                throw new IllegalStateException("insufficient balance");
            }
            int destination = Math.addExact(balances[1], amount);
            balances[0] -= amount;
            balances[1] = destination;
        }
    }

    public int[] snapshot() {
        synchronized (lock) {
            return balances.clone();
        }
    }
}
```

Kiểm tra biên dịch:

```shell
javac LockedBalances.java
```

Lệnh thành công không in stdout. Lớp này cung cấp API sử dụng, không có `main` để chạy độc lập.

Bốn điểm quyết định tính đúng:

1. Kiểm tra đủ tiền và cập nhật hai phần tử nằm trong cùng khối khóa.
2. `snapshot()` cũng lấy đúng khóa ấy, nên không sao chép giữa hai bước chuyển.
3. Mảng nội bộ là `private`; kết quả đọc là bản sao, nên bên gọi không thể sửa dữ liệu thật mà bỏ qua khóa.
4. Tính giá trị có thể tràn bằng `Math.addExact` trước lần ghi đầu tiên, tránh ném lỗi sau khi đã trừ tiền.

Mảng thường đã đủ trong giao thức này. Thêm `AtomicIntegerArray` vào bên trong không thay thế yêu cầu khóa chung. Chỉ khóa luồng ghi còn luồng đọc đi thẳng vào mảng sẽ không đáp ứng giao thức.

Nếu chỉ cần bảo vệ một nhóm vị trí, có thể thiết kế khóa theo nhóm. Nhưng thao tác chạm nhiều nhóm phải có quy tắc phối hợp và thứ tự lấy khóa để tránh deadlock; tách nhỏ khóa không tự bảo vệ một bất biến trải qua nhiều nhóm.

## 6. Cách khác: công bố một phiên bản mảng mới qua AtomicReference

Thay vì sửa mảng đã công bố, ta có thể:

1. Đọc một tham chiếu tới phiên bản hiện hành.
2. Sao chép phiên bản ấy thành mảng mới.
3. Hoàn tất mọi sửa đổi trên bản mới còn riêng tư.
4. CAS tham chiếu cũ sang tham chiếu mới.
5. Nếu CAS thất bại, đọc phiên bản mới nhất và tính lại.

Điểm công bố của thao tác là lần CAS thành công. Với người đọc tuân thủ giao thức, phiên bản cũ và mới là hai trạng thái trọn vẹn. **Mảng đã công bố phải được đối xử như bất biến**: không luồng nào sửa lại nó, dù kiểu `int[]` bản thân vẫn là kiểu có thể sửa.

Lưu thành `WholeArraySnapshotDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

public class WholeArraySnapshotDemo {
    static final class Balances {
        private final AtomicReference<int[]> current =
                new AtomicReference<>(new int[]{2_000, 0});

        void transferOne() {
            while (true) {
                int[] before = current.get();
                if (before[0] == 0) {
                    throw new IllegalStateException("insufficient balance");
                }

                int[] after = before.clone();
                after[0]--;
                after[1]++;

                if (current.compareAndSet(before, after)) {
                    return;
                }
            }
        }

        int[] snapshot() {
            int[] version = current.get();
            return version.clone();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Balances balances = new Balances();
        Runnable work = () -> {
            for (int i = 0; i < 1_000; i++) {
                balances.transferOne();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        int[] snapshot = balances.snapshot();
        System.out.println(Arrays.toString(snapshot));
        System.out.println("Total: " + (snapshot[0] + snapshot[1]));
    }
}
```

Chạy:

```shell
javac WholeArraySnapshotDemo.java
java WholeArraySnapshotDemo
```

Stdout:

```text
[0, 2000]
Total: 2000
```

Giới hạn 2.000 lần chuyển và tổng ban đầu 2.000 là dữ kiện cố định của thí nghiệm; không dùng ví dụ này như một mô hình đầy đủ cho tiền tệ hay mọi miền giá trị số.

Tại sao `snapshot()` nhất quán? Nó giữ **một** tham chiếu `version`. Luồng khác có thể công bố phiên bản mới, nhưng không sửa phiên bản mà người đọc đang sao chép. Bản sao trả ra cũng ngăn bên gọi sửa mảng nằm trong `current`.

Tại sao cần CAS khi có nhiều luồng ghi? Nếu dùng `get()` → sao chép → `set(after)`, hai luồng có thể cùng tính từ một phiên bản cũ rồi ghi đè kết quả của nhau. CAS kiểm tra tham chiếu hiện hành vẫn chính là `before`; nếu đã đổi, phép cập nhật phải tính lại trên trạng thái mới. `AtomicReference.compareAndSet` so sánh tham chiếu bằng `==`, không so nội dung từng phần tử.

Để giữ chứng minh đơn giản, giao thức trên luôn tạo một mảng mới và không công bố lại các mảng cũ. Không được sửa trực tiếp `current.get()[0]`: đó là bỏ qua cả cơ chế công bố phiên bản lẫn CAS.

Các bảo đảm của tham chiếu và hàm cập nhật được mô tả trong [AtomicReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).

### Chi phí và giới hạn

- Mỗi lần thử sao chép một mảng `n` phần tử tốn O(n), tạo thêm rác cho GC; CAS thất bại làm tăng số lần sao chép.
- Một tham chiếu chung khiến các cập nhật ở những chỉ số khác nhau vẫn tranh chấp với nhau.
- Người đọc lấy được một phiên bản nhất quán, nhưng phiên bản ấy có thể đã cũ khi phương thức trả về. “Nhất quán” không có nghĩa là “không thể lỗi thời”.
- CAS không làm một luồng cụ thể chắc chắn hoàn thành trong số bước hữu hạn; dưới tranh chấp nó có thể phải thử lại nhiều lần.
- Không đặt gửi email, ghi log tính phí hoặc cập nhật hệ thống ngoài vào phần tính toán có thể thử lại. Thành công trong bộ nhớ cũng không tạo giao dịch chung với cơ sở dữ liệu hay dịch vụ ngoài.

Với trạng thái ít trường cố định, một đối tượng bất biến có các trường đặt tên rõ, chẳng hạn `record Balances(int first, int second)`, có thể dễ hiểu hơn mảng. Nếu một record chứa trường `int[]`, record không tự làm các phần tử mảng bất biến; vẫn cần sao chép và đóng gói đúng.

## 7. Những cách hiểu sai cần tránh

### volatile int[] làm mọi phần tử volatile

```java
private volatile int[] values = new int[2];
```

`volatile` áp dụng cho biến tham chiếu `values`. Nó không tự biến `values[0]++` thành phép tăng nguyên tử và không tạo giao dịch trên hai phần tử.

Có thể công bố một mảng mới đã chuẩn bị xong bằng ghi volatile, nếu giao thức không sửa mảng sau công bố. Nhưng nhiều luồng cùng đọc–tính–ghi vẫn cần cơ chế ngăn mất cập nhật; `volatile` không cung cấp CAS.

### AtomicReferenceArray làm đối tượng bên trong an toàn đồng thời

```java
// Ví dụ minh họa về phạm vi bảo vệ.
AtomicReferenceArray<StringBuilder> slots =
        new AtomicReferenceArray<>(1);
slots.set(0, new StringBuilder());
slots.get(0).append("x");
```

Cần import `java.util.concurrent.atomic.AtomicReferenceArray` khi dùng đoạn này. Lần lấy tham chiếu không làm thao tác `append` trên cùng một `StringBuilder` an toàn khi nhiều luồng cùng sửa. Cần đối tượng bất biến hoặc cơ chế đồng bộ riêng cho trạng thái đối tượng.

### Chụp xong rồi kiểm tra là đủ cho hành động tiếp theo

Ảnh chụp nhất quán chỉ nói về trạng thái được đọc. Nếu đọc đủ tiền rồi gọi một thao tác trừ độc lập, luồng khác có thể đổi số dư giữa hai bước. Điều kiện và cập nhật phải cùng khối khóa hoặc cùng một lần chuyển phiên bản CAS.

### synchronized trên một nơi tự bảo vệ mọi người dùng mảng

Khóa chỉ có tác dụng khi những đường truy cập liên quan đều tuân thủ nó. Khóa khác nhau, tham chiếu mảng bị rò rỉ hoặc đọc ngoài khóa đều phá vỡ lập luận bảo vệ chung.

## 8. Chọn giải pháp theo quan hệ dữ liệu

| Nhu cầu thực tế | Hướng lựa chọn |
| --- | --- |
| Mỗi ô là một bộ đếm độc lập; chấp nhận tổng tại nhiều thời điểm | `AtomicIntegerArray` / `AtomicLongArray` và phép cập nhật nguyên tử từng ô |
| Cập nhật một nhóm ô và đọc trạng thái nhóm phải nhất quán | Khóa chung cho cả cập nhật và đọc |
| Đọc nhiều, ghi ít; có thể sao chép toàn bộ trạng thái | Công bố phiên bản bất biến qua `AtomicReference`, CAS khi cần phối hợp nhiều người ghi |
| Thay từng tham chiếu độc lập tới đối tượng bất biến | `AtomicReferenceArray<T>` |
| Nghiệp vụ cần đồng thời thay đổi dữ liệu ngoài bộ nhớ tiến trình | Thiết kế giao dịch/phối hợp ở tầng sở hữu dữ liệu đó |

Không chọn giải pháp chỉ theo số lượng phần tử. Hãy bắt đầu từ câu hỏi: “Những giá trị nào phải được quan sát và thay đổi cùng nhau?”

## 9. Tự kiểm tra

1. Hai lời gọi `addAndGet` ở hai chỉ số có giữ tổng không đổi trước mọi người đọc không?  
   Không. Người đọc có thể chạy giữa hai lần cập nhật.

2. `get(0) + get(1)` có luôn là tổng tại một thời điểm chung không?  
   Không. Mỗi lời gọi là một lần đọc riêng.

3. Chỉ khóa phương thức `transfer`, còn `snapshot` đọc không khóa, đã đủ chưa?  
   Chưa. Hai bên phải cùng tuân thủ giao thức khóa.

4. Trong mô hình phiên bản, có được trả thẳng mảng nội bộ để tiết kiệm sao chép không?  
   Nếu bên gọi có thể sửa nó thì không. Mảng bị sửa sau công bố làm mất nền tảng của snapshot bất biến.

5. Khi nào `AtomicReference<int[]>` có thể bảo vệ một thay đổi nhiều ô?  
   Khi mọi thay đổi được chuẩn bị trong phiên bản riêng, mảng đã công bố không bị sửa, và việc chuyển phiên bản được phối hợp đúng, chẳng hạn bằng CAS cho nhiều người ghi.

Bài học cốt lõi: phạm vi của thao tác nguyên tử phải trùng với phạm vi của bất biến cần bảo vệ. Nguyên tử từng phần tử là công cụ phù hợp cho dữ liệu độc lập; trạng thái có quan hệ cần một giao thức đọc–ghi chung.
