# Thu hẹp số nguyên và phần bit bị loại bỏ — Java 17+

Khi chuyển một giá trị số nguyên sang kiểu nguyên **hẹp hơn** trong Java, kết quả không được bảo đảm giữ nguyên giá trị. Với các phép chuyển `long -> int`, `int/long -> short`, `int/long -> byte` hoặc `int/long -> char`, Java **loại bỏ các bit cao** và giữ các bit thấp phù hợp với độ rộng kiểu đích. Sau đó, giá trị được diễn giải theo quy tắc **có dấu hoặc không dấu** của kiểu đích.

Đây là hành vi được ngôn ngữ quy định, **không phải ngoại lệ tràn số**. Viết cast `(byte)` hoặc `(short)` chỉ yêu cầu chuyển kiểu; nó không kiểm tra giá trị có nằm trong miền đích hay không.

## 1. Nhớ miền giá trị và số bit

| Kiểu | Độ rộng | Diễn giải | Miền |
| --- | ---: | --- | --- |
| `byte` | 8 bit | Số nguyên có dấu, bù hai | −128 đến 127 |
| `short` | 16 bit | Số nguyên có dấu, bù hai | −32.768 đến 32.767 |
| `char` | 16 bit | Đơn vị mã UTF-16 **không dấu** | 0 đến 65.535 |
| `int` | 32 bit | Số nguyên có dấu, bù hai | −2.147.483.648 đến 2.147.483.647 |
| `long` | 64 bit | Số nguyên có dấu, bù hai | −2⁶³ đến 2⁶³−1 |

**Đặc biệt:** `short` và `char` cùng có 16 bit nhưng diễn giải **khác nhau**. Cùng một mẫu bit `0xABCD` sẽ là `-21555` nếu nhìn như `short`, nhưng là `43981` nếu nhìn như `char`.

## 2. Quy tắc giữ bit thấp

Khi thu hẹp số nguyên xuống `n` bit:

1. Lấy biểu diễn nhị phân của giá trị nguồn.
2. **Giữ đúng `n` bit thấp nhất**, bỏ tất cả bit cao hơn.
3. Đọc mẫu bit còn lại theo kiểu đích: `byte`/`short`/`int` có dấu; `char` không dấu.

Ví dụ `int 130` có 16 bit thấp như sau:

~~~text
Giá trị gốc 130:      00000000 10000010
Giữ 8 bit thấp:                10000010
Bỏ 8 bit cao:         xxxxxxxx
                                     
(byte) 130:                    10000010  →  -126
Diễn giải không dấu:           10000010  →   130
~~~

Mẫu bit `10000010` có bit cao nhất bằng 1, nên `byte` diễn giải theo bù hai thành `-126`. Trong khi đó, `Byte.toUnsignedInt((byte) 130)` cho `130` vì diễn giải tám bit đó như số **không dấu**.

Ví dụ thứ hai, `int 0x1234ABCD` chuyển sang 16 bit:

~~~text
int 32 bit:    0x1234 ABCD
Loại bit cao:  0x1234 ----
Giữ bit thấp:  0x---- ABCD

(short) 0x1234ABCD → -21555
(char)  0x1234ABCD →  43981
~~~

## 3. Chương trình Java 17+ chạy được

Tạo tệp UTF-8 tên **`NarrowingBitsDemo.java`**:

~~~java
public class NarrowingBitsDemo {
    private static String bits8(int value) {
        return String.format("%8s",
                Integer.toBinaryString(value & 0xFF))
                .replace(' ', '0');
    }

    private static String bits16(int value) {
        return String.format("%16s",
                Integer.toBinaryString(value & 0xFFFF))
                .replace(' ', '0');
    }

    public static void main(String[] args) {
        int source = 130;
        byte narrowed = (byte) source;

        System.out.println("130.binary16=" + bits16(source));
        System.out.println("130.low8=" + bits8(narrowed));
        System.out.println("130.asByte=" + narrowed);
        System.out.println("130.asUnsignedByte="
                + Byte.toUnsignedInt(narrowed));

        System.out.println("255.asByte=" + (byte) 255);
        System.out.println("256.asByte=" + (byte) 256);
        System.out.println("-129.asByte=" + (byte) -129);

        int hex = 0x1234ABCD;
        System.out.printf("hex.original=0x%08X%n", hex);
        System.out.printf("hex.low16=0x%04X%n", hex & 0xFFFF);
        System.out.println("hex.asShort=" + (short) hex);
        System.out.println("hex.asCharCode=" + (int) (char) hex);

        long large = 0x1_0000_0001L;
        System.out.println("long.asInt=" + (int) large);

        byte counter = 127;
        counter += 1;
        System.out.println("compoundWrap=" + counter);

        try {
            Math.toIntExact(large);
            System.out.println("toIntExact=ok");
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact=overflow");
        }

        boolean fitsByte = source >= Byte.MIN_VALUE
                && source <= Byte.MAX_VALUE;
        System.out.println("fitsByte130=" + fitsByte);
    }
}
~~~

Mở **PowerShell** (Windows) hoặc **Bash** (Linux/macOS) trong thư mục chứa file. Cần JDK 17 hoặc mới hơn:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NarrowingBitsDemo.java
java NarrowingBitsDemo
~~~

**Expected output chính xác của lệnh `java NarrowingBitsDemo`:**

~~~text
130.binary16=0000000010000010
130.low8=10000010
130.asByte=-126
130.asUnsignedByte=130
255.asByte=-1
256.asByte=0
-129.asByte=127
hex.original=0x1234ABCD
hex.low16=0xABCD
hex.asShort=-21555
hex.asCharCode=43981
long.asInt=1
compoundWrap=-128
toIntExact=overflow
fitsByte130=false
~~~

Các lệnh `java -version` và `javac -version` hiển thị thông tin phụ thuộc môi trường; khối trên chỉ mô tả kết quả chương trình.

## 4. Giải thích từng nhóm kết quả

### Từ `int` sang `byte`

`130` viết dưới dạng 16 bit là `0000000010000010`. Ép thành `byte` giữ tám bit thấp `10000010`, được Java diễn giải có dấu thành `-126`.

`Byte.toUnsignedInt(narrowed)` **không đổi lại đối tượng hay bit trong byte**. Phương thức này tạo giá trị `int` biểu diễn chính tám bit của `byte` như số nguyên không dấu từ 0 đến 255.

| Giá trị nguồn | 8 bit thấp | Giá trị `byte` sau cast |
| ---: | --- | ---: |
| `127` | `01111111` | 127 |
| `128` | `10000000` | −128 |
| `130` | `10000010` | −126 |
| `255` | `11111111` | −1 |
| `256` | `00000000` | 0 |
| `-129` | `01111111` | 127 |

Có thể hình dung kết quả không dấu là phần dư theo `2^8 = 256`, sau đó nếu bit dấu bằng 1 thì `byte` diễn giải kết quả trong miền âm. **Không** hiểu phép cast là “chặn giá trị ở −128 hoặc 127”: Java không làm điều đó cho phép thu hẹp số nguyên.

### Từ `int` sang `short` và `char`

Giá trị nguồn `0x1234ABCD` gồm 32 bit. Hai kiểu đích chỉ giữ **16 bit thấp** là `0xABCD`.

- Với `short`, `0xABCD` bằng 43981 nếu xem không dấu, nhưng vì bit dấu 16 bit bằng 1, giá trị có dấu là `43981 - 65536 = -21555`.
- Với `char`, `0xABCD` được đọc **không dấu**, nên giá trị là `43981`. Đây là một UTF-16 code unit, không mặc định là một ký tự hiển thị hoàn chỉnh.

Chỉ việc ép sang `char` không làm giá trị trở thành chuỗi `String`. Để in mã số của `char`, ví dụ dùng `(int) (char) hex` như chương trình.

### Từ `long` sang `int`

`0x1_0000_0001L` tương đương `4294967297` (một lớn hơn `2^32`). Khi ép sang `int`, Java giữ 32 bit thấp `0x00000001`, nên kết quả bằng **1**. Việc mất bit cao này có thể khiến mã định danh, bộ đếm hoặc phép tính sai nghiêm trọng nếu lập trình viên không kiểm tra miền.

## 5. Ép kiểu tường minh không có nghĩa “an toàn”

~~~java
int source = 130;
byte b = (byte) source; // Hop le ve cu phap, nhung b = -126.
~~~

Compiler chấp nhận cast vì người lập trình đã yêu cầu chuyển đổi. Nhưng compiler **không suy ra đây là lựa chọn đúng về nghiệp vụ**.

Cách kiểm tra trước khi ép về `byte`:

~~~java
int value = 130;

if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
    throw new IllegalArgumentException("Out of byte range");
}

byte narrowed = (byte) value;
~~~

Cách tương tự áp dụng cho `short` (`Short.MIN_VALUE`/`Short.MAX_VALUE`), `char` (0 đến `Character.MAX_VALUE`) và các kiểu số nguyên khác. Khi thu hẹp `long` sang `int`, Java 17 hỗ trợ:

~~~java
int exact = Math.toIntExact(42L); // 42.

// Math.toIntExact(0x1_0000_0001L) nem ArithmeticException.
~~~

`Math.toIntExact` kiểm tra **toàn bộ giá trị `long` có nằm trong miền `int` không**, không chỉ lấy các bit thấp. Không có phương thức `Math.toByteExact` chuẩn tương đương; muốn ép `int` về `byte` cần kiểm tra miền như trên hoặc dùng thư viện được lựa chọn rõ ràng.

## 6. Phép gán hằng và phép toán gán kết hợp

Hai quy tắc Java dễ khiến người học nhầm là Java luôn tự động thu hẹp:

**A. Hằng số nguyên nằm trong miền:**

~~~java
byte ok = 100;          // Hop le: hang int 100 nam trong mien byte.
// byte bad = 130;      // Loi bien dich: vuot mien byte.
byte casted = (byte) 130; // Hop le, gia tri -126.
~~~

Compiler cho phép một số biểu thức hằng kiểu `int` được gán cho `byte`/`short`/`char` nếu giá trị nằm trong miền. Nhưng một biến `int` bất kỳ **không** tự được gán sang `byte`:

~~~java
int n = 100;
// byte x = n;      // Loi: can cast.
byte x = (byte) n;  // Hop le.
~~~

**B. Phép gán kết hợp có ép kiểu ngầm:**

~~~java
byte count = 127;
count += 1; // Hop le: ket qua ve byte -> -128.

// count = count + 1; // Loi bien dich: phep cong la int.
~~~

Ở biểu thức số học `count + 1`, `count` được nâng thành `int` và kết quả có kiểu `int`. Với `count += 1`, Java áp dụng phép toán gán kết hợp và chuyển về kiểu bên trái, tương đương về hiệu ứng kiểu với phép cast xuống `byte`. Vì vậy phép tăng này **cũng có thể làm mất bit**.

## 7. Phân biệt hai cơ chế thường bị lẫn

**Thu hẹp số nguyên → số nguyên:** giữ các bit thấp và diễn giải kiểu đích theo quy tắc có dấu/không dấu; ví dụ `(byte) 130 == -126`.

**Ép số thực → số nguyên:** **không** đơn giản lấy bit thấp của biểu diễn số thực. Java áp dụng quy tắc chuyển từ floating-point sang integral, gồm cắt phần thập phân về 0, xử lý `NaN` và giới hạn giá trị khi vượt miền. Ví dụ `(int) 12.9 == 12`.

Bài này tập trung vào **phần bit bị loại bỏ khi thu hẹp giữa các kiểu số nguyên**. Không dùng mô hình “giữ bit thấp” để giải thích mọi phép cast trong Java.

## 8. Bài tập tự kiểm tra

**Bài 1.** Kết quả `(byte) 128` và `(byte) 256` là bao nhiêu?

*Đáp án:* `-128` và `0`, vì tám bit thấp lần lượt là `10000000` và `00000000`.

**Bài 2.** Tại sao `(short) 0x1234ABCD` là `-21555`?

*Đáp án:* Chỉ giữ 16 bit thấp `0xABCD`; diễn giải 16 bit có dấu thành `43981 - 65536 = -21555`.

**Bài 3.** Với cùng nguồn trên, `(int) (char) 0x1234ABCD` bằng bao nhiêu?

*Đáp án:* `43981`, vì `char` giữ 16 bit thấp và không có dấu.

**Bài 4.** `(int) 0x1_0000_0001L` trả giá trị nào? Có ném exception không?

*Đáp án:* Trả **1**, không tự ném ngoại lệ khi cast. `Math.toIntExact` mới báo `ArithmeticException` do vượt miền `int`.

**Bài 5.** `byte b = 127; b += 1;` cho kết quả gì? Tại sao?

*Đáp án:* `-128`. Phép cộng tính bằng `int` nhưng `+=` có chuyển về kiểu `byte`, làm mất các bit cao hơn tám bit.

## Checklist ghi nhớ

- [ ] Xác định **độ rộng bit** của kiểu nguồn và kiểu đích.
- [ ] Thu hẹp **nguyên → nguyên** giữ các bit thấp, loại bit cao.
- [ ] `byte`/`short`/`int` có dấu; `char` là 16 bit không dấu.
- [ ] Cast hợp lệ về cú pháp không có nghĩa giá trị không thay đổi.
- [ ] Kiểm tra miền trước khi cast khi việc mất dữ liệu là lỗi.
- [ ] `Math.toIntExact` giúp kiểm tra `long -> int`.
- [ ] Lưu ý chuyển kiểu ở `+=` và các phép toán số học với `byte`, `short`.
- [ ] Không áp dụng quy tắc giữ bit thấp để giải thích cast `double -> int`.

**Kết luận:** Khi thu hẹp giữa các kiểu số nguyên của Java, câu hỏi chính là **“những bit nào bị bỏ và những bit còn lại sẽ được diễn giải có dấu hay không dấu?”**. Nếu cần dữ liệu chính xác, đừng cast mù; hãy kiểm tra miền hoặc chọn kiểu đủ rộng từ đầu.
