# NaN, signed zero và kiểm tra biên min, max của clamp

Java 21 bổ sung các overload **Math.clamp** để giới hạn một giá trị trong khoảng từ **min** đến **max**. Với số nguyên, thao tác này khá trực tiếp: giá trị nhỏ hơn cận dưới được đưa lên min, giá trị lớn hơn cận trên được đưa xuống max, còn giá trị nằm trong khoảng được giữ nguyên.

Với **float** và **double**, cần chú ý thêm hai trường hợp đặc biệt của số dấu phẩy động IEEE 754: NaN (Not a Number) và signed zero (**+0.0**, **-0.0**). **Math.clamp** có quy tắc cụ thể cho chúng: NaN ở vị trí value được truyền qua kết quả, NaN ở cận bị từ chối, và -0.0 được xem là nhỏ hơn +0.0. Hiểu các quy tắc này giúp tránh lỗi khi kiểm tra dữ liệu đo lường, tọa độ, tỷ lệ, âm lượng hoặc giá trị số đến từ hệ thống bên ngoài.

## 1. Math.clamp trong Java 21

Các overload chính thức:

```java
long Math.clamp(long value, long min, long max)
int Math.clamp(long value, int min, int max)
float Math.clamp(float value, float min, float max)
double Math.clamp(double value, double min, double max)
```

Java SE 21 không khai báo overload riêng có ba tham số int. Khi truyền ba đối số int, lời gọi được phân giải sang overload `clamp(long value, int min, int max)` bằng cách widening đối số value; kiểu trả về vẫn là int.

Phương thức giới hạn value trong khoảng đóng [min, max]:

- Nếu value nhỏ hơn min, trả về min.
- Nếu value lớn hơn max, trả về max.
- Nếu value nằm trong khoảng, trả về chính value.
- Nếu min lớn hơn max, ném **IllegalArgumentException**.

Ví dụ cơ bản:

```java
int pageSize = Math.clamp(250, 1, 100);   // 100
int retries = Math.clamp(-3, 0, 5);      // 0
int percentage = Math.clamp(75, 0, 100); // 75
```

Hai cận đều được tính là hợp lệ. Nếu value bằng min hoặc max, giá trị đó được giữ nguyên. Nếu min bằng max, mọi giá trị số hợp lệ đều được đưa về cận duy nhất đó.

**Math.clamp** được bổ sung từ Java 21, vì vậy có thể sử dụng trực tiếp trong mã nguồn Java 21 mà không cần thư viện ngoài.

## 2. Kiểm tra biên min và max

Hai cận cần tạo thành một khoảng hợp lệ trước khi áp dụng clamp. Với các kiểu số nguyên, điều kiện hợp lệ là min nhỏ hơn hoặc bằng max.

```java
static int bounded(int value, int min, int max) {
    return Math.clamp(value, min, max);
}
```

Nếu caller truyền min lớn hơn max, phương thức ném **IllegalArgumentException**; nó không tự hoán đổi hai cận.

```java
int result = Math.clamp(10, 100, 0);
// IllegalArgumentException vì min > max
```

Không nên âm thầm đổi chỗ min và max nếu thứ tự cận phản ánh cấu hình nghiệp vụ. Ví dụ, min lớn hơn max có thể là lỗi cấu hình cần được phát hiện sớm thay vì bị che giấu.

### 2.1. Kiểm tra khoảng trước khi xử lý nhiều giá trị

Nếu một khoảng được dùng lặp lại, nên xác thực cận tại thời điểm tạo cấu hình:

```java
record IntRange(int min, int max) {
    IntRange {
        if (min > max) {
            throw new IllegalArgumentException(
                    "min phải nhỏ hơn hoặc bằng max");
        }
    }

    int clamp(int value) {
        return Math.clamp(value, min, max);
    }
}
```

Cách này đảm bảo đối tượng IntRange luôn đại diện cho một khoảng hợp lệ. Các đoạn code sử dụng range không cần lặp lại cùng một kiểm tra cấu hình.

Với float và double, xác thực cận cần thêm quy tắc NaN và signed zero, được trình bày ở các phần sau.

## 3. NaN là gì?

NaN là giá trị dấu phẩy động biểu thị kết quả không phải một số thực có thứ tự thông thường. NaN có thể xuất hiện từ các phép toán không có kết quả số hợp lệ:

```java
double a = 0.0 / 0.0;
double b = Math.sqrt(-1.0);

System.out.println(Double.isNaN(a)); // true
System.out.println(Double.isNaN(b)); // true
```

NaN có một số đặc điểm quan trọng:

- NaN == NaN trả về false.
- Các phép so sánh <, >, <=, >= với NaN đều trả về false.
- Double.isNaN(value) và Float.isNaN(value) là cách kiểm tra rõ ràng.
- NaN không biểu diễn một giá trị nhỏ hơn hoặc lớn hơn các số khác; nó không có thứ tự số học thông thường.

Vì vậy, không thể dùng các phép so sánh thông thường để kiểm tra NaN. Ví dụ:

```java
double value = Double.NaN;

if (value < 0.0) {
    // Không chạy
} else if (value > 1.0) {
    // Cũng không chạy
} else {
    // Nhánh này chạy, nhưng value vẫn là NaN.
}
```

Đây là lý do cần hiểu riêng quy tắc NaN của Math.clamp, thay vì tự suy luận kết quả chỉ từ các phép so sánh.

## 4. NaN ở value và NaN ở hai cận

Với overload Math.clamp(float, float, float) và Math.clamp(double, double, double), Java quy định hai trường hợp khác nhau:

| Vị trí NaN | Hành vi |
|---|---|
| value là NaN | Kết quả là NaN |
| min là NaN | Ném IllegalArgumentException |
| max là NaN | Ném IllegalArgumentException |

Ví dụ NaN ở value:

```java
double result = Math.clamp(Double.NaN, 0.0, 1.0);

System.out.println(Double.isNaN(result)); // true
```

Phương thức không tự thay NaN bằng min hoặc max. Nếu NaN có nghĩa là dữ liệu đầu vào không hợp lệ hoặc bị thiếu, ứng dụng phải quyết định chính sách xử lý riêng.

Ví dụ NaN ở cận:

```java
double result = Math.clamp(0.5, Double.NaN, 1.0);
// IllegalArgumentException
```

Cận NaN không xác định được khoảng số hợp lệ, nên bị từ chối. Tương tự, max = Double.NaN cũng ném IllegalArgumentException.

### 4.1. Kiểm tra NaN trước hay để clamp xử lý?

Nếu nghiệp vụ muốn giữ nguyên ý nghĩa “NaN là kết quả chưa xác định”, có thể để Math.clamp truyền NaN qua.

Nếu nghiệp vụ yêu cầu dữ liệu phải là số hợp lệ, hãy kiểm tra trước:

```java
static double clampMeasurement(double value) {
    if (Double.isNaN(value)) {
        throw new IllegalArgumentException(
                "Giá trị đo không được là NaN");
    }

    return Math.clamp(value, 0.0, 100.0);
}
```

Nếu cần loại cả vô cực, dùng Double.isFinite(value):

```java
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException(
            "Giá trị phải hữu hạn");
}
```

Math.clamp cho phép value là vô cực và sẽ đưa nó về cận hữu hạn nếu khoảng giới hạn hữu hạn. Việc có chấp nhận vô cực hay không là quyết định nghiệp vụ, không phải mặc định của clamp.

## 5. Signed zero: +0.0 và -0.0

IEEE 754 có hai cách biểu diễn số 0:

- **+0.0**: zero mang dấu dương.
- **-0.0**: zero mang dấu âm.

Hai giá trị này bằng nhau theo toán tử ==:

```java
System.out.println(+0.0 == -0.0); // true
```

Tuy nhiên, chúng có thể tạo ra kết quả khác nhau trong một số phép toán:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Vì vậy, không nên mặc định rằng hai signed zero luôn có thể thay thế cho nhau. Khi xử lý dấu phẩy động, dấu của zero có thể mang thông tin về hướng hoặc kết quả tính toán trước đó.

### 5.1. So sánh signed zero

Các phép so sánh số học cơ bản xem +0.0 và -0.0 bằng nhau:

```java
System.out.println(-0.0 == +0.0); // true
System.out.println(-0.0 < +0.0);  // false
System.out.println(-0.0 > +0.0);  // false
```

Nhưng Double.compare phân biệt thứ tự của chúng:

```java
System.out.println(Double.compare(-0.0, +0.0) < 0); // true
```

Math.clamp cũng xem -0.0 nhỏ hơn +0.0, theo quy tắc được nêu trong API Java 21. Đây là điểm khác biệt quan trọng so với việc tự viết clamp bằng toán tử < và >.

## 6. Signed zero ảnh hưởng đến kết quả clamp như thế nào?

Ví dụ trong Java API:

```java
double result = Math.clamp(-0.0, 0.0, 1.0);

System.out.println(result); // 0.0
```

Mặc dù -0.0 == +0.0 là true, Math.clamp xem -0.0 nhỏ hơn cận dưới +0.0, nên trả về cận dưới +0.0.

Ví dụ theo chiều ngược lại:

```java
double result = Math.clamp(+0.0, -1.0, -0.0);

System.out.println(result); // -0.0
```

Ở đây +0.0 lớn hơn cận trên -0.0, nên kết quả là -0.0.

Một số trường hợp tiêu biểu:

| Lời gọi | Kết quả |
|---|---|
| Math.clamp(-0.0, -0.0, +0.0) | -0.0 |
| Math.clamp(+0.0, -0.0, +0.0) | +0.0 |
| Math.clamp(-0.0, +0.0, 1.0) | +0.0 |
| Math.clamp(+0.0, -1.0, -0.0) | -0.0 |
| Math.clamp(-0.0, -0.0, -0.0) | -0.0 |

Nếu min = +0.0 và max = -0.0, khoảng bị đảo theo thứ tự signed-zero của Math.clamp, do đó phương thức ném IllegalArgumentException. Điều này có thể gây bất ngờ nếu chỉ kiểm tra bằng toán tử min > max, vì phép so sánh primitive thông thường không xem +0.0 lớn hơn -0.0.

## 7. Kiểm tra dấu của zero trong chương trình

In giá trị bằng System.out.println có thể không đủ để kiểm tra chính xác mọi tình huống. Có thể dùng Double.doubleToRawLongBits để xem bit dấu của double.

```java
static void printZeroSign(double value) {
    long bits = Double.doubleToRawLongBits(value);

    if (value == 0.0) {
        System.out.println(
                bits < 0 ? "negative zero" : "positive zero");
    } else {
        System.out.println(value);
    }
}

public static void main(String[] args) {
    printZeroSign(Math.clamp(-0.0, 0.0, 1.0));
    printZeroSign(Math.clamp(+0.0, -1.0, -0.0));
}
```

Bit cao nhất của biểu diễn double là bit dấu. Với zero:

- +0.0 có bit pattern 0x0000000000000000.
- -0.0 có bit pattern 0x8000000000000000.

Với float, dùng Float.floatToRawIntBits để kiểm tra bit dấu tương ứng. Cách kiểm tra bit phù hợp khi cần xác nhận việc bảo toàn dấu zero trong thuật toán hoặc khi viết test cho thư viện số học.

## 8. Vô cực và các giá trị ở biên

Math.clamp cũng xử lý Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY, và các giá trị vô cực của float.

Nếu khoảng giới hạn hữu hạn:

```java
double upper = Math.clamp(
        Double.POSITIVE_INFINITY, -10.0, 10.0); // 10.0

double lower = Math.clamp(
        Double.NEGATIVE_INFINITY, -10.0, 10.0); // -10.0
```

Nếu cận cũng là vô cực, chúng vẫn có thể tạo thành khoảng hợp lệ:

```java
double value = Math.clamp(
        5.0,
        Double.NEGATIVE_INFINITY,
        Double.POSITIVE_INFINITY
); // 5.0
```

Điều cần phân biệt là NaN không có thứ tự số học để làm cận, còn vô cực là giá trị có thứ tự và có thể dùng làm cận. Nếu ứng dụng chỉ chấp nhận số hữu hạn, cần kiểm tra Double.isFinite hoặc Float.isFinite trước khi clamp.

## 9. Kiểm tra min/max đặc biệt với float và double

Với kiểu dấu phẩy động, Math.clamp ném IllegalArgumentException nếu:

- min là NaN.
- max là NaN.
- min lớn hơn max theo thứ tự mà Math.clamp áp dụng.
- min là +0.0 và max là -0.0.

Ví dụ:

```java
Math.clamp(0.5, Double.NaN, 1.0); // IllegalArgumentException
Math.clamp(0.5, 0.0, Double.NaN); // IllegalArgumentException
Math.clamp(0.5, 2.0, 1.0);        // IllegalArgumentException
Math.clamp(0.0, +0.0, -0.0);      // IllegalArgumentException
```

Các cận min và max nên được xác thực ngay khi nhận cấu hình. Đặc biệt, không nên chỉ dùng min > max để kiểm tra cặp signed zero, vì phép so sánh primitive coi hai zero bằng nhau.

Ví dụ hàm xác thực:

```java
static void validateBounds(double min, double max) {
    if (Double.isNaN(min) || Double.isNaN(max)) {
        throw new IllegalArgumentException(
                "Cận không được là NaN");
    }

    if (Double.compare(min, max) > 0) {
        throw new IllegalArgumentException(
                "min phải nhỏ hơn hoặc bằng max");
    }
}
```

Double.compare phân biệt -0.0 và +0.0, nên phát hiện được cả trường hợp min = +0.0, max = -0.0. Dù vậy, nếu chỉ cần giới hạn giá trị, nên gọi trực tiếp Math.clamp để sử dụng đúng hợp đồng API; hàm xác thực riêng hữu ích khi muốn báo lỗi cấu hình sớm hoặc gắn thông tin nghiệp vụ vào thông báo lỗi.

## 10. Clamp số nguyên và biên MIN_VALUE, MAX_VALUE

Với int và long, các cận min/max được kiểm tra bằng thứ tự số nguyên thông thường. Một ứng dụng thường cần đưa một giá trị long về miền biểu diễn của int.

Ép kiểu trực tiếp có thể làm tràn và đổi giá trị:

```java
long raw = 5_000_000_000L;
int narrowed = (int) raw; // Tràn theo quy tắc chuyển đổi narrowing
```

Java 21 có overload Math.clamp(long value, int min, int max) để giới hạn và trả về int an toàn:

```java
long raw = 5_000_000_000L;

int safe = Math.clamp(
        raw,
        Integer.MIN_VALUE,
        Integer.MAX_VALUE
);

System.out.println(safe); // Integer.MAX_VALUE
```

Nếu raw nhỏ hơn Integer.MIN_VALUE, kết quả là Integer.MIN_VALUE. Nếu lớn hơn Integer.MAX_VALUE, kết quả là Integer.MAX_VALUE. Nếu nằm trong miền int, giá trị được giữ nguyên và chuyển thành int mà không mất dữ liệu.

Đây là saturating conversion (chuyển đổi bão hòa): giá trị ngoài miền được đưa về biên gần nhất. Nó khác với ép kiểu narrowing, vốn giữ các bit thấp và có thể tạo ra một số khác xa giá trị ban đầu.

### 10.1. Clamp không thay thế kiểm tra overflow trong phép tính

Math.clamp giới hạn kết quả đã có; nó không tự phát hiện overflow xảy ra trước khi gọi.

```java
int total = current + increment;
int bounded = Math.clamp(total, 0, 100);
```

Nếu phép cộng current + increment đã overflow, clamp chỉ nhận giá trị int bị tràn đó và giới hạn nó. Khi cần phát hiện overflow, hãy dùng Math.addExact:

```java
int total = Math.addExact(current, increment);
int bounded = Math.clamp(total, 0, 100);
```

Tách rõ hai nhiệm vụ: addExact kiểm tra phép tính có vượt miền biểu diễn hay không; clamp áp dụng giới hạn nghiệp vụ lên giá trị hợp lệ.

## 11. Vì sao không nên tự viết clamp bằng toán tử so sánh?

Một cách viết thường gặp:

```java
static double clampManually(
        double value, double min, double max) {
    if (value < min) {
        return min;
    }
    if (value > max) {
        return max;
    }
    return value;
}
```

Cách viết này không tương đương hoàn toàn với Math.clamp:

- Nếu value là NaN, hai phép so sánh đều false và hàm trả lại NaN; phần này có vẻ phù hợp.
- Nếu min hoặc max là NaN, hàm không báo lỗi cấu hình như Math.clamp.
- Nếu min = +0.0 và max = -0.0, phép so sánh thông thường không nhận ra khoảng đảo.
- Khi value là signed zero, phép so sánh thông thường không thực hiện thứ tự đặc biệt của Math.clamp.

Nếu thay bằng Math.max(min, Math.min(value, max)), vẫn cần tự xác thực cận. Math.min và Math.max có quy tắc NaN/signed-zero riêng, nhưng không thực hiện hợp đồng kiểm tra khoảng của Math.clamp.

Vì Java 21 đã có API chuẩn cho thao tác này, nên ưu tiên Math.clamp để mã nguồn thể hiện rõ ý định và tuân thủ chính xác các trường hợp biên.

## 12. Ví dụ tổng hợp: chuẩn hóa giá trị cảm biến

Giả sử cảm biến trả về nhiệt độ dạng double. Ứng dụng chỉ hiển thị trong khoảng từ -40 đến 125 độ C. Có thể clamp các giá trị hữu hạn hoặc vô cực về khoảng đó, nhưng cần quyết định rõ cách xử lý NaN:

```java
static double displayTemperature(double raw) {
    if (Double.isNaN(raw)) {
        throw new IllegalArgumentException(
                "Cảm biến không trả về nhiệt độ hợp lệ");
    }

    return Math.clamp(raw, -40.0, 125.0);
}
```

Ở đây:

- Giá trị nhỏ hơn -40 được đưa về -40.
- Giá trị lớn hơn 125 được đưa về 125.
- Giá trị nằm trong khoảng được giữ nguyên.
- NaN bị từ chối theo chính sách ứng dụng.
- Nếu cần từ chối cả vô cực, thêm kiểm tra Double.isFinite(raw).

Không phải mọi lĩnh vực đều nên clamp dữ liệu ngoài phạm vi. Trong hệ thống cảnh báo an toàn, giá trị vượt ngưỡng có thể là tín hiệu sự cố cần giữ nguyên hoặc phát cảnh báo, thay vì bị giới hạn để hiển thị như một giá trị bình thường. Hãy chọn clamp theo mục tiêu nghiệp vụ.

## 13. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cho rằng NaN luôn bị clamp về min hoặc max | NaN không có thứ tự số học | Kiểm tra chính sách NaN; Math.clamp trả NaN nếu value là NaN |
| Truyền NaN làm min hoặc max | Cận không xác định được khoảng hợp lệ | Xác thực cận và từ chối NaN |
| Nghĩ -0.0 và +0.0 giống nhau trong mọi trường hợp | Primitive equality không phân biệt dấu zero, nhưng Math.clamp có thứ tự riêng | Dùng quy tắc signed zero của API; kiểm tra bit nếu cần |
| Chỉ kiểm tra min > max bằng toán tử > | Không phát hiện cặp cận +0.0, -0.0 bị đảo | Dùng Math.clamp hoặc Double.compare khi xác thực |
| Ép long sang int trước khi clamp | Narrowing conversion có thể làm tràn | Dùng Math.clamp(long, int, int) |
| Nghĩ clamp phát hiện overflow của phép tính trước đó | Clamp chỉ nhận giá trị đã tính | Dùng Math.addExact, multiplyExact khi cần kiểm tra overflow |
| Dùng clamp để che mọi dữ liệu ngoài miền | Có thể che giấu lỗi cảm biến hoặc lỗi nghiệp vụ | Quyết định rõ khi nào giới hạn và khi nào phải từ chối/cảnh báo |

## 14. Nguyên tắc sử dụng trong Java 21

Khi dùng Math.clamp, hãy kiểm tra lần lượt:

1. Chọn đúng overload theo kiểu dữ liệu và kiểu kết quả cần nhận.
2. Bảo đảm min <= max; với float/double, nhớ cả quy tắc signed zero.
3. Xác định chính sách cho NaN ở value: truyền qua hay từ chối ở tầng nghiệp vụ.
4. Không dùng NaN làm cận; API ném IllegalArgumentException.
5. Quyết định có chấp nhận vô cực hay chỉ chấp nhận giá trị hữu hạn.
6. Dùng overload clamp(long, int, int) khi cần giới hạn an toàn trước khi chuyển long sang int.
7. Dùng Math.addExact hoặc API kiểm tra overflow riêng nếu phép tính tạo ra value có thể bị tràn trước khi clamp.
8. Kiểm tra signed zero bằng Double.doubleToRawLongBits hoặc Float.floatToRawIntBits khi dấu của zero có ý nghĩa.

Math.clamp giúp giới hạn giá trị một cách nhất quán, nhưng NaN, signed zero và cận min/max vẫn cần được hiểu đúng. Với số nguyên, trọng tâm là khoảng hợp lệ và overflow trước khi clamp. Với float/double, cần thêm chính sách cho NaN, vô cực và thứ tự -0.0 < +0.0. Áp dụng đúng các quy tắc này giúp xử lý dữ liệu số ổn định hơn trong Java 21 và các JDK hiện hành.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — Math.clamp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#clamp(double,double,double))
- [Oracle Java SE 21 API — Double: Floating-point Equality, Equivalence, and Comparison](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [Oracle Java SE 21 API — Float](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html)
