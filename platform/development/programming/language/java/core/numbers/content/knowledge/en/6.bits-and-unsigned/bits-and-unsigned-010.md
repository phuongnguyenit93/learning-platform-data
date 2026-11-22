# rotateLeft, rotateRight, reverse và reverseBytes trong Java

## 1. Bốn phép biến đổi bit giải quyết vấn đề gì?

Khi làm việc với số nguyên ở mức bit, ta thường cần xoay một dãy bit theo vòng tròn, đảo thứ tự từng bit hoặc đổi thứ tự các byte. Java cung cấp sẵn các phương thức tĩnh trên **Integer** (32 bit) và **Long** (64 bit):

| Phương thức | Ý nghĩa với dãy có độ rộng cố định | Có làm mất bit không? |
| --- | --- | --- |
| **Integer.rotateLeft(x, distance)** / **Long.rotateLeft(x, distance)** | Xoay toàn bộ bit sang trái; bit đi ra đầu trái quay về đầu phải | Không |
| **Integer.rotateRight(x, distance)** / **Long.rotateRight(x, distance)** | Xoay toàn bộ bit sang phải; bit đi ra đầu phải quay về đầu trái | Không |
| **Integer.reverse(x)** / **Long.reverse(x)** | Đảo thứ tự **mọi bit** từ đầu đến cuối | Không |
| **Integer.reverseBytes(x)** / **Long.reverseBytes(x)** | Đảo thứ tự **các byte**, giữ nguyên thứ tự 8 bit bên trong mỗi byte | Không |

Đây đều là hàm **trả về giá trị mới**: chúng không sửa biến được truyền vào. Mỗi phương thức bảo toàn số bit 1 và số bit 0 của toán hạng; thay đổi nằm ở **vị trí** các bit.

Trong Java, kiểu **int** luôn có 32 bit, **long** luôn có 64 bit và đều là kiểu **có dấu** theo biểu diễn bù hai (two's complement). Java không có kiểu nguyên thủy **unsigned int** hay **unsigned long**, nhưng các phương thức trên xử lý **mẫu bit** mà không quan tâm cách diễn giải dấu. Ví dụ, mẫu **0x80000000** là một số int âm, song bit cao nhất vẫn tham gia xoay/đảo như mọi bit khác.

## 2. Xoay bit khác dịch bit như thế nào?

Giả sử chỉ có tám bit minh họa:

~~~text
Giá trị gốc:         1000 0001
Dịch trái 1 bit:     0000 0010   (bit bên trái bị loại)
Xoay trái 1 bit:     0000 0011   (bit bên trái quay về bên phải)
Dịch phải logic 1:   0100 0000   (bit bên phải bị loại)
Xoay phải 1 bit:     1100 0000   (bit bên phải quay về bên trái)
~~~

Minh họa 8 bit này **không phải** kết quả trực tiếp của **Integer.rotateLeft** trên giá trị 0x81: **Integer** luôn xoay trên **32 bit**. Muốn xoay đúng một byte, cần mã riêng ở mục 6.

Ba toán tử Java cần phân biệt:

- **<<**: dịch trái, bỏ các bit tràn ra ngoài, thêm bit 0 bên phải.
- **>>**: dịch phải số học, lặp lại bit dấu ở phía trái.
- **>>>**: dịch phải logic, thêm bit 0 ở phía trái.

Phép xoay ghép phần đã dịch ra ngoài trở về đầu đối diện nên không mất thông tin. Với độ rộng 32 bit và khoảng xoay d, có thể hình dung:

~~~text
rotateLeft(x, d)  = (x << d) | (x >>> (32 - d))
rotateRight(x, d) = (x >>> d) | (x << (32 - d))
~~~

Đây là công thức mô tả cho **d đã chuẩn hóa trong khoảng 0..31**; sử dụng trực tiếp **Integer.rotateLeft/rotateRight** rõ ý định hơn và tự xử lý giá trị khoảng xoay bất kỳ. Với **long**, công thức tương tự dùng 64 bit. Trong Java, khoảng dịch của **int** chỉ xét 5 bit thấp, còn **long** chỉ xét 6 bit thấp; công thức minh họa không thay thế việc hiểu đúng độ rộng toán hạng.

## 3. rotateLeft và rotateRight: xoay vòng trên 32/64 bit

Với **int**, khoảng xoay có hiệu lực bằng **distance modulo 32**; với **long** là **distance modulo 64**. Do đó:

- **Integer.rotateLeft(x, 40)** tương đương **Integer.rotateLeft(x, 8)**.
- **Integer.rotateLeft(x, -8)** tương đương **Integer.rotateRight(x, 8)**.
- Xoay 0, 32 hoặc bội của 32 trên int trả về đúng mẫu bit ban đầu.
- Với long, mốc vòng quay là 64, không phải 32.

Khoảng xoay âm là hợp lệ: nó có tác dụng xoay theo chiều ngược lại. Không cần tự lấy trị tuyệt đối trước khi gọi hàm.

Ví dụ với mẫu 32 bit **0x12345678**:

~~~text
Gốc:                12 34 56 78
rotateLeft(x, 8):   34 56 78 12
rotateRight(x, 8):  78 12 34 56
~~~

Xoay một khoảng đúng bội của 8 khiến các nhóm byte trông như chuyển vị trí, nhưng **rotateLeft/rotateRight** vẫn là phép xoay trên cả dãy bit; khoảng xoay không nhất thiết phải chia hết cho 8.

### Ví dụ Java 17+ có thể chạy trực tiếp

Lưu thành **BitTransforms.java**:

~~~java
public class BitTransforms {
    public static void main(String[] args) {
        int x = 0x12345678;

        System.out.printf("int x: %08X%n", x);
        System.out.printf("int left8: %08X%n", Integer.rotateLeft(x, 8));
        System.out.printf("int right8: %08X%n", Integer.rotateRight(x, 8));
        System.out.printf("int reverse: %08X%n", Integer.reverse(x));
        System.out.printf("int reverseBytes: %08X%n", Integer.reverseBytes(x));

        System.out.println("negative distance: "
                + (Integer.rotateLeft(x, -8) == Integer.rotateRight(x, 8)));
        System.out.println("distance modulo 32: "
                + (Integer.rotateLeft(x, 40) == Integer.rotateLeft(x, 8)));
        System.out.println("rotation round trip: "
                + (Integer.rotateRight(Integer.rotateLeft(x, 8), 8) == x));
        System.out.println("reverse round trip: "
                + (Integer.reverse(Integer.reverse(x)) == x));
        System.out.println("reverseBytes round trip: "
                + (Integer.reverseBytes(Integer.reverseBytes(x)) == x));

        System.out.printf("reverse(1) hex: %08X%n", Integer.reverse(1));
        System.out.println("reverse(1) signed: " + Integer.reverse(1));

        long y = 0x0123456789ABCDEFL;
        System.out.printf("long x: %016X%n", y);
        System.out.printf("long left8: %016X%n", Long.rotateLeft(y, 8));
        System.out.printf("long right8: %016X%n", Long.rotateRight(y, 8));
        System.out.printf("long reverse: %016X%n", Long.reverse(y));
        System.out.printf("long reverseBytes: %016X%n", Long.reverseBytes(y));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BitTransforms.java
java BitTransforms
~~~

Kết quả chuẩn (stdout):

~~~text
int x: 12345678
int left8: 34567812
int right8: 78123456
int reverse: 1E6A2C48
int reverseBytes: 78563412
negative distance: true
distance modulo 32: true
rotation round trip: true
reverse round trip: true
reverseBytes round trip: true
reverse(1) hex: 80000000
reverse(1) signed: -2147483648
long x: 0123456789ABCDEF
long left8: 23456789ABCDEF01
long right8: EF0123456789ABCD
long reverse: F7B3D591E6A2C480
long reverseBytes: EFCDAB8967452301
~~~

**%08X** hiển thị int dưới dạng 8 chữ số hexa với số 0 bổ sung; **%016X** tương ứng 16 chữ số cho long. Nhờ vậy ta so sánh **mẫu bit** đầy đủ, kể cả số âm. Kết quả **Integer.reverse(1)** là **0x80000000**, có giá trị thập phân có dấu **-2147483648**; điều này không có nghĩa phép reverse tạo ra hay làm mất bit.

## 4. reverse: đảo thứ tự toàn bộ bit

**Integer.reverse(x)** ánh xạ bit ở vị trí **i** (đếm từ bit thấp nhất, bắt đầu từ 0) tới vị trí **31 - i**. **Long.reverse(x)** ánh xạ **i** tới **63 - i**.

Ví dụ trực quan trên một byte minh họa:

~~~text
Bit gốc:     1101 0010
Đảo bit:     0100 1011
~~~

Trên int, đảo diễn ra với **đúng 32 bit**; trên long là **64 bit**. Một bit thấp nhất của int trở thành bit dấu:

~~~text
Integer.reverse(0x00000001) = 0x80000000
Integer.reverse(0x80000000) = 0x00000001
~~~

**reverse** là phép đối xứng: áp dụng hai lần khôi phục nguyên mẫu bit, tức **reverse(reverse(x)) == x**. Nó cũng bảo toàn số lượng bit 1, nhưng thường **không** bảo toàn giá trị số học hay dấu.

Các trường hợp hữu ích gồm chuẩn hóa thứ tự bit theo một định dạng nhị phân được mô tả rõ, các thuật toán bitboard, thao tác thứ tự bit cho giao thức hoặc bước biến đổi trong thuật toán bit. Cần xác nhận rõ **bit order** của định dạng vì nhiều định dạng lưu **byte order** khác với **bit order**.

## 5. reverseBytes: đảo thứ tự byte, không đảo bit trong byte

Một byte có 8 bit. **Integer.reverseBytes** đổi chỗ bốn byte trên 32 bit theo mẫu:

~~~text
Gốc (32 bit):
00010010 00110100 01010110 01111000
   12       34       56       78

reverseBytes:
01111000 01010110 00110100 00010010
   78       56       34       12
~~~

**Long.reverseBytes** thực hiện tương tự với tám byte của long. Trong mỗi byte, thứ tự các bit vẫn giữ nguyên. Vì vậy:

~~~text
Integer.reverseBytes(0x00000001) = 0x01000000
Integer.reverse(0x00000001)      = 0x80000000
~~~

Hai kết quả khác nhau ở cả vị trí và ý nghĩa. Với **0x12345678**:

| Biến đổi | Kết quả hex | Điều xảy ra |
| --- | --- | --- |
| Gốc | **12345678** | Thứ tự 4 byte: 12 34 56 78 |
| **rotateLeft(x, 8)** | **34567812** | Xoay vòng 8 bit sang trái |
| **rotateRight(x, 8)** | **78123456** | Xoay vòng 8 bit sang phải |
| **reverse(x)** | **1E6A2C48** | Đảo toàn bộ 32 bit |
| **reverseBytes(x)** | **78563412** | Đảo thứ tự 4 byte |

**reverseBytes(reverseBytes(x)) == x** vì đảo thứ tự byte hai lần trở về ban đầu.

### Liên hệ với endian

**Big-endian** lưu byte quan trọng nhất trước; **little-endian** lưu byte ít quan trọng nhất trước. Đảo thứ tự byte có thể hữu ích khi **chuyển đổi biểu diễn** của một giá trị giữa hai quy ước byte order. Tuy nhiên:

- **reverseBytes** chỉ biến đổi **giá trị int/long**, không tự đổi endian của CPU, JVM, mảng byte hay luồng I/O.
- Không nên tự động gọi **reverseBytes** mỗi khi đọc/gửi dữ liệu mạng. Cần biết đặc tả giao thức và API đọc/ghi đã xử lý endian hay chưa; chuyển đổi hai lần sẽ gây sai.
- Khi làm việc với mảng byte hoặc bộ đệm, **ByteBuffer.order(ByteOrder.BIG_ENDIAN / LITTLE_ENDIAN)** giúp đọc/ghi theo endian mong muốn; đó thường là cách biểu đạt trực tiếp hơn.
- **reverseBytes** không thay thế **reverse** khi yêu cầu là đảo thứ tự từng bit; **rotateRight(x, 8)** cũng không phải phép đổi endian vì nó chỉ xoay vòng byte thay vì đảo toàn bộ thứ tự.

## 6. Cẩn thận: xoay một byte khác xoay một int

Đối với các toán tử dịch, Java áp dụng **unary numeric promotion** riêng cho từng toán hạng: **byte**, **short**, **char** ở vế trái được nâng thành **int** trước khi dịch. Truyền một byte âm tới phương thức 32 bit sẽ không tự tạo phép xoay 8 bit:

~~~java
byte b = (byte) 0x81;   // có dấu: -127
int promoted = b;       // 0xFFFFFF81 (sign extension)
int unsigned = b & 0xFF; // 0x00000081
~~~

Ngay cả khi đã che dấu bằng **& 0xFF**, gọi **Integer.rotateLeft(unsigned, 1)** vẫn xoay **32 bit**, không phải 8 bit. Muốn xoay trong miền 8 bit, hãy đưa các bit tràn quay lại trong **8 vị trí** rồi che phần ngoài byte.

Ví dụ độc lập, lưu thành **ByteRotationDemo.java**:

~~~java
public class ByteRotationDemo {
    static int rotateLeft8(int rawByte, int distance) {
        int value = rawByte & 0xFF;
        int d = distance & 7;
        return ((value << d) | (value >>> (8 - d))) & 0xFF;
    }

    static int rotateRight8(int rawByte, int distance) {
        int value = rawByte & 0xFF;
        int d = distance & 7;
        return ((value >>> d) | (value << (8 - d))) & 0xFF;
    }

    public static void main(String[] args) {
        byte b = (byte) 0x81;

        System.out.printf("promoted: %08X%n", (int) b);
        System.out.printf("unsigned: %08X%n", b & 0xFF);
        System.out.printf("left8(81, 1): %02X%n", rotateLeft8(b, 1));
        System.out.printf("right8(81, 1): %02X%n", rotateRight8(b, 1));
        System.out.printf("Integer.rotateLeft(81, 1): %08X%n",
                Integer.rotateLeft(b & 0xFF, 1));
        System.out.println("8-bit round trip: "
                + (rotateRight8(rotateLeft8(b, 3), 3) == (b & 0xFF)));
    }
}
~~~

Chạy **javac ByteRotationDemo.java** rồi **java ByteRotationDemo**, stdout:

~~~text
promoted: FFFFFF81
unsigned: 00000081
left8(81, 1): 03
right8(81, 1): C0
Integer.rotateLeft(81, 1): 00000102
8-bit round trip: true
~~~

Trong hàm phụ, **distance & 7** chuẩn hóa số bước theo modulo 8, kể cả bước âm. **& 0xFF** giới hạn kết quả còn 8 bit, tránh để các bit cao của int lọt vào giá trị byte. Nếu cần biến đổi 16 bit, hãy thiết kế tương tự với mặt nạ **0xFFFF** và modulo 16; đừng nhầm độ rộng dữ liệu với độ rộng của kiểu int.

## 7. Số không dấu: cách đọc kết quả chính xác

Phương thức xoay/đảo bit không phân biệt signed và unsigned, nhưng lúc **hiển thị, so sánh hoặc đổi kiểu** phải chọn cách hiểu phù hợp. Với int:

~~~java
int bits = 0xFFFFFFFF;
System.out.println(bits);                          // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.printf("%08X%n", bits);                  // FFFFFFFF
~~~

Với long, có **Long.toUnsignedString**, **Long.compareUnsigned**, **Long.divideUnsigned**, ... phù hợp cho thao tác số không dấu. Tuy nhiên **Integer.toUnsignedLong(x)** mở rộng mẫu 32 bit thành một **long** 64 bit có giá trị không âm; nếu sau đó gọi **Long.rotateLeft**, phép xoay sẽ diễn ra trên **64 bit**. Muốn xoay nguyên mẫu 32 bit, hãy dùng **Integer.rotateLeft** trước khi mở rộng.

Để kiểm tra bit cuối hoặc bit dấu, có thể dùng:

~~~java
int x = Integer.rotateLeft(1, 31);
boolean highBitSet = (x & 0x80000000) != 0; // true
boolean lowBitSet = (x & 1) != 0;          // false
~~~

Không suy luận rằng một phép biến đổi bit sai chỉ vì số in ra là âm: **int/long** chỉ là một cách diễn giải signed của mẫu bit. Khi phân tích dữ liệu, hãy in hex đủ chữ số hoặc biểu diễn nhị phân có bổ sung số 0 phía trước.

## 8. Tính chất quan trọng và cách tự kiểm chứng

Gọi **ROL(x, d)** và **ROR(x, d)** là hai phép xoay cùng độ rộng:

1. **ROR(ROL(x, d), d) == x** và **ROL(ROR(x, d), d) == x**.
2. **ROL(x, a + b) == ROL(ROL(x, a), b)**, với cách tính khoảng xoay theo độ rộng tương ứng.
3. **ROL(x, d) == ROR(x, -d)**, kể cả khi d lớn hơn độ rộng.
4. **reverse(reverse(x)) == x**.
5. **reverseBytes(reverseBytes(x)) == x**.

Các đẳng thức trên đúng theo **mẫu bit** kể cả với số âm, số 0, mọi bit đều 1 và các khoảng xoay âm. Trong Java, **==** so sánh được trực tiếp mẫu bit int/long vì hai phía cùng kiểu nguyên thủy.

Một số phép kiểm tra tay rất tiện:

~~~text
int 0x00000000: mọi phép biến đổi đều trả 0x00000000
int 0xFFFFFFFF: mọi phép xoay/đảo đều trả 0xFFFFFFFF
reverse(0x00000001):      0x80000000
reverseBytes(0x00000001): 0x01000000
rotateLeft(0x80000001,1): 0x00000003
rotateRight(0x80000001,1):0xC0000000
~~~

Xoay và đảo chỉ **hoán vị vị trí bit**, nên giữ nguyên số lượng bit 1. Tuy nhiên chúng không cùng một phép hoán vị và không thể thay thế cho nhau. **Integer.bitCount(x)** hoặc **Long.bitCount(x)** có thể được dùng để kiểm chứng tính bảo toàn số bit 1 nếu cần.

## 9. Ứng dụng thực tế và giới hạn

- **Hashing và trộn bit:** phép rotate thường kết hợp với XOR, cộng modulo độ rộng hoặc các phép toán khác để khuếch tán thông tin giữa các vị trí bit. Chỉ xoay bit riêng lẻ **không** tạo hàm băm tốt và **không** có tính bảo mật.
- **Giao thức/định dạng nhị phân:** **reverseBytes** hữu ích khi cần biểu diễn giá trị bằng thứ tự byte đối nghịch; **reverse** phù hợp khi đặc tả yêu cầu đảo thứ tự bit. Cần đọc kỹ đặc tả để xác định đơn vị là **bit** hay **byte**.
- **Thuật toán thao tác bit:** chuyển hướng các mặt nạ bit, xử lý bitmap/bitboard, đảo vị trí bit hoặc kiểm thử cấu trúc dữ liệu nhị phân theo độ rộng cố định.
- **Khôi phục dữ liệu:** các phép đảo và xoay đều có nghịch đảo rõ ràng, thuận tiện cho thuật toán cần biến đổi khả nghịch; chúng **không mã hóa bảo mật** dữ liệu.

Về hiệu năng, hãy ưu tiên các phương thức chuẩn của **Integer/Long**: ngữ nghĩa rõ ràng, ít lỗi dấu/khoảng dịch và cho phép JDK tối ưu theo nền tảng. Không tự khẳng định chúng luôn biên dịch thành một lệnh CPU hoặc luôn nhanh hơn mọi mã thủ công; điều đó phụ thuộc JVM, máy và bối cảnh.

## 10. Lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng **>>** thay **>>>** khi mô phỏng xoay phải | **>>** kéo dài bit dấu, làm sai phần ghép | Dùng hàm chuẩn hoặc dịch logic **>>>** |
| Nghĩ **Integer.rotateLeft** xoay đúng 8 bit khi đầu vào là byte | Phương thức luôn dùng 32 bit | Viết helper xoay 8 bit và che **& 0xFF** |
| Nhầm **reverse** với **reverseBytes** | Một bên đảo mọi bit; bên kia chỉ đảo byte | Vẽ nhóm 8 bit và đối chiếu đặc tả |
| Coi **rotateRight(x, 8)** là đổi endian | Xoay vòng khác đảo thứ tự các byte | Dùng **reverseBytes** khi thực sự cần byte swap |
| Cho rằng kết quả âm là lỗi | Bit cao nhất của int/long là bit dấu | In hex đủ độ rộng, hoặc hiển thị unsigned |
| Tự áp **% 32** rồi nghĩ mọi trường hợp âm đều dương | Toán tử **%** trong Java có thể trả số âm | Gọi thẳng **rotateLeft/Right**; hoặc chuẩn hóa phù hợp |
| Trộn **Integer** với **Long** | Độ rộng xoay thay đổi từ 32 sang 64 bit | Chọn phương thức khớp độ rộng định dạng |
| Đổi byte order hai lần | Có thể khôi phục về giá trị ban đầu nhưng làm sai dữ liệu cần truyền | Chỉ chuyển đổi ở ranh giới đã xác minh |

### Câu hỏi tự luyện

1. Với **int x = 1**, tại sao **Integer.rotateLeft(x, 1) == 2**, còn **Integer.reverse(x) == 0x80000000**?
2. Với **0x12345678**, giải thích tại sao **rotateRight(x, 8) = 0x78123456** nhưng **reverseBytes(x) = 0x78563412**.
3. Tại sao **Integer.rotateLeft(x, 40) == Integer.rotateLeft(x, 8)**, trong khi không thể lấy kết luận đó cho **Long.rotateLeft**?
4. Với một byte **0x81**, dự đoán xoay trái và xoay phải 1 bit trong **8 bit**, sau đó chạy **ByteRotationDemo** để kiểm chứng.
5. Nếu giao thức yêu cầu little-endian, bước nào trong quá trình ghi bằng **ByteBuffer** cần thể hiện byte order? Việc gọi thêm **reverseBytes** có còn đúng không?

Hiểu rõ ba khái niệm **độ rộng bit**, **thứ tự bit** và **thứ tự byte** sẽ giúp chọn đúng phép biến đổi và tránh những lỗi nhị phân rất khó nhìn thấy khi chỉ in số thập phân.