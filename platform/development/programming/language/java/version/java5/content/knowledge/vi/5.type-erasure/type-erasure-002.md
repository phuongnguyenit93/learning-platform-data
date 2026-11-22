# Xóa kiểu của tham số không giới hạn và tham số có giới hạn

## 1. Phân biệt tham số kiểu và kiểu đối số

Trong khai báo `class Box<T>`, `T` là **tham số kiểu (type parameter)**. Khi viết `Box<String>`, `String` là **đối số kiểu (type argument)**.

Bài này xét quy tắc xóa kiểu (type erasure) đối với tham số kiểu:

- `T` không ghi giới hạn tường minh.
- `T extends B` có một giới hạn trên.
- `T extends B & I` có nhiều giới hạn.
- Tham số kiểu của lớp và của phương thức.

Không nên nhầm `<T>` trước kiểu trả về với tham số giá trị trong dấu ngoặc. Ví dụ:

```java
static <T> T echo(T value) {
    return value;
}
```

Ở đây, `T` là tham số kiểu, còn `value` là tham số nhận giá trị khi gọi phương thức.

Xóa kiểu là cơ chế của generic Java hiện hành. Hiểu nó giúp đọc bytecode, dùng reflection và nhận ra vì sao một thay đổi giới hạn có thể tác động tới API đã biên dịch. Các ví dụ dưới đây chạy trên JDK 17 trở lên.

## 2. Quy tắc cốt lõi: xóa về giới hạn trái nhất

Có thể nhớ bằng hai bước:

1. Nếu không ghi giới hạn, tham số kiểu có giới hạn trên ngầm định là `Object`.
2. Kiểu bị xóa của một biến kiểu là kiểu bị xóa của **giới hạn nằm bên trái nhất** trong khai báo.

Vì vậy:

| Khai báo tham số kiểu | Giới hạn trái nhất | Kiểu sau xóa của tham số kiểu |
| --- | --- | --- |
| `<T>` | `Object` ngầm định | `Object` |
| `<T extends Object>` | `Object` | `Object` |
| `<N extends Number>` | `Number` | `Number` |
| `<S extends CharSequence>` | `CharSequence` | `CharSequence` |
| `<T extends Number & Comparable<T>>` | `Number` | `Number` |
| `<T extends Comparable<T>>` | `Comparable<T>` | `Comparable` |

Trong dòng cuối, giới hạn trái nhất tự nó là một kiểu có tham số. Xóa kiểu tiếp tục bỏ đối số `<T>` của `Comparable<T>`.

Đây là quy tắc của [JLS: Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6). “Không giới hạn” trong cách gọi thông thường nghĩa là không ghi giới hạn tường minh; `T` vẫn là kiểu tham chiếu với giới hạn trên `Object`.

Điều **không** xảy ra: trình biên dịch không xem từng lời gọi để tạo một bản lớp generic riêng có trường `String`, một bản có trường `Integer` và một bản có trường `Double`.

## 3. Tham số không giới hạn: T trở thành Object trong biểu diễn đã xóa

Xét lớp:

```java
class Box<T> {
    private T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Đây là lớp minh họa cho quan hệ kiểu, chưa bao gồm chương trình chạy.

Ở biểu diễn đã xóa, các vị trí dùng `T` trực tiếp được mô tả bằng `Object`:

```text
Truong value: Object
get(): Object
set(Object): void
```

Bảng trên là mô hình mô tả, không phải khuyến nghị viết lại lớp bằng kiểu thô.

Ở mã nguồn, nếu có `Box<String> box` thì:

- `box.set("hello")` hợp lệ.
- `box.set(123)` không biên dịch.
- `box.get()` được kiểm tra theo kiểu `String`.

Trình biên dịch kiểm tra generic dựa trên mã nguồn **trước khi tạo biểu diễn đã xóa**. Nó có thể chèn phép ép kiểu tại chỗ dùng kết quả để nối thông tin kiểu ở mã nguồn với kiểu trả về trong descriptor JVM.

Chẳng hạn:

```java
String text = box.get();
```

Có thể hình dung luồng thực thi:

```text
Goi get() co descriptor tra Object
        |
        v
Kiem tra ep ve String khi can
        |
        v
Gan vao bien String
```

Xóa kiểu không có nghĩa bỏ toàn bộ kiểm tra kiểu. Nó phân chia trách nhiệm: trình biên dịch kiểm tra hợp đồng generic, còn mã đã sinh sử dụng kiểu đã xóa cùng các thao tác hỗ trợ cần thiết.

## 4. Tham số có giới hạn: không phải lúc nào cũng là Object

### 4.1. Giới hạn bằng một lớp

```java
class NumberBox<N extends Number> {
    private N value;

    N get() {
        return value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`N` bị xóa về `Number`. Vì vậy, descriptor của trường `value` và kiểu trả về của `get` sử dụng `Number`.

Trong thân `asDouble`, việc gọi `doubleValue()` hợp lệ vì mọi kiểu đối số đáp ứng `N extends Number` đều có phương thức đó.

Điều này không cho phép thêm một `Double` vào mọi `NumberBox<N>`:

```java
// void wrong() {
//     value = Double.valueOf(2.5); // N co the la Integer
// }
```

Hợp đồng ở mã nguồn vẫn là `N`. Kiểu sau xóa `Number` là biểu diễn dùng trong class file, không phải quyền nới lỏng các phép gán trong mã generic.

### 4.2. Giới hạn bằng một interface

```java
static <S extends CharSequence> int lengthOf(S value) {
    return value.length();
}
```

`S` bị xóa về `CharSequence`. Giới hạn trái nhất không bắt buộc phải là một lớp.

Mô hình descriptor:

```text
lengthOf(CharSequence): int
```

Generic này vẫn có thể nhận `String` hoặc `StringBuilder`. Nếu bài toán chỉ cần độ dài và không cần liên kết `S` với vị trí kiểu nào khác, tham số thông thường `CharSequence` có thể đã đủ rõ. Không cần thêm generic chỉ để có một giới hạn.

## 5. Nhiều giới hạn: giới hạn sau vẫn có ý nghĩa

Xét phương thức:

```java
static <N extends Number & Comparable<N>> N larger(N first, N second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Kiểu hợp lệ phải đồng thời:

- Thuộc họ `Number`.
- Cài đặt `Comparable<N>`.

Giới hạn trái nhất là `Number` nên descriptor của hai đối số và kết quả sử dụng `Number`. Tuy vậy, điều kiện `Comparable<N>` vẫn được kiểm tra khi biên dịch và cho phép gọi `compareTo` trong thân phương thức.

Để gọi phương thức của giới hạn interface không nằm đầu, mã sinh có thể chứa phép `checkcast` tới interface rồi gọi phương thức qua interface. Trong ví dụ trên, `javac` tạo kiểm tra ép sang `Comparable` trước khi gọi `compareTo`.

Không nên nói “giới hạn thứ hai bị bỏ nên không còn tác dụng”. Nó không quyết định kiểu xóa chính, nhưng vẫn góp phần xác định kiểu đối số hợp lệ, khả năng truy cập thành viên và thông tin generic của khai báo.

### Thứ tự khai báo có thể tác động tới biểu diễn nhị phân

Với hai interface minh họa `Readable` và `Named`:

```text
<T extends Readable & Named> -> T bi xoa ve Readable
<T extends Named & Readable> -> T bi xoa ve Named
```

Ví dụ chỉ mô tả quy tắc thứ tự. Nếu có giới hạn bằng một lớp, lớp đó phải đứng trước các interface, chẳng hạn `Number & Comparable<N>`. Không được đảo thành `Comparable<N> & Number`.

Do giới hạn trái nhất quyết định descriptor ở các vị trí dùng `T`, đổi giới hạn đầu có thể đổi biểu diễn nhị phân dù các điều kiện trên kiểu đối số trông gần giống nhau. Khi sửa thư viện đã phát hành, cần đánh giá tương thích của các bên gọi đã biên dịch.

## 6. Chương trình đầy đủ: kiểm chứng bằng reflection

Chương trình sau đặt cạnh nhau:

- `Box<T>` không có giới hạn tường minh.
- `NumberBox<N extends Number>`.
- Phương thức generic không giới hạn, có một giới hạn và có nhiều giới hạn.
- Kiểu đã xóa và thông tin generic còn trong khai báo.

Lưu thành `ErasureBoundsDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class ErasureBoundsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class NumberBox<N extends Number> {
        private final N value;

        NumberBox(N value) {
            this.value = value;
        }

        N get() {
            return value;
        }

        double asDouble() {
            return value.doubleValue();
        }
    }

    static <T> T echo(T value) {
        return value;
    }

    static <N extends Number> N echoNumber(N value) {
        return value;
    }

    static <N extends Number & Comparable<N>> N larger(N first, N second) {
        return first.compareTo(second) >= 0 ? first : second;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Box<String> text = new Box<>("hello");
        String word = text.get();
        NumberBox<Integer> number = new NumberBox<>(42);

        System.out.println("word = " + word);
        System.out.println("number = " + number.get());
        System.out.println("double = " + number.asDouble());
        System.out.println("echo = " + echo("java"));
        System.out.println("echo number = " + echoNumber(7));
        System.out.println("larger = " + larger(4, 9));

        Field plainField = Box.class.getDeclaredField("value");
        Field numberField = NumberBox.class.getDeclaredField("value");
        System.out.println("Box.value erased = "
                + plainField.getType().getTypeName());
        System.out.println("NumberBox.value erased = "
                + numberField.getType().getTypeName());
        System.out.println("Box.value generic = "
                + plainField.getGenericType().getTypeName());

        Method plainMethod = ErasureBoundsDemo.class.getDeclaredMethod(
                "echo", Object.class);
        Method numberMethod = ErasureBoundsDemo.class.getDeclaredMethod(
                "echoNumber", Number.class);
        Method multipleMethod = ErasureBoundsDemo.class.getDeclaredMethod(
                "larger", Number.class, Number.class);

        System.out.println("echo erased return = "
                + plainMethod.getReturnType().getTypeName());
        System.out.println("echoNumber erased return = "
                + numberMethod.getReturnType().getTypeName());
        System.out.println("larger erased return = "
                + multipleMethod.getReturnType().getTypeName());
        System.out.println("larger declared bounds = "
                + Arrays.toString(
                        multipleMethod.getTypeParameters()[0].getBounds()));

        Box<Integer> integerBox = new Box<>(1);
        System.out.println("same Box class = "
                + (text.getClass() == integerBox.getClass()));
        System.out.println("stored object class = "
                + number.get().getClass().getTypeName());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -Xlint:all ErasureBoundsDemo.java
java ErasureBoundsDemo
```

Stdout:

```text
word = hello
number = 42
double = 42.0
echo = java
echo number = 7
larger = 9
Box.value erased = java.lang.Object
NumberBox.value erased = java.lang.Number
Box.value generic = T
echo erased return = java.lang.Object
echoNumber erased return = java.lang.Number
larger erased return = java.lang.Number
larger declared bounds = [class java.lang.Number, java.lang.Comparable<N>]
same Box class = true
stored object class = java.lang.Integer
```

### Cách đọc kết quả

**Trường của lớp không giới hạn:** `Field.getType()` cho thấy `Box.value` có kiểu biểu diễn `Object`.

**Trường của lớp có giới hạn:** `NumberBox.value` có kiểu biểu diễn `Number` dù đối tượng cụ thể trong chương trình là `Integer`.

**Kiểu đã xóa và metadata generic:** `getGenericType()` vẫn trả về một biểu diễn cho biến kiểu `T` ở khai báo trường. Xóa kiểu không đồng nghĩa mọi metadata generic bị xóa sạch khỏi class file.

**Phương thức:** tìm `echo` qua reflection cần `Object.class` vì đó là kiểu tham số trong biểu diễn đã xóa. Với `echoNumber` và `larger`, phải dùng `Number.class`. Truyền `Integer.class` khi tra cứu các phương thức này không khớp chữ ký khai báo đã xóa, dù lời gọi ở mã nguồn có thể nhận số nguyên.

**Nhiều giới hạn:** `larger` trả về `Number` theo `getReturnType()`, trong khi `getTypeParameters()[0].getBounds()` vẫn mô tả cả `Number` và `Comparable<N>`. API [TypeVariable.getBounds](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html#getBounds()) đọc các giới hạn của tham số kiểu được khai báo.

**Lớp của đối tượng chứa:** `Box<String>` và `Box<Integer>` dùng cùng lớp `Box` trong chương trình này.

**Lớp của đối tượng được chứa:** số `42` vẫn là đối tượng `Integer`. Xóa kiểu của `N` không biến đối tượng đó thành một đối tượng `Number` mới và cũng không làm mất lớp thực tế của nó.

Chương trình khai báo `throws ReflectiveOperationException` vì các phép tra cứu trường và phương thức có thể thất bại nếu tên hoặc chữ ký bị thay đổi. Trong ví dụ, chúng được chọn đúng theo khai báo.

## 7. Đọc descriptor bằng javap

Reflection cho một góc nhìn; `javap` cho phép xem trực tiếp class file.

Trong PowerShell hoặc shell hỗ trợ nháy đơn, chạy:

```shell
javap -p -s 'ErasureBoundsDemo$Box'
javap -p -s 'ErasureBoundsDemo$NumberBox'
javap -p -s ErasureBoundsDemo
```

Dấu nháy đơn giữ nguyên ký tự `$` trong tên lớp lồng nhau, tránh việc shell hiểu nó là biến.

Các dòng quan trọng của `Box`:

```text
private final T value;
  descriptor: Ljava/lang/Object;

T get();
  descriptor: ()Ljava/lang/Object;
```

Các dòng quan trọng của `NumberBox`:

```text
private final N value;
  descriptor: Ljava/lang/Number;

N get();
  descriptor: ()Ljava/lang/Number;
```

Các descriptor phương thức:

| Phương thức | Descriptor sau xóa |
| --- | --- |
| `echo` | `(Ljava/lang/Object;)Ljava/lang/Object;` |
| `echoNumber` | `(Ljava/lang/Number;)Ljava/lang/Number;` |
| `larger` | `(Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;` |

Trong ký hiệu descriptor:

- `L...;` biểu diễn một kiểu tham chiếu.
- Phần trong `(...)` là danh sách kiểu đối số.
- Phần sau dấu `)` là kiểu kết quả.
- `V` là `void`; `D` là `double`.

`javap` có thể in dòng khai báo dưới dạng generic nhờ metadata, đồng thời in descriptor đã xóa ngay bên dưới. Hai dòng phản ánh hai lớp thông tin khác nhau, không mâu thuẫn.

Để quan sát mã lệnh:

```shell
javap -p -c ErasureBoundsDemo
```

Trong `main`, tìm lời gọi `Box.get` trả về `Object` và lệnh `checkcast` sang `String` ngay sau đó.

Trong `larger`, tìm `checkcast` sang `Comparable` trước lời gọi `compareTo`. Không cần học thuộc offset hay số thứ tự trong constant pool; chúng có thể thay đổi khi sửa chương trình hoặc đổi trình biên dịch.

Các tùy chọn `-p`, `-s` và `-c` lần lượt giúp xem mọi thành viên, descriptor và mã lệnh theo [tài liệu javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html).

## 8. Hai trường hợp dễ tính sai kiểu sau xóa

### 8.1. Giới hạn là một tham số kiểu khác

```java
class Pair<T extends Number, U extends T> {
    T first;
    U second;
}
```

Đây là lớp minh họa độc lập:

- `T` xóa về `Number`.
- Giới hạn của `U` là `T`.
- `U` xóa về kiểu xóa của `T`, cũng là `Number`.

Không kết luận `U` xóa về `Object` chỉ vì phía sau `extends` không phải tên lớp cụ thể. Phải lần theo giới hạn.

### 8.2. Kiểu chứa tham số khác với tham số đứng trực tiếp

```java
class Holder<T extends Number> {
    T direct;
    java.util.List<T> values;
}
```

`direct` có descriptor `Number`. Nhưng `values` có descriptor `List`, không phải `Number`: nó là một kiểu danh sách có tham số, không phải chính biến kiểu `T`.

Quy tắc phải áp dụng đúng hình dạng:

```text
T                 -> kieu xoa cua gioi han trai nhat
List<T>           -> List
T[]               -> mang cua kieu xoa cua T
```

Với `T extends Number`, trường kiểu `T[]` có descriptor tương ứng `Number[]`. Điều này không cho phép tự viết `new T[10]`: phép tạo mảng của một biến kiểu vẫn là câu hỏi riêng về kiểu có thể được biểu diễn đầy đủ lúc chạy.

## 9. Những kết luận cần tránh

### “Generic luôn bị thay bằng Object”

Chỉ đúng với tham số không giới hạn tường minh hoặc có giới hạn đầu xóa về `Object`. `N extends Number` xóa về `Number`, `S extends CharSequence` xóa về `CharSequence`.

### “Gọi với Integer thì N xóa thành Integer”

Kiểu xóa được quyết định từ **khai báo**, không từ từng đối số của lời gọi. `echoNumber(7)` vẫn gọi phương thức có descriptor nhận và trả `Number`.

### “Sau xóa, trình biên dịch cho gán mọi Number vào N”

Mã nguồn vẫn được kiểm tra theo `N` và các quan hệ generic. Trong `NumberBox<Integer>`, `Double` không trở thành giá trị hợp lệ chỉ vì trường có descriptor `Number`.

### “Xóa kiểu làm mất lớp thực của phần tử”

Đối tượng `Integer` vẫn có lớp thực là `Integer`. Cái không được tự động lưu như một biến kiểu runtime cho mỗi đối tượng generic là đối số kiểu của khai báo, chẳng hạn `T = String` trong một đối tượng `new Box<String>(...)` thông thường.

### “Reflection không bao giờ thấy generic”

Reflection có thể đọc metadata của khai báo: tham số kiểu, giới hạn, kiểu trường và kiểu phương thức dưới dạng generic. Nhưng đọc `T` trong khai báo không đồng nghĩa lấy được `String` từ mọi đối tượng `Box<String>` bất kỳ.

### “Đổi thứ tự giới hạn interface chỉ là định dạng”

Giới hạn trái nhất quyết định kiểu xóa. Thay đổi nó có thể đổi descriptor và tác động tới tương thích nhị phân. Đừng tự sắp xếp lại các giới hạn của API đã có chỉ để chúng trông đều hơn.

## 10. Thực hành tự kiểm tra

### Bài 1: Xác định kiểu xóa

Với các khai báo:

```java
class Plain<T> {}
class Numeric<N extends Number> {}
class Textual<S extends CharSequence> {}
class Ordered<T extends Comparable<T>> {}
class Composite<T extends Number & Comparable<T>> {}
```

**Đáp án:**

- `T` của `Plain`: `Object`.
- `N` của `Numeric`: `Number`.
- `S` của `Textual`: `CharSequence`.
- `T` của `Ordered`: `Comparable`.
- `T` của `Composite`: `Number`.

### Bài 2: Tính descriptor của phương thức

```java
static <T> T identity(T value) {
    return value;
}

static <N extends Number> N numericIdentity(N value) {
    return value;
}
```

**Đáp án:** phương thức đầu có mô hình `Object identity(Object)`; phương thức sau có mô hình `Number numericIdentity(Number)`. Dù gọi cả hai bằng `Integer`, kiểu đã xóa không thay đổi theo từng lần gọi.

### Bài 3: Có thể bỏ Comparable ở giới hạn thứ hai không?

Với `<N extends Number & Comparable<N>>`, nếu bỏ `Comparable<N>` mà vẫn gọi `first.compareTo(second)` thì sao?

**Đáp án:** không biên dịch, vì `Number` không khai báo `compareTo`. Giới hạn sau vẫn cung cấp khả năng cần thiết ở mã nguồn, dù kiểu xóa chính là `Number`.

### Bài 4: Tại sao javap vừa in T vừa in Object?

**Đáp án:** dòng khai báo generic có thể được dựng từ metadata của class file; dòng `descriptor` cho biết biểu diễn kiểu đã xóa. Muốn chứng minh quy tắc xóa kiểu, phải xem đúng dòng descriptor hoặc kết quả reflection thích hợp.

### Bài 5: Vì sao getDeclaredMethod cần Number.class?

Với `<N extends Number> N echoNumber(N value)`, thử thay `Number.class` bằng `Integer.class` trong phép tra cứu ở chương trình.

**Đáp án:** tra cứu không tìm thấy phương thức có chữ ký đó và ném `NoSuchMethodException`. Phương thức khai báo có kiểu tham số đã xóa là `Number`; nó không tạo thêm một bản phương thức có tham số `Integer` cho lời gọi dùng số nguyên.

Khi xác định kiểu sau xóa, hãy bắt đầu từ khai báo tham số kiểu, tìm giới hạn trái nhất, rồi áp dụng quy tắc đệ quy nếu giới hạn đó vẫn còn tham số. Sau đó đối chiếu descriptor để tách bạch kiểu ở mã nguồn, kiểu đã xóa và lớp thực của đối tượng.
