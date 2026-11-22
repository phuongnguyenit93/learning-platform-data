# Chọn phép toán có kiểm tra theo hợp đồng miền dữ liệu trong Java

## 1. Mục tiêu: đúng phạm vi biểu diễn *và* đúng quy tắc nghiệp vụ

Khi xử lý số nguyên trong Java, **tràn số (integer overflow)** có thể làm kết quả sai mà không phát sinh exception. Với các thao tác dùng cho số tiền, số lượng hàng, hạn mức, dung lượng tệp hoặc bộ đếm bảo mật, một kết quả tràn âm hay quay vòng có thể khiến điều kiện nghiệp vụ bị vượt qua mà hệ thống không nhận ra.

Java cung cấp nhóm phép toán có kiểm tra **`Math.*Exact`**. Chúng trả kết quả nguyên khi biểu diễn được trong `int` hoặc `long`, và ném `ArithmeticException` nếu vượt phạm vi kiểu. Tuy nhiên, **không phải mọi kết quả nằm trong `long` đều hợp lệ theo miền dữ liệu**. Ví dụ một hóa đơn giới hạn 100.000.000 cents mà tổng là 100.000.001 cents: phép cộng không tràn `long`, nhưng vẫn **vi phạm hạn mức nghiệp vụ**.

Vì vậy, “chọn phép toán có kiểm tra theo hợp đồng miền dữ liệu” có nghĩa là:

1. **Xác định miền hợp lệ**: kiểu dữ liệu, đơn vị, dấu âm/dương, khoảng min/max, độ chính xác, có cho phép làm tròn hay không.
2. **Chọn cách biểu diễn**: `int`, `long`, `BigInteger`, `BigDecimal` hoặc một kiểu miền dữ liệu phù hợp.
3. **Chọn phép tính không làm mất giá trị ngoài ý muốn**: `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact`, `toIntExact` hoặc API khác có hợp đồng tương đương.
4. **Kiểm tra giới hạn nghiệp vụ riêng** trước/sau phép tính ở những điểm thích hợp.
5. **Phân biệt các trường hợp thất bại**: input sai, kết quả vượt giới hạn `int/long`, kết quả hợp lệ về số học nhưng vượt hạn mức miền, hoặc phép chia cần quy tắc làm tròn.
6. **Kiểm thử tại ranh giới**: min, max, max+1, 0, số âm, phép nhân lớn, ép kiểu và các trường hợp `Integer.MIN_VALUE`/`Long.MIN_VALUE`.

Các API này **vẫn được hỗ trợ trong Java 17/21/25 và các JDK hiện đại**. Bài sử dụng Java 17+ cho chương trình chạy độc lập, đồng thời chú thích khi một API được thêm ở phiên bản sau.

## 2. Hai loại giới hạn phải được xem độc lập

### 2.1. Giới hạn của kiểu số nguyên Java

| Kiểu | Phạm vi | Hành vi của toán tử thông thường |
| --- | --- | --- |
| `int` | -2.147.483.648 đến 2.147.483.647 | Phép cộng/trừ/nhân tràn sẽ **quay vòng trong 32 bit** |
| `long` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Phép cộng/trừ/nhân tràn sẽ **quay vòng trong 64 bit** |

Số nguyên nguyên thủy sử dụng biểu diễn signed two's complement. Phép cộng/trừ/nhân bằng toán tử `+`, `-`, `*` thường **không ném exception khi tràn**, mà giữ phần bit thấp theo quy tắc Java.

Ví dụ:

~~~java
int next = Integer.MAX_VALUE + 1;
System.out.println(next); // -2147483648
~~~

Nếu dùng:

~~~java
int next = Math.addExact(Integer.MAX_VALUE, 1);
~~~

thì `Math.addExact` ném `ArithmeticException`; không trả về giá trị âm sai.

**Chú ý:** `Math.*Exact` kiểm tra giới hạn **của kiểu toán hạng/phép toán được chọn**. Không có nghĩa phương thức đó biết hạn mức tiền, số lượng, sức chứa của kho hay độ lớn tối đa của một trường API trong ứng dụng.

### 2.2. Giới hạn của hợp đồng miền dữ liệu

Một hệ thống có thể định nghĩa:

| Trường | Ví dụ hợp đồng | Vì sao không thể chỉ dùng `long`? |
| --- | --- | --- |
| `quantity` | Số nguyên 1–1.000.000 | `-5` và `1.000.001` vẫn vừa `int` nhưng không hợp lệ |
| `unitPriceCents` | Số cents không âm | `-1` vừa `long` nhưng không hợp lệ nếu sản phẩm không cho hoàn tiền |
| `invoiceTotalCents` | 0–100.000.000 cents | Tổng 100.000.001 cents không tràn `long` nhưng vượt hạn mức |
| `fileOffset` | Không âm và nằm trong giới hạn file | Giá trị `-1L` hoặc quá cuối file vẫn biểu diễn được |
| `retryCount` | Không âm và tối đa 10 lần | `Math.incrementExact(10)` cho 11, vẫn vi phạm quy tắc |
| `percentage` | 0–100% hoặc basis points 0–10.000 | Phép cộng không tràn số vẫn có thể tạo 125% |

**Hợp đồng miền dữ liệu cần được viết ra** trước khi chọn phép toán. Số tiền hoàn trả, số dư cho phép âm, thuế, ngày tháng và số lượng hàng có thể có quy tắc khác nhau; không tự áp dụng “mọi số đều phải không âm” cho tất cả dự án.

Ví dụ một hàm chỉ nhận số lượng từ 1 đến 1.000.000:

~~~java
static int validateQuantity(int quantity) {
    if (quantity < 1 || quantity > 1_000_000) {
        throw new IllegalArgumentException("quantity outside contract");
    }
    return quantity;
}
~~~

Đây là **mảnh phương thức** có thể đặt trong một class, không phải chương trình chạy độc lập. Nó kiểm tra miền nghiệp vụ, **không phải overflow**.

## 3. Chọn phép toán `Math.*Exact` phù hợp

Những hàm dưới đây là API Java hiện còn áp dụng. Chúng thuộc `java.lang.Math`, không cần import đặc biệt.

| Tình huống | API | Thất bại khi |
| --- | --- | --- |
| Cộng hai số nguyên | `Math.addExact(a,b)` | Tổng vượt `int` hoặc `long` tương ứng |
| Trừ hai số nguyên | `Math.subtractExact(a,b)` | Hiệu ngoài khoảng biểu diễn |
| Nhân hai số nguyên | `Math.multiplyExact(a,b)` | Tích ngoài khoảng biểu diễn |
| Tăng bộ đếm một đơn vị | `Math.incrementExact(value)` | Đang ở `MAX_VALUE` |
| Giảm bộ đếm một đơn vị | `Math.decrementExact(value)` | Đang ở `MIN_VALUE` |
| Đảo dấu | `Math.negateExact(value)` | Giá trị là `MIN_VALUE` |
| Trị tuyệt đối | `Math.absExact(value)` | Giá trị là `MIN_VALUE` |
| Thu hẹp từ long sang int | `Math.toIntExact(longValue)` | Không thể biểu diễn đúng bằng int |
| Chia số nguyên với kiểm tra tràn | `Math.divideExact(x,y)` | Số chia bằng 0 hoặc `MIN_VALUE / -1` tràn |

**Phiên bản cần lưu ý:** nhóm `addExact/subtractExact/multiplyExact/incrementExact/decrementExact/negateExact/toIntExact` có từ Java 8; `absExact` có từ Java 15; `divideExact` có từ Java 18. Do đó ví dụ độc lập nhắm **Java 17** chỉ gọi những API đã có ở Java 17. Nếu muốn dùng `Math.divideExact`, build/runtime phải ở **Java 18+**.

Nhóm này không giống `Math.abs` hoặc `Math.max`:

~~~java
System.out.println(Math.abs(Integer.MIN_VALUE));
// -2147483648, không phải số dương.

Math.absExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

**Không bắt buộc dùng `Exact` tại mọi phép toán.** Dùng nó khi hợp đồng yêu cầu phát hiện tràn. Với thuật toán cố ý thực hiện số học modulo \(2^{32}\) hoặc \(2^{64}\) như một số hàm hash/bit manipulation, wrap-around có thể là hành vi được thiết kế. Điều quan trọng là **chọn có chủ đích**, không để hành vi tràn mặc định quyết định kết quả nghiệp vụ.

### Kết quả `int` hay `long` phụ thuộc overload

~~~java
int count = 2;
int price = 1_500_000_000;

long wrong = price * count; // Nhân int * int trước, rồi mới gán sang long.
long correct = Math.multiplyExact((long) price, (long) count);
System.out.println(correct); // 3000000000
~~~

`wrong` là một `long` nhưng **đã nhận kết quả `int` bị tràn**. Việc gán sang kiểu rộng hơn **sau** phép tính không hồi phục được giá trị đúng. Để nhân trong phạm vi long, cần **widen ít nhất một toán hạng trước khi nhân**, hoặc dùng đúng overload `Math.multiplyExact(long,long)`/`Math.multiplyExact(long,int)`.

**Với phép tính có kết quả nằm trong long nhưng vượt int:** nên tính bằng long và kiểm tra miền nghiệp vụ trên long, thay vì cố dùng `Math.multiplyExact(int,int)` rồi nhận ArithmeticException không cần thiết.

## 4. Quy trình chọn kiểu và phép tính theo hợp đồng

Hãy trả lời lần lượt những câu hỏi sau:

### 4.1. Giá trị có phải **số nguyên thật sự** không?

- **Số lượng, byte count, offset, số sản phẩm, cents theo đơn vị nhỏ nhất**: thường biểu diễn được bằng `int` hoặc `long`.
- **Tiền có phần thập phân, thuế, tỷ lệ, lãi suất, phép chia cần chính sách làm tròn**: cân nhắc `BigDecimal` với scale/rounding rõ ràng.
- **Số nguyên không có cận trên thực tế** hoặc trung gian có thể vượt long: cân nhắc `BigInteger`.
- **Giá trị đo xấp xỉ, khoa học, đồ họa**: `double/float` có thể phù hợp, nhưng phép toán `Math.*Exact` cho integer **không kiểm tra sai số dấu phẩy động**.

### 4.2. Miền hợp lệ có nằm trong `int` không?

Chẳng hạn `quantity` chỉ từ 1 đến 1.000.000: `int` hợp lý. Nhưng tổng phép nhân `quantity × unitPriceCents` có thể vượt `int`, nên **không vì hai toán hạng nhỏ mà chọn kiểu kết quả int**.

Nếu phép tính có khả năng vượt int nhưng vẫn nằm trong long theo hợp đồng, hãy thực hiện phép tính bằng long:

~~~java
long subtotal = Math.multiplyExact(
        unitPriceCents, (long) quantity);
~~~

Đây là mảnh code cần biến đã khai báo. Nó vẫn ném nếu **tích vượt long**, dù đã tránh tràn int.

### 4.3. Miền hợp lệ có chắc chắn nằm trong `long` không?

Nếu mọi giá trị/tổng trung gian đều có cận chứng minh được trong long, `long` kết hợp `Math.*Exact` là lựa chọn đơn giản.

Nếu **kết quả hợp lệ có thể lớn hơn `Long.MAX_VALUE`**, đừng dùng `long` rồi bỏ exception hoặc clamp xuống max. Hãy dùng `BigInteger` hoặc thay đổi đặc tả/đơn vị biểu diễn.

Nếu **chỉ có trung gian vượt long nhưng kết quả cuối vẫn vừa long**, dùng `BigInteger` cho trung gian rồi `longValueExact()` khi chuyển về long, hoặc một thuật toán được chứng minh không tràn. Việc tính trung gian bằng toán tử long trước rồi đổi sang BigInteger **đã quá muộn**.

### 4.4. Phải làm gì khi phép tính thất bại?

Tùy hợp đồng:

| Chính sách | Cách làm | Có thích hợp với tiền/hạn mức? |
| --- | --- | --- |
| **Fail fast** | `Math.*Exact` → `ArithmeticException`, xử lý ở biên phù hợp | Thường **có**, tránh kết quả sai |
| **Từ chối input vượt domain** | Kiểm tra min/max, trả lỗi hợp đồng rõ ràng | Thường **có** |
| **Tính với độ rộng lớn hơn** | `BigInteger`/`BigDecimal` | Khi miền thực sự yêu cầu |
| **Saturation/clamping** | Trả min/max khi vượt mức **theo yêu cầu rõ ràng** | Chỉ khi nghiệp vụ thật sự cho phép; không phải mặc định |
| **Modulo/wrap** | Dùng toán tử/bit width có chủ đích | Không phù hợp với tổng tiền, quota, chứng từ |
| **Rounding decimal** | `BigDecimal.setScale(...,RoundingMode)` | Chỉ khi hợp đồng cho phép làm tròn |

Không có một lựa chọn duy nhất cho tất cả. “Không bị crash” không đồng nghĩa “đúng nghiệp vụ”; trả `0` hoặc `Long.MAX_VALUE` khi overflow có thể nguy hiểm hơn trả lỗi.

## 5. Ví dụ doanh nghiệp: tổng tiền hóa đơn là số nguyên cents

Đặt hợp đồng minh họa:

- Mỗi hóa đơn có **1 đến 1.000 dòng**.
- `quantity` mỗi dòng là **1 đến 1.000.000**.
- `unitPriceCents` là số nguyên **không âm**.
- Tổng cuối `totalCents` không vượt **100.000.000 cents**.
- Mọi phép nhân/cộng phải **không tràn long**.
- Không tự làm tròn; giá trị đã là **cents nguyên**.
- Khi input vi phạm domain, ném `IllegalArgumentException`; khi tràn kiểu máy, `Math.*Exact` ném `ArithmeticException`.
- Đây là **hợp đồng ví dụ**. Ứng dụng cho phép giảm giá/hoàn tiền hoặc có hạn mức khác phải định nghĩa lại quy tắc, không sao chép số cận tùy tiện.

### 5.1. Vì sao chỉ kiểm tra `total <= MAX` là thiếu?

Cách viết dễ sai:

~~~java
long subtotal = unitPriceCents * quantity; // Có thể tràn long.
long total = previousTotal + subtotal;      // Có thể tràn long.
if (total > MAX_INVOICE_CENTS) {
    throw new IllegalArgumentException("invoice limit");
}
~~~

Đây là **mảnh code phản diện**. Nếu phép toán trước đó đã tràn, `total` có thể trở thành số âm hoặc số nhỏ giả, khiến so sánh hạn mức không bắt được vi phạm.

Cách phù hợp hơn:

~~~java
long subtotal = Math.multiplyExact(
        unitPriceCents, (long) quantity);
long nextTotal = Math.addExact(previousTotal, subtotal);
if (nextTotal > MAX_INVOICE_CENTS) {
    throw new IllegalArgumentException("invoice limit");
}
~~~

Kiểm tra **tràn kiểu** và **giới hạn nghiệp vụ** là **hai bước độc lập**. Nếu hợp đồng không cho số âm, cần kiểm tra điều đó **trước khi nhân/cộng**.

### 5.2. Chương trình Java 17+ hoàn chỉnh

Tạo file **`CheckedDomainArithmeticDemo.java`** (UTF-8). Mã dưới đây đã biên dịch/chạy trên OpenJDK 24 với `--release 17`.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;

public class CheckedDomainArithmeticDemo {
    private static final long MAX_INVOICE_CENTS = 100_000_000L;

    record Line(long unitPriceCents, int quantity) { }

    static long totalCents(List<Line> lines) {
        if (lines == null || lines.isEmpty() || lines.size() > 1_000) {
            throw new IllegalArgumentException("line count");
        }

        long total = 0L;
        for (Line line : lines) {
            if (line == null || line.unitPriceCents() < 0
                    || line.quantity() < 1 || line.quantity() > 1_000_000) {
                throw new IllegalArgumentException("invalid line");
            }

            long subtotal = Math.multiplyExact(
                    line.unitPriceCents(), (long) line.quantity());
            total = Math.addExact(total, subtotal);

            if (total > MAX_INVOICE_CENTS) {
                throw new IllegalArgumentException("invoice limit");
            }
        }
        return total;
    }

    static void expectFailure(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=UNEXPECTED_SUCCESS");
        } catch (ArithmeticException exception) {
            System.out.println(name + "=ARITHMETIC");
        } catch (IllegalArgumentException exception) {
            System.out.println(name + "=DOMAIN");
        }
    }

    public static void main(String[] args) {
        System.out.println("valid-total=" + totalCents(
                List.of(new Line(1_250, 2), new Line(350, 3))));

        expectFailure("domain-excess", () ->
                totalCents(List.of(new Line(100_000_001L, 1))));
        expectFailure("machine-overflow", () ->
                totalCents(List.of(new Line(Long.MAX_VALUE, 2))));

        System.out.println("wrap=" + (Integer.MAX_VALUE + 1));
        expectFailure("int-add-overflow", () ->
                Math.addExact(Integer.MAX_VALUE, 1));
        expectFailure("abs-min", () ->
                Math.absExact(Integer.MIN_VALUE));
        expectFailure("narrow-overflow", () ->
                Math.toIntExact(3_000_000_000L));

        System.out.println("widen-first=" +
                Math.multiplyExact((long) 1_500_000_000, 2L));
        System.out.println("big-product=" +
                BigInteger.valueOf(Long.MAX_VALUE)
                    .multiply(BigInteger.TWO));
        System.out.println("exact-cents=" +
                new BigDecimal("12.34")
                    .movePointRight(2).longValueExact());
        expectFailure("fractional-cent", () ->
                new BigDecimal("12.345")
                    .movePointRight(2).longValueExact());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 CheckedDomainArithmeticDemo.java
java CheckedDomainArithmeticDemo
~~~

**Đầu ra đã kiểm chứng trên OpenJDK 24:**

~~~text
valid-total=3550
domain-excess=DOMAIN
machine-overflow=ARITHMETIC
wrap=-2147483648
int-add-overflow=ARITHMETIC
abs-min=ARITHMETIC
narrow-overflow=ARITHMETIC
widen-first=3000000000
big-product=18446744073709551614
exact-cents=1234
fractional-cent=ARITHMETIC
~~~

### 5.3. Phân tích từng kết quả

**Hóa đơn hợp lệ:**

- Dòng một: `1.250 × 2 = 2.500` cents.
- Dòng hai: `350 × 3 = 1.050` cents.
- Tổng `2.500 + 1.050 = 3.550` cents, dưới giới hạn.
- `Math.multiplyExact` và `Math.addExact` đều hoàn tất; đầu ra `valid-total=3550`.

**Vượt hạn mức domain:** `100.000.001 × 1` vẫn nằm rất xa `Long.MAX_VALUE` nên không gây machine overflow. Nhưng nó lớn hơn `MAX_INVOICE_CENTS` và sinh `IllegalArgumentException`, vì vậy `domain-excess=DOMAIN`.

**Tràn kiểu máy:** `Long.MAX_VALUE × 2` không vừa long nên `Math.multiplyExact` ném `ArithmeticException`. Vì vậy `machine-overflow=ARITHMETIC`; không có một “số tiền đã wrap” nào được dùng làm tổng.

**Vượt int:** `Integer.MAX_VALUE + 1` với toán tử Java thông thường wrap thành `-2147483648`. `Math.addExact` phát hiện trường hợp đó và báo `ARITHMETIC`.

**Trị tuyệt đối:** `Integer.MIN_VALUE` không có giá trị dương tương ứng trong `int`. `Math.absExact` ném thay vì trả một giá trị âm sai.

**Ép kiểu:** `3.000.000.000L` vừa long nhưng không vừa int. `Math.toIntExact` ném thay vì cắt bit.

**Nhân trong long:** một toán hạng được đổi thành long **trước khi nhân**, nên `1.500.000.000 × 2 = 3.000.000.000` đúng.

**Trung gian lớn:** `BigInteger` biểu diễn `Long.MAX_VALUE × 2` thành số nguyên 18.446.744.073.709.551.614 mà không wrap long.

**Tiền thập phân:** `"12.34"` chuyển thành `1.234` cents nguyên. `"12.345"` chuyển thành `1.234,5` cents, không phải cents nguyên. `longValueExact()` từ chối phần lẻ bằng `ArithmeticException`. **Không được diễn giải mọi `ArithmeticException` là integer overflow**: ở trường hợp này lỗi là **mất phần thập phân**, còn ở phép nhân long là **tràn phạm vi**.

### 5.4. Ý nghĩa và giới hạn của bộ kiểm thử

Hàm `expectFailure` cố ý in nhãn **ARITHMETIC** hoặc **DOMAIN** để chứng minh phân nhánh. Đây là helper **dành cho demo**, không phải API error handling hoàn chỉnh cho production. Code thực nên dùng thông báo lỗi có ngữ cảnh an toàn, log nguyên nhân đúng mức và không tự nuốt exception.

Không kiểm thử bằng chuỗi tiếng Anh cụ thể từ `ArithmeticException.getMessage()`; message không phải hợp đồng ổn định cho mọi triển khai/JDK. Nên assert **loại lỗi, trạng thái, bất biến và hành vi**.

## 6. Phân biệt kiểm tra đầu vào, kiểm tra overflow và kiểm tra đầu ra

Một phép tính an toàn thường có trình tự:

~~~text
Input từ API/database/file
    |
    v
Xác nhận hợp đồng: đơn vị, không null, miền min/max
    |
    v
Chọn kiểu biểu diễn và phép tính đủ rộng
    |
    v
Tính bằng Math.*Exact / BigInteger / BigDecimal
    |
    v
Kiểm tra giới hạn kết quả của domain
    |
    v
Chuyển đổi/ghi dữ liệu (nếu cần, dùng *Exact)
~~~

Nếu phép tính cần trung gian lớn hơn long, phải **chọn BigInteger từ trước**. Nếu đã dùng `long a*b` bị tràn, chuyển số đó sang BigInteger sau không sửa được.

### 6.1. Đầu vào sai khác overflow

Ví dụ một số lượng `-2` không tràn int; nó chỉ sai vì contract không cho phép lượng âm. Hàm kiểm tra nên dùng `IllegalArgumentException` hoặc một lỗi validation phù hợp.

### 6.2. Arithmetic overflow khác vượt hạn mức

Một tổng bằng `100_000_001L` là số long hoàn toàn hợp lệ. Nếu domain chỉ chấp nhận đến `100_000_000L`, hãy từ chối có lý do riêng.

**Không viết điều kiện**:

~~~java
if (total < 0) {
    // Chắc chắn đã overflow?
}
~~~

Một tổng âm có thể là dữ liệu **hợp lệ** trong domain cho số dư có nợ, hoặc là kết quả từ input âm mà ứng dụng quên validate. Ngược lại, **overflow cũng có thể tạo ra số dương**, không chỉ âm. Kiểm tra dấu không thể thay thế cho `Math.*Exact`.

### 6.3. Kiểm tra ngay trong chuỗi cộng dồn

Với hàng nghìn dòng, mỗi bước `Math.addExact(total, subtotal)` cần giữ nguyên tính chính xác. Nếu dùng cộng thông thường rồi chỉ kiểm tra tổng ở cuối, các giá trị trung gian có thể wrap trước đó.

Trong domain **chỉ cho phép số không âm**, sau mỗi phép cộng có thể kiểm tra luôn hạn mức domain để dừng sớm. Với domain cho phép số âm và bù trừ, không được dùng cùng cách chặn “tổng tạm vượt max” mà không xem lại đặc tả của phép tính/điều kiện giao dịch.

## 7. Khi nào chọn int, long, BigInteger hay BigDecimal?

| Loại dữ liệu | Ưu tiên | Cần chú ý |
| --- | --- | --- |
| Số lượng nhỏ có min/max đã rõ | `int` | Kiểm tra miền; tổng hoặc tích có thể cần long |
| Số tiền theo **đơn vị nhỏ nhất nguyên** với cận rõ | `long` + `Math.*Exact` | Dùng đúng currency scale; không vượt domain cap |
| Offset, size, timestamp count lớn | `long` + kiểm tra tràn/miền | Không ép về int trước khi kiểm tra |
| Số nguyên không có cận long hợp lệ | `BigInteger` | Dù không có fixed-width overflow như long, vẫn giới hạn CPU/memory và domain |
| Giá, thuế, lãi suất, tỷ lệ cần decimal | `BigDecimal` + scale/rounding policy | Quy tắc làm tròn phải rõ; tránh double không cần thiết |
| Bộ đếm hash/cyclic/bit-mask có modulo cố ý | `int/long` với wrap có chủ đích | Cần ghi rõ modulus; không áp logic đó cho tiền/quota |

### Một contract có thể bảo đảm kiểu nhỏ luôn đủ

Nếu một phép nhân có hai toán hạng bị giới hạn ở `0..1_000`, tích tối đa là 1.000.000 và chắc chắn vừa int. Trong trường hợp đó, phép nhân int thường là toán học an toàn theo chứng minh miền, không bắt buộc gọi `multiplyExact` ở mọi chỗ.

Tuy nhiên, thêm `multiplyExact` ở ranh giới nhạy cảm có thể bảo vệ code khi contract thay đổi hoặc validation bị bỏ sót. Quyết định dựa vào **yêu cầu tính đúng, độ tin cậy của invariant và kiểm thử thực tế**, không chỉ sở thích viết cú pháp.

### Mỗi đơn vị cần gắn với một kiểu/hợp đồng rõ

Không nên nhân trực tiếp giá trị “12.34 dollars” kiểu `double` với số cents mà không chuyển đổi. Tương tự, cộng “milliseconds” vào biến đang giữ “nanoseconds” có thể sai cả khi `Math.addExact` không báo overflow.

Với dữ liệu thời gian, ưu tiên những kiểu như `Duration`/`Instant` khi phù hợp; với tiền, cân nhắc một value object hoặc record có tên field chỉ rõ đơn vị `amountCents`, currency và các invariant.

**Kiểu số học không tự chứng minh rằng hai biến cùng đơn vị.**

## 8. Bẫy thu hẹp kiểu và phép nhân trước khi widen

Một bug phổ biến:

~~~java
int unitPriceCents = 1_500_000_000;
int quantity = 2;

// Sai: phép nhân được tính theo int trước khi chuyển sang long.
long alreadyOverflowed = unitPriceCents * quantity;

// Đúng nếu miền cho phép tích dưới Long.MAX_VALUE.
long accurate = Math.multiplyExact(
        (long) unitPriceCents, (long) quantity);
~~~

Giải thích cụ thể:

- Trong phép toán int × int, **binary numeric promotion** giữ kết quả trong int.
- Biến bên trái có kiểu `long` không thay đổi kiểu phép toán đã diễn ra bên phải.
- Ép kiểu **sau** phép nhân như `(long)(a * b)` không giúp lấy lại số đã mất.
- Ép kiểu **trước** phép nhân như `(long)a * b` giúp thực hiện nhân trong long, nhưng nếu hợp đồng vẫn có thể vượt long, dùng `Math.multiplyExact` để kiểm tra.
- Nếu phép toán có kiểu `int` và hợp đồng yêu cầu kết quả cũng là int, dùng `Math.multiplyExact(int,int)` trực tiếp.

Có một API `Math.multiplyFull(int,int)` (Java 9+) trả tích toán học đầy đủ của hai int dưới dạng long. Nó có ích khi kết quả có thể vượt int nhưng luôn vừa long. Tuy nhiên khi thao tác từ dữ liệu đã là long, hãy dùng overload exact tương ứng.

### Ví dụ về chia số trước hay sau khi nhân

Giả sử tính toán `(a*b)/c`. Dù kết quả cuối cùng có thể vừa long, tích `a*b` có thể vượt `Long.MAX_VALUE`. Nếu dùng `Math.multiplyExact` thì **nó phải ném đúng**, không phải “quá nghiêm”.

Khi cần tính hợp lệ mà trung gian vượt long, dùng `BigInteger` rồi chuyển về long **chỉ sau khi đã kiểm tra kết quả**:

~~~java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(3_000_000_000L);
BigInteger b = BigInteger.valueOf(3_000_000_000L);
BigInteger c = BigInteger.valueOf(3_000_000_000L);

BigInteger product = a.multiply(b);
BigInteger[] qr = product.divideAndRemainder(c);

if (!qr[1].equals(BigInteger.ZERO)) {
    throw new ArithmeticException("non-integral quotient");
}

long result = qr[0].longValueExact(); // 3000000000
~~~

Đây là **mảnh code minh họa**, không cần có mặt trong class demo. Dùng `divideAndRemainder` để phát hiện trường hợp phép chia không cho **số nguyên chính xác**. Một lời gọi `BigInteger.divide(c)` đơn lẻ có thể **bỏ phần dư**, tùy yêu cầu. `longValueExact()` chỉ kiểm tra kết quả đã rút về có vừa long không.

## 9. Chia số nguyên: trường hợp đặc biệt dễ bỏ sót

Cần biết rằng toán tử chia nguyên có một dạng tràn khác cộng/trừ/nhân.

Trong Java:

~~~java
int result = Integer.MIN_VALUE / -1;
System.out.println(result); // -2147483648, KHÔNG ném exception.
~~~

Kết quả toán học là `2147483648`, không vừa int. Theo Java Language Specification, **trường hợp riêng `MIN_VALUE / -1` trả chính `MIN_VALUE` mà không ném exception**. Ngược lại, chia nguyên cho 0 ném `ArithmeticException`.

**Từ Java 18**, có thể dùng:

~~~java
int quotient = Math.divideExact(x, y);
~~~

Đây là **mảnh code Java 18+**, không được chèn vào ví dụ mục 5 nhắm Java 17. Phương thức ném `ArithmeticException` nếu chia cho 0 hoặc quotient overflow. Tài liệu hiện hành còn cung cấp `Math.floorDivExact` và `Math.ceilDivExact` (Java 18+) cho các quy tắc làm tròn khác của phép chia nguyên.

Nếu buộc hỗ trợ Java 17, có thể tự chặn trường hợp tràn của `int`:

~~~java
static int checkedDivision17(int x, int y) {
    if (y == 0) {
        throw new ArithmeticException("division by zero");
    }
    if (x == Integer.MIN_VALUE && y == -1) {
        throw new ArithmeticException("integer division overflow");
    }
    return x / y;
}
~~~

Đây là mảnh phương thức Java 17 hợp lệ; với `long` áp dụng cùng nguyên tắc cho `Long.MIN_VALUE / -1L`.

**`divideExact` không có nghĩa thương luôn không có phần dư.** Chẳng hạn `7 / 2` theo phép chia nguyên bằng `3` và không overflow; `Math.divideExact(7,2)` cũng trả **3** ở Java 18+. Nếu contract yêu cầu chia hết, **kiểm tra phần dư riêng**:

~~~java
if (x % y != 0) {
    throw new ArithmeticException("non-integral result");
}
int result = checkedDivision17(x, y);
~~~

Đây là mảnh sử dụng giả định `y != 0` đã được kiểm tra; muốn chắc chắn, gọi hàm checked division trước rồi kiểm tra dư, hoặc tự guard y trước. Không diễn giải tên “Exact” là “số học hữu tỉ có vô hạn độ chính xác”.

## 10. Chuyển đổi hẹp cũng phải có hợp đồng

### 10.1. Long sang int

~~~java
long rowCount = 3_000_000_000L;

int wrong = (int) rowCount; // Cắt bớt bit, giá trị sai.
int checked = Math.toIntExact(rowCount); // ArithmeticException.
~~~

`Math.toIntExact` rất phù hợp ở ranh giới API chỉ nhận `int`: chỉ số buffer, tham số method legacy, cột SQL kiểu 32 bit hoặc chiều dài array. Không ép kiểu chỉ để làm biến vừa signature.

**Chú ý:** kiểm tra tràn số không tự chứng minh index hợp lệ. Một `long offset=100` chuyển sang int chính xác vẫn có thể vượt chiều dài mảng 50; cần kiểm tra `0 <= index < length` riêng.

### 10.2. BigInteger/BigDecimal sang primitive

~~~java
import java.math.BigInteger;
import java.math.BigDecimal;

long a = new BigInteger("123456789").longValueExact();
long b = new BigDecimal("1200.00").longValueExact();
~~~

Hai ví dụ chuyển đổi trên không mất phần giá trị (BigDecimal có phần thập phân chỉ gồm zeros). Trái lại:

- `new BigInteger("999999999999999999999").longValueExact()` ném nếu vượt long.
- `new BigDecimal("1.5").longValueExact()` ném do mất phần lẻ.
- `new BigDecimal("1.5").longValue()` có thể trả 1, tức **bỏ phần lẻ**, không phù hợp khi contract yêu cầu chính xác.

Nếu một API đầu ra chỉ nhận `int`/`long`, hãy chuyển bằng `*ValueExact()` và xử lý lỗi rõ thay vì ép cắt số.

## 11. Giá trị tiền, scale và chính sách làm tròn

Một hợp đồng tiền tệ thường khó hơn kiểm tra integer overflow vì có **đơn vị, currency, số chữ số thập phân và làm tròn**.

### 11.1. Dùng long cents khi miền tiền đã quy về số nguyên

Nếu API chỉ nhận số cents nguyên, dữ liệu có thể được lưu bằng long kèm cap. Điều kiện:

- Currency có quy tắc decimal scale phù hợp với đơn vị “cents” của hệ thống (không phải mọi currency đều có 2 decimal places).
- Nguồn dữ liệu không được tự làm tròn.
- Đơn giá, số lượng và tổng đều có cận được kiểm tra.
- Tất cả các phép cộng/trừ/nhân dùng width đúng và có kiểm tra nếu có nguy cơ tràn.

### 11.2. Nhận giá trị decimal từ API

~~~java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("12.34");
long cents = amount.movePointRight(2).longValueExact();
// cents == 1234
~~~

Nếu nhập `"12.345"` thì dịch phải hai chữ số cho kết quả `1234.5`, không thể chuyển thành long cents nguyên mà không mất mát; `longValueExact()` ném `ArithmeticException`.

Điều này **khác** tràn `long`. Nó báo giá trị có độ chính xác không phù hợp với **hợp đồng số cents nguyên**.

### 11.3. Nếu nghiệp vụ *cho phép* làm tròn

Một hợp đồng khác có thể cho phép hai chữ số thập phân với `RoundingMode.HALF_EVEN` hoặc `HALF_UP`. Khi đó phải viết rõ chính sách:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal rounded =
        new BigDecimal("12.345")
            .setScale(2, RoundingMode.HALF_EVEN);
// Với HALF_EVEN, số 12.345 trở thành 12.34.
~~~

Đây là **mảnh code**. Quy tắc HALF_EVEN ở trường hợp đúng giữa hai kết quả lựa chọn chữ số cuối chẵn; tổ chức có thể yêu cầu một phương thức khác theo chuẩn kế toán/thuế.

**Đừng đưa một `RoundingMode` vào code chỉ để ngăn exception.** Quy tắc làm tròn là quyết định nghiệp vụ, không phải cách khắc phục lỗi một cách tùy tiện. Với hợp đồng **không cho làm tròn**, dùng `RoundingMode.UNNECESSARY`/`longValueExact()` để từ chối dữ liệu không đúng.

### 11.4. Vì sao không dùng double cho tiền cần chính xác decimal?

Số thực IEEE 754 kiểu `double` thường không thể biểu diễn chính xác nhiều phân số thập phân. `Math.addExact` **không có overload cho double** và không phát hiện sai số dấu phẩy động.

Nếu giao thức yêu cầu số thập phân chính xác, ưu tiên truyền giá trị ở dạng **chuỗi thập phân có hợp đồng rõ**, tạo `BigDecimal(String)` hoặc truyền long theo đơn vị nhỏ nhất. Không tạo `new BigDecimal(double)` từ một giá trị double đã mang sai số rồi nghĩ rằng precision được phục hồi.

## 12. Lựa chọn overflow, wrap, clamp hay BigInteger theo mục đích

### 12.1. Exact/fail fast: tính toán an toàn

Ứng dụng billing, inventory, account quota, financial reconciliation, file size/offset hoặc security counter thường nên **từ chối phép tính không biểu diễn được** và báo rõ trường hợp dữ liệu không hợp lệ.

~~~java
long next = Math.addExact(current, delta);
if (next > maximumAllowed) {
    throw new IllegalArgumentException("domain limit");
}
~~~

Nếu domain cho phép số âm, cần kiểm tra thêm **minAllowed** theo hợp đồng. `Math.addExact` không tự biết khoảng nghiệp vụ.

### 12.2. Wrap-around: chỉ khi hợp đồng định nghĩa modulo

Một số thuật toán bit manipulation, checksum hoặc hash có thể cố ý dùng phép toán modulo \(2^{32}\). Khi đó **wrap có thể là một phần thuật toán**. Cần ghi chú rõ và viết test xác nhận kết quả theo đặc tả, không copy code này sang tiền/quota.

### 12.3. Saturation/clamp: phải được định nghĩa *trước*

Trong đo lường hoặc UI progress indicator, có thể có hợp đồng “mọi giá trị vượt 100 chỉ hiển thị là 100”. Đây là saturation của **giá trị hiển thị**, không nhất thiết là cách lưu trữ dữ liệu gốc.

Không làm:

~~~java
// Sai nếu phép cộng đã tràn trước khi clamp:
long displayed = Math.min(100L, current + delta);
~~~

Nếu `current + delta` đã overflow, việc `Math.min` sau đó không cứu được dữ liệu.

Muốn saturation, cần **kiểm tra trước khi cộng** (cẩn thận cả dấu âm) hoặc tính bằng `BigInteger` rồi so với giới hạn trước khi chuyển kiểu. Quan trọng hơn, phải xác nhận hợp đồng thật sự cho phép mất phần vượt giới hạn.

### 12.4. BigInteger không có nghĩa không giới hạn tài nguyên

`BigInteger` không wrap ở 32/64 bit theo kiểu `int/long`, nhưng phép toán vẫn dùng CPU, bộ nhớ và có giới hạn triển khai. Với input không tin cậy, cần giới hạn:

- Số chữ số/độ dài chuỗi đầu vào.
- Số lượng phép toán, độ lớn của phép lũy thừa.
- Độ dài dữ liệu trung gian và timeout/budget xử lý.
- Quy tắc miền nghiệp vụ sau phép tính.

**BigInteger không thay thế validation.** Nếu hợp đồng chỉ cho tổng tối đa 100.000.000 cents, dùng BigInteger rồi chấp nhận 10^50 cents vẫn sai nghiệp vụ.

## 13. Hợp đồng đồng thời: AtomicLong vẫn có thể tràn

Trong một hệ thống có nhiều threads, nhiều phép `Math.addExact` trên biến long thông thường **không tự trở thành atomic**.

Ví dụ phản diện:

~~~java
long current = balance;
long updated = Math.addExact(current, delta);
balance = updated; // Có thể lost update nếu nhiều threads cùng truy cập.
~~~

Nếu `balance` được dùng chung giữa threads, việc đọc/tính/ghi cần đồng bộ. Một lựa chọn Java hiện hành là `AtomicLong.updateAndGet`:

~~~java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong used = new AtomicLong();
long maximumAllowed = 1000L;
long delta = 10L;

long updated = used.updateAndGet(current -> {
    long next = Math.addExact(current, delta);
    if (next < 0 || next > maximumAllowed) {
        throw new IllegalArgumentException("quota outside contract");
    }
    return next;
});
~~~

Đây là **mảnh code hợp lệ trong một phương thức**. Callback của `updateAndGet` có thể bị gọi **nhiều lần khi CAS phải retry**, nên hàm cập nhật phải **không tạo side effects** (không gửi email, ghi hóa đơn, đặt hàng hoặc tăng counter khác bên trong callback).

`AtomicLong.addAndGet(delta)` có atomicity cho update nhưng **không tự kiểm tra overflow**: nó vẫn dùng số học long. Nếu contract cần vừa atomic vừa checked, kết hợp như trên hoặc thiết kế lock/transaction phù hợp.

Đối với tài khoản tiền trong hệ thống phân tán, `AtomicLong` trong một JVM **không thể thay thế** database transaction, kiểm soát đồng thời liên tiến trình và quy tắc nhất quán của hệ thống.

## 14. Input từ JSON, database hoặc văn bản

Một chương trình có thể làm đúng mọi phép `Math.*Exact` nhưng vẫn nhận dữ liệu sai từ đầu vào:

- Chuỗi `"999999999999999999999"` vượt long khi parse bằng `Long.parseLong`.
- Chuỗi `"-5"` vừa long nhưng có thể sai contract số lượng không âm.
- JSON integer được client xử lý qua một kiểu floating-point có thể đã mất độ chính xác trước khi server nhận.
- Database column `INT` không chứa được một long hợp lệ nếu không kiểm tra khi ghi.
- Một trường không có đơn vị rõ gây nhầm **đồng/cents**, **seconds/milliseconds** hoặc **bytes/KiB**.

**Phân biệt các tầng lỗi:**

| Tầng | Vấn đề | Nên kiểm tra bằng |
| --- | --- | --- |
| Parse | Chuỗi không phải số hợp lệ hoặc quá độ rộng của `long` | `Long.parseLong`, `NumberFormatException`, schema validation |
| Domain | Giá trị âm, vượt min/max, sai scale hoặc currency | Hàm validation theo hợp đồng |
| Computation | Phép cộng/trừ/nhân không vừa int/long | `Math.*Exact` |
| Conversion | Chuyển `long→int` hoặc `BigDecimal→long` mất thông tin | `Math.toIntExact`, `*ValueExact()` |
| Persistence | DB/file/protocol không giữ được giá trị | Kiểu column, serialization và round-trip tests |

Đừng sửa một `NumberFormatException` do input quá lớn bằng cách **parse thành double rồi cast về long**; điều đó có thể gây mất giá trị. Chọn schema và kiểu dữ liệu phù hợp ngay từ biên.

## 15. Xử lý lỗi ở ranh giới API và trong hệ thống

Một contract tốt quy định cả **đầu ra thành công lẫn kết quả khi thất bại**.

Ví dụ API nhận số lượng:

- Không phải số, thiếu trường, quá 1.000.000, hoặc số âm: trả **lỗi validation** theo giao thức API (ví dụ HTTP 400/422 tùy hợp đồng), không tạo hóa đơn.
- Một phép tính bất ngờ vượt giới hạn của long: **không ghi kết quả đã wrap**. Có thể là dấu hiệu dữ liệu đầu vào không giới hạn đủ chặt, lỗi logic hoặc thay đổi yêu cầu; ghi log có kiểm soát, chuyển về mã lỗi phù hợp.
- Tổng hợp lệ kiểu máy nhưng vượt cap: trả **lỗi domain** rõ ràng.
- Hệ thống cần hỗ trợ giá trị thực sự lớn hơn long: nâng contract và kiểu lưu trữ, không giả lập bằng cách nuốt `ArithmeticException`.

Ví dụ:

~~~java
try {
    long total = Math.addExact(current, amount);
    validateTotal(total);
    save(total);
} catch (ArithmeticException overflow) {
    // Không lưu giá trị sai. Ghi lỗi/đổi thành lỗi domain
    // tại ranh giới phù hợp, không tự chọn total = 0.
}
~~~

Đây là **mảnh code minh họa**: `validateTotal` và `save` cần được ứng dụng định nghĩa. Trong service thật, cần bảo đảm **không ghi trạng thái một phần** trước khi validation/thao tác tính toán hoàn thành; dùng transaction nếu nhiều thay đổi phải cùng thành công/thất bại.

Không dựa trên chuỗi tiếng Anh của `ArithmeticException.getMessage()` để quyết định logic API. Phần mềm có thể thay đổi JDK, ngôn ngữ và công cụ log; điều nên kiểm thử là exception type và invariant.

**Không dùng `assert` làm validation đầu vào**: Java assertions thường bị tắt trong production nếu không bật `-ea`; hơn nữa lỗi dữ liệu đầu vào khác với một assertion về invariant nội bộ.

## 16. Kiểm thử theo biên và thuộc tính

Một số unit tests quan trọng cho hợp đồng “hóa đơn 1–1000 dòng, quantity 1–1.000.000, total ≤100.000.000 cents”:

| Ca | Input minh họa | Kết quả mong đợi |
| --- | --- | --- |
| Tính hợp lệ | 1250×2 + 350×3 | 3550 cents |
| Bằng đúng giới hạn | 100.000.000×1 | Thành công |
| Vượt giới hạn một cent | 100.000.001×1 | Lỗi domain |
| Giá âm | -1×1 | Lỗi validation |
| Quantity bằng 0 | 100×0 | Lỗi validation |
| Quantity quá lớn | 100×1.000.001 | Lỗi validation |
| Dòng null | `List.of` không cho null; tạo list khác có null | Lỗi validation |
| Danh sách rỗng | `List.of()` | Lỗi validation |
| Quá 1.000 dòng | 1.001 dòng | Lỗi validation |
| Tràn long khi nhân | `Long.MAX_VALUE × 2` | `ArithmeticException` |
| Tràn int khi cộng | `Integer.MAX_VALUE + 1` | `ArithmeticException` với addExact |
| Hẹp long→int | `3_000_000_000L` | `ArithmeticException` với toIntExact |
| Trị tuyệt đối cực âm | `Integer.MIN_VALUE` | `ArithmeticException` với absExact |
| Cents nguyên | `"12.34"` | 1234 |
| Cents lẻ | `"12.345"` | `ArithmeticException` với longValueExact |

### Test ranh giới chứ không chỉ ví dụ nhỏ

Đặc biệt nên kiểm tra:

1. `minAllowed-1`, `minAllowed`, `minAllowed+1`.
2. `maxAllowed-1`, `maxAllowed`, `maxAllowed+1`.
3. `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, `Long.MAX_VALUE`.
4. Biên **số lần lặp** và số lượng bản ghi.
5. Nhiều phép toán ghép chuỗi, đặc biệt multiplication rồi aggregation.
6. Kết quả tính toán **có độ rộng vừa đủ nhưng domain không cho**.
7. Dữ liệu từ JSON/database cần chuyển kiểu.

### Property-based testing

Với những cặp `a,b` bất kỳ mà tổng toán học vừa int, `Math.addExact(a,b)` phải bằng kết quả toán học. Nếu tổng không vừa, nó phải ném. Có thể dùng `BigInteger` làm **oracle tham chiếu** để so sánh trong tests.

Ví dụ ý tưởng:

~~~java
BigInteger exact = BigInteger.valueOf(a)
        .add(BigInteger.valueOf(b));
if (exact.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) >= 0
        && exact.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) <= 0) {
    int expected = exact.intValueExact();
    int actual = Math.addExact(a, b);
    // So sánh expected và actual bằng test framework.
} else {
    // Test framework phải xác nhận Math.addExact(a,b) ném
    // ArithmeticException, không chấp nhận silent wrap.
}
~~~

Đây là **mảnh code hướng dẫn kiểm thử**, yêu cầu import `BigInteger` và biến `a,b` kiểu int. Không tạo “test chỉ pass” bằng cách bắt exception rồi im lặng; dùng assertion thật của framework hoặc kiểm tra giá trị bất biến.

## 17. Những lỗi phổ biến cần tránh

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Số vừa long thì luôn hợp lệ.” | Còn có hạn mức domain, đơn vị, dấu âm và scale. |
| “`Math.addExact` kiểm tra giá trị tổng tiền tối đa.” | Nó chỉ kiểm tra overflow long/int, không biết cap doanh nghiệp. |
| “Gán kết quả int multiplication vào long sẽ cứu overflow.” | Phép nhân int đã xảy ra trước việc gán. |
| “`(long)(a*b)` đủ an toàn.” | Nếu `a,b` đều int, nó cast sau khi đã nhân/tràn. |
| “Chỉ kiểm tra `result < 0` là đủ.” | Overflow có thể tạo giá trị dương hoặc âm; âm đôi khi hợp lệ theo domain. |
| “`Math.abs(Integer.MIN_VALUE)` luôn dương.” | Nó trả chính MIN_VALUE; cần `absExact` khi cần phát hiện. |
| “`Math.divideExact` có trên Java 17.” | Có từ Java 18; cần guard thủ công hoặc dùng JDK mới hơn. |
| “`divideExact(7,2)` phát hiện phần lẻ.” | Nó trả 3 theo phép chia nguyên; kiểm tra dư riêng. |
| “`Math.toIntExact` kiểm tra index hợp lệ.” | Chỉ kiểm tra giá trị vừa int; vẫn phải so với length. |
| “BigInteger giải quyết mọi vấn đề.” | Vẫn có domain cap, input budget, CPU/memory và giới hạn hệ thống. |
| “BigDecimal không bao giờ ném ArithmeticException.” | Có thể ném khi chia không biểu diễn chính xác, mất phần lẻ hoặc vượt range/scale. |
| “Bắt ArithmeticException rồi trả 0 là chống lỗi.” | Có thể làm sai dữ liệu/ẩn sự cố; xử lý theo contract. |
| “Clamp sau `a+b` sẽ ngăn overflow.” | Phép cộng có thể đã tràn trước khi clamp. |
| “`AtomicLong.addAndGet` có checked arithmetic.” | Update atomic nhưng số học vẫn wrap nếu vượt long. |
| “`BigDecimal("12.345")` có thể chuyển long cents không mất mát.” | 12.345 đơn vị = 1234.5 cents; phải từ chối hoặc chọn rounding policy. |
| “Nâng JDK là không còn cần Math.*Exact.” | Các API vẫn là lựa chọn hữu ích; hợp đồng domain vẫn do ứng dụng quyết định. |
| “Validation bằng `assert` hoạt động mọi lúc.” | Assertions có thể bị tắt; không dùng thay input validation. |
| “Chỉ cần test giá trị nhỏ.” | Bug overflow thường ở biên max/min và chuỗi phép tính. |

## 18. Checklist khi chọn phép toán có kiểm tra

1. **Ý nghĩa:** trường dữ liệu là số lượng, tiền, dung lượng, offset, tỷ lệ hay bộ đếm?
2. **Đơn vị:** cents, đơn vị tiền chính, milliseconds, bytes, KiB… có thống nhất không?
3. **Miền:** có cho số âm, zero, null, min/max và bao nhiêu phần tử không?
4. **Kiểu:** `int/long` có đủ cho **mọi trung gian**, không chỉ đầu ra?
5. **Phép tính:** cộng/trừ/nhân/tăng/giảm/đổi dấu/chuyển kiểu cần `Math.*Exact` nào?
6. **Phiên bản:** method dùng có mặt trên JDK target (`absExact` từ 15, `divideExact` từ 18) không?
7. **Widening:** đã thực hiện trước phép nhân, không phải sau overflow, chưa?
8. **Độ chính xác:** phép chia có cần phát hiện remainder? Decimal cần rounding policy nào?
9. **Domain cap:** đã check hạn mức riêng sau phép tính đã checked chưa?
10. **Lỗi:** input không hợp lệ, tràn kiểu và domain excess được phân biệt đúng chưa?
11. **Persistence:** database/file/API có chứa được kết quả không? Narrowing đã dùng `*Exact` chưa?
12. **Concurrency:** dữ liệu dùng chung có cần atomic update và invariant đồng thời không?
13. **Bảo mật:** input cực lớn có giới hạn độ dài/CPU/memory không? Lỗi có gây lộ dữ liệu không?
14. **Tests:** có min/max, max±1, số âm, zero, huge product và rounding không?
15. **Hành vi đặc biệt:** nếu yêu cầu modulo/saturation, đã viết thành contract tường minh chưa?

## 19. Bài tập tự luyện và đáp án

### Bài 1 — Khi tổng không tràn long nhưng vượt hạn mức

Hóa đơn giới hạn `100_000_000` cents. Tổng phép cộng chính xác được `100_000_001L`. Có nên trả thành công vì `Math.addExact` không ném?

**Đáp án:** không. `Math.addExact` chỉ kiểm tra long overflow. Kết quả vượt **hạn mức miền** và phải bị từ chối theo contract.

### Bài 2 — Widen trước khi nhân

~~~java
int a = 1_500_000_000;
int b = 2;
long result = a * b;
~~~

**Câu hỏi:** có thu được `3_000_000_000L` không?

**Đáp án:** không. `a*b` là int multiplication nên overflow trước khi được gán vào long. Sửa bằng `Math.multiplyExact((long)a, (long)b)`.

### Bài 3 — Chọn BigInteger

Một tích `Long.MAX_VALUE*2` là giá trị hợp lệ theo hợp đồng biểu diễn số nguyên rất lớn. Có nên catch `Math.multiplyExact` rồi trả `Long.MAX_VALUE`?

**Đáp án:** không. Dùng `BigInteger.valueOf(Long.MAX_VALUE).multiply(BigInteger.TWO)` từ đầu để lấy **18446744073709551614**. Cần giới hạn tài nguyên nếu có input rất lớn.

### Bài 4 — Phép chia có phần dư

Ở Java 18+, `Math.divideExact(7,2)` có ném không?

**Đáp án:** không, trả 3. “Exact” ở đây là kiểm tra **tràn số nguyên**, không bảo đảm thương là số nguyên toán học không có phần dư. Nếu hợp đồng cần chia hết, kiểm tra `7 % 2`.

### Bài 5 — Trị tuyệt đối của int cực âm

Chạy `Math.abs(Integer.MIN_VALUE)` và `Math.absExact(Integer.MIN_VALUE)`. Vì sao khác?

**Đáp án:** giá trị `2147483648` không biểu diễn được trong int; `abs` trả giá trị âm `MIN_VALUE`, còn `absExact` ném `ArithmeticException`.

### Bài 6 — Tiền có ba chữ số decimal

API chỉ chấp nhận cents nguyên nhưng nhận `"12.345"`. Nên chuyển bằng `movePointRight(2).longValue()`?

**Đáp án:** không nếu hợp đồng cấm làm tròn hoặc mất phần lẻ. Dùng `longValueExact()` để từ chối, hoặc xác định `RoundingMode` bằng chính sách nghiệp vụ rồi mới chuyển.

### Bài 7 — Bộ đếm dùng chung

Một service tăng quota bằng `AtomicLong.addAndGet(delta)`. Nó có phát hiện overflow hoặc cap nghiệp vụ?

**Đáp án:** không. Nó bảo đảm atomic update nhưng arithmetic vẫn có thể wrap; dùng `updateAndGet` với `Math.addExact` và domain check trong lambda thuần, hoặc thiết kế transaction/lock thích hợp.

### Bài 8 — Thiết kế test của riêng bạn

Viết unit tests cho `totalCents`:

- Giá trị đúng **bằng** `MAX_INVOICE_CENTS` phải thành công.
- Giá trị **vượt đúng một cent** phải báo domain.
- `Long.MAX_VALUE × 2` phải báo arithmetic overflow.
- `quantity=0` và `quantity=1_000_001` phải báo validation.
- Không một đường thất bại nào được ghi hóa đơn có số tiền đã wrap.

### Bài 9 — Kết quả cuối vừa long nhưng trung gian không vừa

Bạn cần tính `(3_000_000_000 × 3_000_000_000) / 3_000_000_000`, kết quả là 3 tỷ. Tại sao không nên tính tích bằng long trước?

**Đáp án:** tích là 9×10^18 (nằm trong long), nên trong **chính ví dụ này** nó *vẫn vừa* long. Tuy nhiên nếu thay hai toán hạng thành giá trị lớn hơn `Long.MAX_VALUE` tại phép nhân, phép nhân long sẽ tràn. Cần tính biên trung gian **cho giá trị thật**, không suy từ kết quả cuối; khi trung gian có thể vượt long, dùng BigInteger hoặc biến đổi công thức đã chứng minh. (Bài 8 có ví dụ BigInteger để thực hành thiết kế dự phòng.)

## 20. Tài liệu chính thức hiện còn áp dụng

- [Oracle Java 25 — Math API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact`, `multiplyExact`, `absExact`, `divideExact`, `toIntExact` và thông tin `Since`.
- [Oracle Java 17 — Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): xác định những phương thức dùng được ngay trên Java 17.
- [Oracle Java 25 — BigInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigInteger.html): số nguyên tùy độ dài, `multiply`, `divideAndRemainder`, `longValueExact` và giới hạn tài nguyên.
- [Oracle Java 25 — BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, `movePointRight`, `setScale`, `longValueExact`, cách chọn rounding mode.
- [Oracle Java 25 — RoundingMode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html): các quy tắc làm tròn không còn dùng int constants legacy.
- [Java Language Specification 25 — Integer operations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.2): overflow đối với số nguyên và ý nghĩa kiểu.
- [Java Language Specification 25 — Division operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.17.2): trường hợp đặc biệt `MIN_VALUE / -1` và chia cho 0.
