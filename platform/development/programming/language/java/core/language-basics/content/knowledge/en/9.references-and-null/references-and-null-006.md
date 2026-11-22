# `==` trên tham chiếu kiểm tra cùng đối tượng — Java 17+

## 1. Mục tiêu: “cùng đối tượng” khác “cùng nội dung”

Trong Java, toán tử `==` có ý nghĩa khác nhau tùy **kiểu toán hạng**:

- Với **giá trị nguyên thủy** (*primitive*), `==` so sánh giá trị theo quy tắc của loại primitive tương ứng.
- Với **hai tham chiếu có thể so sánh được**, `==` trả `true` khi **cả hai tham chiếu cùng chỉ tới một đối tượng**, hoặc **đều là `null`**. Nó không tự so sánh từng field, từng ký tự hoặc từng phần tử mảng.

~~~java
int x = 10;
int y = 10;
System.out.println(x == y); // true: cùng giá trị int

String first = new String("Java");
String second = new String("Java");
System.out.println(first == second);      // false: hai object khác nhau
System.out.println(first.equals(second)); // true: cùng nội dung chuỗi
~~~

**Trọng tâm:** `==` trên tham chiếu trả lời câu hỏi **“hai biến này có đang chỉ đến đúng cùng một object không?”**, chứ không phải **“hai object có dữ liệu giống nhau không?”**.

Để giữ ví dụ dễ kiểm chứng, bài dùng Java 17+, class tự định nghĩa, chuỗi, mảng và `record` để phân biệt **object identity** và **value equality**.

## 2. Mỗi biến tham chiếu giữ một giá trị tham chiếu

Xét class:

~~~java
static final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}
~~~

Trong một method:

~~~java
Box a = new Box(10);
Box alias = a;
Box b = new Box(10);

System.out.println(a == alias); // true
System.out.println(a == b);     // false
~~~

Tại sao?

1. `new Box(10)` lần đầu tạo một instance, rồi gán tham chiếu của instance đó cho `a`.
2. `alias = a` **sao chép tham chiếu**, không gọi `new`, nên `alias` và `a` cùng chỉ vào instance ban đầu.
3. `new Box(10)` lần thứ hai tạo **instance khác**, nên `b` không cùng identity với `a`, dù `a.value` và `b.value` đều bằng `10`.

Sơ đồ minh họa quan hệ, **không phải địa chỉ bộ nhớ**:

~~~mermaid
flowchart LR
  A["a"] --> X["Box #1: value = 10"]
  C["alias"] --> X
  B["b"] --> Y["Box #2: value = 10"]
~~~

| Biểu thức | Kết quả | Lý do |
|---|---|---|
| `a == alias` | `true` | Hai tham chiếu cùng object |
| `a == b` | `false` | Hai lần `new` tạo hai Box riêng |
| `a.value == b.value` | `true` | Hai field `int` có cùng giá trị |
| `alias == b` | `false` | Hai object khác nhau |

**Không có quy tắc “field giống nhau thì `==` true”** đối với tham chiếu.


## 3. Khi nào alias ảnh hưởng phép so identity?

`Box alias = a;` khiến `a == alias` là `true`; sửa `alias.value` không đổi kết quả vì cả hai vẫn trỏ một object. Sau `alias = new Box(99);`, phép so thành `false` dù `a` không bị sửa. Đây là quan hệ giữa **giá trị tham chiếu hiện tại** và identity, độc lập với việc hai object có field giống nhau.

## 4. `null`: trường hợp hai tham chiếu đều không trỏ object

`null` là giá trị tham chiếu đặc biệt thể hiện **không trỏ đến object nào**.

~~~java
Box first = null;
Box second = null;
Box actual = new Box(5);

System.out.println(first == second); // true
System.out.println(first == actual); // false
System.out.println(actual != null);  // true
~~~

**Điểm quan trọng:** `null == null` cho `true` theo nghĩa so sánh tham chiếu, **không** có nghĩa Java tạo ra “một object null” để cả hai cùng trỏ tới.

Kiểm tra `null` trước khi dereference là một trường hợp đúng và phổ biến để dùng `==`:

~~~java
static void printBox(Box box) {
    if (box == null) {
        System.out.println("No box");
        return;
    }
    System.out.println(box.value);
}
~~~

Còn:

~~~java
Box box = null;
// System.out.println(box.value); // Nếu thực thi sẽ có NullPointerException
~~~

thì truy cập field qua tham chiếu `null` gây lỗi lúc chạy.

**Phân biệt với biến cục bộ chưa gán**:

~~~java
Box box;
// System.out.println(box == null); // Lỗi compile: box chưa gán giá trị
box = null;
System.out.println(box == null); // true
~~~

Việc khai báo `Box box;` không tự khởi tạo biến cục bộ bằng `null`. Quy tắc **definite assignment** vẫn áp dụng.

## 5. `String`: vì sao nên so nội dung bằng `equals`

Với dữ liệu văn bản, ý định thường là so sánh **nội dung**:

~~~java
String a = new String("Hello");
String b = new String("Hello");

System.out.println(a == b);      // false: hai String instance riêng
System.out.println(a.equals(b)); // true: cùng nội dung ký tự
~~~

**`String.equals`** được class String định nghĩa để so sánh các dãy ký tự tương ứng. Nó khác toán tử `==` trên tham chiếu.

### Bẫy string pool

~~~java
String a = "Java";
String b = "Java";

System.out.println(a == b); // true
~~~

Hai **string literal giống hệt nhau** được *intern* theo quy tắc của Java, vì vậy trong ví dụ này chúng trỏ đến cùng một `String` đã được intern.

Nhưng **không được lấy kết quả `true` đó làm cách kiểm tra nội dung** trong code tổng quát:

~~~java
String literal = "Java";
String created = new String("Java");

System.out.println(literal == created);      // false
System.out.println(literal.equals(created)); // true
~~~

`new String("Java")` tạo object String mới; nội dung vẫn là `Java`, nhưng identity khác với literal được intern.

**Thực hành:** dùng `equals` khi muốn kiểm tra hai chuỗi có cùng nội dung. Khi một biến có thể `null`, cân nhắc cách so sánh an toàn:

~~~java
String input = null;

System.out.println("OK".equals(input));           // false
System.out.println(java.util.Objects.equals(input, "OK")); // false
~~~

Đừng gọi `input.equals(...)` khi `input` có thể `null`; lời gọi method trên null gây `NullPointerException`.

## 6. `equals()` không phải toán tử `==`

`==` là toán tử ngôn ngữ Java. Ngược lại, `equals(Object)` là một **method** khai báo trong `java.lang.Object`, và class có thể **override** để đưa ra tiêu chí so sánh nội dung.

~~~java
static final class NumberBox {
    final int number;

    NumberBox(int number) {
        this.number = number;
    }
}

NumberBox a = new NumberBox(7);
NumberBox b = new NumberBox(7);

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false: chưa override equals
~~~

Nếu class **không override `equals`**, implementation mặc định từ `Object` chỉ trả true cho cùng object. Không nên mặc định rằng `equals` luôn so các field.

Nếu nghiệp vụ cần so sánh theo giá trị, có thể tự định nghĩa `equals`/`hashCode` cho class, hoặc dùng kiểu đã hỗ trợ value equality phù hợp.

### `record` trong Java 17: ví dụ value equality rõ ràng

~~~java
record Point(int x, int y) {}

Point p = new Point(1, 2);
Point q = new Point(1, 2);
Point alias = p;

System.out.println(p == q);       // false
System.out.println(p.equals(q));  // true
System.out.println(p == alias);   // true
~~~

Một `record` đơn giản tự cung cấp `equals` và `hashCode` dựa trên các thành phần của record. Nhưng **`==` vẫn so identity**, không đổi thành phép so nội dung chỉ vì kiểu là `record`.

> **Lưu ý:** `equals` theo thành phần của record không tự làm các thành phần tham chiếu mutable trở nên bất biến hoặc buộc so sánh mảng theo nội dung. Với một record chứa mảng, cần đặc biệt chú ý vì `equals` của mảng mặc định so identity.

## 7. Mảng: cùng phần tử chưa chắc cùng đối tượng mảng

~~~java
int[] first = {2, 4, 6};
int[] second = {2, 4, 6};
int[] alias = first;

System.out.println(first == second); // false
System.out.println(first == alias);  // true
~~~

Mỗi khởi tạo mảng độc lập tạo một array object. Muốn **so nội dung của mảng một chiều**, dùng `java.util.Arrays.equals`:

~~~java
System.out.println(java.util.Arrays.equals(first, second)); // true
~~~

Với mảng lồng nhau, có thể cần `Arrays.deepEquals` nếu cấu trúc phù hợp.

Tương tự các object khác, `first.equals(second)` của array **không tự so từng phần tử**; `Object.equals` mặc định là so identity.

**Không nhầm** `Arrays.equals` với `==`: API so nội dung sẽ xem từng phần tử theo quy tắc của loại mảng, còn `==` trên tham chiếu chỉ xác định một object duy nhất hay không.

## 8. Wrapper, autoboxing và caching: không dùng `==` để so giá trị

Kiểu wrapper như `Integer` hoặc `Long` là **object**, không phải primitive tương ứng:

~~~java
Integer left = Integer.valueOf(500);
Integer right = Integer.valueOf(500);

System.out.println(left.equals(right)); // true
~~~

Không nên kiểm tra `left == right` với ý định so số 500: `==` trên hai biến có kiểu `Integer` so **tham chiếu** và kết quả có thể chịu ảnh hưởng của caching/triển khai API.

Một số giá trị boxed có caching được bảo đảm hoặc thường gặp nên thỉnh thoảng `==` trả `true`; đó chính là lý do bug này **khó phát hiện** nếu chỉ thử một vài giá trị nhỏ.

Phân biệt hai tình huống:

~~~java
Integer boxed = 500;
int primitive = 500;

System.out.println(boxed.equals(primitive)); // true (boxed tham số)
System.out.println(boxed == primitive);      // true (unboxing rồi so số)
~~~

Ở phép so `boxed == primitive`, một toán hạng kiểu `int` khiến wrapper được **unbox**, rồi Java thực hiện phép so số; không phải reference identity. Nếu `boxed == null`, phép unboxing trong biểu thức này có thể ném `NullPointerException`.

**Quy tắc:** đối với wrapper, nếu muốn so nội dung hãy dùng `equals`, `Objects.equals` hoặc chuyển sang primitive có kiểm soát null; đừng dựa vào identity.


## 9. Kiểm tra identity qua lời gọi method

Tham số tham chiếu được **sao chép theo giá trị**. Method có thể sửa object đang chia sẻ mà không làm thay đổi phép `==` giữa các alias; nếu method gán lại tham số bằng `new Box(...)`, tham chiếu trong biến của caller vẫn giữ nguyên. Phép kiểm tra identity phải dựa vào **tham chiếu ở thời điểm so sánh**, không dựa vào việc method đã nhận một đối số trước đó.

## 10. Bảng chọn phép so sánh

| Dữ liệu / mục tiêu | Cách kiểm tra phù hợp |
|---|---|
| Hai biến primitive `int` | `a == b` |
| Hai tham chiếu có cùng instance không | `a == b` |
| Một tham chiếu có null không | `value == null` hoặc `value != null` |
| Hai `String` có cùng nội dung | `a.equals(b)` nếu `a` chắc chắn không null |
| Hai giá trị String có thể null | `Objects.equals(a, b)` |
| Hai `int[]` có cùng phần tử | `Arrays.equals(a, b)` |
| Hai object của class tự tạo có cùng dữ liệu | Override `equals` đúng hợp đồng hoặc sử dụng kiểu value phù hợp |
| Hai giá trị wrapper `Integer` có cùng số | `Objects.equals(a, b)` hoặc `equals` khi không null |
| Hai `record` có cùng component | `equals` theo hợp đồng record |

Đây là bảng theo **ý định**, không phải cứ thấy biến là sử dụng một phép so sánh chung cho mọi loại. Với số thực `float`/`double`, còn có quy tắc riêng cho NaN, signed zero và sai số xấp xỉ; không nên kéo phép so sánh identity của tham chiếu sang bài toán số thực.

## 11. Ví dụ Java 17 hoàn chỉnh và kết quả chạy

Tạo tệp đúng tên **`ReferenceIdentityDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class ReferenceIdentityDemo {
    private ReferenceIdentityDemo() {}

    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    record Point(int x, int y) {}

    static void rebind(Box parameter) {
        parameter = new Box(999);
        System.out.println("inside parameter=" + parameter.value);
    }

    public static void main(String[] args) {
        int number1 = 10;
        int number2 = 10;
        System.out.println("primitive equal=" + (number1 == number2));

        Box first = new Box(10);
        Box alias = first;
        Box twin = new Box(10);
        System.out.println("alias identity=" + (first == alias));
        System.out.println("twin identity=" + (first == twin));
        System.out.println("field values=" + (first.value == twin.value));

        alias.value = 25;
        System.out.println("first after alias=" + first.value);
        System.out.println("twin unchanged=" + twin.value);

        alias = new Box(30);
        System.out.println("identity after rebind=" + (first == alias));
        System.out.println("first after rebind=" + first.value);

        Box absent = null;
        Box alsoAbsent = null;
        System.out.println("two null references=" + (absent == alsoAbsent));
        System.out.println("null vs object=" + (absent == first));
        System.out.println("null safe equals=" + Objects.equals(absent, alsoAbsent));

        String text1 = new String("Java");
        String text2 = new String("Java");
        String textAlias = text1;
        System.out.println("new Strings identity=" + (text1 == text2));
        System.out.println("new Strings contents=" + text1.equals(text2));
        System.out.println("String alias identity=" + (text1 == textAlias));

        String literal1 = "OK";
        String literal2 = "OK";
        System.out.println("interned literals=" + (literal1 == literal2));

        int[] array1 = {1, 2};
        int[] array2 = {1, 2};
        int[] arrayAlias = array1;
        System.out.println("arrays identity=" + (array1 == array2));
        System.out.println("arrays contents=" + Arrays.equals(array1, array2));
        System.out.println("array alias identity=" + (array1 == arrayAlias));

        Point point1 = new Point(1, 2);
        Point point2 = new Point(1, 2);
        System.out.println("records identity=" + (point1 == point2));
        System.out.println("records contents=" + point1.equals(point2));

        Integer boxed = Integer.valueOf(500);
        int primitive = 500;
        System.out.println("boxed vs primitive=" + (boxed == primitive));

        rebind(first);
        System.out.println("caller unchanged=" + first.value);
    }
}
~~~

Mở terminal trong thư mục chứa file; cần cài **JDK 17+**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ReferenceIdentityDemo.java
java -cp . ReferenceIdentityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ReferenceIdentityDemo.java
java -cp . ReferenceIdentityDemo
~~~

**Expected output chính xác:**

~~~text
primitive equal=true
alias identity=true
twin identity=false
field values=true
first after alias=25
twin unchanged=10
identity after rebind=false
first after rebind=25
two null references=true
null vs object=false
null safe equals=true
new Strings identity=false
new Strings contents=true
String alias identity=true
interned literals=true
arrays identity=false
arrays contents=true
array alias identity=true
records identity=false
records contents=true
boxed vs primitive=true
inside parameter=999
caller unchanged=25
~~~

Đầu ra tránh hash code, địa chỉ object hoặc chi tiết triển khai cache không ổn định. Những điểm nên tự đối chiếu:

- **Alias:** `first == alias` ban đầu `true`; sửa `alias.value` làm `first.value` đổi theo.
- **Gán lại:** sau `alias = new Box(30)`, `first == alias` là `false`; `first.value` vẫn `25`.
- **Null:** hai tham chiếu `null` so bằng `==` là `true`, dù không có object `null`.
- **String:** hai lần `new String` độc lập khác identity nhưng `equals` trả true.
- **Mảng:** hai array object khác nhau dù `Arrays.equals` thấy phần tử giống nhau.
- **Record:** `point1 == point2` là false, nhưng `point1.equals(point2)` là true.
- **Wrapper:** `boxed == primitive` thực hiện unboxing để so số, nên true.
- **Method:** tạo Box mới cho tham số trong `rebind` không thay đối tượng mà `first` đang trỏ.

## 12. Lỗi thường gặp

| Đoạn mã / ngộ nhận | Vấn đề | Cách khắc phục |
|---|---|---|
| `new Box(1) == new Box(1)` phải true | Hai lần `new` tạo hai object | Dùng so nội dung theo hợp đồng nếu đó là mục tiêu |
| `Box b = a` tạo bản sao Box | Gán chỉ sao chép giá trị tham chiếu | Cần cơ chế copy/create object riêng |
| Hai object có field `value` giống nhau thì `==` true | `==` không so field | So giá trị hoặc dùng `equals` được thiết kế rõ |
| `"Hi" == new String("Hi")` true vì chữ giống nhau | String literal và String tạo mới khác identity | `equals` |
| Thử hai literal trùng nhau rồi quyết định dùng `==` cho String | String pool làm kết quả gây hiểu nhầm | Dùng `String.equals` |
| `a.equals(b)` với `a == null` | Gọi method trên null ném exception | `Objects.equals(a, b)` |
| `charArray1 == charArray2` để so phần tử | `==` so array object | `Arrays.equals` |
| `Integer a == Integer b` để so số | So identity của boxed objects | Dùng `equals`/`Objects.equals` |
| `Integer boxed = null; boxed == 1` | Unboxing null gây `NullPointerException` | Kiểm tra null trước |
| Override `equals` mà mong toán tử `==` đổi hành vi | `==` không bị override | Gọi `equals` đúng chỗ |
| `rebind(parameter)` làm biến bên gọi trỏ object mới | Java pass-by-value | Trả tham chiếu mới và gán tại phía caller nếu cần |
| Nhìn `Object.toString()` rồi nghĩ đó là địa chỉ | Không có bảo đảm địa chỉ vật lý | Tư duy qua identity, không qua hash/địa chỉ |

**Cẩn thận về kiểu tĩnh:** không phải mọi cặp tham chiếu bất kỳ đều có thể viết `a == b`. Compiler yêu cầu toán hạng có kiểu cho phép kiểm tra reference equality; một số cặp kiểu không liên quan có thể bị từ chối ngay lúc biên dịch. Đừng ép kiểu bừa chỉ để cưỡng ép một so sánh không có ý nghĩa.

## 13. Bài tập tự kiểm tra (có đáp án)

### Bài A — cùng object hay cùng field?

~~~java
Box a = new Box(7);
Box b = a;
Box c = new Box(7);
System.out.println(a == b);
System.out.println(a == c);
System.out.println(a.value == c.value);
~~~

**Đáp án:**

~~~text
true
false
true
~~~

### Bài B — thay đổi alias rồi gán lại

~~~java
Box first = new Box(4);
Box second = first;
second.value = 9;
second = new Box(1);
System.out.println(first.value);
System.out.println(first == second);
~~~

**Đáp án:**

~~~text
9
false
~~~

### Bài C — hai String có nội dung giống nhau

~~~java
String a = new String("ok");
String b = new String("ok");
System.out.println(a == b);
System.out.println(a.equals(b));
~~~

**Đáp án:**

~~~text
false
true
~~~

### Bài D — hai mảng cùng phần tử

~~~java
int[] a = {3, 4};
int[] b = {3, 4};
System.out.println(a == b);
System.out.println(java.util.Arrays.equals(a, b));
~~~

**Đáp án:**

~~~text
false
true
~~~

### Bài E — null

~~~java
Object a = null;
Object b = null;
System.out.println(a == b);
System.out.println(java.util.Objects.equals(a, b));
~~~

**Đáp án:**

~~~text
true
true
~~~

Trong ví dụ này cả hai phương pháp trả true, nhưng **không cùng bản chất**: `==` so hai giá trị tham chiếu null; `Objects.equals` là phép kiểm tra equality an toàn với null.

## 14. Checklist và kết luận

- [ ] Biết `==` trên primitive khác `==` trên tham chiếu.
- [ ] Giải thích được tại sao `new Box(1)` hai lần không tạo cùng identity.
- [ ] Biết `Box alias = first;` chỉ sao chép tham chiếu.
- [ ] Phân biệt sửa object qua alias và gán lại một biến tham chiếu.
- [ ] Hiểu `null == null` là true nhưng `null` không phải object.
- [ ] Dùng `String.equals` thay cho `==` khi so nội dung chuỗi.
- [ ] Biết string pool có thể khiến so literal bằng `==` trả true.
- [ ] Biết `Arrays.equals` cho so nội dung mảng.
- [ ] Hiểu `Object.equals` mặc định so identity khi class không override.
- [ ] Nhớ `record.equals` so component nhưng `record == record` vẫn so identity.
- [ ] Tránh dùng `==` trên hai wrapper để so giá trị, chú ý unboxing.
- [ ] Chạy `ReferenceIdentityDemo.java` bằng `javac`/`java` Java 17+ và đối chiếu toàn bộ expected output.

**Kết luận:** Khi áp dụng cho tham chiếu Java, `==` hỏi **“có cùng một object hay đều null không?”**. Nó **không** tự kiểm tra “dữ liệu bằng nhau”. Muốn so nội dung, hãy chọn API và hợp đồng equality phù hợp: `String.equals`, `Arrays.equals`, `Objects.equals` hoặc `equals` do class cung cấp.