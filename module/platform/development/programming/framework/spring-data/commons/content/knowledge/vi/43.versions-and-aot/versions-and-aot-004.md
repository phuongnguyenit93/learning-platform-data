# Chuyển API sắp xếp có kiểu khi TypedSort bị thay thế ở phiên bản mới

Trong chương **Phiên bản và AOT** của **SPRING_DATA_COMMONS**, bài này hướng dẫn chuyển cách tạo `Sort` từ `Sort.TypedSort` sang API đường dẫn thuộc tính có kiểu. Mục tiêu là giữ nguyên hành vi của truy vấn repository, phân trang và thứ tự dữ liệu khi nâng cấp Spring Data. Đây là một phần của các abstraction dùng chung: API tạo điều kiện sắp xếp thuộc tầng Commons, còn việc thực thi do module lưu trữ đảm nhiệm.

Sau bài học, bạn có thể đọc thông báo deprecated đúng phiên bản, thay method reference theo API mới, biểu diễn đường dẫn lồng nhau và xác định những hành vi cần kiểm chứng trên JVM hoặc native image.

## 1. Phân biệt deprecated, thay thế và xóa API

Trong Javadoc API 4.1, cả `Sort.TypedSort<T>` và factory `Sort.sort(Class<T>)` đều được đánh dấu deprecated từ **4.1**. Hướng thay thế được chỉ ra là `Sort.by(org.springframework.data.core.TypedPropertyPath...)`. API cũ vẫn xuất hiện trong Javadoc này; không được suy ra rằng nó đã bị xóa ở 4.1 hoặc đã bị deprecated từ 4.0. Xem [Javadoc TypedSort](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.TypedSort.html).

| Trạng thái ở phiên bản đích | Ý nghĩa đối với ứng dụng | Cách xử lý |
| --- | --- | --- |
| API cũ còn được hỗ trợ, API mới chưa tồn tại | Không thể sao chép ví dụ dùng overload mới vào dự án | Giữ API phù hợp hoặc dùng `Sort` theo tên thuộc tính |
| API cũ deprecated, API mới đã có | Cần lập kế hoạch chuyển mã; cảnh báo chưa đồng nghĩa với lỗi biên dịch | Chuyển cách tạo `Sort`, giữ hợp đồng repository |
| API cũ thực sự bị xóa trong một phiên bản đích | Những chỗ còn tham chiếu API cũ không biên dịch được | Loại bỏ các tham chiếu trước khi hoàn tất nâng cấp |

Các ví dụ API mới trong bài yêu cầu **API Spring Data 4.1 có các overload tương ứng hoặc phiên bản tương thích về sau**. Kiểm tra dependency thực tế được BOM quản lý, thay vì đoán từ phiên bản Java hoặc chỉ từ tên phiên bản Spring Boot. Không nâng riêng một thư viện Spring Data chỉ để hết lỗi import mà bỏ qua tính tương thích của cả bộ dependency.

Các liên kết có đoạn `current` có thể chuyển sang phiên bản mới theo thời gian. Khi áp dụng vào dự án, chọn Javadoc tương ứng với dependency đang sử dụng.

## 2. Nhận diện mẫu TypedSort cũ

Giả sử domain có những accessor sau. Đây là khung kiểu Java phục vụ ví dụ sắp xếp; mapping và cách khởi tạo đối tượng phụ thuộc module lưu trữ của ứng dụng.

```java
import java.math.BigDecimal;
import java.time.Instant;

class Product {
    private Long id;
    private String name;
    private BigDecimal price;
    private Instant updatedAt;
    private Address address;

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Address getAddress() { return address; }
}

class Address {
    private String city;

    public String getCity() { return city; }
}
```

Một đoạn mã dùng API cũ có dạng:

```java
import org.springframework.data.domain.Sort;

Sort.TypedSort<Product> product = Sort.sort(Product.class);

Sort oldSort = product.by(Product::getName).ascending()
    .and(product.by(Product::getPrice).descending())
    .and(product.by(Product::getId).ascending());
```

Yêu cầu nghiệp vụ ở đây là `name ASC`, sau đó `price DESC`, cuối cùng `id ASC`. Chỉ khi tên bằng nhau mới xét giá; chỉ khi cả tên và giá bằng nhau mới xét ID.

`TypedSort` cũ ghi nhận truy cập thuộc tính thông qua runtime proxy, thường dùng CGLIB. Cơ chế đó có thể gây trở ngại khi biên dịch GraalVM Native Image. Đây là lý do cần xem xét cơ chế tạo biểu thức, dù kết quả cuối cùng vẫn là một `Sort`. Xem phần [Paging and Sorting trong tài liệu repository](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.paging-and-sorting).

Không coi đoạn `Product::getPrice` trong biểu thức sắp xếp là thao tác lấy toàn bộ sản phẩm rồi tính giá trong Java. Nó mô tả thuộc tính mà tầng lưu trữ cần dùng khi tạo truy vấn.

## 3. Chuyển trực tiếp sang Sort.by với method reference

Với API mới, có thể bỏ biến `Sort.TypedSort<Product>`:

```java
import org.springframework.data.domain.Sort;

Sort migratedSort = Sort.by(Product::getName).ascending()
    .and(Sort.by(Product::getPrice).descending())
    .and(Sort.by(Product::getId).ascending());
```

Các overload nhận `TypedPropertyPath` được bổ sung từ 4.1. Với method reference trực tiếp, Java suy luận kiểu đích của tham số; kiểu trả về của factory vẫn là `Sort`. Xem các chữ ký `by(TypedPropertyPath...)` trong [Javadoc Sort](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html).

Nếu nhiều thuộc tính dùng chung một chiều, có thể viết:

```java
Sort newestFirst = Sort.by(
    Sort.Direction.DESC,
    Product::getUpdatedAt,
    Product::getId
);
```

Ví dụ này yêu cầu `updatedAt DESC, id DESC`. Nó khác với trường hợp cần `updatedAt DESC, id ASC`:

```java
Sort newestWithAscendingId = Sort.by(Product::getUpdatedAt).descending()
    .and(Sort.by(Product::getId).ascending());
```

Trước khi sửa, hãy ghi lại danh sách tiêu chí theo đúng thứ tự ưu tiên. Ví dụ, biểu thức ban đầu tương ứng với bộ ba:

```text
(name, ASC)
(price, DESC)
(id, ASC)
```

Bộ ba này là hợp đồng hành vi dùng để đối chiếu sau chuyển đổi. Việc mã mới hết cảnh báo deprecated chỉ xác nhận được một phần công việc.

## 4. Tách đường dẫn có kiểu để tái sử dụng

Khi cần tái sử dụng thuộc tính ở nhiều biểu thức, khai báo một `TypedPropertyPath<T, P>` rõ ràng:

```java
import java.math.BigDecimal;
import org.springframework.data.core.PropertyPath;
import org.springframework.data.core.TypedPropertyPath;
import org.springframework.data.domain.Sort;

TypedPropertyPath<Product, String> name =
    PropertyPath.of(Product::getName);

TypedPropertyPath<Product, BigDecimal> price =
    PropertyPath.of(Product::getPrice);

Sort sort = Sort.by(name).ascending()
    .and(Sort.by(price).descending())
    .and(Sort.by(Product::getId).ascending());
```

`T` biểu diễn kiểu gốc, `P` biểu diễn kiểu giá trị thuộc tính. Factory `PropertyPath.of(...)` tạo đường dẫn có kiểu từ accessor. Chú ý import **`org.springframework.data.core.PropertyPath`** trong ví dụ, thay vì chọn một lớp cùng tên ở package khác theo gợi ý tự động của IDE. Xem [Javadoc PropertyPath](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/core/PropertyPath.html).

Với thuộc tính lồng nhau:

```java
TypedPropertyPath<Product, String> city =
    PropertyPath.of(Product::getAddress)
        .then(Address::getCity);

Sort byCity = Sort.by(city).ascending()
    .and(Sort.by(Product::getId).ascending());

String propertyName = city.toDotPath(); // address.city
```

Hãy nối từng accessor để mô tả đường đi. Không thay bằng một biểu thức có logic như `p -> p.getAddress().getCity().toUpperCase()` rồi kỳ vọng nó trở thành hàm sắp xếp của cơ sở dữ liệu.

API khuyến nghị method reference trực tiếp đến accessor. Constructor reference, phương thức có tham số và biểu thức phức tạp không phải những cách mô tả thuộc tính hợp lệ; lambda có thể đòi hỏi phân tích bytecode ở nơi khai báo. Xem giới hạn của [TypedPropertyPath](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/core/TypedPropertyPath.html).

An toàn kiểu giúp phát hiện accessor bị đổi tên hoặc nối sai kiểu trong Java. Nó không chứng minh rằng thuộc tính đó được lưu, được phép sắp xếp trong truy vấn hiện tại, hay được module lưu trữ hỗ trợ. Với `address.city`, cần kiểm tra riêng khả năng truy vấn cấu trúc lồng nhau của store đang dùng.

## 5. Giữ chiều, ignoreCase và null handling

Có thể dùng overload có kiểu của `Sort.Order` để diễn đạt từng tiêu chí riêng:

```java
import org.springframework.data.domain.Sort;

Sort detailedSort = Sort.by(
    Sort.Order.asc(Product::getName).ignoreCase().nullsLast(),
    Sort.Order.desc(Product::getPrice),
    Sort.Order.asc(Product::getId)
);
```

Trong ví dụ này, bỏ qua hoa thường và gợi ý đặt `null` cuối chỉ áp dụng cho tiêu chí `name`. `nullsLast()` là một **gợi ý**; store có thể không thực hiện được. Kiểm tra hành vi collation và null ordering của hệ quản trị thực tế khi chúng ảnh hưởng kết quả. Xem [Javadoc Sort.Order](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.Order.html).

Hai lỗi chuyển đổi thường gặp:

```java
// Kết quả của and(...) không được giữ lại.
Sort incomplete = Sort.by(Product::getName);
incomplete.and(Sort.by(Product::getPrice).descending());
```

Cách viết giữ lại biểu thức mới:

```java
Sort complete = Sort.by(Product::getName)
    .and(Sort.by(Product::getPrice).descending());
```

Lỗi thứ hai là gọi đổi chiều sau khi đã ghép nhiều tiêu chí:

```java
Sort changedDirections = Sort.by(Product::getName).ascending()
    .and(Sort.by(Product::getPrice).descending())
    .ascending();
```

Lệnh `ascending()` cuối áp dụng cho toàn bộ các tiêu chí đang có. Nếu cần giữ `price DESC`, hãy đặt chiều cho từng thành phần hoặc dùng `Sort.Order` như ví dụ trên.

## 6. Đưa Sort mới vào repository và Pageable

Repository vẫn nhận abstraction quen thuộc:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

interface ProductRepository extends Repository<Product, Long> {
    Page<Product> findByNameContaining(String text, Pageable pageable);
}
```

Mã gọi tạo `PageRequest` cùng `Sort` mới:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(Product::getName).ascending()
    .and(Sort.by(Product::getPrice).descending())
    .and(Sort.by(Product::getId).ascending());

Pageable pageable = PageRequest.of(0, 20, sort);
// Trong service đã có ProductRepository:
// Page<Product> result = repository.findByNameContaining("An", pageable);
```

Chỉ số trang bắt đầu từ `0`, kích thước trang phải lớn hơn `0`, và `Sort` truyền vào không được `null`. Xem [Javadoc PageRequest](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html).

Trong thiết kế ví dụ, `id` là khóa duy nhất và có giá trị. Thêm nó ở cuối giúp xác định thứ tự giữa các bản ghi trùng tên và giá. Điều này đặc biệt hữu ích khi điểm chia trang rơi vào nhóm giá trị bằng nhau.

Nếu `updatedAt` là thuộc tính auditing, nhiều bản ghi có thể cùng thời điểm cập nhật; dùng thêm khóa duy nhất vẫn có ý nghĩa. Tuy vậy, thứ tự xác định trên một tập dữ liệu cố định không tạo ra snapshot xuyên suốt nhiều lần đọc trang. Khi dữ liệu được thêm, xóa hoặc cập nhật giữa các request, offset pagination vẫn có thể dịch chuyển kết quả.

Nếu truy vấn trả về projection, hãy xác định thuộc tính sắp xếp theo hợp đồng truy vấn và domain gốc. Không tự thay `Product::getName` bằng accessor của DTO chỉ vì DTO có một trường cùng tên; khả năng ánh xạ tên hoặc alias cần được kiểm chứng ở truy vấn cụ thể.

## 7. Chuyển tham số từ client qua danh sách cho phép

Trong ví dụ thiết kế API sau, client chỉ được chọn `name`, `price` hoặc `updatedAt`. Mã server ánh xạ lựa chọn đó thành accessor của domain:

```java
import java.util.Objects;
import org.springframework.data.domain.Sort;

final class ProductSorts {
    private ProductSorts() {}

    static Sort fromClient(String field, Sort.Direction direction) {
        Objects.requireNonNull(field, "field");
        Objects.requireNonNull(direction, "direction");

        Sort primary = switch (field) {
            case "name" -> Sort.by(direction, Product::getName);
            case "price" -> Sort.by(direction, Product::getPrice);
            case "updatedAt" -> Sort.by(direction, Product::getUpdatedAt);
            default -> throw new IllegalArgumentException(
                "Thuộc tính sắp xếp không được hỗ trợ: " + field
            );
        };

        return primary.and(Sort.by(Product::getId).ascending());
    }
}
```

Ví dụ này cố ý giữ `id ASC` cho mọi lựa chọn; đó là quyết định hợp đồng cần thống nhất với phía sử dụng API. Đầu vào thiếu hoặc không hợp lệ cần được tầng web xử lý theo quy ước lỗi của ứng dụng.

Chuỗi `"price"` ở đây là khóa giao tiếp công khai. Nếu domain đổi `getPrice()` thành accessor khác, server có thể cập nhật ánh xạ mà vẫn giữ khóa API đã công bố. Việc dùng API có kiểu trong nội bộ không tự thay thế bước kiểm soát những trường mà client được phép yêu cầu.

## 8. Khi chưa thể sử dụng overload mới

Nếu phiên bản đích chưa cung cấp `TypedPropertyPath`, một phương án chuyển tiếp là biểu thức `Sort.Order` theo tên thuộc tính:

```java
Sort compatibleSort = Sort.by(
    Sort.Order.asc("name"),
    Sort.Order.desc("price"),
    Sort.Order.asc("id")
);
```

Đây là cách mô tả thuộc tính bằng chuỗi. Java không kiểm tra lỗi gõ `"pirce"` hoặc tự bảo đảm chuỗi sẽ được đổi khi refactor accessor. Với lựa chọn này, tập trung tên thuộc tính và kiểm tra các truy vấn sử dụng chúng.

Nếu ứng dụng đã có Querydsl và store hỗ trợ, metamodel Querydsl là một lựa chọn khác cho biểu thức có kiểu. Việc đưa thêm metamodel, annotation processing và dependency vào dự án là thay đổi phạm vi lớn hơn một phép thay `TypedSort`; hãy đánh giá nhu cầu truy vấn trước khi chọn hướng đó.

Không biến thuộc tính domain thành tên cột chỉ vì biểu thức cuối cùng được thực thi bằng SQL. Ví dụ, accessor `getUpdatedAt()` tương ứng với thuộc tính `updatedAt`; tên vật lý như `updated_at` thuộc trách nhiệm mapping hoặc hợp đồng riêng của native query.

## 9. Liên hệ với AOT và native image

Đường dẫn có kiểu mới chuyển cách mô tả thuộc tính khỏi cơ chế ghi nhận truy cập bằng proxy của `TypedSort`. API cũ dùng `MethodInvocationRecorder` cũng được deprecated từ 4.1, với hướng thay thế là hạ tầng `PropertyReference` và `TypedPropertyPath`; Javadoc nêu giới hạn của subclass proxy. Xem [Javadoc các utility Spring Data](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/util/package-summary.html).

Bản phát hành Commons 4.1.0 có thay đổi liên quan đến `TypedPropertyPathFeature` và lambda reachability metadata. Điều đó cho thấy đường dẫn có kiểu có phần tích hợp native riêng, thay vì cho phép kết luận rằng mọi nhu cầu metadata đều biến mất. Xem [ghi chú phát hành Spring Data Commons](https://github.com/spring-projects/spring-data-commons/releases).

Khi dự án có mục tiêu native, kế hoạch xác minh nên đi qua chính đường xử lý tạo `Sort` và thực thi truy vấn. Khởi động được ứng dụng chưa chứng minh rằng nhánh sắp xếp ít sử dụng sẽ hoạt động. Kết quả chạy JVM cũng chưa đủ để kết luận về native image.

Phân biệt rõ ba lớp trách nhiệm khi tìm lỗi: tạo property path, ánh xạ truy vấn của store và cấu hình native của ứng dụng. Không nên thêm hàng loạt reflection hint chỉ từ một cảnh báo deprecated mà chưa xác định lỗi xảy ra ở lớp nào.

## 10. Thiết kế kiểm chứng hành vi sau chuyển đổi

Đây là các tình huống để áp dụng trong dự án khi thực hiện migration; các đoạn minh họa trong bài không phải kết quả chạy kiểm thử.

Với yêu cầu `name ASC, price DESC, id ASC`, chuẩn bị dữ liệu có chủ ý tạo giá trị trùng:

| id | name | price |
| --- | --- | --- |
| 11 | An | 100 |
| 12 | An | 200 |
| 13 | Binh | 80 |
| 14 | An | 200 |
| 15 | Binh | 80 |

Với quy tắc so sánh tên của ví dụ đặt `An` trước `Binh`, thứ tự ID mong đợi là **12, 14, 11, 13, 15**. Nếu lấy từng trang hai phần tử trên tập dữ liệu cố định, các trang tương ứng là `[12, 14]`, `[11, 13]`, `[15]`.

Bộ dữ liệu này phát hiện được việc đảo chiều giá, thiếu tiêu chí ID hoặc thay đổi thứ tự ưu tiên. Nếu mọi tên và giá đều khác nhau, một lỗi thiếu thứ tự phụ có thể không lộ ra.

| Tầng kiểm chứng | Nội dung cần quan sát |
| --- | --- |
| Biểu thức `Sort` | Đúng property path, thứ tự tiêu chí, chiều và các cờ từng `Order` |
| Truy vấn repository | ID trả về đúng thứ tự trên store thực tế |
| Phân trang | Ranh giới trang đúng với dữ liệu trùng giá trị |
| Đường dẫn lồng nhau | Thuộc tính được store ánh xạ và sắp xếp đúng |
| Giá trị đặc biệt | `null`, hoa thường, collation và quy tắc công khai của API |
| Native image nếu có | Nhánh tạo đường dẫn và gọi repository chạy được trong executable |

Khi đối chiếu hai biểu thức, có thể so sánh danh sách `Sort.Order` thay vì chỉ nhìn chuỗi hiển thị. Với đường dẫn lồng nhau, quan sát `toDotPath()` giúp nhận ra việc vô tình đổi `address.city` thành một thuộc tính phẳng.

## 11. Chẩn đoán nhanh khi migration gặp lỗi

| Dấu hiệu | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không import được `TypedPropertyPath` | Dependency thực tế chưa có API mới | Đối chiếu phiên bản đã resolve và BOM |
| Không tìm thấy overload nhận method reference | Phiên bản hoặc import không khớp ví dụ | Xem Javadoc đúng phiên bản trước khi sửa cú pháp |
| Tham chiếu accessor không biên dịch | Accessor đã đổi tên hoặc sai kiểu domain | Sửa method reference theo mô hình hiện tại |
| Property path tạo được nhưng truy vấn thất bại | Thuộc tính không được lưu hoặc store không hỗ trợ đường dẫn | Kiểm tra mapping và hợp đồng truy vấn |
| Mọi tiêu chí bất ngờ thành tăng dần | Có lệnh `ascending()` sau khi ghép | Đặt chiều cho từng thành phần |
| Thứ tự giữa các bản ghi cùng giá thay đổi | Thiếu khóa duy nhất ở cuối | Bổ sung thứ tự phụ theo hợp đồng API |
| JVM chạy được, native thất bại | Nhánh xử lý hoặc metadata native chưa được xác minh | Tái hiện trên executable với cùng đầu vào |

Khi kết thúc chuyển đổi, phần tạo biểu thức sử dụng API phù hợp phiên bản đích, còn người gọi repository vẫn làm việc với `Sort` hoặc `Pageable`. Tiêu chí chấp nhận quan trọng là truy vấn duy trì đúng hợp đồng sắp xếp và phân trang trên môi trường ứng dụng sử dụng.
