# Vì sao không thể thêm một giá trị T tùy ý vào `List<? extends T>`?

## 1. Mục tiêu và tình huống

Giả sử ta cần viết phương thức nhận danh sách các số để tính toán:

```java
static double sum(List<? extends Number> values) {
    double result = 0.0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

Phương thức trên có thể nhận `List<Integer>`, `List<Double>`, `List<BigDecimal>` hoặc `List<Number>`. Nhưng trong chính phương thức, thao tác sau không biên dịch:

```java
values.add(42); // LỖI BIÊN DỊCH
```

Vì sao `Integer` là `Number`, giá trị `42` là `Integer`, và wildcard khai báo `extends Number`, Java vẫn từ chối?

**Câu trả lời cốt lõi:** `List<? extends T>` chứa phần tử thuộc **một kiểu cụ thể chưa biết, là kiểu con của hoặc chính T**. Để thêm phần tử, phải chứng minh phần tử mới tương thích với **kiểu cụ thể đó**, không chỉ tương thích với giới hạn trên `T`. Java không thể chứng minh điều này cho một giá trị `T` bất kỳ.

Bài học này giải thích quy tắc kiểu, chứng minh lý do an toàn, cách đọc/ghi thực sự được phép, trường hợp `null`, và cách thiết kế API khi cần thêm dữ liệu.

## 2. `? extends T` thực sự có nghĩa gì?

Một tham chiếu `List<? extends Number>` có thể nhận `List<Integer>`, `List<Double>` hoặc `List<Number>`, nhưng **không công khai element type chính xác** ở chỗ sử dụng:

```java
List<Integer> ints = new ArrayList<>();
List<? extends Number> numbers = ints;
Number value = numbers.isEmpty() ? 0 : numbers.get(0);
```

`Number` là upper bound cho phép **đọc**, không phải giấy phép **chèn bất kỳ `Number` nào**. Trong bài này, ta sẽ chứng minh cụ thể compiler phải cấm ghi để không phá contract của `List<Integer>` hoặc `List<Double>`, kể cả khi caller biết object runtime đang là loại nào.

## 3. Chứng minh bằng phản ví dụ: thêm `T` sẽ phá an toàn kiểu

Giả sử trình biên dịch cho phép thêm một `Number` qua biến `List<? extends Number>`:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> view = integers;

// Giả định Java cho phép, nhưng thực tế dòng này KHÔNG biên dịch:
view.add(3.14);
```

`3.14` được boxing thành `Double`, là kiểu con của `Number`. Nó vẫn **không phải `Integer`**. Nếu phép thêm được chấp nhận, `integers` sẽ chứa `Double` trong khi mã nguồn khác tiếp tục tin rằng danh sách đó chỉ chứa `Integer`:

```java
// Mô phỏng hậu quả giả định; không phải chương trình Java hợp lệ.
Integer first = integers.get(0); // Dữ liệu thực là Double!
```

Vấn đề không chỉ xuất hiện khi thêm `Double`. Ngay cả `view.add(42)` cũng phải bị cấm, vì biến `view` có thể đang trỏ tới một `List<Double>`. Trình biên dịch không thể phán đoán dựa trên một loại giá trị cụ thể có vẻ “hợp lý” trong một trường hợp.

Do đó, với:

```java
static void cannotAdd(List<? extends Number> values) {
    values.add(Integer.valueOf(42)); // LỖI BIÊN DỊCH
    values.add(Double.valueOf(3.14)); // LỖI BIÊN DỊCH
    values.add((Number) Integer.valueOf(1)); // VẪN LỖI
}
```

Cả ba dòng đều không hợp lệ. Ép kiểu giá trị thành `Number` không giúp gì, bởi `Number` là giới hạn trên, không phải kiểu phần tử cụ thể đã biết của danh sách.

## 4. Vì sao đọc được dưới kiểu T nhưng ghi T lại không được?

Giả sử một danh sách có kiểu phần tử thực tế `U` với `U extends T`.

**Khi đọc:** mọi giá trị kiểu `U` đều là giá trị kiểu `T`, nên có thể đọc và sử dụng dưới kiểu `T`.

**Khi ghi:** một giá trị kiểu `T` bất kỳ không nhất thiết là `U`. Nó có thể là một kiểu con khác của `T`, nên không thể đưa vào danh sách chỉ nhận `U`.

```java
List<? extends Number> values = List.of(10, 20);

Number number = values.get(0); // ĐÚNG: phần tử chắc chắn là Number
Object object = values.get(0); // ĐÚNG: Number cũng là Object
Integer integer = values.get(0); // SAI: phần tử có thể là Double
values.add(number);             // SAI: Number chưa chắc đúng kiểu phần tử
```

Đây là một chiều thông tin có chủ đích: **giới hạn trên bảo đảm khả năng đọc**, không bảo đảm khả năng ghi giá trị mới.

Một ví dụ với hierarchy tự định nghĩa:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}

List<Dog> dogs = new ArrayList<>();
List<? extends Animal> animals = dogs;

Animal a = animals.get(0); // Hợp lệ về kiểu; sẽ lỗi chỉ số nếu list đang trống
animals.add(new Dog());    // LỖI BIÊN DỊCH
animals.add(new Cat());    // LỖI BIÊN DỊCH
animals.add(new Animal()); // LỖI BIÊN DỊCH
```

Ngay cả `new Dog()` cũng bị từ chối qua `animals`, bởi kiểu tĩnh của biến là `List<? extends Animal>`, không phải `List<Dog>`. Khi biết chính xác kiểu danh sách, hãy ghi qua biến có kiểu rõ ràng:

```java
dogs.add(new Dog()); // ĐÚNG
```

## 5. Wildcard capture: trình biên dịch đang kiểm tra điều gì?

Khi trình biên dịch sử dụng `List<? extends Number>`, nó có thể biểu diễn `?` bằng một kiểu tạm, thường được nói tới trong thông báo lỗi là **`CAP#1`** (*capture of ? extends Number*). Có thể hình dung:

```text
CAP#1 là kiểu phần tử chưa biết
CAP#1 <: Number

get(int)  : CAP#1
add(CAP#1): boolean
```

Đây là sơ đồ giải thích kiểu, không phải cú pháp Java. Vì `CAP#1` là kiểu con chưa biết của `Number`, trình biên dịch **không** có quy tắc cho phép đưa một `Number` hoặc `Integer` bất kỳ vào vị trí yêu cầu `CAP#1`.

Thông báo lỗi của trình biên dịch có thể đề cập:

```text
incompatible types: Integer cannot be converted to CAP#1
where CAP#1 is a fresh type-variable:
  CAP#1 extends Number from capture of ? extends Number
```

Cách trình bày lỗi cụ thể phụ thuộc bản JDK và biểu thức nguồn; ý nghĩa vẫn là kiểu giá trị định chèn chưa được chứng minh tương thích với kiểu phần tử đã capture.

Điều đáng lưu ý: kiểu tham số `T` trong `List<? extends T>` **không phải** kiểu `CAP#1`. `T` là **giới hạn trên**; `CAP#1` là kiểu phần tử cụ thể nhưng chưa biết nằm bên dưới giới hạn ấy.

### 5.1. Viết phương thức generic với T vẫn không cho phép thêm T

```java
static <T> void tryAdd(List<? extends T> target, T value) {
    target.add(value); // LỖI BIÊN DỊCH
}
```

Có thể truyền `List<Integer>` cùng một giá trị `Number` làm tham số để kiểu `T` được suy luận là `Number`, nhưng danh sách có thể chỉ nhận `Integer`. Việc đặt tên `T` cho giới hạn trên không khiến kiểu cụ thể bên dưới dấu `?` trở nên biết được.

Tương tự:

```java
static <T extends Number> void tryAddNumber(
        List<? extends T> list, T value) {
    list.add(value); // VẪN LỖI
}
```

Cách khai báo `<T extends Number>` chỉ giới hạn chính `T` trong họ `Number`; nó không xóa bỏ wildcard của `List<? extends T>`.

### 5.2. Biết đối tượng thực tế vẫn chưa đủ nếu biến bị khai báo bằng wildcard

```java
List<? extends Number> view = new ArrayList<Number>();
view.add(1); // LỖI BIÊN DỊCH
```

Mặc dù `new ArrayList<Number>()` nhận được `Integer`, kiểu được khai báo cho `view` vẫn là `List<? extends Number>`. Trình biên dịch kiểm tra lời gọi dựa trên **kiểu tĩnh của biểu thức nhận phương thức** và các quy tắc capture.

Nếu muốn ghi, giữ tham chiếu đúng kiểu:

```java
List<Number> numbers = new ArrayList<>();
List<? extends Number> readable = numbers;

numbers.add(1);    // ĐÚNG
// readable.add(1); // SAI
```

Cả hai tham chiếu trỏ cùng danh sách; sự khác nhau nằm ở khả năng mà từng **kiểu khai báo** cho phép mã nguồn sử dụng.

## 6. Có thật sự không thể thêm bất cứ thứ gì?

**Ngoại lệ quan trọng: `null`.** Trong Java, `null` có thể chuyển đổi sang bất kỳ kiểu tham chiếu nào, kể cả kiểu capture chưa biết:

```java
List<Integer> integers = new ArrayList<>();
List<? extends Number> view = integers;

view.add(null); // BIÊN DỊCH ĐƯỢC
```

Nếu đối tượng danh sách hỗ trợ thêm phần tử và cho phép `null`, thao tác thành công. Nhưng đây không phải cách thêm một giá trị `T` hữu ích:

- `null` không mang một đối tượng `Number` hoặc một giá trị số cụ thể.
- `List.of(...)` và các danh sách không hỗ trợ sửa đổi sẽ ném `UnsupportedOperationException` khi gọi `add(null)`.
- Một số triển khai hoặc hợp đồng tập hợp có thể từ chối `null` bằng ngoại lệ riêng.

Do đó cách nói chính xác là: **không thể thêm một giá trị khác `null` có kiểu `T` tùy ý qua `List<? extends T>`**; `add(null)` là trường hợp hợp lệ về mặt hệ thống kiểu, chưa chắc thành công khi chạy.

`set(index, value)` cũng có cùng giới hạn kiểu ở đối số mới:

```java
List<? extends Number> view = new ArrayList<Integer>(List.of(1, 2));

view.set(0, 5);    // LỖI BIÊN DỊCH
view.set(0, null); // BIÊN DỊCH ĐƯỢC nếu xét riêng dòng này
```

`set(0, null)` chỉ thành công nếu vị trí tồn tại và danh sách thực tế hỗ trợ thay thế, chấp nhận `null`. Chỉ số không hợp lệ có thể ném `IndexOutOfBoundsException`.

## 7. `? extends T` không đồng nghĩa với danh sách bất biến

Cấm ghi một `T` mới tùy ý **không** có nghĩa đối tượng nguồn immutable:

```java
List<Integer> ints = new ArrayList<>(List.of(1, 2, 3));
List<? extends Number> view = ints;
view.remove(1); // Biên dịch; xóa phần tử nếu list hỗ trợ.
view.clear();   // Biên dịch; không cần giá trị thuộc capture type.
```

Các thao tác này có thể ném `UnsupportedOperationException` với list không cho sửa. `Collections.swap` và helper generic capture cũng có thể di chuyển những phần tử **đã thuộc cùng list**. Đó là thao tác khác với chèn một `Number` mới. Bài riêng về **wildcard không làm đối tượng bất biến** phân tích alias, unmodifiable views và snapshots.

## 8. Vì sao helper generic có thể thêm lại phần tử đã đọc?

Đoạn sau có thể gây bất ngờ:

```java
static void cannotDuplicate(List<? extends Number> values) {
    values.add(values.get(0)); // LỖI BIÊN DỊCH
}
```

Dù `get(0)` và `add(...)` cùng được gọi trên `values`, Java có thể capture các lần sử dụng wildcard ở những vị trí kiểu khác nhau. Trình biên dịch không bảo đảm giá trị đọc trong biểu thức này được xem như chính kiểu tham số mà `add` yêu cầu.

Một phương thức helper kiểu `<E>` có thể giữ **cùng một kiểu phần tử E** trong toàn bộ thân phương thức:

```java
static <E> void duplicateFirst(List<E> values) {
    if (!values.isEmpty()) {
        E first = values.get(0);
        values.add(first); // ĐÚNG: cùng E
    }
}

static void caller(List<? extends Number> source) {
    duplicateFirst(source); // ĐÚNG: capture wildcard thành E tại lời gọi
}
```

Điều này an toàn vì giá trị được thêm **đến từ chính danh sách và giữ đúng kiểu E**. `duplicateFirst` không tự tạo một `Number` tùy ý. Nếu nguồn là `List<Integer>`, helper nhận `E` tương ứng với kiểu phần tử đó; nếu là `List<Double>`, nó giữ kiểu `Double`.

Helper chỉ giải quyết kiểm tra kiểu; nếu danh sách không hỗ trợ `add`, lời gọi vẫn ném `UnsupportedOperationException`.

Đừng dùng raw `List` hoặc ép kiểu unchecked để “đánh lừa” compiler. Những cách đó có thể khiến phần tử sai loại lọt vào danh sách và gây lỗi `ClassCastException` khi đọc sau này.

## 9. Khi muốn thực sự ghi T, thiết kế API thế nào?

### 9.1. Dùng `List<T>` khi cần đúng cùng một kiểu

Nếu phương thức cần bảo đảm giá trị mới cùng kiểu phần tử:

```java
static <T> void append(List<T> target, T value) {
    target.add(value);
}
```

Ví dụ:

```java
List<Integer> integers = new ArrayList<>();
append(integers, 10); // Hợp lệ: T là Integer
```

Kiểu `T` trong `List<T>` là cùng tham số kiểu của giá trị `value`; danh sách không chứa wildcard chưa biết trong chữ ký phương thức. Phương thức này vẫn phụ thuộc danh sách có hỗ trợ `add` lúc chạy hay không.

### 9.2. Dùng `List<? super T>` khi danh sách là nơi nhận giá trị T

Nếu một phương thức được thiết kế để ghi phần tử `T` vào đích, wildcard **giới hạn dưới** phù hợp:

```java
static <T> void appendTo(List<? super T> target, T value) {
    target.add(value); // Hợp lệ về kiểu
}
```

Với `T` là `Integer`, đích có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`: tất cả đều chấp nhận một `Integer`. Đây là điều ngược với `List<? extends T>`, vốn có thể trỏ tới danh sách của một kiểu con hẹp hơn mà `T` không được phép chèn vào.

Ví dụ:

```java
List<Number> numbers = new ArrayList<>();
appendTo(numbers, Integer.valueOf(7));
appendTo(numbers, Double.valueOf(2.5));
```

### 9.3. Dùng `extends` cho nguồn đọc và `super` cho đích ghi

Chữ ký thường gặp khi chuyển phần tử:

```java
static <T> void transfer(
        List<? extends T> source,
        List<? super T> destination) {
    for (T value : source) {
        destination.add(value);
    }
}
```

Ví dụ gọi với `List<Integer>` và `List<Number>` hợp lệ. `source` chỉ cần bảo đảm mỗi phần tử đọc được là `T`; `destination` bảo đảm tiếp nhận được `T`.

Đây là quy tắc **PECS (Producer Extends, Consumer Super)**:

- **Producer `? extends T`**: cung cấp giá trị đọc được dưới dạng `T`.
- **Consumer `? super T`**: nhận giá trị kiểu `T` để ghi.

PECS hướng dẫn lựa chọn chữ ký API theo cách sử dụng dữ liệu. Nó không có nghĩa một danh sách `extends` là bất biến về nội dung hoặc danh sách `super` luôn hỗ trợ sửa đổi.

## 10. Chương trình Java 17+ đầy đủ

Lưu tệp `ExtendsWriteDemo.java` với nội dung:

```java
import java.util.ArrayList;
import java.util.List;

public class ExtendsWriteDemo {
    // Giữ một kiểu E cho cả phần tử đọc và phần tử thêm vào.
    static <E> void duplicateFirst(List<E> list) {
        if (!list.isEmpty()) {
            E first = list.get(0);
            list.add(first);
        }
    }

    // Kiểu T được bảo đảm phù hợp với danh sách đích.
    static <T> void appendTo(List<? super T> target, T value) {
        target.add(value);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(10, 20));
        List<? extends Number> source = integers;

        Number read = source.get(0);
        System.out.println("Read: " + read);

        // source.add(30); // Lỗi biên dịch nếu bỏ dấu chú thích.
        duplicateFirst(source);
        System.out.println("Same list: " + integers);

        List<Number> destination = new ArrayList<>();
        appendTo(destination, 3.5);
        System.out.println("Destination: " + destination);

        try {
            List<? extends Number> unmodifiable = List.of(1, 2);
            unmodifiable.add(null); // Hợp lệ về kiểu nhưng không sửa được List.of.
        } catch (UnsupportedOperationException e) {
            System.out.println(
                    "Unmodifiable: " + e.getClass().getSimpleName());
        }
    }
}
```

Trong thư mục chứa tệp, biên dịch và chạy:

```bash
javac -encoding UTF-8 ExtendsWriteDemo.java
java ExtendsWriteDemo
```

Đầu ra:

```text
Read: 10
Same list: [10, 20, 10]
Destination: [3.5]
Unmodifiable: UnsupportedOperationException
```

Phân tích:

1. `source.get(0)` trả giá trị đọc được dưới kiểu `Number`.
2. `source.add(30)` được chú thích vì không thể biên dịch với `List<? extends Number>`.
3. `duplicateFirst(source)` hợp lệ vì helper capture cùng một kiểu `E` và lấy phần tử từ chính danh sách. Nó thay đổi đối tượng `integers`, vì `source` và `integers` cùng tham chiếu tới đối tượng đó.
4. `appendTo` có đích `List<? super T>`, nên có thể thêm giá trị thực.
5. `List.of` từ chối sửa đổi ở runtime. Điều này độc lập với việc `add(null)` hợp lệ về kiểu.

## 11. Sai lầm thường gặp

| Nhận định hoặc cách viết | Kết luận | Lý do |
| --- | --- | --- |
| “`? extends Number` nghĩa là thêm được mọi `Number`” | Sai | Kiểu phần tử thực tế có thể chỉ là `Integer` hoặc `Double` |
| `list.add((Number) 1)` qua `List<? extends Number>` | Không biên dịch | Ép thành `Number` không chứng minh tương thích với kiểu capture |
| “Danh sách thực tế là `ArrayList<Number>` nên biến wildcard thêm được” | Sai | Kiểm tra ở compile-time dựa trên kiểu tĩnh `List<? extends Number>` |
| `list.add(null)` | Biên dịch được | `null` tương thích với kiểu tham chiếu chưa biết; runtime vẫn có thể từ chối |
| “Wildcard `extends` đồng nghĩa immutable” | Sai | Một số thao tác xóa/sắp xếp lại có thể hợp lệ và chạy được |
| `list.add(list.get(0))` với biến wildcard | Có thể không biên dịch | Kiểu capture ở hai vị trí không được buộc là một |
| Helper `<E>` nhận `List<E>` rồi thêm phần tử vừa đọc | Hợp lệ | Cùng một `E` kiểm soát cả đọc và ghi |
| Ghi `T` vào `List<? super T>` | Hợp lệ về kiểu | Đích nhận được bất kỳ giá trị `T` nào |
| Dùng raw `List` để thêm giá trị không hợp kiểu | Không an toàn | Bỏ qua kiểm tra kiểu, dễ gây lỗi khi đọc |

### Gợi ý đọc lỗi biên dịch

Khi gặp lỗi liên quan `CAP#1` hay “capture of `? extends ...`”, hãy tự hỏi: “Tôi đang đưa một giá trị **bên ngoài** vào nơi yêu cầu đúng một kiểu con chưa biết phải không?” Nếu có, hãy xem API của bạn cần `List<T>`, `List<? super T>`, hay chỉ cần dùng helper để thao tác với **các phần tử đã có**.

## 12. Bài tập tự kiểm tra

Xét riêng từng đoạn sau với `import java.util.*;`. Hãy xác định biên dịch được không, và nếu được thì có chắc chạy thành công không.

**A — Đọc nguồn**

```java
List<? extends Number> a = List.of(1, 2, 3);
Number value = a.get(0);
```

**B — Thêm kiểu con**

```java
List<? extends Number> b = new ArrayList<Integer>();
b.add(4);
```

**C — Thêm chính giới hạn trên**

```java
List<? extends Number> c = new ArrayList<Number>();
c.add((Number) 4);
```

**D — Thêm null**

```java
List<? extends Number> d = new ArrayList<Integer>();
d.add(null);
System.out.println(d.size());
```

**E — Ghi qua giới hạn dưới**

```java
List<? super Integer> e = new ArrayList<Number>();
e.add(4);
```

**F — Dùng helper capture**

```java
static <E> void copyFirst(List<E> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
List<? extends Number> f = new ArrayList<>(List.of(1, 2));
copyFirst(f);
```

Đoạn F là hai khai báo đặt trong một lớp hoặc ngữ cảnh khai báo phương thức hợp lệ; không thể khai báo phương thức `static` tự do giữa các câu lệnh trong cùng phương thức `main`.

**Đáp án:**

- **A:** Biên dịch được; đọc `Number` an toàn.
- **B:** Không biên dịch; `Integer` không được chứng minh là kiểu phần tử capture của `b`.
- **C:** Không biên dịch; dù đối tượng thực sự là `ArrayList<Number>`, biến `c` có kiểu wildcard.
- **D:** Biên dịch và chạy với `ArrayList`; in `1`. Không thể suy mọi triển khai `List` khác cũng cho phép `add(null)`.
- **E:** Biên dịch; `List<? super Integer>` nhận được giá trị `Integer`. Đối tượng `ArrayList<Number>` hỗ trợ thêm nên thao tác thành công.
- **F:** Biên dịch; helper dùng cùng tham số `E` cho `get` và `add`. Đối tượng nguồn `ArrayList` hỗ trợ thay đổi nên thao tác thành công.

## 13. Ghi nhớ

`List<? extends T>` là danh sách của **một kiểu con chưa biết của T**. Đọc ra một `T` là an toàn vì mọi phần tử đều thuộc `T`; thêm một `T` tùy ý là không an toàn vì giá trị ấy có thể không thuộc kiểu phần tử thực tế. `null` là ngoại lệ hợp lệ về mặt kiểu, nhưng runtime có thể từ chối thao tác.

Khi thiết kế API: dùng `? extends T` cho nguồn đọc, `? super T` cho đích ghi, và `List<T>` hoặc helper generic khi cần liên kết chính xác kiểu phần tử đang đọc với kiểu phần tử sẽ ghi.
