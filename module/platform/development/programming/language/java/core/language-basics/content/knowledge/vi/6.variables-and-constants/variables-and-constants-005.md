# Giá trị mặc định của trường và phần tử mảng trong Java

> **Java core — language-basics / Biến và hằng**  
> **Yêu cầu:** JDK 17 trở lên.  
> **Mục tiêu:** Biết Java tự cấp giá trị nào cho field và phần tử mảng; phân biệt `static`/instance field, primitive/reference, mảng nhiều chiều và biến cục bộ; tránh nhầm `null` với đối tượng đã được cấp phát.

## 1. Những vị trí nào có giá trị mặc định?

Java tự khởi tạo các vị trí lưu trữ sau theo **kiểu khai báo** của chúng:

- **Instance field:** mỗi object mới có bộ field riêng, ban đầu nhận giá trị mặc định; sau đó field initializer và constructor có thể thay đổi.
- **Static field:** thuộc lớp, nhận giá trị mặc định trước khi chạy các khai báo khởi tạo và static initializer tương ứng của lớp.
- **Phần tử mảng:** ngay khi mảng mới được cấp phát bằng `new`, mọi phần tử **thực sự tồn tại** đều có giá trị mặc định. Quy tắc này đúng dù biến giữ tham chiếu mảng nằm trong method.

Ví dụ:

~~~java
class Account {
    int points;         // 0
    boolean active;     // false
    String owner;       // null
    static long total;  // 0L
}
~~~

Không cần tự viết `= 0` hoặc `= null` cho các field trên. Tuy nhiên, giá trị mặc định chỉ là **trạng thái ban đầu**; nếu có initializer hoặc constructor gán lại, giá trị được nhìn thấy sau khi tạo object sẽ khác.

## 2. Bảng giá trị mặc định theo kiểu

| Kiểu field / phần tử | Giá trị mặc định | Diễn giải |
| --- | --- | --- |
| `byte`, `short`, `int` | `0` | Số nguyên không |
| `long` | `0L` | Số nguyên không kiểu `long` |
| `float` | `0.0f` | Số thực dương 0.0 |
| `double` | `0.0d` | Số thực dương 0.0 |
| `char` | `'\u0000'` | Mã UTF-16 bằng 0 (NUL), **không phải** ký tự `'0'` hoặc dấu cách |
| `boolean` | `false` | Giá trị logic sai |
| Mọi **kiểu tham chiếu** | `null` | Chưa có object được tham chiếu |

Kiểu tham chiếu gồm `String`, các class khác, interface và **chính kiểu mảng** như `int[]`. Vì vậy `String[]` chứa phần tử mặc định `null`, chứ không tự tạo `""`. `Integer[]` chứa `null`, **không** tự tạo các wrapper `Integer.valueOf(0)`.

Khi in trực tiếp ký tự mặc định của `char`, bạn khó quan sát được vì nó là NUL. Hãy ép sang `int` để thấy mã **0**: `System.out.println((int) character);`.

## 3. Chương trình Java 17+ độc lập

Tạo file **DefaultValuesDemo.java**:

~~~java
import java.util.Arrays;

public class DefaultValuesDemo {
    static int sharedCount;
    static boolean enabled;

    int quantity;
    double price;
    char initial;
    String label;

    public static void main(String[] args) {
        DefaultValuesDemo first = new DefaultValuesDemo();
        DefaultValuesDemo second = new DefaultValuesDemo();

        int[] scores = new int[3];
        boolean[] flags = new boolean[2];
        char[] letters = new char[1];
        String[] names = new String[2];
        Integer[] wrappers = new Integer[1];

        int[][] partial = new int[2][];
        int[][] complete = new int[2][3];

        System.out.println("static=" + sharedCount + "," + enabled);
        System.out.println("instance=" + first.quantity + ","
                + first.price + "," + (int) first.initial + ","
                + first.label);
        System.out.println("scores=" + Arrays.toString(scores));
        System.out.println("flags=" + Arrays.toString(flags));
        System.out.println("charCode=" + (int) letters[0]);
        System.out.println("names=" + Arrays.toString(names));
        System.out.println("wrapper=" + wrappers[0]);
        System.out.println("partialRow=" + partial[0]);
        System.out.println("completeRow="
                + Arrays.toString(complete[0]));

        first.quantity = 7;
        scores[0] = 9;
        System.out.println("objects=" + first.quantity + ","
                + second.quantity);
        System.out.println("scoresAfter=" + Arrays.toString(scores));
    }
}
~~~

Mở terminal tại thư mục chứa file rồi chạy (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 DefaultValuesDemo.java
java DefaultValuesDemo
~~~

**Expected output:**

~~~text
static=0,false
instance=0,0.0,0,null
scores=[0, 0, 0]
flags=[false, false]
charCode=0
names=[null, null]
wrapper=null
partialRow=null
completeRow=[0, 0, 0]
objects=7,0
scoresAfter=[9, 0, 0]
~~~

Giải thích: field `static` có giá trị 0/false; mỗi object `DefaultValuesDemo` mới có field `quantity` bằng 0, `price` bằng 0.0, `initial` bằng NUL và `label` bằng `null`. Các mảng primitive mới có phần tử 0/false/NUL, trong khi mảng `String` và `Integer` có phần tử `null`.

Sau phép gán `first.quantity = 7`, object `second` vẫn giữ `quantity = 0`: mỗi object có field instance riêng. Sau `scores[0] = 9`, hai vị trí còn lại của mảng vẫn là 0.

## 4. Mảng nhiều chiều: chỉ khởi tạo các mảng thật sự được cấp phát

Hãy phân biệt:

~~~java
int[][] partial = new int[2][];
int[][] complete = new int[2][3];
~~~

- `partial` là **mảng ngoài gồm hai tham chiếu kiểu `int[]`**; hai tham chiếu ấy mặc định `null` vì chưa cấp phát hàng con. Do đó `partial[0]` là `null`.
- `complete` đã cấp phát mảng ngoài và hai hàng con `int[3]`. Sáu phần tử số nguyên đều mặc định bằng **0**.
- Nếu chạy `partial[0][0]` trước khi gán `partial[0] = new int[3];`, chương trình sẽ gặp `NullPointerException`.

Không nhầm `new int[0]` với mảng `null`: `new int[0]` là một object mảng **có độ dài 0**, nhưng không có phần tử nào để đọc giá trị mặc định.

## 5. Biến cục bộ KHÔNG có giá trị mặc định để đọc

Đây là ngoại lệ quan trọng với người mới học. Biến cục bộ bên trong phương thức phải được **gán chắc chắn trước khi đọc** (*definite assignment*):

~~~java
void example() {
    int count;
    // System.out.println(count); // Lỗi biên dịch nếu bỏ comment.
    count = 3;
    System.out.println(count); // 3
}
~~~

Không có quy tắc “biến cục bộ `int` chưa gán sẽ đọc ra 0”. Compiler có thể báo `variable count might not have been initialized`.

Tuy nhiên, **mảng được tạo từ một biến cục bộ** vẫn được gán giá trị mặc định cho từng phần tử:

~~~java
int[] values = new int[2];
System.out.println(values[0]); // 0
~~~

Ở đây biến cục bộ `values` đã được gán tham chiếu tới mảng mới; còn `values[0]` nhận giá trị mặc định 0 từ cơ chế cấp phát mảng. Hai quy tắc không mâu thuẫn.

## 6. Khởi tạo tường minh và `final`

Với field initializer/constructor, giá trị cuối sau khi tạo object có thể khác mặc định:

~~~java
class Ticket {
    int count = 5;

    Ticket() {
        count = 8;
    }
}
~~~

Khi đọc `new Ticket().count` sau constructor, giá trị là **8**. Trước các gán tường minh, cơ chế khởi tạo mặc định đã thiết lập 0.

Field `final` chưa có initializer (blank final) vẫn phải được gán theo quy tắc *definite assignment* thích hợp, ví dụ trong constructor:

~~~java
class Product {
    final int id;

    Product(int id) {
        this.id = id;
    }
}
~~~

`final` ngăn gán lại field sau khi khởi tạo hợp lệ, nhưng không biến object được giữ qua một tham chiếu `final` thành bất biến. Nó cũng không khiến phần tử mảng tự có giá trị khác mặc định.

## 7. Bẫy thường gặp và luyện tập

| Tình huống | Hiểu đúng |
| --- | --- |
| `String[] a = new String[2];` | Các phần tử là **`null`**, không phải `""` |
| `Integer[] a = new Integer[2];` | Các phần tử là `null`; unbox `a[0]` sang `int` gây `NullPointerException` |
| `int[] a = new int[2];` | Hai số 0 |
| `int[][] a = new int[2][];` | Hai hàng chưa cấp phát, đều `null` |
| `int[][] a = new int[2][3];` | Hai hàng đã cấp phát, sáu số 0 |
| `char` mặc định | NUL với mã 0, không phải ký tự in được `'0'` |
| `String label;` là field | `null`; gọi `label.length()` trước khi gán object có thể gây `NullPointerException` |

**Bài tập 1:** Tạo class có field `byte`, `float`, `char`, `boolean`, `String` chưa gán. In giá trị; với `char`, ép sang `int` để xác nhận mã 0.

**Bài tập 2:** In `Arrays.toString(new String[3])`. Sau đó gán phần tử thứ hai thành `"Java"` và in lại: phần tử nào vẫn `null`?

**Bài tập 3:** Tạo `int[][] rows = new int[2][];`. Dự đoán `rows[0]`; sau đó gán `rows[0] = new int[2];` rồi in `rows[0][0]`.

**Bài tập 4:** Giải thích vì sao `int local; System.out.println(local);` không biên dịch, nhưng `int[] array = new int[1]; System.out.println(array[0]);` in 0.

### Ghi nhớ

**Field và phần tử mảng** có giá trị mặc định theo kiểu: primitive nhận giá trị 0/0.0/`false`/NUL tương ứng; tham chiếu nhận `null`. **Biến cục bộ phải được gán chắc chắn trước khi đọc.** Các gán ở initializer, constructor và sau khi cấp phát có thể thay đổi giá trị mặc định.
