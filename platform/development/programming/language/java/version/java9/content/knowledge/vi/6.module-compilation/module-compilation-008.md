# Phát hiện split package và xung đột tên mô-đun trong JPMS

## Mục tiêu

Khi chuyển một ứng dụng Java sang Java Platform Module System (JPMS), các thư viện có thể mang theo package hoặc tên mô-đun trùng nhau. Một ứng dụng có thể biên dịch thành công nhưng vẫn không khởi tạo được module layer vì cấu trúc mô-đun không hợp lệ. Một trường hợp khác là hai JAR cùng khai báo một tên mô-đun, khiến một phiên bản bị che khuất trên module path.

Bài này giúp bạn:

- Phân biệt split package với xung đột tên mô-đun.
- Hiểu vì sao hai mô-đun có thể biên dịch riêng nhưng không thể cùng tồn tại trong một module layer.
- Phát hiện module name bị trùng, kể cả khi một JAR là automatic module.
- Dùng công cụ JDK hiện đại để kiểm tra module path và dependency.
- Xử lý xung đột tại nguồn dependency hoặc ranh giới package một cách có kiểm soát.

## 1. Hai loại xung đột khác nhau

JPMS quản lý mô-đun và package như hai cấp tên riêng biệt. Vì vậy, cần phân biệt:

| Vấn đề | Điều bị trùng | Hậu quả thường gặp |
|---|---|---|
| Split package | Tên package xuất hiện trong nhiều named module cùng được phân giải vào một module layer | Module layer không thể được khởi tạo hợp lệ |
| Duplicate module name | Hai hoặc nhiều đầu vào trên module path khai báo cùng tên mô-đun | Một định nghĩa mô-đun có thể bị shadow bởi định nghĩa đứng trước trên module path |
| Duplicate class | Cùng tên đầy đủ của lớp xuất hiện trong nhiều artifact | Có thể gây lỗi biên dịch, nạp lớp hoặc hành vi phụ thuộc vào classpath/module path |

Hai khái niệm đầu tiên không giống nhau:

- **Split package** liên quan đến tên package, ví dụ **com.acme.shared**, xuất hiện trong cả **com.acme.alpha** và **com.acme.beta**.
- **Duplicate module name** liên quan đến tên mô-đun, ví dụ cả hai JAR đều khai báo **module com.acme.logging**.

Một dự án có thể gặp cả hai vấn đề cùng lúc. Cần kiểm tra package ownership và module identity độc lập.

## 2. Split package là gì?

Split package xảy ra khi cùng một tên package được chứa trong nhiều named module. Ví dụ:

~~~text
com.acme.alpha
└── package com.acme.shared
    └── Alpha.java

com.acme.beta
└── package com.acme.shared
    └── Beta.java
~~~

Hai mô-đun có thể chứa các lớp khác nhau:

~~~java
// Trong mô-đun com.acme.alpha
package com.acme.shared;

public class Alpha {
    public static String name() {
        return "alpha";
    }
}
~~~

~~~java
// Trong mô-đun com.acme.beta
package com.acme.shared;

public class Beta {
    public static String name() {
        return "beta";
    }
}
~~~

Dù **Alpha** và **Beta** có tên lớp khác nhau, cả hai đều thuộc package **com.acme.shared**. Nếu hai mô-đun cùng được đưa vào một module layer, package đó bị chia sẻ giữa các named module và cấu hình không hợp lệ.

Split package thường xuất hiện khi:

- Hai thư viện được phát triển độc lập nhưng vô tình dùng chung namespace package.
- Một thư viện bị chia thành nhiều JAR trong khi các JAR vẫn chứa các lớp thuộc cùng package.
- Một dependency được fork hoặc shade nhưng giữ nguyên package cũ.
- Ứng dụng ghép nhiều phiên bản hoặc nhiều biến thể artifact của cùng một thư viện.
- Quá trình chuyển từ classpath sang module path làm lộ ra ranh giới package vốn trước đó chưa được kiểm soát bởi JPMS.

### Vì sao classpath có thể che giấu vấn đề?

Trên classpath, nhiều JAR có thể đóng góp các lớp thuộc cùng package vào unnamed module. Cách tổ chức đó vẫn có thể chạy, miễn là không phát sinh xung đột lớp hoặc vấn đề class loader khác.

Khi chuyển các JAR thành named module hoặc automatic module trên module path, mỗi mô-đun có ranh giới package riêng. JPMS không cho phép cùng một package bị chia giữa nhiều named module trong cùng module layer.

Vì vậy, việc một ứng dụng chạy được trên classpath không chứng minh rằng các artifact của nó có thể chuyển nguyên trạng sang module path.

## 3. Split package được phát hiện ở giai đoạn nào?

Một điểm quan trọng là bước biên dịch và bước phân giải mô-đun có trách nhiệm khác nhau.

Hai mô-đun có cùng package có thể được biên dịch thành công khi biên dịch nguồn của chúng. Tuy nhiên, khi module resolver cố gắng đưa cả hai vào cùng một module layer, kiểm tra package ownership sẽ phát hiện xung đột.

Do đó:

- **javac** thành công chưa đủ chứng minh module path hợp lệ.
- **java --validate-modules** có thể phát hiện split package trước khi khởi chạy ứng dụng.
- Khi launcher khởi tạo boot layer, split package có thể làm quá trình khởi chạy thất bại.

Thông báo lỗi có thể khác theo phiên bản JDK và cách các mô-đun được cung cấp. Hãy tập trung vào tên package và mô-đun được nêu trong thông báo.

## 4. Xung đột tên mô-đun là gì?

Mỗi named module có một tên định danh. Với explicit module, tên này được khai báo trong **module-info.java**:

~~~java
module com.acme.logging {
    exports com.acme.logging.api;
}
~~~

Một modular JAR chứa module descriptor đã biên dịch sẽ mang tên mô-đun được khai báo ở đó. Tên file JAR không quyết định tên explicit module.

Ví dụ, hai file:

~~~text
libs/
├── logging-1.2.jar
└── logging-2.0.jar
~~~

có thể cùng khai báo:

~~~java
module com.acme.logging {
    exports com.acme.logging.api;
}
~~~

Khi cả hai nằm trên cùng module path, chúng tạo ra hai định nghĩa cho tên mô-đun **com.acme.logging**.

Module path không phải cơ chế để nạp đồng thời hai phiên bản của cùng một named module trong một module layer. Khi tìm thấy nhiều định nghĩa cùng tên, module finder có thể chọn định nghĩa xuất hiện trước và báo các định nghĩa sau bị **shadowed** (che khuất).

Đây là xung đột dependency dù không nhất thiết làm **java --validate-modules** trả về lỗi khác 0. Kết quả thực tế có thể phụ thuộc thứ tự các mục trên module path. Nếu JAR đầu tiên không phải phiên bản ứng dụng mong đợi, chương trình có thể chạy với API hoặc implementation khác dự kiến.

Không nên dựa vào thứ tự module path để âm thầm chọn phiên bản. Hãy loại bỏ định nghĩa dư thừa và giữ một phiên bản dependency có chủ đích.

## 5. Tên mô-đun đến từ đâu?

Có ba trường hợp thường gặp:

### Explicit module

Mô-đun có **module-info.java**, ví dụ:

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
}
~~~

Tên mô-đun là **com.acme.payment**. Tên JAR có thể khác, nhưng module descriptor xác định tên khi JAR được xử lý trên module path.

### Automatic module

JAR không có module descriptor nhưng được đặt trên module path có thể trở thành automatic module. Tên của nó được xác định theo thứ tự:

1. Thuộc tính manifest **Automatic-Module-Name**, nếu có.
2. Nếu không có, tên được suy ra từ tên file JAR theo quy tắc đặt tên automatic module của Java.

Ví dụ, hai thư viện có thể có tên file khác nhau nhưng cùng khai báo **Automatic-Module-Name: com.acme.common**. Khi cùng xuất hiện trên module path, chúng vẫn xung đột tên mô-đun.

Với thư viện chưa có module descriptor nhưng cần giữ tên module ổn định cho người dùng JPMS, **Automatic-Module-Name** là cách khai báo tên tương thích trong manifest. Khi thư viện chuyển sang explicit module, tên trong **module-info.java** nên tiếp tục giữ đúng tên đã công bố.

### Unnamed module

Mã chạy từ classpath thuộc unnamed module của class loader tương ứng. Unnamed module không có tên explicit để so sánh như named module. Quy tắc split package giữa các named module cần được phân biệt với việc nhiều JAR cùng đóng góp package trên classpath.

Khi kiểm tra xung đột trên module path, hãy xác định JAR nào đang trở thành explicit hoặc automatic module.

## 6. Cách phát hiện split package và module name bị trùng

### Bước 1: Kiểm tra module path

Xác định toàn bộ thư mục và JAR được truyền qua **--module-path** hoặc **-p**. Trên Windows, dấu phân cách giữa các mục path là dấu chấm phẩy **;**; trên Linux và macOS là dấu hai chấm **:**.

Ví dụ trên Windows:

~~~powershell
java --validate-modules --module-path "mods;libs"
~~~

Ví dụ trên Linux/macOS:

~~~bash
java --validate-modules --module-path "mods:libs"
~~~

Lệnh **--validate-modules** yêu cầu runtime kiểm tra tính hợp lệ của các mô-đun được tìm thấy trên module path rồi kết thúc. Đây là bước chẩn đoán hữu ích trước khi chạy ứng dụng.

### Bước 2: Đọc module descriptor của từng JAR

Dùng:

~~~bash
jar --describe-module --file libs/example.jar
~~~

Lệnh này cho biết tên mô-đun, package được chứa, dependency, package được xuất và main class metadata nếu có.

Thực hiện với các JAR nghi ngờ trùng tên. Nếu hai artifact có cùng tên mô-đun, cần xác định dependency nào thực sự được ứng dụng sử dụng.

### Bước 3: Kiểm tra dependency của mô-đun

Dùng **jdeps** để xem dependency và kiểm tra module descriptor:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

**jdeps --check** giúp kiểm tra quan hệ dependency của mô-đun và đưa ra đồ thị dependency được đề xuất. Nó hỗ trợ phân tích module descriptor; khi cần phát hiện split package trên module path, hãy dùng thêm **java --validate-modules**.

### Bước 4: Xem quá trình phân giải

Khi chạy ứng dụng, có thể yêu cầu launcher hiển thị module resolution:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Thông tin này giúp xác định mô-đun nào được tìm thấy và được phân giải từ vị trí nào. Kết hợp với **jar --describe-module** để truy ngược artifact cung cấp mô-đun.

## 7. Ví dụ: hai mô-đun chia sẻ cùng package

Tạo cấu trúc:

~~~text
src/
├── com.acme.alpha/
│   ├── module-info.java
│   └── com/acme/shared/Alpha.java
└── com.acme.beta/
    ├── module-info.java
    └── com/acme/shared/Beta.java
~~~

Tệp **src/com.acme.alpha/module-info.java**:

~~~java
module com.acme.alpha {
    exports com.acme.shared;
}
~~~

Tệp **src/com.acme.alpha/com/acme/shared/Alpha.java**:

~~~java
package com.acme.shared;

public class Alpha {
    public static String name() {
        return "alpha";
    }
}
~~~

Tệp **src/com.acme.beta/module-info.java**:

~~~java
module com.acme.beta {
    exports com.acme.shared;
}
~~~

Tệp **src/com.acme.beta/com/acme/shared/Beta.java**:

~~~java
package com.acme.shared;

public class Beta {
    public static String name() {
        return "beta";
    }
}
~~~

Biên dịch cả hai mô-đun:

~~~bash
javac --release 17 -d out --module-source-path src -m com.acme.alpha,com.acme.beta
~~~

Trên JDK 24, bước biên dịch ví dụ này thành công. Sau đó kiểm tra module path:

~~~bash
java --validate-modules --module-path out
~~~

Kết quả chẩn đoán có dòng:

~~~text
contains com.acme.shared conflicts with module com.acme.alpha
~~~

và runtime báo validation module path thất bại. Đây là ví dụ cho thấy việc biên dịch thành công không đồng nghĩa các mô-đun có thể cùng tồn tại trong một module layer.

### Sửa split package

Nếu hai package thực sự đại diện cho hai API độc lập, hãy đổi namespace để mỗi mô-đun sở hữu package riêng:

~~~text
com.acme.alpha
└── package com.acme.alpha.api

com.acme.beta
└── package com.acme.beta.api
~~~

Cập nhật module descriptor tương ứng:

~~~java
module com.acme.alpha {
    exports com.acme.alpha.api;
}
~~~

~~~java
module com.acme.beta {
    exports com.acme.beta.api;
}
~~~

Sau đó di chuyển các lớp vào package mới và cập nhật import/caller. Khi biên dịch và chạy **java --validate-modules --module-path out**, module path không còn xung đột package.

Nếu hai nhóm lớp vốn thuộc cùng một API và cần ở cùng package, hãy gom chúng về một mô-đun sở hữu package đó. Đừng tạo hai named module chỉ để chia các lớp của một package thành hai phần.

## 8. Ví dụ: hai JAR khai báo cùng tên mô-đun

Giả sử có hai JAR khác vị trí:

~~~text
vendor-a/shared-one.jar
vendor-b/shared-two.jar
~~~

Cả hai đều có module descriptor khai báo:

~~~java
module com.acme.sharedmod {
    exports com.acme.sharedmod;
}
~~~

Kiểm tra từng JAR:

~~~bash
jar --describe-module --file vendor-a/shared-one.jar
jar --describe-module --file vendor-b/shared-two.jar
~~~

Sau đó kiểm tra cả hai cùng trên module path:

~~~bash
java --validate-modules --module-path "vendor-a;vendor-b"
~~~

Trên hệ thống Unix-like, dùng dấu hai chấm để phân tách path. Nếu hai JAR có cùng module name, output có thể ghi nhận một JAR bị **shadowed by** JAR còn lại.

Thử đảo thứ tự module path có thể làm artifact bị shadow thay đổi. Điều đó chứng minh thứ tự tìm kiếm ảnh hưởng đến định nghĩa mô-đun được chọn. Đây là dấu hiệu cần sửa dependency graph thay vì coi kết quả thứ tự là một cơ chế chọn phiên bản đáng tin cậy.

## 9. Cách xử lý theo nguyên nhân

| Nguyên nhân | Cách xử lý phù hợp |
|---|---|
| Hai mô-đun sở hữu cùng package | Thiết kế lại namespace hoặc gom package về một mô-đun duy nhất |
| Hai phiên bản của cùng thư viện cùng nằm trên module path | Chọn một phiên bản tương thích và loại phiên bản dư thừa khỏi runtime dependency |
| Dependency bắc cầu kéo vào một artifact trùng | Dùng dependency insight/tree của Gradle hoặc Maven để tìm đường phụ thuộc, rồi exclude hoặc điều chỉnh dependency có chủ đích |
| Hai JAR khác nhau nhưng cùng Automatic-Module-Name | Chọn một artifact hoặc yêu cầu nhà cung cấp dùng module name ổn định, duy nhất |
| JAR chưa có module descriptor và tên tự suy ra bị trùng | Ưu tiên bản thư viện có module descriptor hoặc manifest Automatic-Module-Name ổn định |
| Một thư viện bị fork nhưng giữ package gốc | Xác định package nào thuộc API chung; chọn một bản hoặc thực hiện relocation có kiểm soát nếu tương thích cho phép |

### Thận trọng khi relocation package

Relocation (đổi namespace package khi đóng gói, thường thông qua shading) có thể giải quyết xung đột package trong một số trường hợp. Tuy nhiên, đổi tên package làm thay đổi tên đầy đủ của lớp. Nó có thể ảnh hưởng đến:

- Mã nguồn và binary consumer đang tham chiếu package cũ.
- Reflection, cấu hình framework và tên lớp được lưu trong cấu hình.
- Service provider metadata và resource đi kèm.
- Dữ liệu serialization hoặc dữ liệu lưu trữ chứa tên lớp.

Chỉ relocation khi bạn kiểm soát được phạm vi tương thích và đã kiểm thử các đường sử dụng liên quan. Với thư viện công khai, chọn artifact/module variant phù hợp hoặc thay đổi package ở nguồn thường an toàn hơn.

## 10. Quy trình kiểm tra trong dự án thực tế

Khi một ứng dụng gặp lỗi module resolution, thực hiện lần lượt:

1. Ghi lại chính xác module path mà lệnh chạy hoặc build tool tạo ra.
2. Liệt kê các JAR và thư mục mô-đun thực sự có trên module path.
3. Dùng **jar --describe-module** để lấy tên mô-đun và package của các artifact nghi ngờ.
4. Chạy **java --validate-modules --module-path ...** để phát hiện split package và các vấn đề module path.
5. Dùng **jdeps --check** để kiểm tra dependency descriptor của mô-đun.
6. Xem dependency tree của Gradle/Maven để xác định artifact nào kéo phiên bản trùng vào runtime.
7. Sửa dependency hoặc package ownership tại nguồn.
8. Chạy lại compile, module validation và ứng dụng trên JDK baseline được hỗ trợ.

Không nên chỉ kiểm tra source code của project chính. Xung đột thường đến từ dependency bắc cầu hoặc các JAR được đóng gói ở một bước khác của pipeline.

## 11. Checklist trước khi phát hành ứng dụng modular

- Mỗi named module có tên định danh rõ ràng và duy nhất trong module path được triển khai.
- Không có hai named module cùng sở hữu một package trong module layer.
- Không có artifact cũ bị shadow bởi phiên bản khác cùng module name.
- Automatic module có tên ổn định nếu được sử dụng lâu dài.
- Các dependency bắc cầu được kiểm tra từ runtime dependency graph thực tế.
- **java --validate-modules** chạy thành công trên tập mô-đun triển khai.
- **jar --describe-module** xác nhận đúng module name và package của các JAR.
- Ứng dụng được chạy thử bằng đúng module path và JDK mục tiêu.

## Kết luận

Split package là xung đột ở cấp package: nhiều named module cùng chứa một package trong một module layer. Duplicate module name là xung đột ở cấp định danh mô-đun: nhiều artifact cùng khai báo một tên, khiến một định nghĩa có thể bị shadow theo thứ tự module path.

Hãy dùng **java --validate-modules** để kiểm tra module path, **jar --describe-module** để xác nhận module name/package của từng JAR và **jdeps --check** để phân tích dependency. Khi tìm thấy xung đột, xử lý package ownership hoặc dependency graph tại nguồn. Cách này giúp module layer có cấu trúc rõ ràng và ứng dụng modular chạy nhất quán trên các JDK hiện đại.
