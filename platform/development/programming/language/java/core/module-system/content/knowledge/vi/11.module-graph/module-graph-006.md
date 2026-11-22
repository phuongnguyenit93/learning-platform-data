# Duplicate module name và lỗi resolution

## 1. Tên module là định danh trong JPMS

Trong Java Platform Module System (JPMS), mỗi named module có một tên được khai báo trong module descriptor. Tên này được dùng để liên kết các chỉ thị requires, exports có giới hạn, opens, uses và provides giữa các module.

Ví dụ:

~~~java
module com.acme.orders {
    requires com.acme.customer.api;
}
~~~

Trong đó com.acme.orders và com.acme.customer.api là tên module. Tên module phải ổn định và duy nhất trong một cấu hình module đã được phân giải.

Tên module khác với:

- Tên file JAR, ví dụ customer-api-2.1.jar.
- Tọa độ dependency của Maven hoặc Gradle.
- Tên package Java, ví dụ com.acme.customer.api.
- Phiên bản thư viện, ví dụ 2.1.0.

Một module có thể khai báo phiên bản trong descriptor, nhưng chỉ thị requires liên kết theo tên module; nó không phải cú pháp chọn một phiên bản dependency như Maven hoặc Gradle.

Vì vậy, nếu hai artifact cùng khai báo tên module com.acme.customer.api, module system xem chúng là hai ứng viên cho cùng một định danh module, dù tên file hoặc phiên bản artifact khác nhau.

## 2. Duplicate module name xuất hiện từ đâu?

Xung đột tên module thường xuất hiện trong các tình huống sau:

- Hai phiên bản của cùng một thư viện cùng được đưa lên module path.
- Hai JAR khác nhau khai báo cùng thuộc tính Automatic-Module-Name.
- Hai JAR cũ có tên file sau chuẩn hóa tạo ra cùng tên automatic module.
- Một thư viện được đóng gói thành cả modular JAR và exploded module, rồi cả hai cùng xuất hiện trong đường dẫn tìm kiếm.
- Một dependency được đưa vào module path qua nhiều nhánh dependency hoặc qua cả thư mục ứng dụng và thư mục plugin.
- Một bản JAR được copy vào nhiều thư mục cấu hình khác nhau, khiến module finder nhìn thấy nhiều candidate cùng tên.

Ví dụ:

~~~text
project/
├── mods/
│   ├── customer-api-1.8.jar
│   └── customer-api-2.1.jar
└── app/
~~~

Nếu cả hai JAR khai báo:

~~~java
module com.acme.customer.api {
    exports com.acme.customer.api;
}
~~~

thì tên module của chúng giống nhau dù version hoặc tên file khác nhau.

Đối với JAR chưa có module-info.class, Java có thể dùng thuộc tính Automatic-Module-Name trong manifest. Nếu thuộc tính này không tồn tại, tên automatic module được suy ra từ tên file JAR sau khi chuẩn hóa. Do đó, đổi tên file hoặc đưa hai JAR có tên suy ra giống nhau vào module path có thể tạo va chạm.

## 3. Vì sao hai module cùng tên gây vấn đề?

Tên module là khóa để module system tìm dependency. Khi một module khai báo:

~~~java
module com.acme.application {
    requires com.acme.customer.api;
}
~~~

bộ phân giải cần tìm một định nghĩa module mang tên com.acme.customer.api. Chỉ thị requires không nói rằng ứng dụng muốn phiên bản 1.8 hay 2.1.

Một cấu hình module không thể chứa hai định nghĩa độc lập cùng tên như thể chúng là hai dependency khác nhau. Nếu hai bản cùng tên được phát hiện trong các vị trí tìm kiếm, một bản có thể che khuất bản còn lại theo quy tắc tìm kiếm của module finder; với đầu vào không hợp lệ hoặc không thể phân biệt, quá trình tìm kiếm có thể phát sinh FindException.

Điểm nguy hiểm là ứng dụng có thể phân giải thành công nhưng sử dụng nhầm artifact so với bản mà developer dự định. Khi API giữa các phiên bản khác nhau, lỗi có thể chỉ xuất hiện lúc biên dịch hoặc lúc chạy, chẳng hạn thiếu method, thay đổi kiểu dữ liệu hoặc hành vi không tương thích.

Vì vậy, duplicate module name không chỉ là vấn đề đặt tên. Nó là vấn đề xác định chính xác artifact nào đại diện cho một định danh module trong cấu hình.

## 4. Thứ tự module path và hiện tượng shadowing

Module path có thể chứa nhiều entry: modular JAR, exploded module hoặc thư mục chứa các module. Các entry được cung cấp cho module finder theo thứ tự.

Với module finder chuẩn, khi cùng một tên module xuất hiện ở nhiều entry trên module path, candidate được tìm thấy trước có thể được dùng và che khuất candidate ở entry sau. Vì vậy, thứ tự module path có thể ảnh hưởng module nào được chọn.

Ví dụ:

~~~bash
java --module-path "mods-v1:mods-v2" --module com.acme.application/com.acme.application.Main
~~~

Nếu cả mods-v1 và mods-v2 đều chứa module com.acme.customer.api, kết quả tìm kiếm có thể phụ thuộc vào thứ tự entry. Trên Windows, dấu phân cách path là dấu chấm phẩy:

~~~powershell
java --module-path "mods-v1;mods-v2" --module com.acme.application/com.acme.application.Main
~~~

Không nên dùng thứ tự module path như một cơ chế quản lý version. Cách an toàn là đảm bảo mỗi tên module chỉ có một artifact dự kiến trong tập module có thể quan sát, và để Maven/Gradle quản lý dependency graph cùng phiên bản thư viện.

Nếu một custom ModuleFinder được dùng, hành vi tìm kiếm còn phụ thuộc implementation của finder đó. Đừng giả định mọi finder đều áp dụng chính sách giống finder mặc định của Java launcher.

## 5. Automatic module có thể tạo va chạm tên

JAR cũ không có module descriptor vẫn có thể được đưa lên module path. Java xem nó là automatic module.

Tên automatic module được xác định theo thứ tự:

1. Nếu manifest có Automatic-Module-Name hợp lệ, dùng tên đó.
2. Nếu không có, Java suy ra tên từ tên file JAR theo quy tắc chuẩn hóa.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy.logging
~~~

Hai JAR có thể có tên file khác nhau nhưng cùng khai báo Automatic-Module-Name:

~~~text
legacy-logging-1.0.jar
legacy-logging-2.0.jar
~~~

Nếu cả hai đều khai báo com.acme.legacy.logging, chúng tạo candidate cùng tên module.

Với thư viện đang chuyển tiếp sang JPMS, nên đặt Automatic-Module-Name ổn định ngay từ các bản phát hành chưa có module-info.class. Khi phát hành modular JAR chính thức, giữ tên module nhất quán để consumer không phải đổi requires.

Không nên tự sửa tên file dependency để che một va chạm nếu dependency graph vẫn chứa nhiều phiên bản không tương thích. Hãy loại bỏ phiên bản dư thừa hoặc chọn một phiên bản được quản lý thống nhất.

## 6. Phân biệt duplicate module name và split package

Hai khái niệm này dễ bị nhầm vì đều liên quan đến nhiều artifact, nhưng nguyên nhân khác nhau.

**Duplicate module name**: nhiều candidate cùng khai báo một tên module, ví dụ hai JAR đều có tên com.acme.customer.api.

**Split package**: hai module khác tên cùng chứa hoặc export một package có cùng tên, ví dụ:

~~~text
com.acme.customer.api
    package com.acme.shared.model

com.acme.order.api
    package com.acme.shared.model
~~~

Khi một module đọc cả hai module và cả hai cùng export package com.acme.shared.model, module graph không nhất quán. Resolution có thể thất bại với ResolutionException do split package.

Ví dụ:

~~~java
module com.acme.customer.api {
    exports com.acme.shared.model;
}

module com.acme.order.api {
    exports com.acme.shared.model;
}

module com.acme.application {
    requires com.acme.customer.api;
    requires com.acme.order.api;
}
~~~

Module com.acme.application đọc cả hai module và nhìn thấy cùng package từ hai nguồn. Đây là xung đột package, không phải duplicate module name.

Cách xử lý thường là:

- Đưa package dùng chung vào một module sở hữu duy nhất.
- Chuyển các type về package riêng theo module sở hữu.
- Điều chỉnh ranh giới API để hai module không export cùng package cho một consumer.
- Loại bỏ class trùng khỏi artifact nếu chúng là bản sao ngoài ý muốn.

Đổi tên module không tự giải quyết split package nếu package vẫn bị chia sẻ và cùng được đọc.

## 7. Module graph và các bước resolution

Module resolution xây dựng cấu hình module dựa trên tập module gốc và các phụ thuộc bắt buộc.

Có thể mô tả quy trình:

1. **Tìm module có thể quan sát**: module finder tìm module theo tên từ module path, system modules hoặc nguồn được cấu hình.
2. **Chọn module gốc**: launcher xác định root modules từ module được chạy, --add-modules hoặc quy tắc khởi chạy tương ứng.
3. **Đọc requires**: với mỗi root, bộ phân giải đọc module descriptor và lấy các dependency trực tiếp.
4. **Tìm dependency đệ quy**: mỗi module được phân giải tiếp tục kéo theo các module mà nó requires.
5. **Kiểm tra tính nhất quán**: bộ phân giải kiểm tra tên module, dependency bắt buộc, package xung đột và các ràng buộc của module graph.
6. **Tạo configuration**: nếu graph hợp lệ, Java tạo Configuration chứa các module đã phân giải và quan hệ đọc giữa chúng.
7. **Định nghĩa module trong runtime layer**: module layer gắn các module đã phân giải với class loader theo cách khởi chạy hoặc cách ứng dụng tạo layer.

Ví dụ:

~~~text
Root: com.acme.application
       |
       +-- requires com.acme.customer.api
       |        |
       |        +-- requires com.acme.model
       |
       +-- requires com.acme.logging.api
                |
                +-- requires com.acme.model
~~~

Module com.acme.model được dùng chung bởi hai nhánh. Đây là graph hợp lệ nếu chỉ có một định nghĩa module cùng tên và các package/dependency không xung đột.

Nếu một dependency bắt buộc không tìm thấy, graph không thể được phân giải hoàn chỉnh. Nếu graph chứa hai module cùng export một package cho một consumer đọc cả hai, graph cũng không hợp lệ.

## 8. Các lỗi resolution thường gặp

### FindException

FindException thuộc giai đoạn tìm module. Nó có thể xuất hiện khi:

- Không tìm thấy module được requires.
- Module finder không thể đọc hoặc diễn giải module descriptor.
- Modular JAR bị hỏng hoặc descriptor không hợp lệ.
- Đầu vào tìm kiếm chứa candidate module không thể xử lý theo quy tắc finder.

Ví dụ thông báo thường gặp:

~~~text
java.lang.module.FindException: Module com.acme.customer.api not found
~~~

Hãy kiểm tra module path, tên module thực tế, file JAR có tồn tại và descriptor có đọc được không.

### ResolutionException

ResolutionException xuất hiện khi các module tìm được nhưng cấu hình phụ thuộc không thể tạo thành một module graph hợp lệ.

Một ví dụ điển hình là split package: hai module mà consumer cùng đọc export package trùng tên.

Ví dụ thông báo có thể chỉ ra package bị export từ nhiều module:

~~~text
java.lang.module.ResolutionException:
Modules com.acme.customer.api and com.acme.order.api
export package com.acme.shared.model to module com.acme.application
~~~

Hãy xác định hai module liên quan, package xung đột và module consumer đọc cả hai. Sau đó sửa ranh giới package hoặc dependency graph.

### InvalidModuleDescriptorException

Lỗi này liên quan đến module descriptor không hợp lệ hoặc không thể diễn giải. Kiểm tra module-info.java và artifact được đóng gói: tên module, cú pháp requires/exports, package được khai báo và cấu trúc JAR.

### LayerInstantiationException

Lỗi này có thể xuất hiện khi runtime không thể định nghĩa module layer từ configuration đã phân giải. Nguyên nhân có thể liên quan đến cách gắn module vào class loader, package hoặc trạng thái runtime. Nếu resolution đã thành công nhưng tạo layer thất bại, hãy xem stack trace ở bước defineModules thay vì chỉ kiểm tra requires.

## 9. Module version không tự giải quyết duplicate name

Module descriptor có thể mang metadata version:

~~~java
module com.acme.customer.api {
    exports com.acme.customer.api;
}
~~~

Version của module, nếu được ghi vào descriptor khi đóng gói, là metadata. Cú pháp requires thông thường chỉ chỉ định tên module:

~~~java
module com.acme.application {
    requires com.acme.customer.api;
}
~~~

Nó không có biểu thức như requires com.acme.customer.api version 2.1.

Vì vậy, JPMS không thay thế dependency manager. Maven hoặc Gradle chịu trách nhiệm chọn artifact/version theo dependency graph của dự án; module system dùng tên module trong artifact để liên kết các module ở compile/runtime.

Một dự án có thể chọn đúng Maven coordinate nhưng vẫn gặp va chạm module name nếu hai artifact khác nhau khai báo cùng module name. Ngược lại, hai artifact có tên file khác nhau không đảm bảo chúng có module name khác nhau.

Hãy kiểm tra cả hai lớp thông tin:

- Dependency manager: artifact nào và phiên bản nào được đưa vào runtime.
- Module descriptor: mỗi artifact được nhận diện bằng tên module nào.

## 10. Cách phát hiện duplicate module name và artifact không mong muốn

Trước tiên, liệt kê nội dung và descriptor của các JAR nghi ngờ:

~~~bash
jar --describe-module --file libs/customer-api-1.8.jar
jar --describe-module --file libs/customer-api-2.1.jar
~~~

Nếu cả hai đều báo tên com.acme.customer.api, dependency graph đang chứa hai artifact cùng module name.

Để xem các module hệ thống của JDK:

~~~bash
java --list-modules
~~~

Lệnh này liệt kê module của runtime image; nó không thay thế việc kiểm tra mọi dependency ngoài JDK trong module path ứng dụng.

Để quan sát module được phân giải khi chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.application/com.acme.application.Main
~~~

Log resolution giúp biết module nào được tìm thấy và dependency nào được đưa vào cấu hình. Kết hợp với jar --describe-module để đối chiếu tên module với artifact cụ thể.

Nếu dùng Maven hoặc Gradle, kiểm tra runtime dependency report để tìm nhiều phiên bản hoặc nhiều đường dẫn kéo cùng một thư viện vào. Sau khi loại bỏ dependency dư thừa, chạy lại với --show-module-resolution để xác nhận cấu hình mới.

## 11. Quy trình xử lý lỗi resolution

Khi ứng dụng không khởi động vì module resolution, hãy xử lý theo thứ tự:

1. **Đọc lỗi đầu tiên**: xác định đây là lỗi tìm module, descriptor, graph hay tạo layer.
2. **Xác định tên module liên quan**: lấy tên từ thông báo lỗi hoặc module-info.java.
3. **Kiểm tra artifact**: dùng jar --describe-module cho từng JAR nghi ngờ.
4. **Kiểm tra dependency graph**: xác định module nào đưa artifact vào runtime và có nhiều phiên bản hay không.
5. **Kiểm tra package export**: nếu lỗi là split package, tìm package bị export từ nhiều module và consumer đọc các module đó.
6. **Sửa dependency hoặc module boundary**: chọn một artifact cho mỗi module name, gom package dùng chung về một module, hoặc điều chỉnh requires/exports theo API thực tế.
7. **Chạy lại và quan sát**: dùng --show-module-resolution để xác nhận module graph được tạo đúng.

Không nên sửa bằng cách thêm hàng loạt --add-reads, --add-exports hoặc --add-opens khi lỗi gốc là duplicate module hoặc split package. Những tùy chọn đó không loại bỏ candidate trùng tên và cũng không hợp nhất package bị chia tách.

## 12. Ví dụ minh họa một lỗi do dependency trùng

Giả sử ứng dụng có hai nhánh dependency:

~~~text
com.acme.application
    |
    +-- com.acme.order
    |       |
    |       +-- com.acme.customer.api 1.x
    |
    +-- com.acme.reporting
            |
            +-- com.acme.customer.api 2.x
~~~

Nếu hai phiên bản customer API đều được đóng gói thành module có tên com.acme.customer.api, module path có nhiều candidate cho cùng tên.

Cách giải quyết là đồng bộ dependency version để cả com.acme.order và com.acme.reporting dùng một phiên bản tương thích, hoặc nâng cấp một module trung gian để loại bỏ dependency cũ.

Không nên đổi tên file JAR rồi cho rằng đã giải quyết vấn đề: module name bên trong descriptor vẫn là định danh mà JPMS sử dụng.

Nếu hai phiên bản thật sự cần tồn tại độc lập, cần thiết kế cách cô lập bằng class loader hoặc module layer riêng và xử lý tương thích API một cách tường minh. Đưa cả hai vào cùng một module configuration dưới cùng tên module không tạo ra hai phiên bản độc lập.

## 13. Ghi nhớ

- Tên module là định danh được dùng trong requires và module resolution; tên file JAR và version dependency không thay thế tên đó.
- Hai artifact có thể khác tên file nhưng vẫn khai báo cùng module name.
- Automatic module có thể bị trùng tên qua Automatic-Module-Name hoặc tên file sau chuẩn hóa.
- Module path order và hành vi của module finder có thể ảnh hưởng candidate được tìm thấy; không dùng shadowing để quản lý version.
- Duplicate module name khác split package: một lỗi là trùng định danh module, lỗi kia là trùng package giữa các module được đọc.
- FindException thường liên quan đến tìm hoặc đọc module; ResolutionException thường liên quan đến module graph không nhất quán.
- Module version metadata không phải cơ chế chọn phiên bản trong requires; dùng Maven/Gradle để quản lý dependency.
- Dùng jar --describe-module, dependency report và java --show-module-resolution để xác định artifact và module thực sự được phân giải.

Khi xử lý lỗi resolution, hãy lần từ tên module trong thông báo tới descriptor và artifact tương ứng. Xác định đúng candidate trùng, dependency kéo nó vào hoặc package bị chia sẻ sẽ giúp sửa graph một cách có kiểm soát.
