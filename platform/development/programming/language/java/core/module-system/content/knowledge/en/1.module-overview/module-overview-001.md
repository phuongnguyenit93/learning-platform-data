# Java Platform Module System (JPMS) là gì?

Java Platform Module System (JPMS) là hệ thống mô-đun được đưa vào Java 9. Nó cho phép chia một ứng dụng hoặc thư viện thành các mô-đun có tên, khai báo rõ mô-đun nào phụ thuộc vào mô-đun nào và gói nào được phép cung cấp ra bên ngoài.

Trước JPMS, Java chủ yếu tổ chức mã nguồn bằng package và quản lý phụ thuộc lúc chạy qua classpath. Package giúp nhóm lớp theo namespace, nhưng bản thân package không nói rõ ứng dụng cần những thư viện nào hoặc package nào là API công khai. JPMS bổ sung một ranh giới ở cấp mô-đun để giải quyết hai vấn đề đó.

## 1. Vì sao Java cần hệ thống mô-đun?

Khi ứng dụng lớn dần, việc đặt tất cả JAR lên classpath tạo ra một số khó khăn:

- **Phụ thuộc khó nhìn thấy:** một thư viện có thể sử dụng lớp từ thư viện khác mà cấu hình build không thể hiện rõ quan hệ đó.
- **Ranh giới API không rõ:** nhiều package nội bộ vẫn có thể bị ứng dụng khác truy cập nếu lớp và thành viên của chúng là public.
- **Lỗi cấu hình xuất hiện muộn:** thiếu hoặc xung đột thư viện thường chỉ lộ ra khi chạy ứng dụng.
- **JDK quá lớn so với nhu cầu:** ứng dụng nhỏ vẫn thường chạy trên một JRE chứa nhiều thành phần không dùng đến.

JPMS cung cấp các cơ chế để:

1. Khai báo phụ thuộc ngay trong mô-đun.
2. Chỉ công khai những package được chọn.
3. Hỗ trợ kiểm tra và phân giải đồ thị mô-đun khi biên dịch hoặc khởi chạy.
4. Chia JDK thành các mô-đun nhỏ và tạo runtime image gọn hơn bằng công cụ như jlink.

JPMS không thay thế package. Package vẫn tổ chức lớp theo namespace; mô-đun gom một hoặc nhiều package và định nghĩa ranh giới phụ thuộc, truy cập của chúng.

## 2. Mô-đun là gì?

Một **named module** là một đơn vị có tên, chứa các package và tài nguyên, đồng thời có một module descriptor mô tả cách mô-đun hoạt động. Descriptor thường được viết trong file **module-info.java** ở thư mục gốc của source set.

Một mô-đun thường có:

- Tên ổn định, thường theo quy ước tên miền đảo ngược như **com.example.orders**.
- Một hoặc nhiều package.
- Danh sách mô-đun mà nó cần đọc.
- Danh sách package được export để mô-đun khác sử dụng.
- Các khai báo mở package cho reflection hoặc cung cấp dịch vụ, nếu cần.

Sau khi biên dịch, descriptor trở thành **module-info.class**. Khi đóng gói thành modular JAR, file này nằm ở gốc JAR.

Ví dụ cấu trúc đơn giản:

~~~text
project/
└── src/
    └── com.example.greetings/
        ├── module-info.java
        └── com/example/greetings/api/GreetingService.java
~~~

Nội dung descriptor:

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

Khai báo trên đặt tên mô-đun là **com.example.greetings** và công khai package **com.example.greetings.api**. Các package khác trong mô-đun vẫn được giữ kín với những mô-đun bên ngoài, trừ khi được export hoặc open riêng.

## 3. Hai khai báo quan trọng nhất: requires và exports

JPMS tách hai câu hỏi khác nhau:

- **requires:** mô-đun hiện tại cần đọc mô-đun nào?
- **exports:** mô-đun hiện tại cho phép mô-đun khác truy cập package nào?

Ví dụ có hai mô-đun:

~~~text
src/
├── com.example.greetings/
│   ├── module-info.java
│   └── com/example/greetings/api/GreetingService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Mô-đun thư viện công khai API:

~~~java
module com.example.greetings {
    exports com.example.greetings.api;
}
~~~

Mô-đun ứng dụng khai báo phụ thuộc vào thư viện:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Lớp API trong thư viện:

~~~java
package com.example.greetings.api;

public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Lớp sử dụng API:

~~~java
package com.example.app;

import com.example.greetings.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Java"));
    }
}
~~~

**requires** làm cho mô-đun ứng dụng đọc được mô-đun thư viện. **exports** cho phép ứng dụng truy cập các kiểu public thuộc package API. Chỉ có **public** trên lớp là chưa đủ: package chứa lớp cũng phải được export tới mô-đun đang sử dụng.

Một package không được export vẫn có thể chứa các lớp public, nhưng những mô-đun khác không thể sử dụng chúng như API thông thường. Đây là điểm tạo nên tính đóng gói mạnh của JPMS.

## 4. Những chỉ thị thường gặp trong module-info.java

| Chỉ thị | Ý nghĩa |
| --- | --- |
| **requires module.name;** | Khai báo phụ thuộc và khả năng đọc mô-đun được chỉ định. |
| **requires transitive module.name;** | Mô-đun phụ thuộc được truyền tiếp cho các mô-đun đọc mô-đun hiện tại. |
| **requires static module.name;** | Phụ thuộc cần khi biên dịch nhưng có thể không hiện diện lúc chạy. |
| **exports package.name;** | Công khai package cho các mô-đun đọc mô-đun hiện tại. |
| **exports package.name to a, b;** | Chỉ công khai package cho các mô-đun được nêu tên. |
| **opens package.name;** | Cho phép deep reflection trên package ở runtime. |
| **opens package.name to a, b;** | Chỉ cho các mô-đun được nêu tên deep reflection trên package. |
| **uses service.Type;** | Khai báo mô-đun sử dụng một service. |
| **provides service.Type with impl.Type;** | Khai báo mô-đun cung cấp implementation cho một service. |

### requires transitive

Giả sử mô-đun **com.example.facade** dùng kiểu dữ liệu của **com.example.library** trong API public. Nếu mô-đun ứng dụng chỉ phụ thuộc vào facade, nó có thể cần đọc cả library để biên dịch và sử dụng API đó.

~~~java
module com.example.facade {
    requires transitive com.example.library;
}
~~~

**transitive** truyền khả năng đọc phụ thuộc tới các mô-đun đọc facade. Chỉ dùng khi phụ thuộc thực sự là một phần của hợp đồng API mà facade đưa ra.

### requires static

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

Chỉ thị này hữu ích cho annotation hoặc tích hợp tùy chọn chỉ cần ở thời điểm biên dịch. Nó không tự bảo đảm ứng dụng có thể chạy mọi nhánh mã nếu mô-đun bị thiếu; mã thực sự cần lớp từ dependency vẫn phải xử lý đúng việc dependency có mặt hay không.

### exports có giới hạn

~~~java
module com.example.internal.api {
    exports com.example.internal.api to com.example.app;
}
~~~

Package chỉ được công khai cho mô-đun **com.example.app**. Cách này phù hợp khi một package cần chia sẻ giữa một số mô-đun nội bộ nhưng không nên trở thành API chung cho tất cả người dùng.

## 5. exports khác opens như thế nào?

**exports** phục vụ truy cập API thông thường từ mã Java. Nó cho phép mô-đun khác tham chiếu các kiểu public trong package đã export, tuân theo quy tắc truy cập của Java.

**opens** phục vụ reflection ở runtime, đặc biệt là **deep reflection** — truy cập các thành viên không public khi framework cần đọc hoặc thay đổi trạng thái bên trong đối tượng.

Ví dụ một framework cần đọc field private để ánh xạ dữ liệu:

~~~java
module com.example.domain {
    opens com.example.domain.model to com.example.mapper;
}
~~~

Mô-đun mapper được phép thực hiện deep reflection trên package model. Khai báo **opens** không biến package thành API public để mã nguồn khác import tùy ý.

Có thể mở toàn bộ package của một mô-đun cho reflection bằng:

~~~java
open module com.example.domain {
    // Các requires và khai báo khác nếu cần.
}
~~~

Chỉ nên mở phạm vi cần thiết. Mở toàn bộ mô-đun làm giảm lợi ích đóng gói mà JPMS cung cấp. Với ứng dụng dùng framework, hãy xác định chính xác package nào framework cần truy cập qua reflection và mở package đó.

## 6. JPMS và cơ chế Service Provider

JPMS hỗ trợ mô hình service để mô-đun sử dụng phụ thuộc qua một interface thay vì phụ thuộc trực tiếp vào implementation.

Mô-đun khai báo service:

~~~java
module com.example.payment.api {
    exports com.example.payment;
}
~~~

Mô-đun ứng dụng khai báo sử dụng service:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.PaymentProcessor;
}
~~~

Mô-đun triển khai khai báo provider:

~~~java
module com.example.payment.stripe {
    requires com.example.payment.api;
    provides com.example.payment.PaymentProcessor
        with com.example.payment.stripe.StripePaymentProcessor;
}
~~~

Ứng dụng có thể tìm implementation bằng **ServiceLoader**:

~~~java
ServiceLoader<PaymentProcessor> processors =
        ServiceLoader.load(PaymentProcessor.class);

for (PaymentProcessor processor : processors) {
    processor.process();
}
~~~

Cách này tách hợp đồng service khỏi implementation và cho phép bổ sung provider mà không buộc mô-đun sử dụng phải biết lớp triển khai cụ thể.

## 7. Named module, automatic module và unnamed module

Trong một ứng dụng Java có thể gặp ba loại mô-đun:

| Loại | Nguồn hình thành | Đặc điểm |
| --- | --- | --- |
| Named module | Có **module-info.java** | Có tên và khai báo rõ dependency, exports, opens, service. |
| Automatic module | JAR không có descriptor nhưng được đặt trên module path | Tên thường lấy từ manifest **Automatic-Module-Name** hoặc suy ra từ tên file; tự động export các package và đọc các named module khác. |
| Unnamed module | Các lớp/JAR trên classpath | Không có tên mô-đun; thường dùng để duy trì khả năng tương thích với ứng dụng chưa modular hóa. |

Automatic module là cầu nối hữu ích khi chuyển thư viện cũ sang module path. Tuy nhiên, vì các package của nó được export rộng và khả năng đọc dependency rất rộng, nó không tạo ra ranh giới rõ như một named module có descriptor được thiết kế cẩn thận.

Các lớp trên classpath thuộc unnamed module của class loader tương ứng. Unnamed module có thể đọc các named module quan sát được và export các package của nó. Một named module không thể khai báo **requires** tới unnamed module, vì unnamed module không có tên để tham chiếu.

## 8. Module path khác classpath ra sao?

Classpath là cơ chế tìm lớp truyền thống. Khi chạy với classpath, JVM không dùng module descriptor để xây dựng đồ thị dependency cho các JAR trên classpath.

Module path chứa các mô-đun mà JPMS có thể nhận diện và phân giải. Khi khởi chạy một ứng dụng modular, JVM tìm mô-đun gốc, giải quyết các chỉ thị **requires**, rồi tạo module layer phù hợp.

Ví dụ biên dịch hai mô-đun theo cấu trúc ở phần trên:

~~~bash
javac --module-source-path src -d out -m com.example.greetings,com.example.app
~~~

Chạy lớp main trong mô-đun ứng dụng:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Trong lệnh chạy:

- **--module-path out** chỉ ra nơi chứa các mô-đun đã biên dịch.
- **-m** hoặc **--module** chỉ định mô-đun và lớp main theo dạng **module.name/main.class**.

Với một ứng dụng chưa modular hóa, vẫn có thể chạy theo cách truyền thống:

~~~bash
java -cp "lib/*:classes" com.example.app.Main
~~~

Dấu phân cách classpath tùy hệ điều hành: **:** trên Unix-like và **;** trên Windows. Dự án có thể chuyển đổi từng bước, nhưng cần kiểm tra tương thích của thư viện và framework khi đưa dependency từ classpath sang module path.

## 9. JPMS trong chính JDK

JDK cũng được chia thành các mô-đun. Một số mô-đun thường gặp:

- **java.base:** các API nền tảng như java.lang, java.util, java.io; mọi mô-đun đều phụ thuộc ngầm vào mô-đun này.
- **java.sql:** JDBC và API truy cập cơ sở dữ liệu.
- **java.xml:** API xử lý XML.
- **java.logging:** API logging chuẩn.
- **jdk.compiler:** các công cụ và API liên quan đến trình biên dịch Java.

Việc chia JDK thành mô-đun giúp runtime chỉ cần những thành phần mà ứng dụng yêu cầu. Công cụ **jlink** có thể ghép các mô-đun cần thiết thành một runtime image tùy chỉnh. Đây là nền tảng để phân phối ứng dụng với môi trường chạy gọn hơn so với việc mang theo toàn bộ JDK.

## 10. JPMS không có nghĩa là mọi dự án đều phải modular hóa

JPMS hữu ích khi cần quản lý ranh giới giữa các phần của hệ thống, phát triển thư viện có API rõ ràng, kiểm soát reflection hoặc tạo runtime image riêng.

Với một ứng dụng nhỏ, thêm **module-info.java** có thể làm tăng công sức cấu hình mà chưa đem lại lợi ích tương xứng. Với ứng dụng dùng nhiều framework cũ, việc chuyển sang module path còn có thể cần mở package cho reflection hoặc xử lý các dependency chưa có module descriptor.

Có thể cân nhắc JPMS khi:

- Dự án có nhiều thư viện hoặc nhiều nhóm phát triển cần ranh giới API rõ ràng.
- Muốn ngăn việc sử dụng package nội bộ ngoài dự kiến.
- Xây dựng thư viện cần công bố API ổn định.
- Muốn phân tích dependency và tạo runtime image tối giản.
- Cần thiết kế plugin hoặc service provider theo hợp đồng rõ ràng.

Nếu ứng dụng hiện tại đang chạy ổn trên classpath, việc áp dụng JPMS nên xuất phát từ một mục tiêu cụ thể như kiểm soát API, giảm phụ thuộc hoặc tối ưu runtime.

## 11. Những nhầm lẫn thường gặp

**Package và module là một thứ:** Không đúng. Package là namespace chứa lớp; module là đơn vị lớn hơn, gom nhiều package và quản lý dependency cũng như quyền truy cập.

**Lớp public luôn dùng được từ mô-đun khác:** Không đúng. Package chứa lớp phải được export cho mô-đun sử dụng.

**exports và opens giống nhau:** Không đúng. **exports** công khai API cho truy cập Java thông thường; **opens** cho phép deep reflection ở runtime.

**requires tự động làm package của dependency trở thành API công khai:** Không đúng. **requires** thiết lập quan hệ đọc mô-đun. Package vẫn cần được mô-đun sở hữu export.

**Có module-info.java là không thể dùng thư viện cũ:** Không đúng. JPMS hỗ trợ automatic module và unnamed module để tương thích trong giai đoạn chuyển đổi, dù các cơ chế này có ranh giới yếu hơn named module tường minh.

**JPMS chỉ là cách đóng gói JAR:** Không đúng. JAR là định dạng đóng gói; JPMS còn định nghĩa cách phân giải mô-đun, khả năng đọc, export, reflection và service.

## 12. Cách ghi nhớ

Có thể hiểu JPMS qua ba câu hỏi:

1. **Mô-đun này cần gì?** Dùng **requires** để khai báo dependency.
2. **Mô-đun này công khai gì?** Dùng **exports** để công khai package API.
3. **Framework cần truy cập nội bộ bằng reflection ở đâu?** Dùng **opens** cho đúng package và đúng mô-đun.

Khi ba câu hỏi này được trả lời rõ ràng, module descriptor trở thành bản mô tả ngắn gọn về ranh giới và hợp đồng của mô-đun. Đó là giá trị cốt lõi của Java Platform Module System.
