# Giá trị mặc định của phần tử nguyên thủy và tham chiếu trong mảng Java

> **Java core — language-basics / Mảng một chiều**  
> **Áp dụng:** Java 17+ (JDK); một chương trình chạy độc lập bằng `javac`/`java`.  
> **Mục tiêu:** Biết chính xác giá trị mà mỗi phần tử nhận được sau `new Type[length]`; phân biệt mảng của kiểu nguyên thủy với mảng của kiểu tham chiếu; nhận ra `null`, phần tử chưa gán tường minh và biến cục bộ chưa khởi tạo.

## 1. Khi tạo mảng, các phần tử được khởi tạo tự động

Một mảng Java là **đối tượng có độ dài cố định** và chứa các phần tử cùng kiểu thành phần. Khi tạo mảng bằng `new` có độ dài, mọi phần tử đều được khởi tạo về **giá trị mặc định của kiểu thành phần** trước khi chương trình đọc chúng:

~~~java
int[] numbers = new int[3];
System.out.println(numbers.length); // 3
System.out.println(numbers[0]);     // 0
System.out.println(numbers[1]);     // 0
System.out.println(numbers[2]);     // 0
~~~

Câu lệnh `new int[3]` tạo ba phần tử được đánh chỉ số `0`, `1` và `2`. Không cần viết vòng lặp để gán từng phần tử bằng 0. Đây là **bảo đảm của ngôn ngữ Java**, không phải hành vi may rủi của bộ nhớ.

**Lưu ý:** Giá trị mặc định phụ thuộc vào **kiểu của phần tử**, không phụ thuộc vào tên mảng, tên biến hoặc kiểu dữ liệu mà bạn dự định gán vào sau này. Việc dùng `new` ở đây tạo mảng mới; việc khai báo một biến tham chiếu mảng **chưa tạo mảng** là tình huống khác.

## 2. Bảng giá trị mặc định của tám kiểu nguyên thủy

Nếu kiểu thành phần của mảng là kiểu nguyên thủy (*primitive*), phần tử ban đầu có giá trị sau:

| Kiểu phần tử | Ví dụ tạo mảng | Giá trị mặc định mỗi phần tử |
| --- | --- | --- |
| `byte` | `new byte[2]` | `0` |
| `short` | `new short[2]` | `0` |
| `int` | `new int[2]` | `0` |
| `long` | `new long[2]` | `0L` (số 0 kiểu `long`) |
| `float` | `new float[2]` | `0.0f` (dương không) |
| `double` | `new double[2]` | `0.0d` (dương không) |
| `char` | `new char[2]` | ký tự có mã Unicode **0**, thường biểu diễn bằng `'\0'` |
| `boolean` | `new boolean[2]` | `false` |

Những ký hiệu `0L`, `0.0f`, `0.0d` mô tả **giá trị và kiểu**, không phải chuỗi văn bản tự chứa trong mảng. Các giá trị số 0.0 mặc định là **dương không** (`+0.0`), không phải `NaN`.

~~~java
long[] counts = new long[2];
boolean[] flags = new boolean[2];
char[] letters = new char[2];

System.out.println(counts[0] == 0L);   // true
System.out.println(flags[0]);          // false
System.out.println((int) letters[0]);  // 0
System.out.println(letters[0] == '\0'); // true
~~~

**Đặc biệt với `char`:** mặc định là ký tự NUL mang mã 0, **không** phải ký tự số '0' (mã Unicode 48), **không** phải dấu cách (mã 32) và **không** phải chữ `null`. Nếu in trực tiếp ký tự NUL, mắt người có thể không thấy gì; hãy dùng ép kiểu `(int) letters[0]` để quan sát giá trị mã.

`boolean[]` nhận `false`; `false` không đồng nghĩa số nguyên 0 và Java không cho đổi qua lại trực tiếp giữa `boolean` và `int` như một số ngôn ngữ khác.

## 3. Mảng kiểu tham chiếu: mỗi phần tử mặc định là `null`

Với kiểu thành phần là **tham chiếu** như `String`, `Integer` hoặc lớp tự định nghĩa, phần tử mặc định là `null`:

~~~java
String[] names = new String[3];
Integer[] scores = new Integer[2];

System.out.println(names[0] == null);  // true
System.out.println(scores[0] == null); // true
~~~

Điều này có nghĩa:

- **Bản thân mảng** `names` đã tồn tại vì đã thực hiện `new String[3]`, nên `names.length` bằng 3.
- Nhưng từng **phần tử tham chiếu** như `names[0]` vẫn là `null` cho đến khi được gán tham chiếu phù hợp.
- `new String[3]` **không tự tạo ba đối tượng `String` rỗng**, cũng không đặt các phần tử thành `""`.
- `new Student[2]` **không tự gọi constructor `Student` hai lần**; nó tạo mảng chứa hai tham chiếu `null`.

Ví dụ khác biệt giữa kiểu nguyên thủy và *wrapper*:

~~~java
int[] primitive = new int[2];
Integer[] boxed = new Integer[2];
boolean[] primitiveFlags = new boolean[2];
Boolean[] boxedFlags = new Boolean[2];

System.out.println(primitive[0]);        // 0
System.out.println(boxed[0]);            // null
System.out.println(primitiveFlags[0]);   // false
System.out.println(boxedFlags[0]);       // null
~~~

`Integer` và `Boolean` là **lớp tham chiếu**, không phải `int` và `boolean`. Vì vậy không được giả định phần tử `Integer[]` mặc định bằng 0 hoặc phần tử `Boolean[]` mặc định bằng `false`.

Nếu cố *unbox* một phần tử `Integer[]` đang `null` thành `int`, Java sẽ ném `NullPointerException`.

## 4. Đọc, gán phần tử và xử lý `null` đúng cách

Sau khi tạo mảng, phần tử đã có giá trị mặc định và có thể **đọc** ngay nếu chỉ số hợp lệ:

~~~java
String[] words = new String[3];
System.out.println(words[0]); // In dòng chữ null.

words[1] = "Java";
words[2] = "";
System.out.println(words[1].length()); // 4
System.out.println(words[2].length()); // 0
~~~

`null` và chuỗi rỗng `""` khác nhau: chuỗi rỗng là **một đối tượng `String` có độ dài 0**, còn `null` biểu thị không có đối tượng được tham chiếu.

Đọc trực tiếp `words[0]` hoặc so sánh `words[0] == null` là hợp lệ. Nhưng gọi phương thức instance như `words[0].length()` khi phần tử đó `null` sẽ gây `NullPointerException`.

~~~java
static int safeLength(String[] words, int index) {
    String value = words[index]; // Yêu cầu words khác null và index hợp lệ.
    return value == null ? -1 : value.length();
}
~~~

Hàm `safeLength` trả `-1` để biểu thị phần tử `null` theo hợp đồng ví dụ; nó **không** xử lý mảng `words == null` hoặc chỉ số ngoài phạm vi. Trong ứng dụng, hãy xác định rõ cần phân biệt null, chuỗi rỗng và lỗi chỉ số như thế nào.

**Gán giá trị tường minh** thay thế mặc định tại vị trí đó:

~~~java
int[] numbers = new int[3];       // [0, 0, 0]
numbers[1] = 7;                   // [0, 7, 0]

String[] words = new String[3];   // [null, null, null]
words[1] = "Java";                // [null, Java, null]
~~~

Việc gán `numbers[1]` không thay đổi `numbers[0]` hay `numbers[2]`. Những phần tử chưa được gán tường minh tiếp tục giữ giá trị mặc định cho đến khi có thao tác thay đổi.

## 5. Khởi tạo theo danh sách, `Arrays.fill` và mảng rỗng

Nếu đã biết toàn bộ giá trị ngay lúc tạo, có thể khởi tạo bằng **danh sách**:

~~~java
int[] points = {4, 5, 6};
String[] labels = {"A", null, "C"};
~~~

Ở đây các phần tử lần lượt nhận **giá trị từ danh sách**, không phải chỉ còn giá trị mặc định. Cú pháp thay thế hợp lệ trong biểu thức là `new int[] {4, 5, 6}`.

Nếu muốn mọi phần tử có **cùng giá trị khác mặc định**, có thể dùng `java.util.Arrays.fill`:

~~~java
int[] offsets = new int[3]; // Ban đầu [0, 0, 0].
java.util.Arrays.fill(offsets, -1);
// Bây giờ [-1, -1, -1].
~~~

`Arrays.fill` là thao tác gán **sau khi mảng được tạo**, không làm thay đổi quy tắc giá trị mặc định của Java.

**Mảng độ dài 0** cũng là một đối tượng mảng hợp lệ:

~~~java
int[] empty = new int[0];
System.out.println(empty.length);  // 0
System.out.println(empty == null); // false
// System.out.println(empty[0]);    // Nếu chạy: ArrayIndexOutOfBoundsException.
~~~

Mảng độ dài 0 **không có phần tử**, nên không có giá trị mặc định nào để đọc ở chỉ số 0; khác với một biến tham chiếu mảng bằng `null`.

## 6. Không nhầm phần tử mảng với biến cục bộ chưa khởi tạo

Đây là khác biệt quan trọng trong Java:

~~~java
static void valid() {
    int[] data = new int[2]; // Biến data được gán một tham chiếu mảng mới.
    System.out.println(data[0]); // 0: phần tử mảng đã có mặc định.
}
~~~

Trong khi đó, một **biến cục bộ** không tự được gán giá trị mặc định để có thể đọc ngay:

~~~java
// KHÔNG BIÊN DỊCH nếu bỏ comment:
// static void invalid() {
//     int number;
//     System.out.println(number); // Biến local chưa được gán.
//
//     String[] names;
//     System.out.println(names);  // Biến local names chưa được gán.
// }
~~~

Chú ý hai tầng:

| Tình huống | Có giá trị đọc ngay? | Giải thích |
| --- | --- | --- |
| `int[] data = new int[2]; data[0]` | Có: `0` | Phần tử mảng được mặc định hóa |
| `String[] data = new String[2]; data[0]` | Có: `null` | Phần tử là tham chiếu |
| `int n;` trong phương thức, đọc `n` ngay | Không | Local chưa đạt *definite assignment* |
| `int[] data;` trong phương thức, đọc `data` ngay | Không | Biến tham chiếu local chưa được gán |
| `int[] data = null; data.length` | Không chạy thành công | `data` được gán `null`, gọi `length` gây `NullPointerException` |
| Trường `int number;` trong đối tượng | Có: `0` | Field cũng có giá trị mặc định |
| Trường `String text;` trong đối tượng | Có: `null` | Field tham chiếu mặc định `null` |

**Scope** chỉ xác định tên dùng được ở đâu; **definite assignment** mới xác định biến cục bộ đã được gán chắc chắn trước khi đọc chưa. Giá trị mặc định của **phần tử trong một mảng đã tạo** không thể được dùng để biện minh cho việc đọc một **biến cục bộ chưa khởi tạo**.

## 7. Chương trình Java 17+ độc lập và stdout chính xác

Tạo file **ArrayDefaultValuesDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayDefaultValuesDemo {
    private static final class Student {
        private final String name;

        Student(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        byte[] bytes = new byte[2];
        short[] shorts = new short[2];
        int[] integers = new int[3];
        long[] longs = new long[2];
        float[] floats = new float[2];
        double[] doubles = new double[2];
        char[] chars = new char[2];
        boolean[] flags = new boolean[2];

        System.out.println("byte=" + Arrays.toString(bytes));
        System.out.println("short=" + Arrays.toString(shorts));
        System.out.println("int=" + Arrays.toString(integers));
        System.out.println("long=" + Arrays.toString(longs));
        System.out.println("float=" + Arrays.toString(floats));
        System.out.println("double=" + Arrays.toString(doubles));
        System.out.println("boolean=" + Arrays.toString(flags));
        System.out.println("charCodes=" + (int) chars[0] + "," + (int) chars[1]);
        System.out.println("charIsNul=" + (chars[0] == '\0'));

        String[] words = new String[3];
        Integer[] boxed = new Integer[2];
        Boolean[] boxedFlags = new Boolean[2];
        Student[] students = new Student[2];

        System.out.println("wordsInitial=" + Arrays.toString(words));
        System.out.println("boxedInitial=" + Arrays.toString(boxed));
        System.out.println("boxedFlagsInitial=" + Arrays.toString(boxedFlags));
        System.out.println("studentsInitial=" + Arrays.toString(students));
        System.out.println("arrayExists=" + (words != null));
        System.out.println("firstWordNull=" + (words[0] == null));

        integers[1] = 7;
        words[1] = "Java";
        boxed[0] = 42;
        students[0] = new Student("Lan");

        System.out.println("intAfter=" + Arrays.toString(integers));
        System.out.println("wordsAfter=" + Arrays.toString(words));
        System.out.println("boxedAfter=" + Arrays.toString(boxed));
        System.out.println("firstStudent=" + students[0].name());
        System.out.println("secondStudentNull=" + (students[1] == null));

        int[] filled = new int[3];
        Arrays.fill(filled, -1);
        System.out.println("filled=" + Arrays.toString(filled));

        int[] explicit = {4, 5};
        System.out.println("explicit=" + Arrays.toString(explicit));

        int[] empty = new int[0];
        System.out.println("emptyLength=" + empty.length);
        System.out.println("emptyIsNull=" + (empty == null));

        try {
            System.out.println("badLength=" + words[0].length());
        } catch (NullPointerException ex) {
            System.out.println("nullElement=NullPointerException");
        }

        try {
            System.out.println("badIndex=" + empty[0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("emptyIndex=ArrayIndexOutOfBoundsException");
        }

        int[] missing = null;
        System.out.println("missingArrayNull=" + (missing == null));
    }
}
~~~

Biên dịch rồi chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ArrayDefaultValuesDemo.java
java ArrayDefaultValuesDemo
~~~

**Expected stdout chính xác:**

~~~text
byte=[0, 0]
short=[0, 0]
int=[0, 0, 0]
long=[0, 0]
float=[0.0, 0.0]
double=[0.0, 0.0]
boolean=[false, false]
charCodes=0,0
charIsNul=true
wordsInitial=[null, null, null]
boxedInitial=[null, null]
boxedFlagsInitial=[null, null]
studentsInitial=[null, null]
arrayExists=true
firstWordNull=true
intAfter=[0, 7, 0]
wordsAfter=[null, Java, null]
boxedAfter=[42, null]
firstStudent=Lan
secondStudentNull=true
filled=[-1, -1, -1]
explicit=[4, 5]
emptyLength=0
emptyIsNull=false
nullElement=NullPointerException
emptyIndex=ArrayIndexOutOfBoundsException
missingArrayNull=true
~~~

Ví dụ dùng `Arrays.toString(...)` để nhìn rõ các phần tử. Riêng `char[]` được in dưới dạng **mã số** để ký tự NUL không bị nhầm là chuỗi rỗng. `Student[]` bắt đầu bằng hai `null`; chỉ khi gán `new Student("Lan")` vào vị trí 0 thì một đối tượng `Student` mới xuất hiện.

Hai `catch` có đầu ra cố định minh họa **lỗi truy cập phần tử null** và **lỗi chỉ số trên mảng rỗng**, không phụ thuộc vào nội dung thông báo ngoại lệ của JVM.

## 8. Lỗi thường gặp, cách kiểm tra và bài tập

| Hiểu nhầm hoặc lỗi | Cách hiểu đúng |
| --- | --- |
| `new String[3]` tạo 3 chuỗi rỗng | Sai: tạo 3 phần tử tham chiếu `null` |
| `new Integer[3]` tạo 3 số nguyên bằng 0 | Sai: `Integer` là lớp, phần tử là `null` |
| `new boolean[2]` có `null` | Sai: `boolean` nguyên thủy, mặc định `false` |
| `new char[2]` có ký tự `'0'` | Sai: mặc định ký tự NUL có mã 0 |
| Truy cập phần tử `null` qua `.length()` | Có thể gây `NullPointerException` |
| Mảng mới nhưng có độ dài 0 thì bằng `null` | Sai: vẫn là đối tượng, nhưng không có phần tử |
| Local `int number;` tự mặc định thành 0 | Sai: phải gán trước khi đọc |
| `new Student[2]` gọi constructor cho từng `Student` | Sai: chỉ tạo mảng tham chiếu, chưa tạo từng đối tượng |
| Cần giá trị ban đầu khác mặc định cho mọi phần tử | Dùng vòng lặp, danh sách khởi tạo hoặc `Arrays.fill` phù hợp |
| Đọc `data[0]` khi `data == null` | Không có mảng để đánh chỉ số; gây `NullPointerException` |

**Bài 1.** Tạo `double[] temperatures = new double[4]`, in từng phần tử và giải thích vì sao chúng là `0.0`.

**Bài 2.** Tạo `char[] symbols = new char[3]`, in `(int) symbols[0]` và so sánh `symbols[0] == '0'` với `symbols[0] == '\0'`.

**Bài 3.** Tạo `Integer[] ids = new Integer[2]` và `int[] indexes = new int[2]`. Dự đoán `ids[0]` và `indexes[0]`; thử gán `ids[0] = 9` rồi in lại.

**Bài 4.** Tạo lớp `Book` có constructor nhận tiêu đề; khai báo `Book[] books = new Book[2]`. Tại sao `books[0].title()` chưa gọi được trước khi `books[0] = new Book("Java")`?

**Bài 5.** So sánh `int[] a = new int[0]`, `int[] b = null` và `int[] c = new int[1]` về `length`, `== null` và khả năng đọc `[0]`.

**Bài 6.** Tạo `int[] values = new int[5]`, dùng `Arrays.fill(values, -1)` rồi cập nhật riêng `values[2] = 10`. Dự đoán toàn bộ mảng.

### Ghi nhớ

**Mỗi phần tử của mảng vừa tạo bằng `new Type[length]` đều có giá trị mặc định theo kiểu thành phần:** số nguyên là 0, số thực là +0.0, `char` là NUL (mã 0), `boolean` là `false` và **mọi kiểu tham chiếu là `null`**. Mặc định của **phần tử mảng** không phải quy tắc tự gán cho **biến cục bộ chưa khởi tạo**. Muốn đối tượng ở một phần tử tham chiếu, phải gán một tham chiếu đối tượng thích hợp.
