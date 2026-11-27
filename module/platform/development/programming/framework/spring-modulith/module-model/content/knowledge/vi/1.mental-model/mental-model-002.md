# Application module là ranh giới chức năng hay chỉ là một thư mục?

Khi nhìn vào một ứng dụng Spring Boot, ta thường thấy các thư mục hoặc package như `order`, `customer`, `inventory`. Chia code theo cách đó giúp dự án dễ đọc hơn, nhưng chưa đủ để kết luận ứng dụng đã có kiến trúc mô-đun. Một ranh giới mô-đun chỉ có ý nghĩa khi ta xác định được phần nào là API, phần nào là triển khai nội bộ và mô-đun nào được phép phụ thuộc vào mô-đun nào.

Spring Modulith biến cấu trúc package thành một mô hình mô-đun có thể kiểm tra. Vì vậy, câu trả lời là: **application module là một ranh giới chức năng được mô tả bằng cấu trúc package và quy tắc phụ thuộc; thư mục chỉ là cách tổ chức file thường đi kèm với cấu trúc đó.**

## 1. Phân biệt thư mục, Java package và application module

Ba khái niệm này thường trùng nhau trong cách tổ chức dự án, nhưng chúng không có cùng vai trò.

| Khái niệm | Nó mô tả điều gì? | Ví dụ |
| --- | --- | --- |
| Thư mục | Vị trí lưu file trên hệ thống tệp | `src/main/java/com/acme/shop/order/` |
| Java package | Không gian tên của các lớp Java, được khai báo bằng câu lệnh `package` | `com.acme.shop.order` |
| Application module | Một đơn vị chức năng có API, phần triển khai nội bộ và các phụ thuộc được xác định | Mô-đun `order` quản lý vòng đời đơn hàng |

Java package giúp tránh xung đột tên và kiểm soát một phần khả năng truy cập bằng `public`, `protected` và package-private. Tuy nhiên, Java không tự hiểu rằng `order` là một năng lực nghiệp vụ, cũng không tự ngăn mọi lớp ở package khác gọi trực tiếp vào phần triển khai của `order`.

Application module bổ sung góc nhìn kiến trúc. Nó trả lời những câu hỏi mà tên thư mục không trả lời được:

- Mô-đun chịu trách nhiệm cho nghiệp vụ nào?
- Thành phần nào được phép sử dụng từ bên ngoài?
- Những package nào chỉ phục vụ triển khai bên trong mô-đun?
- Mô-đun này được phép phụ thuộc vào mô-đun nào?
- Làm thế nào để phát hiện một thay đổi vô tình phá vỡ các ranh giới đó?

Nếu chỉ tạo thư mục `order` rồi đặt tất cả lớp liên quan vào đó, ta mới có cách sắp xếp code. Nếu xác định API, đóng gói phần nội bộ và kiểm tra các phụ thuộc, ta mới có một ranh giới mô-đun có thể duy trì.

## 2. Application module đại diện cho một năng lực nghiệp vụ

Trong Spring Modulith, application module là một đơn vị chức năng trong ứng dụng Spring Boot. Một mô-đun thường có ba phần:

1. **API được cung cấp:** các Spring bean hoặc application event mà mô-đun cho phép mô-đun khác sử dụng.
2. **Triển khai nội bộ:** repository, adapter, quy tắc xử lý và các thành phần hỗ trợ không được xem là API công khai.
3. **API được yêu cầu:** các dịch vụ, sự kiện hoặc cấu hình mà mô-đun cần dùng từ những mô-đun khác.

Ví dụ, mô-đun `order` chịu trách nhiệm tạo đơn hàng và theo dõi trạng thái đơn. Nó có thể cung cấp `OrderManagement` làm điểm vào nghiệp vụ, giữ `OrderRepository` và các chính sách tính tổng tiền bên trong, đồng thời sử dụng API của mô-đun `inventory` để kiểm tra khả năng đáp ứng hàng hóa.

Ranh giới này giúp người đọc hiểu trách nhiệm của từng phần. Khi muốn thay đổi cách lưu đơn hàng, ta có thể làm việc bên trong `order` mà không buộc `customer` hoặc `shipping` phải biết chi tiết repository. Khi một mô-đun khác cần tạo đơn, nó gọi API mà `order` công bố.

Một application module không mặc nhiên là một microservice. Các mô-đun vẫn có thể chạy trong cùng tiến trình, dùng chung một ứng dụng Spring Boot và được triển khai như một đơn vị. Spring Modulith giúp ứng dụng nguyên khối có cấu trúc mô-đun rõ ràng; việc tách mô-đun thành dịch vụ độc lập là một quyết định triển khai khác.

## 3. Spring Modulith tìm mô-đun từ package như thế nào?

Spring Modulith xây dựng mô hình mô-đun từ package Java nằm bên dưới package chứa lớp ứng dụng Spring Boot. Với chiến lược phát hiện mặc định:

- Package chứa lớp `@SpringBootApplication` là package gốc của ứng dụng.
- Mỗi package con trực tiếp của package gốc được xem là một application module.
- Các package con sâu hơn thuộc về mô-đun đó và mặc định được xem là phần nội bộ.

Giả sử lớp khởi chạy nằm trong `com.acme.shop`:

```text
src/main/java
└── com/acme/shop
    ├── ShopApplication.java
    ├── order
    │   ├── OrderManagement.java
    │   ├── OrderId.java
    │   ├── internal
    │   │   ├── OrderRepository.java
    │   │   └── OrderPolicy.java
    │   └── events
    │       └── OrderPlaced.java
    ├── inventory
    │   ├── InventoryManagement.java
    │   └── internal
    │       └── StockRepository.java
    └── customer
        └── CustomerManagement.java
```

Trong cấu trúc mặc định này, `order`, `inventory` và `customer` là ba application module. `order.internal` và `order.events` vẫn thuộc mô-đun `order`; việc tạo package con không tự động tạo ra một mô-đun mới.

Điểm cần nhớ là Spring Modulith phân tích **Java package**, không dựa đơn thuần vào tên thư mục trên ổ đĩa. Trong dự án Java thông thường, đường dẫn thư mục phản ánh tên package, nhưng yếu tố quyết định đối với mô hình mô-đun là khai báo package và vị trí của nó trong cây package.

### Package gốc của mô-đun là API mặc định

Với mô-đun dạng đóng mặc định, package gốc của mô-đun là package API. Các package con như `order.internal` được xem là nội bộ và mô-đun khác không được tham chiếu trực tiếp đến kiểu nằm trong đó.

Ví dụ, `OrderManagement` nằm trong package gốc:

```java
package com.acme.shop.order;

public class OrderManagement {

    public OrderId placeOrder(CreateOrder command) {
        // Điều phối quy trình tạo đơn hàng.
        // Chi tiết lưu trữ và chính sách nằm bên trong mô-đun.
        return new OrderId("ORD-1001");
    }
}
```

Một mô-đun khác có thể phụ thuộc vào `OrderManagement` vì đây là kiểu thuộc package API của `order`.

Ngược lại, `OrderRepository` nằm trong `com.acme.shop.order.internal`. Dù lớp này phải khai báo `public` để các lớp ở package con khác của chính mô-đun `order` sử dụng được, mô-đun bên ngoài vẫn không nên truy cập nó.

Đây là khác biệt quan trọng giữa khả năng truy cập của Java và ranh giới kiến trúc. Java cho phép một lớp `public` ở package con được import từ package khác. Spring Modulith có thể phát hiện việc một mô-đun khác vượt qua ranh giới đó khi chạy kiểm tra kiến trúc.

## 4. Named Interface: công bố thêm một phần API có chủ đích

Đôi khi API của mô-đun không chỉ nằm trong package gốc. Chẳng hạn, `order` muốn cung cấp các kiểu sự kiện trong `order.events` để mô-đun khác đăng ký xử lý. Nếu để package này ở trạng thái mặc định, nó vẫn là package nội bộ.

Ta có thể công bố package đó bằng `@NamedInterface` trong `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Sau khai báo này, `order.events` trở thành một named interface có tên `events`. Các mô-đun khác có thể tham chiếu những kiểu được công bố trong package đó. Ví dụ, `shipping` có thể sử dụng `OrderPlaced` để bắt đầu quy trình giao hàng khi đơn hàng được tạo.

Named Interface có hai lợi ích:

- **Công bố có chọn lọc:** mô-đun có thể mở một package phục vụ tích hợp mà không phải mở toàn bộ phần triển khai nội bộ.
- **Đặt tên cho hợp đồng:** tên như `events`, `spi` hoặc `api` thể hiện mục đích của phần API được công bố.

Không nên đánh dấu mọi package con là named interface chỉ để làm cho lỗi kiểm tra biến mất. Mỗi named interface nên có người dùng và mục đích rõ ràng. Nếu mô-đun khác cần truy cập một lớp nội bộ, hãy xem lại hợp đồng giữa hai mô-đun trước khi công bố package đó.

## 5. Quy tắc phụ thuộc làm cho ranh giới có ý nghĩa

Một mô-đun có thể được tổ chức đẹp nhưng vẫn phụ thuộc chằng chịt vào các mô-đun khác. Khi đó, việc chia package chưa tạo ra kiến trúc dễ thay đổi.

Spring Modulith hỗ trợ kiểm tra các quan hệ phụ thuộc. Có ba quy tắc cơ bản cần hiểu:

### Không tạo chu trình giữa các mô-đun

Giả sử `order` phụ thuộc vào `inventory`, `inventory` lại phụ thuộc vào `shipping`, còn `shipping` gọi ngược về `order`. Ta có một chu trình. Thay đổi trong một mô-đun có thể kéo theo nhiều mô-đun khác và làm cho việc kiểm thử hoặc tái cấu trúc khó hơn.

Mục tiêu là để đồ thị phụ thuộc giữa các mô-đun không có chu trình. Nếu hai phần cần trao đổi thông tin, hãy xem xét chuyển một hợp đồng nhỏ sang API phù hợp hoặc dùng application event để giảm liên kết trực tiếp.

### Chỉ truy cập API của mô-đun khác

Một mô-đun chỉ nên tham chiếu package gốc hoặc named interface được công bố của mô-đun khác. Ví dụ:

```java
// Hợp lệ về mặt ranh giới: OrderManagement nằm trong package API.
import com.acme.shop.order.OrderManagement;

// Không hợp lệ về mặt ranh giới: đây là package triển khai nội bộ.
import com.acme.shop.order.internal.OrderRepository;
```

Ví dụ thứ hai có thể vẫn biên dịch nếu lớp là `public`, nhưng vi phạm quy tắc kiến trúc của mô-đun đóng mặc định. Vì vậy, việc biên dịch thành công chưa chứng minh rằng các mô-đun đang phụ thuộc đúng cách.

### Khai báo danh sách phụ thuộc được phép

Nếu muốn giới hạn rõ hơn những mô-đun mà `order` được phép sử dụng, ta khai báo `allowedDependencies` trên package của `order`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Khai báo này cho biết code trong `order` chỉ được phụ thuộc vào mô-đun `inventory` trong số các application module. Khi cần phụ thuộc vào named interface cụ thể, có thể dùng tên mô-đun và tên interface nối bằng `::`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory :: events"
)
package com.acme.shop.order;
```

Khi đã khai báo danh sách cho phép, một phụ thuộc đến mô-đun không có trong danh sách sẽ bị xem là vi phạm. Nếu không khai báo `allowedDependencies`, ứng dụng vẫn có thể kiểm tra chu trình và việc truy cập package nội bộ; danh sách cho phép là lớp kiểm soát bổ sung.

## 6. Đưa kiểm tra kiến trúc vào test

Ranh giới mô-đun chỉ hữu ích lâu dài khi nhóm phát triển có thể kiểm tra nó sau mỗi thay đổi. `ApplicationModules` tạo mô hình từ lớp ứng dụng, còn `verify()` thực thi các quy tắc kiến trúc.

Có thể đặt một bài kiểm tra đơn giản trong test source set:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi chạy, Spring Modulith kiểm tra những điều như:

- Các mô-đun có tạo thành chu trình phụ thuộc hay không.
- Mô-đun có truy cập package nội bộ của mô-đun khác hay không.
- Các phụ thuộc có tuân thủ `allowedDependencies` đã khai báo hay không.

Nếu phát hiện vi phạm, `verify()` ném exception và bài test thất bại. Đặt kiểm tra này trong pipeline CI giúp nhóm phát hiện việc phá vỡ ranh giới ngay trong quá trình phát triển, thay vì đợi đến khi một thay đổi lớn trở nên khó truy vết.

Kiểm tra này là kiểm tra cấu trúc và phụ thuộc dựa trên code đã biên dịch; nó không biến các mô-đun thành tiến trình riêng, cũng không phải cơ chế bảo mật runtime. Nhóm vẫn cần thiết kế API tốt và giữ bài kiểm tra kiến trúc trong quy trình build.

## 7. Một số nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Có thư mục `order` nghĩa là đã có module `order`. | Thư mục mới chỉ là nơi lưu file. Spring Modulith nhận diện module từ cấu trúc package và chiến lược phát hiện module. |
| Mọi package con của `order` đều là module riêng. | Theo mặc định, package con thuộc module `order` và là nội bộ. Có thể khai báo nested application module khi thực sự cần một ranh giới lồng nhau. |
| Lớp `public` có thể được mọi module sử dụng. | Java cho phép import lớp `public`, nhưng Spring Modulith vẫn có thể đánh dấu việc truy cập package nội bộ là vi phạm kiến trúc. |
| Named Interface là cách đặt tên package cho đẹp. | Named Interface là hợp đồng API được công bố rõ ràng cho mô-đun khác. |
| Application module đồng nghĩa với microservice. | Module là ranh giới logic trong ứng dụng. Nó vẫn có thể chạy cùng tiến trình và được triển khai cùng ứng dụng Spring Boot. |
| Chỉ cần chạy ứng dụng thành công là đủ. | Ứng dụng có thể chạy dù các module đang phụ thuộc sai ranh giới. Cần chạy `ApplicationModules.verify()` để kiểm tra cấu trúc. |

Spring Modulith cũng hỗ trợ các cấu trúc nâng cao như nested application module, open module và chiến lược phát hiện module tùy chỉnh. Đây là các lựa chọn dành cho nhu cầu cụ thể. Với một ứng dụng mới, nên bắt đầu bằng mô hình package mặc định và chỉ mở rộng khi có lý do kiến trúc rõ ràng. Đặc biệt, `OPEN` cho phép truy cập rộng hơn vào phần nội bộ, nên thường phù hợp với quá trình chuyển đổi hệ thống cũ hơn là mục tiêu đóng gói chặt chẽ của một thiết kế mới.

## 8. Cách quyết định một package có nên trở thành module

Trước khi tạo thêm một application module, hãy tự hỏi:

1. Package này có đại diện cho một năng lực nghiệp vụ hoặc trách nhiệm tương đối độc lập không?
2. Có thể mô tả API mà phần còn lại của ứng dụng cần sử dụng không?
3. Có phần triển khai nào cần được giữ kín bên trong không?
4. Những mô-đun nào thực sự cần phụ thuộc vào nó?
5. Các phụ thuộc có thể đi theo một chiều và không tạo chu trình không?

Nếu một package chỉ gom vài lớp kỹ thuật dùng chung mà không có trách nhiệm nghiệp vụ rõ ràng, việc biến nó thành module có thể làm kiến trúc phức tạp thêm. Ngược lại, một năng lực như `order`, `inventory` hoặc `customer` thường có lý do tốt để trở thành module khi nó có API và quy tắc thay đổi riêng.

Khi đã chọn ranh giới, hãy đặt lớp API ở package gốc, giữ triển khai trong package con, công bố thêm named interface khi có hợp đồng tích hợp cụ thể và khai báo các phụ thuộc được phép khi cần kiểm soát chặt. Cuối cùng, thêm `ApplicationModules.verify()` vào test để quyết định kiến trúc được thực thi bằng kiểm tra tự động.

## 9. Ghi nhớ

Một application module không được định nghĩa chỉ bằng cái tên thư mục. Nó là một đơn vị chức năng có **API được cung cấp, phần triển khai nội bộ và các phụ thuộc có quy tắc**. Spring Modulith dùng cấu trúc package để nhận diện đơn vị đó, dùng package gốc và `@NamedInterface` để xác định API, rồi dùng `ApplicationModules.verify()` để kiểm tra các ranh giới và quan hệ phụ thuộc.

Khi nhìn vào một package như `com.acme.shop.order`, hãy hỏi: “Mô-đun này sở hữu nghiệp vụ gì, công bố hợp đồng nào và được phép phụ thuộc vào đâu?” Câu trả lời cho ba câu hỏi đó mới cho thấy ta đang thiết kế một application module, thay vì chỉ sắp xếp file vào một thư mục.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
