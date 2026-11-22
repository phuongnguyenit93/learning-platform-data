# Khai báo requires, exports, opens, uses và provides trong JPMS

JPMS (Java Platform Module System) là hệ thống mô-đun được đưa vào Java 9 và vẫn là một phần của nền tảng Java hiện hành. Mỗi named module mô tả tên mô-đun, các phụ thuộc và những phần API mà nó cho phép mô-đun khác sử dụng. Những khai báo này được đặt trong tệp **module-info.java** ở thư mục gốc của mô-đun nguồn.

Bài học tập trung vào năm directive thường gặp: **requires**, **exports**, **opens**, **uses** và **provides**. Chúng quyết định mô-đun có thể đọc mô-đun nào, package nào được công khai, package nào được phép truy cập bằng reflection và cách các mô-đun trao đổi dịch vụ.

## 1. Cấu trúc của module-info.java

Một module descriptor có dạng tổng quát:

~~~java
module com.example.orders {
    requires com.example.common;
    exports com.example.orders.api;
    opens com.example.orders.model to com.example.orm;
}
~~~

- **module com.example.orders** khai báo tên mô-đun. Tên này phải duy nhất trong cấu hình mô-đun đang chạy.
- **requires** khai báo mô-đun mà mô-đun hiện tại cần đọc.
- **exports** công khai một package để mô-đun đọc nó có thể dùng các kiểu public trong package đó.
- **opens** cho phép truy cập bằng reflection vào các kiểu và thành viên trong package, kể cả thành viên không public, theo phạm vi được khai báo.

Mỗi named module có một module descriptor. Khi biên dịch, descriptor trở thành **module-info.class**. Một ứng dụng chạy trên classpath và thuộc unnamed module không có module descriptor như vậy.

Mô-đun **java.base** được yêu cầu ngầm định bởi mọi named module. Vì vậy không cần viết **requires java.base;** trong module-info.java.

Để hiểu các directive, cần phân biệt hai câu hỏi:

1. Mô-đun hiện tại có quyền đọc kiểu được khai báo trong mô-đun khác không?
2. Package chứa kiểu đó có được mô-đun sở hữu công khai hoặc mở cho bên cần truy cập không?

**requires** giải quyết khả năng đọc mô-đun. **exports** và **opens** giải quyết quyền truy cập vào package. Có **requires** chưa có nghĩa là mọi package của mô-đun phụ thuộc đều có thể được sử dụng.

## 2. Directive requires

**requires** tạo quan hệ phụ thuộc và cho phép mô-đun hiện tại đọc một mô-đun khác. Nếu mã nguồn sử dụng một kiểu thuộc mô-đun khác, thông thường mô-đun hiện tại phải có **requires** tới mô-đun sở hữu kiểu đó; package chứa kiểu cũng phải được mô-đun sở hữu export.

~~~java
module com.example.orders {
    requires com.example.common;
}
~~~

Trong ví dụ này, mã nguồn của **com.example.orders** có thể tham chiếu các kiểu public thuộc những package mà **com.example.common** export.

### 2.1. requires transitive

**requires transitive** truyền khả năng đọc sang các mô-đun phụ thuộc vào mô-đun hiện tại.

Giả sử mô-đun API công khai kiểu có sử dụng kiểu từ mô-đun model trong chữ ký phương thức:

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

Một mô-đun khác chỉ cần khai báo:

~~~java
module com.example.client {
    requires com.example.api;
}
~~~

Mô-đun **com.example.client** có thể đọc các kiểu public được export bởi **com.example.model** vì **com.example.api** đã khai báo phụ thuộc transitive.

Dùng **requires transitive** khi kiểu của mô-đun phụ thuộc xuất hiện trong API công khai mà người dùng mô-đun hiện tại cần truy cập. Không nên thêm transitive cho mọi phụ thuộc: nó làm tăng số mô-đun mà các mô-đun phía sau phải đọc và có thể mở rộng phạm vi phụ thuộc ngoài ý muốn.

**requires transitive** chỉ truyền khả năng đọc. Nó không tự export package của mô-đun phụ thuộc. Mô-đun phụ thuộc vẫn phải export package cần thiết.

### 2.2. requires static

**requires static** biểu thị một phụ thuộc cần có khi biên dịch nhưng có thể không hiện diện ở thời điểm chạy:

~~~java
module com.example.metrics.adapter {
    requires static com.example.metrics.api;
}
~~~

Cách khai báo này phù hợp với tích hợp tùy chọn, chẳng hạn một adapter chỉ được sử dụng khi ứng dụng có thêm mô-đun metrics.

Điều kiện quan trọng: nếu mô-đun phụ thuộc vắng mặt lúc chạy, mã thực thi không được khởi tạo hoặc gọi trực tiếp các kiểu của mô-đun đó. Nếu một đường chạy vẫn nạp lớp có tham chiếu tới kiểu bị thiếu, ứng dụng có thể gặp lỗi liên kết hoặc nạp lớp. Với tích hợp tùy chọn, hãy kiểm tra sự hiện diện của mô-đun trước khi nạp phần triển khai phụ thuộc; có thể dùng reflection hoặc một ranh giới API không buộc phần lõi tham chiếu trực tiếp tới thư viện tùy chọn.

Có thể kết hợp hai modifier khi thật sự cần cả hai ngữ nghĩa:

~~~java
requires transitive static com.example.optional.api;
~~~

### 2.3. Khi nào dùng requires?

- Dùng **requires** cho phụ thuộc trực tiếp mà mã nguồn cần đọc.
- Dùng **requires transitive** khi API công khai của mô-đun hiện tại làm lộ kiểu thuộc mô-đun phụ thuộc và client cần đọc kiểu đó.
- Dùng **requires static** cho phụ thuộc bắt buộc khi biên dịch nhưng được thiết kế để có thể vắng mặt khi chạy.
- Tránh khai báo phụ thuộc không được sử dụng hoặc dùng transitive chỉ để khắc phục lỗi biên dịch mà chưa hiểu quan hệ API.

## 3. Directive exports

**exports** công khai một package của mô-đun. Các mô-đun có quyền đọc mô-đun sở hữu có thể truy cập những kiểu public trong package được export, cùng các thành viên public hợp lệ của chúng theo quy tắc truy cập Java.

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Trong ví dụ này, package **com.example.orders.api** là API mà mô-đun khác có thể sử dụng. Các package khác của mô-đun vẫn được đóng gói bên trong mô-đun và không tự động trở thành API công khai.

### 3.1. Qualified exports

Có thể chỉ export một package cho một số mô-đun được chỉ định:

~~~java
module com.example.orders {
    exports com.example.orders.spi to com.example.plugin;
}
~~~

Khi đó, **com.example.orders.spi** chỉ được export cho **com.example.plugin**. Các mô-đun khác không nhận quyền truy cập package này thông qua quan hệ export.

Qualified exports hữu ích cho SPI nội bộ, plugin hoặc các mô-đun tích hợp được kiểm soát. Nó giúp tránh công khai rộng một package vốn chỉ dành cho một nhóm mô-đun phối hợp.

### 3.2. exports không thay thế opens

**exports** phục vụ truy cập thông thường theo quy tắc truy cập Java. Nó không cho phép một thư viện dùng reflection để truy cập sâu vào thành viên private của lớp trong package.

Nếu một framework cần reflection để đọc hoặc gán trường private, cần xem xét **opens** ở phần tiếp theo. Không nên mở package rộng chỉ để sửa một lỗi thiếu export; hãy xác định loại truy cập thực sự cần thiết.

## 4. Directive opens

**opens** cho phép reflection truy cập sâu vào các kiểu trong một package tại thời điểm chạy. Quyền này bao gồm khả năng truy cập thành viên không public khi cơ chế reflection và chính sách truy cập cho phép.

~~~java
module com.example.orders {
    opens com.example.orders.model;
}
~~~

Khai báo trên mở package **com.example.orders.model** cho reflection từ các mô-đun khác. Nó không làm package trở thành API có thể được tham chiếu trực tiếp trong mã nguồn của mô-đun khác. Muốn client dùng kiểu public theo cách thông thường, package vẫn cần **exports**.

### 4.1. Qualified opens

Nếu chỉ một framework hoặc mô-đun tích hợp cần reflection, hãy giới hạn phạm vi:

~~~java
module com.example.orders {
    opens com.example.orders.model to com.example.orm;
}
~~~

Trong ví dụ này, package model chỉ được mở cho mô-đun **com.example.orm**. Các mô-đun khác không nhận quyền truy cập reflection thông qua khai báo này.

Đây thường là lựa chọn phù hợp khi một framework cần ánh xạ entity, đọc annotation hoặc truy cập trường private. Tên mô-đun đích phải khớp với tên mô-đun thực tế của thư viện tích hợp.

### 4.2. open module

Có thể khai báo toàn bộ mô-đun là open:

~~~java
open module com.example.integration {
    requires com.example.core;
}
~~~

Mọi package trong mô-đun này được mở cho reflection. Tuy nhiên, **open module không tự export package**; truy cập thông thường từ mã nguồn mô-đun khác vẫn cần các directive **exports** phù hợp.

Vì mở toàn bộ package có phạm vi rộng, chỉ dùng **open module** khi toàn bộ mô-đun thực sự cần khả năng reflection đó. Một open module không khai báo thêm directive **opens** riêng lẻ; nếu chỉ cần mở một vài package, hãy dùng các directive **opens** tương ứng trong module thông thường.

### 4.3. Phân biệt exports và opens

| Khai báo | Mục đích | Truy cập mã nguồn thông thường | Reflection sâu |
|---|---|---|---|
| **exports p** | Công khai package p | Có, với kiểu public | Không tự cấp quyền truy cập thành viên private |
| **exports p to m** | Công khai p cho mô-đun m | Có, chỉ với m | Không tự cấp quyền truy cập sâu |
| **opens p** | Mở p cho reflection | Không | Có |
| **opens p to m** | Mở p cho reflection từ m | Không | Có, chỉ với m |
| **open module** | Mở mọi package cho reflection | Không tự export package | Có |

Một package có thể vừa được export vừa được open nếu ứng dụng có cả nhu cầu truy cập API thông thường và reflection. Hãy chọn phạm vi hẹp nhất đáp ứng nhu cầu thực tế.

## 5. Directive uses và provides

**uses** và **provides** là hai directive dùng cho cơ chế dịch vụ của JPMS. Chúng cho phép mô-đun tiêu thụ một abstraction mà không cần phụ thuộc trực tiếp vào mô-đun triển khai.

- **uses** khai báo mô-đun hiện tại sử dụng một service type.
- **provides ... with ...** khai báo mô-đun hiện tại cung cấp một hoặc nhiều implementation cho service type đó.

Cơ chế thường được sử dụng cùng **java.util.ServiceLoader**.

### 5.1. uses ở mô-đun tiêu thụ dịch vụ

Ví dụ mô-đun ứng dụng sử dụng giao diện GreetingService:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Mô-đun ứng dụng cần đọc mô-đun chứa service type, ở đây là **com.example.spi**. Directive **uses** ghi nhận nhu cầu dịch vụ để module system có thể tìm các provider tương ứng.

Mô-đun tiêu thụ không cần khai báo **requires com.example.provider** cho từng implementation. Đây là điểm quan trọng giúp ứng dụng phụ thuộc vào abstraction thay vì gắn chặt với một nhà cung cấp cụ thể.

### 5.2. provides ở mô-đun cung cấp dịch vụ

Mô-đun triển khai khai báo provider:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreetingService;
}
~~~

Mô-đun provider phải đọc mô-đun chứa service type. Với cách cung cấp phổ biến bằng lớp triển khai, lớp provider phải là lớp public, không abstract và có constructor public không tham số.

Package chứa lớp provider không bắt buộc phải export cho mô-đun tiêu thụ chỉ để ServiceLoader tạo provider. Nhờ đó implementation có thể tiếp tục được đóng gói bên trong mô-đun provider.

### 5.3. Provider method

Ngoài lớp trực tiếp triển khai service type, provider có thể dùng một lớp factory public với phương thức **public static provider()** trả về service type:

~~~java
public final class GreetingProviderFactory {
    public static GreetingService provider() {
        return new EnglishGreetingService();
    }
}
~~~

Module descriptor vẫn dùng dạng **provides ServiceType with ProviderClass;**. Trong trường hợp này, lớp provider không bắt buộc phải implement trực tiếp service interface; module system gọi provider method để lấy đối tượng dịch vụ.

Chọn một cách cung cấp rõ ràng và nhất quán. Với ví dụ thực hành bên dưới, ta dùng lớp triển khai có constructor public không tham số.

## 6. Ví dụ hoàn chỉnh: ServiceLoader với ba mô-đun

Ví dụ có ba mô-đun độc lập:

- **com.example.spi** định nghĩa giao diện dịch vụ và export package chứa giao diện.
- **com.example.provider** cung cấp implementation bằng directive **provides**.
- **com.example.app** sử dụng dịch vụ bằng directive **uses**.

Cấu trúc thư mục:

~~~text
src/
├── com.example.spi/
│   ├── module-info.java
│   └── com/example/spi/GreetingService.java
├── com.example.provider/
│   ├── module-info.java
│   └── com/example/provider/EnglishGreetingService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 6.1. Mô-đun SPI

Tệp **src/com.example.spi/module-info.java**:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Tệp **src/com.example.spi/com/example/spi/GreetingService.java**:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Package **com.example.spi** được export vì ứng dụng và provider cần tham chiếu giao diện **GreetingService**.

### 6.2. Mô-đun provider

Tệp **src/com.example.provider/module-info.java**:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreetingService;
}
~~~

Tệp **src/com.example.provider/com/example/provider/EnglishGreetingService.java**:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Mô-đun provider cần **requires com.example.spi** để đọc giao diện dịch vụ. Package **com.example.provider** không cần export vì ứng dụng không gọi trực tiếp lớp **EnglishGreetingService**; ServiceLoader tìm implementation thông qua khai báo **provides**.

### 6.3. Mô-đun ứng dụng

Tệp **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Tệp **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import java.util.ServiceLoader;
import com.example.spi.GreetingService;

public final class Main {
    public static void main(String[] args) {
        GreetingService service = ServiceLoader.load(GreetingService.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No GreetingService provider found"
            ));

        System.out.println(service.greet("Java JPMS"));
    }
}
~~~

Ứng dụng chỉ biết **GreetingService**. Nó không import hoặc khởi tạo trực tiếp **EnglishGreetingService**. Việc chọn implementation được giao cho ServiceLoader và module system.

### 6.4. Biên dịch và chạy

Yêu cầu JDK 17 trở lên. Chạy các lệnh sau từ thư mục chứa thư mục **src**:

~~~bash
javac -d out --module-source-path src -m com.example.spi,com.example.provider,com.example.app
java --module-path out --add-modules com.example.provider -m com.example.app/com.example.app.Main
~~~

Lệnh đầu biên dịch ba mô-đun vào thư mục **out**. Lệnh thứ hai chạy main class của mô-đun ứng dụng; **--add-modules com.example.provider** đưa provider vào cấu hình mô-đun khi khởi chạy ví dụ.

Kết quả stdout:

~~~text
Hello, Java JPMS!
~~~

Nếu thay đổi nội dung lời chào trong **EnglishGreetingService**, ứng dụng vẫn không cần biết tên lớp provider. Đây là lợi ích chính của service abstraction: có thể thay provider mà không phải sửa mã tiêu thụ, miễn là provider vẫn cung cấp cùng service type và được đưa vào cấu hình chạy.

## 7. Quan hệ giữa các directive

Có thể đọc module descriptor theo các câu hỏi sau:

1. **Mô-đun cần đọc mô-đun nào?** Khai báo bằng **requires**.
2. **Mô-đun cần công khai package nào cho mã nguồn bên ngoài?** Khai báo bằng **exports**.
3. **Framework nào cần reflection vào package nào?** Khai báo bằng **opens** hoặc **open module** nếu thật sự cần mở toàn bộ.
4. **Mô-đun cần tiêu thụ dịch vụ nào?** Khai báo bằng **uses**.
5. **Mô-đun cung cấp implementation cho dịch vụ nào?** Khai báo bằng **provides ... with ...**.

Các directive có thể cùng xuất hiện trong một descriptor. Ví dụ:

~~~java
module com.example.application {
    requires com.example.domain;
    requires transitive com.example.shared.api;

    exports com.example.application.api;
    opens com.example.application.model to com.example.orm;

    uses com.example.shared.api.AuditService;
}
~~~

Đoạn khai báo trên thể hiện một mô-đun vừa có phụ thuộc, vừa công khai API, vừa mở package model cho một framework và vừa tiêu thụ một dịch vụ. Mỗi directive giải quyết một loại quan hệ riêng; không dùng **opens** để thay **requires**, hoặc dùng **exports** để thay **uses**.

## 8. Lỗi thường gặp và cách xử lý

### 8.1. Module not found

**Nguyên nhân:** mô-đun được khai báo trong **requires** không có trong module path hoặc tên mô-đun không khớp.

**Cách xử lý:** kiểm tra tên trong module-info.java, vị trí artifact và tham số **--module-path** khi biên dịch hoặc chạy.

### 8.2. Package không được export

**Nguyên nhân:** mô-đun đã có **requires**, nhưng package chứa kiểu cần dùng chưa được mô-đun sở hữu export.

**Cách xử lý:** kiểm tra module descriptor của mô-đun sở hữu kiểu. Chỉ export package thật sự thuộc API cần công khai; nếu không có nhu cầu công khai, cân nhắc thay đổi thiết kế để không phụ thuộc vào package nội bộ.

### 8.3. Reflection bị từ chối

**Nguyên nhân:** framework cần truy cập thành viên không public nhưng package chưa được mở cho mô-đun framework.

**Cách xử lý:** thêm **opens package.name to target.module;** với đúng package và đúng mô-đun cần truy cập. Chỉ dùng **open module** nếu toàn bộ package đều cần mở.

### 8.4. ServiceLoader không tìm thấy provider

**Nguyên nhân có thể gặp:**

- Mô-đun tiêu thụ chưa khai báo **uses**.
- Mô-đun provider chưa khai báo **provides** đúng service type.
- Provider không đáp ứng yêu cầu về constructor hoặc provider method.
- Mô-đun provider không nằm trong module path hoặc chưa được đưa vào cấu hình mô-đun đang chạy.
- Service type không được mô-đun của nó export cho mô-đun provider và mô-đun tiêu thụ.

**Cách xử lý:** kiểm tra lần lượt descriptor của SPI, provider và app; kiểm tra tên service type phải giống nhau; kiểm tra cấu hình module path và root modules khi chạy. Không khắc phục bằng cách import trực tiếp implementation vào ứng dụng nếu mục tiêu là giữ mô hình service discovery.

### 8.5. Dùng nhầm exports và opens

**Nguyên nhân:** dùng **exports** để giải quyết lỗi reflection hoặc dùng **opens** với mong muốn mã nguồn mô-đun khác tham chiếu trực tiếp kiểu trong package.

**Cách xử lý:** xác định lỗi xuất hiện khi biên dịch hay khi chạy. Lỗi truy cập kiểu trong mã nguồn thường liên quan đến **requires** hoặc **exports**. Lỗi truy cập sâu qua reflection thường liên quan đến **opens**.

## 9. Checklist khi viết module-info.java

- Tên mô-đun và tên trong các directive khớp với module descriptor thực tế.
- Chỉ khai báo phụ thuộc cần thiết; chọn **requires**, **requires transitive** hoặc **requires static** theo đúng mục đích.
- Chỉ export package thuộc API cần cho mô-đun khác.
- Chỉ open package mà framework thực sự cần reflection.
- Mô-đun tiêu thụ khai báo **uses** cho service type.
- Mô-đun cung cấp khai báo **provides** với provider hợp lệ.
- Các mô-đun cần thiết đều có mặt trong cấu hình module path lúc chạy.
- Không công khai implementation package nếu client chỉ cần service abstraction.

Khi thiết kế JPMS, hãy bắt đầu từ API mà mô-đun cần cung cấp và các phụ thuộc thực sự cần đọc. Sau đó mới quyết định package nào được export, package nào cần mở cho reflection và dịch vụ nào nên được phát hiện qua ServiceLoader. Cách tổ chức này giữ ranh giới mô-đun rõ ràng, giảm phụ thuộc trực tiếp giữa implementation và client, đồng thời giúp ứng dụng dễ thay thế thành phần hơn.