# Giảm dữ liệu trả về bằng projection và giới hạn kích thước trang

Một API Spring Data REST có thể trả quá nhiều dữ liệu nếu mỗi tài nguyên chứa nhiều thuộc tính và collection trả về quá nhiều phần tử trong một response. Hai cách kiểm soát quan trọng là projection và giới hạn kích thước trang.

Projection xác định những thuộc tính nào được đưa vào representation của mỗi tài nguyên. Page size xác định số tài nguyên tối đa được trả về trong một trang. Kết hợp hai cách này giúp giảm payload, thời gian serialize, băng thông và lượng dữ liệu client phải xử lý.

Hai cơ chế tác động ở hai chiều khác nhau: projection giảm số trường trong mỗi item; page size giảm số item trong một response. Chỉ dùng một cơ chế có thể vẫn để response lớn nếu chiều còn lại không được giới hạn.

## 1. Vì sao cần giảm payload của API?

Giả sử Product có các thuộc tính:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String description;
    private BigDecimal price;
    private BigDecimal internalCost;
    private String supplierNotes;
    private boolean active;

    // getters and setters
}
~~~

Một màn hình danh sách sản phẩm có thể chỉ cần id, name, price và active. Nếu API trả cả description dài, internalCost và supplierNotes cho từng sản phẩm, response sẽ chứa dữ liệu không cần thiết.

Vấn đề tăng lên khi collection có hàng nghìn sản phẩm. Nếu mỗi item đều có nhiều trường, response có thể lớn, tốn thời gian serialize và truyền qua mạng, đồng thời khiến client phải parse dữ liệu không dùng đến.

Nên thiết kế representation theo nhu cầu của từng màn hình hoặc use case. Màn hình danh sách thường cần summary gọn; màn hình chi tiết có thể cần thêm description hoặc thuộc tính khác.

## 2. Projection trong Spring Data REST là gì?

Projection là một interface mô tả tập thuộc tính được hiển thị trong representation. Spring Data REST có thể dùng projection để trình bày một entity theo cấu trúc gọn hơn mà không cần thay đổi entity hoặc tạo một endpoint riêng cho từng dạng dữ liệu.

Ví dụ projection cho danh sách sản phẩm:

~~~java
import java.math.BigDecimal;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "productSummary", types = Product.class)
public interface ProductSummary {

    Long getId();

    String getName();

    BigDecimal getPrice();

    boolean isActive();
}
~~~

ProductSummary chỉ công bố id, name, price và active. Các thuộc tính description, internalCost và supplierNotes không nằm trong projection này nên không xuất hiện trong representation được tạo bằng projection.

Đặt projection trong package của domain type hoặc package con theo quy tắc phát hiện projection của Spring Data REST. Tên trong @Projection là tên client dùng để yêu cầu projection; tên interface và tên projection không bắt buộc phải giống nhau.

Projection interface thường dùng getter có tên tương ứng với property của domain object. Ví dụ getName() ánh xạ tới property name; isActive() ánh xạ tới property boolean active.

## 3. Yêu cầu projection qua tham số projection

Sau khi projection được phát hiện, client có thể chọn nó qua query parameter projection.

Lấy collection:

~~~http
GET /api/products?projection=productSummary
~~~

Lấy một tài nguyên:

~~~http
GET /api/products/42?projection=productSummary
~~~

Response minh họa:

~~~json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 120.00,
  "active": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    }
  }
}
~~~

Client nhận representation chỉ gồm các trường mà ProductSummary khai báo, cùng các liên kết HATEOAS phù hợp với cấu hình Spring Data REST.

Nếu gửi tên projection không tồn tại hoặc projection không được framework phát hiện, request có thể không cho kết quả mong muốn. Hãy kiểm tra tên trong @Projection, kiểu domain trong types và package chứa interface.

Projection có thể được yêu cầu cho collection hoặc item. Với ứng dụng có nhiều projection, hãy đặt tên dễ hiểu theo mục đích như productSummary, productDetail hoặc productCard.

## 4. Dùng excerptProjection làm representation mặc định cho collection

Nếu muốn các phần tử được nhúng trong collection mặc định dùng một projection, có thể khai báo excerptProjection trên repository:

~~~java
@RepositoryRestResource(
    path = "products",
    excerptProjection = ProductSummary.class
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Khi client đọc collection /api/products, excerpt projection được dùng cho representation rút gọn của các item được nhúng trong collection. Nhờ vậy, client không cần thêm ?projection=productSummary ở mọi request collection để có dạng summary mặc định.

Cần phân biệt excerpt projection với projection được yêu cầu tường minh:

- excerptProjection đặt dạng representation mặc định cho các item được nhúng trong collection resource.
- Tham số projection cho phép client yêu cầu một projection đã công bố cho request cụ thể.
- Excerpt projection không tự biến mọi endpoint item hoặc mọi representation khác thành cùng một cấu trúc.

Ví dụ, collection có thể dùng ProductSummary để hiển thị danh sách; client mở /api/products/42?projection=productSummary để yêu cầu cùng dạng summary cho item. Một projection chi tiết khác có thể được công bố cho màn hình chi tiết nếu cần.

Không nên đưa mọi thuộc tính vào excerpt projection. Collection thường trả nhiều item nên mỗi trường dư thừa đều nhân lên theo số phần tử.

## 5. Projection giúp giảm dữ liệu như thế nào?

Giả sử một Product có 20 thuộc tính, nhưng danh sách chỉ cần 4 thuộc tính. Nếu mỗi thuộc tính có dữ liệu đáng kể, giảm representation từ 20 trường xuống 4 trường sẽ làm response nhỏ hơn và giảm công việc xử lý JSON ở client.

Lợi ích thường thấy:

- Giảm số byte truyền qua mạng.
- Giảm thời gian serialize và parse JSON.
- Giảm bộ nhớ client dành cho dữ liệu không cần thiết.
- Giúp hợp đồng API phù hợp hơn với từng màn hình.
- Hạn chế việc vô tình đưa trường nội bộ vào representation được chọn.

Tuy nhiên, projection trước hết kiểm soát representation được trả về. Không nên mặc định rằng mọi projection đều làm database chỉ đọc đúng các cột đã khai báo. Khả năng tối ưu truy vấn phụ thuộc loại projection, kiểu repository, query và store đang dùng.

Closed interface projection chỉ khai báo accessor cho property có sẵn có thể giúp Spring Data tối ưu một số truy vấn. Projection dùng @Value hoặc SpEL có thể truy cập nhiều thuộc tính của target và làm giảm khả năng xác định trước tập cột cần đọc. Quan hệ lồng nhau cũng có thể kích hoạt lazy loading hoặc truy vấn bổ sung.

Nếu mục tiêu là kiểm soát chính xác SQL và dữ liệu đọc từ database, hãy cân nhắc DTO/class-based projection hoặc query chỉ chọn các trường cần thiết. Đo truy vấn thực tế thay vì suy luận rằng payload gọn đồng nghĩa với database luôn đọc ít cột hơn.

## 6. Giới hạn kích thước trang trong Spring Data REST

Projection giảm số trường của từng item, còn page size giới hạn số item được trả về trong một response collection. Spring Data REST hỗ trợ cấu hình kích thước trang mặc định và kích thước trang tối đa qua RepositoryRestConfiguration.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RepositoryRestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
~~~

Trong ví dụ:

- setDefaultPageSize(20) dùng 20 phần tử khi client không gửi tham số kích thước trang.
- setMaxPageSize(100) đặt giới hạn tối đa 100 phần tử cho một trang.

Với cấu hình này, client có thể yêu cầu ít hơn 100 item mỗi trang. Nếu client gửi size lớn hơn giới hạn, Spring Data REST áp dụng giới hạn được cấu hình thay vì cho phép một request lấy một trang tùy ý lớn.

Giới hạn page size không giới hạn tổng số bản ghi của collection. Nó chỉ giới hạn số phần tử trong mỗi response; client vẫn có thể đi qua nhiều trang bằng các link điều hướng.

## 7. Dùng page, size và sort khi truy vấn

Spring Data REST cung cấp các tham số phổ biến:

- page: chỉ số trang, bắt đầu từ 0.
- size: số phần tử yêu cầu trong trang.
- sort: thuộc tính và hướng sắp xếp.

Ví dụ:

~~~http
GET /api/products?page=0&size=20&sort=name,asc
~~~

Request này lấy trang đầu tiên, yêu cầu 20 sản phẩm và sắp xếp theo name tăng dần.

Client có thể yêu cầu trang tiếp theo:

~~~http
GET /api/products?page=1&size=20&sort=name,asc
~~~

Nếu không gửi size, server dùng default page size. Nếu gửi size vượt max page size, server giới hạn theo cấu hình. Nếu sort không hợp lệ hoặc property không thể sắp xếp, request có thể bị từ chối tùy cơ chế xử lý và phiên bản Spring Data.

Có thể kết hợp projection và paging trong cùng request:

~~~http
GET /api/products?projection=productSummary&page=0&size=20&sort=name,asc
~~~

Request này đồng thời giới hạn số item trong trang và giới hạn các trường được trình bày cho mỗi item. Đây là cách phổ biến để tạo collection response nhẹ cho giao diện danh sách.

## 8. Đọc metadata và link phân trang trong HAL

Collection được phân trang có thể trả về các item nhúng, page metadata và link điều hướng. Ví dụ minh họa:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 42,
        "name": "Mechanical Keyboard",
        "price": 120.00,
        "active": true
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/api/products?page=1&size=20"
    },
    "last": {
      "href": "http://localhost:8080/api/products?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 0
  }
}
~~~

Các trường page thường cho biết:

- size: kích thước trang được áp dụng.
- totalElements: tổng số phần tử phù hợp với collection query.
- totalPages: tổng số trang.
- number: chỉ số trang hiện tại, bắt đầu từ 0.

Các link first, prev, next và last xuất hiện tùy vị trí trang. Ở trang đầu có thể không có prev; ở trang cuối không có next. Client nên theo href mà server cung cấp để giữ các tham số lọc, sắp xếp và kích thước trang nhất quán.

Metadata totalElements và totalPages hữu ích cho giao diện, nhưng việc tính tổng có thể cần truy vấn count. Với dữ liệu lớn, hãy cân nhắc chi phí của truy vấn đếm và chọn chiến lược phân trang phù hợp với yêu cầu sản phẩm.

## 9. Đặt tên tham số và cấu hình nhất quán

Spring Data REST cho phép tùy chỉnh tên tham số page, size và sort qua RepositoryRestConfiguration:

~~~java
config.setPageParamName("page");
config.setLimitParamName("limit");
config.setSortParamName("sort");
~~~

Nếu dùng limit thay cho size, client phải gửi đúng tên tham số đã cấu hình. Hãy công bố tên tham số trong tài liệu API và giữ nhất quán giữa các endpoint.

Không nên đổi tên tham số chỉ vì sở thích nếu đã có nhiều client tích hợp. Việc đổi có thể làm request cũ không còn hoạt động như mong đợi. Nếu cần thay đổi hợp đồng, hãy có kế hoạch tương thích và thông báo rõ cho client.

Đối với custom Spring MVC controller nhận Pageable trực tiếp, cần kiểm soát giới hạn trong cấu hình Spring Data Web/Pageable resolver tương ứng hoặc xác thực tham số tại endpoint. Không giả định rằng cấu hình riêng của Spring Data REST tự động bảo vệ mọi custom controller trong ứng dụng.

## 10. Projection không thay thế bảo mật dữ liệu

Projection giúp định hình dữ liệu được trả về, nhưng không phải cơ chế phân quyền. Một projection gọn không bảo đảm rằng người dùng không thể truy cập cùng entity qua endpoint khác hoặc projection khác.

Ví dụ ProductSummary không có internalCost, nhưng nếu representation mặc định hoặc một projection khác vẫn công bố internalCost, trường đó vẫn có thể bị lộ.

Để bảo vệ dữ liệu nhạy cảm:

- Không đưa trường bí mật vào projection công khai.
- Xem xét representation mặc định khi client không truyền projection.
- Dùng Spring Security để kiểm soát ai có thể truy cập tài nguyên hoặc thao tác.
- Dùng DTO/custom controller khi cần response khác nhau theo vai trò.
- Có thể dùng cấu hình serialization như @JsonIgnore cho thuộc tính không được phép xuất hiện, nhưng cần kiểm tra cả ảnh hưởng tới deserialization và các endpoint khác.
- Không dựa vào việc client không yêu cầu một trường để xem đó là biện pháp bảo mật.

Nếu quyền xem từng thuộc tính phụ thuộc người dùng, hãy thiết kế representation theo quyền ở tầng service/controller và kiểm tra quyền trước khi trả dữ liệu. Projection công khai nên chỉ chứa những trường có thể chia sẻ với mọi đối tượng được phép gọi endpoint đó.

## 11. Khi nào projection hoặc page size chưa đủ?

Projection và page size giải quyết phần lớn nhu cầu giảm payload của collection, nhưng một số tình huống cần thêm thiết kế:

- Một trường văn bản lớn vẫn có thể làm item summary nặng; hãy bỏ trường đó khỏi projection.
- Một projection truy cập quan hệ lazy có thể gây nhiều truy vấn; kiểm tra SQL và fetch strategy.
- Một page size nhỏ nhưng client phải tải hàng nghìn trang có thể tạo quá nhiều request; cân nhắc tìm kiếm, lọc hoặc cursor/keyset pagination khi phù hợp.
- Một endpoint custom trả List trực tiếp có thể không áp dụng giới hạn của Spring Data REST; cần dùng Pageable và cấu hình resolver.
- Một response có nhiều dữ liệu nhúng từ quan hệ có thể lớn dù collection chính đã phân trang; giới hạn mức độ lồng và chọn projection phù hợp.

Nếu client chỉ cần tìm một nhóm sản phẩm, hãy kết hợp filter/search với paging để database chỉ trả về tập kết quả phù hợp. Không tải toàn bộ collection về server hoặc client rồi mới cắt thành trang trong bộ nhớ.

## 12. Quy trình kiểm tra payload và giới hạn trang

Sau khi khai báo ProductSummary và cấu hình RepositoryRestConfiguration:

1. Gọi GET /api/products?projection=productSummary và xác nhận response chỉ có id, name, price và active theo projection.
2. Gọi GET /api/products/42?projection=productSummary để kiểm tra projection trên item resource.
3. Đọc GET /api/products và xác nhận excerptProjection được dùng cho các item nhúng trong collection nếu đã cấu hình.
4. Gọi GET /api/products?page=0 không có size; xác nhận server dùng default page size.
5. Gọi GET /api/products?page=0&size=10; xác nhận trang có tối đa 10 item.
6. Gửi size lớn hơn maxPageSize; xác nhận kích thước được giới hạn theo cấu hình.
7. Kết hợp projection, page, size và sort trong cùng request; xác nhận cả nội dung item lẫn số lượng item đúng mong đợi.
8. Kiểm tra page metadata và link next/last ở trang đầu, trang giữa và trang cuối.
9. Đo kích thước response trước và sau khi dùng projection để xác nhận payload giảm.
10. Kiểm tra representation mặc định và các endpoint khác để bảo đảm trường nhạy cảm không bị lộ qua một đường truy cập khác.

Projection giảm số thuộc tính trong representation của mỗi tài nguyên; giới hạn page size giảm số tài nguyên trong một response. Kết hợp projection summary, excerptProjection và max page size giúp collection API nhẹ hơn, dễ dự đoán và phù hợp với nhu cầu client. Hãy kiểm tra payload thực tế, truy vấn database và các đường truy cập khác để bảo đảm tối ưu hiệu năng không làm suy yếu bảo mật dữ liệu.
