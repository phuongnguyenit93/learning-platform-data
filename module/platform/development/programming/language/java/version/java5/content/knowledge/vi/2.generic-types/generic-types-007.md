# Tham số kiểu trong trường, hàm tạo và phương thức

## 1. Một tham số kiểu nối các phần của đối tượng với nhau

Một lớp lưu dữ liệu thường cần cùng một kiểu xuất hiện ở nhiều nơi: trường giữ giá trị, hàm tạo nhận giá trị ban đầu, phương thức đọc trả về giá trị và phương thức cập nhật nhận giá trị mới. Nếu những vị trí ấy không được nối bằng một hợp đồng kiểu, nơi sử dụng dễ truyền nhầm dữ liệu hoặc phải ép kiểu khi đọc.

Với `class Slot<T>`, tham số kiểu `T` diễn đạt mối liên hệ đó. `T` được khai báo **một lần ở cấp lớp** rồi được dùng trong các thành viên phù hợp. Khi sử dụng `Slot<String>`, các thao tác qua kiểu này được kiểm tra theo `String`; với `Slot<Integer>`, chúng được kiểm tra theo `Integer`.

Điểm quan trọng là phân biệt **dùng tham số kiểu đã có** với **khai báo tham số kiểu mới**. Một phương thức có kiểu trả về `T` chưa chắc là phương thức generic; một hàm tạo nhận `T` cũng chưa chắc tự khai báo tham số kiểu.

| Vị trí | Ví dụ trong lớp `Slot<T>` | Nguồn của tham số kiểu |
| --- | --- | --- |
| Trường của đối tượng | `private T value;` | Dùng `T` của lớp |
| Hàm tạo thông thường | `Slot(T value)` | Dùng `T` của lớp |
| Phương thức thông thường | `T get()` | Dùng `T` của lớp |
| Phương thức thông thường | `T replace(T next)` | Dùng `T` của lớp |
| Phương thức generic | `<R> Slot<R> map(Function<T, R> mapper)` | Dùng `T` của lớp và khai báo thêm `R` của phương thức |
| Phương thức generic `static` | `static <U> Slot<U> of(U value)` | Khai báo `U` riêng, không dùng `T` của lớp |

Các ví dụ trong bài dùng JDK 17 trở lên và những quy tắc generic vẫn được áp dụng trong Java hiện hành.

## 2. Tham số kiểu trong trường: đối tượng lưu gì?

Đây là đoạn minh họa thành viên lớp; chương trình đầy đủ nằm ở mục 7.

```java
static final class Slot<T> {
    private T value;

    Slot(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    T replace(T next) {
        T previous = value;
        value = next;
        return previous;
    }
}
```

`private T value` nói rằng trường `value` có kiểu do tham số `T` của lớp đại diện. Nó không tạo ra một đối tượng `T` và cũng không phải một giá trị có tên `T`. Mỗi đối tượng `Slot` có trường `value` riêng như các trường đối tượng thông thường.

Có thể dùng `T` bên trong một kiểu khác, chẳng hạn khai báo `private List<T> history;`. Khi đó quan hệ kiểu còn áp dụng tới phần tử trong danh sách. Việc khởi tạo danh sách, giới hạn kích thước và quản lý dữ liệu vẫn là trách nhiệm của mã trong lớp.

Trường không có cơ chế khai báo một danh sách tham số kiểu riêng tương tự phương thức. Cú pháp `private <T> T value;` là sai. Nếu muốn kiểu trường thay đổi theo từng lần tham số hóa của lớp, khai báo tham số ở lớp rồi sử dụng nó trong kiểu của trường.

Generic cũng không tự đưa ra điều kiện khác `null`. Nếu hàm tạo không kiểm tra, `new Slot<String>(null)` vẫn hợp lệ. Khi dữ liệu phải luôn có mặt, có thể kiểm tra bằng `Objects.requireNonNull` trong hàm tạo và những đường cập nhật liên quan; chỉ ghi `T` không đủ để bảo đảm điều đó.

## 3. Tham số kiểu trong hàm tạo thông thường

Hàm tạo ở ví dụ trên là:

```java
Slot(T value) {
    this.value = value;
}
```

Hàm tạo có cùng tên với lớp và không có kiểu trả về. Tên khai báo là `Slot`, không viết `Slot<T>(...)` như thể đó là tên hàm tạo.

`T` trong danh sách đối số được lấy từ khai báo `class Slot<T>`. Bản thân hàm tạo này **không khai báo thêm tham số kiểu**, nên không được gọi là hàm tạo generic chỉ vì nó nhận một giá trị có kiểu `T`.

Khi viết:

```java
Slot<String> title = new Slot<>("Java");
```

Trình biên dịch kiểm tra việc tạo một `Slot<String>` trong ngữ cảnh này và kiểm tra chuỗi `"Java"` tương thích với đối số hàm tạo. Dấu `<>` hỗ trợ suy luận đối số kiểu của lớp; nó không bổ sung một tham số kiểu mới cho hàm tạo.

Một biểu thức khác cũng hợp lệ là:

```java
Slot<Number> amount = new Slot<>(10);
amount.replace(2.5);
```

Đối số kiểu của lớp được chọn là `Number`. Giá trị `10` được đóng hộp thành `Integer` rồi dùng như một `Number`; giá trị `2.5` được đóng hộp thành `Double`, cũng tương thích với `Number`. Hàm tạo không khóa kiểu của đối tượng thành `Integer` chỉ vì giá trị đầu tiên là số nguyên.

Ngược lại, nếu biến có kiểu `Slot<String>`, truyền một số vào hàm tạo hoặc vào `replace` sẽ vi phạm hợp đồng kiểu và bị từ chối khi biên dịch.

## 4. Tham số kiểu trong phương thức của đối tượng

### 4.1. Dùng `T` của lớp

Với `T get()` và `T replace(T next)`, phương thức dùng lại `T` đã được khai báo ở lớp. Hai phương thức này không có danh sách `<...>` riêng trước kiểu trả về, nên **không phải phương thức generic theo nghĩa tự khai báo tham số kiểu**.

Từ một biến `Slot<String>`, nơi sử dụng thấy `get()` trả về `String`; `replace(...)` nhận một `String` và trả về giá trị `String` trước đó. Quan hệ ấy được kiểm tra trong toàn bộ đường đi: nhận giá trị → lưu vào trường → đọc ra → trả về.

Tuy nhiên, thân lớp generic được kiểm tra dựa trên giới hạn khai báo của `T`. Với `class Slot<T>`, `T` mặc định có giới hạn trên là `Object`; không thể gọi `value.length()` trong thân lớp chỉ vì một nơi sử dụng sẽ chọn `Slot<String>`. Muốn một thao tác đặc thù, cần thiết kế một giới hạn phù hợp hoặc truyền hành vi xử lý vào lớp/phương thức.

### 4.2. Khai báo thêm một tham số kiểu của phương thức

Giả sử muốn chuyển giá trị thành một kiểu mới nhưng vẫn giữ `Slot` ban đầu. Có thể thêm phương thức sau vào lớp:

```java
<R> Slot<R> map(Function<T, R> mapper) {
    return new Slot<>(mapper.apply(value));
}
```

Đoạn này cần `import java.util.function.Function;`. Interface `Function<A, B>` mô tả phép chuyển từ đầu vào kiểu `A` sang kết quả kiểu `B`.

`<R>` nằm **trước kiểu trả về** để khai báo tham số kiểu riêng của phương thức. Trong cùng chữ ký, `T` vẫn là kiểu của lớp, còn `R` là kiểu kết quả của lần gọi chuyển đổi. Với `Slot<String>`, lời gọi `map(String::length)` có thể tạo `Slot<Integer>`; đối tượng ban đầu vẫn là `Slot<String>`.

Mỗi lần gọi có thể suy luận một `R` khác. Không có chuyện gọi phương thức với `R = Integer` rồi làm đổi `T` của đối tượng thành `Integer`. Phương thức đang tạo một đối tượng kết quả mới có hợp đồng riêng.

Chữ ký trên được giữ đơn giản để làm rõ phạm vi của `T` và `R`. API thư viện cần nhận các hàm chuyển đổi linh hoạt hơn có thể thiết kế thêm wildcard; đó là bước thiết kế riêng, không làm thay đổi việc tham số nào thuộc lớp và tham số nào thuộc phương thức.

## 5. Thành viên `static` cần tham số kiểu riêng

Thành viên `static` thuộc về lớp, không thuộc về một đối tượng `Slot<String>` hay `Slot<Integer>` cụ thể. Vì vậy không được dùng `T` của lớp làm kiểu của một trường `static` hoặc dùng nó trực tiếp trong chữ ký một phương thức `static`.

Đoạn sau cố ý sai, không thêm vào chương trình chạy đầy đủ:

```java
static final class BadSlot<T> {
    static T sharedValue; // Lỗi: dùng T của lớp trong ngữ cảnh static

    static T identity(T value) { // Lỗi cùng nguyên nhân
        return value;
    }
}
```

Không tồn tại một trường `sharedValue` kiểu `String` riêng cho `Slot<String>` và một trường kiểu `Integer` riêng cho `Slot<Integer>`. Thành viên `static` không được nhân bản theo các đối số kiểu.

Nếu cần một phương thức tạo đối tượng dùng được độc lập, khai báo tham số kiểu của **chính phương thức**:

```java
static <U> Slot<U> of(U value) {
    return new Slot<>(value);
}
```

`U` thuộc phương thức `of`, nên được phép dùng trong chữ ký và thân phương thức `static`. Ví dụ `Slot<Integer> count = Slot.of(5);` suy luận kiểu phù hợp cho lần gọi đó.

Ở nơi sử dụng, gọi thành viên `static` bằng tên lớp `Slot.of(...)`, không viết `Slot<String>.of(...)`. Nếu cần ghi rõ đối số kiểu của phương thức, cú pháp là `Slot.<Integer>of(5)`: danh sách `<Integer>` đứng trước tên phương thức và không phải đối số kiểu của một đối tượng lớp.

Tương tự, lớp lồng `static` có thể tự khai báo tham số kiểu của mình. Việc lớp `Slot<T>` trong chương trình là lớp lồng `static` không ngăn nó có trường đối tượng kiểu `T`; hạn chế nằm ở việc dùng tham số của phạm vi lớp bên ngoài từ ngữ cảnh `static`, không phải cấm mọi lớp `static` có generic.

Đối chiếu quy tắc thành viên lớp và phương thức generic tại [JLS §8.1.2, §8.3 và §8.4.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.2).

## 6. Hàm tạo có thể tự khai báo tham số kiểu

Ngoài hàm tạo dùng `T` của lớp, Java cho phép hàm tạo có danh sách tham số kiểu riêng. Ví dụ sau nhận một nguồn dữ liệu kiểu `S` và một hàm chuyển đổi từ `S` sang kiểu lưu trữ `T`:

```java
static final class Converted<T> {
    private final T value;

    <S> Converted(S source, Function<S, T> converter) {
        this.value = converter.apply(source);
    }

    T get() {
        return value;
    }
}
```

`T` thuộc lớp `Converted`; `S` được khai báo trước tên hàm tạo và chỉ thuộc hàm tạo đó. Hai tham số tạo ra quan hệ rõ ràng: kiểu của `source` phải phù hợp với đầu vào của hàm chuyển đổi, còn kết quả của hàm chuyển đổi phù hợp với kiểu trường `value`.

Có thể tạo một đối tượng lưu `Integer` từ nguồn `String`:

```java
Converted<Integer> parsed = new Converted<>("42", Integer::valueOf);
```

Hoặc ghi rõ cả đối số kiểu của hàm tạo lẫn đối số kiểu của lớp:

```java
Converted<Integer> parsed =
        new <String> Converted<Integer>("42", Integer::valueOf);
```

Trong cách viết thứ hai, `<String>` ngay sau `new` chọn `S` của hàm tạo; `<Integer>` sau `Converted` chọn `T` của lớp. Cách viết tường minh này dùng đối số kiểu của lớp đầy đủ, không kết hợp đối số kiểu hàm tạo tường minh với `<>`.

Hàm tạo vẫn không có kiểu trả về. Giá trị của biểu thức `new` là đối tượng `Converted<Integer>`, không phải `String`, dù hàm tạo khai báo `S = String`.

Tham số `S` không được dùng để khai báo một trường ở cấp lớp: sau khi hàm tạo hoàn tất, đối tượng lưu `T`; kiểu nguồn chỉ mô tả cách tạo đối tượng ở lần gọi ấy. Nếu lớp cần lưu nguồn với kiểu tĩnh riêng và sử dụng nó về sau, đó là yêu cầu thiết kế khác, có thể cần thêm tham số kiểu cấp lớp.

Không cần biến mọi hàm tạo thành generic. Chỉ khai báo tham số riêng khi nó diễn đạt được một quan hệ kiểu cần thiết mà hợp đồng hiện tại chưa diễn đạt được.

Đối chiếu khai báo và phạm vi của tham số kiểu hàm tạo tại [JLS §8.8.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.4) và [JLS §6.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3).

## 7. Chương trình chạy đầy đủ

Lưu vào tệp `MemberTypeParametersDemo.java`:

```java
import java.util.function.Function;

public class MemberTypeParametersDemo {
    static final class Slot<T> {
        private T value;

        Slot(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        T replace(T next) {
            T previous = value;
            value = next;
            return previous;
        }

        <R> Slot<R> map(Function<T, R> mapper) {
            return new Slot<>(mapper.apply(value));
        }

        static <U> Slot<U> of(U value) {
            return new Slot<>(value);
        }
    }

    static final class Converted<T> {
        private final T value;

        <S> Converted(S source, Function<S, T> converter) {
            this.value = converter.apply(source);
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Slot<String> title = new Slot<>("Java");
        String previous = title.replace("Generics");
        System.out.println("previous=" + previous);
        System.out.println("current=" + title.get());

        Slot<Integer> length = title.map(String::length);
        System.out.println("length=" + length.get());
        System.out.println("unchanged title=" + title.get());

        Slot<Integer> count = Slot.of(5);
        System.out.println("count=" + count.get());

        Slot<Number> amount = new Slot<>(10);
        amount.replace(2.5);
        System.out.println("amount=" + amount.get());

        Converted<Integer> parsed =
                new <String> Converted<Integer>("42", Integer::valueOf);
        System.out.println("parsed=" + parsed.get());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all MemberTypeParametersDemo.java
java MemberTypeParametersDemo
```

Stdout:

```text
previous=Java
current=Generics
length=8
unchanged title=Generics
count=5
amount=2.5
parsed=42
```

`replace` nhận và trả về cùng `T` của đối tượng. `map` có thêm `R`, nên có thể tạo đối tượng kết quả chứa kiểu khác. `of` dùng `U` của phương thức `static`. Hàm tạo `Converted` dùng `S` cho nguồn và `T` cho dữ liệu đã chuyển đổi.

Trong ví dụ này, chuỗi `"42"` được chuyển thành số hợp lệ. Nếu truyền `"abc"`, `Integer.valueOf` sẽ ném `NumberFormatException`; quan hệ kiểu đúng không bảo đảm mọi nội dung đầu vào đều chuyển đổi thành công.

## 8. Phạm vi, tên trùng và các lỗi thường gặp

### 8.1. Tham số kiểu của phương thức không đổi kiểu trường

Không thể thêm một phương thức `<U> void setAnything(U next)` rồi tự gán `next` vào trường `T value`: `U` và `T` độc lập nếu chưa có quan hệ giới hạn hoặc chuyển đổi phù hợp. Đổi tên một kiểu không tạo ra bằng chứng rằng nó tương thích với kiểu của trường.

Trong lớp `Slot<T>`, cách cập nhật trường bằng cùng hợp đồng đang có là `void set(T next)` hoặc `T replace(T next)`. Nếu muốn đổi kiểu dữ liệu kết quả, tạo một đối tượng `Slot<R>` như `map`, thay vì giả định đối tượng hiện tại đổi đối số kiểu.

### 8.2. Tránh che khuất `T` của lớp

Đoạn minh họa lỗi:

```java
class Confusing<T> {
    private T value;

    <T> void set(T incoming) {
        value = incoming; // Lỗi: hai T là hai tham số kiểu khác nhau
    }
}
```

`<T>` trước `void` khai báo một `T` mới của phương thức và che tên `T` của lớp trong phạm vi phương thức. Nhìn cùng tên không có nghĩa là cùng kiểu. Có thể đổi tham số phương thức thành `U` để thấy rõ sự độc lập, nhưng chỉ đổi tên vẫn chưa làm phép gán hợp lệ; cần sửa đúng quan hệ kiểu của thiết kế.

Nếu `set` chỉ cập nhật giá trị của đối tượng, bỏ danh sách `<T>` ở phương thức và dùng `void set(T incoming)`. Khi thật sự cần một kiểu riêng, chọn tên khác như `R` hoặc `U` để người đọc theo dõi được nguồn khai báo.

### 8.3. Không dùng tên tham số kiểu ngoài phạm vi

`R` của `map` chỉ có ý nghĩa trong khai báo và thân `map`; `S` của hàm tạo `Converted` chỉ có ý nghĩa trong phạm vi hàm tạo đó. Một trường khác của lớp không thể tự dùng `R` hoặc `S` nếu lớp chưa khai báo chúng. Việc nhiều phương thức dùng cùng tên `U` cũng không làm chúng chia sẻ một tham số kiểu.

### 8.4. `T` không phải một hàm tạo hoặc một đối tượng `Class`

Trong thân lớp generic, `new T()` không hợp lệ: tham số kiểu không cung cấp một hàm tạo cụ thể để gọi. `T.class` cũng không phải cú pháp hợp lệ để lấy lớp lúc chạy của đối số kiểu. Nếu cần tạo đối tượng, có thể thiết kế nhận một hàm tạo dữ liệu như `Supplier<T>`; nếu cần thông tin lớp lúc chạy, có thể nhận `Class<T>` phù hợp. Những yêu cầu ấy cần được thể hiện trong API.

Không giải quyết các lỗi phạm vi/kiểu bằng ép kiểu tùy tiện hoặc che cảnh báo. Trước tiên hãy xác định tham số kiểu đang thuộc lớp, phương thức hay hàm tạo nào.

## 9. Tự kiểm tra

1. Trong `class Store<T> { T load() { ... } }`, `load` có tự khai báo tham số kiểu không?
2. Trong `static <U> Store<U> of(U value)`, `U` thuộc lớp hay phương thức?
3. Vì sao `static T cache` không hợp lệ trong `class Store<T>`?
4. Với `<R> Slot<R> map(Function<T, R> mapper)`, gọi `map` có làm đổi `T` của đối tượng hiện tại không?
5. Trong `<S> Converted(S source, Function<S, T> converter)`, đâu là tham số kiểu của lớp và đâu là tham số kiểu của hàm tạo?

Đáp án:

1. Không. `load` dùng `T` đã được khai báo ở lớp; nó không có danh sách tham số kiểu riêng.
2. `U` thuộc phương thức `of`, nên từng lần gọi có thể suy luận độc lập.
3. `T` mô tả đối số kiểu của từng lần tham số hóa lớp, còn trường `static` được chia sẻ ở cấp lớp và không thuộc một đối tượng được tham số hóa cụ thể.
4. Không. `R` là kiểu của kết quả mới; `T` vẫn là hợp đồng của đối tượng ban đầu.
5. `T` được khai báo bởi `class Converted<T>`; `S` được khai báo bởi chính hàm tạo.

Khi đọc một thành viên có generic, hãy tìm nơi khai báo từng tên kiểu trước, sau đó lần theo nó qua trường, đầu vào và đầu ra. Cách đọc này giúp phân biệt một quan hệ được giữ suốt đời đối tượng với một quan hệ chỉ tồn tại trong một lần gọi.
