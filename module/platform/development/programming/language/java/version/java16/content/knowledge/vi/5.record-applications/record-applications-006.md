# Dùng method reference tới accessor để sắp xếp và ánh xạ

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record cung cấp accessor có tên trùng với component, ví dụ `title()`, `price()` hoặc `createdAt()`. Trong Java hiện đại, có thể truyền trực tiếp các accessor này làm method reference cho `Comparator` và Stream, giúp biểu đạt việc sắp xếp, trích xuất hoặc chuyển đổi dữ liệu ngắn gọn và an toàn kiểu.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt accessor của record với getter theo quy ước JavaBeans.
- Dùng `RecordType::componentName` làm method reference trong `Comparator.comparing`, `thenComparing` và `Stream.map`.
- Sắp xếp theo nhiều tiêu chí, xử lý thứ tự tăng/giảm và giá trị `null`.
- Chọn comparator chuyên biệt cho dữ liệu số nguyên, số dài và số thực.
- Ánh xạ danh sách record thành danh sách component, record khác hoặc dữ liệu tổng hợp.
- Nhận biết khi method reference không đủ rõ và nên dùng lambda.

## 1. Accessor của record và method reference

Khi khai báo:

```java
public record Product(
        String code,
        String name,
        int price,
        int stock
) {}
```

Java tạo accessor công khai theo tên component: `code()`, `name()`, `price()` và `stock()`. Đây là accessor, không phải getter có tiền tố `get`. Khi gọi trực tiếp, ta viết `product.name()`; khi truyền phương thức đó làm hành vi, ta có thể dùng method reference `Product::name`.

Ví dụ:

```java
List<String> names = products.stream()
        .map(Product::name)
        .toList();
```

`Product::name` tham chiếu tới accessor `name()` của một đối tượng Product. Trong ngữ cảnh `map`, nó tương ứng với một hàm nhận `Product` và trả về `String`, tức `Function<Product, String>`.

### 1.1. Method reference dạng Type::instanceMethod

Cú pháp `Product::name` là method reference tới phương thức instance không gắn với một đối tượng cụ thể. Stream truyền từng phần tử vào phương thức đó:

```java
Function<Product, String> getName = Product::name;

Product product = new Product("P-01", "Keyboard", 750000, 12);
String name = getName.apply(product);

System.out.println(name); // Keyboard
```

Cách viết tương đương bằng lambda:

```java
Function<Product, String> getName = product -> product.name();
```

Khi lambda chỉ gọi một accessor và trả kết quả, method reference thường ngắn gọn và làm rõ ý định.

### 1.2. Method reference dạng instance::method

Nếu đã có một đối tượng cụ thể, có thể tạo bound method reference:

```java
Product product = new Product("P-01", "Keyboard", 750000, 12);

Supplier<String> nameSupplier = product::name;

System.out.println(nameSupplier.get()); // Keyboard
```

| Cú pháp | Ý nghĩa | Kiểu hàm thường gặp |
|---|---|---|
| `Product::name` | Nhận một Product rồi gọi accessor của nó | `Function<Product, String>` |
| `product::name` | Gọi accessor trên Product đã xác định | `Supplier<String>` |

Trong pipeline Stream, phần tử được xử lý thay đổi theo từng lượt, vì vậy `Product::name` thường là dạng phù hợp. `product::name` phù hợp khi muốn lấy giá trị từ một instance cụ thể.

## 2. Dùng accessor làm tiêu chí sắp xếp

`Comparator.comparing` nhận một hàm trích xuất khóa so sánh (*key extractor*). Accessor của record thường đáp ứng trực tiếp yêu cầu này.

Ví dụ sắp xếp sản phẩm theo tên:

```java
List<Product> byName = products.stream()
        .sorted(Comparator.comparing(Product::name))
        .toList();
```

Cách viết tương đương:

```java
List<Product> byName = products.stream()
        .sorted(Comparator.comparing(product -> product.name()))
        .toList();
```

Method reference giúp thấy ngay tiêu chí là component `name`. Comparator được suy luận từ kiểu phần tử của Stream và kiểu giá trị mà accessor trả về.

### 2.1. Sắp xếp theo component số

Với component số nguyên, nên dùng `comparingInt`:

```java
List<Product> byPrice = products.stream()
        .sorted(Comparator.comparingInt(Product::price))
        .toList();
```

Các comparator chuyên biệt:

| Kiểu component | API |
|---|---|
| `int` | `Comparator.comparingInt` |
| `long` | `Comparator.comparingLong` |
| `double` | `Comparator.comparingDouble` |
| Kiểu object như `String`, `BigDecimal`, `LocalDate` | `Comparator.comparing` |

Dùng comparator chuyên biệt giúp tránh boxing không cần thiết khi so sánh giá trị primitive. Với kiểu wrapper như `Integer` hoặc `Long`, `comparing` cũng dùng được; comparator chuyên biệt yêu cầu hàm trích xuất trả primitive tương ứng.

Ví dụ:

```java
public record Employee(
        long id,
        String name,
        int age,
        double rating
) {}
```

```java
employees.stream()
        .sorted(Comparator.comparingInt(Employee::age))
        .toList();

employees.stream()
        .sorted(Comparator.comparingLong(Employee::id))
        .toList();

employees.stream()
        .sorted(Comparator.comparingDouble(Employee::rating))
        .toList();
```

### 2.2. Truyền comparator tùy chỉnh

`Comparator.comparing` có overload nhận comparator cho kiểu component. Ví dụ sắp xếp tên không phân biệt chữ hoa/chữ thường:

```java
List<Product> byNameIgnoreCase = products.stream()
        .sorted(Comparator.comparing(
                Product::name,
                String.CASE_INSENSITIVE_ORDER
        ))
        .toList();
```

Comparator truyền vào quyết định cách so sánh component; accessor chỉ cung cấp giá trị để so sánh. Điều này hữu ích khi quy tắc nghiệp vụ khác thứ tự tự nhiên của kiểu dữ liệu.

## 3. Sắp xếp theo nhiều accessor với thenComparing

Một danh sách thường cần nhiều tiêu chí. Ví dụ sắp xếp sản phẩm theo giá tăng dần, sau đó theo tên:

```java
List<Product> sorted = products.stream()
        .sorted(
                Comparator.comparingInt(Product::price)
                        .thenComparing(Product::name)
        )
        .toList();
```

Thứ tự hoạt động:

1. So sánh `price` trước.
2. Nếu hai sản phẩm có giá bằng nhau, so sánh tiếp `name`.
3. Nếu cả hai tiêu chí đều bằng nhau, comparator xem hai phần tử tương đương về thứ tự.

Có thể nối nhiều tiêu chí:

```java
List<Employee> ranked = employees.stream()
        .sorted(
                Comparator.comparingInt(Employee::age)
                        .thenComparing(Employee::name)
                        .thenComparingLong(Employee::id)
        )
        .toList();
```

Trong ví dụ này, nhân viên được sắp xếp theo tuổi, sau đó tên, cuối cùng ID. Thứ tự tiêu chí rất quan trọng: tiêu chí đầu tiên có quyền quyết định cao nhất.

### 3.1. Sắp xếp giảm dần

Để đảo thứ tự toàn bộ comparator:

```java
List<Product> byPriceDescending = products.stream()
        .sorted(Comparator.comparingInt(Product::price).reversed())
        .toList();
```

Nếu cần giá giảm dần nhưng tên tăng dần, chỉ đảo comparator của tiêu chí giá:

```java
Comparator<Product> comparator =
        Comparator.comparingInt(Product::price)
                .reversed()
                .thenComparing(Product::name);

List<Product> result = products.stream()
        .sorted(comparator)
        .toList();
```

Không đặt `reversed()` ở cuối chuỗi comparator trong trường hợp này, vì nó sẽ đảo cả thứ tự giá lẫn tên. Hãy đảo comparator của đúng tiêu chí cần giảm dần.

### 3.2. Dùng accessor lồng nhau

Giả sử đơn hàng chứa một record khách hàng:

```java
record Customer(String id, String name) {}

record Order(
        String orderCode,
        Customer customer,
        BigDecimal total
) {}
```

Muốn sắp xếp đơn hàng theo tên khách hàng, có thể viết:

```java
orders.stream()
        .sorted(Comparator.comparing(
                order -> order.customer().name()
        ))
        .toList();
```

Không thể viết method reference dạng `Order::customer.name` vì cú pháp method reference chỉ tham chiếu một phương thức hoặc constructor, không nối trực tiếp nhiều accessor. Dùng lambda cho chuỗi truy cập lồng nhau. Nếu logic này được dùng nhiều nơi, có thể định nghĩa comparator có tên hoặc accessor tính toán phù hợp trong kiểu dữ liệu.

## 4. Xử lý component có thể null

`Comparator.comparing(Product::name)` giả định giá trị trả về có thể so sánh theo comparator được dùng. Nếu `name` có thể `null`, comparator tự nhiên có thể ném `NullPointerException`.

Nếu null được phép và cần đặt cuối danh sách:

```java
Comparator<Product> byNameNullLast =
        Comparator.comparing(
                Product::name,
                Comparator.nullsLast(Comparator.naturalOrder())
        );

List<Product> sorted = products.stream()
        .sorted(byNameNullLast)
        .toList();
```

Nếu muốn null đứng đầu:

```java
Comparator<Product> byNameNullFirst =
        Comparator.comparing(
                Product::name,
                Comparator.nullsFirst(Comparator.naturalOrder())
        );
```

Có thể kết hợp với tiêu chí tiếp theo:

```java
Comparator<Product> comparator = Comparator
        .comparing(
                Product::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
        )
        .thenComparingInt(Product::price);
```

Ở đây sản phẩm có tên null được xếp sau những sản phẩm có tên; các sản phẩm cùng tên được so sánh tiếp theo giá.

Với DTO hoặc value object, thường nên quyết định rõ component nào bắt buộc và xác thực trong constructor. Chỉ dùng comparator null-aware khi null thực sự là trạng thái hợp lệ của dữ liệu.

## 5. Dùng accessor với Stream.map để trích xuất dữ liệu

`map` biến mỗi phần tử nguồn thành một giá trị khác. Accessor của record là method reference tự nhiên khi muốn lấy một component.

Lấy danh sách tên:

```java
List<String> names = products.stream()
        .map(Product::name)
        .toList();
```

Lấy danh sách giá:

```java
List<Integer> prices = products.stream()
        .map(Product::price)
        .toList();
```

Với component primitive, `mapToInt` có thể tránh boxing nếu bước tiếp theo xử lý bằng stream số nguyên:

```java
int totalStock = products.stream()
        .mapToInt(Product::stock)
        .sum();
```

Tương tự:

```java
long totalIds = employees.stream()
        .mapToLong(Employee::id)
        .sum();

double averageRating = employees.stream()
        .mapToDouble(Employee::rating)
        .average()
        .orElse(0.0);
```

Chọn `mapToInt`, `mapToLong` hoặc `mapToDouble` khi cần pipeline số học. Nếu cần danh sách wrapper hoặc tiếp tục xử lý như object, `map` vẫn phù hợp.

### 5.1. Ánh xạ sang record khác

Accessor cũng thường được dùng làm đối số cho constructor của record đích:

```java
public record ProductView(String name, int price) {}

List<ProductView> views = products.stream()
        .map(product -> new ProductView(
                product.name(),
                product.price()
        ))
        .toList();
```

Ở đây dùng lambda vì cần kết hợp hai accessor để gọi constructor. Nếu chỉ truyền một component hoặc gọi một hàm có sẵn, method reference có thể ngắn hơn. Constructor nhận nhiều trường thường cần lambda hoặc factory method.

### 5.2. Kết hợp accessor với map và flatMap

Nếu một record chứa danh sách record con, `map` lấy danh sách con, còn `flatMap` trải các danh sách thành một Stream chung.

```java
record OrderLine(String sku, int quantity) {}

record Order(String code, List<OrderLine> lines) {}

List<OrderLine> allLines = orders.stream()
        .flatMap(order -> order.lines().stream())
        .toList();
```

`Order::lines` trả về `List<OrderLine>`, nên không thể truyền trực tiếp nó cho `flatMap` của Stream<Order> vốn cần một `Stream`. Lambda `order -> order.lines().stream()` thực hiện cả hai bước. Nếu muốn dùng method reference, có thể tham chiếu phương thức trả Stream đã định nghĩa trong kiểu:

```java
record Order(String code, List<OrderLine> lines) {
    public Stream<OrderLine> lineStream() {
        return lines.stream();
    }
}

List<OrderLine> allLines = orders.stream()
        .flatMap(Order::lineStream)
        .toList();
```

Chỉ thêm phương thức như `lineStream()` nếu nó có ý nghĩa trong API của kiểu; không cần thêm chỉ để thay một lambda ngắn.

## 6. Ví dụ tổng hợp: sắp xếp và tạo báo cáo sản phẩm

Ví dụ dưới đây dùng accessor của record xuyên suốt: lọc sản phẩm còn hàng, sắp xếp theo tồn kho giảm dần và tên tăng dần, rồi ánh xạ sang record báo cáo.

```java
import java.util.Comparator;
import java.util.List;

public final class ProductReports {
    private ProductReports() {}

    public record Product(
            String code,
            String name,
            int price,
            int stock
    ) {}

    public record ProductReport(
            String code,
            String name,
            int stock
    ) {}

    public static List<ProductReport> availableProducts(List<Product> products) {
        return products.stream()
                .filter(product -> product.stock() > 0)
                .sorted(
                        Comparator.comparingInt(Product::stock)
                                .reversed()
                                .thenComparing(Product::name)
                )
                .map(product -> new ProductReport(
                        product.code(),
                        product.name(),
                        product.stock()
                ))
                .toList();
    }
}
```

Sử dụng:

```java
List<ProductReports.Product> products = List.of(
        new ProductReports.Product("P-01", "Keyboard", 750000, 12),
        new ProductReports.Product("P-02", "Mouse", 250000, 30),
        new ProductReports.Product("P-03", "Monitor", 3200000, 0),
        new ProductReports.Product("P-04", "Headset", 950000, 12)
);

List<ProductReports.ProductReport> report =
        ProductReports.availableProducts(products);

report.forEach(System.out::println);
```

Kết quả theo thứ tự tồn kho giảm dần, tên tăng dần khi tồn kho bằng nhau:

| Mã | Tên | Tồn kho |
|---|---|---:|
| P-02 | Mouse | 30 |
| P-04 | Headset | 12 |
| P-01 | Keyboard | 12 |

`Monitor` bị loại bởi `filter` vì tồn kho bằng không. Hai sản phẩm có tồn kho 12 được sắp xếp tiếp theo tên. Cuối cùng pipeline chuyển `Product` thành `ProductReport`, chỉ giữ những component cần cho báo cáo.

## 7. Comparator và equality của record là hai khái niệm khác nhau

Record sinh `equals()`/`hashCode()` dựa trên tất cả component. Comparator lại có thể chỉ xét một hoặc một số component.

Ví dụ:

```java
Product first = new Product("P-01", "Keyboard", 750000, 12);
Product second = new Product("P-02", "Keyboard", 900000, 20);

System.out.println(first.equals(second)); // false

int comparison = Comparator.comparing(Product::name)
        .compare(first, second);

System.out.println(comparison); // 0
```

Hai sản phẩm khác nhau theo record equality vì mã, giá và tồn kho khác nhau. Nhưng comparator chỉ so sánh tên nên kết quả bằng 0.

Điều này hợp lệ khi mục tiêu chỉ là sắp xếp theo tên. Tuy nhiên, nếu cần thứ tự toàn phần xác định hoặc muốn phân biệt các sản phẩm trùng tên, hãy thêm tiêu chí phụ:

```java
Comparator<Product> byNameThenCode =
        Comparator.comparing(Product::name)
                .thenComparing(Product::code);
```

Không nên giả định comparator trả về 0 có nghĩa hai record bằng nhau. Nó chỉ có nghĩa hai đối tượng tương đương theo những tiêu chí mà comparator đang xét.

### 7.1. Sắp xếp ổn định và thứ tự khi bằng nhau

`Stream.sorted(comparator)` là phép sắp xếp ổn định đối với ordered stream: các phần tử có comparator trả về 0 giữ nguyên thứ tự tương đối ban đầu. Với unordered stream, không có cam kết giữ thứ tự tương đối đó.

Nếu thứ tự hiển thị cần xác định rõ bất kể thứ tự nguồn, hãy thêm tiêu chí phụ duy nhất như mã hoặc ID. Không dựa vào thứ tự ngẫu nhiên của nguồn hoặc thứ tự duyệt của cấu trúc dữ liệu không cam kết thứ tự.

## 8. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Viết `Product::getName` trong khi record chỉ có component `name` | Không có accessor tương ứng nếu không tự khai báo getter | Dùng `Product::name` |
| Dùng `Product::name` như thể là một `String` | Nhầm method reference với kết quả gọi phương thức | Gọi `product.name()` hoặc dùng reference trong ngữ cảnh hàm |
| Dùng `comparing` cho component primitive mà không cần boxing | Có thể tạo boxing không cần thiết | Dùng `comparingInt`, `comparingLong`, `comparingDouble` |
| Gọi `reversed()` ở cuối comparator nhiều tiêu chí | Đảo cả thứ tự tiêu chí phụ | Đảo comparator của đúng tiêu chí cần giảm dần |
| Accessor trả null nhưng dùng natural order | Có thể ném `NullPointerException` | Xác thực dữ liệu hoặc dùng `nullsFirst`/`nullsLast` |
| Cố viết `Order::customer.name` | Cú pháp method reference không hỗ trợ nối accessor | Dùng lambda `order -> order.customer().name()` |
| Nghĩ comparator trả 0 có nghĩa hai record bằng nhau | Nhầm thứ tự sắp xếp với equality | Thêm tiêu chí phụ nếu cần phân biệt |
| Dùng `map` khi component là collection và muốn một Stream phẳng | Kết quả là Stream của collection | Dùng `flatMap` với lambda tạo Stream |

## 9. Checklist sử dụng method reference với accessor

Trước khi viết pipeline, hãy kiểm tra:

1. Accessor có đúng tên component và đúng kiểu trả về không?
2. Method reference có phù hợp chữ ký hàm mà `map`, `comparing` hoặc API đang yêu cầu không?
3. Nên dùng `comparingInt`/`comparingLong`/`comparingDouble` hay `comparing`?
4. Comparator có cần thêm `thenComparing` để phá hòa không?
5. Thứ tự tăng/giảm có được đảo đúng tiêu chí không?
6. Component có thể null không và null cần đứng ở đâu?
7. Nếu truy cập component lồng nhau, lambda có rõ ràng hơn method reference không?
8. Kết quả `Stream.toList()` có phù hợp với yêu cầu danh sách unmodifiable không?

## 10. Bài tập vận dụng

**Bài 1 — Sắp xếp nhân viên:** Tạo record `Employee(id, name, department, age, salary)`. Sắp xếp theo phòng ban, lương giảm dần và tên tăng dần. Dùng accessor method reference cho các tiêu chí đơn.

**Bài 2 — Trích xuất dữ liệu:** Từ danh sách `Product`, dùng `map(Product::name)` tạo danh sách tên và `mapToInt(Product::stock)` tính tổng tồn kho. So sánh hai kiểu pipeline.

**Bài 3 — Xử lý null:** Tạo record có component `nickname` có thể null. Sắp xếp null cuối, sau đó sắp xếp theo ID. Giải thích vai trò của `Comparator.nullsLast`.

**Bài 4 — Ánh xạ DTO:** Tạo `OrderView` từ `Order` bằng cách lấy mã đơn, tên khách hàng và tổng tiền. Dùng lambda khi cần kết hợp nhiều accessor, giải thích vì sao `Order::customer.name` không hợp lệ.

**Bài 5 — Comparator và equality:** Tạo hai record có cùng tên nhưng component khác. Chứng minh comparator chỉ so sánh tên có thể trả 0 dù `equals()` trả false; sau đó thêm tiêu chí phụ để phân biệt.

---

**Ghi nhớ:** Accessor của record có thể được truyền trực tiếp dưới dạng method reference như `Product::name` hoặc `Product::price`. Kết hợp chúng với `Comparator.comparing`, `thenComparing` và `Stream.map` giúp pipeline sắp xếp, trích xuất và chuyển đổi dữ liệu rõ ràng. Hãy chọn comparator phù hợp kiểu component, xử lý null có chủ đích và thêm tiêu chí phụ khi cần thứ tự xác định.
