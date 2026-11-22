# `byte`, `short`, `int` và `long`: độ rộng và miền giá trị trong Java 17+

## 1. Bốn kiểu số nguyên có dấu

Java có bốn **kiểu nguyên thủy số nguyên có dấu** (*signed integral primitive types*) thường dùng để lưu số lượng, chỉ số, mã trạng thái và các đại lượng nguyên: `byte`, `short`, `int`, `long`.

Độ rộng và miền giá trị của chúng được **ngôn ngữ Java quy định cố định**; không đổi theo Windows/Linux hay JVM 32-bit/64-bit.

| Kiểu | Độ rộng giá trị | Nhỏ nhất | Lớn nhất | Hằng giới hạn |
|---|---:|---:|---:|---|
| `byte` | 8 bit | -128 | 127 | `Byte.MIN_VALUE`, `Byte.MAX_VALUE` |
| `short` | 16 bit | -32.768 | 32.767 | `Short.MIN_VALUE`, `Short.MAX_VALUE` |
| `int` | 32 bit | -2.147.483.648 | 2.147.483.647 | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` |
| `long` | 64 bit | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | `Long.MIN_VALUE`, `Long.MAX_VALUE` |

Mỗi kiểu có `n` bit và biểu diễn số nguyên có dấu theo **bù hai** (*two's complement*), nên miền giá trị là:

\[
-2^{n-1} \;\leq\; x \;\leq\; 2^{n-1}-1.
\]

Ví dụ `byte` có 8 bit: giá trị nhỏ nhất \(-2^7=-128\), lớn nhất \(2^7-1=127\). Phía âm nhiều hơn phía dương **một** giá trị; đây là lý do `Math.abs(Integer.MIN_VALUE)` không cho ra số dương trong `int`.

**Chú ý:** “8 bit” mô tả **độ rộng giá trị của kiểu**, không phải cam kết rằng mọi biến `byte` trong mọi object chiếm đúng 1 byte bộ nhớ thực tế sau khi JVM căn chỉnh, đóng gói object hoặc tối ưu.

## 2. Khai báo và đọc các giới hạn

~~~java
byte temperature = -20;
short altitudeMeters = 2_500;
int population = 1_000_000;
long distanceMeters = 12_000_000_000L;
~~~

Một số điểm cần chú ý:

- Dấu `_` giữa chữ số chỉ giúp dễ đọc: `1_000_000` bằng `1000000`.
- Literal thập phân như `1_000_000` **mặc định là `int`**, miễn nằm trong miền hợp lệ.
- Với giá trị thập phân lớn hơn `Integer.MAX_VALUE`, phải dùng hậu tố `L` để tạo **literal `long`**: `12_000_000_000L`. Nên dùng chữ **`L` hoa**, vì `l` thường dễ nhìn nhầm thành số 1.
- Biến kiểu `long` **không sửa được** literal `int` đã quá giới hạn. Ví dụ `long x = 3_000_000_000;` không biên dịch, trong khi `long x = 3_000_000_000L;` hợp lệ.

Các class wrapper `Byte`, `Short`, `Integer`, `Long` có sẵn các hằng `MIN_VALUE` và `MAX_VALUE` để tránh nhập nhầm các con số dài.


## 3. Có dấu trong dữ liệu nhị phân

Cùng mẫu bit, kết quả đọc có thể khác tùy cách diễn giải. Bốn kiểu số nguyên đang xét là kiểu **có dấu**. Chẳng hạn, `byte` lưu 8 bit `11111111` được hiểu là `-1` theo bù hai, trong khi dữ liệu giao thức có thể xem cùng tám bit là `255`:

~~~java
byte payload = (byte) 0xFF;
System.out.println(payload);                    // -1
System.out.println(Byte.toUnsignedInt(payload)); // 255
~~~

`Byte.toUnsignedInt` trả về một `int`; nó không biến `byte` thành một kiểu nguyên thủy không dấu. Bài **Số nguyên có dấu và biểu diễn bù hai** ngay sau đây đi sâu vào cách đọc bit, mở rộng dấu và dịch bit; ở đây trọng tâm là **miền có thể lưu** để khai báo và chuyển kiểu đúng.

## 4. Chuyển kiểu mở rộng: từ nhỏ sang lớn

Java cho phép chuyển **mở rộng** (*widening primitive conversion*) giữa bốn kiểu số nguyên theo hướng:

~~~text
byte → short → int → long
~~~

Và có thể đi trực tiếp từ kiểu nhỏ tới kiểu lớn hơn bất kỳ ở bên phải:

~~~java
byte count = 100;
short asShort = count;
int asInt = count;
long asLong = count;

System.out.println(asShort); // 100
System.out.println(asInt);   // 100
System.out.println(asLong);  // 100
~~~

Trong chuỗi này, mọi giá trị `byte` đều biểu diễn chính xác bằng `short`, `int`, `long`. Mở rộng **không đòi ép kiểu tường minh**.

Phân biệt **kiểu của giá trị/biến nguồn** với **kiểu đích**: `long result = 42;` hợp lệ, nhưng literal `42` vẫn là `int` rồi được chuyển mở rộng sang `long`.

## 5. Chuyển kiểu thu hẹp: có thể mất dữ liệu

Hướng ngược lại **không tự động cho mọi giá trị**:

~~~java
int input = 130;
// byte narrowed = input; // LỖI BIÊN DỊCH: int không tự thu hẹp thành byte
byte narrowed = (byte) input;
System.out.println(narrowed); // -126
~~~

`130` vượt miền của `byte` là -128 đến 127. Ép kiểu `(byte)` giữ 8 bit thấp; `130` có bit thấp `1000_0010`, khi diễn giải là `byte` có dấu thì thành **-126**.

**Cast không phải kiểm tra an toàn.** Nếu một giá trị có thể vượt miền, nên kiểm tra trước:

~~~java
static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("Out of byte range: " + value);
    }
    return (byte) value;
}
~~~

Khi cần đúng giá trị mà không chấp nhận mất dữ liệu, có thể giữ nguyên kiểu `int`/`long` thay vì cast.

### Ngoại lệ quan trọng: gán hằng int nằm trong phạm vi

Dù `127` là literal `int`, Java cho phép **narrowing conversion của một số constant expressions** trong ngữ cảnh gán/khởi tạo nếu giá trị vừa kiểu nhỏ:

~~~java
byte maxByte = 127;      // Hợp lệ
short maxShort = 32767;  // Hợp lệ
// byte wrong = 128;     // LỖI: ngoài giới hạn byte
// short wrong2 = 40000; // LỖI: ngoài giới hạn short
~~~

Nhưng khi biểu thức là biến `int` thông thường, compiler không được tự coi giá trị runtime là an toàn:

~~~java
int source = 127;
// byte b = source; // LỖI
byte b = (byte) source; // Có cast; lập trình viên chịu trách nhiệm miền
~~~

Trường hợp đặc biệt này **không có nghĩa** literal `127` mang kiểu `byte`; kiểu literal mặc định vẫn là `int`.

## 6. Phép tính với byte/short thường được nâng lên int

Một bẫy quan trọng: Java **nâng** `byte` và `short` thành `int` trong nhiều phép toán số học (*binary numeric promotion*).

~~~java
byte a = 100;
byte b = 20;

// byte sum = a + b; // LỖI: biểu thức a + b có kiểu int
int sum = a + b;
System.out.println(sum); // 120
~~~

Tương tự:

~~~java
short x = 10;
short y = 20;
int product = x * y;
System.out.println(product); // 200
~~~

Nếu chắc chắn kết quả nằm trong miền cần thiết, có thể ép kiểu:

~~~java
byte a = 100;
byte b = 20;
byte sum = (byte) (a + b); // 120, còn trong phạm vi byte
~~~

Nhưng ép kiểu có thể tạo giá trị bất ngờ:

~~~java
byte a = 120;
byte b = 20;
byte wrong = (byte) (a + b);
System.out.println(wrong); // -116, vì 140 vượt phạm vi byte
~~~

Một biến `short` không làm `short + short` tự tính bằng `short`. Ngược lại, phép tính có toán hạng `long` thường thực hiện trong `long` theo quy tắc nâng kiểu số học.


## 7. Tràn số xảy ra trước khi gán kết quả

Độ rộng giá trị cố định nên phép cộng/nhân số nguyên thông thường có thể vượt miền. Phép toán `int` không tự đổi thành `long` hoặc tự ném ngoại lệ:

~~~java
long tooLate = 2_000_000_000 + 2_000_000_000;   // -294967296
long inTime = 2_000_000_000L + 2_000_000_000;   // 4000000000
~~~

Ở `tooLate`, phép cộng đã chạy theo kiểu `int`; phép gán chỉ mở rộng **kết quả bị tràn**. Khi muốn báo lỗi nếu kết quả không vừa miền, dùng `Math.addExact`, `Math.subtractExact` hoặc `Math.multiplyExact` với overload `int`/`long` phù hợp. Các API này ném `ArithmeticException` khi tràn. Cách đọc bit khi tràn, biên `MIN_VALUE` và cách dịch bit được giải thích trong bài kế tiếp.

## 8. Chương trình Java 17 chạy được và expected output

Tạo tệp đúng tên **`IntegerTypesDemo.java`**:

~~~java
public final class IntegerTypesDemo {
    private IntegerTypesDemo() {}

    static byte checkedByte(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("byte overflow: " + value);
        }
        return (byte) value;
    }

    public static void main(String[] args) {
        System.out.println("byte: " + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short: " + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int: " + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long: " + Long.MIN_VALUE + ".." + Long.MAX_VALUE);

        byte small = 100;
        short widenedShort = small;
        int widenedInt = small;
        long widenedLong = small;
        System.out.println("widen: " + widenedShort + ","
                + widenedInt + "," + widenedLong);

        byte a = 100;
        byte b = 20;
        int promotedSum = a + b;
        System.out.println("byte + byte -> int: " + promotedSum);

        byte castValue = (byte) 130;
        System.out.println("cast 130 to byte: " + castValue);

        byte signedBits = (byte) 0xFF;
        System.out.println("signed byte: " + signedBits);
        System.out.println("unsigned view: "
                + Byte.toUnsignedInt(signedBits));

        int wrapped = Integer.MAX_VALUE + 1;
        System.out.println("int wrap: " + wrapped);

        long wrong = 2_000_000_000 + 2_000_000_000;
        long correct = 2_000_000_000L + 2_000_000_000;
        System.out.println("int overflow first: " + wrong);
        System.out.println("long addition: " + correct);

        System.out.println("checked byte: " + checkedByte(127));
        try {
            checkedByte(128);
        } catch (IllegalArgumentException ex) {
            System.out.println("range check: " + ex.getMessage());
        }

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("Math.addExact: overflow detected");
        }

        System.out.println("abs int min: " + Math.abs(Integer.MIN_VALUE));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+** tại thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IntegerTypesDemo.java
java -cp . IntegerTypesDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IntegerTypesDemo.java
java -cp . IntegerTypesDemo
~~~

**Đầu ra dự kiến:**

~~~text
byte: -128..127
short: -32768..32767
int: -2147483648..2147483647
long: -9223372036854775808..9223372036854775807
widen: 100,100,100
byte + byte -> int: 120
cast 130 to byte: -126
signed byte: -1
unsigned view: 255
int wrap: -2147483648
int overflow first: -294967296
long addition: 4000000000
checked byte: 127
range check: byte overflow: 128
Math.addExact: overflow detected
abs int min: -2147483648
~~~

Những dòng quan trọng:

- Bốn dòng đầu đọc miền giá trị từ **wrapper constants**; không phải nhập tay các con số để dự đoán kiểu.
- `byte + byte -> int` cho biết kiểu biểu thức sau nâng kiểu số học.
- `cast 130 to byte` minh họa dữ liệu bị thu hẹp; `unsigned view` chỉ là cách diễn giải các bit.
- `int overflow first` và `long addition` phân biệt việc **tính ở int** với việc **tính ở long**.
- `Math.addExact` báo lỗi thay vì âm thầm dùng giá trị sau tràn.

Ví dụ độc lập, không cần thư viện ngoài JDK.


## 9. Độ rộng kiểu là một ràng buộc dữ liệu

Chọn `byte` khi trao đổi **một octet** nhị phân, nhưng nhớ phải xử lý cách diễn giải có dấu/không dấu theo giao thức. Chọn `short` nếu tài liệu định dạng thực sự yêu cầu số nguyên 16 bit có dấu; đừng dùng `short` chỉ vì một số đếm hiện tại nhỏ. `int` thường khớp chỉ số và API Java phổ biến; `long` thích hợp khi miền dữ liệu hoặc các phép toán trung gian có thể vượt `int`. Khi **ngay cả `long` cũng không đủ** và cần số nguyên chính xác, `BigInteger` là kiểu tham chiếu phù hợp.

Một kiểu có miền rộng không thay thế kiểm tra hợp lệ của nghiệp vụ: giá trị `-5` nằm trong miền `int` nhưng không nhất thiết hợp lệ cho số lượng sản phẩm. Bài **Chọn kiểu theo miền dữ liệu và yêu cầu tính toán** sẽ kết hợp độ rộng, đơn vị dữ liệu và độ chính xác thành một quyết định thiết kế.

## 10. Lỗi thường gặp

| Tình huống | Nguyên nhân | Sửa thế nào? |
|---|---|---|
| `byte n = 128;` | 128 vượt miền byte | Chọn `short`/`int` nếu cần giá trị 128 |
| `short n = 40000;` | 40000 vượt miền short | Dùng `int` |
| `long n = 3000000000;` | Literal decimal mặc định int quá lớn | `3000000000L` |
| `byte sum = a + b;` | `a + b` được nâng thành int | Nhận vào `int` hoặc cast có kiểm tra |
| `byte n = (byte) 130;` | Cast cắt bit, ra -126 | Kiểm tra miền trước cast |
| `long n = 2_000_000_000 + 2_000_000_000;` | Tràn int trước khi gán | Có `L` ở toán hạng trước phép cộng |
| `Integer.MAX_VALUE + 1` | Tràn về `Integer.MIN_VALUE` | `Math.addExact` hoặc đổi miền kiểu |
| `Math.abs(Integer.MIN_VALUE)` | Không thể biểu diễn trị tuyệt đối dương trong int | Kiểm tra giá trị biên, xử lý bằng kiểu phù hợp |

Lưu ý một giới hạn thực tế: `Math.addExact` phát hiện overflow của kiểu được sử dụng; nếu biểu thức **đã overflow trước khi truyền** vào `Math.addExact`, API không thể biết ý định ban đầu. Hãy chọn toán hạng/kiểu đúng trước khi tính.

## 11. Bài tập kèm đáp án

### Bài A — miền giá trị

`byte` 8 bit lưu được `127`, `128`, `-128`, `-129` không?

**Đáp án:** `127` và `-128` nằm trong miền; `128` và `-129` nằm ngoài miền `byte`.

### Bài B — chuyển kiểu mở rộng

~~~java
short s = 32000;
int n = s;
long m = n;
System.out.println(m);
~~~

**Đáp án:** in `32000`. Giá trị vừa miền `short` và được mở rộng chính xác sang `int`, rồi `long`.

### Bài C — phép cộng byte

~~~java
byte a = 120;
byte b = 20;
// byte sum = a + b;
int sum = a + b;
System.out.println(sum);
~~~

**Đáp án:** `140`. Biểu thức `a+b` có kiểu `int`; khai báo `byte sum` sẽ lỗi dù bạn biết cú pháp `byte`.

### Bài D — int overflow trước khi gán long

~~~java
long a = Integer.MAX_VALUE + 1;
long b = (long) Integer.MAX_VALUE + 1;
System.out.println(a);
System.out.println(b);
~~~

**Đáp án:**

~~~text
-2147483648
2147483648
~~~

Ở `a` phép cộng dùng `int` và tràn; ở `b` ép kiểu sang `long` xảy ra trước phép cộng.

### Bài E — signed byte và unsigned view

~~~java
byte b = (byte) 255;
System.out.println(b);
System.out.println(Byte.toUnsignedInt(b));
~~~

**Đáp án:** lần lượt `-1` và `255`; mẫu 8 bit vẫn là `11111111`, chỉ cách diễn giải khác nhau.

## 12. Checklist tự đánh giá

- [ ] Nhớ độ rộng cố định: `byte` 8, `short` 16, `int` 32, `long` 64 bit.
- [ ] Tra đúng `MIN_VALUE`/`MAX_VALUE` thay vì đoán giá trị biên.
- [ ] Hiểu miền có dấu theo bù hai: \(-2^{n-1}\) đến \(2^{n-1}-1\).
- [ ] Biết chuyển mở rộng `byte → short → int → long` không cần cast.
- [ ] Biết ép thu hẹp có thể mất dữ liệu; `(byte)130 == -126`.
- [ ] Phân biệt ngoại lệ gán constant expression int vừa miền với ép biến int runtime.
- [ ] Hiểu phép tính `byte`/`short` thường dùng `int`.
- [ ] Biết `int`/`long` có thể overflow mà không ném lỗi.
- [ ] Dùng hậu tố `L` khi literal số nguyên cần kiểu `long`.
- [ ] Tự biên dịch/chạy `IntegerTypesDemo.java` và đối chiếu output.

**Kết luận:** Độ rộng và miền giá trị của bốn kiểu số nguyên có dấu trong Java là **cố định**. Chọn kiểu theo yêu cầu thực, hiểu phép tính có thể được nâng thành `int` hoặc `long`, và kiểm tra chuyển kiểu/overflow ở những điểm có thể làm sai dữ liệu.