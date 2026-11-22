# Khai báo giao diện generic và lớp triển khai

## 1. Giao diện generic giải quyết vấn đề gì?

Giao diện (interface) mô tả một hợp đồng: đối tượng cung cấp những thao tác nào, nhận dữ liệu kiểu gì và trả về kiểu gì. Lớp triển khai quyết định cách thực hiện hợp đồng ấy. Khi cùng một hợp đồng cần dùng với nhiều kiểu dữ liệu, ta khai báo giao diện generic bằng tham số kiểu.

Ví dụ, một ô lưu trữ có hai thao tác: đọc giá trị và thay giá trị. Ô chứa tên phải nhận và trả về `String`; ô chứa số đếm phải nhận và trả về `Integer`. Ta muốn dùng chung hình dạng hợp đồng nhưng vẫn để trình biên dịch phát hiện việc đưa nhầm kiểu dữ liệu vào ô.

```java
interface Slot<T> {
    T get();
    void set(T value);
}
```

Ở đây, `T` là **tham số kiểu**, chưa phải một kiểu cụ thể. Trong `Slot<String>`, `String` là **đối số kiểu**: hợp đồng được nhìn như `String get()` và `void set(String value)`. Trong `Slot<Integer>`, các vị trí ấy tương ứng với `Integer`.

Có thể hình dung quan hệ theo thứ tự:

```text
Slot<T>                         khai báo hợp đồng tổng quát
   ↓ chọn đối số kiểu
Slot<String>                    hợp đồng làm việc với chuỗi
   ↑ được triển khai bởi
MemorySlot<String>              một cách lưu trữ cụ thể
```

Đây là kiến thức generic vẫn dùng trong Java hiện hành. Những ví dụ bên dưới chạy với Java 17 trở lên; không cần thư viện hoặc framework.

## 2. Hai cách lớp triển khai lựa chọn kiểu

### 2.1. Giữ lớp triển khai ở dạng generic

```java
class MemorySlot<T> implements Slot<T> {
    private T value;

    MemorySlot(T initialValue) {
        this.value = initialValue;
    }

    @Override
    public T get() {
        return value;
    }

    @Override
    public void set(T value) {
        this.value = value;
    }
}
```

`<T>` sau tên lớp khai báo tham số kiểu của **lớp**. `Slot<T>` sau `implements` truyền tham số đó vào **giao diện**. Hai vị trí có vai trò khác nhau; viết `class MemorySlot implements Slot<T>` mà chưa khai báo `T` trong phạm vi phù hợp sẽ không biên dịch.

Khi tạo `MemorySlot<String>`, trình biên dịch nối các quan hệ: `T` của lớp là `String`, nên giao diện mà lớp thực hiện là `Slot<String>`. Bên gọi có thể dùng kiểu giao diện để ít phụ thuộc vào lớp cụ thể:

```java
Slot<String> name = new MemorySlot<>("Lan");
name.set("Mai");
String result = name.get();
// name.set(123); // Lỗi biên dịch: Slot<String> yêu cầu String.
```

Đoạn trên là minh họa đặt trong một phương thức, chưa phải chương trình độc lập. Dấu `<>` ở lời gọi constructor cho phép trình biên dịch suy luận đối số kiểu; nó không thay thế phần khai báo `<T>` của lớp.

Tên tham số không cần giống nhau. `class MemorySlot<E> implements Slot<E>` diễn đạt cùng quan hệ. Điều quan trọng là ánh xạ đối số kiểu, không phải ký tự `T` hay `E`.

### 2.2. Cố định kiểu ngay tại lớp triển khai

```java
class TrimmedTextSlot implements Slot<String> {
    private String value;

    TrimmedTextSlot(String initialValue) {
        set(initialValue);
    }

    @Override
    public String get() {
        return value;
    }

    @Override
    public void set(String value) {
        this.value = value.trim();
    }
}
```

`TrimmedTextSlot` không có tham số kiểu: lớp này chỉ triển khai `Slot<String>`. Vì đã cố định `T = String`, phương thức triển khai nhận/trả về `String`. Không viết `new TrimmedTextSlot<String>(...)` vì bản thân lớp không generic.

Lớp này bổ sung quy tắc cắt khoảng trắng ở đầu/cuối chuỗi. Đây là quy tắc của cách triển khai, không phải khả năng tự có của generic. Ví dụ yêu cầu chuỗi khác `null`; truyền `null` sẽ gây `NullPointerException` khi gọi `trim()`. Khi xây dựng API thực tế, cần công bố hoặc kiểm tra chính sách `null` rõ ràng.

| Cách khai báo | Ai lựa chọn kiểu dữ liệu? | Ví dụ sử dụng |
| --- | --- | --- |
| `MemorySlot<T> implements Slot<T>` | Bên sử dụng chọn đối số kiểu khi tạo hoặc khai báo đối tượng | `new MemorySlot<Integer>(1)` |
| `TrimmedTextSlot implements Slot<String>` | Lớp triển khai đã cố định kiểu là `String` | `new TrimmedTextSlot(" hello ")` |

Không cần làm mọi lớp thành generic. Nếu một cách triển khai chỉ có ý nghĩa với chuỗi, cố định `Slot<String>` thường làm ý định rõ hơn.

## 3. Chương trình chạy đầy đủ

Lưu toàn bộ mã sau vào **`GenericInterfaceDemo.java`**. Các kiểu phụ không khai báo `public` để có thể nằm trong cùng tệp với lớp chạy chính.

```java
interface Slot<T> {
    T get();
    void set(T value);
}

class MemorySlot<T> implements Slot<T> {
    private T value;

    MemorySlot(T initialValue) {
        this.value = initialValue;
    }

    @Override
    public T get() {
        return value;
    }

    @Override
    public void set(T value) {
        this.value = value;
    }
}

class TrimmedTextSlot implements Slot<String> {
    private String value;

    TrimmedTextSlot(String initialValue) {
        set(initialValue);
    }

    @Override
    public String get() {
        return value;
    }

    @Override
    public void set(String value) {
        this.value = value.trim();
    }
}

public class GenericInterfaceDemo {
    public static void main(String[] args) {
        Slot<String> name = new MemorySlot<>("Lan");
        name.set("Mai");
        System.out.println(name.get());

        Slot<Integer> count = new MemorySlot<>(2);
        count.set(3);
        System.out.println(count.get());

        Slot<String> label = new TrimmedTextSlot(" first ");
        label.set(" second ");
        System.out.println(label.get());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 -Xlint:all GenericInterfaceDemo.java
java GenericInterfaceDemo
```

Stdout chính xác:

```text
Mai
3
second
```

Ba biến được khai báo qua `Slot<...>`, còn đối tượng thật thuộc hai lớp triển khai khác nhau. Lời gọi `label.set(...)` chạy phần thân trong `TrimmedTextSlot`; kiểu giao diện không làm mất cơ chế đa hình. Generic bổ sung kiểm tra quan hệ kiểu tại thời điểm biên dịch, còn việc lựa chọn phương thức thể hiện dựa trên đối tượng thật vẫn diễn ra khi chạy.

## 4. Quy tắc triển khai cần nắm

### Phương thức triển khai phải có mức truy cập phù hợp

Hai phương thức `get` và `set` trong giao diện ở bài này ngầm định là `public abstract`. Lớp cụ thể phải cung cấp hoặc thừa kế phần triển khai phù hợp cho chúng. Vì vậy, phương thức trong lớp phải là `public`; bỏ `public` sẽ làm mức truy cập hẹp hơn và gây lỗi biên dịch.

Dùng `@Override` để trình biên dịch kiểm tra việc ghi đè. Nếu gõ nhầm `setValue` thay cho `set`, hoặc dùng kiểu tham số không khớp hợp đồng đã thay đối số kiểu, lỗi được phát hiện sớm.

Không phải mọi phương thức trong mọi giao diện đều là `public abstract`: Java hiện hành còn có phương thức `default`, `static` và `private`. Quy tắc trên nói về các khai báo không có thân trong ví dụ này.

### Lớp trừu tượng có thể để lại một phần hợp đồng

Đây là đoạn khai báo độc lập dùng cùng giao diện `Slot<T>`:

```java
abstract class ReadOnlyBase<T> implements Slot<T> {
    @Override
    public void set(T value) {
        throw new UnsupportedOperationException("Read only");
    }
}
```

Lớp trên chưa thực hiện `get()`, nên phải là `abstract`. Lớp cụ thể kế thừa nó cần cung cấp `get()` nếu chưa thừa kế phương thức phù hợp từ nơi khác. Việc một chữ ký có thể biên dịch không chứng minh thiết kế hợp đồng tốt: nếu người dùng thường cần ô chỉ đọc, một giao diện đọc riêng sẽ diễn đạt khả năng chính xác hơn việc luôn ném ngoại lệ ở `set()`.

### Tham số kiểu thuộc giao diện khác với tham số kiểu của phương thức

```java
interface Reader<T> {
    T read();
}

interface Identity {
    <U> U echo(U value);
}
```

`Reader<String>` cố định kiểu trả về cho toàn bộ hợp đồng của tham chiếu đó. `Identity` không phải giao diện generic; phương thức `echo` tự khai báo `U`, và mỗi lần gọi có thể suy luận một đối số kiểu khác nhau. Các khai báo trên chỉ minh họa sự khác nhau về phạm vi tham số kiểu.

Khi triển khai `Slot<String>`, không thêm `<T>` trước phương thức để cố “nhận mọi kiểu”:

```java
// Sai nếu dùng làm phần triển khai Slot<String>:
// public <T> void set(T value) { ... }
```

Phương thức generic mới không thực hiện hợp đồng `void set(String value)`. Nó còn có thể gây xung đột sau xóa kiểu. Hãy triển khai đúng chữ ký đã được xác định bởi giao diện.

## 5. Nhiều tham số kiểu và kế thừa giao diện

Giao diện có thể liên hệ nhiều kiểu. Đoạn sau là tập khai báo minh họa có thể đặt trong cùng một tệp Java:

```java
interface Mapper<S, R> {
    R map(S source);
}

class LengthMapper implements Mapper<String, Integer> {
    @Override
    public Integer map(String source) {
        return source.length();
    }
}

interface TextMapper<R> extends Mapper<String, R> {
}

class TrimMapper implements TextMapper<String> {
    @Override
    public String map(String source) {
        return source.trim();
    }
}
```

`Mapper<S, R>` mô tả quan hệ từ kiểu nguồn `S` sang kiểu kết quả `R`. `LengthMapper` cố định cả hai kiểu. `TextMapper<R>` cố định nguồn là `String` nhưng giữ kiểu kết quả mở; `TrimMapper` tiếp tục cố định kết quả thành `String`.

Giao diện kế thừa giao diện bằng `extends`; lớp thực hiện giao diện bằng `implements`. Một lớp có thể thực hiện nhiều giao diện tương thích. Tuy nhiên, không được thực hiện cùng một giao diện generic với hai đối số kiểu khác nhau, dù trực tiếp hay qua các nhánh kế thừa. Ví dụ sau cố tình không hợp lệ:

```java
// class Both implements Slot<String>, Slot<Integer> { ... }
```

Tránh thiết kế dựa vào việc quá tải hai bộ phương thức này để khắc phục; Java không cho phép quan hệ kiểu ấy ngay từ khai báo lớp.

## 6. Giới hạn kiểu phải được giữ đúng

Khi giao diện đặt giới hạn, đối số kiểu của lớp triển khai phải đáp ứng giới hạn đó:

```java
interface NumericSource<T extends Number> {
    T get();
}

class ConstantNumber<N extends Number> implements NumericSource<N> {
    private final N value;

    ConstantNumber(N value) {
        this.value = value;
    }

    @Override
    public N get() {
        return value;
    }
}
```

`N extends Number` bảo đảm `N` là đối số hợp lệ của `NumericSource<N>`. Nếu bỏ giới hạn ở lớp, `N` có thể là bất kỳ kiểu tham chiếu nào và không còn đáp ứng yêu cầu của giao diện. `ConstantNumber<Integer>` hợp lệ; `ConstantNumber<String>` không hợp lệ.

Giới hạn `extends Number` áp dụng cho lớp con hoặc chính `Number`, không có nghĩa là cho phép dùng kiểu nguyên thủy. Đối số kiểu phải là kiểu tham chiếu: dùng `Integer`, không dùng `int`. Trong ví dụ chạy đầy đủ, `count.set(3)` hợp lệ vì Java boxing giá trị `int` thành `Integer`.

## 7. Những lỗi thiết kế và biên dịch thường gặp

### Nhầm quan hệ kiểu con của đối số với quan hệ kiểu con của giao diện

`Integer` là kiểu con của `Number`, nhưng `Slot<Integer>` không phải kiểu con của `Slot<Number>`:

```java
Slot<Integer> integers = new MemorySlot<>(1);
// Slot<Number> numbers = integers; // Lỗi biên dịch.
```

Nếu phép gán được cho phép, bên giữ `numbers` có thể gọi `set(1.5)`, đưa `Double` vào ô vốn chỉ chứa `Integer`. Đây là lý do tham số kiểu của các giao diện như `Slot<T>` có tính bất biến (invariance).

Nếu chỉ cần đọc một giá trị như `Number`, có thể dùng wildcard tại nơi sử dụng:

```java
Slot<? extends Number> source = integers;
Number value = source.get();
// source.set(2); // Không hợp lệ: chưa biết kiểu cụ thể được giữ kín là gì.
```

Wildcard diễn đạt khả năng ở tham chiếu sử dụng, không thay thế khai báo tham số kiểu và không được dùng trực tiếp như `class X implements Slot<?>`.

### Dùng tham số kiểu của giao diện trong thành viên static

Các trường của giao diện ngầm định là `public static final`. Chúng không phải trạng thái riêng của mỗi `Slot<String>` hay `Slot<Integer>`, nên không thể khai báo `T DEFAULT_VALUE` bằng tham số `T` của giao diện. Phương thức `static` cũng không được trực tiếp dùng `T` ấy. Nếu phương thức static cần generic, nó phải tự khai báo tham số kiểu riêng.

Trạng thái `private T value` trong bài được đặt ở **lớp triển khai**, nơi mỗi đối tượng sở hữu giá trị của mình.

### Nghĩ rằng luôn có thể tạo đối tượng của T

`new T()` không hợp lệ. Hợp đồng generic không bảo đảm `T` là lớp cụ thể có constructor không tham số. Hãy nhận giá trị ban đầu qua constructor như `MemorySlot<T>`, hoặc thiết kế nhận một đối tượng tạo giá trị khi bài toán thật sự cần. Không dùng ép kiểu tùy tiện để che lỗi này.

### Nhầm generic với một lớp runtime riêng cho mỗi đối số kiểu

Java dùng cơ chế xóa kiểu (type erasure). Việc chọn `Slot<String>` không sinh ra một phiên bản lớp triển khai độc lập trong JVM cho riêng `String`. Trình biên dịch kiểm tra kiểu, chèn thao tác cần thiết và có thể tạo phương thức cầu nối (bridge method) để giữ quan hệ ghi đè sau xóa kiểu. Không cần tự viết các phương thức cầu nối.

Trong thiết kế và sử dụng bình thường, hãy giữ đầy đủ đối số kiểu ở các tham chiếu; không bỏ chúng để vượt qua lỗi kiểu. Tính an toàn mất đi nếu trộn dữ liệu không tương thích qua những đường không được kiểm tra kiểu.

## 8. Tự thực hành

1. Từ chương trình đầy đủ, thêm `Slot<Double>` dùng `MemorySlot<>`, gán `2.5` rồi đọc lại. Xác định vị trí khai báo hợp đồng và vị trí lựa chọn cách lưu trữ.
2. Đổi `MemorySlot<T>` thành `MemorySlot<E>` và cập nhật các chỗ dùng tham số ấy. Chương trình phải giữ nguyên hành vi: tên tham số kiểu chỉ có ý nghĩa trong phạm vi khai báo.
3. Tạo `UpperTextSlot implements Slot<String>`: chuẩn hóa chuỗi bằng `toUpperCase(java.util.Locale.ROOT)` trong `set`. Kiểm tra chuỗi `"java"` được đọc thành `"JAVA"`; nêu rõ chính sách đối với `null`.
4. Thử bỏ `public` ở `get()` rồi biên dịch để quan sát lỗi về mức truy cập. Khôi phục trước khi chạy.
5. Giải thích vì sao `Slot<String>` có thể nhận đối tượng `TrimmedTextSlot`, còn `Slot<Object>` không thể nhận chính đối tượng ấy chỉ vì `String` là kiểu con của `Object`.

Sau bài này, cần phân biệt được ba quyết định: giao diện đặt ra quan hệ kiểu nào, lớp triển khai giữ hay cố định tham số kiểu ra sao, và bên sử dụng nên phụ thuộc vào hợp đồng nào. Ba quyết định đó giúp tái sử dụng mã mà trình biên dịch vẫn kiểm tra được dữ liệu đi vào và đi ra.

## Tài liệu đối chiếu

- [JLS §9.1.2 — Generic Interfaces and Type Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.1.2): khai báo và phạm vi tham số kiểu của giao diện.
- [JLS §8.1.5 — Superinterfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.5): quan hệ giữa lớp và các giao diện được thực hiện.
- [JLS §9.4.1 — Inheritance and Overriding](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1): quy tắc thừa kế và ghi đè phương thức giao diện.
