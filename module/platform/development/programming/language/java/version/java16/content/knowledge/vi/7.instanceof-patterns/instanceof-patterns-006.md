# Giới hạn khi pattern yêu cầu phép chuyển kiểu không hợp lệ

## 1. Type pattern phải tương thích với kiểu tĩnh của biểu thức nguồn

Khi viết pattern matching for `instanceof`, Java kiểm tra tính hợp lệ của kiểu ngay ở thời điểm biên dịch. Kiểu tĩnh của biểu thức nguồn phải có khả năng chuyển đổi tham chiếu sang kiểu được ghi trong pattern theo quy tắc *casting conversion* của Java. Nếu không tồn tại phép chuyển kiểu hợp lệ, chương trình bị từ chối trước khi chạy.

Ví dụ hợp lệ:

~~~java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Biểu thức nguồn có kiểu tĩnh `Object`. Một đối tượng được tham chiếu qua `Object` có thể là `String`, nên phép kiểm tra có ý nghĩa và được biên dịch. Khi chạy, pattern chỉ khớp nếu đối tượng thực tế là chuỗi.

Ngược lại:

~~~java
Integer value = 16;

// Lỗi biên dịch: Integer không thể chuyển kiểu tham chiếu sang String.
// if (value instanceof String text) {
//     System.out.println(text);
// }
~~~

`Integer` và `String` là hai lớp không có quan hệ kế thừa cho phép một đối tượng thuộc cả hai kiểu. Không có casting conversion hợp lệ giữa kiểu tĩnh `Integer` và kiểu pattern `String`, nên trình biên dịch phát hiện lỗi ngay cả khi đoạn mã nằm trong một nhánh có vẻ không bao giờ chạy.

## 2. Phân biệt lỗi biên dịch với trường hợp pattern không khớp lúc chạy

Đây là hai tình huống khác nhau:

~~~java
Object value = Integer.valueOf(16);

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Giá trị không phải String");
}
~~~

Đoạn mã trên **biên dịch được**. Kiểu tĩnh của `value` là `Object`, nên phép chuyển kiểu tham chiếu sang `String` có thể hợp lệ. Nhưng đối tượng thực tế là `Integer`, do đó pattern trả về `false` và nhánh `else` chạy.

Trong khi đó, nếu khai báo nguồn là `Integer`:

~~~java
Integer value = 16;

// Không biên dịch: kiểu tĩnh Integer không thể khớp String.
// if (value instanceof String text) { ... }
~~~

Trình biên dịch không đợi đến lúc chạy để kiểm tra một khả năng vốn bị loại trừ bởi hệ thống kiểu. Hãy phân biệt:

| Tình huống | Kết quả |
| --- | --- |
| Kiểu tĩnh nguồn và kiểu pattern có casting conversion hợp lệ | Có thể biên dịch; đối tượng thực tế quyết định pattern đúng hay sai |
| Không có casting conversion hợp lệ | Lỗi biên dịch |
| Pattern luôn đúng theo kiểu tĩnh nguồn | Lỗi biên dịch với type pattern của `instanceof` |
| Nguồn là `null` | Biên dịch nếu kiểu tương thích; lúc chạy pattern trả về `false` |

Type pattern không thực hiện một phép ép kiểu mù rồi chờ `ClassCastException`. Nó kiểm tra kiểu an toàn và chỉ cung cấp biến pattern khi điều kiện khớp.

## 3. Các quan hệ kiểu quyết định phép chuyển kiểu có thể thực hiện

### 3.1. Lớp và lớp có quan hệ kế thừa

Khi kiểu pattern là lớp con của kiểu nguồn, phép kiểm tra có thể hợp lệ:

~~~java
Number value = Integer.valueOf(42);

if (value instanceof Integer number) {
    System.out.println(number.intValue());
}
~~~

`Integer` là lớp con của `Number`. Một biến `Number` có thể tham chiếu đến đối tượng `Integer`, nên trình biên dịch cho phép pattern. Nếu đối tượng thực tế là một lớp con khác của `Number`, điều kiện chỉ đơn giản trả về `false`.

Nếu hai lớp không có quan hệ kế thừa khả thi, phép kiểm tra bị từ chối:

~~~java
Number value = Integer.valueOf(7);

// Lỗi biên dịch: Number và String không thể mô tả cùng một đối tượng.
// if (value instanceof String text) {
//     ...
// }
~~~

`String` là lớp `final` và không phải lớp con của `Number`. Một đối tượng không thể đồng thời là instance của hai lớp này.

### 3.2. Lớp final và interface

Một lớp `final` không thể có lớp con. Vì vậy, nếu lớp đó không triển khai một interface, không thể tồn tại lớp con nào vừa là lớp đó vừa bổ sung interface:

~~~java
final class FixedValue {
}

interface RunnableTask {
    void run();
}

FixedValue value = new FixedValue();

// Lỗi biên dịch: FixedValue là final và không triển khai RunnableTask.
// if (value instanceof RunnableTask task) {
//     task.run();
// }
~~~

Ngược lại, nếu lớp `final` đã triển khai interface thì phép kiểm tra có thể hợp lệ:

~~~java
import java.io.Serializable;

Serializable value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

`String` là lớp `final` nhưng triển khai `Serializable`. Kiểu nguồn `Serializable` có thể tham chiếu đến chuỗi, nên pattern `String text` hợp lệ. Không phải cứ một bên là interface và bên kia là lớp `final` thì phép kiểm tra đều sai; cần xem lớp đó có triển khai interface hay không.

### 3.3. Interface và lớp không final

Một interface có thể khớp với lớp không `final` nếu một lớp con có thể mở rộng lớp đó và đồng thời triển khai interface:

~~~java
import java.util.AbstractList;

interface RunnableTask {
    void run();
}

class PatternCompatibilityDemo {
    static void inspect(RunnableTask task) {
        if (task instanceof AbstractList<?> list) {
            System.out.println("Đối tượng cũng là một danh sách");
        }
    }
}
~~~

`AbstractList` không phải lớp `final`. Một lớp có thể kế thừa `AbstractList` và triển khai `RunnableTask`, vì vậy hai kiểu không bị loại trừ chỉ bởi tên của chúng. Kiểu generic trong pattern dùng dấu hỏi `<?>` để giữ kiểu có thể kiểm tra lúc chạy.

Ví dụ này minh họa khả năng tương thích của kiểu. Nó không khẳng định mọi đối tượng `RunnableTask` đều là danh sách; nếu đối tượng thực tế không thuộc một lớp con của `AbstractList`, pattern trả về `false`.

### 3.4. Interface và interface

Hai interface có thể không kế thừa lẫn nhau nhưng một lớp vẫn có thể triển khai cả hai:

~~~java
interface Readable {
    String read();
}

interface CloseableResource {
    void close();
}

class InterfacePatternDemo {
    static void inspect(Readable source) {
        if (source instanceof CloseableResource resource) {
            resource.close();
        }
    }
}
~~~

Một lớp có thể triển khai đồng thời `Readable` và `CloseableResource`, nên phép kiểm tra có thể hợp lệ. Nếu đối tượng lúc chạy chỉ triển khai `Readable`, điều kiện trả về `false`.

## 4. Kiểu generic có thể làm phép chuyển kiểu không hợp lệ

Java xóa thông tin tham số kiểu generic ở thời điểm chạy (*type erasure*). Do đó, pattern không thể kiểm tra một kiểu tham số hóa cụ thể không *reifiable*, chẳng hạn `List<String>`.

~~~java
Object value = java.util.List.of("Java", "Pattern");

// Lỗi biên dịch: List<String> không phải kiểu reifiable.
// if (value instanceof java.util.List<String> strings) {
//     ...
// }

// Hợp lệ: List<?> là kiểu reifiable.
if (value instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
~~~

Pattern `List<?> elements` chỉ xác nhận đối tượng là một `List`. Khi đọc phần tử, kiểu tĩnh của phần tử là `Object`. Muốn dùng phần tử như `String`, hãy kiểm tra riêng:

~~~java
if (value instanceof java.util.List<?> elements) {
    for (Object item : elements) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
~~~

Không thể dùng một pattern với tham số kiểu cụ thể chỉ vì chương trình biết dữ liệu được tạo từ danh sách chuỗi. Phép kiểm tra `instanceof` phải dựa trên kiểu có thể xác định tại runtime, không dựa trên giả định về tham số generic đã bị xóa.

## 5. Kiểu mảng cũng chịu quy tắc casting conversion

Mảng là kiểu tham chiếu, nên có thể xuất hiện trong type pattern. Tuy nhiên, quan hệ kiểu của mảng phải hợp lệ:

~~~java
Object value = new String[] { "A", "B" };

if (value instanceof Object[] elements) {
    System.out.println(elements.length);
}
~~~

`String[]` là subtype của `Object[]` vì `String` là subtype của `Object`. Pattern trên hợp lệ.

Mảng kiểu nguyên thủy không phải subtype của `Object[]`:

~~~java
Object value = new int[] { 1, 2, 3 };

if (value instanceof int[] numbers) {
    System.out.println(numbers.length);
}

// Không hợp lệ: int[] không chuyển kiểu tham chiếu được sang Object[].
// if (value instanceof Object[] elements) { ... }
~~~

`int[]` vẫn là một đối tượng và có thể khớp với `Object`, `Cloneable` hoặc `java.io.Serializable`. Nhưng nó không thể khớp với `Object[]`, vì phần tử của nó là kiểu nguyên thủy.

## 6. Cú pháp type pattern Java 16 làm việc với kiểu tham chiếu

Type pattern được chuẩn hóa trong Java 16 dùng biểu thức nguồn và kiểu pattern thuộc hệ kiểu tham chiếu. Một biến nguyên thủy không tự động được boxing để tham gia phép kiểm tra:

~~~java
int count = 10;

// Lỗi biên dịch: count có kiểu nguyên thủy int.
// if (count instanceof Integer number) {
//     ...
// }
~~~

Nếu muốn kiểm tra một đối tượng bao kiểu nguyên thủy, hãy dùng lớp wrapper:

~~~java
Object value = Integer.valueOf(10);

if (value instanceof Integer number) {
    int result = number + 1; // Unboxing khi dùng trong phép cộng
    System.out.println(result);
}
~~~

Trong ví dụ này, biểu thức nguồn có kiểu tĩnh `Object` và đối tượng thực tế là `Integer`. Pattern variable `number` có kiểu tĩnh `Integer`; việc unboxing xảy ra khi sử dụng biến trong phép toán số học, không phải trong phép kiểm tra pattern.

## 7. Casting conversion hợp lệ nhưng pattern luôn đúng

Không phải mọi lỗi liên quan đến pattern đều do thiếu casting conversion. Có trường hợp hai kiểu tương thích nhưng pattern luôn đúng theo kiểu tĩnh của biểu thức nguồn. Type pattern như vậy cũng bị trình biên dịch từ chối vì không còn phép kiểm tra hữu ích:

~~~java
String title = "Java";

// Lỗi biên dịch: mọi giá trị String đều là CharSequence.
// if (title instanceof CharSequence chars) {
//     System.out.println(chars.length());
// }
~~~

Ở đây, `String` triển khai `CharSequence` nên quan hệ chuyển kiểu là hợp lệ. Tuy nhiên, kiểu tĩnh `String` đã bảo đảm điều kiện luôn đúng. Hãy dùng trực tiếp biến `title`.

So sánh hai trường hợp:

- **Không có casting conversion:** kiểu nguồn và kiểu pattern không thể cùng mô tả một đối tượng; lỗi do không tương thích kiểu.
- **Pattern luôn đúng:** kiểu nguồn đã bảo đảm đối tượng thuộc kiểu pattern; lỗi do kiểm tra thừa.

Phân biệt hai nguyên nhân này giúp đọc thông báo lỗi và sửa mã đúng chỗ.

## 8. Cách xử lý khi gặp lỗi chuyển kiểu

Khi trình biên dịch báo một pattern không hợp lệ, hãy lần lượt:

1. Xác định kiểu tĩnh của biểu thức nguồn tại đúng vị trí `instanceof`, không chỉ nhìn vào giá trị khởi tạo.
2. Xác định kiểu được ghi trong pattern và kiểm tra quan hệ kế thừa hoặc triển khai interface.
3. Nếu có lớp `final`, kiểm tra xem lớp đó có triển khai interface đích hay không; lớp con không thể bổ sung interface cho một lớp `final`.
4. Với generic, dùng kiểu reifiable như `List<?>`, sau đó kiểm tra từng phần tử nếu cần kiểu cụ thể.
5. Với mảng, phân biệt mảng tham chiếu như `String[]` với mảng nguyên thủy như `int[]`.
6. Nếu pattern luôn đúng, bỏ phép kiểm tra và dùng trực tiếp biến nguồn.

| Biểu thức nguồn | Pattern | Đánh giá |
| --- | --- | --- |
| `Object` | `String text` | Hợp lệ; runtime quyết định có khớp |
| `Integer` | `String text` | Không có casting conversion; lỗi biên dịch |
| `Number` | `Integer number` | Hợp lệ; `Integer` là subtype của `Number` |
| `String` | `CharSequence chars` | Pattern luôn đúng; lỗi biên dịch |
| `Serializable` | `String text` | Hợp lệ; `String` triển khai `Serializable` |
| `Object` | `List<?> items` | Hợp lệ; kiểu pattern reifiable |
| `Object` | `List<String> items` | Không hợp lệ; kiểu pattern không reifiable |
| `Object` | `Object[] items` với giá trị runtime `int[]` | Biên dịch được; runtime không khớp |

**Ghi nhớ:** Type pattern chỉ được biên dịch khi kiểu tĩnh của biểu thức nguồn có thể chuyển kiểu tham chiếu sang kiểu pattern và pattern không phải trường hợp luôn đúng bị cấm. Nếu biên dịch thành công, đối tượng thực tế quyết định kết quả khớp; nếu không có quan hệ kiểu hợp lệ, phải sửa kiểu nguồn hoặc kiểu pattern trước khi chương trình có thể chạy.
