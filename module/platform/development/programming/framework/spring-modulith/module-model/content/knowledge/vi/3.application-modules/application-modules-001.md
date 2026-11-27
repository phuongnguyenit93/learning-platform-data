# ApplicationModules là mô hình tổng của các module

Trong một ứng dụng Spring Boot được tổ chức theo modular monolith, ta cần nhìn toàn bộ các module như một hệ thống có cấu trúc: module nào tồn tại, mỗi module sở hữu package nào, phần API nào được công khai và các module đang liên hệ với nhau ra sao. Spring Modulith cung cấp lớp **ApplicationModules** để biểu diễn tổng thể đó trong bộ nhớ.

Có thể xem ApplicationModules là mô hình ở cấp ứng dụng. Nó được tạo bằng cách phân tích cấu trúc mã nguồn và cấu hình module, sau đó chứa các đối tượng **ApplicationModule** đại diện cho từng module được nhận diện. Nhờ mô hình tổng này, ta có thể liệt kê, tra cứu và kiểm chứng các module bằng API thống nhất.

Đây là điểm cốt lõi của chủ đề: ApplicationModules mô tả toàn bộ cách ứng dụng được chia thành module; ApplicationModule mô tả một module cụ thể trong cách chia đó.

## 1. Phân biệt ApplicationModules và ApplicationModule

Hai tên gọi gần giống nhau nhưng đại diện cho hai cấp độ khác nhau:

| Kiểu | Vai trò | Phạm vi |
|---|---|---|
| ApplicationModules | Mô hình tổng hợp các module của ứng dụng | Toàn bộ ứng dụng |
| ApplicationModule | Mô hình của một module cụ thể | Một module |
| @ApplicationModule | Annotation khai báo metadata hoặc quy tắc cho package module | Cấu hình một module |

ApplicationModules không chỉ là một danh sách tên package. Nó là điểm truy cập trung tâm để làm việc với mô hình module: tạo mô hình, duyệt các module, tìm module theo tên hoặc kiểu Java, và chạy kiểm chứng kiến trúc.

Mỗi ApplicationModule mô tả một đơn vị chức năng được nhận diện trong ứng dụng. Tùy cấu trúc và cấu hình, thông tin của nó có thể bao gồm package gốc, định danh module, các named interface được công khai, các kiểu nội bộ, Spring bean, sự kiện được phát hoặc lắng nghe và các phụ thuộc trực tiếp hay gián tiếp.

Sơ đồ dưới đây thể hiện quan hệ giữa hai cấp độ:

~~~mermaid
flowchart TD
    A["Lớp ứng dụng ShopApplication"] --> B["ApplicationModules"]
    B --> C["ApplicationModule: catalog"]
    B --> D["ApplicationModule: orders"]
    B --> E["ApplicationModule: customers"]
    C --> F["Package, API, bean và phụ thuộc của catalog"]
    D --> G["Package, API, bean và phụ thuộc của orders"]
    E --> H["Package, API, bean và phụ thuộc của customers"]
~~~

Khi đọc mã hoặc API của Spring Modulith, hãy giữ rõ sự phân biệt này. ApplicationModules quản lý góc nhìn toàn ứng dụng; ApplicationModule là phần tử mô tả từng module trong góc nhìn đó.

## 2. Tạo mô hình tổng từ lớp ứng dụng

Điểm bắt đầu phổ biến là gọi phương thức tĩnh of() với lớp khởi động Spring Boot:

~~~java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        org.springframework.boot.SpringApplication.run(
            ShopApplication.class, args
        );
    }
}
~~~

Ta tạo mô hình module từ lớp này:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

ApplicationModules.of() nhận lớp làm mốc để xác định phạm vi ứng dụng cần phân tích. Theo cấu trúc mặc định, package chứa lớp ứng dụng là package gốc; các package con trực tiếp của nó được xem là các package module.

Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── CatalogManagement.java
│   └── internal
│       └── CatalogRepository.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
└── customers
    ├── CustomerManagement.java
    └── internal
        └── CustomerRepository.java
~~~

Với cách sắp xếp này, Spring Modulith có thể nhận diện các module catalog, orders và customers. Các package con và quy tắc công khai của từng module tiếp tục được phân tích để xác định phần API và phần nội bộ.

Ta cũng có thể tạo mô hình từ tên package:

~~~java
ApplicationModules modules = ApplicationModules.of("com.acme.shop");
~~~

Cách dùng lớp ứng dụng thường dễ bảo trì hơn vì điểm bắt đầu gắn với lớp khởi động thực tế. Cách dùng tên package hữu ích trong trường hợp muốn chỉ định trực tiếp package gốc.

Việc phát hiện module dựa trên package và metadata kiến trúc, không dựa vào việc framework tự suy luận ý nghĩa nghiệp vụ từ tên gọi. Nếu ứng dụng có cách tổ chức khác quy ước mặc định, Spring Modulith cung cấp các cơ chế tùy chỉnh cách phát hiện module và package gốc. Nhóm phát triển cần cấu hình rõ ràng để mô hình phản ánh đúng ranh giới đã chọn.

## 3. Mô hình được tạo ra chứa những thông tin nào?

Sau khi gọi of(), ta có một đối tượng ApplicationModules trong bộ nhớ. Đối tượng này tập hợp các ApplicationModule được phát hiện từ codebase và cấu hình tương ứng.

Có thể nhóm thông tin trong mô hình thành bốn khía cạnh:

| Khía cạnh | Nội dung được mô tả | Ý nghĩa khi thiết kế |
|---|---|---|
| Danh tính và vị trí | Tên hoặc định danh module, package gốc | Xác định module thuộc khu vực mã nào |
| Thành phần | Kiểu Java, Spring bean và các thành phần liên quan | Hiểu module đang bao gồm những gì |
| Bề mặt giao tiếp | Package API mặc định, named interface và phần nội bộ | Xác định module khác có thể sử dụng phần nào |
| Quan hệ | Phụ thuộc giữa module, sự kiện công bố hoặc lắng nghe | Hiểu các module kết nối với nhau ra sao |

Ví dụ, module orders có thể có package gốc com.acme.shop.orders, cung cấp OrderManagement làm API nghiệp vụ, chứa OrderRepository trong package internal và phụ thuộc vào API của catalog.

ApplicationModules giữ góc nhìn tổng thể để những thông tin ở cấp module có thể được truy vấn và kiểm tra trong cùng một mô hình. Nó không thay thế mã nguồn hay lưu một bản sao triển khai độc lập của các module. Đây là kết quả phân tích kiến trúc được tạo trong bộ nhớ.

## 4. Duyệt và quan sát toàn bộ module

ApplicationModules triển khai giao diện Iterable<ApplicationModule>, đồng thời cung cấp phương thức stream(). Vì vậy, ta có thể duyệt các module theo nhiều cách quen thuộc của Java.

~~~java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

// Duyệt từng module
modules.forEach(System.out::println);

// Hoặc dùng Stream API
long moduleCount = modules.stream().count();

System.out.println("Số module: " + moduleCount);
~~~

Khi in từng ApplicationModule, biểu diễn văn bản của module giúp quan sát tên logic, package gốc, các Spring bean và thông tin hiển thị về khả năng truy cập. Đây là cách nhanh để kiểm tra Spring Modulith đang nhận diện ứng dụng như thế nào.

Có thể hình dung luồng quan sát như sau:

~~~mermaid
flowchart LR
    A["ApplicationModules"] --> B["Iterable"]
    A --> C["stream()"]
    B --> D["ApplicationModule"]
    C --> D
    D --> E["Quan sát từng module"]
~~~

Việc duyệt mô hình hữu ích trong những tình huống như:

- Kiểm tra ứng dụng đã được nhận diện thành bao nhiêu module.
- Xem package gốc của mỗi module.
- Đối chiếu cấu trúc thực tế với sơ đồ kiến trúc đã thống nhất.
- Phát hiện module chưa được nhận diện do package đặt sai vị trí hoặc cấu hình phát hiện chưa phù hợp.

Nếu kết quả in ra không giống kiến trúc mong đợi, hãy kiểm tra lớp hoặc package được truyền vào of(), package gốc của ứng dụng và chiến lược phát hiện module.

## 5. Tra cứu module từ mô hình tổng

Ngoài duyệt toàn bộ, ApplicationModules còn cho phép tìm một ApplicationModule cụ thể.

**Tìm theo tên module**

~~~java
modules.getModuleByName("orders")
    .ifPresent(System.out::println);
~~~

Phương thức getModuleByName() trả về Optional<ApplicationModule>. Vì module có thể không tồn tại trong mô hình, mã gọi nên xử lý trường hợp Optional rỗng thay vì giả định luôn tìm thấy kết quả.

**Tìm theo kiểu Java**

~~~java
modules.getModuleByType(OrderManagement.class)
    .ifPresent(System.out::println);
~~~

Cách này phù hợp khi ta biết một lớp cụ thể và muốn xác định nó thuộc module nào. Ví dụ, từ OrderManagement.class, mô hình có thể tìm module chứa lớp đó.

**Tìm theo package**

~~~java
modules.getModuleForPackage("com.acme.shop.orders")
    .ifPresent(System.out::println);
~~~

Cách này hữu ích khi đầu vào là tên package thay vì một lớp hoặc tên module.

Các phương thức tra cứu có thể được dùng trong công cụ hỗ trợ phát triển, kiểm thử kiến trúc hoặc mã cần phân tích một phần của mô hình. Hãy chọn khóa tra cứu dựa trên dữ liệu đang có: tên logic khi đã biết tên module, kiểu Java khi đang xử lý một lớp, và package khi đang làm việc với cấu trúc package.

## 6. Kiểm chứng toàn bộ mô hình bằng verify()

Một trong những giá trị lớn nhất của ApplicationModules là khả năng kiểm chứng kiến trúc ở cấp ứng dụng. Sau khi tạo mô hình, ta có thể gọi verify():

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Lệnh này yêu cầu Spring Modulith kiểm tra các quy tắc cấu trúc module áp dụng cho toàn bộ mô hình. Những kiểm tra quan trọng gồm:

1. **Không có chu trình phụ thuộc giữa các module.** Quan hệ phụ thuộc cấp module phải tạo thành đồ thị có hướng không chu trình.
2. **Chỉ truy cập API được công khai của module khác.** Tham chiếu từ module này vào kiểu nằm trong package nội bộ của module khác sẽ bị phát hiện là vi phạm theo quy tắc tương ứng.
3. **Tuân thủ danh sách phụ thuộc được phép nếu đã khai báo.** Khi module cấu hình allowedDependencies, các phụ thuộc thực tế phải phù hợp với chính sách đó.

Nếu phát hiện vi phạm, verify() ném ngoại lệ để bài kiểm thử thất bại. Nhóm có thể đưa bài kiểm thử này vào CI để mỗi thay đổi đều được kiểm tra với các ranh giới module đã xác định.

Nếu cần xử lý danh sách vi phạm theo cách linh hoạt hơn, ApplicationModules còn cung cấp detectViolations(). Phương thức này trả về đối tượng Violations để nhóm có thể xem xét, lọc hoặc yêu cầu ném lỗi khi còn vi phạm. Khác với verify(), detectViolations() luôn thực hiện kiểm tra khi được gọi.

Hãy nhớ rằng verify() kiểm tra kiến trúc được mô hình hóa từ mã và cấu hình. Nó không chứng minh nghiệp vụ đúng, không kiểm thử mọi luồng chạy và không thay thế kiểm thử đơn vị hay tích hợp. Nó bổ sung một lớp kiểm tra riêng dành cho cấu trúc module.

## 7. Mô hình tổng trong một quy trình làm việc

Giả sử nhóm đang phát triển ứng dụng bán hàng. Nhóm thống nhất ba module chính: catalog, orders và customers. Module orders cần sử dụng API của catalog và customers; các module còn lại không được phụ thuộc ngược lại vào orders.

Có thể áp dụng ApplicationModules theo quy trình:

~~~mermaid
flowchart TD
    A["Chọn lớp ShopApplication"] --> B["ApplicationModules.of(...)"]
    B --> C["Phân tích package và metadata"]
    C --> D["Tạo mô hình ApplicationModules"]
    D --> E["Duyệt và tra cứu ApplicationModule"]
    E --> F["Đối chiếu ranh giới và phụ thuộc"]
    F --> G["verify()"]
    G --> H["Kiến trúc hợp lệ"]
    G --> I["Báo lỗi để nhóm xử lý"]
~~~

Trong quy trình này:

- of() xác định điểm bắt đầu và tạo mô hình tổng.
- Mỗi ApplicationModule cung cấp góc nhìn chi tiết về một module.
- forEach() hoặc stream() giúp quan sát toàn bộ các module.
- Các phương thức getModuleByName(), getModuleByType() và getModuleForPackage() giúp tìm module theo thông tin đầu vào.
- verify() kiểm tra các quy tắc kiến trúc trên mô hình tổng.

Nhóm nên tạo mô hình từ lớp ứng dụng phù hợp với codebase và dùng cùng một điểm bắt đầu trong các bài kiểm thử kiến trúc. Nhờ đó, kết quả kiểm tra nhất quán với phạm vi ứng dụng mà nhóm định nghĩa.

## 8. Những giới hạn cần hiểu đúng

**ApplicationModules không phải Spring ApplicationContext.** ApplicationContext quản lý bean đã được khởi tạo trong vòng đời ứng dụng. ApplicationModules mô tả cấu trúc module được suy ra từ codebase và metadata kiến trúc. Hai đối tượng có mục đích khác nhau.

**ApplicationModules không phải bộ nạp module.** Nó không tạo classloader riêng, không tách module thành tiến trình và không tự cô lập bộ nhớ hoặc giao dịch giữa các module. Các module vẫn thuộc một ứng dụng Spring Boot thống nhất.

**Mô hình không tự thay đổi khi mã nguồn thay đổi.** Đối tượng được tạo từ kết quả phân tích tại thời điểm gọi of(). Khi cần phản ánh thay đổi trong codebase, hãy tạo lại mô hình trong lần kiểm tra tiếp theo.

**Phát hiện module phụ thuộc vào cấu trúc và cấu hình.** Package đặt sai vị trí hoặc chiến lược phát hiện không phù hợp có thể khiến mô hình khác với ý định của nhóm. Spring Modulith cung cấp cơ chế tùy chỉnh, nhưng nhóm phải khai báo rõ cách tổ chức mong muốn.

**ApplicationModule và annotation @ApplicationModule khác nhau.** ApplicationModule là đối tượng mô hình trong API của Spring Modulith; annotation @ApplicationModule là một cách khai báo metadata trên package hoặc kiểu phù hợp. Không nên nhầm đối tượng được phân tích với annotation dùng để cấu hình.

## Kết luận

ApplicationModules là mô hình tổng hợp trong bộ nhớ mô tả cách một ứng dụng Spring Boot được chia thành các application module. Nó được tạo từ lớp ứng dụng hoặc package gốc, chứa các ApplicationModule và cung cấp API để duyệt, tra cứu, quan sát cũng như kiểm chứng toàn bộ cấu trúc.

Khi sử dụng ApplicationModules, nhóm có một điểm truy cập thống nhất để đọc kiến trúc từ codebase và biến các quy tắc modular monolith thành kiểm tra có thể tự động hóa. ApplicationModule cho biết từng module là gì; ApplicationModules cho biết toàn bộ các module kết hợp thành kiến trúc ứng dụng như thế nào.
