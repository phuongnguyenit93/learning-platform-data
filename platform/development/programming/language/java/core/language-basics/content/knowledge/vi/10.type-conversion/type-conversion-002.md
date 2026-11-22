# Mở rộng và thu hẹp kiểu nguyên thủy trong Java 17+

## 1. Mục tiêu: chuyển đổi kiểu là gì?

**Chuyển đổi kiểu nguyên thủy** (*primitive type conversion*) là quá trình Java chuyển một giá trị giữa các kiểu primitive tương thích, ví dụ từ `byte` sang `int` hoặc từ `double` sang `int`.

~~~java
int count = 120;
long widened = count;       // Mở rộng: int -> long
byte narrowed = (byte) count; // Thu hẹp tường minh: int -> byte

System.out.println(widened);  // 120
System.out.println(narrowed); // 120
~~~

Có hai nhóm quan trọng:

- **Widening primitive conversion (chuyển đổi mở rộng)**: đi theo quan hệ cho phép Java chuyển tự động trong ngữ cảnh phù hợp, thường là từ kiểu có phạm vi đại diện rộng hơn. **Không đồng nghĩa luôn giữ độ chính xác số học**.
- **Narrowing primitive conversion (chuyển đổi thu hẹp)**: đi từ kiểu nguồn sang kiểu đích có thể không chứa trọn giá trị nguồn; thường cần **ép kiểu tường minh** `(TargetType)`, và có thể mất dữ liệu.

Java kiểm tra tính hợp lệ **khi biên dịch** đối với kiểu dữ liệu; nhưng phép cast hợp lệ không tự bảo đảm giá trị sau khi chuyển còn đúng nghiệp vụ.

## 2. Nhớ các kiểu primitive trước khi chuyển đổi

| Kiểu | Độ rộng | Đặc điểm |
|---|---:|---|
| `byte` | 8 bit | Số nguyên có dấu, -128 đến 127 |
| `short` | 16 bit | Số nguyên có dấu, -32768 đến 32767 |
| `char` | 16 bit | UTF-16 code unit không dấu, 0 đến 65535 |
| `int` | 32 bit | Số nguyên có dấu |
| `long` | 64 bit | Số nguyên có dấu |
| `float` | 32 bit | Số thực dấu phẩy động nhị phân, khoảng 24 bit có nghĩa |
| `double` | 64 bit | Số thực dấu phẩy động nhị phân, khoảng 53 bit có nghĩa |
| `boolean` | Theo ngữ nghĩa true/false | **Không có** chuyển đổi số học sang/từ các kiểu còn lại |

**Lưu ý:** `char` và `short` đều 16 bit nhưng không có cùng miền giá trị. `char` không âm; `short` có dấu. Vì thế Java không cho phép chuyển mở rộng trực tiếp từ `char` sang `short` hoặc ngược lại.

`String` không phải kiểu nguyên thủy. Các thao tác `Integer.parseInt("123")`, `String.valueOf(123)` là **chuyển đổi văn bản và giá trị**, không phải một widening/narrowing primitive conversion.

## 3. Các đường chuyển đổi mở rộng hợp lệ

Trong Java, những quan hệ mở rộng primitive có thể ghi nhớ bằng bảng sau:

| Kiểu nguồn | Kiểu đích mở rộng trực tiếp hợp lệ |
|---|---|
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

Không có widening từ `double` sang kiểu nào khác; và `boolean` không tham gia bảng này.

~~~java
byte small = 100;
short medium = small; // byte -> short
int count = medium;   // short -> int
long total = count;   // int -> long
double reading = total; // long -> double

char letter = 'A';
int codeUnit = letter; // char -> int: 65

System.out.println(reading);  // 100.0
System.out.println(codeUnit); // 65
~~~

Ví dụ `char` là nhánh mở rộng riêng, không nằm trong chuỗi `byte -> short -> int -> long`.

**Không cần viết cast** ở các phép gán widening trên. Viết `(long) count` cũng có thể hợp lệ, nhưng thường không cần thiết trừ khi muốn làm rõ kiểu trước một phép toán.

## 4. “Mở rộng” không bảo đảm chính xác tuyệt đối

Đây là một điểm dễ hiểu sai. Các chuyển đổi mở rộng **giữa kiểu nguyên và kiểu nguyên** trong bảng trên giữ giá trị chính xác. Tuy nhiên, khi mở rộng sang kiểu dấu phẩy động, một số giá trị lớn **không thể biểu diễn chính xác bằng significand hữu hạn**.

Ví dụ một `long` có giá trị \(2^{53}+1\):

~~~java
long exact = 9_007_199_254_740_993L;
double approximate = exact; // Widening long -> double

System.out.println(exact);               // 9007199254740993
System.out.println(approximate);         // 9.007199254740992E15
System.out.println((long) approximate);  // 9007199254740992
~~~

`long` giữ chính xác số nguyên trên, nhưng `double` chỉ có 53 bit significand hiệu dụng: giá trị được làm tròn thành \(2^{53}\), mất đơn vị cuối.

Tương tự:

~~~java
float big = 16_777_216f; // 2^24
System.out.println(big + 1f == big); // true
~~~

Ở độ lớn này, `float` không còn phân biệt được mọi bước tăng 1.

Một ví dụ khác là `float -> double`:

~~~java
float f = 0.1f;
double d = f;
System.out.println(d); // 0.10000000149011612
~~~

Chuyển `float` sang `double` **giữ chính xác giá trị nhị phân đang có trong float**, không khôi phục số thập phân `0.1` ban đầu.

**Quy tắc ứng dụng:** khi chuyển số nguyên lớn sang `float`/`double`, hãy xem xét độ chính xác yêu cầu. Nếu mọi đơn vị đếm cần được bảo toàn, giữ `long`/`int` hoặc chọn biểu diễn chính xác hơn.

## 5. Thu hẹp kiểu nguyên: cast và mất dữ liệu

Khi muốn chuyển từ một kiểu nguyên sang một kiểu nguyên nhỏ hơn, thường phải viết cast:

~~~java
int value = 130;
// byte invalid = value; // LỖI BIÊN DỊCH
byte narrowed = (byte) value;
System.out.println(narrowed); // -126
~~~

Vì `byte` chỉ biểu diễn từ -128 đến 127, nên chuyển 130 sang `byte` giữ **8 bit thấp** của kết quả theo quy tắc narrowing. Mẫu bit `1000_0010` được diễn giải thành -126 theo biểu diễn có dấu.

Tương tự:

~~~java
int value = 65_537;
char c = (char) value;
System.out.println((int) c); // 1
~~~

`char` 16 bit nhận 16 bit thấp; 65537 tương đương \(65536+1\), nên code unit sau cast có giá trị 1.

| Chuyển đổi | Input | Kết quả |
|---|---:|---:|
| `(byte) 127` | 127 | 127 |
| `(byte) 128` | 128 | -128 |
| `(byte) 130` | 130 | -126 |
| `(short) 65535` | 65535 | -1 |
| `(char) -1` | -1 | 65535 |

**Cast không tự cảnh báo tràn.** Nó chỉ yêu cầu Java thực hiện một phép chuyển kiểu hợp lệ về cú pháp. Nếu không cho phép thay đổi giá trị số học, hãy kiểm tra giới hạn trước khi cast.

## 6. Ngoại lệ: gán hằng int vừa phạm vi cho byte, short, char

Phép gán `int -> byte`, `short` hoặc `char` thường là narrowing. Tuy nhiên Java có **narrowing conversion dành riêng cho biểu thức hằng tại thời điểm biên dịch** (*constant expressions*) khi giá trị biểu diễn được trong kiểu đích.

~~~java
byte b = 127;         // Hợp lệ dù literal 127 có kiểu int
short s = 32_000;     // Hợp lệ
char c = 65;          // Hợp lệ: mã UTF-16 65
// byte wrong = 128;  // LỖI: ngoài miền byte
// char wrong2 = -1;  // LỖI: ngoài miền char
~~~

Một biến `int` bình thường **không được chuyển tự động**, kể cả khi hiện đang chứa số 127:

~~~java
int value = 127;
// byte b = value;    // Lỗi compile: int không tự thu hẹp
byte b = (byte) value; // Hợp lệ nhưng cần tự chịu trách nhiệm
~~~

Một **final constant variable** kiểu `int` được gán bằng constant expression cũng có thể được compiler xét trong ngữ cảnh gán:

~~~java
final int LIMIT = 100;
byte threshold = LIMIT; // Hợp lệ vì LIMIT là constant variable
~~~

Nhưng `final int runtime = Integer.parseInt("100");` không phải constant variable theo nghĩa này; giá trị xuất phát từ lời gọi method, nên không dùng được phép gán narrowing đặc biệt.

**Giới hạn quy tắc:** ngoại lệ trên thuộc ngữ cảnh assignment (cũng bao gồm initializer), không biến mọi lời gọi method hay biểu thức đều được phép implicit narrowing. Tránh suy từ `byte b = 127;` rằng mọi nơi đều có thể truyền một `int` bất kỳ vào tham số `byte` không cần cast.

## 7. Thu hẹp từ float/double sang số nguyên

Chuyển `float` hoặc `double` sang kiểu nguyên yêu cầu cast trong các trường hợp thông thường:

~~~java
double positive = 12.9;
double negative = -12.9;

System.out.println((int) positive); // 12
System.out.println((int) negative); // -12
~~~

Java **cắt phần thập phân về 0**, không dùng quy tắc làm tròn tới số nguyên gần nhất như `Math.round`.

Cần nhớ các trường hợp đặc biệt theo đặc tả:

| Đầu vào double | `(int)` | Giải thích |
|---|---:|---|
| `12.9` | 12 | Cắt phần thập phân |
| `-12.9` | -12 | Hướng về 0 |
| `Double.NaN` | 0 | Quy tắc NaN khi chuyển về số nguyên |
| `Double.POSITIVE_INFINITY` | 2147483647 | Bão hòa tại `Integer.MAX_VALUE` |
| `Double.NEGATIVE_INFINITY` | -2147483648 | Bão hòa tại `Integer.MIN_VALUE` |
| `1.0e30` | 2147483647 | Bão hòa khi vượt miền int |

Nếu đích là `byte` hoặc `short`, phép thu hẹp từ dấu phẩy động trước hết chuyển qua `int` rồi thu hẹp tiếp, nên có thể cho kết quả càng khó đoán nếu bạn không kiểm tra đầu vào.

Không dùng `(int) doubleValue` làm “validation”: NaN, Infinity hoặc giá trị ngoài miền **không nhất thiết ném exception**. Nếu cần dữ liệu hữu hạn, số nguyên và nằm trong khoảng xác định, phải kiểm tra từng điều kiện trước phép cast.

## 8. Thu hẹp double -> float: mất độ chính xác, overflow, underflow

~~~java
double source = 0.1;
float narrowed = (float) source;

System.out.println(narrowed);        // 0.1
System.out.println((double) narrowed); // 0.10000000149011612
~~~

Chuỗi hiển thị `0.1` là cách Java in một giá trị `float` gần `0.1`, không có nghĩa `float` lưu chính xác 1/10.

Giá trị hữu hạn `double` quá lớn khi chuyển sang `float` có thể thành **Infinity**:

~~~java
double huge = 1.0e40;
float overflow = (float) huge;
System.out.println(overflow); // Infinity
~~~

Giá trị có độ lớn quá nhỏ có thể chuyển thành zero (có dấu) hoặc một giá trị subnormal. Khi yêu cầu kết quả `float` hữu hạn và khác 0, cần validation phù hợp.

**Với float/double:** đừng đồng nhất “độ rộng ít bit hơn” với quy tắc giữ các bit thấp như chuyển `int -> byte`. Dấu phẩy động thu hẹp dùng quy tắc làm tròn/giới hạn của mô hình dấu phẩy động.

## 9. Chuyển kiểu trong biểu thức số học

Java thực hiện **numeric promotion** đối với nhiều toán tử số học. Đặc biệt, `byte`, `short` và `char` được nâng lên `int` trong phép cộng thông thường:

~~~java
byte a = 100;
byte b = 20;

// byte sum = a + b; // LỖI: a + b có kiểu int
int sum = a + b;
System.out.println(sum); // 120

char ch = 'A';
// char next = ch + 1; // LỖI: ch + 1 là int
char next = (char) (ch + 1);
System.out.println(next); // B
~~~

Với toán hạng `long`, `float` hoặc `double`, biểu thức được nâng kiểu theo quy tắc tương ứng trước khi tính.

Một bẫy quan trọng là **tràn xảy ra trước khi gán sang long**:

~~~java
int x = Integer.MAX_VALUE;
long wrong = x + 1;        // int + int tràn trước khi gán long
long correct = (long) x + 1; // Một toán hạng đã là long

System.out.println(wrong);   // -2147483648
System.out.println(correct); // 2147483648
~~~

Chỉ khai báo biến **đích** kiểu `long` không thay đổi phép cộng đã diễn ra với toán hạng `int`.

### Phép gán kết hợp có cast ngầm

~~~java
byte count = 120;
count += 10;
System.out.println(count); // -126
~~~

`count += 10` có thể biên dịch bởi ngữ nghĩa compound assignment bao gồm chuyển kiểu về kiểu của biến nhận. Nhưng:

~~~java
byte count = 120;
// count = count + 10; // LỖI: count + 10 có kiểu int
~~~

Hai cách nhìn gần giống nhau nhưng **khác kết quả compile**. Đừng dùng `+=` như cách lách kiểm tra tràn: `count += 10` vẫn mất dữ liệu số học.

## 10. Kiểm tra an toàn trước khi narrowing

Có nhiều cách tùy miền kiểu.

### Trường hợp long -> int

Java cung cấp `Math.toIntExact(long)`, trả `int` nếu vừa miền; nếu vượt miền, nó ném `ArithmeticException`:

~~~java
long big = 2_147_483_648L;

try {
    int safe = Math.toIntExact(big);
    System.out.println(safe);
} catch (ArithmeticException ex) {
    System.out.println("outside int range");
}
~~~

Đầu ra: `outside int range`.

### Trường hợp long -> byte

Không có `Math.toByteExact(long)` tương ứng trong Java 17; bạn có thể kiểm tra:

~~~java
static byte checkedByte(long value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("outside byte range");
    }
    return (byte) value;
}
~~~

### Trường hợp double -> int cần đúng số nguyên

~~~java
static int checkedWholeInt(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value >= 2147483648.0
            || value != Math.rint(value)) {
        throw new IllegalArgumentException("not a finite int");
    }
    return (int) value;
}
~~~

Ở đây chúng ta kiểm tra **hữu hạn**, **nằm trong miền int**, và **không có phần lẻ**. Cận trên dùng `2147483648.0` (2³¹) và điều kiện `>=` để tránh bẫy biểu diễn khi so sánh số thực với `Integer.MAX_VALUE`.

Nếu cần hỗ trợ chính xác theo decimal, quy tắc làm tròn cụ thể hoặc miền số lớn, hãy chọn kiểu/thuật toán phù hợp thay vì cast trực tiếp.

## 11. `boolean` không có chuyển đổi kiểu số học

Java **không cho** chuyển `boolean` thành `int` hoặc ngược lại bằng widening/narrowing:

~~~java
boolean enabled = true;
// int number = (int) enabled; // LỖI BIÊN DỊCH

int number = 1;
// boolean flag = (boolean) number; // LỖI BIÊN DỊCH
~~~

Nếu nghiệp vụ quy định `true` tương ứng với `1`, bạn phải diễn đạt quy tắc đó rõ ràng:

~~~java
boolean enabled = true;
int numericFlag = enabled ? 1 : 0;
System.out.println(numericFlag); // 1
~~~

Đây là biểu thức điều kiện sinh số nguyên theo quy tắc bạn đặt ra, **không phải** một primitive conversion từ boolean.

## 12. Ví dụ Java 17 hoàn chỉnh, runnable

Tạo đúng tệp **`PrimitiveConversionDemo.java`**:

~~~java
public final class PrimitiveConversionDemo {
    private PrimitiveConversionDemo() {}

    static byte checkedByte(long value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("outside byte range");
        }
        return (byte) value;
    }

    static int checkedWholeInt(double value) {
        if (!Double.isFinite(value)
                || value < Integer.MIN_VALUE
                || value >= 2147483648.0
                || value != Math.rint(value)) {
            throw new IllegalArgumentException("not a finite int");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        byte small = 100;
        short asShort = small;
        int asInt = small;
        long asLong = asInt;
        double asDouble = asLong;
        System.out.println("widen=" + asShort + "," + asInt
                + "," + asLong + "," + asDouble);

        char letter = 'A';
        int codeUnit = letter;
        System.out.println("char code=" + codeUnit);

        int input = 130;
        byte narrowed = (byte) input;
        System.out.println("int to byte=" + narrowed);
        System.out.println("int to char=" + (int) (char) -1);

        final int limit = 100;
        byte fromConstant = limit;
        System.out.println("constant=" + fromConstant);

        long bigInteger = 9_007_199_254_740_993L;
        double approximate = bigInteger;
        System.out.println("long original=" + bigInteger);
        System.out.println("long through double=" + (long) approximate);

        float decimalFloat = 0.1f;
        double widenedFloat = decimalFloat;
        System.out.println("float as double=" + widenedFloat);

        System.out.println("positive trunc=" + (int) 12.9);
        System.out.println("negative trunc=" + (int) -12.9);
        System.out.println("NaN to int=" + (int) Double.NaN);
        System.out.println("infinity to int="
                + (int) Double.POSITIVE_INFINITY);
        System.out.println("double to float=" + (float) 1.0e40);

        byte a = 100;
        byte b = 20;
        int sum = a + b;
        System.out.println("byte addition=" + sum);

        byte count = 120;
        count += 10;
        System.out.println("compound assignment=" + count);

        int max = Integer.MAX_VALUE;
        long wrong = max + 1;
        long right = (long) max + 1;
        System.out.println("int overflow first=" + wrong);
        System.out.println("long arithmetic=" + right);

        System.out.println("checked byte=" + checkedByte(127));
        try {
            checkedByte(128);
        } catch (IllegalArgumentException ex) {
            System.out.println("checked byte error=" + ex.getMessage());
        }

        System.out.println("checked whole int=" + checkedWholeInt(42.0));
        try {
            checkedWholeInt(42.5);
        } catch (IllegalArgumentException ex) {
            System.out.println("checked whole error=" + ex.getMessage());
        }

        try {
            Math.toIntExact(2_147_483_648L);
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact=overflow");
        }
    }
}
~~~

Yêu cầu: cài **JDK 17 trở lên**, terminal đang đứng tại thư mục chứa tệp.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveConversionDemo.java
java -cp . PrimitiveConversionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveConversionDemo.java
java -cp . PrimitiveConversionDemo
~~~

**Expected output:**

~~~text
widen=100,100,100,100.0
char code=65
int to byte=-126
int to char=65535
constant=100
long original=9007199254740993
long through double=9007199254740992
float as double=0.10000000149011612
positive trunc=12
negative trunc=-12
NaN to int=0
infinity to int=2147483647
double to float=Infinity
byte addition=120
compound assignment=-126
int overflow first=-2147483648
long arithmetic=2147483648
checked byte=127
checked byte error=outside byte range
checked whole int=42
checked whole error=not a finite int
toIntExact=overflow
~~~

**Đọc kết quả theo nhóm:**

1. `widen` và `char code` cho thấy mở rộng giữ chính xác những giá trị nhỏ.
2. `int to byte`, `int to char` cho thấy thu hẹp kiểu nguyên có thể đổi giá trị.
3. `constant` minh họa ngoại lệ gán constant variable kiểu int vừa miền byte.
4. `long through double` và `float as double` chứng minh widening không phải lúc nào cũng khôi phục độ chính xác mong muốn.
5. `positive/negative trunc`, `NaN`, `infinity` cho thấy casting dấu phẩy động về số nguyên có quy tắc đặc biệt.
6. `compound assignment` và `int overflow first` nhắc rằng phép tính có thể đã mất giá trị trước khi gán.
7. Hai hàm `checkedByte`/`checkedWholeInt` và `Math.toIntExact` thể hiện cách ngăn mất dữ liệu khi nghiệp vụ không chấp nhận.

Ví dụ không cần thư viện bên ngoài JDK, đầu ra không phụ thuộc hệ điều hành hoặc dữ liệu nhập bàn phím.

## 13. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `byte b = intVariable;` | Narrowing int -> byte không tự động | Kiểm tra miền rồi cast |
| `byte b = 128;` | Constant int không vừa miền byte | Sử dụng kiểu lớn hơn nếu cần 128 |
| `short s = charVariable;` | Không có widening char -> short | Kiểm tra miền rồi cast, hoặc dùng int |
| `char c = shortVariable;` | Short có thể âm, char không có dấu | Kiểm tra trước khi cast |
| `long x = 3_000_000_000;` | Decimal integer literal mặc định int quá giới hạn | `3_000_000_000L` |
| `float f = 0.1;` | Literal 0.1 có kiểu double | `0.1f` hoặc cast có chủ đích |
| `long result = intA + intB;` bị tràn | Phép cộng int xảy ra trước widening | Đổi ít nhất một toán hạng sang long trước |
| `byte s = a + b;` với a,b là byte | Binary numeric promotion thành int | Nhận `int`, hoặc cast có kiểm tra |
| `byte count; count += delta;` mất dữ liệu | Compound assignment thu hẹp ngầm | Tính bằng int, kiểm tra miền rồi gán |
| `(int) 12.9` cho 12 | Cast cắt phần lẻ về 0 | Nếu muốn làm tròn, dùng quy tắc/ API riêng |
| `(int) Double.NaN` cho 0 | Quy tắc chuyển đổi đặc biệt | Validation trước cast |
| `(int) Double.POSITIVE_INFINITY` cho max int | Giá trị bão hòa | Kiểm tra `isFinite`/range |
| `long -> double` mất chữ số cuối | Giới hạn 53 bit significand | Duy trì long nếu cần số nguyên chính xác |
| Cast boolean sang int | Không có primitive conversion như vậy | Dùng biểu thức điều kiện theo nghiệp vụ |

**Phân biệt rõ:** Java có thể chấp nhận một phép cast về cú pháp nhưng tạo kết quả sai yêu cầu. Việc chọn biểu diễn/validation là trách nhiệm của thiết kế chương trình.

## 14. Bài tập có đáp án

### Bài A — mở rộng

~~~java
byte b = -10;
int i = b;
long l = i;
System.out.println(l);
~~~

**Đáp án:** `-10`. Hai bước mở rộng giữa số nguyên giữ đúng giá trị âm.

### Bài B — narrowing

~~~java
int n = 255;
System.out.println((byte) n);
~~~

**Đáp án:** `-1`. Mẫu 8 bit thấp `11111111` là -1 khi diễn giải dưới dạng byte có dấu.

### Bài C — char và short

~~~java
char c = 65;
int code = c;
System.out.println(code);
~~~

**Đáp án:** `65`. `char -> int` là widening; nhưng `char -> short` không phải widening dù cả hai có 16 bit.

### Bài D — float và double

~~~java
float f = 0.1f;
double d = f;
System.out.println(d);
~~~

**Đáp án:** `0.10000000149011612`. Chuyển mở rộng giữ đúng **giá trị xấp xỉ đã lưu** trong `float`.

### Bài E — phép cộng int

~~~java
int max = Integer.MAX_VALUE;
long result = max + 1;
System.out.println(result);
~~~

**Đáp án:** `-2147483648`, vì phép cộng tràn trong `int` trước. Sửa bằng `long result = (long) max + 1;`.

### Bài F — không chấp nhận phần lẻ

Muốn chuyển `double value = 12.5;` thành số nguyên nhưng nghiệp vụ **không cho phép mất phần lẻ**, có nên viết `(int) value`?

**Đáp án:** không. Phép cast cho `12`, làm mất 0.5. Trước khi cast cần kiểm tra dữ liệu hữu hạn, nằm trong miền kiểu nguyên và có giá trị nguyên; nếu không hợp lệ phải từ chối hoặc xử lý theo quy tắc nghiệp vụ.

## 15. Checklist tổng kết

- [ ] Biết phân biệt widening và narrowing primitive conversion.
- [ ] Nhớ `char` không phải `short` có dấu và `boolean` không tham gia chuyển kiểu số học.
- [ ] Biết widening giữa kiểu nguyên giữ chính xác giá trị, còn sang float/double có thể làm tròn.
- [ ] Biết narrowing nguyên bằng cast có thể giữ các bit thấp và đổi giá trị số.
- [ ] Hiểu ngoại lệ gán constant int vừa miền byte/short/char.
- [ ] Biết cast float/double sang int/long thường cắt phần lẻ về 0 và có quy tắc đặc biệt cho NaN/Infinity.
- [ ] Biết double -> float có thể mất độ chính xác, overflow hoặc underflow.
- [ ] Nhớ byte/short/char được nâng thành int trong nhiều phép tính.
- [ ] Biết compound assignment như `+=` có thể thu hẹp kiểu ngầm.
- [ ] Chọn kiểu toán hạng **trước** khi phép cộng có thể bị overflow.
- [ ] Kiểm tra miền trước khi cast, dùng `Math.toIntExact` khi thích hợp.
- [ ] Chạy `PrimitiveConversionDemo.java` bằng JDK 17+ và đối chiếu từng dòng output.

**Kết luận:** **Chuyển kiểu mở rộng** thường được Java thực hiện tự động, nhưng có trường hợp mất độ chính xác khi sang floating-point. **Chuyển kiểu thu hẹp** thường cần cast và có thể thay đổi giá trị mà không ném exception. Phân biệt kiểu của toán hạng, giới hạn biểu diễn và yêu cầu nghiệp vụ là cách viết chuyển đổi primitive an toàn trong Java 17+.