# Ràng buộc nhiều đầu vào cùng chia sẻ một kiểu trong Java Generics và PECS

Khi một phương thức Java nhận nhiều danh sách, tập hợp hoặc các giá trị generic, ta thường cần diễn đạt **mối quan hệ giữa các tham số**: phần tử từ nhiều nguồn phải được xử lý theo một kiểu chung, dữ liệu được chuyển sang đích phải an toàn, và kết quả trả về phải giữ được thông tin kiểu.

Một tham số kiểu phương thức, chẳng hạn `<T>`, cho phép đặt **một tên kiểu chung** dùng ở nhiều vị trí trong cùng chữ ký. Kết hợp với quy tắc **PECS** (*Producer Extends, Consumer Super*), ta có thể viết:

```java
static <T> void transferBoth(
        List<? extends T> first,
        List<? extends T> second,
        List<? super T> destination) {
    for (T value : first) {
        destination.add(value);
    }
    for (T value : second) {
        destination.add(value);
    }
}
```

Ở đây, `first` và `second` là **nguồn cung cấp** các phần tử tương thích với `T`; `destination` là **đích nhận** giá trị `T`. Cả ba tham số được kiểm tra thông qua **cùng một `T` của mỗi lần gọi**, nhờ đó compiler có thể xác minh luồng dữ liệu.

Điều quan trọng cần hiểu ngay: dùng chung `T` trong `List<? extends T>` **không buộc hai nguồn có cùng kiểu phần tử chính xác**. Ví dụ nguồn `List<Integer>` và `List<Double>` vẫn có thể cùng tham gia một lời gọi với `T = Number`. Nếu muốn yêu cầu cả hai danh sách có **chính xác cùng đối số kiểu**, chữ ký `List<T>` ở cả hai vị trí cho một hợp đồng khác.

## 1. Thế nào là “nhiều đầu vào cùng chia sẻ một kiểu”?

Xét phương thức xử lý hai danh sách:

```java
static <T> void inspect(List<T> left, List<T> right) {
    T firstLeft = left.get(0);
    T firstRight = right.get(0);
    System.out.println(firstLeft + " | " + firstRight);
}
```

Khai báo `<T>` **một lần** trước kiểu trả về của phương thức; các lần dùng `T` trong chữ ký và thân phương thức chỉ tới **cùng tham số kiểu**. Với các đối số là `List<String>` và `List<String>`, compiler có thể suy luận `T = String`. Với hai `List<Integer>`, compiler có thể suy luận `T = Integer`.

Trong chữ ký này, `List<T>` là bất biến (*invariant*), nên hai tham số danh sách được yêu cầu phù hợp với **cùng một đối số kiểu `T`**. Ví dụ:

```java
List<Integer> integers = List.of(1, 2);
List<Integer> moreIntegers = List.of(3, 4);
List<Number> numbers = List.of(5, 6);

inspect(integers, moreIntegers); // Hợp lệ: T là Integer.
// inspect(integers, numbers);   // Không biên dịch với chữ ký List<T>, List<T>.
```

Đoạn trên là minh họa nằm trong class có phương thức `inspect` và cần `import java.util.List;`.

Lỗi ở lời gọi thứ hai xuất hiện vì `List<Integer>` không phải `List<Number>`. Java không thể chỉ chọn `T = Number` để biến `List<Integer>` thành `List<Number>`; các generic như `List<E>` không tự hiệp biến theo đối số kiểu.

**Khái niệm “chung một `T`” có hai mức thiết kế khác nhau**:

1. `List<T>` ở nhiều vị trí: các tham số danh sách phải dùng cùng một kiểu đối số theo các quy tắc tương thích generic.
2. `List<? extends T>` ở nhiều vị trí: mỗi danh sách có thể dùng kiểu phần tử riêng, miễn đều là `T` hoặc kiểu con của `T`.

Cả hai đều dùng chung tên `T`, nhưng **lời hứa về các đối số đầu vào khác nhau**.

## 2. Tham số kiểu `<T>` và vai trò của suy luận kiểu

Trong một phương thức generic:

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

các vị trí `T` được ràng buộc bởi cùng một biến kiểu của phương thức. Tuy nhiên, đừng hiểu `T` là lời hứa rằng **hai đối tượng runtime phải có cùng class**. Lời gọi:

```java
Number value = chooseFirst(10, 2.5);
```

có thể hợp lệ vì compiler tìm được một kiểu chung tương thích với `Integer` và `Double`, đồng thời phù hợp với ngữ cảnh kết quả, chẳng hạn `Number`. Cả hai tham số `T first` và `T second` nhận giá trị có kiểu con của `T` thông qua chuyển đổi phương thức.

Khác biệt xuất hiện ở generic bất biến:

```java
static <T> void acceptLists(List<T> first, List<T> second) {
    // Hai tham số List<T> cùng đòi hỏi đối số kiểu T.
}
```

Dù `Integer` và `Double` cùng kế thừa `Number`, một `List<Integer>` không thể tự chuyển thành `List<Number>` để khớp `List<T>`. Khi cần cho phép các **nguồn khác kiểu nhưng có kiểu cha chung**, ta phải biểu diễn rõ ràng quan hệ đó bằng `? extends T`.

Không nên lạm dụng `<T>` chỉ để thay cho một kiểu cụ thể mà không có quan hệ nào cần duy trì. Giá trị của tham số kiểu chung là **kết nối nhiều vị trí** trong chữ ký và cho phép compiler kiểm tra chúng nhất quán.

## 3. Hai producer: `List<? extends T>` kết hợp `List<? extends T>`

Một phương thức muốn đọc hai nguồn với kiểu phần tử có thể khác nhau nên khai báo:

```java
static <T> List<T> combine(
        List<? extends T> first,
        List<? extends T> second) {
    List<T> result = new ArrayList<>();
    result.addAll(first);
    result.addAll(second);
    return result;
}
```

Hai đầu vào là *producer*: chúng cung cấp dữ liệu mà ta có thể đọc dưới kiểu `T`. Mỗi wildcard có thể đại diện cho một kiểu con khác nhau của `T`; không phải cùng một wildcard capture và không phải hai danh sách có cùng kiểu phần tử chính xác.

Ví dụ `List<Integer>` và `List<Double>` đều có thể được đọc dưới kiểu `Number`. Nếu biến nhận kết quả có kiểu `List<Number>`, compiler có thể chọn `T = Number`.

### Ví dụ Java 17 chạy được: kết hợp hai nguồn

Lưu thành `SharedProducerDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SharedProducerDemo {
    static <T> List<T> combine(
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

        List<Number> allNumbers = combine(integers, doubles);
        System.out.println(allNumbers);

        List<String> allWords = combine(
                List.of("Java"),
                List.of("Generics"));
        System.out.println(allWords);

        // List<Integer> wrong = combine(integers, doubles);
        // Không biên dịch: Double không thể là Integer.
    }
}
```

Biên dịch và chạy:

```bash
javac SharedProducerDemo.java
java SharedProducerDemo
```

Đầu ra:

```text
[1, 2, 2.5, 3.5]
[Java, Generics]
```

Phương thức `combine` tạo ra một danh sách mới nên việc gọi `addAll` trên `result` được hỗ trợ vì `ArrayList` có thể thay đổi. Phần tử lấy từ mỗi nguồn được phép thêm vào `List<T>` vì compiler đã chứng minh kiểu phần tử của các nguồn là `T` hoặc kiểu con của `T`.

Khi cần bảo toàn kiểu `Integer` cho toàn bộ kết quả, nguồn `List<Double>` sẽ không phù hợp. Không có phép ép kiểu an toàn nào biến giá trị `Double` thành `Integer` chỉ nhờ generic.

## 4. Hai producer và một consumer: liên kết bằng chung `T`

Quy tắc PECS áp dụng rõ nhất khi dữ liệu luân chuyển **từ nhiều nguồn vào một đích**:

```java
static <T> void transferBoth(
        List<? extends T> first,
        List<? extends T> second,
        List<? super T> destination) {
    for (T item : first) {
        destination.add(item);
    }
    for (T item : second) {
        destination.add(item);
    }
}
```

Ý nghĩa của từng vị trí:

| Vị trí | Chữ ký | Hợp đồng kiểu |
| --- | --- | --- |
| Nguồn thứ nhất | `List<? extends T>` | Đọc phần tử dưới kiểu `T` |
| Nguồn thứ hai | `List<? extends T>` | Đọc phần tử dưới cùng kiểu chung `T` |
| Đích | `List<? super T>` | Có thể thêm các đối tượng kiểu `T` |
| Khai báo phương thức | `<T>` | Liên kết tất cả điều kiện kiểu trong một lần gọi |

Compiler phải tìm một cách gán `T` sao cho các nguồn phù hợp với `? extends T`, còn đích phù hợp với `? super T`. Nếu không tồn tại kiểu thỏa tất cả, lời gọi bị từ chối trước khi chạy.

### Ví dụ Java 17: chuyển nhiều nguồn vào một đích

Lưu thành `MultiSourcePecsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class MultiSourcePecsDemo {
    static <T> void transferBoth(
            List<? extends T> first,
            List<? extends T> second,
            List<? super T> destination) {
        for (T item : first) {
            destination.add(item);
        }
        for (T item : second) {
            destination.add(item);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(2.5, 3.5);
        List<Number> numbers = new ArrayList<>();

        transferBoth(integers, doubles, numbers);
        System.out.println(numbers);

        List<Object> objects = new ArrayList<>();
        transferBoth(List.of("A", "B"), List.of(10, 20), objects);
        System.out.println(objects);

        List<Integer> integerDestination = new ArrayList<>();
        transferBoth(integers, List.of(3, 4), integerDestination);
        System.out.println(integerDestination);

        // transferBoth(integers, doubles, integerDestination);
        // Không biên dịch: đích List<Integer> không thể nhận Double.
    }
}
```

```bash
javac MultiSourcePecsDemo.java
java MultiSourcePecsDemo
```

Đầu ra:

```text
[1, 2, 2.5, 3.5]
[A, B, 10, 20]
[1, 2, 3, 4]
```

Phân tích:

1. Với `List<Integer>`, `List<Double>` và `List<Number>`, có thể chọn `T = Number`: hai nguồn đọc được như `Number` và đích nhận được `Number`.
2. Với nguồn `List<String>`, `List<Integer>` và đích `List<Object>`, có thể chọn kiểu chung như `Object`, đủ để truyền cả hai loại phần tử.
3. Với hai nguồn số nguyên và đích `List<Integer>`, có thể chọn `T = Integer`.
4. Với nguồn có `Double` nhưng đích `List<Integer>`, không có `T` an toàn thỏa cả yêu cầu nhận `Double` của nguồn và giới hạn nhận `Integer` của đích.

Ví dụ minh họa **ràng buộc kiểu qua nhiều tham số**. Nó không ép Java chuyển đổi đối tượng `Double` thành `Integer` hay `String` thành `Object` mới; các thao tác chỉ chuyển cùng tham chiếu đối tượng qua interface danh sách.

## 5. “Chia sẻ một `T`” không đồng nghĩa các nguồn cùng kiểu chính xác

Đây là chỗ dễ nhầm nhất.

So sánh hai chữ ký:

```java
static <T> void exactArguments(List<T> left, List<T> right) {
    // Hai List dùng cùng đối số kiểu T.
}

static <T> void commonSupertype(
        List<? extends T> left,
        List<? extends T> right) {
    // Mỗi List có thể dùng kiểu con khác nhau của T.
}
```

Với:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);

// exactArguments(ints, doubles); // Không biên dịch.
commonSupertype(ints, doubles);   // Có thể suy luận T chung.
```

Lưu ý: các đoạn ở mục này chỉ minh họa cú pháp và điều kiện biên dịch; muốn chạy độc lập, đặt chúng vào class, thêm `import java.util.List;` và phương thức `main`.

**Tại sao `List<T>` chặt hơn?** Tham số kiểu `T` nằm bên trong `List<T>` bất biến. Khi một đối số là `List<Integer>`, nó tạo điều kiện đẳng thức đối số kiểu phù hợp với `Integer`; đối số `List<Double>` tạo điều kiện khác không khớp.

**Tại sao `List<? extends T>` mềm hơn?** Tham số nguồn chỉ cần có đối số kiểu thuộc `T` hoặc kiểu con của `T`. `Integer` và `Double` có kiểu cha chung `Number`, nên điều kiện có thể được thỏa đồng thời.

Cũng đừng đồng nhất `<T> void accept(T a, T b)` với `<T> void accept(List<T> a, List<T> b)`. Ở cách đầu, mỗi giá trị `Integer` hay `Double` có thể tự chuyển sang một kiểu cha chung khi truyền tham số; ở cách thứ hai, hai container bất biến không được chuyển đổi đối số kiểu như vậy.

## 6. Cận trên của `T` giới hạn miền kiểu chung

Nếu mục tiêu chỉ xử lý các số, ta có thể thêm cận:

```java
static <T extends Number> double sumBoth(
        List<? extends T> first,
        List<? extends T> second) {
    double sum = 0;
    for (Number value : first) {
        sum += value.doubleValue();
    }
    for (Number value : second) {
        sum += value.doubleValue();
    }
    return sum;
}
```

Compiler cần tìm một `T` là `Number` hoặc kiểu con của `Number`, đồng thời là kiểu cha chung phù hợp với cả hai nguồn. Hai nguồn `Integer` và `Double` có thể dùng chung `T = Number`. Nhưng nếu một nguồn là `List<String>` thì không có cách suy luận hợp lệ thỏa `T extends Number`.

Lưu thành `BoundedInputsDemo.java`:

```java
import java.util.List;

public class BoundedInputsDemo {
    static <T extends Number> double sumBoth(
            List<? extends T> first,
            List<? extends T> second) {
        double result = 0;
        for (Number number : first) {
            result += number.doubleValue();
        }
        for (Number number : second) {
            result += number.doubleValue();
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(sumBoth(
                List.of(1, 2),
                List.of(0.5, 1.5)));

        // sumBoth(List.of(1), List.of("hello"));
        // Không biên dịch: String không phải Number.
    }
}
```

```bash
javac BoundedInputsDemo.java
java BoundedInputsDemo
```

Đầu ra:

```text
5.0
```

Cận `T extends Number` giúp code trong thân phương thức dùng được API của `Number`. Tuy nhiên, cận kiểu không ngăn giá trị `null` xuất hiện trong những nguồn cho phép `null`. Đoạn `sumBoth` giả định các phần tử được cung cấp là số khác `null`; nếu không, `number.doubleValue()` có thể gây `NullPointerException`. API thực tế nên nêu rõ hoặc kiểm tra giả định dữ liệu.

## 7. Kết quả trả về cũng có thể chia sẻ `T` với nhiều đầu vào

Ràng buộc kiểu không chỉ áp dụng cho tham số đầu vào. Kiểu trả về `T` hoặc `List<T>` giúp bảo toàn mối quan hệ qua ranh giới lời gọi:

```java
static <T> List<T> combine(
        List<? extends T> first,
        List<? extends T> second) {
    List<T> result = new ArrayList<>();
    result.addAll(first);
    result.addAll(second);
    return result;
}
```

Nhờ kiểu trả về `List<T>`, ngữ cảnh gán cũng có thể tham gia suy luận:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);

List<Number> combined = combine(ints, doubles); // Hợp lệ.

// List<Integer> wrong = combine(ints, doubles);
// Không biên dịch: yêu cầu đầu ra Integer không dung nạp Double.
```

Nếu đổi chữ ký sang `List<?> combine(List<?> a, List<?> b)`, phương thức vẫn có thể chứa và trả lại các phần tử, nhưng caller chỉ đọc được kết quả dưới dạng `Object` và đánh mất thông tin kiểu chung mà `<T>` có thể duy trì.

Đây là tiêu chí thiết kế quan trọng: **khi có quan hệ kiểu giữa nhiều tham số và kết quả, dùng tên `T` chung để mô tả quan hệ ấy**. Wildcard độc lập `?` thường phù hợp khi caller và phương thức không cần duy trì mối liên hệ đó.

## 8. Nhiều wildcard `?` không tự liên kết với nhau

Xét phương thức:

```java
static void inspectUnknown(List<?> first, List<?> second) {
    Object a = first.get(0);
    Object b = second.get(0);
    System.out.println(a + ", " + b);
}
```

Mỗi `?` biểu thị một đối số kiểu chưa biết **riêng**. Không thể suy ra rằng phần tử của `first` có cùng kiểu với phần tử của `second`.

Tương tự, chữ ký:

```java
static void acceptTwo(
        List<? extends Number> first,
        List<? extends Number> second) {
    // Cả hai nguồn đều đọc được như Number.
}
```

bảo đảm cả hai danh sách chứa số khi đọc qua kiểu tĩnh, nhưng không khẳng định hai danh sách có cùng kiểu phần tử chính xác. `List<Integer>` và `List<Double>` đều hợp lệ.

Với một phương thức generic:

```java
static <T> void acceptLinked(
        List<? extends T> first,
        List<? extends T> second) {
    // Có một T dùng chung, mỗi wildcard có thể capture kiểu con khác.
}
```

cũng không thể thực hiện `first.add(second.get(0))`, vì `first` có kiểu phần tử capture không xác định và có thể là `List<Integer>` trong khi `second` là `List<Double>`. **Kiểu chung `T` chỉ bảo đảm các phần tử có thể được đọc như `T`**, chưa đủ cho phép ghi một phần tử của nguồn này trực tiếp vào nguồn kia.

Nếu cần chuyển phần tử, phải truyền vào một **consumer phù hợp**, hoặc nhận các danh sách chính xác `List<T>` khi thực sự yêu cầu cùng kiểu phần tử và các thao tác ghi phù hợp.

## 9. Tại sao không dùng `List<Object>` hoặc ép kiểu để đơn giản hóa?

Một cách viết kém linh hoạt là:

```java
static void transferOnlyObjects(
        List<Object> source1,
        List<Object> source2,
        List<Object> destination) {
    destination.addAll(source1);
    destination.addAll(source2);
}
```

Cách này không nhận trực tiếp `List<String>` hay `List<Integer>` vì `List<String>` không phải `List<Object>`. Người gọi có thể bị buộc tạo danh sách mới hoặc dùng cast không an toàn.

Nếu chữ ký thật sự chỉ cần **đọc các nguồn và ghi vào đích kiểu cha chung**, `<T>` + PECS diễn đạt ý định chính xác hơn:

```java
static <T> void transferBoth(
        List<? extends T> first,
        List<? extends T> second,
        List<? super T> destination) {
    for (T value : first) destination.add(value);
    for (T value : second) destination.add(value);
}
```

Compiler tự kiểm tra kiểu. Tránh raw type hoặc `(List)` để ép một `List<Integer>` thành `List<Number>`: những cách đó có thể làm hỏng an toàn kiểu và gây `ClassCastException` ở nơi đọc về sau.

Tuy vậy, **không phải mọi phương thức đều cần generic**. Nếu nghiệp vụ thật sự yêu cầu mọi đầu vào đã là `List<Object>` và không chấp nhận các loại danh sách tham số hóa khác, việc khai báo kiểu cụ thể có thể là phù hợp. Quyết định đến từ **hợp đồng dữ liệu mong muốn**, không phải mong muốn dùng nhiều cú pháp generic nhất.

## 10. Liên hệ với API `Collections.copy`

Thư viện chuẩn Java có phương thức với ý tưởng PECS quen thuộc:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Đây là chữ ký khái niệm của `java.util.Collections.copy`. `src` là producer, `dest` là consumer, cùng chia sẻ `T`; do đó có thể sao chép từ `List<Integer>` vào `List<Number>`.

Chú ý: `Collections.copy` **ghi đè các phần tử hiện có** ở đích và yêu cầu danh sách đích đủ dài; nó **không phải** một phương thức `addAll` tự tăng kích thước đích.

Trong bài toán có **hai nguồn**, chúng ta tổng quát hóa mô hình này bằng cách gắn cả hai nguồn vào một `T`:

```java
static <T> void appendAll(
        List<? extends T> sourceA,
        List<? extends T> sourceB,
        List<? super T> destination) {
    destination.addAll(sourceA);
    destination.addAll(sourceB);
}
```

`appendAll` yêu cầu đích hỗ trợ thêm phần tử; compiler chỉ kiểm tra quan hệ kiểu, không bảo đảm collection đích sửa được. Ví dụ `List.of(...)` có thể thỏa tham số về kiểu nhưng vẫn ném `UnsupportedOperationException` khi `addAll` thực hiện thay đổi.

Nếu dữ liệu từ hai nguồn không có kiểu chung đáp ứng khả năng của đích, compiler từ chối lời gọi thay vì để lỗi kiểu xuất hiện sau khi ghi.

## 11. Trường hợp API cần ràng buộc cùng loại phần tử chính xác

Giả sử hai danh sách là hai phiên bản của **cùng một loại dữ liệu**, và phương thức cần hoán đổi các phần tử giữa chúng. Khi ấy ta có thể viết:

```java
static <T> void exchangeFirst(List<T> first, List<T> second) {
    T temporary = first.get(0);
    first.set(0, second.get(0));
    second.set(0, temporary);
}
```

Ở đây `List<T>` ở cả hai vị trí **cố ý yêu cầu cùng đối số kiểu**. Một `List<Integer>` và một `List<Number>` không được tự xem là cặp cùng kiểu phần tử để gọi trực tiếp phương thức này.

Ví dụ Java 17 đầy đủ, lưu thành `SameTypeSwapDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SameTypeSwapDemo {
    static <T> void exchangeFirst(List<T> first, List<T> second) {
        T previous = first.get(0);
        first.set(0, second.get(0));
        second.set(0, previous);
    }

    public static void main(String[] args) {
        List<String> first = new ArrayList<>(List.of("left", "keep"));
        List<String> second = new ArrayList<>(List.of("right", "stay"));

        exchangeFirst(first, second);
        System.out.println(first);
        System.out.println(second);

        List<Integer> ints = new ArrayList<>(List.of(1));
        List<Number> numbers = new ArrayList<>(List.of(2));
        // exchangeFirst(ints, numbers); // Không biên dịch.
    }
}
```

```bash
javac SameTypeSwapDemo.java
java SameTypeSwapDemo
```

Đầu ra:

```text
[right, keep]
[left, stay]
```

`exchangeFirst` yêu cầu cả hai danh sách không rỗng và cho phép `set`. Các giả định này được đáp ứng bởi ví dụ `ArrayList`, nhưng không phải do generics tự bảo đảm. Danh sách không sửa đổi hoặc rỗng có thể gây exception khi chạy. Đây là giới hạn về API collection, tách biệt với kiểm tra quan hệ kiểu.

Đừng thêm `? extends T` vào mọi tham số chỉ vì PECS: khi hàm phải **đọc và ghi lại** đúng kiểu phần tử vào cả hai danh sách, `List<T>` thường diễn đạt ràng buộc tốt hơn.

## 12. Lỗi phổ biến và cách sửa

### Lỗi 1: dùng `List<T>` nhưng muốn nhận hai producer có kiểu con khác nhau

```java
static <T> void consumeBoth(List<T> a, List<T> b) {
    // ...
}
```

Lời gọi với `List<Integer>` và `List<Double>` sẽ không phù hợp vì danh sách generic bất biến.

**Cách sửa:** khi phương thức chỉ đọc từ hai danh sách, cân nhắc `List<? extends T>` cho cả hai, với `<T>` dùng chung.

### Lỗi 2: dùng hai wildcard `?` rồi giả định chúng là cùng kiểu

```java
static void wrongAssumption(List<?> a, List<?> b) {
    Object value = b.get(0);
    // a.add(value); // Không biên dịch.
}
```

Không có quan hệ nào buộc kiểu phần tử của `a` và `b` giống nhau. Đổi sang `List<T>` nếu cần cùng đối số kiểu để chuyển phần tử, hoặc chuyển phần tử qua một consumer riêng `List<? super T>` nếu chỉ cần một kiểu cha chung.

### Lỗi 3: nhầm `? extends T` với lời hứa hai nguồn cùng kiểu chính xác

```java
static <T> void accept(List<? extends T> left,
                       List<? extends T> right) {
    // T chung không có nghĩa hai wildcard capture giống nhau.
}
```

Có thể truyền `List<Integer>` và `List<Double>`, nên không được tự động ghi phần tử từ một nguồn vào nguồn kia.

### Lỗi 4: chọn đích quá hẹp cho các nguồn

```java
List<Integer> ints = List.of(1);
List<Double> doubles = List.of(2.5);
List<Integer> destination = new ArrayList<>();

// transferBoth(ints, doubles, destination); // Không biên dịch.
```

**Cách sửa:** nếu đích phải chứa cả hai loại số, dùng `List<Number>` hoặc kiểu cha chung phù hợp làm kiểu phần tử của đích.

### Lỗi 5: dùng `List<Object>` thay cho wildcard phù hợp

`List<Object>` không nhận trực tiếp `List<String>` hay `List<Integer>`. Nếu phương thức chỉ quan sát dữ liệu, dùng `List<?>`; nếu cần giữ quan hệ qua nhiều nguồn/đích, dùng một tham số kiểu `<T>` cùng cận wildcard.

### Lỗi 6: nghĩ một `T` sẽ được suy ra từ đúng một đối số

Compiler xét **toàn bộ điều kiện của lời gọi**, bao gồm các nguồn, đích, cận `T extends ...` và đôi khi cả kiểu kết quả được kỳ vọng. Nếu một đối số buộc `T` không tương thích với đối số khác, lời gọi sẽ bị từ chối. Không chọn `T` riêng rẽ cho từng vị trí rồi coi chúng là cùng kiểu.

### Lỗi 7: nhầm an toàn kiểu với khả năng sửa đổi collection

`List<? super T>` cho phép compiler chấp nhận thao tác thêm `T`, nhưng collection thực tế có thể không hỗ trợ `add` hoặc có quy tắc về `null`. Bảo đảm kiểu của PECS và hợp đồng runtime của collection là các vấn đề khác nhau.

## 13. Các câu hỏi tự kiểm tra

**Câu 1.** Với hai danh sách `List<Integer>` và `List<Double>`, có gọi được phương thức sau không?

```java
static <T> void read(List<? extends T> a,
                     List<? extends T> b) { }
```

**Có.** Compiler có thể chọn kiểu cha chung thích hợp như `Number`. Hai wildcard capture không cần bằng nhau.

**Câu 2.** Hai danh sách ấy có gọi được phương thức `static <T> void read(List<T> a, List<T> b)` không?

**Không**, vì `List<Integer>` và `List<Double>` là các tham số hóa bất biến khác nhau.

**Câu 3.** Nếu hai nguồn là `List<Integer>` và `List<Double>`, đích `List<Number>` có phù hợp với chữ ký `<T> void transferBoth(List<? extends T>, List<? extends T>, List<? super T>)` không?

**Có.** Có thể chọn `T = Number` và thêm tất cả phần tử số vào đích.

**Câu 4.** Thay đích thành `List<Integer>` thì sao?

**Không hợp lệ** vì nguồn `List<Double>` chứa kiểu phần tử không thể ghi an toàn vào `List<Integer>`.

**Câu 5.** Một phương thức cần hoán đổi phần tử qua lại giữa hai danh sách thì nên dùng hai `List<? extends T>`?

**Không nhất thiết; thường nên dùng hai `List<T>`** vì cần đọc và ghi các phần tử cùng kiểu chính xác. `? extends T` chủ yếu thích hợp khi tham số là producer.

**Câu 6.** Tại sao `<T>` xuất hiện một lần trong chữ ký nhưng được dùng ở nhiều chỗ?

Vì một tham số kiểu phải được khai báo một lần và có phạm vi sử dụng trong chữ ký/thân phương thức. Các chỗ dùng cùng `T` cho compiler khả năng kiểm tra một quan hệ nhất quán giữa nguồn, đích và kết quả.

## 14. Hướng dẫn chọn chữ ký

Hãy bắt đầu từ **hướng dữ liệu và quan hệ kiểu mong muốn**:

1. Nếu nhiều tham số phải là danh sách có **cùng đối số kiểu chính xác** và có thể đọc/ghi qua lại, dùng `<T> ... (List<T> a, List<T> b)`.
2. Nếu nhiều nguồn có thể chứa **những kiểu con khác nhau của một kiểu chung**, dùng `<T> ... (List<? extends T> a, List<? extends T> b)`.
3. Nếu dữ liệu từ những nguồn ấy cần được **thêm vào một đích**, dùng `List<? super T>` cho đích để nối quan hệ PECS.
4. Nếu miền dữ liệu phải thuộc một họ nhất định, bổ sung cận cho `T`, ví dụ `<T extends Number>`.
5. Nếu kiểu kết quả cần phản ánh đúng quan hệ với các nguồn, dùng `T` hoặc `List<T>` trong kiểu trả về.
6. Nếu không cần quan hệ giữa các phần tử hoặc giữa các tham số, `List<?>` có thể đủ và dễ đọc hơn một generic method không cần thiết.

**Ghi nhớ:** `<T>` tạo tên cho **một biến kiểu chung**; `? extends T` cho phép mỗi nguồn là producer của `T` hoặc kiểu con; `? super T` cho phép đích nhận `T`. Thiết kế đúng phải phân biệt rõ “cùng `T` để liên kết luồng dữ liệu” với “các danh sách có cùng đối số kiểu chính xác”.