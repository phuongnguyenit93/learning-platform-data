# Nạp JSON qua Jackson hoặc XML qua Spring OXM

Một ứng dụng học tập, môi trường demo hoặc bộ kiểm thử có thể cần một tập sản phẩm ban đầu. Spring Data Commons cung cấp cơ chế repository populator để đọc object từ resource rồi lưu chúng qua repository tương ứng. JSON có thể được đọc bằng tích hợp Jackson; XML có thể được chuyển thành object qua abstraction `Unmarshaller` của Spring OXM.

Trong chương **Khởi tạo dữ liệu** của **Spring Data Commons**, bài học này tập trung vào đường đi từ tài liệu đến domain object và thao tác lưu. Cơ chế dùng repository thay cho việc mã hóa trực tiếp tên bảng/collection trong file seed, nhưng mapping, khả năng CRUD, transaction, callbacks và auditing vẫn phụ thuộc module lưu trữ.

## 1. Repository populator thực hiện việc gì?

Đường xử lý khái niệm:

```text
Resource JSON hoặc XML
    → ResourceReader phù hợp
    → domain object hoặc collection object
    → xác định repository cho domain type
    → gọi thao tác lưu qua repository invoker
    → module thực hiện persistence
```

Những thành phần cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `Resource` | Xác định nguồn tài liệu, ví dụ resource trên classpath |
| Jackson reader | Đọc JSON và tạo object theo thông tin kiểu cần thiết |
| OXM `Unmarshaller` | Chuyển XML thành object theo mapping XML |
| Repository populator | Điều phối việc đọc và lưu qua repository |
| Repository của module | Cung cấp thao tác persistence cho domain type |
| Schema/index và mapping | Điều kiện nền để lưu và đọc dữ liệu đúng |

Đọc được một JSON/XML chưa chứng minh object đã được lưu. Ngược lại, một lần lưu thành công chưa chứng minh toàn bộ tập seed đã hoàn tất nếu quá trình gồm nhiều object hoặc resource.

Populator không tự định nghĩa schema, sinh mọi index, sắp xếp phụ thuộc nghiệp vụ hoặc tạo chính sách cập nhật dữ liệu cũ.

## 2. Điều kiện để nạp dữ liệu qua repository

Các ví dụ giả định:

1. Domain type có mapping persistence hợp lệ cho module đang dùng.
2. Repository tương ứng đã được tạo thành bean trong application context.
3. Hợp đồng repository có thao tác lưu mà cơ chế invoker sử dụng được.
4. Kho dữ liệu, schema/index cần thiết và kết nối đã sẵn sàng.
5. Bộ thư viện JSON hoặc XML tương thích với cấu hình Spring Data của ứng dụng.

Một hợp đồng repository minh họa:

```java
package example.catalog;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, String> {
}
```

Interface cung cấp CRUD và metadata domain/ID. Nó vẫn cần được module Spring Data phù hợp phát hiện và triển khai.

Không suy ra một DAO tùy ý hoặc một interface chỉ có vài phương thức đọc sẽ được populator tự chọn để lưu object. Trong ứng dụng nhiều module, cần xác định đúng repository của domain và cách module nhận diện mapping.

Các ví dụ minh họa đường repository đồng bộ. Không coi reactive hoặc coroutine repository là một thay thế tự động cho mọi factory/invoker đồng bộ được trình bày.

## 3. Mô hình Product dùng cho ví dụ

Giả sử domain `example.catalog.Product` có ID kiểu chuỗi và tiêu đề:

```java
package example.catalog;

import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "product")
@XmlAccessorType(XmlAccessType.FIELD)
public class Product {

    private String id;
    private String title;

    public Product() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

Đoạn mã trình bày phần cấu trúc Java và mapping XML cần cho bài học. Mapping persistence nhận diện ID, aggregate/entity, tên bảng/collection và các yêu cầu khác phải được cấu hình theo module của ứng dụng; annotation JAXB không thay annotation persistence.

Ví dụ XML dùng namespace Jakarta XML Binding cùng bộ Spring OXM tương thích. Một bộ phiên bản cũ dùng namespace khác cần cấu hình tương ứng; không trộn tùy ý `javax` và `jakarta`.

Nếu chỉ nạp JSON, không bắt buộc thêm mapping JAXB vào domain. Có thể chọn riêng một phương án reader mà không kéo theo mọi dependency của phương án còn lại.

## 4. Nạp JSON qua Jackson repository populator

### 4.1. Resource JSON có thông tin domain type

Một fixture minh họa, chẳng hạn resource `seed/products.json`:

```json
[
  {
    "_class": "example.catalog.Product",
    "id": "SEED-PRODUCT-001",
    "title": "Spring Data cơ bản"
  },
  {
    "_class": "example.catalog.Product",
    "id": "SEED-PRODUCT-002",
    "title": "Repository và phân trang"
  }
]
```

Trong quy ước JSON repository reader tương ứng, `_class` cung cấp tên lớp domain cần tạo. Nó không phải tên repository bean và không phải tên bảng/collection.

Quá trình khái niệm:

```text
_class = example.catalog.Product
    → tạo Product từ JSON
    → tìm repository cho Product
    → lưu qua ProductRepository
```

Một tài liệu có thể chứa nhiều object và có thể gồm nhiều domain type nếu reader, metadata và repository tương ứng hỗ trợ. Mỗi loại phải được tạo đúng và có đường persistence hợp lệ.

Tên lớp trong fixture tạo liên kết với package/class của ứng dụng. Đổi package hoặc đổi tên domain có thể làm fixture không còn đọc được dù dữ liệu nhìn vẫn giống nhau.

`_class` là quy ước của đường reader này, không phải yêu cầu chung của mọi JSON trong ứng dụng. Một request DTO thông thường không tự phải có field đó.

### 4.2. Cấu hình Java với API Jackson 2 tương ứng

Ở bộ phiên bản cung cấp API tích hợp Jackson 2, có thể dùng factory bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init.Jackson2RepositoryPopulatorFactoryBean;

@Configuration
@Profile("local-seed")
class JsonSeedConfiguration {

    @Bean
    Jackson2RepositoryPopulatorFactoryBean jsonRepositoryPopulator() {
        Jackson2RepositoryPopulatorFactoryBean factory =
                new Jackson2RepositoryPopulatorFactoryBean();

        factory.setResources(new Resource[] {
                new ClassPathResource("seed/products.json")
        });

        return factory;
    }
}
```

Đây là cấu hình minh họa cho API có tên `Jackson2RepositoryPopulatorFactoryBean`, không phải cam kết mọi dòng Spring Data/Jackson đều có cùng tên lớp. Nếu dự án dùng bộ tích hợp Jackson khác, cần dùng factory/reader được bộ phiên bản đó hỗ trợ, thay vì suy đoán một import mới.

`ClassPathResource` đọc resource được đóng gói trong classpath; không yêu cầu tài liệu phải là một file hệ thống có thể lấy bằng `getFile()`. Điều này phù hợp cả trường hợp ứng dụng được đóng gói.

Profile `local-seed` là điều kiện đăng ký cấu hình trong ví dụ. Nó không tự bảo đảm datasource là dữ liệu thử nghiệm; cấu hình môi trường vẫn phải trỏ đến kho dữ liệu mong muốn.

## 5. Jackson cần ánh xạ được chính domain object

Metadata `_class` chỉ xác định kiểu cần tạo. Các điều kiện deserialize vẫn phải được đáp ứng:

| Yêu cầu | Ví dụ vấn đề |
|---|---|
| Cách tạo object | Constructor, creator hoặc cơ chế hỗ trợ kiểu immutable |
| Ánh xạ thuộc tính | Tên JSON khác tên Java mà không có cấu hình phù hợp |
| Kiểu dữ liệu | Chuỗi không chuyển được sang số, enum hoặc ID mong muốn |
| Module bổ sung | Date/time, Kotlin hoặc kiểu giá trị tùy biến cần cấu hình tương ứng |
| Chính sách thuộc tính phụ | Reader có metadata riêng và ObjectMapper có cấu hình xử lý phù hợp |

Không mặc định ObjectMapper mà populator dùng luôn là cùng instance với ObjectMapper của HTTP controller. Nếu ứng dụng tùy biến mapper, cần xác định cách factory/reader của phiên bản đang dùng nhận cấu hình ấy.

Cũng không bật cấu hình đa hình rộng cho toàn bộ hệ thống chỉ để một fixture có `_class` đọc được. Fixture và reader là một hợp đồng riêng cần được giới hạn ở nguồn dữ liệu khởi tạo mà ứng dụng quản lý.

Nếu domain immutable, Java record hoặc Kotlin data class, phải bảo đảm đường Jackson hiện tại hiểu đúng constructor và tên thuộc tính. Khả năng tạo object trong persistence không tự đồng nghĩa JSON reader cũng tạo object theo cùng cách.

## 6. Nạp XML qua Spring OXM

Spring OXM cung cấp abstraction `Unmarshaller`. Repository populator không buộc ứng dụng phải tự viết parser XML trong từng lần nạp.

### 6.1. Resource XML cho một Product

Ví dụ `seed/product-spring.xml`:

```xml
<product>
    <id>SEED-PRODUCT-001</id>
    <title>Spring Data cơ bản</title>
</product>
```

Với JAXB mapping ở phần 3, tài liệu có thể được chuyển thành một `Product`. Kiểu Java đến từ mapping XML và unmarshaller, không phải từ `_class` như ví dụ JSON.

### 6.2. Cấu hình Jaxb2Marshaller và populator

```java
import example.catalog.Product;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.data.repository.init.UnmarshallerRepositoryPopulatorFactoryBean;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
@Profile("local-seed-xml")
class XmlSeedConfiguration {

    @Bean
    Jaxb2Marshaller seedUnmarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setClassesToBeBound(Product.class);
        return marshaller;
    }

    @Bean
    UnmarshallerRepositoryPopulatorFactoryBean xmlRepositoryPopulator(
            Jaxb2Marshaller seedUnmarshaller) {

        UnmarshallerRepositoryPopulatorFactoryBean factory =
                new UnmarshallerRepositoryPopulatorFactoryBean();

        factory.setUnmarshaller(seedUnmarshaller);
        factory.setResources(new Resource[] {
                new ClassPathResource("seed/product-spring.xml")
        });

        return factory;
    }
}
```

`Jaxb2Marshaller` có thể thực hiện vai trò `Unmarshaller` của OXM. Cần có dependency Spring OXM cùng API/runtime JAXB tương thích; không giả định mọi JDK đều đã chứa sẵn toàn bộ runtime XML Binding.

Cấu hình này là phương án XML thay thế cho phương án JSON. Nếu đồng thời kích hoạt hai cấu hình cùng nạp cùng ID, ứng dụng phải có chính sách cho hai lần lưu; không bật cả hai chỉ để so sánh định dạng mà bỏ qua dữ liệu đích.

Nếu chỉ cần một định dạng, chọn một cấu hình giúp đường khởi tạo dễ theo dõi hơn.

## 7. Một XML chứa nhiều phần tử không tự là nhiều domain object

Tài liệu sau có một root bao ngoài:

```xml
<products>
    <product>
        <id>SEED-PRODUCT-001</id>
        <title>Spring Data cơ bản</title>
    </product>
    <product>
        <id>SEED-PRODUCT-002</id>
        <title>Repository và phân trang</title>
    </product>
</products>
```

Cần biết chính xác unmarshaller và resource reader trả về object gì. Nếu kết quả là một wrapper `Products`, không được mặc định populator sẽ tự hiểu mọi thuộc tính `products` bên trong như một collection cần lưu qua `ProductRepository`.

Việc resource reader xử lý collection cần đi cùng kiểu object thực tế mà nó nhận. Một wrapper nghiệp vụ không tự trở thành domain `Product` chỉ vì có các phần tử `<product>` ở bên trong.

Các lựa chọn có thể gồm:

- Mỗi XML resource biểu diễn một domain object như ví dụ phần 6.
- Cấu hình unmarshaller/reader để trả về cấu trúc collection mà đường populator hỗ trợ.
- Đọc wrapper trong một initializer riêng rồi chuyển từng mục sang service hoặc repository theo chính sách cần thiết.

Nếu dùng nhiều resource, có thể khai báo thêm `ClassPathResource` trong mảng được truyền vào `setResources`. Cần tổ chức thứ tự dữ liệu có phụ thuộc rõ ràng thay vì kỳ vọng XML wrapper tự giải quyết mọi quan hệ.

## 8. Lúc nào quá trình nạp chạy?

Các factory repository populator tương ứng tích hợp với vòng đời application context; quá trình populate được kích hoạt theo cơ chế lifecycle của chúng, gắn với việc context được khởi tạo/refresh.

Điều cần hiểu là cấu hình bean không chỉ tạo một đối tượng reader để ứng dụng cất đó. Khi được đăng ký đúng, đường populator sẽ thực hiện công việc đọc và lưu theo lifecycle của hạ tầng.

Cần bảo đảm repository và điều kiện persistence sẵn sàng tại thời điểm đó. Nếu ứng dụng còn có migration, schema initializer hoặc một cơ chế khởi tạo khác, phải thiết kế thứ tự phù hợp.

Không suy ra rằng việc inject được repository vào một bean khác chứng minh mọi resource seed đã được nạp xong. Thứ tự tạo bean, callback lifecycle và các công cụ khởi tạo không phải cùng một sự kiện.

Cũng không xem mỗi lần refresh hoặc restart là một migration chỉ được chạy đúng một lần. Nếu cơ chế nạp được kích hoạt lại, khả năng chạy lặp phải được giải quyết ở chính sách dữ liệu.

Một log báo reader đã mở tài liệu không phải bằng chứng mọi object đã được commit thành công.

## 9. save không tự bảo đảm idempotent

Một fixture có ID cố định giúp nhận diện dữ liệu, nhưng không đủ để bảo đảm chạy nhiều lần luôn không đổi kết quả.

Khi gọi `save`, module có thể quyết định insert/update/merge theo metadata, trạng thái newness, version, `Persistable` hoặc cách triển khai cụ thể. Cùng một ID có thể dẫn đến cập nhật, xung đột, lỗi ràng buộc hoặc một hành vi khác tùy cấu hình.

Các tình huống cần phân biệt:

| Chiến lược dữ liệu | Hệ quả cần kiểm soát |
|---|---|
| ID được sinh mới mỗi lần | Có thể tạo thêm bản ghi khi nạp lại |
| ID cố định | Giúp định danh nhưng vẫn cần chính sách lưu/cập nhật |
| Seed chỉ khi chưa có | Cần xử lý cả khả năng chạy đồng thời |
| Seed cập nhật bản ghi đã có | Có thể ghi đè thay đổi của người dùng nếu không có quy tắc |
| Seed có version | Phải hiểu optimistic locking và trạng thái mới của entity |

Không gọi `deleteAll()` trước khi seed chỉ để tránh trùng trong một ứng dụng có dữ liệu cần giữ. Việc dọn toàn bộ dữ liệu là một quyết định khác với việc nạp một fixture.

Nếu cần hành vi “tạo nếu thiếu, giữ nguyên nếu đã được sửa”, một initializer/service có chính sách tường minh thường phù hợp hơn việc dựa hoàn toàn vào save của populator.

Kiểm tra `existsById` rồi lưu cũng không tự loại bỏ race khi nhiều instance cùng khởi động. Cần dựa vào ràng buộc dữ liệu, cơ chế điều phối hoặc chiến lược khởi tạo phù hợp với môi trường thực tế.

## 10. Transaction và lỗi giữa chừng

Giả sử resource A đã được lưu, sau đó resource B lỗi parse hoặc object tiếp theo vi phạm ràng buộc. Không được mặc định toàn bộ dữ liệu từ A đã được rollback.

Repository populator điều phối các thao tác lưu; phạm vi transaction của từng thao tác và khả năng giao dịch phụ thuộc module/cấu hình. Một loạt lệnh `save` không tự trở thành một transaction bao trọn mọi file và mọi kho dữ liệu.

Những câu hỏi cần xác định:

| Câu hỏi | Ý nghĩa |
|---|---|
| Mỗi lần lưu có transaction riêng không? | Một phần dữ liệu có thể đã commit trước lỗi |
| Có transaction bao toàn bộ đợt không? | Cần cơ chế thực thi đúng và manager phù hợp |
| Có nhiều datasource/kho dữ liệu không? | Không tự có giao dịch phân tán |
| Tài liệu được đọc trước hay xen kẽ lưu? | Ảnh hưởng điểm có thể thất bại và trạng thái đã ghi |
| Lần khởi động sau gặp dữ liệu dang dở thì làm gì? | Cần chính sách phục hồi/chạy lặp |

Đặt `@Transactional` trên phương thức `@Bean` không tự chứng minh callback populate chạy sau đó đã nằm trong transaction ấy. Cần đặt ranh giới transaction tại đường thực thi thật sự làm công việc và đi qua cơ chế Spring phù hợp.

Với yêu cầu atomicity hoặc báo cáo từng mục phức tạp, có thể đọc fixture thành dữ liệu đầu vào, kiểm tra trước rồi gọi một service import có ranh giới transaction được thiết kế riêng.

Không bắt mọi exception rồi tiếp tục khởi động với thông báo thành công. Nếu dữ liệu seed là điều kiện để ứng dụng hoạt động đúng, lỗi cần được biểu diễn theo chính sách khởi động có chủ đích.

## 11. Quan hệ, thứ tự nạp và business logic

Populator chọn repository theo domain type; nó không tự giải toàn bộ đồ thị phụ thuộc giữa các object.

Ví dụ sản phẩm tham chiếu một danh mục đã tồn tại. Việc JSON chứa một ID danh mục không tự chứng minh converter đã tạo được quan hệ domain đúng hoặc repository sẽ tra danh mục đó theo business key.

Cần xác định:

- Dữ liệu phụ thuộc được tạo trước hay được cascade theo mapping.
- ID tham chiếu là scalar, object lồng nhau hay quan hệ persistence.
- Module có cùng ngữ nghĩa cascade/aggregate như thiết kế giả định hay không.
- Các ràng buộc bắt buộc được đáp ứng tại thời điểm lưu.

Nếu service tạo sản phẩm còn kiểm tra quy tắc giá, trạng thái, tenant hoặc sự tồn tại của danh mục, lưu trực tiếp qua repository không tự gọi lại toàn bộ logic service đó.

Callbacks, converters, entity listeners hoặc domain events của module có thể tham gia theo đường persistence thực tế, nhưng không nên đồng nhất chúng với một lời gọi đầy đủ qua use case nghiệp vụ.

Auditing cũng cần được xem xét: khởi tạo lúc startup có thể không có danh tính request. Nguồn auditor hoặc danh tính hệ thống phải được cấu hình phù hợp nếu dữ liệu yêu cầu metadata này. Timestamp trong fixture có thể tương tác với chính sách auditing; không mặc định nó luôn được giữ nguyên.

## 12. Repository population khác migration và import lớn

| Bài toán | Đặc điểm cần có |
|---|---|
| Fixture cho demo/test | Tập object tương đối nhỏ, dễ hiểu, môi trường được kiểm soát |
| Bootstrap dữ liệu tham chiếu | Cần định danh ổn định và quy tắc chạy lặp |
| Migration dữ liệu | Cần quản lý phiên bản, lịch sử và chiến lược nâng cấp |
| Import lớn | Cần batching/streaming, theo dõi tiến độ và phục hồi phù hợp |

Repository populator hữu ích cho việc nạp object ban đầu, nhưng không tự cung cấp mọi đặc tính của một migration engine hoặc pipeline import.

Một JSON array lớn có thể cần được giữ và xử lý theo cách reader của thư viện thực hiện; không suy ra cơ chế streaming hoặc batching chỉ vì nguồn là file.

Tương tự, việc nhiều object đi qua repository không bảo đảm chúng được gửi xuống backend trong một lệnh batch duy nhất. Cách tối ưu ghi phải được thiết kế theo module nếu khối lượng dữ liệu đòi hỏi.

Đối với dữ liệu cần quản lý thay đổi qua nhiều lần phát hành, cần có chiến lược version và chính sách cập nhật rõ ràng. Không dùng việc sửa một fixture rồi khởi động lại làm bằng chứng mọi môi trường đã chuyển sang cùng trạng thái.

## 13. Đối chiếu hai định dạng

| Khía cạnh | JSON qua Jackson | XML qua Spring OXM |
|---|---|---|
| Cách xác định domain type trong ví dụ | Metadata `_class` của reader | Mapping của unmarshaller |
| Cấu trúc tài liệu | Object/array JSON | XML root, phần tử và namespace |
| Điều kiện ánh xạ | Cấu hình Jackson và kiểu Java | Cấu hình OXM cùng implementation như JAXB |
| Nhiều object | Reader hỗ trợ cấu trúc collection tương ứng | Phụ thuộc object/collection mà unmarshaller-reader tạo ra |
| Lưu dữ liệu | Qua repository phù hợp | Qua repository phù hợp |
| Transaction/chạy lặp | Cần chính sách riêng | Cần chính sách riêng |

Chọn định dạng dựa trên cách dữ liệu được quản lý và nhu cầu mapping. Đổi JSON thành XML không tự sửa một repository thiếu khả năng lưu hoặc một fixture không có chính sách chạy lặp.

Nếu hai định dạng biểu diễn cùng dữ liệu, nên đối chiếu domain object và trạng thái persistence mong muốn, không chỉ so số dòng hoặc số trường trong tài liệu.

## 14. Chẩn đoán theo từng ranh giới

| Hiện tượng | Ranh giới cần xem xét |
|---|---|
| Không tìm thấy resource | Vị trí classpath, tên resource và cách đóng gói |
| JSON không tạo được domain | `_class`, tên lớp, constructor và cấu hình mapper |
| XML không unmarshal được | Root, namespace, lớp được bind và runtime OXM/JAXB |
| Không có repository cho object | Domain type thực tế và repository scanning |
| Lưu thất bại | Mapping, schema, constraint, ID/version và module |
| Restart tạo trùng hoặc ghi đè | Chính sách chạy lặp và newness của entity |
| Chỉ một phần dữ liệu có mặt | Transaction và lỗi giữa chừng |
| Metadata audit thiếu | Nguồn auditor và vòng đời startup |
| Log thành công nhưng dữ liệu không như mong muốn | Đối chiếu đúng datasource và readback theo ID/nội dung |

Khi xác minh một đợt nạp, chỉ `count()` bằng một con số mong muốn có thể chưa đủ: dữ liệu trùng, dữ liệu cũ hoặc bản ghi sai nội dung vẫn có thể làm tổng số giống nhau. Cần đối chiếu các ID ổn định và thuộc tính quan trọng theo hợp đồng seed.

Trong môi trường có nhiều kho dữ liệu, cần xác nhận readback đang đi qua đúng repository/datasource đã được populate. Việc một ứng dụng kết nối được nhiều kho không chứng minh mọi resource đã được phân phối đúng nơi.

## 15. Bài tập tự kiểm tra

### Tình huống 1: JSON có _class nhưng không có repository bean

Object `Product` được tạo thành công nhưng quá trình nạp không tìm được đường lưu.

**Phân tích:** deserialize và persistence là hai bước khác nhau. Cần repository phù hợp được module tạo và phát hiện, cùng metadata domain đúng.

### Tình huống 2: XML có root products nhưng chỉ bind Product

Nhóm phát triển kỳ vọng mọi phần tử product bên trong tự được lưu riêng.

**Phân tích:** phải xác định object mà unmarshaller-reader tạo ra. Wrapper không tự là collection domain được populator xử lý; có thể dùng resource riêng, cấu hình reader phù hợp hoặc initializer tường minh.

### Tình huống 3: ID cố định nên cho rằng chạy lại chắc chắn không đổi dữ liệu

Một bản ghi người dùng đã sửa bị cập nhật theo fixture, hoặc lần lưu sau gặp lỗi version.

**Phân tích:** ID ổn định không định nghĩa đầy đủ ngữ nghĩa save. Cần chính sách chạy lặp dựa trên module, trạng thái entity và yêu cầu giữ/cập nhật dữ liệu cũ.

### Tình huống 4: Gắn Transactional lên phương thức tạo factory

Đợt populate sau đó vẫn để lại dữ liệu một phần khi có lỗi.

**Phân tích:** transaction tại lúc tạo bean không tự bao callback lifecycle về sau. Ranh giới cần nằm trên đường thực thi thật sự và dùng đúng transaction manager.

### Tình huống 5: Seed gọi save nên cho rằng mọi kiểm tra trong service đều chạy

Một quy tắc nghiệp vụ chỉ được viết ở service không được áp dụng.

**Phân tích:** populator lưu qua repository không tự gọi use case service. Nếu seed cần đầy đủ logic nghiệp vụ, nên có đường import/service được thiết kế tương ứng.

### Tình huống 6: Cả JSON và XML seed được bật với cùng ID

Ứng dụng nạp hai nguồn biểu diễn cùng dữ liệu.

**Phân tích:** hai nguồn vẫn tạo hai lần xử lý lưu. Cần chọn một nguồn hoặc định nghĩa rõ chính sách phối hợp, thứ tự và chạy lặp; khác định dạng không làm thao tác tự trở nên duy nhất.

Nạp JSON bằng Jackson hoặc XML bằng Spring OXM giúp đưa dữ liệu khởi tạo đi qua abstraction repository chung. Để trạng thái sau khởi tạo đúng và có thể kiểm soát, hãy giữ rõ cách tạo domain object, repository được chọn, thời điểm nạp, ranh giới transaction và chính sách cho lần chạy tiếp theo.
