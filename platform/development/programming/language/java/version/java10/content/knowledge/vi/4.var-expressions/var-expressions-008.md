# Biểu thức khởi tạo được xử lý không có ngữ cảnh kiểu của vế trái trong `var`

> **Phạm vi:** Đây là quy tắc cốt lõi của suy luận kiểu biến cục bộ (`var`), được giới thiệu ở Java 10 và vẫn còn hiệu lực trên JDK hiện đại. Bài dùng kiến thức còn áp dụng trong code Java hiện nay, không yêu cầu cài JDK 10 hay dựa vào tính năng cũ đã bị loại bỏ.

## 1. Mục tiêu và quy tắc trọng tâm

Sau bài này, bạn có thể giải thích và dự đoán kiểu được compiler chọn khi khai báo `var`, nhất là với generic method, toán tử diamond `<>`, lambda, method reference, mảng và biểu thức điều kiện.

**Quy tắc:** Với khai báo như `var x = initializer;`, compiler tìm kiểu của biểu thức `initializer` khi coi biểu thức đó là **standalone expression** (biểu thức độc lập), không nhận một **target type** từ phía khai báo biến. Sau đó, compiler dùng kiểu suy ra để xác lập **kiểu tĩnh** của `x`. Quy tắc được định nghĩa ở Java Language Specification (JLS), `14.4.1, và phần thiết kế của OpenJDK JEP 286.

So sánh hai khai báo:

```java
List<String> names = java.util.Collections.emptyList();
var names2 = java.util.Collections.emptyList();
```

Hai dòng này dùng cùng phương thức generic `Collections.emptyList()`, nhưng **khác ngữ cảnh kiểu**:

- Ở dòng đầu, `List<String>` bên trái cung cấp target type cho invocation, nên tham số kiểu `T` của `emptyList()` được suy ra là `String`; biến có kiểu `List<String>`.
- Ở dòng thứ hai, `var` không cung cấp target type bên trái. Invocation không có tham số đầu vào để suy luận `T`, nên compiler chọn `Object` theo giới hạn của tham số kiểu; biến có kiểu `List<Object>`.
- Cả hai danh sách đều rỗng. Sự khác nhau thể hiện ở **khả năng kiểm tra kiểu khi biên dịch**, không phải khác biệt in ra màn hình lúc chạy.

Không nên hiểu “không có target type” là **mọi biểu thức con đều mất ngữ cảnh kiểu**. Một lời gọi phương thức, phép ép kiểu hoặc một tham số đã có kiểu vẫn có thể cung cấp target type cho **biểu thức con**; xem ví dụ `stream.map(String::length)` ở phần 5.

## 2. Phân biệt target typing với kiểu của biến sau suy luận

### 2.1. Khai báo tường minh: vế trái giúp suy luận generic

```java
java.util.List<String> a = new java.util.ArrayList<>();
java.util.List<Integer> b = java.util.Collections.emptyList();
```

Với `a`, vế trái `List<String>` hướng việc suy luận type argument cho toán tử diamond thành `String`. Với `b`, vế trái hướng suy luận tham số kiểu phương thức generic `emptyList()` thành `Integer`.

### 2.2. Khai báo `var`: vế trái không cung cấp target type

```java
var a = new java.util.ArrayList<>();         // ArrayList<Object>
var b = java.util.Collections.emptyList();    // List<Object>
```

`var` không “đọc trước” các lệnh sẽ dùng biến ở phía sau để đoán loại phần tử. Ví dụ thêm chuỗi vào `a` sau khai báo **không biến** `a` thành `ArrayList<String>`. Nó vẫn là `ArrayList<Object>` và có thể nhận cả `String` lẫn `Integer`.

```java
var items = new java.util.ArrayList<>();
items.add("Java");
items.add(10);   // Hợp lệ: cả String và Integer đều là Object.
```

Trong dự án thật, cần chủ ý khai báo kiểu phần tử thay vì để compiler chọn `Object` ngoài ý muốn.

### 2.3. Cấp thêm thông tin kiểu ở đúng nơi

Ba cách thông dụng:

```java
// Cách A: chỉ rõ kiểu phần tử ở constructor.
var stringsA = new java.util.ArrayList<String>();

// Cách B: truyền đối số có kiểu vào constructor.
var stringsB = new java.util.ArrayList<>(java.util.List.of("A", "B"));

// Cách C: dùng khai báo tường minh khi cần target typing.
java.util.List<String> stringsC = new java.util.ArrayList<>();
```

- `stringsA` và `stringsB` có kiểu tĩnh `ArrayList<String>`, vì compiler biết `String` từ **vế phải**.
- `stringsC` có kiểu khai báo `List<String>`. Đây cũng là cách hữu ích khi muốn code chỉ phụ thuộc vào giao diện `List` thay vì lớp cài đặt.
- Với generic method không có thông tin từ đối số, có thể chỉ rõ type witness: `var words = Collections.<String>emptyList();` suy ra `List<String>`.

**Chú ý:** `var` không có nghĩa là “kiểu bên trái sẽ trở thành interface phù hợp nhất”. Ví dụ `var list = new ArrayList<String>();` có kiểu tĩnh `ArrayList<String>`, còn `List<String> list = new ArrayList<>();` có kiểu tĩnh `List<String>`. Chọn khai báo rõ kiểu khi muốn duy trì abstraction ổn định.

## 3. Thực hành hoàn chỉnh trên JDK hiện đại

Sử dụng JDK 21 hoặc JDK 25 **nếu bản phân phối bạn cài đặt vẫn đang được nhà cung cấp hỗ trợ và cập nhật bản vá**. Các API và cú pháp minh họa có thể chạy từ Java 10 trở lên; không cần chuyển về JDK 10 đã hết vòng đời sử dụng thông thường.

Kiểm tra trình biên dịch và máy ảo:

```bash
javac -version
java -version
```

Tạo tệp `VarInitializerContext.java` với toàn bộ nội dung dưới đây:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

public class VarInitializerContext {
    public static void main(String[] args) {
        // var không cung cấp target type cho biểu thức new.
        var mixed = new ArrayList<>(); // ArrayList<Object>
        mixed.add("Java");
        mixed.add(10);
        System.out.println("Diamond without target: " + mixed);

        // Kiểu rõ ở bên trái và kiểu có thể suy ra từ đối số constructor.
        List<String> fromLeft = new ArrayList<>();
        fromLeft.add("Lan");
        var fromArgument = new ArrayList<>(List.of("A", "B"));
        fromArgument.add("C");
        System.out.println("Explicit left type: " + fromLeft);
        System.out.println("Argument types: " + fromArgument);

        // Invocation generic không nhận target từ var.
        var unknown = Collections.emptyList();           // List<Object>
        List<String> fromTarget = Collections.emptyList();
        var fromWitness = Collections.<String>emptyList();
        List<Object> objectProof = unknown; // Kiểm tra kiểu tĩnh.
        System.out.println("Empty sizes: " + objectProof.size()
                + "/" + fromTarget.size() + "/" + fromWitness.size());

        // Lambda/method reference cần target type rõ ràng.
        Function<String, Integer> direct = String::length;
        var castTarget = (Function<String, Integer>) String::length;
        System.out.println("Method reference: "
                + direct.apply("Java") + "/" + castTarget.apply("Hi"));

        // Method reference ở bên trong map() có target type do map cấp.
        var lengths = List.of("A", "BBB").stream()
                .map(String::length)
                .collect(Collectors.toList());
        System.out.println("Nested target: " + lengths);

        // Mảng phải có biểu thức tạo mảng đầy đủ ở vế phải.
        var letters = new String[] {"A", "B"};
        System.out.println("Array length: " + letters.length);

        // Biểu thức điều kiện số tự xác định kiểu theo numeric promotion.
        var number = true ? 1 : 2L; // long
        long asLong = number;
        System.out.println("Conditional: " + asLong);

        // null đơn lẻ không đủ kiểu; cast mang lại kiểu String.
        var nullable = (String) null;
        System.out.println("Typed null: " + (nullable == null));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac VarInitializerContext.java
java VarInitializerContext
```

### Output chính xác

```text
Diamond without target: [Java, 10]
Explicit left type: [Lan]
Argument types: [A, B, C]
Empty sizes: 0/0/0
Method reference: 4/2
Nested target: [1, 3]
Array length: 2
Conditional: 1
Typed null: true
```

### Giải thích theo từng nhóm

1. **Diamond không có target:** `new ArrayList<>()` không có đối số giúp suy luận kiểu `E` và cũng không được `var` truyền target vào, nên `E` được suy ra `Object`. Vì vậy `mixed.add("Java")` và `mixed.add(10)` đều biên dịch.
2. **Khai báo kiểu rõ:** `List<String> fromLeft` cung cấp target `String` cho toán tử diamond. Với `fromArgument`, `List.of("A", "B")` đã mang thông tin `String`, nên constructor suy luận `ArrayList<String>` dù dùng `var`.
3. **Generic method:** `unknown` có kiểu `List<Object>`. Dòng `List<Object> objectProof = unknown;` thể hiện kết quả kiểm tra kiểu lúc biên dịch. `fromTarget` và `fromWitness` là `List<String>` vì có target kiểu hoặc type witness. Việc các list đều có `size() == 0` không tiết lộ generic type ở runtime.
4. **Method reference:** `String::length` không có kiểu độc lập; `Function<String,Integer>` bên trái hoặc phép cast cung cấp functional interface tương ứng. Các lời gọi với `"Java"` và `"Hi"` trả `4` và `2`.
5. **Biểu thức con:** `map(String::length)` hợp lệ dù kết quả cuối cùng gán cho `var lengths`. Target type của method reference được xác lập từ **tham số `map`**; kiểu đầu ra `List<Integer>` được suy luận từ chuỗi xử lý Stream.
6. **Array và null:** `new String[]{...}` là biểu thức tạo mảng có kiểu `String[]`. `(String) null` có kiểu `String`, nên `var nullable` hợp lệ, dù giá trị thực là `null`.
7. **Conditional:** Toán tử `?:` với hai nhánh số `int` và `long` dùng numeric promotion để có kiểu `long`. `var number` nhận kiểu đó, không có cơ chế suy luận kiểu ngược từ các lệnh sau.

## 4. Các biểu thức không tự có kiểu đích: lỗi biên dịch

Những đoạn sau **cố ý sai, chỉ dùng để phân tích**. Không thêm vào chương trình `VarInitializerContext.java` ở phần trước.

### 4.1. Lambda expression

```java
var converter = text -> text.length(); // SAI: lambda cần target functional interface.
var supplier = () -> "hello";          // SAI: không biết là Supplier, Callable, ...
```

Dù body lambda trả về một `String` hay `int`, compiler vẫn cần biết **functional interface** có phương thức trừu tượng với chữ ký tương ứng. Sửa bằng khai báo hoặc cast có kiểu:

```java
java.util.function.Function<String, Integer> converter = text -> text.length();
var converter2 = (java.util.function.Function<String, Integer>)
        (text -> text.length());
```

Lambda phía trong **phép cast** có target type là `Function<String,Integer>`. Biến cục bộ `converter2` được suy luận từ **kiểu của toàn bộ biểu thức cast**. Đây là trường hợp hợp lệ vì không yêu cầu `var` trực tiếp đặt target type cho lambda.

### 4.2. Method reference

```java
var lengthFn = String::length; // SAI: method reference cần target functional interface.
```

Sửa bằng:

```java
java.util.function.Function<String, Integer> lengthFn = String::length;
var lengthFn2 = (java.util.function.Function<String, Integer>) String::length;
```

Biểu thức `String::length` tự nó không quyết định phải trở thành `Function<String,Integer>`, `ToIntFunction<String>` hay interface chức năng khác. Compiler cần target type để kiểm tra chữ ký và quy tắc tương thích.

### 4.3. Array initializer dạng rút gọn

```java
var letters = {"A", "B"}; // SAI: dạng {...} cần loại mảng từ ngữ cảnh.
```

Sửa bằng một trong hai cách:

```java
String[] letters = {"A", "B"};           // Có kiểu mảng tường minh ở vế trái.
var letters2 = new String[] {"A", "B"};  // Vế phải là biểu thức tạo mảng có kiểu.
```

Không nhầm kiểu mảng `String[]` với generic collection; ở đây sự khác biệt đến từ ngữ pháp và quy tắc xử lý initializer của Java.

### 4.4. `null` không mang kiểu cụ thể

```java
var value = null; // SAI: initializer có null type; không suy được kiểu biến.
```

Sửa bằng kiểu khai báo tường minh hoặc cast có chủ đích:

```java
String value = null;
var value2 = (String) null; // Hợp lệ, nhưng phải có lý do thực tế.
```

Không dùng cast chỉ để thỏa cú pháp khi loại dữ liệu chưa được xác định. Trong thiết kế code, nên giữ khai báo kiểu tường minh hoặc khởi tạo bằng giá trị có ngữ nghĩa rõ ràng.

### 4.5. `var` cũng không dựa vào các lệnh sử dụng trong tương lai

```java
var values = new java.util.ArrayList<>(); // ArrayList<Object>
values.add("A");                          // Không làm kiểu đổi thành ArrayList<String>.
java.util.List<String> strings = values;  // SAI: List<Object> không gán cho List<String>.
```

Generic type arguments là bất biến (*invariant*) trong Java: `List<Object>` không phải subtype của `List<String>`. Sửa ngay ở khai báo đầu tiên bằng `new ArrayList<String>()` hoặc `List<String> values = new ArrayList<>()`, tùy trường hợp sử dụng.

## 5. Tinh tế quan trọng: vế phải là standalone, nhưng biểu thức con vẫn có target

Đôi khi có nhận định sai rằng “đã dùng `var` thì bên trong initializer không thể có lambda/method reference hoặc generic inference”. Đây là cách hiểu quá rộng.

Hãy tách **biểu thức cấp ngoài** và **ngữ cảnh của biểu thức con**:

```java
var lengths = java.util.List.of("Hi", "Java")
        .stream()
        .map(String::length)
        .collect(java.util.stream.Collectors.toList());
```

- Cấp ngoài là lời gọi `collect(...)`; toàn bộ initializer được xem là standalone vì vế trái là `var`.
- Ở bên trong, `Stream.map` đòi tham số kiểu `Function<? super String,? extends R>`. Chữ ký của `map` cung cấp ngữ cảnh để compiler suy luận và kiểm tra `String::length`.
- `Stream<String>` và method reference cung cấp thông tin suy luận `R=Integer`; lời gọi collector cho `List<Integer>`.
- Biến `lengths` được suy luận là `List<Integer>`. Không cần phải viết `List<Integer>` bên trái chỉ để `map` hoạt động.

Tương tự, lambda bên trong một phép gọi nhận tham số `Predicate<String>` hoặc `Function<String,Integer>` có thể hợp lệ nếu compiler biết rõ kiểu tham số phương thức đó. **Quy tắc thiếu target type áp dụng cho toàn biểu thức khởi tạo của `var`**, không xóa bỏ các ngữ cảnh suy luận phát sinh bên trong chính biểu thức ấy.

Một ví dụ rõ ràng hơn:

```java
var message = java.util.Optional.of("abc")
        .map(s -> s.toUpperCase())
        .orElse("DEFAULT"); // String, vì Optional.map có target type cho lambda.
```

`message` được suy luận là `String`. Lambda `s -> s.toUpperCase()` nhận target kiểu từ phương thức `map`; `var` không phải nguồn target kiểu đó.

## 6. Bảng quyết định nhanh

| Biểu thức khởi tạo | Kiểu tĩnh/kết quả | Lý do |
| --- | --- | --- |
| `var n = 10;` | `int` | Kiểu của literal xác định được độc lập. |
| `var title = "Java";` | `String` | Literal chuỗi có kiểu `String`. |
| `var list = new ArrayList<>();` | `ArrayList<Object>` | Diamond không nhận target từ `var`; không có đối số hạn chế `E`. |
| `List<String> list = new ArrayList<>();` | `List<String>` | Vế trái khai báo rõ loại phần tử. |
| `var list = new ArrayList<>(List.of("A"));` | `ArrayList<String>` | Đối số constructor cung cấp thông tin `String`. |
| `var empty = Collections.emptyList();` | `List<Object>` | Generic method không có đối số hoặc target để xác định `T`. |
| `var empty = Collections.<String>emptyList();` | `List<String>` | Type witness `<String>` cung cấp `T`. |
| `var f = s -> s.length();` | **Lỗi** | Lambda không có target functional interface. |
| `var f = String::length;` | **Lỗi** | Method reference không có target functional interface. |
| `var f = (Function<String,Integer>) String::length;` | `Function<String,Integer>` | Phép cast cung cấp target type. |
| `var array = {"A", "B"};` | **Lỗi** | Array initializer rút gọn thiếu kiểu mảng. |
| `var array = new String[]{"A","B"};` | `String[]` | Biểu thức tạo mảng có kiểu rõ. |
| `var nothing = null;` | **Lỗi** | Kiểu `null` không thể dùng làm kiểu biến. |
| `var maybe = (String) null;` | `String` | Cast cung cấp kiểu cho toàn biểu thức. |
| `var x = true ? 1 : 2L;` | `long` | Numeric conditional tự xác định kiểu bằng numeric promotion. |

Các dòng ghi **Lỗi** là ví dụ được cố ý viết sai; không ghép chúng vào cùng tệp Java đang chạy.

## 7. Các bẫy dễ gặp khi refactor từ kiểu tường minh sang `var`

### Bẫy A — Refactor thay đổi generic type âm thầm

**Trước:**

```java
java.util.List<String> tags = new java.util.ArrayList<>();
tags.add("java");
```

**Sau khi thay trực tiếp `List<String>` bằng `var`:**

```java
var tags = new java.util.ArrayList<>();
tags.add("java");
```

Đoạn sau biên dịch nhưng biến có kiểu `ArrayList<Object>`, không còn hợp đồng `List<String>`. Hệ quả có thể là mất kiểm tra kiểu ở compile time hoặc lỗi khi chuyển dữ liệu sang API đòi `List<String>`. Cách sửa tối thiểu là `var tags = new ArrayList<String>();`; nếu muốn giới hạn biến theo interface `List`, giữ nguyên khai báo kiểu tường minh.

### Bẫy B — Runtime không cho biết type argument generic

`ArrayList<Object>` và `ArrayList<String>` thường trông giống nhau khi debug hoặc gọi `getClass()`, vì generic type argument không được lưu theo cách giúp truy xuất trực tiếp từ instance ở runtime (type erasure). Đừng dùng `getClass().getSimpleName()` để “chứng minh” loại phần tử của một generic list; hãy đọc kiểu tĩnh trong IDE hoặc dùng một phép gán kiểm tra bằng compiler.

### Bẫy C — Nhầm `var` với kiểu động

`var name = "A";` tạo biến kiểu tĩnh `String`. `name = 123;` **không biên dịch**. Việc thiếu target type từ vế trái **chỉ ảnh hưởng giai đoạn chọn kiểu ban đầu**, không cho phép biến đổi kiểu của biến về sau.

### Bẫy D — Thông tin kiểu bị thiếu trong generic factory

`var empty = Collections.emptyList();` thường không phản ánh mục đích nghiệp vụ nếu sau đó cần `List<Customer>` hoặc `List<Order>`. Viết `Collections.<Customer>emptyList()` hoặc `List<Customer> empty = Collections.emptyList();` khi loại phần tử mang ý nghĩa quan trọng. Trong ví dụ này, `Customer` và `Order` là tên lớp minh họa, không phải lớp có sẵn trong JDK.

### Bẫy E — Lạm dụng ép kiểu lambda

Cast sang `Function<...>` là cách minh họa target typing tốt, nhưng nhiều phép ép kiểu dài có thể làm code khó đọc. Trong code thật, một khai báo tường minh như `Function<String,Integer> length = String::length;` thường ngắn gọn và rõ ý hơn.

## 8. Bài tập tự luyện có đáp án kiểm tra

**Bài 1 — Dự đoán kiểu:** Với các khai báo sau, viết kiểu tĩnh của `a`, `b` và `c`:

```java
var a = new java.util.ArrayList<>();
var b = new java.util.ArrayList<>(java.util.List.of(2, 4));
var c = java.util.Collections.<String>emptyList();
```

**Đáp án:** `a` là `ArrayList<Object>`, `b` là `ArrayList<Integer>`, `c` là `List<String>`. Thử `b.add("x")` sẽ bị compiler từ chối, còn `a.add("x")` không lỗi kiểu.

**Bài 2 — Sửa ba lỗi thiếu target:** Những dòng nào không biên dịch?

```java
var supplier = () -> 5;
var chars = {'x', 'y'};
var ref = String::length;
```

**Đáp án:** Cả ba đều không biên dịch. Hãy sửa thành:

```java
java.util.function.Supplier<Integer> supplier = () -> 5;
var chars = new char[] {'x', 'y'};
java.util.function.Function<String, Integer> ref = String::length;
```

**Bài 3 — Generic method có và không có target:** Giải thích vì sao dòng sau không hợp lệ:

```java
var data = java.util.Collections.emptyList();
java.util.List<String> strings = data; // Lỗi: List<Object> không gán cho List<String>.
```

**Đáp án:** `data` đã có kiểu `List<Object>` ngay sau khai báo. Sửa thành `List<String> data = Collections.emptyList();` hoặc `var data = Collections.<String>emptyList();`.

**Bài 4 — Target bên trong biểu thức:** Giải thích vì sao đoạn sau biên dịch được dù có lambda và `var`:

```java
var values = java.util.List.of("a", "bb").stream()
        .map(s -> s.length())
        .collect(java.util.stream.Collectors.toList());
System.out.println(values); // [1, 2]
```

**Đáp án:** `map` cấp ngữ cảnh `Function` cho lambda. Kết quả `List<Integer>` của `collect` được dùng để suy luận kiểu biến `values`. Đây là method call chứa lambda ở tham số, không phải lambda trực tiếp làm initializer của `var`.

**Bài 5 — Refactor an toàn:** Thay `List<String> ids = new ArrayList<>();` bằng một khai báo `var` mà vẫn giữ được `String` làm type argument. Hai câu trả lời đúng gồm `var ids = new ArrayList<String>();` và `var ids = new ArrayList<>(List.<String>of());`. Giải thích phần nào của vế phải giúp compiler biết `String`.

### Checklist tự kiểm tra

- [ ] Phân biệt **target type từ vế trái** với kiểu tĩnh suy ra cho biến `var`.
- [ ] Dự đoán đúng `ArrayList<Object>` với `var x = new ArrayList<>()` và `List<Object>` với `var x = Collections.emptyList()`.
- [ ] Giải thích vì sao lambda, method reference hoặc array initializer rút gọn không thể trực tiếp làm initializer của `var`.
- [ ] Sửa được lỗi bằng khai báo kiểu tường minh, type witness, đối số có kiểu hoặc phép cast phù hợp.
- [ ] Nhận ra một biểu thức con vẫn có target type từ chữ ký phương thức như `Stream.map(...)`.
- [ ] Chạy chương trình `VarInitializerContext.java` và đối chiếu chính xác chín dòng output.
- [ ] Khi refactor, kiểm tra lại generic type; không giả định compiler suy luận kiểu từ các lệnh dùng biến sau khai báo.

## 9. Áp dụng trong dự án

Dùng `var` khi initializer cho thấy rõ kiểu thực tế (ví dụ `var request = new HttpRequest(...)` trong dự án có class phù hợp, hoặc `var names = List.of("A", "B")`). Giữ khai báo tường minh hoặc thêm type argument khi kết quả generic không thể xác định loại phần tử từ vế phải. Đặc biệt cẩn trọng với `new ArrayList<>()`, `Collections.emptyList()`, `Optional.empty()` và các factory generic không nhận đối số: nếu không có target type hoặc type witness, chúng có thể suy ra `Object`.

Không cần dựa vào hành vi lỗi thời để hiểu quy tắc này. Nó là một phần của Java Language Specification hiện đại và được compiler của các JDK còn được hỗ trợ tuân thủ.

## Tài liệu chuẩn

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): nguyên tắc initializer không có target type và giới hạn của biểu thức đa hình.
- [Java Language Specification — `14.4 Local Variable Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.4): biểu thức khởi tạo của `var` được xử lý như standalone expression.
- [OpenJDK FAQ — Local Variable Type Inference](https://cr.openjdk.org/~briangoetz/jep-286/lvti-faq.html): giải thích diamond, array initializer và cách suy luận kiểu.
- [dev.java — Type Inference](https://dev.java/learn/language/fp/generics/type-inference/): target typing cho generic và lambda trong lời gọi phương thức.