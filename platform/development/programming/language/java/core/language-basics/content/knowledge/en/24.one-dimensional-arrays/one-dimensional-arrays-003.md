# Khởi tạo mảng bằng danh sách giá trị trong Java

> **Java core — language-basics / Mảng một chiều**  
> **Môi trường:** JDK 17+; ví dụ một file tự chứa, không dùng thư viện ngoài.  
> **Mục tiêu:** Phân biệt cú pháp `{...}` khi khai báo với `new T[]{...}` trong biểu thức, hiểu độ dài được suy ra từ số phần tử, kiểu thành phần, danh sách rỗng, thứ tự đánh giá và các lỗi biên dịch thường gặp.

## 1. Cú pháp ngắn `{...}` ngay tại khai báo

Khi **khai báo biến mảng và khởi tạo ngay trong cùng câu lệnh**, ta có thể viết các phần tử trong dấu ngoặc nhọn:

~~~java
int[] scores = {8, 10, 6};
String[] names = {"An", "Binh", "Chi"};
boolean[] flags = {true, false, true};
~~~

Java tạo đối tượng mảng mới, gán lần lượt các giá trị vào vị trí có chỉ số bắt đầu từ 0. `scores` có kiểu `int[]`, kiểu thành phần `int` và `scores.length == 3`.

~~~java
System.out.println(scores[0]); // 8
System.out.println(scores[2]); // 6
System.out.println(scores.length); // 3
~~~

Cú pháp đầy đủ tương đương:

~~~java
int[] scores = new int[] {8, 10, 6};
~~~

**Lưu ý:** Không khai báo kích thước trong `new int[] { ... }`, vì độ dài được xác định từ số biểu thức khởi tạo. Mảng đã tạo có `length` cố định; thay phần tử bằng `scores[i] = value` là hợp lệ, còn kéo dài chính đối tượng mảng là không thể.

## 2. Khi nào phải viết `new T[] {...}`?

Dạng `{...}` **đơn độc** chỉ hợp lệ trong *array initializer* gắn trực tiếp với khai báo hoặc các ngữ cảnh khởi tạo thành phần mảng thích hợp. Khi biểu thức cần tạo mảng mới trong phép gán sau khai báo, đối số phương thức hoặc giá trị `return`, hãy ghi rõ `new T[] { ... }`.

~~~java
int[] values;
values = new int[] {2, 4, 6};      // ĐÚNG.

static int total(int[] numbers) {
    int sum = 0;
    for (int number : numbers) {
        sum += number;
    }
    return sum;
}

// Gọi:
// int result = total(new int[] {1, 2, 3});
// result == 6.
~~~

Phương thức trả về mảng:

~~~java
static int[] createPair() {
    return new int[] {4, 6};
}
~~~

Các dạng sau **không biên dịch** (chỉ minh họa, không đưa vào chương trình chạy):

~~~java
// int[] a;
// a = {1, 2};                   // Thiếu "new int[]" ở phép gán.
// total({1, 2});                // Thiếu "new int[]" ở đối số.
// int[] wrong = new int[2] {1, 2}; // Vừa chỉ kích thước vừa khởi tạo.
~~~

Bảng ghi nhớ:

| Ngữ cảnh | Cú pháp hợp lệ |
| --- | --- |
| Khai báo + khởi tạo | `int[] a = {1, 2};` |
| Khai báo + khởi tạo tường minh | `int[] a = new int[] {1, 2};` |
| Gán lại sau khai báo | `a = new int[] {3, 4};` |
| Đối số phương thức nhận `int[]` | `method(new int[] {1, 2});` |
| Trả về `int[]` | `return new int[] {1, 2};` |
| Khai báo có số phần tử, chưa ghi giá trị | `new int[2]` (nhận hai số 0 mặc định) |

## 3. Số phần tử, mảng rỗng và dấu phẩy cuối

**Số biểu thức trong danh sách quyết định chiều dài mảng**, không phụ thuộc vào giá trị của phần tử.

~~~java
int[] three = {5, 5, 5}; // length = 3.
int[] empty = {};        // length = 0.
int[] two = {7, 9,};     // Dấu phẩy sau phần tử cuối là hợp lệ.
~~~

Dấu phẩy cuối có thể hữu ích khi chỉnh sửa danh sách nhiều dòng. Nó **không tạo thêm phần tử**.

`new int[] {}` và `new int[0]` đều tạo một đối tượng mảng dài 0; chúng không phải `null`:

~~~java
int[] nothing = {};
System.out.println(nothing.length); // 0
// nothing[0]; // Nếu truy cập: ArrayIndexOutOfBoundsException.
~~~

Giá trị mặc định khác với giá trị khai báo rõ ràng:

~~~java
int[] defaults = new int[3]; // [0, 0, 0]
int[] given = {0, 0, 0};     // [0, 0, 0]
~~~

Hai mảng trên có cùng **nội dung khởi đầu**, nhưng là **hai đối tượng khác nhau**. Không dùng `==` để so sánh nội dung mảng; khi cần có thể dùng `java.util.Arrays.equals(defaults, given)`.

## 4. Quy tắc kiểu thành phần

Mỗi phần tử phải **tương thích với kiểu thành phần** theo quy tắc gán của Java:

~~~java
long[] distances = {1, 2, 3};    // Hợp lệ: int -> long.
double[] rates = {1, 2.5, 3};    // Hợp lệ: giá trị số phù hợp.
String[] words = {"A", null, "C"}; // Hợp lệ: tham chiếu String hoặc null.
Object[] items = {"text", Integer.valueOf(7), null};
~~~

Một mảng tham chiếu vẫn có **một kiểu thành phần**, nhưng có thể chứa nhiều lớp đối tượng runtime nếu đều gán được cho kiểu đó: `Object[]` ở trên chứa `String`, `Integer` và `null`.

Ví dụ sai:

~~~java
// int[] wrong = {1, "two"}; // String không gán được cho int.
// String[] wrong2 = {"A", Integer.valueOf(2)}; // Integer không là String.
~~~

Một số hằng nguyên `int` nằm trong phạm vi của kiểu nhỏ hơn có thể được gán qua *constant narrowing*; nhưng hằng vượt miền thì không:

~~~java
byte[] bytes = {0, 127}; // Hợp lệ.
// byte[] wrong = {128}; // Không biên dịch: vượt miền byte.
~~~

Với mảng kiểu tham chiếu, kiểu thành phần thực còn được kiểm tra khi lưu giá trị ở **runtime** (ví dụ `String[]` gán qua `Object[]` có thể ném `ArrayStoreException` nếu cố lưu một `Integer`). Danh sách khởi tạo không bỏ qua cơ chế kiểm tra kiểu này.

## 5. Danh sách chứa biểu thức và thứ tự đánh giá

Mỗi phần tử không bắt buộc là literal. Java có thể đánh giá các biến, biểu thức số học và lời gọi phương thức **từ trái sang phải** trong danh sách:

~~~java
int base = 4;
int[] computed = {base, base * 2, base + 5};
// computed = [4, 8, 9].
~~~

Ví dụ có hiệu ứng phụ để thấy rõ thứ tự:

~~~java
static int counter = 0;

static int next() {
    counter++;
    return counter * 10;
}

// Trong một phương thức:
// int[] values = {next(), next(), next()};
// values = [10, 20, 30]; counter = 3.
~~~

Lưu ý rằng nếu một biểu thức ném ngoại lệ, các phần tử còn lại chưa được đánh giá sẽ không được khởi tạo qua các biểu thức đó. Trong mã ứng dụng, hạn chế side effects phức tạp bên trong danh sách khởi tạo để dễ đọc và dễ kiểm thử.

## 6. `var`, tham chiếu và thay đổi mảng sau khi khởi tạo

Java 17 hỗ trợ suy luận kiểu của biến cục bộ bằng `var` khi biểu thức bên phải có kiểu rõ ràng:

~~~java
var numbers = new int[] {2, 4, 6}; // Suy ra int[].
// var wrong = {2, 4, 6};          // Không biên dịch.
~~~

Không có kiểu đích đủ rõ từ riêng `{...}`, nên không viết `var numbers = { ... };`. Với mã nhập môn, `int[] numbers = { ... };` thường ngắn và rõ nhất.

Danh sách khởi tạo **tạo đối tượng mảng mới**, nhưng giá trị của mảng vẫn có thể được cập nhật:

~~~java
int[] a = {2, 4};
a[0] = 9; // a thành [9, 4].

int[] alias = a;
alias[1] = 7; // a thành [9, 7], vì alias trỏ cùng mảng.

a = new int[] {1, 3, 5}; // a trỏ mảng mới, dài 3.
// alias vẫn trỏ mảng cũ [9, 7], dài 2.
~~~

Để sao chép thành một mảng khác, dùng `a.clone()` hoặc `Arrays.copyOf(...)`. Với mảng tham chiếu chứa đối tượng mutable, cách sao chép này chỉ sao chép **tham chiếu phần tử**, không sao chép sâu các đối tượng.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **ArrayInitializerDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayInitializerDemo {
    private static int counter = 0;

    private static int next() {
        counter++;
        return counter * 10;
    }

    private static int total(int[] values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    private static int[] createPair() {
        return new int[] {4, 6};
    }

    public static void main(String[] args) {
        int[] numbers = {2, 4, 6};
        System.out.println("declared=" + Arrays.toString(numbers));
        System.out.println("length=" + numbers.length);

        int[] empty = {};
        System.out.println("emptyLength=" + empty.length);

        int[] trailing = {8, 9,};
        System.out.println("trailing=" + Arrays.toString(trailing));

        int[] assigned;
        assigned = new int[] {3, 5};
        System.out.println("assigned=" + Arrays.toString(assigned));

        System.out.println("argumentSum="
                + total(new int[] {1, 2, 3}));
        System.out.println("returned=" + Arrays.toString(createPair()));

        int[] defaults = new int[3];
        int[] explicitZeros = {0, 0, 0};
        System.out.println("defaults=" + Arrays.toString(defaults));
        System.out.println("contentsEqual="
                + Arrays.equals(defaults, explicitZeros));
        System.out.println("sameObject=" + (defaults == explicitZeros));

        long[] widened = {1, 2, 3};
        System.out.println("longValues=" + Arrays.toString(widened));

        String[] words = {"A", null, "C"};
        System.out.println("words=" + Arrays.toString(words));

        Object[] mixed = {"x", Integer.valueOf(7), null};
        System.out.println("mixed=" + Arrays.toString(mixed));

        var inferred = new int[] {7, 8};
        System.out.println("inferredComponent="
                + inferred.getClass().getComponentType().getTypeName());

        int[] evaluated = {next(), next(), next()};
        System.out.println("evaluation=" + Arrays.toString(evaluated));
        System.out.println("calls=" + counter);

        numbers[0] = 99;
        int[] alias = numbers;
        alias[1] = 42;
        System.out.println("mutated=" + Arrays.toString(numbers));

        int[] copy = numbers.clone();
        copy[0] = 123;
        System.out.println("originalAfterCopy=" + Arrays.toString(numbers));
        System.out.println("copy=" + Arrays.toString(copy));

        numbers = new int[] {1, 3, 5};
        System.out.println("reassigned=" + Arrays.toString(numbers));
        System.out.println("aliasOld=" + Arrays.toString(alias));
    }
}
~~~

Tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ArrayInitializerDemo.java
java ArrayInitializerDemo
~~~

**Expected stdout chính xác:**

~~~text
declared=[2, 4, 6]
length=3
emptyLength=0
trailing=[8, 9]
assigned=[3, 5]
argumentSum=6
returned=[4, 6]
defaults=[0, 0, 0]
contentsEqual=true
sameObject=false
longValues=[1, 2, 3]
words=[A, null, C]
mixed=[x, 7, null]
inferredComponent=int
evaluation=[10, 20, 30]
calls=3
mutated=[99, 42, 6]
originalAfterCopy=[99, 42, 6]
copy=[123, 42, 6]
reassigned=[1, 3, 5]
aliasOld=[99, 42, 6]
~~~

Chú ý `trailing=[8, 9]` (dấu phẩy cuối không tăng độ dài), `sameObject=false` (cùng nội dung không đồng nghĩa cùng đối tượng), `calls=3` (biểu thức được đánh giá theo thứ tự) và `aliasOld` (gán lại biến không làm mảng cũ đổi chiều dài).

## 8. Lỗi thường gặp và bài tập

| Trường hợp | Cách xử lý |
| --- | --- |
| Viết `a = {1, 2};` sau khi khai báo | Dùng `a = new int[] {1, 2};` |
| Viết `method({1, 2})` | Truyền `new int[] {1, 2}` |
| Viết `new int[2] {1, 2}` | Bỏ kích thước: `new int[] {1, 2}` |
| Cho rằng `{1, 2,}` dài 3 | Dấu phẩy cuối không tạo vị trí |
| Dùng `var a = {1, 2};` | Dùng `var a = new int[] {1, 2};` |
| Trộn phần tử không tương thích | Chọn kiểu thành phần phù hợp hoặc sửa danh sách |
| Nhầm `new int[3]` với `{3}` | Một bên là ba phần tử mặc định 0; bên kia là một phần tử giá trị 3 |

**Bài 1.** Khai báo mảng `double[]` bằng `{1.5, 2.0, 3.5}` và tính tổng; kiểm tra chiều dài được suy ra.

**Bài 2.** Tạo mảng rỗng bằng hai cách `{}` và `new int[0]`; so sánh độ dài và tham chiếu.

**Bài 3.** Viết phương thức nhận `String[]`, gọi bằng `new String[] {"A", "B"}` và thử viết trực tiếp `{"A", "B"}` để nhận ra lỗi cú pháp.

**Bài 4.** Khởi tạo bằng các lời gọi có side effects; xác định thứ tự và trạng thái biến sau các phần tử.

**Bài 5.** Khai báo `int[] a = {1, 2};`, lấy `alias = a` rồi gán `a = new int[] {3, 4, 5};`. Dự đoán các giá trị và `length` của hai tham chiếu.

### Ghi nhớ

**`T[] a = {v1, v2};`** là dạng khởi tạo ngắn **ngay khi khai báo**. Khi cần tạo mảng ở ngữ cảnh biểu thức, dùng **`new T[] {v1, v2}`**. Độ dài bằng **số phần tử được liệt kê**, kiểu từng phần tử phải gán được cho kiểu thành phần, và danh sách có thể rỗng hoặc có dấu phẩy cuối. Sau khi khởi tạo, đối tượng mảng có chiều dài cố định, nhưng nội dung có thể thay đổi.
