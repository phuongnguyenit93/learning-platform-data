# Kiểu đích và ảnh hưởng của ngữ cảnh gán hoặc truyền đối số trong suy luận kiểu Java

## 1. Vấn đề cần giải quyết

Java Generics cho phép trình biên dịch **suy luận tham số kiểu** của phương thức generic, constructor dùng diamond `<>` và nhiều biểu thức khác từ thông tin sẵn có. Một nguồn thông tin đặc biệt quan trọng là **kiểu đích** (*target type*): kiểu mà kết quả của biểu thức cần tương thích tại vị trí sử dụng.

Hai dòng mã trông tương tự nhưng có thể dẫn đến suy luận khác nhau:

```java
List<Number> numbers = List.of(1, 2);
var integers = List.of(1, 2);
```

Ở dòng đầu, biểu thức `List.of(1, 2)` được dùng trong **ngữ cảnh gán** có kiểu đích `List<Number>`. Trình biên dịch có thể chọn tham số kiểu `E = Number`, vì `Integer` có thể được chuyển thành `Number`.

Ở dòng thứ hai, `var` không cung cấp một kiểu đích cụ thể. Các phần tử `1`, `2` được boxing thành `Integer`; kiểu của biến `integers` được suy luận là `List<Integer>`.

Sự khác biệt này ảnh hưởng đến khả năng truyền kết quả vào phương thức khác, giữ thông tin kiểu, chọn wildcard và tránh phải ép kiểu.

Bài học này tập trung vào **kiểu đích và ảnh hưởng của ngữ cảnh gán hoặc truyền đối số**, trong module Java Core Generics, với các ví dụ phù hợp Java 17+.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **kiểu đích**, **kiểu của biểu thức**, **kiểu trả về khai báo** và **kiểu phần tử runtime**.
2. Xác định ngữ cảnh gán, truyền đối số, `return`, lambda và method reference cung cấp thông tin kiểu như thế nào.
3. Giải thích vì sao một lời gọi generic như `List.of(1)` có thể được dùng dưới `List<Number>`, trong khi biến đã có kiểu `List<Integer>` không tự động gán được cho `List<Number>`.
4. Dự đoán ảnh hưởng của `var`, diamond `<>`, type witness `<T>` và target typing đối với chương trình.
5. Biết giới hạn của suy luận: target type không phá vỡ tính bất biến của Generics, không tự đổi kiểu đối tượng đã khai báo và không thay thế kiểm tra kiểu.
6. Viết và kiểm tra được các ví dụ Java 17 có đầu ra xác định.

## 3. Khái niệm: biểu thức có kiểu đích là gì?

Một biểu thức có **kiểu đích** khi Java dùng yêu cầu về kiểu ở vị trí đặt biểu thức để kiểm tra hoặc suy luận kiểu của chính biểu thức đó.

Ví dụ:

```java
List<Number> values = List.of(1, 2);
```

Ở đây:

- Bên trái có kiểu `List<Number>`: đó là kiểu đích.
- Bên phải gọi phương thức generic `List.of(E... elements)`: cần suy luận `E`.
- Hai đối số nguyên được boxing thành `Integer`.
- Suy luận có thể chọn `E = Number`, sao cho cả các giá trị `Integer` đều chấp nhận được và biểu thức tương thích với `List<Number>`.

Một biểu thức có thể phụ thuộc kiểu đích được gọi là **poly expression** khi đáp ứng các điều kiện của Java Language Specification. Ngược lại, **standalone expression** tự xác định kiểu mà không phụ thuộc vào target type theo cùng cơ chế.

Không phải mọi biểu thức đều là poly expression. Cũng không phải cứ bên trái có một kiểu là Java sẽ tự thay đổi kiểu của mọi biểu thức bên phải. **Chính loại biểu thức và quy tắc ngữ cảnh quyết định** thông tin kiểu đích có được dùng hay không.

### 3.1. Ba câu hỏi cần phân biệt

Với đoạn:

```java
List<Number> numbers = List.of(1, 2);
```

Hỏi: "Biểu thức tạo ra loại đối tượng nào ở runtime?" — Một đối tượng implementation của `List` chứa các tham chiếu đến phần tử `Integer`.

Hỏi: "Biến `numbers` có kiểu tĩnh gì?" — `List<Number>`.

Hỏi: "Thông tin `Number` từ đâu?" — Từ kiểu đích của phép gán, được sử dụng trong suy luận lời gọi generic.

Type erasure có nghĩa JVM không mang một `List<Number>` tách biệt hoàn toàn với `List<Integer>` chỉ vì type argument khác nhau. Nhưng **kiểm tra kiểu tĩnh** tại lúc biên dịch vẫn rất quan trọng.

## 4. Ngữ cảnh gán: kiểu bên trái có thể tham gia suy luận

Xét phương thức generic độc lập về mặt ý tưởng:

```java
static <T> List<T> one(T value) {
    return List.of(value);
}
```

Các phép gán sau đều hợp lệ:

```java
List<Integer> a = one(1);
List<Number> b = one(1);
List<Object> c = one(1);
```

Trình biên dịch có thể chọn `T` khác nhau tùy yêu cầu của biểu thức đích. Trong các phép gán đó, lời gọi `one(1)` không bị buộc phải có kiểu `List<Integer>` từ trước khi xét ngữ cảnh gán.

**Điểm quan trọng:** `one(1)` là một *lời gọi generic method* có thể tham gia suy luận; nó khác với **một biến** đã được khai báo là `List<Integer>`.

### 4.1. Gán từ một biểu thức generic và gán từ biến đã có kiểu

```java
List<Number> direct = List.of(1, 2); // Hợp lệ.

List<Integer> integers = List.of(1, 2);
// List<Number> invalid = integers;   // LỖI BIÊN DỊCH.
```

Tại sao?

- `List.of(1, 2)` là lời gọi generic; kiểu đích có thể tham gia suy luận tham số kiểu của lần gọi đó.
- `integers` là biểu thức biến với kiểu tĩnh **đã được xác lập** là `List<Integer>`; phép gán không suy luận lại type argument của biến.
- `List<Integer>` không phải subtype của `List<Number>`, bởi Java Generics **bất biến** (*invariant*) theo tham số kiểu.

Nếu có thể gán `integers` cho `List<Number>`, người dùng tham chiếu mới có thể thêm một `Double` vào danh sách `Integer`, gây vi phạm an toàn kiểu.

### 4.2. Cách sửa khi đã có một `List<Integer>`

Nếu chỉ cần **đọc** như `Number`, dùng wildcard:

```java
List<Integer> integers = List.of(1, 2);
List<? extends Number> view = integers;
Number first = view.get(0);
```

Nếu cần **danh sách `List<Number>` mới** để thêm nhiều subtype của `Number`, sao chép:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>(integers);
numbers.add(2.5);
```

`new ArrayList<>(integers)` là tạo danh sách mới có type argument suy luận theo ngữ cảnh; đây là **sao chép nông**, không biến danh sách `integers` gốc thành `List<Number>`.

## 5. Ngữ cảnh truyền đối số: kiểu tham số của phương thức là đầu mối suy luận

Kiểu đích không chỉ xuất hiện bên trái dấu `=`. Khi truyền một biểu thức vào lời gọi phương thức, **tham số hình thức** cũng có thể tạo ra ngữ cảnh kiểu cho biểu thức đối số.

Ví dụ:

```java
static void acceptNumbers(List<Number> values) {
    System.out.println(values);
}

static <T> List<T> one(T value) {
    return List.of(value);
}
```

Trong lời gọi:

```java
acceptNumbers(one(10)); // HỢP LỆ.
```

Trình biên dịch biết `acceptNumbers` cần `List<Number>`. Lời gọi generic `one(10)` có thể được kiểm tra/suy luận sao cho `T = Number`, dù đối số cụ thể `10` được boxing thành `Integer`.

Đối chiếu:

```java
List<Integer> existing = one(10);
// acceptNumbers(existing); // LỖI: List<Integer> khác List<Number>.
```

Thông tin kiểu đích từ tham số phương thức giúp **lời gọi generic lồng bên trong**, nhưng không tự nới kiểu của một biến đã được định kiểu.

### 5.1. Phân biệt tham số generic và tham số cụ thể

```java
static void receiveExact(List<Number> values) { }

static void receiveProducer(List<? extends Number> values) { }
```

Với `List<Integer> integers`:

```java
List<Integer> integers = List.of(1, 2);

// receiveExact(integers);    // Sai vì generic invariant.
receiveProducer(integers);    // Đúng nhờ wildcard extends.
receiveExact(List.of(1, 2)); // Đúng nhờ suy luận với target type.
```

Ba dòng trên minh họa **hai cơ chế khác nhau**:

1. `receiveProducer(integers)`: chấp nhận tham số đã có kiểu `List<Integer>` theo quy tắc wildcard.
2. `receiveExact(List.of(1, 2))`: lời gọi `List.of` có thể được suy luận theo ngữ cảnh truyền đối số để tạo biểu thức tương thích `List<Number>`.

Không nên trộn hai cơ chế và nói rằng Java có covariance tự động cho `List<T>`.

### 5.2. Suy luận qua nhiều tham số

Xét:

```java
static <T> void appendAll(
        List<? super T> destination,
        List<? extends T> source) {
    destination.addAll(source);
}
```

Lời gọi sau hợp lệ:

```java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2);
appendAll(numbers, integers);
```

Trình biên dịch giải đồng thời các ràng buộc từ hai đối số:

- Kiểu của `source` phải tương thích `List<? extends T>`.
- Kiểu của `destination` phải tương thích `List<? super T>`.

Ví dụ `T = Integer` là lựa chọn phù hợp: nguồn có `Integer`, đích `Number` có thể nhận `Integer`.

Đây là mẫu sử dụng PECS. Suy luận generic có thể phối hợp nhiều ràng buộc; không nhất thiết từng đối số phải có đúng kiểu `List<T>` ban đầu.

## 6. Biểu thức `return`: chữ ký trả về là ngữ cảnh

Trong phương thức:

```java
static List<Number> provideNumbers() {
    return List.of(1, 2.5);
}
```

`List<Number>` trong khai báo phương thức là kiểu đích của biểu thức `return`. Lời gọi `List.of` có thể suy luận `E = Number` để chấp nhận cả `Integer` và `Double`.

Tương tự:

```java
static Optional<CharSequence> provideText() {
    return Optional.of("Java");
}
```

`Optional.of(T value)` là một lời gọi generic, còn `Optional<CharSequence>` là kiểu đích trong ngữ cảnh `return`.

Đừng nhầm với:

```java
static List<Number> invalid() {
    List<Integer> local = List.of(1, 2);
    // return local; // Lỗi: local có kiểu List<Integer> cố định.
    return new ArrayList<>(local); // Hợp lệ: tạo List<Number> mới.
}
```

Kiểu trả về có thể hướng dẫn suy luận **trong biểu thức return**, nhưng không thay đổi kiểu tĩnh của `local`.

## 7. `var` làm thay đổi nguồn cung cấp kiểu đích

`var` suy luận kiểu **biến cục bộ** từ initializer, chứ không truyền một contract tường minh như `List<Number>` xuống lời gọi bên phải:

```java
List<Number> widened = List.of(1, 2); // E có thể là Number.
var narrowed = List.of(1, 2);         // List<Integer>.
```

Kiểu của `narrowed` được cố định ngay khi khai báo. Nó không trở thành `List<Number>` khi được dùng về sau. `var` vẫn có kiểu tĩnh, không phải kiểu động.

Một lời gọi không có đối số dữ liệu còn thể hiện khác biệt rõ hơn:

```java
List<String> texts = Collections.emptyList(); // T là String.
var unknown = Collections.emptyList();        // List<Object>.
```

Trong trường hợp `var`, không có kiểu đích String, nên suy luận mặc định có thể dùng Object. Khi cần contract phần tử, hãy khai báo rõ biến hoặc chọn type witness tại nơi tạo dữ liệu.

## 8. Diamond `<>` cũng chịu ảnh hưởng của ngữ cảnh

```java
List<Number> numbers = new ArrayList<>(); // ArrayList<Number>.
var objects = new ArrayList<>();          // ArrayList<Object>.
var strings = new ArrayList<>(List.of("A")); // ArrayList<String>.
```

Diamond không đồng nghĩa Object: đối số constructor như `List.of("A")` có thể ràng buộc tham số kiểu ngay cả khi dùng `var`. Phân biệt diamond `<>` (yêu cầu suy luận lúc tạo đối tượng) với wildcard `<?>` (đối số kiểu chưa biết trong một kiểu được sử dụng); `new ArrayList<?>()` không hợp lệ. Bài **Diamond** trình bày thêm các constructor và generic class lồng nhau; bài **var với diamond** đi sâu vào trường hợp thiếu thông tin khiến kiểu thành Object.

## 9. Lời gọi generic method: target type tham gia cùng đối số

Định nghĩa:

```java
static <T> T choose(T left, T right) {
    return left;
}
```

Một lời gọi như:

```java
Number n = choose(1, 2.5);
```

có các ràng buộc:

- `Integer` (sau boxing) phải được chấp nhận làm `T`.
- `Double` phải được chấp nhận làm `T`.
- Kết quả trả về `T` phải tương thích với kiểu đích `Number`.

Trình biên dịch có thể suy luận một `T` phù hợp các điều kiện, và `n` có kiểu khai báo là `Number`.

Ngược lại:

```java
// Integer i = choose(1, 2.5); // Lỗi: Double không thể trở thành Integer.
```

Kiểu đích **không thể ép** một lời gọi nhận đối số không tương thích. Suy luận phải đồng thời thỏa các ràng buộc do tham số, cận generic và target type đưa ra.

### 9.1. Type witness: chỉ định tham số kiểu tường minh

Khi muốn làm rõ ý định hoặc xử lý trường hợp suy luận khó đọc, có thể viết type witness:

```java
List<Number> numbers = List.<Number>of(1, 2.5);
Number value = TargetTypingDemo.<Number>choose(1, 2.5);
```

Ở đây `TargetTypingDemo` là tên class chứa phương thức `static choose`, được định nghĩa đầy đủ trong chương trình phần 13.

Type witness `<Number>` yêu cầu type argument của lời gọi generic là `Number`. Nó **khác** với diamond `<>` ở constructor: một bên chỉ định kiểu, một bên yêu cầu suy luận.

Đừng dùng type witness để che đi một API khai báo kiểu sai. Nếu một phương thức vốn trả `List<Integer>` cố định, viết type witness ở caller không tự biến nó thành `List<Number>`.

## 10. Lambda: target type xác định functional interface

Lambda **cần ngữ cảnh kiểu** (target type là một functional interface), ví dụ:

```java
Function<String, Integer> length = text -> text.length();
```

Target type `Function<String, Integer>` cung cấp:

- Kiểu của tham số lambda `text`: `String`.
- Kiểu kết quả mà thân lambda phải tương thích: `Integer`.
- Hợp đồng phương thức chức năng `apply`.

Vì thế:

```java
int n = length.apply("Java"); // 4
```

Trái lại:

```java
// var lambda = value -> value; // LỖI BIÊN DỊCH
```

Một lambda tự thân không xác định functional interface mà nó triển khai; `var` ở khai báo biến không cung cấp target functional interface tương ứng.

### 10.1. Lambda trong ngữ cảnh truyền đối số

```java
static void useText(Function<String, Integer> fn) {
    System.out.println(fn.apply("Java"));
}

useText(text -> text.length()); // Hợp lệ.
```

Ở lời gọi, kiểu tham số `Function<String, Integer>` tạo target type cho lambda. Compiler hiểu `text` có kiểu `String` dù không khai báo kiểu ngay trong lambda.

Đây là một minh họa quan trọng rằng **ngữ cảnh truyền đối số có thể ảnh hưởng không chỉ generic method mà cả kiểu của lambda**.

### 10.2. Lambda là đầu vào cho generic method

```java
static <T, R> R transform(T value, Function<? super T, ? extends R> fn) {
    return fn.apply(value);
}

Integer size = transform("Java", text -> text.length());
```

Compiler dùng kiểu `String` của đối số `"Java"`, target `Integer` của phép gán và chữ ký `Function<? super T, ? extends R>` để tìm ràng buộc phù hợp cho `T`, `R`.

Nếu cần hiểu một lỗi inference, hãy xem **tất cả vị trí đóng góp ràng buộc**: kiểu của đối số đầu vào, tham số hàm chức năng, biểu thức kết quả lambda, và kiểu đích của toàn lời gọi.

## 11. Method reference cũng nhận kiểu từ ngữ cảnh

Ví dụ:

```java
Function<String, Integer> length = String::length;
Supplier<List<String>> emptyStrings = Collections::emptyList;
```

`String::length` phù hợp với functional interface nhận `String` và trả `Integer` (giá trị `int` được boxing khi cần). `Collections::emptyList` là method reference đến generic method; functional interface `Supplier<List<String>>` cung cấp ràng buộc cho việc suy luận `T = String`.

```java
List<String> result = emptyStrings.get();
```

Nhưng:

```java
// var ref = String::length; // LỖI: method reference cần target type.
```

Không có một functional interface cụ thể, compiler không xác định được kiểu method reference chỉ từ cú pháp `String::length`.

## 12. Biểu thức điều kiện `?:` và kiểu đích

Trong ngữ cảnh gán, **reference conditional expression** có thể là poly expression. Target type có thể được dùng khi kiểm tra từng nhánh:

```java
boolean enabled = true;

List<Number> result = enabled
        ? List.of(1, 2)
        : List.of(2.5, 3.5);
```

Ở đây, cả hai nhánh `List.of(...)` là các lời gọi generic có thể tương thích với target `List<Number>`. Dù một nhánh chứa `Integer`, nhánh kia chứa `Double`, phép gán vẫn hợp lệ.

Đừng suy luận rằng **mọi** biểu thức `?:` đều hoạt động theo target type. Quy tắc Java phân biệt conditional expression với các loại boolean/numeric/reference, và chỉ một số loại reference conditional expression ở các ngữ cảnh thích hợp mới là poly expression.

### 12.1. Khi sử dụng `var` với conditional expression

```java
var result = enabled
        ? List.of(1, 2)
        : List.of(2.5, 3.5);
```

Biến `result` không có target type `List<Number>` tường minh, nên trình biên dịch xác định kiểu từ các nhánh theo những quy tắc type combination (*least upper bound*) tương ứng. Không nên khẳng định kiểu cuối luôn là `List<Number>`; có thể là một kiểu tổng hợp chứa wildcard/intersection phức tạp hơn.

Nếu API cần `List<Number>`, khai báo rõ kiểu đích để giữ hợp đồng dễ hiểu:

```java
List<Number> values = enabled
        ? List.of(1, 2)
        : List.of(2.5, 3.5);
```

## 13. Chương trình Java 17+ hoàn chỉnh, chạy được

Lưu đoạn sau thành **`TargetTypingDemo.java`**. Mã cố ý trình bày cả ngữ cảnh gán, truyền đối số, `return`, diamond, lambda, method reference và `var`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class TargetTypingDemo {
    static <T> List<T> one(T value) {
        return List.of(value);
    }

    static <T> T choose(T left, T right) {
        return left;
    }

    static void acceptNumbers(List<Number> values) {
        System.out.println("argument=" + values);
    }

    static List<Number> returnedNumbers() {
        return List.of(3, 4.5);
    }

    static void useText(Function<String, Integer> lengthFn) {
        System.out.println("lambda=" + lengthFn.apply("Java"));
    }

    public static void main(String[] args) {
        List<Number> assigned = one(1);
        System.out.println("assignment=" + assigned);

        acceptNumbers(one(2));
        System.out.println("return=" + returnedNumbers());

        Number selected = choose(5, 6.5);
        System.out.println("choose=" + selected);

        List<Number> diamond = new ArrayList<>();
        diamond.add(7);
        diamond.add(2.5);
        System.out.println("diamond=" + diamond);

        var integers = List.of(8, 9);
        List<Number> copied = new ArrayList<>(integers);
        copied.add(10.5);
        System.out.println("var=" + integers);
        System.out.println("copy=" + copied);

        useText(text -> text.length());

        Function<String, Integer> length = String::length;
        System.out.println("reference=" + length.apply("abcd"));

        Supplier<List<String>> empty = Collections::emptyList;
        System.out.println("empty=" + empty.get().size());

        boolean flag = true;
        List<Number> conditional = flag
                ? List.of(11)
                : List.of(12.5);
        System.out.println("conditional=" + conditional);
    }
}
```

Biên dịch và chạy:

```bash
javac TargetTypingDemo.java
java TargetTypingDemo
```

Stdout chính xác:

```text
assignment=[1]
argument=[2]
return=[3, 4.5]
choose=5
diamond=[7, 2.5]
var=[8, 9]
copy=[8, 9, 10.5]
lambda=4
reference=4
empty=0
conditional=[11]
```

Diễn giải theo thứ tự:

1. `assigned` có kiểu đích `List<Number>`, giúp lời gọi `one(1)` suy luận tham số kiểu tương thích.
2. `acceptNumbers(one(2))` dùng ngữ cảnh truyền đối số `List<Number>` cho lời gọi `one(2)`.
3. `returnedNumbers()` có `return List.of(...)` được kiểm tra với `List<Number>`.
4. `choose(5, 6.5)` kết hợp ràng buộc từ `Integer`, `Double` và target `Number`; phương thức trả về đối số đầu tiên nên in `5`.
5. `new ArrayList<>()` nhận kiểu phần tử `Number` từ khai báo `List<Number> diamond`.
6. `var integers` có kiểu `List<Integer>` từ initializer `List.of(8, 9)`; bản sao `List<Number>` là collection khác và nhận thêm `Double`.
7. Lambda `text -> text.length()` được định kiểu theo tham số `Function<String, Integer>`.
8. Method reference `String::length` phù hợp functional interface `Function<String, Integer>`.
9. `Collections::emptyList` nhận target `Supplier<List<String>>`.
10. Biểu thức điều kiện gồm hai lời gọi `List.of` được kiểm tra với target `List<Number>`; `flag = true` nên kết quả là `[11]`.

**Lưu ý về mutability:** `List.of` trả về danh sách không cho phép sửa. Việc `List.of` được suy luận thành `List<Number>` không đồng nghĩa `add` sẽ chạy thành công; với `List.of`, lệnh sửa vẫn có thể ném `UnsupportedOperationException`. Bản sao `new ArrayList<>(...)` trong ví dụ mới là mutable.

## 14. Vì sao compiler không luôn suy luận đúng “ý định của ta”?

### 14.1. Kiểu đích không phá invariance

```java
List<Integer> source = List.of(1);
// List<Number> target = source; // Lỗi.
```

Target `List<Number>` không thể làm `source` đổi từ `List<Integer>` sang `List<Number>`. Đây là phép gán giữa hai kiểu đã xác định, không phải lời gọi generic cần suy luận.

### 14.2. Kiểu đích không “chữa” đối số không tương thích

```java
static <T extends Number> T identity(T value) {
    return value;
}

// Number invalid = identity("text"); // Lỗi vì String không phải Number.
```

Dù target `Number` có vẻ rộng, cận `T extends Number` và đối số `String` mâu thuẫn. Không có lựa chọn `T` hợp lệ.

### 14.3. Không phải mọi generic API đều trả về kiểu `T` cần suy luận

```java
static List<Integer> fixed() {
    return List.of(1, 2);
}

// List<Number> result = fixed(); // Lỗi.
```

Phương thức `fixed()` khai báo trả về `List<Integer>` cụ thể. Compiler không được thay chữ ký thành `List<Number>` chỉ vì caller mong điều đó.

### 14.4. Kiểu đích không đổi runtime subtype

```java
List<Number> values = List.of(1, 2);
Number n = values.get(0); // Nắm tham chiếu đến đối tượng Integer.
```

Từ `Number` ở biến `n` không suy ra đối tượng đã biến thành một instance khác. **Kiểu tĩnh** và **class runtime** là hai khái niệm khác nhau.

### 14.5. Không nên dùng raw type và unchecked cast

```java
List<Integer> integers = List.of(1, 2);
// List<Number> unsafe = (List<Number>) (List<?>) integers;
```

Ép kiểu không kiểm tra có thể vượt qua lỗi compile-time nhưng phá hợp đồng kiểu, đặc biệt khi các phần tử mới được thêm qua tham chiếu `List<Number>`. Nếu cần chuyển một danh sách đã có kiểu, ưu tiên wildcard chỉ đọc hoặc tạo danh sách mới phù hợp.

## 15. Tương tác giữa type inference và overload resolution

Với nhiều phương thức trùng tên, compiler còn phải chọn overload phù hợp. Ngữ cảnh kiểu và suy luận có quan hệ qua lại, nhưng **không nên dự đoán overload chỉ từ kiểu bên trái**.

Ví dụ hai overload có thể phân biệt thật sự ở số tham số:

```java
static void log(String text) {
    System.out.println(text);
}

static void log(String text, int count) {
    System.out.println(text + ":" + count);
}
```

Ở đây overload được xác định đơn giản theo danh sách đối số. Nhưng nếu nhiều overload nhận functional interface hoặc generic type, lambda, method reference và inference có thể tạo ràng buộc phức tạp hoặc ambiguity.

Đặc biệt, không thể khai báo hai overload chỉ khác nhau bởi đối số generic sau erasure:

```java
// static void consume(List<Integer> values) {}
// static void consume(List<Number> values) {}
```

Hai chữ ký có cùng erasure là `consume(List)`; Java báo name clash. Target typing không vượt qua giới hạn của type erasure.

Khi gặp overload mơ hồ, thay vì đoán rằng compiler nhìn kiểu biến kết quả rồi chọn “đúng”, nên xem từng chữ ký, quy tắc applicability và most-specific, hoặc dùng kiểu tường minh/type witness có cơ sở.

## 16. Target typing với nested generics

Ngữ cảnh có thể giúp suy luận qua nhiều tầng generic:

```java
List<List<Number>> matrix = List.of(
    List.of(1, 2),
    List.of(3.5, 4.5)
);
```

Vế trái yêu cầu `List<List<Number>>`; các biểu thức `List.of` bên trong được kiểm tra trong ngữ cảnh tương ứng để xây cấu trúc phù hợp.

Đối chiếu:

```java
List<List<Integer>> matrixOfIntegers =
        List.of(List.of(1, 2));

// List<List<Number>> invalid = matrixOfIntegers; // Lỗi.
```

Một biến `List<List<Integer>>` đã có kiểu tĩnh cụ thể. Nó không tự động tương thích `List<List<Number>>` chỉ vì `Integer <: Number`, bởi invariance tồn tại ở từng cấp generic.

Nếu chỉ đọc:

```java
List<? extends List<? extends Number>> view = matrixOfIntegers;
Number first = view.get(0).get(0);
```

Đây là cách dùng wildcard ở **đúng các cấp** cần biến thiên khi không tạo bản sao. Còn khi đang gọi generic factory mới trong một target type, compiler có thể suy luận type argument ngay từ đầu.

## 17. Type witness, target type và thiết kế API

### 17.1. Khi API viết tốt, caller ít phải can thiệp

Một generic factory:

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
```

cho phép:

```java
List<Number> a = singleton(1);
List<Integer> b = singleton(1);
List<Object> c = singleton(1);
```

Caller được chọn kiểu đích hợp lệ phù hợp yêu cầu sử dụng.

### 17.2. Khi API cần cố định quan hệ giữa nguồn và đích

Ví dụ:

```java
static <T> List<T> copyOf(Iterable<? extends T> source) {
    List<T> result = new ArrayList<>();
    for (T item : source) {
        result.add(item);
    }
    return result;
}
```

Lời gọi:

```java
List<Integer> ints = List.of(1, 2);
List<Number> nums = copyOf(ints);
```

Compiler phối hợp cận `? extends T` của nguồn với target `List<Number>` của kết quả. Việc trả **bản sao mới** cho phép chọn một `List<Number>` thực sự, trong khi phương thức vẫn nhận nguồn `Iterable<Integer>`.

Nếu API chỉ trả lại chính reference `List<Integer>` dưới kiểu `List<Number>`, điều đó sẽ không an toàn. Thiết kế generic không được đánh tráo hành vi copy với alias.

### 17.3. Khi muốn định kiểu không lệ thuộc ngữ cảnh, nêu rõ đối số

```java
var numbers = List.<Number>of(1, 2.5);
var sink = new ArrayList<Number>();
```

Dù dùng `var`, initializer ở ví dụ này đã nêu rõ `Number`, nên kiểu được suy luận cho biến tương ứng có type argument `Number`.

Dùng khai báo như vậy khi kiểu rộng có ý nghĩa đối với API, thay vì trông chờ compiler đọc ý định từ tên biến.

## 18. Bảng đối chiếu nhanh

| Tình huống | Có thông tin kiểu đích hữu ích? | Kết quả cần nhớ |
| --- | --- | --- |
| `List<Number> x = List.of(1)` | Có, từ phép gán | Có thể suy luận `E = Number` |
| `acceptNumbers(List.of(1))` | Có, từ tham số `List<Number>` | Lời gọi generic lồng bên trong tương thích |
| `return List.of(1)` trong hàm trả `List<Number>` | Có, từ kiểu trả về khai báo | Biểu thức generic được kiểm tra theo `List<Number>` |
| `var x = List.of(1)` | Không có `List<Number>` tường minh | `x` được suy luận là `List<Integer>` |
| `List<Number> x = new ArrayList<>()` | Có, cho diamond | Suy luận `ArrayList<Number>` |
| `var x = new ArrayList<>()` | Không có kiểu đích `Number` | Suy luận `ArrayList<Object>` khi không có ràng buộc khác |
| `Function<String,Integer> f = s -> s.length()` | Có, functional interface | `s` có kiểu `String` |
| `var f = s -> s.length()` | Không | Lỗi: lambda cần target functional interface |
| `Supplier<List<String>> f = Collections::emptyList` | Có | Method reference được định kiểu phù hợp |
| `var f = String::length` | Không | Lỗi: method reference cần target |
| `List<Number> y = existingListOfInteger` | Có target nhưng source cố định | Lỗi invariance |
| `List<Number> y = new ArrayList<>(existingListOfInteger)` | Có và tạo bản sao mới | Hợp lệ |

Các kết quả trong bảng dựa trên JDK 17 và các import hợp lệ, với tên biến/phương thức đã được định nghĩa đúng kiểu.

## 19. Lỗi thường gặp và cách tự chẩn đoán

### Lỗi A — Nhầm “suy luận” với “ép kiểu”

Lời gọi generic factory có thể chọn `T = Number` từ đầu. Đó là suy luận **khi biểu thức được kiểm tra**, không phải một ép kiểu `List<Integer>` sang `List<Number>` sau khi kiểu đã được xác định.

### Lỗi B — Tin rằng `var` luôn chọn “kiểu tốt nhất”

`var` suy luận dựa trên initializer và không tự biết rằng business logic muốn `List<Number>`. Nếu chương trình sau này cần kiểu đích rộng, hãy thể hiện ý định bằng khai báo hoặc type witness.

### Lỗi C — Đổi `? extends T` thành `List<T>` tùy tiện

Nếu phương thức nhận tham chiếu `List<Integer>` thực sự, chuyển nó thành `List<Number>` bằng ép kiểu là không an toàn. Dùng wildcard cho view đọc, hoặc tạo bản sao theo kiểu rộng.

### Lỗi D — Cho rằng mọi biểu thức dùng `?:` hay method call đều là poly expression

Quy tắc Java có điều kiện cụ thể. Chỉ một số dạng generic method invocation, reference conditional expression, lambda, method reference, diamond… dùng target typing theo cách mô tả. Đừng suy luận rằng phép gán có thể biến đổi kiểu tĩnh của bất kỳ biểu thức nào.

### Lỗi E — Quên boxing/unboxing

Primitive `int` không phải subtype của `Number`. Nhưng `1` có thể boxing thành `Integer`, sau đó `Integer <: Number`. Khi đọc lỗi generic từ literal primitive, hãy tính đến boxing conversion.

### Lỗi F — Lẫn kết quả suy luận với khả năng sửa collection

`List<Number> list = List.of(1,2)` hợp lệ, nhưng `list.add(3.5)` vẫn ném `UnsupportedOperationException`. Muốn thêm phần tử thật, dùng implementation mutable như `ArrayList`.

## 20. Bài tập tự kiểm tra

### Bài 1 — Dự đoán đúng/sai

```java
static <T> List<T> box(T item) {
    return List.of(item);
}

static void takeNumbers(List<Number> values) {}

List<Number> a = box(1); // (1)
takeNumbers(box(2));     // (2)
List<Integer> b = box(3);
// takeNumbers(b);       // (3)
```

**Đáp án:** (1) đúng nhờ target `List<Number>`; (2) đúng nhờ ngữ cảnh truyền đối số `List<Number>`; (3) sai vì biến `b` đã có kiểu `List<Integer>`, không phải `List<Number>`.

### Bài 2 — Kiểu của biến `var`

```java
var a = List.of(1, 2);
var b = new ArrayList<>();
List<Number> c = new ArrayList<>();
```

**Đáp án:** `a` là `List<Integer>` (vì các phần tử `Integer`); `b` là `ArrayList<Object>` khi không có ràng buộc khác; `c` có kiểu khai báo `List<Number>`, với diamond suy luận type argument của implementation theo target.

### Bài 3 — Target của `return`

```java
static List<CharSequence> load() {
    return List.of("A", "B");
}
```

**Đáp án:** Hợp lệ. `List.of` có thể suy luận type argument `CharSequence`, nhận các `String` là subtype của `CharSequence`. Nếu trả một **biến** đã khai báo `List<String>`, phép gán trực tiếp lại sai vì invariance.

### Bài 4 — Lambda và method reference

```java
Function<String, Integer> a = text -> text.length();
Function<String, Integer> b = String::length;
// var c = text -> text.length();
```

**Đáp án:** `a` và `b` hợp lệ vì có target functional interface; `c` sai vì `var` không cung cấp target type cần thiết cho lambda.

### Bài 5 — Khi nào nên dùng wildcard?

Một phương thức nhận danh sách `Integer` do caller đã tạo, nhưng chỉ cần đọc dưới dạng `Number`:

```java
static double sum(List<? extends Number> values) {
    double result = 0;
    for (Number number : values) {
        result += number.doubleValue();
    }
    return result;
}
```

**Đáp án:** `? extends Number` cho phép truyền `List<Integer>`, `List<Double>` hoặc `List<Number>`. Target typing của các **lời gọi factory** không thay thế được wildcard khi **biến nguồn đã có kiểu cụ thể**.

### Bài 6 — Đánh giá biểu thức `?:`

```java
boolean flag = false;
List<Number> values = flag ? List.of(1) : List.of(2.5);
```

**Đáp án:** Hợp lệ nhờ target type `List<Number>` trong ngữ cảnh gán của reference conditional expression; khi chạy, `flag = false` nên phần tử là `Double` có giá trị `2.5`. Không kết luận điều tương tự cho một biến đã có kiểu `List<Integer>` được đưa vào nhánh: kiểu tĩnh của biến không bị suy luận lại.

## 21. Quy trình phân tích khi compiler báo “incompatible types”

1. Xác định **toàn biểu thức** cần có kiểu gì và nguồn thông tin kiểu đích đến từ đâu: gán, truyền đối số, `return` hay target functional interface.
2. Kiểm tra biểu thức bên trong có thực sự thuộc loại dùng **target typing** hay không.
3. Nếu là generic method, tìm các type parameter `<T>`, kiểu đầu vào, kiểu trả về, bound và các ràng buộc cần đồng thời thỏa.
4. Nếu là constructor có `<>`, kiểm tra target type có giúp suy luận đối số kiểu không.
5. Nếu biến được khai báo bằng `var`, xác định kiểu initializer ngay tại khai báo; không giả định ý định từ tên biến.
6. Nếu nguồn đã là `List<Integer>` và đích cần `List<Number>`, xem lại invariance; cân nhắc `? extends Number` hoặc tạo bản sao.
7. Với lambda/method reference, kiểm tra functional interface ở ngữ cảnh đích, kiểu tham số và kiểu kết quả.
8. Nếu suy luận mơ hồ, thử khai báo type argument `<Number>` rõ ràng **khi hợp lệ**, hoặc đơn giản hóa biểu thức bằng biến trung gian có kiểu tường minh.
9. Sau khi biên dịch, đánh giá riêng các hợp đồng runtime: mutability, null, checked/unchecked exceptions.

## 22. Tài liệu tham khảo

- [Java Language Specification 17 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): suy luận trong lời gọi phương thức và applicability.
- [Java Language Specification 17 — §18 Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): ràng buộc, reduction và suy luận kiểu generic.
- [Java Language Specification 17 — §15.2 Poly Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.2): khái niệm poly expression và ngữ cảnh kiểu.
- [Java Language Specification 17 — §15.25 Conditional Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25): quy tắc kiểu của biểu thức điều kiện.
- [Java Language Specification 17 — §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambda và target functional interface.
- [Java Language Specification 17 — §15.13 Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): method reference và ngữ cảnh kiểu.
- [Java Language Specification 17 — §14.4 Local Variable Declaration Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): suy luận cho biến cục bộ dùng `var`.
- [Java Tutorials — Type Inference](https://docs.oracle.com/javase/tutorial/java/generics/genTypeInference.html): ví dụ tổng quan về type inference.

**Kết luận:** Kiểu đích là một nguồn ràng buộc giúp Java suy luận type arguments trong những biểu thức phù hợp, đặc biệt khi **gán kết quả lời gọi generic, truyền biểu thức generic làm đối số, hoặc trả về từ một phương thức có kiểu đã khai báo**. Nó không biến `List<Integer>` đang tồn tại thành `List<Number>`, không làm `var` tự biết kiểu nghiệp vụ cần dùng và không xóa bỏ kiểm tra an toàn của Generics.