# Wildcard giới hạn dưới khi ghi dữ liệu và quy tắc PECS

Một phương thức muốn thêm các số nguyên vào danh sách không nhất thiết phải yêu cầu đúng `List<Integer>`. Một `List<Number>` cũng nhận được `Integer`, và một `List<Object>` cũng vậy. Nếu chữ ký chỉ nhận `List<Integer>`, nó loại bỏ những nơi nhận hoàn toàn an toàn đó.

Wildcard giới hạn dưới, viết bằng `? super T`, giải quyết vấn đề này: chấp nhận một nơi có thể **tiếp nhận giá trị kiểu T** mà vẫn giữ kiểm tra kiểu của Java.

Bài này tập trung vào chiều ghi dữ liệu và cách phối hợp với chiều đọc trong quy tắc PECS. Ví dụ sử dụng Java 17 trở lên.

## 1. Vấn đề cần giải quyết: nhận đúng loại nơi ghi

Giả sử cần thêm các mã mẫu kiểu `Integer`:

```java
static void addSampleIds(List<Integer> target) {
    target.add(10);
    target.add(20);
}
```

Phương thức nhận được `List<Integer>`, nhưng không nhận một biến `List<Number>` hoặc `List<Object>`. Generic là bất biến: `List<Integer>` không trở thành kiểu con của `List<Number>` chỉ vì `Integer` là kiểu con của `Number`.

Trong trường hợp này, phương thức không cần biết loại phần tử chính xác của đích. Nó chỉ cần bảo đảm đích chấp nhận `Integer`.

Chữ ký phù hợp hơn:

```java
static void addSampleIds(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

Đây là các phương thức minh họa cần đặt trong một lớp có import `java.util.List`.

Nhờ giới hạn dưới, có thể gọi cùng phương thức với các nơi nhận khác nhau:

```java
List<Integer> ids = new ArrayList<>();
List<Number> measurements = new ArrayList<>();
List<Object> values = new ArrayList<>();

addSampleIds(ids);
addSampleIds(measurements);
addSampleIds(values);
```

`ArrayList` cũng cần được import. Kiểu phần tử của các danh sách đích đều cho phép nhận `Integer`. [Oracle: wildcard giới hạn dưới](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

## 2. Đọc chính xác ý nghĩa ? super Integer

`List<? super Integer>` không phải “danh sách chỉ chứa lớp cha của Integer”.

Nó biểu thị một danh sách có **đối số kiểu cụ thể chưa biết**, nhưng đối số ấy là `Integer` hoặc một kiểu cha phù hợp của `Integer`.

Có thể hình dung kiểu chưa biết là `S` với quan hệ:

```text
Integer là kiểu con của S.
```

Khi đưa một `Integer` vào nơi nhận `S`, phép ghi an toàn. Nhưng ta không biết chính xác `S` là gì chỉ từ tham chiếu wildcard.

Các ví dụ sau hợp lệ:

| Đối tượng có kiểu | Gán cho `List<? super Integer>`? | Lý do |
| --- | --- | --- |
| `List<Integer>` | Có | Nhận đúng `Integer` |
| `List<Number>` | Có | `Integer` là `Number` |
| `List<Object>` | Có | `Integer` là `Object` |
| `List<Double>` | Không | `Double` không phải kiểu cha của `Integer` |
| `List<String>` | Không | Không có quan hệ nhận `Integer` phù hợp |

Ba dòng hợp lệ đầu là ví dụ quen thuộc, không phải tuyên bố chỉ có đúng ba kiểu được chấp nhận. Quan hệ kiểu cha còn có thể bao gồm interface mà `Integer` triển khai.

Wildcard giới hạn dưới được dùng ở vị trí sử dụng generic. Nó không khai báo một lớp generic mới và không sao chép dữ liệu.

```java
List<Object> original = new ArrayList<>();
List<? super Integer> target = original;

target.add(10);
System.out.println(original); // [10]
```

Hai biến vẫn trỏ đến cùng một đối tượng danh sách; thay đổi qua `target` được thấy qua `original`. [Java Language Specification 17: đối số kiểu và wildcard](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1)

## 3. Có thể ghi những giá trị nào?

### 3.1. Ghi giá trị của giới hạn dưới

Qua `List<? super Integer>`, có thể thêm `Integer`:

```java
List<? super Integer> target = new ArrayList<Number>();
target.add(Integer.valueOf(7));
target.add(8);
```

Ở dòng cuối, giá trị `int` được boxing thành `Integer`.

Với một giới hạn dưới tổng quát `? super Dog`, cũng có thể thêm một đối tượng của lớp con `Dog`, vì nó vẫn dùng được ở nơi nhận `Dog`. Trong ví dụ số nguyên, `Integer` là lớp final nên không có lớp con do người dùng định nghĩa.

### 3.2. Không phải được thêm mọi Number

Đoạn sau **không biên dịch**:

```java
List<? super Integer> target = new ArrayList<Integer>();
target.add(2.5); // Double không được bảo đảm chấp nhận.
```

`2.5` trở thành `Double`. Nhưng danh sách thực tế có thể là `List<Integer>`, nên thêm `Double` sẽ phá cam kết kiểu.

Cũng không được thêm một biến chỉ có kiểu tĩnh `Number`:

```java
Number value = Integer.valueOf(7);
List<? super Integer> target = new ArrayList<Number>();

// Không biên dịch:
target.add(value);
```

Dù đối tượng hiện tại của `value` là `Integer`, biểu thức `value` được kiểm tra dưới kiểu `Number`. Giới hạn dưới không cho phép bỏ qua hợp đồng kiểu của biểu thức.

Nếu dữ liệu vốn phải là `Integer`, hãy giữ thông tin kiểu đó trong thiết kế. Không thêm cast chỉ để vượt lỗi mà chưa có cơ sở.

### 3.3. Thay phần tử cũng chịu quy tắc cùng kiểu

Với một danh sách không rỗng và có hỗ trợ `set`:

```java
List<Number> values = new ArrayList<>(List.<Number>of(2.5));
List<? super Integer> target = values;

Object old = target.set(0, 10);
```

Ghi `Integer` là an toàn, nhưng giá trị cũ chỉ được bảo đảm là `Object`: nó có thể là `Double` như trong ví dụ.

Wildcard giới hạn dưới nói về loại dữ liệu an toàn khi ghi, không chỉ riêng phương thức `add`.

## 4. Vì sao đọc chỉ bảo đảm Object?

Một danh sách nhận `Integer` không nhất thiết chỉ chứa `Integer`:

```java
List<Object> values = new ArrayList<>();
values.add("header");

List<? super Integer> target = values;
target.add(10);

Object first = target.get(0);
System.out.println(first); // header
```

Nếu `get(0)` được coi là `Integer`, ví dụ trên sẽ không an toàn. Vì đích có thể là một `List<Object>` với dữ liệu cũ bất kỳ, kiểu đọc chung chỉ là `Object`.

Các dòng sau **không biên dịch**:

```java
Integer firstInteger = target.get(0);
Number firstNumber = target.get(0);
```

Từ “consumer” trong PECS không có nghĩa đối tượng không đọc được. Nó có nghĩa ta dùng kiểu này để bảo đảm chiều nhận giá trị; thông tin kiểu của dữ liệu đọc ra yếu hơn.

Đừng mô tả `? super Integer` là “write-only”. Ta vẫn có thể đọc dưới kiểu `Object`, hỏi kích thước, duyệt, xóa hoặc thực hiện các thao tác được đối tượng hỗ trợ.

Một phép ép kiểu khi đọc chỉ an toàn nếu có bằng chứng độc lập rằng phần tử phù hợp. Sự hiện diện của wildcard không cung cấp bằng chứng ấy.

## 5. PECS: nhìn luồng dữ liệu từ phương thức

PECS là cách ghi nhớ:

```text
Producer Extends
Consumer Super
```

Dịch theo vai trò:

- Nơi **cung cấp T để phương thức đọc**: dùng `? extends T`.
- Nơi **nhận T do phương thức ghi**: dùng `? super T`.

Xét một phương thức chuyển phần tử từ nguồn sang đích:

```java
static <T> void appendAll(
        Iterable<? extends T> source,
        Collection<? super T> target) {

    for (T value : source) {
        target.add(value);
    }
}
```

Phương thức cần import `java.util.Collection`; `Iterable` thuộc `java.lang`.

- `source` cung cấp các giá trị dùng được như `T`, nên dùng `extends`.
- `target` nhận những giá trị `T`, nên dùng `super`.
- Tham số kiểu `T` liên kết hai phía trong cùng một lời gọi.

Đây là một phương thức **thêm các phần tử vào đích theo thao tác add**, không phải giao dịch di chuyển dữ liệu. Nó không xóa nguồn và không hoàn tác nếu có lỗi giữa chừng. Thứ tự và khả năng giữ phần tử trùng phụ thuộc loại collection đích; chẳng hạn một tập không giữ các phần tử bằng nhau lặp lại.

Điểm nhìn là phương thức đang thiết kế. Một collection có thể cung cấp dữ liệu trong phương thức này nhưng nhận dữ liệu trong phương thức khác; vai trò không gắn vĩnh viễn với tên lớp hay tên biến. [Oracle: hướng dẫn thiết kế wildcard](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html)

### Các cặp nguồn–đích thường gặp

| Kiểu nguồn | Kiểu đích | Có thể chuyển an toàn theo phương thức trên? |
| --- | --- | --- |
| `List<Integer>` | `List<Integer>` | Có |
| `List<Integer>` | `List<Number>` | Có |
| `List<Integer>` | `List<Object>` | Có |
| `List<Double>` | `List<Number>` | Có |
| `List<Number>` | `List<Integer>` | Không |
| `List<String>` | `List<Number>` | Không |

Dòng `List<Number>` sang `List<Integer>` bị từ chối dù nguồn hiện tại tình cờ chỉ có số nguyên. Kiểu nguồn cho phép có những `Number` khác; chữ ký không có bằng chứng rằng mọi phần tử đều là `Integer`.

Khi dùng phương thức minh họa, nguồn không được bị sửa cấu trúc không hợp lệ trong lúc đang duyệt. Đặc biệt, không mặc định an toàn khi nguồn và đích thực chất là cùng một collection hoặc các view chung dữ liệu.

## 6. So sánh ba kiểu dễ nhầm

| Kiểu tham chiếu | Điều biết về phần tử | Ghi `Integer` tùy ý? | Kiểu đọc bảo đảm |
| --- | --- | --- | --- |
| `List<Integer>` | Chính xác kiểu phần tử là `Integer` | Có | `Integer` |
| `List<? extends Number>` | Một kiểu chưa biết thuộc hệ `Number` | Không | `Number` |
| `List<? super Integer>` | Một kiểu chưa biết nhận được `Integer` | Có | `Object` |
| `List<?>` | Một kiểu phần tử chưa biết | Không | `Object` |
| `List<Object>` | Kiểu phần tử là `Object` | Có | `Object` |

Các cột “ghi” nói về kiểm tra kiểu. Danh sách có thể vẫn không cho sửa hoặc có hạn chế giá trị khi chạy.

`List<? extends Number>` không bảo đảm chỉ đọc theo nghĩa bất biến: chẳng hạn `clear()` có thể hợp lệ và thay đổi nguồn. `List<? super Integer>` cũng không bảo đảm chỉ ghi. Wildcard giới hạn những phép sử dụng cần biết loại phần tử; nó không tạo một cơ chế phân quyền sửa ở thời điểm chạy. [Oracle: quan hệ kiểu với wildcard](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html)

## 7. PECS xuất hiện cả trong callback

### 7.1. Consumer nhận được phần tử

`Iterable.forEach` nhận đối tượng dạng:

```java
Consumer<? super T>
```

Nếu danh sách có phần tử `Integer`, một `Consumer<Number>` hoàn toàn có thể nhận chúng:

```java
List<Integer> ids = List.of(1, 2, 3);

Consumer<Number> printer =
        value -> System.out.println(value.doubleValue());

ids.forEach(printer);
```

Đoạn minh họa cần import `List` và `java.util.function.Consumer`.

Consumer có khả năng xử lý `Number` cũng xử lý được `Integer`. Không bắt người dùng viết lại thành `Consumer<Integer>` khi năng lực hiện có đã đủ.

Trong trường hợp này, đối tượng callback là bên tiêu thụ `T`. Đừng chỉ nhìn tên phương thức `forEach` rồi đoán chiều wildcard. [Java 17: Iterable.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html#forEach(java.util.function.Consumer)), [Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html)

### 7.2. Comparator tiêu thụ hai giá trị để so sánh

`List<E>.sort` nhận `Comparator<? super E>`. Một comparator so sánh được `Number` có thể dùng để sắp danh sách `Integer`:

```java
Comparator<Number> byNumber =
        Comparator.comparingDouble(Number::doubleValue);

List<Integer> ids = new ArrayList<>(List.of(3, 1, 2));
ids.sort(byNumber);

System.out.println(ids); // [1, 2, 3]
```

Đây là minh họa cần import các kiểu được dùng. Comparator tiếp nhận hai phần tử; giá trị `int` trả về của phép so sánh không biến `T` thành dữ liệu đầu ra.

Comparator dùng `doubleValue` chỉ phù hợp với mục tiêu minh họa và miền dữ liệu này. Nó không bảo toàn chính xác thứ tự của mọi loại `Number` có độ chính xác lớn; kiểu generic phù hợp không tự bảo đảm quy tắc so sánh nghiệp vụ đúng. [Java 17: List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))

## 8. Đọc chữ ký Collections.copy bằng PECS

Một API tiêu biểu:

```java
static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Đích nhận giá trị `T`; nguồn cung cấp giá trị dùng được như `T`. Đây là cùng hướng lập luận, dù thứ tự tham số là đích trước và nguồn sau.

Nhưng PECS chỉ giải quyết quan hệ kiểu. Hợp đồng thực thi của `Collections.copy` còn quy định đích phải có **kích thước ít nhất bằng nguồn**. Nó thay các vị trí có sẵn, không tự thêm chỗ như phương thức `appendAll` ở trên.

```java
List<Number> dest =
        new ArrayList<>(List.<Number>of(9.0, 9.0, 9.0));

Collections.copy(dest, List.of(1, 2));
System.out.println(dest); // [1, 2, 9.0]
```

Nếu chỉ viết:

```java
List<Number> dest = new ArrayList<>(10);
Collections.copy(dest, List.of(1, 2)); // IndexOutOfBoundsException.
```

Dung lượng 10 không tạo 10 phần tử; kích thước đích vẫn bằng 0.

Đọc wildcard để hiểu bên nào đọc và bên nào ghi, rồi tiếp tục đọc yêu cầu về kích thước, quyền sửa và ngoại lệ. Một chữ ký generic đúng không thay thế toàn bộ hợp đồng API. [Java 17: Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List))

## 9. Khi nào không nên chỉ dùng wildcard?

### 9.1. Cần giữ một kiểu chính xác qua nhiều vị trí

Nếu phương thức vừa đọc một giá trị kiểu cụ thể vừa trả nó về, hoặc liên kết nó với tham số khác, một tham số kiểu có tên thường biểu đạt tốt hơn.

Ví dụ:

```java
static <T> T addAndReturn(List<T> target, T value) {
    target.add(value);
    return value;
}
```

Đây là phương thức minh họa. `T` liên kết giá trị được nhận, danh sách và kết quả.

Không biến mọi `List<T>` thành `List<? super T>` theo thói quen. Cần xem hợp đồng mong muốn, cách suy luận kiểu và loại kết quả người gọi cần.

### 9.2. Trả về wildcard khiến bên gọi tiếp tục mang giới hạn ấy

Nếu một phương thức tạo mới một `List<Integer>`, trả `List<? super Integer>` thường làm bên gọi mất khả năng đọc trực tiếp ra `Integer` mà không có lợi ích tương xứng.

Wildcard là công cụ nới điều kiện nhận đầu vào theo vai trò, không phải một mặc định phải xuất hiện ở mọi chỗ. Chỉ đưa wildcard vào kiểu trả về khi giới hạn ấy thực sự là chủ ý của API.

### 9.3. Lower bound không dùng cùng cú pháp với type parameter

Trong Java, không viết:

```java
// Không hợp lệ:
<T super Integer>
```

`super` ở bài này thuộc cú pháp wildcard `? super Integer`. Tham số kiểu có tên sử dụng những quy tắc khai báo khác, chẳng hạn `<T extends Number>` cho giới hạn trên.

Một wildcard không đồng thời viết cả `extends` lẫn `super` để tạo khoảng tùy ý. Đừng suy rộng cú pháp từ cách đọc nghĩa tiếng Việt.

## 10. Giới hạn kiểu không bảo đảm quyền sửa hay tính nguyên tử

### 10.1. Đối tượng có thể không hỗ trợ add

Phương thức nhận `List<? super Integer>` chấp nhận một biến `List<Integer>` về mặt kiểu, nhưng đối tượng có thể được tạo bằng `List.of`:

```java
List<Integer> target = List.of(1, 2);
addSampleIds(target); // UnsupportedOperationException.
```

Nếu phương thức cần ghi, tài liệu của nó nên nói đích phải hỗ trợ thao tác đó. Nếu phương thức sở hữu việc tạo kết quả, có thể chủ động chọn cấu trúc có thể sửa.

Tương tự, `null` có thể hợp lệ về kiểu nhưng bị collection từ chối theo chính sách riêng. Wildcard không diễn đạt đầy đủ tính null của dữ liệu.

### 10.2. Ghi nhiều lần không tự thành giao dịch

Nếu lần `add` thứ nhất thành công nhưng lần tiếp theo lỗi, các phần tử đã thêm không được hợp đồng wildcard tự hoàn tác.

`List<? super T>` cũng không có nghĩa an toàn đồng thời. Đích là `ArrayList` dùng chung giữa nhiều luồng vẫn cần cơ chế phối hợp phù hợp; kiểu generic không làm phát sinh khóa.

### 10.3. Không dùng raw type hoặc cast để bỏ qua lỗi kiểu

Nếu nguồn có kiểu `List<Number>` mà đích là `List<Integer>`, lỗi có thể phản ánh một thiết kế thật sự không an toàn. Hãy xác định có cần kiểm tra từng giá trị, chuyển đổi dữ liệu hoặc chọn đích rộng hơn không.

Ép qua raw `List` hoặc tắt cảnh báo unchecked không chuyển `Double` thành `Integer`. Nó chỉ bỏ một phần kiểm tra, khiến lỗi có thể xuất hiện muộn hơn ở nơi đọc.

## 11. Chương trình Java 17 hoàn chỉnh

Lưu vào `LowerBoundPecsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;

public class LowerBoundPecsDemo {
    private static void addSampleIds(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    private static <T> void appendAll(
            Iterable<? extends T> source,
            Collection<? super T> target) {
        for (T value : source) {
            target.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>(List.<Number>of(2.5));
        List<Object> objects = new ArrayList<>(List.of("header"));

        addSampleIds(integers);
        addSampleIds(numbers);
        addSampleIds(objects);
        System.out.println("integers = " + integers);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);

        List<? super Integer> sink = objects;
        Object existing = sink.get(0);
        System.out.println("existing sink value = " + existing);

        List<Integer> source = List.of(3, 1, 2);
        List<Number> destination = new ArrayList<>();
        appendAll(source, destination);
        System.out.println("appended numbers = " + destination);
        System.out.println("source unchanged = " + source);

        Comparator<Number> byNumber =
                Comparator.comparingDouble(Number::doubleValue);
        integers = new ArrayList<>(source);
        integers.sort(byNumber);
        System.out.println("sorted integers = " + integers);

        Consumer<Number> printer =
                value -> System.out.println("consume = " + value);
        integers.forEach(printer);

        List<Number> slots = new ArrayList<>(
                List.<Number>of(9.0, 9.0, 9.0));
        Collections.copy(slots, List.of(1, 2));
        System.out.println("copied into existing slots = " + slots);

        List<Number> capacityOnly = new ArrayList<>(10);
        try {
            Collections.copy(capacityOnly, List.of(1, 2));
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("capacity alone is not enough for Collections.copy");
        }

        List<Integer> unmodifiable = List.of(1, 2);
        try {
            addSampleIds(unmodifiable);
        } catch (UnsupportedOperationException expected) {
            System.out.println("compatible type does not promise mutability");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LowerBoundPecsDemo.java
java LowerBoundPecsDemo
```

Stdout:

```text
integers = [10, 20]
numbers = [2.5, 10, 20]
objects = [header, 10, 20]
existing sink value = header
appended numbers = [3, 1, 2]
source unchanged = [3, 1, 2]
sorted integers = [1, 2, 3]
consume = 1
consume = 2
consume = 3
copied into existing slots = [1, 2, 9.0]
capacity alone is not enough for Collections.copy
compatible type does not promise mutability
```

Cách đọc minh chứng:

1. Cùng một phương thức lower bound ghi được `Integer` vào ba loại nơi nhận.
2. Đích `List<Object>` vẫn giữ phần tử cũ `"header"`; đọc qua lower bound chỉ có thể dựa vào `Object`.
3. Hàm `appendAll` phối hợp nguồn `extends` và đích `super`, tạo thêm các phần tử ở đích mà không xóa nguồn.
4. `Comparator<Number>` nhận được các phần tử `Integer` để so sánh.
5. `Consumer<Number>` nhận được từng `Integer` từ `forEach`.
6. `Collections.copy` thay các vị trí đích có sẵn và không đụng vị trí thừa.
7. Dự trữ dung lượng không đủ đáp ứng yêu cầu kích thước của `Collections.copy`.
8. Loại generic phù hợp không làm một danh sách không sửa được trở thành có thể sửa.

Ví dụ dùng các nguồn và đích riêng cho `appendAll`, tránh việc thêm vào chính collection đang được duyệt.

## 12. Ca cố ý không biên dịch

Lưu riêng tệp `LowerBoundMustFail.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LowerBoundMustFail {
    public static void main(String[] args) {
        List<? super Integer> target = new ArrayList<Integer>();
        target.add(2.5);
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 LowerBoundMustFail.java
```

**Kỳ vọng:** trình biên dịch từ chối `target.add(2.5)`.

Nguyên nhân là `target` có thể trỏ đến `List<Integer>`, nên không thể bảo đảm nhận `Double`. Thông báo có thể nhắc đến một kiểu capture chưa biết; đó là cách trình biên dịch biểu diễn kiểu phần tử cụ thể đang bị wildcard che đi.

Không đặt tệp cố ý lỗi vào tập nguồn cần build thành công. Đây là phép kiểm chứng quy tắc kiểu, không phải ví dụ chương trình chạy.

## 13. Quy trình chọn bound cho một tham số

Với mỗi tham số generic của phương thức, làm lần lượt:

1. Chọn kiểu giá trị `T` mà phương thức thực sự cần xử lý.
2. Xác định phương thức lấy `T` ra từ tham số hay đưa `T` vào đó.
3. Nếu lấy ra như `T`, bắt đầu cân nhắc `? extends T`.
4. Nếu đưa `T` vào, bắt đầu cân nhắc `? super T`.
5. Nếu cần giữ quan hệ kiểu chính xác qua nhiều chỗ, cân nhắc tham số kiểu có tên.
6. Kiểm tra quyền sửa, `null`, kích thước và điều kiện đồng thời ngoài hệ thống generic.
7. Thử cả lời gọi cần được nhận lẫn lời gọi phải bị từ chối.

Ví dụ với danh sách nhận `Integer`, hãy kiểm tra `List<Integer>`, `List<Number>` và `List<Object>` đều dùng được, trong khi `List<Double>` bị từ chối. Đây là cách đánh giá tính linh hoạt mà không làm mất an toàn.

## 14. Lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `super Integer` nghĩa là thêm mọi lớp cha của Integer | Nó bảo đảm đích nhận `Integer`; không bảo đảm nhận mọi `Number` hoặc `Object` |
| Đích lower bound chỉ chứa Integer | Nó có thể là `List<Object>` với dữ liệu cũ khác loại |
| Đọc từ `List<? super Integer>` được `Number` | Chỉ bảo đảm `Object` |
| PECS dựa trên tên biến source/target | Phải nhìn hướng dữ liệu từ phương thức |
| Consumer luôn là collection đích | Callback nhận phần tử cũng là consumer của kiểu đó |
| Wildcard làm collection có thể sửa | Quyền sửa vẫn do đối tượng và API quyết định |
| Có dung lượng là `Collections.copy` dùng được | Đích phải có đủ số phần tử hiện có |
| Dùng `super` cho cả nguồn lẫn đích sẽ linh hoạt hơn | Nguồn khi đó không cho đọc với kiểu `T` cần thiết |
| Dùng `extends` cho cả hai phía vẫn ghi được T | Đích có kiểu phần tử chưa biết nên không nhận một T tùy ý |
| Suppress warning là cách giải quyết bound | Nó không chứng minh dữ liệu an toàn |

## 15. Tự luyện

1. Một phương thức thêm `Long` vào collection. Nếu muốn nhận cả `Collection<Long>`, `Collection<Number>` và `Collection<Object>`, nên bắt đầu với chữ ký nào?  
   **Đáp án:** `Collection<? super Long>`, kèm yêu cầu đích hỗ trợ thêm.

2. Vì sao `List<? super Integer>` không cho thêm `Double`?  
   **Đáp án:** danh sách thật có thể có kiểu phần tử `Integer`.

3. Vì sao đọc từ đích lower bound không bảo đảm ra `Integer`?  
   **Đáp án:** đích có thể là một danh sách kiểu rộng hơn và đã chứa giá trị khác.

4. Một hàm chuyển dữ liệu số nguyên sang danh sách số nên đặt wildcard hai phía thế nào?  
   **Gợi ý:** nguồn cung cấp kiểu dùng được như `T` với `extends`; đích nhận `T` với `super`.

5. `Comparator<Object>` có thể dùng cho `List<String>.sort` về mặt kiểu không?  
   **Đáp án:** có, vì nó nhận được `String`. Nhưng logic so sánh vẫn phải thực sự hợp lệ cho các phần tử và đáp ứng hợp đồng comparator.

Giới hạn dưới giúp viết nơi nhận dữ liệu linh hoạt mà không làm mất cam kết kiểu. PECS trở nên dễ áp dụng khi luôn xác định rõ giá trị nào đi ra từ nguồn, giá trị nào đi vào đích và những yêu cầu nào còn nằm ngoài kiểm tra generic.
