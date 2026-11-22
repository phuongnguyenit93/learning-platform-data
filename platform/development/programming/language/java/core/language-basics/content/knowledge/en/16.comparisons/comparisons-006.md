# So sánh số thực bằng sai số phù hợp yêu cầu — Java 17+

## 1. Mục tiêu

Khi làm việc với `float` và `double`, kết quả phép tính có thể khác giá trị toán học mong đợi một lượng nhỏ do **biểu diễn nhị phân hữu hạn và làm tròn**. Vì thế, việc kiểm tra hai kết quả tính toán “đủ gần nhau” phải sử dụng **sai số chấp nhận được theo yêu cầu thực tế**, không phải một hằng `epsilon` tùy ý.

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
~~~

Mục tiêu của bài:

- Phân biệt **so bằng chính xác** với **so gần bằng**.
- Biết chọn **sai số tuyệt đối**, **sai số tương đối** hoặc cách kết hợp.
- Hiểu cách xử lý số gần 0, số rất lớn, `NaN`, `Infinity` và `-0.0`.
- Biết khi nào **không nên dùng tolerance** mà phải chuyển sang số nguyên hoặc `BigDecimal`.
- Viết và kiểm thử được hàm so sánh gần bằng trong Java 17+.

**Nguyên tắc cốt lõi:** “Gần” chỉ có ý nghĩa khi được định nghĩa bằng **đơn vị đo, độ chính xác thiết bị/dữ liệu và mức chênh lệch mà nghiệp vụ chấp nhận**.

## 2. Vì sao `==` thường không diễn tả điều bạn muốn?

`==` kiểm tra hai giá trị `double` có bằng nhau theo quy tắc dấu phẩy động Java; nó **không tự cho phép dung sai**.

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual == expected); // false
System.out.println(actual - expected);  // 5.551115123125783E-17
~~~

`0.1`, `0.2` và `0.3` không biểu diễn đúng hoàn toàn bằng số nhị phân hữu hạn. Kết quả cộng và literal `0.3` có thể nằm ở **hai giá trị `double` kế cận nhau**.

Tuy nhiên, **`==` không phải luôn sai**. Nó phù hợp khi cần so chính xác một giá trị biểu diễn có chủ đích, chẳng hạn những trạng thái số hữu hạn/giá trị sentinel đã được đặc tả rõ. Khi yêu cầu là “chênh lệch không vượt quá sai số cho phép”, hãy định nghĩa phép so gần bằng riêng.

**Phân biệt:**

| Yêu cầu | Cách tiếp cận |
|---|---|
| Hai giá trị primitive phải bằng nhau đúng theo Java | `a == b` |
| Hai kết quả đo được chấp nhận nếu lệch không quá 0,05 mm | Sai số tuyệt đối **0,05 mm** |
| Sai số chấp nhận phụ thuộc quy mô đại lượng | Sai số tương đối |
| Cần chấp nhận chênh lệch cả gần 0 và số rất lớn | Kết hợp tuyệt đối + tương đối |
| Số tiền thập phân phải chính xác đến cent | Mô hình số nguyên theo cent hoặc `BigDecimal` với rounding rõ |
| Cần so một ID hoặc bộ đếm nguyên lớn | `int`/`long`/`BigInteger`, không dùng float/double |

## 3. Sai số tuyệt đối (*absolute tolerance*)

Hai giá trị `a` và `b` được coi là gần nhau theo sai số tuyệt đối `absTol` khi:

\[
|a-b| \le \text{absTol}
\]

Ví dụ một cảm biến đo chiều dài, yêu cầu lệch tối đa **0,05 mm**:

~~~java
double targetMm = 12.0;
double measuredMm = 12.04;
double allowedErrorMm = 0.05;

boolean acceptable =
        Math.abs(measuredMm - targetMm) <= allowedErrorMm;
System.out.println(acceptable); // true
~~~

Nếu kết quả đo là `12.08` mm, mức chênh lệch lớn hơn 0,05 mm và không đạt.

**Ưu điểm:** dễ giải thích theo đơn vị thực (`mm`, `°C`, `s`, `V`). **Hạn chế:** cùng một sai số tuyệt đối có thể quá dễ dãi với số rất nhỏ hoặc quá khắt khe với số rất lớn.

Ví dụ: sai số 0,05 m phù hợp hay không còn tùy đang đo kích thước linh kiện vài milimét hay chiều dài hàng kilomet.

**Không quên đơn vị:** nếu `a` đo bằng mét và `b` đo bằng milimét, phải **quy đổi về cùng đơn vị trước khi so sánh**. Bản thân hàm tính chênh lệch không nhận biết đơn vị.

## 4. Sai số tương đối (*relative tolerance*)

Sai số tương đối đánh giá độ chênh so với **quy mô của giá trị**. Một quy tắc đối xứng thường dùng:

\[
|a-b| \le \text{relTol}\times\max(|a|,|b|)
\]

Ví dụ:

~~~java
double a = 1_000_000_000.0;
double b = 1_000_000_001.0;
double relativeTolerance = 1e-8;

double difference = Math.abs(a - b);
double scale = Math.max(Math.abs(a), Math.abs(b));
boolean close = difference <= relativeTolerance * scale;

System.out.println(close); // true
~~~

Chênh lệch tuyệt đối là 1, nhưng tỷ lệ so với quy mô 1 tỷ chỉ xấp xỉ `1e-9`; mức cho phép `1e-8` chấp nhận được.

**Ưu điểm:** tỉ lệ sai số tự thay đổi theo độ lớn. **Hạn chế lớn:** khi một giá trị bằng 0, công thức thuần tương đối rất khắt khe:

~~~java
double a = 4e-10;
double b = 0.0;
double relTol = 1e-5;

// |a-b| = 4e-10; relTol * max(|a|, |b|) = 4e-15
// Kết quả: không gần nhau theo quy tắc chỉ tương đối này.
~~~

Nếu nghiệp vụ cho rằng `4e-10` gần 0 đủ để chấp nhận, phải có một **ngưỡng tuyệt đối gần 0**. Đây là lý do nhiều ứng dụng dùng cả hai loại dung sai.

## 5. Kết hợp tuyệt đối và tương đối

Một lựa chọn phổ biến khi muốn “đủ gần theo ít nhất một tiêu chí”:

\[
|a-b| \le \max(\text{absTol},\,\text{relTol}\times\max(|a|,|b|))
\]

Tương đương kiểm tra:

~~~java
difference <= absTol || difference <= relTol * scale
~~~

Cách hiểu:

- **Gần 0:** `absTol` xử lý chênh lệch nhỏ mang ý nghĩa tuyệt đối.
- **Ở quy mô lớn:** `relTol` cho phép chênh lệch tăng theo độ lớn đại lượng.
- **Miền trung gian:** dùng tiêu chí có ngưỡng rộng hơn.

| Trường hợp | absTol | relTol | Điều được kiểm tra |
|---|---:|---:|---|
| `0.1+0.2` so với `0.3` | `1e-12` | `1e-12` | Sai số tính toán rất nhỏ |
| `4e-10` so với `0` | `1e-9` | `1e-5` | Chấp nhận gần zero bằng ngưỡng tuyệt đối |
| `1e9` so với `1e9+1` | `0.01` | `1e-8` | Chấp nhận sai lệch theo quy mô lớn |
| `12.04` so với `12.0` mm | `0.05` | `0` | Dung sai thiết bị cố định 0,05 mm |

**Đây là quy tắc ví dụ, không phải định lý rằng OR luôn đúng cho mọi lĩnh vực.** Có hệ thống yêu cầu phải đạt **đồng thời** hai ràng buộc, hoặc cần kiểm tra giới hạn một chiều (chỉ được cao hơn/thấp hơn một giá trị); khi đó phải viết đúng chính sách nghiệp vụ.

## 6. Hàm Java 17 minh họa: `nearlyEqualFinite`

Hàm dưới đây dành cho **hai số hữu hạn** và hai ngưỡng không âm, hữu hạn. Nó **cố ý trả false** nếu đầu vào là `NaN` hoặc `Infinity`.

~~~java
static boolean nearlyEqualFinite(
        double a, double b, double absTol, double relTol) {
    if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
            || absTol < 0 || relTol < 0 || relTol > 1) {
        throw new IllegalArgumentException("invalid tolerances");
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    if (a == b) {
        return true; // Bao gồm +0.0 và -0.0
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));

    return difference <= absTol || difference <= relTol * scale;
}
~~~

Sử dụng:

~~~java
System.out.println(
        nearlyEqualFinite(0.1 + 0.2, 0.3, 1e-12, 1e-12)
); // true

System.out.println(
        nearlyEqualFinite(1.0, 1.1, 1e-12, 1e-12)
); // false
~~~

**Lựa chọn chính sách trong hàm:**

1. Ngưỡng âm, `NaN`, Infinity hoặc `relTol > 1` là **tham số không hợp lệ**, nên ném `IllegalArgumentException`.
2. Hai đầu vào cần **hữu hạn**; cùng Infinity cũng trả `false` vì đây không phải một phép so hai đại lượng đo hữu hạn.
3. Hai giá trị bằng nhau theo `==` được chấp nhận; `+0.0` và `-0.0` vì thế được xem là gần nhau.
4. Nếu khác nhau, chênh lệch phải nằm trong **ít nhất một trong hai ngưỡng**.

**Giới hạn số học:** `a-b` vẫn có thể overflow thành Infinity nếu `a` và `b` hữu hạn nhưng cực lớn và trái dấu; các phép nhân và trừ `double` cũng có thể underflow/làm tròn. Hàm được thiết kế để **minh họa và dùng cho các miền đã kiểm soát**, không thay thế thuật toán so sánh chuẩn số học cho toàn bộ cực trị binary64. Với dữ liệu cực trị, cần đặc tả và kiểm thử riêng.

## 7. Chọn tolerance dựa trên yêu cầu, không dựa trên thói quen

Không có con số **`1e-6`**, **`1e-9`** hay **`1e-12`** nào đúng cho mọi bài toán.

Hãy trả lời:

1. **Đang đo đại lượng gì?** Độ dài, tiền, xác suất, áp suất, thời gian, tọa độ, nhiệt độ?
2. **Đơn vị và khoảng giá trị?** Mét hay millimét, giây hay nano giây, quanh 0 hay hàng tỷ?
3. **Sai số đầu vào là bao nhiêu?** Độ phân giải cảm biến, rounding từ dữ liệu, chất lượng thuật toán?
4. **Hậu quả khi chấp nhận nhầm?** Lỗi hiển thị đơn giản hay ảnh hưởng tính tiền, cảnh báo an toàn?
5. **Dùng so sánh để làm gì?** Kiểm tra kết quả tính toán, kiểm thử phần mềm, phân nhóm dữ liệu hay quyết định điều khiển?
6. **Ngưỡng có cần tính vào biên không?** `<=` cho phép bằng đúng biên, còn `<` thì không.

Ví dụ, cảm biến có sai số công bố ±0,05 mm thì một lựa chọn **có cơ sở nghiệp vụ** là `absTol = 0.05` mm sau khi quy đổi đơn vị, không phải mặc định dùng `Double.MIN_VALUE` hay `1e-12`.

Đối với kiểm thử thuật toán số, ngưỡng cần xét cả **sai số thuật toán**, độ nhạy bài toán và định dạng số; không nên chỉ nhìn vào số chữ số được hiển thị.

## 8. Hiểu `Math.ulp` và độ phân giải

`Math.ulp(x)` biểu diễn độ lớn một đơn vị ở vị trí thấp nhất của định dạng số thực tại giá trị `x` theo định nghĩa API. Nó hữu ích khi xem **khoảng cách biểu diễn** gần một số.

~~~java
double one = 1.0;
double next = Math.nextUp(one);

System.out.println(next);          // 1.0000000000000002
System.out.println(Math.ulp(one)); // 2.220446049250313E-16
System.out.println(next == one);   // false
~~~

`Math.nextUp(1.0)` là giá trị `double` biểu diễn được ngay sau 1.0. Tại 1.0, khoảng cách ấy bằng `Math.ulp(1.0)`.

**Không nhầm `Double.MIN_VALUE` với epsilon cho mọi phép so**: `Double.MIN_VALUE` là số dương nhỏ nhất khác 0 biểu diễn được dưới dạng `double`, không phải “sai số máy chung” quanh các giá trị bất kỳ.

So sánh theo số ULP có thể hữu ích trong kiểm thử thuật toán dấu phẩy động, nhưng cần quy tắc riêng cho số âm, zero, subnormal, Infinity, NaN và độ lớn. Nó **không thay thế tự động** dung sai nghiệp vụ như 0,05 mm.

## 9. `NaN`, Infinity và signed zero

### `NaN`

~~~java
double nan = Double.NaN;
System.out.println(nan == nan);       // false
System.out.println(Double.isNaN(nan)); // true
~~~

`NaN` không bằng ngay cả chính nó dưới toán tử `==`. Do đó kiểm tra `Math.abs(a-b) <= tolerance` cũng không cung cấp một quy tắc gần bằng có ý nghĩa khi một toán hạng là NaN. Cần **quy định chính sách rõ ràng**: reject, trả false hoặc báo lỗi.

### Infinity

~~~java
System.out.println(Double.POSITIVE_INFINITY
        == Double.POSITIVE_INFINITY); // true
~~~

Toán tử `==` cho true với cùng Infinity, nhưng hàm `nearlyEqualFinite` ở trên **trả false có chủ đích** vì chỉ so đại lượng hữu hạn. Không có một lựa chọn đúng chung: tùy hợp đồng phần mềm.

### Zero có dấu

~~~java
System.out.println(+0.0 == -0.0); // true
~~~

`+0.0` và `-0.0` có thể khác biểu diễn bit và tạo nghịch đảo Infinity khác dấu, nhưng `==` xem là bằng nhau. Nếu nghiệp vụ cần phân biệt **dấu zero hoặc bit pattern**, dùng API chuyên biệt thay vì phép so gần bằng.

**Chốt lại:** nên tách việc **kiểm tra dữ liệu đầu vào** (`Double.isFinite`) khỏi việc **so gần bằng**.

## 10. Khi `float`/`double` không phải giải pháp đúng

Dùng dung sai không phải cách hợp thức hóa một mô hình dữ liệu sai.

**Tiền tệ:** Nếu phải cộng `0.1 + 0.2` chính xác theo thập phân, cân nhắc:

~~~java
java.math.BigDecimal amount =
        new java.math.BigDecimal("0.1")
                .add(new java.math.BigDecimal("0.2"));

System.out.println(amount); // 0.3
~~~

Tạo `BigDecimal` từ chuỗi decimal giúp giữ đúng giá trị nhập. Dùng `BigDecimal.compareTo` khi muốn so **giá trị số**, và xác định `scale`/`RoundingMode` cho phép chia hoặc nghiệp vụ tiền tệ.

**ID / bộ đếm:** Giữ `long` hoặc `BigInteger`, không đổi sang `double` để “so gần bằng”: số nguyên lớn có thể mất độ chính xác khi chuyển thành floating-point.

**Giới hạn an toàn:** Với ràng buộc “nhiệt độ không được vượt 80 °C”, cần chính sách **so biên** rõ ràng, không tự thay bằng `nearlyEqual(temp, 80)` và coi mọi giá trị gần 80 là an toàn. Tolerance có thể hợp lý với cảm biến, nhưng phải gắn với độ bất định, cơ chế fail-safe và yêu cầu an toàn thực tế.

## 11. Tích lũy sai số và so sánh sau vòng lặp

~~~java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}

System.out.println(total);        // 0.9999999999999999
System.out.println(total == 1.0); // false
~~~

Mỗi phép cộng có thể làm tròn một lần. Kiểm thử chỉ dựa vào `total == 1.0` có thể thất bại dù thuật toán có sai số nằm trong giới hạn chấp nhận.

~~~java
System.out.println(
        nearlyEqualFinite(total, 1.0, 1e-12, 1e-12)
); // true
~~~

Nhưng **không đặt tolerance quá rộng** chỉ để làm test xanh. Nếu thuật toán đáng lẽ trả kết quả chính xác (ví dụ xử lý số tiền theo cent), nên sửa **mô hình tính**. Với thuật toán số học, ngưỡng nên xuất phát từ **error budget** và dữ liệu đại diện.

## 12. Các lỗi thường gặp

| Lỗi/nhầm lẫn | Vì sao nguy hiểm? | Hướng xử lý |
|---|---|---|
| `0.1 + 0.2 == 0.3` luôn true | Binary64 làm tròn | Dung sai được đặc tả, hoặc decimal exact |
| Luôn đặt epsilon `1e-9` | Đơn vị/miền số khác nhau | Chọn ngưỡng theo bài toán |
| Dùng chỉ sai số tương đối gần zero | Ngưỡng tương đối tiến về 0 | Kết hợp ngưỡng tuyệt đối |
| Dùng chỉ sai số tuyệt đối cho giá trị cực lớn | Có thể quá khắt khe | Xét relative tolerance |
| Cho rằng `Double.MIN_VALUE` là epsilon phổ dụng | Đây là dương nhỏ nhất khác 0 | Xem `Math.ulp` và sai số được phép |
| Không validate tolerance âm/NaN/Infinity | Điều kiện so trở nên vô nghĩa | Kiểm tra ngưỡng trước |
| Coi NaN gần bằng NaN vì cùng trạng thái | Không phải số hữu hạn | Quy định chính sách NaN riêng |
| Dùng `==` với Infinity và coi là số đo hợp lệ | Infinity không hữu hạn | `Double.isFinite` khi cần |
| So đại lượng khác đơn vị | Kết luận sai dù code đúng cú pháp | Quy đổi về cùng đơn vị |
| Chấp nhận lệch quá lớn vì `relTol` rộng | False positive | Dựa vào giới hạn nghiệp vụ |
| Dùng tolerance cho tiền/ID nguyên | Che sai mô hình số | `long` theo đơn vị cố định hoặc `BigDecimal` |
| Không test tại biên tolerance | Bug do `<` vs `<=`, rounding | Kiểm thử sát biên và miền cực trị |
| Xem hàm mẫu là giải pháp tổng quát mọi `double` | Overflow/underflow trong `a-b` và phép nhân | Thuật toán chuyên biệt khi cần |

## 13. Ví dụ Java 17 hoàn chỉnh, chạy độc lập

Tạo file đúng tên **`FloatingPointToleranceDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class FloatingPointToleranceDemo {
    private FloatingPointToleranceDemo() {}

    static boolean nearlyEqualFinite(
            double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0 || relTol < 0 || relTol > 1) {
            throw new IllegalArgumentException("invalid tolerances");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double computed = 0.1 + 0.2;
        System.out.println("computed=" + computed);
        System.out.println("exact equality=" + (computed == 0.3));
        System.out.println("decimal near="
                + nearlyEqualFinite(computed, 0.3, 1e-12, 1e-12));
        System.out.println("decimal too strict="
                + nearlyEqualFinite(computed, 0.3, 1e-18, 0));
        System.out.println("different number="
                + nearlyEqualFinite(computed, 0.4, 1e-12, 1e-12));

        System.out.println("near zero absolute="
                + nearlyEqualFinite(4e-10, 0.0, 1e-9, 0.0));
        System.out.println("near zero relative only="
                + nearlyEqualFinite(4e-10, 0.0, 0, 1e-5));

        System.out.println("large relative="
                + nearlyEqualFinite(1e9, 1e9 + 1, 0, 1e-8));
        System.out.println("large absolute only="
                + nearlyEqualFinite(1e9, 1e9 + 1, 0.01, 0));
        System.out.println("large different="
                + nearlyEqualFinite(1e9, 1e9 + 100, 0.01, 1e-8));

        System.out.println("sensor acceptable="
                + nearlyEqualFinite(12.04, 12.0, 0.05, 0));
        System.out.println("sensor rejected="
                + nearlyEqualFinite(12.08, 12.0, 0.05, 0));

        double next = Math.nextUp(1.0);
        System.out.println("next double=" + next);
        System.out.println("ULP at one=" + Math.ulp(1.0));
        System.out.println("next exact=" + (next == 1.0));

        double total = 0;
        for (int i = 0; i < 10; i++) {
            total += 0.1;
        }
        System.out.println("repeated sum=" + total);
        System.out.println("repeated near one="
                + nearlyEqualFinite(total, 1.0, 1e-12, 1e-12));

        System.out.println("signed zero="
                + nearlyEqualFinite(0.0, -0.0, 0, 0));
        System.out.println("NaN near="
                + nearlyEqualFinite(Double.NaN, Double.NaN, 1e-6, 1e-6));
        System.out.println("Infinity near="
                + nearlyEqualFinite(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-6, 1e-6));

        BigDecimal decimal = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal exact sum=" + decimal);
        System.out.println("decimal compare="
                + (decimal.compareTo(new BigDecimal("0.3")) == 0));

        try {
            nearlyEqualFinite(1.0, 1.0, -1.0, 1e-6);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad tolerance=" + ex.getMessage());
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên. Đặt terminal tại thư mục có file. Không cần Maven, Gradle hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FloatingPointToleranceDemo.java
java -cp . FloatingPointToleranceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FloatingPointToleranceDemo.java
java -cp . FloatingPointToleranceDemo
~~~

**Exact expected stdout:**

~~~text
computed=0.30000000000000004
exact equality=false
decimal near=true
decimal too strict=false
different number=false
near zero absolute=true
near zero relative only=false
large relative=true
large absolute only=false
large different=false
sensor acceptable=true
sensor rejected=false
next double=1.0000000000000002
ULP at one=2.220446049250313E-16
next exact=false
repeated sum=0.9999999999999999
repeated near one=true
signed zero=true
NaN near=false
Infinity near=false
decimal exact sum=0.3
decimal compare=true
bad tolerance=invalid tolerances
~~~

### Cách đọc kết quả

1. `computed` và `exact equality`: hai biểu thức thập phân gần nhau nhưng không có cùng biểu diễn binary64.
2. `decimal near=true` nhưng `decimal too strict=false`: **chọn tolerance ảnh hưởng kết luận**; không có một ngưỡng đúng toàn cục.
3. `near zero absolute=true` / `relative only=false`: ngưỡng tuyệt đối có vai trò đặc biệt quanh zero.
4. `large relative=true` nhưng `large absolute only=false`: mức chênh 1 có thể nhỏ theo quy mô 1 tỷ.
5. Hai dòng cảm biến minh họa việc đặt ngưỡng theo **mm**, không theo mặc định của ngôn ngữ.
6. `Math.nextUp` và `Math.ulp` cho thấy các giá trị double biểu diễn được nằm cách nhau một khoảng hữu hạn.
7. Cộng 0.1 lặp nhiều lần có thể tích lũy sai số; so gần bằng chấp nhận sai lệch theo quy định.
8. `NaN` và Infinity không được hàm **finite-only** chấp nhận; signed zero thì được.
9. `BigDecimal` từ chuỗi cho phép cộng decimal chính xác trong ví dụ.
10. Tolerance âm bị từ chối để không âm thầm trả kết quả không có ý nghĩa.

## 14. Bài tập có đáp án

### Bài A — so gần bằng

~~~java
double result = 0.1 + 0.2;
System.out.println(result == 0.3);
System.out.println(nearlyEqualFinite(result, 0.3, 1e-12, 1e-12));
~~~

**Đáp án:**

~~~text
false
true
~~~

Hàm `nearlyEqualFinite` đã được định nghĩa ở trên. `==` so đúng giá trị nhị phân, còn hàm cho phép sai lệch nhỏ được khai báo.

### Bài B — gần 0

Hai kết quả `a = 5e-10`, `b = 0`. Nghiệp vụ chấp nhận sai lệch tối đa `1e-9` (cùng đơn vị).

**Đáp án:**

~~~java
boolean accepted = nearlyEqualFinite(5e-10, 0.0, 1e-9, 0.0);
System.out.println(accepted); // true
~~~

Trong trường hợp này, sai số tuyệt đối mô tả đúng yêu cầu.

### Bài C — giá trị lớn

Hai số lần lượt là `1_000_000_000` và `1_000_000_001`. Cho phép mức chênh tương đối `1e-8`.

**Đáp án:**

~~~java
boolean accepted =
        nearlyEqualFinite(1e9, 1e9 + 1, 0, 1e-8);
System.out.println(accepted); // true
~~~

### Bài D — dữ liệu NaN

~~~java
double x = Double.NaN;
System.out.println(x == x);
System.out.println(nearlyEqualFinite(x, x, 1e-3, 1e-3));
~~~

**Đáp án:**

~~~text
false
false
~~~

Hàm ở bài này có chính sách **không chấp nhận số không hữu hạn**.

### Bài E — khi nào không nên dùng tolerance?

Yêu cầu cộng giá tiền thập phân `0.1` và `0.2`, sau đó so với `0.3` chính xác.

**Đáp án:** không nên “nới epsilon” để hợp thức hóa tiền; dùng số nguyên theo đơn vị nhỏ nhất khi thích hợp hoặc `BigDecimal` từ chuỗi:

~~~java
BigDecimal sum = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
boolean exact = sum.compareTo(new BigDecimal("0.3")) == 0;
~~~

### Bài F — thiết kế kiểm thử tại biên

Nếu dung sai cho phép là 0,05 mm, nên thử các giá trị nào?

**Đáp án:** ít nhất nên thử chênh lệch 0, chênh lệch nhỏ hơn ngưỡng, sát ngưỡng dưới/trên và lớn hơn ngưỡng; đồng thời kiểm tra số âm, zero và dữ liệu không hữu hạn theo chính sách. Do chính `0.05` không có biểu diễn nhị phân chính xác, nếu hợp đồng đòi biên decimal tuyệt đối chính xác, có thể cần mô hình decimal thay vì kỳ vọng bit của `double` luôn trùng biên toán học.

## 15. Checklist và kết luận

- [ ] Phân biệt phép `==` chính xác với so gần bằng theo yêu cầu.
- [ ] Hiểu nguồn sai lệch của `float`/`double` là biểu diễn nhị phân hữu hạn và rounding.
- [ ] Biết chọn **absolute tolerance** theo đơn vị/độ phân giải dữ liệu.
- [ ] Biết chọn **relative tolerance** khi miền giá trị thay đổi theo quy mô.
- [ ] Hiểu vì sao gần zero cần cân nhắc ngưỡng tuyệt đối.
- [ ] Định nghĩa rõ **OR/AND** của hai ngưỡng theo chính sách chấp nhận sai số.
- [ ] Không áp đặt một epsilon cho mọi bài toán.
- [ ] Kiểm tra tính hữu hạn và tính hợp lệ của ngưỡng.
- [ ] Phân biệt `Double.MIN_VALUE` với ULP/độ phân giải.
- [ ] Hiểu `NaN`, Infinity và signed zero cần chính sách tường minh.
- [ ] Không dùng tolerance để so tiền, ID hoặc dữ liệu đòi tính chính xác tuyệt đối.
- [ ] Biết phép trừ `a-b` cũng có rủi ro rounding/overflow ở cực trị.
- [ ] Chạy `FloatingPointToleranceDemo.java` bằng `javac`/`java` trên Java 17+ và đối chiếu exact stdout.

**Kết luận:** So sánh số thực “đủ gần” không bắt đầu từ `1e-9`, mà bắt đầu từ câu hỏi **“mức lệch nào là chấp nhận được, tính bằng đơn vị gì, ở quy mô nào?”**. Dựa trên câu trả lời, hãy chọn sai số tuyệt đối, tương đối hoặc kết hợp chúng, kiểm soát `NaN`/Infinity và kiểm thử trường hợp biên. Nếu yêu cầu là chính xác thập phân hoặc số nguyên, hãy chọn **mô hình dữ liệu chính xác** thay vì dùng dung sai để che lỗi.