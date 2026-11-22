# Thay đổi nội dung mảng khác với gán lại tham số mảng trong Java

> **Java core — language-basics / Phương thức**  
> **Môi trường:** JDK 17+, một file Java tự chứa, không dùng thư viện ngoài.  
> **Mục tiêu:** Hiểu Java **truyền đối số theo giá trị**, kể cả khi đối số là tham chiếu mảng; phân biệt sửa phần tử của mảng, gán lại biến tham số, trả về mảng mới và gán lại biến ở phía gọi.

## 1. Quy tắc cốt lõi: tham số nhận bản sao của tham chiếu

Khi truyền một biến mảng vào phương thức, Java **không sao chép toàn bộ các phần tử** và cũng không cho phương thức nắm quyền gán lại biến của bên gọi. Thay vào đó, giá trị tham chiếu tới mảng được **sao chép** sang biến tham số.

~~~java
static void changeFirst(int[] values) {
    values[0] = 99;
}

int[] numbers = {1, 2, 3};
changeFirst(numbers);
// numbers hiện là [99, 2, 3].
~~~

Tại lúc vào phương thức, `numbers` và `values` là **hai biến khác nhau** đang trỏ tới **cùng một đối tượng mảng**:

~~~text
Trong phương thức:
Bên gọi                       Phương thức
numbers ─────────┐          values ─────────┐
                 ▼                          ▼
               [ 1, 2, 3 ]   (CÙNG MỘT MẢNG)
~~~

`values[0] = 99` sửa một phần tử **trong đối tượng mảng dùng chung**. Vì bên gọi vẫn trỏ tới mảng ấy, sau khi phương thức trở về, `numbers[0]` là `99`.

**Thuật ngữ chính xác:** Java dùng *pass-by-value* (truyền theo giá trị), **không** dùng *pass-by-reference* theo nghĩa phương thức có thể gán lại biến `numbers` của bên gọi. Giá trị được sao chép ở đây tình cờ là **tham chiếu đối tượng**, nên các thao tác qua tham chiếu có thể làm thay đổi đối tượng chung.

## 2. Gán lại tham số chỉ đổi biến cục bộ của phương thức

So sánh với lời gọi sau:

~~~java
static void replaceLocal(int[] values) {
    values = new int[] {7, 8}; // values trỏ tới mảng mới.
    values[0] = 70;            // Chỉ sửa mảng mới này.
}

int[] numbers = {1, 2, 3};
replaceLocal(numbers);
// numbers vẫn là [1, 2, 3].
~~~

Sau phép `values = new int[] {7, 8}`:

~~~text
numbers ────────> [1, 2, 3]    (mảng gốc bên gọi)

values  ────────> [7, 8]       (mảng mới của phương thức)
                          └── sửa thành [70, 8]
~~~

Phép gán thay **giá trị tham chiếu được giữ trong tham số `values`**, không thay đổi tham chiếu lưu trong biến `numbers` bên ngoài. Vì vậy bên gọi không tự chuyển sang mảng mới.

| Câu lệnh trong phương thức | Thay đổi gì? | Bên gọi có quan sát được? |
| --- | --- | --- |
| `values[0] = 99;` | Giá trị một phần tử của mảng đang trỏ tới | Có, nếu cùng tham chiếu mảng |
| `values[0]++;` | Tăng phần tử mảng đang trỏ tới | Có, nếu cùng mảng |
| `values = new int[] {7, 8};` | Tham chiếu **cục bộ** trong `values` | Không đổi biến tham chiếu của bên gọi |
| `values = null;` | Chỉ đặt **tham số** thành `null` | Không tự làm biến mảng bên gọi thành `null` |
| `values = values.clone();` | Tham số trỏ sang mảng mới được clone | Không tự thay tham chiếu của bên gọi |
| `return new int[] {...};` | Trả tham chiếu mảng mới | Bên gọi chỉ đổi biến nếu tự gán kết quả |

Quan trọng: Nếu vừa sửa mảng gốc rồi mới gán lại tham số, **phần sửa trước đó vẫn còn** trong mảng gốc.

## 3. Kết hợp sửa nội dung và gán lại tham số

~~~java
static void mutateThenRebind(int[] data) {
    data[1] = 22;               // Sửa mảng gốc.
    data = new int[] {3, 4};    // Chỉ đổi tham số cục bộ.
    data[0] = 30;               // Sửa mảng mới, không phải mảng gốc.
}

int[] original = {11, 2, 3};
mutateThenRebind(original);
// original == [11, 22, 3] theo nội dung.
~~~

Trình tự rất quan trọng: `data[1] = 22` xảy ra **trước** lúc `data` bị gán sang mảng khác, nên kết quả bên gọi nhìn thấy là `[11, 22, 3]`. Còn `data[0] = 30` diễn ra sau phép gán lại, không ảnh hưởng mảng gốc.

**Không nhầm phép so sánh:** `original == other` trên hai biến mảng kiểm tra chúng có cùng tham chiếu không. Để so sánh nội dung mảng một chiều `int[]`, dùng `java.util.Arrays.equals(original, other)`.

## 4. Muốn bên gọi dùng mảng khác: trả về rồi nhận kết quả

Nếu mục tiêu là thay **mảng mà biến ở phía gọi trỏ tới**, cách rõ ràng là phương thức trả về mảng mong muốn và bên gọi tự gán:

~~~java
static int[] replacement(int[] old) {
    return new int[] {100, 200};
}

int[] numbers = {1, 2, 3};
int[] newer = replacement(numbers); // numbers vẫn giữ mảng cũ.
numbers = newer;                    // Bên gọi chủ động gán lại biến.
~~~

Cũng có thể viết trực tiếp:

~~~java
numbers = replacement(numbers);
~~~

Sau phép gán đó, chính **mã bên gọi** thay giá trị của biến `numbers`. Phương thức `replacement` chỉ trả về một tham chiếu; nó không có khả năng truy cập phép gán tới biến local `numbers` của caller.

Nếu muốn tạo mảng mới **dựa trên dữ liệu cũ** mà không sửa nguồn, dùng `Arrays.copyOf`:

~~~java
static int[] withAppended(int[] source, int value) {
    int[] output = java.util.Arrays.copyOf(source, source.length + 1);
    output[source.length] = value;
    return output;
}
~~~

`withAppended(new int[] {1, 2}, 3)` trả mảng nội dung `[1, 2, 3]`, còn mảng nguồn `[1, 2]` không bị thay đổi. `Arrays.copyOf` có thể ném ngoại lệ nếu `source == null`; cần xác định hợp đồng đầu vào trước khi gọi.

## 5. Alias, `clone()` và từ khóa `final`

Hai biến tham chiếu tới cùng mảng được gọi là **alias**. Sửa qua alias cũng là sửa dữ liệu được quan sát qua biến còn lại:

~~~java
int[] first = {3, 4};
int[] alias = first;
alias[0] = 10;

System.out.println(first[0]);   // 10
System.out.println(alias == first); // true
~~~

Còn `clone()` trên mảng `int[]` tạo **đối tượng mảng mới**:

~~~java
int[] copy = first.clone();
copy[0] = 99;

System.out.println(first[0]);      // 10
System.out.println(copy[0]);       // 99
System.out.println(copy == first); // false
~~~

Đối với `int[]`, clone sao chép các giá trị nguyên thủy. Với mảng `String[]` hoặc `Object[]`, clone chỉ sao chép **tham chiếu phần tử** chứ không tự nhân bản các đối tượng được tham chiếu. Với `int[][]`, clone mảng ngoài vẫn chia sẻ các mảng con.

`final` trên một tham số mảng **cấm gán lại biến tham số**, nhưng không tự cấm thay đổi phần tử:

~~~java
static void increment(final int[] values) {
    values[0]++;                  // Hợp lệ.
    // values = new int[] {5};   // LỖI biên dịch vì values là final.
}
~~~

Mảng Java vẫn là đối tượng mutable, kể cả khi tham chiếu tới nó nằm trong biến `final`.

## 6. Mảng tham chiếu và mảng nhiều chiều tuân theo cùng nguyên lý

Nguyên tắc không chỉ áp dụng cho `int[]`:

~~~java
static void changeLabel(String[] labels) {
    labels[0] = "X";                 // Sửa phần tử của mảng gốc.
}

static void rebindLabels(String[] labels) {
    labels = new String[] {"LOCAL"}; // Chỉ đổi tham số.
}
~~~

Với mảng nhiều chiều, cần phân biệt **thay phần tử của mảng ngoài** với **gán lại biến tham số mảng ngoài**:

~~~java
static void changeRows(int[][] matrix) {
    matrix[0][1] = 9;         // Sửa phần tử trong mảng con hiện tại.
    matrix[1] = new int[] {8}; // Sửa phần tử của mảng NGOÀI: thay hàng 1.
}

static void replaceMatrixLocally(int[][] matrix) {
    matrix = new int[][] {{100}}; // Chỉ gán lại tham số cục bộ.
}
~~~

Cả `matrix[0][1] = 9` và `matrix[1] = new int[] {8}` đều thay đổi đối tượng có thể được bên gọi quan sát. Nhưng `matrix = new int[][] {{100}}` **không** thay mảng ngoài mà biến của bên gọi đang giữ.

Tương tự, nếu phần tử của `Person[]` là tham chiếu tới đối tượng mutable, cần phân biệt thay `people[0] = new Person(...)` (thay phần tử mảng) với `people[0].setName(...)` (thay trạng thái của đối tượng mà phần tử trỏ tới). Đó là hai thao tác khác nhau, dù cả hai có thể được bên gọi quan sát qua tham chiếu phù hợp.

## 7. `null`, chỉ số và hợp đồng của phương thức

Ví dụ đơn giản thường giả định tham số có mảng khác `null` và đủ phần tử:

~~~java
static void increaseFirst(int[] numbers) {
    numbers[0] += 10;
}
~~~

- Nếu `numbers == null`, phép truy cập `numbers[0]` gây `NullPointerException`.
- Nếu `numbers.length == 0`, chỉ số 0 không tồn tại và gây `ArrayIndexOutOfBoundsException`.
- Nếu người dùng chỉ muốn gán lại tham số `numbers = new int[3]`, thao tác này **không** tạo/thay mảng bên caller.

Có thể chọn một hợp đồng an toàn và rõ ràng:

~~~java
static boolean tryIncreaseFirst(int[] numbers) {
    if (numbers == null || numbers.length == 0) {
        return false;
    }
    numbers[0] += 10;
    return true;
}
~~~

Nếu cần tạo mảng mới cho bên gọi trong trường hợp null, **trả mảng mới** rồi caller gán kết quả. Không thể biến tham số `null` thành mảng mới ở caller bằng một phép `numbers = new int[3]` nằm trong phương thức `void`.

Trong API thực tế, hãy ghi rõ phương thức có **sửa mảng đầu vào** hay trả về bản sao không sửa nguồn. Chọn tên như `sortInPlace`, `fill`, `copyAndAppend` hoặc tài liệu tương ứng để người gọi không nhầm tác dụng.

## 8. Chương trình Java 17+ độc lập, chạy và xem kết quả

Tạo file **ArrayParameterSemanticsDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayParameterSemanticsDemo {
    private static void increaseFirst(int[] values) {
        values[0] += 10;
    }

    private static void rebindOnly(int[] values) {
        values = new int[] {7, 8};
        values[0] = 70;
        System.out.println("insideRebind=" + Arrays.toString(values));
    }

    private static void mutateThenRebind(int[] values) {
        values[1] = 22;
        values = new int[] {3, 4};
        values[0] = 30;
        System.out.println("insideCombined=" + Arrays.toString(values));
    }

    private static void setParameterNull(int[] values) {
        values = null;
        System.out.println("insideNull=" + (values == null));
    }

    private static int[] replacement(int[] old) {
        return new int[] {100, 200};
    }

    private static void finalMutation(final int[] values) {
        values[0]++;
    }

    private static void changeLabel(String[] values) {
        values[0] = "X";
    }

    private static void rebindLabels(String[] values) {
        values = new String[] {"LOCAL"};
        System.out.println("insideLabelRebind=" + Arrays.toString(values));
    }

    private static void changeRows(int[][] values) {
        values[0][1] = 9;
        values[1] = new int[] {8};
    }

    private static void rebindMatrix(int[][] values) {
        values = new int[][] {{100}};
        System.out.println("insideMatrixRebind=" + Arrays.deepToString(values));
    }

    public static void main(String[] args) {
        int[] original = {1, 2, 3};
        System.out.println("start=" + Arrays.toString(original));

        increaseFirst(original);
        System.out.println("afterElement=" + Arrays.toString(original));

        rebindOnly(original);
        System.out.println("afterRebind=" + Arrays.toString(original));

        mutateThenRebind(original);
        System.out.println("afterCombined=" + Arrays.toString(original));

        int[] alias = original;
        alias[2] = 33;
        System.out.println("aliasSame=" + (alias == original));
        System.out.println("afterAlias=" + Arrays.toString(original));

        setParameterNull(original);
        System.out.println("afterNullOriginal=" + (original != null));

        int[] returned = replacement(original);
        System.out.println("returned=" + Arrays.toString(returned));
        System.out.println("callerBeforeAssign=" + Arrays.toString(original));
        original = returned;
        System.out.println("callerAfterAssign=" + Arrays.toString(original));
        System.out.println("oldAlias=" + Arrays.toString(alias));

        int[] copied = original.clone();
        copied[0] = 500;
        System.out.println("copySame=" + (copied == original));
        System.out.println("copyChanged=" + Arrays.toString(copied));
        System.out.println("sourceAfterCopy=" + Arrays.toString(original));

        finalMutation(original);
        System.out.println("afterFinalMutation=" + Arrays.toString(original));

        String[] labels = {"A", "B"};
        changeLabel(labels);
        System.out.println("afterLabelMutation=" + Arrays.toString(labels));
        rebindLabels(labels);
        System.out.println("afterLabelRebind=" + Arrays.toString(labels));

        int[][] matrix = {{1, 2}, {3, 4}};
        changeRows(matrix);
        System.out.println("afterNestedMutation=" + Arrays.deepToString(matrix));
        rebindMatrix(matrix);
        System.out.println("afterMatrixRebind=" + Arrays.deepToString(matrix));

        try {
            increaseFirst(null);
        } catch (NullPointerException ex) {
            System.out.println("nullMutation=NullPointerException");
        }
    }
}
~~~

Từ thư mục chứa file, chạy trong PowerShell, Command Prompt hoặc Bash:

~~~bash
javac -encoding UTF-8 ArrayParameterSemanticsDemo.java
java ArrayParameterSemanticsDemo
~~~

**Expected stdout chính xác:**

~~~text
start=[1, 2, 3]
afterElement=[11, 2, 3]
insideRebind=[70, 8]
afterRebind=[11, 2, 3]
insideCombined=[30, 4]
afterCombined=[11, 22, 3]
aliasSame=true
afterAlias=[11, 22, 33]
insideNull=true
afterNullOriginal=true
returned=[100, 200]
callerBeforeAssign=[11, 22, 33]
callerAfterAssign=[100, 200]
oldAlias=[11, 22, 33]
copySame=false
copyChanged=[500, 200]
sourceAfterCopy=[100, 200]
afterFinalMutation=[101, 200]
afterLabelMutation=[X, B]
insideLabelRebind=[LOCAL]
afterLabelRebind=[X, B]
afterNestedMutation=[[1, 9], [8]]
insideMatrixRebind=[[100]]
afterMatrixRebind=[[1, 9], [8]]
nullMutation=NullPointerException
~~~

Các dòng `afterElement`, `afterCombined` và `afterNestedMutation` chứng minh sửa **đối tượng mảng** vẫn được thấy sau lời gọi. Các dòng `afterRebind`, `afterLabelRebind` và `afterMatrixRebind` chứng minh thay **tham chiếu của biến tham số** không thay biến của caller. `callerAfterAssign` là trường hợp duy nhất trong ví dụ bên gọi chủ động gán mảng được trả về.

## 9. Lỗi thường gặp và bài tập

| Hiểu nhầm | Cách sửa cách nghĩ |
| --- | --- |
| “Java truyền mảng theo tham chiếu” có nghĩa hàm thay được biến caller | Java truyền **bản sao giá trị tham chiếu**; gán lại tham số không gán lại caller |
| Hàm `void` viết `values = new int[3]` sẽ thay mảng bên gọi | Không; hãy trả mảng hoặc dùng kiểu dữ liệu bao trạng thái nếu thiết kế cần |
| `values[0] = ...` chỉ đổi biến tham số | Không; đó là sửa phần tử của **đối tượng mảng** |
| Thay `matrix[0] = new int[] {...}` cũng không thấy ngoài caller | Sai: đây là gán **phần tử của mảng ngoài**, thấy được qua alias |
| `clone()` luôn sao chép sâu mọi đối tượng | Không; với mảng tham chiếu, phần tử được sao chép dưới dạng tham chiếu |
| Gán `values = null` làm caller thành `null` | Không; chỉ tham số bên trong phương thức đổi |
| Tham số `final int[]` biến mảng thành bất biến | Không; vẫn có thể đổi `values[i]` |
| `Arrays.equals(a,b)` kiểm tra cùng đối tượng | Không; so sánh **nội dung** một chiều, còn `a == b` so sánh cùng tham chiếu |
| Gọi `array[0]` khi mảng `null` hoặc rỗng | Cần kiểm tra null và độ dài trước khi truy cập |

**Bài 1.** Viết `static void doubleFirst(int[] values)` nhân đôi phần tử đầu. Dự đoán giá trị ở bên gọi sau khi chạy với `int[] numbers = {3, 5}`.

**Bài 2.** Viết `static void reset(int[] values) { values = new int[values.length]; }`. Vì sao mảng cũ vẫn giữ giá trị? Sửa bằng `Arrays.fill(values, 0)` nếu muốn thay đổi mảng gốc.

**Bài 3.** Viết `static int[] resized(int[] source)` tạo mảng lớn hơn một phần tử, rồi dùng `source = resized(source)` trong **mã bên gọi**. So sánh trước và sau phép gán.

**Bài 4.** Truyền `String[]` vào phương thức đổi `values[0]`, sau đó thử gán `values = new String[] {...}`. So sánh kết quả trên mảng gốc.

**Bài 5.** Với `int[][]`, so sánh `matrix[0] = new int[] {9}` với `matrix = new int[][] {{9}}` trong phương thức. Lệnh nào thay được hàng của mảng caller?

**Bài 6.** Thử `final int[] data` trong tham số: biên dịch trường hợp thay `data[0]` và trường hợp `data = new int[1]`; giải thích vì sao chỉ một trường hợp hợp lệ.

### Ghi nhớ

**Java luôn truyền đối số theo giá trị.** Khi đối số là mảng, giá trị được sao chép là **tham chiếu tới mảng**: sửa `values[i]` thay đổi mảng dùng chung, còn `values = anotherArray` chỉ thay tham chiếu **cục bộ**. Muốn caller trỏ tới mảng mới, hãy **trả tham chiếu mới và gán ở phía gọi**; muốn giữ cùng mảng thì sửa các phần tử có chủ đích và nêu rõ hợp đồng phương thức.
