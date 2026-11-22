# replaceAll và sort trên danh sách

Một danh sách có hai loại thay đổi rất khác nhau:

- **Biến đổi phần tử:** chuẩn hóa chuỗi, tính lại một giá trị hoặc thay một đối tượng bằng kết quả mới.
- **Sắp xếp phần tử:** giữ các phần tử nhưng tổ chức lại vị trí theo một quy tắc so sánh.

`List.replaceAll` phục vụ loại thứ nhất; `List.sort` phục vụ loại thứ hai. Cả hai tác động lên chính danh sách nhận lời gọi và đều trả về `void`.

Bài lấy Java 17 làm mốc. Bốn chương trình hoàn chỉnh đã được biên dịch với `--release 17` và chạy để đối chiếu stdout. Các đoạn rút gọn còn lại minh họa biểu thức hoặc thao tác trong một phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn có thể:

- Dùng UnaryOperator để biến đổi từng phần tử.
- Chọn thứ tự tự nhiên hoặc comparator khi sắp xếp.
- Giải thích tính ổn định của sort.
- Phân biệt khả năng thay phần tử với khả năng tăng/giảm kích thước.
- Dự đoán ảnh hưởng tới tham chiếu dùng chung và xử lý khi phép biến đổi thất bại.

## 1. Phân biệt biến đổi giá trị và đổi vị trí

Với dữ liệu:

```text
[3, 1, 2]
```

thay mỗi số bằng số đối cho:

```text
[-3, -1, -2]
```

Các vị trí được thay bằng kết quả tính từ phần tử cũ. Chưa có bước sắp xếp.

Sắp xếp tăng dần dữ liệu mới cho:

```text
[-3, -2, -1]
```

Đây là một bước riêng, quyết định vị trí tương đối của các phần tử.

| Đặc điểm | replaceAll | sort |
| --- | --- | --- |
| Đầu vào chính | Hàm biến đổi một phần tử | Quy tắc so sánh hai phần tử |
| Kết quả tại mỗi vị trí | Có thể được thay bằng giá trị/đối tượng khác | Các phần tử được tổ chức lại theo thứ tự |
| Số phần tử trong thao tác thành công hợp lệ | Giữ nguyên | Giữ nguyên |
| Tự lọc hoặc loại trùng | Không | Không |
| Giá trị trả về | `void` | `void` |
| Cần danh sách hỗ trợ sửa đổi | Có | Có |
| Có cần tăng/giảm kích thước? | Không | Không |

Những bảo đảm về nội dung ở đây giả định hàm truyền vào chỉ thực hiện vai trò của nó, không tự thêm/xóa cùng danh sách hoặc gây các tác dụng phụ phá vỡ điều kiện sử dụng.

## 2. replaceAll và UnaryOperator

Chữ ký:

```java
default void replaceAll(UnaryOperator<E> operator)
```

`UnaryOperator<E>` biểu diễn một hàm nhận một giá trị kiểu E và trả về kết quả cùng kiểu E. Có thể hiểu phần thao tác cốt lõi là:

```text
E apply(E value)
```

Đây là ý nghĩa của giao diện hàm, không phải một phương thức cần tự thêm vào List.

Tài liệu [UnaryOperator của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/UnaryOperator.html) mô tả đây là phép toán trên một toán hạng và trả cùng kiểu. Với replaceAll, kết quả đó được dùng để thay phần tử.

Ví dụ:

```java
names.replaceAll(value -> value.strip());
```

hoặc dùng tham chiếu phương thức:

```java
names.replaceAll(String::strip);
```

Đoạn minh họa giả định `names` là List<String> hỗ trợ thay phần tử và không chứa null.

### Kết quả hàm phải được trả về

Hàm biến đổi cần cung cấp giá trị thay thế. Với thân khối, phải có return phù hợp:

```java
names.replaceAll(value -> {
    String cleaned = value.strip();
    return cleaned;
});
```

Nếu cần chuyển từ List<String> sang List<Integer>, replaceAll trên danh sách chuỗi không phải công cụ phù hợp: kết quả phải giữ kiểu phần tử của danh sách. Khi đổi kiểu dữ liệu, hãy tạo một danh sách kết quả bằng cách biến đổi phù hợp.

### replaceAll khác forEach

```java
names.forEach(value -> value.strip());
```

không tự lưu chuỗi được strip trở lại danh sách. Hàm gọi trên String trả về một chuỗi kết quả, nhưng trong cách dùng Consumer này, giá trị trả về bị bỏ qua.

Với replaceAll, chính hợp đồng của thao tác sẽ lưu kết quả hàm vào vị trí phần tử.

### Không phải thao tác thay theo một giá trị cũ cố định

Hai API có tên gần nhau:

| API | Vai trò |
| --- | --- |
| `list.replaceAll(operator)` | Áp dụng hàm cho từng phần tử và lưu kết quả |
| `Collections.replaceAll(list, oldValue, newValue)` | Thay các phần tử phù hợp với oldValue bằng newValue |

Đừng nhầm replaceAll của List với thao tác thay chuỗi theo biểu thức chính quy của String. Đối tượng nhận lời gọi và kiểu đối số quyết định hợp đồng đang dùng.

## 3. sort và Comparator

Chữ ký:

```java
default void sort(Comparator<? super E> comparator)
```

Có hai cách dùng chính:

```java
numbers.sort(null);
numbers.sort(Comparator.naturalOrder());
```

Cả hai diễn đạt sắp theo thứ tự tự nhiên khi phần tử đáp ứng điều kiện so sánh.

Với thứ tự riêng:

```java
tickets.sort(Comparator.comparingInt(Ticket::priority));
```

Các đoạn cần import Comparator và các kiểu dữ liệu tương ứng.

### sort(null) không có nghĩa bỏ qua sắp xếp

Ở API này, comparator null là tín hiệu dùng thứ tự tự nhiên. Điều đó khác với:

```text
replaceAll(null)
```

vì replaceAll không có hàm biến đổi để áp dụng trong trường hợp đó.

### Hiểu dấu của comparator

```text
compare(first, second) < 0  -> first đứng trước second
compare(first, second) = 0  -> ngang hàng theo tiêu chí
compare(first, second) > 0  -> first đứng sau second
```

Comparator phải mô tả một quan hệ thứ tự hợp lệ và nhất quán. Đừng lấy hiệu hai trường int/long rồi ép kiểu để tạo kết quả, vì tràn số hoặc mất dữ liệu có thể làm sai dấu. Các hàm như comparingInt hoặc comparingLong giúp diễn đạt tiêu chí đúng kiểu.

Comparator cũng không nên sửa chính danh sách, thay khóa so sánh trong lúc đang sort hoặc dựa vào trạng thái bên ngoài thay đổi tùy ý.

### Tính ổn định

List.sort bảo đảm ổn định: các phần tử được comparator coi ngang hàng giữ thứ tự tương đối trước đó. Sort cần danh sách cho phép sửa đổi nhưng không bắt buộc nó tăng/giảm được kích thước. Các đặc tả này nằm ở [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

Ổn định không có nghĩa:

- Thứ tự mọi phần tử được giữ nguyên.
- Các phần tử trùng bị loại.
- Dữ liệu tự có một tiêu chí phụ mà bạn chưa khai báo.

Nếu comparator chỉ xét priority, hai đối tượng có cùng priority được coi ngang hàng, dù chúng không equals nhau.

## 4. Chương trình biến đổi rồi sắp xếp

Tạo tệp **`ListReplaceSortDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ListReplaceSortDemo {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("  beta ", "ALPHA", " beta"));

        names.replaceAll(value -> value.strip().toLowerCase(Locale.ROOT));
        System.out.println("normalized = " + names);
        names.sort(null);
        System.out.println("sorted = " + names);
        System.out.println("size = " + names.size());

        List<Integer> transformFirst = new ArrayList<>(List.of(3, 1, 2));
        transformFirst.replaceAll(value -> -value);
        transformFirst.sort(null);

        List<Integer> sortFirst = new ArrayList<>(List.of(3, 1, 2));
        sortFirst.sort(null);
        sortFirst.replaceAll(value -> -value);

        System.out.println("transform then sort = " + transformFirst);
        System.out.println("sort then transform = " + sortFirst);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ListReplaceSortDemo.java
java -Dfile.encoding=UTF-8 ListReplaceSortDemo
```

Stdout đã kiểm chứng:

```text
normalized = [beta, alpha, beta]
sorted = [alpha, beta, beta]
size = 3
transform then sort = [-3, -2, -1]
sort then transform = [-1, -2, -3]
```

### Nhóm chuỗi

1. strip loại phần khoảng trắng ở hai đầu theo quy tắc của phương thức.
2. toLowerCase với Locale.ROOT tạo chính sách chữ thường không phụ thuộc locale mặc định của máy chạy.
3. replaceAll thay từng phần tử bằng kết quả chuẩn hóa.
4. sort(null) xếp các chuỗi mới theo thứ tự tự nhiên.
5. Hai lần beta vẫn tồn tại; kích thước vẫn là 3.

Các chuỗi là đối tượng bất biến. Chương trình không sửa nội dung một String cũ; nó thay tham chiếu ở vị trí danh sách bằng chuỗi kết quả.

### Thứ tự hai bước có thể làm đổi kết quả

Với các số 3, 1, 2:

- Biến đổi thành số đối trước rồi sort cho `[-3, -2, -1]`.
- Sort trước rồi biến đổi thành số đối cho `[-1, -2, -3]`.

Một phép biến đổi có thể thay đổi quan hệ lớn/nhỏ. Vì vậy, không được đổi chỗ hai bước chỉ vì thấy chúng đều “xử lý tất cả phần tử”.

Nếu mục tiêu là thứ tự của dữ liệu sau chuẩn hóa, hãy chuẩn hóa trước rồi sắp theo chính dữ liệu hoặc khóa đã chuẩn hóa.

## 5. Sắp xếp ổn định, tiêu chí phụ và null

Giả sử các Ticket có id và priority. Danh sách ban đầu:

```text
T3(priority=2)
T1(priority=1)
T2(priority=2)
T4(priority=1)
```

Sắp theo priority tăng dần cần cho nhóm 1 đứng trước nhóm 2. Trong từng nhóm bằng priority, thứ tự cũ được giữ:

```text
T1, T4, T3, T2
```

Nếu thêm id làm tiêu chí phụ:

```text
T1, T4, T2, T3
```

thì T2 đứng trước T3 vì tiêu chí id, chứ không phải vì tính ổn định tự phát sinh cách xếp đó.

### Chương trình hoàn chỉnh

Tạo tệp **`StableListSortDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class StableListSortDemo {
    public record Ticket(String id, int priority) {
    }

    public static void main(String[] args) {
        List<Ticket> tickets = new ArrayList<>(List.of(
                new Ticket("T3", 2),
                new Ticket("T1", 1),
                new Ticket("T2", 2),
                new Ticket("T4", 1)));

        tickets.sort(Comparator.comparingInt(Ticket::priority));
        System.out.println("priority only = " + ids(tickets));

        tickets.sort(Comparator.comparingInt(Ticket::priority)
                .thenComparing(Ticket::id));
        System.out.println("priority then id = " + ids(tickets));
        System.out.println("ticket count = " + tickets.size());

        List<Integer> nullable =
                new ArrayList<>(Arrays.asList(3, null, 1, null, 2));
        nullable.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("nulls last = " + nullable);
    }

    private static List<String> ids(List<Ticket> tickets) {
        return tickets.stream().map(Ticket::id).toList();
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 StableListSortDemo.java
java -Dfile.encoding=UTF-8 StableListSortDemo
```

Stdout đã kiểm chứng:

```text
priority only = [T1, T4, T3, T2]
priority then id = [T1, T4, T2, T3]
ticket count = 4
nulls last = [1, 2, 3, null, null]
```

### Đọc các kết quả

- Chỉ xét priority: T1 vẫn trước T4, T3 vẫn trước T2.
- Có id làm tiêu chí phụ: các phần tử trước đó ngang priority được xét tiếp theo id.
- Số Ticket vẫn bằng 4.
- Danh sách số có null dùng một chính sách tường minh: số không null tăng dần, null ở cuối.

### Comparator cho null khác comparator null

Hai biểu thức có ý nghĩa khác nhau:

```java
nullable.sort(null);
```

yêu cầu thứ tự tự nhiên, còn:

```java
nullable.sort(Comparator.nullsLast(Comparator.naturalOrder()));
```

cấp một comparator có chính sách xử lý null.

Nếu thuật toán cần so tới null mà quy tắc không hỗ trợ, có thể gặp lỗi. Không mặc định rằng mọi danh sách có null đều được sắp tự nhiên một cách hợp lệ.

### Đảo chiều đúng phạm vi

Nếu muốn các số không null giảm dần nhưng null vẫn ở cuối, một chính sách phù hợp là:

```java
Comparator<Integer> order =
        Comparator.nullsLast(Comparator.reverseOrder());
```

Đảo cả comparator nullsLast sau khi tạo có thể đảo luôn vị trí của null. Hãy xác định đang đảo phần thứ tự nào.

## 6. Danh sách cố định kích thước vẫn có thể hỗ trợ hai thao tác

Cần phân biệt:

- Không tăng/giảm kích thước.
- Không cho thay thế phần tử.
- Không cho bất kỳ thao tác sửa đổi nào.

Một danh sách có số vị trí cố định vẫn có thể cho phép thay giá trị từng vị trí và tổ chức lại thứ tự.

Ví dụ, Arrays.asList tạo một List có kích thước cố định và được chống lưng bởi mảng nguồn. Thay đổi phần tử ở danh sách và mảng được phản ánh qua dữ liệu dùng chung. Xem [Arrays.asList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### Bảng thực hành

| Nguồn | replaceAll/sort | Thêm/xóa |
| --- | --- | --- |
| ArrayList thông thường | Hỗ trợ | Hỗ trợ |
| LinkedList thông thường | Hỗ trợ | Hỗ trợ |
| Arrays.asList | Có thể thay phần tử và sắp xếp | Không đổi kích thước |
| List.of hoặc List.copyOf | Không cho sửa đổi | Không cho sửa đổi |
| Collections.unmodifiableList | Không cho sửa qua góc nhìn này | Không cho sửa qua góc nhìn này |

Giao diện List không đồng nghĩa đối tượng nào cũng nhận mọi thao tác sửa. Cần biết danh sách được tạo ở đâu và nó chia sẻ dữ liệu với ai.

### Chương trình hoàn chỉnh

Tạo tệp **`FixedSizeListOperationsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class FixedSizeListOperationsDemo {
    public static void main(String[] args) {
        String[] source = {" B ", "a", " C "};
        List<String> view = Arrays.asList(source);

        view.replaceAll(value -> value.strip().toLowerCase(Locale.ROOT));
        view.sort(null);

        System.out.println("view = " + view);
        System.out.println("source = " + Arrays.toString(source));

        try {
            view.add("d");
        } catch (UnsupportedOperationException exception) {
            System.out.println("fixed-size add = "
                    + exception.getClass().getSimpleName());
        }

        List<String> readOnly = List.of("b", "a");

        try {
            readOnly.replaceAll(value -> value);
        } catch (UnsupportedOperationException exception) {
            System.out.println("read-only replaceAll = "
                    + exception.getClass().getSimpleName());
        }

        try {
            readOnly.sort(null);
        } catch (UnsupportedOperationException exception) {
            System.out.println("read-only sort = "
                    + exception.getClass().getSimpleName());
        }

        List<String> copy = new ArrayList<>(readOnly);
        copy.sort(null);

        System.out.println("read-only original = " + readOnly);
        System.out.println("sorted copy = " + copy);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 FixedSizeListOperationsDemo.java
java -Dfile.encoding=UTF-8 FixedSizeListOperationsDemo
```

Stdout đã kiểm chứng:

```text
view = [a, b, c]
source = [a, b, c]
fixed-size add = UnsupportedOperationException
read-only replaceAll = UnsupportedOperationException
read-only sort = UnsupportedOperationException
read-only original = [b, a]
sorted copy = [a, b]
```

### Những điểm đã kiểm chứng

- View từ Arrays.asList được chuẩn hóa rồi sort thành a, b, c.
- Mảng nguồn cũng thành a, b, c vì dữ liệu được chia sẻ.
- Thêm d bị từ chối do cần đổi kích thước.
- List.of từ chối cả replaceAll với hàm đồng nhất và sort.
- Tạo một ArrayList bản sao cho phép sort mà không đổi tập phần tử của danh sách gốc.

Không nên dùng một hàm đồng nhất hoặc dữ liệu đã có thứ tự để dò khả năng sửa một danh sách không cho sửa đổi. Các API sửa đổi có thể từ chối ngay cả khi bạn cho rằng kết quả nhìn thấy sẽ không khác.

## 7. Hai phương thức trả void và thay danh sách nhận lời gọi

Cách tổ chức:

```java
names.replaceAll(String::strip);
names.sort(Comparator.naturalOrder());
```

Không có danh sách kết quả mới được trả về để gán hoặc nối chuỗi lời gọi.

Nếu hai biến cùng trỏ tới một danh sách:

```java
List<String> alias = names;
names.replaceAll(String::strip);
```

thì alias cũng nhìn thấy các phần tử đã được thay trong cùng đối tượng danh sách.

### Muốn giữ nguyên danh sách nguồn

Tạo danh sách kết quả riêng trước:

```java
List<String> result = new ArrayList<>(source);
result.replaceAll(String::strip);
result.sort(Comparator.naturalOrder());
```

Đoạn này giả định nguồn không chứa null và được đọc trong điều kiện ổn định phù hợp.

Bản sao cấu trúc không tự sao chép sâu các phần tử. Với String bất biến, thay vị trí trong result không sửa nội dung String của source. Với đối tượng khả biến, một operator sửa trực tiếp thuộc tính của đối tượng chung vẫn có thể tác động dữ liệu mà source đang tham chiếu.

### replaceAll có thể trả cùng tham chiếu hoặc một tham chiếu mới

Một hàm có thể:

- Trả lại chính đối tượng nhận vào.
- Trả một đối tượng mới cùng kiểu.
- Trả null nếu chính sách danh sách và nghiệp vụ cho phép.

Không có quy tắc rằng mọi lần replaceAll đều tạo các đối tượng mới hoặc đều sửa đối tượng cũ. Điều đó do hàm biến đổi quyết định; API chịu trách nhiệm dùng kết quả để thay phần tử.

## 8. Khi hàm biến đổi ném lỗi: đừng giả định tự rollback

Tài liệu [List.replaceAll Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)) quy định lỗi hoặc ngoại lệ lúc chạy từ operator được chuyển cho bên gọi. API này không được mô tả như một giao dịch tự hoàn tác toàn bộ danh sách khi thất bại.

Xét phép biến đổi:

```text
value -> 20 / value
```

Với đầu vào:

```text
[2, 4, 0, 5]
```

hai phần tử đầu có thể đã được thay trước khi phép chia cho 0 thất bại. Chương trình sau xác định rõ trường hợp đó trên ArrayList.

### Chương trình hoàn chỉnh

Tạo tệp **`PartialReplaceAllDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PartialReplaceAllDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>(List.of(2, 4, 0, 5));
        List<Integer> alias = values;

        try {
            values.replaceAll(value -> 20 / value);
        } catch (ArithmeticException exception) {
            System.out.println("in-place failure = "
                    + exception.getClass().getSimpleName());
        }
        System.out.println("values after failure = " + values);
        System.out.println("alias after failure = " + alias);

        List<Integer> original = new ArrayList<>(List.of(2, 4, 0, 5));
        try {
            List<Integer> result = transformedCopy(original);
            System.out.println("result = " + result);
        } catch (ArithmeticException exception) {
            System.out.println("copy transform failure = "
                    + exception.getClass().getSimpleName());
        }
        System.out.println("original preserved = " + original);

        System.out.println("successful copy = "
                + transformedCopy(List.of(2, 4, 5)));
    }

    private static List<Integer> transformedCopy(List<Integer> source) {
        List<Integer> candidate = new ArrayList<>(source);
        candidate.replaceAll(value -> 20 / value);
        candidate.sort(null);
        return candidate;
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 PartialReplaceAllDemo.java
java -Dfile.encoding=UTF-8 PartialReplaceAllDemo
```

Stdout đã kiểm chứng:

```text
in-place failure = ArithmeticException
values after failure = [10, 5, 0, 5]
alias after failure = [10, 5, 0, 5]
copy transform failure = ArithmeticException
original preserved = [2, 4, 0, 5]
successful copy = [4, 5, 10]
```

### Lượt sửa trực tiếp

- 2 được thay thành 10.
- 4 được thay thành 5.
- Đến 0 thì phép chia ném ArithmeticException.
- Danh sách trong ví dụ giữ trạng thái `[10, 5, 0, 5]`.
- Alias trỏ cùng danh sách nên thấy cùng kết quả đã sửa một phần.

Đây là trạng thái được kiểm chứng trên lớp và phép toán trong chương trình. Không được dùng nó để buộc mọi lớp triển khai khác phải cập nhật theo cùng một cách khi có lỗi.

### Lượt sửa bản sao

Hàm transformedCopy:

1. Tạo một ArrayList mới từ nguồn.
2. Biến đổi trên bản sao.
3. Sort nếu bước biến đổi thành công.
4. Chỉ trả kết quả khi toàn bộ chuỗi bước hoàn tất.

Với đầu vào có 0, hàm không trả kết quả; danh sách original vẫn nguyên dữ liệu. Với đầu vào hợp lệ 2, 4, 5, nó trả `[4, 5, 10]`.

Trong mô hình này, dữ liệu Integer là bất biến và operator không có tác dụng phụ ngoài phép tính. Vì vậy, lỗi trên candidate không làm đổi phần tử của nguồn.

### Giới hạn của cách dùng bản sao

- Sao chép nông không ngăn hàm sửa trực tiếp một đối tượng khả biến dùng chung.
- Không hoàn tác được gửi thông báo, ghi tệp hoặc gọi dịch vụ mà operator đã làm.
- Không tự tạo snapshot nguyên tử nếu nguồn đang được sửa không theo giao thức phối hợp.
- Việc công bố kết quả cho nhiều luồng còn là một bước cần thiết kế riêng.

Tạo bản sao là cách kiểm soát quyền sở hữu dữ liệu và thời điểm sử dụng kết quả, không phải một cơ chế giao dịch tổng quát.

## 9. Null, loại dữ liệu và các điều kiện lỗi

### Phân biệt ba vấn đề null của replaceAll

| Trường hợp | Câu hỏi cần giải quyết |
| --- | --- |
| Bản thân operator là null | Không có hàm để áp dụng; lời gọi không hợp lệ |
| Một phần tử đầu vào là null | Hàm có xử lý đầu vào đó không? |
| Hàm trả về null | Nguồn và nghiệp vụ có chấp nhận phần tử null không? |

Ví dụ, String::strip không xử lý một tham chiếu String null. Nếu ứng dụng muốn giữ hoặc thay dữ liệu thiếu, phải chọn chính sách rõ.

Một phép chuẩn hóa minh họa:

```java
names.replaceAll(value -> value == null ? "" : value.strip());
```

Đoạn này chọn chuỗi rỗng làm kết quả cho null; đó là quyết định nghiệp vụ của ví dụ, không phải hành vi mặc định của replaceAll.

### Sort cần các phần tử so sánh được theo quy tắc đang dùng

Với thứ tự tự nhiên, các phần tử phải hỗ trợ phép so sánh phù hợp với nhau. Với comparator riêng, comparator phải xử lý các cặp phần tử mà nó nhận.

Những lỗi có thể liên quan:

- Đối tượng hoặc phần tử không có kiểu so sánh phù hợp.
- Null không được quy tắc xử lý.
- Comparator vi phạm hợp đồng thứ tự.
- Comparator ném ngoại lệ từ logic riêng.
- Danh sách không hỗ trợ sửa đổi.
- Nguồn bị sửa không hợp lệ trong lúc thao tác.

Không dựa vào trạng thái sau khi sort thất bại như thể nó chắc chắn đã hoàn tác hoặc chắc chắn chỉ sửa một tiền tố. Chi tiết còn phụ thuộc lớp thực tế và điểm phát sinh lỗi.

### Không sửa cùng danh sách bên trong hàm

Một operator hoặc comparator tự gọi add, remove, sort hoặc replaceAll lên chính danh sách đang được xử lý có thể phá vỡ điều kiện thao tác.

Nếu cần một quy trình phức tạp, hãy tách việc tính kết quả và áp dụng thay đổi. Đừng dựa vào cơ chế phát hiện sửa đổi như một cách điều khiển luồng hợp lệ.

## 10. Hiệu quả và thiết kế hàm truyền vào

### Với replaceAll

Nếu mỗi lần biến đổi có chi phí cố định và cơ chế duyệt/thay thế phù hợp, tổng công việc tăng theo số phần tử.

Hàm quá nặng, có I/O hoặc truy cập nguồn chậm có thể quyết định toàn bộ chi phí, dù thao tác ngoài nhìn như một lời gọi ngắn.

Nên ưu tiên:

- Hàm có ý nghĩa rõ, không phụ thuộc số lần hoặc thứ tự tác dụng phụ để đúng.
- Không sửa chính nguồn.
- Kiểm tra dữ liệu cần thiết trước nếu có thể.
- Tách xử lý bên ngoài khỏi biến đổi phần tử.

### Với sort

Sort có thể gọi comparator nhiều lần và với nhiều cặp theo thứ tự mà bạn không nên phụ thuộc. Comparator không phải hàm biến đổi “mỗi phần tử đúng một lần”.

Nếu khóa so sánh rất đắt để tính, cân nhắc chuẩn bị khóa hoặc một mô hình dữ liệu trung gian phù hợp trước khi sort. Tránh đặt thao tác gọi dịch vụ hoặc thay đổi dữ liệu vào comparator.

Không suy từ tên giao diện List rằng mọi lớp sẽ sort theo cùng một thuật toán hoặc có cùng chi phí. Tính ổn định là phần hợp đồng cần dùng; chi tiết triển khai phải xem theo lớp.

### Sắp xếp không duy trì thứ tự cho các lần thêm về sau

Một lần sort chỉ xử lý trạng thái lúc thao tác thành công. Nếu sau đó thêm phần tử hoặc sửa giá trị quyết định thứ tự, danh sách không tự giữ có thứ tự theo comparator cũ.

Cần sắp xếp lại khi yêu cầu dùng thứ tự, hoặc chọn mô hình dữ liệu khác phù hợp với nhu cầu duy trì trật tự.

## 11. Những lỗi thường gặp

### Tưởng replaceAll lọc phần tử

Nó thay mỗi phần tử bằng kết quả, không bỏ phần tử. Trả null không có nghĩa xóa vị trí đó.

### Tưởng sort loại trùng

Danh sách vẫn có thể giữ nhiều phần tử so bằng nhau. Tính ổn định chỉ quy định thứ tự tương đối của chúng.

### Gán kết quả của phương thức void

Cả replaceAll và sort đều không trả List mới. Dùng hai câu lệnh riêng hoặc tự tạo bản sao khi cần kết quả độc lập.

### Gọi trên List.of vì “chỉ đổi thứ tự, không thêm/xóa”

Thay thế và sắp xếp vẫn là sửa danh sách. Danh sách không cho sửa đổi có thể từ chối ngay.

### Cho rằng Arrays.asList hoàn toàn bất biến

Nó cố định kích thước nhưng có thể thay phần tử. Ví dụ đã cho thấy replaceAll và sort cũng phản ánh lên mảng nguồn.

### Dùng comparator bằng phép trừ

Sai dấu do tràn có thể phá hợp đồng thứ tự. Dùng hàm so sánh đúng kiểu hoặc các hàm tạo comparator.

### Mong thứ tự ổn định tự sắp theo một tiêu chí phụ

Nếu cần id hoặc một thuộc tính khác để phá hòa, phải khai báo tiêu chí đó. Ổn định giữ thứ tự cũ trong nhóm ngang hàng.

### Gọi sort trước chuẩn hóa rồi mặc định vẫn đúng

Phép biến đổi có thể làm đổi quan hệ thứ tự. Xác định khóa muốn sắp trước khi chọn thứ tự các bước.

### Bắt lỗi rồi coi dữ liệu vẫn nguyên vẹn

Thử nghiệm ArrayList cho thấy replaceAll có thể đã sửa một phần. Khi cần giữ nguồn, kiểm soát bản sao và tác dụng phụ từ đầu.

## 12. Thực hành

### Bài 1: dự đoán quy trình chuỗi

Tạo một ArrayList từ:

```text
[" Z ", "b", " A", "b "]
```

Chuẩn hóa bằng strip và chữ thường theo Locale.ROOT, rồi sort tự nhiên.

Trước khi chạy, hãy dự đoán:

- Nội dung sau replaceAll.
- Nội dung sau sort.
- Số phần tử còn lại.
- Hai phần tử b có bị loại đi không.

### Bài 2: tính ổn định hay tiêu chí phụ?

Với Ticket trong chương trình:

1. Chỉ sort theo priority.
2. Đối chiếu thứ tự trong từng nhóm priority.
3. Sau đó thêm id giảm dần làm tiêu chí phụ.
4. Giải thích kết quả nào đến từ comparator và kết quả nào đến từ tính ổn định.

### Bài 3: thay nguồn dữ liệu

Chạy các thao tác phù hợp trên:

- Một ArrayList bản sao.
- Một view từ Arrays.asList.
- Một List.of.

Ghi rõ thao tác nào sửa được, thao tác nào bị từ chối, và dữ liệu nguồn nào cùng thay đổi qua quan hệ chia sẻ.

### Bài 4: chính sách null

Tạo danh sách cho phép null và chọn một chính sách:

- Giữ null nhưng đặt ở cuối khi sort.
- Thay null bằng chuỗi rỗng trước khi sort.
- Từ chối toàn bộ dữ liệu trước khi bắt đầu sửa.

Mô tả ý nghĩa của từng chính sách. Không coi ba lựa chọn là cùng một kết quả nghiệp vụ.

### Bài 5: lỗi giữa chừng

Từ PartialReplaceAllDemo:

1. Đặt số 0 ở đầu, giữa và cuối trong các thử nghiệm riêng.
2. Theo dõi trạng thái ArrayList sau lỗi.
3. Làm lại trên bản sao cấu trúc.
4. Giải thích vì sao bản sao với Integer khác tình huống operator sửa thuộc tính một đối tượng khả biến dùng chung.
5. Xác định thời điểm được phép công bố kết quả cho bên sử dụng.

Tiêu chí hoàn thành là phân biệt đúng biến đổi với sắp xếp, chọn hàm phù hợp, giữ rõ quyền sửa dữ liệu và không giả định nguồn có khả năng sửa hoặc khả năng hoàn tác mà hợp đồng chưa cam kết.
