# Gán lại biến enhanced `for` không thay phần tử mảng — Java 17+

## 1. Quy tắc cốt lõi

Với vòng lặp **enhanced `for`** (còn gọi là *for-each*), Java lấy lần lượt giá trị từ mảng rồi **gán giá trị đó cho biến lặp cục bộ**. Gán lại biến lặp **không ghi ngược** vào phần tử mảng đang duyệt.

~~~java
import java.util.Arrays;

public class FirstExample {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};

        for (int number : numbers) {
            number = number * 10;
        }

        System.out.println(Arrays.toString(numbers));
    }
}
~~~

**Exact expected stdout:**

~~~text
[1, 2, 3]
~~~

Mặc dù mỗi lần lặp `number` nhận giá trị từ mảng, biểu thức `number = number * 10` **chỉ đổi biến cục bộ `number`**, không thay đổi `numbers[0]`, `numbers[1]` hoặc `numbers[2]`.

**Muốn thay chính các phần tử mảng**, dùng vị trí chỉ số để gán:

~~~java
for (int i = 0; i < numbers.length; i++) {
    numbers[i] = numbers[i] * 10;
}
System.out.println(Arrays.toString(numbers));
~~~

**Exact expected stdout (tiếp nối ví dụ trên):**

~~~text
[10, 20, 30]
~~~

Đây là điểm phân biệt quan trọng nhất của bài học: **biến trong `for (T value : array)` không phải một “ô tham chiếu” cho phép thay trực tiếp `array[index]` bằng phép gán vào `value`**.

## 2. Vì sao gán lại biến lặp không ghi ngược mảng?

Với một **mảng**, Java xử lý enhanced for gần tương đương về ý nghĩa với dạng dùng chỉ số ẩn:

~~~java
int[] data = {4, 5};

// Ý nghĩa tương đương về việc lấy giá trị từ mảng:
for (int index = 0; index < data.length; index++) {
    int element = data[index];
    element = 100; // Chỉ đổi element.
}
~~~

Ở mỗi lượt:

1. Java lấy giá trị `data[index]`.
2. Gán giá trị đó cho biến cục bộ `element`.
3. Thực thi thân vòng lặp.
4. Khi tới lượt kế, lấy một phần tử tiếp theo.

**Không có bước tự động kiểu `data[index] = element;` sau thân vòng lặp**. Phép gán vào biến và phép gán vào phần tử mảng là hai thao tác khác nhau.

Một cách dễ nhớ:

~~~text
data[0] ----giá trị----> element
  4                          4

element = 100;

data[0]                      element
  4                             100
~~~

Sơ đồ này dùng cho **giá trị nguyên thủy**. Với mảng đối tượng, giá trị được sao chép vào biến cục bộ là **giá trị tham chiếu**; cần phân biệt tiếp ở phần sau.

## 3. Kiểu nguyên thủy: tăng, giảm hay gán lại đều không sửa phần tử

~~~java
int[] values = {5, 6, 7};

for (int value : values) {
    value++;
    value *= 2;
    value = -1;
}

System.out.println(Arrays.toString(values));
~~~

**Exact expected stdout:**

~~~text
[5, 6, 7]
~~~

Các phép toán `++`, `--`, `+=`, `*=` và `=` đều chỉ thay **biến lặp**:

- `value++` không tương đương `values[i]++`.
- `value += 10` không tương đương `values[i] += 10`.
- `value = -1` không tương đương `values[i] = -1`.

**Cách đúng khi cần thay cả mảng:**

~~~java
for (int i = 0; i < values.length; i++) {
    values[i]++;
}
System.out.println(Arrays.toString(values));
~~~

**Exact expected stdout (tiếp nối):**

~~~text
[6, 7, 8]
~~~

## 4. Mảng `String`: gán lại biến cũng không thay phần tử

`String` là kiểu tham chiếu nhưng **bất biến** (*immutable*): method như `toUpperCase` trả một String, không sửa nội dung String gốc.

~~~java
import java.util.Locale;

String[] names = {"an", "binh"};
for (String name : names) {
    name = name.toUpperCase(Locale.ROOT);
}

System.out.println(Arrays.toString(names));
~~~

**Exact expected stdout:**

~~~text
[an, binh]
~~~

`name = name.toUpperCase(...)` chỉ cho biến `name` tham chiếu một String khác, còn các phần tử của `names` giữ nguyên.

**Cách đúng khi muốn thay String trong mảng:**

~~~java
for (int i = 0; i < names.length; i++) {
    names[i] = names[i].toUpperCase(Locale.ROOT);
}
System.out.println(Arrays.toString(names));
~~~

**Exact expected stdout (tiếp nối):**

~~~text
[AN, BINH]
~~~

Đừng nhầm giữa **tạo giá trị mới rồi gán cho biến lặp** và **gán giá trị mới vào ô mảng**.

## 5. Giới hạn: đối tượng, mảng con và List

**Gán lại phần tử** và **sửa đối tượng mà phần tử trỏ tới** là hai thao tác khác nhau. Với `StringBuilder[] builders`, `builder.append("!")` làm thay đổi nội dung đối tượng chung; `builder = new StringBuilder("NEW")` chỉ đổi biến local, còn `builders[i] = ...` mới thay tham chiếu ở vị trí mảng.

Với `int[][] matrix`, biến `row` trong `for (int[] row : matrix)` là bản sao tham chiếu tới mảng con. `row[0]++` sửa dữ liệu mảng con; `row = new int[]{99}` không thay `matrix[i]`. Khi cần thay cả hàng, dùng chỉ số của mảng ngoài.

Enhanced `for` trên `List<Integer>` cũng không tự gọi `set`: `number++` chỉ gán lại biến cục bộ (unboxing/boxing). Với List sửa được, dùng `set(i, value)` hoặc `replaceAll`. `List.of(...)` không hỗ trợ các thao tác cập nhật phần tử. Các cơ chế aliasing và `ListIterator.set` được bàn sâu hơn trong bài riêng về tham chiếu đối tượng.

## 6. Chương trình Java 17 độc lập và có đầu ra chính xác

Tạo đúng file **`EnhancedForAssignmentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class EnhancedForAssignmentDemo {
    private EnhancedForAssignmentDemo() {}

    static void primitiveArray() {
        int[] scores = {1, 2, 3};

        for (int score : scores) {
            score *= 10;
        }
        System.out.println("primitive after reassignment="
                + Arrays.toString(scores));

        for (int i = 0; i < scores.length; i++) {
            scores[i] *= 10;
        }
        System.out.println("primitive after indexed update="
                + Arrays.toString(scores));
    }

    static void immutableStringArray() {
        String[] names = {"an", "binh"};

        for (String name : names) {
            name = name.toUpperCase(Locale.ROOT);
        }
        System.out.println("string after reassignment="
                + Arrays.toString(names));

        for (int i = 0; i < names.length; i++) {
            names[i] = names[i].toUpperCase(Locale.ROOT);
        }
        System.out.println("string after indexed update="
                + Arrays.toString(names));
    }

    static void mutableObjectArray() {
        StringBuilder[] builders = {
            new StringBuilder("A"),
            new StringBuilder("B")
        };

        for (StringBuilder builder : builders) {
            builder.append("!");
            builder = new StringBuilder("OTHER");
        }
        System.out.println("objects after mutation="
                + Arrays.toString(builders));

        for (int i = 0; i < builders.length; i++) {
            builders[i] = new StringBuilder("NEW" + i);
        }
        System.out.println("objects after indexed replacement="
                + Arrays.toString(builders));
    }

    static void twoDimensionalArray() {
        int[][] matrix = {
            {1, 2},
            {3, 4}
        };

        for (int[] row : matrix) {
            row[0] += 10;
            row = new int[]{99, 99};
        }
        System.out.println("matrix after row alias mutation="
                + Arrays.deepToString(matrix));

        for (int i = 0; i < matrix.length; i++) {
            matrix[i] = new int[]{20 + i};
        }
        System.out.println("matrix after row replacement="
                + Arrays.deepToString(matrix));
    }

    static void boxedList() {
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

        for (Integer number : numbers) {
            number++;
        }
        System.out.println("list after variable update=" + numbers);

        for (int i = 0; i < numbers.size(); i++) {
            numbers.set(i, numbers.get(i) + 1);
        }
        System.out.println("list after set=" + numbers);
    }

    static void finalLocalReference() {
        StringBuilder[] items = {new StringBuilder("A")};
        for (final StringBuilder item : items) {
            item.append("!");
        }
        System.out.println("final reference object="
                + Arrays.toString(items));
    }

    public static void main(String[] args) {
        primitiveArray();
        immutableStringArray();
        mutableObjectArray();
        twoDimensionalArray();
        boxedList();
        finalLocalReference();
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; mở terminal tại thư mục chứa file. Code chỉ dùng thư viện tiêu chuẩn JDK, không có tính năng preview.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 EnhancedForAssignmentDemo.java
java -cp . EnhancedForAssignmentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\EnhancedForAssignmentDemo.java
java -cp . EnhancedForAssignmentDemo
~~~

### Exact expected stdout

~~~text
primitive after reassignment=[1, 2, 3]
primitive after indexed update=[10, 20, 30]
string after reassignment=[an, binh]
string after indexed update=[AN, BINH]
objects after mutation=[A!, B!]
objects after indexed replacement=[NEW0, NEW1]
matrix after row alias mutation=[[11, 2], [13, 4]]
matrix after row replacement=[[20], [21]]
list after variable update=[1, 2, 3]
list after set=[2, 3, 4]
final reference object=[A!]
~~~

**Đối chiếu:**

1. `score *= 10` không sửa `scores`; `scores[i] *= 10` sửa trực tiếp phần tử.
2. `name = name.toUpperCase(...)` không thay String trong mảng; `names[i] = ...` có thay.
3. `builder.append("!")` đổi nội dung object chung; `builder = new ...` không thay object được mảng tham chiếu.
4. `row[0] += 10` sửa mảng con; `row = new int[] {...}` không thay mảng con trong `matrix`.
5. `Integer number++` chỉ cập nhật biến cục bộ; `numbers.set(...)` mới thay phần tử List.
6. `final` ngăn biến tham chiếu đổi sang object khác nhưng không làm object mutable trở thành immutable.

## 7. Bài tập có đáp án

### Bài A — dự đoán mảng sau vòng lặp

~~~java
int[] a = {2, 4};
for (int x : a) {
    x = 0;
}
System.out.println(Arrays.toString(a));
~~~

**Đáp án:**

~~~text
[2, 4]
~~~

Phép gán chỉ tác động lên `x` của mỗi lượt.

### Bài B — sửa đúng cách

Yêu cầu nhân mọi phần tử `a` với 3.

~~~java
for (int i = 0; i < a.length; i++) {
    a[i] *= 3;
}
~~~

Với mảng ban đầu `{2, 4}`, kết quả `[6, 12]`.

### Bài C — object mutable

~~~java
StringBuilder[] a = {new StringBuilder("X")};
for (StringBuilder x : a) {
    x.append("Y");
    x = new StringBuilder("Z");
}
System.out.println(Arrays.toString(a));
~~~

**Đáp án:**

~~~text
[XY]
~~~

`append` đổi object đang nằm trong mảng; gán lại `x` không thay phần tử `a[0]`.

### Bài D — mảng hai chiều

~~~java
int[][] m = {{1, 2}};
for (int[] row : m) {
    row[1] = 9;
    row = new int[]{0};
}
System.out.println(Arrays.deepToString(m));
~~~

**Đáp án:**

~~~text
[[1, 9]]
~~~

`row[1] = 9` sửa phần tử của mảng con; gán lại `row` không thay phần tử mảng ngoài.

### Bài E — biến `final`

~~~java
StringBuilder[] items = {new StringBuilder("A")};
for (final StringBuilder item : items) {
    item.append("B");
    // item = new StringBuilder("C"); // Không biên dịch.
}
~~~

**Đáp án:** object đầu tiên thành `"AB"`; phép gán lại `item` bị cấm vì `final`, nhưng `append` vẫn hợp lệ.

## 8. Checklist và kết luận

- [ ] Hiểu enhanced `for` duyệt từng **giá trị phần tử**, không cung cấp ô mảng để gán ngược.
- [ ] Biết gán `value = ...`, `value++`, `value += ...` không sửa mảng primitive.
- [ ] Biết `String` immutable và gán lại biến String không thay phần tử trong mảng.
- [ ] Phân biệt **gán lại biến tham chiếu** với **thay trạng thái object mutable** được tham chiếu.
- [ ] Biết `row[0]` có thể sửa mảng con, còn `row = new int[]` không thay hàng của mảng ngoài.
- [ ] Biết gán `numbers.set(i, ...)` với List sửa được mới thay phần tử List.
- [ ] Biết `final` ngăn gán lại biến, không làm nội dung object thành bất biến.
- [ ] Chọn for theo chỉ số khi cần thay thế phần tử, enhanced for khi duyệt/đọc dữ liệu.
- [ ] Không nhầm thay đổi cấu trúc collection với gán lại biến lặp.
- [ ] Chạy `EnhancedForAssignmentDemo.java` trên Java 17+, đối chiếu exact stdout.

**Kết luận:** Enhanced `for` trao cho bạn **một biến cục bộ chứa giá trị phần tử ở lượt hiện tại**. Vì Java sao chép **giá trị** (kể cả giá trị tham chiếu), phép gán lại biến ấy **không ghi ngược vào mảng hay List**. Muốn thay phần tử, hãy cập nhật đúng vị trí bằng chỉ số hoặc API collection; nếu biến đang tham chiếu object mutable, có thể thay **trạng thái object** bằng method, nhưng đó là hành động khác với thay phần tử.
