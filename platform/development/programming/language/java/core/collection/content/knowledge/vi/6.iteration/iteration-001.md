# Vòng lặp theo chỉ số, enhanced for và Iterable

**Duyệt phần tử** là lần lượt lấy các phần tử từ một nguồn dữ liệu để xử lý. Trong Java, hai cách quen thuộc là vòng lặp dùng chỉ số và vòng lặp for-each, còn được gọi là **enhanced for**.

Chúng không chỉ khác cú pháp:

- Vòng lặp theo chỉ số dựa vào khả năng truy cập một vị trí.
- Enhanced for diễn đạt việc xử lý từng phần tử mà không yêu cầu người viết tự quản lý vị trí.
- `Iterable<T>` là hợp đồng giúp một đối tượng cung cấp cách duyệt các phần tử của nó.

Hiểu quan hệ này giúp chọn cách duyệt phù hợp, tránh truy cập kém hiệu quả và không nhầm việc thay biến vòng lặp với thay dữ liệu trong collection.

Bài sử dụng Java 17. Ba chương trình hoàn chỉnh đã được biên dịch với `--release 17` và chạy để đối chiếu stdout. Các đoạn rút gọn còn lại chỉ minh họa một thao tác hoặc một phần của phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn cần có thể:

- Viết vòng lặp đúng giới hạn của mảng hoặc danh sách.
- Giải thích nguồn dữ liệu nào dùng được với enhanced for.
- Mô tả vai trò khác nhau của `Iterable` và `Iterator`.
- Chọn cách duyệt theo nhu cầu chỉ số, thay thế phần tử và cấu trúc dữ liệu.
- Tự xây dựng một `Iterable` nhỏ với các lượt duyệt độc lập.

## 1. Bắt đầu từ nhu cầu, không bắt đầu từ cú pháp

Giả sử có các bước xử lý:

```text
read
write
run
```

Hai yêu cầu khác nhau dẫn đến cách viết khác nhau:

| Yêu cầu | Thông tin cần dùng |
| --- | --- |
| In tên từng bước | Chỉ cần phần tử |
| In vị trí và tên bước | Cần chỉ số cùng phần tử |
| Thay phần tử thứ hai | Cần thao tác theo vị trí |
| Duyệt một tập hợp không có chỉ số | Cần cơ chế lấy phần tử tiếp theo |
| Duyệt một dải số do chương trình sinh ra | Cần một nguồn có thể cung cấp phần tử lần lượt |

Không phải dữ liệu nào cũng có vị trí truy cập bằng `get(index)`. Nếu chỉ cần phần tử, việc bắt nguồn dữ liệu phải cung cấp chỉ số có thể tạo phụ thuộc thừa.

## 2. Vòng lặp theo chỉ số

### Với mảng

Đoạn minh họa trong một phương thức:

```java
String[] steps = {"read", "write", "run"};

for (int index = 0; index < steps.length; index++) {
    String step = steps[index];
    System.out.println(index + " -> " + step);
}
```

Ba phần của vòng lặp:

1. `int index = 0`: bắt đầu từ vị trí đầu.
2. `index < steps.length`: chỉ dùng các vị trí hợp lệ.
3. `index++`: chuyển sang vị trí kế tiếp sau mỗi lượt.

Mảng có độ dài `n` dùng chỉ số từ `0` đến `n - 1`. Nếu điều kiện là `index <= steps.length`, vòng lặp sẽ cố truy cập vị trí `n`, nằm ngoài mảng.

Mảng rỗng có `length == 0`; điều kiện sai ngay từ đầu nên thân vòng lặp không chạy.

### Với List

```java
List<String> steps = new ArrayList<>(List.of("read", "write", "run"));

for (int index = 0; index < steps.size(); index++) {
    String step = steps.get(index);
    System.out.println(index + " -> " + step);
}
```

Đoạn này cần các import `List` và `ArrayList` từ `java.util`.

Phân biệt:

- Mảng dùng thuộc tính `length` và cú pháp `array[index]`.
- Danh sách dùng phương thức `size()` và `get(index)`.
- Giao diện `List` có thao tác truy cập theo chỉ số.
- Giao diện `Collection` chung không khai báo `get(index)`; `Set` không phải một danh sách có chỉ số.

### Khi chỉ số có giá trị học tập hoặc nghiệp vụ

Vòng lặp chỉ số phù hợp khi cần:

- In vị trí phần tử.
- Truy cập các vị trí lân cận, sau khi kiểm tra giới hạn.
- Gán vào một ô mảng hoặc thay phần tử danh sách.
- Duyệt một đoạn, duyệt ngược hoặc bước qua nhiều vị trí.
- Phối hợp nhiều nguồn theo cùng một chỉ số khi chúng thực sự có quan hệ vị trí.

Ví dụ duyệt ngược một danh sách:

```java
for (int index = steps.size() - 1; index >= 0; index--) {
    System.out.println(steps.get(index));
}
```

Khi danh sách rỗng, giá trị bắt đầu là `-1`, điều kiện sai ngay. Không có lần truy cập `get(-1)` trong đoạn này.

Việc điều khiển chỉ số đem lại sự chủ động, nhưng cũng làm người viết chịu trách nhiệm về cận, bước nhảy và các thay đổi vị trí trong lúc duyệt.

## 3. Enhanced for: thể hiện ý định xử lý từng phần tử

Cú pháp:

```java
for (String step : steps) {
    System.out.println(step);
}
```

Đọc là: với mỗi phần tử lấy từ `steps`, gán giá trị đó cho biến `step` của lượt hiện tại rồi thực hiện thân vòng lặp.

Cú pháp này dùng được với:

1. Mảng, kể cả mảng nguyên thủy như `int[]`.
2. Đối tượng có kiểu phù hợp với `Iterable`.

Nó không có biến chỉ số được cung cấp sẵn. Nếu thật sự cần một chỉ số truy cập vị trí, hãy cân nhắc vòng lặp theo chỉ số. Nếu chỉ muốn một số thứ tự để hiển thị, có thể đếm số lượt, nhưng số đếm đó không tạo thêm khả năng truy cập chỉ số cho nguồn.

### Những bảo đảm cần đọc đúng

Enhanced for:

- Lấy phần tử theo cơ chế duyệt của nguồn.
- Không tự sắp xếp.
- Không tự loại trùng.
- Không tự tạo bản sao độc lập của toàn bộ dữ liệu.
- Không mặc định làm cho thao tác trở nên an toàn khi nhiều luồng cùng sử dụng.
- Không tự chuyển một đối tượng bất kỳ thành nguồn duyệt được.

Danh sách thường được duyệt theo thứ tự danh sách. Với một tập hợp, thứ tự phải dựa vào hợp đồng cụ thể của tập hợp đó; cú pháp for-each không bổ sung bảo đảm thứ tự mới.

### Break và continue

Vẫn có thể dùng các lệnh điều khiển thông thường:

- `break`: thoát vòng lặp theo phạm vi của lệnh.
- `continue`: bỏ phần còn lại của lượt hiện tại và chuyển sang lượt tiếp theo.

Ví dụ dừng khi gặp bước cần tìm:

```java
for (String step : steps) {
    if (step.equals("write")) {
        break;
    }
    System.out.println(step);
}
```

Đoạn minh họa giả định `step` không `null`. Điều kiện dừng là quyết định của thân vòng lặp, không phải việc xóa phần tử khỏi nguồn.

## 4. So sánh trực tiếp hai cách duyệt

Tạo tệp **`TraversalStylesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class TraversalStylesDemo {
    public static void main(String[] args) {
        List<String> steps = new ArrayList<>(List.of("read", "write", "run"));

        System.out.println("indexed:");
        for (int index = 0; index < steps.size(); index++) {
            System.out.println(index + " -> " + steps.get(index));
        }

        System.out.println("enhanced:");
        for (String step : steps) {
            System.out.println(step);
        }

        int[] numbers = {2, 4, 6};

        for (int number : numbers) {
            number *= 10;
        }
        System.out.println("after local assignment = " + Arrays.toString(numbers));

        for (int index = 0; index < numbers.length; index++) {
            numbers[index] *= 10;
        }
        System.out.println("after indexed assignment = " + Arrays.toString(numbers));

        for (int index = steps.size() - 1; index >= 0; index--) {
            System.out.println("reverse " + index + " -> " + steps.get(index));
        }
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 TraversalStylesDemo.java
java -Dfile.encoding=UTF-8 TraversalStylesDemo
```

Stdout:

```text
indexed:
0 -> read
1 -> write
2 -> run
enhanced:
read
write
run
after local assignment = [2, 4, 6]
after indexed assignment = [20, 40, 60]
reverse 2 -> run
reverse 1 -> write
reverse 0 -> read
```

### Đọc chương trình

- Vòng lặp chỉ số in được cả vị trí lẫn tên bước.
- Enhanced for lấy từng chuỗi mà không viết `get(index)`.
- Vòng lặp trên mảng số dùng biến `number` nhận **giá trị** của phần tử ở mỗi lượt.
- Gán `number *= 10` chỉ đổi biến cục bộ, nên mảng vẫn là `[2, 4, 6]`.
- Gán `numbers[index] *= 10` thay đúng vị trí trong mảng, nên kết quả là `[20, 40, 60]`.
- Vòng lặp cuối duyệt danh sách ngược bằng chỉ số.

Cả hai cách đều có thể biểu diễn việc duyệt, nhưng không cung cấp cùng quyền truy cập vào vị trí của nguồn.

## 5. Biến vòng lặp không phải một ô trong collection

Điểm này đặc biệt dễ nhầm khi phần tử là đối tượng.

### Với giá trị nguyên thủy

Trong:

```java
for (int number : numbers) {
    number = 100;
}
```

`number` là biến cục bộ. Nó không phải một tên khác có thể gán thay cho `numbers[index]`.

### Với đối tượng

Trong:

```java
for (Counter counter : counters) {
    counter.value += 10;
}
```

biến `counter` nhận một bản sao của **tham chiếu** tới đối tượng. Tham chiếu đó vẫn trỏ tới cùng đối tượng đang được collection giữ, nên sửa trạng thái của đối tượng có thể được quan sát qua collection.

Nhưng:

```java
for (Counter counter : counters) {
    counter = new Counter(99);
}
```

chỉ đổi tham chiếu trong biến cục bộ. Phần tử trong danh sách không được thay bằng đối tượng mới.

Cần phân biệt ba hành động:

| Hành động | Có thay phần tử được lưu ở vị trí của danh sách không? |
| --- | --- |
| Gán lại biến cục bộ trong for-each | Không |
| Sửa trạng thái đối tượng được tham chiếu | Giữ nguyên tham chiếu, nhưng đối tượng có thể thay đổi |
| `list.set(index, other)` trên danh sách hỗ trợ thay thế | Có |

### Chương trình hoàn chỉnh

Tạo tệp **`ElementReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ElementReferenceDemo {
    private static final class Counter {
        private int value;

        private Counter(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    public static void main(String[] args) {
        List<Counter> counters = new ArrayList<>(
                List.of(new Counter(1), new Counter(2)));

        for (Counter counter : counters) {
            counter.value += 10;
        }
        System.out.println("after object mutation = " + counters);

        for (Counter counter : counters) {
            counter = new Counter(99);
        }
        System.out.println("after local reassignment = " + counters);

        for (int index = 0; index < counters.size(); index++) {
            counters.set(index, new Counter(20 + index));
        }
        System.out.println("after list replacement = " + counters);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ElementReferenceDemo.java
java -Dfile.encoding=UTF-8 ElementReferenceDemo
```

Stdout:

```text
after object mutation = [11, 12]
after local reassignment = [11, 12]
after list replacement = [20, 21]
```

Kết quả cho thấy:

1. Sửa thuộc tính của hai đối tượng làm dữ liệu thành `[11, 12]`.
2. Gán `counter` sang đối tượng mới không thay danh sách.
3. `set` theo chỉ số mới thật sự thay các phần tử danh sách thành hai đối tượng mới.

Ở các kiểu bất biến như `String`, không có thao tác sửa trực tiếp nội dung của đối tượng chuỗi. Ví dụ, nhận một chuỗi mới từ một phương thức rồi chỉ gán vào biến for-each cũng không cập nhật danh sách chuỗi.

## 6. Iterable và Iterator giữ hai vai trò khác nhau

### Iterable<T>: nguồn có thể cung cấp lượt duyệt

Chữ ký cốt lõi, ở dạng rút gọn:

```java
public interface Iterable<T> {
    Iterator<T> iterator();
}
```

Đây là trích dạng chữ ký để giải thích hợp đồng, không phải giao diện cần tự định nghĩa lại.

`iterator()` trả về một đối tượng có khả năng lần lượt cung cấp phần tử. Nguồn không cần tiết lộ nó lưu bằng mảng, danh sách liên kết hay sinh giá trị khi được yêu cầu.

`Iterable` không bắt buộc có:

- `size()`.
- `get(index)`.
- `add` hoặc `remove`.
- Dữ liệu đã được nạp hết trong bộ nhớ.
- Một số lượng phần tử hữu hạn.
- Một snapshot cố định cho mọi lượt duyệt.

### Iterator<T>: trạng thái của một lượt duyệt

Hai thao tác quan trọng:

| Thao tác | Ý nghĩa |
| --- | --- |
| `hasNext()` | Cho biết còn phần tử để lấy không |
| `next()` | Trả phần tử tiếp theo và tiến trạng thái duyệt |

`next()` khi đã hết cần ném `NoSuchElementException`. Không dùng `null` như tín hiệu kết thúc chung vì một nguồn có thể hợp lệ chứa phần tử `null`.

`hasNext()` không có nhiệm vụ tiến sang phần tử tiếp theo. Nếu bỏ quên `next()` trong một vòng lặp thủ công, chương trình có thể không tiến được.

Một `Iterator` thường được sử dụng như con trỏ của một lượt duyệt đã tiến dần. Bản thân kiểu `Iterator` không mặc định là `Iterable`; không thể cho rằng có iterator là có thể đặt trực tiếp nó bên phải dấu `:` của enhanced for.

### Quan hệ với Collection

```text
Collection<E> mở rộng Iterable<E>

Nguồn Iterable<E>
    -> iterator()
    -> một Iterator<E> giữ vị trí duyệt
    -> next() cung cấp từng phần tử
```

`List`, `Set` và nhiều loại collection do đó dùng được với enhanced for thông qua hợp đồng kế thừa này.

Cần tránh nhầm “nguồn” với “con trỏ đang ở đâu trong nguồn”. Hai biến cùng trỏ tới một iterator sẽ cùng chia sẻ trạng thái duyệt của chính iterator đó.

## 7. Enhanced for hoạt động như thế nào?

### Trên một Iterable

Vòng lặp:

```java
for (String step : steps) {
    System.out.println(step);
}
```

có thể được hiểu gần với thao tác tường minh:

```java
Iterator<String> cursor = steps.iterator();

while (cursor.hasNext()) {
    String step = cursor.next();
    System.out.println(step);
}
```

Đoạn rút gọn cần `import java.util.Iterator;` và một nguồn `steps` có kiểu tương ứng. Nó minh họa ý tưởng của cơ chế duyệt, không cố liệt kê mọi chi tiết chuyển đổi kiểu của trình biên dịch.

Những điểm quan trọng:

- Một iterator được lấy cho lượt vòng lặp này.
- `hasNext()` quyết định có tiếp tục không.
- `next()` cung cấp phần tử ở mỗi lượt.
- Biến `step` là biến của thân vòng lặp, không phải một ô có thể gán ngược vào nguồn.
- Lượt for-each sau sẽ yêu cầu iterator qua một lần gọi khác tới `iterator()`.

### Trên một mảng

Mảng dùng được với enhanced for nhờ quy tắc riêng của ngôn ngữ Java; mảng **không triển khai `Iterable`**.

Về ý tưởng, trình biên dịch giữ tham chiếu tới mảng cần duyệt rồi đi qua các vị trí của mảng. Nó không cần tạo một `Iterator` của Java Collections Framework cho mảng.

Hệ quả:

- `int[]` dùng được trong `for (int value : array)`.
- Không thể vì vậy mà truyền `int[]` vào một phương thức yêu cầu `Iterable<Integer>`.
- Gán lại biến nguồn mảng ở nơi khác không có nghĩa vòng for-each đã bắt đầu sẽ tự chuyển sang một mảng khác.
- Đừng giả định có snapshot sâu: các giá trị ở những vị trí chưa đọc vẫn thuộc mảng đang được duyệt.

Hai loại nguồn cùng dùng một cú pháp nhưng không phải cùng một cơ chế bên dưới.

## 8. Tự định nghĩa một Iterable đơn giản

Ta tạo một dải số nguyên:

```text
[startInclusive, endExclusive)
```

Ví dụ `[3, 6)` cung cấp `3`, `4`, `5`. Dải không cần giữ sẵn một collection chứa ba số; nó có thể tạo từng giá trị từ trạng thái con trỏ.

Thiết kế này cần:

1. Nguồn giữ hai cận không thay đổi.
2. Mỗi lời gọi `iterator()` tạo một iterator mới.
3. Mỗi iterator có biến `current` riêng.
4. `hasNext()` kiểm tra cận.
5. `next()` từ chối khi hết, nếu chưa hết thì trả giá trị rồi tiến con trỏ.

### Chương trình hoàn chỉnh

Tạo tệp **`IterableRangeDemo.java`**:

```java
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.StringJoiner;

public class IterableRangeDemo {
    public record IntRange(int startInclusive, int endExclusive)
            implements Iterable<Integer> {
        public IntRange {
            if (endExclusive < startInclusive) {
                throw new IllegalArgumentException("Invalid range");
            }
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
                        throw new NoSuchElementException();
                    }
                    return current++;
                }
            };
        }
    }

    public static void main(String[] args) {
        IntRange range = new IntRange(3, 6);

        System.out.println("range pass 1 = " + join(range));
        System.out.println("range pass 2 = " + join(range));
        System.out.println("list = " + join(List.of(8, 9)));

        Iterator<Integer> first = range.iterator();
        Iterator<Integer> second = range.iterator();

        System.out.println("first iterator = " + first.next() + ", " + first.next());
        System.out.println("second iterator = " + second.next());

        Iterator<Integer> empty = new IntRange(5, 5).iterator();
        System.out.println("empty hasNext = " + empty.hasNext());

        try {
            empty.next();
        } catch (NoSuchElementException exception) {
            System.out.println("empty next = "
                    + exception.getClass().getSimpleName());
        }
    }

    private static String join(Iterable<Integer> source) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (int number : source) {
            result.add(Integer.toString(number));
        }
        return result.toString();
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 IterableRangeDemo.java
java -Dfile.encoding=UTF-8 IterableRangeDemo
```

Stdout:

```text
range pass 1 = [3, 4, 5]
range pass 2 = [3, 4, 5]
list = [8, 9]
first iterator = 3, 4
second iterator = 3
empty hasNext = false
empty next = NoSuchElementException
```

### Vì sao ví dụ này thực hiện đúng vai trò?

- `IntRange` triển khai `Iterable<Integer>` nhưng không phải một `Collection`.
- Dải không cung cấp thao tác thêm/xóa hoặc truy cập bằng chỉ số.
- Hàm tạo từ chối cận cuối nhỏ hơn cận đầu.
- Dải có hai cận bằng nhau là rỗng.
- `iterator()` tạo đối tượng iterator mới, nên hai lượt `join(range)` đều bắt đầu từ `3`.
- Hai iterator tường minh cũng có trạng thái độc lập: iterator đầu đã lấy `3`, `4`, nhưng iterator thứ hai vẫn bắt đầu từ `3`.
- `next()` trên dải rỗng gây đúng `NoSuchElementException`.
- Phương thức `join` chỉ cần `Iterable<Integer>`, nên dùng được với cả dải tự định nghĩa và một `List<Integer>`.

Do cận cuối là cận loại trừ, phần tử cuối được trả về nhỏ hơn `endExclusive`. Với phạm vi `int` hợp lệ trong thiết kế này, thao tác tăng sau phần tử cuối không cần vượt quá `Integer.MAX_VALUE`.

Ví dụ không cung cấp khả năng xóa phần tử qua iterator. Nguồn là một dải giá trị được mô tả bằng cận, không phải collection khả biến cần gỡ phần tử.

### Không suy rộng tính lặp lại cho mọi Iterable

Trong `IntRange`, các iterator độc lập và có thể duyệt lại vì ta đã thiết kế như vậy. Chỉ nhìn thấy kiểu `Iterable` chưa đủ để kết luận mọi nguồn đều:

- Lặp lại được bao nhiêu lần cũng cho cùng dữ liệu.
- Đọc dữ liệu miễn phí.
- Tạo các iterator độc lập trong mọi điều kiện.
- Không phụ thuộc tài nguyên bên ngoài hoặc thời điểm đọc.

Khi thiết kế API, hãy tài liệu hóa các điều kiện này. Nếu nguồn có tài nguyên cần đóng, riêng `Iterable` cũng không có hợp đồng tự đóng tài nguyên thay cho bên sử dụng.

## 9. Chọn cách duyệt theo cấu trúc và yêu cầu

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| Đọc tuần tự mọi phần tử | Enhanced for thường diễn đạt ý định rõ |
| Cần sửa một vị trí mảng | Vòng lặp theo chỉ số |
| Cần thay phần tử của một `List` | Chỉ số với `set`, hoặc cơ chế phù hợp của danh sách |
| Cần duyệt nguồn chỉ có `Iterable` | Enhanced for hoặc iterator tường minh |
| Cần tự điều khiển con trỏ, chẳng hạn xóa qua iterator được hỗ trợ | Iterator tường minh |
| Cần duyệt ngược một nguồn | Cơ chế ngược mà nguồn hỗ trợ; không mặc định mọi nguồn đều có chỉ số |
| Cần số thứ tự để hiển thị | Có thể đếm số lượt; không coi số đếm là chỉ số truy cập của nguồn |

### Hiệu quả của get(index) phụ thuộc lớp triển khai

Với `ArrayList`, truy cập một chỉ số có chi phí không tăng theo số phần tử trong mô hình sử dụng thông thường. Duyệt bằng `get(index)` liên tiếp là một lựa chọn hợp lý khi cần chỉ số.

Với `LinkedList`, việc lấy phần tử theo chỉ số cần tìm tới vị trí trong chuỗi liên kết. Nếu cứ gọi `get(0)`, `get(1)`, ..., `get(n - 1)`, tổng công việc có thể tăng theo bậc hai của số phần tử.

Duyệt tuần tự bằng iterator của `LinkedList` tránh việc tìm lại từ đầu hoặc cuối cho từng chỉ số và có chi phí tuyến tính cho toàn lượt duyệt.

Do đó, nếu một phương thức nhận `List` bất kỳ và chỉ cần đọc lần lượt, enhanced for thường tránh được giả định không cần thiết về khả năng truy cập ngẫu nhiên.

Không nên kết luận mọi enhanced for luôn nhanh hơn mọi vòng lặp chỉ số. Kiểu dữ liệu, công việc trong thân vòng lặp và tối ưu hóa lúc chạy đều ảnh hưởng. Trước hết hãy chọn cách đúng với hợp đồng và tránh cấu trúc truy cập có chi phí không phù hợp.

### Lưu size trước vòng lặp không phải cách chữa mọi vấn đề

Viết `int count = list.size()` trước vòng lặp chỉ có nghĩa bạn đang dùng một cận đã lưu. Nó không làm `get(index)` của danh sách liên kết trở thành truy cập ngẫu nhiên nhanh.

Nếu danh sách thay đổi trong lúc duyệt, cận đã lưu còn có thể không phù hợp với kích thước hiện tại. Chỉ dùng cách tổ chức này khi điều kiện dữ liệu và mục đích rõ ràng.

## 10. Những nguồn không dùng được trực tiếp với enhanced for

### Map không triển khai Iterable

Không duyệt trực tiếp một `Map` bằng:

```text
for (entry : map)
```

theo cách suy đoán đó. `Map` cung cấp các góc nhìn:

| Góc nhìn | Nội dung |
| --- | --- |
| `keySet()` | Các khóa |
| `values()` | Các giá trị |
| `entrySet()` | Các cặp khóa–giá trị |

Nếu cần cả khóa và giá trị, một mẫu minh họa là:

```java
for (Map.Entry<String, Integer> entry : counts.entrySet()) {
    System.out.println(entry.getKey() + " = " + entry.getValue());
}
```

Đoạn này cần `import java.util.Map;` và biến `counts` có kiểu map phù hợp. Thứ tự duyệt vẫn phụ thuộc hợp đồng của loại map và góc nhìn, không phải do enhanced for quyết định.

### String không tự là một Iterable<Character>

Một đối tượng `String` không thể được đặt trực tiếp vào enhanced for với giả định nó sẽ cung cấp từng ký tự.

Có thể lựa chọn cách duyệt phù hợp với yêu cầu ký tự, đơn vị mã hoặc điểm mã, nhưng đó là bài toán cần xác định rõ. Không nên mặc định một ký tự hiển thị luôn tương đương một `char`.

### Iterator không tự là nguồn Iterable

Nếu bạn đã có một iterator, hãy điều khiển nó qua `hasNext()` và `next()`, hoặc cơ chế riêng mà API đó cung cấp.

`Iterable` có nhiệm vụ cấp cách duyệt; iterator cụ thể là trạng thái đang được tiến. Hai vai trò không thể thay thế chỉ bằng việc đổi tên biến.

## 11. Null, kiểu phần tử và dữ liệu thay đổi

### Nguồn null khác nguồn rỗng

- Nguồn rỗng: không có lượt xử lý phần tử.
- Nguồn `null`: không có đối tượng mảng hoặc `Iterable` để duyệt; enhanced for sẽ gây `NullPointerException`.

Hãy thống nhất API trả về nguồn rỗng hay cho phép `null`. Đừng dùng hai trạng thái đó như thể giống nhau.

### Phần tử null có thể gây lỗi trong thân vòng lặp

Với nguồn có thể chứa `null`, enhanced for vẫn có thể nhận phần tử đó. Lỗi có thể phát sinh khi gọi phương thức trên biến hoặc mở hộp.

Ví dụ minh họa:

```java
for (int number : values) {
    System.out.println(number);
}
```

Nếu `values` là một `Iterable<Integer>` chứa `null`, việc chuyển `Integer` sang `int` ở lượt tương ứng cần mở hộp và gây `NullPointerException`.

Enhanced for không tự xác thực hoặc bỏ qua dữ liệu thiếu.

### Thêm/xóa trong lúc đang duyệt cần một cơ chế được hỗ trợ

Không nên trực tiếp thêm/xóa cấu trúc collection trong một for-each rồi kỳ vọng con trỏ luôn tự cập nhật đúng.

Một số iterator có cơ chế phát hiện sửa đổi và có thể ném `ConcurrentModificationException`, kể cả khi chỉ có một luồng. Đây không phải bảo đảm rằng mọi lần sửa sai đều được phát hiện.

Các hướng xử lý tùy mục tiêu:

- Xóa qua iterator tường minh khi nguồn hỗ trợ thao tác đó.
- Dùng `removeIf` trên collection hỗ trợ xóa.
- Thu thập thay đổi rồi áp dụng sau lượt duyệt.
- Chọn loại collection có hợp đồng duyệt phù hợp với yêu cầu đồng thời.

Không nên chỉ đổi sang vòng lặp chỉ số để “né ngoại lệ”. Xóa một phần tử làm các phần tử phía sau đổi chỉ số; nếu tăng chỉ số như cũ, có thể bỏ sót phần tử hoặc truy cập sai giới hạn.

Sửa trạng thái của đối tượng phần tử, thay phần tử của danh sách và thêm/xóa cấu trúc là các loại thay đổi khác nhau. Cách xử lý phải dựa vào hợp đồng của nguồn và mục tiêu cụ thể.

## 12. Enhanced for khác phương thức forEach

Cú pháp:

```java
for (String step : steps) {
    System.out.println(step);
}
```

khác với lời gọi phương thức:

```java
steps.forEach(step -> System.out.println(step));
```

Mẫu thứ hai dùng một hàm được truyền vào API; nó không biến thân lambda thành thân vòng lặp enhanced for.

| Đặc điểm | Enhanced for | `forEach` nhận hàm xử lý |
| --- | --- | --- |
| Hình thức | Cấu trúc điều khiển của ngôn ngữ | Lời gọi phương thức |
| Dừng bằng `break` của vòng lặp | Có | Không có vòng lặp đó để `break` bên trong lambda |
| Bỏ phần còn lại của lượt bằng `continue` | Có | Không dùng `continue` như thân vòng lặp |
| Yêu cầu biết chỉ số | Không | Cũng không tự cung cấp chỉ số |
| Cách hiểu ngữ cảnh xử lý | Thân vòng lặp đang viết | Hàm xử lý do API gọi |

Không cần đổi sang lambda chỉ để code trông ngắn. Hãy chọn hình thức thể hiện rõ luồng điều khiển cần có, nhất là khi muốn dừng sớm hoặc có nhiều nhánh.

## 13. Lỗi thường gặp

### Dùng <= thay vì < với length hoặc size

Chỉ số hợp lệ cuối cùng là số phần tử trừ một. Kiểm tra điều kiện trước khi truy cập, kể cả khi nhóm rỗng.

### Gán biến for-each để thay phần tử

Gán `element = other` chỉ thay biến cục bộ. Với mảng hoặc danh sách cần thay thế, dùng cơ chế gán vị trí được hỗ trợ.

### Cho rằng collection không sửa đổi được thì đối tượng bên trong cũng bất biến

Không cho thêm/xóa hoặc thay vị trí không đồng nghĩa các đối tượng khả biến bên trong không thể bị sửa. Cần phân biệt hợp đồng của nhóm với hợp đồng phần tử.

### Dùng get(index) trên mọi kiểu Collection

`Collection` không có thao tác đó. Chỉ yêu cầu `List` khi cần đúng khả năng của danh sách; nếu chỉ đọc lần lượt, `Iterable` có thể đã đủ.

### Tạo một iterator dùng chung cho mọi iterator()

Nếu nguồn muốn cung cấp các lượt duyệt độc lập nhưng luôn trả cùng một iterator đang tiến, lượt sau có thể bắt đầu ở giữa hoặc hết dữ liệu. Vòng lặp lồng nhau cũng có thể can thiệp vào cùng trạng thái.

Hãy thiết kế và tài liệu hóa chính sách iterator. Ví dụ `IntRange` tạo mới để phù hợp với nhu cầu duyệt lại.

### Trả null khi iterator hết dữ liệu

`null` có thể là một phần tử. Khi hết, `hasNext()` phải thể hiện trạng thái và `next()` cần ném `NoSuchElementException`.

### Gọi hasNext mà không lấy phần tử

`hasNext()` không phải thao tác tiến. Trong vòng lặp iterator thủ công, phải có đường gọi `next()` phù hợp nếu muốn chuyển phần tử.

### Mặc định foreach là snapshot an toàn

Enhanced for không tự sao chép dữ liệu. Thứ tự, tính nhất quán khi có sửa đổi và khả năng dùng nhiều luồng đều phải được xác định từ nguồn.

## 14. Thực hành

### Bài 1: chọn cách duyệt

Với từng yêu cầu, chọn vòng lặp và giải thích:

1. In các tên trong một `Set<String>`.
2. Đổi mọi giá trị trong `int[]` thành giá trị gấp đôi.
3. In chỉ số và giá trị của một `ArrayList<String>`.
4. Đọc lần lượt một `LinkedList<String>` mà không cần vị trí.
5. Viết phương thức nhận bất kỳ nguồn `Iterable<Integer>` nào và tính tổng theo chính sách số học đã chọn.

Nêu rõ yêu cầu nào cần vị trí và yêu cầu nào chỉ cần phần tử.

### Bài 2: dự đoán gán biến và sửa đối tượng

Trong `ElementReferenceDemo`:

- Đổi phần sửa thuộc tính từ cộng `10` thành nhân `10`.
- Giữ nguyên vòng lặp gán lại biến cục bộ.
- Dự đoán trạng thái danh sách sau mỗi vòng trước khi chạy.
- Giải thích vì sao `new Counter(99)` không tự thay phần tử trong danh sách.

### Bài 3: kiểm tra dải rỗng và lượt duyệt độc lập

Dùng `IntRange` với các cận:

```text
[2, 2)
[-2, 1)
[4, 3)
```

Dự đoán:

- Nguồn nào rỗng.
- Nguồn nào trả `-2, -1, 0`.
- Nguồn nào bị từ chối khi tạo.
- Điều gì xảy ra nếu gọi `next()` sau khi iterator đã hết.

Sau đó tạo hai iterator của cùng một dải và lấy phần tử xen kẽ để kiểm chứng trạng thái riêng.

### Bài 4: phát hiện giả định không cần thiết

Bạn có một phương thức chỉ in các phần tử nhưng tham số yêu cầu `ArrayList<String>`.

Hãy:

1. Viết lại để nhận `Iterable<String>`.
2. Giữ việc duyệt bằng enhanced for.
3. Truyền thử một danh sách, một tập hợp có thứ tự rõ và một nguồn tự định nghĩa.
4. Giải thích những thao tác không còn được giả định, như `get`, `size` hoặc `add`.

Tiêu chí hoàn thành là chọn đúng hợp đồng cần dùng, duyệt hết theo cơ chế nguồn cung cấp và không dựa vào khả năng không được giao diện cam kết.
