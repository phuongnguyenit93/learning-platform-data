# Bài tập đối tượng giá trị và so sánh bằng trong Java OOP

> **Mục tiêu thực hành:** Thiết kế *value object* có dữ liệu hợp lệ ngay từ khi khởi tạo, bất biến trong suốt vòng đời, so sánh theo **giá trị** và hoạt động đúng làm khóa trong `HashMap`, phần tử `HashSet` hoặc `TreeSet`.

Giả sử cửa hàng cần định danh một sản phẩm bằng SKU và biểu diễn đơn giá bằng một số tiền có đơn vị tiền tệ. Hai biến chứa cùng SKU chuẩn hóa hoặc cùng số tiền và đơn vị tiền tệ phải được coi là **bằng nhau về ý nghĩa**, dù được tạo ở những thời điểm khác nhau.

Đây là bài tập kết hợp thiết kế đối tượng giá trị với kiểm thử các hợp đồng `equals`, `hashCode` và `compareTo`; nó không chỉ yêu cầu thêm hai phương thức so sánh vào một class.

## 1. Phân biệt identity và value equality

Một *entity* (ví dụ `Order` trong nghiệp vụ) thường có **danh tính riêng**: hai đơn hàng có tổng tiền bằng nhau vẫn có thể là hai đơn khác nhau. Một *value object* (ví dụ mã SKU chuẩn hóa hoặc số tiền) được nhận diện chủ yếu bằng **tập thuộc tính tạo ra ý nghĩa của nó**.

~~~java
String sku1 = new String("BOOK-1");
String sku2 = new String("BOOK-1");

System.out.println(sku1 == sku2);      // false: hai tham chiếu khác nhau
System.out.println(sku1.equals(sku2)); // true: cùng nội dung
~~~

Với các class tự định nghĩa:

- `==` kiểm tra cùng tham chiếu khi toán hạng là object.
- `Object.equals` mặc định chỉ trả `true` khi hai biến trỏ tới cùng object.
- Có thể override `equals`/`hashCode` trong class thường, hoặc dùng `record` để Java sinh hành vi so sánh theo component.
- `record` chỉ sinh so sánh theo giá trị của **các component**; nếu component chứa mảng hoặc object mutable, tính bất biến sâu và ngữ nghĩa so sánh chưa tự được giải quyết.

| Khái niệm | Entity | Value object |
|---|---|---|
| Điều quyết định “cùng một” | Định danh nghiệp vụ, ví dụ `orderId` | Giá trị các thuộc tính mang ý nghĩa |
| Ví dụ | Đơn hàng, tài khoản người dùng | SKU, Money, khoảng thời gian |
| Tính bất biến | Có thể thay đổi trạng thái theo nghiệp vụ | Nên bất biến để dễ chia sẻ và so sánh |
| Kết quả khi hai object có dữ liệu hiển thị giống nhau | Không nhất thiết là cùng entity | Bằng nhau nếu tất cả thành phần có ý nghĩa bằng nhau |
| Sử dụng trong collection dựa trên hash | Theo identity được thiết kế ổn định | Thích hợp nếu `equals` và `hashCode` nhất quán |

**Lưu ý:** Không gán `equals` của entity đơn thuần theo mọi field thay đổi được. Nếu entity được dùng làm khóa mà các field tham gia hash biến đổi, việc tra cứu có thể hỏng.

## 2. Đề bài và hợp đồng nghiệm thu

Hãy xây hai value object:

### A. `Sku` — mã sản phẩm

- Nhận chuỗi từ bên ngoài, `trim()` khoảng trắng ở đầu/cuối và chuyển thành chữ hoa bằng `Locale.ROOT`.
- Sau chuẩn hóa, độ dài **3–20 ký tự**, ký tự đầu/cuối là chữ cái Latin in hoa hoặc chữ số; giữa chuỗi cho phép `A-Z`, `0-9` và dấu `-`.
- Với null hoặc chuỗi không hợp lệ, ném `IllegalArgumentException`.
- `new Sku(" ab-01 ")` phải bằng `new Sku("AB-01")` và có cùng hash.
- Không có setter; cùng một SKU luôn giữ cùng mã sau khi tạo.

### B. `Money` — số tiền

Đơn giản hóa nghiệp vụ bài tập: chỉ hỗ trợ **USD** và **EUR**, cả hai có **2 chữ số thập phân** trong hệ thống này. Không thực hiện chuyển đổi tỷ giá.

- Chứa `Currency` là enum `USD` hoặc `EUR` và `BigDecimal amount`.
- Không chấp nhận `null`; số tiền phải **không âm**.
- Chuẩn hóa `BigDecimal` về **scale = 2** bằng `setScale(2, RoundingMode.UNNECESSARY)`. Cho phép bỏ chữ số 0 dư, không âm thầm làm tròn giá trị có chữ số thập phân thứ ba khác 0.
- `USD 12.3` bằng `USD 12.30` và có cùng hash.
- `USD 12.30` **không** bằng `EUR 12.30`: cùng con số nhưng khác tiền tệ.
- Phép `add` chỉ được cộng hai số tiền cùng loại; trộn USD với EUR phải bị từ chối.
- `compareTo` phải có thứ tự **nhất quán với equals**. Để sắp xếp kỹ thuật trong collection, so sánh **mã tiền tệ trước**, số tiền sau. Thứ tự này **không mang ý nghĩa quy đổi kinh tế**.
- Thao tác so sánh nghiệp vụ `greaterThan` chỉ nhận cùng tiền tệ và ném lỗi nếu khác.

### C. `ProductKey` và `ProductTags`

- `ProductKey(Sku, Money)` coi cặp SKU + đơn giá là một giá trị tổng hợp: hai object với cùng SKU, tiền tệ và số tiền được coi là bằng nhau.
- `ProductTags` chứa danh sách `List<String>`, phải sao chép để đối tượng nhận đầu vào không bị thay đổi khi caller sửa danh sách cũ; cũng không được trả list có thể sửa.
- Không cần ID ngẫu nhiên, thời điểm tạo hoặc bộ đếm để so sánh `ProductKey`; những giá trị đó sẽ làm hai “giá trị bằng nhau” trở thành khác nhau.

### Các ca nghiệm thu cốt lõi

| Mã | Ca kiểm thử | Kỳ vọng |
|---|---|---|
| EQ01 | Hai `Sku` từ `" ab-01 "` và `"AB-01"` | `equals = true`, hash bằng nhau |
| EQ02 | SKU khác nhau | `equals = false` |
| EQ03 | `Money(USD, 12.3)` và `Money(USD, 12.30)` | Bằng nhau, hash bằng nhau, `compareTo = 0` |
| EQ04 | `USD 12.30` và `EUR 12.30` | Khác nhau; `compareTo != 0` |
| EQ05 | `HashSet` chứa hai SKU tương đương | Chỉ có 1 phần tử |
| EQ06 | Dùng `Money` tương đương để `get` trong `HashMap` | Lấy được giá trị đã `put` |
| EQ07 | `TreeSet` chứa các `Money` tương đương | Không sinh phần tử trùng |
| EQ08 | Cộng USD với EUR | `IllegalArgumentException` |
| EQ09 | Amount âm hoặc cần làm tròn, ví dụ `1.234` | Bị từ chối |
| EQ10 | Sửa danh sách đầu vào sau khi tạo `ProductTags` | Không ảnh hưởng trạng thái trong value object |
| EQ11 | Sửa danh sách được trả từ `ProductTags` | Bị từ chối |
| EQ12 | `equals(null)` hoặc `equals` khác kiểu | `false` |

## 3. Bẫy thực tế: BigDecimal có hai định nghĩa “bằng”

`BigDecimal` dùng **giá trị số** cho `compareTo` nhưng dùng **cả giá trị và scale** cho `equals`:

~~~java
BigDecimal a = new BigDecimal("12.3");
BigDecimal b = new BigDecimal("12.30");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
~~~

Nếu viết `Money.equals` bằng `amount.compareTo(other.amount) == 0` nhưng lại viết `hashCode` bằng `amount.hashCode()`, bạn có nguy cơ tạo hai đối tượng **bằng nhau theo equals nhưng có hash khác nhau**. Điều đó vi phạm hợp đồng hash và có thể khiến `HashSet`/`HashMap` hoạt động trái mong đợi.

Trong bài này, cả hai amount đều được chuẩn hóa bằng `setScale(2, UNNECESSARY)` ngay trong constructor. Sau đó record có thể sinh `equals` và `hashCode` chính xác vì component `BigDecimal` đã có scale cố định. Đây là một ví dụ của **canonical representation** (biểu diễn chuẩn tắc): đầu vào khác cú pháp nhưng cùng ý nghĩa được đưa về cùng biểu diễn.

Không dùng `new BigDecimal(0.1)` nếu muốn biểu diễn số thập phân chính xác theo chuỗi nhập. Hãy sử dụng `new BigDecimal("0.1")` hoặc một phương thức tạo thích hợp như `BigDecimal.valueOf(0.1)`. Trong ví dụ, đầu vào tiền được lấy từ chuỗi.

## 4. Tự triển khai trước: khung bài tập

Trước khi xem lời giải, bạn có thể tự điền logic trong những kiểu sau:

~~~java
record Sku(String code) {
    Sku {
        // TODO: normalize + validate; gán ngược vào code
    }
}

enum Currency { EUR, USD }

record Money(Currency currency, BigDecimal amount)
        implements Comparable<Money> {
    Money {
        // TODO: validate currency và chuẩn hóa amount về scale 2
    }

    Money add(Money other) {
        // TODO: chỉ cộng khi cùng currency
        throw new UnsupportedOperationException();
    }

    @Override
    public int compareTo(Money other) {
        // TODO: thứ tự theo mã tiền tệ, sau đó theo amount
        throw new UnsupportedOperationException();
    }
}
~~~

Đặt các câu hỏi trước khi viết:

1. Có field nào sẽ bị đổi sau khi object đã được đưa vào `HashSet` hay làm key của `HashMap` không?
2. Hai object có cùng nội dung nhưng khác thứ tự constructor/biểu diễn chữ thường/chữ hoa nên bằng hay khác?
3. Phép so sánh thứ tự có yêu cầu tính `a.compareTo(b) == 0` đúng khi và chỉ khi `a.equals(b)` không?
4. Nếu chứa `List`, `Date` hoặc mảng, chỉ khai báo `final` có đủ đảm bảo không có mutable alias không?
5. Có phải các tiền tệ khác nhau được phép tính cộng hoặc so sánh giá trị kinh tế trực tiếp không?

## 5. Lời giải Java 17 chạy độc lập

Tạo một tệp **`ValueObjectPractice.java`**, dán toàn bộ mã sau và chạy bằng JDK 17 trở lên, không cần thư viện ngoài:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ValueObjectPractice {

    // Chỉ hỗ trợ hai loại tiền tệ có hai chữ số thập phân.
    enum Currency { EUR, USD }

    // Value object cho mã SKU chuẩn hóa.
    record Sku(String code) {
        Sku {
            if (code == null) {
                throw new IllegalArgumentException("SKU is null");
            }
            code = code.trim().toUpperCase(Locale.ROOT);
            if (!code.matches("[A-Z0-9][A-Z0-9-]{1,18}[A-Z0-9]")) {
                throw new IllegalArgumentException("Invalid SKU: " + code);
            }
        }
    }

    // Cả currency và amount đều là các component bất biến trong bài này.
    record Money(Currency currency, BigDecimal amount)
            implements Comparable<Money> {

        Money {
            currency = Objects.requireNonNull(currency, "currency");
            amount = Objects.requireNonNull(amount, "amount")
                    .setScale(2, RoundingMode.UNNECESSARY);
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("Money must be >= 0");
            }
        }

        static Money of(Currency currency, String decimal) {
            return new Money(currency, new BigDecimal(decimal));
        }

        private void requireSameCurrency(Money other) {
            Objects.requireNonNull(other, "other");
            if (currency != other.currency) {
                throw new IllegalArgumentException(
                    "Currency mismatch: " + currency + " vs " + other.currency
                );
            }
        }

        Money add(Money other) {
            requireSameCurrency(other);
            return new Money(currency, amount.add(other.amount));
        }

        // So sánh nghiệp vụ chỉ hợp lệ khi cùng đơn vị tiền tệ.
        boolean greaterThan(Money other) {
            requireSameCurrency(other);
            return amount.compareTo(other.amount) > 0;
        }

        // Thứ tự phục vụ sorted collections: currency trước, amount sau.
        // KHÔNG phải phép so sánh sức mua giữa USD và EUR.
        @Override
        public int compareTo(Money other) {
            Objects.requireNonNull(other, "other");
            int byCurrency = currency.name().compareTo(other.currency.name());
            return byCurrency != 0
                    ? byCurrency : amount.compareTo(other.amount);
        }
    }

    // Value object kết hợp: equals/hashCode do record sinh theo hai component.
    record ProductKey(Sku sku, Money unitPrice) {
        ProductKey {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
        }
    }

    // Ví dụ value object có thành phần là một collection.
    // String immutable; List.copyOf loại bỏ alias mutable của danh sách.
    record ProductTags(List<String> values) {
        ProductTags {
            values = List.copyOf(Objects.requireNonNull(values, "values"));
            if (values.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Tag cannot be blank");
            }
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expect(
            Class<? extends RuntimeException> type, Runnable operation) {
        try {
            operation.run();
        } catch (RuntimeException ex) {
            if (type.isInstance(ex)) return;
            throw new AssertionError(
                "Expected " + type.getSimpleName()
                    + " but got " + ex.getClass().getSimpleName(), ex
            );
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        // 1. Hai object khác tham chiếu nhưng bằng giá trị.
        Sku first = new Sku(" ab-01 ");
        Sku second = new Sku("AB-01");
        check(first != second, "Objects should be distinct references");
        check(first.equals(second), "SKU value equality");
        check(second.equals(first), "Symmetric equality");
        check(first.hashCode() == second.hashCode(), "Equal hash codes");
        check(!first.equals(null), "Not equal to null");
        check(!first.equals("AB-01"), "Not equal to different type");

        Set<Sku> skuSet = new HashSet<>();
        skuSet.add(first);
        skuSet.add(second);
        check(skuSet.size() == 1, "HashSet should deduplicate equal SKUs");
        expect(IllegalArgumentException.class, () -> new Sku("a"));
        expect(IllegalArgumentException.class, () -> new Sku("bad!"));
        System.out.println("PASS: SKU equality and HashSet");

        // 2. Chuẩn hóa BigDecimal: 12.3 và 12.30 có cùng biểu diễn.
        Money usd1 = Money.of(Currency.USD, "12.3");
        Money usd2 = Money.of(Currency.USD, "12.30");
        Money eur = Money.of(Currency.EUR, "12.30");

        check(usd1 != usd2, "Distinct Money instances");
        check(usd1.equals(usd2), "Numeric representation normalized");
        check(usd1.hashCode() == usd2.hashCode(), "Equal Money hash");
        check(usd1.compareTo(usd2) == 0, "Comparison consistent with equals");
        check(!usd1.equals(eur), "Currency belongs to value");
        check(usd1.compareTo(eur) != 0, "Currencies distinguish sort keys");

        Map<Money, String> descriptions = new HashMap<>();
        descriptions.put(usd1, "Twelve USD and thirty cents");
        check("Twelve USD and thirty cents".equals(descriptions.get(usd2)),
                "HashMap equivalent-key lookup");

        Set<Money> sorted = new TreeSet<>();
        sorted.add(usd1);
        sorted.add(usd2);
        sorted.add(eur);
        check(sorted.size() == 2, "TreeSet uses compareTo for duplicates");
        System.out.println("PASS: Money equality, HashMap and TreeSet");

        // 3. Phép toán phải tuân thủ miền và đơn vị tiền tệ.
        Money plus = usd1.add(Money.of(Currency.USD, "0.70"));
        check(plus.equals(Money.of(Currency.USD, "13.00")),
                "Currency-preserving addition");
        check(usd1.greaterThan(Money.of(Currency.USD, "12.29")),
                "Greater-than same currency");
        expect(IllegalArgumentException.class, () -> usd1.add(eur));
        expect(IllegalArgumentException.class, () -> usd1.greaterThan(eur));
        expect(IllegalArgumentException.class,
                () -> Money.of(Currency.USD, "-0.01"));
        expect(ArithmeticException.class,
                () -> Money.of(Currency.USD, "1.234"));
        System.out.println("PASS: currency-aware operations and validation");

        // 4. Giá trị tổng hợp: cùng SKU và Money thì cùng ProductKey.
        ProductKey key1 = new ProductKey(first, usd1);
        ProductKey key2 = new ProductKey(second, usd2);
        check(key1.equals(key2), "Composite value equality");
        check(key1.hashCode() == key2.hashCode(), "Composite hash");
        System.out.println("PASS: composite value object");

        // 5. Defensive copy: thay đổi list gốc không làm đổi value object.
        List<String> input = new ArrayList<>(List.of("sale", "book"));
        ProductTags tags = new ProductTags(input);
        input.set(0, "changed");
        check(tags.values().get(0).equals("sale"),
                "Input list must not alias internal state");
        expect(UnsupportedOperationException.class,
                () -> tags.values().add("hidden"));
        check(tags.equals(new ProductTags(List.of("sale", "book"))),
                "List components compare by contents");
        System.out.println("PASS: immutable composite data and defensive copy");

        // 6. Bẫy BigDecimal thuần: equals không giống compareTo.
        BigDecimal a = new BigDecimal("12.3");
        BigDecimal b = new BigDecimal("12.30");
        check(a.compareTo(b) == 0, "Numeric values match");
        check(!a.equals(b), "Raw BigDecimal scale differs");
        System.out.println("PASS: BigDecimal equality pitfall demonstrated");
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac ValueObjectPractice.java
java ValueObjectPractice
~~~

Đầu ra dự kiến:

~~~text
PASS: SKU equality and HashSet
PASS: Money equality, HashMap and TreeSet
PASS: currency-aware operations and validation
PASS: composite value object
PASS: immutable composite data and defensive copy
PASS: BigDecimal equality pitfall demonstrated
~~~

### Giải thích thiết kế

**`Sku`:** Chuẩn hóa được thực hiện trong *compact constructor* của `record`. Việc gán lại tham số `code` cập nhật giá trị được lưu trong component record. Sau đó mỗi object có một biểu diễn chuẩn tắc.

**`Money`:** Vì mọi `amount` có `scale = 2`, record-generated `equals` và `hashCode` sẽ coi `12.3` và `12.30` tương đương sau chuẩn hóa. Đơn vị tiền tệ là một component nên cũng tham gia so sánh bằng.

**`ProductKey`:** Một khóa tổng hợp kết hợp hai value object bất biến. Nó không dùng thời điểm tạo, địa chỉ bộ nhớ hay random ID; do đó phù hợp làm khóa khi các quy tắc tạo object không đổi.

**`ProductTags`:** `List.copyOf` tạo danh sách không chỉnh sửa được và tách khỏi list nguồn mutable. Vì từng phần tử ở đây là `String` (immutable), không có đường sửa phần tử gián tiếp. Nếu phần tử là `StringBuilder` hoặc `Date` thì cần sao chép chính các phần tử, không chỉ sao chép list.

**`compareTo`:** Thứ tự được định nghĩa là (tên currency, amount). Nó hợp lệ cho `TreeSet`/`TreeMap` vì hai `Money` chỉ có `compareTo == 0` khi cả currency và amount giống nhau sau chuẩn hóa. Không thể suy ra EUR 10 có sức mua thấp hay cao hơn USD 11 dựa trên thứ tự đó.

## 6. Hợp đồng equals, hashCode và compareTo phải được kiểm tra như thế nào?

### Hợp đồng `equals`

Cho `a`, `b` và `c` là object không đổi trong suốt phép kiểm tra:

| Tính chất | Điều kiện cần đúng |
|---|---|
| Phản xạ (*reflexive*) | `a.equals(a) == true` |
| Đối xứng (*symmetric*) | `a.equals(b) == b.equals(a)` |
| Bắc cầu (*transitive*) | Nếu `a=b` và `b=c` theo equals thì `a=c` |
| Nhất quán (*consistent*) | Gọi lặp không đổi kết quả khi dữ liệu không đổi |
| So với null | `a.equals(null) == false` |

Khi `a.equals(b)` là `true`, **bắt buộc** `a.hashCode() == b.hashCode()`. Chiều ngược lại không bắt buộc: hai object khác nhau **có thể va chạm hash**.

### Hợp đồng `compareTo`

Java `Comparable` cần thứ tự nhất quán để sắp xếp. Các tính chất cốt lõi:

- Dấu của `a.compareTo(b)` ngược dấu của `b.compareTo(a)`.
- Nếu `a > b` và `b > c` theo so sánh thì `a > c`.
- Nếu `a.compareTo(b) == 0`, so sánh `a` và `b` với mọi phần tử khác phải có cùng dấu.
- **Rất nên** nhất quán với equals khi dùng cùng kiểu trong `TreeSet` hoặc `TreeMap`: `compareTo == 0` phải tương ứng với `equals == true`. Nếu chủ động không nhất quán phải tài liệu hóa vì sorted collections sẽ dựa vào `compareTo` để phân biệt phần tử.

Trong Java, `HashSet` dựa vào `hashCode` và `equals`; `TreeSet` (khi dùng natural ordering) dựa vào `compareTo`. Vì vậy một `Money` có so sánh thiếu tiền tệ hoặc không chuẩn hóa scale có thể dẫn đến tập hợp có kết quả khác nhau.

~~~mermaid
flowchart TD
    A["Tạo hai value object từ input"] --> B["Chuẩn hóa và validate trong constructor"]
    B --> C["Các component có ý nghĩa có cùng giá trị?"]
    C -->|Có| D["equals = true; hashCode bằng nhau"]
    C -->|Không| E["equals = false; hash có thể trùng"]
    D --> F["HashSet/HashMap nhận diện cùng khóa"]
    D --> G["Nếu Comparable: compareTo = 0"]
    E --> H["Nếu Comparable: compareTo khác 0"]
    G --> I["TreeSet/TreeMap nhận diện cùng phần tử"]
~~~

Sơ đồ giả định `compareTo` được thiết kế nhất quán với `equals` như trong lời giải. Hash collision không phải lỗi, miễn `equals` vẫn phân biệt đúng.

## 7. Tự viết equals/hashCode khi không dùng record

Trong dự án cũ hoặc class có mô hình riêng, có thể dùng một **final class** với field immutable và override thủ công:

~~~java
import java.util.Locale;
import java.util.Objects;

public final class ProductCode {
    private final String value;

    public ProductCode(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw cannot be null");
        }
        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("empty product code");
        }
        this.value = normalized;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ProductCode other)) return false;
        return value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

Hai instance `new ProductCode(" abc ")` và `new ProductCode("ABC")` bằng nhau và có cùng hash. Việc đặt class là `final` ở ví dụ này loại bỏ bài toán kế thừa có thể làm mất tính đối xứng của `equals` khi subclass bổ sung field mang ý nghĩa mới.

Một lỗi thường gặp:

~~~java
@Override
public boolean equals(Object obj) {
    // Sai: chỉ so sánh field "name" và bỏ qua currency.
    // Hoặc sai: equals dùng compareTo của BigDecimal,
    // nhưng hashCode vẫn dùng BigDecimal.hashCode() chưa chuẩn hóa.
}
~~~

Không override `equals` mà quên `hashCode`; không sử dụng field mutable tham gia hash khi object còn được lưu làm key.

## 8. Bẫy mutable value object và alias

### 8.1. Key thay đổi sau khi đưa vào HashMap

~~~java
class MutableKey {
    String code;

    MutableKey(String code) { this.code = code; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof MutableKey other
                && java.util.Objects.equals(code, other.code);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}
~~~

Nếu bạn `put` một `MutableKey` vào `HashMap` rồi sửa `code`, hash của key có thể thay đổi. Tra cứu key sau đó có thể thất bại dù object vẫn tồn tại trong map. Không thể dựa vào kết quả cụ thể của một input may rủi; lỗi thiết kế là **dữ liệu dùng để so sánh/hash không ổn định trong khi lưu key**.

Cách sửa: giữ field `private final`, normalize ngay khi tạo và cung cấp **object mới** thay cho setter.

### 8.2. Record chứa mảng không tự thành deep value object

~~~java
record ArrayKey(byte[] bytes) {}
~~~

Mảng là mutable và `equals` của mảng là so sánh theo tham chiếu. Hai mảng khác nhau có cùng byte vẫn không được record coi là bằng nhau theo nội dung. Ngoài ra, caller có thể sửa mảng đầu vào sau khi truyền vào constructor.

Một hướng an toàn: biểu diễn bằng kiểu value object bất biến được thiết kế riêng, copy array khi vào/ra và override equals/hashCode với `Arrays.equals`/`Arrays.hashCode`; hoặc chọn cấu trúc immutable khác phù hợp. Không nên đưa thẳng array như một component rồi coi đó là deep immutable.

### 8.3. `Collections.unmodifiableList` và `List.copyOf` không tương đương

- `Collections.unmodifiableList(original)` tạo một **view** không sửa được qua wrapper, nhưng vẫn phản ánh các thay đổi do chủ sở hữu `original` thực hiện.
- `List.copyOf(original)` tạo một biểu diễn list bất biến theo API, dùng để giữ giá trị tại thời điểm nhận; nhưng nó **không deep-copy** từng element.
- Cần quyết định rõ: bạn muốn **live read-only view** hay **snapshot bất biến**? Đối tượng giá trị thường ưu tiên snapshot khi collection đầu vào có thể thay đổi.

## 9. Bài tập nâng cao: viết property-based test thủ công

Không cần thư viện, hãy sinh nhiều chuỗi số tiền có cùng giá trị nhưng khác scale, chẳng hạn `"12.3"` và `"12.30"`, rồi thử:

~~~java
Money a = Money.of(Currency.USD, "12.3");
Money b = Money.of(Currency.USD, "12.30");

assert a.equals(b);
assert b.equals(a);
assert a.hashCode() == b.hashCode();
assert a.compareTo(b) == 0;
~~~

**Chú ý:** Java `assert` bị tắt mặc định nếu không chạy với `-ea`. Để test có hiệu lực trong CI, dùng JUnit Assertions hoặc hàm `check` như ví dụ hoàn chỉnh; nếu dùng các câu `assert` trên, chạy `java -ea ...`.

Có thể tự động duyệt cặp giá trị:

~~~java
String[] inputs = {"0", "0.0", "0.00", "1.2", "1.20", "12.30"};

for (String x : inputs) {
    for (String y : inputs) {
        Money a = Money.of(Currency.USD, x);
        Money b = Money.of(Currency.USD, y);
        if (a.compareTo(b) == 0) {
            if (!a.equals(b) || a.hashCode() != b.hashCode()) {
                throw new AssertionError("Inconsistent Money: " + x + ", " + y);
            }
        }
    }
}
~~~

Trong ví dụ này, `Money` và `Currency` là các nested types bên trong `ValueObjectPractice`; nếu đặt đoạn test ở file khác, sử dụng `ValueObjectPractice.Money` và `ValueObjectPractice.Currency` (cùng package) hoặc import chúng phù hợp.

Đối với dự án có JUnit 5, thay khối lặp bằng `@ParameterizedTest`/`@MethodSource` và mở rộng tập biên: `0`, `0.01`, `999999.99`, số âm, scale 3 phải làm tròn và currency khác. Khi thất bại, in rõ input để có thể tái lập.

## 10. Bài tập mở rộng

1. **Nâng cấp `Sku`:** thêm điều kiện SKU không được có `"--"` liên tiếp. Viết test cho `"AB--01"` và chứng minh các SKU đã hợp lệ vẫn so sánh bằng đúng.
2. **Thêm phép trừ `Money.subtract`:** quyết định có cho phép âm không theo nghiệp vụ. Nếu không, phép trừ tạo số âm phải bị từ chối trước khi trả value object.
3. **Tạo `Percentage`:** chấp nhận 0–100% với scale cố định, không dùng `double` để lưu tỷ lệ. Đảm bảo `5.0%` và `5.00%` tương đương theo hợp đồng.
4. **Tạo `DateRange`:** hai ngày bắt đầu/kết thúc, bắt buộc `start <= end`, cung cấp `contains(LocalDate)`. Hai khoảng có cùng hai mốc phải bằng nhau và có cùng hash.
5. **Tạo `EmailAddress`:** quyết định quy tắc chuẩn hóa trước khi viết equals. Đừng mặc định toàn bộ phần local của email không phân biệt hoa/thường nếu hệ thống chưa quy định như vậy.
6. **Bỏ record để tự cài đặt class:** hiện thực `Money` bằng `final class` với `private final` fields, `equals`/`hashCode`/`compareTo` thủ công. Chạy lại cùng bộ test và so sánh độ dài/rủi ro bảo trì.
7. **Kiểm thử collection:** thêm 50 cách viết amount tương đương nhau, đếm số phần tử `HashSet` và `TreeSet` sau chuẩn hóa. Không dùng chỉ số hash để suy đoán nội dung bằng nhau.

### Rubric tự đánh giá — 10 điểm

| Tiêu chí | Điểm |
|---|---:|
| Dữ liệu được chuẩn hóa, validate và bất biến sau khởi tạo | 2 |
| Phân biệt đúng identity/value, cài đặt equals theo các component có ý nghĩa | 2 |
| hashCode nhất quán, HashSet/HashMap không tạo bản sao khóa bằng nhau | 2 |
| compareTo nhất quán với equals, TreeSet hoạt động đúng | 2 |
| Bắt được các bẫy BigDecimal scale, mutable alias và currency khác nhau | 2 |

**Tiêu chí hoàn thành:** Có thể tạo hai value object độc lập từ đầu vào khác cách viết nhưng cùng ý nghĩa và chứng minh chúng bằng nhau, có hash giống nhau, hành xử nhất quán trong hash/sorted collections, không bị thay đổi gián tiếp qua reference; đồng thời giải thích được vì sao entity và value object không nên có cùng chính sách so sánh một cách máy móc.