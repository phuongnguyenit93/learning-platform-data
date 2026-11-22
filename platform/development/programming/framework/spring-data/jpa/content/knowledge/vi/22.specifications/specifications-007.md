# Xây dựng bộ lọc tùy chọn mà không sinh điều kiện thừa

Một màn hình tìm kiếm thường có nhiều tiêu chí: từ khóa, trạng thái, danh mục, khoảng giá, ngày tạo, cờ hoạt động hoặc email. Người dùng có thể chỉ nhập một vài tiêu chí trong mỗi lần tìm. Nếu luôn đưa mọi điều kiện vào câu query, ứng dụng dễ tạo ra các biểu thức OR để kiểm tra tham số null, điều kiện không cần thiết và truy vấn khó tối ưu.

Spring Data JPA Specification cho phép xây dựng predicate động bằng Criteria API. Chỉ khi người dùng cung cấp một bộ lọc hợp lệ, ứng dụng mới thêm điều kiện tương ứng vào query. Cách làm này giúp query phản ánh đúng yêu cầu tìm kiếm, phân biệt rõ bộ lọc bị bỏ qua với yêu cầu tìm giá trị NULL, và dễ kiểm thử từng điều kiện.

Bài học dùng ví dụ Product để giải thích Specification, JpaSpecificationExecutor, cách xây predicate theo filter DTO, xử lý chuỗi rỗng, Boolean false, collection rỗng, khoảng số/ngày, AND/OR, quan hệ, NULL, phân trang, sort, count query, bảo mật và hiệu năng.

## 1. Bộ lọc tùy chọn là gì?

Giả sử API tìm sản phẩm có các tiêu chí:

- Từ khóa trong tên.
- ID danh mục.
- Giá tối thiểu và tối đa.
- Một hoặc nhiều trạng thái.
- Sản phẩm đang hoạt động hay không.
- Khoảng ngày tạo.
- Email liên hệ có giá trị, không có giá trị hoặc không lọc email.

Người dùng có thể chỉ cung cấp keyword và minPrice; những tiêu chí khác không tham gia lần tìm kiếm đó.

Ví dụ request:

~~~json
{
  "keyword": "keyboard",
  "minPrice": 500000,
  "maxPrice": null,
  "categoryId": null,
  "available": true
}
~~~

Ý nghĩa:

- Tìm sản phẩm có tên chứa keyboard.
- Giá từ 500.000 trở lên.
- Không lọc theo maxPrice và categoryId.
- Chỉ lấy sản phẩm available = true.

Một bộ lọc tùy chọn cần định nghĩa rõ trạng thái đầu vào:

| Trạng thái đầu vào | Ý nghĩa đề xuất |
|---|---|
| Field không được gửi hoặc null | Bỏ qua bộ lọc đó |
| Chuỗi rỗng hoặc chỉ có khoảng trắng | Chuẩn hóa thành không có bộ lọc |
| Boolean false | Lọc theo giá trị false |
| Số 0 | Lọc theo giá trị 0 nếu miền nghiệp vụ cho phép |
| Collection null | Không áp dụng điều kiện collection |
| Collection rỗng | Quy định rõ: bỏ qua, trả rỗng hoặc từ chối request |
| Chế độ NULL riêng | Chủ động tìm giá trị NULL hoặc NOT NULL |

Không nên dùng một giá trị null để biểu diễn nhiều ý nghĩa khác nhau mà API không thể phân biệt.

## 2. Vì sao không nên luôn viết điều kiện OR với tham số null?

Một cách viết phổ biến là:

~~~java
@Query("""
    select p
    from Product p
    where (:keyword is null or lower(p.name) like lower(:pattern))
      and (:categoryId is null or p.category.id = :categoryId)
      and (:available is null or p.available = :available)
    """)
List<Product> search(
    @Param("keyword") String keyword,
    @Param("pattern") String pattern,
    @Param("categoryId") Long categoryId,
    @Param("available") Boolean available
);
~~~

Cách này có thể đúng về mặt logic trong một số trường hợp đơn giản, nhưng có các hạn chế:

- Query luôn chứa mọi nhánh điều kiện dù phần lớn filter không được dùng.
- Biểu thức OR có thể làm optimizer khó chọn index hiệu quả trong một số database và workload.
- Khi số bộ lọc tăng, câu query trở nên dài và khó đọc.
- Việc phân biệt bỏ qua filter với tìm giá trị NULL trở nên khó hơn.
- Kiểm thử từng tổ hợp điều kiện khó hơn.
- Một số tham số cần chuẩn hóa hoặc escape trước khi bind.

Không phải mọi biểu thức OR đều chậm. Optimizer của database có thể tối ưu tốt nhiều trường hợp. Vấn đề là không nên giả định một query với hàng loạt nhánh tham số null luôn có execution plan tốt. Hãy tạo predicate theo đúng filter đã nhận và đo bằng execution plan trên dữ liệu thực tế.

## 3. Specification trong Spring Data JPA

Specification là abstraction của Spring Data JPA để biểu diễn một điều kiện truy vấn dựa trên Criteria API.

Một Specification có dạng:

~~~java
public interface Specification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
    );
}
~~~

Ba tham số có vai trò:

- Root: đại diện entity gốc đang truy vấn và cho phép truy cập thuộc tính/quan hệ.
- CriteriaQuery: mô tả query tổng thể, ví dụ select, distinct, subquery.
- CriteriaBuilder: tạo predicate và expression như equal, like, greaterThan, and, or, isNull.

Specification chưa tự chạy SQL. Nó cung cấp điều kiện để repository xây query khi được gọi.

Có thể kết hợp Specification bằng các phép AND, OR và NOT. Điều này giúp tách điều kiện theo nghiệp vụ và tái sử dụng ở nhiều use case.

## 4. Khai báo repository hỗ trợ Specification

Repository cần kế thừa JpaSpecificationExecutor:

~~~java
package example.repository;

import example.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

JpaSpecificationExecutor cung cấp các method như:

- findAll(specification)
- findAll(specification, sort)
- findAll(specification, pageable)
- findOne(specification)
- count(specification)
- exists(specification)

Nhờ vậy, cùng một bộ lọc có thể dùng để lấy danh sách, phân trang, đếm hoặc kiểm tra tồn tại.

## 5. Thiết kế Filter DTO

Tạo một object chứa các tiêu chí tìm kiếm. Dùng wrapper type như Boolean thay vì primitive boolean khi cần phân biệt không truyền với false.

~~~java
package example.dto;

import example.domain.ProductStatus;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Set;

public record ProductFilter(
    String keyword,
    Long categoryId,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Set<ProductStatus> statuses,
    Boolean available,
    LocalDateTime createdFrom,
    LocalDateTime createdTo,
    NullMode emailNullMode
) {
    public enum NullMode {
        ANY,
        IS_NULL,
        IS_NOT_NULL
    }
}
~~~

Các trường có ý nghĩa:

- keyword null hoặc blank: không lọc theo tên.
- categoryId null: không lọc danh mục.
- minPrice/maxPrice null: không áp dụng cận tương ứng.
- statuses null hoặc empty: trong ví dụ này không lọc trạng thái.
- available null: không lọc; true hoặc false đều là giá trị lọc hợp lệ.
- createdFrom/createdTo null: bỏ qua cận thời gian tương ứng.
- emailNullMode ANY: không lọc email; IS_NULL hoặc IS_NOT_NULL là yêu cầu tường minh.

Hãy ghi rõ hợp đồng này trong API. Nếu sản phẩm có thể có giá 0, không được dùng điều kiện kiểm tra kiểu minPrice > 0 để xác định filter có được gửi hay không. Chỉ kiểm tra null.

## 6. Xây dựng tất cả predicate trong một Specification

Cách rõ ràng là tạo danh sách predicate và chỉ thêm điều kiện khi filter có giá trị:

~~~java
package example.repository.specification;

import example.domain.Product;
import example.dto.ProductFilter;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.jpa.domain.Specification;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> from(ProductFilter filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (filter.keyword() != null
                    && !filter.keyword().isBlank()) {
                String keyword = escapeLike(filter.keyword().strip())
                    .toLowerCase(Locale.ROOT);

                predicates.add(
                    cb.like(
                        cb.lower(root.<String>get("name")),
                        "%" + keyword + "%",
                        '!'
                    )
                );
            }

            if (filter.categoryId() != null) {
                predicates.add(
                    cb.equal(
                        root.get("category").get("id"),
                        filter.categoryId()
                    )
                );
            }

            if (filter.minPrice() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(
                        root.<BigDecimal>get("price"),
                        filter.minPrice()
                    )
                );
            }

            if (filter.maxPrice() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(
                        root.<BigDecimal>get("price"),
                        filter.maxPrice()
                    )
                );
            }

            if (filter.statuses() != null
                    && !filter.statuses().isEmpty()) {
                predicates.add(
                    root.get("status").in(filter.statuses())
                );
            }

            if (filter.available() != null) {
                predicates.add(
                    cb.equal(
                        root.get("available"),
                        filter.available()
                    )
                );
            }

            if (filter.createdFrom() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(
                        root.<LocalDateTime>get("createdAt"),
                        filter.createdFrom()
                    )
                );
            }

            if (filter.createdTo() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(
                        root.<LocalDateTime>get("createdAt"),
                        filter.createdTo()
                    )
                );
            }

            if (filter.emailNullMode()
                    == ProductFilter.NullMode.IS_NULL) {
                predicates.add(cb.isNull(root.get("contactEmail")));
            } else if (filter.emailNullMode()
                    == ProductFilter.NullMode.IS_NOT_NULL) {
                predicates.add(cb.isNotNull(root.get("contactEmail")));
            }

            if (predicates.isEmpty()) {
                return null;
            }

            return cb.and(predicates.toArray(Predicate[]::new));
        };
    }

    private static String escapeLike(String value) {
        return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }
}
~~~

Đây là ví dụ cần có entity Product với các property tương ứng: name, category, price, status, available, createdAt và contactEmail. Các import, enum và mapping domain phải khớp với dự án thực tế khi áp dụng.

Điểm quan trọng:

- Predicate chỉ được thêm khi filter tương ứng có giá trị.
- Boolean false vẫn được thêm vì điều kiện kiểm tra là null, không phải if (available).
- Khoảng giá có thể chỉ có min, chỉ có max hoặc có cả hai.
- Danh sách trạng thái rỗng được coi là không lọc theo trạng thái trong hợp đồng ví dụ.
- IS NULL và IS NOT NULL được biểu diễn bằng chế độ riêng.
- Nếu không có predicate nào, Specification trả về null để Spring Data không thêm WHERE clause.
- Nếu có predicate, chúng được kết hợp bằng AND.

Việc trả về null từ toPredicate có ý nghĩa không áp dụng predicate trong cơ chế Specification của Spring Data JPA. Không dùng cb.conjunction() một cách máy móc nếu mục tiêu là không tạo điều kiện WHERE không cần thiết.

## 7. Phân biệt null, false và 0

Một lỗi thường gặp là kiểm tra giá trị theo truthiness hoặc điều kiện khác null không đúng cách.

Ví dụ sai:

~~~java
if (filter.available()) {
    predicates.add(cb.isTrue(root.get("available")));
}
~~~

Đoạn này bỏ qua trường hợp available = false, vì false không vào nhánh if.

Cách đúng:

~~~java
if (filter.available() != null) {
    predicates.add(
        cb.equal(root.get("available"), filter.available())
    );
}
~~~

Tương tự với số:

~~~java
if (filter.minPrice() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"),
            filter.minPrice()
        )
    );
}
~~~

Nếu minPrice bằng 0 và nghiệp vụ cho phép, điều kiện vẫn được thêm.

Quy tắc chung: dùng wrapper type và kiểm tra null khi null có nghĩa là bỏ qua filter; không kiểm tra giá trị có khác false hoặc 0 hay không.

## 8. Chuỗi rỗng và khoảng trắng

Một keyword null, chuỗi rỗng hoặc chỉ chứa khoảng trắng thường nên được chuẩn hóa thành không có bộ lọc.

Ví dụ:

~~~java
if (filter.keyword() != null
        && !filter.keyword().isBlank()) {
    String keyword = filter.keyword().strip();
    // Thêm predicate tìm kiếm.
}
~~~

isBlank() kiểm tra chuỗi rỗng hoặc chỉ có whitespace; strip() loại khoảng trắng ở hai đầu theo quy tắc Unicode của Java.

Nếu nghiệp vụ cần tìm đúng chuỗi rỗng trong database, đó là một chế độ filter riêng. Không dùng blank làm đại diện cho cả bỏ qua filter và tìm dữ liệu rỗng.

Có thể chuẩn hóa ở tầng service trước khi tạo Specification để logic truy vấn gọn hơn. Nhưng hãy thống nhất cùng một chính sách khi lưu và khi tìm kiếm.

## 9. LIKE và escape wildcard

Khi dùng LIKE, % và _ có ý nghĩa wildcard:

- % khớp không hoặc nhiều ký tự.
- _ khớp đúng một ký tự.

Nếu người dùng nhập ký tự này để tìm literal, cần escape. Trong ví dụ, ký tự ! được chọn làm escape:

~~~java
private static String escapeLike(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

Predicate CriteriaBuilder:

~~~java
cb.like(
    cb.lower(root.<String>get("name")),
    "%" + escapedKeyword.toLowerCase(Locale.ROOT) + "%",
    '!'
)
~~~

Thứ tự escape rất quan trọng: escape ký tự escape trước, rồi mới escape % và _. Nếu làm ngược, ký tự ! vừa được thêm có thể bị escape lần nữa.

Bind parameter và escape wildcard giải quyết hai vấn đề khác nhau:

- Bind parameter tách dữ liệu khỏi cú pháp query.
- Escape wildcard bảo đảm ký tự % và _ do người dùng nhập được tìm như ký tự literal.

## 10. Xây dựng Specification nhỏ và tái sử dụng

Khi bộ lọc có nhiều điều kiện, có thể tách thành các Specification nhỏ theo nghiệp vụ.

Ví dụ:

~~~java
public static Specification<Product> nameContains(String keyword) {
    return (root, query, cb) -> {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }

        String value = escapeLike(keyword.strip())
            .toLowerCase(Locale.ROOT);

        return cb.like(
            cb.lower(root.<String>get("name")),
            "%" + value + "%",
            '!'
        );
    };
}

public static Specification<Product> priceAtLeast(
        BigDecimal minPrice) {
    return (root, query, cb) -> {
        if (minPrice == null) {
            return null;
        }

        return cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"),
            minPrice
        );
    };
}

public static Specification<Product> isAvailable(Boolean available) {
    return (root, query, cb) -> {
        if (available == null) {
            return null;
        }

        return cb.equal(root.get("available"), available);
    };
}
~~~

Có thể kết hợp:

~~~java
Specification<Product> spec =
    ProductSpecs.hasCategory(categoryId)
        .and(ProductSpecs.priceAtLeast(minPrice))
        .and(ProductSpecs.isAvailable(available));
~~~

Các Specification không có filter trả về null predicate. Cơ chế composition của Spring Data JPA xử lý predicate null như một điều kiện không tham gia phép kết hợp.

Ở các phiên bản Spring Data JPA mới, một số API composition có thể có cảnh báo deprecation hoặc cách khởi tạo unrestricted specification mới. Hãy dùng API tương ứng với release train của dự án; nguyên tắc cốt lõi vẫn là không thêm predicate cho filter bị bỏ qua.

Nếu dự án muốn tránh phụ thuộc vào khác biệt phiên bản, có thể dùng một Specification duy nhất xây List<Predicate> như phần 6.

## 11. Kết hợp AND và OR đúng nhóm

Mặc định ví dụ ở phần trước kết hợp các filter bằng AND:

~~~text
keyword AND category AND minPrice AND available
~~~

Có trường hợp một nhóm điều kiện cần OR, ví dụ tìm sản phẩm có tên chứa keyword hoặc mã SKU chứa keyword:

~~~java
Predicate nameMatches = cb.like(
    cb.lower(root.<String>get("name")),
    pattern,
    '!'
);

Predicate skuMatches = cb.like(
    cb.lower(root.<String>get("sku")),
    pattern,
    '!'
);

predicates.add(cb.or(nameMatches, skuMatches));
~~~

Kết quả là nhóm điều kiện:

~~~text
(name matches keyword OR sku matches keyword)
AND category filter
AND price filter
~~~

Hãy tạo nhóm OR thành một predicate riêng rồi thêm predicate đó vào danh sách AND tổng thể. Tránh ghép các toán tử theo cách làm thay đổi ý nghĩa do ưu tiên AND/OR.

Nếu một nhánh OR là tùy chọn, chỉ thêm nhánh đó khi input hợp lệ. Không thêm điều kiện so sánh với null chỉ để giữ số lượng predicate cố định.

## 12. Khoảng giá và khoảng thời gian

Với minPrice và maxPrice:

- Chỉ có minPrice: price >= minPrice.
- Chỉ có maxPrice: price <= maxPrice.
- Có cả hai: price nằm trong khoảng.
- Cả hai null: không lọc theo giá.

Có thể kiểm tra minPrice <= maxPrice ở tầng validation. Nếu minPrice lớn hơn maxPrice, trả lỗi đầu vào rõ ràng thay vì chạy query chắc chắn không có kết quả.

Với thời gian, quyết định khoảng là inclusive hay exclusive:

- GreaterThanOrEqualTo và LessThanOrEqualTo là inclusive.
- GreaterThan và LessThan là exclusive.

Nếu API nhận LocalDate nhưng database lưu timestamp, cần xác định múi giờ và cách chuyển ngày cuối thành thời điểm cuối ngày. Không tự cộng một ngày hoặc đổi timezone trong Specification nếu quy tắc nghiệp vụ chưa rõ.

Với khoảng thời gian nửa mở [from, to), thường dùng createdAt >= from và createdAt < to. Cách này hữu ích khi lọc theo ngày hoặc khoảng thời gian liên tiếp mà tránh chồng lấn biên.

## 13. Collection filter và danh sách rỗng

Điều kiện IN phù hợp khi người dùng chọn nhiều trạng thái:

~~~java
if (filter.statuses() != null
        && !filter.statuses().isEmpty()) {
    predicates.add(root.get("status").in(filter.statuses()));
}
~~~

Cần định nghĩa rõ semantics:

| Giá trị statuses | Hành vi trong ví dụ |
|---|---|
| null | Không lọc trạng thái |
| Empty set | Không lọc trạng thái |
| Có phần tử | Chỉ lấy trạng thái nằm trong set |

Nếu nghiệp vụ quy định danh sách rỗng có nghĩa không chọn sản phẩm nào, phải biểu diễn điều đó rõ ràng bằng predicate luôn false:

~~~java
if (filter.statuses() != null
        && filter.statuses().isEmpty()) {
    predicates.add(cb.disjunction());
}
~~~

cb.disjunction() là predicate FALSE. Ngược lại, cb.conjunction() là predicate TRUE.

Không truyền collection rỗng vào IN rồi phụ thuộc provider tạo SQL gì. Cách xử lý IN với collection rỗng có thể khác nhau giữa provider hoặc database. Hãy quyết định từ API contract và tạo predicate tương ứng.

## 14. Quan hệ và JOIN chỉ khi filter cần

Nếu người dùng lọc theo categoryId, query mới cần tham chiếu đến category. Nếu filter không có categoryId, không cần tạo join chỉ để kiểm tra điều kiện không hoạt động.

Ví dụ:

~~~java
if (filter.categoryId() != null) {
    predicates.add(
        cb.equal(
            root.get("category").get("id"),
            filter.categoryId()
        )
    );
}
~~~

Nếu cần kiểm soát kiểu JOIN rõ ràng:

~~~java
if (filter.categoryId() != null) {
    Join<Product, Category> category =
        root.join("category", JoinType.INNER);

    predicates.add(
        cb.equal(category.get("id"), filter.categoryId())
    );
}
~~~

Chỉ tạo Join khi có filter cần dùng nó. Với quan hệ optional, INNER JOIN có thể loại entity không có category; điều này phù hợp nếu filter categoryId đang được áp dụng nhưng không phù hợp nếu mục tiêu là giữ các sản phẩm không có category.

Đừng tạo join trước rồi mới kiểm tra filter có null hay không. Join không cần thiết có thể làm thay đổi tập kết quả hoặc tăng chi phí query.

## 15. Collection relationship và duplicate root entity

Nếu lọc Product theo một collection quan hệ như tags, join có thể tạo nhiều hàng cho cùng Product.

Ví dụ:

~~~java
Join<Product, Tag> tag = root.join("tags");
predicates.add(tag.get("id").in(filter.tagIds()));
query.distinct(true);
~~~

DISTINCT có thể loại entity gốc trùng trong kết quả, nhưng việc join collection cũng có thể làm count query và phân trang phức tạp hơn.

Nếu chỉ cần kiểm tra Product có ít nhất một Tag phù hợp, cân nhắc correlated EXISTS subquery để tránh nhân số hàng ở query chính. Cấu trúc minh họa:

~~~java
Subquery<Integer> subquery = query.subquery(Integer.class);
Root<ProductTag> productTag = subquery.from(ProductTag.class);

subquery.select(cb.literal(1))
    .where(
        cb.equal(productTag.get("product"), root),
        productTag.get("tag").get("id").in(filter.tagIds())
    );

predicates.add(cb.exists(subquery));
~~~

Ví dụ này giả định domain có entity ProductTag với quan hệ product và tag. Điều chỉnh tên entity/property theo mapping thực tế.

EXISTS thường thể hiện rõ mục tiêu kiểm tra sự tồn tại và tránh nhân hàng Product ở query ngoài. Vẫn cần đo hiệu năng trên database thực tế.

## 16. Phân biệt bỏ qua filter với tìm giá trị NULL

Đây là một trong những quyết định API quan trọng nhất.

Ví dụ field contactEmail:

- ANY: không áp dụng điều kiện email.
- IS_NULL: chỉ lấy sản phẩm có contactEmail NULL.
- IS_NOT_NULL: chỉ lấy sản phẩm có contactEmail khác NULL.

Không thể biểu diễn đầy đủ ba trạng thái này bằng một String nullable đơn giản nếu null vừa có nghĩa không gửi vừa có nghĩa tìm NULL.

Dùng enum hoặc một trường mode riêng:

~~~java
public enum NullMode {
    ANY,
    IS_NULL,
    IS_NOT_NULL
}
~~~

Specification:

~~~java
if (filter.emailNullMode() == NullMode.IS_NULL) {
    predicates.add(cb.isNull(root.get("contactEmail")));
} else if (filter.emailNullMode() == NullMode.IS_NOT_NULL) {
    predicates.add(cb.isNotNull(root.get("contactEmail")));
}
~~~

Nếu API dùng JSON, có thể dùng một trường operation rõ ràng như emailMode. Tránh dựa vào việc phân biệt field bị bỏ qua và field có giá trị null nếu framework deserialize cả hai thành cùng một trạng thái.

Với PATCH hoặc filter API cần phân biệt missing và explicit null, có thể dùng wrapper/JSON node/tri-state DTO phù hợp với framework serialization.

## 17. Validation trước khi tạo query

Specification chịu trách nhiệm chuyển filter hợp lệ thành predicate. Validation đầu vào nên được xử lý ở tầng API/service hoặc trong constructor của filter DTO.

Các kiểm tra thường cần:

- minPrice không âm nếu domain không cho giá âm.
- minPrice không lớn hơn maxPrice.
- createdFrom không sau createdTo.
- keyword có độ dài tối đa.
- danh sách trạng thái không vượt giới hạn.
- categoryId và các ID khác có định dạng hợp lệ.
- page size và page number nằm trong giới hạn.
- sort key thuộc danh sách được phép.

Không dùng Specification để thay thế toàn bộ validation. Một request không hợp lệ nên được từ chối với lỗi rõ ràng thay vì âm thầm tạo query không có kết quả.

## 18. Kết hợp Specification với Pageable và Sort

Specification mô tả điều kiện lọc; Pageable mô tả phân trang và thứ tự. Nên giữ hai trách nhiệm này tách biệt.

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Service:

~~~java
public Page<Product> search(
        ProductFilter filter,
        Pageable pageable) {

    Specification<Product> specification =
        ProductSpecifications.from(filter);

    return productRepository.findAll(specification, pageable);
}
~~~

Pageable có thể chứa Sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Thêm khóa duy nhất làm tiêu chí cuối giúp thứ tự ổn định khi nhiều bản ghi có cùng createdAt.

Không nên đặt orderBy vào mọi Specification nếu cùng Specification còn được dùng với Pageable có Sort. Việc một Specification thay đổi query order có thể xung đột với sort của caller hoặc ảnh hưởng count query.

Nếu cần sort theo biểu thức đặc biệt, hãy xử lý riêng bằng query/custom repository có kiểm soát.

## 19. Page, Slice và count query

findAll(specification, pageable) thường trả Page. Page cung cấp tổng số phần tử và tổng số trang; để tính các giá trị này, Spring Data có thể chạy count query.

Nếu Specification tạo JOIN collection, count query có thể đếm hàng JOIN thay vì entity gốc. Cần dùng DISTINCT phù hợp hoặc cấu trúc EXISTS để đếm đúng.

Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, cân nhắc Slice. Slice thường không cần count tổng, giảm chi phí với truy vấn lớn.

Khi query có join phức tạp, fetch collection hoặc distinct, hãy kiểm tra SQL và count query được sinh. Nếu cần kiểm soát count query riêng, có thể dùng repository query tường minh hoặc custom repository phù hợp.

## 20. Sort key từ client phải được whitelist

Không cho client truyền bất kỳ tên property nào rồi chuyển trực tiếp vào Sort.

Ví dụ ánh xạ sort key công khai:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "newest", "createdAt",
    "price", "price",
    "name", "name"
);

public Sort resolveSort(String key, String direction) {
    String property = SORT_FIELDS.get(key);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction sortDirection =
        Sort.Direction.fromString(direction);

    return Sort.by(
        new Sort.Order(sortDirection, property)
    );
}
~~~

Whitelist giúp giới hạn query vào những property được phép và tránh lộ dữ liệu qua sort theo field nội bộ. Không dùng raw input với JpaSort.unsafe.

Cũng cần giới hạn page size, số sort criteria và direction. Nếu direction không hợp lệ, trả lỗi rõ ràng thay vì âm thầm chọn DESC.

## 21. Tách Specification theo từng tiêu chí

Với hệ thống lớn, mỗi điều kiện có thể là một method riêng để tái sử dụng:

~~~java
public final class ProductSpecs {

    private ProductSpecs() {
    }

    public static Specification<Product> hasCategory(Long categoryId) {
        return (root, query, cb) -> categoryId == null
            ? null
            : cb.equal(root.get("category").get("id"), categoryId);
    }

    public static Specification<Product> priceAtLeast(
            BigDecimal minPrice) {
        return (root, query, cb) -> minPrice == null
            ? null
            : cb.greaterThanOrEqualTo(
                root.<BigDecimal>get("price"),
                minPrice
            );
    }

    public static Specification<Product> isAvailable(Boolean available) {
        return (root, query, cb) -> available == null
            ? null
            : cb.equal(root.get("available"), available);
    }
}
~~~

Ghép các Specification:

~~~java
Specification<Product> spec =
    ProductSpecs.hasCategory(categoryId)
        .and(ProductSpecs.priceAtLeast(minPrice))
        .and(ProductSpecs.isAvailable(available));
~~~

Cách này giúp tái sử dụng và kiểm thử từng predicate. Tuy nhiên, nếu có nhiều filter, một method from(filter) xây List<Predicate> có thể dễ theo dõi hơn vì toàn bộ hợp đồng filter nằm ở một nơi.

Chọn cấu trúc phù hợp với độ phức tạp. Không cần tạo hàng chục class nhỏ nếu chúng không được tái sử dụng hoặc không giúp code dễ đọc hơn.

## 22. Khi nào nên dùng Specification, khi nào dùng @Query?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Một query cố định, ít điều kiện | Derived query hoặc @Query |
| Nhiều filter tùy chọn kết hợp linh hoạt | Specification |
| Cần tái sử dụng predicate giữa nhiều query | Specification |
| Query có projection, group by hoặc biểu thức phức tạp | @Query hoặc custom repository |
| Query cần cấu trúc động nhiều kiểu | Criteria API hoặc Specification |
| SQL phụ thuộc database | Native query/custom repository |
| Bộ lọc đơn giản, chỉ vài tham số | Derived query có thể đủ |

Không dùng Specification chỉ vì có thể dùng. Với query cố định và đơn giản, method repository dễ đọc hơn. Specification phát huy giá trị khi tổ hợp điều kiện thay đổi theo request và cần tái sử dụng.

## 23. Kiểm thử Specification

Nên có cả unit test cho logic predicate và integration test cho kết quả database.

Dữ liệu test có thể gồm:

| Product | category | price | available | contactEmail |
|---|---|---:|---|---|
| Keyboard A | 1 | 700000 | true | a@example.com |
| Keyboard B | 1 | 400000 | false | NULL |
| Mouse A | 2 | 250000 | true | m@example.com |
| Mouse B | 2 | 0 | false | NULL |

Các trường hợp cần kiểm tra:

1. Tất cả filter null: không thêm WHERE predicate và trả toàn bộ dữ liệu theo quyền truy cập/phạm vi mặc định của ứng dụng.
2. Keyword blank: bỏ qua filter tên.
3. Keyword có giá trị: chỉ trả sản phẩm khớp.
4. Keyword có % hoặc _: tìm literal nếu contract yêu cầu.
5. available = true: chỉ trả true.
6. available = false: chỉ trả false.
7. minPrice = 0: vẫn thêm điều kiện nếu 0 hợp lệ.
8. Chỉ có minPrice hoặc maxPrice: áp dụng đúng một cận.
9. Cả hai cận: trả đúng khoảng.
10. statuses null và empty: đúng semantics đã công bố.
11. emailNullMode IS_NULL: chỉ lấy email NULL.
12. emailNullMode IS_NOT_NULL: chỉ lấy email khác NULL.
13. OR group: kiểm tra đúng ngoặc logic.
14. JOIN collection: không nhân entity ngoài ý muốn.
15. Page: totalElements đếm đúng entity.
16. Sort: thứ tự có tie-breaker ổn định.

Ví dụ test tích hợp:

~~~java
@DataJpaTest
class ProductSpecificationTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void falseIsARealFilterValue() {
        ProductFilter filter = new ProductFilter(
            null,
            null,
            null,
            null,
            null,
            false,
            null,
            null,
            ProductFilter.NullMode.ANY
        );

        List<Product> products = repository.findAll(
            ProductSpecifications.from(filter)
        );

        assertTrue(products.stream().allMatch(
            product -> !product.getAvailable()
        ));
    }
}
~~~

Test giả định fixture đã được chuẩn bị và Product có getter available. Với dự án thực tế, thêm import, setup dữ liệu và transaction test theo cấu hình hiện tại.

Nếu cần chứng minh không tạo predicate thừa, có thể bật SQL logging hoặc dùng StatementInspector/query counter để kiểm tra SQL được sinh cho từng tổ hợp filter. Không nên chỉ kiểm tra kết quả cuối nếu nhiều query khác nhau có thể tình cờ trả cùng dữ liệu.

## 24. Hiệu năng và query plan

Dynamic Specification có thể tạo nhiều hình dạng SQL tùy tổ hợp filter. Điều đó giúp tránh các nhánh OR không cần thiết, nhưng không tự bảo đảm query nhanh.

Cần chú ý:

- Index cho các cột thường dùng trong equality/range filter.
- Thứ tự cột trong composite index theo workload thực tế.
- LIKE với wildcard đầu chuỗi thường khó tận dụng B-tree index.
- LOWER(column) có thể cần functional index hoặc cột normalized.
- JOIN collection có thể nhân số hàng và làm count query đắt hơn.
- Nhiều predicate AND/OR cần xem execution plan.
- Page phát sinh count query; Slice có thể phù hợp hơn nếu không cần total.
- Không tạo join hoặc fetch join khi filter không cần quan hệ đó.

Dùng EXPLAIN/EXPLAIN ANALYZE hoặc công cụ tương ứng của database để kiểm tra. Đo với dữ liệu gần production và các tổ hợp filter thường gặp.

## 25. Các lỗi thường gặp

**1. Dùng Boolean primitive cho filter tùy chọn**

Primitive false không phân biệt được không truyền với muốn lọc false. Dùng Boolean wrapper.

**2. Dùng điều kiện if (available)**

Cách này bỏ qua false. Kiểm tra available != null.

**3. Xem chuỗi blank là filter hợp lệ**

Keyword rỗng có thể tạo LIKE '%%' và không có giá trị lọc. Chuẩn hóa blank thành bỏ qua filter nếu đó là API contract.

**4. Dùng null vừa để bỏ qua filter vừa để tìm NULL**

Hai ý nghĩa khác nhau. Dùng enum hoặc operation mode riêng.

**5. Truyền collection rỗng vào IN**

Có thể tạo SQL không hợp lệ hoặc hành vi khác nhau giữa provider. Xử lý empty collection trước khi tạo predicate.

**6. Tạo JOIN trước khi biết filter có cần không**

Join không cần thiết có thể loại entity hoặc tăng chi phí. Chỉ tạo join khi điều kiện tương ứng được áp dụng.

**7. Dùng DISTINCT để che giấu mọi vấn đề JOIN**

DISTINCT có chi phí và không sửa điều kiện join sai. Cân nhắc EXISTS nếu chỉ cần kiểm tra tồn tại.

**8. Đưa sort field từ client vào trực tiếp**

Whitelist property và direction. Không dùng raw input trong Sort expression.

**9. Đặt ORDER BY trong Specification**

Specification nên tập trung vào predicate. Dùng Pageable/Sort để caller quyết định thứ tự, trừ trường hợp custom query có yêu cầu đặc biệt.

**10. Quên count query khi phân trang**

JOIN collection có thể làm totalElements sai hoặc tốn kém. Kiểm thử Page và cân nhắc EXISTS, DISTINCT hoặc Slice.

**11. Không validate khoảng giá/ngày**

min lớn hơn max tạo query vô nghĩa. Từ chối request không hợp lệ trước khi truy vấn.

**12. Tạo quá nhiều Specification nhỏ không cần thiết**

Tách khi có tái sử dụng hoặc ranh giới nghiệp vụ rõ. Nếu không, một builder tập trung có thể dễ đọc hơn.

## 26. Quy trình xây dựng bộ lọc tùy chọn

1. Liệt kê từng filter và kiểu dữ liệu.
2. Định nghĩa rõ null, blank, false, 0 và collection empty có ý nghĩa gì.
3. Phân biệt bỏ qua filter với tìm giá trị NULL.
4. Validate đầu vào và khoảng giá/ngày.
5. Chuẩn hóa keyword và escape wildcard nếu cần.
6. Tạo predicate chỉ khi filter hợp lệ được cung cấp.
7. Ghép các điều kiện AND và OR theo đúng nhóm nghiệp vụ.
8. Chỉ JOIN quan hệ khi có điều kiện cần dùng.
9. Dùng EXISTS nếu chỉ cần kiểm tra collection có phần tử phù hợp.
10. Giữ sort và pagination ở Pageable.
11. Kiểm tra count query nếu dùng Page.
12. Whitelist sort key và giới hạn page size.
13. Viết unit/integration test cho từng trạng thái filter.
14. Xem SQL và execution plan trên database mục tiêu.

## 27. Checklist tự đánh giá

- [ ] Tôi giải thích được Specification và JpaSpecificationExecutor.
- [ ] Tôi biết tạo predicate động từ Filter DTO.
- [ ] Tôi chỉ thêm điều kiện khi filter có giá trị.
- [ ] Tôi biết trả null predicate khi không có điều kiện áp dụng.
- [ ] Tôi phân biệt Boolean null với false.
- [ ] Tôi phân biệt số 0 với filter bị bỏ qua.
- [ ] Tôi định nghĩa rõ semantics của collection null và empty.
- [ ] Tôi phân biệt bỏ qua filter với tìm giá trị NULL.
- [ ] Tôi chuẩn hóa chuỗi rỗng và khoảng trắng theo API contract.
- [ ] Tôi escape wildcard LIKE khi cần tìm literal.
- [ ] Tôi kết hợp AND/OR đúng nhóm.
- [ ] Tôi chỉ tạo JOIN khi cần.
- [ ] Tôi cân nhắc EXISTS cho collection relationship.
- [ ] Tôi kết hợp Specification với Pageable/Sort đúng trách nhiệm.
- [ ] Tôi kiểm tra count query và pagination.
- [ ] Tôi whitelist sort key và validate input.
- [ ] Tôi có integration test cho false, 0, NULL, empty collection và khoảng giá.
- [ ] Tôi kiểm tra SQL và execution plan khi cần tối ưu.

## 28. Câu hỏi ôn tập

**1. Specification giải quyết vấn đề gì?**

Nó cho phép xây dựng điều kiện truy vấn động từ nhiều filter tùy chọn bằng Criteria API và kết hợp chúng theo AND, OR hoặc NOT.

**2. Vì sao không nên luôn viết tham số null OR điều kiện?**

Cách đó giữ nhiều nhánh không cần thiết trong query và có thể làm optimizer khó tận dụng index trong một số trường hợp. Specification có thể chỉ thêm predicate thật sự được dùng.

**3. Vì sao Boolean filter phải dùng Boolean thay vì boolean?**

Boolean null biểu diễn không áp dụng filter; true và false đều là giá trị lọc. Primitive boolean không có trạng thái null.

**4. Khi nào Specification trả về null predicate?**

Khi không có điều kiện tương ứng cần áp dụng. Spring Data JPA bỏ qua predicate null trong quá trình xây query.

**5. Collection rỗng nên có nghĩa gì?**

Đó là quyết định API/domain. Có thể bỏ qua filter, trả về rỗng hoặc từ chối request. Phải định nghĩa rõ và không phụ thuộc cách provider xử lý IN rỗng.

**6. Làm sao phân biệt không lọc email với chỉ tìm email NULL?**

Dùng chế độ riêng như ANY, IS_NULL và IS_NOT_NULL thay vì chỉ một tham số String nullable.

**7. Vì sao chỉ JOIN khi filter cần quan hệ?**

JOIN không cần thiết có thể làm thay đổi tập kết quả, nhân số hàng hoặc tăng chi phí. Tạo join đúng lúc giúp query sát với yêu cầu.

**8. Khi nào dùng EXISTS thay cho JOIN?**

Khi chỉ cần biết có ít nhất một bản ghi liên quan thỏa điều kiện mà không cần lấy dữ liệu từ bản ghi đó. EXISTS thường tránh nhân hàng ở query chính.

**9. Specification có nên chịu trách nhiệm sắp xếp không?**

Thông thường không. Specification mô tả predicate; Pageable và Sort mô tả thứ tự/phân trang. Tách hai trách nhiệm giúp tái sử dụng và tránh xung đột.

**10. Vì sao cần test SQL ngoài test kết quả?**

Hai cách xây query có thể trả cùng kết quả trên fixture nhỏ nhưng có chi phí rất khác nhau. SQL logging, query counter và execution plan giúp phát hiện điều kiện thừa, join không cần thiết và count query đắt.

Bộ lọc tùy chọn tốt chỉ đưa những điều kiện người dùng thực sự yêu cầu vào query. Khi định nghĩa rõ semantics của null, false, 0, chuỗi blank và collection rỗng, Specification giúp repository dễ đọc, dễ kiểm thử và dễ tối ưu hơn.

## Tài liệu tham khảo

- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
