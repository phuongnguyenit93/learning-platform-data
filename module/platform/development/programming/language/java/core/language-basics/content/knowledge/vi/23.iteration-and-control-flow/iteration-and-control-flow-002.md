# Biến vòng lặp là bản sao giá trị phần tử — Java 17+

Trong **enhanced `for`** (còn gọi là *for-each*), biến vòng lặp nhận **giá trị của từng phần tử**, chứ không phải một ô lưu trữ có thể gán thay thế trong mảng hoặc danh sách. Vì Java truyền và gán **theo giá trị**, việc **gán lại biến vòng lặp** không đồng nghĩa với việc sửa phần tử gốc.

~~~java
int[] numbers = {1, 2, 3};

for (int number : numbers) {
    number *= 10;
}
// numbers vẫn là {1, 2, 3}.
~~~

Với **kiểu nguyên thủy**, biến nhận bản sao của số. Với **kiểu tham chiếu**, biến nhận **bản sao của tham chiếu**: nó có thể trỏ tới *cùng đối tượng*, nhưng bản thân biến không phải vị trí chứa phần tử trong collection. Phân biệt này quyết định phép thay đổi nào được phản ánh ra bên ngoài.

## 1. Enhanced `for` đọc phần tử như thế nào?

~~~java
int[] a = {10, 20};
for (int value : a) {
    System.out.println(value);
}
~~~

Về ý nghĩa liên quan đến biến phần tử, có thể hình dung gần như:

~~~java
for (int i = 0; i < a.length; i++) {
    int value = a[i]; // Nhận một bản sao của giá trị phần tử.
    System.out.println(value);
}
~~~

Với `Iterable` như `List`, enhanced `for` dùng `Iterator` để lấy từng giá trị, không phải tự nhiên có một biến đại diện trực tiếp cho ô lưu trữ. Dù giá trị lấy qua mảng hay iterator, **gán lại biến phần tử không ghi ngược trở về nguồn**.

| Loại phần tử | Biến vòng lặp giữ gì? | Gán lại biến có thay phần tử gốc? |
| --- | --- | --- |
| `int`, `double`, `boolean`... | Bản sao giá trị nguyên thủy | **Không** |
| `String`, `Integer` | Bản sao tham chiếu đối tượng bất biến | **Không** |
| Đối tượng có thể thay đổi, như `Box` | Bản sao tham chiếu đến cùng đối tượng | **Không**, nhưng có thể sửa trạng thái đối tượng |
| Mảng con `int[]` của `int[][]` | Bản sao tham chiếu mảng con | **Không**, nhưng có thể sửa phần tử trong mảng con |

Từ “bản sao” ở đây là **sao chép giá trị biến** (đối với đối tượng là địa chỉ tham chiếu theo mô hình ngữ nghĩa), **không** phải tự động tạo *deep copy* của đối tượng.

## 2. Chương trình Java 17+ độc lập, chạy bằng CLI

Tạo tệp UTF-8 tên **`EnhancedForCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class EnhancedForCopyDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    public static void main(String[] args) {
        System.out.println("== primitive ==");
        int[] numbers = {1, 2, 3};

        for (int value : numbers) {
            value *= 10;
        }
        System.out.println("afterForEach=" + Arrays.toString(numbers));

        for (int i = 0; i < numbers.length; i++) {
            numbers[i] *= 10;
        }
        System.out.println("afterIndexed=" + Arrays.toString(numbers));

        System.out.println("== immutable references ==");
        String[] words = {"cat", "dog"};
        for (String word : words) {
            word = word.toUpperCase(Locale.ROOT);
        }
        System.out.println("afterRebind=" + Arrays.toString(words));

        for (int i = 0; i < words.length; i++) {
            words[i] = words[i].toUpperCase(Locale.ROOT);
        }
        System.out.println("afterReplace=" + Arrays.toString(words));

        System.out.println("== mutable objects ==");
        Box[] boxes = {new Box(1), new Box(2)};
        for (Box box : boxes) {
            box.value += 5;
        }
        System.out.println("afterMutation=" + Arrays.toString(boxes));

        for (Box box : boxes) {
            box = new Box(999);
        }
        System.out.println("afterObjectRebind=" + Arrays.toString(boxes));

        for (int i = 0; i < boxes.length; i++) {
            boxes[i] = new Box(i + 10);
        }
        System.out.println("afterObjectReplace=" + Arrays.toString(boxes));

        System.out.println("== list of wrappers ==");
        List<Integer> ids = new ArrayList<>(List.of(1, 2, 3));
        for (Integer id : ids) {
            id = id + 10;
        }
        System.out.println("listRebind=" + ids);
        ids.replaceAll(n -> n + 10);
        System.out.println("listReplaceAll=" + ids);

        System.out.println("== nested arrays ==");
        int[][] grid = {{1, 2}, {3, 4}};
        for (int[] row : grid) {
            row[0] *= 10;
        }
        System.out.println("gridMutation=" + Arrays.deepToString(grid));

        for (int[] row : grid) {
            row = new int[] {0, 0};
        }
        System.out.println("gridRebind=" + Arrays.deepToString(grid));

        for (int i = 0; i < grid.length; i++) {
            grid[i] = new int[] {-1};
        }
        System.out.println("gridReplace=" + Arrays.deepToString(grid));
        System.out.println("done");
    }
}
~~~

Dùng **JDK 17 trở lên**, mở PowerShell hoặc Bash tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 EnhancedForCopyDemo.java
java EnhancedForCopyDemo
~~~

**Exact expected stdout** của riêng lệnh `java EnhancedForCopyDemo`:

~~~text
== primitive ==
afterForEach=[1, 2, 3]
afterIndexed=[10, 20, 30]
== immutable references ==
afterRebind=[cat, dog]
afterReplace=[CAT, DOG]
== mutable objects ==
afterMutation=[6, 7]
afterObjectRebind=[6, 7]
afterObjectReplace=[10, 11]
== list of wrappers ==
listRebind=[1, 2, 3]
listReplaceAll=[11, 12, 13]
== nested arrays ==
gridMutation=[[10, 2], [30, 4]]
gridRebind=[[10, 2], [30, 4]]
gridReplace=[[-1], [-1]]
done
~~~

`java -version` và `javac -version` có đầu ra tùy JDK được cài nên không thuộc phần stdout cố định. Chương trình chỉ dùng Java chuẩn và không yêu cầu thư viện ngoài.

## 3. Với kiểu nguyên thủy: chỉ sửa biến cục bộ

~~~java
int[] scores = {10, 20};
for (int score : scores) {
    score += 5;
}
// scores vẫn là {10, 20}.
~~~

Mỗi lượt, `score` nhận **một bản sao số nguyên**. Câu `score += 5` chỉ cập nhật biến cục bộ trong lượt đó. Nếu muốn tăng trực tiếp các phần tử mảng:

~~~java
for (int i = 0; i < scores.length; i++) {
    scores[i] += 5;
}
// scores thành {15, 25}.
~~~

Đây là khác biệt giữa **sửa biến vòng lặp** và **sửa ô mảng bằng chỉ số**. Enhanced `for` đặc biệt thích hợp cho tác vụ **đọc, tính tổng, in hoặc kiểm tra** từng phần tử.

## 4. Với tham chiếu: gán lại khác với thay đổi trạng thái đối tượng

Xét lớp có thể thay đổi:

~~~java
class Box {
    int value;
    Box(int value) { this.value = value; }
}
~~~

Nếu một mảng chứa `Box`:

~~~java
Box[] boxes = {new Box(1), new Box(2)};

for (Box box : boxes) {
    box.value += 5; // Sửa trạng thái đối tượng đang được tham chiếu.
}
// boxes[0].value == 6; boxes[1].value == 7.
~~~

Biến `box` là **bản sao tham chiếu**, nhưng vẫn trỏ tới **cùng một đối tượng `Box`** mà mảng đang giữ. Vì thế `box.value += 5` thay đổi đối tượng và có thể quan sát được thông qua mảng.

Ngược lại:

~~~java
for (Box box : boxes) {
    box = new Box(999); // Chỉ thay đổi biến box trong lượt này.
}
// Mảng vẫn giữ hai đối tượng Box ban đầu.
~~~

`box = ...` không thể thay `boxes[0]` hay `boxes[1]`: phép gán chỉ đổi tham chiếu nằm trong biến cục bộ `box`. Muốn **thay thế đối tượng tại vị trí mảng**, sử dụng `boxes[i] = new Box(...)` với chỉ số.

| Thao tác | Thay ô lưu trữ mảng/list? | Có thể thay trạng thái đối tượng gốc? |
| --- | --- | --- |
| `box = anotherBox;` | Không | Không, chỉ đổi biến cục bộ |
| `box.value = 7;` | Không | Có |
| `boxes[i] = anotherBox;` | Có | Không tự thay đổi đối tượng cũ |
| `list.set(i, anotherBox);` | Có | Không tự thay đổi đối tượng cũ |

**Lưu ý:** Không phải mọi tham chiếu đều trỏ tới đối tượng cho phép sửa. `String` và các wrapper như `Integer` là bất biến; biểu thức tạo “giá trị mới” thường chỉ tạo/trả về một đối tượng khác rồi phải **gán vào phần tử gốc** nếu muốn lưu lại.

## 5. `List` và mảng nhiều chiều

Enhanced `for` duyệt được **mảng** và các đối tượng **`Iterable`** như `List`:

~~~java
List<Integer> ids = new ArrayList<>(List.of(1, 2));

for (Integer id : ids) {
    id++; // Unbox, tăng rồi boxing trở lại vào biến id.
}
// ids vẫn là [1, 2].

ids.replaceAll(n -> n + 1);
// ids thành [2, 3].
~~~

Với danh sách cho phép thay phần tử, có thể dùng `List.set(index, value)` hoặc `replaceAll` tùy ý định. **Đừng xóa/thêm trực tiếp phần tử vào `ArrayList` bằng `list.add/remove` trong lúc đang dùng enhanced `for` duyệt chính danh sách đó**: iterator fail-fast có thể ném `ConcurrentModificationException`. Khi cần xóa an toàn theo điều kiện, dùng `removeIf` hoặc một `Iterator` với `remove()` đúng hợp đồng.

Mảng hai chiều cũng là **mảng chứa các tham chiếu mảng con**:

~~~java
int[][] grid = {{1, 2}, {3, 4}};

for (int[] row : grid) {
    row[0] *= 10; // Sửa phần tử trong mảng con.
}
// grid = {{10, 2}, {30, 4}}.

for (int[] row : grid) {
    row = new int[] {0, 0}; // Không thay tham chiếu trong grid.
}
// grid vẫn = {{10, 2}, {30, 4}}.
~~~

Nếu muốn thay **cả mảng con**, phải cập nhật `grid[index]`. Việc chỉnh sửa phần tử mảng con khác hoàn toàn việc gán lại biến `row`.

## 6. Những lưu ý về phạm vi biến, `final` và `null`

- Biến khai báo trong `for (Type item : items)` là biến của vòng lặp; **không dùng được ngoài phạm vi vòng**.
- Có thể viết `for (final Box box : boxes)` để **cấm gán lại biến tham chiếu `box`**. Tuy nhiên `final` **không khiến đối tượng `Box` bất biến**: `box.value++` vẫn có thể hợp lệ.
- Phần tử tham chiếu có thể là `null`. Lúc đó biến vòng lặp nhận null; gọi `item.method()` sẽ gây `NullPointerException` nếu không kiểm tra.
- Nếu chính mảng hoặc nguồn `Iterable` là null, enhanced `for` không thể duyệt và sẽ gây `NullPointerException`.
- Nếu chỉ cần **đọc từng giá trị**, không cần vị trí, enhanced `for` thường gọn hơn một vòng đếm. Nếu cần **ghi đè chính phần tử**, nên dùng chỉ số hoặc API cập nhật thích hợp.

## 7. Các lỗi thường gặp

| Hiểu nhầm | Cách đúng |
| --- | --- |
| “`for (int x : a) { x++; }` tăng từng phần tử `a`.” | Chỉ tăng **bản sao** trong biến `x` |
| “Biến vòng lặp là bí danh trực tiếp của ô mảng.” | Biến chỉ nhận **giá trị** của phần tử |
| “Tham chiếu được sao chép nghĩa là đối tượng được deep copy.” | Không; hai tham chiếu có thể trỏ cùng đối tượng |
| “`box.value++` cũng không thể thay gì bên ngoài.” | Có thể sửa trạng thái đối tượng gốc |
| “`box = new Box(...)` thay phần tử gốc.” | Không; phải ghi đè vị trí mảng hoặc list |
| “`final Box box` khiến toàn bộ Box bất biến.” | Chỉ không cho gán lại biến `box` |
| “Đổi `String s` bằng `s.toUpperCase()` sẽ cập nhật list.” | Không nếu không gán trở lại phần tử |
| “Enhanced `for` phù hợp nhất để thay mọi phần tử tại chỗ.” | Thường dùng chỉ số, `set` hoặc `replaceAll` để thay |

## 8. Bài tập tự kiểm tra

1. `int[] a = {1,2}; for (int x : a) x += 10;` — mảng có đổi không?  
   *Đáp án:* Không, vẫn `{1,2}`.
2. `String[] a = {"hi"}; for (String s : a) s = "bye";` — phần tử đầu là gì?  
   *Đáp án:* `"hi"`.
3. `Box[] a = {new Box(3)}; for (Box b : a) b.value++;` — giá trị trong `a[0]`?  
   *Đáp án:* 4, vì sửa cùng đối tượng.
4. Nếu thay `b.value++` bằng `b = new Box(9)`, phần tử gốc có bị thay không?  
   *Đáp án:* Không.
5. Với `int[][] grid`, `row[0]++` và `row = new int[1]` khác nhau thế nào?  
   *Đáp án:* Phép đầu sửa mảng con gốc; phép sau chỉ gán lại biến `row`.
6. Muốn thay toàn bộ `Integer` trong `List` theo công thức, dùng gì?  
   *Gợi ý:* `list.replaceAll(...)` hoặc vòng theo chỉ số với `list.set(i, ...)`.

## Checklist

- [ ] Hiểu enhanced `for` gán **giá trị phần tử** vào biến trong mỗi lượt.
- [ ] Phân biệt sao chép **giá trị nguyên thủy** và sao chép **tham chiếu**.
- [ ] Biết **gán lại biến vòng lặp không ghi ngược vào collection**.
- [ ] Nhận diện việc **sửa trạng thái đối tượng** vẫn có thể được phản ánh qua phần tử gốc.
- [ ] Dùng `array[i] = ...`, `list.set` hoặc `replaceAll` khi cần thay thế phần tử.
- [ ] Biết giới hạn phạm vi biến, `final` và cách xử lý phần tử `null`.

**Kết luận:** Enhanced `for` là cách diễn đạt tốt khi **đọc từng phần tử**, nhưng biến vòng lặp chỉ nhận **một bản sao giá trị**. Với đối tượng, bản sao đó là **tham chiếu tới cùng đối tượng**, nên sửa thuộc tính có thể tác động đến đối tượng gốc, còn **gán lại biến tham chiếu** không thay vị trí phần tử trong mảng hoặc danh sách.
