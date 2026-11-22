# Không suy ra kiểu từ `null` hoặc danh sách khởi tạo mảng đứng riêng với `var`

> **Java core — language-basics / Suy luận với var**  
> **Phiên bản:** Java 17+ (các ví dụ `var` cục bộ yêu cầu từ Java 10).  
> **Mục tiêu:** Hiểu vì sao `var x = null` và `var values = {1, 2}` không biên dịch; nắm sự khác biệt giữa **giá trị khởi tạo** và **ngữ cảnh kiểu đích**, từ đó viết khai báo đúng mà vẫn sử dụng `var` khi biểu thức khởi tạo đã có kiểu xác định.

## 1. `var` cần một kiểu suy ra được tại thời điểm biên dịch

`var` cho phép trình biên dịch suy ra **kiểu tĩnh** của biến cục bộ từ biểu thức khởi tạo. Nó **không** phải kiểu dữ liệu động, không tự chọn `Object`, và không chờ đến runtime để đoán kiểu.

~~~java
var count = 10;           // int
var title = "Java";       // String
var numbers = new int[3]; // int[]
~~~

Sau khai báo, kiểu của biến đã cố định. Ví dụ `count = "ten";` không hợp lệ vì `count` là `int`.

Hai cách viết sau **không hợp lệ** trong Java 17:

~~~java
// KHÔNG BIÊN DỊCH:
var unknown = null;
var scores = {10, 20, 30};
~~~

Đây không phải lỗi do nội dung `null` hay số 10, 20, 30 “xấu”, mà vì **không có đủ thông tin để tạo kiểu khai báo hợp lệ** cho `var`.

## 2. Vì sao `var x = null` không hợp lệ?

`null` là giá trị có thể gán cho nhiều **kiểu tham chiếu** khác nhau như `String`, `Integer`, `int[]`, `Object`. Chỉ nhìn literal `null`, Java không thể suy ra nên khai báo biến với kiểu nào.

~~~java
// var name = null;  // Lỗi biên dịch: không thể suy ra kiểu từ null.
~~~

Khi kiểu đã được chỉ rõ, việc khởi tạo `null` hoàn toàn hợp lệ:

~~~java
String name = null;
Integer quantity = null;
int[] data = null;
~~~

Có thể cung cấp kiểu cho **chính biểu thức khởi tạo**, khiến `var` suy ra được:

~~~java
var name = (String) null;     // String
var quantity = (Integer) null; // Integer
var data = (int[]) null;      // int[]
~~~

Dù đúng cú pháp, viết `String name = null;` **thường rõ ràng hơn** `var name = (String) null;`. Không nên lạm dụng cast chỉ để né yêu cầu khai báo kiểu tường minh.

**Phân biệt:** Các cách trên chỉ tạo **tham chiếu bằng null**; chúng không tạo object `String`, `Integer` hay mảng. Gọi `name.length()` khi `name == null` vẫn gây `NullPointerException`.

## 3. Tại sao `var scores = {1, 2, 3}` không hợp lệ?

Cặp ngoặc nhọn đứng riêng `{1, 2, 3}` trong ngữ cảnh này là **array initializer**, không phải một biểu thức tự mang kiểu mảng hoàn chỉnh. Java cho phép dạng rút gọn này khi **khai báo đã có kiểu mảng rõ ràng**:

~~~java
int[] scores = {1, 2, 3};        // Hợp lệ: kiểu int[] đã có.
String[] labels = {"A", "B"};    // Hợp lệ: kiểu String[] đã có.
~~~

Còn ở câu `var scores = {1, 2, 3};`, không có kiểu mảng đích để quyết định array initializer; cú pháp này không được chấp nhận.

Hãy tạo **biểu thức tạo mảng có kiểu tường minh**:

~~~java
var scores = new int[] {1, 2, 3};     // Suy ra int[].
var labels = new String[] {"A", "B"}; // Suy ra String[].
var empty = new int[0];              // Suy ra int[].
~~~

`new int[] {1, 2, 3}` đã là **một biểu thức** với kiểu `int[]`, nên `var` có thể suy ra. Trái lại, `{1, 2, 3}` đứng một mình không phải biểu thức khởi tạo hợp lệ để dùng cùng `var`.

## 4. Bảng so sánh cú pháp hợp lệ và không hợp lệ

| Cách viết | Biên dịch? | Lý do hoặc kiểu suy ra |
| --- | --- | --- |
| `var a = null;` | **Không** | Literal `null` không xác định kiểu |
| `String a = null;` | Có | Kiểu `String` đã khai báo rõ |
| `var a = (String) null;` | Có | Kiểu suy ra `String` từ cast |
| `var a = {1, 2};` | **Không** | Array initializer không có kiểu đích |
| `int[] a = {1, 2};` | Có | Kiểu mảng `int[]` khai báo rõ |
| `var a = new int[] {1, 2};` | Có | Kiểu suy ra `int[]` từ array creation |
| `var a = new int[2];` | Có | Biểu thức có kiểu `int[]` |
| `var a = new String[] {null, "A"};` | Có | Kiểu mảng `String[]` đã xác định |
| `var grid = new int[][] {{1}, {2, 3}};` | Có | Kiểu suy ra `int[][]` |
| `var a = valueReturningString();` | Có nếu method khai báo trả `String` | Kiểu `String` suy ra từ **kiểu trả về**, dù giá trị runtime là `null` |

**Lưu ý:** Mảng có thể chứa phần tử `null` nếu đó là mảng tham chiếu. Ví dụ `new String[] {null, "A"}` vẫn có kiểu `String[]` rõ ràng; nó khác hoàn toàn với `var a = null;`.

## 5. Dữ liệu nhận về `null` vẫn có thể dùng `var`

Điểm quan trọng là **kiểu tĩnh của biểu thức**, không phải giá trị runtime:

~~~java
static String lookupName() {
    return null;
}

// Trong phương thức khác:
var name = lookupName(); // Hợp lệ: compiler biết kiểu trả về là String.
~~~

`name` có **kiểu `String`**, nhưng giá trị hiện tại bằng `null`. Java không hề phải đoán kiểu từ literal null ở đây; kiểu đã nằm trong **khai báo phương thức** `lookupName()`.

Cũng có thể suy ra kiểu từ biểu thức điều kiện nếu quy tắc kiểu của biểu thức đã xác định được:

~~~java
var selected = true ? null : "fallback"; // String, giá trị null.
var other = false ? null : "fallback";   // String, giá trị "fallback".
~~~

Ở đây sự hiện diện của nhánh `"fallback"` cung cấp kiểu tham chiếu `String` phù hợp cho biểu thức ba ngôi. Nhưng `var selected = null;` tự nó vẫn không hợp lệ.

Không nên coi cú pháp này là cách né kiểm tra null: nếu `selected == null`, gọi `selected.length()` vẫn gây `NullPointerException`.

## 6. Chương trình Java 17+ runnable

Tạo file **VarNullArrayDemo.java** với toàn bộ nội dung:

~~~java
public final class VarNullArrayDemo {
    private static String lookupName() {
        return null;
    }

    private static String describe(String text) {
        return text == null ? "(missing)" : text;
    }

    public static void main(String[] args) {
        String explicitNull = null;
        var typedNull = (String) null;
        var fromMethod = lookupName();

        System.out.println("explicitNull=" + describe(explicitNull));
        System.out.println("typedNull=" + (typedNull == null));
        System.out.println("fromMethodNull=" + (fromMethod == null));

        int[] compact = {1, 2, 3};
        var inferred = new int[] {1, 2, 3};
        var empty = new int[0];

        System.out.println("compactSum="
                + (compact[0] + compact[1] + compact[2]));
        System.out.println("inferredLength=" + inferred.length);
        System.out.println("inferredSecond=" + inferred[1]);
        System.out.println("emptyLength=" + empty.length);

        var labels = new String[] {null, "OK"};
        System.out.println("labelsLength=" + labels.length);
        System.out.println("firstLabelNull=" + (labels[0] == null));
        System.out.println("secondLabel=" + labels[1]);

        var grid = new int[][] {{1, 2}, {3, 4}};
        System.out.println("gridElement=" + grid[1][0]);

        var selected = true ? null : "fallback";
        var alternate = false ? null : "fallback";
        System.out.println("selectedNull=" + (selected == null));
        System.out.println("alternate=" + alternate);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 VarNullArrayDemo.java
java VarNullArrayDemo
~~~

**Expected output chính xác:**

~~~text
explicitNull=(missing)
typedNull=true
fromMethodNull=true
compactSum=6
inferredLength=3
inferredSecond=2
emptyLength=0
labelsLength=2
firstLabelNull=true
secondLabel=OK
gridElement=3
selectedNull=true
alternate=fallback
~~~

Giải thích:

1. `explicitNull` có kiểu `String` tường minh; `typedNull` suy ra `String` nhờ cast; `fromMethod` suy ra `String` nhờ kiểu trả về của method. Cả ba đều có thể giữ giá trị `null` tại runtime.
2. `compact` là mảng `int[]` hợp lệ vì khai báo đã nêu kiểu; `inferred` và `empty` cũng là `int[]` vì biểu thức `new int[]`/`new int[0]` cung cấp kiểu.
3. `labels` có kiểu `String[]` bất kể phần tử đầu bằng `null`. Mảng `grid` có kiểu `int[][]` và giá trị ở `grid[1][0]` là 3.
4. Hai biểu thức ba ngôi có kiểu `String` nhưng chọn các nhánh khác nhau nên một kết quả bằng `null`, một kết quả là `"fallback"`.

## 7. Sửa lỗi khai báo một cách có chủ đích

Khi cần khởi tạo **null**:

~~~java
// Sai:
// var token = null;

// Đúng và rõ ràng:
String token = null;

// Hợp lệ nhưng thường kém rõ hơn:
var castToken = (String) null;
~~~

Khi cần khởi tạo **mảng**:

~~~java
// Sai:
// var points = {4, 8};

// Đúng nếu muốn dùng dạng { ... } rút gọn:
int[] points = {4, 8};

// Đúng nếu muốn dùng var:
var otherPoints = new int[] {4, 8};
~~~

Đừng nhầm array initializer với *collection literal*: Java 17 không có cú pháp `var numbers = {1, 2};` để tự suy ra `List<Integer>` hay `int[]`. Nếu muốn `List`, dùng API phù hợp như `List.of(1, 2)` (trường hợp cần list bất biến) và hiểu rõ kiểu trả về cùng đặc tính của collection.

Khi review code, tự hỏi **“Biểu thức khởi tạo này có kiểu tĩnh xác định được không?”**. Nếu không, viết **kiểu khai báo tường minh** hoặc dùng **biểu thức tạo object/mảng đã nêu kiểu** thay vì cố buộc `var` phải đoán.

## 8. Các bẫy cần tránh

| Hiểu lầm | Điều đúng trong Java 17 |
| --- | --- |
| “`var` luôn suy ra `Object` khi không biết kiểu.” | Sai: compiler từ chối nếu không suy ra được kiểu hợp lệ |
| “Giá trị `null` ở runtime khiến `var` lỗi.” | Sai: `var x = lookupName();` hợp lệ nếu return type rõ |
| “`var x = (String) null;` tạo đối tượng String.” | Sai: tham chiếu vẫn `null` |
| “`{1, 2}` đứng riêng đã là `int[]`.” | Sai: cần kiểu mảng đích hoặc cú pháp `new int[] {...}` |
| “`new String[] {null}` không thể suy ra kiểu.” | Sai: `String[]` có sẵn trong biểu thức array creation |
| “Dùng `var` thì có thể gán lại bất kỳ kiểu nào.” | Sai: kiểu đã cố định ở compile time |
| “`new int[] {1, 2}` là `List<Integer>`.” | Sai: nó là mảng primitive `int[]` |

## 9. Bài tập tự kiểm tra

**Bài 1.** Giải thích riêng nguyên nhân hai dòng `var a = null;` và `var b = {1, 2};` không hợp lệ. Chúng có cùng loại thiếu thông tin kiểu hay không?

**Bài 2.** Sửa `var name = null;` theo hai cách: khai báo kiểu tường minh, hoặc tạo một biểu thức initializer có kiểu `String`. Cách nào rõ hơn khi code thật?

**Bài 3.** Sửa `var values = {2, 4, 6};` theo hai cách: dùng `int[]` với array initializer rút gọn, hoặc dùng `var` với `new int[]`.

**Bài 4.** Viết `var names = new String[] {null, "A"};`. Biến `names` có kiểu gì? `names[0] == null` cho kết quả gì? Câu trả lời có liên quan gì tới việc suy ra kiểu từ literal null?

**Bài 5.** Viết method trả `String` nhưng đôi khi trả `null`, rồi khai báo `var result = method();`. Vì sao dòng này vẫn biên dịch được dù giá trị trả về có thể vắng mặt?

### Ghi nhớ

**`var` cần một biểu thức khởi tạo có kiểu tĩnh suy ra được.** Literal `null` đứng một mình không cung cấp kiểu; array initializer `{...}` đứng một mình cần kiểu mảng đích nên không hợp lệ với `var`. Dùng `String x = null;` hoặc `var x = (String) null;` khi cần tham chiếu null có kiểu, và dùng `int[] x = {...};` hoặc `var x = new int[] {...};` khi cần mảng. `var` chỉ thay cách **viết khai báo**, không làm Java thành ngôn ngữ kiểu động.
