# `var` và lựa chọn phương thức nạp chồng (method overloading) trong Java 10

> Bài này giải thích cách **kiểu tĩnh suy luận bởi `var`** ảnh hưởng đến việc Java chọn phương thức nạp chồng, đặc biệt khi kết hợp với **generics**, `<>` (diamond), boxing/unboxing và kiểu dữ liệu của đối số. Các quy tắc vẫn được dùng trên JDK hiện đại; không cần cài đặt Java 10 đã hết vòng đời.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **suy luận kiểu biến cục bộ** `var` với **overload resolution** (quyết định gọi overload nào).
2. Dự đoán overload được chọn dựa trên **kiểu tĩnh của biểu thức đối số**, kể cả khi đối tượng thực tế lúc chạy thuộc lớp con khác.
3. Giải thích vì sao `var items = new ArrayList<>();` và `List<String> items = new ArrayList<>();` có thể dẫn tới lựa chọn overload khác nhau.
4. Phân biệt biểu thức `new ArrayList<>()` truyền **trực tiếp** vào phương thức với việc lưu nó qua `var` trước khi truyền.
5. Phân tích thứ tự áp dụng widening, boxing/unboxing, varargs, mức độ đặc hiệu (*most specific*), generic inference và lỗi mơ hồ.
6. Viết overload không gặp lỗi xung đột chữ ký sau khi xóa kiểu generic (*type erasure*) và kiểm chứng bằng chương trình chạy được.

## 2. Hai quyết định của compiler cần tách riêng

### 2.1. `var` xác định kiểu của biến ngay lúc khai báo

Từ Java 10, `var` dùng cho các khai báo biến cục bộ được phép suy luận kiểu từ **initializer**. Đây là suy luận ở **thời điểm biên dịch**, không phải kiểu động.

```java
var text = "Java";                   // String
var count = 10;                      // int
var boxed = Integer.valueOf(10);    // Integer
var list = new java.util.ArrayList<>(); // ArrayList<Object>
```

Sau khai báo, compiler xử lý `text` như một biến `String`, `count` như `int` và `list` như `ArrayList<Object>`. Biến không thay đổi kiểu theo những phép gán tiếp theo hoặc theo cách nó được sử dụng.

Với `var`, biểu thức initializer ở cấp ngoài được xét như **standalone expression**, không nhận target type từ vế trái. Với `new ArrayList<>()` không có đối số, tham số generic `E` thường được suy ra thành `Object`; nếu muốn `String`, viết rõ `new ArrayList<String>()` hoặc cung cấp đối số có kiểu.

### 2.2. Overload resolution dùng kiểu của đối số tại vị trí gọi

Overloading là nhiều phương thức có **cùng tên nhưng danh sách tham số khác nhau**. Khi biên dịch một lời gọi, compiler tìm các phương thức áp dụng được và chọn phương thức đặc hiệu nhất trong giai đoạn phù hợp theo Java Language Specification (JLS `15.12.2).

```java
static String display(Object x) { return "Object"; }
static String display(String x) { return "String"; }
```

Đoạn sau nằm **trong một phương thức**:

```java
var message = "Hello";  // String
Object general = message;
System.out.println(display(message)); // String
System.out.println(display(general)); // Object
```

Cả hai biến cùng tham chiếu đến một đối tượng chuỗi tại runtime, nhưng `display(message)` có đối số kiểu tĩnh `String`, còn `display(general)` có đối số kiểu tĩnh `Object`. Compiler quyết định chữ ký overload ở **compile time**. Việc cùng trỏ tới một đối tượng lúc chạy không khiến Java chọn lại overload.

**Kết luận quan trọng:** `var` có thể ảnh hưởng **gián tiếp** đến overload qua kiểu tĩnh được suy luận cho biến. Bản thân từ khóa `var` không tạo một quy tắc chọn overload đặc biệt.

## 3. Chương trình thực hành đầy đủ (JDK được hỗ trợ)

Hãy dùng một bản phân phối **JDK LTS hiện vẫn được nhà cung cấp hỗ trợ và cập nhật bản vá**, chẳng hạn bản JDK 21/25 LTS phù hợp chính sách dự án. Những khả năng dùng trong ví dụ đã có từ Java 10 hoặc sớm hơn; bài không yêu cầu chạy một JDK 10 cũ.

Kiểm tra terminal:

```bash
java -version
javac -version
```

Tạo tệp **`OverloadVarLab.java`** và nhập nguyên chương trình dưới đây:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

public class OverloadVarLab {
    static String pick(Object x) { return "Object"; }
    static String pick(String x) { return "String"; }

    static String number(int n) { return "int"; }
    static String number(long n) { return "long"; }
    static String number(Integer n) { return "Integer"; }

    static String widenOrBox(long n) { return "long"; }
    static String widenOrBox(Integer n) { return "Integer"; }

    // Hợp lệ: erasure của hai tham số là List và Collection.
    static String route(List<String> items) { return "List<String>"; }
    static String route(Collection<?> items) { return "Collection<?>"; }

    // Return type không quyết định overload được chọn.
    static String value(Object x) { return "Object"; }
    static Integer value(String x) { return 7; }

    static String which(Object x) { return "Object"; }
    static String which(String x) { return "String"; }
    static String which(Integer x) { return "Integer"; }

    public static void main(String[] args) {
        var name = "Java";
        Object asObject = name;

        System.out.println("pick(name): " + pick(name));
        System.out.println("pick(asObject): " + pick(asObject));

        var primitive = 10;
        var boxed = Integer.valueOf(10);
        var wide = 10L;
        System.out.println("number: " + number(primitive) + ", "
                + number(boxed) + ", " + number(wide));
        System.out.println("widenOrBox: " + widenOrBox(primitive)
                + ", " + widenOrBox(boxed));

        var guessed = new ArrayList<>();           // ArrayList<Object>
        var empty = Collections.emptyList();       // List<Object>
        List<String> typed = new ArrayList<>();
        var witness = Collections.<String>emptyList();
        var fromArgs = new ArrayList<>(List.of("A", "B"));

        System.out.println("route(guessed): " + route(guessed));
        System.out.println("route(empty): " + route(empty));
        System.out.println("route(typed): " + route(typed));
        System.out.println("route(witness): " + route(witness));
        System.out.println("route(fromArgs): " + route(fromArgs));
        System.out.println("route(new ArrayList<>()): "
                + route(new ArrayList<>()));

        var chosen = value("abc");
        System.out.println("value(\"abc\") type/value: "
                + chosen.getClass().getSimpleName() + "/" + chosen);

        var typedNull = (String) null;
        Object objectNull = typedNull;
        System.out.println("which(typedNull): " + which(typedNull));
        System.out.println("which(objectNull): " + which(objectNull));
    }
}
```

Trong thư mục chứa tệp, chạy:

```bash
javac OverloadVarLab.java
java OverloadVarLab
```

`javac` tạo tệp bytecode `OverloadVarLab.class`; `java` chạy bằng **tên lớp**, không thêm đuôi `.class`. Không cần Maven, Gradle hay thư viện ngoài.

### Output chuẩn

```text
pick(name): String
pick(asObject): Object
number: int, Integer, long
widenOrBox: long, Integer
route(guessed): Collection<?>
route(empty): Collection<?>
route(typed): List<String>
route(witness): List<String>
route(fromArgs): List<String>
route(new ArrayList<>()): List<String>
value("abc") type/value: Integer/7
which(typedNull): String
which(objectNull): Object
```

Chương trình chỉ in tên overload được chọn hoặc giá trị xác định; nó không in các collection có thứ tự duyệt không ổn định. Mọi dòng output đều dựa trên kiểu tĩnh và định nghĩa phương thức cụ thể trong mã.

## 4. Phân tích những overload trong lab

### 4.1. `pick(String)` và `pick(Object)`

`name` có kiểu suy luận `String`, nên cả `pick(Object)` lẫn `pick(String)` có thể nhận nó, nhưng `String` đặc hiệu hơn `Object`: gọi `pick(String)`.

`asObject` được khai báo `Object` dù chứa một `String`. Đối số kiểu tĩnh `Object` không thể được chuyển ngầm thành `String`, nên chỉ overload `pick(Object)` áp dụng được.

Có thể kiểm chứng cùng quy tắc bằng:

```java
// Các dòng này đặt bên trong một phương thức.
String s = "A";
Object o = s;
pick(s);         // pick(String)
pick(o);         // pick(Object)
pick((String)o); // pick(String), sau khi ép kiểu đúng và hợp lệ.
```

Ép kiểu có thể thay đổi overload compiler chọn, nhưng ép kiểu sai ở runtime có thể ném `ClassCastException`. Không ép kiểu chỉ nhằm “thắng” một overload khi không chắc dữ liệu tương thích.

### 4.2. Primitive, wrapper, widening và boxing

Ba overload `number(int)`, `number(long)`, `number(Integer)` minh họa những kiểu chuyển đổi quan trọng:

| Biến | Kiểu tĩnh | Overload `number(...)` | Vì sao |
| --- | --- | --- | --- |
| `var primitive = 10;` | `int` | `number(int)` | Khớp chính xác `int`. |
| `var boxed = Integer.valueOf(10);` | `Integer` | `number(Integer)` | Khớp chính xác kiểu tham chiếu. |
| `var wide = 10L;` | `long` | `number(long)` | Khớp chính xác `long`. |

Tình huống `widenOrBox` tinh tế hơn vì chỉ có hai overload `long` và `Integer`. Với đối số `int`, phương thức `widenOrBox(long)` áp dụng bằng *primitive widening* (`int` → `long`) ngay ở giai đoạn strict; boxing (`int` → `Integer`) chỉ xét ở giai đoạn sau nếu không có phương thức phù hợp ở giai đoạn strict. Vì thế `widenOrBox(primitive)` chọn `long`.

Với đối số đã là `Integer`, `widenOrBox(Integer)` khớp trực tiếp nên được chọn trước khi cần unboxing rồi widening. Không có quy tắc “luôn ưu tiên overload có wrapper” hoặc “luôn ưu tiên overload có primitive”.

**Thứ tự khái quát của overload resolution** theo JLS:

1. Tìm overload áp dụng theo *strict invocation*: cho phép identity, primitive widening, reference widening và một số chuyển đổi tương ứng; chưa dùng boxing/unboxing hay gọi varargs theo dạng biến độ dài.
2. Nếu chưa có overload áp dụng, tìm tiếp theo *loose invocation* (cho phép thêm boxing/unboxing với các chuyển đổi hợp lệ).
3. Nếu vẫn chưa có, xét phương thức varargs theo dạng variable arity.
4. Trong **giai đoạn đầu tiên có phương thức áp dụng**, chọn phương thức đặc hiệu nhất; nếu không có lựa chọn duy nhất, lời gọi có thể mơ hồ và không biên dịch.

Không phải mọi sự kết hợp giữa widening, boxing và varargs đều chuyển đổi được; hãy đối chiếu JLS khi gặp overload phức tạp.

### 4.3. Kết quả generic của `var` có thể thay đổi overload

Đây là trọng tâm khi chủ đề `var` gắn với generics.

Lab khai báo:

```java
static String route(List<String> items) { return "List<String>"; }
static String route(Collection<?> items) { return "Collection<?>"; }
```

Hai overload này hợp lệ vì sau type erasure chữ ký của chúng vẫn khác nhau (`List` và `Collection`).

**Trường hợp A — `var` với diamond không có đối số:**

```java
var guessed = new ArrayList<>(); // ArrayList<Object>
route(guessed);                   // Collection<?>
```

Với `var`, vế trái không cung cấp target type cho `new ArrayList<>()`; ở đây type argument được suy luận là `Object`. Vì generics **invariant**, `ArrayList<Object>` **không phải** `List<String>`. Overload `route(List<String>)` không áp dụng; `route(Collection<?>)` áp dụng.

**Trường hợp B — `var` từ generic factory thiếu thông tin kiểu:**

```java
var empty = Collections.emptyList(); // List<Object>
route(empty);                         // Collection<?>
```

`emptyList()` là phương thức generic `<T> List<T>` không có đối số. Không có target type bên trái, compiler suy luận `T=Object`. Lời gọi `route(empty)` vì vậy nhận xử lý tương tự trường hợp A.

**Trường hợp C — khai báo rõ generic type:**

```java
List<String> typed = new ArrayList<>();
route(typed); // List<String>
```

`typed` có kiểu `List<String>` ngay khi biên dịch. Cả hai overload đều áp dụng nhưng `List<String>` đặc hiệu hơn `Collection<?>`, nên chọn `route(List<String>)`.

**Trường hợp D — thêm type witness vào vế phải của `var`:**

```java
var witness = Collections.<String>emptyList(); // List<String>
route(witness);                                 // List<String>
```

Type witness `<String>` cấp thông tin kiểu để generic method trả `List<String>`, dù vế trái vẫn dùng `var`.

**Trường hợp E — constructor nhận đối số có kiểu:**

```java
var fromArgs = new ArrayList<>(List.of("A", "B")); // ArrayList<String>
route(fromArgs);                                   // List<String>
```

`List.of("A", "B")` có kiểu phù hợp `List<String>`; thông tin đến từ **initializer**, nên `ArrayList<String>` được suy ra mà không cần kiểu đích từ vế trái.

### 4.4. Điểm đặc biệt: truyền `new ArrayList<>()` trực tiếp

So sánh hai cách gọi ngay trong lab:

```java
route(new ArrayList<>()); // List<String>

var guessed = new ArrayList<>();
route(guessed);           // Collection<?>
```

**Tại sao cùng biểu thức `new ArrayList<>()` mà khác?**

- Khi truyền **trực tiếp** vào `route(...)`, diamond là biểu thức có thể nhận **target type từ ngữ cảnh đối số của một overload ứng viên**. Compiler có thể suy luận `ArrayList<String>` để khớp `route(List<String>)`, và overload này đặc hiệu hơn `route(Collection<?>)`.
- Khi trước tiên lưu vào `var guessed`, compiler đã xác định kiểu độc lập `ArrayList<Object>`. Ở lời gọi sau đó, `guessed` là một biến đã có kiểu cố định, nên compiler không quay lại sửa type argument thành `String`.
- Đây là sự khác biệt giữa **type inference trong biểu thức đối số** và **type inference khi khởi tạo biến `var`**. Không nên diễn giải thành “`var` luôn chọn overload tổng quát hơn”; kết quả tùy biểu thức và chữ ký overload.

Trong code thật, nếu danh sách chứa `String` theo hợp đồng, cách an toàn là ghi rõ: `List<String> list = new ArrayList<>();` hoặc `var list = new ArrayList<String>();`. Không dựa vào một overload bên ngoài để che việc suy luận type argument thành `Object`.

## 5. Kiểu trả về không phải tín hiệu để chọn overload

Thêm hai overload như trong lab:

```java
static String value(Object x) { return "Object"; }
static Integer value(String x) { return 7; }
```

Lệnh `var chosen = value("abc");` chọn `value(String)` do kiểu **đối số `"abc"`** là `String`. Vì vậy kiểu của `chosen` là `Integer` và giá trị là `7`.

Trường hợp sau **cố ý không biên dịch**:

```java
String desired = value("abc"); // Lỗi: Integer không thể gán cho String.
```

Compiler **không chuyển sang `value(Object)`** chỉ vì overload đó trả `String` phù hợp vế trái. Overload được quyết định dựa vào tên phương thức, kiểu/biểu thức đối số, tham số hình thức, khả năng áp dụng và tính đặc hiệu — **không dựa vào kiểu trả về mà vế trái mong muốn**. Sau khi chọn, việc chuyển đổi kiểu kết quả mới được kiểm tra.

Có một điểm cần phân biệt: đối với **một lời gọi generic** có kết quả phụ thuộc type variable, target type từ assignment có thể tham gia suy luận **type argument của lời gọi đã chọn**. Điều này không đồng nghĩa dùng target type để đổi sang overload khác. Với `var`, initializer không nhận target type từ khai báo nên kết quả generic có thể rộng hơn khi thiếu thông tin ở đối số.

## 6. `null` và lỗi mơ hồ giữa overload

Lab có ba overload: `which(Object)`, `which(String)`, `which(Integer)`.

```java
var typedNull = (String) null; // var suy luận kiểu String
Object objectNull = typedNull;
which(typedNull);              // String
which(objectNull);             // Object
```

Mặc dù hai giá trị cùng là `null` lúc chạy, kiểu tĩnh của chúng khác nhau. `which(typedNull)` có kiểu đối số `String`, nên chọn `which(String)`. `which(objectNull)` có kiểu đối số `Object`, nên chỉ chọn `which(Object)`.

Hai đoạn sau **không biên dịch**:

```java
var untyped = null; // Sai: var không thể suy luận kiểu từ null đơn lẻ.
which(null);        // Sai: mơ hồ giữa which(String) và which(Integer).
```

Với literal `null`, cả `String` và `Integer` đều có thể nhận, nhưng không kiểu nào là subtype của kiểu còn lại. Việc có thêm `which(Object)` không giải quyết mơ hồ, vì hai overload chuyên biệt vẫn không có một lựa chọn duy nhất.

Nếu thật sự muốn chỉ định overload, có thể viết `which((String) null)` hoặc `which((Integer) null)`. Nên ưu tiên điều này **chỉ khi có ý nghĩa nghiệp vụ rõ ràng**; với dữ liệu có thể thiếu, thường tốt hơn là kiểm tra `null` sớm thay vì tạo lời gọi quá tải mơ hồ.

## 7. Giới hạn quan trọng của overloading với generics: type erasure

Đoạn sau **cố ý sai, không đặt vào chương trình đang chạy**:

```java
static void save(List<String> items) { }
static void save(List<Integer> items) { } // Lỗi name clash.
```

Sau *type erasure*, cả hai chữ ký đều tương đương `save(List)`, nên Java không cho phép khai báo chúng như hai overload riêng trong cùng lớp.

Ngược lại, ví dụ hợp lệ của bài có:

```java
static String route(List<String> items) { return "List<String>"; }
static String route(Collection<?> items) { return "Collection<?>"; }
```

Erasure của hai tham số khác nhau (`List` so với `Collection`). Vì vậy việc lựa chọn overload có thể phụ thuộc vào `List<String>` hay `List<Object>` ở **compile time**, trong khi JVM không dùng type argument generic đã bị xóa để lựa chọn overload lại ở runtime.

Đừng xây dựng API gồm các overload chỉ phân biệt bằng `List<String>`/`List<Integer>`; thay bằng tên phương thức khác nhau, kiểu wrapper nghiệp vụ khác nhau hoặc một API generic được thiết kế rõ hợp đồng.

## 8. Overload khác override và dispatch lúc chạy

- **Overload**: các phương thức cùng tên, khác danh sách tham số; compiler quyết định **chữ ký nào** tại vị trí lời gọi.
- **Override**: lớp con triển khai lại một phương thức instance có cùng chữ ký; JVM có thể chọn **implementation** theo kiểu đối tượng nhận lời gọi ở runtime, sau khi chữ ký phương thức đã được compiler xác định.

`var` không thay đổi quy tắc dynamic dispatch của overriding. Các ví dụ `pick`/`route` trong lab đều là phương thức `static`, nên giúp quan sát quyết định overload tại compile time mà không thêm yếu tố overriding.

Nếu một biến `var` có kiểu tĩnh là interface hoặc superclass, các overload khả dụng tại vị trí gọi được xác định từ kiểu tĩnh đó. Việc đối tượng runtime thuộc subclass có nhiều overload riêng không khiến compiler tự động xem lại overload của lời gọi đã biên dịch.

## 9. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `var xs = new ArrayList<>()` gọi overload `Collection<?>` thay vì `List<String>` | `xs` là `ArrayList<Object>`; generics invariant. | Ghi `new ArrayList<String>()` hoặc khai báo `List<String> xs`. |
| `var xs = Collections.emptyList()` không nhận được overload `List<String>` | `xs` có kiểu `List<Object>` vì thiếu target và đối số. | `Collections.<String>emptyList()` hoặc `List<String> xs = ...`. |
| `pick(object)` gọi `Object` dù object thực tế là chuỗi | Compiler dùng kiểu tĩnh của đối số. | Sửa API hoặc khai báo/kiểm tra kiểu đúng từ sớm; tránh ép kiểu tùy tiện. |
| `widenOrBox(primitive)` gọi `long` thay vì `Integer` | Primitive widening được xét trong strict invocation trước boxing. | Xác định rõ chữ ký cần dùng; nếu thực sự cần wrapper, tạo `Integer.valueOf(...)`. |
| `which(null)` bị báo ambiguous | `String` và `Integer` không so sánh được độ đặc hiệu. | Tránh overload mơ hồ; dùng kiểu đích rõ khi hợp lý. |
| Muốn compiler chọn overload trả về kiểu vế trái | Kiểu trả về không quyết định overload. | Chọn đúng tên/phân biệt kiểu tham số; xử lý kiểu kết quả đã chọn. |
| Hai overload `List<String>` và `List<Integer>` báo name clash | Type erasure tạo chữ ký trùng nhau. | Đổi tên API, dùng wrapper types hoặc thiết kế phương thức generic. |
| Thay khai báo tường minh bằng `var` khiến build lỗi downstream | Refactor vô tình thay kiểu generic suy luận. | Đọc kiểu được IDE/compiler suy ra, bổ sung generic type ở vế phải. |

### Hướng thiết kế API

Không nên cố tạo các overload quá sát nhau chỉ để tiết kiệm tên phương thức. Các overload dùng trong lab được chọn để **giải thích cơ chế**. Trong mã dự án, tên mô tả rõ nghiệp vụ như `saveTextOrders`/`saveNumericOrders` đôi khi dễ đọc và khó gọi sai hơn việc dựa vào một mạng các overload generic mơ hồ.

Cũng nên tránh đặt các overload có hành vi nghiệp vụ hoàn toàn khác nhau dưới một tên giống nhau. Người sử dụng API cần dự đoán được logic từ chữ ký, không phải giải ngược toàn bộ quy tắc overload resolution ở mỗi lời gọi.

## 10. Bài tập tự luyện (có đáp án)

### Bài 1 — Kiểu tĩnh hay kiểu runtime?

Giả sử có `pick(Object)` và `pick(String)` như trong lab:

```java
Object value = "Hello";
var copy = value;
System.out.println(pick(copy));
System.out.println(pick((String) copy));
```

**Đáp án:** In `Object` rồi `String`. `copy` có kiểu tĩnh `Object` vì lấy kiểu từ biểu thức `value`. Phép cast `(String) copy` có kiểu tĩnh `String` và thành công trong trường hợp dữ liệu thật sự là chuỗi.

### Bài 2 — Diamond và generic

Dự đoán tên overload được chọn:

```java
var a = new ArrayList<>();
var b = new ArrayList<String>();
List<String> c = new ArrayList<>();
System.out.println(route(a));
System.out.println(route(b));
System.out.println(route(c));
```

**Đáp án:** Lần lượt `Collection<?>`, `List<String>`, `List<String>`. `a` có type argument `Object` do không có target, còn `b`/`c` mang `String` từ constructor hoặc khai báo tường minh.

### Bài 3 — Phương thức generic rỗng

So sánh:

```java
var a = Collections.emptyList();
var b = Collections.<String>emptyList();
List<String> c = Collections.emptyList();
```

**Đáp án:** `a` có kiểu `List<Object>`, `b` và `c` là `List<String>`. Với các overload `route` của bài, `route(a)` chọn `Collection<?>`, còn `route(b)`/`route(c)` chọn `List<String>`.

### Bài 4 — Boxing với widening

Với `widenOrBox(long)` và `widenOrBox(Integer)`:

```java
var first = 5;
var second = Integer.valueOf(5);
System.out.println(widenOrBox(first));
System.out.println(widenOrBox(second));
```

**Đáp án:** In `long` rồi `Integer`. Với `int`, primitive widening áp dụng ở strict phase; với `Integer`, phương thức cùng kiểu áp dụng trực tiếp.

### Bài 5 — Return type có được chọn giúp không?

Với `value(Object)` trả `String` và `value(String)` trả `Integer`, dự đoán:

```java
var a = value("Java");
String b = value("Java");
```

**Đáp án:** Dòng đầu biên dịch và `a` là `Integer`; dòng thứ hai lỗi biên dịch vì `value(String)` đã được chọn và trả `Integer`, không thể gán vào `String`. Compiler không thay bằng `value(Object)` để phù hợp biến `b`.

### Bài 6 — Mã nguồn Java được gọi trực tiếp hay qua `var`?

```java
System.out.println(route(new ArrayList<>()));
var list = new ArrayList<>();
System.out.println(route(list));
```

**Đáp án:** In `List<String>` rồi `Collection<?>`. Ở lời gọi trực tiếp, candidate overload truyền ngữ cảnh tham số cho diamond. Khi lưu vào biến `var`, generic type đã được cố định là `ArrayList<Object>`.

### Bài 7 — Lỗi nào là lỗi compile time?

Xét các đoạn sau, **chỉ phân tích, không dán vào tệp lab**:

```java
var nothing = null;
which(null);
static void store(List<String> x) { }
static void store(List<Integer> x) { }
```

**Đáp án:** `var nothing = null` thiếu kiểu initializer; `which(null)` mơ hồ giữa `String` và `Integer`; hai khai báo `store` trùng chữ ký sau erasure. Để kiểm thử riêng hai khai báo `store`, đặt chúng trong một lớp hợp lệ; chúng không thể đồng tồn tại trong cùng lớp.

## 11. Checklist khi dùng `var` với overload trong dự án

- [ ] Xác định được kiểu tĩnh thực tế của từng biến `var` ngay tại dòng khai báo.
- [ ] Nêu rõ vì sao Java chọn một overload: khả năng áp dụng, giai đoạn strict/loose/varargs và độ đặc hiệu.
- [ ] Không suy luận overload từ kiểu runtime của đối tượng đối số.
- [ ] Biết rằng `var x = new ArrayList<>()` khác `List<String> x = new ArrayList<>()` về generic type.
- [ ] Kiểm tra generic factory thiếu thông tin kiểu: `Collections.emptyList()`, `Optional.empty()`, v.v.
- [ ] Phân biệt biểu thức diamond làm đối số trực tiếp với biểu thức diamond đã lưu qua `var`.
- [ ] Không dùng return type của overload làm tiêu chí chọn overload.
- [ ] Không khai báo overload chỉ khác tham số generic bị type erasure xóa.
- [ ] Chạy được `OverloadVarLab.java` trên JDK được bảo trì, đối chiếu chính xác 13 dòng output.
- [ ] Khi refactor, bổ sung type witness hoặc kiểu generic tường minh nếu kiểu suy ra bị rộng thành `Object`.

## 12. Áp dụng thực tế

Khi thay một khai báo `List<Foo> x = new ArrayList<>();` bằng `var x = new ArrayList<>();`, hãy coi đây là một thay đổi **kiểu tĩnh** chứ không chỉ là rút gọn cú pháp. Xem lại những lời gọi phương thức dùng `x`: overload nào còn áp dụng, overload nào bị loại vì generics invariant, và có kiểm tra kiểu nào bị mất không? Nếu chỉ muốn rút gọn phần bên trái mà giữ contract, dùng `var x = new ArrayList<Foo>();` hoặc giữ `List<Foo>` khai báo rõ. `Foo` ở đây là tên kiểu ứng dụng minh họa.

Với API công khai có overload, nên chọn chữ ký đủ khác biệt và có ý nghĩa, kiểm tra trường hợp `null`, boxing, generic type inference và lời gọi bằng superclass/interface. Các hành vi này được định nghĩa trong JLS và còn áp dụng ở JDK mới; không phụ thuộc vào việc sử dụng một runtime Java 10 đã lỗi thời.

## Tài liệu chuẩn đối chiếu

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi suy luận `var` và initializer như standalone expression.
- [Java SE 25 JLS `14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1): quy tắc suy luận kiểu biến cục bộ với `var`.
- [Java SE 25 JLS `15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): applicability, most specific, thứ tự strict/loose/varargs và kiểm tra return type.
- [Java SE 25 JLS `15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9): diamond và ngữ cảnh kiểu của biểu thức tạo đối tượng.
- [Java SE 25 JLS `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6): lý do hai overload chỉ khác generic type argument gây name clash.