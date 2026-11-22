# Vai trò của Iterable<T> và Iterator<T>

## 1. Vì sao Java tách nguồn duyệt khỏi bộ lặp?

Khi viết:

```java
for (String name : names) {
    System.out.println(name);
}
```

ta muốn xử lý các phần tử mà không phải biết chúng được lưu trong mảng động, danh sách liên kết hay được tính ra khi cần.

Để làm được điều đó với một đối tượng, Java cần tách hai trách nhiệm:

- **Nguồn có thể duyệt — `Iterable<T>`:** cung cấp một cách bắt đầu việc duyệt phần tử kiểu `T`.
- **Bộ lặp — `Iterator<T>`:** giữ trạng thái của một lần duyệt và cung cấp phần tử tiếp theo.

Có thể hình dung một tuyển tập dữ liệu và một dấu vị trí đang đọc. Tuyển tập mô tả nguồn; dấu vị trí cho biết một người đọc cụ thể đã đi tới đâu. Hai dấu vị trí có thể cùng đọc một nguồn nhưng tiến độc lập.

Điều này giải thích vì sao một container thường là `Iterable`, còn mỗi lần duyệt sử dụng một `Iterator` riêng.

Bài dùng các hợp đồng đang áp dụng trong Java hiện nay, với ví dụ chạy trên JDK 17 trở lên.

## 2. Hai hợp đồng đứng cạnh nhau

| Đặc điểm | Iterable<T> | Iterator<T> |
| --- | --- | --- |
| Vai trò chính | Cung cấp bộ lặp cho nguồn | Điều khiển và giữ trạng thái một lần duyệt |
| Phương thức cốt lõi | `iterator()` | `hasNext()`, `next()` |
| Kết quả quan trọng | `Iterator<T>` | Một phần tử `T` từ `next()` |
| Liên hệ với for-each | Đối tượng có kiểu phù hợp làm nguồn trực tiếp | Không tự là nguồn for-each chỉ vì là Iterator |
| Trạng thái “đã đọc đến đâu” | Không nhất thiết nằm ở chính nguồn | Thường thuộc đối tượng iterator |
| Khả năng xóa | Không phải chức năng cốt lõi của Iterable | `remove()` là thao tác tùy chọn |
| Gói | `java.lang` | `java.util` |

`Iterable` được dùng trực tiếp mà không cần import riêng vì thuộc `java.lang`. `Iterator` thường được import bằng `import java.util.Iterator;`.

Phần `<T>` giữ kiểu của giá trị được lấy ra. Với `Iterable<String>`, `iterator()` cung cấp một `Iterator<String>`; `next()` của bộ lặp đó trả `String`.

Không cần kiểu thô rồi ép từng phần tử từ `Object` về kiểu mong muốn.

## 3. Iterable<T>: lời hứa có thể cung cấp bộ lặp

Phương thức cốt lõi có hình dạng:

```java
Iterator<T> iterator();
```

Đây là khai báo phương thức của hợp đồng, không phải một chương trình độc lập.

Một lớp thực hiện `Iterable<String>` phải cung cấp `iterator()` trả một `Iterator<String>` phù hợp. Nhờ đó, mã sử dụng có thể lặp mà không phụ thuộc cách cài đặt lưu trữ.

`Iterable` không bắt buộc có:

- `size()`.
- Truy cập theo chỉ số.
- Thêm hoặc xóa dữ liệu.
- Một danh sách chứa sẵn tất cả phần tử.
- Nguồn hữu hạn.
- Bảo đảm dữ liệu không thay đổi hoặc an toàn luồng.

Vì vậy, một lớp biểu diễn khoảng số có thể là `Iterable<Integer>` mà không cần cấp phát một danh sách tất cả số trong khoảng.

Một tập hợp thường thực hiện `Iterable`, nhưng một đối tượng `Iterable` không nhất thiết phải là `Collection`.

Vai trò tham gia for-each được nêu trong [API Iterable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Iterable.html).

### Có thể duyệt lại hay không là một phần hợp đồng của nguồn

Với danh sách thông thường hoặc khoảng số bất biến của bài, mỗi lần gọi `iterator()` có thể tạo một bộ lặp mới từ đầu.

Tuy nhiên, chỉ nhìn thấy kiểu `Iterable<T>` chưa đủ kết luận mọi nguồn đều lặp lại được cùng một tập giá trị vô hạn lần. Một nguồn có thể phụ thuộc dữ liệu bên ngoài, thay đổi theo thời gian hoặc có hợp đồng tiêu thụ một lần.

Nếu API yêu cầu duyệt nhiều lần hoặc lặp lồng nhau, cần biết nguồn có hỗ trợ các lần duyệt độc lập hay không. Với một lớp tự thiết kế để có khả năng đó, hãy tạo trạng thái riêng cho từng iterator.

## 4. Iterator<T>: trạng thái và bước tiến của một lần duyệt

### 4.1. hasNext() hỏi còn phần tử hay không

```java
boolean hasNext();
```

Nó cho biết một lời gọi `next()` có thể trả phần tử tiếp theo thay vì báo hết dữ liệu.

Trong cách cài đặt đúng, gọi `hasNext()` nhiều lần không làm mất các phần tử mà người dùng chưa nhận qua `next()`.

Một nguồn tính toán lười có thể cần chuẩn bị hoặc đệm dữ liệu trong lúc kiểm tra. Điều cần giữ là ý nghĩa quan sát được: việc hỏi “còn không?” không được tự bỏ qua phần tử kế tiếp.

### 4.2. next() nhận phần tử và tiến trạng thái

```java
T next();
```

Mỗi lần gọi thành công, nó trả phần tử tiếp theo và cập nhật vị trí của chính bộ lặp.

Ví dụ với khoảng `[2, 5)`:

```text
current = 2
    |
    | next() tra 2
    v
current = 3
    |
    | next() tra 3
    v
current = 4
    |
    | next() tra 4
    v
current = 5, hasNext() = false
```

`[2, 5)` nghĩa là có `2`, `3`, `4` và không có `5`.

### 4.3. Khi hết dữ liệu, next() phải báo đúng

Nếu không còn phần tử, `next()` ném `NoSuchElementException`.

Không trả `null` để báo hết dữ liệu. Một nguồn hợp lệ có thể có phần tử `null`, nên giá trị dữ liệu và trạng thái kết thúc phải được phân biệt.

Người gọi thường dùng:

```java
while (cursor.hasNext()) {
    Integer value = cursor.next();
    System.out.println(value);
}
```

Đoạn giả định `cursor` là `Iterator<Integer>`. Kiểu trả về có thể chứa `null` nếu hợp đồng nguồn cho phép; ví dụ khoảng số ở bài không tạo `null`.

Người dùng cũng có thể gọi `next()` trực tiếp khi biết chắc còn dữ liệu. Vì vậy, một iterator tự viết vẫn phải kiểm tra trạng thái trong `next()`, không chỉ tin rằng người gọi luôn gọi `hasNext()` trước.

Các quy tắc hết dữ liệu nằm trong [API Iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html).

## 5. For-each kết nối hai vai trò như thế nào?

Với nguồn có kiểu `Iterable<T>`, có thể hiểu một vòng for-each là:

1. Xác định đối tượng nguồn một lần.
2. Lấy bộ lặp từ nguồn.
3. Kiểm tra `hasNext()`.
4. Lấy phần tử bằng `next()` rồi thực hiện thân vòng lặp.
5. Lặp lại cho tới khi hết hoặc có lệnh kết thúc luồng.

Một vòng for-each cụ thể lấy bộ lặp khi bắt đầu vòng đó; nó không gọi lại `iterator()` để bắt đầu từ đầu ở mỗi phần tử.

Vì vậy:

- Hai vòng for-each nối tiếp nhau trên nguồn có thể lặp lại sẽ có hai trạng thái duyệt khác nhau.
- Trong vòng lặp lồng nhau, mỗi lần bắt đầu vòng trong có một lần yêu cầu iterator cho vòng trong.
- `break` kết thúc vòng hiện tại; nó không mặc định làm rỗng nguồn hay thay đổi các iterator khác.

Một biến chỉ có kiểu `Iterator<T>` không tự dùng được ở bên phải dấu `:`:

```java
Iterator<Integer> cursor = List.of(1, 2).iterator();
// for (int value : cursor) { } // Khong bien dich
```

Đây là đoạn minh họa với các import `Iterator` và `List`. Khi có iterator tường minh, dùng các thao tác của nó để điều khiển lần duyệt.

Mảng là trường hợp riêng của ngôn ngữ: mảng dùng được với for-each mà không thực hiện `Iterable`. Đừng suy ra mọi nguồn for-each đều có phương thức `iterator()` gọi được ở mã nguồn.

Chi tiết ngôn ngữ nằm ở [JLS: The enhanced for statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2).

## 6. Chương trình đầy đủ: nguồn khoảng số và các bộ lặp độc lập

Ta thiết kế `IntRange`:

- Giữ hai mốc của khoảng.
- Không giữ vị trí duyệt chung.
- Mỗi lần `iterator()` tạo một bộ lặp có `current` riêng.
- `next()` kiểm tra hết dữ liệu.
- Không hỗ trợ xóa vì không có một tập hợp lưu trữ để xóa phần tử.

Lưu thành `IterableIteratorRolesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.StringJoiner;

public class IterableIteratorRolesDemo {
    static final class IntRange implements Iterable<Integer> {
        private final int startInclusive;
        private final int endExclusive;

        IntRange(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start must not exceed end");
            }
            this.startInclusive = startInclusive;
            this.endExclusive = endExclusive;
        }

        @Override
        public Iterator<Integer> iterator() {
            return new Iterator<>() {
                private int current = startInclusive;

                @Override
                public boolean hasNext() {
                    return current < endExclusive;
                }

                @Override
                public Integer next() {
                    if (!hasNext()) {
                        throw new NoSuchElementException("range exhausted");
                    }
                    return current++;
                }
            };
        }
    }

    static int sum(Iterable<Integer> source) {
        int total = 0;
        for (int value : source) {
            total += value;
        }
        return total;
    }

    static int consumeRemaining(Iterator<Integer> cursor) {
        int total = 0;
        while (cursor.hasNext()) {
            total += cursor.next();
        }
        return total;
    }

    public static void main(String[] args) {
        IntRange range = new IntRange(2, 5);
        Iterator<Integer> first = range.iterator();
        Iterator<Integer> second = range.iterator();

        System.out.println("hasNext one = " + first.hasNext());
        System.out.println("hasNext two = " + first.hasNext());
        System.out.println("first cursor = " + first.next());
        System.out.println("second cursor = " + second.next());
        System.out.println("first cursor again = " + first.next());
        System.out.println("first remaining sum = "
                + consumeRemaining(first));
        System.out.println("exhausted remaining sum = "
                + consumeRemaining(first));

        try {
            first.next();
        } catch (NoSuchElementException exception) {
            System.out.println("next after exhaustion rejected");
        }

        System.out.println("whole range sum one = " + sum(range));
        System.out.println("whole range sum two = " + sum(range));

        Iterator<Integer> partial = range.iterator();
        partial.next();
        System.out.println("sum after consuming first = "
                + consumeRemaining(partial));

        IntRange small = new IntRange(1, 3);
        StringJoiner pairs = new StringJoiner(" | ");
        for (int left : small) {
            for (int right : small) {
                pairs.add(left + ":" + right);
            }
        }
        System.out.println("nested pairs = " + pairs);

        Iterator<Integer> unsupported = range.iterator();
        unsupported.next();
        try {
            unsupported.remove();
        } catch (UnsupportedOperationException exception) {
            System.out.println("range remove unsupported");
        }

        List<Integer> mutable = new ArrayList<>(List.of(1, 2, 3, 4));
        Iterator<Integer> removable = mutable.iterator();
        while (removable.hasNext()) {
            int value = removable.next();
            if (value % 2 == 0) {
                removable.remove();
            }
        }
        System.out.println("after iterator removal = " + mutable);

        IntRange empty = new IntRange(4, 4);
        System.out.println("empty hasNext = " + empty.iterator().hasNext());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror IterableIteratorRolesDemo.java
java IterableIteratorRolesDemo
```

Stdout:

```text
hasNext one = true
hasNext two = true
first cursor = 2
second cursor = 2
first cursor again = 3
first remaining sum = 4
exhausted remaining sum = 0
next after exhaustion rejected
whole range sum one = 9
whole range sum two = 9
sum after consuming first = 7
nested pairs = 1:1 | 1:2 | 2:1 | 2:2
range remove unsupported
after iterator removal = [1, 3]
empty hasNext = false
```

Các hàm tính tổng dùng `int` cho những khoảng nhỏ của ví dụ. Nếu áp dụng cho nguồn có tổng vượt miền `int`, cần chọn kiểu và chính sách kiểm tra tràn phù hợp.

### 6.1. Vì sao hai lần hasNext không bỏ qua số 2?

Cách cài đặt chỉ so sánh `current < endExclusive` và không cập nhật `current`. Hai lần hỏi đều trả `true`; `next()` đầu tiên vẫn trả `2`.

Nếu cập nhật vị trí ngay trong `hasNext()` mà không giữ đúng dữ liệu đệm, một vòng lặp có thể mất phần tử chỉ vì người dùng kiểm tra thêm. Đó là lỗi hợp đồng.

### 6.2. Vì sao first và second cùng bắt đầu từ 2?

`iterator()` tạo một đối tượng mới mỗi lần. Trường `current` nằm trong đối tượng iterator vô danh, không nằm trong `IntRange`.

`first.next()` thay đổi trạng thái của `first`. `second.next()` dùng trạng thái của `second` nên vẫn nhận `2`.

Hai iterator chia sẻ thông tin bất biến về mốc đầu/cuối, nhưng không chia sẻ dấu vị trí đang đọc.

### 6.3. Vì sao lặp lồng nhau tạo đủ bốn cặp?

Nguồn `small` là khoảng `[1, 3)`, có hai giá trị `1` và `2`.

Mỗi lượt của vòng ngoài, vòng trong xin một iterator mới từ `small`. Nó có thể duyệt lại đủ `1` và `2`, tạo các cặp:

```text
1:1
1:2
2:1
2:2
```

Nếu các vòng dùng chung một trạng thái duyệt duy nhất, vòng trong có thể tiêu thụ dữ liệu mà vòng ngoài đang chờ. Kết quả sẽ không còn thể hiện các lần duyệt độc lập.

## 7. Trạng thái đã tiêu thụ thuộc về iterator, không phải tên biến

Hai hàm trong chương trình có hợp đồng khác nhau.

### sum(Iterable<Integer>) bắt đầu từ nguồn

```java
static int sum(Iterable<Integer> source)
```

Hàm dùng for-each, nên yêu cầu một iterator khi bắt đầu. Với `IntRange` của bài, mỗi lần gọi đều nhận một lần duyệt mới từ đầu.

Do đó, `sum(range)` trả `9` trong cả hai lần gọi.

Không suy rộng kết quả này cho một nguồn tùy biến không cam kết khả năng duyệt lại.

### consumeRemaining(Iterator<Integer>) tiêu thụ phần còn lại

```java
static int consumeRemaining(Iterator<Integer> cursor)
```

Hàm làm việc với chính trạng thái được truyền vào. Nếu người gọi đã lấy số `2`, hàm chỉ còn nhận `3` và `4`, nên tổng là `7`.

Sau khi đã tiêu thụ hết, gọi lại trên cùng iterator cho kết quả `0` trong ví dụ. Iterator không tự quay về đầu.

Tên hàm hoặc tài liệu nên thể hiện việc **tiêu thụ phần còn lại**, vì đây là một thay đổi trạng thái quan trọng đối với người gọi.

### Hai biến có thể vẫn là cùng một iterator

```java
Iterator<Integer> first = range.iterator();
Iterator<Integer> alias = first;
```

Ở đây, `first` và `alias` là hai tham chiếu tới cùng một đối tượng. Gọi `alias.next()` cũng tiến trạng thái mà `first` quan sát.

Để có lần duyệt độc lập trên `IntRange`, cần gọi `range.iterator()` lần nữa, không chỉ gán thêm một tên biến.

## 8. Nguồn tính toán lười không cần lưu sẵn toàn bộ phần tử

`IntRange` chỉ lưu mốc đầu và cuối. Mỗi iterator chỉ cần lưu `current`.

Nó không tạo `List<Integer>` chứa tất cả số trước khi bắt đầu duyệt. Phần tử được cung cấp theo yêu cầu của `next()`.

Tách nguồn và trạng thái giúp API sử dụng cùng một cách duyệt cho:

- Dữ liệu có sẵn trong tập hợp.
- Một chuỗi giá trị được tính dần.
- Một cách nhìn đã lọc hoặc biến đổi từ nguồn khác.
- Một nguồn có chi phí lấy từng phần tử.

Điều này không có nghĩa mọi `hasNext()` hoặc `next()` đều rẻ. Một nguồn ngoài bộ nhớ có thể cần đọc hoặc tính toán. Chữ ký interface không bảo đảm độ phức tạp hay thời gian thực thi.

Một nguồn cũng có thể không hữu hạn. Hàm cố tiêu thụ tới hết, như tính tổng toàn bộ, sẽ không kết thúc nếu nguồn tiếp tục cung cấp phần tử mãi. Hợp đồng hữu hạn cần được biết từ nguồn hoặc giới hạn bởi bên sử dụng.

## 9. remove() là tùy chọn và liên kết với next()

`Iterator.remove()` dùng để xóa phần tử cuối cùng đã được iterator trả về khỏi cấu trúc nền, **nếu iterator hỗ trợ**.

Trong chương trình:

- Iterator của `IntRange` không ghi đè `remove`, nên dùng cách cài đặt mặc định ném `UnsupportedOperationException`.
- Iterator của `ArrayList` có hỗ trợ xóa. Sau khi `next()` trả một số chẵn, `remove()` xóa đúng phần tử đó. Kết quả còn `[1, 3]`.

Đối với một iterator hỗ trợ thao tác này, quy tắc sử dụng thông thường là:

1. Gọi `next()` để nhận phần tử.
2. Có thể gọi `remove()` một lần cho phần tử vừa trả về.
3. Không gọi `remove()` hai lần liên tiếp mà chưa có `next()` mới.
4. Không gọi `remove()` trước khi có phần tử nào được `next()` trả về.

Sử dụng sai trạng thái có thể gây `IllegalStateException`. Với iterator không hỗ trợ xóa, thao tác có thể bị từ chối bằng `UnsupportedOperationException`; không cần đợi một lần xóa thực sự xảy ra.

Không xóa trực tiếp qua danh sách bên ngoài rồi cho rằng bộ lặp tự điều chỉnh. Khả năng thay đổi cấu trúc trong lúc duyệt phụ thuộc hợp đồng cụ thể của nguồn.

Với bộ lặp của nhiều tập hợp thông thường, thay đổi qua đường không được hỗ trợ có thể dẫn tới `ConcurrentModificationException`. Cơ chế phát hiện đó không thay thế đồng bộ giữa luồng và không phải một bảo đảm phát hiện mọi thay đổi sai.

## 10. forEach và forEachRemaining cũng thể hiện hai vai trò

Trong API hiện hành:

- `Iterable.forEach(action)` thao tác ở mức nguồn; cách cài đặt mặc định duyệt thông qua iterator của nguồn.
- `Iterator.forEachRemaining(action)` thao tác trên **phần còn lại của iterator hiện tại**.

Ví dụ:

```java
Iterator<Integer> cursor = range.iterator();
cursor.next();
cursor.forEachRemaining(System.out::println);
```

Với khoảng `[2, 5)`, đoạn này in `3` rồi `4`. Số `2` đã được tiêu thụ trước đó.

Không hiểu `forEachRemaining` như một cách tạo lần duyệt mới. Nó tiếp tục chính bộ lặp đang giữ.

Nếu action ném ngoại lệ, quá trình dừng và trạng thái iterator có thể đã tiến. Không có cơ chế tự quay lại đầu hoặc hoàn tác các hành động đã chạy.

Không suy luận thêm rằng sau `forEachRemaining` luôn được phép gọi `remove` theo cùng cách như sau một `next` tường minh. Hợp đồng của `Iterator` không quy định một bảo đảm tổng quát như vậy cho mọi cách cài đặt.

## 11. Những bảo đảm không tự có từ hai interface

### Không tự bảo đảm snapshot

Hai iterator có thể độc lập về vị trí nhưng vẫn quan sát cùng một nguồn dữ liệu có thể thay đổi. Độc lập trạng thái duyệt không đồng nghĩa mỗi iterator giữ một bản sao dữ liệu.

### Không tự bảo đảm an toàn luồng

Một `Iterator` thông thường là một đối tượng có trạng thái thay đổi. Chia sẻ cùng iterator giữa các luồng không tự trở nên an toàn vì nguồn là `Iterable`.

Ngay cả khi mỗi luồng có iterator riêng, khả năng đọc và sửa dữ liệu nền vẫn phụ thuộc hợp đồng cụ thể của nguồn.

### Không tự đóng tài nguyên

`Iterable` và `Iterator` tự chúng không yêu cầu hợp đồng đóng tài nguyên. For-each không mặc định gọi `close()` khi kết thúc hoặc khi gặp `break`.

Nếu một nguồn gắn với tài nguyên có thể đóng, phải quản lý vòng đời theo kiểu và API cụ thể của nguồn, thường bằng một phạm vi quản lý tài nguyên rõ ràng.

### Không tự cho phép duyệt ngược hoặc truy cập ngẫu nhiên

`Iterator` cơ bản đi qua phần tử tiếp theo. Nó không có `previous` hoặc truy cập theo chỉ số.

Một API cần khả năng đó phải sử dụng hợp đồng phù hợp khác, chẳng hạn `ListIterator` cho một số cách duyệt danh sách.

### Không tự bảo đảm mỗi lần iterator() có cùng dữ liệu

Nguồn có thể thay đổi hoặc tính lại giá trị. Với `IntRange` bất biến của bài, cùng mốc cho cùng chuỗi số; đây là đặc điểm được thiết kế cho nguồn này.

## 12. Lỗi thường gặp khi tự viết hoặc sử dụng

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt vị trí duyệt vào nguồn rồi dùng chung cho mọi lần lặp | Vòng lặp lồng nhau tác động lẫn nhau | Với nguồn hỗ trợ duyệt độc lập, tạo trạng thái riêng mỗi iterator |
| hasNext làm mất phần tử | Hỏi trạng thái cũng làm thay đổi kết quả nhận được | Tách việc chuẩn bị dữ liệu khỏi việc tiêu thụ quan sát được |
| next trả null khi hết | Không phân biệt được phần tử null với kết thúc | Ném `NoSuchElementException` |
| Chỉ kiểm tra hết dữ liệu trong hasNext | next trực tiếp có thể trả sai | Kiểm tra trạng thái trong next |
| Giữ một iterator rồi mong for-each mới sẽ quay lại đầu | Dùng lại trạng thái đã tiêu thụ | Yêu cầu iterator mới từ nguồn có hỗ trợ |
| Truyền Iterator cho hàm nhưng giấu việc tiêu thụ | Người gọi bất ngờ mất phần dữ liệu còn lại | Công bố rõ hợp đồng “remaining” |
| Mặc định mọi remove đều được hỗ trợ | Gặp ngoại lệ ở nguồn không cho xóa | Theo hợp đồng iterator |
| Cho rằng Iterable đồng nghĩa Collection | Đòi size hoặc get mà nguồn không cung cấp | Nhận đúng mức API cần dùng |

Đối với một nguồn cố ý chỉ tiêu thụ được một lần, trả cùng một iterator có thể là một quyết định riêng được tài liệu hóa. Điều sai là hứa duyệt độc lập hoặc hứa lặp lại rồi lại chia sẻ trạng thái khiến người dùng không thể dự đoán hành vi.

## 13. Chọn kiểu tham số theo quyền mà phương thức cần

Nếu phương thức chỉ cần bắt đầu duyệt một nguồn, nhận `Iterable<T>` có thể rộng và rõ hơn việc bắt buộc `List<T>`.

Nếu phương thức cần tiếp tục một lượt duyệt đã bắt đầu, nhận `Iterator<T>` làm rõ rằng nó làm việc với trạng thái hiện có.

Nếu cần biết kích thước, thêm/xóa hoặc truy cập theo chỉ số, `Iterable` có thể chưa đủ. Khi đó, chọn `Collection`, `List` hoặc một hợp đồng miền thực sự cung cấp các khả năng cần thiết.

Không đổi mọi API thành `Iterable` chỉ vì kiểu đó tổng quát hơn. Chữ ký nên diễn tả đủ khả năng mà thuật toán thực sự yêu cầu và không đòi thêm điều không cần.

## 14. Thực hành tự kiểm tra

### Bài 1: Ai giữ vị trí?

Trong `IntRange`, nên đặt `current` ở nguồn hay ở mỗi iterator nếu muốn hai vòng lặp độc lập?

**Đáp án:** ở mỗi iterator. Nguồn chỉ giữ mô tả khoảng; từng lần duyệt giữ trạng thái riêng.

### Bài 2: Gọi hasNext hai lần

Tại sao `first.next()` đầu tiên vẫn trả `2` sau hai lần gọi `hasNext()`?

**Đáp án:** hỏi “còn phần tử không?” không tiêu thụ mất phần tử kế tiếp. Trong cài đặt của bài, `hasNext` chỉ so sánh mốc.

### Bài 3: Hết dữ liệu

`next()` nên trả `null` hay ném ngoại lệ khi hết?

**Đáp án:** ném `NoSuchElementException`. `null` có thể là dữ liệu hợp lệ ở một nguồn khác.

### Bài 4: Duyệt một phần

Nếu đã gọi `next()` một lần trên iterator của `[2, 5)`, `consumeRemaining` nhận được những số nào?

**Đáp án:** `3` và `4`. Nó dùng trạng thái hiện tại, không quay về `2`.

### Bài 5: Gán thêm tên biến

`Iterator<Integer> second = first;` có tạo một lượt duyệt mới không?

**Đáp án:** không. Hai biến cùng tham chiếu một iterator. Muốn độc lập trên `IntRange`, gọi `range.iterator()` lần nữa.

### Bài 6: Iterable có bắt buộc lưu tất cả phần tử không?

**Đáp án:** không. `IntRange` tính số kế tiếp theo yêu cầu. Interface mô tả khả năng duyệt, không bắt buộc cách lưu trữ.

Tách rõ nguồn và trạng thái giúp thiết kế cũng như sử dụng vòng lặp đúng: `Iterable<T>` mở đường bắt đầu duyệt, còn `Iterator<T>` quản lý tiến trình của một lần duyệt cụ thể.
