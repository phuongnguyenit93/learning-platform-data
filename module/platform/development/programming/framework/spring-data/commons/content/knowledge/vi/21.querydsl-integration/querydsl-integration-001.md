# Predicate có kiểu và các lớp Q-type

Khi viết một bộ lọc động, chuỗi như `"age"` hoặc `"customer.address.city"` rất dễ bị gõ sai và khó được trình biên dịch kiểm tra. Querydsl cung cấp một cách biểu diễn khác: thuộc tính miền được truy cập qua các đối tượng đường dẫn có kiểu, và điều kiện truy vấn được tạo thành cây biểu thức Java.

Bài học thuộc chương **Tích hợp Querydsl** của **SPRING_DATA_COMMONS**. Trọng tâm là hiểu **predicate có kiểu**, vai trò của các lớp **Q-type** và cách đưa predicate vào abstraction repository của Spring Data. Ví dụ chọn Spring Data JPA để minh họa cách thực thi; khả năng hỗ trợ ở module lưu trữ khác cần được xác nhận riêng.

Sau bài học, bạn có thể:

- Giải thích Q-type đại diện cho metadata truy vấn thay vì dữ liệu của một bản ghi.
- Tạo điều kiện chuỗi, số, Boolean và enum qua các đường dẫn có kiểu.
- Ghép AND, OR và NOT với nhóm điều kiện rõ ràng.
- Tạo bộ lọc tùy chọn bằng `BooleanBuilder`.
- Phân biệt kiểm tra kiểu lúc biên dịch với tính đúng nghiệp vụ và khả năng thực thi ở store.

## 1. Predicate trong Querydsl là một biểu thức truy vấn

Giả sử có kiểu miền `Customer` với các thuộc tính sau:

| Thuộc tính | Kiểu Java | Ý nghĩa |
|---|---|---|
| `id` | `Long` | Định danh |
| `displayName` | `String` | Tên hiển thị |
| `email` | `String` | Địa chỉ email |
| `age` | `Integer` | Tuổi |
| `active` | `Boolean` | Trạng thái hoạt động |
| `status` | `CustomerStatus` | Trạng thái nghiệp vụ |
| `creditLimit` | `BigDecimal` | Hạn mức tín dụng |
| `address` | `Address` | Giá trị địa chỉ có thuộc tính `city` |

Enum minh họa:

~~~java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
~~~

Nếu Q-type tương ứng đã được sinh, có thể viết:

~~~java
import com.querydsl.core.types.dsl.BooleanExpression;

QCustomer customer = QCustomer.customer;

BooleanExpression predicate = customer.age.goe(18)
    .and(customer.active.isTrue());
~~~

Điều kiện này biểu đạt:

~~~text
age >= 18
AND active = true
~~~

Nó chưa phải danh sách kết quả và cũng chưa tự gửi truy vấn tới cơ sở dữ liệu. Querydsl đang xây dựng một cây biểu thức để thành phần thực thi chuyển sang truy vấn phù hợp.

Luồng xử lý:

~~~text
Mô hình miền
    |
    | sinh metadata truy vấn
    v
QCustomer và các đường dẫn có kiểu
    |
    | tạo biểu thức bằng API Java
    v
Predicate
    |
    | repository hoặc query API thực thi
    v
Truy vấn theo module và store
    |
    v
Kết quả
~~~

### 1.1. Không nhầm với java.util.function.Predicate

Hai kiểu sau có cùng tên nhưng vai trò khác nhau:

| Kiểu | Vai trò |
|---|---|
| `com.querydsl.core.types.Predicate` | Biểu thức truy vấn để Querydsl và adapter xử lý |
| `java.util.function.Predicate<T>` | Hàm Java nhận một đối tượng và trả về boolean |

Ví dụ lọc một Java Stream:

~~~java
java.util.function.Predicate<Customer> adult =
    customer -> customer.getAge() != null
        && customer.getAge() >= 18;
~~~

Lambda này kiểm tra một đối tượng đã có trong bộ nhớ. Nó không phải predicate mà `QuerydslPredicateExecutor` nhận.

Ví dụ đúng cho Querydsl:

~~~java
com.querydsl.core.types.Predicate adult =
    QCustomer.customer.age.goe(18);
~~~

Nếu IDE tự import nhầm `java.util.function.Predicate`, hãy sửa import; không chuyển thành lọc dữ liệu trong bộ nhớ chỉ để làm hết lỗi kiểu.

## 2. Q-type là gì?

Theo quy ước thông dụng, kiểu miền `Customer` có lớp truy vấn `QCustomer`; `Address` có thể có `QAddress`. Lớp này thường được công cụ sinh mã tạo ra từ metadata của mô hình.

Một phần Q-type có thể trông như sau:

~~~java
// Minh họa cấu trúc đã rút gọn.
// Đây không phải file cần tự viết thay cho mã được sinh.

public class QCustomer extends EntityPathBase<Customer> {

    public static final QCustomer customer =
        new QCustomer("customer");

    public final StringPath displayName =
        createString("displayName");

    public final StringPath email =
        createString("email");

    public final NumberPath<Integer> age =
        createNumber("age", Integer.class);

    public final BooleanPath active =
        createBoolean("active");

    public final EnumPath<CustomerStatus> status =
        createEnum("status", CustomerStatus.class);

    public QCustomer(String variable) {
        super(Customer.class, PathMetadataFactory.forVariable(variable));
    }
}
~~~

Các kiểu như `EntityPathBase`, `StringPath`, `NumberPath`, `BooleanPath` và `EnumPath` thuộc API Querydsl. Mã sinh thực tế có thể có thêm constructor, metadata, đường dẫn định danh, quan hệ và cấu hình khởi tạo đường dẫn.

Bảng đối chiếu:

| Thành phần | Đại diện cho |
|---|---|
| `Customer` | Kiểu dữ liệu miền |
| Một đối tượng `Customer` | Dữ liệu của một khách hàng |
| `QCustomer` | Kiểu metadata truy vấn cho Customer |
| `QCustomer.customer` | Một đường dẫn gốc với tên biến truy vấn |
| `QCustomer.customer.age` | Đường dẫn thuộc tính tuổi, có kiểu số |
| `QCustomer.customer.age.goe(18)` | Biểu thức so sánh tuổi |

`QCustomer.customer` không chứa thông tin của một khách hàng cụ thể. Nó không có “tuổi hiện tại” để đọc; `age` là đường dẫn dùng để tạo biểu thức.

### 2.1. Tên biến truy vấn không phải tên bảng

~~~java
QCustomer buyer = new QCustomer("buyer");
~~~

Chuỗi `"buyer"` là tên biến cho đường dẫn truy vấn. Nó không tự đổi tên entity, bảng hoặc collection.

Tên biến hữu ích khi một truy vấn đầy đủ cần phân biệt nhiều vai trò của cùng một kiểu miền. Nhưng một đường dẫn gốc mới không tự đăng ký nguồn dữ liệu hoặc join trong repository. Khi dùng `QuerydslPredicateExecutor`, nên bắt đầu bằng đường dẫn gốc thông dụng mà integration sử dụng; truy vấn nhiều alias cần được thiết kế trong query API phù hợp.

### 2.2. Không sửa trực tiếp mã Q-type được sinh

Nếu thêm hoặc đổi tên thuộc tính miền, cập nhật mô hình rồi sinh lại Q-type bằng quy trình của dự án.

Sửa tay `QCustomer` tạo ra sự lệch giữa metadata truy vấn và mô hình. Lần sinh mã tiếp theo cũng có thể ghi đè thay đổi.

Nếu thuộc tính `displayName` đổi thành `fullName` và Q-type được cập nhật đúng, những vị trí còn gọi `customer.displayName` sẽ không biên dịch. Đây là một lợi ích quan trọng so với việc giữ tên thuộc tính trong chuỗi.

## 3. Vì sao gọi là có kiểu?

Đường dẫn giữ kiểu của thuộc tính và cung cấp các toán tử tương ứng.

| Thuộc tính | Đường dẫn thường gặp | Ví dụ điều kiện |
|---|---|---|
| `String displayName` | `StringPath` | `containsIgnoreCase("an")` |
| `Integer age` | `NumberPath<Integer>` | `goe(18)`, `loe(65)` |
| `BigDecimal creditLimit` | `NumberPath<BigDecimal>` | `goe(new BigDecimal("1000"))` |
| `Boolean active` | `BooleanPath` | `isTrue()`, `isFalse()` |
| `CustomerStatus status` | `EnumPath<CustomerStatus>` | `eq(CustomerStatus.ACTIVE)` |
| Thuộc tính có thể null | Đường dẫn tương ứng | `isNull()`, `isNotNull()` |

Ví dụ:

~~~java
BooleanExpression predicate = customer.displayName
    .containsIgnoreCase("an")
    .and(customer.age.goe(18))
    .and(customer.creditLimit.goe(new BigDecimal("1000")))
    .and(customer.status.eq(CustomerStatus.ACTIVE));
~~~

Các biểu thức sau minh họa lỗi kiểu và không dùng làm mã chạy:

~~~java
// Sai: đường dẫn số không có toán tử tìm chuỗi con này.
customer.age.contains("18");

// Sai: age là Integer, không phải String.
customer.age.eq("18");

// Sai: status cần CustomerStatus, không phải tên enum dạng chuỗi.
customer.status.eq("ACTIVE");
~~~

Trình biên dịch giúp phát hiện sai thuộc tính hoặc sai loại toán tử trước khi chạy truy vấn.

Tuy nhiên, nó không phát hiện được mọi sai lầm:

~~~java
customer.age.goe(180);
~~~

Biểu thức này hợp lệ về kiểu, nhưng có thể sai nghiệp vụ nếu người viết định nhập tuổi tối thiểu 18.

## 4. Predicate, BooleanExpression và BooleanBuilder

Ba kiểu thường xuất hiện cùng nhau:

| Kiểu | Vai trò |
|---|---|
| `Predicate` | Hợp đồng chung cho biểu thức điều kiện Querydsl |
| `BooleanExpression` | Biểu thức Boolean có API ghép `and`, `or`, `not` |
| `BooleanBuilder` | Bộ tích lũy điều kiện có thể thay đổi khi xây truy vấn động |

Có thể gán `BooleanExpression` cho biến `Predicate`:

~~~java
import com.querydsl.core.types.Predicate;
import com.querydsl.core.types.dsl.BooleanExpression;

BooleanExpression adult = customer.age.goe(18);
Predicate predicate = adult;
~~~

`BooleanExpression` phù hợp khi đã có một điều kiện nền rõ ràng. Các phép ghép trả về biểu thức mới:

~~~java
BooleanExpression adult = customer.age.goe(18);

// Không giữ lại biểu thức mới nên adult không được bổ sung điều kiện.
adult.and(customer.active.isTrue());
~~~

Cách đúng:

~~~java
BooleanExpression activeAdult =
    adult.and(customer.active.isTrue());
~~~

Ngược lại, `BooleanBuilder` tích lũy trạng thái:

~~~java
import com.querydsl.core.BooleanBuilder;

BooleanBuilder builder = new BooleanBuilder();
builder.and(customer.age.goe(18));
builder.and(customer.active.isTrue());
~~~

Tạo builder riêng cho từng lần xây bộ lọc. Không dùng một builder dùng chung có thể bị nhiều request bổ sung điều kiện lẫn nhau.

## 5. Ghép AND, OR và NOT với nhóm điều kiện rõ ràng

Giả sử yêu cầu là:

~~~text
Đang hoạt động
AND
(tên chứa từ khóa OR email chứa từ khóa)
~~~

Viết phần tìm từ khóa thành một nhóm:

~~~java
BooleanExpression keywordMatches = customer.displayName
    .containsIgnoreCase("an")
    .or(customer.email.containsIgnoreCase("an"));

BooleanExpression predicate = customer.active.isTrue()
    .and(keywordMatches);
~~~

So sánh với:

~~~java
BooleanExpression differentPredicate = customer.active.isTrue()
    .and(customer.displayName.containsIgnoreCase("an"))
    .or(customer.email.containsIgnoreCase("an"));
~~~

Biểu thức thứ hai có cấu trúc:

~~~text
(đang hoạt động AND tên khớp)
OR email khớp
~~~

Một khách hàng không hoạt động vẫn có thể được chọn nếu email khớp.

Không suy ra nhóm điều kiện chỉ từ thứ tự các dòng. Các lời gọi phương thức đang tạo một cây biểu thức; biến trung gian và dấu ngoặc trong biểu thức con giúp thể hiện ý định.

Ví dụ NOT:

~~~java
BooleanExpression notClosed =
    customer.status.eq(CustomerStatus.CLOSED).not();
~~~

Biểu thức này không mặc nhiên có nghĩa “bao gồm cả trạng thái null”. Quy tắc null vẫn phụ thuộc phép so sánh mà store thực hiện.

## 6. Null: đường dẫn có kiểu không tự quyết định nghiệp vụ

### 6.1. Dùng isNull, không dùng eq(null)

Để tìm email null:

~~~java
BooleanExpression missingEmail = customer.email.isNull();
~~~

Không viết:

~~~java
customer.email.eq((String) null);
~~~

Với API so sánh tương ứng, `eq(null)` không phải cách diễn đạt null được phép; hãy dùng `isNull()`.

Cũng không viết:

~~~java
if (customer.email == null) {
    // ...
}
~~~

Biểu thức Java trên đang kiểm tra đối tượng đường dẫn, không kiểm tra dữ liệu email trong store.

### 6.2. Bỏ qua bộ lọc và tìm giá trị null là hai việc khác nhau

Giả sử người dùng không chọn trạng thái hoạt động:

~~~java
Boolean activeFilter = null;

if (activeFilter != null) {
    builder.and(customer.active.eq(activeFilter));
}
~~~

Ở đây, null có nghĩa **không thêm điều kiện**. Nó khác với:

~~~java
builder.and(customer.active.isNull());
~~~

Điều kiện thứ hai chủ động tìm dữ liệu có trạng thái null.

Một DTO dùng `Boolean` có thể phân biệt ba lựa chọn: không lọc, true và false. Nếu dùng `boolean`, giá trị mặc định false có thể làm mất khả năng biểu diễn “không chọn”.

### 6.3. NOT và khác nhau có thể không chọn giá trị null

Trong môi trường SQL, các phép so sánh với null chịu quy tắc logic ba giá trị. Vì vậy:

~~~java
customer.email.ne("blocked@example.com");
~~~

không đồng nghĩa một cách tổng quát với “mọi bản ghi ngoại trừ email này, kể cả null”.

Nếu nghiệp vụ muốn cho phép null, thể hiện rõ:

~~~java
BooleanExpression allowedEmail = customer.email
    .ne("blocked@example.com")
    .or(customer.email.isNull());
~~~

Khi chuyển sang store khác, cần xác nhận cách null và trường không tồn tại được xử lý. Tính có kiểu của đường dẫn không chuẩn hóa mọi khác biệt giữa các kho dữ liệu.

## 7. Xây bộ lọc động bằng BooleanBuilder

Màn hình tìm khách hàng có các tiêu chí tùy chọn:

- Từ khóa trong tên hoặc email.
- Tuổi tối thiểu và tối đa.
- Trạng thái hoạt động.
- Trạng thái nghiệp vụ.
- Hạn mức tín dụng tối thiểu.

Ví dụ dưới đây tạo predicate riêng cho mỗi lần tìm kiếm và yêu cầu có ít nhất một bộ lọc.

~~~java
import java.math.BigDecimal;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;
import com.querydsl.core.types.dsl.BooleanExpression;

public final class CustomerPredicates {

    private CustomerPredicates() {
    }

    public static Predicate forSearch(
            String keyword,
            Integer minAge,
            Integer maxAge,
            Boolean active,
            CustomerStatus status,
            BigDecimal minimumCreditLimit) {

        if (minAge != null && minAge < 0) {
            throw new IllegalArgumentException(
                "Tuổi tối thiểu không được âm"
            );
        }

        if (maxAge != null && maxAge < 0) {
            throw new IllegalArgumentException(
                "Tuổi tối đa không được âm"
            );
        }

        if (minAge != null && maxAge != null && minAge > maxAge) {
            throw new IllegalArgumentException(
                "Tuổi tối thiểu không được lớn hơn tuổi tối đa"
            );
        }

        if (minimumCreditLimit != null
                && minimumCreditLimit.signum() < 0) {
            throw new IllegalArgumentException(
                "Hạn mức tối thiểu không được âm"
            );
        }

        QCustomer customer = QCustomer.customer;
        BooleanBuilder builder = new BooleanBuilder();

        String normalizedKeyword = trimToNull(keyword);
        if (normalizedKeyword != null) {
            BooleanExpression keywordMatches =
                customer.displayName
                    .containsIgnoreCase(normalizedKeyword)
                    .or(customer.email
                        .containsIgnoreCase(normalizedKeyword));

            builder.and(keywordMatches);
        }

        if (minAge != null) {
            builder.and(customer.age.goe(minAge));
        }

        if (maxAge != null) {
            builder.and(customer.age.loe(maxAge));
        }

        if (active != null) {
            builder.and(customer.active.eq(active));
        }

        if (status != null) {
            builder.and(customer.status.eq(status));
        }

        if (minimumCreditLimit != null) {
            builder.and(
                customer.creditLimit.goe(minimumCreditLimit)
            );
        }

        if (!builder.hasValue()) {
            throw new IllegalArgumentException(
                "Cần ít nhất một bộ lọc"
            );
        }

        return builder;
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
~~~

Những quyết định nghiệp vụ trong ví dụ:

| Tình huống | Chính sách |
|---|---|
| Từ khóa null hoặc chỉ có khoảng trắng được trim xử lý | Bỏ qua điều kiện từ khóa |
| Khoảng tuổi không hợp lệ | Từ chối đầu vào |
| `active = null` | Không lọc trạng thái hoạt động |
| `active = false` | Thêm điều kiện false |
| Không có bộ lọc nào | Từ chối để tránh tìm toàn bộ ngoài ý muốn |

Chính sách “phải có bộ lọc” thuộc ứng dụng, không phải quy tắc bắt buộc của Querydsl. Nếu màn hình cho phép xem toàn bộ, hãy triển khai đường đọc đó một cách chủ động.

Hàm `trimToNull` dùng `trim()` nên không phải giải pháp xử lý mọi khoảng trắng Unicode. Nó cũng không bỏ dấu tiếng Việt hoặc chuẩn hóa toàn bộ văn bản.

### 7.1. Predicate nhận được có cấu trúc gì?

Lời gọi:

~~~java
Predicate predicate = CustomerPredicates.forSearch(
    " an ",
    18,
    65,
    Boolean.TRUE,
    CustomerStatus.ACTIVE,
    new BigDecimal("1000")
);
~~~

tạo ý định:

~~~text
(displayName chứa "an" không phân biệt hoa/thường
 OR email chứa "an" không phân biệt hoa/thường)
AND age >= 18
AND age <= 65
AND active = true
AND status = ACTIVE
AND creditLimit >= 1000
~~~

Kiểu dữ liệu của từng điều kiện được kiểm tra qua Q-type. Các quyết định như khoảng tuổi được phép hay yêu cầu tối thiểu một bộ lọc vẫn do ứng dụng xác định.

### 7.2. Biểu thức nhỏ có thể tái sử dụng

Có thể tách quy tắc miền thành các hàm:

~~~java
public static BooleanExpression activeAdults(QCustomer customer) {
    return customer.active.isTrue()
        .and(customer.age.goe(18));
}

public static BooleanExpression hasCreditLimitAtLeast(
        QCustomer customer,
        BigDecimal amount) {

    if (amount == null || amount.signum() < 0) {
        throw new IllegalArgumentException(
            "Hạn mức phải có giá trị không âm"
        );
    }

    return customer.creditLimit.goe(amount);
}
~~~

Ghép chúng:

~~~java
BooleanExpression predicate =
    activeAdults(QCustomer.customer)
        .and(hasCreditLimitAtLeast(
            QCustomer.customer,
            new BigDecimal("1000")
        ));
~~~

Truyền đường dẫn gốc vào hàm giúp nhìn rõ biểu thức đang áp dụng cho root nào. Đừng ghép các biểu thức dùng nhiều root hoặc alias khác nhau nếu truy vấn thực thi chưa khai báo các root đó.

## 8. Đưa predicate vào Spring Data repository

Với Spring Data JPA và cấu hình tích hợp Querydsl tương thích:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

`JpaRepository` cung cấp các thao tác repository cho JPA. `QuerydslPredicateExecutor` bổ sung các điểm thực thi predicate.

Một số phương thức thông dụng:

| Phương thức | Ý nghĩa |
|---|---|
| `findOne(predicate)` | Tìm tối đa một kết quả theo hợp đồng phương thức |
| `findAll(predicate)` | Lấy các bản ghi khớp |
| `findAll(predicate, pageable)` | Lọc và phân trang |
| `count(predicate)` | Đếm bản ghi khớp |
| `exists(predicate)` | Kiểm tra có bản ghi khớp |

`findOne` trả về `Optional` trong API tương ứng và không phải cách “lấy đại bản ghi đầu tiên”. Nếu có nhiều kết quả, có thể xảy ra lỗi kích thước kết quả không đúng. Dùng nó khi điều kiện thực sự xác định không quá một bản ghi.

Ví dụ lấy một trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Predicate predicate = CustomerPredicates.forSearch(
    "an",
    18,
    null,
    Boolean.TRUE,
    null,
    null
);

Page<Customer> page = repository.findAll(
    predicate,
    PageRequest.of(
        0,
        20,
        Sort.by("id").ascending()
    )
);
~~~

Bộ lọc nằm trong predicate; kích thước trang và thứ tự nằm trong `Pageable`.

Ở ví dụ này, `Sort.by("id")` vẫn dùng tên thuộc tính dạng chuỗi. Tính có kiểu của predicate không làm mọi phần còn lại trong lời gọi tự trở thành có kiểu. Querydsl cũng có `OrderSpecifier` từ đường dẫn như `customer.id.asc()`; lựa chọn overload thực thi phải phù hợp API repository đang dùng.

## 9. Q-type được tạo và đưa vào dự án như thế nào?

Trong ví dụ JPA, Q-type thường được sinh bởi annotation processor từ metadata entity.

Quy trình khái quát:

~~~text
Mã nguồn Customer, Address và các kiểu liên quan
        |
        | annotation processing
        v
Mã nguồn sinh: QCustomer, QAddress...
        |
        | được đưa vào quá trình biên dịch
        v
Mã ứng dụng tham chiếu QCustomer có thể biên dịch
~~~

Cần phân biệt:

- **Thư viện API Querydsl:** cung cấp kiểu biểu thức như `Predicate`, `StringPath` và `BooleanExpression`.
- **Phần tích hợp store:** hỗ trợ chuyển và thực thi truy vấn với công nghệ lưu trữ được chọn.
- **Công cụ sinh mã:** tạo các lớp Q-type từ mô hình.
- **Cấu hình build và IDE:** quyết định processor có chạy và mã sinh có được nhận diện hay không.

Chỉ thêm một thư viện có `Predicate` chưa đủ để tạo `QCustomer`.

### 9.1. Kiểm tra tương thích của cấu hình sinh mã

Trước khi kết luận annotation processor hỏng, cần xác nhận:

1. Mô hình dùng annotation nào và có được processor tương ứng nhận diện không?
2. Hệ annotation persistence của dự án là `javax.persistence` hay `jakarta.persistence`?
3. Artifact và cấu hình processor có phù hợp hệ annotation đó không?
4. Phiên bản runtime Querydsl và phần sinh mã có tương thích không?
5. Mã sinh có được đưa vào source path của quá trình biên dịch không?
6. IDE có nhận đúng cấu hình annotation processing và thư mục mã sinh không?

Không chọn cấu hình chỉ từ tên `QCustomer`. Các dự án khác module, hệ annotation hoặc dòng phiên bản có thể cần cấu hình khác.

Bài học không cố định tọa độ dependency hay số phiên bản cho mọi ứng dụng. Cấu hình thực tế phải theo bộ Spring Data, module store và Querydsl của dự án.

### 9.2. Lỗi sinh mã khác lỗi thực thi

| Hiện tượng | Lớp vấn đề thường cần kiểm tra |
|---|---|
| Không tìm thấy `QCustomer` khi biên dịch | Processor, annotation mô hình, source path mã sinh |
| Có Q-type nhưng thiếu thuộc tính vừa thêm | Mã sinh cũ, annotation hoặc cấu hình sinh mã |
| IDE báo lỗi nhưng build nhận diện được lớp | Đồng bộ mô hình build và thư mục mã sinh trong IDE |
| Biên dịch được nhưng không khởi tạo được repository | Integration, dependency hoặc metadata mà adapter cần |
| Repository khởi tạo được nhưng truy vấn sai kết quả | Predicate, nhóm điều kiện, ánh xạ và hành vi store |
| Truy vấn đúng nhưng chậm | Truy vấn sinh ra, chỉ mục, dữ liệu và cách lấy kết quả |

Chia đúng lớp lỗi giúp tránh sửa biểu thức truy vấn trong khi nguyên nhân thực tế là processor chưa tạo Q-type.

## 10. Thuộc tính lồng nhau và giới hạn của predicate

Nếu mô hình và mã sinh có đường dẫn tương ứng:

~~~java
BooleanExpression inCity =
    QCustomer.customer.address.city.eq("Ha Noi");
~~~

Biểu thức có kiểu giúp truy cập đúng thuộc tính của `Address`. Nó không tự trả lời mọi câu hỏi về cách store thực thi:

- `Address` là giá trị nhúng hay một quan hệ?
- Nếu không có address thì bản ghi được xét ra sao?
- Adapter tạo join hoặc đường dẫn tài liệu như thế nào?
- Kiểu so sánh chuỗi thực tế có phân biệt hoa/thường và dấu không?

Với collection, Querydsl có các loại đường dẫn và toán tử riêng tùy mô hình. Nhưng một predicate không thay thế toàn bộ cấu trúc của một truy vấn có join, subquery, projection hoặc aggregate.

Nếu yêu cầu cần kiểm soát rõ nguồn dữ liệu, alias, join, fetch hoặc phép tổng hợp, một repository fragment dùng query API thích hợp có thể phù hợp hơn chỉ gọi `QuerydslPredicateExecutor`.

Không suy ra “có thể xây biểu thức Java” thành “mọi biểu thức đều thực thi được qua mọi executor”.

## 11. Những gì tính có kiểu chưa bảo đảm

| Có thể được kiểm tra tốt qua Q-type | Vẫn cần thiết kế hoặc kiểm chứng |
|---|---|
| Tên thuộc tính được sinh thành thành viên Java | Metadata sinh có đồng bộ mô hình không |
| Kiểu đối số của phép so sánh | Giá trị có hợp lệ về nghiệp vụ không |
| Toán tử có phù hợp đường dẫn không | Store có hỗ trợ cách chuyển biểu thức đó không |
| Cấu trúc ghép biểu thức qua API | Nhóm AND/OR có đúng yêu cầu không |
| Loại enum được truyền vào | Quy tắc chuyển enum và dữ liệu lưu có đúng không |

Một số giới hạn cụ thể:

### 11.1. Không tự bảo đảm chính sách truy cập

Nếu truy vấn phải giới hạn theo phạm vi dữ liệu của người dùng, điều kiện bắt buộc đó phải được giữ ở nhóm ngoài cùng thích hợp:

~~~text
điều kiện truy cập bắt buộc
AND
(các bộ lọc tùy chọn)
~~~

Một phép OR đặt sai có thể mở rộng tập dữ liệu dù biểu thức hoàn toàn hợp lệ về kiểu.

### 11.2. Không tự giải quyết tìm không dấu

`containsIgnoreCase("da nang")` không phải một cam kết chung rằng dữ liệu `"Đà Nẵng"` sẽ khớp. Bỏ qua hoa/thường khác với bỏ dấu, chuẩn hóa Unicode và các quy tắc collation của store.

### 11.3. Không tự tạo chỉ mục

Một điều kiện `containsIgnoreCase` hợp lệ có thể dẫn tới truy vấn đọc nhiều dữ liệu. Q-type không tạo chỉ mục và không chứng minh truy vấn sử dụng chỉ mục hiệu quả.

### 11.4. Không thay thế ánh xạ và dữ liệu đúng

Q-type phản ánh mô hình Java. Nếu schema, converter, dữ liệu cũ hoặc hệ annotation không nhất quán, truy vấn vẫn có thể lỗi hoặc cho kết quả khác dự kiến.

### 11.5. Không nên quay lại chuỗi động khi đã có đường dẫn ổn định

Querydsl cũng có công cụ tạo đường dẫn động bằng tên chuỗi. Chúng hữu ích khi yêu cầu thực sự động, nhưng bỏ bớt lợi ích kiểm tra tên thuộc tính khi biên dịch.

Khi trường truy vấn đã biết, ưu tiên đường dẫn được sinh như:

~~~java
customer.displayName.containsIgnoreCase(keyword);
~~~

thay vì tự xây đường dẫn từ chuỗi `"displayName"` ở khắp nơi.

## 12. Đối chiếu ngắn với các cách tạo điều kiện khác

| Cách tạo điều kiện | Điểm thuận tiện | Điểm cần cân nhắc |
|---|---|---|
| Derived query | Gọn với điều kiện cố định, dễ đọc khi tên phương thức ngắn | Nhiều tổ hợp tùy chọn có thể làm API repository phình lớn |
| Query by Example | Dễ dùng khi lọc theo giá trị mẫu | Khó diễn đạt nhóm điều kiện hoặc so sánh khoảng ngoài phạm vi hỗ trợ |
| Querydsl Predicate | Đường dẫn có kiểu, ghép điều kiện động rõ | Cần Q-type, cấu hình sinh mã và integration store tương thích |
| Query API đầy đủ | Kiểm soát nguồn dữ liệu, join và cấu trúc truy vấn | Cần triển khai và duy trì nhiều chi tiết hơn |

Ví dụ yêu cầu:

~~~text
active = true
AND age >= 18
AND (displayName chứa q OR email chứa q)
~~~

là trường hợp phù hợp để thấy lợi ích của predicate có kiểu: các toán tử theo kiểu thuộc tính, nhóm OR rõ và các điều kiện tùy chọn dễ ghép.

Tuy nhiên, nếu chỉ cần tìm một khách hàng theo email duy nhất, một phương thức repository đơn giản có thể đã diễn đạt đủ yêu cầu. Không cần áp dụng Querydsl cho mọi thao tác đọc chỉ vì dự án đã có Q-type.

## 13. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Import nhầm `Predicate` | IDE chọn `java.util.function.Predicate` | Dùng `com.querydsl.core.types.Predicate` cho truy vấn Querydsl |
| `QCustomer` không tồn tại | Chưa sinh mã hoặc chưa đưa mã sinh vào quá trình biên dịch | Kiểm tra annotation processor và cấu hình source path |
| Q-type không có trường mới | Metadata sinh chưa cập nhật | Đồng bộ mã sinh với mô hình bằng quy trình build của dự án |
| Điều kiện AND không được giữ | Bỏ kết quả trả về của `BooleanExpression.and` | Gán biểu thức mới hoặc nối chuỗi lời gọi |
| Bộ lọc bị lẫn giữa các request | Dùng chung `BooleanBuilder` có trạng thái | Tạo builder riêng cho mỗi lần xây điều kiện |
| Khách không hoạt động vẫn xuất hiện | OR chưa được nhóm đúng | Tạo biểu thức con cho nhóm tìm từ khóa |
| Lỗi với `eq(null)` | Dùng sai cách diễn đạt null | Dùng `isNull()` hoặc bỏ qua bộ lọc theo chính sách |
| Null bị coi là false | DTO dùng primitive hoặc logic ép mặc định | Dùng trạng thái đầu vào phù hợp với nghiệp vụ |
| Predicate biên dịch nhưng thực thi lỗi | Sai root, mapping hoặc thiếu hỗ trợ module | Kiểm tra truy vấn, metadata và integration |
| `findOne` lỗi khi có nhiều bản ghi | Hiểu nhầm là lấy phần tử đầu | Dùng điều kiện duy nhất hoặc API lấy nhiều kết quả |
| Query đúng nhưng chậm | Phép so sánh, dữ liệu hoặc chỉ mục chưa phù hợp | Quan sát truy vấn và kế hoạch thực thi |

## 14. Bài thực hành

### 14.1. Bộ dữ liệu minh họa

Trong một store được cấu hình hỗ trợ ví dụ JPA, tạo dữ liệu sau:

| Khóa | displayName | email | age | active | status | creditLimit |
|---|---|---|---|---|---|---|
| C01 | `An` | `an@example.com` | 25 | true | ACTIVE | 1500 |
| C02 | `Binh` | `binh.an@example.com` | 32 | false | SUSPENDED | 2000 |
| C03 | `Anh` | `anh@example.com` | 17 | true | ACTIVE | 500 |
| C04 | `Minh` | `minh@example.com` | 40 | true | ACTIVE | 3000 |
| C05 | `Hoa` | null | null | true | ACTIVE | 1200 |

Khóa C01–C05 chỉ dùng để nhận diện dòng trong bài tập; mô hình có thể dùng `id` dạng số tương ứng.

### 14.2. Tạo và giải thích các biểu thức

1. Tạo predicate chỉ chọn `active = true`. Kỳ vọng C01, C03, C04 và C05.
2. Thêm `age >= 18`. Trong ví dụ SQL với dữ liệu trên, kỳ vọng C01 và C04; tuổi null không tự được coi là lớn hơn hoặc bằng 18.
3. Tạo nhóm từ khóa `"an"` trong tên hoặc email, rồi ghép AND với active. Với hành vi tìm chuỗi ASCII thông thường, kỳ vọng C01 và C03.
4. Viết lại sai nhóm thành `(active AND tên khớp) OR email khớp`. Quan sát C02 có thể lọt vào kết quả và giải thích cây điều kiện.
5. Tạo predicate tìm `email.isNull()`. Kỳ vọng C05.
6. Dùng `CustomerPredicates.forSearch` với tuổi từ 18 đến 65, trạng thái ACTIVE và hạn mức tối thiểu 1000. Kỳ vọng C01 và C04.
7. Truyền tuổi tối thiểu lớn hơn tuổi tối đa. Xác nhận tầng xây điều kiện từ chối đầu vào trước khi gọi repository.
8. Bỏ toàn bộ bộ lọc. Xác nhận chính sách của ví dụ từ chối truy vấn không có điều kiện.

### 14.3. Quan sát lợi ích kiểm tra kiểu

Trong một nhánh thử nghiệm của ứng dụng học tập:

- Thay đối số tuổi bằng chuỗi và quan sát lỗi biên dịch.
- Đổi tên một thuộc tính miền, cập nhật Q-type và tìm các vị trí còn dùng tên cũ.
- So sánh khả năng phát hiện lỗi này với một tên thuộc tính được lưu trong chuỗi.
- Khôi phục mã hợp lệ trước khi thực thi truy vấn.

Các tình huống này kiểm tra lợi ích của metadata có kiểu. Chúng không thay thế kiểm thử kết quả trên store thật.

### 14.4. Phân biệt kiểm tra mã với kiểm tra truy vấn

Một mock repository nhận predicate rồi trả danh sách cố định không chứng minh adapter chuyển được biểu thức thành truy vấn đúng.

Khi xác nhận hành vi tích hợp, cần đi qua repository và store đang dùng, rồi đối chiếu:

| Cần kiểm tra | Bằng chứng |
|---|---|
| Tên thuộc tính và toán tử hợp lệ | Mã biên dịch với Q-type đúng |
| Nhóm điều kiện đúng | Kết quả gồm dòng phải chọn và loại đúng dòng không được chọn |
| Ánh xạ đúng | Truy vấn và dữ liệu lưu tương ứng |
| Null đúng nghiệp vụ | Trường hợp null, có giá trị và trường hợp bị bỏ qua bộ lọc |
| Hiệu năng phù hợp | Kế hoạch thực thi và dữ liệu có quy mô đại diện |

Điều cần nắm vững là ranh giới trách nhiệm: Q-type giúp biểu diễn đường dẫn có kiểu; predicate mô tả điều kiện; repository integration chuyển điều kiện sang truy vấn; store thực hiện phép so sánh. Kết hợp bốn phần đó với kiểm tra đầu vào và nhóm logic rõ ràng sẽ tạo bộ lọc động dễ đọc, dễ thay đổi và có thể kiểm chứng.
