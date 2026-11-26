# Vai trò của Commons trong hệ sinh thái Spring Data

## Mục tiêu bài học

Spring Data gồm nhiều module phục vụ những công nghệ lưu trữ khác nhau. Spring Data JPA làm việc với mô hình JPA, Spring Data MongoDB làm việc với MongoDB, còn những module khác tích hợp các loại kho dữ liệu tương ứng. **Spring Data Commons là phần nền tảng dùng chung giúp các module này có một hệ thống abstraction và cơ chế repository nhất quán.**

Trong phạm vi module SPRING_DATA_COMMONS, bài học này giải thích vì sao cần tầng dùng chung đó, nó cung cấp những gì và phần nào vẫn thuộc trách nhiệm của từng module lưu trữ. Sau bài học, bạn có thể:

- Đặt Commons đúng vị trí so với Spring Framework, Spring Boot và các module Spring Data cụ thể.
- Nhận diện các abstraction phổ biến: Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing.
- Theo dõi cách một lời gọi repository đi từ hợp đồng Java đến cơ chế truy cập dữ liệu cụ thể.
- Đánh giá phần kiến thức có thể dùng lại khi thay đổi kho dữ liệu và phần phải kiểm tra lại.

## 1. Vì sao Spring Data cần Commons?

Giả sử một hệ thống bán hàng có hai phần:

- Dữ liệu đơn hàng lưu trong cơ sở dữ liệu quan hệ và được truy cập bằng Spring Data JPA.
- Hồ sơ khách hàng linh hoạt về cấu trúc lưu trong MongoDB và được truy cập bằng Spring Data MongoDB.

Dù công nghệ lưu trữ khác nhau, lập trình viên vẫn thường cần những thao tác tương tự: tìm đối tượng theo định danh, lưu đối tượng, lấy một tập kết quả theo điều kiện, sắp xếp và chia kết quả thành các trang.

Nếu mỗi module tự định nghĩa toàn bộ API cho các nhu cầu này, người học phải làm quen với nhiều hệ thống tên gọi và mô hình gần giống nhau. Các module cũng phải duy trì nhiều phần hạ tầng lặp lại.

Commons giải quyết phần chung bằng những hợp đồng và thành phần có thể tái sử dụng. Chẳng hạn, `Repository<T, ID>` mô tả repository quản lý loại đối tượng nào và loại định danh nào; `Pageable` mô tả yêu cầu phân trang; `Sort` mô tả thứ tự kết quả. Các module lưu trữ dùng những thành phần đó để xây dựng trải nghiệm lập trình quen thuộc.

Tuy nhiên, sự nhất quán ở cấp API không làm các cơ sở dữ liệu trở nên giống nhau. Một truy vấn qua JPA vẫn chịu ảnh hưởng của JPA, provider và cơ sở dữ liệu quan hệ; một truy vấn MongoDB vẫn chịu ảnh hưởng của mô hình document, driver và khả năng truy vấn của MongoDB.

> Commons giúp dùng chung cách diễn đạt nhu cầu truy cập dữ liệu. Module lưu trữ chịu trách nhiệm hiện thực nhu cầu đó trên công nghệ cụ thể.

## 2. Vị trí của Commons trong hệ sinh thái

### 2.1. Phân biệt các thành phần thường gặp

| Thành phần | Vai trò chính | Ví dụ điều nó không tự quyết định |
| --- | --- | --- |
| Spring Framework | Cung cấp nền tảng như container, dependency injection, AOP và abstraction giao dịch. | Không tự tạo cách ánh xạ và truy vấn cho mọi kho dữ liệu. |
| Spring Data Commons | Cung cấp abstraction và hạ tầng chung của họ Spring Data. | Không tự chọn cơ sở dữ liệu, driver hay ngôn ngữ truy vấn. |
| Module Spring Data cụ thể | Tích hợp repository, mapping và truy vấn với một công nghệ lưu trữ. | Không làm mọi kho dữ liệu hỗ trợ cùng một tập tính năng. |
| Provider hoặc driver | Thực thi truy cập dữ liệu theo công nghệ được chọn. | Không thay thế toàn bộ hợp đồng repository ở tầng ứng dụng. |
| Spring Boot | Hỗ trợ cấu hình tự động và quản lý dependency khi ứng dụng sử dụng Boot. | Không làm Commons trở thành một engine truy cập dữ liệu độc lập. |

Ví dụ, `spring-data-commons` là thư viện nền tảng; `spring-data-jpa` và `spring-data-mongodb` là các module sử dụng nền tảng đó. Ứng dụng có thể dùng Spring Data mà không dùng Spring Boot, nhưng khi dùng Boot, starter và cấu hình tự động thường giúp việc tích hợp thuận tiện hơn.

### 2.2. Một sơ đồ trách nhiệm

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ của ứng dụng"] --> B["Interface repository của ứng dụng"]
    B --> C["Proxy và cơ chế repository"]
    C --> D["Module Spring Data cho kho dữ liệu"]
    D --> E["Provider hoặc driver"]
    E --> F["Kho dữ liệu"]
    G["Spring Data Commons: hợp đồng, metadata và hạ tầng chung"] -.-> B
    G -.-> C
    G -.-> D
~~~

Sơ đồ thể hiện quan hệ trách nhiệm, không phải danh sách lớp bắt buộc xuất hiện trong mọi lần gọi. Một method repository tùy biến, một truy vấn suy ra từ tên method và một thao tác CRUD có thể đi qua những nhánh thực thi khác nhau.

Điểm cần nhận diện là Commons cung cấp phần nền tảng được nhiều module sử dụng; nó không đứng ở cuối luồng để trực tiếp thực thi mọi truy vấn trên mọi cơ sở dữ liệu.

## 3. Commons cung cấp những nhóm abstraction nào?

### 3.1. Hợp đồng repository và thao tác dữ liệu cơ bản

Một repository thường khai báo hai tham số kiểu:

~~~java
Repository<Customer, Long>
~~~

Trong khai báo này:

- `Customer` là kiểu domain mà repository quản lý.
- `Long` là kiểu định danh.
- Hai tham số này chưa nói đối tượng được lưu trong bảng, document hay cấu trúc nào khác.

Các interface quan trọng trong Commons gồm:

| Interface | Ý nghĩa |
| --- | --- |
| `Repository<T, ID>` | Hợp đồng đánh dấu nền tảng, cho phép hạ tầng nhận diện kiểu domain và kiểu định danh của repository. |
| `CrudRepository<T, ID>` | Cung cấp hợp đồng cho các thao tác tạo, đọc, cập nhật và xóa thường gặp. |
| `ListCrudRepository<T, ID>` | Biến thể CRUD trả về `List` ở những thao tác trả nhiều phần tử tương ứng. |
| `PagingAndSortingRepository<T, ID>` | Cung cấp các thao tác truy vấn theo yêu cầu phân trang hoặc sắp xếp. |
| `ReactiveCrudRepository<T, ID>` | Cung cấp hợp đồng CRUD theo mô hình reactive cho các module có hỗ trợ tương ứng. |

`Repository` tự nó không khai báo sẵn toàn bộ các method CRUD. Khi thiết kế repository, ứng dụng chọn những hợp đồng phù hợp hoặc khai báo có chọn lọc các method cần dùng.

Cũng không nên mặc định rằng interface có chữ “PagingAndSorting” luôn kế thừa CRUD. Với hệ interface tách riêng các khả năng này, repository cần cả hai thì khai báo kế thừa cả hai. Mối quan hệ kế thừa cụ thể phải phù hợp với dòng phiên bản dự án đang sử dụng.

Việc một interface có mặt trong thư viện Commons không đồng nghĩa mọi module lưu trữ đều cung cấp mọi dạng repository đó. Chẳng hạn, muốn dùng reactive repository, cần module và cơ chế truy cập dữ liệu hỗ trợ reactive; chỉ đổi interface của một repository JPA không tạo ra luồng truy cập dữ liệu reactive.

### 3.2. Phân trang và sắp xếp

Commons cung cấp một ngôn ngữ chung để diễn đạt yêu cầu truy vấn:

- `Sort`: các thuộc tính cần sắp xếp và chiều tăng hoặc giảm.
- `Pageable`: yêu cầu về trang, kích thước trang và sắp xếp.
- `PageRequest`: một cách tạo đối tượng `Pageable`.
- `Page<T>`: kết quả của một trang, kèm thông tin tổng số phần tử và tổng số trang.
- `Slice<T>`: một phần kết quả, kèm thông tin có thể còn phần tiếp theo, không yêu cầu cung cấp tổng số phần tử như `Page`.

Ví dụ:

~~~java
Pageable request = PageRequest.of(
    0,
    20,
    Sort.by("name").ascending()
        .and(Sort.by("id").ascending())
);
~~~

Yêu cầu này mô tả trang đầu tiên, tối đa 20 phần tử, sắp theo `name` rồi `id`. Chỉ số trang của `PageRequest` bắt đầu từ 0.

Commons định nghĩa cách diễn đạt yêu cầu và hình dạng kết quả. Module lưu trữ quyết định cách chuyển yêu cầu đó thành thao tác cụ thể. Không phải kho dữ liệu nào cũng hỗ trợ mọi phương án phân trang hoặc có cùng chi phí khi bỏ qua nhiều bản ghi.

Để có tổng số phần tử cho `Page`, hệ thống có thể cần thêm truy vấn đếm; một số tình huống có thể suy ra tổng mà không cần thực hiện truy vấn đếm riêng. `Slice` phù hợp khi giao diện chỉ cần biết còn kết quả tiếp theo hay không. Đổi sang `Slice` không tự loại bỏ chi phí của việc truy cập đến vị trí sâu trong tập dữ liệu.

Thêm thuộc tính phân biệt như `id` vào thứ tự sắp xếp giúp giảm sự mơ hồ khi nhiều đối tượng có cùng tên. Dù vậy, dữ liệu thay đổi giữa các lần lấy trang vẫn có thể làm kết quả dịch chuyển; `Pageable` không tự tạo một ảnh chụp nhất quán xuyên suốt nhiều yêu cầu.

### 3.3. Hạ tầng cho derived queries

Một method như sau diễn đạt ý định tìm các khách hàng đang hoạt động có tên bắt đầu bằng một tiền tố:

~~~java
Page<Customer> findByActiveTrueAndNameStartingWith(
    String prefix,
    Pageable pageable
);
~~~

Commons cung cấp các thành phần chung để phân tích tên method, nhận diện cấu trúc điều kiện và xử lý metadata liên quan. Module lưu trữ dùng cấu trúc đó để tạo truy vấn phù hợp với công nghệ của nó.

Ranh giới trách nhiệm gồm hai phần:

1. Có thể phân tích một tên method theo quy tắc chung.
2. Có thể thực thi điều kiện tương ứng trên một kho dữ liệu cụ thể.

Hai điều này không phải lúc nào cũng đồng thời đúng. Tập từ khóa, kiểu dữ liệu và phép toán được hỗ trợ cần được kiểm tra ở module lưu trữ đang dùng.

Tên như `name` hoặc `active` trong derived query thường tham chiếu thuộc tính của mô hình domain. Việc thuộc tính đó ánh xạ sang cột hay trường lưu trữ có tên gì thuộc về cơ chế mapping của module cụ thể.

### 3.4. Projection

Projection giúp diễn đạt hình dạng dữ liệu mà bên gọi muốn nhận, ví dụ:

~~~java
interface CustomerNameView {
    String getName();
}
~~~

Một repository của module có hỗ trợ projection tương ứng có thể khai báo:

~~~java
List<CustomerNameView> findByActiveTrue();
~~~

Commons cung cấp hạ tầng chung để mô tả và tạo một số dạng projection. Module lưu trữ quyết định cách tích hợp projection với việc truy vấn dữ liệu.

Không nên kết luận rằng cứ dùng projection là kho dữ liệu chỉ đọc đúng một trường. Khả năng thu hẹp dữ liệu truy vấn phụ thuộc loại projection, cách khai báo, truy vấn và module lưu trữ. Projection là hợp đồng về dữ liệu nhận được; hiệu quả truy cập dữ liệu phải được đánh giá trong ngữ cảnh cụ thể.

### 3.5. Query by Example

Query by Example diễn đạt truy vấn bằng một đối tượng mẫu và quy tắc đối chiếu:

~~~java
Customer probe = new Customer("An", true);

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "active")
    .withMatcher(
        "name",
        ExampleMatcher.GenericPropertyMatchers.startsWith()
    );

Example<Customer> example = Example.of(probe, matcher);
~~~

Ví dụ sử dụng `Customer` được khai báo trong phần thực hành bên dưới. Ở đây, `active` được bỏ qua có chủ đích để truy vấn chỉ đối chiếu tên; nếu giữ lại một thuộc tính kiểu nguyên thủy như `boolean`, giá trị của nó có thể trở thành một phần điều kiện ngay cả khi người viết chỉ quan tâm đến tên.

Commons cung cấp các kiểu như `Example`, `ExampleMatcher` và hợp đồng `QueryByExampleExecutor`. Để thực thi, repository cần được module lưu trữ hỗ trợ và cung cấp khả năng Query by Example tương ứng.

Query by Example thuận tiện cho một số dạng bộ lọc dựa trên thuộc tính. Nó không phải ngôn ngữ truy vấn tổng quát cho mọi phép kết hợp điều kiện, phép nối hoặc tính toán của cơ sở dữ liệu.

### 3.6. Auditing

Những annotation như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` giúp diễn đạt metadata về thời điểm và chủ thể tạo hoặc sửa đối tượng.

Commons cung cấp các thành phần auditing dùng chung, trong đó có hợp đồng như `AuditorAware` để cung cấp chủ thể hiện tại. Module lưu trữ cần tích hợp và kích hoạt auditing theo cơ chế phù hợp.

Chỉ thêm annotation không bảo đảm dữ liệu auditing được cập nhật trong mọi đường ghi. Ví dụ, một câu lệnh cập nhật trực tiếp ở cơ sở dữ liệu có thể không đi qua cơ chế auditing ở cấp đối tượng. Auditing cũng không tự thay thế lịch sử phiên bản, nhật ký thay đổi đầy đủ hoặc chính sách bảo mật.

### 3.7. Metadata và khả năng mở rộng repository

Để xây dựng repository, hạ tầng phải biết những thông tin như:

- Kiểu domain và kiểu định danh.
- Các method repository cần xử lý.
- Những thuộc tính tồn tại trên mô hình domain.
- Các phần triển khai tùy biến cần ghép vào repository.

Commons có những abstraction cho repository metadata, persistent entity, persistent property và cơ chế factory hỗ trợ tạo repository. Module lưu trữ bổ sung quy tắc mapping và thực thi của riêng mình.

Một hướng mở rộng phổ biến là repository fragment: ứng dụng khai báo một interface hành vi riêng, cung cấp phần triển khai rồi ghép nó vào repository. Commons có hạ tầng hỗ trợ việc ghép các phần hành vi; phần triển khai vẫn có thể dùng `EntityManager`, `MongoTemplate` hoặc API phù hợp với kho dữ liệu.

Đây là lý do mô hình repository có thể mở rộng mà không buộc mọi nghiệp vụ phải được biểu diễn bằng một tên method rất dài.

## 4. Theo dõi một repository JPA cụ thể

Ví dụ dưới đây dùng JPA để làm rõ ranh giới giữa phần chung và phần đặc thù. Các đoạn mã minh họa thuộc một ứng dụng đã cấu hình Spring Data JPA, JPA provider và cơ sở dữ liệu; chúng không phải cấu hình hoàn chỉnh của một dự án.

### 4.1. Đối tượng domain

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private boolean active;

    protected Customer() {
    }

    public Customer(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

`Customer` là đối tượng domain của ví dụ. Các annotation `@Entity`, `@Id` và `@GeneratedValue` ở đây được import từ JPA, không phải từ Commons. Chúng diễn đạt mapping và định danh theo mô hình JPA.

Commons có thể cung cấp hợp đồng repository dùng `Customer` mà không quy định rằng mọi đối tượng domain phải mang `@Entity`.

### 4.2. Interface repository

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {

    Page<Customer> findByActiveTrueAndNameStartingWith(
        String prefix,
        Pageable pageable
    );
}
~~~

Ví dụ chọn rõ hai khả năng: CRUD và phân trang/sắp xếp. Các interface và kiểu `Page`, `Pageable` trong đoạn này thuộc phần abstraction dùng chung của Spring Data.

Mặc dù interface không kế thừa `JpaRepository`, ứng dụng vẫn có thể đăng ký nó thành repository JPA thông qua cấu hình repository JPA phù hợp. Trách nhiệm tạo và thực thi repository không được quyết định chỉ bởi tên interface của ứng dụng; nó còn gắn với module và cấu hình đang quản lý repository đó.

Trong ứng dụng JPA thực tế, `JpaRepository` là một lựa chọn thường gặp khi cần cả những thao tác chuyên biệt của JPA. Interface đó nằm ở Spring Data JPA và xây dựng trên các abstraction chung.

### 4.3. Lời gọi từ tầng nghiệp vụ

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> findActiveCustomers(String prefix) {
        Pageable request = PageRequest.of(
            0,
            20,
            Sort.by("name").ascending()
                .and(Sort.by("id").ascending())
        );

        return repository.findByActiveTrueAndNameStartingWith(
            prefix,
            request
        );
    }
}
~~~

Với giả định repository đã được đăng ký đúng, luồng xử lý có thể hiểu như sau:

1. Spring quản lý một repository proxy và inject nó vào service.
2. Proxy tiếp nhận lời gọi method và chuyển đến cơ chế xử lý phù hợp, chẳng hạn truy vấn suy ra từ tên method.
3. Hạ tầng chung và module JPA sử dụng tên method, tham số, kiểu trả về và mapping để chuẩn bị truy vấn.
4. Module JPA làm việc với `EntityManager`; provider JPA thực hiện phần tương tác với cơ sở dữ liệu.
5. Kết quả được trả về theo hợp đồng `Page<Customer>`.

Commons tham gia bằng các hợp đồng và thành phần hạ tầng. Commons không tự chuyển tất cả truy vấn của mọi module thành SQL.

### 4.4. Đặt đúng kỳ vọng vào `save`

Cũng với repository trên, ứng dụng có thể gọi:

~~~java
Customer saved = repository.save(new Customer("An", true));
~~~

Tên `save` là một phần của hợp đồng chung. Nó không bảo đảm rằng mọi module đều dùng cùng một lệnh, cùng cách nhận diện đối tượng mới hay cùng thời điểm gửi thay đổi xuống kho dữ liệu.

Với JPA, hành vi còn liên quan đến trạng thái entity, persistence context và giao dịch. Với một kho dữ liệu khác, cơ chế lưu có thể khác. Bên gọi nên sử dụng đối tượng mà `save` trả về khi cần trạng thái sau lưu, vì không nên giả định đối tượng trả về luôn là cùng một instance với đầu vào.

## 5. Điều gì dùng lại được khi đổi kho dữ liệu?

Giả sử nhóm chuyển một chức năng từ JPA sang MongoDB. Người học có thể tiếp tục vận dụng kiến thức về repository, tham số phân trang, sắp xếp và cách biểu diễn kết quả. Nhưng việc chuyển đổi vẫn cần xử lý mapping, truy vấn và các đặc tính lưu trữ.

| Nội dung | Phần kiến thức có thể dùng lại | Phần cần đánh giá lại |
| --- | --- | --- |
| `Repository<T, ID>` | Cách biểu diễn domain và định danh trong hợp đồng repository. | Kiểu định danh, cách sinh và biểu diễn định danh trong kho mới. |
| CRUD | Ý nghĩa nghiệp vụ tổng quát của lưu, tìm và xóa. | Cách xác định đối tượng mới, cập nhật, xử lý xung đột và độ nhất quán. |
| Derived queries | Cách đọc tên method theo thuộc tính và điều kiện. | Từ khóa được hỗ trợ, mapping và ngữ nghĩa truy vấn thực tế. |
| `Pageable` và `Sort` | Cách truyền yêu cầu phân trang và sắp xếp. | Khả năng thực thi, index, chi phí phân trang và tính ổn định của kết quả. |
| Projection | Cách mô tả phần dữ liệu cần nhận. | Loại projection được hỗ trợ và mức tối ưu hóa truy vấn. |
| Query by Example | Cách tạo đối tượng mẫu và matcher. | Các phép đối chiếu, kiểu dữ liệu và giới hạn của module đích. |
| Auditing | Ý nghĩa metadata về người và thời điểm thay đổi. | Cách kích hoạt và những đường ghi dữ liệu có đi qua auditing hay không. |
| Repository fragment | Cách tách và ghép hành vi tùy biến. | API truy cập dữ liệu trong phần triển khai. |

Ví dụ, giữ nguyên method `findByActiveTrueAndNameStartingWith` có thể giữ được ý định truy vấn ở tầng ứng dụng. Điều đó chưa chứng minh có thể giữ nguyên toàn bộ lớp domain, kiểu ID, chiến lược index, giao dịch và mọi hành vi của truy vấn.

**Tính dùng lại chủ yếu nằm ở mô hình lập trình và các hợp đồng chung; mức tương đương về hành vi phải được xác nhận cho từng công nghệ lưu trữ.**

## 6. Commons trong ứng dụng dùng nhiều module lưu trữ

Một ứng dụng có thể đồng thời dùng nhiều module Spring Data. Khi đó, hệ thống cần xác định repository nào thuộc module nào.

Nếu mọi repository chỉ kế thừa các interface chung, dấu hiệu từ hệ kế thừa có thể chưa đủ rõ để phân loại. Hạ tầng có thể cần dựa thêm vào những đặc trưng như interface chuyên biệt của module, annotation mapping trên domain và phạm vi cấu hình repository.

Các quyết định thiết kế hữu ích gồm:

- Đặt repository của từng công nghệ trong phạm vi package rõ ràng.
- Cấu hình vùng quét repository để mỗi module quản lý đúng tập repository.
- Dùng mapping phù hợp với từng kho dữ liệu.
- Hiểu rõ tác động nếu cùng một kiểu domain mang dấu hiệu mapping của nhiều module.

Commons cung cấp nền tảng nhận diện và cấu tạo repository, nhưng không tự chọn kho dữ liệu đúng theo ý định nghiệp vụ khi cấu hình của ứng dụng còn mơ hồ.

Chia sẻ abstraction cũng không có nghĩa chia sẻ persistence context hoặc có sẵn một giao dịch nguyên tử xuyên qua mọi kho dữ liệu. Giao dịch trên nhiều công nghệ cần được thiết kế và cấu hình theo khả năng thực tế của các thành phần liên quan.

## 7. Dependency: vì sao thêm Commons riêng thường chưa đủ?

Trong ứng dụng Spring Boot dùng JPA, điểm bắt đầu thường là starter phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

Starter đưa các dependency cần thiết cho tích hợp JPA vào dự án, trong đó Commons xuất hiện thông qua quan hệ phụ thuộc của Spring Data. Ứng dụng vẫn cần driver và cấu hình cơ sở dữ liệu phù hợp với môi trường chạy.

Nếu chỉ thêm `spring-data-commons`, mã có thể tham chiếu được `Repository`, `Pageable` hoặc `Sort`, nhưng điều đó chưa cung cấp một triển khai repository có khả năng truy cập cơ sở dữ liệu bất kỳ. Còn thiếu module tích hợp, cấu hình và các thành phần kết nối cần thiết.

Khi dùng Spring Boot, nên để cơ chế quản lý dependency tương thích của Boot quản lý các phiên bản thuộc bộ Spring Data, trừ khi dự án có chủ đích và đã đánh giá việc ghi đè. Tự ghép các phiên bản Commons và module lưu trữ không tương thích có thể gây lỗi dù mã nguồn dùng những tên interface quen thuộc.

Nếu không dùng Boot, dự án cần tự tổ chức dependency và cấu hình phù hợp; vai trò nền tảng của Commons vẫn giữ nguyên.

## 8. Phân loại vấn đề theo đúng tầng trách nhiệm

Hiểu vai trò của Commons giúp khoanh vùng nguyên nhân thay vì quy mọi vấn đề cho repository.

| Tình huống | Hướng kiểm tra đầu tiên |
| --- | --- |
| Có interface repository nhưng không inject được bean. | Module lưu trữ, cơ chế kích hoạt repository, phạm vi quét và cấu hình ứng dụng. |
| Tên method tham chiếu một thuộc tính không tồn tại. | Mô hình domain, đường dẫn thuộc tính và cách phân tích method. |
| Method dùng một phép toán mà kho dữ liệu không hỗ trợ. | Khả năng truy vấn của module và kho dữ liệu cụ thể. |
| Lấy `Page` chậm trên dữ liệu lớn. | Truy vấn dữ liệu, truy vấn đếm nếu có, index, cách phân trang và nhu cầu thật sự về tổng số phần tử. |
| Metadata auditing không được cập nhật. | Cấu hình auditing của module và đường ghi có đi qua cơ chế auditing hay không. |
| `save` chưa tạo ra thay đổi quan sát được ở nơi khác. | Giao dịch, thời điểm ghi hoặc flush, trạng thái đối tượng và mức nhất quán của kho dữ liệu. |
| Nhiều module cùng phát hiện một repository. | Interface kế thừa, mapping domain và phạm vi cấu hình từng module. |

Bảng này là định hướng phân tích. Để xác định lỗi thực tế, vẫn cần đọc thông báo lỗi và kiểm tra cấu hình của ứng dụng cụ thể.

## 9. Các ngộ nhận cần tránh

### “Commons là một cơ sở dữ liệu chung cho Spring Data”

Commons là thư viện nền tảng, không phải hệ quản trị cơ sở dữ liệu, driver hay bộ máy lưu trữ.

### “Viết interface là có thể dùng với mọi kho dữ liệu”

Interface giúp diễn đạt hợp đồng. Để repository hoạt động, cần module phù hợp và cấu hình hợp lệ; các method được khai báo cũng phải nằm trong khả năng hỗ trợ hoặc có phần triển khai tùy biến.

### “Tên method giống nhau thì hành vi và hiệu năng giống nhau”

Các kho dữ liệu có mô hình, toán tử, index và cơ chế thực thi khác nhau. Sự giống nhau về tên method không bảo đảm ngữ nghĩa và chi phí tương đương trong mọi trường hợp.

### “Dùng abstraction chung thì không cần hiểu công nghệ bên dưới”

Abstraction giảm phần việc lặp lại và giúp mô hình lập trình nhất quán. Các quyết định về mapping, giao dịch, truy vấn, index và hiệu năng vẫn cần kiến thức của công nghệ lưu trữ.

### “Commons bảo đảm repository nào cũng có đủ CRUD, paging và reactive”

Các khả năng được biểu diễn bằng những hợp đồng khác nhau. Repository cần chọn hợp đồng thích hợp, đồng thời module lưu trữ phải thực sự hỗ trợ chúng.

## 10. Bài tập vận dụng

Một nhóm xây dựng màn hình tra cứu khách hàng với yêu cầu:

- Lọc khách hàng đang hoạt động theo tiền tố tên.
- Hiển thị 20 khách hàng mỗi lần.
- Sắp xếp theo tên, dùng ID làm thứ tự phụ.
- Có thể triển khai chức năng bằng JPA hoặc một module hỗ trợ MongoDB.

Hãy phân loại các quyết định sau trước khi chọn công nghệ:

| Quyết định | Thuộc phần nào? |
| --- | --- |
| Dùng `Pageable` để truyền kích thước trang và thứ tự sắp xếp. | Abstraction chung từ Commons. |
| Dùng `Page` khi cần tổng số kết quả hoặc cân nhắc `Slice` khi chỉ cần biết còn dữ liệu. | Hợp đồng kết quả chung, kết hợp với nhu cầu của giao diện. |
| Chọn mapping dạng bảng và quan hệ hoặc dạng document. | Mô hình lưu trữ và module cụ thể. |
| Xác định truy vấn có được hỗ trợ và cần index nào. | Khả năng thực thi của module và kho dữ liệu. |
| Tạo implementation của một repository fragment phục vụ tìm kiếm đặc thù. | Cơ chế mở rộng chung, phần truy cập dữ liệu phụ thuộc công nghệ. |
| Kích hoạt metadata người tạo và thời điểm cập nhật. | Hạ tầng auditing chung cùng cơ chế tích hợp của module được chọn. |
| Quyết định độ nhất quán khi vừa cập nhật vừa đọc dữ liệu. | Thiết kế giao dịch và đặc tính của hệ thống lưu trữ. |

Một phương án hợp lý là bắt đầu từ hợp đồng nghiệp vụ, dùng các abstraction chung để biểu diễn yêu cầu, rồi kiểm tra khả năng của module đích trước khi chốt cách triển khai. Khi nhìn một API Spring Data, hãy luôn xác định cả hợp đồng dùng chung lẫn thành phần chịu trách nhiệm thực thi trên kho dữ liệu.