# Predicate.not() và Predicate.isEqual() trong Java

Trong Java, **Predicate<T>** đại diện cho một điều kiện nhận dữ liệu kiểu T và trả về boolean. Ngoài việc tự viết lambda, gói **java.util.function** cung cấp hai phương thức static rất hữu ích khi **kết hợp các điều kiện**:

- **Predicate.not(predicate):** tạo predicate có kết quả **phủ định** của predicate được cung cấp. Phương thức có từ **Java 11**.
- **Predicate.isEqual(targetRef):** tạo predicate kiểm tra một đối tượng có **bằng** đối tượng đích theo hợp đồng equals hay không; hỗ trợ cả trường hợp targetRef là null. Phương thức có từ **Java 8**.

Hai công cụ này giúp viết pipeline có ý nghĩa rõ ràng, chẳng hạn “loại chuỗi trắng”, “chọn phần tử có giá trị mong muốn”, “loại giá trị không bằng X” mà không nhất thiết tạo lambda đảo điều kiện bằng tay. Bài học trình bày cú pháp, cách suy luận generic, quan hệ với negate/and/or, ví dụ Java 17 chạy được và những lỗi dễ mắc.

## 1. Nền tảng: Predicate<T> là gì?

Predicate<T> là functional interface tiêu chuẩn có phương thức trừu tượng duy nhất:

~~~java
boolean test(T value);
~~~

Ví dụ:

~~~java
java.util.function.Predicate<String> longName =
    name -> name.length() >= 4;

System.out.println(longName.test("Java")); // true
System.out.println(longName.test("Go"));   // false
~~~

Predicate có các default method kết hợp như **and**, **or**, **negate** và các static method **not**, **isEqual**. Khác với Function<T,R>, Predicate<T> không biến một T thành giá trị dữ liệu R tùy ý; kết quả chuẩn của test luôn là boolean.

Cần phân biệt:

| Thành phần | Nhận gì? | Tạo ra gì? |
| --- | --- | --- |
| Predicate<T>.test(value) | Một T | boolean |
| predicate.negate() | Không nhận tham số phương thức | Predicate<T> có kết quả đảo |
| Predicate.not(predicate) | Một Predicate phù hợp | Predicate<T> có kết quả đảo |
| Predicate.isEqual(targetRef) | Một đối tượng làm giá trị so sánh | Predicate<T> kiểm tra bằng targetRef |
| predicate.and(other) | Predicate khác | Predicate<T> kết hợp AND |
| predicate.or(other) | Predicate khác | Predicate<T> kết hợp OR |

**Lưu ý:** Predicate.not và Predicate.isEqual là **static factory methods**: chúng trả về đối tượng predicate để dùng sau. Gọi phương thức tạo predicate **không đồng nghĩa** đã kiểm tra dữ liệu; việc đánh giá điều kiện diễn ra khi gọi test hoặc khi API như Stream.filter thực thi.

## 2. Predicate.not(): phủ định một predicate

Chữ ký API (dùng cách viết tương đương để đọc dễ hơn):

~~~java
static <T> Predicate<T> not(Predicate<? super T> target);
~~~

Phương thức trả predicate mới có kết quả tương đương với **!target.test(value)** cho cùng value. Ví dụ:

~~~java
import java.util.function.Predicate;

Predicate<String> blank = String::isBlank;
Predicate<String> notBlank = Predicate.not(blank);

System.out.println(blank.test("   "));    // true
System.out.println(notBlank.test("   ")); // false
System.out.println(notBlank.test("Java")); // true
~~~

Đây là các câu lệnh minh họa nằm trong phương thức; nếu đặt trong lớp độc lập phải bổ sung khai báo class/main. **Predicate.not(blank) không làm thay đổi blank**; cả hai predicate có thể sử dụng độc lập.

### 2.1. Vì sao static not có ích với method reference?

Khi lọc chuỗi không trắng, một cách viết quen thuộc là:

~~~java
List<String> kept = values.stream()
    .filter(value -> !value.isBlank())
    .toList();
~~~

Kể từ Java 11, có thể dùng:

~~~java
List<String> kept = values.stream()
    .filter(Predicate.not(String::isBlank))
    .toList();
~~~

Ý định “lọc các chuỗi không blank” được biểu diễn như phép phủ định của một method reference. Trong đoạn này, **String::isBlank** là phương thức instance của đối tượng mà predicate nhận vào. Method reference có target type phù hợp nhờ tham số của Predicate.not và Stream.filter.

Có thể dùng static import để giảm độ dài:

~~~java
import static java.util.function.Predicate.not;
~~~

Sau đó:

~~~java
List<String> kept = values.stream()
    .filter(not(String::isBlank))
    .toList();
~~~

Trong các đoạn minh họa, List<String> và values phải được khai báo trong chương trình thực tế. Chọn static import nếu tên not đủ rõ trong nhóm mã đang viết; nếu có nhiều phương thức trùng tên, viết Predicate.not(...) giúp tránh nhầm.

### 2.2. So sánh not và negate

Hai cách thường tương đương về kết quả logic:

~~~java
Predicate<Integer> positive = number -> number > 0;
Predicate<Integer> notPositive1 = positive.negate();
Predicate<Integer> notPositive2 = Predicate.not(positive);
~~~

Đều cho false với 3 và true với 0, -2.

**Khác nhau về cách biểu đạt:**

- **positive.negate()** thuận tiện khi đã có biến predicate hoặc một biểu thức trả predicate rõ ràng.
- **Predicate.not(String::isBlank)** thuận tiện để phủ định trực tiếp **method reference**; không cần tạo một biến trung gian.
- **Predicate.not(...)** là static method nên đọc tốt trong các tổ hợp điều kiện và có thể static import.

Tránh hiểu sai rằng not “phủ định object” tại thời điểm gọi; nó **trả predicate** để phủ định kết quả của các lời gọi test sau này. Cả hai không tự bảo đảm callback thuần, thread-safe hay không ném ngoại lệ.

### 2.3. Giá trị null của predicate đầu vào

~~~java
// Sẽ ném NullPointerException:
Predicate<String> invalid = Predicate.not(null);
~~~

Bản thân target predicate phải **không null**. Điều này khác với khả năng predicate có thể **kiểm tra một giá trị null** tại thời điểm test: khả năng đó phụ thuộc vào predicate gốc.

Chẳng hạn String::isBlank không chấp nhận receiver null. Predicate.not(String::isBlank) không tự biến phép gọi isBlank(null) thành false; nó vẫn có thể ném NullPointerException khi test(null).

Nếu collection có thể chứa null, hãy xử lý null tường minh hoặc sử dụng điều kiện có hỗ trợ null, thay vì tin rằng chữ not sẽ tự mang lại null-safety.

## 3. Predicate.isEqual(): tạo điều kiện so sánh bằng

Chữ ký khái niệm của API:

~~~java
static <T> Predicate<T> isEqual(Object targetRef);
~~~

targetRef là **giá trị mốc** cần so sánh. Mỗi lần gọi test(candidate), predicate trả true khi hai giá trị được xem là bằng nhau theo logic tương ứng với **Objects.equals(targetRef, candidate)**.

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");

System.out.println(isJava.test("Java")); // true
System.out.println(isJava.test("Go"));   // false
System.out.println(isJava.test(null));   // false
~~~

Điều quan trọng là so sánh **equality**, không phải đồng nhất địa chỉ đối tượng. Với String, equals thường so sánh nội dung chuỗi, trong khi toán tử == so sánh hai tham chiếu (trừ các trường hợp boxing/primitive khác không liên quan ở đây).

### 3.1. So với Objects.equals()

Một lambda thông thường:

~~~java
Predicate<String> isJava =
    candidate -> java.util.Objects.equals("Java", candidate);
~~~

Có thể biểu diễn bằng:

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");
~~~

Khi đánh giá, cả hai trả boolean dựa trên phép so sánh equality. Trong code nhiều điều kiện hoặc pipeline, Predicate.isEqual giúp nhấn mạnh “mục tiêu là bằng giá trị mốc”.

**Phân biệt hướng so sánh:** Java gọi equals trên đối tượng không null ở vị trí thích hợp; với các lớp tự định nghĩa equals sai, không đối xứng hoặc có tác dụng phụ, hướng so sánh có thể đáng quan tâm. Vì vậy hãy tuân thủ hợp đồng equals (đặc biệt đối xứng, bắc cầu, nhất quán) và không dùng isEqual như một cơ chế sửa lỗi equality của kiểu dữ liệu.

### 3.2. Giá trị null được hỗ trợ

Một trong những ích lợi của isEqual là **xử lý mốc null**:

~~~java
Predicate<Object> isNull = Predicate.isEqual(null);

System.out.println(isNull.test(null));   // true
System.out.println(isNull.test("abc"));  // false
~~~

Với targetRef = null, isEqual tạo predicate kiểm tra candidate có phải null hay không. Vì thế:

~~~java
Predicate<Object> nonNull =
    Predicate.not(Predicate.isEqual(null));
~~~

cho true đối với đối tượng không null và false với null.

Tuy nhiên, khi mục đích chỉ là kiểm tra null, cách viết bằng method reference có thể rõ hơn:

~~~java
Predicate<Object> isNull = java.util.Objects::isNull;
Predicate<Object> nonNull = java.util.Objects::nonNull;
~~~

Hoặc trong pipeline:

~~~java
values.stream()
    .filter(java.util.Objects::nonNull)
    .toList();
~~~

Đừng nhầm rằng Stream.of hoặc List.of cho phép null: **List.of không chấp nhận phần tử null**, và Stream.of có thể tạo stream chứa null khi phần tử null được cung cấp theo ngữ cảnh phù hợp. Khi cần minh họa một danh sách có null, có thể dùng ArrayList và add(null).

### 3.3. Equality dựa trên equals, không phải so sánh cấu trúc tùy ý

Ví dụ:

~~~java
record Point(int x, int y) {}

Predicate<Point> origin = Predicate.isEqual(new Point(0, 0));
System.out.println(origin.test(new Point(0, 0))); // true
~~~

Record Java cung cấp equals/hashCode theo các component, nên hai Point trong ví dụ bằng nhau. Nhưng nếu đối tượng là lớp thông thường không override equals, equals kế thừa từ Object thường dựa trên đồng nhất tham chiếu. isEqual **không** tự suy luận “hai đối tượng có cùng tất cả field thì bằng nhau”.

Muốn so sánh theo một thuộc tính, hãy dùng predicate mô tả thuộc tính:

~~~java
Predicate<Point> xIsZero = point -> point.x() == 0;
~~~

Đây là điều kiện khác với việc bằng hẳn Point(0,0).

### 3.4. So sánh chuỗi phân biệt chữ hoa/chữ thường

~~~java
Predicate<String> exact = Predicate.isEqual("admin");

System.out.println(exact.test("admin")); // true
System.out.println(exact.test("ADMIN")); // false
~~~

String.equals phân biệt chữ hoa/thường. Nếu cần so sánh không phân biệt chữ hoa/thường, chọn logic phù hợp:

~~~java
Predicate<String> adminIgnoreCase =
    text -> "admin".equalsIgnoreCase(text);
~~~

Lambda này có khả năng trả false khi text null, vì receiver là hằng chuỗi "admin". Tránh viết text.equalsIgnoreCase("admin") khi text có thể null. Đối với các quy tắc chuẩn hóa phức tạp, cần xác định quy tắc locale và Unicode rõ ràng; isEqual không tự chuẩn hóa chuỗi.

## 4. Kết hợp not, isEqual, and và or

**Predicate.and**, **Predicate.or** và **Predicate.negate** là default methods, còn **Predicate.not** và **Predicate.isEqual** là static methods. Chúng giúp diễn đạt logic thành các thành phần dễ kiểm thử.

Ví dụ chọn trạng thái đơn hàng:

~~~java
record Order(String status, boolean paid) {}

Predicate<Order> paid = Order::paid;
Predicate<Order> notCancelled =
    Predicate.not(order -> "CANCELLED".equals(order.status()));

Predicate<Order> accepted = paid.and(notCancelled);
~~~

Đây là mã minh họa cần đặt trong ngữ cảnh có khai báo Order/Predicate phù hợp. accepted.test(order) chỉ true nếu order đã thanh toán **và** status khác CANCELLED.

Có thể dùng isEqual cho một thuộc tính:

~~~java
Predicate<String> isCancelled =
    Predicate.isEqual("CANCELLED");

Predicate<Order> active =
    order -> !isCancelled.test(order.status());
~~~

Nhưng nếu chỉ để kiểm tra một field một lần, việc thêm nhiều tầng predicate có thể dài dòng. Không ép dùng isEqual ở mọi nơi; "CANCELLED".equals(order.status()) thường đã rất rõ.

### 4.1. Kết hợp điều kiện với short-circuit

~~~java
Predicate<String> nonNull = java.util.Objects::nonNull;
Predicate<String> nonBlank = Predicate.not(String::isBlank);

Predicate<String> valid = nonNull.and(nonBlank);
~~~

Ở đây valid.test(null) là false **mà không gọi nonBlank** nhờ quy tắc short-circuit của and: nếu điều kiện trái false, điều kiện phải không được gọi. Đây là cách kết hợp điều kiện có thể xử lý null an toàn.

Tương tự:

~~~java
Predicate<String> isSpecial = Predicate.isEqual("SPECIAL");
Predicate<String> longValue = text -> text.length() >= 8;

Predicate<String> allowed = isSpecial.or(longValue);
~~~

Với test("SPECIAL"), nhánh đầu true, nhánh sau không chạy. Với test(null), isSpecial trả false rồi longValue có thể ném NullPointerException: **or không làm predicate phía sau tự hỗ trợ null**.

Nếu cần xử lý null trong mọi trường hợp, kết hợp điều kiện đầu tiên có bảo vệ:

~~~java
Predicate<String> allowedSafely =
    java.util.Objects::<String>nonNull;
~~~

Dòng này chỉ tạo predicate kiểm tra non-null; trong ứng dụng có thể ghép thêm các predicate thích hợp. Ví dụ tự giải thích hơn là:

~~~java
Predicate<String> nonNullAndAllowed =
    ((Predicate<String>) java.util.Objects::nonNull)
        .and(isSpecial.or(longValue));
~~~

Với đầu vào null, kiểm tra nonNull false nên nhánh sau không chạy. Cách rõ nhất đôi khi là tách một biến Predicate<String> nonNull trước khi kết hợp để tránh cast rối.

### 4.2. Các quy tắc De Morgan

Với A, B là các predicate thuần và tổng quát (không ném lỗi), về kết quả logic:

- not(A.and(B)) tương đương not(A).or(not(B)).
- not(A.or(B)) tương đương not(A).and(not(B)).

Trong Java:

~~~java
Predicate<String> a = text -> text.startsWith("J");
Predicate<String> b = text -> text.length() > 3;

Predicate<String> neither =
    Predicate.not(a.or(b));

Predicate<String> equivalent =
    Predicate.not(a).and(Predicate.not(b));
~~~

Hai predicate cùng có kết quả boolean với một String không null; nhưng **nếu callback có tác dụng phụ hoặc ngoại lệ**, khác biệt thứ tự/đường thực thi có thể quan sát được tùy cách biến đổi và cấu trúc điều kiện. Vì vậy, tốt nhất viết predicate **không gây tác dụng phụ** và không phụ thuộc trạng thái mutable ngoài.

### 4.3. Phủ định đúng phạm vi

Một lỗi phổ biến là nhầm giữa:

~~~java
Predicate<String> isEmpty = String::isEmpty;
Predicate<String> isNotEmpty = Predicate.not(isEmpty);
~~~

với:

~~~java
Predicate<String> isBlank = String::isBlank;
Predicate<String> isNotBlank = Predicate.not(isBlank);
~~~

**String.isEmpty()** chỉ true khi độ dài bằng 0, còn **String.isBlank()** true khi chuỗi rỗng hoặc chỉ gồm các ký tự trắng theo định nghĩa của Character.isWhitespace. Chuỗi "   " không empty nhưng blank. Chọn predicate gốc đúng nghiệp vụ **trước khi** phủ định.

## 5. Trong Stream API: biểu đạt ý định rõ ràng

### 5.1. Lọc giá trị không blank

~~~java
List<String> result = List.of("Java", " ", "Stream", "")
    .stream()
    .filter(Predicate.not(String::isBlank))
    .toList();
~~~

Kết quả là ["Java", "Stream"]. Đây là trường hợp Predicate.not tạo ra biểu thức dễ đọc khi method reference gốc đã diễn đạt thuộc tính tốt.

Nếu nguồn có thể chứa null, cần lọc null trước:

~~~java
List<String> result = input.stream()
    .filter(java.util.Objects::nonNull)
    .filter(Predicate.not(String::isBlank))
    .toList();
~~~

Ngược lại, .filter(Predicate.not(String::isBlank)) tự nó **không** kiểm tra null và có thể ném NullPointerException khi phần tử là null.

### 5.2. Lọc đúng giá trị đích

~~~java
List<String> result = List.of("NEW", "PAID", "NEW")
    .stream()
    .filter(Predicate.isEqual("NEW"))
    .toList();
~~~

Kết quả ["NEW", "NEW"], giữ thứ tự encounter order của stream nguồn tuần tự.

Ngược lại, muốn loại tất cả "NEW":

~~~java
List<String> result = List.of("NEW", "PAID", "NEW")
    .stream()
    .filter(Predicate.not(Predicate.isEqual("NEW")))
    .toList();
~~~

Kết quả ["PAID"]. Có thể dùng .filter(status -> !"NEW".equals(status)) nếu đó là cách ngắn và dễ hiểu hơn trong ngữ cảnh; không buộc mọi biểu thức phải dùng factory method.

### 5.3. Tìm phần tử đầu tiên không bằng X

~~~java
String firstOther = List.of("A", "B", "A").stream()
    .filter(Predicate.not(Predicate.isEqual("A")))
    .findFirst()
    .orElse("none");
~~~

firstOther bằng "B". findFirst và orElse làm rõ trường hợp không tìm được. Với nguồn song song, findFirst vẫn có hợp đồng encounter order khi nguồn có thứ tự, nhưng chi phí và cách thực thi có thể khác stream tuần tự.

### 5.4. Lưu ý về lazy evaluation

filter là phép toán trung gian, có thể **chưa gọi predicate** cho đến khi có terminal operation như toList, count hoặc findFirst. Stream có thể short-circuit hoặc tối ưu một số thao tác. Do đó không sử dụng Predicate.not hay Predicate.isEqual như một điểm chắc chắn để đếm số lần đánh giá hay ghi log quan trọng.

Predicate là mô tả điều kiện; **việc áp dụng** điều kiện được API gọi callback quyết định.

## 6. Suy luận kiểu generic và method reference

### 6.1. Predicate.not giữ kiểu mong muốn

Predicate.not dùng type parameter T và tham số Predicate<? super T> để chấp nhận predicate trên T hoặc kiểu cha của T. Điều này hữu ích khi kết hợp các đối tượng có phân cấp kiểu:

~~~java
Predicate<CharSequence> emptyText =
    text -> text.length() == 0;

Predicate<String> notEmptyString = Predicate.not(emptyText);
~~~

Với đầu vào String, Predicate<CharSequence> vẫn kiểm tra được vì String implements CharSequence. Ở đây có target type rõ ràng ở vế trái để suy luận T = String.

Không nên dùng raw Predicate vì mất kiểm tra kiểu và làm tăng khả năng ClassCastException khi predicate được dùng sai kiểu.

### 6.2. Predicate.isEqual có đầu vào Object, nhưng kết quả là Predicate<T>

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");
Predicate<Object> isNull = Predicate.isEqual(null);
~~~

Generic type của predicate kết quả thường được suy ra từ kiểu đích hoặc ngữ cảnh phương thức. targetRef có kiểu khai báo Object để có thể chấp nhận nhiều loại giá trị mốc, **không có nghĩa mọi lần test đều bỏ qua việc type-check**: nếu biến được khai báo Predicate<String>, test(123) không hợp lệ tại compile time.

Khi dùng method reference hoặc lambda nằm sâu trong lời gọi generic, đôi khi compiler cần thêm gợi ý kiểu. Ưu tiên biến predicate khai báo đầy đủ kiểu hoặc type witness hợp lệ, thay vì lạm dụng cast Object.

### 6.3. Kiểu đích của method reference trong not

~~~java
Predicate<String> notEmpty =
    Predicate.not(String::isEmpty);
~~~

String::isEmpty là method reference đến phương thức instance không có tham số tường minh, với receiver được cung cấp từ đối số test(String). Compiler kiểm tra tính tương thích theo function descriptor của Predicate<String>.

**Không phải mọi method reference đều hợp lệ**: nếu phương thức nhận/đưa ra kiểu không khớp SAM test(T) → boolean, compiler sẽ từ chối. Predicate.not không tự chuyển Function<T,R> hay Consumer<T> thành Predicate<T>.

## 7. Predicate.isEqual và hợp đồng equals/hashCode

Khi so sánh đối tượng, isEqual dựa trên **equality**, nên thiết kế equals của kiểu dữ liệu quyết định kết quả:

1. **Reflexive:** một đối tượng x bằng chính nó (x.equals(x) là true với x không null).
2. **Symmetric:** x.equals(y) và y.equals(x) phải có kết quả nhất quán.
3. **Transitive:** nếu x bằng y và y bằng z thì x bằng z.
4. **Consistent:** không đổi khi thông tin tham gia equals không đổi.
5. **Non-null:** x.equals(null) phải false với x không null.

Với record có các component phù hợp, Java tạo equals dựa trên các component; với lớp bình thường, cần override equals/hashCode cẩn thận nếu equality theo dữ liệu là yêu cầu.

Ví dụ:

~~~java
record Code(String value) {}

Predicate<Code> match = Predicate.isEqual(new Code("X"));
System.out.println(match.test(new Code("X"))); // true
~~~

Nếu một lớp không override equals từ Object, hai instance có trường dữ liệu giống nhau thường vẫn không bằng nhau. Predicate.isEqual **không** thay thế việc định nghĩa hợp đồng equality ở loại đối tượng.

**Về tham chiếu mutable:** targetRef được cung cấp khi tạo predicate; nếu đối tượng mốc là mutable và các field tham gia equals thay đổi sau đó, kết quả so sánh cũng có thể thay đổi. Khi cần so sánh ổn định, dùng dữ liệu bất biến hoặc tạo bản chụp phù hợp. Đừng nhầm predicate được tạo một lần với việc trạng thái của mọi đối tượng liên quan được đóng băng.

**Về hashCode:** Predicate.isEqual tự nó không tạo tập hợp băm và không gọi hashCode để so sánh, nhưng nếu đối tượng đó cũng được dùng trong HashMap/HashSet thì phải duy trì hợp đồng equals/hashCode nhất quán.

## 8. Tác dụng phụ và thứ tự đánh giá

Một predicate có thể thực hiện side effect:

~~~java
java.util.concurrent.atomic.AtomicInteger calls =
    new java.util.concurrent.atomic.AtomicInteger();

Predicate<String> checked = text -> {
    calls.incrementAndGet();
    return text.isBlank();
};

Predicate<String> notBlank = Predicate.not(checked);
~~~

Gọi notBlank.test("Java") vẫn gọi checked.test("Java") và tăng calls một lần. **Predicate.not không hủy hay hoàn tác tác dụng phụ** của predicate gốc; nó chỉ phủ định boolean trả về. Việc dùng AtomicInteger có thể làm thao tác tăng nguyên tử nhưng không làm callback thuần.

Tương tự, with Predicate.isEqual(mutableTarget), nếu equals tùy chỉnh có tác dụng phụ, gọi test vẫn có thể gây tác dụng phụ. Không nên đặt nghiệp vụ phụ thuộc số lần gọi hoặc thứ tự gọi vào filter, đặc biệt với parallel stream.

Khi kết hợp and/or, có short-circuit; khi gọi negate/not, kết quả phủ định chỉ có nghĩa khi predicate bên trong hoàn tất bình thường. Nếu predicate gốc ném exception, ngoại lệ vẫn lan ra, không bị “đảo” thành false hoặc true.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình minh họa **Predicate.not**, **Predicate.isEqual**, **negate**, **and**, method reference và kiểm tra null. Ngoài ra có một quy tắc đối với record User và một ví dụ không phân biệt chữ hoa/thường dùng equals với logic riêng.

Tạo tệp **PredicateCompositionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Predicate;

public class PredicateCompositionDemo {
    record User(String username, boolean active) {}

    static List<String> nonBlankValues(List<String> values) {
        return values.stream()
            .filter(Predicate.not(String::isBlank))
            .toList();
    }

    static List<User> activeNonGuestUsers(List<User> users) {
        Predicate<User> active = User::active;
        Predicate<User> notGuest =
            Predicate.not(user -> user.username().equalsIgnoreCase("guest"));
        return users.stream().filter(active.and(notGuest)).toList();
    }

    public static void main(String[] args) {
        List<String> values = List.of("Java", "  ", "Stream", "");
        System.out.println("nonBlank=" + nonBlankValues(values));

        Predicate<String> isAdmin = Predicate.isEqual("admin");
        System.out.println("admin=" + isAdmin.test("admin"));
        System.out.println("other=" + isAdmin.test("guest"));
        System.out.println("notAdmin=" + isAdmin.negate().test("guest"));

        Predicate<Object> isNull = Predicate.isEqual(null);
        System.out.println("isNull=" + isNull.test(null));
        System.out.println("isNullText=" + isNull.test(""));

        List<User> users = List.of(
            new User("alice", true),
            new User("guest", true),
            new User("bob", false),
            new User("carol", true)
        );
        System.out.println("eligible=" + activeNonGuestUsers(users));

        List<String> possiblyNull = new ArrayList<>();
        possiblyNull.add(null);
        possiblyNull.add("Java");
        System.out.println("nullCount=" +
            possiblyNull.stream().filter(Predicate.isEqual(null)).count());

        Predicate<String> lowercaseAdmin =
            text -> "admin".equals(text.toLowerCase(Locale.ROOT));
        System.out.println("caseFold=" + lowercaseAdmin.test("ADMIN"));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 hoặc mới hơn:

~~~bash
javac PredicateCompositionDemo.java
java PredicateCompositionDemo
~~~

**Stdout chính xác:**

~~~text
nonBlank=[Java, Stream]
admin=true
other=false
notAdmin=true
isNull=true
isNullText=false
eligible=[User[username=alice, active=true], User[username=carol, active=true]]
nullCount=1
caseFold=true
~~~

Phân tích:

1. nonBlankValues loại "  " và "" nhờ Predicate.not(String::isBlank), giữ Java và Stream theo thứ tự nguồn.
2. isAdmin dùng Predicate.isEqual("admin"), kiểm tra chính xác case-sensitive; guest không bằng admin.
3. isAdmin.negate() trả true cho guest vì điều kiện gốc là false.
4. Predicate.isEqual(null) trả true khi test(null), false khi test(""); hai kết quả này hoàn toàn khác nhau.
5. activeNonGuestUsers kết hợp hai điều kiện: user.active() và username không bằng "guest" theo equalsIgnoreCase. Chỉ alice và carol được giữ lại.
6. possiblyNull là ArrayList nên có thể chứa null, khác với List.of. Lọc bằng isEqual(null) đếm đúng một phần tử null.
7. lowercaseAdmin dùng quy tắc chuyển chữ thường theo Locale.ROOT rồi so với "admin", do đó "ADMIN" được chấp nhận. Đây là quy tắc tùy biến, **không phải hành vi của Predicate.isEqual**.

Chương trình dùng danh sách bất biến cho dữ liệu bình thường và chỉ dùng ArrayList để minh họa null. Trong ứng dụng thật, nếu User.username() có thể null, lambda notGuest hiện tại có thể ném NullPointerException; cần bổ sung hợp đồng validation hoặc so sánh null-safe tùy nghiệp vụ.

## 10. Các lỗi thường gặp và cách sửa

**Lỗi 1 — nhầm Predicate.not với phép gọi test ngay lập tức.** Predicate.not tạo ra Predicate mới; cần gọi test hoặc truyền vào API callback để áp dụng. Không có chuyện not(...) tự chạy hết stream.

**Lỗi 2 — cho rằng not làm callback an toàn với null.** Predicate.not(String::isBlank) vẫn có thể ném NullPointerException nếu test(null). Lọc null trước hoặc sử dụng predicate có khả năng xử lý null.

**Lỗi 3 — nhầm not với negate.** Cả hai phủ định logic nhưng not là static method nhận predicate, còn negate là instance method trên predicate. Dùng cách diễn đạt nào giúp code sáng rõ nhất.

**Lỗi 4 — nhầm isEqual với ==.** Predicate.isEqual sử dụng equality theo equals/Objects.equals. Nó không kiểm tra đơn thuần việc hai biến trỏ cùng một object, trừ khi equals của kiểu dữ liệu có nghĩa đó.

**Lỗi 5 — nghĩ isEqual tự bỏ qua phân biệt chữ hoa.** Với String, "admin" không bằng "ADMIN". Muốn ignore case phải dùng quy tắc rõ ràng, hoặc normalize dữ liệu trước.

**Lỗi 6 — dùng List.of(null) khi minh họa so sánh null.** List.of không chấp nhận null và có thể ném NullPointerException khi tạo danh sách. Dùng ArrayList hoặc nguồn dữ liệu có thể chứa null để thử Predicate.isEqual(null).

**Lỗi 7 — thay isEqual bằng phép so sánh field sai hợp đồng.** Với record thì equality thường theo component; với class mutable không override equals, kết quả có thể khác mong đợi. Kiểm tra định nghĩa equals trước khi dùng isEqual.

**Lỗi 8 — làm predicate có tác dụng phụ và mong chạy chính xác một lần.** Stream có lazy evaluation, short-circuit và tối ưu. Khi dùng and/or, điều kiện phía sau có thể không gọi. Không phụ thuộc vào số lần gọi callback để ghi audit quan trọng.

**Lỗi 9 — quên Java version.** Predicate.isEqual dùng từ Java 8; **Predicate.not được thêm từ Java 11**. Code dùng Predicate.not không biên dịch khi target JDK 8, dù các method như negate/and/or đã tồn tại.

**Lỗi 10 — lạm dụng generic cast.** Khi compiler báo lỗi suy luận kiểu, ưu tiên kiểm tra kiểu của stream và functional interface, đặt tên biến Predicate<T> rõ ràng, thay vì ép thô sang Predicate hoặc Object rồi mất type safety.

**Lỗi 11 — sai thứ tự điều kiện null-safe.** nonNull.and(notBlank) có thể bảo vệ nhánh sau khỏi null; đổi thành notBlank.and(nonNull) sẽ khiến notBlank gặp null trước. Vì and short-circuit theo thứ tự, thứ tự điều kiện có ý nghĩa.

**Lỗi 12 — nhầm isEmpty với isBlank.** Một chuỗi chỉ có dấu cách không empty nhưng blank. Hãy kiểm tra định nghĩa nghiệp vụ trước khi phủ định điều kiện.

## 11. Chọn cách viết nào?

| Mục đích | Cách biểu đạt rõ ràng |
| --- | --- |
| Phủ định một predicate đã có tên | predicate.negate() |
| Phủ định method reference ngay tại điểm dùng | Predicate.not(String::isBlank) |
| Lọc các phần tử bằng một hằng | Predicate.isEqual("ACTIVE") |
| Lọc các phần tử khác hằng | Predicate.not(Predicate.isEqual("ACTIVE")) |
| Kiểm tra null | Objects::isNull hoặc Predicate.isEqual(null) |
| Loại null | Objects::nonNull hoặc Predicate.not(Predicate.isEqual(null)) |
| Kết hợp điều kiện | predicateA.and(predicateB), predicateA.or(predicateB) |
| So sánh theo thuộc tính | value -> value.property().equals(target) với xử lý null thích hợp |
| So sánh không phân biệt chữ hoa | value -> "target".equalsIgnoreCase(value) |

Không có quy tắc bắt buộc phải viết mọi biểu thức qua Predicate.not hoặc isEqual. Ví dụ .filter(value -> !"ACTIVE".equals(value)) đôi khi rõ hơn .filter(Predicate.not(Predicate.isEqual("ACTIVE"))). Chọn phong cách nhất quán với nhóm và ưu tiên **ý nghĩa dễ thấy, khả năng kiểm thử và tính an toàn của dữ liệu**.

## 12. Câu hỏi tự kiểm tra

1. Predicate.not(String::isBlank) và predicate.negate() giống và khác nhau thế nào về cách tạo predicate?
2. Vì sao Predicate.not(String::isBlank).test(null) không trở thành kết quả true một cách an toàn?
3. Predicate.isEqual("Java").test(new String("Java")) trả true hay false? Vì sao?
4. Predicate.isEqual(null).test(null) và Predicate.isEqual(null).test("") khác nhau thế nào?
5. Nếu một collection có null, vì sao nên lọc Objects::nonNull trước Predicate.not(String::isBlank)?
6. Với predicateA.and(predicateB), predicateB có chạy khi predicateA trả false không?
7. String.isEmpty và String.isBlank khác nhau thế nào khi dùng cho chuỗi chỉ chứa khoảng trắng?
8. Với một lớp không override equals, isEqual có tự so sánh tất cả field không?
9. Vì sao Predicate.isEqual("ADMIN") không thay thế được predicate so sánh equalsIgnoreCase?
10. Khi thiết kế bộ lọc Stream chạy song song, vì sao không nên cập nhật bộ đếm dùng chung trong callback?
11. Khi dùng JDK 8, cách nào có thể thay thế Predicate.not(predicate) mà giữ được hành vi phủ định?
12. Làm thế nào kết hợp isEqual và not để loại một trạng thái đơn hàng cụ thể mà vẫn giữ các trạng thái khác?

**Tóm tắt:** Predicate.not giúp **phủ định một điều kiện**, đặc biệt gọn khi đi với method reference. Predicate.isEqual tạo **điều kiện so sánh bằng đối tượng mốc**, bao gồm mốc null. Dùng chúng cùng negate, and, or đúng cách sẽ làm các quy tắc lọc và pipeline Java dễ đọc, nhưng vẫn phải hiểu equals, generic type, null, short-circuit và tác dụng phụ của callback.