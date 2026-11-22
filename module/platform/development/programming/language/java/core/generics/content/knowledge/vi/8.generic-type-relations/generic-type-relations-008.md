# Tách quan hệ kiểu con khỏi phép ép kiểu và chuyển đổi không kiểm tra trong Java Generics

## 1. Vì sao phải phân biệt ba khái niệm?

Khi đọc các đoạn code generics, rất dễ kết luận sai rằng “gán được” hoặc “ép kiểu được” đồng nghĩa với “là kiểu con”. Java sử dụng **ba cơ chế có ý nghĩa khác nhau**:

1. **Quan hệ kiểu con (subtyping):** một quan hệ giữa các *kiểu* do hệ thống kiểu định nghĩa, thường ký hiệu `S <: T` (“`S` là subtype của `T`”). Quan hệ này có thể giúp một biểu thức kiểu `S` được dùng ở vị trí chấp nhận `T`.
2. **Phép ép kiểu (cast):** cú pháp tường minh `(T) expression` yêu cầu chuyển giá trị biểu thức sang cách nhìn kiểu `T`. Phép cast có thể hợp lệ nhưng thất bại ở runtime; bản thân việc cast được **không chứng minh** `S <: T`.
3. **Chuyển đổi không kiểm tra (unchecked conversion):** Java cho phép một số chuyển đổi từ **raw type** sang **parameterized type** mà không thể chứng minh đầy đủ tham số kiểu. Chuyển đổi có thể xảy ra ngầm trong phép gán hoặc lời gọi phương thức và thường phát ra cảnh báo `[unchecked]`.

Ngoài ra còn có **unchecked cast**: phép cast *tường minh* đến kiểu parameterized mà runtime không thể kiểm tra đầy đủ type argument. “Unchecked conversion” và “unchecked cast” liên quan nhưng **không phải cùng một thao tác**.

Mục tiêu là nhìn một dòng Java và trả lời đúng: đang dựa vào subtyping, đang yêu cầu một cast có kiểm tra runtime, hay đang chấp nhận một thao tác không thể kiểm tra đầy đủ?

## 2. Bản đồ khái niệm

| Ví dụ | Phân loại chính | Compiler xử lý | Runtime có thể xác nhận gì? |
| --- | --- | --- | --- |
| `String text = "Java"; Object x = text;` | Subtyping `String <: Object` và widening reference conversion | Hợp lệ, không cảnh báo unchecked | Không cần kiểm tra downcast. |
| `List<String> a = new ArrayList<>(); Collection<String> b = a;` | Subtyping `List<String> <: Collection<String>` | Hợp lệ, không cảnh báo unchecked | Giữ nguyên tham chiếu. |
| `List<Integer> a = List.of(1); List<? extends Number> b = a;` | Subtyping thông qua wildcard/type-argument containment | Hợp lệ, không cảnh báo unchecked | Không cần kiểm tra type argument ở runtime. |
| `Object x = "Java"; String s = (String) x;` | Checked reference cast | Hợp lệ | Kiểm tra đối tượng thực sự là `String`. |
| `List raw = new ArrayList<Integer>(); List<String> b = raw;` | Unchecked conversion (gán ngầm) | Cảnh báo unchecked conversion | Không xác nhận phần tử là `String`. |
| `Object x = List.of(1); List<String> b = (List<String>) x;` | Unchecked cast (ép kiểu tường minh) | Cảnh báo unchecked cast | Có thể kiểm tra đối tượng là `List`, nhưng không kiểm tra `String` trong `List<String>`. |

**Đừng đồng nhất “có conversion” với “là subtype”.** Gán biến có thể được chấp nhận nhờ widening conversion hoặc, trong trường hợp đặc biệt của generics với raw type, unchecked conversion. Casting context lại cho phép thêm các phép chuyển đổi cần cast tường minh. Quan hệ subtype tự nó không thay đổi vì xuất hiện một cú pháp cast.

## 3. Subtyping với generic type: bất biến (invariance)

Trong Java, `Integer <: Number`, nhưng **`List<Integer>` không phải subtype của `List<Number>`**. Đây là tính bất biến của các type argument cụ thể trong một generic type như `List<E>`.

Ví dụ minh họa **không biên dịch**:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // LỖI biên dịch: incompatible types
~~~

Tại sao phải cấm? Nếu gán được, người dùng biến `numbers` sẽ có thể gọi `numbers.add(3.14)` (một `Double`) và vô tình chèn `Double` vào danh sách ban đầu được khai báo `List<Integer>`. Hệ thống kiểu ngăn việc đó từ compile time.

### 3.1. Hai đường subtyping hợp lệ thường bị bỏ qua

**Thứ nhất, quan hệ kế thừa của *generic declaration* được giữ khi tham số kiểu tương thích:**

~~~java
ArrayList<String> arrayList = new ArrayList<>();
List<String> list = arrayList;
Collection<String> collection = list;
Iterable<String> iterable = collection;
~~~

`ArrayList<String> <: List<String> <: Collection<String> <: Iterable<String>` là những quan hệ hợp lệ. Không có unchecked warning và không có copy dữ liệu.

**Thứ hai, wildcard tạo một kiểu đích trừu tượng hơn:**

~~~java
List<Integer> integers = List.of(10, 20);
List<? extends Number> numericView = integers;
List<?> unknownView = integers;

Number first = numericView.get(0);
Object another = unknownView.get(1);
~~~

`List<Integer>` có thể được xem là `List<? extends Number>` và `List<?>` theo quy tắc type-argument containment của JLS. Đây là chuyển đổi an toàn dựa trên hệ thống kiểu, không phải unchecked conversion.

- `List<? extends Number>`: đọc được mỗi phần tử như `Number`, nhưng không được tùy tiện `add(Integer)` hay `add(Double)` vì loại phần tử cụ thể có thể là subtype khác của `Number`.
- `List<? super Integer>`: có thể `add(Integer)`; khi đọc chỉ bảo đảm kiểu `Object`.
- `List<?>`: có thể đọc dưới dạng `Object`; không thể thêm một giá trị khác `null` khi không biết kiểu phần tử.

Đây là nguyên tắc thường gọi là **PECS**: producer → `extends`, consumer → `super`. PECS giúp mô tả API mà không cần ép kiểu không an toàn.

### 3.2. Cần danh sách `Number` thật sự? Hãy tạo bản sao đúng kiểu

~~~java
List<Integer> integers = List.of(10, 20);
List<Number> numbers = new ArrayList<>(integers);
numbers.add(2.5); // Hợp lệ: numbers là một danh sách riêng, chứa Number
~~~

Constructor `ArrayList(Collection<? extends E>)` cho phép nhận một collection chứa phần tử subtype của `E`. Đoạn này **tạo danh sách mới**, không hề biến danh sách `List<Integer>` ban đầu thành subtype của `List<Number>`.

## 4. Cast có kiểm tra: hợp lệ về cú pháp không đồng nghĩa an toàn runtime

Ví dụ:

~~~java
Object value = "Java";
String text = (String) value; // Cast thành công

Object another = Integer.valueOf(42);
String wrong = (String) another; // ClassCastException tại dòng này
~~~

Với phép cast từ `Object` sang kiểu không parameterized như `String`, JVM kiểm tra loại đối tượng thực tế. Compiler chấp nhận cả hai cú pháp cast; thành bại phụ thuộc giá trị lúc chạy.

Các điểm cần nhớ:

- Một cast không tạo ra đối tượng mới và không chuyển một `Integer` thành `String`; nó chỉ yêu cầu tham chiếu thỏa loại đích.
- `(String) value` là cast có kiểm tra (checked reference cast). Khi đối tượng không phù hợp, runtime ném `ClassCastException`.
- Cast `null` sang một kiểu tham chiếu hợp lệ cho ra `null`, không ném `ClassCastException` tại bước cast; thao tác giải tham chiếu sau đó vẫn có thể ném `NullPointerException`.
- Không phải mọi cast đều được compiler cho phép. Ví dụ chuyển giữa hai kiểu không tương thích rõ ràng có thể bị báo lỗi ngay lúc biên dịch.

**Vì vậy, “compiler cho phép cast `(T) x`” không xác lập một quan hệ `type(x) <: T`**.

## 5. Unchecked conversion: chuyển đổi ngầm từ raw type

**Raw type** là dạng sử dụng tên generic mà không cung cấp type argument, ví dụ `List` thay vì `List<String>`. Java hỗ trợ raw type để tương thích chương trình/thư viện cũ, nhưng điều này làm mất thông tin về kiểu phần tử.

~~~java
List<Integer> integers = new ArrayList<>(List.of(10));
List raw = integers;             // Mất thông tin type argument ở biểu thức raw.
List<String> strings = raw;      // UNCHECKED CONVERSION, không cần viết cast.
~~~

Lệnh `javac -Xlint:unchecked` sẽ chỉ ra **unchecked conversion** tại phép gán cuối. Compiler không thể chứng minh `raw` chỉ chứa `String`, nhưng cho phép gán để hỗ trợ mã legacy.

Dòng `List raw = integers;` không đòi unchecked conversion: các parameterization của `List` có thể được sử dụng như raw `List`. Nguy cơ xuất hiện khi coi raw `List` là `List<String>`, hoặc khi ghi/đọc phần tử qua raw API.

Lời gọi phương thức cũng có thể phát sinh unchecked conversion nếu đối số raw được truyền vào tham số generic tương ứng:

~~~java
static void printStrings(List<String> items) {
    for (String item : items) {
        System.out.println(item);
    }
}

// Ở nơi gọi:
List raw = List.of(1, 2);
printStrings(raw); // Cảnh báo unchecked conversion; có thể lỗi khi sử dụng phần tử.
~~~

Đoạn thứ hai chỉ minh họa một lời gọi, không phải chương trình độc lập. Không nên “chữa” unchecked warning bằng cách bỏ luôn type argument hoặc sử dụng raw type ở toàn bộ hệ thống.

## 6. Unchecked cast: có toán tử `(T)` nhưng không kiểm tra đủ generic argument

Ví dụ:

~~~java
Object value = List.of(10, 20);
List<String> strings = (List<String>) value; // UNCHECKED CAST
~~~

`value` đang giữ một `List<Integer>`. Sau type erasure, runtime biết đây là một implementation của `List`, nhưng **không có bằng chứng runtime để xác nhận các phần tử là `String`**. Vì vậy phép cast có thể vượt qua bước kiểm tra runtime của kiểu `List`, còn lỗi `ClassCastException` xuất hiện khi đọc một phần tử như `String`.

Hai câu sau **khác nhau về cú pháp và loại cảnh báo**:

~~~java
List raw = List.of(1, 2);
List<String> viaConversion = raw;                 // Unchecked conversion
List<String> viaCast = (List<String>) (Object) raw; // Unchecked cast
~~~

Cast không “rửa” dữ liệu hay chứng minh một quan hệ subtyping mới. Nó có thể khiến lỗi khó phát hiện hơn vì mã tiếp tục chạy cho tới thời điểm đọc/ghi phần tử không phù hợp.

### 6.1. Type erasure và reifiable type

Trong Java generics, type arguments như `String` hoặc `Integer` thường bị xóa ở biểu diễn runtime của generic class. Hai đối tượng `new ArrayList<String>()` và `new ArrayList<Integer>()` cùng có lớp runtime `ArrayList`.

~~~java
Object unknown = List.of("a", "b");

boolean isList = unknown instanceof List<?>; // Hợp lệ.
List<?> view = (List<?>) unknown;             // Có thể kiểm tra List ở runtime.
~~~

Ngược lại, cú pháp sau **không hợp lệ**:

~~~java
// SAI: List<String> không phải kiểu reifiable dùng được cho instanceof.
if (unknown instanceof List<String>) {
    System.out.println("strings");
}
~~~

`List<?>` là reifiable theo quy định JLS, vì nó chỉ dùng wildcard không giới hạn; điều đó **không** bảo đảm mọi phần tử thuộc kiểu cụ thể nào. Nếu cần `List<String>` thật, hãy kiểm tra từng phần tử hoặc khởi tạo collection an toàn từ nguồn đã được định kiểu.

### 6.2. Heap pollution: nguyên nhân và thời điểm lỗi

**Heap pollution** xảy ra khi một biến khai báo kiểu parameterized tham chiếu đến dữ liệu thực tế không phù hợp với kiểu đó. Nó có thể được đưa vào qua raw type, unchecked conversion/cast, một số thao tác mảng có generic varargs hoặc cơ chế không an toàn khác.

~~~java
List<Integer> integers = new ArrayList<>(List.of(10));
List raw = integers;
List<String> strings = raw; // Unchecked warning; đã có nguy cơ heap pollution.
String first = strings.get(0); // ClassCastException ở bước dùng Integer như String.
~~~

Compiler chèn kiểm tra/cast cần thiết ở chỗ sử dụng kết quả `get(0)` để đáp ứng `String`. Việc thất bại ở đây không có nghĩa `List<Integer>` đã từng là subtype của `List<String>`. Ngược lại, unchecked conversion **bỏ qua được một phần bảo đảm tĩnh** và đẩy lỗi sang runtime.

Một unchecked warning không đồng nghĩa chắc chắn có lỗi; nếu dữ liệu raw tình cờ chứa đúng các giá trị cần thiết, chương trình có thể chạy. Nhưng compiler không thể chứng minh điều đó từ kiểu khai báo.

## 7. Ví dụ Java 17+ biên dịch và chạy được

Tạo tệp **GenericRelationsDemo.java** với nội dung sau:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericRelationsDemo {
    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(10, 20));
        List<? extends Number> readable = integers;
        List<?> anything = integers;
        System.out.println("subtype: " + readable.get(0));
        System.out.println("unknown: " + anything.get(1));

        List<Number> copied = new ArrayList<>(integers);
        copied.add(2.5);
        System.out.println("copy: " + copied);

        Object value = "Java";
        String text = (String) value;
        System.out.println("checked cast: " + text);

        try {
            String bad = (String) (Object) 42;
            System.out.println(bad);
        } catch (ClassCastException e) {
            System.out.println("checked cast: failed");
        }

        List raw = integers;
        List<String> assumedStrings = raw;
        try {
            System.out.println(assumedStrings.get(0).length());
        } catch (ClassCastException e) {
            System.out.println("unchecked conversion: failed on element read");
        }

        Object unknown = new ArrayList<>(List.of(1, 2));
        List<String> claimedStrings = (List<String>) unknown;
        try {
            System.out.println(claimedStrings.get(0).length());
        } catch (ClassCastException e) {
            System.out.println("unchecked cast: failed on element read");
        }
        System.out.println("reifiable test: " + (unknown instanceof List<?>));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:unchecked GenericRelationsDemo.java
java GenericRelationsDemo
~~~

Lệnh `javac` **thành công** nhưng ghi hai cảnh báo vào stderr:

- `unchecked conversion` tại `List<String> assumedStrings = raw;`.
- `unchecked cast` tại `List<String> claimedStrings = (List<String>) unknown;`.

Bỏ qua vị trí đường dẫn/tên tệp trong stderr, hai cảnh báo này có nội dung khác nhau. Chương trình vẫn chạy và in ra stdout **chính xác**:

~~~text
subtype: 10
unknown: 20
copy: [10, 20, 2.5]
checked cast: Java
checked cast: failed
unchecked conversion: failed on element read
unchecked cast: failed on element read
reifiable test: true
~~~

Giải thích các điểm chính: hai phép gán sang wildcard được hệ thống kiểu chấp nhận an toàn; bản sao `List<Number>` có thể nhận `Double`; cast `Object` sang `String` được kiểm tra; hai phép thao tác generic mất an toàn không lỗi ngay khi gán/cast sang `List<String>`, mà lỗi khi runtime phải sử dụng phần tử `Integer` như `String`.

## 8. Thiết kế API tránh unchecked conversion và unchecked cast

### 8.1. Diễn đạt đúng nhu cầu bằng wildcard

Nếu chỉ đọc các số, dùng `List<? extends Number>` thay vì `List<Number>`:

~~~java
static double sum(List<? extends Number> values) {
    double result = 0.0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}

// sum(List.of(1, 2, 3)) hợp lệ với List<Integer>.
~~~

Nếu thêm các số nguyên vào bộ chứa, dùng `List<? super Integer>`:

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

Có thể truyền `List<Integer>`, `List<Number>` hoặc `List<Object>` tới `addDefaults`. Đây là quan hệ kiểu hợp lệ, không yêu cầu unchecked cast.

### 8.2. Cần kiểm tra dữ liệu không rõ kiểu? Kiểm tra từng phần tử

~~~java
static List<String> requireStrings(List<?> source) {
    List<String> copy = new ArrayList<>();
    for (Object element : source) {
        copy.add(String.class.cast(element));
    }
    return copy;
}
~~~

Đây là ví dụ về *phương thức thành viên* (cần đặt trong lớp và import `List`, `ArrayList` để chạy độc lập). `String.class.cast(element)` kiểm tra từng phần tử thực tế. Nếu tất cả hợp lệ, kết quả là `List<String>` riêng biệt mà không cần unchecked cast. Nếu gặp phần tử không phải `String`, lỗi xuất hiện ngay tại vị trí kiểm tra, dễ chẩn đoán hơn.

Trong ứng dụng thực tế, có thể quyết định từ chối dữ liệu lỗi, thu thập danh sách lỗi, hoặc chuyển đổi kiểu có chủ đích; nhưng phải gọi đúng nó là **validation/conversion của dữ liệu**, không gọi là “ép kiểu generic an toàn” trên toàn collection.

### 8.3. Khi phải tương tác với API legacy/raw

Nếu nguồn chỉ cung cấp raw `List`, hãy cố gắng sửa chữ ký API thành generic hoặc tạo adapter kiểm tra dữ liệu. Trường hợp đã có bằng chứng bất biến từ hệ thống bên ngoài và buộc sử dụng unchecked cast, `@SuppressWarnings("unchecked")` chỉ nên đặt ở phạm vi nhỏ nhất cùng chú thích giải thích vì sao cast an toàn.

`@SuppressWarnings("unchecked")` chỉ **ẩn cảnh báo**, không thêm runtime check, không biến raw type thành parameterized subtype, và không ngăn `ClassCastException`.

## 9. Các kết luận sai thường gặp

| Kết luận sai | Điều đúng |
| --- | --- |
| “`Integer extends Number` nên `List<Integer> extends List<Number>`.” | Generic type arguments cụ thể là invariant; dùng wildcard hoặc tạo bản sao đúng kiểu. |
| “Có thể cast thì chắc chắn là subtype.” | Cast context cho phép narrowing conversion; loại thật có thể không phù hợp và ném `ClassCastException`. |
| “Cast `List<Integer>` thành `List<String>` sẽ đổi kiểu phần tử.” | Không có phép biến đổi phần tử nào xảy ra; erasure ngăn kiểm tra đầy đủ type arguments. |
| “Chỉ cast tường minh mới có `unchecked`.” | Gán một raw `List` cho `List<String>` cũng là unchecked conversion. |
| “`instanceof List<?>` chứng minh đây là `List<String>`.” | Chỉ chứng minh đối tượng thuộc một implementation của `List`, không chứng minh kiểu phần tử. |
| “Đã biên dịch được nghĩa là kiểu khai báo ở runtime luôn đúng.” | Unchecked conversion có thể dẫn tới heap pollution; lỗi có thể chỉ xuất hiện về sau khi dùng phần tử. |
| “Cứ dùng `@SuppressWarnings` là hết rủi ro.” | Annotation không thay đổi quy tắc type system hay hành vi runtime. |

## 10. Quy trình chẩn đoán khi gặp lỗi kiểu generic

1. **Viết rõ kiểu nguồn và kiểu đích** của biểu thức. Phân biệt `List<Integer>`, `List<Number>`, `List<?>` và raw `List`.
2. **Hỏi có subtype không** theo quan hệ kế thừa và wildcard containment; đừng tự suy ra từ subtype của type arguments.
3. **Nếu có `(TargetType) expr`**, xác định đây là cast tường minh, kiểm tra target có reifiable không và có cảnh báo unchecked không.
4. **Nếu không có cast mà vẫn xuất hiện `[unchecked]`**, tìm raw type trong phép gán, đối số phương thức hoặc thao tác tương tác thư viện cũ.
5. **Phân biệt thời điểm lỗi:** compile-time `incompatible types`; compile-time warning `unchecked`; runtime `ClassCastException` hoặc lỗi khác khi dùng giá trị.
6. **Chỉnh mô hình kiểu của API** (wildcard/generic type parameter, copy, validate) trước khi chọn cast/suppress warning.

### Tự kiểm tra

- `List<Integer>` có là subtype của `List<? extends Number>` không? **Có.**
- `List<Integer>` có là subtype của `List<Number>` không? **Không.**
- `Object obj; String s = (String) obj;` có phải unchecked cast không? **Không**, đây là cast có thể kiểm tra runtime.
- `List raw; List<String> strings = raw;` có cần toán tử cast mới phát cảnh báo không? **Không**, đây là unchecked conversion ngầm.
- `Object obj; List<String> xs = (List<String>) obj;` có bảo đảm các phần tử là `String` không? **Không**, vì cast không xác nhận type argument tại runtime.

## 11. Tài liệu chuẩn để tra cứu

- [JLS Java SE 17 §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): quan hệ subtype và các parameterized/wildcard types.
- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard, containment và upper/lower bounds.
- [JLS Java SE 17 §4.6–§4.8 — Type Erasure, Reifiable Types, Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): bối cảnh của giới hạn kiểm tra ở runtime.
- [JLS Java SE 17 §4.12.2 — Heap Pollution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2): biến parameterized tham chiếu dữ liệu không phù hợp.
- [JLS Java SE 17 §5.1.6 — Narrowing Reference Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.6): kiểm tra runtime, checked và unchecked narrowing.
- [JLS Java SE 17 §5.1.9 — Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.9): chuyển từ raw type sang parameterized type.
- [JLS Java SE 17 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): ngữ cảnh áp dụng cast.
