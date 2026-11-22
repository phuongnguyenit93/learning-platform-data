# Không dùng so sánh gần bằng tùy tiện làm quan hệ equals hoặc thứ tự sắp xếp

## 1. Vấn đề cốt lõi

Khi dùng `float` hoặc `double` trong Java, người học thường được khuyên tránh `a == b` sau phép tính có sai số làm tròn. Lời khuyên ấy có lý trong **kiểm tra gần bằng theo yêu cầu đo lường**, nhưng có một ranh giới cực kỳ quan trọng:

> **“Hai số đủ gần” không tự động là quan hệ bằng nhau hợp lệ để triển khai `equals`, `hashCode`, `Comparator` hoặc khóa của `HashMap`/`TreeMap`.**

Ví dụ quy tắc “coi bằng nhau nếu chênh lệch không vượt 0,1”:

```java
static boolean close(double a, double b) {
    return Math.abs(a - b) <= 0.1;
}
```

Xét ba giá trị:

```text
a = 0.00
b = 0.09
c = 0.18

close(a, b) = true
close(b, c) = true
close(a, c) = false
```

Đây là trường hợp **không bắc cầu**: `a` gần `b`, `b` gần `c`, nhưng `a` không gần `c`. Nếu ta cho `close` thay thế `equals` hoặc trả `0` trong `Comparator.compare`, các cấu trúc dữ liệu vốn cần một khái niệm bằng nhau/thứ tự **nhất quán** có thể hoạt động trái trực giác.

Bài này thuộc **Java Core — Numbers / So sánh số thực**. Mục tiêu là:

1. Biết khi nào dùng so sánh số thực **chính xác về giá trị**, khi nào dùng **gần bằng** với dung sai.
2. Hiểu yêu cầu **phản xạ, đối xứng, bắc cầu** của `equals` và mối liên hệ với `hashCode`.
3. Hiểu hợp đồng `Comparator`, đặc biệt ràng buộc khi `compare(a,b) == 0` và tính bắc cầu.
4. Giải thích vì sao “epsilon comparator” không an toàn cho `TreeSet`, `TreeMap` và các thuật toán sắp xếp.
5. Sử dụng `Double.compare` hoặc một **khóa đại diện được chuẩn hóa/định lượng hóa** có quy tắc rõ ràng.
6. Thiết kế riêng phép kiểm tra gần bằng cho thuật toán số, có xét NaN, infinity, signed zero, sai số tuyệt đối/tương đối và dữ liệu biên.

Ví dụ chạy được với **Java 17+**; không cần thư viện ngoài JDK.

## 2. Cần phân biệt bốn câu hỏi khác nhau

Các câu hỏi về hai giá trị `double` không nhất thiết có cùng đáp án:

| Câu hỏi | Công cụ gợi ý | Mục đích |
| --- | --- | --- |
| Hai giá trị bằng theo phép so sánh floating-point của Java không? | `a == b` | Logic toán tử nguyên thủy |
| Hai giá trị gần nhau theo sai số của bài toán không? | `isClose(a,b,absTol,relTol)` | Kiểm định sai số phép đo/kết quả tính |
| Hai đối tượng là cùng một khóa theo hợp đồng ứng dụng không? | `equals` và `hashCode` nhất quán | `HashSet`, `HashMap`, mô hình dữ liệu |
| Hai phần tử có thứ tự nào để sắp xếp/lưu trong cây? | `Comparator` hợp lệ; thường `Double.compare` | `sort`, `TreeSet`, `TreeMap` |

So sánh gần bằng là một **truy vấn** về khoảng cách, không phải mặc nhiên là **định nghĩa danh tính** của một phần tử.

Không nên hiểu “`==` nguy hiểm với `double`” thành “cứ thay mọi phép bằng bằng epsilon”. `==` chính xác có thể hoàn toàn đúng khi so sánh sentinel, kiểm tra zero theo giá trị, hay khi hợp đồng yêu cầu **đúng giá trị dấu phẩy động**. Điều quan trọng là chọn phép so sánh phù hợp với ý nghĩa dữ liệu.

## 3. Quan hệ tương đương mà `equals` phải tuân thủ

Theo hợp đồng của `Object.equals`, với các đối tượng khác `null`, một quan hệ bằng nhau hợp lệ phải có ít nhất những tính chất sau:

- **Phản xạ (reflexive):** `x.equals(x)` phải là `true`.
- **Đối xứng (symmetric):** nếu `x.equals(y)` thì `y.equals(x)`.
- **Bắc cầu (transitive):** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
- **Nhất quán (consistent):** nhiều lần gọi không đổi kết quả nếu những thông tin được dùng để so sánh không đổi.
- `x.equals(null)` phải là `false`.

Ngoài ra, nếu `x.equals(y)` là `true` thì **`x.hashCode() == y.hashCode()` bắt buộc đúng**. Hai đối tượng không bằng nhau vẫn có thể trùng hash, nhưng hai đối tượng bằng nhau không được khác hash.

### 3.1. Vì sao epsilon phá vỡ tính bắc cầu?

Đặt `ε = 0.1` và định nghĩa:

```text
a ≈ b  khi  |a - b| <= ε
```

Chọn `a = 0.00`, `b = 0.09` và `c = 0.18`.

| Cặp | Khoảng cách | Có “gần bằng” không? |
| --- | ---: | --- |
| `a,b` | 0,09 | Có |
| `b,c` | 0,09 | Có |
| `a,c` | 0,18 | Không |

Hợp đồng `equals` sẽ yêu cầu nếu `a` bằng `b` và `b` bằng `c` thì `a` phải bằng `c`. Nhưng kiểm tra dung sai ở đây nói ngược lại.

Một dung sai **dương cố định** trên một miền số liên tục thường có hiện tượng “bắc cầu qua các bước gần nhau”. Đổi từ `<=` sang `<` hoặc đổi epsilon nhỏ hơn không biến nó thành quan hệ tương đương tổng quát.

### 3.2. NaN có thể phá cả phản xạ nếu viết sai

Giả sử:

```java
boolean near = Math.abs(Double.NaN - Double.NaN) <= 1e-9;
```

`near` là `false` do mọi so sánh thứ tự `<=` với NaN trả false. Nếu `equals` của một đối tượng dùng chính phép đó để so sánh field và **không có nhánh identity phù hợp**, một đối tượng chứa NaN thậm chí có thể không bằng chính nó. Nhưng thêm `if (this == other) return true;` chỉ có thể chữa **một nhánh phản xạ**, không sửa tính bắc cầu của quan hệ epsilon.

Tự đặt epsilon vào `equals` không phải “nâng cấp” toàn diện phép so sánh số thực.

## 4. `hashCode` không cứu được quan hệ gần bằng không bắc cầu

Một lỗi thường thấy:

```java
// MÃ Ý TƯỞNG SAI, KHÔNG NÊN DÙNG TRONG equals:
return Math.abs(this.value - other.value) <= EPSILON;
```

rồi triển khai `hashCode` bằng `Double.hashCode(value)`. Khi `this.value` gần `other.value` nhưng bit/giá trị khác nhau, hai object có thể bị `equals` coi là bằng, trong khi hash của chúng khác nhau. Điều này **vi phạm trực tiếp** hợp đồng giữa `equals` và `hashCode`.

Có người sửa bằng cách cho mọi object `hashCode()` cố định bằng `1`. Cách đó tránh yêu cầu hash khác nhau, nhưng:

1. Không khôi phục tính bắc cầu của `equals`.
2. Có thể làm `HashMap`/`HashSet` suy giảm hiệu năng vì quá nhiều va chạm.
3. Khi dữ liệu bằng nhau theo từng cặp nhưng không bắc cầu, thao tác tìm/xóa/phân nhóm vẫn khó định nghĩa một cách nhất quán.

**Kết luận:** một quan hệ gần bằng không bắc cầu không thể trở thành `equals` hợp lệ chỉ nhờ chọn một công thức `hashCode` khéo léo.

## 5. `Comparator` cần một quan hệ thứ tự nhất quán

Java định nghĩa `Comparator<T>` qua phương thức:

```java
int compare(T a, T b);
```

Ý nghĩa dấu kết quả:

- Nhỏ hơn `0`: `a` đứng trước `b`.
- Bằng `0`: comparator coi `a` và `b` **tương đương về thứ tự**.
- Lớn hơn `0`: `a` đứng sau `b`.

Hợp đồng comparator yêu cầu (trình bày theo ý nghĩa toán học):

1. **Đổi hai đối số thì dấu đổi:** dấu của `compare(a,b)` phải đối dấu với `compare(b,a)`, với yêu cầu ngoại lệ phù hợp.
2. **Bắc cầu:** nếu `a > b` và `b > c` theo comparator thì `a > c`.
3. **Nhất quán của lớp so sánh bằng 0:** nếu `compare(a,b) == 0` thì dấu của `compare(a,z)` và `compare(b,z)` phải giống nhau với mọi `z`.

Điều (3) có nghĩa comparator định nghĩa một **quan hệ tương đương dựa trên kết quả so sánh bằng 0**. Nếu dùng “chênh lệch dưới epsilon” để trả 0, điều (3) dễ bị phá.

### 5.1. Comparator sai điển hình

```java
static final double EPSILON = 0.1;

static int badCompare(double a, double b) {
    if (Math.abs(a - b) <= EPSILON) {
        return 0;
    }
    return Double.compare(a, b);
}
```

Đoạn này có vẻ hợp lý vì phân biệt số rất khác nhau, còn số gần thì coi bằng. Nhưng với `a=0.00`, `b=0.09`, `c=0.18`:

```text
badCompare(a, b) = 0
badCompare(b, c) = 0
badCompare(a, c) = -1
```

Comparator vừa nói `a` tương đương `b`, `b` tương đương `c`, nhưng lại nói `a` đứng trước `c`. Đó là **vi phạm hợp đồng**, không chỉ là “độ chính xác chưa tốt”.

**Cảnh báo:** không nên viết `return (int) (a - b);` để so sánh `double`. Phép trừ có thể làm tròn, sinh vô cực hoặc NaN; cast sang `int` sẽ làm mất phần thập phân, làm nhiều cặp khác nhau trả 0, thậm chí tràn/saturate. Với `int`/`long`, phép trừ để so sánh cũng có thể tràn. Hãy dùng comparator có hợp đồng rõ ràng.

## 6. Ví dụ chạy được: cùng dữ liệu, `TreeSet` cho kết quả phụ thuộc thứ tự thêm

Lưu tệp **`BadEpsilonComparator.java`**:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class BadEpsilonComparator {
    private static final double EPSILON = 0.1;

    public static void main(String[] args) {
        double a = 0.00;
        double b = 0.09;
        double c = 0.18;

        System.out.println(near(a, b));
        System.out.println(near(b, c));
        System.out.println(near(a, c));

        Comparator<Double> bad = (x, y) ->
                near(x, y) ? 0 : Double.compare(x, y);

        System.out.println(bad.compare(a, b));
        System.out.println(bad.compare(b, c));
        System.out.println(bad.compare(a, c));

        TreeSet<Double> first = new TreeSet<>(bad);
        first.add(a);
        first.add(b);
        first.add(c);

        TreeSet<Double> second = new TreeSet<>(bad);
        second.add(b);
        second.add(a);
        second.add(c);

        System.out.println(first.size());
        System.out.println(second.size());
    }

    static boolean near(double x, double y) {
        return Math.abs(x - y) <= EPSILON;
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac --release 17 BadEpsilonComparator.java
java BadEpsilonComparator
```

**Stdout với JDK Java chuẩn:**

```text
true
true
false
0
0
-1
2
1
```

Diễn giải:

- Khi thêm `a` trước: `b` bị xem như cùng phần tử với `a`, còn `c` khác `a` nên tập có `2` phần tử.
- Khi thêm `b` trước: cả `a` và `c` đều được comparator coi là cùng phần tử với `b`, nên tập chỉ có `1` phần tử.
- Dữ liệu đầu vào là cùng bộ ba, nhưng ý niệm “loại trùng” phụ thuộc thứ tự thêm. Đây là một phản ví dụ đủ để loại bỏ comparator dạng epsilon.

`TreeSet`/`TreeMap` dùng `compare(a,b) == 0` để quyết định hai khóa có cùng vị trí trong cây, **không dùng `equals` trong bước này**. Các thuật toán `sort` cũng giả định comparator tuân thủ hợp đồng; comparator sai có thể gây thứ tự bất hợp lý hoặc `IllegalArgumentException` về vi phạm hợp đồng trong một số trường hợp, nhưng không bảo đảm lúc nào cũng ném lỗi.

**Không triển khai comparator sai rồi “kiểm thử thấy không crash” để kết luận an toàn.** Hợp đồng phải đúng với toàn bộ miền dữ liệu cho phép.

## 7. Dùng `Double.compare` để tạo thứ tự ổn định

Với các khóa dựa trên giá trị `double`, lựa chọn mặc định phù hợp thường là:

```java
Comparator<Double> byNumericValue = Double::compare;
```

Hoặc với đối tượng có thuộc tính số:

```java
Comparator<Reading> byValue =
        Comparator.comparingDouble(Reading::value);
```

Ở đây `Reading` là một kiểu tự định nghĩa có phương thức `value()` trả `double`; đoạn thứ hai là **mảnh minh họa**, không phải chương trình hoàn chỉnh khi chưa khai báo `Reading`.

`Double.compare` tạo thứ tự được xác định cho cả các giá trị đặc biệt:

- `Double.compare(-0.0, +0.0) < 0`: **zero âm đứng trước zero dương**.
- `Double.compare(Double.NaN, Double.NaN) == 0`: NaN được coi tương đương trong thứ tự của `Double`.
- NaN được xếp **lớn hơn các giá trị số khác**, kể cả `Double.POSITIVE_INFINITY`.
- Các số hữu hạn thông thường và ±Infinity được sắp xếp theo thứ tự số tương ứng.

Điều này khác với toán tử `==` primitive:

```java
System.out.println(-0.0 == +0.0); // true
System.out.println(Double.compare(-0.0, +0.0)); // -1

System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
```

**Không dùng `x < y ? -1 : x > y ? 1 : 0` làm comparator tổng quát cho `double`**: với NaN cả `<` và `>` đều false, nên có thể trả 0 cho NaN và bất kỳ số nào; với ±0, nó cũng xem bằng nhau. Nếu muốn một thứ tự khác `Double.compare`, phải thiết kế **toàn bộ** quy tắc (bao gồm NaN, ±Infinity, ±0) sao cho vẫn bắc cầu và nhất quán.

### 7.1. Thứ tự ổn định không đồng nghĩa dữ liệu đo “giống hệt”

`Double.compare(a,b) == 0` là một tiêu chí **thứ tự theo giá trị IEEE 754** hữu ích cho dữ liệu dùng làm khóa; không phải phép kiểm định hai kết quả đo có nằm trong sai số cho phép hay không. Vì vậy, vẫn có thể dùng `isClose(a,b)` để hiển thị cảnh báo “hai cảm biến cho kết quả tương tự”, đồng thời dùng `Double.compare` cho việc sắp xếp danh sách theo kết quả.

## 8. `Double.equals`, `hashCode`, signed zero và NaN

`Double.equals` có hợp đồng khác primitive `==`:

| Trường hợp | Primitive `==` | `Double.equals` |
| --- | --- | --- |
| `+0.0` và `-0.0` | `true` | `false` |
| `Double.NaN` và `Double.NaN` | `false` | `true` |
| Hai giá trị hữu hạn giống nhau về biểu diễn giá trị | `true` | `true` |

`Double.equals` so sánh theo mã hóa bit do `Double.doubleToLongBits` trả về; phương thức đó chuẩn hóa các dạng NaN về một mẫu canonical nhưng **giữ sự khác biệt ±0**. `Double.hashCode` nhất quán với hợp đồng này.

Do đó, `HashSet<Double>` có thể giữ hai khóa `+0.0` và `-0.0` riêng biệt, trong khi nhận thêm một NaN canonical-equivalent như đã có thì không tạo phần tử mới.

### Ví dụ chạy được: so sánh bằng nhau ở ba tầng

Lưu **`FloatingIdentity.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class FloatingIdentity {
    public static void main(String[] args) {
        System.out.println(+0.0 == -0.0);
        System.out.println(Double.valueOf(+0.0)
                .equals(Double.valueOf(-0.0)));

        System.out.println(Double.NaN == Double.NaN);
        System.out.println(Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));

        System.out.println(Double.compare(-0.0, +0.0));
        System.out.println(Double.compare(Double.NaN,
                Double.POSITIVE_INFINITY));

        Set<Double> values = new HashSet<>();
        values.add(+0.0);
        values.add(-0.0);
        values.add(Double.NaN);
        values.add(Double.NaN);
        System.out.println(values.size());
    }
}
```

Chạy:

```bash
javac --release 17 FloatingIdentity.java
java FloatingIdentity
```

**Stdout:**

```text
true
false
false
true
-1
1
3
```

Hai giá trị zero khác nhau theo wrapper equality; hai NaN được canonicalize cho `equals`. Điều này phù hợp cho các collection Java, không nhằm khẳng định NaN có quan hệ bằng nhau theo toán học thông thường.

### 8.1. Nếu tự viết kiểu dữ liệu có field `double`

Một lựa chọn đúng khi **danh tính chính là bit-value theo `Double`** là viết `equals`/`hashCode` tương thích:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof Measurement other)) return false;
    return Double.doubleToLongBits(this.value)
            == Double.doubleToLongBits(other.value);
}

@Override
public int hashCode() {
    return Double.hashCode(value);
}
```

Đây là **hai phương thức minh họa bên trong class `Measurement`** có field `private final double value`, không phải mã Java độc lập. Dùng `Double.doubleToLongBits` thay vì raw bits nếu muốn tất cả NaN patterns có cùng quy tắc `equals`/`hashCode` như wrapper. Dùng `Double.compare` trong comparator để tương thích với thứ tự của wrapper.

Nếu danh tính đối tượng là `id` ổn định, có thể định nghĩa `equals` bằng `id` và chỉ dùng số đo để lọc/gần bằng. Tránh để field floating-point **có thể thay đổi** quyết định `hashCode` sau khi đối tượng đã được đưa vào `HashSet`/`HashMap`.

## 9. Khi nào **gần bằng** thực sự phù hợp?

Một phép kiểm tra dung sai rất hữu ích khi bạn quan tâm đến **độ lớn chênh lệch theo nghĩa vật lý hoặc số học**, ví dụ:

- Hai phép đo nhiệt độ có chênh lệch nằm trong sai số cảm biến.
- So sánh kết quả thuật toán số với giá trị kỳ vọng có dung sai đã xác định.
- Phát hiện đầu ra mô phỏng khác nhau nhưng vẫn trong ngưỡng chấp nhận.
- Xác định sự hội tụ theo tiêu chuẩn dựa trên sai số, kèm ngưỡng và tiêu chí dừng được thiết kế phù hợp.

Nhưng câu trả lời `isClose(a,b)` nên là **một boolean của truy vấn cụ thể**, không dùng mặc định để quyết định object nào là “cùng khóa” trong hash/tree collection.

### 9.1. Sai số tuyệt đối (absolute tolerance)

Một phép kiểm tra đơn giản:

```java
boolean near = Math.abs(actual - expected) <= absoluteTolerance;
```

Nếu absolute tolerance có đơn vị đo (ví dụ độ C, mét, giây), hãy đặt giá trị theo sai số mà nghiệp vụ chấp nhận; không dùng một con số “ε thần kỳ” cho mọi tình huống.

Ví dụ `|1.00001 - 1.00002| <= 0.0001` hợp lý khi chỉ cần sai số nhỏ hơn `0.0001` đơn vị; nhưng cùng epsilon đó có thể quá nhỏ hoặc quá lớn ở thang số khác.

### 9.2. Sai số tương đối (relative tolerance)

Khi thang độ lớn thay đổi, ta có thể dùng:

```text
|a - b| <= relTol × max(|a|, |b|)
```

Sai số tương đối chỉ có ý nghĩa khi thang đo khác 0. Gần zero, một tolerance tương đối thuần túy trở nên khó sử dụng; thường cần một phần **absolute tolerance** để ổn định.

Ví dụ kết hợp:

```text
|a - b| <= max(absTol, relTol × max(|a|, |b|))
```

Đây là **quy tắc nghiệp vụ được chọn**, không phải định nghĩa equality của ngôn ngữ. Nó vẫn **không có tính bắc cầu tổng quát**.

### 9.3. Cần phân loại NaN/Infinity và kiểm soát input

`Math.abs(a - b) <= eps` có thể trả false cho `a == b == Double.POSITIVE_INFINITY` vì `+∞ - +∞` là NaN. Với NaN, biểu thức `<=` trả false. Nếu một hệ thống muốn “cùng vô cực là cùng trạng thái”, quy tắc đó phải được viết rõ, không tự suy từ hiệu số.

Nếu comparator dùng `near` để trả 0 khi gặp NaN, điều kiện false có thể đẩy chương trình tới nhánh `Double.compare` nhưng quan hệ trộn vẫn không được bảo đảm bắc cầu. Với epsilon âm hoặc NaN, hành vi càng mơ hồ; phải **validate tolerance** ngay từ đầu.

## 10. Ví dụ Java 17+ cho truy vấn gần bằng an toàn theo phạm vi sử dụng

Lưu thành **`NearEnough.java`**:

```java
public class NearEnough {
    static boolean near(double a, double b,
                        double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0 || relTol < 0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }

        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false; // Chính sách: chỉ so sánh gần bằng số hữu hạn
        }

        double diff = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return diff <= Math.max(absTol, relTol * scale);
    }

    public static void main(String[] args) {
        System.out.println(near(0.0, 5e-13, 1e-12, 1e-8));
        System.out.println(near(0.0, 2e-12, 1e-12, 1e-8));
        System.out.println(near(1_000_000.0, 1_000_000.005,
                1e-12, 1e-8));
        System.out.println(near(Double.NaN, Double.NaN,
                1e-12, 1e-8));
        System.out.println(near(-0.0, +0.0,
                1e-12, 1e-8));
    }
}
```

Chạy:

```bash
javac --release 17 NearEnough.java
java NearEnough
```

**Stdout dự kiến:**

```text
true
false
true
false
true
```

Mục tiêu của hàm là **truy vấn “chênh lệch nằm trong mức cho phép” trên dữ liệu hữu hạn**. Nó **không** được dùng trực tiếp cho `equals` hay `Comparator`.

Cần hiểu giới hạn của chính hàm mẫu:

- Nếu `a-b` tràn thành `Infinity` dù hai input hữu hạn, kiểm tra này sẽ trả false. Điều đó phù hợp với nhiều chính sách kiểm tra gần bằng với tolerance nhỏ, nhưng cần phân tích nếu miền dữ liệu rất rộng.
- Tích `relTol * scale` có thể tràn với tolerance lớn; nên ràng buộc `relTol` và miền input theo ứng dụng. Hàm xác nhận tolerance hữu hạn và không âm, nhưng không thay thế đánh giá điều kiện số học ở mọi miền IEEE 754.
- Giá trị `-0.0` và `+0.0` được coi gần bằng; đúng nếu ứng dụng chỉ quan tâm độ chênh lệch, **không** đúng nếu cần giữ signed zero.
- Tolerance có thể không bắc cầu bất kể bạn kết hợp ngưỡng tuyệt đối và tương đối thế nào.

## 11. Nếu cần gom nhóm: chọn một quy tắc **khóa** ổn định, không dùng epsilon làm equals

Đôi khi yêu cầu thực sự là: “mọi số thuộc cùng một khoảng nên được nhóm chung”. Đây là bài toán khác với “hai số gần nhau không quá epsilon”.

Có thể định nghĩa một hàm ánh xạ **mỗi giá trị vào một khóa xác định**, rồi áp dụng equality/order lên khóa:

```text
bucket(x) = floor((x - origin) / width)
```

Khi đó:

```text
sameBucket(a, b) = bucket(a) == bucket(b)
```

Do mỗi giá trị có **một khóa duy nhất**, quan hệ `sameBucket` có tính phản xạ, đối xứng và bắc cầu, giả sử đầu vào và quy tắc bucket được kiểm soát nhất quán. Nó khác gần bằng theo khoảng cách: hai số rất gần nhau nhưng nằm hai phía ranh giới bucket **có thể** bị xếp hai nhóm khác nhau. Đây là lựa chọn có chủ đích để lấy **tính ổn định của quan hệ khóa**.

### 11.1. Ví dụ bucket cho miền dữ liệu bị ràng buộc

Lưu **`BucketGrouping.java`**:

```java
public class BucketGrouping {
    static long bucket(double value) {
        if (!Double.isFinite(value)
                || value < -1_000_000.0
                || value > 1_000_000.0) {
            throw new IllegalArgumentException("Out of range");
        }
        return (long) Math.floor(value / 0.5);
    }

    public static void main(String[] args) {
        System.out.println(bucket(0.1));
        System.out.println(bucket(0.4));
        System.out.println(bucket(0.51));
        System.out.println(bucket(-0.1));

        System.out.println(bucket(0.1) == bucket(0.4));
        System.out.println(bucket(0.49) == bucket(0.51));
    }
}
```

Chạy:

```bash
javac --release 17 BucketGrouping.java
java BucketGrouping
```

**Stdout:**

```text
0
0
1
-1
true
false
```

`0.49` và `0.51` cách nhau chỉ `0.02` nhưng rơi vào hai bucket khác nhau. Đây **không phải lỗi** của hàm: nó cho thấy bucket equality và distance-based closeness là **hai khái niệm khác nhau**.

Ví dụ cố ý dùng `width=0.5` biểu diễn chính xác trong nhị phân và miền đầu vào được chặn. Nếu bucket theo bước thập phân như `0.01` hay dùng các số rất lớn, phải xét làm tròn tại ranh giới, overflow/cast saturation và hợp đồng làm tròn. Có thể dùng `BigDecimal` cho dữ liệu thập phân cần chính xác và lựa chọn chế độ làm tròn phù hợp. Không đưa giá trị NaN/Infinity vào hàm bucket nếu chưa định nghĩa chính sách riêng.

### 11.2. Muốn nhóm theo sai số, có thể cần thuật toán clustering

Nếu yêu cầu là “mọi phép đo được coi thuộc một cụm khi có chuỗi liên kết gần nhau” thì bạn đang định nghĩa **connected components theo quan hệ gần kề**, không phải equality từng cặp. Cụm có thể chứa hai điểm cách nhau lớn hơn epsilon nếu có chuỗi điểm trung gian. Nếu yêu cầu “mọi cặp trong một cụm đều gần nhau”, lại là tiêu chí khác. Hãy chọn rõ bài toán clustering; đừng ngầm cài đặt bằng `equals` hoặc comparator tùy tiện.

## 12. Thực hành với `HashMap`, `TreeMap`, `TreeSet` và `sort`

### 12.1. `HashMap`/`HashSet`

Các collection dựa trên hash sử dụng `hashCode` và `equals` của khóa. Chúng mong đợi hợp đồng equality ổn định, bắc cầu và hash nhất quán. Nếu đối tượng chứa giá trị floating-point thay đổi **sau khi đã dùng làm khóa**, có thể không tìm được khóa trong đúng bucket ban đầu.

Tình huống nên tránh:

```java
// Ý tưởng sai: dùng một trường mutable làm hash/equality rồi đổi nó
// sau khi đối tượng đã được chèn vào HashSet/HashMap.
```

Đây là **mô tả sai lầm**, không phải API Java có thể chạy độc lập. Thiết kế tốt hơn là dùng khóa **immutable** — ví dụ ID, mã mẫu đo, hoặc bucket key được xác định từ đầu.

### 12.2. `TreeMap`/`TreeSet`

Collection dạng cây sử dụng `compare` hoặc `compareTo` để xác định thứ tự và sự trùng khóa. Nếu comparator trả `0` cho hai đối tượng mà `equals` coi khác nhau, tập có thể có hành vi khác `Set` dựa trên equals. Java cho phép comparator **không nhất quán với equals** trong một số ngữ cảnh nhưng cần ghi rõ; đối với `SortedSet`/`SortedMap`, việc không nhất quán có thể làm vi phạm kỳ vọng chung của hợp đồng `Set`/`Map`.

Nhưng comparator **không bắc cầu** là vấn đề nghiêm trọng hơn: nó vi phạm chính hợp đồng `Comparator` và có thể gây kết quả phụ thuộc đường đi so sánh, như ví dụ ở mục 6.

Nếu cần thứ tự theo số đo rồi phá hòa bằng ID:

```java
// Đoạn này giả định Sample có value():double và id():long
Comparator<Sample> order =
        Comparator.comparingDouble(Sample::value)
                .thenComparingLong(Sample::id);
```

Đây là **mảnh minh họa**, cần khai báo `Sample`. Comparator tạo thứ tự có tiêu chí rõ, không dùng epsilon để trả `0`. Chú ý: thêm tiêu chí ID chỉ khắc phục những trường hợp **đã bằng nhau theo tiêu chí đầu hợp lệ**; nó không cứu một comparator epsilon vốn không bắc cầu.

### 12.3. `Collections.sort` và `List.sort`

Các thuật toán sắp xếp mong đợi comparator tuân thủ hợp đồng. Với comparator sai, thứ tự sắp xếp có thể thiếu nhất quán, hoặc có thể gặp ngoại lệ cho biết comparator vi phạm hợp đồng trên một số dữ liệu. **Không có ngoại lệ** không chứng minh comparator đúng; phản ví dụ bắc cầu là đủ để bác bỏ tính hợp lệ.

## 13. Các bẫy đặc biệt của floating point khi thiết kế equality/ordering

### 13.1. Signed zero

`+0.0 == -0.0` là `true`, nhưng `Double.compare(-0.0,+0.0) < 0` và `Double.equals` phân biệt hai dạng zero.

Nếu ứng dụng muốn gộp cả hai thành một khóa, hãy chuẩn hóa theo quy tắc:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

Mảnh phương thức này biến `-0.0` thành `+0.0`, giữ các số khác zero; chỉ dùng nếu dấu zero không có ý nghĩa ở các phép tính kế tiếp. Với phép chia hoặc `Math.atan2`, signed zero có thể có ý nghĩa thực sự.

### 13.2. NaN

`Double.NaN == Double.NaN` là false, trong khi `Double.compare(Double.NaN, Double.NaN) == 0`. Một comparator tự viết dựa trên `a > b` và `a < b` thường sai với NaN. Khi domain không cho phép NaN, hãy **chặn bằng `Double.isFinite`** (nó cũng loại infinity) hoặc `Double.isNaN`; nếu domain cho phép NaN, phải định nghĩa rõ thứ tự và equality.

### 13.3. Infinity và overflow của phép trừ

`Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` là NaN. `Double.MAX_VALUE - (-Double.MAX_VALUE)` tràn thành infinity dù hai đầu vào hữu hạn. Công thức `Math.abs(a-b)` chỉ thích hợp khi bạn đã đánh giá miền giá trị và chính sách đối với các kết quả đặc biệt.

### 13.4. Tolerance thay đổi theo ngữ cảnh

Sai số chấp nhận được của phép đo nhiệt độ có thể khác đơn vị, độ chính xác thiết bị và thời gian lấy mẫu. Sai số cho thuật toán tính số có thể thay đổi theo magnitude và cách tích lũy phép tính. Không dùng một biến global `EPSILON` rồi áp cho mọi field, mọi domain và mọi chức năng.

### 13.5. BigDecimal cũng có phân biệt equality và ordering

`BigDecimal` là số thập phân tùy ý độ chính xác, nhưng `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false vì `equals` xét cả scale, trong khi `compareTo` trả `0` vì hai giá trị số bằng nhau. Nếu dùng `BigDecimal` làm khóa, phải quyết định liệu scale là một phần danh tính hay có quy tắc chuẩn hóa riêng. Việc đổi từ `double` sang `BigDecimal` **không tự giải quyết mọi vấn đề thiết kế equals/comparator**.

## 14. Quy trình chọn quan hệ so sánh cho dự án

**Bước 1 — Xác định mục đích.** Bạn cần trả lời “có nằm trong sai số cho phép”, “có phải cùng thực thể”, “có cùng nhóm đã định nghĩa”, hay “xếp thứ tự nào”?

**Bước 2 — Xác định domain.** Có cho phép `NaN`, `Infinity`, `-0.0`, giá trị ngoài ngưỡng, hoặc số thập phân cần chính xác không? Có cần phân biệt dữ liệu đo theo đơn vị, timestamp, ID?

**Bước 3 — Nếu chỉ là truy vấn gần bằng**, chọn absolute/relative tolerance theo bài toán, kiểm tra finite và tập dữ liệu biên; trả về một `boolean` riêng, không dùng làm `equals`/`compare`.

**Bước 4 — Nếu cần danh tính**, dùng ID ổn định hoặc khóa canonical/bucket có chính sách rõ, tạo `equals`/`hashCode` nhất quán; tránh field mutable.

**Bước 5 — Nếu cần thứ tự**, dùng `Double.compare` hoặc comparator có các bước so sánh bắc cầu, kiểm tra quy tắc `compare(a,b)==0` và cân nhắc tương thích với equality của khóa.

**Bước 6 — Kiểm thử phản ví dụ.** Với ba giá trị `0.00, 0.09, 0.18`, truy vấn gần bằng có thể không bắc cầu; nhưng mọi equality hoặc comparator-zero thực sự dùng làm khóa phải có tính bắc cầu. Thêm bộ dữ liệu chứa ±0, NaN, ±Infinity, số lớn, số gần ranh giới bucket.

**Bước 7 — Ghi rõ quyết định.** Tài liệu hóa: “gần bằng theo dung sai là phép kiểm tra nghiệp vụ” hoặc “khóa nhóm là bucket 0.5 trên miền dữ liệu đã kiểm tra”, không dùng mơ hồ “tất cả gần bằng đều là bằng nhau”.

## 15. Bộ kiểm thử đặc tính nên có

Thay vì chỉ kiểm thử từng cặp bất kỳ, với comparator/equality nên kiểm thử các **tính chất**:

| Tính chất | Câu hỏi kiểm tra |
| --- | --- |
| Reflexivity | Với object `x` hợp lệ, `x.equals(x)` có luôn true? |
| Symmetry | `x.equals(y)` và `y.equals(x)` có giống nhau? |
| Transitivity | Nếu `x == y` và `y == z` theo equality tự định nghĩa, `x == z` có đúng? |
| Hash consistency | Nếu `x.equals(y)` thì hash có giống nhau? |
| Comparator sign symmetry | Dấu của `compare(x,y)` và `compare(y,x)` có ngược nhau? |
| Comparator transitivity | Nếu `x>y` và `y>z` thì có `x>z` không? |
| Comparator zero consistency | Nếu `compare(x,y)==0`, thì mọi `z` nhìn `x` và `y` theo cùng dấu thứ tự không? |
| Special values | ±0.0, NaN, ±Infinity, rất lớn/rất nhỏ được xử lý thế nào? |
| Mutable key | Khóa có bị thay đổi trong thời gian ở collection không? |

**Bộ ba bắt buộc để bắt lỗi epsilon:** `a=0.00`, `b=0.09`, `c=0.18`, `ε=0.1`. Nếu comparator trả `0` cho cặp `a,b` và `b,c` nhưng khác 0 cho `a,c`, dừng lại và thiết kế lại quan hệ, không chỉ tăng số lượng bài test.

## 16. Những ngộ nhận phổ biến

1. **“Mọi phép `double ==` đều sai.”** Không đúng. `==` là phép so sánh số học có hợp đồng xác định; sai là dùng nó cho mục tiêu gần bằng khi kết quả có sai số không được xem xét.
2. **“Thêm epsilon là phép sửa chung cho `equals`.”** Sai: gần bằng thường không bắc cầu.
3. **“`hashCode() = 1` làm equals epsilon hợp lệ.”** Sai: tính bắc cầu vẫn bị phá.
4. **“Comparator trả 0 nghĩa là khoảng cách nhỏ hơn epsilon.”** Chỉ có thể nếu quan hệ trả 0 vẫn là quan hệ tương đương hợp lệ; ngưỡng chênh lệch tùy tiện không đáp ứng.
5. **“`TreeSet` dùng `equals` để loại trùng.”** Sai: nó dùng so sánh bằng 0 của comparator/natural ordering.
6. **“Sắp xếp không ném exception là comparator đúng.”** Sai: lỗi hợp đồng có thể không lộ ở bộ dữ liệu đang kiểm tra.
7. **“Chỉ cần `a < b ? -1 : a > b ? 1 : 0` là đủ.”** Không đủ với NaN và signed zero.
8. **“`Double.compare` cũng chỉ là `a-b`.”** Sai: nó có thứ tự rõ cho NaN, ±0 và các số khác.
9. **“Bucket 0.5 tương đương gần bằng 0.5.”** Sai: hai điểm rất gần ở ranh giới bucket có thể khác nhóm.
10. **“NaN luôn bị mọi kiểu so sánh coi không bằng.”** Primitive `==` và wrapper `equals` có hợp đồng khác nhau.
11. **“Dữ liệu số đo đã gần bằng thì nên là cùng khóa HashMap.”** Không tự động; cần một chính sách danh tính ổn định.
12. **“Dùng BigDecimal thì equals luôn so sánh theo giá trị số.”** Không đúng khi scale khác nhau.
13. **“Epsilon = 1e-9 đúng cho mọi thang độ lớn.”** Sai; sai số phải theo đơn vị, quy mô và hợp đồng.
14. **“Một quan hệ bằng 0 không bắc cầu vẫn có thể thành comparator hợp lệ.”** Sai, đây là vi phạm trực tiếp hợp đồng comparator.

## 17. Bài tập có đáp án

### Bài 1 — Tìm tính chất bị vi phạm

Với `ε=0.1`, `a=0.00`, `b=0.09`, `c=0.18`, hãy xác định tính chất nào của `equals` không được bảo đảm.

**Đáp án:** tính bắc cầu. `near(a,b)` và `near(b,c)` true, nhưng `near(a,c)` false.

### Bài 2 — Comparator sai

Cho comparator trả 0 nếu `Math.abs(x-y)<=0.1`, còn lại dùng `Double.compare`. Vì sao không nên dùng nó trong `TreeSet`?

**Đáp án:** quan hệ `compare(x,y)==0` không bắc cầu. `TreeSet` dùng comparator để xác định trùng khóa, nên thứ tự chèn có thể làm kết quả khác nhau.

### Bài 3 — Phân biệt `==` với `Double.compare`

Dự đoán `-0.0 == +0.0` và `Double.compare(-0.0,+0.0)`.

**Đáp án:** `true` và `-1`. Java primitive equality coi signed zero bằng nhau, wrapper comparison có thứ tự phân biệt.

### Bài 4 — NaN

Dự đoán `Double.NaN == Double.NaN` và `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))`.

**Đáp án:** `false` và `true`, theo hợp đồng riêng của primitive equality và wrapper equality.

### Bài 5 — HashCode

Tại sao không nên viết `equals` bằng `Math.abs(a-b)<=eps` nhưng `hashCode` bằng `Double.hashCode(a)`?

**Đáp án:** hai object được coi là bằng nhau theo epsilon có thể có hash khác nhau. Điều này vi phạm yêu cầu “equals true ⇒ hashCode bằng nhau”, bên cạnh lỗi không bắc cầu.

### Bài 6 — Chọn phép so sánh đúng nhu cầu

Một phép đo nhiệt độ có dung sai ±0.2°C. Nên dùng quan hệ nào để xác định **hai phép đo chênh nhau trong dung sai**, và quan hệ nào để xác định **hai bản ghi có cùng ID**?

**Đáp án:** phép truy vấn gần bằng dựa trên `Math.abs(temp1-temp2)<=0.2` cho yêu cầu đầu; equality bằng `id` ổn định cho yêu cầu thứ hai. Không dùng khoảng cách nhiệt độ làm danh tính bản ghi.

### Bài 7 — Bucket ranh giới

Với `bucket(x)=floor(x/0.5)`, `bucket(0.49)` và `bucket(0.51)` bằng nhau không?

**Đáp án:** không; chúng thuộc bucket `0` và `1` dù chỉ cách nhau 0.02. Đây là hệ quả chính sách lượng hóa, không phải vi phạm bắc cầu.

### Bài 8 — Infinity

Tại sao `Math.abs(Double.POSITIVE_INFINITY-Double.POSITIVE_INFINITY)<=1e-6` là false?

**Đáp án:** `Infinity-Infinity` là NaN, và phép so sánh `NaN <= ...` là false. Nếu nghiệp vụ muốn nhận “cùng vô cực”, phải có quy tắc riêng.

### Bài 9 — Comparator thứ cấp

Khi sắp xếp mẫu đo theo giá trị, nếu hai giá trị bằng nhau theo `Double.compare`, bạn muốn dùng mã bản ghi để sắp thứ tự. Nên làm gì?

**Đáp án:** dùng `Comparator.comparingDouble(Sample::value).thenComparingLong(Sample::id)` với `Sample` có hai phương thức phù hợp. Không dùng epsilon comparator rồi hy vọng ID khắc phục mọi vi phạm.

### Bài 10 — Chọn cấu trúc dữ liệu

Bạn cần lưu các giá trị và cho phép truy vấn “liệt kê mọi số cách target không quá 0.1”. Có nhất thiết biến quy tắc gần bằng thành `equals`/comparator không?

**Đáp án:** không. Lưu bằng khóa/thứ tự hợp lệ (`Double.compare` hoặc khóa ID), rồi thực hiện truy vấn khoảng cách riêng trên các phần tử ứng viên. Có thể sử dụng range query có ranh giới thích hợp và lọc bằng hàm near; chính sách với NaN/Infinity phải rõ.

## 18. Checklist trước khi dùng số thực làm khóa hoặc thứ tự

- [ ] Tôi biết rõ **gần bằng** là truy vấn sai số, không mặc nhiên là equality.
- [ ] Tôi kiểm tra phản xạ, đối xứng, **bắc cầu** và `hashCode` nếu triển khai `equals`.
- [ ] Tôi kiểm tra hợp đồng `Comparator`, nhất là sự nhất quán khi `compare(a,b)==0`.
- [ ] Tôi không trả 0 trong comparator chỉ vì `Math.abs(a-b)<=epsilon`.
- [ ] Tôi dùng `Double.compare`/`Comparator.comparingDouble` khi cần thứ tự theo giá trị floating point.
- [ ] Tôi biết quy tắc khác nhau của `==` primitive, `Double.equals`, `Double.compare` với NaN và signed zero.
- [ ] Tôi chọn tolerance theo **đơn vị và thang độ lớn**, validate NaN/Infinity và trường hợp tràn.
- [ ] Nếu cần nhóm ổn định, tôi định nghĩa **khóa canonical/bucket**, chấp nhận ranh giới nhóm rõ ràng.
- [ ] Tôi không sửa trường tham gia equality/hash khi đối tượng đang nằm trong hash collection.
- [ ] Tôi kiểm tra việc sắp xếp/tập hợp với ba giá trị `0.00,0.09,0.18` cùng ±0, NaN, ±Infinity.
- [ ] Tôi đã biên dịch/chạy ít nhất ba ví dụ và hiểu vì sao kết quả khác nhau theo cơ chế collection.
- [ ] Quy tắc so sánh/nhóm/sắp xếp được ghi rõ cho người bảo trì sau này.

**Tài liệu chính thức (Java SE 17):**

- [Object.equals và Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): hợp đồng equality và hash.
- [Comparator interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): thứ tự, tính bắc cầu và consistency.
- [Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `compare`, `equals`, `hashCode`, signed zero, NaN.
- [TreeSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): thứ tự và tiêu chí bằng nhau.
- [TreeMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): sorted map theo comparator.
- [HashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): sử dụng equality/hash của khóa.
- [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `equals` phân biệt scale, `compareTo` theo giá trị số.

**Kết luận:** sai số gần bằng là **thông tin của bài toán**, còn `equals`, `hashCode` và `Comparator` là **hợp đồng cấu trúc dữ liệu**. Giữ chúng tách biệt: dùng tolerance cho truy vấn số học; dùng khóa ổn định hoặc `Double.compare` cho danh tính và thứ tự.