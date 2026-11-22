# Literal số nguyên thập phân, nhị phân, bát phân và thập lục phân trong Java

> **Java core — language-basics / Literal**  
> **Môi trường:** JDK 17 trở lên, không cần thư viện ngoài.  
> **Mục tiêu:** Viết và đọc đúng literal số nguyên ở cơ số 10, 2, 8, 16; hiểu tiền tố, hậu tố `L`, dấu gạch dưới `_`, giới hạn `int`/`long` và cách Java diễn giải các bit thành số có dấu. Tự biên dịch, chạy chương trình và phân biệt literal trong source với chuỗi số được nhập lúc chạy.

## 1. Literal số nguyên là gì?

**Integer literal** là cách viết trực tiếp một giá trị số nguyên **trong mã nguồn Java**. Chẳng hạn:

~~~java
int students = 42;
long population = 8_000_000_000L;
~~~

`42` và `8_000_000_000L` là các literal; `students` và `population` là tên biến; `int` và `long` là các từ khóa kiểu dữ liệu.

Cùng một giá trị nguyên có thể được viết bằng nhiều cơ số. Java 17 hỗ trợ bốn hệ ký số nguyên phổ biến:

| Cơ số | Cách viết literal | Các chữ số hợp lệ | Ví dụ biểu diễn giá trị 42 |
| --- | --- | --- | --- |
| **Thập phân (10)** | Không cần tiền tố | `0–9` | `42` |
| **Nhị phân (2)** | `0b` hoặc `0B` | `0`, `1` | `0b101010` |
| **Bát phân (8)** | Bắt đầu bằng `0` và có thêm chữ số bát phân | `0–7` | `052` |
| **Thập lục phân (16)** | `0x` hoặc `0X` | `0–9`, `a–f`, `A–F` | `0x2A` |

Ở ví dụ trên, bốn literal đều mang giá trị **42** khi được gán vào `int`. Tên cơ số mô tả **cách viết hằng số trong source**, không tạo ra bốn kiểu biến khác nhau.

**Cẩn thận với số 0 đứng đầu:** `010` có giá trị **8**, không phải 10. Số `09` lại là lỗi vì `9` không phải chữ số bát phân. Khi muốn biểu diễn số thập phân 10, viết `10` — không viết `010`.

## 2. Quy tắc quy đổi cơ số

Giá trị của một số theo cơ số `b` là tổng của các chữ số nhân với lũy thừa của `b` tương ứng vị trí:

\[
(d_n \ldots d_1d_0)_b=\sum_{i=0}^{n} d_i b^i
\]

Ví dụ với cùng số 42:

| Literal | Cách tính | Kết quả thập phân |
| --- | --- | ---: |
| `42` | `4 × 10 + 2` | 42 |
| `0b101010` | `1×32 + 0×16 + 1×8 + 0×4 + 1×2 + 0×1` | 42 |
| `052` | `5×8 + 2` | 42 |
| `0x2A` | `2×16 + A(10)` | 42 |

Từ `A` đến `F` trong hệ 16 đại diện lần lượt cho giá trị 10 đến 15. Trong hệ 2, `1010` là mười; trong hệ 8, `52` là bốn mươi hai; đừng đọc tất cả các chuỗi chữ số như số thập phân.

**Khi chọn cách viết:** cơ số 10 dễ đọc cho số lượng; cơ số 2 hữu ích cho bit flag; cơ số 8 hay xuất hiện ở một số ngữ cảnh quyền truy cập/tương thích cũ; cơ số 16 giúp nhìn nhóm bit gọn hơn, ví dụ mặt nạ `0xFF`. Hãy chọn cách viết rõ ý đồ thay vì chỉ vì có thể viết nhiều cơ số.

## 3. Chương trình Java 17+ chạy được: IntegerLiteralsDemo.java

Tạo file **IntegerLiteralsDemo.java** với nội dung:

~~~java
public class IntegerLiteralsDemo {
    public static void main(String[] args) {
        int decimal = 42;
        int binary = 0b101010;
        int octal = 052;
        int hexadecimal = 0x2A;

        System.out.println("values=" + decimal + "," + binary
                + "," + octal + "," + hexadecimal);
        System.out.println("equal=" + (decimal == binary
                && binary == octal && octal == hexadecimal));

        System.out.println("leadingZero010=" + 010);
        System.out.println("grouped=" + 1_000_000);

        System.out.println("binaryOf42=" + Integer.toBinaryString(decimal));
        System.out.println("octalOf42=" + Integer.toOctalString(decimal));
        System.out.println("hexOf42=" + Integer.toHexString(decimal));

        int allBits = 0xFFFF_FFFF;
        long positiveLong = 0xFFFF_FFFFL;
        System.out.println("intBits=" + allBits);
        System.out.println("longBits=" + positiveLong);
        System.out.println("unsignedIntBits=" + Integer.toUnsignedLong(allBits));

        System.out.println("parseHex=" + Integer.parseInt("2A", 16));
    }
}
~~~

**Biên dịch và chạy** trong Bash, PowerShell hoặc Command Prompt tại thư mục chứa file:

~~~bash
javac -encoding UTF-8 IntegerLiteralsDemo.java
java IntegerLiteralsDemo
~~~

Nếu biên dịch thành công, `javac` thường không in gì. Lệnh `java` cho **đúng các dòng sau**:

~~~text
values=42,42,42,42
equal=true
leadingZero010=8
grouped=1000000
binaryOf42=101010
octalOf42=52
hexOf42=2a
intBits=-1
longBits=4294967295
unsignedIntBits=4294967295
parseHex=42
~~~

**Giải thích ba kết quả quan trọng:**

1. `42`, `0b101010`, `052` và `0x2A` có cách viết khác nhau nhưng cùng giá trị; `==` giữa các `int` so sánh bằng số.
2. `Integer.toBinaryString`, `toOctalString` và `toHexString` trả về **chuỗi ký tự** biểu diễn số trong cơ số được chọn; `toHexString` dùng chữ thường cho `a–f`. Chúng **không đổi kiểu của biến `decimal`**.
3. `0xFFFF_FFFF` có mẫu bit 32 bit toàn số 1; khi biểu diễn dưới dạng `int` có dấu, nó là **-1**. Thêm hậu tố `L` tạo literal `long` với cùng các chữ số hex, nên giá trị dương là **4.294.967.295**. `Integer.toUnsignedLong(allBits)` cũng cho cách nhìn không dấu của 32 bit ấy.

### Lần theo đường đi từ source tới output

~~~mermaid
flowchart LR
    A["Literal 0b101010, 052, 0x2A"] --> B["Compiler hiểu giá trị int: 42"]
    B --> C["Biến int trong chương trình"]
    C --> D["println: hiển thị thập phân 42"]
    C --> E["toBinaryString: chuỗi 101010"]
    C --> F["toHexString: chuỗi 2a"]
~~~

Lúc in bằng cách nối chuỗi, `println` không tự nhớ giá trị từng được viết trong source bằng cơ số nào. Muốn hiển thị ở cơ số khác, dùng phương thức chuyển **giá trị thành chuỗi** tương ứng.

## 4. Kiểu số nguyên khi viết theo cơ số

Cơ số quyết định **cách ghi chữ số**, còn hậu tố quyết định **kiểu literal**: không có `L` thường là `int` (32 bit), có `L` là `long` (64 bit). Ví dụ `42`, `0b101010` và `0x2A` đều là `int` mang giá trị 42; `0x2AL` là `long` cùng giá trị.

~~~java
int count = 42;
long sameCount = 0x2AL;
long veryLarge = 4_000_000_000L;
// long invalid = 4_000_000_000; // Decimal int literal vượt phạm vi.
~~~

Đừng suy ra kiểu literal từ biến nhận: `long x = 42;` vẫn bắt đầu từ literal `int` và chuyển mở rộng sang `long`. Với mẫu bit có bit dấu, cách hiểu `int`/`long` được minh họa trực tiếp ở mục 7; phần giới hạn số, hậu tố `L`, phép toán tràn và ép kiểu được phân tích riêng trong bài **Hậu tố L và kiểu mặc định của literal số nguyên**.

## 5. Nhóm chữ số trong từng cơ số bằng dấu `_`

Bạn có thể viết `1_000_000`, `0b1010_0101`, `07_52` hoặc `0xCA_FE` để dễ đọc. `_` không đổi giá trị, cơ số hay kiểu của literal. Không đặt nó sát tiền tố hoặc ở cuối phần số: `0b_1010`, `0x_FF`, `123_L`, `100_` đều không hợp lệ.

Các quy tắc chi tiết, trường hợp nhiều dấu `_` liên tiếp, dấu chấm và số mũ thuộc bài **Dấu gạch dưới trong literal số và vị trí không hợp lệ**.

## 6. Dấu trừ và giá trị nhỏ nhất

Dấu `-` trước một số là **toán tử một ngôi**, không thuộc bản thân token literal: `-5` được phân tích thành toán tử `-` và literal `5`. Hai dạng thập phân `-2147483648` và `-9223372036854775808L` là các trường hợp đặc biệt Java cho phép khi literal làm toán hạng của dấu trừ; bỏ dấu trừ ở các giá trị đó thì literal dương vượt giới hạn `int`/`long`.

Mục 7 tiếp tục giải thích vì sao **mẫu bit** trong literal nhị phân/bát phân/hex có thể biểu diễn số âm mà không cần viết dấu trừ. Bài về hậu tố `L` đào sâu quy tắc giới hạn và biểu thức số nguyên.

## 7. Cách hiểu mẫu bit đối với literal nhị phân/bát phân/hex

Với literal không phải thập phân, Java cho phép thể hiện **mẫu bit** chiếm trọn 32 bit của `int` hoặc 64 bit của `long`; vì Java `int`/`long` là kiểu có dấu theo biểu diễn bù hai (*two's complement*), mẫu có bit dấu bằng 1 được hiểu là số âm.

| Mẫu nguồn Java | Kiểu literal | Giá trị nếu in thập phân có dấu |
| --- | --- | ---: |
| `0x7FFF_FFFF` | `int` | 2.147.483.647 |
| `0x8000_0000` | `int` | -2.147.483.648 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0xFFFF_FFFFL` | `long` | 4.294.967.295 |
| `0x8000_0000_0000_0000L` | `long` | -9.223.372.036.854.775.808 |

Ví dụ `0b1111_1111` chỉ có 8 bit 1 nhưng được đưa vào kiểu `int` 32 bit nên có giá trị **255**, không phải `-1`; muốn biểu diễn `-1` bằng 32 bit 1 thì phải có đủ 32 bit 1 hoặc viết `0xFFFF_FFFF`.

**Không có kiểu primitive `unsigned int` trong Java 17.** Khi cần giải thích 32 bit như số không dấu, dùng API như `Integer.toUnsignedLong`, `Integer.compareUnsigned` hoặc các phép dịch/bitmask thích hợp. Mục đích là diễn giải các bit, không tạo một primitive mới.

## 8. Literal trong mã nguồn khác với parse chuỗi lúc chạy

Đây là hai việc khác nhau:

- Viết `int color = 0xFF;` trong source: **compiler** nhận diện tiền tố `0x` và tạo giá trị số 255.
- Gọi `Integer.parseInt("FF", 16)` lúc chạy: API Java đọc chuỗi `"FF"` theo **radix 16** và trả `255`.
- Gọi `Integer.decode("0xFF")`: API nhận một số kiểu tiền tố và trả về `Integer` có giá trị `255`.
- Gọi `Integer.parseInt("0xFF", 16)`: **lỗi `NumberFormatException`**, vì `parseInt` với radix 16 không nhận tiền tố `0x` trong chuỗi.

Ví dụ:

~~~java
int fromLiteral = 0b1010;                // 10, do compiler hiểu.
int fromString = Integer.parseInt("1010", 2); // 10, do API parse.
int fromHexString = Integer.parseInt("2A", 16); // 42.
int fromPrefix = Integer.decode("0x2A"); // 42.
~~~

Radix truyền cho `parseInt` có thể từ **2 đến 36**. Đây là API đọc chuỗi, không mở rộng số cơ số mà bạn có thể đặt làm integer literal trực tiếp trong Java source.

Không tự nhét `0b`, `0x` hoặc dấu gạch dưới vào chuỗi parse rồi kỳ vọng chúng hoạt động như cú pháp literal của compiler. Với dữ liệu người dùng, phải chuẩn hóa/kiểm tra theo hợp đồng đầu vào một cách rõ ràng.

## 9. Những lỗi thường gặp

| Đoạn mã / hiện tượng | Vấn đề | Cách sửa |
| --- | --- | --- |
| `int n = 09;` | Số có `0` đầu bị hiểu theo hệ bát phân, chữ số 9 không hợp lệ | Nếu muốn số chín thập phân, viết `9` |
| `int n = 010;` cho ra 8 | Không phải lỗi biên dịch: `010` là bát phân | Viết `10` nếu muốn mười |
| `int x = 0b102;` | `2` không là chữ số cơ số 2 | Chỉ dùng `0`, `1` |
| `int x = 0x1G;` | `G` không phải chữ số hex | Dùng `0–9`, `A–F` |
| `int x = 0x_FF;` | Dấu gạch dưới sai vị trí | Viết `0xFF` hoặc `0xF_F` |
| `long n = 8_000_000_000;` | Literal mặc định `int` quá lớn | Dùng `8_000_000_000L` |
| `int n = 0x1_0000_0000;` | Literal không hậu tố vượt 32 bit | Dùng `long n = 0x1_0000_0000L;` |
| `int n = 0xFFFF_FFFF;` in -1 | Không phải lỗi: mẫu 32 bit toàn 1 mang dấu âm | Dùng `Integer.toUnsignedLong(n)` nếu cần nhìn kiểu unsigned |
| `parseInt("1_000")` lỗi | Chuỗi runtime không theo cú pháp numeric literal | Nhập chuỗi chữ số thuần hoặc xử lý định dạng rõ ràng |

**Cần phân biệt:** lỗi do **cú pháp literal** được compiler phát hiện khi biên dịch; lỗi `NumberFormatException` của `parseInt` chỉ xảy ra khi **chương trình đang chạy**.

## 10. Bài tập thực hành

**Bài 1 — Cùng một giá trị.** Viết giá trị thập phân 255 bằng literal nhị phân, bát phân và hex. Dùng `println` để chứng minh cả ba cho `255`.

*Gợi ý:* `0b1111_1111`, `0377`, `0xFF`.

**Bài 2 — Nhận diện cơ số.** Dự đoán giá trị của `10`, `010`, `0b10` và `0x10`.

*Đáp án:* lần lượt **10**, **8**, **2**, **16**.

**Bài 3 — Giới hạn kiểu.** Vì sao `long n = 8_000_000_000;` không hợp lệ, còn `long n = 8_000_000_000L;` lại hợp lệ? Thử thêm hậu tố `L` cho literal nhị phân và hex.

**Bài 4 — Bit dấu.** Dự đoán đầu ra của `System.out.println(0xFFFF_FFFF);` và `System.out.println(0xFFFF_FFFFL);`. Giải thích vì sao cùng chữ số hex lại ra hai số khác nhau.

**Bài 5 — Dấu `_`.** Phân loại `1_000`, `1__000`, `0b1010_0001`, `0x_FF`, `123_L` và `10_` thành hợp lệ/không hợp lệ. Đừng vội kết luận hai dấu gạch dưới liên tiếp luôn sai.

**Bài 6 — Literal so với chuỗi.** Trong `IntegerLiteralsDemo`, so sánh `0x2A` với `Integer.parseInt("2A", 16)`. Điều gì xảy ra khi viết `Integer.parseInt("0x2A", 16)`? Thử phương thức `Integer.decode`.

## 11. Checklist cuối bài

- [ ] Nhớ **không tiền tố → cơ số 10**, `0b`/`0B` → cơ số 2, `0` đứng đầu số nhiều chữ số bát phân → cơ số 8, `0x`/`0X` → cơ số 16.
- [ ] Biết `09` sai và `010` có giá trị 8.
- [ ] Biết hậu tố `L` quyết định literal `long`; biến đích `long` không tự sửa literal `int` quá lớn.
- [ ] Đặt `_` **giữa các chữ số**, không ngay sau tiền tố hay sát hậu tố.
- [ ] Hiểu dấu âm là **toán tử một ngôi** và biết hai ca giới hạn âm nhỏ nhất.
- [ ] Phân biệt **mẫu bit có dấu** với cách nhìn 32 bit không dấu qua `Integer.toUnsignedLong`.
- [ ] Biết literal trong source khác việc `parseInt` giải mã một chuỗi lúc chạy.

**Tổng kết:** Bốn cơ số là **bốn cách ghi giá trị nguyên** trong chương trình Java. Đọc đúng tiền tố, hậu tố, dấu phân nhóm và giới hạn kiểu sẽ giúp tránh lỗi nhập nhằng như `010`, literal quá lớn và mẫu bit hex mang giá trị âm.
