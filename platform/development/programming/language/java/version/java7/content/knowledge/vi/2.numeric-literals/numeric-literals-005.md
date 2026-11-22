# Dấu gạch dưới trong literal số của Java

## 1. Khái niệm và mục đích

**Numeric literal** (literal số) là cách viết trực tiếp một giá trị số trong mã nguồn Java, ví dụ `1000000`, `0b10100101` hay `3.14159`. Từ **Java 7**, ta có thể đặt ký tự gạch dưới `_` **giữa các chữ số của literal số** để chia nhóm, giúp đọc và kiểm tra những dãy số dài dễ hơn. Cú pháp này tiếp tục được hỗ trợ trong Java hiện đại, kể cả Java 17+.

```java
int population = 1_250_000;       // cùng giá trị với 1250000
long amount = 9_876_543_210L;     // cùng giá trị với 9876543210L
int flags = 0b1010_0101;         // chia theo nhóm bit: 165
int color = 0xFF_A0_12;          // chia theo nhóm chữ số hex
double measurement = 12_345.6_25; // cùng giá trị với 12345.625
```

Dấu `_` ở đây là **dấu phân nhóm trong cú pháp mã nguồn**. Trình biên dịch không coi nó là phép toán hay một phần của giá trị số. Vì thế:

- `1_000_000 == 1000000` là `true`;
- `0b1010_0101` và `0b10100101` có cùng giá trị;
- `System.out.println(1_250_000)` in `1250000`, không tự in lại dấu `_`;
- kiểu dữ liệu, độ chính xác, giới hạn tràn số và các quy tắc tính toán **không thay đổi** chỉ vì thêm `_`.

Đây là tính năng của **Java source code**; không được hiểu rằng mọi hàm đọc chuỗi, file hoặc định dạng dữ liệu bên ngoài đều tự chấp nhận gạch dưới.

## 2. Những loại literal số có thể dùng `_`

Dấu `_` được phép xuất hiện giữa các chữ số thuộc cùng một phần chữ số của literal. Điều này áp dụng cho nhiều hệ cơ số và cho cả phần định trị, phần thập phân, phần số mũ của literal số thực.

| Dạng literal | Ví dụ hợp lệ | Giá trị / cách đọc |
| --- | --- | --- |
| Số nguyên thập phân (cơ số 10) | `1_234_567` | `1234567` |
| Số nguyên nhị phân (cơ số 2) | `0b1010_0101` | `165` |
| Số nguyên thập lục phân (cơ số 16) | `0xCA_FE` | `51966` |
| Số nguyên bát phân (cơ số 8) | `0_52` | `42` |
| `long` với hậu tố kiểu | `9_876_543_210L` | `9876543210L` |
| `float` với hậu tố kiểu | `12_345.6_25F` | giá trị `float` gần `12345.625` |
| `double` thập phân | `12_345.6_25` | `12345.625` |
| Số thực có số mũ cơ số 10 | `1.25e1_0` | `1.25 × 10^10` |
| Số thực hex có số mũ cơ số 2 | `0x1.8p1_0` | `1.5 × 2^10 = 1536.0` |

**Lưu ý về bát phân:** `0_52` hợp lệ theo cú pháp Java hiện hành vì `0` là chữ số đầu của literal bát phân. Tuy nhiên, literal nguyên bắt đầu bằng `0` (ngoài `0x`/`0b`) có thể gây nhầm với thập phân; chỉ dùng khi thật sự cần biểu diễn hệ 8, và ghi rõ ý nghĩa của nó. Ví dụ `052` bằng 42, không phải 52.

**Lưu ý về số thực hex:** Chữ `p` hoặc `P` đánh dấu số mũ cơ số 2, khác với `e`/`E` ở literal thập phân. Dấu `_` có thể nằm **giữa các chữ số** của số mũ (ví dụ `p1_0`), không đặt sát chữ `p`.

## 3. Quy tắc đặt gạch dưới

### 3.1. Đặt giữa các chữ số

Hợp lệ:

```java
int total = 1_000_000;
int grouped = 5_______2;     // 52: nhiều dấu _ liên tiếp vẫn hợp lệ
int bits = 0b1101_0010;
int rgb = 0x12_34_AB;
double pi = 3.14_15_92;
double speed = 1_2.3_4e5_6;
double scaled = 1.25e+1_0;
double hexFraction = 0x1.8p1_0;
```

Số lượng dấu `_` giữa hai chữ số có thể lớn hơn một; `5_______2` vẫn biên dịch thành 52. Nhưng trong mã thực tế hãy phân nhóm **nhất quán và có ý nghĩa**, không lạm dụng nhiều gạch dưới liên tiếp.

### 3.2. Không đặt ở đầu hoặc cuối phần chữ số

Những ví dụ dưới đây **không phải literal số hợp lệ**; để ở dạng comment nhằm minh họa lỗi, không đưa vào chương trình chạy:

```java
// int a = _123;      // _123 không được nhận là literal số 123
// int b = 123_;      // sai: _ sau chữ số cuối
// int c = 0x_FF;     // sai: _ ngay sau tiền tố 0x
// int d = 0b_1010;   // sai: _ ngay sau tiền tố 0b
// int e = 0xFF_;     // sai: _ ở cuối phần chữ số hex
// int f = 0b1010_;   // sai: _ ở cuối phần chữ số nhị phân
// int g = 0_xFF;     // sai: _ chen vào tiền tố 0x
// int h = 0_b1010;   // sai: _ chen vào tiền tố 0b
```

Trường hợp `_123` còn có thể được trình phân tích cú pháp đọc thành **tên định danh**, nên thông báo lỗi cụ thể không nhất thiết ghi “invalid literal”. Điều cần nhớ là nó **không phải cách viết số `123`**.

### 3.3. Không đặt cạnh dấu chấm thập phân

```java
double valid = 12_34.5_6; // hợp lệ

// double a = 12_.34;     // sai: _ ngay trước dấu .
// double b = 12._34;     // sai: _ ngay sau dấu .
// double c = 12.34_;     // sai: _ ở cuối phần thập phân
```

Gạch dưới có thể nằm giữa hai chữ số phía trước `.` hoặc giữa hai chữ số phía sau `.`. **Không được dùng nó thay dấu chấm**: `1_5` là 15, còn `1.5` là 1,5 trong cách viết thập phân.

### 3.4. Không đặt cạnh ký hiệu số mũ hoặc dấu của số mũ

```java
double dec = 1.25e1_0;       // 1.25 × 10^10
double signedExp = 1.25e+1_0; // vẫn hợp lệ
double hex = 0x1.8p1_0;      // 1.5 × 2^10

// double a = 1.25_e10;      // sai: _ ngay trước e
// double b = 1.25e_10;      // sai: _ ngay sau e
// double c = 1.25e+_10;     // sai: _ ngay sau dấu +
// double d = 0x1.8_p10;     // sai: _ ngay trước p
// double e = 0x1.8p_10;     // sai: _ ngay sau p
```

Một phần số mũ có thể có dấu `+` hoặc `-`; dấu `_` chỉ dùng **giữa các chữ số số mũ**, ví dụ `1e+1_0` hoặc `1e-1_0`.

### 3.5. Không đặt sát hậu tố kiểu

Các hậu tố `L`/`l` biểu thị `long`; `F`/`f` biểu thị `float`; `D`/`d` biểu thị `double`. Nên dùng `L` viết hoa để không nhầm chữ `l` với số `1`.

```java
long id = 123_456L;        // đúng
float ratio = 1.2_5F;      // đúng
double fraction = 3.1_4D; // đúng

// long wrongId = 123_456_L;       // sai: _ trước L
// float wrongRatio = 1.25_F;      // sai: _ trước F
// double wrongFraction = 3.14_D;  // sai: _ trước D
```

Nói gọn: **tiền tố cơ số, dấu thập phân, ký hiệu `e`/`p`, dấu của số mũ và hậu tố kiểu không phải chữ số để chèn `_` vào giữa**.

## 4. Không làm thay đổi kiểu và phạm vi giá trị

Đối với literal số nguyên, mặc định Java dùng `int` nếu không có hậu tố `L`. Dấu `_` **không mở rộng giới hạn** của kiểu và **không thay thế hậu tố**.

```java
int oneMillion = 1_000_000;
long large = 9_876_543_210L;

// int tooLarge = 9_876_543_210; // sai: vượt phạm vi literal int
// long stillWrong = 9_876_543_210; // sai: thêm kiểu đích long không biến literal int quá lớn thành hợp lệ
```

Ở hai dòng bị comment, cách viết đúng là thêm `L` trực tiếp vào literal: `9_876_543_210L`. Với `double` hoặc `float`, thêm gạch dưới không đổi quy tắc làm tròn số thực dấu phẩy động; độ chính xác vẫn do kiểu dữ liệu quyết định.

Ví dụ `0xFF_A0_12` được nhóm đẹp hơn nhưng vẫn là một giá trị `int`; cách nhóm chữ số **không quyết định độ rộng 8/16/32/64 bit**. Nếu cần bảo đảm đủ độ rộng hay giá trị không dấu khi xử lý bit, phải thiết kế kiểu và mask tương ứng, độc lập với dấu `_`.

## 5. Ví dụ chương trình Java 17+ chạy được

Lưu đúng tên tệp **`NumericUnderscoreDemo.java`** với nội dung sau:

```java
public final class NumericUnderscoreDemo {
    public static void main(String[] args) {
        int users = 1_250_000;
        long bytes = 9_876_543_210L;
        int flags = 0b1010_0101;
        int color = 0xFF_A0_12;
        double rate = 12_345.6_25;
        double scientific = 1.25e1_0;
        double hexFloat = 0x1.8p1_0;

        System.out.println(users == 1250000);
        System.out.println(bytes);
        System.out.println(flags);
        System.out.println(Integer.toHexString(color));
        System.out.println(rate);
        System.out.println(scientific);
        System.out.println(hexFloat);
    }
}
```

Từ terminal có Java 17 trở lên:

```bash
javac NumericUnderscoreDemo.java
java NumericUnderscoreDemo
```

Kết quả stdout chính xác:

```text
true
9876543210
165
ffa012
12345.625
1.25E10
1536.0
```

Giải thích từng dòng:

1. `users == 1250000` là `true` vì các dấu `_` không làm thay đổi giá trị.
2. `long` in thành dãy chữ số thập phân `9876543210`, không giữ dấu phân nhóm trong mã nguồn.
3. `0b1010_0101` có giá trị 165.
4. `Integer.toHexString` xuất chuỗi hex chữ thường `ffa012`, không giữ dấu `_`.
5. `12_345.6_25` mang giá trị `12345.625`.
6. `1.25e1_0` bằng `1.25 × 10^10`, được Java hiển thị `1.25E10`.
7. `0x1.8p1_0` có phần định trị hex là `1 + 8/16 = 1.5`; nhân `2^10` được `1536.0`.

Chương trình hoạt động trên Java hiện đại; không cần thư viện ngoài hoặc cờ biên dịch đặc biệt.

## 6. Phân biệt literal trong source với dữ liệu chuỗi

Đây là chỗ dễ nhầm nhất khi nhận dữ liệu từ API, JSON, file CSV, cơ sở dữ liệu hay người dùng.

```java
int fromSource = 1_000; // hợp lệ: Java compiler xử lý literal

// Dòng sau ném NumberFormatException nếu thực thi:
// int fromText = Integer.parseInt("1_000");

int fromPlainText = Integer.parseInt("1000"); // 1000
String printed = Integer.toString(fromSource); // "1000"
```

Các hàm như `Integer.parseInt`, `Long.parseLong`, `Double.parseDouble` và `new java.math.BigDecimal(String)` **không chấp nhận dấu `_` làm dấu phân nhóm mặc định**. Chúng nhận **chuỗi dữ liệu** theo hợp đồng riêng của từng API, không áp dụng toàn bộ quy tắc lexical của trình biên dịch Java.

Nếu một định dạng đầu vào do ứng dụng quy định **cho phép phân nhóm bằng gạch dưới**, hãy xác thực cú pháp đó một cách tường minh trước khi bỏ gạch dưới và parse. **Không nên mù quáng** `replace("_", "")` trên chuỗi do người dùng nhập: chẳng hạn `"_123"` hoặc `"12__"` không phải literal số Java hợp lệ, nhưng việc xóa dấu `_` có thể khiến một chuỗi sai được chấp nhận thành số.

Một giá trị JSON dạng number cũng không được viết `1_000`; nếu xuất dữ liệu từ Java ra JSON, giá trị số chuẩn phải là `1000`. Dấu gạch dưới chỉ phục vụ **người đọc source code**, không tự định nghĩa hợp đồng trao đổi dữ liệu.

## 7. Khi nào nên sử dụng?

- **Số lớn có ý nghĩa thập phân:** `1_000_000`, `12_500_000L`; nhóm 3 chữ số giúp kiểm tra nhanh bậc lớn.
- **Bit flags, bitmask:** `0b1111_0000`; nhóm 4 bit một cụm giúp nhìn ra cấu trúc bit và so sánh từng nibble.
- **Màu, giá trị hex, định dạng nhị phân:** `0xFF_12_34_56`; nhóm theo byte khi hệ thống quy ước dữ liệu theo byte.
- **Mã định danh dài có ý nghĩa nhóm:** `1234_5678_9012_3456L`; chỉ dùng `long` khi đó **thực sự là giá trị số**. Đối với mã định danh có số 0 đầu, hoặc không dùng để tính toán, `String` thường phù hợp hơn.
- **Giá trị khoa học có nhiều chữ số:** `6.022_140_76e23` giúp đọc hằng số trong source; nhưng cách nhóm không giúp kiểu `double` biểu diễn chính xác hơn.

Nên nhóm theo **ý nghĩa dữ liệu**, không chèn tùy tiện: `0b1101_0010` dễ đọc hơn `0b11_01_0010` nếu ý tưởng là các nibble 4 bit; `100_000` thường tự nhiên hơn `10_0000` trong số thập phân. Với số ngắn, `42` dễ đọc hơn `4_2`.

Tránh dùng dấu gạch dưới trong những con số mà nhóm làm mơ hồ ý nghĩa. Đây là quy ước code style, **không phải ràng buộc bắt buộc của Java**.

## 8. Các lỗi và hiểu lầm thường gặp

| Nhầm lẫn | Giải thích chính xác |
| --- | --- |
| `1_000` có khác `1000` về giá trị | Không; trình biên dịch nhận cùng một giá trị. |
| Chỉ `long` mới cho dấu gạch dưới | Không; `int`, `long`, `float`, `double` và các dạng số theo nhiều cơ số đều có thể dùng khi hợp lệ. |
| `0x_FF` hợp lệ vì `_` chỉ để phân nhóm | Sai; không được đặt `_` ngay sau tiền tố `0x`. |
| `3_.14` hợp lệ | Sai; không được đặt `_` cạnh dấu thập phân. |
| `1e_10` hợp lệ | Sai; không được đặt `_` ngay sau `e`/`E` hoặc `p`/`P`. |
| `1_000_L` hợp lệ | Sai; `_` không được đặt ngay trước hậu tố `L`. |
| `1____2` luôn sai vì có nhiều `_` | Vẫn hợp lệ; nhưng thường không nên viết như vậy. |
| Thêm `_` sẽ ngăn tràn số hoặc tăng độ chính xác | Sai; kiểu số và giới hạn biểu diễn giữ nguyên. |
| `parseInt("1_000")` đọc giống literal trong source | Sai; có thể ném `NumberFormatException`. |
| In số sẽ tự giữ dấu `_` | Sai; ký hiệu phân nhóm không tồn tại ở giá trị runtime. |

## 9. Tự luyện tập

**Bài 1.** Cho `int a = 12_345;` và `int b = 12345;`. Biểu thức `a == b` có giá trị gì?  
**Đáp án:** `true`; dấu `_` không tham gia giá trị.

**Bài 2.** Chỉ ra literal hợp lệ trong các biểu thức `0b10_10`, `0b_1010`, `3.1_4`, `3._14` và `123_L`.  
**Đáp án:** `0b10_10` và `3.1_4` hợp lệ; ba literal còn lại đặt `_` sát tiền tố, dấu chấm hoặc hậu tố.

**Bài 3.** `double x = 1.25e1_0;` có giá trị bao nhiêu?  
**Đáp án:** `12_500_000_000.0`; phần số mũ `1_0` là 10.

**Bài 4.** Tại sao `long n = 10_000_000_000;` không biên dịch được dù `long` đủ lớn?  
**Đáp án:** literal thập phân không có `L` được xem là `int`; phải viết `10_000_000_000L`.

**Bài 5.** Mã JSON `{"count":1_000}` có hợp lệ không?  
**Đáp án:** Không. JSON number không cho dấu phân nhóm gạch dưới; dùng `{"count":1000}`.

## 10. Kết luận và tài liệu chuẩn

- Dùng `_` để **phân nhóm chữ số trong numeric literal Java**, được hỗ trợ từ Java 7 và vẫn là cú pháp hiện hành.
- Chỉ đặt nó ở những vị trí được ngữ pháp cho phép **giữa các chữ số của cùng phần số**; không đặt cạnh tiền tố cơ số, dấu thập phân, ký hiệu/số dấu của số mũ hoặc hậu tố kiểu.
- Dấu `_` chỉ giúp **đọc mã nguồn**; nó không đổi giá trị, kiểu, phạm vi, độ chính xác, cách in số hoặc cách parse chuỗi.

Tham khảo quy tắc cú pháp chính thức: [Java Language Specification — `3.10.1 Integer Literals và `3.10.2 Floating-Point Literals](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html#jls-3.10.1).