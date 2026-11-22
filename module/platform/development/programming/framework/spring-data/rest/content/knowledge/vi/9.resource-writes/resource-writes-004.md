# Khả năng tạo tài nguyên bằng PUT và cấu hình disablePutForCreation

Spring Data REST có thể cho phép client tạo tài nguyên bằng cách gửi PUT tới URI của item resource. Cách này khác với POST tới collection resource: với POST, server thường chọn ID cho tài nguyên mới; với PUT, client chỉ rõ URI đích và tài nguyên được tạo tại URI đó nếu cấu hình cùng repository cho phép.

Thuộc tính disablePutForCreation trong RepositoryRestConfiguration điều khiển hành vi này. Khi bật, PUT vẫn có thể cập nhật tài nguyên đã tồn tại, nhưng không được dùng để tạo tài nguyên mới tại một item URI chưa tồn tại. Đây là lựa chọn hữu ích khi API muốn dành POST cho việc tạo mới và giữ PUT cho việc thay thế tài nguyên hiện có.

## 1. Phân biệt POST, PUT và PATCH

Ba phương thức HTTP thường gặp khi ghi tài nguyên có mục đích khác nhau:

| Phương thức | URI điển hình | Mục đích |
|---|---|---|
| POST | /api/products | Gửi yêu cầu tạo tài nguyên mới trong collection; server thường cấp ID và trả về liên kết tới item mới. |
| PUT | /api/products/42 | Đặt biểu diễn của tài nguyên tại URI cụ thể; có thể cập nhật item đã tồn tại và, nếu được cho phép, tạo item mới tại URI đó. |
| PATCH | /api/products/42 | Cập nhật một phần biểu diễn của item đã tồn tại, giữ nguyên các thuộc tính không được gửi theo quy tắc xử lý của API. |

Ví dụ, repository được công bố tại /api/products:

~~~java
@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Client có thể dùng POST để yêu cầu server tạo một sản phẩm:

~~~http
POST /api/products
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "price": 120
}
~~~

Server thường tạo ID mới, lưu sản phẩm và trả về phản hồi thành công có Location trỏ tới item resource mới, chẳng hạn /api/products/42.

Với PUT, client chỉ rõ item URI:

~~~http
PUT /api/products/42
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "price": 120
}
~~~

Nếu sản phẩm 42 đã tồn tại, PUT cập nhật biểu diễn của tài nguyên đó. Nếu sản phẩm 42 chưa tồn tại, Spring Data REST mặc định có thể tạo tài nguyên tại URI này khi repository và kiểu ID hỗ trợ việc tạo theo ID được chỉ định.

PATCH cũng nhắm tới item URI, nhưng phù hợp khi client chỉ muốn thay đổi một phần dữ liệu. Ví dụ, cập nhật giá mà không gửi lại tên sản phẩm:

~~~http
PATCH /api/products/42
Content-Type: application/merge-patch+json

{
  "price": 135
}
~~~

Cú pháp và media type PATCH được hỗ trợ phụ thuộc cấu hình và phiên bản ứng dụng. Dù dùng định dạng nào, ý định của PATCH là cập nhật một phần; PUT biểu diễn việc thay thế tài nguyên tại URI đích.

## 2. PUT có thể tạo tài nguyên khi nào?

Khi nhận PUT tới một item URI chưa tồn tại, Spring Data REST có thể xem yêu cầu đó là tạo tài nguyên mới tại URI được chỉ định. Khả năng này thường được gọi là PUT for creation.

Ví dụ client gửi:

~~~http
PUT /api/products/9001
Content-Type: application/json

{
  "name": "USB-C Hub",
  "price": 45
}
~~~

Nếu PUT for creation đang được cho phép và repository có thể lưu entity với định danh 9001, server có thể tạo sản phẩm mới tại /api/products/9001.

Cách này hữu ích khi client đã biết trước định danh của tài nguyên, ví dụ đồng bộ dữ liệu từ hệ thống khác hoặc tạo tài nguyên với ID do nghiệp vụ cấp. URI đích được xác định trước nên client có thể gửi lại cùng yêu cầu PUT tới cùng địa chỉ mà không tạo thêm một item mới ở URI khác.

Tuy nhiên, PUT for creation cần được cân nhắc. Nó cho phép client chọn URI/ID của tài nguyên mới. Nếu hệ thống muốn server quản lý việc cấp ID và chỉ chấp nhận tạo mới qua collection endpoint, hãy tắt hành vi này bằng disablePutForCreation.

## 3. Tắt PUT for creation bằng disablePutForCreation

Spring Data REST cung cấp phương thức setDisablePutForCreation trên RepositoryRestConfiguration. Đặt giá trị true để ngăn PUT tạo tài nguyên tại item URI chưa tồn tại.

Có thể cấu hình bằng RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDisablePutForCreation(true);
    }
}
~~~

Sau khi cấu hình, hành vi được hiểu như sau:

- PUT tới item URI đã tồn tại: vẫn được dùng để cập nhật tài nguyên theo quy tắc PUT.
- PUT tới item URI chưa tồn tại: không tạo item mới; Spring Data REST từ chối yêu cầu tạo tại URI đó, thường bằng phản hồi 404 Not Found.
- POST tới collection resource: vẫn là cách tạo tài nguyên mới thông thường.
- PATCH tới item URI: vẫn dành cho cập nhật một phần tài nguyên đã tồn tại.

Cấu hình này điều chỉnh hành vi công bố repository REST. Nó không vô hiệu hóa phương thức save của repository trong tầng Java và cũng không cấm service nội bộ tạo entity mới.

## 4. Ví dụ kiểm tra trước và sau khi bật cấu hình

Giả sử API có collection /api/products và ID là Long.

**Trước khi bật disablePutForCreation**

Khi sản phẩm 9001 chưa tồn tại, gửi:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/9001 \
  -H "Content-Type: application/json" \
  -d '{"name":"USB-C Hub","price":45}'
~~~

Nếu repository hỗ trợ tạo theo ID và cấu hình mặc định cho phép PUT for creation, yêu cầu có thể tạo sản phẩm 9001. Phản hồi thành công sẽ cho biết tài nguyên đã được tạo; kiểm tra Location hoặc gọi GET tới URI item để xác nhận.

**Sau khi bật disablePutForCreation(true)**

Gửi lại PUT tới một item URI chưa tồn tại:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/9002 \
  -H "Content-Type: application/json" \
  -d '{"name":"USB-C Hub","price":45}'
~~~

Yêu cầu không được dùng để tạo sản phẩm 9002. Spring Data REST thường trả về 404 Not Found vì item resource đích chưa tồn tại.

Tuy nhiên, PUT tới item đã tồn tại vẫn hoạt động:

~~~bash
curl -i -X PUT http://localhost:8080/api/products/42 \
  -H "Content-Type: application/json" \
  -d '{"name":"Mechanical Keyboard","price":135}'
~~~

Sản phẩm 42 được cập nhật theo biểu diễn được gửi. Để kiểm tra rõ, hãy gọi GET /api/products/42 sau PUT và xác nhận dữ liệu đã thay đổi.

Cuối cùng, POST tới collection vẫn có thể tạo item mới:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"USB-C Hub","price":45}'
~~~

Server cấp định danh theo cơ chế của repository và trả về liên kết item mới. Đây là luồng tạo mới nên dùng khi client không cần tự quyết định ID.

## 5. Vì sao cần phân biệt PUT cập nhật và PUT tạo mới?

Hai yêu cầu đều dùng PUT nhưng trạng thái ban đầu của URI khác nhau:

| Trạng thái item URI | disablePutForCreation=false | disablePutForCreation=true |
|---|---|---|
| Item đã tồn tại | PUT cập nhật item. | PUT cập nhật item. |
| Item chưa tồn tại | Có thể tạo item tại URI nếu repository hỗ trợ. | Không tạo item; yêu cầu bị từ chối. |

Khi bật disablePutForCreation, hợp đồng API dễ dự đoán hơn: client phải POST vào collection để tạo mới, còn PUT chỉ dùng cho item đã tồn tại. Điều này cũng giúp tránh việc một client vô tình tạo tài nguyên bằng cách gửi sai ID hoặc gửi PUT tới một URI chưa được đăng ký.

Nếu nghiệp vụ thực sự cần client tạo tài nguyên với ID do client cung cấp, hãy cân nhắc giữ PUT for creation và kiểm soát quyền truy cập, quy tắc ID, tính duy nhất cũng như xác thực dữ liệu. Không nên dựa vào việc ID khó đoán để bảo vệ endpoint.

## 6. PUT là thay thế tài nguyên; PATCH là cập nhật một phần

PUT theo ngữ nghĩa HTTP dùng để đặt trạng thái biểu diễn của tài nguyên tại URI đích. Vì vậy, client nên gửi biểu diễn đầy đủ theo hợp đồng của endpoint. Nếu bỏ qua thuộc tính, kết quả của thuộc tính đó phụ thuộc cách Spring Data REST, Jackson và mô hình entity xử lý giá trị bị thiếu; không nên giả định mọi thuộc tính đều tự động được giữ nguyên.

Ví dụ entity:

~~~java
public class Product {
    private String name;
    private BigDecimal price;
    private String description;
}
~~~

Nếu client chỉ muốn thay đổi price, gửi một PUT chỉ có price có thể khiến name hoặc description bị đặt về giá trị mặc định/null tùy quá trình binding. Với cập nhật một phần, PATCH diễn đạt ý định rõ ràng hơn:

~~~http
PATCH /api/products/42
Content-Type: application/merge-patch+json

{
  "price": 135
}
~~~

Khi cần cập nhật toàn bộ biểu diễn, dùng PUT. Khi chỉ thay đổi một số thuộc tính, dùng PATCH với media type và semantics mà API hỗ trợ. Cấu hình disablePutForCreation chỉ quyết định PUT có được tạo tài nguyên mới hay không; nó không biến PUT thành PATCH.

## 7. Quan hệ giữa cấu hình REST và repository Java

Repository vẫn cung cấp các phương thức persistence như save, findById và delete. disablePutForCreation chỉ ảnh hưởng tới cách Spring Data REST xử lý yêu cầu HTTP tới tài nguyên được công bố.

Ví dụ service nội bộ vẫn có thể tạo sản phẩm:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(Product product) {
        return repository.save(product);
    }
}
~~~

Dù disablePutForCreation được bật, service vẫn có thể gọi save để lưu entity mới. Nếu muốn hạn chế ai được tạo dữ liệu, cần thiết kế phân quyền cho controller/service và cấu hình Spring Security phù hợp. Tắt PUT for creation không thay thế xác thực hoặc phân quyền.

Ngoài ra, cấu hình này không ngăn POST tạo tài nguyên. Nếu API cần hạn chế tạo mới nói chung, hãy kiểm soát POST bằng chính sách bảo mật hoặc ẩn phương thức công bố theo thiết kế endpoint.

## 8. Khi nào nên bật disablePutForCreation?

Nên cân nhắc bật khi:

- Server cần quản lý việc cấp ID cho tài nguyên mới.
- Client chỉ được phép tạo qua POST vào collection resource.
- API muốn giữ quy ước rõ ràng: POST tạo mới, PUT cập nhật item đã tồn tại.
- Không muốn một PUT nhầm ID tạo ra tài nguyên ngoài dự kiến.
- Các client không có nhu cầu tạo tài nguyên tại URI do mình chỉ định.

Có thể giữ PUT for creation khi:

- Client có định danh ổn định và được phép chọn URI của tài nguyên mới.
- Hệ thống đồng bộ cần ghi tài nguyên vào một ID đã biết.
- API có quy tắc kiểm soát ID, xác thực và phân quyền rõ ràng.
- Các client hiểu hợp đồng PUT có thể vừa tạo vừa thay thế tài nguyên.

Quyết định nên dựa trên cách hệ thống quản lý định danh và nhu cầu của client. Đừng bật hoặc tắt chỉ vì muốn đồng nhất tên phương thức HTTP; hãy xét cách tài nguyên được tạo và ai có quyền chọn URI.

## 9. Danh sách kiểm tra khi triển khai

1. Xác định client có cần tự chỉ định ID cho tài nguyên mới hay không.
2. Nếu chỉ tạo mới qua collection, cấu hình RepositoryRestConfigurer và gọi setDisablePutForCreation(true).
3. Kiểm tra PUT tới một item URI đã tồn tại vẫn cập nhật được.
4. Kiểm tra PUT tới một item URI chưa tồn tại không tạo tài nguyên và nhận phản hồi phù hợp.
5. Kiểm tra POST tới collection vẫn tạo tài nguyên mới theo chính sách của ứng dụng.
6. Kiểm tra PATCH cập nhật một phần nếu endpoint hỗ trợ.
7. Kiểm tra service nội bộ vẫn hoạt động theo yêu cầu nghiệp vụ; cấu hình REST không thay đổi hợp đồng persistence của repository.
8. Cập nhật tài liệu API để client biết cách tạo mới, cập nhật toàn bộ và cập nhật một phần.

disablePutForCreation là một cấu hình nhỏ nhưng thay đổi hợp đồng tạo tài nguyên của Spring Data REST. Khi bật, PUT chỉ cập nhật item đã có; POST vẫn là luồng tạo mới qua collection. Hãy kiểm tra cả trường hợp URI tồn tại và chưa tồn tại để xác nhận API phản hồi đúng với chính sách định danh của ứng dụng.
