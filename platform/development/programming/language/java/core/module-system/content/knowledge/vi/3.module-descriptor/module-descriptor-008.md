# Kiểm tra descriptor trước khi phát hành module

## 1. Vì sao cần kiểm tra module descriptor?

Trong JPMS (Java Platform Module System), `module-info.java` là hợp đồng mô tả một module: tên module, dependency mà module đọc, package được công bố, package mở cho reflection và các dịch vụ mà module sử dụng hoặc cung cấp.

Một descriptor có thể biên dịch thành công nhưng vẫn chưa phù hợp để phát hành. Ví dụ:

- Khai báo `requires` thiếu dependency cần thiết hoặc giữ lại dependency không còn dùng.
- API public trả về kiểu của một module khác nhưng dependency đó chưa được khai báo `requires transitive`.
- Package nội bộ bị export rộng ngoài ý muốn.
- Framework cần reflection sâu nhưng package tương ứng chưa được `opens`.
- Tên module trong descriptor không khớp với tên mà ứng dụng tiêu thụ đang yêu cầu.
- JAR phát hành không chứa đúng `module-info.class` hoặc nội dung được build không khớp với cấu hình đã kiểm tra.

Kiểm tra trước khi phát hành giúp phát hiện các vấn đề này ở thời điểm build và thử nghiệm, thay vì để người dùng gặp lỗi khi tích hợp thư viện.

## 2. Kiểm tra cấu trúc và tên module

Một explicit named module có file `module-info.java` tại gốc source module. Sau khi biên dịch, file tương ứng `module-info.class` nằm ở gốc output module hoặc gốc modular JAR.

Ví dụ cấu trúc:

~~~text
customer-module/
  src/
    module-info.java
    com/
      acme/
        customer/
          api/
            Customer.java
          internal/
            CustomerRepositoryImpl.java
  build/
    classes/
      module-info.class
      com/
        acme/
          customer/
            api/
            internal/
~~~

Descriptor tối giản:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Khi kiểm tra tên module:

- Dùng tên ổn định, dễ nhận diện và theo quy ước reverse-domain, ví dụ `com.acme.customer`.
- Không dùng namespace dành cho nền tảng Java như `java.*` cho module của ứng dụng.
- Kiểm tra mọi chỉ thị `requires`, `exports ... to`, `opens ... to`, `uses` và `provides` tham chiếu đúng tên module hoặc service.
- Nếu thư viện cần hỗ trợ cả classpath và module path, cân nhắc giữ tên module ổn định trong các bản phát hành; đổi tên module là thay đổi ảnh hưởng trực tiếp tới người tiêu thụ đang khai báo `requires`.

Tên module là một phần của hợp đồng tích hợp. Không nên để tên module vô tình thay đổi theo tên file JAR nếu người dùng cần phụ thuộc lâu dài vào tên đó.

## 3. Kiểm tra dependency và readability

Mỗi `requires` cần tương ứng với dependency thực sự của module. Đọc lại mã nguồn và public API để xác định module cần đọc:

~~~java
module com.acme.customer {
    requires java.sql;
    requires com.acme.logging;

    exports com.acme.customer.api;
}
~~~

Một số điểm cần rà soát:

- Dependency được dùng trực tiếp trong mã nguồn phải có mặt trong cấu hình compile.
- Dependency cần thiết khi chạy phải có mặt trong runtime image hoặc runtime module path.
- Không giữ các `requires` không còn cần thiết nếu chúng làm tăng ràng buộc phát hành.
- `java.base` được mọi named module đọc ngầm; không cần khai báo `requires java.base`.
- Module có thể đọc dependency gián tiếp qua `requires transitive`, nhưng nên khai báo trực tiếp dependency mà mã nguồn của module thực sự sử dụng để hợp đồng dễ hiểu và bền vững.

### Khi nào dùng requires transitive?

Nếu API public của module để lộ kiểu từ dependency khác, người dùng API có thể cần đọc dependency đó để biên dịch. Khi đó xem xét:

~~~java
module com.acme.customer {
    requires transitive com.acme.domain;
    exports com.acme.customer.api;
}
~~~

Ví dụ API:

~~~java
package com.acme.customer.api;

import com.acme.domain.CustomerId;

public interface CustomerService {
    CustomerId findCustomer(String value);
}
~~~

Module tiêu thụ chỉ khai báo `requires com.acme.customer` vẫn có readability tới `com.acme.domain` nhờ `requires transitive`. Chỉ dùng modifier này khi dependency thực sự xuất hiện trong hợp đồng API công khai; dependency chỉ dùng nội bộ thường nên là `requires` thông thường.

### Khi nào dùng requires static?

~~~java
module com.acme.customer {
    requires static com.acme.annotations;
}
~~~

`requires static` yêu cầu dependency ở compile time nhưng cho phép nó vắng mặt ở runtime. Hãy xác nhận mã chạy không thực sự cần lớp của dependency khi module đó vắng mặt. Nếu runtime path có dùng lớp ấy, dependency phải được cung cấp ở runtime; chỉ khai báo `requires static` không tự tạo implementation thay thế.

## 4. Kiểm tra exports và ranh giới API

Trong explicit named module, package không được công bố mặc định. Chỉ export package thuộc API mà người dùng module cần truy cập.

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Trước khi phát hành, kiểm tra:

- Package được export có thực sự chứa API được hỗ trợ không?
- Các package `internal`, `impl`, `spi` hoặc package chỉ phục vụ triển khai có đang bị export ngoài ý muốn không?
- API public có dùng kiểu thuộc package hoặc module khác mà người tiêu thụ không thể truy cập không?
- Có thể dùng qualified export để giới hạn quyền cho module tiêu thụ cụ thể không?

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.spi to com.acme.integration;
}
~~~

`exports com.acme.customer.api` cho phép mọi module đọc module customer truy cập các kiểu public trong package API. Qualified export chỉ công bố package cho những module được liệt kê.

Export package không làm mọi thành viên trở thành public. Quy tắc truy cập Java thông thường vẫn có hiệu lực. Ngược lại, package không export vẫn có thể chứa lớp được dùng nội bộ bên trong module.

## 5. Kiểm tra opens và nhu cầu reflection

Framework persistence, dependency injection, serialization hoặc binding có thể cần reflection sâu để truy cập constructor hay field không public. Khi đó cần mở đúng package cho đúng module.

~~~java
module com.acme.customer {
    requires com.acme.persistence;

    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.persistence;
}
~~~

Phân biệt:

- `exports` cho phép mã Java của module khác truy cập các kiểu public trong package.
- `opens` cho phép reflection sâu trên package ở runtime.
- `opens package to module` giới hạn quyền reflection cho module được chỉ định.
- `open module` mở tất cả package của module cho reflection sâu.

Không cần mở toàn bộ module nếu framework chỉ truy cập một package. Ngoài ra, một module được khai báo bằng `open module` không được đồng thời chứa các chỉ thị `opens` riêng trong descriptor. Nếu cần kiểm soát theo package, dùng khai báo `module` thông thường với các chỉ thị `opens` có chọn lọc.

Hãy thử đúng framework và cấu hình runtime dự kiến phát hành. Kiểm tra compile thành công không chứng minh reflection sẽ hoạt động khi chạy.

## 6. Kiểm tra uses và provides nếu module dùng ServiceLoader

JPMS hỗ trợ khai báo quan hệ dịch vụ trong module descriptor.

Module tiêu thụ dịch vụ khai báo `uses`:

~~~java
module com.acme.application {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

Module cung cấp implementation khai báo `provides ... with ...`:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

Trước khi phát hành, kiểm tra:

- Service type có phải đúng kiểu mà module tiêu thụ dùng không?
- Provider implementation có tồn tại trong module cung cấp không?
- Provider đáp ứng quy tắc khởi tạo của `ServiceLoader` (public no-argument constructor hoặc public static method tên `provider` với chữ ký phù hợp) không?
- Module provider và module consumer có nằm trong cấu hình runtime/layer mà ứng dụng sử dụng không?
- Có thử gọi `ServiceLoader.load(...)` trong một bài chạy tích hợp thực tế không?

Package chứa provider implementation không nhất thiết phải export chỉ để `ServiceLoader` tìm provider. Hãy export service API ở module sở hữu API, và chỉ export package implementation nếu có nhu cầu truy cập trực tiếp khác.

## 7. Biên dịch và kiểm tra descriptor

Có thể biên dịch module bằng `javac` với module source path:

~~~bash
javac -d mods --module-source-path src -m com.acme.customer
~~~

Nếu module được biên dịch riêng từ một thư mục source đã xác định:

~~~bash
javac -d out/customer-module \
  src/customer-module/module-info.java \
  src/customer-module/com/acme/customer/api/Customer.java
~~~

Trong dự án Gradle hoặc Maven, ưu tiên task build chính thức của dự án vì task đó còn áp dụng đúng dependency, compiler options, toolchain và quy trình đóng gói. Kiểm tra rằng build đang dùng JDK và target release mà dự án công bố hỗ trợ.

Sau khi biên dịch, xem descriptor của output module:

~~~bash
jar --describe-module --file build/libs/customer-module.jar
~~~

Lệnh này cho biết tên module, các package, dependency và các chỉ thị module mà JAR cung cấp. Đối chiếu kết quả với `module-info.java` và hợp đồng dự kiến.

Có thể liệt kê nội dung JAR để xác nhận descriptor nằm đúng vị trí:

~~~bash
jar --list --file build/libs/customer-module.jar
~~~

Với modular JAR, cần thấy `module-info.class` ở gốc archive. Nếu JAR không chứa descriptor, Java có thể nhận diện nó theo cách khác khi đặt trên module path.

## 8. Dùng jdeps và module resolution để phát hiện vấn đề

`jdeps` giúp phân tích dependency mà bytecode thực tế sử dụng. Với module đã biên dịch, có thể kiểm tra descriptor và dependency như sau:

~~~bash
jdeps --check com.acme.customer --module-path mods
~~~

Lệnh này hỗ trợ kiểm tra module descriptor so với dependency được phát hiện, đồng thời đưa ra gợi ý khi quan hệ module chưa được khai báo phù hợp. Đọc cảnh báo và đánh giá theo API mà module muốn công bố; không tự động biến mọi dependency được phát hiện thành `requires transitive`.

Để xem các module được phân giải lúc chạy:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.application/com.acme.application.Main
~~~

Để yêu cầu runtime kiểm tra các module trên module path:

~~~bash
java --module-path mods --validate-modules
~~~

Khi chạy các lệnh này, hãy dùng cùng module path và các module artifact như cấu hình phát hành. Nếu chỉ kiểm tra trên thư mục build tạm thời, kết quả có thể khác với JAR đã upload hoặc image được triển khai.

## 9. Kiểm tra chính artifact sẽ phát hành

Một descriptor đúng trong source chưa bảo đảm JAR cuối cùng chứa đúng descriptor. Hãy kiểm tra artifact sau khi đóng gói:

1. Xác nhận build hoàn tất và JAR được tạo ở đúng đường dẫn.
2. Dùng `jar --describe-module` để đọc tên và descriptor từ chính JAR đó.
3. Dùng `jar --list` để kiểm tra `module-info.class` và các package/class được đóng gói.
4. Kiểm tra không có package nội bộ bị export ngoài ý muốn.
5. Chạy ứng dụng tiêu thụ hoặc một module thử nghiệm nhỏ trên module path chỉ với các dependency phát hành.
6. Nếu module dùng reflection, chạy thử framework thật để xác nhận `opens` đúng.
7. Nếu module dùng `ServiceLoader`, kiểm tra cả discovery lẫn khởi tạo provider.
8. Lặp lại kiểm tra sau khi thay đổi build script, compiler version hoặc quy trình shading/relocation JAR.

Đặc biệt lưu ý quy trình tạo fat JAR hoặc shading. Nếu công cụ đóng gói gộp nhiều module thành một JAR classpath, kết quả có thể không còn giữ nguyên ranh giới JPMS. Chỉ phát hành modular JAR khi artifact cuối cùng thực sự bảo toàn cấu trúc module đã thiết kế.

## 10. Kiểm tra tương thích trước khi đổi descriptor

Descriptor là một phần của API module. Một thay đổi tưởng như nhỏ cũng có thể ảnh hưởng tới người tiêu thụ:

- Đổi tên module làm hỏng các khai báo `requires` đang dùng tên cũ.
- Bỏ một package khỏi `exports` có thể khiến mã consumer không biên dịch hoặc không truy cập được API.
- Bỏ một dependency khỏi `requires transitive` có thể làm consumer mất readability tới kiểu xuất hiện trong API.
- Thu hẹp qualified exports có thể chặn một module tích hợp đã được hỗ trợ.
- Bỏ `opens` có thể khiến framework lỗi ở runtime dù mã ứng dụng vẫn biên dịch.
- Bỏ `uses` hoặc `provides` có thể làm service discovery không tìm thấy implementation.

Vì vậy, hãy kiểm tra descriptor cùng với kiểm thử consumer: biên dịch một module khác chỉ phụ thuộc vào API được công bố, chạy ứng dụng trên module path, và thử các đường reflection/service mà thư viện cam kết hỗ trợ.

## 11. Checklist phát hành

Trước khi gắn nhãn hoặc upload artifact, có thể dùng checklist ngắn sau:

- [ ] Tên module ổn định và khớp với tên trong tài liệu tích hợp.
- [ ] `module-info.class` có trong JAR cuối cùng ở đúng vị trí.
- [ ] Mọi `requires` cần thiết đều có mặt; dependency không còn dùng đã được xem xét loại bỏ.
- [ ] `requires transitive` chỉ áp dụng cho dependency thực sự xuất hiện trong API công khai.
- [ ] `requires static` không che giấu dependency bắt buộc ở runtime.
- [ ] `exports` chỉ công bố các package thuộc API được hỗ trợ.
- [ ] `opens` chỉ mở các package cần reflection và đúng module tiêu thụ.
- [ ] `uses` và `provides` khớp với service/provider thực tế nếu có dùng ServiceLoader.
- [ ] `jar --describe-module`, `jdeps --check` và kiểm tra module resolution đã được chạy trên artifact phát hành.
- [ ] Một consumer độc lập đã biên dịch và chạy được bằng module path thực tế.

## Kết luận

Kiểm tra descriptor trước khi phát hành cần nhìn cả ba lớp: cấu trúc module, hợp đồng truy cập và artifact được đóng gói. `module-info.java` phải mô tả đúng dependency, package API, nhu cầu reflection và dịch vụ; JAR cuối cùng phải giữ nguyên descriptor đó; ứng dụng tiêu thụ phải biên dịch và chạy được trong cấu hình module thực tế.

Khi kiểm tra bằng `jar --describe-module`, `jdeps --check`, `java --validate-modules` và một consumer độc lập, nhóm phát triển có bằng chứng cụ thể rằng module đã sẵn sàng để tích hợp.