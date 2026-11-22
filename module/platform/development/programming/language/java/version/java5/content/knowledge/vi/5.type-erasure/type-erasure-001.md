# Cơ chế xóa kiểu và dạng kiểu sau biên dịch

## 1. Xóa kiểu là gì?

Xóa kiểu (type erasure) là cách Java ánh xạ các kiểu có tham số trong mã nguồn sang dạng kiểu dùng trong mã thực thi. Trình biên dịch kiểm tra các ràng buộc generics trước, rồi tạo bytecode với các kiểu đã xóa và những lệnh chuyển kiểu cần thiết.

Ví dụ, ở mã nguồn:

```java
List<String> names = new ArrayList<>();
names.add("Java");
String first = names.get(0);
```

Trình biên dịch biết `names` chứa `String`, nên chặn `names.add(123)`. Trong bytecode, phương thức `List.get` trả về `Object`; tại nơi dùng cần `String`, trình biên dịch chèn lệnh `checkcast` tương ứng.

Có ba lớp thông tin cần tách:

| Lớp thông tin | Điều cần hiểu |
| --- | --- |
| Kiểu trong mã nguồn | Trình biên dịch dùng `List<String>`, `T`, cận kiểu… để kiểm tra chương trình |
| Kiểu trong descriptor của class file | Các trường và phương thức dùng dạng sau xóa kiểu, chẳng hạn `List`, `Object` hoặc cận đầu tiên |
| Metadata khai báo tổng quát | Class file có thể giữ thông tin generics trong thuộc tính `Signature` để công cụ và reflection đọc |

Vì vậy, “xóa kiểu” không có nghĩa mọi thông tin liên quan đến generics đều biến mất khỏi tệp `.class`. Nó cũng không có nghĩa các đối tượng `String` trong danh sách bị biến thành đối tượng có lớp thực tế là `Object`.

Các quy tắc dưới đây vẫn áp dụng cho Java hiện đại. Ví dụ chạy độc lập dùng Java 17+.

## 2. Vì sao Java dùng cơ chế này?

Generics cho phép diễn đạt quan hệ kiểu ngay trong API: hộp chứa kiểu gì, danh sách trả về phần tử kiểu gì, hay đầu vào và đầu ra của một phương thức liên hệ thế nào.

Xóa kiểu cho phép lớp tổng quát dùng một biểu diễn thực thi chung, thay vì tạo một lớp riêng cho từng đối số kiểu như `Box<String>` và `Box<Integer>`. Điều này cũng gắn với mục tiêu tương thích khi generics được đưa vào hệ sinh thái Java.

Điều người học cần áp dụng hôm nay là: **giữ hợp đồng kiểu chặt chẽ ở mã nguồn, hiểu dạng thực thi chung khi đọc bytecode hoặc phân tích lỗi**. Không cần dùng raw type trong mã nguồn để làm việc với cơ chế xóa kiểu.

Đường đi khái quát:

```text
Mã nguồn có generics
        ↓
Kiểm tra quan hệ kiểu và các cận
        ↓
Ánh xạ sang kiểu đã xóa
        ↓
Chèn chuyển kiểu / phương thức cầu nối khi cần
        ↓
Class file: descriptor + bytecode + metadata khai báo
```

Sơ đồ mô tả các trách nhiệm về mặt khái niệm, không phải cam kết về thứ tự nội bộ từng bước của mọi trình biên dịch.

## 3. Các quy tắc ánh xạ cơ bản

### 3.1. Kiểu có đối số kiểu mất danh sách đối số trong dạng đã xóa

| Kiểu trong mã nguồn | Dạng xóa kiểu |
| --- | --- |
| `List<String>` | `List` |
| `List<Integer>` | `List` |
| `Map<String, Integer>` | `Map` |
| `List<? extends Number>` | `List` |
| `List<? super Integer>` | `List` |
| `List<Map<String, Integer>>` | `List` |

Cột thứ hai diễn tả kết quả ánh xạ kiểu, không khuyến khích khai báo raw type trong mã nguồn.

Chẳng hạn, một trường `List<String> names` có descriptor chỉ nhắc đến `java.util.List`. Nó không trở thành một trường `Object`, và cũng không trở thành `List<Object>` theo nghĩa hợp đồng kiểu của mã nguồn.

### 3.2. Biến kiểu được thay bằng dạng xóa của cận đầu tiên

Nếu không viết cận, biến kiểu có cận ngầm định là `Object`:

```java
class Box<T> {
    private T value;

    T get() {
        return value;
    }
}
```

Trong dạng thực thi, trường `value` và kiểu trả về của `get` dùng `Object`.

Nếu có cận:

```java
class NumberBox<T extends Number> {
    private T value;

    T get() {
        return value;
    }
}
```

thì dạng xóa của `T` là `Number`, không phải `Object`.

Với nhiều cận:

```java
class RankedBox<T extends Number & Comparable<T>> {
    private T value;

    T get() {
        return value;
    }
}
```

dạng xóa của `T` vẫn là `Number`, vì đó là cận đầu tiên. Ràng buộc `Comparable<T>` vẫn tham gia kiểm tra mã nguồn; “không phải kiểu trong descriptor của trường” không đồng nghĩa với “không có tác dụng”.

Cận đầu tiên cũng có thể là một interface khi không có cận lớp, ví dụ `<T extends CharSequence>` có dạng xóa là `CharSequence`. Quy tắc chính xác là lấy dạng xóa của cận bên trái nhất, không phải “lúc nào cũng lấy lớp cha gần nhất”.

### 3.3. Mảng xóa kiểu theo kiểu thành phần

| Kiểu khai báo | Điều kiện | Dạng xóa kiểu |
| --- | --- | --- |
| `T[]` | `T` không có cận tường minh | `Object[]` |
| `T[]` | `T extends Number` | `Number[]` |
| `T[][]` | `T extends Number` | `Number[][]` |
| `String[]` | Không có biến kiểu cần xóa | `String[]` |

Đây là quy tắc cho kiểu khai báo. Nó không nói rằng một đối tượng mảng thực tế bị đổi lớp lúc chạy. Nếu một giá trị `String[]` được truyền vào phương thức có tham số `T[]`, đối tượng đó vẫn là mảng `String`.

### 3.4. Kiểu không tổng quát không tự biến thành Object

Các kiểu như `String`, `Number`, `int` vẫn giữ nguyên. Xóa kiểu không phải thao tác thay mọi kiểu tham chiếu bằng `Object`.

Ví dụ:

```java
static String head(List<String> values) {
    return values.get(0);
}
```

Tham số có dạng xóa `List`, nhưng kiểu trả về của chính `head` vẫn là `String`, vì nó được khai báo trực tiếp như vậy.

## 4. Dạng lớp và phương thức sau biên dịch

### 4.1. Lớp tổng quát dùng một biểu diễn chung

Với `Box<T>`, có thể hình dung phần thực thi đã xóa bằng mã sau:

```java
// Mô hình giải thích, không phải mã nguồn do javac xuất ra.
class BoxErased {
    private Object value;

    BoxErased(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Trình biên dịch không tạo thêm một lớp tên `BoxErased`; tên này chỉ giúp tách mô hình giải thích khỏi lớp gốc.

Khi dùng:

```java
Box<String> box = new Box<>("Java");
String value = box.get();
```

có thể hình dung lời gọi thành:

```java
// Chỉ minh họa ý nghĩa của mã thực thi:
String value = (String) erasedBox.get();
```

Trong bytecode, bước chuyển sang `String` được biểu diễn bằng `checkcast`. Lệnh này kiểm tra đối tượng khi chạy; nó không tạo một `String` mới.

Nếu nơi dùng chỉ cần `Object`, không nhất thiết cần phép cast đó:

```java
Object value = box.get();
```

Trình biên dịch chèn chuyển kiểu theo nhu cầu của nơi sử dụng, không chèn một cast giống nhau sau mọi lời gọi tổng quát.

### 4.2. Phương thức tổng quát cũng được xóa kiểu

```java
static <T> T identity(T value) {
    return value;
}
```

Dạng descriptor dùng `Object` cho tham số và kiểu trả về:

```text
(Ljava/lang/Object;)Ljava/lang/Object;
```

Với:

```java
static <T extends Number> T identityNumber(T value) {
    return value;
}
```

descriptor dùng `Number`:

```text
(Ljava/lang/Number;)Ljava/lang/Number;
```

Không có một bản bytecode riêng của `identity` cho `String`, một bản cho `Integer`, rồi một bản cho mỗi kiểu khác. Thông tin mà nơi gọi cần được kiểm tra trước biên dịch và chuyển thành những thao tác thực thi thích hợp.

### 4.3. Vai trò của phương thức cầu nối

Khi lớp con ghi đè phương thức gắn với tham số kiểu của lớp cha, dạng đã xóa của phương thức cha có thể khác descriptor của phương thức mà lớp con khai báo. Trình biên dịch có thể sinh phương thức cầu nối (bridge method) để giữ đúng hành vi đa hình.

Ví dụ quan hệ `StringBox extends Box<String>` với phương thức `String get()` có thể cần thêm một phương thức cầu nối trả `Object`, chuyển tiếp tới `get()` trả `String`.

Đây là một phần của cơ chế bảo toàn hợp đồng mã nguồn khi chuyển sang dạng thực thi. Không cần tự viết các phương thức cầu nối trong mã ứng dụng; khi đọc `javap -v` hoặc reflection, cần biết vì sao có thành viên do trình biên dịch sinh thêm.

## 5. Chương trình hoàn chỉnh để kiểm chứng

Lưu thành `ErasureDemo.java`:

```java
import java.lang.reflect.Field;
import java.util.List;

public class ErasureDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static class NumberBox<T extends Number> {
        private final T value;

        NumberBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    private List<String> names = List.of();

    static String head(List<String> values) {
        return values.get(0);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(21);

        System.out.println("head = " + head(List.of("Java")));
        System.out.println("same Box class = "
                + (text.getClass() == number.getClass()));
        System.out.println("stored class = "
                + text.get().getClass().getTypeName());

        System.out.println("Box.get return = "
                + Box.class.getDeclaredMethod("get")
                        .getReturnType().getTypeName());
        System.out.println("NumberBox.get return = "
                + NumberBox.class.getDeclaredMethod("get")
                        .getReturnType().getTypeName());

        Field field = ErasureDemo.class.getDeclaredField("names");
        System.out.println("names type = "
                + field.getType().getTypeName());
        System.out.println("names generic type = "
                + field.getGenericType().getTypeName());
    }
}
```

Biên dịch và chạy với JDK 17+:

```shell
javac --release 17 -Xlint:all ErasureDemo.java
java ErasureDemo
```

Stdout chính xác:

```text
head = Java
same Box class = true
stored class = java.lang.String
Box.get return = java.lang.Object
NumberBox.get return = java.lang.Number
names type = java.util.List
names generic type = java.util.List<java.lang.String>
```

Giải thích các bằng chứng:

- `same Box class = true`: hai đối số kiểu không tạo hai lớp thực thi khác nhau. Hai đối tượng hộp vẫn là hai đối tượng riêng.
- `stored class = java.lang.String`: đối tượng nằm trong hộp vẫn giữ lớp thực tế.
- Hai dòng `get return` phản ánh cận dùng cho kiểu trả về đã xóa.
- `getType()` đọc kiểu trường theo biểu diễn lớp thông thường; `getGenericType()` đọc mô tả kiểu tổng quát của khai báo trường.

Dòng cuối không có nghĩa mọi đối tượng `List` tự biết đối số kiểu của chính nó. Reflection đang đọc **khai báo của trường `names` trong lớp `ErasureDemo`**, không suy ra kiểu phần tử từ một danh sách tùy ý.

## 6. Quan sát class file bằng javap

Sau khi biên dịch, chạy:

```shell
javap -p -s ErasureDemo
javap -p -c ErasureDemo
javap -p -s 'ErasureDemo$Box'
javap -p -s 'ErasureDemo$NumberBox'
javap -p -v ErasureDemo
```

Hai tên lớp lồng nhau được đặt trong nháy đơn để lệnh dùng được với PowerShell và các shell có mở rộng ký tự `$`. Nếu dùng Windows Command Prompt, dùng nháy kép cho tên lớp thay thế.

Các tùy chọn cần chú ý:

| Tùy chọn | Mục đích |
| --- | --- |
| `-p` | Hiển thị cả thành viên private |
| `-s` | Hiển thị descriptor |
| `-c` | Hiển thị lệnh bytecode |
| `-v` | Hiển thị thêm metadata, gồm các thuộc tính như `Signature` |

Những descriptor quan trọng có thể tìm thấy:

| Thành viên | Descriptor sau xóa kiểu |
| --- | --- |
| `ErasureDemo.names` | `Ljava/util/List;` |
| `ErasureDemo.head(List<String>)` | `(Ljava/util/List;)Ljava/lang/String;` |
| `ErasureDemo$Box.value` | `Ljava/lang/Object;` |
| `ErasureDemo$Box.get()` | `()Ljava/lang/Object;` |
| `ErasureDemo$NumberBox.value` | `Ljava/lang/Number;` |
| `ErasureDemo$NumberBox.get()` | `()Ljava/lang/Number;` |

Trong bytecode của `head`, tìm lời gọi `List.get` với kiểu trả về `Object`, rồi lệnh `checkcast java/lang/String`. Chúng chứng minh cách trình biên dịch nối hợp đồng `List<String>` trong mã nguồn với phương thức đã xóa kiểu trong lúc chạy.

Khi xem `-v`, trường `names` có thể hiện đồng thời:

```text
descriptor: Ljava/util/List;
Signature: ... // Ljava/util/List<Ljava/lang/String;>;
```

Đây là trích đoạn giải thích đã lược số hiệu constant pool, không phải toàn bộ stdout. Descriptor và `Signature` phục vụ hai mục đích khác nhau. Đừng chỉ đọc dòng hiển thị đẹp `List<String>` của `javap` rồi kết luận descriptor vẫn mang đối số kiểu.

## 7. Những hệ quả cần nhận ra

### 7.1. Không thể kiểm tra List<String> tùy ý bằng instanceof

Với `Object value`, phép kiểm tra sau không hợp lệ:

```java
// if (value instanceof List<String>) { } // Không biên dịch.
```

Kiểm tra lớp thực thi không đủ để khẳng định mọi phần tử của một danh sách tùy ý là `String`. Có thể dùng `value instanceof List<?>` để xác nhận nó là danh sách mà chưa cam kết kiểu phần tử.

Nếu cần xác thực dữ liệu từ bên ngoài, phải kiểm tra nội dung hoặc dùng cơ chế chuyển đổi có hợp đồng rõ ràng. Ép kiểu không được kiểm tra không cung cấp phép xác thực đó.

### 7.2. Không thể tạo trực tiếp đối tượng của T

Trong một phương thức tổng quát, `new T()` không hợp lệ. Một biến kiểu không cung cấp trực tiếp lớp thực thi và hàm tạo cần gọi. Khi thuật toán cần tạo giá trị, thường truyền một hàm tạo dữ liệu như `Supplier<T>` hoặc một đối tượng mô tả kiểu phù hợp với bài toán.

Tương tự, `new T[n]` và `new List<String>[n]` không phải các cách tạo mảng tổng quát hợp lệ. Đây là những giới hạn cần hiểu từ việc đối số kiểu không được giữ như một lớp thực thi riêng cho mỗi trường hợp.

### 7.3. Hai overload không thể chỉ khác đối số kiểu bị xóa

```java
// Không thể cùng khai báo trong một lớp:
// void print(List<String> values) { }
// void print(List<Integer> values) { }
```

Cả hai cùng có tham số `List` sau xóa kiểu, nên xảy ra xung đột. Có thể đổi tên thao tác hoặc thiết kế một phương thức chung nếu hành vi thực sự giống nhau.

### 7.4. Xóa kiểu không vô hiệu hóa kiểm tra biên dịch

```java
List<String> names = new ArrayList<>();
// names.add(42); // Vẫn bị trình biên dịch chặn.
```

Không nên lý luận “runtime chỉ thấy List nên thêm gì cũng được”. Trình biên dịch kiểm tra hợp đồng `List<String>` trước khi tạo bytecode. Những đường vượt qua kiểm tra như raw type hoặc cast không được kiểm tra có thể dẫn tới lỗi chuyển kiểu lúc đọc; chúng không phải cách sử dụng được khuyến nghị.

## 8. Tự kiểm tra cách hiểu

1. `T extends CharSequence` bị xóa thành gì? **`CharSequence`**.
2. Trường `Map<String, List<Integer>>` có descriptor mang cả hai tầng đối số kiểu không? **Không; dạng trường là `Map`, thông tin khai báo tổng quát được biểu diễn riêng nếu có.**
3. `Box<String>` và `Box<Integer>` có cần hai lớp được sinh riêng không? **Không.**
4. Một `String` lấy từ `Box<String>` có bị đổi thành đối tượng lớp `Object` không? **Không; chỉ kiểu biểu diễn tại một số vị trí đã được xóa.**
5. Vì sao reflection vẫn có thể thấy `List<String>` trên một trường? **Nó đọc metadata của khai báo, không chứng minh rằng mọi đối tượng danh sách giữ đối số kiểu khi chạy.**
6. Vì sao có `checkcast` dù mã nguồn không viết cast? **Trình biên dịch khôi phục yêu cầu kiểu tại nơi dùng từ một phương thức trả về kiểu đã xóa.**

## Tài liệu đối chiếu

- [JLS §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6): quy tắc ánh xạ dạng kiểu.
- [JVMS §4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3) và [§4.7.9 — Signature](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.9): phân biệt dạng thực thi với metadata khai báo.
- [Tài liệu lệnh javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): cách đọc descriptor, bytecode và thuộc tính class file.
