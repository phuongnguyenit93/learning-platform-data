# Kiểu nguyên thủy, literal và giới hạn biểu diễn

Trong Java 27, kiểu nguyên thủy (primitive type) xác định loại giá trị mà biến có thể lưu, các phép toán có thể thực hiện và miền giá trị mà chương trình có thể biểu diễn. Literal là cách viết trực tiếp một giá trị trong mã nguồn, chẳng hạn số nguyên, số thực, ký tự hoặc giá trị logic. Muốn viết biểu thức chính xác, cần hiểu cả kiểu của literal lẫn cách kiểu dữ liệu biểu diễn giá trị bên trong.

Java có tám kiểu nguyên thủy: `byte`, `short`, `int`, `long`, `char`, `float`, `double` và `boolean`. Các quy tắc dưới đây là quy tắc của ngôn ngữ Java SE 27, được mô tả trong Java Language Specification (JLS). Đây là kiến thức nền tảng vẫn đang áp dụng trong Java 27; bài không dựa vào cú pháp hay API đã bị loại bỏ.

## 1. Kiểu nguyên thủy là gì?

Java là ngôn ngữ định kiểu tĩnh. Kiểu của biến và biểu thức được xác định tại thời điểm biên dịch. Trình biên dịch dùng thông tin kiểu để kiểm tra phép gán, lựa chọn phép toán, thực hiện chuyển đổi và phát hiện nhiều lỗi trước khi chương trình chạy.

Kiểu nguyên thủy là các kiểu được định nghĩa sẵn trong ngôn ngữ. Một biến primitive chứa trực tiếp một giá trị thuộc kiểu đó. Chúng được chia thành ba nhóm:

- **Kiểu số nguyên:** `byte`, `short`, `int`, `long` và `char`.
- **Kiểu dấu phẩy động:** `float` và `double`.
- **Kiểu logic:** `boolean`.

`char` thuộc nhóm kiểu số nguyên theo đặc tả, dù mục đích sử dụng thường gặp là lưu một đơn vị mã UTF-16. `boolean` là kiểu nguyên thủy nhưng không phải kiểu số và không tham gia chuyển đổi số học.

Các kiểu tham chiếu như `String`, mảng, class và record không phải kiểu nguyên thủy. Một số lớp bao (wrapper) tương ứng với primitive như `Integer`, `Long`, `Double` và `Character` là kiểu tham chiếu. Chúng có thể mang giá trị `null`, có phương thức và có thể được dùng làm tham số kiểu generic; primitive thì không.

## 2. Tám kiểu nguyên thủy và miền giá trị

### 2.1. Bảng tổng hợp

| Kiểu | Kích thước giá trị | Miền giá trị | Công dụng thường gặp |
|---|---:|---|---|
| `byte` | 8 bit | -128 đến 127 | Dữ liệu nhị phân, buffer, dữ liệu có miền nhỏ |
| `short` | 16 bit | -32.768 đến 32.767 | Dữ liệu số nguyên có miền nhỏ khi giao thức hoặc định dạng yêu cầu |
| `int` | 32 bit | -2.147.483.648 đến 2.147.483.647 | Số nguyên mặc định, chỉ số, bộ đếm, số lượng |
| `long` | 64 bit | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Timestamp, ID số, bộ đếm lớn |
| `char` | 16 bit | 0 đến 65.535 | Một code unit UTF-16 |
| `float` | 32 bit IEEE 754 | Xấp xỉ ±3,4028235 × 10³⁸ với độ chính xác khoảng 7 chữ số thập phân | Tính toán cần tiết kiệm bộ nhớ và chấp nhận độ chính xác đơn |
| `double` | 64 bit IEEE 754 | Xấp xỉ ±1,7976931348623157 × 10³⁰⁸ với độ chính xác khoảng 15–16 chữ số thập phân | Tính toán dấu phẩy động thông dụng |
| `boolean` | Do JVM triển khai quyết định | `true` hoặc `false` | Điều kiện, trạng thái đúng/sai |

Các kích thước 8/16/32/64 bit của kiểu số nguyên và định dạng binary32/binary64 của kiểu dấu phẩy động là đặc điểm của kiểu trong đặc tả. Riêng kích thước lưu trữ vật lý của `boolean` hoặc cách JVM bố trí một field không được suy ra từ bảng này.

### 2.2. Kiểu số nguyên có dấu

`byte`, `short`, `int` và `long` là số nguyên có dấu theo biểu diễn bù hai (two's complement). Với kiểu có n bit, miền giá trị là:

\[
-2^{n-1} \le x \le 2^{n-1}-1
\]

Vì một bit được dùng cho dấu theo biểu diễn bù hai, miền âm có thêm một giá trị so với miền dương. Ví dụ `byte` có 256 giá trị: từ -128 đến 127.

`int` là lựa chọn mặc định phù hợp cho phần lớn phép tính số nguyên. Chỉ chuyển sang `long` khi miền giá trị có thể vượt giới hạn của `int` hoặc khi API/giao thức yêu cầu kiểu 64 bit. Chọn `byte` hay `short` chỉ để tiết kiệm vài bit trong một biến cục bộ thường không đem lại lợi ích rõ ràng; cần chọn theo hợp đồng dữ liệu, mảng lớn hoặc định dạng lưu trữ cụ thể.

Java không cung cấp các kiểu primitive unsigned tổng quát song song với `byte`, `short`, `int` và `long`; cả bốn kiểu này đều có dấu. `char` là kiểu unsigned 16 bit nhưng có ngữ nghĩa code unit UTF-16, không phải kiểu unsigned thay thế chung cho `short`. Khi làm việc với dữ liệu unsigned trong giao thức hoặc định dạng nhị phân, có thể dùng các phương thức hỗ trợ unsigned của `Byte`, `Integer` và `Long`, hoặc dùng kiểu rộng hơn để chứa miền giá trị cần thiết. Không nên tự giả định rằng một biến `int` sẽ tự động được hiểu là số unsigned.

### 2.3. Kiểu char và Unicode

`char` là số nguyên không dấu 16 bit, có miền từ 0 đến 65.535. Giá trị của nó biểu diễn một **UTF-16 code unit**, không bảo đảm luôn tương ứng với một ký tự Unicode hoàn chỉnh mà người dùng nhìn thấy.

Unicode có các code point từ U+0000 đến U+10FFFF. Code point lớn hơn U+FFFF được mã hóa bằng một cặp UTF-16 code unit (surrogate pair). Vì thế, một ký tự như emoji có thể cần hai giá trị `char`.

Ví dụ:

~~~java
String text = "😀";

System.out.println(text.length()); // 2 code unit UTF-16
System.out.println(text.codePointCount(0, text.length())); // 1 code point
~~~

Nếu xử lý văn bản đa ngôn ngữ, không nên giả định `char` là một ký tự người dùng nhìn thấy. Khi cần duyệt theo Unicode code point, dùng các API như `String.codePoints()` hoặc các phương thức code point của lớp `Character`. `char` vẫn phù hợp khi xử lý một code unit, ký tự thuộc Basic Multilingual Plane hoặc cú pháp Java yêu cầu kiểu char.

### 2.4. Kiểu boolean

`boolean` chỉ có hai giá trị: `true` và `false`. Nó dùng cho điều kiện và trạng thái logic:

~~~java
boolean authenticated = true;
boolean canEdit = authenticated && hasPermission;
~~~

Java không tự chuyển số nguyên thành boolean hoặc ngược lại. Những biểu thức như `if (1)` hay phép gán `boolean enabled = 1;` không hợp lệ. Điều kiện trong `if`, `while` và các cấu trúc tương ứng phải là biểu thức boolean.

Không nên gán cho `boolean` một kích thước cố định theo bit khi mô tả bố trí bộ nhớ. Đặc tả quy định miền giá trị và ngữ nghĩa của kiểu, còn cách lưu trữ cụ thể phụ thuộc JVM.

### 2.5. Giá trị mặc định và khởi tạo biến

Field của class, field của object và phần tử mảng được khởi tạo bằng giá trị mặc định khi được tạo: các kiểu số nguyên nhận 0, `float` và `double` nhận dương 0, `char` nhận U+0000, `boolean` nhận `false`; biến kiểu tham chiếu nhận `null`.

Biến cục bộ trong method không tự nhận giá trị mặc định theo quy tắc này. Trước khi đọc, biến cục bộ phải được gán một giá trị trên mọi đường thực thi có thể đi tới câu lệnh đọc; compiler kiểm tra điều đó:

~~~java
class Defaults {
    int fieldCount;       // 0
    boolean enabled;      // false
    char marker;          // U+0000

    void run() {
        int localCount;
        // System.out.println(localCount); // lỗi: local variable chưa được gán
        localCount = 0;
        System.out.println(localCount);
    }
}
~~~

## 3. Kiểu dấu phẩy động và giới hạn chính xác

### 3.1. float và double theo IEEE 754

`float` tương ứng với định dạng IEEE 754 binary32, còn `double` tương ứng với binary64.

| Đặc điểm | `float` | `double` |
|---|---:|---:|
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ | 8 | 11 |
| Bit phần trị được lưu | 23 | 52 |
| Độ chính xác hiệu dụng | 24 bit nhị phân | 53 bit nhị phân |
| Độ chính xác thập phân gần đúng | 6–7 chữ số | 15–16 chữ số |
| Giá trị hữu hạn dương lớn nhất | `Float.MAX_VALUE` ≈ 3,4028235 × 10³⁸ | `Double.MAX_VALUE` ≈ 1,7976931348623157 × 10³⁰⁸ |
| Giá trị dương khác 0 nhỏ nhất | `Float.MIN_VALUE` ≈ 1,4 × 10⁻⁴⁵ | `Double.MIN_VALUE` ≈ 4,9 × 10⁻³²⁴ |

Độ chính xác hiệu dụng gồm cả bit ẩn (implicit leading bit) của số chuẩn hóa, không chỉ số bit phần trị được lưu trong trường dữ liệu.

Một điểm dễ nhầm là `Float.MIN_VALUE` và `Double.MIN_VALUE` không phải số âm nhỏ nhất hoặc giá trị hữu hạn âm nhỏ nhất. Chúng là **giá trị dương khác 0 nhỏ nhất** mà kiểu tương ứng có thể biểu diễn, bao gồm cả số subnormal. Giá trị dương chuẩn hóa nhỏ nhất lần lượt có thể tra qua `Float.MIN_NORMAL` và `Double.MIN_NORMAL`.

### 3.2. Vì sao 0.1 không được biểu diễn chính xác?

Hệ nhị phân biểu diễn phân số theo tổng các lũy thừa âm của 2. Một số phân số thập phân có biểu diễn nhị phân hữu hạn, nhưng nhiều phân số khác có chuỗi bit vô hạn tuần hoàn. Giá trị 0,1 là một ví dụ: không thể biểu diễn chính xác bằng số bit hữu hạn trong binary32 hoặc binary64.

~~~java
double a = 0.1;
double b = 0.2;
double sum = a + b;

System.out.println(sum);       // thường hiển thị 0.30000000000000004
System.out.println(sum == 0.3); // false
~~~

Vì vậy, phép tính dấu phẩy động có thể tạo ra sai số làm tròn. Đây không phải lỗi riêng của Java; đó là hệ quả của biểu diễn IEEE 754 hữu hạn.

Khi so sánh kết quả tính toán gần đúng, hãy xác định sai số cho phép (tolerance) phù hợp với miền dữ liệu:

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-12;

boolean closeEnough = Math.abs(actual - expected) < tolerance;
~~~

Không nên chọn một tolerance tùy ý cho mọi bài toán. Sai số chấp nhận được phụ thuộc đơn vị đo, độ lớn dữ liệu, số phép tính và yêu cầu nghiệp vụ. Với bài toán tài chính cần quy tắc làm tròn thập phân rõ ràng, nên cân nhắc `BigDecimal` được tạo từ chuỗi thập phân hoặc lưu số tiền theo đơn vị nhỏ nhất bằng số nguyên.

### 3.3. Infinity, NaN, số subnormal và signed zero

Ngoài các số hữu hạn, `float` và `double` còn có các giá trị đặc biệt theo IEEE 754:

- Dương vô cực và âm vô cực: `Float.POSITIVE_INFINITY`, `Float.NEGATIVE_INFINITY`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`.
- Not-a-Number (NaN): biểu diễn kết quả không phải số thực thông thường, chẳng hạn 0.0 chia cho 0.0.
- Số subnormal: giúp biểu diễn các giá trị rất nhỏ gần 0 với độ chính xác giảm dần.
- Dương 0 và âm 0: có biểu diễn bit khác nhau nhưng phép so sánh số học `+0.0 == -0.0` cho kết quả `true`.

Ví dụ:

~~~java
double positiveInfinity = 1.0 / 0.0;
double notANumber = 0.0 / 0.0;

System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(Double.isNaN(notANumber));             // true
System.out.println(notANumber == notANumber);             // false
~~~

Khác với phép chia số nguyên cho 0, phép chia dấu phẩy động cho 0 không ném `ArithmeticException` trong các trường hợp trên; kết quả có thể là vô cực hoặc NaN theo quy tắc IEEE 754. Khi nhận dữ liệu số thực từ bên ngoài, nên kiểm tra `Double.isFinite(value)` hoặc các phương thức tương ứng nếu nghiệp vụ không chấp nhận NaN và vô cực.

## 4. Literal trong Java

Literal là token biểu diễn trực tiếp một giá trị trong mã nguồn. Kiểu của literal ảnh hưởng đến kiểu biểu thức, phép toán và khả năng gán vào biến.

### 4.1. Integer literal

Java hỗ trợ bốn cơ số cho literal số nguyên:

| Cơ số | Tiền tố | Ví dụ | Giá trị thập phân |
|---|---|---|---:|
| Thập phân | Không có | `42` | 42 |
| Nhị phân | `0b` hoặc `0B` | `0b0010_1010` | 42 |
| Bát phân | `0` ở đầu | `052` | 42 |
| Thập lục phân | `0x` hoặc `0X` | `0x2A` | 42 |

Ví dụ:

~~~java
int decimal = 42;
int binary = 0b0010_1010;
int octal = 052;
int hexadecimal = 0x2A;
~~~

Lưu ý: số 0 ở đầu một integer literal có ý nghĩa chỉ cơ số bát phân. Vì thế, `052` là 42 ở hệ thập phân, không phải 52. Nếu không chủ đích dùng bát phân, hãy viết literal thập phân không có số 0 thừa ở đầu.

Literal số nguyên thập phân không có hậu tố mặc định có kiểu `int` nếu nằm trong miền cho phép. Hậu tố `L` hoặc `l` chỉ định kiểu `long`; nên dùng chữ hoa `L` để tránh nhầm với chữ số 1:

~~~java
int maxInt = 2_147_483_647;
long population = 8_100_000_000L;
~~~

Java không có hậu tố literal riêng cho `byte` hoặc `short`. Literal số nguyên thường bắt đầu ở kiểu `int` hoặc `long` rồi được chuyển đổi theo ngữ cảnh gán nếu đáp ứng quy tắc của ngôn ngữ.

### 4.2. Floating-point literal

Literal có dấu phẩy động mặc định là `double`. Dùng hậu tố `f` hoặc `F` để tạo literal kiểu `float`; hậu tố `d` hoặc `D` có thể dùng để chỉ rõ kiểu `double`.

~~~java
double defaultDouble = 3.14;
double scientific = 6.022e23;
float ratio = 0.75f;
double explicitDouble = 3.14d;
~~~

Dạng thập phân có thể sử dụng dấu chấm và số mũ `e` hoặc `E`. Dạng thập lục phân sử dụng tiền tố `0x` và số mũ `p` hoặc `P`; số mũ p biểu thị lũy thừa của 2:

~~~java
double decimal = 3.0;
double hexadecimalFloat = 0x1.8p1; // 1.5 * 2^1 = 3.0
~~~

Với literal thập lục phân dấu phẩy động, phần số mũ p là bắt buộc. Không nhầm `e` của literal thập phân với `p` của literal thập lục phân.

### 4.3. Dấu âm là toán tử, không phải một phần của literal

Trong biểu thức `-25`, dấu trừ là toán tử một ngôi áp dụng lên literal `25`. Sự phân biệt này có ý nghĩa ở giới hạn nhỏ nhất của kiểu số nguyên:

~~~java
int minInt = -2_147_483_648;
long minLong = -9_223_372_036_854_775_808L;
~~~

Đặc tả có quy tắc đặc biệt cho literal thập phân biểu diễn trị tuyệt đối của giá trị âm nhỏ nhất: literal đó chỉ được xuất hiện làm toán hạng của toán tử trừ một ngôi. Do đó, không thể dùng giá trị dương tương ứng như một literal thông thường.

### 4.4. Dấu gạch dưới trong literal

Có thể đặt dấu gạch dưới giữa các chữ số để nhóm số dài và giúp dễ đọc:

~~~java
int population = 1_234_567;
long accountNumber = 1234_5678_9012_3456L;
double measurement = 12_345.678_9;
int mask = 0b1111_0000;
~~~

Dấu gạch dưới không được đặt tùy ý. Ví dụ, không đặt ngay sau tiền tố cơ số, ở đầu hoặc cuối phần chữ số, hay sát hậu tố kiểu:

~~~java
// Hợp lệ
int valid = 1_000;
int binary = 0b1010_0011;

// Không hợp lệ
// int invalid1 = 0x_FF;
// int invalid2 = 1000_;
// int invalid3 = 1_L;
~~~

## 5. Character literal, boolean literal và null literal

### 5.1. Character literal

Character literal được đặt trong dấu nháy đơn và biểu diễn một giá trị `char`:

~~~java
char initial = 'J';
char newline = '\n';
char letterA = '\u0041';
~~~

Character literal phải biểu diễn một UTF-16 code unit. Một code point bổ sung (supplementary code point) cần hai code unit nên không thể biểu diễn trọn vẹn bằng một literal `char` đơn. Trong trường hợp đó, dùng chuỗi hoặc API xử lý code point.

### 5.2. Boolean literal

Hai boolean literal duy nhất là `true` và `false`:

~~~java
boolean active = true;
boolean expired = false;
~~~

Chúng không có hậu tố số và không thể dùng như số 1 hoặc 0.

### 5.3. null literal không phải giá trị primitive

`null` là literal cho tham chiếu rỗng và chỉ có thể gán cho biến kiểu tham chiếu. Một biến primitive không thể nhận `null`:

~~~java
Integer boxedValue = null; // hợp lệ: Integer là kiểu tham chiếu
// int primitiveValue = null; // lỗi biên dịch
~~~

Đây là một khác biệt thực tế giữa primitive và wrapper. Khi unboxing một wrapper đang chứa `null`, chương trình có thể ném `NullPointerException`:

~~~java
Integer value = null;
// int number = value; // NullPointerException khi thực thi
~~~

Nếu dữ liệu đầu vào có thể thiếu, hãy kiểm tra null trước khi unboxing hoặc giữ kiểu tham chiếu cho đến khi xác thực xong.

## 6. Chuyển đổi kiểu và numeric promotion

### 6.1. Widening primitive conversion

Widening là chuyển đổi sang kiểu số có miền biểu diễn rộng hơn theo các quy tắc của Java, thường không cần ép kiểu tường minh:

~~~java
byte small = 12;
int number = small;
long large = number;
double measurement = large;
~~~

Tuy nhiên, widening không đồng nghĩa luôn giữ nguyên chính xác mọi giá trị. Ví dụ, chuyển `long` hoặc `int` sang `float` có thể làm mất các bit có nghĩa vì `float` chỉ có 24 bit độ chính xác nhị phân. Chuyển `long` sang `double` cũng có thể mất độ chính xác khi số nguyên vượt quá miền số nguyên biểu diễn chính xác của binary64.

### 6.2. Narrowing primitive conversion

Narrowing chuyển về kiểu có miền biểu diễn nhỏ hơn và thường cần ép kiểu tường minh. Kết quả có thể mất dữ liệu:

~~~java
int source = 130;
byte result = (byte) source;

System.out.println(result); // -126
~~~

Trong trường hợp chuyển từ số nguyên sang kiểu số nguyên nhỏ hơn, các bit cao bị loại theo quy tắc chuyển đổi. Khi chuyển từ số dấu phẩy động sang số nguyên, phần thập phân bị cắt về phía 0; giá trị ngoài miền đích được giới hạn về min hoặc max của kiểu đích, còn NaN chuyển thành 0.

Ép kiểu chỉ làm cho phép chuyển đổi hợp lệ về mặt cú pháp. Nó không chứng minh dữ liệu nguồn nằm trong miền đích. Khi chuyển dữ liệu không tin cậy, hãy kiểm tra giới hạn trước khi cast.

### 6.3. Gán hằng số int cho byte, short hoặc char

Java cho phép một số phép gán trực tiếp từ biểu thức hằng số kiểu `int` sang `byte`, `short` hoặc `char` nếu giá trị hằng số nằm trong miền của kiểu đích:

~~~java
byte portOffset = 100; // hợp lệ: hằng số 100 nằm trong miền byte
char letterCode = 65;  // hợp lệ: hằng số 65 nằm trong miền char

int dynamicValue = 100;
// byte another = dynamicValue; // lỗi: biến int không phải hằng số compile-time
~~~

Quy tắc này không áp dụng chung cho mọi biến `int`, dù giá trị chạy thực tế của biến có thể nhỏ. Nếu muốn chuyển một biến, cần kiểm tra miền giá trị và cast rõ ràng.

### 6.4. Numeric promotion trong biểu thức

Trước khi thực hiện nhiều phép toán số học, Java áp dụng numeric promotion. Đặc biệt, các toán hạng `byte`, `short` và `char` thường được nâng lên `int`:

~~~java
byte first = 10;
byte second = 20;

// byte total = first + second; // lỗi: kết quả phép cộng có kiểu int
int total = first + second;
byte narrowed = (byte) (first + second);
~~~

Nếu một toán hạng là `long`, `float` hoặc `double`, kiểu kết quả được xác định theo các quy tắc promotion tương ứng. Điều này giải thích vì sao kiểu của kết quả biểu thức đôi khi rộng hơn kiểu của các biến tham gia.

### 6.5. Phép chia số nguyên và số dấu phẩy động

Khi cả hai toán hạng của phép chia là số nguyên, kết quả là phép chia số nguyên và phần dư thập phân bị bỏ:

~~~java
int whole = 5 / 2;       // 2
double decimal = 5 / 2.0; // 2.5
double stillWhole = 5 / 2; // phép chia int trước, kết quả 2.0
~~~

Nếu cần kết quả phân số, ít nhất một toán hạng phải được chuyển sang kiểu dấu phẩy động trước phép chia. Chỉ gán kết quả vào biến `double` không làm thay đổi kiểu phép chia đã được thực hiện.

## 7. Giới hạn biểu diễn và tràn số nguyên

### 7.1. Integer overflow

Các phép toán số nguyên của Java không tự ném ngoại lệ khi kết quả vượt miền của `int` hoặc `long`. Kết quả giữ lại các bit theo độ rộng của kiểu, tạo ra hiện tượng wrap-around:

~~~java
int max = Integer.MAX_VALUE;
int overflow = max + 1;

System.out.println(overflow); // -2147483648
~~~

Điều này có thể gây lỗi khó phát hiện trong bộ đếm, tính kích thước vùng nhớ, tính thời gian hoặc kiểm tra quyền hạn. Không nên giả định phép cộng, trừ hoặc nhân số nguyên sẽ tự báo overflow.

Nếu muốn phát hiện overflow, dùng các phương thức kiểm tra như `Math.addExact`, `Math.subtractExact` và `Math.multiplyExact`:

~~~java
int safe = Math.addExact(100, 200);

// Ném ArithmeticException nếu kết quả không biểu diễn được bằng int
int checked = Math.addExact(Integer.MAX_VALUE, 1);
~~~

Khi cần miền số nguyên lớn hơn 64 bit, dùng `BigInteger`. Đây là lớp tham chiếu hỗ trợ số nguyên độ chính xác tùy ý, không phải kiểu primitive.

### 7.2. Giới hạn của số dấu phẩy động

Số dấu phẩy động có hai loại giới hạn cần phân biệt:

1. **Giới hạn độ lớn:** giá trị hữu hạn lớn nhất và nhỏ nhất khác 0 mà định dạng có thể biểu diễn.
2. **Giới hạn độ chính xác:** số chữ số có nghĩa có thể giữ được khi biểu diễn và thực hiện phép toán.

Một số có thể nằm trong miền độ lớn nhưng vẫn không thể biểu diễn chính xác. `float` biểu diễn chính xác mọi số nguyên liên tiếp đến 2²⁴; từ mốc này, khoảng cách giữa các giá trị biểu diễn liên tiếp tăng lên 2. Tương tự, `double` biểu diễn chính xác mọi số nguyên liên tiếp đến 2⁵³; sau mốc này, khoảng cách giữa các giá trị biểu diễn liên tiếp lớn hơn 1.

Do đó, không dùng `float` hoặc `double` để lưu mã định danh, số đếm lớn hay số nguyên yêu cầu chính xác tuyệt đối. Dùng `int`/`long` nếu nằm trong miền; dùng `BigInteger` nếu vượt miền 64 bit.

## 8. Chọn kiểu dữ liệu theo yêu cầu

| Dữ liệu | Kiểu thường phù hợp | Điều cần kiểm tra |
|---|---|---|
| Số lượng, chỉ số, vòng lặp | `int` | Có thể vượt Integer.MAX_VALUE không? |
| Timestamp hoặc bộ đếm lớn | `long` | Đơn vị thời gian và nguy cơ overflow |
| Giá trị nhỏ theo định dạng nhị phân | `byte` hoặc `short` | Miền giá trị, signed/unsigned và quy tắc giao thức |
| Một UTF-16 code unit | `char` | Có cần xử lý code point ngoài BMP không? |
| Phép tính gần đúng thông thường | `double` | Sai số làm tròn và miền giá trị |
| Dữ liệu số lượng lớn cần tiết kiệm bộ nhớ | `float` | Có chấp nhận độ chính xác binary32 không? |
| Trạng thái đúng/sai | `boolean` | Không dùng 0/1 thay thế |
| Số nguyên lớn tùy ý | `BigInteger` | Chi phí bộ nhớ và hiệu năng của phép toán |
| Số thập phân cần quy tắc làm tròn | `BigDecimal` | Scale, rounding mode và cách khởi tạo từ chuỗi |

Một số nguyên tắc thực tế:

- Ưu tiên `int` cho số nguyên thông thường; dùng `long` khi miền dữ liệu hoặc API yêu cầu.
- Dùng `double` làm mặc định cho phép tính dấu phẩy động thông dụng, trừ khi có lý do rõ ràng để dùng `float`.
- Với tiền tệ, cân nhắc `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất; xác định rõ quy tắc làm tròn.
- Với văn bản Unicode, phân biệt code unit, code point và grapheme cluster. `char` chỉ đại diện một code unit UTF-16.
- Với dữ liệu từ mạng, file hoặc cơ sở dữ liệu, kiểm tra miền giá trị và quy tắc signed/unsigned trước khi chuyển kiểu.

## 9. Ví dụ tổng hợp

Ví dụ sau minh họa kiểu mặc định của literal, numeric promotion, kiểm tra overflow và cách dùng hằng số giới hạn:

~~~java
public class PrimitiveLimits {
    public static void main(String[] args) {
        int count = 42;                  // int literal
        long totalBytes = 5_000_000_000L; // long literal
        float ratio = 0.75f;             // float literal
        double average = 12.5;           // double literal
        char grade = 'A';                // char literal
        boolean available = true;        // boolean literal

        byte left = 10;
        byte right = 20;
        int sum = left + right;           // byte được nâng lên int

        System.out.println(count);
        System.out.println(totalBytes);
        System.out.println(ratio);
        System.out.println(average);
        System.out.println((int) grade);  // 65
        System.out.println(available);
        System.out.println(sum);

        try {
            int next = Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println(next);
        } catch (ArithmeticException ex) {
            System.out.println("Integer overflow detected");
        }
    }
}
~~~

Khi thử các ví dụ giới hạn, có thể dùng các hằng số trong lớp wrapper thay vì tự gõ số lớn:

~~~java
System.out.println(Byte.MIN_VALUE);
System.out.println(Byte.MAX_VALUE);
System.out.println(Integer.MIN_VALUE);
System.out.println(Integer.MAX_VALUE);
System.out.println(Long.MIN_VALUE);
System.out.println(Long.MAX_VALUE);
System.out.println(Float.MAX_VALUE);
System.out.println(Double.MAX_VALUE);
~~~

Các hằng số này giúp mã nguồn dễ đọc và giảm sai sót khi nhập giới hạn bằng tay.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `char` luôn là một ký tự Unicode hoàn chỉnh | `char` là một UTF-16 code unit; code point bổ sung cần hai code unit |
| `float` chứa mọi số có tối đa 7 chữ số thập phân chính xác | 6–7 chữ số chỉ là mức độ chính xác gần đúng; nhiều phân số thập phân không biểu diễn chính xác |
| `Double.MIN_VALUE` là số âm nhỏ nhất | Đây là số dương khác 0 nhỏ nhất của kiểu double |
| `int` overflow sẽ ném exception | Phép toán số nguyên thông thường không tự phát hiện overflow |
| Gán kết quả vào `double` làm phép chia số nguyên thành phép chia thực | Kiểu phép chia được quyết định từ toán hạng trước khi gán |
| `byte` + `byte` trả về `byte` | Numeric promotion khiến kết quả thông thường có kiểu `int` |
| Literal `3.14` là `float` | Literal dấu phẩy động mặc định là `double`; dùng `3.14f` cho float |
| `null` có thể gán cho mọi kiểu | `null` chỉ dùng cho kiểu tham chiếu |
| Primitive có thể dùng trực tiếp làm tham số generic | Generic Java dùng kiểu tham chiếu; cần wrapper như `Integer` hoặc `Long` |

## 11. Tự kiểm tra kiến thức

1. Vì sao `char` có miền 0 đến 65.535 nhưng không thể biểu diễn mọi Unicode code point trong một biến `char`?
2. Vì sao `double result = 5 / 2;` cho kết quả 2.0 thay vì 2.5?
3. Kiểu của biểu thức `byteA + byteB` là gì và tại sao?
4. `Float.MIN_VALUE` biểu thị giá trị nào?
5. Khi nào nên dùng `Math.addExact` thay cho toán tử `+`?
6. Vì sao `0.1 + 0.2 == 0.3` có thể trả về `false` với kiểu `double`?
7. Literal `42` và `42L` khác nhau ở kiểu nào?
8. Khi nào nên dùng `BigInteger` hoặc `BigDecimal` thay cho primitive?

## 12. Nguồn tham khảo

- [Java Language Specification, Java SE 27 — Chapter 3: Lexical Structure](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-3.html): cú pháp literal số nguyên, số dấu phẩy động, ký tự và boolean.
- [Java Language Specification, Java SE 27 — Chapter 4: Types, Values, and Variables](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html): các kiểu primitive, miền giá trị, số dấu phẩy động và giá trị mặc định.
- [Java Language Specification, Java SE 27 — Chapter 5: Conversions and Contexts](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html): widening, narrowing, assignment conversion và numeric promotion.
- [Java SE 27 API — Integer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Integer.html): giới hạn kiểu int, unsigned helper methods và các phép kiểm tra số nguyên.
- [Java SE 27 API — Float](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Float.html) và [Double](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Double.html): các hằng số và phương thức kiểm tra giá trị IEEE 754.
- [Java SE 27 API — BigInteger](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigInteger.html) và [BigDecimal](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html): số nguyên và số thập phân độ chính xác tùy ý.
