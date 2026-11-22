# Chuyển đổi trong phép gán, lời gọi phương thức và biểu thức — Java 17+

## 1. Mục tiêu: cùng một giá trị, ba ngữ cảnh chuyển kiểu

Java không áp dụng một quy tắc “tự đổi kiểu” duy nhất ở mọi nơi. Compiler xét **ngữ cảnh** của giá trị:

1. **Phép gán (assignment context)**: đưa giá trị vào biến, field hoặc phần tử mảng có kiểu xác định.
2. **Lời gọi phương thức (method invocation context)**: truyền biểu thức đối số cho tham số, đồng thời xử lý lựa chọn overload.
3. **Biểu thức (expression context)**: xác định kiểu và cách chuyển đổi các toán hạng của phép cộng, nhân, so sánh, nối chuỗi, toán tử điều kiện, v.v.

~~~java
byte value = 7;              // Phép gán với hằng int vừa miền byte
long wide = value;            // Phép gán: byte -> long
System.out.println(value + 1); // Biểu thức: byte được nâng thành int
~~~

Ba dòng có cùng biến `value` nhưng ý nghĩa chuyển đổi **không giống nhau**. Một chương trình chạy đúng khi kiểu được compiler chấp nhận **và** giá trị sau chuyển đổi vẫn đáp ứng nghiệp vụ.

Bài này tập trung vào các quy tắc thường dùng trong Java 17+, đặc biệt là **widening**, **narrowing**, **boxing/unboxing**, biểu thức số học và lời gọi method có overload.

## 2. Nền tảng: widening, narrowing, boxing và unboxing

| Cơ chế | Ví dụ | Ý nghĩa |
|---|---|---|
| Identity conversion | `int x = 5;` | Kiểu nguồn khớp kiểu đích |
| Widening primitive | `long x = 5;` | `int` chuyển thành `long` |
| Narrowing primitive | `byte b = (byte) 130;` | Ép về kiểu nhỏ, có thể mất dữ liệu |
| Boxing | `Integer x = 5;` | Chuyển giá trị `int` thành `Integer` |
| Unboxing | `int x = Integer.valueOf(5);` | Lấy `int` từ `Integer` |
| Widening reference | `Object o = "Hi";` | Tham chiếu String gán cho kiểu Object |
| Boxing + widening reference | `Number n = 5;` | `int` → `Integer` → `Number` |
| Unboxing + widening primitive | `long n = Integer.valueOf(5);` | `Integer` → `int` → `long` |

Không phải mọi cách kết hợp đều được thực hiện tự động. Chẳng hạn:

~~~java
Long good = 5L;
// Long wrong = 5; // Sai: int không tự widening sang long rồi boxing thành Long
~~~

`5` là literal `int`, còn `5L` là literal `long`. Java không tự cho phép **widening primitive rồi boxing sang Long** trong phép gán này.

`boolean` không chuyển sang/từ các kiểu số bằng widening hoặc narrowing primitive. `String` cũng không phải kiểu nguyên thủy: `Integer.parseInt("5")` là gọi API phân tích chuỗi, không phải conversion ngầm từ String sang int.

## 3. Ngữ cảnh phép gán (assignment context)

Khi bên trái phép gán có kiểu xác định, compiler phải kiểm tra biểu thức bên phải có thể chuyển thành kiểu đó hay không.

~~~java
byte small = 8;
int asInt = small;       // byte -> int
long asLong = asInt;     // int -> long
double asDouble = asLong; // long -> double
~~~

Những phép gán trên hợp lệ mà không cần cast. Nhưng **hợp lệ không luôn đồng nghĩa chính xác tuyệt đối**: một giá trị `long` rất lớn chuyển thành `double` có thể mất các chữ số cuối vì độ chính xác significand hữu hạn.

Phép gán thu hẹp thường **không được tự thực hiện** với biến runtime:

~~~java
int source = 130;
// byte b = source;   // Lỗi biên dịch: possible lossy conversion
byte b = (byte) source;
System.out.println(b); // -126
~~~

Cast `(byte)` chỉ yêu cầu chuyển kiểu, **không** kiểm tra rằng giá trị 130 vừa miền -128..127. Sau narrowing, giá trị bị thay đổi thành -126.

### Các nơi áp dụng ý tưởng phép gán

Ngoài câu lệnh `x = expression`, quy tắc assignment context xuất hiện trong khởi tạo biến, field, phần tử mảng và các ngữ cảnh trả về giá trị tương ứng với kiểu khai báo:

~~~java
long[] values = {1, 2, 3}; // Các int literal có thể gán vào phần tử long

static long getCount() {
    int count = 7;
    return count; // int -> long trong ngữ cảnh return
}
~~~

Không được suy từ việc một phép gán được phép narrowing hằng số rằng **mọi ngữ cảnh Java** đều cho phép tương tự.


**Riêng hằng `int` vừa miền `byte`/`short`/`char`**, phép gán có một ngoại lệ thu hẹp tại compile time (`byte b = 7;` hợp lệ); đối số method `takeByte(7)` thì không được hưởng ngoại lệ này. Phân biệt hai ngữ cảnh trước khi thêm cast.

## 4. Ngữ cảnh lời gọi phương thức: đối số phải hợp kiểu tham số

Method khai báo kiểu tham số. Khi gọi, Java xét kiểu biểu thức đối số để tìm method có thể áp dụng.

~~~java
static void acceptLong(long value) {
    System.out.println("long=" + value);
}

// Trong main:
byte b = 7;
acceptLong(b); // Hợp lệ: byte -> long
~~~

Đây là **widening primitive trong method invocation context**.

Ngược lại, **quy tắc gán hằng int vừa miền không tự áp dụng cho tham số byte**:

~~~java
static void acceptByte(byte value) {
    System.out.println("byte=" + value);
}

// acceptByte(7);       // Lỗi biên dịch: int không tự narrowing thành byte
acceptByte((byte) 7);   // Hợp lệ: cast tường minh
~~~

Phân biệt rõ:

| Cú pháp | Có biên dịch? | Vì sao |
|---|---|---|
| `byte b = 7;` | Có | Ngoại lệ narrowing constant expression trong phép gán |
| `acceptByte(7);` | Không | Method invocation không cho narrowing hằng int thành byte |
| `acceptByte((byte) 7);` | Có | Đối số sau cast đã có kiểu byte |
| `acceptLong(7);` | Có | int widening sang long |
| `acceptLong((byte) 7);` | Có | byte widening sang long |

**Cách viết tốt:** truyền đúng kiểu tham số bằng literal/hàm sinh giá trị tương ứng; chỉ dùng cast khi có lý do và đã xét miền giá trị.

## 5. Boxing và unboxing trong lời gọi method

Từ Java 5, Java hỗ trợ **autoboxing** và **unboxing** trong những ngữ cảnh thích hợp; Java 17 vẫn dùng cơ chế này.

~~~java
static void showNumber(Number number) {
    System.out.println(number.getClass().getSimpleName());
}

// Trong main:
showNumber(5); // In Integer
~~~

`5` ban đầu là `int`. Trong lời gọi trên, Java có thể boxing thành `Integer`, rồi widening reference thành `Number`.

Ngược lại:

~~~java
static void takeLong(long value) {
    System.out.println(value);
}

Integer boxed = Integer.valueOf(42);
takeLong(boxed); // Integer unboxing -> int, rồi widening thành long
~~~

**Bẫy null:** unboxing tham chiếu `null` gây `NullPointerException` lúc chạy:

~~~java
Integer missing = null;
// long value = missing; // Biên dịch được, nhưng chạy sẽ ném NullPointerException
~~~

Compiler kiểm tra kiểu chuyển đổi, không bảo đảm wrapper khác `null` tại runtime.

## 6. Overloading: chọn method trước khi thực thi chuyển đổi

Khi có nhiều method **cùng tên** nhưng khác tham số, compiler giải quyết overload dựa trên kiểu đối số và các giai đoạn tìm method phù hợp. Về cơ bản, Java ưu tiên xét những lời gọi áp dụng bằng các chuyển đổi *strict* như widening trước; nếu chưa tìm được thì mới xét những khả năng có boxing/unboxing, rồi các trường hợp varargs phù hợp.

~~~java
static void choose(long value) {
    System.out.println("choose(long)");
}

static void choose(Integer value) {
    System.out.println("choose(Integer)");
}
~~~

Với:

~~~java
choose(7);                  // choose(long)
choose(Integer.valueOf(7)); // choose(Integer)
~~~

Vì sao?

- `7` có kiểu **`int`**; `int -> long` là widening primitive, nên method `choose(long)` được chọn trong giai đoạn áp dụng strict.
- `Integer.valueOf(7)` có kiểu **`Integer`**; method `choose(Integer)` nhận đúng kiểu tham chiếu, được chọn trước khả năng unboxing rồi widening.

Đây không phải quy tắc đơn giản “luôn ưu tiên primitive”. **Kiểu đối số và các overload hiện diện** mới quyết định. Overload với nhiều tham số, subtype, varargs hoặc generic còn có các quy tắc lựa chọn cụ thể hơn.

**Thực hành:** tránh tạo bộ overload có ý nghĩa nghiệp vụ khác nhau chỉ vì boxing/ví dụ số hạng; API dễ gây hiểu nhầm khi người gọi đổi từ primitive sang wrapper.

## 7. Ngữ cảnh biểu thức: số học tự nâng kiểu

Trong biểu thức số học với các toán hạng số nguyên nhỏ, Java áp dụng **numeric promotion**. Cụ thể, `byte`, `short`, `char` thường được nâng thành `int` trước các phép cộng, trừ, nhân hoặc chia số học thông thường.

~~~java
byte a = 100;
byte b = 20;

int sum = a + b; // a+b có kiểu int
System.out.println(sum); // 120

// byte wrong = a + b; // Lỗi: kết quả biểu thức là int
byte castResult = (byte) (a + b); // Chỉ an toàn nếu giá trị vừa byte
~~~

Ngoại lệ gán hằng lại khác:

~~~java
byte constantSum = 100 + 20; // Hợp lệ vì đây là constant expression int = 120
~~~

**Hai dòng cùng ra 120 nhưng compiler xử lý khác nhau:**

- `byte constantSum = 100 + 20;`: biểu thức hằng, cho phép narrowing theo assignment context.
- `byte s = a + b;`: biểu thức dựa trên các biến byte, kết quả `int` và không tự narrowing về byte.

Khi có toán hạng `long`, `float` hoặc `double`, kết quả được tính theo những quy tắc nâng kiểu tương ứng. Ví dụ:

~~~java
double result = 3 + 0.5;
System.out.println(result); // 3.5
~~~

Một toán hạng kiểu `double` làm phép cộng được thực hiện theo dấu phẩy động double.

## 8. Bảng so sánh ba ngữ cảnh

| Tình huống | Code ví dụ | Hợp lệ? | Điểm cần nhớ |
|---|---|---|---|
| Gán widening | `long n = 7;` | Có | int → long |
| Gán hằng int vừa miền byte | `byte b = 7;` | Có | Quy tắc đặc biệt assignment |
| Gán biến int sang byte | `byte b = intValue;` | Thường không | Cần cast/kiểm tra |
| Gán boxed rồi widening reference | `Number n = 7;` | Có | int → Integer → Number |
| Gán int vào Long | `Long n = 7;` | Không | Không tự int → long → Long |
| Truyền int literal vào tham số byte | `acceptByte(7);` | Không | Method invocation không narrowing hằng |
| Truyền byte vào tham số long | `acceptLong((byte) 7);` | Có | Widening primitive |
| Gọi tham số Number bằng int | `acceptNumber(7);` | Có | Boxing + widening reference |
| Biểu thức byte + byte | `int s = a + b;` | Có | Numeric promotion ra int |
| Gán kết quả byte + byte vào byte | `byte s = a + b;` | Không | Không tự narrowing kết quả runtime |
| Gán biểu thức hằng vào byte | `byte s = 100 + 20;` | Có | Constant expression vừa miền |
| Compound assignment byte | `b += 10;` | Có | Có narrowing ngầm, có thể tràn |
| Nối String với số | `"n=" + 7` | Có | Kết quả String `"n=7"` |

Không phải mọi phép chuyển đổi chỉ thuộc đúng một ô trong bảng: một biểu thức có thể trải qua **numeric promotion trước**, rồi được **assignment conversion sau**. Hãy phân tích theo từng bước.

## 9. Chương trình Java 17 chạy độc lập

Tạo tệp đúng tên **`ConversionContextsDemo.java`**:

~~~java
public final class ConversionContextsDemo {
    private ConversionContextsDemo() {}

    static void acceptLong(long value) {
        System.out.println("call long=" + value);
    }

    static void acceptByte(byte value) {
        System.out.println("call byte=" + value);
    }

    static void acceptNumber(Number value) {
        System.out.println("call Number type="
                + value.getClass().getSimpleName());
    }

    static void choose(long value) {
        System.out.println("choose=long");
    }

    static void choose(Integer value) {
        System.out.println("choose=Integer");
    }

    public static void main(String[] args) {
        byte small = 7;
        long widened = small;
        System.out.println("assignment widening=" + widened);

        byte constant = 120;
        final int KNOWN = 12;
        byte fromFinalConstant = KNOWN;
        Byte boxedConstant = 9;
        System.out.println("assignment constant=" + constant);
        System.out.println("assignment final=" + fromFinalConstant);
        System.out.println("assignment boxed constant=" + boxedConstant);

        int runtime = 130;
        byte narrowed = (byte) runtime;
        System.out.println("assignment explicit cast=" + narrowed);

        Integer boxed = Integer.valueOf(42);
        long unboxedAndWidened = boxed;
        System.out.println("assignment unbox widen=" + unboxedAndWidened);
        Number asNumber = 17;
        System.out.println("assignment Number type="
                + asNumber.getClass().getSimpleName());
        Long fromLongLiteral = 17L;
        System.out.println("assignment Long=" + fromLongLiteral);

        acceptLong(small);
        acceptByte((byte) 7);
        acceptNumber(5);

        choose(7);
        choose(Integer.valueOf(7));

        byte a = 100;
        byte b = 20;
        int sum = a + b;
        byte constantSum = 100 + 20;
        System.out.println("expression promoted=" + sum);
        System.out.println("expression constant sum=" + constantSum);
        System.out.println("expression mixed=" + (3 + 0.5));

        long wrong = 2_000_000_000 + 2_000_000_000;
        long correct = 2_000_000_000L + 2_000_000_000;
        System.out.println("expression overflow int=" + wrong);
        System.out.println("expression safe long=" + correct);

        byte counter = 120;
        counter += 10;
        System.out.println("compound assignment=" + counter);

        System.out.println("concat=" + 1 + 2);
        System.out.println("parenthesized=" + (1 + 2));

        double fractional = 8.9;
        System.out.println("explicit double cast=" + (int) fractional);

        Integer missing = null;
        try {
            long shouldFail = missing;
            System.out.println(shouldFail);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing=NullPointerException");
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal mở tại thư mục chứa file. Không cần Maven, Gradle hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ConversionContextsDemo.java
java -cp . ConversionContextsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ConversionContextsDemo.java
java -cp . ConversionContextsDemo
~~~

**Expected output:**

~~~text
assignment widening=7
assignment constant=120
assignment final=12
assignment boxed constant=9
assignment explicit cast=-126
assignment unbox widen=42
assignment Number type=Integer
assignment Long=17
call long=7
call byte=7
call Number type=Integer
choose=long
choose=Integer
expression promoted=120
expression constant sum=120
expression mixed=3.5
expression overflow int=-294967296
expression safe long=4000000000
compound assignment=-126
concat=12
parenthesized=3
explicit double cast=8
null unboxing=NullPointerException
~~~

**Điểm quan trọng để đối chiếu:**

1. `byte constant = 120` và `byte fromFinalConstant = KNOWN` hợp lệ nhờ ngoại lệ hằng int trong assignment context.
2. `acceptByte((byte) 7)` cần cast vì method invocation không tự thu hẹp literal int thành byte.
3. `choose(7)` chọn `long` theo strict invocation; `choose(Integer.valueOf(7))` chọn `Integer`.
4. `a + b` có kiểu `int` dù hai biến là byte; `100 + 20` là constant expression có thể gán byte.
5. `wrong` cho kết quả tràn int trước khi gán long; `correct` dùng long ngay lúc cộng.
6. `counter += 10` có narrowing ngầm và biến thành -126.
7. `"concat=" + 1 + 2` nối String ra `12`, khác phép cộng số trong ngoặc.
8. `missing` là `Integer` null; unboxing lúc chạy gây `NullPointerException`, được catch theo chủ đích.

## 10. Bài tập và đáp án

### Bài A — cùng giá trị nhưng khác context

Giả sử có:

~~~java
static void takeByte(byte value) {}

byte a = 100;
takeByte(a);
// takeByte(100);
~~~

**Đáp án:** `byte a = 100` hợp lệ bởi ngoại lệ hằng int trong phép gán. `takeByte(a)` hợp lệ vì đối số đã có kiểu byte; `takeByte(100)` không hợp lệ vì method invocation không tự narrowing literal int. Có thể viết `takeByte((byte) 100)`.

### Bài B — hằng hay biến runtime?

~~~java
byte a = 100 + 20;
byte x = 100;
byte y = 20;
// byte b = x + y;
~~~

**Đáp án:** dòng đầu hợp lệ vì `100+20` là hằng int bằng 120. Dòng `byte b = x+y` lỗi vì toán tử cộng nâng cả byte lên int, kết quả không tự thu hẹp về byte.

### Bài C — boxing và widening

~~~java
Number a = 5;
Integer b = 5;
long c = b;
// Long d = 5;
~~~

**Đáp án:** `a` hợp lệ qua boxing `int -> Integer` rồi widening reference; `b` hợp lệ qua boxing; `c` hợp lệ qua unboxing rồi widening int → long. `Long d = 5` không hợp lệ; viết `5L`.

### Bài D — quá trình cộng xảy ra trước phép gán

~~~java
int x = 2_000_000_000;
long a = x + x;
long b = (long) x + x;
System.out.println(a);
System.out.println(b);
~~~

**Đáp án:**

~~~text
-294967296
4000000000
~~~

`a` nhận kết quả int đã tràn, còn `b` thực hiện phép cộng long vì toán hạng đầu đã được cast trước.

### Bài E — chọn overload

~~~java
static void choose(long x) { System.out.println("long"); }
static void choose(Integer x) { System.out.println("Integer"); }

// Trong main:
choose(3);
choose(Integer.valueOf(3));
~~~

**Đáp án:**

~~~text
long
Integer
~~~

### Bài F — gán kết hợp

~~~java
byte b = 127;
b += 1;
System.out.println(b);
~~~

**Đáp án:** `-128`. Toán tử `+=` có chuyển kiểu thu hẹp về byte; không tự báo overflow. Nếu không cho phép giá trị âm bất ngờ, hãy tính bằng int và kiểm tra miền trước.

## 11. Checklist tổng kết

- [ ] Phân biệt **assignment**, **method invocation** và **expression context**.
- [ ] Biết widening primitive cho phép gán hoặc truyền đối số khi kiểu tương thích.
- [ ] Biết ngoại lệ gán hằng int vừa miền vào byte/short/char.
- [ ] Hiểu ngoại lệ đó **không** đồng nghĩa method nhận byte cho phép truyền literal int tự động.
- [ ] Biết boxing/unboxing và rủi ro unboxing null.
- [ ] Hiểu `Number n = 5` hợp lệ nhưng `Long n = 5` không.
- [ ] Biết overload resolution có thể chọn widening trước boxing.
- [ ] Nhớ byte/short/char được nâng thành int trong phép tính số học.
- [ ] Phân biệt compound assignment với phép gán `=` thông thường.
- [ ] Xác định kiểu toán hạng **trước** khi cộng để tránh overflow.
- [ ] Không nhầm phép nối String với phép cộng số.
- [ ] Dùng cast sau khi kiểm tra giá trị và đúng yêu cầu nghiệp vụ.
- [ ] Chạy `ConversionContextsDemo.java` trên JDK 17+ và so từng dòng expected output.

**Kết luận:** Java quyết định chuyển đổi theo **nơi giá trị được sử dụng**. Phép gán cho phép một số narrowing hằng int đặc biệt; lời gọi method dùng quy tắc thích ứng kiểu tham số và phân giải overload; biểu thức lại có numeric promotion và ngữ nghĩa toán tử riêng. Muốn code đúng, hãy đọc **kiểu nguồn → ngữ cảnh → chuyển đổi → giá trị thực tế**, thay vì chỉ nhìn kiểu của biến nhận.