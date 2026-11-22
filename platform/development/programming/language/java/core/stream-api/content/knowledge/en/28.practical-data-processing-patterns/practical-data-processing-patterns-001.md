# Làm sạch, chuẩn hóa và loại dữ liệu không hợp lệ

Trong ứng dụng thực tế, dữ liệu hiếm khi đi vào hệ thống dưới dạng hoàn hảo. Một đơn hàng có thể chứa mã sản phẩm thừa khoảng trắng, số lượng ghi bằng chuỗi, ngày không tồn tại, số tiền sai định dạng hoặc khóa định danh bị trùng. Trước khi dùng dữ liệu ấy để thống kê, phân nhóm hoặc ghi xuống cơ sở dữ liệu, cần **làm sạch, chuẩn hóa, kiểm tra tính hợp lệ và xác định cách xử lý bản ghi lỗi**.

**Java Stream API** giúp mô tả quy trình này thành một pipeline khai báo gồm các phép toán trung gian *lazy* như `map`, `filter`, `flatMap`, rồi kích hoạt bằng terminal operation như `collect`. Tuy nhiên, một pipeline viết ngắn chưa chắc đã an toàn: `filter` làm mất thông tin về dữ liệu bị loại, phép chuẩn hóa tùy tiện có thể thay đổi ý nghĩa nghiệp vụ, và parse trực tiếp trong `map` có thể khiến một bản ghi lỗi làm hỏng cả lô.

Bài học thuộc chương **Mẫu xử lý dữ liệu thực tế**. Mục tiêu là xây một luồng xử lý rõ ràng, kiểm thử được, ưu tiên hàm thuần, phân biệt bản ghi hợp lệ với bản ghi bị từ chối, đồng thời giữ được nguyên nhân lỗi để đối soát.

## 1. Xác định hợp đồng trước khi viết pipeline

Giả sử đầu vào là những đơn hàng thô có năm trường: mã đơn, mã sản phẩm, số lượng, đơn giá và ngày đặt. Người dùng có thể nhập tất cả dưới dạng chuỗi.

| Bản ghi | Mã đơn | Mã sản phẩm | Số lượng | Đơn giá | Ngày | Kết quả dự kiến |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `" a-001 "` | `" sku-01 "` | `"2"` | `"15.50"` | `"2026-03-05"` | Hợp lệ sau chuẩn hóa. |
| 2 | `"A-002"` | `"SKU-02"` | `"0"` | `"4.50"` | `"2026-03-05"` | Loại: số lượng phải dương. |
| 3 | `"A-003"` | `"SKU-03"` | `"1"` | `"7.20"` | `"2026-02-30"` | Loại: ngày không hợp lệ. |
| 4 | `"A-004"` | `"SKU-04"` | `"3"` | `"7.20"` | `"2026-03-06"` | Hợp lệ. |
| 5 | `"A-005"` | `"SKU-05"` | `"1"` | `"oops"` | `"2026-03-06"` | Loại: đơn giá sai định dạng. |

**Quy tắc nghiệp vụ giả định cho bài tập:** mã đơn và SKU không phân biệt hoa/thường, chỉ chứa `A–Z`, chữ số hoặc dấu gạch nối; số lượng là số nguyên dương không quá sáu chữ số; giá không âm có tối đa hai chữ số thập phân; ngày dùng ISO `yyyy-MM-dd`. Đây là **quy tắc của ví dụ**, không phải định nghĩa đúng cho mọi hệ thống thương mại.

Một pipeline tốt phải làm rõ:

1. **Dữ liệu đầu vào là gì?** Đối tượng Java, văn bản CSV/JSON, hay luồng tệp? Ai chịu trách nhiệm tách trường?
2. **Chuẩn hóa được phép thay đổi điều gì?** Có được bỏ khoảng trắng và đổi chữ hoa hay không?
3. **Điều kiện nào là lỗi?** Bỏ trống, sai kiểu, ngoài miền giá trị, sai ngày, trùng khóa hay không khớp danh mục?
4. **Một bản ghi lỗi được xử lý thế nào?** Từ chối có lý do, yêu cầu sửa, giữ vùng cách ly (*quarantine*) hay dừng cả lô?
5. **Kết quả cần cho ai?** Danh sách sạch để tính toán, danh sách lỗi để hiển thị, hay cả hai để kiểm toán?

## 2. Phân biệt làm sạch, chuẩn hóa, xác thực và loại bỏ

Các bước liên quan nhưng không đồng nghĩa:

| Bước | Ví dụ | Mục đích |
| --- | --- | --- |
| **Làm sạch** (*cleaning*) | Bỏ khoảng trắng đầu/cuối mã đơn. | Loại nhiễu nhập liệu đã được phép loại. |
| **Chuẩn hóa** (*normalization*) | `"sku-01"` → `"SKU-01"`. | Đưa các biểu diễn tương đương về một dạng thống nhất. |
| **Xác thực** (*validation*) | Kiểm tra số lượng lớn hơn 0, ngày tồn tại. | Xác nhận dữ liệu đáp ứng quy tắc. |
| **Chuyển kiểu** (*parsing*) | `"2"` → `int 2`; `"15.50"` → `BigDecimal`. | Chuyển dạng lưu trữ sang kiểu nghiệp vụ. |
| **Loại bỏ/cách ly** (*rejection/quarantine*) | Trả lý do `quantity must be positive`. | Không cho dữ liệu sai đi vào báo cáo và không mất dấu vết lỗi. |

Một sơ đồ xử lý đề xuất:

```text
Nguồn dữ liệu thô
       |
       v
Tách bản ghi và trường theo đúng định dạng nguồn
       |
       v
Làm sạch / chuẩn hóa có kiểm soát
       |
       v
Kiểm tra trường bắt buộc, định dạng và miền giá trị
       |
       v
Chuyển kiểu và xác thực quy tắc liên trường
       |
       v
Kết quả phân loại: Valid(order) hoặc Invalid(reason)
       |                                   |
       v                                   v
Danh sách hợp lệ                      Danh sách lỗi
       |                                   |
       +--> thống kê, grouping, DB         +--> báo cáo, sửa dữ liệu
```

Không bắt buộc mọi bước là một lệnh `map` hoặc `filter` riêng. Với dữ liệu có thể sai định dạng, một hàm `parseAndValidate` trả về **giá trị hoặc lỗi** thường rõ ràng hơn việc rải các `try/catch` khó theo dõi trong nhiều lambda.

## 3. Chuẩn hóa chuỗi phải theo ngữ nghĩa của trường

Ví dụ chuẩn hóa mã định danh không phân biệt hoa/thường (Java 11+):

```java
import java.util.Locale;

static String normalizeBusinessKey(String raw) {
    return raw == null
        ? null
        : raw.strip().toUpperCase(Locale.ROOT);
}

System.out.println(normalizeBusinessKey("  sku-01 ")); // SKU-01
```

`strip()` loại các ký tự khoảng trắng đầu/cuối theo quy tắc `Character.isWhitespace` của Java; `trim()` có quy tắc cũ dựa vào các ký tự có mã không vượt `U+0020`. Chúng **không tương đương hoàn toàn** và không phải lời giải cho mọi ký tự trắng Unicode. Nếu nguồn có non-breaking space hoặc ký tự điều khiển đặc biệt, cần chính sách riêng.

`Locale.ROOT` giúp phép chuyển hoa/thường không phụ thuộc locale mặc định của máy. Tuy nhiên, **không được tự chuyển chữ hoa với mọi trường**:

- Mã SKU được định nghĩa không phân biệt hoa/thường có thể chuẩn hóa về chữ hoa.
- Mật khẩu, chữ ký số hoặc chuỗi bí mật phải được xử lý theo quy tắc xác thực riêng; tự sửa khác đi có thể phá vỡ nghĩa.
- Email không phải lúc nào cũng cho phép coi **toàn bộ địa chỉ** là không phân biệt hoa/thường; quy tắc của phần local-part cần được cân nhắc theo hệ thống nhận thư.
- Tên hiển thị nên giữ nguyên biểu diễn phù hợp với yêu cầu ngôn ngữ và giao diện.

### Chuẩn hóa Unicode khi thật sự cần

Hai chuỗi nhìn giống nhau có thể dùng các chuỗi code point Unicode khác nhau. Java có `Normalizer`:

```java
import java.text.Normalizer;

String canonical = Normalizer.normalize(
    inputText, Normalizer.Form.NFC
);
```

`NFC` là một dạng chuẩn hóa Unicode, hữu ích khi nghiệp vụ coi các dạng tổ hợp ký tự tương đương là cùng giá trị. Tuy nhiên, chuẩn hóa Unicode không tự giải quyết alias nghiệp vụ, bỏ dấu tiếng Việt, phân biệt danh tính hoặc lỗi chính tả. Không dùng `replaceAll("\\s+", "")` để xóa mọi khoảng trắng trong tên người, địa chỉ hoặc dữ liệu có phân cách mang nghĩa.

**Nguyên tắc:** chuẩn hóa phải **có chủ đích và được kiểm thử trên dữ liệu đại diện**; không làm mất thông tin chỉ để tăng tỷ lệ bản ghi “hợp lệ”.

## 4. Kiểm tra định dạng và miền giá trị trước khi chuyển kiểu

Một regex có thể xác nhận **hình dạng chuỗi**, nhưng không thay thế toàn bộ validation.

```java
import java.util.regex.Pattern;

Pattern quantityFormat = Pattern.compile("[0-9]{1,6}");

System.out.println(quantityFormat.matcher("123").matches()); // true
System.out.println(quantityFormat.matcher("-1").matches());  // false
System.out.println(quantityFormat.matcher("2.5").matches()); // false
System.out.println(quantityFormat.matcher("0").matches());   // true
```

Định dạng `"0"` phù hợp regex nhưng **không hợp lệ về miền giá trị** nếu số lượng phải lớn hơn 0. Vì vậy cần cả:

```java
if (!quantityFormat.matcher(text).matches()) {
    // Sai hình dạng đầu vào.
} else {
    int quantity = Integer.parseInt(text);
    if (quantity <= 0) {
        // Hình dạng đúng, nhưng sai quy tắc nghiệp vụ.
    }
}
```

Với ví dụ này, tối đa sáu chữ số bảo đảm `Integer.parseInt` không tràn. Trong hệ thống có số lớn hơn, phải kiểm tra giới hạn hoặc bắt `NumberFormatException` một cách có chủ đích.

### Ngày phải tồn tại, không chỉ khớp mẫu

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

try {
    LocalDate date = LocalDate.parse(
        "2026-02-30", DateTimeFormatter.ISO_LOCAL_DATE
    );
} catch (DateTimeParseException ex) {
    System.out.println("Ngày không hợp lệ");
}
```

`2026-02-30` có vẻ đúng hình dạng `yyyy-MM-dd` nhưng không tồn tại. `ISO_LOCAL_DATE` dùng quy tắc giải quyết ngày nghiêm ngặt. Nếu nguồn là timestamp có múi giờ, không được tùy tiện chuyển thành `LocalDate` khi chưa xác định múi giờ nghiệp vụ.

### Số tiền không nên đi qua `double` nếu cần chính xác thập phân

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("15.50")
    .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(price); // 15.50
```

Tạo `BigDecimal` từ chuỗi thập phân đã kiểm tra, thay vì qua `new BigDecimal(0.1)` nếu mong biểu diễn đúng giá trị thập phân `0.1`. Với tiền tệ có quy tắc làm tròn hoặc đơn vị đặc biệt, phải thiết kế giới hạn độ chính xác, scale và chính sách làm tròn riêng.

## 5. Khi nào dùng `filter`, `map`, `flatMap`?

`map` biểu diễn phép chuyển **một phần tử thành một kết quả**; `filter` chỉ giữ phần tử phù hợp. Nếu một dòng chỉ cần kiểm tra có khác `null` và khác rỗng không, hai phương thức này đủ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> values = Arrays.asList("  A  ", null, " ", " B ");

List<String> cleaned = values.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .filter(s -> !s.isEmpty())
    .collect(Collectors.toList());

System.out.println(cleaned); // [A, B]
```

Đây là ví dụ hợp lệ khi **được phép loại toàn bộ dữ liệu rỗng mà không cần ghi lý do**. Với dữ liệu cần đối soát, dòng nào bị loại và vì sao quan trọng: `filter` đơn thuần **không lưu được thông tin đó**.

Một cách thiết kế tốt hơn cho nhập liệu là dùng kiểu kết quả:

```text
parseAndValidate(raw)
       |
       +-- Valid(data)
       |
       +-- Invalid(rowNumber, field, reason)
```

Sau đó mới quyết định thu hai nhánh, hoặc chỉ lấy nhánh hợp lệ khi nghiệp vụ cho phép.

## 6. Dự án hoàn chỉnh: nhập đơn hàng, giữ cả dữ liệu hợp lệ và lỗi

Ví dụ dưới đây dùng **Java 17+** để có `record` và `Collectors.teeing` (bản thân `teeing` có từ Java 12). `RawOrder` mô tả dữ liệu *đã được parser định dạng nguồn tách thành trường*. Nếu nguồn là CSV, phải dùng parser CSV hỗ trợ quote/escape; không được mặc định `line.split(",")` là đủ cho dữ liệu CSV thực tế.

Chính sách ví dụ:

- `id`, `sku`: chuỗi ASCII có 1–20 ký tự gồm chữ cái, chữ số, dấu `-`; đầu/cuối được `strip()`, mã được chuẩn hóa chữ hoa.
- `units`: 1–6 chữ số, giá trị phải lớn hơn 0.
- `unitPrice`: không âm, có 1–9 chữ số phần nguyên và tối đa 2 chữ số thập phân.
- `orderedOn`: ngày ISO thực sự tồn tại.
- Mỗi bản ghi tạo đúng một `Parsed`: hoặc một `Order`, hoặc một `Reject` có số dòng và lý do.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public final class CleanOrderImport {
    private static final Pattern KEY =
        Pattern.compile("[A-Z0-9-]{1,20}");
    private static final Pattern UNITS =
        Pattern.compile("[0-9]{1,6}");
    private static final Pattern PRICE =
        Pattern.compile("[0-9]{1,9}(\\.[0-9]{1,2})?");

    record RawOrder(
        String id,
        String sku,
        String units,
        String unitPrice,
        String orderedOn
    ) {}

    record Order(
        String id,
        String sku,
        int units,
        BigDecimal unitPrice,
        LocalDate orderedOn
    ) {}

    record Reject(int rowNumber, String field, String reason) {}

    record Parsed(Order order, Reject rejection) {
        static Parsed valid(Order order) {
            return new Parsed(order, null);
        }
        static Parsed invalid(int row, String field, String reason) {
            return new Parsed(null, new Reject(row, field, reason));
        }
        boolean isValid() {
            return order != null;
        }
    }

    record ImportReport(List<Order> accepted, List<Reject> rejected) {
        ImportReport {
            accepted = List.copyOf(accepted);
            rejected = List.copyOf(rejected);
        }
    }

    private CleanOrderImport() {}

    static String stripOrNull(String text) {
        return text == null ? null : text.strip();
    }

    static String canonicalKey(String text) {
        String stripped = stripOrNull(text);
        return stripped == null
            ? null
            : stripped.toUpperCase(Locale.ROOT);
    }

    static Parsed parseRow(int rowNumber, RawOrder raw) {
        if (raw == null) {
            return Parsed.invalid(rowNumber, "row", "Bản ghi null");
        }

        String id = canonicalKey(raw.id());
        String sku = canonicalKey(raw.sku());
        String unitsText = stripOrNull(raw.units());
        String priceText = stripOrNull(raw.unitPrice());
        String dateText = stripOrNull(raw.orderedOn());

        if (id == null || !KEY.matcher(id).matches()) {
            return Parsed.invalid(
                rowNumber, "id", "Mã đơn rỗng hoặc sai định dạng"
            );
        }
        if (sku == null || !KEY.matcher(sku).matches()) {
            return Parsed.invalid(
                rowNumber, "sku", "Mã sản phẩm sai định dạng"
            );
        }
        if (unitsText == null ||
                !UNITS.matcher(unitsText).matches()) {
            return Parsed.invalid(
                rowNumber, "units", "Số lượng không phải số nguyên hợp lệ"
            );
        }
        int units = Integer.parseInt(unitsText);
        if (units <= 0) {
            return Parsed.invalid(
                rowNumber, "units", "Số lượng phải lớn hơn 0"
            );
        }

        if (priceText == null ||
                !PRICE.matcher(priceText).matches()) {
            return Parsed.invalid(
                rowNumber, "unitPrice", "Giá phải không âm, tối đa 2 số lẻ"
            );
        }
        BigDecimal unitPrice = new BigDecimal(priceText)
            .setScale(2, RoundingMode.UNNECESSARY);

        if (dateText == null || dateText.isEmpty()) {
            return Parsed.invalid(
                rowNumber, "orderedOn", "Thiếu ngày đặt"
            );
        }
        LocalDate orderedOn;
        try {
            orderedOn = LocalDate.parse(
                dateText, DateTimeFormatter.ISO_LOCAL_DATE
            );
        } catch (DateTimeParseException ex) {
            return Parsed.invalid(
                rowNumber, "orderedOn", "Ngày không tồn tại hoặc sai ISO"
            );
        }

        return Parsed.valid(
            new Order(id, sku, units, unitPrice, orderedOn)
        );
    }

    static ImportReport importOrders(List<RawOrder> rawRows) {
        return IntStream.range(0, rawRows.size())
            .mapToObj(i -> parseRow(i + 1, rawRows.get(i)))
            .collect(Collectors.teeing(
                Collectors.filtering(
                    Parsed::isValid,
                    Collectors.mapping(
                        Parsed::order, Collectors.toList()
                    )
                ),
                Collectors.filtering(
                    result -> !result.isValid(),
                    Collectors.mapping(
                        Parsed::rejection, Collectors.toList()
                    )
                ),
                ImportReport::new
            ));
    }

    public static void main(String[] args) {
        List<RawOrder> input = List.of(
            new RawOrder(
                " a-001 ", " sku-01 ", "2", "15.50", "2026-03-05"
            ),
            new RawOrder(
                "A-002", "SKU-02", "0", "4.50", "2026-03-05"
            ),
            new RawOrder(
                "A-003", "SKU-03", "1", "7.20", "2026-02-30"
            ),
            new RawOrder(
                "A-004", "SKU-04", "3", "7.20", "2026-03-06"
            ),
            new RawOrder(
                "A-005", "SKU-05", "1", "oops", "2026-03-06"
            )
        );

        ImportReport report = importOrders(input);

        System.out.println("Accepted: " + report.accepted().size());
        System.out.println("Rejected: " + report.rejected().size());
        // Accepted: 2
        // Rejected: 3

        report.rejected().forEach(System.out::println);

        BigDecimal total = report.accepted().stream()
            .map(order -> order.unitPrice().multiply(
                BigDecimal.valueOf(order.units())
            ))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println(total); // 52.60
    }
}
```

### Phân tích cách tổ chức code

1. **Chuẩn hóa diễn ra trước khi xác thực mã:** `" a-001 "` thành `"A-001"`, rồi kiểm tra định dạng.
2. **Chỉ parse sau khi kiểm tra cấu trúc:** regex giới hạn chữ số, nên `Integer.parseInt` không tràn trong miền dữ liệu đã quy định.
3. **Lỗi dữ liệu được biểu diễn thành giá trị:** một ngày sai tạo `Reject`, không làm ngoại lệ thoát ra rồi ngừng toàn bộ pipeline.
4. **Mỗi hàng được parse một lần:** `IntStream.range` cung cấp chỉ số hàng, `mapToObj` tạo một `Parsed` cho mỗi đầu vào.
5. **`teeing` thu hai đầu ra trong cùng terminal operation:** nhánh thứ nhất giữ `Order`, nhánh thứ hai giữ `Reject`. Hai downstream cùng nhận mỗi kết quả `Parsed`, nhưng không phải đọc hay parse lại nguồn hai lần.
6. **Kết quả không sửa đổi được ở cấp danh sách:** `List.copyOf` ngăn thêm/xóa vào các danh sách báo cáo. `Order`, `Reject` là record chỉ chứa kiểu bất biến trong ví dụ; các giá trị `BigDecimal` và `LocalDate` cũng bất biến.
7. **Doanh thu chỉ tính trên dữ liệu đã được chấp nhận:** `BigDecimal` tránh sai số dấu phẩy động nhị phân trong phép cộng tiền thập phân của bài tập.

Kết quả này **chưa xử lý trùng mã đơn với các hàng khác**, đối chiếu danh mục SKU, hạn mức giá theo chính sách hay ghi giao dịch xuống database. Đây là các quy tắc validation ở **cấp tập dữ liệu/hệ thống**, cần một bước riêng, không được suy ra từ việc từng hàng đã hợp lệ.

## 7. Không cần báo cáo lỗi? Lấy riêng dữ liệu hợp lệ một cách có chủ đích

Trong những ứng dụng chỉ cần bỏ qua dữ liệu sai **theo hợp đồng nghiệp vụ**, có thể chuyển kết quả parse thành `Optional<T>` rồi dùng `flatMap(Optional::stream)` (Java 9+):

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

// Giả sử hàm tryParse nhận String và trả Optional<Integer>.
List<Integer> values = rawTexts.stream()
    .map(this::tryParse)
    .flatMap(Optional::stream)
    .collect(Collectors.toList());
```

Đây là **mẫu minh họa** trong một lớp có `tryParse` và `rawTexts` được định nghĩa; không phải một chương trình độc lập. `Optional.empty()` đại diện cho không có giá trị, còn `flatMap` bỏ trường hợp đó khỏi kết quả.

Ưu điểm là pipeline ngắn, không phải dùng `null` để biểu diễn lỗi. Nhưng nhược điểm là **mất nguyên nhân dữ liệu không hợp lệ**. Nếu nhập lô đơn hàng, thanh toán hoặc hồ sơ cần truy vết, hãy giữ đối tượng lỗi như `Reject` thay vì âm thầm bỏ dòng.

Trên Java 16+, `mapMulti` cũng có thể phát 0 hoặc 1 kết quả hợp lệ mà không cần tạo nhiều stream con. Chỉ dùng nó khi hình dạng đầu ra và khả năng truy vết phù hợp; một cách ngắn hơn không phải luôn là thiết kế tốt hơn.

## 8. Trùng khóa sau chuẩn hóa: phải xác định chính sách

Làm sạch và chuẩn hóa có thể khiến **hai giá trị gốc khác nhau trở thành cùng một khóa**:

```text
" a-001 " ---> "A-001"
"A-001"   ---> "A-001"
```

Không được chỉ gọi `distinct()` hoặc `toMap(..., (first, second) -> first)` rồi kết luận bản ghi trùng đã được xử lý đúng. Đôi khi nghiệp vụ muốn giữ bản mới nhất, đôi khi phải từ chối **cả hai** để yêu cầu đối soát, đôi khi muốn gộp số lượng.

Nếu muốn phát hiện những mã đơn xuất hiện nhiều lần trong các `Order` đã parse:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

// orders là List<Order>, Order.id() đã được chuẩn hóa.
Map<String, Long> frequency = orders.stream()
    .collect(Collectors.groupingBy(
        Order::id, Collectors.counting()
    ));

List<Order> onlyUniqueIds = orders.stream()
    .filter(order -> frequency.get(order.id()) == 1L)
    .collect(Collectors.toList());
```

Đây là mẫu **loại tất cả bản ghi có mã trùng** khỏi danh sách chấp nhận. Trong ứng dụng thật, nên tạo **bản ghi lỗi kèm vị trí dòng của từng bản ghi trùng**, không đơn thuần loại chúng rồi mất lý do. `Order` trong ví dụ đầy đủ không lưu chỉ số dòng; có thể chuyển sang lưu chỉ số cùng kết quả parse hoặc đưa vào một DTO nhập liệu có metadata.

Nếu chọn `toMap`, overload không có merger có thể ném `IllegalStateException` khi khóa trùng. Merger phải được chọn theo nghiệp vụ, không phải chỉ để làm ngoại lệ biến mất. Với parallel stream, merger còn cần có ngữ nghĩa thích hợp khi cách kết hợp thay đổi.

## 9. Chuẩn hóa phải ổn định, có thể tái lập và gần với idempotent

Một hàm chuẩn hóa tốt thường có tính **idempotent**: chuẩn hóa lần nữa không đổi kết quả đã chuẩn hóa.

```java
import java.util.Locale;

static String normalize(String value) {
    return value.strip().toUpperCase(Locale.ROOT);
}

String once = normalize("  sku-01 ");
String twice = normalize(once);
System.out.println(once.equals(twice)); // true
```

Điều này giúp pipeline dễ kiểm thử, tránh phụ thuộc số lần dữ liệu đi qua một bước ETL. Tuy nhiên, idempotence của chuẩn hóa **không bảo đảm** toàn bộ nhập liệu idempotent: lưu cùng đơn hàng hai lần có thể tạo hai giao dịch nếu không có khóa idempotency hoặc ràng buộc duy nhất tại nơi ghi.

Các hàm `parseRow` và `canonicalKey` trong dự án không ghi log ra biến chia sẻ, không gọi mạng và không phụ thuộc thời điểm. Vì thế, trên cùng đầu vào và cùng quy tắc, chúng cho cùng kết quả. Quy tắc có thể phụ thuộc **phiên bản danh mục, đơn vị tiền, múi giờ hoặc ngôn ngữ**; khi có, cần truyền chúng như dữ liệu cấu hình rõ ràng và lưu dấu phiên bản để tái lập kết quả.

## 10. Nguyên tắc an toàn khi muốn chuyển sang parallel stream

Một pipeline làm sạch dữ liệu **có thể** chạy song song khi từng phần tử độc lập, nguồn có thể chia và các lambda tuân thủ hợp đồng Stream. Nhưng xử lý song song có thể không nhanh hơn nếu mỗi bản ghi đơn giản hoặc phần lớn thời gian chờ I/O.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

// Minh họa trong phạm vi có parseRow và rawRows như chương trình trên.
List<Parsed> results = IntStream.range(0, rawRows.size())
    .parallel()
    .mapToObj(i -> parseRow(i + 1, rawRows.get(i)))
    .collect(Collectors.toList());
```

Điều kiện để kết quả đúng:

- **Không sửa nguồn** trong lúc stream duyệt; tránh thêm/xóa phần tử của `rawRows` khi tác vụ đang chạy.
- **Không ghi vào một `ArrayList` bên ngoài** trong `parallel().forEach(list::add)`; dùng `collect` hoặc thiết kế result riêng.
- **Không để parser ghi vào bộ đếm/chú thích dùng chung có thể thay đổi**. Nếu cần thống kê lỗi, tổng hợp từ `Parsed` sau khi parse hoặc dùng collector hợp lệ.
- **Không dựa vào thứ tự gọi lambda**. Nếu cần số dòng, lấy chỉ số từ nguồn có thứ tự như `IntStream.range` và gắn chỉ số vào result.
- **Không dùng exception để điều khiển lỗi có thể dự đoán** một cách tùy tiện. Dùng kết quả thành công/thất bại để người đọc hiểu điều kiện loại bỏ.
- **Đo hiệu năng trước khi bật song song**. Với đầu vào nhỏ, chi phí chia và kết hợp tác vụ thường lớn hơn lợi ích.

Nguồn `List` có thứ tự và `Collectors.toList()` giữ encounter order trong kết quả, kể cả khi thực thi song song; **thứ tự chạy thực tế của các lambda** không cần giống thứ tự đó. Nếu đổi sang collector `UNORDERED` hoặc nguồn không có encounter order, phải đánh giá lại hợp đồng thứ tự của kết quả.

## 11. Những trường hợp không nên âm thầm “sửa cho hợp lệ”

Không phải dữ liệu sai nào cũng có thể được sửa tự động:

| Dữ liệu | Rủi ro của việc tự sửa | Khuyến nghị |
| --- | --- | --- |
| Ngày `2026-02-30` | Chuyển sang tháng sau có thể đổi thời điểm nghiệp vụ. | Từ chối và yêu cầu người nhập xác nhận. |
| Giá `1.234,50` | Cách dùng dấu `.`/`,` phụ thuộc locale; parse sai có thể đổi giá trị. | Xác định locale/định dạng hợp đồng trước khi chuyển. |
| Giá `12.345` với thang 2 chữ số | Làm tròn tự động có thể làm thay đổi tiền phải thu. | Dùng quy tắc làm tròn được phê duyệt hoặc từ chối. |
| Số lượng âm `-3` | Có thể là hàng trả lại, không phải lỗi nhập liệu. | Phân biệt đơn đặt hàng với giao dịch hoàn trả. |
| Email/tên người có dấu | Loại dấu hoặc chuyển hoa có thể gộp nhầm danh tính. | Chuẩn hóa theo trường và chính sách định danh. |
| Mã đơn trùng | Bỏ một bản ghi có thể mất giao dịch thật. | Dùng chính sách đối soát và khóa duy nhất. |
| Thiếu mã định danh | Gán ID giả không kiểm soát gây lỗi truy vết. | Dùng cơ chế sinh ID có hợp đồng hoặc báo lỗi. |

Một pipeline tốt cần phân biệt **“có thể chuẩn hóa mà không đổi nghĩa”** với **“không đủ thông tin để tự sửa”**. Sự phân biệt này thường quan trọng hơn việc viết được bao nhiêu phép `map`.

## 12. Thu thập thống kê chất lượng dữ liệu

Nếu có cả kết quả hợp lệ và kết quả lỗi, có thể tính những chỉ số phục vụ giám sát chất lượng nhập liệu:

```java
import java.util.Map;
import java.util.stream.Collectors;

// report là ImportReport được tạo ở ví dụ hoàn chỉnh.
Map<String, Long> rejectedByField = report.rejected().stream()
    .collect(Collectors.groupingBy(
        Reject::field,
        Collectors.counting()
    ));

System.out.println(rejectedByField);
// Ví dụ: {units=1, unitPrice=1, orderedOn=1}
```

Ngoài số lượng lỗi theo trường, báo cáo có thể ghi tổng số hàng nhận, số hàng đạt, tỷ lệ từ chối, tần suất trùng khóa, thời gian parse và nguyên nhân phổ biến. **Đừng coi số hàng được `filter` giữ lại là số lượng dữ liệu sạch** nếu bước validation chưa kiểm tra hết các ràng buộc nghiệp vụ.

Khi xuất thông tin lỗi, tránh đưa toàn bộ dữ liệu thô chứa thông tin cá nhân, token hoặc thông tin thanh toán vào log công khai. Chỉ ghi những trường cần thiết, cân nhắc che dữ liệu nhạy cảm, phân quyền đọc và chính sách lưu giữ.

## 13. Kiểm thử dữ liệu biên và thuộc tính bất biến

Một bộ kiểm thử tối thiểu nên bao gồm:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Chuỗi đầu/cuối có khoảng trắng | Được làm sạch theo chính sách. |
| Mã khác hoa/thường | Cùng dạng chuẩn hóa nếu quy tắc định danh cho phép. |
| Trường bắt buộc là `null` hoặc rỗng | Từ chối có tên trường. |
| Số lượng `0` hoặc âm | Bị từ chối theo hợp đồng đơn hàng. |
| Số lượng quá dài | Bị từ chối trước `parseInt`. |
| Giá âm, sai dấu thập phân, có quá hai chữ số lẻ | Bị từ chối hoặc xử lý theo chính sách rõ ràng. |
| Ngày không tồn tại hoặc sai ISO | Bị từ chối có lý do. |
| Hai mã trùng sau chuẩn hóa | Có chính sách trùng khóa rõ ràng ở cấp lô. |
| Lô rỗng | Danh sách hợp lệ và lỗi đều rỗng. |
| Cùng dữ liệu xử lý lại | Cùng tập bản ghi và lý do lỗi, không phụ thuộc lịch thực thi. |

Với mỗi đầu vào có `n` hàng, nếu mô hình kết quả chỉ có hai trạng thái và mỗi hàng được xử lý đúng một lần, có bất biến:

\[
\text{acceptedCount} + \text{rejectedCount} = n
\]

Trong bài tập, bất biến này có thể kiểm tra bằng `assert` hoặc ngoại lệ thử nghiệm. Nếu một hàng có **nhiều lỗi** và hệ thống chọn lưu tất cả lỗi, công thức số lỗi có thể **lớn hơn** số bản ghi bị từ chối; khi đó phải phân biệt *số hàng lỗi* và *số lỗi phát hiện*.

Nếu dùng parallel stream, kết quả vẫn phải cùng tập bản ghi được chấp nhận và từ chối. Không bắt buộc thứ tự thực thi lambda giống nhau, nhưng **chỉ số hàng và lý do lỗi** phải được gắn với đúng đầu vào.

## 14. Hiệu năng và tài nguyên của pipeline làm sạch

Chi phí chính thường phụ thuộc vào **định dạng nguồn và cách kiểm tra**, không phải chỉ tên phương thức Stream:

- **Regex:** biên dịch trước `Pattern` để tránh biên dịch lại biểu thức ở từng bản ghi; tránh regex quá phức tạp có thể gây backtracking tốn kém trên dữ liệu không tin cậy.
- **Chuẩn hóa Unicode:** có chi phí tạo chuỗi mới; chỉ áp dụng cho những trường thật sự cần.
- **Parse ngày và số tiền:** dùng định dạng cụ thể, không tạo formatter hoặc cấu hình locale tùy tiện cho từng phần tử.
- **Bộ nhớ:** `toList` giữ toàn bộ kết quả; nếu lô quá lớn, cân nhắc chia batch và cơ chế lưu/cách ly lỗi có kiểm soát.
- **Lazy và ngắn mạch:** `map`/`filter` chỉ chạy khi terminal operation yêu cầu; `findFirst` hoặc `limit` có thể không xử lý tất cả bản ghi.
- **I/O:** `Files.lines` phải được đóng bằng `try-with-resources`. Terminal operation không tự thay thế trách nhiệm đóng stream.
- **Song song:** với dữ liệu đủ lớn và parser thuần, có thể thử; khi công việc phụ thuộc DB/network, cần giới hạn kết nối và điều phối tác vụ riêng.

Ví dụ xử lý các dòng tệp khi chỉ cần đọc một lần:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> nonEmptyLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.map(String::strip)
            .filter(s -> !s.isEmpty())
            .collect(Collectors.toList());
    }
}
```

Đoạn này chỉ làm sạch **dòng văn bản**; không giả vờ rằng mỗi dòng đã được parse/validate thành đơn hàng. Với CSV có dấu ngoặc kép, xuống dòng bên trong trường hoặc encoding phức tạp, phải dùng parser phù hợp trước khi chuẩn hóa trường. Không đưa `Files.lines` vào pipeline vô hạn hay giả định tệp không thể thay đổi khi đang đọc.

## 15. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| `map(Integer::parseInt)` trực tiếp trên dữ liệu nhập thô | Một chuỗi lỗi có thể ném `NumberFormatException` làm hỏng lô. | Xác thực định dạng, phạm vi và biểu diễn lỗi theo bản ghi. |
| `filter(x -> isValid(x))` rồi bỏ hết bản ghi sai | Không biết dòng nào sai và vì sao. | Dùng `Parsed`/`Reject` hoặc mô hình `Result`. |
| Xóa mọi khoảng trắng và dấu Unicode | Có thể thay đổi tên, khóa hoặc dữ liệu có nghĩa. | Chuẩn hóa riêng theo trường và hợp đồng. |
| Dùng `double` để giữ tiền chính xác | Có thể có sai số biểu diễn. | Dùng `BigDecimal` hoặc đơn vị nguyên nhỏ nhất khi thích hợp. |
| Regex ngày đúng thì cho là ngày hợp lệ | Có thể chấp nhận ngày không tồn tại. | Parse nghiêm ngặt bằng API ngày/giờ. |
| Gộp mã trùng bằng `distinct()` mà không đối soát | Có thể mất bản ghi hợp lệ của nghiệp vụ. | Xây chính sách phát hiện và xử lý trùng khóa. |
| Ghi vào `ArrayList` ngoài trong `parallel().forEach` | Race, thiếu dữ liệu hoặc sai thứ tự. | Thu bằng `collect` hoặc collector đúng hợp đồng. |
| Dùng `peek` để ghi log cho từng bản ghi | Một số pipeline có thể tối ưu hoặc ngắn mạch, không gọi mọi action. | Thu kết quả và lỗi một cách tường minh. |
| Giả định `List.copyOf` sao chép sâu | Object mutable bên trong vẫn có thể thay đổi. | Dùng kiểu giá trị bất biến hoặc sao chép cấp phần tử. |
| Không có bộ kiểm thử dữ liệu rỗng hoặc biên | Lỗi chỉ xuất hiện khi nhận dữ liệu thật. | Kiểm thử trường thiếu, lỗi số/ngày, trùng và lô rỗng. |

## 16. Bài tập thực hành

**Bài 1 — Làm sạch có kiểm soát.** Cho `List<String>` chứa `"  SKU-01 "`, `"sku-01"`, `null`, `" SKU 02 "`. Chuẩn hóa theo quy tắc mã SKU chỉ chứa chữ, số và dấu `-`. Giá trị nào hợp lệ? Giá trị nào phải từ chối? Vì sao `"SKU 02"` không nên tự xóa khoảng trắng giữa để biến thành mã khác nếu nghiệp vụ không cho phép?

**Bài 2 — Bảo toàn lỗi.** Sửa pipeline `map(String::strip).filter(...).map(Integer::parseInt)` để mỗi phần tử tạo một `Result<Integer, Error>` (hoặc hai record tương đương), với lỗi bao gồm số dòng. Không để một dòng sai làm ngừng cả lô.

**Bài 3 — Kiểm tra ngày.** Dùng `DateTimeFormatter.ISO_LOCAL_DATE` xử lý `"2026-02-28"`, `"2026-02-29"`, `"2026-02-30"`. Dự đoán những giá trị được chấp nhận và giải thích năm nhuận.

**Bài 4 — Tiền tệ.** Cho các chuỗi giá `"12.30"`, `"0"`, `"5.123"`, `"-1.00"`. Viết validator cho hợp đồng không âm, tối đa hai số thập phân; tính tổng các giá hợp lệ bằng `BigDecimal` và cho biết vì sao không nên dùng `double`.

**Bài 5 — Bản ghi trùng.** Sau chuẩn hóa, hai đơn cùng ID `A-001`. Dùng `groupingBy(Order::id, counting())` phát hiện ID trùng, đề xuất chính sách xử lý và cách giữ số dòng lỗi.

**Bài 6 — Báo cáo chất lượng.** Với ví dụ `CleanOrderImport`, đếm tổng số bản ghi, số hợp lệ, số từ chối và phân nhóm `Reject` theo tên trường. Xác nhận bất biến `accepted + rejected = input.size()`.

**Bài 7 — Parallel stream.** Chạy cùng hàm parse trên `IntStream.range(...).parallel()`. So sánh kết quả theo số dòng giữa bản tuần tự và song song. Giải thích vì sao dùng `AtomicInteger` để cấp số dòng theo thứ tự gọi lambda là không phù hợp.

**Bài 8 — Mở rộng dự án.** Thêm kiểm tra mã SKU trong một danh mục hợp lệ, phát hiện giá vượt hạn mức và tách lỗi có thể sửa với lỗi cần chặn. Chỉ ghi cơ sở dữ liệu các đơn đã thỏa mọi quy tắc cần thiết, có cơ chế idempotency và đối soát để không nhập trùng khi chạy lại.

## 17. Checklist trước khi dùng trong ứng dụng

- [ ] Có hợp đồng về dữ liệu bắt buộc, kiểu số, đơn vị, định dạng ngày và locale.
- [ ] Chỉ chuẩn hóa trường được nghiệp vụ cho phép, không tự làm mất nghĩa.
- [ ] Kiểm tra hình dạng **và** miền giá trị trước khi chuyển kiểu.
- [ ] Mỗi bản ghi có kết quả thành công hoặc lỗi có vị trí/nguyên nhân rõ ràng.
- [ ] Không âm thầm bỏ bản ghi lỗi nếu quy trình cần truy vết.
- [ ] Có chính sách xử lý khóa trùng và quy tắc ở cấp tập dữ liệu.
- [ ] Không dùng trạng thái mutable chia sẻ trong các lambda song song.
- [ ] Đã kiểm thử lô rỗng, trường `null`, giá trị biên, lỗi số/ngày và lô lớn.
- [ ] Các báo cáo tiền tệ dùng kiểu số và quy tắc làm tròn thích hợp.
- [ ] Có chính sách bảo vệ dữ liệu nhạy cảm trong thông báo lỗi và log.
- [ ] Nếu nguồn là I/O, stream được đóng đúng vòng đời.
- [ ] Các thay đổi về hiệu năng được đo mà không phá vỡ ngữ nghĩa xử lý.

**Ghi nhớ:** Với dữ liệu thực tế, pipeline `map`–`filter`–`collect` chỉ là công cụ; điều quyết định chất lượng là **hợp đồng chuẩn hóa, kiểm tra tính hợp lệ và khả năng giải thích mỗi bản ghi bị loại**. Hãy tách việc làm sạch khỏi quy tắc nghiệp vụ, dùng kiểu số/ngày chính xác, giữ kết quả lỗi thay vì xóa dấu vết, rồi mới tối ưu hoặc chạy song song. Một bộ dữ liệu “sạch” phải **đáng tin và có thể đối soát**, không đơn thuần là danh sách còn lại sau `filter`.
