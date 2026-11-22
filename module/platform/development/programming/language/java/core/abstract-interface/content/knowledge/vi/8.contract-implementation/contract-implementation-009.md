# Giữ đúng ý nghĩa hợp đồng bên cạnh việc biên dịch thành công

## Mục tiêu

Trong Java, một lớp có thể `implements` interface thành công, khai báo đủ phương thức, biên dịch không lỗi và vẫn **vi phạm điều mà người sử dụng interface có quyền kỳ vọng**. Bài này giúp bạn phân biệt hợp đồng về **hình dạng API** với hợp đồng về **hành vi**, diễn đạt quy tắc hành vi rõ ràng, thiết kế triển khai có thể thay thế cho nhau và kiểm chứng các quy tắc ấy bằng ví dụ Java 17+.

Đây là kỹ năng trọng tâm khi triển khai interface hoặc kế thừa lớp abstract: trình biên dịch bảo vệ được một phần cấu trúc chương trình; chất lượng triển khai còn phụ thuộc vào ngữ nghĩa mà API cam kết.

## 1. Một hợp đồng có nhiều lớp

Xét interface sau:

```java
interface Counter {
    void increase();
    int value();
}
```

Một lớp `Counter` triển khai `increase()` bằng cách đặt giá trị về `0` vẫn có thể biên dịch, vì Java kiểm tra phương thức có tồn tại và tương thích chữ ký, kiểu trả về, quyền truy cập, một số ràng buộc exception và quan hệ kiểu. Nhưng nếu ý nghĩa được công bố là “`increase()` tăng bộ đếm lên một đơn vị”, cách cài đặt đó sai hợp đồng.

Cần phân biệt:

| Lớp hợp đồng | Ví dụ | Trình biên dịch Java có tự bảo đảm? |
| --- | --- | --- |
| Hợp đồng kiểu/chữ ký | Có `increase()`, `value()` trả `int`, phương thức override hợp lệ | Có, trong phạm vi quy tắc ngôn ngữ |
| Tiền điều kiện (precondition) | Tham số đầu vào phải dương, chuỗi không được `null` | Không tự suy ra từ chữ ký thông thường |
| Hậu điều kiện (postcondition) | Sau `increase()`, giá trị mới bằng giá trị cũ cộng một | Không |
| Bất biến (invariant) | Bộ đếm luôn không âm | Không |
| Thứ tự/quan hệ giữa các lần gọi | Hàng đợi trả phần tử theo FIFO | Không |
| Tác dụng phụ và lỗi | Một lần gọi thất bại không làm đổi trạng thái; ném exception đã mô tả | Không đầy đủ |
| Đặc tính vận hành đã hứa | An toàn luồng, tính nguyên tử, ổn định thứ tự hoặc tính nhất quán | Không tự bảo đảm chỉ nhờ `implements` |

Trong một interface, tên phương thức, kiểu tham số và kiểu trả về là **bề mặt** của hợp đồng. Ý nghĩa của thao tác, giới hạn dữ liệu, tác động đến trạng thái, lỗi có thể xảy ra và những điều *không* được phép làm mới xác định liệu một triển khai có dùng đúng được hay không.

`@Override` giúp phát hiện sai lệch về phương thức override, nhưng nó không chứng minh phương thức đó thực hiện đúng chức năng.

## 2. Hợp đồng hành vi là điều người gọi có thể quan sát

Một hợp đồng hành vi tốt trả lời được các câu hỏi cụ thể:

- **Đầu vào hợp lệ:** Có chấp nhận `null`, chuỗi trống, số âm hoặc giá trị ngoài miền không?
- **Kết quả:** Giá trị trả về có ý nghĩa gì? Có được trả `null` hoặc giá trị đặc biệt không?
- **Trạng thái trước và sau:** Phương thức có thêm, bớt, thay thế hoặc giữ nguyên dữ liệu nào?
- **Thứ tự:** Với các thao tác liên tiếp, kết quả có phụ thuộc vào thứ tự gọi không?
- **Lỗi:** Điều gì xảy ra với đầu vào sai? Ném exception nào? Trạng thái có còn nguyên không?
- **Tính lặp:** Gọi lại có gây thêm tác dụng phụ không? Nếu idempotent thì được bảo đảm trong phạm vi nào?
- **Đồng thời:** Nếu nhiều luồng cùng gọi, API có hứa thread-safe/atomic không? Nếu không hứa, không được mặc định là có.

Ví dụ hợp đồng cho một hàng đợi công việc:

> `offer(task)` thêm tác vụ hợp lệ vào cuối hàng đợi. `poll()` lấy và xóa tác vụ có mặt lâu nhất chưa được lấy (FIFO). Khi rỗng, `poll()` trả `Optional.empty()`. `offer(null)` ném `NullPointerException` và không làm thay đổi nội dung. Hợp đồng này không cam kết thread-safe.

Những câu trên kiểm tra được bằng hành vi quan sát qua API, thay vì phụ thuộc vào chi tiết như dùng `ArrayDeque`, mảng, danh sách liên kết hay cơ sở dữ liệu.

**Độ rõ ràng của lời hứa rất quan trọng:** nếu chưa quy định FIFO, người viết một triển khai LIFO có thể hiểu khác mà vẫn cảm thấy đúng. Vì vậy cần ghi hợp đồng hành vi ngay tại interface hoặc tài liệu API liên quan.

## 3. Ví dụ chạy được: cùng interface, một triển khai sai ý nghĩa

Lưu toàn bộ mã sau trong một tệp `ContractDemo.java`.

```java
import java.util.ArrayDeque;
import java.util.Objects;
import java.util.Optional;

public class ContractDemo {
    /** FIFO; null không hợp lệ; poll() rỗng trả Optional.empty(). */
    interface WorkQueue {
        void offer(String task);
        Optional<String> poll();
    }

    static final class FifoQueue implements WorkQueue {
        private final ArrayDeque<String> tasks = new ArrayDeque<>();

        @Override
        public void offer(String task) {
            tasks.addLast(Objects.requireNonNull(task, "task"));
        }

        @Override
        public Optional<String> poll() {
            return Optional.ofNullable(tasks.pollFirst());
        }
    }

    // Hợp lệ về kiểu nhưng sai yêu cầu FIFO.
    static final class LifoQueue implements WorkQueue {
        private final ArrayDeque<String> tasks = new ArrayDeque<>();

        @Override
        public void offer(String task) {
            tasks.addLast(Objects.requireNonNull(task, "task"));
        }

        @Override
        public Optional<String> poll() {
            return Optional.ofNullable(tasks.pollLast());
        }
    }

    static void check(String name, WorkQueue queue) {
        queue.offer("A");
        queue.offer("B");
        String first = queue.poll().orElseThrow();
        String second = queue.poll().orElseThrow();
        boolean fifo = first.equals("A") && second.equals("B");
        boolean empty = queue.poll().isEmpty();
        boolean nullRejected = false;
        try {
            queue.offer(null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        System.out.printf("%s: fifo=%s, empty=%s, nullRejected=%s%n",
                name, fifo, empty, nullRejected);
    }

    public static void main(String[] args) {
        check("FifoQueue", new FifoQueue());
        check("LifoQueue", new LifoQueue());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 ContractDemo.java
java ContractDemo
```

Kết quả stdout đã được kiểm tra:

```text
FifoQueue: fifo=true, empty=true, nullRejected=true
LifoQueue: fifo=false, empty=true, nullRejected=true
```

### Đọc kết quả theo hợp đồng

1. **Cả hai lớp đều biên dịch.** Mỗi lớp đều cài đủ `offer` và `poll`, dùng kiểu trả về chính xác, quyền truy cập override hợp lệ.
2. **`FifoQueue` thực hiện FIFO.** Chèn cuối bằng `addLast()` và lấy đầu bằng `pollFirst()` nên hai lời gọi trả `"A"` rồi `"B"`.
3. **`LifoQueue` vi phạm FIFO.** `pollLast()` trả `"B"` trước `"A"`. Đây là lỗi **ngữ nghĩa**, không phải lỗi chữ ký. Vì vậy `fifo=false` dù chương trình chạy được.
4. **Cả hai trả empty khi đã lấy hết phần tử.** Hai phần tử đều được lấy ra trước lần `poll()` kiểm tra rỗng, nên `empty=true`.
5. **Cả hai từ chối `null`.** `Objects.requireNonNull` ném `NullPointerException` trước khi thêm, đúng hành vi đã ghi; `nullRejected=true`.

Ví dụ `check` là phép kiểm tra minh họa, **không phải bộ kiểm thử đầy đủ**. Nó chưa bao quát nhiều phần tử, nhiều chuỗi thao tác, việc khôi phục sau lỗi hay xử lý đồng thời. Mục tiêu là cho thấy sự khác biệt giữa “biên dịch thành công” và “đáp ứng hợp đồng”.

Có thể sửa `LifoQueue.poll()` thành `tasks.pollFirst()` để tuân thủ FIFO. Nhưng trong ứng dụng thật, hãy sửa tại nguyên nhân thiết kế và kiểm tra tất cả các đường đi qua API.

## 4. Kiểu tham chiếu chung không tự bảo đảm tính thay thế được

Mã gọi thường chỉ thấy interface:

```java
WorkQueue queue = obtainQueue();
queue.offer("A");
queue.offer("B");
String next = queue.poll().orElseThrow();
```

Đây là đoạn mã minh họa được đặt bên trong ngữ cảnh có `WorkQueue` và `obtainQueue()` phù hợp; bản thân nó không phải chương trình độc lập. Nếu mọi triển khai `WorkQueue` tôn trọng FIFO, `next` phải là `"A"`. Người gọi có thể thay `FifoQueue` bằng một triển khai khác mà không đổi giả định nghiệp vụ.

Nguyên tắc thay thế Liskov (Liskov Substitution Principle, LSP) diễn đạt mong muốn đó: nơi cần một đối tượng theo hợp đồng của kiểu cha/interface, đối tượng của kiểu con/triển khai phải sử dụng được **mà không làm mất những tính chất hợp đồng đã được cam kết**.

Với mỗi phương thức, cách diễn đạt thực tế là:

- **Không thắt chặt tiền điều kiện** so với hợp đồng đã công bố. Nếu `offer` cam kết chấp nhận mọi chuỗi không null, triển khai không được tự ý chỉ chấp nhận tối đa 10 ký tự mà không được hợp đồng cho phép.
- **Không làm yếu hậu điều kiện.** Nếu `poll` cam kết FIFO, triển khai không được đổi sang LIFO hoặc trả một phần tử tùy ý.
- **Duy trì bất biến trạng thái.** Nếu hợp đồng yêu cầu không mất phần tử chưa lấy, một lần lỗi không được âm thầm xóa hàng đợi.
- **Giữ các cam kết về exception và tác dụng phụ.** Nếu API hứa không thay đổi trạng thái khi thất bại, triển khai không được sửa dữ liệu rồi báo lỗi.

Các tiêu chí trên áp dụng cả cho `extends` trong lớp abstract và override trong class, không riêng interface. Chúng là tiêu chí về thiết kế và hành vi; trình biên dịch Java không có bộ suy luận tổng quát để chứng minh chúng.

## 5. Phân định rõ tiền điều kiện, hậu điều kiện, bất biến

### Tiền điều kiện: người gọi phải cung cấp gì?

Giả sử `reserve(String sku, int quantity)` chỉ chấp nhận `sku` không trống và `quantity > 0`. Tài liệu nên nêu rõ đầu vào sai sẽ bị từ chối như thế nào, chẳng hạn `IllegalArgumentException`, thay vì để từng lớp tự diễn giải.

Không nên đặt một điều kiện mới âm thầm trong một implementation, ví dụ giới hạn `quantity <= 5` trong khi interface công bố không có giới hạn đó. Người dùng thay implementation sẽ gặp lỗi dù đã tuân thủ tiền điều kiện của interface.

### Hậu điều kiện: sau khi gọi, điều gì phải đúng?

Nếu hợp đồng `reserve` nói “trả `true` khi giữ chỗ thành công và giảm tồn kho đúng `quantity`; trả `false` khi không đủ hàng và giữ nguyên tồn kho”, một triển khai luôn trả `true` nhưng không giảm tồn kho sẽ sai. Nó vẫn có thể đúng về kiểu trả về `boolean`.

### Bất biến: thuộc tính nào phải đúng mọi lúc?

Với dữ liệu tồn kho, `stock >= 0` có thể là bất biến. Khi xử lý trạng thái qua nhiều thao tác, bất biến phải tiếp tục được giữ sau mỗi thao tác công khai, kể cả nhánh ngoại lệ theo quy định.

Không biến mọi chi tiết cấu trúc nội bộ thành bất biến API. Ví dụ dùng `ArrayDeque` chỉ là cách cài đặt; thứ tự FIFO mới là đặc tính mà người gọi phải quan sát được.

## 6. Exception, `null` và thất bại cũng là hợp đồng

Hợp đồng nên quy định điều có thể xảy ra ở **đường lỗi**, không chỉ đường thành công.

Ví dụ với `WorkQueue`:

| Tình huống | Hành vi được yêu cầu |
| --- | --- |
| `offer("A")` trên queue còn dùng được | Lưu phần tử `"A"` ở cuối thứ tự FIFO |
| `poll()` khi queue có phần tử | Trả phần tử cũ nhất chưa lấy, đồng thời xóa nó |
| `poll()` khi queue rỗng | Trả `Optional.empty()`; không trả `null` |
| `offer(null)` | Ném `NullPointerException`, không thêm phần tử |
| Nhiều luồng truy cập | Chưa được bảo đảm; cần thỏa thuận thêm nếu ứng dụng có nhu cầu |

Điều này tránh các phiên bản triển khai trả `null` thay `Optional.empty()`, hoặc lặng lẽ bỏ qua `offer(null)`. Các lựa chọn kia có thể vẫn biểu diễn được trong Java, nhưng **khác quy tắc người dùng đang dựa vào**.

Nếu API công bố một exception cụ thể, nên kiểm tra cả loại exception lẫn sự thay đổi trạng thái. `throws` trong Java thể hiện một số ràng buộc checked exception; nó không tự mô tả đầy đủ unchecked exception, thông điệp lỗi hoặc tính nguyên tử của thao tác.

Khi trạng thái có thể thay đổi, cần nói rõ thất bại là “không thay đổi gì”, “thành công một phần” hay “có thể đã commit”. Đây là sự khác biệt lớn với thao tác mạng, ghi tệp và giao dịch cơ sở dữ liệu.

## 7. Ghi hợp đồng ngay ở nơi khai báo interface

Hãy viết tài liệu trước khi có nhiều implementation. Javadoc giúp đưa quy tắc đến người implement lẫn người gọi.

Ví dụ sau là một **khai báo minh họa độc lập**, không kết hợp cùng khai báo `WorkQueue` trong `ContractDemo.java`:

```java
import java.util.Optional;

/**
 * Hàng đợi tác vụ theo FIFO.
 *
 * <p>Không cam kết an toàn luồng. Mọi implementation phải giữ thứ tự
 * chèn của các phần tử chưa được lấy ra.</p>
 */
interface WorkQueue {
    /**
     * Thêm tác vụ vào cuối hàng đợi.
     *
     * @param task tác vụ không null
     * @throws NullPointerException nếu task là null;
     *                              trong trường hợp này queue không đổi
     */
    void offer(String task);

    /**
     * Lấy và xóa phần tử được thêm sớm nhất còn lại.
     *
     * @return phần tử vừa lấy, hoặc Optional.empty() nếu rỗng
     */
    Optional<String> poll();
}
```

Đối với một interface cần công khai cho package khác, sử dụng `public` ở top-level interface (và đặt trong tệp Java tương ứng). Mức truy cập của kiểu là vấn đề riêng với ý nghĩa hành vi.

Viết Javadoc càng cụ thể càng tốt: thứ tự, nullability, hậu điều kiện, biên lỗi, tính đồng thời và giá trị trả về. Tránh câu mơ hồ như “xử lý hợp lý”, “trả kết quả đúng” hoặc “thường trả phần tử tiếp theo”. Nếu behavior còn có điều kiện, hãy nêu điều kiện đó.

**Tài liệu là nguồn cam kết, nhưng chưa phải cơ chế kiểm chứng tự động.** Cần dùng các phép kiểm thử được rút trực tiếp từ chính quy tắc đã công bố.

## 8. Thiết kế kiểm thử hợp đồng dùng chung cho mọi implementation

Một cách hiệu quả là viết **contract tests**: cùng một bộ thử chạy cho mọi implementation của interface, kể cả các phiên bản mới thêm sau này.

Với `WorkQueue`, bộ kiểm thử cần quan sát:

1. Queue mới rỗng: `poll()` trả `Optional.empty()`.
2. Thêm một phần tử: `offer("A")` rồi `poll()` trả `"A"`, lần kế tiếp rỗng.
3. Thêm nhiều phần tử: lần lượt `A, B, C` rồi lấy ra đúng `A, B, C`.
4. Chèn thêm sau khi đã lấy: `offer(A), offer(B), poll(), offer(C)` phải tiếp tục trả `B, C`.
5. Thêm `null`: ném `NullPointerException`; những phần tử có sẵn vẫn còn với thứ tự không đổi.
6. Những kịch bản khác trong tài liệu: tính lặp, giới hạn dung lượng, lỗi tài nguyên hoặc đồng thời (nếu có cam kết).

Bạn có thể dùng JUnit 5 với các test được tham số hóa hoặc một hàm kiểm thử nhận `Supplier<WorkQueue>` để tạo queue sạch cho mỗi ca thử. `Supplier` ở đây cần tạo instance mới; tái sử dụng một queue đã bị test trước làm thay đổi trạng thái và khiến test khó tin cậy.

Pseudo-flow cho contract test:

```text
Danh sách các implementation được chấp nhận
    -> tạo một instance mới cho từng test
    -> thực hiện cùng chuỗi thao tác công khai
    -> so sánh đầu ra, trạng thái quan sát và exception
    -> báo lỗi khi bất kỳ implementation nào phá cam kết
```

Bộ `check` ở ví dụ chạy được sử dụng chính tư tưởng này ở phạm vi hẹp. Với hệ thống thật, test nên **thất bại rõ ràng** khi kỳ vọng không đúng (ví dụ assertion của JUnit), thay vì chỉ in `false`.

Kiểm thử hành vi cũng có thể sử dụng property-based testing: tạo nhiều chuỗi `offer/poll` hợp lệ, so sánh kết quả với mô hình tham chiếu FIFO. Dù vậy, không có bộ kiểm thử hữu hạn nào chứng minh tuyệt đối mọi triển khai luôn đúng với mọi dữ liệu và lịch chạy đồng thời.

## 9. Default method và abstract class không miễn trừ hợp đồng

### `default` trong interface

Một `default method` có thân giúp tái sử dụng logic, nhưng logic mặc định cũng phải đúng ý nghĩa được công bố. Implementation override `default` được phép đổi thuật toán, **không được tự ý đổi lời hứa API**.

Ví dụ nếu một interface công bố `isEmpty()` đúng khi không còn phần tử, việc một implementation override trả `true` vô điều kiện có thể biên dịch nhưng sai hợp đồng, trừ khi những ngữ cảnh đặc biệt được quy định rõ.

### Lớp abstract

Một abstract class có thể cung cấp trạng thái và logic chung. Việc kế thừa phương thức có sẵn giảm số lượng mã phải viết, nhưng không tự bảo đảm lớp con giữ tiền điều kiện, hậu điều kiện và bất biến khi override hoặc thêm đường đi thay đổi trạng thái.

Không đánh đồng “được thừa kế code”, “triển khai interface” và “đúng hành vi”. Một lớp có thể dùng lại toàn bộ code sai hoặc override một phần nhỏ làm sai quy tắc tổng thể.

### Composition

Nếu nhiều triển khai cần giữ các quy tắc chung, có thể gom thuật toán hoặc bước xác thực thành đối tượng cộng tác, hàm tiện ích nội bộ hoặc template method phù hợp. Việc tái sử dụng logic chung giúp giảm lệch hành vi, nhưng vẫn cần test ở biên interface.

## 10. Một số bẫy thiết kế thường gặp

**Bẫy 1 — Trùng chữ ký, khác ý nghĩa.** Định nghĩa `sort()` nhưng implementation chỉ đảo ngược danh sách; chương trình có thể chạy, nhưng người gọi tưởng kết quả đã sắp xếp tăng dần.

**Bẫy 2 — Thêm hạn chế không có trong contract.** Interface chấp nhận số lượng bất kỳ trong miền `int` hợp lệ, implementation âm thầm giới hạn tối đa 100. Đây là việc tăng tiền điều kiện khiến lời gọi hợp lệ theo interface thất bại.

**Bẫy 3 — Hậu điều kiện yếu đi.** Interface hứa `save` thành công nghĩa là dữ liệu đã được ghi bền vững, implementation chỉ đẩy vào bộ đệm dễ mất mà vẫn trả thành công. Nếu hệ thống chỉ hứa “đã xếp hàng ghi”, phải diễn đạt chính xác mức bảo đảm đó.

**Bẫy 4 — Hành vi sai trên trường hợp biên.** `poll()` có phần tử chạy đúng nhưng khi rỗng trả `null` thay `Optional.empty()`; ứng dụng lỗi ở nhánh ít xảy ra.

**Bẫy 5 — Exception làm hỏng trạng thái.** Xóa trước một phần dữ liệu rồi ném lỗi, trong khi hợp đồng đã cam kết thao tác thất bại phải giữ nguyên trạng thái.

**Bẫy 6 — Dùng `instanceof` để bù cho implementation lệch chuẩn.** Nếu client liên tục kiểm tra “nếu là lớp A thì FIFO, nếu là lớp B thì LIFO”, interface không còn tạo ra một hợp đồng có thể thay thế đáng tin. Chỉ nên phân nhánh theo khả năng được mô hình hóa rõ ràng, thay vì che giấu sai lệch.

**Bẫy 7 — Hứa thread-safe theo suy đoán.** Đúng chức năng khi chạy một luồng không có nghĩa đúng trong nhiều luồng. Nếu API phải thread-safe, cần xác định rõ điều kiện đồng thời, khả năng quan sát trạng thái và phép kiểm thử phù hợp.

**Bẫy 8 — Thay đổi tài liệu mà không đổi kiểm thử.** Khi công bố hợp đồng mới hoặc sửa hợp đồng, kiểm tra các implementation và bộ test liên quan. Không nên chỉnh Javadoc đơn thuần để hợp thức hóa một lỗi đã xuất hiện.

## 11. Quy trình thực hành khi triển khai một interface

1. **Đọc tên thao tác và Javadoc** để xác định những gì client có quyền dựa vào, đặc biệt các trạng thái biên.
2. **Viết trước danh sách tiền điều kiện, hậu điều kiện và bất biến.** Với thao tác có lỗi, xác định rõ trạng thái sau thất bại.
3. **Chọn thuật toán/cấu trúc dữ liệu** thỏa các điều kiện ấy. Ví dụ FIFO với `ArrayDeque` nên thêm cuối và lấy đầu.
4. **Dùng `@Override` và kiểm tra biên dịch** để bảo đảm phù hợp về cấu trúc; sau đó kiểm thử ngữ nghĩa riêng.
5. **Chạy contract tests trên tất cả implementation**, kể cả implementation giả cho test và các lớp tối ưu hiệu năng.
6. **Kiểm tra đường lỗi và tương tác giữa nhiều lần gọi**, không chỉ một “happy path”.
7. **Đánh giá thay thế implementation**: client có còn dùng đúng được khi không biết lớp thực thi cụ thể không?

Để luyện tập, hãy thử tạo thêm `PriorityQueueWork` triển khai `WorkQueue` và sắp tác vụ theo độ ưu tiên. Hỏi: nếu `WorkQueue` hiện cam kết FIFO, liệu đây có phải implementation hợp lệ? **Không**, nếu việc đổi thứ tự làm vi phạm FIFO. Muốn hỗ trợ hàng đợi ưu tiên, cần định nghĩa hợp đồng khác hoặc sửa thiết kế một cách có chủ đích và cập nhật toàn bộ client/test phụ thuộc.

## Ghi nhớ

`implements` và việc biên dịch thành công chứng minh lớp tương thích với **kiểu** của interface ở mức ngôn ngữ; chúng không chứng minh lớp tuân thủ **ý nghĩa nghiệp vụ**. Hợp đồng có giá trị khi người gọi có thể tin vào các cam kết quan sát được — đầu vào hợp lệ, kết quả, thứ tự, trạng thái, lỗi và những thuộc tính vận hành đã công bố — bất kể đối tượng đến từ implementation nào. Viết rõ các cam kết đó và kiểm tra chúng bằng cùng bộ contract tests là nền tảng để interface thật sự cho phép thay thế triển khai an toàn.
