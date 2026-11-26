# So sánh Querydsl, QBE và query method theo nhu cầu bộ lọc

Một màn hình chỉ tìm khách hàng theo email có nhu cầu khác với màn hình tìm kiếm có nhiều trường tùy chọn, khoảng chi tiêu và nhóm điều kiện AND/OR. Chọn cách viết truy vấn theo hình dạng bộ lọc giúp repository dễ đọc và giữ đúng ý nghĩa khi nghiệp vụ mở rộng.

Trong Spring Data Commons, query method, Query by Example (QBE) và tích hợp Querydsl là những hướng tiếp cận có thể cùng xuất hiện trong một ứng dụng. Chúng không thay thế lẫn nhau trong mọi trường hợp. Store module quyết định khả năng triển khai thực tế, các phép toán hỗ trợ và cách chuyển điều kiện thành truy vấn.

Bài học so sánh ba hướng theo nhu cầu bộ lọc, từ điều kiện cố định đến điều kiện động có nhóm logic. Các ví dụ không giả định mọi store hỗ trợ đồng thời QBE, Querydsl và cùng một ngôn ngữ truy vấn khai báo.

## 1. Làm rõ ý nghĩa của query method

Trong phạm vi Spring Data, query method là phương thức repository dùng để truy vấn. Hai hình thức cần phân biệt:

- **Derived query method:** Spring Data phân tích tên method để tạo truy vấn, ví dụ `findByEmail` hoặc `findByStatusAndCity`.
- **Declared query method:** method có truy vấn được khai báo bằng cơ chế của store, chẳng hạn `@Query` trong Spring Data JPA.

Khi đối chiếu độ dài tên method hoặc số tổ hợp bộ lọc, bài học chủ yếu nói về derived query method. Một method dùng `@Query` có thể biểu diễn nhóm điều kiện, join hoặc truy vấn phức tạp theo ngôn ngữ được hỗ trợ; không được gán giới hạn của tên method cho mọi query method.

| Cách tiếp cận | Nơi biểu diễn điều kiện |
| --- | --- |
| Derived query method | Tên method và tham số |
| QBE | Giá trị trong probe cùng `ExampleMatcher` |
| Querydsl | Cây biểu thức có kiểu, thường qua Q-type |
| Declared query method | Văn bản hoặc cấu trúc truy vấn theo store |

Câu hỏi lựa chọn không chỉ là “cách nào ít dòng nhất”, mà là “điều kiện nào có thể được mô tả rõ ràng và duy trì đúng khi thay đổi”.

## 2. Mô hình dùng để so sánh

Giả sử `Customer` có các thuộc tính miền sau:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh |
| `tenantId` | `String` | Phạm vi dữ liệu |
| `fullName` | `String` | Họ tên |
| `email` | `String` | Email |
| `city` | `String` | Thành phố |
| `status` | `CustomerStatus` | Trạng thái nghiệp vụ |
| `active` | `Boolean` | Đang hoạt động hay không |
| `totalSpent` | `BigDecimal` | Tổng chi tiêu |
| `createdAt` | `Instant` | Metadata thời gian tạo |

```java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
```

Các đoạn mã giả định `Customer` có constructor không tham số và getter/setter tương ứng. Mapping phải phù hợp với store đang dùng. Với ví dụ Querydsl, giả định đã có Q-type `QCustomer` và biến gốc `QCustomer.customer`.

Ba nhu cầu tìm kiếm sẽ được mở rộng dần:

1. **Điều kiện ổn định:** tìm theo tenant, trạng thái và thành phố; cả ba đều được yêu cầu.
2. **Bộ lọc tùy chọn:** tên, thành phố và trạng thái có thể không được cung cấp; những điều kiện được cung cấp đều phải thỏa.
3. **Bộ lọc có biểu thức:** cần khoảng chi tiêu và cấu trúc `tenant AND status AND (tên OR thành phố)`.

Các repository bên dưới minh họa các lựa chọn. Không cần tạo cả ba repository chỉ để phục vụ một tính năng nếu ứng dụng không có nhu cầu đó.

## 3. Derived query method: phù hợp với điều kiện ổn định

Một repository có thể khai báo:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;

public interface CustomerMethodRepository
        extends CrudRepository<Customer, Long> {

    Page<Customer> findByTenantIdAndStatusAndCity(
            String tenantId,
            CustomerStatus status,
            String city,
            Pageable pageable);
}
```

Lời gọi thể hiện rõ nghiệp vụ:

```java
Page<Customer> result = repository.findByTenantIdAndStatusAndCity(
        currentTenantId,
        CustomerStatus.ACTIVE,
        "Huế",
        pageable);
```

Trong ví dụ, service đã bảo đảm ba tham số điều kiện hợp lệ và không dùng `null` để biểu diễn “bỏ qua bộ lọc”. Tên method là một mô tả ổn định, dễ tìm và không yêu cầu ứng dụng dựng một đối tượng truy vấn riêng cho mỗi lần gọi.

Derived query không chỉ hỗ trợ phép bằng. Tùy store và thuộc tính, có thể có các từ khóa như `GreaterThanEqual`, `Between`, `Containing`, `In`, `IsNull`, `And` và `Or`. Không nên chọn Querydsl chỉ vì xuất hiện một phép so sánh mà derived query đã biểu diễn rõ ràng được.

### Khi các trường trở thành tùy chọn

Nếu từng trường có thể được bỏ qua, một method cố định không tự biến thành một bộ lọc động theo ý nghĩa “tham số nào null thì không lọc”. Cố tạo một method cho mỗi tổ hợp có thể làm số method tăng nhanh.

Với n tiêu chí độc lập có hoặc không có, số tổ hợp đầu vào có thể lên tới `2^n`. Đây không phải yêu cầu phải tạo đúng `2^n` method; nó cho thấy vì sao việc liệt kê mọi tổ hợp bằng tên method có thể khó duy trì.

Các dấu hiệu cần đánh giá lại:

- Tên method quá dài để đọc chính xác cấu trúc logic.
- Nhiều method chỉ khác nhau một bộ lọc tùy chọn.
- Thêm một field vào màn hình tìm kiếm buộc bổ sung hàng loạt nhánh chọn method trong service.
- Điều kiện chung như tenant bị lặp trong nhiều biểu thức OR khó kiểm tra.

## 4. QBE: phù hợp với nhiều bộ lọc thuộc tính dạng AND

QBE biểu diễn điều kiện qua một đối tượng mẫu. Với chính sách mặc định bỏ qua null, các thuộc tính không được gán có thể không tham gia bộ lọc.

Repository công bố khả năng QBE nếu store hỗ trợ:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerExampleRepository
        extends CrudRepository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Giả sử tên, thành phố và trạng thái đều tùy chọn:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setTenantId(currentTenantId);
probe.setFullName(normalizedName);
probe.setCity(normalizedCity);
probe.setStatus(requestedStatus);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withIgnorePaths("id", "email", "totalSpent", "createdAt")
        .withMatcher("fullName",
                ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase());

Example<Customer> example = Example.of(probe, matcher);
Page<Customer> result = repository.findAll(example, pageable);
```

Trong ví dụ:

- `currentTenantId` là phạm vi bắt buộc đã được service xác định và kiểm tra.
- `normalizedName` và `normalizedCity` là giá trị đã chuẩn hóa theo quy ước đầu vào; không nhập có thể được chuyển thành `null`.
- `requestedStatus` có thể null khi người dùng không lọc trạng thái.
- Chỉ `fullName` được cấu hình chứa chuỗi và không phân biệt hoa thường. Không bật quy tắc đó toàn cục cho mọi thuộc tính.
- `matchingAll()` yêu cầu các điều kiện được xét đều phải thỏa.

Nếu chỉ truyền thành phố, ý định là:

```text
tenantId khớp tenant hiện tại
AND city khớp thành phố đã chọn
```

Nếu truyền thêm tên và trạng thái, các điều kiện đó được bổ sung theo AND. Đây là hình dạng bộ lọc mà QBE có thể diễn đạt ngắn gọn khi mapping và store hỗ trợ các thuộc tính tương ứng.

### Những điểm dễ làm bộ lọc QBE sai ý nghĩa

`null`, chuỗi rỗng và khoảng trắng không giống nhau. `withIgnoreNullValues()` không tự loại một chuỗi `""` hoặc `"   "`.

Kiểu primitive cũng không có trạng thái null. Nếu mô hình dùng `boolean active`, giá trị mặc định false có thể trở thành điều kiện dù người dùng chưa chọn bộ lọc. Với `Boolean`, null có thể biểu diễn không cung cấp giá trị, nếu phù hợp với mô hình nghiệp vụ.

Các giá trị khởi tạo trong constructor và metadata được sao chép từ entity cũng có thể tham gia probe. Auditing không tự biến `createdAt` hay người cập nhật thành thuộc tính bị bỏ qua. Nên dựng probe mới từ đầu vào tìm kiếm, thay vì dùng nguyên một entity đã đọc làm bộ lọc.

## 5. Giới hạn của QBE khi bộ lọc cần biểu thức

QBE không có API tổng quát để diễn đạt:

```text
totalSpent >= minimumSpent
AND totalSpent <= maximumSpent
```

Gán `totalSpent = 1000000` trong probe không có nghĩa là “từ một triệu trở lên”. Đó là một giá trị mẫu để so khớp theo khả năng của store. Transformer giá trị cũng không tự biến phép so khớp thành toán tử khoảng.

Với nhóm logic:

```text
tenantId = tenant hiện tại
AND status = ACTIVE
AND (fullName chứa tên OR city bằng thành phố)
```

`matchingAll()` tạo phép kết hợp AND cho các điều kiện được xét; `matchingAny()` chuyển sang OR. Không có một nhóm con tùy ý chỉ bằng cách đổi từ all sang any.

Đặc biệt, nếu đưa tenant và các điều kiện khác vào `matchingAny()`, kết quả có thể có ý nghĩa:

```text
tenantId khớp OR status khớp OR tên khớp OR thành phố khớp
```

Cấu trúc đó không giữ tenant như một điều kiện bắt buộc. Đừng dùng `matchingAny()` như một công tắc chung để làm các bộ lọc trở nên tùy chọn.

Thuộc tính lồng nhau như `address.city` là một vấn đề khác với nhóm logic lồng nhau. Store có thể hỗ trợ một số đường dẫn lồng nhau hoặc quan hệ đơn trị, nhưng điều đó không đồng nghĩa QBE hỗ trợ mọi join hoặc điều kiện trên phần tử collection.

Khi yêu cầu xuất hiện EXISTS trên collection, cùng một phần tử thỏa nhiều điều kiện, điều kiện phủ định hoặc aggregate, cần một API thể hiện chính xác ý định và được store hỗ trợ.

## 6. Querydsl: phù hợp với điều kiện động có cấu trúc rõ ràng

Querydsl biểu diễn điều kiện bằng các biểu thức có kiểu. Với Q-type, các thuộc tính được tham chiếu trong mã Java thay vì chỉ xuất hiện trong chuỗi tên đường dẫn.

Repository công bố khả năng nếu module đang dùng hỗ trợ:

```java
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.repository.CrudRepository;

public interface CustomerPredicateRepository
        extends CrudRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Một biểu thức cố định để minh họa nhóm logic:

```java
import com.querydsl.core.types.Predicate;

QCustomer customer = QCustomer.customer;

Predicate predicate = customer.tenantId.eq(currentTenantId)
        .and(customer.status.eq(CustomerStatus.ACTIVE))
        .and(
                customer.fullName.containsIgnoreCase("An")
                        .or(customer.city.eq("Huế"))
        );

Page<Customer> result = repository.findAll(predicate, pageable);
```

Dấu ngoặc được phản ánh qua cách ghép biểu thức: tenant và trạng thái nằm ngoài nhóm tên hoặc thành phố. Giá trị tenant được service bảo đảm hợp lệ trước khi dựng predicate.

Q-type giúp phát hiện nhiều lỗi tên thuộc tính và kiểu dữ liệu ở bước biên dịch, sau khi Q-type được sinh lại đúng. Nó không tự phát hiện một lỗi nghiệp vụ như dùng OR ở nơi phải dùng AND.

### Bộ dựng predicate cho yêu cầu nâng cao

Giả sử quy ước mới của màn hình là:

```text
Tenant luôn bắt buộc.
Status, mức chi tiêu tối thiểu và tối đa là bộ lọc tùy chọn.
Nếu có tên hoặc thành phố, yêu cầu khớp ít nhất một trong hai.
Nếu không có cả tên lẫn thành phố, bỏ nhóm đó.
```

Lưu ý đây là yêu cầu tên OR thành phố, khác yêu cầu mọi trường được cung cấp đều kết hợp AND của ví dụ QBE trước đó.

```java
import java.math.BigDecimal;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

static Predicate advancedPredicate(
        String currentTenantId,
        String fullName,
        String city,
        CustomerStatus status,
        BigDecimal minimumSpent,
        BigDecimal maximumSpent) {

    if (currentTenantId == null || currentTenantId.isBlank()) {
        throw new IllegalArgumentException("Thiếu phạm vi tenant");
    }
    if (minimumSpent != null && maximumSpent != null
            && minimumSpent.compareTo(maximumSpent) > 0) {
        throw new IllegalArgumentException(
                "Mức chi tiêu tối thiểu phải nhỏ hơn hoặc bằng tối đa");
    }

    QCustomer customer = QCustomer.customer;
    BooleanBuilder predicate = new BooleanBuilder(
            customer.tenantId.eq(currentTenantId));

    if (status != null) {
        predicate.and(customer.status.eq(status));
    }
    if (minimumSpent != null) {
        predicate.and(customer.totalSpent.goe(minimumSpent));
    }
    if (maximumSpent != null) {
        predicate.and(customer.totalSpent.loe(maximumSpent));
    }

    BooleanBuilder nameOrCity = new BooleanBuilder();
    if (fullName != null && !fullName.isBlank()) {
        nameOrCity.or(customer.fullName.containsIgnoreCase(fullName.trim()));
    }
    if (city != null && !city.isBlank()) {
        nameOrCity.or(customer.city.eq(city.trim()));
    }
    if (nameOrCity.hasValue()) {
        predicate.and(nameOrCity);
    }

    return predicate;
}
```

Builder được tạo mới cho mỗi yêu cầu vì `BooleanBuilder` có thể thay đổi. Không chia sẻ một builder mutable giữa nhiều người dùng hoặc nhiều thread rồi bổ sung điều kiện vào nó.

Import cần dùng là `com.querydsl.core.types.Predicate`, không phải `java.util.function.Predicate`. Predicate Java kiểm tra đối tượng trong bộ nhớ, còn predicate Querydsl mô tả điều kiện để store dịch thành truy vấn.

## 7. Querydsl có chi phí thiết lập và giới hạn tích hợp

So với một derived query method ngắn, Querydsl thường cần thêm:

- Dependency phù hợp với store và thế hệ API của dự án.
- Cấu hình sinh Q-type và đưa mã sinh vào quá trình biên dịch.
- Quy ước tổ chức các hàm dựng predicate.
- Kiểm tra khả năng dịch các biểu thức, thứ tự và quan hệ ở module cụ thể.

Đây là chi phí hợp lý khi nhiều bộ lọc cần được kết hợp, dùng lại và refactor. Với một truy vấn `findByEmail` ổn định, chi phí đó có thể không đem lại lợi ích tương xứng chỉ cho riêng truy vấn này.

`QuerydslPredicateExecutor` cũng không phải một query builder cho mọi nhu cầu. Các overload sẵn có không công bố đầy đủ mọi quyết định về join, fetch plan, aggregate, projection và truy vấn đếm tùy chỉnh.

Nếu cần sắp xếp khách hàng theo đơn hàng gần nhất, lấy DTO từ nhiều nguồn hoặc thực hiện báo cáo nhóm dữ liệu, có thể cần một repository implementation riêng sử dụng API truy vấn của store. Querydsl vẫn có thể được dùng trong implementation đó nếu phù hợp, nhưng khi ấy phạm vi công việc lớn hơn việc thêm một predicate vào executor.

Không nên suy luận rằng một biểu thức viết được bằng Querydsl sẽ tự thực thi được trên mọi Spring Data store. Cần xác nhận module thực tế hỗ trợ phần tích hợp nào.

## 8. Declared query method vẫn có thể xử lý bộ lọc tùy chọn

Một phương án khác là viết query method có truy vấn khai báo. Ví dụ dưới đây dành riêng cho Spring Data JPA và JPQL:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerJpaRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        select c from Customer c
        where c.tenantId = :tenantId
          and (:status is null or c.status = :status)
          and (:city is null or c.city = :city)
        """)
    Page<Customer> search(
            @Param("tenantId") String tenantId,
            @Param("status") CustomerStatus status,
            @Param("city") String city,
            Pageable pageable);
}
```

Ví dụ text block giả định Java 17 trở lên. Tenant được kiểm tra là đầu vào bắt buộc; `status` và `city` có quy ước rõ ràng là null thì bỏ điều kiện tương ứng.

Trong cách viết này, hành vi tùy chọn được khai báo trực tiếp trong truy vấn. Nó không xuất hiện tự động chỉ vì tham số Java có thể null.

Ưu điểm là người đọc thấy biểu thức ở một vị trí và không cần Q-type cho truy vấn này. Khi số điều kiện tăng, một câu query dài với nhiều nhánh `:param is null or ...` có thể khó bảo trì. Khả năng tối ưu kế hoạch thực thi cũng cần được quan sát trên dữ liệu thực tế, thay vì mặc định nó tương đương về chi phí với mọi cách dựng điều kiện động.

Ví dụ JPQL không áp dụng nguyên trạng cho MongoDB hoặc store không dùng JPA. Với truy vấn có join, group hay projection phức tạp, cần xác định thêm cách đếm tổng nếu trả Page; không dựa vào một quy tắc suy diễn count chung cho mọi query.

## 9. So sánh theo khả năng biểu diễn bộ lọc

| Nhu cầu | Derived query method | QBE | Querydsl |
| --- | --- | --- | --- |
| Một vài điều kiện bằng, ổn định | Thường rõ ràng, ít mã | Có thể dùng nhưng cần probe | Có thể dùng, đôi khi nhiều thiết lập hơn cần thiết |
| Nhiều thuộc tính tùy chọn kết hợp AND | Dễ tăng số tổ hợp method nếu liệt kê | Phù hợp khi giá trị mẫu và matcher đủ diễn đạt | Phù hợp, thêm predicate có điều kiện |
| Khoảng số hoặc thời gian | Có thể dùng từ khóa store hỗ trợ | Không phải mô hình biểu diễn khoảng tổng quát | Có toán tử tương ứng nếu store dịch được |
| Nhóm AND/OR có ngoặc | Tên method có giới hạn biểu đạt trực tiếp và dễ dài | Không có cây nhóm tùy ý trong matcher | Cấu trúc nhóm rõ qua biểu thức |
| Tìm null cụ thể | Có thể dùng method IsNull hoặc quy tắc tham số của store | Cần cấu hình null và đường dẫn cẩn thận | Thường thể hiện bằng isNull trên đường dẫn hỗ trợ |
| Thuộc tính lồng nhau | Tùy khả năng phân tích đường dẫn và store | Tùy mapping và store | Tùy mapping, Q-type và khả năng dịch |
| Điều kiện trên phần tử collection | Từ khóa và store quyết định khả năng | Không có ngữ nghĩa phần tử portable cho mọi store | Có khả năng biểu đạt rộng hơn, vẫn cần xác nhận hỗ trợ |
| Kiểm tra tên và kiểu biểu thức qua compiler | Tên method không có Q-type để kiểm tra | Probe có kiểu, đường dẫn matcher thường là chuỗi | Có khi dùng Q-type được sinh đúng |
| Chi phí thiết lập riêng | Thường thấp | Cần executor và store hỗ trợ | Cần tích hợp cùng quy trình sinh Q-type |

Declared query method không nằm trong cột đầu vì khả năng của nó khác derived query. Khi dùng `@Query`, phạm vi biểu đạt phụ thuộc ngôn ngữ truy vấn và module; đây có thể là lựa chọn phù hợp cho một truy vấn ổn định nhưng phức tạp.

Không chọn chỉ dựa vào số lượng field. Ba field có nhóm logic phức tạp có thể cần Querydsl hoặc query khai báo, trong khi mười field scalar tùy chọn kết hợp AND vẫn có thể phù hợp với QBE.

## 10. Thống nhất ý nghĩa của null và đầu vào không được cung cấp

Một bộ lọc thường có ba ý định:

| Ý định | Ví dụ với city |
| --- | --- |
| Không lọc | Chấp nhận mọi thành phố |
| Lọc theo giá trị | Chỉ Huế |
| Lọc theo null | Chỉ bản ghi chưa có thành phố |

Một field `String city` với null dùng cho cả “không truyền” và “tìm null” không đủ để phân biệt mọi trường hợp. Nếu nghiệp vụ cần cả ba, DTO bộ lọc phải biểu diễn được trạng thái riêng.

Cách xử lý khác nhau giữa các hướng:

- Với QBE, null mặc định bị bỏ qua; `withIncludeNullValues()` có thể đưa nhiều thuộc tính null vào điều kiện, không chỉ field đang quan tâm. Cần kết hợp ignored paths phù hợp.
- Với Querydsl, có thể không thêm predicate khi không lọc, dùng `eq(value)` cho giá trị và dùng `isNull()` khi thật sự muốn lọc null. Không truyền null vào `eq` để thay cho quyết định đó.
- Với derived query, không giả định null luôn bị bỏ qua. Chẳng hạn trong JPA, null ở tham số của phép bằng có thể được chuyển thành điều kiện `IS NULL` theo cơ chế suy diễn; muốn bỏ lọc cần thiết kế khác.
- Với `@Query`, ý nghĩa được quyết định bởi biểu thức đã khai báo. Mẫu `:city is null or c.city = :city` chủ động chọn null là không lọc.

Chuỗi rỗng và khoảng trắng cũng cần quy ước rõ. Chuẩn hóa đầu vào trước khi dựng điều kiện giúp các cách triển khai không có hành vi khác nhau ngoài ý muốn.

Không đồng nhất một field tài liệu không tồn tại với field có giá trị null nếu store phân biệt chúng. Khi yêu cầu cần kiểm tra sự tồn tại, phải dùng khả năng truy vấn phù hợp với cách lưu trữ.

## 11. Sort và Pageable không quyết định lựa chọn bộ lọc

Cả ba hướng đều có thể phối hợp thứ tự và phân trang khi method hoặc executor tương ứng hỗ trợ. Ví dụ một thứ tự chung:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("createdAt").descending()
                .and(Sort.by("id").descending()));
```

Sau đó dùng với một trong các lựa chọn:

```java
// Derived query method.
methodRepository.findByTenantIdAndStatusAndCity(
        currentTenantId, CustomerStatus.ACTIVE, "Huế", pageable);

// QBE.
exampleRepository.findAll(example, pageable);

// Querydsl.
predicateRepository.findAll(predicate, pageable);
```

Các biến `example` và `predicate` phải được dựng theo đúng yêu cầu cần so sánh. Không kết luận hai cách tương đương khi một bên dùng AND và bên kia dùng OR, hoặc một bên bỏ null còn bên kia tìm null.

`PageRequest` bắt đầu từ trang 0. Thứ tự có khóa phân định như id giúp phân định các bản ghi có cùng `createdAt`; nó không tạo snapshot giữa các request khi dữ liệu thay đổi.

Trả Page có thể cần thao tác đếm để tạo metadata. Không mặc định mọi lời gọi luôn có đúng hai câu lệnh, nhưng cần kiểm tra cả chi phí lấy content lẫn xác định tổng khi đánh giá hiệu năng.

Không đọc một Page rồi lọc thêm bằng Java mà giữ nguyên `totalElements`. Những điều kiện quyết định bản ghi nào được chọn cần được áp dụng trước khi phân trang. Việc đổi entity sang DTO một-một bằng `Page.map` là một thao tác khác và không tự thay đổi tập bản ghi khớp.

## 12. Không suy ra hiệu năng chỉ từ cách viết

Một derived method, một Example và một predicate Querydsl có thể dẫn tới các truy vấn rất gần nhau nếu cùng biểu diễn điều kiện, mapping và thứ tự. Querydsl không tự nhanh hơn vì biểu thức có kiểu; QBE cũng không tự đọc toàn bộ rồi lọc trong Java.

Các yếu tố cần xem xét gồm:

- Điều kiện có thể sử dụng chỉ mục nào.
- Phép tìm chứa chuỗi, không phân biệt hoa thường hoặc hàm trên cột được dịch thế nào.
- Truy vấn có join hoặc làm nhân dòng của bản ghi gốc không.
- Phân trang dùng offset lớn đến đâu và metadata tổng có tốn chi phí không.
- Dữ liệu cần trả là entity đầy đủ, projection hay kết quả aggregate.
- Việc đọc quan hệ lazy sau truy vấn có phát sinh nhiều truy vấn bổ sung không.

Các hình thức truy vấn không thay thế thiết kế chỉ mục, mapping hoặc chiến lược nạp dữ liệu. Khi cần tối ưu, quan sát truy vấn thực tế và kế hoạch thực thi của store, rồi xác định điểm cần thay đổi.

Nếu chuyển từ QBE sang Querydsl chỉ để hỗ trợ thêm một khoảng chi tiêu, cần kiểm tra tập kết quả, xử lý null và thứ tự có còn đúng yêu cầu. Không coi việc thay API là bằng chứng truy vấn đã tốt hơn về hiệu năng hoặc ngữ nghĩa.

## 13. Cách lựa chọn theo tình huống thực tế

| Tình huống | Lựa chọn ban đầu hợp lý | Khi nào cần nâng cấp |
| --- | --- | --- |
| Tra cứu theo email trong tenant | Derived query method ngắn | Cần thêm biểu thức động hoặc truy vấn đặc thù |
| Màn hình tùy chọn tên, thành phố, trạng thái, mọi điều kiện đều AND | QBE nếu store hỗ trợ | Xuất hiện khoảng, nhóm logic hoặc điều kiện phần tử |
| Tìm theo nhiều bộ lọc động, có khoảng và nhóm OR | Querydsl nếu tích hợp được store hỗ trợ | Cần điều khiển join, fetch hoặc count riêng |
| Một truy vấn nghiệp vụ phức tạp nhưng ổn định | Declared query method hoặc repository tùy chỉnh | Cấu trúc động tăng mạnh, query dài khó duy trì |
| Báo cáo aggregate, nhiều nguồn hoặc kết quả chuyên biệt | API truy vấn theo store và kiểu kết quả riêng | Yêu cầu tối ưu hoặc cấu trúc báo cáo thay đổi |

Một repository có thể cùng có `findByEmail`, QBE và một implementation tìm kiếm nâng cao nếu mỗi phần có vai trò rõ. Không cần chuyển mọi method đơn giản sang Querydsl chỉ vì một màn hình cần bộ lọc phức tạp.

Khi bộ lọc phát triển, có thể giữ nguyên DTO đầu vào và hợp đồng response, rồi thay bộ dựng điều kiện bên trong service hoặc repository. Phần cần giữ là ý nghĩa nghiệp vụ: phạm vi bắt buộc, điều kiện tùy chọn, cách xử lý null, nhóm logic và metadata phân trang.

Tránh để service âm thầm chọn một cách truy vấn khác với ý nghĩa khác chỉ vì thiếu field. Ví dụ, không dùng QBE matchingAll ở một nhánh và Querydsl OR ở nhánh còn lại mà không có quy ước sản phẩm tương ứng.

## 14. Những lỗi lựa chọn thường gặp

| Quyết định hoặc hiện tượng | Vấn đề | Cách điều chỉnh |
| --- | --- | --- |
| Tạo rất nhiều method cho mọi tổ hợp tùy chọn | Tên và nhánh chọn method khó duy trì | Đánh giá QBE hoặc bộ dựng predicate động |
| Dùng QBE để tìm từ một mức tiền trở lên | Giá trị mẫu không phải toán tử khoảng | Dùng derived keyword, Querydsl hoặc query khai báo phù hợp |
| Đổi matchingAll thành matchingAny để có nhóm OR | Mất cấu trúc điều kiện bắt buộc và nhóm con | Viết biểu thức có nhóm rõ ràng |
| Cho rằng query method luôn chỉ là tên method | Bỏ qua khả năng truy vấn khai báo | Tách derived query và declared query khi đánh giá |
| Chọn Querydsl chỉ vì nghĩ luôn nhanh hơn | Cách viết không quyết định toàn bộ truy vấn và kế hoạch | So sánh truy vấn thực tế với cùng ngữ nghĩa |
| Dùng null như cùng một tín hiệu ở mọi API | QBE, derived query và biểu thức có thể hiểu khác nhau | Quy định ba trạng thái bộ lọc nếu cần |
| Chia sẻ BooleanBuilder giữa các request | Điều kiện mutable có thể bị trộn | Tạo builder mới cho mỗi lần dựng predicate |
| Dùng entity đã tải làm probe tìm kiếm | Metadata và giá trị mặc định tham gia ngoài ý muốn | Dựng probe riêng từ bộ lọc đã kiểm soát |
| Có QuerydslPredicateExecutor nên cho rằng mọi join đều tùy biến được | Executor chỉ công bố một tập thao tác | Tạo repository implementation phù hợp khi cần |

## 15. Tự đánh giá một nhu cầu bộ lọc

Trước khi chọn cách truy vấn, hãy viết yêu cầu thành một biểu thức cụ thể và xác định:

1. Điều kiện nào bắt buộc, điều kiện nào chỉ xuất hiện khi có đầu vào?
2. Các điều kiện kết hợp toàn bộ bằng AND hay có nhóm OR lồng nhau?
3. Cần so khớp giá trị, khoảng, null, sự tồn tại hay điều kiện trên phần tử collection?
4. Store và repository đang dùng thực sự hỗ trợ những abstraction nào?
5. Cần entity, projection hay kết quả aggregate; có phân trang và tổng số không?
6. Khi thêm một bộ lọc mới, cách triển khai hiện tại có còn dễ đọc và giữ đúng ngữ nghĩa không?

Với điều kiện ổn định và tên ngắn, derived query method thường đủ rõ. Với các thuộc tính tùy chọn có thể mô tả bằng probe và matcher, QBE là một lựa chọn gọn. Với bộ lọc động cần khoảng và nhóm biểu thức, Querydsl có thể làm cấu trúc điều kiện dễ kiểm tra hơn khi store hỗ trợ. Khi cần một truy vấn đặc thù hoặc toàn quyền điều khiển cấu trúc truy vấn, declared query và repository implementation riêng vẫn là những lựa chọn cần cân nhắc.
