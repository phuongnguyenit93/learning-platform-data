# Mảng tham chiếu hiệp biến và nguy cơ `ArrayStoreException` trong Java

> **Java core — language-basics / Mảng nhiều chiều**  
> **Yêu cầu:** Java 17+, JDK, không cần thư viện ngoài.  
> **Mục tiêu:** Giải thích vì sao `String[]` gán được cho `Object[]`, tại sao phép gán một phần tử vẫn có thể thất bại khi chạy, cách kiểm tra kiểu phần tử thực của mảng, và vận dụng đúng với `String[][]`, `Object[][]` và `int[][]`.

## 1. Hiệp biến (*covariance*) của mảng tham chiếu

Giả sử `String` là lớp con của `Object`. Java cho phép coi **mảng tham chiếu** `String[]` như một `Object[]`:

~~~java
String[] names = {"An", "Binh"};
Object[] view = names; // Hợp lệ: String[] là subtype của Object[].
System.out.println(view == names); // true
~~~

Đây gọi là **hiệp biến của mảng tham chiếu**: nếu `Sub` là một subtype của `Super` và cả hai là kiểu tham chiếu phù hợp, `Sub[]` có thể gán cho biến `Super[]`. Các ví dụ:

| Quan hệ | Có gán trực tiếp? | Lý do |
| --- | --- | --- |
| `String[]` → `Object[]` | Có | `String` là subtype của `Object` |
| `Integer[]` → `Number[]` | Có | `Integer` là subtype của `Number` |
| `Dog[]` → `Animal[]` nếu `Dog extends Animal` | Có | Quan hệ subtype của thành phần |
| `Object[]` → `String[]` | Không, trừ ép kiểu có kiểm tra runtime | Hướng ngược không an toàn |
| `int[]` → `Object[]` | **Không** | `int` là nguyên thủy, không phải subtype của `Object` |
| `int[]` → `Object` | Có | Bản thân mảng là đối tượng |
| `String[][]` → `Object[][]` | Có | Các kiểu mảng ở từng tầng có quan hệ subtype phù hợp |

**Cần phân biệt biến tham chiếu với đối tượng thực:** Trong `Object[] view = names;`, Java **không tạo một mảng `Object[]` mới**. Hai biến chỉ cùng giữ tham chiếu đến đối tượng có **kiểu thực khi chạy là `String[]`**.

## 2. Vì sao kiểm tra lúc biên dịch chưa đủ an toàn?

Xét đoạn mã:

~~~java
String[] names = {"An", "Binh"};
Object[] items = names;

items[1] = "Chi";            // Hợp lệ: String.
System.out.println(names[1]); // Chi.

// items[0] = Integer.valueOf(7); // Biên dịch được,
// nhưng khi chạy ném ArrayStoreException.
~~~

Nhìn vào **kiểu khai báo** `Object[]`, trình biên dịch cho phép đặt một tham chiếu `Integer` vào một phần tử `Object`. Nhưng đối tượng mảng thật sự vẫn là `String[]`, chỉ cho phép mỗi phần tử nhận `String` (hoặc `null`). JVM kiểm tra tại lúc thực hiện thao tác ghi và ném `ArrayStoreException` nếu giá trị không tương thích với **kiểu thành phần runtime**.

Nói cách khác, có **hai lớp kiểm tra**:

1. **Compile time:** biểu thức ở bên phải phải gán được cho kiểu phần tử theo **kiểu tĩnh** của biến mảng (`Object` đối với `Object[]`).
2. **Runtime:** nếu phần tử là tham chiếu không null, JVM kiểm tra đối tượng được ghi có phù hợp với **kiểu thành phần thực của đối tượng mảng** không (`String` đối với `new String[n]`).

Do đó, `Object[]` là tên kiểu mà mã nhìn thấy, không phải lời hứa rằng đối tượng mảng hiện tại chứa được mọi loại `Object`.

Một phương thức nhận `Object[]` cũng có rủi ro tương tự:

~~~java
static void replaceFirst(Object[] array, Object value) {
    array[0] = value; // Có thể ném ArrayStoreException.
}

// replaceFirst(new String[1], Integer.valueOf(10));
// Lời gọi hợp lệ khi biên dịch, thất bại lúc ghi.
~~~

## 3. `ArrayStoreException` xảy ra khi nào?

`ArrayStoreException` là ngoại lệ **runtime** khi cố ghi một giá trị tham chiếu không tương thích vào một mảng có kiểu thành phần tham chiếu cụ thể. Nó kế thừa `RuntimeException`, vì vậy không cần khai báo `throws` để biên dịch lời gọi.

~~~java
Object[] values = new String[2];
values[0] = "Java";       // Đúng.
values[1] = null;         // Đúng: null được phép với kiểu tham chiếu.

try {
    values[1] = Integer.valueOf(42); // Sai kiểu thực String[].
} catch (ArrayStoreException ex) {
    System.out.println("Rejected");
}
~~~

**Cách phân biệt lỗi:**

| Tình huống | Hành vi |
| --- | --- |
| `Object[] a = new String[2]; a[0] = "x";` | Ghi thành công |
| `a[0] = null;` | Ghi thành công; `null` hợp lệ |
| `a[0] = 42;` | `ArrayStoreException` (autobox số 42 thành `Integer`) |
| `Object[] b = new Object[2]; b[0] = 42;` | Ghi thành công vì mảng thực là `Object[]` |
| `String[] s = (String[]) new Object[2];` | `ClassCastException` khi ép kiểu mảng, **không** phải lỗi ghi phần tử |
| `String[] s = null; s[0] = "x";` | `NullPointerException` |
| `new String[0][0];` rồi truy cập phần tử `[0]` | `ArrayIndexOutOfBoundsException` |

**Đừng kiểm tra ngoại lệ bằng thông báo JVM:** nội dung `ex.getMessage()` có thể khác giữa các môi trường; khi demo, in loại ngoại lệ để expected stdout ổn định.

## 4. Kiểu thành phần thật được giữ tại runtime

Khác với thông tin generic thường bị xóa kiểu (*type erasure*), đối tượng mảng Java **biết kiểu thành phần runtime**:

~~~java
Object[] strings = new String[2];
Object[] objects = new Object[2];

System.out.println(strings.getClass().getComponentType().getTypeName());
// java.lang.String
System.out.println(objects.getClass().getComponentType().getTypeName());
// java.lang.Object
~~~

Bởi vậy, `Object[] strings` và `Object[] objects` có **cùng kiểu biến được khai báo** nhưng kiểm tra ghi phần tử khác nhau.

Khi gán `Object[] alias = strings;`, kiểu runtime vẫn không đổi. `strings.clone()` cũng tạo mảng mới **cùng kiểu runtime `String[]`** và sao chép các phần tử hiện tại; mảng clone vẫn không cho chứa `Integer` chỉ vì được gán sang biến `Object[]`.

Nếu muốn một mảng thật sự có thể lưu nhiều loại đối tượng, cần **tạo mảng `Object[]` mới** và sao chép các phần tử phù hợp vào đó, chẳng hạn `Object[] copy = java.util.Arrays.copyOf(strings, strings.length, Object[].class);`.

## 5. Hiệp biến trong mảng nhiều chiều

Một `String[][]` là **mảng ngoài chứa các tham chiếu tới `String[]`**. Nó có thể được nhìn qua biến `Object[][]`:

~~~java
String[][] names = {{"A", "B"}, {"C"}};
Object[][] grid = names;

Object[] firstRow = grid[0]; // Thực tế là String[].
firstRow[1] = "BB";           // Đúng.
System.out.println(names[0][1]); // BB.
~~~

Có **hai vị trí ghi** cần xem xét, mỗi vị trí kiểm tra kiểu của mảng nơi ghi:

| Lệnh qua `Object[][] grid` | Mảng thực được ghi | Kết quả |
| --- | --- | --- |
| `grid[0][0] = "X";` | Mảng con thực `String[]` | Đúng |
| `grid[0][0] = 5;` | Mảng con thực `String[]` | `ArrayStoreException` |
| `grid[1] = new String[] {"Y"};` | Mảng ngoài thực `String[][]`, phần tử kiểu `String[]` | Đúng |
| `grid[1] = new Object[] {"Y"};` | Mảng ngoài thực `String[][]` | `ArrayStoreException` |
| `grid[0] = null;` | Mảng ngoài thực `String[][]` | Đúng; hàng trở thành `null` |

Như vậy, lỗi có thể xảy ra cả **khi thay một mảng con** (`grid[row] = ...`) lẫn **khi thay một phần tử bên trong mảng con** (`grid[row][column] = ...`).

`String[][]` còn có thể được gán cho biến `Object[]` vì phần tử của nó (kiểu `String[]`) cũng là một đối tượng. Tuy nhiên kiểu runtime của mảng ngoài vẫn là `String[][]`; lưu một `Object[]` không phải `String[]` vào một ô hàng cũng sẽ bị từ chối.

**Mảng răng cưa** không thay đổi nguyên tắc: các hàng có thể dài ngắn khác nhau, nhưng mỗi hàng không null vẫn phải là mảng con có kiểu phù hợp với mảng ngoài.

## 6. Ngoại lệ quan trọng: `int[]` và `int[][]`

Với mảng kiểu nguyên thủy:

~~~java
int[] numbers = {1, 2};
Object asObject = numbers; // Đúng: mọi mảng là Object.
// Object[] invalid = numbers; // LỖI biên dịch: int[] không là Object[].
~~~

`int[]` chứa phần tử kiểu nguyên thủy `int`, không phải tham chiếu `Object`. Nhưng `int[][]` là **mảng ngoài chứa các phần tử có kiểu tham chiếu `int[]`**, vì bản thân mỗi `int[]` là một đối tượng. Do đó:

~~~java
int[][] matrix = new int[2][];
Object[] rows = matrix;              // Hợp lệ.
rows[0] = new int[] {1, 2};         // Hợp lệ.
System.out.println(matrix[0][0]);  // 1.

// rows[1] = new long[] {3L};
// Biên dịch được qua Object[], nhưng ném ArrayStoreException:
// mảng ngoài thực tế yêu cầu mỗi hàng là int[].
~~~

Đây không phải “mảng nguyên thủy hiệp biến” theo nghĩa `int[]` gán thành `long[]` hoặc `Object[]`. Sự hiệp biến ở đây diễn ra ở **tầng ngoài**, nơi kiểu phần tử `int[]` là một kiểu tham chiếu.

## 7. So sánh với generic `List` và cách phòng tránh

Java generic thông thường **bất biến** (*invariant*):

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Java");

// java.util.List<Object> objects = names;
// Không biên dịch: List<String> không là subtype của List<Object>.

java.util.List<? extends Object> readable = names;
System.out.println(readable.getClass().getSimpleName()); // ArrayList.
~~~

Một tham chiếu `List<? extends Object>` cho phép **đọc** phần tử như `Object` nhưng không tùy tiện `add(new Object())` vào danh sách có kiểu phần tử chưa biết (ngoài `null`). Điều này chặn sớm loại thao tác vốn có thể gây lỗi runtime khi làm với mảng hiệp biến.

**Gợi ý thiết kế:**

- Nếu API chỉ **đọc dữ liệu**, tránh sửa phần tử trong phương thức nhận `Object[]`; dùng kiểu tham số cụ thể hoặc abstraction chỉ đọc phù hợp.
- Nếu API cần **ghi**, dùng mảng với kiểu thành phần đúng, hoặc dùng `List<T>` cùng hợp đồng generic rõ ràng.
- Khi đã có `Object[] view` nhưng cần biết mảng thật sự nhận được kiểu gì, kiểm tra nguồn và `view.getClass().getComponentType()` trong lúc gỡ lỗi; **không** dùng kiểm tra để thay thế thiết kế kiểu đúng.
- Một đối tượng mảng nhận được qua cast, method parameter hoặc `clone` không tự chuyển kiểu thành phần runtime.
- `final Object[] view` chỉ cấm **gán lại biến view**, không cấm thay phần tử của đối tượng mảng; lỗi `ArrayStoreException` vẫn có thể xảy ra.

Nếu cần sao chép từ `String[]` vào một mảng có kiểu runtime `Object[]`, tạo mảng thật sự mới:

~~~java
String[] source = {"A", "B"};
Object[] flexible = java.util.Arrays.copyOf(
        source, source.length, Object[].class);
flexible[0] = Integer.valueOf(99); // Hợp lệ: mảng runtime là Object[].
~~~

`Arrays.copyOf(..., Object[].class)` trả mảng mới kiểu `Object[]`, khác `source.clone()` vốn duy trì kiểu runtime `String[]`.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo file **CovariantArrayDemo.java**:

~~~java
import java.util.Arrays;

public final class CovariantArrayDemo {
    private static void replaceFirst(Object[] target, Object value) {
        target[0] = value; // Có thể ném ArrayStoreException tại runtime.
    }

    public static void main(String[] args) {
        String[] words = {"A", "B"};
        Object[] view = words;
        System.out.println("sameArray=" + (view == words));
        System.out.println("actualComponent="
                + view.getClass().getComponentType().getTypeName());

        view[1] = "BB";
        view[0] = null; // null luôn hợp lệ cho phần tử tham chiếu.
        System.out.println("validWrites=" + Arrays.toString(words));

        try {
            replaceFirst(view, Integer.valueOf(7));
        } catch (ArrayStoreException ex) {
            System.out.println("stringReject=ArrayStoreException");
        }
        System.out.println("afterReject=" + Arrays.toString(words));

        Object[] general = new Object[1];
        general[0] = Integer.valueOf(42);
        System.out.println("objectAccept=" + general[0]);

        Number[] numbers = new Integer[2];
        numbers[0] = Integer.valueOf(5);
        try {
            numbers[1] = Double.valueOf(1.5);
        } catch (ArrayStoreException ex) {
            System.out.println("numberReject=ArrayStoreException");
        }
        System.out.println("numbersAfter=" + Arrays.toString(numbers));

        String[] cloned = words.clone();
        System.out.println("cloneDifferent=" + (cloned != words));
        System.out.println("cloneComponent="
                + cloned.getClass().getComponentType().getTypeName());
        try {
            ((Object[]) cloned)[0] = Integer.valueOf(8);
        } catch (ArrayStoreException ex) {
            System.out.println("cloneReject=ArrayStoreException");
        }

        String[][] names = {{"A", "B"}, {"C"}};
        Object[][] grid = names;
        Object[] firstRow = grid[0];
        firstRow[1] = "BB";
        System.out.println("innerValid=" + Arrays.toString(names[0]));
        try {
            firstRow[0] = Integer.valueOf(9);
        } catch (ArrayStoreException ex) {
            System.out.println("innerReject=ArrayStoreException");
        }
        try {
            grid[1] = new Object[] {"X"};
        } catch (ArrayStoreException ex) {
            System.out.println("outerReject=ArrayStoreException");
        }
        System.out.println("afterOuterReject=" + Arrays.deepToString(names));

        grid[1] = new String[] {"OK"};
        System.out.println("outerValid=" + Arrays.deepToString(names));

        int[][] primitiveRows = new int[2][];
        Object[] rowView = primitiveRows;
        rowView[0] = new int[] {1, 2};
        System.out.println("intRow=" + Arrays.toString(primitiveRows[0]));
        try {
            rowView[1] = new long[] {3L};
        } catch (ArrayStoreException ex) {
            System.out.println("primitiveRowReject=ArrayStoreException");
        }
        System.out.println("secondRowNull=" + (primitiveRows[1] == null));

        Object primitiveAsObject = new int[] {5};
        System.out.println("primitiveIsObjectArray="
                + (primitiveAsObject instanceof Object[]));

        Object[] flexible = Arrays.copyOf(
                words, words.length, Object[].class);
        flexible[0] = Integer.valueOf(99);
        System.out.println("flexible=" + Arrays.toString(flexible));
        System.out.println("sourceUnchanged=" + Arrays.toString(words));

        try {
            String[] badCast = (String[]) new Object[1];
            System.out.println(badCast.length);
        } catch (ClassCastException ex) {
            System.out.println("badCast=ClassCastException");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 CovariantArrayDemo.java
java CovariantArrayDemo
~~~

**Expected stdout chính xác:**

~~~text
sameArray=true
actualComponent=java.lang.String
validWrites=[null, BB]
stringReject=ArrayStoreException
afterReject=[null, BB]
objectAccept=42
numberReject=ArrayStoreException
numbersAfter=[5, null]
cloneDifferent=true
cloneComponent=java.lang.String
cloneReject=ArrayStoreException
innerValid=[A, BB]
innerReject=ArrayStoreException
outerReject=ArrayStoreException
afterOuterReject=[[A, BB], [C]]
outerValid=[[A, BB], [OK]]
intRow=[1, 2]
primitiveRowReject=ArrayStoreException
secondRowNull=true
primitiveIsObjectArray=false
flexible=[99, BB]
sourceUnchanged=[null, BB]
badCast=ClassCastException
~~~

Ví dụ bắt riêng các ngoại lệ để kết quả chạy ổn định. Dòng `stringReject` cho thấy lỗi sau khi gán `String[]` vào biến `Object[]`; `innerReject` và `outerReject` thể hiện hai cấp kiểm tra kiểu trong `String[][]`; `primitiveRowReject` minh họa mảng ngoài của `int[][]` cũng là mảng **tham chiếu**; `flexible` chứng minh cách tạo mảng thực sự có kiểu `Object[]`.

## 9. Lỗi thường gặp và bài tập

| Lỗi/hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `Object[] view = new String[2]` tạo `Object[]` mới | Không: đối tượng thật vẫn là `String[]` |
| Biên dịch được `view[0] = 7` thì chắc chạy được | Không: JVM kiểm tra kiểu phần tử thực lúc ghi |
| `ArrayStoreException` xảy ra lúc khai báo alias | Không: xảy ra khi cố **ghi** phần tử không tương thích |
| Gán `null` vào `String[]` gây `ArrayStoreException` | Không: `null` hợp lệ với mọi kiểu tham chiếu |
| `int[]` là subtype của `Object[]` | Không; chỉ `int[]` là một `Object` |
| `int[][]` không thể gán thành `Object[]` | Sai: thành phần của mảng ngoài là `int[]`, một kiểu tham chiếu |
| `String[][]` gán thành `Object[][]` là tạo bản sao | Không; vẫn dùng cùng đối tượng mảng nhiều chiều |
| `clone()` của `String[]` tạo mảng `Object[]` | Không: kiểu mảng runtime được giữ nguyên |
| `ArrayStoreException` và `ClassCastException` giống nhau | Không: một lỗi lúc **ghi mảng**, một lỗi **ép kiểu** không hợp lệ |
| `List<String>` gán được cho `List<Object>` | Không: generic thông thường bất biến |

**Bài 1.** Tạo `String[] source = {"a"}; Object[] alias = source;`. Thử ghi `"b"`, `null` và `Integer.valueOf(2)`. Ghi lại khi nào `ArrayStoreException` xảy ra.

**Bài 2.** Tạo `Number[] values = new Integer[2];`. Thử lần lượt lưu `Integer.valueOf(1)` và `Double.valueOf(2.0)`. Vì sao compiler chấp nhận nhưng runtime từ chối giá trị thứ hai?

**Bài 3.** Tạo `String[][] grid` có hai hàng, gán nó cho `Object[][] alias`. So sánh hành vi `alias[0][0] = 5` và `alias[0] = new Object[] {"x"}`.

**Bài 4.** Giải thích vì sao `Object[] rows = new int[2][];` hợp lệ nhưng `Object[] oneRow = new int[2];` không biên dịch.

**Bài 5.** Viết ví dụ sao chép `String[]` thành `Object[]` thực qua `Arrays.copyOf(..., Object[].class)`; chứng minh bản mới lưu được `Integer` mà không thay đổi mảng nguồn.

### Ghi nhớ

**Mảng tham chiếu trong Java hiệp biến:** `String[]` có thể được nhìn như `Object[]`, nhưng **kiểu thành phần của đối tượng mảng không đổi**. Khi ghi vào mảng, JVM kiểm tra kiểu thực và có thể ném `ArrayStoreException`. Với mảng nhiều chiều, kiểm tra xảy ra cả lúc thay **hàng** và thay **phần tử trong hàng**. Tránh API ghi vào mảng quá rộng kiểu; chọn kiểu cụ thể, tạo mảng thật sự đúng kiểu hoặc sử dụng generic `List<T>` phù hợp.
