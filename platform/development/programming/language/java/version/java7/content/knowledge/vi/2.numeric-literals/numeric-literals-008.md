# Java 7 — Phân biệt literal trong mã với chuỗi dữ liệu cần phân tích

## 1. Hai thứ trông giống nhau nhưng được xử lý ở hai thời điểm khác nhau

Trong chủ đề **cú pháp số**, cần phân biệt:

- **Numeric literal trong mã nguồn**: cách viết một giá trị số trực tiếp trong tệp `.java`. Trình biên dịch Java (`javac`) phân tích cú pháp đó **khi biên dịch** và đưa giá trị thích hợp vào bytecode. Các ký hiệu như `0b` hoặc dấu gạch dưới phân nhóm chữ số chỉ là một phần của cú pháp nguồn.
- **Chuỗi ký tự biểu diễn số**: đối tượng `String` như `"0b1010"`, `"1_000"` hay dữ liệu lấy từ JSON, CSV, form, biến môi trường. Những ký tự này được giữ nguyên thành dữ liệu; để có một số, chương trình cần **phân tích chuỗi khi chạy** bằng API và quy tắc đã lựa chọn.

Ví dụ:

```java
int a = 1_000;            // Literal số: javac hiểu thành giá trị int 1000.
String b = "1_000";       // Literal chuỗi: 5 ký tự '1', '_', '0', '0', '0'.
int c = 0b1010;           // Literal nhị phân: giá trị int 10.
String d = "0b1010";      // Chuỗi dữ liệu, chưa phải số.
```

`a` và `c` đã có kiểu `int`. Với `b` và `d`, kiểu vẫn là `String`; không có phép chuyển đổi số tự động. Vì thế `Integer.parseInt("1_000")` không nhận diện dấu `_` như trình biên dịch, và `Integer.parseInt("0b1010", 2)` cũng không tự bỏ tiền tố `0b`.

Cả hai chuỗi `"1_000"` và `"0b1010"` có thể được viết nguyên văn trong mã Java hoặc đọc từ bên ngoài; **nguồn gốc chuỗi không thay đổi quy tắc của hàm parse**.

| Khía cạnh | Numeric literal | Chuỗi dữ liệu cần parse |
| --- | --- | --- |
| Ví dụ | `0b1010_0110` | `"0b1010_0110"` |
| Kiểu ban đầu | Kiểu số do ngôn ngữ quyết định, chẳng hạn `int` | `String` |
| Ai kiểm tra? | Trình biên dịch dựa trên Java Language Specification | API như `Integer.parseInt`, `BigDecimal` hoặc parser ứng dụng |
| Khi nào xảy ra lỗi? | Lúc biên dịch nếu cú pháp/giá trị literal không hợp lệ | Lúc chạy nếu chuỗi sai định dạng hoặc vượt miền giá trị |
| Dấu `_` và tiền tố cơ số | Có ý nghĩa theo ngữ pháp literal | Chỉ được chấp nhận nếu **parser cụ thể** định nghĩa như vậy |
| Kết quả | Giá trị số đã biên dịch | Giá trị số sau khi gọi parser thành công |

## 2. Cú pháp numeric literal vẫn hữu ích trên Java hiện đại

Java hỗ trợ literal số nguyên ở hệ thập phân, nhị phân, thập lục phân và bát phân. **Java 7 đưa vào literal nhị phân (`0b`/`0B`) và dấu gạch dưới phân nhóm chữ số**; các cú pháp này vẫn được hỗ trợ trong các JDK hiện đại.

### 2.1. Các cách viết khác nhau cho cùng một giá trị

```java
int decimal = 10;
int binary = 0b1010;
int hex = 0xA;
int separated = 1_0;

long count = 3_000_000_000L;
double rate = 1_234.5e2; // 123450.0
```

Bốn biến `int` đầu đều mang **giá trị số 10**, dù mã nguồn nhìn khác nhau. `0b` đánh dấu literal nhị phân, `0x` đánh dấu literal thập lục phân; hậu tố `L` làm literal số nguyên thuộc kiểu `long`. `1_234.5e2` là literal dấu phẩy động có ký pháp mũ; các dấu gạch dưới không làm thay đổi giá trị.

Khi in `System.out.println(binary)`, kết quả mặc định là `10`: cách Java biểu diễn số ở đầu vào **không tự được lưu thành định dạng in ra**. Muốn tạo chuỗi nhị phân, dùng `Integer.toBinaryString(binary)` (cho `"1010"`), hoặc tự thêm `"0b"` nếu giao thức hiển thị yêu cầu.

### 2.2. Dấu gạch dưới là cú pháp của literal, không phải ký tự số

Những cách viết sau hợp lệ:

```java
int users = 1_000_000;
int mask = 0b1010_0011;
int color = 0xCA_FE;
long sequence = 12_345L;
double fraction = 3.14_15;
```

Dấu `_` được dùng **giữa các chữ số** của literal. Với binary/hex, không được đặt ngay sau `0b`/`0x` hoặc sau chữ số cuối. Không được đặt sát dấu thập phân hoặc sát hậu tố kiểu. Ví dụ sau là **minh họa mã sai, không được đưa vào chương trình cần biên dịch**:

```text
0b_1010    // Sai: ngay sau tiền tố nhị phân.
0x_FF      // Sai: ngay sau tiền tố hex.
1000_      // Sai: sau chữ số cuối.
1_.5       // Sai: sát dấu thập phân.
1._5       // Sai: sát dấu thập phân.
123_L      // Sai: trước hậu tố L.
```

Ngữ pháp Java cho phép nhiều dấu gạch dưới liên tiếp **nếu vẫn nằm giữa các chữ số** (ví dụ `1__000`), nhưng cách viết một dấu giữa các nhóm có ý nghĩa thường dễ đọc và dễ kiểm tra hơn. Không suy luận từ quy tắc literal rằng thư viện parse chuỗi cũng chấp nhận dấu `_`.

### 2.3. Bẫy số bắt đầu bằng `0`

Cú pháp literal bát phân với số `0` ở đầu vẫn tồn tại trong Java, nhưng dễ gây hiểu lầm. Khi một chuỗi dữ liệu là mã đơn hàng, mã vùng, hoặc số có số `0` ở đầu, **không nên dùng cú pháp bát phân để suy đoán ý nghĩa**.

| Biểu thức | Kết quả | Tại sao? |
| --- | --- | --- |
| `int n = 010;` | `8` | `010` là literal bát phân trong mã nguồn. |
| `Integer.parseInt("010")` | `10` | `parseInt` mặc định phân tích **thập phân**. |
| `Integer.parseInt("010", 10)` | `10` | Cơ số đã được chỉ rõ. |
| `Integer.decode("010")` | `8` | `decode` coi chuỗi có tiền tố `0` là bát phân. |

Một biểu thức nguồn như `int n = 08;` là **lỗi biên dịch**, do `8` không phải chữ số bát phân; trong khi `Integer.parseInt("08")` là `8` hợp lệ ở cơ số 10.

Trong dữ liệu nghiệp vụ hiện nay, hãy quy định rõ **cơ số 10** cho số thập phân và **giữ String** cho mã định danh có số `0` đầu. Tránh tự động chọn bát phân chỉ vì dữ liệu bắt đầu bằng `0`.

## 3. API phân tích chuỗi số: mỗi API có ngữ pháp riêng

Những phương thức thường dùng là:

| Dữ liệu mong muốn | API thông dụng | Lưu ý |
| --- | --- | --- |
| Số nguyên 32-bit có dấu, hệ 10 | `Integer.parseInt(text)` | Mặc định cơ số 10; giới hạn `int`. |
| Số nguyên có dấu theo cơ số rõ ràng | `Integer.parseInt(text, radix)` | Phần chữ số phải phù hợp cơ số; không nhận tiền tố `0b`/`0x` như literal. |
| Số nguyên 64-bit có dấu | `Long.parseLong(text)` | Dùng khi giá trị nằm ngoài miền `int` nhưng trong miền `long`. |
| Số nguyên kích thước tùy ý | `new BigInteger(text, radix)` | Dùng với số vượt miền primitive; đầu vào tuân theo ngữ pháp của constructor. |
| Số thập phân cần độ chính xác dạng thập phân | `new BigDecimal(text)` | Hữu ích cho số tiền và các phép tính cần chính xác thập phân; không hỗ trợ dấu `_` trong chuỗi. |
| Giá trị dấu phẩy động nhị phân | `Double.parseDouble(text)` | Dùng khi chấp nhận sai số làm tròn của `double`; có thể nhận `NaN`/`Infinity`. |
| Chuỗi với quy ước tiền tố 16/8/10 | `Integer.decode(text)` | Nhận một số tiền tố như `0x`, `0X`, `#`, `0`; không nhận `0b` hoặc dấu `_`. Không phù hợp cho dữ liệu thập phân tự do có số `0` đầu. |

`Integer.parseInt` có thể chấp nhận dấu `+` hoặc `-` ở đầu, và sử dụng `Character.digit` để nhận chữ số tương ứng với cơ số; vì vậy **không nên giả định API chỉ nhận ký tự ASCII**. Nếu một giao thức chỉ cho phép `0–9` ASCII, hãy kiểm tra định dạng riêng trước khi parse.

### 3.1. Các cặp rất dễ nhầm

```java
Integer.parseInt("1010", 2);  // 10: chuỗi chứa chữ số cơ số 2.
Integer.parseInt("FF", 16);    // 255: chuỗi chứa chữ số cơ số 16.
Integer.parseInt("010");       // 10: mặc định cơ số 10.
Integer.decode("0xFF");        // 255: decode xử lý tiền tố 0x.
```

Các lời gọi tiếp theo **ném `NumberFormatException`**:

```java
Integer.parseInt("0b1010", 2);  // parseInt không nhận tiền tố 0b.
Integer.parseInt("0xFF", 16);    // parseInt không nhận tiền tố 0x.
Integer.parseInt("1_000");      // Dấu _ của literal không hợp lệ ở đây.
Integer.parseInt(" 42 ");       // parseInt không tự xóa khoảng trắng.
Integer.parseInt("2147483648"); // Quá miền int có dấu.
```

Với chuỗi nhị phân có tiền tố `0b`, khi **định dạng dữ liệu cho phép tiền tố đó**, có thể xác thực tiền tố rồi bỏ đúng hai ký tự để parse phần còn lại. Khi nhận chuỗi từ file/HTTP/UI, đừng nhầm chuỗi này với một token mã nguồn Java được `javac` xử lý.

### 3.2. Những gì `Integer.decode` làm và không làm

`Integer.decode("0xFF")` hữu ích khi đầu vào **được tài liệu hóa rõ ràng** là dùng tiền tố cho cơ số. Nhưng `Integer.decode("010")` trả `8` vì coi đó là bát phân, khác với cách nhiều người dùng hiểu số `010`. Phương thức này cũng không phải parser toàn diện cho mọi literal Java: `Integer.decode("0b1010")`, `Integer.decode("1_000")` và `Integer.decode("100L")` đều không hợp lệ.

Với dữ liệu số thập phân từ form, file CSV, API, biến cấu hình hoặc database, **chọn `Integer.parseInt(text, 10)` hoặc `Long.parseLong(text, 10)`** khi hợp đồng định dạng quy định decimal. Chỉ chọn `decode` nếu chính hợp đồng đầu vào chủ ý chấp nhận các tiền tố do `decode` định nghĩa.

### 3.3. Chuỗi trống, khoảng trắng, giá trị lỗi và tràn số

`Integer.parseInt` có thể ném `NumberFormatException` khi chuỗi không có dạng số nguyên phù hợp, vượt miền giá trị hoặc đầu vào không hợp lệ. Trước khi parse dữ liệu bên ngoài, hãy quyết định:

1. Có cho phép `null`/chuỗi rỗng không? Nếu không, báo lỗi dữ liệu rõ ràng.
2. Có chấp nhận khoảng trắng đầu/cuối không? Nếu có, chủ động gọi `strip()` (API Java 11+, khả dụng với JDK 17+) rồi kiểm tra còn rỗng hay không. **Đừng mặc định tự động bỏ khoảng trắng bên trong.**
3. Có cho phép dấu `+`/`-`, số `0` đầu, các cơ số khác 10 hoặc số rất lớn không?
4. Khi không parse được, có cần báo lỗi người dùng, ghi log có ngữ cảnh hoặc trả lỗi xác thực đầu vào không? Tránh coi số không hợp lệ là `0` vì có thể làm sai ý nghĩa dữ liệu.
5. Có cần bảo toàn các số `0` đầu không? Với mã định danh (ví dụ `"000123"`), **không chuyển sang số nếu không có phép toán số học**.

**Tràn số là lỗi parse, không phải phép làm tròn:** `Integer.parseInt("2147483648")` thất bại vì vượt `Integer.MAX_VALUE`. Nếu dữ liệu thực sự là số nguyên lớn hơn, hãy dùng `Long` hoặc `BigInteger` và xác thực miền nghiệp vụ.

## 4. Chương trình Java 17+ hoàn chỉnh: so sánh literal với text

Tạo tệp `NumericLiteralVsTextDemo.java`:

```java
import java.math.BigDecimal;

public class NumericLiteralVsTextDemo {
    public static void main(String[] args) {
        int binaryLiteral = 0b1010_0110;
        int decimalLiteral = 1_000_000;
        int hexadecimalLiteral = 0xFF;

        System.out.println("binary literal = " + binaryLiteral);
        System.out.println("decimal literal = " + decimalLiteral);
        System.out.println("hex literal = " + hexadecimalLiteral);
        System.out.println("decimal text 010 = " + Integer.parseInt("010"));
        System.out.println("binary text 1010 = " + Integer.parseInt("1010", 2));
        System.out.println("hex text FF = " + Integer.parseInt("FF", 16));
        System.out.println("prefixed hex text = " + Integer.decode("0xFF"));
        System.out.println("trimmed decimal text = " + Integer.parseInt(" 42 ".strip()));
        System.out.println("exact amount = " + new BigDecimal("1000.25").toPlainString());

        printRejected("1_000", 10);
        printRejected("0b1010", 2);
    }

    private static void printRejected(String text, int radix) {
        try {
            Integer.parseInt(text, radix);
            System.out.println(text + " -> accepted");
        } catch (NumberFormatException e) {
            System.out.println(text + " -> NumberFormatException");
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 NumericLiteralVsTextDemo.java
java NumericLiteralVsTextDemo
```

**Stdout chính xác:**

```text
binary literal = 166
decimal literal = 1000000
hex literal = 255
decimal text 010 = 10
binary text 1010 = 10
hex text FF = 255
prefixed hex text = 255
trimmed decimal text = 42
exact amount = 1000.25
1_000 -> NumberFormatException
0b1010 -> NumberFormatException
```

Giải thích: `javac` đã chuyển `0b1010_0110` thành giá trị `166` trước khi chạy. `Integer.parseInt` lại nhận **chữ số của cơ số được yêu cầu** khi chạy, không giải mã trọn bộ cú pháp literal từ tệp `.java`. Cụ thể, `"1010"` với radix 2 hợp lệ, còn `"0b1010"` với radix 2 không hợp lệ. `BigDecimal("1000.25")` biểu diễn chính xác giá trị thập phân dưới dạng `BigDecimal`.

Ví dụ cố ý bắt hai lỗi parsing để cho thấy chương trình vẫn chạy tới cuối; không nên dựa vào exception như một cách dò cơ số tùy tiện nếu dữ liệu đã có hợp đồng định dạng rõ ràng.

## 5. Nếu cần nhận chuỗi có hình thức giống literal, hãy tự định nghĩa hợp đồng nhập

Giả sử API của bạn **quy định** chuỗi nhị phân phải có tiền tố `0b` hoặc `0B`, tiếp theo là ít nhất một chữ số `0`/`1`. Khi đó có thể viết parser riêng có kiểm tra đầu vào; đừng trông chờ `Integer.parseInt` nhận nguyên tiền tố:

```java
static int parseBinaryWithPrefix(String text) {
    if (text == null || !text.matches("0[bB][01]+")) {
        throw new IllegalArgumentException("Expected 0b followed by binary digits");
    }
    return Integer.parseInt(text.substring(2), 2);
}
```

Đây là **phương thức minh họa** để đặt bên trong một lớp Java; nó không phải chương trình chạy độc lập. Với hợp đồng này, `parseBinaryWithPrefix("0b1010")` trả `10`, còn `"1010"`, `"0b10_10"` hoặc `"0b102"` bị từ chối. Chuỗi quá dài để chứa trong `int` vẫn có thể ném `NumberFormatException`; muốn hỗ trợ số nguyên tùy ý, cân nhắc `BigInteger`.

Nếu nghiệp vụ cho phép dấu gạch dưới trong chuỗi decimal, **cần quy định và xác thực vị trí dấu gạch dưới trước khi bỏ dấu**. Ví dụ, một hợp đồng đơn giản cho phép duy nhất **một hoặc không có** dấu `_` giữa hai nhóm chữ số ASCII có thể dùng regex `[+-]?[0-9]+(?:_[0-9]+)*` rồi gọi `Long.parseLong(text.replace("_", ""))`. Regex này **cố ý hẹp hơn** ngữ pháp literal Java (không nhận hai dấu `_` liền nhau), vì parser dữ liệu được quyền có hợp đồng riêng.

Không dùng riêng `text.replace("_", "")` mà bỏ qua xác thực: chuỗi `"_1000"`, `"1000_"` hoặc `"1__000"` có thể bị biến thành số hợp lệ dù người nhập sai định dạng bạn đã công bố.

Cũng cần phân biệt **chuỗi đầu vào đang biểu diễn giá trị số** với **mã định danh**. `"00123"` làm số thập phân có giá trị `123`, nhưng làm mã khách hàng hoặc mã bưu chính thì hai số `0` đầu có thể là thông tin quan trọng: giữ dưới dạng `String`.

## 6. Chuỗi thập phân, dấu phân cách và độ chính xác

### 6.1. Dữ liệu decimal chính xác khác dấu phẩy động nhị phân

```java
double approximation = Double.parseDouble("0.1");
BigDecimal exact = new BigDecimal("0.1");
```

`double` là số dấu phẩy động nhị phân; nhiều phân số thập phân như `0.1` không được biểu diễn chính xác tuyệt đối trong nhị phân. `BigDecimal(String)` giữ đúng giá trị thập phân mà chuỗi cung cấp. Với số tiền hoặc đơn vị cần quy tắc làm tròn xác định, thường nên dùng `BigDecimal` và quy định scale, `RoundingMode`, tiền tệ/đơn vị rõ ràng. Tránh `new BigDecimal(0.1)` khi mục đích là lấy đúng giá trị thập phân `0.1` đã viết.

Không suy luận rằng `double amount = 1_000.25;` cho phép `Double.parseDouble("1_000.25")`: dấu `_` vẫn là cú pháp **nguồn**, không phải một dấu nhóm số được parser mặc định hiểu. `Double.parseDouble("1e3")` hợp lệ và có giá trị `1000.0`; các quy tắc nó nhận được do **API của `Double`** quyết định, không phải vì chuỗi được parse như một biểu thức Java.

Nếu chỉ chấp nhận số hữu hạn (không `NaN`/`Infinity`), hãy kiểm tra `Double.isFinite(value)` sau khi parse thành `double`.

### 6.2. Dấu phẩy và định dạng theo vùng miền

Trong dữ liệu người dùng, `"1,234.50"` (theo quy ước US) hay `"1.234,50"` (theo một số locale khác) có thể mang nghĩa tương đương. Nhưng `Integer.parseInt` và `BigDecimal(String)` **không mặc định hiểu dấu phân nhóm của giao diện**. Với text được nhập theo locale, có thể dùng `NumberFormat` hoặc `DecimalFormat` với `Locale` chỉ định, đồng thời kiểm tra **toàn bộ chuỗi đã được tiêu thụ** và tính hợp lệ của nhóm chữ số. Một số parser locale có thể chấp nhận một phần chuỗi hoặc định dạng không chặt nếu chỉ gọi `parse` rồi tin ngay kết quả.

Phân biệt hai hướng thiết kế:

- **API, JSON, cấu hình kỹ thuật có chuẩn cố định:** dùng định dạng số trung lập, xác thực rõ chữ số/dấu thập phân/cơ số; với giá trị decimal chính xác, dùng `BigDecimal(String)`.
- **Trường nhập liệu hiển thị cho người dùng:** tách bước xác thực và chuyển đổi theo locale khỏi bước xử lý số; không chuyển dấu phân nhóm chỉ bằng thao tác thay ký tự nếu chưa biết quy tắc vùng miền.

Dù áp dụng cách nào, hãy lưu trữ/trao đổi **giá trị số có kiểu rõ ràng** hoặc chuỗi chuẩn hóa theo giao thức, thay vì lấy cách viết literal trong Java làm tiêu chuẩn trao đổi dữ liệu.

## 7. So sánh lỗi compile-time với lỗi runtime

| Mã hoặc chuỗi | Khi nào kiểm tra? | Điều gì xảy ra? |
| --- | --- | --- |
| `int n = 0b1010;` | Compile-time | Hợp lệ, `n = 10`. |
| `int n = 0b_1010;` | Compile-time | Lỗi cú pháp literal. |
| `int n = 1_000;` | Compile-time | Hợp lệ, `n = 1000`. |
| `String s = "1_000";` | Compile-time | Hợp lệ, `s` là chuỗi năm ký tự; chưa parse số. |
| `Integer.parseInt("1_000")` | Runtime | `NumberFormatException`. |
| `Integer.parseInt("1010", 2)` | Runtime | Giá trị `10`. |
| `Integer.parseInt("0b1010", 2)` | Runtime | `NumberFormatException`. |
| `Integer.parseInt("010")` | Runtime | Giá trị `10` theo thập phân. |
| `Integer.decode("010")` | Runtime | Giá trị `8` theo bát phân. |
| `Long.parseLong("3000000000")` | Runtime | Giá trị `long` 3 tỷ, trong miền hợp lệ. |
| `Long.parseLong("3_000_000_000L")` | Runtime | `NumberFormatException`: dấu `_`/hậu tố `L` không hợp lệ với parser này. |

Lưu ý: bảng dùng một số dòng **cố ý sai** để minh họa lỗi; không chép các dòng `int n = 0b_1010;` vào chương trình chạy. Với `NumberFormatException`, ví dụ lỗi xảy ra tại **lời gọi API**; nếu chuỗi đến từ input bên ngoài, giá trị chỉ được biết khi runtime thực thi.

## 8. Quy trình chọn cách parse dữ liệu số trong dự án

1. **Xác định loại dữ liệu.** Đây là giá trị để tính toán (số lượng, dung lượng, tiền) hay chỉ là mã định danh? Với mã định danh có số `0` đầu, ưu tiên `String`.
2. **Viết rõ hợp đồng đầu vào.** Cơ số nào (thường là 10), cho phép số âm hay không, tiền tố hay không, dấu nhóm hay không, có khoảng trắng hay không, có giới hạn lớn nhỏ nào?
3. **Chọn API phù hợp.** `Integer/Long.parseXxx` cho số nguyên hữu hạn; `BigInteger` khi thực sự cần số lớn; `BigDecimal(String)` cho thập phân cần tính chính xác; chỉ dùng `decode` khi đã chủ ý chấp nhận quy tắc tiền tố của nó.
4. **Xác thực và chuẩn hóa theo hợp đồng, rồi parse.** Chỉ bỏ tiền tố `0b`, dấu `_` hay khoảng trắng khi hợp đồng cho phép, và xác thực chúng xuất hiện ở vị trí hợp lệ trước khi bỏ.
5. **Xử lý lỗi và miền giá trị.** Bắt `NumberFormatException` tại biên đầu vào, chỉ ra trường nào không hợp lệ, kiểm tra giới hạn nghiệp vụ; không tự chuyển lỗi thành giá trị `0`.
6. **Phân tách parse, tính toán và format hiển thị.** Dấu phân cách theo locale, cách thêm `0x`/`0b`, và số `0` đầu thuộc tầng biểu diễn. Chúng không tự gắn với kiểu `int`/`long` trong bộ nhớ.

### Những lỗi hiểu sai phổ biến

- **“Java chấp nhận `1_000` nên `parseInt("1_000")` cũng chấp nhận.”** Sai: compiler và parser chuỗi có ngữ pháp riêng.
- **“Truyền radix 2 làm `parseInt("0b1010", 2)` tự hiểu `0b`.”** Sai: cần tách tiền tố theo hợp đồng trước khi parse.
- **“`Integer.decode` là cách parse integer an toàn hơn cho mọi input.”** Sai: có cách hiểu bát phân không mong muốn với chuỗi bắt đầu bằng `0`.
- **“Chỉ cần xóa mọi dấu `_` trong dữ liệu là tương đương cú pháp literal Java.”** Sai: có thể vô tình chấp nhận text sai định dạng.
- **“Chuỗi được đặt trong source Java nên compiler đã kiểm tra đó là số.”** Sai: compiler chỉ kiểm tra nó là **String literal hợp lệ**.
- **“Giá trị in ra phải giữ nguyên tiền tố và dấu nhóm số trong source.”** Sai: giá trị và cách định dạng chữ số là hai thứ khác nhau.
- **“Dùng `double` để parse tiền là luôn chính xác.”** Sai: cân nhắc `BigDecimal(String)` và quy tắc scale/rounding.

## 9. Tự kiểm tra

**Câu 1.** `int a = 0b1111;` và `Integer.parseInt("1111", 2)` có cùng giá trị không? — **Có, đều là 15**, nhưng được kiểm tra ở hai thời điểm khác nhau.

**Câu 2.** Có thể nhận dữ liệu `"1_000"` bằng cách `Integer.parseInt` trực tiếp không? — **Không**. Nếu hợp đồng cho phép dấu phân nhóm `_`, xác thực cách đặt dấu trước rồi chuẩn hóa.

**Câu 3.** Vì sao `Integer.parseInt("010")` là 10 còn `Integer.decode("010")` là 8? — Vì `parseInt` mặc định dùng **cơ số 10**, còn `decode` coi tiền tố `0` là **bát phân**.

**Câu 4.** Dữ liệu CSV có cột `postalCode="00123"`; có nên parse thành `int`? — Nếu là mã định danh, **không**; giữ `String` để bảo toàn số `0` đầu.

**Câu 5.** Với giá tiền từ API dạng `"1000.25"` cần độ chính xác thập phân, nên dùng gì? — Một lựa chọn phù hợp là `new BigDecimal("1000.25")` kết hợp xác thực và quy tắc làm tròn theo nghiệp vụ.

**Câu 6.** `int n = 0b_1010;` và `Integer.parseInt("0b1010", 2)` sai ở cùng giai đoạn? — **Không**. Dòng thứ nhất sai **khi biên dịch**, dòng thứ hai ném exception **khi chạy**.

## Tài liệu chuẩn để tra cứu

- [Java Language Specification 17, §3.10 — Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10): ngữ pháp literal trong mã nguồn, các cơ số và quy tắc dấu gạch dưới.
- [Java SE 17 — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): hợp đồng của `parseInt`, `decode` và các phương thức chuyển đổi chuỗi/số.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): cách xây dựng giá trị thập phân từ `String` và quy tắc số thập phân.

**Ghi nhớ:** `0b1010` và `1_000` là **cú pháp của giá trị trong mã Java**; `"0b1010"` và `"1_000"` là **dữ liệu String**. Khi dữ liệu đến từ bên ngoài, hãy xác định hợp đồng đầu vào, chọn parser và kiểm tra miền giá trị thay vì coi chuỗi như một literal được trình biên dịch xử lý.