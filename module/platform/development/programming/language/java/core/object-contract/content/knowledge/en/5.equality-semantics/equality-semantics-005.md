# Chuẩn hóa dữ liệu trước khi so sánh trong Java

## 1. Vì sao cần chuẩn hóa?

Khi xác định **quan hệ bằng nhau** giữa hai đối tượng Java, ta cần trả lời trước: “Hai cách biểu diễn khác nhau này có được xem là cùng một giá trị theo nghiệp vụ không?”. Câu trả lời phụ thuộc vào loại dữ liệu và mục đích so sánh.

Ví dụ:

- `"  Alice "` và `"alice"` có thể là cùng một **tên đăng nhập** nếu hệ thống quy định bỏ khoảng trắng đầu/cuối và không phân biệt chữ hoa/thường; nhưng với một mật khẩu, hai chuỗi đó **không** nên bị tự động xem là như nhau.
- `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có cùng giá trị số, nhưng `BigDecimal.equals()` trả `false` vì khác `scale`.
- Hai cách mã hóa Unicode như `"é"` (ký tự dựng sẵn) và `"e\u0301"` (chữ e cộng dấu kết hợp) có thể trông giống nhau, nhưng `String.equals()` trực tiếp sẽ trả `false` nếu chuỗi mã điểm khác nhau.
- `2026-01-01T00:00:00Z` và `2026-01-01T07:00:00+07:00` biểu diễn cùng một thời điểm tuyệt đối; nếu bài toán quan tâm “cùng thời điểm”, nên so biểu diễn đã chuyển thành `Instant` thay vì so chuỗi gốc.

**Chuẩn hóa (normalization/canonicalization)** là biến đổi biểu diễn đầu vào theo **quy tắc đã chọn**, tạo ra một dạng chuẩn (canonical form) để những biểu diễn được phép xem là tương đương trở thành cùng một giá trị so sánh.

Một mô hình thường gặp:

```text
Dữ liệu gốc A ──chuẩn hóa N──► N(A) ─┐
                                   ├── so sánh theo giá trị ──► bằng/khác
Dữ liệu gốc B ──chuẩn hóa N──► N(B) ─┘
```

Ở đây `N` phải là quy tắc của chính miền dữ liệu. Không có một hàm chuẩn hóa chung áp dụng đúng cho mọi chuỗi, số, tiền tệ, thời gian hay định danh.

## 2. Chọn quan hệ bằng nhau trước khi chọn phép biến đổi

Phải xác định điều gì **có ý nghĩa về mặt nghiệp vụ**:

| Miền dữ liệu | Ví dụ quan hệ bằng nhau | Cần cẩn trọng |
| --- | --- | --- |
| Username cho phép không phân biệt hoa/thường | `" ALICE "` và `"alice"` có thể coi là một, nếu chính sách cho phép bỏ khoảng trắng và không phân biệt hoa/thường | Quy tắc Unicode và ký tự hợp lệ phải được công bố, ổn định. |
| Mật khẩu/bí mật | Chỉ bằng nhau theo cơ chế xác minh mật khẩu đã thiết kế | Không tự `trim()`, hạ chữ hay bỏ dấu làm mất thông tin người dùng. |
| Mã sản phẩm, mã kho | Tùy đặc tả: có thể cần giữ nguyên hoa/thường và số 0 đầu | `"00012"` không mặc nhiên là `"12"`. |
| Số thập phân mang ý nghĩa giá trị số | `1.0` và `1.00` bằng nhau nếu chỉ xét trị số | `BigDecimal.equals()` phân biệt `scale`; trị số và độ chính xác biểu diễn có thể khác ý nghĩa. |
| Số tiền | Cùng giá trị **và** cùng đơn vị tiền tệ | `100 VND` khác `100 USD`; không chỉ so phần số. |
| Thời gian sự kiện | Hai đầu vào cùng `Instant` | Không đánh đồng “cùng giờ địa phương” với “cùng thời điểm”. |
| Định danh đã cấp phát | Thường phải trùng định danh theo hệ thống phát hành | Không tùy tiện bỏ dấu phân cách, số 0 đầu, tiền tố. |

Trong Java, chuẩn hóa **không tự động** xảy ra khi dùng `==` hay `equals()`:

- `==` giữa hai tham chiếu kiểm tra **danh tính đối tượng**, hoàn toàn không chuẩn hóa nội dung.
- `String.equals()` so chuỗi theo đơn vị ký tự UTF-16 một cách phân biệt hoa/thường và không tự chuẩn hóa Unicode.
- `Objects.equals(a, b)` chỉ giúp so an toàn với `null`; khi cả hai không null, nó gọi `a.equals(b)`.
- Lớp tự định nghĩa `equals()` có thể so theo dạng chuẩn nếu đó là một phần hợp đồng bằng nhau của lớp.

Kết luận thiết kế cần rõ ràng: **chuẩn hóa chỉ được áp dụng khi đó là ý nghĩa đã chọn của quan hệ bằng nhau**.

## 3. Một dạng chuẩn tốt cần những tính chất nào?

### 3.1. Nhất quán và xác định

Cùng đầu vào, cùng chính sách phải cho cùng dạng chuẩn. Không nên để `equals()` phụ thuộc vào ngôn ngữ mặc định của máy, thời điểm hiện tại, cấu hình thay đổi ngẫu nhiên hay dữ liệu có thể biến đổi từ bên ngoài.

### 3.2. Có tính ổn định khi áp dụng lại

Thông thường mong muốn tính **idempotent**:

```text
N(N(x)) = N(x)
```

Ví dụ, một tên đăng nhập đã được loại khoảng trắng hai đầu, chuyển chữ thường và chuẩn hóa NFC thì xử lý lại theo cùng quy tắc không nên tiếp tục thay đổi kết quả. Quy tắc phải được kiểm chứng với tập đầu vào mà hệ thống chấp nhận.

### 3.3. Không hợp nhất những giá trị phải phân biệt

Nếu `N(a) == N(b)` thì hệ thống sẽ có xu hướng coi `a` và `b` bằng nhau. Điều đó chỉ đúng khi nghiệp vụ thực sự cho phép. Ví dụ, tự bỏ mọi dấu tiếng Việt có thể đánh đồng những tên hoặc mã khác nhau; tự xóa mọi khoảng trắng có thể biến `"A B"` thành `"AB"` dù đó là hai định danh độc lập.

Đây là thay đổi **ngữ nghĩa**, không phải công việc làm đẹp chuỗi.

### 3.4. Xử lý dữ liệu không hợp lệ và null rõ ràng

Xác định trước liệu đầu vào `null`, chuỗi rỗng hoặc chỉ chứa khoảng trắng có được chấp nhận. Có thể từ chối ngay trong constructor bằng `Objects.requireNonNull` và `IllegalArgumentException`. Nếu đầu vào có thể `null`, cần quy định null là thiếu dữ liệu hay một giá trị đặc biệt; không lặng lẽ chuyển `null` thành `""` nếu hai trạng thái mang ý nghĩa khác nhau.

### 3.5. Bảo toàn hợp đồng `equals` và `hashCode`

Nếu một lớp so sánh theo `canonicalValue` thì phải tính `hashCode()` theo **cùng các thành phần chuẩn hóa**.

```text
a.equals(b) == true  ⇒  a.hashCode() == b.hashCode()
```

Chiều ngược lại không bắt buộc vì mã hash có thể trùng nhau. Đồng thời, các thành phần dùng để so sánh và tạo hash nên **bất biến trong thời gian đối tượng được sử dụng làm khóa** trong `HashMap` hoặc phần tử của `HashSet`.

## 4. Chuẩn hóa chuỗi: phải quyết định từng bước

### 4.1. Bỏ khoảng trắng ở biên

- `String.trim()` chỉ loại các ký tự đầu/cuối có mã không vượt quá U+0020.
- `String.strip()` (Java 11+) xét khoảng trắng theo `Character.isWhitespace`, thường thích hợp hơn cho nhiều loại văn bản Unicode; tuy vậy **không xử lý tất cả ký tự trông giống dấu cách**, ví dụ một số ký tự no-break space.
- Không tự xóa hoặc gộp khoảng trắng **ở giữa** chuỗi nếu nghiệp vụ chưa quy định. `"Van An"` khác `"VanAn"` trong nhiều hệ thống.

### 4.2. Chữ hoa và chữ thường

`toLowerCase(Locale.ROOT)` hữu ích khi quy tắc định danh cần hạ chữ **không phụ thuộc locale mặc định** của môi trường. Dùng `toLowerCase()` không đối số có thể dẫn tới thay đổi theo locale máy chạy, đặc biệt với những trường hợp như chữ I trong tiếng Thổ Nhĩ Kỳ.

Tuy nhiên, hạ chữ bằng `Locale.ROOT` **không phải full Unicode case folding** cho mọi ngôn ngữ; việc so khớp tên người, chuỗi tìm kiếm theo ngôn ngữ tự nhiên hay chuẩn giao thức có thể cần quy tắc riêng (`Collator`, chuẩn Unicode tương ứng hoặc thư viện chuyên dụng).

### 4.3. Unicode normalization

`java.text.Normalizer` hỗ trợ:

- **NFC:** dạng canonical composition; thường hữu ích khi muốn các cách biểu diễn Unicode tương đương về chuẩn tắc so bằng nhau.
- **NFD:** dạng canonical decomposition.
- **NFKC/NFKD:** dạng compatibility normalization, có thể gộp thêm những ký tự chỉ khác về cách biểu diễn tương thích; đây là thay đổi mạnh hơn, có thể làm mất phân biệt có ý nghĩa.

Ví dụ với username cho phép không phân biệt hoa/thường và chấp nhận các biểu diễn Unicode canonical-equivalent:

```java
static String normalizeHandle(String input) {
    String trimmed = input.strip();
    String lowered = trimmed.toLowerCase(java.util.Locale.ROOT);
    return java.text.Normalizer.normalize(
            lowered, java.text.Normalizer.Form.NFC);
}
```

Đoạn trên là **hàm minh họa**, được lồng vào chương trình đầy đủ ở phần 6. Thứ tự các phép biến đổi là một phần chính sách và cần giữ nhất quán ở mọi đường nhập, truy vấn và cập nhật dữ liệu. Chỉ áp dụng khi ứng dụng đã chọn chính sách username này; nó không phải thuật toán chuẩn hóa toàn diện cho email, URL hay tên người.

**Lưu ý bảo mật:** NFC không loại bỏ các ký tự nhìn giống nhau nhưng khác mã Unicode (confusables), và cũng không tự bảo vệ trước mọi trường hợp giả mạo tên. Hệ thống danh tính cần chính sách ký tự được phép và kiểm tra uniqueness phù hợp.

## 5. Chuẩn hóa các kiểu dữ liệu khác

### 5.1. `BigDecimal`: trị số và scale

`BigDecimal` lưu trị số thập phân cùng `scale`:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

// a.equals(b) => false: khác scale
// a.compareTo(b) == 0 => true: cùng trị số
```

Đây là đoạn minh họa cần `import java.math.BigDecimal;`. Nếu quan hệ bằng nhau mong muốn **chỉ so trị số**, có thể:

1. So trực tiếp bằng `a.compareTo(b) == 0` tại nơi cần quan hệ bằng nhau về số.
2. Tạo canonical value bằng `stripTrailingZeros()` rồi dùng `equals()/hashCode()` trên dạng chuẩn trong một value object.

`stripTrailingZeros()` có thể tạo dạng biểu diễn theo lũy thừa của 10, ví dụ từ `600.0` thành dạng có scale âm; đừng dựa vào chuỗi in ra để đánh giá. Với số không, có thể quy về `BigDecimal.ZERO`. Không tự làm tròn trước so sánh nếu quy tắc miền dữ liệu không cho phép; làm tròn có thể gộp những giá trị vốn phải khác nhau.

### 5.2. Số thực `double` và sai số

Không đưa mặc định quy tắc “`Math.abs(a-b) < epsilon`” vào `equals()` của value object: kiểu gần bằng nhau này có thể **không bắc cầu**. Chẳng hạn với `epsilon = 0.1`, `a = 0.00` gần `b = 0.06` và `b` gần `c = 0.12`, nhưng `a` không gần `c`. Điều đó vi phạm hợp đồng `equals`.

Nếu bài toán yêu cầu dung sai, hãy dùng một phương thức mang tên riêng như `approximatelyEqual(a, b, tolerance)` cho thuật toán số; hoặc thiết kế phép lượng tử hóa theo ranh giới cố định nếu **thực sự** muốn quan hệ bằng nhau dạng nhóm. Khi so số thực, cũng cần xác định quy tắc cho `NaN` và `-0.0` vì `Double.equals()` có ngữ nghĩa riêng so với `==` trên primitive.

### 5.3. Ngày và giờ

Nếu yêu cầu là “cùng thời điểm trên dòng thời gian”, chuyển thông tin có offset/zone sang `Instant`:

```java
Instant a = OffsetDateTime.parse(
        "2026-01-01T00:00:00Z").toInstant();
Instant b = OffsetDateTime.parse(
        "2026-01-01T07:00:00+07:00").toInstant();

// a.equals(b) => true
```

Đoạn minh họa trên cần `import java.time.Instant;` và `import java.time.OffsetDateTime;`. Trái lại, lịch hẹn “9 giờ sáng tại Hà Nội” hay một `LocalDate` có thể cần so theo ngày/giờ địa phương, không nhất thiết theo `Instant`. Không tự áp timezone khi chưa hiểu dữ liệu gốc.

### 5.4. Định danh và dữ liệu có định dạng riêng

Với số điện thoại, email, URL, đường dẫn tệp, mã khách hàng hoặc mã quốc tế, các biến đổi “trông hợp lý” có thể tạo sai:

- Email: phần local part và chính sách của nhà cung cấp có những ràng buộc khác nhau; không mặc nhiên xóa dấu chấm hay phần “+tag” cho mọi địa chỉ.
- Số điện thoại: muốn quy về định dạng quốc tế phải biết quốc gia và quy tắc đánh số; xóa hết ký tự không phải chữ số không đủ để xác định số.
- URL/đường dẫn: chữ hoa/thường, dấu slash, percent-encoding, tham số truy vấn hay đường dẫn tương đối có thể thay đổi định danh tài nguyên.
- Mã sản phẩm: dấu gạch, tiền tố, số 0 ở đầu có thể là một phần mã.

Chỉ dùng chuẩn hóa được xác định bởi đặc tả/miền dữ liệu và các thư viện thích hợp.

## 6. Ví dụ Java 17+ chạy độc lập: canonical username và số thập phân

Tạo tệp **`NormalizationEqualityDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.Normalizer;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class NormalizationEqualityDemo {

    static final class UserHandle {
        private final String submitted;
        private final String canonical;

        UserHandle(String submitted) {
            this.submitted = Objects.requireNonNull(
                    submitted, "submitted");
            this.canonical = normalizeHandle(submitted);
            if (canonical.isEmpty()) {
                throw new IllegalArgumentException("Blank handle");
            }
        }

        private static String normalizeHandle(String input) {
            String trimmed = input.strip();
            String lower = trimmed.toLowerCase(Locale.ROOT);
            return Normalizer.normalize(lower, Normalizer.Form.NFC);
        }

        String displayValue() {
            return submitted;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof UserHandle handle)) {
                return false;
            }
            return canonical.equals(handle.canonical);
        }

        @Override
        public int hashCode() {
            return canonical.hashCode();
        }
    }

    static BigDecimal normalizeAmount(BigDecimal input) {
        Objects.requireNonNull(input, "input");
        if (input.signum() == 0) {
            return BigDecimal.ZERO;
        }
        return input.stripTrailingZeros();
    }

    public static void main(String[] args) {
        String decomposed = "  CAFE\u0301  ";
        String composed = "café";

        System.out.println("raw text equal: "
                + decomposed.equals(composed));

        UserHandle first = new UserHandle(decomposed);
        UserHandle second = new UserHandle(composed);
        Set<UserHandle> handles = new HashSet<>();
        handles.add(first);

        System.out.println("same reference: " + (first == second));
        System.out.println("same normalized value: "
                + first.equals(second));
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("set contains second: "
                + handles.contains(second));

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("raw BigDecimal equals: " + a.equals(b));
        System.out.println("numeric compareTo zero: "
                + (a.compareTo(b) == 0));
        System.out.println("canonical BigDecimal equals: "
                + normalizeAmount(a).equals(normalizeAmount(b)));

        System.out.println("null safe equal: "
                + Objects.equals(null, null));
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac NormalizationEqualityDemo.java
java NormalizationEqualityDemo
```

Kết quả chuẩn:

```text
raw text equal: false
same reference: false
same normalized value: true
same hash: true
set contains second: true
raw BigDecimal equals: false
numeric compareTo zero: true
canonical BigDecimal equals: true
null safe equal: true
```

**Vì sao đúng?**

1. `"  CAFE\u0301  "` và `"café"` không giống nhau theo `String.equals()` vì khác khoảng trắng, hoa/thường và cách biểu diễn dấu Unicode.
2. Constructor `UserHandle` chuẩn hóa một lần, lưu `canonical` dưới dạng `final`. Sau `strip()`, hạ chữ với `Locale.ROOT` rồi NFC, cả hai nhận dạng chuẩn `"café"`.
3. Hai lần `new UserHandle(...)` tạo hai đối tượng khác nhau (`==` là `false`), nhưng `equals()` của lớp so `canonical` nên trả `true`.
4. `hashCode()` cũng dựa trên `canonical` nên bằng nhau. Vì vậy `HashSet.contains(second)` trả `true` sau khi thêm `first`.
5. Hai `BigDecimal` cùng trị số nhưng khác scale nên `equals()` trực tiếp trả `false`; `compareTo` và hàm chuẩn hóa `stripTrailingZeros()` thể hiện quy tắc “cùng trị số”.
6. `Objects.equals(null, null)` trả `true`; đây là tiện ích xử lý null chứ không tự chuẩn hóa giá trị.

Trong chương trình, `displayValue()` cho phép giữ dữ liệu người dùng nhập để hiển thị; trong hệ thống thật, có thể lưu cả giá trị gốc và dạng chuẩn cho tìm kiếm/uniqueness. Không nên hiển thị mã chuẩn thay cho bản gốc nếu việc đó làm mất định dạng mà người dùng muốn giữ.

## 7. Nên chuẩn hóa ở đâu trong ứng dụng?

**Tại biên nhập dữ liệu:** đọc, kiểm tra tính hợp lệ và chuyển về dạng chuẩn trước khi tạo value object hay lưu cơ sở dữ liệu. Dạng chuẩn nên bất biến trong đối tượng; `equals()` và `hashCode()` trở nên ngắn gọn, nhanh và nhất quán.

**Tại điểm tra cứu:** chuyển truy vấn bằng **chính cùng quy tắc** đã dùng khi lưu. Nếu lưu username theo dạng NFC + chữ thường nhưng truy vấn theo cách khác, một giá trị hợp lệ có thể không tìm thấy.

**Tại tầng dữ liệu:** đồng bộ quy tắc ứng dụng với unique index, collation hoặc canonical key trong database. `String.equals()` của Java và phép so chuỗi của database có thể có ngữ nghĩa khác; chỉ kiểm tra trùng ở Java mà không có cơ chế nhất quán tại database có thể phát sinh trùng dữ liệu khi có truy cập đồng thời.

**Khi chính sách thay đổi:** phiên bản của phép chuẩn hóa có thể ảnh hưởng dữ liệu cũ, trùng khóa hoặc khả năng đăng nhập. Nếu thay đổi quy tắc Unicode, phân biệt chữ hoa/thường hay cách xử lý khoảng trắng, cần lập kế hoạch chuyển đổi và phát hiện xung đột, thay vì âm thầm thay đổi `equals()`.

### Vì sao không chuẩn hóa lại tùy ý bên trong mỗi lần gọi `equals()`?

Về lý thuyết có thể chuẩn hóa trong `equals()`, nhưng cách đó dễ tốn chi phí, lặp logic và quên đồng bộ `hashCode()`. Nếu phép biến đổi dựa vào locale/config thay đổi theo môi trường hoặc dữ liệu mutable, kết quả bằng nhau và mã hash còn có thể không ổn định. Với đối tượng dùng làm khóa trong collection, nên tính `canonical` một lần theo chính sách cố định trong constructor/nhà máy tạo đối tượng.

## 8. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách làm |
| --- | --- | --- |
| Chỉ `trim()/lowercase` một phía | Hai dữ liệu tương đương có thể vẫn khác | Chuẩn hóa nhất quán cả hai đầu vào hoặc lưu dạng chuẩn. |
| `equals()` so canonical, `hashCode()` dùng chuỗi gốc | Phá hợp đồng hash; `HashSet`/`HashMap` hành xử sai kỳ vọng | Cả hai dùng cùng canonical fields. |
| Dùng `toLowerCase()` không tham số | Kết quả có thể đổi theo locale mặc định | Dùng `Locale.ROOT` nếu nghiệp vụ cần so không phụ thuộc locale. |
| Chọn NFKC hay xóa dấu để “so cho dễ” | Vô tình hợp nhất các giá trị cần phân biệt | Chỉ áp dụng phép biến đổi mà đặc tả cho phép; thử các trường hợp biên. |
| Gộp null và chuỗi rỗng | Mất ý nghĩa “chưa cung cấp” khác với “có cung cấp nhưng rỗng” | Định nghĩa rõ chính sách validation/null. |
| So `BigDecimal.equals()` khi nghiệp vụ chỉ xét trị số | `1.0` và `1.00` bị coi khác nhau | Dùng `compareTo` hoặc canonical amount theo chính sách. |
| Dùng epsilon trong `equals()` | Có thể vi phạm tính bắc cầu | Dùng hàm so gần bằng nhau riêng hoặc lượng tử hóa đã thiết kế. |
| Chỉ kiểm tra unique trên ứng dụng | Hai request đồng thời có thể tạo dữ liệu trùng về ngữ nghĩa | Dùng unique constraint/index phù hợp với canonical key. |
| Sửa giá trị canonical sau khi đưa vào `HashMap` | Không tìm lại được khóa trong bucket dự kiến | Thiết kế immutable value object hoặc khóa bất biến. |

## 9. Tự kiểm tra

**Câu 1.** Nếu hệ thống coi username không phân biệt hoa/thường nhưng mật khẩu phân biệt mọi ký tự, có được áp dụng cùng phép `strip().toLowerCase(Locale.ROOT)` cho cả hai không?

**Đáp án:** Không. Quan hệ bằng nhau do miền dữ liệu quyết định; chuẩn hóa mật khẩu theo quy tắc username có thể đổi ý nghĩa và làm mất thông tin.

**Câu 2.** Vì sao hai đối tượng có `canonical` bằng nhau cần `hashCode()` dựa trên canonical?

**Đáp án:** Vì hợp đồng Java bắt buộc hai đối tượng `equals()` bằng nhau phải có cùng `hashCode()`. Hash collection dựa vào điều này để tra cứu chính xác.

**Câu 3.** `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` trả gì? Nếu chỉ quan tâm trị số, cần so thế nào?

**Đáp án:** `false` vì khác `scale`. Có thể dùng `a.compareTo(b) == 0` hoặc so canonical BigDecimal theo quy tắc đã chọn.

**Câu 4.** Chuẩn hóa Unicode NFC có làm mọi cặp ký tự trông giống nhau trở thành bằng nhau không?

**Đáp án:** Không. NFC xử lý tương đương Unicode theo chuẩn tắc, không xử lý mọi ký tự nhìn giống nhau hay mọi yêu cầu so khớp ngôn ngữ.

**Câu 5.** Có thể sử dụng `Math.abs(a - b) < 0.1` làm triển khai chung của `Object.equals()` cho mọi số thực không?

**Đáp án:** Không. Quan hệ gần bằng nhau có thể không bắc cầu, vi phạm hợp đồng `equals()`.

**Ghi nhớ:** **Xác định ngữ nghĩa bằng nhau trước; chuẩn hóa theo đúng ngữ nghĩa ấy; bảo đảm `equals()` và `hashCode()` sử dụng cùng dạng chuẩn bất biến.**