# Tiền tố `0b`, `0B` và các kiểu số nguyên trong Java

## 1. Mục đích và phạm vi

Trong mã Java, chúng ta thường ghi số ở hệ thập phân (`10`, `255`) hoặc hệ thập lục phân (`0xFF`). Khi làm việc với bit, cờ trạng thái (flags), mặt nạ bit (bit mask) hay cấu trúc dữ liệu có từng bit mang ý nghĩa riêng, việc nhìn trực tiếp các chữ số `0` và `1` thường dễ kiểm tra hơn.

Java hỗ trợ **hằng số nguyên viết ở hệ nhị phân (binary integer literal)** bằng tiền tố `0b` hoặc `0B`. Cú pháp này được bổ sung từ Java 7 và **vẫn dùng bình thường trong Java hiện đại**. Nó là cách *viết một giá trị nguyên trong mã nguồn*, không tạo ra một kiểu dữ liệu nhị phân mới và không thay đổi cách `int` hay `long` được lưu trong bộ nhớ.

Ví dụ, ba biểu thức sau cùng có giá trị số học là 10:

```java
int decimal = 10;
int binary  = 0b1010;
int hex     = 0xA;
```

Khác biệt là **cách viết**, không phải phép tính hay kiểu lưu trữ. Khi lựa chọn cách viết, hãy ưu tiên biểu diễn nào giúp người đọc hiểu ý nghĩa của số.

## 2. Cú pháp của `0b` và `0B`

Dạng tổng quát:

```text
0b<chuỗi gồm các chữ số 0 và 1>
0B<chuỗi gồm các chữ số 0 và 1>
```

- `0` đứng đầu là chữ số không; `b` hoặc `B` ngay sau báo cho trình biên dịch biết đây là hằng nguyên hệ cơ số 2. Hai tiền tố **hoàn toàn tương đương**.
- Sau tiền tố phải có ít nhất một chữ số `0` hoặc `1`. Không được dùng các chữ số `2` đến `9`.
- Có thể chèn dấu gạch dưới `_` **giữa các chữ số** để nhóm bit cho dễ đọc. `_` không làm đổi giá trị; không đặt ngay sau `0b`/`0B`, ở cuối dãy chữ số hoặc sát hậu tố `L`.
- Hằng nguyên nhị phân **không có hậu tố** thuộc kiểu `int`; thêm `L` hoặc `l` thì thuộc kiểu `long`. Nên viết `L` hoa để không nhầm với chữ số `1`.
- Dấu âm trong `-0b1010` là toán tử âm đơn ngôi tác động lên hằng số 10, nên biểu thức có giá trị -10.

Ví dụ hợp lệ:

```java
int one       = 0b1;
int ten       = 0B1010;
int grouped   = 0b1010_0101;       // 165
long wide     = 0b1_0000_0000L;    // 256
long withL    = 0b1010L;           // 10L
int negative  = -0b1010;           // -10
```

Những dòng sau *không biên dịch được*, chỉ để nhận diện lỗi cú pháp:

```java
// int a = 0b;        // Thiếu chữ số nhị phân
// int b = 0b102;     // Có chữ số 2, không hợp lệ ở cơ số 2
// int c = 0b_1010;   // Dấu _ nằm ngay sau tiền tố
// int d = 0b1010_;   // Dấu _ nằm cuối literal
// long e = 0b1_L;    // Dấu _ nằm ngay trước hậu tố L
```

**Đừng nhầm `0b1010` với `010`:** một hằng số nguyên bắt đầu bằng `0` rồi có thêm chữ số mà không có `b`/`B`/`x`/`X` thuộc dạng bát phân (cơ số 8), vì vậy `010` bằng **8**, không phải 10. Khi không chủ ý dùng hệ bát phân, hãy tránh số nguyên có số `0` đứng đầu.

## 3. Hằng nhị phân liên quan thế nào đến các kiểu số nguyên?

Java có các kiểu nguyên nguyên thủy sau:

| Kiểu | Số bit | Miền giá trị | Điểm cần nhớ |
| --- | ---: | --- | --- |
| `byte` | 8 | -128 đến 127 | Có dấu |
| `short` | 16 | -32.768 đến 32.767 | Có dấu |
| `int` | 32 | -2.147.483.648 đến 2.147.483.647 | Kiểu của literal nhị phân khi không có `L` |
| `long` | 64 | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Dùng hậu tố `L` cho literal kiểu `long` |
| `char` | 16 | 0 đến 65.535 | Không dấu; lưu **một đơn vị mã UTF-16**, không đảm bảo biểu diễn được toàn bộ một ký tự Unicode |

`char` cũng thuộc nhóm *integral types* trong ngôn ngữ Java, dù mục đích sử dụng thường là biểu diễn đơn vị mã ký tự. `float` và `double` là kiểu dấu phẩy động, không dùng hằng nhị phân có tiền tố `0b`. `boolean` không phải kiểu số nguyên.

**Điểm quan trọng:** cách viết `0b` **không tự tạo literal kiểu `byte`, `short` hoặc `char`**. Trình biên dịch áp dụng các quy tắc gán và chuyển đổi kiểu số nguyên thông thường:

```java
byte maxByte     = 0b0111_1111;   // 127: nằm trong miền byte
short shortValue = 0b1_0000_0000; // 256: nằm trong miền short
char letter      = 0b0100_0001;   // 65, tức 'A' theo UTF-16
long widened     = 0b1010;        // Literal int 10 được mở rộng sang long
long big         = 0b1_0000_0000_0000_0000_0000_0000_0000_0000L; // 2^32
```

Trường hợp `byte`, `short`, `char` ở trên được phép vì vế phải là **biểu thức hằng kiểu `int` với giá trị nằm trong miền của kiểu đích**. Quy tắc rút hẹp hằng số này không áp dụng tùy tiện cho một biến `int`:

```java
int value = 100;
// byte b = value;   // Lỗi biên dịch: không tự rút hẹp biến int sang byte
byte b = (byte) value; // Có ép kiểu tường minh; ở đây b bằng 100
```

Một literal nhị phân có 33 bit cần được viết bằng literal kiểu `long`, kể cả khi biến nhận vốn là `long`. Việc gán sang biến `long` không cứu được một **literal `int` đã không hợp lệ**:

```java
// long bad = 0b1_0000_0000_0000_0000_0000_0000_0000_0000; // 33 bit, thiếu L
long good = 0b1_0000_0000_0000_0000_0000_0000_0000_0000L;  // 4294967296
```

## 4. Bit dấu, độ rộng và bù hai

`int` là kiểu nguyên **có dấu 32 bit**, `long` có dấu 64 bit; giá trị âm được biểu diễn bằng **bù hai (two's complement)**. Với hằng nhị phân không có `L`, tối đa 32 chữ số nhị phân có ý nghĩa có thể tạo nên một literal `int`, kể cả khi bit cao nhất là 1. Với `long` dùng `L`, giới hạn tương ứng là 64 bit.

Điều này giải thích các kết quả dễ gây nhầm:

```java
int eightOnes = 0b1111_1111; // 255: chỉ ghi tám bit 1
int allOnes   = 0b1111_1111_1111_1111_1111_1111_1111_1111; // -1
int minInt    = 0b1000_0000_0000_0000_0000_0000_0000_0000; // Integer.MIN_VALUE
```

Không nên suy luận rằng `0b1111_1111` luôn là -1 chỉ vì thấy tám bit đều bằng 1: **kiểu đích và độ rộng biểu diễn quyết định cách hiểu**. Hằng `int` ở đây là 255; nếu ép xuống `byte`, tám bit thấp được giữ lại và được diễn giải là số có dấu:

```java
int bits = 0b1111_1111;             // 255
byte signedByte = (byte) bits;      // -1
int unsignedView = Byte.toUnsignedInt(signedByte); // 255
```

Dòng `byte signedByte = 0b1111_1111;` sẽ bị lỗi biên dịch do **255 vượt miền của `byte`**. Java không có kiểu nguyên thủy `unsigned byte` hoặc `unsigned int` riêng, nhưng có các hàm hỗ trợ thao tác với cách nhìn không dấu như `Byte.toUnsignedInt` và `Integer.toUnsignedString`.

Khi xử lý mặt nạ bit, hãy làm rõ bạn đang quan tâm **giá trị số học có dấu**, **mẫu bit** hay **cách hiển thị không dấu**. Đây là ba việc có liên hệ nhưng không hoàn toàn giống nhau.

## 5. Ví dụ Java chạy độc lập: chuyển đổi giá trị và phân quyền bằng bit

Mỗi bit trong một mặt nạ có thể biểu thị một quyền. Ví dụ dưới đây dùng ba bit thấp: bit 0 cho quyền đọc, bit 1 cho quyền ghi, bit 2 cho quyền thực thi. Các phép `|`, `&` và `~` lần lượt kết hợp cờ, kiểm tra cờ và hỗ trợ xóa cờ.

Tạo tệp **`BinaryLiteralDemo.java`**:

```java
public class BinaryLiteralDemo {
    private static final int READ = 0b0001;
    private static final int WRITE = 0B0010;
    private static final int EXECUTE = 0b0100;

    public static void main(String[] args) {
        int ten = 0b1010;
        int sameTen = 0B1010;
        long large = 0b1_0000_0000_0000_0000_0000_0000_0000_0000L;

        byte maxByte = 0b0111_1111;
        short shortValue = 0b1_0000_0000;
        char letter = 0b0100_0001;
        int allOnes = 0b1111_1111_1111_1111_1111_1111_1111_1111;

        int permissions = READ | WRITE;

        System.out.println("ten = " + ten);
        System.out.println("samePrefix = " + (ten == sameTen));
        System.out.println("large = " + large);
        System.out.println("maxByte = " + maxByte);
        System.out.println("shortValue = " + shortValue);
        System.out.println("letter = " + letter);
        System.out.println("allOnes = " + allOnes);
        System.out.println("hasRead = " + ((permissions & READ) != 0));
        System.out.println("hasExecute = " + ((permissions & EXECUTE) != 0));

        permissions &= ~WRITE;
        System.out.println("hasWriteAfterRemove = " + ((permissions & WRITE) != 0));
    }
}
```

Biên dịch và chạy bằng JDK hiện đại, chẳng hạn Java 17 trở lên:

```bash
javac BinaryLiteralDemo.java
java BinaryLiteralDemo
```

Kết quả chuẩn:

```text
ten = 10
samePrefix = true
large = 4294967296
maxByte = 127
shortValue = 256
letter = A
allOnes = -1
hasRead = true
hasExecute = false
hasWriteAfterRemove = false
```

**Vì sao ra kết quả này?**

- `0b1010` và `0B1010` đều bằng 10; chữ `b` viết hoa hay thường không ảnh hưởng.
- `large` có bit thứ 32 (đếm từ bit 0) bằng 1 nên có giá trị `2^32 = 4294967296`; hậu tố `L` giúp literal thuộc kiểu `long`.
- `maxByte` bằng 127, `shortValue` bằng 256; `letter` có đơn vị mã 65 nên khi in dưới dạng `char` sẽ hiển thị `A`.
- `allOnes` gồm 32 bit `1`, biểu diễn số `-1` kiểu `int` theo bù hai.
- Ban đầu `permissions = READ | WRITE = 0b0011`. Vì thế kiểm tra `READ` khác 0, còn kiểm tra `EXECUTE` bằng 0. Biểu thức `permissions &= ~WRITE` xóa bit ghi; kiểm tra `WRITE` sau đó trả `false`.

Trong chương trình thực tế, hãy đặt tên cho các cờ như `READ`, `WRITE` để tránh những số nhị phân không giải thích được ở nhiều nơi. Nếu số bit/quyền rất lớn hoặc quyền cần được diễn đạt theo đối tượng miền nghiệp vụ, có thể dùng `EnumSet` thay cho bitmask tự quản lý.

## 6. Hằng nhị phân khác chuỗi chứa chữ số nhị phân

`0b1010` là **literal trong mã nguồn**, được trình biên dịch hiểu khi biên dịch. Còn `"1010"` hay `"0b1010"` là **`String`** nhận được lúc chạy; Java không tự chuyển chuỗi có tiền tố thành số.

```java
int parsed = Integer.parseInt("1010", 2); // 10
String binaryText = Integer.toBinaryString(10); // "1010"
```

`Integer.parseInt("0b1010", 2)` **ném `NumberFormatException`**: khi có tham số cơ số 2, phương thức nhận các chữ số nhị phân, không nhận tiền tố `0b`. Nếu chuỗi đầu vào được xác nhận có tiền tố `0b` hoặc `0B`, phải bỏ tiền tố trước khi phân tích, ví dụ:

```java
String input = "0B1010";
int value = Integer.parseInt(input.substring(2), 2); // 10
```

Với đầu vào bên ngoài, cần kiểm tra định dạng và xử lý lỗi để không tùy tiện gọi `substring(2)` trên chuỗi quá ngắn hoặc sai tiền tố. `Integer.toBinaryString` cũng không tự thêm các số 0 ở đầu để đủ 32 bit; nó trả cách viết nhị phân ngắn gọn của giá trị không âm.

## 7. Lỗi thường gặp và cách chọn biểu diễn

| Tình huống | Nguyên nhân và cách xử lý |
| --- | --- |
| `0b102`, `0b_1010`, `0b1010_` | Sai chữ số hoặc vị trí dấu `_`; chỉ dùng `0`/`1` và nhóm dấu `_` giữa các chữ số |
| `byte b = 0b1000_0000;` | 128 vượt mức 127 của `byte`; cần kiểu rộng hơn hoặc ép kiểu có chủ ý và hiểu kết quả -128 |
| Literal nhị phân dài hơn 32 bit nhưng quên `L` | Literal không hậu tố vẫn thuộc `int`; thêm `L` và đảm bảo không vượt 64 bit |
| Thấy tám bit `1` rồi mặc định giá trị là -1 | `0b1111_1111` ở kiểu `int` có giá trị 255; ép về `byte` mới ra -1 |
| Viết `0b...` cho mọi số trong logic nghiệp vụ | Khó đọc khi chỉ quan tâm lượng đếm/tiền/tổng; ưu tiên thập phân cho đại lượng thông thường |
| Nhầm `0b...` với chuỗi đọc từ JSON/config/API | Tiền tố là cú pháp Java, không có nghĩa mọi bộ phân tích chuỗi hay định dạng dữ liệu khác đều chấp nhận |

**Nên chọn cách ghi nào?** Dùng **thập phân** cho đại lượng số học thông thường (`42`, `1000`); dùng **nhị phân** khi cần quan sát vị trí bit (`0b0001_0000`); dùng **thập lục phân** khi nhiều bit cần biểu diễn gọn theo nhóm 4 bit (`0xFF`, `0xA0`). Đây là lựa chọn về tính rõ ràng của mã nguồn, không phải lựa chọn về hiệu năng hay kiểu lưu trữ.

## 8. Tự kiểm tra

1. `0B1011_0100` có giá trị thập phân bao nhiêu? Điều kiện `(value & 0b0000_0100) != 0` đúng hay sai?
2. Tại sao `byte b = 0b1000_0000;` không biên dịch được, trong khi `byte b = (byte) 0b1000_0000;` lại hợp lệ?
3. Literal `0b1_0000_0000_0000_0000_0000_0000_0000_0000L` có giá trị bao nhiêu? Nếu bỏ `L` thì sao?

**Đáp án:** (1) 180 và đúng vì bit thứ 2 bằng 1. (2) 128 nằm ngoài miền `byte`; ép kiểu tường minh giữ tám bit thấp và cho -128. (3) 4.294.967.296 (`2^32`); không có `L`, literal dài 33 bit không hợp lệ ở kiểu `int`.

**Ghi nhớ:** `0b`/`0B` vẫn là cú pháp Java hợp lệ; **kiểu `int`/`long`, độ rộng bit, bit dấu và quy tắc chuyển kiểu** mới quyết định cách Java hiểu và sử dụng giá trị.