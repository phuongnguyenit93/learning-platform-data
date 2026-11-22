# Dùng ngắn mạch để kiểm tra null và giới hạn mảng — Java 17+

## 1. Bài học cốt lõi

Trong Java, toán tử logic **`&&` (AND ngắn mạch)** và **`||` (OR ngắn mạch)** có thể **không đánh giá toán hạng bên phải** nếu kết quả đã được quyết định từ toán hạng bên trái.

Đây là cơ sở để kiểm tra an toàn theo thứ tự: **tham chiếu khác `null` → chỉ số không âm → chỉ số nhỏ hơn `array.length` → mới truy cập phần tử**.

~~~java
int[] values = {4, 0, -2};
int index = 0;

boolean positive = values != null
        && index >= 0
        && index < values.length
        && values[index] > 0;

System.out.println(positive); // true
~~~

Nếu `values == null`, biểu thức `values.length` **không được đánh giá**. Nếu `index` ngoài miền hợp lệ, `values[index]` **không được truy cập**. Nhưng điều này chỉ đúng khi các phép kiểm tra được đặt **đúng thứ tự và dùng toán tử ngắn mạch**.

## 2. Quy tắc `&&` và `||`

Với hai biểu thức boolean `left`, `right`:

| Biểu thức | Khi nào bỏ qua `right`? | Kết quả khi bỏ qua |
|---|---|---|
| `left && right` | Khi `left == false` | `false` |
| `left || right` | Khi `left == true` | `true` |

Cụ thể:

~~~java
boolean a = false;
boolean b = true;

boolean andResult = a && b; // false
boolean orResult = b || a;  // true
~~~

Java đánh giá toán hạng trái trước. **Nếu cần thiết**, toán hạng phải mới được đánh giá; đây không phải đặc tính “compiler tình cờ tối ưu” mà là **ngữ nghĩa của toán tử**.

~~~mermaid
flowchart TD
    A["Đánh giá vế trái của &&"] --> B{"Vế trái true?"}
    B -- "Không" --> C["Trả false, bỏ qua vế phải"]
    B -- "Có" --> D["Đánh giá vế phải và dùng kết quả"]
    E["Đánh giá vế trái của ||"] --> F{"Vế trái true?"}
    F -- "Có" --> G["Trả true, bỏ qua vế phải"]
    F -- "Không" --> H["Đánh giá vế phải và dùng kết quả"]
~~~

Các biểu thức như `a && b && c` được nhóm theo tính kết hợp trái; cả chuỗi có thể dừng ngay khi tìm được một điều kiện false. Tương tự `a || b || c` có thể dừng ngay khi thấy true.

## 3. Kiểm tra `null` đúng thứ tự

Giả sử tham chiếu `String` có thể null:

~~~java
String name = null;

boolean valid = name != null && !name.isBlank();
System.out.println(valid); // false, không ném NullPointerException
~~~

Vế trái `name != null` là false, vì vậy Java **không gọi** `name.isBlank()`. Nếu đảo thứ tự:

~~~java
String name = null;
// boolean invalid = !name.isBlank() && name != null;
// Khi chạy: NullPointerException vì gọi isBlank() trước.
~~~

**Quy tắc:** điều kiện an toàn phải **đi trước thao tác phụ thuộc vào nó**.

| Nên dùng | Vì sao? |
|---|---|
| `obj != null && obj.isReady()` | Không gọi method trên null |
| `text != null && !text.isEmpty()` | Không truy cập String null |
| `array != null && array.length > 0` | Không lấy `length` trên null |
| `boxed != null && boxed > 0` | Không unbox wrapper null |

Không phải cứ viết `&&` ở đâu cũng an toàn. Ví dụ `obj.isReady() && obj != null` vẫn truy cập null **trước** khi kiểm tra.

## 4. Guard giới hạn mảng một chiều

Với mảng `int[] array` có độ dài `n`, chỉ số hợp lệ phải thuộc khoảng **`[0, n)`**:

\[
0 \le \text{index} < \text{array.length}
\]

Java **không** hỗ trợ cú pháp `0 <= index < array.length` kiểu toán học. Phải viết hai điều kiện riêng.

~~~java
static boolean positiveAt(int[] array, int index) {
    return array != null
            && index >= 0
            && index < array.length
            && array[index] > 0;
}
~~~

Hàm có các thuộc tính sau:

1. Mảng null → `false`, không truy cập `length`.
2. Chỉ số âm → `false`, không truy cập phần tử.
3. `index == array.length` → `false`: đây là **vị trí nằm ngay sau phần tử cuối**.
4. Chỉ số hợp lệ → mới kiểm tra `array[index] > 0`.
5. Mảng rỗng → luôn trả `false` với mọi chỉ số `int`.

Với `int[] values = {4, 0, -2}`, các chỉ số hợp lệ là `0`, `1`, `2`, **không phải 3**.

**Lỗi off-by-one rất thường gặp:**

~~~java
// index <= array.length // SAI với truy cập phần tử
// index < array.length  // ĐÚNG nếu đồng thời index >= 0
~~~

Chỉ số âm cũng không thể bỏ qua: Java **không** coi `array[-1]` là phần tử cuối như một số ngôn ngữ khác.

## 5. Kiểm tra giá trị phần tử có thể null

Một mảng tham chiếu như `String[]` có thể **không null**, nhưng một phần tử của nó lại **null**:

~~~java
String[] names = {"Java", null, "Go"};

boolean startsWithJ = names != null
        && 1 >= 0
        && 1 < names.length
        && names[1] != null
        && names[1].startsWith("J");

System.out.println(startsWithJ); // false, không gọi startsWith trên null
~~~

Quy trình guard phải phân biệt **null của mảng** với **null của phần tử**:

~~~java
static boolean startsWithJAt(String[] names, int index) {
    return names != null
            && index >= 0
            && index < names.length
            && names[index] != null
            && names[index].startsWith("J");
}
~~~

Nếu bỏ `names[index] != null`, đoạn cuối có thể gây `NullPointerException`. Đừng suy rằng `names != null` đủ bảo đảm mọi phần tử đều tồn tại và không null.

**Tính dễ đọc:** Nếu dùng cùng `names[index]` quá nhiều lần và dữ liệu có thể thay đổi đồng thời, hãy xác thực môi trường/đồng bộ trước; chỉ lặp biểu thức guard không biến thao tác thành nguyên tử.

## 6. Dùng `||` để loại bỏ dữ liệu không hợp lệ

Khi muốn phát hiện một chỉ số **không hợp lệ**, có thể dùng điều kiện nghịch đảo:

~~~java
static boolean invalidIndex(int[] array, int index) {
    return array == null || index < 0 || index >= array.length;
}
~~~

Ở đây:

- Nếu `array == null` true, Java trả `true` ngay; không truy cập `array.length`.
- Nếu `index < 0` true, điều kiện tiếp theo cũng bị bỏ qua.
- Nếu đã vượt qua hai guard, `array.length` mới được đọc.

Mẫu hay dùng trong một phương thức:

~~~java
if (array == null || index < 0 || index >= array.length) {
    return false; // Hoặc throw theo hợp đồng API
}
return array[index] > 0; // Sau guard, chỉ số hợp lệ
~~~

Hai cách mô tả cùng miền điều kiện:

| Ý nghĩa | Mẫu logic |
|---|---|
| Hợp lệ để truy cập | `array != null && index >= 0 && index < array.length` |
| Không hợp lệ | `array == null || index < 0 || index >= array.length` |
| Truy cập phần tử nếu hợp lệ | `guard && array[index] > 0` |
| Từ chối rồi mới truy cập | `if (invalid) return ...;` rồi `array[index]` |

Đây là một ứng dụng của quy tắc **De Morgan** khi điều kiện không có tác dụng phụ. Chọn cách diễn đạt đúng ngữ nghĩa nghiệp vụ và dễ kiểm tra.

## 7. `&` và `|` KHÔNG ngắn mạch trên boolean

Java có các toán tử `&` (AND không ngắn mạch) và `|` (OR không ngắn mạch) dùng được trên boolean. Chúng **đánh giá cả hai vế**, khác với `&&` và `||`.

~~~java
int[] numbers = null;

// boolean unsafe = numbers != null & numbers.length > 0;
// Nếu chạy: NullPointerException vì vế phải vẫn được đánh giá.
~~~

Tương tự:

~~~java
int[] values = {4, 0};

// boolean unsafe = (values != null) & (values[99] > 0);
// Nếu chạy: ArrayIndexOutOfBoundsException.
~~~

**Đừng thay `&&` bằng `&` trong null guard.** Với `|`, cũng không dùng để thay `||` nếu dựa vào việc bỏ qua phép truy cập nguy hiểm ở vế phải:

~~~java
// values == null | values.length == 0
// Nếu values là null, truy cập values.length vẫn chạy và có thể ném NPE.
~~~

Bảng đối chiếu:

| Toán tử | Dùng với boolean | Đánh giá vế phải khi vế trái đã quyết định kết quả? |
|---|---|---|
| `&&` | Có | Không |
| `||` | Có | Không |
| `&` | Có | **Có** |
| `|` | Có | **Có** |

Toán tử `&`/`|` còn dùng trong thao tác bitwise số nguyên; đây là chức năng khác. Bài này chỉ so sánh **ngữ nghĩa boolean**.

## 8. Mảng hai chiều có thể chứa hàng null hoặc hàng dài ngắn khác nhau

Trong Java, `int[][]` là **mảng chứa các tham chiếu tới từng hàng**. Một hàng có thể null, hàng khác có độ dài riêng (*jagged array*). Không được giả định mọi hàng đều có `matrix[0].length`.

~~~java
static boolean positiveAt2D(int[][] matrix, int row, int col) {
    return matrix != null
            && row >= 0
            && row < matrix.length
            && matrix[row] != null
            && col >= 0
            && col < matrix[row].length
            && matrix[row][col] > 0;
}
~~~

Thứ tự đúng:

1. Mảng ngoài khác null.
2. `row` nằm trong `[0, matrix.length)`.
3. Hàng `matrix[row]` khác null.
4. `col` không âm, nhỏ hơn **độ dài của chính hàng đã chọn**.
5. Chỉ khi ấy mới đọc `matrix[row][col]`.

Nếu đảo `matrix[row] != null` lên trước kiểm tra `row`, vẫn có thể ném `ArrayIndexOutOfBoundsException`. Nếu lấy `matrix[row].length` trước khi chắc chắn hàng khác null, có thể ném `NullPointerException`.

## 9. Boolean wrapper cũng có thể là `null`

Với kiểu nguyên thủy `boolean`, chỉ có `true` hoặc `false`. Với wrapper `Boolean`, còn có thể là `null`:

~~~java
Boolean enabled = null;
boolean allowed = enabled != null && enabled;

System.out.println(allowed); // false
~~~

Khi `enabled == null`, toán hạng `enabled` ở bên phải không được đánh giá, tránh auto-unboxing null.

Nếu muốn chỉ true mới được chấp nhận, một lựa chọn khác là:

~~~java
boolean allowed = Boolean.TRUE.equals(enabled);
~~~

Cách này xử lý null an toàn, nhưng đừng nhầm kiểm tra Boolean với kiểm tra **miền chỉ số mảng**: hai vấn đề có thể xuất hiện cùng lúc và cần guard độc lập.

## 10. Ngoại lệ và tác dụng phụ: short-circuit không bảo vệ mọi thứ

`&&`/`||` chỉ bỏ qua những **toán hạng chưa được đánh giá**. Chúng không hoàn tác tác dụng phụ trước đó và không tự xử lý các lỗi bên trong vế trái.

~~~java
int index = 0;
int[] values = {10, 20};

boolean result = index++ < values.length
        && values[index] > 0;

// Không nên viết: index đã tăng trước khi vế phải dùng index.
~~~

Dù biểu thức này có thể chạy với một số dữ liệu, nó dễ sai ở ranh giới: ví dụ `index` ban đầu là `values.length - 1`; vế trái có thể true rồi tăng chỉ số thành `values.length`, và vế phải truy cập ngoài mảng.

**Guard không nên tự thay đổi biến mà nó dùng để kiểm tra.** Tốt hơn:

~~~java
int index = 1;
boolean valid = values != null
        && index >= 0
        && index < values.length;
if (valid) {
    int current = values[index];
    index++; // Cập nhật rõ ràng ở một câu lệnh khác
}
~~~

Với nhiều thread cùng sửa tham chiếu, chỉ số hoặc nội dung mảng, các guard thông thường **không bảo đảm atomicity hoặc thread safety**. Cần đồng bộ/phân quyền sở hữu dữ liệu theo yêu cầu, thay vì chỉ đặt thêm `&&`.

## 11. Khi nào nên tách thành `if` và guard clause?

Một điều kiện ngắn như:

~~~java
boolean safe = array != null
        && index >= 0
        && index < array.length;
~~~

thường rất dễ hiểu. Nhưng khi phải kiểm tra nhiều thuộc tính hoặc cần **thông báo lỗi riêng** cho null, chỉ số âm và chỉ số quá lớn, cách dùng guard clause rõ hơn:

~~~java
static int requireElement(int[] array, int index) {
    if (array == null) {
        throw new IllegalArgumentException("array is null");
    }
    if (index < 0 || index >= array.length) {
        throw new IndexOutOfBoundsException("invalid index: " + index);
    }
    return array[index];
}
~~~

Ưu điểm:

- Chỉ ra chính xác nguyên nhân từ chối.
- Tách bước validation khỏi thao tác đọc.
- Có thể kiểm thử riêng từng nhánh lỗi.
- Tránh điều kiện boolean quá dài hoặc lặp thao tác có side effect.

Java 17 cũng có `Objects.checkIndex(index, length)` để kiểm tra chỉ số trong `[0,length)`; hàm này ném ngoại lệ nếu không hợp lệ. Nhưng khi đối tượng mảng có thể null, vẫn cần xử lý null **trước khi** truy cập `array.length`.

**Chọn API theo hợp đồng:** hàm truy vấn có thể trả false khi dữ liệu không hợp lệ; hàm truy cập bắt buộc có thể ném exception có ý nghĩa. Không âm thầm trả giá trị mặc định nếu làm mất khác biệt giữa dữ liệu lỗi và dữ liệu hợp lệ.

## 12. Ví dụ Java 17 hoàn chỉnh, có kết quả cố định

Tạo file đúng tên **`ShortCircuitArrayGuardDemo.java`**:

~~~java
public final class ShortCircuitArrayGuardDemo {
    private ShortCircuitArrayGuardDemo() {}

    static boolean positiveAt(int[] array, int index) {
        return array != null
                && index >= 0
                && index < array.length
                && array[index] > 0;
    }

    static boolean invalidIndex(int[] array, int index) {
        return array == null || index < 0 || index >= array.length;
    }

    static boolean startsWithJAt(String[] names, int index) {
        return names != null
                && index >= 0
                && index < names.length
                && names[index] != null
                && names[index].startsWith("J");
    }

    static boolean positiveAt2D(int[][] matrix, int row, int col) {
        return matrix != null
                && row >= 0
                && row < matrix.length
                && matrix[row] != null
                && col >= 0
                && col < matrix[row].length
                && matrix[row][col] > 0;
    }

    static boolean traced(String label, boolean answer) {
        System.out.println("called " + label);
        return answer;
    }

    static int requireElement(int[] array, int index) {
        if (array == null) {
            throw new IllegalArgumentException("array is null");
        }
        if (index < 0 || index >= array.length) {
            throw new IndexOutOfBoundsException("invalid index: " + index);
        }
        return array[index];
    }

    public static void main(String[] args) {
        int[] scores = {4, 0, -2};
        System.out.println("positive[0]=" + positiveAt(scores, 0));
        System.out.println("positive[1]=" + positiveAt(scores, 1));
        System.out.println("positive[2]=" + positiveAt(scores, 2));
        System.out.println("negative index=" + positiveAt(scores, -1));
        System.out.println("end index=" + positiveAt(scores, 3));
        System.out.println("null array=" + positiveAt(null, 0));
        System.out.println("empty array=" + positiveAt(new int[0], 0));

        System.out.println("invalid null=" + invalidIndex(null, 0));
        System.out.println("invalid end=" + invalidIndex(scores, 3));
        System.out.println("valid index=" + !invalidIndex(scores, 2));

        String[] names = {"Java", null, "Go"};
        System.out.println("name[0]=" + startsWithJAt(names, 0));
        System.out.println("name[1]=" + startsWithJAt(names, 1));
        System.out.println("name null=" + startsWithJAt(null, 0));

        int[][] grid = {null, {3, 0}, {}};
        System.out.println("grid null row=" + positiveAt2D(grid, 0, 0));
        System.out.println("grid positive=" + positiveAt2D(grid, 1, 0));
        System.out.println("grid col end=" + positiveAt2D(grid, 1, 2));
        System.out.println("grid empty row=" + positiveAt2D(grid, 2, 0));

        Boolean enabled = null;
        System.out.println("nullable Boolean="
                + (enabled != null && enabled));

        boolean left = false;
        boolean skippedAnd = left && traced("and-right", true);
        System.out.println("&& skipped=" + skippedAnd);

        left = true;
        boolean skippedOr = left || traced("or-right", false);
        System.out.println("|| skipped=" + skippedOr);

        boolean eagerAnd = false & traced("and-eager", true);
        System.out.println("& evaluated=" + eagerAnd);

        boolean eagerOr = true | traced("or-eager", false);
        System.out.println("| evaluated=" + eagerOr);

        int[] missing = null;
        try {
            boolean unsafe = missing != null & missing.length > 0;
            System.out.println(unsafe);
        } catch (NullPointerException ex) {
            System.out.println("eager null=NullPointerException");
        }

        try {
            boolean unsafe = scores != null & scores[99] > 0;
            System.out.println(unsafe);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("eager index=ArrayIndexOutOfBoundsException");
        }

        System.out.println("required element=" + requireElement(scores, 0));
        try {
            requireElement(scores, 3);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("required invalid=" + ex.getMessage());
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; terminal ở thư mục chứa file; không cần Maven, Gradle hoặc thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ShortCircuitArrayGuardDemo.java
java -cp . ShortCircuitArrayGuardDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ShortCircuitArrayGuardDemo.java
java -cp . ShortCircuitArrayGuardDemo
~~~

**Exact expected stdout:**

~~~text
positive[0]=true
positive[1]=false
positive[2]=false
negative index=false
end index=false
null array=false
empty array=false
invalid null=true
invalid end=true
valid index=true
name[0]=true
name[1]=false
name null=false
grid null row=false
grid positive=true
grid col end=false
grid empty row=false
nullable Boolean=false
&& skipped=false
|| skipped=true
called and-eager
& evaluated=false
called or-eager
| evaluated=true
eager null=NullPointerException
eager index=ArrayIndexOutOfBoundsException
required element=4
required invalid=invalid index: 3
~~~

### Cách kiểm tra kết quả

1. `positiveAt` từ chối mảng null, mảng rỗng, chỉ số âm và chỉ số bằng `length`; chỉ truy cập khi các guard đã qua.
2. `invalidIndex` dùng OR ngắn mạch: mảng null hoặc chỉ số ngoài miền đều cho true an toàn.
3. `startsWithJAt` kiểm tra cả mảng và **phần tử** trước khi gọi method trên String.
4. `positiveAt2D` kiểm tra hàng null, độ dài riêng từng hàng và cột ngoài miền.
5. `Boolean enabled = null` không gây NPE nhờ guard trước lúc unboxing.
6. Hai dòng `&& skipped` và `|| skipped` **không in `called and-right` hoặc `called or-right`**, chứng minh vế phải bị bỏ qua.
7. `&` và `|` vẫn in `called and-eager`, `called or-eager` vì chúng không short-circuit.
8. Hai trường hợp `eager ...` ném NPE/AIOOBE; ví dụ bắt đúng loại và in thông báo cố định.
9. `requireElement` minh họa tình huống dùng exception rõ ràng thay vì một giá trị mặc định.

## 13. Lỗi thường gặp

| Lỗi hoặc ngộ nhận | Hậu quả | Cách đúng |
|---|---|---|
| `array.length > 0 && array != null` | NPE nếu mảng null | Kiểm tra `array != null` trước |
| `array != null & array.length > 0` | `&` luôn đánh giá vế phải | Dùng `&&` |
| `array == null | array.length == 0` | `|` luôn đánh giá vế phải | Dùng `||` |
| `index < array.length` không kiểm tra âm | Chỉ số âm vẫn có thể truy cập sai | `index >= 0 && index < array.length` |
| `index <= array.length` | Cho phép index bằng length | Dùng `index < array.length` |
| `array != null && array[index] > 0` | Chỉ bảo vệ null, chưa bảo vệ index | Thêm hai kiểm tra giới hạn |
| `names != null && names[i].isBlank()` | Phần tử `names[i]` có thể null | Kiểm tra `names[i] != null` |
| `matrix[row].length` trước khi kiểm tra row | Row có thể ngoài miền hoặc null | Guard ma trận, row, hàng rồi col |
| `array[index++]` trong guard | Index có thể đổi giữa kiểm tra và truy cập | Tách cập nhật index khỏi validation |
| `&&` tự đồng bộ mọi dữ liệu | Không atomic nếu dữ liệu bị thread khác sửa | Dùng đồng bộ/ownership phù hợp |
| Nghĩ `&&` và `&` chỉ khác hiệu năng | Side effect và exception có thể khác | Chọn theo ngữ nghĩa |
| Dùng null guard nhưng vẫn truy cập bên ngoài guard | Guard chỉ bảo vệ đoạn được kiểm soát | Xác thực ở điểm truy cập hoặc thiết kế API rõ |
| `Boolean nullable` tự chuyển null thành false | Unboxing null ném NPE | Guard `!= null` hoặc `Boolean.TRUE.equals` |

## 14. Bài tập có đáp án

### Bài A — kiểm tra chỉ số hợp lệ

Cho `int[] values = {5, 8, 13};` và một `index`. Hãy viết điều kiện chỉ đọc `values[index]` khi mảng tồn tại và index hợp lệ.

**Đáp án:**

~~~java
boolean valid = values != null
        && index >= 0
        && index < values.length;
if (valid) {
    System.out.println(values[index]);
}
~~~

Nếu `index == 3` hoặc `-1`, đoạn truy cập bị bỏ qua.

### Bài B — `&&` khác `&`

~~~java
int[] a = null;
boolean safe = a != null && a.length > 0;
// boolean unsafe = a != null & a.length > 0;
~~~

**Đáp án:** `safe == false`, không ném lỗi. Nếu chạy dòng `unsafe`, vế phải vẫn đọc `a.length` và ném `NullPointerException`.

### Bài C — guard với `||`

~~~java
int[] a = {2, 3};
int i = -1;
boolean invalid = a == null || i < 0 || i >= a.length;
System.out.println(invalid);
~~~

**Đáp án:** `true`; Java dừng ở `i < 0`, không cần tính vế cuối.

### Bài D — phần tử String null

~~~java
String[] names = {null, "Java"};
int i = 0;
boolean ok = names != null
        && i >= 0 && i < names.length
        && names[i] != null && names[i].startsWith("J");
System.out.println(ok);
~~~

**Đáp án:** `false`, không ném NPE.

### Bài E — mảng hai chiều

~~~java
int[][] matrix = {null, {3, 4}};
System.out.println(positiveAt2D(matrix, 0, 0));
System.out.println(positiveAt2D(matrix, 1, 1));
~~~

**Đáp án:**

~~~text
false
true
~~~

Hàm `positiveAt2D` được định nghĩa trong ví dụ độc lập phía trên.

### Bài F — lỗi khi index thay đổi ngay trong guard

~~~java
int[] values = {10, 20};
int index = 1;
// boolean ok = index++ < values.length && values[index] > 0;
~~~

**Đáp án:** vế trái so `1 < 2` cho true nhưng tăng `index` lên 2; vế phải `values[2]` gây `ArrayIndexOutOfBoundsException`. Hãy dùng index không thay đổi trong quá trình guard, rồi cập nhật nó bằng câu lệnh riêng.

## 15. Checklist và kết luận

- [ ] Nhớ `&&` bỏ vế phải khi vế trái false; `||` bỏ vế phải khi vế trái true.
- [ ] Không nhầm `&&`/`||` với `&`/`|` boolean.
- [ ] Luôn kiểm tra `array != null` trước `array.length`.
- [ ] Kiểm tra cả `index >= 0` và `index < array.length`.
- [ ] Với mảng reference, kiểm tra `array[index] != null` trước gọi method trên phần tử.
- [ ] Với mảng hai chiều, guard từng cấp theo đúng thứ tự.
- [ ] Dùng `array == null || index < 0 || index >= array.length` khi cần phát hiện invalid.
- [ ] Hiểu short-circuit bỏ qua side effect ở vế phải nhưng không rollback thao tác đã xảy ra.
- [ ] Không tăng/giảm index ngay trong các phép so sánh guard nếu còn dùng lại nó.
- [ ] Phân biệt kiểm tra dữ liệu an toàn trong một thread và thread safety thực sự.
- [ ] Chọn trả boolean hoặc ném exception theo hợp đồng API.
- [ ] Biên dịch/chạy `ShortCircuitArrayGuardDemo.java` bằng Java 17+ và đối chiếu chính xác stdout.

**Kết luận:** Dùng ngắn mạch hiệu quả nhất khi **đặt điều kiện bảo vệ trước thao tác có thể lỗi**, theo thứ tự **null → chỉ số không âm → chỉ số nhỏ hơn length → phần tử tồn tại → truy cập**. `&&` và `||` cung cấp bảo đảm ngữ nghĩa để bỏ qua vế phải; `&` và `|` không làm vậy. Guard rõ ràng, không kèm side effect và có kiểm thử biên giúp code Java 17+ dễ đọc, đúng logic và tránh `NullPointerException`/`ArrayIndexOutOfBoundsException` không cần thiết.