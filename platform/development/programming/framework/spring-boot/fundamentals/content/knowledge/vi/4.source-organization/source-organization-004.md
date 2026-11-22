# Tổ chức theo chức năng hoặc theo miền nghiệp vụ

Khi bắt đầu một ứng dụng Spring Boot, nhiều người đặt tất cả controller vào thư mục `controller`, tất cả service vào `service`, tất cả repository vào `repository`. Cách này dễ làm quen vì mỗi package cho biết **loại thành phần kỹ thuật**. Tuy nhiên, khi hệ thống lớn lên, một yêu cầu như “thay đổi cách đặt hàng” có thể buộc lập trình viên mở rất nhiều package để tìm những lớp liên quan.

Một hướng tổ chức khác là nhóm mã nguồn theo **chức năng (feature)** hoặc **miền nghiệp vụ (domain)**. Thay vì hỏi “lớp này là controller hay repository?”, ta bắt đầu bằng câu hỏi “lớp này phục vụ khả năng nghiệp vụ nào?”. Với ứng dụng bán hàng, các khả năng có thể là `catalog` (danh mục), `orders` (đơn hàng), `customers` (khách hàng) hoặc `payments` (thanh toán). Mỗi nhóm chứa những thành phần cần thiết để thực hiện công việc của nó.

Tổ chức theo chức năng hoặc miền nghiệp vụ không tự động làm ứng dụng trở thành microservices hay áp đặt một kiến trúc phức tạp. Đó là cách **đặt ranh giới và sở hữu mã nguồn** để sửa đổi, hiểu, kiểm thử và phát triển ứng dụng Spring Boot dễ hơn.

## 1. Hiểu đúng các cách tổ chức mã nguồn

Trước hết, cần phân biệt ba góc nhìn thường gặp.

| Cách tổ chức | Tiêu chí gom nhóm chính | Package cấp cao minh họa | Câu hỏi trả lời |
|---|---|---|---|
| Theo tầng kỹ thuật (*package by layer*) | Loại thành phần trong kiến trúc | `controller`, `service`, `repository`, `entity` | “Lớp này làm công việc kỹ thuật nào?” |
| Theo chức năng (*package by feature*) | Khả năng mà người dùng hoặc hệ thống sử dụng | `catalog`, `orders`, `checkout` | “Lớp này phục vụ chức năng nào?” |
| Theo miền nghiệp vụ (*package by domain*) | Khái niệm, quy tắc và ranh giới sở hữu trong nghiệp vụ | `inventory`, `ordering`, `billing` | “Quy tắc này thuộc phần nghiệp vụ nào?” |

**Theo chức năng** và **theo miền nghiệp vụ** có nhiều điểm giao nhau nhưng không hoàn toàn đồng nghĩa. Một feature thường xuất phát từ năng lực hoặc luồng sử dụng, ví dụ “khách hàng đặt hàng”. Một domain hoặc subdomain được xác định qua mô hình và quy tắc nghiệp vụ, ví dụ “đặt hàng”, “quản lý tồn kho”, “tính tiền”. Một tính năng thanh toán có thể liên quan đồng thời đến các miền đặt hàng và lập hóa đơn. Ngược lại, một miền đơn hàng có thể cung cấp nhiều tính năng: tạo đơn, hủy đơn, theo dõi trạng thái.

Trong các dự án nhỏ, tên package `orders` có thể đồng thời đại diện cho feature và phần miền nghiệp vụ tương ứng. Khi dự án phát triển, cần nhìn sâu hơn vào trách nhiệm và đường phụ thuộc thay vì chỉ nhìn tên thư mục.

## 2. So sánh cấu trúc theo tầng và theo chức năng

Giả sử xây dựng hệ thống bán sách bằng Spring Boot, có API xem sách, đặt hàng và quản lý khách hàng.

### 2.1. Cấu trúc theo tầng kỹ thuật

~~~text
src/main/java/com/example/bookstore/
├── BookstoreApplication.java
├── controller/
│   ├── BookController.java
│   ├── OrderController.java
│   └── CustomerController.java
├── service/
│   ├── BookService.java
│   ├── OrderService.java
│   └── CustomerService.java
├── repository/
│   ├── BookRepository.java
│   ├── OrderRepository.java
│   └── CustomerRepository.java
├── entity/
│   ├── Book.java
│   ├── Order.java
│   └── Customer.java
└── dto/
    ├── BookResponse.java
    ├── CreateOrderRequest.java
    └── OrderResponse.java
~~~

**Ưu điểm:** dễ nhận diện các lớp cùng loại; hợp lý với bài học nhập môn hoặc ứng dụng rất nhỏ, nơi luồng xử lý ngắn, số lượng lớp ít và chưa có nhiều ranh giới nghiệp vụ.

**Hạn chế khi quy mô tăng:** mọi thay đổi của feature “đơn hàng” trải dài qua `controller`, `service`, `repository`, `entity` và `dto`. Các package trở nên rất lớn, trách nhiệm sở hữu khó nhận ra; dễ vô tình gọi repository hoặc service của feature khác vì tất cả đều ở gần nhau về mặt kỹ thuật.

Quan trọng: package theo tầng **không sai về mặt Spring Boot**. Spring vẫn hoạt động bình thường nếu các bean nằm trong phạm vi quét và được cấu hình đúng. Vấn đề là cách tổ chức này có thể trở nên khó duy trì khi yêu cầu nghiệp vụ tăng.

### 2.2. Cấu trúc theo chức năng

Cũng những lớp đó có thể được sắp xếp như sau:

~~~text
src/main/java/com/example/bookstore/
├── BookstoreApplication.java
├── catalog/
│   ├── BookController.java
│   ├── BookService.java
│   ├── BookRepository.java
│   ├── Book.java
│   └── BookResponse.java
├── orders/
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   ├── Order.java
│   ├── CreateOrderRequest.java
│   └── OrderResponse.java
└── customers/
    ├── CustomerController.java
    ├── CustomerService.java
    ├── CustomerRepository.java
    └── Customer.java
~~~

Lúc này, lập trình viên cần thay đổi cách tạo đơn hàng thường bắt đầu từ một nơi: `orders`. Trong package đó có thể tìm luồng nhận request, logic tạo đơn, dữ liệu cần lưu và các kiểu dữ liệu trả về.

Cấu trúc này đem lại ba lợi ích chính:

1. **Tăng tính liên kết nội bộ (*cohesion*).** Những thành phần cùng giải quyết một vấn đề nghiệp vụ nằm gần nhau.
2. **Làm rõ chủ sở hữu.** Nhóm phụ trách đơn hàng có thể tập trung làm việc trong `orders` mà ít phải thay đổi phần danh mục.
3. **Giúp thay đổi có phạm vi dễ nhận biết.** Khi xem một yêu cầu hoặc pull request, các file thuộc cùng feature thường được thay đổi cùng nhau.

Điều này chưa bảo đảm ranh giới thật sự. Nếu `OrderService` trực tiếp thao tác `CustomerRepository` và `BookRepository` ở mọi nơi, dự án vẫn có liên kết chằng chịt dù đã chia thư mục theo feature. **Vị trí đặt file chỉ là bước đầu; cách các lớp phụ thuộc vào nhau mới quyết định tính độc lập.**

## 3. Từ feature đến miền nghiệp vụ: xác định ranh giới sở hữu

Trong thiết kế hướng miền nghiệp vụ (Domain-Driven Design, hay DDD), lập trình viên cố hiểu ngôn ngữ và quy tắc mà người làm nghiệp vụ sử dụng. Ví dụ hệ thống thương mại có thể có:

- **Catalog:** mô tả sách, tác giả, giá đang niêm yết, thông tin tìm kiếm.
- **Inventory:** số lượng thực tế, hàng được giữ chỗ, quy tắc xuất nhập kho.
- **Ordering:** giỏ hàng và đơn hàng đã đặt, trạng thái xử lý đơn, điều kiện hủy đơn.
- **Billing:** hóa đơn, khoản cần thu, đối soát.
- **Shipping:** đóng gói, giao nhận, trạng thái vận chuyển.

“Danh mục” và “kho” có thể cùng nói về một sản phẩm nhưng **không nhất thiết sở hữu cùng dữ liệu hoặc cùng quy tắc**. Catalog quản lý nội dung mô tả; Inventory quản lý số lượng có thể bán. Việc đặt mọi thứ vào package `product` chỉ vì đều liên quan tới sản phẩm dễ tạo một package quá lớn.

Một ranh giới nghiệp vụ tốt thường trả lời được:

- Phần này chịu trách nhiệm cho quy tắc nào?
- Dữ liệu nào được phép thay đổi trực tiếp ở đây?
- Phần khác cần biết kết quả gì để phối hợp, nhưng không cần biết cách xử lý bên trong?
- Khi một quy tắc thay đổi, những phần nào phải sửa?

Ở hệ thống nhỏ, có thể không cần DDD đầy đủ hay phân tách nhiều subdomain ngay. Nhưng việc dùng **từ ngữ nghiệp vụ** để đặt tên package là nền tảng rất hữu ích.

### Bounded context và package khác nhau thế nào?

Một **bounded context** là phạm vi mà một mô hình và các thuật ngữ nghiệp vụ có ý nghĩa nhất quán. Package Java là cơ chế tổ chức lớp và kiểm soát khả năng truy cập trong mã nguồn. Chúng liên quan nhưng không tương đương: một bounded context có thể trải qua nhiều package; một package không tự động cưỡng chế được các quy tắc của bounded context.

Tương tự, một **module nghiệp vụ** có thể gồm một số package bên trong và một API công khai. Nó vẫn có thể nằm trong **một ứng dụng Spring Boot và một JAR**. Không cần chia thành microservice chỉ để thực hành tổ chức theo miền nghiệp vụ.

## 4. Một cấu trúc thực tế cho Spring Boot

Khi feature có nhiều lớp, có thể kết hợp hai cách tổ chức: **bên ngoài theo nghiệp vụ, bên trong theo trách nhiệm kỹ thuật**.

~~~text
src/
├── main/
│   ├── java/com/example/bookstore/
│   │   ├── BookstoreApplication.java
│   │   ├── catalog/
│   │   │   ├── api/
│   │   │   │   ├── BookController.java
│   │   │   │   └── BookResponse.java
│   │   │   ├── application/
│   │   │   │   └── SearchBooksService.java
│   │   │   ├── domain/
│   │   │   │   └── Book.java
│   │   │   └── persistence/
│   │   │       └── BookRepository.java
│   │   ├── orders/
│   │   │   ├── api/
│   │   │   │   ├── OrderController.java
│   │   │   │   └── CreateOrderRequest.java
│   │   │   ├── application/
│   │   │   │   └── PlaceOrderService.java
│   │   │   ├── domain/
│   │   │   │   └── Order.java
│   │   │   └── persistence/
│   │   │       └── OrderRepository.java
│   │   ├── customers/
│   │   │   └── ...
│   │   └── configuration/
│   │       └── SecurityConfiguration.java
│   └── resources/
│       └── application.yml
└── test/
    └── java/com/example/bookstore/
        ├── catalog/
        └── orders/
~~~

Ý nghĩa của các package con (nếu cần) là:

| Package con | Trách nhiệm thường gặp | Cần tránh |
|---|---|---|
| `api` hoặc `web` | REST controller, HTTP request/response DTO, chuyển đổi lỗi liên quan đến API | Viết toàn bộ quy tắc nghiệp vụ ngay trong controller |
| `application` | Điều phối use case, transaction ở mức tác vụ, gọi các thành phần cần thiết | Chứa mọi loại logic không phân biệt trách nhiệm |
| `domain` | Khái niệm và quy tắc nghiệp vụ, đối tượng thể hiện trạng thái hợp lệ | Phụ thuộc trực tiếp vào HTTP request hoặc giao diện người dùng |
| `persistence` hoặc `infrastructure` | Chi tiết lưu trữ, adapter gọi hệ thống ngoài, cấu hình tích hợp riêng của feature | Để các feature khác phụ thuộc thẳng vào chi tiết lưu trữ |

Các tên `api`, `application`, `domain`, `persistence` là quy ước phổ biến, **không phải yêu cầu của Spring Boot**. Một feature chỉ có một controller và một service có thể đặt hai lớp trực tiếp trong `catalog`. Đừng tạo nhiều package rỗng hoặc những tầng chỉ chuyển tiếp lời gọi mà không mang ý nghĩa.

### Package gốc và component scan

Đặt lớp khởi động tại package chung cao nhất mà Spring cần quét:

~~~java
package com.example.bookstore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookstoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookstoreApplication.class, args);
    }
}
~~~

Với vị trí này, component scan mặc định có thể tìm các thành phần được chú thích như `@RestController`, `@Service`, `@Component` trong những package con `com.example.bookstore.catalog`, `com.example.bookstore.orders`, v.v.

Nếu vô tình đặt `BookstoreApplication` trong `com.example.bookstore.orders`, Spring có thể không tự quét được controller trong `catalog` theo mặc định. Điều này là vấn đề **phạm vi quét**, không phải bằng chứng rằng cách tổ chức theo feature không tương thích với Spring.

Với Spring Data JPA, phạm vi quét entity và repository mặc định cũng liên quan tới package cấu hình ứng dụng và các thiết lập auto-configuration. Nếu chủ động đưa entity/repository ra ngoài cây package, cần cấu hình quét tương ứng theo đúng phiên bản và công nghệ sử dụng.

## 5. Ví dụ tương tác giữa hai feature: Catalog và Orders

Một hệ thống thực tế cần cho phép các feature phối hợp. Ví dụ, **Orders** cần biết thông tin giá sản phẩm từ **Catalog** trước khi tạo đơn. Cách tổ chức tốt là cho Catalog công bố một **hợp đồng nhỏ**, đồng thời giữ chi tiết persistence của Catalog ở bên trong.

Để tập trung vào ranh giới package, các đoạn mã sau chỉ minh họa những lớp quan trọng; các lớp hỗ trợ như entity, repository và exception cần được triển khai đầy đủ trong ứng dụng thật.

### 5.1. Catalog công bố hợp đồng đọc sản phẩm

File `catalog/ProductInfo.java`:

~~~java
package com.example.bookstore.catalog;

import java.math.BigDecimal;

public record ProductInfo(
        Long id,
        String title,
        BigDecimal unitPrice
) {}
~~~

File `catalog/ProductCatalog.java`:

~~~java
package com.example.bookstore.catalog;

public interface ProductCatalog {
    ProductInfo findAvailableProduct(Long productId);
}
~~~

Hai kiểu dữ liệu này đóng vai trò **API Java giữa các phần nghiệp vụ trong cùng ứng dụng**. `ProductInfo` chỉ mang thông tin mà feature khác thực sự cần; nó không phơi bày entity JPA hay repository nội bộ.

### 5.2. Catalog tự triển khai hợp đồng bằng dữ liệu của mình

Ví dụ service bên trong Catalog:

~~~java
package com.example.bookstore.catalog;

import org.springframework.stereotype.Service;

@Service
class DatabaseProductCatalog implements ProductCatalog {
    private final BookRepository repository;

    DatabaseProductCatalog(BookRepository repository) {
        this.repository = repository;
    }

    @Override
    public ProductInfo findAvailableProduct(Long productId) {
        Book book = repository.findById(productId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy sách"));

        return new ProductInfo(
                book.getId(),
                book.getTitle(),
                book.getCurrentPrice()
        );
    }
}
~~~

Ở ví dụ này, `BookRepository` và `Book` được giả định là các kiểu nội bộ cùng package `catalog`; code thực tế có thể đặt chúng trong các package con và điều chỉnh phạm vi truy cập cho phù hợp. Việc để `DatabaseProductCatalog` không có từ khóa `public` biểu thị ý định giữ một chi tiết triển khai nội bộ package.

Spring vẫn có thể phát hiện `@Service` nằm dưới package gốc và inject bean bằng interface `ProductCatalog` trong cách đóng gói ứng dụng Spring Boot thông thường. Nếu dùng Java Platform Module System hoặc các quy tắc đóng gói chặt hơn, cần thiết kế quyền truy cập và reflection phù hợp.

### 5.3. Orders phụ thuộc vào hợp đồng, không phụ thuộc repository Catalog

File `orders/PlaceOrderService.java` (ví dụ rút gọn):

~~~java
package com.example.bookstore.orders;

import com.example.bookstore.catalog.ProductCatalog;
import com.example.bookstore.catalog.ProductInfo;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final ProductCatalog productCatalog;
    private final OrderRepository orderRepository;

    public PlaceOrderService(
            ProductCatalog productCatalog,
            OrderRepository orderRepository
    ) {
        this.productCatalog = productCatalog;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long place(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn 0"
            );
        }

        ProductInfo product =
                productCatalog.findAvailableProduct(productId);

        Order order = Order.create(
                product.id(),
                product.unitPrice(),
                quantity
        );

        return orderRepository.save(order).getId();
    }
}
~~~

Các kiểu `Order` và `OrderRepository` thuộc quyền sở hữu của Orders, và ở ví dụ này được giả định nằm cùng package `orders`. Phương thức `Order.create(...)` biểu thị nơi đặt quy tắc tạo đơn, chẳng hạn lưu lại đơn giá tại thời điểm đặt; chi tiết của quy tắc không cần thiết cho việc hiểu cách tổ chức package.

Hướng phụ thuộc chính:

~~~text
    orders/PlaceOrderService
             |
             | gọi API công khai
             v
      catalog/ProductCatalog
             ^
             | triển khai
             |
 catalog/DatabaseProductCatalog
             |
             v
     catalog/BookRepository
~~~

Orders cần biết `ProductCatalog` và `ProductInfo` nhưng **không cần biết** Catalog đang dùng JPA, JDBC, API bên ngoài hay cache. Việc thay đổi phương án lưu trữ của Catalog vì thế ít ảnh hưởng đến Orders, miễn hợp đồng và ý nghĩa nghiệp vụ được giữ nguyên.

Nếu Orders trực tiếp inject `BookRepository` của Catalog và thao tác `Book` như entity của chính mình, các quy tắc truy cập dữ liệu sẽ bị phân tán. Khi Catalog đổi mô hình lưu trữ, Orders dễ bị kéo theo.

### 5.4. Controller nên hướng tới use case của feature

Controller của Orders thường chỉ chuyển HTTP request thành lời gọi nghiệp vụ và chuyển kết quả về HTTP response:

~~~java
package com.example.bookstore.orders;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final PlaceOrderService placeOrderService;

    public OrderController(PlaceOrderService placeOrderService) {
        this.placeOrderService = placeOrderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderCreatedResponse create(
            @RequestBody CreateOrderRequest request
    ) {
        Long orderId = placeOrderService.place(
                request.productId(), request.quantity()
        );
        return new OrderCreatedResponse(orderId);
    }

    public record CreateOrderRequest(Long productId, int quantity) {}
    public record OrderCreatedResponse(Long id) {}
}
~~~

Một request ví dụ:

~~~http
POST /orders
Content-Type: application/json

{
  "productId": 101,
  "quantity": 2
}
~~~

Luồng xử lý:

1. `OrderController` trong Orders nhận request và chuyển thành tham số use case.
2. `PlaceOrderService` kiểm tra điều kiện đặt hàng và hỏi Catalog qua `ProductCatalog`.
3. Catalog tự đọc thông tin sách bằng cơ chế nội bộ của mình.
4. Orders tạo đối tượng đơn hàng và lưu bằng repository của Orders.
5. Controller trả về ID đơn hàng qua HTTP response.

Đây là **minh họa ranh giới và hướng gọi**, chưa phải quy trình đặt hàng hoàn chỉnh. Một hệ thống bán hàng thật còn phải xử lý validation đầu vào, tiền tệ, giá thay đổi, giữ tồn kho, lỗi cạnh tranh, phân quyền, exception mapping và tính nhất quán khi nhiều giao dịch xảy ra đồng thời. Các trách nhiệm ấy cần được đặt trong đúng phần nghiệp vụ sở hữu quy tắc.

## 6. Đặt ranh giới giữa các package để giảm phụ thuộc

Chuyển file vào thư mục theo feature chỉ giải quyết phần hiển thị của cấu trúc. Để package có ý nghĩa lâu dài, cần hình thành một số quy tắc phụ thuộc.

### Chỉ công khai những thứ cần được sử dụng bên ngoài feature

Một feature có thể có **giao diện công khai** và **chi tiết nội bộ**:

~~~text
catalog/
├── ProductCatalog.java        <- hợp đồng dùng bởi feature khác
├── ProductInfo.java           <- dữ liệu cần thiết để trao đổi
├── DatabaseProductCatalog.java <- chi tiết triển khai
├── Book.java                  <- mô hình nội bộ Catalog
└── BookRepository.java        <- cơ chế lưu trữ nội bộ
~~~

Trong Java, package-private (không viết `public` cho top-level class) có thể hạn chế lớp khác package truy cập trực tiếp. Tuy nhiên, **package con là package khác**: `catalog.persistence` không cùng Java package với `catalog`. Nếu tổ chức nhiều package con, việc kiểm soát công khai cần dựa thêm vào mô-đun, API rõ ràng, code review hoặc công cụ kiểm tra kiến trúc khi thật sự cần. Đừng giả định mọi thứ nằm dưới tên `catalog.*` tự động bị ẩn khỏi `orders`.

Không phải mọi class `public` đều nên được coi là hợp đồng sử dụng ổn định. Tên package, quy ước nhóm và trách nhiệm được công bố cũng rất quan trọng.

### Hạn chế vòng phụ thuộc

Ví dụ có vấn đề:

~~~text
orders/OrderService -> catalog/BookService
catalog/BookService -> orders/OrderService
~~~

Vòng phụ thuộc làm khó hiểu luồng nghiệp vụ; trong Spring, nó còn có thể gây vòng phụ thuộc bean khi khởi tạo. Không nên giải quyết mặc định bằng cách bật cho phép circular references. Hãy xác định phần nào thực sự sở hữu công việc: chuyển use case điều phối sang đúng feature, định nghĩa hợp đồng một chiều hoặc dùng cơ chế sự kiện nếu quy trình nghiệp vụ phù hợp.

Ví dụ, sau khi đơn được tạo, Orders có thể phát một sự kiện “OrderPlaced” để phần khác xử lý công việc hậu kỳ. Nhưng event không phải giải pháp mặc định: phải cân nhắc transaction, xử lý lỗi, retry, idempotency và thứ tự sự kiện. Với một lời gọi đồng bộ đơn giản, interface công khai giữa các feature thường dễ hiểu hơn.

### Tránh package “dùng chung” trở thành nơi chứa mọi thứ

Một package `shared` hoặc `common` thường bắt đầu nhỏ rồi tích lũy nhiều utility, DTO, entity và quy tắc nghiệp vụ của mọi feature. Cuối cùng mọi feature đều phụ thuộc vào nó, làm mất ranh giới sở hữu.

Chỉ chuyển mã thật sự có nghĩa chung vào khu vực dùng chung, chẳng hạn cấu hình hạ tầng cấp ứng dụng hoặc một abstraction ổn định được nhiều phần sử dụng. Nếu hai feature có DTO tên giống nhau nhưng ngữ nghĩa khác nhau, giữ hai DTO độc lập thường tốt hơn tạo một kiểu “dùng chung” dễ bị kéo theo thay đổi.

## 7. Kết hợp tổ chức theo feature với kiến trúc phân tầng

“Tổ chức theo feature” và “thiết kế theo tầng” không loại trừ nhau. Chúng trả lời hai câu hỏi khác nhau:

- **Theo feature/domain:** ai sở hữu mã nguồn và quy tắc?
- **Theo tầng:** bên trong feature đó, mã nguồn chịu trách nhiệm ở mức nào?

Ví dụ, cấu trúc sau là một lựa chọn hợp lý cho feature có logic phức tạp:

~~~text
orders/
├── api/
│   ├── OrderController.java
│   └── dto/
├── application/
│   ├── PlaceOrderUseCase.java
│   └── CancelOrderUseCase.java
├── domain/
│   ├── Order.java
│   └── OrderStatus.java
└── infrastructure/
    ├── JpaOrderRepository.java
    └── OrderJpaEntity.java
~~~

Trong một kiến trúc có mục tiêu tách domain khỏi công nghệ, các đối tượng domain không cần biết `@RestController` hoặc cách JPA lưu dữ liệu; interface repository có thể nằm gần domain/application, còn implementation nằm ở infrastructure. Tuy nhiên, đó là **lựa chọn kiến trúc bổ sung**, không phải điều bắt buộc của việc gom package theo feature.

Với ứng dụng CRUD nhỏ, dùng entity JPA trực tiếp trong service của feature có thể là giải pháp đơn giản và chấp nhận được. Khi các quy tắc nghiệp vụ nhiều lên và thay đổi độc lập với lưu trữ, tách mô hình domain khỏi persistence trở nên có giá trị hơn. Mức độ phân tầng nên đi theo độ phức tạp thực tế.

## 8. Một số quyết định tổ chức thường gặp

### Feature nên rộng hay hẹp?

Một feature quá rộng, ví dụ `commerce` chứa tất cả danh mục, đặt hàng, thanh toán và giao hàng, tạo ra package khổng lồ. Một feature quá hẹp, ví dụ mỗi thao tác `createOrder`, `cancelOrder`, `getOrder` đều có package cấp cao hoàn toàn riêng, dễ làm mất khái niệm đơn hàng chung.

Thường có thể bắt đầu từ một **năng lực nghiệp vụ có ngữ nghĩa ổn định**, sau đó chia nhỏ khi có các quy tắc hoặc nhóm thay đổi độc lập. Những use case trong cùng một miền có thể nằm dưới `orders.application` nếu thấy hữu ích.

### DTO request/response đặt ở đâu?

DTO phụ thuộc vào hợp đồng mà nó phục vụ. `CreateOrderRequest` thuộc API của Orders, vì vậy nên đặt gần `OrderController` hoặc trong `orders.api.dto`. DTO của Catalog không nên được dùng làm request của Orders chỉ vì có vài trường giống nhau.

DTO trao đổi giữa các feature khác DTO HTTP: `ProductInfo` trong ví dụ là hợp đồng giữa Orders và Catalog, không nhất thiết là JSON mà Catalog trả cho người dùng cuối. Phân biệt hai loại hợp đồng giúp thay đổi API HTTP mà ít tác động tới các feature nội bộ.

### Validation thuộc lớp nào?

Ràng buộc hình thức của HTTP request (ví dụ trường bắt buộc, định dạng) có thể xử lý ở lớp API, thường dùng Bean Validation. Nhưng quy tắc như “đơn đã giao không được hủy” phải được đảm bảo ở nơi sở hữu nghiệp vụ đơn hàng. Nếu chỉ đặt trong controller, một luồng gọi service khác có thể bỏ qua quy tắc.

### Giao dịch đặt ở đâu?

`@Transactional` thường được đặt tại ranh giới use case/service phù hợp, nơi ứng dụng cần bảo đảm các thay đổi dữ liệu diễn ra theo đơn vị giao dịch. Không có quy tắc nào yêu cầu tất cả transaction phải nằm trong một package `transaction` toàn cục. Package organization không thay đổi bản chất Spring transaction, cơ chế proxy hay phạm vi giao dịch của database.

### Cấu hình và security nằm ở đâu?

Cấu hình toàn ứng dụng, ví dụ cấu hình Spring Security chung, có thể nằm dưới `configuration` ở package gốc. Cấu hình chỉ phục vụ Orders có thể đặt trong `orders`. Quy tắc phân quyền đặc thù nghiệp vụ vẫn cần được thực thi ở lớp thích hợp bên trong feature; đặt chung security configuration không đồng nghĩa tất cả kiểm tra nghiệp vụ đều nằm ở đó.

## 9. Kiểm thử và làm việc nhóm theo ranh giới feature

Một cấu trúc test thường phản chiếu cấu trúc source:

~~~text
src/test/java/com/example/bookstore/
├── catalog/
│   ├── ProductCatalogTest.java
│   └── CatalogControllerTest.java
└── orders/
    ├── PlaceOrderServiceTest.java
    └── OrderControllerTest.java
~~~

Khi cần kiểm tra quy tắc đặt hàng, lập trình viên biết tìm test trong `orders`. Khi cần kiểm tra hợp đồng giữa Orders và Catalog, bài test có thể mô phỏng `ProductCatalog` để tập trung vào quyết định của Orders, hoặc dùng integration test nếu cần kiểm tra thực sự cách hai phần phối hợp.

Trong Spring Boot, có thể dùng các loại test phù hợp: kiểm thử lớp Java thuần cho quy tắc domain, web slice với `@WebMvcTest` cho controller, data slice với `@DataJpaTest` cho persistence hoặc `@SpringBootTest` cho luồng tích hợp. Mỗi cách có mục đích khác nhau; không phải cứ tổ chức theo feature thì phải tạo ApplicationContext mới cho từng package.

Đối với nhóm phát triển, ranh giới feature cũng giúp phân công trách nhiệm và giảm xung đột sửa cùng một tập file. Nhưng nếu nhiều nhóm cần thay đổi liên tục cùng một API nội bộ, đó là tín hiệu cần trao đổi lại về hợp đồng hoặc cách chia ranh giới, không chỉ đổi tên package.

## 10. Khi nào nên dùng cách nào?

| Bối cảnh | Gợi ý tổ chức | Lý do |
|---|---|---|
| Bài học Spring Boot đầu tiên, rất ít lớp | Theo tầng hoặc nhóm feature đơn giản | Người học dễ thấy mối quan hệ controller–service–repository |
| Dự án có vài chức năng tương đối độc lập | **Theo feature**, mỗi feature có controller/service/repository riêng | Dễ tìm mã và sửa trọn một chức năng |
| Nghiệp vụ đa dạng, nhiều quy tắc và nhiều nhóm phụ trách | **Theo miền nghiệp vụ**, xác định trách nhiệm và hợp đồng | Tránh lan truyền quy tắc và phụ thuộc chéo |
| Một feature bắt đầu có nhiều thành phần | Bên ngoài theo feature, bên trong chia `api`/`application`/`domain`/`infrastructure` khi có ích | Vừa giữ ranh giới nghiệp vụ, vừa rõ trách nhiệm kỹ thuật |
| Dự án đang tổ chức theo tầng nhưng vẫn dễ bảo trì | Chỉ chuyển dần những phần có nhu cầu thay đổi | Tránh đổi cấu trúc hàng loạt mà chưa mang lại giá trị |

Không cần chọn giữa “100% package theo tầng” và “100% package theo feature”. Có thể bắt đầu đơn giản, quan sát các nhóm file thường được thay đổi cùng nhau, rồi hình thành các ranh giới phù hợp. Tổ chức dựa trên **cách hệ thống thay đổi** thường bền vững hơn một sơ đồ cố định áp cho mọi dự án.

## 11. Chuyển dần từ cấu trúc theo tầng sang theo feature

Nếu một dự án đã có nhiều file trong `controller`, `service`, `repository`, không nhất thiết phải di chuyển tất cả một lần. Có thể thực hiện theo từng khả năng nghiệp vụ:

1. **Chọn một phạm vi rõ ràng**, ví dụ đặt hàng. Xác định controller, service, entity, repository, DTO và test thực sự thuộc phạm vi đó.
2. **Liệt kê các phụ thuộc ra bên ngoài**: Orders đang gọi lớp nào của Catalog, Customers hoặc hạ tầng chung? Xác định lời gọi nào là hợp đồng cần giữ.
3. **Tạo package `orders`** và di chuyển các lớp cùng test liên quan; cập nhật khai báo `package` và `import` bằng chức năng refactor của IDE.
4. **Định nghĩa API nội bộ nhỏ** cho phần cần được feature khác gọi; tránh buộc phần khác đi thẳng vào repository hoặc entity nội bộ.
5. **Điều chỉnh phạm vi truy cập** và nơi đặt dependency injection để thể hiện rõ ranh giới, nếu dự án cho phép.
6. **Rà soát những thứ phụ thuộc tên class/package** như cấu hình scan, mapping framework, rule security hoặc tham chiếu kiểu dữ liệu. Khi chỉ đổi package, HTTP endpoint và schema database thường không cần đổi, trừ khi dự án có cấu hình gắn với tên lớp/package.
7. **Tiếp tục với feature tiếp theo** khi cấu trúc mới đã ổn định và giúp việc thay đổi dễ hiểu hơn.

Trong Spring Boot, thao tác di chuyển package cần đặc biệt chú ý đến vị trí `@SpringBootApplication`, phạm vi quét component, entity và Spring Data repository. Đây là những cơ chế có thể bị ảnh hưởng bởi tên package dù logic nghiệp vụ không thay đổi.

## 12. Những dấu hiệu tổ chức chưa hợp lý

Có thể quan sát một vài triệu chứng để quyết định cần điều chỉnh:

| Dấu hiệu | Nguyên nhân có thể | Hướng cải thiện |
|---|---|---|
| Một yêu cầu nhỏ phải sửa ở rất nhiều package kỹ thuật | Cấu trúc theo tầng phân tán file cùng feature | Gom theo feature hoặc use case liên quan |
| Một service xử lý tạo đơn, cập nhật tồn kho, tính hóa đơn và gửi hàng | Trách nhiệm nghiệp vụ quá rộng | Xác định miền sở hữu; điều phối qua hợp đồng rõ ràng |
| Nhiều feature inject repository của nhau | Ranh giới dữ liệu bị vượt qua | Tạo API/use case công khai cho chủ sở hữu dữ liệu |
| `shared` chứa phần lớn logic nghiệp vụ | Không rõ nơi sở hữu mã | Đưa logic về miền phù hợp, chỉ chia sẻ abstraction ổn định |
| Thường xảy ra vòng phụ thuộc giữa feature | Đường gọi không có hướng rõ ràng | Xác định bên điều phối và quy tắc phụ thuộc một chiều |
| Mỗi controller, service đơn giản đều có nhiều interface và tầng trung gian | Phân tầng hình thức vượt nhu cầu | Giảm lớp chuyển tiếp, giữ cấu trúc vừa đủ |
| Package đặt theo tên màn hình nhưng một nghiệp vụ chạy qua nhiều màn hình | Ranh giới dựa vào UI hơn là quy tắc thực tế | Gom mã theo khả năng hoặc miền sở hữu nghiệp vụ |

Một nguyên tắc thực dụng: **những lớp thường thay đổi vì cùng một lý do nên được đặt gần nhau; những phần có lý do thay đổi khác nhau nên có ranh giới rõ ràng.** Nếu một thay đổi ở Catalog buộc sửa hàng loạt lớp bên trong Orders, hãy xem xét hợp đồng giữa hai feature.

## 13. Bài tập tự áp dụng

Giả sử bạn đang tạo ứng dụng Spring Boot cho thư viện trường học. Các yêu cầu ban đầu:

- Học sinh tìm kiếm sách theo tên hoặc tác giả.
- Thủ thư quản lý số lượng bản sách đang có.
- Học sinh mượn và trả sách.
- Hệ thống tính số ngày mượn quá hạn và phí phạt.

Hãy thử thiết kế package cấp cao trước khi viết controller. Một điểm khởi đầu có thể là:

~~~text
com.example.library/
├── LibraryApplication.java
├── catalog/
│   └── ... tìm kiếm và mô tả sách
├── inventory/
│   └── ... số lượng bản sách và tình trạng sẵn sàng
├── loans/
│   └── ... quy tắc mượn, trả và hạn trả
└── fines/
    └── ... cách tính, ghi nhận và thanh toán phí phạt
~~~

Tự trả lời: dữ liệu “tên sách” thuộc Catalog hay Loans? Quy tắc “không cho mượn khi hết bản sách” thuộc phần nào? Nếu Loans cần biết tình trạng còn sách, nên gọi thẳng `InventoryRepository` hay gọi một hợp đồng mà Inventory cung cấp? Khi thư viện bổ sung chính sách phí phạt mới, những package nào có lý do hợp lệ để thay đổi?

Không có một cây package duy nhất đúng trong mọi bài toán. Điều cần giải thích được là **trách nhiệm mỗi package**, **luồng phụ thuộc giữa các package**, **cách thay đổi nghiệp vụ ảnh hưởng đến mã nguồn** và **Spring Boot sẽ phát hiện các thành phần như thế nào**.

## Kết luận

Tổ chức mã nguồn Spring Boot theo chức năng hoặc miền nghiệp vụ đặt trọng tâm vào những việc ứng dụng thực hiện và những quy tắc mà hệ thống phải bảo vệ. Cấu trúc theo tầng kỹ thuật vẫn hữu ích để chia trách nhiệm bên trong một feature; điều quan trọng là tránh để một năng lực nghiệp vụ bị phân tán và phụ thuộc vào quá nhiều chi tiết của phần khác.

Hãy bắt đầu bằng tên package thể hiện nghiệp vụ, giữ thành phần liên quan gần nhau, công bố những hợp đồng thật sự cần thiết và kiểm soát chiều phụ thuộc. Với Spring Boot, nhớ đặt lớp khởi động ở package gốc phù hợp để component scan và những cơ chế quét liên quan tìm được thành phần ứng dụng. Khi nhu cầu tăng, ranh giới feature/domain sẽ là điểm tựa để bổ sung use case, kiểm thử và tiến hóa kiến trúc mà không phải làm lại toàn bộ hệ thống.
