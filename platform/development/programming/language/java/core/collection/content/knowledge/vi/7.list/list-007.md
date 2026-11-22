# subList với khoảng đầu bao gồm, cuối không bao gồm

## 1. subList chọn một khoảng vị trí như thế nào?

`List.subList(fromIndex, toIndex)` trả về một danh sách nhìn vào đoạn liên tiếp của danh sách ban đầu. Khoảng được viết là `[fromIndex, toIndex)`:

- Dấu `[` ở đầu nghĩa là lấy phần tử tại `fromIndex`.
- Dấu `)` ở cuối nghĩa là dừng trước `toIndex`, không lấy phần tử tại chỉ số đó.
- Các phần tử được chọn vẫn theo thứ tự của danh sách ban đầu.

Với danh sách `[A, B, C, D, E]`:

| Chỉ số trong danh sách gốc | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Phần tử | A | B | C | D | E |
| Thuộc khoảng `[1, 4)`? | Không | Có | Có | Có | Không |

Vì vậy, `list.subList(1, 4)` cho đoạn `[B, C, D]`. Nó không chọn `E`, cũng không hiểu đối số thứ hai là “lấy 4 phần tử”.

Đoạn minh họa trong một phương thức, với các import `java.util.List` và `java.util.ArrayList`:

```java
List<String> letters =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));

List<String> middle = letters.subList(1, 4);

// middle = [B, C, D]
// middle.size() = 3
```

Có hai kiến thức cần đi cùng nhau: cách tính khoảng và bản chất kết quả. Kết quả là một khung nhìn (view) có liên hệ với danh sách gốc, không mặc nhiên là một bản sao độc lập. Đọc đúng hai biên nhưng hiểu sai quan hệ này vẫn có thể làm chương trình sửa nhầm dữ liệu. [List.subList trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

## 2. Vì sao dùng đầu bao gồm và cuối không bao gồm?

### 2.1. Độ dài được tính bằng phép trừ hai biên

Nếu khoảng hợp lệ, kích thước ban đầu của kết quả là:

```text
length = toIndex - fromIndex
```

Ví dụ:

| Lời gọi trên danh sách 5 phần tử | Các chỉ số được lấy | Kết quả | Kích thước |
|---|---|---|---|
| `subList(0, 2)` | 0, 1 | `[A, B]` | 2 |
| `subList(1, 4)` | 1, 2, 3 | `[B, C, D]` | 3 |
| `subList(4, 5)` | 4 | `[E]` | 1 |
| `subList(0, 5)` | 0, 1, 2, 3, 4 | `[A, B, C, D, E]` | 5 |
| `subList(2, 2)` | Không có | `[]` | 0 |
| `subList(5, 5)` | Không có | `[]` | 0 |

Muốn lấy `count` phần tử bắt đầu ở `from`, biên cuối là `from + count`, sau khi đã bảo đảm phép tính không tràn số và không vượt kích thước danh sách. Không dùng `from + count - 1` làm `toIndex`; cách đó làm thiếu phần tử cuối.

Nếu bài toán cho một chỉ số cuối có bao gồm, chẳng hạn muốn lấy từ chỉ số 1 đến hết chỉ số 3, thì khoảng tương ứng là `[1, 4)`. Việc chuyển từ “chỉ số cuối được lấy” sang “biên dừng” phải được thực hiện rõ ràng.

### 2.2. Hai khoảng kề nhau dùng chung biên

Có thể chia danh sách ở vị trí `split` thành:

```java
List<String> left = letters.subList(0, split);
List<String> right = letters.subList(split, letters.size());
```

Đây là các biểu thức minh họa, giả sử `letters` và `split` đã được khai báo hợp lệ. Phần tử tại `split` chỉ thuộc phía phải. Hai khoảng không bỏ sót hoặc lặp lại phần tử ở điểm chia.

Ví dụ, với `split = 2` trên `[A, B, C, D, E]`, hai đoạn là `[A, B]` và `[C, D, E]`. Nếu chỉ đọc, đây là cách chia thuận tiện. Nếu định sửa cấu trúc một đoạn trong khi giữ đoạn kia, cần xử lý quan hệ giữa các view được giải thích phía dưới.

### 2.3. size() là biên hợp lệ, nhưng không phải chỉ số phần tử hợp lệ

Danh sách có `n` phần tử có chỉ số phần tử từ 0 đến `n - 1`, còn các vị trí ranh giới chạy từ 0 đến `n`.

Với `n = 5`, biên 5 nằm ngay sau `E`. Nó được dùng làm `toIndex` để lấy tới hết danh sách, nhưng `get(5)` vẫn sai. Việc cho phép `subList(5, 5)` không tạo ra một phần tử ở chỉ số 5; nó chỉ chọn khoảng rỗng ở cuối.

## 3. Điều kiện hợp lệ và khoảng rỗng

Mọi lời gọi hợp lệ đều phải thỏa:

```text
0 <= fromIndex <= toIndex <= list.size()
```

Ba điều cần kiểm tra riêng:

1. Biên đầu không âm.
2. Biên đầu không đứng sau biên cuối.
3. Biên cuối không vượt kích thước hiện tại.

`subList` không tự cắt biên cho vừa danh sách. Trên danh sách có 5 phần tử, `subList(0, 100)` không có nghĩa “lấy tối đa 100 phần tử”; đó là khoảng sai.

Với `ArrayList`, biên ngoài phạm vi gây `IndexOutOfBoundsException`, còn cặp biên đúng phạm vi nhưng đảo thứ tự như `subList(4, 2)` gây `IllegalArgumentException`. Các ví dụ ngoại lệ trong bài dùng `ArrayList`; khi xử lý một triển khai khác, xem hợp đồng cụ thể của triển khai đó thay vì dựa vào chuỗi thông báo lỗi. [ArrayList.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#subList(int,int)).

Khoảng rỗng hoàn toàn hợp lệ khi hai biên bằng nhau và nằm trong `[0, size()]`. Với danh sách rỗng, `subList(0, 0)` là khoảng hợp lệ duy nhất.

Một view rỗng không mặc nhiên là danh sách không sửa đổi được. Nếu danh sách nền cho phép thêm và view vẫn hợp lệ, có thể thêm qua view rỗng; phần tử được chèn vào vị trí ranh giới mà view đại diện. Vì vậy, đừng suy ra khả năng sửa đổi chỉ từ kết quả `isEmpty()`.

## 4. Chỉ số của kết quả bắt đầu lại từ 0

Giả sử:

```java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));
List<String> part = source.subList(1, 4);
```

Đây là đoạn khởi tạo minh họa trong một phương thức. Khi chưa có thay đổi cấu trúc, phép ánh xạ là:

```text
chỉ số trong source = fromIndex + chỉ số trong part
```

| Chỉ số trong part | Chỉ số tương ứng trong source | Giá trị |
|---|---|---|
| 0 | 1 | B |
| 1 | 2 | C |
| 2 | 3 | D |

`part.get(0)` trả `B`, không trả `A`. `part.get(3)` gây lỗi vì `part.size()` là 3. Mặc dù `source.get(3)` hợp lệ, chỉ số 3 không hợp lệ khi dùng để đọc phần tử trong `part`.

Tương tự, `part.set(1, "X")` tác động đến vị trí tương ứng với chỉ số 2 trong `source`. Các thao tác như `get`, `set`, `remove(int)`, `indexOf` trên view dùng hệ chỉ số của chính view. Nếu `part.indexOf("D")` trả 2, đó là vị trí trong `part`, không phải chỉ số 3 của danh sách gốc.

Phép ánh xạ cộng biên giúp giải thích cách view hoạt động; không nên lưu các chỉ số đã tính như danh tính bền vững của phần tử. Sau thêm hoặc xóa, vị trí của phần tử còn lại có thể thay đổi.

## 5. Chương trình đầy đủ: khoảng, biên và phân trang

Chương trình sau dùng các API có trong Java 17. Lưu thành `SubListRangeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListRangeDemo {
    private static void showRange(List<String> source, int from, int to) {
        try {
            List<String> part = source.subList(from, to);
            System.out.println("[" + from + ", " + to + ") -> "
                    + part + "; size = " + part.size());
        } catch (IndexOutOfBoundsException | IllegalArgumentException ex) {
            System.out.println("[" + from + ", " + to + ") -> "
                    + ex.getClass().getSimpleName());
        }
    }

    private static <T> List<T> pageCopy(
            List<T> source, int pageIndex, int pageSize) {
        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException("Invalid page");
        }
        int size = source.size();
        long offset = (long) pageIndex * pageSize;
        if (offset >= size) {
            return new ArrayList<>();
        }
        int from = (int) offset;
        int to = (int) Math.min((long) size, offset + pageSize);
        return new ArrayList<>(source.subList(from, to));
    }

    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        showRange(source, 1, 4);
        showRange(source, 0, source.size());
        showRange(source, 2, 2);
        showRange(source, source.size(), source.size());
        showRange(source, -1, 2);
        showRange(source, 0, 6);
        showRange(source, 4, 2);

        List<String> part = source.subList(1, 4);
        System.out.println("part.get(0) = " + part.get(0));
        System.out.println("part.get(2) = " + part.get(2));
        try {
            part.get(part.size());
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("get(size) -> IndexOutOfBoundsException");
        }

        for (int page = 0; page < 4; page++) {
            System.out.println("page " + page + " = "
                    + pageCopy(source, page, 2));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListRangeDemo.java
java SubListRangeDemo
```

Kết quả chuẩn:

```text
[1, 4) -> [B, C, D]; size = 3
[0, 5) -> [A, B, C, D, E]; size = 5
[2, 2) -> []; size = 0
[5, 5) -> []; size = 0
[-1, 2) -> IndexOutOfBoundsException
[0, 6) -> IndexOutOfBoundsException
[4, 2) -> IllegalArgumentException
part.get(0) = B
part.get(2) = D
get(size) -> IndexOutOfBoundsException
page 0 = [A, B]
page 1 = [C, D]
page 2 = [E]
page 3 = []
```

Các lời gọi đầu kiểm tra cả trường hợp thường và các biên đặc biệt. Hai khoảng `[2, 2)` và `[5, 5)` cùng rỗng nhưng đại diện cho hai vị trí khác nhau. Các lời gọi sai không được “sửa hộ” thành khoảng hợp lệ.

Phương thức `pageCopy` minh họa một chính sách phân trang cụ thể:

- `pageIndex` bắt đầu từ 0; `pageSize` phải dương.
- Trang vượt cuối trả danh sách rỗng.
- Trang cuối chỉ lấy phần còn lại: với 5 phần tử và kích thước trang 2, các khoảng là `[0, 2)`, `[2, 4)`, `[4, 5)`.
- Phép nhân được thực hiện bằng `long` ngay từ đầu bằng `(long) pageIndex * pageSize`, tránh tràn số `int` trước khi kiểm tra biên.
- Kết quả được bọc bằng `new ArrayList<>(...)` để tách cấu trúc danh sách trả về khỏi danh sách nguồn.
- Ví dụ giả sử `source` khác `null` và không bị sửa cấu trúc trong lúc tính kích thước rồi lấy khoảng.

Đây là chính sách của `pageCopy`, không phải hành vi tự có của `subList`. Một hàm khác có thể chọn báo lỗi khi yêu cầu trang ngoài phạm vi; cần quyết định rõ trong API thay vì vô tình phụ thuộc vào ngoại lệ.

## 6. Kết quả là view: thay đổi có thể phản ánh hai chiều

### 6.1. Thay thế phần tử qua view tác động vào nguồn

Đoạn minh họa:

```java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));
List<String> part = source.subList(1, 4);

part.set(1, "c");

// part = [B, c, D]
// source = [A, B, c, D, E]
```

Không có một mảng phần tử độc lập được hứa tạo ra cho `part`. View cung cấp cách thao tác trên một vùng của nguồn.

Chiều ngược lại cũng có ý nghĩa. Với `ArrayList`, thay thế một phần tử bằng `source.set(index, value)` không thay đổi kích thước và không phải thay đổi cấu trúc. Nếu phần tử nằm trong vùng đang nhìn, view thấy giá trị mới.

Điều này khác với thêm hoặc xóa trực tiếp qua nguồn. Không gộp mọi phương thức sửa đổi vào một quy tắc “gốc đổi thì view tự cập nhật ổn định”; thay đổi cấu trúc bên ngoài view có giới hạn sử dụng riêng.

### 6.2. Thêm hoặc xóa qua view có thể sửa cấu trúc nguồn

Với một `ArrayList` cho phép sửa đổi:

- `part.remove(0)` xóa phần tử đầu của view khỏi nguồn.
- `part.add(value)` thêm ở cuối view, tức chèn trước phần tử nằm ngay sau khoảng hiện tại trong nguồn.
- `part.clear()` xóa tất cả phần tử thuộc khoảng đang nhìn khỏi nguồn.
- Kích thước của view có thể thay đổi sau các thao tác này.

Do đó, cặp biên lúc tạo view không có nghĩa view mãi mãi giữ đúng số phần tử ban đầu. Sau khi thêm hoặc xóa thông qua chính view, nó tiếp tục đại diện cho đoạn đã thay đổi.

Nếu chỉ muốn bỏ biến view, không gọi `clear()`. `clear()` là thao tác xóa dữ liệu khỏi danh sách nền, không phải thao tác ngắt liên kết hoặc giải phóng riêng một đối tượng view.

### 6.3. Xóa một khoảng bằng subList(...).clear()

Đoạn minh họa:

```java
List<Integer> values =
        new ArrayList<>(List.of(0, 1, 2, 3, 4, 5));

values.subList(1, 4).clear();

// values = [0, 4, 5]
```

Khoảng `[1, 4)` gồm các giá trị 1, 2, 3 trong danh sách này. Lệnh xóa cả đoạn, không xóa phần tử tại biên 4. Cách này tránh phải tự lặp nhiều lần với chỉ số đang dịch chuyển.

Không nhầm với `values.clear()`, vốn xóa toàn bộ danh sách. Cũng không nhầm với việc tạo bản sao rồi xóa bản sao; khi đó cấu trúc nguồn sẽ không bị xóa.

## 7. subList lồng nhau dùng biên theo view trực tiếp

Giả sử danh sách gốc là `[A, B, C, D, E, F]`:

```java
List<String> middle = root.subList(1, 5);  // [B, C, D, E]
List<String> inner = middle.subList(1, 3); // [C, D]
```

Đây là đoạn minh họa với `root` đã được khởi tạo. Biên `1, 3` của lời gọi thứ hai áp dụng cho `middle`, không áp dụng lại cho `root`. Trước khi có thay đổi cấu trúc, `inner.get(0)` tương ứng `middle.get(1)`, rồi tương ứng `root.get(2)`.

Nếu khoảng ngoài bắt đầu ở `a` và khoảng trong bắt đầu ở `c`, biên bắt đầu hiệu dụng trong nguồn là `a + c`. Cách cộng này giúp kiểm tra phạm vi, nhưng một `inner` vẫn là view liên kết; việc lồng nhiều lần không tạo ra bản sao.

Khi cần sửa cấu trúc qua view lồng nhau, thực hiện qua đúng view sẽ dùng tiếp và quản lý các view liên quan cẩn thận. Đừng giữ tùy ý nhiều view chồng lấn rồi thêm/xóa thông qua các đường khác nhau. Ví dụ chạy sau minh họa thay đổi qua `inner` và đọc các view tổ tiên tương ứng.

## 8. Chương trình đầy đủ: sửa qua view và view lồng nhau

Lưu thành `SubListViewDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListViewDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        List<String> part = source.subList(1, 4);
        System.out.println("initial part = " + part);

        part.set(1, "c");
        System.out.println("after part.set: source = " + source);

        source.set(3, "d");
        System.out.println("after source.set: part = " + part);

        part.add(part.size(), "X");
        System.out.println("after part.add: source = " + source);
        System.out.println("after part.add: part = " + part);

        String removed = part.remove(0);
        System.out.println("removed = " + removed);
        System.out.println("after part.remove: source = " + source);
        System.out.println("after part.remove: part = " + part);

        part.clear();
        System.out.println("after part.clear: source = " + source);
        System.out.println("after part.clear: part = " + part);

        part.add("Z");
        System.out.println("after adding to empty part: source = " + source);
        System.out.println("after adding to empty part: part = " + part);

        List<Integer> numbers =
                new ArrayList<>(List.of(0, 1, 2, 3, 4, 5));
        numbers.subList(1, 4).clear();
        System.out.println("range cleared = " + numbers);

        List<String> root =
                new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));
        List<String> middle = root.subList(1, 5);
        List<String> inner = middle.subList(1, 3);
        inner.set(0, "C*");
        inner.remove(1);
        System.out.println("nested root = " + root);
        System.out.println("nested middle = " + middle);
        System.out.println("nested inner = " + inner);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListViewDemo.java
java SubListViewDemo
```

Kết quả chuẩn:

```text
initial part = [B, C, D]
after part.set: source = [A, B, c, D, E]
after source.set: part = [B, c, d]
after part.add: source = [A, B, c, d, X, E]
after part.add: part = [B, c, d, X]
removed = B
after part.remove: source = [A, c, d, X, E]
after part.remove: part = [c, d, X]
after part.clear: source = [A, E]
after part.clear: part = []
after adding to empty part: source = [A, Z, E]
after adding to empty part: part = [Z]
range cleared = [0, 4, 5]
nested root = [A, B, C*, E, F]
nested middle = [B, C*, E]
nested inner = [C*]
```

Theo dõi vùng dữ liệu ở các bước quan trọng:

| Thao tác | Ý nghĩa trong view | Hệ quả trong nguồn |
|---|---|---|
| `part.set(1, "c")` | Thay phần tử thứ hai của view | Giá trị `C` ở chỉ số 2 của nguồn thành `c` |
| `source.set(3, "d")` | View thấy phần tử tương ứng được thay | `part` trở thành `[B, c, d]` |
| `part.add(part.size(), "X")` | Chèn tại biên cuối hiện tại của view | `X` đứng trước `E` trong nguồn |
| `part.remove(0)` | Xóa `B` | `B` cũng biến mất khỏi nguồn |
| `part.clear()` | Xóa hết đoạn `[c, d, X]` | Nguồn chỉ còn `[A, E]` |
| `part.add("Z")` khi view rỗng | Thêm tại ranh giới view còn giữ | Nguồn thành `[A, Z, E]` |

Phần lồng nhau thay `C` thành `C*`, rồi xóa `D` qua `inner`. Nguồn, view giữa và view trong cùng phản ánh đoạn đã đổi. Chương trình không sửa cấu trúc trực tiếp qua `root` rồi tiếp tục giả định các view cũ vẫn hợp lệ.

## 9. Khi nguồn bị sửa cấu trúc ngoài view

### 9.1. Ranh giới sử dụng được bảo đảm

Hợp đồng `subList` không bảo đảm ngữ nghĩa của view sau khi danh sách nền bị sửa cấu trúc bằng đường khác với chính view đó. Việc thêm/xóa làm thay đổi kích thước là những ví dụ trực tiếp.

Khái niệm thay đổi cấu trúc không chỉ có nghĩa là kích thước tăng hoặc giảm. Hợp đồng còn tính đến thay đổi làm việc duyệt đang diễn ra có thể cho kết quả sai. Cần xem thao tác và triển khai cụ thể; không dựa riêng vào việc `size()` giữ nguyên để kết luận view vẫn hợp lệ.

Đoạn dưới minh họa một cách dùng sai; không phải chương trình có kết quả đầu ra ổn định để dựa vào:

```java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> part = source.subList(1, 3);

source.add("E"); // Sửa cấu trúc qua nguồn, ngoài part.

// Không tiếp tục dùng part như một view còn hợp lệ.
// Hãy bỏ view này hoặc tạo lại view theo dữ liệu và biên mới.
```

Ngay cả thêm ở cuối, bên ngoài đoạn `[1, 3)`, cũng không làm cách dùng đó trở nên an toàn theo hợp đồng. Không suy luận rằng view vẫn hợp lệ vì “không đụng tới các phần tử đang nhìn”.

Nếu xóa qua một view chị em, view đang giữ cũng có thể không còn dùng được. Ví dụ, hai view đều trỏ vào cùng nguồn; sửa cấu trúc qua view thứ nhất là thay đổi bên ngoài đường thao tác của view thứ hai.

### 9.2. ConcurrentModificationException chỉ là dấu hiệu phát hiện lỗi

Các triển khai thường dùng cơ chế kiểm tra thay đổi cấu trúc để phát hiện view đã không còn đồng bộ với nguồn. Với `ArrayList`, một thao tác tiếp theo trên view cũ có thể ném `ConcurrentModificationException`, kể cả thao tác đọc như `size()` hoặc thao tác in làm phát sinh duyệt phần tử.

Tên ngoại lệ không có nghĩa phải có hai luồng mới xảy ra lỗi. Một luồng tạo view, sửa cấu trúc nguồn trực tiếp, rồi dùng lại view cũ đã có thể gặp tình huống này.

Không xây dựng luồng điều khiển theo cách “cứ dùng, nếu có ngoại lệ thì bắt và thử lại”. Điều cần sửa là vòng đời view và đường sửa đổi dữ liệu. Việc không thấy ngoại lệ trong một phép thử không mở rộng hợp đồng sử dụng của `subList`. [Giới hạn của view trong ArrayList.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#subList(int,int)), [cách AbstractList theo dõi thay đổi của view](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#subList(int,int)).

Nếu đã có thay đổi bên ngoài, hãy tạo view mới từ trạng thái nguồn hiện tại và tính lại biên theo ý định nghiệp vụ. Đừng dùng lại biên cũ một cách máy móc: sau chèn/xóa, cùng cặp chỉ số có thể chỉ vào các phần tử khác.

## 10. Khi nào cần bản sao độc lập?

Nếu cần trả một đoạn dữ liệu để bên nhận có thể giữ lâu hoặc sửa danh sách riêng, tạo một danh sách mới từ view:

```java
List<String> copy = new ArrayList<>(source.subList(from, to));
```

Đây là biểu thức minh họa với nguồn và biên hợp lệ. `copy.add`, `copy.remove` hoặc `copy.set` sẽ thay đổi cấu trúc hoặc vị trí chứa tham chiếu của `copy`, không sửa tương ứng các vị trí chứa tham chiếu trong `source`.

Nếu cần kết quả không cho phép thêm, xóa hoặc thay phần tử qua API danh sách:

```java
List<String> snapshot = List.copyOf(source.subList(from, to));
```

`List.copyOf` không chấp nhận phần tử `null`; cần chọn cách sao chép phù hợp nếu vùng nguồn có thể chứa `null`. Tên `snapshot` ở đây nói về các phần tử/tham chiếu được chọn tại thời điểm tạo kết quả, không hứa sao chép sâu trạng thái của mọi đối tượng phần tử. [ArrayList(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)), [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

| Cách tạo kết quả | Còn phụ thuộc cấu trúc danh sách nguồn? | Bên nhận có thể sửa danh sách kết quả? | Tự sao chép sâu đối tượng phần tử? |
|---|---|---|---|
| `source.subList(from, to)` | Có | Tùy khả năng sửa đổi của nguồn | Không |
| `new ArrayList<>(source.subList(from, to))` | Không | Có | Không |
| `List.copyOf(source.subList(from, to))` | Không phản ánh việc nguồn thay danh sách phần tử về sau | Không | Không |
| `Collections.unmodifiableList(source.subList(from, to))` | Có, vẫn bọc một view | Không sửa được qua lớp bọc này | Không |

`Collections.unmodifiableList` là lớp bọc ngăn sửa qua tham chiếu trả về, không biến view thành một bản chụp độc lập. Nếu nguồn còn bị thay đổi, các hạn chế về view vẫn cần được tôn trọng. [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

### 10.1. Sao chép danh sách không đồng nghĩa sao chép phần tử

Giả sử mỗi phần tử là một đối tượng `Item` có thể đổi tên. Cả view và bản sao có thể cùng chứa tham chiếu đến một `Item`.

- Đổi tên chính `Item` đó có thể được nhìn thấy từ mọi danh sách còn giữ tham chiếu.
- Dùng `source.set(index, newItem)` thay tham chiếu trong nguồn; một bản sao đã tạo trước đó vẫn giữ tham chiếu cũ.
- Thêm phần tử vào bản sao không làm nguồn dài thêm.

Nếu yêu cầu là độc lập cả trạng thái phần tử, cần sao chép từng đối tượng theo quy tắc của kiểu dữ liệu hoặc dùng các kiểu phần tử bất biến phù hợp. `subList`, hàm dựng `ArrayList(Collection)` và `List.copyOf` không tự giải quyết yêu cầu đó.

### 10.2. Khả năng sửa đổi của nguồn vẫn chi phối view

`subList` không tự cấp thêm quyền sửa đổi:

- View của `new ArrayList<>(...)` hỗ trợ các thao tác sửa đổi thông thường.
- View của danh sách từ `List.of(...)` không cho thêm, xóa hoặc thay phần tử.
- View của danh sách từ `Arrays.asList(array)` có thể thay phần tử bằng `set`, nhưng không cho thay đổi kích thước bằng thêm/xóa.
- Khả năng chứa `null`, ràng buộc kiểu phần tử và các điều kiện khác còn phụ thuộc danh sách nền.

Nếu muốn một bản sao có thể sửa đổi từ nguồn không sửa được, `new ArrayList<>(view)` tạo cấu trúc mới để sửa riêng. [Arrays.asList và danh sách kích thước cố định](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 11. Chương trình đầy đủ: bản sao và phần tử dùng chung

Lưu thành `SubListCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListCopyDemo {
    private static final class Item {
        private String name;

        private Item(String name) {
            this.name = name;
        }

        private void rename(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<Item> source = new ArrayList<>(List.of(
                new Item("A"), new Item("B"), new Item("C")));
        List<Item> view = source.subList(1, 3);
        List<Item> copy = new ArrayList<>(view);
        List<Item> snapshot = List.copyOf(view);

        source.get(1).rename("B*");
        System.out.println("after item rename: view = " + view);
        System.out.println("after item rename: copy = " + copy);
        System.out.println("after item rename: snapshot = " + snapshot);

        source.set(1, new Item("NEW"));
        System.out.println("after source.set: view = " + view);
        System.out.println("after source.set: copy = " + copy);
        System.out.println("after source.set: snapshot = " + snapshot);

        copy.add(new Item("COPY"));
        System.out.println("after copy.add: source = " + source);
        System.out.println("after copy.add: copy = " + copy);

        try {
            snapshot.add(new Item("X"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot.add -> UnsupportedOperationException");
        }

        source.add(new Item("D"));
        System.out.println("after source.add: source = " + source);
        System.out.println("after source.add: copy = " + copy);
        System.out.println("after source.add: snapshot = " + snapshot);
        // Không dùng view sau thay đổi cấu trúc qua source.
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SubListCopyDemo.java
java SubListCopyDemo
```

Kết quả chuẩn:

```text
after item rename: view = [B*, C]
after item rename: copy = [B*, C]
after item rename: snapshot = [B*, C]
after source.set: view = [NEW, C]
after source.set: copy = [B*, C]
after source.set: snapshot = [B*, C]
after copy.add: source = [A, NEW, C]
after copy.add: copy = [B*, C, COPY]
snapshot.add -> UnsupportedOperationException
after source.add: source = [A, NEW, C, D]
after source.add: copy = [B*, C, COPY]
after source.add: snapshot = [B*, C]
```

Đọc sự khác biệt giữa sửa đối tượng và thay tham chiếu:

1. `rename("B*")` sửa một đối tượng `Item` đang được ba danh sách cùng tham chiếu; cả ba đều in tên mới.
2. `source.set(1, new Item("NEW"))` thay phần tử ở nguồn. View nhìn thấy `NEW`, còn `copy` và `snapshot` vẫn giữ đối tượng cũ tên `B*`.
3. `copy.add(...)` chỉ làm bản sao dài thêm.
4. `snapshot.add(...)` gây `UnsupportedOperationException` vì `List.copyOf` tạo danh sách không sửa đổi được.
5. `source.add(...)` ở cuối sửa cấu trúc nguồn. Chương trình vẫn dùng được các bản sao nhưng chủ động kết thúc việc sử dụng view cũ.

Một danh sách không sửa đổi được vẫn có thể chứa phần tử có trạng thái thay đổi được. Do đó, “không được gọi `add`” và “mọi giá trị quan sát được luôn bất biến” là hai yêu cầu khác nhau.

## 12. Chọn phạm vi và vòng đời view trong thực tế

`subList` hữu ích khi xử lý một đoạn ngay trong phạm vi có kiểm soát: đọc một khoảng, tìm kiếm trong đoạn, sắp xếp riêng đoạn trên nguồn cho phép thay phần tử, hoặc xóa đoạn bằng `clear`. Trước khi truyền view cho một hàm khác, phải biết hàm đó chỉ đọc hay có thể sửa danh sách.

Nếu một hàm nhận `List<T>` rồi gọi `clear()`, truyền `source.subList(from, to)` cho hàm đó đồng nghĩa cho phép hàm xóa đoạn tương ứng trong nguồn, khi nguồn hỗ trợ thao tác này. Kiểu tham số `List` không tự diễn đạt quyền sở hữu dữ liệu.

Với kết quả trả về từ dịch vụ, trang dữ liệu giữ lâu, bộ nhớ đệm hoặc xử lý trì hoãn, thường cần quyết định rõ có giữ quan hệ với nguồn hay trả cấu trúc độc lập. Không chỉ nhìn vào vài phần tử đang in ra giống nhau để coi view và bản sao là tương đương.

Các triển khai view như view của `ArrayList` còn giữ liên hệ với danh sách nền. Một view nhỏ được giữ lâu có thể làm cấu trúc nguồn lớn còn được giữ trong bộ nhớ. Đây là hệ quả của việc giữ tham chiếu, không phải bằng chứng rằng mọi `subList` đều luôn rò rỉ bộ nhớ. Nếu chỉ cần giữ lâu một đoạn nhỏ và không cần liên hệ với nguồn, bản sao riêng thường diễn đạt đúng ý định hơn.

Về chi phí, không suy ra rằng mọi cách tạo view, truy cập hay sửa view đều có cùng độ phức tạp trên mọi `List`. Bản sao cần đi qua các phần tử được chọn và có nơi lưu riêng; view tránh việc tự sao chép toàn bộ phần tử chỉ để tạo một đoạn nhìn, nhưng vẫn dùng cơ chế truy cập và sửa đổi của triển khai nền.

## 13. Các lỗi cần nhận ra khi đọc mã

| Cách hiểu hoặc cách viết | Vấn đề | Cách kiểm tra |
|---|---|---|
| `subList(1, 4)` lấy cả phần tử chỉ số 4 | Nhầm biên cuối có bao gồm | Liệt kê chỉ số 1, 2, 3; độ dài là 3 |
| `subList(from, count)` để lấy `count` phần tử | Đối số thứ hai bị hiểu sai | Tính biên cuối từ `from + count` với kiểm tra thích hợp |
| Dùng `size() - 1` làm biên cuối để lấy hết | Bỏ mất phần tử cuối | Dùng `size()` làm biên dừng |
| Dùng `part.get(fromIndex)` để đọc phần tử đầu | Trộn chỉ số nguồn và view | Phần tử đầu của view có chỉ số 0 |
| Cho rằng `subList(i, i)` là lỗi | Không nhận ra khoảng rỗng | Kiểm tra `i` nằm trong `[0, size()]` |
| Gọi `part.clear()` để “bỏ view” | Xóa dữ liệu thật trong nguồn | Chỉ dùng `clear` khi muốn xóa đoạn |
| Thêm vào nguồn rồi tiếp tục dùng view cũ | Vượt giới hạn hợp đồng view | Quản lý đường sửa cấu trúc, hoặc dùng bản sao |
| Bắt `ConcurrentModificationException` rồi tiếp tục dùng view | Không sửa nguyên nhân view mất hiệu lực | Bỏ view cũ và tính lại theo trạng thái hiện tại |
| Bọc bằng `unmodifiableList` rồi cho rằng đã sao chép | Lớp bọc vẫn liên kết với view nền | Chọn `new ArrayList` hoặc `List.copyOf` khi cần tách cấu trúc |
| Cho rằng bản sao danh sách tạo các phần tử mới | Nhầm sao chép cấu trúc với sao chép sâu | Kiểm tra phần tử có thay đổi trạng thái được và còn dùng chung tham chiếu không |

## 14. Tự kiểm tra bằng dự đoán

Mỗi câu độc lập, dùng danh sách mới:

```java
List<String> data =
        new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));
```

Đây là đoạn khởi tạo cho bài tập trong một phương thức.

1. `data.subList(2, 5)` có những phần tử nào, kích thước bao nhiêu?
2. Muốn lấy đúng ba phần tử bắt đầu ở chỉ số 1, hai biên là gì?
3. Muốn lấy hai phần tử cuối, hai biên là gì?
4. `data.subList(data.size(), data.size())` có hợp lệ không?
5. Sau `List<String> part = data.subList(1, 4);`, `part.get(1)` là gì?
6. Nếu gọi `part.clear()` ngay sau bước khởi tạo ở câu 5, `data` còn gì?
7. Nếu tạo `List<String> copy = new ArrayList<>(data.subList(1, 4));` rồi `copy.clear()`, `data` có bị xóa đoạn không?
8. Nếu giữ một view rồi gọi `data.add("G")`, có thể tiếp tục dựa vào view cũ theo hợp đồng không?

Đáp án:

1. `[C, D, E]`, kích thước 3; chỉ số 5 chứa `F` bị loại.
2. `[1, 4)`; biên cuối bằng 1 + 3.
3. `[data.size() - 2, data.size())`, tức `[4, 6)`. Công thức này cần nguồn có ít nhất hai phần tử.
4. Hợp lệ, kết quả rỗng.
5. `C`; chỉ số 1 của view tương ứng chỉ số 2 của nguồn.
6. `[A, E, F]`; các phần tử `B, C, D` bị xóa qua view.
7. Không; `copy` có cấu trúc riêng nên nguồn vẫn `[A, B, C, D, E, F]`.
8. Không; nguồn đã bị sửa cấu trúc ngoài view. Cần tạo lại view hợp lệ hoặc dùng bản sao theo yêu cầu.

Khi dùng `subList`, hãy xác định đồng thời ba điều: khoảng `[fromIndex, toIndex)`, hệ chỉ số bắt đầu lại từ 0 của kết quả, và việc kết quả còn là view của nguồn. Ba điều này quyết định đúng phần tử nào được chọn, thao tác nào sửa dữ liệu gốc và kết quả có thể được giữ lại trong bao lâu.
