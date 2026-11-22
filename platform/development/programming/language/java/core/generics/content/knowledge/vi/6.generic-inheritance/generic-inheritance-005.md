# Vì sao một lớp không thể kế thừa cùng giao diện với hai đối số kiểu khác nhau?

Trong Java Generics, một lớp có thể triển khai nhiều interface, và một generic interface có thể được sử dụng với nhiều đối số kiểu. Tuy nhiên, **cùng một lớp hoặc interface không thể đồng thời kế thừa hai cách tham số hóa khác nhau của cùng một generic interface**. Ví dụ, Java không cho một lớp vừa là `Handler<String>` vừa là `Handler<Integer>` thông qua hai nhánh kế thừa, kể cả khi bạn dự định viết hai phương thức overload `handle(String)` và `handle(Integer)`.

Quy tắc này thường gây bất ngờ khi thiết kế các interface như `Listener<T>`, `Handler<T>`, `Repository<T>`, `Comparable<T>` hoặc `Converter<I, O>`. Nguyên nhân liên quan đến **tính nhất quán của quan hệ kế thừa** và cách Java biên dịch generic bằng **type erasure**. Bài này phân tích lỗi trực tiếp và gián tiếp, lý do overload không cứu được thiết kế, trường hợp kế thừa cùng một đối số kiểu là hợp lệ và các cách mô hình hóa nhu cầu xử lý nhiều kiểu an toàn hơn.

## 1. Nhắc lại: khai báo generic và từng kiểu được tham số hóa

Giả sử có interface:

```java
interface Handler<T> {
    void handle(T value);
}
```

`T` là **tham số kiểu** (*type parameter*) được khai báo trên `Handler<T>`. Những kiểu sau là hai **cách tham số hóa** (*parameterizations*) khác nhau của cùng interface:

```java
Handler<String>
Handler<Integer>
```

Hai dòng trên là tên kiểu minh họa, **không phải câu lệnh Java độc lập**. Với `Handler<String>`, compiler yêu cầu phương thức nhận `String`; với `Handler<Integer>`, yêu cầu nhận `Integer`.

Một lớp xử lý chuỗi hoàn toàn hợp lệ:

```java
final class TextHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println(value.toUpperCase());
    }
}
```

Một lớp khác xử lý số nguyên cũng hợp lệ:

```java
final class NumberHandler implements Handler<Integer> {
    @Override
    public void handle(Integer value) {
        System.out.println(value * 2);
    }
}
```

Điểm cần nhớ: **nhiều lớp khác nhau được phép chọn những đối số kiểu khác nhau**. Điều bị cấm là **một kiểu duy nhất cùng lúc kế thừa cả hai cách tham số hóa của cùng interface**.

## 2. Lỗi trực tiếp: một lớp muốn `implements Handler<String>, Handler<Integer>`

Đoạn dưới đây **cố ý không hợp lệ**:

```java
interface Handler<T> {
    void handle(T value);
}

// KHÔNG BIÊN DỊCH:
class Impossible implements Handler<String>, Handler<Integer> {
    public void handle(String value) { }
    public void handle(Integer value) { }
}
```

Lỗi nằm ngay ở quan hệ kế thừa `implements Handler<String>, Handler<Integer>`. Java không cho ghi hai cách tham số hóa khác nhau của cùng generic interface cho một lớp. Với dạng khai báo trực tiếp này, compiler cũng có thể báo rằng interface `Handler` bị lặp trong danh sách `implements`.

Dễ nhầm rằng do `handle(String)` và `handle(Integer)` là hai overload hợp lệ trong lớp thông thường, Java sẽ chấp nhận. Nhưng **overload ở cấp phương thức không giải quyết được điều kiện hợp lệ ở cấp hệ phân cấp kiểu**.

Điều này khác hoàn toàn với việc khai báo hai phương thức overload trong một lớp không triển khai `Handler<T>`:

```java
final class MultiMethod {
    void handle(String text) {
        System.out.println(text);
    }

    void handle(Integer number) {
        System.out.println(number);
    }
}
```

`MultiMethod` là một khai báo lớp Java hợp lệ. Có hai phương thức nhận hai kiểu khác nhau, nhưng không có tuyên bố rằng đối tượng vừa là `Handler<String>` vừa là `Handler<Integer>`. Sự khác biệt nằm ở **hợp đồng interface được kế thừa**, không phải ở khả năng viết overload nói chung.

## 3. Lỗi gián tiếp qua hai nhánh interface: trường hợp khó phát hiện hơn

Ngay cả khi không viết hai lần `Handler<...>` trực tiếp trong cùng danh sách `implements`, quy tắc vẫn áp dụng.

```java
interface Handler<T> {
    void handle(T value);
}

interface TextHandler extends Handler<String> { }

interface NumberHandler extends Handler<Integer> { }

// CỐ Ý SAI:
class BothHandlers implements TextHandler, NumberHandler {
    public void handle(String value) { }
    public void handle(Integer value) { }
}
```

Sơ đồ kế thừa:

```text
             Handler<T>
              /     \
     Handler<String> Handler<Integer>
            |             |
       TextHandler    NumberHandler
             \           /
              BothHandlers
                  X
```

Mỗi nhánh riêng lẻ là hợp lệ: `TextHandler` chọn `String`, `NumberHandler` chọn `Integer`. Nhưng khi `BothHandlers` muốn kế thừa cả hai, hệ phân cấp buộc cùng một lớp phải đồng thời là hai cách tham số hóa không tương thích của `Handler`.

Compiler sẽ từ chối khai báo này. Thông báo cụ thể thay đổi tùy compiler và ngữ cảnh, thường nói rằng `Handler` không thể được kế thừa với hai đối số kiểu khác nhau. **Bổ sung cả hai overload vào thân lớp vẫn không giải quyết được.**

Quy tắc cũng áp dụng khi một trong hai nhánh đi qua **lớp cha** thay vì interface trung gian.

```java
interface Reader<T> {
    T read();
}

abstract class BaseReader<T> implements Reader<T> { }

// CỐ Ý SAI:
class MixedReader extends BaseReader<String>
        implements Reader<Integer> {
    public Integer read() {
        return 1;
    }
}
```

`BaseReader<String>` đã thiết lập quan hệ `Reader<String>`. `MixedReader` không được đồng thời bổ sung `Reader<Integer>`. Lỗi không thể sửa chỉ bằng cách chọn một kiểu trả về của `read()`; chính hệ thống kế thừa đã không nhất quán.

## 4. Quy tắc của Java: không có hai superinterface là các cách tham số hóa khác nhau của cùng một generic interface

Có thể diễn đạt nguyên tắc như sau:

> Trong hệ phân cấp của một kiểu Java, không được kế thừa cùng một generic interface dưới hai đối số kiểu khác nhau.

Ở đây **“cùng một generic interface”** có nghĩa cùng khai báo, ví dụ `Handler<T>`, không phải “hai interface bất kỳ đều có chữ `T`”.

**“Kế thừa”** bao gồm cả đường trực tiếp và đường gián tiếp qua `extends` hoặc `implements`. Nếu một lớp `Child` đã nhận `Handler<String>` từ lớp cha hoặc interface cha, nó không thể nhận thêm `Handler<Integer>` từ nhánh khác.

Tuy nhiên, hai con đường dẫn đến **chính xác cùng cách tham số hóa** là trường hợp khác. Ví dụ `Left extends ValueSource<String>` và `Right extends ValueSource<String>` có thể cùng được triển khai bởi một lớp, miễn các hợp đồng khác không xung đột. Phần tiếp theo có chương trình chạy được để minh họa trường hợp hợp lệ này.

Một lưu ý quan trọng: quy tắc không chỉ tồn tại vì một số cặp phương thức bị trùng sau erasure. **Ngay cả generic interface không khai báo phương thức nào**, hai cách tham số hóa khác nhau của cùng interface vẫn không thể cùng xuất hiện trong một hệ phân cấp.

```java
interface Marker<T> { }
interface TextMarker extends Marker<String> { }
interface NumberMarker extends Marker<Integer> { }

// CỐ Ý SAI, dù Marker<T> không có phương thức nào:
// final class TwoMarkers implements TextMarker, NumberMarker { }
```

Vì vậy, hãy coi đây là **quy tắc nhất quán danh tính superinterface của Java**, không chỉ là một bài toán tránh trùng tên phương thức có thể chữa bằng overload.

## 5. Type erasure giải thích vì sao hai chữ ký không tự trở thành hai hợp đồng độc lập

Java Generics chủ yếu được kiểm tra ở **compile time** và được triển khai bằng **type erasure**. Xét interface:

```java
interface Handler<T> {
    void handle(T value);
}
```

Ở mã nguồn:

- `Handler<String>` cần một thao tác nhận `String`.
- `Handler<Integer>` cần một thao tác nhận `Integer`.

Nhưng khi compiler xóa tham số kiểu không có bound, phương thức generic của `Handler<T>` có chữ ký JVM về cơ bản như:

```java
void handle(Object value);
```

Đoạn trên chỉ là **mô hình chữ ký sau erasure**, không phải chỉ dẫn sửa interface gốc. Có một khai báo interface runtime `Handler`, không có hai interface runtime tách biệt cho `Handler<String>` và `Handler<Integer>`.

Khi một lớp triển khai **một** cách tham số hóa, chẳng hạn `Handler<String>`, compiler có thể tự tạo **bridge method** để giữ khả năng gọi đa hình đúng với chữ ký bị xóa kiểu. Nhưng không nên hiểu rằng compiler sẽ tự tạo hai “slot interface generic” độc lập cho hai đối số kiểu khác nhau. Java chủ động từ chối hệ phân cấp mâu thuẫn, thay vì chờ tới khi chạy mới phát hiện thiếu nhất quán.

### Ví dụ hợp lệ để hiểu bridge method

Lưu tệp **`BridgeDemo.java`**:

```java
public class BridgeDemo {
    interface Handler<T> {
        T transform(T value);
    }

    static final class UppercaseHandler
            implements Handler<String> {
        @Override
        public String transform(String value) {
            return value.toUpperCase();
        }
    }

    public static void main(String[] args) {
        Handler<String> handler = new UppercaseHandler();
        System.out.println(handler.transform("java"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BridgeDemo.java
java BridgeDemo
```

`stdout`:

```text
JAVA
```

Ở mã nguồn, `UppercaseHandler` chỉ cần viết `String transform(String)`. Sau erasure, interface có phương thức dạng `Object transform(Object)`, vì vậy compiler tạo một bridge method tổng hợp ở lớp triển khai để bảo toàn lời gọi qua `Handler<String>`.

Có thể xem chi tiết bytecode:

```bash
javap -p -v 'BridgeDemo$UppercaseHandler'
```

Lệnh trên sử dụng cách đặt tên class file của lớp lồng `BridgeDemo$UppercaseHandler` trong môi trường shell có hỗ trợ dấu nháy đơn; nếu ở Windows PowerShell, tên này cũng được bảo toàn trong nháy đơn. Với compiler `javac`, output có cờ `ACC_BRIDGE` và `ACC_SYNTHETIC` ở phương thức cầu nối tương ứng.

**Bridge method là công việc tự động của compiler để hỗ trợ một hợp đồng kế thừa hợp lệ**, không phải cơ chế cho phép kế thừa hai cách tham số hóa khác nhau.

## 6. Trường hợp hợp lệ: hai nhánh cùng kế thừa đúng một đối số kiểu

Hai nhánh interface có thể cùng chỉ về `ValueSource<String>`.

Lưu chương trình độc lập **`SameTypeDiamondDemo.java`**:

```java
public class SameTypeDiamondDemo {
    interface ValueSource<T> {
        T value();
    }

    interface FromDatabase extends ValueSource<String> { }

    interface FromCache extends ValueSource<String> { }

    static final class SharedSource
            implements FromDatabase, FromCache {
        @Override
        public String value() {
            return "ready";
        }
    }

    public static void main(String[] args) {
        SharedSource source = new SharedSource();
        ValueSource<String> generic = source;
        FromDatabase database = source;
        FromCache cache = source;

        System.out.println(generic.value());
        System.out.println(database.value());
        System.out.println(cache.value());
    }
}
```

Biên dịch và chạy bằng Java 17:

```bash
javac -encoding UTF-8 SameTypeDiamondDemo.java
java SameTypeDiamondDemo
```

Kết quả:

```text
ready
ready
ready
```

Mặc dù có hai đường kế thừa, cả hai đều yêu cầu **cùng một kiểu** `ValueSource<String>`. Lớp `SharedSource` chỉ cần thực hiện một hợp đồng `String value()`.

Đối chiếu:

| Hai đường kế thừa | Hợp lệ? | Lý do |
|---|---|---|
| `ValueSource<String>` và `ValueSource<String>` | Có, nếu không có xung đột khác | Cùng một cách tham số hóa. |
| `ValueSource<String>` và `ValueSource<Integer>` | Không | Hai cách tham số hóa khác nhau của cùng `ValueSource`. |
| `Handler<String>` và `Formatter<Integer>` | Có thể | Hai generic interface khác nhau; còn phải xét chữ ký của chúng. |
| `InterfaceA<String>` và `InterfaceB<String>` | Có thể | Cùng đối số `String` nhưng là hai khai báo interface khác nhau. |

Như vậy **không phải cứ có hình thoi kế thừa là lỗi**. Vấn đề nằm ở việc kế thừa **không nhất quán các đối số kiểu của cùng interface generic**.

## 7. Khác generic interface thì có thể sử dụng các đối số kiểu khác nhau

Java cho một lớp triển khai nhiều **generic interface khác nhau**, nếu các phương thức mà chúng yêu cầu có thể được cài đặt nhất quán.

Lưu **`DifferentInterfacesDemo.java`**:

```java
public class DifferentInterfacesDemo {
    interface TextProvider<T> {
        T text();
    }

    interface NumberProvider<T> {
        T number();
    }

    static final class Combined
            implements TextProvider<String>, NumberProvider<Integer> {
        @Override
        public String text() {
            return "hello";
        }

        @Override
        public Integer number() {
            return 42;
        }
    }

    public static void main(String[] args) {
        Combined combined = new Combined();

        TextProvider<String> textProvider = combined;
        NumberProvider<Integer> numberProvider = combined;

        System.out.println(textProvider.text());
        System.out.println(numberProvider.number() + 1);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DifferentInterfacesDemo.java
java DifferentInterfacesDemo
```

`stdout`:

```text
hello
43
```

Một lớp `Combined` đồng thời triển khai `TextProvider<String>` và `NumberProvider<Integer>`. Không có lỗi “cùng interface generic với hai đối số kiểu”, vì `TextProvider` và `NumberProvider` là **hai interface khác nhau**.

Cần thận trọng: không phải mọi cặp interface khác nhau đều tự động tương thích. Nếu chúng định nghĩa những phương thức có chữ ký va chạm nhưng kiểu trả về hoặc yêu cầu override không tương thích, Java vẫn có thể báo lỗi. Quy tắc đang học chỉ là một **điều kiện cần của hệ phân cấp**, không thay thế tất cả quy tắc overload, override và method erasure.

## 8. Giải pháp thứ nhất: composition — giữ hai handler riêng và ủy quyền

Nếu yêu cầu nghiệp vụ thực sự cần xử lý cả chuỗi và số nguyên, một giải pháp tự nhiên là dùng **hai đối tượng khác nhau** thực hiện cùng generic interface theo hai cách tham số hóa, rồi cho một lớp điều phối giữ tham chiếu tới chúng.

Thay vì ép một lớp thành cả `Handler<String>` và `Handler<Integer>`, lớp điều phối **chứa** hai handler riêng và cung cấp các hàm nghiệp vụ rõ ràng.

Lưu **`CompositionDemo.java`**:

```java
public class CompositionDemo {
    interface Handler<T> {
        String handle(T value);
    }

    static final class TextHandler implements Handler<String> {
        @Override
        public String handle(String value) {
            return "text=" + value.toUpperCase();
        }
    }

    static final class NumberHandler implements Handler<Integer> {
        @Override
        public String handle(Integer value) {
            return "number=" + (value * 2);
        }
    }

    static final class Router {
        private final Handler<String> textHandler = new TextHandler();
        private final Handler<Integer> numberHandler = new NumberHandler();

        String processText(String value) {
            return textHandler.handle(value);
        }

        String processNumber(Integer value) {
            return numberHandler.handle(value);
        }
    }

    public static void main(String[] args) {
        Router router = new Router();

        System.out.println(router.processText("java"));
        System.out.println(router.processNumber(21));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CompositionDemo.java
java CompositionDemo
```

`stdout`:

```text
text=JAVA
number=42
```

Ưu điểm:

1. `TextHandler` là `Handler<String>` và được kiểm tra kiểu tại compile time.
2. `NumberHandler` là `Handler<Integer>` và có hợp đồng kiểu độc lập.
3. `Router` không `implements Handler<String>, Handler<Integer>`; nó chỉ **phối hợp** hai đối tượng.
4. Không có ép kiểu không được kiểm tra, không cần raw type, và mã không bị ràng buộc bởi xung đột superinterface.

Đây thường là lựa chọn tốt nếu hai hành vi có logic khác nhau hoặc có vòng đời/phụ thuộc khác nhau. Composition không phải thủ thuật để “lách compiler”; nó diễn đạt một mô hình đối tượng khác phù hợp hơn với nhu cầu.

## 9. Giải pháp thứ hai: một kiểu chung có ý nghĩa cho toàn bộ các trường hợp

Nếu muốn **một handler duy nhất** xử lý nhiều dạng sự kiện và có một hợp đồng thống nhất, hãy mô hình hóa một **kiểu nghiệp vụ chung**. Thay vì yêu cầu đối tượng làm hai loại `Handler<...>`, nó thực hiện `Handler<Event>` với một phân cấp sự kiện rõ ràng.

Java 17 hỗ trợ `sealed interface` và `record`, thuận tiện để mô tả tập loại sự kiện có giới hạn.

Lưu **`EventHandlerDemo.java`**:

```java
public class EventHandlerDemo {
    interface Handler<T> {
        String handle(T value);
    }

    sealed interface Event permits TextEvent, NumberEvent { }

    record TextEvent(String text) implements Event { }

    record NumberEvent(int number) implements Event { }

    static final class UnifiedHandler implements Handler<Event> {
        @Override
        public String handle(Event event) {
            if (event instanceof TextEvent text) {
                return "text:" + text.text().toUpperCase();
            }
            if (event instanceof NumberEvent number) {
                return "number:" + (number.number() * 2);
            }
            throw new IllegalStateException("Unexpected event");
        }
    }

    public static void main(String[] args) {
        Handler<Event> handler = new UnifiedHandler();

        System.out.println(handler.handle(new TextEvent("java")));
        System.out.println(handler.handle(new NumberEvent(21)));
    }
}
```

Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 EventHandlerDemo.java
java EventHandlerDemo
```

`stdout`:

```text
text:JAVA
number:42
```

Ở đây:

- `Event` là kiểu chung đại diện cho dữ liệu mà handler chấp nhận.
- `TextEvent` và `NumberEvent` là hai kiểu cụ thể trong phân cấp.
- `UnifiedHandler` thực hiện **duy nhất `Handler<Event>`**, nên không vi phạm quy tắc kế thừa generic.
- Phép `instanceof` với pattern variable được hỗ trợ từ Java 16, có sẵn trong Java 17.
- Các nhánh `if` thể hiện logic nghiệp vụ rõ ràng; tính đúng đắn của chúng do chương trình chịu trách nhiệm, không tự được đảm bảo hoàn toàn bởi generic.

Có thể dùng `Handler<Object>` nếu yêu cầu thực sự là chấp nhận mọi đối tượng, nhưng kiểu `Object` làm hợp đồng rộng và giảm khả năng giới hạn đầu vào. Một supertype nghiệp vụ như `Event` thường tốt hơn khi tập đầu vào được xác định.

## 10. Giải pháp thứ ba: giữ lớp triển khai generic và chuyên biệt hóa ở nơi tạo

Đôi khi cùng một thuật toán xử lý được mọi kiểu mà không cần phân biệt `String` hay `Integer`. Khi đó, lớp triển khai nên **tiếp tục generic**:

```java
interface Handler<T> {
    T handle(T value);
}

final class IdentityHandler<T> implements Handler<T> {
    @Override
    public T handle(T value) {
        return value;
    }
}
```

Đây là các khai báo minh họa. Bây giờ tạo **hai đối tượng** của cùng lớp generic:

```java
Handler<String> texts = new IdentityHandler<>();
Handler<Integer> numbers = new IdentityHandler<>();
```

Mỗi đối tượng có một hợp đồng kiểu được xác định tại nơi sử dụng. Không có **một đối tượng hoặc một lớp** được tuyên bố kế thừa đồng thời hai cách tham số hóa của `Handler<T>`.

Khi thiết kế lớp generic, nhớ phân biệt:

- `class IdentityHandler<T> implements Handler<T>`: khai báo lớp generic chuyển tiếp tham số kiểu của nó vào interface.
- `Handler<String> h = new IdentityHandler<>()`: một lần **sử dụng** lớp ấy với đối số kiểu `String`.
- `Handler<Integer> h = new IdentityHandler<>()`: lần sử dụng khác với kiểu `Integer`.
- `class Impossible implements Handler<String>, Handler<Integer>`: cố tạo **một quan hệ kế thừa không hợp lệ**, khác bản chất với hai lần khởi tạo ở trên.

Có thể chuyên biệt hóa qua lớp con một lần theo một kiểu cụ thể. Ví dụ `class StringIdentity extends IdentityHandler<String>` là hợp lệ nếu `IdentityHandler<T>` không bị khai báo `final`. Tuy nhiên, lớp con đó vẫn không được tự thêm `implements Handler<Integer>` vì đã kế thừa `Handler<String>` từ lớp cha.

## 11. Vì sao wildcard `<?>` và raw type không khắc phục được lỗi kế thừa?

### 11.1. Wildcard giúp diễn đạt kiểu chưa biết ở vị trí sử dụng

Wildcard thích hợp khi cần giữ một tham chiếu tới handler mà **chưa biết** đối số kiểu:

```java
Handler<?> anyHandler;
```

Đây là một đoạn khai báo biến trong ngữ cảnh có `Handler<T>`. Nó không khai báo thêm một interface mới, cũng không làm `Handler<String>` và `Handler<Integer>` trở thành hai vai trò mà cùng một lớp được phép kế thừa.

Nếu phương thức là `void handle(T value)`, một tham chiếu `Handler<?>` **không cho phép tùy tiện gọi** `handle("text")` hay `handle(42)`, vì compiler không biết tham số kiểu đã bị wildcard che đi là gì. Có thể lưu các handler khác nhau trong một tập hợp các tham chiếu wildcard, nhưng khi thực sự gọi cần giữ **mối liên hệ giữa handler và kiểu dữ liệu đầu vào**.

Ví dụ helper generic:

```java
static <T> void dispatch(Handler<T> handler, T value) {
    handler.handle(value);
}
```

Đoạn này là một **phương thức minh họa**. Khi truyền vào `Handler<String>` cùng `String`, compiler có thể kiểm tra quan hệ kiểu. Nếu chỉ có `Handler<?>` và một đối tượng đầu vào bất kỳ, cần thêm thông tin hoặc một mô hình đóng gói cặp handler–giá trị phù hợp.

### 11.2. Raw type bỏ kiểm tra nhưng không làm hệ phân cấp trở nên đúng

Raw type là cách viết `Handler` không có đối số kiểu. Nó tồn tại chủ yếu để tương thích mã Java trước generics.

Không nên sửa thiết kế bằng việc bỏ `<String>` hoặc `<Integer>` chỉ để né lỗi. Raw type làm mất hợp đồng kiểu và có thể gây cảnh báo `rawtypes`, `unchecked`, thậm chí khiến lỗi kiểu xuất hiện lúc chạy. Nếu quan hệ kế thừa ban đầu mâu thuẫn, phải sửa **mô hình đối tượng**, không phải che giấu đối số generic.

### 11.3. Ép kiểu không kiểm tra không biến lớp thành interface khác

Một cast như `(Handler<Integer>) (Object) handlerOfString` có thể vượt qua một số kiểm tra biên dịch bằng cảnh báo hoặc thao tác không an toàn, nhưng **không thay đổi cấu trúc interface mà lớp thực sự triển khai**. Giá trị được truyền sai kiểu có thể gây `ClassCastException` khi đi qua bridge method hoặc mã xử lý. Đây không phải giải pháp cho bài toán kế thừa hai cách tham số hóa.

## 12. Câu chuyện erasure còn ảnh hưởng đến overload như thế nào?

Ngay cả khi không kế thừa interface, Java cũng cấm một số overload có cùng chữ ký sau type erasure. Ví dụ **cố ý sai**:

```java
import java.util.List;

class WrongOverloads {
    void process(List<String> texts) { }

    // Không được khai báo cùng lúc:
    // void process(List<Integer> numbers) { }
}
```

Nếu bỏ dấu chú thích ở phương thức thứ hai, compiler báo va chạm chữ ký: cả hai cùng erasure về tham số kiểu `List`. Java không dùng đối số generic `String` hay `Integer` để phân biệt hai phương thức có cùng tên ở runtime.

Tuy nhiên, cần phân biệt hai quy tắc:

- **Name clash do erasure**: có thể xuất hiện khi định nghĩa hoặc kế thừa những phương thức có chữ ký bị xóa kiểu giống nhau.
- **Không được kế thừa hai cách tham số hóa khác nhau của cùng một generic interface**: là ràng buộc của hệ phân cấp kiểu. Quy tắc này còn áp dụng khi interface **không có phương thức nào**, như `Marker<T>` đã minh họa.

Hiểu sự khác nhau giúp tìm nguyên nhân gốc. Không nên đọc mọi thông báo biên dịch về generic rồi kết luận “chỉ cần đổi tên hoặc overload thêm phương thức”.

## 13. Những lỗi thường gặp và cách xử lý

| Tình huống | Vấn đề | Hướng xử lý |
|---|---|---|
| `implements Handler<String>, Handler<Integer>` | Hai cách tham số hóa khác nhau của cùng interface. | Dùng hai handler độc lập, composition hoặc một kiểu chung. |
| Hai interface cha lần lượt `extends Handler<String>` và `extends Handler<Integer>` | Xung đột kế thừa **gián tiếp**. | Thiết kế lại phân cấp; đừng cố ghép hai nhánh vào cùng lớp. |
| `extends Base<String> implements Handler<Integer>` khi `Base<T> implements Handler<T>` | Lớp cha đã mang `Handler<String>`. | Giữ cùng đối số kiểu hoặc bỏ quan hệ xung đột. |
| Viết thêm `handle(String)` và `handle(Integer)` | Overload không sửa được quan hệ superinterface. | Không tuyên bố kế thừa hai `Handler<...>`; dùng overload trên lớp điều phối nếu cần. |
| Tưởng hai interface khác nhau cũng luôn bị cấm | Quy tắc áp vào cùng **một khai báo generic interface**. | `A<String>` và `B<Integer>` có thể cùng xuất hiện nếu phương thức tương thích. |
| Hai nhánh cùng `Handler<String>` mà nghĩ luôn lỗi | Kế thừa cùng một cách tham số hóa có thể hợp lệ. | Kiểm tra xung đột phương thức/default riêng nếu có. |
| Tưởng interface rỗng `Marker<T>` miễn trừ quy tắc | Kế thừa hai đối số kiểu khác nhau vẫn không hợp lệ. | Không tạo quan hệ kế thừa mâu thuẫn dù interface không có phương thức. |
| Dùng `Handler<?>` rồi truyền tùy ý `String`/`Integer` | Wildcard là kiểu chưa biết, không xác nhận kiểu tham số để ghi. | Giữ thông tin kiểu bằng phương thức generic hoặc API chuyên biệt. |
| Dùng raw `Handler` hoặc cast không kiểm tra | Mất bảo vệ compile time và có nguy cơ lỗi runtime. | Giữ các interface tham số hóa rõ ràng; sửa thiết kế gốc. |
| Cố overload `process(List<String>)` và `process(List<Integer>)` | Name clash do erasure. | Đổi tên phương thức hoặc thiết kế một API generic có chữ ký phù hợp. |

## 14. Checklist thiết kế khi cần nhiều vai trò generic

Khi gặp yêu cầu một lớp xử lý nhiều kiểu, hãy kiểm tra:

1. **Có đang kế thừa cùng generic interface qua hai đường không?** Tra toàn bộ `extends`/`implements` liên quan, không chỉ danh sách trực tiếp.
2. **Các đối số kiểu cuối cùng có giống nhau hoàn toàn không?** Hai nhánh đều là `Source<String>` có thể hợp lệ; một nhánh `Source<String>` và một nhánh `Source<Integer>` thì không.
3. **Đó có phải là hai generic interface thật sự khác nhau?** Nếu là `TextProvider<String>` và `NumberProvider<Integer>`, xét tiếp chữ ký để quyết định có thể triển khai chung không.
4. **Một đối tượng có thực sự cần đóng hai vai trò không?** Nếu chỉ cần phối hợp hai chiến lược, composition thường đơn giản hơn kế thừa.
5. **Có một supertype nghiệp vụ tự nhiên không?** Nếu xử lý các loại sự kiện chung, `Handler<Event>` có thể hợp lý hơn `Handler<Object>` hoặc hai cách tham số hóa.
6. **Có thể dùng cùng một thuật toán generic cho nhiều instance không?** `IdentityHandler<T>` có thể tạo các đối tượng `IdentityHandler<String>` và `IdentityHandler<Integer>` độc lập.
7. **Compiler có đang báo name clash do erasure không?** Kiểm tra các phương thức overload và bridge method; tránh sửa một lỗi kế thừa bằng cách gây thêm lỗi chữ ký.
8. **Có đang dùng raw type, wildcard hoặc unchecked cast để giấu vấn đề không?** Những kỹ thuật này không thay đổi ràng buộc kế thừa và có thể khiến API kém an toàn hơn.

## 15. Tự kiểm tra

**Câu 1.** Vì sao đoạn sau không hợp lệ?

```java
interface Consumer<T> {
    void accept(T value);
}
interface TextConsumer extends Consumer<String> { }
interface IntegerConsumer extends Consumer<Integer> { }

// class Both implements TextConsumer, IntegerConsumer { ... }
```

**Câu 2.** Hai interface `A extends Provider<String>` và `B extends Provider<String>` có nhất thiết xung đột khi một lớp `implements A, B` không?

**Câu 3.** Vì sao hai phương thức `handle(String)` và `handle(Integer)` trong một lớp không giải quyết được lỗi `implements Handler<String>, Handler<Integer>`?

**Câu 4.** Nếu `interface Marker<T> {}` không có phương thức, vì sao vẫn không thể kết hợp `Marker<String>` và `Marker<Integer>` vào một hệ phân cấp?

**Câu 5.** Nêu hai hướng thiết kế thay thế cho một lớp muốn xử lý cả thông điệp chuỗi và thông điệp số nguyên.

**Câu 6.** `Handler<?>` có nghĩa một handler nhận được mọi loại giá trị không? Nếu không, cần làm gì để gọi phương thức tiêu thụ dữ liệu an toàn?

**Gợi ý đáp án:**

1. `Both` sẽ kế thừa `Consumer<String>` và `Consumer<Integer>` thông qua hai nhánh — hai cách tham số hóa khác nhau của cùng interface.
2. Không. Nếu hai nhánh giữ đúng một cách tham số hóa và các yêu cầu phương thức không xung đột, lớp có thể triển khai cả hai.
3. Vì quy tắc kiểm tra **quan hệ superinterface** xảy ra độc lập với việc thân lớp có overload phù hợp hay không.
4. Vì đây là ràng buộc cấu trúc hệ phân cấp Java, không chỉ là việc có phương thức bị xung đột sau erasure.
5. Composition với hai đối tượng `Handler<String>`/`Handler<Integer>`, hoặc một `Handler<Event>` với kiểu sự kiện chung. Ngoài ra, có thể dùng nhiều instance của lớp `Handler<T>` generic.
6. Không. `<?>` che đối số kiểu nên compiler không biết giá trị nào hợp lệ để truyền vào phương thức nhận `T`; phải giữ hoặc khôi phục mối quan hệ kiểu qua API generic hoặc mô hình đối tượng đúng.

**Điểm cần nhớ:** Một generic interface có thể được sử dụng với nhiều đối số kiểu **ở những đối tượng và hệ phân cấp khác nhau**, nhưng **một kiểu Java không được kế thừa cùng một generic interface với hai đối số kiểu khác nhau**, kể cả qua các nhánh gián tiếp. Type erasure giải thích những khó khăn về phương thức JVM; quy tắc nhất quán hệ phân cấp còn chặt chẽ hơn xung đột chữ ký. Khi cần xử lý nhiều kiểu, hãy chọn **composition, các interface độc lập hoặc một kiểu nghiệp vụ chung**, thay vì bỏ kiểm tra generics.
