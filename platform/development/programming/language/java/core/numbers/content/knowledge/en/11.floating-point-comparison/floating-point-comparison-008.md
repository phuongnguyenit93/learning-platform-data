# So sánh bằng sai số tương đối trong Java

## 1. Vì sao so sánh `double` bằng `==` thường chưa đủ?

Với số nguyên, phép so sánh `==` thường là lựa chọn thích hợp để kiểm tra hai giá trị có bằng nhau không. Với `float` và `double`, kết quả của phép toán dấu phẩy động có thể **khác đôi chút so với giá trị lý tưởng** vì chỉ một số hữu hạn các giá trị nhị phân có thể biểu diễn được. Ví dụ:

~~~java
double computed = 0.1 + 0.2;
double expected = 0.3;

System.out.println(computed);            // 0.30000000000000004
System.out.println(computed == expected); // false
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. Phép `==` **không sai**: nó trả lời câu hỏi hai giá trị `double` hiện có bằng nhau theo quy tắc so sánh dấu phẩy động hay không. Vấn đề là nhiều bài toán thực tế muốn trả lời **“hai kết quả có đủ gần nhau trong mức sai số chấp nhận được không?”**.

Một cách định lượng mức gần nhau là **sai số tương đối** (*relative error/tolerance*), dùng tỷ lệ chênh lệch so với độ lớn của giá trị được so sánh. Nó đặc biệt hữu ích khi các đại lượng thay đổi theo nhiều bậc độ lớn.

Ví dụ:

- Độ chênh lệch **1** giữa 1.000.000 và 1.000.001 chỉ khoảng **0,0001%**.
- Độ chênh lệch **1** giữa 1 và 2 lại lên tới **50% hoặc 100%**, tùy chọn mốc tham chiếu.

Cùng một sai số tuyệt đối `1` không mang cùng ý nghĩa khi thang giá trị thay đổi lớn. Đó là lý do dùng sai số tương đối.

**Lưu ý phạm vi:** bài này giải thích cách so sánh **gần bằng** về mặt số học. Nó không thay đổi quy tắc của `==`, không làm cho phép toán `double` trở thành chính xác tuyệt đối và không thay thế tiêu chuẩn sai số cụ thể của từng lĩnh vực.

## 2. Sai số tuyệt đối và sai số tương đối

### Sai số tuyệt đối

Với hai giá trị hữu hạn `a` và `b`, sai số tuyệt đối thường được định nghĩa:

\[
E_{\mathrm{abs}} = |a-b|
\]

Nếu `a=1000000.0` và `b=1000000.5`, sai số tuyệt đối là `0.5`. Một phép kiểm tra gần bằng theo ngưỡng tuyệt đối là:

~~~java
Math.abs(a - b) <= absoluteTolerance
~~~

Đoạn trên chỉ là biểu thức minh họa. Nó phù hợp khi bài toán đặt sai số theo **đơn vị cụ thể**: chẳng hạn sai số đo không quá 0,001 mét.

Nhưng nếu `a` và `b` đôi lúc ở cỡ `1e-12`, đôi lúc ở cỡ `1e12`, một ngưỡng tuyệt đối chung có thể quá rộng ở thang nhỏ và quá khắt khe ở thang lớn.

### Sai số tương đối theo mốc tham chiếu

Nếu `reference` là một giá trị chuẩn **khác 0**, sai số tương đối có thể định nghĩa:

\[
E_{\mathrm{rel,ref}} =
\frac{|observed-reference|}{|reference|}
\]

Đây là định nghĩa hợp lý trong phép đo: mẫu số là độ lớn của **giá trị chuẩn**. Ví dụ, sai số `0.5` trên mốc `1_000_000` bằng `0.0000005`, tức `0.00005%`. Với ngưỡng `relativeTolerance = 1e-6` (một phần triệu), hai số được coi là đủ gần nhau.

**Mẫu số `reference == 0` khiến công thức không xác định.** Không được lặng lẽ thay mẫu số 0 bằng một số tùy tiện mà không mô tả chính sách của bài toán.

### Sai số tương đối đối xứng

Nếu không có giá trị nào được ưu tiên là “chuẩn”, có thể chọn thang đo đối xứng:

\[
scale = \max(|a|,|b|)
\]

\[
E_{\mathrm{rel,sym}} =
\frac{|a-b|}{\max(|a|,|b|)}
\quad \text{(khi }scale>0\text{)}
\]

Bài này sẽ dùng biến thể **đối xứng theo `max(|a|, |b|)`** trong ví dụ chính. Đổi chỗ `a` và `b` không thay đổi kết quả. Công thức không phải định nghĩa duy nhất của “relative error”: một số tài liệu dùng `|reference|`, trung bình độ lớn hoặc một thang vật lý xác định trước. Cần thống nhất **mẫu số** khi thiết kế API và viết test.

### Phần trăm và ngưỡng

| Giá trị ngưỡng `relTol` | Tương đương tỷ lệ | Ý nghĩa |
|---:|---:|---|
| `1e-2` | `1%` | Cho phép chênh lệch khoảng một phần trăm của thang đo |
| `1e-3` | `0.1%` | Khoảng một phần nghìn |
| `1e-6` | `0.0001%` | Khoảng một phần triệu |
| `1e-9` | `0.0000001%` | Khoảng một phần tỷ |

Ngưỡng là **chính sách của ứng dụng**, không phải một con số Java “đúng cho mọi `double`”. Độ chính xác của dữ liệu đầu vào, thuật toán, số phép tính, đơn vị đo và hậu quả của kết luận sai đều ảnh hưởng đến ngưỡng thích hợp.

## 3. Công thức so sánh tương đối và hai điểm phải xử lý

Một phép kiểm tra lý tưởng thường được viết:

\[
|a-b| \le relTol\cdot\max(|a|,|b|)
\]

hoặc chia hai vế cho `scale` dương:

\[
\frac{|a-b|}{scale} \le relTol
\]

Giả sử `relTol` nằm trong `[0, 1)` để có ý nghĩa “hai số phải thật sự gần nhau”, khi cả hai số hữu hạn.

**Nhưng đừng sao chép công thức trực tiếp mà bỏ qua các trường hợp biên**:

1. **Cả hai bằng 0:** `scale == 0`, phép chia tạo biểu thức `0.0 / 0.0` là `NaN`; nếu không xử lý trước, phép so sánh sẽ trả `false` dù hai số bằng nhau.
2. **Hai số hữu hạn rất lớn và trái dấu:** `a-b` có thể tràn thành `Infinity`, dù `a` và `b` riêng lẻ đều hữu hạn. Khi `relTol < 1`, hai số trái dấu không thể đủ gần theo quy tắc tương đối thuần túy (ngoại trừ cùng bằng 0 đã được xử lý).
3. **`NaN` hoặc vô cực:** phải quyết định rõ cách diễn giải gần bằng; áp dụng phép chia công thức một cách máy móc có thể trả `NaN` hoặc giá trị không hữu ích.
4. **Số gần 0:** một giá trị 0 và một giá trị dương rất nhỏ có sai số tương đối đối xứng bằng `1`, **không** được coi là gần nhau nếu `relTol < 1`. Bài toán có thể cần **ngưỡng tuyệt đối** riêng ở gần 0.

Việc thêm các điều kiện này giúp ví dụ chạy ổn định trên miền `double` của Java.

## 4. Triển khai so sánh **tương đối thuần túy** trong Java 17+

Tạo tệp `RelativeErrorDemo.java`:

~~~java
public class RelativeErrorDemo {
    /**
     * Gần bằng theo tỷ lệ đối xứng max(abs(a), abs(b)).
     * Chính sách: NaN khác mọi giá trị; vô cực bằng chính cùng dấu.
     * Ngưỡng phải hữu hạn và nằm trong [0, 1).
     */
    static boolean nearlyEqualRelative(double a, double b, double relTol) {
        if (!Double.isFinite(relTol) || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid relative tolerance");
        }

        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true; // gồm +0.0/-0.0 và vô cực cùng dấu
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        // Với relTol < 1, hai số khác dấu hoặc một số là 0
        // không thể đạt điều kiện sai số tương đối thuần túy.
        if (a == 0.0 || b == 0.0 || ((a < 0.0) != (b < 0.0))) {
            return false;
        }

        // Hai số hữu hạn cùng dấu: phép trừ không tràn vô cực.
        double scale = Math.max(Math.abs(a), Math.abs(b));
        double relativeError = Math.abs(a - b) / scale;
        return relativeError <= relTol;
    }

    public static void main(String[] args) {
        System.out.println("largeLoose="
                + nearlyEqualRelative(1_000_000.0, 1_000_000.5, 1e-6));
        System.out.println("largeTight="
                + nearlyEqualRelative(1_000_000.0, 1_000_000.5, 1e-7));
        System.out.println("tiny="
                + nearlyEqualRelative(1e-12, 1.01e-12, 0.02));
        System.out.println("zeroVsTiny="
                + nearlyEqualRelative(0.0, 1e-12, 0.02));
        System.out.println("signedZero="
                + nearlyEqualRelative(0.0, -0.0, 0.0));
        System.out.println("oppositeLarge="
                + nearlyEqualRelative(
                        Double.MAX_VALUE, -Double.MAX_VALUE, 0.5));
        System.out.println("sameInfinity="
                + nearlyEqualRelative(
                        Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-6));
        System.out.println("notANumber="
                + nearlyEqualRelative(Double.NaN, Double.NaN, 1e-6));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RelativeErrorDemo.java
java RelativeErrorDemo
~~~

Đầu ra chính xác:

~~~text
largeLoose=true
largeTight=false
tiny=true
zeroVsTiny=false
signedZero=true
oppositeLarge=false
sameInfinity=true
notANumber=false
~~~

**Đọc kết quả:**

- `1_000_000.0` và `1_000_000.5` chỉ lệch xấp xỉ `5e-7` tương đối nên lọt ngưỡng `1e-6` nhưng không lọt `1e-7`.
- `1e-12` và `1.01e-12` lệch khoảng 1%, nên lọt ngưỡng 2% dù hiệu tuyệt đối chỉ khoảng `1e-14`.
- `0` và `1e-12` có tỷ lệ lệch bằng 100% theo mẫu số `max`, nên không được coi là gần nếu chỉ dùng tương đối với ngưỡng dưới 1.
- `+0.0` và `-0.0` so sánh `==` là `true`, nên được chấp nhận trước khi tính tỷ lệ.
- Chính sách ở đây coi hai vô cực **cùng dấu** là bằng nhau, vô cực khác dấu hoặc so với số hữu hạn là không gần; `NaN` luôn trả `false`.

Trong thực tế, một hệ thống có thể yêu cầu **từ chối mọi `NaN`/`Infinity`** thay vì cho phép vô cực cùng dấu. Nếu vậy, hãy kiểm tra `Double.isFinite(a) && Double.isFinite(b)` *trước* câu `a == b` và trả lỗi hoặc `false` theo hợp đồng API. Điều quan trọng là chính sách phải **được ghi rõ và kiểm thử**.

## 5. Vì sao phải kết hợp sai số tuyệt đối khi gần 0?

Một ví dụ rất thường gặp: thuật toán toán học kỳ vọng kết quả `0.0`, nhưng tính toán thực tế cho `1e-12`. Với sai số tương đối đối xứng:

\[
\frac{|0 - 10^{-12}|}{\max(0, 10^{-12})} = 1
\]

Ngưỡng `relTol = 1e-6` không chấp nhận khác biệt này, dù `1e-12` có thể hoàn toàn nằm trong sai số đo hoặc giới hạn số học hợp lý của bài toán.

Cách thường dùng là **kết hợp điều kiện tuyệt đối hoặc điều kiện tương đối**:

\[
\operatorname{near}(a,b) =
(|a-b| \le absTol)
\;\lor\;
\left(
\frac{|a-b|}{\max(|a|,|b|)} \le relTol
\right)
\]

trong đó trường hợp `scale == 0` và các giá trị đặc biệt được xử lý riêng.

Cũng có thể viết dưới dạng `|a-b| <= max(absTol, relTol*scale)` trên các giá trị hữu hạn thông thường, nhưng **không nên nhân/chênh lệch một cách không kiểm soát** khi làm việc gần giới hạn `double`. Cách kiểm tra hai nhánh riêng giúp tránh nhân `relTol * scale` và cho phép kiểm tra trước khi tính tỷ lệ.

Hai tham số có **vai trò khác nhau**:

| Tham số | Đơn vị | Dùng khi nào |
|---|---|---|
| `absTol` | Cùng đơn vị với `a` và `b` | Cho phép sai số nhỏ gần số 0 |
| `relTol` | Không thứ nguyên | Cho phép sai số tỷ lệ theo độ lớn giá trị |
 
Ví dụ, nếu dữ liệu là mét, `absTol = 1e-9` có nghĩa dung sai tuyệt đối 1 nanomét; `relTol = 1e-6` là dung sai một phần triệu tương đối. **Không được lấy ngưỡng chỉ vì thấy nó phổ biến**; hãy chọn theo độ chính xác đo và hậu quả khi chấp nhận nhầm.

## 6. Triển khai kết hợp tuyệt đối/tương đối an toàn với số hữu hạn

Tạo tệp `HybridToleranceDemo.java`:

~~~java
public class HybridToleranceDemo {
    /**
     * Chính sách: chấp nhận nếu sai số tuyệt đối HOẶC tương đối đủ nhỏ.
     * Cho phép hai vô cực cùng dấu bằng nhau, NaN luôn khác.
     */
    static boolean nearlyEqual(double a, double b,
                               double absTol, double relTol) {
        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid tolerance");
        }

        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }

        // Có thể thành Infinity nếu a và b cực lớn, trái dấu.
        double diff = Math.abs(a - b);
        if (diff <= absTol) {
            return true;
        }

        // Nếu cả hai hữu hạn, khác dấu hoặc có một số bằng 0,
        // sai số tương đối >= 1. absTol đã được thử ở trên.
        if (a == 0.0 || b == 0.0 || ((a < 0.0) != (b < 0.0))) {
            return false;
        }

        double scale = Math.max(Math.abs(a), Math.abs(b));
        return diff / scale <= relTol;
    }

    public static void main(String[] args) {
        double absTol = 1e-10;
        double relTol = 1e-6;

        System.out.println("nearZero="
                + nearlyEqual(0.0, 1e-12, absTol, relTol));
        System.out.println("largeClose="
                + nearlyEqual(1_000_000.0, 1_000_000.5,
                        absTol, relTol));
        System.out.println("largeFar="
                + nearlyEqual(1_000_000.0, 1_000_002.0,
                        absTol, relTol));
        System.out.println("oppositeSmall="
                + nearlyEqual(1e-12, -1e-12, absTol, relTol));
        System.out.println("oppositeLarge="
                + nearlyEqual(Double.MAX_VALUE,
                        -Double.MAX_VALUE, absTol, relTol));
        System.out.println("exactZero="
                + nearlyEqual(0.0, -0.0, 0.0, 0.0));
        System.out.println("notFinite="
                + nearlyEqual(Double.NaN, 1.0, absTol, relTol));
    }
}
~~~

~~~bash
javac HybridToleranceDemo.java
java HybridToleranceDemo
~~~

Đầu ra:

~~~text
nearZero=true
largeClose=true
largeFar=false
oppositeSmall=true
oppositeLarge=false
exactZero=true
notFinite=false
~~~

**Giải thích điều kiện đối với dấu:** Khi `a` và `b` hữu hạn, khác 0 và trái dấu, `|a-b| >= max(|a|,|b|)`. Do đó tỷ số tương đối không nhỏ hơn 1, không thể thỏa `relTol < 1`. Trường hợp này chỉ có thể được chấp nhận nhờ **`absTol`** nếu cả hai nằm rất gần 0. Bằng việc kiểm tra `absTol` trước, hàm vẫn có thể chấp nhận `1e-12` và `-1e-12` mà không cần đánh đồng hai số khác dấu ở quy mô lớn.

**Vì sao không tính `diff / scale` ngay từ đầu?** Nếu `a == b == 0.0`, `scale` bằng 0 và biểu thức `0.0 / 0.0` thành `NaN`. Nếu hai giá trị khác dấu cực lớn, `a-b` có thể thành `Infinity`; nhánh kiểm tra dấu tránh dựa vào tỷ lệ không cần thiết. Với hai số hữu hạn cùng dấu, độ lớn chênh lệch không vượt số có độ lớn lớn hơn và phép trừ không gây overflow về vô cực.

## 7. Ba lựa chọn mẫu số và khi nào dùng

Không có một công thức tương đối độc quyền:

### 7.1. Dựa trên giá trị chuẩn

\[
\frac{|measured-reference|}{|reference|} \le relTol
\]

Phù hợp khi có **reference khác 0** mang ý nghĩa vật lý hoặc nghiệp vụ: một mục tiêu sản lượng, một giá trị đo chuẩn, kết quả tham chiếu có độ chính xác cao. Nhưng đảo thứ tự `measured` và `reference` thay đổi mẫu số, do đó có thể thay đổi kết luận.

Ví dụ, lấy `reference = 100`, `measured = 101` thì sai số tham chiếu bằng 1%; nếu lấy `reference = 101`, `measured = 100` thì sai số bằng khoảng 0,9901%.

### 7.2. Đối xứng theo độ lớn lớn nhất

\[
\frac{|a-b|}{\max(|a|,|b|)} \le relTol
\]

Phù hợp khi không có tham chiếu ưu tiên, ví dụ kiểm tra hai kết quả tính độc lập có gần nhau không. Đây là cách chọn trong hai chương trình Java trên.

### 7.3. Dựa trên thang đo định sẵn

Một phép so sánh có thể sử dụng mẫu số `scale` theo chuẩn ngành (kích thước thiết bị, miền chuẩn hóa, định mức) thay vì chọn từ hai giá trị. Cách này hữu ích khi **gần 0** nhưng bài toán vẫn có một thang đo tự nhiên.

**Quan trọng:** lựa chọn mẫu số phải dựa trên ý nghĩa dữ liệu. Đừng gọi ba công thức là hoàn toàn tương đương, và đừng đưa ra ngưỡng `relTol` mà không nêu mẫu số.

## 8. `float` so với `double` và ý nghĩa của epsilon

`float` có khoảng 24 bit độ chính xác phần định trị nhị phân, `double` có 53 bit. Một phép đo hoặc thuật toán ở kiểu `float` thường tạo sai số tương đối làm tròn lớn hơn trường hợp tương ứng ở `double`, nhưng **không có quy luật rằng cứ dùng `double` thì ngưỡng `1e-12` luôn phù hợp**.

Các hằng:

- `Math.ulp(1.0f)` là khoảng cách tới giá trị `float` liền trên ở `1.0f`, xấp xỉ `1.1920929e-7`.
- `Math.ulp(1.0)` là khoảng cách tới giá trị `double` liền trên ở `1.0`, xấp xỉ `2.220446049250313e-16`.

Đây là thông tin về **độ phân giải biểu diễn tại một thang cụ thể**, không phải lời hứa mọi phép tính đều có sai số không vượt một ULP. Sai số có thể tích lũy qua nhiều bước, phát sinh từ mô hình dữ liệu đầu vào, hoặc do thuật toán không ổn định.

### Một số tên thường bị hiểu nhầm

- `Double.MIN_VALUE` là số dương subnormal nhỏ nhất lớn hơn 0 của kiểu `double`, **không phải epsilon để so sánh gần bằng**.
- `Float.MIN_VALUE` cũng là số dương subnormal nhỏ nhất lớn hơn 0, không phải ngưỡng tương đối phổ quát.
- Java không có một hằng `Double.EPSILON` tiêu chuẩn trong `java.lang.Double` để tự động giải quyết mọi phép so sánh gần bằng. `Math.ulp(1.0)` thường dùng để minh họa độ phân giải gần 1, nhưng **ngưỡng so sánh vẫn phải đến từ yêu cầu bài toán**.

Nếu cần kiểm tra **sự trùng khớp chính xác theo bit**, hoặc dùng số làm khóa định danh, tuyệt đối không đánh tráo yêu cầu đó bằng một phép so sánh có dung sai.

## 9. Các bẫy thường gặp: overflow, underflow, NaN và vô cực

### 9.1. Chênh lệch của hai số hữu hạn có thể overflow

~~~java
double a = Double.MAX_VALUE;
double b = -Double.MAX_VALUE;
double difference = Math.abs(a - b); // Infinity
~~~

Đây là đoạn minh họa. Cả `a` và `b` hữu hạn, nhưng chênh lệch toán học vượt miền số hữu hạn `double`, vì thế `difference` thành `Infinity`. Nếu sau đó tùy tiện tính `difference / Math.max(Math.abs(a), Math.abs(b))`, tỷ số trở thành `Infinity`, không phải sai số tương đối hữu hạn dự kiến khoảng 2. Dù hai số không nên được coi là “gần nhau”, phép chia đơn giản này cho thấy **công thức viết thẳng có thể đánh mất thông tin tại biên**.

Với ngưỡng `relTol < 1`, chỉ cần loại trường hợp trái dấu (sau kiểm tra tuyệt đối trong phiên bản hybrid). Điều đó tránh phải tính tỷ lệ ở vùng overflow của hiệu. Nếu bài toán đòi **tính chính xác trị số tỷ lệ tới ngưỡng lớn hơn hoặc bằng 1**, cần một thuật toán khác có xử lý thang giá trị, không được tái sử dụng hàm được thiết kế cho `relTol < 1`.

### 9.2. Dưới mức biểu diễn và trường hợp `scale` quá nhỏ

Gần 0, giá trị `double` có thể thuộc miền **subnormal**, và số học có thể bị underflow. Sai số tương đối lúc đó có thể rất nhạy với lượng thay đổi một ULP; phép so sánh có `absTol` mang ý nghĩa đo đạc thường hữu ích hơn.

Tuy nhiên, `absTol` quá lớn so với ý nghĩa nghiệp vụ cũng gây **false positive**: hai số khác nhau đáng kể theo tỷ lệ lại bị xem là gần nhau chỉ vì chúng đều nhỏ. Vì vậy, không được chọn `absTol` một cách máy móc theo “một số bé”.

### 9.3. `NaN` và `Infinity` không phải số hữu hạn bình thường

Trong Java:

- `Double.NaN == Double.NaN` là `false`.
- `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` là `true`.
- `Double.isNaN(a)` hoặc `Double.isFinite(a)` cung cấp kiểm tra rõ ràng.
- Nếu chỉ một toán hạng là vô cực và toán hạng kia hữu hạn, phép gần bằng được định nghĩa trong hai ví dụ là `false`.

**Chính sách của hai ví dụ**: NaN không bao giờ gần bằng; vô cực chỉ gần bằng chính vô cực cùng dấu. Một thư viện kiểm tra dữ liệu đầu vào có thể chọn **bác bỏ mọi giá trị không hữu hạn** ngay từ đầu để kết luận có ý nghĩa theo số đo. Không có một chính sách ngoại lệ duy nhất cho mọi ứng dụng.

### 9.4. `-0.0` và `+0.0`

`-0.0 == 0.0` cho `true` mặc dù biểu diễn bit và dấu khi chia cho 0 có thể khác. Hai hàm mẫu chấp nhận chúng là bằng nhau, giống ngữ nghĩa `==`. Nếu ứng dụng cần phân biệt bit dấu của số 0, phải dùng kiểm tra khác phù hợp, chứ không dùng phép gần bằng.

## 10. Ví dụ kiểm tra lỗi do chọn ngưỡng tuyệt đối cố định

Một sai lầm phổ biến là dùng mỗi điều kiện:

~~~java
Math.abs(a - b) < 1e-6
~~~

Thử ở hai thang khác nhau:

- `a = 1e-12`, `b = 2e-12`: hiệu chỉ `1e-12`, nên ngưỡng `1e-6` chấp nhận, dù hai số lệch **50% theo mẫu số max**.
- `a = 1_000_000`, `b = 1_000_000.5`: hiệu `0.5`, nên ngưỡng `1e-6` loại, dù lệch **khoảng 0,00005%**.

Tạo tệp `AbsoluteVsRelativeDemo.java`:

~~~java
public class AbsoluteVsRelativeDemo {
    static boolean absoluteClose(double a, double b, double absTol) {
        return Math.abs(a - b) <= absTol;
    }

    static boolean relativeClose(double a, double b, double relTol) {
        if (a == b) {
            return true;
        }
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return Math.abs(a - b) / scale <= relTol;
    }

    public static void main(String[] args) {
        System.out.println("tinyAbs="
                + absoluteClose(1e-12, 2e-12, 1e-6));
        System.out.println("tinyRel="
                + relativeClose(1e-12, 2e-12, 1e-6));
        System.out.println("largeAbs="
                + absoluteClose(1_000_000, 1_000_000.5, 1e-6));
        System.out.println("largeRel="
                + relativeClose(1_000_000, 1_000_000.5, 1e-6));
    }
}
~~~

~~~bash
javac AbsoluteVsRelativeDemo.java
java AbsoluteVsRelativeDemo
~~~

Đầu ra:

~~~text
tinyAbs=true
tinyRel=false
largeAbs=false
largeRel=true
~~~

**Giới hạn của ví dụ phụ:** `relativeClose` trong class này **chỉ để minh họa so sánh ở hai cặp hữu hạn khác 0 cùng dấu được gọi từ `main`**. Nó không phải hàm thư viện an toàn cho mọi đầu vào, vì thiếu xử lý `NaN`/vô cực, `scale == 0` và overflow của hiệu. Trong mã ứng dụng, hãy dùng triển khai kiểm tra đầy đủ tại phần 4 hoặc phần 6, hoặc áp dụng chính sách đặc thù có kiểm thử.

## 11. Gần bằng không phải quan hệ tương đương

Một điểm dễ bị bỏ qua là phép “gần bằng” với dung sai dương thường **không có tính bắc cầu** (*transitive*):

- Có thể `near(a, b) == true`.
- Có thể `near(b, c) == true`.
- Nhưng `near(a, c) == false`.

Ví dụ, dùng ngưỡng tuyệt đối `0.1`: `a=0.0`, `b=0.09`, `c=0.18`. Hai cặp kề có hiệu 0.09, còn `a` và `c` cách nhau 0.18. Với dung sai tương đối, tính không bắc cầu cũng xảy ra ở các giá trị dương gần nhau.

**Hệ quả thiết kế:** Không dùng `nearlyEqual` như thể nó là `Object.equals`, hoặc trực tiếp thay đổi `equals`/`hashCode` của các khóa `HashMap`/`HashSet`. Các cấu trúc tập hợp thường đòi quan hệ tương đương ổn định; dùng gần bằng có thể tạo hành vi trái mong đợi trong phân nhóm, tra cứu, sắp xếp.

Nếu cần phân cụm giá trị gần nhau, phải xác định thuật toán phân cụm hoặc **lượng tử hóa** (*quantization*) với quy tắc biên rõ ràng, thay vì giả định phép gần bằng bắc cầu. Nếu cần so sánh định danh hoặc kết quả chính xác, dùng kiểu số/chính sách chính xác phù hợp.

## 12. Không phải bài toán nào cũng nên dùng dung sai tương đối

| Bài toán | Cách tiếp cận đáng cân nhắc |
|---|---|
| So sánh hai kết quả số học/đo đạc có thang dao động lớn | Sai số tương đối đối xứng, hoặc kết hợp với tuyệt đối |
| So sánh với **giá trị chuẩn** khác 0 | Sai số tương đối theo `reference` |
| So sánh số gần 0 với sai số đo có đơn vị rõ ràng | Ngưỡng tuyệt đối theo đơn vị vật lý |
| Kiểm tra sự bằng nhau chính xác của số lượng nguyên | `==` trên `int`/`long` hoặc kiểu số nguyên chính xác |
| So sánh dữ liệu tiền thập phân chính xác | `BigDecimal` và chính sách scale/rounding, không dùng sai số `double` tùy ý |
| So sánh bit biểu diễn của số thực | Kiểm tra bit phù hợp, không dùng phép gần bằng |
| Xác định thứ tự sắp xếp | Comparator có thứ tự nhất quán; tránh “bằng nhau gần đúng” không bắc cầu |

Các dung sai mặc định “luôn là `1e-6`” hoặc “luôn là `Double.MIN_VALUE`” là dấu hiệu phải xem lại yêu cầu độ chính xác thực tế.

## 13. Những nhầm lẫn phổ biến

1. **“Sai số tương đối là `Math.abs(a-b)`.”** Không: đó là sai số **tuyệt đối**. Sai số tương đối phải so với một thang đo được xác định.
2. **“`Math.abs(a-b) / Math.abs(b)` luôn an toàn.”** Không: `b` có thể bằng 0, gần 0, hoặc `a-b` overflow; đồng thời mẫu số dựa vào `b` không đối xứng.
3. **“Hai số gần 0 thì ngưỡng tương đối nhỏ chắc chắn chấp nhận.”** Không: `0` so với `1e-12` có sai số tương đối đối xứng bằng 1.
4. **“Ngưỡng `1e-12` là chính xác cho mọi `double`.”** Không: phải chọn theo thang dữ liệu, phép toán, số bước tính và mục tiêu nghiệp vụ.
5. **“`Double.MIN_VALUE` chính là epsilon của `double`.”** Không: nó là số dương subnormal nhỏ nhất, không phải ngưỡng sai số tương đối tổng quát.
6. **“Nếu chênh lệch hữu hạn thì phép `a-b` luôn hữu hạn.”** Không: hai số lớn trái dấu có thể làm chênh lệch overflow tới vô cực.
7. **“`NaN` có thể được xử lý giống số hữu hạn.”** Không: phải có chính sách riêng; `NaN == NaN` là `false`.
8. **“Hai số rất gần thì có thể làm khóa bằng nhau trong mọi `HashMap`.”** Không: gần bằng với ngưỡng dương không nhất thiết bắc cầu.
9. **“Chỉ cần phần trăm sai số, không cần chọn mẫu số.”** Không: mẫu số là phần của định nghĩa bài toán; `reference`, `max` và thang chuẩn cố định có thể cho kết quả khác nhau.
10. **“Tăng `relTol` tới 100% chắc chắn không có vấn đề.”** Một ngưỡng quá rộng làm mất ý nghĩa “gần”; các hàm mẫu cố tình giới hạn `relTol < 1` và yêu cầu chính sách khác nếu cần miền rộng hơn.

## 14. Checklist xây dựng phép so sánh gần bằng

1. **Xác định dữ liệu:** đại lượng đo, kết quả mô phỏng, giá tiền, tỉ lệ hay mã định danh?
2. **Chọn định nghĩa sai số:** theo giá trị chuẩn, theo `max(|a|, |b|)` hay một thang cố định có ý nghĩa.
3. **Đặt `relTol` theo yêu cầu**, không dựa trên một hằng mặc định chưa được giải thích.
4. **Xử lý gần 0:** nếu cần, đặt `absTol` theo đơn vị và độ phân giải của dữ liệu.
5. **Kiểm tra đầu vào đặc biệt:** `NaN`, vô cực, số 0 có dấu; xác định chúng bị từ chối hay so sánh bằng quy tắc riêng.
6. **Tránh overflow trung gian** khi số hữu hạn nhưng rất lớn/trái dấu.
7. **Không nhầm “gần bằng” với “bằng chính xác”.** Đặc biệt khi làm khóa, nhóm, sắp xếp và xác thực dữ liệu.
8. **Viết test biên:** cùng số, hai số lân cận, ở trên/dưới ngưỡng, gần 0, khác dấu, số cực đại, vô cực, NaN, ngưỡng âm/NaN.
9. **Ghi rõ API trả `boolean` hay ném exception** khi ngưỡng không hợp lệ; ví dụ mẫu ném `IllegalArgumentException`.
10. **Đánh giá sai số nguồn**: nếu cảm biến sai tới 1%, ngưỡng `1e-12` không phản ánh độ chắc chắn của dữ liệu cho dù dùng `double`.

## 15. Tự kiểm tra

1. Sai số tuyệt đối khác sai số tương đối ra sao? Đơn vị của mỗi loại?
2. Vì sao `a=1e-12` và `b=2e-12` có sai số tuyệt đối rất nhỏ nhưng sai số tương đối đối xứng lớn?
3. Sai số tương đối theo `reference` có giữ nguyên khi đổi chỗ hai số không?
4. Tại sao `0.0` với `1e-12` không gần nhau theo `relTol=1e-6` thuần túy, nhưng có thể gần nhau theo `absTol=1e-10`?
5. Vì sao nên xử lý `a == b` trước khi chia cho `max(|a|,|b|)`?
6. Nếu một số là `Double.NaN`, có nên dùng trực tiếp phép `==` hoặc phép chia để kết luận gần bằng?
7. Hai số hữu hạn `Double.MAX_VALUE` và `-Double.MAX_VALUE` có hiệu `a-b` kiểu `double` ra sao?
8. Khi nào nên chọn `BigDecimal` thay vì so sánh `double` bằng dung sai?
9. Tại sao phép gần bằng không thích hợp để thay thế `equals`/`hashCode`?
10. Nếu hai phép đo có cùng đơn vị nhưng thay đổi từ `1e-9` tới `1e9`, tại sao ngưỡng tuyệt đối đơn độc thường không đủ?

**Gợi ý đáp án:** (1) Tuyệt đối là độ lệch cùng đơn vị, tương đối là tỷ lệ không thứ nguyên. (2) Chênh lệch bằng nửa giá trị lớn hơn nên tỷ lệ `0.5`. (3) Không, vì đổi giá trị chuẩn làm đổi mẫu số. (4) Relative error bằng 1, còn absolute difference bằng `1e-12`. (5) Tránh `0/0` khi cả hai 0 và xử lý trùng nhau chính xác. (6) Xử lý `NaN` theo chính sách; trong ví dụ là `false`. (7) Overflow thành `Infinity`. (8) Khi cần thập phân chính xác theo nghiệp vụ như tiền. (9) Quan hệ gần bằng có thể không bắc cầu. (10) Sai số có ý nghĩa phụ thuộc thang giá trị, thường cần phần tương đối kết hợp điều kiện tuyệt đối gần 0.

**Ghi nhớ:** **Sai số tương đối đánh giá chênh lệch theo thang giá trị**, giúp so sánh số `float`/`double` ở nhiều độ lớn. Chọn rõ **mẫu số**, đặt **ngưỡng theo yêu cầu bài toán**, và xử lý **gần 0, NaN, vô cực và overflow trung gian**. Khi cần, kết hợp **sai số tuyệt đối hoặc tương đối**, chứ không dùng một epsilon cố định cho mọi tình huống.