# Khai báo lớp generic và tham số kiểu T, E, K, V

## 1. Một cấu trúc dữ liệu, nhiều kiểu giá trị

Giả sử cần một đối tượng giữ một giá trị và cho phép đọc/thay giá trị đó. Viết riêng một lớp cho chuỗi rồi một lớp gần giống cho số sẽ lặp lại cùng cấu trúc. Lớp generic cho phép **tham số hóa kiểu dữ liệu** mà vẫn giữ cùng cách tổ chức và cùng thuật toán.

```java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

`T` là một **tham số kiểu** được khai báo ngay sau tên lớp. Trong phần thân lớp, nó đại diện kiểu mà mã sử dụng sẽ cung cấp. Khi dùng `Box<String>`, hợp đồng của `get` cho phía gọi là `String`, còn `set` nhận giá trị tương thích với `String`.

Lợi ích không chỉ là bớt mã lặp: trình biên dịch có thể từ chối việc đặt một số vào hộp đã được khai báo giữ chuỗi. Không cần tự trả `Object` rồi bắt mọi nơi gọi ép kiểu lại.

## 2. Tham số kiểu khác với đối số kiểu

| Vị trí | Ví dụ | Vai trò |
| --- | --- | --- |
| Khai báo lớp | `class Box<T>` | Khai báo tham số kiểu `T` |
| Sử dụng kiểu | `Box<String>` | Cung cấp đối số kiểu `String` |
| Biến thông thường | `Box<String> name` | Biến tham chiếu đến một đối tượng theo hợp đồng kiểu |
| Tạo đối tượng | `new Box<>("Lan")` | Suy luận đối số kiểu từ ngữ cảnh và đối số constructor |

`T` không phải một biến chứa tên lớp dưới dạng chuỗi, cũng không phải giá trị được truyền như tham số constructor. `new Box<String>("Lan")` cung cấp cả đối số kiểu `String` và giá trị `"Lan"`; hai phần này có vai trò khác nhau.

`Box<String>` và `Box<Integer>` là hai kiểu tham số hóa khác nhau trong kiểm tra kiểu. Compiler không tạo một bản mã lớp riêng theo kiểu chuyên biệt cho từng đối số như thể người viết đã nhân bản toàn bộ lớp. [JLS: lớp generic](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.2)

## 3. T, E, K, V là quy ước đặt tên

Các chữ này không phải từ khóa hoặc các kiểu đặc biệt có sẵn. Người viết khai báo tên nào thì tên đó có hiệu lực trong phạm vi tương ứng.

| Tên thường dùng | Cách đọc | Ngữ cảnh |
| --- | --- | --- |
| `T` | Type, kiểu tổng quát | Một giá trị hoặc đối tượng chưa chốt kiểu |
| `E` | Element, phần tử | Collection hoặc cấu trúc chứa phần tử |
| `K` | Key, khóa | Tra cứu/ánh xạ |
| `V` | Value, giá trị | Giá trị tương ứng với khóa |
| `R` | Result, kết quả | Kiểu kết quả trong một số hợp đồng |

Ví dụ `Box<E>` vẫn hợp lệ về ngôn ngữ nếu khai báo và dùng nhất quán; đổi chữ không tự đổi hành vi. Chọn tên theo vai trò để người đọc hiểu ý định.

`Map<K,V>` của JDK dùng `K` cho kiểu khóa và `V` cho kiểu giá trị. Đây là ví dụ của quy ước có ý nghĩa, không phải yêu cầu mọi lớp có hai tham số đều phải đặt tên `K,V`. [Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html)

Nếu nhiều chữ đơn trở nên khó theo dõi, có thể chọn tên có nghĩa như `Input` và `Output`, hoặc giải thích rõ trong tài liệu. Tên tham số kiểu không cần là một chữ, nhưng nên khác tên lớp quen thuộc để tránh che khuất hoặc gây hiểu nhầm.

## 4. Nhiều tham số kiểu giữ quan hệ giữa các thành phần

Một lớp giữ cặp khóa/giá trị có thể có hai tham số độc lập:

```java
final class Entry<K, V> {
    private final K key;
    private final V value;

    Entry(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
```

`Entry<String, Integer>` giữ quan hệ khóa chuỗi và giá trị số nguyên trong một kiểu. Không cần cả hai có cùng kiểu; `Entry<String, String>` cũng hợp lệ.

Cấu trúc này chỉ là cặp dữ liệu, không tự có hành vi ánh xạ duy nhất của `Map`. Dấu `<K,V>` không tạo thuật toán tra cứu, không cấm khóa trùng và không tự cung cấp `equals`/`hashCode` theo giá trị. Những hành vi đó phải có trong hợp đồng và triển khai của lớp.

## 5. Compiler kiểm tra cách dùng kiểu

Đoạn minh họa trong một phương thức với lớp `Box` đã khai báo:

```java
Box<String> text = new Box<>("Lan");
String name = text.get();
text.set("Mai");
// text.set(10); // Không biên dịch: không tương thích với String.

Box<Integer> count = new Box<>(3);
int next = count.get() + 1;
```

`Integer` là kiểu tham chiếu dùng làm đối số kiểu. Giá trị `3` được boxing khi cần; kết quả `get()` được unboxing khi cộng vào `int`. Không viết `Box<int>` trong mô hình generics Java của ví dụ này.

`<>` ở biểu thức tạo đối tượng là diamond, yêu cầu compiler suy luận; nó không có nghĩa “bỏ mọi thông tin kiểu”. Ví dụ `Box<String> text = new Box<>("Lan")` vẫn giữ ràng buộc `String` qua kiểu biến.

Nếu dùng `var`, kiểu được suy từ biểu thức khởi tạo: `var box = new Box<>("Lan")` cho kiểu tham số hóa theo đối số đó. Nhưng `var box = new Box<>(null)` không có thông tin cụ thể như `String` để suy ra; nên viết ngữ cảnh kiểu rõ khi nó là một phần quan trọng của hợp đồng.

## 6. Chương trình hoàn chỉnh

Lưu thành `GenericClassDemo.java`. Lớp `Shelf<E>` minh họa quy ước phần tử; `Entry<K,V>` minh họa hai vai trò độc lập.

```java
import java.util.ArrayList;
import java.util.List;

public class GenericClassDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() { return value; }
        void set(T value) { this.value = value; }
    }

    static final class Shelf<E> {
        private final List<E> elements = new ArrayList<>();

        void add(E element) { elements.add(element); }
        E first() { return elements.get(0); }
        int size() { return elements.size(); }
    }

    static final class Entry<K, V> {
        private final K key;
        private final V value;

        Entry(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() { return key; }
        V value() { return value; }
    }

    public static void main(String[] args) {
        Box<String> name = new Box<>("Lan");
        name.set("Mai");
        System.out.println("name=" + name.get());

        Box<Integer> count = new Box<>(3);
        count.set(count.get() + 2);
        System.out.println("count=" + count.get());

        Shelf<String> titles = new Shelf<>();
        titles.add("Generics");
        titles.add("Collections");
        String first = titles.first();
        System.out.println("first=" + first);
        System.out.println("size=" + titles.size());

        Entry<String, Integer> stock = new Entry<>("book", 12);
        String key = stock.key();
        int quantity = stock.value();
        System.out.println("entry=" + key + ":" + quantity);

        Box<String> another = new Box<>("An");
        System.out.println("separateValue=" + another.get());
        System.out.println("sameRuntimeClass="
                + (name.getClass() == count.getClass()));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 GenericClassDemo.java
java GenericClassDemo
```

Stdout chính xác:

```text
name=Mai
count=5
first=Generics
size=2
entry=book:12
separateValue=An
sameRuntimeClass=true
```

`name` và `another` là hai đối tượng khác nhau nên giữ giá trị độc lập. Việc cả hai có `Box<String>` không làm chúng chia sẻ trường `value`. Hai hộp khác đối số kiểu vẫn có cùng lớp lúc chạy theo cơ chế xóa kiểu của generics; thông tin đó không biến `Box<String>` thành `Box<Integer>` ở mã nguồn.

`Shelf.first()` trong ví dụ chỉ hợp lệ khi có phần tử; generics không làm danh sách rỗng tự có phần tử đầu. Thiết kế API thực tế có thể dùng `Optional<E>`, báo lỗi có nghĩa hoặc ghi rõ điều kiện, tùy yêu cầu.

## 7. Phạm vi và giới hạn của một tham số kiểu

`T` khai báo trên lớp thuộc ngữ cảnh của các thành viên đối tượng. Không dùng trực tiếp nó như kiểu cho một trường `static` của lớp:

```java
class Box<T> {
    // static T shared; // Không hợp lệ.
}
```

Thành viên static gắn với lớp, không có một bộ giá trị riêng cho mỗi `Box<String>` hay `Box<Integer>`. Nếu một phương thức static thực sự cần kiểu tổng quát, nó có thể khai báo **tham số kiểu riêng**; đó là generic method, khác với việc dùng `T` của đối tượng.

Khi không khai báo giới hạn, `T` có giới hạn trên ngầm định là `Object`. Bên trong lớp, không thể gọi phương thức đặc thù như `value.length()` chỉ vì một nơi sử dụng đã chọn `String`; lớp phải đúng cho mọi đối số kiểu mà khai báo cho phép.

Nếu thuật toán cần một khả năng cụ thể, có thể khai báo giới hạn như `T extends Number`; chữ `extends` trong giới hạn cũng được dùng cho interface. Cần chọn giới hạn theo khả năng thật sự sử dụng, không thêm tùy ý để làm tên kiểu có vẻ chặt chẽ. [JLS: biến kiểu](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.4)

## 8. Những điều lớp generic không tự bảo đảm

### Không tự cho phép chuyển kiểu theo quan hệ của phần tử

`Integer` là kiểu con của `Number`, nhưng `Box<Integer>` không tự là kiểu con của `Box<Number>`. Nếu được gán như vậy, mã qua tham chiếu `Box<Number>` có thể đặt một `Double` vào hộp được coi là chỉ giữ `Integer`.

Đây là lý do cần hiểu wildcard hoặc thiết kế phương thức đọc/ghi ở bước phù hợp, thay vì ép kiểu bỏ qua compiler. [JLS: kiểu tham số hóa](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5)

### Không tự cấm null

`new Box<String>(null)` vẫn phù hợp với kiểu tham chiếu. Nếu lớp cấm thiếu giá trị, constructor và `set` cần kiểm tra như `Objects.requireNonNull`. Generics kiểm tra quan hệ kiểu, không thay mọi điều kiện dữ liệu.

### Không cung cấp một constructor chung cho T

Không viết `new T()`: khai báo `T` không cam kết có constructor không tham số. Nếu cần tạo giá trị, nhận giá trị từ bên ngoài hoặc thiết kế một factory được truyền vào, thay vì tự đoán cách tạo mọi kiểu.

### Không tự bảo đảm bất biến hoặc an toàn nhiều luồng

Ví dụ `Box` cho phép thay giá trị; dấu `<T>` không thêm khóa đồng bộ hoặc tạo bản sao sâu. Những thuộc tính đó thuộc thiết kế lớp và kiểu giá trị chứa bên trong.

## 9. Đặt tên và dùng lớp generic có mục đích

Một lớp nên generic khi cấu trúc hoặc thuật toán có thể áp dụng cho nhiều kiểu và cần bảo toàn quan hệ kiểu qua API. Nếu lớp chỉ xử lý một kiểu nghiệp vụ cố định, thêm `<T>` nhưng luôn ép nó về kiểu đó làm hợp đồng kém rõ.

Chọn tên theo vai trò, dùng kiểu tham số hóa nhất quán tại ranh giới và để compiler giúp kiểm tra. Tài liệu lớp nên nói tham số biểu diễn gì, có cho `null` không, giá trị có bị giữ/sao chép hay sửa không.

Nếu hai tham số có quan hệ với nhau, biểu đạt quan hệ đó trong khai báo và phương thức khi cần. Đừng đặt hai chữ khác nhau rồi mặc định compiler hiểu rằng chúng phải cùng kiểu hoặc có khả năng chuyển đổi.

## 10. Tự thực hành

1. Tạo `Box<LocalDate>` và đọc kết quả vào biến `LocalDate` mà không ép kiểu.
2. Đổi `Box<T>` thành `Box<Item>` nhất quán để thấy tên tham số không phải từ khóa.
3. Tạo `Entry<Long, String>` rồi kiểm tra compiler từ chối một giá trị không đúng kiểu khóa.
4. Thêm chính sách cấm `null` vào constructor và `set`, phân biệt lỗi dữ liệu với lỗi kiểu.

Đối chiếu: khai báo lớp tạo tham số kiểu, nơi sử dụng cung cấp đối số kiểu, còn T/E/K/V chỉ là tên giúp mô tả vai trò của các kiểu đó.