# Kết hợp sai số tuyệt đối và tương đối khi so sánh số thực trong Java

## 1. Vì sao so sánh số thực cần ngưỡng sai số?

`float` và `double` trong Java dùng biểu diễn dấu phẩy động nhị phân. Nhiều giá trị thập phân, như `0.1`, không có biểu diễn nhị phân hữu hạn chính xác. Khi tính toán, các phép toán có thể làm tròn, tạo ra kết quả gần với giá trị mong đợi nhưng không có cùng mẫu bit.

Ví dụ:

```java
double computed = 0.1 + 0.2;
double expected = 0.3;

System.out.println(computed == expected); // false
System.out.println(computed);              // 0.30000000000000004
System.out.println(expected);              // 0.3
```

`==` trả lời câu hỏi: *hai toán hạng `double` hiện có bằng nhau theo quy tắc toán tử Java hay không?* Nó không trả lời câu hỏi: *hai giá trị có đủ gần nhau theo dung sai của bài toán hay không?*

Khi bài toán cho phép sai số, ta thường so sánh:

\[
|a-b|\le T,
\]

trong đó `T` là ngưỡng dung sai (*tolerance*). Vấn đề là **ngưỡng nào phù hợp với độ lớn của dữ liệu**. Một ngưỡng cố định có thể hợp lý ở gần 0 nhưng quá chặt với số lớn; ngược lại, ngưỡng tỷ lệ theo độ lớn có thể gần bằng 0 và không bảo vệ được các kết quả nhỏ.

Vì vậy, trong nhiều bài toán tính gần đúng, ta kết hợp **sai số tuyệt đối** và **sai số tương đối**. Đây là tiêu chí chấp nhận sai lệch do ứng dụng chọn, không phải quy tắc “làm cho mọi phép so sánh `double` đều đúng”.

## 2. Sai số tuyệt đối và tương đối khác nhau ở đâu?

### 2.1. Sai số tuyệt đối

Với giá trị tính được `a` và giá trị tham chiếu `b`:

\[
E_{\text{abs}}=|a-b|.
\]

Ví dụ `a = 10.002`, `b = 10.000` có sai số tuyệt đối xấp xỉ `0.002`. Nếu dữ liệu là mét thì dung sai tuyệt đối cũng được hiểu theo đơn vị mét; nếu là giây thì theo đơn vị giây.

Điều kiện so sánh chỉ dùng sai số tuyệt đối:

\[
|a-b|\le \text{absTol}.
\]

Trong Java:

```java
boolean closeByAbsoluteTolerance =
        Math.abs(a - b) <= absTol;
```

Đoạn trên là **minh họa biểu thức**, giả sử `a`, `b`, `absTol` đã được khai báo và đều là giá trị hữu hạn, `absTol >= 0`. Đối với dữ liệu bất kỳ, phải xử lý riêng `NaN`, vô cực và trường hợp phép trừ tràn ra vô cực.

Sai số tuyệt đối phù hợp khi có một khoảng sai lệch tối đa mang ý nghĩa thực tế. Chẳng hạn, nếu cảm biến đo chiều dài chấp nhận lệch `0.001` mét, ngưỡng tuyệt đối `0.001` có thể có ý nghĩa dù số đo nằm gần 0.

Nhược điểm: một ngưỡng như `1e-9` có thể quá lớn khi so sánh các giá trị cỡ `1e-12`, nhưng lại quá nhỏ khi so sánh kết quả có độ lớn hàng tỷ.

### 2.2. Sai số tương đối

Khi có giá trị tham chiếu `b != 0`, dạng thường dùng là:

\[
E_{\text{rel,ref}}=\frac{|a-b|}{|b|}.
\]

Nếu `b = 1_000_000` và `a = 1_000_000.001`, sai lệch tuyệt đối khoảng `0.001`, nhưng sai lệch tương đối khoảng `10^{-9}` (một phần tỷ).

Đây là cách diễn giải tốt khi **`b` là một giá trị chuẩn có ý nghĩa**, ví dụ kết quả tham chiếu độc lập hoặc chuẩn hiệu chuẩn. Nhưng mẫu số `|b|` gây vấn đề khi `b = 0` và làm tiêu chí rất khắt khe khi `b` cực nhỏ.

Trong so sánh **hai kết quả ngang vai trò** (không có bên nào là chuẩn), thường dùng chuẩn hóa đối xứng:

\[
S=\max(|a|,|b|),\qquad
|a-b|\le \text{relTol}\times S.
\]

Cách này không ưu tiên bên nào, và cùng kết quả khi đổi vị trí `a`, `b`. `relTol` không có đơn vị; chẳng hạn `1e-9` tương ứng dung sai ở mức khoảng một phần tỷ **theo thang độ lớn `S`**. Nếu cả hai cùng bằng 0, cần xử lý riêng hoặc kết hợp ngưỡng tuyệt đối.

**Phân biệt rõ:** “Sai số tương đối” có nhiều cách định nghĩa mẫu số tùy bài toán. Dùng `max(|a|, |b|)` là một lựa chọn đối xứng cho phép so sánh gần bằng nhau, không phải mẫu số duy nhất đúng trong mọi lĩnh vực.

## 3. Kết hợp hai ngưỡng thành một phép so sánh

Một tiêu chí phổ biến:

\[
\boxed{|a-b|\le\max\bigl(\text{absTol},
\text{relTol}\cdot\max(|a|,|b|)\bigr)}
\]

trong đó:

- `absTol >= 0`: dung sai tuyệt đối, cùng đơn vị với `a` và `b`;
- `relTol >= 0`: dung sai tương đối, không có đơn vị;
- `max(|a|, |b|)`: thang độ lớn đối xứng;
- dấu `<=` quy định sai lệch đúng bằng ngưỡng cũng được chấp nhận.

Điều kiện trên tương đương:

\[
|a-b|\le\text{absTol}
\quad\text{HOẶC}\quad
|a-b|\le\text{relTol}\times\max(|a|,|b|).
\]

Nghĩa là hai giá trị được coi là “đủ gần” nếu đáp ứng **ít nhất một** tiêu chí. Khi một giá trị gần 0, ngưỡng tuyệt đối bảo vệ phép so sánh. Khi cả hai có độ lớn đáng kể, ngưỡng tương đối thường là phần quyết định.

Một quy tắc khác cũng hợp lệ tùy tài liệu/ứng dụng là:

\[
|a-b|\le \text{absTol}
+\text{relTol}\cdot\max(|a|,|b|).
\]

Dạng **cộng** rộng hơn hoặc bằng dạng **max** vì tổng hai số không âm không nhỏ hơn số lớn nhất. Không nên xem hai dạng tương đương hoặc dùng lẫn nếu cần kết quả nhất quán với một tiêu chuẩn, thư viện hay hệ thống kiểm thử cụ thể. Bài này dùng **dạng max** xuyên suốt để dễ giải thích và kiểm thử.

### Minh họa tại ba thang đo

Giả sử `absTol = 1e-9`, `relTol = 1e-9`:

| Cặp giá trị | Hiệu tuyệt đối xấp xỉ | Ngưỡng chi phối | Đủ gần? |
| --- | ---: | --- | --- |
| `0.0` và `1e-10` | `1e-10` | `absTol = 1e-9` | Có |
| `0.0` và `1e-7` | `1e-7` | `absTol = 1e-9` | Không |
| `1e6` và `1e6 + 1e-4` | `1e-4` | `relTol × 1e6 ≈ 1e-3` | Có |
| `1e6` và `1e6 + 1e-2` | `1e-2` | `relTol × 1e6 ≈ 1e-3` | Không |
| `100.0` và `101.0` | `1.0` | `relTol × 101 ≈ 1.01e-7` | Không |

Các kết luận phụ thuộc **cặp ngưỡng đã chọn**. Không có một cặp `absTol`/`relTol` mặc định thích hợp cho mọi thang đo, mọi phép tính và mọi yêu cầu chính xác.

### Vì sao không áp dụng ngưỡng tương đối ở gần 0 một cách đơn độc?

Với `a = 0.0` và `b = 1e-12`, ta có `S = 1e-12`. Nếu `relTol = 1e-9` thì ngưỡng tương đối chỉ là `1e-21`, nên phép so sánh báo khác nhau dù chênh lệch `1e-12` có thể nhỏ hơn sai số đo hợp lệ. Ngưỡng tuyệt đối cung cấp một mức chấp nhận sai lệch thực tế quanh 0.

Ngược lại, nếu dữ liệu thực sự cần phân biệt `0` với `1e-12` (ví dụ tín hiệu cỡ pico), đặt `absTol = 1e-9` sẽ quá dễ dãi. **Đơn vị và yêu cầu nghiệp vụ phải quyết định `absTol`**, chứ không phải thói quen dùng `1e-9` trong mọi chương trình.

## 4. Hàm `approximatelyEqual` cho `double` trong Java 17

Một hàm sử dụng được phải làm rõ cả cách xử lý giá trị đặc biệt. Trong bài này, ta chọn chính sách:

- `NaN` không “gần bằng” bất kỳ giá trị nào, kể cả `NaN`.
- Hai vô cực **cùng dấu** được coi bằng nhau vì chúng bằng nhau theo `==`; vô cực khác dấu hoặc so với số hữu hạn không được coi là gần.
- `+0.0` và `-0.0` được coi bằng nhau về giá trị số.
- Dung sai phải hữu hạn, không âm; để tránh dung sai tương đối quá dễ dãi, yêu cầu `relTol < 1.0`.
- Với hai giá trị hữu hạn không bằng nhau chính xác, áp dụng công thức kết hợp dạng `max`.

Lưu thành tệp `ApproximatelyEqual.java`:

```java
public final class ApproximatelyEqual {
    private ApproximatelyEqual() {
    }

    public static boolean isClose(
            double a, double b, double absTol, double relTol) {

        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("Invalid tolerances");
        }

        // Theo chính sách của ví dụ, NaN không so sánh gần bằng.
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }

        // Gồm hai số hữu hạn bằng nhau, ±0.0, và vô cực cùng dấu.
        if (a == b) {
            return true;
        }

        // Nếu còn vô cực mà chưa bằng nhau thì không chấp nhận.
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double limit = Math.max(absTol, relTol * scale);

        return difference <= limit;
    }

    public static void main(String[] args) {
        double absTol = 1e-9;
        double relTol = 1e-9;

        System.out.println("0.1 + 0.2 == 0.3: " + (0.1 + 0.2 == 0.3));
        System.out.println("decimal close: "
                + isClose(0.1 + 0.2, 0.3, absTol, relTol));
        System.out.println("near zero small: "
                + isClose(0.0, 1e-10, absTol, relTol));
        System.out.println("near zero large: "
                + isClose(0.0, 1e-7, absTol, relTol));
        System.out.println("large values close: "
                + isClose(1e6, 1e6 + 1e-4, absTol, relTol));
        System.out.println("large values far: "
                + isClose(1e6, 1e6 + 1e-2, absTol, relTol));
        System.out.println("NaN: "
                + isClose(Double.NaN, Double.NaN, absTol, relTol));
        System.out.println("same infinity: "
                + isClose(Double.POSITIVE_INFINITY,
                          Double.POSITIVE_INFINITY, absTol, relTol));
        System.out.println("infinity vs finite: "
                + isClose(Double.POSITIVE_INFINITY,
                          Double.MAX_VALUE, absTol, relTol));
        System.out.println("signed zeros: "
                + isClose(-0.0, +0.0, absTol, relTol));
        System.out.println("opposite extremes: "
                + isClose(-Double.MAX_VALUE,
                          Double.MAX_VALUE, absTol, relTol));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ApproximatelyEqual.java
java ApproximatelyEqual
```

Kết quả:

```text
0.1 + 0.2 == 0.3: false
decimal close: true
near zero small: true
near zero large: false
large values close: true
large values far: false
NaN: false
same infinity: true
infinity vs finite: false
signed zeros: true
opposite extremes: false
```

Hàm này nhận giá trị `double` đã tính xong. Nó **không sửa hoặc phục hồi độ chính xác** đã mất trong một phép tính. Việc trả `true` chỉ biểu thị cặp giá trị **đạt tiêu chí dung sai cụ thể**.

### Tại sao phải kiểm tra `NaN` và vô cực trước?

`NaN` có tính chất `Double.NaN == Double.NaN` là `false`; phép trừ với `NaN` cũng cho `NaN`. Mọi phép so sánh `NaN <= limit` đều trả `false`. Tuy nhiên, kiểm tra tường minh thể hiện đúng chính sách, tránh vô tình thay đổi hành vi khi sửa thuật toán.

`Infinity - Infinity` tạo `NaN`; vì vậy nếu chỉ tính `Math.abs(a-b)`, hai vô cực cùng dấu có thể bị báo khác nhau. Ví dụ chủ động công nhận chúng qua `a == b`. Với dữ liệu mô phỏng hoặc cảm biến, ứng dụng cũng có thể muốn **từ chối mọi giá trị không hữu hạn** ngay từ đầu; khi ấy thay chính sách `a == b` bằng kiểm tra `Double.isFinite` trước. Chính sách phải được ghi rõ trong API.

### Phép trừ có thể tràn ra vô cực

Với `a = Double.MAX_VALUE` và `b = -Double.MAX_VALUE`, cả hai là số hữu hạn nhưng `a-b` vượt độ lớn hữu hạn của `double`, nên `difference` thành `+Infinity`. Hàm trả `false`, đúng với các ngưỡng hợp lệ nêu trên (`relTol < 1`, `absTol` hữu hạn). Đây là lý do hàm tránh chia `difference` cho `scale` để lập tỷ số: phép tính trung gian có thể tràn, dẫn đến kết quả khó giải thích.

Dù đã bảo vệ trường hợp này, không nên coi công thức là thuật toán tính khoảng cách chính xác tùy ý ở toàn miền `double`. Nó là một **quy tắc chấp nhận gần bằng nhau** dựa trên số học `double` và dung sai ứng dụng.

## 5. Chọn `absTol` và `relTol` dựa trên dữ liệu

Trước khi quyết định dung sai, cần biết độ lớn điển hình, đơn vị và nguồn sai số.

### 5.1. Sai số tuyệt đối mang đơn vị

Ví dụ hai kết quả tính quãng đường theo mét được coi tương đương nếu chênh nhau không quá `0.001 m`. Khi đó `absTol = 0.001` có căn cứ nghiệp vụ. Nếu đổi kết quả sang milimét, cùng dung sai đó phải đổi thành `1.0 mm`. Không được giữ nguyên trị số `0.001` khi đổi đơn vị.

Với những giá trị cực nhỏ, nếu `absTol` quá lớn thì nhiều giá trị thực sự khác nhau đều bị xem là gần bằng 0. Một cách chọn ngưỡng là dựa vào độ phân giải thiết bị đo, độ chính xác của dữ liệu nguồn hoặc sai số phân tích đã biết.

### 5.2. Sai số tương đối theo quy mô

Nếu kết quả ở thang hàng triệu có thể dao động ở mức vài phần tỷ do thuật toán, một `relTol` được đặt theo mức sai số dự kiến có thể hợp lý hơn ngưỡng tuyệt đối cực nhỏ.

Ví dụ `relTol = 1e-9` cho phép sai lệch khoảng `0.001` ở thang `1e6`. Nhưng điều đó **không** tự chứng minh sai lệch `0.001` chấp nhận được với số lượng tài sản, tiền hoặc ID. Cần dựa vào quy định của miền nghiệp vụ trước khi chọn số.

### 5.3. Ngưỡng chính xác bằng 0

Nếu đặt `absTol = 0.0`, `relTol = 0.0`, hàm ở mục 4 gần như chỉ chấp nhận các cặp **bằng nhau về giá trị số**: nó vẫn cho `+0.0` và `-0.0` bằng nhau, cho vô cực cùng dấu bằng nhau, và từ chối `NaN`. Điều này khác với yêu cầu so sánh cùng **mẫu bit**.

Không nên dùng ngưỡng 0 nếu mục tiêu là bỏ qua sai số làm tròn thông thường.

### 5.4. Không lấy epsilon máy làm ngưỡng tùy ý

`Math.ulp(1.0)` đối với `double` bằng khoảng `2.220446049250313E-16`. Đây là khoảng cách giữa `1.0` và số `double` kế tiếp, không phải một “dung sai chung” hợp lý cho toàn miền.

Một ULP thay đổi theo độ lớn giá trị: `Math.ulp(1e16)` là `2.0`. `Double.MIN_VALUE` lại là số **dương nhỏ nhất khác 0**, không phải sai số máy dùng cho mọi phép so sánh. Khi chọn ngưỡng theo số ULP, cần cân nhắc sự thay đổi độ chính xác theo miền, số dưới chuẩn và nghiệp vụ; cách đó phục vụ mục đích khác với `absTol`/`relTol` thuần túy.

## 6. So sánh với giá trị tham chiếu và so sánh đối xứng

Có hai tình huống khác nhau:

**Một bên là tham chiếu đáng tin hơn.** Ví dụ mô phỏng dùng kết quả độ chính xác cao làm chuẩn `reference` và muốn đánh giá kết quả `actual`. Khi đó tiêu chí:

\[
|\text{actual}-\text{reference}|
\le \max(\text{absTol},\text{relTol}\cdot|\text{reference}|)
\]

có thể phản ánh đúng yêu cầu “sai số tính theo quy mô chuẩn”. Tuy nhiên cần có chính sách rõ cho `reference == 0` và dữ liệu không hữu hạn. Nếu miền giá trị có thể rất lớn và dễ tràn, cần thiết kế cách so sánh phù hợp.

**Hai bên ngang vai trò.** Khi đối chiếu kết quả từ hai triển khai mà không chọn bên nào làm chuẩn, tiêu chí đối xứng với `max(|a|,|b|)` giúp đổi chỗ hai đối số mà không đổi phán đoán.

Cả hai tiêu chí đều có thể chấp nhận một cặp số này nhưng từ chối cặp số khác so với tiêu chí còn lại. Đừng thay mẫu số khi đang triển khai một chuẩn kiểm thử hoặc hợp đồng API cụ thể.

### Quan hệ “gần bằng” không có tính bắc cầu

Với `absTol = 0.1` và `relTol = 0`, hãy xét `a = 0.0`, `b = 0.09`, `c = 0.18`:

- `a` gần `b` vì chênh lệch `0.09 <= 0.1`.
- `b` gần `c` vì chênh lệch `0.09 <= 0.1`.
- `a` **không** gần `c` vì chênh lệch `0.18 > 0.1`.

Vì vậy “approximately equal” **không phải quan hệ tương đương toán học**, cho dù hàm được thiết kế đối xứng và trả `true` với hai số hữu hạn giống nhau. Không nên dùng hàm này làm `equals`/`hashCode`, làm định nghĩa tính duy nhất của `HashSet`/`HashMap`, hay làm `Comparator` để sắp xếp các khóa: các cấu trúc đó đòi hỏi các hợp đồng khác, và độ gần không bắc cầu có thể phá hỏng tính nhất quán.

Nếu bài toán cần nhóm giá trị gần nhau, hãy định nghĩa quy tắc gom cụ thể (ví dụ chia khoảng theo độ phân giải được chỉ định), thay vì coi `isClose` là quan hệ bằng nhau của đối tượng.

## 7. `==`, `Double.compare`, `BigDecimal.compareTo` và so sánh gần đúng

Các phép này có mục đích khác nhau:

| Cách so sánh | Mục tiêu | Đặc điểm cần nhớ |
| --- | --- | --- |
| `a == b` với `double` | Bằng nhau theo toán tử số học Java | `+0.0 == -0.0` là `true`; `NaN == NaN` là `false` |
| `Double.compare(a, b)` | Thứ tự nhất quán để so sánh/sắp xếp `double` theo hợp đồng `Double` | Phân biệt `-0.0` với `+0.0`; coi các `NaN` là bằng nhau trong cách so sánh này |
| `isClose(a, b, absTol, relTol)` | Chấp nhận chênh lệch theo ngưỡng của ứng dụng | Không bắc cầu, không dùng thay `equals`/`Comparator` |
| `BigDecimal.compareTo` | So sánh giá trị decimal của `BigDecimal` | `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` |
| `BigDecimal.equals` | Bằng nhau cả giá trị và `scale` theo hợp đồng `BigDecimal` | `"2.0"` và `"2.00"` không bằng nhau theo `equals` |

Đừng chuyển từ `double` sang `BigDecimal` sau khi một phép tính đã làm mất phần thông tin nguồn rồi kỳ vọng kết quả tự trở nên chính xác. Nếu nghiệp vụ cần số thập phân chính xác (ví dụ tiền), giữ đầu vào từ chuỗi decimal hoặc biểu diễn số nguyên theo đơn vị nhỏ nhất phù hợp.

Cũng không thể suy rằng mọi phép tính `double` đều phải so sánh gần đúng. Kiểm tra sentinel rõ ràng, cờ trạng thái, số nguyên biểu diễn chính xác, hoặc các giá trị mà hợp đồng API yêu cầu chính xác có thể dùng so sánh trực tiếp. Chọn loại so sánh theo **ý nghĩa dữ liệu**.

## 8. Kiểm thử hợp lý cho phép so sánh có dung sai

Một bộ kiểm thử có giá trị nên bao gồm cả các trường hợp dễ bị bỏ qua:

1. **Sai số do biểu diễn:** `0.1 + 0.2` đối chiếu với `0.3`.
2. **Rất gần 0:** `0` so với một lượng nhỏ hơn và lớn hơn `absTol`.
3. **Thang lớn:** chênh lệch nhỏ tương đối nhưng lớn hơn `absTol`.
4. **Ngoài ngưỡng:** cặp chênh lệch lớn hơn cả hai loại dung sai.
5. **Dấu âm:** hai số âm gần nhau, hoặc số âm và dương ở gần 0; dùng `Math.abs` để kiểm tra độ lớn.
6. **Hai số 0 có dấu khác nhau:** chính sách `+0.0`/`-0.0` rõ ràng.
7. **`NaN` và vô cực:** chính sách phải thống nhất với người gọi.
8. **Dữ liệu cực lớn:** tránh phép trừ hoặc phép chia trung gian tạo `Infinity`/`NaN` bất ngờ.
9. **Dung sai không hợp lệ:** giá trị âm, `NaN`, vô cực hoặc `relTol` không thuộc miền cấu hình cho phép.
10. **Bằng đúng ngưỡng:** hiểu tác động của dấu `<` so với `<=` và sai số khi biểu diễn chính ngưỡng.

Để kiểm tra phần cốt lõi của hàm trên, có thể tự thử:

```java
// Các dòng này nằm trong một phương thức Java; ví dụ dùng hàm
// ApproximatelyEqual.isClose được định nghĩa đầy đủ ở mục 4.
boolean nearZero = ApproximatelyEqual.isClose(
        0.0, 1e-10, 1e-9, 1e-9);      // true

boolean farNearZero = ApproximatelyEqual.isClose(
        0.0, 1e-7, 1e-9, 1e-9);       // false

boolean largeClose = ApproximatelyEqual.isClose(
        1e6, 1e6 + 1e-4, 1e-9, 1e-9); // true
```

Với các quy trình khoa học cần đánh giá độ chính xác, nên lưu thêm sai số tuyệt đối, sai số tương đối (khi mẫu số có nghĩa), giá trị tham chiếu, số ULP nếu phù hợp và lý do lựa chọn ngưỡng. Một giá trị boolean `true`/`false` không cung cấp đủ thông tin để chẩn đoán chất lượng thuật toán.

## 9. Những lỗi thường gặp

### Chỉ dùng ngưỡng tuyệt đối cho mọi giá trị

```java
Math.abs(a - b) < 1e-9
```

Đây có thể là quy tắc hợp lý nếu mọi dữ liệu cùng đơn vị và quy mô đã biết. Nhưng khi phải so sánh từ các giá trị gần 0 đến hàng triệu, nó không tự điều chỉnh theo độ lớn. Có thể dùng thêm `relTol` để phản ánh sai số tỷ lệ.

### Chỉ dùng ngưỡng tương đối quanh 0

```java
Math.abs(a - b) <= relTol * Math.max(Math.abs(a), Math.abs(b))
```

Với một bên bằng 0 và bên kia khác 0, nếu `0 <= relTol < 1` thì điều kiện không thể đúng. Điều này có thể quá chặt nếu bài toán chấp nhận chênh lệch tuyệt đối rất nhỏ. Dùng thêm `absTol` khi thực tế cần.

### Chia để tính tỷ lệ mà không xét 0 và overflow

Biểu thức `Math.abs(a-b) / Math.abs(b)` gặp vấn đề với `b = 0`, và có thể tạo vô cực/`NaN` với đầu vào hoặc hiệu đặc biệt. Công thức so sánh bằng ngưỡng nhân với thang độ lớn thường tránh được phép chia trong điều kiện đơn giản, nhưng vẫn phải kiểm tra tính hữu hạn.

### Chấp nhận `NaN` hoặc vô cực ngoài ý muốn

Không dựa vào một biểu thức đại số ngắn để quyết định chính sách. Xử lý riêng `Double.isNaN`, `Double.isFinite`, và vô cực cùng dấu nếu ứng dụng muốn coi chúng bằng nhau.

### Chọn một “EPSILON” cố định vì thấy trong ví dụ

Các giá trị như `1e-6`, `1e-9`, `1e-12` không có giá trị đúng phổ quát. Hãy chọn chúng từ yêu cầu, đơn vị, độ phân giải đầu vào và sai số của thuật toán. Một `absTol` quá lớn sẽ làm hai giá trị khác biệt về nghiệp vụ bị coi như nhau; một `relTol` quá nhỏ làm kiểm thử dễ thất bại vì sai số hợp lệ.

### Dùng so sánh gần đúng cho định danh và cấu trúc dữ liệu

ID, timestamp nguyên, số thứ tự, chỉ số mảng và khóa định danh cần tiêu chí chính xác. Nếu hai ID khác nhau một đơn vị, việc dùng `relTol` có thể khiến chúng bị coi là “bằng nhau” khi độ lớn lớn, gây hỏng logic.

### Quên rằng sai số đã xảy ra trước khi so sánh

Nếu hai số nguyên lớn khác nhau đã cùng bị làm tròn thành một `double`, cả `==` và `isClose` đều có thể trả `true`; không cách so sánh nào phục hồi nguồn đã mất. Khi cần phân biệt số nguyên liên tiếp lớn, giữ chúng dưới dạng `long` hoặc `BigInteger`.

### Nhầm sự gần nhau với tính đúng của thuật toán

Một kết quả có thể nằm trong dung sai mà vẫn sai logic. Kiểm thử số học cần kiểm tra cả invariant, miền giá trị, nhánh điều kiện và so sánh với kết quả đáng tin, chứ không chỉ nới ngưỡng đến khi mọi test qua.

## 10. Bài tập tự kiểm tra

**Câu 1.** Với `absTol = 1e-8`, `relTol = 1e-6`, hai giá trị `a = 0` và `b = 5e-9` có đạt điều kiện dạng `max` không? Còn `b = 5e-7`?

**Đáp án:** `5e-9` đạt vì nhỏ hơn ngưỡng tuyệt đối `1e-8`. `5e-7` không đạt: ngưỡng tương đối chỉ `1e-6 × 5e-7 = 5e-13`, còn ngưỡng tuyệt đối là `1e-8`.

**Câu 2.** Với `absTol = 1e-8`, `relTol = 1e-6`, cặp `a = 1_000_000` và `b = 1_000_000.5` có gần nhau không?

**Đáp án:** Có. Sai lệch tuyệt đối là `0.5`, còn ngưỡng tương đối khoảng `1.0000005`, lớn hơn `0.5`.

**Câu 3.** Tại sao cần một nhánh riêng cho vô cực cùng dấu trong hàm so sánh gần đúng?

**Đáp án:** `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` là `true`, nhưng `Infinity - Infinity` cho `NaN`; nếu chỉ dùng `Math.abs(a-b) <= limit` thì kết quả sai với chính sách coi hai vô cực cùng dấu bằng nhau.

**Câu 4.** Có thể dùng `isClose` làm logic `equals` cho khóa `HashMap` không?

**Đáp án:** Không. Quan hệ gần bằng có thể không bắc cầu; nó không đáp ứng hợp đồng bằng nhau cần thiết để định nghĩa khóa một cách nhất quán. Dùng giá trị/đại diện chuẩn hóa và `equals`/`hashCode` tương ứng với chính sách định danh.

**Câu 5.** Khi nào nên dùng dung sai dựa vào `reference` thay vì `max(|a|, |b|)`?

**Đáp án:** Khi một bên là chuẩn có ý nghĩa độc lập và yêu cầu sai số được xác định theo tỷ lệ của giá trị chuẩn. Phải quy định cách xử lý `reference = 0`; nếu hai bên ngang vai trò, công thức đối xứng dễ giải thích hơn.

**Câu 6.** Phép so sánh gần đúng có thể chứng minh `0.1 + 0.2` được tính chính xác về mặt toán học không?

**Đáp án:** Không. Nó chỉ đánh giá chênh lệch nằm trong dung sai đặt ra. Các giá trị nhị phân vẫn đã làm tròn; để yêu cầu chữ số thập phân chính xác theo nguồn, cần biểu diễn và quy tắc tính thích hợp như `BigDecimal` từ chuỗi decimal.

**Ghi nhớ:** Sai số tuyệt đối trả lời *“lệch bao nhiêu theo đơn vị dữ liệu?”*; sai số tương đối trả lời *“lệch bao nhiêu so với quy mô?”*. Kết hợp bằng `|a-b| <= max(absTol, relTol × max(|a|,|b|))` thường phù hợp khi dữ liệu trải qua nhiều thang đo, nhưng ngưỡng và chính sách `NaN`/vô cực vẫn phải do bài toán quyết định. Phép so sánh gần đúng là quy tắc chấp nhận kết quả, không thay thế giá trị chính xác, hợp đồng `equals`, hay phân tích sai số thuật toán.