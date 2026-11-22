# Truyền đối số kiểu tường minh để làm rõ lời gọi

## Mục tiêu

Trong phần lớn lời gọi phương thức generic của Java, compiler tự suy luận kiểu từ đối số truyền vào và từ ngữ cảnh sử dụng kết quả. Tuy nhiên, có lúc bạn muốn **chỉ định rõ type argument** để thể hiện ý định, điều khiển kiểu kết quả hoặc giúp một lời gọi phức tạp dễ hiểu hơn.

Ví dụ:

```java
Number value = ExplicitTypeArgumentsDemo.<Number>chooseFirst(10, 2.5);
List<String> empty = Collections.<String>emptyList();
```

Hai câu lệnh này là **minh họa**: phương thức `chooseFirst` do ta định nghĩa ở ví dụ chạy độc lập bên dưới; `Collections.emptyList()` là API chuẩn trong `java.util.Collections`.

Sau bài này, bạn sẽ phân biệt được **type parameter khi khai báo** và **type argument khi gọi**, viết đúng cú pháp truyền đối số kiểu tường minh cho phương thức static/instance, giải thích mối quan hệ với **type inference** và **target typing**, đồng thời nhận biết khi nào cách viết tường minh thực sự hữu ích và khi nào chỉ làm mã dài hơn.

## 1. Type parameter trong khai báo khác type argument trong lời gọi

Hãy xem phương thức generic:

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

Đây là phương thức **minh họa** đặt trong một class. Trong `static <T> T chooseFirst(...)`:

- `<T>` đứng trước kiểu trả về là **khai báo biến kiểu** (*type parameter*) của phương thức.
- Hai tham số `first` và `second` được kiểm tra theo kiểu `T`.
- Phương thức trả về một giá trị có kiểu tĩnh `T`.

Người gọi có thể để compiler suy luận:

```java
Number result = chooseFirst(10, 2.5);
```

Hoặc chỉ định rõ đối số kiểu:

```java
Number result = ExplicitTypeArgumentsDemo.<Number>chooseFirst(10, 2.5);
```

Ở lời gọi thứ hai, **`<Number>` là explicit type argument**. Nó thay vai trò `T` bằng `Number` cho lần gọi ấy: `Integer` nhận từ literal `10` qua boxing và `Double` nhận từ literal `2.5` đều tương thích với `Number`. Kiểu trả về tại compile time là `Number`.

Đối số kiểu **không thay thế giá trị tham số phương thức**. Những biểu thức `10` và `2.5` vẫn là đối số dữ liệu thực. Chỉ định `T = Number` cũng **không biến đối tượng `Integer` thành `Number` mới**; trong ví dụ, đối tượng trả về là phần tử `first` như ban đầu.

Cần tách rõ hai cặp khái niệm:

| Vị trí | Mẫu cú pháp | Tác dụng |
| --- | --- | --- |
| Khai báo phương thức | `static <T> T chooseFirst(T a, T b)` | Định nghĩa biến kiểu `T` |
| Gọi với kiểu tường minh | `Demo.<Number>chooseFirst(1, 2.5)` | Chọn `Number` làm `T` cho lần gọi |
| Gọi không tường minh | `Demo.chooseFirst(1, 2.5)` | Compiler tự suy luận kiểu phù hợp |
| Tham số dữ liệu | `1, 2.5` | Cung cấp các giá trị cho `a` và `b` |

Một class có thể vừa generic vừa có generic method riêng. Type parameter `T` của phương thức không mặc nhiên là type parameter của class và chỉ có hiệu lực trong phạm vi khai báo của chính phương thức.

## 2. Cú pháp truyền đối số kiểu tường minh

### 2.1. Gọi phương thức static

Với một phương thức static generic trong class `Demo`, cú pháp rõ ràng là:

```java
Demo.<String>identity("hello");
Demo.<Number>chooseFirst(10, 2.5);
```

Hai lời gọi trên minh họa cú pháp; để biên dịch, class `Demo` cần khai báo các phương thức `identity`/`chooseFirst` phù hợp. Dấu chấm nằm **trước** `<String>`, tiếp theo là **tên phương thức**. Cách viết `Demo.<String>identity(...)` cho biết đây là đối số kiểu của *phương thức được gọi*.

Với `java.util.Collections`, mã thực tế là:

```java
List<String> values = Collections.<String>emptyList();
```

`Collections.emptyList()` khai báo theo dạng:

```java
public static <T> List<T> emptyList()
```

Đây là chữ ký rút gọn của API chuẩn, không phải phương thức cần tự định nghĩa. Gọi `Collections.<String>emptyList()` chỉ định `T = String`, nên kết quả có kiểu `List<String>`.

### 2.2. Gọi phương thức instance

Đối số kiểu tường minh cũng có thể đặt sau biểu thức nhận (*receiver*) của một phương thức instance:

```java
String description = printer.<String>describe("generic");
```

Đây là đoạn minh họa, trong đó `printer` là đối tượng có phương thức generic `<T> String describe(T value)`. Ví dụ chạy hoàn chỉnh ở phần sau dùng biểu thức `new Printer().<String>describe("generic")`.

Bạn không cần dùng kiểu tham số của class làm đối số kiểu cho mọi phương thức instance. Cần xem **phương thức cụ thể có khai báo `<T>` hay không**. Một phương thức thông thường của `List<String>` như `add(String)` không tự nhiên trở thành generic method chỉ vì class/interface chứa nó có type parameter.

### 2.3. Nhiều type parameter và giới hạn kiểu

Nếu phương thức khai báo nhiều type parameter:

```java
static <K, V> String describePair(K key, V value) {
    return key + "=" + value;
}
```

thì caller có thể truyền type arguments **theo đúng thứ tự**:

```java
String pair = Demo.<String, Integer>describePair("age", 20);
```

Đây là các ví dụ minh họa (giả sử phương thức được đặt vào class `Demo`). Số đối số kiểu được truyền phải phù hợp với số type parameter của phương thức. Các type argument phải tuân thủ bound và ràng buộc kiểu.

Ví dụ, với:

```java
static <T extends Number> double asDouble(T number) {
    return number.doubleValue();
}
```

thì `Demo.<Integer>asDouble(7)` hợp lệ, nhưng `Demo.<String>asDouble("7")` **không biên dịch**: `String` không thỏa ràng buộc `T extends Number`.

Type argument tường minh phải là **kiểu tham chiếu** như `Integer`, `String` hoặc `Number`, không phải primitive `int`, `double`. Khi truyền literal primitive `7` vào một tham số kiểu `Integer`, Java có thể dùng autoboxing.

## 3. Type inference và target typing hoạt động ra sao?

**Type inference** là quá trình compiler tìm type argument phù hợp từ các thông tin tại lời gọi. Với Java 17, thông tin ấy có thể bao gồm:

- Kiểu tĩnh của các đối số thực được truyền cho phương thức.
- Ràng buộc trên các type parameter như `<T extends Number>`.
- Kiểu mong đợi của ngữ cảnh, chẳng hạn phép gán, tham số của lời gọi bao quanh hoặc return context phù hợp.
- Quan hệ giữa các type parameter và wildcard ở khai báo phương thức.

Ví dụ:

```java
List<String> first = Collections.emptyList();
List<Integer> second = Collections.emptyList();
```

Ở hai phép gán này, compiler có đủ **target type** từ phía bên trái để suy luận `T = String` và `T = Integer` mà không cần viết `Collections.<String>emptyList()` hoặc `Collections.<Integer>emptyList()`.

Vì vậy, khi lời gọi đã ngắn và kiểu mong muốn rõ ràng, cách viết tường minh thường **không cần thiết**. Việc thêm `<T>` chỉ hữu ích khi nó nêu được một quyết định kiểu đáng chú ý.

Ngược lại, nếu dùng `var`, kiểu của biến đến từ kiểu tĩnh của biểu thức khởi tạo; không có kiểu khai báo ở vế trái như `List<String>` để định hướng suy luận:

```java
var inferred = Collections.emptyList();          // List<Object>
var explicit = Collections.<String>emptyList(); // List<String>
```

Các dòng trên là ví dụ minh họa trong một phương thức Java 17. Với lời gọi `emptyList()` không có đối số dữ liệu, compiler thường suy ra `Object` khi không có target type cụ thể. Explicit type argument là cách diễn đạt chủ ý `List<String>` ngay trong biểu thức khởi tạo.

Tuy nhiên, việc `emptyList()` trả về `List<String>` **không làm danh sách thành mutable**. Danh sách trống trả từ `Collections.emptyList()` không cho phép thêm phần tử. Nếu cần một danh sách sửa được, hãy tạo một `ArrayList` mới từ nó.

## 4. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`ExplicitTypeArgumentsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ExplicitTypeArgumentsDemo {
    static <T> T chooseFirst(T first, T second) {
        return first;
    }

    static <T> List<T> copy(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T extends Number> double asDouble(T value) {
        return value.doubleValue();
    }

    static final class Printer {
        <T> String describe(T value) {
            return "value=" + value;
        }
    }

    public static void main(String[] args) {
        Number chosen = ExplicitTypeArgumentsDemo.<Number>chooseFirst(10, 2.5);
        System.out.println("chosen: " + chosen);

        List<Integer> integers = List.of(1, 2);
        List<Number> copied = ExplicitTypeArgumentsDemo.<Number>copy(integers);
        System.out.println("copied: " + copied);

        List<String> empty = Collections.<String>emptyList();
        System.out.println("empty size: " + empty.size());

        var texts = new ArrayList<>(Collections.<String>emptyList());
        texts.add("Java");
        System.out.println("texts: " + texts);

        String info = new Printer().<String>describe("generic");
        System.out.println("instance: " + info);

        System.out.println("as double: "
                + ExplicitTypeArgumentsDemo.<Integer>asDouble(7));

        List<Number> inferred = ExplicitTypeArgumentsDemo.copy(List.of(3, 4.5));
        System.out.println("inferred: " + inferred);
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

**Stdout chính xác:**

```text
chosen: 10
copied: [1, 2]
empty size: 0
texts: [Java]
instance: value=generic
as double: 7.0
inferred: [3, 4.5]
```

### Giải thích kết quả

1. `<Number>chooseFirst(10, 2.5)` nói rõ `T = Number`. Phần tử đầu là số nguyên `10`, nên `System.out.println` in `10`, dù kiểu tĩnh của biến `chosen` là `Number`.
2. `<Number>copy(integers)` tạo `List<Number>` mới từ `List<Integer>`. Chữ ký `List<? extends T>` cho phép đọc `Integer` như `Number`. Đây là **sao chép cấu trúc danh sách** (shallow copy đối với phần tử tham chiếu), không tạo danh sách gốc kiểu `List<Number>`.
3. `Collections.<String>emptyList()` chỉ rõ kiểu phần tử của kết quả, còn `size()` bằng 0 vì danh sách trống.
4. `new ArrayList<>(Collections.<String>emptyList())` tạo danh sách mới có thể sửa, đồng thời giữ kiểu `String`. `texts.add("Java")` làm danh sách thành `[Java]`.
5. `new Printer().<String>describe("generic")` minh họa cách đặt type argument trên **lời gọi instance method**.
6. `<Integer>asDouble(7)` thỏa `T extends Number` và gọi `doubleValue()` trên đối tượng `Integer` nên in `7.0`.
7. `copy(List.of(3, 4.5))` không có explicit type argument; compiler suy luận kiểu tương thích với `List<Number> inferred`. Đây là một trường hợp nên **ưu tiên để Java suy luận** vì kết quả mong muốn đã hiện rõ ở kiểu biến nhận.

Ví dụ dùng Java 17, không cần thư viện bên ngoài JDK. `Integer`, `Number`, `String` thuộc `java.lang` nên không cần import.

## 5. Khi nào đối số kiểu tường minh thực sự giúp ích?

### 5.1. Không có thông tin kiểu từ đối số dữ liệu

`Collections.emptyList()` không nhận đối số dữ liệu; khi ngữ cảnh không cung cấp kiểu mong đợi, type argument tường minh là cách rõ ràng nhất để khẳng định ý định:

```java
var names = Collections.<String>emptyList();
```

Compiler có kiểu `List<String>` ngay từ biểu thức, thay vì suy ra danh sách của kiểu tổng quát hơn. Đây là ví dụ minh họa trong phương thức Java 17; `names` trỏ tới danh sách trống không sửa được.

### 5.2. Muốn nhìn thấy kiểu kết quả ở ngay lời gọi

Giả sử có phương thức:

```java
static <T> List<T> copy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

Đối số nguồn có thể là `List<Integer>` nhưng bạn cần kết quả được khai báo là `List<Number>`:

```java
List<Integer> source = List.of(1, 2);
List<Number> numbers = ExplicitTypeArgumentsDemo.<Number>copy(source);
```

Cú pháp `<Number>` cho người đọc biết **muốn mở rộng kiểu phần tử của bản sao thành `Number`**. Biến `numbers` có thể thêm `Double` sau này vì `copy` trả về `ArrayList<Number>`, nếu thao tác thêm phù hợp với logic ứng dụng:

```java
numbers.add(2.5);
System.out.println(numbers); // [1, 2, 2.5]
```

Đoạn code trên là ví dụ bổ sung trong một phương thức. **Nguồn `source` vẫn là `List<Integer>`** và không chứa `Double`. Kiểu tường minh giúp chọn kiểu trả về phù hợp; nó không ép kiểu không an toàn cho nguồn.

### 5.3. Muốn ràng buộc một lựa chọn kiểu đáng chú ý

Khi generic method có nhiều đối số thuộc các subtype khác nhau:

```java
Number chosen = ExplicitTypeArgumentsDemo.<Number>chooseFirst(1, 2.5);
```

`<Number>` thể hiện rằng caller muốn xử lý hai giá trị trong khuôn khổ `Number`. Đây là lựa chọn hữu ích về **tính rõ ràng**, nhất là khi kiểu suy luận mặc định có thể phức tạp. Dù vậy, bản thân `<Number>` không làm phép chuyển đổi số học từ `Integer` sang `Double` hay ngược lại.

### 5.4. Khi API dạng chuỗi làm mờ target type

Trong các biểu thức lồng nhau hoặc fluent chain, người đọc có thể phải suy luận qua nhiều lời gọi. Một explicit type argument đúng chỗ làm rõ kiểu ngay tại nguồn tạo dữ liệu:

```java
var mutableNames =
        new ArrayList<>(Collections.<String>emptyList());
mutableNames.add("Lan");
```

Cú pháp này rõ về `String` mà không cần thêm một khai báo type đầy đủ ở vế trái. Đừng rải type arguments ở mọi lời gọi trong chuỗi; chỉ đặt tại bước mà nó thực sự diễn đạt ý định hoặc giải quyết lỗi suy luận.

## 6. Đối số kiểu tường minh không thể ép một lời gọi sai thành đúng

**Quy tắc:** viết `<T>` chỉ định type parameter; Java vẫn kiểm tra kiểu của **mọi đối số giá trị**, kiểu trả về, generic bounds và overload applicability.

Ví dụ lỗi biên dịch, đã chú thích:

```java
// Không thể gán List<Integer> vào List<Number>:
List<Integer> integers = List.of(1, 2);
// List<Number> invalid = integers;

// T = Number không cho phép một danh sách String làm nguồn:
// List<Number> invalidCopy =
//         ExplicitTypeArgumentsDemo.<Number>copy(List.of("a"));

// T = String vi phạm giới hạn T extends Number:
// double invalidNumber =
//         ExplicitTypeArgumentsDemo.<String>asDouble("7");

// T = Integer khiến kết quả là List<Integer>, không phải List<Number>:
// List<Number> invalidResult =
//         ExplicitTypeArgumentsDemo.<Integer>copy(integers);
```

Từng dòng lỗi phải được hiểu qua chữ ký generic và tính bất biến của `List<T>`. Không có “type witness thần kỳ” nào đổi được một `List<Integer>` thành `List<Number>` bằng phép gán trực tiếp.

### Type argument không phải cast

- `(Number) expression` là cú pháp **cast** một biểu thức sang kiểu mục tiêu.
- `Demo.<Number>method(...)` là cú pháp **truyền type argument cho generic method**; compiler kiểm tra chữ ký với `T = Number`.
- `new ArrayList<Number>(source)` là **tạo đối tượng danh sách mới** có type argument `Number` ở constructor/class, khác lời gọi generic method.

Type argument có thể tác động đến các ràng buộc kiểu của lời gọi, nhưng nó không tạo thêm đối tượng, không tự thực hiện chuyển đổi dữ liệu và không làm biến mất lỗi runtime của code trong thân phương thức.

### Không có type parameter thì không có gì để chỉ định

Không thể viết một `<String>` tùy ý lên phương thức **không generic** rồi mong phương thức nhận kiểu mới. Hãy xem chữ ký khai báo của method: chỉ các type parameters do generic method cung cấp mới có ý nghĩa trong lời gọi type-witness tương ứng.

Nếu class là `Box<String>` nhưng phương thức `get()` không khai báo type parameter riêng, thì kiểu `String` của kết quả đến từ **class parameter**, chứ không có nghĩa bạn cần viết `box.<String>get()`.

## 7. Quan hệ với quá tải phương thức (overloading)

Một lớp có thể khai báo nhiều phương thức trùng tên nhưng khác danh sách tham số. Việc lựa chọn overload còn dựa vào **kiểu và số đối số**, khả năng áp dụng của các chữ ký, boxing, varargs và quy tắc “more specific” của Java.

Explicit type argument có thể ảnh hưởng đến việc một **ứng viên generic** có áp dụng được hay không, nhưng **không phải cú pháp chọn bất kỳ overload nào theo ý muốn**. Để hiểu lời gọi nào được chọn, cần đọc tất cả các chữ ký cùng tên và áp dụng quy tắc overload resolution.

Đặc biệt, đừng cố dùng `<T>` như cách giải quyết một overload mơ hồ mà chưa hiểu vì sao mơ hồ. Có những trường hợp phải **thay đổi kiểu của đối số biểu thức**, dùng API có tên rõ ràng hơn hoặc bổ sung thông tin loại khác. Không nên đánh đồng việc chỉ rõ type parameter với thao tác cast.

## 8. Liên hệ với wildcard và phương thức generic

Một generic method thường kết hợp type parameter và wildcard:

```java
static <T> List<T> copy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

Ở đây:

- `<T>` khai báo một type parameter của **phương thức**.
- `? extends T` nói rằng phần tử nguồn thuộc một subtype (chưa biết chính xác) của `T`.
- `List<T>` là kiểu trả về, nên caller có thể muốn quyết định chính xác `T`.

Lời gọi:

```java
List<Integer> input = List.of(1, 2);
List<Number> result = ExplicitTypeArgumentsDemo.<Number>copy(input);
```

là hợp lệ vì `Integer extends Number`. Trái lại:

```java
// List<String> invalid =
//         ExplicitTypeArgumentsDemo.<String>copy(input);
```

không hợp lệ: `Integer` không phải subtype của `String`.

Đây là ví dụ tốt cho thấy explicit type argument giúp diễn đạt mục tiêu, còn wildcard giúp **giữ an toàn kiểu giữa producer và kiểu kết quả**. Tuy nhiên, khi có target type đủ rõ, `List<Number> result = ExplicitTypeArgumentsDemo.copy(input);` cũng có thể được compiler suy luận thành công. Sự khác biệt chủ yếu ở việc bạn có muốn quyết định `Number` xuất hiện ngay tại vị trí gọi hay không.

## 9. Những lỗi thường gặp

**Nhầm cú pháp khai báo và cú pháp gọi.** `static <T> T f(T x)` là khai báo; `ClassName.<String>f("a")` là lời gọi. Không viết `<String>` trước toàn bộ tên class một cách tùy tiện.

**Chỉ định kiểu primitive.** `<int>` và `<double>` không phải type arguments hợp lệ của generics. Dùng `Integer`, `Double` khi cần.

**Cho rằng explicit type argument làm bất biến generic thành hiệp biến.** `List<Integer>` vẫn không phải `List<Number>`. Nếu cần tạo danh sách mới có kiểu `Number`, phải dùng một cơ chế phù hợp như generic `copy` ở ví dụ; không dùng phép gán trực tiếp.

**Tin rằng `<T>` có thể bỏ qua bound.** `<String>asDouble(...)` sai nếu method khai báo `T extends Number`.

**Lặp type argument không cần thiết.** `List<String> x = Collections.<String>emptyList()` đúng, nhưng `List<String> x = Collections.emptyList()` cũng rõ ràng và thường gọn hơn nhờ target typing.

**Nhầm loại collection.** `Collections.<String>emptyList()` mang kiểu `List<String>` nhưng không thêm được phần tử; an toàn kiểu không đồng nghĩa mutability.

**Nhầm type argument với runtime type token.** `<String>` không khiến Java giữ lại `Class<String>` để dùng reflection hoặc phân biệt specialization ở runtime. Generics Java chủ yếu được triển khai qua type erasure; muốn method nhận thông tin `Class<T>` ở runtime, API phải khai báo tham số kiểu `Class<T>` hoặc cơ chế tương ứng.

**Dùng type witness để che thiết kế API khó hiểu.** Nếu phải chèn type argument quá nhiều, hãy cân nhắc điều chỉnh chữ ký, kiểu trung gian, tên phương thức hoặc cấu trúc biểu thức cho dễ đọc hơn.

## 10. Tự kiểm tra

**Câu 1.** Hai lời gọi `Collections.emptyList()` và `Collections.<String>emptyList()` khác nhau ở đâu?

Lời gọi thứ hai chỉ định tường minh `T = String`. Nếu ngữ cảnh như `List<String> x = ...` đã đủ suy luận, cả hai có thể cho cùng kiểu kết quả tại compile time.

**Câu 2.** `var items = Collections.<Integer>emptyList();` cho `items` kiểu gì?

Compiler suy ra kiểu `List<Integer>` của biểu thức khởi tạo, nên `items` có kiểu tĩnh `List<Integer>`. Danh sách ấy vẫn không sửa được.

**Câu 3.** Tại sao `<Number>copy(List<Integer>)` hợp lệ?

Vì source khai báo `List<? extends Number>` sau khi chọn `T = Number`, và `Integer` là subtype của `Number`. Hàm trả một `List<Number>` mới.

**Câu 4.** Có viết `SomeClass.<int>genericMethod(1)` được không?

Không. Generics cần type argument là kiểu tham chiếu, ví dụ `Integer`. Literal `1` có thể được autobox sang `Integer` nếu chữ ký yêu cầu.

**Câu 5.** `Demo.<String>asDouble("7")` có qua được compiler nếu method khai báo `<T extends Number>` không?

Không, vì `String` không thỏa giới hạn kiểu `Number`.

**Câu 6.** Khi nào nên ưu tiên suy luận tự động?

Khi compiler suy luận đúng, các kiểu mong đợi đã rõ từ tham số và target type, và thêm `<T>` không đem lại thông tin đọc hiểu quan trọng.

## Ghi nhớ

Cú pháp `Receiver.<TypeArg>genericMethod(args)` cho phép **chỉ định đối số kiểu của generic method tại nơi gọi**. Nó làm rõ kiểu `T` mong muốn, nhất là khi không có target type hoặc khi muốn chọn kiểu kết quả rộng hơn một cách có chủ đích. Compiler vẫn áp dụng đầy đủ các ràng buộc kiểu, generic bounds và overload resolution. Nếu suy luận mặc định đã rõ ràng, hãy để Java tự suy luận; chỉ viết tường minh khi cách đó giúp biểu đạt ý nghĩa hoặc xử lý tình huống suy luận cụ thể.
