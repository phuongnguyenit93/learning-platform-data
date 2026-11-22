# Chỉ định đối số kiểu tường minh khi ngữ cảnh không đủ (`var` và generics trong Java)

## Mục tiêu

Java có thể tự suy luận kiểu của **đối số kiểu generic** trong nhiều lời gọi phương thức hoặc constructor. Tuy nhiên, khi khai báo biến cục bộ bằng `var`, biểu thức khởi tạo không có **kiểu đích từ phía khai báo** để hỗ trợ suy luận. Nếu lời gọi không có tham số hoặc các tham số chưa đủ thông tin, trình biên dịch có thể suy luận kiểu rộng như `Object`, hoặc không thể xác định kiểu cần thiết cho lambda.

Trong bài này, bạn sẽ biết:

- Vì sao `List<String> names = List.of();` và `var names = List.of();` có kết quả suy luận khác nhau.
- Cú pháp **type witness** như `List.<String>of()`, `Collections.<String>emptyList()` và `Map.<String, Integer>of()`.
- Cách dùng đối số kiểu tường minh để làm rõ generic method, lambda và các API trả về giá trị rỗng.
- Phân biệt type witness của **phương thức generic** với `<>\` (diamond) và đối số kiểu của **lớp generic**.
- Khi nào nên viết kiểu khai báo tường minh thay cho `var`.

Các ví dụ dành cho Java 17 trở lên và sử dụng những cơ chế vẫn được hỗ trợ trong Java hiện đại.

## 1. Hiểu ngữ cảnh suy luận kiểu

Xét phương thức generic của Java:

~~~java
public static <E> List<E> of()
~~~

Ký hiệu `<E>` là **tham số kiểu** do phương thức khai báo. Trình biên dịch cần xác định `E` là kiểu nào trong từng lời gọi. Với phương thức không nhận đối số như `List.of()`, thông tin suy luận chủ yếu đến từ **kiểu đích**, nếu có.

~~~java
import java.util.List;

// Ví dụ đặt bên trong một phương thức:
List<String> known = List.of();  // E được suy ra là String nhờ kiểu đích
var unknown = List.of();         // E được suy ra là Object
~~~

Tại khai báo `known`, trình biên dịch biết biểu thức phải phù hợp với `List<String>`. Trong khai báo `unknown`, từ khóa `var` báo rằng kiểu của biến sẽ được quyết định bởi **kiểu của biểu thức khởi tạo**, chứ không cung cấp `List<String>` làm đích. Không có phần tử nào truyền vào `of()` để xác định `E`, nên kiểu được suy luận là `Object`; biến `unknown` có kiểu tĩnh `List<Object>`.

Điều này được quy định trong JLS §14.4.1: biểu thức khởi tạo của `var` được xét như một biểu thức độc lập (*standalone expression*) ở vị trí khai báo, không được cấp ngữ cảnh gán từ kiểu của biến.

**Hệ quả:** Java generics là bất biến (*invariant*): `List<Object>` không thể dùng ở vị trí yêu cầu `List<String>`, dù danh sách đang rỗng.

~~~java
static void useStrings(List<String> values) {
    System.out.println(values.size());
}

// Đặt trong cùng lớp/phương thức thích hợp:
var unknown = List.of();      // List<Object>
// useStrings(unknown);       // Lỗi biên dịch: cần List<String>
useStrings(List.<String>of()); // Hợp lệ
~~~

Các đoạn tại mục này minh họa cú pháp và cần được đặt vào lớp/phương thức phù hợp; mục 4 chứa chương trình độc lập có thể chạy nguyên vẹn.

## 2. Type witness là gì, viết ở đâu?

**Type witness** là cách bạn viết trực tiếp các đối số kiểu ở **lời gọi phương thức generic** thay vì để trình biên dịch tự đoán:

~~~java
List.<String>of()
Collections.<String>emptyList()
Optional.<String>empty()
Map.<String, Integer>of()
~~~

Đối với phương thức `static`, vị trí thường gặp là:

~~~text
TenLop.<Kieu1, Kieu2>tenPhuongThuc(thamSo)
~~~

Cụ thể:

- `List.<String>of()`: chọn `E = String`, kết quả có kiểu `List<String>`.
- `Collections.<String>emptyList()`: chọn `T = String`, kết quả có kiểu `List<String>`.
- `Optional.<String>empty()`: chọn `T = String`, kết quả có kiểu `Optional<String>`.
- `Map.<String, Integer>of()`: chọn `K = String`, `V = Integer`, kết quả có kiểu `Map<String, Integer>`.

Ký hiệu `<String>` đặt **sau dấu chấm và trước tên phương thức**, không đặt sau tên phương thức. Ví dụ `List.of<String>()` **không phải cú pháp Java** để truyền đối số kiểu cho phương thức; cách đúng là `List.<String>of()`.

Đối số kiểu được chỉ định phải phù hợp với số lượng tham số kiểu và các ràng buộc của phương thức. Vì generics dùng kiểu tham chiếu, bạn dùng `<Integer>` thay cho `<int>`; viết `List.<String>of(123)` không hợp lệ vì giá trị `int`/ `Integer` không chuyển thành `String`.

Một số phương thức gọi trên đối tượng cũng có tham số kiểu riêng, với cú pháp `object.<Type>method(...)`. Hãy xem khai báo thực tế của phương thức để biết nó có generic type parameter hay không, thay vì thêm `<Type>` vào một lời gọi bất kỳ.

## 3. Khi nào cần viết đối số kiểu tường minh?

### 3.1. Phương thức không có đối số để suy luận

Các factory method tạo giá trị rỗng là tình huống thường gặp:

| Khai báo | Kiểu tĩnh của biến | Ý nghĩa |
| --- | --- | --- |
| `var values = List.of();` | `List<Object>` | Không có phần tử hay kiểu đích |
| `var values = List.<String>of();` | `List<String>` | Chỉ rõ kiểu phần tử |
| `var values = Collections.emptyList();` | `List<Object>` | Không có thông tin để chọn `T` |
| `var values = Collections.<String>emptyList();` | `List<String>` | Chọn `T = String` |
| `var value = Optional.empty();` | `Optional<Object>` | Không có đối số |
| `var value = Optional.<String>empty();` | `Optional<String>` | Chọn `T = String` |
| `var index = Map.of();` | `Map<Object, Object>` | Không có khóa/giá trị mẫu |
| `var index = Map.<String, Integer>of();` | `Map<String, Integer>` | Chọn kiểu khóa và giá trị |

Với các lời gọi không có tham số truyền vào, type witness giúp ràng buộc rõ kiểu trả về **ngay tại nguồn biểu thức**. Một phương án tương đương về hợp đồng kiểu là khai báo biến tường minh:

~~~java
List<String> names = List.of();
Optional<String> maybeName = Optional.empty();
Map<String, Integer> scores = Map.of();
~~~

Không cần dùng đồng thời type witness và kiểu biến tường minh nếu ngữ cảnh đã đủ rõ.

### 3.2. Lambda chưa có đủ thông tin về kiểu tham số

Có những generic method cần biết kiểu `T` để phân tích lambda. Ví dụ `Comparator.comparingInt` nhận hàm trích xuất một số nguyên từ đối tượng kiểu `T`:

~~~java
// Cố ý minh họa lỗi biên dịch:
// var invalid = Comparator.comparingInt(s -> s.length());
// Chưa có kiểu đích để suy luận s là String; length() không có trên Object.
~~~

Bạn có thể chỉ định `T` là `String` để lambda được kiểm tra theo kiểu phù hợp:

~~~java
var byLength = Comparator.<String>comparingInt(s -> s.length());
// Kiểu tĩnh: Comparator<String>
~~~

Hoặc khai báo kiểu đích thay vì dùng `var`:

~~~java
Comparator<String> byLength = Comparator.comparingInt(s -> s.length());
~~~

Cả hai cách đều giúp trình biên dịch biết `s` là `String` và gọi được `String.length()`. **Lưu ý:** lỗi trong ví dụ lambda phụ thuộc vào việc biểu thức bên trong chưa cung cấp đủ ràng buộc kiểu; không nên kết luận rằng mọi lời gọi `Comparator.comparingInt` đều bắt buộc type witness. Chẳng hạn method reference `String::length` có thể cung cấp thêm thông tin suy luận.

### 3.3. Lời gọi generic đã có thông tin từ đối số thì không cần ép thêm

~~~java
var names = List.of("An", "Binh");        // List<String>
var count = Optional.of(42);             // Optional<Integer>
var lengths = List.of(2, 4, 6);          // List<Integer>
~~~

Ở đây các đối số cụ thể đã đủ thông tin để suy luận. Viết `List.<String>of("An", "Binh")` vẫn hợp lệ nhưng thường không cần thiết.

Với `var`, *không có kiểu đích ở chính khai báo biến* không có nghĩa tất cả biểu thức con đều mất ngữ cảnh. Một biểu thức nằm trong đối số gọi phương thức hoặc constructor vẫn có thể nhận ngữ cảnh riêng từ chữ ký của lời gọi bao quanh.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau vào tệp **ExplicitTypeArgumentsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class ExplicitTypeArgumentsDemo {
    private static void acceptStrings(List<String> values) {
        System.out.println("List<String>: " + values);
    }

    public static void main(String[] args) {
        List<String> contextual = List.of();        // Được định hướng bởi kiểu đích
        var inferredEmpty = List.of();              // List<Object>
        var explicitEmpty = List.<String>of();      // List<String>
        var viaCollections = Collections.<String>emptyList();

        var created = new ArrayList<String>();     // ArrayList<String>
        var fromElements = new ArrayList<>(List.of("An", "Binh"));

        var scores = Map.<String, Integer>of();    // Map<String, Integer>
        var optional = Optional.<String>empty();   // Optional<String>
        var byLength = Comparator.<String>comparingInt(s -> s.length());

        acceptStrings(contextual);
        acceptStrings(explicitEmpty);
        acceptStrings(viaCollections);
        acceptStrings(created);
        acceptStrings(fromElements);

        // acceptStrings(inferredEmpty); // Lỗi biên dịch nếu bỏ comment

        System.out.println("inferredEmpty size: " + inferredEmpty.size());
        System.out.println("scores size: " + scores.size());
        System.out.println("optional fallback: " + optional.orElse("khong co"));
        System.out.println("length comparison: " + byLength.compare("An", "Binh"));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
~~~

Kết quả chính xác:

~~~text
List<String>: []
List<String>: []
List<String>: []
List<String>: []
List<String>: [An, Binh]
inferredEmpty size: 0
scores size: 0
optional fallback: khong co
length comparison: -1
~~~

Giải thích kết quả:

1. `contextual`, `explicitEmpty`, `viaCollections` và `created` đều tương thích với tham số `List<String>` của `acceptStrings`.
2. `inferredEmpty` vẫn là `List<Object>`. Danh sách rỗng có `size() == 0` nhưng **độ dài bằng nhau không chứng minh kiểu generic giống nhau**. Lời gọi `acceptStrings(inferredEmpty)` bị comment vì không biên dịch.
3. `fromElements` là `ArrayList<String>`: constructor nhận một `Collection<String>` từ `List.of("An", "Binh")`, nên ngữ cảnh từ đối số constructor đủ để suy luận `String`.
4. `scores` có kiểu `Map<String, Integer>` và trống nên kích thước 0.
5. `optional` là `Optional<String>`; vì rỗng, `orElse("khong co")` trả chuỗi dự phòng.
6. Bộ so sánh tính độ dài của hai chuỗi `"An"` và `"Binh"` lần lượt là 2 và 4; kết quả so sánh là `-1`.

Không dùng `getClass()` để chứng minh `List<String>` khác `List<Object>`: **type erasure** khiến thông tin đối số kiểu generic không được giữ nguyên để kiểm tra theo cách đó lúc chạy. Trong bài này, chữ ký phương thức `acceptStrings(List<String>)` cho thấy sự khác biệt **tại thời điểm biên dịch**.

## 5. Phân biệt type witness với `<>` (diamond) của constructor

Hai cú pháp cùng dùng dấu ngoặc nhọn góc `< >` nhưng tác dụng khác nhau.

**Type witness của phương thức generic:**

~~~java
var names = List.<String>of();    // Kiểu trả về phương thức: List<String>
~~~

**Đối số kiểu của lớp generic khi tạo đối tượng:**

~~~java
var names = new ArrayList<String>(); // Biến có kiểu ArrayList<String>
~~~

**Diamond cho phép suy luận đối số kiểu của lớp từ ngữ cảnh:**

~~~java
List<String> names = new ArrayList<>();  // Có kiểu đích List<String>
~~~

Với `var`, diamond không tự biết kiểu phần tử mong muốn khi constructor không nhận đối số:

~~~java
var unknown = new ArrayList<>();         // ArrayList<Object>
var known = new ArrayList<String>();    // ArrayList<String>
~~~

Nếu constructor nhận dữ liệu có generic rõ ràng, diamond có thể suy luận từ tham số:

~~~java
var names = new ArrayList<>(List.of("An", "Binh")); // ArrayList<String>
~~~

Đừng dùng **raw type** `new ArrayList()` để thay cho diamond hoặc tham số kiểu; raw type mất kiểm tra generic và có thể sinh cảnh báo *unchecked*. Khi cần một danh sách rỗng có thể thêm phần tử `String`, ví dụ `new ArrayList<String>()` phù hợp hơn `List.<String>of()`, vì các danh sách tạo bởi `List.of()` không cho phép sửa.

## 6. Khi chỉ định kiểu cụ thể mà vẫn không hợp lệ

Type witness giúp làm rõ kiểu mong muốn nhưng **không bỏ qua các ràng buộc của generic method**.

~~~java
// Những dòng sau được comment vì cố ý minh họa lỗi:
 
// var numbers = List.<int>of();          // int là kiểu nguyên thủy, không dùng làm type argument
// var strings = List.<String>of(123);    // Integer không tương thích với String
// var result = List.of<String>();       // Đặt type witness sai vị trí
// var flag = Boolean.<String>valueOf("true"); // valueOf không khai báo tham số kiểu T
~~~

Với API có giới hạn kiểu `<T extends Number>`, một type witness như `<String>` cũng sẽ bị từ chối vì `String` không thỏa ràng buộc. Hãy đọc chữ ký generic của phương thức trước khi chỉ định đối số kiểu.

Lưu ý một số nguyên nhân khác mà type witness không tự giải quyết được:

- **Dữ liệu đầu vào không phù hợp:** đối số và kiểu được chỉ định vẫn phải tương thích.
- **Kết quả suy luận không diễn đạt đúng mục đích API:** đôi khi khai báo interface rõ ràng (`List<String>`) sẽ dễ bảo trì hơn để `var` suy luận lớp cài đặt cụ thể.
- **Nhầm tên kiểu với khả năng thay đổi collection:** `List.<String>of()` trả về danh sách không thể sửa, dù có kiểu `List<String>`.
- **Ép kiểu không an toàn:** tránh cố chữa việc suy luận quá rộng bằng raw cast hoặc unchecked cast; chỉ định type argument hoặc khai báo kiểu đích ngay từ đầu thường an toàn hơn.

## 7. Quy trình chọn cách viết trong mã thực tế

Khi một khai báo `var` liên quan đến generic, hãy tự hỏi theo thứ tự:

1. **Biểu thức khởi tạo đã có thông tin kiểu từ đối số chưa?** `var names = List.of("An", "Binh");` đủ rõ, thường không cần type witness.
2. **Có kiểu đích mong muốn như `List<String>` hay `Optional<Long>` không?** Nếu kiểu đó là hợp đồng quan trọng cho người đọc, viết trực tiếp `List<String> names = List.of();`.
3. **Muốn giữ `var` với một generic method thiếu thông tin?** Chỉ định type witness: `var names = List.<String>of();`, `var maybe = Optional.<Long>empty();`.
4. **Đang gọi constructor của lớp generic?** Với constructor rỗng và `var`, viết rõ `new ArrayList<String>()`. Với constructor có dữ liệu `Collection<String>`, diamond có thể tự suy luận.
5. **Có lambda không xác định được kiểu tham số?** Xác định xem type witness trên generic method, kiểu biến tường minh hoặc kiểu tham số lambda tường minh có làm rõ được kiểu hay không.

Ví dụ so sánh nhanh:

~~~java
// Rõ loại đối tượng trả về qua kiểu đích:
List<String> emptyNames = List.of();

// Gọn, vẫn rõ loại phần tử nhờ type witness:
var emptyNames2 = List.<String>of();

// Danh sách mutable có generic rõ:
var writableNames = new ArrayList<String>();

// Đối số đủ để suy luận nên không cần witness:
var existingNames = List.of("An", "Binh");
~~~

## 8. Tự kiểm tra

Hãy dự đoán kiểu tĩnh của các biến bên dưới (mỗi dòng độc lập với nhau):

~~~java
var a = List.of();
var b = List.<String>of();
var c = Optional.empty();
var d = Optional.<Integer>empty();
var e = new ArrayList<>();
var f = new ArrayList<String>();
var g = new ArrayList<>(List.of("Java"));
List<String> h = List.of();
var i = Comparator.<String>comparingInt(s -> s.length());
~~~

**Đáp án:**

| Biến | Kiểu tĩnh |
| --- | --- |
| `a` | `List<Object>` |
| `b` | `List<String>` |
| `c` | `Optional<Object>` |
| `d` | `Optional<Integer>` |
| `e` | `ArrayList<Object>` |
| `f` | `ArrayList<String>` |
| `g` | `ArrayList<String>` |
| `h` | `List<String>` |
| `i` | `Comparator<String>` |

Hãy giải thích thêm: tại sao không gọi `acceptStrings(a)` nếu `acceptStrings` nhận `List<String>`? Vì `a` có kiểu `List<Object>`, và generic không cho phép chuyển trực tiếp kiểu này thành `List<String>`. Có thể sửa bằng cách thay khai báo thành `var a = List.<String>of();` hoặc `List<String> a = List.of();`.

## 9. Tài liệu chuẩn và ghi nhớ

- [Java Language Specification §14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4.1): biểu thức khởi tạo `var` được xét không có ngữ cảnh gán ở khai báo.
- [Java Language Specification §15.12.2 — Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2): kiểm tra lời gọi phương thức, lựa chọn overload và đối số kiểu generic.
- [Dev.java — Type Inference](https://dev.java/learn/generics/type-inference/): vai trò của ngữ cảnh kiểu đích và type witness.
- [Java Tutorials — Type Inference](https://docs.oracle.com/javase/tutorial/java/generics/genTypeInference.html): phân biệt type witness của generic method với diamond của generic class.

**Ghi nhớ:** `var` suy luận **kiểu của biểu thức khởi tạo**, không cung cấp một kiểu đích để generic method đoán theo mong muốn của bạn. Khi thiếu dữ liệu đầu vào, hãy dùng **kiểu khai báo tường minh** hoặc **type witness** như `List.<String>of()`. Với constructor generic, dùng đối số kiểu của lớp hoặc diamond khi có đủ ngữ cảnh. Những lựa chọn này vẫn bảo đảm cơ chế kiểm tra kiểu tĩnh của Java.
