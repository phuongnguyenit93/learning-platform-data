# Kiểu tĩnh của biểu thức nguồn và kiểu của pattern variable

## 1. Hai kiểu khác nhau trong một biểu thức `instanceof`

Khi đọc một type pattern như:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

cần phân biệt hai khái niệm:

- **Kiểu tĩnh của biểu thức nguồn** (`value`) là kiểu mà trình biên dịch biết tại thời điểm biên dịch. Trong ví dụ này, kiểu tĩnh là `Object`, vì biến được khai báo là `Object`.
- **Kiểu của pattern variable** (`text`) là kiểu được ghi trong pattern. Ở đây, `text` có kiểu tĩnh là `String`.

Khi chương trình chạy, đối tượng thực tế mà `value` tham chiếu đến là một `String`. Phép kiểm tra xác nhận đối tượng đó có khớp với `String` hay không. Nếu khớp, biến `text` tham chiếu đến **chính đối tượng đó**, nhưng được trình biên dịch nhìn nhận dưới kiểu `String`.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Kiểu tĩnh của biểu thức nguồn | `Object` | Kiểu được xác định khi biên dịch từ khai báo và biểu thức |
| Kiểu pattern | `String` | Kiểu mà phép kiểm tra yêu cầu đối tượng khớp |
| Kiểu tĩnh của pattern variable | `String` | Kiểu dùng để kiểm tra các thao tác gọi trên biến `text` |
| Kiểu thực tế lúc chạy | `String` | Lớp thực tế của đối tượng đang được tham chiếu trong ví dụ |

Type pattern được chuẩn hóa trong Java 16 theo JEP 394. Việc khai báo pattern variable không tạo bản sao đối tượng, không chuyển đổi nội dung và không thay đổi kiểu khai báo của biến nguồn.

## 2. Kiểu tĩnh của biểu thức nguồn quyết định pattern nào có thể dùng

Trình biên dịch không chỉ nhìn vào giá trị hiện tại. Nó kiểm tra kiểu tĩnh của biểu thức nguồn để xác định phép kiểm tra có khả thi hay không.

### 2.1. Nguồn có kiểu tổng quát

```java
Object data = "Xin chào";

if (data instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

`data` có kiểu tĩnh là `Object`, nên có thể tham chiếu đến một đối tượng `String` hoặc nhiều kiểu tham chiếu khác. Pattern `String text` là một trường hợp cụ thể cần kiểm tra lúc chạy. Nếu đối tượng thực tế là chuỗi, pattern khớp và `text` có kiểu `String`.

### 2.2. Nguồn có kiểu giao diện

```java
CharSequence content = new StringBuilder("Java");

if (content instanceof StringBuilder builder) {
    builder.append(" 16");
}
```

Kiểu tĩnh của `content` là `CharSequence`, không phải `StringBuilder`. Giao diện `CharSequence` có thể được triển khai bởi nhiều lớp, trong đó có `StringBuilder`. Vì vậy, phép kiểm tra có ý nghĩa: chỉ khi đối tượng thực tế là `StringBuilder`, biến `builder` mới được cung cấp.

### 2.3. Cùng đối tượng nhưng kiểu tĩnh khác nhau

```java
Object first = "Java";
var second = "Java"; // var suy luận kiểu String

if (first instanceof String text) {
    System.out.println(text.length()); // Hợp lệ
}

// Không hợp lệ: kiểu tĩnh của second đã là String,
// nên pattern String luôn khớp.
// if (second instanceof String text) {
//     System.out.println(text.length());
// }
```

Hai biến có thể tham chiếu đến những đối tượng cùng lớp lúc chạy, nhưng kiểu tĩnh khác nhau. `first` được khai báo là `Object`, còn `second` được suy luận thành `String`. Chính kiểu tĩnh này ảnh hưởng đến tính hợp lệ của pattern khi biên dịch.

## 3. Pattern variable có kiểu tĩnh được khai báo trong pattern

Kiểu của pattern variable là kiểu được viết ngay sau `instanceof`, không tự động trở thành lớp cụ thể nhất của đối tượng lúc chạy.

### 3.1. Khớp với một lớp cha

```java
Object value = Integer.valueOf(16);

if (value instanceof Number number) {
    System.out.println(number.doubleValue());
}
```

Đối tượng thực tế là `Integer`, nhưng pattern khai báo `Number number`, nên kiểu tĩnh của `number` là `Number`. Có thể gọi các phương thức được khai báo trong `Number`, chẳng hạn `doubleValue()`.

Nếu cần dùng thành viên riêng của `Integer`, cần kiểm tra cụ thể hơn:

```java
if (value instanceof Integer integer) {
    System.out.println(integer.intValue());
}
```

Không nên suy luận rằng biến `number` ở ví dụ đầu tự có kiểu `Integer` chỉ vì giá trị hiện tại là một `Integer`. Trình biên dịch kiểm tra mã dựa trên kiểu tĩnh `Number`.

### 3.2. Khớp với giao diện

```java
Object value = new StringBuilder("Pattern");

if (value instanceof CharSequence sequence) {
    System.out.println(sequence.length());
    System.out.println(sequence.charAt(0));
}
```

`sequence` có kiểu tĩnh `CharSequence`. Vì vậy, mã có thể gọi `length()` và `charAt()`, là các phương thức của giao diện. Dù đối tượng thực tế là `StringBuilder`, mã không thể gọi trực tiếp `append()` qua biến `sequence`, vì phương thức đó không được khai báo trong `CharSequence`.

Nếu thật sự cần hành vi riêng của `StringBuilder`, hãy kiểm tra thêm:

```java
if (value instanceof CharSequence sequence) {
    System.out.println(sequence.length());

    if (sequence instanceof StringBuilder builder) {
        builder.append("!");
    }
}
```

Ở phép kiểm tra thứ hai, `builder` có kiểu tĩnh `StringBuilder`. Mỗi pattern variable cung cấp một góc nhìn kiểu cụ thể theo pattern tương ứng.

### 3.3. Pattern variable với mảng

```java
Object value = new int[] { 10, 20, 30 };

if (value instanceof int[] numbers) {
    System.out.println(numbers.length);
    System.out.println(numbers[0]);
}
```

`int[]` là kiểu tham chiếu mảng, dù các phần tử của mảng là kiểu nguyên thủy `int`. Do đó, có thể dùng nó làm kiểu pattern. Biến `numbers` có kiểu tĩnh `int[]`.

## 4. Quan hệ tương thích giữa kiểu nguồn và kiểu pattern

Một pattern phải có khả năng khớp với giá trị thuộc kiểu tĩnh của biểu thức nguồn. Nếu hai kiểu không thể cùng mô tả một đối tượng theo quy tắc kiểu của Java, trình biên dịch từ chối biểu thức.

### 4.1. Pattern hẹp hơn kiểu nguồn và có thể khớp

```java
Number value = Integer.valueOf(42);

if (value instanceof Integer integer) {
    System.out.println(integer + 1);
}
```

`Integer` là lớp con của `Number`. Một biểu thức có kiểu tĩnh `Number` có thể tham chiếu đến đối tượng `Integer`, nên phép kiểm tra hợp lệ. Khi khớp, biến `integer` có kiểu tĩnh là `Integer`.

### 4.2. Pattern luôn đúng bị từ chối

```java
String title = "Java";

// Không hợp lệ: mọi giá trị không null của String đều là String.
// if (title instanceof String text) { ... }

// Cũng không hợp lệ: String luôn triển khai CharSequence.
// if (title instanceof CharSequence chars) { ... }
```

Từ Java 16, trình biên dịch từ chối pattern *unconditional* đối với kiểu tĩnh của biểu thức nguồn. Nếu kiểu nguồn đã bảo đảm đối tượng luôn thuộc kiểu pattern, phép kiểm tra không thể tạo ra một nhánh thất bại hữu ích. Hãy dùng trực tiếp biến nguồn trong trường hợp này.

Quy tắc này áp dụng cả khi pattern là kiểu rộng hơn. Ví dụ, nếu biến có kiểu tĩnh `String`, mọi giá trị khác `null` của biến đều là `Object`; pattern `Object obj` vì thế cũng luôn đúng và không được dùng để kiểm tra lại.

### 4.3. Các kiểu không thể giao nhau

```java
Number value = Integer.valueOf(7);

// Không hợp lệ: một đối tượng không thể vừa là Number
// vừa là String; hai lớp này không có quan hệ kế thừa phù hợp.
// if (value instanceof String text) { ... }
```

`Number` và `String` là hai lớp không có quan hệ kế thừa có thể tạo ra đối tượng chung. `String` là lớp `final`, nên không có lớp con nào của `Number` có thể đồng thời là `String`. Trình biên dịch có thể kết luận pattern không bao giờ khớp và báo lỗi.

Với hai giao diện không liên quan trực tiếp, phép kiểm tra có thể vẫn hợp lệ nếu một lớp có thể triển khai cả hai:

```java
interface Readable { }
interface CloseableResource { }

class ResourceInspector {
    static void inspect(Readable value) {
        if (value instanceof CloseableResource resource) {
            System.out.println("Đối tượng có cả hai khả năng");
        }
    }
}
```

Một lớp có thể triển khai đồng thời `Readable` và `CloseableResource`, nên chỉ nhìn vào hai tên giao diện không đủ để kết luận chúng không thể khớp. Trình biên dịch xét khả năng tương thích kiểu theo quy tắc của Java, bao gồm quan hệ lớp, giao diện và các lớp `final`.

## 5. Giới hạn của kiểu generic trong pattern

Java sử dụng *type erasure*: thông tin tham số kiểu như `String` trong `List<String>` không được giữ đầy đủ để kiểm tra trực tiếp ở thời điểm chạy. Vì vậy, kiểu pattern phải là kiểu có thể kiểm tra lúc chạy (*reifiable type*).

```java
Object value = java.util.List.of("Java", "16");

// Không hợp lệ: List<String> không phải kiểu reifiable.
// if (value instanceof java.util.List<String> strings) { ... }

// Hợp lệ: List<?> là kiểu reifiable.
if (value instanceof java.util.List<?> elements) {
    Object first = elements.get(0);
    System.out.println(first);
}
```

Kiểu tĩnh của `elements` là `List<?>`. Khi đọc một phần tử qua kiểu này, kiểu tĩnh của kết quả là `Object`; không thể gọi phương thức riêng của `String` nếu chưa kiểm tra phần tử:

```java
if (value instanceof java.util.List<?> elements) {
    for (Object item : elements) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

Pattern `List<?> elements` xác nhận đối tượng là một danh sách, không chứng minh mọi phần tử đều là chuỗi. Pattern bên trong vòng lặp xác nhận từng phần tử riêng.

## 6. Kiểu nguyên thủy và lớp bao

Toán hạng của `instanceof` là một biểu thức kiểu tham chiếu. Vì vậy, không thể viết pattern với kiểu nguyên thủy:

```java
Object value = Integer.valueOf(16);

if (value instanceof Integer number) {
    int primitive = number; // Mở hộp (unboxing) từ Integer sang int
    System.out.println(primitive);
}
```

Pattern variable `number` có kiểu tĩnh `Integer`, không phải `int`. Khi gán nó cho biến `int`, Java thực hiện unboxing. Nếu giá trị nguồn là `null`, pattern không khớp nên phần thân `if` không chạy; không có unboxing từ `null` trong ví dụ này.

## 7. Cách đọc và thiết kế type pattern

Khi xem một biểu thức `instanceof` có pattern, hãy xác định lần lượt:

1. **Biểu thức nguồn có kiểu tĩnh gì?** Xem kiểu khai báo, kiểu suy luận hoặc kiểu của biểu thức tại vị trí sử dụng.
2. **Pattern yêu cầu kiểu gì?** Kiểu được ghi sau `instanceof` cũng là kiểu tĩnh của pattern variable.
3. **Hai kiểu có tương thích không?** Java phải cho phép khả năng đối tượng thuộc cả hai kiểu; pattern luôn đúng và pattern không thể khớp đều có thể bị từ chối khi biên dịch.
4. **Biến pattern cho phép gọi thành viên nào?** Chỉ dựa trên kiểu tĩnh của pattern variable, không dựa vào phỏng đoán về lớp thực tế lúc chạy.

| Kiểu tĩnh nguồn | Pattern | Kết quả điển hình |
| --- | --- | --- |
| `Object` | `String text` | Hợp lệ; kiểm tra lúc chạy |
| `Number` | `Integer number` | Hợp lệ; `number` có kiểu tĩnh `Integer` |
| `CharSequence` | `StringBuilder builder` | Hợp lệ; giao diện có thể được lớp này triển khai |
| `String` | `CharSequence chars` | Bị từ chối vì pattern luôn đúng |
| `Number` | `String text` | Bị từ chối vì hai lớp không thể khớp |
| `Object` | `List<?> items` | Hợp lệ; `items` có kiểu tĩnh `List<?> ` |

Type pattern không thay đổi kiểu tĩnh của biểu thức nguồn. Nó tạo một biến cục bộ mới có kiểu đã chỉ định trong pattern, chỉ khả dụng trên những đường đi mà Java xác định phép khớp thành công. Hiểu rõ hai kiểu này giúp dự đoán được biểu thức nào biên dịch, biến pattern gọi được phương thức nào và khi nào cần kiểm tra kiểu cụ thể hơn.
