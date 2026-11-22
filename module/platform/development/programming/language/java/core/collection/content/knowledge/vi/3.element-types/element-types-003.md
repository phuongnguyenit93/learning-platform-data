# Tính bất biến của generic: `List<Integer>` và `List<Number>`

`Integer` là kiểu con của `Number`, nên một giá trị `Integer` có thể được dùng ở nơi nhận `Number`. Nhưng từ đó không suy ra `List<Integer>` là kiểu con của `List<Number>`.

Đây là **tính bất biến trong quan hệ kiểu (invariance)** của tham số generic. Từ “bất biến” ở đây không nói danh sách có được thêm hoặc xóa phần tử hay không. Một `ArrayList<Integer>` vẫn có thể sửa nội dung; điều bị giới hạn là quan hệ gán giữa các kiểu danh sách có đối số kiểu khác nhau.

Bài này giải thích quy tắc qua nhu cầu thực tế: muốn đọc các số từ nhiều loại danh sách, muốn thêm số nguyên vào một nơi nhận, hoặc muốn tạo danh sách số mới từ danh sách số nguyên. Ví dụ dùng Java 17 trở lên.

## 1. Hai tầng kiểu phải được xét riêng

### 1.1. Quan hệ giữa kiểu phần tử

Đoạn sau hợp lệ:

```java
Integer integer = 7;
Number number = integer;
```

Một `Integer` là một `Number`. Qua tham chiếu `number`, ta có thể gọi các phương thức được `Number` công bố, chẳng hạn `doubleValue()`.

`Double` cũng là một kiểu con của `Number`. Vì vậy, một vị trí cho phép chứa `Number` có thể nhận cả `Integer` lẫn `Double`.

### 1.2. Quan hệ giữa kiểu danh sách

Đoạn sau **không biên dịch**:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // Lỗi kiểu.
```

`List<Integer>` và `List<Number>` là hai kiểu tham số hóa khác nhau. Quan hệ `Integer`–`Number` không được tự động nâng thành cùng quan hệ giữa hai danh sách.

Trong Java, một kiểu generic như `List<E>` không được khai báo là đồng biến theo `E`. Wildcard là công cụ để diễn đạt quan hệ phù hợp ở nơi sử dụng, khi ta thực sự cần chấp nhận nhiều kiểu danh sách. [Oracle: generics, kế thừa và kiểu con](https://docs.oracle.com/javase/tutorial/java/generics/inheritance.html)

### Bảng đối chiếu nhanh

| Phép gán | Hợp lệ? | Lý do |
| --- | --- | --- |
| `Integer` sang `Number` | Có | Quan hệ kiểu con thông thường |
| `ArrayList<Integer>` sang `List<Integer>` | Có | `ArrayList<E>` triển khai `List<E>` |
| `List<Integer>` sang `Collection<Integer>` | Có | `List<E>` kế thừa `Collection<E>` |
| `List<Integer>` sang `List<Number>` | Không | Thay đối số generic không tự tạo quan hệ kiểu con |
| `List<Integer>` sang `List<Object>` | Không | Cùng lý do, dù `Integer` là một `Object` |
| `List<Integer>` sang `List<? extends Number>` | Có | Wildcard cho phép một kiểu phần tử chưa biết nhưng là `Number` hoặc kiểu con |

Điểm quan trọng là phân biệt việc đổi **lớp chứa theo quan hệ kế thừa** với việc đổi **đối số kiểu phần tử**.

## 2. Vì sao Java phải từ chối `List<Integer>` sang `List<Number>`?

Hãy giả sử Java cho phép phép gán ấy:

```java
// Mã giả định để giải thích nguy cơ; Java không cho phép dòng gán thứ hai.
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers;

numbers.add(3.5);
Integer first = integers.get(0);
```

Hai biến `integers` và `numbers` sẽ cùng trỏ tới một danh sách. Qua kiểu `List<Number>`, lời gọi `add(3.5)` là hợp lệ vì `3.5` được boxing thành `Double`, một kiểu con của `Number`.

Nhưng tham chiếu ban đầu vẫn có kiểu `List<Integer>`. Khi đọc, bên sử dụng kỳ vọng phần tử là `Integer`, trong khi dữ liệu vừa bị chèn là `Double`. Cam kết kiểu của danh sách đã bị phá.

Java chặn ngay phép gán để không tạo đường ghi nguy hiểm này.

Lập luận không phụ thuộc việc danh sách hiện tại đang rỗng hay chỉ chứa số nguyên. `List<Number>` là một hợp đồng cho phép làm việc với phần tử kiểu `Number`; nó không chỉ có nghĩa “một danh sách mà ta định đọc như số”.

### Vì sao chiều ngược lại cũng không hợp lệ?

```java
List<Number> numbers = new ArrayList<>();
numbers.add(3.5);

// Không biên dịch:
List<Integer> integers = numbers;
```

Một `List<Number>` có thể chứa `Double`, `Long` hoặc những kiểu `Number` khác. Không thể bảo đảm mọi phần tử đều là `Integer`.

Vì vậy, `List<Integer>` không phải kiểu con của `List<Number>`, và `List<Number>` cũng không phải kiểu con của `List<Integer>`. [Java Language Specification 17: kiểu con của kiểu tham chiếu](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2)

## 3. Invariance không phải immutability

Hai khái niệm trả lời hai câu hỏi khác nhau:

| Khái niệm | Câu hỏi |
| --- | --- |
| Invariance | Các kiểu như `List<Integer>` và `List<Number>` có được gán thay thế nhau không? |
| Không sửa được / bất biến dữ liệu | Đối tượng danh sách hoặc trạng thái phần tử có thể thay đổi không? |

Ví dụ:

```java
List<Integer> editable = new ArrayList<>();
editable.add(1);
editable.add(2);
editable.remove(Integer.valueOf(1));
```

Danh sách này có thể sửa, nhưng `List<Integer>` vẫn không gán được sang `List<Number>`.

Ngược lại:

```java
List<Integer> fixed = List.of(1, 2, 3);

// Vẫn không biên dịch:
List<Number> numbers = fixed;
```

Dù đối tượng do `List.of` tạo không cho sửa, quy tắc quan hệ kiểu vẫn áp dụng. Trình biên dịch không đổi quan hệ giữa `List<Integer>` và `List<Number>` chỉ vì biết một cách tạo hiện tại không hỗ trợ `add`.

Cũng không liên quan đến từ khóa `final`:

```java
final List<Integer> values = new ArrayList<>();
values.add(1); // Hợp lệ.
```

`final` ngăn gán lại biến `values`; nó không chuyển kiểu generic và không tự đóng băng nội dung danh sách.

## 4. Chỉ cần đọc số: dùng `List<? extends Number>`

Nếu một phương thức chỉ cần lấy các phần tử như `Number`, yêu cầu `List<Number>` thường quá hẹp.

Một chữ ký phù hợp hơn:

```java
static double sum(List<? extends Number> source) {
    double result = 0;
    for (Number value : source) {
        result += value.doubleValue();
    }
    return result;
}
```

Đây là phương thức minh họa cần đặt trong một lớp và import `List`. Nó giả định các phần tử không phải `null`.

Phương thức nhận được:

```java
sum(List.of(1, 2, 3));
sum(List.of(1.5, 2.5));
sum(List.<Number>of(1, 2.5));
```

`List<? extends Number>` có thể hiểu là:

> Một danh sách có kiểu phần tử cụ thể chưa biết; kiểu ấy là `Number` hoặc một kiểu con của `Number`.

Ta chưa biết danh sách thật là `List<Integer>`, `List<Double>` hay `List<Number>`, nhưng khi đọc một phần tử, có thể an toàn nhìn nó như `Number`. [Oracle: upper-bounded wildcard](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html)

### 4.1. Vì sao không được thêm một Integer?

```java
List<? extends Number> source = new ArrayList<Double>();

// Không biên dịch:
source.add(1);
```

Giá trị 1 là một `Integer`. Nhưng đối tượng được gán vào `source` trong ví dụ là danh sách `Double`. Thêm `Integer` sẽ phá quy tắc của danh sách thật.

Tương tự, không được thêm một `Double` tùy ý, vì `source` có thể đang trỏ đến `List<Integer>`.

Quy tắc không đổi ngay cả ở trường hợp này:

```java
List<? extends Number> source =
        new ArrayList<Integer>();

// Vẫn không biên dịch:
source.add(1);
```

Khi sử dụng qua biến `source`, kiểu phần tử được xem là một kiểu chưa biết được giới hạn bởi `Number`. Trình biên dịch không cho dùng suy đoán bên ngoài để bỏ qua giới hạn đó.

### 4.2. Extends không tạo một danh sách chỉ đọc

`List<? extends Number>` hạn chế các phép ghi cần biết kiểu phần tử; nó không tạo wrapper mới và không tự cấm mọi thay đổi.

Ví dụ:

```java
List<Integer> original =
        new ArrayList<>(List.of(8, 9));

List<? extends Number> reference = original;
reference.clear();

System.out.println(original); // []
```

`clear()` không phải đưa một giá trị không rõ kiểu vào danh sách. Nó được phép về kiểu; có thực hiện được hay không còn tùy quyền sửa của đối tượng.

Ngoài ra, `null` có thể được truyền về mặt kiểu vào `add` của wildcard này, nhưng lớp cụ thể có thể từ chối `null` hoặc không hỗ trợ thêm. Không dùng điều đó làm cách lách quy tắc hoặc làm cơ sở thiết kế dữ liệu.

Nếu thật sự cần không cho sửa qua tham chiếu, hãy dùng API có hợp đồng không sửa được phù hợp. Wildcard chỉ điều chỉnh khả năng biểu đạt thao tác theo kiểu. [Oracle: hướng dẫn dùng wildcard](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html)

## 5. Cần thêm Integer: dùng `List<? super Integer>`

Giả sử phương thức cần đưa các số nguyên vào một danh sách nhận. `List<? super Integer>` diễn đạt:

> Một danh sách có kiểu phần tử cụ thể là `Integer` hoặc một kiểu cha của `Integer`.

Ví dụ:

```java
static void appendIntegers(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

Có thể truyền:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendIntegers(integers);
appendIntegers(numbers);
appendIntegers(objects);
```

Cả ba kiểu danh sách đều có thể chấp nhận `Integer` mà không vi phạm kiểu phần tử. `List<Double>` không phù hợp. [Oracle: lower-bounded wildcard](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

### 5.1. Đọc lại chỉ bảo đảm Object

```java
List<Object> objects = new ArrayList<>();
objects.add("label");

List<? super Integer> target = objects;
target.add(10);

Object first = target.get(0);
```

`target` có thể đang trỏ đến `List<Object>` chứa chuỗi trước đó. Vì vậy, không được kết luận `get(0)` luôn là `Integer` hoặc thậm chí luôn là `Number`.

Đoạn sau không biên dịch:

```java
Integer first = target.get(0);
```

Nếu xử lý yêu cầu đọc với kiểu mạnh hơn, hãy thiết kế chữ ký phù hợp thay vì thêm ép kiểu chỉ để dập lỗi.

### 5.2. Không thêm được mọi Number

```java
List<? super Integer> target = new ArrayList<Integer>();

// Không biên dịch:
target.add(2.5);
```

Wildcard `super Integer` bảo đảm nhận `Integer`, không bảo đảm nhận mọi `Number`. Một `Double` không phải `Integer`.

Có thể ghi nhớ theo vai trò dữ liệu: nơi cung cấp số để đọc dùng `extends`; nơi nhận số nguyên được thêm vào dùng `super`. Quy tắc thường được gọi là PECS: Producer Extends, Consumer Super. Hãy xác định rõ kiểu đang được cung cấp/tiêu thụ, không áp dụng khẩu hiệu theo tên biến.

## 6. Khi thực sự cần `List<Number>`, hãy tạo cấu trúc mới

Có những trường hợp ứng dụng cần danh sách chứa được nhiều loại `Number`, bắt đầu từ dữ liệu số nguyên.

Cách an toàn:

```java
List<Integer> integers =
        new ArrayList<>(List.of(1, 2, 3));

List<Number> numbers = new ArrayList<>(integers);
numbers.add(4.5);

System.out.println(integers); // [1, 2, 3]
System.out.println(numbers);  // [1, 2, 3, 4.5]
```

Không có phép đổi kiểu toàn bộ một đối tượng `List<Integer>` thành `List<Number>` ở đây. Chương trình tạo **một đối tượng danh sách mới** có kiểu phần tử `Number`, rồi đưa các phần tử `Integer` hợp lệ vào.

Constructor nhận nguồn dạng `Collection<? extends E>`, nên khi `E` là `Number`, nguồn `Collection<Integer>` được chấp nhận. [Java 17: ArrayList(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection))

Nếu đã có đích:

```java
List<Number> destination = new ArrayList<>();
destination.addAll(integers);
```

Đây cũng là sao chép các phần tử vào cấu trúc phù hợp, không phải gán hai biến cùng trỏ đến một danh sách với hai cam kết phần tử mâu thuẫn.

### Sao chép cấu trúc không phải sao chép sâu

Danh sách mới chứa các tham chiếu phần tử được lấy từ nguồn. Với `Integer` bất biến, điều đó thường dễ suy luận. Với đối tượng có thể sửa, hai danh sách vẫn có thể cùng tham chiếu một đối tượng phần tử.

Tạo bản sao danh sách giải quyết việc thêm/xóa trên hai cấu trúc độc lập; nó không tự sao chép toàn bộ đồ thị đối tượng.

## 7. `List<?>` khác với `List<Object>`

Hai kiểu này rất dễ bị nhầm:

| Kiểu | Ý nghĩa | Có thể thêm một chuỗi tùy ý về mặt kiểu? |
| --- | --- | --- |
| `List<Object>` | Danh sách có kiểu phần tử là `Object` | Có |
| `List<?>` | Danh sách có kiểu phần tử cụ thể chưa biết | Không |
| `List<? extends Number>` | Kiểu phần tử chưa biết nhưng thuộc hệ `Number` | Không |
| `List<? super Integer>` | Kiểu phần tử là `Integer` hoặc kiểu cha phù hợp | Không; chỉ bảo đảm nhận `Integer` |

Cột cuối nói về kiểm tra kiểu khi biên dịch. Đối tượng danh sách thực tế vẫn có thể không hỗ trợ `add`.

Một hàm chỉ muốn in phần tử bất kỳ có thể nhận:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Hàm nhận được cả `List<Integer>` lẫn `List<String>` mà không cần biến chúng thành `List<Object>`.

Vì vậy, nếu trình biên dịch từ chối truyền `List<Integer>` vào phương thức nhận `List<Object>`, hãy hỏi phương thức thực sự có cần thêm mọi `Object` không. Nếu chỉ đọc như `Object`, `List<?>` có thể mới là hợp đồng đúng. [Oracle: wildcard và quan hệ kiểu con](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html)

## 8. Suy luận kiểu không thay đổi quy tắc invariance

Đoạn này hợp lệ:

```java
List<Number> numbers = List.of(1, 2);
```

Nó không chứng minh `List<Integer>` gán được cho `List<Number>`. `List.of` là phương thức generic; kiểu đích tham gia vào suy luận đối số kiểu. Trong ngữ cảnh trên, trình biên dịch có thể chọn kiểu phần tử `Number` ngay khi gọi factory.

Có thể viết ý định rõ hơn:

```java
List<Number> numbers = List.<Number>of(1, 2);
```

Trong khi đó:

```java
List<Integer> integers = List.of(1, 2);

// Không biên dịch:
List<Number> numbers = integers;
```

Ở đây biến nguồn đã có kiểu `List<Integer>`; không còn lời gọi factory đang được suy luận theo kiểu đích để thay đổi ý nghĩa.

Tương tự, `var` không làm kiểu trở nên linh hoạt:

```java
var integers = List.of(1, 2);

// Không biên dịch:
List<Number> numbers = integers;
```

Kiểu của biến `integers` được suy luận lúc khai báo. `var` không phải “một biến nhận danh sách với bất kỳ kiểu phần tử nào”.

Lưu ý riêng: danh sách từ `List.of` không sửa được. Quyền sửa của factory và quy tắc suy luận generic là hai vấn đề độc lập.

## 9. Vì sao mảng lại cho phép Number[] = Integer[]?

Java cho phép:

```java
Number[] numbers = new Integer[]{1, 2};
```

Mảng tham chiếu có quan hệ đồng biến. Nhưng đối tượng mảng lúc chạy vẫn biết kiểu phần tử thật là `Integer`.

Vì vậy:

```java
numbers[0] = 3.5; // Biên dịch được, nhưng ném ArrayStoreException.
```

Lời gọi gán được nhìn qua kiểu `Number[]`, nhưng khi thực thi, mảng từ chối một `Double` trong vùng dành cho `Integer`. [Java Language Specification 17: kiểm tra lưu phần tử mảng](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5)

So sánh:

| Cấu trúc | Phép nâng kiểu đang xét | Cách chặn trường hợp ghi sai |
| --- | --- | --- |
| Mảng | `Integer[]` sang `Number[]` được phép | Kiểm tra kiểu phần tử mảng khi chạy |
| Generic List | `List<Integer>` sang `List<Number>` không được phép | Từ chối quan hệ gán khi biên dịch |

Không lấy quy tắc mảng để đoán quy tắc generic. Hai cơ chế được thiết kế và kiểm tra theo cách khác nhau.

## 10. Không giải quyết bằng raw type hoặc ép kiểu không kiểm tra

Một raw type như `List` bỏ đối số kiểu khỏi phần kiểm tra generic. Những ép kiểu qua `List<?>` hoặc raw type có thể làm trình biên dịch chấp nhận một phép gán với cảnh báo unchecked, nhưng không tạo một danh sách mới và không biến mọi phần tử thành `Number` theo một hợp đồng an toàn.

Nếu một alias cho phép thêm `Double` vào đối tượng mà nơi khác vẫn giữ dưới kiểu `List<Integer>`, dữ liệu bị ô nhiễm kiểu. Lỗi có thể chỉ xuất hiện về sau khi một nơi đọc và ép phần tử thành `Integer`.

Không dùng `@SuppressWarnings("unchecked")` như cách sửa mặc định. Nó chỉ tắt cảnh báo, không làm giả định trở thành đúng.

Hãy chọn một trong các cách phù hợp:

- Chỉ cần đọc các số: tham số `? extends Number`.
- Chỉ cần thêm số nguyên: tham số `? super Integer`.
- Cần giữ đúng một kiểu phần tử dùng ở nhiều vị trí: thiết kế phương thức generic với tham số kiểu.
- Cần một danh sách `Number` độc lập: sao chép phần tử vào cấu trúc mới.
- Không cần biết loại phần tử: cân nhắc `List<?>`.

Kiểu generic kiểm tra tại thời điểm biên dịch; không có thao tác tự động “nâng cấp” đối tượng chỉ vì người lập trình viết một phép cast.

## 11. Ví dụ hoàn chỉnh chạy được trên Java 17+

Lưu vào `GenericInvarianceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericInvarianceDemo {
    private static double sum(List<? extends Number> source) {
        double result = 0;
        for (Number value : source) {
            result += value.doubleValue();
        }
        return result;
    }

    private static void appendIntegers(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    public static void main(String[] args) {
        Integer integer = 7;
        Number number = integer;
        System.out.println("number = " + number);

        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<? extends Number> source = integers;
        Number first = source.get(0);
        System.out.println("first = " + first);
        System.out.println("integer sum = " + sum(integers));
        System.out.println("double sum = " + sum(List.of(1.5, 2.5)));

        List<Number> mixed = new ArrayList<>();
        mixed.add(2.5);
        List<? super Integer> sink = mixed;
        appendIntegers(sink);
        Object firstFromSink = sink.get(0);
        System.out.println("mixed = " + mixed);
        System.out.println("first sink value = " + firstFromSink);

        List<Number> copy = new ArrayList<>(integers);
        copy.add(4.5);
        System.out.println("original integers = " + integers);
        System.out.println("independent list structure = " + copy);

        List<Integer> removable = new ArrayList<>(List.of(8, 9));
        List<? extends Number> restricted = removable;
        restricted.clear();
        System.out.println("extends view after clear = " + removable);

        List<Number> targetTyped = List.of(1, 2);
        System.out.println("target-typed list = " + targetTyped);

        Number[] covariantArray = new Integer[]{1, 2};
        try {
            covariantArray[0] = 3.5;
        } catch (ArrayStoreException expected) {
            System.out.println("array rejects Double at runtime");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 GenericInvarianceDemo.java
java GenericInvarianceDemo
```

Stdout:

```text
number = 7
first = 1
integer sum = 6.0
double sum = 4.0
mixed = [2.5, 10, 20]
first sink value = 2.5
original integers = [1, 2, 3]
independent list structure = [1, 2, 3, 4.5]
extends view after clear = []
target-typed list = [1, 2]
array rejects Double at runtime
```

Cách đọc kết quả:

1. Giá trị `Integer` được dùng dưới kiểu `Number`.
2. Nguồn `? extends Number` cho đọc một `Number`, nên cùng hàm tính tổng xử lý được danh sách số nguyên hoặc số thực.
3. Đích `? super Integer` nhận thêm số nguyên vào một danh sách `Number` đã có `Double`; khi đọc qua tham chiếu wildcard, kiểu bảo đảm chung là `Object`.
4. Bản sao `List<Number>` có thể thêm `4.5` mà không sửa cấu trúc của danh sách số nguyên gốc.
5. Tham chiếu `? extends Number` vẫn có thể gọi `clear` trên đối tượng có hỗ trợ sửa, chứng minh wildcard không làm dữ liệu bất biến.
6. Kiểu đích tham gia suy luận ở lời gọi `List.of`.
7. Mảng đồng biến cho phép phép gán tham chiếu nhưng chặn một phần tử sai kiểu bằng ngoại lệ lúc chạy.

Hàm `sum` trong ví dụ chỉ minh họa khả năng đọc các `Number`; nó dùng `double` và không được thiết kế để tính tài chính hoặc bảo toàn chính xác mọi kiểu số.

## 12. Ca cố ý không biên dịch

Một quy tắc về kiểu cần được kiểm chứng cả bằng mã hợp lệ lẫn mã bị từ chối.

Lưu riêng tệp `InvarianceMustFail.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InvarianceMustFail {
    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = integers;
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 InvarianceMustFail.java
```

**Kỳ vọng:** biên dịch thất bại tại phép gán từ `List<Integer>` sang `List<Number>`.

Thông báo sẽ thể hiện lỗi kiểu không tương thích; văn bản hoặc cách trình bày cụ thể có thể khác giữa các phiên bản trình biên dịch. Không đưa tệp cố ý lỗi này vào cùng tập mã cần build thành công của ứng dụng.

Nếu sửa dòng gán thành `List<? extends Number> numbers = integers;`, phần khai báo sẽ hợp lệ. Sau đó, thử thêm `numbers.add(3.5)` để thấy hệ thống kiểu tiếp tục chặn đường ghi không an toàn.

## 13. Chọn chữ ký theo vai trò của dữ liệu

| Việc phương thức cần làm | Kiểu nên bắt đầu cân nhắc |
| --- | --- |
| Đọc các phần tử như `Number` | `List<? extends Number>` |
| Thêm các `Integer` vào nơi nhận | `List<? super Integer>` |
| Đọc và ghi một kiểu `E` cần liên kết với tham số/kết quả khác | Tham số kiểu generic `E` |
| Chỉ duyệt để hiển thị giá trị bất kỳ | `List<?>` |
| Thêm cả `Integer`, `Double` và các `Number` khác | Một `List<Number>` thực sự phù hợp |
| Chuyển dữ liệu số nguyên sang danh sách số có thể mở rộng | Tạo `List<Number>` mới và sao chép phần tử |

Không dùng wildcard chỉ để hết lỗi biên dịch. Trước hết xác định bên nhận sẽ đọc gì, ghi gì và có cần giữ quan hệ kiểu với giá trị khác hay không. Chữ ký nên mô tả đúng trách nhiệm ấy.

## 14. Lỗi thường gặp

| Hiểu nhầm | Điều cần sửa |
| --- | --- |
| `Integer` là `Number` nên `List<Integer>` là `List<Number>` | Quan hệ kiểu phần tử không tự truyền qua generic |
| Invariance nghĩa là không được sửa danh sách | Đây là quy tắc quan hệ kiểu, khác quyền sửa dữ liệu |
| `? extends Number` nhận mọi `Number` để thêm | Nó cho đọc dưới kiểu `Number`, không cho chèn một số bất kỳ |
| `? super Integer` đọc ra luôn là `Integer` | Có thể là `List<Object>` chứa giá trị khác; chỉ bảo đảm `Object` |
| `List<?>` đồng nghĩa `List<Object>` | Một bên chưa biết kiểu; một bên có kiểu phần tử là `Object` |
| Danh sách không sửa được thì quan hệ kiểu có thể đổi | Quan hệ gán vẫn do kiểu tĩnh quyết định |
| `new ArrayList<>(integers)` chỉ là cast | Nó tạo cấu trúc mới rồi đưa phần tử hợp lệ vào |
| Cast unchecked hoặc suppress warning sẽ chuyển đổi dữ liệu | Không; chỉ bỏ qua hoặc tắt một phần kiểm tra |
| `var` cho phép đổi kiểu phần tử sau đó | Kiểu vẫn được xác định lúc khai báo |
| Mảng cho phép đồng biến nên List cũng phải vậy | Mảng và generic có cơ chế khác nhau |

## 15. Tự luyện

1. `List<Double>` có truyền được vào phương thức nhận `List<Number>` không?  
   **Đáp án:** không. Nếu phương thức chỉ đọc như số, cân nhắc `List<? extends Number>`.

2. Vì sao không được thêm `1` vào một biến `List<? extends Number>`?  
   **Đáp án:** danh sách thật có thể là `List<Double>`; kiểu phần tử cụ thể chưa biết.

3. Một `List<Object>` có thể truyền cho phương thức nhận `List<? super Integer>` không?  
   **Đáp án:** có, vì nó có thể nhận `Integer`. Khi đọc qua wildcard đó chỉ bảo đảm `Object`.

4. Muốn bắt đầu từ `List<Integer>`, sau đó thêm `Double` mà không ảnh hưởng danh sách gốc thì làm gì?  
   **Đáp án:** tạo `List<Number> copy = new ArrayList<>(integers)`, rồi thêm vào bản mới.

5. Tại sao `List<Number> values = List.of(1, 2)` hợp lệ nhưng gán biến `List<Integer>` sang `List<Number>` lại không?  
   **Đáp án:** trường hợp đầu là suy luận kiểu cho lời gọi generic theo ngữ cảnh đích; trường hợp sau là quan hệ gán giữa hai kiểu đã xác định.

Tính bất biến của generic giữ cho mỗi tham chiếu danh sách duy trì cam kết về loại phần tử. Khi cần linh hoạt, hãy nới hợp đồng đúng theo vai trò đọc hoặc ghi, thay vì làm mất kiểm tra kiểu.
