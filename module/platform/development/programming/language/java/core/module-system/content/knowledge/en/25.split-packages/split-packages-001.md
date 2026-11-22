# Split package là gì?

## 1. Khái niệm split package

Một package trong Java được nhận diện bằng tên package, ví dụ **com.example.logging**. Một **split package** xuất hiện khi các lớp thuộc cùng tên package được phân bố qua nhiều module. Trong môi trường cũ, các lớp đó cũng thường được đóng gói trong nhiều JAR khác nhau trên classpath.

Ví dụ, hai thư viện có cấu trúc:

    logging-api.jar
      com/example/logging/Logger.class

    logging-impl.jar
      com/example/logging/ConsoleLogger.class

Cả hai JAR đều chứa lớp thuộc package **com.example.logging**. Khi các JAR nằm trên classpath của cùng một ứng dụng, chúng thường được nạp vào unnamed module của class loader tương ứng. Vì vậy, việc một package được đóng góp từ nhiều JAR không tự tạo ra lỗi split package của JPMS.

Khi chuyển các JAR thành named modules, tình huống thay đổi. Nếu logging-api.jar và logging-impl.jar trở thành hai module riêng biệt nhưng cùng chứa package **com.example.logging**, đó là split package giữa các named modules. Cấu hình có thể bị module resolution từ chối nếu một module tiêu thụ đọc đồng thời các module cùng export package đó.

Cần phân biệt:

- **Split package:** cùng tên package được phân bố giữa nhiều module hoặc artifact.
- **Duplicate class:** cùng tên nhị phân của một lớp xuất hiện nhiều lần, ví dụ hai JAR cùng chứa **com.example.logging.Logger**.
- **Package dùng chung trên classpath:** nhiều JAR đóng góp các lớp khác nhau vào một package thuộc cùng unnamed module của một class loader. Đây là cách tổ chức có thể hoạt động trên classpath nhưng gây khó khăn khi modular hóa.

## 2. Vì sao split package gây vấn đề trong JPMS?

JPMS tạo ranh giới module để xác định module nào đọc được module nào và package nào được công khai. Nếu cùng một package được export từ nhiều module tới một module tiêu thụ, module tiêu thụ sẽ không có một nguồn package duy nhất rõ ràng.

Ví dụ:

    module com.example.logging.api {
        exports com.example.logging;
    }

    module com.example.logging.impl {
        exports com.example.logging;
    }

    module com.example.application {
        requires com.example.logging.api;
        requires com.example.logging.impl;
    }

Cả hai module thư viện đều export **com.example.logging**, và application đọc cả hai. Module resolution có thể thất bại vì application nhận cùng một package từ hai module khác nhau. Một lỗi điển hình là **ResolutionException** báo các module cùng export một package tới module tiêu thụ.

Không phải mọi lần trùng tên package ở bất kỳ đâu cũng nhất thiết làm toàn bộ runtime thất bại. Xung đột được phát hiện trong quan hệ đọc/export của cấu hình module. Tuy vậy, để thiết kế ổn định, nên tránh để cùng một package thuộc về nhiều named modules có thể được sử dụng đồng thời.

Một module cũng không thể dùng việc thêm quyền truy cập để biến hai package thành một package thống nhất. **exports**, **opens** và **reads** giải quyết quyền truy cập; chúng không hợp nhất nội dung package từ các module khác nhau.

## 3. Split package trên classpath và module path

### Nhiều JAR trên classpath

Classpath truyền thống cho phép nhiều JAR đóng góp lớp vào cùng một package:

    java -cp "lib/logging-api.jar;lib/logging-impl.jar;app.jar" com.example.Main

Trên Windows, dấu phân cách classpath thường là dấu chấm phẩy. Trên Linux và macOS, dùng dấu hai chấm:

    java -cp "lib/logging-api.jar:lib/logging-impl.jar:app.jar" com.example.Main

Các lớp trong cùng package có thể được nhìn thấy như thành phần của unnamed module do class loader tương ứng quản lý. Cách tổ chức này không có module descriptor để xác định ranh giới giữa logging-api và logging-impl.

Nếu hai JAR cùng chứa một lớp có tên đầy đủ giống nhau, class loader thông thường sẽ tìm theo thứ tự đường dẫn classpath. Lớp được tìm thấy trước có thể che khuất bản còn lại. Với class loader tùy biến, hành vi tìm kiếm phụ thuộc cách loader được triển khai.

### Nhiều named modules trên module path

Khi mỗi JAR trở thành một named module, module descriptor xác định package và quan hệ export. Nếu nhiều module cùng chứa package, một module tiêu thụ đọc các module đó có thể gặp lỗi split package trong quá trình resolve.

Ví dụ cấu trúc:

    mods/
      com.example.logging.api.jar
      com.example.logging.impl.jar
      com.example.application.jar

Kiểm tra từng JAR:

    jar --describe-module --file mods/com.example.logging.api.jar
    jar --describe-module --file mods/com.example.logging.impl.jar

Nếu cả hai module đều chứa và export **com.example.logging**, cần xem lại ranh giới module thay vì cố giải quyết bằng cách thêm quyền truy cập ở launcher.

### Automatic modules cũng có thể tạo xung đột

Một JAR không có module-info.class khi đặt trên module path có thể được xem là automatic module. Automatic module export các package của nó theo quy tắc automatic module. Vì vậy, hai JAR legacy cùng chứa package **com.example.logging** khi trở thành hai automatic modules vẫn có thể tạo split package trong cấu hình JPMS.

Việc thêm thuộc tính **Automatic-Module-Name** chỉ đặt tên ổn định cho automatic module. Nó không gộp các package trùng tên và không giải quyết xung đột package.

## 4. Cách nhận diện split package

Bắt đầu bằng việc xem nội dung từng JAR:

    jar --list --file logging-api.jar
    jar --list --file logging-impl.jar

Tìm các đường dẫn có cùng tiền tố package, ví dụ:

    com/example/logging/Logger.class
    com/example/logging/ConsoleLogger.class

Tiếp theo, kiểm tra module descriptor:

    jar --describe-module --file logging-api.jar
    jar --describe-module --file logging-impl.jar

Kết quả giúp xác định tên module, các package được chứa và các package được export. Với explicit module, chú ý dòng **exports** và **contains**. Với automatic module, xem tên module suy ra và danh sách package được xuất.

Có thể kiểm tra danh sách module runtime nhìn thấy:

    java --module-path mods --list-modules

Và xem quá trình resolve:

    java --show-module-resolution \
         --module-path mods \
         --module com.example.application/com.example.application.Main

Nếu cấu hình có xung đột package, thông báo lỗi module resolution thường chỉ ra tên các module và package bị trùng. Hãy dùng đúng tên package và module trong thông báo để lần ngược về JAR chứa lớp.

Đối với dependency phức tạp, **jdeps** giúp xem quan hệ phụ thuộc module và package:

    jdeps --module-path mods --check com.example.application

**jdeps** không thay thế việc đọc nội dung JAR hoặc phân tích module resolution, nhưng có thể giúp xác định module nào đang đọc hoặc phụ thuộc vào thư viện liên quan.

## 5. Cách xử lý split package khi modular hóa

### Gộp các lớp cùng package vào một module

Nếu hai JAR thực chất là các phần của cùng một thư viện và cần cùng sở hữu package, giải pháp rõ ràng thường là đóng gói chúng vào một named module duy nhất.

Ví dụ, thay vì:

    com.example.logging.api
      com.example.logging.Logger

    com.example.logging.impl
      com.example.logging.ConsoleLogger

Có thể tổ chức thành:

    com.example.logging
      com.example.logging.Logger
      com.example.logging.ConsoleLogger

Module descriptor duy nhất:

    module com.example.logging {
        exports com.example.logging;
    }

Việc gộp có thể được thực hiện ở bước build hoặc bằng cách tái cấu trúc artifact. Khi gộp, cần giữ nguyên các dependency, service metadata và tài nguyên cần thiết của thư viện.

### Tách package theo trách nhiệm

Nếu API và implementation có thể độc lập, nên đặt chúng ở các package khác nhau:

    com.example.logging.api
    com.example.logging.internal

Ví dụ:

    module com.example.logging.api {
        exports com.example.logging.api;
    }

    module com.example.logging.impl {
        requires com.example.logging.api;
        provides com.example.logging.api.LoggerProvider
            with com.example.logging.internal.ConsoleLoggerProvider;
    }

Module implementation không cần export package nội bộ nếu ứng dụng chỉ tương tác qua API service. Cách này tạo ranh giới module rõ ràng và giảm khả năng xung đột package.

### Di chuyển lớp sang module sở hữu package

Khi một package đang bị chia giữa nhiều module, xác định module nào là chủ sở hữu hợp lý. Chuyển các lớp còn lại vào module đó hoặc đổi package của chúng để package có một chủ sở hữu duy nhất trong kiến trúc.

Đừng chỉ đổi tên module mà giữ nguyên package ở cả hai nơi; tên module khác nhau không làm split package biến mất.

### Tách module theo các module layer độc lập

Một ứng dụng plugin có thể dùng các module layer riêng để cô lập những nhóm module độc lập. Các layer khác nhau có thể chứa module với cùng tên package mà không tự động hợp nhất chúng thành một package dùng chung.

Cách này chỉ phù hợp khi các plugin thực sự độc lập về kiểu và dependency. Nếu host cần truyền đối tượng thuộc package đó giữa các plugin, hai phía có thể có các lớp khác nhau về danh tính runtime. API chia sẻ giữa host và plugin nên nằm trong một module chung mà cả hai cùng đọc.

## 6. Vai trò và giới hạn của --patch-module

Option **--patch-module** cho phép bổ sung lớp và tài nguyên vào một module đã tồn tại. Nó thường hữu ích trong kiểm thử, instrumentation hoặc khi cần vá module trong một môi trường triển khai có kiểm soát.

Ví dụ:

    java --patch-module com.example.logging=patches/logging \
         --module-path mods \
         --module com.example.application/com.example.application.Main

Các lớp và tài nguyên từ đường dẫn patch được xem như nội dung của module đích trong quá trình chạy. Nếu patch chứa package mà module đích sở hữu, các lớp đó thuộc module đích thay vì tạo một named module mới.

Tuy nhiên, **--patch-module không phải giải pháp tổng quát để hợp nhất hai named modules độc lập**. Nó không thay thế việc thiết kế lại ranh giới module, không sửa các dependency sai và không nên được dùng để che giấu cấu trúc package xung đột lâu dài.

Khi dùng trong test, hãy giới hạn patch path vào đúng module và môi trường test. Không đưa patch nội bộ vào lệnh production nếu không có lý do vận hành rõ ràng.

## 7. Những option không giải quyết split package

| Option | Chức năng | Có hợp nhất package không? |
|---|---|---|
| **--add-modules** | Thêm root module vào quá trình resolve | Không |
| **--add-reads** | Bổ sung quan hệ readability | Không |
| **--add-exports** | Export thêm package cho module đích | Không |
| **--add-opens** | Mở package cho deep reflection | Không |
| **--module-path** | Chỉ định nơi tìm named modules | Không |
| **--patch-module** | Bổ sung lớp/tài nguyên vào module đích | Chỉ bổ sung vào module đích; không tự thiết kế lại các module xung đột |

Ví dụ, nếu application đọc cả hai module cùng export package **com.example.logging**, thêm:

    --add-reads com.example.application=com.example.logging.api

không làm package của hai module trở thành một. Tương tự, --add-exports chỉ điều chỉnh package nào được truy cập, không chuyển lớp từ module này sang module khác.

Cần xác định đúng loại vấn đề: thiếu module, thiếu readability, thiếu export, thiếu open cho reflection hay split package. Mỗi vấn đề có cơ chế xử lý riêng.

## 8. Quy trình chuyển một ứng dụng classpath sang JPMS

Khi một hệ thống cũ có nhiều JAR cùng đóng góp lớp vào package, nên kiểm tra trước khi tạo module descriptor:

1. Liệt kê các JAR dependency và các package mà mỗi JAR chứa.
2. Dùng jar --list để phát hiện package trùng tên giữa các artifact.
3. Dùng jar --describe-module để xác định tên module và package export của các JAR đã modular hoặc automatic.
4. Xác định package nào cần là API công khai, package nào chỉ dùng nội bộ.
5. Gộp các artifact cùng sở hữu một package hoặc tách package theo trách nhiệm.
6. Viết module-info.java với requires, exports, uses và provides phù hợp.
7. Build lại các JAR và kiểm tra module descriptor.
8. Chạy java --validate-modules hoặc ứng dụng với --show-module-resolution để phát hiện xung đột còn lại.
9. Chạy integration test để xác nhận class loading, service discovery và reflection.

Không nên modular hóa bằng cách chỉ thêm module-info.java vào từng JAR mà không xem package layout. Một cấu trúc classpath hợp lệ có thể trở thành cấu hình module không hợp lệ sau khi chia các JAR thành nhiều named modules.

## 9. Ví dụ minh họa

Giả sử hai JAR cũ:

    legacy-api.jar
      com/example/payment/Payment.class
      com/example/payment/PaymentRequest.class

    legacy-adapter.jar
      com/example/payment/LegacyPaymentAdapter.class

Khi chạy classpath:

    java -cp "legacy-api.jar;legacy-adapter.jar;app.jar" com.example.Main

Các lớp trên có thể cùng thuộc package của unnamed module do application class loader quản lý.

Nếu chuyển thành hai module:

    module com.example.payment.api {
        exports com.example.payment;
    }

    module com.example.payment.adapter {
        exports com.example.payment;
    }

và application yêu cầu cả hai:

    module com.example.application {
        requires com.example.payment.api;
        requires com.example.payment.adapter;
    }

thì application đọc hai module cùng export **com.example.payment**. Module resolution có thể từ chối cấu hình vì split package.

Một thiết kế thay thế là đổi package implementation:

    module com.example.payment.api {
        exports com.example.payment.api;
    }

    module com.example.payment.adapter {
        requires com.example.payment.api;
        exports com.example.payment.adapter;
    }

Các lớp được tổ chức lại:

    com/example/payment/api/Payment.class
    com/example/payment/api/PaymentRequest.class
    com/example/payment/adapter/LegacyPaymentAdapter.class

Application chỉ cần đọc API và module adapter. Package đã có ranh giới rõ ràng, không còn cùng một package được export từ hai module.

## 10. Ghi nhớ

- Split package là tình trạng cùng tên package được chia giữa nhiều module.
- Trên classpath, nhiều JAR có thể đóng góp lớp vào package của unnamed module; điều này không đồng nghĩa với xung đột split package của JPMS.
- Trên module path, nhiều named modules cùng export một package tới một module tiêu thụ có thể khiến module resolution thất bại.
- Automatic modules cũng có thể gây xung đột package khi nhiều JAR cùng chứa package và cùng được đọc.
- Split package khác duplicate class: một trường hợp chia các lớp trong package, trường hợp kia lặp lại cùng tên lớp.
- **--add-reads**, **--add-exports** và **--add-opens** không hợp nhất package.
- **--patch-module** bổ sung nội dung vào module đích nhưng không thay thế một thiết kế module tốt.
- Ưu tiên gộp các artifact cùng sở hữu package hoặc tách package theo trách nhiệm.
- Với plugin độc lập, module layer có thể hỗ trợ cô lập, nhưng API dùng chung cần nằm trong module được chia sẻ.
- Dùng **jar --list**, **jar --describe-module**, **jdeps** và **--show-module-resolution** để tìm nguồn xung đột.

**Split package thường bộc lộ vấn đề ranh giới thư viện khi một ứng dụng chuyển từ classpath sang JPMS.** Cách xử lý bền vững là xác định một module sở hữu mỗi package API, tổ chức lại package và khai báo dependency rõ ràng.

## Tài liệu tham khảo

- Java Language Specification, Java SE 21 — Packages: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- Java SE 21 API — java.lang.module package: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 Tool Specifications — jar: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html