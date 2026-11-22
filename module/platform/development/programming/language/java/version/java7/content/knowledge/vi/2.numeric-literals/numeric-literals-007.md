# Java 7 — Vị trí gạch dưới hợp lệ và lỗi cú pháp trong literal số

## Mục tiêu bài học

Từ Java 7, Java cho phép đặt dấu gạch dưới `_` **giữa các chữ số trong numeric literal** để nhóm chữ số dễ đọc. Quy tắc này vẫn được Java hỗ trợ trên các JDK hiện đại. Đây là cú pháp của **mã nguồn**, không phải cơ chế định dạng số khi chạy chương trình.

Sau bài này, bạn có thể:

1. Xác định đúng vị trí được đặt `_` trong literal `int`, `long`, `float`, `double`, kể cả nhị phân, thập lục phân, bát phân và phần số mũ.
2. Phân biệt lỗi vị trí `_` với lỗi hệ cơ số, lỗi phạm vi kiểu số và lỗi dùng identifier.
3. Tự lập ví dụ hợp lệ/không hợp lệ, kiểm chứng bằng `javac` và giải thích chính xác kết quả.
4. Viết số dài dễ đọc mà vẫn giữ nguyên giá trị, kiểu dữ liệu và cách tính toán.

Các ví dụ chạy trên **JDK 17+** và chỉ dùng cú pháp đã có từ Java 7, hiện vẫn hợp lệ. Không cần cài một bản JDK cũ để thực hành.

## 1. Dấu `_` trong numeric literal thực chất làm gì?

Literal số là cách viết giá trị ngay trong mã nguồn, chẳng hạn `1000000`, `0xCAFE`, `3.1415`. Khi viết `1_000_000`, dấu `_` chỉ là **dấu phân tách để người đọc nhận diện nhóm chữ số**. Trình biên dịch hiểu `1_000_000` và `1000000` là cùng một giá trị `int`; không có ký tự gạch dưới nào được lưu trong giá trị số ở runtime.

```java
int dailyLimit = 1_000_000;
int sameLimit = 1000000;
boolean equal = dailyLimit == sameLimit; // true
```

Tương tự, `0b1010_0101`, `0xCA_FE` hay `3.14_15` cũng chỉ nhóm các chữ số của những literal tương ứng.

**Nguyên tắc cốt lõi:** `_` phải ở **bên trong một dãy chữ số hợp lệ của cùng thành phần literal**. Trong hệ thập lục phân, các chữ cái `A`–`F` cũng là chữ số của hệ cơ số 16. Với số thực, phần nguyên, phần thập phân và phần số mũ là các thành phần riêng: có thể nhóm chữ số *bên trong* từng phần, nhưng không đặt `_` sát ký hiệu ngăn cách các phần.

Không đặt `_` tùy ý giữa mọi ký tự nhìn có vẻ “thuộc số”. Đặc biệt, prefix (`0x`/`0b`), dấu chấm (`.`), ký hiệu số mũ (`e`/`E`/`p`/`P`), dấu `+`/`-` sau ký hiệu mũ và hậu tố kiểu (`L`/`F`/`D`) không phải chữ số của phần cần phân nhóm.

## 2. Những vị trí hợp lệ

| Dạng số | Ví dụ hợp lệ | Cách hiểu |
| --- | --- | --- |
| Số nguyên thập phân | `1_234_567` | Cùng giá trị với `1234567`, kiểu `int` nếu không có hậu tố |
| Số `long` | `9_223_372_036_854_775_807L` | Nhóm chữ số trước `L`; `L` xác định kiểu `long` |
| Số nhị phân | `0b1010_0101` | `_` ở giữa các chữ số `0`/`1` sau prefix `0b` |
| Số thập lục phân | `0xCA_FE` hoặc `0xFF_EC_DE_5E` | `_` giữa các chữ số hex, gồm `A`–`F` |
| Số bát phân | `05_2` hoặc `0_52` | Hợp lệ; literal có `0` dẫn đầu được đọc theo cơ số 8 |
| Số thực thập phân | `3.14_15F`, `12_34.56_78` | Nhóm bên trong phần nguyên hoặc phần lẻ |
| Số thực dạng mũ | `1.2e1_0`, `1.2e+1_0` | Nhóm **giữa các chữ số của số mũ** |
| Số thực hex | `0x1.8p1_0` | Nhóm phần exponent nhị phân; `p` phân tách phần mũ |
| Nhiều dấu liên tiếp | `5___2` | Hợp lệ về cú pháp và có giá trị `52`; không nên lạm dụng |

Ví dụ khác hợp lệ:

```java
int decimal = 20_000_000;
int bits = 0b1111_0000;
int color = 0xFF_80_00;
long distance = 123_456_789L;
float ratio = 3.14_15F;
double amount = 12_34.56_78;
double scale = 1.2e+1_0;
```

Trên JDK hiện đại, `_` vẫn có cùng ý nghĩa với các literal này. Việc đặt dấu tùy tiện vào những vị trí sai vẫn là **lỗi biên dịch**.

### 2.1. Lưu ý riêng: `0_52` là bát phân, không phải thập phân

Ở literal số nguyên, chữ số `0` đứng đầu có ý nghĩa của cú pháp bát phân khi tiếp theo là các chữ số bát phân. Vì `0` là một chữ số thuộc literal bát phân, `0_52` được phép và có giá trị `42` theo hệ thập phân: `5 × 8 + 2`. `05_2` cũng bằng `42`.

Tuy nhiên, `0_8` **không hợp lệ** vì `8` không phải chữ số bát phân; lỗi không phải do `_` đứng sau `0`. Nếu muốn số **52 thập phân**, viết `52`; nếu muốn cấu hình bit rõ cơ số, thường ưu tiên `0b...` hoặc `0x...` theo bài toán. Đừng dùng số `0` dẫn đầu chỉ để trang trí.

### 2.2. Trong literal số thực, mỗi dãy chữ số có biên riêng

```java
double a = 12_34.56_78; // 1234.5678
double b = 1.2e1_0;     // 1.2 × 10^10
double c = 0x1.8p1_0;   // 1.5 × 2^10 = 1536.0
```

- Dấu `_` có thể ở giữa `1` và `2`, giữa `5` và `6` hoặc giữa `1` và `0` của exponent.
- Không được đặt ngay trước/sau `.` hoặc ngay sau `e`, `p`, `+`/`-` của exponent.
- Trong literal hex float, phần `1.8` là hệ 16, `p10` thể hiện lũy thừa 2; đừng nhầm `p` với `e` trong số thực thập phân.
- `F`/`f` định kiểu `float`, còn `D`/`d` là hậu tố tùy chọn của `double`. Không được đặt `_` ngay trước các hậu tố đó.

## 3. Các lỗi đặt dấu gạch dưới thường gặp

Bảng sau là những **dòng cố ý viết sai** để đọc và thử biên dịch riêng. Không dán tất cả vào một lớp Java mà mong lớp đó chạy được.

| Mã nguồn sai | Vì sao sai | Sửa phù hợp |
| --- | --- | --- |
| `int a = 123_;` | `_` sau chữ số cuối | `int a = 123;` hoặc `1_23` |
| `long b = 1_000_L;` | `_` sát hậu tố `L` | `long b = 1_000L;` |
| `float c = 3.14_F;` | `_` sát hậu tố `F` | `float c = 3.14F;` |
| `double d = 3_.14;` | `_` ngay trước `.` | `double d = 3.14;` |
| `double e = 3._14;` | `_` ngay sau `.` | `double e = 3.14;` |
| `int f = 0x_FF;` | `_` ngay sau prefix `0x` | `int f = 0xFF;` |
| `int g = 0_xFF;` | Chèn `_` vào giữa prefix `0x` | `int g = 0xFF;` |
| `int h = 0b_1010;` | `_` ngay sau prefix `0b` | `int h = 0b1010;` |
| `int i = 0b1010_;` | `_` sau chữ số nhị phân cuối | `int i = 0b1010;` |
| `double j = 1e_10;` | `_` ngay sau `e` | `double j = 1e10;` |
| `double k = 1e+_10;` | `_` ngay sau dấu `+` trong exponent | `double k = 1e+10;` |
| `double m = 0x1.8p_10;` | `_` ngay sau `p` | `double m = 0x1.8p10;` |
| `double n = 0x1.8p+_10;` | `_` ngay sau `+` trong exponent hex | `double n = 0x1.8p+10;` |

Điểm chung: `_` chỉ được phân tách các **chữ số có thật**, không được đứng ở mép của một dãy chữ số hoặc sát ký hiệu phân cách, prefix/hậu tố.

### 3.1. Ba kiểu lỗi dễ bị chẩn đoán nhầm

**Trường hợp 1 — Ký tự ở đầu có thể là identifier, không phải literal số**

```java
int value = _52; // _52 được đọc như tên biến, không phải literal 52
```

Nếu không có biến tên `_52` được khai báo, `javac` báo không tìm thấy symbol. Đừng mô tả lỗi này là một literal số chứa dấu `_` ở đầu: đoạn `_52` được phân tích thành **identifier**. Muốn giá trị số `52`, hãy viết `52` hoặc `5_2`.

**Trường hợp 2 — Cơ số sai nhưng vị trí `_` không nhất thiết sai**

```java
int octal = 0_8; // không hợp lệ: 8 không phải chữ số bát phân
```

Ngược lại, `0_52` hợp lệ nhưng mang giá trị bát phân `42`. Phải kiểm tra **cơ số và dãy chữ số** trước khi kết luận vị trí `_` có hợp lệ.

**Trường hợp 3 — Giá trị vượt phạm vi kiểu số**

```java
int tooLarge = 2_147_483_648;     // lỗi: literal thập phân vượt int
long correct = 2_147_483_648L;    // hợp lệ: literal có hậu tố L
```

Lỗi ở dòng đầu không phải do các dấu `_`; cùng giá trị `2147483648` không có `_` cũng vượt giới hạn của literal thập phân kiểu `int`. Cần chọn đúng kiểu và hậu tố, không cố di chuyển dấu gạch dưới.

## 4. Chương trình chạy được: kiểm chứng các vị trí hợp lệ

Tạo tệp `NumericUnderscoreDemo.java` với **toàn bộ** nội dung sau:

```java
public final class NumericUnderscoreDemo {
    public static void main(String[] args) {
        int decimal = 1_200_000;
        long maxLong = 9_223_372_036_854_775_807L;
        int binary = 0b1010_0101;
        int hexadecimal = 0xCA_FE;
        int octal = 0_52;
        double fraction = 3.14_15;
        double exponent = 1.2e1_0;
        double hexFloat = 0x1.8p1_0;
        int consecutive = 5___2;

        System.out.println("decimal=" + decimal);
        System.out.println("long=" + maxLong);
        System.out.println("binary=" + binary);
        System.out.println("hexadecimal=" + hexadecimal);
        System.out.println("octal=" + octal);
        System.out.println("fraction=" + fraction);
        System.out.println("exponent=" + exponent);
        System.out.println("hexFloat=" + hexFloat);
        System.out.println("consecutive=" + consecutive);
        System.out.println("sameValue=" + (1_000_000 == 1000000));
    }
}
```

Từ terminal tại thư mục chứa file, dùng JDK 17+:

```bash
javac -encoding UTF-8 NumericUnderscoreDemo.java
java NumericUnderscoreDemo
```

**Output chính xác:**

```text
decimal=1200000
long=9223372036854775807
binary=165
hexadecimal=51966
octal=42
fraction=3.1415
exponent=1.2E10
hexFloat=1536.0
consecutive=52
sameValue=true
```

Giải thích những điểm cần hiểu:

- `decimal=1200000`: dấu `_` không xuất hiện khi in giá trị; `1_200_000` bằng `1200000`.
- `long=9223372036854775807`: suffix `L` đứng sau **chữ số cuối**, không được có `_` ngay trước `L`.
- `binary=165`: `0b1010_0101` = `128 + 32 + 4 + 1`.
- `hexadecimal=51966`: `0xCA_FE` có cùng giá trị với `0xCAFE`.
- `octal=42`: `0_52` cho thấy ngoại lệ hợp lệ của chữ số `0` dẫn đầu trong cú pháp bát phân.
- `fraction=3.1415`: nhóm chữ số bên phải dấu chấm, không đặt `_` sát dấu chấm.
- `exponent=1.2E10`: `1.2e1_0` có số mũ bằng `10`. Cách biểu diễn chuỗi `double` khi in dùng ký hiệu khoa học.
- `hexFloat=1536.0`: `0x1.8` tương đương `1.5` thập phân, nhân `2^10` thành `1536`.
- `consecutive=52`: ngôn ngữ cho phép nhiều `_` liên tiếp *giữa các chữ số*, nhưng cách viết ấy không có lợi cho khả năng đọc.
- `sameValue=true`: dấu `_` không đổi kết quả phép so sánh hoặc kiểu literal.

Để tự kiểm chứng sâu hơn, lần lượt bỏ các dấu `_` ở **những vị trí hợp lệ** rồi chạy lại. Output phải giữ nguyên. Sau đó chủ động chèn `_` vào một vị trí cấm và quan sát lỗi biên dịch trước khi chương trình chạy.

## 5. Phép thử lỗi cú pháp: tách từng ca và biên dịch

Thí nghiệm lỗi phải là **một tệp riêng**, vì mã nguồn cố ý sai không thể chạy bằng `java`. Ví dụ tạo `InvalidPlacement.java`:

```java
public final class InvalidPlacement {
    public static void main(String[] args) {
        int bits = 0b_1010; // CỐ Ý SAI: _ ngay sau 0b
        System.out.println(bits);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InvalidPlacement.java
```

**Kết quả mong đợi:** `javac` thất bại, trả mã thoát khác `0` và chỉ ra lỗi liên quan đến literal/dấu `_`. Không có output của `System.out.println` vì chương trình không biên dịch. **Câu chữ của chẩn đoán compiler có thể khác giữa các bản JDK**; điều cần kiểm chứng là trạng thái biên dịch thất bại và vị trí lỗi.

Sửa thành `int bits = 0b1010;` hoặc `int bits = 0b10_10;`, biên dịch lại và chạy:

```bash
javac -encoding UTF-8 InvalidPlacement.java
java InvalidPlacement
```

Kết quả sau khi sửa:

```text
10
```

### Ma trận kiểm chứng

Thay **một** dòng khai báo trong file thử lỗi bằng một hàng của bảng sau; biên dịch sau mỗi lần thay:

| Dòng khai báo đem thử | Kỳ vọng | Lý do |
| --- | --- | --- |
| `int n = 10_00;` | PASS | `_` giữa hai chữ số của thập phân |
| `int n = 1___2;` | PASS | Nhiều `_` liên tiếp vẫn ở giữa `1` và `2` |
| `int n = 0xA_B;` | PASS | `A`, `B` là các chữ số hex |
| `int n = 0b10_10;` | PASS | `_` giữa các bit |
| `int n = 0_52;` | PASS | Bát phân hợp lệ, giá trị thập phân `42` |
| `double n = 12_34.56_78;` | PASS | Có `_` trong phần nguyên và phần lẻ |
| `double n = 1.2e+1_0;` | PASS | `_` giữa hai chữ số exponent |
| `double n = 0x1.8p+1_0;` | PASS | `_` giữa hai chữ số của exponent nhị phân |
| `int n = 10_;` | FAIL | `_` ở cuối dãy chữ số |
| `long n = 100_L;` | FAIL | `_` đứng trước hậu tố |
| `int n = 0x_FF;` | FAIL | `_` ngay sau `0x` |
| `int n = 0b_10;` | FAIL | `_` ngay sau `0b` |
| `double n = 1_.0;` | FAIL | `_` ngay trước `.` |
| `double n = 1._0;` | FAIL | `_` ngay sau `.` |
| `double n = 1e_10;` | FAIL | `_` ngay sau `e` |
| `double n = 1e+_10;` | FAIL | `_` ngay sau dấu `+` của exponent |
| `int n = 0_8;` | FAIL | `8` không thuộc hệ cơ số 8 |
| `int n = 2_147_483_648;` | FAIL | Vượt phạm vi literal thập phân `int`, không phải lỗi vị trí `_` |

Việc tách từng phép thử giúp phân biệt chính xác **lexer/parser lỗi**, **kiểu dữ liệu sai**, **giá trị vượt phạm vi** và **tên biến chưa khai báo**. Đừng chỉ ghi “có lỗi” mà không xác định nguyên nhân.

## 6. Phân biệt literal trong source code và chuỗi dữ liệu ở runtime

Nhiều người thấy `1_000` trong Java rồi kỳ vọng `Integer.parseInt("1_000")` cũng thành công. Đây là hai việc khác nhau:

- `1_000` là **literal trong source code**; compiler hiểu cú pháp `_`.
- `"1_000"` là một **chuỗi ký tự** chứa dấu `_` thật sự.
- `Integer.parseInt` không chấp nhận dấu `_` làm dấu nhóm số trong chuỗi; nó sẽ báo `NumberFormatException`.

Tạo `LiteralAndText.java`:

```java
public final class LiteralAndText {
    public static void main(String[] args) {
        int literal = 1_000;
        System.out.println("literal=" + literal);

        try {
            Integer.parseInt("1_000");
            System.out.println("parsed");
        } catch (NumberFormatException e) {
            System.out.println("textRejected=true");
        }

        System.out.println("plainParsed=" + Integer.parseInt("1000"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LiteralAndText.java
java LiteralAndText
```

Kết quả:

```text
literal=1000
textRejected=true
plainParsed=1000
```

Dòng `parsed` không được in ra vì lời gọi phân tích cú pháp chuỗi phát sinh exception. Trong ứng dụng nhận dữ liệu người dùng, hãy **xác định định dạng đầu vào được chấp nhận và validate rõ ràng** trước khi chuyển chuỗi thành số. Đừng tùy tiện xóa mọi dấu `_` trong dữ liệu vào, vì việc biến đổi có thể che giấu dữ liệu không hợp lệ đối với hợp đồng nhập liệu.

## 7. Lựa chọn cách nhóm số để code dễ bảo trì

Pháp luật cú pháp cho phép `5___2`, nhưng “hợp lệ” khác với “dễ đọc”. Một số quy ước thực tế:

- **Thập phân:** nhóm theo bộ ba từ phải sang trái, chẳng hạn `1_000_000`, `35_000`, `9_223_372_036_854_775_807L`.
- **Nhị phân:** nhóm 4 hoặc 8 bit nếu dữ liệu đại diện cho bit field, chẳng hạn `0b1010_0101`. Mục tiêu là so sánh bit và mask dễ dàng.
- **Hex:** nhóm theo byte hoặc word, chẳng hạn `0xFF_80_00` hoặc `0xDEAD_BEEF`; dùng cách nhóm phù hợp với ý nghĩa dữ liệu.
- **Số thực:** phân nhóm khi thực sự cải thiện khả năng nhìn; `3.14_15` có thể hữu ích trong ví dụ, nhưng nhiều dấu phân tách không tự làm tính toán chính xác hơn.
- **Hậu tố:** dùng `L` hoa cho `long` để tránh nhầm `l` thường với chữ số `1`. Giữ dấu `_` cách hậu tố bằng ít nhất một chữ số, ví dụ `1_000L`.

Đừng nhầm khả năng dễ đọc với độ chính xác hoặc giới hạn kiểu. `0xFF_FF_FF_FF` có các quy tắc giá trị và kiểu số nguyên của Java; việc thêm/bớt dấu `_` không thay đổi biểu diễn bit hay tính signedness. Giá trị `double` được biểu diễn bằng số thực nhị phân; `3.14_15` không “chính xác thập phân” hơn `3.1415`.

## 8. Cách tự phân tích một literal lạ trong code review

Thay vì bỏ dấu `_` bằng mắt ngay từ đầu, hãy kiểm tra theo thứ tự:

1. **Xác định đây có phải numeric literal?** `_52` có thể là identifier, còn `"1_000"` là string literal.
2. **Xác định cơ số:** số bắt đầu bằng `0b` là nhị phân, `0x` là thập lục phân, `0` dẫn đầu ở số nguyên có thể tạo số bát phân, còn literal thông thường không có prefix là thập phân.
3. **Chia thành các thành phần:** prefix, phần chữ số, dấu chấm, exponent, dấu exponent, suffix kiểu.
4. **Kiểm tra dãy chữ số đúng cơ số:** ví dụ bát phân không có `8`/`9`, nhị phân không có `2`.
5. **Kiểm tra từng dấu `_`:** nó có thực sự nằm giữa các chữ số của cùng một thành phần không?
6. **Kiểm tra kiểu/range:** `int`/`long`, `float`/`double` có hợp đồng phạm vi và hậu tố riêng; lỗi range không được sửa bằng cách di chuyển `_`.
7. **Biên dịch ví dụ nhỏ:** khi không chắc, dùng `javac` trên một lớp tối giản thay vì suy diễn dựa trên màu cú pháp của IDE.

### Câu hỏi tự luyện

**Câu 1.** `0xA_B` có hợp lệ không? — **Có**. `A` và `B` là chữ số hex, `_` nằm giữa chúng.

**Câu 2.** `0x_AB` có hợp lệ không? — **Không**. `_` đứng ngay sau prefix `0x`.

**Câu 3.** `0_52` và `52` có bằng nhau không? — **Không**. Chúng lần lượt mang giá trị thập phân `42` và `52`.

**Câu 4.** `1.2e1_0` và `1.2e10` có bằng nhau không? — **Có**. Dấu `_` giữa hai chữ số exponent không thay đổi số mũ.

**Câu 5.** `1e+_10` có hợp lệ không? — **Không**. `_` nằm sát dấu `+` thay vì giữa các chữ số mũ.

**Câu 6.** `5___2` có hợp lệ không? — **Có**, giá trị bằng `52`; tuy nhiên cách nhóm này thường khó đọc.

**Câu 7.** `Integer.parseInt("2_000")` có đọc được `2000` không? — **Không**. Đây là parsing chuỗi runtime, không phải cú pháp numeric literal của mã nguồn.

## 9. Checklist trước khi đưa vào codebase

- [ ] Mỗi `_` được đặt giữa các chữ số hợp lệ của đúng thành phần literal.
- [ ] Không có `_` sát `0b`/`0x`, `.`, `e`/`E`/`p`/`P`, dấu của exponent hoặc hậu tố `L`/`F`/`D`.
- [ ] Đã xác định cơ số và kiểu số; không vô tình biến số thập phân mong muốn thành bát phân.
- [ ] Đã kiểm tra range: không nhầm lỗi vượt `int`/`long` với lỗi gạch dưới.
- [ ] Đặt dấu có quy luật dễ đọc, không dùng chuỗi `___` chỉ vì cú pháp cho phép.
- [ ] Đã chạy `javac` với ít nhất một ca hợp lệ, một ca không hợp lệ và một ca góc (ví dụ `0_52`).
- [ ] Không áp dụng quy tắc `_` của source code cho `Integer.parseInt` hoặc đầu vào người dùng nếu chưa định nghĩa cách phân tích.

## Nguồn tham khảo chuẩn

- [Java Language Specification — `3.10.1 Integer Literals và `3.10.2 Floating-Point Literals (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html#jls-3.10): cú pháp literal, dấu `_` giữa chữ số, cơ số và thành phần số thực trên JDK hiện hành.
- [Dev.java — Primitive Types, Using Underscore Characters in Numeric Literals](https://dev.java/learn/language/constructs/basics/primitive-types/): giải thích quy tắc sử dụng và ví dụ hợp lệ/không hợp lệ.
- [Oracle — Underscores in Numeric Literals](https://docs.oracle.com/javase/8/docs/technotes/guides/language/underscores-literals.html): mô tả tính năng được bổ sung từ Java 7 và các trường hợp cú pháp.

**Kết luận:** dấu `_` làm literal **dễ đọc hơn** ở cấp mã nguồn; giá trị không thay đổi. Quy tắc đáng nhớ là **nằm giữa chữ số trong cùng thành phần literal**, sau đó cần kiểm tra cơ số, type suffix, phạm vi kiểu và kết quả `javac` để tránh nhầm lỗi.