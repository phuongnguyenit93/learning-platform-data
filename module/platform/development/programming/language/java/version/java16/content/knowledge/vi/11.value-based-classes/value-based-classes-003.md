# Dùng equals thay vì == khi so sánh giá trị đối tượng

Trong Java, **==** và **equals()** có thể cho kết quả giống nhau trong một số trường hợp, nhưng chúng kiểm tra hai điều khác nhau. Với kiểu nguyên thủy, **==** so sánh giá trị. Với hai biến tham chiếu, **==** kiểm tra chúng có cùng trỏ tới một object hay không. Trong khi đó, **equals()** được dùng để kiểm tra hai object có bằng nhau theo định nghĩa của lớp hay không.

Khi làm việc với các đối tượng biểu diễn dữ liệu như **String**, **Integer**, **Optional**, **LocalDate** hoặc các lớp value object của ứng dụng, hãy dùng **equals()** để so sánh giá trị. Bài học này trình bày cách chọn phép so sánh đúng, cách xử lý **null**, hợp đồng **equals()** và **hashCode()**, cùng những trường hợp đặc biệt vẫn thường gặp trong Java hiện đại.

## 1. Hai phép so sánh trả lời hai câu hỏi khác nhau

### == với kiểu nguyên thủy

Với các kiểu nguyên thủy như **int**, **long**, **double**, **char** và **boolean**, toán tử **==** so sánh giá trị:

~~~java
int first = 10;
int second = 10;

System.out.println(first == second); // true
~~~

Đây là cách so sánh đúng vì hai biến chứa giá trị nguyên thủy, không phải hai object reference.

### == với object reference

Khi cả hai toán hạng là reference, **==** kiểm tra chúng có cùng tham chiếu tới một object hay không:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Hai object **String** chứa cùng chuỗi ký tự, nhưng được tạo thành hai object khác nhau. Vì vậy, phép so sánh identity bằng **==** trả về **false**, còn **equals()** trả về **true**.

Nếu hai biến cùng tham chiếu tới một object, cả **==** và **equals()** thông thường đều trả về **true**:

~~~java
String first = new String("Java");
String second = first;

System.out.println(first == second);      // true
System.out.println(first.equals(second)); // true
~~~

Trong trường hợp này, kết quả giống nhau vì hai biến trỏ tới cùng object. Điều đó không làm cho **==** trở thành phép so sánh giá trị.

### equals() biểu diễn phép bằng nhau theo hợp đồng của lớp

**equals()** là phương thức được khai báo trong **Object**. Mặc định, implementation của **Object.equals()** chỉ xem hai tham chiếu là bằng nhau khi chúng trỏ tới cùng object. Một lớp có thể ghi đè phương thức này để định nghĩa thế nào là hai instance có cùng giá trị.

Ví dụ, **String** ghi đè **equals()** để so sánh nội dung chuỗi. Các lớp wrapper, **Optional** và nhiều lớp trong **java.time** cũng định nghĩa phép bằng nhau dựa trên giá trị mà chúng biểu diễn.

Vì thế, không phải mọi lời gọi **equals()** đều tự động có nghĩa là so sánh nội dung. Hãy đọc hợp đồng của lớp đang sử dụng. Nếu lớp không ghi đè **equals()**, hành vi kế thừa từ **Object** vẫn là so sánh identity.

## 2. So sánh các đối tượng giá trị bằng equals()

### String

Đối với chuỗi, dùng **equals()** khi cần kiểm tra nội dung:

~~~java
String expected = "Java 16";
String actual = new String("Java 16");

if (expected.equals(actual)) {
    System.out.println("Nội dung trùng khớp");
}
~~~

Không dùng **==** để kiểm tra hai chuỗi có cùng nội dung. String literal có thể được intern và dùng chung object trong string pool, nên một số phép so sánh **==** có thể tình cờ trả về **true**. Đó là đặc điểm quản lý identity của chuỗi, không phải cách so sánh nội dung.

Nếu cần so sánh không phân biệt chữ hoa chữ thường, dùng **equalsIgnoreCase()**:

~~~java
String input = "java";
boolean matches = "JAVA".equalsIgnoreCase(input); // true
~~~

### Wrapper và các lớp biểu diễn giá trị

Các lớp wrapper như **Integer**, **Long**, **Boolean**, **Double** cùng nhiều kiểu ngày giờ trong **java.time** có hợp đồng so sánh giá trị. Ví dụ:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second)); // true
~~~

Không dựa vào việc JVM có cache hoặc tái sử dụng wrapper hay không. Hợp đồng value-based không bảo đảm hai lần gọi factory phải tạo object riêng hoặc phải dùng chung một object. Các instance bằng nhau cần được xem là có thể thay thế cho nhau trong những thao tác được lớp định nghĩa.

Với **LocalDate**, cũng so sánh theo ngày mà object biểu diễn:

~~~java
import java.time.LocalDate;

LocalDate dateFromFactory = LocalDate.of(2026, 11, 27);
LocalDate dateFromText = LocalDate.parse("2026-11-27");

System.out.println(dateFromFactory.equals(dateFromText)); // true
~~~

### Lớp do ứng dụng định nghĩa

Giả sử ứng dụng có lớp **UserId** dùng để biểu diễn mã người dùng. Hai instance có cùng mã cần được xem là bằng nhau, dù được tạo ở hai thời điểm khác nhau:

~~~java
import java.util.Objects;

public final class UserId {
    private final String value;

    public UserId(String value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof UserId)) {
            return false;
        }

        UserId that = (UserId) other;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Có thể kiểm tra:

~~~java
UserId first = new UserId("U-100");
UserId second = new UserId("U-100");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Lớp ghi đè cả **equals()** và **hashCode()**. Điều này quan trọng khi **UserId** được dùng làm khóa trong **HashMap** hoặc phần tử trong **HashSet**.

Từ Java 16, nếu lớp chỉ là một nhóm dữ liệu và phù hợp với ngữ nghĩa record, có thể biểu diễn ngắn gọn hơn:

~~~java
public record UserKey(String value) {}
~~~

Record tự sinh **equals()** và **hashCode()** dựa trên các component. Với component là object reference, phép bằng nhau của component được xét theo hợp đồng **equals()** tương ứng. Nếu component là mảng, cần nhớ rằng mảng không tự ghi đè **equals()** để so sánh nội dung; hai mảng khác object vẫn không bằng nhau theo cách này. Hãy chọn kiểu component và định nghĩa equality phù hợp với ý nghĩa dữ liệu.

## 3. Xử lý null khi gọi equals()

Một lỗi thường gặp là gọi **equals()** trên một reference có thể đang là **null**:

~~~java
String actual = null;

boolean matches = actual.equals("Java"); // NullPointerException
~~~

Có hai cách thường dùng để xử lý.

### Gọi equals trên giá trị chắc chắn không null

Nếu biết đối tượng ở phía nhận lời gọi luôn khác **null**, có thể viết:

~~~java
String actual = null; // Có thể thay bằng dữ liệu nhận từ ứng dụng

if ("Java".equals(actual)) {
    System.out.println("Đúng giá trị");
}
~~~

Chuỗi literal **"Java"** không null, vì vậy lời gọi an toàn ngay cả khi **actual** là **null**. Kết quả khi đó là **false**.

### Dùng Objects.equals()

Khi cả hai giá trị đều có thể **null**, dùng **Objects.equals(a, b)**:

~~~java
import java.util.Objects;

String first = null;
String second = null;

System.out.println(Objects.equals(first, second)); // true
System.out.println(Objects.equals(first, "Java")); // false
~~~

Phương thức này xử lý ba trường hợp:

| Giá trị thứ nhất | Giá trị thứ hai | Kết quả |
| --- | --- | --- |
| **null** | **null** | **true** |
| **null** | object khác null | **false** |
| object khác null | object khác null | Gọi **equals()** của giá trị thứ nhất |

**Objects.equals()** không làm cho hai lớp bất kỳ tự động có cùng ngữ nghĩa bằng nhau. Khi cả hai khác **null**, kết quả vẫn phụ thuộc implementation **equals()** của đối tượng thứ nhất.

### Cẩn thận với unboxing

Wrapper có thể được tự động unbox khi so sánh với primitive. Nếu wrapper đang **null**, phép unboxing sẽ ném **NullPointerException**:

~~~java
Integer count = null;

// Ném NullPointerException khi unbox count
// boolean isZero = count == 0;
~~~

Nếu cần so sánh wrapper với một giá trị primitive, hãy kiểm tra null trước:

~~~java
Integer count = null;

if (count != null && count.intValue() == 0) {
    System.out.println("Bằng không");
}
~~~

Nếu cần so sánh hai wrapper như hai object giá trị, có thể dùng **Objects.equals(first, second)**.

## 4. Hợp đồng equals() và hashCode()

Khi ghi đè **equals()** cho lớp riêng, implementation cần tuân thủ hợp đồng của **Object.equals()**:

1. **Phản xạ:** với mọi reference khác null **x**, **x.equals(x)** phải là **true**.
2. **Đối xứng:** nếu **x.equals(y)** là **true**, thì **y.equals(x)** cũng phải là **true**.
3. **Bắc cầu:** nếu **x.equals(y)** và **y.equals(z)** đều là **true**, thì **x.equals(z)** phải là **true**.
4. **Nhất quán:** gọi nhiều lần phải cho cùng kết quả nếu thông tin được dùng để so sánh không thay đổi.
5. **Không null:** với reference khác null **x**, **x.equals(null)** phải là **false**.

**hashCode()** có hợp đồng đi cùng **equals()**:

- Nếu hai object bằng nhau theo **equals()**, chúng phải có cùng **hashCode()**.
- Nếu hai object có cùng **hashCode()**, chưa thể kết luận chúng bằng nhau.
- Kết quả **hashCode()** cần nhất quán trong một lần thực thi khi thông tin được dùng để so sánh không thay đổi.

Vì vậy, khi ghi đè **equals()**, thông thường phải ghi đè cả **hashCode()** và dùng cùng những trường quyết định equality.

Ví dụ, nếu hai **UserId** có cùng **value** thì cả hai phải có cùng hash code. Nếu chỉ ghi đè **equals()** mà giữ **hashCode()** mặc định từ **Object**, **HashSet** hoặc **HashMap** có thể không tìm thấy một khóa bằng nhau dù **equals()** trả về **true**.

~~~java
import java.util.HashSet;
import java.util.Set;

Set<UserId> ids = new HashSet<>();
ids.add(new UserId("U-100"));

boolean exists = ids.contains(new UserId("U-100")); // true
~~~

Kết quả mong đợi chỉ đạt được khi **equals()** và **hashCode()** được cài đặt nhất quán.

## 5. Những trường hợp không nên áp dụng máy móc equals()

**equals()** là lựa chọn thông thường khi so sánh giá trị object, nhưng một số kiểu dữ liệu có ngữ nghĩa riêng. Hãy chọn phép so sánh theo hợp đồng API.

### Enum

Mỗi hằng enum là một instance duy nhất trong JVM. So sánh hai giá trị enum bằng **==** là hợp lệ và rõ ràng:

~~~java
enum Status {
    ACTIVE, INACTIVE
}

Status status = Status.ACTIVE;

if (status == Status.ACTIVE) {
    System.out.println("Đang hoạt động");
}
~~~

### Array

Mảng Java không ghi đè **equals()** để so sánh phần tử. Vì vậy, **array1.equals(array2)** vẫn kiểm tra identity. Dùng **Arrays.equals()** cho mảng một chiều và **Arrays.deepEquals()** cho mảng lồng nhau:

~~~java
import java.util.Arrays;

int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second);              // false
System.out.println(first.equals(second));         // false
System.out.println(Arrays.equals(first, second)); // true
~~~

Với mảng object nhiều chiều hoặc mảng lồng nhau, dùng **Arrays.deepEquals()** để so sánh nội dung theo chiều sâu.

### BigDecimal

**BigDecimal.equals()** xét cả giá trị số và scale. Vì vậy, **2.0** và **2.00** không bằng nhau theo **equals()**, dù chúng có cùng giá trị số. Nếu yêu cầu nghiệp vụ chỉ quan tâm giá trị số, dùng **compareTo()**:

~~~java
import java.math.BigDecimal;

BigDecimal first = new BigDecimal("2.0");
BigDecimal second = new BigDecimal("2.00");

System.out.println(first.equals(second));         // false
System.out.println(first.compareTo(second) == 0); // true
~~~

Hãy quyết định rõ nghiệp vụ có phân biệt scale hay không trước khi chọn phép so sánh. Điều này cũng quan trọng khi dùng **BigDecimal** trong collection: **HashSet** dựa trên **equals()**/**hashCode()**, còn **TreeSet** dựa trên thứ tự so sánh.

### So sánh số thực

Với **float** và **double** nguyên thủy, **==** so sánh theo quy tắc số thực của Java. Có hai trường hợp cần nhớ:

~~~java
double nan = Double.NaN;

System.out.println(nan == nan);   // false
System.out.println(+0.0 == -0.0); // true
~~~

Nếu cần quy tắc so sánh đặc thù, hãy xem API **Double.compare()** hoặc **Float.compare()** và hợp đồng của lớp wrapper tương ứng. Không chuyển đổi tùy tiện giữa so sánh primitive và so sánh object vì quy tắc về NaN và số không có dấu có thể khác nhau.

## 6. Chọn phép so sánh phù hợp

Bảng sau có thể dùng như hướng dẫn nhanh khi viết code:

| Nhu cầu | Cách dùng |
| --- | --- |
| So sánh hai giá trị primitive | Dùng **==** |
| Kiểm tra hai reference có cùng object | Dùng **==** |
| So sánh nội dung của object có hợp đồng value equality | Dùng **equals()** |
| So sánh hai object có thể null | Dùng **Objects.equals()** |
| So sánh nội dung mảng | Dùng **Arrays.equals()** hoặc **Arrays.deepEquals()** |
| So sánh hai enum constant | Dùng **==** |
| So sánh số **BigDecimal** theo giá trị số, không phân biệt scale | Dùng **compareTo() == 0** |
| Kiểm tra một reference có null | Dùng **== null** hoặc **!= null** |

Một vài nguyên tắc giúp tránh lỗi:

- Đừng dựa vào string pool hoặc cache wrapper để so sánh object bằng **==**.
- Đừng cho rằng mọi lớp đều định nghĩa **equals()** theo nội dung; lớp có thể giữ implementation mặc định của **Object**.
- Khi thiết kế value object, xác định rõ những field nào tham gia equality và triển khai **equals()**/**hashCode()** nhất quán.
- Khi dùng object làm khóa trong collection dựa trên hash, không thay đổi những field tham gia equality trong thời gian object đang được dùng làm khóa.
- Với API có ngữ nghĩa so sánh riêng như mảng, **BigDecimal** hoặc kiểu số thực, đọc JavaDoc trước khi quyết định.

## 7. Kết luận

**==** và **equals()** không thể thay thế tùy ý cho nhau. **==** so sánh giá trị khi dùng với primitive và identity khi dùng với reference. **equals()** kiểm tra equality theo hợp đồng mà lớp định nghĩa; với các lớp value-based, đó là phép so sánh phù hợp để làm việc theo giá trị.

Trong code Java hiện đại, hãy dùng **equals()** hoặc **Objects.equals()** cho object value, kiểm tra null trước khi unbox wrapper, và luôn triển khai **hashCode()** tương thích khi ghi đè **equals()**. Với enum, mảng, **BigDecimal** và số thực, hãy chọn phép so sánh theo đúng ngữ nghĩa API của kiểu dữ liệu.

## Tài liệu tham khảo

- [Object.equals() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))
- [Object.hashCode() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html#hashCode())
- [Objects.equals() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object))
- [String — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html)
- [Arrays — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html)
- [BigDecimal — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html)
- [Enum — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Enum.html)
- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [Record Classes — Java SE 27 Language Specification](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10)

