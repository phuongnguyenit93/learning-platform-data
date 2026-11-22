# Đảo ngược điều khiển và bài toán quản lý đồ thị đối tượng

Một chương trình Java hiếm khi chỉ gồm một đối tượng hoạt động độc lập. Controller nhận HTTP request cần gọi service; service cần repository, bộ tính giá hoặc client gọi hệ thống ngoài; repository lại cần một đối tượng kết nối cơ sở dữ liệu. Những đối tượng đó **phụ thuộc vào nhau** và tạo thành một **đồ thị đối tượng** (*object graph*).

Spring Boot giải quyết phần lớn công việc tạo và kết nối đồ thị này thông qua **Spring IoC container**. Để hiểu cơ chế đó, cần bắt đầu từ bài toán cụ thể: ai chịu trách nhiệm tạo các đối tượng, lựa chọn implementation, cung cấp dependency, quản lý vòng đời và đảm bảo cấu hình nhất quán?

**Inversion of Control (IoC, đảo ngược điều khiển)** là nguyên tắc chuyển quyền quyết định việc tạo và kết nối các thành phần từ mã ứng dụng sang một cơ chế điều phối bên ngoài. **Dependency Injection (DI, tiêm phụ thuộc)** là một cách thực hiện IoC: đối tượng nhận dependency cần thiết từ bên ngoài thay vì tự tạo nó. Trong Spring, cơ chế bên ngoài đó chủ yếu là **ApplicationContext**, tức một IoC container có khả năng đăng ký, khởi tạo, kết nối và quản lý các **bean**.

## 1. Đồ thị đối tượng là gì?

Giả sử một ứng dụng bán sách có endpoint tính giá đơn hàng:

- `QuoteController` nhận yêu cầu HTTP.
- `QuoteService` xử lý quy tắc tính báo giá.
- `ProductCatalog` tìm thông tin sách.
- `PricingPolicy` tính tổng tiền theo chính sách giá.
- `InMemoryProductCatalog` và `StandardPricingPolicy` là các implementation cụ thể.

Quan hệ giữa chúng có thể hình dung như sau:

~~~text
HTTP request
     |
     v
QuoteController
     |
     v
QuoteService
     |                     |
     v                     v
ProductCatalog        PricingPolicy
     ^                     ^
     |                     |
InMemoryProductCatalog  StandardPricingPolicy
~~~

**Nút** của đồ thị là các đối tượng (hoặc các định nghĩa bean khi ta nói về giai đoạn cấu hình), còn **cạnh** biểu thị quan hệ một đối tượng cần hoặc giữ tham chiếu tới đối tượng khác. Với sơ đồ trên:

- Controller không thể làm việc đúng nếu không có service.
- Service phụ thuộc vào hai hợp đồng, nhưng không cần tự biết cách tạo implementation.
- Có thể thay implementation của `ProductCatalog` mà vẫn giữ nguyên mã của `QuoteService` nếu hợp đồng không thay đổi.

Đồ thị thật có thể lớn hơn nhiều và **không nhất thiết là một cây**. Hai service có thể dùng chung một bean repository, một bean cấu hình hoặc một HTTP client. Một đối tượng có thể được nhiều đối tượng khác tham chiếu; thậm chí nếu thiết kế kém, có thể hình thành vòng phụ thuộc.

### Đồ thị phụ thuộc không đồng nghĩa với luồng gọi hàm

Hai khái niệm thường bị nhầm:

- **Đồ thị dependency:** đối tượng nào cần tham chiếu tới đối tượng nào để hoạt động.
- **Luồng thực thi:** trong một request hoặc sự kiện, phương thức nào thực sự được gọi, theo thứ tự nào.

`QuoteService` giữ tham chiếu tới `ProductCatalog` không có nghĩa mỗi lần gọi service đều phải gọi catalog. Dependency mô tả **khả năng và yêu cầu kết nối** của thành phần; luồng thực thi phụ thuộc vào logic và đầu vào.

## 2. Vấn đề khi mỗi lớp tự tạo dependency bằng `new`

Trong một ứng dụng đơn giản, chúng ta có thể viết:

~~~java
public class QuoteService {
    private final ProductCatalog catalog =
            new InMemoryProductCatalog();

    private final PricingPolicy pricing =
            new StandardPricingPolicy();

    public long quote(String sku, int quantity) {
        Product product = catalog.findBySku(sku)
                .orElseThrow();
        return pricing.total(product.unitPrice(), quantity);
    }
}
~~~

Mã này có thể chạy, nhưng `QuoteService` đang làm hai việc: **xử lý nghiệp vụ** và **quyết định cách xây dựng hạ tầng phục vụ nghiệp vụ**. Hệ quả sẽ rõ khi yêu cầu thay đổi:

1. Nếu cần đọc catalog từ PostgreSQL thay vì bộ nhớ, phải sửa cách tạo dependency trong service hoặc cài thêm điều kiện môi trường.
2. Khi kiểm thử, khó cung cấp một catalog giả với dữ liệu có kiểm soát, vì service tự tạo catalog thật.
3. Khi nhiều service cần dùng cùng catalog hoặc client mạng, mỗi nơi có thể tạo một instance khác nhau; có thể lặp connection pool, cache hoặc cấu hình.
4. Nếu `InMemoryProductCatalog` lại cần `DataSource` hay cấu hình, chuỗi `new` tiếp tục lan sang các lớp khác.
5. Những lựa chọn như secret, timeout hoặc endpoint bên ngoài có thể bị gắn cứng trong mã nghiệp vụ.

Vấn đề cốt lõi không phải từ khóa `new` là xấu. Tạo một giá trị ngắn hạn, chẳng hạn `new OrderLine(...)` hoặc `new ArrayList<>()` bên trong phương thức hoàn toàn bình thường. Vấn đề xuất hiện khi lớp nghiệp vụ **tự sở hữu việc tạo các cộng tác viên dài hạn**, đặc biệt những dependency thay đổi theo môi trường hoặc cần dùng chung.

## 3. Dependency Injection chuyển việc lắp ghép ra ngoài

Một bước cải thiện quan trọng là nhận dependency qua constructor:

~~~java
public class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    public QuoteService(
            ProductCatalog catalog,
            PricingPolicy pricing
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
    }

    public long quote(String sku, int quantity) {
        Product product = catalog.findBySku(sku)
                .orElseThrow();
        return pricing.total(product.unitPrice(), quantity);
    }
}
~~~

Bây giờ, service chỉ nói: “Tôi cần một `ProductCatalog` và một `PricingPolicy`”. Mã lắp ghép nằm ở nơi khác:

~~~java
ProductCatalog catalog = new InMemoryProductCatalog();
PricingPolicy pricing = new StandardPricingPolicy();

QuoteService quoteService = new QuoteService(catalog, pricing);
QuoteController controller = new QuoteController(quoteService);
~~~

Trong cách này, Java thuần vẫn có DI: đối tượng được **tiêm qua constructor**. Chúng ta chưa cần Spring để áp dụng nguyên tắc, vì constructor injection là một kỹ thuật thiết kế Java thông thường.

Nơi tập trung tạo và kết nối các đối tượng thường được gọi là **composition root**. Với Spring Boot, phần lớn vai trò này được chuyển sang các bean definition, component scanning, `@Configuration`, `@Bean` và cơ chế auto-configuration. ApplicationContext sử dụng những thông tin đó để thực hiện việc kết nối.

### “Đảo ngược” chính xác là đảo ngược điều gì?

So sánh hai hướng điều khiển:

~~~text
Tự điều khiển việc tạo dependency:

QuoteService
    |
    +-- new InMemoryProductCatalog()
    |
    +-- new StandardPricingPolicy()


Dependency Injection:

Composition root / Spring container
    |
    +-- tạo InMemoryProductCatalog
    +-- tạo StandardPricingPolicy
    +-- tạo QuoteService(catalog, pricing)
                 |
                 +-- chỉ dùng dependency được cấp
~~~

Trước khi áp dụng DI, `QuoteService` kiểm soát việc lựa chọn và tạo implementation. Sau đó, **bên ngoài** đưa implementation cho service. Service vẫn hoàn toàn kiểm soát quy tắc nghiệp vụ của nó; IoC không có nghĩa mọi lệnh Java đều do framework thực thi.

## 4. IoC, DI, bean và ApplicationContext khác nhau thế nào?

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **IoC** | Nguyên tắc chuyển một phần quyền điều khiển việc lắp ghép và vòng đời đối tượng cho cơ chế bên ngoài | Container tạo và kết nối các thành phần |
| **DI** | Cách cung cấp dependency từ bên ngoài cho đối tượng | `new QuoteService(catalog, pricing)` |
| **Bean** | Đối tượng được Spring container quản lý | `QuoteService` được đánh dấu `@Service` và được quét |
| **Bean definition** | Metadata cho container biết cách tạo/cấu hình một bean | Metadata từ `@Component` hoặc phương thức `@Bean` |
| **BeanFactory** | Giao diện lõi cung cấp đăng ký/truy xuất bean và cơ chế container cơ bản | Nền tảng của cơ chế quản lý bean |
| **ApplicationContext** | Giao diện container phổ biến, mở rộng BeanFactory với nhiều khả năng tích hợp | Context tạo bởi `SpringApplication.run(...)` |
| **Auto-configuration** | Cơ chế Spring Boot đăng ký cấu hình dựa trên classpath, bean, property và điều kiện | Tự cấu hình web server hoặc DataSource khi phù hợp |

Điểm quan trọng: **không phải mọi đối tượng Java đều là Spring bean**. Những object tạo bằng `new` thông thường vẫn tồn tại và có ích; chúng chỉ không tự động tham gia quản lý vòng đời, wiring, AOP hay DI của container.

Một bean thường có **tên**, **kiểu**, **scope**, cách tạo, dependency và các metadata khác. Container dùng những thông tin này để xây dựng object graph có thể hoạt động.

## 5. Ví dụ Spring Boot: để container tự lắp một đồ thị nhỏ

Ví dụ dưới đây dùng ứng dụng web Spring Boot với Java 17 trở lên và Spring MVC. Để chạy bằng cách thông thường, dự án cần starter web tương ứng với phiên bản Spring Boot đang sử dụng. Các lớp nằm trong cùng package `com.example.shop` để tập trung vào cơ chế DI; ở dự án thực tế có thể tách thành nhiều package theo chức năng.

### 5.1. Điểm khởi động đặt ở package gốc

File `ShopApplication.java`:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bao gồm cấu hình và component scanning theo quy ước package, đồng thời kích hoạt auto-configuration của Spring Boot. Đặt lớp trong `com.example.shop` giúp Spring quét các bean nằm ở package này và các package con.

### 5.2. Định nghĩa hợp đồng thay vì gắn vào implementation

File `Product.java`:

~~~java
package com.example.shop;

public record Product(
        String sku,
        long unitPrice,
        int availableQuantity
) {}
~~~

File `ProductCatalog.java`:

~~~java
package com.example.shop;

import java.util.Optional;

public interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}
~~~

File `PricingPolicy.java`:

~~~java
package com.example.shop;

public interface PricingPolicy {
    long total(long unitPrice, int quantity);
}
~~~

Đây là các kiểu Java bình thường; riêng `Product` là record chứa dữ liệu, không nhất thiết cần container quản lý. Hai interface mô tả khả năng mà service yêu cầu; chúng không tự trở thành bean nếu chưa có implementation hoặc một bean tương ứng được đăng ký.

### 5.3. Đăng ký implementation cho container

File `InMemoryProductCatalog.java`:

~~~java
package com.example.shop;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryProductCatalog implements ProductCatalog {
    private final Map<String, Product> products = Map.of(
            "BOOK-001",
            new Product("BOOK-001", 120_000L, 10)
    );

    @Override
    public Optional<Product> findBySku(String sku) {
        return Optional.ofNullable(products.get(sku));
    }
}
~~~

File `StandardPricingPolicy.java`:

~~~java
package com.example.shop;

import org.springframework.stereotype.Component;

@Component
public class StandardPricingPolicy implements PricingPolicy {
    @Override
    public long total(long unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`@Repository` và `@Component` đánh dấu các thành phần để component scan đăng ký bean definition. `@Repository` là một specialization của `@Component` với ý nghĩa truy cập dữ liệu; tên annotation không tự biến Map trong bộ nhớ thành một cơ sở dữ liệu.

### 5.4. Service chỉ khai báo dependency cần dùng

File `QuoteService.java`:

~~~java
package com.example.shop;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    public QuoteService(
            ProductCatalog catalog,
            PricingPolicy pricing
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
    }

    public Quote quote(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn 0"
            );
        }

        Product product = catalog.findBySku(sku)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Không tìm thấy sản phẩm"
                        )
                );

        if (quantity > product.availableQuantity()) {
            throw new IllegalArgumentException(
                    "Không đủ tồn kho"
            );
        }

        long total = pricing.total(
                product.unitPrice(), quantity
        );

        return new Quote(sku, quantity, total);
    }
}
~~~

File `Quote.java`:

~~~java
package com.example.shop;

public record Quote(
        String sku,
        int quantity,
        long total
) {}
~~~

Service không gọi `new InMemoryProductCatalog()` hay `new StandardPricingPolicy()`. Nó phụ thuộc vào **hợp đồng** và nhận implementation qua constructor. Trong trường hợp chỉ có một bean phù hợp cho mỗi interface, Spring có thể tự giải quyết dependency dựa trên kiểu tham số.

Với một constructor duy nhất, Spring không yêu cầu thêm `@Autowired` vào constructor đó trong trường hợp thông thường. Việc sử dụng constructor injection thể hiện dependency bắt buộc và cho phép giữ các trường `final`.

### 5.5. Controller nhận service

File `QuoteController.java`:

~~~java
package com.example.shop;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {
    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @GetMapping("/quotes")
    public Quote quote(
            @RequestParam String sku,
            @RequestParam int quantity
    ) {
        return quoteService.quote(sku, quantity);
    }
}
~~~

Khi ứng dụng khởi động và các điều kiện cần thiết được đáp ứng, có thể gọi:

~~~http
GET http://localhost:8080/quotes?sku=BOOK-001&quantity=2
~~~

Kết quả minh họa:

~~~json
{
  "sku": "BOOK-001",
  "quantity": 2,
  "total": 240000
}
~~~

Nếu số lượng lớn hơn `10` hoặc mã SKU không tồn tại, service ném `IllegalArgumentException`. Mã trên chỉ minh họa IoC và luồng DI; chưa cài đặt xử lý HTTP exception chuyên biệt, xác thực, database hay tiền tệ cho ứng dụng production.

### 5.6. Đồ thị bean mà Spring cần xây dựng

~~~text
                    ApplicationContext
                           |
           +---------------+------------------+
           |               |                  |
           v               v                  v
  InMemoryProductCatalog  StandardPricingPolicy  QuoteController
           |               |                  |
           |               |                  v
           |               +------------> QuoteService
           |                                      ^
           +--------------------------------------+
~~~

Để đọc chính xác các quan hệ, có thể nhìn từ thành phần cần dependency:

~~~text
QuoteController
  └── QuoteService
      ├── ProductCatalog -> InMemoryProductCatalog
      └── PricingPolicy  -> StandardPricingPolicy
~~~

Container tạo hoặc tìm bean phù hợp, cung cấp vào constructor rồi tiếp tục kết nối đối tượng còn thiếu. Lớp ứng dụng chỉ cần khai báo **mình cần gì**, còn việc chọn implementation có thể được quyết định tại lớp cấu hình.

## 6. Container tìm bean definition từ đâu?

Spring có thể biết cách tạo một bean theo nhiều nguồn, phổ biến nhất trong Spring Boot là:

1. **Component scanning:** tìm các lớp có `@Component` hoặc các stereotype như `@Service`, `@Repository`, `@Controller`.
2. **Java configuration:** các phương thức `@Bean` trong lớp `@Configuration` trả về đối tượng cần container quản lý.
3. **Auto-configuration:** Spring Boot đăng ký bean/configuration khi những điều kiện cụ thể được thỏa mãn.
4. **Cơ chế đăng ký bean khác:** thư viện và mã cấu hình chuyên biệt có thể đăng ký metadata trực tiếp khi cần.

### `@Component` và các annotation chuyên biệt

~~~java
@Component
public class DefaultClockService {
    // ...
}

@Service
public class InvoiceService {
    // ...
}

@Repository
public class InvoiceRepositoryAdapter {
    // ...
}
~~~

Các stereotype không đơn thuần là nhãn trang trí. Chúng giúp trình quét component nhận diện những lớp mà ứng dụng muốn đưa vào quản lý. Tuy nhiên, việc Spring phát hiện lớp còn phụ thuộc vị trí package, phạm vi component scan, điều kiện được áp dụng và khả năng khởi tạo bean.

Sử dụng `@Service` cho logic ứng dụng hoặc `@Repository` cho thành phần truy cập dữ liệu giúp đọc mã dễ hiểu hơn, nhưng Spring không “tự viết nghiệp vụ” chỉ vì lớp có annotation tương ứng.

### `@Bean` phù hợp với đối tượng do thư viện ngoài cung cấp

Một số dependency không có annotation Spring hoặc không thuộc mã nguồn có thể sửa. Có thể đăng ký chúng bằng phương thức factory:

~~~java
package com.example.shop;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Nếu một service cần thời gian hệ thống:

~~~java
@Service
public class ExpirationService {
    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }
}
~~~

Ở đây, đối tượng `Clock` do phương thức `applicationClock()` tạo nhưng sau khi được đăng ký, nó là bean do container quản lý. Nếu service khác cũng inject `Clock`, Spring mặc định có thể cung cấp cùng singleton bean đó.

Khi `@Bean` cần một dependency khác, Spring có thể tiêm trực tiếp vào tham số phương thức:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public PricingClient pricingClient(
            ClientSettings settings
    ) {
        return new PricingClient(
                settings.baseUrl(),
                settings.timeout()
        );
    }
}
~~~

`ClientSettings` và `PricingClient` trong đoạn trên là các kiểu minh họa do dự án phải định nghĩa; mục đích là cho thấy **phương thức `@Bean` cũng tham gia đồ thị dependency**.

### Khi nào dùng `@Component`, khi nào dùng `@Bean`?

| Tình huống | Cách thường phù hợp | Vì sao |
|---|---|---|
| Lớp service do dự án sở hữu | `@Service` + constructor injection | Rõ mục đích, đơn giản |
| Thành phần xử lý HTTP | `@RestController` | Được Spring MVC nhận diện |
| Bộ chuyển đổi hoặc adapter do dự án viết | `@Component` hoặc stereotype thích hợp | Dễ quét và kết nối |
| Đối tượng từ thư viện bên thứ ba | Phương thức `@Bean` | Không cần sửa mã nguồn thư viện |
| Đối tượng cần dựng bằng factory hoặc cấu hình chi tiết | `@Bean` | Cho phép kiểm soát quá trình tạo |
| Kiểu dữ liệu ngắn hạn được tạo khi xử lý nghiệp vụ | `new` bình thường | Không cần quản lý như một bean |

Hai cơ chế đều tạo bean, khác ở cách cung cấp định nghĩa. Không nên sử dụng đồng thời cả `@Component` và `@Bean` cho cùng một đối tượng nếu không có chủ đích, vì có thể vô tình tạo nhiều bean cùng kiểu.

## 7. Spring giải quyết dependency bằng cách nào?

Container cần xác định bean nào tương ứng với tham số constructor. Trường hợp đơn giản nhất là **một bean phù hợp với kiểu được yêu cầu**.

~~~text
QuoteService(ProductCatalog catalog)
                     |
                     v
       InMemoryProductCatalog bean
           implements ProductCatalog
~~~

Nếu không có bean phù hợp, ứng dụng thường không thể khởi tạo service và báo lỗi thiếu dependency. Nếu có nhiều bean cùng kiểu mà container không thể xác định nên chọn cái nào, ứng dụng thường báo dependency không duy nhất.

### Khi có nhiều implementation cùng interface

Giả sử có hai chính sách giá:

~~~java
@Component
public class StandardPricingPolicy implements PricingPolicy {
    @Override
    public long total(long price, int quantity) {
        return Math.multiplyExact(price, quantity);
    }
}
~~~

~~~java
@Component
public class DiscountPricingPolicy implements PricingPolicy {
    @Override
    public long total(long price, int quantity) {
        return Math.multiplyExact(price, quantity) * 9 / 10;
    }
}
~~~

Hai lớp đều cung cấp `PricingPolicy`. Constructor:

~~~java
public QuoteService(
        ProductCatalog catalog,
        PricingPolicy pricing
) { /* ... */ }
~~~

trở nên **mơ hồ** nếu không có quy tắc lựa chọn rõ ràng. Một số cách giải quyết:

- Dùng `@Primary` trên implementation muốn ưu tiên theo mặc định.
- Dùng `@Qualifier` tại injection point để chọn bean có qualifier phù hợp.
- Tạo cấu hình có điều kiện, ví dụ chỉ đăng ký một implementation cho mỗi profile.
- Nếu nghiệp vụ cần tất cả implementation, inject danh sách hoặc map các bean và có cơ chế chọn phù hợp ở tầng ứng dụng.

Ví dụ chọn rõ bằng tên bean:

~~~java
@Service
public class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    public QuoteService(
            ProductCatalog catalog,
            @Qualifier("standardPricingPolicy")
            PricingPolicy pricing
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
    }
}
~~~

Ở đây, cần import `org.springframework.beans.factory.annotation.Qualifier`. Khi component scan đăng ký `StandardPricingPolicy` với tên mặc định `standardPricingPolicy`, qualifier có thể chọn bean đó. Trong mã thực tế, có thể định nghĩa tên rõ ràng bằng annotation nếu cần tránh phụ thuộc quy ước tên tự suy ra.

`@Primary` có ích khi có một lựa chọn chuẩn toàn ứng dụng; `@Qualifier` có ích khi một người tiêu thụ cần lựa chọn cụ thể. Chọn bằng tên không phải lựa chọn duy nhất: Spring còn có cơ chế qualifier, priority và các quy tắc resolution khác; trong bài học này, nguyên tắc quan trọng là **đồ thị có nhiều ứng viên cần một quyết định rõ ràng**.

### Dependency tuỳ chọn và nhóm dependency

Một dependency có thể là bắt buộc hoặc có tính tùy chọn. Spring hỗ trợ những mẫu như `Optional<T>`, `ObjectProvider<T>` và tiêm `List<T>` hoặc `Map<String,T>` cho nhiều bean phù hợp.

~~~java
@Service
public class NotificationDispatcher {
    private final List<NotificationChannel> channels;

    public NotificationDispatcher(
            List<NotificationChannel> channels
    ) {
        this.channels = channels;
    }
}
~~~

Ví dụ giả định có nhiều bean triển khai `NotificationChannel`; container có thể cung cấp danh sách các bean đó. Khi thứ tự có ý nghĩa, phải thiết kế thứ tự rõ ràng bằng cơ chế Spring phù hợp, thay vì dựa vào thứ tự quan sát được một cách tình cờ.

Không nên biến mọi dependency thành optional chỉ để ứng dụng khởi động. Nếu một thành phần **không thể hoạt động hợp lệ** nếu thiếu dependency, constructor injection bắt buộc giúp phát hiện lỗi cấu hình sớm hơn.

## 8. IoC container quản lý nhiều hơn việc gọi constructor

Spring container có trách nhiệm phối hợp vòng đời bean. Một mô hình đơn giản hóa của quá trình khởi tạo là:

~~~text
Đọc cấu hình / bean definitions
              |
              v
Xác định bean nào cần tạo
              |
              v
Tìm constructor và resolve dependency
              |
              v
Tạo instance và tiêm dependency
              |
              v
Áp dụng xử lý, callback khởi tạo,
BeanPostProcessor và proxy (nếu có)
              |
              v
Bean sẵn sàng được sử dụng
              |
              v
      Xử lý nghiệp vụ
              |
              v
Đóng context và dọn tài nguyên
(những bean mà container quản lý
vòng đời hủy)
~~~

Đây là sơ đồ khái quát, không phải mô tả thứ tự đầy đủ của mọi hook nội bộ. Một số bean được tạo sớm, một số được khởi tạo lười; bean post-processor hoặc proxy có thể thay đổi đối tượng cuối cùng được đưa vào dependency.

### Khởi tạo và dọn dẹp

Ví dụ một bean cần mở và đóng một tài nguyên:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ManagedResource {
    @PostConstruct
    public void initialize() {
        // Chuẩn bị tài nguyên sau khi được inject
    }

    @PreDestroy
    public void close() {
        // Đóng tài nguyên khi bean được container hủy
    }
}
~~~

Trong các dòng Spring Boot sử dụng Jakarta EE, `@PostConstruct` và `@PreDestroy` nằm trong package `jakarta.annotation`. Ở những phiên bản Spring Boot cũ hơn sử dụng Java EE, namespace có thể khác.

Nếu bean do Spring quản lý có lifecycle phù hợp, container có thể gọi các callback đã đăng ký khi khởi tạo và đóng context. Nhưng dọn dẹp không được bảo đảm nếu tiến trình bị kill đột ngột hoặc máy chủ mất điện. Đặc biệt với prototype bean, Spring thường không tự quản lý đầy đủ quá trình hủy sau khi giao instance cho nơi sử dụng.

Không nên dùng constructor hoặc `@PostConstruct` để bắt đầu công việc nghiệp vụ kéo dài vô hạn. Những tác vụ nền, kết nối hoặc tiến trình cần vòng đời rõ ràng nên dùng cơ chế lifecycle thích hợp và có phương án dừng an toàn.

## 9. Bean scope thay đổi hình dạng đồ thị trong lúc chạy

Không phải mọi bean đều được tạo đúng một lần. **Scope** quy định phạm vi container quản lý và tái sử dụng instance.

| Scope | Ý nghĩa thường gặp | Lưu ý |
|---|---|---|
| `singleton` | Một instance cho một bean definition trong một Spring container | Mặc định; không đồng nghĩa một instance duy nhất trên toàn JVM |
| `prototype` | Container tạo một instance mới mỗi lần bean được yêu cầu theo cơ chế tương ứng | Quản lý dọn dẹp sau khi tạo không giống singleton |
| `request` | Một instance trong phạm vi HTTP request | Cần web-aware ApplicationContext |
| `session` | Một instance trong phạm vi HTTP session | Phụ thuộc ngữ cảnh web và session |
| `application` | Một instance trong phạm vi ServletContext | Có ngữ nghĩa riêng của ứng dụng web servlet |
| `websocket` | Một instance theo WebSocket session trong môi trường hỗ trợ | Chỉ dùng khi thực sự có ngữ cảnh phù hợp |

### Singleton là mặc định nhưng không tự bảo đảm thread safety

Một `@Service` singleton có thể đồng thời phục vụ rất nhiều HTTP request. Nếu bean giữ trạng thái mutable để xử lý từng request, nó dễ gặp race condition:

~~~java
@Service
public class UnsafeCounterService {
    private int count = 0;

    public int next() {
        return ++count;  // Không an toàn khi nhiều thread gọi đồng thời
    }
}
~~~

Việc Spring tạo một instance và quản lý dependency **không làm phép tăng `++count` trở thành atomic**. Với dữ liệu request, thường dùng biến cục bộ trong phương thức; nếu thật sự cần trạng thái chia sẻ, phải thiết kế đồng bộ hoặc dùng kiểu concurrency thích hợp.

### Prototype inject vào singleton có điều gì bất ngờ?

Giả sử:

~~~java
@Component
@Scope("prototype")
public class RequestToken {
    // ...
}
~~~

Và:

~~~java
@Service
public class TokenService {
    private final RequestToken token;

    public TokenService(RequestToken token) {
        this.token = token;
    }
}
~~~

`TokenService` là singleton và constructor của nó thường chỉ được gọi khi tạo singleton. Spring cung cấp **một instance prototype tại thời điểm lắp ghép**. Điều đó không có nghĩa mỗi lần `TokenService` sử dụng trường `token` sẽ nhận prototype mới.

Nếu cần lấy instance theo nhu cầu:

~~~java
@Service
public class TokenService {
    private final ObjectProvider<RequestToken> tokenProvider;

    public TokenService(
            ObjectProvider<RequestToken> tokenProvider
    ) {
        this.tokenProvider = tokenProvider;
    }

    public RequestToken newToken() {
        return tokenProvider.getObject();
    }
}
~~~

Cần import `org.springframework.beans.factory.ObjectProvider`. Provider cho phép yêu cầu bean tại thời điểm phương thức chạy. Đây là một sự khác biệt quan trọng giữa **đối tượng được inject lúc khởi tạo** và **yêu cầu một đối tượng mỗi lần cần dùng**.

### Bean request-scoped bên trong singleton

Một singleton không nên giữ trực tiếp một HTTP request hoặc dữ liệu request mà không hiểu scope. Spring hỗ trợ scoped proxy hoặc provider để giải quyết dependency có vòng đời ngắn hơn. Ví dụ, một proxy có thể được inject vào singleton và chuyển lời gọi đến bean thực sự thuộc request hiện tại.

Cách tiếp cận đó hữu ích, nhưng không thay thế việc phân tích trách nhiệm: dữ liệu request đơn giản thường có thể truyền qua tham số phương thức rõ ràng, tránh làm service phụ thuộc ngầm vào ngữ cảnh web.

## 10. Khi đồ thị có vòng phụ thuộc

Giả sử:

~~~text
OrderService
     |
     v
PaymentService
     |
     v
OrderService
~~~

Nếu cả hai bean đều yêu cầu nhau qua constructor:

~~~java
@Service
public class OrderService {
    public OrderService(PaymentService paymentService) {
        // ...
    }
}

@Service
public class PaymentService {
    public PaymentService(OrderService orderService) {
        // ...
    }
}
~~~

Để tạo `OrderService`, container cần `PaymentService`; nhưng để tạo `PaymentService` lại cần `OrderService` chưa tồn tại. Đây là **circular dependency**. Constructor cycle không thể giải quyết chỉ bằng cách thay thứ tự dòng khai báo.

Một số kiểu injection hoặc cơ chế trì hoãn có thể làm lỗi không xuất hiện ngay, nhưng vòng phụ thuộc vẫn thường là tín hiệu hai thành phần chưa có ranh giới trách nhiệm tốt.

Hướng thiết kế tốt hơn thường là:

- Xác định service nào điều phối use case và service nào chỉ cung cấp chức năng.
- Tách phần nghiệp vụ chung sang một thành phần có trách nhiệm riêng nếu thật sự cần.
- Làm rõ hướng gọi một chiều giữa các phần nghiệp vụ.
- Dùng sự kiện hoặc callback chỉ khi luồng nghiệp vụ thực sự phù hợp với kiểu phối hợp đó.

Ví dụ thay vì hai service gọi lẫn nhau:

~~~text
CheckoutCoordinator
    |             |
    v             v
OrderService   PaymentService
~~~

`CheckoutCoordinator` điều phối giao dịch thanh toán và đặt hàng theo quy tắc ứng dụng, trong khi hai service không cần inject ngược lại nhau. Với giao dịch phân tán, còn cần thiết kế tính nhất quán; ví dụ này chỉ minh họa cách làm rõ hướng phụ thuộc.

Không nên xem `@Lazy` hay bật một cấu hình cho phép circular references là cách sửa mặc định. Chúng có thể che đi vấn đề thiết kế và khiến hành vi khó dự đoán hơn.

## 11. Bean conditional khiến đồ thị thay đổi theo môi trường

Đồ thị đối tượng không nhất thiết giống nhau giữa tất cả lần chạy cùng mã nguồn. Spring Boot sử dụng cấu hình, classpath và điều kiện để quyết định tạo bean.

### Lựa chọn bằng profile

Ví dụ có hai implementation `ProductCatalog`:

~~~java
@Repository
@Profile("dev")
public class InMemoryProductCatalog implements ProductCatalog {
    // ...
}

@Repository
@Profile("prod")
public class DatabaseProductCatalog implements ProductCatalog {
    // ...
}
~~~

Đoạn code minh họa hai lựa chọn cấu hình; trong ứng dụng thật cần triển khai đầy đủ các phương thức interface và dependency của database catalog. Khi profile `dev` hoạt động, Spring có thể đăng ký bean in-memory; khi profile `prod` hoạt động, Spring có thể đăng ký bean database.

Nếu không có profile phù hợp, `QuoteService` có thể thiếu `ProductCatalog` và thất bại lúc khởi tạo. Nếu nhiều profile cùng hoạt động dẫn tới hai implementation, container có thể gặp ambiguity trừ khi có cách chọn rõ ràng.

Spring profile là **điều kiện đăng ký bean/configuration**, không tự tạo database, mạng hoặc secret tương ứng.

### Lựa chọn bằng property

Một bean có thể chỉ được đăng ký nếu cấu hình cho phép:

~~~java
@Configuration
public class PromotionConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "shop.promotion",
            name = "enabled",
            havingValue = "true"
    )
    public PromotionEngine promotionEngine() {
        return new PromotionEngine();
    }
}
~~~

Trong đoạn này, `PromotionEngine` là kiểu ví dụ cần được định nghĩa bởi ứng dụng. `@ConditionalOnProperty` là annotation thuộc Spring Boot. Nếu property không thỏa điều kiện, bean sẽ không được khai báo bởi phương thức này.

Nếu một service **bắt buộc** inject `PromotionEngine` nhưng tính năng bị tắt, cần thiết kế lại dependency: ví dụ dùng interface với implementation “không khuyến mãi”, một provider optional hoặc chỉ tạo service khi tính năng bật. Conditional annotation không tự biến dependency bắt buộc thành optional.

### Auto-configuration là việc tạo đồ thị có điều kiện ở quy mô framework

Spring Boot auto-configuration thường dựa vào những điều kiện như:

- Một class hoặc thư viện cụ thể có trên classpath: `@ConditionalOnClass`.
- Một bean chưa được ứng dụng định nghĩa: `@ConditionalOnMissingBean`.
- Một property có giá trị phù hợp: `@ConditionalOnProperty`.
- Loại ứng dụng hoặc công nghệ web đang được sử dụng.

Nhờ vậy, khi ứng dụng có web starter, framework có thể cấu hình nhiều thành phần HTTP phù hợp mà không cần tạo thủ công mọi bean. Khi ứng dụng tự cung cấp một bean phù hợp, một số cấu hình mặc định có thể **nhường chỗ** cho lựa chọn đó.

Điều quan trọng là đọc được nguyên nhân **bean nào có mặt hoặc không có mặt** trong ApplicationContext. “Spring Boot magic” thực chất là một hệ thống luật đăng ký và kết nối object graph dựa trên metadata và điều kiện.

## 12. Không phải mọi đối tượng có annotation đều là bean

Một hiểu lầm thường gặp là chỉ cần thêm `@Autowired` hoặc `@Service` vào mã là dependency sẽ tự hoạt động ở mọi nơi.

Xét ví dụ:

~~~java
@Service
public class ReportService {
    private final ProductCatalog catalog;

    public ReportService(ProductCatalog catalog) {
        this.catalog = catalog;
    }
}
~~~

Nếu bạn tạo instance thủ công bằng:

~~~java
ReportService reportService = new ReportService(null);
~~~

đối tượng đó không nhận dependency từ container chỉ vì lớp có `@Service`. Đây là đối tượng được tạo bởi mã Java thông thường, không phải instance do Spring giải quyết constructor. Nó sẽ chứa `null` và có thể lỗi khi được sử dụng.

Tương tự:

~~~java
public class ImportJob {
    @Autowired
    private ReportService reportService;
}

// Ở nơi nào đó:
ImportJob job = new ImportJob();
~~~

`job` được tạo bằng `new`, không tự được container inject `reportService`. Chỉ thêm annotation trên field không đủ để kích hoạt cơ chế wiring. Cần để Spring quản lý `ImportJob` hoặc truyền `ReportService` rõ ràng từ bên ngoài.

**Quy tắc hữu ích:** đối tượng có annotation chỉ là **ứng viên** được container quản lý; việc thực sự trở thành bean còn phụ thuộc vào quá trình đăng ký và khởi tạo của context.

## 13. Proxy: đối tượng mà consumer nhận có thể không phải instance thô

Đồ thị do Spring cung cấp có thể chứa **proxy**: một đối tượng trung gian chuyển lời gọi tới đối tượng đích, đồng thời áp dụng hành vi bổ sung như transaction, method security, caching hoặc AOP tùy cấu hình.

Ví dụ:

~~~java
@Service
public class OrderService {
    @Transactional
    public void placeOrder() {
        // Thao tác thuộc transaction
    }
}
~~~

Với transaction infrastructure được cấu hình thích hợp, Spring có thể đưa một proxy của `OrderService` tới bean khác. Khi bean khác gọi phương thức qua proxy, interceptor có thể mở hoặc tham gia transaction trước khi gọi vào mã nghiệp vụ.

~~~text
OrderController
      |
      v
 OrderService proxy
      |
      | transaction advice
      v
 OrderService target
      |
      v
  Repository
~~~

Điều này giải thích vì sao một lời gọi trực tiếp từ phương thức này sang phương thức khác **trên cùng instance** có thể không đi qua proxy trong mô hình Spring AOP mặc định:

~~~java
@Service
public class OrderService {
    public void submit() {
        saveOrder(); // self-invocation
    }

    @Transactional
    public void saveOrder() {
        // ...
    }
}
~~~

Trong cơ chế proxy mặc định, lời gọi `saveOrder()` từ chính đối tượng target thường bỏ qua interceptor `@Transactional`, dù annotation có mặt. Khi thiết kế transaction, nên đặt ranh giới ở phương thức được gọi qua bean/proxy phù hợp, hoặc dùng cách quản lý transaction rõ ràng hơn.

Không phải bean nào cũng có proxy; việc tạo proxy phụ thuộc cấu hình, annotation, loại proxy và những điều kiện tương ứng. Đối với người học IoC, điểm cốt lõi là **đối tượng được inject có thể là thành phần đã được container xử lý**, không đơn thuần là kết quả của `new`.

## 14. Constructor injection, setter injection và field injection

Spring hỗ trợ nhiều cách tiêm dependency, nhưng mỗi cách có ý nghĩa thiết kế khác nhau.

### Constructor injection

~~~java
@Service
public class EmailService {
    private final MailGateway gateway;

    public EmailService(MailGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Đây thường là lựa chọn nên ưu tiên cho dependency **bắt buộc**:

- Thể hiện rõ đối tượng cần gì để được tạo hợp lệ.
- Có thể giữ trường `final` và tránh trạng thái thiếu dependency sau constructor.
- Dễ tạo object trong unit test bằng fake/stub mà không cần khởi động Spring context.
- Khi số constructor parameter tăng quá nhiều, đó có thể là tín hiệu cần xem lại trách nhiệm của class.

### Setter injection

~~~java
@Component
public class ReportFormatter {
    private LocaleProvider localeProvider;

    @Autowired
    public void setLocaleProvider(LocaleProvider localeProvider) {
        this.localeProvider = localeProvider;
    }
}
~~~

Kiểu này phù hợp khi dependency cần được thay thế hoặc có tính tùy chọn trong thiết kế cụ thể, nhưng cũng cho phép object tồn tại một giai đoạn chưa được gán đủ trạng thái. Nếu dùng setter cho dependency bắt buộc, phải hiểu cơ chế Spring bảo đảm injection trước khi bean được sử dụng như thế nào.

### Field injection

~~~java
@Service
public class LegacyOrderService {
    @Autowired
    private OrderRepository repository;
}
~~~

Cú pháp ngắn nhưng che dependency khỏi constructor, gây khó cho việc tạo object ngoài container và không thuận tiện với trường `final`. Vì vậy, trong mã ứng dụng mới thường nên ưu tiên constructor injection.

Ba cách trên không làm IoC thay đổi bản chất. Chúng chỉ là những **điểm tiếp nhận dependency** khác nhau để container lắp vào object graph.

## 15. IoC container không thay thế thiết kế tốt

Có Spring ở giữa không có nghĩa mọi quan hệ dependency đều hợp lý.

Ví dụ một controller inject trực tiếp hàng loạt repository:

~~~text
CheckoutController
   ├── OrderRepository
   ├── ProductRepository
   ├── CustomerRepository
   ├── PaymentRepository
   └── InventoryRepository
~~~

Container có thể lắp ghép được đồ thị này, nhưng controller đang gánh quá nhiều trách nhiệm. Một cấu trúc dễ duy trì hơn có thể là:

~~~text
CheckoutController
        |
        v
CheckoutUseCase
   |         |
   v         v
OrdersApi  InventoryApi
   |         |
   v         v
repository  repository
~~~

Ở đây, controller biết use case; use case điều phối các hợp đồng nghiệp vụ; từng miền sở hữu dữ liệu của mình. Spring giúp cung cấp đối tượng, còn **đường phụ thuộc** vẫn là quyết định kiến trúc của lập trình viên.

### DI và Service Locator

Một mẫu có thể làm mờ dependency là gọi container từ bên trong logic nghiệp vụ:

~~~java
public class QuoteService {
    private final ApplicationContext context;

    public QuoteService(ApplicationContext context) {
        this.context = context;
    }

    public long quote(...) {
        PricingPolicy pricing =
                context.getBean(PricingPolicy.class);
        // ...
    }
}
~~~

Đây là một dạng **service locator**: class tự đi tìm dependency khi cần. Nó vẫn dùng container, nhưng những thứ class cần bị che khỏi constructor, khiến việc kiểm thử và thay thế khó thấy hơn. Đối với dependency ổn định và bắt buộc, inject trực tiếp interface thường tốt hơn.

Truy cập container bằng API không phải lúc nào cũng sai; mã infrastructure, plugin system hoặc cơ chế cần chọn bean động có thể có lý do. Nhưng đó nên là lựa chọn có mục tiêu, không phải cách mặc định của mã nghiệp vụ.

## 16. Chẩn đoán lỗi khi Spring không xây dựng được đồ thị

Nếu ApplicationContext không thể tạo đầy đủ các dependency bắt buộc, ứng dụng thường thất bại lúc startup. Thông báo lỗi và chuỗi `Caused by` giúp lần theo **điểm bị đứt trong đồ thị**.

| Dấu hiệu | Cách hiểu trong đồ thị | Điều cần xem |
|---|---|---|
| `NoSuchBeanDefinitionException` | Một điểm injection không tìm được bean phù hợp | Annotation, component scan, `@Bean`, profile, conditional |
| `NoUniqueBeanDefinitionException` | Có nhiều ứng viên cho cùng dependency | `@Primary`, `@Qualifier`, tên bean, định nghĩa trùng |
| `UnsatisfiedDependencyException` | Không thể thỏa dependency của bean đang tạo | Đọc cause để biết thiếu hoặc lỗi ở dependency nào |
| `BeanCreationException` | Quá trình khởi tạo bean thất bại | Constructor, factory method, cấu hình, callback, tài nguyên ngoài |
| `BeanCurrentlyInCreationException` | Có thể liên quan đến vòng phụ thuộc hoặc vòng tạo bean | Đồ thị giữa các constructor, proxy, initialization |
| `NullPointerException` ở một field `@Autowired` trong đối tượng tạo thủ công | Đối tượng có thể không được container quản lý | Chỗ gọi `new` và cách đăng ký bean |
| Chạy được ở `dev` nhưng lỗi ở `prod` | Đồ thị khác nhau theo cấu hình | Profile, property, dependency có điều kiện, hạ tầng |

### Tìm gốc lỗi qua đường dependency

Giả sử log có dạng khái niệm:

~~~text
Error creating bean with name 'quoteController'
  -> Unsatisfied dependency 'quoteService'
      -> Unsatisfied dependency 'productCatalog'
          -> No qualifying bean of type 'ProductCatalog'
~~~

Thông điệp hữu ích nhất thường nằm ở **dependency sâu nhất chưa thỏa**, ở đây là `ProductCatalog`. Sửa tên controller không giải quyết được việc container không có catalog bean.

Các bước định hướng:

1. Xác định bean nào đang tạo và dependency nào không được đáp ứng.
2. Kiểm tra có implementation hay phương thức `@Bean` đăng ký kiểu cần thiết không.
3. Kiểm tra package nằm trong vùng component scan không.
4. Kiểm tra profile/conditional có đang loại bean đó không.
5. Kiểm tra runtime classpath có thiếu dependency hoặc auto-configuration cần thiết không.
6. Nếu lỗi là nhiều bean, xác định cách lựa chọn rõ ràng thay vì xóa ngẫu nhiên một implementation.

Ví dụ, nếu lớp `ShopApplication` nằm ở `com.example.shop.web` còn `ProductCatalog` ở `com.example.shop.catalog`, component scan mặc định từ package `web` có thể không đi qua `catalog`. Đặt lớp khởi động tại package gốc phù hợp thường giúp tránh vấn đề này.

Trong các trường hợp khó, Spring Boot có báo cáo đánh giá điều kiện auto-configuration và các cơ chế quan sát context. Có thể dùng logging khởi động hoặc công cụ quản trị phù hợp để tìm lý do cấu hình được áp dụng hay bỏ qua; thông tin cấu hình nhạy cảm không nên được công khai qua endpoint quản trị.

## 17. Kiểm thử thuận lợi hơn khi dependency được khai báo rõ

Một lợi ích thực tế của DI là có thể thử quy tắc của service mà không khởi động ứng dụng đầy đủ.

Ví dụ kiểm thử logic tính báo giá, với fake catalog do test cung cấp:

~~~java
ProductCatalog fakeCatalog = sku ->
        Optional.of(new Product(sku, 50_000L, 3));

PricingPolicy pricing = new StandardPricingPolicy();
QuoteService service = new QuoteService(fakeCatalog, pricing);

Quote quote = service.quote("TEST-BOOK", 2);

// quote.total() dự kiến là 100_000
~~~

Đoạn này dùng interface như seam để cung cấp dữ liệu thử. Không cần Spring ApplicationContext vì `QuoteService` nhận dependency qua constructor Java bình thường. Trong bài test thật, có thể dùng JUnit và assertion tương ứng.

Khi cần xác nhận component scan, auto-configuration, MVC mapping hoặc bean wiring, lúc đó mới nên dùng Spring test context, ví dụ `@SpringBootTest` hay test slice phù hợp. Hai loại kiểm thử trả lời những câu hỏi khác nhau:

| Loại kiểm thử | Mục tiêu | Có cần container thật không? |
|---|---|---|
| Unit test service bằng fake/stub | Quy tắc nghiệp vụ trong service | Thường không |
| Web slice test | Mapping, validation HTTP, controller behavior | Có context giới hạn |
| Integration test | Tương tác bean, configuration và hạ tầng | Thường cần context phù hợp |
| Kiểm thử khởi động | Đồ thị bean có thể lắp dưới cấu hình cụ thể không | Có |

Đồ thị dependency gọn và hợp đồng rõ giúp tập trung kiểm thử theo đúng trách nhiệm. Nhưng DI không tự đảm bảo test tốt nếu service vẫn phụ thuộc vào trạng thái toàn cục, thời gian hệ thống không kiểm soát hoặc các API ẩn.

## 18. Liên hệ IoC với cấu hình và dependency trong Spring Boot

Điểm đặc trưng của Spring Boot là đồ thị bean được xây dựng từ sự kết hợp của:

~~~text
Mã nguồn Java                 Dependency / classpath
   |                                  |
   | @Component, @Configuration       | Starter, thư viện, driver
   v                                  v
       Bean definitions và điều kiện
                    ^
                    |
            Profile / properties
                    |
                    v
              IoC container
                    |
                    v
       Object graph của ứng dụng
                    |
                    v
      Controller, service, repository
                    |
                    v
         Hành vi khi ứng dụng chạy
~~~

Ví dụ khi thêm starter web, nhiều class liên quan HTTP trở nên khả dụng và auto-configuration có thể đăng ký bean tương ứng. Khi đặt property thay đổi, một số bean hoặc giá trị cấu hình có thể khác. Khi profile đổi, implementation có thể đổi. Spring container kết hợp tất cả để tạo đồ thị cuối cùng.

Do đó, việc đọc lỗi dependency injection không nên chỉ hỏi “annotation có đúng không?” mà còn xem **đồ thị mong muốn** và **đồ thị mà context thực sự có khả năng xây dựng trong môi trường này**.

## 19. Bài tập tư duy: thiết kế đồ thị cho ứng dụng đặt lịch

Giả sử xây dựng ứng dụng Spring Boot đặt lịch khám với ba yêu cầu:

1. API nhận lịch hẹn từ người dùng.
2. Service kiểm tra slot còn trống và tạo lịch hẹn.
3. Có thể gửi thông báo qua email; trong môi trường local dùng giả lập thay vì gửi email thật.

Một thiết kế ban đầu:

~~~text
AppointmentController
        |
        v
   BookingService
     |       |
     v       v
SlotCatalog  NotificationGateway
     |              |
     v              +-- LocalNotificationGateway
DatabaseSlotCatalog +-- EmailNotificationGateway
~~~

Hãy xác định:

- Những lớp nào là bean cần container quản lý, những object nào chỉ là dữ liệu của một request?
- `BookingService` nên inject interface nào và constructor cần những tham số gì?
- Làm thế nào đảm bảo chỉ một `NotificationGateway` được chọn cho từng môi trường?
- Nếu `DatabaseSlotCatalog` cần `DataSource`, ai sẽ cung cấp dependency đó?
- Nếu container báo có hai bean `NotificationGateway`, nguyên nhân mơ hồ xuất hiện tại cạnh nào?
- Nếu chỉ một request cần giữ dữ liệu tạm của lịch hẹn, có nên lưu nó vào field mutable của singleton service không?
- Khi viết unit test cho quy tắc không cho đặt slot đã đầy, có thể thay catalog thật bằng fake như thế nào?

Một phương án đơn giản là đăng ký hai implementation `NotificationGateway` với các profile hoặc điều kiện rõ ràng, để `BookingService` chỉ phụ thuộc vào interface, còn `AppointmentController` chỉ biết use case tạo lịch hẹn. Dữ liệu lịch hẹn cụ thể là các object thông thường đi qua tham số, không phải tất cả đều trở thành bean.

## 20. Các nguyên tắc nên giữ khi dùng IoC container

1. **Để class khai báo dependency, còn việc lắp ghép đặt ở container hoặc composition root.** Constructor injection là lựa chọn rõ ràng cho dependency bắt buộc.
2. **Phụ thuộc vào hợp đồng có ý nghĩa, không gắn trực tiếp implementation khi cần thay đổi.** Interface giúp thay đổi implementation và kiểm thử dễ dàng hơn, nhưng không cần tạo interface cho mọi class chỉ để thỏa một quy tắc hình thức.
3. **Biết bean nào thật sự được quản lý.** `@Component` trong package ngoài vùng scan hoặc một object được tạo thủ công sẽ không tự nhận đầy đủ cơ chế container.
4. **Hiểu scope và trạng thái dùng chung.** Singleton không tự bảo đảm thread safety; prototype không tự tạo instance mới mỗi lần singleton gọi phương thức.
5. **Giữ đồ thị có hướng phụ thuộc rõ ràng.** Vòng phụ thuộc và service ôm quá nhiều trách nhiệm thường cần cải thiện thiết kế trước khi dùng workaround.
6. **Phân biệt bean thật và proxy.** Transaction, caching, security và scoped proxy có thể tác động vào lời gọi qua container.
7. **Đọc lỗi khởi động như lỗi lắp ghép đồ thị.** Tìm dependency sâu nhất bị thiếu, mơ hồ hoặc không thể khởi tạo; kiểm tra cả classpath, cấu hình và profile.
8. **Đừng đưa mọi object vào container.** Spring quản lý những cộng tác viên và tài nguyên cấp ứng dụng phù hợp; các object dữ liệu tạo theo từng request hoặc mỗi phép tính vẫn có thể là Java object thuần.

## Kết luận

**IoC giải quyết bài toán ai điều khiển việc tạo và kết nối các thành phần; DI là cách trao các dependency cho thành phần mà không buộc nó tự tạo chúng.** Trong Spring Boot, ApplicationContext đọc các định nghĩa bean và điều kiện cấu hình, giải quyết những quan hệ phụ thuộc, khởi tạo bean theo scope, áp dụng các bước lifecycle cần thiết và cung cấp object graph mà ứng dụng sử dụng.

Khi hiểu đồ thị đó, ta hiểu vì sao Spring có thể inject một interface, vì sao thiếu bean làm ứng dụng không khởi động, vì sao hai implementation gây ambiguity, vì sao singleton có rủi ro trạng thái dùng chung và vì sao việc tạo object bằng `new` ở ngoài container khác với nhận một bean Spring. Từ đây, IoC container không còn là cơ chế khó hiểu: nó là một công cụ tổ chức việc **lắp ghép, cấu hình và quản lý các đối tượng cộng tác** để mã nghiệp vụ tập trung vào công việc thực sự của mình.
