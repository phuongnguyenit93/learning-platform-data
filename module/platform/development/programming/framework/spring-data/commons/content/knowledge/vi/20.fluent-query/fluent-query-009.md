# Tái sử dụng mô hình lọc mà giữ rõ phạm vi store

## 1. Vấn đề: cùng yêu cầu tìm kiếm, khác cách lưu trữ

Một ứng dụng có thể tìm khách hàng trong cơ sở dữ liệu quan hệ hoặc một collection tài liệu. Ở cả hai nơi, yêu cầu nghiệp vụ có thể giống nhau:

- Lọc theo quốc gia.
- Tìm tên bắt đầu bằng một tiền tố.
- Chọn khách hàng đang hoặc không còn hoạt động.
- Trả về một trang thông tin ngắn gọn.

Spring Data Commons cung cấp các abstraction như `Example`, `ExampleMatcher`, `Pageable` và `FluentQuery` để biểu diễn nhiều phần của luồng này. Tuy nhiên, abstraction chung không làm các kho dữ liệu có cùng mô hình ánh xạ, collation, index hoặc cách thực thi.

Mục tiêu tái sử dụng hợp lý là:

> Giữ chung ý nghĩa bộ lọc và hợp đồng kết quả; ánh xạ điều kiện, thuộc tính và khả năng thực thi tại adapter của từng store.

Trong bài này, **store** là loại kho dữ liệu cùng Spring Data module thực thi truy vấn, chẳng hạn JPA cho dữ liệu quan hệ hoặc MongoDB cho tài liệu. Ví dụ minh họa hai adapter đồng bộ; không coi chúng là một triển khai đồng nhất cho mọi module Spring Data.

Sau bài học, bạn có thể:

- Tách mô hình lọc nghiệp vụ khỏi entity và document.
- Dựng `Example` phù hợp với từng kiểu domain được lưu.
- Tái sử dụng callback khi các khả năng cần thiết thực sự tương thích.
- Xác định phần nào cần giữ riêng ở adapter.
- Tránh cam kết quá mức về projection, sắp xếp, phân trang và tính nhất quán giữa các store.

## 2. Ba lớp cần phân biệt

| Lớp | Chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| Mô hình lọc dùng chung | Ý nghĩa đầu vào, chuẩn hóa và kiểm tra quy tắc | `CustomerFilter` |
| Ánh xạ theo store | Chuyển bộ lọc thành probe, matcher và đường dẫn thuộc tính | `Example<CustomerEntity>` hoặc `Example<CustomerDocument>` |
| Thực thi và trả kết quả | Gọi repository, chọn projection, phân trang và chuyển kết quả | `findBy(example, callback)` |

~~~mermaid
flowchart TD
    F["CustomerFilter: ý nghĩa bộ lọc"] --> J["Mapper JPA"]
    F --> M["Mapper MongoDB"]
    J --> JE["Example của CustomerEntity"]
    M --> ME["Example của CustomerDocument"]
    JE --> JR["JPA repository và callback"]
    ME --> MR["MongoDB repository và callback"]
    JR --> R["Page của CustomerSummary"]
    MR --> R
~~~

Hai nhánh cùng trả một hợp đồng dữ liệu cho tầng gọi, nhưng vẫn có implementation, giới hạn và đặc điểm thực thi riêng.

### 2.1. Không dùng entity làm mô hình lọc chung

Một entity JPA có thể chứa ID, quan hệ, phiên bản optimistic locking và metadata auditing. Document có thể có những thuộc tính, ID hoặc cấu trúc lồng khác.

Nếu dùng trực tiếp một trong hai làm đầu vào tìm kiếm chung:

- Tầng gọi phải biết chi tiết của store đó.
- Trường được gán sẵn có thể vô tình trở thành điều kiện QBE.
- Chuyển sang store khác dễ kéo theo phụ thuộc ánh xạ.
- Giá trị `null` vừa có thể biểu thị thiếu bộ lọc, vừa bị hiểu thành trạng thái dữ liệu.

Một kiểu đầu vào riêng giúp quy định rõ tiêu chí nào có mặt mà không mang theo trạng thái persistence không liên quan.

### 2.2. Không dùng đối tượng fluent query làm mô hình lọc

`FetchableFluentQuery` là đối tượng được repository cung cấp trong một lần thực thi callback. Nó không phải DTO bộ lọc có thể lưu, truyền qua tầng ứng dụng rồi dùng lại về sau.

Có thể dùng lại dữ liệu bộ lọc hoặc một hàm callback không giữ trạng thái thực thi. Không giữ lại đối tượng query từ lần gọi trước để thực thi với repository khác.

## 3. Định nghĩa hợp đồng bộ lọc

Các ví dụ dùng cú pháp `record` của Java 17 trở lên. Mỗi kiểu `public` đặt trong file Java riêng khi đưa vào ứng dụng thực hành; những file này chỉ là mã minh họa trong bài.

~~~java
import java.util.Locale;

public record CustomerFilter(
        String country,
        String namePrefix,
        Boolean active) {

    public CustomerFilter {
        country = trimToNull(country);
        if (country != null) {
            country = country.toUpperCase(Locale.ROOT);
        }

        namePrefix = trimToNull(namePrefix);
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

Hợp đồng của kiểu này:

| Thuộc tính | Giá trị có mặt | Giá trị vắng mặt |
| --- | --- | --- |
| `country` | Khớp mã quốc gia đã chuẩn hóa chữ hoa | `null`: không lọc quốc gia |
| `namePrefix` | Tên bắt đầu bằng tiền tố, yêu cầu bỏ qua hoa thường | `null`: không lọc tên |
| `active` | `true` hoặc `false` là điều kiện cụ thể | `null`: không lọc trạng thái |

Chuỗi rỗng hoặc chỉ có khoảng trắng được chuẩn hóa thành `null`. Đây là quy tắc ứng dụng chủ động chọn, không phải hành vi QBE tự áp dụng.

Dữ liệu được lưu cũng cần tuân thủ quy ước mã quốc gia. Chuẩn hóa riêng đầu vào thành `VN` không tự sửa những bản ghi đã lưu dưới một quy ước khác.

Đối với tên, “bỏ qua hoa thường” chưa định nghĩa đầy đủ cách xử lý dấu tiếng Việt, Unicode hoặc thứ tự ngôn ngữ. Nếu nghiệp vụ yêu cầu các kết quả giống hệt nhau giữa nhiều store, phải quy định và kiểm chứng các trường hợp đó. Không mặc định `ignoreCase()` có cùng cách thực thi trên mọi kho.

### 3.1. Boolean phải biểu diễn được ba trạng thái

~~~java
CustomerFilter activeOnly =
        new CustomerFilter("vn", " An ", true);

CustomerFilter inactiveOnly =
        new CustomerFilter("VN", null, false);

CustomerFilter anyActivity =
        new CustomerFilter("VN", null, null);
~~~

Nếu thay `Boolean` bằng `boolean`, trạng thái mặc định `false` không còn phân biệt được “không cung cấp bộ lọc” với “chỉ lấy khách hàng không hoạt động”.

Tương tự, nếu cần tìm những bản ghi có một trường thực sự `null`, hợp đồng nên có cách biểu diễn riêng, chẳng hạn một enum `ANY / IS_NULL / HAS_VALUE`. Không dùng cùng một `null` để mang hai ý nghĩa mâu thuẫn.

### 3.2. Tách thứ tự và cửa sổ trang khỏi điều kiện

~~~java
public enum CustomerOrder {
    NAME_ASC,
    NAME_DESC
}
~~~

~~~java
import java.util.Objects;

public record CustomerPage(
        int number,
        int size,
        CustomerOrder order) {

    public CustomerPage {
        if (number < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Trang phải >= 0; kích thước từ 1 đến 100");
        }

        Objects.requireNonNull(order, "order");
    }
}
~~~

Bộ lọc xác định tập dữ liệu phù hợp. Thứ tự và số trang xác định cách đọc tập đó. Tách hai khái niệm giúp cùng một `CustomerFilter` phục vụ việc đọc trang, đếm hoặc kiểm tra tồn tại.

Enum thứ tự cũng giúp tầng gọi không phải gửi trực tiếp tên thuộc tính nội bộ như `fullName` hoặc `displayName`.

## 4. Giữ mô hình lưu trữ riêng cho từng adapter

Giả sử JPA dùng thuộc tính Java `fullName`, còn MongoDB dùng `displayName`. Hai thuộc tính đều phục vụ khái niệm “tên hiển thị” của nghiệp vụ.

### 4.1. Mô hình JPA

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class CustomerEntity {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "full_name")
    private String fullName;

    private String country;
    private Boolean active;

    public CustomerEntity() {
    }

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
    public String getCountry() { return country; }
    public Boolean getActive() { return active; }

    public void setFullName(String value) { fullName = value; }
    public void setCountry(String value) { country = value; }
    public void setActive(Boolean value) { active = value; }
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaCustomerRepository
        extends JpaRepository<CustomerEntity, Long> {
}
~~~

### 4.2. Mô hình MongoDB

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field("display_name")
    private String displayName;

    private String country;
    private Boolean active;

    public CustomerDocument() {
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public String getCountry() { return country; }
    public Boolean getActive() { return active; }

    public void setDisplayName(String value) { displayName = value; }
    public void setCountry(String value) { country = value; }
    public void setActive(Boolean value) { active = value; }
}
~~~

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoCustomerRepository
        extends MongoRepository<CustomerDocument, String> {
}
~~~

Hai repository thuộc hai module khác nhau. Khi đặt cả hai trong một ứng dụng, cấu hình package quét repository, domain và hạ tầng kết nối phải phân biệt rõ. Tên bean khác nhau không thay thế việc cấu hình repository factory đúng module.

### 4.3. Dùng đường dẫn thuộc tính domain trong matcher và sort

| Khái niệm | JPA | MongoDB |
| --- | --- | --- |
| Thuộc tính tên trong Java | `fullName` | `displayName` |
| Tên trường lưu trữ minh họa | `full_name` | `display_name` |
| Đường dẫn dùng cho matcher | `"fullName"` | `"displayName"` |
| Đường dẫn dùng cho sắp xếp theo tên | `"fullName"` | `"displayName"` |

Với các API ánh xạ theo domain trong ví dụ, dùng tên thuộc tính Java; adapter chịu trách nhiệm chuyển sang tên trường lưu trữ. Không lấy tên cột hoặc tên field vật lý làm một chuẩn chung cho mọi store.

## 5. Ánh xạ cùng bộ lọc thành hai Example

### 5.1. Mapper JPA

~~~java
import java.util.Objects;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class JpaCustomerExamples {

    private JpaCustomerExamples() {
    }

    public static Example<CustomerEntity> from(
            CustomerFilter filter) {

        Objects.requireNonNull(filter, "filter");

        CustomerEntity probe = new CustomerEntity();
        probe.setCountry(filter.country());
        probe.setFullName(filter.namePrefix());
        probe.setActive(filter.active());

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withIgnorePaths("id")
                .withMatcher(
                        "fullName",
                        ExampleMatcher.GenericPropertyMatchers
                                .startsWith()
                                .ignoreCase());

        return Example.of(probe, matcher);
    }
}
~~~

### 5.2. Mapper MongoDB

~~~java
import java.util.Objects;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public final class MongoCustomerExamples {

    private MongoCustomerExamples() {
    }

    public static Example<CustomerDocument> from(
            CustomerFilter filter) {

        Objects.requireNonNull(filter, "filter");

        CustomerDocument probe = new CustomerDocument();
        probe.setCountry(filter.country());
        probe.setDisplayName(filter.namePrefix());
        probe.setActive(filter.active());

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withIgnorePaths("id")
                .withMatcher(
                        "displayName",
                        ExampleMatcher.GenericPropertyMatchers
                                .startsWith()
                                .ignoreCase());

        return Example.of(probe, matcher);
    }
}
~~~

Các mapper cùng thể hiện ý định nghiệp vụ, nhưng mỗi mapper biết đúng kiểu probe và tên thuộc tính của store mình.

Điểm dùng chung là `CustomerFilter` và quy tắc xử lý đầu vào. Không cần ép hai mapper thành một hàm generic nhận hàng loạt tên field dạng chuỗi chỉ để giảm vài dòng code.

### 5.3. Vì sao không dùng một Example cho cả hai?

`Example<CustomerEntity>` chứa một probe thuộc mô hình JPA. Nó không tự trở thành `Example<CustomerDocument>` khi chuyển sang MongoDB.

Ép kiểu generic không chuyển đổi:

- Kiểu runtime của probe.
- Metadata ánh xạ.
- Tên thuộc tính trong matcher.
- Cấu trúc quan hệ hoặc tài liệu.
- Ngữ nghĩa ID của domain.

Cần dựng `Example` mới cho đúng model. Việc tái sử dụng một đối tượng matcher chỉ hợp lý khi toàn bộ đường dẫn và quy tắc liên quan thực sự phù hợp; trong ví dụ này, đường dẫn tên đã khác nhau.

Mỗi lần dựng bộ lọc nên tạo probe mới. Không giữ một probe chung trong singleton service rồi sửa nó theo từng request; `Example` giữ tham chiếu đến probe nên trạng thái dùng chung có thể làm các yêu cầu ảnh hưởng lẫn nhau.

## 6. Chia sẻ hợp đồng kết quả, giữ projection theo adapter

Giả sử tầng ứng dụng chỉ cần một ID có thể truyền ra ngoài và tên hiển thị:

~~~java
public record CustomerSummary(
        String id,
        String displayName) {
}
~~~

Mỗi adapter có thể dùng projection phù hợp với domain của nó:

~~~java
public interface JpaCustomerView {
    Long getId();
    String getFullName();
}
~~~

~~~java
public interface MongoCustomerView {
    String getId();
    String getDisplayName();
}
~~~

Hai projection này phục vụ cùng một kết quả nghiệp vụ nhưng có tên getter và kiểu ID khác nhau. Adapter chuyển chúng sang `CustomerSummary` sau khi truy vấn.

`as(ProjectionType.class)` yêu cầu Spring Data ánh xạ kết quả theo kiểu đích; đó không phải phép ép kiểu Java. Ví dụ giả định module và phiên bản đang dùng hỗ trợ QBE fluent cùng các projection interface đơn giản này. Nếu dạng projection mong muốn không được hỗ trợ, chọn một cách ánh xạ khác có chủ đích tại adapter.

Chuyển `Long` thành `String` chỉ thống nhất định dạng truyền tải. Nó không làm ID từ hai store trở thành cùng một định danh nghiệp vụ. Nếu hợp nhất dữ liệu từ nhiều nguồn, cần một mã nghiệp vụ chung hoặc thông tin nguồn phù hợp.

## 7. Tái sử dụng callback ở mức nào?

### 7.1. Callback có thể dùng chung khi không mang tên thuộc tính riêng

Một hành vi đơn giản là “chọn projection và trả về trang” có thể viết bằng API Commons:

~~~java
import java.util.Objects;
import java.util.function.Function;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.query.FluentQuery;

public final class ReadPlans {

    private ReadPlans() {
    }

    public static <T, P> Function<
            FluentQuery.FetchableFluentQuery<T>,
            Page<P>> pageAs(
                    Class<P> projectionType,
                    Pageable pageable) {

        Objects.requireNonNull(projectionType, "projectionType");
        Objects.requireNonNull(pageable, "pageable");

        return query -> query
                .as(projectionType)
                .page(pageable);
    }
}
~~~

Hàm này tái sử dụng **cách lấy kết quả**, không tái sử dụng query đang chạy. Nó nhận vào kiểu projection và cấu hình trang do adapter đã lựa chọn.

Tính generic của hàm không chứng minh mọi store hỗ trợ mọi kiểu projection. Adapter vẫn chịu trách nhiệm chọn đầu vào phù hợp và bảo đảm khả năng thực thi.

### 7.2. Đối tượng query chỉ sống trong lần gọi findBy

Cách sử dụng đúng:

~~~java
Page<JpaCustomerView> rows = repository.findBy(
        JpaCustomerExamples.from(filter),
        ReadPlans.pageAs(JpaCustomerView.class, pageable));
~~~

Ở đây `repository` là `JpaCustomerRepository`, `filter` là `CustomerFilter` và `pageable` do adapter JPA tạo.

Không trả query ra ngoài để dùng lại:

~~~java
// Không hợp lệ: callback phải trả kết quả, không trả fluent query.
// repository.findBy(example, query -> query);
~~~

Không lưu query vào field của helper, không đưa query vào một tác vụ chạy sau callback và không thử chuyển query đó sang repository khác.

Nếu cần chạy lại cùng yêu cầu, dùng lại mô hình lọc và gọi repository lần nữa. Nếu cần cache dữ liệu, cache kết quả theo một chính sách rõ ràng; không cache đối tượng thực thi query.

### 7.3. Helper chỉ đáng dùng khi làm rõ ý định

Với một callback ngắn, viết trực tiếp vẫn rất rõ:

~~~java
Page<JpaCustomerView> rows = repository.findBy(
        JpaCustomerExamples.from(filter),
        query -> query
                .as(JpaCustomerView.class)
                .page(pageable));
~~~

Hai cách diễn đạt cùng một hành vi. Không cần tạo một tầng helper chỉ để che đi mọi lời gọi repository. Phần đáng tái sử dụng trước tiên là hợp đồng bộ lọc và quy tắc nghiệp vụ.

## 8. Hai adapter cùng thực hiện một hợp đồng đọc

### 8.1. Giao diện dùng ở tầng ứng dụng

~~~java
import org.springframework.data.domain.Page;

public interface CustomerReader {

    Page<CustomerSummary> search(
            CustomerFilter filter,
            CustomerPage request);
}
~~~

Giao diện này chủ động dùng `Page` của Commons vì cả hai implementation trong ví dụ là đồng bộ và cùng hỗ trợ phân trang dạng này. Nó không hứa hỗ trợ mọi mô hình thực thi, đặc biệt là reactive.

### 8.2. Adapter JPA

~~~java
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Repository;

@Repository("jpaCustomerReader")
public class JpaCustomerReader implements CustomerReader {

    private final JpaCustomerRepository repository;

    public JpaCustomerReader(JpaCustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Page<CustomerSummary> search(
            CustomerFilter filter,
            CustomerPage request) {

        Objects.requireNonNull(request, "request");

        Sort sort = switch (request.order()) {
            case NAME_ASC -> Sort.by(
                    Sort.Order.asc("fullName"),
                    Sort.Order.asc("id"));
            case NAME_DESC -> Sort.by(
                    Sort.Order.desc("fullName"),
                    Sort.Order.asc("id"));
        };

        PageRequest pageable = PageRequest.of(
                request.number(),
                request.size(),
                sort);

        Page<JpaCustomerView> rows = repository.findBy(
                JpaCustomerExamples.from(filter),
                ReadPlans.pageAs(
                        JpaCustomerView.class,
                        pageable));

        return rows.map(row -> new CustomerSummary(
                row.getId().toString(),
                row.getFullName()));
    }
}
~~~

Adapter biết đường dẫn `fullName` và kiểu ID `Long`. `Page.map` chuyển từng phần tử nhưng giữ metadata của trang; không cần tự dựng lại tổng số từ độ dài trang.

### 8.3. Adapter MongoDB

~~~java
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Repository;

@Repository("mongoCustomerReader")
public class MongoCustomerReader implements CustomerReader {

    private final MongoCustomerRepository repository;

    public MongoCustomerReader(MongoCustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Page<CustomerSummary> search(
            CustomerFilter filter,
            CustomerPage request) {

        Objects.requireNonNull(request, "request");

        Sort sort = switch (request.order()) {
            case NAME_ASC -> Sort.by(
                    Sort.Order.asc("displayName"),
                    Sort.Order.asc("id"));
            case NAME_DESC -> Sort.by(
                    Sort.Order.desc("displayName"),
                    Sort.Order.asc("id"));
        };

        PageRequest pageable = PageRequest.of(
                request.number(),
                request.size(),
                sort);

        Page<MongoCustomerView> rows = repository.findBy(
                MongoCustomerExamples.from(filter),
                ReadPlans.pageAs(
                        MongoCustomerView.class,
                        pageable));

        return rows.map(row -> new CustomerSummary(
                row.getId(),
                row.getDisplayName()));
    }
}
~~~

Adapter biết đường dẫn `displayName`, kiểu ID `String` và repository MongoDB. Nó không sử dụng entity JPA hoặc metadata của JPA để suy ra truy vấn.

Các kiểu tự định nghĩa trong ví dụ cần được import theo package của ứng dụng. Mô hình chung nên nằm ở package không phụ thuộc các kiểu lưu trữ; mapper, projection và repository của mỗi store nằm trong nhánh adapter tương ứng.

### 8.4. Chọn implementation một cách rõ ràng

Nếu cả hai adapter được đăng ký thành bean, constructor chỉ yêu cầu `CustomerReader` sẽ có nhiều ứng viên. Có thể chọn adapter ở tầng cấu hình hoặc dùng qualifier:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class CustomerSearchService {

    private final CustomerReader reader;

    public CustomerSearchService(
            @Qualifier("jpaCustomerReader") CustomerReader reader) {
        this.reader = reader;
    }
}
~~~

Ví dụ này chọn nhánh JPA. Chuyển lựa chọn store không đòi caller biết tên field của entity/document, nhưng vẫn cần cấu hình đúng nguồn dữ liệu và repository factory.

Không suy ra rằng việc có hai implementation đồng nghĩa ứng dụng tự đồng bộ dữ liệu, tự chuyển nguồn khi lỗi hoặc có kết quả giống nhau ở mọi thời điểm. Những hành vi đó là yêu cầu riêng cần được thiết kế rõ.

## 9. Kiểm soát phần hợp đồng chung thực sự có ý nghĩa

Hai adapter có cùng kiểu trả về chưa đủ để nói chúng tương đương. Cần xem ý nghĩa của từng khả năng:

| Khía cạnh | Phần có thể mô tả chung | Phần phải xác định theo store |
| --- | --- | --- |
| Trường lọc | Quốc gia, tiền tố tên, trạng thái | Đường dẫn domain và ánh xạ lưu trữ |
| Kết hợp điều kiện | Trong bài là AND tất cả tiêu chí có mặt | Cách adapter biểu diễn trong truy vấn |
| So khớp chuỗi | Yêu cầu tìm theo tiền tố, bỏ qua hoa thường | Collation, Unicode, biểu thức và khả năng dùng index |
| Giá trị vắng mặt | `null` trong filter nghĩa là không lọc | Khác biệt giữa field thiếu, field null và giá trị lưu |
| Projection | ID và tên cần trả | Kiểu projection, quy tắc ánh xạ và dữ liệu thực sự được đọc |
| Phân trang | Số trang bắt đầu từ 0, kích thước có giới hạn | Chi phí đọc trang, đếm và ảnh hưởng của thay đổi dữ liệu |
| Sắp xếp | Tăng/giảm theo tên | Tên thuộc tính, thứ tự null, collation và kiểu ID |
| Transaction | Yêu cầu nhất quán của nghiệp vụ | Transaction manager và cơ chế của từng kho |
| Thực thi reactive | Một nhu cầu đọc bất đồng bộ riêng nếu có | Interface, kiểu trả về và vòng đời của API reactive |

### 9.1. Quy tắc so khớp không tự đồng nhất

`startsWith().ignoreCase()` thể hiện cùng ý định ở hai mapper. Tuy nhiên, không nên suy ra nó xử lý mọi ký tự tiếng Việt, dấu, dạng Unicode hoặc ký tự đặc biệt giống hệt nhau.

Nếu cần khả năng tìm kiếm đồng nhất cao giữa các nguồn, có thể thiết kế một trường tìm kiếm đã chuẩn hóa tại thời điểm ghi và dùng cùng quy tắc chuẩn hóa ở đầu vào. Khi đó phải định nghĩa cách cập nhật trường này và cách chuyển đổi dữ liệu cũ.

Không tự thay yêu cầu “tiền tố” thành “chứa”, regex tùy ý hoặc full-text chỉ vì một store hỗ trợ thuận tiện hơn. Những thay đổi đó làm thay đổi hợp đồng nghiệp vụ.

### 9.2. Thứ tự ổn định trong một store khác với thứ tự giống nhau giữa hai store

Thêm `id` sau tên giúp phân định khi nhiều khách hàng trùng tên trong cùng store. Nhưng:

- ID `Long` và ID `String` có thể có thứ tự khác nhau.
- Các store có thể sắp xếp chuỗi hoặc `null` theo quy tắc khác.
- Dữ liệu mới hoặc dữ liệu bị xóa vẫn có thể làm các trang dịch chuyển.

Nếu cần thứ tự đối chiếu giữa nhiều store, phải chọn một khóa nghiệp vụ dùng chung và định nghĩa quy tắc sắp xếp phù hợp. Chỉ thêm ID nội bộ không tạo ra bảo đảm đó.

### 9.3. Không âm thầm bỏ qua tiêu chí chưa hỗ trợ

Giả sử sau này có yêu cầu `minimumRevenue` nhưng adapter hiện tại chỉ dùng QBE với các phép khớp giá trị đơn giản.

Nếu adapter bỏ qua tiêu chí mới rồi trả dữ liệu như bình thường, caller sẽ nhận kết quả rộng hơn yêu cầu mà không biết. Đây là lỗi hợp đồng.

Các hướng xử lý hợp lý:

1. Dùng công cụ truy vấn thích hợp tại adapter để thực hiện đúng điều kiện.
2. Tách yêu cầu nâng cao thành một hợp đồng khác nếu nó chỉ thuộc một store.
3. Từ chối rõ ràng yêu cầu chưa được hỗ trợ trước khi trả kết quả.

Không tải toàn bộ dữ liệu rồi lọc trong Java như một cách thay thế mặc định. Cách đó có thể làm sai tổng số, phân trang và tăng mạnh chi phí.

## 10. Khi mở rộng bộ lọc, chọn công cụ tại adapter

QBE phù hợp với một số bộ lọc theo giá trị và chuỗi. Nó không phải công cụ tổng quát cho mọi điều kiện.

| Nhu cầu mới | Vì sao cần xem lại cách triển khai |
| --- | --- |
| Khoảng thời gian hoặc giá trị lớn hơn/nhỏ hơn | Probe không biểu diễn trực tiếp các phép so sánh này |
| Nhóm điều kiện AND/OR lồng nhau | `matchingAll` hoặc `matchingAny` không phải cây điều kiện tùy ý |
| Thống kê theo nhóm, tổng doanh thu | Đây là nhu cầu aggregation, không chỉ lọc thực thể |
| Full-text hoặc xếp hạng độ liên quan | Có đặc điểm và khả năng riêng của từng store |
| Quan hệ hoặc collection phức tạp | Mô hình dữ liệu và cách truy vấn không giống nhau |
| Cursor hoặc scrolling | Vị trí đọc và khả năng hỗ trợ cần được xác định riêng |

Có thể giữ nguyên mô hình lọc chung nếu ý nghĩa nghiệp vụ vẫn thực hiện được ở các adapter. Implementation JPA có thể chuyển sang một công cụ như Specifications hoặc truy vấn tùy chỉnh; implementation MongoDB có thể dùng API truy vấn hoặc aggregation phù hợp.

Điều cần giữ là hợp đồng đầu vào/đầu ra và ngữ nghĩa đã công bố. Không bắt buộc cả hai store phải tiếp tục dùng `Example` chỉ để có code bề ngoài giống nhau.

Nếu một trường chỉ có ý nghĩa ở một nguồn, ví dụ lựa chọn tìm kiếm đặc thù theo cấu trúc tài liệu, hãy cân nhắc một kiểu yêu cầu riêng. Tránh nhét mọi đặc tính của tất cả store vào một DTO chung đầy tham số mà mỗi adapter chỉ hiểu một phần.

## 11. Cùng mô hình lọc cho tìm, đếm và tồn tại

Một mapper `from(filter)` có thể dùng cho các thao tác khác nhau trong đúng adapter:

~~~java
CustomerFilter filter =
        new CustomerFilter("VN", "An", true);

Example<CustomerEntity> example =
        JpaCustomerExamples.from(filter);

long total = jpaRepository.count(example);
boolean present = jpaRepository.exists(example);
~~~

Hoặc dùng fluent callback nếu phù hợp với cách tổ chức code:

~~~java
long total = jpaRepository.findBy(
        JpaCustomerExamples.from(filter),
        query -> query.count());

boolean present = jpaRepository.findBy(
        JpaCustomerExamples.from(filter),
        query -> query.exists());
~~~

Các đoạn trên là những lựa chọn riêng, không có nghĩa cần gọi tất cả trong cùng một request.

Đối với MongoDB, dùng mapper và repository MongoDB tương ứng. Không lấy `Example<CustomerEntity>` truyền sang repository tài liệu.

Những điểm cần giữ:

- Tổng số phải dùng cùng định nghĩa bộ lọc với danh sách.
- `exists` trả lời về toàn bộ tập phù hợp, không chỉ nội dung một trang.
- Nếu `Page` đã cung cấp tổng số cần hiển thị, thường không cần gọi `count` thêm.
- Các lần đọc riêng không mặc nhiên quan sát cùng một trạng thái dữ liệu.
- Một mô hình lọc dùng chung không tạo transaction xuyên nhiều store.

Khi ứng dụng có nhiều transaction manager, phạm vi transaction cần được cấu hình phù hợp với adapter. Không suy ra một annotation transaction bất kỳ sẽ bao phủ đồng nhất tất cả nguồn dữ liệu.

Nếu adapter trả stream hoặc dùng reactive API, hợp đồng vòng đời và quản lý tài nguyên cũng cần được thể hiện riêng. Không dùng chung một callback giữ query sống lâu để che đi khác biệt đó.

## 12. Minh họa hợp đồng trên dữ liệu tương ứng

Giả sử hai store đã được cung cấp các khách hàng có cùng dữ liệu nghiệp vụ dưới đây. ID nội bộ của hai nguồn có thể khác.

| Khách hàng | Tên | Quốc gia | active |
| --- | --- | --- | --- |
| A | An Nguyen | VN | true |
| B | Anh Pham | VN | true |
| C | Binh Tran | VN | true |
| D | An Le | VN | false |
| E | An Smith | US | true |

Tạo yêu cầu:

~~~java
CustomerFilter filter =
        new CustomerFilter(" vn ", " an ", true);

CustomerPage request =
        new CustomerPage(0, 20, CustomerOrder.NAME_ASC);
~~~

Sau chuẩn hóa:

~~~text
country = "VN"
namePrefix = "an"
active = true
~~~

Trên dữ liệu minh họa dùng các ký tự ASCII trong tên, hai adapter được kỳ vọng trả về khách hàng A và B sau khi ánh xạ sang kết quả chung. Các khách hàng còn lại bị loại vì tiền tố, trạng thái hoặc quốc gia không phù hợp.

Các trường hợp cần làm rõ khi triển khai thực tế:

| Đầu vào hoặc dữ liệu | Ý nghĩa cần giữ |
| --- | --- |
| `active = false` | Tìm trạng thái false, không bỏ qua bộ lọc |
| `active = null` | Không đặt điều kiện trạng thái |
| Tiền tố chỉ có khoảng trắng | Sau chuẩn hóa thì không lọc tên |
| Không tiêu chí nào có mặt | Ví dụ này cho phép tìm toàn bộ, nhưng vẫn phân trang |
| Hai người cùng tên | Có tiêu chí phân định trong từng store |
| Tên có dấu hoặc dạng Unicode khác nhau | Cần quy tắc và dữ liệu kiểm chứng theo hợp đồng |
| Tiêu chí không được adapter hỗ trợ | Không bỏ qua âm thầm |
| Trang vượt phạm vi | Nội dung có thể rỗng dù bộ lọc vẫn có kết quả |

Đây là các tình huống minh họa hợp đồng, không phải tuyên bố đã chạy kiểm thử trên một hệ cơ sở dữ liệu cụ thể. Khi áp dụng vào dự án, những bảo đảm nghiệp vụ cần được xác nhận với chính adapter, cấu hình và dữ liệu liên quan.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách tổ chức phù hợp |
| --- | --- | --- |
| Dùng một entity làm DTO lọc cho mọi nguồn | Rò rỉ mapping và điều kiện ngầm | Tạo mô hình lọc nghiệp vụ riêng |
| Ép kiểu một `Example` sang domain khác | Không chuyển được probe hay metadata | Dựng Example theo từng adapter |
| Đưa tên cột hoặc field vật lý vào hợp đồng chung | Caller phụ thuộc schema của store | Dùng tên tiêu chí nghiệp vụ và ánh xạ cục bộ |
| Cho rằng callback generic bảo đảm tương thích | Lỗi projection hoặc thiếu hỗ trợ lúc chạy | Xác định khả năng adapter trước khi tái sử dụng |
| Dùng chung một probe mutable cho nhiều request | Bộ lọc thay đổi ngoài ý muốn | Tạo probe mới mỗi lần dựng Example |
| Giữ query để chạy sau callback | Vượt phạm vi sống được API bảo đảm | Trả kết quả trong callback |
| Tự thay kiểu so khớp khi chuyển store | Hai nguồn trả tập kết quả khác ý nghĩa | Giữ đúng hợp đồng hoặc công bố khác biệt |
| Dùng ID nội bộ để cam kết cùng thứ tự giữa nguồn | Thứ tự có thể khác nhau | Định nghĩa khóa và quy tắc sắp xếp dùng chung nếu cần |
| Thêm mọi tính năng store vào một DTO | Hợp đồng khó hiểu và có tiêu chí bị bỏ qua | Tách phần chung và yêu cầu chuyên biệt |

Tái sử dụng tốt bắt đầu từ một mô hình lọc có ý nghĩa rõ ràng. `Example`, matcher, projection và fluent callback là công cụ triển khai hợp đồng đó; chúng vẫn cần gắn với domain và khả năng thực sự của từng store.
