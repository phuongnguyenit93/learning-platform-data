# Di chuyển package để sửa split package trong Java Module System

## 1. Mục tiêu

Trong dự án Java chạy trên classpath, nhiều JAR có thể cùng chứa class thuộc một package. Khi chuyển sang Java Platform Module System (JPMS), cách tổ chức này có thể tạo ra **split package**: cùng một tên package xuất hiện trong nhiều module.

Một split package trở thành vấn đề khi module graph khiến một module đọc được nhiều module cùng chứa hoặc export package đó. Resolver không thể tạo một cách nhìn package nhất quán cho module tiêu thụ, vì vậy quá trình resolution có thể thất bại với lỗi dạng:

~~~text
Module com.example.app reads package com.example.shared
from both com.example.alpha and com.example.beta
~~~

Cách xử lý bền vững là xác định module sở hữu package, sau đó di chuyển toàn bộ phần package liên quan về một module duy nhất hoặc đổi tên package nếu các phần thực sự thuộc hai miền độc lập. Cần cập nhật cả source tree, module descriptor và các tham chiếu đi kèm.

Sau bài này, bạn có thể:

- Nhận diện split package và hiểu điều kiện khiến module resolution xung đột.
- Chọn module sở hữu package dựa trên trách nhiệm và dependency.
- Di chuyển source mà không bỏ sót package declaration, module descriptor, resource và test.
- Xử lý dependency mới mà không tạo vòng phụ thuộc.
- Biên dịch và kiểm tra lại module graph sau khi refactor.

## 2. Split package là gì?

Giả sử có hai module:

- `com.example.alpha`
- `com.example.beta`

Cả hai đều chứa class trong package `com.example.shared`:

~~~text
src/
├── com.example.alpha/
│   ├── module-info.java
│   └── com/example/shared/AlphaHelper.java
└── com.example.beta/
    ├── module-info.java
    └── com/example/shared/BetaHelper.java
~~~

Module descriptor có thể đang export cùng package:

~~~java
// com.example.alpha/module-info.java
module com.example.alpha {
    exports com.example.shared;
}
~~~

~~~java
// com.example.beta/module-info.java
module com.example.beta {
    exports com.example.shared;
}
~~~

Ứng dụng tiêu thụ cả hai:

~~~java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
~~~

Khi app đọc cả hai module và cả hai module đều export `com.example.shared`, resolver gặp hai nguồn cùng cung cấp một package cho cùng module tiêu thụ. Đây là trường hợp split package điển hình và có thể khiến configuration không resolve được.

Không nên hiểu rằng chỉ cần nhìn thấy cùng tên package ở bất kỳ hai module nào là mọi cấu hình đều lập tức lỗi. Quy tắc resolution quan trọng là một module không thể đọc nhiều module cùng export package đó. Dù vậy, việc chia một package thành nhiều module thường làm ranh giới sở hữu và quyền truy cập khó hiểu; nên thiết kế để package có một module owner rõ ràng.

## 3. Vì sao classpath có thể chạy nhưng named modules lại gặp lỗi?

Trên classpath, các JAR thường được nạp vào unnamed module. Class loader có thể tìm class cùng package từ nhiều JAR, miễn là không phát sinh vấn đề khác như trùng class name hoặc thứ tự classpath.

Với named modules, module descriptor xác định module nào sở hữu package và module nào được đọc package đó. Module system kiểm tra quan hệ này khi xây dựng configuration. Việc một package bị chia giữa nhiều module có thể làm một consumer đọc nhiều nguồn package trùng tên, tạo ra sự mơ hồ.

Ngoài lỗi resolution, package-private access cũng cần chú ý. Hai class cùng khai báo `package com.example.shared;` nhưng nằm trong hai named module khác nhau không mặc nhiên thuộc cùng một runtime package để truy cập package-private members của nhau. Cùng tên package trong source không xóa ranh giới module.

Vì vậy, split package không chỉ là vấn đề đặt file trong thư mục nào. Nó liên quan đến module ownership, readability, exports và encapsulation.

## 4. Chọn module sở hữu package trước khi di chuyển

Trước khi sửa file, xác định package thuộc trách nhiệm nào.

Có ba hướng thường dùng:

1. **Chuyển toàn bộ package vào một module hiện có:** phù hợp khi các class thực sự là một phần của module đó. Module còn lại sẽ phụ thuộc vào module owner.
2. **Tạo module dùng chung có trách nhiệm rõ ràng:** phù hợp khi package là API hoặc capability được nhiều module dùng độc lập. Tránh biến module này thành một kho chứa các class tiện ích không liên quan.
3. **Tách thành hai package có tên riêng:** phù hợp khi class cùng package hiện tại thực ra thuộc hai miền nghiệp vụ khác nhau. Đổi package để mỗi miền có namespace riêng, rồi đặt từng package trong module sở hữu tương ứng.

Không chọn module chỉ vì nó đang có sẵn một vài class trong package. Hãy xét dependency của class, API công khai, vòng đời, quyền sở hữu và khả năng tránh dependency cycle.

Nếu alpha cần beta và beta lại cần alpha sau khi di chuyển, không nên thêm hai chiều `requires` để ép build. Hãy tách contract ổn định sang một module API nhỏ hoặc điều chỉnh ranh giới trách nhiệm.

## 5. Ví dụ: gom package vào một module owner

Giả sử `com.example.shared` là package dùng chung thật sự. Ta tạo module owner `com.example.shared` và chuyển cả hai class về đó.

Trước khi di chuyển:

~~~text
src/
├── com.example.alpha/
│   ├── module-info.java
│   └── com/example/shared/AlphaHelper.java
├── com.example.beta/
│   ├── module-info.java
│   └── com/example/shared/BetaHelper.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Sau khi di chuyển:

~~~text
src/
├── com.example.shared/
│   ├── module-info.java
│   └── com/example/shared/
│       ├── AlphaHelper.java
│       └── BetaHelper.java
├── com.example.alpha/
│   └── module-info.java
├── com.example.beta/
│   └── module-info.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Module owner khai báo:

~~~java
module com.example.shared {
    exports com.example.shared;
}
~~~

Hai module alpha và beta khai báo dependency:

~~~java
module com.example.alpha {
    requires com.example.shared;
}
~~~

~~~java
module com.example.beta {
    requires com.example.shared;
}
~~~

Module app vẫn yêu cầu alpha và beta nếu nó dùng API của cả hai:

~~~java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
~~~

Nếu app cần gọi trực tiếp class trong `com.example.shared`, app cũng cần khai báo `requires com.example.shared;`. Readability không tự động truyền từ alpha sang app theo cách khiến app đọc mọi dependency của alpha; `requires` thông thường không có tính transitive.

Sau thay đổi, chỉ module `com.example.shared` chứa và export package `com.example.shared`. Alpha và beta sử dụng package đó qua dependency tới owner.

Nếu các helper chỉ phục vụ nội bộ alpha hoặc beta, hãy cân nhắc chuyển chúng vào package riêng của module tương ứng thay vì tạo module shared. Mục tiêu là một package có một owner hợp lý, không phải tạo thêm module cho mọi nhóm class.

## 6. Các bước di chuyển source

Thực hiện di chuyển theo trình tự có thể kiểm soát:

1. **Liệt kê class trong package:** tìm mọi file có khai báo `package com.example.shared;` trong các source root của module. Xác định class, `package-info.java`, file test và resource liên quan.
2. **Chọn owner:** quyết định module sẽ chứa package sau refactor. Kiểm tra dependency của class để tránh tạo vòng `requires`.
3. **Di chuyển file:** đưa các source file vào đúng thư mục package dưới source root của owner. Nếu đổi tên package, cập nhật cả thư mục và câu lệnh `package` trong source.
4. **Cập nhật module descriptor:** thêm `exports` hoặc qualified `exports` ở owner khi consumer cần truy cập API. Thêm `requires` ở consumer; xóa export cũ khỏi module không còn sở hữu package.
5. **Cập nhật tham chiếu:** sửa import nếu package name đổi. Nếu giữ nguyên package name nhưng đổi module owner, import Java có thể không đổi, nhưng module descriptor và dependency build phải đổi.
6. **Di chuyển test và resource:** đặt test theo module mới; kiểm tra resource path, `module-info.java`, test fixture và cấu hình đóng gói.
7. **Build toàn bộ consumer:** biên dịch module owner trước hoặc trong cùng lượt modular compilation, sau đó biên dịch mọi module phụ thuộc và chạy test.

Không để lại một phần class của package trong module cũ. Sau khi di chuyển, module cũ không còn source hoặc package output thuộc package đó.

## 7. Những tham chiếu thường bị bỏ sót

Di chuyển package không chỉ ảnh hưởng các file Java có import trực tiếp.

- **`package-info.java`:** annotation và Javadoc gắn với package phải đi cùng package owner hoặc được cập nhật khi đổi tên.
- **`module-info.java`:** cập nhật `exports`, `opens`, `uses`, `provides` nếu package chứa service type hoặc provider implementation.
- **Reflection:** chuỗi tên class/package trong `Class.forName`, cấu hình framework, dependency injection, serialization hoặc mapping cần được cập nhật nếu package name đổi.
- **Resource:** kiểm tra file được nạp bằng `Class.getResource`, `ClassLoader.getResource` hoặc đường dẫn resource tương đối với package.
- **Service provider:** nếu implementation được khai báo bằng `provides Service with Provider`, bảo đảm provider class vẫn ở module phù hợp và descriptor đã cập nhật. Nếu dùng classpath service configuration, cập nhật file `META-INF/services`.
- **Test và build:** cập nhật source set, test module descriptor, module path, cấu hình plugin, Javadoc và script chạy.
- **API consumers:** nếu class công khai chuyển sang module khác, các module tiêu thụ phải đọc module mới và module owner phải export package cần thiết.

Nếu package name không đổi, các import có thể vẫn biên dịch như cũ sau khi module dependency được cập nhật. Tuy nhiên, điều đó không có nghĩa migration đã hoàn tất: module graph, resource và reflection vẫn cần được kiểm tra.

## 8. Khi cần đổi tên package thay vì gom chung

Không phải hai nhóm class cùng tên package đều nên đặt trong một module. Ví dụ, một thư viện bên thứ ba và code nội bộ cùng sử dụng package `com.example.util`, nhưng chúng không chia sẻ trách nhiệm hoặc API.

Có thể đổi package của code nội bộ thành namespace riêng:

Trước:

~~~java
package com.example.util;

public final class InternalDateParser {
    // ...
}
~~~

Sau:

~~~java
package com.example.app.internal.date;

public final class InternalDateParser {
    // ...
}
~~~

Cấu trúc thư mục tương ứng:

~~~text
com.example.app/
├── module-info.java
└── com/example/app/internal/date/
    └── InternalDateParser.java
~~~

Cách này giữ code nội bộ trong module app và tránh tranh chấp package với thư viện. Đổi package name là thay đổi tên đầy đủ của class (fully qualified name), vì vậy cần cập nhật consumer, cấu hình reflection, serialization và các dữ liệu lưu tên class.

Đối với API công khai đã phát hành, đổi package có thể là breaking change. Cần có kế hoạch versioning, migration guide hoặc lớp facade/adapter trong giai đoạn chuyển tiếp nếu tương thích ngược là yêu cầu.

## 9. Biên dịch và kiểm tra sau khi di chuyển

Với source tree modular, có thể biên dịch các module liên quan bằng:

~~~bash
javac --module-source-path src -d out \
    -m com.example.shared,com.example.alpha,com.example.beta,com.example.app
~~~

Nếu owner đã được build thành modular JAR, đặt JAR đó trên module path khi biên dịch consumer:

~~~bash
javac --module-path libs -d out \
    --module-source-path src \
    -m com.example.alpha,com.example.beta,com.example.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Có thể kiểm tra descriptor của owner:

~~~bash
java --module-path out --describe-module com.example.shared
~~~

Và quan sát graph khi chạy:

~~~bash
java --show-module-resolution --module-path out \
    --module com.example.app/com.example.app.Main
~~~

Khi xác nhận migration:

- Build tất cả module có dependency tới package.
- Chạy unit test và integration test của owner cùng các consumer.
- Xác nhận module owner export đúng package cần thiết.
- Xác nhận module cũ không còn chứa package đó trong output hoặc JAR.
- Tìm lại package declaration để bảo đảm không còn bản sao ngoài dự kiến.
- Kiểm tra cấu hình reflection, service provider và resource.
- Kiểm tra artifact phát hành cuối cùng, không chỉ source tree trong IDE.

Nếu dùng modular JAR, có thể xem nội dung module bằng:

~~~bash
jar --describe-module --file libs/com.example.shared.jar
~~~

## 10. Vì sao không nên dùng workaround để che split package?

Một số tùy chọn runtime có thể giúp xử lý vấn đề module access, nhưng chúng không phải giải pháp tổng quát cho split package:

- `--add-reads` bổ sung readability, không hợp nhất package từ hai module.
- `--add-exports` cấp quyền truy cập package, không chuyển quyền sở hữu package.
- `--add-opens` phục vụ deep reflection, không sửa package conflict trong module graph.
- `--patch-module` thêm class/resource vào một module cụ thể và có thể dùng trong test hoặc compatibility workaround; nó không thay thế việc xác định module owner và đóng gói source đúng cách.

Nếu lỗi resolution nói một consumer đọc cùng package từ hai module, hãy sửa cấu trúc package/module hoặc quan hệ module sao cho consumer chỉ còn một nguồn package. Thêm quyền truy cập không loại bỏ nguyên nhân.

## 11. Ghi nhớ

- Split package là tình trạng cùng tên package xuất hiện trong nhiều module.
- Xung đột điển hình xảy ra khi một module đọc hai module cùng export package đó.
- Chọn một module owner cho package; chuyển toàn bộ class liên quan về owner hoặc đổi tên package khi hai nhóm code thuộc các miền độc lập.
- Cập nhật `requires`, `exports`, `opens`, `uses`, `provides` và các consumer phù hợp.
- Kiểm tra package-private access, reflection, resource, service provider, test và build script sau khi di chuyển.
- Build toàn bộ module graph và xác nhận module cũ không còn chứa package đã chuyển.

Hãy bắt đầu bằng việc xác định package nào đang có nhiều owner và module nào thực sự cần sở hữu nó. Một lần di chuyển có kiểm soát, đi kèm cập nhật descriptor và consumer, sẽ loại bỏ xung đột tận gốc và giữ cho ranh giới module rõ ràng.
