# So sánh xuất API (exports) với mở phản chiếu (opens) trong JPMS

Trong Java Platform Module System (JPMS), một module có thể giới hạn những package mà module khác được phép sử dụng. Hai directive thường bị nhầm lẫn là **exports** và **opens**. Cả hai đều được khai báo trong **module-info.java**, nhưng phục vụ hai kiểu truy cập khác nhau:

- **exports** công bố package để module khác sử dụng API Java thông thường, chẳng hạn import kiểu public và gọi các thành viên được phép truy cập.
- **opens** cho phép truy cập sâu bằng reflection lúc chạy, bao gồm việc kiểm tra và truy cập các thành viên không public khi quyền truy cập được bật.

Hiểu đúng hai directive giúp thiết kế API công khai rõ ràng, giữ phần triển khai nội bộ được đóng gói và vẫn tích hợp được với framework cần reflection.

## 1. Khác biệt cốt lõi

| Tiêu chí | exports | opens |
|---|---|---|
| Mục đích | Công bố API của package cho module khác | Cho phép reflection truy cập sâu vào package lúc chạy |
| Thời điểm có hiệu lực chính | Biên dịch và runtime | Runtime |
| Cho phép import kiểu public từ package | Có, nếu module sử dụng cũng đọc module cung cấp | Không |
| Cho phép truy cập thành viên public theo quy tắc Java | Có, trong phạm vi package được export và module được đọc | Không tự tạo quyền truy cập API thông thường |
| Cho phép reflection truy cập thành viên private/package-private/protected sâu | Không chỉ nhờ exports | Có, khi package được mở cho module thực hiện reflection |
| Có thể giới hạn module nhận quyền | Có, bằng qualified exports | Có, bằng qualified opens |
| Có thể áp dụng cho toàn bộ package trong module | Có thể export từng package; không có directive “export mọi package” | Có thể dùng open module để mở tất cả package cho reflection |

Hai điều kiện quan trọng:

1. Module sử dụng phải đọc module cung cấp. Với named module, quan hệ này thường được khai báo bằng requires.
2. Quyền truy cập package và thành viên phải phù hợp với loại thao tác. requires chỉ tạo quan hệ đọc; nó không tự export hoặc open package.

exports và opens không thay thế nhau. Một package được export vẫn có thể từ chối deep reflection vào private member. Một package được open vẫn không thể được import như API Java thông thường từ module khác.

## 2. exports: công bố API cho module khác

Directive exports công bố một package của module. Các module đọc module cung cấp có thể dùng các kiểu public trong package đó theo quy tắc truy cập của Java.

### 2.1. Export không giới hạn người nhận

Ví dụ:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Package com.example.domain.api trở thành API công khai của module. Module khác muốn sử dụng package này cần đọc com.example.domain, thường thông qua:

~~~java
module com.example.client {
    requires com.example.domain;
}
~~~

Sau đó, mã trong module client có thể import kiểu public thuộc package API đã export:

~~~java
package com.example.client;

import com.example.domain.api.CustomerView;

public class Client {
    public static void print(CustomerView customer) {
        System.out.println(customer.name());
    }
}
~~~

Việc export package không làm mọi thành viên trong package trở thành public. Quy tắc truy cập Java vẫn được áp dụng: kiểu và thành viên private, package-private hoặc protected vẫn chịu quy tắc truy cập tương ứng.

### 2.2. Qualified exports: chỉ công bố cho module được chỉ định

Nếu API chỉ dành cho một số module, có thể dùng qualified exports:

~~~java
module com.example.domain {
    exports com.example.domain.api to com.example.client, com.example.admin;
}
~~~

Chỉ các module com.example.client và com.example.admin được hưởng quyền truy cập package API này. Module khác dù có requires com.example.domain cũng không thể truy cập package đó như API thông thường.

Đây là cách thu hẹp bề mặt API khi một module có package dành riêng cho một nhóm module nội bộ.

### 2.3. exports có cho phép reflection không?

exports cho phép truy cập thông thường tới các kiểu public trong package được export. Reflection cũng có thể sử dụng các public member được phép truy cập theo quy tắc Java.

Tuy nhiên, exports không cấp quyền deep reflection để bật truy cập vào private member. Ví dụ, một framework có thể lấy được Field đại diện cho thuộc tính private, nhưng việc gọi trySetAccessible() để vượt qua kiểm tra truy cập vẫn cần package được mở.

## 3. opens: cho phép reflection truy cập sâu lúc chạy

Framework như dependency injection, object mapper, serializer hoặc công cụ binding có thể cần đọc hoặc gán field private, gọi constructor không public hay kiểm tra annotation của thành viên nội bộ.

Directive opens cấp quyền cần thiết cho deep reflection trong package được mở.

### 3.1. Open package cho mọi module

~~~java
module com.example.domain {
    opens com.example.domain.model;
}
~~~

Package com.example.domain.model được mở cho reflection từ các module khác. Package này vẫn không trở thành API có thể import khi biên dịch.

### 3.2. Qualified opens: chỉ mở cho framework cần quyền

Thực tế nên giới hạn module được phép reflection khi có thể:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.framework;
}
~~~

Trong ví dụ:

- com.example.domain.api là API công khai, có thể được module đọc com.example.domain sử dụng bình thường.
- com.example.domain.model không được export, nên framework không thể import các kiểu trong package này như API.
- com.example.domain.model được mở riêng cho com.example.framework, nên framework có thể thực hiện deep reflection lúc chạy.

Qualified opens giúp tích hợp framework mà không phải mở toàn bộ package cho mọi module.

### 3.3. open module: mở tất cả package cho reflection

Có thể khai báo:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module được khai báo với modifier open sẽ mở tất cả package của nó cho deep reflection lúc chạy. Directive exports vẫn cần thiết nếu muốn công bố API cho truy cập thông thường.

open module có phạm vi rộng hơn qualified opens. Chỉ nên dùng khi hầu hết package thực sự cần được framework hoặc thư viện truy cập sâu.

## 4. Ví dụ chạy được: export API và open package nội bộ cho reflection

Ví dụ dưới đây có hai module:

- com.example.domain cung cấp API CustomerView, đồng thời giữ implementation trong package nội bộ com.example.domain.model.
- com.example.framework đọc API của domain và dùng reflection để đọc field private của implementation.

### 4.1. Cấu trúc dự án

~~~text
src/
├── com.example.domain/
│   ├── module-info.java
│   └── com/example/domain/
│       ├── api/
│       │   ├── CustomerView.java
│       │   └── Customers.java
│       └── model/
│           └── CustomerRecord.java
└── com.example.framework/
    ├── module-info.java
    └── com/example/framework/app/
        └── Main.java
~~~

### 4.2. Module descriptor của domain

File src/com.example.domain/module-info.java:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.framework;
}
~~~

Domain export package API và chỉ mở package model cho framework.

### 4.3. API public

File src/com.example.domain/com/example/domain/api/CustomerView.java:

~~~java
package com.example.domain.api;

public interface CustomerView {
    String name();
}
~~~

File src/com.example.domain/com/example/domain/api/Customers.java:

~~~java
package com.example.domain.api;

import com.example.domain.model.CustomerRecord;

public final class Customers {
    private Customers() {
    }

    public static CustomerView create(String name, String email) {
        return new CustomerRecord(name, email);
    }
}
~~~

CustomerView và Customers thuộc package được export. Client có thể import và gọi chúng mà không cần biết implementation nằm ở đâu.

### 4.4. Implementation nội bộ

File src/com.example.domain/com/example/domain/model/CustomerRecord.java:

~~~java
package com.example.domain.model;

import com.example.domain.api.CustomerView;

public final class CustomerRecord implements CustomerView {
    private final String name;
    private final String email;

    public CustomerRecord(String name, String email) {
        this.name = name;
        this.email = email;
    }

    @Override
    public String name() {
        return name;
    }
}
~~~

Package com.example.domain.model không được export. Module framework không thể import CustomerRecord để sử dụng như API Java thông thường. Tuy nhiên, framework vẫn có thể nhận object qua interface CustomerView và lấy lớp runtime bằng getClass().

### 4.5. Module descriptor của framework

File src/com.example.framework/module-info.java:

~~~java
module com.example.framework {
    requires com.example.domain;
}
~~~

requires giúp framework đọc module domain. Quyền reflection đối với package model được cấp riêng bởi opens trong module domain.

### 4.6. Dùng API và reflection

File src/com.example.framework/com/example/framework/app/Main.java:

~~~java
package com.example.framework.app;

import com.example.domain.api.CustomerView;
import com.example.domain.api.Customers;

import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        CustomerView customer = Customers.create("Ada", "ada@example.com");

        // Truy cập API công khai thông qua interface đã export.
        System.out.println("API name: " + customer.name());

        // Lấy field private từ implementation runtime.
        Field email = customer.getClass().getDeclaredField("email");

        // Package model đã được mở cho module framework.
        boolean opened = email.trySetAccessible();
        System.out.println("Reflection open: " + opened);

        if (opened) {
            System.out.println("Private email: " + email.get(customer));
        }
    }
}
~~~

trySetAccessible() trả về true khi quyền truy cập sâu được bật thành công. API này có từ Java 9 và phù hợp để kiểm tra khả năng truy cập reflection mà không phải dựa vào việc bắt ngoại lệ từ setAccessible(true).

### 4.7. Biên dịch và chạy

Từ thư mục chứa src, tạo thư mục đầu ra trước khi biên dịch:

~~~bash
mkdir -p out
javac -d out --module-source-path src -m com.example.domain,com.example.framework
java --module-path out -m com.example.framework/com.example.framework.app.Main
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out --module-source-path src -m com.example.domain,com.example.framework
java --module-path out -m com.example.framework/com.example.framework.app.Main
~~~

Kết quả stdout:

~~~text
API name: Ada
Reflection open: true
Private email: ada@example.com
~~~

Ví dụ dùng cú pháp JPMS và API reflection hiện hành, biên dịch/chạy trên Java 17 trở lên. Hai module được biên dịch cùng lúc để compiler phân giải được module framework được nêu trong qualified opens.

### 4.8. Thử đóng package lại

Nếu bỏ directive sau khỏi com.example.domain/module-info.java:

~~~java
opens com.example.domain.model to com.example.framework;
~~~

Sau khi biên dịch lại, API CustomerView vẫn dùng được vì package API vẫn được export. Tuy nhiên, trySetAccessible() với field private trong package model sẽ trả về false, bởi package này không còn được mở cho framework.

Khi đó, hai dòng đầu của stdout vẫn là:

~~~text
API name: Ada
Reflection open: false
~~~

Chương trình không đọc field private vì nhánh if (opened) không được thực hiện. Đây là cách quan sát rõ ràng rằng quyền sử dụng API và quyền deep reflection là hai quyền độc lập.

## 5. Bổ sung quyền lúc chạy bằng --add-opens

Trong quá trình tích hợp một thư viện hoặc framework chưa thể thay đổi module descriptor, có thể cấp quyền mở package ở dòng lệnh JVM:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.framework --module-path out -m com.example.framework/com.example.framework.app.Main
~~~

Cú pháp:

~~~text
--add-opens source-module/package=target-module
~~~

Trong đó:

- source-module là module sở hữu package cần mở.
- package là package cần cho phép deep reflection.
- target-module là module nhận quyền truy cập reflection.

ALL-UNNAMED có thể được dùng làm target khi cần cấp quyền cho mã chạy trong unnamed module trên classpath:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED --module-path out -cp tools.jar com.example.tools.Main
~~~

--add-opens chỉ thay đổi quyền reflection lúc chạy. Nó không làm package trở thành API có thể import khi biên dịch. Nếu framework cần truy cập API thông thường, hãy dùng exports và quan hệ đọc module phù hợp.

Nên giới hạn package và module nhận quyền. Việc mở package rộng trong cấu hình runtime làm giảm mức đóng gói mà JPMS cung cấp.

## 6. Khi nào dùng exports, opens hoặc cả hai?

| Nhu cầu | Directive phù hợp | Ví dụ |
|---|---|---|
| Công bố interface, class hoặc API public | exports | API của thư viện cho ứng dụng sử dụng |
| Chỉ công bố API cho một số module nội bộ | exports ... to ... | Package dành riêng cho module admin |
| Cho framework đọc field private hoặc gọi constructor không public bằng reflection | opens | Package entity cho ORM hoặc serializer |
| Chỉ cho một framework được reflection | opens ... to ... | Package model mở riêng cho module framework |
| Framework cần API public và deep reflection vào package triển khai | Kết hợp exports và opens | Export package API, open package model |
| Phần lớn package cần deep reflection | open module | Module tích hợp sâu với framework cần truy cập nhiều package |

Nguyên tắc thiết kế:

- Xem package được export là một phần hợp đồng API; thay đổi hoặc loại bỏ nó có thể ảnh hưởng module phụ thuộc.
- Giữ package triển khai ở trạng thái không export nếu module khác không cần sử dụng trực tiếp.
- Chỉ mở package mà framework thực sự cần reflection.
- Ưu tiên qualified exports và qualified opens để thu hẹp module nhận quyền.
- Không dùng open module chỉ để xử lý một lỗi reflection trong một package.
- Nếu một thư viện cần truy cập API, hãy export API; nếu cần truy cập thành viên private, hãy open package tương ứng.

## 7. Lỗi thường gặp và cách xử lý

| Lỗi hoặc triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| package ... is not visible hoặc compiler báo package không được export | Module đích chưa export package hoặc module sử dụng chưa đọc module nguồn | Kiểm tra exports và requires |
| IllegalAccessError khi chạy | Module descriptor hoặc ranh giới truy cập lúc runtime không khớp với những gì mã đã được biên dịch dựa vào | Kiểm tra descriptor thực tế của module đang chạy và package export |
| trySetAccessible() trả về false | Package chứa thành viên không được open cho module gọi reflection | Dùng qualified opens hoặc --add-opens cho đúng module/package |
| InaccessibleObjectException khi bật truy cập sâu | Framework gọi API bật truy cập nhưng package không mở cho module của framework | Mở package có giới hạn bằng opens ... to ... |
| Framework đọc được kiểu public nhưng không đọc được field private | Package đã export nhưng chưa open | Giữ exports cho API và bổ sung opens cho package cần reflection |
| Đã opens nhưng mã nguồn vẫn không import được class trong package | opens chỉ cấp quyền reflection lúc chạy, không export API khi biên dịch | Bổ sung exports nếu class cần trở thành API |
| Đã khai báo requires nhưng vẫn bị từ chối truy cập package | requires chỉ thiết lập quan hệ đọc, không tự cấp quyền export/open | Kiểm tra directive trong module descriptor của module nguồn |

Khi xử lý lỗi, xác định trước thao tác đang thất bại là truy cập API Java thông thường hay deep reflection. Sau đó mới chọn directive tương ứng. Cách này tránh mở package rộng chỉ để làm mất thông báo lỗi.

## 8. Checklist rà soát module descriptor

- [ ] Module sử dụng đã khai báo requires tới module cung cấp.
- [ ] Package chứa API public đã được exports.
- [ ] Qualified exports chỉ liệt kê đúng module cần sử dụng API.
- [ ] Package triển khai nội bộ không bị export nếu không cần thiết.
- [ ] Package cần deep reflection đã được opens.
- [ ] Qualified opens chỉ cấp quyền cho framework cần thiết.
- [ ] Không nhầm opens với exports.
- [ ] Không dùng open module nếu chỉ cần mở một vài package.
- [ ] Ví dụ hoặc cấu hình runtime đã được kiểm tra với JDK đang hỗ trợ.

## 9. Tài liệu tham khảo

- [Java Language Specification, Java SE 26 — Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html): cú pháp và ngữ nghĩa của exports, opens, open module và requires.
- [Java SE 26 API — AccessibleObject.trySetAccessible()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible()): kiểm tra và bật quyền truy cập reflection.
- [Java SE 26 — java command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): tùy chọn runtime như --add-opens.
- [Dev.java — Organizing Code into Modules](https://dev.java/learn/organizing/modules/): hướng dẫn thực hành JPMS và module descriptor.
