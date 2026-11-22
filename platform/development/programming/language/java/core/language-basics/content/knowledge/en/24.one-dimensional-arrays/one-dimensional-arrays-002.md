# Khai báo biến mảng và tạo mảng bằng `new` — Java 17+

## 1. Phân biệt khai báo biến và tạo đối tượng mảng

Trong Java, **mảng (array)** là một đối tượng có độ dài cố định, chứa các phần tử cùng kiểu thành phần. Biến kiểu mảng giữ **tham chiếu** đến đối tượng mảng, chứ không tự chứa các phần tử chỉ vì đã được khai báo.

~~~java
int[] scores;           // Chỉ khai báo biến tham chiếu mảng.
scores = new int[3];    // Tạo đối tượng mảng ba phần tử và gán tham chiếu.
scores[0] = 10;         // Truy cập phần tử đầu tiên.
~~~

Có thể gộp khai báo và cấp phát:

~~~java
int[] scores = new int[3];
~~~

| Cú pháp | Điều gì xảy ra? |
|---|---|
| `int[] scores;` | Khai báo biến cục bộ có kiểu `int[]`; **chưa có mảng được tạo** |
| `new int[3]` | Cấp phát đối tượng mảng `int` có **3 phần tử**; trả tham chiếu |
| `scores = new int[3];` | Gán tham chiếu tới mảng mới cho biến `scores` |
| `scores[0] = 10;` | Thay giá trị ở chỉ số 0 trong mảng mà `scores` trỏ tới |
| `scores.length` | Đọc độ dài mảng, ở đây là `3` |

**Ghi nhớ:** *khai báo biến* và *tạo mảng* là hai thao tác khác nhau. Từ khóa `new` thực hiện việc tạo đối tượng mảng khi chạy.

## 2. Cú pháp khai báo được khuyến nghị

Java ưu tiên cách viết **ngoặc vuông ở kiểu**:

~~~java
int[] numbers;
String[] names;
double[] temperatures;
boolean[] flags;
~~~

Java cũng chấp nhận phong cách cũ:

~~~java
int numbers[];
~~~

Tuy nhiên, `int[] numbers` dễ đọc hơn vì thể hiện rõ kiểu biến là **mảng của int**.

Một bẫy khi khai báo nhiều biến:

~~~java
int[] first, second; // Cả first lẫn second đều là int[].

int third[], count;  // third là int[]; count là int.
~~~

Vì vậy, thường nên dùng **một khai báo trên một dòng** để tránh hiểu nhầm kiểu.

Dấu `[]` biểu thị **kiểu mảng**, không phải kích thước. Độ dài được chỉ định ở biểu thức cấp phát `new int[3]`, không phải trong kiểu khai báo:

~~~java
int[] data = new int[3]; // Đúng.
// int[3] data;           // Sai cú pháp Java.
~~~

## 3. Tạo mảng bằng `new ElementType[size]`

~~~java
int[] scores = new int[3];
String[] labels = new String[2];
boolean[] enabled = new boolean[2];
double[] prices = new double[2];
~~~

`size` là biểu thức kiểu số nguyên phù hợp và được đánh giá **khi chạy**. Giá trị phải không âm:

~~~java
int size = 2 + 1;
int[] values = new int[size];   // length = 3.
int[] empty = new int[0];       // Hợp lệ: mảng rỗng.
~~~

`new int[-1]` là biểu thức có thể biên dịch, nhưng khi thực thi sẽ ném `NegativeArraySizeException`. Kích thước không âm vẫn không bảo đảm đủ bộ nhớ; yêu cầu cấp phát quá lớn có thể gặp `OutOfMemoryError`.

Mảng có **độ dài cố định sau khi tạo**. Không gán được `values.length = 5`; muốn độ dài khác, phải tạo một mảng mới (chẳng hạn qua `Arrays.copyOf`) rồi dùng tham chiếu tới mảng mới.

## 4. Sau `new`, phần tử đã có giá trị mặc định

`new int[3]` tạo **một mảng** có ba vị trí; giá trị ở từng vị trí ban đầu là `0`. Với `boolean[]`, mặc định là `false`; với `char[]`, là NUL (mã 0); với `String[]`, `Student[]` hoặc các mảng tham chiếu khác, mặc định là **`null`**, không tự gọi constructor từng đối tượng.

~~~java
int[] numbers = new int[2];         // [0, 0]
String[] names = new String[2];      // [null, null]
System.out.println(java.util.Arrays.toString(numbers));
System.out.println(java.util.Arrays.toString(names));
~~~

Biến cục bộ `int[] ref;` **chưa được gán** nên không được đọc ngay; khác với phần tử của mảng đã cấp phát. Quy tắc chi tiết của cả tám kiểu nguyên thủy và các kiểu tham chiếu được giải thích riêng ở bài về giá trị mặc định.

## 5. Chỉ số và `length` của đối tượng vừa tạo

Với `new int[3]`, `length == 3` nhưng chỉ số hợp lệ là `0`, `1`, `2`. `length` là **trường**, không có dấu `()`; không thể sửa để nới dài chính mảng ấy.

~~~java
int[] scores = new int[3];
scores[0] = 10;
scores[2] = 30;
System.out.println(scores.length); // 3
// scores[3] = 40; // Nếu thực thi: ArrayIndexOutOfBoundsException.
~~~

Kiểm tra `0 <= i && i < scores.length` trước khi đọc/ghi theo chỉ số do người dùng cung cấp. Đây là giới hạn của mảng đã tồn tại, khác với lỗi `NegativeArraySizeException` khi **tạo** mảng với kích thước âm.

Sau khi phân biệt khai báo và cấp phát, chương trình sau áp dụng thêm các tình huống liên quan để bạn tự quan sát trạng thái của mảng đã tạo.

## 6. Chương trình Java 17+ chạy độc lập

Lưu file tên **`ArrayDeclarationNewDemo.java`**:

~~~java
import java.util.Arrays;

public final class ArrayDeclarationNewDemo {
    private ArrayDeclarationNewDemo() {}

    static void show(String name, int[] array) {
        System.out.println(name + " length=" + array.length
                + " values=" + Arrays.toString(array));
    }

    public static void main(String[] args) {
        int[] numbers;             // Khai báo, chưa tạo mảng.
        numbers = new int[3];      // Tạo ba phần tử mặc định bằng 0.
        show("new", numbers);

        numbers[0] = 10;
        numbers[2] = 30;
        show("updated", numbers);

        int[] empty = new int[0];
        show("empty", empty);

        int[] initializer = {2, 4, 6};
        show("initializer", initializer);

        int[] explicit = new int[]{7, 8};
        show("explicit", explicit);

        int size = 2 + 1;
        int[] computed = new int[size];
        show("computed", computed);

        String[] labels = new String[2];
        boolean[] flags = new boolean[2];
        double[] prices = new double[2];
        System.out.println("labels=" + Arrays.toString(labels));
        System.out.println("flags=" + Arrays.toString(flags));
        System.out.println("prices=" + Arrays.toString(prices));

        int[] alias = numbers;
        alias[1] = 20;
        show("shared", numbers);
        System.out.println("same object=" + (numbers == alias));

        int[] independent = numbers.clone();
        independent[0] = 99;
        show("original", numbers);
        show("clone", independent);
        System.out.println("clone distinct=" + (numbers != independent));

        int[] extended = Arrays.copyOf(numbers, 5);
        show("extended", extended);
        show("original again", numbers);

        int[] missing = null;
        System.out.println("null ref=" + (missing == null));
        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("null length=NullPointerException");
        }

        try {
            int[] bad = new int[-1];
            System.out.println(bad.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negative size=NegativeArraySizeException");
        }

        try {
            System.out.println(empty[0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("empty index=ArrayIndexOutOfBoundsException");
        }
    }
}
~~~

**Bash (Linux/macOS), yêu cầu JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ArrayDeclarationNewDemo.java
java -cp . ArrayDeclarationNewDemo
~~~

**PowerShell (Windows), yêu cầu JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayDeclarationNewDemo.java
java -cp . ArrayDeclarationNewDemo
~~~

### Exact expected stdout

~~~text
new length=3 values=[0, 0, 0]
updated length=3 values=[10, 0, 30]
empty length=0 values=[]
initializer length=3 values=[2, 4, 6]
explicit length=2 values=[7, 8]
computed length=3 values=[0, 0, 0]
labels=[null, null]
flags=[false, false]
prices=[0.0, 0.0]
shared length=3 values=[10, 20, 30]
same object=true
original length=3 values=[10, 20, 30]
clone length=3 values=[99, 20, 30]
clone distinct=true
extended length=5 values=[10, 20, 30, 0, 0]
original again length=3 values=[10, 20, 30]
null ref=true
null length=NullPointerException
negative size=NegativeArraySizeException
empty index=ArrayIndexOutOfBoundsException
~~~

**Đối chiếu:** `new int[3]` tạo các số 0; gán giá trị cập nhật phần tử nhưng không đổi `length`. Alias tác động cùng mảng; clone tạo mảng `int[]` khác; `copyOf` tạo mảng dài 5, để mảng gốc dài 3. Ba lỗi/trường hợp biên `null`, kích thước âm, đọc mảng rỗng được bắt riêng và in nhãn ổn định, không dựa vào thông điệp ngoại lệ của JDK.

## 7. Lỗi phổ biến khi mới học mảng

| Sai lầm | Vấn đề | Cách đúng |
|---|---|---|
| `int[] a;` rồi đọc `a.length` | Local chưa gán | `a = new int[3];` trước khi đọc |
| Cho rằng `int[] a = null;` tạo mảng rỗng | `null` không có object | `new int[0]` để tạo mảng rỗng |
| Viết `int[3] a;` | Sai vị trí kích thước | `int[] a = new int[3];` |
| `a.length()` | `length` không phải method | `a.length` |
| Truy cập `a[a.length]` | Chỉ số cuối là `length-1` | Kiểm tra `0 <= i && i < a.length` |
| Tạo `new int[-1]` | `NegativeArraySizeException` | Kiểm tra kích thước không âm |
| `new int[2]{1, 2}` | Không được ghi kích thước với initializer | `new int[]{1, 2}` |
| `a = {1,2};` sau khi khai báo | Initializer rút gọn không dùng ở đây | `a = new int[]{1,2};` |
| Nghĩ `int[] b = a;` sao chép phần tử | Hai biến chia sẻ cùng mảng | `a.clone()` hoặc `Arrays.copyOf` |
| Nghĩ `new Student[2]` tạo hai Student | Chỉ tạo mảng hai tham chiếu null | Tạo riêng từng object `Student` |
| Nghĩ có thể đổi `a.length` | Mảng có độ dài cố định | Tạo mảng mới độ dài mong muốn |

## 8. Bài tập có đáp án

**A.** Khai báo một biến kiểu mảng `double[]` và cấp phát 4 phần tử.  
**Đáp án:**

~~~java
double[] temperatures = new double[4];
~~~

Giá trị mặc định mỗi phần tử là `0.0`.

**B.** Vì sao `int[] a;` không thể gọi ngay `a.length`?  
**Đáp án:** mới chỉ khai báo biến cục bộ, chưa được gán tham chiếu tới mảng; compiler áp dụng quy tắc *definite assignment*.

**C.** `int[] a = new int[0];` có hợp lệ không và `a.length` bằng bao nhiêu?  
**Đáp án:** hợp lệ, `a.length == 0`; nhưng không có phần tử `a[0]`.

**D.** Sau đoạn mã dưới, `a[1]` là bao nhiêu?

~~~java
int[] a = {3, 4};
int[] b = a;
b[1] = 8;
~~~

**Đáp án:** `8`, vì `a` và `b` cùng trỏ một mảng.

**E.** Viết lại cho đúng phép gán mảng có sẵn biến:

~~~java
int[] a;
a = new int[]{5, 6};
~~~

**Đáp án:** đoạn trên đã đúng. `a = {5,6};` mới là cú pháp sai.

**F.** Với `String[] names = new String[2];`, có hai đối tượng String mới được tạo sẵn không?  
**Đáp án:** không. Mảng có hai phần tử tham chiếu, mỗi phần tử mặc định `null`.

## 9. Checklist và kết luận

- [ ] Biết `int[] x;` **chỉ khai báo tham chiếu mảng**, không tạo object.
- [ ] Biết `new int[n]` tạo một đối tượng mảng dài `n`.
- [ ] Dùng `int[]` thay cho cú pháp gây hiểu nhầm `int a[]`.
- [ ] Hiểu giá trị mặc định của phần tử mảng mới.
- [ ] Phân biệt biến local chưa gán, tham chiếu `null` và mảng rỗng.
- [ ] Đọc `length` và truy cập chỉ số hợp lệ từ 0 đến `length-1`.
- [ ] Tạo mảng bằng initializer `{...}` và `new int[]{...}` đúng ngữ cảnh.
- [ ] Biết việc gán `b = a` chia sẻ tham chiếu, không sao chép phần tử.
- [ ] Biết mảng cố định độ dài, muốn đổi độ dài phải tạo mảng mới.
- [ ] Phân biệt lỗi kích thước âm với lỗi truy cập chỉ số.
- [ ] Chạy `ArrayDeclarationNewDemo.java` trên JDK 17+ và đối chiếu exact stdout.

**Kết luận:** **Khai báo mảng** tạo một biến kiểu tham chiếu; **`new ElementType[size]`** mới tạo đối tượng mảng với độ dài cố định và các phần tử có giá trị mặc định. Hiểu rõ hai bước này là nền tảng để xử lý `null`, mảng rỗng, chỉ số và sao chép mảng trong Java.