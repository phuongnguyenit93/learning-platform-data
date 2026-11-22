# Vòng phụ thuộc module và lỗi resolve

Trong Java Platform Module System (JPMS), mỗi named module khai báo dependency bằng directive `requires` trong `module-info.java`. Tập hợp các module và quan hệ `requires` tạo thành một đồ thị phụ thuộc. Để Java có thể phân giải (resolve) module graph, các module cần được tìm thấy và các quan hệ phụ thuộc phải hợp lệ.

Một lỗi quan trọng là **vòng phụ thuộc module**: module A cần B, B cần C, và C lại cần A. Vòng này khiến ranh giới phụ thuộc không còn có thứ tự rõ ràng, nên JPMS không thể phân giải đồ thị module như một cấu trúc hợp lệ.

Cần phân biệt vòng phụ thuộc ở cấp module với việc hai class gọi lẫn nhau hoặc hai package tham chiếu kiểu của nhau. Java cho phép nhiều kiểu có quan hệ tham chiếu qua lại; điều bị cấm trong thiết kế JPMS là chu trình trong quan hệ phụ thuộc giữa các named module.

## 1. Module graph hình thành từ requires

Mỗi directive `requires` tạo một cạnh phụ thuộc có hướng từ module khai báo sang module được yêu cầu.

Ví dụ:

~~~java
module com.example.checkout {
    requires com.example.catalog;
    requires com.example.payment;
}
~~~

Có thể đọc theo hướng:

- `com.example.checkout` cần đọc `com.example.catalog`.
- `com.example.checkout` cần đọc `com.example.payment`.

Nếu `com.example.payment` cũng khai báo `requires com.example.catalog`, quan hệ phụ thuộc vẫn hợp lệ:

~~~java
module com.example.payment {
    requires com.example.catalog;
}
~~~

Đồ thị lúc này có dạng:

~~~text
com.example.checkout ──requires──> com.example.catalog
          │
          └────────────requires──> com.example.payment
                                         │
                                         └──requires──> com.example.catalog
~~~

Đây là một đồ thị có hướng không có chu trình. Một module có thể phụ thuộc vào nhiều module và nhiều module có thể cùng phụ thuộc vào một module dùng chung.

Vấn đề xuất hiện khi một chuỗi phụ thuộc quay trở lại module ban đầu:

~~~text
com.example.order
       │
       ▼
com.example.payment
       │
       ▼
com.example.customer
       │
       └──────────────> com.example.order
~~~

Chu trình có thể gồm hai module hoặc nhiều module. Chỉ cần tồn tại một đường đi từ module này quay trở lại chính nó thông qua các cạnh `requires`, module graph đã có vòng phụ thuộc.

## 2. Ví dụ vòng phụ thuộc hai module

Giả sử hệ thống có hai module:

~~~text
module-order/
└── module-info.java

module-payment/
└── module-info.java
~~~

Descriptor của module order:

~~~java
module com.example.order {
    requires com.example.payment;
}
~~~

Descriptor của module payment:

~~~java
module com.example.payment {
    requires com.example.order;
}
~~~

Quan hệ thực tế:

~~~text
com.example.order ──requires──> com.example.payment
com.example.payment ──requires──> com.example.order
~~~

Khi compiler hoặc công cụ Java phân giải hai module, nó phát hiện mỗi module đều cần module còn lại để hoàn thành dependency graph. Đây là chu trình trong module graph và quá trình phân giải sẽ thất bại.

Tùy phiên bản JDK, công cụ và giai đoạn phát hiện, thông báo lỗi có thể diễn đạt khác nhau, ví dụ có cụm từ như `cyclic dependence`, `cycle detected` hoặc chỉ ra chuỗi module liên quan. Không nên dựa vào một chuỗi lỗi duy nhất; hãy đọc tên các module và lần theo các directive `requires` để tìm đường quay về module ban đầu.

## 3. Vòng phụ thuộc nhiều module

Trong dự án lớn, chu trình thường khó nhận ra vì các cạnh phụ thuộc nằm trong nhiều descriptor khác nhau.

Ví dụ:

~~~java
// module com.example.order
module com.example.order {
    requires com.example.payment;
}
~~~

~~~java
// module com.example.payment
module com.example.payment {
    requires com.example.customer;
}
~~~

~~~java
// module com.example.customer
module com.example.customer {
    requires com.example.order;
}
~~~

Đồ thị:

~~~text
order ──requires──> payment
  ▲                    │
  │                    ▼
customer <─────────────┘
       requires
~~~

Có thể lần theo chuỗi:

1. `com.example.order` cần `com.example.payment`.
2. `com.example.payment` cần `com.example.customer`.
3. `com.example.customer` lại cần `com.example.order`.

Chu trình không nhất thiết xuất hiện trong hai file cạnh nhau hoặc trong cùng một thư mục. Vì vậy, khi xử lý lỗi resolve, cần kiểm tra toàn bộ đường phụ thuộc liên quan thay vì chỉ sửa descriptor đầu tiên được nhắc trong thông báo.

## 4. Vì sao vòng phụ thuộc là vấn đề?

Module descriptor được thiết kế để mô tả các ranh giới phụ thuộc có thể phân giải. Chu trình làm cho ranh giới đó mất tính một chiều: mỗi module vừa là dependency của module khác, vừa cần module đó để hình thành quan hệ đọc.

Một số hệ quả:

- **Không thể resolve module graph:** JPMS không chấp nhận chu trình trong quan hệ `requires` của named module.
- **Ranh giới trách nhiệm bị mờ:** hai module có thể đang chia sẻ quá nhiều chi tiết triển khai hoặc cùng sở hữu một phần abstraction.
- **Khó kiểm soát API:** thay đổi trong module này dễ kéo theo thay đổi descriptor và build của module kia.
- **Khó tái sử dụng độc lập:** một module không thể được phân phối hoặc phát triển độc lập nếu luôn kéo theo một vòng phụ thuộc.
- **Khó kiểm thử và bảo trì:** nhóm phát triển khó xác định module nào nên sở hữu API, dữ liệu hoặc quy tắc nghiệp vụ chung.

Vòng phụ thuộc thường là dấu hiệu cần xem lại cách chia module và hướng phụ thuộc của các abstraction.

## 5. Phân biệt module cycle với các loại vòng tham chiếu khác

Không phải mọi quan hệ hai chiều trong code đều là lỗi vòng phụ thuộc JPMS.

### 5.1. Hai class tham chiếu lẫn nhau

Ví dụ hai class cùng nằm trong một module:

~~~java
package com.example.order;

public class Order {
    private Customer customer;
}
~~~

~~~java
package com.example.order;

public class Customer {
    private Order latestOrder;
}
~~~

Hai class có thể tham chiếu kiểu của nhau. Đây là quan hệ ở cấp type trong cùng module, không tạo ra hai cạnh `requires` giữa các module.

### 5.2. Hai package tham chiếu lẫn nhau

Hai package trong cùng một module có thể chứa class sử dụng kiểu của nhau. Package không phải là đơn vị module độc lập trong JPMS, nên quan hệ này tự nó không tạo module cycle.

Dù vậy, tham chiếu hai chiều ở cấp package có thể làm code khó tổ chức. Có thể xem xét tách interface, gom các kiểu liên quan hoặc điều chỉnh trách nhiệm nếu việc phụ thuộc qua lại làm thiết kế khó hiểu.

### 5.3. Hai named module có requires lẫn nhau

Đây mới là vòng phụ thuộc ở cấp JPMS:

~~~java
// module A
module com.example.a {
    requires com.example.b;
}
~~~

~~~java
// module B
module com.example.b {
    requires com.example.a;
}
~~~

Chu trình này không hợp lệ khi resolve module graph.

### 5.4. Vòng phụ thuộc giữa Gradle/Maven projects

Gradle project hoặc Maven module cũng có dependency graph riêng. Nếu project A cần project B và project B lại cần project A, build tool có thể gặp chu trình task hoặc lỗi cấu hình dependency.

Đây là tầng build, độc lập với JPMS:

- Gradle/Maven quản lý artifact, project dependency và thứ tự task.
- JPMS quản lý readability giữa các named module và quyền truy cập package.

Một dự án có thể gặp cả hai loại vòng phụ thuộc, nhưng sửa một tầng không tự động sửa tầng còn lại. Hãy kiểm tra cả `build.gradle`/`pom.xml` và `module-info.java` nếu lỗi xuất hiện trong dự án modular dùng nhiều project build.

## 6. Các nguyên nhân thường dẫn đến module cycle

### 6.1. Chia module theo nhóm class thay vì theo trách nhiệm

Ví dụ module order giữ quy tắc nghiệp vụ nhưng lại cần class cụ thể của payment; payment cũng cần gọi trực tiếp class của order. Hai module bị gắn chặt vào nhau.

Cách xử lý là xác định abstraction chung hoặc hợp đồng giao tiếp, sau đó để hai bên phụ thuộc theo một hướng rõ ràng.

### 6.2. Đặt API dùng chung trong một module đang phụ thuộc ngược

Ví dụ `com.example.order` chứa interface `PaymentGateway`, nhưng module payment lại cần API của order trong khi order cũng cần implementation payment. Khi cả API và implementation nằm chung trong module order, việc chia module có thể tạo chu trình.

Có thể tách interface thành module API độc lập:

~~~text
com.example.payment.api
       ▲             ▲
       │             │
       │             │
com.example.order   com.example.payment.impl
~~~

Module order và implementation cùng phụ thuộc vào API; API không phụ thuộc ngược vào hai module còn lại.

### 6.3. Dùng class implementation trực tiếp thay vì interface

Nếu module A cần tạo hoặc gọi class nội bộ của B, còn B cần class nội bộ của A, hai bên dễ hình thành quan hệ `requires` hai chiều.

Hãy cân nhắc để module sở hữu hợp đồng công bố interface, còn module khác phụ thuộc vào hợp đồng đó. Việc khởi tạo implementation có thể được thực hiện ở composition root hoặc qua service loader.

### 6.4. Thêm requires theo lỗi biên dịch mà không xem lại đồ thị

Khi gặp lỗi không đọc được module hoặc package, thêm một directive `requires` có thể làm một lỗi biến mất nhưng tạo cạnh mới trong đồ thị. Nếu cạnh đó hoàn tất một đường quay về module ban đầu, lỗi cycle sẽ xuất hiện.

Trước khi thêm `requires`, hãy hỏi:

- Module hiện tại cần API nào?
- API đó thuộc module nào?
- Có đang phụ thuộc vào implementation thay vì abstraction không?
- Dependency này có thể được chuyển về một module API dùng chung không?

### 6.5. Nhầm requires transitive hoặc requires static là cách phá chu trình

`requires transitive` thay đổi cách dependency được truyền tới module tiêu thụ; nó vẫn là một cạnh phụ thuộc trong module graph. Nó không xóa chu trình.

`requires static` cho phép một dependency compile-time không bắt buộc phải hiện diện ở runtime trong một số tình huống. Nó cũng không phải công cụ để hợp thức hóa một đồ thị `requires` có chu trình. Nếu hai module cần nhau ở compile time, đổi một cạnh thành `static` không giải quyết thiết kế phụ thuộc vòng.

## 7. Cách phá vòng phụ thuộc

Mục tiêu là làm cho module graph trở thành đồ thị có hướng không chu trình, đồng thời giữ được trách nhiệm nghiệp vụ rõ ràng.

### 7.1. Tách module API hoặc contract dùng chung

Đây là cách phổ biến khi hai module cùng cần một số interface, DTO hoặc kiểu hợp đồng.

Trước khi tách:

~~~text
order <──────────────> payment
       requires hai chiều
~~~

Sau khi tách:

~~~text
        payment-api
          ▲     ▲
          │     │
          │     │
        order  payment-impl
~~~

Ví dụ:

~~~java
// module com.example.payment.api
module com.example.payment.api {
    exports com.example.payment.api;
}
~~~

~~~java
// module com.example.order
module com.example.order {
    requires com.example.payment.api;
}
~~~

~~~java
// module com.example.payment.impl
module com.example.payment.impl {
    requires com.example.payment.api;
}
~~~

Module API chỉ chứa hợp đồng cần chia sẻ. Nó không nên phụ thuộc ngược vào order hoặc payment implementation; nếu không, chu trình có thể chỉ chuyển sang một vị trí khác.

### 7.2. Dùng dependency inversion

Module nghiệp vụ nên phụ thuộc vào interface mô tả điều nó cần. Implementation nằm ở module khác và thực hiện interface đó.

Ví dụ module order định nghĩa cổng thanh toán:

~~~java
package com.example.order.spi;

public interface PaymentPort {
    void charge(String orderId);
}
~~~

Descriptor của order:

~~~java
module com.example.order {
    exports com.example.order.spi;
}
~~~

Module payment implementation phụ thuộc vào API của order:

~~~java
module com.example.payment.impl {
    requires com.example.order;

    provides com.example.order.spi.PaymentPort
        with com.example.payment.impl.CardPaymentAdapter;
}
~~~

Module order không cần `requires com.example.payment.impl`. Nó chỉ biết interface `PaymentPort`; implementation được tìm thông qua service loader hoặc được inject từ composition root.

Module order có thể khai báo sử dụng service:

~~~java
module com.example.order {
    exports com.example.order.spi;
    uses com.example.order.spi.PaymentPort;
}
~~~

Trong trường hợp này, quan hệ phụ thuộc một chiều từ payment implementation tới API order. Nếu cần tách service contract độc lập hơn, có thể đưa interface vào module API riêng để cả consumer và provider cùng phụ thuộc vào module đó.

### 7.3. Dùng module composition hoặc application module

Một module ở tầng ứng dụng có thể kết nối các module nghiệp vụ:

~~~text
             application
              /       \
             ▼         ▼
           order     payment
             \         /
              ▼       ▼
              shared-api
~~~

Application module chịu trách nhiệm lắp ráp implementation và cấu hình hệ thống. Các module nghiệp vụ không cần biết trực tiếp implementation của nhau.

Cách này phù hợp khi một luồng nghiệp vụ cần phối hợp nhiều capability. Tầng composition có thể phụ thuộc vào cả hai bên mà không tạo dependency ngược giữa chúng.

### 7.4. Gộp module khi ranh giới không có ý nghĩa độc lập

Nếu hai nhóm code luôn thay đổi cùng nhau, dùng chung nhiều chi tiết nội bộ và không có API ổn định giữa chúng, việc tách thành hai named module có thể không đem lại lợi ích.

Có thể gộp chúng vào một module, rồi tiếp tục tổ chức bằng package và encapsulation ở cấp Java. Không cần tạo một module cho mỗi package hoặc mỗi nhóm class.

## 8. Quy trình chẩn đoán lỗi resolve

Khi gặp lỗi resolve module, hãy xử lý theo thứ tự sau.

### Bước 1: Xác định giai đoạn lỗi

Ghi nhận lỗi xảy ra khi:

- Biên dịch bằng `javac`.
- Chạy ứng dụng bằng `java`.
- Đóng gói modular JAR.
- Chạy task Gradle/Maven.
- Khởi tạo ứng dụng trong IDE hoặc framework.

Giai đoạn phát hiện giúp khoanh vùng cấu hình đang được sử dụng. Build có thể compile thành công nhưng runtime dùng module path khác và gặp lỗi.

### Bước 2: Đọc tên module trong thông báo lỗi

Tìm các tên module được nhắc tới. Nếu lỗi chỉ ra một chuỗi module, ghi lại từng module và đường phụ thuộc giữa chúng.

Không chỉ sửa module xuất hiện đầu tiên trong log; hãy xác định cạnh nào đóng chu trình.

### Bước 3: Kiểm tra các module descriptor

Tìm toàn bộ directive `requires` liên quan trong các `module-info.java`. Vẽ lại quan hệ thành sơ đồ có hướng.

Ví dụ:

~~~text
A -> B
B -> C
C -> A
~~~

Chuỗi trên cho thấy chu trình A-B-C-A. Hãy kiểm tra cả `requires transitive` và `requires static`, vì chúng vẫn thể hiện quan hệ dependency trong descriptor.

### Bước 4: Kiểm tra tên module và module path

Một số lỗi resolve không phải cycle mà do module không được tìm thấy hoặc tên không khớp.

Có thể dùng:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Lệnh này cho biết tên module mà JAR công bố hoặc tên automatic module được suy ra. So sánh với tên trong directive `requires`.

Kiểm tra module path được truyền cho compiler/runtime:

~~~bash
javac --module-path libs -d out --module com.example.app
~~~

~~~bash
java --module-path out:libs -m com.example.app/com.example.app.Main
~~~

Trên Windows, dấu phân cách nhiều đường dẫn là dấu chấm phẩy thay vì dấu hai chấm. Cú pháp cụ thể cũng có thể khác theo shell và công cụ build.

### Bước 5: Quan sát quá trình resolve lúc chạy

Có thể yêu cầu JVM hiển thị các module được phân giải:

~~~bash
java --show-module-resolution --module-path out:libs -m com.example.app/com.example.app.Main
~~~

Thông tin này giúp xác nhận module nào được tìm thấy, module nào được yêu cầu và module graph runtime được dựng từ các vị trí nào.

### Bước 6: Kiểm tra lỗi khác sau khi đã xử lý cycle

Khi chu trình được phá, có thể lộ ra lỗi độc lập khác:

- `Module ... not found`: thiếu module trên module path hoặc tên module không khớp.
- `Package ... is not visible`: module hiện tại chưa đọc module chứa package đó hoặc package không được export phù hợp.
- `module ... does not read ...`: thiếu quan hệ readability.
- `Package ... is declared in module ...` hoặc thông báo split package: nhiều module cùng chứa package gây xung đột trong module graph.
- `Module ... not in graph`: module đích chưa được resolve hoặc chưa được đưa vào cấu hình phù hợp.
- Lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`: có thể liên quan đến classpath/module path hoặc dependency runtime; cần kiểm tra riêng sau khi module graph hợp lệ.

Không nên xử lý tất cả thông báo bằng cách thêm `requires` hoặc mở package hàng loạt. Mỗi lỗi tương ứng với một loại quan hệ khác nhau.

## 9. Các công cụ hỗ trợ kiểm tra

Một số lệnh hữu ích khi điều tra module:

~~~bash
# Xem descriptor của một modular JAR hoặc tên automatic module
jar --describe-module --file path/to/library.jar

# Hiển thị dependency module được suy ra từ class/JAR
jdeps --module-path libs --check com.example.app

# Hiển thị module resolution khi chạy
java --show-module-resolution --module-path out:libs -m com.example.app/com.example.app.Main
~~~

Ý nghĩa:

- `jar --describe-module` giúp xác nhận tên module và các directive được đóng gói trong JAR.
- `jdeps` hỗ trợ phân tích dependency giữa các class/package/module; tùy phiên bản JDK và tùy chọn, nó có thể chỉ ra dependency cần xem xét.
- `--show-module-resolution` cho biết JVM đã resolve module nào khi khởi chạy.

Với Gradle, cũng cần xem dependency graph của project:

~~~bash
./gradlew :app:dependencies
~~~

Nếu nghi ngờ vòng dependency ở cấp project hoặc task, kiểm tra thêm các project dependency và task graph. Đừng nhầm kết quả của dependency report Gradle với module graph JPMS; chúng là hai mô hình khác nhau.

## 10. Những cách sửa nên tránh

- **Thêm `requires` hai chiều để làm compiler hết báo lỗi:** có thể tạo cycle hoặc làm module phụ thuộc chặt hơn.
- **Đổi sang `requires transitive` để che lỗi:** modifier này lan truyền readability, không loại bỏ cạnh phụ thuộc.
- **Đổi sang `requires static` với hy vọng bỏ cycle:** dependency compile-time vẫn cần được phân giải; đây không phải cách sửa đồ thị.
- **Đưa mọi class vào một module chung không có API rõ ràng:** có thể tránh cycle trước mắt nhưng làm mất ranh giới trách nhiệm.
- **Dùng `--add-reads` hoặc `--add-exports` như giải pháp kiến trúc lâu dài:** các tùy chọn này có thể hỗ trợ kiểm tra hoặc tương thích trong tình huống đặc biệt, nhưng không sửa quan hệ `requires` vòng.
- **Đổi tất cả JAR sang classpath:** có thể né một số kiểm tra JPMS nhưng làm mất encapsulation và tính minh bạch của module graph. Chỉ nên thay đổi mô hình chạy khi đó là quyết định kiến trúc có chủ đích.

## 11. Tự kiểm tra

Khi xử lý một lỗi resolve liên quan đến module, hãy tự trả lời:

1. Những module nào xuất hiện trong thông báo lỗi?
2. Mỗi module khai báo những directive `requires` nào?
3. Có đường phụ thuộc nào quay lại module bắt đầu không?
4. Chu trình nằm trong JPMS module graph, Gradle/Maven project graph hay cả hai?
5. Hai module có đang tham chiếu implementation của nhau thay vì một contract ổn định không?
6. Có thể tách API chung, đảo chiều dependency bằng interface/SPI hoặc chuyển việc kết nối lên application module không?
7. Sau khi thay đổi descriptor, compiler và runtime có cùng nhìn thấy một module path hợp lệ không?

Vòng phụ thuộc module là vấn đề về cấu trúc dependency. Cách xử lý bền vững là tìm đúng chu trình, xác định abstraction hoặc trách nhiệm đang bị đặt sai chỗ, rồi thiết kế lại hướng phụ thuộc để mỗi module có thể được resolve độc lập theo một đồ thị không chu trình.
