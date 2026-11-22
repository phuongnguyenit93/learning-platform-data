# Phép gán hằng nằm trong miền giá trị của `byte`, `short` hoặc `char` — Java 17+

Trong Java, các literal số nguyên thông thường như `100` có kiểu `int`, nhưng đoạn mã **`byte b = 100;` vẫn biên dịch**. Lý do là Java cho phép **chuyển đổi thu hẹp đặc biệt trong ngữ cảnh gán** (*assignment context*) đối với một **biểu thức hằng tại thời điểm biên dịch** (*constant expression*), khi giá trị của nó nằm trọn trong miền biểu diễn của kiểu đích `byte`, `short` hoặc `char`.

Đây là quy tắc riêng trong Java, **không phải** chuyển đổi ngầm định từ mọi biến `int` sang `byte`.

~~~java
byte age = 100;        // Hop le: hang int 100 trong mien byte.
short count = 30_000;  // Hop le: hang int trong mien short.
char code = 65;        // Hop le: hang int 65 trong mien char ('A').

// byte bad = 128;     // LOI: 128 vuot Byte.MAX_VALUE.
// byte bad2 = -129;   // LOI: nho hon Byte.MIN_VALUE.
// short bad3 = 32768; // LOI: vuot Short.MAX_VALUE.
// char bad4 = -1;     // LOI: char khong dau.
~~~

## 1. Quy tắc chính xác

Trong **phép gán**, nếu biểu thức nguồn là *constant expression* có kiểu `byte`, `short`, `char` hoặc `int` và có **giá trị biểu diễn được** bằng kiểu đích `byte`, `short` hoặc `char`, Java có thể thực hiện chuyển đổi thu hẹp mà **không cần cast tường minh**.

| Kiểu đích | Miền giá trị | Gán hằng `int` hợp lệ | Gán hằng vượt miền |
| --- | --- | --- | --- |
| `byte` | −128 đến 127 | `byte b = 127;` | `byte b = 128;` |
| `short` | −32.768 đến 32.767 | `short s = 32_767;` | `short s = 32_768;` |
| `char` | 0 đến 65.535 | `char c = 65_535;` | `char c = 65_536;` hoặc `char c = -1;` |

**Hai điều kiện phải cùng đúng:** biểu thức phải là **hằng ở compile time** và **giá trị hằng nằm trong miền kiểu đích**.

Một biến `int` thông thường có giá trị 100 **không** thuộc ngoại lệ này:

~~~java
int value = 100;
// byte b = value;     // LOI bien dich: int -> byte can cast.
byte b = (byte) value; // Hop le; boi vi 100 nam trong mien nen b = 100.
~~~

Việc có cast không giúp compiler hoặc JVM tự bảo đảm giá trị vẫn nằm trong miền; nếu `value` thành 130, `(byte) value` cho `-126` do mất các bit cao.

## 2. Chương trình Java 17+ runnable

Tạo tệp UTF-8 **`ConstantAssignmentDemo.java`**:

~~~java
public class ConstantAssignmentDemo {
    static final int CLASS_LIMIT = 127;

    public static void main(String[] args) {
        byte maxByte = 127;
        byte minByte = -128;
        short maxShort = 32_767;
        short minShort = -32_768;
        char maxChar = 65_535;

        System.out.println("byteMax=" + maxByte);
        System.out.println("byteMin=" + minByte);
        System.out.println("shortMax=" + maxShort);
        System.out.println("shortMin=" + minShort);
        System.out.println("charMaxCode=" + (int) maxChar);

        byte foldedByte = 40 + 60;
        short foldedShort = 30_000 + 2_767;
        char nextLetter = 'A' + 1;
        System.out.println("foldedByte=" + foldedByte);
        System.out.println("foldedShort=" + foldedShort);
        System.out.println("letter=" + nextLetter);

        final int localConstant = 120;
        byte fromLocalFinal = localConstant;

        final int foldedConstant = 60 + 67;
        byte fromFoldedFinal = foldedConstant;
        byte fromClassFinal = CLASS_LIMIT;

        System.out.println("localFinal=" + fromLocalFinal);
        System.out.println("foldedFinal=" + fromFoldedFinal);
        System.out.println("classFinal=" + fromClassFinal);

        int variable = 120;
        byte castVariable = (byte) variable;

        final int runtimeFinal = Integer.parseInt("12");
        byte castRuntimeFinal = (byte) runtimeFinal;
        System.out.println("castVariable=" + castVariable);
        System.out.println("runtimeFinal=" + castRuntimeFinal);

        byte castOverflow = (byte) 128;
        short castShortOverflow = (short) 32_768;
        char castCharOverflow = (char) 65_536;
        System.out.println("castByteOverflow=" + castOverflow);
        System.out.println("castShortOverflow=" + castShortOverflow);
        System.out.println("castCharOverflow=" + (int) castCharOverflow);

        byte compounded = 100;
        compounded += 30;
        System.out.println("compoundAssignment=" + compounded);
    }
}
~~~

Tại thư mục chứa file, dùng **JDK 17 trở lên** trên PowerShell (Windows) hoặc Bash (Linux/macOS):

~~~bash
java -version
javac -version
javac -encoding UTF-8 ConstantAssignmentDemo.java
java ConstantAssignmentDemo
~~~

**Expected output chính xác của lệnh `java ConstantAssignmentDemo`:**

~~~text
byteMax=127
byteMin=-128
shortMax=32767
shortMin=-32768
charMaxCode=65535
foldedByte=100
foldedShort=32767
letter=B
localFinal=120
foldedFinal=127
classFinal=127
castVariable=120
runtimeFinal=12
castByteOverflow=-128
castShortOverflow=-32768
castCharOverflow=0
compoundAssignment=-126
~~~

Các lệnh kiểm tra phiên bản `java -version` và `javac -version` có đầu ra khác nhau tùy môi trường và không nằm trong khối expected output.

## 3. Tại sao biểu thức `40 + 60` vẫn gán được vào `byte`?

Khi tính `40 + 60`, cả hai literal mang kiểu `int` nên biểu thức có **kiểu `int`**. Tuy vậy, `40 + 60` là một **constant expression**: compiler tính được giá trị **100** trong lúc biên dịch. Vì 100 nằm trong miền `byte`, câu sau hợp lệ:

~~~java
byte result = 40 + 60; // 100: constant int nam trong mien byte.
~~~

Ngược lại, nếu dùng biến thông thường:

~~~java
int left = 40;
int right = 60;

// byte result = left + right; // LOI: ket qua la int, khong la hang.
int result = left + right;     // Hop le: int 100.
~~~

Ngay cả `byte + byte` thông thường cũng có kiểu kết quả `int` (theo *binary numeric promotion*):

~~~java
byte a = 40;
byte b = 60;
// byte sum = a + b; // LOI: int khong duoc tu thu hep ve byte.
int sum = a + b;    // 100.
~~~

**Không suy luận** rằng compiler nhìn thấy giá trị nhỏ thì sẽ tự gán vào kiểu hẹp. Nó chỉ áp dụng ngoại lệ đúng cho **biểu thức hằng thỏa điều kiện**.

## 4. `final int` có thể là *constant variable* — nhưng không phải lúc nào cũng vậy

Một **constant variable** trong Java là biến `final` có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng một *constant expression*. Với bài toán gán hằng số nguyên, trường hợp điển hình là `final int`:

~~~java
final int FIXED = 120;
byte b = FIXED; // Hop le: FIXED la constant variable, gia tri vua byte.

final int CALCULATED = 60 + 67;
byte max = CALCULATED; // Hop le: 127 vua byte.
~~~

`static final int` cũng có thể là constant variable nếu initializer là constant expression:

~~~java
static final int BYTE_MAX = 127;

// Trong mot phuong thuc:
// byte b = BYTE_MAX; // Hop le.
~~~

Nhưng **từ khóa `final` một mình không đủ**:

~~~java
final int parsed = Integer.parseInt("12");
// byte b = parsed;        // LOI: parsed KHONG la constant variable.
byte b = (byte) parsed;    // Hop le, nhung phai can nhac mien gia tri.
~~~

Hàm `Integer.parseInt` chạy khi chương trình chạy, nên initializer trên **không phải constant expression**, bất kể giá trị trả về là 12. Ngược lại, các biểu thức có toán tử số học trên literal/hằng thích hợp như `60 + 67` có thể được compiler tính sẵn.

Tương tự, biến `final Integer boxed = 100;` không phải constant variable kiểu nguyên thủy, vì `Integer` là **kiểu tham chiếu**, không phải kiểu primitive hoặc `String`. Đừng dùng `final` và giá trị “tình cờ vừa miền” làm bằng chứng một biến tham gia ngoại lệ gán hằng.

## 5. Ranh giới miền: `byte`, `short` và `char`

### `byte` là số nguyên có dấu 8 bit

~~~java
byte smallest = -128;
byte largest = 127;

// byte under = -129; // Ngoai mien.
// byte over = 128;   // Ngoai mien.
~~~

Một phép cast vẫn được phép nhưng **không bảo toàn giá trị** khi số vượt miền:

~~~java
byte wrapped = (byte) 128; // -128.
~~~

Phép thu hẹp nguyên-sang-nguyên giữ **các bit thấp** phù hợp với kiểu đích; với `byte`, mẫu 8 bit được diễn giải có dấu. Java không “chặn” giá trị ở 127 và cũng không tự ném `ArithmeticException` khi cast.

### `short` là số nguyên có dấu 16 bit

~~~java
short min = -32_768;
short max = 32_767;
// short bad = 32_768; // Ngoai mien.
short wrapped = (short) 32_768; // -32768.
~~~

### `char` là đơn vị mã UTF-16 không dấu 16 bit

~~~java
char zero = 0;
char letter = 65;      // 'A'.
char max = 65_535;

// char negative = -1; // Ngoai mien char.
// char tooBig = 65_536; // Ngoai mien char.
char wrapped = (char) 65_536; // Co gia tri so 0.
~~~

`char` khác `short`: cùng có 16 bit nhưng `char` có miền 0–65535. Khi in trực tiếp `char`, terminal hiển thị **ký tự tương ứng** chứ không phải mã số. Để xem giá trị số, dùng `(int) letter` hoặc `(int) max`.

## 6. Vì sao `long` literal và `double` literal không áp dụng ngoại lệ?

Phép thu hẹp hằng trong ngữ cảnh gán primitive đích `byte`, `short` hoặc `char` chỉ cho phép **kiểu của constant expression nguồn** thuộc `byte`, `short`, `char` hoặc `int`. Vì vậy:

~~~java
byte a = 100;          // Hop le: constant int.
// byte b = 100L;       // LOI: constant long, du gia tri 100.
// byte c = 100.0;      // LOI: literal double.
byte b = (byte) 100L;   // Cast tuong minh.
byte c = (byte) 100.0;  // Cast tuong minh.
~~~

Nếu giá trị kiểu `long` thực tế nhỏ, điều đó **không** làm chuyển đổi `long -> byte` thành ngoại lệ gán hằng. Cast có thể cho phép đoạn mã chạy, nhưng chính bạn phải kiểm tra mất dữ liệu.

Khi dữ liệu đến từ đầu vào, API, biến hay kết quả tính toán lúc chạy, cách thực tế là chọn kiểu đủ rộng, kiểm tra miền trước khi chuyển hoặc dùng phương thức kiểm tra tràn thích hợp, ví dụ `Math.toIntExact` khi thu hẹp `long -> int`.

## 7. Phân biệt phép gán trực tiếp với `+=`

~~~java
byte b = 100;
// b = b + 30;  // LOI: b + 30 la int, khong la constant expression.
b += 30;        // Hop le; ket qua la -126.
~~~

`b += 30` hợp lệ **không phải nhờ ngoại lệ gán hằng**. Toán tử gán kết hợp có quy tắc riêng: cộng trước rồi **chuyển về kiểu của vế trái**. Với `byte b = 100`, phép cộng cho `int 130`, chuyển về `byte` thành `-126`.

Nếu giá trị nằm ngoài miền đích, đừng dùng cast hoặc `+=` như cách “lách lỗi compiler” khi nghiệp vụ yêu cầu số chính xác.

## 8. Bảng phân biệt hợp lệ / lỗi biên dịch

| Mã Java | Hợp lệ? | Lý do |
| --- | --- | --- |
| `byte b = 127;` | Có | Constant `int` vừa `byte` |
| `byte b = 128;` | Không | Constant `int` vượt miền `byte` |
| `short s = 30_000 + 2_767;` | Có | Constant expression `int 32767` vừa `short` |
| `char c = 'A' + 1;` | Có | Constant expression `int 66` vừa `char` |
| `char c = -1;` | Không | `char` không có số âm |
| `byte b = 100L;` | Không | Nguồn là `long`, không thuộc ngoại lệ |
| `int x = 100; byte b = x;` | Không | `x` không là constant variable |
| `final int X = 100; byte b = X;` | Có | `X` là constant variable primitive |
| `final int X = Integer.parseInt("100"); byte b = X;` | Không | Initializer không là constant expression |
| `byte b = (byte) 128;` | Có | Cast tường minh, nhưng kết quả là −128 |

Nếu thấy thông báo compiler kiểu *possible lossy conversion from int to byte*, hãy hỏi: biểu thức có phải hằng không? Giá trị có nằm trong miền đích không? Hay bạn đang dùng biến thông thường và thực sự cần giữ kiểu rộng hơn?

## 9. Bài tập tự kiểm tra

1. **Biên của `byte`:** `byte a = -128; byte b = 127;` hợp lệ không? `byte c = 128;` thì sao?  
   *Đáp án:* Hai câu đầu hợp lệ; câu cuối lỗi biên dịch.
2. **Hằng biểu thức:** `short s = 10_000 + 20_000;` có cần cast không?  
   *Đáp án:* Không. Biểu thức hằng `int 30000` nằm trong miền `short`.
3. **Biến thông thường:** `int x = 100; byte b = x;` có hợp lệ không?  
   *Đáp án:* Không; `x` không là constant variable, dù giá trị chạy thử là 100.
4. **Hằng `final`:** `final int X = 127; byte b = X;` có hợp lệ không? Nếu `X = 128`?  
   *Đáp án:* 127 hợp lệ; 128 vượt miền `byte` và bị compiler từ chối.
5. **`char`:** `char c = 65_535;` và `char d = 65_536;` thì sao?  
   *Đáp án:* `c` hợp lệ, `d` không; `char` không dấu 16 bit.
6. **`long` literal:** Tại sao `byte b = 100L;` không hợp lệ nhưng `byte b = 100;` hợp lệ?  
   *Đáp án:* Chuyển thu hẹp hằng trong ngữ cảnh gán không áp dụng cho nguồn kiểu `long`.
7. **Cast vượt miền:** `(byte) 128` cho bao nhiêu?  
   *Đáp án:* `-128` do giữ tám bit thấp và diễn giải có dấu.

## Checklist

- [ ] Xác định **kiểu nguồn của constant expression**, không chỉ giá trị.
- [ ] Kiểm tra giá trị nằm trong miền `byte`/`short`/`char`.
- [ ] Phân biệt literal hằng và biến `int` thông thường.
- [ ] `final int` chỉ tham gia như constant variable nếu initializer là constant expression.
- [ ] Biểu thức constant như `'A' + 1` và `40 + 60` có thể được compiler tính trước.
- [ ] `100L` và `100.0` không thuộc ngoại lệ gán hằng `int`.
- [ ] Cast hoặc gán `+=` có thể **làm mất dữ liệu**, không tự kiểm tra miền.
- [ ] Nếu không chắc kết quả nằm trong miền, ưu tiên kiểu rộng hơn hoặc kiểm tra miền trước khi chuyển.

**Kết luận:** `byte b = 100;` hợp lệ nhờ **ngoại lệ thu hẹp biểu thức hằng trong ngữ cảnh gán**, chứ không phải vì mọi `int` đều tự chuyển về `byte`. Compiler cần biết **giá trị tại thời điểm biên dịch**, và giá trị phải **nằm trong miền kiểu đích**.
