# Suy luận kiểu với nhiều đối số có các kiểu khác nhau trong Java Generics

**Suy luận kiểu (type inference)** là quá trình trình biên dịch Java xác định các đối số kiểu generic khi chương trình không ghi chúng tường minh. Khi một lời gọi phương thức có **nhiều đối số khác kiểu**, compiler không đơn giản chọn kiểu của đối số đầu tiên: nó thu thập ràng buộc từ tất cả các đối số, các cận `extends`, cấu trúc generic và cả ngữ cảnh mong đợi của biểu thức, rồi tìm một cách gán tham số kiểu hợp lệ.

Ví dụ:

```java
static <T> T first(T a, T b) {
    return a;
}

Number result = first(10, 2.5);
```

`10` được boxing thành `Integer`, còn `2.5` thành `Double`. Hai kiểu này đều kế thừa `Number`, vì vậy compiler có thể suy luận một kiểu chung tương thích với cả hai và với ngữ cảnh `Number result`. Tuy nhiên, việc hai kiểu có chung kiểu cha **không có nghĩa** có thể truyền một `List<Integer>` và một `List<Double>` cho bất kỳ phương thức `<T>` nào nhận hai `List<T>`.

Bài này giải thích cách suy luận hoạt động, sự khác nhau giữa kiểu của giá trị và đối số kiểu của container, ảnh hưởng của kiểu kết quả, wildcard, cận kiểu và cách thiết kế chữ ký để nhiều đối số khác kiểu vẫn an toàn.

## 1. Suy luận bắt đầu từ chữ ký generic và các đối số

Một phương thức generic khai báo tham số kiểu trước kiểu trả về:

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

Trong lời gọi `chooseFirst("a", "b")`, cả hai đối số đều là `String`, nên compiler có thể dùng `T = String`. Với `chooseFirst(10, 20)`, boxing tạo ra hai `Integer` và `T` có thể là `Integer`.

Với `chooseFirst(10, 2.5)`, hai kiểu đầu vào là `Integer` và `Double`. Lời gọi vẫn có thể hợp lệ vì compiler tìm kiểu chung sao cho:

```text
Integer  <: T
Double   <: T
```

Ký hiệu `A <: B` nghĩa là `A` là subtype của `B`. Trong ví dụ, `Number` là một lựa chọn kiểu cha chung phù hợp.

**Không nên ghi nhớ rằng Java luôn chọn chính xác `Number` hay `Object` cho mọi cặp kiểu.** Với nhiều kiểu tham chiếu, kiểu chung nhỏ nhất (*least upper bound*, LUB) có thể bao gồm những interface và kiểu giao (*intersection type*) phức tạp. Ngữ cảnh gán hoặc cận của phương thức còn có thể làm kết quả suy luận khác nhau. Điều cần biết là compiler sẽ kiểm tra toàn bộ ràng buộc theo quy tắc của ngôn ngữ, thay vì chọn kiểu bằng cách nhìn một đối số riêng lẻ.

## 2. Ví dụ Java 17: hai đối số khác kiểu vẫn gọi được cùng một `<T>`

Lưu tệp `MixedArgumentsDemo.java`:

```java
public class MixedArgumentsDemo {
    static <T> T chooseFirst(T first, T second) {
        return first;
    }

    static <T> String describe(T first, T second) {
        return first.getClass().getSimpleName()
                + " + "
                + second.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Number number = chooseFirst(10, 2.5);
        Object object = chooseFirst("Java", 17);

        System.out.println(number);
        System.out.println(object);
        System.out.println(describe(10, 2.5));
        System.out.println(describe("Java", 17));
    }
}
```

Biên dịch/chạy bằng Java 17 trở lên:

```bash
javac MixedArgumentsDemo.java
java MixedArgumentsDemo
```

Đầu ra:

```text
10
Java
Integer + Double
String + Integer
```

Giải thích:

- `Number number = chooseFirst(10, 2.5)` hợp lệ: hai đối số khác class vẫn chuyển được tới một kiểu chung đáp ứng ngữ cảnh `Number`.
- `Object object = chooseFirst("Java", 17)` hợp lệ vì cả `String` và `Integer` đều là kiểu tham chiếu và có thể xem như `Object`.
- `describe` dùng các phương thức của `Object` là `getClass()`, nên không yêu cầu phải biết cụ thể `T` là `Integer`, `Double` hay `String`.
- Chương trình in kiểu runtime của từng **đối tượng**, không in chính xác kiểu `T` compiler suy luận. Generic không tạo ra một class runtime riêng cho `T`.

Hai đối số khác kiểu không có nghĩa mọi phép toán dành cho kiểu con đều hợp lệ. Bên trong `describe`, compiler không thể tùy tiện gọi `first.intValue()` hoặc `first.length()` vì `T` không bị ràng buộc lần lượt bởi `Number` hay `String`.

## 3. Từ nhiều đối số đến kiểu chung: quan hệ “cùng dùng được như `T`”

Với chữ ký `<T> void handle(T a, T b)`, compiler cần tìm một `T` mà **cả hai giá trị** có thể truyền vào. Giá trị của class con có thể tự chuyển lên class cha hoặc interface phù hợp tại vị trí tham số.

Ví dụ:

```java
static <T> void printPair(T a, T b) {
    System.out.println(a + " | " + b);
}
```

Các lời gọi hợp lệ về kiểu:

```java
printPair(1, 2);           // Hai Integer sau boxing.
printPair(1, 2.5);         // Integer và Double.
printPair("hello", 2026);  // String và Integer.
```

Việc dùng cùng `T` **không bắt buộc các đối số có đúng cùng class runtime**. Một biến kiểu phương thức có thể đại diện cho kiểu cha chung của nhiều kiểu con.

Đối chiếu hai vấn đề khác nhau:

| Trường hợp | Compiler kiểm tra điều gì? |
| --- | --- |
| `<T> void f(T a, T b)` | Mỗi giá trị có thể chuyển đến một `T` chung |
| `<T> void f(List<T> a, List<T> b)` | Hai danh sách có đối số kiểu phù hợp với **cùng `T`** theo tính bất biến |
| `<T> void f(List<? extends T> a, List<? extends T> b)` | Kiểu phần tử của từng danh sách là kiểu con của `T`, có thể khác nhau |
| `<T> void f(List<? extends T> a, List<? super T> b)` | Nguồn đọc được dưới `T` và đích nhận được `T` |

Đây là điểm mấu chốt của suy luận với nhiều đối số: **ràng buộc phụ thuộc vị trí của `T` trong chữ ký**, không chỉ phụ thuộc class của các giá trị đầu vào.

## 4. Generic bất biến: vì sao `List<Integer>` và `List<Double>` không khớp hai `List<T>`?

Xét:

```java
static <T> void inspectSameLists(List<T> first, List<T> second) {
    System.out.println(first.size() + second.size());
}
```

Với hai danh sách cùng đối số kiểu:

```java
List<Integer> first = List.of(1, 2);
List<Integer> second = List.of(3);
inspectSameLists(first, second); // Hợp lệ: T = Integer.
```

Nhưng trường hợp sau không biên dịch:

```java
List<Integer> integers = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);

// inspectSameLists(integers, doubles); // LỖI BIÊN DỊCH.
```

Vì `List<T>` là bất biến, compiler không thể tùy ý dùng `T = Number` để xem `List<Integer>` thành `List<Number>`, hoặc xem `List<Double>` thành `List<Number>`.

Thông báo lỗi có thể nêu **inference variable `T` has incompatible equality constraints** hoặc các yêu cầu kiểu không thống nhất. Ý nghĩa là hai tham số `List<T>` đòi cùng một đối số kiểu, trong khi caller cung cấp hai tham số hóa khác nhau.

Không sửa bằng:

```java
// List<Number> numbers = (List<Number>) (List<?>) integers;
```

Cách ép kiểu vòng qua wildcard có thể gây cảnh báo `unchecked` và phá an toàn kiểu. Một danh sách `Integer` có thể bị thêm `Double` qua tham chiếu bị ép sai, khiến lỗi xuất hiện muộn khi đọc.

**Cách thiết kế đúng** phụ thuộc mục tiêu: nếu chỉ muốn đọc hai nguồn cùng nhóm kiểu, dùng wildcard `? extends T` ở từng nguồn; nếu cần trao đổi dữ liệu qua lại giữa hai danh sách **cùng kiểu phần tử**, giữ `List<T>` để compiler từ chối nguồn không tương thích.

## 5. Wildcard `? extends T` cho phép suy luận từ nhiều nguồn khác kiểu

Khi thuật toán chỉ **đọc** phần tử từ hai danh sách, thay vì yêu cầu cả hai chính xác `List<T>`, ta có thể viết:

```java
static <T> List<T> merge(
        List<? extends T> first,
        List<? extends T> second) {
    List<T> result = new ArrayList<>();
    result.addAll(first);
    result.addAll(second);
    return result;
}
```

Compiler cần tìm một `T` sao cho:

```text
ElementType(first)  <: T
ElementType(second) <: T
```

Mỗi nguồn có wildcard **riêng**, nên một nguồn có thể là `List<Integer>` và nguồn kia là `List<Double>`. Chúng cùng cung cấp dữ liệu đọc được như `Number`.

### Chương trình hoàn chỉnh

Lưu thành `MergeDifferentTypes.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class MergeDifferentTypes {
    static <T> List<T> merge(
            List<? extends T> first,
            List<? extends T> second) {
        List<T> result = new ArrayList<>();
        result.addAll(first);
        result.addAll(second);
        return result;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(2.5, 3.5);

        List<Number> numbers = merge(integers, doubles);
        System.out.println(numbers);

        List<Object> objects = merge(
                List.of("Java"),
                List.of(17));
        System.out.println(objects);

        // List<Integer> invalid = merge(integers, doubles);
        // Lỗi: kết quả Integer không nhận được Double.
    }
}
```

```bash
javac MergeDifferentTypes.java
java MergeDifferentTypes
```

Đầu ra:

```text
[1, 2, 2.5, 3.5]
[Java, 17]
```

Ngữ cảnh `List<Number> numbers = ...` giúp ràng buộc kiểu kết quả là `List<Number>`; hai danh sách nguồn có phần tử là kiểu con của `Number`. Tương tự, `List<Object>` chứa được cả `String` và `Integer`.

**Giới hạn của phép đọc từ `? extends T`:** không được tùy ý thêm một đối tượng `T` vào `first` hoặc `second`. Ví dụ `first.add((T) someValue)` là cách làm không an toàn; chúng có thể thực sự là `List<Integer>` hoặc `List<Double>` riêng biệt. Ở ví dụ, chỉ `result` là `List<T>` mới được phép nhận các phần tử của cả hai nguồn.

## 6. Kết hợp producer và consumer để suy luận qua nhiều đối số

PECS (*Producer Extends, Consumer Super*) giúp diễn đạt **chiều di chuyển dữ liệu**. Một phương thức nhận hai nguồn khác kiểu và một đích chung có thể viết:

```java
static <T> void appendAll(
        List<? extends T> left,
        List<? extends T> right,
        List<? super T> destination) {
    destination.addAll(left);
    destination.addAll(right);
}
```

Ràng buộc đối với compiler:

- Kiểu phần tử của `left` phải phù hợp với `T` hoặc kiểu con của `T`.
- Kiểu phần tử của `right` phải phù hợp với `T` hoặc kiểu con của `T`.
- Đích phải có khả năng nhận giá trị `T` theo hệ kiểu.

Vì thế:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);
List<Number> output = new ArrayList<>();

appendAll(ints, doubles, output); // Hợp lệ.

// List<Integer> onlyInts = new ArrayList<>();
// appendAll(ints, doubles, onlyInts); // Không biên dịch.
```

Compiler có thể chọn `T = Number` cho trường hợp đầu. Trong trường hợp đích `List<Integer>`, không tồn tại `T` vừa có thể nhận nguồn `Double` vừa có thể thêm an toàn vào đích chỉ nhận `Integer`.

### Ví dụ Java 17 chạy được

Lưu thành `MultipleInputPecs.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class MultipleInputPecs {
    static <T> void appendAll(
            List<? extends T> first,
            List<? extends T> second,
            List<? super T> destination) {
        destination.addAll(first);
        destination.addAll(second);
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        appendAll(List.of(1, 2), List.of(3.5, 4.5), numbers);
        System.out.println(numbers);

        List<Object> objects = new ArrayList<>();
        appendAll(List.of("A"), List.of(7), objects);
        System.out.println(objects);

        List<Integer> integers = new ArrayList<>();
        appendAll(List.of(1), List.of(2), integers);
        System.out.println(integers);
    }
}
```

```bash
javac MultipleInputPecs.java
java MultipleInputPecs
```

Đầu ra:

```text
[1, 2, 3.5, 4.5]
[A, 7]
[1, 2]
```

Đích dùng `ArrayList` nên cho phép `addAll`. Wildcard `? super T` chỉ bảo đảm **an toàn kiểu của phần tử được thêm**, không tự bảo đảm đích có thể sửa đổi: một collection không sửa đổi có thể ném `UnsupportedOperationException`.

## 7. Kiểu đích là một ràng buộc khác của lời gọi nhiều đối số

Khi lời gọi generic trả `List<T>`, ngữ cảnh gán cũng có thể ràng buộc T, ngoài các điều kiện từ đối số:

```java
static <T> List<T> one(T value) {
    return new ArrayList<>(List.of(value));
}

List<Integer> a = one(10);
List<Number> b = one(10);
List<Object> c = one(10);
// List<String> wrong = one(10); // Mâu thuẫn Integer và String.
```

Cùng một Integer có thể đi vào những lần gọi có T khác nhau, nhưng một biến `List<Integer>` đã được khai báo không tự chuyển thành `List<Number>`. Khi có **nhiều đối số khác loại**, kiểu đích phải được kiểm tra cùng ràng buộc từ tất cả đầu vào; không thể dùng nó để buộc một Double thành Integer.

## 8. `var` giữ kiểu được suy luận tại chính initializer

```java
var inferred = one(10);        // List<Integer>.
List<Number> wider = one(10);   // List<Number>.
```

`var` không truyền kiểu đích Number xuống initializer và không tự nới `inferred` thành `List<Number>` khi có một lệnh dùng nó về sau. Nếu kết quả cần chứa nhiều subtype Number, hãy biểu đạt contract ngay trong khai báo hoặc type witness hợp lệ. Trong bài này, điểm chính vẫn là **tập hợp nhiều lower/equality constraints từ các đối số**, không phải cú pháp `var`: đọc kiểu của `List<T>`, `List<? extends T>` và `List<? super T>` trước khi lựa chọn cách sửa.

## 9. Boxing, primitive và sự pha trộn kiểu số

Tham số kiểu generic chỉ nhận **kiểu tham chiếu**, không nhận primitive như `int` hoặc `double`. Vì thế:

```java
static <T> T first(T a, T b) {
    return a;
}

Number n = first(10, 2.5);
```

các biểu thức số primitive được **boxing** thành `Integer` và `Double` khi tham gia generic. Compiler sau đó xét ràng buộc kiểu tham chiếu.

Điều này khác với việc áp dụng phép toán cộng primitive:

```java
double sum = 10 + 2.5; // Chuyển đổi số primitive, kết quả 12.5.
```

Generic không tự áp dụng `Integer + Double` cho mọi `T`. Nếu cần tính tổng của nhiều kiểu số, hãy thêm cận cho tham số kiểu:

```java
static <T extends Number> double sum(T first, T second) {
    return first.doubleValue() + second.doubleValue();
}
```

Khi ấy `sum(10, 2.5)` có thể biên dịch vì cả `Integer` và `Double` thuộc họ `Number`, và compiler biết có thể gọi `doubleValue()` trên `T`.

Một ví dụ hoàn chỉnh:

```java
public class BoundedInferenceDemo {
    static <T extends Number> double sum(T a, T b) {
        return a.doubleValue() + b.doubleValue();
    }

    public static void main(String[] args) {
        System.out.println(sum(10, 2.5));
        System.out.println(sum(1L, 3));

        // sum("10", 2.5); // Không biên dịch: String không extends Number.
    }
}
```

Lưu thành `BoundedInferenceDemo.java`:

```bash
javac BoundedInferenceDemo.java
java BoundedInferenceDemo
```

Đầu ra:

```text
12.5
4.0
```

Cận `T extends Number` không buộc hai đối số có cùng subclass; nó chỉ buộc kiểu chung được suy luận phải nằm trong họ `Number`. Đồng thời nó loại những lời gọi chứa đối số không phù hợp như `String`.

**Giới hạn số học:** `Number.doubleValue()` có thể mất độ chính xác với kiểu số lớn hoặc khi tính toán tài chính. Ví dụ tập trung minh họa suy luận kiểu, không thay thế các quy tắc về số học chính xác hay `BigDecimal` trong ứng dụng thật.

## 10. Nhiều cận có thể khiến suy luận không có nghiệm

Với:

```java
static <T extends Number> T choose(T first, T second) {
    return first;
}
```

Lời gọi:

```java
Number n = choose(10, 2.5); // Hợp lệ.
```

có thể suy luận `T` phù hợp với cận `Number`. Nhưng:

```java
// String s = choose("text", 2.5); // Không biên dịch.
```

vì `String` không phải subtype của `Number`. Compiler không thể bỏ qua một đối số để tìm một kiểu phù hợp cho các đối số còn lại.

Tương tự, yêu cầu kiểu trả về quá hẹp có thể khiến hệ ràng buộc vô nghiệm:

```java
// Integer impossible = choose(10, 2.5); // Không biên dịch.
```

Một `Double` không thể tự chuyển thành `Integer` chỉ nhờ tham số kiểu generic; suy luận kiểu không làm chuyển đổi số theo ý muốn.

Khi gặp lỗi “incompatible bounds” hoặc “inference variable has incompatible bounds”, hãy phân tích toàn bộ yêu cầu:

1. Đối số thực tế cung cấp kiểu nào sau boxing nếu cần?
2. Tham số kiểu có cận `extends` hoặc các cận giao nào?
3. `T` xuất hiện ở vị trí giá trị đơn, `List<T>`, `? extends T` hay `? super T`?
4. Ngữ cảnh sử dụng kết quả có đòi một kiểu cụ thể không?
5. Có tồn tại một `T` thỏa tất cả các điều kiện cùng lúc không?

Phản hồi compiler phụ thuộc chữ ký cụ thể; đừng giả định mọi cặp đối số khác kiểu đều sẽ suy luận về `Object` thành công.

## 11. Hai wildcard giống nhau không có nghĩa hai đối số có cùng kiểu phần tử

Xét:

```java
static void printTwo(
        List<? extends Number> first,
        List<? extends Number> second) {
    Number a = first.get(0);
    Number b = second.get(0);
    System.out.println(a + " " + b);
}
```

Một lời gọi với `List<Integer>` và `List<Double>` được chấp nhận, vì mỗi danh sách đều có phần tử có thể xem như `Number`. Nhưng wildcard thứ nhất và wildcard thứ hai có thể được compiler **capture thành hai kiểu khác nhau**.

Vì vậy đoạn này không hợp lệ:

```java
static void wrongCopy(
        List<? extends Number> first,
        List<? extends Number> second) {
    // second.add(first.get(0)); // Không biên dịch.
}
```

`first` có thể là `List<Integer>`, `second` là `List<Double>`. Việc chúng có cùng cận trên `Number` không làm kiểu capture của chúng đồng nhất.

Muốn chép giá trị từ nguồn sang đích, đặt ràng buộc cho nơi nhận:

```java
static <T> void copyValues(
        List<? extends T> source,
        List<? super T> destination) {
    destination.addAll(source);
}
```

Hoặc, nếu cần **đúng cùng đối số kiểu** và phải ghi qua lại giữa hai danh sách, dùng `List<T>` cho cả hai tham số. Điều quyết định là mối quan hệ kiểu mà API muốn biểu diễn.

## 12. Phân biệt kiểu chung khi gán giá trị với quan hệ kiểu của container

Hai ví dụ sau phản ánh hai lớp kiểm tra khác nhau:

**Các giá trị đơn:**

```java
static <T> void accept(T a, T b) { }

accept(1, 2.5); // Hợp lệ: compiler tìm kiểu chung.
```

**Các container bất biến:**

```java
static <T> void acceptLists(List<T> a, List<T> b) { }

List<Integer> ints = List.of(1);
List<Double> doubles = List.of(2.5);

// acceptLists(ints, doubles); // Không biên dịch.
```

Không thể lập luận “`Integer extends Number` và `Double extends Number`, vậy cả hai `List` tự trở thành `List<Number>`”. Java generic không hiệp biến theo đối số kiểu.

Tuy nhiên:

```java
static <T> void acceptSources(
        List<? extends T> a,
        List<? extends T> b) { }

acceptSources(ints, doubles); // Hợp lệ.
```

Vì lời hứa giờ đây chỉ yêu cầu hai nguồn cung cấp giá trị mà thuật toán có thể xem như `T`. Compiler có thể chọn một kiểu chung để thỏa cả hai ràng buộc, mà không giả vờ hai danh sách có cùng đối số kiểu.

Các đoạn trong mục này minh họa cấu trúc chữ ký; cần đặt trong một class, có `import java.util.List;` và một `main` nếu muốn biên dịch/chạy độc lập.

## 13. Khi nào cần khai báo kiểu tường minh tại lời gọi?

Java hỗ trợ cung cấp đối số kiểu cho **generic method** trước tên phương thức, ví dụ:

```java
List<Number> numbers = MergeDifferentTypes.<Number>merge(
        List.of(1, 2),
        List.of(2.5, 3.5));
```

Đây là cú pháp minh họa khi phương thức `merge` là phương thức static trong class `MergeDifferentTypes` đã định nghĩa ở mục 5. `<Number>` yêu cầu compiler dùng `T = Number` trong lời gọi đó.

Trong phần lớn trường hợp, compiler tự suy luận đủ tốt và ta chỉ cần:

```java
List<Number> numbers = MergeDifferentTypes.merge(
        List.of(1, 2),
        List.of(2.5, 3.5));
```

Khai báo kiểu tường minh hữu ích khi muốn chỉ rõ ý định API hoặc cần giải quyết tình huống ngữ cảnh suy luận không diễn đạt được mong muốn. Nó **không** cho phép bỏ qua lỗi an toàn kiểu:

```java
// List<Integer> wrong = MergeDifferentTypes.<Integer>merge(
//         List.of(1), List.of(2.5));
// Không biên dịch: Double không thỏa ? extends Integer.
```

Cần phân biệt đối số kiểu tường minh với **cast**: `<Number>` đưa ràng buộc cho compiler kiểm tra từ đầu; nó không biến một đối tượng `Double` thành `Integer`, không bỏ kiểm tra an toàn generic và không thể cứu một tập ràng buộc vô nghiệm.

## 14. Những lỗi thường gặp khi suy luận nhiều kiểu

### Lỗi 1: nghĩ compiler chỉ nhìn đối số đầu tiên

```java
static <T> T first(T a, T b) {
    return a;
}

Number value = first(10, 2.5);
```

Compiler xét cả hai đối số và ngữ cảnh kết quả. Nó không “khóa” `T` thành `Integer` ngay khi thấy `10` rồi bỏ qua `Double`.

### Lỗi 2: nghĩ chung superclass là đủ để truyền hai `List<T>`

`List<Integer>` và `List<Double>` không tự động phù hợp với hai `List<T>`. Nếu phương thức chỉ đọc, hãy biểu diễn các tham số như `List<? extends T>`.

### Lỗi 3: dùng `List<Object>` cho mọi nguồn khác kiểu

```java
static void readObjects(List<Object> source) { }
```

Chữ ký trên không nhận trực tiếp `List<String>` hay `List<Integer>`. Nếu chỉ cần đọc các phần tử dưới dạng `Object`, `List<?>` thích hợp hơn; nếu cần giữ kiểu chung từ nhiều nguồn, dùng generic method với wildcard phù hợp.

### Lỗi 4: lạm dụng `var` rồi cho rằng kiểu động

`var` là suy luận **kiểu tĩnh cho biến cục bộ**. Sau khi compiler chọn kiểu, các phép gán/thao tác tiếp theo phải tuân thủ kiểu ấy. `var` không giúp “tự mở rộng” một `List<Integer>` khi muốn thêm `Double` sau đó.

### Lỗi 5: bỏ qua kiểu đích trong ràng buộc PECS

Hai nguồn `Integer` và `Double` cần một kiểu chung, nhưng nơi nhận cũng phải an toàn. Nếu đích chỉ là `List<Integer>` thì không thể đưa `Double` vào. Hãy kiểm tra đồng thời producer và consumer.

### Lỗi 6: coi suy luận kiểu là chuyển đổi giá trị số

`T` phù hợp với `Number` không có nghĩa Java tự chuyển `Double` thành `Integer`. Boxing, chuyển đổi primitive và chuyển kiểu tham chiếu có quy tắc riêng; generic inference không thay thế các phép biến đổi dữ liệu có chủ đích.

### Lỗi 7: ép generic để “sửa” lỗi suy luận

Cast raw/unchecked có thể xóa cảnh báo tại điểm gọi nhưng tạo lỗi dữ liệu về sau. Thay bằng chữ ký `<T>`, `? extends T`, `? super T` hoặc thiết kế một bước chuyển đổi dữ liệu thực sự khi cần.

### Lỗi 8: giả định suy luận bảo đảm collection thay đổi được

Compiler cho phép `destination.addAll(source)` theo kiểu không có nghĩa runtime sẽ hỗ trợ `addAll`. `List.of(...)` không sửa đổi; một collection có chính sách `null` hoặc đặc tính khác cũng có thể từ chối phần tử.

## 15. Bộ câu hỏi tự kiểm tra

**Câu 1.** Vì sao `chooseFirst(10, 2.5)` có thể hợp lệ với `static <T> T chooseFirst(T a, T b)`?

Vì hai đối số có thể được xem như các đối tượng thuộc một kiểu tham chiếu chung, và compiler có thể chọn `T` thỏa các ràng buộc đầu vào cùng ngữ cảnh sử dụng kết quả.

**Câu 2.** Có truyền `List<Integer>` và `List<Double>` cho `static <T> void f(List<T> a, List<T> b)` không?

**Không**, vì `List<T>` bất biến và hai danh sách được tham số hóa bởi các kiểu khác nhau.

**Câu 3.** Nếu đổi chữ ký thành `static <T> void f(List<? extends T> a, List<? extends T> b)` thì sao?

**Có**, vì mỗi nguồn có thể dùng một kiểu phần tử riêng là subtype của `T`, chẳng hạn cùng đọc dưới `Number`.

**Câu 4.** Hai nguồn `List<Integer>` và `List<Double>` có chuyển vào `List<Number>` theo `<T> void appendAll(List<? extends T>, List<? extends T>, List<? super T>)` không?

**Có.** `T = Number` đáp ứng điều kiện hai producer và consumer.

**Câu 5.** Nếu đích là `List<Integer>` thì sao?

**Không**, vì đích đó không nhận được mọi `Double` từ nguồn thứ hai.

**Câu 6.** Vì sao `List<Number> numbers = one(10)` có thể biên dịch dù `10` là `Integer`?

Vì ngữ cảnh kiểu trả về `List<Number>` cùng đối số `Integer` có thể dẫn compiler chọn `T = Number`.

**Câu 7.** Với `<T extends Number> double sum(T a, T b)`, `sum(10, 2.5)` và `sum("10", 2.5)` khác nhau ra sao?

Lời gọi thứ nhất phù hợp vì `Integer` và `Double` đều là `Number`. Lời gọi thứ hai bị từ chối vì `String` không thỏa cận `T extends Number`.

## 16. Quy trình chọn chữ ký khi có nhiều kiểu đầu vào

Khi xây dựng hoặc sửa một generic method, hãy đi theo thứ tự:

1. **Liệt kê kiểu thực tế** có thể đến từ từng đối số sau các phép chuyển đổi Java cho phép, chẳng hạn boxing.
2. **Xác định mục đích của từng tham số:** chỉ đọc, chỉ ghi, hay cần đọc và ghi chính xác cùng kiểu.
3. **Đặt `<T>` chung** nếu nhiều vị trí cần quan hệ kiểu nhất quán hoặc kết quả cần giữ loại phần tử.
4. **Dùng `? extends T` cho nguồn** nếu nguồn có thể chứa các subtype khác nhau của `T`.
5. **Dùng `? super T` cho đích** khi cần truyền các phần tử `T` vào một nơi nhận tương thích.
6. **Dùng `List<T>`** khi các danh sách thật sự phải chia sẻ cùng đối số kiểu và cần tương tác hai chiều.
7. **Thêm cận `<T extends Base>`** nếu thuật toán cần phương thức hoặc khả năng của `Base`.
8. **Xét kiểu kết quả mong đợi**; với `var`, nhớ rằng ngữ cảnh gán tường minh không còn.
9. **Kiểm tra mọi ràng buộc cùng lúc**, không chỉ tìm class cha chung của hai giá trị.

**Ghi nhớ:** suy luận generic cho nhiều đối số là việc tìm một nghiệm cho các ràng buộc kiểu của **toàn bộ lời gọi**. Hai giá trị `Integer` và `Double` có thể cùng dùng một `T` như `Number`, nhưng hai danh sách `List<Integer>` và `List<Double>` không tự trở thành hai `List<Number>`. Wildcard và PECS là cách diễn đạt chính xác quan hệ cần thiết để compiler vừa linh hoạt vừa giữ an toàn kiểu.