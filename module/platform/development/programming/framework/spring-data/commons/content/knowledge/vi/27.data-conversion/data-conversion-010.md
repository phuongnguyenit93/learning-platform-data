# Kiểm thử đối xứng đọc–ghi và tương thích dữ liệu cũ

## 1. Vì sao converter cần được kiểm thử như một hợp đồng dữ liệu?

Trong chương **Chuyển đổi dữ liệu** của module **SPRING_DATA_COMMONS**, converter nối mô hình Java với biểu diễn mà tầng lưu trữ hiểu được. Một thay đổi nhỏ như đổi cách ghi số tiền, tên enum hoặc múi giờ có thể tác động đến dữ liệu đã tồn tại, truy vấn repository và những phiên bản ứng dụng đang chạy song song.

Spring Data Commons cung cấp hạ tầng `CustomConversions` và các annotation định hướng đọc/ghi. Converter cần được đăng ký tường minh vào cơ chế conversion của module tương ứng; chỉ đặt annotation hoặc có class trong classpath chưa đủ. [Spring Data Commons: Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html)

Mục tiêu kiểm thử gồm ba câu hỏi khác nhau:

1. Ghi rồi đọc có giữ nguyên ý nghĩa nghiệp vụ không?
2. Đọc dữ liệu cũ có cho ra giá trị đúng, theo chính sách đã công bố không?
3. Đường persistence thực tế có sử dụng đúng converter và giữ hợp đồng của database không?

Bài sử dụng một giá trị `Money` để minh họa. Đây là lựa chọn phục vụ kiểm thử converter, không phải khuyến nghị lưu mọi số tiền thành chuỗi. Kiểu lưu trữ phải phù hợp với nhu cầu tính toán, tìm kiếm và sắp xếp của từng kho dữ liệu.

## 2. Xác định chính xác “đối xứng” nghĩa là gì

Gọi:

- `D` là tập giá trị domain hợp lệ.
- `S` là tập biểu diễn lưu trữ được reader hỗ trợ.
- `W: D → S` là hàm ghi.
- `R: S → D` là hàm đọc.
- `N` là quy tắc chuẩn hóa domain đã được chấp nhận.
- `C(s) = W(R(s))` là dạng lưu trữ chuẩn hóa của một biểu diễn hợp lệ.

### 2.1. Đối xứng từ domain

```text
R(W(x)) = N(x)
```

Nếu domain đã được chuẩn hóa ngay khi tạo object, có thể kiểm tra `R(W(x)).equals(x)`. Nếu domain cho phép nhiều cách biểu diễn cùng một ý nghĩa, cần so sánh theo hợp đồng nghiệp vụ thay vì theo identity của object.

Ví dụ, số `12.3` và `12.30` có thể là cùng số tiền nhưng có scale khác nhau. Với `BigDecimal`, `equals()` xét cả giá trị và scale, còn so sánh thứ tự bằng `compareTo()` xem các giá trị bằng nhau về số học là bằng nhau. Test phải chọn chủ đích, không sửa assertion chỉ để làm test xanh. [Java API: BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)

### 2.2. Đối xứng từ biểu diễn lưu trữ

```text
W(R(s)) = C(s)
```

Không nhất thiết yêu cầu kết quả bằng nguyên chuỗi đầu vào. Nếu reader chấp nhận dữ liệu cũ `USD 12.3` và writer hiện tại ghi `v2|USD|12.30`, việc thay đổi chuỗi có thể là chuẩn hóa được thiết kế trước.

Dạng chuẩn cần ổn định:

```text
C(C(s)) = C(s)
```

Thuộc tính này gọi là tính lũy đẳng của chuẩn hóa: chạy thêm một vòng đọc–ghi không tiếp tục biến đổi dữ liệu.

### 2.3. Khi không thể yêu cầu bằng nhau tuyệt đối

Nếu storage chỉ giữ mili giây nhưng domain giữ nano giây, phép chuyển đổi đã làm mất độ chính xác. Cần chọn một trong các hướng: tăng khả năng lưu trữ, giới hạn domain ngay từ đầu hoặc định nghĩa rõ phép chuẩn hóa có mất dữ liệu được nghiệp vụ chấp nhận.

Nếu writer mã hóa với nonce ngẫu nhiên, hai lần ghi cùng giá trị có thể cho ra byte khác nhau. Khi đó, kiểm tra khả năng khôi phục và ý nghĩa dữ liệu; không áp dụng máy móc assertion bằng nhau giữa ciphertext của hai lần ghi.

Một epsilon tùy ý không phải lời giải chung. Sai số phải có đơn vị, giới hạn và lý do nghiệp vụ cụ thể.

## 3. Round-trip hiện tại không chứng minh tương thích lịch sử

Gọi `R_old`, `W_old` là reader/writer cũ và `R_new`, `W_new` là reader/writer mới.

| Hợp đồng | Điều cần chứng minh |
| --- | --- |
| `R_new(W_new(x)) = N(x)` | Dữ liệu vừa ghi bằng phiên bản mới có thể đọc đúng. |
| `R_new(W_old(x)) = N(x)` | Phiên bản mới đọc được dữ liệu do phiên bản cũ ghi trong phạm vi hỗ trợ. |
| `R_old(W_new(x))` có kết quả hợp lệ | Phiên bản cũ có đọc được dữ liệu mới khi cùng hoạt động hoặc rollback hay không. |
| `W_new(R_new(s_old)) = C(s_old)` | Dữ liệu cũ được chuyển sang dạng chuẩn theo đúng kỳ vọng. |

Hai chiều tương thích giữa phiên bản không tự kéo theo nhau. Một reader mới đọc cả hai định dạng không làm reader cũ hiểu được định dạng mới.

Ngoài ra, writer và reader mới có thể cùng sai theo cách bù trừ. Chẳng hạn writer nhân số tiền với `1000` và reader chia cho `1000`: round-trip vẫn trả lại giá trị ban đầu, nhưng dữ liệu thực tế không còn đúng hợp đồng với hệ thống khác.

Vì vậy cần đồng thời có test round-trip, test đầu ra cố định và fixture lịch sử độc lập với writer hiện tại.

## 4. Đặt hợp đồng cho ví dụ Money

Ví dụ giới hạn nghiệp vụ như sau:

| Thành phần | Chính sách minh họa |
| --- | --- |
| Tiền tệ | Chỉ `USD` và `VND`; tên được trim và đổi sang chữ hoa bằng `Locale.ROOT`. |
| Scale của USD | Hai chữ số thập phân. |
| Scale của VND | Không có chữ số thập phân. |
| Làm tròn | Không tự làm tròn; giá trị cần làm tròn sẽ bị từ chối. |
| Độ lớn | Precision sau chuẩn hóa không vượt quá 18. |
| Giá trị âm | Được phép để biểu diễn điều chỉnh hoặc hoàn tiền. |
| Định dạng cũ | `USD 12.3`, cho phép khoảng trắng phân cách và ở hai đầu chuỗi. |
| Định dạng ghi hiện tại | `v2|USD|12.30`. |
| Cú pháp số được đọc | Số thập phân thường, không phân cách hàng nghìn và không dùng dạng số mũ. |
| Version lạ | Từ chối rõ ràng, không đoán theo định dạng cũ. |
| Đầu vào quá dài | Reader từ chối chuỗi dài hơn 80 ký tự trong ví dụ. |

Đây là hợp đồng của bài toán giả định. Không dùng bảng này như danh mục quy tắc đầy đủ cho mọi tiền tệ.

Lựa chọn dấu `|` phù hợp ở đây vì tiền tệ và số tiền bị giới hạn theo grammar. Nếu dữ liệu chứa văn bản tự do có thể mang dấu phân cách, cần thiết kế escaping hoặc chọn một cấu trúc tuần tự hóa phù hợp hơn.

## 5. Cặp converter minh họa

Mã dưới đây dùng Java record, phù hợp với Java 17 trở lên, cùng API conversion của Spring Framework và Spring Data. Tất cả kiểu được đặt trong một lớp bao ngoài để thể hiện trọn ví dụ.

```java
package example.conversion;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

public final class MoneyConversions {

    private MoneyConversions() {
    }

    public record Money(String currency, BigDecimal amount) {

        public Money {
            currency = Objects.requireNonNull(currency, "currency")
                    .trim()
                    .toUpperCase(Locale.ROOT);
            amount = Objects.requireNonNull(amount, "amount");

            int scale = switch (currency) {
                case "USD" -> 2;
                case "VND" -> 0;
                default -> throw new IllegalArgumentException(
                        "Unsupported currency");
            };

            try {
                amount = amount.setScale(scale, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                        "Amount requires rounding", ex);
            }

            if (amount.precision() > 18) {
                throw new IllegalArgumentException("Amount is too large");
            }
        }
    }

    @WritingConverter
    public static final class MoneyWriter implements Converter<Money, String> {

        @Override
        public String convert(Money source) {
            Objects.requireNonNull(source, "source");
            return "v2|" + source.currency()
                    + "|" + source.amount().toPlainString();
        }
    }

    @ReadingConverter
    public static final class MoneyReader implements Converter<String, Money> {

        private static final Pattern DECIMAL = Pattern.compile(
                "-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?");

        @Override
        public Money convert(String source) {
            Objects.requireNonNull(source, "source");

            if (source.length() > 80) {
                throw new IllegalArgumentException("Money input is too long");
            }

            if (source.indexOf('|') >= 0) {
                String[] parts = source.split("\\|", -1);
                if (parts.length != 3) {
                    throw new IllegalArgumentException("Invalid money structure");
                }
                if (!"v2".equals(parts[0])) {
                    throw new IllegalArgumentException("Unsupported money version");
                }
                return parse(parts[1], parts[2]);
            }

            String[] legacy = source.trim().split("\\s+");
            if (legacy.length != 2) {
                throw new IllegalArgumentException("Invalid legacy money");
            }
            return parse(legacy[0], legacy[1]);
        }

        private Money parse(String currency, String amount) {
            if (!DECIMAL.matcher(amount).matches()) {
                throw new IllegalArgumentException("Invalid decimal syntax");
            }
            return new Money(currency, new BigDecimal(amount));
        }
    }
}
```

Các điểm có chủ đích trong thiết kế:

- Domain chuẩn hóa scale ngay trong constructor nên record equality phù hợp với hợp đồng đã chọn.
- Writer chỉ có một định dạng đầu ra hiện tại.
- Reader chấp nhận định dạng cũ nhưng không dùng nhánh legacy để che lỗi version mới.
- `split(..., -1)` giữ phần rỗng ở cuối để dữ liệu thiếu amount không bị bỏ qua khi kiểm tra cấu trúc.
- Reader và writer không giữ trạng thái thay đổi theo từng lần gọi.

SPI `Converter<S,T>` yêu cầu triển khai an toàn khi dùng đồng thời; đầu vào được framework truyền cho `convert()` theo hợp đồng không null. Việc gọi trực tiếp method trong unit test là một ranh giới khác; ví dụ dùng `requireNonNull` để báo lỗi sớm. [Spring Framework: Converter SPI](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)

## 6. Kiểm thử converter bằng kỳ vọng độc lập

Các ví dụ kiểm thử sử dụng JUnit Jupiter. Parameterized test cần module `junit-jupiter-params`; dùng phiên bản phù hợp với JDK và bộ dependency của dự án. [JUnit: Parameterized Tests](https://docs.junit.org/current/writing-tests/parameterized-classes-and-tests.html)

### 6.1. Bộ kiểm thử mẫu

```java
package example.conversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import example.conversion.MoneyConversions.Money;
import example.conversion.MoneyConversions.MoneyReader;
import example.conversion.MoneyConversions.MoneyWriter;
import java.math.BigDecimal;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;

class MoneyConversionsTest {

    private final MoneyReader reader = new MoneyReader();
    private final MoneyWriter writer = new MoneyWriter();

    static Stream<Arguments> storageFixtures() {
        return Stream.of(
                Arguments.of("USD 12.3", "USD", "12.30", "v2|USD|12.30"),
                Arguments.of(" usd   12.30 ", "USD", "12.30", "v2|USD|12.30"),
                Arguments.of("VND 120000.0", "VND", "120000", "v2|VND|120000"),
                Arguments.of("USD -4.5", "USD", "-4.50", "v2|USD|-4.50"),
                Arguments.of("USD -0.00", "USD", "0.00", "v2|USD|0.00"),
                Arguments.of("v2|USD|12.30", "USD", "12.30", "v2|USD|12.30"),
                Arguments.of("v2|VND|0", "VND", "0", "v2|VND|0")
        );
    }

    @ParameterizedTest
    @MethodSource("storageFixtures")
    void readsExpectedValueAndWritesCanonicalForm(
            String stored, String currency, String amount, String canonical) {
        Money value = reader.convert(stored);

        assertEquals(currency, value.currency());
        assertEquals(new BigDecimal(amount), value.amount());
        assertEquals(canonical, writer.convert(value));
    }

    @ParameterizedTest
    @MethodSource("storageFixtures")
    void normalizationIsIdempotent(
            String stored, String currency, String amount, String canonical) {
        String first = writer.convert(reader.convert(stored));
        String second = writer.convert(reader.convert(first));

        assertEquals(canonical, first);
        assertEquals(first, second);
    }

    @Test
    void writesThePublishedStorageFormat() {
        Money value = new Money("usd", new BigDecimal("12.3"));

        assertEquals("v2|USD|12.30", writer.convert(value));
    }

    @Test
    void roundTripsManyValidDomainValues() {
        for (long n = -1000; n <= 1000; n++) {
            Money usd = new Money("USD", BigDecimal.valueOf(n, 2));
            Money vnd = new Money("VND", BigDecimal.valueOf(n));

            assertEquals(usd, reader.convert(writer.convert(usd)));
            assertEquals(vnd, reader.convert(writer.convert(vnd)));
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "", "USD", "USD twelve", "USD 01.00", "USD 1E3",
            "v3|USD|12.30", "v2|USD|", "v2|USD|12.30|extra",
            "v2|XXX|12.30", "v2|USD|1.001", "v2|VND|1.5",
            "v2|USD|12,30", "v2|USD|10000000000000000.00"
    })
    void rejectsUnsupportedOrMalformedValues(String stored) {
        assertThrows(IllegalArgumentException.class,
                () -> reader.convert(stored));
    }

    @Test
    void rejectsOversizedInput() {
        String stored = "USD " + "1".repeat(81);

        assertThrows(IllegalArgumentException.class,
                () -> reader.convert(stored));
    }
}
```

`storageFixtures()` chứa dữ liệu cố định và đầu ra kỳ vọng tường minh. Nó không gọi writer hiện tại để tạo đầu vào cũ; nhờ đó, một thay đổi writer không âm thầm viết lại lịch sử trong test.

Vòng lặp domain bao phủ nhiều giá trị có thể lặp lại kết quả ổn định. Đây là tập mẫu có hệ thống, không phải bằng chứng cho toàn bộ không gian giá trị. Có thể bổ sung property-based testing để sinh nhiều trường hợp hơn, với seed có thể ghi nhận và tái hiện lỗi.

### 6.2. Những trường hợp biên nên bổ sung

| Nhóm dữ liệu | Kiểm tra cần có |
| --- | --- |
| Biên precision | Giá trị lớn nhất được hỗ trợ, giá trị vượt biên, âm và dương. |
| Scale | Giá trị cần thêm số 0, bỏ số 0 thừa và giá trị buộc phải làm tròn. |
| Null tại tầng mapping | Thuộc tính null, cột SQL NULL, field document thiếu; phân biệt theo store. |
| Cấu trúc | Thiếu thành phần, thừa thành phần, version không hỗ trợ. |
| Ngôn ngữ và môi trường | Locale khác nhau, cấu hình môi trường không làm thay đổi dạng chuẩn. |
| Dữ liệu sai lịch sử | Dữ liệu từng được ghi lỗi cần chính sách xử lý riêng, không tự coi là hợp lệ. |

Với converter thời gian, bổ sung thời điểm quanh chuyển đổi DST, offset, múi giờ và giới hạn độ chính xác của storage. Converter mặc định cho một số kiểu thời gian cục bộ có thể phụ thuộc múi giờ hệ thống; đây là lý do cần cố định môi trường hoặc cấu hình rõ chiến lược. [Commons: các converter thời gian mặc định](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html)

## 7. Tách ba tầng kiểm thử

### 7.1. Tầng hàm converter

Gọi trực tiếp reader/writer để kiểm tra grammar, chuẩn hóa, lỗi dữ liệu và các đẳng thức đã định nghĩa. Tầng này nhanh và chỉ ra lỗi thuật toán rõ ràng.

Kết quả đạt chưa chứng minh converter đã được Spring Data sử dụng. Nó cũng chưa kiểm tra giới hạn của cột, kiểu BSON hoặc cách driver trả giá trị.

### 7.2. Tầng mapping và đăng ký

Khởi tạo cấu hình mapping của module thực tế rồi kiểm tra thuộc tính `Money` được đọc/ghi bằng cặp converter mong muốn. Cần phát hiện ít nhất các tình huống sau:

- Quên đăng ký writer hoặc reader.
- Đăng ký sai chiều hoặc sai cặp source/target.
- Một converter tổng quát khác cạnh tranh với cặp converter dự kiến.
- Mapper xử lý `Money` như object lồng thay vì giá trị đơn theo thiết kế.

`CustomConversions` duy trì thông tin chuyển đổi và các kiểu được xem là simple type. Vì vậy đăng ký converter có thể ảnh hưởng tới cách mapper nhìn nhận một kiểu, không chỉ lời gọi chuyển đổi riêng lẻ. [API CustomConversions](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/CustomConversions.html)

### 7.3. Tầng repository và database thật

Dùng module repository, driver và loại database phù hợp với môi trường đích để xác nhận:

1. Dữ liệu lưu thực tế có đúng kiểu và giá trị không?
2. Đọc từ storage có khôi phục đúng domain không?
3. Dữ liệu cũ được chèn trực tiếp có đọc được không?
4. Cập nhật sau khi đọc dữ liệu cũ có tạo đúng dạng chuẩn không?
5. Các truy vấn liên quan có nhìn thấy cả dữ liệu cũ và mới theo yêu cầu không?

Không lấy object vừa `save()` trả về làm bằng chứng duy nhất. Cần đọc lại qua đường truy cập đủ độc lập theo đặc điểm module; nếu tầng có cache hoặc persistence context, phải kiểm soát chúng để tránh chỉ nhận lại trạng thái trong bộ nhớ.

## 8. Kiểm thử tích hợp với fixture lưu trữ cũ

### 8.1. Bối cảnh Spring Data JDBC

Với ví dụ JDBC, chọn một thuộc tính `Money` ánh xạ vào một cột chuỗi. Tài liệu JDBC mô tả custom converter cho chuyển đổi giá trị thuộc tính; không suy ra một `Converter` bất kỳ sẽ tách một object thành nhiều cột. Việc đăng ký phải đi qua cấu hình conversion được module và phiên bản đang dùng hỗ trợ. [Spring Data JDBC: Custom Converters](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.custom-converters)

Domain minh họa:

```java
package example.conversion;

import example.conversion.MoneyConversions.Money;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("payment")
public record Payment(
        @Id @Column("id") Long id,
        @Column("amount") Money amount) {
}
```

Repository minh họa:

```java
package example.conversion;

import org.springframework.data.repository.CrudRepository;

public interface PaymentRepository extends CrudRepository<Payment, Long> {
}
```

Cấu hình test cần đăng ký `MoneyReader` và `MoneyWriter`. Chỉ đưa converter vào một `DefaultConversionService` dùng riêng cho test không chứng minh `JdbcConverter` của ứng dụng đang dùng cấu hình đó.

### 8.2. Chèn dữ liệu cũ bằng đường độc lập

Giả sử schema test đã có bảng với các tên được quote chính xác là `payment`, `id`, `amount`; `id` là khóa chính kiểu số và `amount` là cột chuỗi đủ dài. Đoạn dưới đặt trong method kiểm thử đã được cung cấp `JdbcTemplate jdbc` và `PaymentRepository repository`, với các static import assertion cần thiết:

```java
long id = 81010L;

jdbc.update("""
        INSERT INTO "payment" ("id", "amount") VALUES (?, ?)
        """, id, "USD 12.3");

Payment loaded = repository.findById(id).orElseThrow();

assertEquals("USD", loaded.amount().currency());
assertEquals(new BigDecimal("12.30"), loaded.amount().amount());

repository.save(loaded);

String raw = jdbc.queryForObject("""
        SELECT "amount" FROM "payment" WHERE "id" = ?
        """, String.class, id);

assertEquals("v2|USD|12.30", raw);
```

Điểm quan trọng là chuỗi cũ được chèn trực tiếp, không đi qua writer mới. Giá trị sau lưu được đọc thô để kiểm chứng hợp đồng storage, không đi qua reader có thể bù trừ cho lỗi writer.

Nếu schema đích dùng cách đặt tên, quoting hoặc kiểu khóa khác, điều chỉnh fixture đúng với schema đó. Với document store, có thể dùng driver hoặc native collection API để chèn document cũ; vẫn giữ nguyên nguyên tắc tách khỏi converter hiện tại.

Test cần quản lý dọn dữ liệu hoặc rollback theo cơ chế của môi trường kiểm thử để chạy lặp lại được. Không giả định mọi store cùng hỗ trợ transaction hoặc cùng có cơ chế rollback test như JDBC.

### 8.3. Phân biệt null, thiếu field và dữ liệu hỏng

Với document, thiếu field có thể là hiện tượng bình thường của dữ liệu từ schema cũ; với SQL, thêm cột mới có thể để lại NULL. Chính sách cần nói rõ liệu trường hợp đó là giá trị tùy chọn, giá trị mặc định hợp lệ hay lỗi cần xử lý.

Không dùng một `catch (Exception)` rồi trả `Money("VND", ZERO)` cho mọi lỗi. Cách đó đánh đồng không có dữ liệu với dữ liệu sai và có thể làm mất ý nghĩa tài chính khi object được lưu lại.

## 9. Bộ fixture lịch sử phải độc lập và có nguồn gốc

Một bộ fixture tốt nên thể hiện ít nhất:

| Thông tin | Ví dụ |
| --- | --- |
| Định dạng | Chuỗi legacy không có version, chuỗi v2, document schema cũ. |
| Nguồn tạo | Bản phát hành đã phát sinh biểu diễn đó hoặc đặc tả cũ được xác nhận. |
| Ý nghĩa kỳ vọng | `USD`, amount `12.30`. |
| Kết quả ghi lại | `v2|USD|12.30` hoặc chính sách giữ nguyên được chọn. |
| Phạm vi hỗ trợ | Những phiên bản dữ liệu còn cần đọc. |
| Trường hợp lỗi | Version lạ, mã tiền tệ không hỗ trợ, dữ liệu bị cắt. |

Trong dự án thực tế, fixture có thể được lưu bằng file dữ liệu kiểm thử hoặc literal đã được quản lý phiên bản. Chỉ lấy mẫu dữ liệu sau khi xử lý các thông tin nhạy cảm phù hợp với dự án.

Không tạo lại toàn bộ fixture bằng writer mới mỗi khi test thất bại. Khi phải thay đổi kỳ vọng, giải thích rõ hợp đồng nào thay đổi và tác động đến bản ghi đã tồn tại.

Nếu dữ liệu từng do nhiều writer tạo ra, cần fixture từ từng nguồn: API chính, batch import, tác vụ nền, công cụ quản trị và phiên bản cũ. Một phiên bản ứng dụng có thể đã có nhiều đường ghi với hành vi khác nhau.

## 10. Tương thích truy vấn là một yêu cầu riêng

Reader có thể đọc hai định dạng nhưng truy vấn equality vẫn có thể chỉ tìm được một định dạng.

Ví dụ trong thời gian chuyển đổi, storage đồng thời chứa:

```text
USD 12.3
v2|USD|12.30
```

Nếu tham số `Money("USD", 12.30)` được đường truy vấn chuyển thành chuỗi mới, điều kiện equality với chuỗi đó không tự khớp chuỗi cũ. Round-trip converter vẫn đạt trong khi kết quả tìm kiếm thiếu dữ liệu.

Cần có test cho đường truy vấn thực tế mà module hỗ trợ:

- Derived query có tham số thuộc tính đã được chuyển đổi.
- Query by Example nếu module hỗ trợ với kiểu và cấu trúc đang dùng.
- Truy vấn khai báo hoặc repository fragment có điều kiện viết tay.
- Projection đọc toàn bộ giá trị hoặc chỉ một phần dữ liệu.
- Phân trang và sắp xếp trên dữ liệu chuyển đổi.

Không giả định mọi đường trên đều gọi converter giống nhau. Ví dụ, custom SQL chọn một biểu thức tính toán hoặc trả scalar có thể có đường materialize khác với đọc đầy đủ aggregate.

Chuỗi tiền tệ cũng không có thứ tự số học mong muốn: sắp xếp từ điển có thể đặt `v2|USD|100.00` trước `v2|USD|20.00`. Nếu nghiệp vụ cần sort, range query hoặc tính tổng số tiền trong database, cần lựa chọn biểu diễn và truy vấn đáp ứng yêu cầu đó.

Trong giai đoạn tồn tại hai định dạng, giải pháp có thể là migration trước khi đổi truy vấn, điều kiện truy vấn hỗ trợ cả hai biểu diễn hoặc trường lưu trữ được thiết kế lại. Chọn theo khả năng của store và kiểm tra lại hiệu quả index, tổng số phần tử và ranh giới các trang.

## 11. Triển khai nhiều phiên bản và khả năng rollback

Một lộ trình thay đổi định dạng có thể gồm:

1. **Mở rộng reader:** triển khai reader hiểu cả định dạng cũ và mới, trong khi writer vẫn ghi định dạng cũ.
2. **Xác nhận các consumer:** API, batch job và các instance còn hoạt động đã có khả năng đọc định dạng mới.
3. **Chuyển writer:** bắt đầu ghi định dạng mới, giữ khả năng đọc dữ liệu cũ.
4. **Chuyển đổi dữ liệu tồn:** migration có kiểm soát và có khả năng chạy lại.
5. **Thu hẹp hỗ trợ:** chỉ loại nhánh đọc cũ sau khi đáp ứng điều kiện lưu trữ và phục hồi của hệ thống.

`MoneyWriter` trong bài minh họa trạng thái sau bước chuyển writer. Để thực hiện giai đoạn đầu, cần tiếp tục dùng writer legacy hoặc cơ chế chọn định dạng theo cấu hình được thiết kế riêng; cặp converter hiện tại không tự tạo lộ trình triển khai này.

Bộ kiểm thử triển khai cần trả lời rõ bản rollback nào vẫn đọc được dữ liệu sau bước 3. Nếu reader cũ chỉ hiểu `USD 12.3`, việc rollback code không tự biến các chuỗi `v2|...` về định dạng cũ.

Không chỉ xét dữ liệu đang nằm trong database chính. Bản sao lưu, file import, thông điệp chờ xử lý và job bị trì hoãn có thể đưa biểu diễn cũ trở lại. Thời điểm xóa hỗ trợ legacy cần dựa trên vòng đời thực tế của các nguồn này.

## 12. Đọc được dữ liệu cũ khác với ghi lại an toàn

Converter không giải quyết mọi vấn đề của migration hoặc cập nhật entity.

| Tình huống | Kiểm thử bổ sung |
| --- | --- |
| Reader áp giá trị mặc định cho field cũ bị thiếu | Lưu lại không vô tình thay đổi ý nghĩa bản ghi. |
| Reader object không biết field do phiên bản mới thêm | Luồng ghi lại có bảo toàn hay làm mất field đó theo đúng chính sách. |
| Migration đọc rồi ghi trong lúc có người dùng cập nhật | Cơ chế version hoặc điều kiện ghi không làm mất cập nhật mới. |
| Repository fragment ghi trực tiếp | Conversion, auditing và metadata cần thiết vẫn được xử lý đúng. |
| Chuẩn hóa chạy nhiều lần | Kết quả storage ổn định và không tạo tác dụng phụ không mong muốn. |

Với converter toàn bộ document, chỉ biết đọc một số field không đảm bảo ghi lại sẽ giữ field lạ. Phải kiểm tra cấu trúc lưu thực tế sau cập nhật hoặc chọn chiến lược cập nhật từng phần phù hợp. Đây là vấn đề về tính toàn vẹn của đường ghi, tách khỏi việc `MoneyReader` phân tích một chuỗi thành công.

Khi migration chạy lại, lũy đẳng của dữ liệu cũng chưa chắc đồng nghĩa không có tác dụng phụ: auditing, event và version có thể thay đổi theo thao tác persistence. Thiết kế migration cần phân biệt chuẩn hóa nội dung với hành vi của từng lần ghi.

## 13. Dấu hiệu một bộ kiểm thử còn thiếu

| Dấu hiệu | Khoảng trống thường gặp |
| --- | --- |
| Chỉ có `read(write(value))` | Thiếu kỳ vọng storage độc lập và fixture cũ. |
| Tất cả fixture được tạo bằng writer mới | Chưa kiểm tra dữ liệu lịch sử thực sự. |
| Test converter đạt nhưng lưu repository lỗi | Thiếu kiểm tra đăng ký, mapping hoặc driver. |
| Chỉ kiểm tra object `save()` trả về | Chưa xác nhận storage thực tế và đường đọc độc lập. |
| Đọc cũ đạt nhưng query không tìm thấy cũ | Thiếu hợp đồng tương thích truy vấn. |
| Rollback làm một phần dữ liệu không đọc được | Chưa kiểm tra chiều reader cũ với writer mới. |
| Ghi lại làm mất field hoặc đổi mặc định | Thiếu kiểm tra toàn vẹn khi cập nhật. |
| Đổi assertion để bỏ qua mọi chênh lệch số | Chưa xác định chuẩn hóa và độ chính xác nghiệp vụ. |

Một bộ kiểm thử có giá trị phải gắn từng assertion với một lời hứa cụ thể: giữ ý nghĩa domain, ghi đúng dạng lưu trữ, đọc được dữ liệu lịch sử trong phạm vi hỗ trợ và thực thi nhất quán qua module repository đang dùng. Kết hợp các lớp kiểm thử đó mới giúp đánh giá thay đổi converter trước khi áp dụng lên dữ liệu đã tồn tại.