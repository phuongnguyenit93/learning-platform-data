# Thay đổi record bằng cách tạo instance mới và giữ invariant

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record được chuẩn hóa từ Java 16 và tiếp tục phù hợp với Java hiện đại để biểu diễn dữ liệu theo giá trị. Vì component của record không thể được gán lại sau khi khởi tạo, cách cập nhật tự nhiên là tạo **instance mới** từ dữ liệu cũ và phần thay đổi. Bài học này hướng dẫn thiết kế các phương thức tạo bản sao có chỉnh sửa, bảo vệ invariant và cập nhật dữ liệu lồng nhau an toàn.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao record không có setter và cách cập nhật bằng cách tạo instance mới.
- Viết các phương thức kiểu `withX(...)` để thay đổi một hoặc nhiều component.
- Đặt validation trong canonical constructor để mọi instance mới đều giữ invariant.
- Cập nhật record chứa collection hoặc record lồng nhau mà không làm thay đổi dữ liệu cũ.
- Dùng cách biến đổi bất biến với Stream, Map và các cấu trúc dữ liệu thông dụng.
- Phân biệt tính bất biến của record với bất biến sâu, thread-safety và equality theo giá trị.

## 1. Vì sao cập nhật record bằng instance mới?

Ví dụ record biểu diễn sản phẩm:

```java
public record Product(
        String code,
        String name,
        BigDecimal price,
        int stock
) {}
```

Các component được lưu trong những trường instance `private final`. Sau khi constructor hoàn tất, không thể gán lại `price` hoặc `stock`. Record không tự sinh setter, vì vậy cách sau không hợp lệ:

```java
Product product = new Product(
        "P-01", "Keyboard", new BigDecimal("750000"), 12);

// Không hợp lệ: không có setter và component không thể gán lại.
// product.setPrice(new BigDecimal("700000"));
```

Nếu giá cần thay đổi, ta tạo một Product khác với giá mới:

```java
Product discounted = new Product(
        product.code(),
        product.name(),
        new BigDecimal("700000"),
        product.stock()
);
```

`product` vẫn giữ giá cũ; `discounted` là một instance riêng chứa giá mới. Cách làm này thường được gọi là *immutable update* hoặc *copy with changes*.

Lợi ích của cách cập nhật này:

- Mỗi instance giữ trạng thái ổn định sau khi tạo.
- Không có setter công khai để thay đổi dữ liệu bỏ qua validation.
- Có thể giữ lại instance cũ để so sánh, audit hoặc dùng trong một phép tính khác.
- Dễ kết hợp với Stream và các phép biến đổi trả về giá trị mới.
- Khi component tham gia `equals()`/`hashCode()`, mỗi trạng thái được so sánh theo dữ liệu của chính nó.

## 2. Viết phương thức with để tạo bản sao có thay đổi

Java không tự sinh phương thức `withName`, `withPrice` hoặc cú pháp cập nhật `with` cho record. Nếu cần thao tác này, ta tự định nghĩa phương thức trả về một instance mới.

Ví dụ:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record Product(
        String code,
        String name,
        BigDecimal price,
        int stock
) {
    public Product {
        code = requireText(code, "code");
        name = requireText(name, "name");
        Objects.requireNonNull(price, "price");

        if (price.signum() < 0) {
            throw new IllegalArgumentException("price must not be negative");
        }
        if (stock < 0) {
            throw new IllegalArgumentException("stock must not be negative");
        }
    }

    public Product withName(String newName) {
        return new Product(code, newName, price, stock);
    }

    public Product withPrice(BigDecimal newPrice) {
        return new Product(code, name, newPrice, stock);
    }

    public Product withStock(int newStock) {
        return new Product(code, name, price, newStock);
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field);
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return normalized;
    }
}
```

Sử dụng:

```java
Product original = new Product(
        "P-01", "Keyboard", new BigDecimal("750000"), 12);

Product renamed = original.withName("Mechanical Keyboard");
Product repriced = original.withPrice(new BigDecimal("700000"));
Product restocked = original.withStock(20);
```

Mỗi phương thức `withX` gọi constructor để tạo record mới. Constructor kiểm tra lại toàn bộ invariant, kể cả component không thay đổi. Nhờ đó, đường cập nhật luôn tuân theo cùng quy tắc với đường khởi tạo.

### 2.1. Vì sao không tự gán lại từng trường?

Một phương thức cập nhật trong record không thể viết `this.price = newPrice` vì trường component là final. Ta cũng không nên dùng reflection hoặc cơ chế bên ngoài để phá tính bất biến. Việc tạo instance mới là cách cập nhật được thiết kế cho record.

### 2.2. Cập nhật nhiều component cùng lúc

Nếu một thao tác nghiệp vụ luôn thay đổi nhiều component liên quan, hãy tạo một phương thức mô tả đúng thao tác đó:

```java
public Product withPriceAndStock(BigDecimal newPrice, int newStock) {
    return new Product(code, name, newPrice, newStock);
}
```

Ví dụ trên là phương thức bổ sung trong record `Product` ở phần trước. Nó hữu ích khi thay đổi giá và tồn kho cần được xem như một thao tác thống nhất. Không cần tạo phương thức cho mọi tổ hợp có thể; chỉ thêm các thao tác có ý nghĩa với người dùng kiểu dữ liệu.

### 2.3. Có thể nối nhiều phương thức with

Vì mỗi phương thức trả về một Product mới, có thể nối các thao tác:

```java
Product updated = original
        .withName("Keyboard Pro")
        .withPrice(new BigDecimal("990000"))
        .withStock(8);
```

Mỗi bước tạo một instance trung gian rồi bước tiếp theo tạo instance khác. Với record nhỏ, cách viết này rõ ràng. Nếu một thao tác cần thay đổi nhiều component, một phương thức duy nhất như `withPriceAndStock` có thể thể hiện ý định tốt hơn và tránh tạo các bản trung gian không cần thiết.

## 3. Giữ invariant bằng canonical constructor

*Invariant* là điều kiện phải luôn đúng đối với mọi instance hợp lệ. Ví dụ:

- Mã sản phẩm không được rỗng.
- Giá và số lượng không âm.
- Ngày bắt đầu không sau ngày kết thúc.
- Tiền phải có đơn vị tiền tệ.
- Trạng thái đơn hàng phải tuân theo quy tắc miền.

Record có thể dùng compact canonical constructor để xác thực và chuẩn hóa component. Đây là vị trí quan trọng vì constructor được gọi cả khi tạo instance lần đầu lẫn khi các phương thức `withX` tạo bản sao.

### 3.1. Invariant trên từng component

Ví dụ `Money`:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }

        amount = amount.stripTrailingZeros();
    }

    public Money withAmount(BigDecimal newAmount) {
        return new Money(newAmount, currency);
    }
}
```

`withAmount` không tự kiểm tra lại giá trị bằng một bộ điều kiện riêng. Nó chuyển dữ liệu mới vào constructor; constructor kiểm tra số tiền không âm, đơn vị tiền không null và chuẩn hóa scale.

Chuẩn hóa `BigDecimal` chỉ phù hợp khi miền nghiệp vụ xác định scale không phải một phần của giá trị. Với tiền tệ, hãy xác định chính sách số chữ số thập phân và làm tròn phù hợp với đơn vị tiền trước khi áp dụng cách chuẩn hóa này.

### 3.2. Invariant liên quan nhiều component

Một số quy tắc chỉ có thể kiểm tra khi xem nhiều component cùng lúc. Ví dụ khoảng ngày:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException("start must not be after end");
        }
    }

    public DateRange withStart(LocalDate newStart) {
        return new DateRange(newStart, end);
    }

    public DateRange withEnd(LocalDate newEnd) {
        return new DateRange(start, newEnd);
    }
}
```

Ví dụ:

```java
DateRange range = new DateRange(
        LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 12, 31));

DateRange nextRange = range.withStart(LocalDate.of(2026, 2, 1));

// Ném IllegalArgumentException vì ngày bắt đầu mới sau ngày kết thúc.
DateRange invalid = range.withStart(LocalDate.of(2027, 1, 1));
```

`withStart` chỉ thay component `start`, nhưng constructor kiểm tra cả `start` và `end`. Nếu thay đổi làm vi phạm invariant, instance mới không được tạo. Instance `range` cũ vẫn hợp lệ và không bị ảnh hưởng.

### 3.3. Đừng lặp validation trong mọi phương thức with

Nếu validation chỉ được viết trong `withPrice` nhưng constructor công khai không kiểm tra, caller vẫn có thể tạo dữ liệu sai bằng constructor. Ngược lại, nếu constructor đã kiểm tra đầy đủ, các phương thức with không cần sao chép cùng logic kiểm tra.

Một nguyên tắc tốt:

1. Đặt invariant tại constructor của record.
2. Mọi phương thức tạo bản sao đều gọi constructor.
3. Chỉ đặt thêm kiểm tra trong phương thức with khi đó là quy tắc riêng của thao tác, không phải invariant chung.

## 4. Cập nhật record lồng nhau và collection

Record có thể chứa record khác hoặc collection. Tạo instance mới ở lớp ngoài là chưa đủ nếu các component bên trong vẫn bị chia sẻ và có thể thay đổi.

### 4.1. Sao chép collection trong constructor

Ví dụ dòng đơn hàng:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        sku = sku.strip();
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isEmpty() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    public OrderLine withQuantity(int newQuantity) {
        return new OrderLine(sku, newQuantity, unitPrice);
    }

    public OrderLine withUnitPrice(BigDecimal newUnitPrice) {
        return new OrderLine(sku, quantity, newUnitPrice);
    }
}
```

Đơn hàng chứa danh sách dòng hàng:

```java
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record Order(UUID id, List<OrderLine> lines) {
    public Order {
        Objects.requireNonNull(id, "id");
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));

        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must have at least one line");
        }
    }

    public Order withLines(List<OrderLine> newLines) {
        return new Order(id, newLines);
    }
}
```

`List.copyOf` tạo danh sách không thể sửa thông qua accessor và không giữ thay đổi cấu trúc của danh sách nguồn. Vì `OrderLine` cũng là record chỉ chứa các kiểu bất biến, danh sách dòng hàng trong ví dụ này phù hợp làm snapshot.

### 4.2. Cập nhật một phần tử trong danh sách

Muốn thay số lượng của một dòng hàng, ta tạo dòng mới rồi tạo Order mới với danh sách mới:

```java
public Order withLineQuantity(String sku, int newQuantity) {
    Objects.requireNonNull(sku, "sku");

    List<OrderLine> updatedLines = new ArrayList<>(lines);
    boolean found = false;

    for (int i = 0; i < updatedLines.size(); i++) {
        OrderLine line = updatedLines.get(i);

        if (line.sku().equals(sku)) {
            updatedLines.set(i, line.withQuantity(newQuantity));
            found = true;
            break;
        }
    }

    if (!found) {
        throw new IllegalArgumentException("Unknown SKU: " + sku);
    }

    return new Order(id, updatedLines);
}
```

Đây là phương thức bổ sung bên trong record `Order` ở phần trước. Cần có các import `java.util.ArrayList`, `java.util.List` và `java.util.Objects`. Danh sách tạm được thay đổi cục bộ, nhưng `lines` của Order cũ không bị sửa. Khi tạo Order mới, constructor lại dùng `List.copyOf` và kiểm tra invariant.

Nếu một SKU có thể xuất hiện nhiều lần và cần cập nhật tất cả dòng cùng SKU, hãy bỏ `break` và xác định rõ quy tắc tổng hợp. Nếu SKU phải duy nhất, hãy kiểm tra invariant đó trong constructor `Order`.

### 4.3. Phiên bản dùng Stream

Với thao tác đơn giản, có thể tạo danh sách mới bằng Stream:

```java
List<OrderLine> updatedLines = order.lines().stream()
        .map(line -> line.sku().equals(targetSku)
                ? line.withQuantity(newQuantity)
                : line)
        .toList();

Order updatedOrder = order.withLines(updatedLines);
```

`map` trả về dòng hàng mới ở vị trí cần cập nhật và giữ nguyên các dòng khác. `Stream.toList()` từ Java 16 trả về danh sách unmodifiable; constructor Order vẫn sao chép để bảo vệ invariant của chính nó.

Nếu cần báo lỗi khi SKU không tồn tại, kiểm tra trước bằng `anyMatch` hoặc dùng một vòng lặp để vừa tìm vừa tạo danh sách. Đừng âm thầm trả lại đơn hàng cũ nếu nghiệp vụ yêu cầu mã hàng phải tồn tại.

### 4.4. Bất biến nông và bất biến sâu

`List.copyOf` chỉ sao chép cấu trúc danh sách, không sao chép sâu từng phần tử. Nếu một record chứa `List<MutableItem>`, người dùng vẫn có thể gọi phương thức thay đổi trạng thái của từng `MutableItem`.

Các lựa chọn:

- Ưu tiên phần tử bất biến, chẳng hạn record khác chỉ chứa các kiểu bất biến.
- Chuyển phần tử mutable thành snapshot record khi tạo danh sách.
- Nếu bắt buộc giữ object mutable, cung cấp API có kiểm soát và không tuyên bố object graph là bất biến sâu.

Một record chỉ có thể được xem là bất biến sâu khi toàn bộ trạng thái có thể quan sát qua component cũng không thể bị thay đổi ngoài ý muốn.

## 5. Cập nhật record trong pipeline Stream

Vì phương thức with trả về instance mới, có thể dùng trực tiếp trong `map` để biến đổi danh sách:

```java
List<Product> repriced = products.stream()
        .map(product -> product.withPrice(
                product.price().multiply(new BigDecimal("0.95"))))
        .toList();
```

Mỗi phần tử đầu vào tạo ra một Product mới với giá giảm 5%. Danh sách nguồn và các Product cũ không bị sửa. Constructor vẫn kiểm tra giá mới theo invariant.

### 5.1. Chỉ cập nhật phần tử thỏa điều kiện

```java
List<Product> restocked = products.stream()
        .map(product -> product.stock() < 5
                ? product.withStock(20)
                : product)
        .toList();
```

Phần tử không thỏa điều kiện được giữ nguyên tham chiếu. Điều này an toàn khi Product và toàn bộ component của nó bất biến. Nếu component chứa trạng thái mutable, việc giữ nguyên tham chiếu có thể làm hai danh sách chia sẻ cùng object mutable.

### 5.2. Biến đổi rồi sắp xếp

```java
List<Product> result = products.stream()
        .map(product -> product.withPrice(
                product.price().multiply(new BigDecimal("0.90"))))
        .sorted(Comparator.comparing(Product::price))
        .toList();
```

Pipeline thực hiện cập nhật giá bằng instance mới, sau đó sắp xếp theo giá đã cập nhật. Comparator đọc accessor của record mới.

### 5.3. Không dùng side effect để cập nhật record

Không nên cố thay đổi record trong `forEach` hoặc lưu kết quả vào biến dùng chung chỉ để mô phỏng setter. Stream được thiết kế tốt nhất theo hướng chuyển đổi giá trị; `map` biểu đạt trực tiếp việc tạo dữ liệu mới.

Nếu cần cập nhật một collection mutable đang được quản lý bởi một lớp khác, hãy thực hiện thao tác đó tại ranh giới phù hợp. Bản thân record vẫn được tạo mới và giữ invariant qua constructor.

## 6. Cập nhật giá trị trong Map

Record thường được dùng làm value của Map. Khi cần thay đổi dữ liệu, tạo value mới rồi thay thế entry:

```java
Map<String, Product> productsByCode = new HashMap<>();
productsByCode.put("P-01", original);

productsByCode.computeIfPresent(
        "P-01",
        (code, current) -> current.withStock(current.stock() + 5)
);
```

`computeIfPresent` nhận value hiện tại và trả về value thay thế. Phương thức `withStock` tạo Product mới; đối tượng Product cũ không thay đổi.

Nếu record được dùng làm **key**, không được thay đổi giá trị tham gia equality/hash code sau khi đã đưa vào map. Record không cho gán lại component, nhưng component mutable vẫn có thể làm key thay đổi hash. Nếu khóa logic thay đổi, hãy xóa entry theo key cũ và thêm entry với key mới, hoặc thiết kế key chứa các kiểu bất biến.

Ví dụ key bất biến:

```java
import java.util.HashMap;
import java.util.Map;

record ProductKey(String warehouse, String sku) {}

class InventoryIndex {
    private final Map<ProductKey, Integer> stockByKey = new HashMap<>();

    void moveStockKey() {
        ProductKey oldKey = new ProductKey("WH-01", "P-01");
        stockByKey.put(oldKey, 10);

        Integer quantity = stockByKey.remove(oldKey);
        ProductKey newKey = new ProductKey("WH-02", "P-01");

        if (quantity != null) {
            stockByKey.put(newKey, quantity);
        }
    }
}
```

Ta thay khóa bằng cách remove và put. Không có thao tác “sửa key tại chỗ” trong HashMap.

## 7. Phân biệt with method, factory và builder

Với record, các cách tạo instance mới có mục đích khác nhau:

| Cách | Mục đích | Khi nên dùng |
|---|---|---|
| Canonical constructor | Tạo instance và kiểm tra toàn bộ invariant | Mọi lần khởi tạo hoặc copy |
| `withX(...)` tự viết | Tạo bản sao thay đổi một vài component | Cập nhật nhỏ, có ý nghĩa rõ |
| Factory method | Tạo instance theo một quy tắc đặt tên hoặc lựa chọn | Có nhiều cách tạo hoặc cần che constructor |
| Builder | Gom nhiều tham số tùy chọn trước khi tạo object | Đầu vào phức tạp, nhiều tùy chọn hoặc API cần cấu hình từng bước |

Record không tự sinh builder hay wither. Không nên thêm builder chỉ vì record có nhiều component; nếu tất cả component đều bắt buộc và constructor đã rõ ràng, canonical constructor thường đủ dùng.

Ví dụ factory:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record Percentage(BigDecimal value) {
    public Percentage {
        Objects.requireNonNull(value, "value");
        if (value.compareTo(BigDecimal.ZERO) < 0
                || value.compareTo(new BigDecimal("100")) > 0) {
            throw new IllegalArgumentException("Percentage must be 0..100");
        }
    }

    public static Percentage zero() {
        return new Percentage(BigDecimal.ZERO);
    }

    public Percentage withValue(BigDecimal newValue) {
        return new Percentage(newValue);
    }
}
```

`zero()` diễn tả một cách tạo có tên; `withValue` diễn tả cập nhật từ một giá trị đã có. Cả hai đều đi qua constructor và giữ cùng invariant.

## 8. Equality, hashCode và vòng đời của bản sao

Record sinh `equals()` và `hashCode()` dựa trên tất cả component. Khi một component thay đổi, instance mới thường không bằng instance cũ:

```java
Product before = new Product(
        "P-01", "Keyboard", new BigDecimal("750000"), 12);

Product after = before.withStock(20);

System.out.println(before.equals(after)); // false
System.out.println(before.stock());        // 12
System.out.println(after.stock());         // 20
```

Điều này hữu ích cho value object và snapshot. Nhưng nếu kiểu biểu diễn entity có danh tính riêng và equality chỉ dựa trên ID, record có thể không phải lựa chọn thích hợp vì equality mặc định xét tất cả component. Trong trường hợp đó, class thông thường cho phép thiết kế equality theo định danh và quản lý vòng đời mutable.

Không dùng một record đã được đưa vào `HashSet` hoặc làm key của `HashMap` nếu các component tham gia hash có thể thay đổi gián tiếp. Bản thân record không cho gán lại component, nhưng component tham chiếu tới collection hoặc object mutable vẫn có thể thay đổi.

## 9. Các giới hạn cần nhớ

### 9.1. Tạo instance mới không tự động bảo đảm thread-safety

Record bất biến với các component bất biến có thể được chia sẻ giữa nhiều luồng an toàn hơn vì trạng thái của nó không thay đổi. Tuy nhiên, việc cập nhật một tham chiếu dùng chung vẫn cần cơ chế đồng bộ phù hợp.

Ví dụ, hai luồng cùng đọc một giá trị hiện tại rồi ghi hai instance mới có thể ghi đè kết quả của nhau nếu tham chiếu được quản lý không đúng. Dùng transaction, lock hoặc cơ chế atomic như `AtomicReference.updateAndGet` khi bài toán yêu cầu cập nhật nguyên tử. Không suy ra rằng mọi thao tác trên collection hoặc Map chứa record đều tự động thread-safe.

### 9.2. Tạo bản sao có thể tốn allocation

Mỗi phương thức with tạo một instance mới. Với record nhỏ và các phép cập nhật thông thường, đây thường là lựa chọn rõ ràng và dễ kiểm soát. Nếu xử lý khối lượng dữ liệu rất lớn, hãy đo hiệu năng bằng workload thực tế trước khi tối ưu. Đừng chuyển sang mutable chỉ dựa trên giả định rằng allocation chắc chắn là nút thắt.

### 9.3. Không biến record thành entity mutable bằng component mutable

Đưa `AtomicInteger`, `Date` mutable, collection có thể sửa hoặc một entity mutable vào component không làm record trở thành một object immutable. Hãy chọn kiểu component bất biến hoặc sao chép phòng vệ. Với dữ liệu ngày giờ, ưu tiên `java.time` như `LocalDate`, `Instant` và `YearMonth`.

## 10. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Mong đợi record có setter | Không thể cập nhật component | Tạo phương thức `withX` trả instance mới |
| Viết validation chỉ trong with method | Constructor vẫn có thể tạo instance sai | Đặt invariant trong canonical constructor |
| Phương thức with bỏ sót component | Bản sao vô tình làm mất dữ liệu cũ | Truyền lại tất cả component không đổi |
| Dùng List mutable trực tiếp làm component | Dữ liệu có thể bị sửa từ bên ngoài | Sao chép bằng `List.copyOf` |
| Nghĩ List.copyOf là deep copy | Phần tử mutable vẫn thay đổi | Dùng phần tử bất biến hoặc chuyển thành snapshot |
| Cập nhật record key sau khi đưa vào Map | Hash/equality có thể thay đổi nếu component mutable | Dùng key bất biến; remove/put khi khóa logic đổi |
| Dùng record cho entity có lifecycle mutable | Equality theo toàn bộ component có thể không phù hợp | Cân nhắc class quản lý danh tính và trạng thái |
| Cho rằng instance mới đồng nghĩa thread-safe | Tham chiếu dùng chung vẫn có thể bị race | Dùng cơ chế đồng bộ/atomic phù hợp |

## 11. Checklist thiết kế

Trước khi thêm phương thức cập nhật cho record, hãy kiểm tra:

1. Phương thức có trả về instance mới và giữ nguyên instance cũ không?
2. Mọi component không đổi có được truyền lại đầy đủ không?
3. Canonical constructor có kiểm tra toàn bộ invariant không?
4. Component collection đã được sao chép phòng vệ chưa?
5. Phần tử bên trong collection có bất biến không?
6. Phương thức with thể hiện một thao tác nghiệp vụ có tên rõ ràng không?
7. Equality/hashCode sau khi cập nhật có phù hợp với cách dùng trong Map/Set không?
8. Nếu tham chiếu được chia sẻ giữa nhiều luồng, thao tác thay tham chiếu có cần atomicity không?

## 12. Bài tập vận dụng

**Bài 1 — Cập nhật sản phẩm:** Tạo `Product(code, name, price, stock)` với invariant mã/tên không rỗng, giá và tồn kho không âm. Viết `withPrice`, `withStock` và `withName`. Chứng minh instance gốc không đổi sau khi gọi từng phương thức.

**Bài 2 — Giữ invariant nhiều component:** Tạo `DateRange(start, end)` yêu cầu ngày bắt đầu không sau ngày kết thúc. Viết `withStart` và `withEnd`. Thử cập nhật làm khoảng ngày không hợp lệ và xác định ngoại lệ.

**Bài 3 — Cập nhật đơn hàng:** Tạo `Order` chứa `List<OrderLine>`. Sao chép danh sách trong constructor. Viết `withLineQuantity(sku, quantity)` để tạo dòng mới và đơn hàng mới; xác định cách xử lý khi SKU không tồn tại hoặc xuất hiện nhiều lần.

**Bài 4 — Biến đổi Stream:** Từ danh sách sản phẩm, giảm giá 10% bằng `map(product -> product.withPrice(...))`, lọc sản phẩm còn hàng và sắp xếp theo giá mới. Giải thích vì sao danh sách nguồn không bị sửa.

**Bài 5 — Map value và key:** Dùng `computeIfPresent` để cập nhật value là record. Sau đó tạo record key mới và thay entry bằng remove/put. Giải thích vì sao không nên dùng component mutable trong key.

---

**Ghi nhớ:** Record không được cập nhật bằng setter. Hãy tạo instance mới từ các component cũ và giá trị cần đổi, đồng thời để canonical constructor bảo vệ invariant ở mọi đường tạo dữ liệu. Khi record chứa collection hoặc object lồng nhau, phải bảo vệ cả những tham chiếu bên trong. Cách tiếp cận này đặc biệt phù hợp với DTO, snapshot và value object trong Java hiện đại.
