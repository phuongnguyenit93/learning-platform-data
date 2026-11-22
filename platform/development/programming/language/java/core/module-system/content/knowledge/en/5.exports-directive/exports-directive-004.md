# Exports type public và điều kiện truy cập

## 1. exports kiểm soát điều gì?

Trong Java Platform Module System (JPMS), một module có thể chứa nhiều package phục vụ các mục đích khác nhau: API dành cho người dùng, phần triển khai nội bộ, adapter, helper và mã kiểm thử. Nếu module không có ranh giới truy cập, người dùng dễ phụ thuộc trực tiếp vào các lớp triển khai mà tác giả module muốn giữ kín.

Chỉ thị **exports** trong module descriptor xác định package nào được công khai để module khác truy cập theo quy tắc Java thông thường.

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Khai báo này cho phép các module đọc được com.acme.customer truy cập những kiểu public thuộc package com.acme.customer.api, đồng thời giữ các package khác của module ở trạng thái đóng đối với truy cập Java thông thường từ bên ngoài.

Một số điểm cần nhớ:

- exports áp dụng cho **toàn bộ package**, không chọn riêng từng class hoặc method.
- Chỉ thị exports không tự biến class hay member thành public.
- Module sử dụng package vẫn phải có quyền đọc module cung cấp package đó.
- Các quy tắc truy cập của ngôn ngữ Java như public, protected, package-private và private vẫn được áp dụng.
- Package con là package riêng. Export com.acme.customer.api không tự export com.acme.customer.api.internal.

Vì vậy, exports là một phần của hợp đồng API ở cấp module. Nó xác định bề mặt package mà module cho phép module khác sử dụng.

## 2. Điều kiện để truy cập một type public

Để mã trong module A sử dụng một type public thuộc package của module B, các điều kiện chính phải đồng thời thỏa mãn:

1. **Module B được phân giải trong cấu hình hiện tại**: module cung cấp phải hiện diện trong cấu hình module của ứng dụng.
2. **Module A đọc được module B**: thường được khai báo bằng requires trong module-info.java của A; quan hệ đọc cũng có thể đến từ requires transitive hoặc các tùy chọn bổ sung khi chạy.
3. **Package chứa type được export tới A**: B phải export package đó không hạn chế hoặc export có giới hạn tới chính module A.
4. **Type và thành viên cần dùng có mức truy cập phù hợp**: type phải public; constructor, method hoặc field phải cho phép truy cập theo quy tắc Java.
5. **Các điều kiện ngôn ngữ khác đều hợp lệ**: kiểu tham số, kiểu trả về, kiểu bao ngoài, kế thừa và các quy tắc truy cập protected cũng phải hợp lệ.

Có thể hình dung quan hệ này như sau:

~~~text
Module A (consumer)
    |
    | requires com.acme.customer
    v
Module B (provider)
    |
    | exports com.acme.customer.api
    v
Package com.acme.customer.api
    |
    | public type + public member
    v
Mã của module A được phép sử dụng API
~~~

Chỉ có requires là chưa đủ nếu package không được export. Ngược lại, package được export cũng chưa đủ nếu module sử dụng không đọc module cung cấp.

## 3. Ví dụ một module có API public và phần triển khai nội bộ

Giả sử thư viện quản lý khách hàng có cấu trúc:

~~~text
com.acme.customer/
├── module-info.java
└── com/
    └── acme/
        └── customer/
            ├── api/
            │   ├── Customer.java
            │   └── CustomerService.java
            └── internal/
                └── CustomerRepository.java
~~~

Module descriptor chỉ export package API:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Type public trong API:

~~~java
package com.acme.customer.api;

public record Customer(String id, String name) {
}
~~~

Service công khai:

~~~java
package com.acme.customer.api;

public class CustomerService {
    public Customer findById(String id) {
        return new Customer(id, "An");
    }
}
~~~

Một class triển khai nằm trong package internal:

~~~java
package com.acme.customer.internal;

public class CustomerRepository {
    public CustomerRepository() {
    }
}
~~~

Module ứng dụng khai báo phụ thuộc:

~~~java
module com.acme.application {
    requires com.acme.customer;
}
~~~

Và sử dụng API:

~~~java
package com.acme.application;

import com.acme.customer.api.Customer;
import com.acme.customer.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.findById("C-100");

        System.out.println(customer.name());
    }
}
~~~

Mã ứng dụng biên dịch được vì:

- com.acme.application đọc com.acme.customer thông qua requires.
- com.acme.customer export com.acme.customer.api.
- Customer và CustomerService là các type public.
- findById và name là các thành viên public có thể truy cập.

Nếu Main thử import com.acme.customer.internal.CustomerRepository, compiler sẽ từ chối vì package internal không được export. Việc class CustomerRepository được khai báo public không thay đổi kết quả này. Mức public của type không thể vượt qua ranh giới module do exports thiết lập.

## 4. exports không thay thế public và các mức truy cập Java

JPMS bổ sung ranh giới ở cấp module; nó không xóa bỏ hệ thống truy cập thành viên của Java.

| Mức truy cập | Ý nghĩa trong Java | Module khác truy cập qua package đã export? |
|---|---|---|
| public | Có thể truy cập từ nơi phù hợp theo quy tắc Java | Có, nếu type và các điều kiện module đều hợp lệ |
| protected | Truy cập trong package và theo quy tắc subclass | Chỉ trong các ngữ cảnh được Java cho phép |
| package-private | Chỉ trong cùng package | Không |
| private | Chỉ trong phạm vi class/nest được Java cho phép | Không |

Ví dụ:

~~~java
package com.acme.customer.api;

public class CustomerService {
    public Customer findById(String id) {
        return new Customer(id, "An");
    }

    protected void validateExtension() {
    }

    void resetCache() {
    }

    private void rebuildIndex() {
    }
}
~~~

Nếu package này được export:

- Module khách hàng khác có thể gọi findById trên một instance hợp lệ.
- validateExtension vẫn tuân theo quy tắc protected: mã ở package khác chỉ có thể truy cập trong ngữ cảnh subclass được Java cho phép.
- resetCache là package-private nên không thể gọi từ module khác.
- rebuildIndex là private nên không thể gọi trực tiếp từ bên ngoài class.

Tương tự, export một package không làm cho class package-private trong package đó trở thành public. Ví dụ sau vẫn không cho module ngoài package sử dụng InternalMapper:

~~~java
package com.acme.customer.api;

class InternalMapper {
}
~~~

Khi thiết kế API, hãy xác định rõ type và member nào thực sự là hợp đồng công khai. Tránh tăng mức truy cập chỉ để vượt qua lỗi biên dịch nếu type đó không dành cho người dùng thư viện.

## 5. Qualified exports: chỉ công khai cho module được chọn

Một module có thể export package cho tất cả module đọc nó hoặc chỉ cho một nhóm module có tên cụ thể.

Export không giới hạn:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Bất kỳ module nào đọc com.acme.customer đều có thể truy cập các type public trong package API theo quy tắc Java.

Qualified export:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.spi to
        com.acme.application,
        com.acme.integration;
}
~~~

Trong ví dụ này:

- com.acme.customer.api là API dành cho mọi module đọc thư viện.
- com.acme.customer.spi chỉ được export cho com.acme.application và com.acme.integration.
- Module khác có thể đọc com.acme.customer nhưng không được truy cập package SPI qua quy tắc truy cập thông thường.

Qualified exports hữu ích khi module có một API công khai rộng và một số điểm mở rộng dành riêng cho các module tích hợp đã biết.

Danh sách module đích phải dùng đúng tên module được khai báo trong descriptor của chúng. Nếu đổi tên module đích, qualified export cũng cần được cập nhật.

Qualified exports không tự tạo quan hệ đọc. Module đích vẫn cần đọc module nguồn, thường bằng requires. Việc export có giới hạn và việc đọc module là hai điều kiện độc lập.

## 6. Export package không tự động export package con

Trong Java, package không có quan hệ kế thừa truy cập theo cấu trúc tên. Package com.acme.customer.api và com.acme.customer.api.internal là hai package khác nhau.

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Khai báo trên chỉ export com.acme.customer.api. Nó không export:

- com.acme.customer.api.internal
- com.acme.customer.api.validation
- com.acme.customer.spi

Nếu muốn công khai thêm package, cần khai báo riêng:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.api.validation;
}
~~~

Không nên export toàn bộ package nội bộ chỉ vì chúng nằm bên dưới một package API. Việc export thêm một package tạo thêm bề mặt tương thích mà tác giả module phải cân nhắc khi thay đổi phiên bản thư viện.

## 7. exports và requires transitive có vai trò khác nhau

Hai chỉ thị này thường xuất hiện cùng nhau nhưng giải quyết hai vấn đề khác nhau:

- **exports** quyết định package nào của module hiện tại có thể được module khác truy cập.
- **requires transitive** truyền quan hệ đọc tới một module phụ thuộc cho các module đọc module hiện tại.

Ví dụ module API sử dụng type từ module model trong chữ ký public:

~~~java
module com.acme.customer.api {
    requires transitive com.acme.model;
    exports com.acme.customer.api;
}
~~~

Module ứng dụng chỉ cần khai báo:

~~~java
module com.acme.application {
    requires com.acme.customer.api;
}
~~~

Nhờ requires transitive, com.acme.application có quan hệ đọc tới com.acme.model và có thể làm việc với type được API công khai làm lộ ra, miễn là package tương ứng của com.acme.model cũng được export phù hợp.

Nếu chỉ viết exports com.acme.customer.api mà không có quan hệ đọc thích hợp tới com.acme.model, module sử dụng vẫn có thể gặp vấn đề khi cần tham chiếu type thuộc module model.

Một cách nhớ:

~~~text
exports
    -> Mở package của module hiện tại cho module khác.

requires transitive
    -> Truyền quan hệ đọc tới module phụ thuộc.
~~~

Không dùng requires transitive chỉ để “sửa cho biên dịch được”. Hãy dùng nó khi dependency thực sự xuất hiện trong API công khai hoặc người dùng API cần đọc module đó theo hợp đồng đã thiết kế.

## 8. exports và opens: truy cập API khác truy cập reflection sâu

exports dành cho truy cập Java thông thường vào các type public và các thành viên được phép. Nó cũng hỗ trợ reflection công khai đối với các thành viên public của type public trong package đã export.

Tuy nhiên, framework có thể cần reflection sâu để truy cập field private, constructor private hoặc method private. Trường hợp đó cần package được mở bằng opens.

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.internal to com.acme.persistence;
}
~~~

Khai báo trên có nghĩa:

- Module người dùng API có thể truy cập type public trong com.acme.customer.api.
- Module com.acme.persistence được phép thực hiện deep reflection vào package com.acme.customer.internal.
- Package internal vẫn không trở thành API Java thông thường cho mọi module.

Có thể mở package cho mọi module bằng:

~~~java
module com.acme.customer {
    opens com.acme.customer.internal;
}
~~~

Hoặc khai báo toàn module là open:

~~~java
open module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Một open module mở tất cả package của nó cho deep reflection ở thời điểm chạy. Trong module descriptor dạng open, không khai báo các chỉ thị opens riêng lẻ; nếu cần mở có giới hạn, dùng module thông thường với các dòng opens cụ thể.

| Chỉ thị | Truy cập Java thông thường | Deep reflection |
|---|---|---|
| exports | Cho phép theo mức public/protected của Java | Cho phép truy cập public thông thường |
| opens | Không cấp quyền import/gọi API như exports | Cho phép truy cập sâu trong package |
| open module | Không tự export package | Mở tất cả package cho deep reflection |

Nếu framework báo InaccessibleObjectException khi truy cập private member, hãy xem package đã được opens cho module framework chưa. Thêm exports thường không giải quyết được yêu cầu reflection sâu.

## 9. Bổ sung export khi chạy bằng dòng lệnh

Trong giai đoạn chuyển đổi hoặc khi cần chẩn đoán, Java launcher và compiler có các tùy chọn bổ sung export mà không cần sửa ngay module descriptor.

Ví dụ mở package API cho một module đích:

~~~bash
java --add-exports com.acme.customer/com.acme.customer.internal=com.acme.application \
     --module-path mods \
     --module com.acme.application/com.acme.application.Main
~~~

Cú pháp tổng quát:

~~~text
--add-exports source.module/package=target.module
~~~

Có thể dùng ALL-UNNAMED làm đích khi muốn export package cho các class thuộc unnamed module:

~~~bash
java --add-exports com.acme.customer/com.acme.customer.internal=ALL-UNNAMED \
     -cp app.jar \
     com.acme.legacy.Main
~~~

Đối với mã nguồn modular cần biên dịch trong môi trường tương ứng, javac cũng hỗ trợ --add-exports. Cấu hình bổ sung này nên được quản lý rõ ràng trong build hoặc launch configuration.

Các tùy chọn này hữu ích cho tương thích và chẩn đoán, nhưng nếu một package thực sự là API được hỗ trợ lâu dài, hãy khai báo nó trong module-info.java. Tránh để ứng dụng phụ thuộc vào package nội bộ của thư viện chỉ vì một tùy chọn dòng lệnh đã mở quyền truy cập.

Lưu ý: --add-exports chỉ mở truy cập Java thông thường cho package được chỉ định. Nó không thay thế --add-opens khi framework cần deep reflection vào thành viên private.

## 10. Cách kiểm tra một API có được export hay không

Khi một type public không thể được import từ module khác, hãy kiểm tra theo thứ tự:

1. **Tên module**: module descriptor của thư viện khai báo đúng tên mà module tiêu thụ dùng trong requires hay chưa?
2. **Module path**: module chứa type có được tìm thấy và phân giải trong lần biên dịch/chạy hiện tại không?
3. **Tên package**: package khai báo trong source có đúng package mà module descriptor export không?
4. **Kiểu export**: package được export không giới hạn hay qualified export chỉ tới một module khác?
5. **Quan hệ đọc**: module tiêu thụ có requires module cung cấp hoặc nhận được quan hệ đọc hợp lệ không?
6. **Mức truy cập Java**: type có public không, các type bao ngoài và constructor/member cần dùng có truy cập được không?
7. **Reflection**: nếu lỗi xảy ra trong framework khi truy cập private member, package có cần opens cho module framework không?

Có thể xem descriptor của một modular JAR:

~~~bash
jar --describe-module --file mods/com.acme.customer.jar
~~~

Đầu ra cho biết tên module, các package được export, các qualified export và các chỉ thị phụ thuộc. Đây là cách nhanh để xác nhận module đang phân phối có descriptor như dự kiến.

Có thể yêu cầu Java in module resolution khi chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.application/com.acme.application.Main
~~~

Kết quả này giúp xác nhận module nào tham gia cấu hình chạy. Nếu module cung cấp không xuất hiện, cần xem lại module root, requires và module path trước khi kết luận lỗi nằm ở exports.

## 11. Lỗi thường gặp và cách xử lý

**Package không được export**

Compiler có thể báo package không được export hoặc module không đọc được package. Kiểm tra module-info.java của module nguồn và bổ sung exports đúng package, đúng đối tượng nhận quyền nếu thiết kế yêu cầu.

**Type public nhưng vẫn không truy cập được**

Từ khóa public không vượt qua ranh giới module. Package chứa type phải được export tới module tiêu thụ, và module tiêu thụ phải đọc module nguồn.

**Qualified export trỏ sai module**

Nếu dòng exports package to module-name dùng sai tên, module cần truy cập sẽ không nhận được quyền. Đối chiếu tên trong module-info.java của module đích.

**Package con bị hiểu nhầm là đã export**

Export package cha không export package con. Khai báo riêng từng package thuộc API công khai.

**API public làm lộ type từ package nội bộ**

Một method public có thể trả về hoặc nhận tham số thuộc package không được export. Người dùng bên ngoài khó sử dụng đầy đủ hợp đồng đó. Hãy chuyển type cần công khai vào package API hoặc thiết kế lại chữ ký để không lộ chi tiết nội bộ.

**Framework không truy cập được private member**

exports không cấp quyền deep reflection. Mở đúng package bằng opens hoặc cấu hình tương đương cho module framework cần truy cập.

**Mở quá nhiều package**

Export hoặc open toàn bộ package nội bộ làm tăng bề mặt phụ thuộc và giảm khả năng thay đổi implementation. Chỉ export package thuộc hợp đồng API và chỉ opens cho framework thực sự cần reflection.

## 12. Nguyên tắc thiết kế API module

Khi thiết kế module, nên phân chia package theo vai trò:

~~~text
com.acme.customer/
├── com.acme.customer.api/          # Public API
├── com.acme.customer.spi/          # Extension point có kiểm soát
├── com.acme.customer.internal/     # Implementation
└── com.acme.customer.persistence/  # Chi tiết lưu trữ
~~~

Sau đó chỉ công khai các package cần thiết:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    exports com.acme.customer.spi to com.acme.application;
    opens com.acme.customer.persistence to com.acme.persistence;
}
~~~

Các nguyên tắc nên áp dụng:

- Giữ API công khai nhỏ, ổn định và có tài liệu.
- Dùng qualified exports khi chỉ một số module được phép tích hợp.
- Giữ package triển khai ở trạng thái không export.
- Không tăng mức truy cập Java chỉ để né lỗi module.
- Dùng opens riêng cho nhu cầu deep reflection, tránh mở toàn module nếu không cần.
- Khi API public làm lộ type của dependency khác, cân nhắc requires transitive dựa trên hợp đồng API.
- Kiểm tra module descriptor của artifact thực tế sau khi đóng gói.

Thiết kế như vậy giúp người dùng thư viện biết phần nào được hỗ trợ lâu dài, còn tác giả vẫn có thể thay đổi package và class triển khai nội bộ mà không phá vỡ API đã công bố.

## 13. Ghi nhớ

- exports công khai package ở cấp module; nó không tự biến type hoặc member thành public.
- Module tiêu thụ phải đọc module cung cấp và package phải được export tới module đó.
- Java access modifiers vẫn có hiệu lực: package-private và private không trở thành public nhờ exports.
- Qualified exports giới hạn package cho các module đích được chỉ định.
- Export package không tự export package con.
- requires transitive truyền quan hệ đọc; exports mở package của module hiện tại. Hai chỉ thị có vai trò riêng.
- opens dành cho deep reflection; exports không thay thế opens.
- Dùng jar --describe-module để xem descriptor và --show-module-resolution để quan sát cấu hình module khi chạy.

Khi gặp lỗi truy cập trong JPMS, hãy xác định đó là thiếu quan hệ đọc, thiếu export, mức truy cập Java không phù hợp hay thiếu opens cho reflection. Xử lý đúng điều kiện sẽ giữ API rõ ràng và tránh mở quyền truy cập rộng hơn nhu cầu.
