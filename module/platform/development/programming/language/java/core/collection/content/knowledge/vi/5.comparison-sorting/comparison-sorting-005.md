# reversed, reverseOrder, nullsFirst và nullsLast

Khi sắp xếp dữ liệu, cần quyết định riêng hai điều:

1. **Các giá trị có thật được xếp theo quy tắc nào, theo chiều nào?**
2. **Nếu có null, null đứng trước hay sau các giá trị đó?**

Các phương thức `reversed`, `reverseOrder`, `nullsFirst` và `nullsLast` giúp xây dựng comparator cho những quyết định này. Chúng tạo quy tắc so sánh; việc sắp xếp chỉ diễn ra khi quy tắc được truyền vào một thao tác như `List.sort`.

Trong bài này, `reversed()` chỉ phương thức của **Comparator**. Các ví dụ dùng API tương thích Java 17 trở lên.

## 1. Nhận diện từng công cụ

| Biểu thức | Loại phương thức | Chức năng |
| --- | --- | --- |
| `c.reversed()` | Phương thức mặc định trên một comparator có sẵn | Đảo toàn bộ thứ tự do `c` định nghĩa |
| `Comparator.reverseOrder()` | Phương thức static | Tạo comparator theo chiều ngược của thứ tự tự nhiên |
| `Comparator.nullsFirst(c)` | Phương thức static | Đặt null trước giá trị khác, dùng `c` cho hai giá trị không null |
| `Comparator.nullsLast(c)` | Phương thức static | Đặt null sau giá trị khác, dùng `c` cho hai giá trị không null |

Ở đây, `c` là một đối tượng `Comparator`, không phải một danh sách.

Cần phân biệt thêm hai phương thức thuộc lớp `Collections`:

- `Collections.reverseOrder(c)`: tạo comparator đảo quy tắc của `c`.
- `Collections.reverse(list)`: đảo **vị trí các phần tử đang có** trong một danh sách.

Hai thao tác này không thể thay thế cho nhau một cách tùy ý.

## 2. reversed(): đảo một quy tắc đã có

### 2.1. Đảo theo quy tắc nào?

Giả sử comparator ban đầu xếp chuỗi theo độ dài tăng dần:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);

Comparator<String> lengthDescending = byLength.reversed();
```

Đây là các khai báo minh họa, cần import `java.util.Comparator`.

Comparator mới đưa chuỗi dài hơn lên trước. Nó không tự đổi quy tắc thành thứ tự từ điển giảm dần, bởi quy tắc gốc đang xét **độ dài**.

Nếu comparator gốc xếp theo nhiều tiêu chí, đảo comparator là đảo toàn bộ thứ tự đó.

### 2.2. Hiểu bằng chiều so sánh, không bằng độ lớn kết quả

Về quan hệ thứ tự, comparator đảo tương đương việc dùng comparator gốc với hai đối số đổi chỗ:

```java
// Minh họa ý nghĩa:
Comparator<String> reverse = (a, b) -> byLength.compare(b, a);
```

Nếu `a` đứng trước `b` theo comparator gốc, nó đứng sau theo comparator đảo. Những đối tượng cùng hạng vẫn cùng hạng.

Không nên tự viết:

```java
// Không dùng làm mẫu đảo comparator:
// Comparator<String> reverse = (a, b) -> -byLength.compare(a, b);
```

Hợp đồng comparator cho phép trả về bất kỳ số nguyên âm hoặc dương phù hợp, không chỉ -1 hoặc 1. Nếu kết quả là `Integer.MIN_VALUE`, đổi dấu số đó vẫn âm do tràn miền `int`.

`reversed()` diễn đạt đúng ý định mà không đòi bên sử dụng tự xử lý trường hợp này.

### 2.3. Comparator gốc và danh sách không bị sửa

Lời gọi:

```java
Comparator<String> reverse = byLength.reversed();
```

không làm `byLength` đổi sang giảm dần, cũng không tự sắp xếp một danh sách nào. Sau đó vẫn có thể dùng hai comparator cho hai nơi khác nhau.

Đảo hai lần cho thứ tự tương đương quy tắc ban đầu. Điều đó là nhận xét về **kết quả so sánh**, không phải lời bảo đảm rằng hai biểu thức sẽ trả cùng một tham chiếu đối tượng.

Xem [API Comparator.reversed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#reversed()).

## 3. reverseOrder(): đảo thứ tự tự nhiên

### 3.1. Thứ tự tự nhiên là gì?

Thứ tự tự nhiên đến từ hợp đồng `Comparable` của kiểu dữ liệu. Chẳng hạn, `Integer` có thứ tự số và `String` có thứ tự so sánh chuỗi do kiểu đó định nghĩa.

```java
Comparator<Integer> descendingNumbers = Comparator.reverseOrder();
Comparator<String> descendingStrings = Comparator.reverseOrder();
```

Hai comparator này không cần một comparator gốc do người dùng truyền vào.

Không nên hiểu `reverseOrder()` là “đảo thứ tự mà danh sách hiện đang có”. Nó mô tả một thứ tự có thể áp dụng cho nhiều danh sách.

### 3.2. Khác với đảo comparator tùy chỉnh

Với các chuỗi:

```text
z, aa, bbb
```

hai yêu cầu cho kết quả khác nhau:

| Yêu cầu | Kết quả |
| --- | --- |
| Giảm dần theo thứ tự tự nhiên của String | `[z, bbb, aa]` |
| Giảm dần theo độ dài | `[bbb, aa, z]` |

Dùng `Comparator.reverseOrder()` cho hàng đầu. Dùng `Comparator.comparingInt(String::length).reversed()` cho hàng sau.

Nếu một kiểu miền nghiệp vụ không triển khai `Comparable`, không thể chỉ dùng `Comparator.reverseOrder()` rồi kỳ vọng Java tự biết cần đảo theo thuộc tính nào. Hãy tạo comparator theo thuộc tính mong muốn trước.

### 3.3. reverseOrder không tự hỗ trợ null

`Comparator.reverseOrder()` không có chính sách xếp null. Nếu việc so sánh chạm vào đối số null, nó ném `NullPointerException`.

Muốn các giá trị không null giảm dần nhưng null đứng cuối:

```java
Comparator<String> rule =
        Comparator.nullsLast(Comparator.reverseOrder());
```

Quy tắc trên có hai lớp: lớp ngoài xử lý null, lớp trong xử lý các chuỗi thực.

Xem [API Comparator.reverseOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#reverseOrder()).

## 4. nullsFirst và nullsLast hoạt động ra sao?

Giả sử `c` là comparator hợp lệ cho hai giá trị không null:

| Hai đối số | `nullsFirst(c)` | `nullsLast(c)` |
| --- | --- | --- |
| Cả hai null | Cùng hạng | Cùng hạng |
| Đối số đầu null, đối số sau không null | Đầu đứng trước | Đầu đứng sau |
| Đối số đầu không null, đối số sau null | Đầu đứng sau | Đầu đứng trước |
| Cả hai không null | Dùng `c` | Dùng `c` |

Lớp bao ngoài xử lý những trường hợp có null trước khi cần đến comparator bên trong. Nó không đổi giá trị null thành chuỗi rỗng, số 0 hoặc một đối tượng giả.

Hai khai báo thường gặp:

```java
Comparator<String> nullFirstAscending =
        Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<String> nullLastAscending =
        Comparator.nullsLast(Comparator.naturalOrder());
```

`naturalOrder()` không tự chấp nhận null, nhưng có thể đặt bên trong lớp bao xử lý null như trên.

### 4.1. Đối số comparator null có ý nghĩa riêng

API cho phép:

```java
Comparator<String> onlyNullPlacement =
        Comparator.nullsFirst(null);
```

Trong trường hợp này:

- Null vẫn đứng trước các giá trị không null.
- **Mọi giá trị không null đều được xem là cùng hạng.**
- Không có bước tự động dùng thứ tự tự nhiên cho phần không null.

Tương tự, `Comparator.nullsLast(null)` chỉ tách null ra sau, còn các giá trị không null cùng hạng.

Đây không phải cách viết tắt của `nullsFirst(naturalOrder())`. Nếu cần phân biệt các giá trị không null, phải truyền comparator phù hợp.

Nếu dùng quy tắc chỉ phân biệt null vào `TreeSet`, mọi giá trị không null thuộc một hạng theo comparator; không thể mong cây giữ đủ mọi chuỗi khác nhau. Với danh sách, những phần tử cùng hạng vẫn được giữ lại.

Chi tiết của hai lớp bao nằm trong [API nullsFirst](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)) và [API nullsLast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsLast(java.util.Comparator)).

## 5. Vị trí reversed quyết định vị trí null

Đây là điểm cần đọc theo cấu trúc biểu thức.

### 5.1. Đảo toàn bộ lớp bao

```java
Comparator<String> original =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<String> reverseEverything = original.reversed();
```

Quy tắc ban đầu xếp:

```text
giá trị nhỏ -> giá trị lớn -> null
```

Đảo toàn bộ cho:

```text
null -> giá trị lớn -> giá trị nhỏ
```

Null chuyển từ cuối lên đầu vì nó cũng là một phần của thứ tự đã đảo.

### 5.2. Chỉ đảo các giá trị không null

```java
Comparator<String> descendingButNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
```

Ở đây, null vẫn ở cuối. Comparator bên trong chỉ định chiều giảm dần cho các chuỗi không null.

Có thể đọc từ trong ra ngoài:

1. Xếp giá trị thực theo chiều giảm dần.
2. Bổ sung quy tắc đặt null cuối.

### 5.3. Bảng đối chiếu nhanh

Đặt `c` là thứ tự tăng dần cho các giá trị không null:

| Biểu thức | Chiều của giá trị thực | Vị trí null |
| --- | --- | --- |
| `nullsFirst(c)` | Tăng | Đầu |
| `nullsLast(c)` | Tăng | Cuối |
| `nullsFirst(c).reversed()` | Giảm | Cuối |
| `nullsLast(c).reversed()` | Giảm | Đầu |
| `nullsFirst(c.reversed())` | Giảm | Đầu |
| `nullsLast(c.reversed())` | Giảm | Cuối |

Bảng dùng cách viết rút gọn của các phương thức static thuộc `Comparator`.

Hai biểu thức cùng chiều của phần không null chưa chắc có cùng chính sách null. Vì vậy, cần kiểm tra cả hai trục khi đọc một comparator được ghép nhiều lớp.

## 6. Chương trình hoàn chỉnh: đảo chiều và xếp null

Lưu vào **ComparatorDirectionDemo.java**. Hàm `sorted` luôn tạo bản `ArrayList` mới để mỗi lần thử dùng cùng một đầu vào.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class ComparatorDirectionDemo {
    private static List<String> sorted(
            List<String> source, Comparator<String> comparator) {
        List<String> result = new ArrayList<>(source);
        result.sort(comparator);
        return result;
    }

    public static void main(String[] args) {
        List<String> words = List.of("z", "aa", "bbb");
        Comparator<String> byLength =
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder());

        System.out.println("Natural descending: "
                + sorted(words, Comparator.reverseOrder()));
        System.out.println("Length descending: "
                + sorted(words, byLength.reversed()));
        System.out.println("Collections reverse comparator: "
                + sorted(words, Collections.reverseOrder(byLength)));

        List<String> nullable =
                Arrays.asList("z", null, "aa", "bbb", null);
        Comparator<String> natural = Comparator.naturalOrder();
        Comparator<String> nullLastAscending =
                Comparator.nullsLast(natural);

        System.out.println("Null first ascending: "
                + sorted(nullable, Comparator.nullsFirst(natural)));
        System.out.println("Null last ascending: "
                + sorted(nullable, nullLastAscending));
        System.out.println("Reverse whole rule: "
                + sorted(nullable, nullLastAscending.reversed()));
        System.out.println("Null last descending: "
                + sorted(nullable, Comparator.nullsLast(
                        Comparator.reverseOrder())));

        Comparator<String> onlyNullPlacement =
                Comparator.nullsFirst(null);
        System.out.println("Only null placement: "
                + sorted(nullable, onlyNullPlacement));
        System.out.println("Non-null tie: "
                + onlyNullPlacement.compare("z", "aa"));
        System.out.println("Source unchanged: " + nullable);

        List<String> positional = new ArrayList<>(List.of("b", "a", "c"));
        Collections.reverse(positional);
        System.out.println("Reverse positions: " + positional);
        System.out.println("Sort descending: "
                + sorted(List.of("b", "a", "c"), Comparator.reverseOrder()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparatorDirectionDemo.java
java ComparatorDirectionDemo
```

Stdout:

```text
Natural descending: [z, bbb, aa]
Length descending: [bbb, aa, z]
Collections reverse comparator: [bbb, aa, z]
Null first ascending: [null, null, aa, bbb, z]
Null last ascending: [aa, bbb, z, null, null]
Reverse whole rule: [null, null, z, bbb, aa]
Null last descending: [z, bbb, aa, null, null]
Only null placement: [null, null, z, aa, bbb]
Non-null tie: 0
Source unchanged: [z, null, aa, bbb, null]
Reverse positions: [c, a, b]
Sort descending: [c, b, a]
```

### Đối chiếu kết quả

**Ba dòng đầu** phân biệt thứ tự tự nhiên với thứ tự theo độ dài. `Collections.reverseOrder(byLength)` cho kết quả cùng quy tắc đảo như `byLength.reversed()`.

**Bốn dòng về null** chứng minh vị trí của lời gọi `reversed()` có tác động:

- Đảo toàn bộ `nullLastAscending` đưa null lên đầu.
- Bọc thứ tự giảm dần bằng `nullsLast` giữ null ở cuối.

**`Only null placement`** giữ thứ tự tương đối `z, aa, bbb` của phần không null. Đây là hệ quả hai điều cùng xảy ra: comparator xem chúng cùng hạng và `List.sort` là phép sắp xếp ổn định. Nó không phải một phép sắp xếp tăng dần ẩn bên trong `nullsFirst(null)`. Bảo đảm ổn định được mô tả trong [API List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

**`Source unchanged`** xác nhận ví dụ sắp các bản sao; danh sách nguồn không bị đổi. Nếu trực tiếp gọi `source.sort(comparator)` trên danh sách có hỗ trợ, chính danh sách đó sẽ bị thay thứ tự.

**Hai dòng cuối** cho thấy đảo vị trí và sắp giảm dần là hai công việc khác nhau:

- Đảo `[b, a, c]` theo vị trí cho `[c, a, b]`.
- Sắp các chuỗi theo thứ tự tự nhiên giảm dần cho `[c, b, a]`.

## 7. Đảo một tiêu chí hay đảo cả chuỗi tiêu chí?

Giả sử kiểu dữ liệu:

```java
record Result(String code, int score) {}
```

Yêu cầu là điểm giảm dần, khi bằng điểm thì mã tăng dần.

Cách đọc đúng:

```java
Comparator<Result> scoreDescendingCodeAscending =
        Comparator.comparingInt(Result::score)
                .reversed()
                .thenComparing(Result::code);
```

`reversed()` chỉ tác động lên comparator điểm tại thời điểm nó được gọi. Sau đó, tiêu chí mã tăng dần mới được ghép thêm.

Biểu thức khác:

```java
Comparator<Result> scoreAndCodeDescending =
        Comparator.comparingInt(Result::score)
                .thenComparing(Result::code)
                .reversed();
```

đảo cả hai tiêu chí: điểm giảm dần và mã cũng giảm dần khi hòa điểm.

Thứ tự ưu tiên vẫn là điểm trước rồi mã; thay đổi nằm ở chiều so sánh của từng phần.

Nếu cần xử lý null, phải xác định null ở tiêu chí nào. Đặt một lớp `nullsLast` ở cuối cả chuỗi không có nghĩa mọi trường bên trong đều tự được bảo vệ.

## 8. Null của phần tử khác null của thuộc tính

Xét:

```java
record Task(String code, Integer priority) {}
```

Có thể có ba trường hợp riêng:

1. Tham chiếu `Task` là null.
2. `Task` tồn tại nhưng `priority` là null.
3. `Task` tồn tại nhưng `code` là null.

### 8.1. Chỉ bọc phần tử chưa đủ

Đoạn minh họa sau chưa bảo vệ thuộc tính null:

```java
Comparator<Task> incomplete = Comparator.nullsLast(
        Comparator.comparing(Task::priority));
```

Lớp ngoài xử lý một `Task` null. Khi cả hai task không null, comparator bên trong trích `priority`. Nếu priority null, thứ tự tự nhiên dùng cho thuộc tính đó vẫn có thể ném `NullPointerException`.

Tương tự, `comparingInt(task -> task.priority())` phải chuyển `Integer` thành `int`. Priority null gây lỗi khi mở hộp, trước khi có cơ hội so sánh số nguyên.

### 8.2. Xử lý null ở đúng lớp dữ liệu

Yêu cầu cụ thể:

- Priority không null giảm dần.
- Priority null ở sau những priority có thật.
- Khi bằng priority, code tăng dần và code null ở cuối nhóm hòa.
- Cả task null đứng cuối toàn bộ danh sách.

Xây từng lớp:

```java
Comparator<Task> priorityDescending = Comparator.comparing(
        Task::priority,
        Comparator.nullsLast(Comparator.reverseOrder()));

Comparator<Task> codeAscending = Comparator.comparing(
        Task::code,
        Comparator.nullsLast(Comparator.naturalOrder()));

Comparator<Task> complete = Comparator.nullsLast(
        priorityDescending.thenComparing(codeAscending));
```

`nullsLast` bên trong xử lý các **thuộc tính**; `nullsLast` bên ngoài xử lý **đối tượng Task**.

Khi hai priority đều null, comparator priority trả 0, nên tiêu chí code vẫn được xét. Nếu chính sách nghiệp vụ không muốn phân biệt thêm trong nhóm đó, phải mô tả một quy tắc khác có chủ đích.

## 9. Chương trình hoàn chỉnh với nhiều lớp null

Lưu vào **NullableTaskSortDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullableTaskSortDemo {
    record Task(String code, Integer priority) {}

    private static String describe(Task task) {
        if (task == null) {
            return "<null task>";
        }
        return String.valueOf(task.code()) + ":" + task.priority();
    }

    private static List<String> sorted(
            List<Task> source, Comparator<Task> comparator) {
        List<Task> copy = new ArrayList<>(source);
        copy.sort(comparator);
        return copy.stream().map(NullableTaskSortDemo::describe).toList();
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
                new Task("B", 2),
                new Task("A", 2),
                new Task("C", null),
                null,
                new Task(null, 2),
                new Task("D", 1));

        Comparator<Task> priorityDescending = Comparator.comparing(
                Task::priority,
                Comparator.nullsLast(Comparator.reverseOrder()));

        Comparator<Task> codeAscending = Comparator.comparing(
                Task::code,
                Comparator.nullsLast(Comparator.naturalOrder()));

        Comparator<Task> rule = Comparator.nullsLast(
                priorityDescending.thenComparing(codeAscending));

        System.out.println("Selected rule: " + sorted(tasks, rule));
        System.out.println("Reverse whole rule: "
                + sorted(tasks, rule.reversed()));
        System.out.println("Original size: " + tasks.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NullableTaskSortDemo.java
java NullableTaskSortDemo
```

Stdout:

```text
Selected rule: [A:2, B:2, null:2, D:1, C:null, <null task>]
Reverse whole rule: [<null task>, C:null, D:1, null:2, B:2, A:2]
Original size: 6
```

### Đọc các nhóm dữ liệu

Với `rule`:

1. Priority 2 đứng trước priority 1.
2. Trong nhóm priority 2, code `A` rồi `B`, sau đó mới đến code null.
3. Task `C` có priority null đứng sau các task có priority thật.
4. Tham chiếu task null ở cuối cùng.

Chuỗi `null:2` trong output biểu diễn **task tồn tại, code null, priority 2**. Ký hiệu `<null task>` biểu diễn **không có đối tượng task**. Chương trình in khác nhau để không lẫn hai trạng thái.

Khi gọi `rule.reversed()`, toàn bộ thứ tự đảo lại: task null lên đầu, priority null đi lên, các tiêu chí giá trị thực và thứ tự mã cũng đổi chiều. Đây không còn là yêu cầu “priority giảm, code tăng, null cuối” ban đầu.

Muốn chỉ đổi chiều priority mà giữ các chính sách khác, hãy dựng lại phần comparator priority ở lớp tương ứng rồi ghép lại.

## 10. reverseOrder trong lớp Collections

Ngoài `Comparator.reverseOrder()`, Java có hai phương thức quen thuộc trong `Collections`:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `Collections.reverseOrder()` | Thứ tự tự nhiên đảo chiều |
| `Collections.reverseOrder(c)` | Đảo thứ tự do comparator `c` định nghĩa |

Với `c` không null, lời gọi thứ hai đáp ứng cùng ý định thứ tự như `c.reversed()`. Nếu `c` đã hỗ trợ null, việc đảo cũng đảo quan hệ giữa null và các giá trị khác.

Có một trường hợp đặc biệt của overload nhận comparator: **`Collections.reverseOrder(null)` dùng thứ tự tự nhiên đảo chiều**. Điều đó khác với ý nghĩa của comparator null trong `Comparator.nullsFirst(null)`.

Xem hợp đồng của [Collections.reverseOrder không tham số](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverseOrder()) và [Collections.reverseOrder nhận comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverseOrder(java.util.Comparator)).

### Những giá trị null trong API không có cùng ý nghĩa

| Nơi truyền null | Ý nghĩa |
| --- | --- |
| Một phần tử trong dữ liệu | Một giá trị cần chính sách chấp nhận hoặc từ chối |
| `Comparator.nullsFirst(null)` | Null đầu; mọi giá trị không null cùng hạng |
| `Comparator.nullsLast(null)` | Null cuối; mọi giá trị không null cùng hạng |
| `Collections.reverseOrder(null)` | Dùng thứ tự tự nhiên đảo chiều |
| `list.sort(null)` | Dùng thứ tự tự nhiên; không tự trở thành phép sort hỗ trợ phần tử null |

Với biến comparator `c` có giá trị null, gọi `c.reversed()` là gọi phương thức trên tham chiếu null và gây `NullPointerException`. Không áp dụng trường hợp đặc biệt của `Collections.reverseOrder(null)` cho mọi phương thức cùng tên hoặc có liên quan.

## 11. Comparator đảo và thao tác đảo danh sách

`Collections.reverse(list)` thay đổi thứ tự vị trí hiện có:

```text
phần tử cuối -> ... -> phần tử đầu
```

Nó không cần biết các phần tử là số, chuỗi hay task, không xét tiêu chí, và không tự quyết định thứ tự tăng hay giảm. Vì không cần so sánh phần tử, thao tác đảo vị trí không cần một comparator để xử lý null.

Ví dụ, nếu dãy gốc đã được sắp tăng theo một comparator, đảo dãy có thể cho thứ tự giảm theo quan hệ đó. Nhưng nếu có các phần tử cùng hạng, đảo vị trí còn đảo thứ tự tương đối của chúng. Sắp xếp ổn định bằng comparator đảo sẽ giữ thứ tự tương đối của những phần tử cùng hạng. Hai thao tác có thể cùng đạt thứ tự hợp lệ nhưng khác vị trí của các phần tử hòa nhau.

Vì vậy, hãy chọn thao tác theo mục tiêu:

- Muốn đảo dãy hiện tại: `Collections.reverse`.
- Muốn tạo thứ tự theo quy tắc giảm dần: truyền comparator phù hợp vào thao tác sắp xếp.

Chi tiết sửa danh sách nằm trong [API Collections.reverse](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)).

## 12. Những lỗi thường gặp

| Biểu hiện hoặc cách viết | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `reverseOrder()` nhưng kết quả không theo độ dài | Đã đảo thứ tự tự nhiên thay vì quy tắc tùy chỉnh | Dùng `byLength.reversed()` |
| Null lên đầu sau khi đảo | Đã đảo cả lớp `nullsLast` | Bọc phần giảm dần bằng `nullsLast` nếu null phải ở cuối |
| Task không null nhưng vẫn lỗi null | Thuộc tính trích ra null chưa được bảo vệ | Truyền comparator hỗ trợ null ở cấp thuộc tính |
| Priority null gây lỗi khi dùng `comparingInt` | Mở hộp `Integer` null sang `int` | Dùng so sánh kiểu boxed có chính sách null |
| Mọi giá trị không null giữ nguyên thứ tự, không tăng dần | Đã truyền comparator null vào `nullsFirst/nullsLast` | Truyền comparator thực cho các giá trị đó |
| Cả tiêu chí phụ bị giảm dần | Gọi `reversed()` sau khi đã ghép chuỗi | Đảo từng tiêu chí ở đúng vị trí |
| Khởi tạo dữ liệu thử null bằng `List.of` bị lỗi | Factory này không chấp nhận phần tử null | Dùng một cấu trúc hỗ trợ null cho ví dụ, như `ArrayList` |
| Gọi sort lên danh sách không cho sửa bị lỗi | Việc sort cần sửa thứ tự danh sách | Tạo bản `ArrayList` khi cần sắp một bản sao |
| Tự đổi dấu kết quả compare | Có thể tràn số với một kết quả âm hợp lệ | Dùng `reversed()` hoặc đổi chiều đối số |
| Dùng `Collections.reverse` như phép sort giảm dần | Chỉ đảo vị trí, không sắp theo giá trị | Gọi sort với comparator giảm dần |

Các lớp bao null và thao tác đảo không làm một comparator sai trở nên đúng. Comparator nền vẫn cần có hợp đồng dấu, tính bắc cầu và sự nhất quán phù hợp với dữ liệu.

## 13. Cách thiết kế và kiểm chứng một quy tắc

Trước khi viết biểu thức ghép, mô tả yêu cầu bằng câu đầy đủ:

> Priority giảm dần; priority thiếu để cuối. Khi hòa priority, code tăng dần; code thiếu để cuối nhóm. Task null để cuối toàn bộ.

Sau đó xây từng lớp và kiểm tra các trường hợp:

1. Hai giá trị thực khác nhau.
2. Hai giá trị thực cùng tiêu chí chính.
3. Một null và một không null, ở cả hai chiều đối số.
4. Hai null.
5. Null của thuộc tính và null của toàn phần tử.
6. Tiêu chí chính hòa nhưng tiêu chí phụ khác.
7. Đảo riêng tiêu chí so với đảo toàn bộ comparator.
8. Danh sách nguồn có được phép thay đổi hay phải giữ nguyên?

Không kết luận một comparator hỗ trợ null chỉ vì thử trên danh sách rỗng hoặc một phần tử mà không có lỗi: thuật toán có thể chưa gọi phép so sánh liên quan.

Nếu muốn kiểm chứng chính sách null trực tiếp, có thể gọi `compare(null, value)`, `compare(value, null)` và `compare(null, null)` trên comparator đã được thiết kế để chấp nhận những trường hợp đó, rồi đối chiếu dấu với yêu cầu.

## 14. Bài tập tự kiểm tra

1. Với các chuỗi `z, aa, bbb`, giải thích vì sao `reverseOrder()` và comparator đảo theo độ dài cho kết quả khác nhau.
2. Dự đoán vị trí null của `nullsFirst(c).reversed()` và `nullsFirst(c.reversed())`.
3. Sửa một quy tắc đang giảm cả điểm và mã để chỉ giảm điểm, mã vẫn tăng.
4. Trong ví dụ Task, đổi priority từ giảm dần sang tăng dần nhưng vẫn giữ null cuối ở cả ba vị trí liên quan.
5. Giải thích vì sao `Comparator.nullsLast(null)` không tương đương `Comparator.nullsLast(Comparator.naturalOrder())`.
6. Tạo hai phần tử cùng hạng nhưng có mã khác, rồi so sánh việc đảo vị trí với sắp xếp ổn định bằng comparator đảo.

Điểm cần nắm là phạm vi tác động của từng lớp: **đảo quy tắc hiện có, chọn thứ tự tự nhiên ngược, đặt null ở một phía, và thực hiện thao tác trên danh sách** là những quyết định riêng có thể kết hợp theo đúng yêu cầu.
