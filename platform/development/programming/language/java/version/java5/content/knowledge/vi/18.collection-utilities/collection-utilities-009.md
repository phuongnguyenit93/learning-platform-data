# Comparator đảo thứ tự bằng Collections.reverseOrder

## 1. Đảo một quy tắc so sánh khác với đảo các vị trí đang có

`Collections.reverseOrder` tạo hoặc trả về một Comparator mô tả thứ tự ngược lại. Bản thân lời gọi không sửa list, không sắp mảng và không lấy phần tử khỏi hàng đợi.

Ví dụ:

```java
Comparator<Integer> descending = Collections.reverseOrder();
```

Comparator này xếp các Integer theo thứ tự ngược với thứ tự tự nhiên, nên số lớn đứng trước số nhỏ.

Muốn dữ liệu thực sự được sắp, phải đưa Comparator vào thao tác tương ứng:

```java
numbers.sort(descending);
```

Các API này vẫn áp dụng trong Java hiện đại. Ví dụ đầy đủ trong bài chạy trên Java 17+.

## 2. Hai overload quan trọng

| Cách gọi | Thứ tự được tạo |
| --- | --- |
| `Collections.reverseOrder()` | Ngược với thứ tự tự nhiên của phần tử |
| `Collections.reverseOrder(comparator)` | Ngược với thứ tự do comparator cung cấp |

Ví dụ với thứ tự tự nhiên:

```java
Comparator<String> descendingText = Collections.reverseOrder();
```

String có thứ tự tự nhiên dựa trên các đơn vị UTF-16. Đảo nó không tự tạo thứ tự sắp theo tiếng Việt hay thứ tự không phân biệt hoa/thường.

Ví dụ với thứ tự tùy chỉnh:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);

Comparator<String> longestFirst =
        Collections.reverseOrder(byLength);
```

longestFirst xếp chuỗi dài trước chuỗi ngắn. Hai chuỗi cùng độ dài vẫn so sánh bằng 0 nếu Comparator gốc không có tiêu chí phụ.

Nếu tham số comparator là null, `Collections.reverseOrder(null)` có nghĩa dùng thứ tự ngược của thứ tự tự nhiên, không phải luôn ném NullPointerException.

## 3. Cơ chế qua dấu của kết quả so sánh

Một Comparator trả:

- Giá trị âm nếu đối số thứ nhất đứng trước đối số thứ hai.
- 0 nếu cùng mức so sánh.
- Giá trị dương nếu đối số thứ nhất đứng sau đối số thứ hai.

Đảo thứ tự có thể hiểu qua việc đổi hai đối số của quan hệ so sánh. Khi Comparator gốc cho a đứng trước b, Comparator đảo cho b đứng trước a.

Không yêu cầu kết quả số nguyên phải bằng chính xác số đối của kết quả gốc. Hợp đồng dựa trên dấu và quan hệ, không phải một công thức trả về từng giá trị int cụ thể.

Vì vậy, không tự viết:

```java
// Tránh:
// (a, b) -> -original.compare(a, b)
```

Comparator được phép trả một số âm bất kỳ, kể cả Integer.MIN_VALUE. Lấy âm giá trị này bị tràn và vẫn là số âm, nên có thể làm sai ý định đảo dấu.

Dùng Collections.reverseOrder(original), `original.reversed()` hoặc một cách đổi chiều so sánh đúng hợp đồng.

## 4. Ví dụ đầy đủ với list, Comparator ghép và PriorityQueue

Lưu thành `ReverseOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class ReverseOrderDemo {
    record Job(int priority, long sequence, String name) {
    }

    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(3, 1, 4, 2));
        numbers.sort(Collections.reverseOrder());
        System.out.println("numbers=" + numbers);

        List<String> words =
                new ArrayList<>(List.of("bb", "a", "ccc", "aa"));

        Comparator<String> byLengthThenText = Comparator
                .comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());

        words.sort(Collections.reverseOrder(byLengthThenText));
        System.out.println("words=" + words);

        List<Job> base = List.of(
                new Job(2, 1, "high-first"),
                new Job(2, 2, "high-later"),
                new Job(1, 3, "normal")
        );

        Comparator<Job> priorityOnly =
                Comparator.comparingInt(Job::priority);

        Comparator<Job> highThenOldest =
                Collections.reverseOrder(priorityOnly)
                        .thenComparingLong(Job::sequence);

        Comparator<Job> allReversed =
                Collections.reverseOrder(
                        priorityOnly.thenComparingLong(Job::sequence));

        List<Job> first = new ArrayList<>(base);
        first.sort(highThenOldest);
        System.out.println("primary reversed=" + names(first));

        List<Job> second = new ArrayList<>(base);
        second.sort(allReversed);
        System.out.println("all reversed=" + names(second));

        PriorityQueue<Integer> queue =
                new PriorityQueue<>(Collections.reverseOrder());
        queue.addAll(Arrays.asList(3, 1, 4, 2));

        List<Integer> polled = new ArrayList<>();
        Integer value;
        while ((value = queue.poll()) != null) {
            polled.add(value);
        }
        System.out.println("queue poll=" + polled);

        Comparator<Integer> nullComparator = null;
        boolean threeComesFirst =
                Collections.reverseOrder(nullComparator)
                        .compare(3, 1) < 0;
        System.out.println("null comparator first=" + threeComesFirst);
    }

    static String names(List<Job> jobs) {
        StringBuilder result = new StringBuilder();
        for (Job job : jobs) {
            if (result.length() > 0) {
                result.append(",");
            }
            result.append(job.name());
        }
        return result.toString();
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ReverseOrderDemo.java
java ReverseOrderDemo
```

Kết quả:

```text
numbers=[4, 3, 2, 1]
words=[ccc, bb, aa, a]
primary reversed=high-first,high-later,normal
all reversed=high-later,high-first,normal
queue poll=[4, 3, 2, 1]
null comparator first=true
```

Biểu thức cuối chỉ kiểm tra dấu của kết quả so sánh: 3 đứng trước 1 theo thứ tự tự nhiên đảo. Nó không phụ thuộc vào độ lớn cụ thể của giá trị int mà Comparator trả về.

## 5. Đảo tiêu chí chính và đảo toàn bộ Comparator ghép

Giả sử Comparator gốc xét priority tăng dần rồi sequence tăng dần.

Nếu đảo toàn bộ Comparator:

```java
Collections.reverseOrder(
        priorityOnly.thenComparingLong(Job::sequence));
```

kết quả là:

- Priority giảm dần.
- Khi bằng priority, sequence cũng giảm dần.

Nếu chỉ đảo priority rồi mới thêm sequence:

```java
Collections.reverseOrder(priorityOnly)
        .thenComparingLong(Job::sequence);
```

kết quả là:

- Priority giảm dần.
- Khi bằng priority, sequence vẫn tăng dần.

Hai dòng output `primary reversed` và `all reversed` trong chương trình chứng minh khác biệt này. Cách đặt reverseOrder hoặc reversed trong chuỗi ghép là một phần của hợp đồng nghiệp vụ.

Đừng chỉ nhìn tên “descending” rồi bỏ qua các tiêu chí phụ. Nếu cần “khẩn cấp trước, cùng mức thì đến trước”, phải đảo đúng tiêu chí khẩn cấp và giữ chiều khóa thứ tự đến.

## 6. Collections.reverseOrder và Collections.reverse khác mục đích

| API | Tác động |
| --- | --- |
| `Collections.reverseOrder(...)` | Trả Comparator đảo một quan hệ thứ tự |
| `Collections.reverse(list)` | Đảo các vị trí trong list hiện có |
| `list.sort(comparator)` | Sắp list theo Comparator |

Ví dụ với list `[3, 1, 2]`:

- reverse cho `[2, 1, 3]`.
- sort(reverseOrder()) cho `[3, 2, 1]`.

Đảo list chưa sắp không tự thành sắp giảm dần.

Ngay cả khi list đã sắp, việc sort với Comparator đảo và việc reverse toàn bộ list có thể khác cách xử lý các phần tử cùng mức. List.sort là phép sắp ổn định theo hợp đồng: các phần tử so sánh bằng 0 giữ thứ tự tương đối. Reverse đảo cả các vị trí của chúng.

Vì vậy, không thay hai cách một cách máy móc nếu thứ tự các phần tử cùng mức có ý nghĩa.

## 7. Null và phần tử không so sánh được

### Null Comparator khác null phần tử

Tham số null của reverseOrder(comparator) là tín hiệu chọn thứ tự tự nhiên đảo. Nó không tạo Comparator tự chấp nhận phần tử null.

Comparator đảo của thứ tự tự nhiên sẽ gây NullPointerException khi cần so sánh phần tử null. Nếu dữ liệu cho phép null và muốn chúng luôn đứng cuối:

```java
Comparator<Integer> descendingNullsLast =
        Comparator.nullsLast(Collections.reverseOrder());
```

Thứ tự ghép vẫn quan trọng:

```java
Comparator<Integer> reverseIncludingNullPolicy =
        Collections.reverseOrder(
                Comparator.nullsLast(Comparator.<Integer>naturalOrder()));
```

Comparator thứ hai đảo luôn chính sách “null cuối”, nên null sẽ đứng đầu.

Với PriorityQueue, bản thân cấu trúc không chấp nhận phần tử null, dù Comparator có khả năng xử lý null.

### Kiểu phần tử cần đáp ứng quan hệ so sánh

reverseOrder() không tự tạo thứ tự cho một lớp tùy ý không có Comparable. Nếu không có thứ tự tự nhiên phù hợp, hãy cung cấp Comparator rõ ràng qua overload nhận comparator.

Một Comparator tùy chỉnh vẫn phải tuân theo đối xứng dấu, tính bắc cầu và các quy tắc nhất quán của Comparator. Đảo một quan hệ vốn không hợp lệ không sửa được quan hệ đó.

## 8. Kiểu nguyên thủy và mảng được sắp

Comparator áp dụng cho kiểu tham chiếu/generic. Để sắp một Integer[] giảm dần:

```java
Integer[] values = {3, 1, 2};
Arrays.sort(values, Collections.reverseOrder());
```

Không có overload tương ứng nhận Comparator cho int[]:

```java
// Không biên dịch:
// Arrays.sort(new int[] {3, 1, 2}, Collections.reverseOrder());
```

Nếu dữ liệu là int[], có thể sắp tăng bằng Arrays.sort rồi đảo mảng bằng thao tác phù hợp, hoặc chọn thuật toán khác theo nhu cầu. Đổi toàn bộ sang Integer[] có thể thêm chi phí bộ nhớ và đóng hộp; không nên làm chỉ vì muốn một lời gọi ngắn mà chưa cân nhắc dữ liệu.

List<Integer> trong ví dụ là list có thể sửa vì được tạo bằng ArrayList. Một List.of không sửa được sẽ không trở thành list sắp được chỉ nhờ truyền Comparator.

## 9. API tương đương trong Java hiện đại

Hai cách thường gặp:

```java
Comparator<Integer> a = Collections.reverseOrder();
Comparator<Integer> b = Comparator.reverseOrder();
```

cùng biểu đạt thứ tự tự nhiên đảo theo hợp đồng API.

Với Comparator đã có:

```java
Comparator<Job> a = Collections.reverseOrder(priorityOnly);
Comparator<Job> b = priorityOnly.reversed();
```

cùng biểu đạt đảo thứ tự của priorityOnly nếu nó khác null. Điểm khác cần nhớ: Collections.reverseOrder(null) có ý nghĩa riêng, còn gọi `reversed()` trên biến null sẽ ném NullPointerException vì đang gọi phương thức trên null.

Không kiểm tra hai Comparator bằng `==` để kết luận chúng có cùng ngữ nghĩa. API không yêu cầu mọi cách tạo quan hệ tương đương đều trả cùng một instance.

## 10. Dùng đúng trong hàng đợi ưu tiên

PriorityQueue luôn chọn phần tử nhỏ nhất theo Comparator của nó. Nếu Comparator là reverseOrder của số tự nhiên, số lớn nhất được lấy trước.

Điều này không biến iterator thành phép duyệt có thứ tự giảm dần và không bảo đảm FIFO cho các phần tử có cùng mức so sánh. Trong chương trình, thứ tự được kiểm chứng bằng vòng lặp poll.

Nếu cần thay đổi quy tắc của một hàng đợi đã có dữ liệu, không dùng một Comparator có trạng thái thay đổi bên ngoài rồi kỳ vọng heap tự tổ chức lại. Hãy dựng lại hàng đợi theo quy tắc mới hoặc thiết kế một bước chuyển có kiểm soát.

## 11. Thực hành

1. Tạo list `[3, 1, 2]`, đối chiếu reverse với sort(reverseOrder()).
2. Với hai Job cùng priority nhưng khác sequence, so sánh đảo toàn bộ Comparator với chỉ đảo priority.
3. Thêm một phần tử null vào list Integer và thử hai cách ghép chính sách null ở mục 7.
4. Dùng list có hai chuỗi cùng độ dài rồi so sánh sort ổn định theo độ dài đảo với reverse một list đã sắp theo độ dài.
5. Giải thích vì sao không viết phép lấy âm kết quả compare bất kỳ để đảo thứ tự.

## Tài liệu đối chiếu

- [Collections — Hai overload reverseOrder và reverse](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).
- [Comparator — reverseOrder, reversed và chính sách null](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html).
- [List.sort — Hợp đồng sắp ổn định](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).
