# Suy luận type argument trong pattern — Java Generics, reifiable types và record patterns

Với Java Generics, câu hỏi dễ gây nhầm lẫn là: **compiler có thể tự suy ra type argument trong một pattern hay không, và nếu có, điều đó có nghĩa là Java kiểm tra được type argument ở runtime hay không?** Hai việc này khác nhau.

Trong **Java 21+**, một *generic record pattern* như `Box(var value)` có thể được compiler suy luận thành pattern ứng với `Box<String>` nếu giá trị cần khớp đã có **kiểu tĩnh** `Box<String>`. Khi đó biến thành phần `value` có kiểu tĩnh `String` và sử dụng được các phương thức của `String`. Tuy nhiên, cơ chế này **không khôi phục type argument đã bị xóa ở runtime**: nếu chỉ có một tham chiếu kiểu `Object`, Java không thể tự đoán rằng một `Box` đang chứa `String` rồi coi `value` là `String`.

Bài học phân biệt bốn khái niệm:

1. **Type argument**: kiểu được truyền cho một generic type, chẳng hạn `String` trong `Box<String>`.
2. **Type inference**: compiler suy ra kiểu phù hợp từ thông tin *tại thời điểm biên dịch*.
3. **Reifiable type**: kiểu còn đủ thông tin cần thiết để được kiểm tra ở runtime, ví dụ `String` hoặc `List<?>`.
4. **Pattern matching**: kiểm tra giá trị theo pattern, và binding các pattern variable khi khớp.

Trọng tâm là suy luận type argument của **record pattern**, không phải một phép kiểm tra runtime tổng quát cho mọi generic type.

## 1. Bối cảnh: Generic và type erasure

Ví dụ khai báo một generic record:

```java
record Box<T>(T value) {}
```

Có thể tạo:

```java
Box<String> names = new Box<>("Java");
Box<Integer> numbers = new Box<>(21);
```

`T` là **type parameter** của `Box`. `String` và `Integer` là **type argument** ở từng kiểu sử dụng. Compiler dùng thông tin này để kiểm tra các phép gán và lời gọi phương thức:

```java
String text = names.value();
Integer count = numbers.value();
```

Ở runtime, do **type erasure**, thông tin `String`/`Integer` của kiểu tham số hóa thông thường không hiện diện như một “mã kiểu đầy đủ” có thể đem đi thử bằng `instanceof`. JVM biết đối tượng thuộc lớp `Box`, nhưng không thể dựa riêng vào đối tượng để chứng minh an toàn rằng nó là `Box<String>` thay vì `Box<Integer>`.

Ví dụ sau **không biên dịch** khi biến đầu vào có kiểu tĩnh `Object`:

```java
Object unknown = java.util.List.of("Java");

// LỖI: không thể kiểm tra an toàn List<String> từ Object.
// if (unknown instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

Đối với kiểu `List<String>`, phép thử này đòi hỏi thông tin về `String` vốn không được giữ lại để kiểm tra toàn bộ tham số kiểu ở runtime. Cách hợp lệ từ `Object` là kiểm tra bằng `List<?>` rồi kiểm tra từng phần tử nếu cần:

```java
if (unknown instanceof java.util.List<?> values) {
    for (Object item : values) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

`List<?>` là một **reifiable type** theo các quy tắc của Java; `List<String>` nói chung **không phải** reifiable. Suy luận kiểu ở compiler không làm thay đổi thực tế đó.

## 2. Vì sao generic record pattern được suy luận trong Java 21?

Xét lại:

```java
record Box<T>(T value) {}
```

Từ Java 21, ta viết được một record pattern với type argument tường minh:

```java
static void explicit(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Ở đây kiểu tĩnh của đối tượng kiểm tra đã là `Box<String>`; việc khớp record pattern có thể thực hiện phép kiểm tra phù hợp mà **không cần chuyển đổi unchecked** từ kiểu đầu vào sang `Box<String>`.

Compiler còn có thể suy luận type argument khi ta **bỏ phần `<String>`** trong record pattern:

```java
static void inferred(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Trong ví dụ này, compiler suy luận record pattern `Box(var text)` theo ngữ cảnh thành kiểu tương ứng với `Box<String>`, rồi suy ra biến thành phần `text` có kiểu tĩnh `String`.

**Hai mức suy luận khác nhau:**

- **Suy luận type argument của record pattern:** từ kiểu tĩnh của `box` là `Box<String>`, compiler suy ra đối số kiểu `String` cho `Box(...)`.
- **Suy luận kiểu của component pattern `var text`:** sau khi biết kiểu record pattern, compiler biết thành phần `value` có kiểu `String`; biến `text` cũng được xem là `String`.

`var` ở đây là *type pattern trong danh sách thành phần record*; nó không phải biến `Object` mặc định và cũng không gọi một phương thức tự đoán kiểu runtime.

Cú pháp `Box(var text)` trong vị trí pattern **không phải lời gọi constructor**, và việc bỏ `<String>` **không có nghĩa là cố ý dùng raw type theo cách unchecked**. Java định nghĩa một phép suy luận type argument riêng cho record pattern khi type argument không được viết ra.

## 3. Đọc từng bước một phép suy luận

Xét chương trình Java 21:

```java
Box<String> source = new Box<>("Java");

if (source instanceof Box(var text)) {
    System.out.println(text.length());
}
```

Có thể phân tích như sau:

| Bước | Thông tin compiler có | Hệ quả |
| --- | --- | --- |
| 1. Target | `source` có kiểu tĩnh `Box<String>` | Compiler biết kiểu tham số hóa của biến tại vị trí sử dụng |
| 2. Record pattern | Cú pháp `Box(var text)` chưa ghi type argument | Compiler xét generic record `Box<T>` với kiểu target |
| 3. Type argument inference | Ràng buộc tương thích từ `Box<String>` | Suy ra đối số kiểu phù hợp là `String` |
| 4. Component pattern | Thành phần `value` của `Box<String>` có kiểu `String` | `var text` giới thiệu biến `text` có kiểu tĩnh `String` |
| 5. Flow scoping | Nhánh `if` chỉ chạy khi pattern khớp | `text.length()` hợp lệ và cho kết quả `4` |

Mô hình:

```text
Kiểu tĩnh của target: Box<String>
                |
                v
        record Box<T>(T value)
                |
                v
      pattern: Box(var text)
                |
                v
  suy luận T từ ngữ cảnh -> String
                |
                v
  suy luận kiểu thành phần -> String text
                |
                v
  runtime match thành công -> binding text
                |
                v
     text.length() hợp lệ
```

Phần **suy luận kiểu** thuộc về **compiler**. Phần **thử pattern và binding giá trị** diễn ra khi thực thi. Đừng đảo ngược trình tự để cho rằng Java chạy đến đối tượng, thấy một `String` rồi tái tạo type argument `T = String` từ runtime.

## 4. Ví dụ đầy đủ: suy luận một, hai và nhiều tầng type argument

Lưu nội dung sau vào tệp **`RecordInferenceDemo.java`**. Chương trình dùng Java 21+:

```java
record Box<T>(T value) {}
record Pair<T, U>(T first, U second) {}

public class RecordInferenceDemo {
    static void one(Box<String> source) {
        if (source instanceof Box(var text)) {
            System.out.println("upper=" + text.toUpperCase());
            System.out.println("length=" + text.length());
        }
    }

    static void two(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var label, var count)) {
            System.out.println("pair=" + label.toUpperCase() + ":" + (count + 1));
        }
    }

    static void nested(Box<Box<String>> outer) {
        if (outer instanceof Box(Box(var text))) {
            System.out.println("nested=" + text.length());
        }
    }

    static void unknown(Object source) {
        if (source instanceof Box(var value)) {
            Object kept = value;
            System.out.println("runtime=" + kept.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        one(new Box<>("java"));
        two(new Pair<>("java", 4));
        nested(new Box<>(new Box<>("Java")));
        unknown(new Box<>("actual String"));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac RecordInferenceDemo.java
java RecordInferenceDemo
```

Kết quả:

```text
upper=JAVA
length=4
pair=JAVA:5
nested=4
runtime=String
```

Giải thích:

- **`one`:** tham số `Box<String>` cho phép compiler suy luận `Box(var text)` thành kiểu tương ứng với `Box<String>`; `text` có kiểu tĩnh `String`.
- **`two`:** từ `Pair<String, Integer>`, compiler suy luận đồng thời hai type argument `T = String` và `U = Integer`. Vì thế `label.toUpperCase()` và phép cộng `count + 1` đều hợp lệ.
- **`nested`:** từ `Box<Box<String>>`, compiler suy luận các record pattern lồng nhau, đi từ lớp `Box` ngoài đến `Box` trong và cuối cùng suy ra `text` là `String`.
- **`unknown`:** target được khai báo là `Object`. Record pattern vẫn có thể khớp đối tượng `Box`, nhưng compiler **không thể suy ra type argument cụ thể `String` từ kiểu tĩnh `Object`**. Biến thành phần `value` chỉ có kiểu có thể sử dụng an toàn như `Object`. Dòng `getClass().getSimpleName()` trả về `String` ở runtime, nhưng đó là quan sát lớp thực tế của giá trị, không phải bằng chứng compiler đã suy luận `T = String`.

Một biểu thức có giá trị runtime giống hệt nhau vẫn có thể dẫn đến **khả năng suy luận kiểu khác nhau** nếu được nhìn qua các kiểu tĩnh khác nhau. Đây là đặc điểm bình thường của hệ thống kiểu Java.

## 5. Khác biệt căn bản: target là `Box<String>` hay `Object`?

So sánh:

```java
Box<String> typed = new Box<>("Java");
Object unknown = typed;

if (typed instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // Hợp lệ: text có kiểu String
}

if (unknown instanceof Box(var item)) {
    System.out.println(item);                // Hợp lệ
    // System.out.println(item.toUpperCase()); // LỖI nếu mở comment
}
```

Trong nhánh `unknown`, compiler không có thông tin rằng đối tượng đang được nhìn dưới kiểu `Box<String>`. Biến `item` không có phương thức `toUpperCase()` trong kiểu tĩnh mà compiler suy ra. Muốn dùng nó như `String`, cần kiểm tra thành phần:

```java
if (unknown instanceof Box(var item) && item instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Cách này **không tuyên bố** toàn bộ object có kiểu tham số hóa `Box<String>`; nó chỉ kiểm tra rằng object là một `Box` phù hợp với record pattern và giá trị thành phần thực sự là `String`.

Điều này đặc biệt hữu ích với object đến từ deserialization, API không khai báo generic chính xác, hay một tập hợp nhiều kiểu khác nhau. Hãy suy luận từ **kiểu tĩnh thật sự có trong chữ ký và biến**, sau đó kiểm tra runtime ở phần dữ liệu cần dùng.

## 6. Vì sao không thể viết `Box<String>` pattern tùy ý trên `Object`?

Cú pháp sau **không hợp lệ** với target kiểu `Object`:

```java
Object unknown = new Box<>("Java");

// Sai: kiểm tra Box<String> từ Object cần unchecked conversion.
// if (unknown instanceof Box<String>(var text)) {
//     System.out.println(text.length());
// }
```

Compiler không được phép biến một phép thử kiểu runtime chỉ biết đối tượng thuộc `Box` thành một lời khẳng định an toàn rằng đối tượng thuộc `Box<String>`. Kiểu tham số hóa cụ thể không phải thứ JVM kiểm tra đầy đủ bằng `instanceof`.

Ngay cả khi đối tượng cụ thể trong ví dụ **đang chứa một chuỗi**, `unknown` vẫn có kiểu tĩnh `Object`. Một chương trình khác có thể truyền `new Box<>(42)`, và Java không thể dựa vào erasure để phân biệt toàn bộ `Box<String>` với `Box<Integer>`.

**Quy tắc về checked cast:** với generic record pattern có type argument tường minh, phép kiểm tra chỉ hợp lệ nếu target có thể được chuyển đổi tới kiểu record pattern bằng một **checked cast conversion**, không đòi hỏi unchecked conversion. Vì vậy:

- Từ `Box<String>` sang record pattern phù hợp `Box<String>(...)`: có thông tin kiểu tĩnh cần thiết, có thể hợp lệ.
- Từ `Object` hoặc raw `Box` tới `Box<String>(...)`: không thể tự khẳng định type argument cụ thể bằng phép cast checked; compiler từ chối trong các ví dụ trên.
- Từ `Object` sang `Box(var item)`: có thể hợp lệ, nhưng type argument suy ra phải phản ánh lượng thông tin kiểu tĩnh thực sự có được; không tự hóa thành `String`.

Lưu ý: không nên kết luận mọi đoạn code chứa `instanceof SomeGeneric<Concrete>` đều luôn bị cấm trong mọi ngữ cảnh. Java xét **kiểu tĩnh của target và tính checked của chuyển đổi**. Ví dụ chuẩn `Object instanceof List<String>` không an toàn, nhưng các pattern có kiểu tham số hóa phù hợp với một target đã biết cũng có thể được chấp nhận. Phải đọc **ngữ cảnh**, không chỉ nhìn mỗi dấu `<...>`.

## 7. Suy luận type argument và suy luận kiểu `var` không phải một bước duy nhất

Hai cú pháp:

```java
Box<String> box = new Box<>("Hi");

if (box instanceof Box(var value)) {
    System.out.println(value.length());
}
```

đặt ra hai câu hỏi khác nhau:

1. **`Box<T>` được chuyên biệt hóa thế nào trong pattern?** Compiler suy luận đối số kiểu của record pattern từ kiểu đầu vào `Box<String>`.
2. **`var value` có kiểu gì?** Sau khi suy luận record pattern, compiler xem kiểu khai báo của record component tương ứng; ở đây `T` đã tương ứng `String`, nên `value` có kiểu `String`.

Nếu đầu vào là `Pair<String, Integer>`, mỗi component có thể có một kiểu khác nhau. Nếu đầu vào là `Box<Box<String>>`, suy luận áp dụng qua các cấp pattern. Nếu đầu vào là `Object`, không có cơ sở để tự suy luận `String`.

`var` trong component list của record pattern **không phải phép kiểm tra runtime “đoán kiểu tùy ý”** và cũng không cho phép viết `if (obj instanceof var x)` như một type pattern độc lập. `var` ở đây có vai trò đặc biệt của pattern thành phần.

Không nên nhầm với toán tử diamond `<>` của constructor:

```java
Box<String> box = new Box<>("Java");
```

Trong dòng này, `new Box<>(...)` sử dụng **diamond inference khi tạo đối tượng**. Trong `box instanceof Box(var text)`, compiler lại áp dụng **record pattern type inference khi khớp dữ liệu**. Hai vị trí đều có suy luận generic, nhưng ngữ cảnh và quy tắc áp dụng khác nhau.

## 8. Suy luận trong `switch` cũng hoạt động (Java 21+)

Record pattern type inference không giới hạn ở `instanceof`. Ví dụ `switch expression` sau suy luận các biến thành phần từ kiểu tĩnh `Pair<String, Integer>`:

```java
record Pair<T, U>(T first, U second) {}

static String describe(Pair<String, Integer> pair) {
    return switch (pair) {
        case null -> "missing";
        case Pair(var label, var number) -> label.toUpperCase() + ":" + (number + 1);
    };
}
```

Đoạn trên là **minh họa phương thức**, giả định `Pair` được khai báo trong chương trình. Khi gọi với `new Pair<>("java", 4)`, giá trị trả về là `"JAVA:5"`; với `null`, trả về `"missing"`. Pattern `Pair(var label, var number)` có thể suy luận từ kiểu selector `Pair<String, Integer>`.

Điểm quan trọng:

- Compiler suy luận kiểu `label` và `number` từ kiểu selector/record, chứ không phải từ nội dung chuỗi mà nhánh `switch` sẽ tạo ra.
- Record pattern **không khớp `null` của chính đối tượng record**; ví dụ có `case null` riêng.
- Điều kiện `case` được kiểm tra rồi mới thực hiện biểu thức ở vế phải `->`. Hai giai đoạn pattern matching và expression evaluation không đồng nhất.

Cần **JDK 21+** vì cả record patterns và pattern matching cho `switch` được chuẩn hóa trong Java 21. Không mang cú pháp này vào dự án biên dịch `--release 17`.

## 9. Type erasure, reifiable types và wildcard liên quan thế nào?

Tách rõ các ví dụ:

| Cú pháp / kiểu | Có thể kiểm tra trực tiếp theo ví dụ? | Ý nghĩa |
| --- | --- | --- |
| `obj instanceof String text` với `obj` kiểu `Object` | Có (Java 17+) | `String` là kiểu runtime xác định được; khi khớp, `text` là `String` |
| `obj instanceof List<?> list` với `obj` kiểu `Object` | Có (Java 17+) | Kiểm tra được đối tượng có phải `List`; các phần tử chỉ có thể dùng an toàn dưới kiểu `Object` |
| `obj instanceof List<String> list` với `obj` kiểu `Object` | Không | Không thể kiểm tra toàn bộ type argument `String` ở runtime từ `Object` |
| `box instanceof Box(var s)` với `box` kiểu `Box<String>` | Có (Java 21+) | Suy luận generic record pattern nhờ kiểu tĩnh của target; `s` là `String` |
| `obj instanceof Box(var s)` với `obj` kiểu `Object` | Có (Java 21+) | Khớp record, nhưng không có cơ sở suy luận `s` là `String` |
| `obj instanceof Box<String>(var s)` với `obj` kiểu `Object` | Không | Yêu cầu chuyển đổi unchecked để khẳng định kiểu generic cụ thể |

**Reifiable type** nói về thông tin runtime có sẵn để thử kiểu; **type inference** nói về việc compiler giải các ràng buộc kiểu khi biên dịch. Một pattern có thể chứa generic type argument được suy luận **mà không phải vì JVM bất ngờ giữ lại type argument đã bị erasure**.

Nếu code kiểm tra `List<?>` rồi lấy phần tử, chỉ dùng kiểu `String` sau khi kiểm tra từng phần tử; không cast toàn bộ danh sách thành `List<String>` một cách mù quáng.

### Ví dụ Java 17+ chạy được khi không có record patterns

Lưu **`GenericBoundaryDemo.java`**:

```java
public class GenericBoundaryDemo {
    static void inspect(Object source) {
        if (source instanceof java.util.List<?> values) {
            System.out.println("size=" + values.size());
            if (!values.isEmpty() && values.get(0) instanceof String text) {
                System.out.println("first=" + text.toUpperCase());
            }
        }
    }

    public static void main(String[] args) {
        inspect(java.util.List.of("java", "core"));
    }
}
```

```bash
javac GenericBoundaryDemo.java
java GenericBoundaryDemo
```

Đầu ra:

```text
size=2
first=JAVA
```

Ví dụ chỉ dựa vào `List<?>` và type pattern `String text` của `instanceof`, nên phù hợp Java 17. Đây là lựa chọn thực tế khi dữ liệu ban đầu chỉ có kiểu `Object` mà ứng dụng phải kiểm tra an toàn.

## 10. Giới hạn của kiểu suy luận khi dùng wildcard, raw type và bound

Giả sử:

```java
Box<?> wildcardBox = new Box<>("Java");
Object any = wildcardBox;
```

Cả `wildcardBox` lẫn `any` đều không cho phép compiler **khẳng định type argument cụ thể là `String`**, dù nội dung hiện tại là một chuỗi. Với `Box<?>`, kiểu component bị giới hạn bởi thông tin wildcard; với `Object`, thông tin của generic record còn ít hơn. Việc `new Box<>("Java")` xuất hiện trong một đường đi thực thi cụ thể không thay thế được kiểu tĩnh của biến ở nơi pattern được viết.

Với một kiểu có bound, chẳng hạn:

```java
record NumericBox<T extends Number>(T value) {}
```

compiler có thể dùng các ràng buộc của `T extends Number` trong suy luận. Tuy nhiên bound **`Number` không đồng nghĩa `Integer`**: nếu không có thông tin `Integer` từ kiểu tĩnh thích hợp, không được gọi phương thức riêng của `Integer` như thể compiler đã suy luận chính xác kiểu ấy.

**Raw type** (ví dụ khai báo `Box raw`) làm mất kiểm tra generic. Tránh dùng raw type để “lách” lỗi compile của record pattern. Nếu dữ liệu đi từ thư viện legacy qua raw type, hãy nâng chữ ký generic nếu có thể hoặc kiểm tra component bằng pattern thích hợp trước khi xử lý.

Có thể có các tình huống suy luận phức tạp hơn với `? extends ...`, `? super ...`, capture conversion hoặc giao diện generic mà record triển khai. Java dùng ràng buộc kiểu tĩnh, bound và quy tắc suy luận của JLS để tìm kiểu hợp lệ; không nhất thiết luôn cho một concrete class duy nhất. Nguyên tắc an toàn vẫn là **chỉ dùng các phương thức được khai báo trên kiểu mà compiler thực sự suy luận**.

## 11. Một sắc thái về `null` trong record pattern

**Đối tượng record ở ngoài cùng là `null`** sẽ không khớp một record pattern:

```java
Object source = null;
// source instanceof Box(var content) cho kết quả false.
```

Nhưng **thành phần bên trong record có thể là `null`**. Với component pattern không điều kiện, `var` trong danh sách record component có thể binding cả giá trị `null`:

```java
Box<String> box = new Box<>(null);
if (box instanceof Box(var content)) {
    System.out.println(content == null); // true
}
```

Điều này hợp lệ trong Java 21: outer record `box` không `null` và record pattern khớp; `content` được binding tới giá trị `null` của component. **Suy luận `content` có kiểu `String` không bảo đảm giá trị runtime khác `null`.** Không gọi `content.length()` khi chưa kiểm tra null nếu record có thể chứa null.

Sắc thái này nhắc lại rằng **type inference** xác định kiểu tĩnh; **null-safety** là một yêu cầu kiểm tra riêng. Không nên suy ra dữ liệu non-null chỉ vì compiler đã suy luận được type argument.

## 12. Các lỗi thường gặp

1. **Nhầm suy luận generic với runtime type inspection.** `Box(var value)` có thể suy luận `String` từ `Box<String>` tại compile time; nó không có năng lực “đọc” type argument `String` từ mọi đối tượng `Box` runtime.
2. **Bỏ qua kiểu tĩnh của target.** `Object obj = new Box<>("Java")` không tương đương với `Box<String> obj = new Box<>("Java")` về thông tin compiler sử dụng tại pattern.
3. **Cho rằng `var` luôn suy ra lớp runtime của component.** Với target `Object`, biến component chỉ có kiểu đủ an toàn theo ngữ cảnh, không mặc nhiên là `String` dù object hiện đang chứa chuỗi.
4. **Thử kiểu không reifiable từ `Object`.** `instanceof List<String>` hoặc `instanceof Box<String>(...)` không trở thành checked chỉ vì ta viết type argument tường minh.
5. **Nhầm `Box(var x)` với constructor hoặc raw cast.** Trong vị trí record pattern, Java suy luận type argument theo ngữ cảnh và khớp thành phần record.
6. **Sử dụng phương thức vượt kiểu được suy luận.** Khi biến có kiểu `Object`, không gọi trực tiếp `toUpperCase()`; cần thêm `instanceof String text` hoặc thay đổi chữ ký đầu vào để giữ được thông tin.
7. **Dùng raw type để bỏ qua compiler.** Raw type làm tăng nguy cơ heap pollution và unchecked operation; nó không cung cấp runtime verification của generic argument.
8. **Bỏ qua tính null của component.** Một biến pattern có kiểu `String` vẫn có thể nhận component `null` trong record pattern phù hợp.
9. **Nhầm mốc phiên bản.** Java 17 hỗ trợ type pattern cho `instanceof` nhưng không hỗ trợ record patterns chính thức; cú pháp `Box(var x)` và record pattern trong `switch` của bài cần Java 21+.
10. **Suy luận quá sâu từ kết quả in ra.** `value.getClass() == String.class` chỉ chứng minh lớp runtime của một giá trị thành phần; không chứng minh `Box` mang type argument `String` theo cách JVM kiểm tra đầy đủ.

## 13. Cách quyết định khi viết code

Khi muốn dùng generic trong pattern matching, thực hiện lần lượt:

1. **Xác định kiểu tĩnh của target tại vị trí kiểm tra.** `Box<String>`, `Box<?>`, raw `Box`, `Object` hay interface generic nào?
2. **Xác định loại pattern.** Type pattern thông thường hay record pattern có các component? Java 21+ mới có record pattern chính thức.
3. **Nếu là generic record pattern:** type argument được khai báo rõ hay cần compiler suy luận? Các ràng buộc từ target và bound có đủ thông tin để suy luận không?
4. **Xem kiểu thực tế được compiler gán cho component variable.** `String`, `Integer`, `Object` hay kiểu bound/wildcard? Chỉ gọi API có trong kiểu ấy.
5. **Kiểm tra chuyển đổi checked.** Đừng ép target `Object` thành một generic record type cụ thể nếu cần unchecked conversion.
6. **Kiểm tra null và flow scope.** Pattern variable chỉ hợp lệ khi pattern khớp và trong vùng luồng điều khiển cho phép; component bên trong record vẫn có thể `null`.
7. **Chạy đúng phiên bản Java.** Dự án Java 17 nên dùng `instanceof List<?>`/type pattern thông thường và kiểm tra từng thành phần; Java 21+ có thể dùng record pattern inference.

Một phép thử ngắn giúp tự kiểm tra suy luận: đổi khai báo target từ `Box<String> box` thành `Object box` rồi xem lời gọi `text.toUpperCase()` có còn được compiler chấp nhận hay không. Nếu không, điều đó cho thấy **thông tin generic đã đến từ kiểu tĩnh của target**, không phải phép “phát hiện” `String` từ runtime.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): generic records, type inference, `var` và nested record patterns.
- [Java Language Specification 21 — `18.5.5 Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): quy tắc suy luận đối số kiểu của generic record pattern.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): mốc chuẩn hóa record patterns và pattern matching cho `switch`.
