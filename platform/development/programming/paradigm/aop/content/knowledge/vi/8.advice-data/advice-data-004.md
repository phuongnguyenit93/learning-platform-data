# Giá trị null, kiểu nguyên thủy và chuyển đổi kiểu trong dữ liệu của advice (AOP)

Khi một **advice** nhận dữ liệu tại điểm can thiệp (*join point*) trong lập trình hướng khía cạnh (**Aspect-Oriented Programming, AOP**), dữ liệu có thể xuất hiện dưới nhiều hình thức: đối số tham chiếu là `null`, tham số khai báo `int` nhưng được biểu diễn thành `Integer` trong một mảng `Object[]`, một phương thức trả về `void`, một giá trị có kiểu runtime khác kiểu khai báo hoặc một ngoại lệ được bọc qua reflection. Nếu advice tự ép kiểu mà không phân biệt các trường hợp này, nó có thể thất bại **trước khi** phương thức nghiệp vụ được gọi hoặc **sau khi** phương thức đã có tác dụng phụ.

Vì vậy, khi dùng dữ liệu trong advice, cần trả lời ba câu hỏi riêng biệt:

1. **Pointcut đã chọn join point nào?** Chữ ký khai báo, overload, loại điểm nối và phạm vi áp dụng là gì?
2. **Dữ liệu được bind vào advice bằng cách nào?** Ngữ nghĩa của kiểu tĩnh, kiểu runtime, tham số tên, `null` và kiểu nguyên thủy của mô hình AOP ra sao?
3. **Advice có bảo toàn hợp đồng không?** Nếu chỉ quan sát, nó có chuyển tiếp đúng một lần, giữ kết quả và ngoại lệ, không đưa vào giá trị `null` hoặc kiểu không phù hợp không?

Các cơ chế AOP không hỗ trợ cùng một tập join point hoặc cùng quy tắc *binding*. Bài này giải thích nền tảng Java và các nguyên tắc AOP tổng quát, dùng JDK dynamic proxy để minh họa một hình thức can thiệp **qua phương thức giao diện**. Đây không phải khẳng định proxy tương đương mọi cơ chế weaving hay một cú pháp pointcut được dùng chung.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt **giá trị `null`**, **kiểu tham chiếu**, **kiểu nguyên thủy**, **wrapper class** và tình huống không có giá trị trả về.
- Giải thích boxing/unboxing khi dữ liệu primitive đi qua các API động như `Object[]`, đồng thời hiểu vì sao kiểu khai báo của phương thức không đổi.
- Chọn overload dựa vào kiểu tham số được khai báo thay vì loại đối tượng runtime truyền vào.
- Dùng ép kiểu tham chiếu, kiểm tra `instanceof`, chuyển đổi số, widening/narrowing đúng điều kiện mà không ngụy trang lỗi.
- Phân tích cách `null` ảnh hưởng tới pointcut động, ràng buộc đối số, `this`/`target`, binding kết quả và binding ngoại lệ.
- Nhận diện lỗi `NullPointerException` khi unboxing, `ClassCastException` khi cast sai, sai lệch số do narrowing hoặc khi trả kết quả không tương thích.
- Áp dụng các phép kiểm chứng đối với thành công, lỗi, kết quả `null`, giá trị primitive và đường gọi bỏ qua cơ chế AOP.
- Giữ advice theo dõi độc lập khỏi quy tắc nghiệp vụ và tránh làm lộ dữ liệu nhạy cảm.

## 2. Bốn tầng của một lần can thiệp

Đừng coi “dữ liệu của advice” là một biến duy nhất. Một lần gọi có thể có:

| Tầng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Chữ ký tĩnh** | `compute(int, Object)` | Kiểu và thứ tự tham số phương thức đã được Java chọn |
| **Đối số runtime** | `[7, "A"]` trong cơ chế trả `Object[]` | Giá trị của đúng lần thực thi; `int` có thể được boxing thành `Integer` |
| **Điều kiện pointcut/binding** | “chọn `compute(int,Object)`; bind đối số thứ hai” | Xác định nơi áp advice và biến nào nhận dữ liệu |
| **Hợp đồng advice** | đọc đối số, chuyển tiếp, ghi kết quả/lỗi | Quyết định có giữ nguyên cách thực thi đã định hay thay đổi nó |

Ví dụ một phương thức khai báo tham số `Object` có thể nhận đối tượng `String`. Điều này **không biến phương thức ấy thành overload có tham số `String`**. Cũng vậy, một biến `Object` chứa `Integer` không làm chữ ký của phương thức `int` bị đổi thành `Integer`.

Một bộ weaving có thể tạo mã với kiểu mạnh ở điểm can thiệp; một proxy động có thể chuyển dữ liệu qua `Object[]`. Tư duy về **kiểu tĩnh và biểu diễn động** vẫn áp dụng, nhưng chi tiết binding phải xem theo công cụ.

## 3. `null` là gì và không phải là gì?

`null` là giá trị đặc biệt có thể gán cho **biến kiểu tham chiếu** trong Java:

```java
String name = null;
Integer count = null;
Object payload = null;
```

Trong khi đó, biến kiểu nguyên thủy không thể mang `null`:

```java
int amount = 3;
// int other = null; // Lỗi biên dịch.
```

**`null` không phải một đối tượng.** Nó không có phương thức instance để gọi hoặc một lớp runtime có thể truy vấn bằng `getClass()`. Việc `null` truyền được vào tham số tham chiếu không nói rằng ứng dụng chấp nhận `null` về mặt nghiệp vụ.

### 3.1. `null` trong binding đối số

Giả sử:

```java
String normalize(String text)
```

Nếu người gọi truyền `null`, advice có thể nhận một giá trị `String` bằng `null` **nếu cơ chế binding cho phép trường hợp đó**. Advice này không nên lập tức thực hiện `text.length()`. Phải xử lý hoặc từ chối theo hợp đồng:

```java
if (text == null) {
    // Ghi nhận trạng thái thiếu dữ liệu, không dereference.
} else {
    int length = text.length();
}
```

Đoạn code chỉ mô tả một nhánh kiểm tra; nó **không** yêu cầu advice tự thay đổi `null` thành chuỗi rỗng. Trong một số miền nghiệp vụ, hai giá trị này mang nghĩa khác nhau.

### 3.2. `instanceof` và `null`

Biểu thức `value instanceof String` trả `false` nếu `value == null`. Vì vậy:

```java
Object value = null;
System.out.println(value instanceof String); // false
```

Hệ quả trong AOP: một điều kiện pointcut **kiểm tra kiểu đối tượng runtime** có thể xử lý `null` khác với điều kiện chọn **chữ ký khai báo có tham số `String`**. Không được suy rằng mọi biểu thức kiểu trong mọi ngôn ngữ pointcut có quy tắc giống `instanceof` Java; nhiều ngôn ngữ AOP có quy tắc binding riêng khi đối số null. Cần đọc mô tả điều kiện đó và kiểm thử trực tiếp.

### 3.3. `null` trong overload

```java
void accept(String value);
void accept(Object value);
```

Ở Java, `accept(null)` chọn phiên bản `String`, vì `String` cụ thể hơn `Object` trong tập ứng viên này. Nhưng nếu có `accept(String)` và `accept(Integer)`, lời gọi `accept(null)` không có một overload duy nhất cụ thể hơn và gây lỗi biên dịch; `accept((String) null)` hoặc `accept((Integer) null)` chọn rõ phương thức.

Quan trọng: **lựa chọn overload xảy ra ở phía mã gọi**. Pointcut theo chữ ký `accept(String)` xét phương thức đã được chọn, không phải đoán kiểu của `null` ở thời gian chạy.

### 3.4. `null` không giống `void`

- Phương thức `String find()` trả `null`: lời gọi **trả về bình thường**, có kết quả tham chiếu là `null`.
- Phương thức `void update()` hoàn tất: **không có một giá trị kết quả** như `String` hay `Integer` để người gọi nhận.
- Phương thức `String find()` ném lỗi: **không có kết quả trả về bình thường** cho lần gọi đó.

Một số API reflection biểu diễn `Method.invoke` đối với phương thức `void` bằng `null`. Điều đó là **quy ước biểu diễn của API**, không biến `void` thành một phương thức trả về đối tượng null. Không đưa mọi `result == null` vào cùng nhóm nghiệp vụ “không tìm thấy”.

## 4. Kiểu nguyên thủy và các wrapper class

Java có tám kiểu nguyên thủy:

| Kiểu nguyên thủy | Wrapper | Ghi chú |
| --- | --- | --- |
| `boolean` | `Boolean` | Không phải kiểu số |
| `byte` | `Byte` | Số nguyên 8 bit có dấu |
| `short` | `Short` | Số nguyên 16 bit có dấu |
| `char` | `Character` | Đơn vị mã UTF-16, không phải ký tự Unicode đầy đủ theo mọi cách hiểu |
| `int` | `Integer` | Số nguyên 32 bit có dấu |
| `long` | `Long` | Số nguyên 64 bit có dấu |
| `float` | `Float` | Dấu phẩy động độ chính xác đơn |
| `double` | `Double` | Dấu phẩy động độ chính xác kép |

Một giá trị primitive **không phải đối tượng tham chiếu**. Nhưng nhiều API động của Java dùng `Object` hoặc `Object[]`, nên giá trị primitive có thể được **boxing** thành wrapper tương ứng.

```java
int raw = 12;
Integer boxed = raw;     // Autoboxing.
int again = boxed;       // Unboxing.
Object context = boxed;  // Giữ wrapper Integer.
```

### 4.1. Boxing trong advice qua proxy/reflection

Một giao diện:

```java
interface CounterPort {
    int increment(int delta);
}
```

Khi JDK dynamic proxy nhận lời gọi `increment(5)`, `InvocationHandler` thường nhìn thấy `Method` với kiểu tham số khai báo `int.class`, trong khi phần tử trong `Object[] args` chứa `Integer.valueOf(5)`.

Các mệnh đề đúng đồng thời:

1. **Chữ ký vẫn là `increment(int)`.**
2. **Giá trị được truyền qua `Object[]` bằng wrapper `Integer`.**
3. **Có thể nhận kiểu nguyên thủy trở lại bằng unboxing** khi giá trị không null và wrapper phù hợp.
4. **Số lượng đối số** trong mảng và thứ tự phải được kiểm chứng trước khi cast nếu pointcut có thể chọn nhiều overload.

Một ví dụ minh họa:

```java
int delta = (Integer) args[0];
```

Đoạn này giả định `args != null`, có ít nhất một phần tử, `args[0]` là `Integer` không null và đúng chữ ký. Nếu một điểm can thiệp khác lọt vào bộ lọc, giả định có thể sai. Không suy rằng mọi `Object` số đều cast được thành `Integer`.

### 4.2. Khi nào `args` là `null`?

Theo hợp đồng `InvocationHandler` của JDK dynamic proxy, **mảng đối số có thể là `null` khi phương thức không có tham số**. Đây là đặc điểm của cơ chế proxy, không phải “đối số đầu tiên có giá trị null”.

Phân biệt:

```text
args == null        -> có thể biểu diễn phương thức không tham số
args.length == 1    -> có một phần tử (phần tử ấy có thể là null)
args[0] == null     -> có đối số ở vị trí 0 và giá trị là null
```

Nếu phương thức không có tham số, đọc `args[0]` trực tiếp có thể gây lỗi. Với mô hình AOP có tham số advice được bind theo chữ ký rõ ràng, công cụ có thể làm phần đối chiếu hộ người lập trình; với interceptor tự viết, trách nhiệm kiểm tra thuộc về bạn.

## 5. Unboxing từ `null`: lỗi trước khi nghiệp vụ chạy

Đây là một trong những lỗi dễ làm hỏng advice.

```java
Integer wrapped = null;
// int value = wrapped; // Ném NullPointerException khi chạy.
```

Vì `int` không thể chứa null, unboxing `Integer null` thành `int` gây `NullPointerException`. Lỗi cũng có thể xuất hiện ở biểu thức số học hoặc phép so sánh tưởng chừng vô hại:

```java
Integer count = null;
// if (count > 0) { ... } // Unboxing ngầm -> NullPointerException.
```

Nếu advice thực thi một biểu thức như vậy **trước khi `proceed`**, phương thức đích có thể **không bao giờ được gọi**. Khi đó lỗi quan sát được là do advice, không nhất thiết do nghiệp vụ.

### 5.1. Cách kiểm tra phù hợp

Nếu `null` hợp lệ theo hợp đồng tham số, giữ giá trị là wrapper và xử lý nhánh riêng:

```java
Integer count = (Integer) args[0];
if (count == null) {
    System.out.println("count is absent");
} else {
    System.out.println("count=" + count.intValue());
}
```

Nếu `null` là dữ liệu không hợp lệ, lớp nghiệp vụ hoặc ranh giới xác thực dữ liệu nên **có trách nhiệm xác định cách từ chối**. Advice quan sát không nên tự đổi null thành 0 vì điều đó thay đổi ý nghĩa kết quả.

### 5.2. `Optional` cũng không tự giải mọi vấn đề

`Optional<T>` có thể biểu đạt một giá trị có hoặc không trong API thích hợp, nhưng không làm mọi phương thức Java tự động null-safe. `Optional` cũng không thay thế việc xử lý các trường hợp kiểu nguyên thủy, overload, kết quả `void` hoặc lỗi do proxy/weaver cung cấp dữ liệu không hợp lệ.

Nếu làm việc với số nguyên, có `OptionalInt`, `OptionalLong`, `OptionalDouble` cho một số thiết kế API, nhưng không nên chuyển đổi giao diện nghiệp vụ chỉ để tránh kiểm tra null trong advice.

## 6. Ép kiểu tham chiếu: cast và `instanceof`

Giả sử một bộ chặn nhận `Object value`. Các biểu thức sau có nghĩa khác nhau:

```java
String text = (String) value;         // Cast: lỗi nếu value không phải String phù hợp.
boolean isText = value instanceof String; // Kiểm tra loại runtime.
```

Nếu `value == null`, ép `(String) value` **hợp lệ** và kết quả vẫn là null; `instanceof String` là false. Nhưng nếu `value` là `Integer` thì cast sang `String` gây `ClassCastException`.

Một cú pháp an toàn khi thật sự cần đọc thông tin từ `String`:

```java
if (value instanceof String text) {
    System.out.println("Length=" + text.length());
} else if (value == null) {
    System.out.println("Value is null");
} else {
    System.out.println("Other type");
}
```

Đoạn code Java 17 này **minh họa** kiểm tra kiểu; không phải toàn bộ chương trình. Điều kiện `instanceof` tránh dereference trên null và tránh cast sai khi nhánh không được chọn.

### 6.1. Cast không làm chuyển kiểu đối tượng

Cast `(String) value` yêu cầu giá trị runtime tương thích với `String`; nó **không chuyển `Integer 42` thành `String "42"`**. Nếu thật sự cần một chuỗi mô tả, `String.valueOf(value)` trả `"null"` khi tham số tham chiếu null, hoặc biểu diễn chuỗi phù hợp của đối tượng.

Khác biệt này đặc biệt quan trọng trong advice ghi log: việc chuyển thành chuỗi để quan sát **khác** quyền tự sửa đối số truyền vào phương thức đích.

### 6.2. Kiểm tra kiểu không phải xác thực dữ liệu

Một đối tượng là `String` chỉ chứng minh loại đối tượng, không chứng minh chuỗi ấy là mã đơn hợp lệ, không nhạy cảm hoặc được phép ghi vào log. Tương tự, một `Integer` không có nghĩa số nằm trong miền chấp nhận của nghiệp vụ.

Advice không nên tự xác thực/ủy quyền dựa trên cast và `instanceof` đơn giản nếu ranh giới bảo mật đòi hỏi điều kiện mạnh hơn.

## 7. Chuyển đổi kiểu số: widening, narrowing và wrapper

Java hỗ trợ một số chuyển đổi kiểu nguyên thủy, nhưng không phải mọi kiểu chuyển đổi đều an toàn về độ lớn hay độ chính xác.

### 7.1. Widening primitive

```java
int small = 12;
long wide = small;      // Widening int -> long.
double approx = wide;   // Widening long -> double, có thể mất độ chính xác.
```

Việc gọi chuyển đổi là **widening** không đồng nghĩa mọi giá trị nguyên lớn đều giữ chính xác khi chuyển sang dấu phẩy động. Ví dụ, `long` chứa được những số nguyên mà `double` không biểu diễn chính xác toàn bộ.

### 7.2. Narrowing primitive

```java
long large = 3_000_000_000L;
int narrow = (int) large;  // Mất thông tin; kết quả không còn là 3_000_000_000.
```

Nếu advice “chuẩn hóa” một số tiền, mã định danh hoặc kích thước bằng narrowing mà không kiểm tra phạm vi, dữ liệu có thể bị biến đổi thầm lặng. Với phép chuyển `long` sang `int` đòi hỏi phát hiện tràn, `Math.toIntExact(long)` sẽ ném `ArithmeticException` nếu giá trị không biểu diễn được trong `int`.

### 7.3. Wrapper không có quan hệ kế thừa số tương đương

`Integer` và `Long` đều kế thừa `Number`, nhưng **không** có nghĩa ép `(Long) (Object) Integer.valueOf(5)` hợp lệ. Phép cast ấy gây `ClassCastException`.

Khi thật sự cần chuyển dữ liệu số:

```java
Object data = Integer.valueOf(5);
long converted = ((Number) data).longValue();
```

Đây là phép **chuyển giá trị** dựa trên `Number`, không phải cast wrapper sang wrapper. Nó cần kiểm tra `data != null`, `data instanceof Number` và yêu cầu độ chính xác/phạm vi. `Number.longValue()` không bảo đảm không mất thông tin với mọi lớp con `Number`.

### 7.4. Kiểu chữ ký không tự thay đổi khi có widening ở điểm gọi

Ví dụ có hai overload `calculate(int)` và `calculate(long)`. Lời gọi `calculate(4)` thường chọn `int` khi cả hai khả dụng. Nếu chỉ có `calculate(long)`, Java có thể chuyển `int` thành `long` ở **điểm gọi**. Pointcut theo chữ ký phải chọn **phương thức thật đã được compiler lựa chọn**, không suy ra overload bằng loại đối tượng trong `Object[]`.

Khi proxy nhận phương thức khai báo `long`, đối số primitive của phương thức đó được biểu diễn bằng `Long` tương ứng trong mảng của handler; không vì mã nguồn ban đầu có literal `4` mà handler được bảo đảm nhận `Integer`.

## 8. Binding kiểu tĩnh và kiểu động trong pointcut

Một cơ chế AOP có thể cho phép kết hợp:

- Điều kiện theo **chữ ký phương thức/field**;
- Điều kiện theo **kiểu runtime của đối số**;
- Điều kiện theo **kiểu runtime của đối tượng đích**, khi join point có target;
- Ràng buộc dữ kiện phù hợp vào **biến advice**;
- Điều kiện theo annotation, bối cảnh điều khiển hoặc trạng thái khác được hỗ trợ.

Tuy nhiên, từ “binding một `String`” có thể chỉ hai ý:

1. **Bind đối số ở vị trí xác định của phương thức khai báo `String`**, kể cả khi giá trị null được hợp đồng cho phép.
2. **Chỉ khớp khi đối số thực tế có kiểu runtime `String`**, tức một điều kiện động có thể loại trừ null tùy ngữ nghĩa công cụ.

Không được đánh đồng hai ý. Một số ngôn ngữ pointcut còn có những quy tắc riêng cho kiểu primitive, boxing, binding reference và `null`. Cú pháp như `args(name)` nếu được một công cụ hỗ trợ **không nhất thiết** hoạt động giống `name instanceof T` viết tay trong Java.

### 8.1. Không suy luận “có dữ liệu” từ tên biến

Giả sử một advice khai báo tham số `String orderId`. Tên biến `orderId` chỉ có ý nghĩa nếu **quy tắc binding** đã liên kết nó với đúng dữ kiện ở join point. Công cụ không tự tìm một biến cục bộ cùng tên trong mã nguồn đích.

Nếu hai tham số đều là `String`, việc đảo vị trí binding có thể không gây lỗi kiểu nhưng tạo dữ liệu sai. Đây là lỗi khác với `NullPointerException` hoặc `ClassCastException`, và cần kiểm thử riêng.

### 8.2. Kiểu rộng có thể khiến advice bỏ lỡ thông tin

Một advice khai báo đối số kiểu `Object` có thể nhận nhiều loại giá trị, bao gồm null. Nếu nó cần tính chiều dài chuỗi mà tự cast mọi giá trị sang `String`, chính sự rộng của bộ chọn tạo rủi ro runtime. Có hai chiến lược hợp lệ tùy mục đích:

- **Làm pointcut hẹp** để chọn đúng chữ ký hoặc kiểu đối số mà advice được phép xử lý.
- **Giữ pointcut rộng nhưng xử lý kiểu theo nhánh** an toàn, không giả định mọi đối số thuộc một lớp.

Dù chọn hướng nào, đừng nới pointcut vì “muốn dễ quan sát” rồi vô tình gắn advice thay đổi nghiệp vụ lên những loại join point không phù hợp.

## 9. Giá trị trả về trong advice: null, primitive và void

Khi around advice hoặc một bộ chặn định trả kết quả ra người gọi, **hợp đồng trả về** quan trọng không kém đầu vào.

### 9.1. Phương thức trả tham chiếu

Nếu phương thức khai báo `String find()`, kết quả `null` có thể hợp lệ về kiểu (dù nghiệp vụ có thể cấm). Advice chỉ quan sát thường nên **trả nguyên kết quả** nhận được từ thao tác bên trong.

Khi ghi kết quả, phải xử lý null trước nếu gọi `result.toString()` hoặc dereference. `String.valueOf(result)` có thể an toàn hơn cho log kỹ thuật, nhưng vẫn cần bảo vệ dữ liệu nhạy cảm và chi phí tạo chuỗi.

### 9.2. Phương thức trả primitive

Nếu phương thức khai báo `int count()`, người gọi cần kết quả primitive. Trong JDK dynamic proxy, handler trả `Object`; proxy phải **unbox** giá trị wrapper phù hợp trước khi trả tới người gọi. Nếu handler trả **null** cho phương thức trả primitive, quá trình unboxing của proxy có thể ném `NullPointerException`. Nếu trả một đối tượng kiểu không tương thích, proxy có thể ném `ClassCastException`.

Điều này có nghĩa một advice quanh không được tự coi `null` là “không muốn can thiệp” cho mọi kiểu kết quả. Nếu không có kết quả thay thế hợp lệ, cần **chuyển tiếp đúng kết quả** của đích hoặc tuân thủ hợp đồng rõ ràng về đường lỗi.

### 9.3. Phương thức `void`

Với `void save()`, không có giá trị nghiệp vụ trả về. Một handler proxy thông thường có thể trả `null` cho kiểu `void` theo hợp đồng `InvocationHandler` mà không gây vấn đề tương tự kiểu primitive. Nhưng điều này không biến `save()` thành `Object save()`; mã gọi vẫn không thể lấy kết quả từ phương thức void.

Phân biệt ba trường hợp:

| Chữ ký | Kết quả hợp lệ | Lỗi thường gặp trong advice |
| --- | --- | --- |
| `String name()` | Một `String` hoặc null về mặt kiểu Java | Gọi `toString` trên null |
| `int count()` | Giá trị int (trong proxy biểu diễn qua `Integer`) | Handler trả null hoặc sai wrapper |
| `void update()` | Không có giá trị trả về | Cố coi null của API reflection là một “kết quả nghiệp vụ” |

### 9.4. After-returning và after-throwing không hoán đổi được

Một lời gọi trả null bình thường là nhánh **after-returning**, không phải nhánh **after-throwing**. Nếu advice sau thành công yêu cầu ràng buộc một kiểu cụ thể, điều kiện binding có thể giới hạn những kết quả được advice nhận; phải xem quy tắc công nghệ.

Ngược lại, nếu đích ném lỗi, không có kết quả trả về bình thường để bind vào tham số result. Advice after-throwing có thể nhận đối tượng lỗi theo hợp đồng loại ngoại lệ được hỗ trợ.

## 10. Ngoại lệ khi ép kiểu và ngoại lệ của nghiệp vụ

Một `ClassCastException` xảy ra **trong thân advice** có thể là lỗi kỹ thuật của khía cạnh; nó không chứng minh đích đã xử lý sai dữ liệu. Một `IllegalArgumentException` xảy ra khi `Method.invoke` nhận đối số không tương thích cũng có thể xuất phát từ lớp chuyển tiếp, không phải từ thân phương thức đích.

Phân biệt các nguồn:

| Vị trí phát sinh | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Binding/cast trong advice** | `(String) Integer.valueOf(2)` | Sai giả định kiểu của advice |
| **Unboxing trong advice** | `int n = (Integer) null` | Không thể chuyển null thành primitive |
| **Gọi reflection** | Mảng đối số sai số lượng hoặc kiểu | Lỗi truyền tham số trước khi target chạy |
| **Target** | `throw new IllegalArgumentException(...)` trong nghiệp vụ | Lỗi gốc của logic được gọi |
| **Unboxing kết quả proxy** | Handler trả null cho `int` | Lỗi chuyển kết quả ở ranh giới proxy |
| **Cleanup/logging advice** | Mã ghi log tự ném lỗi | Có thể thay hoặc che lỗi gốc |

### 10.1. `InvocationTargetException` không phải lỗi nghiệp vụ gốc

Khi dùng `Method.invoke`, ngoại lệ do thân phương thức đích ném thường được bọc bởi `InvocationTargetException`. Khi muốn giữ ngoại lệ gốc qua proxy, handler có thể làm:

```java
try {
    return method.invoke(target, args);
} catch (java.lang.reflect.InvocationTargetException ex) {
    throw ex.getCause();
}
```

Đây là **đoạn mã dùng bên trong một phương thức khai báo `throws Throwable`**, không phải chương trình độc lập. Nếu chỉ ghi wrapper, advice có thể chẩn đoán nhầm loại lỗi. Tuy vậy đừng bắt mọi `Throwable` rồi mặc định nó đến từ target: các lỗi ngay trong advice hoặc trong cơ chế chuyển tiếp cũng cần được phân biệt.

### 10.2. Advice không được nuốt lỗi ép kiểu rồi trả kết quả bất kỳ

Một mẫu nguy hiểm là:

```java
try {
    return proceed();
} catch (ClassCastException ex) {
    return null;
}
```

Đây là giả mã theo phong cách Java: `proceed()` phải được định nghĩa bởi cơ chế AOP. Trả null để che lỗi không an toàn nếu phương thức có kết quả primitive; nó cũng có thể biến lỗi lập trình thành kết quả nghiệp vụ giả.

Cách sửa là **làm rõ tập điểm và kiểu binding** thay vì dùng fallback tùy ý khi phát hiện một cast sai.

## 11. Ví dụ Java 17: null, primitive boxing và kết quả advice

Ví dụ dưới đây dùng **JDK dynamic proxy** để minh họa cơ chế nhận dữ liệu ở handler, chọn phương thức theo chữ ký, quan sát `null`, unboxing có kiểm soát và chuyển tiếp kết quả/ngoại lệ. Tất cả chỉ dùng JDK 17, không cần thư viện bên ngoài.

Lưu toàn bộ thành `AdviceDataDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class AdviceDataDemo {
    interface Calculation {
        int add(int left, int right);
        Integer doubleOrNull(Integer number);
        String describe(Object payload);
    }

    static final class Calculator implements Calculation {
        @Override
        public int add(int left, int right) {
            if (left < 0) {
                throw new IllegalArgumentException("left phải không âm");
            }
            return left + right;
        }

        @Override
        public Integer doubleOrNull(Integer number) {
            return number == null ? null : number * 2;
        }

        @Override
        public String describe(Object payload) {
            return payload == null ? "<null>" : payload.toString();
        }
    }

    private static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    static Calculation withAdvice(Calculation target) {
        return (Calculation) Proxy.newProxyInstance(
            Calculation.class.getClassLoader(),
            new Class<?>[] { Calculation.class },
            (proxy, method, args) -> {
                System.out.println("[ENTER] " + method.getName()
                        + " args=" + Arrays.toString(args));

                if (method.getName().equals("add")) {
                    if (!Arrays.equals(method.getParameterTypes(),
                            new Class<?>[] { int.class, int.class })) {
                        throw new IllegalStateException("Wrong signature");
                    }

                    // int của chữ ký được boxing thành Integer trong Object[].
                    int left = (Integer) args[0];
                    int right = (Integer) args[1];
                    System.out.println("[BIND] add=" + left + "+" + right);
                } else if (method.getName().equals("doubleOrNull")) {
                    Integer number = (Integer) args[0];
                    System.out.println("[BIND] number=" + number);
                } else if (method.getName().equals("describe")) {
                    Object payload = args[0];
                    String type = payload == null
                            ? "null" : payload.getClass().getSimpleName();
                    System.out.println("[BIND] runtimeType=" + type);
                }

                try {
                    Object result = invokeTarget(method, target, args);
                    System.out.println("[RETURN] " + String.valueOf(result));
                    return result;
                } catch (Throwable error) {
                    System.out.println("[THROW] "
                            + error.getClass().getSimpleName());
                    throw error;
                }
            }
        );
    }

    public static void main(String[] args) {
        Calculation monitored = withAdvice(new Calculator());

        System.out.println("CALLER add=" + monitored.add(2, 3));
        System.out.println("CALLER missing=" + monitored.doubleOrNull(null));
        System.out.println("CALLER double=" + monitored.doubleOrNull(4));
        System.out.println("CALLER describe=" + monitored.describe("A"));
        System.out.println("CALLER null=" + monitored.describe(null));

        try {
            monitored.add(-1, 1);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER error=" + error.getMessage());
        }

        System.out.println("DIRECT add=" + new Calculator().add(1, 1));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AdviceDataDemo.java
java AdviceDataDemo
```

Đầu ra dự kiến:

```text
[ENTER] add args=[2, 3]
[BIND] add=2+3
[RETURN] 5
CALLER add=5
[ENTER] doubleOrNull args=[null]
[BIND] number=null
[RETURN] null
CALLER missing=null
[ENTER] doubleOrNull args=[4]
[BIND] number=4
[RETURN] 8
CALLER double=8
[ENTER] describe args=[A]
[BIND] runtimeType=String
[RETURN] A
CALLER describe=A
[ENTER] describe args=[null]
[BIND] runtimeType=null
[RETURN] <null>
CALLER null=<null>
[ENTER] add args=[-1, 1]
[BIND] add=-1+1
[THROW] IllegalArgumentException
CALLER error=left phải không âm
DIRECT add=2
```

### 11.1. Những điểm quan trọng của ví dụ

1. `Calculation.add(int,int)` khai báo kiểu primitive. `Method.getParameterTypes()` vẫn có `int.class`, nhưng handler nhận `Integer` trong `Object[]`. Ép `(Integer)` rồi unboxing là phù hợp khi đã xác nhận chữ ký.
2. `doubleOrNull(Integer)` là kiểu tham chiếu: có thể nhận null và trả null. Cả hai trường hợp đều đi qua nhánh trả về bình thường, không phải ngoại lệ.
3. `describe(Object)` nhận chuỗi `"A"` nhưng chữ ký vẫn là `Object`; `runtimeType=String` là thông tin của **giá trị**.
4. `describe(null)` không được gọi `payload.getClass()` trực tiếp. Advice phân nhánh để không ném lỗi khi giá trị null.
5. `add(-1,1)` cho thấy lỗi do **đích** ném, được tháo khỏi `InvocationTargetException` rồi chuyển tiếp tới người gọi. Advice chỉ ghi loại lỗi và giữ nguyên ngoại lệ.
6. `new Calculator().add(1,1)` gọi trực tiếp đối tượng đích, **không qua proxy**, nên không có `[ENTER]` hoặc `[RETURN]`. Điều này minh họa phạm vi của proxy, không phải mọi công nghệ AOP.
7. `Arrays.toString(args)` được dùng cho giao diện có tham số ở mọi phương thức đang demo. Khi mở rộng handler cho phương thức **không tham số**, phải xử lý `args == null` nếu định truy cập phần tử.
8. Ví dụ in dữ liệu người gọi chỉ để học cách binding; với ứng dụng thật cần bảo vệ mã định danh, token, nội dung riêng tư và dữ liệu có thể nhạy cảm.

### 11.2. Vì sao ví dụ không gọi advice là pointcut hoàn chỉnh?

Bộ lọc theo `method.getName()` trong handler chỉ là **logic Java do người lập trình viết**. Ngôn ngữ pointcut đầy đủ có thể hỗ trợ nhiều loại join point, điều kiện khai báo, kiểu runtime, annotation và luật kết hợp. Dynamic proxy này chỉ chặn **lời gọi phương thức qua giao diện đại diện**.

Vì vậy kết quả của ví dụ chỉ chứng minh: **nếu lời gọi đi qua proxy, dữ liệu nào có thể được quan sát và chuyển tiếp như thế nào**. Nó không chứng minh mọi truy cập field, constructor, phương thức tĩnh/private hoặc lời gọi nội bộ đều được advice nhận.

## 12. Ví dụ Java 17: lỗi khi handler trả null cho primitive

Một lỗi khác xuất hiện ở ranh giới trả kết quả. Để nhìn thấy rõ, lưu mã hoàn chỉnh thành `PrimitiveReturnDemo.java`:

```java
import java.lang.reflect.Proxy;

public class PrimitiveReturnDemo {
    interface NumberPort {
        int value();
    }

    public static void main(String[] args) {
        NumberPort invalid = (NumberPort) Proxy.newProxyInstance(
                NumberPort.class.getClassLoader(),
                new Class<?>[] { NumberPort.class },
                (proxy, method, input) -> null
        );

        try {
            System.out.println(invalid.value());
        } catch (NullPointerException error) {
            System.out.println("NULL_FOR_INT NullPointerException");
        }

        NumberPort valid = (NumberPort) Proxy.newProxyInstance(
                NumberPort.class.getClassLoader(),
                new Class<?>[] { NumberPort.class },
                (proxy, method, input) -> Integer.valueOf(7)
        );

        System.out.println("VALID " + valid.value());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 PrimitiveReturnDemo.java
java PrimitiveReturnDemo
```

Đầu ra:

```text
NULL_FOR_INT NullPointerException
VALID 7
```

**Tại sao?** `NumberPort.value()` khai báo `int`. Handler có kiểu trả về `Object`, và lớp proxy phải chuyển giá trị đó sang `int`. Nó không thể unbox `null`; `Integer.valueOf(7)` thì phù hợp và cho kết quả 7.

Đây là hành vi của JDK dynamic proxy. Một bộ AOP có binding kết quả và kiểm tra kiểu ở giai đoạn weaving có thể phát hiện lỗi ở thời điểm khác; không nên suy rằng mọi công nghệ đều ném cùng loại lỗi tại cùng điểm thực thi. Điều cần nhớ là **đường return của advice phải phù hợp hợp đồng kiểu kết quả của điểm can thiệp**.

## 13. Nếu advice chủ động sửa đối số

Một số around advice có thể gọi tiếp với đối số thay thế, nhưng **năng lực và quy tắc đó phụ thuộc mô hình**. Nếu được hỗ trợ, trước khi thay dữ liệu cần xét:

- Đối số được thay có cùng kiểu/hợp đồng với tham số của phương thức đã chọn không?
- Nếu thay null cho tham số primitive, cơ chế từ chối ở giai đoạn nào?
- Nếu chuyển số `long` sang `int`, có kiểm tra tràn không?
- Nếu thay wrapper bằng kiểu runtime khác, cơ chế có thể thực hiện conversion được không, hay ném lỗi?
- Thay đối số có làm mất định danh giao dịch, khóa chống trùng hoặc dữ liệu audit không?
- Nếu gọi tiếp nhiều lần với các giá trị khác nhau, tác dụng phụ có bị lặp không?

Tuyệt đối không dùng “cast thành kiểu cần thiết” như công cụ sửa dữ liệu tùy tiện. `((Number) value).intValue()` có thể cắt phần thập phân hoặc tràn tùy lớp số; nó không tương đương một phép xác minh miền giá trị.

### 13.1. Chữ ký overload không tự được giải lại

Trong Java, `handle(Object)` không tự đổi thành `handle(String)` chỉ vì around advice thay giá trị đối số thành một đối tượng `String`. Thông thường, điểm thực thi đã được lựa chọn theo chữ ký/cấu trúc của join point. Nếu cần gọi overload khác, đó là **một thao tác điều phối khác có chủ đích**, không phải phép đổi kiểu thông thường của binding.

## 14. Generics, type erasure và bridge methods

Java xóa phần lớn thông tin tham số kiểu generic khi biên dịch (*type erasure*). Xét:

```java
interface Handler<T> {
    T handle(T value);
}

class TextHandler implements Handler<String> {
    @Override
    public String handle(String value) {
        return value;
    }
}
```

Đây là **mã minh họa**, không phải tệp thực thi độc lập. Compiler có thể tạo phương thức cầu nối (*bridge method*) để giữ hành vi đa hình sau erasure. Một công cụ phân tích bytecode/reflection có thể nhìn thấy thêm phương thức tổng hợp, trong khi người đọc mã nguồn chỉ thấy phiên bản `handle(String)`.

Các vấn đề đối với advice:

1. `Method.getParameterTypes()` trả kiểu đã xóa/khai báo ở cấp lớp đang phản chiếu; không tự khôi phục mọi tham số generic `T` ở nguồn.
2. Một điểm `handle(Object)` do bridge có thể chuyển tiếp tới `handle(String)`; việc đếm join point/advice phụ thuộc công nghệ và loại điểm được weaving.
3. Phép cast generic có thể bị compiler chèn ở đường thực thi, gây `ClassCastException` ở vị trí khác điều bạn tưởng.
4. Nếu advice yêu cầu kiểu `String`, phải phân biệt pointcut theo **chữ ký gốc của interface**, **phương thức hiện thực** và **giá trị runtime**.

`Method.isBridge()` và `Method.isSynthetic()` giúp kiểm tra một số phương thức do compiler sinh trong Java Reflection. Nhưng không nên loại bỏ chúng vô điều kiện khỏi mọi chính sách; tập điểm mong muốn phải được định nghĩa theo hợp đồng nghiệp vụ và khả năng AOP thực tế.

## 15. `this`, `target` và đối tượng vắng mặt

Ngoài args/result, một advice có thể cần đối tượng đang thực thi hoặc đối tượng đích. Một số mô hình phân biệt `this` và `target` theo loại join point:

- Ở điểm gọi phương thức, đối tượng chứa mã phát sinh lời gọi và đối tượng nhận lời gọi có thể là hai đối tượng khác nhau.
- Ở một điểm thực thi instance, chúng có thể trùng nhau theo ngữ nghĩa công nghệ.
- Với thao tác tĩnh hoặc điểm nối không có receiver, **không được mặc định luôn có một target instance**.
- Với JDK proxy, handler được cung cấp một tham chiếu proxy trong tham số `proxy`, nhưng không vì thế mà tham số này luôn đại diện cho **target thực tế**; target có thể là đối tượng mà handler tự giữ để chuyển tiếp.

Vì vậy dùng `target.getClass()` trong advice đòi hỏi có target thực sự và khác null. Nếu metadata của join point đã đủ để ghi log, không cần tự dereference một đối tượng vốn có thể vắng mặt.

## 16. Số, độ chính xác và dữ liệu nghiệp vụ

Việc ép kiểu trong advice có thể làm thay đổi các miền nhạy cảm:

- **Giá tiền:** `float`/`double` có biểu diễn nhị phân giới hạn; quy tắc làm tròn và đơn vị cần được định nghĩa rõ. Không dùng `Double` thay tùy tiện cho `BigDecimal` trong một chính sách chuyển tiền.
- **Mã định danh:** chuyển `long` sang `int` có thể mất dữ liệu; ID không phải lúc nào là đại lượng để làm toán.
- **Thời lượng:** `Duration`, nanoseconds và milliseconds có thể khác đơn vị; narrowing có thể tràn.
- **Số lượng:** `Integer null` có thể biểu thị “không cung cấp”, trong khi `0` biểu thị đã cung cấp giá trị 0.
- **Tỷ lệ:** chuyển `double` sang `int` làm mất phần thập phân, không tự thực hiện nghiệp vụ làm tròn mong muốn.
- **Kiểu boolean:** `Boolean null` có thể có ý nghĩa ba trạng thái; `boolean` chỉ có hai trạng thái.

Một advice đo đạc có thể chuyển dữ liệu sang loại biểu diễn phù hợp cho hệ quan sát, nhưng phải **không biến dữ liệu đầu vào của nghiệp vụ** khi không có quyền.

### 16.1. Boxing cũng có chi phí

Trên các đường gọi nóng, tạo wrapper, mảng đối số và dùng reflection/proxy có thể tăng chi phí. JVM có thể tối ưu một phần, nhưng không nên tuyên bố “boxing luôn tạo allocation” hoặc “không có chi phí vì cache wrapper”.

Khi hiệu năng quan trọng, hãy benchmark đúng đường thực thi và công cụ AOP trong môi trường gần sản xuất; đừng suy chi phí từ một lần in log hoặc một ví dụ nhỏ.

## 17. Kiểm thử từng trường hợp

Một ma trận test nên kiểm tra **pointcut có đúng**, **binding có đúng** và **hợp đồng kết quả có được giữ**:

| Ca kiểm thử | Mong đợi |
| --- | --- |
| Đối số `String` hợp lệ | Advice nhận đúng chuỗi, đích chạy đúng một lần |
| Đối số tham chiếu null | Advice không dereference lỗi; xử lý theo hợp đồng |
| Đối số primitive `int` | Binding có kiểu khai báo `int` và biểu diễn runtime phù hợp |
| Wrapper `Integer` là null | Không unbox bất cẩn |
| Hai overload `f(int)`, `f(Integer)` | Pointcut chọn đúng chữ ký mong muốn |
| Đối số `Object` giữ `String` runtime | Không nhầm chữ ký `Object` thành `String` |
| Giá trị trả `String null` | Nhánh return bình thường, không báo throw |
| Phương thức `void` | Không ép một giá trị kết quả vốn không tồn tại |
| Phương thức trả primitive và handler trả null | Phát hiện lỗi tại ranh giới kiểu trả về |
| Cast sai lớp wrapper | Lỗi được nhận diện, không bị nuốt hoặc đổi kết quả tùy tiện |
| Chuyển `long` sang `int` quá phạm vi | Có kiểm tra tràn nếu hợp đồng đòi tính chính xác |
| Đích ném ngoại lệ | Advice ghi nhận và chuyển tiếp lỗi gốc |
| Advice ném lỗi trước khi chuyển tiếp | Xác định đích không chạy, phân biệt lỗi advice |
| Lời gọi bỏ qua proxy / mã chưa weaving | Không giả định advice được áp |
| Hai lời gọi đồng thời | Dữ liệu mỗi lần advice không lẫn nhau |
| Dữ liệu nhạy cảm | Không in hoặc lưu giá trị ngoài chính sách |

### 17.1. Quy trình chẩn đoán khi xuất hiện `NullPointerException` trong advice

1. Xác định `null` thuộc **đối số**, **target**, **mảng `args`**, **kết quả** hay **ngữ cảnh kỹ thuật**.
2. Kiểm tra chữ ký phương thức thật: tham số đó khai báo primitive hay reference?
3. Xác định có phép dereference hoặc **unboxing ngầm** không.
4. Nếu handler lấy `args[0]`, kiểm tra có đúng số phần tử và vị trí không.
5. Nếu null ở kết quả, xem phương thức trả reference, primitive hay void.
6. Xác định lỗi phát sinh **trước `proceed`**, **trong target** hay **sau khi nhận kết quả**.
7. Sửa điều kiện/binding hoặc hợp đồng xử lý null; không ngầm chuyển null thành giá trị mặc định khi miền nghiệp vụ không cho phép.
8. Kiểm thử lại cả các đường mà pointcut không được áp dụng.

### 17.2. Quy trình chẩn đoán `ClassCastException`

1. Xem lớp runtime thật của giá trị (khi khác null) và kiểu đích của cast.
2. Kiểm tra `Method.getParameterTypes()` cùng số/thứ tự tham số; có overload không?
3. Xem giá trị primitive đã được boxing thành wrapper nào.
4. Phân biệt **cast wrapper** với **chuyển giá trị primitive/số**.
5. Kiểm tra generic erasure/bridge nếu phương thức generic đang tham gia.
6. Xác minh dữ liệu có được thay bởi một around advice khác trong chuỗi không.
7. Thu hẹp pointcut hoặc thêm nhánh xử lý kiểu phù hợp; không chỉ bắt lỗi rồi trả null.
8. Kiểm tra lại kết quả/ngoại lệ và tác dụng phụ của lời gọi gốc.

## 18. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `null` là một đối tượng có lớp runtime | Dereference hoặc giả định kiểu sai | Xử lý null tách biệt |
| Dùng `instanceof T` để khẳng định chữ ký khai báo là `T` | Khớp nhầm overload nhận `Object` | So chữ ký và tiêu chí runtime riêng |
| Ép `(Integer) args[0]` khi pointcut chọn mọi overload | Cast sai hoặc không có phần tử | Lọc chữ ký/kiểm tra args trước |
| Tưởng mảng `Object[]` chứa primitive trực tiếp | Lẫn cơ chế boxing | Hiểu wrapper tương ứng |
| Unbox một `Integer null` | `NullPointerException` | Kiểm tra null, giữ dữ liệu reference khi cần |
| Coi `int` và `Integer` là cùng chữ ký | Chọn sai pointcut | Phân biệt primitive và wrapper |
| Dùng `(Long) objectInteger` | `ClassCastException` | Chuyển số có kiểm tra, không cast wrapper ngang |
| Ép `long` xuống `int` tùy ý | Tràn/mất dữ liệu | Kiểm tra phạm vi hoặc dùng `Math.toIntExact` |
| Trả null từ handler cho phương thức trả `int` | Lỗi unboxing ở proxy | Trả đúng wrapper/giữ giá trị gốc |
| Xem `void` là một kết quả null nghiệp vụ | Ghi sai trạng thái | Phân biệt chữ ký void với reference trả null |
| Catch mọi lỗi và trả null | Che lỗi gốc, phá hợp đồng | Chuyển tiếp ngoại lệ phù hợp |
| Đổi tham số khi chỉ được yêu cầu ghi log | Thay hành vi nghiệp vụ | Giữ input/output nguyên dạng |
| Tin rằng binding đúng là đã weaving đúng | Bỏ sót đường gọi trực tiếp | Kiểm chứng cơ chế và phạm vi |
| Log toàn bộ `args` hoặc `result` | Rò rỉ thông tin | Ghi tối thiểu, che dữ liệu nhạy cảm |
| Lưu dữ liệu lời gọi trong field aspect dùng chung | Lẫn ngữ cảnh khi đồng thời | Dùng biến theo lần thực thi |

## 19. Bài tập vận dụng và đáp án

### Bài 1 — Null và primitive

Cho:

```java
Integer x = null;
// int y = x;
```

Dòng thứ hai (nếu bỏ chú thích) có hợp lệ khi biên dịch và chuyện gì xảy ra khi chạy?

**Đáp án:** Dòng mã hợp lệ về cú pháp/kiểu nhờ unboxing từ `Integer` sang `int`; khi thực thi nó ném `NullPointerException` vì `x` là null. Advice không nên thực hiện unboxing vô điều kiện nếu dữ liệu đầu vào có thể null.

### Bài 2 — Null có phải một lỗi không?

Phương thức `String find()` trả null bình thường. Advice sau thành công có nhất thiết là nhánh after-throwing không?

**Đáp án:** Không. Đây là lời gọi trả về bình thường. Việc bind null vào một tham số advice kiểu cụ thể phụ thuộc công nghệ, nhưng không nên gắn nhãn “exception” chỉ vì giá trị kết quả là null.

### Bài 3 — Boxing trong proxy

Một phương thức khai báo `long process(long amount)`, người gọi truyền literal `3`. Trong handler JDK proxy, kiểu tham số khai báo và biểu diễn đối số tương ứng thường là gì?

**Đáp án:** Chữ ký đích có tham số `long` (reflection trả `long.class`); sau khi Java chuyển literal nguyên thủy theo lời gọi tới tham số `long`, phần tử `Object[]` được biểu diễn bằng `Long`. Không giả định có `Integer` chỉ vì literal ban đầu là một giá trị `int`.

### Bài 4 — Cast ngang giữa wrapper

`Object o = Integer.valueOf(9)`. Biểu thức `(Long) o` có chuyển giá trị 9 thành một `Long` không?

**Đáp án:** Không. Nó gây `ClassCastException` khi chạy. Nếu cần giá trị long, có thể dùng `((Number)o).longValue()` sau khi xác minh kiểu/phạm vi, hoặc dùng unboxing rồi widening theo thiết kế rõ.

### Bài 5 — `args == null` khác `args[0] == null`

Trong JDK proxy, một phương thức không tham số được gọi; handler dự kiến đọc `args[0]`. Vì sao điều này nguy hiểm?

**Đáp án:** Với phương thức không có tham số, mảng `args` có thể là null. Không có phần tử 0 để đọc. Phải chọn/kiểm tra chữ ký và dạng mảng trước khi truy cập.

### Bài 6 — Primitive return

Một handler proxy cho giao diện có phương thức `int total()` trả `null` để biểu thị “không có dữ liệu”. Điều gì xảy ra?

**Đáp án:** Proxy cần unbox kết quả thành `int`; null không thể unbox và có thể gây `NullPointerException`. Phải tuân thủ hợp đồng kiểu trả về; nếu API cần thể hiện thiếu dữ liệu, kiểu tham chiếu hoặc thiết kế result phù hợp phải được xác định ở hợp đồng, không dùng null tùy ý trong handler.

### Bài 7 — Kiểu runtime khác chữ ký

Một lớp có `send(Object)` và `send(String)`, mã gọi `send((Object)"A")`. Pointcut chọn chữ ký `send(String)` có được áp chỉ vì đối tượng truyền là `String` không?

**Đáp án:** Không. Mã gọi chọn `send(Object)`; kiểu runtime của giá trị và kiểu khai báo của overload là hai tiêu chí khác nhau. Một điều kiện dynamic riêng có thể xem xét giá trị runtime nếu công nghệ hỗ trợ.

### Bài 8 — Độ chính xác

Một advice nhận `long` rồi ép `(int)` trước khi chuyển tiếp để phù hợp một API khác. Những rủi ro nào cần kiểm tra?

**Đáp án:** Giá trị ngoài phạm vi `int` có thể bị cắt mất phần bit cao. Nếu việc chuyển này được phép thì phải kiểm tra phạm vi (`Math.toIntExact` khi phù hợp), đơn vị, ý nghĩa nghiệp vụ và hợp đồng đầu vào; không nên làm việc đó trong advice thuần quan sát.

### Bài 9 — Lỗi advice hay lỗi target?

Một advice ép `args[0]` sang `String` nhưng đối số thật là `Integer`. Phương thức đích có chắc đã chạy không?

**Đáp án:** Không. Cast có thể ném `ClassCastException` ngay trong advice trước khi `proceed`. Cần phân biệt nguồn lỗi dựa trên vị trí phát sinh và đường thực thi, không quy mọi ngoại lệ cho phương thức đích.

### Bài 10 — Chọn cách kiểm thử

Bạn có một pointcut theo tên `process` và advice đọc phần tử 0 thành `Integer`. Hãy nêu ít nhất ba ca cần thử.

**Đáp án:** Nên thử overload `process(int)` (primitive được boxing), `process(Integer)` với null (không được unbox mù quáng), `process(String)` (không khớp hoặc phải được xử lý khác), và `process()` (mảng args có thể null). Đồng thời thử kết quả/ngoại lệ và các đường bỏ qua cơ chế AOP.

## 20. Ghi nhớ

- **`null` chỉ dùng như một giá trị tham chiếu**, không phải primitive hay một đối tượng có kiểu runtime.
- **Kiểu phương thức khai báo** và **đối tượng biểu diễn giá trị trong handler/advice** là hai lớp thông tin khác nhau; primitive có thể được boxing trong `Object[]`.
- `int` và `Integer` là hai kiểu khác nhau. **Unboxing null** gây lỗi, cast ngang giữa wrapper không phải chuyển số, narrowing có thể mất thông tin.
- **Pointcut theo chữ ký** khác điều kiện theo kiểu đối số runtime; ngữ nghĩa binding với null, primitive và kết quả phụ thuộc cơ chế AOP.
- Kết quả trả null, phương thức void và đường ném ngoại lệ **không đồng nghĩa**. Phương thức trả primitive đòi một giá trị tương thích ở ranh giới trả kết quả.
- **Advice chỉ để quan sát nên giữ nguyên đối số, kết quả, ngoại lệ và số lần thực thi**; nếu cần chuyển kiểu hoặc thay dữ liệu, phải có hợp đồng riêng.
- Kiểm thử cả trường hợp khớp lẫn không khớp, null, boxed primitive, overload, lỗi chuyển kiểu, giá trị trả về và phạm vi weaving/proxy.
