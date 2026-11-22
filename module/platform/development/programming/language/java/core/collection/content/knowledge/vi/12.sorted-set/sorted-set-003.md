# Tiêu chí trùng phần tử khi phép so sánh trả về 0

## 1. Với TreeSet, phép so sánh quyết định cả thứ tự và phần tử trùng

Khi dùng một tập sắp xếp như `TreeSet`, ta thường chú ý tới câu hỏi “phần tử nào đứng trước?”. Nhưng cùng phép so sánh đó còn trả lời một câu hỏi quan trọng khác: **hai giá trị có được tập xem là cùng một phần tử hay không?**

Quy tắc cần nhớ:

```text
compare(a, b) == 0
    → a và b tương đương theo thứ tự của tập
    → TreeSet không giữ chúng thành hai phần tử riêng
```

Nếu dùng thứ tự tự nhiên, phép so sánh là `a.compareTo(b)`. Nếu tạo tập với một `Comparator`, phép so sánh là `comparator.compare(a, b)`.

Ví dụ, bộ so sánh chỉ theo độ dài chuỗi xem `"An"` và `"Bo"` là tương đương vì cùng dài hai ký tự. Một `TreeSet` dùng bộ so sánh đó chỉ giữ một đại diện, dù:

```java
"An".equals("Bo") // false
```

Vì vậy, chọn `Comparator` cho một tập không chỉ là chọn kiểu trình bày. Nó ảnh hưởng trực tiếp tới số phần tử, kết quả thêm, tìm và xóa.

Tài liệu `TreeSet` giải thích rằng các phần tử được so sánh bằng `compareTo` hoặc `Comparator`; hai giá trị có kết quả so sánh bằng `0` được tập xem là bằng nhau theo thứ tự của nó. [TreeSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

## 2. Ba loại kết quả của phép so sánh

Một phép so sánh hợp lệ trả về số nguyên có ý nghĩa theo dấu:

| Kết quả compare(a, b) | Ý nghĩa theo thứ tự đã chọn |
| --- | --- |
| Nhỏ hơn 0 | a đứng trước b |
| Bằng 0 | a và b tương đương theo tiêu chí so sánh |
| Lớn hơn 0 | a đứng sau b |

Không mặc định phương thức chỉ được trả về đúng `-1`, `0`, `1`. Với một `Comparator` bất kỳ, dấu âm/dương mới là điều dùng để quyết định trước–sau.

Số `0` cũng không có nghĩa:

- Hai biến trỏ tới cùng đối tượng.
- Hai đối tượng có mọi trường giống nhau.
- Phương thức `equals` chắc chắn trả về `true`.
- Không đủ thông tin để so sánh nên tập sẽ tự xét tiếp bằng `equals`.

Nó có nghĩa bộ so sánh đã kết luận hai giá trị tương đương theo thứ tự đó. Với `TreeSet`, kết luận này đủ để xem là đã có phần tử tương ứng.

Nếu mục đích chỉ là “cùng ưu tiên nhưng vẫn phải giữ riêng”, trả về `0` sau khi chỉ so ưu tiên có thể là thiếu tiêu chí đối với một tập. [Comparator.compare](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T))

## 3. Thứ tự tự nhiên và Comparator: quy tắc nào được dùng?

### 3.1. Không truyền Comparator: dùng Comparable

```java
Set<Integer> numbers = new TreeSet<>();
```

Các số nguyên được sắp theo thứ tự tự nhiên do `Integer` cung cấp. Các phần tử cần có khả năng so sánh tương thích với nhau theo quy tắc đó.

Với những kiểu giá trị thông thường như `Integer`, hai số nguyên bằng nhau theo `equals` cũng có kết quả so sánh bằng `0`. Nhưng sự phù hợp đó không phải điều được mọi lớp có `Comparable` bắt buộc phải cung cấp; `BigDecimal` là trường hợp cần phân biệt ở phần sau.

Nếu `tree.comparator()` trả về `null`, điều đó có nghĩa tập dùng thứ tự tự nhiên, không phải tập không có quy tắc thứ tự.

### 3.2. Có truyền Comparator: dùng quy tắc được truyền

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
Set<String> names = new TreeSet<>(byLength);
```

Quy tắc đang dùng chỉ nhìn độ dài:

```text
compare("An", "Bo") = 0
compare("An", "Linh") < 0
compare("Linh", "Chi") > 0
```

Không có bước mặc định “nếu độ dài bằng nhau thì so tiếp theo chữ” trong biểu thức trên. Nếu muốn bước đó, phải thiết kế nó, chẳng hạn bằng `thenComparing`.

Đối tượng phần tử không nhất thiết phải tự cài `Comparable` khi đã có một `Comparator` phù hợp cho chúng. Tuy nhiên, mọi phần tử vẫn phải nằm trong miền dữ liệu mà bộ so sánh có thể xử lý. [Các cách xác định thứ tự của SortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html)

## 4. Cơ chế khiến một phần tử bị xem là trùng

Có thể hình dung việc tìm vị trí trong cây bằng quy trình khái niệm:

```text
giá trị cần tìm hoặc thêm
    ↓
so với một mục đang lưu
    ├─ kết quả âm: tiếp tục phía đứng trước
    ├─ kết quả dương: tiếp tục phía đứng sau
    └─ kết quả 0: đã tìm được phần tử tương đương
```

Sơ đồ không mô tả hình dạng cây hay mọi chi tiết cài đặt. Nó cho thấy vì sao kết quả `0` có ý nghĩa dừng tìm một giá trị mới riêng biệt.

### 4.1. add trả false khi có phần tử tương đương

Với bộ so sánh theo độ dài:

```text
ban đầu: []

add("An") → true
tập: [An]

add("Bo") → false
tập: [An]
```

`"Bo"` không được thêm thành phần tử thứ hai. Không có thao tác gộp hai chuỗi thành một giá trị mới và cũng không tự thay `"An"` bằng `"Bo"`.

Một phần tử đã lưu là đại diện cho nhóm tương đương theo bộ so sánh. Trong chuỗi thêm ở ví dụ, `"An"` đã được giữ trước; thêm `"Bo"` vào tập đang có đại diện đó không thay đổi tập.

Thứ tự thêm có thể ảnh hưởng đại diện được giữ trong một nhóm mà các đối tượng không bằng nhau theo `equals`. Đây là hệ quả cần hiểu nếu dùng bộ so sánh thô hơn ý nghĩa giá trị của đối tượng.

### 4.2. contains cũng dùng cùng ý nghĩa tương đương

Nếu tập chỉ đang giữ `"An"`, thì:

```java
names.contains("Tu"); // true với Comparator chỉ theo độ dài
```

Điều đó không có nghĩa tập đang lưu đúng chuỗi `"Tu"`. Nó có nghĩa tập có một phần tử tương đương với `"Tu"` theo quy tắc so sánh hiện tại.

`contains` không phải phương thức lấy đại diện đang lưu ra cho người gọi. Kết quả là một giá trị `boolean`.

### 4.3. remove có thể xóa một đại diện không bằng đối số theo equals

Cũng trong trạng thái đang có `"An"`:

```java
names.remove("Tu"); // true với Comparator chỉ theo độ dài
```

đã loại phần tử đại diện cho nhóm chuỗi dài hai ký tự, tức `"An"` trong ví dụ này.

Nếu người viết chỉ nghĩ “remove chuỗi nào thì chỉ xóa đúng chuỗi đó theo String.equals”, thao tác này có thể gây bất ngờ. Cần đọc quy tắc nhận diện của tập trước khi suy luận kết quả.

### 4.4. hashCode không phân xử thêm sau compare == 0

`TreeSet` không dùng mã băm để tách hai giá trị đã được bộ so sánh xem là tương đương.

Thay đổi `hashCode` của phần tử không làm `TreeSet` giữ riêng hai đối tượng khi phép so sánh vẫn trả `0`. Việc tìm và loại trùng ở đây dựa vào thứ tự, khác với cơ chế tìm trong tập băm.

Điều đó không có nghĩa có thể bỏ mọi hợp đồng `equals`/`hashCode` của kiểu đối tượng. Nó chỉ nói mã băm không phải tiêu chí dự phòng cho đường tìm của tập cây.

## 5. Chương trình đầy đủ: chuỗi cùng độ dài bị gộp

Lưu toàn bộ mã vào **ComparisonZeroDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ComparisonZeroDemo {
    public static void main(String[] args) {
        Comparator<String> byLength = Comparator.comparingInt(String::length);
        TreeSet<String> names = new TreeSet<>(byLength);

        System.out.println("An equals Bo: " + "An".equals("Bo"));
        System.out.println("compare An/Bo: " + byLength.compare("An", "Bo"));
        System.out.println("add An: " + names.add("An"));
        System.out.println("add Bo: " + names.add("Bo"));
        names.add("Linh");
        names.add("Chi");
        System.out.println("by length: " + names);
        System.out.println("size: " + names.size());
        System.out.println("contains Tu: " + names.contains("Tu"));
        System.out.println("remove Tu: " + names.remove("Tu"));
        System.out.println("after removal: " + names);

        Comparator<String> byLengthThenText =
                byLength.thenComparing(Comparator.naturalOrder());
        TreeSet<String> precise = new TreeSet<>(byLengthThenText);
        precise.addAll(List.of("An", "Bo", "Linh", "Chi", "An"));
        System.out.println("length then text: " + precise);
        System.out.println("precise size: " + precise.size());
        System.out.println("precise contains Tu: " + precise.contains("Tu"));

        List<String> sequence =
                new ArrayList<>(List.of("An", "Bo", "Linh", "Chi"));
        sequence.sort(byLength);
        System.out.println("list sorted by length: " + sequence);

        Set<String> coarse = new TreeSet<>(byLength);
        coarse.add("An");
        Set<String> ordinary = new HashSet<>(Set.of("Bo"));
        System.out.println("coarse.equals(ordinary): " + coarse.equals(ordinary));
        System.out.println("ordinary.equals(coarse): " + ordinary.equals(coarse));
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparisonZeroDemo.java
java ComparisonZeroDemo
```

Stdout:

```text
An equals Bo: false
compare An/Bo: 0
add An: true
add Bo: false
by length: [An, Chi, Linh]
size: 3
contains Tu: true
remove Tu: true
after removal: [Chi, Linh]
length then text: [An, Bo, Chi, Linh]
precise size: 4
precise contains Tu: false
list sorted by length: [An, Bo, Chi, Linh]
coarse.equals(ordinary): true
ordinary.equals(coarse): false
```

Cách đọc kết quả:

1. `"An"` không bằng `"Bo"` theo `String.equals`, nhưng so độ dài cho `0`.
2. Thêm `"Bo"` trả về `false`, nên nhóm dài hai ký tự chỉ có đại diện `"An"`.
3. `"Chi"` dài ba ký tự, `"Linh"` dài bốn ký tự, nên trình tự là `[An, Chi, Linh]`.
4. Tìm `"Tu"` trả về `true`, dù chuỗi được lưu ở nhóm dài hai là `"An"`.
5. Xóa bằng `"Tu"` loại đại diện `"An"`.
6. Thêm tiêu chí văn bản sau độ dài giúp tập `precise` giữ riêng `"An"` và `"Bo"`.
7. Sắp xếp một `List` theo độ dài không loại bỏ các phần tử cùng độ dài.
8. Hai dòng cuối chủ động cho thấy hậu quả khi tập cây dùng quy tắc không nhất quán với `equals`: phép bằng nhau của cả tập có thể mất đối xứng. Phần tiếp theo giải thích vì sao không nên coi đó là một cách dùng bình thường của hợp đồng `Set`.

## 6. Tính nhất quán với equals phải xét theo hai chiều

Một thứ tự **nhất quán với equals (consistent with equals)** khi, trong miền dữ liệu đang dùng:

```text
compare(a, b) == 0
    khi và chỉ khi
a.equals(b) == true
```

Cần cả hai chiều:

| Tình huống | Hệ quả trong TreeSet | Vấn đề với hợp đồng chung của Set |
| --- | --- | --- |
| `equals` false nhưng compare trả 0 | Hai đối tượng khác theo giá trị bị xem là một phần tử | Có thể từ chối một giá trị mà Set thông thường xem là khác |
| `equals` true nhưng compare khác 0 | Tập có thể giữ cả hai đối tượng | Có thể giữ hai phần tử bằng nhau theo equals |
| Hai phép nhận diện phù hợp nhau | Tập sắp xếp và phép bằng nhau giá trị thống nhất | Thuận lợi để tuân thủ hợp đồng Set |

Tài liệu `Comparator` không cấm mọi bộ so sánh không nhất quán với `equals`. Một bộ so sánh có thể hợp lệ để sắp xếp một danh sách nhưng không phù hợp để làm tiêu chí nhận diện của một tập muốn tuân thủ đầy đủ hợp đồng chung.

Tài liệu `TreeSet` cũng nêu rõ: nếu thứ tự không nhất quán với `equals`, tập vẫn hoạt động theo quy tắc so sánh của nó, nhưng không tuân thủ hợp đồng chung của `Set`. [Comparator: nhất quán với equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html), [TreeSet: điều kiện hợp đồng Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### Vì sao equals của hai tập có thể khác theo chiều gọi?

Trong chương trình đầu:

- `coarse` là tập cây chỉ có `"An"`, dùng độ dài để nhận diện.
- `ordinary` là tập băm chỉ có `"Bo"`, dùng quy tắc bằng nhau của chuỗi.

Khi tập cây kiểm tra chuỗi `"Bo"`, nó thấy nhóm dài hai đã có. Khi tập băm kiểm tra `"An"`, nó không thấy chuỗi bằng `"An"`.

Vì thế:

```text
coarse.equals(ordinary) → true
ordinary.equals(coarse) → false
```

Đây không phải một quy tắc mong muốn của phép bằng nhau. Nó là minh chứng rằng hai tập đang dùng hai ý nghĩa không thống nhất về thành viên.

Không “sửa” bằng cách luôn gọi `equals` từ bên có kết quả đúng ý hoặc ghép hai chiều bằng toán tử OR. Cần sửa thiết kế nhận diện, hoặc chọn cấu trúc và phép so sánh riêng phù hợp với mục đích khác.

## 7. Bổ sung tiêu chí phụ: thenComparing có tác dụng gì?

### 7.1. Tiêu chí phụ chỉ chạy khi tiêu chí trước trả 0

Nếu muốn sắp chuỗi theo độ dài nhưng vẫn giữ các chuỗi khác nhau có cùng độ dài:

```java
Comparator<String> order =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());
```

Quy tắc là:

1. So độ dài.
2. Nếu độ dài khác nhau, đã có kết quả.
3. Nếu độ dài bằng nhau, so tiếp nội dung chuỗi theo thứ tự tự nhiên.

Với `String`, tiêu chí văn bản tiếp theo phân biệt những nội dung không bằng nhau, nên `"An"` và `"Bo"` không còn có kết quả tổng bằng `0`.

Không có việc `thenComparing` tự biết trường định danh nghiệp vụ. Người thiết kế phải chọn tiêu chí phụ đúng ý nghĩa.

### 7.2. Với đối tượng nhiều trường, cần khớp cả quy tắc equals

Ví dụ dùng record:

```java
private record Task(String id, int priority) {
}
```

Record này có phép bằng nhau theo cả `id` và `priority`. Một thứ tự so ưu tiên rồi so mã phù hợp với hai thành phần đó:

```java
Comparator<Task> order = Comparator.comparingInt(Task::priority)
        .thenComparing(Task::id);
```

Giả định `id` là chuỗi hợp lệ theo hợp đồng đầu vào, hai đối tượng có compare bằng `0` khi cùng ưu tiên và cùng mã, tương ứng với bằng nhau của record trong ví dụ.

Nếu chỉ so `priority`, hai công việc khác mã nhưng cùng ưu tiên bị gộp. Nếu mục đích là giữ mọi công việc cùng ưu tiên, tiêu chí đó chưa đủ cho một tập.

### 7.3. Thêm mã phụ không phải phương thuốc đúng cho mọi mô hình

Giả sử một lớp khác định nghĩa `equals` chỉ theo mã, nhưng bộ so sánh lại nhìn ưu tiên rồi mã. Hai đối tượng cùng mã nhưng ưu tiên khác có thể:

```text
equals → true
compare → khác 0
```

Khi đó, bộ so sánh vẫn không nhất quán với `equals`, dù đã có `thenComparing(id)`.

Vì vậy, đừng áp dụng khẩu quyết “cứ thêm id là xong”. Phải viết rõ:

- Dữ liệu nào xác định một giá trị?
- Hai đối tượng thế nào được xem là trùng?
- Những dữ liệu nào tham gia thứ tự?
- Compare bằng 0 có tương ứng chính xác với equals không?

Nếu chỉ cần giữ duy nhất theo mã rồi hiển thị theo ưu tiên, có thể tách việc quản lý theo mã với việc tạo một danh sách sắp xếp để trình bày. Không bắt một `TreeSet` vừa mang quy tắc định danh này vừa giả vờ mang một quy tắc khác.

## 8. Sắp xếp một List khác với loại trùng trong TreeSet

Cùng một bộ so sánh theo độ dài có hai vai trò khác nhau:

| Nơi sử dụng | Khi hai chuỗi cùng độ dài |
| --- | --- |
| `List.sort(byLength)` | Sắp thứ tự, vẫn giữ các phần tử trong danh sách |
| `new TreeSet<>(byLength)` rồi thêm | Chỉ giữ một đại diện cho nhóm có compare bằng 0 |

Một danh sách có thể chứa nhiều phần tử bằng nhau theo tiêu chí sắp xếp. Không có quy tắc loại trùng tự động chỉ vì gọi `sort`.

Nếu yêu cầu chỉ là “hiển thị mọi công việc theo điểm/ưu tiên”, danh sách sắp xếp có thể đúng ý nghĩa hơn. Nếu yêu cầu thực sự là tập các giá trị phân biệt và cần thứ tự, phải thiết kế tiêu chí phân biệt đầy đủ cho tập.

Chuyển từ danh sách sang tập cây không phải một cách sắp xếp trung tính: nó có thể làm giảm số phần tử. Trước khi thay cấu trúc, hãy kiểm tra điều kiện compare bằng `0`.

## 9. BigDecimal: thứ tự tự nhiên cũng có thể khác equals

Không chỉ `Comparator` tự viết mới có sự khác biệt này. `BigDecimal` là ví dụ được tài liệu `Comparable` nêu rõ:

```java
BigDecimal first = new BigDecimal("4.0");
BigDecimal second = new BigDecimal("4.00");
```

Hai đối tượng biểu diễn cùng giá trị số theo `compareTo`, nhưng có scale khác nhau:

```text
first.compareTo(second) → 0
first.equals(second)    → false

first.scale()  → 1
second.scale() → 2
```

`BigDecimal.equals` xét giá trị và scale; `compareTo` so giá trị số mà không phân biệt hai scale này. Đây là lý do một `HashSet<BigDecimal>` có thể giữ hai giá trị trong khi `TreeSet<BigDecimal>` dùng thứ tự tự nhiên chỉ giữ một đại diện. [Comparable: trường hợp BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html), [BigDecimal.compareTo và equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

Có ít nhất hai yêu cầu khác nhau:

- Nếu ý nghĩa mong muốn là cùng giá trị số, hai biểu diễn này có thể cần được quản lý như cùng một giá trị theo một mô hình được xác định rõ.
- Nếu cần giữ sự khác nhau mà `BigDecimal.equals` nhìn thấy, không thể chỉ dùng so sánh số tự nhiên để phân biệt trong tập cây.

Ví dụ cho lựa chọn thứ hai là so giá trị số trước, rồi so scale:

```java
Comparator<BigDecimal> valueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
```

Khi giá trị số bằng nhau nhưng scale khác, tiêu chí phụ phân biệt chúng. Với `BigDecimal`, cùng giá trị số và cùng scale tương ứng với điều kiện bằng nhau mà `equals` sử dụng.

Đây là lựa chọn ý nghĩa dữ liệu, không phải thay đổi tùy tiện để kích thước tập lớn hơn. Nếu miền dữ liệu xem scale có ý nghĩa, không tự xóa thông tin đó chỉ để làm một loại tập dễ dùng.

## 10. Chương trình đầy đủ: record, tiêu chí phụ và BigDecimal

Lưu mã vào **SortedSetIdentityDemo.java**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class SortedSetIdentityDemo {
    private record Task(String id, int priority) {
    }

    private static String taskOrder(Set<Task> tasks) {
        StringBuilder result = new StringBuilder("[");
        String separator = "";
        for (Task task : tasks) {
            result.append(separator).append(task.id())
                    .append(":").append(task.priority());
            separator = ", ";
        }
        return result.append("]").toString();
    }

    public static void main(String[] args) {
        Comparator<Task> order = Comparator.comparingInt(Task::priority)
                .thenComparing(Task::id);
        Set<Task> tasks = new TreeSet<>(order);
        tasks.add(new Task("t-3", 2));
        tasks.add(new Task("t-2", 1));
        tasks.add(new Task("t-1", 1));
        System.out.println("tasks: " + taskOrder(tasks));
        System.out.println("duplicate task: " + tasks.add(new Task("t-2", 1)));
        System.out.println("contains same fields: "
                + tasks.contains(new Task("t-2", 1)));
        System.out.println("contains changed priority: "
                + tasks.contains(new Task("t-2", 9)));

        BigDecimal first = new BigDecimal("4.0");
        BigDecimal second = new BigDecimal("4.00");
        System.out.println("decimal equals: " + first.equals(second));
        System.out.println("decimal compareTo: " + first.compareTo(second));

        Set<BigDecimal> hashed = new HashSet<>();
        hashed.add(first);
        hashed.add(second);
        System.out.println("HashSet decimals: " + hashed.size());

        TreeSet<BigDecimal> numeric = new TreeSet<>();
        System.out.println("TreeSet add first: " + numeric.add(first));
        System.out.println("TreeSet add second: " + numeric.add(second));
        System.out.println("TreeSet decimals: " + numeric.size());
        System.out.println("stored scale: " + numeric.first().scale());
        System.out.println("contains 4.000: "
                + numeric.contains(new BigDecimal("4.000")));
        System.out.println("remove second: " + numeric.remove(second));
        System.out.println("numeric empty: " + numeric.isEmpty());

        Comparator<BigDecimal> valueThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        Set<BigDecimal> scaleAware = new TreeSet<>(valueThenScale);
        scaleAware.add(first);
        scaleAware.add(second);
        System.out.println("scale-aware size: " + scaleAware.size());
        System.out.println("scale-aware order: " + scaleAware);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SortedSetIdentityDemo.java
java SortedSetIdentityDemo
```

Stdout:

```text
tasks: [t-1:1, t-2:1, t-3:2]
duplicate task: false
contains same fields: true
contains changed priority: false
decimal equals: false
decimal compareTo: 0
HashSet decimals: 2
TreeSet add first: true
TreeSet add second: false
TreeSet decimals: 1
stored scale: 1
contains 4.000: true
remove second: true
numeric empty: true
scale-aware size: 2
scale-aware order: [4.0, 4.00]
```

Cách đọc kết quả:

1. Hai công việc cùng ưu tiên `1` vẫn được giữ vì mã `t-1` và `t-2` phân biệt ở tiêu chí phụ.
2. Thêm một record có cả hai trường giống record đang có trả về `false`.
3. Cùng mã nhưng ưu tiên `9` không bằng record có ưu tiên `1` trong mô hình record này.
4. `4.0` và `4.00` không bằng nhau theo `BigDecimal.equals`; tập băm giữ hai phần tử.
5. Tập cây tự nhiên chỉ giữ một phần tử. Scale của đại diện đang lưu là `1`, vì `first` được thêm trước và lần thêm `second` không thay thế nó.
6. Truy vấn bằng `4.000` vẫn tìm được đại diện cùng giá trị số.
7. Xóa bằng `second` xóa đại diện đó, làm tập cây tự nhiên rỗng.
8. Bộ so sánh giá trị rồi scale giữ được cả `4.0` và `4.00`.

Hai chương trình độc lập đã được biên dịch với `--release 17` và chạy để đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và tạo bytecode tương thích Java 17; nó không khẳng định JVM thực thi chính là JDK 17.

## 11. Comparator phải hợp lệ trước khi bàn tới tiêu chí trùng

Một bộ so sánh không nhất quán với `equals` chưa chắc là bộ so sánh sai về các quy tắc thứ tự. Bộ so độ dài là một ví dụ: nó có thể hợp lệ để sắp xếp nhưng nhận diện quá thô đối với tập chuỗi dùng `String.equals`.

Cần phân biệt việc đó với một bộ so sánh vi phạm chính hợp đồng `Comparator`.

### 11.1. Những tính chất cần kiểm tra

Với các giá trị trong miền so sánh:

- So một giá trị với chính nó phải cho `0`.
- Đổi chiều hai đối số phải đảo dấu kết quả.
- Quan hệ trước–sau phải bắc cầu.
- Nếu `x` và `y` có compare bằng `0`, khi so chúng với một `z`, dấu kết quả phải nhất quán.

Tính chất cuối giúp các giá trị được xem là tương đương có quan hệ trước–sau thống nhất với các nhóm còn lại. Nếu không, cấu trúc cây không có một thứ tự đáng tin để tìm kiếm. [Hợp đồng Comparator.compare](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T))

### 11.2. Không trả một số khác 0 chỉ để ép giữ mọi phần tử

Cách viết “nếu điểm bằng nhau thì cứ trả `1`” không phải tiêu chí phụ hợp lệ. Nó có thể làm:

```text
compare(a, b) > 0
compare(b, a) > 0
```

hoặc thậm chí `compare(a, a) > 0`. Đó là mâu thuẫn của bộ so sánh, không phải một cách biến tập thành danh sách giữ mọi phần tử.

Muốn giữ các giá trị khác nhau, bổ sung tiêu chí thật sự phân biệt chúng. Nếu muốn giữ cả những giá trị hoàn toàn bằng nhau, hãy xem lại việc dùng `Set`.

### 11.3. Không dùng phép trừ int làm cách so sánh tổng quát

Đoạn so `left.priority - right.priority` có thể tràn phạm vi `int`, khiến dấu kết quả sai với giá trị lớn/nhỏ ở biên.

Dùng `Integer.compare` hoặc `Comparator.comparingInt` để thể hiện phép so sánh số nguyên. Thêm tiêu chí phụ bằng các phương thức tương ứng thay vì tự ghép những phép tính khó kiểm tra.

Không dùng ngẫu nhiên, thời gian hiện tại hay một cấu hình thay đổi giữa các lời gọi để phá hòa. Một thứ tự thay đổi trong lúc tập đang giữ dữ liệu làm việc tìm kiếm không còn có nền tảng ổn định.

## 12. Miền dữ liệu và tính ổn định của khóa so sánh

### 12.1. Trường dùng để so sánh cần ổn định khi đang trong tập

Nếu tập sắp xếp công việc theo ưu tiên, rồi chương trình đổi ưu tiên của một đối tượng đang nằm trong tập, vị trí cấu trúc cũ có thể không còn phù hợp với quy tắc hiện tại.

Không dựa vào việc vẫn còn tham chiếu đối tượng để khẳng định `contains` hoặc `remove` sẽ tìm được nó như một khóa ổn định. Nên dùng các giá trị bất biến hoặc thiết kế rõ việc bỏ giá trị cũ rồi thêm giá trị mới theo quy trình phù hợp.

Ngay cả khi đối tượng bất biến, một bộ so sánh đọc dữ liệu từ một bảng cấu hình bên ngoài có thể thay đổi thứ tự nếu bảng đó bị sửa. Cần giữ ổn định cả dữ liệu nhận diện lẫn quy tắc so sánh trong thời gian tập được dùng.

### 12.2. null và kiểu không so sánh được là yêu cầu khác

Compare bằng `0` là kết quả của một phép so sánh hợp lệ. Nó không phải mã thay thế cho lỗi không thể so sánh.

`TreeSet` dùng thứ tự tự nhiên không cho phần tử `null`. Một `Comparator` có thể hỗ trợ `null` nếu được thiết kế như vậy, chẳng hạn bằng `Comparator.nullsFirst`.

Bộ so `Comparator.comparingInt(String::length)` trong ví dụ không tự xử lý `null`: gọi `length` cần một chuỗi hợp lệ. Hợp đồng đầu vào phải rõ ràng.

Tương tự, mọi phần tử phải có thể được so sánh theo cùng quy tắc. Một kiểu khai báo quá rộng không làm các giá trị không tương thích bỗng có thứ tự tự nhiên chung. [TreeSet: yêu cầu so sánh và ngoại lệ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### 12.3. Chi phí so sánh cũng ảnh hưởng thao tác

`TreeSet` có mô hình O(log n) cho các thao tác cơ bản. Nhưng mỗi bước còn thực hiện phép so sánh; một bộ so sánh phải duyệt nhiều trường hoặc nhiều dữ liệu có chi phí riêng.

Không thêm tiêu chí phụ tốn kém mà không hiểu ý nghĩa, nhưng cũng không bỏ tiêu chí định danh cần thiết chỉ để làm phép so sánh ngắn hơn. Tính đúng của việc giữ phần tử là yêu cầu trước tiên.

## 13. Các lỗi thường gặp và cách tự kiểm tra

| Hiện tượng hoặc cách viết | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Thêm nhiều đối tượng nhưng size ít hơn dự kiến | Comparator trả 0 cho nhiều giá trị nghiệp vụ khác nhau | In hoặc kiểm tra cặp khóa so sánh cụ thể |
| contains trả true cho đối tượng chưa từng thêm | Có đại diện tương đương theo thứ tự | Phân biệt đối tượng đang lưu với nhóm compare bằng 0 |
| remove xóa một đại diện khác đối số theo equals | Quy tắc so sánh thô hơn equals | Xem lại tiêu chí nhận diện của tập |
| Đổi hashCode nhưng vẫn mất phần tử khi thêm | TreeSet không dùng mã băm để tách compare bằng 0 | Sửa bộ so sánh hoặc mô hình dữ liệu |
| Thêm thenComparing(id) rồi nghĩ mọi thứ đã nhất quán | Equals của lớp có thể dùng quy tắc khác | Kiểm tra điều kiện khi và chỉ khi ở cả hai chiều |
| Trả 1 khi bằng điểm để ép thêm | Vi phạm hợp đồng thứ tự | Dùng tiêu chí phụ hợp lệ hoặc chọn List |
| Dùng phép trừ số nguyên để so | Có thể tràn phạm vi và sai dấu | Dùng compare/comparingInt |
| Sắp xếp List thì đủ phần tử, chuyển TreeSet lại mất | Tập còn thực hiện loại trùng theo compare | Chọn cấu trúc theo yêu cầu giữ dữ liệu |
| HashSet giữ hai BigDecimal, TreeSet chỉ một | Equals và thứ tự tự nhiên của BigDecimal khác nhau về scale | Xác định scale có thuộc ý nghĩa giá trị cần giữ không |
| Hai chiều equals giữa các tập khác nhau | Các tập dùng quy tắc nhận diện không thống nhất | Sửa thiết kế, không chọn chiều có kết quả thuận ý |

Một cách chẩn đoán cụ thể là lấy hai đối tượng mà người học cho rằng phải được giữ riêng, rồi kiểm tra cả:

```java
a.equals(b);
comparator.compare(a, b);
```

Nếu đang dùng thứ tự tự nhiên, kiểm tra `a.compareTo(b)` thay cho lời gọi comparator. Sau đó xét kết quả có đúng yêu cầu nhận diện hay chỉ đúng yêu cầu trình bày.

## 14. Tự luyện và đối chiếu

### Bài 1: đại diện của nhóm bằng độ dài

Tạo tập cây chuỗi dùng bộ so sánh chỉ theo độ dài. Thêm lần lượt:

```text
"aa", "bb", "c", "ddd", "ee"
```

Dự đoán:

1. Giá trị trả về của năm lần thêm.
2. Nội dung và kích thước tập.
3. `contains("ff")`.
4. Sau `remove("xx")`, phần tử nào còn?

Đối chiếu:

```text
các kết quả add: true, false, true, true, false
tập: [c, aa, ddd]
size: 3
contains("ff"): true
remove("xx"): true
sau xóa: [c, ddd]
```

Phải giải thích được `"ff"` và `"xx"` không cần trùng nội dung với `"aa"` để thuộc cùng nhóm so sánh.

### Bài 2: giữ các chuỗi cùng độ dài

Bổ sung tiêu chí văn bản sau độ dài rồi thêm cùng dữ liệu của bài 1.

Kết quả là:

```text
[c, aa, bb, ee, ddd]
```

Các chuỗi dài hai ký tự được giữ riêng và sắp trong nhóm theo thứ tự văn bản.

### Bài 3: kiểm tra quy tắc của một lớp

Một lớp định nghĩa `equals` chỉ theo `id`. Comparator so theo `priority`, rồi `id`.

Cho hai đối tượng cùng `id` nhưng khác `priority`. Hãy xét:

- `equals` có trả `true` không?
- Comparator có trả `0` không?
- Bộ so sánh có nhất quán với `equals` trên cặp này không?

Đối chiếu: bằng nhau theo equals; khác nhau theo comparator; không nhất quán. Thêm id vào cuối chưa giải quyết được sự khác biệt về ý nghĩa của priority.

### Bài 4: chọn ý nghĩa cho BigDecimal

Với hai giá trị tạo từ `"5.0"` và `"5.00"`:

- Tập cây dùng thứ tự tự nhiên giữ một đại diện.
- Tập băm dùng phép bằng nhau của `BigDecimal` giữ hai phần tử.
- Tập cây so giá trị rồi scale có thể giữ hai phần tử theo ý nghĩa có phân biệt scale.

Không chọn một trong ba chỉ dựa vào kích thước lớn hay nhỏ hơn. Phải xác định hai biểu diễn có cần được giữ riêng trong mô hình dữ liệu hay không.

## 15. Tài liệu tra cứu

- [TreeSet Java 17 — thứ tự và nhận diện phần tử](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [SortedSet — quan hệ giữa thứ tự và hợp đồng Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html)
- [Comparator — compare, thenComparing và tính nhất quán với equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Comparable — thứ tự tự nhiên và trường hợp BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)
- [BigDecimal — compareTo, equals và scale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
