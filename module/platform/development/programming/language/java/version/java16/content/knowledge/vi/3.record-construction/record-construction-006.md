# Chuẩn hóa tham số ngay trong compact constructor

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu các cải tiến từ Java 16 vẫn còn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này tập trung vào cách chuẩn hóa các tham số ngầm của compact constructor trước khi compiler gán chúng vào component field.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao có thể gán lại tham số trong compact canonical constructor.
- Phân biệt **chuẩn hóa (normalization)** với **xác thực (validation)**.
- Chuẩn hóa chuỗi, mã định danh, giá trị số và collection theo hợp đồng dữ liệu.
- Chọn thứ tự kiểm tra null, chuẩn hóa và xác thực phù hợp.
- Dùng `Locale.ROOT` và Unicode normalization đúng ngữ cảnh.
- Hiểu vì sao chuẩn hóa nên có kết quả ổn định, dễ dự đoán và không làm mất thông tin ngoài ý muốn.
- Viết test cho giá trị đầu vào và giá trị thực sự được lưu trong record.

## 1. Chuẩn hóa tham số trong compact constructor là gì?

Record mô tả dữ liệu qua các component trong header. Ví dụ:

```java
public record UserName(String value) {}
```

Khi không khai báo constructor, Java sinh canonical constructor. Nếu cần chuẩn hóa dữ liệu trước khi lưu, bạn có thể viết compact canonical constructor:

```java
public record UserName(String value) {
    public UserName {
        value = value.strip();
    }
}
```

Trong compact constructor, danh sách tham số không được viết tường minh. Compiler suy ra tham số `value` từ component `String value` trong record header.

Tham số này có thể được gán lại. Khi thân constructor kết thúc bình thường, compiler tự gán **giá trị cuối cùng của tham số** vào component field `this.value`. Vì vậy, lệnh:

```java
value = value.strip();
```

điều chỉnh giá trị sẽ được lưu vào record. Bạn không viết `this.value = ...` trong compact constructor.

Ví dụ sử dụng:

```java
UserName userName = new UserName("  Linh  ");

System.out.println(userName.value()); // Linh
```

Record lưu chuỗi đã bỏ khoảng trắng ở đầu và cuối, thay vì lưu nguyên chuỗi đầu vào.

## 2. Phân biệt chuẩn hóa và xác thực

Hai thao tác thường được đặt cạnh nhau trong constructor nhưng có mục đích khác nhau:

- **Chuẩn hóa:** chuyển dữ liệu về một dạng biểu diễn nhất quán mà hệ thống chấp nhận, ví dụ bỏ khoảng trắng thừa ở hai đầu hoặc chuyển mã kỹ thuật về chữ hoa.
- **Xác thực:** quyết định dữ liệu có đáp ứng điều kiện nghiệp vụ hay không, ví dụ tên không được rỗng hoặc số lượng phải lớn hơn 0.

Ví dụ:

```java
import java.util.Objects;

public record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(java.util.Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Trong ví dụ:

1. `Objects.requireNonNull` từ chối `null`.
2. `strip()` loại bỏ khoảng trắng ở hai đầu.
3. `toUpperCase(Locale.ROOT)` chuẩn hóa chữ hoa theo locale trung lập.
4. Điều kiện `isEmpty()` xác thực chuỗi sau chuẩn hóa.

Không phải dữ liệu nào cũng nên tự động chuẩn hóa. Nếu khoảng trắng, chữ hoa/thường hoặc ký tự Unicode mang ý nghĩa phân biệt trong nghiệp vụ, hãy từ chối dữ liệu sai thay vì âm thầm thay đổi nó. Chuẩn hóa là một phần của hợp đồng kiểu dữ liệu, cần được chọn có chủ đích.

## 3. Thứ tự xử lý: null, chuẩn hóa, xác thực

Với component tham chiếu, hãy xử lý null trước khi gọi phương thức trên giá trị đó. Một thứ tự phổ biến:

1. Kiểm tra null cho component bắt buộc.
2. Chuẩn hóa theo quy tắc đã xác định.
3. Xác thực giá trị sau chuẩn hóa.
4. Gán lại tham số ngầm bằng giá trị cuối cùng.

Ví dụ:

```java
import java.util.Objects;

public record DisplayName(String value) {
    public DisplayName {
        Objects.requireNonNull(value, "value");

        value = value.strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Không nên gọi `strip()` trước rồi mới kiểm tra null:

```java
// SAI THỨ TỰ
public record DisplayName(String value) {
    public DisplayName {
        value = value.strip(); // Ném NullPointerException nếu value là null.

        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
```

Điều kiện kiểm tra null phía sau không thể chạy nếu lệnh `strip()` đã ném ngoại lệ. Dùng `Objects.requireNonNull(value, "value")` giúp xác định component bắt buộc ngay tại đầu constructor.

Nếu null được phép theo nghiệp vụ, hãy biểu đạt rõ điều đó. Không phải component tham chiếu nào cũng phải non-null; đôi khi `null` có ý nghĩa riêng, và constructor nên giữ hoặc chuyển đổi nó theo hợp đồng đã công bố.

## 4. Bỏ khoảng trắng ở đầu và cuối bằng strip()

`String.strip()` loại bỏ các ký tự mà `Character.isWhitespace` nhận diện ở đầu và cuối chuỗi. Phương thức này có từ Java 11 nên sử dụng bình thường trong Java 16 và các phiên bản Java hiện đại.

```java
public record AccountName(String value) {
    public AccountName {
        value = value.strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("account name is required");
        }
    }
}
```

Ví dụ:

```java
AccountName a = new AccountName("  alice  ");
AccountName b = new AccountName("alice");

System.out.println(a.value());       // alice
System.out.println(a.equals(b));     // true
```

Sau chuẩn hóa, hai đối tượng có cùng component value nên phép so sánh giá trị do record cung cấp xem chúng là bằng nhau.

### strip(), stripLeading(), stripTrailing() và trim()

Có thể chọn thao tác theo chính sách:

| Phương thức | Hành vi |
| --- | --- |
| `strip()` | Bỏ khoảng trắng ở cả đầu và cuối. |
| `stripLeading()` | Chỉ bỏ ở đầu chuỗi. |
| `stripTrailing()` | Chỉ bỏ ở cuối chuỗi. |
| `trim()` | Dùng quy tắc cũ dựa trên ký tự có mã nhỏ hơn hoặc bằng U+0020. |

Với ứng dụng Java hiện đại, `strip()` thường phù hợp hơn khi yêu cầu là bỏ khoảng trắng theo `Character.isWhitespace`. Tuy nhiên, `strip()` không đồng nghĩa với việc xóa mọi ký tự trông giống khoảng trắng trong Unicode; ví dụ một số ký tự space đặc biệt không được `Character.isWhitespace` nhận diện. Nếu dữ liệu đến từ nhiều nguồn hoặc có quy tắc Unicode cụ thể, hãy định nghĩa rõ tập ký tự cần xử lý và test các trường hợp đó.

Không dùng `strip()` cho mọi chuỗi một cách máy móc. Ví dụ, khoảng trắng có thể là một phần hợp lệ của nội dung tự do hoặc dữ liệu được ký số; việc thay đổi nó có thể làm thay đổi ý nghĩa hoặc chữ ký.

## 5. Chuẩn hóa chữ hoa/thường với Locale.ROOT

Với mã kỹ thuật không phụ thuộc ngôn ngữ người dùng, có thể chuẩn hóa chữ hoa hoặc chữ thường bằng `Locale.ROOT`:

```java
import java.util.Locale;
import java.util.Objects;

public record CountryCode(String value) {
    public CountryCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException("expected two ASCII letters");
        }
    }
}
```

`Locale.ROOT` tránh kết quả chuyển chữ phụ thuộc locale mặc định của máy chạy. Điều này phù hợp với mã giao thức, mã kỹ thuật hoặc khóa được định nghĩa không phụ thuộc ngôn ngữ.

Tương tự, chuẩn hóa chữ thường:

```java
import java.util.Locale;
import java.util.Objects;

public record FeatureKey(String value) {
    public FeatureKey {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toLowerCase(Locale.ROOT);

        if (!value.matches("[a-z][a-z0-9-]*")) {
            throw new IllegalArgumentException("invalid feature key");
        }
    }
}
```

Lưu ý:

- `Locale.ROOT` là locale trung lập cho các phép chuyển đổi chữ hoa/thường theo quy tắc Java; nó không phải một thuật toán Unicode case folding đầy đủ cho mọi hệ thống tìm kiếm.
- Không tự động chuyển email, tên người, tên địa danh hoặc nội dung ngôn ngữ tự nhiên về chữ thường nếu hợp đồng nghiệp vụ không cho phép.
- Nếu một định danh chỉ cho phép ASCII, hãy xác thực tập ký tự sau khi chuẩn hóa thay vì giả định mọi chữ cái Unicode đều tương đương A-Z.
- Quy tắc so sánh và chuẩn hóa cần nhất quán ở mọi nơi tạo, lưu và truy vấn khóa.

## 6. Chuẩn hóa Unicode khi cần dạng biểu diễn nhất quán

Trong Unicode, một ký tự người dùng nhìn thấy có thể được biểu diễn bằng nhiều chuỗi code point khác nhau. Chẳng hạn, chữ có dấu có thể được mã hóa bằng một code point dựng sẵn hoặc chữ cái cơ sở đi cùng dấu kết hợp.

Nếu nghiệp vụ cần xem các biểu diễn tương đương theo chuẩn Unicode là cùng một giá trị, có thể dùng `java.text.Normalizer`:

```java
import java.text.Normalizer;
import java.util.Objects;

public record SearchLabel(String value) {
    public SearchLabel {
        value = Normalizer.normalize(
                Objects.requireNonNull(value, "value").strip(),
                Normalizer.Form.NFC
        );

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

`Normalizer.Form.NFC` chuẩn hóa theo dạng Canonical Composition. Một số dạng phổ biến:

| Form | Mục đích khái quát |
| --- | --- |
| `NFC` | Phân rã canonical rồi kết hợp về dạng dựng sẵn khi có thể. |
| `NFD` | Phân rã canonical. |
| `NFKC` | Phân rã tương thích rồi kết hợp. |
| `NFKD` | Phân rã tương thích. |

NFC thường là lựa chọn phù hợp khi cần chuẩn hóa tương đương canonical mà vẫn giữ khác biệt tương thích. NFKC/NFKD có thể làm mất một số khác biệt về cách trình bày hoặc ký hiệu; chỉ dùng khi hợp đồng dữ liệu cho phép.

Không phải mọi hệ thống đều cần chuẩn hóa Unicode. Hãy chọn form theo quy tắc nghiệp vụ, đặc tả giao thức hoặc yêu cầu lưu trữ. Nếu giá trị được dùng làm khóa bảo mật, định danh đăng nhập hoặc dữ liệu ký số, cần cân nhắc thêm quy tắc chống ký tự giả mạo, confusable và kiểm soát ký tự cho phép; NFC đơn thuần không giải quyết tất cả các vấn đề đó.

## 7. Chuẩn hóa số và giá trị thập phân

Chuẩn hóa số thường nhằm đưa các biểu diễn tương đương về một dạng nhất quán. Với `BigDecimal`, các giá trị `1.0` và `1.00` có cùng giá trị số nhưng khác scale; `equals()` xem chúng là khác nhau, còn `compareTo()` xem chúng bằng nhau.

Nếu scale không mang ý nghĩa trong component, có thể chuẩn hóa bằng `stripTrailingZeros()`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record UnitPrice(BigDecimal amount) {
    public UnitPrice {
        amount = Objects.requireNonNull(amount, "amount")
                .stripTrailingZeros();

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
    }
}
```

Ví dụ:

```java
UnitPrice a = new UnitPrice(new BigDecimal("1.00"));
UnitPrice b = new UnitPrice(new BigDecimal("1.0"));

System.out.println(a.amount());       // 1
System.out.println(a.equals(b));     // true
```

Sau chuẩn hóa, hai component `BigDecimal` có biểu diễn bằng nhau theo `equals()`. Tuy nhiên, cần thận trọng: scale đôi khi có ý nghĩa nghiệp vụ, chẳng hạn số chữ số thập phân được nhập hoặc quy tắc làm tròn theo đơn vị tiền. Khi scale quan trọng, không nên tự ý gọi `stripTrailingZeros()`; thay vào đó hãy xác thực scale hoặc áp dụng chính sách làm tròn được công bố.

Với tiền tệ, hãy dùng `BigDecimal` thay cho `double` khi cần biểu diễn thập phân chính xác. Đồng thời xác định rõ currency, scale hợp lệ, rounding mode và thời điểm làm tròn.

## 8. Chuẩn hóa collection và dữ liệu có thể thay đổi

Component có kiểu collection thường cần sao chép phòng vệ để record không giữ tham chiếu đến cấu trúc dữ liệu mà bên gọi có thể thay đổi.

Ví dụ:

```java
import java.util.List;
import java.util.Objects;

public record SearchRequest(String query, List<String> tags) {
    public SearchRequest {
        query = Objects.requireNonNull(query, "query").strip();
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));

        if (query.isEmpty()) {
            throw new IllegalArgumentException("query is required");
        }
    }
}
```

`List.copyOf` tạo danh sách không thể sửa đổi qua các thao tác sửa collection thông thường và tách cấu trúc danh sách khỏi nguồn đầu vào.

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("java", "record"));
SearchRequest request = new SearchRequest("compact", source);

source.add("changed");

System.out.println(request.tags()); // [java, record]

// request.tags().add("new"); // UnsupportedOperationException
```

Với collection khác, hãy chọn cách sao chép phù hợp. Ví dụ `Set.copyOf` hoặc `Map.copyOf` tạo collection không thể sửa đổi từ dữ liệu đầu vào. Cần nhớ các phương thức copy-of không tự làm bất biến sâu các phần tử bên trong. Nếu phần tử là mutable, trạng thái của nó vẫn có thể thay đổi sau khi record được tạo.

Nếu thứ tự phần tử có ý nghĩa, hãy chọn collection và cách sao chép giữ đúng thứ tự mong muốn. Không dùng `Set` nếu nghiệp vụ yêu cầu thứ tự hoặc cho phép phần tử trùng lặp.

## 9. Chuẩn hóa nhiều component có quan hệ với nhau

Một số quy tắc cần chuẩn hóa các component trước khi kiểm tra quan hệ giữa chúng. Ví dụ mã đơn vị và số tiền:

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public record Money(BigDecimal amount, String currency) {
    private static final Set<String> SUPPORTED =
            Set.of("VND", "USD", "EUR");

    public Money {
        amount = Objects.requireNonNull(amount, "amount")
                .stripTrailingZeros();

        currency = Objects.requireNonNull(currency, "currency")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }

        if (!SUPPORTED.contains(currency)) {
            throw new IllegalArgumentException("unsupported currency");
        }

        if ("VND".equals(currency)
                && amount.stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException(
                    "VND amount must be a whole number"
            );
        }
    }
}
```

Ở đây, constructor chuẩn hóa `amount` và `currency` trước, rồi xác thực miền giá trị và chính sách tương ứng. Quy tắc số nguyên đối với VND là ví dụ nghiệp vụ cụ thể; hệ thống thật cần quyết định rõ cách xử lý số lẻ, làm tròn và scale theo yêu cầu.

Khi nhiều component phụ thuộc nhau, hãy chuẩn hóa tất cả giá trị liên quan trước khi kiểm tra quan hệ. Tránh so sánh một giá trị đã chuẩn hóa với một giá trị vẫn ở dạng thô nếu điều đó có thể tạo kết quả không nhất quán.

## 10. Chuẩn hóa nên ổn định và có tính idempotent

Một phép chuẩn hóa tốt thường có tính **idempotent**: áp dụng nhiều lần cho kết quả tương tự như áp dụng một lần.

Về khái niệm, hàm chuẩn hóa `N` nên thỏa:

```text
N(N(value)) = N(value)
```

Ví dụ:

```java
public record FeatureKey(String value) {
    public FeatureKey {
        value = value.strip().toLowerCase(java.util.Locale.ROOT);
    }
}
```

Sau lần chuẩn hóa đầu tiên, chuỗi đã bỏ khoảng trắng hai đầu và chuyển chữ thường theo cùng quy tắc. Lặp lại phép chuẩn hóa không làm thay đổi kết quả.

Tính idempotent hữu ích khi dữ liệu đi qua nhiều tầng ứng dụng, được đọc rồi tạo lại record, hoặc được gửi qua nhiều service. Nó giúp giảm nguy cơ mỗi lần xử lý lại làm dữ liệu biến đổi thêm.

Tuy nhiên, không phải mọi phép biến đổi đều idempotent. Ví dụ, nối thêm hậu tố mỗi lần chạy hoặc mã hóa tăng cấp sẽ thay đổi kết quả qua từng lần áp dụng. Tránh đặt những thao tác như vậy vào constructor nếu mục tiêu chỉ là chuẩn hóa biểu diễn.

## 11. Chuẩn hóa có thể ảnh hưởng equals() và hashCode()

Record sinh `equals()` và `hashCode()` dựa trên giá trị component. Vì thế, chuẩn hóa trong constructor ảnh hưởng trực tiếp đến cách hai record được so sánh.

```java
public record UserName(String value) {
    public UserName {
        value = value.strip().toLowerCase(java.util.Locale.ROOT);
    }
}
```

```java
UserName a = new UserName(" Alice ");
UserName b = new UserName("alice");

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

Hai đầu vào khác nhau được chuẩn hóa thành cùng component value nên record bằng nhau. Đây có thể là hành vi mong muốn đối với username không phân biệt hoa/thường.

Nhưng nếu nghiệp vụ phân biệt chữ hoa/thường, chuẩn hóa lowercase sẽ làm mất thông tin và khiến hai giá trị vốn khác nhau trở thành bằng nhau. Do đó, hãy xác định chính sách equality trước khi chọn phép chuẩn hóa. Một khi record được dùng làm key trong `HashMap` hoặc phần tử `HashSet`, thay đổi chính sách chuẩn hóa có thể ảnh hưởng hành vi tra cứu và loại trùng.

## 12. Compact constructor và canonical constructor đầy đủ

Chuẩn hóa tham số có thể thực hiện bằng cả hai dạng canonical constructor:

| Đặc điểm | Compact canonical | Canonical đầy đủ |
| --- | --- | --- |
| Tham số | Suy ra từ record header | Khai báo tường minh |
| Chuẩn hóa | Gán lại tham số ngầm | Gán giá trị đã chuẩn hóa vào field |
| Gán component field | Compiler tự gán sau khi thân kết thúc bình thường | Tự gán bằng `this.field = ...` |
| Hợp với | Xác thực và chuẩn hóa component ngắn gọn | Cần điều khiển rõ việc gán từng field |

Ví dụ compact:

```java
public record UserName(String value) {
    public UserName {
        value = value.strip();
    }
}
```

Ví dụ canonical đầy đủ tương đương:

```java
public record UserName(String value) {
    public UserName(String value) {
        this.value = value.strip();
    }
}
```

Hai khai báo là hai phiên bản thay thế nhau. Trong dạng đầy đủ, bạn phải gán mọi component field `final` đúng một lần trên mọi đường thực thi kết thúc bình thường. Trong dạng compact, compiler tự thực hiện phép gán sau khi thân constructor kết thúc bình thường.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Gọi `strip()` trước khi kiểm tra null | Ném NPE ở thao tác chuỗi, thông điệp không rõ. | Kiểm tra null trước. |
| Chuẩn hóa mọi chuỗi về lowercase | Có thể làm mất phân biệt hoa/thường có ý nghĩa. | Chỉ chuẩn hóa theo hợp đồng component. |
| Dùng locale mặc định cho mã kỹ thuật | Kết quả có thể phụ thuộc máy chạy. | Dùng `Locale.ROOT` khi quy tắc không phụ thuộc ngôn ngữ. |
| Nghĩ `strip()` xóa mọi ký tự Unicode giống khoảng trắng | Một số ký tự đặc biệt không thuộc `Character.isWhitespace`. | Định nghĩa tập ký tự cần xử lý và test. |
| Dùng NFKC mà không đánh giá tác động | Có thể xóa khác biệt tương thích có ý nghĩa. | Chọn Unicode form theo hợp đồng. |
| Chuẩn hóa BigDecimal dù scale có ý nghĩa | Làm mất thông tin số chữ số thập phân ban đầu. | Xác định scale và rounding policy. |
| Giữ nguyên collection mutable đầu vào | Bên gọi có thể thay đổi trạng thái quan sát được qua record. | Sao chép phòng vệ phù hợp. |
| Nghĩ copy-of tạo bất biến sâu | Phần tử mutable bên trong vẫn có thể thay đổi. | Bảo vệ cả kiểu phần tử khi cần. |
| Chuẩn hóa không idempotent | Mỗi lần xử lý lại có thể làm dữ liệu biến đổi thêm. | Thiết kế phép chuẩn hóa ổn định. |
| Chuẩn hóa làm thay đổi equality ngoài ý muốn | Record có thể bằng nhau dù nghiệp vụ cần phân biệt. | Quyết định equality trước khi chuẩn hóa. |

## 14. Kiểm thử chuẩn hóa

Test nên kiểm tra **giá trị được lưu**, không chỉ xác nhận constructor không ném ngoại lệ.

Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class UserNameTest {

    @Test
    void stripsAndLowercasesValue() {
        UserName user = new UserName("  Alice  ");

        assertEquals("alice", user.value());
    }

    @Test
    void normalizationIsIdempotent() {
        String once = new UserName("  Alice ").value();
        String twice = new UserName(once).value();

        assertEquals(once, twice);
    }

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> new UserName(null)
        );
    }
}
```

Các trường hợp nên có trong bộ test:

- Đầu vào bình thường.
- Có khoảng trắng ở đầu/cuối.
- Chuỗi rỗng sau chuẩn hóa.
- Null nếu component bắt buộc.
- Chữ hoa/thường theo chính sách.
- Unicode ở các dạng biểu diễn tương đương nếu ứng dụng chuẩn hóa Unicode.
- Giá trị biên của số hoặc scale.
- Collection đầu vào bị thay đổi sau khi record được tạo.
- Tính idempotent của phép chuẩn hóa.
- Equality/hash code sau chuẩn hóa.

Với test Unicode, nên dùng các chuỗi literal hoặc code point cụ thể để thể hiện rõ dạng đầu vào và dạng mong đợi. Tránh dựa vào cách hiển thị của terminal vì hai chuỗi Unicode khác code point có thể trông giống hệt nhau.

## 15. Bài tập tự luyện

### Bài 1: Chuẩn hóa mã sản phẩm

Viết record `Sku(String value)` với quy tắc:

- Không nhận null.
- Bỏ khoảng trắng hai đầu.
- Chuyển chữ hoa bằng `Locale.ROOT`.
- Sau chuẩn hóa phải khớp mẫu `AA-0000`.

**Đáp án tham khảo:**

```java
import java.util.Locale;
import java.util.Objects;

public record Sku(String value) {
    public Sku {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2}-[0-9]{4}")) {
            throw new IllegalArgumentException("invalid SKU");
        }
    }
}
```

### Bài 2: Chuẩn hóa Unicode NFC

Viết record `NormalizedText(String value)` để từ chối null, bỏ khoảng trắng hai đầu và chuẩn hóa NFC.

**Đáp án tham khảo:**

```java
import java.text.Normalizer;
import java.util.Objects;

public record NormalizedText(String value) {
    public NormalizedText {
        value = Normalizer.normalize(
                Objects.requireNonNull(value, "value").strip(),
                Normalizer.Form.NFC
        );
    }
}
```

### Bài 3: Chuẩn hóa collection

Viết record `Labels(List<String> values)` để từ chối null và lưu danh sách không thể sửa đổi.

**Đáp án tham khảo:**

```java
import java.util.List;
import java.util.Objects;

public record Labels(List<String> values) {
    public Labels {
        values = List.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

Nếu từng label cũng có quy tắc riêng, hãy chuẩn hóa hoặc xác thực từng phần tử trước khi tạo danh sách kết quả. `List.copyOf` không tự chuẩn hóa phần tử.

### Bài 4: Có nên chuyển lowercase?

Một record lưu tên hiển thị của người dùng. Hệ thống cần giữ nguyên cách viết hoa/thường mà người dùng đã nhập, nhưng muốn loại bỏ khoảng trắng ở hai đầu.

**Đáp án:** Chỉ dùng `strip()`. Không gọi `toLowerCase(Locale.ROOT)` vì sẽ làm thay đổi cách viết hiển thị và có thể mất thông tin mà nghiệp vụ cần giữ.

## Ghi nhớ

Compact constructor cho phép chuẩn hóa component bằng cách gán lại các tham số ngầm. Khi thân constructor kết thúc bình thường, compiler mới gán các giá trị cuối cùng đó vào component field. Hãy phân biệt chuẩn hóa với xác thực, kiểm tra null trước khi sử dụng, chọn chính sách chuỗi/Unicode/số/collection theo hợp đồng dữ liệu và cân nhắc ảnh hưởng đến equality. Chuẩn hóa nên ổn định, có thể dự đoán và được kiểm thử qua chính giá trị accessor trả về.

## Tài liệu tham khảo

- [Java Language Specification — `8.10.4.2, Compact Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.2).
- [Java API — String.strip()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#strip()).
- [Java API — Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html).
- [Java API — Locale.ROOT](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html#ROOT).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
