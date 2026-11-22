# Các phép ép kiểu được trình biên dịch chèn vào

## 1. Vì sao mã generic không viết cast mà bytecode vẫn có cast?

Xét đoạn mã quen thuộc:

```java
List<String> names = List.of("Java");
String name = names.get(0);
```

Trong mã nguồn, `names.get(0)` có kiểu `String` theo khai báo `List<String>`, nên người viết không cần thêm `(String)`.

Tuy nhiên, phương thức `List.get(int)` được biên dịch với kiểu trả về sau xóa kiểu là `Object`. Ở nơi cần kết quả như một `String`, trình biên dịch phải tạo mã kiểm tra kiểu tham chiếu tương ứng. Với `javac`, có thể quan sát một lệnh JVM `checkcast java/lang/String` ngay sau lời gọi `get`.

Có hai tầng cần giữ tách biệt:

- **Tầng mã nguồn:** generic cho phép kiểm tra quan hệ kiểu và viết mã có kiểu cụ thể.
- **Tầng thực thi:** bytecode gọi phương thức theo mô tả kiểu đã xóa; một số nơi sử dụng giá trị cần kiểm tra kiểu hẹp hơn.

Xóa kiểu không có nghĩa mọi kiểu phần tử biến thành một đối tượng mới. Giá trị chuỗi vẫn là đối tượng `String`; thay đổi nằm ở cách biểu diễn kiểu trong mô tả trường/phương thức và các lệnh cần dùng để giữ ngữ nghĩa chương trình. Quy tắc nền tảng nằm ở [JLS §4.6 về xóa kiểu](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6).

## 2. Phép ép kiểu được chèn ở nơi cần dùng kiểu hẹp hơn

Có thể hình dung hai dòng đầu bài theo các bước sau:

```java
Object erasedResult = names.get(0);
String name = (String) erasedResult;
```

Đây là cách diễn giải để hiểu vai trò của cast, không phải bản chuyển đổi mã nguồn chính xác mà `javac` ghi ra một tệp Java khác.

Trình biên dịch đã kiểm tra mã nguồn có hợp lệ với generic hay không trước khi sinh bytecode. Nó không dùng cast tự động để hợp thức hóa mã sai kiểu như:

```java
List<String> names = List.of("Java");
// Integer number = names.get(0); // Lỗi biên dịch.
```

Nếu phép gán đã hợp lệ về kiểu nguồn, cast được chèn nhằm bảo đảm giá trị do lời gọi với mô tả kiểu đã xóa cung cấp có thể được dùng ở vị trí yêu cầu kiểu hẹp hơn.

Các vị trí thường gặp:

- Gán kết quả trả về của phương thức generic vào biến có kiểu cụ thể.
- Dùng kết quả đó làm đối tượng nhận lời gọi phương thức của kiểu cụ thể, như `names.get(0).length()`.
- Đọc trường có kiểu là một tham số kiểu rồi sử dụng kết quả như kiểu cụ thể.
- Đọc một giá trị wrapper qua generic rồi unboxing thành kiểu nguyên thủy.

Không cần có dấu `(Type)` trong mã nguồn mới có lệnh `checkcast` trong bytecode.

## 3. Không phải mọi lần đọc generic đều cần cùng một cast

So sánh:

```java
String text = names.get(0);
Object value = names.get(0);
```

Ở dòng thứ nhất, bytecode cần kiểm tra kết quả dưới dạng `String`. Ở dòng thứ hai, đích đã là `Object`; kết quả trả về sau xóa kiểu phù hợp trực tiếp, nên `javac` không cần chèn `checkcast String` cho phép gán này.

Điều đó không làm kiểu của biểu thức nguồn `names.get(0)` trở thành `Object`. Trong hệ thống kiểu nguồn, nó vẫn gắn với `String`; chỉ là ngữ cảnh sử dụng không yêu cầu một phép kiểm tra hẹp hơn trong bytecode.

Cũng không nên học thuộc “cứ gọi `get` là có cast”. Cần xét:

1. Mô tả kiểu sau xóa kiểu của thành viên được gọi là gì?
2. Kết quả được sử dụng như kiểu nào?
3. Có cần kiểm tra kiểu tham chiếu hẹp hơn để thực hiện sử dụng đó không?

Quy tắc đánh giá lời gọi và các kiểm tra kiểu liên quan được mô tả trong [JLS §15.12.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.5).

## 4. Có cận thì kiểu bị xóa không nhất thiết là `Object`

Xét lớp generic sau, đặt trong một lớp bao ngoài khi chạy:

```java
static final class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Vì cận trái nhất của `T` là `Number`, mô tả kiểu JVM của `get()` trả về `Number`, không phải `Object`.

```java
Box<Integer> box = new Box<>(42);
Integer exact = box.get();
Number broad = box.get();
```

Hai dòng đọc có nhu cầu khác nhau:

| Mã nguồn | Kiểu trả về sau xóa kiểu | Việc `javac` cần làm ở nơi gọi |
| --- | --- | --- |
| `Integer exact = box.get()` | `Number` | Kiểm tra kết quả là `Integer` |
| `Number broad = box.get()` | `Number` | Không cần thu hẹp về `Integer` cho phép gán này |

Trong thân `Box.get()`, việc trả trường `value` vốn đã có mô tả `Number` không đòi hỏi một cast về `Integer`. Lớp generic không được sinh một bản riêng cho mỗi đối số kiểu. Cast cụ thể xuất hiện tại nơi mã gọi cần sử dụng kết quả như `Integer`.

Nếu tham số kiểu có nhiều cận, xóa kiểu dựa trên cận trái nhất; những ràng buộc còn lại vẫn có ý nghĩa khi kiểm tra mã nguồn. Vì vậy, không thể suy luận mọi cast chỉ bằng một quy tắc “`T` luôn thành `Object`”.

## 5. Phân biệt `checkcast` với unboxing

Ví dụ:

```java
List<Integer> counts = List.of(7);
int count = counts.get(0);
```

Luồng bytecode điển hình là:

```text
List.get(int) trả Object
        ↓
checkcast java/lang/Integer
        ↓
Integer.intValue() trả int
```

Có hai bước khác nhau:

- `checkcast Integer` kiểm tra kiểu tham chiếu của đối tượng.
- `Integer.intValue()` lấy giá trị `int` từ wrapper, tức unboxing.

`checkcast` không biến một đối tượng `Long` thành `Integer`, cũng không thực hiện phép chuyển đổi số từ `long` sang `int`. Nếu đối tượng không phù hợp với kiểu kiểm tra, nó có thể gây `ClassCastException`.

Với giá trị `null`, kiểm tra `checkcast Integer` không tự gây lỗi; tham chiếu vẫn là `null`. Gọi `intValue()` trên tham chiếu đó mới gây `NullPointerException`. Phân biệt hai bước giúp xác định đúng nguyên nhân khi đọc stack trace.

Theo [đặc tả JVM của lệnh checkcast](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html#jvms-6.5.checkcast), lệnh này kiểm tra tính tương thích kiểu của tham chiếu; nó không sao chép đối tượng hoặc đổi lớp thực tế của đối tượng.

## 6. Chương trình hoàn chỉnh để xem bytecode

Lưu vào `CastInsertionDemo.java`, dùng Java 17 trở lên:

```java
import java.util.List;

public class CastInsertionDemo {
    static final class Box<T extends Number> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        List<String> names = List.of("Java");
        String name = names.get(0);
        Object asObject = names.get(0);

        List<Integer> counts = List.of(7);
        int count = counts.get(0);

        Box<Integer> box = new Box<>(42);
        Integer boxed = box.get();
        Number asNumber = box.get();
        String echo = identity("ok");

        System.out.println("name = " + name);
        System.out.println("asObject = " + asObject);
        System.out.println("count = " + count);
        System.out.println("boxed = " + boxed);
        System.out.println("asNumber = " + asNumber);
        System.out.println("echo = " + echo);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 CastInsertionDemo.java
java CastInsertionDemo
```

Kết quả chuẩn:

```text
name = Java
asObject = Java
count = 7
boxed = 42
asNumber = 42
echo = ok
```

Xem mã lệnh và mô tả kiểu JVM:

```shell
javap -c -s -p CastInsertionDemo
```

- `-c`: hiển thị các lệnh bytecode.
- `-s`: hiển thị mô tả kiểu JVM (descriptor).
- `-p`: hiển thị cả các thành viên không public.

Các tùy chọn này có trong [tài liệu javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html).

### 6.1. Nhận chuỗi từ `List<String>`

Phần tương ứng với `String name = names.get(0)` có các lệnh chính sau; đã lược bỏ offset và chỉ số constant pool để tập trung vào ý nghĩa:

```text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast java/lang/String
astore_2
```

`(I)Ljava/lang/Object;` nghĩa là nhận một `int` và trả một tham chiếu `Object`. Sau đó `checkcast` kiểm tra đối tượng như `String` trước khi kết quả được dùng như biến `name`.

### 6.2. Nhận cùng kết quả dưới dạng `Object`

Phần tương ứng với `Object asObject = names.get(0)`:

```text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
astore_3
```

Không có `checkcast String` ở giữa. Cùng một phương thức generic, nhưng ngữ cảnh sử dụng khác nhau dẫn tới mã lệnh khác nhau.

### 6.3. Nhận số nguyên rồi unboxing

Phần tương ứng với `int count = counts.get(0)`:

```text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast java/lang/Integer
invokevirtual java/lang/Integer.intValue:()I
```

Đây là bằng chứng trực tiếp rằng kiểm tra kiểu wrapper và unboxing là hai bước riêng.

### 6.4. Nhận `Integer` từ lớp có cận `Number`

Các lệnh chính cho `Integer boxed = box.get()`:

```text
invokevirtual CastInsertionDemo$Box.get:()Ljava/lang/Number;
checkcast java/lang/Integer
```

Trong khi `Number asNumber = box.get()` không cần lệnh thu hẹp về `Integer`.

Có thể xem riêng lớp lồng trong PowerShell bằng cách đặt tên lớp trong dấu nháy đơn để giữ nguyên ký tự `$`:

```powershell
javap -c -s -p 'CastInsertionDemo$Box'
```

Mô tả kiểu của trường `value` là `Ljava/lang/Number;`, còn `get` có descriptor `()Ljava/lang/Number;`. Thông tin khai báo generic vẫn có thể xuất hiện trong metadata của class file; điều đó không thay thế descriptor mà JVM dùng để gọi phương thức.

### 6.5. Phương thức generic cũng có cast tại nơi gọi

`identity` không có cận tường minh, nên descriptor là:

```text
(Ljava/lang/Object;)Ljava/lang/Object;
```

Phần tương ứng với `String echo = identity("ok")` có:

```text
invokestatic identity:(Ljava/lang/Object;)Ljava/lang/Object;
checkcast java/lang/String
```

Phép kiểm tra `String` nằm ở nơi sử dụng kết quả. Thân `identity` chỉ nhận rồi trả cùng tham chiếu với mô tả kiểu đã xóa.

Tên biến cục bộ, offset, chỉ số constant pool và chi tiết hiển thị có thể thay đổi khi sửa chương trình hoặc dùng phiên bản trình biên dịch khác. Các đoạn trên là trích rút gọn từ bytecode của chương trình minh họa, không phải toàn bộ đầu ra nguyên văn của `javap`.

## 7. Vì sao `ClassCastException` có thể xuất hiện ở dòng không viết cast?

Nếu toàn bộ mã giữ đúng hợp đồng generic, kết quả sẽ phù hợp với cast được chèn. Nhưng một ép kiểu không kiểm tra có thể làm một tham chiếu mang khai báo generic không phù hợp với dữ liệu thực.

Chương trình độc lập dưới đây cố tình tạo tình huống sai để quan sát. Đây là phản ví dụ cần tránh khi viết ứng dụng, không phải cách chuyển danh sách số thành danh sách chuỗi.

Lưu vào `HiddenCastFailure.java`:

```java
import java.util.List;

public class HiddenCastFailure {
    public static void main(String[] args) {
        List<?> source = List.of(123);

        @SuppressWarnings("unchecked")
        List<String> wrong = (List<String>) source;

        Object value = wrong.get(0);
        System.out.println("as Object = " + value);

        try {
            String text = wrong.get(0);
            System.out.println("text = " + text);
        } catch (ClassCastException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HiddenCastFailure.java
java HiddenCastFailure
```

Kết quả chuẩn:

```text
as Object = 123
ClassCastException
```

Phép cast sang `List<String>` không duyệt danh sách để kiểm tra từng phần tử. `@SuppressWarnings` chỉ ẩn cảnh báo của trình biên dịch, không sửa dữ liệu hay tăng mức an toàn.

Dòng gán vào `Object` chưa yêu cầu kiểm tra phần tử là `String`, nên đọc được số `123` dưới dạng `Object`. Dòng `String text = wrong.get(0)` cần cast được chèn về `String`; đối tượng thực là `Integer`, nên ném `ClassCastException`. Dòng in `text` không được thực hiện.

Trong ứng dụng thực tế, hãy tìm nguyên nhân làm sai hợp đồng kiểu ở phía trước, thay vì chỉ thêm `try/catch` tại điểm đọc. Nếu thật sự muốn chuyển số thành chuỗi, cần ánh xạ từng giá trị bằng một phép chuyển đổi như `String.valueOf`, không dùng ép kiểu danh sách.

## 8. Đọc lỗi và bytecode theo đúng nguyên nhân

Khi thấy `ClassCastException` ở dòng lấy phần tử generic:

1. Xác định dòng đó sử dụng kết quả như kiểu nào.
2. Xem descriptor sau xóa kiểu và lệnh `checkcast` tại nơi dùng bằng `javap` khi cần.
3. Kiểm tra dữ liệu thực tế không phù hợp đã đi vào qua đâu: ép kiểu không kiểm tra, ranh giới reflection, thư viện bên ngoài hoặc một đường truyền dữ liệu phá vỡ hợp đồng.
4. Sửa nguồn làm mất an toàn kiểu; không cho rằng chính danh sách đã tự chuyển đổi một đối tượng sang kiểu mới.

Cũng cần phân biệt:

| Hiện tượng | Nguyên nhân tiêu biểu |
| --- | --- |
| Lỗi biên dịch khi gán `String` thành `Integer` | Quan hệ kiểu nguồn không hợp lệ |
| `ClassCastException` tại `checkcast String` | Đối tượng thực không phải kiểu tham chiếu yêu cầu |
| `NullPointerException` khi unboxing | Tham chiếu wrapper là `null` |
| Không thấy `checkcast String` khi đích là `Object` | Ngữ cảnh sử dụng không cần thu hẹp về `String` |

Bytecode cho biết phép kiểm tra được biểu diễn ra sao; nó không tự chỉ ra toàn bộ lịch sử dữ liệu sai kiểu. Cần kết hợp vị trí lỗi với hợp đồng generic và đường đi của dữ liệu.

## 9. Những điều không nên suy diễn

- **Không có cast trong mã nguồn không đồng nghĩa không có cast trong bytecode.** Generic có thể khiến trình biên dịch sinh kiểm tra kiểu ở nơi sử dụng.
- **`checkcast` không chuyển đổi nội dung.** Nó không biến số thành chuỗi hoặc biến wrapper này thành wrapper khác.
- **Xóa kiểu không xóa mọi metadata generic khỏi class file.** Descriptor thực thi và metadata khai báo phục vụ công cụ/reflection có vai trò khác nhau.
- **Không cần tự thêm cast vào mọi lần đọc.** Hãy giữ khai báo generic đúng; trình biên dịch sinh mã cần thiết.
- **Không kết luận hiệu năng chỉ từ việc đếm `checkcast`.** JVM có thể tối ưu các kiểm tra khi có đủ bằng chứng; đánh giá chi phí thực cần phép đo phù hợp, không suy luận từ một lệnh đứng riêng.
- **Cast do trình biên dịch sinh không chỉ xuất hiện ở việc gán biến.** Một số phương thức cầu nối (bridge methods) cũng có cast để giữ quan hệ giữa override và descriptor sau xóa kiểu. Đó là một ngữ cảnh riêng; bài này tập trung vào việc sử dụng giá trị generic.

## 10. Tự kiểm tra

**Câu 1.** Vì sao `String s = list.get(0)` với `List<String>` có thể sinh `checkcast String`?

Vì mã nguồn biết kết quả là `String`, còn descriptor của `List.get` trả `Object`. Nơi sử dụng cần kiểm tra kết quả dưới dạng kiểu cụ thể.

**Câu 2.** Với cùng danh sách, `Object x = list.get(0)` có nhất thiết cần cast về `String` không?

Không. Trong chương trình minh họa, `javac` dùng trực tiếp kết quả `Object` cho phép gán này.

**Câu 3.** `T extends Number` bị xóa thành gì, và khi nào cần cast về `Integer`?

`T` bị xóa thành cận trái nhất là `Number`. Khi một kết quả có descriptor trả `Number` được dùng như `Integer`, cần kiểm tra kiểu phù hợp ở nơi sử dụng.

**Câu 4.** `checkcast Integer` có tự tạo ra `int` không?

Không. Nó kiểm tra tham chiếu `Integer`; unboxing tiếp theo mới tạo giá trị `int` bằng `intValue()`.
