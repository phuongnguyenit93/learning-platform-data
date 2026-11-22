# Sealed hierarchy và exhaustive analysis trong Java

## 1. Tại sao sealed hierarchy giúp compiler biết một `switch` đã đủ nhánh?

Trong Java, một **sealed class/interface** giới hạn những kiểu nào được phép trực tiếp kế thừa hoặc hiện thực nó. Từ Java 17, đây là tính năng chính thức (JEP 409). Khi **pattern matching for `switch`** trở thành tính năng chính thức trong **Java 21** (JEP 441), compiler có thể kết hợp thông tin từ `sealed` với các nhãn `case` để kiểm tra **exhaustiveness**: mọi giá trị hợp lệ theo kiểu tĩnh của selector (ngoại trừ cách xử lý đặc biệt với `null`) đều có một nhánh xử lý.

Ví dụ cấu trúc:

```text
Shape (sealed interface)
├── Circle (record, final)
└── Quad (sealed interface)
    ├── Rectangle (record, final)
    └── Square (record, final)
```

Nếu một biến có kiểu tĩnh `Shape`, về mặt kiểu được khai báo, các nhánh hợp lệ của hệ phân cấp này được giới hạn bởi `permits`. Một `switch` xét đầy đủ `Circle`, `Rectangle` và `Square` có thể **biên dịch mà không cần `default`**. Compiler kiểm tra không chỉ một danh sách `case` rời rạc mà cả cấu trúc cây kế thừa sealed.

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
    };
}
```

Đoạn trên chỉ là phần phương thức đặt trong ngữ cảnh đã khai báo `Shape`, `Circle`, `Rectangle`, `Square` tương ứng; chương trình đầy đủ ở mục 5.

**Phân biệt ba khái niệm:**

- **Sealed hierarchy:** mô hình kiểu có danh sách các *permitted direct subclasses/subinterfaces*, giúp compiler biết những nhánh kế thừa trực tiếp có thể xuất hiện.
- **Exhaustive analysis:** kiểm tra tĩnh rằng các nhãn `case` bao phủ mọi khả năng cần xét của kiểu selector; đây là trách nhiệm của compiler.
- **Runtime matching:** khi chạy, Java chọn nhãn đầu tiên phù hợp với đối tượng thực tế và guard `when` (nếu có). Đây là quyết định lúc thực thi, không phải phép đếm số `case`.

**Kết luận nền tảng:** một `switch` có thể **exhaustive mà không có `default`**, nhưng một `switch` được chứng minh exhaustive vẫn không có nghĩa rằng nó tự động xử lý `null` theo ý muốn của bạn.

## 2. Sealed, final và non-sealed liên quan thế nào?

Khai báo sealed có dạng:

```java
sealed interface Shape permits Circle, Quad {
}
```

`permits` xác định các **kiểu con trực tiếp** được phép hiện thực/kế thừa `Shape`. Mỗi kiểu con trực tiếp hợp lệ phải chọn cách tiếp nối hạn chế kế thừa:

1. **`final`:** nhánh kết thúc, không có subclass mới của class đó. `record` là `final` ngầm định, nên rất phù hợp làm lá của cây.
2. **`sealed`:** nhánh tiếp tục đóng có kiểm soát, khai báo tiếp những kiểu trực tiếp được phép kế thừa.
3. **`non-sealed`:** nhánh mở lại khả năng kế thừa/hiện thực từ những kiểu khác, không cần khai báo mọi lớp con tương lai.

Ví dụ:

```java
sealed interface Shape permits Circle, Quad {}

record Circle(int radius) implements Shape {}

sealed interface Quad extends Shape permits Rectangle, Square {}

record Rectangle(int width, int height) implements Quad {}

record Square(int side) implements Quad {}
```

Các khai báo này phải đặt trong một ngữ cảnh Java hợp lệ (cùng compilation unit/package/module theo luật sealed), hoặc dùng đầy đủ chương trình ở mục 5. Chúng có nghĩa:

- `Circle` trực tiếp implement `Shape` và tự động `final` vì là record.
- `Quad` là subtype trực tiếp của `Shape`, nhưng không phải lá: nó tự sealed và chỉ cho phép `Rectangle`, `Square`.
- `Rectangle` và `Square` trực tiếp implement `Quad`.
- Compiler có thể suy luận từ `Shape` đến các lá của nhánh `Quad` khi kiểm tra các nhãn `case`.

**Không nên hiểu `permits` là danh sách tất cả subtype ở mọi cấp.** Nó liệt kê **những kiểu trực tiếp** được phép; compiler dùng đệ quy thông tin sealed ở các nhánh bên dưới để phân tích coverage.

Việc đặt khai báo ở package/module thích hợp cũng là một phần của quy tắc Java sealed: trong named module, các lớp trực tiếp được phép phải thuộc cùng module; trong unnamed module, chúng phải thuộc cùng package. Đừng tách các ví dụ thành những file/package tùy ý rồi nghĩ chỉ cần chỉnh `permits` là đủ.

## 3. Exhaustiveness được xác định dựa trên kiểu tĩnh của selector

Giả sử:

```java
Shape shape = new Circle(2);
```

Khi viết `switch (shape)`, kiểu tĩnh mà compiler xét là `Shape`, không phải chỉ lớp runtime `Circle` của đối tượng đang được gán trong một lần chạy.

```java
static String kind(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Quad q -> "quad";
    };
}
```

Đây là **exhaustive** vì:

- Một giá trị `Shape` khác `null` thuộc nhánh trực tiếp `Circle` hoặc `Quad`.
- Pattern `case Circle c` xử lý nhánh `Circle`.
- Pattern `case Quad q` xử lý **toàn bộ** `Quad`, gồm mọi `Rectangle` và `Square` hiện tại, đồng thời cả subtype hợp lệ của `Quad` nếu cấu trúc được mở rộng trong tương lai.

Có thể đạt coverage theo hai cách khác nhau:

| Cách viết | Các nhánh | Lợi ích và giới hạn |
| --- | --- | --- |
| **Gom theo kiểu cha** | `case Circle`, `case Quad` | Gọn, mọi subtype thuộc `Quad` cùng một xử lý |
| **Liệt kê đến các lá** | `case Circle`, `case Rectangle`, `case Square` | Phân biệt được từng subtype, dễ cập nhật hành vi riêng |

Hai cách đều có thể exhaustive. Việc chọn cách nào **phụ thuộc vào logic nghiệp vụ**, không phải bắt buộc phải luôn liệt kê từng record lá.

Ngược lại, đoạn sau **không exhaustive**:

```java
// LỖI biên dịch trên Shape:
// static String incomplete(Shape shape) {
//     return switch (shape) {
//         case Circle c -> "circle";
//         case Rectangle r -> "rectangle";
//         // Thiếu Square.
//     };
// }
```

Vì nhánh `Square` chưa có nhãn nào tiếp nhận, compiler báo lỗi tương tự:

```text
the switch expression does not cover all possible input values
```

Có thể sửa bằng cách bổ sung `case Square s`, đổi sang `case Quad q` để bao phủ cả hai nhánh dưới `Quad`, hoặc dùng `default` nếu thật sự muốn fallback thay vì xử lý riêng.

## 4. Tại sao Java 21 không bắt buộc `default` trong ví dụ sealed?

Một `switch expression` phải **exhaustive**: nếu được dùng như một biểu thức, nó cần có cách xử lý cho toàn bộ miền giá trị mà compiler xem là có thể xảy ra. Java 21 còn yêu cầu **enhanced `switch` statement** (ví dụ dùng type pattern) phải exhaustive.

Cách phổ biến nhất để làm một `switch` trên `Object` exhaustive là bổ sung `default`:

```java
static String generic(Object input) {
    return switch (input) {
        case String s -> "string";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

Nhưng sealed hierarchy cho compiler một cách khác: nếu các nhánh loại trừ nhau hoặc bao phủ đủ cây kiểu, **không cần `default`**.

Với sealed `Shape`, việc không có `default` thường là **có chủ đích**. Khi đội phát triển thêm một subtype được phép và biên dịch lại mã, compiler có thể chỉ ra chỗ `switch` cũ chưa xử lý subtype mới. Thêm `default` từ đầu sẽ làm chương trình biên dịch được mà không buộc người phát triển cập nhật từng nhánh cụ thể.

Tuy nhiên, **không phải luôn nên bỏ `default`**:

- Nếu API cần trả về một thông điệp chung cho những trường hợp chưa hỗ trợ, `default` có thể là hành vi hợp lý.
- Nếu từng subtype cần xử lý riêng và sự xuất hiện của subtype mới là một thay đổi contract, nên để compiler phát hiện nhánh bị thiếu.
- Nếu selector có kiểu mở, như `Object`, compiler không thể suy ra mọi subtype từ một `sealed` khác nằm sâu bên dưới; phải xét **kiểu tĩnh của selector** và các nhánh thực sự bao phủ kiểu đó.

**Khác biệt về phiên bản:** sealed types đã chính thức từ Java 17, nhưng pattern `switch` dùng `case Circle c ->` và `when` như bài này chính thức từ Java 21. Để biên dịch ví dụ, dùng `javac --release 21`, không phải `--release 17`.

## 5. Chương trình Java 21 hoàn chỉnh: sealed hierarchy hai cấp

Tạo file **`SealedExhaustiveDemo.java`**:

```java
public class SealedExhaustiveDemo {
    sealed interface Shape permits Circle, Quad {}

    record Circle(int radius) implements Shape {}

    sealed interface Quad extends Shape permits Rectangle, Square {}

    record Rectangle(int width, int height) implements Quad {}

    record Square(int side) implements Quad {}

    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c ->
                "circle:" + c.radius();
            case Rectangle r ->
                "rectangle:" + (r.width() * r.height());
            case Square s ->
                "square:" + (s.side() * s.side());
        };
    }

    static String grouped(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle";
            case Quad q -> "quad";
        };
    }

    public static void main(String[] args) {
        Shape[] shapes = {
            new Circle(2),
            new Rectangle(3, 4),
            new Square(5)
        };

        for (Shape s : shapes) {
            System.out.println(describe(s));
        }

        System.out.println(grouped(new Square(5)));

        try {
            describe(null);
        } catch (NullPointerException e) {
            System.out.println("null=>NPE");
        }
    }
}
```

Biên dịch/chạy với JDK 21 trở lên:

```bash
javac --release 21 SealedExhaustiveDemo.java
java SealedExhaustiveDemo
```

Đầu ra:

```text
circle:2
rectangle:12
square:25
quad
null=>NPE
```

Diễn giải:

1. `describe` liệt kê ba lá `Circle`, `Rectangle`, `Square`; compiler biết không còn nhánh `Shape` hợp lệ khác theo cấu trúc sealed đã khai báo, nên `switch` exhaustive.
2. `grouped` không liệt kê mọi lá, mà dùng `Quad` để bao phủ cả nhánh tứ giác; `Square` được phân vào `quad`.
3. Không nhánh nào dùng `default`, nhưng cả hai phương thức vẫn **biên dịch**.
4. `describe(null)` ném `NullPointerException`, được `main` bắt và in `null=>NPE`. Đây **không** phải minh chứng `switch` thiếu exhaustive: `null` được xử lý theo luật riêng của pattern `switch`.

### Cách xử lý `null` mà vẫn không có `default`

Khi muốn `null` có ý nghĩa riêng, thêm một `case null`:

```java
static String safeDescribe(Shape shape) {
    return switch (shape) {
        case null -> "no shape";
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
    };
}
```

Đây vẫn là `switch` không có `default`. `case null` nhận selector `null`; ba type pattern giải quyết mọi giá trị `Shape` còn lại.

Một lỗi hay gặp là nghĩ rằng `default` sẽ bắt `null`:

```java
static String misleading(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        default -> "other";
    };
}
```

Đoạn trên **exhaustive đối với các giá trị non-null** nhưng truyền `null` vẫn ném `NullPointerException`. Muốn chính sách xử lý null rõ ràng, dùng `case null` hoặc `case null, default`.

## 6. `non-sealed` mở một nhánh, nhưng vẫn có thể exhaustive

Sealed không nhất thiết có nghĩa **mọi** subtype ở **mọi độ sâu** đều bị liệt kê cố định. Một permitted subtype `non-sealed` mở lại khả năng mở rộng trong nhánh đó.

Ví dụ:

```text
Message (sealed interface)
├── Text (record)
├── Binary (record)
└── Event (non-sealed interface)
    ├── Ping
    └── ... các implementation khác trong tương lai
```

Mặc dù `Event` là **non-sealed**, `switch` dưới đây vẫn exhaustive:

```java
static String classify(Message msg) {
    return switch (msg) {
        case Text t -> "text";
        case Binary b -> "binary";
        case Event e -> "event";
    };
}
```

Vì sao? `Message` chỉ cho phép ba nhánh trực tiếp `Text`, `Binary`, `Event`, và `case Event e` nhận **mọi đối tượng thuộc Event**, kể cả những implementation chưa viết hôm nay. Compiler không cần liệt kê tất cả lớp có thể implement `Event`.

Điều không đúng là viết:

```java
// Không exhaustive nếu Event là nhánh mở:
// return switch (msg) {
//     case Text t -> "text";
//     case Binary b -> "binary";
//     case Ping p -> "ping";
// };
```

`Ping` chỉ là một implementation của `Event`. Nếu sau này có `UpdateEvent implements Event`, `switch` trên chưa biết xử lý. Muốn exhaustive phải có `case Event e` hoặc một nhãn fallback khác phù hợp.

### Chương trình Java 21 thứ hai, chạy độc lập

Tạo **`SealedOpenDemo.java`**:

```java
public class SealedOpenDemo {
    sealed interface Message permits Text, Binary, Event {}

    record Text(String value) implements Message {}

    record Binary(byte[] bytes) implements Message {}

    non-sealed interface Event extends Message {}

    record Ping(String id) implements Event {}

    static String classify(Message msg) {
        return switch (msg) {
            case Text t -> "text:" + t.value();
            case Binary b -> "bytes:" + b.bytes().length;
            case Event e -> "event";
        };
    }

    static String guarded(Message msg) {
        return switch (msg) {
            case Text t when t.value().isEmpty() -> "empty";
            case Text t -> "text";
            case Binary b -> "binary";
            case Event e -> "event";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Text("Hello")));
        System.out.println(classify(new Binary(new byte[]{1, 2, 3})));
        System.out.println(classify(new Ping("p1")));
        System.out.println(guarded(new Text("")));
        System.out.println(guarded(new Text("abc")));
    }
}
```

Lệnh chạy:

```bash
javac --release 21 SealedOpenDemo.java
java SealedOpenDemo
```

Đầu ra:

```text
text:Hello
bytes:3
event
empty
text
```

`Ping` thuộc nhánh `Event`, nên được `case Event e` tiếp nhận. `guarded` có thể dùng `when` để xử lý riêng `Text` rỗng; nhánh `case Text t` không guard sau đó vẫn tiếp nhận những `Text` khác. Nhờ có fallback cùng kiểu, toàn bộ nhánh `Text` vẫn được bao phủ.

**Giới hạn của ví dụ:** `guarded(new Text(null))` có thể ném `NullPointerException` trong `t.value().isEmpty()`; compiler kiểm tra coverage của kiểu, **không** chứng minh dữ liệu component luôn non-null. Để bảo vệ dữ liệu thực, phải xác thực invariant của record hoặc kiểm tra `t.value() != null` trước khi gọi `isEmpty()`.

## 7. Guard `when` có thể làm mất exhaustiveness

Một type pattern có `when` thường chỉ bao phủ **một phần** các đối tượng thuộc subtype đó. Compiler không thể coi một nhánh guarded tùy ý là đủ cho toàn bộ subtype.

```java
// Không exhaustive, dù đã có tên của ba nhánh Message:
// return switch (msg) {
//     case Text t when t.value().isEmpty() -> "empty";
//     case Binary b -> "binary";
//     case Event e -> "event";
// };
```

Nhánh `Text` mới xử lý những đối tượng `Text` có `value` rỗng. Một `Text("abc")` không có case nào để chọn. Compiler Java 21 từ chối `switch expression` này vì **không bao phủ hết**.

Sửa bằng cách bổ sung nhánh không guard sau nhánh guarded:

```java
return switch (msg) {
    case Text t when t.value().isEmpty() -> "empty";
    case Text t -> "text";
    case Binary b -> "binary";
    case Event e -> "event";
};
```

Một `when true` là trường hợp đặc biệt: guard bằng biểu thức hằng `true` được coi là không hạn chế pattern khi xét dominance/coverage. Nhưng `when t.value().isEmpty()`, `when n > 0` và phần lớn điều kiện thực tế **không thể** được compiler xem như bao phủ toàn bộ.

**Đừng đánh đồng** “trong dữ liệu hiện tại không có giá trị không thỏa guard” với “compiler chứng minh được exhaustive”. Compiler dựa vào quan hệ kiểu và quy tắc pattern; nó không tự phân tích mọi invariant nghiệp vụ.

## 8. Generic sealed hierarchy: không chỉ đếm tên trong `permits`

Với sealed generic interface, một permitted subtype có thể **không tương thích với một cách gắn type argument cụ thể**. Java tính exhaustiveness theo **kiểu selector**, bao gồm type argument liên quan.

Ví dụ:

```java
sealed interface Token<T> permits StrToken, BoxToken {}

record StrToken(String value) implements Token<String> {}

record BoxToken<T>(T value) implements Token<T> {}
```

Nếu biến có kiểu `Token<Integer>`, kiểu `StrToken` (chỉ hiện thực `Token<String>`) không thể là kiểu runtime hợp lệ của biến `Token<Integer>` trong chương trình dùng generic type an toàn. Do đó, compiler có thể chứng minh `switch` chỉ với nhánh `BoxToken<Integer>` là exhaustive, không cần liệt kê `StrToken` một cách máy móc:

```java
static String asInteger(Token<Integer> value) {
    return switch (value) {
        case BoxToken<Integer> box -> "box:" + box.value();
    };
}
```

Nếu selector có kiểu `Token<String>`, cả `StrToken` và `BoxToken<String>` đều có thể xuất hiện:

```java
static String asString(Token<String> value) {
    return switch (value) {
        case StrToken text -> "str:" + text.value();
        case BoxToken<String> box -> "box:" + box.value();
    };
}
```

Đây là ví dụ Java 21 hợp lệ, cần đặt trong ngữ cảnh khai báo generic sealed interface và record ở trên. Để chạy độc lập, dùng chương trình đầy đủ **`GenericSealedDemo.java`**:

```java
public class GenericSealedDemo {
    sealed interface Token<T> permits StrToken, BoxToken {}

    record StrToken(String value) implements Token<String> {}

    record BoxToken<T>(T value) implements Token<T> {}

    static String asInteger(Token<Integer> value) {
        return switch (value) {
            case BoxToken<Integer> box -> "box:" + box.value();
        };
    }

    static String asString(Token<String> value) {
        return switch (value) {
            case StrToken text -> "str:" + text.value();
            case BoxToken<String> box -> "box:" + box.value();
        };
    }

    public static void main(String[] args) {
        System.out.println(asInteger(new BoxToken<>(42)));
        System.out.println(asString(new StrToken("hi")));
    }
}
```

Chạy:

```bash
javac --release 21 GenericSealedDemo.java
java GenericSealedDemo
```

Đầu ra:

```text
box:42
str:hi
```

**Điều cần nhớ:** *exhaustiveness là câu hỏi về những giá trị có thể có của kiểu selector*, không phải chỉ đếm số mục trong `permits`. Trong trường hợp generic phức tạp, đừng suy luận từ ví dụ có `Token<Integer>` cho mọi cách gắn kiểu khác; hãy để compiler đúng phiên bản kiểm tra.

## 9. Tại sao `switch` sealed có thể bắt lỗi khi phát triển hệ thống?

Giả sử phiên bản đầu tiên có hai kiểu được phép:

```java
sealed interface Transport permits Car, Bike {}
record Car() implements Transport {}
record Bike() implements Transport {}
```

Và có `switch`:

```java
static String dispatch(Transport value) {
    return switch (value) {
        case Car c -> "car";
        case Bike b -> "bike";
    };
}
```

Ở phiên bản này, compiler thấy đủ hai nhánh. Sau đó người phát triển cập nhật sealed interface để cho phép thêm `Bus`:

```java
// BẢN THAY ĐỔI (minh họa, không khai báo song song với bản cũ):
// sealed interface Transport permits Car, Bike, Bus {}
// record Bus() implements Transport {}
```

Khi biên dịch lại những mã nguồn `switch` phụ thuộc, nhánh `Bus` mới có thể làm `dispatch` không còn exhaustive và compiler báo lỗi. Đây là **lợi ích bảo trì rất lớn**: lỗi thiếu xử lý được phát hiện sớm thay vì rơi vào nhánh mặc định không được xem xét.

Nếu trước đây đã viết:

```java
return switch (value) {
    case Car c -> "car";
    case Bike b -> "bike";
    default -> "other";
};
```

thì nhánh `default` vẫn xử lý `Bus`, compiler không bắt buộc cập nhật `switch` khi biên dịch lại. Điều này tốt khi “other” thực sự là hợp đồng mong muốn; nó không tốt nếu mỗi loại phương tiện cần một nghiệp vụ riêng.

### Lưu ý separate compilation và `MatchException`

Compiler chỉ phân tích theo **hệ kiểu tại lần biên dịch**. Nếu một chương trình được biên dịch với sealed hierarchy cũ nhưng chạy cùng các class/binary đã thay đổi theo cách khiến runtime xuất hiện một subtype mà mã `switch` cũ không có nhánh phù hợp, việc Java chứng minh exhaustive từ trước **không bảo đảm** luôn tìm được nhãn match cho dữ liệu mới. Trong trường hợp thiếu nhãn runtime sau sự thay đổi không đồng bộ như vậy, một exhaustive pattern `switch` có thể ném **`java.lang.MatchException`** (Java 21+).

Điều này khác với `NullPointerException` do selector `null`:

- `NullPointerException` xuất hiện khi selector `null` mà không có xử lý `case null`.
- `MatchException` có thể xuất hiện khi runtime không tìm được nhãn cho một giá trị non-null trong bối cảnh thiết kế đã cho phép compiler kết luận exhaustive (ví dụ thay đổi hierarchy nhưng không biên dịch đồng bộ).

**Thực hành:** khi thay đổi sealed hierarchy, nên biên dịch và chạy test các module phụ thuộc đồng bộ; đừng coi `default` là cách thay thế việc quản lý binary compatibility.

## 10. Sealed hierarchy khác enum, legacy switch và chuỗi `if`

**Enum** có miền constant hữu hạn. `switch expression` trên enum có thể exhaustive bằng cách liệt kê mọi constant:

```java
enum Status { NEW, DONE }

static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

Khác với sealed hierarchy, enum không thể bổ sung những subtype mới: thay đổi miền bằng cách thêm enum constant. Trong cả hai trường hợp, không có `default` giúp compiler báo khi danh sách phân loại thay đổi.

**Legacy `switch` statement** (ví dụ `switch(int)` chỉ có constant labels) không phải lúc nào cũng buộc exhaustive:

```java
static void legacy(int x) {
    switch (x) {
        case 1 -> System.out.println("one");
        // Không nhất thiết cần default trong legacy statement.
    }
}
```

**Enhanced `switch` statement** có pattern label trên kiểu như `Shape` phải exhaustive theo Java 21. Điều đó giải thích vì sao quy tắc “statement không cần default” từ Java cũ không áp dụng máy móc cho pattern `switch`.

**Chuỗi `if/else if (x instanceof ...)`** cũng không được compiler kiểm tra exhaustiveness giống `switch` expression, dù `x` là sealed type. Bạn có thể quên một subtype mà Java vẫn biên dịch:

```java
static String byIf(Shape shape) {
    if (shape instanceof Circle) {
        return "circle";
    }
    // Thiếu Quad: Java không tự báo "non-exhaustive if".
    return "other";
}
```

Đây không phải cú pháp sai: lập trình viên cố ý trả về `other`. Nhưng nếu mục tiêu là buộc xử lý đầy đủ từng kiểu, pattern `switch` trên sealed hierarchy diễn đạt ý định tốt hơn.

## 11. Dominance khác với exhaustiveness

Exhaustiveness đặt câu hỏi: **đã bao phủ tất cả giá trị chưa?** Dominance đặt câu hỏi: **có nhánh nào bị nhánh trước che khuất hoàn toàn không?**

Ví dụ không hợp lệ:

```java
// LỖI: nhánh Circle phía sau bị Shape phía trước bao phủ.
// return switch (shape) {
//     case Shape s -> "some shape";
//     case Circle c -> "circle";
// };
```

`case Shape s` là pattern tổng quát cho kiểu selector `Shape` (đối tượng khác null), nên `case Circle c` phía sau không có cơ hội được chọn. Compiler báo **dominated case label**. Về mặt coverage, nhánh đầu có thể đã đủ rộng; nhưng vấn đề ở đây là **cấu trúc case không hợp lệ**, không phải thiếu nhánh.

Đặt kiểu cụ thể trước sẽ hợp lệ:

```java
return switch (shape) {
    case Circle c -> "circle";
    case Shape s -> "other shape";
};
```

Cũng không nên viết `default` riêng sau một pattern `case Shape s` vô điều kiện trên selector `Shape`: Java 21 không cho vừa có unconditional pattern cho selector vừa có nhánh `default` riêng.

Với sealed hierarchy có thể liệt kê từng subtype, **thường không cần dùng `case Shape` tổng quát** chỉ để làm compiler hết báo non-exhaustive: cách đó che việc thêm subtype cần xử lý riêng trong tương lai.

## 12. Các lỗi phổ biến và cách khắc phục

| Nhầm lẫn | Thực tế | Cách làm đúng |
| --- | --- | --- |
| “Có sealed thì mọi switch tự exhaustive” | Cần đủ coverage cho kiểu selector | Liệt kê các subtype hoặc dùng pattern cho nhánh cha thích hợp |
| “Phải thêm default để switch biên dịch” | Sealed/enum có thể được bao phủ tường minh | Bỏ default nếu muốn compiler bắt thiếu subtype |
| “Chỉ đếm các tên trong permits” | Permits chỉ liệt kê subtype trực tiếp; sealed có thể lồng nhau | Phân tích đệ quy hoặc bao phủ nhánh cha |
| “non-sealed phá tính exhaustive của cả hierarchy” | Nhánh non-sealed vẫn có kiểu cha chung | Dùng pattern trên chính nhánh non-sealed, ví dụ `case Event e` |
| “Liệt kê một implementation của non-sealed là đủ” | Non-sealed có thể có vô số subtype khác | Bao phủ interface/class non-sealed hoặc fallback thích hợp |
| “Guarded case phủ toàn bộ một subtype” | Guard tùy ý có thể sai | Thêm unguarded case cho subtype hoặc default |
| “default tự xử lý null” | Default đơn lẻ không bắt selector null | Thêm `case null` khi muốn xử lý |
| “Exhaustive nghĩa là không có lỗi runtime” | Guard có thể ném ngoại lệ; null có thể gây NPE; binary drift có thể gây MatchException | Kiểm tra dữ liệu và tương thích phiên bản |
| “Có thể dùng case lớp cha trước lớp con” | Nhánh lớp con sau đó bị dominated | Đặt pattern cụ thể trước |
| “Generic sealed luôn cần mọi subclass trong permits” | Một instantiation có thể loại subtype bất tương thích | Xét type argument của selector, biên dịch đúng release |
| “Java 17 dùng pattern switch như Java 21” | Java 17 chưa có pattern switch ổn định | Dùng JDK 21+ cho các ví dụ |

## 13. Checklist thiết kế `switch` với sealed types

1. **Xác định kiểu tĩnh của selector**, bao gồm generic arguments.
2. **Vẽ cây `permits` trực tiếp**, đánh dấu nhánh nào `final`, `sealed`, `non-sealed`.
3. **Quyết định mức phân loại**: từng lá hay một pattern chung cho nhánh cha?
4. **Kiểm tra coverage đệ quy**: với mỗi subtype có thể xảy ra, có case nào chắc chắn áp dụng không?
5. **Xem các guard**: `when` có thể thất bại; cần nhánh không guard để bao phủ phần còn lại.
6. **Xác định chính sách `null`**: để Java ném `NullPointerException` hay xử lý bằng `case null`?
7. **Quyết định có cần `default` không**: fallback cho kiểu mở, hay muốn compiler cảnh báo subtype mới?
8. **Sắp xếp nhánh tránh dominance**: cụ thể trước tổng quát, nhánh guarded trước nhánh unguarded cùng kiểu.
9. **Kiểm thử thay đổi hierarchy**: thêm một subtype trong môi trường thử nghiệm và kiểm tra compile-time errors mong muốn.
10. **Biên dịch đúng phiên bản và đồng bộ binary**: dùng `javac --release 21` cho pattern `switch`, quản lý lại bản build khi thay đổi sealed hierarchy.

## 14. Tự kiểm tra kiến thức

**Câu 1.** `sealed interface S permits A, B`, cả `A` và `B` là record. `switch(S)` có `case A` và `case B` nhưng không có `default` thì sao?

**Đáp án:** Hợp lệ và exhaustive trong Java 21, nếu toàn bộ permitted direct subclasses đúng là `A`, `B` và các case bao phủ đầy đủ. `null` vẫn cần xem xét riêng.

**Câu 2.** `S permits A, Branch`, và `Branch` là `sealed` cho phép `B1`, `B2`. Chỉ viết `case A` và `case Branch` có đủ không?

**Đáp án:** Có, vì `case Branch` nhận mọi đối tượng là subtype của `Branch`, kể cả `B1`, `B2`.

**Câu 3.** Một permitted direct subtype `Event` là `non-sealed`. Nếu chỉ liệt kê `Ping implements Event` thì `switch` đã exhaustive chưa?

**Đáp án:** Chưa, vì còn các implementation `Event` khác có thể tồn tại. `case Event e` bao phủ cả nhánh mở.

**Câu 4.** Chỉ có `case Text t when t.value().isEmpty()` trong nhánh Text của sealed `Message`; có đủ không?

**Đáp án:** Không. `Text("abc")` là một giá trị hợp lệ nhưng guard sai; cần `case Text t` không guard hoặc một fallback phù hợp.

**Câu 5.** Vì sao `switch(Token<Integer>)` trong ví dụ generic có thể chỉ cần `BoxToken<Integer>` mà không có `StrToken`?

**Đáp án:** `StrToken` chỉ implement `Token<String>`, không phù hợp với kiểu selector `Token<Integer>`; generic type argument làm thay đổi các subtype có thể xảy ra.

**Câu 6.** Một sealed switch không có `default` đã biên dịch thành công. Có bảo đảm tuyệt đối sẽ không ném ngoại lệ runtime không?

**Đáp án:** Không. `null` có thể gây `NullPointerException`, phép tính trong nhánh có thể ném ngoại lệ, và thay đổi binary/sealed hierarchy không đồng bộ có thể dẫn tới `MatchException`.

**Câu 7.** Vì sao `default` có thể không tốt khi thêm một subtype mới cần xử lý riêng?

**Đáp án:** `default` khiến mã cũ vẫn exhaustive khi biên dịch lại, nên compiler không buộc lập trình viên viết nhánh cho subtype mới. Bỏ `default` giúp lỗi biên dịch đóng vai trò cảnh báo thiếu xử lý.

### Ghi nhớ cốt lõi

**Sealed đóng tập các nhánh kế thừa trực tiếp; exhaustive analysis dùng kiểu selector và cây kiểu đó để chứng minh mọi giá trị cần thiết đã được case xử lý.** Không phải lúc nào cũng cần `default`; nhưng luôn phải xét nhánh `non-sealed`, guard có thể sai, generic type arguments và chính sách `null`. Đây là lợi ích thực tế của sealed hierarchy khi kết hợp với pattern `switch` trong Java 21: mô hình dữ liệu và kiểm tra tính đầy đủ của logic điều khiển được gắn với nhau ngay từ lúc biên dịch.

### Tài liệu chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21 §14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [JLS Java SE 21 §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JLS Java SE 21 §8.1.1.2 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
