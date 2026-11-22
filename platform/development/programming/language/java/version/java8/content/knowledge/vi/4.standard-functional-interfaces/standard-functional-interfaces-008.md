# Function.compose, andThen và identity trong Java

Trong Java, `java.util.function.Function<T, R>` biểu diễn một phép biến đổi từ đầu vào kiểu `T` sang kết quả kiểu `R`. Ngoài phương thức trừu tượng `apply`, interface này có ba phương thức quan trọng để **kết hợp hoặc tái sử dụng các phép biến đổi**: `compose`, `andThen` và `identity`. Chúng có từ Java 8 và tiếp tục là API chuẩn, còn phù hợp với các ứng dụng Java hiện đại.

Ví dụ, một hệ thống cần nhận chuỗi văn bản, bỏ khoảng trắng hai đầu, chuyển thành số nguyên và nhân đôi. Nếu viết từng bước riêng, mã vẫn hợp lệ; còn `andThen`/`compose` cho phép mô tả các bước đó thành **một `Function` mới**, có thể truyền như lambda, method reference hay callback. `identity` biểu diễn phép biến đổi không làm thay đổi đầu vào.

**Mục tiêu của bài:** hiểu thứ tự thực hiện chính xác, quy tắc tương thích kiểu, cách sử dụng `identity`, thời điểm thực thi, hành vi khi có `null`/ngoại lệ, và các lỗi logic thường gặp.

## 1. Nền tảng: `Function<T, R>` và `apply`

`Function<T, R>` là một *functional interface* có một phương thức trừu tượng:

```java
R apply(T value);
```

Hai chữ `T` và `R` đại diện cho kiểu đầu vào và đầu ra. Ví dụ:

```java
Function<String, Integer> length = text -> text.length();
int size = length.apply("Java"); // 4
```

Đoạn mã minh họa cần `import java.util.function.Function;`. Biểu thức `text -> text.length()` tương đương method reference `String::length` trong ngữ cảnh đó:

```java
Function<String, Integer> length = String::length;
```

Lambda **được tạo ra ở bước gán**, còn phần thân tính độ dài được thực thi khi gọi `apply`. Các phương thức `compose` và `andThen` trả về một hàm kết hợp mới; chúng **không áp dụng phép biến đổi lên dữ liệu ngay khi tạo chuỗi hàm**.

Ba phương thức quan trọng của `Function`:

| Phương thức | Loại | Ý nghĩa |
| --- | --- | --- |
| `R apply(T t)` | Abstract | Thực thi phép biến đổi trên một đầu vào |
| `<V> Function<V,R> compose(Function<? super V,? extends T> before)` | Default | Chạy `before` trước, sau đó chạy hàm hiện tại |
| `<V> Function<T,V> andThen(Function<? super R,? extends V> after)` | Default | Chạy hàm hiện tại trước, sau đó chạy `after` |
| `static <T> Function<T,T> identity()` | Static | Trả về hàm nhận `T` và trả lại chính `T` |

Các chữ ký trong bảng được rút gọn cho dễ đọc nhưng giữ đúng ý nghĩa generic của API Java. `compose`/`andThen` là phương thức mặc định trên đối tượng `Function`; `identity` là phương thức tĩnh gọi qua `Function.identity()`.

## 2. `andThen`: thực hiện hàm hiện tại rồi đến hàm kế tiếp

Cú pháp:

```java
Function<T, V> chain = first.andThen(after);
```

Về mặt ý nghĩa:

```text
Đầu vào T
    |
    v
first.apply(...)
    |
    v
Kết quả trung gian R
    |
    v
after.apply(...)
    |
    v
Kết quả cuối V
```

Công thức:

```text
first.andThen(after).apply(x) = after.apply(first.apply(x))
```

**Trật tự đọc từ trái sang phải:** viết `first.andThen(after)` nghĩa là “chạy `first`, sau đó chạy `after`”.

Ví dụ:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> trimmedLength = trim.andThen(length);
int result = trimmedLength.apply("  Java  "); // 4
```

Lúc đầu `trim` nhận `String`, trả lại `String`. `length` tiếp nhận kết quả `String` đó và trả về `Integer`. `trimmedLength` có kiểu `Function<String,Integer>`. Nếu đảo thứ tự thành `length.andThen(trim)` thì **không biên dịch** vì `trim` cần `String` trong khi `length` trả ra `Integer`.

### 2.1. Nối nhiều bước

`andThen` cho phép kết nối các phép biến đổi có chữ ký tương thích:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Integer> doubleNumber = n -> n * 2;

Function<String, Integer> process =
        trim.andThen(parse).andThen(doubleNumber);

int value = process.apply(" 21 "); // 42
```

Các bước khi gọi `process.apply(" 21 ")`:

1. `trim` đổi `" 21 "` thành `"21"`.
2. `parse` chuyển `"21"` thành `Integer` có giá trị 21.
3. `doubleNumber` biến 21 thành 42.

Nếu `Integer.parseInt` không thể phân tích chuỗi, nó ném `NumberFormatException`; bước nhân đôi không chạy. `andThen` không tự động bắt, chuyển hoặc khôi phục khi lỗi.

## 3. `compose`: thực hiện hàm được truyền vào trước

Cú pháp:

```java
Function<V, R> chain = current.compose(before);
```

Công thức:

```text
current.compose(before).apply(x) = current.apply(before.apply(x))
```

**Trật tự gọi trong mã có thể gây nhầm:** `current` nằm bên trái `.compose`, nhưng `before` **được thực thi trước**.

Ví dụ tương đương với `andThen` ở mục trên:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> trimmedLength = length.compose(trim);
int result = trimmedLength.apply("  Java  "); // 4
```

Thứ tự là `trim` rồi `length`. Hai biểu thức dưới đây **cùng ý nghĩa** nếu các hàm có chữ ký phù hợp:

```java
trim.andThen(length)
length.compose(trim)
```

Cả hai đều tạo hàm nhận `String` và trả về `Integer`.

### 3.1. Phân biệt bằng phép tính không giao hoán

Một bài toán rất dễ hiểu sai là cộng rồi nhân:

```java
Function<Integer, Integer> addThree = n -> n + 3;
Function<Integer, Integer> timesTwo = n -> n * 2;

int a = addThree.andThen(timesTwo).apply(4); // (4 + 3) * 2 = 14
int b = addThree.compose(timesTwo).apply(4); // (4 * 2) + 3 = 11
```

Bảng đối chiếu:

| Biểu thức | Hàm chạy đầu tiên | Hàm chạy tiếp | Kết quả với đầu vào 4 |
| --- | --- | --- | --- |
| `addThree.andThen(timesTwo)` | `addThree` | `timesTwo` | 14 |
| `addThree.compose(timesTwo)` | `timesTwo` | `addThree` | 11 |
| `timesTwo.andThen(addThree)` | `timesTwo` | `addThree` | 11 |
| `timesTwo.compose(addThree)` | `addThree` | `timesTwo` | 14 |

Đây là cách kiểm tra quan trọng: hãy **ghi ra thứ tự thực thi thật** trước khi nghĩ tới tên biến.

### 3.2. Khi nào dùng `compose` thay vì `andThen`?

- Dùng `andThen` khi mô tả pipeline **theo chiều dữ liệu đi qua**: `parse.andThen(validate).andThen(format)` nếu đầu ra/đầu vào tương thích.
- Dùng `compose` khi đã có một hàm cuối và muốn **thêm bước chuẩn bị đầu vào ở phía trước**: `existingTransform.compose(normalizeInput)`.
- Cả hai có thể biểu diễn phép hợp thành tương đương: `f.andThen(g)` tương đương `g.compose(f)` về thứ tự gọi và kết quả, khi các hàm có kiểu phù hợp.

Việc chọn một phong cách nhất quán thường giúp người đọc theo dõi thứ tự tốt hơn. Không nên trộn `compose` và `andThen` trong một chuỗi dài nếu nó làm khó xác định bước nào chạy trước.

## 4. `Function.identity()`: hàm trả lại đúng đầu vào

`Function.identity()` là phương thức tĩnh:

```java
static <T> Function<T, T> identity()
```

Nó biểu diễn phép đồng nhất `id(x) = x`:

```java
Function<String, String> sameText = Function.identity();

String input = "Java";
String output = sameText.apply(input);
System.out.println(output); // Java
```

Đối với đối tượng tham chiếu, `identity` trả về **chính tham chiếu đầu vào**, không tạo bản sao và không chuyển đổi:

```java
StringBuilder builder = new StringBuilder("abc");
Function<StringBuilder, StringBuilder> sameBuilder = Function.identity();

StringBuilder returned = sameBuilder.apply(builder);
boolean sameReference = (returned == builder); // true
```

`identity.apply(null)` trả lại `null`; bản thân hàm identity không tự kiểm tra đầu vào có null hay không. **Identity không đồng nghĩa với phép copy, clone, map sang một đối tượng mới, hay chuẩn hóa dữ liệu.** Nếu đối tượng đầu vào có thể bị sửa ở nơi khác, cả hai tham chiếu vẫn trỏ cùng đối tượng.

### 4.1. Tác dụng trong phép hợp thành

Theo quy tắc toán học:

```text
identity.andThen(f) ≡ f
f.andThen(identity) ≡ f
f.compose(identity) ≡ f
identity.compose(f) ≡ f
```

Ký hiệu `≡` ở đây chỉ **tương đương về hành vi khi áp dụng cho cùng đầu vào**, không bảo đảm hai biến `Function` là cùng một instance hoặc có `equals` bằng nhau.

Ví dụ:

```java
Function<String, String> upper = String::toUpperCase;

Function<String, String> a = Function.<String>identity().andThen(upper);
Function<String, String> b = upper.andThen(Function.identity());

System.out.println(a.apply("java")); // JAVA
System.out.println(b.apply("java")); // JAVA
```

Việc chỉ định `Function.<String>identity()` làm rõ type argument khi ngữ cảnh suy luận phức tạp. Không bắt buộc phải viết tường minh trong trường hợp phép gán có đủ kiểu đích.

### 4.2. Khi `identity` hữu ích thật sự

**Giữ đầu vào làm khóa khi thu thập Stream:**

```java
Map<String, Integer> lengths = Stream.of("Java", "Lambda")
        .collect(Collectors.toMap(
                Function.identity(),
                String::length));
```

`Function.identity()` ở đây là *key mapper*: khóa chính là chuỗi ban đầu; `String::length` tạo giá trị độ dài. Kết quả có hai cặp tương ứng `Java -> 4` và `Lambda -> 6`. Không dựa vào thứ tự in của `HashMap` nếu không dùng map có thứ tự rõ ràng.

**Dùng làm chiến lược mặc định không biến đổi dữ liệu:**

```java
static <T> Function<T, T> chooseTransform(
        Function<T, T> candidate) {
    return candidate != null
            ? candidate
            : Function.identity();
}
```

Đây là phương thức minh họa, cần import `Function`. Ví dụ này diễn đạt chính sách API: nếu không cung cấp biến đổi, giữ nguyên đầu vào. Trong API thực tế, có thể chọn yêu cầu `candidate` không null để phát hiện cấu hình sai sớm; không phải lúc nào fallback identity cũng phù hợp.

**Tạo phép biến đổi đơn vị trong generic utility:** Khi viết mã kết hợp nhiều `Function<T,T>`, identity có thể đóng vai trò phần tử trung hòa khi chưa có bước xử lý.

### 4.3. Cần chú ý khi dùng `identity` với `Collectors.toMap`

Nếu Stream có **khóa trùng**, `Collectors.toMap` ở overload hai đối số có thể ném `IllegalStateException`; `identity` không giải quyết xung đột khóa. Ví dụ:

```java
// Hai phần tử cùng khóa "Java" sẽ va chạm.
// Stream.of("Java", "Java")
//     .collect(Collectors.toMap(Function.identity(), String::length));
```

Muốn cho phép trùng khóa, chọn overload có *merge function* phù hợp với nghiệp vụ:

```java
Map<String, Integer> lengths = Stream.of("Java", "Java")
        .collect(Collectors.toMap(
                Function.identity(),
                String::length,
                Integer::max));
```

`Integer::max` giải quyết hai giá trị có cùng khóa; kết quả có một phần tử `"Java" -> 4`. Đây là ví dụ độc lập với bài toán thứ tự map; chỉ nói về cách xử lý duplicate key.

## 5. Hiểu kiểu generic khi ghép hàm

Giả sử có:

```java
Function<A, B> f = ...;
Function<B, C> g = ...;
```

Đây là ký hiệu **minh họa đại số kiểu**, không phải mã Java biên dịch độc lập vì `A`, `B`, `C` chỉ đại diện cho kiểu giả định và dấu `...` là placeholder.

Khi kết hợp:

```text
f.andThen(g) : Function<A, C>
g.compose(f) : Function<A, C>

A --f--> B --g--> C
```

Điều bắt buộc là **đầu ra của hàm chạy trước phù hợp với đầu vào của hàm chạy sau**. Compiler kiểm tra điều đó qua generic và wildcard của API.

Ví dụ thay đổi kiểu qua từng bước:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Long> toLong = Integer::longValue;
Function<Long, String> present = number -> "Giá trị=" + number;

Function<String, String> pipeline =
        parse.andThen(toLong).andThen(present);

System.out.println(pipeline.apply("42")); // Giá trị=42
```

Các bước: `String` → `Integer` → `Long` → `String`. Kết quả cuối là `Function<String,String>`, **không** phải `Function<String,Long>`.

### 5.1. Vì sao có `? super` và `? extends`?

Chữ ký chính thức:

```java
default <V> Function<T, V> andThen(
        Function<? super R, ? extends V> after)

default <V> Function<V, R> compose(
        Function<? super V, ? extends T> before)
```

Đây là các chữ ký được trích biểu diễn cấu trúc API để học, **không** được đặt vào file Java như phương thức top-level.

- `? super R` ở đầu vào của `after` cho phép nó chấp nhận `R` hoặc một kiểu cha của `R`.
- `? extends V` ở đầu ra của `after` cho phép nó tạo `V` hoặc một kiểu con của `V`.
- `compose` có logic tương tự với kiểu đầu vào của `before` và kiểu kết quả mà hàm hiện tại nhận.

Ví dụ với phân cấp kiểu chuẩn:

```java
Function<String, Integer> length = String::length;
Function<Number, String> describe = n -> "n=" + n;

Function<String, String> combined = length.andThen(describe);
System.out.println(combined.apply("Java")); // n=4
```

`length` trả `Integer`, còn `describe` chấp nhận `Number`. Vì `Integer` là lớp con của `Number`, phép ghép là hợp lệ. Đây là ứng dụng cụ thể của wildcard về tính tương thích kiểu.

Không cần tự thêm cast để ép ghép hai hàm không tương thích: nếu compiler báo lỗi, hãy kiểm tra chữ ký đầu vào và đầu ra của từng bước.

## 6. Thời điểm thực thi: tạo hàm trước, gọi `apply` sau

`andThen` và `compose` tạo ra một `Function` kết hợp. Chúng **không tự chạy phần thân của `before`/`after` trong lúc tạo pipeline**:

```java
Function<Integer, Integer> stepA = n -> {
    System.out.print("A ");
    return n + 1;
};

Function<Integer, Integer> stepB = n -> {
    System.out.print("B ");
    return n * 2;
};

Function<Integer, Integer> pipeline = stepA.andThen(stepB);
// Chưa in "A " hoặc "B ".

int result = pipeline.apply(3);
// Lúc này mới in "A B " và result bằng 8.
```

Đoạn trên minh họa việc quan sát side effect khi thực thi; nó không phải phần của chương trình chính ở mục 10.

Nếu gọi `pipeline.apply(...)` nhiều lần thì các bước được thực hiện lại mỗi lần. `Function` không hứa memoization, caching hoặc tự động làm cho hàm bất biến. Kết hợp `Function` cũng không có nghĩa là chạy song song, tạo thread mới hay chạy bất đồng bộ.

### 6.1. Ngoại lệ truyền qua pipeline

Theo hợp đồng API, nếu một bước ném ngoại lệ trong khi `apply`, ngoại lệ được chuyển đến người gọi hàm kết hợp và các bước tiếp theo **không được thực thi**:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Integer> doubleIt = n -> n * 2;

Function<String, Integer> pipeline = parse.andThen(doubleIt);
// pipeline.apply("abc") ném NumberFormatException,
// nên doubleIt không được gọi.
```

`NumberFormatException` là unchecked exception, vì vậy `Function.apply` không cần khai báo `throws`. Các functional interface chuẩn `Function` và các phương thức `compose`/`andThen` **không biến một checked exception thành hợp lệ** nếu thân lambda không được phép ném nó theo chữ ký SAM. Khi cần I/O có checked `IOException`, phải xử lý trong lambda hoặc thiết kế interface/hợp đồng riêng phù hợp; không thể chỉ thêm `compose` để tránh quy tắc của compiler.

### 6.2. Null ở hai thời điểm khác nhau

Nếu truyền chính đối tượng hàm `before` hoặc `after` bằng `null`, phương thức tạo tổ hợp ném `NullPointerException`:

```java
Function<String, Integer> length = String::length;

// KHÔNG THỰC THI khi không muốn lỗi:
// length.compose(null); // NullPointerException
// length.andThen(null); // NullPointerException
```

Ngược lại, đầu vào null trong `apply(null)` sẽ được truyền cho bước đầu; ngoại lệ phụ thuộc vào hàm cụ thể. Ví dụ `String::length` không nhận được null và sẽ ném `NullPointerException`, trong khi `Function.identity().apply(null)` trả lại null. **`compose` và `andThen` không tự kiểm tra mọi kết quả trung gian có null hay không**.

Nếu hệ thống có thể có input null, xác định rõ chính sách trong hợp đồng của từng hàm; không mặc định pipeline an toàn với null.

## 7. Phân biệt `Function` với các API ghép hàm khác

### 7.1. `UnaryOperator<T>`

`UnaryOperator<T>` là một interface con của `Function<T,T>`, thuận tiện khi kiểu đầu vào và đầu ra giống nhau. Dù vậy, phương thức `andThen`/`compose` được kế thừa từ `Function` có kiểu trả về khai báo là `Function`. Ví dụ:

```java
UnaryOperator<String> trim = String::trim;
UnaryOperator<String> upper = String::toUpperCase;

Function<String, String> together = trim.andThen(upper);
```

Đoạn mã cần import `java.util.function.UnaryOperator` và `Function`. Không nên mặc định phép ghép `UnaryOperator.andThen` có kiểu tĩnh trả về `UnaryOperator`; khai báo `Function<String,String>` là chính xác theo chữ ký API.

### 7.2. `IntUnaryOperator` và các kiểu chuyên biệt cho primitive

`IntUnaryOperator` có `compose`, `andThen` và `identity` riêng, hoạt động với `int` để tránh boxing sang `Integer` trong đường xử lý primitive:

```java
IntUnaryOperator plusOne = n -> n + 1;
IntUnaryOperator square = n -> n * n;

int a = plusOne.andThen(square).applyAsInt(3); // 16
int b = plusOne.compose(square).applyAsInt(3); // 10
int c = IntUnaryOperator.identity().applyAsInt(3); // 3
```

Đoạn mã cần import `java.util.function.IntUnaryOperator`. Chữ ký, thứ tự thực thi có ý nghĩa tương tự với `Function`, nhưng các hàm nhận và trả về primitive `int`. Có thể cân nhắc ở đoạn mã xử lý số lượng lớn dữ liệu primitive nếu đo đạc cho thấy boxing đáng kể.

### 7.3. `BiFunction<T,U,R>`

`BiFunction` nhận hai đầu vào và trả kết quả, có `andThen` để biến đổi kết quả sau khi `apply`:

```java
BiFunction<Integer, Integer, Integer> sum = Integer::sum;
BiFunction<Integer, Integer, String> formatSum =
        sum.andThen(n -> "Tổng=" + n);
```

`BiFunction` **không có phương thức `compose` tương ứng với `Function.compose`**. Điều này hợp lý vì việc chuẩn bị hai đầu vào cần hợp đồng khác, không phải một phép biến đổi đầu vào đơn giản. Đừng đoán mọi functional interface đều có đủ bộ ba phương thức.

### 7.4. `Predicate` và `Consumer`

`Predicate` có `and`, `or`, `negate` để kết hợp điều kiện; `Consumer` có `andThen` để nối các hành động `void`. Đây là các API với ngữ nghĩa riêng, không đồng nhất với `Function.andThen`.

`Function` phù hợp khi cần đầu vào và **kết quả** qua các bước. Nếu chỉ cần điều kiện lọc, `Predicate` thường diễn đạt tốt hơn. Nếu chỉ cần hành động không kết quả, `Consumer` rõ hơn `Function<T,Void>`.

## 8. Mối quan hệ với Stream API

`Stream.map` nhận `Function`, vì vậy có thể truyền hàm kết hợp trực tiếp:

```java
Function<String, String> normalize =
        ((Function<String, String>) String::trim)
                .andThen(String::toLowerCase);

List<String> normalized = source.stream()
        .map(normalize)
        .collect(Collectors.toList());
```

Đoạn trên giả định `source` là `List<String>` và có import `Function`, `List`, `Collectors`. Phép ép kiểu ở method reference chỉ để giúp xác định target type trong ví dụ; cách dễ đọc hơn là khai báo hai biến `Function` với kiểu rõ ràng rồi ghép.

Một phiên bản dễ đọc và tránh ép kiểu:

```java
Function<String, String> trim = String::trim;
Function<String, String> lower = s -> s.toLowerCase(Locale.ROOT);
Function<String, String> normalize = trim.andThen(lower);

List<String> normalized = source.stream()
        .map(normalize)
        .collect(Collectors.toList());
```

`Locale.ROOT` giúp xử lý chữ hoa/thường có kết quả ổn định hơn trong các phép chuẩn hóa mang tính kỹ thuật. Với nội dung ngôn ngữ tự nhiên, việc chọn locale cần bám theo nhu cầu nghiệp vụ.

Lưu ý: Stream là API có ngữ nghĩa thực thi riêng, đặc biệt với các thao tác trung gian lazy như `map`. `compose`/`andThen` chỉ tạo một callback dùng trong `map`, **không thay đổi quy tắc lazy hoặc parallel của Stream**.

### 8.1. Khi nào nên tách thành nhiều `map`?

Hai cách này thường cho kết quả tương đương với các hàm thuần và pipeline đơn giản:

```java
stream.map(trim).map(lower)
stream.map(trim.andThen(lower))
```

Đoạn mã giả định `stream` là `Stream<String>` và các hàm `trim`, `lower` đã được khai báo. **Tương đương ở đây là về kết quả biến đổi**, không khẳng định mọi side effect/đặc điểm tối ưu hóa của Stream đều giống nhau trong mọi tình huống.

Tách thành nhiều `map` khi mỗi bước cần quan sát riêng hoặc giúp dễ hiểu. Ghép thành một `Function` khi muốn dùng lại tổ hợp ở nhiều nơi hoặc truyền vào API chỉ nhận một mapper. Nên tránh side effect khi biến đổi dữ liệu trong Stream để không tạo phụ thuộc vào thứ tự và cách thực thi.

## 9. Thiết kế pipeline dễ bảo trì

### 9.1. Đặt tên hàm theo kết quả và trách nhiệm

Ví dụ trong xử lý mã đơn hàng (hành vi minh họa):

```java
Function<String, String> trim = String::trim;
Function<String, String> uppercase = s -> s.toUpperCase(Locale.ROOT);
Function<String, String> normalizeCode = trim.andThen(uppercase);
```

Tên `normalizeCode` giúp người sử dụng hiểu toàn bộ phép biến đổi. Tuy nhiên, **chuẩn hóa mã đơn hàng** có thể cần quy tắc nghiệp vụ riêng, chẳng hạn cho phép ký tự nào, xử lý unicode hay null, và phải được định nghĩa trong hợp đồng thực sự. Không đồng nhất `trim + uppercase` với mọi quy tắc chuẩn hóa có thể có.

### 9.2. Kiểm tra đầu vào ở bước thích hợp

```java
Function<String, String> requireNonNull =
        text -> Objects.requireNonNull(text, "text");
Function<String, String> trim = String::trim;
Function<String, String> safeNormalize =
        requireNonNull.andThen(trim);
```

Đoạn mã cần `java.util.Objects`. `safeNormalize.apply(null)` ném `NullPointerException` có thông điệp `"text"` trước khi thực hiện `trim`. Tên `safeNormalize` ở đây chỉ minh họa **fail-fast với null**, không có nghĩa giá trị đã được kiểm tra mọi quy tắc nghiệp vụ khác.

Với dữ liệu có thể không hợp lệ, hãy xác định chính sách: ném ngoại lệ, trả cấu trúc kết quả kiểm tra, hay áp dụng fallback hợp lệ. Đừng âm thầm biến lỗi thành dữ liệu giả chỉ để giữ cho pipeline chạy.

### 9.3. Tác dụng phụ và khả năng kiểm thử

Chỉ vì `Function` cho phép side effect không có nghĩa là mọi chuỗi xử lý nên chứa thao tác sửa trạng thái, ghi file hoặc gọi mạng. Các hàm nhỏ, thuần (cùng đầu vào cho cùng kết quả, không có tác dụng phụ quan sát được) thường dễ ghép, kiểm tra và suy luận hơn.

Nếu một bước cần ghi log hoặc cập nhật trạng thái, ghi rõ thứ tự và ngoại lệ có thể xảy ra; `andThen` bảo đảm thứ tự gọi **trong một lần áp dụng**, nhưng không cung cấp transaction, rollback hay đồng bộ đa luồng.

### 9.4. Lưu ý về độ dài chuỗi và hiệu năng

Một pipeline rất dài có thể giảm khả năng đọc hoặc khiến stack trace khó theo dõi. Việc ghép các `Function` không đồng nghĩa tạo một lần tính toán được compiler tối ưu hoàn toàn. Hãy ưu tiên thiết kế rõ, và chỉ điều chỉnh hiệu năng dựa trên đo đạc.

## 10. Chương trình hoàn chỉnh có thể biên dịch và chạy

Tạo file **`FunctionCompositionDemo.java`**. Mã dùng cú pháp/API Java 8-compatible, có thể chạy trên JDK 17+ và vẫn tương thích khi cần mức Java 8.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.stream.Collectors;

public class FunctionCompositionDemo {

    public static void main(String[] args) {
        Function<String, String> trim = String::trim;
        Function<String, Integer> length = String::length;

        Function<String, Integer> viaAndThen =
                trim.andThen(length);
        Function<String, Integer> viaCompose =
                length.compose(trim);

        System.out.println("andThen: "
                + viaAndThen.apply("  Java  "));
        System.out.println("compose: "
                + viaCompose.apply("  Java  "));

        Function<Integer, Integer> addThree = n -> n + 3;
        Function<Integer, Integer> timesTwo = n -> n * 2;

        System.out.println("Cộng rồi nhân: "
                + addThree.andThen(timesTwo).apply(4));
        System.out.println("Nhân rồi cộng: "
                + addThree.compose(timesTwo).apply(4));

        Function<String, Integer> parse = Integer::parseInt;
        Function<String, Integer> parseAndDouble =
                trim.andThen(parse).andThen(timesTwo);

        System.out.println("Chuỗi nhiều bước: "
                + parseAndDouble.apply(" 21 "));

        Function<String, String> same = Function.identity();
        System.out.println("identity: " + same.apply("Lambda"));

        StringBuilder builder = new StringBuilder("same");
        Function<StringBuilder, StringBuilder> preserveReference =
                Function.identity();
        System.out.println("Cùng tham chiếu: "
                + (preserveReference.apply(builder) == builder));

        Function<String, String> uppercase =
                s -> s.toUpperCase(Locale.ROOT);
        Function<String, String> normalize =
                trim.andThen(uppercase);

        List<String> items =
                Arrays.asList("  java ", " lambda  ");
        List<String> normalized = items.stream()
                .map(normalize)
                .collect(Collectors.toList());

        System.out.println("Stream: " + normalized);

        Map<String, Integer> lengths =
                normalized.stream()
                        .collect(Collectors.toMap(
                                Function.identity(),
                                String::length));

        System.out.println("Độ dài JAVA: " + lengths.get("JAVA"));

        IntUnaryOperator plusOne = n -> n + 1;
        IntUnaryOperator square = n -> n * n;
        System.out.println("Primitive: "
                + plusOne.andThen(square).applyAsInt(3));

        try {
            parseAndDouble.apply("không-phải-số");
        } catch (NumberFormatException e) {
            System.out.println("Lỗi parse: NumberFormatException");
        }
    }
}
```

Chạy:

```bash
javac FunctionCompositionDemo.java
java FunctionCompositionDemo
```

**Stdout chính xác**:

```text
andThen: 4
compose: 4
Cộng rồi nhân: 14
Nhân rồi cộng: 11
Chuỗi nhiều bước: 42
identity: Lambda
Cùng tham chiếu: true
Stream: [JAVA, LAMBDA]
Độ dài JAVA: 4
Primitive: 16
Lỗi parse: NumberFormatException
```

Giải thích ngắn theo từng phần:

1. `trim.andThen(length)` và `length.compose(trim)` đều chạy `trim` trước `length`, nên kết quả cùng là 4.
2. `addThree.andThen(timesTwo)` chạy cộng trước nhân, ra 14; `addThree.compose(timesTwo)` nhân trước cộng, ra 11.
3. Chuỗi `trim → parse → timesTwo` biến `" 21 "` thành 42.
4. `Function.identity()` trả lại chuỗi `"Lambda"` và cả tham chiếu `StringBuilder` ban đầu; kiểm tra `==` trên đối tượng đó là `true`.
5. Stream biến các chuỗi thành `JAVA` và `LAMBDA`; `Collectors.toMap` dùng `identity` giữ nguyên chuỗi đã chuẩn hóa làm khóa, từ đó `lengths.get("JAVA")` trả 4.
6. `IntUnaryOperator` cộng một rồi bình phương giá trị 3, nên kết quả là `(3 + 1) * (3 + 1) = 16`.
7. Giá trị không phải số làm `Integer.parseInt` ném `NumberFormatException`; chương trình bắt đúng loại để in thông báo xác định.

## 11. Những lỗi thường gặp khi dùng `compose`, `andThen` và `identity`

| Sai lầm | Vì sao có vấn đề | Cách tránh |
| --- | --- | --- |
| Nghĩ `f.compose(g)` chạy `f` trước | Thực tế `g` chạy trước | Viết công thức `f(g(x))` để xác nhận |
| Nghĩ `f.andThen(g)` chạy `g` trước | Thực tế `f` chạy trước | Đọc từ trái sang phải `f → g` |
| Ghép đầu ra `Integer` với hàm chỉ nhận `String` | Generic không tương thích | Ghi kiểu của từng bước và kiểm tra `T → R` |
| Tưởng gọi `andThen` đã xử lý dữ liệu | Nó tạo ra `Function` mới | Cần gọi `apply` hoặc truyền callback cho API tiêu thụ |
| Nghĩ `identity` tạo bản sao an toàn | Nó trả lại đúng tham chiếu đầu vào | Dùng cơ chế copy riêng khi muốn bản sao |
| Dùng `identity` trong `toMap` mà bỏ qua khóa trùng | Duplicate key có thể gây `IllegalStateException` | Chọn merge function nếu cần |
| Đặt `before=null` hoặc `after=null` | Gọi `compose(null)`/`andThen(null)` ném `NullPointerException` | Truyền `Function` hợp lệ |
| Nghĩ `Function` tự xử lý checked exception | `apply` không khai báo checked exception | Bắt trong lambda hoặc đổi hợp đồng nhận callback nếu có quyền |
| Đặt nhiều side effect trong pipeline và suy đoán có rollback | API ghép hàm không hỗ trợ transaction | Tách trách nhiệm và kiểm soát lỗi ở tầng thích hợp |
| Dùng `compose`/`andThen` như API async | Đây là lời gọi hàm đồng bộ khi `apply` | Dùng abstraction phù hợp nếu cần bất đồng bộ |
| Hiểu nhầm `UnaryOperator.andThen` trả về `UnaryOperator` | Chữ ký kế thừa trả về `Function<T,V>` | Khai báo kiểu kết quả `Function` phù hợp |

## 12. Checklist dùng ngay trong công việc

1. Xác định `T` và `R` của từng `Function<T,R>`.
2. Viết chuỗi thứ tự mong muốn trước: `A → B → C`.
3. Nếu đọc theo chiều dữ liệu, nối `A.andThen(B).andThen(C)`.
4. Nếu bổ sung bước chuẩn bị đầu vào cho hàm cuối, có thể dùng `C.compose(B).compose(A)`, miễn kiểu khớp.
5. Nếu không muốn thay đổi đầu vào, dùng `Function.identity()` và nhớ rằng nó **không copy**.
6. Xác định chính sách null, lỗi parse, checked exception và tác dụng phụ.
7. Chỉ gọi `apply` khi đã có dữ liệu; tạo hàm không chạy các bước.
8. Khi tích hợp với `Stream.map`, cân nhắc hàm nhỏ, ít side effect và quy tắc xử lý dữ liệu lỗi.
9. Kiểm tra cả trường hợp biểu thức không giao hoán để chắc chắn thứ tự đúng.
10. Chọn primitive-specialized interface nếu chữ ký và số lần thao tác khiến boxing đáng cân nhắc.

**Ghi nhớ:**

- `f.andThen(g)` = **gọi `f` rồi gọi `g`**, tương đương `g(f(x))`.
- `f.compose(g)` = **gọi `g` rồi gọi `f`**, tương đương `f(g(x))`.
- `Function.identity()` = **trả lại đầu vào**, không biến đổi và không tạo bản sao.

Ba phương thức đều thuộc API Java chuẩn từ Java 8 và tiếp tục hữu ích trong các pipeline xử lý dữ liệu hiện đại.

## Tài liệu chuẩn để tra cứu

- Java SE API: `java.util.function.Function` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html
- Java SE API: `java.util.function.IntUnaryOperator` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/IntUnaryOperator.html
- Java SE API: `java.util.stream.Stream` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
