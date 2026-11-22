# Phân biệt giới hạn dưới của wildcard với giới hạn của tham số kiểu trong Java Generics

## 1. Vấn đề: hai cách nói “giới hạn kiểu” không tương đương

Khi đọc chữ ký Java generics, ta thường gặp hai cấu trúc:

```java
List<? super Integer> destination;
<T extends Number> void process(T value) { /* ... */ }
```

Cả hai đều sử dụng từ ngữ “giới hạn” (*bound*), nhưng chúng áp dụng cho **hai đối tượng ngữ pháp khác nhau**:

- `? super Integer` là **wildcard có giới hạn dưới** (*lower-bounded wildcard*) ở **vị trí đối số kiểu**; nó diễn đạt một kiểu phần tử chưa biết nhưng là kiểu `Integer` hoặc một **kiểu cha của `Integer`**.
- `<T extends Number>` là **khai báo tham số kiểu có giới hạn trên** (*upper-bounded type parameter*); nó đặt tên cho một kiểu `T` mà trình biên dịch phải biết là `Number` hoặc **kiểu con của `Number`** trong phạm vi khai báo.

Điểm quan trọng: Java **không hỗ trợ cú pháp khai báo tham số kiểu có giới hạn dưới** như `<T super Integer>`. Từ khóa `super` xuất hiện hợp lệ trong giới hạn dưới của **wildcard**, còn tham số kiểu khai báo bằng `<T extends ...>` dùng giới hạn trên.

Bài này tập trung phân biệt ý nghĩa, cú pháp, cách suy luận kiểu và tác dụng khi đọc/ghi dữ liệu; nó không đánh đồng tham số kiểu `T` với wildcard `?`.

## 2. Phân biệt hình thức: type parameter và wildcard

### 2.1. Tham số kiểu là một tên kiểu có thể dùng lại

Trong phương thức sau, `T` là **tham số kiểu** được khai báo và có thể xuất hiện ở nhiều vị trí:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

- `<T extends Number>` **khai báo** `T`, đồng thời ràng buộc `T` phải là một kiểu thích hợp với `Number`.
- `T value` và kiểu trả về `T` cùng tham chiếu tới **một tham số kiểu được đặt tên**.
- Trong thân phương thức, có thể gọi những thao tác được bảo đảm bởi giới hạn trên, chẳng hạn `value.doubleValue()`.
- Ở mỗi lần gọi, trình biên dịch suy luận hoặc kiểm tra đối số kiểu phù hợp (ví dụ `Integer`, `Double`).

`extends` trong giới hạn tham số kiểu bao gồm cả **kế thừa lớp** và **triển khai interface**:

```java
static <T extends CharSequence> int sizeOf(T text) {
    return text.length();
}
```

`CharSequence` là interface, nhưng từ khóa vẫn là `extends`, không phải `implements`.

Giới hạn còn có thể là giao (*intersection*) của nhiều yêu cầu:

```java
static <T extends Number & Comparable<T>> int compare(T a, T b) {
    return a.compareTo(b);
}
```

Nếu có lớp trong danh sách giới hạn, lớp phải đứng trước các interface. Đây vẫn là **giới hạn trên** đối với `T`.

### 2.2. Wildcard biểu diễn một kiểu chưa biết tại vị trí sử dụng

Khác với khai báo `T`, wildcard không đặt tên kiểu để sử dụng độc lập:

```java
List<? super Integer> receiver = new ArrayList<Number>();
```

Ở đây, dấu `?` là **đối số kiểu** của `List<...>`. Danh sách thực tế có thể được khai báo với `Integer` hoặc một kiểu cha phù hợp của `Integer`; mã sử dụng `receiver` **không biết chính xác** tham số kiểu của danh sách.

`? super Integer` khác với `? extends Integer`:

- `? super Integer`: kiểu phần tử chưa biết là **`Integer` hoặc kiểu cha của `Integer`**; an toàn để **ghi `Integer`**.
- `? extends Integer`: kiểu phần tử chưa biết là **`Integer` hoặc kiểu con của `Integer`**; an toàn để **đọc thành `Integer`**. `Integer` là `final`, nên ví dụ với nó ít thể hiện sự đa dạng của kiểu con, nhưng quy tắc vẫn áp dụng.

Khi gọi phương thức trên `List<? super Integer>`, trình biên dịch có thể tạo một kiểu capture nội bộ cho wildcard. Capture đó có giới hạn dưới là `Integer` và được bảo đảm có giới hạn trên `Object`. Không thể biến wildcard `?` thành một tên kiểu `T` rồi sử dụng tùy tiện ở các khai báo khác.

### 2.3. Bảng đối chiếu

| Thuộc tính | `List<? super Integer>` | `<T extends Number>` |
| --- | --- | --- |
| Đối tượng bị ràng buộc | Wildcard làm **đối số kiểu** của `List` | **Tham số kiểu được khai báo** tên `T` |
| Hướng giới hạn | **Dưới**: kiểu phần tử chưa biết là kiểu cha hoặc chính `Integer` | **Trên**: `T` là kiểu con hoặc chính `Number` |
| Vị trí xuất hiện | Trong kiểu tham số hóa, ví dụ `List<? super Integer>` | Trong khai báo lớp, interface, phương thức hoặc constructor generic |
| Có tên để liên hệ nhiều vị trí? | Không có tên trực tiếp; có thể dùng helper để capture | Có: cùng một `T` có thể lặp lại ở tham số, biến, kiểu trả về |
| Giá trị có thể đưa vào danh sách | Qua biến `List<? super Integer>`, có thể thêm `Integer` (và subtype tương ứng) | Chỉ riêng giới hạn `T extends Number` **không nói** có danh sách nào để thêm |
| Giá trị lấy ra | Với `List<? super Integer>`, chỉ chắc chắn nhận được `Object` | Với giá trị `T`, ít nhất có thể sử dụng nó như `Number` |
| Cú pháp tương ứng đối lập | `? extends Integer` là wildcard giới hạn trên | `<T super Integer>` **không hợp lệ** trong Java |

Ký hiệu “kiểu cha” ở đây bao gồm những **supertype** hợp lệ theo hệ thống kiểu Java, kể cả interface. Chẳng hạn `List<Number>`, `List<Object>` và các kiểu `List` với tham số là supertype thích hợp của `Integer` đều có thể được dùng tại vị trí `List<? super Integer>`. Không nên hiểu rằng chỉ có chính xác ba lựa chọn `Integer`, `Number`, `Object`.

## 3. `? super T` tạo ra giới hạn dưới như thế nào?

Xét:

```java
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> targetA = numbers; // Đúng
List<? super Integer> targetB = objects; // Đúng
```

Ở trường hợp `targetA`, danh sách thật nhận `Number`. Ở `targetB`, danh sách thật nhận `Object`. Cả hai loại đều **chấp nhận một `Integer`**, vì mọi `Integer` đồng thời là một `Number` và một `Object`.

Các thao tác hợp lệ về kiểu:

```java
targetA.add(Integer.valueOf(10));
targetB.add(20); // int được boxing thành Integer
targetA.set(0, Integer.valueOf(30)); // Cần chỉ số hợp lệ và List hỗ trợ set
```

Ngược lại:

```java
targetA.add(3.14);                 // LỖI BIÊN DỊCH: Double không bảo đảm phù hợp
targetB.add(new Object());        // LỖI BIÊN DỊCH: Object không chắc là Integer
Integer n = targetA.get(0);       // LỖI BIÊN DỊCH: chỉ biết chắc Object
Object value = targetA.get(0);    // Hợp lệ nếu danh sách không rỗng
```

**Tại sao đọc ra chỉ an toàn dưới dạng `Object`?** Vì kiểu phần tử thực tế có thể là `Object`, và một `List<Object>` còn có thể chứa `String`, `Double` hoặc bất kỳ đối tượng khác bên cạnh các `Integer` đã thêm. Giới hạn dưới đảm bảo điều kiện **đưa `Integer` vào**, không bảo đảm mọi phần tử có thể đọc ra là `Integer`.

Lưu ý về `set`: ngoài an toàn kiểu, vị trí cần tồn tại và đối tượng `List` phải hỗ trợ thay thế. `? super Integer` không biến một danh sách không thể sửa đổi thành danh sách có thể sửa đổi.

## 4. `<T extends Number>` ràng buộc một kiểu được đặt tên

Thử phương thức chỉ thao tác với một `T`:

```java
static <T extends Number> double twice(T value) {
    return value.doubleValue() * 2;
}
```

`T` được giới hạn bởi `Number`, nên có thể gọi `doubleValue()`. Phương thức chấp nhận `Integer`, `Long`, `Double` và những kiểu phù hợp khác. Nhưng nó **không** tạo quan hệ đặc biệt giữa `List<Integer>` và `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // LỖI BIÊN DỊCH: generic vẫn bất biến
```

Quan trọng hơn: ngay cả khi có `T extends Number`, việc thêm phần tử vẫn cần đúng `T`:

```java
static <T extends Number> void put(List<T> list, T value) {
    list.add(value); // Đúng: tham số kiểu của list và value cùng là T
}
```

Không thể chỉ biết `T extends Number` rồi tùy ý thêm một `Double`:

```java
static <T extends Number> void wrong(List<T> list) {
    list.add(3.14); // LỖI BIÊN DỊCH: T có thể là Integer
}
```

Cùng một tên `T` giữ quan hệ nhất quán giữa nhiều vị trí. Phương thức `put` có thể nhận `List<Integer>` với `Integer`, hoặc `List<Double>` với `Double`. Giới hạn trên không đồng nghĩa mọi giá trị kiểu `Number` đều có thể đưa vào một `List<T>` bất kỳ.

## 5. Vì sao không có cú pháp `<T super Integer>`?

Các khai báo sau **sai cú pháp Java**:

```java
// KHÔNG biên dịch:
class InvalidBox<T super Integer> { }
static <T super Number> void invalid(T value) { }
```

Java chỉ có cú pháp giới hạn trên ở phần **khai báo tham số kiểu**, ví dụ:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Nếu API muốn nhận danh sách có tham số kiểu là `Integer` hoặc kiểu cha của `Integer`, hãy viết giới hạn dưới **ở vị trí sử dụng kiểu**:

```java
static void appendInteger(List<? super Integer> target) {
    target.add(42);
}
```

Hoặc vừa đặt tên kiểu `T`, vừa dùng wildcard giới hạn dưới:

```java
static <T> void append(List<? super T> target, T value) {
    target.add(value);
}
```

Đây là hai lớp ràng buộc khác nhau: `T` liên kết với kiểu của `value`; `? super T` bảo đảm **đích** nhận được các giá trị kiểu `T`.

**Phân biệt với suy luận kiểu:** trong quá trình *type inference*, trình biên dịch có thể dùng những quan hệ ràng buộc kiểu “dưới” hoặc “trên” để giải hệ suy luận. Điều đó không tạo ra cú pháp khai báo mới `<T super X>` trong mã nguồn Java.

## 6. Dùng cả giới hạn trên của T và giới hạn dưới wildcard trong cùng một API

Đây là tình huống rất thường gặp:

```java
static <T extends Number> void copyNumbers(
        List<? super T> destination,
        List<? extends T> source) {
    for (T number : source) {
        destination.add(number);
    }
}
```

Phân tích từng phần:

1. `<T extends Number>`: `T` là kiểu số hợp lệ; có thể dùng các thao tác do `Number` cung cấp.
2. `List<? extends T> source`: **nguồn đọc** có kiểu phần tử là `T` hoặc một kiểu con của `T`; mỗi phần tử đọc ra có thể được xử lý như `T`.
3. `List<? super T> destination`: **đích ghi** có kiểu phần tử là `T` hoặc một kiểu cha của `T`; có thể thêm an toàn mỗi giá trị `T`.
4. `for (T number : source)`: phần tử từ nguồn an toàn để đọc thành `T`, rồi có thể truyền vào `destination.add(number)`.

Ví dụ:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

copyNumbers(numbers, integers); // Đúng
copyNumbers(objects, integers); // Đúng
```

Một lời gọi không hợp lệ:

```java
List<Double> doubles = new ArrayList<>();
copyNumbers(doubles, integers); // LỖI BIÊN DỊCH
```

`List<Double>` không phải đích phù hợp để nhận các phần tử `Integer` từ nguồn này. Trình biên dịch không thể tìm một `T` thỏa đồng thời các quan hệ kiểu mà cả hai tham số yêu cầu.

Có thể viết `<T>` mà không giới hạn `extends Number` nếu phương thức chỉ cần sao chép đối tượng bất kỳ:

```java
static <T> void copyAll(
        List<? super T> destination,
        List<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}
```

Ở đây, giới hạn trên `Number` không cần thiết. Chỉ khai báo những ràng buộc mà thân phương thức hoặc hợp đồng API thật sự cần.

### PECS là cách nhớ hướng sử dụng

**PECS: Producer Extends, Consumer Super.**

- `? extends T` phù hợp cho nguồn cung cấp phần tử để **đọc như T**.
- `? super T` phù hợp cho đích tiêu thụ phần tử để **ghi T**.

PECS là quy tắc thiết kế chữ ký generic, không phải quy tắc cho rằng mọi nguồn `extends` đều không thể sửa đổi hoặc mọi đích `super` chắc chắn sửa được tại runtime.

## 7. Biểu đồ phạm vi kiểu

Giả sử:

```text
Object
  ↑
Number
  ↑
Integer
```

Mũi tên hướng từ kiểu con lên kiểu cha.

Đối với một biến có kiểu `List<? super Integer>`:

```text
Danh sách thực tế có thể nhận:
    List<Integer>
    List<Number>
    List<Object>
    ... hoặc List<supertype phù hợp khác của Integer>

Giá trị an toàn để thêm: Integer (hoặc giá trị kiểu con của Integer)
Kiểu bảo đảm khi đọc: Object
```

Ví dụ `Integer` là lớp `final` nên không có lớp con thực tế nào của nó; cách diễn đạt “hoặc kiểu con” là quy tắc tổng quát khi `T` không phải `final`.

Đối với khai báo `<T extends Number>`:

```text
Kiểu T được chọn:
    Number
    Integer
    Double
    Long
    ... kiểu con phù hợp khác của Number

Có thể dùng giá trị T dưới dạng Number.
Một List<T> chỉ nhận những giá trị được chứng minh tương thích với T.
```

Hai tập quan hệ nằm về **hai hướng khác nhau** đối với bound. Một bên nói về kiểu phần tử ẩn của **vị trí nhận dữ liệu**; bên kia nói về những kiểu cụ thể được phép gán cho **tham số kiểu có tên**.

## 8. Ví dụ Java 17+ độc lập, biên dịch và chạy được

Tạo file `LowerBoundDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LowerBoundDemo {
    // T bị giới hạn trên bởi Number.
    // Wildcard đích bị giới hạn dưới bởi T.
    static <T extends Number> void copyNumbers(
            List<? super T> destination,
            List<? extends T> source) {
        for (T number : source) {
            destination.add(number);
        }
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(4, 8);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        copyNumbers(numbers, ids);
        copyNumbers(objects, ids);
        System.out.println("Numbers: " + numbers);
        System.out.println("Objects: " + objects);

        List<? super Integer> sink = numbers;
        sink.add(12);
        System.out.println("After add: " + numbers);

        Object first = sink.get(0);
        System.out.println("Read as Object: " + first);

        List<? super Number> broadSink = objects;
        broadSink.add(3.5);
        System.out.println("Objects after double: " + objects);
    }
}
```

Biên dịch và chạy trong thư mục có file:

```bash
javac -encoding UTF-8 LowerBoundDemo.java
java LowerBoundDemo
```

Đầu ra chính xác:

```text
Numbers: [4, 8]
Objects: [4, 8]
After add: [4, 8, 12]
Read as Object: 4
Objects after double: [4, 8, 3.5]
```

Giải thích:

- `copyNumbers(numbers, ids)` và `copyNumbers(objects, ids)` đều hợp lệ: danh sách đích có tham số kiểu đủ rộng để tiếp nhận phần tử nguồn.
- `List<? super Integer> sink = numbers` cho phép thêm `12` vì `12` được boxing thành `Integer`.
- `sink.get(0)` chỉ có kiểu được bảo đảm là `Object`; danh sách thực tế tình cờ đang chứa số `4`, nhưng compiler không suy ngược kiểu phần tử từ nội dung runtime.
- `List<? super Number> broadSink = objects` cho phép thêm `Double` vì `Double` là `Number` và đích có thể chứa `Number`.

Chương trình không chứa ép kiểu unchecked hay raw type.

## 9. Ví dụ về lỗi thường gặp

### 9.1. Lấy `? super T` làm giới hạn trên của T

```java
// Không hợp lệ: wildcard không thể đứng trực tiếp tại vị trí bound của T.
static <T extends ? super Number> void broken(T x) {}
```

Tham số kiểu được khai báo với **một kiểu giới hạn trên hợp lệ**, không được khai báo bằng wildcard kiểu này. Nếu cần chức năng “đích nhận số”, đặt `? super Number` vào vị trí đối số kiểu của danh sách:

```java
static void addNumber(List<? super Number> list, Number value) {
    list.add(value);
}
```

### 9.2. Nhầm `List<? super Integer>` là `List<Integer>`

```java
List<? super Integer> values = new ArrayList<Object>();
values.add(1);          // Hợp lệ
Integer n = values.get(0); // LỖI BIÊN DỊCH
```

Danh sách thật có thể là `List<Object>` chứa nhiều đối tượng không phải `Integer`. Không thể rút ra `Integer` chỉ từ giới hạn dưới.

### 9.3. Nhầm giới hạn trên của T làm quyền ghi Number

```java
static <T extends Number> void wrong(List<T> values) {
    values.add(3.5); // LỖI BIÊN DỊCH: T có thể là Integer
}
```

Khi cần thêm `Double` cụ thể, hãy nhận `List<? super Double>` hoặc `List<Double>`. Khi cần giữ cùng kiểu `T`, hãy nhận thêm tham số kiểu `T value`.

### 9.4. Nghĩ `super` làm generic “hiệp biến”

```java
List<Integer> ids = new ArrayList<>();
List<Number> numbers = ids; // LỖI BIÊN DỊCH
List<? super Integer> target = ids; // Hợp lệ
```

`List<Integer>` và `List<Number>` vẫn **bất biến** theo tham số kiểu. Wildcard chỉ tạo một **kiểu nhận tham chiếu linh hoạt** với bảo đảm đọc/ghi thích hợp.

### 9.5. Đổi tên T nhưng không liên hệ các vị trí

```java
static <A, B> void unsafe(
        List<? super A> destination, B value) {
    // destination.add(value); // Không thể biên dịch: A và B không có quan hệ.
}
```

Tên tham số kiểu khác nhau không tự tạo quan hệ. Nếu mục tiêu là thêm `value`, hãy dùng cùng `T`:

```java
static <T> void safe(List<? super T> destination, T value) {
    destination.add(value);
}
```

### 9.6. Đánh đồng an toàn kiểu và khả năng sửa đổi

```java
List<? super Integer> target = List.of(1, 2);
target.add(3); // Biên dịch, nhưng ném UnsupportedOperationException
```

Wildcard giới hạn dưới chứng minh kiểu phần tử **phù hợp để chèn**. Nó không bảo đảm đối tượng danh sách cho phép thay đổi.

## 10. Tự kiểm tra

Giả sử đã `import java.util.*;`. Với từng đoạn độc lập, cho biết **biên dịch được hay không**, và nếu được, kiểu nào được bảo đảm khi đọc.

**A — Wildcard super nhận đích rộng**

```java
List<? super Integer> a = new ArrayList<Number>();
a.add(10);
Object x = a.get(0);
```

**B — Đọc thành Integer**

```java
List<? super Integer> b = new ArrayList<Object>();
Integer x = b.get(0);
```

**C — Tham số kiểu có giới hạn dưới**

```java
class Box<T super Integer> {}
```

**D — Tham số kiểu có giới hạn trên**

```java
static <T extends Number> double toDouble(T x) {
    return x.doubleValue();
}
```

**E — Ghi Number vào List<? super Integer>**

```java
List<? super Integer> e = new ArrayList<Number>();
Number n = 3.5;
e.add(n);
```

**F — Ghi Integer vào List<? super Number>**

```java
List<? super Number> f = new ArrayList<Object>();
f.add(3);
```

**G — Phối hợp type parameter và wildcard**

```java
static <T extends Number> void store(
        List<? super T> target, T value) {
    target.add(value);
}
List<Object> objects = new ArrayList<>();
store(objects, Integer.valueOf(9));
```

Trong ví dụ D và G, các phương thức `static` phải được khai báo trong một lớp hoặc ngữ cảnh phù hợp; đây là mảnh mã minh họa, không phải tệp Java chạy độc lập.

**Đáp án:**

- **A:** Hợp lệ; thêm `Integer` vào danh sách chấp nhận `Integer`, đọc an toàn dưới kiểu `Object`.
- **B:** Không biên dịch: `get` trả về kiểu chỉ được bảo đảm là `Object`.
- **C:** Không biên dịch: Java không có cú pháp `<T super ...>`.
- **D:** Hợp lệ khi đặt trong khai báo lớp thích hợp; `T` bị giới hạn trên bởi `Number`, cho phép gọi `doubleValue()`.
- **E:** Không biên dịch: một `Number` bất kỳ có thể là `Double`, trong khi `List<? super Integer>` có thể trỏ tới `List<Integer>`.
- **F:** Hợp lệ: `Integer` là `Number` và mọi danh sách `List<? super Number>` đều nhận được `Number`.
- **G:** Hợp lệ: `T` có thể được suy luận là `Integer` (hoặc kiểu phù hợp), còn `List<Object>` là đích có khả năng chứa giá trị đó.

## 11. Ghi nhớ

**`? super T` là giới hạn dưới của wildcard tại vị trí đối số kiểu**: biểu diễn một kiểu phần tử chưa biết nhưng đủ rộng để nhận các giá trị `T`; đọc ra chỉ bảo đảm `Object`. **`<T extends U>` là giới hạn trên của tham số kiểu được đặt tên**: ràng buộc `T` thuộc họ `U` và cho phép liên kết nhiều vị trí trong cùng một khai báo.

Java không hỗ trợ `<T super U>` ở vị trí khai báo tham số kiểu. Khi cần cả hai cơ chế, dùng cú pháp kết hợp như `<T extends Number> void copy(List<? super T> dest, List<? extends T> src)` để mô tả chính xác giá trị được đọc từ nguồn và được chấp nhận bởi đích.
