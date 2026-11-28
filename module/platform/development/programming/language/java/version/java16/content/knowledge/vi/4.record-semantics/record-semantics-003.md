# So sánh component primitive với NaN, +0.0 và -0.0

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record trở thành tính năng chính thức từ Java 16. Một record tự động có `equals(Object)` và `hashCode()` dựa trên các record component. Với component kiểu nguyên thủy, quy tắc so sánh phụ thuộc vào kiểu primitive. Phần lớn kiểu primitive có hành vi dễ dự đoán; riêng `float` và `double` có hai trường hợp đặc biệt thường gây nhầm lẫn: `NaN` và hai dạng số không có dấu.

Điểm cần nhớ: `equals` mặc định của record so sánh component `float` theo ngữ nghĩa `Float.compare` và component `double` theo ngữ nghĩa `Double.compare`. Vì vậy kết quả không hoàn toàn giống toán tử `==` của primitive.

## 1. Quy tắc so sánh component primitive

Record không so sánh component primitive bằng cách gọi `Objects.equals` vì primitive không phải kiểu tham chiếu. Về mặt ngữ nghĩa, phép so sánh tương ứng với phương thức `compare` của wrapper:

| Kiểu component | Phép so sánh tương ứng | Khi nào được xem là bằng nhau? |
| --- | --- | --- |
| `boolean` | `Boolean.compare(a, b)` | Cùng là `true` hoặc cùng là `false`. |
| `byte` | `Byte.compare(a, b)` | Cùng giá trị byte. |
| `short` | `Short.compare(a, b)` | Cùng giá trị short. |
| `char` | `Character.compare(a, b)` | Cùng mã ký tự UTF-16. |
| `int` | `Integer.compare(a, b)` | Cùng giá trị int. |
| `long` | `Long.compare(a, b)` | Cùng giá trị long. |
| `float` | `Float.compare(a, b)` | Cùng giá trị theo quy tắc của Float, bao gồm quy tắc riêng cho NaN và signed zero. |
| `double` | `Double.compare(a, b)` | Cùng giá trị theo quy tắc của Double, bao gồm quy tắc riêng cho NaN và signed zero. |

Bảng mô tả **kết quả ngữ nghĩa tương đương** với `compare(a, b) == 0`; không có nghĩa compiler bắt buộc phải sinh đúng lời gọi các phương thức wrapper này.

Các kiểu nguyên thủy nguyên, ký tự và boolean thường hoạt động như mong đợi:

```java
record Coordinates(int x, int y) {}
record SwitchState(boolean enabled) {}

System.out.println(new Coordinates(3, 5).equals(new Coordinates(3, 5))); // true
System.out.println(new Coordinates(3, 5).equals(new Coordinates(3, 6))); // false
System.out.println(new SwitchState(true).equals(new SwitchState(true))); // true
```

Khác biệt đáng chú ý tập trung ở `float` và `double`. Để hiểu đúng, cần phân biệt ngữ nghĩa của `Float.compare`/`Double.compare` với phép so sánh số học bằng `==`.

## 2. `NaN`: primitive `==` trả về false, record vẫn có thể bằng nhau

`NaN` (Not a Number) là giá trị đặc biệt của số dấu phẩy động IEEE 754. Một phép toán không tạo ra số thực hợp lệ, chẳng hạn `0.0 / 0.0`, có thể tạo ra `NaN`.

Theo phép so sánh số học của Java:

```java
double value = Double.NaN;

System.out.println(value == value); // false
System.out.println(value != value); // true
System.out.println(value < 1.0);     // false
System.out.println(value > 1.0);     // false
```

Điều này khác với quy tắc bằng nhau của `Double`. `Double.compare` xem hai giá trị `NaN` là bằng nhau; `Float.compare` cũng làm tương tự. Do đó, record chứa `NaN` có thể bằng một record khác cũng chứa `NaN`:

```java
record Measurement(double value) {}

Measurement first = new Measurement(Double.NaN);
Measurement second = new Measurement(Double.NaN);

System.out.println(first.value() == second.value()); // false
System.out.println(first.equals(second));            // true
```

Đây không phải lỗi của record. Phương thức `equals(Object)` phải có tính phản xạ: một đối tượng phải bằng chính nó. Nếu dùng trực tiếp `==` cho component `NaN`, ngay cả phép so sánh một record với chính nó cũng có thể cho kết quả sai với hợp đồng `equals`. Quy tắc của `Float.compare` và `Double.compare` giải quyết điểm này.

### Các cách biểu diễn NaN khác nhau

IEEE 754 cho phép nhiều bit pattern biểu diễn `NaN`. Java cung cấp `floatToRawIntBits` và `doubleToRawLongBits` để quan sát bit pattern thô; các phương thức `floatToIntBits` và `doubleToLongBits` chuẩn hóa các bit pattern NaN về một biểu diễn chuẩn.

`Float.compare` và `Double.compare` xem các NaN là bằng nhau, kể cả khi bit pattern thô khác nhau:

```java
record DoubleValue(double value) {}

double canonicalNaN = Double.NaN;
double anotherNaN = Double.longBitsToDouble(0x7ff8_0000_0000_0001L);

System.out.println(Double.isNaN(canonicalNaN)); // true
System.out.println(Double.isNaN(anotherNaN));   // true

System.out.println(
    Double.doubleToRawLongBits(canonicalNaN)
        == Double.doubleToRawLongBits(anotherNaN)
); // false: bit pattern thô khác nhau

System.out.println(
    new DoubleValue(canonicalNaN).equals(new DoubleValue(anotherNaN))
); // true: các NaN được xem là bằng nhau
```

Quy tắc tương tự áp dụng cho `float` với `Float.intBitsToFloat` và `Float.floatToRawIntBits`. Trong mã nghiệp vụ, thường chỉ cần `Double.isNaN(value)` hoặc `Float.isNaN(value)` để nhận biết NaN; chỉ kiểm tra bit pattern thô khi làm việc với dữ liệu số mức thấp, định dạng nhị phân hoặc thuật toán cần giữ payload NaN.

## 3. Signed zero: +0.0 và -0.0 không bằng nhau theo record

IEEE 754 có hai biểu diễn số không cho cả `float` và `double`:

- `+0.0`: số không dương.
- `-0.0`: số không âm.

Toán tử `==` xem chúng là bằng nhau:

```java
System.out.println(+0.0 == -0.0); // true
```

Nhưng `Double.compare` phân biệt dấu của số không. `Float.compare` cũng vậy. Vì thế hai record có component lần lượt là `+0.0` và `-0.0` **không bằng nhau**:

```java
record Temperature(double celsius) {}

Temperature positiveZero = new Temperature(+0.0);
Temperature negativeZero = new Temperature(-0.0);

System.out.println(positiveZero.celsius() == negativeZero.celsius()); // true
System.out.println(positiveZero.equals(negativeZero));                // false
System.out.println(Double.compare(+0.0, -0.0));                       // 1
System.out.println(Double.compare(-0.0, +0.0));                       // -1
```

Sự khác biệt này có ý nghĩa thực tế. Hai giá trị zero có thể tạo ra kết quả khác nhau trong phép toán:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Vì dấu của zero có thể ảnh hưởng đến phép toán tiếp theo, việc giữ hai giá trị thành hai trạng thái khác nhau trong `equals` là hợp lý. Nếu bài toán của bạn coi hai số zero là cùng một giá trị, hãy chuẩn hóa dấu trước khi lưu vào record.

### Nhận biết dấu của zero

Có thể dùng phép chia hoặc kiểm tra bit để phân biệt:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(Double.doubleToRawLongBits(positiveZero)); // 0
System.out.println(Double.doubleToRawLongBits(negativeZero)); // Long.MIN_VALUE

System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
```

Với `float`, dùng `Float.floatToRawIntBits`. Không dùng `value == 0.0` để xác định dấu, vì biểu thức đó trả về `true` cho cả `+0.0` lẫn `-0.0`.

## 4. Bảng so sánh nhanh giữa `==` và `equals` của record

Với component `double`, những trường hợp quan trọng có kết quả như sau:

| Giá trị bên trái | Giá trị bên phải | Primitive `==` | `Double.compare(a, b) == 0` | Record mặc định bằng nhau? |
| --- | --- | --- | --- | --- |
| `2.5` | `2.5` | `true` | `true` | `true` |
| `2.5` | `3.5` | `false` | `false` | `false` |
| `Double.NaN` | `Double.NaN` | `false` | `true` | `true` |
| NaN bit pattern A | NaN bit pattern B | `false` | `true` | `true` |
| `+0.0` | `-0.0` | `true` | `false` | `false` |
| `Double.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` | `true` | `true` | `true` |
| `Double.NEGATIVE_INFINITY` | `Double.POSITIVE_INFINITY` | `false` | `false` | `false` |

`Float.compare` có quy tắc tương tự cho component `float`. Với component kiểu nguyên thủy khác `float` và `double`, phép so sánh bằng nhau không có các trường hợp NaN hoặc signed zero.

## 5. Hệ quả với `hashCode` và collection

`equals` và `hashCode` phải nhất quán: nếu hai record bằng nhau thì mã băm của chúng phải bằng nhau. `Float` và `Double` cũng thiết kế `equals`/`hashCode` theo cùng cách xử lý NaN và signed zero:

- Các NaN được xem là bằng nhau và có cùng hash code của wrapper tương ứng.
- `+0.0` và `-0.0` không bằng nhau và `Double.hashCode`/`Float.hashCode` phân biệt hai dạng zero.

Record tự sinh `hashCode` phù hợp với hợp đồng `equals`. Không dựa vào một giá trị hash cụ thể hoặc công thức kết hợp component: đặc tả không cố định thuật toán hash của record. Mã băm trùng nhau cũng không đồng nghĩa hai record bằng nhau.

Ví dụ sau cho thấy `HashSet` giữ riêng hai dạng zero nhưng chỉ giữ một phần tử đại diện cho các NaN bằng nhau:

```java
import java.util.HashSet;
import java.util.Set;

record Reading(double value) {}

Set<Reading> readings = new HashSet<>();
readings.add(new Reading(Double.NaN));
readings.add(new Reading(Double.NaN));
readings.add(new Reading(+0.0));
readings.add(new Reading(-0.0));

System.out.println(readings.size()); // 3
```

Kết quả là ba phần tử: một record NaN, một record positive zero và một record negative zero. `HashSet` dùng `hashCode` để tìm nhóm ứng viên, sau đó dùng `equals` để xác định phần tử trùng; vì vậy không nên suy luận tính bằng nhau chỉ từ việc hai mã băm giống nhau.

## 6. Chuẩn hóa nếu nghiệp vụ muốn coi hai dạng zero là một

Không phải ứng dụng nào cũng cần phân biệt `+0.0` và `-0.0`. Ví dụ, một hệ thống thống kê chỉ quan tâm giá trị nhiệt độ hiển thị có thể muốn hai dạng zero tương đương.

Có thể chuẩn hóa ngay trong compact constructor:

```java
record NormalizedMeasurement(double value) {
    NormalizedMeasurement {
        if (value == 0.0) {
            value = 0.0; // Gán lại positive zero cho cả +0.0 và -0.0
        }
    }
}

System.out.println(
    new NormalizedMeasurement(+0.0)
        .equals(new NormalizedMeasurement(-0.0))
); // true
```

Điều kiện `value == 0.0` đúng với cả hai dạng zero. Phép gán `value = 0.0` lưu một positive zero thống nhất. `NaN` không bị thay đổi bởi điều kiện này vì mọi phép so sánh bằng NaN với zero đều trả về `false`.

Nếu muốn từ chối NaN hoặc vô cực thay vì lưu chúng, có thể kiểm tra bằng API hiện hành:

```java
record FiniteMeasurement(double value) {
    FiniteMeasurement {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("value must be finite");
        }
        if (value == 0.0) {
            value = 0.0;
        }
    }
}
```

`Double.isFinite` có từ Java 8 và vẫn được hỗ trợ trong Java hiện đại. Điều kiện này từ chối cả NaN và hai dạng vô cực; việc chuẩn hóa zero tiếp tục bảo đảm chỉ còn một biểu diễn zero.

Chính sách chuẩn hóa phải theo yêu cầu miền nghiệp vụ. Không nên loại bỏ NaN, vô cực hoặc dấu của zero một cách tùy tiện trong hệ thống khoa học, tài chính, đo lường hoặc tính toán số học nơi các trạng thái này mang ý nghĩa.

## 7. Ví dụ hoàn chỉnh chạy từ Java 16

Đoạn chương trình dưới đây gom các trường hợp quan trọng vào một ví dụ. Lưu thành `RecordPrimitiveEquality.java`, biên dịch bằng `javac RecordPrimitiveEquality.java` và chạy bằng `java RecordPrimitiveEquality`.

```java
import java.util.HashSet;
import java.util.Set;

public class RecordPrimitiveEquality {
    record FloatValue(float value) {}
    record DoubleValue(double value) {}
    record Count(int value) {}

    public static void main(String[] args) {
        // NaN: primitive == false, record equals true.
        DoubleValue nan1 = new DoubleValue(Double.NaN);
        DoubleValue nan2 = new DoubleValue(
            Double.longBitsToDouble(0x7ff8_0000_0000_0001L)
        );
        System.out.println(Double.NaN == Double.NaN); // false
        System.out.println(nan1.equals(nan2));         // true

        // Signed zero: primitive == true, record equals false.
        DoubleValue plusZero = new DoubleValue(+0.0);
        DoubleValue minusZero = new DoubleValue(-0.0);
        System.out.println(+0.0 == -0.0);                // true
        System.out.println(plusZero.equals(minusZero)); // false

        // Float có cùng quy tắc đặc biệt.
        FloatValue floatNaN1 = new FloatValue(Float.NaN);
        FloatValue floatNaN2 = new FloatValue(
            Float.intBitsToFloat(0x7fc0_0001)
        );
        FloatValue floatPlusZero = new FloatValue(+0.0f);
        FloatValue floatMinusZero = new FloatValue(-0.0f);
        System.out.println(floatNaN1.equals(floatNaN2));       // true
        System.out.println(floatPlusZero.equals(floatMinusZero)); // false

        // Primitive nguyên vẫn so sánh theo giá trị thông thường.
        System.out.println(new Count(10).equals(new Count(10))); // true

        Set<DoubleValue> values = new HashSet<>();
        values.add(nan1);
        values.add(nan2);
        values.add(plusZero);
        values.add(minusZero);
        System.out.println(values.size()); // 3
    }
}
```

Đây là các hành vi được đặc tả và ổn định từ Java 16, không phải tính năng preview hay API thử nghiệm.

## 8. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| `new Measurement(Double.NaN).equals(new Measurement(Double.NaN))` là `false` vì NaN không bằng chính nó. | **Sai** | `Double.compare` xem hai NaN là bằng nhau. |
| Hai record chứa `+0.0` và `-0.0` mặc định bằng nhau vì `+0.0 == -0.0`. | **Sai** | `Double.compare` phân biệt signed zero. |
| Hai NaN có raw bit pattern khác nhau luôn tạo ra hai record khác nhau. | **Sai** | Các NaN được xem là bằng nhau theo quy tắc compare của wrapper. |
| Record chứa `int` bằng nhau nếu hai giá trị int bằng nhau. | **Đúng** | Kiểu nguyên không có trường hợp đặc biệt như NaN. |
| `HashSet` luôn gộp hai record có cùng hash code. | **Sai** | Collection còn kiểm tra `equals`; hash collision vẫn có thể chứa hai phần tử khác nhau. |
| Có thể dùng `value == 0.0` để phân biệt positive zero và negative zero. | **Sai** | Cả hai đều so sánh bằng zero; cần dùng phép kiểm tra khác. |

## 9. Checklist khi thiết kế record chứa số thực

1. Xác định NaN có phải trạng thái hợp lệ của dữ liệu hay cần từ chối.
2. Xác định nghiệp vụ có cần phân biệt `+0.0` và `-0.0` không.
3. Dùng `Double.isNaN`/`Float.isNaN` để kiểm tra NaN; dùng `Double.isFinite`/`Float.isFinite` nếu chỉ chấp nhận số hữu hạn.
4. Nếu muốn chuẩn hóa zero, thực hiện trong constructor để mọi instance lưu cùng một dạng.
5. Dùng `equals` của record làm quy tắc bình đẳng giá trị; không thay thế nó bằng phép so sánh `==` trong mã kiểm tra.
6. Khi record làm khóa `Map` hoặc phần tử `Set`, giữ các component ổn định sau khi tạo đối tượng.

**Ghi nhớ:** Với component `float` và `double`, `equals` mặc định của record theo ngữ nghĩa `Float.compare`/`Double.compare`: các NaN được xem là bằng nhau, còn `+0.0` và `-0.0` được xem là khác nhau. Đây là điểm khác biệt quan trọng so với toán tử `==` của primitive và vẫn áp dụng trong Java hiện đại.

## Tài liệu chính thức

- [Java SE 25 API — `java.lang.Record`, hợp đồng `equals` và `hashCode`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html).
- [Java SE 25 API — `java.lang.Double.compare` và `doubleToLongBits`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html).
- [Java SE 25 API — `java.lang.Float.compare` và `floatToIntBits`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Float.html).
- [Java Language Specification, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
