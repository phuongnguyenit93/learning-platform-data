# Integer, Long: numberOfLeadingZeros và numberOfTrailingZeros

## 1. Đếm các bit 0 ở hai đầu của một từ bit

Một giá trị `int` có 32 bit; `long` có 64 bit. Khi xử lý cờ, mặt nạ bit hoặc thuật toán số nguyên, ta thường muốn biết:

- Từ đầu bên trái có bao nhiêu bit 0 trước bit 1 đầu tiên?
- Từ đầu bên phải có bao nhiêu bit 0 trước khi gặp bit 1?

Java cung cấp trực tiếp:

```java
int leading = Integer.numberOfLeadingZeros(value);
int trailing = Integer.numberOfTrailingZeros(value);

int longLeading = Long.numberOfLeadingZeros(longValue);
int longTrailing = Long.numberOfTrailingZeros(longValue);
```

Các biến value và longValue trong đoạn minh họa lần lượt có kiểu `int` và `long`. Cả bốn phương thức đều trả về `int`, vì số lượng bit chỉ nằm trong khoảng 0–32 hoặc 0–64.

Tên gọi:

- **Leading zeros:** các bit 0 liên tiếp ở đầu cao, bên trái.
- **Trailing zeros:** các bit 0 liên tiếp ở đầu thấp, bên phải.

Các phương thức xét biểu diễn bù hai (two's complement) có độ rộng cố định. Chúng không đếm chữ số 0 trong dạng thập phân và không đếm mọi bit 0 ở bất kỳ vị trí nào.

`Integer` và `Long` thuộc `java.lang`, không cần import. Đây là API hiện hành; ví dụ đầy đủ trong bài dùng Java 17+.

## 2. Ví dụ đọc bằng mắt với int 40

Biểu diễn đủ 32 bit của 40:

```text
00000000 00000000 00000000 00101000
```

Bit 1 cao nhất nằm ở chỉ số 5, nên trước nó có 26 bit 0: các vị trí 31 xuống 6.

Bit 1 thấp nhất nằm ở chỉ số 3, nên sau nó có 3 bit 0: các vị trí 2, 1, 0.

```java
Integer.numberOfLeadingZeros(40);  // 26
Integer.numberOfTrailingZeros(40); // 3
```

Bit 0 nằm giữa hai bit 1, tại chỉ số 4, không thuộc nhóm leading hay trailing.

Nếu cần đếm số bit 1 trong toàn bộ từ, dùng `Integer.bitCount`; nếu cần tổng số bit 0, lấy `Integer.SIZE - Integer.bitCount(value)`. Đó là câu hỏi khác với hai phương thức của bài này.

Các quy tắc của phiên bản int được mô tả trong [Integer API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#numberOfLeadingZeros(int)).

## 3. Các trường hợp phải nhớ: 0, số âm và giá trị nhỏ nhất

### Giá trị 0 trả về toàn bộ độ rộng

Nếu không có bit 1 nào, cả hai phương thức trả về số bit của kiểu:

```text
Integer.numberOfLeadingZeros(0)  = 32
Integer.numberOfTrailingZeros(0) = 32

Long.numberOfLeadingZeros(0L)    = 64
Long.numberOfTrailingZeros(0L)   = 64
```

32 và 64 ở đây không phải chỉ số bit hợp lệ. Chúng là kết quả đặc biệt cho từ bit toàn 0.

Không diễn giải trailingZeros(0) như một kết luận rằng số 0 chỉ chia hết cho một lũy thừa 2 cụ thể. Phương thức có hợp đồng theo độ rộng biểu diễn, còn bài toán phân tích thừa số của 0 cần xử lý riêng.

### Mọi số âm đều có leadingZeros bằng 0

Trong bù hai, bit cao nhất của số âm bằng 1. Do đó:

```text
numberOfLeadingZeros(-1)   = 0
numberOfLeadingZeros(-40)  = 0
```

Chúng không tính theo độ lớn tuyệt đối của số. Không cần và không nên gọi `Math.abs` trước chỉ để “bỏ dấu”: cách đó đổi mẫu bit đang xét, đồng thời `abs(MIN_VALUE)` không tạo được độ lớn dương trong cùng kiểu.

Số âm vẫn có thể có nhiều bit 0 cuối. Ví dụ -40 có dạng int:

```text
11111111 11111111 11111111 11011000
```

Ba bit cuối vẫn là 0, nên trailingZeros(-40) bằng 3.

### MIN_VALUE chỉ có một bit 1 ở đầu cao

| Giá trị | Leading zeros | Trailing zeros |
| --- | ---: | ---: |
| `Integer.MIN_VALUE` | 0 | 31 |
| `Long.MIN_VALUE` | 0 | 63 |
| -1 ở mỗi kiểu | 0 | 0 |

Bit 1 ở đầu cao đồng thời là bit dấu. Không có ngoại lệ chỉ vì giá trị số đang âm.

## 4. Độ rộng kiểu dữ liệu là một phần của kết quả

Với cùng giá trị dương 40:

```text
Integer.numberOfLeadingZeros(40) = 26
Long.numberOfLeadingZeros(40L)   = 58
```

Phiên bản long có thêm 32 bit 0 ở đầu. Trailing zeros của cả hai vẫn là 3.

Đổi int âm sang long thông thường sẽ mở rộng dấu: các bit mới ở đầu đều là 1. Nếu muốn giữ mẫu 32 bit và đặt nó trong 64 bit với phần đầu bằng 0, dùng `Integer.toUnsignedLong`.

```java
int bits = Integer.MIN_VALUE;

long signed = bits;
long zeroExtended = Integer.toUnsignedLong(bits);

Long.numberOfLeadingZeros(signed);       // 0
Long.numberOfLeadingZeros(zeroExtended); // 32
```

Cả hai được tạo từ cùng một int, nhưng mẫu 64 bit không giống nhau.

Hợp đồng đếm theo 64 bit có tại [Long API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Long.html#numberOfTrailingZeros(long)).

### Nếu dữ liệu gốc là byte hoặc short

Java nâng các kiểu nhỏ lên int khi gọi phương thức phù hợp. Một `byte` âm được mở rộng dấu, không được tự coi là từ 8 bit không dấu.

Ví dụ muốn đếm leading zeros trong đúng 8 bit của một byte:

```java
byte value = (byte) 0x80;
int unsigned = Byte.toUnsignedInt(value);
int leadingWithinByte = Integer.numberOfLeadingZeros(unsigned) - 24;
// leadingWithinByte = 0.
```

Đối với trailing zeros trong 8 bit, có thể dùng `Math.min(Byte.SIZE, Integer.numberOfTrailingZeros(unsigned))` để trường hợp byte 0 trả 8 thay vì 32. Điều quan trọng là xác định độ rộng mà bài toán thực sự muốn xét.

## 5. Tìm vị trí bit 1 cao nhất và thấp nhất

Với x khác 0:

```text
Chỉ số bit 1 cao nhất của int  = 31 - leadingZeros(x)
Chỉ số bit 1 thấp nhất của int = trailingZeros(x)

Chỉ số bit 1 cao nhất của long  = 63 - leadingZeros(x)
Chỉ số bit 1 thấp nhất của long = trailingZeros(x)
```

Các chỉ số bắt đầu tại 0 ở đầu phải.

Với x = 40, bit cao nhất ở 5 và bit thấp nhất ở 3. Với int âm, bit cao nhất luôn ở 31 nếu đang xét mẫu bit đầy đủ.

Nên xác định một kết quả “không có bit” riêng cho x = 0:

```java
static int highestSetBitIndex(int x) {
    return x == 0 ? -1 : 31 - Integer.numberOfLeadingZeros(x);
}

static int lowestSetBitIndex(int x) {
    return x == 0 ? -1 : Integer.numberOfTrailingZeros(x);
}
```

Nếu cần **mặt nạ** chỉ có một bit 1 thay vì **chỉ số**, có sẵn `Integer.highestOneBit` và `Integer.lowestOneBit`, cùng các bản long. Chúng trả 0 với đầu vào 0. Đừng nhầm kết quả “vị trí 3” với mặt nạ “giá trị 8”.

### Duyệt các bit đang bật

Có thể dùng trailing zeros để tìm bit đang bật thấp nhất, xử lý nó, rồi xóa nó:

```java
int remaining = mask;
while (remaining != 0) {
    int index = Integer.numberOfTrailingZeros(remaining);
    // Xử lý bit ở vị trí index.
    remaining &= remaining - 1;
}
```

Dòng `remaining &= remaining - 1` xóa bit 1 thấp nhất. Với mask 40, các chỉ số được thăm là 3 rồi 5. Với mask âm, thuật toán vẫn xét được toàn bộ mẫu 32 bit và kết thúc sau số bước bằng số bit 1.

Điều kiện `remaining != 0` bảo đảm không dùng giá trị 32 như một chỉ số bit.

## 6. Liên hệ với log₂, số bit cần dùng và tính chia hết

### Log₂ nguyên cho số dương

Với int x > 0:

```text
floor(log₂(x)) = 31 - Integer.numberOfLeadingZeros(x)
```

Ví dụ 2⁵ ≤ 40 < 2⁶, nên kết quả là 5.

Số bit tối thiểu để viết một số nguyên dương ở dạng nhị phân không dấu là:

```text
32 - Integer.numberOfLeadingZeros(x)
```

Với 40, cần 6 bit: 101000. Với 0, công thức cho 0; nếu cách hiển thị của ứng dụng muốn chuỗi "0" dài một ký tự, đó là quy tắc hiển thị riêng.

Với long dương, thay 31/32 bằng 63/64. Không dùng công thức log₂ số dương cho số âm mà bỏ qua điều kiện đầu vào.

### Trailing zeros đếm số thừa số 2 của số khác 0

Nếu x có k bit 0 cuối, nó có thể chia hết cho 2ᵏ nhưng không chia hết cho 2ᵏ⁺¹. Ví dụ:

```text
40 = 5 × 2³ → trailingZeros(40) = 3
```

Với số khác 0, nhận xét này cũng phù hợp cho số âm: -40 vẫn có ba thừa số 2.

Trong ứng dụng địa chỉ hoặc kích thước, k bit thấp bằng 0 cho biết mẫu bit căn chỉnh theo bội của 2ᵏ. Phải giữ rõ độ rộng và cách diễn giải có dấu/không dấu, đặc biệt khi bit cao nhất đang bật.

### Lũy thừa 2 kế tiếp cần kiểm soát tràn

Một ứng dụng của leading zeros là tìm lũy thừa 2 nhỏ nhất không nhỏ hơn n. Với int dương, kết quả dương lớn nhất loại này là 2³⁰.

```java
static int nextPositivePowerOfTwo(int n) {
    if (n < 1 || n > (1 << 30)) {
        throw new IllegalArgumentException("n out of supported range");
    }
    if (n == 1) {
        return 1;
    }
    int exponent = 32 - Integer.numberOfLeadingZeros(n - 1);
    return 1 << exponent;
}
```

Trừ 1 để đầu vào vốn là lũy thừa 2 không bị đẩy sang lũy thừa tiếp theo. Ví dụ n = 64 thì n - 1 = 63, exponent bằng 6, kết quả vẫn là 64.

Đây là hàm có miền hỗ trợ tường minh. Nếu n lớn hơn 2³⁰, lũy thừa tiếp theo 2³¹ không thể biểu diễn thành int dương. Trả một số âm do tràn sẽ làm sai ý nghĩa “kích thước dương”.

## 7. Lỗi dịch bit khi dùng kết quả cho đầu vào 0

Khoảng dịch của int chỉ dùng 5 bit thấp; khoảng dịch của long chỉ dùng 6 bit thấp. Do đó:

```text
1 << 32   = 1
1L << 64  = 1
```

Nếu viết:

```java
int bit = 1 << Integer.numberOfTrailingZeros(x);
```

với x = 0, kết quả là 1, không phải 0. Lý do là trailing zeros trả 32 rồi khoảng dịch bị quy về 0.

Cần kiểm tra x = 0 trước hoặc dùng `Integer.lowestOneBit(x)` khi đó chính là mục đích.

Một lỗi khác là dùng literal int cho mặt nạ long:

```java
long wrong = 1 << 40;   // Phép dịch vẫn diễn ra trên int: kết quả 256.
long right = 1L << 40;  // Phép dịch trên long: kết quả 1099511627776.
```

Việc gán sang biến long diễn ra sau phép dịch, nên không thể khôi phục bit đã đặt sai. Tương tự, ép long xuống int trước khi đếm có thể xóa toàn bộ bit cao mà bài toán muốn xét.

## 8. Chương trình hoàn chỉnh

Lưu thành `ZeroBitCountsDemo.java`. Chương trình kiểm tra các trường hợp biên, sự khác nhau giữa int/long và hai ứng dụng đơn giản.

```java
public class ZeroBitCountsDemo {
    private static void row(int x) {
        System.out.println(x + " | "
                + Integer.numberOfLeadingZeros(x) + " | "
                + Integer.numberOfTrailingZeros(x));
    }

    private static int highestSetBitIndex(int x) {
        return x == 0 ? -1 : 31 - Integer.numberOfLeadingZeros(x);
    }

    private static int lowestSetBitIndex(int x) {
        return x == 0 ? -1 : Integer.numberOfTrailingZeros(x);
    }

    private static int nextPositivePowerOfTwo(int n) {
        if (n < 1 || n > (1 << 30)) {
            throw new IllegalArgumentException("n out of supported range");
        }
        if (n == 1) {
            return 1;
        }
        int exponent = 32 - Integer.numberOfLeadingZeros(n - 1);
        return 1 << exponent;
    }

    public static void main(String[] args) {
        System.out.println("int | leading | trailing");
        for (int x : new int[] {0, 1, 8, 40, -40, Integer.MIN_VALUE, -1}) {
            row(x);
        }

        System.out.println("long40.leading=" + Long.numberOfLeadingZeros(40L));
        System.out.println("long40.trailing=" + Long.numberOfTrailingZeros(40L));
        System.out.println("longZero.leading=" + Long.numberOfLeadingZeros(0L));
        System.out.println("longZero.trailing=" + Long.numberOfTrailingZeros(0L));
        System.out.println("longMin.leading="
                + Long.numberOfLeadingZeros(Long.MIN_VALUE));
        System.out.println("longMin.trailing="
                + Long.numberOfTrailingZeros(Long.MIN_VALUE));

        long bit40 = 1L << 40;
        System.out.println("bit40.leading=" + Long.numberOfLeadingZeros(bit40));
        System.out.println("bit40.trailing=" + Long.numberOfTrailingZeros(bit40));
        System.out.println("truncatedBit40.trailing="
                + Integer.numberOfTrailingZeros((int) bit40));

        int signedBits = Integer.MIN_VALUE;
        System.out.println("signedWiden.leading="
                + Long.numberOfLeadingZeros((long) signedBits));
        System.out.println("zeroExtend.leading="
                + Long.numberOfLeadingZeros(Integer.toUnsignedLong(signedBits)));

        System.out.println("highest40=" + highestSetBitIndex(40));
        System.out.println("lowest40=" + lowestSetBitIndex(40));
        System.out.println("highestZero=" + highestSetBitIndex(0));
        System.out.println("lowestZero=" + lowestSetBitIndex(0));
        System.out.println("floorLog2Of40="
                + (31 - Integer.numberOfLeadingZeros(40)));

        StringBuilder indexes = new StringBuilder();
        int remaining = 40;
        while (remaining != 0) {
            if (indexes.length() > 0) {
                indexes.append(",");
            }
            indexes.append(Integer.numberOfTrailingZeros(remaining));
            remaining &= remaining - 1;
        }
        System.out.println("setBitIndexes=" + indexes);

        System.out.println("nextPow2Of1=" + nextPositivePowerOfTwo(1));
        System.out.println("nextPow2Of40=" + nextPositivePowerOfTwo(40));
        System.out.println("nextPow2Of64=" + nextPositivePowerOfTwo(64));
        try {
            nextPositivePowerOfTwo((1 << 30) + 1);
        } catch (IllegalArgumentException exception) {
            System.out.println("nextPow2Overflow=rejected");
        }

        System.out.println("zeroShiftTrap="
                + (1 << Integer.numberOfTrailingZeros(0)));
        System.out.println("wrongIntShift=" + (1 << 40));
        System.out.println("rightLongShift=" + (1L << 40));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ZeroBitCountsDemo.java
java ZeroBitCountsDemo
```

Stdout:

```text
int | leading | trailing
0 | 32 | 32
1 | 31 | 0
8 | 28 | 3
40 | 26 | 3
-40 | 0 | 3
-2147483648 | 0 | 31
-1 | 0 | 0
long40.leading=58
long40.trailing=3
longZero.leading=64
longZero.trailing=64
longMin.leading=0
longMin.trailing=63
bit40.leading=23
bit40.trailing=40
truncatedBit40.trailing=32
signedWiden.leading=0
zeroExtend.leading=32
highest40=5
lowest40=3
highestZero=-1
lowestZero=-1
floorLog2Of40=5
setBitIndexes=3,5
nextPow2Of1=1
nextPow2Of40=64
nextPow2Of64=64
nextPow2Overflow=rejected
zeroShiftTrap=1
wrongIntShift=256
rightLongShift=1099511627776
```

`truncatedBit40.trailing=32` cho thấy phép ép kiểu đã biến mẫu chỉ có bit 40 thành int 0. Phương thức đếm không sai; đầu vào đã bị thay đổi trước khi gọi.

Hai dòng về mở rộng dấu và mở rộng bằng 0 cho thấy kiểu đích long không tự nói rõ ý định của dữ liệu. Cần chọn phép chuyển đổi phù hợp.

## 9. Cách dùng rõ ràng và những lỗi phổ biến

- Xác định ngay đang xét 8, 16, 32 hay 64 bit; API Integer/Long luôn dùng độ rộng riêng của chúng.
- Xử lý 0 trước khi đổi số lượng zero thành vị trí bit hoặc khoảng dịch.
- Không bỏ qua bit dấu khi làm việc với số âm.
- Không dùng độ dài của `Integer.toBinaryString` như thể nó luôn chứa đủ 32 bit. Với số dương, phương thức đó bỏ các số 0 đầu.
- Không thay leading zeros bằng phép log dấu phẩy động; bài toán vị trí bit có thể giải chính xác bằng API số nguyên.
- Không coi trailing zeros là số chữ số 0 cuối trong hệ 10. Ví dụ 40 có một chữ số 0 thập phân cuối, nhưng ba bit 0 cuối.
- Không dùng `1 << k` khi cần mặt nạ long ở vị trí cao; dùng `1L << k`.
- Không hứa hẹn một số lệnh CPU cố định cho mọi JVM. JIT có thể tối ưu các phương thức này, nhưng hợp đồng Java chủ yếu quy định kết quả, không quy định một lệnh máy cụ thể.

Dùng phương thức thư viện giúp ý định rõ và bao phủ sẵn trường hợp 0. Nếu tự viết vòng lặp minh họa, phải hiểu khác biệt giữa dịch phải có dấu `>>` và không dấu `>>>`: một vòng dịch `>>` số âm cho đến 0 có thể không kết thúc vì dấu được lấp lại.

## 10. Thực hành

1. Dự đoán leading/trailing zeros của int 12, 64, -64 và 0x00010000, rồi kiểm chứng.
2. Với cùng mẫu 0x80000000, so sánh kết quả khi giữ int, mở rộng dấu sang long và mở rộng bằng 0 sang long.
3. Viết hai hàm tìm vị trí bit cao nhất/thấp nhất cho long; thống nhất kết quả -1 với đầu vào 0.
4. Duyệt các bit đang bật của mask `0b10110000`. Thứ tự chỉ số là gì? Vì sao số vòng lặp không bằng tổng độ rộng từ bit?
5. Kiểm tra hàm lũy thừa 2 kế tiếp với 1, 2, 3, 2³⁰ và 2³⁰ + 1. Vì sao cần từ chối trường hợp cuối?
6. Viết hàm đếm leading/trailing zeros trong một byte không dấu, bảo đảm byte 0 cho kết quả 8 ở cả hai hướng.

Gợi ý: int 12 có leading = 28, trailing = 2; 64 có leading = 25, trailing = 6; -64 có leading = 0, trailing = 6; 0x00010000 có leading = 15, trailing = 16. Các bit của 0b10110000 được thăm theo thứ tự 4, 5, 7.
