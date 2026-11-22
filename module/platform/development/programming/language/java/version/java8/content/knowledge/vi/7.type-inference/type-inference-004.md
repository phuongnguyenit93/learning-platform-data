# Suy luận kiểu trong lời gọi phương thức generic (Java)

## Mục tiêu

**Suy luận kiểu trong lời gọi phương thức generic** (*generic method invocation type inference*) là quá trình compiler xác định **type arguments** cho các tham số kiểu như `<T>`, `<T,R>` khi gọi một generic method mà không cần viết tường minh `<String>` hoặc `<Integer>` ở nơi gọi. Đây là khả năng nền tảng của Java từ trước Java 8, được Java 8 mở rộng đáng kể để phối hợp với **target typing**, lambda, method reference và các lời gọi generic lồng nhau. Các quy tắc này **vẫn được sử dụng trong Java hiện đại**.

Sau bài này, bạn sẽ:

- Phân biệt **type parameter** được khai báo ở phương thức và **type argument** được suy luận/chỉ định tại lời gọi.
- Nhận ra nguồn ràng buộc cho suy luận: **kiểu đối số thực tế, giới hạn `extends`, kiểu đích**, các biểu thức lồng nhau và generic functional interface.
- Hiểu vì sao cùng một generic method có thể được suy luận khác nhau tùy ngữ cảnh.
- Dùng đúng cú pháp **explicit type witness**, như `MyClass.<String>method(...)`, khi compiler cần thêm thông tin hoặc bạn muốn nêu rõ ý định.
- Phân biệt suy luận kiểu tại **method invocation**, generic class/diamond và `var`.
- Chẩn đoán lỗi `incompatible types`, `cannot infer type-variable(s)`, `no suitable method found` và overload ambiguity mà không bỏ tính an toàn kiểu.
- Viết các ví dụ Java 17+ biên dịch/chạy độc lập và kiểm tra đúng kết quả.

## 1. Nhắc lại generic method: tham số kiểu nằm ở đâu?

Xem phương thức:

~~~java
static <T> T identity(T value) {
    return value;
}
~~~

Ở đây:

- `<T>` đứng **trước kiểu trả về** là khai báo một **type parameter** của phương thức.
- `T value` là tham số nhận dữ liệu kiểu `T`.
- `T` ở vị trí kiểu trả về nghĩa là kết quả có cùng kiểu `T` đã được quyết định cho lời gọi.
- `T` thuộc **phương thức**; class chứa nó không nhất thiết là generic class.

Khi gọi:

~~~java
String name = identity("Java");
Integer count = identity(42);
~~~

compiler có thể suy luận `T` là `String` ở lời gọi đầu và `Integer` ở lời gọi sau. Đối số nguyên thủy `42` được **boxing** thành `Integer` khi truyền vào tham số generic kiểu tham chiếu. Bạn **không** phải viết:

~~~java
String name = MyClass.<String>identity("Java");
Integer count = MyClass.<Integer>identity(42);
~~~

Dạng ghi tường minh có thể hợp lệ (khi class thực sự tên `MyClass`), nhưng thường không cần thiết.

### Type parameter, type argument và biến tham số

Ba khái niệm dễ nhầm:

| Thuật ngữ | Ví dụ | Vai trò |
| --- | --- | --- |
| **Type parameter** | `<T>` trong `static <T> T identity(T x)` | Biến đại diện một kiểu, được khai báo khi định nghĩa method |
| **Type argument** | `<String>` trong `MyClass.<String>identity("a")` | Kiểu cụ thể tại lời gọi, được chỉ định rõ |
| **Method argument** | `"a"` | Giá trị truyền cho tham số `x` |
| **Inferred type argument** | `T = String` trong `identity("a")` | Kiểu compiler giải ra từ các ràng buộc |

Suy luận generic là **cơ chế compile time**. Nó không biến Java thành ngôn ngữ dynamic typing; lỗi kiểu vẫn được phát hiện trước khi chạy.

## 2. Compiler lấy thông tin suy luận từ đâu?

Về mặt khái niệm, Java tạo **ràng buộc kiểu** từ những yếu tố sau:

1. **Đối số của lời gọi** và kiểu tham số trong method declaration.
2. **Giới hạn của type parameter**, ví dụ `<T extends Number>` hoặc `<T extends Comparable<? super T>>`.
3. **Kiểu đích (target type)** của *poly method invocation*, như vế trái phép gán hoặc kiểu tham số của một lời gọi ngoài.
4. **Lambda và method reference** truyền làm đối số: functional interface đích cung cấp chữ ký SAM để kiểm tra biểu thức.
5. **Lời gọi generic lồng nhau**, wildcard/capture conversion và các chuyển đổi Java cho phép, tùy ngữ cảnh.

Không nên coi đây là một luật đơn giản “compiler luôn lấy đúng kiểu của đối số đầu tiên”. Nếu nhiều ràng buộc cùng tác động, kiểu suy luận phải thỏa chúng, đôi khi là một **kiểu cha**, kiểu giao (*intersection type*) hoặc một kiểu liên quan đến wildcard. Cụ thể được xác định bằng JLS Chapter 18, không phải bằng cách đếm ký tự trong mã nguồn.

### Suy luận từ đối số

~~~java
static <T> T echo(T value) {
    return value;
}

String text = echo("hi");  // T tương thích với String
Integer num = echo(10);    // T tương thích với Integer
~~~

### Suy luận từ kiểu đích

~~~java
static <T> java.util.List<T> empty() {
    return java.util.Collections.emptyList();
}

java.util.List<String> names = empty();
java.util.List<Integer> ids = empty();
~~~

Phương thức `empty()` **không nhận đối số giá trị** nên không thể biết `T` từ danh sách tham số. Compiler vẫn có thể dùng target type `List<String>` hoặc `List<Integer>` để xác định `T` trong ngữ cảnh của một generic method invocation đủ điều kiện.

**Điều rất quan trọng:** thông tin target type không phải luôn dùng để quyết định **overload nào thắng**. Java tách nhiều giai đoạn của overload resolution (`15.12.2`) và inference (`18.5`). Khi có nhiều phương thức cùng tên, compiler trước hết xác định phương thức có thể áp dụng/cụ thể nhất theo các quy tắc liên quan; sau đó việc suy luận kiểu lời gọi có thể tiếp nhận thêm ràng buộc từ kiểu đích. Vì vậy đừng mặc định đổi kiểu biến nhận kết quả sẽ luôn ép compiler chọn một overload khác.

## 3. Generic method invocation là poly expression khi nào?

Một **poly expression** là biểu thức có kiểu được quyết định một phần theo ngữ cảnh sử dụng. Trong Java hiện đại, một lời gọi generic method có thể là poly expression khi đáp ứng những điều kiện mà JLS `15.12 quy định, ví dụ lời gọi nằm trong **assignment context** hoặc **invocation context**, phương thức được chọn có return type phụ thuộc vào type parameter và **không ghi explicit type arguments**.

Ví dụ dễ hiểu:

~~~java
java.util.List<String> a =
        java.util.Collections.emptyList();

java.util.List<Long> b =
        java.util.Collections.emptyList();
~~~

`Collections.emptyList()` có chữ ký:

~~~java
// Chữ ký API minh họa:
public static final <T> java.util.List<T> emptyList();
~~~

Hai lời gọi cùng không có đối số, nhưng kiểu đích khiến compiler suy luận `T` tương ứng `String` và `Long`.

Bạn cũng có thể chỉ rõ type arguments:

~~~java
java.util.List<String> a =
        java.util.Collections.<String>emptyList();
~~~

Khi có explicit type arguments `<String>`, compiler không cần suy luận `T` cho riêng lời gọi đó theo cùng cách như khi bỏ type witness; nó vẫn tiếp tục kiểm tra tính tương thích của kết quả.

### Không phải ngữ cảnh nào cũng có target type hữu ích

Nếu lời gọi đứng một mình ở vị trí không có kiểu đích đủ thông tin, compiler dùng những ràng buộc sẵn có và giới hạn kiểu:

~~~java
var unknown = java.util.Collections.emptyList();
~~~

Với `var` (biến cục bộ, Java 10+), không có `List<String>` ở vế trái để định hướng lời gọi; trong trường hợp này, kiểu `unknown` được suy luận là `List<Object>`. **`var` không phải cách viết tắt cho một target type mà compiler chưa hề được cung cấp.**

Điều tương tự xảy ra ở:

~~~java
var value = echo(null);
~~~

Lời gọi `echo(null)` không có đối số mang kiểu tham chiếu cụ thể; trong trường hợp không có ràng buộc khác, compiler có thể dùng `Object` làm kiểu suy luận. Giá trị runtime vẫn là `null`, nhưng kiểu tĩnh của biến có thể rộng hơn mong muốn.

Để nêu rõ ý định:

~~~java
String nullable = echo(null);
java.util.List<String> typedEmpty =
        java.util.Collections.emptyList();
~~~

**Không nên dựa vào việc một kết quả được dùng ở dòng code sau đó để yêu cầu compiler “suy luận ngược” qua các biến đã khai báo.** Type inference phân tích các ràng buộc trong biểu thức/ngữ cảnh hiện tại; nó không tự tái định kiểu một biến vì các dòng tiếp theo cần kiểu khác.

## 4. Khi một phương thức có nhiều tham số cùng T

Xét:

~~~java
static <T> T first(T left, T right) {
    return left;
}
~~~

Với hai chuỗi:

~~~java
String result = first("A", "B");  // "A"
~~~

Cả hai đối số phù hợp `String`. Nếu gọi với các kiểu khác nhau:

~~~java
Number result = first(10, 2.5);
~~~

`10` được boxing thành `Integer`; `2.5` thành `Double`. Compiler tìm một kiểu `T` đáp ứng các ràng buộc từ đối số và kiểu đích `Number`. Giá trị trả về vẫn là đối số đầu (`Integer 10`), nhưng biến `result` có **kiểu tĩnh `Number`**.

Cách nghĩ sai:

> “Phương thức `first` thấy đối số đầu là `Integer`, nên mọi đối số còn lại cũng phải là `Integer`.”

Với generic method `<T> T first(T,T)`, **không có** điều kiện “hai đối số phải cùng runtime class”. Có thể chọn một supertype chung khi các ràng buộc cho phép. Ngược lại, nếu **nghiệp vụ** yêu cầu hai đầu vào đúng cùng loại cụ thể, một generic parameter chưa chắc tự cưỡng chế điều đó; cần thiết kế API/hợp đồng phù hợp.

### Least upper bound không phải luôn một class đơn giản

Khi kết hợp nhiều kiểu không liên quan trực tiếp, Java có thể suy ra một **least upper bound** biểu diễn qua supertype, wildcard và/hoặc intersection type. Đừng khẳng định không kiểm chứng rằng `var result = first(1, "x")` có đúng kiểu `Object` trong mọi trình biên dịch/ngữ cảnh — kiểu compile time có thể phức tạp hơn.

Với code ứng dụng, cách thường dễ đọc và ổn định là **chọn kiểu đích có ý nghĩa**, chẳng hạn:

~~~java
Object mixed = first(1, "x");
~~~

Điều này **không có nghĩa** mọi kết hợp dữ liệu hỗn hợp là thiết kế tốt: kiểu quá rộng có thể làm giảm khả năng kiểm tra lỗi ở các bước tiếp theo.

## 5. Giới hạn trên của tham số kiểu (type bounds)

Một generic method có thể giới hạn `T`:

~~~java
static <T extends Number> double doubleValue(T number) {
    return number.doubleValue();
}
~~~

Ở lời gọi:

~~~java
double a = doubleValue(12);   // Integer -> Number
double b = doubleValue(2.5);  // Double -> Number
~~~

compiler suy luận tham số kiểu sao cho vừa tương thích đối số vừa thỏa `T extends Number`. Bạn **không** thể truyền `String` chỉ vì nó có `toString()`; `String` không là subtype của `Number`:

~~~java
// Không biên dịch:
// doubleValue("12");
~~~

Ví dụ bound phức tạp nhưng thực tế:

~~~java
static <T extends Comparable<? super T>> T greater(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

Gọi:

~~~java
Integer max = greater(7, 9); // 9
String later = greater("a", "b"); // "b"
~~~

`Comparable<? super T>` cho phép phương thức so sánh với `T` hoặc một kiểu cha phù hợp, thường linh hoạt hơn `Comparable<T>` trong các cây kế thừa. Đây là idiom vẫn được sử dụng trong các API Java hiện đại.

**Không được chỉ định kiểu vi phạm bound**:

~~~java
// Không hợp lệ: String không mở rộng Number.
// double x = MyClass.<String>doubleValue("12");
~~~

Explicit type witness không phải cách vượt qua type bounds.

## 6. Explicit type witness: khi muốn tự chỉ định type arguments

Cú pháp gọi **static generic method**:

~~~java
ClassName.<ConcreteType>genericMethod(arguments);
~~~

Ví dụ khi phương thức nằm trong class `Example`:

~~~java
Example.<String>identity("Java");
~~~

Nếu lời gọi nằm trong chính class đó, có thể dùng dạng tên phương thức generic có type arguments đúng cú pháp:

~~~java
Example.<String>identity("Java");
~~~

Với một **instance generic method**, có thể viết:

~~~java
object.<String>genericMethod(arguments);
~~~

Phân biệt với:

~~~java
// Đây là generic method invocation:
Example.<String>identity("Java");

// Đây là generic type/constructor instantiation, không cùng cú pháp:
// new java.util.ArrayList<String>();
// new java.util.ArrayList<>();
~~~

**Nên chỉ định tường minh khi:**
- Target type chưa được suy ra đúng ý định, ví dụ muốn giá trị `List<String>` từ một factory generic không có đối số.
- Một lời gọi generic lồng nhau gây lỗi inference hoặc thông điệp compiler khó hiểu.
- Bạn muốn truyền một **kiểu cụ thể theo hợp đồng API** để tránh người đọc suy đoán.
- Cần làm rõ ràng buộc giữa hai lời gọi generic.

**Không cần chỉ định tường minh khi** compiler đã suy luận chính xác và một type witness chỉ làm code rườm rà.

Một lỗi cú pháp:

~~~java
// Không hợp lệ: type arguments của lời gọi nằm sau dấu chấm,
// không thay thế kiểu đối số giá trị:
// Example.identity<String>("Java");
~~~

Đúng là `Example.<String>identity("Java")`. Nếu class là generic class, cần tiếp tục phân biệt type parameters của class và type parameters của chính method.

## 7. Suy luận với phương thức trả về List<T>

Giả sử:

~~~java
static <T> java.util.List<T> singleton(T element) {
    return java.util.Collections.singletonList(element);
}
~~~

Gọi:

~~~java
java.util.List<String> names = singleton("Lan");
java.util.List<Integer> ids = singleton(7);
~~~

`T` được xác định từ cả đối số và kiểu đích phù hợp. Đây vẫn là một generic method **duy nhất**, chứ không phải compiler sinh nhiều overload từ cùng một method declaration.

### Generic factory không có đối số: target type trở nên quan trọng hơn

~~~java
static <T> java.util.List<T> empty() {
    return java.util.Collections.emptyList();
}

java.util.List<String> words = empty();
java.util.List<Integer> codes = empty();
~~~

Nếu viết:

~~~java
var emptyValues = empty();
~~~

Java 10+ không có kiểu đích phần tử cụ thể nên thường suy luận `T` là `Object` trong trường hợp method đơn giản này. Khi sau đó bạn mong chờ `List<String>`, kiểu tĩnh `List<Object>` không thể gán trực tiếp vì generic Java **invariant**:

~~~java
// Không biên dịch nếu emptyValues đã là List<Object>:
// java.util.List<String> names = emptyValues;
~~~

Cách đúng: khai báo kiểu ngay tại nơi gọi `List<String> names = empty()`, hoặc gọi `Example.<String>empty()` nếu cần type witness.

### Trả về rỗng không có nghĩa không cần type safety

Một `List<Object>` rỗng vẫn **khác kiểu** `List<String>` trong hệ thống kiểu Java. Java không cho phép ép kiểu generic một cách tùy tiện chỉ vì runtime collection đang rỗng. Đây là nguyên nhân phổ biến khi suy luận với factory không có input.

## 8. Lời gọi generic lồng nhau (nested invocations)

Từ Java 8, compiler có khả năng phối hợp ràng buộc ở các biểu thức generic lồng nhau theo target typing. Ví dụ phổ biến:

~~~java
static <T> java.util.List<T> empty() {
    return java.util.Collections.emptyList();
}

static <T> java.util.List<T> copy(
        java.util.Collection<? extends T> source) {
    return new java.util.ArrayList<>(source);
}

java.util.List<String> names = copy(empty());
~~~

Kiểu đích của `copy(empty())` và thông tin từ tham số `copy` tạo các ràng buộc phối hợp; trong ngữ cảnh này, compiler có thể chọn `String` cho type arguments phù hợp.

Bạn không cần tách mọi lời gọi:

~~~java
java.util.List<String> source = empty();
java.util.List<String> names = copy(source);
~~~

Nhưng **việc tách biến tường minh vẫn là một kỹ thuật debug tốt** khi inference phức tạp, nhất là khi lỗi được báo ở một biểu thức lồng nhau dài.

### Inference diễn ra theo các pha

Nói ngắn gọn theo JLS:
- Java đánh giá **ứng viên phương thức có thể áp dụng** (*invocation applicability inference*).
- Sau khi xác định phương thức được chọn, compiler thực hiện các ràng buộc liên quan đến **kiểu lời gọi** (*invocation type inference*), bao gồm sự phù hợp với target type khi biểu thức là poly expression.
- Trong các lời gọi lồng nhau, compiler có thể tiếp tục giải các ràng buộc giữa nhiều type variables theo quy tắc JLS `18.

Không nên tưởng tượng một thuật toán “cứ đi từ trái sang phải suy luận xong hết từng lời gọi” rồi coi đó là quy tắc chắc chắn; trường hợp poly expressions đòi hỏi phép kiểm tra phối hợp.

## 9. Generic method với nhiều type parameters: T và R

Ví dụ rất thực dụng:

~~~java
static <T, R> java.util.List<R> transform(
        java.util.List<T> values,
        java.util.function.Function<? super T, ? extends R> mapper) {

    java.util.List<R> result = new java.util.ArrayList<>();
    for (T value : values) {
        result.add(mapper.apply(value));
    }
    return result;
}
~~~

Trong chữ ký này:
- `T` là kiểu phần tử đầu vào.
- `R` là kiểu kết quả sau ánh xạ.
- `Function<? super T, ? extends R>` cho phép callback nhận `T` hoặc supertype thích hợp và trả `R` hoặc subtype thích hợp.
- `List<R>` bảo đảm kết quả của phép biến đổi là danh sách có element type `R`.

Gọi:

~~~java
java.util.List<Integer> lengths =
        transform(java.util.List.of("go", "java"),
                  String::length);

// lengths == [2, 4]
~~~

Compiler suy luận `T` liên quan `String` từ `List<String>`, và `R` liên quan `Integer` từ method reference `String::length` cùng target `List<Integer>` (có boxing). Đây là ví dụ **giao nhau** giữa generic method invocation inference, target typing, method reference và wildcard.

Một lời gọi khác:

~~~java
java.util.List<Integer> numbers =
        transform(java.util.List.of("7", "12"),
                  Integer::parseInt);

// numbers == [7, 12]
~~~

Hai type arguments `T` và `R` được suy luận khi gọi, không cần `transform<String,Integer>(...)`. Nếu muốn ghi tường minh cho mục đích giải thích, cú pháp là `Example.<String,Integer>transform(...)` khi `Example` là class chứa method.

### Vì sao dùng <? super T, ? extends R>?

Đây là lựa chọn linh hoạt thường thấy trong các API `java.util.function`:

- Input của một `Function` có thể là **supertype** của `T` (hàm nhận `Object` vẫn xử lý được `String`).
- Output có thể là **subtype** của `R` (hàm trả `Integer` vẫn dùng được khi kết quả được yêu cầu là `Number`).

Tuy nhiên, wildcard làm inference phức tạp hơn. Đọc Javadoc và tập trung vào **hợp đồng ai tiêu thụ / ai sản sinh dữ liệu** thay vì xóa wildcard hoặc đổi sang raw type cho compiler im lặng.

## 10. Suy luận qua lambda và target typing

Với lời gọi `transform`:

~~~java
java.util.List<String> upper =
        transform(java.util.List.of("a", "b"),
                  text -> text.toUpperCase(java.util.Locale.ROOT));
~~~

Lambda `text -> ...` không nêu kiểu tham số; compiler biết nó phải phù hợp với `Function<? super T, ? extends R>` trong ngữ cảnh gọi `transform`, nên suy luận để kiểu `text` tương thích `String`.

Viết tường minh cũng được:

~~~java
java.util.List<String> upper =
        transform(java.util.List.of("a", "b"),
                  (String text) ->
                          text.toUpperCase(java.util.Locale.ROOT));
~~~

**Không phải mọi lambda đều có thể tự mang kiểu nếu không có functional interface mục tiêu.** Ví dụ sau không hợp lệ:

~~~java
// Không có target functional interface:
// var mapper = text -> text.length();
~~~

Hãy viết:

~~~java
java.util.function.Function<String, Integer> mapper =
        text -> text.length();
~~~

Rồi:

~~~java
java.util.List<Integer> sizes =
        transform(java.util.List.of("go", "java"), mapper);
~~~

Đây là một kỹ thuật chẩn đoán hữu ích: nếu suy luận trong một lời gọi dài không rõ, **khai báo callback với functional interface typed trước** rồi truyền biến ấy vào generic method.

## 11. Suy luận qua method reference

Method reference cũng cần target functional interface:

~~~java
java.util.List<Integer> lengths =
        transform(java.util.List.of("cat", "dog"),
                  String::length);
~~~

`String::length` là **unbound instance method reference**: receiver `String` được cung cấp như đối số của SAM. Nó trả về primitive `int`, compiler boxing nếu cần để phù hợp `Integer`.

Với static method reference:

~~~java
java.util.List<Integer> parsed =
        transform(java.util.List.of("1", "20"),
                  Integer::parseInt);
~~~

`Integer::parseInt` có overload; compiler dùng functional interface target và ràng buộc đối số để tìm overload tương thích (`parseInt(String)` trong trường hợp này).

### Khi overload vẫn mơ hồ

Nếu API bạn gọi **cũng overload theo các functional interfaces khác nhau**, compiler đôi khi không thể chọn một phương thức nhận callback duy nhất. Việc thêm một type witness cho một generic method không phải phép màu giải quyết mọi overload ambiguity. Trong thực tế:

1. Xác định overload nào nhận callback mà bạn muốn gọi.
2. Khai báo biến functional interface có kiểu rõ (như `Function<String,Integer> parser = Integer::parseInt`).
3. Truyền biến typed vào lời gọi.
4. Nếu phù hợp, cast method reference sang functional interface tương ứng hoặc viết lambda có kiểu tham số tường minh.

Cần phân biệt **suy luận type arguments của generic method** với **overload resolution của method invocation**. Hai cơ chế có liên quan nhưng không đồng nhất.

## 12. Java 17+ và var: không phải lúc nào cũng giúp inference

`var` được thêm vào Java 10 cho biến cục bộ. Nó khiến compiler suy ra **kiểu của biến** từ biểu thức khởi tạo, nhưng **không cung cấp trước một kiểu đích cụ thể** cho generic invocation giống như `List<String> names = ...`.

So sánh:

~~~java
java.util.List<String> explicit =
        java.util.Collections.emptyList();

var inferred =
        java.util.Collections.emptyList();
~~~

`explicit` có kiểu tĩnh `List<String>`; `inferred` là `List<Object>` trong ví dụ này. Cả hai đều chỉ chứa danh sách rỗng lúc chạy, nhưng **không tương đương về kiểu tĩnh**.

Một ví dụ `var` khác có đủ thông tin:

~~~java
var names = java.util.Collections.singletonList("Lan");
~~~

Compiler có thể suy luận `names` là `List<String>` vì `singletonList` nhận một đối số kiểu `String`.

**Kết luận:** dùng `var` khi biểu thức khởi tạo đã diễn đạt kiểu rõ ràng và không làm mất thông tin mà API cần. Với generic factory không có tham số hoặc lời gọi có ràng buộc target type quan trọng, khai báo kiểu tường minh thường tốt hơn.

### Chú ý diamond không phải suy luận của method invocation

Hai mã sau nói về hai cơ chế liên quan nhưng khác nhau:

~~~java
// Generic method invocation inference:
java.util.List<String> a =
        java.util.Collections.emptyList();

// Diamond inference cho generic class constructor:
java.util.List<String> b =
        new java.util.ArrayList<>();
~~~

`<>` được dùng để suy luận **type arguments của generic class ở constructor invocation**, không phải cách viết type witness cho generic method. Để chỉ định type argument tường minh khi gọi method, dùng `ClassName.<String>method()` — không phải `ClassName.<>method()`.

## 13. Boxing, primitive và generic type arguments

Type arguments của Java generics là **reference types**, không phải primitive types:

~~~java
static <T> T echo(T value) {
    return value;
}

Integer boxed = echo(12); // boxing từ int sang Integer
~~~

Bạn **không** thể viết:

~~~java
// Không hợp lệ: primitive int không thể làm type argument.
// Integer wrong = MyClass.<int>echo(12);
~~~

Thay bằng `<Integer>` nếu cần explicit witness. Khi tính toán nhiều số nguyên thủy, cân nhắc các functional interfaces đặc biệt như `IntUnaryOperator` hoặc primitive streams (`IntStream`) để hạn chế boxing, nhưng điều đó không thay đổi quy tắc type inference cho generic method.

### Chú ý hiệu ứng của null

~~~java
static <T> T echo(T value) {
    return value;
}

String value = echo(null); // Hợp lệ: value bằng null.
~~~

Không có nghĩa compiler “biết” kiểu runtime của `null`. Nó kết hợp null literal, type bounds và target type để chọn type arguments phù hợp. Nếu bạn gọi một phương thức overload với đối số `null`, có thể còn phát sinh **overload ambiguity** giữa các overload không có quan hệ subtype. Đó là vấn đề riêng mà bạn không nên tự động chữa bằng raw cast.

## 14. Wildcard capture và lời gọi generic

Xem:

~~~java
static <T> T head(java.util.List<T> values) {
    return values.get(0);
}
~~~

Giả sử:

~~~java
java.util.List<? extends Number> numbers =
        java.util.List.of(1, 2, 3);

Number first = head(numbers);
~~~

Java dùng **capture conversion** cho wildcard `? extends Number`, tạo một kiểu capture có upper bound thích hợp để gọi generic method. Vì thế `head(numbers)` có thể cung cấp một giá trị gán được vào `Number`.

Tuy nhiên, nếu một method **thêm** phần tử vào `List<T>`, `List<? extends Number>` không cho phép thêm tùy ý một `Integer` hoặc `Double` vì kiểu phần tử cụ thể có thể là một subtype khác của `Number`. **Suy luận kiểu không loại bỏ ràng buộc an toàn của wildcard**.

Ví dụ:

~~~java
// Không được tự ý ghi vào list với phần tử chưa biết chính xác:
// numbers.add(1);
~~~

Trong ứng dụng, nhiều lỗi `capture of ?` xuất hiện do API làm việc với wildcard quá phức tạp. Hãy cân nhắc **helper method generic**, chuyển API sang đọc dữ liệu immutable, hoặc khai báo `? super T` / `? extends T` phù hợp theo vai trò tiêu thụ/sản sinh. Đừng dùng raw `List` hoặc unchecked cast như cách sửa mặc định.

## 15. Overload resolution: mối quan hệ với type inference

Giả sử:

~~~java
static String describe(Object value) {
    return "object";
}

static String describe(String value) {
    return "string";
}
~~~

Gọi `describe("hi")` thường chọn overload `describe(String)` vì cụ thể hơn theo quy tắc overload; việc vế trái là `String s` không tự làm thay đổi bản chất lựa chọn này.

Với **generic overloads**, compiler cần kiểm tra nhiều ràng buộc hơn:

- Có bao nhiêu overload có tên và arity tương ứng?
- Đối số truyền vào có tương thích với formal parameters không?
- Type bounds của generic methods có cho phép một candidate không?
- Phương thức nào *most specific* theo JLS?
- Kiểu trả về của phương thức đã chọn có tương thích target type không?

**Đừng suy luận overload chỉ bằng kiểu trả về mong muốn.** Trong Java, không thể khai báo hai phương thức trùng chữ ký chỉ khác return type; và việc thay đổi kiểu biến nhận kết quả không phải một cơ chế chọn overload tổng quát.

Nếu generic method dùng type inference trong kết hợp overload phức tạp, hãy **tách lời gọi thành biến trung gian có kiểu rõ**, hoặc **type witness** khi thực sự liên quan type parameters của method. Nếu đó là overload giữa functional interfaces, viết callback typed hoặc cast sang interface phù hợp.

## 16. Những lỗi thường gặp

| Lỗi/ngộ nhận | Giải thích và cách khắc phục |
| --- | --- |
| “`T` luôn bằng kiểu của đối số đầu tiên.” | Không; compiler phải giải **tất cả ràng buộc**, có thể chọn một supertype/kiểu phức hợp. |
| “Không có đối số thì không thể suy luận type argument.” | Với poly expression, **target type** có thể cung cấp ràng buộc, như `List<String> x = Collections.emptyList()`. |
| “`var` và khai báo `List<String>` tương đương.” | Không; `var` không cung cấp target type phần tử trước cho generic factory không đối số. |
| “Có thể truyền primitive làm type argument.” | Không; `<int>` không hợp lệ, dùng `Integer` hoặc primitive-specific APIs. |
| “`List<Integer>` là subtype của `List<Number>`.” | Không; generic Java invariant. Có thể dùng wildcard phù hợp. |
| “Type witness bỏ qua `extends` bounds.” | Không; explicit type arguments vẫn phải đáp ứng tất cả bounds. |
| “Type witness luôn sửa được method overload ambiguity.” | Không; cần phân biệt method inference với overload của chính lời gọi/functional interface. |
| “Generic inference xử lý luôn hợp đồng nghiệp vụ.” | Không; nó chỉ bảo đảm kiểu, không đảm bảo thuật toán đúng, xử lý null hay side effect. |
| “Bỏ generic dùng raw type là giải pháp tốt.” | Raw type làm mất type safety, có thể tạo unchecked warnings và lỗi runtime. |
| “`<>` sau dấu chấm là cách gọi generic method.” | Sai; generic method invocation dùng `ClassName.<T>method()`, diamond dùng với constructor. |
| “Compiler đọc được ý định ở dòng sau.” | Không; cần target type và các ràng buộc của biểu thức hiện tại. |
| “Tăng phiên bản Java làm mọi inference cũ giữ đúng y nguyên.” | Khi đổi baseline/compiler hoặc đổi overload của API, nên compile/test lại; không dựa vào các trường hợp góc cạnh chưa được xác nhận. |

## 17. Chương trình Java 17+ đầy đủ: nhiều nguồn suy luận trong một ví dụ

Tạo tệp **`GenericInvocationInferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class GenericInvocationInferenceDemo {

    static <T> T identity(T value) {
        return value;
    }

    static <T> T first(T left, T right) {
        return left;
    }

    static <T> List<T> empty() {
        return Collections.emptyList();
    }

    static <T extends Comparable<? super T>> T greater(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T, R> List<R> transform(
            List<T> source,
            Function<? super T, ? extends R> mapper) {

        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    static <T> List<T> merge(
            List<? extends T> first,
            List<? extends T> second) {

        List<T> result = new ArrayList<>();
        result.addAll(first);
        result.addAll(second);
        return result;
    }

    public static void main(String[] args) {
        String language = identity("Java");
        Integer count = identity(42);
        String nullable = identity(null);

        System.out.println("language=" + language);
        System.out.println("count=" + count);
        System.out.println("nullable=" + (nullable == null));

        List<String> names = empty();
        List<Integer> numbers = empty();
        var noTarget = Collections.emptyList();

        System.out.println("empty-names=" + names.size());
        System.out.println("empty-numbers=" + numbers.size());
        System.out.println("var-empty=" + noTarget.size());

        List<String> words = List.of("go", "java", "lambda");
        List<Integer> lengths = transform(words, String::length);
        List<Integer> parsed = transform(
                List.of("7", "12"), Integer::parseInt);

        List<String> upper = transform(
                List.of("a", "b"),
                value -> value.toUpperCase(Locale.ROOT));

        System.out.println("lengths=" + lengths);
        System.out.println("parsed=" + parsed);
        System.out.println("upper=" + upper);

        Integer larger = greater(7, 9);
        Number mixed = first(10, 2.5);

        System.out.println("greater=" + larger);
        System.out.println("mixed-first=" + mixed);

        List<Number> joined = merge(
                List.of(1, 2),
                List.of(3.5));

        System.out.println("joined=" + joined);

        List<String> explicit = 
                GenericInvocationInferenceDemo.<String>empty();
        System.out.println("explicit-empty=" + explicit.size());

        Function<String, String> echo =
                GenericInvocationInferenceDemo::identity;
        System.out.println("echo=" + echo.apply("typed"));
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac --release 17 GenericInvocationInferenceDemo.java
java GenericInvocationInferenceDemo
~~~

**Stdout dự kiến chính xác**:

~~~text
language=Java
count=42
nullable=true
empty-names=0
empty-numbers=0
var-empty=0
lengths=[2, 4, 6]
parsed=[7, 12]
upper=[A, B]
greater=9
mixed-first=10
joined=[1, 2, 3.5]
explicit-empty=0
echo=typed
~~~

### Giải thích mấu chốt

1. `identity("Java")` và `identity(42)` suy luận `T` từ đối số và ngữ cảnh; `42` được boxing thành `Integer`.
2. `identity(null)` được gán cho `String`; dù biểu thức null không cho kiểu cụ thể, target type giúp compiler xác định invocation type phù hợp.
3. `empty()` không có đối số; `List<String>` và `List<Integer>` ở vế trái đóng vai trò target types.
4. `var noTarget = Collections.emptyList()` không có target element type nên `List<Object>` là kiểu của biến trong tình huống này.
5. `transform(words, String::length)` suy luận đầu vào `String` và kết quả `Integer` qua method reference, boxing và target `List<Integer>`.
6. `transform(List.of("7","12"), Integer::parseInt)` kết hợp lời gọi factory generic, inference của `transform` và static method reference.
7. `greater(7,9)` thỏa bound `Comparable<? super T>` và trả `9`.
8. `first(10,2.5)` cho phép một `T` chung thỏa ràng buộc `Number`, nhưng giá trị trả về là đối số đầu `10`.
9. `merge(List.of(1,2),List.of(3.5))` sử dụng wildcard `? extends T` và target `List<Number>` để tạo danh sách có thể chứa các dạng `Number`.
10. `GenericInvocationInferenceDemo.<String>empty()` minh họa **explicit type witness**; method reference tới `identity` cũng dựa trên target `Function<String,String>`.

`List.of(...)` được giới thiệu trong Java 9 và `var` từ Java 10; ví dụ chọn **JDK 17+**. Nguyên tắc generic method inference cốt lõi và lambda/method reference được hỗ trợ từ Java 8. Nếu cần chạy `--release 8`, thay `List.of(...)` bằng cách tạo collection tương thích và bỏ `var`; không dùng API mới trên runtime cũ.

## 18. Bài tập có lời giải gợi ý

### Bài 1 — Suy luận đơn giản

~~~java
static <T> T twiceSeen(T a, T b) {
    return b;
}

String value = twiceSeen("A", "B");
~~~

**Câu hỏi:** `T` được suy luận thế nào và giá trị `value` là gì?

**Đáp án:** hai đối số cùng là `String`, target cũng `String`, nên suy luận một kiểu `T` phù hợp `String`; giá trị trả về là `"B"`.

### Bài 2 — Factory không có input

~~~java
static <T> List<T> empty() {
    return java.util.Collections.emptyList();
}
~~~

Viết lời gọi để nhận một `List<Long>` mà không phải cast.

**Đáp án:**

~~~java
List<Long> ids = empty();
~~~

Hoặc `MyClass.<Long>empty()` khi tên class tương ứng.

### Bài 3 — Bound

~~~java
static <T extends Number> T same(T value) {
    return value;
}
~~~

**Câu hỏi:** lời gọi `same("12")` có hợp lệ không? Tại sao?

**Đáp án:** không; `String` không thỏa bound `Number`. Type witness `<String>` cũng không giúp.

### Bài 4 — Lambda và inference

Với `transform` ở mục 17:

~~~java
List<Integer> sizes =
        transform(List.of("a", "abcd"), String::length);
~~~

**Đáp án:** `[1, 4]`. Compiler kết hợp kiểu `String` của source và `int` của `String.length()` (boxing thành `Integer`) để suy luận các type arguments.

### Bài 5 — var

**Câu hỏi:** khác biệt kiểu tĩnh giữa:

~~~java
List<String> values = Collections.emptyList();
var automatic = Collections.emptyList();
~~~

**Đáp án:** `values` có kiểu `List<String>`, `automatic` có kiểu `List<Object>` trong trường hợp này. Vì generics invariant, hai kiểu không thể gán qua lại tùy ý.

### Bài 6 — Mixed input

~~~java
Number n = first(5, 3.5);
~~~

Giải thích vì sao lời gọi hợp lệ dù hai đối số có wrapper types khác nhau, và vì sao kết quả runtime được in có thể là `5`.

### Bài 7 — Lỗi wildcard

Vì sao không thể thêm tự do `Integer.valueOf(3)` vào `List<? extends Number>`? Cách thiết kế một method chỉ đọc danh sách có thể vẫn chấp nhận kiểu ấy?

### Bài 8 — Explicit witness

Viết lời gọi `Collections.<String>emptyList()` và giải thích khác biệt với `new ArrayList<>()`.

### Bài 9 — Debug type inference

Một lời gọi generic có lambda lồng nhau báo `cannot infer type-variable(s)`. Hãy tách lambda thành biến `Function<Input,Output>` typed, xác định type bounds và nhìn lại overload của phương thức đang gọi. Đừng dùng raw type để ép code biên dịch.

## 19. Quy trình gỡ lỗi inference thực tế

Khi gặp lỗi suy luận kiểu, làm theo thứ tự:

1. **Xác định generic method được chọn** và liệt kê `<T,R,...>` của nó.
2. **Đọc chữ ký formal parameters và return type**, gồm wildcard và các bounds.
3. **Xác định kiểu chính xác của arguments** — tránh đoán dựa trên giá trị in ra. Kiểm tra việc boxing/unboxing.
4. **Ghi target type nếu có**: phép gán, return statement hay tham số của phương thức ngoài.
5. **Nếu có lambda/method reference**, viết rõ functional interface đích hoặc tách thành biến typed.
6. **Nếu có `var`**, cân nhắc thay bằng khai báo generic rõ ràng để tạo target type phần tử.
7. **Nếu là lời gọi lồng nhau**, tách thành hai câu lệnh có kiểu tường minh nhằm chỉ ra ràng buộc thiếu.
8. **Nếu có overload**, xác nhận đó là lỗi chọn overload hay lỗi giải type arguments; hai lỗi không cùng bản chất.
9. **Dùng explicit type witness** chỉ khi nó làm rõ một type parameter cụ thể mà compiler cần, ví dụ `MyClass.<String>empty()`.
10. **Không bỏ cảnh báo `unchecked` bằng cast/raw type** chỉ để test xanh. Chọn lại API hoặc kiểu dữ liệu nếu ràng buộc không được mô hình hóa đúng.

### Ví dụ “trước và sau” để dễ debug

Thay vì viết một pipeline phức tạp ngay:

~~~java
List<Integer> output =
        transform(List.of("1", "2"), Integer::parseInt);
~~~

hãy tách rõ:

~~~java
List<String> source = List.of("1", "2");

java.util.function.Function<String, Integer> parser =
        Integer::parseInt;

List<Integer> output = transform(source, parser);
~~~

Các biến typed giúp nhìn thấy `T=String`, `R=Integer` và kiểu của callback. Khi đã hiểu/biên dịch thành công, bạn có thể quay lại dạng ngắn nếu mã vẫn dễ đọc.

## 20. Tổng kết

- **Suy luận kiểu trong generic method invocation** tìm type arguments thỏa các ràng buộc từ arguments, type bounds, target context và các biểu thức liên quan.
- **Java 8 nâng cao target typing** để generic method calls phối hợp tốt hơn với lambda, method reference và nested invocations. Cơ chế này vẫn hiện diện trong Java hiện hành.
- **Poly expressions** có thể nhận target type từ phép gán hoặc lời gọi ngoài. `Collections.emptyList()` là một ví dụ điển hình cho generic factory không có đối số.
- **`var` không tự cung cấp một target element type**: `var empty = Collections.emptyList()` thường cho `List<Object>` trong ví dụ đơn giản.
- **Type witness** như `ClassName.<String>method()` cho phép chỉ định tường minh type arguments, nhưng vẫn phải thỏa bounds và không thể tự chữa mọi overload ambiguity.
- **Wildcards và capture conversion** giữ tính an toàn kiểu; `List<? extends Number>` không phải danh sách có thể thêm mọi `Number`.
- **Suy luận kiểu không phải xử lý nghiệp vụ**: compiler bảo vệ quan hệ kiểu, không bảo đảm kết quả thuật toán hoặc xử lý null/exception.
- Khi code khó đọc hoặc compiler báo lỗi, hãy **tách lời gọi, bổ sung biến có kiểu rõ, kiểm tra bounds và signatures** trước khi dùng cast.

## 21. Tài liệu chính thức, còn áp dụng

1. Java Language Specification, **Chapter 18: Type Inference**, nhất là `18.5.1 (invocation applicability) và `18.5.2 (invocation type inference): https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html
2. Java Language Specification, **`15.12 Method Invocation Expressions**, đặc biệt `15.12.2: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12
3. Dev.java, **Type Inference** (tài liệu học Java hiện đại): https://dev.java/learn/generics/type-inference/
4. Java SE 17 API, **Collections.emptyList** và `singletonList`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html
5. Java SE 17 API, **Function** và `java.util.function`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html
6. Java SE 17 API, **List.of** (Java 9+): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html
7. Java Language Specification, **`5.1.10 Capture Conversion**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10

Các nguyên tắc trên là phần của Java hiện hành, không phải kiến thức đã bị loại bỏ. Khi áp dụng vào dự án, luôn biên dịch trên **JDK/`--release` mục tiêu**, đối chiếu JLS/Javadoc tương ứng và kiểm tra lỗi sau mỗi thay đổi overload hoặc signatures generic.