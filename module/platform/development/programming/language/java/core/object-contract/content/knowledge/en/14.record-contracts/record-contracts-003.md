# So sánh thành phần float hoặc double theo quy tắc lớp bao trong Java record

## Mục tiêu

Trong Java 17+, `record` được sinh sẵn `equals(Object)`, `hashCode()` và `toString()` từ các thành phần (record components). Với thành phần kiểu nguyên thủy `float` hoặc `double`, **phép so sánh bằng nhau của record tuân theo ngữ nghĩa so sánh của lớp bao tương ứng** (`Float.compare` hoặc `Double.compare`), thay vì áp dụng trực tiếp toán tử số học `==`.

Bài học giúp bạn:

- Hiểu vì sao hai record chứa `NaN` vẫn có thể `equals` nhau, dù `NaN == NaN` là `false`.
- Hiểu vì sao `+0.0` và `-0.0` **khác nhau theo `record.equals`**, dù `+0.0 == -0.0` là `true`.
- Nắm cách so sánh thành phần nguyên thủy `float`/`double` và thành phần tham chiếu `Float`/`Double`.
- Hiểu ý nghĩa của `hashCode`, tính nhất quán của quan hệ bằng nhau, và cách dùng record trong `HashSet`/`HashMap`.
- Biết khi nào cần chính sách bằng nhau riêng của miền nghiệp vụ, như coi hai zero khác dấu là một giá trị hay so sánh gần đúng.

## 1. Hợp đồng equals của record

Với một khai báo:

```java
record Measurement(float level, double precision) {}
```

trình biên dịch cung cấp mặc định các phương thức quan trọng, gồm `equals(Object)` và `hashCode()`. Theo đặc tả `java.lang.Record`, một phép so sánh bằng nhau mặc định giữa hai record yêu cầu:

1. Đối tượng so sánh thuộc **cùng lớp record**.
2. Các thành phần tương ứng đều bằng nhau theo quy tắc cho **kiểu** của mỗi thành phần.
3. Với thành phần kiểu tham chiếu, kết quả tương đương `Objects.equals(componentA, componentB)`.
4. Với thành phần kiểu nguyên thủy, kết quả tương đương việc phương thức `compare` của **lớp bao tương ứng** trả `0`. Với `float` và `double`, đây là `Float.compare(a, b) == 0` hoặc `Double.compare(a, b) == 0`.

Mô tả ở trên là **quy tắc ngữ nghĩa**; JVM không bắt buộc phải thực sự tạo đối tượng bao (boxing) hay gọi đúng các phương thức đó trong quá trình thực thi. Thuật toán nội bộ có thể được tối ưu hoặc thay đổi, miễn kết quả đúng hợp đồng.

Vì hai thành phần có kiểu `float` và `double`, có thể hình dung logic của `equals` như sau:

```java
// MÃ GIẢ để giải thích ngữ nghĩa; không phải mã compiler bắt buộc sinh ra.
boolean equivalent(Measurement a, Measurement b) {
    return Float.compare(a.level(), b.level()) == 0
            && Double.compare(a.precision(), b.precision()) == 0;
}
```

Đoạn trên giả định `a` và `b` đều khác `null` và cùng lớp `Measurement`. Trong thực tế, `record.equals` còn xử lý trường hợp chính đối tượng, `null` và khác lớp đúng hợp đồng `Object.equals`.

**Tại sao không dùng `==` cho hai thành phần số thực?** Vì `==` không tạo thành một quan hệ tương đương cho mọi giá trị IEEE 754, đặc biệt với `NaN`. `equals` cần giữ tính phản xạ (một đối tượng bằng chính nó), tính đối xứng và tính bắc cầu. Cách so sánh theo lớp bao xử lý các trường hợp biên một cách nhất quán.

## 2. So sánh `==` khác `Float.compare` và `Double.compare`

Java có các giá trị dấu phẩy động đặc biệt:

- `Float.NaN` và `Double.NaN`: không phải số (Not a Number).
- `+0.0` và `-0.0`: hai giá trị zero có dấu khác nhau.
- `Float.POSITIVE_INFINITY`, `Float.NEGATIVE_INFINITY` và các giá trị tương ứng của `Double`.

So sánh theo toán tử số học và theo quy tắc lớp bao khác nhau ở những trường hợp quan trọng:

| Hai giá trị | Toán tử nguyên thủy `a == b` | `Float.compare` / `Double.compare` trả `0`? | Hai record cùng lớp chỉ chứa giá trị này `equals` nhau? |
| --- | --- | --- | --- |
| `1.5` và `1.5` | `true` | Có | Có |
| `+0.0` và `-0.0` | `true` | **Không** | **Không** |
| `NaN` và `NaN` | **`false`** | Có | Có |
| `+Infinity` và `+Infinity` | `true` | Có | Có |
| `-Infinity` và `+Infinity` | `false` | Không | Không |

### 2.1. NaN: `==` không bằng chính nó, nhưng record equals có

```java
double a = Double.NaN;
double b = Double.NaN;

System.out.println(a == b);                  // false
System.out.println(Double.compare(a, b) == 0); // true
```

Với toán tử `==`, một NaN luôn **không bằng** bất kỳ giá trị nào, kể cả NaN. Với `Double.compare`, các NaN được xem là cùng nhóm giá trị cho quan hệ bằng nhau của lớp bao; do đó so sánh trả `0`. `Float.compare` cũng có đặc tính tương ứng.

Đối với record, điều này là quan trọng: record chứa NaN vẫn bằng chính nó và có thể bằng một record khác cùng lớp với các thành phần tương ứng là NaN.

### 2.2. Signed zero: `==` coi bằng nhau, record equals phân biệt

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero);              // true
System.out.println(Double.compare(positiveZero, negativeZero)); // 1
```

`Double.compare(+0.0, -0.0)` trả một số **dương**; ở đây ví dụ cho `1`. Tương tự, `Double.compare(-0.0, +0.0)` trả số âm. Quy tắc lớp bao đặt `-0.0` thấp hơn `+0.0`.

Hai zero có thể tạo hành vi khác nhau trong phép toán: `1.0 / +0.0` là dương vô cực, còn `1.0 / -0.0` là âm vô cực. Việc phân biệt chúng trong quan hệ bằng nhau có ý nghĩa khi cần giữ đúng biểu diễn số thực.

### 2.3. Đây là so sánh đại diện, không phải so sánh gần đúng

`Float.compare` và `Double.compare` **không** kiểm tra “hai số gần nhau đủ nhỏ”. Chúng có thứ tự và quy tắc bằng nhau cụ thể cho các giá trị IEEE 754, gồm NaN và hai signed zero.

Ví dụ, hai số `0.1 + 0.2` và `0.3` có thể khác nhau do cách biểu diễn nhị phân; record mặc định **không tự áp dụng epsilon** để coi chúng bằng nhau. Muốn chính sách “gần bằng nhau”, cần kiểm tra riêng theo quy tắc phù hợp với bài toán số học; không nên giả định record áp dụng cơ chế làm tròn.

## 3. Ví dụ Java 17+ hoàn chỉnh: record với float và double

Tạo tệp **`RecordFloatingEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class RecordFloatingEqualityDemo {
    record Measurement(float level, double precision) {}

    public static void main(String[] args) {
        Measurement nanA =
                new Measurement(Float.NaN, Double.NaN);
        Measurement nanB =
                new Measurement(Float.NaN, Double.NaN);

        Measurement positive =
                new Measurement(+0.0f, +0.0d);
        Measurement negative =
                new Measurement(-0.0f, +0.0d);

        System.out.println("Float.NaN == Float.NaN: "
                + (Float.NaN == Float.NaN));
        System.out.println("Double.NaN == Double.NaN: "
                + (Double.NaN == Double.NaN));
        System.out.println("nanA.equals(nanB): "
                + nanA.equals(nanB));
        System.out.println("nanA equals itself: "
                + nanA.equals(nanA));
        System.out.println("nan hashes equal: "
                + (nanA.hashCode() == nanB.hashCode()));

        System.out.println("+0.0f == -0.0f: "
                + (+0.0f == -0.0f));
        System.out.println("positive.equals(negative): "
                + positive.equals(negative));
        System.out.println("Float.compare(+0.0f, -0.0f) == 0: "
                + (Float.compare(+0.0f, -0.0f) == 0));

        Set<Measurement> measurements = new HashSet<>();
        measurements.add(nanA);
        measurements.add(nanB);
        measurements.add(positive);
        measurements.add(negative);

        System.out.println("set size: " + measurements.size());
        System.out.println("set contains equal NaN record: "
                + measurements.contains(
                        new Measurement(Float.NaN, Double.NaN)));
    }
}
```

Biên dịch và chạy:

```bash
javac RecordFloatingEqualityDemo.java
java RecordFloatingEqualityDemo
```

**Đầu ra chính xác:**

```text
Float.NaN == Float.NaN: false
Double.NaN == Double.NaN: false
nanA.equals(nanB): true
nanA equals itself: true
nan hashes equal: true
+0.0f == -0.0f: true
positive.equals(negative): false
Float.compare(+0.0f, -0.0f) == 0: false
set size: 3
set contains equal NaN record: true
```

Giải thích theo trình tự:

1. `nanA` và `nanB` là **hai đối tượng record riêng**, nhưng chúng có cùng lớp và các thành phần đều tương đương theo `Float.compare`/`Double.compare`. `equals` trả `true`.
2. Khi `equals` là `true`, hợp đồng yêu cầu `hashCode` bằng nhau. Vì vậy, `nanA.hashCode() == nanB.hashCode()` là `true`. Không cần biết con số hash cụ thể.
3. `positive` và `negative` chỉ khác dấu của giá trị zero trong `level`. Vì `Float.compare(+0.0f, -0.0f) != 0`, chúng **không bằng nhau** theo `equals`.
4. `HashSet` chỉ giữ một trong hai record `nanA`/`nanB` tương đương, nhưng giữ cả record zero dương và zero âm. Tổng số phần tử là **3**.
5. `HashSet.contains` dùng `hashCode` và `equals` của record, do đó tìm được record mới có các thành phần NaN tương đương.

Điểm cần nhớ: **không nên thay việc so sánh record bằng cách so sánh riêng các thành phần nguyên thủy với `==`**, vì điều đó có thể cho câu trả lời khác.

## 4. Thành phần Float/Double là đối tượng: cùng quy tắc lớp bao

Một record cũng có thể khai báo thành phần **kiểu tham chiếu** `Float` hoặc `Double`:

```java
record WrappedMeasurement(Float level, Double precision) {}
```

Với thành phần tham chiếu, `record.equals` dùng ngữ nghĩa tương đương `Objects.equals`. Vì `Float.equals(Object)` và `Double.equals(Object)` tuân theo quy tắc tương tự `Float.compare`/`Double.compare` về NaN và signed zero, ta vẫn có:

- Hai đối tượng bao chứa NaN tương đương: **bằng nhau**.
- Một đối tượng bao chứa `+0.0` và một đối tượng bao chứa `-0.0`: **không bằng nhau**.
- Hai thành phần đều `null`: bằng nhau đối với riêng thành phần đó.
- Một bên `null`, bên kia khác `null`: khác nhau.

**Khác biệt quan trọng:** Thành phần `float`/`double` nguyên thủy không thể `null`; thành phần `Float`/`Double` có thể `null`. Nếu dùng wrapper làm record component, hãy quyết định rõ liệu `null` có được phép trong miền nghiệp vụ hay không.

### 4.1. Ví dụ chạy được: wrapper và null

**Tệp `RecordWrappedFloatingDemo.java`:**

```java
import java.util.Objects;

public class RecordWrappedFloatingDemo {
    record WrappedMeasurement(Float level, Double precision) {}

    public static void main(String[] args) {
        WrappedMeasurement nanA =
                new WrappedMeasurement(Float.NaN, Double.NaN);
        WrappedMeasurement nanB =
                new WrappedMeasurement(Float.NaN, Double.NaN);
        WrappedMeasurement plus =
                new WrappedMeasurement(+0.0f, +0.0d);
        WrappedMeasurement minus =
                new WrappedMeasurement(-0.0f, +0.0d);
        WrappedMeasurement noValueA =
                new WrappedMeasurement(null, null);
        WrappedMeasurement noValueB =
                new WrappedMeasurement(null, null);

        System.out.println("nan wrapped equal: "
                + nanA.equals(nanB));
        System.out.println("wrapped zero signs equal: "
                + plus.equals(minus));
        System.out.println("null components equal: "
                + noValueA.equals(noValueB));
        System.out.println("one null differs: "
                + noValueA.equals(
                        new WrappedMeasurement(null, 1.0)));

        System.out.println("Float.equals for NaN: "
                + Float.valueOf(Float.NaN).equals(
                        Float.valueOf(Float.NaN)));
        System.out.println("Double.equals for signed zeros: "
                + Double.valueOf(+0.0d).equals(
                        Double.valueOf(-0.0d)));
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(null, null));
    }
}
```

```bash
javac RecordWrappedFloatingDemo.java
java RecordWrappedFloatingDemo
```

**Đầu ra chính xác:**

```text
nan wrapped equal: true
wrapped zero signs equal: false
null components equal: true
one null differs: false
Float.equals for NaN: true
Double.equals for signed zeros: false
Objects.equals(null, null): true
```

Nếu tham số không được phép `null`, có thể kiểm tra trong compact constructor:

```java
record StrictMeasurement(Float level, Double precision) {
    StrictMeasurement {
        java.util.Objects.requireNonNull(level);
        java.util.Objects.requireNonNull(precision);
    }
}
```

Đoạn khai báo này chỉ minh họa cách kiểm tra trong constructor. Nó có thể đặt vào một tệp Java phù hợp; với compact constructor, các thành phần được gán tự động sau khi chạy thân constructor thành công.

## 5. NaN có nhiều biểu diễn bit nhưng được so tương đương

Dữ liệu IEEE 754 có thể có nhiều **bit pattern** mang ý nghĩa NaN. Khi `Float.equals`/`Double.equals` và `Float.compare`/`Double.compare` so sánh, NaN được đối xử theo dạng **chuẩn hóa** cho mục đích bình đẳng. Vì vậy các NaN có payload khác nhau vẫn được xem là tương đương theo `record.equals` mặc định.

Có thể liên hệ với những phương thức chuẩn:

- `Float.floatToIntBits(value)` chuẩn hóa các bit pattern NaN thành một dạng chuẩn; `Double.doubleToLongBits(value)` tương tự.
- `Float.floatToRawIntBits(value)` và `Double.doubleToRawLongBits(value)` cho truy cập bit thô, không chủ động chuẩn hóa NaN; việc giữ nguyên payload cụ thể qua phép toán/chuyển đổi có thể phụ thuộc môi trường và cách giá trị được xử lý.
- `Float.compare`/`Double.compare` có quy tắc bằng nhau nhất quán với lớp bao, trong đó tất cả NaN được xem là bằng nhau.

**Đừng suy ra record mặc định giữ hoặc phân biệt payload NaN.** Record có thành phần `float`/`double` so theo ngữ nghĩa lớp bao. Nếu dữ liệu nghiệp vụ cần phân biệt từng bit pattern, cần **mô hình biểu diễn riêng** (chẳng hạn lưu bit trong thành phần `int`/`long`) và định nghĩa rõ cách dữ liệu được thu thập, lưu trữ.

## 6. HashCode của record tương thích với equals, nhưng không cố định công thức

`record` sinh sẵn `hashCode()` dựa trên các thành phần. Vì record sinh `equals` cho NaN và signed zero theo quy tắc lớp bao, `hashCode` phải phù hợp với cùng quan hệ bằng nhau:

```text
Nếu a.equals(b) == true
thì a.hashCode() == b.hashCode() bắt buộc true.
```

Do đó, hai record chứa NaN tương đương có cùng hash. Ngược lại, hai record có một thành phần zero khác dấu không `equals` nhau; hash của chúng **được phép** khác, nhưng không bắt buộc phải khác (collision vẫn hợp lệ).

Không nên phụ thuộc vào một **giá trị hash chính xác** hay giả định thuật toán sinh hash của record luôn là `Objects.hash(component1, component2, ...)`. Đặc tả cho phép triển khai record dùng thuật toán khác miễn tuân thủ hợp đồng. Hash cũng không phải địa chỉ bộ nhớ, khóa bảo mật hoặc định danh duy nhất.

### 6.1. Vì sao HashMap và HashSet nhận ra NaN?

`HashSet`/`HashMap` sử dụng `hashCode` cùng `equals` của khóa. Nếu record được tạo với NaN ở các thành phần số thực, hai record có cùng các thành phần tương đương theo quy tắc của record sẽ được nhận diện như cùng khóa/giá trị. Đây là lợi ích của việc record dùng quan hệ bằng nhau có tính phản xạ và nhất quán.

Không áp dụng quy tắc nhầm lẫn:

```java
record Reading(double value) {}

Reading x = new Reading(Double.NaN);
Reading y = new Reading(Double.NaN);

// x.equals(y) là true.
// x.value() == y.value() lại là false.
```

Đoạn trên là mã minh họa đặt trong ngữ cảnh có khai báo record và phương thức phù hợp. Sự khác biệt không làm vi phạm hợp đồng: **đối tượng record** và **phép so sánh toán học trên nguyên thủy** theo hai chính sách bằng nhau khác nhau.

## 7. Khi nào cần chính sách “+0.0 bằng -0.0”?

Nhiều miền nghiệp vụ xem `+0.0` và `-0.0` là **cùng giá trị zero**, không quan tâm dấu của nó. Nếu vậy, hành vi mặc định của record có thể không phù hợp. Thay vì ghi đè `equals` tùy tiện, một cách đơn giản là **chuẩn hóa đầu vào** tại constructor rồi giữ nguyên `equals/hashCode` được sinh.

### 7.1. Chuẩn hóa zero trong compact constructor

**Tệp `NormalizedZeroRecordDemo.java`:**

```java
import java.util.HashSet;
import java.util.Set;

public class NormalizedZeroRecordDemo {
    record Reading(float value, double correction) {
        Reading {
            if (value == 0.0f) {
                value = 0.0f; // Chuẩn hóa cả -0.0f thành +0.0f.
            }
            if (correction == 0.0d) {
                correction = 0.0d; // Chuẩn hóa cả -0.0d thành +0.0d.
            }
        }
    }

    public static void main(String[] args) {
        Reading negative =
                new Reading(-0.0f, -0.0d);
        Reading positive =
                new Reading(+0.0f, +0.0d);
        Reading nanA =
                new Reading(Float.NaN, Double.NaN);
        Reading nanB =
                new Reading(Float.NaN, Double.NaN);

        System.out.println("zeros equal after normalization: "
                + negative.equals(positive));
        System.out.println("zero hashes equal: "
                + (negative.hashCode() == positive.hashCode()));
        System.out.println("stored float is positive zero: "
                + (Float.floatToIntBits(negative.value())
                        == Float.floatToIntBits(+0.0f)));
        System.out.println("stored double is positive zero: "
                + (Double.doubleToLongBits(negative.correction())
                        == Double.doubleToLongBits(+0.0d)));
        System.out.println("NaN values remain equal: "
                + nanA.equals(nanB));

        Set<Reading> values = new HashSet<>();
        values.add(negative);
        values.add(positive);
        values.add(nanA);
        values.add(nanB);
        System.out.println("set size: " + values.size());
    }
}
```

```bash
javac NormalizedZeroRecordDemo.java
java NormalizedZeroRecordDemo
```

**Đầu ra chính xác:**

```text
zeros equal after normalization: true
zero hashes equal: true
stored float is positive zero: true
stored double is positive zero: true
NaN values remain equal: true
set size: 2
```

Vì điều kiện `value == 0.0f` đúng cho cả zero dương và zero âm, phép gán `value = 0.0f` đưa cả hai về zero dương. Thân compact constructor thay đổi biến tham số trước khi Java gán chúng cho trường thành phần; record sau đó sử dụng `equals/hashCode` mặc định một cách nhất quán.

**Đánh đổi:** Chuẩn hóa này **loại bỏ thông tin dấu của zero**. Nó phù hợp khi ứng dụng quyết định dấu zero không có ý nghĩa, nhưng không phù hợp nếu cần phân biệt chúng trong phép toán, phân tích tín hiệu hoặc lưu dữ liệu IEEE 754 chính xác.

### 7.2. Nếu cần chuẩn hóa các trường khác thì sao?

Có thể áp dụng chuẩn hóa khác trong constructor (ví dụ kiểm tra `Double.isFinite` để cấm NaN/vô cực, hoặc lượng tử hóa theo đơn vị miền nghiệp vụ) nếu yêu cầu ứng dụng rõ ràng. Điều kiện quan trọng là **cùng một trạng thái chuẩn hóa phải sinh ra cùng quan hệ `equals`/`hashCode`**.

Không nên tự ghi đè `equals` để coi hai zero bằng nhau nhưng để `hashCode` mặc định: nếu hash của hai zero khác dấu khác nhau, record sẽ vi phạm hợp đồng “bằng nhau thì hash bằng nhau”. Chuẩn hóa trong constructor giúp duy trì nguyên cặp phương thức mặc định.

## 8. So sánh gần đúng không nên tự biến thành equals

Trong tính toán số, người ta đôi khi dùng ngưỡng sai số:

```java
Math.abs(a - b) <= epsilon
```

Đây là một cách kiểm tra gần đúng đơn giản, **không phải** quan hệ bằng nhau lý tưởng cho `equals(Object)`. Nó có thể **không bắc cầu**: với `epsilon = 1.0`, ta có `0.0` gần `0.6`, `0.6` gần `1.2` nhưng `0.0` không gần `1.2`.

Nếu đưa quan hệ gần đúng đó vào `equals`, hai giá trị mà ứng dụng coi là bằng nhau có thể khó gán hash một cách hợp lệ, và quan hệ `equals` có thể mất tính bắc cầu — ảnh hưởng tới các collection dùng khóa.

Nên tách:

- `record.equals`: đồng nhất theo quy tắc rõ ràng, có tính phản xạ, đối xứng và bắc cầu.
- Một phương thức riêng như `approximatelyEquals`: phép kiểm tra số học theo dung sai dành cho ứng dụng, không dùng thay `equals` trong `HashMap`/`HashSet`.

### 8.1. Ví dụ kiểm tra riêng phép gần bằng nhau

**Tệp `ApproximateComparisonDemo.java`:**

```java
public class ApproximateComparisonDemo {
    record Reading(double value) {
        boolean approximatelyEquals(Reading other, double epsilon) {
            if (other == null || !Double.isFinite(value)
                    || !Double.isFinite(other.value())
                    || !Double.isFinite(epsilon) || epsilon < 0) {
                return false;
            }
            return Math.abs(value - other.value()) <= epsilon;
        }
    }

    public static void main(String[] args) {
        Reading a = new Reading(0.0);
        Reading b = new Reading(0.6);
        Reading c = new Reading(1.2);

        System.out.println("a approximately b: "
                + a.approximatelyEquals(b, 1.0));
        System.out.println("b approximately c: "
                + b.approximatelyEquals(c, 1.0));
        System.out.println("a approximately c: "
                + a.approximatelyEquals(c, 1.0));
        System.out.println("a.equals(b): " + a.equals(b));
    }
}
```

```bash
javac ApproximateComparisonDemo.java
java ApproximateComparisonDemo
```

**Đầu ra chính xác:**

```text
a approximately b: true
b approximately c: true
a approximately c: false
a.equals(b): false
```

Phép kiểm tra đơn giản này chỉ phù hợp cho ví dụ hữu hạn có quy mô số hợp lý. Với các đại lượng rất lớn/nhỏ, có thể cần công thức dựa trên dung sai tuyệt đối và tương đối, kiểm soát overflow/underflow, tùy miền bài toán. Chính sách xấp xỉ vẫn nên **tách khỏi `equals`**.

## 9. Những điều dễ nhầm khi dùng record chứa số thực

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “`record.equals` so thành phần `double` bằng `==`.” | Nó theo ngữ nghĩa tương đương `Double.compare`, phân biệt signed zero và công nhận các NaN tương đương. |
| “Vì `Double.NaN == Double.NaN` là `false`, record chứa NaN không bằng chính nó.” | `record.equals` phải phản xạ và dùng quy tắc lớp bao, nên record chứa NaN vẫn bằng chính nó. |
| “`+0.0 == -0.0` nên hai record chứa hai zero này bằng nhau.” | Theo record mặc định, `+0.0` và `-0.0` **khác nhau**. |
| “`Double.compare` là kiểm tra gần đúng.” | Không; nó là phép so sánh có thứ tự, với quy tắc đặc biệt cho NaN và signed zero. |
| “Có thể so sánh hash để chứng minh hai record bằng nhau.” | Không; va chạm hash được phép xảy ra. |
| “Record có thành phần `Double` và `double` hoạt động hoàn toàn giống nhau.” | Ngữ nghĩa so giá trị đặc biệt tương tự, nhưng kiểu `Double` cho phép `null` còn `double` thì không. |
| “Muốn zero khác dấu bằng nhau, chỉ cần ghi đè equals.” | Phải đồng bộ `hashCode`; thường dễ kiểm chứng hơn nếu chuẩn hóa đầu vào và giữ phương thức mặc định. |
| “So sánh sai số nhỏ hơn epsilon dùng được như equals cho khóa hash.” | Quan hệ gần đúng có thể không bắc cầu, không phù hợp làm `equals` tổng quát. |
| “Có thể dựa vào đúng con số hash của record ở mọi JDK.” | Đặc tả không cam kết thuật toán hash cố định giữa các triển khai/chạy chương trình. |

### Checklist khi thiết kế một record có float hoặc double

1. Thành phần đó có thể nhận `NaN`, `+Infinity`, `-Infinity` hoặc signed zero không?
2. Miền nghiệp vụ muốn **phân biệt** zero khác dấu, hay muốn chuẩn hóa cả hai về một giá trị?
3. Nếu có thể nhận NaN, toàn bộ NaN có nên được coi tương đương không? Mặc định của record là **có**.
4. Có cần kiểm tra gần đúng trong một **phương thức riêng** không?
5. Record có thành phần kiểu `Float`/`Double` cần xử lý `null` không?
6. Nếu ghi đè `equals`, đã chứng minh `hashCode` tương thích, tính phản xạ, đối xứng và bắc cầu chưa?
7. Nếu lưu trong `HashSet` hoặc `HashMap`, đã kiểm tra trường hợp zero khác dấu và NaN chưa?

## 10. Tự kiểm tra

**Câu 1.** Cho `record R(double x) {}`. Hai đối tượng `new R(Double.NaN)` có `equals` nhau không?  
**Đáp án:** Có. Ngữ nghĩa bằng nhau mặc định của record đối với `double` tương đương `Double.compare`; NaN được xem là bằng nhau.

**Câu 2.** `new R(+0.0).equals(new R(-0.0))` trả gì?  
**Đáp án:** `false`. `Double.compare(+0.0, -0.0)` không trả `0`.

**Câu 3.** Tại sao `Double.NaN == Double.NaN` trả `false` nhưng record chứa NaN lại có thể trả `equals == true`?  
**Đáp án:** Toán tử nguyên thủy `==` tuân theo quy tắc so sánh số thực IEEE 754. Record mặc định sử dụng ngữ nghĩa so sánh của lớp bao để tạo quan hệ bằng nhau hợp lệ theo hợp đồng `equals`.

**Câu 4.** Nếu một record chứa `Float f` và cả hai đối tượng đều có `f == null`, thành phần đó có được coi là bằng nhau không?  
**Đáp án:** Có. Thành phần tham chiếu được so tương đương `Objects.equals(null, null)`. Tuy nhiên record còn phải xét mọi thành phần còn lại và đúng lớp record.

**Câu 5.** Làm cách nào để record coi `+0.0` và `-0.0` là bằng nhau mà vẫn dùng `equals/hashCode` được sinh?  
**Đáp án:** Chuẩn hóa cả hai về cùng zero (ví dụ `+0.0`) trong compact constructor, khi đó các trường thực tế lưu vào record giống nhau về quy tắc mặc định.

**Câu 6.** `approximatelyEquals` với dung sai cố định có nên được cài làm `equals(Object)` không?  
**Đáp án:** Không. Quan hệ gần bằng nhau có thể vi phạm bắc cầu, khiến cấu trúc dữ liệu dựa vào `equals/hashCode` không có hành vi đúng theo hợp đồng.

## Ghi nhớ

**Record so thành phần `float` và `double` theo quy tắc tương đương `Float.compare`/`Double.compare`, không theo toán tử `==` nguyên thủy.** Vì vậy NaN tương đương NaN, còn `+0.0` khác `-0.0` trong `record.equals` mặc định. Thành phần `Float`/`Double` dùng quy tắc `Objects.equals` và hỗ trợ thêm `null`. Đặc tả yêu cầu `hashCode` nhất quán với `equals` nhưng không ấn định con số hash cụ thể. Nếu ứng dụng muốn quy tắc khác, hãy xác định ngữ nghĩa miền nghiệp vụ, ưu tiên chuẩn hóa đầu vào và giữ quan hệ `equals/hashCode` nhất quán; dùng phương thức riêng cho so sánh gần đúng.
