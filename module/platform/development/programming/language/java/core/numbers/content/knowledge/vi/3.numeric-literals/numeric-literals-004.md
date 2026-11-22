# Bẫy số 0 ở đầu literal bát phân trong Java

Trong Java, **một số nguyên viết trực tiếp trong mã nguồn với chữ số `0` ở đầu có thể là literal hệ bát phân (octal, cơ số 8)**. Vì vậy, `010` trong mã Java **không phải số thập phân 10**: nó có giá trị **8**. Ngược lại, `08` không phải cách viết hợp lệ của một literal số nguyên Java, vì chữ số `8` không tồn tại trong hệ bát phân.

Đây là một bẫy dễ bỏ qua khi người lập trình thêm số 0 để căn chỉnh, sao chép một mã có số 0 đầu vào biểu thức số học, hoặc nhầm lẫn giữa **cú pháp literal trong source code** và **chuỗi số đọc lúc chạy**. Bài học này tập trung vào nguyên nhân, lỗi thường gặp và cách xử lý chính xác trong Java.

## 1. Literal số nguyên là gì và số 0 đầu có nghĩa gì?

**Literal** là cách viết trực tiếp một giá trị trong mã nguồn. Ví dụ:

```java
int decimal = 10;  // Hệ thập phân: 10
int octal = 010;   // Hệ bát phân: 8
```

Hai biến đều có kiểu `int`, nhưng giữ **hai giá trị khác nhau**. Trình biên dịch Java diễn giải ký hiệu literal **ngay khi biên dịch**, trước khi chương trình chạy.

Các cú pháp số nguyên thường gặp:

| Cách viết trong Java | Hệ cơ số | Giá trị hệ thập phân | Nhận xét |
| --- | ---: | ---: | --- |
| `10` | 10 | 10 | Literal thập phân thông thường |
| `010` | 8 | 8 | Số `0` đầu kích hoạt cách viết bát phân |
| `012` | 8 | 10 | `1 × 8 + 2 = 10` |
| `077` | 8 | 63 | `7 × 8 + 7 = 63` |
| `0123` | 8 | 83 | `1 × 64 + 2 × 8 + 3 = 83` |
| `0` | Giá trị 0 | 0 | Một số 0 đơn lẻ không gây bẫy chuyển giá trị |
| `000` | 8 | 0 | Có thể viết được nhưng dễ gây hiểu nhầm |
| `0b1010` | 2 | 10 | Nhị phân có tiền tố `0b`/`0B` |
| `0xA` | 16 | 10 | Thập lục phân có tiền tố `0x`/`0X` |
| `010L` | 8 | 8 | Literal bát phân kiểu `long` |

**Quy tắc nhận diện:** một literal **nguyên** không có `0x`/`0X` hoặc `0b`/`0B`, bắt đầu bằng `0` và còn chữ số phía sau, được đọc theo cú pháp bát phân. Các chữ số hợp lệ của hệ bát phân chỉ là `0` đến `7`.

Java không có tiền tố `0o` cho literal bát phân như một số ngôn ngữ khác. Viết `0o12` trong Java là lỗi biên dịch. Cách viết bát phân thông dụng trong source Java là `012`, nhưng khi mục đích chỉ là giá trị thập phân, hãy viết `10`.

## 2. Tại sao 010 lại bằng 8?

Ở hệ thập phân, mỗi vị trí là một lũy thừa của 10. Ở hệ bát phân, mỗi vị trí là một lũy thừa của 8. Chữ số `0` phía trước đánh dấu cách diễn giải literal, không thêm một hàng thập phân.

Với `010`:

```text
Literal Java: 010
Chữ số bát phân: 1 0
Giá trị thập phân: 1 × 8¹ + 0 × 8⁰ = 8
```

Với `0123`:

```text
Literal Java: 0123
Chữ số bát phân: 1 2 3
Giá trị thập phân: 1 × 8² + 2 × 8¹ + 3 × 8⁰
                  = 64 + 16 + 3
                  = 83
```

Do đó, `010 == 8` là `true` nhưng `010 == 10` là `false`. Điều này không phải lỗi của toán tử so sánh và không liên quan đến tràn số. Trình biên dịch đã gán cho literal `010` giá trị 8 từ đầu.

Một nhầm lẫn có thể len vào ứng dụng:

```java
int retries = 03;      // Thực tế là 3; vô tình chưa thấy lỗi.
int timeout = 010;     // Thực tế là 8, không phải 10.
int limit = 012;       // Thực tế là 10, không phải 12.
```

Các dòng trên là ví dụ khai báo độc lập. Chính sự trùng hợp ở `03` khiến kiểu viết số 0 đầu có thể qua code review mà không bị phát hiện, trước khi xuất hiện giá trị `010` hoặc `012` cho kết quả khác mong đợi.

## 3. Lỗi biên dịch: 08 và 09 không hợp lệ trong literal số nguyên

Hệ bát phân chỉ sử dụng tám chữ số `0, 1, 2, 3, 4, 5, 6, 7`. Các literal số nguyên sau **không biên dịch được**:

```java
// Ví dụ lỗi có chủ đích; KHÔNG đưa vào file demo hợp lệ.
int august = 08;  // LỖI: chữ số 8 không hợp lệ trong literal bát phân.
int year = 09;    // LỖI: chữ số 9 không hợp lệ trong literal bát phân.
int value = 018;  // LỖI: có chữ số 8 trong literal bát phân.
```

**Sửa đúng:** nếu ý định là số nguyên thập phân tám, chín, mười tám, viết:

```java
int august = 8;
int year = 9;
int value = 18;
```

Đừng sửa lỗi bằng cách đổi `08` sang `008`; chữ số `8` vẫn không hợp lệ. Đừng mặc định sửa bằng cách chuyển kiểu sang `long`: `08L` vẫn không hợp lệ vì hậu tố `L` chỉ xác định **kiểu**, không thay đổi cơ số.

### Ngoại lệ quan trọng: 08.0 là literal số thực hợp lệ

Bẫy trên áp dụng cho **literal số nguyên**. Khi có dấu chấm thập phân hoặc cú pháp số thực thích hợp, `08.0` được phân tích là literal dấu phẩy động thập phân và hợp lệ:

```java
double decimalFloating = 08.0; // Hợp lệ: 8.0 (double)
float decimalFloat = 08.0f;    // Hợp lệ: 8.0f (float)
```

Việc `08.0` biên dịch được không có nghĩa `08` là literal nguyên hợp lệ. Cũng không có nghĩa nên thêm `.0` để “sửa” mọi biểu thức: làm như vậy đổi kiểu và có thể thay đổi semantics tính toán (ví dụ chia nguyên so với chia thực). Nếu muốn số nguyên tám, dùng `8`.

## 4. Số 0 đầu xuất hiện ở đâu, và chỗ nào không gây hiểu theo bát phân?

Cần phân biệt bốn ngữ cảnh sau:

| Ngữ cảnh | Cách viết | Giá trị hoặc hành vi |
| --- | --- | --- |
| Literal số nguyên trong mã nguồn | `int x = 010;` | `x == 8` |
| Chuỗi ký tự trong mã nguồn | `String s = "010";` | Ba ký tự `0`, `1`, `0` |
| Chuyển chuỗi sang số nguyên thập phân | `Integer.parseInt("010")` | `10`, vì radix mặc định là 10 |
| Chuyển chuỗi với radix 8 | `Integer.parseInt("010", 8)` | `8` |
| Dùng parser tự phát hiện tiền tố | `Integer.decode("010")` | `8`, vì `decode` nhận biết số 0 đầu là bát phân |

**Đây là điểm mấu chốt:** **`010`** là ký pháp số nguyên được trình biên dịch xử lý, còn **`"010"`** chỉ là chuỗi. Không có một quy tắc “mọi chuỗi bắt đầu bằng 0 đều là bát phân” trong Java.

Ví dụ hợp lệ:

```java
String text = "010";
int decimal = Integer.parseInt(text);      // 10
int decimalExplicit = Integer.parseInt(text, 10); // 10
int octal = Integer.parseInt(text, 8);     // 8
int decoded = Integer.decode(text);        // 8
```

`Integer.parseInt` **không tự dò cơ số**. `Integer.decode` thì có cơ chế phát hiện ký hiệu `0x`/`0X`, `#` cho hex và số 0 đầu cho bát phân. Nếu người dùng nhập `"08"`, `Integer.parseInt("08")` trả 8, nhưng `Integer.decode("08")` ném `NumberFormatException` vì `decode` diễn giải đầu vào theo bát phân. `Long.parseLong` và `Long.decode` cũng có sự phân biệt tương ứng.

Khi đầu vào luôn là **số thập phân**, gọi `Integer.parseInt(text, 10)` hoặc `Long.parseLong(text, 10)` sẽ rõ ý định và dễ bảo trì hơn dùng `decode`. Chỉ dùng `decode` khi đặc tả thực sự yêu cầu người dùng được nhập nhiều cơ số với các tiền tố quy ước.

## 5. Cần giữ số 0 đầu: mã định danh hay số lượng?

Thử xét hai dữ liệu đều viết là `0010`:

- **Số lượng 10 sản phẩm:** giá trị toán học là mười; kiểu `int` và literal `10` là phù hợp. Khi cần hiển thị đủ bốn chữ số, định dạng lại ở **lớp hiển thị**, chẳng hạn `String.format("%04d", 10)`.
- **Mã vé `"0010"`:** dãy ký tự, không phải số lượng. Dùng `String` để giữ đầy đủ số 0 đầu. Chuyển mã sang `int` làm mất hình thức nhận diện; không thể suy ra có bao nhiêu số 0 ban đầu nếu chưa có quy định chiều dài.

```java
String ticketCode = "0010"; // Giữ nguyên định danh.
int count = 10;            // Giá trị số học.
String countLabel = String.format(
        java.util.Locale.ROOT, "%04d", count); // "0010"
```

Ví dụ trên là mảnh mã Java. **Chọn `String`** cho mã bưu chính, mã khách hàng, số điện thoại, mã đơn hàng, ID có số 0 đầu hoặc chuỗi mà các ký tự mang ý nghĩa riêng. Đừng dùng `int postalCode = 01234;`: ngoài việc làm mất định dạng gốc, giá trị đó còn bị diễn giải thành bát phân và tương đương **668 thập phân**, không phải 1234.

Nếu trường nhập là số lượng có thể cho phép người dùng gõ `"0010"`, hãy quyết định rõ có chấp nhận số 0 đệm hay không: `Integer.parseInt("0010", 10)` nhận và trả 10. Nếu chính sách nhập yêu cầu dạng chuẩn không có số 0 thừa, phải xác thực cú pháp trước khi parse; parser thập phân không tự áp đặt quy tắc nghiệp vụ đó.

## 6. Số 0 đầu trong literal không phải quy tắc chung của JSON, CSV hay cơ sở dữ liệu

Bẫy này thuộc **cú pháp mã nguồn Java**. Không được suy rộng rằng mọi dữ liệu bên ngoài mang chữ số `0` đầu đều phải đọc là bát phân:

- Trong **CSV**, giá trị `0010` là dữ liệu văn bản ban đầu; cách chuyển sang kiểu số phụ thuộc thư viện nhập, schema và radix được chỉ định.
- Trong **JSON chuẩn**, number `010` không hợp lệ vì ngữ pháp JSON không cho số nguyên có số 0 dư ở đầu. Dùng `10` nếu là số lượng, hoặc `"0010"` nếu phải bảo toàn mã.
- Trong **cơ sở dữ liệu**, một trường `VARCHAR` giữ chuỗi theo cách lưu trữ; trường số nguyên lưu giá trị số. Cách truyền dữ liệu qua driver, SQL dialect và cách format kết quả có thể khác nhau; đừng suy ra rằng DB sẽ diễn giải số 0 đầu giống literal Java.
- Trong **cấu hình**, cách hiểu `010` tùy định dạng và thư viện parser. Ví dụ, các phiên bản/quy tắc YAML khác nhau từng có khác biệt về số 0 đầu. Hãy cấu hình rõ kiểu và quy tắc đọc, tránh giả định.

Khi nhận giá trị từ API hoặc file, tốt nhất là **xác định schema**: trường là số lượng thập phân, mã định danh hay một literal có cơ số cho phép chọn? Một lần parse sai ở biên hệ thống có thể lặng lẽ biến dữ liệu hợp lệ thành một con số khác.

## 7. Phép tính, số âm và kiểu long vẫn chịu quy tắc literal

Hậu tố `L` trên literal nguyên chỉ thay đổi kiểu từ `int` sang `long` (khi thích hợp), không thay cơ số:

```java
long expectedDecimal = 10L;
long octalLong = 010L;       // 8L
```

Dấu trừ là **toán tử một ngôi** áp dụng lên giá trị literal: `-010` là âm tám (`-8`), không phải âm mười. Tương tự, `+010` có giá trị tám.

```java
int a = 010 + 1;       // 9, vì 010 == 8
int b = 10 + 1;        // 11
boolean same = 010 == 8;  // true
int negative = -010;   // -8
```

Khi kết quả bị lệch, hãy xem **literal ở đầu vào** trước khi nghi ngờ phép cộng, phép trừ hay ép kiểu. In ra số bằng `System.out.println` thường cho biểu diễn thập phân của **giá trị đã lưu**, nên chương trình `System.out.println(010);` in `8`.

Literal `0` đơn lẻ có giá trị 0 và không tạo sai khác số học; `00`, `000` vẫn có giá trị 0. Nhưng thói quen thêm số 0 đầu là rủi ro vì các chữ số khác 0 có thể đổi nghĩa hoặc làm mã không biên dịch.

## 8. Ví dụ Java 17+ hoàn chỉnh để tự kiểm chứng

Tạo file **`OctalLeadingZeroDemo.java`** với nội dung sau. Chương trình chỉ dùng các literal **hợp lệ**; những dòng `08`/`09` sai cú pháp ở phần trước đã được tách ra khỏi chương trình chạy được.

```java
import java.util.Locale;

public class OctalLeadingZeroDemo {
    public static void main(String[] args) {
        int decimalTen = 10;
        int octalTen = 010;
        int octalForTen = 012;
        long octalLong = 010L;

        System.out.println("decimal-10=" + decimalTen);
        System.out.println("octal-010=" + octalTen);
        System.out.println("octal-012=" + octalForTen);
        System.out.println("octal-long=" + octalLong);
        System.out.println("binary-1010=" + 0b1010);
        System.out.println("hex-a=" + 0xA);
        System.out.println("negative-octal=" + (-010));
        System.out.println("decimal-floating=" + 08.0);

        String input = "010";
        System.out.println("parse-decimal=" + Integer.parseInt(input));
        System.out.println("parse-octal=" + Integer.parseInt(input, 8));
        System.out.println("decode-octal=" + Integer.decode(input));
        System.out.println("octal-format=" + Integer.toOctalString(10));

        String ticketCode = "0010";
        System.out.println("ticket-code=" + ticketCode);
        System.out.println("padded-count=" +
                String.format(Locale.ROOT, "%04d", 10));

        try {
            Integer.decode("08");
        } catch (NumberFormatException ex) {
            System.out.println("decode-08=NumberFormatException");
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 hoặc phiên bản mới hơn:

```bash
javac OctalLeadingZeroDemo.java
java OctalLeadingZeroDemo
```

Kết quả stdout:

```text
decimal-10=10
octal-010=8
octal-012=10
octal-long=8
binary-1010=10
hex-a=10
negative-octal=-8
decimal-floating=8.0
parse-decimal=10
parse-octal=8
decode-octal=8
octal-format=12
ticket-code=0010
padded-count=0010
decode-08=NumberFormatException
```

Giải thích các điểm dễ lẫn:

1. `010` và `010L` có giá trị 8 vì là bát phân; hậu tố `L` chỉ làm kết quả mang kiểu `long`.
2. `012`, `0b1010`, `0xA` và `10` đều có giá trị thập phân 10 dù ký pháp khác nhau.
3. `08.0` là literal `double` hợp lệ và in `8.0`; `08` nguyên thì không hợp lệ.
4. Cùng chuỗi `"010"`, `parseInt` mặc định ra 10 còn `decode` ra 8.
5. `Integer.toOctalString(10)` cho chuỗi `"12"` vì 10 thập phân tương đương 12 bát phân. Chuỗi kết quả không tự thêm số 0 đầu theo cú pháp literal Java.
6. Mã `"0010"` giữ đúng ký tự; phần định dạng `%04d` tạo chuỗi có số 0 đệm cho giá trị số mười, nhưng không đổi giá trị số nguyên trong bộ nhớ.

## 9. Phân biệt lỗi khi biên dịch và lỗi khi chạy

| Mã hoặc thao tác | Thời điểm phát hiện | Nguyên nhân |
| --- | --- | --- |
| `int x = 08;` | Biên dịch | Chữ số 8 không hợp lệ trong literal nguyên bát phân |
| `int x = 09;` | Biên dịch | Chữ số 9 không hợp lệ trong literal nguyên bát phân |
| `int x = 010;` | Không lỗi; có thể **sai logic** khi chạy | Hợp lệ nhưng giá trị thực là 8 |
| `Integer.parseInt("08", 10)` | Không lỗi; trả 8 | Parse chuỗi với cơ số thập phân |
| `Integer.parseInt("08", 8)` | Runtime: `NumberFormatException` | Đầu vào có chữ số không thuộc radix 8 |
| `Integer.decode("08")` | Runtime: `NumberFormatException` | Tự nhận dạng cơ số 8 do số 0 đầu |
| `Integer.parseInt("0010", 10)` | Không lỗi; trả 10 | Phân tích số và bỏ các số 0 thừa về mặt giá trị |
| `String code = "0010";` | Không lỗi; giữ `"0010"` | Dữ liệu chuỗi, không phải literal số nguyên |

Điều nguy hiểm nhất là trường hợp **không báo lỗi**: `010` hợp lệ nên unit test chỉ kiểm tra biên dịch, hoặc test data chỉ dùng `01` đến `07`, có thể không phát hiện sai lệch. Đây là lỗi **ngữ nghĩa** của code.

## 10. Cách phòng tránh trong code thật

### 10.1. Viết literal theo ý nghĩa muốn thể hiện

- Nếu ý định là số thập phân, **không viết số 0 ở đầu**: `8`, `10`, `123`.
- Nếu ý định là giá trị bit/permission hoặc cơ số đặc biệt, có thể dùng ký pháp phù hợp và thêm chú thích về ý nghĩa; đối với bitmask, `0b...` hoặc `0x...` thường dễ đọc hơn.
- Nếu ý định là **định dạng có số 0 đệm**, dùng `String` và định dạng ở nơi nhập/xuất; không dùng literal nguyên bắt đầu bằng 0.
- Khi đọc chuỗi số, **chỉ rõ radix** nếu đầu vào có thể bị hiểu nhầm: `Integer.parseInt(text, 10)`.

### 10.2. Kiểm tra dữ liệu đầu vào và radix

Một parser đơn giản cho **số đếm không âm, dạng thập phân chuẩn, không cho số 0 thừa** có thể viết như sau:

```java
static int parseCanonicalCount(String text) {
    if (text == null || !text.matches("0|[1-9][0-9]*")) {
        throw new IllegalArgumentException("Invalid decimal count");
    }
    return Integer.parseInt(text, 10);
}
```

Đây là phương thức minh họa, đặt bên trong một class Java. Theo hợp đồng này, `"0"`, `"8"`, `"10"` hợp lệ, còn `"08"`, `"010"`, `"-1"`, chuỗi trống hoặc giá trị chứa khoảng trắng bị từ chối. Một chuỗi toàn chữ số quá lớn vẫn có thể khiến `Integer.parseInt` ném `NumberFormatException` do vượt miền `int`; có thể bắt và chuyển thành lỗi validation thống nhất tại biên API.

Nếu yêu cầu nghiệp vụ **cho phép số 0 đầu**, không áp dụng regex này: dùng parser thập phân với radix 10, hoặc giữ chuỗi nếu đó là mã. Kiểm tra dữ liệu phải dựa trên đặc tả, không mặc định một chính sách cho tất cả trường.

### 10.3. Test đặc biệt tại các mốc 07, 08, 09, 010

Trong review và kiểm thử, chú ý những vùng dữ liệu tuần tự có padding, đặc biệt ngày, tháng, phiên bản và mã từ `01` đến `12`. Ví dụ, ghi `int month = 010;` với ý định tháng 10 sẽ thực sự lưu 8; còn `int month = 08;` không biên dịch. Kiểm thử tháng 1–7 không thể chứng minh cách viết đó đúng cho tháng 8–12.

Các mẫu tìm kiếm số 0 đầu trong source có thể hỗ trợ review, nhưng cần đọc ngữ cảnh: số 0 trong **chuỗi**, số thực `08.0`, các literal `0x...`/`0b...`, các giá trị 0 và các comment không nên bị đánh đồng với lỗi. Static analysis và code review cần nêu rõ ý định của literal trước khi sửa.

### 10.4. Đừng tự động “sửa” dữ liệu mã thành số

Nếu người dùng gửi `"00123"`, ứng dụng cần biết đây là **mã** hay **số lượng** trước khi parse. Chuyển thành số 123 rồi ghi lại chuỗi `"123"` có thể làm mất tính định danh, kể cả khi không hề dùng octal. Ngược lại, một phép tính đếm không nên giữ số 0 đầu chỉ để “giống màn hình”; trình bày tách biệt khỏi giá trị.

## 11. Câu hỏi tự kiểm tra

1. Tính giá trị thập phân của `010`, `012`, `077`, `0123` mà không chạy Java. Giải thích bằng tổng các lũy thừa của 8.
2. Trong bốn biểu thức `08`, `08.0`, `010L`, `0o10`, biểu thức nào là literal Java hợp lệ? Biểu thức nào không biên dịch được và vì sao?
3. Cho `String s = "010";`, dự đoán kết quả `Integer.parseInt(s)`, `Integer.parseInt(s, 8)`, `Integer.decode(s)`. Trường hợp nào phù hợp để xử lý một chuỗi số lượng nhập theo hệ thập phân?
4. Vì sao `int month = 010;` là bẫy khó thấy hơn `int month = 08;`? Test hoặc công cụ nào có thể giúp phát hiện?
5. Một mã khách hàng `"000123"` phải giữ nguyên khi gửi qua API và lưu vào database. Bạn chọn kiểu Java nào, loại cột/schema nào và định dạng JSON nào? Vì sao dùng `int` có thể làm mất thông tin?
6. Sửa chương trình sau để giữ ý định “giới hạn mười” mà không đổi sang kiểu thực:

```java
int limit = 010;
System.out.println(limit + 2);
```

Đáp án: đổi literal thành `10`, khi đó chương trình in `12`. Mã ban đầu in `10` vì `010` là 8.

## 12. Ghi nhớ

- **Trong mã nguồn Java, `010` là literal nguyên bát phân có giá trị 8**, còn `10` là literal thập phân có giá trị 10.
- **`08` và `09` không phải literal số nguyên hợp lệ**, nhưng `08.0` là literal số thực thập phân hợp lệ.
- **`"010"` là chuỗi**, không được tự diễn giải thành bát phân. `Integer.parseInt("010")` trả 10; `Integer.decode("010")` trả 8.
- Giữ số 0 đầu bằng **chuỗi/định dạng**, không bằng cách thêm số 0 vào literal nguyên.
- Khi review code, kiểm tra ý nghĩa của dữ liệu, đặc biệt các giá trị tuần tự có padding, và viết rõ radix ở biên nhập liệu khi cần.

Chỉ một chữ số `0` được đặt sai chỗ có thể biến giá trị thập phân dự định thành giá trị bát phân mà Java vẫn biên dịch thành công. Cách phòng tránh hiệu quả nhất là tách **giá trị số học**, **cơ số biểu diễn** và **dạng văn bản của dữ liệu** ngay từ thiết kế.
