# Kiểm thử rỗng, nhiều lần mở rộng và thứ tự phần tử của ArrayDeque

## 1. Kiểm thử điều gì khi dùng ArrayDeque?

Một deque cho phép thêm và lấy phần tử ở cả hai đầu. Khi dùng `ArrayDeque` làm hàng đợi hoặc ngăn xếp, lỗi dễ xuất hiện ở chỗ chuyển từ rỗng sang một phần tử, lấy hết dữ liệu, hoặc trộn các thao tác ở hai đầu. Kiểm thử cần xác nhận **giá trị, thứ tự và trạng thái sau thao tác**, thay vì chỉ thấy chương trình không ném ngoại lệ.

Ba nhóm mục tiêu của bài này là:

- **Rỗng:** các phương thức báo rỗng đúng hợp đồng; deque có thể dùng lại sau khi lấy hết hoặc xóa hết.
- **Nhiều đợt tăng dữ liệu:** bắt đầu nhỏ rồi thêm lượng dữ liệu lớn, tiếp tục thêm sau khi đã lấy bớt; các giá trị cũ vẫn nguyên vẹn.
- **Thứ tự:** hàng đợi tuân thủ FIFO, ngăn xếp tuân thủ LIFO, và thao tác hai đầu cho ra đúng chuỗi dự kiến.

`ArrayDeque` tự tăng sức chứa khi cần và không cho phép phần tử `null`. Số truyền vào `new ArrayDeque<>(1)` là yêu cầu sức chứa ban đầu, không phải giới hạn chỉ được chứa một phần tử. Xem [ArrayDeque trong Java hiện hành](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).

Bài sử dụng chương trình kiểm thử độc lập trên Java 17+, không yêu cầu thư viện kiểm thử ngoài. Các nguyên tắc vẫn áp dụng khi chuyển từng phương thức kiểm thử thành một ca JUnit.

## 2. Xác định kết quả mong đợi trước khi viết mã

### Trạng thái rỗng có nhiều cách quan sát

| Thao tác | Kết quả khi deque rỗng |
| --- | --- |
| `size()` / `isEmpty()` | `0` / `true` |
| `peekFirst()`, `peekLast()` | `null`, không xóa |
| `pollFirst()`, `pollLast()` | `null` |
| `getFirst()`, `getLast()` | `NoSuchElementException` |
| `removeFirst()`, `removeLast()`, `pop()` | `NoSuchElementException` |

Không gom mọi phương thức vào một giả định “rỗng thì trả null”. Nhóm trả giá trị đặc biệt và nhóm ném ngoại lệ là hai hợp đồng khác nhau. `push` thêm vào đầu, `pop` lấy ở đầu; hàng đợi FIFO thường thêm cuối và lấy đầu. Xem [hợp đồng Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html).

Cần kiểm tra rỗng sau nhiều đường đi: vừa tạo mới, lấy phần tử duy nhất, lấy hết một tập lớn và gọi `clear()`. Những trạng thái có cùng kết quả công khai có thể được đi tới từ những lịch sử thao tác rất khác nhau.

### Giá trị và số lượng không thay thế được thứ tự

Giả sử thêm lần lượt `1, 2, 3`:

- Với `addLast` rồi `removeFirst`, phải nhận `1, 2, 3`.
- Với `push` rồi `pop`, phải nhận `3, 2, 1`.

Chỉ kiểm tra `size() == 3` không phân biệt hai chuỗi. Kiểm tra tổng bằng 6 cũng không phân biệt được. Muốn phát hiện đảo thứ tự, mất phần tử rồi lặp phần tử khác, hoặc lỗi ở giữa chuỗi, cần đối chiếu từng vị trí hoặc toàn bộ dãy.

## 3. Kiểm thử mở rộng nhưng không phụ thuộc chi tiết nội bộ

Một kịch bản hữu ích bắt đầu bằng sức chứa nhỏ, thêm hàng chục nghìn giá trị tăng dần, lấy bớt ở đầu, rồi thêm nhiều giá trị mới vào cuối. Cách này tạo áp lực lên việc duy trì thứ tự sau những lịch sử thêm–lấy khác nhau.

Trong các triển khai JDK thông dụng, lượng tăng lớn từ một deque nhỏ sẽ đi qua nhiều lần cấp thêm vùng lưu trữ. Tuy nhiên, API công khai không có phương thức trả về sức chứa hiện tại hoặc số lần mở rộng. Vì vậy:

- Đừng cố định rằng lần thêm thứ 17 luôn gây mở rộng.
- Đừng yêu cầu sức chứa luôn nhân đôi hay luôn là lũy thừa của hai.
- Đừng đọc trường riêng bằng reflection để kiểm tra mã sử dụng deque.
- Đừng kết luận `clear()` đã thu nhỏ bộ nhớ chỉ vì `size()` bằng 0.

Bộ kiểm thử này xác nhận **hành vi quan sát được khi dữ liệu tăng lớn**, không tuyên bố đã đo chính xác số lần cấp phát. Nếu đang bảo trì chính mã triển khai một deque, kiểm thử nội bộ cho thuật toán mở rộng là một lớp kiểm thử riêng.

Cùng một chương trình có thể kiểm tra nhiều quy mô như 1, 2, 32, 1.024 và 50.000 phần tử. Quy mô nhỏ giúp tìm lỗi biên; quy mô lớn giúp phát hiện việc dữ liệu bị hỏng sau lịch sử thao tác dài. Không dùng quy mô quá lớn tới mức kết quả chủ yếu phụ thuộc bộ nhớ của máy.

## 4. Bộ kiểm thử đầy đủ, chạy được

Lưu toàn bộ mã dưới đây vào `ArrayDequeChecks.java`.

Hàm `equal` ném `AssertionError` nếu sai. Vì không dùng câu lệnh `assert`, việc kiểm tra luôn hoạt động mà không cần cờ `-ea`.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Random;

public class ArrayDequeChecks {
    private static void equal(Object expected, Object actual, String where) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(where + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    private static void empty(Deque<Integer> q) {
        equal(0, q.size(), "empty size");
        equal(true, q.isEmpty(), "empty flag");
        equal(null, q.peekFirst(), "empty peekFirst");
        equal(null, q.peekLast(), "empty peekLast");
        equal(null, q.pollFirst(), "empty pollFirst");
        equal(null, q.pollLast(), "empty pollLast");
    }

    private static void noElement(Runnable operation, String where) {
        try {
            operation.run();
        } catch (NoSuchElementException expected) {
            return;
        }
        throw new AssertionError(where + ": missing NoSuchElementException");
    }

    private static void emptyAndSingle() {
        Deque<Integer> q = new ArrayDeque<>(1);
        empty(q);
        noElement(q::getFirst, "getFirst");
        noElement(q::getLast, "getLast");
        noElement(q::removeFirst, "removeFirst");
        noElement(q::removeLast, "removeLast");
        noElement(q::pop, "pop");

        q.addLast(10);
        equal(1, q.size(), "single size");
        equal(10, q.peekFirst(), "single first");
        equal(10, q.peekLast(), "single last");
        equal(1, q.size(), "peek preserves size");
        equal(10, q.pollFirst(), "single removal");
        empty(q);

        q.addFirst(20);
        equal(20, q.pollLast(), "opposite-end removal");
        empty(q);
    }

    private static void fifoGrowth() {
        Deque<Integer> q = new ArrayDeque<>(1);
        int n = 50_000;
        for (int i = 0; i < n; i++) {
            q.addLast(i);
        }
        equal(n, q.size(), "FIFO initial size");
        for (int i = 0; i < n / 2; i++) {
            equal(i, q.removeFirst(), "FIFO first phase " + i);
        }
        for (int i = n; i < 3 * n; i++) {
            q.addLast(i);
        }
        equal(3 * n - n / 2, q.size(), "FIFO second size");
        int next = n / 2;
        for (Integer value : q) {
            equal(next++, value, "FIFO iteration");
        }
        equal(3 * n, next, "FIFO iterator length");
        for (int i = n / 2; i < 3 * n; i++) {
            equal(i, q.removeFirst(), "FIFO drain " + i);
        }
        empty(q);
    }

    private static void lifoGrowth() {
        Deque<Integer> q = new ArrayDeque<>(1);
        int n = 50_000;
        for (int i = 0; i < n; i++) {
            q.push(i);
        }
        equal(n - 1, q.peek(), "stack top");
        equal(n, q.size(), "peek does not pop");
        for (int i = n - 1; i >= 0; i--) {
            equal(i, q.pop(), "LIFO pop " + i);
        }
        empty(q);
        noElement(q::pop, "pop after drain");
    }

    private static void mixedEndsAndReuse() {
        Deque<Integer> q = new ArrayDeque<>(2);
        q.addLast(1);
        q.addFirst(0);
        q.addLast(2);
        q.addFirst(-1);
        equal(List.of(-1, 0, 1, 2), new ArrayList<>(q), "forward");

        List<Integer> reverse = new ArrayList<>();
        q.descendingIterator().forEachRemaining(reverse::add);
        equal(List.of(2, 1, 0, -1), reverse, "backward");
        equal(4, q.size(), "iteration preserves size");

        equal(-1, q.removeFirst(), "mixed first");
        equal(2, q.removeLast(), "mixed last");
        q.addFirst(0);
        q.addLast(1);
        equal(List.of(0, 0, 1, 1), new ArrayList<>(q), "duplicates");
        q.clear();
        empty(q);

        q.addLast(99);
        equal(99, q.removeFirst(), "reuse after clear");
        empty(q);
    }

    private static void modelSequence() {
        Deque<Integer> actual = new ArrayDeque<>(1);
        Deque<Integer> expected = new LinkedList<>();
        Random random = new Random(2026L);

        for (int step = 0; step < 12_000; step++) {
            int value = random.nextInt(11) - 5;
            switch (random.nextInt(6)) {
                case 0 -> {
                    actual.addFirst(value);
                    expected.addFirst(value);
                }
                case 1 -> {
                    actual.addLast(value);
                    expected.addLast(value);
                }
                case 2 -> equal(expected.pollFirst(), actual.pollFirst(),
                        "model pollFirst step " + step);
                case 3 -> equal(expected.pollLast(), actual.pollLast(),
                        "model pollLast step " + step);
                case 4 -> equal(expected.peekFirst(), actual.peekFirst(),
                        "model peekFirst step " + step);
                case 5 -> equal(expected.peekLast(), actual.peekLast(),
                        "model peekLast step " + step);
                default -> throw new AssertionError("unreachable");
            }

            equal(expected.size(), actual.size(), "model size " + step);
            equal(new ArrayList<>(expected), new ArrayList<>(actual),
                    "model order " + step);

            if (step % 997 == 996) {
                expected.clear();
                actual.clear();
                empty(actual);
            }
        }

        List<Integer> reverseExpected = new ArrayList<>(expected);
        Collections.reverse(reverseExpected);
        List<Integer> reverseActual = new ArrayList<>();
        actual.descendingIterator().forEachRemaining(reverseActual::add);
        equal(reverseExpected, reverseActual, "model final reverse");
    }

    public static void main(String[] args) {
        emptyAndSingle();
        System.out.println("PASS empty and single");
        fifoGrowth();
        System.out.println("PASS FIFO growth");
        lifoGrowth();
        System.out.println("PASS LIFO growth");
        mixedEndsAndReuse();
        System.out.println("PASS mixed ends and reuse");
        modelSequence();
        System.out.println("PASS deterministic model");
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 ArrayDequeChecks.java
java ArrayDequeChecks
```

Kết quả chính xác khi tất cả ca kiểm thử thành công:

```text
PASS empty and single
PASS FIFO growth
PASS LIFO growth
PASS mixed ends and reuse
PASS deterministic model
```

Nếu một điều kiện sai, chương trình dừng ở `AssertionError` và không in các dòng PASS của những ca phía sau. Thông báo có ngữ cảnh như `FIFO drain 25000` hoặc `model order 713` để giúp tìm thao tác gây sai.

## 5. Mỗi ca kiểm thử chứng minh điều gì?

### emptyAndSingle: rỗng → một phần tử → rỗng

Ca này kiểm tra cả cách báo rỗng bằng `null` lẫn bằng ngoại lệ. Sau khi thêm một phần tử, nó kiểm tra hai đầu cùng nhìn thấy phần tử đó; đọc bằng `peek` không làm giảm số lượng.

Hai cách thêm–lấy được thử riêng: thêm cuối rồi lấy đầu, và thêm đầu rồi lấy cuối. Nếu chỉ thử một phía, chương trình có thể bỏ sót lỗi trong mã bao quanh deque ở phía còn lại.

Hàm `noElement` chỉ bắt đúng `NoSuchElementException`. Nó không dùng `catch (Exception)` rồi coi mọi lỗi là đạt: một ngoại lệ sai loại cũng phải khiến kiểm thử thất bại.

### fifoGrowth: thêm nhiều, lấy bớt, tiếp tục thêm

Giai đoạn đầu thêm `0..49.999`, sau đó lấy `0..24.999`. Giai đoạn tiếp theo thêm `50.000..149.999`.

Dãy còn lại phải là `25.000..149.999`, có 125.000 phần tử. Kiểm thử đối chiếu:

1. Kích thước sau từng đợt.
2. Từng giá trị khi lấy ở giai đoạn đầu.
3. Toàn bộ thứ tự khi duyệt mà chưa xóa.
4. Từng giá trị khi lấy hết ở giai đoạn cuối.
5. Trạng thái rỗng sau cùng.

Số đếm của vòng duyệt cũng được kiểm tra để tránh một iterator kết thúc sớm mà các giá trị đã duyệt vẫn có vẻ đúng. Đây là kiểm tra tính đúng đắn, không phải đo hiệu năng.

### lifoGrowth: giữ đúng đỉnh ngăn xếp khi dữ liệu tăng

`push(0)` đến `push(49_999)` khiến 49.999 trở thành đỉnh. Đọc đỉnh bằng `peek()` phải giữ nguyên kích thước; lần lượt `pop()` phải cho chuỗi giảm dần về 0.

Dùng cùng dữ liệu đầu vào nhưng kỳ vọng FIFO cho trường hợp này sẽ là kiểm thử sai. Trước khi đánh giá kết quả, cần xác định rõ chương trình đang dùng deque theo quy ước hàng đợi hay ngăn xếp.

### mixedEndsAndReuse: hai đầu, phần tử trùng và dùng lại

Chuỗi ngắn được viết tay để người đọc có thể tự tính:

```text
[] -> [1] -> [0, 1] -> [0, 1, 2] -> [-1, 0, 1, 2]
```

Ca kiểm thử duyệt thuận và nghịch, lấy ở cả hai đầu, rồi tạo dãy `[0, 0, 1, 1]`. Phần tử trùng giúp phát hiện các kiểm thử sai vô tình coi deque như tập hợp.

Sau `clear()`, tiếp tục thêm rồi lấy một phần tử mới để xác nhận deque vẫn dùng được. Không suy diễn gì về dung lượng mảng bên trong từ kết quả này.

### modelSequence: nhiều thao tác có kết quả đối chiếu

Ca cuối tạo 12.000 thao tác với hạt giống ngẫu nhiên cố định `2026L`. Một `LinkedList` được dùng qua giao diện `Deque` làm mô hình đối chiếu; chương trình gửi cùng thao tác tới hai cấu trúc và so sánh kết quả, kích thước, toàn bộ dãy sau mỗi bước.

Cách làm này mở rộng phạm vi lịch sử thao tác: thêm đầu, thêm cuối, lấy đầu, lấy cuối, nhìn đầu, nhìn cuối; định kỳ xóa rồi dùng tiếp. Hạt giống cố định giúp tái hiện lỗi. Các giá trị nằm trong khoảng nhỏ `-5..5` cố ý tạo nhiều phần tử trùng.

Mô hình đối chiếu không thay thế các ví dụ tính tay: nếu cả hai phía bị gọi sai cùng một cách, chúng có thể cùng cho một kết quả mà không phản ánh mục tiêu nghiệp vụ. Vì vậy bộ kiểm thử giữ cả các ca xác định ngắn và ca thao tác dài.

## 6. So sánh thứ tự cho đúng

Không viết kiểm thử như sau và kỳ vọng so sánh nội dung:

```java
// Khong dung de so sanh day phan tu cua ArrayDeque:
boolean same = new ArrayDeque<>(List.of(1, 2))
        .equals(new ArrayDeque<>(List.of(1, 2)));
```

`ArrayDeque` không định nghĩa `equals` theo dãy phần tử như `List`. Hai đối tượng chứa cùng dãy vẫn là hai đối tượng khác nhau khi so sánh theo danh tính. Đặc điểm chung này cũng được lưu ý trong [tài liệu Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html).

Trong chương trình, `new ArrayList<>(q)` lấy dãy theo thứ tự duyệt để so sánh bằng hợp đồng của danh sách. Với duyệt nghịch, chương trình thu kết quả của `descendingIterator()` vào danh sách riêng. Cách này diễn đạt trực tiếp điều cần kiểm thử.

Không dùng `containsAll` để xác nhận thứ tự hoặc số lần xuất hiện; không chuyển sang `Set` rồi so sánh vì sẽ làm mất thông tin phần tử trùng.

## 7. Những giới hạn cần hiểu khi đọc kết quả

- Bộ kiểm thử chạy trong một luồng. Nó không chứng minh `ArrayDeque` an toàn khi nhiều luồng cùng sửa.
- Không có đo thời gian; chạy nhanh hoặc chậm không quyết định ca kiểm thử tính đúng đắn đạt hay không.
- Số lần mở rộng, dung lượng thực tế và cách bố trí mảng không được suy ra từ stdout.
- Một hạt giống cố định tạo một lịch sử dài có thể tái hiện, không bao phủ mọi lịch sử có thể có.
- Chỉ in deque ra màn hình không tự tạo ra kiểm thử: cần có kỳ vọng rõ và điều kiện khiến chương trình thất bại khi sai.

## 8. Thực hành

1. Đổi quy mô lớn từ 50.000 xuống 1, rồi lên 100.000. Giải thích vì sao phần tính kích thước và ranh giới vòng lặp trong `fifoGrowth` vẫn đúng kể cả khi `n` lẻ.
2. Trong bản sao của ca FIFO, cố ý đổi `removeFirst()` thành `removeLast()`. Xác định kiểm tra nào phát hiện sai đầu tiên và vì sao chỉ so sánh kích thước không phát hiện được.
3. Viết thêm ca chỉ dùng `addFirst` và `removeLast` như một hàng đợi theo hướng ngược. Tự viết dãy mong đợi ngắn trước, rồi mới mở rộng dữ liệu.
4. Khi chuyển sang JUnit, giữ từng kịch bản độc lập và thông báo lỗi rõ. Không biến mọi lỗi ném ra thành “đạt”; kết quả mong đợi phải được xác định trước mỗi thao tác.
