# Record cục bộ để biểu diễn kết quả trung gian trong Collection và Stream (Java 17)

## 1. Vì sao cần một kiểu dữ liệu cho kết quả trung gian?

Khi xử lý collection, một phần tử đầu vào thường phải đi qua nhiều bước trước khi tạo ra kết quả cuối cùng. Ví dụ, từ danh sách đơn hàng, chương trình có thể tính doanh thu theo khách hàng, số lượng đơn, trạng thái hợp lệ hoặc thông tin dùng để sắp xếp.

Nếu kết quả gồm nhiều trường có quan hệ với nhau, các cách biểu diễn tạm như mảng, `Map.Entry` hoặc một lớp phụ khai báo ở cấp package thường làm ý nghĩa dữ liệu khó đọc:

~~~java
Object[] summary = { "CUST-01", 4L, new BigDecimal("125.50") };
~~~

Người đọc phải nhớ phần tử số 0 là mã khách hàng, phần tử số 1 là số đơn và phần tử số 2 là doanh thu. Trình biên dịch cũng không thể kiểm tra kiểu cụ thể khi lấy giá trị từ `Object[]`.

**Local record** (*record cục bộ*) là một lựa chọn gọn hơn khi một kiểu dữ liệu chỉ cần tồn tại trong một phương thức hoặc một block xử lý. Nó đặt tên rõ ràng cho từng thành phần, cung cấp constructor, accessor, `equals()`, `hashCode()` và `toString()` do Java sinh tự động.

Ví dụ:

~~~java
static void printSummary() {
    record CustomerTotal(
            String customerId,
            long orderCount,
            BigDecimal revenue) {
    }

    CustomerTotal total = new CustomerTotal(
            "CUST-01", 4, new BigDecimal("125.50"));

    System.out.println(total.customerId());
    System.out.println(total.orderCount());
    System.out.println(total.revenue());
}
~~~

`CustomerTotal` chỉ được khai báo bên trong phương thức `printSummary()`. Nó không trở thành một kiểu công khai của package hoặc API bên ngoài. Đây là điểm hữu ích khi bạn cần một cấu trúc rõ ràng để chuyển dữ liệu giữa các bước của collection/stream pipeline.

Trong Java 17, record và local record đều là tính năng ổn định; không cần bật preview.

## 2. Cú pháp và phạm vi của local record

Một local record được khai báo bằng từ khóa `record` trong một block, thường là thân phương thức:

~~~java
static void process(List<String> values) {
    record ParsedValue(String original, String normalized) {
    }

    List<ParsedValue> parsed = values.stream()
            .map(value -> new ParsedValue(value, value.strip().toLowerCase()))
            .toList();

    parsed.forEach(System.out::println);
}
~~~

Quy tắc cần nhớ:

- Local record chỉ có thể được dùng trong phạm vi lexical nơi khai báo và các block lồng bên trong phù hợp.
- Có thể tạo nhiều instance, lưu trong collection cục bộ, dùng làm kiểu phần tử của stream hoặc truyền cho lambda trong phạm vi đó.
- Record tự sinh accessor theo tên component, ví dụ `original()` và `normalized()`.
- Record class là `final` và các component là `final`; không thể kế thừa một record để bổ sung trạng thái.
- Một local record **ngầm định là static**. Nó không giữ tham chiếu ngầm tới instance bao quanh và không thể đọc trực tiếp biến cục bộ hoặc type parameter của phương thức bên ngoài như một local class thông thường có thể làm.
- Nếu kiểu kết quả cần được trả về từ phương thức, dùng làm kiểu field, hoặc chia sẻ giữa nhiều phương thức, hãy cân nhắc khai báo record ở cấp thành viên hoặc cấp package.

### 2.1. Record cục bộ có thể có constructor và phương thức

Local record có các khả năng cơ bản giống record khác: compact constructor để kiểm tra dữ liệu, phương thức instance và có thể triển khai interface.

~~~java
static void showAmounts(List<BigDecimal> amounts) {
    record Amount(BigDecimal value, String currency) {
        Amount {
            Objects.requireNonNull(value, "value");
            Objects.requireNonNull(currency, "currency");
            if (currency.isBlank()) {
                throw new IllegalArgumentException("currency is blank");
            }
        }

        String display() {
            return value + " " + currency;
        }
    }

    amounts.stream()
            .map(value -> new Amount(value, "VND"))
            .map(Amount::display)
            .forEach(System.out::println);
}
~~~

Ở đây, record giữ cả số tiền và đơn vị tiền tệ trong cùng một giá trị. Compact constructor bảo đảm các component hợp lệ trước khi instance được tạo.

### 2.2. Local record không capture biến cục bộ

Vì local record ngầm định là static, phần thân record không thể dùng trực tiếp biến cục bộ của phương thức bao quanh:

~~~java
static void invalidCapture() {
    String currency = "VND";

    record Amount(BigDecimal value) {
        // Không hợp lệ: local record không capture biến currency.
        // String display() { return value + " " + currency; }
    }
}
~~~

Nếu giá trị bên ngoài cần trở thành một phần của dữ liệu trung gian, hãy truyền nó vào component:

~~~java
static void validCaptureAlternative(List<BigDecimal> values) {
    String currency = "VND";

    record Amount(BigDecimal value, String currency) {
        String display() {
            return value + " " + currency;
        }
    }

    values.stream()
            .map(value -> new Amount(value, currency))
            .map(Amount::display)
            .forEach(System.out::println);
}
~~~

Lambda trong phương thức có thể capture biến `currency` nếu biến đó là final hoặc effectively final. Nó truyền giá trị vào constructor; chính record lưu dữ liệu qua component. Phần thân record chỉ đọc component của chính nó.

### 2.3. Local record trong phương thức generic

Local record không thể dùng trực tiếp type parameter của phương thức bao quanh vì nó ngầm định static:

~~~java
static <T> void invalidGeneric(List<T> values) {
    // Không hợp lệ: local record không thể capture T của method.
    // record Box(T value) {}
}
~~~

Nếu cần một kiểu generic cục bộ, khai báo type parameter riêng cho record:

~~~java
static <T> void printValues(List<T> values) {
    record Box<U>(U value) {
    }

    values.stream()
            .map(value -> new Box<T>(value))
            .map(Box::value)
            .forEach(System.out::println);
}
~~~

`Box<U>` có type parameter độc lập. Khi dùng trong phương thức, ta khởi tạo `Box<T>`; `T` được truyền vào như đối số kiểu tại điểm sử dụng, chứ không bị record capture từ môi trường bên ngoài.

## 3. Local record phù hợp với stream pipeline như thế nào?

Một stream pipeline thường gồm ba nhóm thao tác:

1. **Nguồn dữ liệu:** collection, array, stream hoặc nguồn khác.
2. **Intermediate operations:** `map`, `filter`, `flatMap`, `sorted`, `distinct`, `peek`... Các thao tác này mô tả cách chuyển đổi/lọc dữ liệu và thường được thực thi lazy.
3. **Terminal operation:** `toList`, `collect`, `reduce`, `forEach`, `count`... Terminal operation kích hoạt quá trình xử lý.

Local record rất hữu ích khi một intermediate operation tạo ra một giá trị có nhiều trường, hoặc khi collector cần giữ một số kết quả tổng hợp có liên quan.

~~~text
List<Order>
    |
    | stream()
    v
Stream<Order>
    |
    | grouping / map / filter
    v
Stream hoặc Collector dùng LocalRecord
    |
    | collect() / toList()
    v
Kết quả tổng hợp trong phạm vi phương thức
~~~

Ví dụ, từ một đơn hàng có thể tính ra một dòng kết quả trung gian gồm mã sản phẩm, số lượng và thành tiền:

~~~java
static void printLineTotals(List<OrderLine> lines) {
    record LineTotal(String sku, long quantity, BigDecimal amount) {
    }

    List<LineTotal> totals = lines.stream()
            .map(line -> new LineTotal(
                    line.sku(),
                    line.quantity(),
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity()))))
            .toList();

    totals.forEach(total -> System.out.printf(
            "%s: %d x -> %s%n",
            total.sku(), total.quantity(), total.amount()));
}
~~~

`LineTotal` giúp các bước sau đọc tên trường thay vì nhớ vị trí phần tử trong mảng. Một đối tượng trung gian cũng có thể được dùng để sort, filter hoặc nhóm theo một component.

## 4. Ví dụ đầy đủ: tổng hợp doanh thu theo khách hàng

Ta xây dựng một báo cáo từ collection đơn hàng. Mỗi đơn có mã khách hàng và tổng tiền. Kết quả cần mã khách hàng, số lượng đơn và tổng doanh thu.

`Totals` chỉ là dữ liệu nội bộ trong quá trình tổng hợp của phương thức `summarize`. Vì vậy, ta khai báo nó dưới dạng local record.

### 4.1. Mô hình đầu vào và kết quả công khai

Tệp `CustomerReport.java`:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class CustomerReport {
    private CustomerReport() {
    }

    public record Order(String customerId, BigDecimal total) {
        public Order {
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(total, "total");
            if (customerId.isBlank()) {
                throw new IllegalArgumentException(
                        "customerId must not be blank");
            }
        }
    }

    public record CustomerSummary(
            String customerId,
            long orderCount,
            BigDecimal revenue) {
    }

    public static List<CustomerSummary> summarize(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");

        // Kiểu này chỉ cần trong phương thức summarize.
        record Totals(long orderCount, BigDecimal revenue) {
            Totals {
                Objects.requireNonNull(revenue, "revenue");
            }
        }

        Map<String, Totals> totalsByCustomer = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::customerId,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.mapping(
                                        Order::total,
                                        Collectors.reducing(
                                                BigDecimal.ZERO,
                                                BigDecimal::add)),
                                Totals::new)));

        return totalsByCustomer.entrySet().stream()
                .map(entry -> new CustomerSummary(
                        entry.getKey(),
                        entry.getValue().orderCount(),
                        entry.getValue().revenue()))
                .sorted(
                        Comparator.comparing(CustomerSummary::revenue)
                                .reversed()
                                .thenComparing(CustomerSummary::customerId))
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("CUST-01", new BigDecimal("100.00")),
                new Order("CUST-02", new BigDecimal("250.00")),
                new Order("CUST-01", new BigDecimal("75.50")),
                new Order("CUST-03", new BigDecimal("80.00")),
                new Order("CUST-02", new BigDecimal("50.00")));

        summarize(orders).forEach(System.out::println);
    }
}
~~~

Trong Java 17, `Collectors.teeing()` có sẵn từ Java 12. Nó chạy hai collector trên cùng một nhóm phần tử rồi kết hợp hai kết quả bằng hàm merge. Ở đây:

- `counting()` đếm số đơn trong nhóm.
- `mapping(Order::total, reducing(...))` lấy tổng tiền của các đơn.
- `Totals::new` nhận hai kết quả và tạo local record giữ chúng cùng nhau.

Sau bước grouping, map có dạng khái niệm:

~~~text
"CUST-01" -> Totals(orderCount=2, revenue=175.50)
"CUST-02" -> Totals(orderCount=2, revenue=300.00)
"CUST-03" -> Totals(orderCount=1, revenue=80.00)
~~~

Sau đó stream các entry để chuyển sang `CustomerSummary`, sắp xếp doanh thu giảm dần và mã khách hàng tăng dần khi doanh thu bằng nhau.

### 4.2. Vì sao dùng local record `Totals`?

Nếu dùng `Object[]`, người đọc phải biết vị trí nào là count và vị trí nào là revenue. Nếu dùng `Map.Entry<Long, BigDecimal>`, ý nghĩa hai thành phần cũng không rõ bằng tên miền nghiệp vụ. Local record biểu diễn đúng cấu trúc:

~~~java
record Totals(long orderCount, BigDecimal revenue) {
}
~~~

Đồng thời:

- Kiểu chỉ xuất hiện trong `summarize`, nơi nó được tạo và sử dụng.
- Không làm tăng số kiểu top-level của package.
- Có accessor có kiểu rõ ràng: `orderCount()` và `revenue()`.
- Dễ in log nhờ `toString()` tự sinh.
- Dễ so sánh giá trị nhờ `equals()` và `hashCode()` dựa trên component.

`CustomerSummary` lại được khai báo ở cấp thành viên vì nó là kiểu kết quả công khai mà phương thức trả về. Đây là ranh giới hữu ích: **kiểu trung gian nội bộ là local record; kiểu kết quả cần xuất khỏi phương thức là kiểu có phạm vi rộng hơn**.

### 4.3. Kết quả chạy

Biên dịch và chạy:

~~~text
javac --release 17 -encoding UTF-8 CustomerReport.java
java CustomerReport
~~~

Đầu ra:

~~~text
CustomerSummary[customerId=CUST-02, orderCount=2, revenue=300.00]
CustomerSummary[customerId=CUST-01, orderCount=2, revenue=175.50]
CustomerSummary[customerId=CUST-03, orderCount=1, revenue=80.00]
~~~

`BigDecimal` được dùng cho tiền thay vì `double`, nhằm tránh sai số biểu diễn nhị phân thường gặp khi tính toán số thập phân. Ví dụ giả định tất cả giá trị đầu vào đã cùng đơn vị tiền tệ và cùng quy tắc làm tròn; ứng dụng thực tế cần mô hình hóa currency và rounding policy nếu có nhiều loại tiền.

## 5. Local record trong các bước xử lý khác

### 5.1. `map`: biến đổi một phần tử thành kết quả có nhiều trường

~~~java
static List<String> normalizeNames(List<String> names) {
    record NormalizedName(String original, String value, boolean changed) {
    }

    return names.stream()
            .map(name -> {
                String normalized = name.strip().toLowerCase(Locale.ROOT);
                return new NormalizedName(
                        name, normalized, !name.equals(normalized));
            })
            .filter(NormalizedName::changed)
            .map(NormalizedName::value)
            .toList();
}
~~~

`NormalizedName` giúp giữ đồng thời giá trị gốc, giá trị chuẩn hóa và cờ cho biết có thay đổi. Các bước sau có thể lọc theo `changed()` rồi chỉ lấy `value()`.

### 5.2. `filter`: giữ kết quả đã kiểm tra

~~~java
static void printParsedScores(List<String> inputs) {
    record ParsedScore(String source, int value) {
    }

    inputs.stream()
            .map(input -> {
                try {
                    return Optional.of(
                            new ParsedScore(input, Integer.parseInt(input)));
                } catch (NumberFormatException exception) {
                    return Optional.<ParsedScore>empty();
                }
            })
            .flatMap(Optional::stream)
            .filter(parsed -> parsed.value() >= 0 && parsed.value() <= 100)
            .forEach(System.out::println);
}
~~~

`Optional.stream()` có từ Java 9 nên dùng được trong Java 17. Cách này tránh phần tử `null` trong stream. Record giữ dữ liệu nguồn cùng kết quả parse; các bước tiếp theo chỉ nhận những phần tử parse thành công.

### 5.3. `sorted`: giữ khóa sắp xếp cùng dữ liệu

~~~java
static void printByNormalizedName(List<String> names) {
    record SortKey(String original, String normalized) {
    }

    names.stream()
            .map(name -> new SortKey(
                    name, name.strip().toLowerCase(Locale.ROOT)))
            .sorted(Comparator.comparing(SortKey::normalized))
            .map(SortKey::original)
            .forEach(System.out::println);
}
~~~

Local record giữ khóa so sánh và giá trị gốc cùng nhau. Khi sort xong, chương trình lấy lại giá trị ban đầu để hiển thị.

### 5.4. `flatMap`: biểu diễn phần tử đã tách

Giả sử mỗi dòng log chứa một mã đơn hàng và nhiều tag. Có thể dùng local record để giữ thông tin nguồn khi làm phẳng danh sách:

~~~java
static List<String> allTags(List<LogLine> lines) {
    record TaggedValue(String orderId, String tag) {
    }

    return lines.stream()
            .flatMap(line -> line.tags().stream()
                    .map(tag -> new TaggedValue(line.orderId(), tag)))
            .filter(value -> value.tag() != null && !value.tag().isBlank())
            .map(TaggedValue::tag)
            .toList();
}
~~~

Local record cho phép giữ `orderId` và `tag` trong suốt bước `flatMap`; nếu các bước tiếp theo cần nhóm tag theo đơn, thông tin nguồn vẫn sẵn có. Nếu chỉ cần tag cuối cùng và không dùng `orderId`, record có thể là không cần thiết; hãy tránh thêm kiểu trung gian không mang lại ý nghĩa.

## 6. So sánh local record với các cách biểu diễn khác

| Cách biểu diễn | Ưu điểm | Hạn chế | Khi phù hợp |
|---|---|---|---|
| Local record | Có tên component, kiểu rõ, `equals/hashCode/toString` tự sinh, phạm vi hẹp. | Không thể dùng làm kiểu trả về công khai bên ngoài phạm vi khai báo; ngầm định static. | Kết quả trung gian chỉ dùng trong một phương thức/block. |
| Record cấp thành viên | Có đặc tính record và tái sử dụng được trong nhiều phương thức của lớp. | Mở rộng phạm vi hơn mức cần thiết nếu chỉ dùng một nơi. | Kiểu kết quả dùng chung trong một lớp hoặc API. |
| Record top-level | Có thể dùng giữa nhiều lớp/package và làm kiểu API. | Tạo thêm một kiểu cấp package/module. | Dữ liệu miền hoặc kết quả được chia sẻ rộng. |
| `Map.Entry<K,V>` | Có sẵn, tiện cho cặp key/value. | Chỉ biểu diễn hai thành phần; tên key/value có thể không diễn đạt đúng miền nghiệp vụ. | Một cặp khóa/giá trị thật sự. |
| Mảng (`Object[]`, `long[]`) | Ít cú pháp, có thể gọn trong tính toán thấp cấp. | Không có tên trường; dễ sai chỉ số/ép kiểu; có thể mutable. | Dữ liệu số hiệu năng thấp cấp, cấu trúc cố định và đã rõ quy ước. |
| Class thông thường | Có thể tùy chỉnh mutability, kế thừa, lifecycle và logic phức tạp. | Nhiều mã khung hơn record. | Đối tượng có hành vi, trạng thái thay đổi hoặc vòng đời phức tạp. |

Local record không phải lúc nào cũng tốt hơn một biến đơn giản. Nếu kết quả chỉ là một `long`, cứ dùng `long`. Nếu có hai giá trị độc lập nhưng không cần tạo kiểu mới, `Map.Entry` có thể đủ. Dùng local record khi **một nhóm trường có ý nghĩa chung và được xử lý như một đơn vị**.

## 7. Các giới hạn và lưu ý khi dùng trong Collection/Stream

### 7.1. Component của record chỉ bất biến nông

Record có component final, nhưng điều đó không tự làm object được tham chiếu trở nên bất biến:

~~~java
record Snapshot(List<String> tags) {
}
~~~

Tham chiếu `tags` là final, nhưng list bên trong vẫn có thể thay đổi nếu người gọi giữ một tham chiếu mutable. Nếu cần snapshot không cho sửa qua accessor, hãy sao chép trong constructor:

~~~java
record Snapshot(List<String> tags) {
    Snapshot {
        tags = List.copyOf(tags);
    }
}
~~~

`List.copyOf` tạo list không sửa được và từ chối phần tử `null`. Đây là lựa chọn phù hợp nếu hợp đồng dữ liệu yêu cầu danh sách tag không chứa `null`.

### 7.2. Không để local record thoát ra ngoài nơi khai báo

Local record có phạm vi hẹp. Bạn không thể khai báo một phương thức khác ở ngoài block rồi dùng tên kiểu local record làm kiểu tham số hoặc kiểu trả về:

~~~java
static void example() {
    record Intermediate(long count) {
    }

    Intermediate value = new Intermediate(10);
    System.out.println(value.count());
}

// Không thể viết một method cấp lớp nhận Intermediate,
// vì tên kiểu Intermediate không nằm trong phạm vi ở đây.
~~~

Nếu cần truyền kết quả sang lớp khác, hãy chuyển nó thành kiểu có phạm vi phù hợp, chẳng hạn record thành viên/top-level, hoặc chuyển đổi sang DTO/API model ở ranh giới phương thức.

### 7.3. Local record không phải cơ chế tối ưu hiệu năng tự động

Record giúp mã nguồn rõ ràng, nhưng không nên giả định nó luôn nhanh hơn class hoặc mảng. Mỗi lần tạo một record vẫn có thể tạo một object; JVM có thể tối ưu một số allocation nhờ JIT/escape analysis nhưng không nên dựa vào điều đó nếu chưa đo.

Với pipeline rất lớn, hãy benchmark trên dữ liệu đại diện và kiểm tra allocation/GC nếu hiệu năng là yêu cầu quan trọng. Đừng chuyển sang `Object[]` chỉ vì lo lắng trước khi có số liệu; cấu trúc có tên thường giảm lỗi bảo trì.

### 7.4. Không dùng stream side effect để lấp dữ liệu trung gian

Tránh tạo một collection bên ngoài rồi dùng `forEach` để thêm dữ liệu vào nó:

~~~java
// Không nên dùng side effect làm cách mặc định để biến đổi stream.
List<String> output = new ArrayList<>();
values.stream().forEach(value -> output.add(value.strip()));
~~~

Hãy dùng `map(...).toList()` hoặc `collect(...)`. Local record có thể giúp mỗi phép `map` trả ra một giá trị có cấu trúc, làm pipeline dễ đọc và ít side effect hơn.

## 8. Khi nào local record nên trở thành record dùng chung?

Một local record phù hợp khi:

- Chỉ một phương thức tạo và tiêu thụ dữ liệu đó.
- Tên component giúp làm rõ các bước `map`, `filter`, `collect`, `sorted`.
- Kiểu không phải một phần của hợp đồng public.
- Dữ liệu trung gian có cấu trúc ổn định trong phạm vi xử lý.

Nên chuyển thành record cấp thành viên hoặc top-level nếu:

- Nhiều phương thức hoặc nhiều lớp cùng cần kiểu đó.
- Nó là kiểu trả về của API, service hoặc repository.
- Cần viết test trực tiếp với kiểu đó từ package khác.
- Nó thể hiện một khái niệm miền có ý nghĩa độc lập.
- Cấu trúc cần tài liệu hóa, serialize hoặc trao đổi qua module.

Ví dụ `Totals` trong `CustomerReport.summarize()` là local record vì chỉ phục vụ collector. `CustomerSummary` được trả ra khỏi phương thức nên phải có phạm vi rộng hơn.

## 9. Kiểm thử logic tạo kết quả trung gian

Một record tự sinh `equals()` và `hashCode()` dựa trên các component, nên rất thuận tiện khi kiểm thử giá trị:

~~~java
record Totals(long count, BigDecimal revenue) {
}

Totals actual = new Totals(2, new BigDecimal("175.50"));
Totals expected = new Totals(2, new BigDecimal("175.50"));

assertEquals(expected, actual);
~~~

Trong code test thực tế, nếu local record được khai báo trong phương thức production, test bên ngoài không thể nhắc trực tiếp tên kiểu local đó. Hãy kiểm thử qua kết quả công khai của phương thức hoặc tách phép tính thành một phương thức có kiểu trả về phù hợp.

Với `CustomerReport`, có thể kiểm tra:

- Mỗi customer có số lượng đơn đúng.
- Tổng tiền là tổng của các đơn thuộc customer đó.
- Kết quả được sắp xếp theo doanh thu giảm dần.
- Khi doanh thu bằng nhau, mã customer được sắp xếp tăng dần.
- Danh sách đầu vào rỗng tạo ra danh sách kết quả rỗng.
- Đầu vào `null` bị từ chối theo hợp đồng `Objects.requireNonNull`.

Ví dụ đầu vào rỗng:

~~~java
List<CustomerReport.CustomerSummary> empty =
        CustomerReport.summarize(List.of());

if (!empty.isEmpty()) {
    throw new AssertionError("Expected empty summary");
}
~~~

Local record giúp triển khai bước tổng hợp rõ ràng; kiểm thử vẫn cần xác nhận kết quả cuối cùng theo yêu cầu nghiệp vụ.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không dùng được tên local record ở phương thức khác | Kiểu chỉ có phạm vi trong block đã khai báo. | Đưa record lên cấp thành viên/top-level nếu cần tái sử dụng. |
| Local record không truy cập được biến cục bộ | Local record ngầm định static, không capture biến bao quanh. | Truyền giá trị vào component hoặc tính giá trị khi tạo instance. |
| Dùng type parameter của method trong local record | Local record không capture type parameter từ phương thức bao quanh. | Khai báo type parameter riêng cho record, ví dụ `record Box<U>(U value)`. |
| Dữ liệu trong record vẫn thay đổi | Component final chỉ cố định tham chiếu, không làm object bên trong bất biến. | Sao chép collection hoặc dùng kiểu dữ liệu bất biến theo hợp đồng. |
| Dùng `Object[]` cho kết quả nhiều trường | Không có tên component và phải ép kiểu thủ công. | Dùng local record với tên trường có nghĩa. |
| Dùng local record dù chỉ có một giá trị | Tạo kiểu không cần thiết. | Dùng kiểu đơn giản nếu không có nhóm dữ liệu cần đặt tên. |
| Collector không kết hợp được hai kết quả | Chữ ký hàm merge hoặc kiểu generic không khớp. | Kiểm tra kiểu trả về của từng collector và constructor local record. |
| Dùng `List.get(i)` trong stream trên `LinkedList` | Truy cập theo chỉ số có thể tốn thời gian tuyến tính mỗi lần. | Duyệt stream trực tiếp hoặc dùng iterator/stream phù hợp. |
| Dùng `double` cho tiền | Sai số biểu diễn số thập phân có thể tích lũy. | Dùng `BigDecimal` với quy tắc scale/rounding rõ ràng. |

## 11. Bài tập thực hành

### Bài tập 1 — Tạo kết quả parse

Cho danh sách chuỗi biểu diễn số lượng. Khai báo local record `ParsedQuantity(String source, int quantity)` trong phương thức xử lý. Dùng stream để parse từng chuỗi, chỉ giữ giá trị từ 1 đến 100 và in cả chuỗi gốc cùng số nguyên đã parse.

### Bài tập 2 — Tổng hợp theo loại sản phẩm

Cho danh sách `ProductSale(category, amount)`. Dùng local record `CategoryTotal(long count, BigDecimal revenue)` để nhóm theo category, đếm số dòng và tính tổng amount bằng collector.

### Bài tập 3 — Tạo khóa sắp xếp

Cho danh sách tên người dùng. Dùng local record giữ `originalName` và `normalizedName`, sắp xếp theo `normalizedName`, sau đó in `originalName`. Xác định locale phù hợp khi chuẩn hóa mã định danh.

### Bài tập 4 — Kiểm tra giới hạn capture

Viết một phương thức generic `<T>` và thử khai báo local record có component kiểu `T`. Quan sát lỗi biên dịch, sau đó sửa bằng cách khai báo local record generic riêng như `record Box<U>(U value)`.

### Bài tập 5 — Quyết định phạm vi kiểu

Giả sử `CustomerSummary` chỉ dùng trong một phương thức báo cáo. Hãy cân nhắc để nó là local record. Sau đó giả sử ba service khác cũng nhận và trả `CustomerSummary`; giải thích vì sao nên chuyển nó lên thành viên/top-level record.

### Gợi ý tự đối chiếu

- Bài 1: Local record lưu dữ liệu nguồn và giá trị đã parse; bắt `NumberFormatException` hoặc dùng `Optional` để biểu diễn lỗi.
- Bài 2: Có thể dùng `groupingBy` kết hợp `teeing(counting(), mapping(... reducing(...)), CategoryTotal::new)`.
- Bài 3: Chuẩn hóa bằng `toLowerCase(Locale.ROOT)` nếu tên được dùng như khóa kỹ thuật không phụ thuộc locale.
- Bài 4: Local record ngầm định static; record generic phải khai báo type parameter của chính nó.
- Bài 5: Phạm vi của kiểu nên phản ánh phạm vi sử dụng; kiểu trao đổi giữa service không nên bị ẩn trong một method.

## 12. Các nguyên tắc cần ghi nhớ

- Local record là record được khai báo trong một block, thường là bên trong phương thức.
- Nó thích hợp để biểu diễn kết quả trung gian có nhiều component trong collection và stream pipeline.
- Các component có tên và kiểu rõ ràng, giúp thay thế những mảng hoặc cặp dữ liệu khó hiểu.
- Local record ngầm định static, không capture instance bao quanh, biến cục bộ hoặc type parameter của phương thức.
- Nếu cần dữ liệu bên ngoài, truyền dữ liệu qua constructor/component; lambda tạo instance vẫn có thể dùng biến effectively final của phương thức.
- Record bất biến nông: component final không tự làm collection bên trong bất biến.
- Local record không thể làm kiểu trả về/field ở ngoài phạm vi khai báo. Nếu cần chia sẻ, chuyển nó thành record cấp thành viên hoặc top-level.
- `map`, `filter`, `flatMap`, `sorted` và `collect` có thể phối hợp với local record để tạo pipeline dễ đọc, ít side effect.
- Dùng `BigDecimal` cho tiền và xác định quy tắc rounding/currency trong nghiệp vụ thực tế.
- Không thêm local record nếu một kiểu đơn giản đã đủ; hãy dùng nó khi tên component thực sự làm dữ liệu dễ hiểu hơn.

### Tài liệu tham khảo

- [Java SE 17 Language Specification — Section 8.10: Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [Java SE 17 Language Specification — Section 14.3: Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3).
- [Java SE 17 API — Collectors.teeing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#teeing(java.util.stream.Collector,java.util.stream.Collector,java.util.function.BiFunction)).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
