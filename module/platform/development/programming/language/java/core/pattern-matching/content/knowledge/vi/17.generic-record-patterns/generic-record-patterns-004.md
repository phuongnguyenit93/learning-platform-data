# Wildcard trong generic record pattern (Java 21)

## 1. Mục tiêu và bối cảnh

Bài học tập trung vào cách sử dụng **wildcard (`?`)** trong **generic record pattern** để đọc dữ liệu từ record có tham số kiểu chưa biết, kết hợp với pattern lồng nhau mà vẫn giữ an toàn kiểu. Sau bài học, bạn sẽ:

- Viết và đọc được `Box<?>(var value)`, `Box<?>(String text)`, `Pair<?, ?>(...)` và nested record patterns.
- Phân biệt **wildcard** với kiểu cụ thể, `Object` và **raw type**.
- Giải thích giới hạn của runtime matching do **type erasure**, kể cả các trường hợp biên dịch lỗi.
- Hiểu kiểu tĩnh của biến được tách ra, sự khác nhau giữa `?` và bound từ khai báo generic.
- Nhận ra wildcard không tạo bản sao dữ liệu và không bảo đảm bất biến.

**Phiên bản:** Record class là tính năng chuẩn từ Java 16; record patterns (JEP 440) và pattern matching cho `switch` là tính năng chuẩn từ **Java 21**. Các ví dụ đầy đủ trong bài dùng JDK 21 hoặc mới hơn, không cần `--enable-preview`.

## 2. Wildcard có ý nghĩa gì trong record pattern?

Khai báo một generic record:

```java
record Box<T>(T value) {}
```

Một đối tượng có thể được tạo như `new Box<>("Java")`, `new Box<>(42)` hoặc `new Box<>(List.of(1, 2))`. Khi mã chỉ nhận `Object input`, nó chưa biết record chứa dữ liệu kiểu gì. **Unbounded wildcard** `?` cho phép biểu diễn "`Box` có tham số kiểu nào đó, nhưng hiện chưa biết kiểu cụ thể":

```java
Object input = new Box<>("Java");

if (input instanceof Box<?>(var value)) {
    System.out.println(value); // Java
}
```

`Box<?>(var value)` gồm hai phần:

1. **`Box<?>`** kiểm tra hình dạng record ngoài là `Box` với tham số kiểu chưa xác định. Dấu `?` không phải biến, không có giá trị để gán, và không suy ra `T = Object`.
2. **`(var value)`** là component pattern. Java lấy component `value()` của `Box` và gán vào biến `value` khi match thành công. Với `Box<T>` không giới hạn `T`, kiểu tĩnh có thể dùng an toàn từ biến này là `Object`.

Dấu `?` có thể xuất hiện nhiều lần khi record có nhiều tham số kiểu:

```java
record Pair<L, R>(L left, R right) {}

Object input = new Pair<>("total", 12);
if (input instanceof Pair<?, ?>(String label, Integer count)) {
    System.out.println(label + "=" + count); // total=12
}
```

Ở đây `Pair<?, ?>` không kiểm tra rằng `L` được khai báo là `String` hay `R` được khai báo là `Integer`. Hai **component patterns** `String label` và `Integer count` mới kiểm tra các giá trị thực tế bằng runtime type check. Nếu giá trị không khớp, toàn bộ pattern thất bại.

### So sánh với các cách viết gần giống

| Cách viết | Ý nghĩa |
| --- | --- |
| `Box<?>` | `Box` với tham số kiểu chưa biết; có thể kiểm tra kiểu ngoài tại runtime |
| `Box<Object>` | `Box` được tham số hóa bằng đúng `Object` ở mức kiểu tĩnh |
| `Box<String>` | `Box` với đối số kiểu `String`; từ `Object` không thể xác nhận trực tiếp thông tin `String` tại runtime |
| `Box` (raw type) | Bỏ kiểm tra generic của trình biên dịch; nên tránh khi không tương tác API cũ |
| `Box<?>(String text)` | Kiểm tra `Box`, rồi kiểm tra giá trị component thực sự là `String` |

Java generic **invariant**: `Box<String>` không phải subtype của `Box<Object>`, nhưng có thể tham chiếu bằng `Box<?>`. Dùng `<?>` khi muốn *quan sát* dữ liệu không phụ thuộc tham số kiểu và không cần giả định kiểu cụ thể.

## 3. Từ wildcard đến kiểm tra kiểu component

Record patterns và type patterns có thể kết hợp trực tiếp trong `instanceof` hoặc `switch`:

```java
record Box<T>(T value) {}

static String describe(Object input) {
    return switch (input) {
        case Box<?>(String text) -> "String: " + text;
        case Box<?>(Integer number) -> "Integer: " + number;
        case Box<?>(var value) -> "Other: " + value;
        case null -> "null";
        default -> "not Box";
    };
}
```

Các nhánh được xét theo thứ tự:

- `Box<?>(String text)` chỉ khớp nếu đầu vào là `Box` và giá trị component là một `String` không `null`.
- `Box<?>(Integer number)` tương tự với `Integer`.
- `Box<?>(var value)` nhận các giá trị component còn lại, **kể cả component bằng `null`**. Biến `value` chưa có kiểu cụ thể hơn để gọi phương thức riêng của `String` hay `Integer`.
- `case null` xử lý khi **toàn bộ đầu vào** là `null`; khác với `new Box<>(null)`.
- `default` xử lý các giá trị không phải `Box`.

Ví dụ, `new Box<Number>(42)` vẫn có thể khớp `Box<?>(Integer number)`: pattern kiểm tra **giá trị** là `Integer`, không xác minh đối số kiểu gốc `T` là `Integer`.

Khi thêm nhánh `Box<?>(List<?> items)`, Java kiểm tra component là một `List`, nhưng không xác nhận kiểu phần tử. Chỉ có thể biết chắc `items` có kiểu `List<?>`, không phải `List<String>`.

## 4. Nested wildcard record patterns

Có thể lồng record pattern khi component của record ngoài lại là một generic record:

```java
record Box<T>(T value) {}
record Envelope<T>(Box<T> payload, String tag) {}

Object input = new Envelope<>(new Box<>("book"), "VN");

if (input instanceof Envelope<?>(Box<?>(String item), String tag)) {
    System.out.println(item + "@" + tag); // book@VN
}
```

Quá trình match đi từ ngoài vào trong:

1. Kiểm tra `input` là `Envelope<?>` và lấy `payload()`, `tag()`.
2. Kiểm tra `payload` là `Box<?>`.
3. Kiểm tra `payload.value()` thực sự là `String`, rồi bind `item`.
4. Kiểm tra `tag()` là `String` và bind `tag`.

Nếu bất kỳ bước nào thất bại, pattern tổng thể không khớp; biến pattern không đi vào phạm vi sử dụng của nhánh thành công. Nested record pattern dùng **accessor** để lấy component, không tạo record mới hay ép đối số generic thành kiểu không được chứng minh.

Với nhiều tham số, `Pair<?, ?>(var left, var right)` cũng hợp lệ; mỗi dấu `?` là một kiểu chưa biết có thể khác nhau. Đừng ngầm giả định rằng hai dấu `?` cùng biểu diễn một kiểu.

## 5. Chương trình Java 21 hoàn chỉnh

Lưu đoạn dưới đây thành **`WildcardRecordPatternDemo.java`**. Chương trình mô tả wildcard ở record ngoài, nested patterns, nhiều tham số kiểu, bound trong khai báo record và tác động lên danh sách mutable.

```java
import java.util.*;

public class WildcardRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(Box<T> payload, String tag) {}
    record NumberBox<T extends Number>(T value) {}
    record Batch<E>(List<E> items) {}

    static String describe(Object input) {
        return switch (input) {
            case Box<?>(String s) -> "String: " + s;
            case Box<?>(Integer n) -> "Integer: " + n;
            case Box<?>(List<?> items) -> "List size: " + items.size();
            case Box<?>(var value) -> "Other: " + value;
            case null -> "null";
            default -> "not Box";
        };
    }

    static String nested(Object input) {
        return switch (input) {
            case Envelope<?>(Box<?>(String name), String tag) ->
                    name + "@" + tag;
            case Envelope<?>(Box<?>(var value), var tag) ->
                    value + "@" + tag;
            default -> "unknown";
        };
    }

    static void inspectPair(Object input) {
        if (input instanceof Pair<?, ?>(String name, Integer count)) {
            System.out.println("Pair: " + name + "=" + count);
        }
    }

    static void readBounded(Object input) {
        if (input instanceof NumberBox<?>(var n)) {
            Number number = n;
            System.out.println("Number: " + number);
        }
    }

    static void changeList(Batch<?> batch) {
        if (batch instanceof Batch<?>(var items)) {
            System.out.println("Before clear: " + items);
            items.clear();
            System.out.println("After clear: " + items);
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(new Box<>("Java")));
        System.out.println(describe(new Box<>(12)));
        System.out.println(describe(new Box<>(List.of("A", "B"))));
        System.out.println(describe(new Box<>(3.5)));
        System.out.println(describe(new Box<>(null)));
        System.out.println(describe(null));
        System.out.println(describe("plain text"));

        System.out.println(nested(new Envelope<>(new Box<>("book"), "VN")));
        System.out.println(nested(new Envelope<>(new Box<>(2026), "ID")));

        inspectPair(new Pair<>("score", 8));
        inspectPair(new Pair<>("score", "eight"));
        readBounded(new NumberBox<>(5.5));

        List<String> mutable = new ArrayList<>(List.of("A", "B"));
        changeList(new Batch<>(mutable));
        System.out.println("Original: " + mutable);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac --release 21 WildcardRecordPatternDemo.java
java WildcardRecordPatternDemo
```

**Đầu ra chính xác:**

```text
String: Java
Integer: 12
List size: 2
Other: 3.5
Other: null
null
not Box
book@VN
2026@ID
Pair: score=8
Number: 5.5
Before clear: [A, B]
After clear: []
Original: []
```

Phân tích kết quả:

- `Box<String>` và `Box<Integer>` được nhận diện bằng **kiểu component ở runtime**, không phải bằng cách kiểm tra đối số generic `T`.
- `Box<List<String>>` đi vào nhánh `List<?>` do component có kiểu runtime là `List`. Nhánh không chứng minh phần tử là `String`.
- `Box<Double>` đi vào `Box<?>(var value)`. Với `new Box<>(null)`, `var value` vẫn có thể nhận `null`, khác với đối tượng đầu vào `null`.
- Pattern của `Envelope<?>` xử lý nhiều cấp; nhánh dành cho `String` đứng trước nhánh `var` tổng quát.
- `Pair<?, ?>(String name, Integer count)` in ra một dòng cho cặp có giá trị `"score"`, `8`. Cặp `("score", "eight")` không khớp và không in gì.
- `NumberBox<?>` có kiểu tham số `T extends Number` ngay trong khai báo record. Vì vậy `var n` có thể gán an toàn vào biến `Number`.
- `Batch<?>` không cấm `clear()` trên danh sách mutable; thay đổi đó lan về biến `mutable` đã được truyền vào constructor.

## 6. Type erasure: wildcard làm được gì và không làm được gì?

Java generic chủ yếu được kiểm tra ở **thời điểm biên dịch**. Sau type erasure, runtime thường biết đối tượng là `Box`, nhưng không giữ đủ thông tin để phân biệt đáng tin cậy `Box<String>` với `Box<Integer>`.

Vì `Box<?>` có toàn bộ type arguments là wildcard không giới hạn, đây là **reifiable type**, có thể dùng trong phép kiểm tra từ một giá trị `Object`. Ngược lại, `Box<String>` hoặc `Box<? extends Number>` không phải kiểu reifiable theo cách đó.

Các ví dụ sau **cố ý không biên dịch** khi `input` có kiểu khai báo `Object`:

```java
record Box<T>(T value) {}

// Lỗi: không thể kiểm tra đầy đủ T == String tại runtime.
if (input instanceof Box<String>(var text)) {
    System.out.println(text);
}

// Lỗi: không thể kiểm tra bound của đối số kiểu trong Box ở runtime.
if (input instanceof Box<? extends Number>(var number)) {
    System.out.println(number);
}

// Lỗi: các phần tử List<String> không thể kiểm tra qua generic tại runtime.
if (input instanceof Box<?>(List<String> names)) {
    System.out.println(names);
}
```

Khối trên chỉ là **các ví dụ lỗi biên dịch để phân tích**, không phải mã đặt vào phương thức `main` để chạy.

**Cách sửa khi cần đối chiếu một giá trị `String`:**

```java
if (input instanceof Box<?>(String text)) {
    System.out.println(text.toUpperCase());
}
```

**Cách sửa khi component là `List`:** match `Box<?>(List<?> items)`, rồi kiểm tra từng phần tử bằng `instanceof String` hoặc dùng một API/kiểu dữ liệu đã xác minh. Không ép `List<?>` thành `List<String>` chỉ vì record có dữ liệu mẫu giống chuỗi.

**Cách làm việc với bound:** dùng bound tại nơi khai báo, như `record NumberBox<T extends Number>(T value) {}`. Trong `NumberBox<?>(var n)`, `n` có thể được xem là `Number` nhờ ràng buộc khai báo. Hoặc, khi đã có biến `Box<? extends Number> numericBox` nhờ kiểm tra tĩnh từ API gọi, `Number n = numericBox.value();` hợp lệ. Đừng coi `instanceof Box<? extends Number>` trên một `Object` là phép xác minh runtime cho bound đó.

## 7. Wildcard capture và phạm vi sử dụng biến pattern

Với `Box<?>(var value)`, dấu `?` có nghĩa là tồn tại một kiểu nào đó nhưng **chưa biết là kiểu nào**. Trình biên dịch không cho phép bạn tự suy diễn `value` thành `String`:

```java
if (input instanceof Box<?>(var value)) {
    Object ok = value;
    // String notSafe = value; // không biên dịch nếu thiếu kiểm tra kiểu
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Với `record Batch<E>(List<E> items) {}`, `Batch<?>(var items)` cho phép đọc danh sách theo kiểu `List<?>`. Kiểu phần tử chưa biết nên các thao tác thêm phần tử tùy ý không an toàn:

```java
if (batch instanceof Batch<?>(var items)) {
    Object first = items.isEmpty() ? null : items.get(0);
    // items.add("X"); // lỗi biên dịch: không biết E có nhận String hay không
    items.clear();       // hợp lệ về kiểu; thay đổi danh sách nếu mutable
}
```

Ví dụ này giả định `batch` là biến thuộc kiểu thích hợp, chẳng hạn `Batch<?>`. `items.clear()` có thể thành công (như chương trình đầy đủ) hoặc ném `UnsupportedOperationException` nếu danh sách không hỗ trợ sửa.

**Nguyên tắc sử dụng:** sau khi tách bằng `<?>`, xử lý component theo thao tác chung của kiểu được biết. Muốn dùng thao tác riêng của một subtype, thực hiện pattern check tương ứng ở component hoặc cung cấp type token/validation từ thiết kế API.

## 8. Wildcard không phải cơ chế bất biến

Record giữ các trường component `private final`, nhưng chỉ **bất biến nông** nếu component trỏ đến đối tượng mutable. Dấu `?` không sao chép dữ liệu và không ngăn thao tác sửa đổi mà API của component cho phép.

Trong chương trình hoàn chỉnh:

```java
List<String> mutable = new ArrayList<>(List.of("A", "B"));
Batch<?> batch = new Batch<>(mutable);

if (batch instanceof Batch<?>(var items)) {
    items.clear();
}
System.out.println(mutable); // []
```

Dù `Batch<?>` không cho biết kiểu phần tử, danh sách vẫn là **cùng đối tượng** được truyền vào. `List<?>` cản việc thêm một `String` tùy ý vì an toàn kiểu; nó **không** tự chặn `clear()`, `remove(...)` hay các phương thức sửa cấu trúc khác.

Nếu bài toán cần giữ dữ liệu ổn định, hãy thực hiện defensive copy ở constructor của record:

```java
record SafeBatch<E>(List<E> items) {
    SafeBatch {
        Objects.requireNonNull(items);
        items = List.copyOf(items);
    }
}
```

`List.copyOf` tạo hoặc tái sử dụng danh sách không sửa được, tách khỏi các thay đổi sau này trên danh sách mutable nguồn; nó không sao chép sâu các phần tử mutable. Nếu `E` là đối tượng có setter, phần tử vẫn có thể thay đổi theo tham chiếu. Ví dụ trên là **khai báo minh họa**, có thể đặt vào một lớp Java chứa các record khác; nó không kèm `main`.

Với record pattern, accessor do record cung cấp được dùng để lấy component. Nếu accessor trả về mảng hoặc đối tượng mutable, biến được bind có thể làm lộ chính tham chiếu đó; muốn bảo vệ mảng, thường phải sao chép khi nhận vào **và** khi trả qua accessor, đồng thời cân nhắc contract của `equals`/`hashCode`.

## 9. Quy tắc thiết kế, thứ tự nhánh và các lỗi thường gặp

| Tình huống | Cách xử lý |
| --- | --- |
| Chỉ cần biết đầu vào là một generic record và đọc nội dung | Dùng `Box<?>(var value)` |
| Cần xử lý riêng thành phần `String`/`Integer` | Dùng `Box<?>(String s)` hoặc `Box<?>(Integer n)` |
| Record có nhiều type parameters độc lập | Dùng đúng số wildcard, ví dụ `Pair<?, ?>(...)` |
| Component là một record generic khác | Dùng nested pattern, ví dụ `Envelope<?>(Box<?>(String s), var tag)` |
| Cần biết element type của `List<?>` | Kiểm tra từng phần tử hoặc xác minh tại ranh giới API |
| Cần giữ subtype bound của một record | Khai báo `T extends Number` ở record hoặc dùng kiểu API đã được kiểm tra |
| Component có thể thay đổi | Defensive copy/immutable components; wildcard không giải quyết bất biến |
| Giá trị đầu vào có thể bằng `null` | Tách `case null` khỏi trường hợp record có component `null` |

Những lỗi cần tránh:

1. **Viết `Box<String>(var s)` để kiểm tra kiểu generic từ `Object`.** Type erasure không cung cấp phép kiểm tra đó; dùng `Box<?>(String s)` để kiểm tra *giá trị thành phần*.
2. **Hiểu nhầm `Box<?>(String s)` đảm bảo record đã được tạo bằng `T = String`.** Một `Box<Object>` chứa `String` cũng có thể match.
3. **Cho rằng `Box<?>(List<?> xs)` chứng minh tất cả phần tử là cùng một kiểu.** Nó mới chứng minh component là `List`.
4. **Đặt nhánh `case Box<?>(var value)` trước nhánh cụ thể.** Nhánh tổng quát có thể che khuất các nhánh riêng, khiến `switch` báo lỗi dominated case.
5. **Đọc `?` như `Object` hoặc raw type.** Wildcard giữ kiểm tra generic tĩnh; raw type làm mất phần bảo vệ đó.
6. **Gọi phương thức riêng của `String` trên biến `var value` chưa được kiểm tra.** Hãy dùng component type pattern hoặc `instanceof`.
7. **Nghĩ rằng `Box<?>(var value)` bảo vệ dữ liệu bên trong.** Pattern chỉ truy cập qua accessor; copy và tính bất biến phải do thiết kế record đảm nhiệm.
8. **Nhầm `new Box<>(null)` với đầu vào `null`.** Khi dùng `var` cho component, trường hợp thứ nhất vẫn có thể match record, còn trường hợp thứ hai cần `case null`.
9. **Chạy record patterns trên JDK 17 mà không kiểm tra phiên bản.** Record class đã có ở JDK 17 nhưng record patterns là tính năng chuẩn ở Java 21.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Box<?>` dùng được với `Object input`, còn `Box<String>` không thích hợp để runtime test đối số kiểu?  
*Đáp án:* `Box<?>` là dạng reifiable, còn Java type erasure không duy trì thông tin cụ thể `T = String` để runtime đối chiếu đáng tin cậy.

**Câu 2.** `Box<?>(String s)` sẽ khớp với `new Box<Object>("x")` không?  
*Đáp án:* Có. Nó kiểm tra object ngoài là `Box` và component thực sự là `String`.

**Câu 3.** `Pair<?, ?>(String a, Integer b)` có buộc hai wildcard liên hệ cùng kiểu không?  
*Đáp án:* Không. Chúng độc lập; các component patterns kiểm tra từng giá trị thực tế.

**Câu 4.** Trong `NumberBox<T extends Number>`, vì sao `NumberBox<?>(var n)` có thể đọc `n` như `Number`?  
*Đáp án:* Vì upper bound `T extends Number` được khai báo trong kiểu record, nên biến component có upper bound đó ở mức kiểu tĩnh.

**Câu 5.** Vì sao `Batch<?>(var items)` không cho phép `items.add("A")` nhưng có thể cho phép `items.clear()`?  
*Đáp án:* Không biết kiểu phần tử nên thêm `String` có thể sai kiểu; `clear()` không thêm phần tử nên hợp lệ về generic, dù có thể sửa danh sách mutable.

**Câu 6.** Wildcard giúp immutable record như thế nào?  
*Đáp án:* Wildcard không làm dữ liệu bất biến. Cần thiết kế component bất biến, defensive copy và accessor phù hợp.

## Tham khảo

- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Java Language Specification 21 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
- [Oracle Java Tutorials — Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/wildcards.html)
