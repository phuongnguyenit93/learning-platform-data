# Phạm vi số nguyên được `float` và `double` biểu diễn liên tiếp chính xác trong Java

## 1. “Biểu diễn liên tiếp chính xác” nghĩa là gì?

Một kiểu dấu phẩy động **biểu diễn chính xác** số nguyên `n` khi có một giá trị thuộc kiểu đó bằng đúng `n`, không cần làm tròn sang số khác. Nhưng việc một số nguyên riêng lẻ biểu diễn được không có nghĩa **mọi số nguyên liền kề** cũng biểu diễn được.

Ta gọi `[-M, M]` là một **khoảng số nguyên liên tiếp biểu diễn chính xác** khi mọi số nguyên `n` thỏa `-M <= n <= M` đều có giá trị `float` hoặc `double` bằng đúng `n`. Với hai kiểu Java:

| Kiểu | Số bit chính xác của phần trị (precision) | Khoảng số nguyên liên tiếp chính xác, bao gồm hai đầu mút | Mốc dương dạng thập phân |
| --- | ---: | --- | ---: |
| `float` | 24 bit | `[-2^24, 2^24]` | `16_777_216` |
| `double` | 53 bit | `[-2^53, 2^53]` | `9_007_199_254_740_992` |

**Ngay sau** mốc dương, `2^24 + 1` không biểu diễn chính xác bằng `float` và `2^53 + 1` không biểu diễn chính xác bằng `double`. Tuy nhiên, một số nguyên xa hơn **vẫn có thể** biểu diễn chính xác, ví dụ `2^24 + 2` dưới dạng `float` và `2^53 + 2` dưới dạng `double`.

Từ “liên tiếp” rất quan trọng: không nên viết “`float` chỉ biểu diễn được số nguyên tối đa `2^24`” hoặc “`double` chỉ biểu diễn được số nguyên tối đa `2^53`”. Các câu đó sai: các kiểu dấu phẩy động còn biểu diễn được nhiều số nguyên có độ lớn lớn hơn, nhưng sẽ **bỏ qua một số số nguyên ở giữa**.

Một ví dụ sát biên:

```java
int a = 16_777_216;       // 2^24
int b = 16_777_217;       // 2^24 + 1
int c = 16_777_218;       // 2^24 + 2

float fa = a;             // chính xác
float fb = b;             // làm tròn thành 16_777_216f
float fc = c;             // chính xác
```

Vì vậy `fa == fb` là `true` dù `a != b`. Đây là lỗi tiềm ẩn khi dùng `float` làm khóa định danh, đếm số nguyên lớn hoặc so sánh hai kết quả vốn khác nhau đúng một đơn vị.

## 2. Vì sao mốc là `2^24` và `2^53`?

`float` và `double` của Java theo định dạng IEEE 754 binary32/binary64. Một số hữu hạn chuẩn hóa có thể được diễn giải về mặt toán học dưới dạng:

\[
(-1)^{sign} \times (1.fraction)_2 \times 2^{exponent}
\]

Trong đó phần trị hữu hiệu bao gồm bit `1` đầu ẩn (*implicit leading bit*) của số chuẩn hóa:

| Đặc tính | `float` (binary32) | `double` (binary64) |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Trường số mũ | 8 | 11 |
| Trường fraction lưu thực tế | 23 | 52 |
| **Độ chính xác phần trị hiệu dụng `p`** | **24** | **53** |

Trong khoảng các số dương từ `2^e` (bao gồm) đến `2^(e+1)` (không bao gồm), khoảng cách giữa hai số dấu phẩy động chuẩn hóa liền kề là:

\[
ULP = 2^{e-(p-1)}
\]

`ULP` (*unit in the last place*) chỉ khoảng cách ở mức độ chính xác đó. Với các số nguyên:

- Khi `ULP <= 1`, lưới biểu diễn đủ mịn để chứa **từng số nguyên**.
- Tại `2^p`, khoảng cách tới giá trị tiếp theo phía dương tăng thành `2`: số `2^p + 1` nằm giữa hai giá trị biểu diễn được.
- Sau những mốc cao hơn, khoảng cách có thể thành `4`, `8`, `16`, ...; các số có phần bit thấp không phù hợp với bước nhảy sẽ không còn biểu diễn được chính xác.

Với `float`, `p=24`: trong `[2^23, 2^24)` bước là `1`, còn tại và ngay phía trên `2^24` bước là `2`. Với `double`, `p=53`: trong `[2^52, 2^53)` bước là `1`, còn tại và phía trên `2^53` bước là `2`.

**Lưu ý tại đúng biên:** `2^p` vẫn được biểu diễn chính xác, và số nguyên ngay trước nó (`2^p - 1`) vẫn chính xác. Bước nhảy về bên trái và bên phải của một lũy thừa hai có thể khác nhau. Do đó miền liên tiếp chính xác có đầu mút **bao gồm** `±2^p`; tuy nhiên `2^p` không còn có hàng xóm lớn hơn đúng `1` ở dạng dấu phẩy động cùng kiểu.

## 3. Quan sát trực tiếp các khoảng trống sau mốc

### 3.1. `float`: biên `2^24`

| Số nguyên gốc | Giá trị `float` biểu diễn (dưới dạng số nguyên) | Chính xác? |
| --- | ---: | --- |
| `16_777_215 = 2^24 - 1` | `16_777_215` | Có |
| `16_777_216 = 2^24` | `16_777_216` | Có |
| `16_777_217 = 2^24 + 1` | `16_777_216` | Không |
| `16_777_218 = 2^24 + 2` | `16_777_218` | Có |
| `16_777_219 = 2^24 + 3` | `16_777_220` | Không |
| `16_777_220 = 2^24 + 4` | `16_777_220` | Có |

Ở khu vực ngay phía trên `2^24`, chỉ các số nguyên **chẵn** được biểu diễn chính xác. Giá trị lẻ nằm giữa hai số chẵn biểu diễn được sẽ được làm tròn khi chuyển sang `float`.

Quy tắc mặc định của chuyển đổi số nguyên sang dấu phẩy động Java là làm tròn tới giá trị gần nhất; khi đúng giữa hai giá trị, chọn kết quả có bit cuối phần trị là **chẵn** (*round to nearest, ties to even*). Bởi vậy:

- `16_777_217` nằm giữa `16_777_216` và `16_777_218`, nên về `16_777_216`.
- `16_777_219` nằm giữa `16_777_218` và `16_777_220`, nên về `16_777_220`.

Về phía âm có hiện tượng đối xứng: `-16_777_217` làm tròn thành `-16_777_216` dưới dạng `float`. Không nên áp dụng suy luận “số âm thì luôn làm tròn xuống”; quy tắc làm tròn ở đây dựa vào số gần nhất trong hệ nhị phân.

### 3.2. `double`: biên `2^53`

| Số nguyên gốc | Giá trị `double` biểu diễn (dưới dạng số nguyên) | Chính xác? |
| --- | ---: | --- |
| `9_007_199_254_740_991 = 2^53 - 1` | `9_007_199_254_740_991` | Có |
| `9_007_199_254_740_992 = 2^53` | `9_007_199_254_740_992` | Có |
| `9_007_199_254_740_993 = 2^53 + 1` | `9_007_199_254_740_992` | Không |
| `9_007_199_254_740_994 = 2^53 + 2` | `9_007_199_254_740_994` | Có |
| `9_007_199_254_740_995 = 2^53 + 3` | `9_007_199_254_740_996` | Không |

Ví dụ:

```java
long a = 9_007_199_254_740_992L;
long b = 9_007_199_254_740_993L;

double da = a; // 9_007_199_254_740_992
double db = b; // cũng là 9_007_199_254_740_992
```

Ở đây **hai `long` khác nhau có thể trở thành cùng một `double`**. Việc chuyển đổi Java vẫn hợp lệ và không ném lỗi, vì đây là một phép chuyển kiểu số nguyên → dấu phẩy động được ngôn ngữ cho phép.

Một số thư viện hoặc giao thức gọi `2^53 - 1` là *largest safe integer* vì yêu cầu phép cộng/trừ `1` và các số lân cận còn phân biệt được. Trong bài này, ta đang xét **tập các số nguyên biểu diễn đúng**, do đó `2^53` bản thân nó vẫn đúng và là đầu mút của khoảng liên tiếp; cách dùng từ “safe” có thể đặt điều kiện chặt hơn cho các phép tính.

## 4. Phạm vi liên tiếp khác với giá trị lớn nhất của kiểu

Không được nhầm ngưỡng `2^24`/`2^53` với `Float.MAX_VALUE`/`Double.MAX_VALUE`:

- `Float.MAX_VALUE` xấp xỉ `3.4028235 × 10^38`, rất lớn so với `16_777_216`.
- `Double.MAX_VALUE` xấp xỉ `1.7976931348623157 × 10^308`, rất lớn so với `9_007_199_254_740_992`.

Các giá trị `MAX_VALUE` này mô tả **cận trên số hữu hạn**, không mô tả miền số nguyên mà mọi giá trị liên tiếp đều có thể biểu diễn. Càng xa 0, khoảng cách giữa các giá trị dấu phẩy động thường càng lớn.

Ví dụ `Long.MIN_VALUE = -2^63` **biểu diễn chính xác** bằng `double` vì nó là một lũy thừa của 2, dù có độ lớn lớn hơn `2^53`. Trái lại, `Long.MAX_VALUE = 2^63 - 1` **không chính xác** khi chuyển sang `double` và sẽ được làm tròn thành `2^63`, một giá trị không nằm trong miền `long`.

Tương tự, `Integer.MAX_VALUE = 2^31 - 1` khi chuyển sang `float` được làm tròn thành `2^31`. Điều đáng chú ý là kết quả `float` hoàn toàn hữu hạn; việc nó hữu hạn không chứng tỏ giá trị nguyên ban đầu được bảo toàn.

## 5. Liên hệ với các kiểu số nguyên của Java

| Chuyển kiểu | Có đảm bảo chính xác cho **mọi** giá trị nguồn không? | Lý do |
| --- | --- | --- |
| `byte` → `float` | Có | Toàn bộ miền 8 bit nằm trong `±2^24` |
| `short` → `float` | Có | Toàn bộ miền 16 bit nằm trong `±2^24` |
| `char` → `float` | Có | Các giá trị `char` từ 0 đến 65535 nằm trong miền chính xác |
| `int` → `float` | **Không** | Nhiều `int` có độ lớn lớn hơn `2^24` |
| `int` → `double` | **Có** | Toàn bộ miền `int` nằm trong `±2^53` |
| `long` → `float` | **Không** | Phần trị `float` chỉ có 24 bit chính xác |
| `long` → `double` | **Không** | Nhiều `long` có độ lớn lớn hơn `2^53` |

Ngay cả chuyển kiểu **mở rộng** (*widening primitive conversion*) như `int` → `float` hoặc `long` → `double` vẫn có thể làm mất thông tin phần bit thấp. “Mở rộng” nói về quy tắc phân loại chuyển kiểu Java, không phải cam kết giữ mọi chữ số chính xác.

`float` → `double` thì giữ đúng **giá trị `float` đã có**, nhưng không thể phục hồi số nguyên gốc nếu nó đã bị làm tròn trước đó:

```java
int original = 16_777_217;
float rounded = original;       // 16_777_216
double widened = rounded;       // vẫn chính xác 16_777_216, không khôi phục 16_777_217
```

Một `double` biểu diễn mọi `int` chính xác, nhưng điều này không có nghĩa *mọi phép toán* giữa các giá trị `int` chuyển sang `double` đều cho kết quả đúng như số nguyên toán học. Kết quả của phép tính có thể vượt `2^53` hoặc có phần lẻ không biểu diễn chính xác.

## 6. Dùng `Math.ulp`, `Math.nextUp` và `Math.nextDown` để kiểm tra khoảng cách

Java có các hàm trong `Math` hữu ích để quan sát “lưới” giá trị:

- `Math.ulp(x)` trả về độ lớn của một ULP tại `x` (có overload `float` và `double`).
- `Math.nextUp(x)` trả về giá trị dấu phẩy động biểu diễn được liền sau theo hướng tăng.
- `Math.nextDown(x)` trả về giá trị biểu diễn được liền trước theo hướng giảm.

Ở mốc `float`:

```java
float edge = 16_777_216f;
float up = Math.nextUp(edge);     // 16_777_218f
float down = Math.nextDown(edge); // 16_777_215f
float step = Math.ulp(edge);      // 2.0f
```

Ở mốc `double`:

```java
double edge = 9_007_199_254_740_992d;
double up = Math.nextUp(edge);     // 9_007_199_254_740_994d
double down = Math.nextDown(edge); // 9_007_199_254_740_991d
double step = Math.ulp(edge);      // 2.0d
```

Một chi tiết quan trọng: **`Math.ulp(edge)` bằng 2 không có nghĩa giá trị phía dưới cách `edge` hai đơn vị**. Biên là nơi bước nhảy tăng: `nextDown(edge)` cách `1`, còn `nextUp(edge)` cách `2`.

`Math.ulp` chỉ đo khoảng cách cục bộ, không phải một phép kiểm tra chuyển đổi nguyên gốc có giữ đủ giá trị hay không. Muốn đánh giá độ chính xác của một giá trị nguồn cụ thể, còn phải so sánh với nguồn theo cách không tự làm tròn nguồn trong quá trình kiểm tra.

## 7. Ví dụ Java 17 đầy đủ, có thể chạy trực tiếp

Tạo tệp `ExactIntegerRangeDemo.java`:

```java
public class ExactIntegerRangeDemo {
    // Dùng long trung gian để kiểm tra float -> int mà không bão hòa ở Integer.MAX_VALUE.
    private static boolean exactAsFloat(int original) {
        float encoded = original;
        return (long) encoded == (long) original;
    }

    // Double của Long.MAX_VALUE làm tròn thành 2^63: phải chặn biên này.
    private static boolean exactAsDouble(long original) {
        double encoded = original;
        return encoded < 0x1.0p63 && (long) encoded == original;
    }

    public static void main(String[] args) {
        int floatEdge = 1 << 24;
        long doubleEdge = 1L << 53;

        System.out.println("float edge = " + floatEdge);
        System.out.println("float edge+1 stored = "
                + (long) (float) (floatEdge + 1));
        System.out.println("float edge+2 stored = "
                + (long) (float) (floatEdge + 2));
        System.out.println("float edge+1 exact = "
                + exactAsFloat(floatEdge + 1));
        System.out.println("float edge+2 exact = "
                + exactAsFloat(floatEdge + 2));
        System.out.println("float ulp at edge = " + Math.ulp((float) floatEdge));

        System.out.println("double edge = " + doubleEdge);
        System.out.println("double edge+1 stored = "
                + (long) (double) (doubleEdge + 1));
        System.out.println("double edge+2 stored = "
                + (long) (double) (doubleEdge + 2));
        System.out.println("double edge+1 exact = "
                + exactAsDouble(doubleEdge + 1));
        System.out.println("double edge+2 exact = "
                + exactAsDouble(doubleEdge + 2));
        System.out.println("double ulp at edge = "
                + Math.ulp((double) doubleEdge));

        System.out.println("Integer.MAX_VALUE exact as float = "
                + exactAsFloat(Integer.MAX_VALUE));
        System.out.println("Long.MAX_VALUE exact as double = "
                + exactAsDouble(Long.MAX_VALUE));
        System.out.println("Long.MIN_VALUE exact as double = "
                + exactAsDouble(Long.MIN_VALUE));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ExactIntegerRangeDemo.java
java ExactIntegerRangeDemo
```

Đầu ra dự kiến:

```text
float edge = 16777216
float edge+1 stored = 16777216
float edge+2 stored = 16777218
float edge+1 exact = false
float edge+2 exact = true
float ulp at edge = 2.0
double edge = 9007199254740992
double edge+1 stored = 9007199254740992
double edge+2 stored = 9007199254740994
double edge+1 exact = false
double edge+2 exact = true
double ulp at edge = 2.0
Integer.MAX_VALUE exact as float = false
Long.MAX_VALUE exact as double = false
Long.MIN_VALUE exact as double = true
```

Hai hàm kiểm tra trên phục vụ **đúng kiểu nguồn được ghi trong chữ ký**: một `int` sang `float`, và một `long` sang `double`. Chúng không phải thư viện kiểm tra tùy ý mọi số thực hay số nguyên vô hạn. `0x1.0p63` là literal `double` biểu diễn đúng `2^63`; `Long.MAX_VALUE` nếu đã được đổi sang `double` thì có thể thành chính giá trị đó, nên cần phép kiểm tra cận trên trước khi cast lại về `long`.

Ở trường hợp `int` → `float`, ép ngược sang `long` làm bộ kiểm tra tránh sai sót do bão hòa của chuyển `float` → `int` tại `Integer.MAX_VALUE`. `float` nhận từ một `int` luôn là số hữu hạn có độ lớn nằm trong miền `long`, nên bước ép sang `long` này đủ phạm vi để so sánh với `int` gốc.

## 8. Các bẫy khi kiểm tra dữ liệu có mất độ chính xác hay không

### 8.1. So sánh hỗn hợp có thể tự chuyển nguồn thành `float`/`double`

```java
int n = 16_777_217;
float f = n;

System.out.println(n == f); // true, dù f chứa 16_777_216
```

Java áp dụng *binary numeric promotion*: khi so sánh `int` với `float`, `n` cũng được chuyển sang `float`, nên **cả hai bên đều đã bị làm tròn** và phép so sánh báo bằng nhau.

Tương tự:

```java
long n = 9_007_199_254_740_993L;
double d = n;

System.out.println(n == d); // true, dù d chứa 9_007_199_254_740_992
```

Do đó `original == (float) original` hoặc `original == (double) original` **không phải** phép thử đảm bảo không mất thông tin. Hãy giữ và so sánh nguồn ở kiểu nguyên thích hợp, đồng thời tránh bẫy bão hòa lúc ép ngược.

### 8.2. Ép ngược có thể bão hòa và gây kết quả “đúng giả”

Một kiểm tra tưởng hợp lý là `(int) (float) n == n`. Nhưng với `n = Integer.MAX_VALUE`, giá trị `float` đã làm tròn thành `2^31` (ngoài miền `int`), và cast về `int` bão hòa thành `Integer.MAX_VALUE`; so sánh có thể trả `true` dù giá trị trung gian sai.

Tương tự, `Long.MAX_VALUE` chuyển sang `double` thành `2^63`, rồi cast về `long` lại bão hòa thành `Long.MAX_VALUE`. Để kiểm tra chính xác, cần loại bỏ các giá trị trung gian ở hoặc ngoài biên kiểu đích trước khi cast, hoặc dùng kiểu nguyên trung gian lớn hơn nếu biết miền nguồn đủ nhỏ, như hàm ở mục 7.

### 8.3. Số thập phân chính xác là một vấn đề khác

`0.1` là số thực có biểu diễn thập phân hữu hạn nhưng không có biểu diễn nhị phân hữu hạn; vì vậy `0.1d` không chính xác tuyệt đối theo toán học. Mốc `2^53` **chỉ nói về số nguyên liên tiếp**, không nói rằng mọi số thực trong khoảng `[-2^53, 2^53]` đều biểu diễn đúng.

Với số tiền hoặc đầu vào decimal cần bảo toàn chữ số, cân nhắc dùng `BigDecimal` được tạo từ chuỗi:

```java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
```

Nếu cần một giá trị nguyên lớn với phạm vi vượt `long`, dùng `BigInteger`. Không thể khôi phục phần giá trị đã bị làm tròn nếu chỉ còn dữ liệu `float`/`double`.

### 8.4. Các phép tính ở sát ngưỡng có thể dừng tăng từng đơn vị

Ví dụ:

```java
float count = 16_777_216f;
count = count + 1f; // vẫn 16_777_216f
```

Vì `16_777_217` ở đúng giữa hai giá trị `float` đại diện được, kết quả làm tròn về `16_777_216f` (*ties to even*). Phép tính không gây exception. Tương tự, cộng `1d` vào `9_007_199_254_740_992d` vẫn trả lại giá trị ban đầu.

Không nên dùng `float` hoặc `double` làm bộ đếm cho những thao tác đòi hỏi số nguyên tăng chính xác từng 1 trên phạm vi lớn; chọn `int`, `long`, hoặc `BigInteger` theo phạm vi cần dùng và kiểm tra tràn số nguyên khi phù hợp.

## 9. Quy tắc lựa chọn kiểu cho từng bài toán

| Tình huống | Cách xử lý |
| --- | --- |
| Lưu một giá trị `int` bất kỳ để xử lý dưới dạng dấu phẩy động | `double` bảo toàn giá trị nguyên của mọi `int` |
| Lưu số đếm chắc chắn trong `[-16_777_216, 16_777_216]` bằng `float` | Mỗi số nguyên trong khoảng đều chính xác, nhưng cần xét độ chính xác của kết quả các phép tính sau đó |
| Chuyển `int` ngoài phạm vi trên sang `float` | Không mặc định chính xác; kiểm tra giá trị cụ thể hoặc giữ kiểu nguyên |
| Chuyển `long` sang `double` | Mọi giá trị trong `[-2^53, 2^53]` đều chính xác; ngoài vùng chỉ một phần chính xác |
| Lưu ID, mã giao dịch, khóa hoặc số đếm lớn | Dùng kiểu nguyên (`long`, `BigInteger`) thay vì `float`/`double` nếu cần phân biệt mọi giá trị |
| Làm việc với tiền / decimal yêu cầu chữ số thập phân chính xác | Dùng `BigDecimal` với nguồn từ chuỗi decimal và quy tắc làm tròn rõ ràng |
| Quan sát lưới biểu diễn quanh một giá trị | Dùng `Math.ulp`, `Math.nextUp`, `Math.nextDown`; chúng không tự xác thực nguồn có mất thông tin hay không |

Các giá trị vượt ngưỡng không phải tất cả đều sai: chẳng hạn `2^60` biểu diễn chính xác bằng `double` vì là lũy thừa của 2. Câu hỏi quan trọng là: **“Kiểu này có biểu diễn chính xác tất cả số nguyên trong khoảng tôi cần hay chỉ một số giá trị rời rạc?”**

## 10. Câu hỏi tự kiểm tra

1. `float` có biểu diễn chính xác `16_777_216` không? `16_777_217` thì sao?
2. Vì sao `16_777_218` vẫn chính xác bằng `float` dù nằm ngoài khoảng liên tiếp?
3. Một `double` có biểu diễn chính xác mọi giá trị `int` không? Có biểu diễn chính xác mọi `long` không?
4. `Long.MIN_VALUE` là một số nguyên rất lớn về độ lớn. Vì sao vẫn chính xác bằng `double`?
5. Vì sao `long n = 9_007_199_254_740_993L; double d = n; n == d` có thể là `true`?
6. Có thể dùng `(int)(float)n == n` để chắc chắn phép chuyển `int` → `float` chính xác không?
7. Tại `2^24f`, `Math.nextDown` và `Math.nextUp` cách giá trị đó bao nhiêu?

**Đáp án:**

1. `16_777_216` có; `16_777_217` không (làm tròn về `16_777_216`).
2. Bước nhảy phía trên mốc là `2`, nên các số chẵn gần mốc vẫn nằm trên lưới biểu diễn.
3. Có với mọi `int`; không với mọi `long`, vì `double` chỉ có 53 bit phần trị chính xác.
4. `-2^63` là một lũy thừa của 2 và được biểu diễn chính xác dù nằm ngoài khoảng liên tiếp.
5. Khi so sánh `long` với `double`, toán hạng `long` cũng bị chuyển sang `double`, làm hai bên trùng nhau sau khi mất thông tin.
6. Không; ép `float` đã làm tròn về lại `int` có thể bão hòa ở `Integer.MAX_VALUE`, tạo kết quả đúng giả.
7. `nextDown(2^24f) = 2^24 - 1`, cách `1`; `nextUp(2^24f) = 2^24 + 2`, cách `2`.

**Ghi nhớ:** `float` bảo toàn *mọi* số nguyên liên tiếp đến `±2^24`, `double` đến `±2^53` (đều bao gồm đầu mút). Ngoài miền này vẫn có nhiều số nguyên chính xác nhưng không còn **mọi** số nguyên liền kề. Độ lớn có thể biểu diễn, độ chính xác phần trị và độ chính xác của phép tính là ba thuộc tính cần phân biệt.