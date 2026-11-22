# Hoàn thiện ví dụ tích hợp cùng bộ kiểm thử dữ liệu biên — Java Core Numbers

## 1. Mục tiêu và sản phẩm cuối

Bài thực hành này hoàn thiện **một chương trình Java 17 chạy độc lập**, sử dụng nhiều kiến thức số học của Java trong cùng một luồng xử lý: nhập dữ liệu decimal, chuyển về số nguyên đơn vị nhỏ nhất, kiểm tra số lượng, nhân và cộng có phát hiện overflow, tính thuế có quy tắc làm tròn rõ ràng, định dạng kết quả, và kiểm thử dữ liệu ở biên.

Bài toán minh họa: tính tiền cho **một dòng hóa đơn**. Đầu vào gồm đơn giá decimal dạng chuỗi, số lượng dạng chuỗi và tỷ lệ thuế dạng chuỗi. Đầu ra là ba giá trị số nguyên long: tiền hàng, thuế và tổng tiền, tất cả tính bằng **cents**. Thuật toán có một bộ kiểm thử tự động không cần thư viện ngoài, cho kết quả xác định khi chạy bằng JDK 17 trở lên.

Yêu cầu kiểm chứng cụ thể:

- Đơn giá không âm, chỉ dùng chữ số ASCII; phần thập phân tối đa hai chữ số. Chuỗi có dấu âm, dấu phẩy, khoảng trắng hoặc số mũ bị từ chối.
- Số lượng là số nguyên dương trong miền int, không có dấu và không có phần thập phân.
- Tỷ lệ thuế nằm trong khoảng 0 đến 1 và có tối đa bốn chữ số thập phân; ví dụ 0.075 nghĩa là 7,5%.
- Mọi phép nhân và cộng tạo kết quả long phải **phát hiện tràn**, không được âm thầm wrap.
- Thuế làm tròn tới cents theo **HALF_EVEN** (làm tròn về số chẵn ở trường hợp đúng nửa bước).
- Dữ liệu sai định dạng/miền bị từ chối; số vượt phạm vi khi chuyển đổi hoặc tính toán được báo lỗi.
- Bộ kiểm thử gồm giá trị thông thường, giá trị biên hợp lệ, giá trị ngay bên ngoài biên, trường hợp nửa bước làm tròn, NaN, vô cực và overflow.

Đây là ví dụ thiết kế dữ liệu số, **không phải hệ thống hóa đơn hay thuế thực tế**: đơn vị cents và tỷ lệ thuế chỉ nhằm minh họa, không đại diện cho quy tắc của một quốc gia hay loại tiền cụ thể.

## 2. Xác định hợp đồng trước khi viết code

| Thành phần | Kiểu đầu vào | Quy tắc | Kiểu lưu sau kiểm tra |
| --- | --- | --- | --- |
| Đơn giá | String | Dạng `[0-9]+(?:\\.[0-9]{1,2})?`, không âm | long cents |
| Số lượng | String | Chỉ chữ số, giá trị 1 đến Integer.MAX_VALUE | int |
| Tỷ lệ thuế | String | Từ 0 đến 1, tối đa 4 chữ số thập phân | BigDecimal |
| Tiền hàng | long cents nhân int | Không vượt long | long |
| Thuế | Tiền hàng × tỷ lệ | HALF_EVEN tới cents; còn trong long | long |
| Tổng | Tiền hàng + thuế | Không vượt long | long |

Một vài trường hợp đầu vào:

| Đơn giá | Số lượng | Thuế | Kỳ vọng |
| --- | --- | --- | --- |
| 19.99 | 3 | 0.075 | Hợp lệ: 59.97 + 4.50 = 64.47 |
| 0.05 | 1 | 0.1 | Thuế 0.5 cents, HALF_EVEN → 0 cents |
| 0.15 | 1 | 0.1 | Thuế 1.5 cents, HALF_EVEN → 2 cents |
| 1.000 | 1 | 0 | Từ chối: định dạng có 3 chữ số thập phân |
| -0.01 | 1 | 0 | Từ chối: đơn giá âm |
| 1.00 | 0 | 0 | Từ chối: số lượng phải dương |
| 1.00 | 2147483648 | 0 | Từ chối: vượt miền int |
| 92233720368547758.08 | 1 | 0 | Từ chối: cents vượt Long.MAX_VALUE |

**Lưu ý:** Chính sách “tối đa hai chữ số decimal trong **chuỗi nhập**” khác với “không mất giá trị số khi đổi sang cents”. Theo chính sách đã chọn, `1.000` bị từ chối dù nó có cùng giá trị số với `1.00`. Muốn cho phép các số 0 dư ở cuối, phải sửa đặc tả và kiểm thử tương ứng.

## 3. Luồng xử lý: validate trước, tính toán sau

~~~text
raw price ----------> kiểm tra cú pháp ----------> BigDecimal
                                                   |
                                                   v
                                      movePointRight(2)
                                                   |
                                                   v
                                          longValueExact()
                                                   |
                                                   v
                                              unitCents
                                                   |
raw quantity -------> kiểm tra cú pháp ------> BigInteger
                                                   |
                                                   v
                                             intValueExact()
                                                   |
                                                   v
                                               quantity
                                                   |
                        Math.multiplyExact(unitCents, quantity)
                                                   |
                                                   v
                                             subtotalCents
                                                   |
raw tax rate -------> kiểm tra 0..1 -------> BigDecimal
                                                   |
                        subtotal × tax rate (decimal chính xác)
                                                   |
                                  setScale(0, HALF_EVEN)
                                                   |
                                      longValueExact()
                                                   |
                                                   v
                                                taxCents
                                                   |
                                 Math.addExact(subtotal, tax)
                                                   |
                                                   v
                                               totalCents
~~~

Ta không chuyển đầu vào số tiền qua `double`, bởi một số decimal như 0.1 không thể biểu diễn chính xác bằng binary64. Các phép cộng/nhân trên long chỉ diễn ra khi đầu vào đã qua bước exact; bất cứ khi nào vượt miền, chương trình báo lỗi thay vì tạo một giá trị sai vẫn mang kiểu long hợp lệ.

## 4. Mã nguồn Java 17 hoàn chỉnh

Tạo tệp **NumericBoundaryLab.java** với nội dung sau. Đây là **một chương trình đầy đủ**, gồm cả logic nghiệp vụ và bộ kiểm thử, không cần JUnit, Maven hoặc thư viện ngoài.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericBoundaryLab {
    record Receipt(long subtotalCents, long taxCents, long totalCents) {}

    private static int passed;

    static long parsePriceCents(String raw) {
        if (raw == null || raw.length() > 40 ||
                !raw.matches("[0-9]+(?:\\.[0-9]{1,2})?")) {
            throw new IllegalArgumentException("Invalid price format");
        }
        return new BigDecimal(raw).movePointRight(2).longValueExact();
    }

    static int parseQuantity(String raw) {
        if (raw == null || raw.length() > 20 ||
                !raw.matches("[0-9]+")) {
            throw new IllegalArgumentException("Invalid quantity format");
        }
        int quantity = new BigInteger(raw).intValueExact();
        if (quantity < 1) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        return quantity;
    }

    static BigDecimal parseRate(String raw) {
        if (raw == null || raw.length() > 8 ||
                !raw.matches("(?:0(?:\\.[0-9]{1,4})?|1(?:\\.0{1,4})?)")) {
            throw new IllegalArgumentException(
                    "Rate must be 0..1 with <=4 decimals");
        }
        return new BigDecimal(raw);
    }

    static Receipt quote(String price, String quantity, String rate) {
        long unitCents = parsePriceCents(price);
        int units = parseQuantity(quantity);
        BigDecimal taxRate = parseRate(rate);

        long subtotal = Math.multiplyExact(unitCents, (long) units);
        long tax = BigDecimal.valueOf(subtotal)
                .multiply(taxRate)
                .setScale(0, RoundingMode.HALF_EVEN)
                .longValueExact();
        long total = Math.addExact(subtotal, tax);
        return new Receipt(subtotal, tax, total);
    }

    static int exactInt(double value) {
        if (!Double.isFinite(value) ||
                value < Integer.MIN_VALUE ||
                value > Integer.MAX_VALUE ||
                value != Math.rint(value)) {
            throw new IllegalArgumentException("Not an exact int");
        }
        return (int) value;
    }

    static String money(long cents) {
        return BigDecimal.valueOf(cents, 2).toPlainString();
    }

    static void same(Receipt receipt, long subtotal, long tax, long total) {
        if (receipt.subtotalCents() != subtotal ||
                receipt.taxCents() != tax || receipt.totalCents() != total) {
            throw new AssertionError("Unexpected receipt: " + receipt);
        }
    }

    static void check(String name, Runnable test) {
        try {
            test.run();
            passed++;
        } catch (RuntimeException | AssertionError ex) {
            throw new AssertionError("FAILED: " + name, ex);
        }
    }

    static void rejects(String name, Class<? extends RuntimeException> expected,
                        Runnable test) {
        check(name, () -> {
            try {
                test.run();
            } catch (RuntimeException actual) {
                if (expected.isInstance(actual)) return;
                throw new AssertionError("Wrong exception: " + actual);
            }
            throw new AssertionError("Expected " + expected.getSimpleName());
        });
    }

    public static void main(String[] args) {
        check("normal", () -> same(quote("19.99", "3", "0.075"), 5997, 450, 6447));
        check("zero price", () -> same(quote("0.00", "3", "0.075"), 0, 0, 0));
        check("HALF_EVEN even tie", () -> same(quote("0.05", "1", "0.1"), 5, 0, 5));
        check("HALF_EVEN odd tie", () -> same(quote("0.15", "1", "0.1"), 15, 2, 17));
        check("no tax", () -> same(quote("1.00", "2", "0"), 200, 0, 200));
        check("max cents", () -> same(quote("92233720368547758.07", "1", "0"),
                Long.MAX_VALUE, 0, Long.MAX_VALUE));
        check("int upper", () -> { if (exactInt(2147483647.0) != Integer.MAX_VALUE)
                throw new AssertionError(); });
        check("int lower", () -> { if (exactInt(-2147483648.0) != Integer.MIN_VALUE)
                throw new AssertionError(); });
        check("int normal", () -> { if (exactInt(42.0) != 42)
                throw new AssertionError(); });

        rejects("negative price", IllegalArgumentException.class,
                () -> quote("-0.01", "1", "0"));
        rejects("price too many decimals", IllegalArgumentException.class,
                () -> quote("1.000", "1", "0"));
        rejects("price exponent", IllegalArgumentException.class,
                () -> quote("1E3", "1", "0"));
        rejects("price comma", IllegalArgumentException.class,
                () -> quote("1,00", "1", "0"));
        rejects("price space", IllegalArgumentException.class,
                () -> quote(" 1.00", "1", "0"));
        rejects("price null", IllegalArgumentException.class,
                () -> quote(null, "1", "0"));
        rejects("quantity zero", IllegalArgumentException.class,
                () -> quote("1.00", "0", "0"));
        rejects("quantity negative", IllegalArgumentException.class,
                () -> quote("1.00", "-1", "0"));
        rejects("quantity decimal", IllegalArgumentException.class,
                () -> quote("1.00", "1.5", "0"));
        rejects("tax over one", IllegalArgumentException.class,
                () -> quote("1.00", "1", "1.01"));
        rejects("tax too many digits", IllegalArgumentException.class,
                () -> quote("1.00", "1", "0.12345"));
        rejects("tax negative", IllegalArgumentException.class,
                () -> quote("1.00", "1", "-0.1"));
        rejects("price cents overflow", ArithmeticException.class,
                () -> quote("92233720368547758.08", "1", "0"));
        rejects("quantity int overflow", ArithmeticException.class,
                () -> quote("1.00", "2147483648", "0"));
        rejects("subtotal long overflow", ArithmeticException.class,
                () -> quote("92233720368547758.07", "2", "0"));
        rejects("total long overflow", ArithmeticException.class,
                () -> quote("92233720368547758.07", "1", "1"));
        rejects("fractional double", IllegalArgumentException.class,
                () -> exactInt(12.9));
        rejects("NaN", IllegalArgumentException.class,
                () -> exactInt(Double.NaN));
        rejects("Infinity", IllegalArgumentException.class,
                () -> exactInt(Double.POSITIVE_INFINITY));
        rejects("double out of int range", IllegalArgumentException.class,
                () -> exactInt(2147483648.0));
        rejects("int addition overflow", ArithmeticException.class,
                () -> Math.addExact(Integer.MAX_VALUE, 1));

        Receipt demo = quote("19.99", "3", "0.075");
        System.out.println("subtotal=" + money(demo.subtotalCents()) +
                ", tax=" + money(demo.taxCents()) +
                ", total=" + money(demo.totalCents()));
        System.out.println("PASS " + passed + " boundary cases");
    }
}
~~~

**Cách chạy:**

~~~bash
javac NumericBoundaryLab.java
java NumericBoundaryLab
~~~

**Kết quả khi chương trình vượt qua toàn bộ kiểm thử:**

~~~text
subtotal=59.97, tax=4.50, total=64.47
PASS 30 boundary cases
~~~

Nếu một bài test trả sai kết quả hoặc một phép chuyển đổi không ném exception như dự kiến, phương thức `check` ném `AssertionError` có tên case. Chương trình sẽ dừng với lỗi thay vì in dòng PASS cuối cùng.

Bộ thử dùng plain Java nên thuận tiện cho một bài học chạy trực tiếp. Trong dự án thực tế, có thể chuyển từng nhóm sang JUnit 5 và thiết lập pipeline tự động; logic assert và dữ liệu biên vẫn dùng được.

## 5. Giải thích từng lớp bảo vệ

### 5.1. Kiểm tra cú pháp trước khi parse

`parsePriceCents` từ chối null, chuỗi dài hơn 40 ký tự và chuỗi không khớp một mẫu decimal ASCII không âm, với tối đa hai chữ số sau dấu chấm. Lý do đặt kiểm tra trước `new BigDecimal(raw)`: BigDecimal nhận nhiều cú pháp hợp lệ về mặt toán học, chẳng hạn exponent, nhưng hợp đồng của ứng dụng minh họa **không** cho phép.

Các đầu vào như `1E3`, `1,00`, ` 1.00` hoặc `-0.00` bị từ chối theo chính sách đã chọn. Lưu ý rằng xét về **giá trị số**, `-0.00` có thể bằng 0; cấm dấu trừ là quyết định về cú pháp, không phải phép so sánh số âm.

Giới hạn độ dài trước parse giúp tránh tiếp nhận chuỗi số quá dài không cần thiết trong bài toán này. Với ứng dụng có giao diện đa ngôn ngữ, mẫu ASCII nghiêm ngặt có thể không phù hợp; định dạng hợp lệ cần được công bố rõ, ví dụ cách nhập dấu phân cách thập phân và hàng nghìn.

### 5.2. Đổi decimal thành cents mà không làm tròn

`new BigDecimal(raw).movePointRight(2).longValueExact()` gồm hai thao tác quan trọng:

- `movePointRight(2)` nhân giá trị decimal với 100 theo phép biểu diễn thập phân chính xác, không làm tròn.
- `longValueExact()` chỉ chấp nhận nếu giá trị sau nhân 100 là số nguyên nằm trong miền long; nếu không ném `ArithmeticException`.

Ở đây tính hợp lệ về **định dạng** đã được kiểm tra riêng. Với đơn giá đầu vào tối đa hai chữ số thập phân, kết quả cents sẽ có giá trị nguyên. Nhưng vẫn phải có bước kiểm tra **phạm vi long** vì chuỗi có thể chứa số rất lớn.

Biên trên của long là 9223372036854775807 cents. Vì vậy giá `92233720368547758.07` đi với số lượng 1, thuế 0, còn hợp lệ; `92233720368547758.08` vượt một cent và bị từ chối.

### 5.3. Không ép số lượng từ BigInteger xuống int một cách âm thầm

`parseQuantity` parse chuỗi qua `BigInteger` rồi gọi `intValueExact()`. Cách này cho phép phân biệt:

- `"0"`: cú pháp đúng, **sai miền nghiệp vụ** vì phải lớn hơn 0.
- `"-1"`: sai cú pháp vì không cho dấu trừ.
- `"1.5"`: sai cú pháp vì số lượng phải nguyên.
- `"2147483648"`: cú pháp nguyên không âm đúng, nhưng **vượt miền int**, khiến `intValueExact()` ném ArithmeticException.

Dùng `Integer.parseInt` cũng có thể từ chối số ngoài miền int, nhưng thông báo/loại lỗi sẽ khác. Cách dùng BigInteger làm rõ hai giai đoạn: hiểu giá trị số nguyên trước, kiểm tra phạm vi kiểu đích sau.

### 5.4. Nhân và cộng có kiểm tra overflow

`Math.multiplyExact(unitCents, (long) units)` trả long hoặc ném ArithmeticException nếu tích toán học vượt miền long. Phép ép long của số lượng được làm **trước phép nhân**; dù phép nhân giữa hai int có thể phù hợp nếu kết quả vừa int, không được tính một kết quả int tràn rồi mới gán vào long.

`Math.addExact(subtotal, tax)` dùng sau khi thuế được tính xong để tránh overflow tổng. Ví dụ đơn giá tạo đúng Long.MAX_VALUE cents và số lượng bằng 2 phải bị từ chối tại bước nhân, chứ không được cho ra kết quả âm. Một giá trị Long.MAX_VALUE cents có số lượng 1 và thuế suất 100% bị từ chối tại bước cộng, vì tổng gấp đôi vượt long.

Nếu nghiệp vụ thật sự cần các số lớn hơn long, phải chuyển các toán hạng sang BigInteger **trước khi tính**, thay vì bọc một giá trị long đã tràn bằng BigInteger.

### 5.5. Thuế tính trong BigDecimal và làm tròn đúng một lần

Tiền hàng đã ở dạng cents nguyên. Để tính thuế theo decimal, dùng:

~~~java
BigDecimal.valueOf(subtotal)
        .multiply(taxRate)
        .setScale(0, RoundingMode.HALF_EVEN)
        .longValueExact();
~~~

Đây là mảnh code nằm trong `quote`. `BigDecimal.valueOf(long)` tạo số decimal chính xác từ long. Phép nhân với tỷ lệ thuế cũng chính xác; sau đó mới làm tròn về **số nguyên cents** theo quy tắc đã xác định. `HALF_EVEN` xử lý điểm đúng giữa hai số nguyên bằng cách chọn số nguyên chẵn.

Hai dữ liệu biên quan trọng:

- 5 cents × 10% = **0.5 cents** → làm tròn HALF_EVEN thành **0 cents** (0 là chẵn).
- 15 cents × 10% = **1.5 cents** → thành **2 cents** (2 là chẵn).

Nếu đổi quy tắc sang HALF_UP hoặc DOWN, kết quả ở các điểm biên này có thể khác. Bộ test phải gắn với **chính sách thực tế**, không chỉ kiểm tra phép tính có chạy được.

Một ví dụ tính thuế 7,5% từ 5997 cents: 5997 × 0.075 = 449.775 cents, làm tròn HALF_EVEN tới **450 cents**, tức 4.50. Tổng là 5997 + 450 = 6447 cents, tức 64.47.

### 5.6. Chỉ chuyển về decimal để hiển thị

`money(long cents)` sử dụng:

~~~java
BigDecimal.valueOf(cents, 2).toPlainString()
~~~

Đây là cách tạo biểu diễn decimal có scale 2 từ cents nguyên. Do đó 5997 cents thành 59.97, 450 cents thành 4.50, 0 cents thành 0.00. Chuỗi này dùng dấu chấm thập phân và không kèm mã tiền tệ, chỉ để minh họa cách hiển thị không đánh mất cents.

Nếu hệ thống yêu cầu hiển thị theo locale hay mã tiền tệ, hãy xử lý tại tầng presentation với quy tắc phù hợp; không nên parse lại chuỗi đã format để làm tính toán cốt lõi.

## 6. Bộ kiểm thử: vì sao cần dữ liệu biên thay vì chỉ trường hợp thông thường?

Chỉ test đơn giá 19.99 và số lượng 3 không thể bắt được những lỗi nguy hiểm như overflow, parse chấp nhận cú pháp sai, hoặc làm tròn sai ở đúng nửa bước.

30 case trong chương trình được chia thành các nhóm:

| Nhóm | Case trọng tâm | Điều được kiểm chứng |
| --- | --- | --- |
| Hóa đơn hợp lệ | Bình thường, đơn giá 0, không thuế | Tính subtotal, thuế, tổng |
| Rounding | 0.5 và 1.5 cents | Hai nhánh HALF_EVEN |
| Biên miền số | Long.MAX_VALUE cents | Giá trị vừa miền được chấp nhận |
| Chuyển double → int | 42, Integer.MIN_VALUE, Integer.MAX_VALUE | Giá trị nguyên hữu hạn trong miền |
| Định dạng giá | Âm, 3 chữ số decimal, exponent, dấu phẩy, khoảng trắng, null | Chặn input ngoài hợp đồng |
| Định dạng số lượng | 0, âm, có phần lẻ | Chặn giá trị sai miền hoặc cú pháp |
| Miền thuế | >1, âm, quá 4 chữ số decimal | Chặn tỷ lệ ngoài miền/precision |
| Chuyển đổi bị tràn | Price cents vượt long, quantity vượt int | Không âm thầm mất dữ liệu |
| Tính toán bị tràn | subtotal/tổng vượt long | Math.multiplyExact và Math.addExact |
| Dấu phẩy động | 12.9, NaN, vô cực, quá miền int | Kiểm tra trước khi cast |
| Phép cộng int | Integer.MAX_VALUE + 1 | Math.addExact ném lỗi thay vì wrap |

Đếm case tự động bằng biến `passed` giúp phát hiện việc chương trình chưa chạy đủ số test mong đợi. Nó không thay thế một công cụ test runner chuyên nghiệp, nhưng **chủ động báo lỗi ngay** nếu bất kỳ kỳ vọng nào bị vi phạm.

### Kiểm thử giá trị ngay sát hai phía của biên

Với một miền [min, max], tập dữ liệu nên gồm **min**, **max**, **giá trị ngay bên trong**, và **giá trị ngay ngoài**, nếu kiểu nguồn có biểu diễn phù hợp.

Ví dụ đối với số lượng:

| Đầu vào | Kỳ vọng |
| --- | --- |
| "0" | Không hợp lệ vì số lượng phải >= 1 |
| "1" | Hợp lệ |
| "2147483647" | Giá trị int hợp lệ, nhưng tổng hóa đơn còn có thể overflow |
| "2147483648" | Không thể chuyển chính xác thành int |
| "-1" | Không hợp lệ về cú pháp |
| "1.0" | Không hợp lệ vì quy tắc chỉ nhận chữ số nguyên |

Một dữ liệu có số lượng hợp lệ vẫn có thể tạo tổng vượt long, nên chỉ validate từng trường **không đủ**; phải tiếp tục kiểm tra từng phép tính tạo dữ liệu phái sinh.

## 7. Nhận diện các loại lỗi và thiết kế thông báo

Chương trình minh họa sử dụng:

- `IllegalArgumentException` cho đầu vào không khớp cú pháp hoặc vi phạm miền nghiệp vụ, ví dụ đơn giá âm hay số lượng bằng 0.
- `ArithmeticException` do `intValueExact`, `longValueExact` hoặc `Math.*Exact` ném khi giá trị/kết quả không thể biểu diễn chính xác.

Cả hai cần được nhận diện và chuyển thành thông báo phù hợp tại tầng API hoặc giao diện người dùng. Đừng để exception kỹ thuật kèm dữ liệu nhạy cảm bị trả trực tiếp ra ngoài trong ứng dụng thật.

`rejects(name, expectedType, runnable)` là helper kiểm tra **loại exception kỳ vọng**: nếu thao tác không ném hoặc ném sai loại, case thất bại. Điều này ngăn lỗi viết test kiểu “mọi exception đều được coi là pass”.

Tuy nhiên, chỉ kiểm tra loại exception có thể chưa đủ với phần mềm lớn. Bạn có thể thêm mã lỗi nghiệp vụ cụ thể và xác minh chính xác trường, mã lỗi, thông điệp thích hợp; đừng khóa test vào toàn bộ stack trace vì nó có thể thay đổi khi refactor.

## 8. Phân biệt kiểm thử chuyển đổi kiểu với xử lý tiền

Phương thức `exactInt(double)` trong chương trình là một bài kiểm tra độc lập để tái sử dụng kiến thức về **các phép ép có thể mất dữ liệu**:

~~~java
static int exactInt(double value) {
    if (!Double.isFinite(value) ||
            value < Integer.MIN_VALUE ||
            value > Integer.MAX_VALUE ||
            value != Math.rint(value)) {
        throw new IllegalArgumentException("Not an exact int");
    }
    return (int) value;
}
~~~

Nó từ chối NaN, vô cực, số ngoài miền int và số có phần lẻ. Chỉ khi đã qua tất cả điều kiện mới cast.

Vì sao không kiểm tra sau khi ép?

~~~java
int wrongA = (int) 12.9;        // 12: phần lẻ đã mất
int wrongB = (int) Double.NaN;  // 0: nguồn NaN đã mất
~~~

Giá trị `12` và `0` đều là int hợp lệ, nhưng không chứng minh nguồn là số nguyên tương ứng. Ngay cả việc gán kết quả này sang long sau đó cũng không phục hồi được đầu vào gốc.

Nếu dữ liệu decimal bắt buộc exact ngay từ khi người dùng nhập, không nên đi vòng qua double trước bước này. Nên dùng BigDecimal từ chuỗi và `intValueExact()`.

## 9. Bộ kiểm thử mạnh hơn: các ý tưởng mở rộng có kiểm soát

Bộ 30 case hiện tại chứng minh các nhánh quan trọng, nhưng **không có nghĩa bao phủ mọi đầu vào**. Một hướng mở rộng thích hợp:

### 9.1. Kiểm thử tham số hóa

Thay vì lặp lại câu lệnh cho từng giá, có thể tạo bảng dữ liệu gồm input, kiểu lỗi/kết quả dự kiến và chạy qua từng dòng. Khi chuyển sang JUnit 5, có thể tổ chức kiểm thử tham số hóa qua `@ParameterizedTest` cùng nguồn dữ liệu tương ứng.

### 9.2. Kiểm thử thuộc tính (property-based)

Ví dụ, với mọi đơn giá hợp lệ, số lượng dương và thuế suất 0:

- `subtotal == total` khi tính toán vừa long.
- `tax == 0`.
- `subtotal >= 0` theo miền đầu vào.
- Kết quả ở dạng cents phải là số nguyên long, không tồn tại phần lẻ cents.

Với thuế suất từ 0 đến 1 và subtotal không âm, thuế đã làm tròn không âm; tổng không âm nếu không có overflow. Những thuộc tính này hữu ích hơn một vài mẫu số cụ thể nhưng cần chú ý **loại trừ hoặc kỳ vọng exception ở phép tính overflow**.

### 9.3. Kiểm thử cấu trúc input

Thử null, chuỗi rỗng, Unicode digits nếu hợp đồng chỉ cho ASCII, nhiều dấu chấm, dấu cộng, dấu trừ, dấu phân cách hàng nghìn, số mũ, khoảng trắng ở đầu/cuối và chuỗi cực dài. Một parser có thể chấp nhận nhiều thứ hơn hợp đồng, nên không thể chỉ dựa vào việc tạo được BigDecimal là kết luận input hợp lệ.

### 9.4. Kiểm thử ranh giới làm tròn

Ngoài 0.5 và 1.5 cents, khảo sát các giá trị đúng dưới, đúng tại và đúng trên nửa bước, cùng các trạng thái có chữ số giữ lại chẵn/lẻ. Kiểm tra riêng thời điểm làm tròn: **mỗi dòng hóa đơn trước khi cộng** khác với **cộng các dòng rồi làm tròn toàn bộ**. Không đổi chính sách mà không cập nhật test.

### 9.5. Kiểm thử hiệu năng và tài nguyên

Đo cách hệ thống xử lý danh sách nhiều dòng; giới hạn kích thước input trước khi parse BigInteger/BigDecimal nhằm tránh lạm dụng bộ nhớ/CPU. Test hiệu năng cần môi trường ổn định và không nên trộn trực tiếp vào bộ test đúng-sai có stdout cố định.

## 10. Các lỗi phổ biến được ví dụ này phòng tránh

**Lỗi 1 — Dùng double cho tiền rồi so bằng dấu ==.** Số thập phân như 0.1 không được biểu diễn exact trong binary64. Ví dụ giữ cents long và tính tỷ lệ bằng BigDecimal.

**Lỗi 2 — Đổi số decimal sang int/long bằng cast hoặc intValue().** Có thể cắt phần thập phân hoặc tràn. Mã sử dụng `longValueExact` và `intValueExact`.

**Lỗi 3 — Gán một phép tính đã tràn vào kiểu rộng hơn.** `long x = intA * intB` vẫn có thể tràn int trước khi gán. Mã dùng phép tính long và `Math.multiplyExact`.

**Lỗi 4 — Tin rằng các trường riêng lẻ hợp lệ thì tổng chắc chắn hợp lệ.** Đơn giá bằng Long.MAX_VALUE cents và số lượng 2 tạo overflow ở subtotal. Mỗi phép tính phái sinh cũng cần bảo vệ.

**Lỗi 5 — Làm tròn ở nhiều bước không kiểm soát.** Cần chọn rõ policy và thời điểm làm tròn. Ở đây chỉ làm tròn thuế về cents một lần bằng HALF_EVEN.

**Lỗi 6 — Bỏ qua ranh giới nửa bước.** Test 0.5/1.5 cents giúp phân biệt HALF_EVEN với các mode khác.

**Lỗi 7 — Đồng nhất “parse được” với “đầu vào được phép”.** BigDecimal chấp nhận nhiều cách viết số; app có thể cấm exponent, dấu âm, dấu phẩy hoặc khoảng trắng.

**Lỗi 8 — Bắt mọi exception rồi trả tiền bằng 0.** Dữ liệu không hợp lệ không phải số 0. Nên từ chối có kiểm soát, không biến lỗi thành một giao dịch hợp lệ.

**Lỗi 9 — Chỉ viết happy path.** Bộ test cần cả giá trị hợp lệ tại biên và ngay ngoài biên, NaN/Infinity, overflow, input null và số lượng sai.

**Lỗi 10 — Sửa code rồi chỉ nhìn stdout cuối.** Test nên có assertion độc lập cho subtotal, tax và total. Một tổng đúng tình cờ không đảm bảo các thành phần đúng.

## 11. Bài tập tự thực hành

1. **Thay đổi chính sách giá:** Cho phép chuỗi `1.000` khi giá trị số đổi sang cents vẫn exact. Cập nhật parser và test; phân biệt điều kiện cú pháp với điều kiện giá trị.
2. **Giới hạn nghiệp vụ:** Đặt số lượng tối đa 10.000 thay vì Integer.MAX_VALUE; thêm test 10.000 hợp lệ và 10.001 bị từ chối.
3. **Cấu hình rounding:** Truyền `RoundingMode` vào phương thức quote nhưng chỉ cho phép các mode do nghiệp vụ phê duyệt. Chứng minh trường hợp 0.5 cents thay đổi kết quả khi đổi mode.
4. **Tính nhiều dòng:** Viết hàm cộng nhiều Receipt bằng `Math.addExact`, chọn rõ liệu thuế làm tròn theo từng dòng hay theo tổng.
5. **Phân loại lỗi:** Tạo mã lỗi riêng cho cú pháp, miền giá trị, vượt long và làm tròn không cho phép; viết test xác minh từng loại.
6. **Ngẫu nhiên tái lập:** Tạo dữ liệu test bổ sung bằng một Random với seed cố định, vẫn giữ các case biên viết tay. Dữ liệu ngẫu nhiên không thay thế các phản ví dụ đã biết.
7. **Lưu trữ và hiển thị:** Kiểm tra công cụ format tiền theo locale ở giao diện nhưng vẫn giữ số cents nguyên để tính toán; tránh parse lại chuỗi đã format.

### Hướng giải cho bài nhiều dòng

Giả sử có ba đối tượng Receipt đã tính xong, và chính sách là **thuế được làm tròn theo từng dòng**, thì tổng cộng:

~~~java
long subtotal = 0L;
long tax = 0L;
for (NumericBoundaryLab.Receipt r : receipts) {
    subtotal = Math.addExact(subtotal, r.subtotalCents());
    tax = Math.addExact(tax, r.taxCents());
}
long total = Math.addExact(subtotal, tax);
~~~

Đây là **mảnh code minh họa**, yêu cầu biến `receipts` đã được khai báo trong cùng package/ngữ cảnh truy cập record, và tuân theo chính sách thuế làm tròn từng dòng. Nếu nghiệp vụ quy định chỉ tính thuế trên tổng toàn hóa đơn, thuật toán và các test sẽ khác. Không tự giả định hai cách luôn cho một kết quả.

## 12. Checklist khi chốt ví dụ tích hợp

- Đã định nghĩa rõ **cú pháp input**, **miền nghiệp vụ**, **đơn vị** và **kiểu lưu**?
- Có giữ giá trị nguồn đủ chính xác cho tới khi các kiểm tra xong?
- Những phép chuyển hẹp có dùng các hàm **Exact** hoặc kiểm tra range/phần lẻ?
- Các phép tính có dùng `Math.*Exact` khi kiểu nguyên có thể overflow?
- Có phân biệt rõ **rounding cho phép** với **mất dữ liệu không được phép**?
- Có kiểm tra ngay tại và ngay ngoài giá trị min/max, cũng như điểm giữa làm tròn?
- Có kiểm tra null, chuỗi sai, NaN/Infinity khi đầu vào là kiểu dấu phẩy động?
- Bài test có thật sự thất bại nếu giá trị hoặc loại exception không đúng?
- Test có chạy được bằng lệnh `javac`/`java` trên JDK 17 và cho kết quả xác định?
- Nếu nâng cấp thành ứng dụng sản xuất, đã xem xét giới hạn tài nguyên, thuế/tiền tệ thực tế, lỗi API và khả năng quan sát hệ thống?

**Kết luận:** Một ví dụ số học đúng không chỉ là công thức tính tiền. Nó còn bao gồm **hợp đồng input**, **chuyển đổi chính xác**, **phát hiện overflow**, **rounding minh bạch**, **kiểu dữ liệu phù hợp** và **bộ kiểm thử dữ liệu biên có thể chạy lại**. Chương trình trên chứng minh toàn bộ chuỗi đó trên một bài toán nhỏ, từ chuỗi ban đầu cho tới kết quả cents và 30 case xác minh tự động.
