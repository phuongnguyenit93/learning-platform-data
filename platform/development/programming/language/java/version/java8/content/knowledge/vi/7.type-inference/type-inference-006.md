# Ép kiểu tường minh để làm rõ ý nghĩa trong suy luận kiểu Java

**Ép kiểu tường minh** (*explicit cast*) là cách người lập trình chỉ rõ kiểu mà một biểu thức cần được xem xét, bằng cú pháp `(TargetType) expression`. Trong Java, ép kiểu có hai vai trò rất khác nhau cần phân biệt:

1. **Xác lập kiểu đích lúc biên dịch**, đặc biệt cho lambda hoặc method reference là những biểu thức cần *target typing*. Khi gặp nhiều functional interface có thể phù hợp, cast có thể làm rõ bạn muốn giao diện nào.
2. **Yêu cầu chuyển đổi/kiểm tra một giá trị đã có**, ví dụ chuyển một tham chiếu kiểu `Object` sang `String`. Với tham chiếu thông thường, cast có thể cần kiểm tra tại runtime và ném `ClassCastException`.

Ở nhóm kiến thức **suy luận kiểu**, vai trò thứ nhất là trọng tâm. Java suy luận kiểu rất tốt khi đã có ngữ cảnh, nhưng không phải mọi biểu thức đều có một kiểu duy nhất tự suy ra từ chính cú pháp. Cast tường minh có thể bổ sung đúng kiểu đích còn thiếu, hoặc phân giải một lời gọi overload khó hiểu.

**Nguyên tắc thực hành:** ưu tiên **kiểu khai báo rõ, generic đúng và API không nhập nhằng**. Chỉ thêm cast khi nó thực sự truyền đạt ý định hoặc giúp compiler chọn kiểu đích hợp lệ. Cast không phải cách tắt kiểm tra kiểu, không tạo ra một đối tượng kiểu khác và không thể biến lambda không tương thích thành hợp lệ.

Các quy tắc dưới đây có từ Java 8 và vẫn áp dụng trong Java hiện đại. Bài có ví dụ chạy được trên JDK 17+; phần mã hoàn chỉnh không phụ thuộc API đã lỗi thời.

## 1. Nhắc lại: suy luận kiểu phụ thuộc ngữ cảnh

Java sử dụng nhiều nguồn thông tin để suy ra kiểu, chẳng hạn kiểu ở vế trái phép gán, chữ ký phương thức được gọi, kiểu tham số generic và kiểu trả về kỳ vọng.

Ví dụ bình thường không cần cast:

```java
import java.util.function.Function;

Function<String, Integer> length = String::length;
int value = length.apply("Java"); // 4
```

Trong phép gán này:

- `Function<String,Integer>` là kiểu **được kỳ vọng** (*target type*).
- SAM `Integer apply(String input)` cho biết method reference cần nhận một `String`.
- `String::length` chỉ đến phương thức instance `int length()`; kết quả `int` có thể boxing thành `Integer`.

Vì ngữ cảnh đã đầy đủ, viết thêm `(Function<String,Integer>)` ở đây thường không cải thiện gì.

Lambda cũng tương tự:

```java
java.util.function.Predicate<String> nonEmpty =
        text -> !text.isEmpty();
```

Kiểu của tham số `text` được suy luận là `String` từ `Predicate<String>`. Điều này khác với lập trình viên tự ép kiểu một giá trị trong thân lambda.

### 1.1. Lambda và method reference là poly expression

Trong các ngữ cảnh thích hợp, lambda và method reference được kiểm tra dựa trên **functional interface đích**, chứ không có một kiểu callback độc lập duy nhất trước khi biết nơi sử dụng.

Ví dụ cố ý không biên dịch:

```java
// KHÔNG BIÊN DỊCH vì Object không phải functional interface đích:
// Object callback = text -> text.trim();

// KHÔNG BIÊN DỊCH vì method reference thiếu target function type:
// Object length = String::length;
```

Một đối tượng lambda sau khi được tạo ra có thể được tham chiếu qua kiểu `Object`, nhưng biểu thức lambda **không thể lấy `Object` làm target type trực tiếp**.

Cách hợp lệ là xác định functional interface trước:

```java
Object callback =
        (Function<String, String>) String::trim;
```

`Function<String,String>` trong cast cung cấp target type cho method reference. Sau đó, đối tượng kết quả được gán cho biến kiểu `Object` bằng chuyển đổi tham chiếu thông thường. Tuy nhiên, việc lưu callback dưới `Object` sẽ làm người gọi khó sử dụng hơn; nếu cần gọi `apply`, hãy giữ biến có kiểu `Function<String,String>` ngay từ đầu.

## 2. Cú pháp cast làm rõ target type cho lambda

Một cast có dạng `(FunctionalInterface) lambdaExpression`, trong đó kiểu trong dấu ngoặc phải là một target functional interface phù hợp.

```java
java.util.function.Supplier<String> factory =
        (java.util.function.Supplier<String>) () -> "Java";
```

Đoạn này hợp lệ, nhưng cast dư thừa vì kiểu ở vế trái đã là `Supplier<String>`. Cách ngắn và dễ đọc hơn:

```java
java.util.function.Supplier<String> factory =
        () -> "Java";
```

Cast trở nên có giá trị khi **vế trái không đưa ra target type đủ cụ thể**, hoặc một lời gọi overload cần phân biệt hai functional interface.

### 2.1. Cast là một cách cung cấp target type, không phải chuyển đổi kết quả lambda

Ví dụ:

```java
java.util.function.Function<String, Integer> length =
        (java.util.function.Function<String, Integer>)
                (text -> text.length());
```

Cast nói rằng callback có hợp đồng `String -> Integer`. Nó **không** có nghĩa “lấy kết quả `int` rồi ép cả lambda thành `Integer`”. Cơ chế boxing kết quả của `length()` xảy ra do kiểu trả về SAM.

Nếu thân lambda không tương thích với SAM, cast không cứu được:

```java
// KHÔNG BIÊN DỊCH: Predicate.test phải trả boolean.
// java.util.function.Predicate<String> bad =
//         (java.util.function.Predicate<String>)
//                 (text -> text.length());
```

Không thể chuyển `int` thành `boolean` bằng việc gắn tên `Predicate<String>` vào lambda.

### 2.2. Cast tới interface phù hợp với chữ ký

```java
java.util.function.Function<String, Integer> length =
        (java.util.function.Function<String, Integer>) String::length;

java.util.function.Predicate<String> empty =
        (java.util.function.Predicate<String>) String::isEmpty;

java.util.function.BiPredicate<String, String> starts =
        (java.util.function.BiPredicate<String, String>)
                String::startsWith;
```

Ba method reference này có số đầu vào/kiểu đầu ra khác nhau:

- `String::length` cần receiver `String` và tạo `int`.
- `String::isEmpty` cần receiver `String` và tạo `boolean`.
- `String::startsWith` cần receiver và prefix `String`, tạo `boolean`.

Các cast trên hợp lệ nhưng không cần thiết nếu có khai báo biến đích rõ ràng. Điều quan trọng là **phù hợp chữ ký**, không phải dùng cast càng nhiều càng tốt.

## 3. Tình huống hữu ích nhất: phân giải overload

Giả sử một lớp có hai overload đều chấp nhận lambda không đối số, có kết quả kiểu `String`:

```java
static void execute(java.util.function.Supplier<String> source) {
    System.out.println("Supplier: " + source.get());
}

static void execute(java.util.concurrent.Callable<String> task)
        throws Exception {
    System.out.println("Callable: " + task.call());
}
```

Đây là hai phương thức **minh họa trong một lớp Java**, không phải tệp chạy độc lập. `Supplier.get()` và `Callable.call()` đều không có tham số và đều trả một `String`. Vì cả hai functional interface đều có thể nhận lambda `() -> "ready"`, câu lệnh sau **nhập nhằng**:

```java
// KHÔNG BIÊN DỊCH: lời gọi overload không xác định duy nhất.
// execute(() -> "ready");
```

Bạn có thể làm rõ ý định bằng cast:

```java
execute((java.util.function.Supplier<String>)
        () -> "ready");

execute((java.util.concurrent.Callable<String>)
        () -> "ready");
```

- Cast `Supplier<String>` buộc compiler xem lambda theo SAM `String get()` và chọn overload nhận `Supplier`.
- Cast `Callable<String>` buộc compiler xem lambda theo SAM `String call() throws Exception` và chọn overload nhận `Callable`.
- Ở ví dụ, overload `Callable` có `throws Exception` nên ngữ cảnh gọi cần xử lý hoặc khai báo ngoại lệ như bình thường. Cast không xóa bỏ hợp đồng ngoại lệ.

**Mấu chốt:** cast làm rõ **overload nào bạn muốn gọi**. Nó không ép Java chạy một overload “bất chấp” tham số không tương thích.

### 3.1. Khi nào nên chọn biến trung gian thay cho cast?

Cũng có thể viết:

```java
java.util.function.Supplier<String> source = () -> "ready";
execute(source);
```

Với callback có nhiều dòng hoặc được dùng ở nhiều nơi, biến trung gian thường dễ đọc và test hơn. Cast ngay tại nơi gọi hữu ích khi lambda ngắn và muốn thể hiện rõ quyết định chọn overload.

### 3.2. Method reference cũng có thể dùng cast để giải quyết overload

Ví dụ:

```java
execute((java.util.function.Supplier<String>) String::new);
```

`String::new` là constructor reference không đối số trong ngữ cảnh `Supplier<String>`. Cast làm rõ interface đích và overload. Nếu đã có biến:

```java
java.util.function.Supplier<String> emptyText = String::new;
execute(emptyText);
```

thì không cần cast. Trong nhiều trường hợp, chuỗi rỗng có thể viết gọn `() -> ""`; chọn biểu thức đơn giản nhất đối với ý định hiện tại.

### 3.3. Không phải mọi overload với lambda đều nhập nhằng

Compiler vẫn có các quy tắc chọn overload thích hợp, bao gồm khả năng phân biệt lambda trả `void` và lambda trả giá trị, hoặc kiểu dữ liệu primitive/reference trong những trường hợp luật Java cho phép.

**Không nên cho rằng “cứ có hai overload nhận functional interface là phải cast”.** Chỉ cân nhắc cast khi compiler báo nhập nhằng, khi suy luận chưa phản ánh ý định, hoặc khi người đọc cần thấy target type rõ hơn. Trước hết hãy kiểm tra phương thức nào thực sự phù hợp.

Một API public có nhiều overload khác nhau chỉ bởi các functional interface tương tự nhau thường gây khó sử dụng. Nếu bạn thiết kế API, cân nhắc **đặt tên phương thức khác nhau** (ví dụ `executeSupplier` và `executeCallable`) thay vì bắt mọi caller phải cast.

## 4. Làm rõ method reference trong biểu thức phức tạp

Method reference có thể dùng trực tiếp bên trong một lời gọi khi method đích cung cấp kiểu:

```java
java.util.List<String> words =
        java.util.Arrays.asList("Java", "Lambda");

java.util.List<Integer> lengths = words.stream()
        .map(String::length)
        .collect(java.util.stream.Collectors.toList());
```

`Stream<String>.map` đã yêu cầu một `Function<? super String,? extends R>`. Compiler thường suy luận được `R` ở các tình huống như thế này; không cần cast vào `String::length`.

Khi bạn muốn **gọi ngay phương thức của một Function vừa tạo bằng method reference**, cần cung cấp kiểu đích rõ ràng:

```java
int count =
        ((java.util.function.Function<String, Integer>)
                String::length).apply("Lambda"); // 6
```

Đây là trường hợp cast có tác dụng: `String::length` cần target functional interface để có thể gọi `apply`, trong khi không có biến trung gian. Dù vậy, để code dễ đọc hơn, bạn có thể khai báo:

```java
java.util.function.Function<String, Integer> length =
        String::length;
int count = length.apply("Lambda");
```

### 4.1. Cast không đồng nghĩa cung cấp type argument cho generic method

So sánh hai cách diễn đạt một danh sách rỗng:

```java
java.util.List<String> a =
        java.util.Collections.emptyList();

java.util.List<String> b =
        java.util.Collections.<String>emptyList();
```

Cả hai đều hợp lệ. Ở dòng thứ hai, `<String>` là **type witness** — type argument tường minh của phương thức generic — **không phải cast**. Java thường có thể suy luận `String` từ phép gán, nhưng đôi khi type witness giúp giải thích hoặc điều khiển suy luận generic tốt hơn.

Đừng thay type witness bằng một phép cast không an toàn vào `List<String>` chỉ để làm hết cảnh báo. Khi compiler đã có thông tin generic đúng, hãy dùng thông tin đó.

## 5. Ép kiểu tường minh của tham chiếu đối tượng: khác target typing

Cast đối tượng thông thường có dạng:

```java
Object value = "Java";
String text = (String) value;
System.out.println(text.length()); // 4
```

`value` có kiểu khai báo `Object`, nhưng đối tượng thực tế là `String`. Cast cho phép truy cập API của `String`. Với phép downcast như vậy, JVM có thể cần kiểm tra tương thích kiểu tại runtime.

Nếu không đúng kiểu thực tế:

```java
Object value = Integer.valueOf(7);

// Hợp lệ về cú pháp, nhưng ném ClassCastException khi chạy:
// String text = (String) value;
```

**Cast không biến `Integer` thành `String`.** Nó yêu cầu xem giá trị đã có như một kiểu tham chiếu khác và có thể thất bại.

### 5.1. Dùng `instanceof` trước khi downcast khi dữ liệu thực tế không chắc chắn

Kiểu viết dùng được từ Java 8:

```java
static void showText(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.toUpperCase(
                java.util.Locale.ROOT));
    } else {
        System.out.println("Không phải String");
    }
}
```

Đây là đoạn phương thức minh họa trong một lớp. Khi dự án dùng Java 16+, pattern matching cho `instanceof` cho phép viết ngắn hơn:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Cú pháp trên yêu cầu source level phù hợp, **không biên dịch với Java 8**. Quy tắc cast thông thường vẫn đúng; Java hiện đại có thêm cú pháp giảm nhu cầu cast thủ công ở một số trường hợp.

### 5.2. `(Type)` không tự động loại bỏ null

`(String) null` cho kết quả `null`, không ném `ClassCastException`. Nhưng gọi `((String) null).length()` sẽ ném `NullPointerException` do dereference đối tượng null. Khi ép kiểu dữ liệu đầu vào có thể null, phải định nghĩa rõ chính sách kiểm tra null.

### 5.3. Đối tượng không bị đổi runtime class

`Object text = "Java"; String s = (String) text;` không tạo một bản sao `String` mới. Cả `text` và `s` tham chiếu tới cùng giá trị chuỗi. Cast đối tượng **không phải phép parse**. Nếu muốn đổi nội dung chuỗi thành số, dùng `Integer.parseInt("42")` thay vì `(Integer) "42"`.

## 6. Cast kiểu số không thay thế suy luận kiểu generic

Java có phép ép kiểu số như:

```java
double amount = 9.9;
int whole = (int) amount; // 9: bỏ phần thập phân về phía 0
```

Phép cast số ở đây là **chuyển đổi giá trị**, có thể làm mất độ chính xác hoặc phạm vi giá trị. Nó khác việc cung cấp target type cho lambda/method reference.

Ví dụ `(int) 9.9` không giải quyết một lời gọi overload `Supplier`/`Callable`. Ngược lại, ép lambda thành `Supplier` không làm phép toán số bên trong an toàn hơn.

**Cảnh báo:** không dùng cast số để “sửa” lỗi nghiệp vụ về tiền tệ, làm tròn hoặc vượt phạm vi `int`. Dùng kiểu dữ liệu và quy tắc chuyển đổi phù hợp với hệ thống.

## 7. Cast với generic: không được coi cảnh báo unchecked là vô hại

Generic trong Java chịu ảnh hưởng của **type erasure**. JVM thường không thể kiểm tra đầy đủ tham số generic bên trong một `List<String>` như cách kiểm tra bản thân runtime class của `List`. Cast từ kiểu ít thông tin sang kiểu tham số hóa có thể tạo **unchecked warning**.

Ví dụ cố ý chứa vấn đề:

```java
java.util.List<?> unknown =
        java.util.Arrays.asList(1, 2);

// Có thể nhận unchecked cast warning; không bảo đảm
// các phần tử bên trong thật sự là String.
// java.util.List<String> strings =
//         (java.util.List<String>) unknown;
```

Một danh sách có thể chứa `Integer` dù bị gắn type `List<String>` bằng unchecked cast. Lỗi thường lộ ra **khi lấy phần tử và compiler sinh phép kiểm tra/cast phù hợp**:

```java
// Nếu dùng cast không an toàn ở trên, truy xuất như sau
// có thể ném ClassCastException khi đọc phần tử:
// String first = strings.get(0);
```

Thay vì cast mù quáng, hãy kiểm tra nguồn dữ liệu, sử dụng generic từ đầu hoặc chuyển từng phần tử một cách an toàn:

```java
java.util.List<?> input =
        java.util.Arrays.asList("A", "B");

java.util.List<String> output = new java.util.ArrayList<>();

for (Object item : input) {
    if (!(item instanceof String)) {
        throw new IllegalArgumentException("Expected String");
    }
    output.add((String) item);
}
```

Đây là một chuyển đổi có kiểm tra từng phần tử, không phải thao tác cast `List<?>` thành `List<String>`. Nó tạo danh sách mới chỉ chứa String khi đầu vào hợp lệ.

### 7.1. Vì sao `@SuppressWarnings("unchecked")` không phải giải pháp đầu tiên?

Annotation này chỉ che cảnh báo compiler tại nơi được áp dụng; nó **không** thêm kiểm tra runtime hay bảo đảm kiểu dữ liệu đúng. Chỉ dùng khi đã có chứng cứ và ranh giới tin cậy rõ ràng, đặt phạm vi annotation nhỏ nhất có thể và ghi giải thích tại code. Khi có thể thay bằng API generic an toàn, hãy ưu tiên API đó.

## 8. Phân biệt cast của toàn lambda với kiểu tham số lambda

Hai ví dụ:

```java
java.util.function.Predicate<String> a =
        (String text) -> !text.isEmpty();

java.util.function.Predicate<String> b =
        (java.util.function.Predicate<String>)
                (text -> !text.isEmpty());
```

Trong `a`, `(String text)` là **khai báo kiểu tường minh cho tham số lambda**. Nó không phải cast.

Trong `b`, `(Predicate<String>)` là **cast bao ngoài biểu thức lambda**, xác định target functional interface. Cả hai hợp lệ, nhưng giúp compiler theo hai cách khác nhau. Với vế trái đã ghi `Predicate<String>`, cả hai chi tiết tường minh đều không cần thiết trong ví dụ cơ bản.

Kiểu tham số lambda phải đồng bộ: không thể tùy tiện trộn tham số tường minh và suy luận ngầm trong cùng danh sách. Cú pháp `var` cho tham số lambda được bổ sung từ Java 11 và vẫn cần tuân theo quy tắc nhất quán; đây là tính năng khác với ép kiểu cả callback.

### 8.1. Cast không thể vượt qua checked exception của SAM

`Function<T,R>` không khai báo checked exception ở `apply`. Ví dụ giả định có phương thức `read(Path) throws IOException`:

```java
// KHÔNG BIÊN DỊCH nếu read(path) throws IOException:
// Function<Path, String> f =
//         (Function<Path, String>) (path -> read(path));
```

Dù có cast `Function<Path,String>`, thân lambda vẫn không được phép để `IOException` chưa xử lý thoát khỏi `Function.apply`. Cách đúng là xử lý ngoại lệ trong lambda, bọc nó phù hợp với ý nghĩa nghiệp vụ (ví dụ `UncheckedIOException` cho I/O), hoặc đổi hợp đồng API đích khi có quyền kiểm soát API.

**Cast cung cấp target type, không cấp quyền bỏ qua checked exception, return type hoặc số tham số.**

## 9. Intersection cast: nhiều interface nhưng vẫn chỉ có một SAM

Java cho phép một **intersection type** trong cast, ví dụ `(Runnable & java.io.Serializable)`, miễn tổ hợp kiểu đáp ứng các ràng buộc ngôn ngữ và kết quả thực sự xác định một functional interface.

```java
Runnable action =
        (Runnable & java.io.Serializable)
                () -> System.out.println("run");
```

Cast này chỉ rõ callback phải triển khai `Runnable` và marker interface `Serializable`. Nó khác với việc tạo hai phương thức abstract độc lập. `Runnable.run()` là hành vi chức năng duy nhất cần triển khai trong intersection trên.

**Lưu ý quan trọng:** khả năng đánh dấu lambda là serializable **không có nghĩa** nên lưu lambda như định dạng dữ liệu lâu dài. Việc serialize/deserialize lambda có ràng buộc về captured state, tương thích phiên bản, bảo mật và thay đổi code. Với cấu hình lâu dài hoặc giao tiếp giữa dịch vụ, nên lưu **dữ liệu và tên chiến lược** theo schema rõ ràng thay vì serialize implementation lambda.

Không dùng intersection cast khi chỉ cần một `Runnable` thường. Việc cố ép nhiều interface không liên quan với các SAM độc lập vào một lambda sẽ không tự tạo một đối tượng triển khai đủ mọi hành vi.

## 10. Chương trình Java hoàn chỉnh: cast rõ đích và an toàn dữ liệu

Chương trình sau minh họa chọn overload `Supplier`/`Callable` bằng cast, method reference cần target type, lambda cast, downcast có kiểm tra, cast sai bị phát hiện ở runtime và intersection cast. Mã **tương thích Java 8**, có thể biên dịch/chạy trên JDK 17+.

Tạo tệp **`ExplicitCastInferenceDemo.java`**:

```java
import java.io.Serializable;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class ExplicitCastInferenceDemo {

    static void execute(Supplier<String> supplier) {
        System.out.println("Supplier: " + supplier.get());
    }

    static void execute(Callable<String> callable)
            throws Exception {
        System.out.println("Callable: " + callable.call());
    }

    static void showText(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            System.out.println("Text length: " + text.length());
        } else {
            System.out.println("Not String");
        }
    }

    public static void main(String[] args) throws Exception {
        // Cast chọn đúng overload cần gọi.
        execute((Supplier<String>) () -> "ready");
        execute((Callable<String>) () -> "done");

        // Biến có kiểu đích: không cần cast.
        Function<String, Integer> length = String::length;
        System.out.println("Length: " + length.apply("Java"));

        // Cast trực tiếp cung cấp target type cho method reference.
        int count =
                ((Function<String, Integer>) String::length)
                        .apply("Lambda");
        System.out.println("Reference cast: " + count);

        Predicate<String> hasText =
                (Predicate<String>)
                        (s -> !s.trim().isEmpty());
        System.out.println("Predicate: "
                + hasText.test(" x "));

        showText("hello");
        showText(Integer.valueOf(7));

        Object value = "42";
        String text = (String) value;
        System.out.println("String cast: "
                + text.substring(1));

        Object wrong = Integer.valueOf(10);
        try {
            String impossible = (String) wrong;
            System.out.println(impossible);
        } catch (ClassCastException e) {
            System.out.println("Bad cast: ClassCastException");
        }

        Runnable action =
                (Runnable & Serializable)
                        () -> System.out.println("Action: run");
        action.run();

        Function<String, String> normalize =
                s -> s.trim().toUpperCase(Locale.ROOT);
        System.out.println("Normalize: "
                + normalize.apply(" java "));
    }
}
```

Biên dịch và chạy:

```bash
javac ExplicitCastInferenceDemo.java
java ExplicitCastInferenceDemo
```

**Stdout chính xác:**

```text
Supplier: ready
Callable: done
Length: 4
Reference cast: 6
Predicate: true
Text length: 5
Not String
String cast: 2
Bad cast: ClassCastException
Action: run
Normalize: JAVA
```

**Giải thích:**

1. `execute((Supplier<String>) () -> "ready")` gọi overload nhận `Supplier`. Dòng tiếp theo cast `Callable` chọn overload còn lại.
2. `String::length` được gán cho `Function<String,Integer>` nên compiler có đủ target type; `"Java"` có độ dài 4.
3. Trong `((Function<String,Integer>) String::length).apply("Lambda")`, cast cung cấp target type để gọi `apply` ngay; chuỗi `"Lambda"` dài 6 ký tự.
4. `hasText` là một predicate nhận `String`; chuỗi `" x "` sau `trim` không rỗng nên trả `true`.
5. `showText` chỉ cast khi `value instanceof String`, vì vậy `"hello"` cho 5 còn số nguyên 7 in `Not String`.
6. `(String) value` thành công với đối tượng `"42"`; `substring(1)` trả `"2"`. Một `Integer` không thể downcast thành `String`, nên ví dụ bắt đúng `ClassCastException`.
7. Intersection cast tạo callback tương thích `Runnable` và `Serializable`, nhưng chương trình chỉ chạy `run()`, không serialize callback.
8. Ví dụ `normalize` cuối cùng không cần cast: khi target type đã rõ, cách viết thông thường là đủ. `" java "` được chuẩn hóa thành `"JAVA"`.

Chương trình không dựa vào thông điệp ngoại lệ do JDK tự tạo; kết quả in ở nhánh `catch` là chuỗi cố định, nên stdout ổn định.

## 11. Bảng quyết định: khi nào cast là đúng công cụ?

| Tình huống | Có nên cast tường minh? | Giải thích |
| --- | --- | --- |
| `Function<String,Integer> f = String::length` | Thường **không** | Vế trái đã cung cấp target type |
| Hai overload `Supplier<String>` và `Callable<String>` đều nhận `() -> "x"` | **Có thể có** | Cast xác định overload muốn gọi |
| Muốn gọi `apply` trực tiếp trên method reference | **Có thể có** | Cast cung cấp target functional interface ngay trong biểu thức |
| Biến `Object` thực sự chứa một `String` nhưng cần API của `String` | **Có, khi đã xác minh kiểu** | Downcast có thể kiểm tra ở runtime |
| Dữ liệu đến từ API không tin cậy | **Không cast mù quáng** | Kiểm tra `instanceof`, xác thực hoặc chuyển đổi |
| `List<?>` muốn dùng thành `List<String>` | **Tránh unchecked cast** | Erasure không kiểm tra nội dung mọi phần tử |
| Muốn chỉ định kiểu cho generic `Collections.emptyList()` | Ưu tiên **type witness** khi cần | `Collections.<String>emptyList()` không phải cast |
| Lambda có return type/parameters không khớp interface | **Không** | Cast không biến biểu thức sai thành đúng |
| Lambda làm rò checked exception nhưng SAM không có `throws` | **Không** | Cần xử lý lỗi/hợp đồng khác |
| Muốn lambda vừa `Runnable` vừa `Serializable` | **Có thể dùng intersection cast** | Chỉ khi thực sự cần và thỏa SAM |
| Muốn tránh overload nhập nhằng do API tự thiết kế | **Ưu tiên sửa API** | Tên method khác nhau thường dễ đọc hơn nhiều cast |

## 12. Những lỗi dễ gặp

### Lỗi 1: Dùng cast để giấu một hợp đồng thiết kế yếu

Nếu phải viết `(Supplier<String>)` hoặc `(Callable<String>)` ở hầu hết lời gọi, có thể API có overload quá giống nhau. Cast giải quyết tức thời nhưng khiến caller khó bảo trì. Khi bạn kiểm soát API, phân biệt tên phương thức theo trách nhiệm giúp giảm lỗi.

### Lỗi 2: Ép kiểu một lambda sang interface không phải SAM tương thích

`(Object) (s -> s)` không biến `Object` thành functional interface; cast vào `Object` không cung cấp target type hợp lệ cho lambda. Cần cast vào **functional interface** thích hợp như `Function<String,String>` nếu hành vi thật sự khớp chữ ký.

### Lỗi 3: Tưởng cast biến đổi runtime object

`(String) Integer.valueOf(10)` không chuyển số 10 thành chuỗi `"10"`. Muốn chuyển đổi dữ liệu, dùng API chuyển đổi như `String.valueOf(10)`. Cast tham chiếu chỉ biểu đạt yêu cầu tương thích kiểu.

### Lỗi 4: Tưởng generics đã được kiểm tra nhờ cast

`(List<String>) unknown` có thể chỉ kiểm tra đối tượng là `List` ở runtime, **không xác minh mỗi phần tử là `String`**. Đừng bỏ qua unchecked warning bằng thói quen.

### Lỗi 5: Nhầm cast với khai báo kiểu tham số lambda

`(String s) -> s.length()` không phải cast; `(Function<String,Integer>) (s -> s.length())` mới là cast vào functional interface. Cả hai có thể bổ sung thông tin, nhưng ở vị trí cú pháp và mục đích khác nhau.

### Lỗi 6: Cast không cần thiết làm mã khó đọc

`Function<String,Integer> f = (Function<String,Integer>) String::length` lặp lại cùng một kiểu trong khi compiler đã biết target type. Hãy xóa cast khi nó không có giá trị bổ sung.

### Lỗi 7: Nghĩ cast loại bỏ ràng buộc checked exception

Dù đặt `(Function<Path,String>)` phía trước lambda, `Function.apply` vẫn không khai báo `IOException`. Hãy giải quyết ngoại lệ ở nơi có đủ thông tin hoặc thiết kế interface có `throws` phù hợp.

### Lỗi 8: Dùng `var` mà không có target type cho method reference

`var` cho biến cục bộ từ Java 10 không tự cung cấp kiểu đích cho lambda hoặc method reference trần:

```java
// KHÔNG BIÊN DỊCH:
// var f = String::length;

// Hợp lệ, Java 10+ vì initializer đã có kiểu nhờ cast:
var f = (Function<String, Integer>) String::length;
```

Ở ví dụ, `var` suy luận kiểu từ **biểu thức đã có target type do cast**, không tự suy ra target type của method reference. Với codebase cần tương thích Java 8, khai báo `Function<String,Integer> f = String::length;` thay vì `var`.

## 13. Checklist trước khi thêm cast

1. **Compiler đang thiếu thông tin gì?** Target type của lambda/method reference, overload phải chọn, hay kiểm tra downcast một đối tượng?
2. **Có thể dùng kiểu khai báo rõ ràng thay cast không?** Ví dụ `Supplier<String> s = ...; execute(s);`.
3. **Kiểu trong cast có thực sự là functional interface tương thích không?** Xác nhận số tham số, kiểu trả về và checked exception.
4. **Tại nơi gọi overload, cast có làm rõ ý định nghiệp vụ không?** Nếu API thường xuyên cần cast, cân nhắc đổi tên API.
5. **Nếu cast tham chiếu, kiểu thực tế có được xác thực không?** Cần tránh `ClassCastException` khó đoán.
6. **Nếu liên quan generic, có unchecked warning không?** Cân nhắc kiểm tra từng phần tử hoặc dùng API generic tốt hơn.
7. **Cast có làm mất thông tin kiểu hữu ích không?** Tránh đưa callback về `Object` nếu caller cần `apply`.
8. **Có thể dùng type witness thay cast cho generic method không?** Chọn công cụ đúng mục đích.
9. **Có dùng tính năng đúng source level không?** Java 8 hỗ trợ lambda/cast target typing; `var` local từ Java 10, pattern matching `instanceof` ổn định từ Java 16.
10. **Đã thử cả nhánh lỗi chưa?** Với downcast, test trường hợp sai kiểu; với overload, test đúng phương thức được chọn.

**Kết luận:** cast tường minh hữu ích khi nó **nói rõ kiểu đích của một biểu thức có thể phù hợp với nhiều functional interface**, đặc biệt để chọn overload cho lambda hoặc method reference. Nhưng khi context đã đủ, cast thường thừa. Với một giá trị tham chiếu thông thường, cast là một cơ chế kiểm tra/chuyển kiểu có giới hạn runtime và generic riêng. **Ép kiểu đúng làm sáng tỏ ý định; ép kiểu tùy tiện làm che lỗi thiết kế.**

## Tài liệu chuẩn tham khảo

- Java Language Specification, **`15.16 Cast Expressions** — https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.16
- Java Language Specification, **`15.27 Lambda Expressions** — https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27
- Java Language Specification, **`15.12 Method Invocation Expressions / Overload Resolution** — https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.12
- Java Language Specification, **`5.5 Casting Contexts** — https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html#jls-5.5
- Java SE 27 Specifications index — https://docs.oracle.com/en/java/javase/27/docs/specs/index.html
