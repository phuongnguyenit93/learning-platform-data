# indexOf, lastIndexOf và tìm phần tử không tồn tại

Một danh sách có thể chứa nhiều phần tử giống nhau. Khi cần biết vị trí của một giá trị, ta không chỉ hỏi “có hay không” mà còn phải xác định muốn lấy **lần xuất hiện đầu tiên**, **lần cuối cùng** hay **mọi vị trí**.

`List.indexOf` và `List.lastIndexOf` giải quyết hai câu hỏi đầu:

- `indexOf(target)`: vị trí xuất hiện đầu tiên của phần tử phù hợp.
- `lastIndexOf(target)`: vị trí xuất hiện cuối cùng của phần tử phù hợp.
- Không tìm thấy phần tử phù hợp: trả về `-1`.

Điểm dễ gây lỗi là `-1` vẫn có kiểu `int`, nhưng **không phải chỉ số hợp lệ để truy cập danh sách**.

Bài dùng Java 17. Ba chương trình hoàn chỉnh đã được biên dịch với `--release 17` và chạy để đối chiếu stdout. Các đoạn rút gọn khác minh họa thao tác trong một phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn có thể:

- Đọc đúng chỉ số đầu/cuối trong một danh sách có phần tử trùng.
- Xử lý `-1` trước khi dùng kết quả với `get` hoặc thao tác theo vị trí.
- Giải thích quy tắc so khớp bằng `equals`.
- Phân biệt tìm `null`, tìm chuỗi, tìm đối tượng và tìm theo thuộc tính.
- Nhận diện những trường hợp cần một vòng duyệt thay vì lặp lại indexOf.

## 1. Mô hình vị trí của List

Xét danh sách:

```text
Giá trị:   Lan   Minh   Lan   An   Lan
Chỉ số:     0     1      2    3     4
```

Các vị trí bắt đầu từ `0`. Danh sách có `5` phần tử, nên chỉ số hợp lệ là `0..4`.

Với giá trị `"Lan"`:

```text
indexOf("Lan")     = 0
lastIndexOf("Lan") = 4
```

Với giá trị `"Minh"`:

```text
indexOf("Minh")     = 1
lastIndexOf("Minh") = 1
```

Với giá trị `"Mai"`:

```text
indexOf("Mai")     = -1
lastIndexOf("Mai") = -1
```

### Chỉ số cuối cùng vẫn tính từ đầu danh sách

`lastIndexOf` trả về chỉ số thông thường của danh sách. Nó không trả số bước tính từ cuối về đầu.

Trong ví dụ, `"Lan"` cuối cùng ở chỉ số `4`, nên kết quả là `4`, không phải `0` vì phần tử nằm sát cuối.

### Hai giá trị đầu/cuối không cho biết mọi vị trí

Biết đầu tiên là `0` và cuối cùng là `4` chưa cho biết các vị trí ở giữa. Chúng có thể là `0, 2, 4`, hoặc một cách phân bố khác.

Không thể lấy:

```text
lastIndex - firstIndex + 1
```

làm số lần xuất hiện, vì khoảng giữa hai vị trí có thể chứa các phần tử khác.

## 2. Chữ ký và ý nghĩa của hai phương thức

Dạng chữ ký:

```java
int indexOf(Object target);
int lastIndexOf(Object target);
```

Đây là mô tả chữ ký của `List`, không phải một tệp Java độc lập.

Ý nghĩa theo hợp đồng:

| Phương thức | Kết quả khi tìm thấy |
| --- | --- |
| `indexOf(target)` | Chỉ số nhỏ nhất của phần tử phù hợp |
| `lastIndexOf(target)` | Chỉ số lớn nhất của phần tử phù hợp |

Hai phương thức:

- Không làm thay đổi danh sách.
- Không sắp xếp lại dữ liệu.
- Không xóa các phần tử trùng.
- Không yêu cầu danh sách đã sắp xếp.
- Trả về chỉ số, không trả về chính đối tượng phần tử.

Với đối số được nguồn chấp nhận, không có phần tử phù hợp thì kết quả là `-1`. Một danh sách rỗng cũng không có vị trí phù hợp nên trả `-1`.

### indexOf khác get

| Lời gọi | Đối số có nghĩa gì? | Kết quả |
| --- | --- | --- |
| `list.get(1)` | Chỉ số `1` | Phần tử ở vị trí đó |
| `list.indexOf(1)` trên `List<Integer>` | Giá trị số `1` cần tìm | Chỉ số đầu tiên chứa giá trị phù hợp hoặc `-1` |

Đối số số nguyên truyền cho `indexOf` được dùng như một giá trị cần tìm, không phải chỉ số truy cập.

Vì chữ ký nhận `Object`, khả năng biên dịch của một lời gọi không tự chứng minh đối số đó phù hợp với hợp đồng của mọi lớp triển khai. Nên giữ đúng mô hình kiểu phần tử và đọc chính sách của nguồn đối với các giá trị bị hạn chế.

## 3. Phần tử phù hợp được xác định như thế nào?

Về ý nghĩa, một vị trí phù hợp khi:

```java
Objects.equals(target, list.get(index))
```

biểu diễn quan hệ bằng nhau cần tìm.

Đoạn này cần `java.util.Objects` nếu viết trong mã. Nó mô tả hợp đồng so khớp, không yêu cầu mọi lớp triển khai phải dùng đúng biểu thức và thuật toán truy cập theo chỉ số như trên.

### equals khác so sánh tham chiếu

Hai đối tượng khác nhau trong bộ nhớ có thể bằng nhau theo `equals`.

Ví dụ:

- Hai chuỗi có cùng nội dung có thể được xem bằng nhau dù không cùng đối tượng.
- Một kiểu record có các thành phần bằng nhau cung cấp phép bằng nhau theo giá trị.
- Một lớp không ghi đè `equals` sẽ giữ ý nghĩa mặc định của `Object.equals`, dựa trên cùng đối tượng.

Vì vậy, nếu tìm bằng một đối tượng mới nhưng luôn nhận `-1`, hãy kiểm tra hợp đồng `equals` của kiểu trước khi kết luận indexOf không hoạt động.

### Không tự dùng comparator hoặc thứ tự tự nhiên

Một danh sách đã được sắp bằng comparator vẫn dùng hợp đồng bằng nhau của phần tử khi gọi indexOf.

“Đứng ngang hàng trong phép sắp xếp” và “bằng nhau theo equals” là hai quan hệ cần phân biệt. Việc truyền comparator cho một lần sắp xếp không lưu comparator đó như chính sách tìm kiếm mới của danh sách.

### Với String: tìm cả phần tử, không tìm chuỗi con

`String.equals` so nội dung có phân biệt hoa/thường. Nó không tự bỏ khoảng trắng hoặc chuẩn hóa đầu vào.

Ví dụ:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `List.of("Lan").indexOf("Lan")` | Tìm một phần tử bằng chuỗi Lan |
| `List.of("Lan").indexOf("lan")` | Không khớp theo quy tắc equals của String |
| `List.of("Lan").indexOf("an")` | Không tìm chuỗi con trong phần tử Lan |
| `"Lan".indexOf("an")` | Phương thức của String, tìm chuỗi con trong một chuỗi |

Các tên phương thức giống nhau không có nghĩa đối tượng nhận lời gọi và loại tìm kiếm giống nhau.

Nếu bài toán muốn tìm không phân biệt hoa/thường, tìm chuỗi con hoặc tìm theo một thuộc tính, hãy dùng tiêu chí riêng một cách tường minh.

## 4. Chương trình hoàn chỉnh: đầu, cuối và mọi vị trí

Tạo tệp **`ListPositionLookupDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;

public class ListPositionLookupDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "Lan", "An", "Lan");

        System.out.println("names = " + names);
        show(names, "Lan");
        show(names, "Minh");
        show(names, "Mai");
        show(names, "lan");

        List<Integer> positions = new ArrayList<>();
        ListIterator<String> cursor = names.listIterator();
        while (cursor.hasNext()) {
            int index = cursor.nextIndex();
            if (Objects.equals(cursor.next(), "Lan")) {
                positions.add(index);
            }
        }
        System.out.println("all Lan positions = " + positions);
    }

    private static void show(List<String> values, String target) {
        int first = values.indexOf(target);
        int last = values.lastIndexOf(target);
        System.out.println(target + ": first=" + first + ", last=" + last);

        if (first < 0) {
            System.out.println("  not found");
        } else {
            System.out.println("  get(first) = " + values.get(first));
        }
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ListPositionLookupDemo.java
java -Dfile.encoding=UTF-8 ListPositionLookupDemo
```

Stdout đã kiểm chứng:

```text
names = [Lan, Minh, Lan, An, Lan]
Lan: first=0, last=4
  get(first) = Lan
Minh: first=1, last=1
  get(first) = Minh
Mai: first=-1, last=-1
  not found
lan: first=-1, last=-1
  not found
all Lan positions = [0, 2, 4]
```

### Đọc kết quả

- Lan xuất hiện tại `0, 2, 4`; hai phương thức trả lần lượt `0` và `4`.
- Minh chỉ xuất hiện tại `1`, nên đầu và cuối trùng nhau.
- Mai không tồn tại, nên cả hai kết quả đều là `-1`.
- Chuỗi `"lan"` khác `"Lan"` theo `String.equals`, nên không khớp.
- Nhánh `first < 0` xử lý không tìm thấy; nhánh còn lại mới gọi `get(first)`.
- Vị trí `0` được nhận diện là tìm thấy bình thường.

### Vì sao có thêm vòng duyệt tìm mọi vị trí?

Danh sách vị trí `[0, 2, 4]` được thu thập bằng một lượt ListIterator:

1. Đọc `nextIndex()` trước khi lấy phần tử.
2. `next()` trả phần tử tại chỉ số đó.
3. Nếu phù hợp, lưu chỉ số.

Đây là một lượt duyệt riêng có tiêu chí rõ ràng. `indexOf` và `lastIndexOf` không trả về tập vị trí đó thay cho chương trình.

Dùng `Objects.equals` trong vòng duyệt giúp tiêu chí so khớp xử lý được cả trường hợp tham chiếu `null`, khi nguồn cho phép chúng.

## 5. Xử lý -1 an toàn

Một cách dùng phù hợp:

```java
int found = values.indexOf(target);

if (found >= 0) {
    String value = values.get(found);
    System.out.println(value);
} else {
    System.out.println("Không tìm thấy");
}
```

Đoạn minh họa giả định `values` là danh sách chuỗi, `target` là giá trị cần tìm và danh sách không bị thay đổi giữa các thao tác.

### Lỗi: dùng kết quả trực tiếp

```java
String value = values.get(values.indexOf(target));
```

Nếu không tìm thấy, chương trình thực hiện `get(-1)`, gây `IndexOutOfBoundsException`.

Không tìm thấy phần tử là một kết quả bình thường của tìm kiếm; biến nó thành lỗi truy cập chỉ số thường là do thiếu nhánh xử lý trong ứng dụng.

### Lỗi: chỉ kiểm tra lớn hơn 0

```java
if (found > 0) {
    System.out.println("Đã tìm thấy");
}
```

Điều kiện này bỏ qua phần tử ở vị trí đầu tiên. Một chỉ số hợp lệ có thể bằng `0`.

Hai cách kiểm tra thường dùng là:

```text
found >= 0
found != -1
```

Cách thứ nhất diễn đạt trực tiếp miền chỉ số không âm.

### Lỗi: chỉ kiểm tra nhỏ hơn size

Với danh sách không rỗng, `-1 < values.size()` vẫn đúng. Chỉ kiểm tra cận trên không loại được giá trị báo thiếu.

Nếu đang kiểm tra một chỉ số bất kỳ để truy cập List, cần đủ hai cận:

```text
0 <= index < size
```

Với chỉ số vừa nhận từ indexOf trong một danh sách không thay đổi, nhánh `found >= 0` đã dựa vào hợp đồng của kết quả để biết nó nằm trong cận trên.

### Lỗi: đổi -1 thành 0 để “có giá trị mặc định”

Việc ép một kết quả thiếu về vị trí đầu không làm phần tử cần tìm xuất hiện. Nó khiến chương trình lấy một phần tử khác nhưng có vẻ vẫn chạy.

Nếu cần hành vi dự phòng, hãy viết nhánh đó rõ ràng: hiển thị thông báo, trả kết quả rỗng theo hợp đồng API, hoặc xử lý theo yêu cầu nghiệp vụ. Không dùng chỉ số giả để che sự vắng mặt.

## 6. Null là một phần tử khác với không tìm thấy

Với một danh sách cho phép `null`:

```text
[null, A, null, B]
```

có thể có:

```text
indexOf(null)     = 0
lastIndexOf(null) = 2
```

`-1` báo rằng không có vị trí phù hợp. Nó không có cùng ý nghĩa với “phần tử tại vị trí tìm được là null”.

Cần phân biệt:

| Tình huống | Kết quả tìm vị trí |
| --- | --- |
| Có phần tử null ở đầu | Chỉ số `0` |
| Có phần tử null ở vị trí khác | Chỉ số không âm tương ứng |
| Không có phần tử phù hợp | `-1`, nếu đối số được nguồn chấp nhận |

### Nguồn có thể hạn chế null

Không phải mọi List đều cho phép phần tử `null` hoặc chấp nhận truy vấn `null` theo cùng chính sách. Ví dụ, các danh sách không cho phép null có thể từ chối kiểu truy vấn đó bằng `NullPointerException`.

Không nên tự quy ước rằng mọi lời gọi `indexOf(null)` trên mọi List chắc chắn chỉ trả số hoặc `-1`. Hãy xác định hợp đồng nguồn.

Trong chương trình sau, nguồn được chọn là `ArrayList`, tạo từ một đầu vào có phần tử null để tình huống được xác định rõ.

## 7. Chương trình hoàn chỉnh: thiếu, rỗng và null

Tạo tệp **`MissingAndNullDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class MissingAndNullDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(Arrays.asList(null, "A", null, "B"));

        System.out.println("values = " + values);
        System.out.println("first null = " + values.indexOf(null));
        System.out.println("last null = " + values.lastIndexOf(null));

        int found = values.indexOf("Z");
        System.out.println("Z position = " + found);

        if (found >= 0) {
            System.out.println("Z value = " + values.get(found));
        } else {
            System.out.println("Z is absent");
        }

        try {
            values.get(found);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("get(-1) = "
                    + exception.getClass().getSimpleName());
        }

        List<String> empty = List.of();
        System.out.println("empty first A = " + empty.indexOf("A"));
        System.out.println("empty last A = " + empty.lastIndexOf("A"));

        List<Integer> numbers = List.of(10, 20, 10);
        System.out.println("numbers.get(1) = " + numbers.get(1));
        System.out.println("numbers.indexOf(1) = " + numbers.indexOf(1));
        System.out.println("numbers.lastIndexOf(10) = " + numbers.lastIndexOf(10));
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 MissingAndNullDemo.java
java -Dfile.encoding=UTF-8 MissingAndNullDemo
```

Stdout đã kiểm chứng:

```text
values = [null, A, null, B]
first null = 0
last null = 2
Z position = -1
Z is absent
get(-1) = IndexOutOfBoundsException
empty first A = -1
empty last A = -1
numbers.get(1) = 20
numbers.indexOf(1) = -1
numbers.lastIndexOf(10) = 2
```

### Những trường hợp đã kiểm chứng

1. `null` có vị trí đầu và cuối cụ thể.
2. Z không tồn tại, nên nhận `-1`.
3. Nhánh kiểm tra chỉ số xử lý Z vắng mặt mà không gọi `get`.
4. Lần gọi `get(found)` ngoài nhánh an toàn được cố ý đặt trong thử nghiệm để thấy `get(-1)` gây lỗi.
5. Danh sách rỗng trả `-1` khi tìm A.
6. `numbers.get(1)` trả phần tử `20`.
7. `numbers.indexOf(1)` lại tìm giá trị `1`, không có nên trả `-1`.
8. `lastIndexOf(10)` trả vị trí cuối của giá trị `10`, là `2`.

Khối bắt ngoại lệ trong chương trình dùng để minh họa một cách sử dụng sai đã biết. Trong mã xử lý tìm kiếm thông thường, hãy kiểm tra kết quả trước khi truy cập thay vì dùng ngoại lệ làm nhánh “không tìm thấy”.

## 8. Tìm đối tượng không phải tự động tìm theo một thuộc tính

Giả sử một sản phẩm gồm:

```text
code
name
```

Ta có thể cần hai bài toán khác nhau:

- Tìm một Product bằng nhau theo `equals`.
- Tìm sản phẩm có cùng code, bất kể name.

`indexOf` chỉ trực tiếp giải bài toán thứ nhất theo hợp đồng của Product. Nó không biết thuộc tính code có ý nghĩa nghiệp vụ đặc biệt nào nếu bạn chưa thiết kế như vậy.

Trong chương trình, Product là record. Phép bằng nhau do record cung cấp xét các thành phần code và name.

### Chương trình hoàn chỉnh

Tạo tệp **`ObjectPositionLookupDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class ObjectPositionLookupDemo {
    public record Product(String code, String name) {
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P1", "Pen"),
                new Product("P2", "Book"),
                new Product("P1", "Pen"));

        Product sameValue = new Product("P1", "Pen");
        Product sameCodeOnly = new Product("P1", "Pencil");

        System.out.println("same reference = " + (products.get(0) == sameValue));
        System.out.println("same value = " + products.get(0).equals(sameValue));
        System.out.println("sameValue first = " + products.indexOf(sameValue));
        System.out.println("sameValue last = " + products.lastIndexOf(sameValue));
        System.out.println("sameCodeOnly indexOf = " + products.indexOf(sameCodeOnly));
        System.out.println("find P1 by code = " + firstIndexByCode(products, "P1"));
        System.out.println("find P9 by code = " + firstIndexByCode(products, "P9"));
    }

    private static int firstIndexByCode(List<Product> products, String code) {
        for (int index = 0; index < products.size(); index++) {
            if (Objects.equals(products.get(index).code(), code)) {
                return index;
            }
        }
        return -1;
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ObjectPositionLookupDemo.java
java -Dfile.encoding=UTF-8 ObjectPositionLookupDemo
```

Stdout đã kiểm chứng:

```text
same reference = false
same value = true
sameValue first = 0
sameValue last = 2
sameCodeOnly indexOf = -1
find P1 by code = 0
find P9 by code = -1
```

### Vì sao một đối tượng mới vẫn tìm được?

`sameValue` không phải cùng tham chiếu với phần tử đầu, nhưng code và name đều giống. Theo phép bằng nhau của record, chúng bằng nhau nên indexOf tìm được ở `0`.

Vì cũng có một Product bằng nhau ở cuối, lastIndexOf trả `2`.

### Vì sao cùng code vẫn có thể không tìm được?

`sameCodeOnly` có code P1 nhưng name Pencil, khác name Pen ở dữ liệu nguồn. Theo phép bằng nhau của record đang dùng, nó không khớp.

Hàm `firstIndexByCode` mô tả một tiêu chí khác:

```text
Mã sản phẩm bằng code cần tìm
```

Do đó tìm P1 theo code trả `0`, còn tìm P9 trả `-1`.

Hàm minh họa giả định các phần tử Product không null. Việc dùng `Objects.equals` cho code giúp so các giá trị code có thể null, nhưng không tự bảo vệ thao tác gọi `code()` trên một phần tử Product null.

### Có nên sửa equals để indexOf tìm đúng theo code?

Chỉ sửa nếu “hai Product bằng nhau khi cùng code” là hợp đồng đúng của kiểu trong toàn hệ thống. `equals` còn ảnh hưởng nhiều nơi khác, không riêng một lần tìm kiếm.

Nếu chỉ màn hình hoặc tác vụ hiện tại cần tìm theo một thuộc tính, hãy viết tiêu chí tìm riêng. Không thay đổi định nghĩa bằng nhau của cả kiểu chỉ để tiết kiệm một vòng duyệt.

## 9. Chỉ số tìm được gắn với trạng thái danh sách

Kết quả là một vị trí trong danh sách tại lúc tìm, không phải mã định danh ổn định của phần tử.

Đoạn minh họa:

```java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

int found = values.indexOf("B"); // found = 1
values.add(0, "X");

// values hiện là [X, A, B, C].
// values.get(found) bây giờ trả A, không phải B.
```

Chèn ở đầu đã làm vị trí B thay đổi.

Các thao tác có thể khiến chỉ số đã lưu không còn mang ý nghĩa cũ gồm:

- Chèn hoặc xóa trước vị trí đó.
- Sắp xếp lại danh sách.
- Thay phần tử tại vị trí tìm được.
- Đổi dữ liệu mà quy tắc equals dựa vào.

Vì vậy:

- Dùng chỉ số ngay trong phạm vi trạng thái được giữ ổn định.
- Nếu phải lưu nhận diện lâu dài, dùng định danh phù hợp thay vì chỉ số.
- Nếu có nhiều bên sửa, việc tìm rồi truy cập cần cơ chế phối hợp theo yêu cầu.
- Một collection có các phương thức an toàn luồng cũng không tự làm chuỗi “tìm rồi dùng chỉ số” nguyên tử.

Trong những ví dụ hoàn chỉnh của bài, dữ liệu không có bên sửa đồng thời giữa tìm và truy cập, nên điều kiện đó được xác định rõ.

## 10. Chi phí và khi nào nên dùng một lượt duyệt

Ở các danh sách thông dụng như ArrayList và LinkedList, tìm theo giá trị có thể phải kiểm tra nhiều phần tử. Trường hợp xấu nhất thường tăng theo số phần tử.

Hai phương thức còn có thể dừng ở những điểm khác nhau:

- Khi phần tử phù hợp nằm ở đầu, indexOf có thể tìm thấy sớm.
- Khi nó nằm ở cuối, lastIndexOf có thể tìm thấy sớm.
- Không tồn tại thì phải xác định rằng không có vị trí phù hợp trong phạm vi tìm.

Đừng dùng các ví dụ nhỏ để cho rằng tìm kiếm theo giá trị luôn có chi phí không đổi.

### Tránh contains rồi indexOf khi chỉ cần vị trí

Một mẫu không cần thiết thường gặp:

```java
if (values.contains(target)) {
    int found = values.indexOf(target);
    System.out.println(found);
}
```

Nếu mục tiêu đã là lấy chỉ số, gọi indexOf một lần rồi kiểm tra `-1` thường đủ. Hai lời gọi trên có thể tạo hai lượt tìm, và nếu nguồn thay đổi giữa chúng thì hai kết quả còn có thể không cùng trạng thái.

Ngược lại, nếu chỉ cần câu trả lời có/không, `contains` diễn đạt ý định trực tiếp.

### Khi cần mọi vị trí

Dùng một vòng duyệt và thu thập các chỉ số phù hợp, như chương trình đầu.

`List.indexOf` không có tham số bắt đầu kiểu `fromIndex` như một số phương thức tìm của String. Nếu cứ tìm lại trên các đoạn danh sách, bạn phải tự xử lý độ lệch chỉ số và có thể tạo nhiều lượt quét.

Một lượt iterator có chỉ số giúp nhìn rõ phạm vi và tránh tìm lại cùng dữ liệu một cách không cần thiết.

### Khi tìm theo thuộc tính

Một vòng duyệt với điều kiện tường minh thường phù hợp cho tác vụ đơn lẻ.

Nếu hệ thống thường xuyên tra dữ liệu theo một khóa, hãy xem lại mô hình lưu trữ: có thể cần một chỉ mục hoặc Map đi kèm. Tuy nhiên, phải giữ rõ yêu cầu về phần tử trùng, thứ tự và đồng bộ dữ liệu; không mặc định đổi List thành Map mà vẫn giữ nguyên mọi ý nghĩa.

### Cẩn thận với vòng get(index) trên LinkedList

Hàm tìm theo code trong ví dụ nhấn mạnh cách quyết định vị trí trên một dữ liệu nhỏ. Nếu dùng một thuật toán truy cập từng chỉ số trên danh sách liên kết lớn, việc tìm lại nút cho mỗi get có thể làm tổng chi phí tăng không phù hợp.

Khi cần duyệt chung cho nhiều kiểu List, một ListIterator hoặc cơ chế duyệt tuần tự có thể tránh giả định về truy cập ngẫu nhiên. Đây là chuyện chọn thuật toán phù hợp cấu trúc, không làm thay đổi hợp đồng kết quả `-1` hoặc chỉ số tìm thấy.

## 11. Lỗi thường gặp

### Nhầm -1 với phần tử cuối

Trong List của Java, `-1` không phải cú pháp truy cập phần tử cuối. Nó là giá trị báo không tìm thấy của hai phương thức đang học.

### Bỏ qua vị trí 0

Dùng `found > 0` làm điều kiện tìm thấy sẽ khiến dữ liệu đầu danh sách bị coi như không có. Dùng kiểm tra miền không âm.

### Tưởng lastIndexOf đếm từ cuối

Chỉ số trả về vẫn theo hệ chỉ số từ đầu danh sách. Phần tử cuối của danh sách kích thước n có chỉ số `n - 1`.

### Tưởng indexOf tìm chuỗi con hoặc tự bỏ qua hoa/thường

Với List<String>, phép tìm vẫn so cả phần tử bằng String.equals. Muốn tiêu chí khác thì phải mô tả khác.

### Tưởng cùng mã là equals tự động

Ý nghĩa bằng nhau phụ thuộc kiểu phần tử. Record có nhiều thành phần không tự coi một thành phần là khóa duy nhất.

### Dùng get trước khi kiểm tra -1

Đảo thứ tự này gây lỗi truy cập khi đối tượng không tồn tại. Không tìm thấy là một nhánh cần được dự tính trước.

### Dùng phần tử null để kết luận không tìm thấy

Tìm được một vị trí đang chứa null vẫn là tìm thấy. Dùng kết quả chỉ số để phân biệt sự tồn tại, không chỉ nhìn giá trị trả về từ get.

### Lưu chỉ số qua nhiều thay đổi

Chỉ số không phải định danh ổn định. Nếu danh sách được sửa hoặc sắp xếp lại, phải đánh giá lại cách dùng vị trí cũ.

### Lấy khoảng đầu-cuối làm số lượng phần tử trùng

Khoảng đó có thể chứa các giá trị khác. Muốn đếm hoặc lấy mọi vị trí, cần duyệt theo tiêu chí cần thiết.

## 12. Thực hành

### Bài 1: dự đoán vị trí

Với:

```text
[red, blue, red, green, red]
```

Không chạy mã trước, hãy điền:

| Giá trị cần tìm | indexOf | lastIndexOf |
| --- | --- | --- |
| red | ? | ? |
| blue | ? | ? |
| yellow | ? | ? |
| RED | ? | ? |

Giải thích quy tắc dùng để tìm và vì sao số lần xuất hiện của red không bằng khoảng từ chỉ số đầu đến cuối.

### Bài 2: sửa nhánh không tìm thấy

Đoạn mã:

```java
int found = names.indexOf(target);
System.out.println(names.get(found));
```

Hãy bổ sung nhánh xử lý để:

1. Phần tử ở vị trí `0` vẫn được nhận là tìm thấy.
2. Đối tượng không tồn tại không gây lỗi get.
3. Không biến `-1` thành một vị trí giả.
4. Không tìm kiếm hai lần khi chỉ cần một kết quả vị trí.

### Bài 3: phân biệt null và vắng mặt

Tạo ArrayList từ:

```text
[A, null, B, null]
```

Dự đoán:

- Vị trí đầu của null.
- Vị trí cuối của null.
- Kết quả tìm C.
- Điều kiện để phân biệt tìm thấy null với không tìm thấy.

Hai vị trí null cần lần lượt là `1` và `3`; tìm C trả `-1`.

### Bài 4: tìm theo giá trị và tìm theo thuộc tính

Từ ObjectPositionLookupDemo:

1. Thêm Product có code P1 nhưng name khác.
2. Tìm đối tượng bằng cả code và name.
3. Tìm lần đầu theo code.
4. Viết một lượt duyệt để lấy mọi vị trí theo code.
5. Giải thích vì sao hai tiêu chí có thể cho các tập vị trí khác nhau.

### Bài 5: kiểm tra chỉ số đã cũ

Tìm vị trí B trong `[A, B, C]`, sau đó thử riêng từng thao tác:

- Chèn X ở đầu.
- Xóa A.
- Thay B bằng Y ở vị trí đang biết.

Theo dõi giá trị của biến chỉ số và nội dung tại vị trí đó. Nêu khi nào chỉ số còn biểu diễn đúng phần tử ban đầu và khi nào cần tìm lại hoặc dùng một cách nhận diện khác.

Tiêu chí hoàn thành là xác định đúng quan hệ so khớp, chọn đúng chỉ số đầu/cuối, xử lý rõ sự vắng mặt và chỉ dùng kết quả vị trí trong trạng thái danh sách phù hợp.
