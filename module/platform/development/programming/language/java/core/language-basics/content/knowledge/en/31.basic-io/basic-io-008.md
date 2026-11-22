# Kiểm tra đầu vào và chuyển chuỗi thành số — Java 17+

## 1. Vì sao cần kiểm tra trước và sau khi chuyển kiểu?

Dữ liệu mà chương trình nhận từ bàn phím, file hoặc dòng lệnh ban đầu thường là **chuỗi**. Ngay cả khi người dùng gõ `25`, giá trị đọc qua `BufferedReader.readLine()` hay `Scanner.nextLine()` vẫn có kiểu `String`. Muốn cộng, nhân, so sánh giới hạn, ta cần **chuyển chuỗi thành kiểu số** và **xác thực dữ liệu**.

Ba bước không được nhầm với nhau:

1. **Đọc dữ liệu:** lấy chuỗi người dùng nhập, ví dụ `"12"`.
2. **Chuyển kiểu (parse):** dùng `Integer.parseInt("12")` để nhận số nguyên `12`; bước này có thể thất bại nếu chuỗi không có định dạng hợp lệ hoặc vượt giới hạn kiểu.
3. **Kiểm tra ràng buộc (validation):** xác nhận giá trị thuộc miền nghiệp vụ, ví dụ số lượng `1..100`. Chuyển được `"0"` thành số `0` không có nghĩa số lượng 0 được phép.

~~~text
Chuỗi đầu vào
    |
    v
Kiểm tra thiếu/rỗng, chuẩn hóa hợp lệ
    |
    v
Chuyển thành số (parse)
    |             \
    |              \ lỗi định dạng / vượt phạm vi kiểu
    v               v
Kiểm tra miền       Thông báo lỗi phù hợp
nghiệp vụ
    |             \
    v              \ sai miền
Dùng số hợp lệ       Thông báo lỗi phù hợp
~~~

Mục tiêu là **không để dữ liệu xấu đi sâu vào phép tính**, đồng thời đưa ra thông báo cụ thể để người dùng sửa đầu vào.

## 2. Đọc một dòng từ stdin

Với Java 17, có thể dùng `BufferedReader` để nhận nguyên văn một dòng:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String line = reader.readLine();
~~~

- `System.in` là luồng input chuẩn (stdin).
- `InputStreamReader` chuyển byte thành ký tự; chỉ định `StandardCharsets.UTF_8` giúp thống nhất mã hóa.
- `BufferedReader.readLine()` đọc một dòng, bỏ ký tự kết thúc dòng và trả về `String`.
- Nếu **hết dữ liệu** trước khi đọc được dòng, `readLine()` trả về **`null`**.
- Thao tác I/O có thể ném checked `IOException`, nên method phải catch hoặc declare `throws IOException`.

Khi người dùng **chỉ nhấn Enter**, `readLine()` trả `""` (chuỗi rỗng), **khác** với `null` lúc EOF. Đầu vào chỉ chứa khoảng trắng như `"   "` lại là một chuỗi không rỗng về độ dài nhưng có thể bị xem là “không có nội dung” sau khi chuẩn hóa.

~~~java
if (line == null) {
    System.out.println("Missing line (EOF)");
} else if (line.isBlank()) {
    System.out.println("Empty or whitespace-only line");
}
~~~

Đây là mã minh họa đặt sau khi đã đọc `line`; chương trình chạy độc lập nằm ở mục 9.

## 3. Chuẩn hóa chuỗi trước khi parse

`String.strip()` (Java 11+) loại bỏ các ký tự khoảng trắng ở hai đầu theo quy tắc Unicode mà API hỗ trợ. Nếu hợp đồng cho phép khoảng trắng đầu/cuối:

~~~java
String raw = " 42 ";
String normalized = raw.strip();
int number = Integer.parseInt(normalized);
System.out.println(number);
~~~

**Exact stdout:**

~~~text
42
~~~

Phải kiểm tra `null` trước khi gọi `strip()`. Một chuỗi rỗng `""` hoặc chỉ có khoảng trắng sẽ không chuyển thành số bằng `Integer.parseInt`; nên thông báo “bắt buộc nhập” trước để người dùng hiểu, thay vì đưa ra một thông báo kỹ thuật khó hiểu.

**Không tùy tiện chỉnh sửa mọi chuỗi:** ví dụ yêu cầu tài chính hoặc mã định danh có thể quy định rất rõ có được bỏ khoảng trắng hay chấp nhận dấu cộng đầu chuỗi không. Việc chuẩn hóa phải tuân theo **hợp đồng đầu vào**.

## 4. Chuyển chuỗi thành `int` và `long`

Các API thường dùng:

~~~java
int age = Integer.parseInt("21");
long population = Long.parseLong("9000000000");

System.out.println(age);
System.out.println(population);
~~~

**Exact stdout:**

~~~text
21
9000000000
~~~

`Integer.parseInt(String)` nhận chuỗi biểu diễn số nguyên trong phạm vi **`-2147483648..2147483647`**; `Long.parseLong` nhận số nguyên kiểu `long` với phạm vi lớn hơn. Cả hai có thể ném **unchecked `NumberFormatException`** khi chuỗi không biểu diễn được số đúng kiểu.

Ví dụ:

| Chuỗi truyền vào `Integer.parseInt` | Kết quả |
|---|---|
| `"15"` | `15` |
| `"-8"` | `-8` |
| `"+9"` | `9` |
| `"0012"` | `12` |
| `"3.5"` | `NumberFormatException` |
| `"ten"` | `NumberFormatException` |
| `"2147483648"` | `NumberFormatException` do vượt giới hạn `int` |
| `" 12 "` | Không parse trực tiếp; cần `strip()` nếu hợp đồng cho phép |

Nếu cần **chỉ chấp nhận chữ số ASCII**, dấu hoặc định dạng đặc biệt phải được quy định và kiểm tra thêm. Chuyển số tự động không thay thế bước kiểm tra format của hệ thống.

Mẫu xử lý ngoại lệ:

~~~java
try {
    int quantity = Integer.parseInt(text.strip());
    System.out.println("quantity=" + quantity);
} catch (NumberFormatException ex) {
    System.out.println("quantity must be an integer");
}
~~~

Đoạn này giả sử `text` khác `null`; ví dụ hoàn chỉnh sẽ xử lý EOF/blank trước khi parse.

## 5. Chuyển số thực: `double` và `BigDecimal`

Chuyển sang số thực dấu phẩy động:

~~~java
double rate = Double.parseDouble("2.5");
System.out.println(rate);
~~~

**Exact stdout:**

~~~text
2.5
~~~

`Double.parseDouble` có thể hiểu dạng khoa học như `"1e3"`, đồng thời chấp nhận các giá trị đặc biệt như `"NaN"` hoặc `"Infinity"`. Nếu hợp đồng chỉ chấp nhận số thực **hữu hạn**, nên kiểm tra thêm:

~~~java
double value = Double.parseDouble(text.strip());
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("value must be finite");
}
~~~

Cũng cần kiểm tra miền cho phép, ví dụ `0.0 <= value && value <= 1.0`.

### Khi cần số thập phân có ý nghĩa chính xác

Đối với **giá tiền, tổng tiền hoặc đơn giá** cần biểu diễn thập phân nhất quán, `BigDecimal` thường phù hợp hơn `double`:

~~~java
import java.math.BigDecimal;

BigDecimal price = new BigDecimal("12.50");
BigDecimal total = price.multiply(BigDecimal.valueOf(3));
System.out.println(total.toPlainString());
~~~

**Exact stdout:**

~~~text
37.50
~~~

Tránh `new BigDecimal(0.1)` khi muốn biểu diễn đúng giá trị thập phân `0.1` vì `double` không lưu chính xác số đó theo hệ nhị phân. Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` tùy mục đích.

**Quan trọng:** `BigDecimal` xử lý chính xác số thập phân **đã parse**, nhưng không tự xác nhận “giá hợp lệ”. Vẫn cần giới hạn miền, số chữ số thập phân, đơn vị và luật làm tròn. Chương trình mẫu chỉ cho giá có tối đa **hai chữ số sau dấu chấm**, không âm và không vượt ngưỡng.

## 6. Định dạng số và dấu phân cách

Người dùng có thể nhập:

~~~text
12.50
12,50
1 000
1,000
1e3
~~~

Các chuỗi này **không tương đương một cách tự động**. Ví dụ `new BigDecimal("12,50")` không parse trực tiếp được. Trong ví dụ mục 9, giá có hợp đồng cố định:

- Chỉ dùng **chữ số ASCII `0..9`** và **dấu chấm `.`** cho phần thập phân.
- Cho phép số nguyên như `"12"` hoặc số có 1–2 chữ số thập phân như `"12.5"` và `"12.50"`.
- Không chấp nhận dấu phẩy, khoảng trắng ở giữa, ký hiệu tiền tệ, số mũ hoặc số âm.
- Khoảng trắng **hai đầu** được bỏ bằng `strip()`.
- Sau khi parse phải lớn hơn `0` và không vượt `1_000_000`.

Biểu thức kiểm tra định dạng Java:

~~~java
boolean validFormat = normalized.matches("[0-9]+(\\.[0-9]{1,2})?");
~~~

Trong Java string literal, `\\.` đại diện cho ký tự dấu chấm trong regex; dấu chấm được escape để không có nghĩa “bất kỳ ký tự nào”. Dùng một quy tắc format thống nhất giúp mã không phải đoán `12,50` là mười hai phẩy năm hay một danh sách hai giá trị.

Nếu ứng dụng hỗ trợ nhiều locale, hãy chọn một parser theo `Locale` xác định (ví dụ `NumberFormat`/`DecimalFormat`) với hợp đồng rõ và bảo đảm đã **đọc hết chuỗi hợp lệ**. Không giả định cách nhập dấu phẩy/thập phân giống nhau trên mọi hệ điều hành.

## 7. Phân biệt lỗi cú pháp, vượt kiểu và sai miền nghiệp vụ

Ba lỗi sau cần xử lý khác nhau:

| Nhóm lỗi | Ví dụ | Cách ứng xử |
|---|---|---|
| Thiếu dữ liệu | EOF trước khi có số lượng; chuỗi rỗng | Thông báo trường bắt buộc |
| Không chuyển được thành kiểu số | `"abc"`, `"2.5"` cho `int`, số quá lớn cho `int` | Bắt `NumberFormatException` hoặc kiểm tra cú pháp trước |
| Số hợp lệ về cú pháp nhưng sai miền | `0` cho số lượng phải `1..100`; giá `0.00` | Ném hoặc trả lỗi validation có thông điệp riêng |

Đừng dùng `assert quantity > 0` để kiểm tra đầu vào bắt buộc: câu lệnh `assert` có thể bị vô hiệu khi chạy JVM. Dùng điều kiện `if` chạy bình thường.

~~~java
static int validateQuantity(String input) {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("quantity is required");
    }

    final int quantity;
    try {
        quantity = Integer.parseInt(input.strip());
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "quantity must be an integer", ex);
    }

    if (quantity < 1 || quantity > 100) {
        throw new IllegalArgumentException("quantity must be 1..100");
    }
    return quantity;
}
~~~

Với `"abc"`, lỗi đến từ parse; với `"0"`, parse thành công nhưng validation miền thất bại. Khi phát hiện sai dữ liệu, nên **ngừng bước tính toán hiện tại**, thay vì tiếp tục dùng giá trị giả định hoặc “sửa” dữ liệu bí mật.

## 8. Chọn cách đọc input nhất quán

Khi bài toán cần xác thực **mỗi trường trên một dòng**, `Scanner.nextLine()` kết hợp `Integer.parseInt` hoặc `BigDecimal(String)` giúp tách ba trách nhiệm: đọc văn bản, chuyển kiểu và kiểm tra miền. Với nguồn có thể kết thúc sớm, hãy kiểm tra `hasNextLine()` trước khi đọc.

`nextInt()` đọc theo token, nên sau đó gọi `nextLine()` có thể nhận phần dư dòng số; nó cũng dùng cú pháp/locale của `Scanner` và có thể ném `InputMismatchException` thay vì `NumberFormatException` của `Integer.parseInt`. Vì chương này đang xây dựng validator chặt chẽ, ví dụ hoàn chỉnh chọn `BufferedReader.readLine()` và xử lý EOF rõ ràng.

## 9. Chương trình Java 17+ hoàn chỉnh: nhập số lượng và đơn giá

Ví dụ nhận **hai dòng từ stdin**:

1. Số lượng nguyên, từ **1 tới 100**.
2. Đơn giá thập phân, từ **lớn hơn 0 tới 1_000_000**, dùng dấu `.`, tối đa 2 chữ số thập phân.

Chương trình tính tổng `quantity × unitPrice` bằng `BigDecimal`, chuẩn hóa hiển thị đúng hai chữ số thập phân, từ chối input thiếu/sai và trả mã thoát **2** khi không hợp lệ.

Lưu file **`InputNumberValidationDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;

public final class InputNumberValidationDemo {
    private InputNumberValidationDemo() {}

    static int parseQuantity(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("quantity is required");
        }

        final int value;
        try {
            value = Integer.parseInt(raw.strip());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "quantity must be an integer", ex);
        }

        if (value < 1 || value > 100) {
            throw new IllegalArgumentException("quantity must be 1..100");
        }
        return value;
    }

    static BigDecimal parsePrice(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("price is required");
        }

        String normalized = raw.strip();
        if (!normalized.matches("[0-9]+(\\.[0-9]{1,2})?")) {
            throw new IllegalArgumentException(
                    "price must use digits and optional dot with 1-2 decimals");
        }

        final BigDecimal price;
        try {
            price = new BigDecimal(normalized);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "price must be a decimal number", ex);
        }

        if (price.compareTo(BigDecimal.ZERO) <= 0
                || price.compareTo(new BigDecimal("1000000")) > 0) {
            throw new IllegalArgumentException(
                    "price must be > 0 and <= 1000000");
        }

        return price.setScale(2, RoundingMode.UNNECESSARY);
    }

    static int run(BufferedReader reader) throws IOException {
        System.out.println("quantity?");
        String quantityLine = reader.readLine();
        if (quantityLine == null) {
            System.out.println("error: quantity is missing");
            return 2;
        }

        final int quantity;
        try {
            quantity = parseQuantity(quantityLine);
        } catch (IllegalArgumentException ex) {
            System.out.println("error: " + ex.getMessage());
            return 2;
        }

        System.out.println("price?");
        String priceLine = reader.readLine();
        if (priceLine == null) {
            System.out.println("error: price is missing");
            return 2;
        }

        final BigDecimal unitPrice;
        try {
            unitPrice = parsePrice(priceLine);
        } catch (IllegalArgumentException ex) {
            System.out.println("error: " + ex.getMessage());
            return 2;
        }

        BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(quantity));
        System.out.println("quantity=" + quantity);
        System.out.println("unitPrice=" + unitPrice.toPlainString());
        System.out.println("total=" + total.toPlainString());
        System.out.println("status=OK");
        return 0;
    }

    public static void main(String[] args) {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8));

        int status;
        try {
            status = run(reader);
        } catch (IOException ex) {
            System.out.println("error: input unavailable");
            status = 2;
        }

        if (status != 0) {
            System.exit(status);
        }
    }
}
~~~

**Giải thích kỹ thuật:**

- Hai câu lệnh `readLine()` đọc chuỗi; chương trình kiểm tra EOF riêng để phân biệt với dòng trống.
- `parseQuantity` bắt `NumberFormatException` từ `Integer.parseInt` và chuyển thành thông điệp phù hợp; đồng thời kiểm tra miền `1..100`.
- `parsePrice` kiểm tra format trước, tạo `BigDecimal` từ chuỗi, so giá bằng `compareTo` và dùng `setScale(2, RoundingMode.UNNECESSARY)`. Vì input chỉ có tối đa hai chữ số thập phân nên bước đặt scale không phải làm tròn số; nó chuẩn hóa đầu ra, ví dụ `12.5` thành `12.50`.
- Nhánh lỗi kết thúc `run` với mã `2`, không tính tổng khi đầu vào không hợp lệ.
- `System.exit(2)` thuộc **ranh giới ứng dụng**. Không nên gọi `System.exit` trong hàm tiện ích parsing; thư viện nên cho caller quyết định lỗi nào được xử lý.
- Các thông báo của ví dụ in ra stdout để so khớp dễ dàng. CLI production thường in lỗi qua `System.err`.

### Biên dịch

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 InputNumberValidationDemo.java
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\InputNumberValidationDemo.java
~~~

Không cần Maven/Gradle, thư viện ngoài hoặc preview features. Chạy trong thư mục chứa file `.class` được biên dịch.

### Trường hợp 1 — dữ liệu hợp lệ

**Bash:**

~~~bash
printf '3\n12.50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("3", "12.50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
quantity=3
unitPrice=12.50
total=37.50
status=OK
~~~

Trường hợp này trả **exit status 0**.

### Trường hợp 2 — số lượng không phải số nguyên

**Bash:**

~~~bash
printf 'abc\n12.50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("abc", "12.50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
error: quantity must be an integer
~~~

Chương trình không đọc tiếp đơn giá sau khi từ chối số lượng; **exit status 2**.

### Trường hợp 3 — chuyển được số nhưng ngoài miền

**Bash:**

~~~bash
printf '0\n12.50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("0", "12.50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
error: quantity must be 1..100
~~~

`"0"` parse thành số nguyên thành công, nhưng không thỏa miền nghiệp vụ `1..100`. **Exit status 2**.

### Trường hợp 4 — dùng dấu phẩy sai định dạng

**Bash:**

~~~bash
printf '2\n12,50\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("2", "12,50") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
error: price must use digits and optional dot with 1-2 decimals
~~~

Format giá được quy định sử dụng `.`, không chấp nhận `,`. **Exit status 2**.

### Trường hợp 5 — giá bằng 0

**Bash:**

~~~bash
printf '2\n0.00\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
@("2", "0.00") | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
error: price must be > 0 and <= 1000000
~~~

`"0.00"` đúng format và parse được thành `BigDecimal`, nhưng sai quy tắc **giá phải lớn hơn 0**; **exit status 2**.

### Trường hợp 6 — hết dữ liệu trước khi nhập giá

**Bash:**

~~~bash
printf '2\n' | java -cp . InputNumberValidationDemo
~~~

**PowerShell:**

~~~powershell
"2" | java -cp . InputNumberValidationDemo
~~~

**Exact expected stdout:**

~~~text
quantity?
price?
error: price is missing
~~~

Hết input khiến `readLine()` thứ hai trả `null`; chương trình thông báo thiếu trường, không tự suy ra `0`. **Exit status 2**.

## 10. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| Tưởng `readLine()` trả số đã chuyển | API trả `String` hoặc `null` | Gọi parse sau khi kiểm tra đầu vào |
| Đọc `null.strip()` khi EOF | `NullPointerException` | Kiểm tra `null` trước |
| Xử lý chuỗi rỗng như số 0 | Dễ tạo dữ liệu giả | Phân biệt thiếu dữ liệu với số 0 thực sự |
| Parse `"abc"` không bắt lỗi | `NumberFormatException` | Catch đúng loại hoặc thông báo lỗi |
| Parse `"2147483648"` bằng `int` rồi coi là số hợp lệ | Ngoài phạm vi `int` | Dùng kiểu phù hợp và kiểm tra miền |
| `int n = Integer.parseInt(s);` rồi không kiểm tra `n` | `n` có thể là 0, âm hoặc quá giới hạn nghiệp vụ | Validate miền sau parse |
| Dùng `double` để cộng tiền và kỳ vọng chính xác thập phân tuyệt đối | Dấu phẩy động có thể làm tròn nhị phân | `BigDecimal` và quy tắc scale/rounding rõ |
| Tưởng `Double.parseDouble("NaN")` là số hữu hạn hợp lệ | NaN là giá trị đặc biệt | `Double.isFinite` nếu hợp đồng cần |
| Tưởng `12,50` luôn parse giống `12.50` | Parser/locale khác nhau | Chọn format rõ và kiểm tra |
| Dùng `==` để so chuỗi nhập | `==` so identity | Dùng `equals` hoặc parse số |
| Trộn `Scanner.nextInt()` với `nextLine()` không xử lý phần cuối dòng | Có thể đọc chuỗi rỗng ngoài ý muốn | Dùng `nextLine()` + parse hoặc tiêu thụ hết dòng đúng cách |
| Dùng `assert` để validate input bắt buộc | Assertion có thể bị tắt | Dùng `if`/throw/validation luôn chạy |
| Nuốt `NumberFormatException` rồi tự động dùng 0 | Che giấu dữ liệu sai | Thông báo hoặc yêu cầu nhập lại theo hợp đồng |
| Nhầm lỗi cú pháp với lỗi miền | Hai vấn đề cần xử lý riêng | Parse trước, validate sau |

## 11. Bài tập và đáp án

**A.** Với `String s = " 18 ";`, cách chuyển thành `int` nếu cho phép khoảng trắng hai đầu?

**Đáp án:**

~~~java
int n = Integer.parseInt(s.strip()); // 18
~~~

**B.** `Integer.parseInt("2.5")` trả gì?

**Đáp án:** ném `NumberFormatException` vì `2.5` không phải biểu diễn một số nguyên `int` hợp lệ.

**C.** Nếu quantity = `0` nhưng `Integer.parseInt("0")` thành công thì dữ liệu hợp lệ chưa?

**Đáp án:** **Chưa**. Hợp đồng ví dụ yêu cầu `1..100`, nên số lượng 0 phải bị từ chối bởi validation.

**D.** Nếu muốn dữ liệu thập phân chính xác để tính giá tiền, dùng `new BigDecimal("12.50")` hay `new BigDecimal(12.50)`?

**Đáp án:** ưu tiên `new BigDecimal("12.50")` khi đầu vào là chuỗi số thập phân đã được kiểm tra; tránh tạo từ `double` vì độ chính xác nhị phân.

**E.** `BufferedReader.readLine()` trả `null` khi nào?

**Đáp án:** khi đạt EOF trước khi đọc một dòng, khác với `""` khi đọc dòng rỗng.

**F.** Vì sao `Double.parseDouble("NaN")` chưa đủ để xác thực một phép đo bắt buộc hữu hạn?

**Đáp án:** `NaN` là giá trị `double` đặc biệt; kiểm tra `Double.isFinite` và miền giá trị thích hợp.

**G.** `12,50` bị ví dụ từ chối do lý do nào?

**Đáp án:** lỗi **định dạng**: hợp đồng cho đơn giá yêu cầu chữ số ASCII và dấu thập phân `.`, không phải dấu phẩy.

**H.** Với `2` và `12.50`, tổng tiền theo ví dụ là bao nhiêu?

**Đáp án:** `25.00` vì `2 × 12.50 = 25.00`.

## 12. Checklist và kết luận

- [ ] Biết input từ `readLine()`/`nextLine()` là chuỗi cần chuyển đổi.
- [ ] Phân biệt EOF (`null`), chuỗi rỗng và chuỗi toàn khoảng trắng.
- [ ] Kiểm tra `null` trước khi chuẩn hóa `strip()`.
- [ ] Sử dụng `Integer.parseInt`, `Long.parseLong` cho số nguyên.
- [ ] Hiểu `NumberFormatException` và giới hạn phạm vi kiểu số.
- [ ] Biết `Double.parseDouble` và kiểm tra giá trị hữu hạn khi cần.
- [ ] Biết dùng `BigDecimal` từ `String` để xử lý thập phân chính xác.
- [ ] Chọn quy tắc dấu thập phân, khoảng trắng, số chữ số theo hợp đồng.
- [ ] Kiểm tra miền nghiệp vụ sau bước parse.
- [ ] Không dùng `assert` hoặc giá trị mặc định tùy tiện để thay validation.
- [ ] Hiểu bẫy trộn `Scanner.nextInt()` và `nextLine()`.
- [ ] Đọc và hiểu thông báo lỗi, exit status trong CLI.
- [ ] Chạy `InputNumberValidationDemo.java` trên JDK 17+ cho cả trường hợp hợp lệ và sai, đối chiếu stdout.

**Kết luận:** **Đọc chuỗi, chuyển thành số và kiểm tra dữ liệu hợp lệ** là ba bước khác nhau nhưng liên tiếp. Chương trình Java vững chắc phải xử lý được input thiếu, sai cú pháp hoặc ngoài phạm vi, đồng thời dùng kiểu số phù hợp với nghiệp vụ. Chỉ tính toán sau khi tất cả các bước kiểm tra bắt buộc đều thành công.