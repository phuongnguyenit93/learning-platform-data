# Áp dụng `? super T` cho đầu ra nhận dữ liệu trong Java Generics

Khi một phương thức **đưa các giá trị kiểu `T` vào một đối tượng đích** (destination/consumer), tham số đích thường nên khai báo bằng **lower-bounded wildcard `? super T`**. Cách này cho phép phương thức ghi `T` vào collection có đối số kiểu chính xác là `T` **hoặc một kiểu cha của `T`**, đồng thời vẫn được Java kiểm tra an toàn kiểu khi biên dịch.

Ví dụ, một phương thức chuyên thêm `Integer` không nhất thiết phải yêu cầu `List<Integer>`: nó cũng có thể thêm `Integer` vào `List<Number>` và `List<Object>`. Chữ ký `List<? super Integer>` thể hiện chính xác nhu cầu đó.

Đây là phần **Consumer Super** trong nguyên tắc **PECS — Producer Extends, Consumer Super**. “Đầu ra nhận dữ liệu” trong bài này chỉ **tham số đích được phương thức ghi phần tử vào**, không bắt buộc là giá trị `return` của phương thức.

## 1. Thế nào là đầu ra nhận dữ liệu?

Một tham số là **consumer** trong một thao tác khi nó **nhận các đối tượng do phương thức cung cấp**, chẳng hạn:

- Danh sách đích được thêm các `Integer` mới.
- Collection đích nhận phần tử đọc từ collection nguồn.
- Hàng đợi nhận các công việc mang kiểu `T`.
- Hàm xử lý (ví dụ `Consumer<? super T>`) nhận giá trị `T` để thực hiện tác vụ.
- `Comparator<? super T>` nhận các phần tử `T` để so sánh, dù nó không lưu chúng.

Vai trò producer/consumer được xác định **theo hướng luân chuyển dữ liệu trong API**. Một `ArrayList<Number>` có thể là *consumer* khi nhận số từ nguồn, và trở thành *producer* khi một phương thức khác duyệt các số đã có.

Ví dụ phương thức chỉ ghi:

```java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Các lời gọi hợp lệ về mặt kiểu:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addDefaults(integers);
addDefaults(numbers);
addDefaults(objects);
```

`destination` chỉ cần khả năng tiếp nhận `Integer`. Không có lý do buộc người gọi xây dựng đúng một `List<Integer>` nếu danh sách đích rộng hơn vẫn lưu được `Integer` an toàn.

## 2. Vì sao một tham số consumer không nên bị cố định thành `List<Integer>`?

API chỉ cần gửi một `Integer` vào đích thì đích có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`. Java Generics bất biến nên `List<Number>` không gán trực tiếp cho `List<Integer>`; nếu dùng chữ ký quá hẹp, caller phải tạo list mới không cần thiết hoặc tìm cách cast.

~~~java
static void sendTen(List<? super Integer> destination) {
    destination.add(10);
}
~~~

Chữ ký này **mở rộng lựa chọn destination mà không nới lỏng kiểu phần tử được ghi**. Bản thân destination có thể đã chứa phần tử kiểu rộng hơn; method trên không cần biết hay đọc chúng. Đây là trường hợp consumer rõ ràng nhất trước khi xét callback, comparator và kết hợp nguồn/đích.

## 3. Chọn cận dưới theo giá trị mà đầu ra phải nhận

Đừng đọc `? super Integer` thành “cho phép gửi bất kỳ `Number` vào danh sách”. Một `List<? super Integer>` có thể chính là `List<Integer>`, nên lời gọi `destination.add(2.5)` không an toàn. Nếu cần gửi cả `Integer` lẫn `Double`, chọn `List<? super Number>` để bên nhận bảo đảm chứa được các `Number`.

~~~java
List<Number> numbers = new ArrayList<>();
List<? super Integer> integerOnly = numbers;
integerOnly.add(7);
// integerOnly.add(2.5); // Không biên dịch.

numbers.add(2.5);       // Được, nhờ kiểu tham chiếu List<Number>.
~~~

Hai tham chiếu dùng chung đối tượng nhưng **mỗi biến có quyền thao tác theo kiểu tĩnh của chính nó**. Chọn cận `T` theo loại dữ liệu method định ghi, không theo lớp runtime của một đối tượng list tình cờ được truyền vào.

## 4. Đầu ra có thể nhận `T`, nhưng không chắc sản xuất ra `T`

Giới hạn dưới của wildcard chỉ chứng minh **đích nhận được những giá trị `T`**. Nếu `List<? super Integer>` trỏ tới `List<Object>` chứa `String` cũ, `get(i)` không thể được compiler xem là `Integer` hay `Number`:

~~~java
List<Object> actual = new ArrayList<>();
actual.add("old");
List<? super Integer> destination = actual;
destination.add(42);

Object item = destination.get(0); // "old"
// Integer wrong = destination.get(0); // Lỗi biên dịch.
~~~

`set(i, 99)` được phép về kiểu nhưng cần index hợp lệ và list cho phép sửa; `add(null)` được compiler chấp nhận nhưng implementation có thể cấm null. Nếu cần kết quả đọc có kiểu mạnh, hãy dùng một tham số nguồn phù hợp hoặc xác minh **từng giá trị** bằng `instanceof`. `? super T` không phải một lời hứa về nội dung có sẵn hay mutability.

## 5. Vì sao `super` thiên về đầu ra nhận dữ liệu?

Một API nhận đích để thêm `T` cần biết **đích chấp nhận được `T`**. Nó không nhất thiết phải biết **tất cả phần tử hiện có của đích là `T`**.

Đó chính là hai chiều khác nhau:

- **Ghi:** cần bảo đảm `T` có thể đặt vào collection → `Collection<? super T>`.
- **Đọc:** cần bảo đảm phần tử lấy ra dùng được dưới dạng `T` → `Collection<? extends T>`.

Sự bất đối xứng này là lý do của quy tắc PECS:

> **Producer Extends, Consumer Super.**

PECS là hướng dẫn dựa trên cách tham số được sử dụng. Nó không có nghĩa bất kỳ đối tượng nào mang tên “output” đều phải dùng `super`, hoặc hễ gọi `add` là cần wildcard `super`. Nếu thuật toán cần **cả đọc và ghi với chính xác `T`**, `List<T>` có thể rõ ràng hơn.

Ví dụ:

```java
static void increment(List<Integer> values) {
    for (int i = 0; i < values.size(); i++) {
        values.set(i, values.get(i) + 1);
    }
}
```

Phương thức cần đọc ra `Integer` để cộng, rồi ghi `Integer` trở lại, vì vậy `List<Integer>` hợp lý. Nếu đổi thành `List<? super Integer>`, kết quả `get(i)` chỉ được bảo đảm là `Object` và phép cộng không thể áp dụng trực tiếp.

## 6. Ghép nguồn sản xuất và đầu ra nhận dữ liệu

Một pipeline thường đọc từ một iterable và ghi vào một collection khác. Chữ ký vừa đúng PECS vừa dùng abstraction tối thiểu:

~~~java
static <T> void transfer(
        Iterable<? extends T> source,
        Collection<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
~~~

`Iterable<? extends T>` **sản xuất** phần tử có thể đọc như `T`; `Collection<? super T>` **tiêu thụ** `T`. Do đó có thể chuyển `List<Integer>` sang `Collection<Number>` hoặc `Collection<Object>` mà không dùng unchecked cast.

Method này **append**, không ghi đè các vị trí đã có. Nếu `source` và `destination` là cùng một `ArrayList`, việc `add` trong lúc foreach có thể gây `ConcurrentModificationException`; muốn hỗ trợ self-copy, cần snapshot phù hợp trước khi mutate. Nếu `destination.add` ném exception, những phần tử trước đó có thể đã được thêm: PECS không làm thao tác copy trở thành atomic transaction.

## 7. Ví dụ thư viện chuẩn: `Collections.copy`

Java Collections Framework sử dụng cùng ý tưởng consumer cho đích. Chữ ký khái niệm của phương thức:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Trong đó:

- `src` cung cấp phần tử, nên dùng `? extends T`.
- `dest` nhận hoặc thay thế phần tử, nên dùng `? super T`.

Ví dụ độc lập nhỏ:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CopyExample {
    public static void main(String[] args) {
        List<Integer> source = List.of(4, 5);
        List<Number> target = new ArrayList<>(List.of(0, 0));

        Collections.copy(target, source);
        System.out.println(target);
    }
}
```

Lưu `CopyExample.java` và chạy:

```bash
javac CopyExample.java
java CopyExample
```

Stdout:

```text
[4, 5]
```

**Quan trọng:** `Collections.copy` **thay thế** phần tử tại các vị trí sẵn có của đích, không `append` vào cuối như `appendAll`. Danh sách đích phải có `size()` **ít nhất bằng** kích thước nguồn; nếu không, phương thức ném `IndexOutOfBoundsException`. Việc đích là danh sách có thể thay thế phần tử cũng cần được bảo đảm, nếu không thao tác có thể ném `UnsupportedOperationException`.

Ở ví dụ trên, `target` được tạo với hai phần tử `0`, đủ chỗ để thay thế hai vị trí bằng `4` và `5`. `new ArrayList<>(source)` là một cách khác khi thực sự muốn tạo danh sách mới, không phải ghi vào một đích có sẵn.

## 8. `? super T` không chỉ có trong collection

“Consumer” có thể là một hàm hoặc đối tượng **tiếp nhận giá trị `T`**, ngay cả khi nó không lưu phần tử.

### 8.1. `Consumer<? super T>`

Phương thức `Iterable.forEach` có chữ ký nhận một `Consumer<? super T>`. Nhờ vậy một `Consumer<Number>` có thể xử lý phần tử của `List<Integer>`:

```java
import java.util.List;
import java.util.function.Consumer;

public class ConsumerExample {
    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        Consumer<Number> printNumber =
                number -> System.out.println(number.intValue());

        integers.forEach(printNumber);
    }
}
```

Chạy:

```bash
javac ConsumerExample.java
java ConsumerExample
```

Stdout:

```text
1
2
3
```

`Consumer<Number>` biết nhận bất kỳ `Number` nào, vì thế có thể nhận các `Integer`. Trường hợp ngược lại, một `Consumer<Integer>` không thể được coi là consumer tổng quát của mọi `Number`, do nó không được đảm bảo xử lý `Double`.

### 8.2. `Comparator<? super T>`

`List.sort` nhận `Comparator<? super E>`, nơi `E` là kiểu phần tử của danh sách. Một `Comparator<Number>` đủ khả năng so sánh các `Integer` vì mỗi `Integer` cũng là `Number`.

```java
List<Integer> values = new ArrayList<>(List.of(10, 3, 20));
Comparator<Number> byValue =
        Comparator.comparingDouble(Number::doubleValue);
values.sort(byValue);
System.out.println(values); // [3, 10, 20]
```

Đây là **đoạn mã dùng trong ngữ cảnh đã import `java.util.List`, `java.util.ArrayList` và `java.util.Comparator`**. `Comparator` là consumer ở khía cạnh **nhận phần tử để so sánh**, không có nghĩa comparator phải ghi vào danh sách.

Điểm chung là **một API cần đưa giá trị `T` cho đối tượng nhận**; giới hạn dưới cho phép đối tượng nhận được thiết kế để xử lý cả kiểu cha của `T`.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình sau tổng hợp các tình huống chính: nhiều loại đích nhận `Integer`, nguồn–đích có quan hệ kiểu, đọc qua `? super Integer` và comparator tiêu thụ `Number`.

Lưu thành **`SuperConsumerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public class SuperConsumerDemo {
    static void seed(Collection<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> target) {
        for (T element : source) {
            target.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        seed(integers);
        seed(numbers);
        seed(objects);

        List<Integer> source = List.of(3, 5);
        appendAll(source, numbers);
        appendAll(source, objects);

        System.out.println("integers = " + integers);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);

        List<? super Integer> target = numbers;
        Object first = target.get(0);
        System.out.println("first = " + first);

        numbers.add(2.5);
        System.out.println("numbers after Double = " + numbers);

        List<Integer> sorted = new ArrayList<>(List.of(10, 3, 20));
        Comparator<Number> byValue =
                Comparator.comparingDouble(Number::doubleValue);
        sorted.sort(byValue);
        System.out.println("sorted = " + sorted);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SuperConsumerDemo.java
java SuperConsumerDemo
```

Stdout:

```text
integers = [10, 20]
numbers = [10, 20, 3, 5]
objects = [10, 20, 3, 5]
first = 10
numbers after Double = [10, 20, 3, 5, 2.5]
sorted = [3, 10, 20]
```

Giải thích kết quả:

1. Cùng phương thức `seed` thêm `Integer` vào ba loại collection đích, vì cả ba đều chấp nhận `Integer`.
2. `appendAll` chuyển giá trị từ `List<Integer>` sang `List<Number>` và `List<Object>` mà không cần ép kiểu.
3. Qua tham chiếu `target` kiểu `List<? super Integer>`, kết quả đọc bảo đảm an toàn dưới dạng `Object`.
4. Danh sách `numbers` vốn là `List<Number>`, nên qua tham chiếu `numbers` vẫn có thể thêm `2.5` sau khi phương thức consumer đã chạy.
5. `Comparator<Number>` so sánh được các phần tử `Integer` khi `sorted.sort(byValue)` được gọi.

Đoạn mã không có chuyển đổi một `List<Number>` thành `List<Integer>`; wildcard chỉ điều chỉnh **những quan hệ tham số được phép trong hệ kiểu**, không đổi kiểu phần tử của danh sách thực.

## 10. Chọn chữ ký thích hợp theo nhu cầu

| Nhu cầu của API | Chữ ký gợi ý | Đọc được như | Ghi được |
| --- | --- | --- | --- |
| Chỉ thêm `Integer` vào đích | `Collection<? super Integer>` | `Object` khi lấy phần tử | `Integer` |
| Đọc mọi loại số từ nguồn | `Collection<? extends Number>` | `Number` | Không bảo đảm giá trị không-null cụ thể |
| Đọc và thêm mọi `Number` vào danh sách đích đã xác định | `List<Number>` | `Number` | `Number` và các subtype |
| Đọc và ghi chính xác `Integer` | `List<Integer>` | `Integer` | `Integer` |
| Chuyển giá trị từ nguồn sang đích | `<T>` + `Iterable<? extends T>` và `Collection<? super T>` | `T` từ nguồn | `T` vào đích |
| Xử lý các phần tử `Integer` bằng callback nhận `Number` | `Consumer<? super Integer>` | Không áp dụng với callback này | Callback nhận `Integer` |

“Ghi được” trong bảng nghĩa là **hợp lệ về kiểu**, không bảo đảm một collection cụ thể mutable. Lựa chọn chữ ký phải theo hợp đồng phương thức, không phải chỉ theo tên biến.

Một số API chỉ cần gọi `destination.add(...)` nên có thể nhận `Collection<? super T>`. Nếu cần truy cập vị trí hoặc thay thế phần tử bằng `set(index, value)`, khi đó chọn `List<? super T>`.

## 11. Lỗi phổ biến

### 11.1. Giả sử `? super Integer` cho phép ghi mọi `Number`

`List<? super Integer>` chấp nhận **chắc chắn `Integer`**, không chắc chắn chấp nhận `Double`. Nếu đích thật là `List<Integer>`, thêm `Double` sẽ sai. Muốn thêm các `Number` tùy ý, dùng `List<? super Number>` (cho đích có kiểu `Number` hoặc kiểu cha), hoặc `List<Number>` khi biết rõ kiểu danh sách cần dùng.

### 11.2. Đọc `Integer` trực tiếp từ đích wildcard

```java
List<Object> objects = new ArrayList<>();
objects.add("other");
List<? super Integer> destination = objects;

// Integer value = destination.get(0); // LỖI BIÊN DỊCH.
Object value = destination.get(0);      // Hợp lệ.
```

Đây là ví dụ cho thấy đọc dưới dạng `Integer` sẽ không an toàn: phần tử hiện tại thật sự là `String`. Tham chiếu lower-bounded wildcard không hứa mọi phần tử của đích đều có kiểu `Integer`.

### 11.3. Tưởng `super` tạo ra collection có thể sửa đổi

```java
List<Integer> immutable = List.of(1, 2);
List<? super Integer> target = immutable;
// target.add(3); // Biên dịch được, nhưng nếu chạy sẽ ném
// UnsupportedOperationException vì List.of không hỗ trợ thêm.
```

Từ `super` chỉ suy ra **kiểm tra kiểu cho phần tử ghi**, không suy ra khả năng thay đổi cấu trúc. Nếu API có nhiệm vụ ghi, cần hợp đồng nói rõ collection đích phải hỗ trợ thao tác tương ứng.

### 11.4. Nhầm `super` với “kiểu cha của danh sách”

`List<? super Integer>` không phải `List<Number>` và không có nghĩa nó kế thừa từ `List<Integer>`. Đây là **một kiểu tham số hóa có wildcard với giới hạn dưới**, dùng để chấp nhận nhiều đối số kiểu phù hợp. Các phép gán và quyền đọc/ghi được compiler kiểm tra dựa trên giới hạn đó.

### 11.5. Dùng raw type hoặc unchecked cast để ép dữ liệu

Đừng viết `List raw = ...` rồi thêm đối tượng không có ràng buộc kiểu, hoặc ép `List<?>` sang `List<Integer>` chỉ để gọi `add`. Các lối tắt ấy có thể làm dữ liệu không phù hợp với tham số kiểu gốc và dẫn đến `ClassCastException` khi phần tử được đọc theo kiểu khai báo.

Hãy sử dụng `? super T` khi cần **thêm `T` vào đích rộng hơn** và `? extends T` khi cần **lấy `T` từ nguồn hẹp hơn**.

### 11.6. Quên kích thước hoặc khả năng ghi của đích

Một số thao tác dùng `add` để mở rộng đích; thao tác như `Collections.copy` lại dùng `set` để thay thế vị trí đã tồn tại. Hai loại cùng có thể tận dụng `? super T`, nhưng điều kiện runtime khác nhau. Hãy đọc hợp đồng API: collection có mutable không, đích có đủ kích thước không, có chấp nhận `null` không, và nguồn/đích có được trùng nhau không.

## 12. Tự kiểm tra kiến thức

Cho các biến có kiểu khai báo rõ ràng:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<Double> doubles = new ArrayList<>();

List<? super Integer> destination = numbers;
```

Đánh giá từng câu:

1. `destination.add(1)` — **Hợp lệ**. `1` được boxing thành `Integer`.
2. `destination.add(Double.valueOf(2.5))` — **Lỗi biên dịch**. Đích có thể là `List<Integer>`.
3. `Number n = destination.get(0)` — **Lỗi biên dịch**. Đọc qua wildcard chỉ bảo đảm `Object`.
4. `Object o = destination.get(0)` — **Hợp lệ về kiểu**; nếu danh sách rỗng, runtime ném `IndexOutOfBoundsException`.
5. `destination = integers` — **Hợp lệ**. `List<Integer>` có thể làm consumer của `Integer`.
6. `destination = objects` — **Hợp lệ**. `List<Object>` chấp nhận `Integer`.
7. `destination = doubles` — **Lỗi biên dịch**. `Double` không phải kiểu cha của `Integer`.
8. `List<? super Number> target = numbers` — **Hợp lệ**. `Number` thỏa giới hạn dưới.
9. `List<? super Number> target = integers` — **Lỗi biên dịch**. `Integer` không là kiểu cha của `Number`.
10. `appendAll(integers, objects)` — **Hợp lệ**, với chữ ký `<T> void appendAll(List<? extends T>, List<? super T>)` trong chương trình hoàn chỉnh phía trên.

Các câu liên quan `get(0)` chỉ đánh giá **kiểu của biểu thức**; muốn chạy thành công, danh sách phải có phần tử và không vi phạm hợp đồng runtime.

## Ghi nhớ

- **Consumer** là tham số **nhận giá trị kiểu `T`** từ phương thức; khi cần ghi `T` vào nhiều loại đích, dùng `? super T`.
- `List<? super Integer>` nhận được tham chiếu `List<Integer>`, `List<Number>` và `List<Object>`; không nhận `List<Double>`.
- Với `List<? super T>`, có thể ghi **`T` hoặc subtype của `T`** nhưng đọc ra an toàn chung chỉ là `Object`.
- **PECS:** dùng `? extends T` cho nguồn cung cấp, `? super T` cho đích tiêu thụ.
- Khi cần cả đọc và ghi với đúng một kiểu cụ thể, `List<T>` hoặc `List<Integer>` thường phù hợp hơn.
- Khả năng ghi được **về mặt generic** không chứng minh collection mutable. Những điều kiện runtime của `add`, `set`, `Collections.copy` vẫn phải được tuân thủ.
- Java Generics bất biến; lower-bounded wildcard cung cấp khả năng nhận đích rộng hơn **mà không cần ép kiểu không an toàn**.

Chọn `? super T` cho đúng vai trò nhận dữ liệu giúp API Java tái sử dụng tốt hơn, cho phép chuyển phần tử lên collection đích có kiểu cha và giữ tính đúng đắn của hợp đồng generic ngay từ thời điểm biên dịch.
