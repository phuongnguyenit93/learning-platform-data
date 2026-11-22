# Đánh giá lỗi kiểu khi thay khai báo tường minh bằng `var` (Java 10+)

## 1. Mục tiêu: thay kiểu khai báo có thể đổi cả ngữ nghĩa suy luận

Với Java 10 trở lên, `var` cho phép trình biên dịch suy luận **kiểu tĩnh của biến cục bộ** từ biểu thức khởi tạo. Nhưng việc đổi:

```java
List<String> names = new ArrayList<>();
```

thành:

```java
var names = new ArrayList<>();
```

**không nhất thiết là một phép thay thế tương đương**. Ở khai báo đầu tiên, vế trái cung cấp kiểu đích `List<String>` để toán tử diamond `<>` suy luận `String`. Ở khai báo thứ hai, `var` không cung cấp kiểu đích đó; constructor `new ArrayList<>()` không có đối số và thường dẫn đến kiểu **`ArrayList<Object>`**. Vì vậy, kiểu khai báo **và** kiểu phần tử đều thay đổi.

Điểm cần nắm:

- `var` **không phải kiểu động**. Biến vẫn có một kiểu tĩnh cố định tại thời điểm biên dịch.
- Kiểu tường minh ở vế trái có thể truyền cho biểu thức bên phải một **target type** (kiểu đích), đặc biệt hữu ích cho generic method, diamond, lambda và method reference.
- Khi thay bằng `var`, initializer được xét như **standalone expression**: kiểu suy luận có thể khác, mã phía sau có thể lỗi biên dịch, hoặc vẫn biên dịch nhưng giảm mức kiểm tra kiểu.
- `var` suy luận kiểu từ initializer **một lần**. Những phép `add`, phép gán lại hoặc lời gọi phương thức về sau không khiến compiler suy luận lại kiểu generic.
- Nếu initializer đã chứa đủ thông tin kiểu, `var` có thể hoàn toàn hợp lệ và dễ đọc.

Bài tập trung vào nhóm **“var và generics”**: cách phát hiện lỗi kiểu khi chuyển từ khai báo tường minh sang `var`, lý do sinh lỗi, cách sửa và quy trình review/refactor. Các quy tắc được mô tả vẫn áp dụng trên Java hiện đại.

## 2. Ba thứ cần tách biệt trước khi review

### 2.1. Kiểu khai báo của biến

```java
List<String> a = new ArrayList<>();
var b = new ArrayList<String>();
```

- `a` có kiểu tĩnh `List<String>` vì kiểu này được viết rõ ràng ở vế trái.
- `b` có kiểu tĩnh `ArrayList<String>` vì đó là kiểu của biểu thức tạo đối tượng.

Hai biến đều chứa các đối tượng tương thích `ArrayList<String>`, nhưng **kiểu tĩnh không giống nhau**. Ví dụ, `a` có thể được gán lại bằng `new LinkedList<String>()`; `b` không thể vì `LinkedList<String>` không là subtype của `ArrayList<String>`.

### 2.2. Suy luận tham số generic

```java
List<String> a = new ArrayList<>(); // diamond nhận target type List<String>
var b = new ArrayList<>();          // không có target type; ArrayList<Object>
var c = new ArrayList<String>();    // ArrayList<String>
```

Suy luận kiểu của **biến** (`var`) và suy luận **tham số kiểu của generic** (`<>`) là hai cơ chế có liên quan nhưng không đồng nhất. Việc thay khai báo vế trái có thể làm mất dữ kiện mà cơ chế generic cần.

### 2.3. Kiểu phần tử và hành vi runtime

```java
var values = new ArrayList<>(); // ArrayList<Object>
values.add("Lan");
values.add(42);
```

Đoạn trên biên dịch: `Object` chấp nhận cả `String` và `Integer`. Nhưng nếu ứng dụng muốn một `List<String>`, việc biên dịch thành công **không có nghĩa refactor đã đúng**. Bạn có thể vô tình làm lỏng hợp đồng kiểu, dẫn đến lỗi ở nơi lấy dữ liệu ra hoặc truyền cho API khác.

**Cách đánh giá:** không chỉ hỏi “có biên dịch được không?”, mà phải xác định **kiểu tĩnh trước/sau**, **kiểu generic trước/sau**, **các phép gán/lời gọi bị ảnh hưởng** và **hợp đồng nghiệp vụ cần giữ**.

## 3. Vì sao thay kiểu tường minh bằng `var` có thể gây lỗi?

Java Language Specification `14.4 quy định: khi khai báo bằng `var`, kiểu của biến được xác định từ **kiểu của initializer khi xem như không nằm trong assignment context**, tức một standalone expression. Trái lại, biểu thức ở vế phải của khai báo có kiểu tường minh đôi khi được hỗ trợ bởi kiểu đích ở vế trái.

Sơ đồ:

```text
Khai báo tường minh:
List<String> xs = new ArrayList<>();
        |                  |
        +-- target type ---+--> diamond suy luận String
=> xs: List<String>

Khai báo với var:
var xs = new ArrayList<>();
              |
              +-- tự suy luận từ constructor không có đối số
=> xs: ArrayList<Object>
```

Sau khi thay:

1. Compiler kiểm tra biểu thức khởi tạo theo các quy tắc generic, overload và target typing.
2. Compiler suy luận kiểu tĩnh cho biến `var` từ kết quả đó.
3. Compiler kiểm tra các câu lệnh dùng biến dựa trên **kiểu mới**.
4. Nếu kiểu mới không phù hợp, một chỗ trước đây hợp lệ có thể báo lỗi; nếu kiểu mới rộng hơn, lỗi lại có thể xuất hiện xa hơn hoặc bị che khuất.

**Không có phép suy luận ngược từ các dòng sau:**

```java
var names = new ArrayList<>(); // ArrayList<Object>
names.add("A");                 // không khiến names thành ArrayList<String>
names.add("B");                 // vẫn ArrayList<Object>
```

## 4. Phân loại kết quả refactor

| Nhóm | Ví dụ thay thế | Điều xảy ra | Cách đánh giá |
| --- | --- | --- | --- |
| An toàn về kiểu nếu đủ ngữ cảnh | `String name = "Lan";` → `var name = "Lan";` | `name` vẫn là `String`. | Kiểm tra tên biến, độ rõ ràng và toàn bộ chỗ dùng. |
| Vẫn biên dịch nhưng đổi lớp khai báo | `List<String> xs = new ArrayList<>();` → `var xs = new ArrayList<String>();` | `List<String>` → `ArrayList<String>`. | Kiểm tra gán lại implementation, overload và ranh giới interface. |
| Vẫn biên dịch nhưng generic rộng ra | `List<String> xs = new ArrayList<>();` → `var xs = new ArrayList<>();` | Có thể thành `ArrayList<Object>`. | Nguy cơ mất kiểm tra kiểu phần tử. |
| Lỗi biên dịch ở dòng sau | `List<String> xs = new ArrayList<>(); String s = xs.get(0);` → `var xs = new ArrayList<>(); String s = xs.get(0);` | `get(0)` có kiểu `Object`; không gán cho `String`. | Giữ kiểu `String` bằng type witness/constructor tường minh hoặc giữ khai báo cũ. |
| Lỗi ngay ở initializer | `Predicate<String> p = s -> s.isBlank();` → `var p = s -> s.isBlank();` | Lambda không có target type. | Giữ functional interface tường minh. |
| Khác hành vi dù vẫn biên dịch | `Collection<String> xs = new ArrayList<>();` → `var xs = new ArrayList<String>();` | Overload được chọn có thể đổi do kiểu tĩnh đổi. | Kiểm tra overload và các test hành vi. |
| Giữ nguyên kiểu thực sự | `List<String> xs = List.of("Lan");` → `var xs = List.of("Lan");` | Hai kiểu tĩnh đều `List<String>`. | Có thể dùng `var` nếu initializer đủ rõ. |

Đừng gộp chung **lỗi biên dịch**, **thay đổi kiểu không mong muốn**, **cảnh báo unchecked/raw type** và **khác hành vi lúc chạy**. Mỗi loại cần một cách xử lý riêng.

## 5. Lỗi phổ biến nhất: mất target type khi dùng diamond `<>`

### 5.1. `ArrayList` không có dữ kiện kiểu phần tử

Trước:

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0); // Hợp lệ: String
```

Sau khi thay máy móc:

```java
var names = new ArrayList<>(); // ArrayList<Object>
names.add("An");
// String first = names.get(0); // LỖI: Object không gán được cho String
```

Chẩn đoán: không phải `get` bị hỏng. Kiểu phần tử đã thay từ `String` thành `Object` ngay tại khai báo `names`.

Các cách sửa hợp lệ:

```java
List<String> names = new ArrayList<>();   // Giữ interface + target typing
var names2 = new ArrayList<String>();     // Giữ generic String, kiểu biến ArrayList<String>
```

Chọn cách thứ nhất nếu muốn thể hiện hợp đồng `List<String>`; chọn cách thứ hai nếu kiểu cụ thể và mục đích của biến đều rõ.

### 5.2. Các collection có hai tham số kiểu

```java
Map<String, Integer> counts = new HashMap<>();
```

Nếu đổi thành:

```java
var counts = new HashMap<>(); // HashMap<Object,Object>
```

kiểu khóa và giá trị đều có thể bị suy luận là `Object`. Ví dụ:

```java
counts.put("apples", 3);
counts.put(100, "wrong kind"); // Có thể biên dịch; trái với hợp đồng ban đầu
```

Cách sửa có chủ đích:

```java
var counts = new HashMap<String, Integer>();
```

Lưu ý: trên một `Map<String,Integer>`, lời gọi `get` về mặt tham số khóa nhận `Object` theo API `Map`, nên không nên chỉ dựa vào `get(100)` để kiểm tra an toàn của kiểu khóa. Hãy kiểm tra cả `put`, `entrySet`, `getOrDefault`, kiểu trả về và các API tiêu thụ map.

### 5.3. Diamond không phải lúc nào cũng suy luận `Object`

```java
var names = new ArrayList<>(List.of("An", "Lan")); // ArrayList<String>
```

Constructor nhận một `Collection<String>`, nên có thông tin cho suy luận tham số kiểu. Ngược lại, `new ArrayList<>()` không có đối số và không có kiểu đích, nên `Object` là kết quả thông thường.

**Nguyên tắc:** xem **toàn bộ biểu thức khởi tạo**, đặc biệt đối số constructor, thay vì áp dụng quy tắc “cứ `var` + `<>` là lỗi”.

## 6. Generic factory method: gọi được nhưng trả kiểu khác

Java có nhiều phương thức generic mà tham số kiểu được quyết định một phần bởi **kiểu đích**.

### 6.1. `Collections.emptyList()`

Trước:

```java
List<String> names = Collections.emptyList();
String first = names.isEmpty() ? "none" : names.get(0);
```

Sau:

```java
var names = Collections.emptyList(); // List<Object>
// String first = names.isEmpty() ? "none" : names.get(0);
// Có thể lỗi kiểu: nhánh get trả Object, biểu thức điều kiện không cho String
```

Cách giữ kiểu:

```java
var names = Collections.<String>emptyList(); // List<String>
```

hoặc giữ `List<String> names = Collections.emptyList();` để thể hiện rõ ý định.

### 6.2. `List.of()`, `Set.of()`, `Map.of()` rỗng

```java
List<String> emptyNames = List.of();
var emptyUnknown = List.of();         // List<Object>
var emptyStrings = List.<String>of(); // List<String>

Map<String, Integer> emptyCounts = Map.of();
var emptyMap = Map.of();                      // Map<Object,Object>
var typedMap = Map.<String, Integer>of();     // Map<String,Integer>
```

Factory không có đối số khiến **đối số generic không có dữ kiện suy luận từ giá trị đầu vào**. Khai báo tường minh hoặc type witness giúp truyền đúng kiểu mong muốn.

Ngược lại:

```java
var names = List.of("An", "Lan");     // List<String>
var counts = Map.of("An", 1);         // Map<String,Integer>
```

Những initializer có đối số rõ ràng thường giữ được thông tin generic khi đổi sang `var`.

### 6.3. `Optional.empty()`

```java
Optional<String> maybeName = Optional.empty(); // Optional<String>
var maybeOther = Optional.empty();               // Optional<Object>
var maybeString = Optional.<String>empty();      // Optional<String>
```

Tác động dễ thấy:

```java
String first = maybeName.orElse("fallback"); // Hợp lệ
// String second = maybeOther.orElse("fallback"); // LỖI: kết quả Object
String third = maybeString.orElse("fallback"); // Hợp lệ
```

**Ghi nhớ:** Nếu generic method không có đủ đối số để xác định kiểu, việc mất target type ở vế trái thường làm kiểu suy luận rộng hơn mong muốn.

## 7. Mất target type làm lambda và method reference không biên dịch

Một lambda hoặc method reference trần **cần** functional interface làm kiểu đích.

Hợp lệ:

```java
Predicate<String> isBlank = s -> s.isBlank();
Function<String, Integer> length = String::length;
```

Không hợp lệ khi đổi trực tiếp:

```java
// var isBlank = s -> s.isBlank();   // LỖI: thiếu target type
// var length = String::length;      // LỖI: thiếu target type
```

Dù có dấu `=`, compiler không thể suy ra functional interface từ biểu thức lambda hay method reference độc lập. Cách tốt nhất khi kiểu hàm mang ý nghĩa là **giữ kiểu tường minh**.

Bạn có thể dùng một phép cast để tạo biểu thức có kiểu:

```java
var isBlank = (Predicate<String>) (s -> s.isBlank());
```

nhưng cách này thường kém dễ đọc hơn `Predicate<String> isBlank = ...`. Đừng coi ép kiểu là cách refactor mặc định.

**Phân biệt:** `var` cho **tham số lambda** (từ Java 11), ví dụ `(var s) -> s.isBlank()` bên trong một biểu thức đã có functional interface đích, là cơ chế khác. Nó không giúp `var predicate = s -> ...` trở nên hợp lệ.

## 8. Sửa lớp khai báo có thể khiến phép gán lại không hợp lệ

Thậm chí khi bạn đã giữ đúng tham số `String`, kiểu biến có thể hẹp hơn kiểu tường minh ban đầu.

```java
List<String> names = new ArrayList<>();
names = new LinkedList<>(); // Hợp lệ: List<String>
```

Thay bằng:

```java
var names = new ArrayList<String>(); // ArrayList<String>
// names = new LinkedList<String>();  // LỖI: LinkedList<String> không phải ArrayList<String>
```

Đây là **lỗi do kiểu khai báo cụ thể**; khác với lỗi `ArrayList<Object>` ở mục 5. Khi cần thay đổi implementation, giữ một biến khai báo bằng interface hoặc supertype phù hợp.

Một trường hợp khác:

```java
List<? extends Number> numbers = new ArrayList<Integer>();
numbers = new ArrayList<Double>(); // Hợp lệ: kiểu khai báo List<? extends Number>
```

Nếu thay bằng:

```java
var numbers = new ArrayList<Integer>(); // ArrayList<Integer>
// numbers = new ArrayList<Double>();    // LỖI: không cùng generic type
```

Ở đây biến `var` giữ **`ArrayList<Integer>`**, không tự suy luận wildcard `? extends Number` từ những phép gán về sau. Wildcard ở khai báo tường minh là một phần hợp đồng mà `var` không tự đoán.

**Đánh giá thêm:** `List<? extends Number>` chỉ bảo đảm đọc phần tử như `Number`; thông thường không được `add` giá trị `Integer`/`Double` tùy ý vì kiểu phần tử thực tế có thể là một subtype khác. Tránh dùng wildcard với kỳ vọng có thể sửa danh sách không giới hạn.

## 9. Overload: mã vẫn biên dịch nhưng hành vi có thể thay đổi

Java chọn phương thức overload theo **kiểu tĩnh tại điểm gọi**.

Giả sử có:

```java
static String inspect(Collection<?> items) { return "collection"; }
static String inspect(List<?> items) { return "list"; }
```

Với khai báo:

```java
Collection<String> items = new ArrayList<>();
System.out.println(inspect(items)); // chọn inspect(Collection<?>)
```

Nếu đổi dòng khai báo thành:

```java
var items = new ArrayList<String>();
System.out.println(inspect(items)); // chọn inspect(List<?>)
```

Thao tác gọi `inspect(items)` không đổi, nhưng kiểu tĩnh của `items` đã đổi từ `Collection<String>` sang `ArrayList<String>`. `inspect(List<?>)` cụ thể hơn `inspect(Collection<?>)` nên có thể được chọn.

Điều này là **rủi ro thay đổi hành vi âm thầm**, không nhất thiết gây lỗi biên dịch. Vì vậy, review refactor sang `var` phải xem những nơi biến được truyền vào API có overload. Không dựa vào lớp runtime để dự đoán overload: lựa chọn overload diễn ra tại lúc biên dịch.

## 10. Raw type, unchecked warnings và generic type safety

### 10.1. `var` không tự sửa raw type

```java
List<String> names = new ArrayList(); // Raw ArrayList, có unchecked warning
```

Đổi thành:

```java
var names = new ArrayList(); // Kiểu raw ArrayList; generic type safety bị mất
```

Không phải vì `var` “sai”, mà vì initializer đã dùng **raw type**. Đây vẫn là cách dùng không nên ưu tiên trong mã Java hiện đại khi có thể viết generic đầy đủ.

Cách sửa:

```java
var names = new ArrayList<String>(); // ArrayList<String>
```

hoặc:

```java
List<String> names = new ArrayList<>();
```

Hãy chạy `javac -Xlint:unchecked` trong trường hợp nghi có raw type/unchecked conversion; các warning này có thể chỉ ra nơi mất bảo đảm kiểu.

### 10.2. Mất generic có thể làm lỗi xuất hiện muộn

```java
var values = new ArrayList<>(); // ArrayList<Object>
values.add("An");
values.add(15);
Object value = values.get(1);    // Hợp lệ, nhưng đầu ra không được bảo đảm là String
```

Nếu về sau lập trình viên ép kiểu:

```java
// String name = (String) values.get(1); // Biên dịch nhưng có thể gây ClassCastException
```

Đây là **rủi ro runtime do ép kiểu sai**. Không nên sửa lỗi kiểu tĩnh `Object` → `String` bằng cast tùy tiện; hãy sửa **nguồn suy luận generic**.

### 10.3. Kiểu element có thể đủ chặt nhưng lớp biến khác

```java
var names = new ArrayList<>(List.of("An")); // ArrayList<String>
```

Phần tử `String` được giữ, nhưng kiểu của biến vẫn là **`ArrayList<String>`**, không phải `List<String>`. Chỉ kiểm tra kiểu phần tử là chưa đủ khi ranh giới interface có ý nghĩa.

## 11. Những khác biệt tinh tế khác

### 11.1. Generic invariance không biến mất

`List<Integer>` **không phải** subtype của `List<Number>`, dù `Integer` là subtype của `Number`.

```java
List<Number> numbers = new ArrayList<>();
numbers.add(1);
numbers.add(2.5);
```

Không thể thay thành:

```java
var numbers = new ArrayList<Integer>();
numbers.add(1);
// numbers.add(2.5); // LỖI: phần tử phải là Integer
```

Nếu mục tiêu là chứa nhiều subtype của `Number`, giữ `List<Number>` hoặc khởi tạo bằng `new ArrayList<Number>()` theo ý định.

### 11.2. Kiểu trả về của phương thức, không phải lớp thực tế bên trong

```java
static List<String> loadNames() {
    return new ArrayList<>(List.of("An"));
}
```

`var names = loadNames();` có kiểu `List<String>`. Dù hiện tại bên trong phương thức trả một đối tượng `ArrayList`, nó **không** làm kiểu biến trở thành `ArrayList<String>`. Trường hợp này thường an toàn hơn khi dùng `var`, vì chữ ký phương thức đã cố định hợp đồng.

Nếu thay initializer `loadNames()` bằng `new ArrayList<String>()`, lúc đó **kiểu được suy luận** có thể đổi sang `ArrayList<String>`; phải đánh giá lại những chỗ dùng.

### 11.3. Kiểu anonymous class có thể được suy luận

```java
Object holder = new Object() {
    int answer() { return 42; }
};
// holder.answer(); // LỖI: kiểu tĩnh của holder là Object
```

Thay bằng:

```java
var holder = new Object() {
    int answer() { return 42; }
};
int x = holder.answer(); // Hợp lệ: var có thể suy luận kiểu lớp ẩn danh
```

Đây là trường hợp `var` có thể suy luận một kiểu khó hoặc không thể viết tên tường minh. Tuy hợp lệ, hãy cân nhắc độ rõ ràng và phạm vi biến; không nên coi `var` là phép thay cú pháp luôn bảo toàn API khả dụng.

### 11.4. Intersection và wildcard/capture

Khi initializer liên quan tới wildcard, intersection type hoặc capture conversion, kiểu được suy luận có thể **phức tạp hơn `Object`**. Java áp dụng các quy tắc type projection để không giữ những biến kiểu capture tổng hợp vượt khỏi phạm vi phù hợp. Không suy luận bằng mắt rằng tất cả generic phức tạp sẽ trở thành `Object`. Hãy xem kiểu thực tế trong IDE hoặc kiểm tra với `javac` và hợp đồng API.

## 12. Ví dụ Java 17+ chạy độc lập: phát hiện thay đổi kiểu

Tạo tệp **`VarGenericReviewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class VarGenericReviewDemo {
    static String inspect(Collection<?> values) {
        return "collection";
    }

    static String inspect(List<?> values) {
        return "list";
    }

    static List<String> loadNames() {
        return new ArrayList<>(List.of("Mai"));
    }

    public static void main(String[] args) {
        List<String> explicit = new ArrayList<>();
        explicit.add("Lan");
        String first = explicit.get(0);

        var unconstrained = new ArrayList<>(); // ArrayList<Object>
        unconstrained.add("Lan");
        unconstrained.add(42);

        var typed = new ArrayList<String>();
        typed.add("An");

        List<String> emptyExplicit = Collections.emptyList();
        var emptyInferred = Collections.emptyList(); // List<Object>
        var emptyTyped = Collections.<String>emptyList();

        var optionalUnconstrained = Optional.empty(); // Optional<Object>
        var optionalTyped = Optional.<String>empty();

        Collection<String> asCollection = new ArrayList<>(List.of("X"));
        var asConcrete = new ArrayList<String>(List.of("X"));

        List<String> changeable = new ArrayList<>();
        changeable = new LinkedList<>(List.of("Binh"));

        var viaMethod = loadNames(); // List<String>
        viaMethod = new LinkedList<>(List.of("Hoa"));

        var map = Map.of("Lan", 1); // Map<String,Integer>

        System.out.println("first=" + first);
        System.out.println("unconstrained=" + unconstrained);
        System.out.println("typed=" + typed);
        System.out.println("emptyExplicit=" + emptyExplicit.size());
        System.out.println("emptyInferred=" + emptyInferred.size());
        System.out.println("emptyTyped=" + emptyTyped.size());
        System.out.println("optionalUnconstrained=" + optionalUnconstrained.isEmpty());
        System.out.println("optionalTyped=" + optionalTyped.isEmpty());
        System.out.println("overloadExplicit=" + inspect(asCollection));
        System.out.println("overloadVar=" + inspect(asConcrete));
        System.out.println("changeable=" + changeable);
        System.out.println("viaMethod=" + viaMethod);
        System.out.println("map=" + map.get("Lan"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 VarGenericReviewDemo.java
java VarGenericReviewDemo
```

Stdout dự kiến chính xác:

```text
first=Lan
unconstrained=[Lan, 42]
typed=[An]
emptyExplicit=0
emptyInferred=0
emptyTyped=0
optionalUnconstrained=true
optionalTyped=true
overloadExplicit=collection
overloadVar=list
changeable=[Binh]
viaMethod=[Hoa]
map=1
```

**Giải thích:**

1. `explicit` có kiểu `List<String>` và `get` trả `String`; `unconstrained` là `ArrayList<Object>` nên giữ cả chuỗi và số.
2. `typed` dùng constructor ghi rõ `String`; compiler bảo đảm không thêm một `Integer` trực tiếp vào nó.
3. `emptyExplicit` và `emptyTyped` là `List<String>`; `emptyInferred` là `List<Object>`. Kích thước đều bằng 0, nên **stdout không đủ để chứng minh kiểu**; phải xét khai báo và kiểm tra biên dịch.
4. `optionalUnconstrained` có kiểu `Optional<Object>` còn `optionalTyped` là `Optional<String>`.
5. `inspect(asCollection)` và `inspect(asConcrete)` chọn overload khác nhau vì kiểu tĩnh của đối số khác nhau.
6. `changeable` và `viaMethod` đều có kiểu `List<String>` nên gán lại `LinkedList<String>` hợp lệ.
7. `Map.of("Lan", 1)` có đối số xác định được cả kiểu khóa và kiểu giá trị.

Trong chương trình này không có phép duyệt collection/map với thứ tự không bảo đảm. Dòng in map chỉ đọc giá trị bằng một khóa cụ thể, nên stdout xác định.

## 13. Ví dụ lỗi biên dịch cần nhận diện

Các đoạn này **cố ý không biên dịch** khi dùng như được viết; hãy thử riêng và không chèn trực tiếp vào chương trình chạy ở mục 12.

### Lỗi A: `Object` thay cho `String`

```java
var names = new ArrayList<>();
names.add("An");
String first = names.get(0); // incompatible types: Object cannot be converted to String
```

**Sửa:** `var names = new ArrayList<String>();` hoặc `List<String> names = new ArrayList<>();`.

### Lỗi B: generic factory method thiếu target type

```java
var names = Collections.emptyList();
String name = names.get(0); // Object không thể gán cho String
```

**Sửa:** `var names = Collections.<String>emptyList();`; lưu ý `get(0)` trên danh sách rỗng sẽ ném `IndexOutOfBoundsException` **nếu chạy đến đó**, nên ví dụ chỉ nhằm minh họa lỗi kiểu và phải bổ sung phần tử/kiểm tra rỗng trong mã ứng dụng.

### Lỗi C: hai implementation của cùng interface

```java
var names = new ArrayList<String>();
names = new LinkedList<String>(); // incompatible types
```

**Sửa:** `List<String> names = new ArrayList<>();`.

### Lỗi D: kiểu hàm bị mất

```java
var check = s -> s.isEmpty(); // lambda needs a target type
```

**Sửa:** `Predicate<String> check = s -> s.isEmpty();` (có import `java.util.function.Predicate`).

### Lỗi E: raw type và unchecked cast

```java
var names = new ArrayList(); // raw ArrayList
names.add(7);
String name = (String) names.get(0); // có thể ném ClassCastException nếu chạy
```

**Sửa:** dùng generic đúng từ constructor/khai báo; tránh ép kiểu mù để vá hậu quả.

## 14. Quy trình review khi chuyển khai báo tường minh sang `var`

### Bước 1: Ghi lại kiểu tĩnh và generic ban đầu

Ví dụ: `Map<String, List<Integer>> data = ...;`. Xác định đầy đủ các tầng `String`, `List<Integer>`, interface và wildcard; đừng chỉ ghi “Map”.

### Bước 2: Tính kiểu initializer nếu không có vế trái tường minh

Hỏi: Diamond `<>` còn đủ dữ kiện từ đối số constructor không? Generic method có tham số giá trị hay type witness không? Lambda/method reference có target type ở đâu?

### Bước 3: So sánh cả kiểu outer và inner

`List<String>` khác `ArrayList<String>` về kiểu outer; `ArrayList<String>` khác `ArrayList<Object>` về kiểu phần tử. Cả hai sự thay đổi đều quan trọng.

### Bước 4: Kiểm tra từng điểm sử dụng

Tập trung vào:

- `get`, `iterator`, `stream`, `map`, `orElse` và nơi nhận giá trị generic.
- `add`, `put`, `set` và nơi đưa dữ liệu mới vào collection.
- Gán lại `ArrayList` ↔ `LinkedList`, thay kiểu implementer.
- Lời gọi overload có tham số interface/lớp cụ thể.
- Method reference/lambda, generic factories không đối số.
- Các cast, unchecked warning và chỗ có thể ném `ClassCastException`.

### Bước 5: Biên dịch, bật warning và chạy test mang ý nghĩa

Ví dụ:

```bash
javac --release 17 -Xlint:unchecked VarGenericReviewDemo.java
java VarGenericReviewDemo
```

Với dự án nhiều module, thực hiện build/test theo công cụ thực tế (Maven, Gradle hoặc pipeline của dự án). Lỗi kiểu được compiler phát hiện sớm, nhưng thay đổi overload hay “mất rào chắn generic” cần bài test hành vi và review ý định.

### Bước 6: Chỉ giữ `var` khi lợi ích rõ ràng

Một số trường hợp đáng giữ:

```java
var result = List.of("An", "Lan");        // List<String>
var names = new ArrayList<String>();     // ArrayList<String>
var count = names.size();                // int
```

Một số trường hợp nên giữ kiểu tường minh:

```java
List<String> names = new ArrayList<>();            // Giữ interface/target typing
Map<String, Integer> counts = new HashMap<>();     // Giữ kiểu generic cả khóa lẫn giá trị
Predicate<String> predicate = s -> s.isBlank();    // Lambda có target type
List<? extends Number> numbers = new ArrayList<Integer>(); // Giữ wildcard có ý nghĩa
```

Không có quy tắc “dùng `var` ở mọi chỗ” hoặc “cấm `var` với generic”. Hãy chọn cú pháp **giữ hợp đồng kiểu, an toàn biên dịch và khả năng đọc mã**.

## 15. Luyện tập tự kiểm tra

Mỗi câu sau là **một tình huống độc lập**; nếu nhiều lựa chọn dùng cùng tên biến, chúng thay thế nhau chứ không nằm trong một khối.

**Câu 1.** `List<String> words = new ArrayList<>();` được đổi thành `var words = new ArrayList<>();`. Hai điều gì đã thay đổi về kiểu?

**Câu 2.** `var words = new ArrayList<>(List.of("A"));` có nhất thiết là `ArrayList<Object>` không? Vì sao?

**Câu 3.** `Optional<String> value = Optional.empty();` được đổi thành `var value = Optional.empty();`. Kiểu mới là gì và sửa thế nào?

**Câu 4.** Vì sao `Predicate<String> p = s -> s.isBlank();` hợp lệ nhưng `var p = s -> s.isBlank();` không hợp lệ?

**Câu 5.** `List<String> xs = new ArrayList<>(); xs = new LinkedList<>();` chuyển thành `var xs = new ArrayList<String>(); xs = new LinkedList<>();` có còn hợp lệ không?

**Câu 6.** Vì sao `Collection<String> xs = new ArrayList<>(); inspect(xs);` và `var xs = new ArrayList<String>(); inspect(xs);` có thể in khác nhau khi tồn tại overload `inspect(Collection<?>)` và `inspect(List<?>)`?

**Câu 7.** `var map = new HashMap<>();` có bảo đảm `Map<String,Integer>` khi các lệnh sau chỉ `put("A", 1)` không?

**Câu 8.** `List<String> names = loadNames();` đổi thành `var names = loadNames();` có thể giữ nguyên kiểu khi nào?

**Đáp án và lý do:**

1. Kiểu outer từ `List` sang `ArrayList` và kiểu phần tử từ `String` sang `Object`, vì initializer thiếu target type và đối số.
2. Không. `List.of("A")` cho dữ kiện `String` vào constructor, nên suy luận `ArrayList<String>`.
3. `Optional<Object>`; dùng `Optional<String> value = Optional.empty();` hoặc `var value = Optional.<String>empty();`.
4. Lambda cần functional interface đích; `var` không cung cấp target type cho lambda trần.
5. Không. `xs` giờ là `ArrayList<String>`; nên giữ `List<String>` nếu muốn gán `LinkedList<String>`.
6. Chọn overload lúc biên dịch theo kiểu tĩnh: `Collection` trong bản đầu, `ArrayList` (phù hợp overload `List` cụ thể hơn) trong bản sau.
7. Không. `HashMap<Object,Object>` không tự trở thành `HashMap<String,Integer>` từ các lệnh `put` về sau.
8. Khi chữ ký `loadNames()` khai báo trả về `List<String>` và initializer là lời gọi ấy. Nếu sửa initializer sang constructor lớp cụ thể, phải đánh giá lại.

## 16. Tổng kết và tài liệu áp dụng hiện nay

- Việc đổi **`Type<T> x = initializer;`** sang **`var x = initializer;`** có thể thay **kiểu tĩnh** và làm mất **target type** cho generic inference.
- **`var x = new ArrayList<>()`** với constructor rỗng khác với **`List<String> x = new ArrayList<>()`**; đừng cho rằng compiler đọc được ý định từ các dòng phía sau.
- Hai nhóm lỗi lớn: **lỗi biên dịch** (không gán được `Object` cho `String`, thiếu target type lambda, gán khác implementation) và **thay đổi vẫn biên dịch** (generic rộng thành `Object`, overload đổi, raw type/warning).
- Các cách giữ an toàn: viết **kiểu tường minh**, ghi **tham số kiểu trong constructor** hoặc dùng **type witness** như `Collections.<String>emptyList()`.
- `var` vẫn hữu ích khi initializer cho kiểu rõ ràng; review cần kiểm tra cả kiểu outer, tham số generic, overload, tính mutable và toàn bộ nơi sử dụng.

Nguồn chính thức:

1. [Java Language Specification, Java SE 26 — `14.4: Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4): loại kiểu được suy luận với `var` và cách xét initializer như standalone expression.
2. [Java Language Specification, Java SE 26 — `15.9: Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.9): diamond và ngữ cảnh kiểu.
3. [Java Language Specification, Java SE 26 — `15.12: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.12): chọn overload và kiểu của lời gọi.
4. [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): cơ sở thiết kế của `var` trong Java 10.
5. [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): đánh giá khi nào kiểu suy luận giúp hoặc cản trở khả năng đọc mã.
