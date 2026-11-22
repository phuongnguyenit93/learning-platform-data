# Kiểm tra, chuẩn hóa dữ liệu tại constructor

## 1. Constructor là ranh giới bảo vệ trạng thái object

Constructor không chỉ gán tham số vào field. Nó là thời điểm một object được tạo và bắt đầu tham gia vào chương trình. Nếu object đại diện cho một khái niệm trong domain, các trạng thái không hợp lệ cần bị từ chối ngay khi tạo object.

Ví dụ, một tài khoản có thể yêu cầu:

- Mã tài khoản không được null hoặc rỗng.
- Mã được chuẩn hóa về dạng chữ hoa để so sánh nhất quán.
- Tên hiển thị không được chỉ chứa khoảng trắng.
- Hạn mức không được âm.
- Danh sách nhãn không được chứa phần tử null.
- Dữ liệu mảng truyền vào không được để caller sửa đổi trạng thái nội bộ sau khi constructor trả về.

Nếu constructor chỉ gán giá trị mà không bảo vệ các điều kiện này, object có thể tồn tại trong trạng thái sai. Những lỗi đó thường xuất hiện muộn hơn, ở một method không liên quan trực tiếp tới nơi dữ liệu được nhập.

Một constructor tốt giúp object tuân thủ **invariant** ngay từ lúc được tạo. Invariant là tập điều kiện luôn phải đúng đối với một instance hợp lệ trong suốt vòng đời của nó.

Trong Java 17, việc kiểm tra và chuẩn hóa dữ liệu tại constructor thường kết hợp:

- `Objects.requireNonNull` để từ chối tham số bắt buộc bị null.
- `IllegalArgumentException` để từ chối giá trị không hợp lệ.
- Các phép chuẩn hóa tường minh như `strip()`, `toUpperCase(Locale.ROOT)` và Unicode normalization.
- Defensive copy cho collection và array mutable.
- Constructor delegation để tập trung invariant ở một nơi.
- Compact constructor của record khi dùng record làm data carrier.

## 2. Phân biệt validation và normalization

### 2.1. Validation: dữ liệu có đáp ứng contract không?

Validation kiểm tra một giá trị có nằm trong miền được phép hay không. Ví dụ:

- Mã sản phẩm có đúng định dạng không?
- Số lượng có lớn hơn 0 không?
- Ngày kết thúc có sau ngày bắt đầu không?
- Danh sách chi tiết có rỗng không?
- Một trạng thái có nằm trong tập trạng thái được hỗ trợ không?

Nếu giá trị không hợp lệ, constructor từ chối tạo object:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException(
            "quantity must be greater than zero"
    );
}
```

### 2.2. Normalization: đưa dữ liệu về một dạng biểu diễn thống nhất

Normalization chuyển các đầu vào tương đương về một dạng chuẩn theo contract của domain. Ví dụ:

- Loại bỏ khoảng trắng ở đầu/cuối mã.
- Chuẩn hóa Unicode về NFC.
- Đưa mã không phân biệt hoa thường về chữ hoa với `Locale.ROOT`.
- Sao chép collection để object sở hữu snapshot riêng.

Ví dụ:

```java
String normalizedCode = rawCode.strip().toUpperCase(Locale.ROOT);
```

Sau khi chuẩn hóa, constructor vẫn phải validation. Không phải mọi giá trị đều trở nên hợp lệ chỉ vì đã được chuyển thành dạng chuẩn.

### 2.3. Thứ tự xử lý thường dùng

Một luồng đơn giản:

```text
Constructor arguments
        |
        v
Check required references for null
        |
        v
Normalize representation
        |
        v
Validate format, range and cross-field rules
        |
        v
Defensively copy mutable input
        |
        v
Assign fields
        |
        v
Valid object
~~~

Có thể thay đổi thứ tự copy/normalize tùy kiểu dữ liệu, nhưng cần bảo đảm constructor không để lọt reference mutable của caller vào object.

### 2.4. Không biến normalization thành sửa dữ liệu âm thầm

Không nên tự động biến một giá trị sai thành một giá trị khác nếu domain chưa định nghĩa quy tắc đó.

Ví dụ, nếu số lượng âm là sai, không tự đổi:

```java
this.quantity = Math.max(0, quantity);
```

Cách này biến lỗi đầu vào thành số 0 và có thể che giấu bug của caller. Hãy từ chối bằng exception, trừ khi contract nghiệp vụ thực sự yêu cầu clamp giá trị.

Tương tự, không tự cắt tên người dùng quá dài, làm tròn tiền hoặc xóa ký tự lạ nếu chưa có quy tắc nghiệp vụ rõ ràng.

## 3. Chọn exception cho dữ liệu không hợp lệ

### 3.1. Null bắt buộc: NullPointerException

Với một tham số bắt buộc phải có, `Objects.requireNonNull` là cách diễn đạt rõ:

```java
this.name = Objects.requireNonNull(name, "name must not be null");
```

Nếu `name` null, constructor ném `NullPointerException` với message đã cung cấp.

Đây là contract của API: caller phải cung cấp một reference. Việc dùng NPE ở đây giúp phân biệt trường hợp thiếu reference với một giá trị tồn tại nhưng sai nội dung.

### 3.2. Giá trị tồn tại nhưng sai: IllegalArgumentException

Ví dụ:

```java
if (name.isBlank()) {
    throw new IllegalArgumentException("name must not be blank");
}
~~~

Tên là một String hợp lệ về kiểu nhưng nội dung không đáp ứng contract. `IllegalArgumentException` thể hiện rằng caller truyền đối số không được phép.

Các ví dụ khác:

```java
if (age < 0) {
    throw new IllegalArgumentException("age must not be negative");
}

if (endDate.isBefore(startDate)) {
    throw new IllegalArgumentException(
            "endDate must not be before startDate"
    );
}
~~~

### 3.3. Domain exception khi cần thêm ngữ nghĩa

Một domain có thể định nghĩa exception riêng nếu caller cần xử lý lỗi theo loại nghiệp vụ:

```java
public final class InvalidAccountCodeException
        extends IllegalArgumentException {

    public InvalidAccountCodeException(String message) {
        super(message);
    }
}
~~~

Không cần tạo một exception class riêng cho mọi điều kiện nhỏ. Chỉ tạo khi tên lỗi hoặc metadata bổ sung giúp API dễ sử dụng và xử lý.

### 3.4. Message cần chỉ rõ tham số và điều kiện

Message tốt:

```text
creditLimit must be zero or greater
accountCode must match [A-Z0-9-]{3,20}
endDate must not be before startDate
~~~

Message kém hữu ích:

```text
Invalid input
Bad value
Something went wrong
~~~

Không đưa mật khẩu, token, thông tin cá nhân nhạy cảm hoặc toàn bộ payload vào exception message/log. Tên tham số và quy tắc vi phạm thường đủ để caller biết cách sửa.

## 4. Kiểm tra null và chuỗi rỗng

### 4.1. requireNonNull

```java
String code = Objects.requireNonNull(rawCode, "rawCode");
~~~

Đoạn này chỉ kiểm tra null. Nó không từ chối chuỗi rỗng hoặc chuỗi chỉ chứa khoảng trắng.

### 4.2. isEmpty và isBlank

| Method | Ý nghĩa |
|---|---|
| `isEmpty()` | Chuỗi có độ dài bằng 0 |
| `isBlank()` | Chuỗi rỗng hoặc chỉ gồm các ký tự được Java nhận diện là whitespace |
| `strip()` | Trả chuỗi mới sau khi loại bỏ whitespace ở hai đầu theo quy tắc Unicode của Java |
| `trim()` | API cũ hơn, chỉ xử lý tập ký tự có code point không lớn hơn U+0020 |

Trong code Java 17, `strip()` và `isBlank()` thường phù hợp hơn `trim()` khi contract cần xử lý whitespace Unicode.

Ví dụ:

```java
String value = Objects.requireNonNull(rawValue, "rawValue");
String normalized = value.strip();

if (normalized.isEmpty()) {
    throw new IllegalArgumentException(
            "rawValue must not be blank"
    );
}
~~~

### 4.3. Tạo helper dùng chung

```java
private static String requireText(String value, String name) {
    Objects.requireNonNull(value, name + " must not be null");

    String normalized = value.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException(
                name + " must not be blank"
        );
    }
    return normalized;
}
~~~

Helper này phù hợp với các trường cần text không rỗng và muốn bỏ khoảng trắng hai đầu. Không dùng nó cho mọi String một cách máy móc: password, token, chữ ký hoặc dữ liệu mà whitespace có ý nghĩa cần giữ nguyên.

### 4.4. Blank khác với chuỗi chỉ có dấu phân cách

Ví dụ `"---"` không blank, nhưng có thể không phải mã hợp lệ. `isBlank()` chỉ kiểm tra whitespace; format validation vẫn cần quy tắc riêng.

## 5. Chuẩn hóa mã định danh

### 5.1. Dùng Locale.ROOT cho mã không phụ thuộc ngôn ngữ

Nếu mã tài khoản được định nghĩa là không phân biệt hoa thường, có thể chuẩn hóa về chữ hoa:

```java
String code = rawCode.strip().toUpperCase(Locale.ROOT);
~~~

Dùng `Locale.ROOT` thay vì locale mặc định của máy. Kết quả chuyển đổi mã máy không nên thay đổi theo ngôn ngữ người dùng hoặc locale hệ điều hành.

Ví dụ, một số chữ cái có quy tắc chuyển hoa/thường đặc biệt theo locale. Dùng locale mặc định có thể làm cùng input tạo ra mã khác nhau giữa hai máy.

Không chuyển mọi tên hiển thị thành uppercase. Tên người, địa chỉ và nội dung tự do thường cần giữ nguyên cách viết theo contract.

### 5.2. Kiểm tra format sau normalization

Ví dụ mã tài khoản cho phép chữ ASCII, số và dấu gạch nối:

```java
private static final Pattern ACCOUNT_CODE =
        Pattern.compile("[A-Z0-9-]{3,20}");

private static String normalizeAccountCode(String rawCode) {
    Objects.requireNonNull(rawCode, "accountCode must not be null");

    String code = Normalizer.normalize(
            rawCode.strip(),
            Normalizer.Form.NFC
    ).toUpperCase(Locale.ROOT);

    if (!ACCOUNT_CODE.matcher(code).matches()) {
        throw new IllegalArgumentException(
                "accountCode must match [A-Z0-9-]{3,20}"
        );
    }
    return code;
}
~~~

Quy tắc này là ví dụ cho một domain cụ thể. Nếu hệ thống cho phép Unicode identifier, cần thiết kế character policy riêng, bao gồm normalization form, confusable characters và quy tắc so sánh.

### 5.3. Không dùng regex đơn giản cho mọi định dạng

Một regex email ngắn không thể mô tả đầy đủ mọi địa chỉ email hợp lệ. Nếu constructor cần giữ email, có thể:

- Từ chối null/blank.
- Loại bỏ whitespace đầu/cuối nếu contract cho phép.
- Chuẩn hóa domain theo chính sách phù hợp.
- Dùng validator chuyên dụng ở boundary nếu cần xác thực cú pháp đầy đủ.
- Không tự lowercase local-part nếu domain contract không cho phép.

Validation cú pháp không chứng minh địa chỉ tồn tại hoặc người dùng sở hữu nó. Xác minh ownership cần một quy trình riêng như gửi mã xác nhận.

## 6. Unicode normalization và chuỗi hiển thị

### 6.1. Hai chuỗi có thể nhìn giống nhau nhưng biểu diễn khác

Unicode có thể biểu diễn một ký tự hiển thị bằng một code point hoặc bằng tổ hợp ký tự nền và combining mark. Hai chuỗi có thể nhìn giống nhau nhưng không có cùng chuỗi code point.

Ví dụ chữ có dấu có thể được biểu diễn ở dạng dựng sẵn hoặc dạng ký tự cơ sở kết hợp dấu. Nếu dùng chuỗi làm khóa so sánh, cache key hoặc identifier, cần quyết định normalization form.

### 6.2. Dùng java.text.Normalizer

```java
String normalized = Normalizer.normalize(
        rawName,
        Normalizer.Form.NFC
);
~~~

Các form phổ biến:

- **NFC:** canonical decomposition rồi composition.
- **NFD:** canonical decomposition.
- **NFKC:** compatibility decomposition rồi composition.
- **NFKD:** compatibility decomposition.

NFC thường là lựa chọn phù hợp khi muốn biểu diễn tương đương canonical mà giữ khác biệt compatibility. NFKC có thể biến một số ký tự compatibility thành dạng chuẩn hóa khác và làm mất khác biệt có ý nghĩa trong một số domain.

Không chọn NFKC chỉ vì tên nghe có vẻ “mạnh hơn”. Hãy xác định contract của identifier và tác động tới dữ liệu hiện có.

### 6.3. Chuẩn hóa không giải quyết mọi vấn đề Unicode

Normalization không tự giải quyết:

- Ký tự nhìn giống nhau nhưng khác chữ (confusables).
- Script mixing.
- Ký tự điều khiển hoặc ký tự vô hình.
- Quy tắc grapheme cluster.
- Quy tắc ngôn ngữ về so sánh/collation.

Nếu identifier được dùng trong bảo mật, quyền truy cập hoặc URL, cần một policy riêng về ký tự được phép và so sánh. Không dựa vào normalization duy nhất để ngăn giả mạo tên.

### 6.4. Giữ nguyên display text khi phù hợp

Với tên hiển thị, thường nên:

1. Từ chối null.
2. Loại bỏ khoảng trắng đầu/cuối nếu contract cho phép.
3. Chuẩn hóa Unicode nếu hệ thống cần canonical representation.
4. Giữ nguyên chữ hoa/thường và dấu câu.

Không tự chuyển tên thành chữ thường hoặc xóa dấu vì có thể làm thay đổi ý nghĩa hoặc cách người dùng muốn hiển thị.

## 7. Kiểm tra miền giá trị số và tiền

### 7.1. Kiểm tra range

Ví dụ số lượng phải dương:

```java
public Quantity(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "quantity must be greater than zero"
        );
    }
    this.value = value;
}
~~~

Với giá trị nằm trong khoảng:

```java
if (percentage < 0 || percentage > 100) {
    throw new IllegalArgumentException(
            "percentage must be between 0 and 100"
    );
}
~~~

Kiểm tra biên inclusive/exclusive phải phản ánh chính xác nghiệp vụ. Không dùng `>=` thay cho `>` chỉ để tránh trường hợp bằng 0 nếu 0 là giá trị hợp lệ.

### 7.2. BigDecimal cho tiền

Không dùng `double` để biểu diễn tiền nếu cần phép tính decimal chính xác. Có thể dùng `BigDecimal`:

```java
public Money(BigDecimal amount) {
    Objects.requireNonNull(amount, "amount");
    if (amount.signum() < 0) {
        throw new IllegalArgumentException(
                "amount must not be negative"
        );
    }
    this.amount = amount;
}
~~~

`BigDecimal` immutable nên không cần defensive copy.

### 7.3. Scale là một phần của contract

Không tự động gọi `setScale(2, RoundingMode.HALF_UP)` trong mọi constructor tiền. Điều đó là một quy tắc nghiệp vụ về độ chính xác và rounding, không chỉ là chuẩn hóa hình thức.

Nếu domain yêu cầu tối đa hai chữ số thập phân:

```java
if (amount.scale() > 2) {
    throw new IllegalArgumentException(
            "amount must have at most two fractional digits"
    );
}
~~~

Nếu domain cho phép nhiều chữ số nhưng phải làm tròn, chọn rounding mode rõ ràng và ghi trong contract. Phân biệt số tiền có scale 2 với số tiền có giá trị tương đương nhưng scale 4; `BigDecimal.equals` xét cả scale, trong khi `compareTo` so sánh giá trị số.

### 7.4. Tránh overflow khi kiểm tra số học

Nếu invariant phụ thuộc tổng hoặc tích số nguyên, dùng phép toán kiểm tra overflow:

```java
long total = Math.addExact(first, second);
~~~

Nếu overflow là không hợp lệ, để `ArithmeticException` hoặc chuyển thành exception domain phù hợp. Không để giá trị wrap-around rồi tiếp tục tạo object sai.

## 8. Kiểm tra nhiều field và cross-field invariant

Một số điều kiện chỉ có thể xác định khi nhìn nhiều tham số cùng lúc:

- Ngày kết thúc không trước ngày bắt đầu.
- Ngày sinh không nằm trong tương lai nếu domain yêu cầu.
- Số tiền phải không âm và currency phải được hỗ trợ.
- Khoảng min/max phải có min nhỏ hơn hoặc bằng max.
- Trạng thái thanh toán phải tương thích với thời điểm thanh toán.

Ví dụ:

```java
public DateRange(LocalDate start, LocalDate end) {
    this.start = Objects.requireNonNull(start, "start");
    this.end = Objects.requireNonNull(end, "end");

    if (end.isBefore(start)) {
        throw new IllegalArgumentException(
                "end must not be before start"
        );
    }
}
~~~

Với code quan trọng, có thể validate tất cả tham số thành biến local trước khi gán field:

```java
LocalDate normalizedStart =
        Objects.requireNonNull(start, "start");
LocalDate normalizedEnd =
        Objects.requireNonNull(end, "end");

if (normalizedEnd.isBefore(normalizedStart)) {
    throw new IllegalArgumentException(
            "end must not be before start"
    );
}

this.start = normalizedStart;
this.end = normalizedEnd;
~~~

Cách viết này giúp nhìn thấy rõ giai đoạn kiểm tra và giai đoạn thiết lập trạng thái. Nó đặc biệt hữu ích khi constructor có nhiều tham số và invariant liên quan nhiều field.

### 8.1. Không dùng thời gian hiện tại một cách ẩn

Nếu constructor kiểm tra ngày kết thúc phải sau “hôm nay”, kết quả có thể phụ thuộc thời điểm tạo object và timezone mặc định.

Thay vì gọi `LocalDate.now()` ẩn trong constructor, hãy cân nhắc truyền `Clock` hoặc tách policy thời gian sang service/domain operation. Với object chỉ cần biểu diễn một khoảng ngày hợp lệ, kiểm tra `end >= start` là invariant ổn định; quy tắc “không được đặt lịch trong quá khứ” có thể thuộc nghiệp vụ tạo booking tại thời điểm cụ thể.

## 9. Defensive copy cho collection và array

### 9.1. Vấn đề với collection mutable

Đoạn code này giữ reference tới list của caller:

```java
public class Team {
    private final List<String> members;

    public Team(List<String> members) {
        this.members = members;
    }
}
~~~

Caller có thể thay đổi list sau khi constructor trả về:

```java
List<String> names = new ArrayList<>();
names.add("An");

Team team = new Team(names);
names.add("Bình"); // trạng thái team thay đổi theo
~~~

Field `final` chỉ ngăn gán lại reference. Nó không làm object mà reference trỏ tới trở thành immutable.

### 9.2. Dùng List.copyOf

Java 10 trở lên có `List.copyOf`; Java 17 dùng được:

```java
public Team(List<String> members) {
    this.members = List.copyOf(
            Objects.requireNonNull(members, "members")
    );
}
~~~

`List.copyOf` tạo list không sửa đổi và không giữ alias tới collection mutable ban đầu theo cách cho phép caller thay đổi list snapshot. Nó cũng từ chối phần tử null.

Nếu caller truyền một list đã immutable, implementation có thể tái sử dụng instance; contract quan trọng là caller không thể thay đổi collection mà object đang quan sát.

### 9.3. Chuẩn hóa từng phần tử

Nếu mỗi member phải là text không rỗng:

```java
private static List<String> normalizeMembers(List<String> input) {
    Objects.requireNonNull(input, "members");

    List<String> normalized = new ArrayList<>(input.size());
    for (String member : input) {
        normalized.add(requireText(member, "member"));
    }
    return List.copyOf(normalized);
}
~~~

Đoạn code vừa validate vừa chuẩn hóa phần tử và tạo snapshot immutable. Nếu cần loại bỏ duplicate, dùng cấu trúc và quy tắc thứ tự rõ ràng; không dùng `Set` nếu thứ tự là một phần của contract.

### 9.4. Defensive copy chỉ là shallow copy

`List.copyOf` chỉ sao chép cấu trúc collection, không tự clone các object bên trong. Nếu list chứa mutable object, caller vẫn có thể sửa object đó.

Ví dụ:

```java
List<Address> addresses = List.copyOf(input);
~~~

Nếu `Address` mutable, object sở hữu list vẫn quan sát được thay đổi của từng address. Có thể:

- Dùng immutable element type.
- Chuyển từng element thành immutable value object.
- Tạo deep copy theo contract của domain.

Không thể có một deep copy tổng quát an toàn cho mọi loại object.

### 9.5. Array phải clone

Array luôn mutable:

```java
public final class Digest {
    private final byte[] bytes;

    public Digest(byte[] bytes) {
        this.bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Clone ở constructor ngăn caller sửa array đầu vào. Clone ở accessor ngăn caller sửa trạng thái nội bộ sau khi lấy giá trị ra.

Nếu chỉ clone trong constructor nhưng getter trả array gốc, object vẫn bị thay đổi từ bên ngoài.

### 9.6. Map và Set

Các factory copy immutable tương ứng:

```java
this.roles = Set.copyOf(roles);
this.attributes = Map.copyOf(attributes);
~~~

Chúng từ chối null collection và null key/value theo contract. Nếu cần chuẩn hóa key, value hoặc bảo toàn thứ tự cụ thể, hãy tạo bản sao và xử lý tường minh trước khi dùng `Map.copyOf`/`Set.copyOf`.

## 10. Ví dụ tổng hợp: constructor bảo vệ invariant

Ta xây dựng `CustomerAccount` với các quy tắc:

- Account code bắt buộc, chuẩn hóa NFC, strip và uppercase theo `Locale.ROOT`.
- Code chỉ chứa A-Z, 0-9 và dấu gạch nối, dài 3 đến 20 ký tự.
- Display name bắt buộc, strip và chuẩn hóa NFC, nhưng giữ cách viết hoa/thường.
- Credit limit bắt buộc và không âm.
- Tags được chuẩn hóa, không rỗng, không null và lưu thành list immutable.
- Reference bytes được clone cả khi nhận và khi trả về.

~~~java
import java.math.BigDecimal;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public final class CustomerAccount {

    private static final Pattern ACCOUNT_CODE =
            Pattern.compile("[A-Z0-9-]{3,20}");

    private final String accountCode;
    private final String displayName;
    private final BigDecimal creditLimit;
    private final List<String> tags;
    private final byte[] externalReference;

    public CustomerAccount(
            String accountCode,
            String displayName,
            BigDecimal creditLimit,
            List<String> tags,
            byte[] externalReference
    ) {
        String normalizedCode = normalizeAccountCode(accountCode);
        String normalizedName = normalizeDisplayName(displayName);
        BigDecimal checkedLimit = validateCreditLimit(creditLimit);
        List<String> copiedTags = normalizeTags(tags);
        byte[] copiedReference =
                Objects.requireNonNull(
                        externalReference,
                        "externalReference must not be null"
                ).clone();

        this.accountCode = normalizedCode;
        this.displayName = normalizedName;
        this.creditLimit = checkedLimit;
        this.tags = copiedTags;
        this.externalReference = copiedReference;
    }

    private static String normalizeAccountCode(String raw) {
        Objects.requireNonNull(raw, "accountCode must not be null");

        String code = Normalizer.normalize(
                raw.strip(),
                Normalizer.Form.NFC
        ).toUpperCase(Locale.ROOT);

        if (!ACCOUNT_CODE.matcher(code).matches()) {
            throw new IllegalArgumentException(
                    "accountCode must match [A-Z0-9-]{3,20}"
            );
        }
        return code;
    }

    private static String normalizeDisplayName(String raw) {
        Objects.requireNonNull(raw, "displayName must not be null");

        String name = Normalizer.normalize(
                raw.strip(),
                Normalizer.Form.NFC
        );

        if (name.isEmpty()) {
            throw new IllegalArgumentException(
                    "displayName must not be blank"
            );
        }
        return name;
    }

    private static BigDecimal validateCreditLimit(BigDecimal value) {
        Objects.requireNonNull(value, "creditLimit must not be null");

        if (value.signum() < 0) {
            throw new IllegalArgumentException(
                    "creditLimit must not be negative"
            );
        }
        return value;
    }

    private static List<String> normalizeTags(List<String> input) {
        Objects.requireNonNull(input, "tags must not be null");

        List<String> normalized = new ArrayList<>(input.size());
        for (String tag : input) {
            String value = Objects.requireNonNull(
                    tag,
                    "tags must not contain null"
            ).strip();

            if (value.isEmpty()) {
                throw new IllegalArgumentException(
                        "tags must not contain blank values"
                );
            }
            normalized.add(
                    Normalizer.normalize(value, Normalizer.Form.NFC)
            );
        }
        return List.copyOf(normalized);
    }

    public String accountCode() {
        return accountCode;
    }

    public String displayName() {
        return displayName;
    }

    public BigDecimal creditLimit() {
        return creditLimit;
    }

    public List<String> tags() {
        return tags;
    }

    public byte[] externalReference() {
        return externalReference.clone();
    }
}
~~~

### 10.1. Vì sao dùng biến local trước khi gán field?

Constructor chuẩn hóa và kiểm tra các tham số thành biến local:

```java
String normalizedCode = normalizeAccountCode(accountCode);
String normalizedName = normalizeDisplayName(displayName);
...
this.accountCode = normalizedCode;
~~~

Điều này làm rõ rằng các giá trị đã qua validation trước khi trở thành trạng thái của object. Nếu validation thất bại, constructor ném exception và instance chưa được trả về caller.

### 10.2. Vì sao BigDecimal không cần clone?

`BigDecimal` là immutable. Không có cách thay đổi object BigDecimal hiện tại; các phép toán trả về instance mới. Vì vậy có thể lưu reference sau khi validation.

### 10.3. Vì sao List.copyOf phù hợp?

Tags được tạo thành list mới, từng phần tử được chuẩn hóa, sau đó `List.copyOf` tạo collection không sửa đổi. Caller không thể thêm/xóa phần tử để làm thay đổi tags của account.

### 10.4. Vì sao accessor của byte[] phải clone?

Array mutable nên nếu trả reference nội bộ, caller có thể sửa dữ liệu. Accessor trả clone để bảo vệ invariant sau khi object đã được tạo.

## 11. Constructor delegation và tránh lặp validation

### 11.1. Dùng this(...) để tập trung logic

Nếu class có nhiều constructor, hãy để các constructor phụ chuyển tiếp về một constructor chính:

~~~java
public final class Product {
    private final String code;
    private final String description;
    private final boolean active;

    public Product(String code) {
        this(code, "No description", true);
    }

    public Product(String code, String description) {
        this(code, description, true);
    }

    public Product(
            String code,
            String description,
            boolean active
    ) {
        this.code = requireText(code, "code");
        this.description = requireText(description, "description");
        this.active = active;
    }

    private static String requireText(String value, String name) {
        Objects.requireNonNull(value, name);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return normalized;
    }
}
~~~

Mọi đường tạo Product đều đi qua constructor chính, nên invariant không bị bỏ sót ở một overload.

### 11.2. this(...) phải là câu lệnh đầu tiên

Trong constructor Java, lời gọi `this(...)` phải đứng đầu constructor. Vì vậy không thể viết validation statement trước lời gọi này.

Nếu một constructor cần chuẩn hóa input riêng, hãy chuyển quy tắc vào static helper được gọi trong đối số `this(...)`, hoặc để constructor chính xử lý tất cả.

### 11.3. Tránh constructor overload mơ hồ

Nhiều constructor khác nhau chỉ vì các tham số có kiểu gần nhau có thể gây khó gọi, đặc biệt khi caller truyền `null`.

Ví dụ:

```java
new Report(null); // Có thể mơ hồ nếu có overload String và Path
~~~

Khi API có nhiều cấu hình tùy chọn, cân nhắc static factory hoặc builder để lời gọi có tên và tránh overload ambiguity.

## 12. Dùng static factory khi cần chuyển đổi dữ liệu đầu vào

Constructor nên tập trung thiết lập invariant của object. Nếu đầu vào là định dạng ngoài như chuỗi ngày, JSON DTO hoặc record từ database, static factory có thể chuyển đổi trước:

~~~java
public final class Booking {
    private final LocalDate start;
    private final LocalDate end;

    public Booking(LocalDate start, LocalDate end) {
        LocalDate checkedStart =
                Objects.requireNonNull(start, "start");
        LocalDate checkedEnd =
                Objects.requireNonNull(end, "end");

        if (checkedEnd.isBefore(checkedStart)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }

        this.start = checkedStart;
        this.end = checkedEnd;
    }

    public static Booking fromIsoDates(
            String startText,
            String endText
    ) {
        LocalDate start = LocalDate.parse(
                Objects.requireNonNull(startText, "startText").strip()
        );
        LocalDate end = LocalDate.parse(
                Objects.requireNonNull(endText, "endText").strip()
        );
        return new Booking(start, end);
    }
}
~~~

Static factory làm rõ conversion boundary:

- Parse input text thành kiểu domain.
- Constructor xác nhận invariant của domain object.

Nếu parsing thất bại, `DateTimeParseException` được ném ra. Có thể để caller xử lý lỗi định dạng tại boundary hoặc chuyển thành exception của API nếu cần message thống nhất. Không bắt mọi `RuntimeException` rồi đổi thành “invalid input”, vì sẽ che giấu bug không liên quan.

## 13. Compact constructor của record

### 13.1. Record phù hợp với value data carrier

Java 17 hỗ trợ record. Record tự tạo field private final, accessor, `equals`, `hashCode` và `toString` dựa trên component.

Record vẫn có thể kiểm tra và chuẩn hóa component tại constructor. Với compact constructor, tham số có thể được gán lại; Java sẽ gán giá trị cuối cùng vào component field sau khi thân constructor hoàn tất.

~~~java
public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }
    }
}
~~~

Không viết `this.start = start` trong compact constructor; việc gán component được compiler thực hiện sau phần thân compact constructor.

### 13.2. Chuẩn hóa String trong record

~~~java
public record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]{3,20}")) {
            throw new IllegalArgumentException(
                    "value must match [A-Z0-9-]{3,20}"
            );
        }
    }
}
~~~

Sau khi tạo, `ProductCode` luôn giữ giá trị đã chuẩn hóa.

### 13.3. Record chứa collection vẫn cần defensive copy

Record không tự làm object được tham chiếu trở thành immutable:

~~~java
public record Team(List<String> members) {
    public Team {
        members = List.copyOf(
                Objects.requireNonNull(members, "members")
        );
    }
}
~~~

Nếu `members` chứa mutable element, `List.copyOf` vẫn chỉ copy cấu trúc list. Cần immutable element hoặc deep copy theo contract.

### 13.4. Record không phù hợp với mọi entity

Record phù hợp với dữ liệu có identity dựa trên component và không cần thay đổi sau khi tạo. Với entity có identity riêng, lifecycle, behavior phong phú hoặc compatibility yêu cầu khác, class thông thường có thể phù hợp hơn.

Dù dùng class hay record, invariant vẫn cần được bảo vệ.

## 14. Constructor không nên làm những việc gì?

### 14.1. Không thực hiện I/O hoặc gọi dịch vụ từ xa

Không nên viết:

~~~java
public Customer(String id) {
    this.id = id;
    this.profile = customerRepository.load(id);
}
~~~

Constructor lúc này phụ thuộc database, network, credentials và trạng thái hệ thống. Việc tạo object có thể chậm, thất bại do môi trường hoặc tạo side effect khó kiểm soát.

Hãy thực hiện I/O ở service/factory có dependency rõ ràng, sau đó truyền dữ liệu đã tải vào constructor.

### 14.2. Không đăng ký this vào nơi khác trước khi hoàn tất

Tránh để `this` thoát khỏi constructor trước khi tất cả field được thiết lập:

~~~java
public Listener() {
    Registry.register(this);
    this.name = "ready";
}
~~~

Registry hoặc thread khác có thể nhìn thấy object chưa hoàn chỉnh. Đây là một dạng `this escape`.

Đăng ký listener sau khi object đã được tạo hoàn chỉnh, ví dụ bằng một lifecycle method hoặc factory quản lý bước khởi tạo.

### 14.3. Không gọi overridable method trong constructor

Một constructor của superclass có thể gọi method đã được subclass override. Khi đó method subclass chạy trước khi field subclass được khởi tạo đầy đủ.

~~~java
class Base {
    Base() {
        initialize();
    }

    void initialize() {
    }
}

class Child extends Base {
    private String value = "ready";

    @Override
    void initialize() {
        System.out.println(value.length()); // value có thể vẫn null
    }
}
~~~

Tránh gọi method có thể override từ constructor. Nếu cần tính toán invariant, dùng private/static helper hoặc logic không dispatch tới subclass.

### 14.4. Không lưu trực tiếp mutable input

Đừng dựa vào `final` để nghĩ array, collection hoặc Date đã immutable. Hãy copy dữ liệu mutable hoặc chuyển sang kiểu immutable phù hợp.

### 14.5. Không validate một phần rồi bỏ sót overload khác

Nếu class có nhiều constructor, các đường khởi tạo phải hội tụ về một điểm kiểm tra invariant. Nếu không, một overload có thể tạo object hợp lệ còn overload khác tạo object sai.

## 15. Validation tại constructor và validation ở tầng ứng dụng

### 15.1. Hai tầng có mục tiêu khác nhau

Validation ở API/controller/form thường phục vụ trải nghiệm nhập liệu:

- Hiển thị lỗi cho field cụ thể.
- Gom nhiều lỗi vào một response.
- Kiểm tra định dạng request.
- Chuyển đổi dữ liệu từ JSON/form thành kiểu domain.

Validation tại constructor bảo vệ invariant của object:

- Không phụ thuộc caller có đi qua controller hay không.
- Bảo đảm object hợp lệ khi tạo từ test, batch, message consumer hoặc service nội bộ.
- Ngăn trạng thái sai lọt vào domain model.

Một API có thể dùng Jakarta Bean Validation annotations để kiểm tra request DTO, nhưng annotation validation ở boundary không thay thế invariant trong domain object nếu object phải luôn hợp lệ.

### 15.2. Không lặp cùng một validation một cách vô ích

Có thể kiểm tra format ở boundary để trả lỗi thân thiện và tiếp tục bảo vệ invariant ở constructor. Hai nơi có mục đích khác nhau:

- Boundary: lỗi đầu vào và phản hồi cho người dùng.
- Constructor: đảm bảo mọi đường tạo object tuân thủ domain contract.

Nếu logic phức tạp, đặt quy tắc trong một value object/helper dùng chung để tránh hai nơi triển khai khác nhau.

### 15.3. Validation cần dữ liệu ngoài object thuộc service/domain operation

Ví dụ “email chưa được tài khoản khác sử dụng” cần truy vấn repository. Đây không phải invariant có thể xác minh chỉ từ tham số constructor.

Hãy kiểm tra uniqueness ở service/domain operation với transaction và database constraint phù hợp. Constructor chỉ kiểm tra các điều kiện nội tại như null, blank hoặc format theo contract.

## 16. Kiểm thử constructor

Kiểm thử constructor nên xác nhận cả:

- Input hợp lệ được chuẩn hóa đúng.
- Input null bị từ chối.
- Input sai format/range bị từ chối.
- Cross-field invariant được bảo vệ.
- Mutable input không thể thay đổi trạng thái object sau khi tạo.
- Accessor không làm lộ mutable internal state.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CustomerAccountTest {

    @Test
    void normalizesAccountCodeAndDisplayName() {
        CustomerAccount account = new CustomerAccount(
                "  ac-100  ",
                "  Nguyễn An  ",
                new BigDecimal("100.00"),
                List.of(" premium "),
                new byte[] {1, 2, 3}
        );

        assertEquals("AC-100", account.accountCode());
        assertEquals("Nguyễn An", account.displayName());
        assertEquals(List.of("premium"), account.tags());
    }

    @Test
    void rejectsNullAccountCode() {
        assertThrows(
                NullPointerException.class,
                () -> new CustomerAccount(
                        null,
                        "An",
                        BigDecimal.ZERO,
                        List.of(),
                        new byte[0]
                )
        );
    }

    @Test
    void rejectsInvalidAccountCode() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new CustomerAccount(
                        "bad code",
                        "An",
                        BigDecimal.ZERO,
                        List.of(),
                        new byte[0]
                )
        );
    }

    @Test
    void rejectsNegativeCreditLimit() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new CustomerAccount(
                        "AC-100",
                        "An",
                        new BigDecimal("-0.01"),
                        List.of(),
                        new byte[0]
                )
        );
    }

    @Test
    void copiesTagsAndReferenceArray() {
        List<String> tags = new ArrayList<>(List.of("vip"));
        byte[] reference = {1, 2, 3};

        CustomerAccount account = new CustomerAccount(
                "AC-100",
                "An",
                BigDecimal.ZERO,
                tags,
                reference
        );

        tags.add("changed");
        reference[0] = 99;

        assertEquals(List.of("vip"), account.tags());
        assertArrayEquals(
                new byte[] {1, 2, 3},
                account.externalReference()
        );

        byte[] returned = account.externalReference();
        returned[1] = 88;

        assertArrayEquals(
                new byte[] {1, 2, 3},
                account.externalReference()
        );
    }
}
~~~

Các test trên minh họa cách kiểm tra constructor contract. Khi áp dụng vào project, cần dùng đúng dependency/test framework và package của class thực tế.

### 16.1. Test boundary values

Với mỗi điều kiện range hoặc length, test:

- Giá trị nhỏ nhất hợp lệ.
- Giá trị lớn nhất hợp lệ.
- Một giá trị ngay dưới biên.
- Một giá trị ngay trên biên.
- Null/blank nếu kiểu dữ liệu cho phép.

Ví dụ mã có độ dài 3 đến 20 ký tự cần test độ dài 2, 3, 20 và 21.

### 16.2. Test normalization idempotence

Một normalization thường nên có tính idempotent: chuẩn hóa một lần rồi chuẩn hóa lại không thay đổi kết quả:

~~~java
String once = normalizeAccountCode(input);
String twice = normalizeAccountCode(once);
assertEquals(once, twice);
~~~

Đây là tính chất hữu ích cho identifier canonicalization. Không áp dụng máy móc cho phép biến đổi có chủ đích thay đổi theo thời gian hoặc trạng thái bên ngoài.

### 16.3. Test immutable boundary

Đừng chỉ kiểm tra getter trả đúng dữ liệu. Hãy sửa input sau constructor và sửa output sau accessor để xác nhận object không bị thay đổi.

Với collection chứa mutable elements, test cả việc thay đổi phần tử nếu contract yêu cầu deep immutability.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ gán tham số vào field | Object có thể tồn tại ở trạng thái sai | Kiểm tra invariant trong constructor |
| Dùng `requireNonNull` rồi nghĩ đã đủ validation | Chuỗi rỗng, số âm hoặc format sai vẫn lọt qua | Kiểm tra nội dung sau null check |
| Dùng `trim()` cho mọi chuỗi | Quy tắc whitespace hạn chế hơn `strip()` | Chọn method theo contract Java 17 |
| Dùng locale mặc định để chuẩn hóa identifier | Kết quả có thể khác theo máy/ngôn ngữ | Dùng `Locale.ROOT` cho mã kỹ thuật |
| Lowercase tên hiển thị | Làm thay đổi dữ liệu người dùng | Chỉ chuẩn hóa những trường có contract rõ |
| Dùng regex đơn giản để xác minh email hoàn chỉnh | Có thể từ chối input hợp lệ hoặc nhận input sai | Dùng validator phù hợp và xác minh ownership riêng |
| Dùng NFKC cho mọi identifier | Có thể làm mất khác biệt compatibility có ý nghĩa | Chọn Unicode normalization form theo domain |
| Clamp giá trị sai thành 0 | Che giấu lỗi đầu vào | Ném exception nếu contract không cho phép |
| Lưu trực tiếp List/Map/Set từ caller | Caller có thể thay đổi object sau khi tạo | Copy và dùng immutable collection |
| Chỉ clone array ở constructor | Getter vẫn làm lộ array nội bộ | Clone cả input và output |
| Nghĩ List.copyOf là deep copy | Mutable elements vẫn có thể thay đổi | Dùng immutable element hoặc deep copy có chủ đích |
| Lặp validation trong mọi constructor overload | Các đường khởi tạo dễ lệch nhau | Dùng constructor delegation |
| Gọi repository/network trong constructor | Tạo object có side effect, khó test và retry | Tách I/O sang service/factory |
| Đăng ký `this` khi constructor chưa xong | Object có thể bị quan sát ở trạng thái dở dang | Đăng ký sau khi khởi tạo hoàn tất |
| Gọi method có thể override từ constructor | Subclass có thể chạy trước khi khởi tạo xong | Dùng private/static helper |
| Chỉ validate ở controller | Object tạo từ batch/test/service vẫn có thể sai | Giữ invariant tại domain constructor |
| Kiểm tra uniqueness trong constructor | Constructor phụ thuộc DB và race condition | Dùng service/transaction và DB constraint |
| Không test biên và defensive copy | Regression có thể phá invariant | Test boundary và mutation từ caller |

## 18. Bài tập thực hành

### Bài 1 — Value object cho mã sản phẩm

Tạo `ProductCode`:

- Không null.
- Strip whitespace đầu/cuối.
- Chuẩn hóa uppercase bằng `Locale.ROOT`.
- Chỉ cho phép chữ ASCII, số và dấu gạch nối.
- Độ dài từ 3 đến 20.

Viết test cho input hợp lệ, null, blank, ký tự không hợp lệ và boundary length.

### Bài 2 — Money

Tạo `Money` dùng `BigDecimal`:

- Amount không null.
- Amount không âm.
- Currency không null.
- Xác định rõ scale policy.
- Không tự làm tròn nếu contract không yêu cầu.

Viết test cho zero, positive, negative và scale vượt giới hạn nếu domain có giới hạn.

### Bài 3 — Defensive copy

Tạo class nhận `List<String>`, `Map<String, String>` và `byte[]`. Thay đổi input sau khi tạo object; xác nhận trạng thái object không đổi. Sau đó sửa giá trị trả từ accessor và xác nhận internal state vẫn được bảo vệ.

### Bài 4 — Cross-field invariant

Tạo `DateRange` hoặc `BookingPeriod`:

- Start/end bắt buộc.
- End không trước start.
- Không gọi clock ẩn trong constructor.
- Viết test cho cùng ngày, ngày sau và ngày trước.

### Bài 5 — Constructor delegation

Tạo class có ba constructor với các cấu hình mặc định khác nhau. Đảm bảo tất cả đi qua constructor chính và không có đường tạo object bỏ qua validation.

### Bài 6 — Record compact constructor

Chuyển một value object đơn giản thành record. Chuẩn hóa component trong compact constructor và defensive copy collection. Giải thích vì sao record không tự làm collection component immutable.

### Bài 7 — Unicode normalization

Tạo hai String có biểu diễn Unicode canonical tương đương. Chuẩn hóa về NFC và so sánh kết quả. Thử NFKC trên một số ký tự compatibility và giải thích vì sao không nên áp dụng tùy tiện.

### Bài 8 — Tách boundary validation và invariant

Tạo DTO nhận dữ liệu dạng String từ request, chuyển thành domain value object. Xác định validation nào phục vụ thông báo cho người dùng và validation nào phải được bảo vệ ở constructor.

### Bài 9 — Kiểm tra constructor anti-pattern

Viết một class có constructor gọi repository và một class đăng ký `this` trước khi hoàn tất. Refactor để I/O nằm ở factory/service và lifecycle registration diễn ra sau khi object được tạo.

## 19. Câu hỏi tự kiểm tra

1. Invariant của object là gì?
2. Validation khác normalization thế nào?
3. Vì sao constructor cần từ chối trạng thái không hợp lệ?
4. Khi nào dùng `Objects.requireNonNull`?
5. Khi nào dùng `IllegalArgumentException`?
6. `String.isEmpty()` và `String.isBlank()` khác nhau thế nào?
7. Vì sao `strip()` phù hợp hơn `trim()` trong nhiều trường hợp Java 17?
8. Vì sao dùng `Locale.ROOT` khi chuẩn hóa mã kỹ thuật?
9. NFC và NFKC khác nhau thế nào?
10. Vì sao Unicode normalization không ngăn mọi confusable identifier?
11. Vì sao không nên lowercase mọi display name?
12. Tại sao không nên tự động làm tròn BigDecimal trong constructor nếu contract chưa yêu cầu?
13. `List.copyOf` bảo vệ điều gì và không bảo vệ điều gì?
14. Vì sao phải clone array cả lúc nhận và lúc trả?
15. Defensive copy khác deep copy thế nào?
16. Constructor delegation giúp giữ invariant ra sao?
17. Compact constructor của record gán component field khi nào?
18. Vì sao không nên gọi repository hoặc network trong constructor?
19. `this escape` trong constructor nguy hiểm thế nào?
20. Vì sao không nên gọi overridable method trong constructor?
21. Validation ở controller có thay thế validation domain không?
22. Vì sao uniqueness check thường thuộc service/database thay vì constructor?
23. Test constructor cần bao gồm những boundary case nào?
24. Khi nào static factory phù hợp hơn constructor overload?

## 20. Tài liệu tham khảo

- [Java SE 17 API — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull` và các tiện ích kiểm tra object.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `isBlank`, `strip`, `stripLeading`, `stripTrailing`.
- [Java SE 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization forms.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, scale và rounding.
- [Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `copyOf` và immutable list factory.
- [Java SE 17 API — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `copyOf` và immutable map factory.
- [Java SE 17 API — Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): `copyOf` và immutable set factory.
- [Java Language Specification, Java SE 17 — Records](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record declaration và canonical/compact constructors.
- [Java SE 17 API — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale-independent processing với `Locale.ROOT`.

Constructor là nơi thiết lập contract cho một object. Hãy kiểm tra null, chuẩn hóa dữ liệu theo quy tắc domain, validate range và các điều kiện liên quan nhiều field, rồi bảo vệ các giá trị mutable bằng defensive copy. Tập trung mọi đường khởi tạo vào một invariant rõ ràng, giữ I/O ở tầng service/factory và viết test cho cả dữ liệu hợp lệ, dữ liệu sai lẫn khả năng caller thay đổi input sau khi tạo object. Khi object được tạo thành công, các điều kiện hợp lệ của nó phải luôn được duy trì trong Java 17.
