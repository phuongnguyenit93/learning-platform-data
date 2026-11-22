# Chọn record cho kết quả truy vấn, tham số và dữ liệu trung gian

## 1. Quy tắc lựa chọn: record mô tả dữ liệu có cấu trúc ổn định

Trong Java hiện đại, `record` phù hợp khi cần một **giá trị dữ liệu có tên và kiểu rõ ràng**, thường được tạo một lần rồi chuyển qua các lớp hoặc các bước xử lý. Ba trường hợp thường gặp là:

1. **Kết quả truy vấn**: đóng gói chính xác những cột/trường mà màn hình, API hoặc nghiệp vụ cần.
2. **Tham số truy vấn/thao tác**: nhóm những điều kiện thường đi cùng nhau vào một đối tượng, có thể kiểm tra tính hợp lệ lúc tạo.
3. **Dữ liệu trung gian**: lưu những giá trị tạm thời (ví dụ một bản ghi đã tính điểm, một cặp khóa và tổng, một kết quả parse) trong pipeline xử lý để tránh `Object[]` hoặc nhiều danh sách song song.

Record đã là tính năng chính thức từ **Java 16** và dùng trực tiếp trên **Java 17+**, không cần `--enable-preview`. Trong bài này, ví dụ chạy bằng Java 17 trở lên và tập trung vào các cách dùng còn áp dụng trong Java hiện nay.

Một record:

~~~java
record ProductView(long id, String title, java.math.BigDecimal price) {}
~~~

tự có constructor nhận `id`, `title`, `price`; các trường thành phần là `private final`; có accessor `id()`, `title()`, `price()`; và có `equals()`, `hashCode()`, `toString()` được tạo dựa trên các thành phần. Không có setter được tự sinh.

**Mấu chốt:** record thể hiện một *data carrier có cấu trúc cố định*, với ngữ nghĩa **bất biến nông** (shallowly immutable), không mặc nhiên bất biến sâu. Nó **không thay thế** mọi class, entity hoặc đối tượng nghiệp vụ có vòng đời/phát sinh trạng thái.

## 2. Bảng quyết định theo vai trò dữ liệu

| Vai trò | Record phù hợp khi | Nên cân nhắc loại khác khi |
| --- | --- | --- |
| Kết quả truy vấn / projection DTO | Chỉ cần một tập trường cụ thể, dữ liệu đọc, ánh xạ rõ; không cần quản lý trạng thái thực thể | Đối tượng phải được ORM theo dõi, cập nhật, lazy-load hoặc có identity/lifecycle riêng |
| Tham số truy vấn / command | Một nhóm điều kiện đi cùng nhau, hợp đồng rõ, có thể xác thực khi tạo, phần lớn được đọc sau đó | Cần builder thay đổi nhiều lần, tập tham số cực kỳ động, hoặc đối tượng có hành vi và trạng thái dài hạn |
| Dữ liệu trung gian | Cần gói các trường tạm của một bước tính toán, sắp xếp, nhóm hoặc chuyển đổi; thời gian sống ngắn | Cần sửa từng trường trong vòng lặp, cấu trúc tạm chỉ có một giá trị, hoặc giá trị không đáng tạo kiểu riêng |

Tên record nên nói rõ **ý nghĩa**: `ProductSummary`, `SearchFilter`, `ScoredCandidate` tốt hơn tên mơ hồ như `Data` hoặc `Result1`. Mỗi record nên diễn tả **một hợp đồng dữ liệu thống nhất**; đừng gom mọi tham số không liên quan chỉ để giảm số lượng tham số phương thức.

## 3. Record cho kết quả truy vấn: lấy đúng dữ liệu cần dùng

Ví dụ bảng sản phẩm có nhiều cột: ID, tên, giá, lượng tồn kho, nhà cung cấp, thời điểm cập nhật, dữ liệu nội bộ. Trang danh sách chỉ cần **ID, tên, giá**.

Thay vì trả về nguyên bản entity/tất cả cột, tạo projection:

~~~java
import java.math.BigDecimal;

public record ProductSummary(long id, String title, BigDecimal price) {}
~~~

Đây là ví dụ **độc lập về khai báo kiểu**, lưu thành `ProductSummary.java` nếu biên dịch riêng. Mỗi kết quả có cấu trúc rõ:

~~~java
ProductSummary item = new ProductSummary(
    101L, "Java Fundamentals", new BigDecimal("39.00")
);
System.out.println(item.title()); // Java Fundamentals
~~~

Lợi ích:

- **Chọn đúng dữ liệu**: projection phân biệt dữ liệu để hiển thị/xử lý với mô hình lưu trữ. Các trường nhạy cảm hoặc thừa không tự động lọt vào payload.
- **Giao diện sử dụng minh bạch**: `item.price()` có kiểu `BigDecimal`; tránh `Object[]` phải nhớ phần tử số 0/1/2 và ép kiểu tại runtime.
- **Hợp đồng có kiểm tra biên dịch**: gọi constructor thiếu trường hoặc sai kiểu được phát hiện sớm.
- **Giá trị dễ so sánh và kiểm thử**: `equals/hashCode` dựa trên các thành phần; phù hợp với snapshot kết quả đọc nếu các thành phần cũng có ngữ nghĩa so sánh mong muốn.

**Không đánh đồng projection DTO với persistence entity.** Trong JPA chuẩn, entity thường cần constructor không tham số phù hợp, không phải lớp `final` và mang vòng đời được persistence context quản lý; record mặc định là `final` và có canonical constructor theo các components. Hãy sử dụng record làm **kiểu kết quả** của truy vấn, không mặc định chuyển entity JPA thành record. Việc ánh xạ từ entity sang DTO có thể bằng constructor, mapper, JDBC hoặc cơ chế projection của framework.

Nếu kết quả cần khác nhau tùy giao diện (ví dụ danh sách chỉ có 3 trường, trang chi tiết có thêm 8 trường), thường nên tạo **hai record có mục đích riêng** thay vì một record khổng lồ với nhiều trường không dùng hoặc thường `null`.

## 4. Record cho tham số: gom điều kiện và kiểm tra hợp đồng

Một thao tác tìm kiếm có thể nhận `keyword`, `minPrice` và `limit`. Nhiều tham số rời dễ bị truyền sai thứ tự (nhất là các tham số cùng kiểu) và khó mở rộng.

Record cho phép gói chúng:

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;

record ProductFilter(String keyword, BigDecimal minPrice, int limit) {
    ProductFilter {
        keyword = Objects.requireNonNull(keyword, "keyword")
                .strip()
                .toLowerCase(Locale.ROOT);
        minPrice = Objects.requireNonNull(minPrice, "minPrice");

        if (keyword.isBlank()) {
            throw new IllegalArgumentException("keyword must not be blank");
        }
        if (minPrice.signum() < 0) {
            throw new IllegalArgumentException("minPrice must be >= 0");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be between 1 and 100");
        }
    }
}
~~~

Đây là **compact canonical constructor**. Khi constructor kết thúc, Java tự gán các tham số đã chuẩn hóa cho các thành phần cùng tên. Việc gán lại biến tham số `keyword` trong compact constructor là hợp lệ; không cần và không được gán trực tiếp `this.keyword = ...` trong dạng constructor này.

Điều kiện được kiểm tra **ngay khi tạo**:

~~~java
var filter = new ProductFilter(" JAVA ", new BigDecimal("30.00"), 3);
System.out.println(filter.keyword()); // java
~~~

Dù constructor đã xác thực, lớp truy cập dữ liệu vẫn phải kiểm soát **quyền truy cập, tham số SQL, chi phí truy vấn và phân trang**. Record không tự chống SQL injection; điều đó đòi hỏi dùng truy vấn tham số hóa và không ghép trực tiếp dữ liệu không tin cậy vào cú pháp SQL. Phạm vi `limit` cần giới hạn theo chính sách của ứng dụng.

Nên dùng `BigDecimal` cho tiền tệ khi cần số thập phân chính xác, tránh `double` cho giá trị tiền. Nếu ứng dụng cần mã tiền tệ, hãy mô hình hóa nó bằng thành phần thích hợp; `BigDecimal` một mình không tự mang đơn vị tiền.

Với API công khai, cân nhắc riêng khả năng tương thích: thêm một thành phần vào record làm thay đổi canonical constructor, các accessor, `equals/hashCode` và hình dạng dữ liệu công bố. Không nên thêm trường chỉ để tiện một lời gọi đặc biệt; hãy dùng một kiểu yêu cầu khác khi ý nghĩa thực sự khác nhau.

## 5. Record cho dữ liệu trung gian: mang thông tin qua một pipeline

Giả sử kết quả tìm kiếm cần ưu tiên hàng còn tồn trước khi trả về. Để sắp xếp, cần tạm thời giữ:

- Dữ liệu cuối cùng của sản phẩm.
- Một dấu hiệu `inStock` để sắp xếp.

Record trung gian:

~~~java
record Candidate(ProductSummary view, boolean inStock) {}
~~~

cho phép viết `candidate.view()` và `candidate.inStock()` thay vì dùng mảng `Object[]` với hai vị trí không có tên. Khi pipeline kết thúc, chỉ lấy `ProductSummary` để trả cho caller.

Điều này giúp tách **dữ liệu phục vụ tính toán nội bộ** khỏi **dữ liệu cuối cùng cần xuất ra**. Ví dụ `inStock` là chi tiết xếp hạng ở tầng tìm kiếm; nó không nhất thiết phải là trường của DTO trả về.

Một intermediate record tốt nên ngắn, có tên rõ và thường được khai báo ở phạm vi hẹp nhất còn dễ tái sử dụng: `private record` bên trong class, hoặc **local record** bên trong phương thức khi chỉ một bước xử lý dùng nó. Tránh xuất bản record trung gian thành kiểu API chỉ vì tiện.

## 6. Ví dụ đầy đủ trên Java 17+: tham số → trung gian → kết quả truy vấn

Ví dụ chạy được mà **không cần cơ sở dữ liệu**. Danh sách `CatalogItem` mô phỏng dữ liệu nguồn, rồi pipeline lọc theo điều kiện, chấm mức ưu tiên, sắp xếp, giới hạn số lượng và trả về DTO.

Tạo tệp **`RecordQueryDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class RecordQueryDemo {

    // Dữ liệu mô phỏng từ kho lưu trữ; chỉ dùng cho ví dụ tại chỗ.
    record CatalogItem(long id, String title, BigDecimal price, int stock) {}

    // DTO được trả về; không tiết lộ stock.
    record ProductView(long id, String title, BigDecimal price) {}

    // Đầu vào có bất biến về mặt điều kiện truy vấn.
    record ProductFilter(String keyword, BigDecimal minPrice, int limit) {
        ProductFilter {
            keyword = Objects.requireNonNull(keyword, "keyword")
                    .strip()
                    .toLowerCase(Locale.ROOT);
            minPrice = Objects.requireNonNull(minPrice, "minPrice");

            if (keyword.isBlank()) {
                throw new IllegalArgumentException("keyword must not be blank");
            }
            if (minPrice.signum() < 0) {
                throw new IllegalArgumentException("minPrice must be >= 0");
            }
            if (limit < 1 || limit > 100) {
                throw new IllegalArgumentException(
                    "limit must be between 1 and 100"
                );
            }
        }
    }

    // Chỉ phục vụ việc sắp xếp trong pipeline.
    private record Candidate(ProductView view, boolean inStock) {}

    static List<ProductView> search(
            List<CatalogItem> catalog, ProductFilter filter) {

        Objects.requireNonNull(catalog, "catalog");
        Objects.requireNonNull(filter, "filter");

        return catalog.stream()
                .filter(item -> item.title()
                        .toLowerCase(Locale.ROOT)
                        .contains(filter.keyword()))
                .filter(item -> item.price()
                        .compareTo(filter.minPrice()) >= 0)
                .map(item -> new Candidate(
                        new ProductView(
                            item.id(), item.title(), item.price()
                        ),
                        item.stock() > 0
                ))
                .sorted(
                    Comparator.comparing(Candidate::inStock)
                        .reversed()
                        .thenComparing(candidate -> candidate.view().title())
                )
                .limit(filter.limit())
                .map(Candidate::view)
                .toList();
    }

    public static void main(String[] args) {
        List<CatalogItem> catalog = List.of(
            new CatalogItem(101, "Java Fundamentals",
                    new BigDecimal("39.00"), 5),
            new CatalogItem(102, "Java Practice",
                    new BigDecimal("45.00"), 0),
            new CatalogItem(103, "Spring Boot Guide",
                    new BigDecimal("60.00"), 7),
            new CatalogItem(104, "Java Reference",
                    new BigDecimal("29.00"), 10),
            new CatalogItem(105, "Effective Java",
                    new BigDecimal("50.00"), 2)
        );

        ProductFilter filter = new ProductFilter(
            " JAVA ", new BigDecimal("30.00"), 3
        );

        System.out.println("Filter: " + filter);

        search(catalog, filter).forEach(view ->
            System.out.println(
                view.id() + " | " + view.title()
                    + " | " + view.price()
            )
        );
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RecordQueryDemo.java
java RecordQueryDemo
~~~

**Đầu ra chính xác:**

~~~text
Filter: ProductFilter[keyword=java, minPrice=30.00, limit=3]
105 | Effective Java | 50.00
101 | Java Fundamentals | 39.00
102 | Java Practice | 45.00
~~~

**Giải thích từng bước:**

1. `new ProductFilter(" JAVA ", ...)` chuẩn hóa thành `keyword=java`, kiểm tra giá tối thiểu và `limit`.
2. Stream chỉ giữ sản phẩm có tên chứa `java`, không phân biệt chữ hoa/thường, và giá từ `30.00` trở lên. `Spring Boot Guide` bị loại vì không chứa từ khóa; `Java Reference` bị loại vì giá `29.00`.
3. `map` biến mỗi mục thành `Candidate(ProductView, inStock)`. Phần `ProductView` chứa đúng dữ liệu trả về; `inStock` chỉ phục vụ sắp xếp.
4. Comparator ưu tiên `inStock=true`, sau đó tên sản phẩm theo thứ tự chữ cái. Vì vậy `Effective Java` đứng trước `Java Fundamentals`; `Java Practice` hết hàng đứng cuối.
5. `limit(3)` lấy tối đa ba kết quả; `map(Candidate::view)` bỏ metadata trung gian, trả `List<ProductView>`. `Stream.toList()` hiện hành (Java 16+) trả danh sách không thể sửa qua các phương thức thay đổi cấu trúc như `add`.

Trong code này cả `CatalogItem` cũng là record để làm fixture gọn. **Điều đó không hàm ý entity JPA nên được khai báo thành record.** Dữ liệu thực có thể đến từ entity, bảng SQL, dịch vụ ngoài hoặc cache; mục đích bài tập là cho thấy **ba vai trò record khác nhau** trong một luồng dữ liệu.

Nếu thứ tự kết quả từ DB phải nhất quán qua nhiều trang, cần thêm thứ tự tie-breaker ổn định (thường là ID) ở tầng truy vấn. Ví dụ trên chỉ xử lý dữ liệu trong bộ nhớ; không được suy ra rằng `Stream.limit` sẽ làm DB tự động trả ít dòng.

## 7. Ánh xạ truy vấn SQL/JDBC sang record

Với JDBC, record không tự đọc các cột từ `ResultSet`. Chương trình phải ánh xạ **tường minh**, đúng tên cột và kiểu dữ liệu. Ví dụ phương thức sau dùng schema giả định có bảng `products(id, title, price)`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

static List<ProductSummary> findProducts(
        Connection connection,
        ProductFilter filter) throws SQLException {

    String sql = """
        SELECT id, title, price
        FROM products
        WHERE LOWER(title) LIKE ? AND price >= ?
        ORDER BY title, id
        """;

    List<ProductSummary> results = new ArrayList<>();

    try (PreparedStatement statement =
            connection.prepareStatement(sql)) {

        statement.setString(1, "%" + filter.keyword() + "%");
        statement.setBigDecimal(2, filter.minPrice());
        statement.setMaxRows(filter.limit());

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                results.add(new ProductSummary(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")
                ));
            }
        }
    }
    return List.copyOf(results);
}
~~~

**Phạm vi:** đây là **mảnh mã tích hợp**, không phải chương trình chạy độc lập. Nó cần nằm trong class có `ProductSummary`/`ProductFilter` và có cơ sở dữ liệu, bảng, kết nối JDBC/driver tương ứng. Ví dụ độc lập có thể chạy ngay nằm ở mục 6.

Điểm thực hành:

- **Select đúng cột**: tránh `SELECT *` khi projection chỉ cần ba trường; chọn ít cột thường làm hợp đồng rõ hơn và có thể giảm dữ liệu truyền.
- **Dùng `PreparedStatement`** cho giá trị người dùng; không nối `keyword` trực tiếp vào chuỗi SQL. Dấu `%` và `_` vẫn có nghĩa wildcard trong `LIKE`; nếu tìm chuỗi đúng nghĩa đen, cần escape ký tự wildcard theo hệ quản trị CSDL.
- **`setMaxRows` không tương đương tối ưu truy vấn phân trang ở DB**. Trong hệ thống thực, chọn cách giới hạn/phân trang ngay tại DB theo SQL dialect và thiết kế chỉ mục thích hợp.
- **Xử lý NULL SQL có chủ đích**: nếu một cột không thể null, xác thực ở schema và lớp ánh xạ; nếu có thể null, model thành phần phù hợp. `rs.getLong` trả `0` khi SQL NULL và cần kiểm tra `rs.wasNull()` nếu phải phân biệt.
- **Ánh xạ giá trị chính xác**: `getBigDecimal` giúp không đánh mất độ chính xác của số tiền do chuyển sang `double`.
- **Phạm vi bảo mật**: điều kiện phân quyền dữ liệu phải được áp dụng trong truy vấn/tầng repository, không phải chỉ dựa vào việc đã tạo DTO.

## 8. Với Spring Data JPA: record là projection DTO, không phải entity tự quản lý

Trong Spring Data JPA hiện hành, record phù hợp với **class-based projection (DTO projection)**. Chẳng hạn, một record nằm trong package có thể truy cập từ repository:

~~~java
package com.example.dto;

public record ProductNameView(Long id, String title) {}
~~~

Một JPQL query có thể sử dụng **constructor expression** để tạo record bằng các cột đã chọn:

~~~java
@Query("""
    SELECT new com.example.dto.ProductNameView(p.id, p.title)
    FROM Product p
    WHERE p.active = true
    """)
List<ProductNameView> findActiveNames();
~~~

Đoạn repository là **minh họa tích hợp**: cần entity `Product` và các import của Spring Data JPA. Đảm bảo tên package và thứ tự/kiểu tham số constructor khớp với các trường đã chọn.

Một số dạng derived query hoặc JPQL được Spring Data JPA hỗ trợ tự viết lại cho DTO projection; mức độ áp dụng phụ thuộc hình thức truy vấn và phiên bản framework. Không nên kết luận “cứ trả về record thì mọi native SQL đều được tự map”. Khi mapping native query không khớp constructor, cần chỉ rõ cơ chế ánh xạ (ví dụ result set mapping hoặc mapper của ứng dụng).

Không nhầm **DTO projection** với **managed entity**: thay đổi một record trả về không có setter để tự động cập nhật DB, và record kết quả không mang theo dirty checking hoặc lazy-loading tự động của một entity được quản lý. Khi cần cập nhật, dùng repository/service thực hiện lệnh cập nhật hoặc thao tác trên entity theo đúng mô hình persistence.

## 9. Record chỉ bất biến nông: phải kiểm soát thành phần có thể thay đổi

Ví dụ sau **không đảm bảo bất biến sâu**:

~~~java
record SearchPage(List<String> tags) {}
~~~

Nếu truyền một `ArrayList` vào rồi sửa danh sách từ bên ngoài, `SearchPage.tags()` vẫn trỏ tới danh sách đã bị thay đổi. Thành phần record là tham chiếu `final`, **không đồng nghĩa đối tượng được tham chiếu là bất biến**.

Một cách bảo vệ phổ biến là tạo bản sao không sửa được tại compact constructor:

~~~java
import java.util.List;
import java.util.Objects;

record SearchPage(List<String> tags) {
    SearchPage {
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }
}
~~~

`List.copyOf` tạo một danh sách không thể thêm/xóa/sửa qua API của nó và từ chối phần tử `null`. Trong ví dụ, `String` cũng bất biến nên đủ để bảo vệ dữ liệu phần tử. Nếu phần tử là đối tượng có thể sửa, chỉ sao chép danh sách **chưa đủ**; cần snapshot hoặc bản sao thích hợp của từng phần tử theo hợp đồng.

Với thành phần là mảng `byte[]`, thường phải clone cả ở constructor lẫn accessor để tránh lộ tham chiếu. Ngoài ra, `equals/hashCode` được sinh cho thành phần mảng dựa trên **ngữ nghĩa của mảng** (so sánh tham chiếu, không so sánh từng phần tử); nếu nghiệp vụ cần so sánh theo nội dung, dùng representation/equals phù hợp hoặc cân nhắc class riêng.

Tương tự, với `BigDecimal`, `equals` phân biệt scale: `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có thể so sánh `compareTo == 0` nhưng **không bằng nhau** theo `equals`. Vì `equals` của record gồm các thành phần, hai DTO có số tiền biểu diễn bằng scale khác nhau có thể không được xem là bằng nhau. Nếu yêu cầu nghiệp vụ cần chuẩn hóa, thực hiện rõ ràng ở điểm tạo dữ liệu và tránh bỏ qua chính sách làm tròn.

## 10. Những trường hợp nên tránh dùng record

**1. Đối tượng cần thay đổi trạng thái.** Nếu mục tiêu là một workflow cập nhật từng bước như `draft.setTitle(...); draft.setStatus(...);`, record không cung cấp setter. Có thể tạo record mới khi trạng thái thay đổi, nhưng với object có vòng đời và hành vi phong phú thì class thường rõ ràng hơn.

**2. Managed JPA entity.** Record là `final`, không tuân theo các yêu cầu thông thường của entity JPA và không tự tham gia cơ chế tracking. Tách entity và projection DTO.

**3. Record chứa quá nhiều trường không cùng mục đích.** Một constructor 15–20 tham số và phần lớn tùy chọn có thể báo hiệu mô hình chưa được phân ranh rõ. Hãy chia theo use case (ví dụ `ProductListItem`, `ProductDetails`) hoặc dùng một kiểu cấu hình có builder nếu cần.

**4. Kiểu trung gian không cần danh tính tên.** Với chỉ một số đếm `long count` hoặc một chuỗi, thêm record thường làm rối mã. Tạo record khi việc nhóm nhiều giá trị cùng nhau mang ý nghĩa.

**5. Hợp đồng cho phép phụ thuộc mutable sâu mà chưa thiết kế snapshot.** Nếu dữ liệu chứa collection, array, `Date` hoặc đối tượng có setter, phải cân nhắc defensive copy. Chỉ khai báo `record` không tự khóa toàn bộ object graph.

**6. Mô hình cần kế thừa từ một base class.** Record ngầm định `final` và kế thừa trực tiếp từ `java.lang.Record`; không thể `extends` một class khác. Record vẫn có thể `implements` interface.

**7. Payload chứa thông tin bí mật mà có thể bị log.** `toString()` mặc định thường in tên và giá trị tất cả components. Tránh đưa mật khẩu, token, thông tin nhạy cảm vào record được ghi log tự động; áp dụng chính sách ghi log và redaction rõ ràng.

## 11. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gọi `getTitle()` trên record không có phương thức đó | Accessor mặc định là `title()`, không phải JavaBeans getter | Dùng `title()` hoặc cung cấp API khác có chủ đích |
| Chờ record tự động cập nhật DB | DTO là giá trị dữ liệu, không phải managed entity | Tách đọc projection và lệnh ghi thông qua repository |
| Trả nguyên entity từ truy vấn chỉ cần ba trường | Tạo liên kết không cần thiết và có thể lộ dữ liệu | Chọn projection DTO khớp use case |
| Dùng `Object[]` để truyền nhiều kết quả tạm | Dễ sai index/ép kiểu, khó đọc | Dùng record tạm có tên và kiểu rõ |
| Tin record “deep immutable” | Component `final` có thể tham chiếu đối tượng mutable | Defensive copy; cân nhắc snapshot sâu |
| Thêm field vào record API mà không kiểm tra nơi gọi | Constructor và cấu trúc payload thay đổi | Version hóa hoặc cập nhật consumer/test |
| Dùng `double` cho tiền cần độ chính xác thập phân | Có thể gặp sai số biểu diễn nhị phân | Dùng `BigDecimal` và quy tắc làm tròn rõ |
| Nối từ khóa trực tiếp thành SQL | Nguy cơ SQL injection và lỗi escape | `PreparedStatement`, binding tham số |
| Cho rằng `List.copyOf` sao chép sâu | Chỉ bảo vệ danh sách, không tự copy object mutable trong đó | Sao chép phần tử theo bất biến dữ liệu |
| Cho rằng mọi framework tự ánh xạ record | Khả năng mapping phụ thuộc phiên bản, loại truy vấn và constructor | Xác minh hỗ trợ projection và viết mapper khi cần |

## 12. Checklist khi thiết kế dữ liệu

Trước khi tạo một record, trả lời:

1. **Dữ liệu này có vai trò gì?** Kết quả truy vấn, bộ tham số hay giá trị trung gian? Tên record nói lên vai trò chưa?
2. **Tập thành phần có ổn định và cùng ý nghĩa?** Có trường nào được tạo chỉ để dùng cho một màn hình khác?
3. **Có cần quản lý trạng thái hay identity?** Nếu có, record có thực sự phù hợp với mô hình object không?
4. **Các component có bất biến sâu không?** Có collection/mảng/object mutable cần copy không?
5. **Dữ liệu vào đã được kiểm tra?** `null`, khoảng giá, limit, ký tự tìm kiếm, điều kiện miền nghiệp vụ?
6. **Kết quả truy vấn có giới hạn dữ liệu và quyền truy cập đúng không?** SELECT, mapping, quyền, phân trang?
7. **Kiểu public đã có consumer nào?** Thay đổi component có làm đổi canonical constructor, serialized form, `equals/hashCode/toString` không?
8. **Ví dụ/kiểm thử có cả case hợp lệ và lỗi?** Kiểm tra tính chính xác của mapping, thứ tự sắp xếp, `BigDecimal` và defensive copy.

Một cách tổ chức hiệu quả là: **dữ liệu lưu trữ/domain model** → **lọc bằng tham số record** → **tính toán qua record trung gian nếu cần** → **trả projection record chỉ chứa trường cần công bố**. Mỗi kiểu phục vụ một trách nhiệm và có thể được kiểm thử riêng.

## 13. Bài tập tự luyện

**Bài 1 – Cắt đúng projection.** Giả sử `Customer` có ID, tên, email, số điện thoại, ngày đăng ký, trạng thái và số dư. Màn hình danh sách chỉ hiện ID, tên, trạng thái. Hãy tạo `CustomerListItem` dưới dạng record và mô tả vì sao không nên trả toàn bộ entity. Nếu cần xuất email ở màn hình chi tiết, thiết kế DTO riêng.

**Bài 2 – Kiểm tra tham số.** Mở rộng `ProductFilter` ở mục 6 với `maxPrice`. Thêm quy tắc `maxPrice >= minPrice` vào compact constructor và cập nhật pipeline. Viết hai test case: mức giá hợp lệ và khoảng giá ngược phải ném `IllegalArgumentException`.

**Bài 3 – Trung gian tính điểm.** Thay `boolean inStock` bằng `int score`, ví dụ hàng còn tồn cộng 10 điểm, tên bắt đầu bằng từ khóa cộng 5 điểm. Sort giảm dần theo score, khi bằng điểm thì sort theo tên và ID để ổn định. Chỉ trả `List<ProductView>`, không tiết lộ score nội bộ.

**Bài 4 – Bất biến nông.** Tạo `record Tags(List<String> values) {}` từ một `ArrayList`, sửa `ArrayList` bên ngoài và quan sát `values()`. Sau đó thêm compact constructor dùng `List.copyOf` và giải thích kết quả.

**Bài 5 – Tính tương thích dữ liệu.** Thêm trường `currencyCode` vào `ProductView`. Liệt kê những nơi phải kiểm tra lại: lời gọi constructor, mapper JDBC/JPA, JSON API và phép so sánh nếu dùng DTO làm khóa cache hoặc thành phần của `Set`.

## Tài liệu chính thức, còn phù hợp

- [Oracle – Record Classes (Java 21)](https://docs.oracle.com/en/java/javase/21/language/records.html): components, constructor, compact constructor, accessor, semantics của record.
- [Java SE API – `java.lang.Record` (Java 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html): khái niệm data carrier bất biến nông và các thành phần bắt buộc.
- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395): thiết kế records, hoàn thiện tính năng trong Java 16.
- [Spring Data JPA – Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html): record DTO projection, constructor projection và giới hạn khi mapping.
- [Oracle – JDBC `PreparedStatement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): binding tham số và thực thi SQL có tham số.
