# Kế thừa lớp generic với đối số kiểu cố định hoặc được truyền tiếp

## 1. Kế thừa cần quyết định hợp đồng kiểu của lớp cha

Một lớp generic như `Box<T>` mô tả hộp giữ giá trị kiểu `T`. Khi viết lớp con, ta cần xác định lớp con là **hộp của kiểu nào**: một hộp chỉ dành cho chuỗi, hay một họ hộp tiếp tục cho người sử dụng chọn kiểu phần tử?

Hai khai báo sau thể hiện hai quyết định khác nhau:

- `class TextBox extends Box<String>`: lớp con dành riêng cho chuỗi.
- `class ForwardBox<U> extends Box<U>`: lớp con truyền tiếp kiểu được chọn.

`TextBox` cố định đối số kiểu của lớp cha thành `String`. `ForwardBox<U>` tự khai báo tham số kiểu `U` rồi truyền nó vào vị trí `T` của `Box`. Việc dùng tên `U` thay vì `T` làm rõ rằng tham số của lớp con và tham số trong khai báo lớp cha là hai khai báo khác nhau, được nối với nhau bằng `extends Box<U>`.

Đây là những quy tắc vẫn dùng trong Java hiện hành. Ví dụ đầy đủ trong bài chạy bằng JDK 17 trở lên.

| Kiểu lớp con | Lớp cha tương ứng | Ai chọn kiểu giá trị? |
| --- | --- | --- |
| `TextBox` | `Box<String>` | Người thiết kế `TextBox` cố định là `String` |
| `ForwardBox<Integer>` | `Box<Integer>` | Người sử dụng chọn `Integer` cho `U` |
| `ForwardBox<String>` | `Box<String>` | Người sử dụng chọn `String` cho `U` |
| `ListBox<Integer>` với `extends Box<List<E>>` | `Box<List<Integer>>` | Người sử dụng chọn `E`; lớp con quy định cách ghép thành `List<E>` |

Không phải cứ lớp cha generic thì lớp con bắt buộc generic. Lớp con chỉ generic khi chính khai báo của nó có tham số kiểu.

## 2. Lớp cha dùng chung

Đoạn sau là lớp cha được dùng trong các ví dụ. Khi đặt bên trong lớp chạy mẫu ở mục 7, thêm `static` như chương trình đầy đủ.

```java
class Box<T> {
    private T value;

    Box(T initial) {
        this.value = initial;
    }

    public T get() {
        return value;
    }

    public void set(T next) {
        value = next;
    }
}
```

Trường `value` thuộc phần trạng thái do `Box` quản lý. Nó là `private`, nên lớp con không tự truy cập trực tiếp bằng tên trường; lớp con sử dụng các phương thức được phép truy cập như `get()` và `set(...)`.

Lớp cha không đánh dấu `final` vì bài này cần cho phép kế thừa. Trong mã thực tế, việc được phép mở rộng còn chịu những quy tắc thông thường về quyền truy cập, `final` hoặc `sealed`; có generic không bỏ qua các quy tắc ấy.

## 3. Cố định đối số kiểu: lớp con dành riêng cho chuỗi

```java
class TextBox extends Box<String> {
    TextBox(String initial) {
        super(initial.strip());
    }

    @Override
    public void set(String next) {
        super.set(next.strip());
    }

    int length() {
        return get().length();
    }
}
```

Trong `extends Box<String>`, đối số `String` thay vào các vị trí dùng `T` của lớp cha khi kiểm tra kiểu thành viên cho lớp con này. Vì vậy `get()` được dùng như phương thức trả về `String`, còn `set(...)` nhận `String`.

`TextBox` bổ sung quy tắc bỏ khoảng trắng đầu/cuối khi tạo hoặc cập nhật dữ liệu. Hàm tạo chuẩn hóa trực tiếp trước khi gọi `super`; hàm tạo `Box` chỉ gán trường và không gọi phương thức có thể bị ghi đè. Với ví dụ này, truyền `null` vào hàm tạo hoặc `set` sẽ gây `NullPointerException` tại `strip()`; nếu cần chấp nhận `null`, phải thiết kế quy tắc xử lý riêng.

Có thể dùng đối tượng lớp con thông qua lớp cha:

```java
TextBox text = new TextBox(" Java ");
Box<String> view = text;
view.set(" Generics ");
String result = view.get();
```

`text` và `view` cùng tham chiếu tới một đối tượng `TextBox`. Khi gọi `view.set(...)`, cơ chế chọn phương thức của đối tượng vẫn chạy bản ghi đè của `TextBox`, nên chuỗi được chuẩn hóa. Generic quyết định hợp đồng kiểu; đa hình quyết định phần triển khai phương thức được chạy.

`TextBox` không khai báo tham số kiểu riêng, do đó không viết `TextBox<String>` và không dùng `new TextBox<>(...)`. Chỉ viết `new TextBox(...)`; đối số `String` của lớp cha đã được cố định trong khai báo lớp con.

Nếu cần kiểu `T` xuất hiện trong mã của lớp con, phải có một khai báo `T` thuộc phạm vi hợp lệ. Không thể dùng tên `T` của `Box<T>` như thể nó tự được đưa vào phạm vi tên của `TextBox`; ở đây kiểu cụ thể cần dùng là `String`.

## 4. Truyền tiếp đối số kiểu: lớp con vẫn generic

```java
class ForwardBox<U> extends Box<U> {
    ForwardBox(U initial) {
        super(initial);
    }
}
```

`U` được khai báo bởi `ForwardBox<U>`. Cụm `extends Box<U>` nói rằng bất cứ kiểu nào được chọn cho `U` cũng được dùng làm đối số kiểu của lớp cha.

Với `ForwardBox<Integer>`, đường truyền là:

```text
ForwardBox<U> extends Box<U>
          U = Integer
             ↓
ForwardBox<Integer> → Box<Integer>
```

Người sử dụng không chọn hai kiểu độc lập cho lớp con và lớp cha trong khai báo này. Một khi chọn `ForwardBox<Integer>`, quan hệ với `Box<Integer>` được xác định bởi chính `extends`.

```java
ForwardBox<Integer> count = new ForwardBox<>(3);
Box<Integer> view = count;
view.set(5);
Integer result = count.get();
```

Nếu đổi tham số lớp con từ `U` sang `T` ở mọi vị trí liên quan thì ý nghĩa không đổi. Tên tham số không tự tạo quan hệ kế thừa; biểu thức kiểu được ghi sau `extends` mới quy định quan hệ đó.

Nếu viết `class Child<U> extends Box<String>`, thì `U` không được truyền vào `Box`; lớp cha vẫn là `Box<String>`. Một lớp con có thể có tham số kiểu riêng phục vụ việc khác, nên cần đọc toàn bộ khai báo thay vì đoán từ việc thấy `<U>`.

## 5. Lớp con có thể biến đổi hoặc cố định một phần đối số

### 5.1. Ghép tham số thành một kiểu khác

Không bắt buộc truyền nguyên một tham số vào lớp cha. Có thể dùng nó để tạo một kiểu tham số hóa lồng nhau:

```java
class ListBox<E> extends Box<List<E>> {
    ListBox(List<E> initial) {
        super(initial);
    }

    int size() {
        return get().size();
    }
}
```

Đoạn này cần `import java.util.List;`. Với `ListBox<Integer>`, giá trị mà hộp giữ là **một danh sách số nguyên**, nên kiểu cha là `Box<List<Integer>>`, không phải `Box<Integer>`.

Có hai tầng ý nghĩa khác nhau: `E` là kiểu từng phần tử trong danh sách; đối số kiểu của `Box` là cả `List<E>`. Do đó `get()` trả về danh sách, `size()` đếm phần tử, còn `set(...)` thay cả danh sách. Nó không trở thành một phương thức thêm một số vào danh sách.

Trong ví dụ này, `ListBox` giữ tham chiếu danh sách được truyền vào, không tự sao chép hoặc bảo đảm danh sách bất biến. Nếu đối tượng danh sách cho phép sửa và còn có nơi khác giữ tham chiếu tới nó, thay đổi ở nơi đó có thể được quan sát qua hộp. Generic không thay thế chính sách sở hữu dữ liệu.

### 5.2. Cố định một phần khi lớp cha có nhiều tham số

Với lớp cha có kiểu khóa và kiểu giá trị riêng, lớp con có thể cố định khóa thành `String` rồi tiếp tục cho chọn kiểu giá trị:

```java
class Entry<K, V> {
    private final K key;
    private final V value;

    Entry(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}

class StringKeyEntry<V> extends Entry<String, V> {
    StringKeyEntry(String key, V value) {
        super(key, value);
    }
}
```

`StringKeyEntry<Integer>` có kiểu cha `Entry<String, Integer>`. Phần khóa đã được cố định trong thiết kế lớp con; phần giá trị được truyền tiếp từ người sử dụng. Số lượng và thứ tự đối số sau tên lớp cha phải khớp khai báo của lớp cha.

### 5.3. Truyền tiếp phải đáp ứng giới hạn

Nếu lớp cha yêu cầu `T extends Number`, tham số được truyền tiếp phải có giới hạn đủ để bảo đảm điều đó:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class MeasuredBox<N extends Number> extends NumberBox<N> {
    MeasuredBox(N value) {
        super(value);
    }
}
```

Nếu bỏ `extends Number` khỏi khai báo `N` của `MeasuredBox`, mã không biên dịch: khi ấy `N` có thể là `String`, trong khi `NumberBox` không chấp nhận đối số kiểu như vậy. Cần chứng minh quan hệ giới hạn ngay tại khai báo, không đợi đến khi một nơi sử dụng chọn `Integer`.

## 6. Kiểu con và ghi đè sau khi thay đối số kiểu

`TextBox` là kiểu con của `Box<String>`. `ForwardBox<Integer>` là kiểu con của `Box<Integer>`. Đây là các quan hệ xuất phát từ khai báo kế thừa.

Tuy nhiên, từ việc `String` là kiểu con của `Object` không suy ra `Box<String>` là kiểu con của `Box<Object>`. Vì vậy đoạn sau cố ý không hợp lệ:

```java
Box<String> strings = new TextBox("Java");
// Box<Object> objects = strings; // Lỗi biên dịch nếu bỏ dấu chú thích
```

Nếu phép gán bị cấm này được chấp nhận, có thể gọi `objects.set(42)` để đưa một số vào hộp vốn được hứa chỉ nhận chuỗi. Các lần tham số hóa với đối số cụ thể như vậy có tính bất biến (invariance). Đừng nhầm tính bất biến giữa hai lần tham số hóa với quan hệ lớp con đã được khai báo rõ bằng `extends`.

Khi ghi đè phương thức, hãy xét chữ ký sau khi áp dụng đối số kiểu cho lớp cha. Trong `TextBox extends Box<String>`, ghi đè phương thức cập nhật bằng `public void set(String next)`, không thêm một tham số kiểu phương thức mới như `<T> void set(T next)` để giả vờ thay thế nó.

Dùng `@Override` giúp trình biên dịch xác nhận ý định ghi đè. Các quy tắc thông thường vẫn áp dụng: không giảm quyền truy cập của phương thức được ghi đè, và giá trị trả về phải tương thích theo quy tắc ghi đè. Đặc biệt, thay `set(String)` bằng `set(Integer)` không làm nó nhận được vai trò của phương thức cha.

Đối chiếu khai báo lớp cha tại [JLS §8.1.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.4), quan hệ kiểu con tại [JLS §4.10.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.2), và quy tắc ghi đè tại [JLS §8.4.8.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.1).

## 7. Chương trình chạy đầy đủ

Lưu thành `GenericInheritanceDemo.java`:

```java
import java.util.List;

public class GenericInheritanceDemo {
    static class Box<T> {
        private T value;

        Box(T initial) {
            this.value = initial;
        }

        public T get() {
            return value;
        }

        public void set(T next) {
            value = next;
        }
    }

    static final class TextBox extends Box<String> {
        TextBox(String initial) {
            super(initial.strip());
        }

        @Override
        public void set(String next) {
            super.set(next.strip());
        }

        int length() {
            return get().length();
        }
    }

    static final class ForwardBox<U> extends Box<U> {
        ForwardBox(U initial) {
            super(initial);
        }
    }

    static final class ListBox<E> extends Box<List<E>> {
        ListBox(List<E> initial) {
            super(initial);
        }

        int size() {
            return get().size();
        }
    }

    public static void main(String[] args) {
        TextBox text = new TextBox(" Java ");
        Box<String> textView = text;
        textView.set(" Generics ");
        System.out.println("text=" + text.get());
        System.out.println("length=" + text.length());

        ForwardBox<Integer> count = new ForwardBox<>(3);
        Box<Integer> countView = count;
        countView.set(5);
        System.out.println("count=" + count.get());

        ListBox<Integer> scores = new ListBox<>(List.of(8, 9));
        Box<List<Integer>> scoresView = scores;
        scoresView.set(List.of(10, 7, 9));
        System.out.println("scores=" + scores.get());
        System.out.println("size=" + scores.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all GenericInheritanceDemo.java
java GenericInheritanceDemo
```

Stdout:

```text
text=Generics
length=8
count=5
scores=[10, 7, 9]
size=3
```

Ba phép gán sang biến lớp cha giữ nguyên tham chiếu tới các đối tượng lớp con. Việc cập nhật qua `textView`, `countView` và `scoresView` được quan sát qua các biến lớp con tương ứng. Với `textView`, phương thức ghi đè vẫn chuẩn hóa chuỗi; với `scoresView`, giá trị cập nhật là cả `List<Integer>`.

`textView` có kiểu tĩnh `Box<String>`, nên không thể trực tiếp gọi `textView.length()` dù đối tượng thật là `TextBox`. Kiểu tĩnh quyết định tập thao tác có thể gọi từ biến; kiểu đối tượng lúc chạy quyết định bản ghi đè của các phương thức đa hình.

## 8. Hàm tạo, chuỗi kế thừa và lỗi khai báo

### 8.1. Hàm tạo không được kế thừa

`Box(T initial)` không tự trở thành một hàm tạo của `TextBox` hoặc `ForwardBox<U>`. Lớp con tự khai báo hàm tạo của mình rồi gọi hàm tạo lớp cha phù hợp bằng `super(...)`.

Vì `Box` trong bài chỉ có hàm tạo nhận một đối số, nếu lớp con không có lời gọi hàm tạo cha phù hợp thì không thể trông chờ một hàm tạo không đối số của `Box` tự xuất hiện. Các ví dụ gọi `super(...)` rõ ràng; cách viết này chạy được với JDK 17 trở lên.

Hàm tạo `TextBox(String initial)` dùng `String` vì lớp cha đã cố định kiểu đó. Hàm tạo `ForwardBox(U initial)` dùng `U` của lớp con và truyền giá trị tương thích vào `Box<U>`.

### 8.2. Đọc lần lượt qua nhiều tầng

Giả sử có chuỗi khai báo `Middle<U> extends Box<U>` và `FinalText extends Middle<String>`. Khi đọc quan hệ, thay `U` bằng `String` ở tầng `Middle` rồi tiếp tục đi lên: `FinalText` có quan hệ kiểu con với `Middle<String>` và `Box<String>`.

Tương tự, nếu lớp trung gian khai báo `Middle<U> extends Box<List<U>>`, chọn `Middle<Integer>` sẽ dẫn tới `Box<List<Integer>>`. Cần giữ nguyên toàn bộ biểu thức kiểu, không bỏ mất tầng `List` khi đi qua chuỗi kế thừa.

### 8.3. Không bỏ qua khai báo tham số hoặc dùng wildcard làm lớp cha

Trong một khai báo lớp bình thường, `class Child extends Box<T>` không hợp lệ nếu `T` chưa được khai báo trong phạm vi phù hợp. Muốn truyền tiếp, cần khai báo `class Child<T> extends Box<T>`; muốn cố định, cần ghi một kiểu như `Box<String>`.

Không viết `class Child extends Box<?>`. Lớp cha trực tiếp trong khai báo `extends` không được dùng wildcard làm đối số kiểu ở vị trí đó. Nếu cần để kiểu mở cho người sử dụng, khai báo một tham số kiểu của lớp con rồi truyền tiếp nó.

Cũng không viết `extends Box<>`: dấu diamond dùng trong những biểu thức tạo đối tượng phù hợp, không thay thế danh sách đối số kiểu của lớp cha trong khai báo lớp.

### 8.4. Chỉ kế thừa khi quan hệ thay thế có ý nghĩa

Quan hệ `TextBox` là một `Box<String>` có ý nghĩa vì nó giữ hợp đồng nhận/trả chuỗi và thêm hành vi phù hợp. Đừng tạo lớp con chỉ để tiết kiệm vài dòng khởi tạo nếu nó không có vai trò hoặc hành vi riêng. Khi một đối tượng chỉ cần **có một** `Box<T>` bên trong, thiết kế chứa một trường `Box<T>` có thể rõ hơn.

Generic không cho phép một lớp mở rộng hai lớp cha. Quy tắc một lớp cha trực tiếp của Java vẫn giữ nguyên; lựa chọn đối số kiểu không tạo ra cơ chế đa kế thừa lớp.

## 9. Tự kiểm tra

1. `class Names extends Box<String>` có khiến `Names` trở thành lớp generic không?
2. Với `class Child<X> extends Box<X>`, kiểu cha của `Child<Integer>` là gì?
3. Với `class Groups<E> extends Box<List<E>>`, `get()` từ `Groups<String>` được dùng với kiểu trả về nào?
4. Vì sao `TextBox` có thể gán cho `Box<String>` nhưng không thể gán trực tiếp cho `Box<Object>`?
5. Nếu cha khai báo `Parent<T extends Number>`, lớp con truyền tiếp `U` cần điều kiện nào?

Đáp án:

1. Không. `Names` không tự khai báo tham số kiểu; lớp cha của nó đã được tham số hóa bằng `String`.
2. `Box<Integer>`.
3. `List<String>`.
4. Quan hệ thứ nhất được khai báo bởi `extends Box<String>`; quan hệ thứ hai không tồn tại vì `Box<String>` không là kiểu con của `Box<Object>`.
5. `U` phải thỏa mãn giới hạn của cha, chẳng hạn khai báo `Child<U extends Number> extends Parent<U>`.

Khi gặp `extends` với generic, hãy xác định tham số nào thuộc lớp con, đối số nào đã cố định, rồi thay đối số theo từng tầng để đọc đúng hợp đồng lớp cha. Từ đó mới quyết định hàm tạo, kiểu đầu vào/đầu ra và phương thức có thể ghi đè.
