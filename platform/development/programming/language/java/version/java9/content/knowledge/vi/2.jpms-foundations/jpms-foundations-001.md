# Động cơ tách hệ thống thành các mô-đun có ranh giới rõ ràng

Java Platform Module System (JPMS), được giới thiệu trong Java 9, cung cấp cơ chế để chia ứng dụng hoặc thư viện Java thành các mô-đun có tên, có phụ thuộc được khai báo và có phạm vi truy cập được kiểm soát. Động cơ cốt lõi là làm cho cấu trúc của hệ thống thể hiện rõ trong mã và trong quá trình chạy: thành phần nào cung cấp chức năng, thành phần nào được phép phụ thuộc vào nó, và phần triển khai nào cần được giữ kín.

JPMS vẫn là nền tảng hiện hành của Java. Các ứng dụng nhỏ có thể tiếp tục chạy trên classpath; việc dùng module descriptor có giá trị nhất khi hệ thống có nhiều package, nhiều nhóm chức năng hoặc cần một hợp đồng API ổn định giữa các phần.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích những khó khăn xuất hiện khi hệ thống lớn lên nhưng các package và dependency không có ranh giới rõ.
- Nêu được các mục tiêu kiến trúc của JPMS: phụ thuộc tường minh, đóng gói mạnh, cấu hình đáng tin cậy và khả năng bảo trì.
- Phân biệt lợi ích của mô-đun với việc chỉ chia mã thành package hoặc thư mục.
- Nhận diện trường hợp nên và chưa nên mô-đun hóa.
- Đọc ví dụ ba mô-đun có thể biên dịch và chạy bằng Java 17 trở lên.

## 1. Vì sao hệ thống cần ranh giới mô-đun?

### 1.1. Khi ứng dụng còn nhỏ

Một chương trình ban đầu có thể chỉ gồm vài class. Các class gọi trực tiếp nhau, số dependency ít và người phát triển dễ nắm toàn bộ cấu trúc. Khi hệ thống lớn dần, các chức năng như quản lý người dùng, đơn hàng, thanh toán, báo cáo và tích hợp bên ngoài có thể phát triển thành nhiều package và nhiều nhóm class.

Nếu mọi thành phần đều có thể phụ thuộc tùy ý vào nhau, một thay đổi nhỏ có thể lan sang nhiều nơi. Một class ở tầng giao diện có thể gọi thẳng vào chi tiết lưu trữ; một module nghiệp vụ có thể sử dụng class nội bộ của module khác; dependency mới có thể xuất hiện mà kiến trúc không thể hiện rõ. Khi đó, cấu trúc thư mục trông có vẻ được chia nhỏ nhưng ranh giới thực tế vẫn lỏng lẻo.

### 1.2. Các vấn đề khi thiếu ranh giới

- **Phụ thuộc ngầm:** nhìn vào một class khó biết nó cần những thành phần nào. Dependency có thể được kéo vào qua classpath hoặc qua các thư viện khác.
- **Rò rỉ chi tiết triển khai:** class được khai báo public có thể bị thành phần khác sử dụng dù nó chỉ được tạo ra để phục vụ nội bộ.
- **Thay đổi lan rộng:** một phần triển khai bị sửa có thể buộc nhiều phần không liên quan phải sửa theo.
- **Khó hiểu kiến trúc:** tên package hoặc cách sắp xếp thư mục không đủ để trình biên dịch biết package nào được phép truy cập từ thành phần nào.
- **Khó kiểm soát dependency:** phiên bản thư viện, dependency bắc cầu và thành phần không còn được sử dụng có thể làm cấu hình ngày càng phức tạp.
- **Khó chia việc giữa các nhóm:** nếu hợp đồng giữa các phần không rõ, các nhóm dễ phụ thuộc vào class nội bộ của nhau và phát sinh xung đột khi thay đổi.

Classpath vẫn cần thiết và vẫn được hỗ trợ trong Java hiện nay, nhưng classpath truyền thống không tự mô tả đầy đủ ranh giới truy cập giữa các nhóm package. JPMS bổ sung một lớp cấu trúc ở cấp mô-đun để giải quyết vấn đề này.

## 2. Những động cơ chính của JPMS

### 2.1. Khai báo phụ thuộc tường minh

Mỗi named module có thể khai báo các mô-đun mà nó cần thông qua module descriptor. Người đọc và công cụ build có thể xác định module nào đọc được module nào. Điều này giúp dependency trở thành một phần của thiết kế, thay vì chỉ là kết quả gián tiếp của classpath.

Khi một dependency bắt buộc bị thiếu hoặc không thể giải quyết, hệ thống module có thể phát hiện vấn đề trong quá trình biên dịch hoặc khởi chạy. Nhờ đó, lỗi cấu hình được phát hiện sớm hơn so với việc để một đường gọi hiếm gặp mới bộc lộ lỗi ở thời điểm chạy.

### 2.2. Đóng gói mạnh, giới hạn API công khai

Trong Java, từ khóa public chỉ nói rằng một kiểu hoặc thành viên có thể được truy cập theo quy tắc ngôn ngữ. Với named module, một package còn phải được module export thì module khác mới có thể truy cập API công khai trong package đó.

Điều này cho phép module công bố một bề mặt API nhỏ, trong khi giữ package triển khai ở bên trong. Các class nội bộ có thể được đổi tên, tách hoặc tổ chức lại mà ít ảnh hưởng đến bên sử dụng, miễn là hợp đồng công khai được giữ ổn định.

Đóng gói mạnh cũng giảm khả năng thành phần bên ngoài vô tình dựa vào chi tiết triển khai. Với truy cập phản chiếu, module có thể kiểm soát riêng package nào được mở cho mục đích đó; việc mở package cần được cân nhắc theo nhu cầu thực tế.

### 2.3. Cấu hình đáng tin cậy và đồ thị module rõ ràng

Một hệ thống module tạo thành đồ thị phụ thuộc. JPMS và JVM giải quyết đồ thị này để xác định các module cần có và các quan hệ đọc giữa chúng. Module descriptor cho biết dependency nào là chủ ý của module.

Đồ thị rõ ràng giúp:

- Phát hiện module bắt buộc không có trong cấu hình chạy.
- Hiểu thành phần nào cần module nào.
- Tránh phụ thuộc tùy tiện vào các package nội bộ.
- Hỗ trợ công cụ build, kiểm tra và đóng gói runtime theo tập module cần thiết.

Đây là một phần của mục tiêu cấu hình đáng tin cậy: các thành phần được nạp theo cấu trúc dependency đã khai báo, thay vì phụ thuộc vào một classpath lớn khó kiểm soát.

### 2.4. Giảm ảnh hưởng khi thay đổi

Khi ranh giới được thiết kế tốt, module cung cấp một hợp đồng ổn định và giữ phần triển khai bên trong. Một thay đổi nội bộ không cần lan sang các module khác nếu API công khai không đổi.

Ví dụ, module báo cáo chỉ cần biết cách gọi API lấy dữ liệu. Nó không cần biết module dữ liệu dùng cấu trúc collection nội bộ nào, truy vấn ra sao hoặc tổ chức class repository thế nào. Module dữ liệu có thể tối ưu triển khai mà không buộc module báo cáo sửa theo.

Điều này không có nghĩa là mọi thay đổi đều được cô lập tự động. Nếu API công khai thay đổi, các module phụ thuộc vẫn cần được cập nhật. Lợi ích nằm ở việc giới hạn phần được phép phụ thuộc và làm rõ nơi thay đổi có thể ảnh hưởng.

### 2.5. Hỗ trợ phát triển theo nhóm và tái sử dụng

Một module có API và dependency rõ ràng giúp các nhóm làm việc song song trên các phần khác nhau. Nhóm cung cấp module chịu trách nhiệm về hợp đồng; nhóm sử dụng module chỉ phụ thuộc vào API được công bố.

Một module thư viện có thể được tái sử dụng bởi nhiều ứng dụng nếu hợp đồng của nó ổn định. Ranh giới module giúp người dùng thư viện biết phần nào được hỗ trợ để gọi và phần nào là chi tiết nội bộ không nên phụ thuộc.

### 2.6. Hỗ trợ runtime gọn hơn khi cần

JPMS cũng cho phép công cụ như jlink tạo runtime image chứa tập module cần thiết cho ứng dụng. Đây là lợi ích hữu ích khi xây dựng bản phân phối có kiểm soát thành phần runtime.

Tuy vậy, không phải mọi ứng dụng module đều cần tự tạo runtime image. Đây là lựa chọn triển khai khi kích thước, môi trường chạy hoặc khả năng phân phối yêu cầu; lợi ích kiến trúc của ranh giới module vẫn có giá trị độc lập với jlink.

## 3. Một ranh giới mô-đun tốt trông như thế nào?

### 3.1. Ranh giới dựa trên trách nhiệm và hợp đồng

Hãy chia hệ thống theo năng lực hoặc miền nghiệp vụ có trách nhiệm tương đối độc lập, ví dụ catalog, identity, billing hoặc reporting. Mỗi module nên có mục đích dễ giải thích và API phục vụ mục đích đó.

Không nên tạo một module cho mỗi class hoặc mỗi package chỉ để tăng số lượng module. Module quá nhỏ làm tăng chi phí khai báo, dependency và phối hợp mà không đem lại ranh giới có ý nghĩa.

### 3.2. Giữ API nhỏ, giữ triển khai ở bên trong

Một module nên chỉ công bố các kiểu mà người sử dụng thực sự cần. Những package chứa adapter, helper, repository nội bộ hoặc chi tiết triển khai nên được giữ kín nếu không có lý do để công khai.

Nếu mọi package đều được export, hệ thống vẫn có module descriptor nhưng lợi ích đóng gói giảm đáng kể. API công khai càng lớn thì càng nhiều chi tiết trở thành cam kết tương thích dài hạn.

### 3.3. Dependency đi theo hướng kiến trúc

Ví dụ, module ứng dụng có thể phụ thuộc vào module dịch vụ; module dịch vụ phụ thuộc vào module API hoặc domain. Hạn chế việc module thấp tầng phụ thuộc ngược vào module ứng dụng. Dependency vòng khiến ranh giới khó hiểu và làm giảm khả năng thay đổi độc lập.

Một cách kiểm tra hữu ích là hỏi: "Nếu thay đổi phần triển khai của module này, module nào thực sự cần biết?" Nếu câu trả lời là quá nhiều module, có thể API đang quá rộng hoặc trách nhiệm chưa được tách hợp lý.

### 3.4. Không nhầm module với microservice

JPMS tổ chức mã và quyền truy cập trong hệ sinh thái module của Java. Các module thường chạy trong cùng một tiến trình JVM, có thể gọi nhau trực tiếp và chia sẻ bộ nhớ theo các quy tắc của Java.

Tách module không tự tạo ra dịch vụ độc lập qua mạng, không tự có database riêng, không tự triển khai riêng và không tạo ra ranh giới lỗi như một tiến trình riêng. Microservice là quyết định kiến trúc phân tán với giao tiếp, vận hành và triển khai riêng. Một ứng dụng có thể là modular monolith: một đơn vị triển khai nhưng bên trong có các module rõ ràng.

## 4. Ví dụ: tách ứng dụng catalog thành ba module

Ví dụ này có ba module:

- catalog.api: cung cấp kiểu dữ liệu Product dùng chung.
- catalog.service: chứa nghiệp vụ lấy danh sách sản phẩm và công bố ProductService.
- catalog.app: là ứng dụng khởi chạy, sử dụng API và service.

Cấu trúc thư mục:

~~~text
src/
├── catalog.api/
│   ├── module-info.java
│   └── com/acme/catalog/api/Product.java
├── catalog.service/
│   ├── module-info.java
│   └── com/acme/catalog/service/ProductService.java
└── catalog.app/
    ├── module-info.java
    └── com/acme/catalog/app/Main.java
~~~

### 4.1. Module catalog.api

File src/catalog.api/module-info.java:

~~~java
module catalog.api {
    exports com.acme.catalog.api;
}
~~~

File src/catalog.api/com/acme/catalog/api/Product.java:

~~~java
package com.acme.catalog.api;

public record Product(String name, int price) { }
~~~

Module API chỉ công bố package chứa Product. Các module khác có thể dùng kiểu Product thông qua hợp đồng này.

### 4.2. Module catalog.service

File src/catalog.service/module-info.java:

~~~java
module catalog.service {
    requires catalog.api;
    exports com.acme.catalog.service;
}
~~~

File src/catalog.service/com/acme/catalog/service/ProductService.java:

~~~java
package com.acme.catalog.service;

import com.acme.catalog.api.Product;
import java.util.List;

public final class ProductService {
    public List<Product> findAvailableProducts() {
        return List.of(
                new Product("Keyboard", 120),
                new Product("Mouse", 40)
        );
    }
}
~~~

Service khai báo rõ dependency vào catalog.api. Package service được công bố để ứng dụng có thể gọi ProductService. Trong một hệ thống lớn hơn, các chi tiết repository hoặc adapter có thể nằm trong package không export.

### 4.3. Module catalog.app

File src/catalog.app/module-info.java:

~~~java
module catalog.app {
    requires catalog.api;
    requires catalog.service;
}
~~~

File src/catalog.app/com/acme/catalog/app/Main.java:

~~~java
package com.acme.catalog.app;

import com.acme.catalog.api.Product;
import com.acme.catalog.service.ProductService;
import java.util.List;

public final class Main {
    public static void main(String[] args) {
        List<Product> products =
                new ProductService().findAvailableProducts();

        System.out.println("module boundary=app -> service -> api");
        System.out.println("product count=" + products.size());
        System.out.println("product names="
                + products.stream().map(Product::name).toList());
    }
}
~~~

### 4.4. Biên dịch và chạy

Từ thư mục chứa thư mục src, dùng JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d out -m catalog.api,catalog.service,catalog.app
java --module-path out -m catalog.app/com.acme.catalog.app.Main
~~~

Kết quả stdout:

~~~text
module boundary=app -> service -> api
product count=2
product names=[Keyboard, Mouse]
~~~

Ví dụ cho thấy ba điều:

1. Dependency được khai báo trong module descriptor thay vì chỉ dựa vào việc đặt JAR trên classpath.
2. catalog.service đọc được catalog.api vì có requires, và catalog.app đọc được API mà hai module đã export.
3. Mỗi module có thể giữ package triển khai riêng. Module sử dụng chỉ nhìn thấy phần được công bố.

Trong ví dụ nhỏ, các module nằm trong cùng một ứng dụng và cùng runtime. Việc tách module tạo ranh giới cấu trúc và truy cập; nó không biến chúng thành ba dịch vụ độc lập.

## 5. Khi nào nên và chưa nên mô-đun hóa?

### Nên cân nhắc JPMS khi

- Ứng dụng có nhiều nhóm chức năng và dependency bắt đầu khó theo dõi.
- Thư viện cần công bố một API ổn định, đồng thời giữ package nội bộ.
- Nhiều nhóm cùng phát triển và cần hợp đồng rõ giữa các phần.
- Cần kiểm soát module nào được phép đọc module nào.
- Cần đóng gói runtime image với tập module xác định.

### Chưa cần vội mô-đun hóa khi

- Ứng dụng nhỏ, số package và dependency ít, ranh giới đã rõ bằng cấu trúc đơn giản.
- Module dự kiến quá nhỏ hoặc không có API có ý nghĩa.
- Các package chưa có trách nhiệm ổn định và dependency vẫn thay đổi liên tục.
- Dự án chưa sẵn sàng xử lý các vấn đề tương thích của thư viện hoặc framework khi chuyển sang module path.

Classpath vẫn là lựa chọn hợp lệ trong Java hiện nay. Có thể tiếp tục dùng classpath nếu dự án chưa cần các đảm bảo của JPMS. Khi cần chuyển đổi, hãy lập kế hoạch theo dependency thực tế của ứng dụng và các thư viện đang dùng; không nên thêm module descriptor chỉ để làm cho dự án trông hiện đại hơn.

## 6. Các sai lầm kiến trúc thường gặp

- **Chia module theo số lượng class:** module không phải một cách đặt tên thư mục mới. Mỗi module cần có trách nhiệm và hợp đồng có ý nghĩa.
- **Export mọi package:** làm lộ chi tiết triển khai và khiến việc refactor khó hơn.
- **Tạo dependency vòng:** làm mờ hướng phụ thuộc và khiến module khó phát triển độc lập.
- **Gom mọi thứ vào một module khổng lồ:** module descriptor tồn tại nhưng không tạo được ranh giới kiến trúc thực chất.
- **Cho rằng module là microservice:** module không cung cấp giao tiếp mạng, triển khai riêng hay cô lập tiến trình.
- **Dùng module như giải pháp thay thế cho thiết kế tốt:** JPMS hỗ trợ thực thi ranh giới đã thiết kế; nó không tự quyết định domain, trách nhiệm hoặc API đúng.
- **Chuyển đổi toàn bộ hệ thống cùng lúc:** việc chuyển đổi có thể ảnh hưởng đến dependency và framework. Nên kiểm kê dependency, xác định API và chuyển theo từng phần có thể kiểm chứng.

## 7. Quy trình suy nghĩ khi tách một hệ thống

1. Xác định các năng lực hoặc miền nghiệp vụ chính và trách nhiệm của từng phần.
2. Xác định API tối thiểu mà phần khác cần sử dụng.
3. Liệt kê dependency theo hướng từ thành phần sử dụng đến thành phần cung cấp.
4. Đưa chi tiết triển khai vào package nội bộ và chỉ công bố package cần thiết.
5. Kiểm tra dependency vòng, dependency không cần thiết và các API đang bị sử dụng ngoài dự kiến.
6. Biên dịch, chạy và kiểm tra module graph trong cấu hình thật của dự án.
7. Chỉ bổ sung module mới khi nó tạo ra một ranh giới dễ hiểu và có thể duy trì.

## 8. Checklist tự đánh giá

- [ ] Giải thích được vì sao classpath lớn và dependency ngầm gây khó khăn khi hệ thống phát triển.
- [ ] Nêu được bốn mục tiêu: dependency tường minh, đóng gói mạnh, cấu hình đáng tin cậy và bảo trì dễ hơn.
- [ ] Hiểu rằng public trong Java chưa đồng nghĩa với package được module khác truy cập.
- [ ] Biết rằng named module chỉ công bố package cần thiết.
- [ ] Phân biệt module trong JVM với microservice chạy trong tiến trình độc lập.
- [ ] Biết khi nào modular monolith là lựa chọn phù hợp.
- [ ] Đọc được đồ thị app -> service -> api trong ví dụ.
- [ ] Biết kiểm tra dependency và API trước khi tách module.
- [ ] Không mô-đun hóa chỉ để tăng số lượng module.
