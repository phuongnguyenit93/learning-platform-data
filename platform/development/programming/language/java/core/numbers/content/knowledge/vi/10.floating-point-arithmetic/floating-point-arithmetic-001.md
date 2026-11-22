# Cộng, trừ, nhân, chia và làm tròn về giá trị biểu diễn được trong Java

## 1. Điểm cốt lõi: kết quả toán học và kết quả lưu trong máy có thể khác nhau

Trong toán học, các phép `+`, `-`, `*` và `/` trên số thực tạo ra kết quả chính xác nếu các toán hạng được biết chính xác. Trong Java, các kiểu `float` và `double` chỉ lưu một **tập hữu hạn các giá trị dấu phẩy động nhị phân**. Khi một phép tính cho ra kết quả toán học không thuộc tập đó, Java phải **làm tròn về một giá trị biểu diễn được**.

Ví dụ kinh điển:

~~~java
double result = 0.1 + 0.2;
System.out.println(result);           // 0.30000000000000004
System.out.println(result == 0.3);    // false
~~~

Đây là đoạn minh họa, không phải lớp chạy độc lập. Chương trình không “cộng sai”: các literal thập phân `0.1`, `0.2` và `0.3` đã được chuyển thành các giá trị `double` gần nhất có thể biểu diễn. Kết quả cộng hai giá trị `double` đầu tiên sau làm tròn không trùng đúng bit với giá trị `double` mà literal `0.3` biểu diễn.

**Điều cần phân biệt:**

1. **Giá trị toán học**: ví dụ `1/10 + 2/10 = 3/10`.
2. **Giá trị được lưu của toán hạng**: biểu diễn nhị phân hữu hạn gần các phân số thập phân đó.
3. **Kết quả phép tính trước khi làm tròn**: kết quả số học chính xác của hai giá trị đã lưu, xét về mặt mô hình.
4. **Kết quả Java trả về**: được làm tròn vào miền giá trị biểu diễn được của kiểu kết quả, hoặc nhận giá trị đặc biệt như vô cực/NaN theo quy tắc IEEE 754.

Không nên coi `float` và `double` là những số thập phân có thể ghi và tính toán chính xác tùy ý.

## 2. Hai kiểu dấu phẩy động trong Java

| Đặc tính | `float` | `double` |
|---|---|---|
| Chuẩn biểu diễn | IEEE 754 binary32 | IEEE 754 binary64 |
| Kích thước | 32 bit | 64 bit |
| Độ chính xác phần định trị (*significand precision*) | 24 bit nhị phân | 53 bit nhị phân |
| Số chữ số thập phân có nghĩa gần đúng | 6–7 | 15–16 |
| Khoảng số hữu hạn bình thường (*normal*) | Rộng, nhưng kém `double` | Rộng hơn `float` |
| Giá trị đặc biệt | `+Infinity`, `-Infinity`, `NaN`, `+0.0`, `-0.0` | Tương tự |
| Literal mặc định | Cần hậu tố `f`/`F`, ví dụ `0.1f` | `0.1` mặc định là `double` |

Ngoài số *normal*, cả hai kiểu có thể lưu các số **subnormal** rất gần 0, với độ chính xác tương đối suy giảm. `Double.MIN_VALUE` là **số dương subnormal nhỏ nhất** lớn hơn 0, không phải “số `double` âm nhất”; trị số hữu hạn âm xa 0 nhất là `-Double.MAX_VALUE`. Với `float`, ý nghĩa của `Float.MIN_VALUE` cũng tương tự.

Khi cần ưu tiên độ chính xác và không có yêu cầu tiết kiệm bộ nhớ hay giao thức bắt buộc `float`, `double` thường là lựa chọn phù hợp hơn. Tuy nhiên, `double` cũng không làm cho `0.1` trở thành phân số nhị phân chính xác.

### Vì sao `0.1` không biểu diễn chính xác bằng nhị phân?

Giá trị `0.5 = 1/2` và `0.25 = 1/4` có biểu diễn nhị phân hữu hạn. Nhưng `0.1 = 1/10` có mẫu nhị phân lặp vô hạn; không thể lưu chính xác bằng số bit hữu hạn. Trình biên dịch chuyển literal thập phân thành giá trị `float` hoặc `double` theo quy tắc làm tròn.

Phép in `System.out.println(0.1)` cho `0.1` **không chứng minh lưu chính xác**: `Double.toString` chọn biểu diễn thập phân ngắn gọn mà khi phân tích lại sẽ khôi phục đúng giá trị `double` tương ứng. Chữ số thập phân khi hiển thị không phải toàn bộ nội dung bit của giá trị đã lưu.

## 3. Quy tắc làm tròn về giá trị biểu diễn được

Với các phép số học dấu phẩy động cơ bản ở Java 17+, kết quả hữu hạn được làm tròn theo chế độ **round to nearest, ties to even** của IEEE 754:

- Nếu kết quả chính xác nằm gần một giá trị biểu diễn được hơn giá trị khác, chọn giá trị gần nhất.
- Nếu kết quả nằm **đúng giữa** hai giá trị biểu diễn được kế tiếp, chọn giá trị có bit cuối của phần định trị chẵn (*ties to even*).
- Quy tắc này áp dụng cho kết quả phép toán số học dấu phẩy động, **không đồng nghĩa** với quy tắc của mọi hàm trong `Math`, chẳng hạn `Math.round`.

Đặc biệt, **mỗi phép toán cơ bản** cộng/trừ/nhân/chia tạo kết quả theo kiểu của biểu thức với độ chính xác và miền số mũ tương ứng. Trong Java 17+, ngữ nghĩa dấu phẩy động luôn nghiêm ngặt (*always-strict*), nên không còn chuyện dùng trung gian có số mũ mở rộng khác nhau vì từng vùng `strictfp`/không `strictfp` như các JDK rất cũ.

### ULP và khoảng cách giữa hai số kề nhau

**ULP** (*unit in the last place*) giúp diễn tả độ thô của lưới các số biểu diễn được ở một cỡ trị số nhất định. Java cung cấp `Math.ulp(double)` và `Math.ulp(float)`; `Math.nextUp(x)` và `Math.nextDown(x)` dịch tới số dấu phẩy động biểu diễn được kế cận theo hướng tương ứng.

Quanh `1.0` kiểu `double`, khoảng cách từ `1.0` đến số `double` kế tiếp lớn hơn là `2^-52`, xấp xỉ `2.220446049250313E-16`. Vì vậy, biểu thức:

~~~java
double halfGap = Math.ulp(1.0) / 2.0;
double rounded = 1.0 + halfGap;
~~~

có `rounded == 1.0`: tổng lý tưởng nằm đúng giữa `1.0` và `Math.nextUp(1.0)`, tie được làm tròn về `1.0` theo quy tắc chẵn.

Không có một “độ sai số tuyệt đối cố định” cho mọi giá trị `double`. Khi trị tuyệt đối tăng, khoảng cách giữa các số biểu diễn được nhìn chung tăng; với số rất nhỏ trong vùng subnormal, cơ chế lại có chi tiết riêng.

## 4. Cộng và trừ: làm tròn và mất chữ số có nghĩa

### 4.1. Cộng `+`

Với hai toán hạng dấu phẩy động, Java cộng những giá trị mà mỗi toán hạng đang lưu, rồi trả kết quả biểu diễn được của kiểu kết quả. Điều đó có thể làm xuất hiện chênh lệch nhỏ so với phép cộng thập phân tưởng tượng.

~~~java
double a = 0.1;
double b = 0.2;
double sum = a + b;      // 0.30000000000000004
~~~

Không có biểu diễn chính xác `0.1` hoặc `0.2` trong binary64, nên phép so sánh `sum == 0.3` là `false` ở đây.

**Cộng số rất lớn với số quá nhỏ** có thể “nuốt mất” số nhỏ khi độ chênh lệch vượt mức phân giải của `double`:

~~~java
double large = 1e16;
double small = 1.0;
double same = large + small; // vẫn biểu diễn thành 1.0E16
~~~

Chênh lệch 1 quá nhỏ so với khoảng cách ULP quanh `1e16`. Do đó, dù toán học `large + 1` khác `large`, kết quả Java có thể bằng đúng `large`.

### 4.2. Trừ `-` và *catastrophic cancellation*

Phép trừ hai số rất gần nhau có thể làm mất nhiều chữ số có nghĩa: nếu hai số đã được làm tròn ở bước trước, sai số của mỗi số có thể trở nên lớn so với hiệu nhỏ. Hiện tượng này được gọi là **triệt tiêu chữ số có nghĩa** (*catastrophic cancellation*).

Ví dụ, không phải biểu thức đại số nào cũng giữ nguyên kết quả khi các phép trung gian được làm tròn:

~~~java
double original = 1e16;
double modified = original + 1.0;
double difference = modified - original; // 0.0, không phải 1.0
~~~

Giá trị `modified` đã bằng `original` sau phép cộng, nên phép trừ không thể “tìm lại” thông tin 1.0 đã mất. Thay đổi sang `double` từ `float` có thể giảm sai số nhưng không loại bỏ tính chất này.

### 4.3. Phép cộng không kết hợp tuyệt đối

Trong đại số thực, `(a + b) + c = a + (b + c)`. Với dấu phẩy động, mỗi phép `+` có thể làm tròn, nên hai cách đặt ngoặc có thể khác:

~~~java
double left = (1e16 + -1e16) + 1.0;    // 1.0
double right = 1e16 + (-1e16 + 1.0);  // 0.0
~~~

Phép cộng trong ngoặc `-1e16 + 1.0` mất số 1 nhỏ; còn `1e16 + -1e16` cho 0. Đây là lý do thứ tự cộng nhiều phần tử ảnh hưởng độ chính xác; không được tự do biến đổi thứ tự phép tính dấu phẩy động như khi biến đổi biểu thức đại số trên số thực chính xác.

## 5. Nhân `*`: kết quả có thể tràn ra vô cực hoặc hụt về 0

Phép nhân hai giá trị hữu hạn có thể cho tích toán học lớn hơn mọi số hữu hạn biểu diễn được trong kiểu kết quả: **overflow dấu phẩy động**. Trong trường hợp đó, kết quả có thể là `+Infinity` hoặc `-Infinity`, tùy dấu. Khác phép nhân số nguyên Java, phép nhân dấu phẩy động **không cuốn vòng về giá trị âm có mẫu bit bù hai**.

~~~java
double overflow = 1e308 * 10.0; // Infinity
~~~

Một phép nhân (hoặc chia) cũng có thể tạo số khác 0 nhưng quá nhỏ để biểu diễn, dẫn đến **underflow**, kết quả subnormal hoặc bị làm tròn thành `+0.0`/`-0.0`.

~~~java
double underflow = Double.MIN_VALUE / 2.0; // 0.0
~~~

Ở đây `Double.MIN_VALUE` chính là đơn vị số dương subnormal nhỏ nhất; chia đôi không tạo số dương `double` khác 0 nào biểu diễn được, nên kết quả được làm tròn về `0.0`.

Không phải mọi phép nhân số rất lớn đều cho Infinity, cũng không phải mọi số rất nhỏ đều tự động về 0: các số subnormal vẫn có thể lưu những giá trị hữu hạn khác 0 gần sát 0.

## 6. Chia `/`: làm tròn, số chia 0, Infinity và NaN

Với toán hạng dấu phẩy động, `/` tính thương và làm tròn về biểu diễn được. Phép chia không hết trong nhị phân thường tạo kết quả gần đúng, tương tự `1.0 / 10.0`.

Điểm khác biệt lớn với **chia nguyên**: phép chia dấu phẩy động cho 0 **không ném `ArithmeticException`**. Nó tuân theo quy tắc IEEE 754:

| Phép tính `double` | Kết quả | Giải thích |
|---|---|---|
| `1.0 / 0.0` | `Infinity` | Giá trị dương chia cho +0 |
| `1.0 / -0.0` | `-Infinity` | Giá trị dương chia cho -0 |
| `0.0 / 0.0` | `NaN` | Dạng không xác định |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` | Thương tiến gần 0 và có dấu dương |
| `Double.MIN_VALUE / 2.0` | `0.0` | Underflow |
| `-7.0 / 2.0` | `-3.5` | Có phần thập phân vì chia dấu phẩy động |

Trong Java:

~~~java
int integerQuotient = 7 / 2;    // 3: chia nguyên, bỏ phần lẻ
double floatingQuotient = 7.0 / 2; // 3.5
double castFirst = (double) 7 / 2; // 3.5
double castTooLate = (double) (7 / 2); // 3.0
~~~

Đây là đoạn minh họa. Khi cả hai toán hạng là số nguyên, `7 / 2` đã hoàn thành phép chia nguyên **trước khi cast kết quả** sang `double`. Muốn có phép chia dấu phẩy động phải có ít nhất một toán hạng `float` hoặc `double` (hoặc ép kiểu trước khi tính).

`NaN` không bằng chính nó theo `==`. Hãy dùng `Double.isNaN(result)`, `Float.isNaN(result)` để nhận diện, và `Double.isFinite`/`Float.isFinite` khi chỉ chấp nhận số hữu hạn.

## 7. Số 0 có dấu và phép toán trên giá trị đặc biệt

Cả `float` lẫn `double` phân biệt về mặt biểu diễn `+0.0` và `-0.0`, dù phép so sánh số học `0.0 == -0.0` cho `true`.

- `1.0 / 0.0` là `Infinity`.
- `1.0 / -0.0` là `-Infinity`.
- Phủ định `-0.0` bằng toán tử một ngôi đổi dấu thành `+0.0`.
- Cộng/trừ số 0 có dấu tuân theo quy tắc của dấu phẩy động; không giả định mọi phép tính trên 0 giữ nguyên dấu bit.
- `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` cho `NaN`; `0.0 * Double.POSITIVE_INFINITY` cũng cho `NaN`.

Nếu có `NaN` trong phép toán số học thông thường, kết quả thường tiếp tục là `NaN`. Phần lớn so sánh thứ tự với `NaN` (`<`, `<=`, `>`, `>=`) và so sánh bằng `==` đều là `false`; `NaN != NaN` là `true`.

**Đừng dùng điều kiện `result != Double.NaN` để kiểm tra hợp lệ:** điều kiện này luôn `true` khi phép so sánh số thông thường chứa NaN. Dùng `Double.isNaN` hoặc `Double.isFinite` tùy yêu cầu.

## 8. Kiểu biểu thức ảnh hưởng độ chính xác trước khi gán

`float` và `double` tham gia các quy tắc **binary numeric promotion** của Java:

- Nếu một trong hai toán hạng là `double`, phép tính thực hiện ở `double`.
- Nếu không có `double` mà có `float`, phép tính thực hiện ở `float`.
- Với hai toán hạng `int` hoặc `long`, phép tính **không tự trở thành dấu phẩy động** chỉ vì biến nhận kết quả là `double`.

Ví dụ:

~~~java
float f = 0.1f;
double d = 0.2;
double mixed = f + d;      // kiểu double, nhưng f đã được làm tròn dưới kiểu float
double simple = 1f + 1d;   // 2.0

int a = 7;
int b = 2;
double wrong = a / b;         // 3.0: chia int trước rồi chuyển thành double
double correct = (double) a / b; // 3.5
~~~

Đây là đoạn minh họa. Nâng `float` lên `double` không tái tạo phần chữ số chính xác đã mất trong `float` trước đó. Thứ tự chuyển kiểu quan trọng giống như thứ tự tính toán.

Với các biểu thức liên quan literal, `0.1f` là literal `float`, còn `0.1` là literal `double`. Không nên viết `float x = 0.1;` vì gán literal `double` sang biến `float` như vậy thường bị lỗi kiểu; dùng `0.1f` hoặc cast rõ ràng.

## 9. Ví dụ Java 17+: thấy phép làm tròn và kiểu kết quả

Tạo tệp `FloatingArithmeticDemo.java`:

~~~java
public class FloatingArithmeticDemo {
    public static void main(String[] args) {
        double sum = 0.1 + 0.2;

        System.out.println("sum=" + sum);
        System.out.println("equal03=" + (sum == 0.3));
        System.out.println("sumHex=" + Double.toHexString(sum));
        System.out.println("literal03Hex="
                + Double.toHexString(0.3));

        double large = 1e16;
        System.out.println("lostOne=" + ((large + 1.0) - large));
        System.out.println("assocLeft=" + ((large + -large) + 1.0));
        System.out.println("assocRight=" + (large + (-large + 1.0)));

        System.out.println("intDivision=" + (7 / 2));
        System.out.println("doubleDivision=" + (7.0 / 2));
        System.out.println("castTooLate=" + (double) (7 / 2));
        System.out.println("floatSum=" + (0.1f + 0.2f));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac FloatingArithmeticDemo.java
java FloatingArithmeticDemo
~~~

Đầu ra:

~~~text
sum=0.30000000000000004
equal03=false
sumHex=0x1.3333333333334p-2
literal03Hex=0x1.3333333333333p-2
lostOne=0.0
assocLeft=1.0
assocRight=0.0
intDivision=3
doubleDivision=3.5
castTooLate=3.0
floatSum=0.3
~~~

`Double.toHexString` thể hiện biểu diễn theo lũy thừa nhị phân của giá trị `double`. Hai dòng `sumHex` và `literal03Hex` khác nhau **1 ULP tại cỡ đó**: tổng sau làm tròn có bit cuối khác với literal `0.3`.

Dòng `floatSum=0.3` chỉ là dạng chuỗi thập phân Java chọn khi in giá trị `float`; nó không chứng minh `0.1f` và `0.2f` đã là các phân số thập phân chính xác.

## 10. Ví dụ Java 17+: ULP, làm tròn tại nửa khoảng và giới hạn số nguyên chính xác

Tạo tệp `FloatingRoundingDemo.java`:

~~~java
public class FloatingRoundingDemo {
    public static void main(String[] args) {
        double one = 1.0;
        double gap = Math.ulp(one);
        double halfGap = gap / 2.0;

        System.out.println("ulpAtOne=" + gap);
        System.out.println("halfUlpAdded=" + (one + halfGap));
        System.out.println("nextUp=" + Math.nextUp(one));

        float largeFloat = 16_777_216f; // 2^24
        System.out.println("floatBefore=" + largeFloat);
        System.out.println("floatPlusOne=" + (largeFloat + 1.0f));
        System.out.println("floatPlusTwo=" + (largeFloat + 2.0f));

        System.out.println("doubleRoundTie=" + Math.rint(2.5));
        System.out.println("mathRoundPositive=" + Math.round(2.5));
        System.out.println("mathRoundNegative=" + Math.round(-2.5));
    }
}
~~~

~~~bash
javac FloatingRoundingDemo.java
java FloatingRoundingDemo
~~~

Đầu ra:

~~~text
ulpAtOne=2.220446049250313E-16
halfUlpAdded=1.0
nextUp=1.0000000000000002
floatBefore=1.6777216E7
floatPlusOne=1.6777216E7
floatPlusTwo=1.6777218E7
doubleRoundTie=2.0
mathRoundPositive=3
mathRoundNegative=-2
~~~

Ở `float`, `2^24` là 16.777.216; khoảng cách đến số `float` lớn hơn kế tiếp là 2. Thêm 1 nằm đúng giữa hai giá trị biểu diễn được, nên làm tròn về số có bit cuối chẵn: **vẫn là 16.777.216**. Thêm 2 đạt số có thể biểu diễn chính xác: **16.777.218**.

Ba dòng cuối **không mô tả phép làm tròn của mỗi toán tử số học**, mà cho thấy các API làm tròn tường minh trong `Math` có quy tắc riêng:

- `Math.rint(2.5)` trả `double 2.0` theo *nearest, ties to even*.
- `Math.round(2.5)` trả `long 3` (overload nhận `double`).
- `Math.round(-2.5)` trả `long -2`.

Với các giá trị hữu hạn thông thường, `Math.round(x)` làm tròn tới số nguyên gần nhất, trường hợp chính giữa chọn hướng **dương vô cùng**. Đừng đồng nhất nó với “round-to-nearest ties-to-even” của `+`, `-`, `*` và `/`.

## 11. Ví dụ Java 17+: overflow, underflow, Infinity và NaN

Tạo tệp `FloatingSpecialValuesDemo.java`:

~~~java
public class FloatingSpecialValuesDemo {
    public static void main(String[] args) {
        double overflow = 1e308 * 10.0;
        double underflow = Double.MIN_VALUE / 2.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = 1.0 / -0.0;
        double notANumber = 0.0 / 0.0;

        System.out.println("overflow=" + overflow);
        System.out.println("underflow=" + underflow);
        System.out.println("positiveInfinity=" + positiveInfinity);
        System.out.println("negativeInfinity=" + negativeInfinity);
        System.out.println("notANumber=" + notANumber);
        System.out.println("finiteOverflow=" + Double.isFinite(overflow));
        System.out.println("isNaN=" + Double.isNaN(notANumber));
        System.out.println("nanEqualsSelf=" + (notANumber == notANumber));
        System.out.println("zerosEqual=" + (0.0 == -0.0));
    }
}
~~~

~~~bash
javac FloatingSpecialValuesDemo.java
java FloatingSpecialValuesDemo
~~~

Đầu ra:

~~~text
overflow=Infinity
underflow=0.0
positiveInfinity=Infinity
negativeInfinity=-Infinity
notANumber=NaN
finiteOverflow=false
isNaN=true
nanEqualsSelf=false
zerosEqual=true
~~~

Những kết quả trên là **giá trị dấu phẩy động đặc biệt theo đặc tả**, không phải ngoại lệ Java. Nếu chương trình không được phép có NaN hoặc vô cực, cần **kiểm tra** sau khi tính hoặc kiểm tra đầu vào và điều kiện miền giá trị trước phép toán.

Lưu ý: khi xử lý dữ liệu cần lưu lâu dài hoặc chuyển qua JSON, giá trị `NaN`/`Infinity` có thể không được định dạng trao đổi dữ liệu chấp nhận. Đừng mặc định mọi serializer đều xử lý chúng theo một cách.

## 12. Các phép toán cơ bản có thể làm tròn *ở mỗi bước*

Hãy xét:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double first = (a + b) + c; // 1.0
double second = a + (b + c); // 0.0
~~~

Cả hai biểu thức giống nhau nếu xem `a`, `b`, `c` là số thực với đại số chính xác, nhưng **khác trong IEEE 754 binary64** vì kết quả của `b + c` không lưu được phần chênh lệch `1.0`. Vì vậy:

- Không được giả định phép cộng dấu phẩy động có tính kết hợp.
- Phép nhân và chia có thể làm tròn; gộp/đổi thứ tự phép tính có thể thay đổi sai số và thời điểm overflow/underflow.
- Khi tính tổng nhiều số chênh lệch bậc lớn, cân nhắc thuật toán cộng có bù (*compensated summation*, ví dụ Kahan) hoặc thay đổi thứ tự cộng khi bài toán và yêu cầu tái lập cho phép.
- Khi cần phép nhân-cộng với **một lần làm tròn** thay vì nhân rồi cộng làm tròn riêng, Java cung cấp `Math.fma(a, b, c)`: tính gần đúng phép toán `a * b + c` theo ngữ nghĩa hợp nhất (*fused multiply-add*). Nó hữu ích cho một số thuật toán số, nhưng không làm cho mọi dữ liệu nhị phân trở nên chính xác tuyệt đối.

`Math.fma` không phải toán tử `*` rồi `+` đơn thuần: mục đích của API là làm tròn **một lần sau kết quả nhân-cộng kết hợp**, thay vì hai lần cho hai phép riêng lẻ.

## 13. Phân biệt làm tròn biểu diễn với làm tròn chủ động

Có ít nhất **ba việc** thường bị gọi chung là “làm tròn”:

| Mục tiêu | Cơ chế | Ví dụ |
|---|---|---|
| Lưu kết quả phép cộng/trừ/nhân/chia vào `float`/`double` | Làm tròn IEEE 754 về giá trị **biểu diễn được** | `1.0 + ulp(1.0)/2` có thể vẫn là `1.0` |
| Làm tròn số dấu phẩy động về giá trị nguyên hoặc giá trị nguyên dưới dạng `double` | `Math.round`, `Math.rint`, `Math.floor`, `Math.ceil` | `Math.round(2.5) == 3L` |
| Làm tròn số thập phân đến số chữ số theo quy tắc nghiệp vụ | `BigDecimal.setScale` cùng `RoundingMode` | Số tiền hai chữ số thập phân |

**Không nhầm một số được in ra có hai chữ số thập phân với kết quả được lưu chính xác đến hai chữ số.** `System.out.printf("%.2f", value)` chỉ định dạng hiển thị; biến `value` vẫn là số `double` cũ.

Trong một số ứng dụng (giá, thuế, thanh toán), cần số thập phân chính xác và quy tắc làm tròn theo nghiệp vụ. `BigDecimal` thích hợp hơn với điều kiện **khởi tạo từ chuỗi thập phân hoặc `BigDecimal.valueOf` phù hợp với nguồn dữ liệu**, chọn `RoundingMode` rõ ràng, và không chuyển kết quả qua `double` ở các bước cần chính xác.

### Ví dụ tiền tệ: dùng thập phân từ nguồn

Tạo tệp `DecimalVsBinaryDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalVsBinaryDemo {
    public static void main(String[] args) {
        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum =
                new BigDecimal("0.1").add(new BigDecimal("0.2"));

        System.out.println("binarySum=" + binarySum);
        System.out.println("decimalSum=" + decimalSum);
        System.out.println("money="
                + decimalSum.setScale(2, RoundingMode.HALF_UP));
        System.out.println("formattedBinary="
                + String.format(java.util.Locale.ROOT,
                        "%.2f", binarySum));
    }
}
~~~

~~~bash
javac DecimalVsBinaryDemo.java
java DecimalVsBinaryDemo
~~~

Đầu ra:

~~~text
binarySum=0.30000000000000004
decimalSum=0.3
money=0.30
formattedBinary=0.30
~~~

Lệnh định dạng dòng cuối **không biến** `binarySum` thành số thập phân chính xác; đó chỉ là chuỗi để trình bày. Dòng `decimalSum` là kết quả phép cộng số thập phân chính xác của hai `BigDecimal` được tạo từ chuỗi. Tránh `new BigDecimal(0.1)` nếu mục tiêu là chính xác theo giá trị thập phân người dùng gõ vào, vì constructor nhận `double` bảo tồn chính xác giá trị nhị phân gần đúng của `0.1`.

## 14. So sánh kết quả gần đúng và kiểm tra điều kiện biên

Với các phép tính `float`/`double`, đừng dùng `==` để hỏi “hai kết quả toán học gần nhau hay không” khi chúng đi qua những chuỗi phép tính khác nhau và sai số làm tròn có thể tích lũy.

Ví dụ, với các giá trị hữu hạn nhỏ gần `0.3`:

~~~java
double observed = 0.1 + 0.2;
double expected = 0.3;
boolean close = Math.abs(observed - expected) <= 1e-12;
~~~

`close` bằng `true` ở đây. Đây là **đoạn minh họa**, không phải giải pháp tổng quát cho mọi phép so sánh số. Một ngưỡng tuyệt đối `1e-12` có thể quá rộng với đại lượng cực nhỏ hoặc quá hẹp với đại lượng lớn.

Khi thiết kế phép so sánh gần bằng, nên xem xét:

1. **Đơn vị và mức sai số chấp nhận được của nghiệp vụ** (độ, mét, giây, tiền...).
2. Sai số **tuyệt đối** và đôi khi cả sai số **tương đối**, đặc biệt khi giá trị thay đổi nhiều bậc độ lớn.
3. Trường hợp `NaN`, `Infinity` và số 0 có dấu — phép trừ và `Math.abs` không giải quyết mọi trường hợp.
4. Cần kết quả xác định theo bit hay chấp nhận sai số: thuật toán, thứ tự phép tính và dữ liệu đầu vào phải được quy định phù hợp.

Trong mã cần kiểm tra tính hữu hạn trước khi sử dụng số làm chỉ số, kích thước, tỷ lệ hoặc giá trị lưu trữ:

~~~java
if (!Double.isFinite(observed)) {
    throw new IllegalArgumentException("Kết quả không hữu hạn");
}
~~~

Đây là đoạn mã minh họa. `Double.isFinite` trả `false` cho `NaN` và `+/-Infinity`, nhưng **không** đánh giá tính chính xác hoặc tính hợp lệ nghiệp vụ của một giá trị hữu hạn.

## 15. Những lỗi thường gặp

| Nhận định | Giải thích chính xác |
|---|---|
| “`0.1 + 0.2` phải bằng đúng `0.3` vì toàn số thập phân.” | Các literal `double` là xấp xỉ nhị phân; kết quả sau làm tròn có thể khác bit. |
| “`double` không có sai số vì dùng 64 bit.” | `double` có 53 bit độ chính xác phần định trị; nhiều phân số không biểu diễn được. |
| “Chỉ phép chia mới làm tròn.” | `+`, `-`, `*`, `/` đều có thể làm tròn. |
| “Đổi thứ tự phép cộng không thay đổi kết quả.” | Làm tròn ở từng bước khiến phép cộng dấu phẩy động không kết hợp tuyệt đối. |
| “`double huge + 1` luôn lớn hơn `huge`.” | Khi `huge` đủ lớn, 1 có thể nhỏ hơn nửa khoảng ULP. |
| “Phép chia `double` cho 0 ném `ArithmeticException`.” | Thường trả Infinity hoặc NaN; chia nguyên cho 0 mới ném lỗi. |
| “Overflow số thực cuốn vòng như `int`.” | Kết quả có thể là Infinity, không phải wraparound nguyên. |
| “`Double.MIN_VALUE` là số âm bé nhất.” | Nó là **số dương subnormal nhỏ nhất** lớn hơn 0. |
| “`Math.round` dùng cùng quy tắc tie-even của toán tử `+`.” | `Math.round` có quy tắc làm tròn riêng; `Math.rint` dùng ties-to-even cho kết quả `double`. |
| “In `%.2f` thì số đã thành số tiền hai chữ số chính xác.” | Đó chỉ là định dạng; muốn nghiệp vụ thập phân chính xác, dùng `BigDecimal` đúng cách. |
| “Gán phép `int / int` sang biến `double` cho ra thương thực.” | `int / int` tính chia nguyên trước; phải chuyển toán hạng trước phép chia. |

## 16. Checklist khi giải bài toán số thực

1. **Dữ liệu thuộc miền nào?** Số nguyên đếm, đại lượng đo gần đúng hay số thập phân chính xác?
2. **Chọn `float` hay `double`:** cân nhắc độ chính xác, phạm vi và yêu cầu giao thức.
3. **Xác định kiểu trước mỗi phép tính:** `int / int` không tự thành chia thực; `float` ghép với `double` có thể mang sai số từ toán hạng `float`.
4. **Xem xét sai số khi phép toán diễn ra:** nhất là cộng số chênh lệch bậc lớn, trừ hai số gần nhau và phép nhân/chia gần giới hạn.
5. **Kiểm tra giá trị đặc biệt:** dùng `Double.isFinite`, `Double.isNaN` khi bài toán không chấp nhận Infinity/NaN.
6. **Tách làm tròn biểu diễn khỏi làm tròn nghiệp vụ:** `Math.round`, `Math.rint`, `BigDecimal.setScale` là các công cụ khác nhau.
7. **Kiểm thử biên:** `0.1 + 0.2`, nửa ULP, `Double.MIN_VALUE / 2`, `Double.MAX_VALUE * 2`, chia cho `+0.0`/`-0.0` và các phép tính dễ mất chữ số.
8. **Giữ khả năng tái lập:** ghi rõ trình tự tính và đơn vị; tránh biến đổi biểu thức theo các đẳng thức đại số thực mà không đánh giá ảnh hưởng tới làm tròn.

## 17. Bài tập tự kiểm tra

1. Vì sao `0.1 + 0.2 == 0.3` là `false` trong `double`?
2. Tại sao `1e16 + 1.0` vẫn có thể bằng `1e16`?
3. `Math.ulp(1.0)` biểu thị đại lượng gì, và vì sao cộng nửa khoảng này với `1.0` có thể không đổi kết quả?
4. `(a + b) + c` có luôn bằng `a + (b + c)` đối với `double` không? Cho ví dụ.
5. `1.0 / 0.0`, `1.0 / -0.0` và `0.0 / 0.0` có kết quả gì? Có ném `ArithmeticException` không?
6. `double x = 7 / 2;` cho giá trị nào? Cách sửa để nhận `3.5`?
7. Vì sao phép nhân `1e308 * 10.0` có thể trả Infinity, trong khi `Double.MIN_VALUE / 2.0` trả `0.0`?
8. `Math.round(2.5)` khác `Math.rint(2.5)` thế nào?
9. Vì sao `String.format("%.2f", 0.1 + 0.2)` không giải quyết độ chính xác của dữ liệu tiền?
10. Nếu cần cộng hai giá trị thập phân `0.1` và `0.2` chính xác theo nghiệp vụ, nên chọn cách biểu diễn nào?

**Gợi ý đáp án:** (1) Các giá trị nhị phân được làm tròn khác nhau, tổng và literal `0.3` không cùng bit. (2) ULP gần `1e16` lớn hơn mức thay đổi 1. (3) Khoảng đơn vị tại vị trí cuối; tie-even có thể chọn `1.0`. (4) Không, ví dụ `(1e16 + -1e16) + 1` khác `1e16 + (-1e16 + 1)`. (5) `Infinity`, `-Infinity` và `NaN`; không ném lỗi chia thực. (6) `3.0`, dùng `7.0 / 2` hoặc ép trước phép chia. (7) Overflow và underflow theo miền giá trị biểu diễn được. (8) `3L` so với `2.0`. (9) Chỉ làm tròn chuỗi hiển thị, không thay dữ liệu nguồn. (10) `BigDecimal` khởi tạo từ chuỗi thập phân phù hợp.

**Ghi nhớ:** Java làm tròn kết quả `float`/`double` của **cộng, trừ, nhân, chia** về giá trị nhị phân biểu diễn được, theo quy tắc IEEE 754. Sai số có thể xuất hiện **từ lúc ghi literal** và tiếp tục sau **mỗi phép tính**. Đừng nhầm cơ chế đó với làm tròn về số nguyên, làm tròn để trình bày, hoặc số học thập phân chính xác theo nghiệp vụ.