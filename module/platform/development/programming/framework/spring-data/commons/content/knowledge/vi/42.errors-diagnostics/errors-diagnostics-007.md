# Kiểu trả về, tham số đặc biệt hoặc từ khóa không được store hỗ trợ

## 1. Một abstraction dùng chung không phải cam kết hỗ trợ đồng nhất

Trong chương **Lỗi và chẩn đoán** của module **SPRING_DATA_COMMONS**, một lỗi thường gặp là thấy một kiểu trả về, tham số hoặc từ khóa trong tài liệu Commons rồi dùng nó cho mọi repository.

Spring Data Commons cung cấp các khái niệm dùng chung: Repository, CRUD, query derivation, phân trang, sắp xếp và projection. Tuy nhiên, mỗi module store phải cung cấp cách thực thi tương ứng. Một database có khả năng nào đó cũng chưa đồng nghĩa module Spring Data có thể diễn đạt khả năng ấy bằng mọi dạng query method.

Cần phân biệt ba mức:

~~~text
Commons biết abstraction hoặc cú pháp
    -> module store hỗ trợ cách thực thi đó
    -> engine, dialect, schema và dữ liệu đáp ứng yêu cầu
~~~

Một method có thể hợp lệ ở mức parser nhưng bị module từ chối. Một query được module tạo thành công vẫn có thể bị database từ chối khi chạy.

Danh sách kiểu trả về của Commons yêu cầu đối chiếu khả năng của từng store. Danh sách keyword cũng có giới hạn tương tự. [Query return types của Commons](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html), [query keywords của Commons](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html).

## 2. Nhận diện đúng nhóm lỗi trước khi sửa

| Nhóm | Ví dụ | Điều cần xác định |
| --- | --- | --- |
| Kiểu trả về | Page, Mono, Stream, projection, wrapper lồng nhau | Module có hỗ trợ hình dạng kết quả này không? |
| Tham số đặc biệt | Pageable, Sort, Limit, ScrollPosition | Tham số được nhận diện đúng và tổ hợp có hợp lệ không? |
| Keyword | Regex, Near, Containing, IgnoreCase | Store có dịch được keyword với property đó không? |
| Binding | Thiếu cận Between, In nhận sai kiểu | Đủ số và đúng loại tham số bindable chưa? |
| Property path | Sai tên field, đường nested không tồn tại | Parser có xác định đúng property không? |
| Mapping | DTO thiếu constructor hoặc alias không khớp | Query đã chạy nhưng kết quả không tạo được object? |
| Engine/schema | Function, operator hoặc index không có | Module đã chuyển truy vấn hợp lệ xuống đúng backend chưa? |

Các nhóm có thể liên quan nhưng không đồng nhất. Ví dụ:

- `findByFullNameRegx` có thể là lỗi tên property do viết sai keyword.
- `findByFullNameRegex` có thể được parser hiểu nhưng store không cung cấp cách thực thi.
- Native SQL regex có thể chạy ở database này nhưng không ở database khác.
- `Optional<T>` có nhiều kết quả là lỗi cardinality, không tự là kiểu trả về không được hỗ trợ.

Không sửa tất cả bằng cách đổi method sang trả `List`. Cách đó có thể làm mất một hợp đồng quan trọng như duy nhất, tổng số phần tử hoặc tính reactive.

## 3. Lần theo giai đoạn lỗi

Một đường xử lý đơn giản hóa:

~~~mermaid
flowchart TD
    A["Repository được module nào quản lý?"] --> B["Phân tích method và metadata"]
    B --> C["Kiểm tra kiểu trả về và tham số"]
    C --> D["Derive hoặc nhận query khai báo"]
    D --> E["Module tạo query cho store"]
    E --> F["Driver và engine thực thi"]
    F --> G["Mapping/projection kết quả"]
    G --> H["Caller nhận dữ liệu, completion hoặc lỗi"]
~~~

Thứ tự chi tiết có thể khác giữa các module và phiên bản. Sơ đồ giúp xác định bằng chứng cần tìm, không phải thứ tự bắt buộc của mọi class nội bộ.

### 3.1. Lỗi ở startup chưa chắc do kết nối database

Một repository có method không hợp lệ có thể làm application context không khởi động. Exception ngoài cùng có thể là lỗi tạo bean hoặc dependency; cần tìm method repository và cause có ý nghĩa ở bên trong.

Chuỗi minh họa:

~~~text
Không tạo được service bean
    -> Không tạo được repository bean
       -> Không tạo được query cho một method
          -> Keyword, return type hoặc parameter combination bị từ chối
~~~

Thông báo cụ thể thay đổi theo phiên bản. Không dựa vào đúng một câu message của một bản Spring Data để phân loại mọi lỗi.

### 3.2. Lỗi chỉ xuất hiện khi gọi hoặc tiêu thụ kết quả

Một số lỗi bị trì hoãn tới lần gọi đầu, lúc query chạy hoặc khi result được materialize.

Với Mono/Flux/Flow, cần subscribe/collect và quan sát completion/error. Chỉ lấy được một publisher từ method không chứng minh query đã thành công.

Nếu startup qua nhưng code đọc projection mới lỗi, cần xem cả đường mapping; không mặc định quay lại sửa keyword khi query thực tế đã được chấp nhận.

## 4. Mẫu domain cho các ví dụ JPA

Phần JPA dùng Jakarta Persistence trên một ứng dụng có repository/entity scanning phù hợp. Các public type được hiểu là nằm trong các file Java riêng khi triển khai.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false)
    private String status;

    protected Customer() {
    }

    public Customer(String fullName, String status) {
        this.fullName = fullName;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Trong model này:

- Property Java là `fullName`.
- Column vật lý là `full_name`.
- Derived query dùng property path của domain, không dùng tên column như một tên property thay thế.
- Query JPQL và native SQL dùng hai hệ tên khác nhau.

Các ví dụ sửa dưới đây gắn với module và kiểu query được chỉ rõ; chúng không phải interface có thể chép nguyên vẹn sang mọi store.

## 5. Kiểu trả về: đúng generic chưa đủ

### 5.1. Page cần hợp đồng phân trang tương ứng

Ví dụ thiếu tham số cần thiết:

~~~java
// Method minh họa lỗi: Page query nhưng thiếu Pageable.
Page<Customer> findByStatus(String status);
~~~

Trong query method phân trang tương ứng, dùng:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Page<Customer> findByStatus(String status, Pageable pageable);
}
~~~

Page biểu diễn cả nội dung trang và metadata như tổng số phần tử. [Page API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html). Nếu mục tiêu chỉ là một đoạn dữ liệu hoặc biết còn đoạn tiếp theo, có thể chọn hình dạng khác **khi module hỗ trợ**.

Ví dụ các lựa chọn JPA được khai báo bằng tên method riêng:

~~~java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Customer> findSliceByStatus(
    String status, Pageable pageable
);

List<Customer> findListByStatus(
    String status, Pageable pageable
);
~~~

Đây là các method thêm vào interface repository, không phải compilation unit độc lập. Chúng thể hiện các hợp đồng khác nhau; không đổi từ Page sang List rồi vẫn trả total giả ở tầng API.

Metadata phân trang có thể cần thêm công việc count. Mức thực thi cụ thể phụ thuộc module và tình huống query; không nên khẳng định mọi lần gọi Page luôn phát đúng hai query.

### 5.2. Bọc một kiểu trong Mono không tự làm nó được hỗ trợ

Ví dụ trên Spring Data R2DBC 3.5.0:

~~~java
// Không suy rằng hình dạng này được module chấp nhận.
Mono<Page<CustomerRow>> findByStatus(
    String status, Pageable pageable
);
~~~

Trong phiên bản này, kiểm tra query method R2DBC từ chối kiểu thực thi Page/Slice bọc trong single-value reactive wrapper khi có Pageable. Đây là ràng buộc của module, dù Mono, Page và Pageable đều là các type có thật. [R2dbcQueryMethod 3.5.0](https://github.com/spring-projects/spring-data-relational/blob/3.5.0/spring-data-r2dbc/src/main/java/org/springframework/data/r2dbc/repository/query/R2dbcQueryMethod.java).

Một đường query derived phù hợp có thể trả các phần tử qua Flux và dùng count riêng nếu nghiệp vụ cần tổng số. Phần 9 trình bày cách tổ chức đó.

Đổi thành `Flux<Page<CustomerRow>>` chỉ để vượt một bước kiểm tra cũng không tạo ra một hợp đồng pagination đúng. Cần chọn hình dạng được tài liệu module hỗ trợ, không tìm một lớp bọc giúp method tình cờ qua bootstrap.

### 5.3. Repository blocking không thành reactive nhờ đổi return type

Nếu repository JPA đang được hạ tầng JPA quản lý, việc đổi method sang `Mono<Customer>` hoặc `Flux<Customer>` không thay driver, transaction manager và cơ chế thực thi thành R2DBC.

Các lựa chọn phải rõ ràng:

- Giữ API repository theo mô hình blocking mà module hỗ trợ.
- Chọn module reactive và driver phù hợp nếu ứng dụng thực sự chuyển mô hình.
- Nếu có adapter ở biên ứng dụng, xem nó là một quyết định về scheduling và hợp đồng API; nó không biến JPA thành reactive store.

Các họ repository reactive/coroutine được chọn theo module và khả năng hỗ trợ tương ứng. [Định nghĩa repository interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

### 5.4. Optional là hợp đồng cardinality, không phải “chọn ngẫu nhiên một bản ghi”

Với một query kỳ vọng nhiều nhất một kết quả, nhiều bản ghi khớp có thể làm phát sinh lỗi kích thước kết quả.

Ví dụ:

~~~java
Optional<Customer> findByFullName(String fullName);
~~~

Nếu nhiều khách hàng cùng tên, lỗi không chứng minh Optional bị store cấm. Cần chọn đúng hợp đồng:

- Nếu tên phải duy nhất: kiểm tra dữ liệu và ràng buộc duy nhất cần có.
- Nếu có thể nhiều người cùng tên: trả collection theo nghiệp vụ.
- Nếu cần phần tử đầu theo thứ tự: dùng truy vấn giới hạn và sort xác định nếu module hỗ trợ.

Không thêm First chỉ để che dữ liệu vi phạm một invariant duy nhất. Việc “chọn đầu tiên” thay đổi ý nghĩa của API.

## 6. Tham số đặc biệt: không phải mọi đối số đều được bind vào predicate

Pageable, Sort hoặc Limit có vai trò điều khiển query trong những đường được hỗ trợ. Chúng không phải giá trị nghiệp vụ tương ứng với một placeholder bình thường.

Hạ tầng query phân biệt tham số bindable, tham số đặc biệt và tham số dynamic projection. Khi chẩn đoán binding, cần dựa vào cách hạ tầng nhận diện chứ không chỉ đếm tổng số đối số Java. [Parameter API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/Parameter.html).

### 6.1. Pageable và Sort không khai báo đồng thời cho cùng query method

Ví dụ cần sửa:

~~~java
Page<Customer> findByStatus(
    String status,
    Pageable pageable,
    Sort sort
);
~~~

Pageable đã chứa Sort; hạ tầng kiểm tra query method cũng kiểm soát các khai báo tham số tương ứng. [QueryMethod 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/repository/query/QueryMethod.java).

Gộp ý định ở điểm gọi:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest request = PageRequest.of(
    0,
    20,
    Sort.by("fullName").ascending()
        .and(Sort.by("id").ascending())
);

Page<Customer> page = repository.findByStatus("ACTIVE", request);
~~~

Khóa id bổ sung giúp thứ tự xác định khi tên trùng nhau. Đây là đoạn gọi trong một lớp đã được inject repository, không phải một chương trình hoàn chỉnh.

### 6.2. Pageable và Limit cũng có thể xung đột

Ví dụ tổ hợp cần loại bỏ:

~~~java
List<Customer> findByStatus(
    String status, Pageable pageable, Limit limit
);
~~~

Pageable đã mang kích thước giới hạn cho trang. Chọn một cơ chế phù hợp mục tiêu và khả năng module.

Các special parameter không được lặp tùy ý trong cùng method. Những tổ hợp như Pageable + Sort và Pageable + Limit được liệt kê là không hợp lệ trong hướng dẫn Commons. [Paging, sorting và limiting parameters](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html).

### 6.3. First/Top với Limit khác First/Top với Pageable

Không áp dụng quy tắc “đã có giới hạn thì cấm mọi giới hạn khác”.

- Commons mô tả First/Top không dùng cùng một Limit parameter.
- First/Top có thể phối hợp với Pageable trong semantics được hỗ trợ: giới hạn toàn tập và phạm vi trang là hai vai trò cần hiểu đúng.
- Module thực tế vẫn quyết định khả năng thực thi.

Ví dụ cần xem lại:

~~~java
List<Customer> findTop10ByStatus(
    String status, Limit limit
);
~~~

Chọn giới hạn cố định trong tên hoặc Limit parameter khi module hỗ trợ; không để cả hai mô tả cùng một quyết định một cách mâu thuẫn.

### 6.4. Kiểm tra đúng import và giá trị “không dùng”

Đảm bảo Pageable/Sort/Limit đến từ `org.springframework.data.domain` trong các ví dụ này. Một interface cùng tên ở package khác không tự được hạ tầng Spring Data nhận diện là special parameter.

Khi API hỗ trợ, dùng các giá trị như `Pageable.unpaged()`, `Sort.unsorted()` hoặc `Limit.unlimited()` để biểu đạt ý định tương ứng thay vì truyền null.

Không phải mọi API tự viết đều xử lý unpaged giống nhau: một helper gọi offset/page size không điều kiện có thể cần tự kiểm tra trạng thái paged trước. Lỗi trong helper như vậy khác với một khả năng không được store hỗ trợ.

### 6.5. Thiếu đối số bindable sau khi loại special parameter

Ví dụ với property id hợp lệ:

~~~java
// Between cần hai giá trị biên; Pageable không phải biên thứ hai.
List<Customer> findByIdBetween(
    Long lowerBound, Pageable pageable
);
~~~

Một khai báo có đủ cận sẽ có dạng:

~~~java
List<Customer> findByIdBetween(
    Long lowerBound,
    Long upperBound,
    Pageable pageable
);
~~~

Tương tự, với In cần kiểm tra loại collection/array mà module chấp nhận. Không xem một lỗi thiếu hoặc sai kiểu bind parameter là bằng chứng toàn bộ keyword bị store cấm.

## 7. Keyword được parser nhận diện nhưng store không dịch được

### 7.1. Ví dụ Regex trong derived query JPA

Method minh họa:

~~~java
List<Customer> findByFullNameRegex(String pattern);
~~~

Property `fullName` có thật trong model, và Regex nằm trong tập keyword Commons nhận diện. Điều đó chưa đủ để đường query derivation JPA tạo predicate regex.

Ở Spring Data JPA 3.5.0, JpaQueryCreator chỉ xử lý những loại predicate mà implementation cung cấp; loại không được xử lý bị báo là unsupported keyword. [JpaQueryCreator 3.5.0](https://github.com/spring-projects/spring-data-jpa/blob/3.5.0/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/query/JpaQueryCreator.java).

Đây là lỗi năng lực của đường query đang chọn, không phải bằng chứng field `fullName` bị viết sai.

### 7.2. Chọn cách sửa theo ý nghĩa tìm kiếm

Nếu yêu cầu thật là tìm chuỗi con không phân biệt hoa thường, một query JPA có thể là:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;

List<Customer> findByFullNameContainingIgnoreCase(
    String text, Sort sort
);
~~~

JPA có các keyword cho tìm prefix, suffix, chuỗi con và so sánh không phân biệt hoa thường trên property phù hợp. Các tham số của nhóm Containing/StartingWith/EndingWith được xử lý theo semantics của query derivation JPA, trong đó có việc escape wildcard LIKE. [JPA query methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html).

Nhưng chuỗi con và regex không tương đương.

Ví dụ với tên `Lan`, `Lun` và `L.n`:

| Ý định | Input | Kết quả khái niệm |
| --- | --- | --- |
| Tìm literal chứa chuỗi L.n | `L.n` | Chỉ giá trị có chuỗi L.n |
| Regex dùng dấu chấm làm ký tự đại diện | `L.n` | Có thể khớp cả Lan, Lun và L.n |

Nếu sản phẩm thực sự yêu cầu regex, thay bằng Containing có thể làm application khởi động nhưng làm sai chức năng.

### 7.3. Nếu cần regex PostgreSQL, chọn đường query tường minh

Một ví dụ native query JPA gắn với PostgreSQL:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Query(
    value = """
        SELECT id, full_name, status
        FROM app_customer
        WHERE full_name ~ :pattern
        ORDER BY id
        """,
    nativeQuery = true
)
List<Customer> findUsingPostgresRegex(
    @Param("pattern") String pattern
);
~~~

Operator `~` ở đây là regex của PostgreSQL, không phải JPQL tiêu chuẩn hay một keyword JPA được bật thêm. [Pattern matching của PostgreSQL](https://www.postgresql.org/docs/current/functions-matching.html).

Cách sửa này có các điều kiện cần kiểm chứng:

- Backend thật sự là PostgreSQL với semantics phù hợp.
- Query select đủ dữ liệu để map entity.
- Tham số được bind thay vì nối input trực tiếp vào SQL.
- Pattern và cách so sánh đáp ứng hợp đồng ứng dụng.
- Test dùng đúng engine để xác nhận hành vi.

Đây là một lựa chọn có tính phụ thuộc store. Không đổi `nativeQuery = true` rồi xem query đó như một phương án độc lập database.

### 7.4. Cùng keyword đó có thể được MongoDB hỗ trợ

Ví dụ một model MongoDB riêng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public record CustomerDocument(
    @Id String id,
    String fullName,
    String status
) {
}
~~~

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerDocumentRepository
        extends MongoRepository<CustomerDocument, String> {

    List<CustomerDocument> findByFullNameRegex(String pattern);
}
~~~

Spring Data MongoDB mô tả Regex được dịch sang tiêu chí regex của MongoDB. Điều này giải thích vì sao một tên method có thể hợp lệ ở module này mà không hợp lệ ở module khác. [MongoDB-specific query methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html).

Không chuyển một interface từ MongoRepository sang JpaRepository rồi mặc định toàn bộ method giữ nguyên ý nghĩa và khả năng thực thi.

## 8. Keyword còn phụ thuộc loại property và cách diễn giải

Ngay khi store có hỗ trợ keyword, vẫn cần kiểm tra property tương ứng.

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| IgnoreCase trên field không phải chuỗi | Module có phép so sánh phù hợp với kiểu property không? |
| IsEmpty trên một property scalar | Keyword có yêu cầu collection không? |
| Containing trên String và collection | Semantics là chuỗi con hay thành viên tập hợp? |
| Near/Within | Model tọa độ, kiểu tham số, index và toán tử địa lý có phù hợp không? |
| In | Kiểu collection/array và conversion phần tử có đúng không? |
| Between | Có đủ hai cận và đúng kiểu so sánh không? |
| Distinct | Đang phân biệt toàn entity hay giá trị projection nào? |

Một lỗi kiểu property khác với “module không hỗ trợ keyword trong mọi trường hợp”. Ví dụ, một keyword cho collection không tự áp dụng được cho String chỉ vì cả hai có khái niệm “rỗng” trong ngôn ngữ thông thường.

Đối với truy vấn địa lý, còn phải xác định đơn vị khoảng cách, thứ tự tọa độ và loại index theo store. Chỉ đổi kiểu trả về sang GeoResults không tạo ra khả năng truy vấn địa lý cho một module không cung cấp đường thực thi đó.

### 8.1. Phân biệt property Java và field lưu trữ

Với entity JPA mẫu:

~~~java
List<Customer> findByFullName(String name);
~~~

dùng property `fullName`. Không đổi tên method sang `findByFull_name` chỉ vì column SQL là `full_name`.

Ngược lại, native SQL ở ví dụ trước phải dùng tên column SQL thực tế. Query khai báo bằng ngôn ngữ khác cần tuân theo hệ tên và mapping của ngôn ngữ đó.

Nếu property nested không tồn tại hoặc đường phân giải bị mơ hồ, hãy chẩn đoán property path trước. Một lỗi “không tìm thấy property” chưa phải dấu hiệu chắc chắn của keyword unsupported.

## 9. R2DBC: tách kết quả reactive khỏi việc tự xây Page ở service

Ví dụ model relational dành cho R2DBC:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("app_customer")
public record CustomerRow(
    @Id Long id,
    @Column("full_name") String fullName,
    String status
) {
}
~~~

Repository có các method derived riêng cho dữ liệu và count:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCrudRepository<CustomerRow, Long> {

    Flux<CustomerRow> findByStatus(
        String status, Pageable pageable
    );

    Mono<Long> countByStatus(String status);
}
~~~

R2DBC có ví dụ derived query trả Flux nhận Pageable để truyền offset và sort tới database. Điều đó khác với việc yêu cầu repository tự thực thi `Mono<Page<T>>`. [R2DBC query methods](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html).

Nếu API ứng dụng thật sự cần Page, service có thể phối hợp hai thao tác:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import reactor.core.publisher.Mono;

public class CustomerPageReader {

    private final ReactiveCustomerRepository repository;

    public CustomerPageReader(ReactiveCustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Page<CustomerRow>> readPage(
            String status, Pageable pageable) {

        if (pageable == null || !pageable.isPaged()) {
            return Mono.error(new IllegalArgumentException(
                "API này yêu cầu Pageable có giới hạn"
            ));
        }

        return repository.findByStatus(status, pageable)
            .collectList()
            .flatMap(content ->
                repository.countByStatus(status)
                    .map(total -> {
                        Page<CustomerRow> page = new PageImpl<>(
                            content, pageable, total
                        );
                        return page;
                    })
            );
    }
}
~~~

Ở đây:

- `Mono<Page<CustomerRow>>` là kiểu trả về của **service tự viết**.
- Repository vẫn dùng những query method được module hỗ trợ.
- Thao tác count chạy sau khi đã thu thập dữ liệu.
- Có thêm chi phí count nếu caller cần tổng số.
- Kích thước trang, thuộc tính sort được phép và giới hạn tải cần được kiểm soát theo API ứng dụng.

Hai query dữ liệu và count không tự tạo một snapshot nhất quán khi có ghi đồng thời. Nếu nghiệp vụ cần tính nhất quán đó, phải đánh giá transaction/isolation và semantics của backend tương ứng.

Nếu chỉ cần cuộn tiếp dữ liệu, có thể chọn hợp đồng không yêu cầu total thay vì luôn tạo Page. Không lấy `content.size()` làm total của toàn bộ tập kết quả.

## 10. @Query có thể thay đổi cả ngôn ngữ và khả năng của method

Một cách sửa thường thấy là thêm `@Query` vào method có tên khó derive. Cách này chỉ đúng nếu khai báo phù hợp module và ngôn ngữ query.

| Module | Annotation Query thuộc package | Ngôn ngữ thường gặp |
| --- | --- | --- |
| Spring Data JPA | `org.springframework.data.jpa.repository.Query` | JPQL hoặc native SQL khi được khai báo tương ứng |
| Spring Data JDBC | `org.springframework.data.jdbc.repository.query.Query` | SQL |
| Spring Data R2DBC | `org.springframework.data.r2dbc.repository.Query` | SQL |
| Spring Data MongoDB | `org.springframework.data.mongodb.repository.Query` | Query document theo cú pháp module |

Cùng tên ngắn Query không có nghĩa các annotation có thể thay thế cho nhau.

Một đoạn JPQL dùng entity/property không tự chạy như SQL R2DBC. Một đoạn JSON query MongoDB cũng không được hiểu bởi JPA chỉ vì tên method giống nhau.

### 10.1. Derived query và string-based query không nhất thiết hỗ trợ cùng special parameter

Trong tài liệu R2DBC được dẫn, string-based `@Query` không tự hỗ trợ pagination hoặc nhận Sort/Limit như đường query cần được viết lại tự động.

Ví dụ không nên mặc định có tác dụng:

~~~java
@Query("SELECT id, full_name, status FROM app_customer WHERE status = :status")
Flux<CustomerRow> readStatusRows(
    String status, Pageable pageable
);
~~~

Một method có thể dùng Pageable ở đường derived query nhưng không có cùng cơ chế ở đường string-based query. Đừng kết luận Pageable “bị R2DBC cấm hoàn toàn” hoặc “chắc chắn hoạt động ở mọi query”.

### 10.2. Nếu cần SQL tường minh, bind giới hạn như giá trị thường

Ví dụ PostgreSQL/R2DBC có thứ tự cố định:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import reactor.core.publisher.Flux;

@Query("""
    SELECT id, full_name, status
    FROM app_customer
    WHERE status = :status
    ORDER BY id ASC
    LIMIT :maxRows
    OFFSET :offsetRows
    """)
Flux<CustomerRow> readStatusChunk(
    @Param("status") String status,
    @Param("maxRows") int maxRows,
    @Param("offsetRows") long offsetRows
);
~~~

`maxRows` và `offsetRows` là các giá trị bind bình thường trong SQL này, không phải Pageable/Limit special parameter. Caller phải kiểm tra miền giá trị, chẳng hạn maxRows dương và offsetRows không âm.

Thứ tự được cố định theo id. Nếu cần sort động, không thể bind tên column như một giá trị dữ liệu thông thường rồi kỳ vọng database hiểu nó là identifier. Có thể dùng query builder/template phù hợp hoặc một tập lựa chọn sort được thiết kế rõ ràng.

Các query select phải cung cấp column phù hợp mapping của model/DTO. Nếu query bỏ cột bắt buộc, lỗi materialization hoặc giá trị không mong đợi có thể xuất hiện; đó là vấn đề khác với query keyword.

### 10.3. Năng lực của JDBC cũng cần đọc theo phiên bản và đường query

Spring Data JDBC có hướng dẫn riêng về query method, Page/Slice, Stream và SQL khai báo. Không áp một kết luận cũ về “JDBC không hỗ trợ kiểu X” cho mọi phiên bản mới; cũng không suy query SQL khai báo có mọi khả năng của query derived. [JDBC query methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html).

Khi hỗ trợ một module học hoặc thư viện nhiều phiên bản, hãy ghi rõ phiên bản tối thiểu của khả năng đang dùng và kiểm chứng trên dependency thực tế.

## 11. Projection, wrapper và coroutine cần hợp đồng riêng

### 11.1. DTO không phải một lớp bọc tùy ý có thể gán vào mọi query

Khi repository trả projection/DTO, hãy kiểm tra:

- Property hoặc column query cung cấp có khớp dữ liệu cần tạo kết quả không.
- Interface projection có accessor phù hợp không.
- DTO constructor có được chọn và nhận đủ dữ liệu không.
- Kiểu nullable và primitive/default có phản ánh đúng dữ liệu không.
- Module có hỗ trợ loại projection trong đường query đang dùng không.

Lỗi tạo DTO sau khi query đã chạy không tự chứng minh kiểu List hoặc Mono ngoài cùng bị cấm.

Ví dụ projection JPA cho model mẫu:

~~~java
public interface CustomerName {
    String getFullName();
}
~~~

~~~java
List<CustomerName> findNamesByStatus(String status);
~~~

Đây là method có tên riêng trong repository JPA phù hợp. Cần kiểm thử giá trị projection thật, không chỉ kiểm tra proxy trả về một object không null.

Với dynamic projection, một khai báo có thể là:

~~~java
<T> List<T> findByStatus(String status, Class<T> projectionType);
~~~

Khi Class được nhận diện là tham số chọn dynamic projection, nó không còn có cùng vai trò với một giá trị bind nghiệp vụ bình thường. Nếu query cần một Class làm dữ liệu tham số, phải thiết kế signature và query theo cách module nhận diện đúng. [Projections và dynamic projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

Không đổi generic type chỉ để làm compiler im lặng rồi ép kiểu kết quả. Compiler không xác nhận query backend đã trả đủ dữ liệu cho DTO.

### 11.2. Window và ScrollPosition không chỉ là tên khác của Page và Pageable

Window mô tả một hợp đồng scrolling. Nếu cần dùng, phải xác nhận store/version và loại query hỗ trợ scrolling tương ứng.

Thay Page thành Window trong một signature cũ không tự tạo scroll position hợp lệ. Tương tự, không đưa Pageable vào chỗ một API đòi ScrollPosition rồi xem chúng như hai wrapper có thể đổi cho nhau.

Cần giữ nguyên ý nghĩa của API: truy cập trang có offset/total và tiếp tục từ vị trí scroll giải quyết những nhu cầu khác nhau.

### 11.3. Stream không đồng nghĩa Flux

Java Stream và Reactor Flux có mô hình thực thi, tài nguyên và tiêu thụ khác nhau.

Nếu store hỗ trợ Stream, việc đóng stream và vòng đời transaction/cursor phải được thực hiện đúng. Một method trả List rồi gọi `stream()` ở tầng service chỉ tạo stream trên collection đã tải; nó không chứng minh backend đang cung cấp streaming result.

Đổi return type thành Flux trong repository blocking cũng không tự tạo một cursor reactive.

### 11.4. Coroutine phải dùng đường hỗ trợ coroutine thực tế

Một mẫu interface trong module có khả năng coroutine:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CoroutineCustomerRepository :
    CoroutineCrudRepository<CustomerRow, Long> {

    fun findByStatus(status: String): Flow<CustomerRow>
}
~~~

Đây là biến thể repository cần được cấu hình cho module hỗ trợ, không phải một interface đăng ký thêm tùy ý trong ví dụ JPA.

Từ khóa `suspend` hoặc kiểu Flow không tự làm keyword unsupported trở thành supported, cũng không đổi ngôn ngữ của một query khai báo. Cần có dependency, discovery và hạ tầng reactive/coroutine phù hợp. [Coroutines trong Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/kotlin/coroutines.html).

Nếu một Flow chỉ phát lỗi khi collect, bài test phải quan sát lỗi đó. Đừng xem việc gọi method tạo Flow thành công là bằng chứng store đã chấp nhận toàn bộ truy vấn.

## 12. Quy trình chẩn đoán có thể lặp lại

### Bước 1: Chốt module và phiên bản thực thi

Ghi nhận:

~~~text
Repository interface:
Base interface:
Module Spring Data thực sự quản lý:
Phiên bản Spring Data/Boot theo dependency đã resolve:
Model và loại mapping:
Backend/dialect:
Method gây lỗi cùng đầy đủ generic type:
~~~

Khi có nhiều Spring Data module, kiểm tra package scan và store binding. Một interface generic dùng chung hoặc model được gắn nhiều loại annotation có thể khiến giả định về module quản lý không đúng.

Đừng chẩn đoán dựa vào tên folder “jpa” hoặc chỉ dựa vào loại database. PostgreSQL có thể được truy cập qua JPA, JDBC hoặc R2DBC, với các hợp đồng repository khác nhau.

### Bước 2: Xác định đường query

Cần biết method được xử lý như:

- CRUD method được base implementation cung cấp.
- Query derive từ tên.
- Query khai báo bằng annotation hoặc named query.
- Fragment/custom implementation.
- Một method tự viết ở service.

Một method tự viết trong fragment có thể trả wrapper do ứng dụng tạo. Điều đó không có nghĩa query method được derive tự động hỗ trợ wrapper giống hệt.

Nếu mong đợi custom implementation nhưng method bị đưa vào query derivation, hãy kiểm tra wiring fragment. Thêm keyword vào tên method không sửa được một fragment chưa được ghép vào repository.

### Bước 3: Phân tích chữ ký thành các thành phần

Ví dụ:

~~~java
Page<Customer> findByStatus(String status, Pageable pageable);
~~~

Phân tích:

~~~text
Return wrapper: Page
Element type: Customer
Subject: find
Predicate: status bằng một giá trị
Bindable parameter: status
Special parameter: Pageable
Mapping target: Customer
~~~

Với method phức tạp hơn, liệt kê cả operator, số bindable parameter và property path. Cách này thường giúp thấy nhanh một Between thiếu cận hoặc một Pageable bị tưởng là giá trị query.

### Bước 4: Đọc cause có ý nghĩa và giữ thông tin gốc

| Đầu mối trong lỗi | Hướng kiểm tra |
| --- | --- |
| Không tạo được query method | Chữ ký, keyword, query khai báo và binding |
| Không tìm thấy property | Tên property/domain path và việc method có đáng lẽ thuộc fragment không |
| Unsupported keyword | Keyword được module/query creator hỗ trợ |
| Special parameter/parameter combination bị từ chối | Import, số lần xuất hiện và tổ hợp |
| Kiểu execution/return wrapper bị từ chối | Module, blocking/reactive và generic lồng nhau |
| Incorrect result size | Cardinality, predicate và dữ liệu |
| Constructor/converter/materialization lỗi | DTO/entity mapping và cột được select |
| SQL/operator/function lỗi ở server | Dialect, ngôn ngữ query, schema và capability engine |

Các mô tả trên là hướng phân loại, không phải quy tắc một exception class chỉ có duy nhất một nguyên nhân.

Khi báo lỗi, giữ cả method, cause chain và query liên quan nếu đã có. Chỉ ghi dòng “application không chạy” sẽ làm mất bằng chứng cần cho việc sửa đúng tầng.

### Bước 5: Rút gọn về một method và một fixture đủ phân biệt

Cố định module/store, dùng một property đơn giản có thật và một query nhỏ. Sau đó chỉ thay một yếu tố:

1. Đổi wrapper nhưng giữ predicate.
2. Loại special parameter xung đột.
3. Đổi keyword theo đúng yêu cầu nghiệp vụ.
4. Nếu cần, chuyển sang query khai báo có ngôn ngữ đúng.
5. Cuối cùng mới mở rộng lại projection, paging và custom logic.

Đừng cùng lúc đổi module, schema, kiểu trả về và keyword rồi kết luận một trong các thay đổi đã sửa nguyên nhân gốc.

### Bước 6: Kiểm chứng kết quả nghiệp vụ sau khi hết lỗi

Một context khởi động thành công chưa chứng minh query đúng.

Hãy quan sát:

- Những bản ghi nào được trả.
- Thứ tự có ổn định không.
- Page/Slice/total có đúng nghĩa không.
- Các field projection được map đúng không.
- Null/empty và nhiều kết quả được xử lý đúng hợp đồng không.
- Với reactive/coroutine, completion/error có thực sự được quan sát không.

## 13. Kiểm thử để tránh biến một lỗi khởi tạo thành lỗi dữ liệu âm thầm

### 13.1. Parser test chỉ chứng minh mức parser

Ví dụ unit test thuần:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.data.repository.query.parser.Part;
import org.springframework.data.repository.query.parser.PartTree;

class QueryKeywordParsingTest {

    @Test
    void recognizesRegexWithoutProvingStoreExecution() {
        PartTree tree = new PartTree(
            "findByFullNameRegex",
            Customer.class
        );

        Part first = tree.getParts().iterator().next();

        assertEquals(Part.Type.REGEX, first.getType());
    }
}
~~~

Test này không khởi động JPA, không tạo CriteriaQuery và không gọi database. Nó giúp minh họa rằng parser nhận Regex chưa đủ chứng minh store thực thi được Regex.

Muốn kiểm tra JPA từ chối method sai, cần một context test cô lập đăng ký repository tương ứng. Muốn chứng minh native regex chạy đúng, cần test integration trên backend có operator đó.

### 13.2. Tách test âm và test dương

| Test | Mục tiêu |
| --- | --- |
| Context chỉ có repository với signature sai | Nhận đúng lỗi ở giai đoạn tạo query/cấu hình |
| Context có signature đã sửa | Repository khởi tạo được trong module đã chọn |
| Integration query với fixture phân biệt | Query trả đúng dữ liệu, không chỉ hết exception |
| Mapping/projection test | Kết quả chứa đủ và đúng field |
| Reactive/Flow test | Quan sát dữ liệu lẫn terminal condition |
| Regression test cho API service | Giữ đúng hợp đồng total/cardinality sau khi thay chữ ký |

Không đăng ký hàng loạt repository sai trong cùng một negative test rồi phụ thuộc vào lỗi nào xuất hiện đầu tiên. Thứ tự khởi tạo có thể khiến một method che lỗi của method khác.

Các method cố ý sai trong bài chỉ dùng để phân tích; khi đưa ví dụ vào dự án, giữ chúng trong fixture negative test được cô lập thay vì cùng package scan của ứng dụng đang chạy.

### 13.3. Fixture phải làm lộ khác biệt semantics

Đối với ví dụ regex/containing, có thể dùng dữ liệu:

~~~text
Lan
Lun
L.n
Bình
~~~

Một test chỉ có `Lan` rất khó phân biệt query regex với một cách sửa không giữ đúng ý nghĩa. Cần kiểm tra đầu vào có ký tự mang ý nghĩa riêng trong pattern hoặc wildcard nếu hợp đồng có trường hợp đó.

Đối với phân trang, dùng:

- Số bản ghi lớn hơn page size.
- Nhiều bản ghi cùng giá trị sort chính.
- Một khóa sort phụ ổn định.
- Bản ghi không khớp predicate để phát hiện điều kiện lọc bị bỏ sót.
- Trang cuối và trường hợp không có kết quả.

Đối với query một kết quả, có riêng tình huống 0, 1 và nhiều bản ghi nếu nghiệp vụ cho phép tạo fixture đó.

Các ví dụ kiểm thử ở đây là hướng dẫn thiết kế; chưa có báo cáo chạy test trên một dự án cụ thể.

## 14. Chọn cách sửa mà vẫn giữ hợp đồng

| Vấn đề đã xác định | Cách sửa có thể cân nhắc | Điều phải giữ |
| --- | --- | --- |
| Page query thiếu Pageable | Bổ sung Pageable hoặc chọn hợp đồng khác | Ý nghĩa trang và total |
| Pageable + Sort | Đưa sort vào Pageable | Thứ tự và kích thước trang |
| Pageable + Limit | Chọn một cơ chế theo mục tiêu | Giới hạn dữ liệu thực tế |
| Top/First + Limit | Giữ giới hạn cố định hoặc động phù hợp | Số kết quả và cách chọn phần tử |
| Mono<Page<T>> không được R2DBC query execution hỗ trợ | Flux theo trang và count riêng ở service nếu cần | Reactive API và semantics tổng số |
| Keyword không có trong module | Keyword tương đương thật sự, query khai báo hoặc fragment | Predicate nghiệp vụ |
| Engine có khả năng nhưng derived query không diễn đạt | Query/template đặc thù store | Binding, mapping và giới hạn phụ thuộc backend |
| Projection không map được | Chỉnh field/alias/constructor đúng hợp đồng | Dữ liệu cần thiết của DTO |
| Query đơn có nhiều kết quả | Sửa dữ liệu/invariant hoặc đổi cardinality đúng nghiệp vụ | Không che vi phạm duy nhất |
| Fragment không được ghép | Sửa discovery/wiring | Method chạy ở implementation dự định |

Nếu đã chọn fragment/template để dùng khả năng đặc thù, hãy giữ nó như một phần mở rộng có ranh giới rõ ràng. Không làm cả hệ abstraction giả vờ rằng mọi store đều hỗ trợ cùng tập operator.

Ngược lại, cũng không cần bỏ toàn bộ repository chỉ vì một truy vấn cần custom implementation. CRUD, derived queries phổ biến, projection và các extension đặc thù có thể cùng tồn tại khi hợp đồng được phân định rõ.

## 15. Tự kiểm tra kiến thức

1. Vì sao keyword xuất hiện trong Commons chưa chứng minh module store hỗ trợ nó?
2. Một lỗi property path khác unsupported keyword ở tầng nào?
3. Page<Customer> thiếu Pageable cần được chẩn đoán như thế nào?
4. Vì sao bọc Page trong Mono không tự tạo khả năng paging execution cho R2DBC?
5. Pageable kết hợp Sort hoặc Limit có vấn đề gì?
6. First/Top kết hợp Limit khác First/Top kết hợp Pageable ra sao?
7. Vì sao một Between có tổng cộng hai đối số Java vẫn có thể thiếu giá trị bind?
8. Khi nào đổi Regex thành Containing làm sai chức năng dù application đã khởi động?
9. Thêm Query có thể đổi ngôn ngữ và khả năng query method như thế nào?
10. Vì sao Optional có nhiều kết quả không tự là lỗi kiểu trả về unsupported?
11. Dynamic projection ảnh hưởng vai trò của Class<T> parameter ra sao?
12. Cần kiểm tra gì để chứng minh một cách sửa giữ đúng paging, sorting, projection và cardinality?

Chẩn đoán loại lỗi này bắt đầu từ module, phiên bản, đường query và chữ ký method đầy đủ. Chọn kiểu trả về, special parameter và keyword theo khả năng thực thi của store, rồi kiểm tra kết quả nghiệp vụ giúp sửa đúng nguyên nhân thay vì chỉ làm mất exception khởi tạo.
