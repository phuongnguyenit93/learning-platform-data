# Một Model phục vụ nhiều View

Trong kiến trúc Model–View–Controller (MVC), một Model có thể cung cấp trạng thái và hành vi nghiệp vụ cho nhiều View. Cùng một sản phẩm, đơn hàng hoặc hồ sơ khách hàng có thể được trình bày thành danh sách, trang chi tiết, màn hình quản trị, giao diện di động hay tài liệu in. Mỗi View phục vụ một mục đích khác nhau, nhưng chúng vẫn phản ánh cùng một nguồn dữ liệu và cùng các quy tắc nghiệp vụ.

Quan hệ này giúp ứng dụng giữ dữ liệu nhất quán, tránh lặp lại nghiệp vụ trong từng màn hình và cho phép thay đổi cách trình bày mà ít ảnh hưởng đến phần lõi. Để đạt được điều đó, cần phân biệt rõ Model nghiệp vụ, dữ liệu dành cho View và đối tượng Model mà một framework web cung cấp cho template.

## 1. Vì sao một Model cần phục vụ nhiều View?

Một ứng dụng thường có nhiều cách nhìn về cùng một đối tượng. Ví dụ, hệ thống quản lý sản phẩm có thể cần:

- Trang danh sách hiển thị tên, giá và trạng thái còn hàng để người mua so sánh nhanh.
- Trang chi tiết hiển thị mô tả, thông tin vận chuyển và các lựa chọn mua hàng.
- Trang quản trị hiển thị thêm mã nội bộ, trạng thái xuất bản và thông tin kiểm kê.
- Trang in hoặc báo cáo trình bày dữ liệu theo bố cục phù hợp với giấy hoặc tài liệu lưu trữ.

Nếu mỗi màn hình tự duy trì một bản sao dữ liệu và tự cài đặt quy tắc cập nhật, các bản sao có thể lệch nhau. Chẳng hạn, trang chi tiết đã hiển thị giá mới nhưng trang danh sách vẫn dùng giá cũ; hoặc một View cho phép đặt hàng trong khi View khác cho rằng sản phẩm đã hết hàng.

Trong MVC, các View nên cùng dựa trên một mô hình nghiệp vụ nhất quán. Khi giá sản phẩm thay đổi, quy tắc về giá được xử lý ở lớp nghiệp vụ. Các View đọc trạng thái mới và trình bày theo cách riêng của chúng. Nhờ vậy, việc có nhiều cách hiển thị không tạo ra nhiều nguồn chân lý cho cùng một nghiệp vụ.

## 2. Hiểu đúng khái niệm “một Model”

“Một Model” không có nghĩa là toàn ứng dụng chỉ có một class Java, một object dùng chung cho mọi request hoặc một singleton chứa toàn bộ dữ liệu. Trong MVC, Model là phần biểu diễn trạng thái, dữ liệu và quy tắc nghiệp vụ mà ứng dụng cần quản lý. Tùy quy mô, phần này có thể gồm nhiều thành phần:

- Entity hoặc domain object biểu diễn các khái niệm nghiệp vụ như Product, Order và Customer.
- Domain service chứa quy tắc nghiệp vụ không thuộc riêng một entity.
- Application service điều phối một use case, chẳng hạn tìm sản phẩm hoặc tạo đơn hàng.
- Repository cung cấp cách truy vấn và lưu trạng thái.

Các thành phần này phối hợp tạo thành phần Model của ứng dụng. Nhiều View có thể sử dụng cùng Model thông qua Controller và các dịch vụ ứng dụng.

Điều cần chia sẻ là định nghĩa và trạng thái nghiệp vụ có thẩm quyền. Dữ liệu đưa ra từng View có thể khác nhau. Một trang danh sách chỉ cần tên và giá; trang chi tiết cần thêm mô tả; trang quản trị có thể cần trạng thái xuất bản. Vì vậy, cùng một Model không bắt buộc mọi View phải nhận cùng một cấu trúc dữ liệu.

### Phân biệt ba khái niệm thường bị nhầm

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Model nghiệp vụ | Giữ trạng thái và quy tắc của miền nghiệp vụ | Product, Order, ProductService |
| ViewModel hoặc DTO | Đóng gói dữ liệu phù hợp với một màn hình hoặc hợp đồng phản hồi | ProductListItemView, ProductDetailView |
| Model của Spring MVC | Đối tượng chứa các thuộc tính mà Controller chuyển cho template trong một request | org.springframework.ui.Model |

Đặc biệt, org.springframework.ui.Model của Spring MVC là một vùng chứa dữ liệu phục vụ quá trình render View. Nó không phải toàn bộ Model nghiệp vụ của kiến trúc MVC. Đặt tên biến như uiModel hoặc viewModel trong Controller giúp tránh nhầm lẫn này.

## 3. Quan hệ giữa Model, Controller và nhiều View

Controller tiếp nhận request, gọi use case phù hợp, chuẩn bị dữ liệu cho cách trình bày được yêu cầu rồi chọn View. Các View đọc dữ liệu đã được chuẩn bị và hiển thị nó. Controller không nên tự chứa các quy tắc nghiệp vụ cốt lõi; View cũng không nên tự quyết định nghiệp vụ.

~~~mermaid
flowchart LR
    U[Người dùng] --> C[Controller]
    C --> A[Application Service]
    A --> M[Model nghiệp vụ]
    M <--> R[(Repository và cơ sở dữ liệu)]
    A --> C
    C --> P1[Projection cho danh sách]
    C --> P2[Projection cho chi tiết]
    C --> P3[Projection cho quản trị]
    P1 --> V1[View danh sách]
    P2 --> V2[View chi tiết]
    P3 --> V3[View quản trị]
~~~

Sơ đồ thể hiện ba điểm:

1. Nhiều View có thể cùng sử dụng một phần Model nghiệp vụ.
2. Controller hoặc lớp trình bày chuyển dữ liệu nghiệp vụ thành cấu trúc phù hợp với từng View.
3. Mỗi View chỉ chịu trách nhiệm trình bày dữ liệu mà nó nhận được.

Một Controller có thể chọn nhiều View cho các route khác nhau. Ngược lại, nhiều Controller cũng có thể sử dụng chung một application service hoặc Model. Cách tổ chức cụ thể phụ thuộc vào ranh giới use case và quy mô ứng dụng; điều quan trọng là các Controller không sao chép quy tắc nghiệp vụ.

## 4. Ví dụ: Model sản phẩm phục vụ View danh sách và View chi tiết

Giả sử ứng dụng bán hàng có Model sản phẩm với thông tin định danh, tên, mô tả, giá và khả năng cung cấp. Trang danh sách và trang chi tiết đều cần thông tin của sản phẩm, nhưng nhu cầu trình bày khác nhau.

### 4.1. Model nghiệp vụ dùng chung

Ví dụ rút gọn dưới đây dùng Java record để tập trung vào mối quan hệ giữa các lớp:

~~~java
import java.math.BigDecimal;

public record Product(
        long id,
        String name,
        String description,
        BigDecimal price,
        boolean available
) {
}
~~~

Application service cung cấp dữ liệu sản phẩm cho các use case. Việc truy vấn, kiểm tra sản phẩm có được phép hiển thị hay không và các quy tắc nghiệp vụ liên quan thuộc trách nhiệm của tầng ứng dụng hoặc miền nghiệp vụ.

~~~java
import java.util.List;

public interface ProductService {
    List<Product> findPublishedProducts();

    Product getPublishedProduct(long id);
}
~~~

Trong ứng dụng thực tế, service có thể gọi repository, kiểm tra quyền truy cập, áp dụng bộ lọc và xử lý trường hợp không tìm thấy sản phẩm. Controller không cần biết cách truy vấn cơ sở dữ liệu.

### 4.2. Tạo cấu trúc dữ liệu riêng cho từng View

View danh sách chỉ cần một số trường ngắn gọn:

~~~java
import java.math.BigDecimal;

public record ProductListItemView(
        long id,
        String name,
        BigDecimal price
) {
    public static ProductListItemView from(Product product) {
        return new ProductListItemView(
                product.id(),
                product.name(),
                product.price()
        );
    }
}
~~~

View chi tiết cần thêm mô tả và trạng thái có thể mua:

~~~java
import java.math.BigDecimal;

public record ProductDetailView(
        long id,
        String name,
        String description,
        BigDecimal price,
        boolean available
) {
    public static ProductDetailView from(Product product) {
        return new ProductDetailView(
                product.id(),
                product.name(),
                product.description(),
                product.price(),
                product.available()
        );
    }
}
~~~

Hai kiểu dữ liệu này là projection dành cho trình bày. Chúng được tạo từ cùng Product nhưng có cấu trúc khác nhau. Nhờ đó, View danh sách không phải nhận những trường nó không sử dụng; View chi tiết có thể nhận thêm thông tin cần thiết.

### 4.3. Controller chọn View và chuyển dữ liệu

Với Spring MVC, Controller có thể trả về hai template khác nhau:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    public String list(Model uiModel) {
        var products = productService.findPublishedProducts()
                .stream()
                .map(ProductListItemView::from)
                .toList();

        uiModel.addAttribute("products", products);
        return "products/list";
    }

    @GetMapping("/{id}")
    public String detail(
            @PathVariable long id,
            Model uiModel
    ) {
        Product product = productService.getPublishedProduct(id);
        uiModel.addAttribute(
                "product",
                ProductDetailView.from(product)
        );
        return "products/detail";
    }
}
~~~

Khi người dùng truy cập /products, Controller lấy danh sách Product, chuyển từng phần tử thành ProductListItemView và chọn template products/list. Khi truy cập /products/42, Controller lấy cùng loại Model nghiệp vụ, chuyển thành ProductDetailView và chọn template products/detail.

Luồng xử lý có thể tóm tắt như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as ProductController
    participant S as ProductService
    participant M as Product Model
    participant V as View
    User->>C: GET /products
    C->>S: findPublishedProducts()
    S->>M: Truy vấn sản phẩm
    M-->>S: Danh sách Product
    S-->>C: Danh sách Product
    C->>C: Chuyển thành ProductListItemView
    C->>V: Chọn products/list
    V-->>User: HTML danh sách
    User->>C: GET /products/42
    C->>S: getPublishedProduct(42)
    S->>M: Tìm Product có id = 42
    M-->>S: Product
    S-->>C: Product
    C->>C: Chuyển thành ProductDetailView
    C->>V: Chọn products/detail
    V-->>User: HTML chi tiết
~~~

Hai request có thể tạo ra hai cấu trúc trình bày khác nhau, nhưng đều dựa trên cùng Model nghiệp vụ và các quy tắc truy xuất sản phẩm.

## 5. Nguyên tắc thiết kế khi dùng một Model cho nhiều View

### 5.1. Giữ quy tắc nghiệp vụ ở Model hoặc tầng nghiệp vụ

Quy tắc như giá bán hợp lệ, điều kiện sản phẩm được xuất bản, giới hạn số lượng đặt mua hoặc trạng thái hợp lệ của đơn hàng phải được thực thi ở tầng nghiệp vụ. Nếu mỗi View tự kiểm tra các điều kiện này, các màn hình có thể đưa ra kết quả khác nhau.

View có thể ẩn hoặc hiện nút dựa trên trạng thái đã nhận để cải thiện trải nghiệm. Tuy nhiên, thao tác thực tế vẫn phải được Controller và tầng nghiệp vụ kiểm tra lại. Không được xem việc ẩn một nút trên giao diện là cơ chế bảo vệ dữ liệu.

### 5.2. Tạo hợp đồng dữ liệu phù hợp với từng View

Không phải View nào cũng cần toàn bộ thuộc tính của Model. Hãy xác định trường dữ liệu tối thiểu cần thiết cho mỗi màn hình và tạo DTO hoặc ViewModel tương ứng khi cấu trúc trình bày khác với Model nghiệp vụ.

Việc này giúp giảm phụ thuộc giữa giao diện và miền nghiệp vụ. Khi thêm một trường nội bộ vào Product, hợp đồng của trang danh sách không tự động thay đổi. Khi bố cục trang chi tiết thay đổi, Model nghiệp vụ cũng không cần chứa các thuộc tính chỉ phục vụ bố cục.

### 5.3. Để Controller điều phối, không biến Controller thành nơi chứa nghiệp vụ

Controller nên thực hiện các việc ở ranh giới HTTP: đọc path variable, query parameter hoặc form input; gọi service; xử lý kết quả ở mức giao thức; chuẩn bị thuộc tính cho View và chọn phản hồi.

Các thao tác tạo, cập nhật hoặc xóa dữ liệu cần đi qua use case hoặc service tương ứng. View chỉ gửi yêu cầu của người dùng và hiển thị kết quả. Không để mỗi View tự sửa một bản sao Model hoặc tự truy cập repository.

### 5.4. Kiểm soát dữ liệu theo quyền của người dùng

Cùng một Model có thể phục vụ khách hàng và nhân viên quản trị, nhưng hai nhóm không nhất thiết có quyền xem cùng dữ liệu. Service phải kiểm tra quyền và phạm vi dữ liệu trước khi trả kết quả. Projection cho View cần loại bỏ trường nhạy cảm hoặc trường nội bộ mà người dùng hiện tại không được phép xem.

Ví dụ, trang khách hàng có thể hiển thị tên, giá và trạng thái còn hàng; trang quản trị có thể hiển thị thêm mã kho. Không nên trả toàn bộ entity ra ngoài rồi trông chờ template tự ẩn các trường nhạy cảm.

### 5.5. Tối ưu truy vấn theo nhu cầu hiển thị

Chia sẻ Model không có nghĩa là mọi View phải tải tất cả dữ liệu. Trang danh sách nên phân trang và chỉ truy vấn các trường cần thiết. Trang chi tiết có thể tải thêm thông tin liên quan khi người dùng mở trang. Với danh sách lớn, projection ở tầng truy vấn có thể giảm lượng dữ liệu đọc và tránh lỗi truy vấn lặp như N+1.

Nếu dùng cache, cần tính đến người dùng, quyền truy cập, bộ lọc và loại dữ liệu trình bày để tránh trả nhầm dữ liệu giữa các ngữ cảnh.

## 6. Khi dữ liệu thay đổi: các View cùng phản ánh một trạng thái

Giả sử giá sản phẩm thay đổi từ 100.000 đồng thành 120.000 đồng. Luồng cập nhật nên đi qua Controller và use case cập nhật sản phẩm. Service kiểm tra quyền, xác thực dữ liệu và áp dụng quy tắc nghiệp vụ trước khi lưu.

Sau khi thay đổi được lưu thành công, request tiếp theo đến trang danh sách hoặc trang chi tiết sẽ đọc trạng thái mới từ cùng nguồn dữ liệu. Mỗi View định dạng giá theo bố cục riêng, nhưng không tự duy trì một giá trị nghiệp vụ độc lập.

Với ứng dụng có cache, tìm kiếm chỉ mục hoặc bản đọc được đồng bộ bất đồng bộ, các View có thể tạm thời quan sát trạng thái ở những thời điểm khác nhau. Khi đó, kiến trúc cần xác định rõ chính sách nhất quán, thời gian làm mới cache và cách xử lý dữ liệu cũ. Đây là vấn đề đồng bộ dữ liệu của hệ thống, không phải lý do để mỗi View sở hữu một quy tắc nghiệp vụ riêng.

## 7. Những cách làm dễ gây lỗi

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Sao chép quy tắc nghiệp vụ vào từng View | Các màn hình có thể xử lý cùng tình huống khác nhau | Đưa quy tắc về Model hoặc service nghiệp vụ |
| Để View truy cập repository trực tiếp | Giao diện phụ thuộc lưu trữ, khó kiểm soát giao dịch và quyền | Cho View nhận dữ liệu qua Controller và service |
| Trả toàn bộ entity cho mọi View | Rò rỉ trường nội bộ, hợp đồng giao diện phụ thuộc cấu trúc miền | Dùng DTO hoặc projection theo nhu cầu |
| Tạo một Model khổng lồ chứa thuộc tính riêng của mọi màn hình | Model khó hiểu, khó bảo trì và bị chi phối bởi giao diện | Giữ Model tập trung vào miền nghiệp vụ; tách dữ liệu trình bày |
| Tạo bản sao dữ liệu độc lập cho từng View | Dữ liệu dễ lệch nhau sau khi cập nhật | Dùng chung nguồn dữ liệu có thẩm quyền |
| Chỉ kiểm tra quyền bằng cách ẩn thành phần giao diện | Người dùng vẫn có thể gọi endpoint trực tiếp | Kiểm tra quyền ở Controller, service hoặc tầng bảo mật |
| Tải mọi quan hệ và trường dữ liệu cho mọi màn hình | Tốn bộ nhớ, tăng thời gian phản hồi và có thể gây N+1 | Phân trang, projection và truy vấn theo use case |

Một lưu ý khác: không nên ép mọi màn hình vào một DTO duy nhất chỉ vì chúng cùng dùng một Model. DTO quá rộng thường có nhiều trường null hoặc nhiều cờ điều khiển cách hiển thị. Khi các View có nhu cầu khác nhau rõ rệt, những projection riêng thường dễ hiểu và an toàn hơn.

## 8. Kiểm thử quan hệ giữa một Model và nhiều View

Có thể kiểm tra thiết kế này ở nhiều mức:

1. **Kiểm thử Model và nghiệp vụ:** xác nhận quy tắc như giá, trạng thái xuất bản và khả năng mua hoạt động đúng mà không phụ thuộc View.
2. **Kiểm thử application service:** xác nhận service trả đúng dữ liệu, áp dụng bộ lọc và quyền truy cập theo use case.
3. **Kiểm thử Controller:** dùng MockMvc hoặc công cụ tương đương để xác nhận route danh sách chọn đúng View, route chi tiết chọn đúng View và thuộc tính được chuyển đúng cấu trúc.
4. **Kiểm thử tích hợp:** cập nhật một sản phẩm rồi đọc qua cả trang danh sách và trang chi tiết để xác nhận hai View phản ánh cùng trạng thái nghiệp vụ.
5. **Kiểm thử bảo mật:** xác nhận người dùng không có quyền không thể lấy trường quản trị chỉ bằng cách gọi trực tiếp endpoint.

Một tình huống kiểm thử hữu ích là thay đổi giá của một sản phẩm, sau đó gọi cả endpoint danh sách và chi tiết. Kết quả mong đợi là hai phản hồi thể hiện cùng giá mới, dù một phản hồi có thể chứa ít trường hơn phản hồi còn lại.

## 9. Khi nào cần thêm Model đọc hoặc projection riêng?

Với hệ thống nhỏ, Controller có thể chuyển trực tiếp entity sang DTO. Khi hệ thống lớn hơn, một số màn hình có thể cần dữ liệu tổng hợp từ nhiều entity hoặc truy vấn được tối ưu riêng. Khi đó có thể tạo query service, read model hoặc projection chuyên biệt.

Ví dụ, màn hình tổng quan quản trị có thể cần tổng doanh thu, số đơn theo trạng thái và số sản phẩm sắp hết hàng. Đây là dữ liệu đọc tổng hợp, không nhất thiết phải tạo thành một entity nghiệp vụ mới. Một read model có thể được thiết kế riêng để phục vụ truy vấn đó, trong khi các quy tắc ghi vẫn được thực thi bởi Model và use case nghiệp vụ.

Điều cần giữ là ranh giới rõ ràng: read model phục vụ cách đọc; Model nghiệp vụ và các use case vẫn chịu trách nhiệm bảo vệ tính hợp lệ của thay đổi. Nếu dữ liệu đọc được cập nhật bất đồng bộ, cần mô tả rõ độ trễ và mức nhất quán mà View có thể quan sát.

## 10. Checklist thiết kế

Trước khi hoàn thành một tính năng có nhiều View, hãy kiểm tra:

- Các View có đang phản ánh cùng một khái niệm và nguồn dữ liệu nghiệp vụ không?
- Quy tắc nghiệp vụ có được thực thi tập trung ở Model hoặc tầng service phù hợp không?
- Mỗi View có nhận đúng những trường cần thiết qua một hợp đồng dữ liệu rõ ràng không?
- Controller có điều phối request và chọn View mà không chứa nghiệp vụ cốt lõi không?
- Quyền truy cập có được kiểm tra ở phía máy chủ trước khi trả dữ liệu hoặc thay đổi trạng thái không?
- Truy vấn có phân trang và tránh tải dữ liệu không cần thiết không?
- Kiểm thử có xác nhận nhiều View phản ánh nhất quán sau một thay đổi không?

Khi các câu trả lời đều rõ ràng, ứng dụng có thể mở rộng thêm View mà không phải nhân bản Model hoặc quy tắc nghiệp vụ. Đây là lợi ích cốt lõi của quan hệ một Model phục vụ nhiều View trong MVC: mỗi cách trình bày được tự do đáp ứng nhu cầu người dùng, trong khi trạng thái và hành vi nghiệp vụ vẫn nhất quán.
