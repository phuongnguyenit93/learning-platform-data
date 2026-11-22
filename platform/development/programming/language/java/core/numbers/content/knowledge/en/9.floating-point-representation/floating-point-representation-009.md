# ULP và khoảng cách giữa hai giá trị kề nhau trong Java

**ULP (Unit in the Last Place)** là đơn vị giúp mô tả **độ thưa của các số dấu phẩy động biểu diễn được** quanh một giá trị. Khác số nguyên, kiểu `float` và `double` không thể biểu diễn chính xác mọi số thực; chúng có một tập hữu hạn các mẫu bit. Khi trị tuyệt đối của số tăng, khoảng cách giữa các giá trị biểu diễn được gần nhau thường cũng tăng.

Ví dụ gây ngạc nhiên:

```java
double x = 1.0;
System.out.println(Math.nextUp(x));   // 1.0000000000000002
System.out.println(Math.ulp(x));      // 2.220446049250313E-16
```

Khi tiến từ `1.0` đến số `double` ngay phía trên, bước nhỏ nhất là khoảng `2.22 × 10^-16`. Nhưng ở quanh `10^16`, một đơn vị ULP đã là **2.0**: cộng thêm `1.0` có thể không tạo ra số `double` mới.

Điều quan trọng là phân biệt **khoảng cách của lưới biểu diễn**, **sai số sau khi tính toán**, và **độ chính xác thập phân mà con người mong muốn**. ULP mô tả lưới giá trị của kiểu dấu phẩy động, không tự động là một giới hạn sai số cho mọi thuật toán.

## 1. Vì sao số dấu phẩy động có các khoảng trống?

Java `float` là kiểu 32 bit và `double` là kiểu 64 bit theo chuẩn dấu phẩy động nhị phân IEEE 754, với các trường dấu, số mũ và phần trị (significand). Đối với các số hữu hạn **normal** (chuẩn hóa), giá trị gần như có cấu trúc:

```text
value = (-1)^sign × (1.fraction)_2 × 2^exponent
```

Các bit fraction là hữu hạn: `float` có **23 bit fraction được lưu** (24 bit significand hiệu dụng, tính cả bit 1 ẩn), còn `double` có **52 bit fraction được lưu** (53 bit significand hiệu dụng). Vì vậy, tại một khoảng số mũ cố định, chỉ có hữu hạn các mức fraction; giữa hai mức liên tiếp là một **khoảng trống**.

| Đặc tính | `float` | `double` |
| --- | --- | --- |
| Kích thước | 32 bit | 64 bit |
| Bit fraction lưu trữ | 23 | 52 |
| Số bit chính xác significand, gồm bit đầu ẩn ở normal | 24 | 53 |
| ULP tại `1.0` | `2^-23` ≈ `1.1920929E-7` | `2^-52` ≈ `2.220446049250313E-16` |
| Số nguyên liên tiếp biểu diễn chính xác đến ngưỡng | `2^24` | `2^53` |

Các con số này là **bit chính xác nhị phân**, không phải bảo đảm rằng một giá trị bất kỳ có chính xác 7 hoặc 16 chữ số thập phân. Chẳng hạn `0.1` không có biểu diễn hữu hạn trong hệ nhị phân và cần làm tròn khi chuyển thành `double`.

## 2. ULP là gì? Quan hệ với các số kề nhau

Ở một giá trị hữu hạn bình thường `x`, ULP là độ lớn của một bước biểu diễn tương ứng với vị trí bit cuối của phần trị tại cấp số mũ của `x`. Trong Java, `Math.ulp(x)` trả về giá trị ULP **không âm** cho `float` hoặc `double`, với quy tắc riêng ở zero, subnormal, vô cực và NaN.

Để quan sát các giá trị kề, Java cung cấp:

- `Math.nextUp(x)`: giá trị dấu phẩy động kế tiếp theo hướng **dương vô cực**.
- `Math.nextDown(x)`: giá trị kế tiếp theo hướng **âm vô cực**.
- `Math.nextAfter(start, direction)`: bước một giá trị biểu diễn được từ `start` theo hướng `direction`; dạng `double` trả `double`, dạng bắt đầu bằng `float` trả `float`.

Các phương thức này cho phép nhìn vào **những điểm trên lưới biểu diễn**, thay vì thử cộng một số `epsilon` tự chọn. Ví dụ, đặt `x = 1.0`:

```text
Math.nextDown(1.0) = 0.9999999999999999
                1.0
Math.nextUp(1.0)   = 1.0000000000000002
```

Tại đây khoảng cách phía **trên** là `2^-52`, nhưng khoảng cách phía **dưới** là `2^-53`. Đây không phải lỗi! `1.0` chính xác là một **lũy thừa của 2**, là ranh giới của hai khoảng có mật độ biểu diễn khác nhau. Bởi vậy không nên nói `Math.ulp(x)` luôn bằng **cả** `Math.nextUp(x)-x` và `x-Math.nextDown(x)`.

## 3. Công thức khoảng cách đối với số normal

Với `double` normal dương `x` trong khoảng lũy thừa hai:

```text
2^e <= x < 2^(e+1)
```

bước giữa các số normal liên tiếp **trong cùng khoảng số mũ** là:

```text
ULP_double(x) = 2^(e - 52)
ULP_float(x)  = 2^(e - 23)
```

Với `float` thay 52 bằng 23. Công thức mô tả khoảng cách theo significand; nó không nói rằng mọi số thực trong khoảng đều lưu được, cũng không nói kết quả phép toán luôn chỉ sai đúng một ULP.

Bảng ví dụ cho `double`:

| Vị trí | `Math.ulp(x)` | Ý nghĩa |
| --- | --- | --- |
| `x = 0.5` | `2^-53` | Mật độ dày hơn quanh `1.0` |
| `x = 1.0` | `2^-52` | Khoảng phía trên là `2^-52` |
| `x = 2.0` | `2^-51` | Bước tăng gấp đôi khi vượt ngưỡng 2 |
| `x = 1024.0` | `2^-42` | Mỗi bước lớn hơn bước quanh 1 |
| `x = 2^53` | `2` | Không còn đại diện được mọi số nguyên liên tiếp |

Sự thay đổi ULP theo số mũ tạo ra **độ chính xác tương đối gần như ổn định** đối với số normal, còn **độ chính xác tuyệt đối giảm khi độ lớn tăng**. Gần 1, một bước rất nhỏ; ở `2^53`, một bước là 2; ở các giá trị cực lớn, một bước có thể lớn hơn vô số số nguyên.

**Ngoại lệ ở ranh giới:** với `x = 2^e` ở miền normal (trừ một số ranh giới rất thấp), khoảng cách từ `x` xuống số hữu hạn kề trước **bằng một nửa** bước lên trên, vì nó nằm trong khoảng số mũ thấp hơn. `Math.ulp(x)` dùng khoảng tương ứng với `x`, tức khoảng phía trên ở ranh giới này.

## 4. Ví dụ chính xác quanh `1.0`

Ta có:

```text
nextUp(1.0) - 1.0   = 2^-52 = 2.220446049250313E-16
1.0 - nextDown(1.0) = 2^-53 = 1.1102230246251565E-16
Math.ulp(1.0)       = 2^-52
```

Ở `1.0`, `Math.ulp(x)` trùng bước **phía trên** nhưng không trùng bước **phía dưới**. Điều này quan trọng khi thiết kế thuật toán kiểm tra số gần nhau: nếu bạn mặc định “một ULP là một khoảng cách đều ở cả hai phía”, bạn sẽ sai tại các mốc `2^e`.

Để nhìn rõ bit fraction và mũ, dùng `Double.toHexString`:

```java
double ulp = Math.ulp(1.0);
System.out.println(Double.toHexString(ulp)); // 0x1.0p-52
```

Trong literal hex floating-point, `p-52` biểu thị số mũ **cơ số 2**. `0x1.0p-52` có giá trị `2^-52`; nó khác khái niệm literal số nguyên hex. Với `float`, `Float.toHexString(Math.ulp(1.0f))` trả `0x1.0p-23`.

## 5. Giới hạn số nguyên biểu diễn chính xác: `2^24` và `2^53`

Vì phần trị có số bit hữu hạn, trong `float` mọi số nguyên từ 0 đến `2^24` đều biểu diễn chính xác, nhưng **không phải mọi số nguyên lớn hơn** đều biểu diễn được. Với `double`, ngưỡng tương tự là `2^53`.

Ví dụ với `double`:

```java
double limit = 0x1.0p53;        // 2^53 = 9007199254740992
double tooSmallToChange = limit + 1.0;
System.out.println(tooSmallToChange == limit); // true
System.out.println(Math.ulp(limit));           // 2.0
```

Hai giá trị `limit` và `limit + 1.0` cho kết quả bằng nhau trong ví dụ này. Số toán học `2^53+1` nằm **chính giữa** hai số `double` biểu diễn được `2^53` và `2^53+2`; phép làm tròn mặc định kiểu **round to nearest, ties to even** đưa nó về `2^53`. Không phải “phép cộng bị bỏ qua theo cú pháp”; kết quả đúng về mặt toán học nằm **ngoài lưới biểu diễn**.

Tương tự, `Math.ulp(1e16)` là `2.0` và `1e16 + 1.0 == 1e16` có giá trị `true`. Với `float` tại `2^24`, `Math.ulp(0x1.0p24f)` bằng `2.0f`. Điều này giải thích tại sao không nên dùng `float` để lưu các định danh, bộ đếm nguyên lớn hoặc các giá trị cần chính xác tuyệt đối từng đơn vị.

## 6. Rounding: vì sao cộng nửa ULP có thể giữ nguyên giá trị?

Phép cộng trên dấu phẩy động được làm tròn tới một số có thể biểu diễn. Khi kết quả toán học nằm giữa hai giá trị kế nhau, chế độ mặc định thường là **gần nhất, trường hợp hòa thì chọn phần trị chẵn**. Do vậy một thay đổi nhỏ hơn khoảng cách gần số đang lưu có thể biến mất.

Ví dụ quanh `1.0`:

```java
double one = 1.0;
double step = Math.ulp(one);
boolean unchanged = (one + step / 2.0) == one; // true theo ties-to-even
boolean next = (one + step) == Math.nextUp(one); // true
```

Đây là đoạn mã minh họa trong phương thức. Ở `1.0`, `step/2.0 = 2^-53` nằm chính giữa `1.0` và `1.0 + 2^-52`; làm tròn chọn `1.0`. Nhưng **không thể suy thành quy luật chung** “cộng nửa ULP luôn không đổi”: kết quả hòa phụ thuộc bit cuối của significand và các điểm ranh giới.

Nếu cộng một thay đổi rất nhỏ vào tổng rất lớn nhiều lần, bạn có thể bị mất những bước nhỏ do làm tròn. Trong tính tổng dữ liệu nhiều độ lớn khác nhau, có thể cân nhắc thuật toán cộng bù (compensated summation), sắp xếp/nhóm dữ liệu hoặc dùng kiểu số thích hợp theo yêu cầu chính xác.

## 7. Subnormal: khoảng cách gần zero

Khi số quá nhỏ để biểu diễn dưới dạng **normal**, IEEE 754 có miền **subnormal (denormal)** với significand không có bit 1 ẩn. Các giá trị dương subnormal liên tiếp có bước **đều nhau**, giúp tiến dần về 0 thay vì lập tức mất toàn bộ các số nhỏ.

Với Java `double`:

- `Double.MIN_VALUE` là **số `double` dương nhỏ nhất khác 0**, khoảng `4.9E-324`; **không** phải số âm có độ lớn lớn nhất.
- `Double.MIN_NORMAL` là **số normal dương nhỏ nhất**, bằng `2^-1022`.
- Bước subnormal là `2^-1074`, cũng chính là `Double.MIN_VALUE`.
- `Math.ulp(0.0)` và `Math.ulp(Double.MIN_NORMAL)` đều bằng `Double.MIN_VALUE`.

Tương tự, `Float.MIN_VALUE` là số `float` dương subnormal nhỏ nhất (`2^-149`), và `Float.MIN_NORMAL` là số normal dương nhỏ nhất (`2^-126`). Bước nhỏ nhất ở miền subnormal của `float` là `2^-149`.

```java
double stepAtZero = Math.ulp(0.0);             // Double.MIN_VALUE
double firstPositive = Math.nextUp(0.0);        // Double.MIN_VALUE
double firstNegative = Math.nextDown(0.0);      // -Double.MIN_VALUE
```

Hai dạng zero `+0.0` và `-0.0` tồn tại trong IEEE 754; cả hai so sánh bằng nhau bằng `==`, nhưng có mẫu bit dấu khác nhau. `Math.nextUp(-0.0)` vẫn đi tới `Double.MIN_VALUE` dương. Trong miền subnormal, ULP **không tiếp tục giảm vô hạn**: dưới bước nhỏ nhất, một kết quả có thể làm tròn về zero (underflow).

## 8. Các trường hợp đặc biệt: `NaN`, vô cực và giá trị hữu hạn lớn nhất

Không phải mọi `double` đều là một số thực hữu hạn thông thường. Java có `NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`. Quy tắc của `Math.ulp`:

| Đầu vào | Kết quả `Math.ulp` |
| --- | --- |
| `NaN` | `NaN` |
| `+Infinity` hoặc `-Infinity` | `+Infinity` |
| `+0.0` hoặc `-0.0` | `Double.MIN_VALUE` (hoặc `Float.MIN_VALUE`) |
| Giá trị hữu hạn khác 0 | ULP dương tương ứng với độ rộng kiểu |

Ở `Double.MAX_VALUE`, `Math.ulp(Double.MAX_VALUE)` vẫn là một số **hữu hạn rất lớn**, nhưng `Math.nextUp(Double.MAX_VALUE)` là **`+Infinity`**. Vì vậy không được tính “gap đến số hữu hạn kế trên” bằng phép trừ `nextUp(x)-x` trong mọi trường hợp: ở đỉnh hữu hạn, **không có số hữu hạn kế trên**.

Hãy tránh so sánh `Math.ulp(Double.POSITIVE_INFINITY)` với một khoảng cách số học hữu hạn hoặc lấy `Math.nextUp(Double.MAX_VALUE) - Double.MAX_VALUE` để suy ra một ULP thông thường. Nếu dùng `Math.nextUp`/`nextDown` trong thuật toán số, phải kiểm tra `Double.isFinite`, `Double.isNaN`, `Double.isInfinite` khi đầu vào có thể là những giá trị đặc biệt.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu tệp với tên **`UlpSpacingDemo.java`**:

```java
public class UlpSpacingDemo {
    public static void main(String[] args) {
        double one = 1.0;
        double above = Math.nextUp(one);
        double below = Math.nextDown(one);
        System.out.println("ulp(1.0)=" + Math.ulp(one));
        System.out.println("nextUp(1.0)=" + above);
        System.out.println("nextDown(1.0)=" + below);
        System.out.println("gapAbove=" + (above - one));
        System.out.println("gapBelow=" + (one - below));
        System.out.println("upperGapEqualsUlp=" + (above - one == Math.ulp(one)));
        System.out.println("lowerGapEqualsUlp=" + (one - below == Math.ulp(one)));
        System.out.println("ulpHex=" + Double.toHexString(Math.ulp(one)));
        System.out.println("floatUlpHex=" + Float.toHexString(Math.ulp(1.0f)));
        System.out.println("ulp(0.0)==MIN_VALUE=" + (Math.ulp(0.0) == Double.MIN_VALUE));
        System.out.println("ulp(minNormal)==MIN_VALUE=" + (Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE));
        System.out.println("ulp(2.0)/ulp(1.0)=" + (Math.ulp(2.0) / Math.ulp(1.0)));
        System.out.println("ulp(2^53)=" + Math.ulp(0x1.0p53));
        System.out.println("2^53PlusOneLost=" + (0x1.0p53 + 1.0 == 0x1.0p53));
        System.out.println("ulp(1e16)=" + Math.ulp(1e16));
        System.out.println("1e16PlusOneLost=" + (1e16 + 1.0 == 1e16));
        System.out.println("floatULP(2^24)=" + Math.ulp(0x1.0p24f));
        System.out.println("nextUpMaxInfinity=" + Double.isInfinite(Math.nextUp(Double.MAX_VALUE)));
        System.out.println("ulpMaxFinite=" + Double.isFinite(Math.ulp(Double.MAX_VALUE)));
        System.out.println("ulpInfinityInfinite=" + Double.isInfinite(Math.ulp(Double.POSITIVE_INFINITY)));
        System.out.println("ulpNaNisNaN=" + Double.isNaN(Math.ulp(Double.NaN)));
        System.out.println("nextUpNegZeroMinPositive=" + (Math.nextUp(-0.0) == Double.MIN_VALUE));
        System.out.println("nextAfterOneDown=" + (Math.nextAfter(1.0, 0.0) == below));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 UlpSpacingDemo.java
java UlpSpacingDemo
```

Stdout chính xác:

```text
ulp(1.0)=2.220446049250313E-16
nextUp(1.0)=1.0000000000000002
nextDown(1.0)=0.9999999999999999
gapAbove=2.220446049250313E-16
gapBelow=1.1102230246251565E-16
upperGapEqualsUlp=true
lowerGapEqualsUlp=false
ulpHex=0x1.0p-52
floatUlpHex=0x1.0p-23
ulp(0.0)==MIN_VALUE=true
ulp(minNormal)==MIN_VALUE=true
ulp(2.0)/ulp(1.0)=2.0
ulp(2^53)=2.0
2^53PlusOneLost=true
ulp(1e16)=2.0
1e16PlusOneLost=true
floatULP(2^24)=2.0
nextUpMaxInfinity=true
ulpMaxFinite=true
ulpInfinityInfinite=true
ulpNaNisNaN=true
nextUpNegZeroMinPositive=true
nextAfterOneDown=true
```

Các dòng thể hiện bốn khía cạnh:

1. **Không đều ngay tại `1.0`**: `upperGapEqualsUlp=true`, `lowerGapEqualsUlp=false`; ULP tại `1.0` là `2^-52` nhưng bước xuống là `2^-53`.
2. **Độ lớn chi phối khoảng cách**: `ulp(2.0)/ulp(1.0)=2.0`; tại `2^53` và `1e16`, một bước tăng có độ lớn `2.0`.
3. **Zero và subnormal**: `Math.ulp(0.0) == Double.MIN_VALUE`, `Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE`.
4. **Ngoại lệ biên**: `nextUp(Double.MAX_VALUE)` chuyển tới Infinity dù ULP tại max vẫn hữu hạn; `NaN` và Infinity có quy tắc ULP đặc biệt.

Tập ví dụ sử dụng `Double.toHexString` và `Float.toHexString` để hiển thị đúng mũ nhị phân, tránh việc các chữ số thập phân hiển thị ngắn làm ta tưởng rằng các khoảng cách nguyên tử đều biểu diễn được bằng một số chữ số giống nhau.

## 10. ULP có phải sai số tính toán không?

**Không đồng nhất.** ULP là mức phân giải của tập giá trị biểu diễn được gần một số, còn **sai số** là khoảng cách giữa kết quả xấp xỉ và kết quả toán học/giá trị chuẩn được chọn.

Ví dụ, `Math.ulp(1.0)` khoảng `2.22E-16`, nhưng điều đó **không có nghĩa** mọi phép tính trên `double` sẽ sai nhiều nhất `2.22E-16`. Sai số thực tế phụ thuộc độ lớn giá trị, cách làm tròn, số bước tính, điều kiện bài toán và độ ổn định của thuật toán. Một phép trừ hai số rất gần nhau có thể mất nhiều chữ số có nghĩa do **catastrophic cancellation**; lặp hàng triệu phép toán có thể tích lũy sai số.

Khi một phép toán cơ bản được làm tròn đúng tới giá trị `double` gần nhất trong phạm vi thích hợp, có thể phân tích sai số làm tròn bằng phần của một ULP **của kết quả lý tưởng**. Tuy nhiên, phát biểu như “mọi thuật toán sai không quá nửa ULP” là **sai**. Sai số của cả chuỗi phép tính có thể vượt nhiều ULP, nhất là khi dữ liệu nhạy hoặc gần hủy triệt tiêu.

Ngoài ra, **đơn vị ULP ở `a` và ở `b` có thể khác nhau** khi hai số thuộc hai cấp số mũ khác nhau. Khi báo cáo “chênh 2 ULP”, cần xác định quy ước đo tại điểm nào hoặc theo thứ tự mã bit nào, xử lý sign/zero/infinity ra sao.

## 11. Dùng `Math.ulp` để so sánh số dấu phẩy động: có giới hạn

Một số đoạn mã thử so sánh xấp xỉ:

```java
double a = 1.0;
double b = Math.nextUp(a);
boolean near = Math.abs(a - b) <= Math.ulp(a); // true trong trường hợp này
```

Đó là **một ví dụ có kiểm soát**, không phải hàm “so sánh double đúng cho mọi đầu vào”. Có nhiều vấn đề nếu lấy `Math.ulp(a)` làm ngưỡng cố định:

- Ở ranh giới `2^e`, bước phía trên và bước phía dưới khác nhau.
- So sánh hai số chênh độ lớn rất xa cần chính sách rõ về ngưỡng tương đối/tuyệt đối; ULP chỉ ở một đầu không mô tả đầy đủ.
- `a - b` có thể overflow sang Infinity hoặc underflow về zero trong trường hợp biên.
- `NaN`, Infinity và signed zero cần quy tắc nghiệp vụ riêng; `NaN == NaN` luôn `false`, còn hai zero so sánh `==` là `true`.
- Kết quả “gần nhau trong vài ULP” chỉ nói chúng ở gần trên **lưới biểu diễn**, không khẳng định chúng đúng so với thực tế.

Nếu đang kiểm tra một thuật toán số, có thể dùng **sai số tuyệt đối** `abs(a-b)`, **sai số tương đối** theo độ lớn hoặc khoảng cách ULP theo một định nghĩa rõ ràng, tùy phép đo và dữ liệu. Gần zero, ngưỡng tương đối thuần túy thường bất tiện; ở trị tuyệt đối rất lớn, ngưỡng tuyệt đối cố định có thể quá chặt.

Đối với **tiền tệ** hoặc số thập phân phải chính xác theo quy tắc kế toán, thường nên dùng `BigDecimal` được tạo từ chuỗi thập phân (`new BigDecimal("0.1")`) và chọn chế độ làm tròn rõ ràng; đừng coi ULP là cách thay thế độ chính xác thập phân.

## 12. Các nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế | Cách kiểm tra |
| --- | --- | --- |
| “`double` chính xác khoảng 15–16 chữ số nên mọi bước đều nhỏ bằng nhau” | Bước tuyệt đối tăng khi cấp số mũ tăng | `Math.ulp(x)` ở nhiều độ lớn |
| `Math.ulp(x) == Math.nextUp(x)-x == x-Math.nextDown(x)` ở mọi nơi | Sai tại ranh giới lũy thừa 2 như `1.0` | In cả hai bước |
| `Math.ulp(0.0) == 0.0` | ULP tại zero bằng subnormal dương nhỏ nhất | `Math.ulp(0.0) == Double.MIN_VALUE` |
| `Double.MIN_VALUE` là số âm nhỏ nhất | Đây là số **dương** nhỏ nhất khác 0 | Phân biệt `Double.MIN_VALUE` và `-Double.MAX_VALUE` |
| `2^53 + 1` luôn khác `2^53` khi dùng `double` | Không biểu diễn được mọi số nguyên liền nhau sau ngưỡng | `0x1.0p53 + 1.0 == 0x1.0p53` |
| ULP là sai số tối đa của mọi chương trình | ULP mô tả khoảng cách lưới, không phải bảo đảm thuật toán | Đánh giá sai số theo phép tính cụ thể |
| `Math.ulp(Double.MAX_VALUE)` phải là Infinity | ULP tại MAX vẫn hữu hạn, nhưng `nextUp(MAX)` là Infinity | So hai lời gọi riêng biệt |
| So sánh `double` chỉ cần ngưỡng `1e-9` cho mọi thang số | Ngưỡng cố định không phù hợp mọi miền | Xác định sai số tuyệt đối/tương đối theo yêu cầu |
| `float` và `double` có cùng ULP tại `1.0` | Chúng có 24 và 53 bit significand hiệu dụng | So `Math.ulp(1f)` và `Math.ulp(1d)` |

## 13. Câu hỏi tự kiểm tra

1. **ULP mô tả điều gì?** Độ phân giải/khoảng cách biểu diễn liên quan tới vị trí bit cuối của significand gần một giá trị dấu phẩy động, không phải sai số mọi thuật toán.
2. **`Math.ulp(1.0)` bằng gì?** `2^-52` = khoảng `2.220446049250313E-16`. Với `float 1.0f`, ULP là `2^-23`.
3. **Vì sao `1.0-Math.nextDown(1.0)` chỉ bằng một nửa `Math.ulp(1.0)`?** Vì `1.0` là ranh giới giữa hai vùng số mũ liên tiếp; bước phía dưới nhỏ hơn phía trên.
4. **`Math.ulp(2.0)` so với `Math.ulp(1.0)` thế nào?** Gấp đôi; chúng lần lượt là `2^-51` và `2^-52`.
5. **Ở `2^53`, cộng `1.0` vào `double` có nhất thiết đổi số không?** Không; `2^53+1` nằm giữa hai giá trị biểu diễn được nên làm tròn về `2^53`.
6. **`Math.ulp(0.0)` có bằng 0 không?** Không; bằng `Double.MIN_VALUE`, tức bước subnormal dương nhỏ nhất.
7. **`Math.ulp(Double.MAX_VALUE)` là Infinity không?** Không, vẫn hữu hạn; riêng `Math.nextUp(Double.MAX_VALUE)` trả Infinity.
8. **Để tìm số representable ngay dưới `x`, dùng API nào?** `Math.nextDown(x)`; không tự lấy `x - Math.ulp(x)` và giả định luôn đúng.
9. **Có thể dùng `Math.ulp` trực tiếp thay `BigDecimal` cho phép tính tiền chính xác không?** Không; yêu cầu chính xác thập phân và quy tắc làm tròn tiền tệ là vấn đề khác.

**Kết luận:** ULP cho thấy vì sao số dấu phẩy động **có khoảng trống** và vì sao khoảng cách tuyệt đối **thay đổi theo độ lớn và số mũ**. Với Java, hãy dùng `Math.ulp` cùng `Math.nextUp`/`nextDown` để quan sát lưới biểu diễn, chú ý ranh giới lũy thừa 2, vùng subnormal và các giá trị đặc biệt. Khi tính toán thực tế, phân biệt rõ **độ phân giải biểu diễn** với **sai số thuật toán** và chọn chiến lược so sánh/làm tròn theo yêu cầu nghiệp vụ.
