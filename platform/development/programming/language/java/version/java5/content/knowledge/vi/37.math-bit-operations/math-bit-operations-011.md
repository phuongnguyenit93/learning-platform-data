# Đảo bit và đảo thứ tự byte

Khi xử lý dữ liệu nhị phân, từ “đảo” có thể chỉ ba thao tác khác nhau: đổi vị trí từng bit, đổi vị trí từng nhóm 8 bit, hoặc đổi giá trị 0 thành 1 và ngược lại. Chọn sai thao tác có thể làm một trường dữ liệu trông hợp lệ nhưng mang giá trị hoàn toàn khác.

Bài này thuộc nhóm **Toán học và bit**, tập trung vào `Integer.reverse`, `Long.reverse`, `reverseBytes`, độ rộng phép biến đổi và mối liên hệ với thứ tự byte. Những API này có từ Java 5 và vẫn được cung cấp trong Java hiện đại; ví dụ dùng Java 17 trở lên, không dùng API đã lỗi thời.

## 1. Hiểu đúng ba thao tác

Hãy xét một mẫu **8 bit**, giữ cả các số 0 ở đầu:

```text
Ban đầu:                 00010110
Đảo thứ tự 8 bit:         01101000
Bù từng bit trong 8 bit:  11101001
```

Ở dòng đảo thứ tự, bit bên trái nhất chuyển sang bên phải nhất, bit thứ hai chuyển sang vị trí kế bên phải, và cứ thế tiếp tục. Mỗi bit giữ nguyên giá trị; chỉ vị trí thay đổi. Ở dòng bù, mỗi vị trí giữ nguyên nhưng 0 đổi thành 1, 1 đổi thành 0.

Đảo thứ tự byte lại làm việc với **nhóm 8 bit**. Với một mẫu 32 bit:

```text
Giá trị viết hệ 16:       0x12345678
Tách thành bốn byte:      12 34 56 78
Đảo thứ tự byte:          78 56 34 12
Giá trị kết quả:          0x78563412
```

Bên trong byte `12`, các bit không bị đảo. Trong khi đó, đảo toàn bộ 32 bit của `0x12345678` cho `0x1E6A2C48`.

| Nhu cầu | Thao tác thích hợp | Đơn vị thay đổi |
| --- | --- | --- |
| Đưa bit vị trí i sang vị trí đối xứng | `Integer.reverse`, `Long.reverse` | Từng bit |
| Đổi thứ tự các byte của một số nguyên | `reverseBytes` | Từng byte |
| Đổi mọi 0 thành 1, mọi 1 thành 0 | `~` | Giá trị tại từng vị trí |
| Dịch vòng một số vị trí | `rotateLeft`, `rotateRight` | Xoay vị trí theo khoảng dịch |

Dịch vòng không phải đảo thứ tự: các bit đi quanh một vòng, không đổi sang vị trí đối xứng.

## 2. Độ rộng là một phần của yêu cầu

Một mẫu nhị phân không đủ để xác định kết quả nếu chưa biết phải đảo bao nhiêu bit. Số 1 có thể được nhìn trong trường 8 bit hoặc trong một `int` 32 bit:

```text
Đảo 8 bit:   00000001 -> 10000000
Đảo 32 bit:  00000000000000000000000000000001
          -> 10000000000000000000000000000000
```

Trong Java, `int` có 32 bit và `long` có 64 bit. API đảo trên toàn bộ độ rộng của kiểu, kể cả các bit 0 ở đầu và bit dấu.

Các phương thức tiêu biểu:

| Phương thức | Độ rộng xử lý | Kiểu trả về |
| --- | --- | --- |
| `Integer.reverse(int)` | 32 bit | `int` |
| `Integer.reverseBytes(int)` | 4 byte | `int` |
| `Long.reverse(long)` | 64 bit | `long` |
| `Long.reverseBytes(long)` | 8 byte | `long` |
| `Short.reverseBytes(short)` | 2 byte | `short` |

Đây là phương thức `static`: gọi trực tiếp qua tên lớp, không cần tạo đối tượng wrapper. Hợp đồng của các phép đảo `int`, `long` và `short` được mô tả trong [Integer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#reverse(int)), [Long](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Long.html#reverse(long)) và [Short](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Short.html#reverseBytes(short)).

### Kết quả âm không có nghĩa là sai

`Integer.reverse(1)` tạo mẫu `0x80000000`, được hiểu là `-2147483648` nếu in ở dạng `int` thập phân có dấu. Không có thao tác “đảo riêng phần trị rồi giữ dấu”; bit dấu cũng tham gia hoán đổi.

`Integer.reverseBytes(0x00000080)` cũng cho `0x80000000`. Byte cuối chuyển lên đầu, khiến bit cao nhất thành 1.

Khi kiểm tra kết quả, nên in hệ 16 có đủ độ rộng: `%08X` cho `int`, `%016X` cho `long`. Khi cần xem `short` như một trường không dấu, chuyển qua `Short.toUnsignedInt` trước khi in.

## 3. Cơ chế: ánh xạ vị trí, không đổi số bit 1

Với một từ n bit, đảo bit đưa bit ở vị trí i đến vị trí `n - 1 - i`, đếm từ 0 ở phía thấp nhất. Ví dụ với n = 8:

```text
Vị trí cũ:  7 6 5 4 3 2 1 0
Vị trí mới: 0 1 2 3 4 5 6 7
```

Đảo byte của `int` đưa byte thứ 0 ở phía thấp lên byte thứ 3 ở phía cao, byte thứ 1 lên byte thứ 2, và ngược lại. Nó giữ nguyên thứ tự bit bên trong từng byte.

Vì chỉ hoán đổi vị trí, cả hai thao tác đều:

- Giữ nguyên số bit 1 trong cùng độ rộng.
- Áp dụng hai lần thì khôi phục mẫu ban đầu.
- Không cần biết cách CPU vật lý lưu các byte để xác định kết quả của API.

Từ đó có thể tự kiểm tra các phép tính:

```text
reverse(reverse(x)) = x
reverseBytes(reverseBytes(x)) = x
```

Các đẳng thức này phải dùng cùng kiểu và độ rộng ở cả hai lần. Nếu sau lần đầu chỉ giữ lại một phần bit bằng ép kiểu, thông tin có thể đã mất.

Đối với một mẫu gồm nhiều byte, đảo toàn bộ bit có thể hiểu thành hai việc: đảo thứ tự các byte rồi đảo 8 bit bên trong từng byte. Chỉ làm một trong hai việc chưa đủ để tương đương `reverse`.

## 4. Chương trình thực nghiệm hoàn chỉnh

Lưu thành **BitByteReversalDemo.java**. Chương trình sau có thể biên dịch với Java 17 trở lên:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Locale;

public class BitByteReversalDemo {
    static int reverseLowBits(int value, int width) {
        if (width < 1 || width > Integer.SIZE) {
            throw new IllegalArgumentException("width must be 1..32");
        }
        return Integer.reverse(value) >>> (Integer.SIZE - width);
    }

    static int reverse32ByLoop(int value) {
        int result = 0;
        for (int i = 0; i < Integer.SIZE; i++) {
            result = (result << 1) | (value & 1);
            value >>>= 1;
        }
        return result;
    }

    public static void main(String[] args) {
        int value = 0x12345678;
        int reversed = Integer.reverse(value);
        int swapped = Integer.reverseBytes(value);

        System.out.printf(Locale.ROOT, "value        = %08X%n", value);
        System.out.printf(Locale.ROOT, "reverse      = %08X%n", reversed);
        System.out.printf(Locale.ROOT, "reverseBytes = %08X%n", swapped);
        System.out.printf(Locale.ROOT, "complement   = %08X%n", ~value);
        System.out.println("bit round trip = "
                + (Integer.reverse(reversed) == value));
        System.out.println("byte round trip = "
                + (Integer.reverseBytes(swapped) == value));

        int reversedOne = Integer.reverse(1);
        System.out.printf(Locale.ROOT, "reverse(1) = %08X (%d)%n",
                reversedOne, reversedOne);

        byte sample = (byte) 0x96;
        int low8 = reverseLowBits(sample, Byte.SIZE);
        System.out.printf(Locale.ROOT, "reverse8(96) = %02X%n", low8);
        System.out.printf(Locale.ROOT, "cast reverse(byte) = %02X%n",
                Byte.toUnsignedInt((byte) Integer.reverse(sample)));

        short sample16 = (short) 0x1234;
        int reversed16 = reverseLowBits(sample16, Short.SIZE);
        int swapped16 = Short.toUnsignedInt(Short.reverseBytes(sample16));
        System.out.printf(Locale.ROOT, "reverse16(1234) = %04X%n",
                reversed16);
        System.out.printf(Locale.ROOT, "swap16(1234) = %04X%n",
                swapped16);

        long sample64 = 0x0102030405060708L;
        System.out.printf(Locale.ROOT, "reverse64 = %016X%n",
                Long.reverse(sample64));
        System.out.printf(Locale.ROOT, "swap64    = %016X%n",
                Long.reverseBytes(sample64));

        byte[] encoded = {0x78, 0x56, 0x34, 0x12};
        int asBigEndian = ByteBuffer.wrap(encoded)
                .order(ByteOrder.BIG_ENDIAN).getInt();
        int asLittleEndian = ByteBuffer.wrap(encoded)
                .order(ByteOrder.LITTLE_ENDIAN).getInt();
        System.out.printf(Locale.ROOT, "read BIG_ENDIAN    = %08X%n",
                asBigEndian);
        System.out.printf(Locale.ROOT, "read LITTLE_ENDIAN = %08X%n",
                asLittleEndian);
        System.out.println("swap BIG equals LITTLE = "
                + (Integer.reverseBytes(asBigEndian) == asLittleEndian));

        int[] cases = {0, 1, -1, Integer.MIN_VALUE,
                Integer.MAX_VALUE, value};
        boolean matches = true;
        for (int x : cases) {
            matches &= reverse32ByLoop(x) == Integer.reverse(x);
        }
        System.out.println("loop matches API = " + matches);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 BitByteReversalDemo.java
java BitByteReversalDemo
```

Stdout:

```text
value        = 12345678
reverse      = 1E6A2C48
reverseBytes = 78563412
complement   = EDCBA987
bit round trip = true
byte round trip = true
reverse(1) = 80000000 (-2147483648)
reverse8(96) = 69
cast reverse(byte) = FF
reverse16(1234) = 2C48
swap16(1234) = 3412
reverse64 = 10E060A020C04080
swap64    = 0807060504030201
read BIG_ENDIAN    = 78563412
read LITTLE_ENDIAN = 12345678
swap BIG equals LITTLE = true
loop matches API = true
```

Những dòng `round trip` kiểm tra tính khôi phục; dòng `loop matches API` đối chiếu một cách cài đặt dễ quan sát với API trên các trường hợp có bit dấu và các mẫu biên. Đây là minh chứng cho ví dụ, không phải chứng minh bằng thử nghiệm cho mọi giá trị `int`.

## 5. Vì sao đảo byte hoặc short dễ sai?

### 5.1. byte được mở rộng thành int trước khi gọi

`Integer.reverse(sample)` luôn đảo 32 bit. Trong chương trình, `sample` có 8 bit là `10010110`, tức `0x96`, được hiểu là `-106` khi mang kiểu `byte`.

Khi truyền nó vào tham số `int`, Java mở rộng dấu:

```text
byte ban đầu:       10010110
int sau mở rộng:    11111111 11111111 11111111 10010110
int sau reverse:   01101001 11111111 11111111 11111111
```

Ép thẳng kết quả trở lại `byte` chỉ giữ 8 bit thấp, tức `0xFF`, không phải `0x69`. Dòng `cast reverse(byte)` trong stdout chủ đích minh họa lỗi này.

Muốn đảo **8 bit thấp**, phải lấy nhóm 8 bit ở đầu kết quả sau khi đảo 32 bit:

```java
// Đoạn biểu thức, dùng trong một phương thức có biến sample kiểu byte.
int reversed8 = Integer.reverse(sample & 0xFF) >>> 24;
```

`sample & 0xFF` làm rõ rằng đầu vào là một trường 8 bit không dấu. Với công thức đảo rồi dịch trên, các bit cao vốn bị mở rộng dấu cuối cùng đều bị loại bỏ, nên hàm `reverseLowBits` vẫn đúng khi nhận trực tiếp một `byte` âm.

### 5.2. Đảo n bit thấp

Hàm `reverseLowBits(value, width)` trong chương trình có hợp đồng rõ ràng:

- `width` nằm trong 1..32.
- Chỉ đảo `width` bit thấp của `value`.
- Đặt kết quả trong `width` bit thấp của `int`; các bit cao còn lại bằng 0.
- Khi `width = 32`, kết quả có thể âm vì vẫn là `int`.

Sau `Integer.reverse`, n bit cần giữ nằm ở n vị trí cao nhất. Dịch phải không dấu `32 - n` đưa chúng về cuối và thêm 0 ở phía trái.

Với `short`, đảo bit 16 vị trí của `0x1234` là `0x2C48`, còn đổi chỗ hai byte là `0x3412`. Hai kết quả rất khác nhau.

Không dùng `Integer.reverseBytes(shortValue)` để đổi hai byte của một trường 16 bit: lời gọi đó vẫn xử lý **bốn byte** sau khi mở rộng thành `int`. Dùng `Short.reverseBytes` nếu yêu cầu là đổi chỗ đúng hai byte.

### 5.3. Vì sao phải dùng >>>?

`>>` dịch phải có mở rộng dấu; `>>>` dịch phải và bổ sung 0. Khi đưa các bit từ vùng cao xuống vùng thấp mà không muốn kéo thêm bit 1 của dấu, dùng `>>>`.

Ví dụ `Integer.reverse(1)` có bit cao nhất bằng 1:

```text
Integer.reverse(1) >> 24   = 0xFFFFFF80
Integer.reverse(1) >>> 24  = 0x00000080
```

Trong vòng lặp `reverse32ByLoop`, mỗi lượt lấy bit thấp bằng `value & 1`, đẩy kết quả sang trái một vị trí rồi ghép bit đó bằng `|`. Sau đúng 32 lượt, từng bit đã chuyển sang vị trí đối xứng. Dùng số lượt cố định giúp xử lý cả số âm; điều kiện `while (value > 0)` sẽ bỏ qua đầu vào âm.

Khoảng dịch `int` chỉ dùng 5 bit thấp, nên dịch 32 thực tế tương đương dịch 0; với `long`, khoảng dịch dùng 6 bit thấp. Vì vậy hàm có kiểm tra độ rộng: không nhận `width = 0`, tránh biến phép dịch 32 thành một kết quả khác ý định. Các quy tắc dịch được quy định trong [JLS §15.19](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.19).

## 6. Đảo byte và thứ tự byte trong dữ liệu

Thứ tự byte (endianness) mô tả cách các byte của một giá trị nhiều byte được sắp trong một dãy dữ liệu:

- **Big-endian:** byte có trọng số cao nhất đứng trước.
- **Little-endian:** byte có trọng số thấp nhất đứng trước.

Giá trị số `0x12345678` có thể được mã hóa:

```text
Big-endian:     12 34 56 78
Little-endian:  78 56 34 12
```

Trong chương trình, cùng dãy `78 56 34 12` được đọc hai cách, tạo hai giá trị khác nhau. `ByteBuffer.order` chọn cách diễn giải khi đọc/ghi giá trị nhiều byte; thứ tự ban đầu của `ByteBuffer` là big-endian. Xem [ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html#order(java.nio.ByteOrder)).

Khi đọc một định dạng quy định little-endian, nên khai báo rõ `order(ByteOrder.LITTLE_ENDIAN)`. Sau khi đã đọc đúng thứ tự, **không gọi thêm `reverseBytes`**, vì như vậy lại biến đổi giá trị đúng thành giá trị khác.

`reverseBytes` hữu ích khi giao diện hiện có đã đọc/ghi theo thứ tự cố định và cần chuyển đổi một giá trị tại ranh giới đó. Quyết định dựa vào **đặc tả định dạng**, không dựa vào phỏng đoán CPU đang chạy.

Phương thức này trả về giá trị mới. Nó không sửa trực tiếp mảng `byte[]`, không tự cấu hình `ByteBuffer`, và không đảo mọi byte của một tệp. Nếu bản ghi chứa hai trường 32 bit, đổi thứ tự byte từng trường cũng khác việc đảo cả 8 byte của toàn bản ghi.

Đảo thứ tự bit lại phù hợp khi thuật toán quy định ánh xạ vị trí bit, chẳng hạn bước sắp chỉ số theo dạng bit đảo trong một số thuật toán FFT hoặc quy ước bit của một định dạng. Với FFT có `2^k` phần tử, chỉ số cần đảo đúng k bit, không mặc nhiên đảo toàn bộ 32 bit.

## 7. Lỗi thường gặp và cách tự kiểm tra

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `~x` khi muốn đảo thứ tự | Đổi giá trị từng bit | Chọn `reverse` theo độ rộng |
| Nghĩ `reverse(1)` cho 1 | Bỏ qua các số 0 ở đầu | Viết mẫu đủ 32/64 bit trước khi tính |
| Ép kết quả đảo 32 bit sang byte ngay | Giữ nhầm nhóm bit thấp | Dịch không dấu về đúng vị trí trước |
| Đảo 4 byte cho dữ liệu 16 bit | Lẫn các byte mở rộng | Dùng `Short.reverseBytes` |
| Dùng `Integer.reverse` cho giá trị long | Mất hoặc không xử lý 32 bit cao | Dùng `Long.reverse`, literal có hậu tố `L` |
| Loại số âm vì tưởng dữ liệu lỗi | Bỏ sót mẫu có bit dấu | So sánh cả dạng hệ 16 và giá trị có dấu |
| Đọc little-endian rồi đảo byte lần nữa | Đảo hai lần về cách diễn giải sai | Chọn một nơi chịu trách nhiệm chuyển đổi |
| Đảo chuỗi nhị phân không đệm 0 | Sai độ rộng biểu diễn | Dùng phép toán số; chỉ dùng chuỗi để trình bày |

Khi viết mã thực tế, ưu tiên API chuẩn vì tên phương thức diễn đạt ý định rõ ràng. Vòng lặp trong bài giúp hiểu cơ chế; không cần thay thế API bằng thao tác thủ công nếu không có yêu cầu đặc biệt.

Một kiểm tra hữu ích khác là so sánh số bit 1 trước và sau đảo. Tuy vậy, riêng tính chất “đảo hai lần về ban đầu” hoặc “giữ số bit 1” chưa đủ chứng minh đã chọn đúng thao tác: cả đảo bit lẫn đảo byte đều thỏa hai tính chất. Cần có ít nhất một mẫu bất đối xứng với kết quả biết trước, như `0x12345678`.

## 8. Thực hành

1. Dự đoán `Integer.reverse(0)`, `Integer.reverse(-1)`, `Integer.reverse(Integer.MIN_VALUE)` trước khi chạy.
2. Với `0x00F0` trong đúng 16 bit, tính riêng đảo bit và đảo byte.
3. Một giao thức lưu số 32 bit bằng dãy `04 03 02 01` theo little-endian. Chọn cấu hình đọc để nhận `0x01020304`.
4. Giải thích tại sao đảo thứ tự byte của một trường đúng 1 byte không thay đổi gì, còn đảo 8 bit của nó có thể thay đổi giá trị.
5. Sửa vòng lặp để đảo 64 bit, dùng biến `long`, `1L` và đúng 64 lượt; đối chiếu với `Long.reverse`.

Đáp án để tự đối chiếu:

- Câu 1: lần lượt là `0`, `-1`, `1`.
- Câu 2: đảo bit 16 vị trí cho `0x0F00`; đảo byte cho `0xF000`.
- Câu 3: `ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).getInt()`; không đảo thêm.
- Câu 4: một byte chỉ có một nhóm để sắp thứ tự; bên trong nhóm vẫn có tám vị trí bit.
- Câu 5: thay `int` bằng `long`, `Integer.SIZE` bằng `Long.SIZE`, và biểu thức lấy bit bằng `value & 1L`. Giữ phép dịch phải không dấu và kiểm tra cả `Long.MIN_VALUE`.
