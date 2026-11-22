# Sử dụng record với Stream và API thư viện có hỗ trợ (Java 17+)

## 1. Mục tiêu và phạm vi

`record` là một **kiểu lớp mang dữ liệu** (data carrier) của Java. Nó phù hợp để truyền các bản ghi có cấu trúc rõ ràng qua pipeline `Stream`, gom nhóm kết quả, biểu diễn khóa tổng hợp, làm DTO cho API, và làm đối tượng kết quả khi thư viện hỗ trợ record.

Ví dụ:

```java
record OrderItem(String product, int quantity, long unitPrice) {
    long total() {
        return (long) quantity * unitPrice;
    }
}
```

Với record này, Java tự cung cấp các accessor `product()`, `quantity()`, `unitPrice()` và các phương thức `equals`, `hashCode`, `toString` theo record components. Các phương thức thường là **method references** rất thuận tiện khi xử lý Stream:

```java
// Trích đoạn trong một phương thức, sau khi có List<OrderItem> items:
List<String> products = items.stream()
        .map(OrderItem::product)
        .distinct()
        .sorted()
        .toList();
```

Điểm trọng tâm:

- **Stream không cần API đặc biệt cho record.** Record vẫn là một object Java; các phép `map`, `filter`, `sorted`, `collect`, `groupingBy` làm việc bình thường.
- Accessor record có tên `component()`, chẳng hạn `product()`, thay vì giả định có `getProduct()` như quy ước JavaBeans.
- Record thích hợp cho **giá trị kết quả** và **khóa bản ghi** khi các component có ý nghĩa giá trị và có `equals`/`hashCode` ổn định.
- Một thư viện ngoài JDK chỉ có thể tự động đọc/ghi record khi **phiên bản và cơ chế mapping** của thư viện hỗ trợ constructor/component metadata của record.

**Phiên bản:** record đã chính thức từ **Java 16**. Bài tập chạy độc lập với **Java 17+**; chỉ dùng các API vẫn có trong Java hiện đại. Không cần `--enable-preview` hay cú pháp record thử nghiệm của Java 14.

## 2. Dùng record trong pipeline Stream

Giả sử có record:

```java
record Sale(String region, String product, int quantity, int unitPrice) {
    long total() {
        return (long) quantity * unitPrice;
    }
}
```

Mỗi `Sale` mang dữ liệu gắn bó theo một giao dịch. Khi gọi `Sale::quantity`, `Sale::region` hay `Sale::total`, Java tham chiếu đến các phương thức instance không tham số và sử dụng giá trị chúng trả về trong pipeline.

| Phép xử lý | Vai trò | Ví dụ với record |
| --- | --- | --- |
| `filter` | Giữ những bản ghi thỏa điều kiện | `.filter(s -> s.quantity() >= 3)` |
| `map` | Chuyển từ record sang giá trị hoặc record khác | `.map(s -> new SaleView(s.product(), s.quantity()))` |
| `mapToLong` | Chuyển sang luồng số nguyên dài để tổng hợp | `.mapToLong(Sale::total).sum()` |
| `sorted` | Sắp xếp theo component hoặc tiêu chí | `.sorted(Comparator.comparing(Sale::product))` |
| `distinct` | Loại giá trị trùng dựa trên `equals` | `.distinct()` |
| `collect` | Tạo map, group hoặc thống kê | `.collect(Collectors.groupingBy(Sale::region))` |
| `toList` | Thu kết quả thành danh sách | `.toList()` (Java 16+) |

Record **không mặc nhiên triển khai `Comparable`**. Muốn gọi `sorted()` không tham số thì các phần tử phải có thứ tự tự nhiên tương thích; với record tự định nghĩa, thường truyền `Comparator` tường minh.

### 2.1. Từ dữ liệu thô thành record kết quả

Thay vì trả về `Object[]` hoặc danh sách chỉ số khó hiểu, có thể tạo record mô tả dữ liệu hiển thị:

```java
record SaleView(String product, int quantity) {}

// Trích đoạn trong phương thức có biến List<Sale> sales:
List<SaleView> large = sales.stream()
        .filter(s -> s.quantity() >= 3)
        .map(s -> new SaleView(s.product(), s.quantity()))
        .sorted(Comparator.comparing(SaleView::product)
                .thenComparingInt(SaleView::quantity))
        .toList();
```

`filter` giữ đơn hàng từ 3 sản phẩm trở lên; `map` tạo DTO mới; `sorted` sắp theo tên rồi số lượng. Không có setter hay gán lại component fields: mỗi phần tử được biến đổi thành **record khác**.

**Lưu ý về `toList()`:** phương thức `Stream.toList()` trả danh sách **không sửa được** (unmodifiable). Nó giữ *encounter order* nếu stream đầu vào có thứ tự. Không giả định kết quả là `ArrayList` hoặc có thể gọi `add`. `Collectors.toList()` có hợp đồng riêng, **không bảo đảm** kiểu trả về hoặc khả năng sửa; nếu cần danh sách chắc chắn có thể sửa, dùng `collect(Collectors.toCollection(ArrayList::new))`. Nếu muốn danh sách không sửa được rõ ràng, `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` là những lựa chọn khác nhau về hợp đồng (chẳng hạn `toUnmodifiableList` không chấp nhận phần tử `null`).

### 2.2. Tổng hợp dữ liệu số

Phương thức bình thường trên record vẫn dùng như accessor trong method reference:

```java
long totalRevenue = sales.stream()
        .mapToLong(Sale::total)
        .sum();
```

`mapToLong` tránh giữ `Stream<Long>` có boxing ở mỗi bước; `sum()` là terminal operation. Nếu nhân hai số `int` rồi muốn nhận `long`, phải ép kiểu **trước** phép nhân: `(long) quantity * unitPrice`, tránh phép nhân `int` tràn trước khi chuyển sang `long`.

## 3. Gom nhóm theo component và làm khóa tổng hợp

### 3.1. `groupingBy` với một component

```java
Map<String, Long> unitsByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.summingLong(Sale::quantity)));
```

- `Sale::region` tạo khóa nhóm kiểu `String`.
- `summingLong(Sale::quantity)` cộng số lượng theo từng vùng.
- `TreeMap::new` tạo map sắp khóa tăng dần để kết quả minh họa có thứ tự ổn định. Nếu không yêu cầu thứ tự, có thể dùng `groupingBy(Sale::region, ...)` và **không dựa vào thứ tự duyệt** của map trả về.

Với dữ liệu đã được kiểm tra `region != null`, phép gom nhóm được dùng nhất quán. Không mặc nhiên coi `groupingBy` sẽ cung cấp khóa `null` phù hợp; nên xác thực input để tránh lỗi runtime khi khóa phân nhóm không hợp lệ.

### 3.2. Dùng record làm composite key

Khi nhóm theo **nhiều component**, một record là kiểu khóa rõ ràng hơn ghép chuỗi `region + "|" + product`:

```java
record RegionProduct(String region, String product) {}

// Trích đoạn:
Map<RegionProduct, Long> revenueByKey = sales.stream()
        .collect(Collectors.groupingBy(
                s -> new RegionProduct(s.region(), s.product()),
                Collectors.summingLong(Sale::total)));

long revenue = revenueByKey.get(
        new RegionProduct("HN", "Book"));
```

`RegionProduct("HN", "Book")` làm khóa dựa trên **giá trị của hai component** nhờ `equals`/`hashCode` được sinh tự động. Khi tra cứu bằng **một instance record khác có các giá trị component tương đương**, `Map.get` vẫn tìm được kết quả. Không phải tự viết class khóa và các phương thức so sánh thường gặp.

**Điều kiện quan trọng:** component làm khóa phải có ngữ nghĩa `equals`/`hashCode` đúng và **ổn định**. Nếu khóa record chứa mảng hoặc object mutable, việc sửa dữ liệu bên trong có thể làm map lookup không nhất quán. Với mảng, `equals` sinh tự động so sánh tham chiếu mảng (không so sánh từng phần tử), nên không coi `record ArrayKey(byte[] bytes)` là khóa nội dung mảng an toàn nếu chưa thiết kế rõ defensive copy và equals/hashCode.

### 3.3. Tổng hợp nhiều thống kê với `teeing`

`Collectors.teeing` (Java 12+) kết hợp **hai bộ thu** và trả một kết quả bằng hàm hợp nhất. Record rất tiện để mang kết quả đó:

```java
record RegionStats(long units, long revenue) {}

Map<String, RegionStats> byRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.teeing(
                        Collectors.summingLong(Sale::quantity),
                        Collectors.summingLong(Sale::total),
                        RegionStats::new)));
```

Trong mỗi nhóm, bộ thu thứ nhất tính tổng số lượng, bộ thu thứ hai tính tổng doanh thu; `RegionStats::new` là **constructor reference** tạo record có hai component `units` và `revenue`. Không cần mở nhiều stream độc lập để tính từng phép tổng hợp.

## 4. `toMap` và khóa trùng: cần hàm gộp

Nếu lấy `product` làm khóa, nhiều bản ghi có thể cùng sản phẩm. Câu lệnh dưới đây có thể ném `IllegalStateException` khi hai phần tử cùng khóa:

```java
// CỐ Ý THIẾU MERGE FUNCTION khi product xuất hiện nhiều lần:
Map<String, Long> bad = sales.stream()
        .collect(Collectors.toMap(
                Sale::product,
                Sale::total));
```

Cách xử lý khi nghiệp vụ muốn cộng doanh thu theo sản phẩm:

```java
Map<String, Long> byProduct = sales.stream()
        .collect(Collectors.toMap(
                Sale::product,
                Sale::total,
                Long::sum,
                TreeMap::new));
```

`Long::sum` được gọi khi có khóa trùng và cộng hai giá trị. Đây là giải pháp nghiệp vụ rõ ràng; nếu cần giữ **tất cả** bản ghi theo khóa thì nên dùng `groupingBy` tạo `Map<String, List<Sale>>` thay vì `toMap` làm mất phần tử.

Trường hợp cần chỉ giữ giá trị cũ hoặc mới có thể truyền hàm gộp phù hợp, nhưng quyết định phải dựa vào quy tắc dữ liệu. **Record không làm khóa trùng biến mất:** bản thân record hỗ trợ so sánh giá trị, còn xử lý trùng của `toMap` vẫn cần được xác định.

## 5. Chương trình Java 17+ đầy đủ để chạy và quan sát

Lưu nguyên mã thành **`RecordStreamDemo.java`**:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class RecordStreamDemo {
    record Sale(String region, String product, int quantity, int unitPrice) {
        Sale {
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(product, "product");
            if (quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("invalid sale");
            }
        }

        long total() {
            return (long) quantity * unitPrice;
        }
    }

    record RegionProduct(String region, String product) {}
    record SaleView(String product, int quantity) {}
    record RegionStats(long units, long revenue) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("HN", "Book", 2, 100),
                new Sale("HCM", "Pen", 5, 10),
                new Sale("HN", "Book", 1, 100),
                new Sale("HCM", "Book", 3, 100),
                new Sale("HN", "Pen", 4, 10)
        );

        List<SaleView> large = sales.stream()
                .filter(s -> s.quantity() >= 3)
                .map(s -> new SaleView(s.product(), s.quantity()))
                .sorted(Comparator.comparing(SaleView::product)
                        .thenComparingInt(SaleView::quantity))
                .toList();
        System.out.println("large=" + large);

        long grandTotal = sales.stream().mapToLong(Sale::total).sum();
        System.out.println("grandTotal=" + grandTotal);

        Map<String, RegionStats> byRegion = sales.stream().collect(
                Collectors.groupingBy(Sale::region, TreeMap::new,
                        Collectors.teeing(
                                Collectors.summingLong(Sale::quantity),
                                Collectors.summingLong(Sale::total),
                                RegionStats::new)));
        System.out.println("byRegion=" + byRegion);

        Map<RegionProduct, Long> byCompositeKey = sales.stream().collect(
                Collectors.groupingBy(
                        s -> new RegionProduct(s.region(), s.product()),
                        Collectors.summingLong(Sale::total)));
        System.out.println("hnBook=" + byCompositeKey.get(
                new RegionProduct("HN", "Book")));

        Map<String, Long> byProduct = sales.stream().collect(
                Collectors.toMap(Sale::product, Sale::total,
                        Long::sum, TreeMap::new));
        System.out.println("byProduct=" + byProduct);

        System.out.println("isRecord=" + Sale.class.isRecord());
        String fields = Arrays.stream(Sale.class.getRecordComponents())
                .map(RecordComponent::getName)
                .collect(Collectors.joining(","));
        System.out.println("components=" + fields);

        try {
            large.add(new SaleView("Test", 1));
        } catch (UnsupportedOperationException expected) {
            System.out.println("large is unmodifiable");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RecordStreamDemo.java
java RecordStreamDemo
```

Kết quả đã kiểm tra:

```text
large=[SaleView[product=Book, quantity=3], SaleView[product=Pen, quantity=4], SaleView[product=Pen, quantity=5]]
grandTotal=690
byRegion={HCM=RegionStats[units=8, revenue=350], HN=RegionStats[units=7, revenue=340]}
hnBook=300
byProduct={Book=600, Pen=90}
isRecord=true
components=region,product,quantity,unitPrice
large is unmodifiable
```

### Phân tích các kết quả

1. **`large`:** chỉ giữ phần tử có `quantity >= 3`; chuyển thành `SaleView` rồi sắp `product` và `quantity`. `SaleView[...]` là biểu diễn `toString()` do record cung cấp.
2. **`grandTotal=690`:** 200 + 50 + 100 + 300 + 40, tính bằng `mapToLong` và `sum`.
3. **`byRegion`:** vùng HCM có 8 đơn vị/350 doanh thu; vùng HN có 7 đơn vị/340 doanh thu. `TreeMap` tạo thứ tự khóa HCM rồi HN, còn `RegionStats` biểu diễn dữ liệu tổng hợp.
4. **`hnBook=300`:** khóa `RegionProduct("HN", "Book")` bằng về giá trị với khóa được tạo trong quá trình `groupingBy`, nên tra cứu được 200 + 100.
5. **`byProduct`:** nhờ `Long::sum`, các bản ghi `Book` được gộp thành 600 và `Pen` thành 90. Nếu thiếu merge function, `toMap` sẽ gặp khóa trùng.
6. **`isRecord=true`:** phản xạ JDK nhận biết `Sale` là record.
7. **`components=...`:** các record components được trả theo thứ tự khai báo trong header.
8. **`large is unmodifiable`:** danh sách từ `Stream.toList()` không cho phép `add`.

Đây là ví dụ **hoàn chỉnh chỉ dùng JDK**, nên không cần thêm Jackson, Spring hay thư viện bên thứ ba để chạy.

## 6. Các API chuẩn JDK hỗ trợ record trực tiếp

| API | Cách áp dụng | Điều cần lưu ý |
| --- | --- | --- |
| `java.util.stream.Stream` | Xử lý record như các phần tử bất kỳ, dùng method reference đến accessor | Pipeline lazy cho đến terminal operation; không được tái sử dụng stream sau terminal operation |
| `java.util.stream.Collectors` | `groupingBy`, `mapping`, `summingLong`, `teeing`, `toMap`, `toUnmodifiableList` | Chọn merge function cho khóa trùng; lựa chọn map/list có ảnh hưởng đến mutability và thứ tự |
| `java.util.Comparator` | `comparing(RecordType::component)` và `thenComparing...` | Record không tự có natural ordering |
| `java.util.Map` và `Set` | Record làm khóa hoặc phần tử khi `equals`/`hashCode` phù hợp | Tránh mutable component làm thay đổi ý nghĩa hash/equality |
| `java.util.Optional` | Giá trị record có thể vắng mặt sau `findFirst`, `max`, `min` | Kiểm tra `isPresent`/`orElse`/`map` thay vì gọi `get` vô điều kiện |
| `java.lang.Class` | `isRecord()` và `getRecordComponents()` | Phản xạ trên **kiểu khai báo**, không tự bảo đảm thư viện biết cách deserialize |
| `java.lang.reflect.RecordComponent` | `getName()`, `getType()`, `getAccessor()` | Thuộc mô hình reflection; cần xem quyền/module khi truy cập sâu và đừng giả định format khác tự hỗ trợ |

### 6.1. Phản xạ record: metadata để thư viện khai thác

Đối với `record Product(String sku, int stock) {}`:

```java
System.out.println(Product.class.isRecord()); // true
for (java.lang.reflect.RecordComponent component
        : Product.class.getRecordComponents()) {
    System.out.println(component.getName()
            + ": " + component.getType().getSimpleName());
}
```

Đây là **đoạn minh họa bên trong một phương thức** sau khi đã khai báo `Product`. Kết quả là tên các component theo thứ tự: `sku: String`, `stock: int`. `Class.getRecordComponents()` là một trong những API chuẩn giúp công cụ mapper, serializer, validation hoặc library nhận biết cấu trúc record khi được thiết kế để làm như vậy.

**Không đánh đồng “JDK có reflection cho record” với “mọi thư viện đều tự hỗ trợ record”.** Mỗi framework có quy tắc ánh xạ constructor, annotation, nullability và phiên bản riêng. Các thư viện chỉ hiểu JavaBeans `getX()/setX()` có thể cần nâng phiên bản hoặc adapter vì record không sinh setter và accessor mặc định mang tên `x()`.

## 7. JSON: Jackson có hỗ trợ record trong các phiên bản tương thích

**Jackson Databind** là thư viện ngoài JDK hỗ trợ ghi/đọc JSON. Jackson 2.12 đã giới thiệu hỗ trợ chính thức cho `java.lang.Record`; những dòng phiên bản mới cũng cần được kiểm tra tài liệu, cấu hình và tổ hợp dependency tương ứng trong ứng dụng.

Ví dụ **minh họa tích hợp Jackson 2.x đã có hỗ trợ record** (không phải mã chạy chỉ với JDK, cần dependency `jackson-databind` phù hợp):

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class JacksonRecordExample {
    public record OrderDto(String id, int quantity) {}

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        OrderDto source = new OrderDto("A-7", 3);
        String json = mapper.writeValueAsString(source);
        OrderDto restored = mapper.readValue(json, OrderDto.class);

        System.out.println(json);
        System.out.println(restored.equals(source));
    }
}
```

Khi thư viện được cấu hình hỗ trợ record, JSON chứa hai property tương ứng `id` và `quantity`; Jackson có thể gọi canonical constructor để tạo lại `OrderDto`. Ví dụ không đóng đinh thứ tự property trong chuỗi JSON vì thứ tự xuất ra có thể phụ thuộc cấu hình. Kết quả so sánh `restored.equals(source)` là `true` nếu mapping giữ nguyên các giá trị component.

Những lưu ý thực tế:

- Kiểm tra **phiên bản Jackson** tương thích với JDK và framework đang dùng; không tự pha các major version hoặc package import khác nhau.
- Các API Jackson 2.x trong ví dụ dùng package `com.fasterxml.jackson.databind`; khi dùng phiên bản major khác phải theo đúng API tài liệu của phiên bản đó.
- Tên field JSON mặc định thường gắn với tên component; khi cần tên property khác, kiểm tra cách dùng annotation như `@JsonProperty` và xử lý creator trong phiên bản đã chọn.
- Constructor/compact constructor của record có thể kiểm tra đầu vào; nếu JSON thiếu property, truyền `null` hoặc giá trị mặc định cho primitive không hợp lệ theo nghiệp vụ, thao tác deserialize có thể thất bại. Hãy xử lý và kiểm thử trường hợp dữ liệu thiếu/không hợp lệ.
- Record với generic components, kiểu ngày giờ, polymorphism hoặc custom serialization cần cấu hình và type metadata tương ứng; không khẳng định “mọi record đều tự deserialize” trong mọi trường hợp.

Thông tin về record support của Jackson được nêu trong [Jackson 2.12 release notes](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.12).

## 8. Spring Data JPA: record làm DTO projection, không làm entity

Trong hệ sinh thái Spring Data JPA, record là ứng viên phù hợp để biểu diễn **class-based projection/DTO** cho một tập thuộc tính được truy vấn.

Ví dụ **minh họa trong dự án Spring Data JPA đã cấu hình entity và repository**:

```java
// DTO record:
public record NamesOnly(String firstname, String lastname) {}

// Repository sketch; PersonEntity là entity được định nghĩa riêng:
interface PersonRepository
        extends org.springframework.data.repository.Repository<PersonEntity, Long> {
    java.util.List<NamesOnly> findByLastname(String lastname);
}
```

Đây là **đoạn mô tả integration**, không phải source file độc lập biên dịch bằng JDK. Cần có `PersonEntity`, cấu hình JPA và dependency Spring Data JPA thực tế. Khi phiên bản/framework hỗ trợ projection tương ứng, record constructor giúp chuyển các giá trị đã chọn thành DTO typed, với `equals`/`hashCode`/`toString` chuẩn.

**Điểm phân biệt quan trọng:**

- **DTO/projection:** record có thể là dạng trả về của phương thức repository hoặc lớp kết quả truy vấn khi framework hỗ trợ.
- **JPA `@Entity`:** theo Jakarta Persistence, **không dùng record làm entity**; record là final và không phù hợp với hợp đồng entity (chẳng hạn no-arg constructor và quản lý trạng thái). Nếu cần entity có vòng đời và state thay đổi, dùng class entity đúng chuẩn, rồi map sang record DTO ở biên ứng dụng.
- Với các truy vấn thủ công `@Query`, native query hoặc trường tên khác, kiểm tra quy tắc constructor expression, alias, mapping và thứ tự/kiểu tham số theo phiên bản Spring Data JPA/JPA provider.

Tài liệu chính thức: [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html) và [Jakarta Persistence — `Entity`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Entity.html).

## 9. Quy trình ghép record + Stream + API một cách an toàn

Một pipeline thường gặp là:

1. **Nhận dữ liệu từ nguồn** (HTTP, database, file hoặc thư viện tích hợp) và chuyển thành record DTO có component rõ ràng.
2. **Kiểm tra/chuẩn hóa đầu vào** trong compact constructor nếu hợp đồng record cần giá trị không null, số hợp lệ hoặc danh sách được sao chép phòng vệ.
3. **Xử lý Stream** để `filter`, `map`, `groupingBy`, `sorted` và tổng hợp; dùng method reference `RecordType::component`, tránh dựa vào setter.
4. **Tạo record kết quả** với tên component phản ánh ý nghĩa nghiệp vụ; dùng constructor reference nếu phù hợp với collector.
5. **Xuất sang API** qua mapper/serializer **có hỗ trợ record**. Kiểm thử chuyển đổi hai chiều, trường hợp thiếu dữ liệu và tên component.
6. **Kiểm chứng tính ổn định của kết quả**: thứ tự, mutability, xử lý trùng khóa, overflow số học và behavior khi chạy song song nếu có.

Ví dụ kiến trúc: `PersonEntity` (JPA entity) → Spring Data projection `NamesOnly` (record) → Stream lọc/biến đổi → response DTO record → Jackson serialization. Ở mỗi ranh giới, cần dùng phiên bản thư viện có hỗ trợ và tuân thủ constructor/component mapping.

### 9.1. Record có bất biến sâu tự động không?

**Không.** Những component là primitive hoặc kiểu bất biến (như `String`) thường tạo record có ngữ nghĩa giá trị ổn định. Nhưng:

```java
record Tags(List<String> values) {}

List<String> mutable = new java.util.ArrayList<>(List.of("java"));
Tags tags = new Tags(mutable);
mutable.add("updated");
System.out.println(tags.values()); // [java, updated]
```

Trường `values` là `private final`, song danh sách được tham chiếu vẫn có thể sửa. Nếu record là DTO cần ổn định:

```java
record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
```

`List.copyOf` làm cấu trúc danh sách không sửa được, và bản danh sách không thay đổi khi collection đầu vào bị sửa sau đó. Đó vẫn là **shallow copy**; nếu phần tử là object mutable thì cần thêm thiết kế ở cấp phần tử.

### 9.2. Side effect, stream dùng một lần và parallel stream

Các function truyền vào `map`/`filter` nên tránh sửa state bên ngoài, để pipeline dễ dự đoán và an toàn hơn khi thay đổi cách thực thi. Stream thường là **single-use**: sau một terminal operation như `toList()` hoặc `collect()`, muốn xử lý lại hãy gọi `sales.stream()` để tạo stream mới.

`parallelStream()` không tự động tăng hiệu năng. Khi chạy song song, tránh ghi vào `ArrayList`/`HashMap` dùng chung từ lambda; chọn collector đúng và đo hiệu năng. `Stream.toList()` vẫn tuân thủ encounter order nếu có, nhưng thứ tự của `Map` do collector/map implementation quyết định. Trong ví dụ chạy được, `TreeMap` giúp kết quả map có thứ tự ổn định để dễ kiểm chứng.

## 10. Lỗi thường gặp

### Lỗi A — Gọi `getProduct()` trên record khi chưa tự khai báo

```java
record Sale(String product) {}
// Sale s = new Sale("Book");
// s.getProduct(); // LỖI: accessor mặc định là product()
```

Dùng `s.product()` hoặc `Sale::product`. Framework dùng cơ chế JavaBeans có thể không tự nhận tên accessor record; cần record support hoặc mapping rõ ràng.

### Lỗi B — Quên merge function trong `Collectors.toMap`

Nhiều Sale có `product="Book"`, nếu `toMap(Sale::product, Sale::total)` gặp khóa trùng sẽ ném `IllegalStateException`. Nếu muốn cộng, thêm `Long::sum`; nếu muốn giữ nhiều bản ghi, dùng `groupingBy`.

### Lỗi C — Cho rằng record luôn sắp xếp tự nhiên

`sales.stream().sorted()` có thể ném `ClassCastException` khi thực thi nếu record không triển khai `Comparable`. Dùng `sorted(Comparator.comparing(Sale::region).thenComparing(Sale::product))` hoặc một thứ tự phù hợp nghiệp vụ.

### Lỗi D — Trông đợi `Stream.toList()` có thể sửa

`list.add(...)` trên kết quả `Stream.toList()` ném `UnsupportedOperationException`. Nếu cần một `ArrayList` có thể sửa, thu bằng `collect(Collectors.toCollection(ArrayList::new))`.

### Lỗi E — Dùng mutable record key trong Map

Record có component như mảng hoặc đối tượng mutable không tự tạo ngữ nghĩa khóa ổn định. Hãy ưu tiên component bất biến, copy phòng vệ, và tự xác định `equals`/`hashCode` khi cần so sánh nội dung đặc biệt (ví dụ mảng).

### Lỗi F — Coi record DTO là `@Entity`

Jakarta Persistence không cho record làm `@Entity`. Giữ entity là class đúng chuẩn, còn record dùng làm DTO/projection nếu thư viện hỗ trợ. Chú ý provider-specific behavior không thay thế hợp đồng portable JPA.

### Lỗi G — Tin rằng mọi JSON framework hỗ trợ record

Java record không tự tạo cơ chế JSON. Thư viện có thể yêu cầu phiên bản phù hợp, constructor mapping và annotation; cần kiểm thử serialize/deserialize trên chính phiên bản được triển khai.

## 11. Bài tập tự kiểm tra

**Câu 1.** `record Key(String group, int id) {}` có phù hợp làm khóa `Map` khi cả hai component không đổi không?

**Đáp án:** Có. Hai record có cùng `group` và `id` được so sánh theo giá trị component, nên `Map.get(new Key("A", 1))` có thể tìm bản ghi đã được chèn với một instance `new Key("A", 1)` khác.

**Câu 2.** Vì sao `sales.stream().map(Sale::total).reduce(0L, Long::sum)` có thể viết rõ hơn bằng `mapToLong(Sale::total).sum()`?

**Đáp án:** Cả hai diễn đạt phép cộng doanh thu; `mapToLong` dùng primitive stream và không yêu cầu boxing `Long` cho từng phần tử. Hãy bảo đảm `total()` trả `long` đúng.

**Câu 3.** `record UserDto(String name) {}` có tự mang method `getName()` để các thư viện JavaBeans đọc được không?

**Đáp án:** Không. Accessor mặc định là `name()`. Chọn thư viện có hỗ trợ record hoặc bổ sung mapping tương thích theo nhu cầu.

**Câu 4.** `Stream.toList()` và `Collectors.toList()` có cùng cam kết mutability không?

**Đáp án:** Không. `Stream.toList()` bảo đảm danh sách không sửa được; `Collectors.toList()` không bảo đảm mutability hay loại list. Cần loại cụ thể thì dùng `toCollection`.

**Câu 5.** Có thể dùng record làm JPA entity hoặc làm Spring Data DTO projection?

**Đáp án:** Record **không** là JPA `@Entity` portable hợp lệ. Spring Data JPA có hỗ trợ record làm **class-based projection DTO**, tùy loại query, mapping, phiên bản và cấu hình.

**Câu 6.** Trong `toMap(Sale::product, Sale::total)`, vì sao hai record Sale khác nhau vẫn có thể gây lỗi khóa trùng?

**Đáp án:** Khóa được chọn chỉ là `product`. Hai Sale khác nhau có thể cùng sản phẩm nên sinh cùng khóa String. Phải thiết kế merge hoặc nhóm danh sách theo yêu cầu nghiệp vụ.

## 12. Checklist triển khai

- [ ] Dùng record cho các giá trị/DTO có component rõ nghĩa; accessor gọi theo `component()`.
- [ ] Dùng `map` để tạo record kết quả mới, không tìm setter để sửa record cũ.
- [ ] Xác định sort/comparator và encounter order khi thứ tự đầu ra quan trọng.
- [ ] Với `toMap` có thể trùng khóa, cung cấp merge function; với composite keys, cân nhắc record có các component bất biến.
- [ ] Chọn loại list/map theo yêu cầu mutability, null và ordering. Không giả định `Collectors.toList()` là `ArrayList`.
- [ ] Dùng `mapToLong` cho tổng doanh thu và kiểm tra kiểu số học tránh overflow.
- [ ] Sao chép phòng vệ với component mutable khi cần giá trị ổn định; record chỉ bất biến nông.
- [ ] Kiểm tra Spring Data/Jackson/framework có record support trên phiên bản thực tế, không giả định setter hay no-arg constructor.
- [ ] Dùng record làm Spring Data DTO/projection khi phù hợp; giữ JPA entity theo yêu cầu JPA.
- [ ] Kiểm thử cả đường JSON/DB → record → Stream → DTO → JSON trong môi trường ứng dụng.

## Tài liệu còn áp dụng

- [Oracle — Java SE 25 Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `map`, `filter`, `sorted`, `toList` và hợp đồng thứ tự/mutability.
- [Oracle — Java SE 25 Collectors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `groupingBy`, `teeing`, `summingLong`, `toMap`.
- [Oracle — Java SE 25 Class API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `isRecord()` và `getRecordComponents()`.
- [Oracle — Java SE 17 Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): record fields/accessors/constructors và ngữ nghĩa record chính thức.
- [FasterXML — Jackson 2.12 Release](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.12): mốc hỗ trợ `java.lang.Record`.
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html): record làm class-based DTO projection.
- [Jakarta Persistence API — Entity](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Entity.html): điều kiện hợp lệ của entity, bao gồm loại trừ record.
