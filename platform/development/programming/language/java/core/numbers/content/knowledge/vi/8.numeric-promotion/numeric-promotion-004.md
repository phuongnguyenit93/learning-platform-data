# Gán biểu thức hằng trong phạm vi byte, short hoặc char trong Java

Trong Java, các phép toán số học trên `byte`, `short`, `char` thường được **nâng kiểu lên ít nhất `int`**. Kết quả của `byte + byte` là `int`, do đó thường không được gán thẳng về `byte`. Tuy nhiên, Java cho phép một ngoại lệ hữu ích: khi biểu thức bên phải là **biểu thức hằng tại thời điểm biên dịch** và giá trị vừa kiểu đích `byte`, `short` hoặc `char`, trình biên dịch có thể **thu hẹp kiểu ngầm định trong ngữ cảnh gán**.

Ví dụ:

~~~java
byte quantity = 100;      // hợp lệ, hằng int 100 nằm trong miền byte
byte total = 100 + 20;    // hợp lệ, biểu thức hằng int 120 vừa byte
short high = 32000 + 767;// hợp lệ, hằng int 32767 vừa short
char letter = 'A' + 1;    // hợp lệ, hằng int 66 chuyển sang char 'B'
~~~

Quy tắc này không có nghĩa mọi giá trị số nhỏ đều được Java tự ép kiểu. Trình biên dịch phải kiểm tra **kiểu biểu thức**, **tính chất hằng** và **miền biểu diễn**. Biết giá trị tại lúc chạy vẫn chưa đủ.

## 1. Miền của các kiểu đích

| Kiểu | Bit | Miền số nguyên | Ví dụ trong miền | Ví dụ ngoài miền |
| --- | ---: | ---: | --- | --- |
| `byte` | 8, có dấu | -128 đến 127 | -128, 0, 127 | -129, 128 |
| `short` | 16, có dấu | -32768 đến 32767 | -32768, 32767 | -32769, 32768 |
| `char` | 16, không dấu | 0 đến 65535 | 0, 65, 65535 | -1, 65536 |

Trong ngữ nghĩa văn bản, `char` là một **đơn vị mã UTF-16**, chưa chắc chứa được một ký tự Unicode hoàn chỉnh khi ký tự dùng surrogate pair. Trong chủ đề này, ta xét miền số nguyên 16 bit của `char` để hiểu cơ chế chuyển đổi.

Đối với các literal số nguyên thập phân không có hậu tố `L`, kiểu mặc định là `int` nếu giá trị có thể biểu diễn được ở `int`. Dấu âm là toán tử đơn ngôi. Các khai báo sau đều hợp lệ:

~~~java
byte minByte = -128;
byte maxByte = 127;
short minShort = -32768;
short maxShort = 32767;
char firstChar = 0;
char lastChar = 65535;
~~~

Dù biểu thức nguồn mang kiểu `int`, các giá trị đều là hằng và biểu diễn được ở kiểu đích. Trình biên dịch chấp nhận phép gán mà không đòi cast.

## 2. Quy tắc assignment conversion (JLS §5.2)

Trong **assignment context**, biểu thức có kiểu `byte`, `short`, `char` hoặc `int` và là **constant expression** có thể được thu hẹp sang `byte`, `short` hoặc `char` khi giá trị cuối cùng **biểu diễn được trong kiểu đích**.

Hãy phân tích một phép gán theo thứ tự:

1. Xác định **kiểu biểu thức nguồn**. Ví dụ `100 + 20` có kiểu `int` do binary numeric promotion.
2. Kiểm tra biểu thức có là **hằng tại thời điểm biên dịch** theo định nghĩa của ngôn ngữ hay không.
3. Xác định giá trị của **toàn bộ biểu thức**, không chỉ từng toán hạng.
4. So với miền của kiểu đích. Nếu ngoài miền, không được thu hẹp ngầm định theo ngoại lệ này.

Ví dụ cùng số 128:

~~~java
short okShort = 128;      // hợp lệ: 128 trong miền short
char okChar = 128;        // hợp lệ: 128 trong miền char
// byte badByte = 128;    // lỗi biên dịch: 128 > 127
~~~

Và số âm:

~~~java
byte low = -128;          // hợp lệ
short negative = -128;    // hợp lệ
// char badChar = -128;   // lỗi: char không lưu giá trị âm
~~~

**Giới hạn về kiểu nguồn:** ngoại lệ trên không tự áp dụng cho biểu thức kiểu `long`, `float` hoặc `double`, cho dù giá trị toán học rất nhỏ.

~~~java
// byte a = 42L;          // lỗi: literal kiểu long
// short b = 42.0;        // lỗi: literal kiểu double
// char c = 65L;          // lỗi: literal kiểu long

byte a = 42;             // hợp lệ: hằng int vừa miền byte
short b = 42;            // hợp lệ
char c = 65;             // hợp lệ: mã UTF-16 của 'A'
~~~

Không có kiểu primitive `unsigned byte` hoặc `unsigned short` trong Java. Việc `char` không dấu không đồng nghĩa có thể chuyển mọi số âm sang `char` mà giữ giá trị.

## 3. Hằng biểu thức không chỉ là literal đơn lẻ

Một **constant expression** có thể được tạo bằng literal và các toán tử được Java cho phép, cũng như tham chiếu tới những biến hằng đủ điều kiện. Java tính được kết quả trước khi chạy chương trình.

~~~java
byte sum = 20 + 30;           // 50
byte product = 6 * 7;         // 42
short shifted = 1 << 14;      // 16384
char next = 'A' + 1;          // 'B', mã số 66
byte selected = (8 > 3) ? 10 : 20; // 10
~~~

`'A' + 1` là biểu thức có kiểu `int`; tuy nhiên giá trị hằng là 66, vừa miền `char`, nên phép gán được chấp nhận. Khả năng gán này không đổi kiểu của toán tử `+`.

Trường hợp biên:

~~~java
byte edge = 127;                  // hợp lệ
// byte tooHigh = 127 + 1;        // lỗi: kết quả 128
short shortEdge = 32760 + 7;      // hợp lệ: 32767
// short tooHighShort = 32760 + 8; // lỗi: 32768
char charEdge = 65535;            // hợp lệ
// char tooHighChar = 65535 + 1;   // lỗi: 65536
// char negativeChar = 'A' - 66;   // lỗi: -1
~~~

Hai toán hạng của `127 + 1` đều rất nhỏ, nhưng **kết quả 128** vượt giới hạn của `byte`. Với phép dịch bit cũng phải kiểm tra kết quả:

~~~java
byte flag = 1 << 6;          // 64, hợp lệ
// byte overflow = 1 << 7;   // 128, lỗi biên dịch
~~~

Kết quả của phép dịch có kiểu `int` trong cả hai dòng. Chỉ dòng thứ nhất có giá trị hằng vừa miền kiểu đích.

## 4. final và constant variable không hoàn toàn giống nhau

Một **constant variable** trong JLS là biến `final` có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng một constant expression. Với các kiểu số nguyên, tham chiếu tới constant variable có thể tham gia biểu thức hằng mới.

~~~java
final int MAX = 127;
byte maxByte = MAX;             // hợp lệ

final int BASE = 40;
byte answer = BASE + 2;        // hợp lệ: biểu thức hằng 42

final short LETTER_CODE = 65;
char letter = LETTER_CODE;     // hợp lệ: hằng short có giá trị 65

final char DOT = '.';
byte dotCode = DOT;            // hợp lệ: '.' có mã 46, vừa miền byte
~~~

Dòng `char letter = LETTER_CODE` hợp lệ vì đây là biểu thức hằng kiểu `short` có giá trị vừa `char`. Một biến `short` bình thường không được phép gán ngầm định sang `char` chỉ nhờ giá trị hiện tại.

Ngược lại:

~~~java
int mutable = 42;
// byte a = mutable;          // lỗi: mutable không phải hằng biên dịch

final int runtime = Integer.parseInt("42");
// byte b = runtime;          // lỗi: final nhưng không phải constant variable
byte b = (byte) runtime;      // cast tường minh, cần kiểm tra miền
~~~

`final` chỉ ngăn việc gán lại biến. Giá trị `runtime` phải lấy từ lời gọi phương thức, và lời gọi phương thức không thuộc các dạng constant expression được chấp nhận. Dù ai cũng biết `Integer.parseInt("42")` trả 42, trình biên dịch không dùng hiểu biết đó để áp dụng ngoại lệ thu hẹp.

Một cặp ví dụ khác:

~~~java
final int COMPILE_TIME = 100 + 20;
byte x = COMPILE_TIME;          // hợp lệ

final int RUN_TIME = Math.abs(-120);
// byte y = RUN_TIME;           // lỗi: không phải biểu thức hằng
byte y = (byte) RUN_TIME;       // hợp lệ cú pháp, cần xem giá trị
~~~

Vì thế khi gặp lỗi “possible lossy conversion”, hãy hỏi **biến có phải constant variable không** trước khi thêm cast một cách tự động.

## 5. Liên hệ với numeric promotion

Trong các phép toán số học nhị phân, `byte`, `short` và `char` thường được nâng lên ít nhất `int`. Ví dụ `byte + byte` cho kết quả kiểu `int` dù tổng thực tế vẫn rất nhỏ.

~~~java
byte left = 10;
byte right = 20;
int total = left + right;          // hợp lệ
// byte wrong = left + right;      // lỗi: int không hằng
byte explicit = (byte) (left + right); // hợp lệ cú pháp, phải xem miền
~~~

Dù bạn biết tổng bằng 30, `left` và `right` là các biến thường, nên `left + right` không phải constant expression.

So sánh:

~~~java
final byte left = 10;
final byte right = 20;
byte sum = left + right;          // hợp lệ vì biểu thức hằng int bằng 30
~~~

**Kiểu của `left + right` vẫn là `int`.** Trình biên dịch cho phép thu hẹp tại phép gán chỉ vì kết quả hằng 30 vừa `byte`; không có quy tắc riêng khiến `final byte + final byte` trở thành `byte`.

Một chỗ rất dễ nhầm là **compound assignment**:

~~~java
byte count = 120;
// count = count + 10;           // lỗi: int -> byte không tự thu hẹp
count += 10;                    // hợp lệ, nhưng kết quả sẽ là -126
~~~

`+=` có cơ chế chuyển đổi về kiểu vế trái mang hiệu ứng tương tự cast, ngoại trừ việc vế trái chỉ được đánh giá một lần. Vì `120 + 10 = 130` nằm ngoài miền `byte`, kết quả lưu vào `count` là -126. Quy tắc này **không phải** ngoại lệ thu hẹp hằng có kiểm tra giá trị trong miền; vì vậy `+=` có thể gây tràn mà vẫn biên dịch.

## 6. Ngữ cảnh gán không đồng nhất với truyền tham số phương thức

Ngoại lệ này áp dụng khi **khởi tạo biến, dùng phép gán hoặc khởi tạo từng phần tử mảng**. Nhưng **method invocation context** có quy tắc chuyển đổi khác: đối số hằng `int` không tự thu hẹp thành `byte` chỉ để khớp tham số phương thức.

Chương trình ví dụ lưu thành `InvocationExample.java`:

~~~java
class InvocationExample {
    static void consume(byte value) {
        System.out.println(value);
    }

    public static void main(String[] args) {
        byte local = 42;          // hợp lệ: ngữ cảnh gán
        consume(local);           // hợp lệ: byte -> byte
        consume((byte) 42);       // hợp lệ: ép kiểu rõ ràng
        // consume(42);           // lỗi: literal int không tự thành byte
    }
}
~~~

Kết luận: `byte b = 42` là cú pháp hợp lệ không có nghĩa `consume(42)` cũng hợp lệ. Với lời gọi, hãy cung cấp biểu thức có kiểu tương thích hoặc chuyển đổi tường minh phù hợp.

Trong array initializer, từng phần tử được kiểm tra theo ngữ cảnh gán:

~~~java
byte[] signedSamples = {0, 127, -128};
char[] letters = {'A', 66};
// byte[] badSamples = {128};    // lỗi biên dịch: phần tử ngoài miền byte
~~~

Phép gán phần tử 66 vào mảng `char[]` cũng dựa trên việc hằng `int` 66 vừa miền `char`.

## 7. Cast tường minh và rủi ro mất giá trị

Nếu biểu thức không phải hằng hoặc hằng vượt miền, bạn có thể viết cast để thu hẹp, nhưng cast không bảo đảm giữ nguyên giá trị toán học. Chuyển đổi hẹp số nguyên loại bỏ các bit cao; `byte` và `short` sau đó được diễn giải theo số có dấu.

~~~java
byte wrappedByte = (byte) 128;          // -128
short wrappedShort = (short) 32768;    // -32768
char wrappedChar = (char) -1;          // giá trị số 65535
~~~

Những đoạn trên **biên dịch được** nhưng giá trị đã thay đổi. Đối với số lượng, kích thước, giới hạn hoặc ID, việc wrap âm thầm có thể tạo lỗi nghiệp vụ.

Khi nguồn là `int` tính ở thời điểm chạy, hãy kiểm tra trước khi cast nếu cần giữ đúng giá trị số signed:

~~~java
static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("Ngoai mien byte: " + value);
    }
    return (byte) value;
}
~~~

Đây là **đoạn phương thức minh họa**, đặt trong một lớp Java. Với `short` kiểm tra `Short.MIN_VALUE` và `Short.MAX_VALUE`; với `char` kiểm tra 0–65535. Dữ liệu **unsigned** trong protocol là ngữ nghĩa riêng: nên giữ ở kiểu đủ rộng hoặc chuyển đổi bit theo đặc tả, không mặc định đồng nhất nó với miền signed `byte` hoặc `short`.

## 8. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `ConstantNarrowingDemo.java`:

~~~java
public class ConstantNarrowingDemo {
    static final int BASE = 40;
    static final short LETTER_CODE = 65;

    public static void main(String[] args) {
        byte literal = 127;
        byte arithmetic = 100 + 20;
        short shortMax = 32_760 + 7;
        char nextLetter = 'A' + 1;
        byte fromFinal = BASE + 2;
        char fromShort = LETTER_CODE;

        System.out.println("literal: " + literal);
        System.out.println("arithmetic: " + arithmetic);
        System.out.println("shortMax: " + shortMax);
        System.out.println("nextLetter: " + nextLetter);
        System.out.println("fromFinal: " + fromFinal);
        System.out.println("fromShort: " + fromShort);

        int runtime = Integer.parseInt("42");
        byte narrowed = checkedByte(runtime);
        System.out.println("narrowed: " + narrowed);

        byte wrapped = (byte) (127 + 1);
        System.out.println("wrapped: " + wrapped);

        byte count = 120;
        count += 10;
        System.out.println("compound: " + count);
    }

    static byte checkedByte(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("Ngoai mien byte: " + value);
        }
        return (byte) value;
    }
}
~~~

Biên dịch, chạy bằng JDK 17+:

~~~bash
javac ConstantNarrowingDemo.java
java ConstantNarrowingDemo
~~~

Kết quả chính xác:

~~~text
literal: 127
arithmetic: 120
shortMax: 32767
nextLetter: B
fromFinal: 42
fromShort: A
narrowed: 42
wrapped: -128
compound: -126
~~~

Các trường hợp cần phân biệt:

- `BASE + 2` có kiểu `int` nhưng được xem là constant expression bằng 42 bởi `BASE` là constant variable. Thu hẹp về `byte` hợp lệ.
- `Integer.parseInt("42")` được gọi ở runtime; biến `runtime` dù hiện bằng 42 vẫn không phải constant variable. Phương thức `checkedByte` kiểm tra miền rồi mới cast.
- `(byte) (127 + 1)` được cast vì 128 vượt miền `byte` và cho kết quả -128; phép gán trực tiếp `byte wrapped = 127 + 1` sẽ lỗi biên dịch.
- `count += 10` hợp lệ do luật compound assignment và wrap từ 130 về -126.

## 9. Bảng so sánh nhanh

| Đoạn mã | Hợp lệ? | Lý do |
| --- | --- | --- |
| `byte b = 127;` | Có | Hằng int 127 vừa byte |
| `byte b = 128;` | Không | Hằng 128 vượt byte |
| `short s = 32767;` | Có | Hằng vừa short |
| `short s = 32768;` | Không | Hằng vượt short |
| `char c = 65535;` | Có | Hằng vừa char |
| `char c = -1;` | Không | Char không lưu số âm |
| `byte b = 60 + 60;` | Có | Biểu thức hằng kiểu int bằng 120 |
| `byte b = 60 + 70;` | Không | Biểu thức hằng bằng 130 vượt miền |
| `byte b = 42L;` | Không | Hằng kiểu long không thuộc ngoại lệ |
| `final int n = 42; byte b = n;` | Có | n là constant variable |
| `int n = 42; byte b = n;` | Không | n không phải constant variable |
| `byte b = (byte) 128;` | Có | Cast tường minh; b bằng -128 |
| `byte b = 120; b += 10;` | Có | Compound assignment; b bằng -126 |

## 10. Tự luyện và lời giải

**Câu 1.** Vì sao `byte a = 50 + 70;` biên dịch được, còn `int x = 50; byte b = x + 70;` thì không?  
**Đáp án:** Phép cộng thứ nhất là constant expression kiểu `int` có kết quả 120 vừa miền `byte`. Phép cộng thứ hai có biến thường `x` nên không phải biểu thức hằng.

**Câu 2.** `final int X = 200; byte b = X;` có hợp lệ không?  
**Đáp án:** Không. `X` là constant variable, nhưng giá trị hằng 200 vượt `Byte.MAX_VALUE` là 127.

**Câu 3.** Vì sao `char c = 'A' + 1;` hợp lệ dù `'A' + 1` có kiểu `int`?  
**Đáp án:** Toàn biểu thức là hằng bằng 66, vừa miền `char`. Phép chuyển đổi thu hẹp ngầm định ở phép gán tạo ra `'B'`.

**Câu 4.** `final int x = Integer.parseInt("12"); short s = x;` có hợp lệ không?  
**Đáp án:** Không. `x` là `final` nhưng khởi tạo bằng lời gọi phương thức, không phải constant variable; không thể thu hẹp ngầm định từ `int` về `short`.

**Câu 5.** Phân biệt `short s = 32767 + 1;` và `short s = (short) (32767 + 1);`.  
**Đáp án:** Cách đầu báo lỗi vì hằng 32768 ngoài miền `short`; cách sau ép kiểu tường minh nên biên dịch, nhưng giá trị lưu thành -32768, không giữ được số 32768.

## 11. Ghi nhớ

- Thu hẹp biểu thức hằng từ `byte`/`short`/`char`/`int` sang `byte`, `short` hoặc `char` chỉ xảy ra trong **ngữ cảnh gán phù hợp** và khi giá trị biểu diễn được.
- Numeric promotion vẫn áp dụng: `byte + byte` thường là `int`, dù có thể gán biểu thức **hằng** vừa miền trở lại `byte`.
- `final` không tự đồng nghĩa với constant variable; phần khởi tạo phải là một constant expression.
- Truyền đối số vào phương thức, compound assignment và cast có các quy tắc khác; đặc biệt cast hoặc `+=` có thể làm mất giá trị số.
- Khi gặp lỗi “possible lossy conversion”, hãy kiểm tra **kiểu nguồn, tính hằng và miền của kết quả**, rồi mới quyết định dùng kiểu rộng hơn, đổi logic hay cast có kiểm tra.