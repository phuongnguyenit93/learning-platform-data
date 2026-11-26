# QuerydslPredicateExecutor và mô-đun triển khai tương ứng

`QuerydslPredicateExecutor<T>` là interface của Spring Data Commons giúp repository thực thi những điều kiện truy vấn được biểu diễn bằng Querydsl `Predicate`. Nó cung cấp hợp đồng tìm kiếm, đếm, kiểm tra tồn tại và phân trang; việc chuyển predicate thành truy vấn thực tế thuộc mô-đun Spring Data tích hợp với kho dữ liệu.

Vì vậy, thấy interface trong classpath chưa đủ để kết luận một repository có thể thực thi Querydsl. Cần phân biệt ba thành phần: API chung của Commons, thư viện Querydsl dùng để tạo biểu thức và implementation do mô-đun của store cung cấp. Bài học này giải thích mối quan hệ đó, dùng JPA làm ví dụ triển khai cụ thể và đối chiếu với MongoDB ở mức kiến trúc.

## 1. Interface chung không phải bộ máy truy vấn

Interface được khai báo trong package:

```java
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
```

Predicate mà nó nhận thuộc Querydsl:

```java
import com.querydsl.core.types.Predicate;
```

Đây không phải `java.util.function.Predicate<T>`. Predicate của Java biểu diễn một hàm kiểm tra đối tượng trong bộ nhớ; predicate của Querydsl biểu diễn một cây điều kiện để backend phù hợp có thể chuyển thành truy vấn.

Ví dụ:

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.fullName.containsIgnoreCase("Linh");
```

Đoạn mã tạo biểu thức tìm tên chứa chuỗi, chưa phải một vòng lặp lọc danh sách Java. Để chạy nó trên kho dữ liệu, cần executor hiểu mô hình và backend đang dùng.

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring Data Commons | Định nghĩa các abstraction như `Repository`, `Pageable`, `Sort` và `QuerydslPredicateExecutor` |
| Querydsl core và Q-type | Biểu diễn đường dẫn thuộc tính, kiểu dữ liệu và cây biểu thức truy vấn |
| Tích hợp Querydsl theo backend | Cung cấp cơ chế dựng hoặc chuyển biểu thức phù hợp với backend |
| Mô-đun Spring Data của store | Kết nối repository, mapping metadata và công cụ truy cập kho dữ liệu |
| Driver, persistence provider và database | Thực thi truy vấn theo giao thức và ngữ nghĩa của kho dữ liệu |

Commons không tự mở connection, tự tạo `EntityManager` hay tự chuyển mọi predicate thành SQL hoặc truy vấn document.

## 2. Repository được ghép với implementation như thế nào?

Với một store hỗ trợ tích hợp này, repository interface khai báo các khả năng cần dùng. Repository factory của mô-đun nhận diện chúng và ghép implementation tương ứng vào repository proxy.

Một mô hình khái niệm cho JPA:

```text
Service
   |
   v
CustomerRepository proxy
   |
   +--> Khả năng CRUD của repository JPA
   |       |
   |       v
   |    EntityManager / persistence provider
   |
   +--> Khả năng QuerydslPredicateExecutor
           |
           v
        QuerydslJpaPredicateExecutor
           |
           v
        Querydsl JPA + metadata JPA + EntityManager
           |
           v
        Truy vấn trên database
```

Sơ đồ giúp phân biệt trách nhiệm, không yêu cầu ứng dụng tự khởi tạo các executor đó. Trong cách sử dụng repository thông thường, ứng dụng inject repository interface và để hạ tầng Spring Data xây dựng implementation.

Việc thêm một interface có thể làm repository yêu cầu thêm một fragment triển khai. Nó không phải thao tác sinh backend còn thiếu chỉ từ tên phương thức.

## 3. Mô-đun triển khai phải phù hợp với store

Hai ví dụ về implementation chuyên biệt là:

| Store | Mô-đun Spring Data | Implementation tiêu biểu |
| --- | --- | --- |
| JPA | Spring Data JPA | `org.springframework.data.jpa.repository.support.QuerydslJpaPredicateExecutor` |
| MongoDB | Spring Data MongoDB | `org.springframework.data.mongodb.repository.support.QuerydslMongoPredicateExecutor` |

Với JPA, executor làm việc cùng metadata entity, Querydsl JPA và `EntityManager`. Với MongoDB, executor gắn với mapping document và hạ tầng truy vấn MongoDB. Hai implementation cùng thực hiện hợp đồng chung nhưng không sử dụng cùng cơ chế lưu trữ hay cùng ngôn ngữ truy vấn phía dưới.

Không lấy bảng này làm danh sách hỗ trợ cho mọi phiên bản hoặc mọi store. Với một module khác, chẳng hạn khi dự án dùng JDBC hoặc R2DBC, phải xác định rõ module và phiên bản đó có cung cấp implementation tương ứng hay không. Không suy ra hỗ trợ chỉ vì có dependency Spring Data Commons hoặc vì dự án đã dùng Querydsl ở một phần khác.

Cũng không suy ra một executor đồng bộ tự cung cấp API reactive. Mô hình thực thi, kiểu kết quả và khả năng hỗ trợ reactive là những hợp đồng cần xác định riêng.

### Cùng tên abstraction không bảo đảm cùng ngữ nghĩa backend

Một phép so sánh chuỗi, xử lý null, đường dẫn lồng nhau hoặc cách sắp xếp có thể chịu ảnh hưởng của mapping và store. Predicate hợp lệ về kiểu Java chưa đủ chứng minh mọi backend thực thi được hoặc cho kết quả hoàn toàn giống nhau.

Không tái sử dụng một Q-type sinh từ mô hình JPA cho MongoDB chỉ vì cả hai phía có các thuộc tính trùng tên. Q-type, metadata và quy tắc ánh xạ phải phù hợp với mô hình mà executor đang quản lý.

## 4. Những thành phần cần có trước khi dùng executor

Một cấu hình đầy đủ cần giải quyết nhiều lớp khác nhau:

| Lớp cấu hình | Điều cần có |
| --- | --- |
| Repository của store | Mô-đun tích hợp với kho dữ liệu, cấu hình kết nối và repository factory phù hợp |
| Querydsl runtime | Các thư viện Querydsl cần cho backend được chọn |
| Sinh Q-type | Annotation processor hoặc cơ chế sinh metadata phù hợp với mô hình |
| Biên dịch | Mã Q-type được sinh ra phải tham gia quá trình biên dịch |
| Mapping | Domain type được store nhận diện và ánh xạ hợp lệ |
| Khả năng executor | Module thực sự cung cấp khả năng thực thi `QuerydslPredicateExecutor` |

Dependency cho runtime và dependency cho annotation processing không có cùng nhiệm vụ. Thêm thư viện ở runtime không tự bảo đảm processor đã chạy; IDE hiển thị Q-type cũng chưa bảo đảm một lần build sạch sẽ sinh và biên dịch được nó.

Với JPA, cần giữ sự tương thích giữa hệ Spring Data, persistence API, Querydsl và annotation processor. Đặc biệt, các cấu hình dựa trên namespace `jakarta.persistence` và `javax.persistence` không được trộn tùy ý. Tọa độ dependency và tùy chọn processor phải theo đúng hệ phiên bản của dự án.

Bài học không gán sẵn một bộ phiên bản hay đoạn cấu hình build chung cho mọi dự án, vì khả năng tương thích nằm ở tổ hợp thư viện thực tế. Điều cần giữ là đủ cả phần định nghĩa biểu thức, sinh Q-type và triển khai executor cho đúng store.

## 5. Ví dụ JPA: mô hình, Q-type và repository

### 5.1. Entity dùng trong ví dụ

Đoạn mã sau giả định một hệ JPA dùng namespace Jakarta:

```java
import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    private Long id;

    private String tenantId;
    private String fullName;

    @Enumerated(EnumType.STRING)
    private CustomerStatus status;

    private BigDecimal creditLimit;

    protected Customer() {
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getFullName() { return fullName; }
    public CustomerStatus getStatus() { return status; }
    public BigDecimal getCreditLimit() { return creditLimit; }
}
```

Enum tương ứng:

```java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED
}
```

Ví dụ tập trung vào đọc dữ liệu; không mô tả một luồng tạo mới đầy đủ hoặc chiến lược sinh ID. Mapping dùng truy cập trường vì `@Id` đặt trên trường.

### 5.2. Q-type do công cụ sinh

Khi annotation processing được cấu hình đúng cho mô hình trên, Q-type tương ứng thường có tên `QCustomer`, với một root mặc định như:

```java
QCustomer customer = QCustomer.customer;
```

Các thuộc tính được biểu diễn bằng path theo kiểu dữ liệu:

| Thuộc tính | Dạng path điển hình | Ví dụ điều kiện |
| --- | --- | --- |
| `id` | `NumberPath<Long>` | `customer.id.eq(42L)` |
| `tenantId` | `StringPath` | `customer.tenantId.eq("tenant-a")` |
| `fullName` | `StringPath` | `customer.fullName.containsIgnoreCase("Linh")` |
| `status` | `EnumPath<CustomerStatus>` | `customer.status.eq(CustomerStatus.ACTIVE)` |
| `creditLimit` | `NumberPath<BigDecimal>` | `customer.creditLimit.goe(minimum)` |

Không nên viết tay Q-type chỉ để vượt qua lỗi thiếu mã sinh. Q-type phải theo metadata của domain model và được tái sinh khi mô hình thay đổi. Vị trí mã sinh và quy trình sinh phụ thuộc công cụ build của dự án.

### 5.3. Repository khai báo cả CRUD và executor

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

`JpaRepository` xác định đây là repository dùng khả năng JPA. `QuerydslPredicateExecutor` bổ sung hợp đồng thực thi predicate. Trong tổ hợp được hỗ trợ và cấu hình đúng, repository factory của Spring Data JPA cung cấp implementation tương ứng.

Chỉ riêng khai báo trên chưa chứng minh classpath đầy đủ, Q-type tồn tại hoặc entity mapping hợp lệ. Những yêu cầu ở phần trước vẫn cần được đáp ứng.

## 6. Dựng predicate động mà vẫn kiểm soát điều kiện

Giả sử màn hình tìm khách hàng có ba tiêu chí tùy chọn: tên, trạng thái và hạn mức tối thiểu. Mọi truy vấn phải nằm trong tenant hiện tại lấy từ ngữ cảnh tin cậy.

```java
import java.math.BigDecimal;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

public final class CustomerPredicates {

    private CustomerPredicates() {
    }

    public static Predicate forSearch(
            String trustedTenantId,
            String name,
            CustomerStatus status,
            BigDecimal minimumCreditLimit) {

        if (trustedTenantId == null || trustedTenantId.trim().isEmpty()) {
            throw new IllegalArgumentException("Thiếu tenant tin cậy");
        }

        if (minimumCreditLimit != null
                && minimumCreditLimit.signum() < 0) {
            throw new IllegalArgumentException("Hạn mức không được âm");
        }

        QCustomer customer = QCustomer.customer;
        BooleanBuilder builder = new BooleanBuilder(
            customer.tenantId.eq(trustedTenantId)
        );

        if (name != null && !name.trim().isEmpty()) {
            builder.and(customer.fullName.containsIgnoreCase(name.trim()));
        }

        if (status != null) {
            builder.and(customer.status.eq(status));
        }

        if (minimumCreditLimit != null) {
            builder.and(customer.creditLimit.goe(minimumCreditLimit));
        }

        return builder;
    }
}
```

`BooleanBuilder` là bộ dựng điều kiện mutable; ví dụ tạo một instance mới cho mỗi lần gọi. Không giữ nó trong một field dùng chung rồi nối thêm điều kiện từ nhiều request.

Các giá trị tùy chọn chỉ được đưa vào predicate khi xuất hiện. Không gọi `eq(null)` để diễn đạt mọi trường hợp vắng mặt. Nếu nghiệp vụ cần tìm giá trị null, dùng biểu thức null tường minh như `isNull()` theo khả năng của path và store; nếu không có tiêu chí, bỏ điều kiện đó.

Tên tham số `trustedTenantId` mô tả hợp đồng, không tự xác thực nguồn dữ liệu. Code gọi phải lấy tenant từ ngữ cảnh được ứng dụng tin cậy, thay vì để người dùng tùy ý chọn phạm vi tìm kiếm.

Tenant được nối bằng AND với các bộ lọc khác. Nếu sau này thêm một nhóm OR, cần giữ nhóm đó bên trong phạm vi tenant. Một biểu thức “tenant hiện tại HOẶC tên khớp” sẽ có ý nghĩa khác với “tenant hiện tại VÀ tên khớp”.

### `BooleanExpression` và `BooleanBuilder` có cách sử dụng khác nhau

Với biểu thức bất biến, cần giữ kết quả trả về:

```java
BooleanExpression predicate = customer.tenantId.eq(trustedTenantId);
predicate = predicate.and(customer.status.eq(CustomerStatus.ACTIVE));
```

Đoạn mã cần `com.querydsl.core.types.dsl.BooleanExpression` và các biến root, tenant đã có giá trị. Không gọi `predicate.and(...)` rồi bỏ kết quả nếu đang dùng cách dựng biểu thức này. Trong factory phía trên, `BooleanBuilder.and(...)` tích lũy điều kiện trên builder.

## 7. Các thao tác của `QuerydslPredicateExecutor`

Nhóm phương thức thường dùng gồm:

| Thao tác | Kiểu kết quả chung | Mục đích |
| --- | --- | --- |
| `findOne(predicate)` | `Optional<T>` | Kỳ vọng tối đa một kết quả |
| `findAll(predicate)` | `Iterable<T>` | Lấy các bản ghi khớp |
| `findAll(predicate, sort)` | `Iterable<T>` | Lấy kết quả với Spring Data Sort |
| `findAll(predicate, orders...)` | `Iterable<T>` | Lấy kết quả với Querydsl OrderSpecifier |
| `findAll(predicate, pageable)` | `Page<T>` | Lấy một trang và metadata phân trang |
| `count(predicate)` | `long` | Đếm bản ghi khớp |
| `exists(predicate)` | `boolean` | Kiểm tra có ít nhất một bản ghi khớp |

Ở đây `predicate` là Querydsl Predicate. Không ép một `java.util.function.Predicate<Customer>` hoặc một QBE `Example<Customer>` vào vị trí này.

### 7.1. Tìm và phân trang

Giả sử service đã có `CustomerRepository repository` và tenant tin cậy:

```java
Predicate predicate = CustomerPredicates.forSearch(
    currentTenantId,
    "Linh",
    CustomerStatus.ACTIVE,
    new BigDecimal("1000000")
);

Sort sort = Sort.by(
    Sort.Order.desc("creditLimit"),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Page<Customer> page = repository.findAll(predicate, pageable);
```

Các kiểu `Page`, `Pageable`, `PageRequest` và `Sort` thuộc `org.springframework.data.domain`. Chỉ số trang bắt đầu từ 0; kích thước trang phải dương và nên được kiểm soát tại biên API.

ID làm khóa phụ giúp xác định thứ tự khi hạn mức bằng nhau trên tập dữ liệu đang xét. Điều đó không tạo snapshot giữa nhiều lần đọc nếu dữ liệu thay đổi đồng thời.

Để cung cấp tổng số phần tử, implementation có thể cần truy vấn count bổ sung hoặc sử dụng tối ưu phù hợp. Không cam kết mọi lần gọi trả Page đều thực thi đúng một số lượng câu truy vấn cố định.

### 7.2. Sắp xếp bằng Querydsl path

Có thể dùng overload nhận `OrderSpecifier`:

```java
QCustomer customer = QCustomer.customer;

Iterable<Customer> ordered = repository.findAll(
    predicate,
    customer.creditLimit.desc(),
    customer.id.asc()
);
```

Cách này tham chiếu thuộc tính qua Q-type. Cách dùng `Sort` lại nhận tên property path của domain model, không phải tên cột SQL tùy ý.

Cả hai vẫn chịu khả năng sắp xếp, kiểu dữ liệu và thứ tự null của store. Type safety không tự làm mọi biểu thức sắp xếp trở nên hợp lệ trên mọi backend.

### 7.3. Tìm một kết quả

Với ID và tenant đã được kiểm tra hợp lệ:

```java
QCustomer customer = QCustomer.customer;

Predicate byIdInTenant = customer.id.eq(customerId)
    .and(customer.tenantId.eq(currentTenantId));

Optional<Customer> found = repository.findOne(byIdInTenant);
```

Đoạn mã cần `java.util.Optional`. Nếu không có kết quả, nhận Optional rỗng; nếu điều kiện khớp nhiều kết quả, thao tác kỳ vọng duy nhất báo lỗi kích thước kết quả.

Không dùng `findOne` với một bộ lọc rộng rồi mong nó tự lấy bản ghi đầu. Việc sắp xếp cũng không biến hợp đồng tối đa một kết quả thành hợp đồng chọn phần tử đầu.

### 7.4. Chỉ đếm hoặc kiểm tra tồn tại

```java
long total = repository.count(predicate);
boolean hasMatch = repository.exists(predicate);
```

Không tải toàn bộ kết quả rồi mới đếm hay kiểm tra danh sách rỗng nếu đó là mục tiêu duy nhất. Ngược lại, không coi count hoặc exists là một bước khóa dữ liệu: kết quả đọc không bảo đảm điều kiện vẫn đúng khi ghi sau đó.

## 8. Quan hệ với fluent query và projection

Khi phiên bản API và implementation hỗ trợ `findBy(predicate, queryFunction)`, callback fluent có thể chọn cách lấy kết quả. Predicate vẫn mô tả điều kiện; callback quyết định hình thức trả về.

Ví dụ một interface projection:

```java
public interface CustomerSummary {
    Long getId();
    String getFullName();
}
```

Cách dùng trên implementation hỗ trợ tổ hợp này:

```java
Page<CustomerSummary> summaries = repository.findBy(
    predicate,
    fluent -> fluent
        .as(CustomerSummary.class)
        .page(pageable)
);
```

Không trả chính `fluent` ra khỏi callback để dùng sau. Projection phải phù hợp với cơ chế ánh xạ mà store cung cấp; không suy ra `as(...)` tự chuyển đổi sang mọi lớp DTO.

Có fluent projection cũng không đồng nghĩa `QuerydslPredicateExecutor` đã trở thành API tùy ý cho mọi biểu thức SELECT, JOIN hoặc GROUP BY. Phải phân biệt cấu hình lấy kết quả mà executor hỗ trợ với việc tự dựng một Querydsl query hoàn chỉnh.

## 9. Khi nào cần custom repository thay vì executor chung?

Querydsl là một hệ biểu thức truy vấn rộng hơn tập phương thức mà `QuerydslPredicateExecutor` công khai. Executor phù hợp với việc tìm entity hoặc kết quả được hỗ trợ theo một predicate, cùng các lựa chọn sort, page và fetch được cung cấp.

Những nhu cầu sau có thể cần một repository fragment tùy chỉnh hoặc cơ chế truy vấn khác của store:

- Chủ động chỉ định join và fetch join trong JPA.
- Chọn một tổ hợp biểu thức hay phép tổng hợp không được API executor diễn đạt.
- Dùng GROUP BY, HAVING hoặc truy vấn báo cáo nhiều nguồn dữ liệu.
- Kiểm soát riêng câu truy vấn nội dung và count cho phân trang phức tạp.
- Áp dụng tùy chọn backend mà executor không công khai.

Ví dụ, chỉ vì một predicate tham chiếu đường dẫn quan hệ không có nghĩa nó cấu hình fetch join để giải quyết N+1. Hành vi tải quan hệ còn thuộc mapping và truy vấn của JPA.

Khi cần custom repository JPA, ứng dụng có thể dựng truy vấn bằng công cụ Querydsl JPA phù hợp và giữ ranh giới giao dịch, mapping, phân trang cùng count một cách tường minh. Với MongoDB, lựa chọn phải dựa trên hạ tầng truy vấn của MongoDB, không mang trực tiếp `EntityManager` hay `JPAQueryFactory` sang store đó.

Không nên đưa cú pháp SQL tùy ý vào một chuỗi rồi coi đó là cách mở rộng executor chung. Việc dùng biểu thức đặc thù backend phải được thiết kế và kiểm soát ở tầng tích hợp thích hợp.

## 10. Không nhầm executor với các tích hợp khác

| Khả năng | Vai trò | Không tự cung cấp |
| --- | --- | --- |
| `QuerydslPredicateExecutor` | Thực thi predicate qua repository được hỗ trợ | Sinh Q-type hoặc bind tham số HTTP |
| Annotation processing | Sinh Q-type từ mô hình phù hợp | Executor truy cập database |
| Tự dùng Querydsl query API | Dựng truy vấn backend theo API được chọn | Tự ghép fragment vào mọi Spring Data repository |
| Querydsl web binding | Chuyển dữ liệu request thành điều kiện theo cấu hình | Quyền truy cập dữ liệu hoặc quyền sửa entity |
| `QueryByExampleExecutor` | Truy vấn qua probe và ExampleMatcher | Hợp đồng nhận Querydsl Predicate |

Nếu chỉ dùng executor từ service thì không bắt buộc phải đưa predicate ra ngoài tầng web. Nếu dùng web binding, cấu hình trường được cho phép và các quy tắc nghiệp vụ là một phần riêng; executor không tự biết trường nào người dùng được quyền tìm kiếm.

Kết quả là entity cũng không tự mang quyền cập nhật. Luồng đọc bằng Querydsl và luồng ghi vẫn cần hợp đồng nghiệp vụ riêng như các cách đọc repository khác.

## 11. Chẩn đoán theo đúng lớp bị thiếu

| Biểu hiện | Nguyên nhân có thể gặp | Hướng xác định |
| --- | --- | --- |
| Không nhận diện `QuerydslPredicateExecutor` | Thiếu dependency Commons phù hợp hoặc import sai | Kiểm tra lớp abstraction của Spring Data |
| Không nhận diện Querydsl Predicate | Thiếu thư viện Querydsl hoặc import nhầm Predicate của Java | Kiểm tra package và classpath Querydsl |
| Không có `QCustomer` | Processor chưa chạy, mô hình chưa được nhận diện hoặc mã sinh chưa tham gia biên dịch | Kiểm tra quy trình sinh và biên dịch Q-type |
| IDE chạy nhưng build sạch không có Q-type | Phụ thuộc vào mã sinh cũ hoặc cấu hình riêng của IDE | Làm rõ cấu hình annotation processing của build |
| Repository khởi tạo thất bại sau khi thêm interface | Store không cung cấp fragment tương ứng, thiếu thư viện backend hoặc metadata không hợp lệ | Xác định repository factory và implementation mà module hỗ trợ |
| Lỗi liên quan namespace persistence | Trộn dependency hoặc processor không tương thích với mô hình Jakarta/Javax | Đồng bộ hệ dependency theo stack thực tế |
| Predicate biên dịch nhưng truy vấn thất bại | Mapping, biểu thức hoặc backend không hỗ trợ tổ hợp đang dùng | Xem lớp chuyển biểu thức và truy vấn trên store đích |
| Có nhiều kết quả khi gọi findOne | Điều kiện không bảo đảm duy nhất | Sửa bộ lọc hoặc chọn hợp đồng kết quả phù hợp |
| Truy vấn rộng hơn dự định | Thiếu điều kiện bắt buộc hoặc ghép AND/OR sai | Đối chiếu cây predicate với quy tắc nghiệp vụ |
| Kết quả đúng nhưng truy vấn chậm | Điều kiện, collation, truy cập quan hệ hoặc chỉ mục chưa phù hợp | Đối chiếu truy vấn thực tế và kế hoạch thực thi của database |

Không dùng việc thêm ngẫu nhiên dependency làm cách xử lý chung cho mọi lỗi. Thiếu Q-type, thiếu executor và lỗi mapping nằm ở các lớp khác nhau, dù có thể cùng xuất hiện khi repository khởi tạo.

Thông báo exception cụ thể có thể khác theo module và phiên bản. Cần hiểu nguyên nhân ở lớp nào thay vì thiết kế dựa trên một chuỗi thông báo duy nhất.

## 12. Thực hành xác nhận ranh giới Commons và store

Trên một dự án đã có cấu hình Querydsl phù hợp, có thể lần lượt đối chiếu các tình huống:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Repository có cả JPA và executor | Factory của module JPA cung cấp được khả năng thực thi tương ứng |
| Thay đổi tên thuộc tính trong domain model | Q-type được tái sinh và các tham chiếu cũ bị phát hiện khi biên dịch |
| Chỉ truyền tenant, không có tiêu chí tùy chọn | Predicate vẫn giới hạn phạm vi tenant |
| Thêm trạng thái và hạn mức tối thiểu | Các điều kiện được nối đúng bằng AND |
| Nhiều khách hàng cùng hạn mức | Sort có ID làm khóa phụ hoạt động theo store |
| Bộ lọc trả nhiều kết quả nhưng gọi findOne | Lỗi kỳ vọng duy nhất được phân biệt với Optional rỗng |
| Gọi count hoặc exists | Không cần tải toàn bộ entity chỉ để trả lời câu hỏi tương ứng |
| Cần fetch join hoặc GROUP BY | Nhận ra giới hạn API executor và chuyển sang cơ chế phù hợp |
| Đổi sang một store khác | Đánh giá lại module, Q-type, mapping và khả năng hỗ trợ; không chỉ đổi dependency |

`QuerydslPredicateExecutor` hữu ích khi repository cần một hợp đồng chung để thực thi điều kiện Querydsl. Muốn dùng đúng, phải nối được cả chuỗi: domain metadata, Q-type, thư viện Querydsl, repository factory và implementation của store. Interface trong Commons là điểm thống nhất của hợp đồng; khả năng truy vấn thực tế vẫn do mô-đun tích hợp và kho dữ liệu quyết định.