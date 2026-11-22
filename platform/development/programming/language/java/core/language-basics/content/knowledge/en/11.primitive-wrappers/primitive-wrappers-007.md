# NumberFormatException khi chuỗi không hợp lệ trong Java

> **Java core — language-basics / Lớp bao nguyên thủy**  
> **Môi trường:** JDK 17+; không cần thư viện ngoài.  
> **Mục tiêu:** Xác định tại sao chuyển chuỗi sang số có thể ném `NumberFormatException`, phân biệt sai định dạng với vượt miền, áp dụng đúng `Integer.parseInt`/`Long.parseLong`/`Double.parseDouble` và xử lý giá trị nhập không hợp lệ tại ranh giới chương trình.

## 1. Một chuỗi không tự trở thành số

`String` chứa văn bản, còn các kiểu `int`, `long` và `double` lưu giá trị số. Muốn phân tích văn bản thành số, Java cung cấp các phương thức chuyển đổi của lớp bao (*wrapper*):

~~~java
int quantity = Integer.parseInt("42");  // 42
long count = Long.parseLong("3000000000"); // 3000000000L
double rate = Double.parseDouble("3.14"); // 3.14
~~~

Nếu không phân tích được chuỗi theo cú pháp hoặc miền giá trị mà phương thức yêu cầu, Java ném **`java.lang.NumberFormatException`** (*NFE*). Đây là một lớp con của `IllegalArgumentException`.

~~~java
// int value = Integer.parseInt("12x"); // Nếu chạy: NumberFormatException.
~~~

**Điểm chính:** `"12x"` vẫn là một `String` hợp lệ. Lỗi xảy ra khi **cố diễn giải nội dung đó thành số nguyên**, không phải khi tạo chuỗi.

## 2. Các nhóm đầu vào gây `NumberFormatException`

| Dữ liệu và phép chuyển | Kết quả | Nguyên nhân |
| --- | --- | --- |
| `Integer.parseInt("42")` | `42` | Chuỗi thập phân hợp lệ |
| `Integer.parseInt("-7")` | `-7` | Dấu trừ hợp lệ |
| `Integer.parseInt("+8")` | `8` | Dấu cộng đầu hợp lệ |
| `Integer.parseInt("007")` | `7` | Dẫn đầu bằng 0 vẫn là thập phân mặc định |
| `Integer.parseInt(" 42 ")` | NFE | Không tự bỏ khoảng trắng |
| `Integer.parseInt("")` | NFE | Chuỗi rỗng |
| `Integer.parseInt("12x")` | NFE | Có ký tự không hợp lệ ở hệ thập phân |
| `Integer.parseInt("3.14")` | NFE | Số thập phân có phần lẻ không phải cú pháp `int` |
| `Integer.parseInt("1_000")` | NFE | Dấu gạch dưới hợp lệ trong **literal Java**, không phải chuỗi nhập cho `parseInt` |
| `Integer.parseInt("2147483648")` | NFE | Vượt `Integer.MAX_VALUE` là 2147483647 |
| `Integer.parseInt(null)` | NFE | Không có chuỗi để phân tích |
| `Byte.parseByte("128")` | NFE | Giá trị 128 vượt giới hạn `byte` là 127 |

`Integer.parseInt` mặc định là **hệ cơ số 10**. Nó không hiểu cú pháp literal `0xFF` hoặc cách viết dấu gạch dưới trong mã nguồn; đừng nhầm định dạng của một **Java source literal** với định dạng của **chuỗi nhập ở runtime**.

Phương thức parse không tự xử lý toàn bộ ràng buộc nghiệp vụ: `"-1"` có thể phân tích thành `int` thành công, nhưng vẫn có thể **không hợp lệ** nếu đây là số lượng sản phẩm hoặc cổng mạng phải dương.

## 3. Radix: chuỗi hợp lệ phụ thuộc cơ số

Tham số `radix` quy định cơ số cần dùng cho `Integer.parseInt(String, int)`:

~~~java
int hex = Integer.parseInt("FF", 16);   // 255
int binary = Integer.parseInt("101", 2); // 5
int decimal = Integer.parseInt("101", 10); // 101

// Integer.parseInt("FF");     // NFE: F không phải chữ số thập phân.
// Integer.parseInt("102", 2);  // NFE: 2 không thuộc cơ số 2.
~~~

`Integer.parseInt("FF", 16)` yêu cầu chỉ định radix 16; không phải cast kiểu số. Radix hợp lệ cho `Integer.parseInt` nằm từ `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36); radix không hợp lệ cũng dẫn đến `NumberFormatException`.

Nếu đầu vào có tiền tố `0x`, API `Integer.decode(...)` có quy tắc riêng để hiểu tiền tố. Không tự động thay thế `parseInt` bằng `decode` nếu định dạng đầu vào phải được kiểm soát chặt.

## 4. Phân biệt cú pháp, miền giá trị và loại số

Các hàm parse có định dạng/miền khác nhau:

| API | Ví dụ hợp lệ | Điểm cần lưu ý |
| --- | --- | --- |
| `Byte.parseByte` | `"127"` | Vượt miền `byte` gây NFE |
| `Short.parseShort` | `"-30000"` | Vượt miền `short` gây NFE |
| `Integer.parseInt` | `"2147483647"` | Số thập phân có phần lẻ không hợp lệ |
| `Long.parseLong` | `"2147483648"` | Lớn hơn `int` vẫn vừa `long` |
| `Double.parseDouble` | `"3.14"` hoặc `"1e3"` | Hỗ trợ biểu diễn số thực, số mũ và token đặc biệt |
| `Float.parseFloat` | `"2.5"` | Theo quy tắc parsing số thực, không giống `parseInt` |

**Quan trọng:** `Double.parseDouble("NaN")` trả giá trị **`Double.NaN`**, không ném NFE. Một chuỗi hợp lệ theo quy tắc `double` cũng **không nhất thiết là giá trị hữu hạn**: ví dụ đầu vào quá lớn có thể trở thành vô cực. Khi nghiệp vụ chỉ cho phép số thực hữu hạn, kiểm tra thêm `Double.isFinite(value)` sau khi parse.

Với lượng tiền cần chính xác tới chữ số thập phân, cân nhắc `BigDecimal` tạo từ chuỗi hợp lệ và quy tắc scale/rounding nghiệp vụ; không tùy tiện đưa tiền qua `double` rồi cho rằng tuyệt đối chính xác.

## 5. Chương trình Java 17+ runnable

Tạo file **NumberFormatDemo.java**:

~~~java
public final class NumberFormatDemo {
    private static void checkInt(String label, String text) {
        try {
            System.out.println(label + "=" + Integer.parseInt(text));
        } catch (NumberFormatException ex) {
            System.out.println(label + "=NumberFormatException");
        }
    }

    private static int parsePort(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("port required");
        }

        int port;
        try {
            port = Integer.parseInt(input.strip());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "port must be decimal integer", ex);
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port outside 1..65535");
        }
        return port;
    }

    private static void checkPort(String label, String input) {
        try {
            System.out.println(label + "=" + parsePort(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(label + "=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        checkInt("plain", "42");
        checkInt("negative", "-7");
        checkInt("leadingPlus", "+8");
        checkInt("leadingZero", "007");
        checkInt("spaces", " 42 ");
        checkInt("decimal", "3.14");
        checkInt("empty", "");
        checkInt("nonDigit", "12x");
        checkInt("overflow", "2147483648");
        checkInt("underscore", "1_000");
        checkInt("nullInput", null);

        System.out.println("hexFF=" + Integer.parseInt("FF", 16));
        try {
            Integer.parseInt("102", 2);
        } catch (NumberFormatException ex) {
            System.out.println("binaryInvalid=NumberFormatException");
        }

        System.out.println("longLarge=" + Long.parseLong("2147483648"));
        try {
            Byte.parseByte("128");
        } catch (NumberFormatException ex) {
            System.out.println("byteOverflow=NumberFormatException");
        }

        System.out.println("doubleDecimal=" + Double.parseDouble("3.14"));
        System.out.println("doubleNaN=" + Double.parseDouble("NaN"));
        try {
            Double.parseDouble("1.2.3");
        } catch (NumberFormatException ex) {
            System.out.println("doubleInvalid=NumberFormatException");
        }

        checkPort("validPort", "8080");
        checkPort("spacesPort", " 8080 ");
        checkPort("badPort", "abc");
        checkPort("tooLargePort", "65536");
        checkPort("missingPort", null);
    }
}
~~~

Mở terminal trong thư mục chứa file, biên dịch và chạy (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 NumberFormatDemo.java
java NumberFormatDemo
~~~

**Expected output chính xác:**

~~~text
plain=42
negative=-7
leadingPlus=8
leadingZero=7
spaces=NumberFormatException
decimal=NumberFormatException
empty=NumberFormatException
nonDigit=NumberFormatException
overflow=NumberFormatException
underscore=NumberFormatException
nullInput=NumberFormatException
hexFF=255
binaryInvalid=NumberFormatException
longLarge=2147483648
byteOverflow=NumberFormatException
doubleDecimal=3.14
doubleNaN=NaN
doubleInvalid=NumberFormatException
validPort=8080
spacesPort=8080
badPort=port must be decimal integer
tooLargePort=port outside 1..65535
missingPort=port required
~~~

Chương trình **không phụ thuộc vào văn bản lỗi mặc định của JDK**: ở những ví dụ sai format, nó chỉ in tên loại exception; ở `parsePort`, thông báo do code tự định nghĩa nên dễ kiểm thử.

## 6. Xử lý lỗi đúng tại ranh giới nhập liệu

Ở hàm `parsePort`, các bước có chủ đích:

1. **Kiểm tra dữ liệu thiếu:** `null` hoặc chuỗi trắng toàn bộ → `"port required"`. Tránh vô tình coi dữ liệu thiếu như số 0.
2. **Chuẩn hóa đầu vào khi được phép:** `strip()` loại bỏ khoảng trắng đầu/cuối, nhưng chỉ vì hợp đồng của ví dụ **cho phép** khoảng trắng. Nếu định dạng nghiêm ngặt không chấp nhận khoảng trắng, hãy bỏ bước này.
3. **Parse và bắt lỗi đúng nơi:** `Integer.parseInt` xử lý cú pháp số nguyên. `NumberFormatException` được chuyển thành một lỗi đầu vào có thông điệp nghiệp vụ, giữ nguyên `cause` để chẩn đoán.
4. **Kiểm tra miền nghiệp vụ sau khi parse:** số nguyên `65536` có cú pháp đúng và vừa `int`, nhưng không hợp lệ làm cổng mạng; `"-1"` tương tự.
5. **Không biến mọi lỗi thành số 0:** một chuỗi sai format thường cần được báo cho người dùng hoặc upstream, không phải âm thầm đưa vào phép tính.

`try/catch` ở đây bao quanh phần **phân tích dữ liệu không đáng tin cậy**, thay vì bắt một khối ứng dụng quá lớn hoặc bắt `Exception` chung rồi bỏ qua. API nội bộ với hợp đồng khác có thể để NFE đi ra cho caller xử lý, thay vì luôn chuyển thành `IllegalArgumentException` mới.

## 7. Vì sao không nên dựa vào `ex.getMessage()` để điều khiển logic?

`NumberFormatException` cho biết có sự cố phân tích số, nhưng **chi tiết text của thông điệp** không phải định dạng nghiệp vụ ổn định để parser hoặc UI dựa vào. Tránh viết:

~~~java
// Không nên:
// if (ex.getMessage().contains("For input string")) { ... }
~~~

Thay vào đó, bắt đúng **kiểu exception**, kiểm tra trường dữ liệu nguồn, rồi tự tạo một thông điệp rõ ràng như `"quantity must be a whole number"`. Có thể ghi log exception/cause theo chính sách hệ thống, nhưng không hiển thị chi tiết stack trace cho người dùng cuối.

**Không nhầm với lỗi khác:**

- `Integer.parseInt("12x")` → **`NumberFormatException`** do text không phân tích được.
- `int x = someIntegerWrapper;` khi wrapper là `null` → **`NullPointerException`** do unboxing, không phải lỗi cú pháp chuỗi.
- `Integer.valueOf(12)` tạo/nhận wrapper từ giá trị nguyên, không phải parser cho một chuỗi văn bản sai cú pháp.
- `Integer.valueOf("12x")` cũng có thể ném **`NumberFormatException`** vì phải phân tích chuỗi như số nguyên.

## 8. Bài tập tự luyện

**Bài 1:** Dự đoán kết quả của `Integer.parseInt("+15")`, `Integer.parseInt("015")`, `Integer.parseInt("15 ")`, `Integer.parseInt("15.0")` và giải thích vì sao chuỗi nguồn là `String` hợp lệ nhưng parser vẫn có thể từ chối.

**Bài 2:** So sánh `Integer.parseInt("2147483648")` với `Long.parseLong("2147483648")`. Điều gì thay đổi khi chọn wrapper khác?

**Bài 3:** Dùng `Integer.parseInt("101", 2)` và `Integer.parseInt("101", 10)`. Cùng một chuỗi vì sao có thể thành hai số khác nhau?

**Bài 4:** Viết hàm nhận số lượng sản phẩm dạng `String`. Từ chối null/trắng, parse số nguyên, sau đó từ chối lượng âm. Nêu lý do đây là hai lớp kiểm tra khác nhau.

**Bài 5:** Thử `Double.parseDouble("NaN")` và `Double.parseDouble("1e309")`. Viết điều kiện `Double.isFinite(result)` nếu ứng dụng yêu cầu số đo hữu hạn.

### Ghi nhớ

**`NumberFormatException` là dấu hiệu chuỗi không thể được diễn giải theo kiểu số, cơ số hoặc giới hạn đang yêu cầu.** Kiểm tra input thiếu và khoảng trắng theo hợp đồng; dùng đúng `parseInt`/`parseLong`/`parseDouble`; bắt NFE tại ranh giới dữ liệu không đáng tin cậy, rồi **kiểm tra tiếp điều kiện nghiệp vụ**. Đừng dựa vào text lỗi JDK và đừng âm thầm thay mọi đầu vào sai bằng 0.
