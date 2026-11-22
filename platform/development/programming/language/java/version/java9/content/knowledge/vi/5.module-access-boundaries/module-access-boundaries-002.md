# Xuất package có chọn lọc bằng exports ... to

## 1. Vai trò của qualified exports trong JPMS

Java Platform Module System (JPMS), được giới thiệu từ Java 9, cho phép một module công bố những package tạo thành API của nó. Chỉ package được khai báo export mới có thể được module khác sử dụng theo cơ chế truy cập thông thường.

Directive **exports package to moduleA, moduleB** được gọi là *qualified export*. Nó công bố một package cho một danh sách module được chỉ định. Đây là cách thiết kế ranh giới truy cập khi một thư viện chỉ muốn chia sẻ API với một số module cộng tác, trong khi giữ package nội bộ bên ngoài phạm vi truy cập.

Ví dụ:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api to com.acme.report;
}
~~~

Trong ví dụ này, package **com.acme.catalog.api** được export cho module **com.acme.report**. Module khác dù có đọc được **com.acme.catalog** vẫn không được phép truy cập package này thông qua Java access rules nếu không nằm trong danh sách được export.

Qualified exports vẫn là tính năng JPMS được sử dụng trong các phiên bản Java hiện đại. Nó phù hợp khi các module trong cùng một ứng dụng cần chia sẻ API có giới hạn rõ ràng.

## 2. Cú pháp và ý nghĩa

Cú pháp trong file **module-info.java**:

~~~java
module module.name {
    exports package.name to target.module.one, target.module.two;
}
~~~

Các thành phần:

- **package.name** là package thuộc module đang khai báo directive.
- **target.module.one**, **target.module.two** là tên module nhận quyền truy cập. Tên này phải khớp với tên module được khai báo trong module descriptor của bên nhận.
- Có thể liệt kê một hoặc nhiều module đích, phân cách bằng dấu phẩy.
- Dấu chấm phẩy kết thúc directive.

Ví dụ export cho nhiều module:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api
        to com.acme.report, com.acme.admin;
}
~~~

Package API trong ví dụ có thể được sử dụng bởi cả **com.acme.report** và **com.acme.admin**. Các module khác không có quyền truy cập package đó chỉ vì chúng khai báo dependency tới **com.acme.catalog**.

Một số quy tắc cần nhớ:

1. Directive phải nằm trong **module-info.java** của module sở hữu package.
2. Tên package phải đúng với package trong mã nguồn và package đó phải thuộc module đang khai báo.
3. Tên module đích là tên module JPMS, không phải tên package, tên class hay tên file JAR.
4. Export áp dụng cho toàn bộ package được nêu. Nó không tự động áp dụng cho package con.
5. Qualified export công bố các kiểu public trong package. Quy tắc truy cập public, protected, package-private và private của Java vẫn được áp dụng như bình thường.
6. Không thể dùng một directive exports để chỉ chọn một class riêng lẻ trong package. Nếu cần công bố một tập class nhỏ, hãy thiết kế API thành package riêng hoặc dùng facade public.

Ví dụ, khai báo sau chỉ export package **com.acme.catalog.api**:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api to com.acme.report;
}
~~~

Package **com.acme.catalog.api.internal** không được export theo khai báo trên. Package con là một package độc lập trong Java.

## 3. exports và requires giải quyết hai vấn đề khác nhau

Để module client sử dụng một package đã được qualified export, hai điều kiện phải đồng thời đúng:

- Module client phải đọc được module cung cấp API. Thông thường, client khai báo **requires** module cung cấp.
- Module cung cấp phải export package đó cho chính module client.

Ví dụ:

~~~java
module com.acme.report {
    requires com.acme.catalog;
}
~~~

Khai báo **requires** tạo quan hệ readability: module report có thể đọc module catalog. Nó không tự cấp quyền truy cập mọi package của catalog.

Ở chiều ngược lại, khai báo **exports ... to com.acme.report** cho phép report truy cập package được export, nhưng không tự tạo quan hệ readability. Nếu thiếu **requires**, module report vẫn không thể sử dụng module catalog theo cách thông thường.

Có thể phân biệt các directive như sau:

| Directive | Trách nhiệm |
|---|---|
| **requires M** | Khai báo module hiện tại phụ thuộc và có thể đọc module M. |
| **exports p** | Export package p cho mọi module đọc được module hiện tại. |
| **exports p to M** | Chỉ export package p cho các module đích được liệt kê và đọc được module hiện tại. |
| **opens p to M** | Cho phép module M truy cập sâu bằng reflection vào package p tại runtime. |

**exports** phục vụ truy cập API thông thường trong mã Java. Nó không cho phép framework dùng reflection để truy cập tùy ý các thành viên private của package. Khi một framework thực sự cần deep reflection, module cần cân nhắc directive **opens** phù hợp.

## 4. Ví dụ hoàn chỉnh với hai module

Ta tạo module thư viện catalog và module ứng dụng report. Thư viện chỉ công bố package API cho report.

Cấu trúc thư mục:

~~~text
project/
├── src/
│   ├── com.acme.catalog/
│   │   ├── module-info.java
│   │   └── com/acme/catalog/api/Catalog.java
│   └── com.acme.report/
│       ├── module-info.java
│       └── com/acme/report/Main.java
~~~

### 4.1. Module cung cấp API

File **src/com.acme.catalog/module-info.java**:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api to com.acme.report;
}
~~~

File **src/com.acme.catalog/com/acme/catalog/api/Catalog.java**:

~~~java
package com.acme.catalog.api;

public final class Catalog {
    public String name() {
        return "Java modules";
    }
}
~~~

Class Catalog là API public mà module catalog muốn cung cấp cho report.

### 4.2. Module sử dụng API

File **src/com.acme.report/module-info.java**:

~~~java
module com.acme.report {
    requires com.acme.catalog;
}
~~~

File **src/com.acme.report/com/acme/report/Main.java**:

~~~java
package com.acme.report;

import com.acme.catalog.api.Catalog;

public class Main {
    public static void main(String[] args) {
        Catalog catalog = new Catalog();
        System.out.println(catalog.name());
    }
}
~~~

Report khai báo requires để đọc catalog. Package **com.acme.catalog.api** được catalog export đích danh cho report, vì vậy import và sử dụng class Catalog là hợp lệ.

### 4.3. Biên dịch và chạy

Chạy các lệnh sau tại thư mục **project** bằng JDK 17 trở lên:

~~~bash
javac --module-source-path src -d out -m com.acme.catalog,com.acme.report
java --module-path out -m com.acme.report/com.acme.report.Main
~~~

Lệnh đầu biên dịch hai module từ module source path và đặt kết quả vào thư mục **out**. Lệnh thứ hai chạy class Main thuộc module report, đồng thời dùng **out** làm module path.

Kết quả:

~~~text
Java modules
~~~

Ví dụ thể hiện đầy đủ hai phía của ranh giới truy cập: catalog công bố package API cho report bằng qualified exports, còn report khai báo requires để đọc catalog.

## 5. Điều gì xảy ra với module không nằm trong danh sách?

Giả sử có thêm module **com.acme.analytics**:

~~~java
module com.acme.analytics {
    requires com.acme.catalog;
}
~~~

Module analytics đọc được catalog, nhưng catalog chỉ export **com.acme.catalog.api** cho **com.acme.report**. Nếu analytics import class **com.acme.catalog.api.Catalog**, trình biên dịch sẽ từ chối vì package không được export cho analytics.

Muốn analytics sử dụng API đó, cần bổ sung module này vào danh sách đích:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api
        to com.acme.report, com.acme.analytics;
}
~~~

Việc bổ sung phải xuất phát từ quyết định thiết kế API: analytics có thực sự là module được phép phụ thuộc vào package này hay không.

## 6. Phân biệt qualified exports với opens

Hai directive có mục đích khác nhau:

- **exports p to M** cho phép module M truy cập các kiểu public trong package p theo quy tắc Java thông thường. Nó phục vụ việc sử dụng API giữa các module.
- **opens p to M** cho phép module M truy cập sâu vào package p bằng reflection tại runtime, bao gồm các thành viên không public khi các điều kiện truy cập reflection được đáp ứng.
- **opens** không làm package trở thành API có thể import trực tiếp trong mã nguồn của module client.
- **exports** cũng không đồng nghĩa với việc package được mở cho deep reflection.

Ví dụ, một thư viện có thể export package API cho module ứng dụng nhưng chỉ mở package model cho một module framework cần reflection:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api to com.acme.report;
    opens com.acme.catalog.model to com.acme.serializer;
}
~~~

Chỉ dùng **opens** khi có nhu cầu reflection thực tế. Không mở rộng package không cần thiết vì điều đó làm giảm mức độ đóng gói của module.

## 7. Cách thiết kế ranh giới package

Qualified exports hữu ích nhất khi package được tổ chức theo ranh giới API rõ ràng.

- Giữ API ổn định trong các package như **com.acme.catalog.api**.
- Đặt implementation và chi tiết nội bộ trong package riêng, chẳng hạn **com.acme.catalog.internal**.
- Chỉ thêm module vào danh sách đích khi module đó thực sự cần phụ thuộc vào API.
- Nếu nhiều module cần cùng một API, liệt kê rõ các module đó trong directive.
- Khi cần giới hạn tập class được nhìn thấy, hãy tách class thành các package theo trách nhiệm thay vì export package chứa cả API lẫn implementation.
- Giữ tên module nhất quán giữa module descriptor, cấu hình build và module path.

Qualified exports là cơ chế đóng gói và kiểm soát truy cập ở cấp module. Nó giúp trình biên dịch và runtime thực thi ranh giới API của JPMS, nhưng không phải cơ chế sandbox để cô lập mã độc hoặc thay thế các biện pháp bảo vệ ở cấp hệ điều hành.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Package is not visible | Package chưa được export cho module đang sử dụng, hoặc module client chưa khai báo requires. |
| Module client không import được class public | Kiểm tra tên package, tên module đích và khai báo qualified exports. |
| Một package con vẫn không truy cập được | Exports không tự động áp dụng cho subpackage. Hãy khai báo export riêng nếu đó là API cần công bố. |
| Module khác có requires nhưng vẫn không truy cập được package | Readability và exports là hai điều kiện độc lập. requires không mở mọi package. |
| Reflection gặp lỗi truy cập | Kiểm tra nhu cầu deep reflection và khai báo opens đúng package cho module framework. |
| Module không có trong danh sách đích | Bổ sung module đó chỉ khi thiết kế cho phép nó sử dụng API. |

Khi gặp lỗi truy cập, nên kiểm tra theo thứ tự: tên module, quan hệ requires, tên package, danh sách qualified exports và cuối cùng là nhu cầu reflection. Cách kiểm tra này giúp xác định đúng cạnh còn thiếu trong đồ thị module.

## 9. Khi nào nên dùng exports ... to?

Dùng qualified exports khi một package là API dùng chung có chủ đích giữa một số module cụ thể, ví dụ:

- Một module core cung cấp API cho module adapter đã xác định.
- Một thư viện nội bộ chia sẻ package hợp đồng với một số module trong cùng ứng dụng.
- Một module nền tảng cho phép một nhóm module tích hợp sử dụng API mà không công bố package đó cho toàn bộ module graph.

Nếu package thực sự là API công khai cho mọi module đọc được module hiện tại, dùng **exports package** không có danh sách đích sẽ phù hợp hơn. Nếu chỉ cần chia sẻ với một nhóm module, **exports package to ...** biểu đạt chính xác ý định đó.

Điểm cốt lõi là tách bạch readability, export và reflection: **requires** cho phép đọc module, **exports ... to** giới hạn module được sử dụng API public của package, còn **opens ... to** phục vụ deep reflection tại runtime. Đây là ba công cụ khác nhau để xây dựng ranh giới truy cập rõ ràng trong JPMS hiện đại.
