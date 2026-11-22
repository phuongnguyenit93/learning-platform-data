# Suy luận kiểu trong Java Generics: giới hạn trên, giới hạn dưới và kiểu cha chung phù hợp

## 1. Tại sao Java cần suy luận kiểu?

Khi gọi một phương thức generic, Java thường suy ra các type argument thay vì buộc lập trình viên chỉ rõ chúng. Ví dụ:

~~~java
static <T> T first(T a, T b) {
    return a;
}

String word = first("Java", "Generics");
Number number = first(10, 2.5);
~~~

Trong lời gọi đầu, cả hai đối số có kiểu `String`. Ở lời gọi sau, `10` và `2.5` lần lượt được boxing thành `Integer` và `Double` khi dùng trong quá trình suy luận với `T` là kiểu tham chiếu. Java phải chọn một `T` thỏa các điều kiện của **cả hai đối số**, đồng thời xét ngữ cảnh gán kết quả cho `Number`.

Bài học tập trung vào ba thành phần:

1. **Giới hạn dưới (lower bound):** những kiểu mà một biến suy luận phải là *supertype* của chúng; thường nảy sinh từ đối số được truyền vào.
2. **Giới hạn trên (upper bound):** những kiểu mà biến suy luận phải là *subtype* của chúng; có thể đến từ `extends` trong khai báo hoặc các điều kiện kiểu ở nơi sử dụng.
3. **Kiểu cha chung phù hợp (least upper bound, LUB):** giúp tìm loại chung đủ cụ thể để biểu diễn nhiều kiểu đầu vào khác nhau.

Đừng nhầm các **ràng buộc của thuật toán type inference** với wildcard `? extends T` và `? super T`. Wildcard là cấu trúc kiểu trong chương trình; thuật toán inference thu thập các ràng buộc về biến suy luận để quyết định chúng có thể được thay bằng những kiểu cụ thể nào. Hai cơ chế có liên quan nhưng không đồng nhất.

## 2. Thuật ngữ: `T` trong mã và biến suy luận `α` trong compiler

Một method generic khai báo **type parameter** `T`:

~~~java
static <T extends Number> T laterNumber(T a, T b) {
    return b;
}
~~~

Khi gọi `laterNumber(10, 2.5)` mà không viết type argument tường minh, compiler thay `T` bằng một **inference variable** tạm thời (trong mô tả JLS thường ghi `α`). Sau khi giải các ràng buộc, compiler chọn một kiểu hoặc quan hệ kiểu phù hợp rồi kiểm tra toàn bộ lời gọi.

Ký hiệu trong bảng sau là **mô hình toán học**, không phải cú pháp Java:

| Ràng buộc | Đọc thế nào? | Ví dụ ý nghĩa |
| --- | --- | --- |
| `Integer <: α` | `α` phải là một supertype của `Integer` | Đối số `Integer` phải truyền được cho tham số kiểu `T`. |
| `Double <: α` | `α` phải là một supertype của `Double` | Đối số `Double` cũng phải hợp lệ. |
| `α <: Number` | `α` phải thuộc `Number` hoặc subtype | Khai báo `<T extends Number>` đặt giới hạn trên. |
| `α = Integer` | `α` được ràng buộc bằng `Integer` | Một type argument cụ thể/quan hệ invariant có thể yêu cầu điều này. |

`A <: B` nghĩa là `A` là subtype của `B`. Vì vậy cần đặc biệt nhớ hướng:

- **Lower bound của `α` là `Integer`** tức `Integer <: α`, *không* có nghĩa `α` phải nhỏ hơn `Integer`.
- **Upper bound của `α` là `Number`** tức `α <: Number`, *không* có nghĩa `α` phải rộng hơn `Number`.

Một nghiệm hợp lệ phải thỏa **đồng thời** các ràng buộc đó. Với `Integer <: α <: Number`, `Integer` hoặc `Number` có thể là lựa chọn tương thích tùy những điều kiện khác của lời gọi. Java còn phải xử lý equality bounds, kiểu giao (*intersection types*), capture conversion, target typing và nhiều quy tắc đặc thù; không thể suy luận một kiểu duy nhất chỉ bằng việc nhìn một dấu `extends`.

## 3. Lower bounds được tạo ra từ các đối số ra sao?

Xét:

~~~java
static <T> T choose(T left, T right) {
    return left;
}

Number n = choose(10, 2.5);
~~~

Đối số `10` có kiểu primitive `int` và `2.5` có kiểu primitive `double`. Trong ngữ cảnh generic cần kiểu tham chiếu, compiler có thể sử dụng boxing thành `Integer` và `Double`. Hai điều kiện cốt lõi là:

~~~text
Integer <: α
Double  <: α
~~~

Nghĩa là `α` phải chấp nhận cả hai đối số. Việc `Integer` và `Double` cùng có cha là `Number` giúp `Number` trở thành **một kiểu tương thích** cho nơi nhận kết quả.

**Không nên kết luận kiểu suy luận nội bộ luôn chính xác là `Number`.** Theo JLS §4.10.4, LUB trong Java có thể là một *intersection type* bao gồm các interface chung như `Comparable<?>` cùng với một class chung; target context cũng có thể ảnh hưởng đến nghiệm. Người dùng API nên dựa trên kiểu khai báo và các phép gán hợp lệ thay vì cố đoán chính xác tên kiểu compiler chọn trong mọi trường hợp.

### 3.1. Trường hợp đối số có cùng kiểu

~~~java
String label = choose("A", "B");
Integer id = choose(7, 9);
~~~

Trong các tình huống đơn giản này, `T` có thể được suy ra tương ứng với `String` và `Integer`. Không cần cast, không cần viết `MyClass.<String>choose(...)`.

### 3.2. Khi nhiều nguồn cần kiểu cha chung

~~~java
Number number = choose(10, 2.5);     // Hợp lệ.
Object object = choose("text", 42);   // Hợp lệ.
~~~

- Với `Integer` và `Double`, có những supertype chung hữu ích cho phép trả về `Number`.
- Với `String` và `Integer`, `Object` là một supertype chung. Chúng còn có thể chia sẻ interface, nên LUB chính xác không nhất thiết chỉ là `Object`.

**Cần chú ý:** `choose("text", 42)` vẫn trả về **chính đối tượng được chọn**; type inference không chuyển `Integer` thành `String` hay biến hai giá trị thành một loại runtime mới.

## 4. Upper bounds từ khai báo `extends` giới hạn nghiệm

Một phương thức có thể yêu cầu type argument thuộc nhánh `Number`:

~~~java
static <T extends Number> T laterNumber(T a, T b) {
    return b;
}
~~~

Khi gọi:

~~~java
Number result = laterNumber(10, 2.5);
~~~

Compiler kết hợp:

~~~text
Integer <: α
Double  <: α
α       <: Number
~~~

Cần tìm một nghiệm thỏa cả ba. Đây là ví dụ có **lower bounds từ các đối số** và **upper bound từ khai báo type parameter**.

Khi chỉ có một đối số `String`, ràng buộc mâu thuẫn:

~~~java
static <T extends Number> T bounded(T value) {
    return value;
}

// KHÔNG biên dịch:
Number invalid = bounded("text");
~~~

Cốt lõi là `String <: α` và `α <: Number` **không thể đồng thời đúng**; `String` không phải subtype của `Number`.

### 4.1. Nhiều upper bounds với `&`

Java cho phép khai báo type parameter có nhiều bound, ví dụ:

~~~java
static <T extends Number & Comparable<T>> T maximum(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

- `T extends Number` cho phép gọi các phương thức của `Number`.
- `T extends Comparable<T>` bảo đảm hai giá trị cùng `T` có thể so sánh.
- Với `maximum(3, 9)`, `T = Integer` đáp ứng các điều kiện, kết quả là `Integer 9`.

**Đừng hiểu `<T extends Number & Comparable<T>>` là Java nhận mọi cặp số khác loại.** Ví dụ `Integer` và `Double` đều triển khai `Comparable` với **type argument riêng**, nên `maximum(3, 9.5)` không thỏa tự động hợp đồng “so sánh cùng `T`”. Muốn so sánh khác loại theo giá trị số, phải thiết kế một tiêu chí so sánh cụ thể và làm rõ chuyển đổi/độ chính xác.

### 4.2. Quy tắc với nhiều interface bounds

Trong khai báo type parameter, nếu có bound là class thì nó phải đứng đầu; các interface đứng sau `&`:

~~~java
<T extends Number & Comparable<T>>
~~~

Kiểu thực tế phải thỏa tất cả bound, không chỉ một bound bất kỳ. Nếu bộ ràng buộc mâu thuẫn, compiler báo lỗi thay vì tự bỏ bớt giới hạn để chương trình chạy.

## 5. LUB: kiểu cha chung “ít mất thông tin nhất” là gì?

**Least upper bound (LUB)** của một tập các reference types là một kiểu cha chung được tính theo thuật toán JLS §4.10.4 để không chọn một supertype rộng không cần thiết.

Ý tưởng đơn giản khi xét hai kiểu:

~~~text
      Object
        |
      Number
       /  \
  Integer  Double
~~~

`Number` là class cha chung gần nhất trong cây class của `Integer` và `Double`. Nếu chỉ nhìn cây class này, `Number` mang nhiều thông tin hơn `Object`. Vì vậy ta có thể xử lý hai giá trị như `Number`.

Tuy nhiên, **LUB trong JLS không chỉ là tìm một class cha gần nhất trong cây**:

- Một class có thể implements nhiều interface. Hai class khác nhau có thể chia sẻ nhiều interface quan trọng.
- Java có các *intersection types*, ví dụ một kiểu thỏa đồng thời `Number` và các interface chung.
- Với generic types, Java phải xét type arguments, erasure, wildcard và các quy tắc least containing parameterization.
- LUB là một phần trong quá trình resolution; nó không thay thế các upper bounds, equality constraints hay ngữ cảnh kiểu đích.

Vì thế, phát biểu có thể áp dụng là: **LUB giúp tìm kiểu chung phù hợp từ các lower bounds; compiler vẫn cần kiểm tra tất cả các ràng buộc khác.**

### 5.1. Khi có lower bounds, JLS dùng LUB thế nào?

Trong trường hợp đơn giản khi giải một inference variable với các **proper lower bounds** `L1, L2, ...`, JLS §18.4 mô tả ứng viên nghiệm là:

~~~text
α := lub(L1, L2, ...)
~~~

Ứng viên đó còn được đưa vào bộ ràng buộc để kiểm tra tính nhất quán. Nếu nó mâu thuẫn với upper bound hay quan hệ khác, inference có thể thất bại hoặc cần xử lý tiếp theo thuật toán chuẩn. Không thể cứ nhìn thấy LUB là bỏ qua tất cả các bound khác.

### 5.2. “Greatest lower bound” không phải LUB

Trong phần resolution của JLS, nếu không có proper lower bounds, một ứng viên có thể được hình thành từ **greatest lower bound (GLB)** của những proper upper bounds. Đây là khái niệm khác với LUB:

- `lub(Integer, Double)` tìm một **supertype chung** đủ cụ thể của hai kiểu.
- `glb(Upper1, Upper2)` xét sự kết hợp các yêu cầu kiểu **phải nằm dưới** nhiều upper bounds, thường liên hệ với intersection types.

Đừng nhầm “lower bound của inference variable” với “greatest lower bound của nhiều kiểu”. Hai cụm dùng chữ *lower* nhưng nói về các tầng khái niệm khác nhau.

## 6. Equality constraints và invariance của generic arguments

Không phải lúc nào compiler cũng có thể nâng type argument lên một kiểu cha chung. Các generic types như `List<Integer>` và `List<Number>` thông thường **invariant**:

~~~java
List<Integer> ints = List.of(1, 2);
// KHÔNG biên dịch:
List<Number> numbers = ints;
~~~

Nếu ngữ cảnh bắt buộc một generic argument chính xác, compiler có thể có **equality constraint**, ví dụ `α = Integer` thay vì chỉ `Integer <: α`.

Xem lời gọi:

~~~java
// KHÔNG biên dịch:
List<Integer> values = List.of(1, 2.5);
~~~

Trong `List.of(E, E)`, kiểu đích `List<Integer>` đòi type argument `E` tương thích với `Integer`, đồng thời các đối số yêu cầu `E` chấp nhận cả `Integer` và `Double`. Java báo các ràng buộc không tương thích (thường gồm `equality constraints: Integer` và `lower bounds: Double,Integer`). Không thể chỉ chọn `Number` vì `List<Number>` không phải `List<Integer>`.

Ngược lại:

~~~java
List<Number> numbers = List.of(1, 2.5); // Hợp lệ.
~~~

Ngữ cảnh `List<Number>` cho phép các giá trị `Integer` và `Double` cùng là phần tử của list có type argument `Number`. Phép gán trên **không tạo một List<Integer> rồi biến nó thành List<Number>**. Compiler sử dụng target type trong việc suy luận `E` cho lời gọi tạo list.

**Bài học:** Có một superclass chung chưa đủ để chứng minh hai **parameterized types cụ thể** có quan hệ subtype. Phải theo dõi cả invariance và các equality constraints phát sinh từ ngữ cảnh.

## 7. Kiểu đích bổ sung điều kiện cho biến suy luận

Với method trả `List<T>`, kiểu đích có thể tạo **equality constraint** trong ngữ cảnh poly invocation, bên cạnh lower/upper bounds của các đối số:

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
List<Number> numbers = singleton(7);
```

`Number` được đưa vào từ kiểu đích `List<Number>`, còn Integer từ đối số 7 phải được chấp nhận làm T. Compiler tìm nghiệm phù hợp cho cả hai; target không thay đổi kiểu của một `List<Integer>` đã tồn tại.

Nếu cần nêu chủ đích ngay ở lời gọi:

```java
Number value = InferenceBoundsDemo.<Number>first(1, 2.5);
```

Đây là ví dụ với method `first` của chương trình ở mục 9. Với `var values = List.of(1, 2.5)`, không có target `List<Number>` tường minh; thuật toán LUB có thể đưa ra kiểu kết hợp phức tạp hơn một class cha. Ở đây, **mô hình lower/equality/upper bounds** mới là nội dung chính; các quy tắc ngữ cảnh poly expression được đào sâu ở bài kế tiếp.

## 8. Wildcard `extends`/`super` trong phương thức nhiều tham số

PECS (*Producer Extends, Consumer Super*) thường được dùng cùng type inference, chẳng hạn:

~~~java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

Khi gọi:

~~~java
List<Integer> source = List.of(2, 4);
List<Number> destination = new ArrayList<>(List.of(1.5));
appendAll(source, destination);
~~~

Compiler cần tìm một `T` sao cho:

- `source` cung cấp các phần tử gán được cho `T` (`Integer` phù hợp với `T`).
- `destination` có thể nhận những giá trị `T` (`T` phải phù hợp với kiểu phần tử `Number` của destination).

Với trường hợp đơn giản này, có thể hình dung các điều kiện:

~~~text
Integer <: T
T       <: Number
~~~

Có một hoặc nhiều lựa chọn `T` phù hợp với hai ràng buộc; compiler đưa các quy tắc generic wildcard, capture và inference vào để xác nhận lời gọi. Không cần cast, và không cần hai list có cùng type argument. Đây là **quan hệ giữa nguồn và đích**, chứ không chỉ tìm một supertype chung tùy ý.

### 8.1. Khi hai kiểu không có quan hệ truyền an toàn

~~~java
List<String> strings = List.of("A", "B");
List<Integer> integers = new ArrayList<>();

// KHÔNG thể dùng appendAll(strings, integers) để đưa String vào List<Integer>.
~~~

Lời gọi sẽ không biên dịch: không tồn tại `T` đáp ứng đồng thời các ràng buộc truyền từ `String` sang một danh sách chỉ chấp nhận `Integer`, trừ khi bạn đổi hợp đồng/destination type. Tránh raw types và unchecked casts để “bắt” compiler chấp nhận chuyển đổi dữ liệu không an toàn.

### 8.2. Giới hạn từ callback và quan hệ nhiều biến

Trong API xử lý chuyển đổi, một type parameter có thể đóng vai trò đầu vào, một type parameter khác làm đầu ra:

~~~java
static <T, R> List<R> transform(
        List<? extends T> input,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> output = new ArrayList<>();
    for (T item : input) {
        output.add(mapper.apply(item));
    }
    return output;
}
~~~

Đây là **một phương thức minh họa** cần được đặt trong lớp có import `List`, `ArrayList`. Compiler phải suy luận các ràng buộc liên hệ `T`, `R`, nguồn và `mapper`. Đây là trường hợp một upper/lower bound đơn lẻ không thể kể hết cách inference hoạt động; thứ tự suy luận và phụ thuộc giữa inference variables cũng có vai trò.

## 9. Chương trình Java 17+ hoàn chỉnh đã được biên dịch và chạy

Tạo tệp **InferenceBoundsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class InferenceBoundsDemo {
    static <T> T first(T a, T b) {
        return a;
    }

    static <T extends Number> T laterNumber(T first, T second) {
        return second;
    }

    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    static <T extends Number & Comparable<T>> T maximum(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        String word = first("Java", "Generics");
        System.out.println("same type: " + word);

        Number common = first(10, 2.5);
        System.out.println("common: " + common);

        Number last = laterNumber(10, 2.5);
        System.out.println("bounded: " + last);

        List<Number> numbers = List.of(10, 2.5);
        System.out.println("target typed: " + numbers);

        List<Number> one = singleton(7);
        System.out.println("singleton: " + one);

        List<Integer> source = List.of(2, 4);
        List<Number> destination = new ArrayList<>(List.of(1.5));
        appendAll(source, destination);
        System.out.println("combined: " + destination);

        Integer max = maximum(3, 9);
        System.out.println("max: " + max);

        Number explicit = InferenceBoundsDemo.<Number>first(1, 2.5);
        System.out.println("explicit: " + explicit);
    }
}
~~~

Biên dịch và chạy với Java 17 hoặc mới hơn:

~~~bash
javac --release 17 -Xlint:all InferenceBoundsDemo.java
java InferenceBoundsDemo
~~~

**Stdout chính xác**:

~~~text
same type: Java
common: 10
bounded: 2.5
target typed: [10, 2.5]
singleton: [7]
combined: [1.5, 2, 4]
max: 9
explicit: 1
~~~

Đã thử thực tế bằng `javac --release 17 -Xlint:all` và chạy chương trình; ví dụ biên dịch thành công, không có unchecked warnings. Giải thích:

1. Hai `String` cho một lời gọi `first` với kết quả dùng như `String`.
2. `Integer` và `Double` cung cấp lower bounds để kết quả dùng được như `Number`.
3. `laterNumber` có thêm upper bound `Number`.
4. `List.of(...)` và `singleton(...)` chịu ràng buộc từ target type `List<Number>`.
5. `appendAll` cho phép chuyển `Integer` sang danh sách đích `Number`.
6. `maximum` buộc `T` thỏa đồng thời `Number` và `Comparable<T>`.
7. Explicit witness `<Number>` làm rõ type argument của lời gọi cuối.

## 10. Tệp cố ý sai để đọc thông báo `javac`

Tạo riêng **InvalidInference.java** như sau. **Tệp này được thiết kế để biên dịch thất bại**, không phải một phần chương trình chạy ở mục 9:

~~~java
import java.util.List;

class InvalidInference {
    static <T extends Number> T bounded(T value) { return value; }
    static <T> T choose(T a, T b) { return a; }

    static void broken() {
        Number no = bounded("text");
        Integer incompatible = choose(1, 2.5);
        List<Integer> ints = List.of(1, 2.5);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -Xdiags:verbose InvalidInference.java
~~~

**Kỳ vọng:** lệnh kết thúc với exit code khác 0 và ba lỗi. Những đoạn chẩn đoán tiêu biểu được xác minh bằng `javac`:

~~~text
inference variable T has incompatible bounds
  upper bounds: Number
  lower bounds: String
...
inferred type does not conform to upper bound(s)
...
inference variable E has incompatible bounds
  equality constraints: Integer
  lower bounds: Double,Integer
3 errors
~~~

Các dòng trên là **trích đoạn rút gọn**, không phải toàn bộ stderr; tên inference variable, intersection types, đường dẫn và vị trí dòng có thể khác giữa môi trường chạy.

Ba lỗi này minh họa ba cách thất bại:

- `bounded("text")` tạo lower bound `String` xung đột upper bound `Number`.
- `Integer incompatible = choose(1, 2.5)` yêu cầu kết quả có thể dùng như `Integer` nhưng các đối số khác loại không tương thích với yêu cầu đó. Compiler có thể hiển thị một intersection type trong lỗi.
- `List<Integer> ints = List.of(1, 2.5)` có target parameterization đòi `Integer`, nhưng danh sách đầu vào cũng chứa `Double`; equality và lower bounds xung đột.

Không nên làm mất các dấu hiệu lỗi bằng raw types, `@SuppressWarnings("unchecked")` hoặc cast không có cơ sở. Những lỗi này xuất phát từ **không tồn tại nghiệm kiểu phù hợp**, chứ không phải do thiếu một phép cast cú pháp.

## 11. Hướng dẫn đọc lỗi suy luận kiểu

Khi `javac` báo “`inference variable ... has incompatible bounds`”, hãy kiểm tra theo trình tự:

1. **Xác định biến suy luận:** xem method generic khai báo `<T>`, `<E>`, `<T,R>` hay bound nào.
2. **Tìm lower bounds:** lập danh sách các kiểu mà biến suy luận phải chấp nhận từ đối số (ví dụ `Integer`, `Double`, `String`).
3. **Tìm upper bounds:** đọc `extends`, callback constraints và target context có ràng buộc đầu ra.
4. **Kiểm tra equality/invariance:** liệu một `List<Integer>` đang bị yêu cầu nhận một generic type có type argument khác?
5. **Nhìn xem có supertype chung phù hợp không:** nếu có, kiểu cha chung đó có thỏa **tất cả** những điều kiện còn lại không? Chỉ có `Object` là cha chung không tự làm cho mọi chương trình hợp lệ.
6. **Xét target type và overload:** lời gọi đang đứng trong phép gán, `return`, tham số method khác hay được suy luận độc lập với `var`?
7. **Sửa contract ở đúng nơi:** đổi đầu ra sang `Number` khi nghiệp vụ thật sự cho phép nhiều loại số; dùng wildcard `extends`/`super` nếu source và destination có quan hệ biến thiên an toàn; dùng type witness khi cần thể hiện loại mong muốn.
8. **Biên dịch với diagnostics rõ:** dùng `javac -Xdiags:verbose`; không phải mọi lỗi “incompatible bounds” đều có cùng nguyên nhân.

Một dấu hiệu cần cảnh giác là ép `(List<Integer>)` vào collection đã chứa `Double`. Nó có thể dẫn tới heap pollution và `ClassCastException` sau này, không tạo ra một nghiệm suy luận đúng.

## 12. Lỗi hiểu biết thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Lower bound nghĩa là `α <: Lower`.” | Lower bound `L` của `α` nghĩa là `L <: α`. |
| “Upper bound nghĩa là `Upper <: α`.” | Upper bound `U` nghĩa là `α <: U`. |
| “Có cha chung là `Object` thì suy luận nào cũng hợp lệ.” | Các ràng buộc `extends`, equality, invariance và target typing vẫn phải thỏa. |
| “LUB của `Integer` và `Double` lúc nào cũng chỉ là `Number`.” | JLS có thể biểu diễn kiểu giao/interfaces, không chỉ một class cha. |
| “`<T extends Number>` tự động chuyển `String` thành số.” | Không. Nếu đầu vào không thỏa `Number`, compiler báo lỗi. |
| “Hai `List<T>` có thể luôn dùng chung `T` vì đều là List.” | Type arguments là invariant; phải có ràng buộc thật sự giữa chúng. |
| “`List<Integer>` là subtype của `List<Number>` vì Integer extends Number.” | Không. Cần wildcard thích hợp hoặc tạo collection mới đúng type argument. |
| “`var` luôn suy luận đúng kiểu cha mình hình dung.” | `var` dùng kiểu của initializer; kiểu đó có thể là kiểu giao/kiểu tham số hóa phức tạp. |
| “Thông báo upper/lower bounds là lỗi runtime.” | Đây là chẩn đoán **compile time** về tính nhất quán của kiểu. |
| “`@SuppressWarnings("unchecked")` sửa lỗi không có nghiệm inference.” | Không. Nó chỉ tác động tới một số cảnh báo unchecked, không hợp thức hóa kiểu sai. |

## 13. Câu hỏi tự kiểm tra

1. Với `<T extends Number> T f(T x)` và đối số `Integer`, hướng ràng buộc là gì? **`Integer <: α <: Number`**.
2. Tại sao `f("hello")` không hợp lệ? **Vì `String` không nằm dưới `Number` và không có nghiệm thỏa cả hai điều kiện.**
3. Lower bounds `Integer` và `Double` gợi ý tìm gì? **Một supertype chung phù hợp; JLS có thể tính LUB của các reference types.**
4. LUB có phải luôn một class đơn giản? **Không.** Có thể liên hệ với intersection types và parameterized types.
5. `List<Integer> ints = List.of(1, 2.5)` sai dù `Number` là cha chung, vì sao? **Target type tạo constraint buộc type argument phù hợp `Integer`, mâu thuẫn đối số `Double`.**
6. `List<Number> ns = List.of(1, 2.5)` có hợp lệ không? **Có.** Target type tương thích với cả hai loại số.
7. `<T> void append(List<? extends T>, List<? super T>)` có cần hai list có cùng type argument không? **Không.** Nó chỉ đòi quan hệ truyền `T` an toàn từ nguồn sang đích.
8. Tại sao explicit `<Number>` đôi khi hữu ích? **Nó cung cấp type argument chủ đích rõ ràng cho method, miễn đối số và bounds đều phù hợp.**

## 14. Tài liệu chuẩn

- [JLS Java SE 17 §18.1.3 — Bounds](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.1.3): định nghĩa upper, lower, equality, capture và `throws` bounds.
- [JLS Java SE 17 §18.4 — Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.4): cách dùng `lub` từ proper lower bounds và `glb` từ proper upper bounds khi giải inference variables.
- [JLS Java SE 17 §18.5 — Uses of Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.5): method applicability, invocation type inference và tác động của target type.
- [JLS Java SE 17 §4.10.4 — Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4): LUB của reference types có xét generic declarations, intersection type và supertypes.
- [JLS Java SE 17 §4.5.1 — Type Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard containment và bất biến của các parameterized types.
- [JLS Java SE 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): ngữ cảnh và quy tắc của lời gọi method, kể cả generic methods.
