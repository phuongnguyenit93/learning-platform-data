# Byte.toUnsignedInt, Short.toUnsignedInt và Integer.toUnsignedLong

Java có các kiểu số nguyên `byte` (8 bit), `short` (16 bit), `int` (32 bit) với biểu diễn **có dấu** (bù hai). Tuy nhiên, nhiều định dạng ảnh, tệp nhị phân, ID và giao thức mạng định nghĩa trường dữ liệu theo số nguyên **không dấu**. Ba phương thức tĩnh sau giúp đọc toàn bộ mẫu bit thành giá trị không âm bằng kiểu rộng hơn, thay vì hiểu nhầm bit dấu:

- `Byte.toUnsignedInt(byte value)`: giữ 8 bit thấp, trả `int` từ **0 đến 255**.
- `Short.toUnsignedInt(short value)`: giữ 16 bit thấp, trả `int` từ **0 đến 65.535**.
- `Integer.toUnsignedLong(int value)`: giữ 32 bit thấp, trả `long` từ **0 đến 4.294.967.295**.

Các API có từ Java 8, dùng được trong Java 17+. Chúng diễn giải lại cùng bit dữ liệu bằng một **giá trị có kiểu rộng hơn**; không thay đổi biến đầu vào, không tạo thêm kiểu nguyên thủy `unsigned byte`, `unsigned short` hoặc `unsigned int` trong Java.

## 1. Vì sao phải chuyển sang giá trị không dấu?

Mẫu `1111_1111` (hex `0xFF`) có hai cách diễn giải:

- `byte` Java: **−1**, vì bit cao nhất là bit dấu trong bù hai.
- Số nguyên không dấu 8 bit: **255**, vì cả tám bit đều mang trọng số dương.

Sự khác nhau tương tự xảy ra với `short` và `int`. Ví dụ `0xFFFF` là `short -1` nhưng là unsigned 16 bit `65535`; `0xFFFF_FFFF` là `int -1` nhưng là unsigned 32 bit `4294967295`.

| Phương thức | Đầu vào | Miền có dấu của đầu vào | Kiểu kết quả | Miền không dấu của kết quả |
| --- | --- | ---: | --- | ---: |
| `Byte.toUnsignedInt(b)` | `byte` (8 bit) | −128…127 | `int` | 0…255 |
| `Short.toUnsignedInt(s)` | `short` (16 bit) | −32.768…32.767 | `int` | 0…65.535 |
| `Integer.toUnsignedLong(i)` | `int` (32 bit) | −2.147.483.648…2.147.483.647 | `long` | 0…4.294.967.295 |

Phải chọn hàm dựa trên **độ rộng của kiểu dữ liệu gốc**. Hàm `Byte.toUnsignedInt` không thay thế cho `Short.toUnsignedInt` khi đang có 16 bit; `Integer.toUnsignedLong` không đơn thuần là cách viết khác của ép `int` sang `long`.

## 2. Cơ chế zero extension và các mặt nạ bit

Việc ép `byte` âm thành `int` hoặc `int` âm thành `long` theo Java thực hiện **sign extension**: những bit mới bên trái sao chép bit dấu (1 đối với số âm). Ba hàm ở trên muốn giữ giá trị **unsigned** của đúng 8/16/32 bit ban đầu, nên loại các bit 1 do mở rộng dấu gây ra.

Có thể hiểu kết quả tương đương với phép AND sau đây:

~~~java
int u8 = Byte.toUnsignedInt(b);        // bằng b & 0xFF
int u16 = Short.toUnsignedInt(s);     // bằng s & 0xFFFF
long u32 = Integer.toUnsignedLong(i); // bằng ((long) i) & 0xFFFF_FFFFL
~~~

Đoạn trên là **mã minh họa**: giả định `b`, `s`, `i` đã được khai báo lần lượt là `byte`, `short`, `int`. Với `b & 0xFF`, phép AND giữ 8 bit thấp sau khi `byte` được nâng lên `int`. Với `s & 0xFFFF`, giữ 16 bit thấp. Với `i`, mặt nạ phải mang kiểu `long` (hậu tố `L`) để cho ra một số dương chứa đủ 32 bit.

Nếu đầu vào vốn không âm, kết quả bằng chính giá trị đầu vào. Nếu đầu vào âm, kết quả số học không dấu bằng giá trị signed cộng `2^8`, `2^16` hoặc `2^32` tương ứng. Đây là quy tắc **diễn giải giá trị**, không phải phép toán trực tiếp sửa biến gốc.

| Biểu thức | Giá trị signed tương ứng | Kết quả unsigned |
| --- | ---: | ---: |
| `Byte.toUnsignedInt((byte) 0x80)` | −128 | 128 |
| `Byte.toUnsignedInt((byte) 0xFF)` | −1 | 255 |
| `Short.toUnsignedInt((short) 0x8000)` | −32768 | 32768 |
| `Short.toUnsignedInt((short) 0xFFFF)` | −1 | 65535 |
| `Integer.toUnsignedLong(0x8000_0000)` | −2147483648 | 2147483648 |
| `Integer.toUnsignedLong(0xFFFF_FFFF)` | −1 | 4294967295 |

Lưu ý: `Byte`, `Short`, `Integer` là các **lớp wrapper**; tên phương thức là `static`, vì vậy gọi trực tiếp như bảng trên, không cần `new Byte(...)`.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp `UnsignedConversionsDemo.java`:

~~~java
public class UnsignedConversionsDemo {
    public static void main(String[] args) {
        byte b = (byte) 0xFF;
        short s = (short) 0x8001;
        int i = 0xFFFF_FFFE;

        System.out.println("byte signed: " + b);
        System.out.println("byte unsigned: " + Byte.toUnsignedInt(b));
        System.out.println("short signed: " + s);
        System.out.println("short unsigned: " + Short.toUnsignedInt(s));
        System.out.println("int signed: " + i);
        System.out.println("int unsigned: " + Integer.toUnsignedLong(i));

        System.out.println("byte mask: " + (b & 0xFF));
        System.out.println("short mask: " + (s & 0xFFFF));
        System.out.println("int mask: " + (i & 0xFFFF_FFFFL));

        byte[] packet = {
            (byte) 0xFE, (byte) 0xDC, (byte) 0xBA, (byte) 0x98
        };
        int raw32 =
                (Byte.toUnsignedInt(packet[0]) << 24)
              | (Byte.toUnsignedInt(packet[1]) << 16)
              | (Byte.toUnsignedInt(packet[2]) << 8)
              | Byte.toUnsignedInt(packet[3]);
        long packetUnsigned = Integer.toUnsignedLong(raw32);

        System.out.printf("packet=0x%08X, unsigned=%d%n",
                raw32, packetUnsigned);

        System.out.println("signed compare: " + (-1 < 1));
        System.out.println("unsigned compare: "
                + (Integer.compareUnsigned(-1, 1) > 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UnsignedConversionsDemo.java
java UnsignedConversionsDemo
~~~

Đầu ra:

~~~text
byte signed: -1
byte unsigned: 255
short signed: -32767
short unsigned: 32769
int signed: -2
int unsigned: 4294967294
byte mask: 255
short mask: 32769
int mask: 4294967294
packet=0xFEDCBA98, unsigned=4275878552
signed compare: true
unsigned compare: true
~~~

Giải thích:

- `0xFF` có 8 bit đều bằng 1. Với `byte` nó bằng `-1`; qua `Byte.toUnsignedInt` là `255`.
- `0x8001` có bit dấu 16 bit bằng 1. Với `short` nó bằng `-32767`; qua `Short.toUnsignedInt` là `32769`.
- `0xFFFF_FFFE` dưới dạng `int` là `-2`; qua `Integer.toUnsignedLong` là `4294967294L`.
- Các dòng `mask` cho thấy phép AND đúng kiểu cho kết quả bằng các API tường minh. Việc biểu diễn bằng hàm thường dễ đọc và thể hiện rõ ý định hơn.

## 4. Đọc trường nhị phân từ byte array

Giả sử một giao thức mô tả ID **unsigned 32 bit, big-endian** gồm bốn byte `FE DC BA 98`. `byte[]` Java vẫn giữ đủ bit, nhưng những phần tử bắt đầu bằng bit 1 sẽ in ra số âm.

Trong ví dụ:

1. `Byte.toUnsignedInt(packet[k])` biến từng phần tử thành số 0–255 trước khi ghép.
2. Các toán tử `<< 24`, `<< 16`, `<< 8` đặt byte ở đúng vị trí và `|` ghép đủ 32 bit. `raw32` có mẫu bit `0xFEDCBA98` (có thể âm nếu in ra như `int` signed).
3. `Integer.toUnsignedLong(raw32)` đưa mẫu 32 bit này về `long` dương `4275878552L`, phù hợp với định nghĩa ID không dấu của giao thức.

Trường 16 bit big-endian cũng có thể ghép:

~~~java
// byte[] data chứa ít nhất hai phần tử, theo thứ tự big-endian.
int unsigned16 = (Byte.toUnsignedInt(data[0]) << 8)
               | Byte.toUnsignedInt(data[1]);
~~~

Đây là mã minh họa phụ thuộc `data`. Nếu đã đọc nguyên trường bằng `ByteBuffer.getShort()`, hãy dùng `Short.toUnsignedInt(shortValue)`; nếu đọc bằng `ByteBuffer.getInt()`, dùng `Integer.toUnsignedLong(intValue)`. Hướng byte **big-endian/little-endian** do định dạng dữ liệu quy định; các phương thức `toUnsigned...` không tự đảo thứ tự byte.

Trong phép `<< 24` ở ví dụ, kết quả trung gian kiểu `int` có thể âm nhưng vẫn giữ đúng bit để ghép; bước `Integer.toUnsignedLong` sau đó mới diễn giải cả trường thành số không dấu. Không cần cố ép từng byte thành `long` chỉ vì bit cao nhất của `raw32` bằng 1.

## 5. So sánh, tính toán và giới hạn miền unsigned

Với unsigned 8/16 bit, một `int` đủ rộng để chứa trọn kết quả. Với unsigned 32 bit, cần `long` vì `int` signed chỉ tối đa `2147483647`.

Ví dụ `Integer.toUnsignedLong(-1) + 1` cho `4294967296L`, phép cộng hợp lệ trên `long`; tuy nhiên con số ấy đã **vượt miền unsigned 32 bit**. Nếu ghi trả về một trường 32 bit, hãy kiểm tra `0 <= value && value <= 0xFFFF_FFFFL` đối với biến `long value` trước khi ép `(int) value`. Ép xuống `int` lấy 32 bit thấp, kết quả có thể âm khi in ra theo cách signed của Java. Ép giá trị `4294967296L` thành `int` cho `0`: đây là **mất dữ liệu** nếu chưa kiểm tra miền.

So sánh signed và unsigned cũng khác nhau:

~~~java
int a = -1;
int b = 1;
boolean signedLess = a < b;                         // true
boolean unsignedGreater = Integer.compareUnsigned(a, b) > 0; // true
boolean sameViaLong =
        Integer.toUnsignedLong(a) > Integer.toUnsignedLong(b); // true
~~~

Đây là mã minh họa độc lập trong một khối/phương thức hợp lệ. Signed `-1` nhỏ hơn `1`, nhưng bit `0xFFFF_FFFF` tương ứng unsigned 32 bit `4294967295` lớn hơn `1`. Đừng sử dụng toán tử `<` giữa hai `int` signed khi giao thức yêu cầu thứ tự **unsigned**.

Khi dữ liệu thực sự có ý nghĩa signed (chênh lệch âm, nhiệt độ âm, số signed trong đặc tả), giữ nguyên cách diễn giải signed. Chuyển đổi không dấu là lựa chọn dựa trên **ngữ nghĩa dữ liệu nguồn**, chứ không phải mẹo làm mọi số âm biến mất.

## 6. Lỗi phổ biến và cách tránh

### 6.1. Nhầm ép kiểu với unsigned conversion

~~~java
byte b = (byte) 0xFF;
int signedByte = (int) b;                  // -1: sign extension
int unsignedByte = Byte.toUnsignedInt(b); // 255

int i = -1;
long signedInt = (long) i;                   // -1
long unsignedInt = Integer.toUnsignedLong(i); // 4294967295
~~~

Ép `byte` sang `int` và `int` sang `long` giữ **giá trị có dấu**. Các đoạn trong mục lỗi phổ biến là ví dụ nội tuyến, không phải chương trình Java độc lập.

### 6.2. Đặt hậu tố mặt nạ sai chỗ

~~~java
int i = -1;
long wrong = (long) (i & 0xFFFF_FFFF);     // -1
long correct = ((long) i) & 0xFFFF_FFFFL; // 4294967295
long preferred = Integer.toUnsignedLong(i); // 4294967295
~~~

`0xFFFF_FFFF` không có `L` là hằng `int` có toàn bit 1, tức `-1`. Phép `i & -1` vẫn ra `i`; chỉ ép lên `long` sau đó sẽ mở rộng dấu. Dùng mặt nạ `long` `0xFFFF_FFFFL`, hoặc đơn giản dùng `Integer.toUnsignedLong`.

### 6.3. Dịch bit trước khi xử lý sign extension

Với `byte` âm, Java nâng toán hạng sang `int` trước phép dịch. `>>` điền thêm bit dấu 1; `>>>` điền bit 0 nhưng **không tự tạo ra kiểu unsigned nguyên thủy**. Cách dễ hiểu để lấy nibble cao của một byte là:

~~~java
byte encoded = (byte) 0xF0;
int highNibble = Byte.toUnsignedInt(encoded) >>> 4; // 15
~~~

Nếu dịch một `byte` âm rồi dùng kết quả ngay mà không mask đúng số bit, các bit 1 do sign extension có thể ảnh hưởng. Hãy kiểm soát 8 bit trước khi thao tác.

### 6.4. Không kiểm tra dữ liệu khi thu hẹp trở lại

Ba hàm này tạo giá trị chứa được toàn bộ miền unsigned nhờ **mở rộng kiểu**. Không có điều gì ngăn bạn thực hiện cộng, nhân hoặc ép kiểu khiến kết quả vượt phạm vi mong muốn. Khi lưu về 8/16/32 bit, tự kiểm tra giá trị có phù hợp đặc tả hay không; phép cast tự nó có thể cắt các bit cao.

### 6.5. Nhầm unsigned 32 bit với unsigned 64 bit

`Integer.toUnsignedLong` chuyển unsigned **32 bit** sang một `long` dương, còn `long` Java vẫn là kiểu **signed 64 bit**. Nó không tạo giá trị dương để chứa trọn unsigned 64 bit; trường hợp đó có thể cần `Long.compareUnsigned`, `Long.toUnsignedString` hoặc `BigInteger`.

`char` có miền số nguyên 0–65535 nhưng mang ngữ nghĩa **ký tự UTF-16**. Một trường dữ liệu 16 bit không dấu đã nằm trong `short` vẫn nên đọc rõ ý định bằng `Short.toUnsignedInt`.

## 7. Câu hỏi tự luyện

**1.** Nếu `byte b = (byte) 0x80`, `(int) b` và `Byte.toUnsignedInt(b)` là gì?  
**Đáp án:** `-128` và `128`. Cùng 8 bit thấp, khác cách mở rộng và diễn giải.

**2.** Nếu `short s = (short) 0xFFFF`, kết quả `Short.toUnsignedInt(s)`?  
**Đáp án:** `65535`, vì cả 16 bit đều là 1.

**3.** `Integer.toUnsignedLong(Integer.MIN_VALUE)` bằng bao nhiêu?  
**Đáp án:** `2147483648L`, ứng với duy nhất bit 31 bằng 1 trong unsigned 32 bit.

**4.** Vì sao `(long) (i & 0xFFFF_FFFF)` có thể sai khi `i` âm?  
**Đáp án:** Mask là `int -1` nên không xóa bit dấu; ép `long` sau đó vẫn mở rộng dấu. Hãy dùng `0xFFFF_FFFFL` với `long` hoặc `Integer.toUnsignedLong(i)`.

**5.** Dữ liệu byte `FE DC BA 98` big-endian có thể lấy số không dấu bằng API nào?  
**Đáp án:** Dùng `Byte.toUnsignedInt` với từng byte để ghép 32 bit, sau đó `Integer.toUnsignedLong` để diễn giải cả trường thành `4275878552L`.

## 8. Điểm cần nhớ

- Bắt đầu từ **độ rộng dữ liệu gốc**: `byte` → `Byte.toUnsignedInt`; `short` → `Short.toUnsignedInt`; `int` → `Integer.toUnsignedLong`.
- Kết quả là **giá trị không âm trong kiểu rộng hơn**, không đổi biến đầu vào hoặc biểu diễn bit thấp.
- Khi thao tác bit, phân biệt sign extension với mask; với unsigned 32 bit, dùng hằng mặt nạ `long` nếu không dùng API.
- Khi đọc định dạng nhị phân, tuân thủ độ rộng và endian trong đặc tả; khi so sánh hoặc ghi lại, kiểm tra miền unsigned và chọn phép so sánh phù hợp.