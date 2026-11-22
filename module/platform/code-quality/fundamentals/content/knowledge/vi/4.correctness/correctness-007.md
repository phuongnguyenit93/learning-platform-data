# Tính đúng đắn của dữ liệu số, chuỗi và thời gian

> **Chương:** Tính đúng đắn  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết những giả định dễ sai khi chương trình xử lý **số**, **chuỗi Unicode** và **ngày giờ**.
2. Chọn kiểu dữ liệu, cách chuyển đổi và phép so sánh phù hợp với ý nghĩa nghiệp vụ.
3. Phân biệt lỗi tính toán với lỗi biểu diễn, làm tròn, định dạng, múi giờ và quy tắc lịch.
4. Thiết kế hợp đồng dữ liệu rõ ràng ở ranh giới API, cơ sở dữ liệu và các dịch vụ.
5. Viết kiểm thử cho giá trị biên, dữ liệu không hợp lệ và các trường hợp thường gây lỗi âm thầm.

## 1. Đúng đắn nghĩa là gì khi xử lý dữ liệu?

Một chương trình có thể biên dịch, chạy và trả về kết quả mà vẫn **sai về nghiệp vụ**. Ví dụ:

- Tổng tiền đơn hàng hiển thị `0.30` nhưng điều kiện so sánh hai số thực lại cho kết quả sai.
- Tên hiển thị trông giống nhau nhưng được lưu bằng hai chuỗi Unicode khác nhau, nên hệ thống xem là hai giá trị khác nhau.
- Lịch hẹn được đặt lúc 09:00 theo giờ địa phương nhưng thực thi lúc 09:00 UTC.
- Giao dịch ghi ở cuối ngày bị loại khỏi báo cáo do dùng mốc kết thúc sai.

**Tính đúng đắn (correctness)** là việc hành vi thực tế đáp ứng đặc tả đã xác định, kể cả ở các tình huống biên, đầu vào bất thường và chuyển đổi qua nhiều lớp. Với dữ liệu, điểm quan trọng là phải định nghĩa đúng **ý nghĩa** của giá trị trước khi viết phép toán trên nó.

| Câu hỏi | Số | Chuỗi | Thời gian |
| --- | --- | --- | --- |
| Giá trị đại diện cho gì? | Số lượng, tiền, tỉ lệ hay phép đo? | Tên, mã định danh, mật khẩu hay văn bản hiển thị? | Thời điểm, giờ địa phương, ngày trên lịch hay khoảng thời gian? |
| Được biểu diễn ra sao? | `int`, `long`, `BigDecimal`, `double` | Unicode, UTF-8, kiểu `String` | `Instant`, `LocalDate`, `ZonedDateTime` |
| Quy tắc biên nào áp dụng? | Tràn số, làm tròn, giá trị âm, độ chính xác | `null`, chuỗi rỗng, khoảng trắng, chuẩn hóa, độ dài | Múi giờ, DST, ngày nhuận, đầu/cuối khoảng |
| Kiểm tra điều gì? | Kết quả và đơn vị đúng | So sánh, chuyển mã và nhận dạng đúng | Cùng thời điểm/cùng ngày theo vùng, chuyển lịch chính xác |

Một giải pháp đáng tin cậy cần xác định rõ **miền giá trị hợp lệ, đơn vị, cách biểu diễn, quy tắc chuyển đổi và hành vi khi dữ liệu không hợp lệ**. Nếu các quyết định đó bị ẩn trong nhiều hàm, chất lượng mã giảm vì người đọc khó biết kết quả nào mới là đúng.

## 2. Tính đúng đắn của dữ liệu số

### 2.1. Số nguyên: giới hạn miền giá trị và tràn số

Trong Java, `int` là số nguyên có dấu 32 bit, `long` là số nguyên có dấu 64 bit. Chọn kiểu số cần dựa trên **phạm vi của kết quả trung gian và kết quả cuối**, không chỉ giá trị đầu vào hiện tại.

~~~java
int count = Integer.MAX_VALUE;
int wrong = count + 1; // Tràn số, kết quả thành Integer.MIN_VALUE.

// Kiểm tra tràn thay vì âm thầm nhận giá trị sai:
int safe = Math.addExact(count, 1); // Ném ArithmeticException.
~~~

Tràn cũng có thể xảy ra **trước khi gán** cho biến có kiểu lớn hơn:

~~~java
int price = 1_500_000_000;
int quantity = 2;

long wrongTotal = price * quantity;       // Nhân kiểu int trước: đã tràn.
long correctTotal = (long) price * quantity; // Ép kiểu trước phép nhân.
long checkedTotal = Math.multiplyExact((long) price, quantity);
~~~

Trong phép cộng hoặc nhân có nguy cơ vượt cả `long`, cân nhắc `BigInteger` hoặc báo lỗi theo hợp đồng. Không tự ý “chặn” giá trị về `Integer.MAX_VALUE` nếu nghiệp vụ không định nghĩa hành vi đó.

**Các điểm cần hỏi:** số lượng âm có hợp lệ không; giá trị `0` là “không có” hay giá trị thật; giới hạn tối đa bao nhiêu; và khi vượt giới hạn sẽ từ chối, phân đoạn hay chuyển kiểu?

### 2.2. Số thực nhị phân không biểu diễn chính xác mọi phân số thập phân

`float` và `double` sử dụng biểu diễn dấu phẩy động nhị phân. Phần lớn các phân số thập phân như `0.1` không có biểu diễn hữu hạn chính xác ở hệ nhị phân.

~~~java
double x = 0.1 + 0.2;
System.out.println(x);         // Thường in 0.30000000000000004
System.out.println(x == 0.3);  // false
~~~

Không thể chữa vấn đề bằng cách định dạng `x` thành hai chữ số thập phân rồi dùng chuỗi đó để tính toán tiếp. Định dạng chỉ thay đổi cách hiển thị, không thay đổi giá trị lưu bên trong.

`double` vẫn phù hợp với nhiều phép đo, tính toán khoa học và thuật toán chấp nhận sai số, miễn là **mức sai số** được xác định và kiểm soát. Khi so sánh số thực đo lường có dung sai, cần lựa chọn cả sai số tuyệt đối và/hoặc tương đối theo miền dữ liệu:

~~~java
static boolean approximatelyEqual(
        double a, double b,
        double absoluteTolerance,
        double relativeTolerance
) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(absoluteTolerance)
            || !Double.isFinite(relativeTolerance)
            || absoluteTolerance < 0 || relativeTolerance < 0) {
        throw new IllegalArgumentException("Invalid numeric input");
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= absoluteTolerance
            || difference <= relativeTolerance * scale;
}
~~~

Đây chỉ là ví dụ về chính sách so sánh. Dung sai phải phù hợp với phép đo, không có hằng số `epsilon` dùng được cho mọi ứng dụng. Ngoài sai số, cần nhận diện `NaN`, `Infinity`, `-Infinity`, số rất lớn và phép chia cho `0.0` nếu các giá trị đó nằm ngoài miền hợp lệ.

### 2.3. Tiền tệ và số thập phân: `BigDecimal` và quy tắc làm tròn

Với tiền hoặc phép tính cần số thập phân chính xác theo quy tắc nghiệp vụ, thường dùng `BigDecimal` được khởi tạo từ **chuỗi thập phân** hoặc `BigDecimal.valueOf(...)` khi đã có số phù hợp.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal subtotal = unitPrice.multiply(quantity); // 59.70

BigDecimal rate = new BigDecimal("0.075");
BigDecimal tax = subtotal.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP);          // 4.48

BigDecimal total = subtotal.add(tax);               // 64.18
~~~

Lưu ý:

- `new BigDecimal(0.1)` nhận **giá trị `double` xấp xỉ 0.1**, không nhận số thập phân `0.1` chính xác. Ưu tiên `new BigDecimal("0.1")`.
- `BigDecimal` bất biến: `amount.setScale(...)` tạo giá trị mới, không sửa biến cũ.
- Với nghiệp vụ tiền tệ, **thời điểm làm tròn, số chữ số thập phân và chế độ làm tròn** là một phần của đặc tả. Tính thuế từng dòng rồi cộng có thể khác tính thuế trên tổng rồi làm tròn.
- Phép chia có kết quả thập phân vô hạn cần chỉ rõ `scale` và `RoundingMode` (hoặc `MathContext` thích hợp).

~~~java
BigDecimal ratio = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP); // 0.3333
~~~

**So sánh đúng ý nghĩa:** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false` vì `equals` xét cả giá trị và scale; `compareTo` trả về `0` vì hai giá trị bằng nhau về số học. Khi xem tiền là số lượng, dùng `compareTo` phù hợp; khi scale mang ý nghĩa hợp đồng, cần kiểm tra cả scale.

Không có một chế độ làm tròn được mặc định là “đúng” cho mọi hóa đơn. Hãy ghi rõ chính sách áp dụng, đơn vị tiền và trường hợp cần xử lý nhiều loại tiền tệ. Với tiền chỉ có đơn vị nhỏ nhất là số nguyên (ví dụ một hệ thống chỉ nhận VND nguyên), `long` có kiểm tra tràn cũng là một lựa chọn, miễn là toàn bộ hợp đồng nhất quán về đơn vị.

### 2.4. Đơn vị, chuyển đổi và tính hợp lệ

Nhiều kết quả sai đến từ **đúng phép toán nhưng sai đơn vị**:

~~~java
long durationMillis = 1_500L;
// Sai nếu phương thức kỳ vọng số giây:
Instant wrong = Instant.ofEpochSecond(durationMillis);
// Đúng với đơn vị đang có:
Instant correct = Instant.ofEpochMilli(durationMillis);
~~~

Các giá trị như `distance = 10`, `amount = 100`, `timeout = 30` rất dễ bị hiểu nhầm nếu không mang đơn vị trong tên, kiểu dữ liệu hoặc hợp đồng API. Nên đặt tên `timeoutSeconds`, `distanceMeters`, `amountMinorUnits` và dùng các kiểu chuyên biệt (`Duration`, `Money` tự định nghĩa) khi phù hợp.

Khi nhận số từ hệ thống bên ngoài, quyết định rõ cách xử lý chuỗi `"1,250"` hoặc `"1.250"` theo locale và quy tắc nhập liệu. **Không mặc định dấu phẩy luôn là dấu phân cách hàng nghìn hay dấu chấm luôn là thập phân**. Với giao thức máy đọc, một dạng chuẩn (ví dụ JSON number với quy tắc rõ ràng hoặc chuỗi decimal có định dạng cố định) thường giảm mơ hồ; giao diện người dùng có thể phân tích theo locale đã được xác định. Nếu dùng parser có khả năng chấp nhận chuỗi một phần, cần xác nhận **toàn bộ đầu vào** đã được tiêu thụ.

## 3. Tính đúng đắn của chuỗi

### 3.1. Chuỗi là dữ liệu có ý nghĩa, không chỉ một dãy ký tự nhìn thấy được

Java `String` lưu chuỗi các **UTF-16 code unit**. Một ký tự người dùng nhìn thấy có thể bao gồm nhiều code point, và một code point có thể cần hai code unit. Vì vậy:

- `String.length()` đếm số code unit UTF-16, không mặc định là số chữ cái người dùng thấy.
- `charAt(i)` trả một `char` (code unit), có thể chỉ là một nửa của một code point.
- `codePointCount(...)` đếm code point, nhưng vẫn không phải số **cụm ký tự hiển thị** (grapheme clusters).
- Giới hạn “50 ký tự” trong UI phải xác định rõ là code unit, code point, grapheme cluster hay số byte được lưu.

~~~java
String symbol = "😀";
System.out.println(symbol.length());                    // 2 UTF-16 code units
System.out.println(symbol.codePointCount(0, symbol.length())); // 1 code point
~~~

Nếu cắt chuỗi bằng chỉ số `char`, có thể làm hỏng cặp surrogate. Nếu nghiệp vụ thật sự giới hạn số ký tự hiển thị, cần công cụ tách grapheme phù hợp Unicode và kiểm thử với emoji ghép, dấu kết hợp và ngôn ngữ thực tế.

### 3.2. So sánh giá trị, chuẩn hóa và quy tắc chữ hoa/thường

Java so sánh tham chiếu bằng `==`. Muốn kiểm tra nội dung chuỗi, dùng `equals` hoặc một chính sách so sánh khác được đặt tên rõ.

~~~java
String input = new String("ACTIVE");
System.out.println(input == "ACTIVE");       // false: khác đối tượng
System.out.println("ACTIVE".equals(input));  // true: bằng nội dung
~~~

Hai văn bản hiển thị giống nhau có thể sử dụng các chuỗi code point khác nhau. Ví dụ chữ `é` có thể là một code point hoặc chữ `e` cộng dấu sắc.

~~~java
import java.text.Normalizer;

String composed = "Café";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

**Chuẩn hóa Unicode** chỉ giải quyết một loại khác biệt biểu diễn. Nó không tự ngăn các ký tự trông giống nhau giữa các hệ chữ (homoglyph/confusables), cũng không định nghĩa cách xử lý biệt danh, tên riêng hoặc tài khoản. Không tự áp dụng chuẩn hóa tương thích `NFKC` hoặc xóa dấu vào mọi trường vì có thể làm thay đổi ý nghĩa dữ liệu.

Việc không phân biệt hoa/thường cũng cần đặc tả. Chẳng hạn, mã trạng thái nội bộ có thể chuẩn hóa về chữ hoa theo quy tắc không phụ thuộc ngôn ngữ:

~~~java
import java.util.Locale;

String rawStatus = "active";
String status = rawStatus.toUpperCase(Locale.ROOT); // "ACTIVE"
~~~

`Locale.ROOT` hữu ích cho token kỹ thuật có quy tắc phân biệt chữ rõ ràng; nó không thay thế mọi quy tắc so khớp ngôn ngữ tự nhiên, Unicode case folding đầy đủ hoặc collation theo ngôn ngữ. Với tên người, địa chỉ và nội dung hiển thị, đừng mặc định biến mọi thứ thành chữ thường để kiểm tra “trùng nhau”.

### 3.3. `null`, rỗng, toàn khoảng trắng và dữ liệu vắng mặt

Các trạng thái thường bị nhập nhằng:

| Giá trị | Ý nghĩa có thể có |
| --- | --- |
| `null` | Không được cung cấp, không biết hoặc không áp dụng (phải theo hợp đồng) |
| `""` | Được cung cấp nhưng không có ký tự |
| `"   "` | Có ký tự khoảng trắng, có thể không mang nội dung hữu ích |
| `"0"` | Một chuỗi ký tự số; không tự động đồng nghĩa số nguyên `0` |
| `"N/A"` | Giá trị văn bản; chỉ là “không áp dụng” nếu hợp đồng quy định |

~~~java
static String requiredDisplayName(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Name is required");
    }
    String name = raw.strip(); // Java 11+, bỏ khoảng trắng ở đầu/cuối theo isWhitespace
    if (name.isEmpty()) {
        throw new IllegalArgumentException("Name must not be blank");
    }
    return name;
}
~~~

Đây là quy tắc phù hợp cho một *tên hiển thị* giả định; nó **không phù hợp cho mọi chuỗi**. Ví dụ, với mật khẩu hoặc token có định nghĩa byte chính xác, tự ý `trim()`/`strip()`, đổi hoa/thường hoặc chuẩn hóa có thể khiến giá trị người dùng nhập bị đổi mà không có thông báo. Khi yêu cầu phân biệt chính xác khoảng trắng, phải giữ nguyên.

`String.isBlank()` và `strip()` dựa trên định nghĩa khoảng trắng của Java, không bao phủ mọi ký tự có hình thức giống khoảng trắng. Nếu định dạng đầu vào chỉ cho phép ký tự ASCII, phải kiểm tra đúng tập ký tự đã được quy định thay vì suy từ việc hiển thị.

### 3.4. Mã hóa ký tự và chuyển dữ liệu qua ranh giới

**Unicode** là mô hình ký tự; **UTF-8** là cách mã hóa thành byte. Nếu bên ghi dùng UTF-8 nhưng bên đọc đoán sai charset, chuỗi có thể trở thành mojibake hoặc mất thông tin.

~~~java
import java.nio.charset.StandardCharsets;

String original = "Tiếng Việt";
byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(encoded, StandardCharsets.UTF_8);
System.out.println(original.equals(restored)); // true
~~~

Trong API, tệp và database, xác định rõ charset/encoding. Nếu đọc từ byte không hợp lệ, parser hoặc decoder phải có chính sách rõ ràng: từ chối dữ liệu không hợp lệ hay thay ký tự, tránh thay thế âm thầm khi tính toàn vẹn quan trọng.

**Mã định danh không phải văn bản ngôn ngữ tự nhiên.** ID sản phẩm, email, mã khuyến mãi, đường dẫn và token có quy tắc khác nhau: đôi khi phân biệt hoa/thường, đôi khi không; có định dạng cố định; có trường phải giữ nguyên byte. Quy tắc so sánh cần dựa vào hợp đồng của **loại định danh cụ thể**, không dùng một hàm `normalizeEverything()` cho cả hệ thống.

### 3.5. Parsing và kiểm tra đầu vào

Phân tách ba bước:

1. **Kiểm tra hình thức:** đầu vào có đúng cấu trúc mong đợi (độ dài, dấu phân cách, ký tự cho phép) không?
2. **Chuyển kiểu:** giá trị có biểu diễn được trong kiểu đích không?
3. **Kiểm tra nghiệp vụ:** giá trị chuyển được có nằm trong miền hợp lệ không?

Ví dụ, `"999999999999999999999"` chỉ gồm chữ số nhưng có thể vượt miền của `long`; `"-5"` chuyển thành `int` thành công nhưng không hợp lệ cho số lượng hàng nếu hệ thống cấm âm.

~~~java
static int parseQuantity(String text) {
    if (text == null || !text.matches("[0-9]{1,6}")) {
        throw new IllegalArgumentException("Invalid quantity format");
    }
    int quantity = Integer.parseInt(text);
    if (quantity < 1 || quantity > 10_000) {
        throw new IllegalArgumentException("Quantity out of range");
    }
    return quantity;
}
~~~

Ở đây regex diễn đạt rõ định dạng ASCII và giới hạn độ dài đã chọn. Tùy API, giá trị `0`, dấu `+`, chữ số Unicode hoặc khoảng trắng có thể được chấp nhận hay từ chối; quyết định phải được viết vào hợp đồng.

## 4. Tính đúng đắn của thời gian

### 4.1. Phân biệt các khái niệm thời gian

Một chuỗi `2026-11-16 09:00` chưa đủ để xác định một thời điểm toàn cầu nếu không biết múi giờ hoặc offset.

| Khái niệm | Kiểu Java thường dùng | Ý nghĩa |
| --- | --- | --- |
| Thời điểm tuyệt đối | `Instant` | Một mốc trên trục thời gian UTC |
| Ngày theo lịch | `LocalDate` | Một ngày, chưa gắn múi giờ |
| Giờ theo đồng hồ | `LocalTime` | Một giờ trong ngày, chưa gắn ngày/múi giờ |
| Ngày và giờ địa phương | `LocalDateTime` | “09:00 ngày X” nhưng chưa xác định duy nhất một `Instant` |
| Thời gian kèm offset | `OffsetDateTime` | Ngày giờ với chênh lệch cố định so với UTC |
| Thời gian theo vùng | `ZonedDateTime` | Ngày giờ gắn `ZoneId` và quy tắc chuyển giờ của vùng |
| Khoảng thời gian theo giây/nanosecond | `Duration` | Độ dài trên trục thời gian |
| Khoảng theo đơn vị lịch | `Period` | Số năm, tháng, ngày theo lịch |

Java `java.time` cung cấp các kiểu tách biệt vì **“một ngày”, “một mốc UTC” và “24 giờ” không phải lúc nào cũng tương đương**.

Ví dụ:

~~~java
import java.time.*;

Instant instant = Instant.parse("2026-11-16T02:00:00Z");
ZonedDateTime inVietnam = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(inVietnam); // 2026-11-16T09:00+07:00[Asia/Ho_Chi_Minh]
~~~

Cùng một `Instant` có thể rơi vào các ngày địa phương khác nhau tùy vùng. Do đó câu hỏi “đơn được tạo ngày nào?” cần nêu rõ ngày theo vùng của khách hàng, cửa hàng, tổ chức hay UTC.

### 4.2. Múi giờ, offset và giờ mùa hè (DST)

- **UTC** dùng để biểu diễn/truyền thời điểm tuyệt đối; `Instant` phù hợp để lưu thời điểm xảy ra sự kiện.
- **Offset** như `+07:00` là độ lệch tại một thời điểm, không mô tả đầy đủ lịch sử và quy tắc tương lai của một vùng.
- **ZoneId** như `Asia/Ho_Chi_Minh` hoặc `America/New_York` xác định vùng có các quy tắc lịch sử hoặc chuyển giờ, phụ thuộc cơ sở dữ liệu múi giờ của runtime.

Ở một số vùng có đổi giờ mùa hè, có giờ địa phương **không tồn tại** khi đồng hồ nhảy tới, hoặc có giờ **xuất hiện hai lần** khi đồng hồ lùi. Ví dụ `2026-03-08 02:30` tại `America/New_York` rơi vào khoảng giờ không tồn tại do chuyển sang giờ mùa hè.

~~~java
import java.time.*;
import java.util.List;

ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime requested = LocalDateTime.of(2026, 3, 8, 2, 30);

List<ZoneOffset> validOffsets =
        zone.getRules().getValidOffsets(requested);

if (validOffsets.isEmpty()) {
    // Giờ địa phương không tồn tại.
    throw new IllegalArgumentException("Local time falls in a DST gap");
}
if (validOffsets.size() > 1) {
    // Giờ địa phương xuất hiện hai lần; cần chính sách lựa chọn.
    throw new IllegalArgumentException("Ambiguous local time");
}
ZonedDateTime scheduled = ZonedDateTime.ofLocal(
        requested, zone, validOffsets.get(0));
~~~

Lưu ý `LocalDateTime.atZone(zone)` có quy tắc tự điều chỉnh gap/overlap; nó không mặc nhiên từ chối giờ không hợp lệ hoặc mơ hồ. Với lịch hẹn, tác vụ định kỳ và giao dịch ràng buộc giờ địa phương, **chính sách khi gặp gap/overlap** phải được xác định rõ.

Các quy tắc vùng có thể được cập nhật bởi cơ quan quản lý; hệ thống lịch dài hạn cần quan tâm phiên bản dữ liệu múi giờ khi vận hành, không chỉ offset tại lúc tạo lịch.

### 4.3. Ngày lịch, thời lượng và khoảng báo cáo

Một “ngày địa phương” nên được xác định bằng mốc bắt đầu ngày và **mốc bắt đầu ngày kế tiếp** trong cùng `ZoneId`. Không nên tự cộng 86.400 giây nếu vùng có thể chuyển DST.

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDate reportDate = LocalDate.of(2026, 11, 1);

Instant start = reportDate.atStartOfDay(zone).toInstant();
Instant endExclusive = reportDate.plusDays(1)
        .atStartOfDay(zone).toInstant();

Instant event = Instant.parse("2026-11-01T08:30:00Z");
boolean isWithinDay = !event.isBefore(start)
        && event.isBefore(endExclusive);
~~~

**Quy ước khoảng nửa mở `[start, end)`** nhận `start` và loại `end`. Nó giúp ghép các ngày liên tiếp mà không đếm trùng sự kiện ở đúng 00:00:00, đồng thời tránh phải đoán “thời khắc cuối cùng của ngày” với độ chính xác milli/nanosecond.

Có thể đóng gói điều kiện này thành hàm tự chứa để tái sử dụng:

~~~java
static boolean belongsToLocalDate(
        Instant event, LocalDate date, ZoneId zone
) {
    Instant start = date.atStartOfDay(zone).toInstant();
    Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
    return !event.isBefore(start) && event.isBefore(end);
}
~~~

Ngày `2026-11-01` ở New York dài **25 giờ** do kết thúc DST. Vì thế `start.plus(Duration.ofDays(1))` không nhất thiết là đầu ngày kế tiếp theo giờ địa phương.

### 4.4. Parse nghiêm ngặt, định dạng và ý nghĩa của ngày

Định dạng `MM/dd/yyyy` và `dd/MM/yyyy` có thể gây nhầm lẫn nếu không quy định locale. Giao thức máy nên dùng định dạng rõ, chẳng hạn ISO 8601. Trên giao diện, format theo ngôn ngữ/vùng người dùng nhưng giữ dữ liệu nội bộ ở kiểu có ý nghĩa đúng.

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

DateTimeFormatter strictDate = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate leapDay = LocalDate.parse("2024-02-29", strictDate);
// LocalDate.parse("2025-02-29", strictDate) -> DateTimeParseException.
~~~

Dùng `uuuu` với strict parsing cho năm theo lịch ISO (proleptic year); `yyyy` là year-of-era nên khi parse nghiêm ngặt có thể cần thêm era. Các kiểm tra phải bao gồm **ngày nhuận, tháng có 28/29/30/31 ngày** và dữ liệu rơi vào biên thay đổi năm.

Một `LocalDateTime` **không chứa múi giờ**. Nếu API gửi `"2026-11-16T09:00:00"` mà server tự dùng múi giờ máy đang chạy, cùng dữ liệu có thể cho hai thời điểm khác nhau ở hai môi trường. Hợp đồng phải truyền `Instant`/offset khi nói về một thời điểm, hoặc truyền ngày giờ địa phương **kèm vùng được chọn** khi lập lịch.

### 4.5. Đồng hồ hệ thống và kiểm thử có thể lặp lại

Đọc thời gian hiện tại trực tiếp trong nhiều hàm bằng `Instant.now()` khiến kiểm thử phụ thuộc vào đồng hồ thật. Với quy tắc hết hạn, có thể **truyền `Clock`** để cố định thời gian trong test:

~~~java
import java.time.*;

final class ExpiryPolicy {
    private final Clock clock;

    ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        // Hết hạn ngay tại expiresAt.
        return !clock.instant().isBefore(expiresAt);
    }
}

Instant fixedNow = Instant.parse("2026-11-16T02:00:00Z");
ExpiryPolicy policy = new ExpiryPolicy(
        Clock.fixed(fixedNow, ZoneOffset.UTC));

System.out.println(policy.isExpired(fixedNow)); // true
~~~

Đồng hồ wall-clock (`Instant.now()`, `System.currentTimeMillis()`) có thể được điều chỉnh. Để **đo thời gian đã trôi qua trong một tiến trình**, `System.nanoTime()` thường phù hợp hơn vì là nguồn thời gian tương đối/đơn điệu cho đo khoảng, không phải thời điểm UTC. Không gửi giá trị `nanoTime()` qua API rồi giải nghĩa là timestamp.

## 5. Những lỗi khi dữ liệu đi qua nhiều lớp

Tính đúng đắn có thể mất đi ở ranh giới, dù mỗi đoạn mã riêng lẻ trông hợp lý:

| Nguồn → đích | Lỗi thường gặp | Cách kiểm soát |
| --- | --- | --- |
| JSON → Java | Số lớn mất chính xác ở client trước khi gửi; thập phân bị ép sang `double` | Đặc tả kiểu và dải số; dùng decimal dạng chuỗi/kiểu chính xác khi cần |
| Java → database | Cột số không đủ độ rộng, scale của `DECIMAL` không khớp | Định nghĩa precision/scale, kiểm thử giá trị biên và quy tắc làm tròn |
| Form → backend | `"1,234"` được hiểu khác locale; `null` và rỗng bị trộn | Quy định locale, parse chặt, hợp đồng trường bắt buộc/tùy chọn |
| UTF-8 → hệ thống ngoài | Charset không thống nhất hoặc ký tự không hợp lệ bị thay thế | Khai báo encoding và cách xử lý lỗi decode |
| Database → API | Timestamp không có offset được diễn giải theo múi giờ máy | Dùng kiểu thời điểm rõ ràng, serialize có offset/UTC |
| Lịch địa phương → tác vụ nền | Dùng `Duration.ofHours(24)` để lên lịch “cùng giờ ngày mai” | Phân biệt cộng theo lịch với cộng thời lượng; xét quy tắc `ZoneId` |
| Báo cáo theo ngày | Dùng `23:59:59` làm mốc cuối, bỏ sót phần giây | Khoảng nửa mở `[start, nextStart)` |

**Hợp đồng dữ liệu tốt** không chỉ nói “trường này là string/number”. Nó nói rõ: miền hợp lệ, đơn vị, timezone/locale, precision, giá trị thiếu, chính sách chuẩn hóa, làm tròn, hành vi lỗi và định dạng khi trao đổi. Khi đặc tả rõ, người kiểm thử biết phải kiểm chứng gì, và người bảo trì không phải đoán lại quyết định cũ.

## 6. Ví dụ xuyên suốt: xuất báo cáo doanh thu theo ngày

Giả sử cửa hàng cần báo cáo doanh thu trong **ngày 01/11/2026 theo giờ New York**. Mỗi giao dịch có:

- `orderId`: chuỗi định danh theo quy tắc hệ thống; không được tự sửa chữ hoa/thường khi không có đặc tả.
- `completedAt`: thời điểm hoàn tất, lưu như `Instant` (UTC).
- `amount`: giá trị thập phân, phải cộng chính xác và làm tròn theo quy tắc định sẵn.
- `currency`: mã tiền tệ; chỉ cộng các khoản cùng đơn vị tiền đã xác định.

Một triển khai thiếu rõ ràng có thể dùng `double` để cộng tiền, biến ngày thành `Instant` theo múi giờ server và lấy khoảng `24h` kể từ nửa đêm. Ba lựa chọn đó có thể cùng làm báo cáo sai.

Thiết kế rõ nghĩa hơn:

~~~java
import java.math.BigDecimal;
import java.time.*;
import java.util.List;
import java.util.Objects;

record Sale(
        String orderId,
        Instant completedAt,
        BigDecimal amount,
        String currency
) {}

static BigDecimal dailyRevenue(
        List<Sale> sales,
        LocalDate date,
        ZoneId businessZone,
        String currency
) {
    Objects.requireNonNull(sales, "sales");
    Objects.requireNonNull(date, "date");
    Objects.requireNonNull(businessZone, "businessZone");
    Objects.requireNonNull(currency, "currency");

    Instant start = date.atStartOfDay(businessZone).toInstant();
    Instant end = date.plusDays(1).atStartOfDay(businessZone).toInstant();

    BigDecimal total = BigDecimal.ZERO;
    for (Sale sale : sales) {
        Objects.requireNonNull(sale, "sale");
        Objects.requireNonNull(sale.completedAt(), "completedAt");
        Objects.requireNonNull(sale.amount(), "amount");
        Objects.requireNonNull(sale.currency(), "sale currency");

        if (!currency.equals(sale.currency())) {
            continue; // Báo cáo riêng từng đồng tiền.
        }
        Instant moment = sale.completedAt();
        if (!moment.isBefore(start) && moment.isBefore(end)) {
            total = total.add(sale.amount());
        }
    }
    return total; // Quy tắc làm tròn/hiển thị ở ranh giới nghiệp vụ.
}
~~~

Đây là ví dụ thuần tính toán để minh họa ý nghĩa dữ liệu. Hệ thống thực tế còn phải xác định liệu tiền hoàn, hủy đơn, phí và thuế có được cộng vào “doanh thu” không, kiểm tra bản ghi trùng lặp và bảo đảm nguồn dữ liệu đầy đủ. Ví dụ này không tự giải quyết các yêu cầu đó.

Các quyết định rõ ràng trong mã:

1. `LocalDate` nói **ngày trên lịch**, `ZoneId` xác định **ngày theo vùng nào**, `Instant` nói **giao dịch xảy ra lúc nào**.
2. `BigDecimal` tránh lỗi cộng tiền bằng dấu phẩy động nhị phân; đơn vị tiền được lọc rõ ràng.
3. `[start, end)` không bỏ sót phần giây cuối và không đếm trùng ở ranh giới hai ngày.
4. Quy tắc về dữ liệu thiếu và trường không hợp lệ được xử lý tường minh; hành vi với giao dịch âm hay giao dịch trùng phải tiếp tục do nghiệp vụ quy định.

## 7. Kiểm thử những trường hợp dễ sai

Bộ kiểm thử dưới đây giả định JUnit 5 và các lớp/phương thức minh họa đã được đặt trong test scope phù hợp. Mục tiêu là kiểm tra **đặc tả**, không lặp lại cách cài đặt:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.text.Normalizer;
import java.time.*;

class DataCorrectnessExamplesTest {
    @Test
    void decimalAmountsAreComparedNumerically() {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        assertEquals(0, a.compareTo(b));
        assertFalse(a.equals(b)); // Scale khác nhau.
    }

    @Test
    void integerOverflowIsDetected() {
        assertThrows(ArithmeticException.class,
                () -> Math.addExact(Integer.MAX_VALUE, 1));
    }

    @Test
    void unicodeCanHaveEquivalentForms() {
        String first = "Café";
        String second = "Cafe\u0301";
        assertNotEquals(first, second);
        assertEquals(first,
                Normalizer.normalize(second, Normalizer.Form.NFC));
    }

    @Test
    void invalidLeapDayIsRejected() {
        java.time.format.DateTimeFormatter formatter =
                java.time.format.DateTimeFormatter
                        .ofPattern("uuuu-MM-dd")
                        .withResolverStyle(
                                java.time.format.ResolverStyle.STRICT);
        assertThrows(java.time.format.DateTimeParseException.class,
                () -> LocalDate.parse("2025-02-29", formatter));
        assertEquals(LocalDate.of(2024, 2, 29),
                LocalDate.parse("2024-02-29", formatter));
    }

    @Test
    void newYorkFallBackDayHas25Hours() {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDate day = LocalDate.of(2026, 11, 1);
        Instant start = day.atStartOfDay(zone).toInstant();
        Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
        assertEquals(25, Duration.between(start, end).toHours());
    }

    @Test
    void expiryBoundaryIsInclusive() {
        Instant expiry = Instant.parse("2026-11-16T02:00:00Z");
        ExpiryPolicy policy = new ExpiryPolicy(
                Clock.fixed(expiry, ZoneOffset.UTC));
        assertTrue(policy.isExpired(expiry));
    }
}
~~~

Lưu ý: bài kiểm thử ngày nhuận minh họa `LocalDate.parse` với chế độ strict. Trong dự án thực tế, hãy bổ sung assertion cho quy tắc nghiệp vụ đang phát triển (ví dụ: ngày nằm trong khoảng cho phép), thay vì chỉ kiểm tra lại hành vi thư viện chuẩn.

Đối với mỗi loại dữ liệu, nên chuẩn bị thêm các nhóm trường hợp:

| Loại | Trường hợp bình thường | Trường hợp biên và lỗi |
| --- | --- | --- |
| Số nguyên | Giá trị nhỏ, dương, đúng đơn vị | `0`, âm, `MAX_VALUE`, tràn trong trung gian, chia cho 0 |
| Decimal | Tính giá và thuế đúng chính sách | Phân số vô hạn, scale khác, làm tròn đúng tại `x.xx5`, tiền âm hoặc nhiều currency |
| Số thực | Phép đo thông thường | Số rất gần nhau, số rất lớn/nhỏ, `NaN`, vô cực, `-0.0` nếu có ý nghĩa |
| Chuỗi | ASCII và Unicode hợp lệ | `null`, rỗng, trắng, dấu kết hợp, emoji ghép, ký tự tương tự, encoding lỗi |
| Ngày | Ngày làm việc thông thường | 29/02, cuối tháng, giao năm, ngày giờ không hợp lệ |
| Múi giờ | Quy đổi UTC ↔ giờ địa phương | Chênh lệch ngày, gap/overlap do DST, thay đổi offset |
| Khoảng thời gian | Sự kiện giữa khoảng | Đúng `start`, đúng `end`, độ chính xác cao, ngày 23/25 giờ |

**Độ bao phủ dòng cao chưa đảm bảo tính đúng đắn** nếu các bài kiểm thử chỉ thử giá trị “đẹp”. Kiểm tra miền giá trị và các ranh giới thường phát hiện vấn đề sớm hơn.

## 8. Các ngộ nhận cần tránh

- **“`double` có nhiều chữ số nên luôn chính xác với tiền.”** Độ chính xác nhị phân và quy tắc decimal nghiệp vụ là hai vấn đề khác nhau.
- **“Gán kết quả nhân `int` vào `long` sẽ tự tránh tràn.”** Phép tính có thể đã tràn trước khi gán.
- **“Hai chuỗi trông giống nhau thì `equals` chắc chắn `true`.”** Unicode có nhiều cách biểu diễn; tính tương đương phụ thuộc chính sách.
- **“`String.length()` đếm ký tự người dùng thấy.”** Nó đếm code unit UTF-16.
- **“`trim()` luôn là thao tác chuẩn hóa chuỗi an toàn.”** Khoảng trắng có thể có ý nghĩa; hành vi phải theo từng trường dữ liệu.
- **“Timestamp không có offset cũng là thời điểm toàn cầu.”** Thiếu vùng hoặc offset thì không xác định được một `Instant` duy nhất.
- **“Một ngày luôn có 24 giờ.”** Có vùng xảy ra ngày 23 hoặc 25 giờ khi đổi DST.
- **“Ngày kết thúc báo cáo là `23:59:59`.”** Có thể bỏ sót sự kiện với phần giây; dùng khoảng nửa mở.
- **“Parser đọc được phần đầu là dữ liệu hợp lệ.”** Cần kiểm tra toàn bộ chuỗi và miền giá trị hợp lệ.

## 9. Cách áp dụng khi review hoặc sửa mã

Khi gặp một luồng xử lý số, chuỗi hoặc thời gian, hãy đi theo chuỗi câu hỏi cụ thể:

1. **Dữ liệu mang ý nghĩa gì?** Hãy ghi ra ví dụ đúng và trường hợp bị cấm.
2. **Kiểu có giữ đúng ý nghĩa đó không?** `double` cho tiền, `String` cho mọi loại thời gian hay `int` cho bộ đếm lớn có phải dấu hiệu cần xem lại không?
3. **Chuyển đổi diễn ra ở đâu?** Đối chiếu đơn vị, charset, locale, múi giờ, precision và quy tắc làm tròn.
4. **Hợp đồng thiếu/không hợp lệ ra sao?** Có từ chối dữ liệu sai, có thông báo rõ và có tránh biến giá trị sai thành giá trị “hợp lệ” âm thầm không?
5. **Ranh giới nào chưa được thử?** Số cực đại, Unicode kết hợp, DST, ngày nhuận, mốc `start/end`.
6. **Người sửa sau có hiểu không?** Đặt tên theo đơn vị và ý nghĩa, tập trung chính sách tại nơi có trách nhiệm, ghi lại quyết định nghiệp vụ.

Với một lỗi cụ thể, nên bổ sung bài kiểm thử tái hiện **giá trị đầu vào, môi trường, quy tắc kỳ vọng và giá trị thực tế** trước khi sửa. Điều này giúp bảo vệ tính đúng đắn về sau khi chức năng hoặc môi trường thay đổi.

## 10. Tự kiểm tra

1. Vì sao `long total = price * quantity` vẫn có thể sai khi `price` và `quantity` đều là `int`? Hãy đưa ra cách sửa.
2. Khi nào `BigDecimal.compareTo()` phù hợp hơn `equals()`? Có trường hợp nào cần phân biệt scale hay không?
3. Chương trình nhận `"1,250"` từ người dùng ở nhiều quốc gia. Cần xác định những gì trước khi chuyển thành số?
4. Vì sao hai tên hiển thị giống nhau có thể không bằng nhau bằng `String.equals()`? Có nên chuẩn hóa mọi trường không?
5. Phân biệt `Instant`, `LocalDateTime` và `ZonedDateTime` trong ngữ cảnh lịch hẹn.
6. Một báo cáo ngày tại New York bắt đầu 00:00 ngày 01/11/2026. Vì sao cộng đúng 24 giờ để lấy mốc kết thúc có thể sai?
7. Tại sao `23:59:59` không phải cách an toàn để xác định điểm cuối của ngày trong hệ thống hỗ trợ độ chính xác millisecond?
8. Bạn sẽ viết những test nào cho hàm tính thuế có làm tròn, xử lý tên Unicode và kiểm tra thời điểm hết hạn?

## Ghi nhớ

Tính đúng đắn của dữ liệu đến từ **sự khớp nhau giữa ý nghĩa nghiệp vụ và biểu diễn kỹ thuật**. Với số, phải kiểm soát miền giá trị, đơn vị, tràn và làm tròn; với chuỗi, cần quyết định quy tắc so sánh, Unicode, encoding và dữ liệu vắng mặt; với thời gian, phải phân biệt thời điểm, ngày theo lịch, múi giờ và thời lượng. Những quyết định rõ ràng cùng kiểm thử trường hợp biên làm mã đáng tin cậy, dễ hiểu và an toàn khi thay đổi.
