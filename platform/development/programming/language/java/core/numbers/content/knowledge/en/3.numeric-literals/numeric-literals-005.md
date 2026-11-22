# Dấu gạch dưới trong literal và các vị trí không hợp lệ trong Java

## 1. Mục đích: đọc một con số dài dễ hơn mà không đổi giá trị

Từ Java 7, mã nguồn Java cho phép dùng dấu gạch dưới `_` làm **ký tự phân nhóm chữ số** bên trong *numeric literal* (literal số nguyên hoặc số thực). Dấu `_` có ý nghĩa về **cách viết mã nguồn**, không phải một phép toán hay một chữ số góp phần vào giá trị số.

Ví dụ:

```java
int population = 12_345_678;
long accountId = 1_234_567_890_123L;
double ratio = 3.141_592_653_589_793;
```

Các biểu thức trên có cùng giá trị với phiên bản bỏ dấu gạch dưới:

```java
int population = 12345678;
long accountId = 1234567890123L;
double ratio = 3.141592653589793;
```

**Nguyên tắc quan trọng:** Gạch dưới được phép **nằm giữa các chữ số của cùng một phần số**. Nó không được phép thay thế chữ số, tách các ký hiệu tiền tố cơ số, đứng sát dấu thập phân, ký hiệu số mũ hoặc hậu tố kiểu.

Một *literal* là cách viết trực tiếp giá trị trong **mã nguồn** (như `1_000`). Nó khác với chuỗi dữ liệu `"1_000"` đang được xử lý lúc chương trình chạy. Đây là nguồn gốc của nhiều lỗi khi làm việc với `Integer.parseInt`.

## 2. Các cơ số số nguyên cho phép dùng `_` ở đâu?

Java có bốn cách viết *integer literal* cơ bản:

| Cơ số | Cách viết | Ví dụ hợp lệ | Giá trị thập phân |
| --- | --- | --- | ---: |
| 10 (decimal) | Chữ số `0..9`, số nhiều chữ số dương thường không bắt đầu bằng `0` | `1_234_567` | 1234567 |
| 2 (binary) | Tiền tố `0b`/`0B` rồi đến `0`, `1` | `0b1010_0101` | 165 |
| 8 (octal) | Số nguyên bắt đầu bằng `0`, chữ số `0..7` | `0_52` | 42 |
| 16 (hexadecimal) | Tiền tố `0x`/`0X`, các chữ số `0..9`, `A..F` | `0xCA_FE` | 51966 |

Các ví dụ khác đều hợp lệ:

```java
int a = 12_34;             // decimal
int b = 1__000;            // Nhiều dấu _ liên tiếp giữa các chữ số vẫn hợp lệ.
int c = 0b1111_0000;       // binary
int d = 0xA_B_C_D;         // hexadecimal: A..F cũng là chữ số trong hệ 16.
int e = 05_2;              // octal = 42.
int f = 0_52;              // octal = 42; _ ngay sau chữ số 0 đầu là hợp lệ.
long g = 9_876_543_210L;   // L là hậu tố long, không có _ sát L.
```

Quy tắc có chi tiết dễ nhầm:

- Trong số **nhị phân và thập lục phân**, hai ký tự `0b`/`0B` và `0x`/`0X` là **tiền tố**, không thuộc các chữ số của giá trị số. Sau tiền tố phải bắt đầu bằng một chữ số hợp lệ: `0b_1010` và `0x_FF` là **sai**.
- Trong số **bát phân**, chữ số `0` đầu tiên là **một chữ số của literal**, vì vậy `0_52` và `0__52` đều **đúng**. Đây không giống tiền tố `0x`/`0b`.
- Trong số **thập phân**, có thể bắt đầu nhóm bằng chữ số khác `0`, rồi dùng `_` ở giữa, ví dụ `1_000_000`. Dấu `_` không khiến `0_52` trở thành số thập phân; chuỗi đó vẫn là octal.
- Với literal số nguyên có hậu tố `L`/`l` (khuyến nghị `L` vì dễ phân biệt với `1`), dấu `_` phải nằm **trước chữ số cuối cùng**, không được đứng giữa chữ số cuối và hậu tố.

**Độ rộng kiểu vẫn không đổi.** `1_000_000` vẫn là literal `int`; `1_000_000L` là `long`. Dấu gạch dưới không làm số vượt giới hạn kiểu trở nên hợp lệ và không thay đổi ý nghĩa của tiền tố cơ số.

## 3. Dấu gạch dưới trong literal dấu phẩy động

Literal `float`/`double` có thể chứa các phần khác nhau: phần nguyên, dấu thập phân `.`, phần phân số, phần số mũ (nếu có), và hậu tố kiểu `F`/`f`/`D`/`d` (nếu có).

Ví dụ hợp lệ:

```java
double a = 12_345.67_89;
float b = 3.14_15F;
double c = 1.2_5e1_0;
double d = 1_2.5_0e+1_0;
double e = 0x1.fp1_0;
double f = 0xA_B.C_Dp+1_0;
```

Cách đọc:

- `12_345.67_89` có gạch dưới **trong** phần nguyên và phần phân số; không có dấu `_` nằm cạnh dấu chấm.
- `1.2_5e1_0` có gạch dưới trong các chữ số của phần phân số và **trong** các chữ số của số mũ; chữ `e` không bị kẹp sát bởi `_`.
- `0x1.fp1_0` là **hexadecimal floating-point literal**. Trong hệ này, phần trị (significand) dùng các chữ số hệ 16, còn số mũ sau `p`/`P` là số mũ của 2 và dùng chữ số thập phân. Dấu `_` trong `1_0` của số mũ là hợp lệ.
- `F`/`f` chọn `float`; `D`/`d` chọn `double` (không có hậu tố, một literal dấu phẩy động thông thường có kiểu `double`). Không đặt gạch dưới sát các hậu tố.

Không được đặt gạch dưới **ngay trước hoặc sau** `.`, `e`/`E`, `p`/`P`, dấu `+`/`-` của số mũ, hoặc các hậu tố kiểu. Các vùng chữ số riêng có thể chứa gạch dưới **ở giữa các chữ số**.

Ví dụ `1.25e1_0` hợp lệ; `1.25e_10` không hợp lệ; `1.25e+1_0` hợp lệ; `1.25e+_10` không hợp lệ.

**Phân biệt số nguyên thập lục phân với số thực thập lục phân:** `0xA_B` là literal nguyên; `0x1.fp1_0` là literal dấu phẩy động và bắt buộc có phần số mũ `p`/`P`. Trong cả hai, không được đặt `_` ngay sau `0x`.

## 4. Những vị trí không hợp lệ: bảng tra cứu nhanh

Các đoạn ở cột “Sai” là **mảnh mã cố ý không hợp lệ**, không nên đưa trực tiếp vào chương trình đang biên dịch.

| Vị trí sai | Sai | Đúng | Vì sao |
| --- | --- | --- | --- |
| Trước chữ số đầu | `_123` (khi muốn viết literal) | `123` | `_123` được phân tích như **tên định danh** chứ không phải literal số. |
| Sau chữ số cuối | `123_` | `12_3` | Phần số không được kết thúc bằng `_`. |
| Giữa `0` và `x` | `0_xFF` | `0xFF` | Không được chèn dấu vào tiền tố hệ 16. |
| Ngay sau `0x` | `0x_FF` | `0xF_F` | Sau tiền tố phải có chữ số hệ 16. |
| Giữa `0` và `b` | `0_b101` | `0b101` | Không được chèn dấu vào tiền tố hệ 2. |
| Ngay sau `0b` | `0b_101` | `0b1_01` | Sau tiền tố phải có chữ số nhị phân. |
| Trước hậu tố số nguyên | `1_000_L` | `1_000L` | Không có chữ số sau `_` trước `L`. |
| Trước dấu thập phân | `3_.1415` | `3.141_5` | `_` không đứng sát `.`. |
| Sau dấu thập phân | `3._1415` | `3.14_15` | `_` không được mở đầu phần phân số. |
| Trước ký hiệu số mũ | `1_e2` | `1e2` | Gạch dưới không kết thúc phần chữ số trước `e`. |
| Sau ký hiệu số mũ | `1e_2` | `1e2` | Gạch dưới không bắt đầu dãy chữ số số mũ. |
| Sau dấu số mũ | `1e+_2` | `1e+2` | Dấu `+`/`-` phải đi liền chữ số số mũ. |
| Cuối phần số mũ | `1e2_` | `1e2_0` | Dãy chữ số không được kết thúc bằng `_`. |
| Trước hậu tố `F`/`D` | `3.14_F`, `2.0_D` | `3.14F`, `2.0D` | Hậu tố không phải chữ số. |
| Trước `p` hệ 16 | `0x1.f_p4` | `0x1.fp4` | `_` không sát ký hiệu số mũ nhị phân. |
| Sau `p` hệ 16 | `0x1.fp_4` | `0x1.fp4` | Phần số mũ phải bắt đầu bằng chữ số, có thể có dấu. |

Một cách tự kiểm tra: chỉ dùng `_` để phân cách các chữ số trong **một nhóm chữ số liên tục**. Nếu dấu `_` sẽ chạm vào `.`, ký tự chữ thể hiện **cấu trúc** (`x`, `b`, `e`, `p`, `L`, `F`, `D`) hoặc dấu `+`/`-` của số mũ, hãy viết lại.

Cần phân biệt hai trường hợp: `0xA_B` **hợp lệ** vì `A` và `B` là chữ số hệ 16; `0xA_p1` **không hợp lệ** vì `p` là ký hiệu số mũ, không phải một chữ số hệ 16.

## 5. Có thể dùng nhiều dấu `_` liền nhau không?

**Có**, nếu cả chuỗi gạch dưới vẫn nằm *giữa hai chữ số thuộc cùng thành phần số*. Quy tắc Java không giới hạn mỗi chỗ đúng một dấu `_`.

```java
int number = 1________0;      // Hợp lệ: giá trị 10.
int hex = 0xA___B;             // Hợp lệ: giá trị 171.
int octal = 0__7;              // Hợp lệ: giá trị 7 (octal).
double fraction = 1.2___5;     // Hợp lệ: giá trị 1.25.
```

Nhưng thực tế nên phân nhóm hợp lý, ví dụ `1_000_000`, `0xCAFE_BABE` hoặc `0b1111_0000`; `1________0` tuy hợp lệ vẫn khó đọc.

Với quy tắc kiểm tra vị trí, một chuỗi gạch dưới có **các chữ số hợp lệ ở cả hai phía** là dấu hiệu cần, nhưng phải nhớ hai phía thuộc **cùng phần chữ số**: không được nhầm tiền tố cơ số, dấu thập phân và ký hiệu số mũ thành chữ số.

## 6. Khác biệt giữa cú pháp mã nguồn và dữ liệu chuỗi lúc chạy

Dấu `_` được *trình biên dịch* công nhận trong một literal. Khi chạy, giá trị lưu trong biến là **giá trị số**, không mang theo các dấu phân nhóm trong cách viết ban đầu.

```java
int amount = 1_000;
System.out.println(amount); // In 1000, không in 1_000.
```

Tuy nhiên, các hàm parse chuỗi thông dụng **không áp dụng cú pháp literal của trình biên dịch**:

```java
Integer.parseInt("1000");      // 1000.
Integer.parseInt("1_000");     // Ném NumberFormatException.
Double.parseDouble("3.1415");  // 3.1415.
Double.parseDouble("3.14_15"); // Ném NumberFormatException.
```

Do đó, nếu nhận input từ API, tệp cấu hình hoặc biểu mẫu có gạch dưới, bạn phải xác định **định dạng dữ liệu** có cho phép dấu phân nhóm này hay không. Nếu có, hãy kiểm tra dữ liệu đầu vào theo một quy tắc rõ ràng trước khi chuyển sang số. Không nên mù quáng xóa mọi `_`, vì điều đó có thể biến chuỗi không hợp lệ như `"_100"` hoặc `"10_"` thành dữ liệu được chấp nhận ngoài ý muốn.

Một cách minh họa cho **định dạng thập phân không dấu, cho phép một hoặc nhiều dấu `_` giữa các chữ số**:

```java
static int parseGroupedDecimal(String input) {
    if (!input.matches("[0-9]+(?:_+[0-9]+)*")) {
        throw new IllegalArgumentException("Invalid decimal grouping");
    }
    return Integer.parseInt(input.replace("_", ""));
}
```

Đây là **quy tắc của ứng dụng** (chỉ hỗ trợ số nguyên thập phân không dấu), không phải một parser đầy đủ cho mọi Java literal. Dữ liệu sau khi bỏ dấu phân cách còn có thể vượt miền `int`, khi đó `Integer.parseInt` vẫn ném `NumberFormatException`. Nếu nhận số thập phân quá lớn, cân nhắc `BigInteger` và kiểm soát độ dài input.

Ngoài numeric literal, dấu `_` còn có thể xuất hiện trong tên định danh (nếu tuân theo quy tắc đặt tên) hoặc chuỗi ký tự; các trường hợp đó không tự mang nghĩa “phân nhóm chữ số”. Riêng **một dấu `_` đứng một mình** đã là từ khóa dành riêng từ Java 9, không được dùng làm tên biến độc lập.

## 7. Ví dụ Java 17+ chạy được

Lưu trong tệp **`UnderscoreLiteralDemo.java`**:

```java
public class UnderscoreLiteralDemo {
    public static void main(String[] args) {
        int decimal = 1_234_567;
        int repeated = 1__000;
        int octal = 0_52;
        int hex = 0xCA_FE;
        int binary = 0b1010_0101;
        double fraction = 3.14_15;
        double scientific = 1.25e1_0;
        double hexadecimalFloat = 0x1.fp1_0;
        long id = 1_234_567_890L;

        System.out.println("decimal=" + decimal);
        System.out.println("repeated=" + repeated);
        System.out.println("octal=" + octal);
        System.out.println("hex=" + hex);
        System.out.println("binary=" + binary);
        System.out.println("fraction=" + fraction);
        System.out.println("scientific valid=" + (scientific == 12_500_000_000.0));
        System.out.println("hex float=" + hexadecimalFloat);
        System.out.println("long=" + id);

        try {
            Integer.parseInt("1_000");
        } catch (NumberFormatException ex) {
            System.out.println("String 1_000 cannot be parsed as int directly");
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac UnderscoreLiteralDemo.java
java UnderscoreLiteralDemo
```

Kết quả:

```text
decimal=1234567
repeated=1000
octal=42
hex=51966
binary=165
fraction=3.1415
scientific valid=true
hex float=1984.0
long=1234567890
String 1_000 cannot be parsed as int directly
```

Bạn có thể tự kiểm tra lỗi biên dịch bằng cách **thêm từng dòng sau vào trong `main` rồi biên dịch lại**. Các dòng được comment để ví dụ hoàn chỉnh ở trên vẫn chạy được:

```java
// int invalid1 = 123_;
// int invalid2 = 0x_FF;
// int invalid3 = 0b_1010;
// long invalid4 = 1_000_L;
// double invalid5 = 3_.1415;
// double invalid6 = 3._1415;
// double invalid7 = 1e_3;
// double invalid8 = 1e+_3;
// double invalid9 = 0x1.fp_4;
```

Các dòng này minh họa **lỗi cú pháp literal được phát hiện tại thời điểm biên dịch**, không phải `NumberFormatException` lúc chạy. Ngược lại, `Integer.parseInt("1_000")` nằm trong mã nguồn hoàn toàn hợp lệ; nó lỗi khi phương thức xử lý chuỗi tại runtime.

## 8. Quy ước viết mã cho dễ đọc

Dấu `_` có ích nhất khi nhóm chữ số có ý nghĩa rõ ràng:

- Số thập phân theo nhóm ba chữ số từ phải qua trái: `1_000`, `25_000_000`.
- Số nhị phân theo byte hoặc nibble: `0b1100_1010`, `0b1111_0000_1010_0101`.
- Số thập lục phân theo byte/word: `0xFF_00_7F`, `0xCAFE_BABE`.
- Số thực có nhiều chữ số có thể phân nhóm phần nguyên, phần phân số hoặc phần số mũ độc lập, nhưng đừng đặt dấu sát ký hiệu phân cách.

Không nhất thiết phải thêm `_` cho số rất ngắn như `12` hoặc `0xFF`. Tránh nhóm tùy tiện làm mất ý nghĩa, ví dụ `12_34_56` trong bối cảnh cả dự án đang nhóm chữ số thập phân theo ba.

**Tóm lại:** Trong Java, `_` giúp con người đọc numeric literal mà **không đổi giá trị số hay kiểu dữ liệu**. Chỉ đặt nó giữa các chữ số của cùng một phần số; nhớ ngoại lệ quan trọng của số bát phân `0_52` là hợp lệ, trong khi `0x_FF` và `0b_101` không hợp lệ. Việc parse dữ liệu chuỗi là một việc riêng, cần xử lý theo định dạng đầu vào.

**Tài liệu tham khảo:** [Java Language Specification §3.10.1 — Integer Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.1), [§3.10.2 — Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.2), và [Oracle — Underscores in Numeric Literals](https://docs.oracle.com/javase/8/docs/technotes/guides/language/underscores-literals.html).
