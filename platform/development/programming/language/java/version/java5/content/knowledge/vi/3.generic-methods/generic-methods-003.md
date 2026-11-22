# Hàm tạo generic và phạm vi tham số kiểu riêng

## 1. Khi kiểu chỉ cần cho quá trình tạo đối tượng

Một đối tượng có thể nhận dữ liệu đầu vào thuộc nhiều kiểu nhưng sau khi được tạo chỉ giữ một biểu diễn cố định. Ví dụ, một bản chụp văn bản có thể được tạo từ danh sách số hoặc danh sách từ; sau khi định dạng xong, đối tượng chỉ cần giữ danh sách chuỗi.

Không nhất thiết biến cả lớp thành generic chỉ để diễn đạt kiểu của dữ liệu đầu vào. Java cho phép **hàm tạo generic** (generic constructor): hàm tạo tự khai báo tham số kiểu phục vụ quan hệ giữa các đối số trong quá trình tạo đối tượng.

Tiêu chí nhận biết là danh sách tham số kiểu nằm **trước tên hàm tạo**:

```java
public <E> Snapshot(List<E> source, Function<E, String> formatter) {
    List<String> result = new ArrayList<>();
    for (E item : source) {
        result.add(formatter.apply(item));
    }
    this.lines = List.copyOf(result);
}
```

Đây là đoạn thành viên minh họa trong một lớp `Snapshot` có trường `List<String> lines`, cần các import `List`, `ArrayList` và `Function`. Chương trình hoàn chỉnh nằm ở mục 6.

`E` nối kiểu phần tử của `source` với kiểu đầu vào mà `formatter` nhận. Với nguồn số nguyên, hàm định dạng phải nhận được phần tử theo hợp đồng tương ứng; với nguồn chuỗi, có thể dùng một hàm xử lý chuỗi. Sau chuyển đổi, lớp chỉ lưu `List<String>`.

`Snapshot` ở đây không khai báo tham số kiểu cấp lớp. Cùng một lớp có thể được tạo qua nhiều lần gọi hàm tạo, mỗi lần chọn một `E` khác nhau, nhưng kiểu của các biến kết quả đều là `Snapshot`.

Cơ chế này vẫn có trong Java hiện hành. Các ví dụ trong bài dùng JDK 17 trở lên.

## 2. Phân biệt ba nơi khai báo generic

| Nơi khai báo | Dạng minh họa | Tham số thuộc về đâu? |
| --- | --- | --- |
| Lớp generic | `class Holder<T>` | `T` là tham số của lớp |
| Phương thức generic | `<R> R identity(R value)` | `R` là tham số của phương thức |
| Hàm tạo generic | `<S> Holder(S source)` | `S` là tham số của hàm tạo |

Các dạng trong bảng minh họa vị trí cú pháp; muốn viết mã chạy phải cung cấp đầy đủ chữ ký và thân tương ứng.

Một hàm tạo dùng tham số kiểu của lớp không tự trở thành hàm tạo generic. Ví dụ:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}
```

`Holder(T value)` dùng `T` của lớp, nhưng không tự khai báo danh sách `<...>` riêng. Ngược lại, `public <E> Snapshot(...)` tự khai báo `E` nên là hàm tạo generic dù lớp `Snapshot` không generic.

Hàm tạo không có kiểu trả về. Không viết `public <E> E Snapshot(...)`: thêm `E` vào vị trí kiểu trả về không làm hàm tạo trả về dữ liệu kiểu `E`; nó khiến khai báo mang dạng một phương thức có tên giống lớp. Biểu thức `new Snapshot(...)` tạo đối tượng `Snapshot`, không tạo đối tượng kiểu `E`.

Đối chiếu định nghĩa tại [JLS §8.8.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.4): hàm tạo có thể generic độc lập với việc lớp chứa nó có generic hay không.

## 3. Phạm vi của tham số kiểu hàm tạo

Với `<E> Snapshot(List<E> source, Function<E, String> formatter)`, tên `E` dùng được trong phạm vi khai báo hàm tạo đó, bao gồm kiểu của đối số và mã trong thân hàm tạo theo các quy tắc phạm vi của Java.

Ví dụ vòng lặp `for (E item : source)` dùng cùng `E` đã khai báo trước tên hàm tạo. Không cần và không được khai báo thêm một `E` mới cho mỗi vị trí sử dụng.

Tuy nhiên, `E` không trở thành tham số kiểu cấp lớp. Đoạn sau cố ý không hợp lệ:

```java
class InvalidScope {
    private E saved; // Lỗi: E chưa được khai báo ở phạm vi trường

    <E> InvalidScope(E source) {
        E local = source;
    }
}
```

Khai báo `<E>` trên hàm tạo không đưa tên `E` vào phạm vi của các trường hay những phương thức khác trong lớp. Muốn một trường giữ dữ liệu với kiểu được chọn và công khai kiểu đó qua API sau khi tạo đối tượng, thường cần tham số kiểu cấp lớp như `class Holder<E>`.

Việc tên `E` chỉ thuộc phạm vi hàm tạo không có nghĩa giá trị đầu vào bắt buộc biến mất sau khi hàm tạo kết thúc. Có thể lưu dữ liệu dưới một kiểu trường hợp lệ như `Object`, một interface thích hợp, hoặc chuyển sang biểu diễn khác như `String`; điều bị giới hạn là **phạm vi tên kiểu và hợp đồng kiểu**, không phải sự tồn tại của đối tượng đầu vào.

Mỗi hàm tạo hoặc phương thức có danh sách tham số kiểu riêng tạo ra phạm vi riêng. Hai hàm tạo đều dùng tên `E` không chia sẻ một biến kiểu chung. Nếu không ghi giới hạn, `E` có giới hạn trên mặc định là `Object`; thân hàm tạo không được giả định `E` luôn là `String` để gọi các phương thức riêng của chuỗi.

Có thể đặt giới hạn, chẳng hạn `<N extends Number>`, khi hợp đồng tạo đối tượng chỉ chấp nhận các kiểu phù hợp với `Number`. Nhưng nếu chỉ cần nhận một `Number` và không cần nối kiểu với đối số khác, một hàm tạo nhận `Number` trực tiếp có thể đơn giản hơn việc thêm tham số kiểu.

Tham khảo phạm vi tên tại [JLS §6.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3).

## 4. Hàm tạo generic bên trong lớp generic

Một lớp có thể cần giữ kiểu giá trị trong suốt quá trình sử dụng, đồng thời chỉ cần kiểu của khóa đầu vào trong lúc tạo đối tượng. Khi đó dùng hai tham số ở hai cấp khác nhau:

```java
static final class Labelled<T> {
    private final String label;
    private final T value;

    public <K> Labelled(K key, Function<K, String> formatKey, T value) {
        this.label = formatKey.apply(key);
        this.value = value;
    }

    String label() {
        return label;
    }

    T value() {
        return value;
    }
}
```

Đoạn này đặt trong một lớp bao ngoài và cần `import java.util.function.Function;`. `Function<A, B>` mô tả hàm nhận đầu vào kiểu `A` và cho kết quả kiểu `B`.

`T` được khai báo bởi lớp `Labelled<T>`, dùng cho trường và kiểu trả về `value()`. `K` được khai báo bởi hàm tạo, nối kiểu của `key` với kiểu đầu vào của `formatKey`. Sau khi tạo, khóa được biểu diễn thành trường `String label`; các phương thức của lớp không cần biết tên kiểu `K`.

Ví dụ một đối tượng `Labelled<String>` có thể tạo nhãn từ một số `Integer` và giữ giá trị `String` là `"ready"`. Một đối tượng `Labelled<String>` khác có thể tạo nhãn từ khóa `String` và giữ `"queued"`. Hai đối tượng có cùng kiểu giá trị công khai nhưng nhận kiểu khóa đầu vào khác nhau.

Không có quan hệ tự động giữa `K` và `T`. Nếu muốn gán trực tiếp một giá trị `K` vào trường `T`, trình biên dịch cần có một quan hệ kiểu phù hợp; chỉ vì cả hai cùng là chữ cái generic không khiến chúng tương thích.

### Tránh khai báo trùng tên với tham số của lớp

Trong `class Holder<T>`, một hàm tạo có danh sách `<T>` riêng sẽ khai báo một `T` mới và che tên `T` của lớp trong phạm vi hàm tạo. Hai tên giống nhau nhưng không chỉ cùng một tham số kiểu.

Điều đó dễ dẫn tới việc đối số hàm tạo mang `T` của hàm tạo nhưng trường mang `T` của lớp, khiến phép gán không hợp lệ. Chọn tên khác như `K`, `S` giúp đọc rõ nguồn khai báo; nếu muốn dùng đúng `T` của lớp thì không khai báo lại `<T>` trên hàm tạo.

## 5. Suy luận và truyền đối số kiểu tường minh

### 5.1. Để trình biên dịch suy luận

Với lớp `Snapshot` không generic:

```java
Snapshot numbers = new Snapshot(List.of(10, 15), Integer::toHexString);
```

Trong ngữ cảnh này, trình biên dịch suy luận tham số kiểu của hàm tạo từ nguồn và hàm định dạng. Không có đối số kiểu cấp lớp cần cung cấp cho `Snapshot`.

Với lớp `Labelled<T>` generic:

```java
Labelled<String> item = new Labelled<>(7, n -> "row-" + n, "ready");
```

`<>` sau `Labelled` liên quan tới đối số kiểu **của lớp**. Tham số kiểu riêng `K` của hàm tạo cũng được suy luận từ các ràng buộc của lần gọi. Đây là hai nhóm tham số khác nhau, dù cùng tham gia một biểu thức tạo đối tượng.

### 5.2. Chỉ rõ đối số kiểu của hàm tạo

Đối số kiểu tường minh của hàm tạo nằm **ngay sau từ khóa `new`**:

```java
Snapshot numbers =
        new <Integer> Snapshot(List.of(10, 15), Integer::toHexString);
```

`<Integer>` chọn `E` của hàm tạo. Không viết `new Snapshot<Integer>(...)`, vì `Snapshot` không phải lớp generic.

Nếu lớp cũng generic, phân biệt hai vị trí:

```java
Labelled<String> item =
        new <Integer> Labelled<String>(7, n -> "row-" + n, "ready");
```

- `<Integer>` sau `new` là đối số cho `K` của hàm tạo.
- `<String>` sau `Labelled` là đối số cho `T` của lớp.

Biểu thức tạo ra một `Labelled<String>`, không phải `Labelled<Integer>`.

Không kết hợp đối số kiểu hàm tạo tường minh với dấu diamond của lớp trong cùng biểu thức. Dạng `new <Integer> Labelled<>(...)` bị từ chối. Khi đã ghi rõ nhóm đối số kiểu của hàm tạo, dùng nhóm đối số kiểu lớp đầy đủ nếu lớp generic, như `Labelled<String>` ở ví dụ trên.

Trong mã thường ngày, suy luận thường đủ rõ. Cách viết tường minh hữu ích để giải thích hai phạm vi hoặc kiểm tra một ràng buộc cụ thể, không phải yêu cầu phải thêm mọi nơi.

Đối chiếu cú pháp và quy tắc diamond tại [JLS §15.9](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9).

## 6. Chương trình chạy đầy đủ

Lưu thành `GenericConstructorDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class GenericConstructorDemo {
    static final class Snapshot {
        private final List<String> lines;

        public <E> Snapshot(List<E> source, Function<E, String> formatter) {
            List<String> result = new ArrayList<>();
            for (E item : source) {
                result.add(formatter.apply(item));
            }
            this.lines = List.copyOf(result);
        }

        List<String> lines() {
            return lines;
        }
    }

    static final class Labelled<T> {
        private final String label;
        private final T value;

        public <K> Labelled(K key, Function<K, String> formatKey, T value) {
            this.label = formatKey.apply(key);
            this.value = value;
        }

        String label() {
            return label;
        }

        T value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Snapshot numbers = new <Integer> Snapshot(
                List.of(10, 15), Integer::toHexString);
        Snapshot words = new Snapshot(
                List.of("java", "type"), s -> s.length() + ":" + s);

        System.out.println("numbers=" + numbers.lines());
        System.out.println("words=" + words.lines());

        Labelled<String> first = new <Integer> Labelled<String>(
                7, n -> "row-" + n, "ready");
        Labelled<String> second = new Labelled<>(
                "A", s -> "row-" + s, "queued");

        System.out.println(first.label() + "=" + first.value());
        System.out.println(second.label() + "=" + second.value());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror GenericConstructorDemo.java
java GenericConstructorDemo
```

Stdout:

```text
numbers=[a, f]
words=[4:java, 4:type]
row-7=ready
row-A=queued
```

`numbers` dùng hàm tạo với `E = Integer`; hai số 10 và 15 được định dạng thành hệ thập lục phân. `words` suy luận `E = String` và tạo chuỗi có độ dài đứng trước. Dù nguồn khác nhau, cả hai đối tượng đều chỉ công khai danh sách chuỗi qua `lines()`.

`first` dùng `T = String` của lớp và `K = Integer` của hàm tạo. `second` vẫn có `T = String`, còn kiểu khóa được suy luận từ chuỗi `"A"`. Phương thức `value()` của cả hai trả về `String` theo kiểu tĩnh.

Trong `Snapshot`, `List.copyOf` tạo bản danh sách không cho sửa sau khi đã định dạng. Nó không chấp nhận phần tử `null`; một hàm định dạng trả về `null` có thể khiến hàm tạo thất bại. Generic không bảo đảm hàm định dạng luôn trả chuỗi khác `null` hay không ném ngoại lệ.

## 7. Lỗi thường gặp và cách kiểm tra

### 7.1. Cung cấp nguồn và hàm định dạng không tương thích

Với `Snapshot`, nếu nguồn là `List<String>` nhưng truyền một `Function<Integer, String>` thì hai đối số không thỏa mãn cùng quan hệ `E`. Đây là lỗi biên dịch, không phải một lời hứa rằng chương trình sẽ thử chuyển mọi chuỗi sang số lúc chạy.

Có thể thử trong `main` của chương trình trên:

```java
Function<Integer, String> hex = Integer::toHexString;
// Snapshot invalid = new Snapshot(List.of("10"), hex);
// Bỏ dấu chú thích ở dòng trên để quan sát lỗi biên dịch.
```

Muốn định dạng chuỗi như một số, cần cung cấp một hàm có đầu vào `String` và chuyển đổi nội dung một cách rõ ràng. Việc đó còn cần xử lý chuỗi không hợp lệ; tham số kiểu không tự thực hiện chuyển đổi dữ liệu.

### 7.2. Nhầm cú pháp hàm tạo với cú pháp phương thức generic

Phương thức generic có kiểu trả về, còn hàm tạo generic có tên lớp và không có kiểu trả về. Khi gọi phương thức generic tường minh, đối số kiểu đứng trước tên phương thức; khi dùng `new` với hàm tạo generic, nó đứng ngay sau `new`.

Hàm tạo không thể là `static`, và không được kế thừa thành hàm tạo của lớp con. Nếu hàm tạo lớp con gọi một hàm tạo generic của lớp cha qua `super(...)`, đó là một lời gọi tới hàm tạo cha; các tham số kiểu riêng vẫn thuộc khai báo hàm tạo cha, không tự biến thành tham số của lớp con.

### 7.3. Đổi tên tham số không tạo một overload mới

Hai hàm tạo có cùng dạng đối số nhưng chỉ đổi `<E>` thành `<S>` không tạo ra hai chữ ký khác nhau. Tương tự, không thể nạp chồng chỉ bằng việc đổi `List<String>` thành `List<Integer>` nếu chữ ký sau xóa kiểu bị trùng.

Khi nhiều cách tạo đối tượng có ý nghĩa khác nhau, cân nhắc đổi dạng đối số thực sự hoặc dùng những phương thức tạo đối tượng có tên rõ ràng. Một phương thức tạo đối tượng generic trả về `Labelled<T>` cũng có thể dễ đọc hơn cú pháp hai nhóm đối số kiểu tường minh.

### 7.4. Không thêm tham số kiểu khi nó không diễn đạt quan hệ

Hàm tạo `<E> Item(E source)` mà chỉ gọi `source.toString()` rồi lưu chuỗi có thể không cần generic; nhận `Object` có thể đã mô tả đủ yêu cầu. Trong `Snapshot`, generic hữu ích vì nó nối `List<E>` với `Function<E, String>`, giúp ngăn một hàm định dạng không phù hợp với nguồn.

Quyết định dùng generic nên dựa trên quan hệ kiểu cần bảo vệ. Việc thêm nhiều chữ cái trong `<...>` không tự làm API an toàn hoặc linh hoạt hơn.

## 8. Tự kiểm tra

1. Một lớp không generic có thể có hàm tạo generic không?
2. `Holder(T value)` trong `class Holder<T>` có tự khai báo tham số kiểu riêng không?
3. Trong `new <Integer> Labelled<String>(...)`, nhóm nào thuộc hàm tạo và nhóm nào thuộc lớp?
4. Có thể dùng `K` chỉ được khai báo trên hàm tạo làm kiểu của một trường khác trong lớp không?
5. Vì sao `Snapshot` cần quan hệ `E` giữa nguồn và hàm định dạng?

Đáp án:

1. Có. `Snapshot` trong chương trình là ví dụ.
2. Không. Nó dùng lại `T` của lớp; muốn là hàm tạo generic phải tự khai báo danh sách tham số kiểu.
3. `Integer` chọn tham số hàm tạo; `String` chọn tham số lớp. Đối tượng kết quả có kiểu `Labelled<String>`.
4. Không. Tên `K` không thuộc phạm vi khai báo trường; nếu cần giữ kiểu đó qua API thì phải thiết kế một tham số cấp lớp phù hợp.
5. Để mỗi phần tử lấy từ nguồn có kiểu phù hợp với đầu vào mà hàm định dạng nhận, thay vì chờ lỗi xảy ra khi chạy.

Khi đọc một hàm tạo generic, hãy tách tham số của lớp khỏi tham số của chính hàm tạo, rồi theo dõi nhóm nào cần xuất hiện trong API sau khi đối tượng được tạo. Cách phân biệt này giúp chọn đúng phạm vi cho từng quan hệ kiểu.
