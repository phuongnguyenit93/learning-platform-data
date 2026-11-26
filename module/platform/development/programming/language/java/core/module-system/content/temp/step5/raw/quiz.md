Câu 1. Vai trò chính của tệp `module-info.java` trong một Java named module là gì?
A. Thiết lập đường dẫn module path của JVM lúc ứng dụng chạy.
B. Khai báo tên module, dependency và khả năng export package.
C. Điều khiển JVM chọn class loader cho từng package trong module.
D. Xác định main class và entry point cho từng module cụ thể.
Đáp án đúng: B

Câu 2. Dạng khai báo nào tạo named module `com.shop.orders` hợp lệ trong JPMS?
A. `module com.shop.orders { requires java.sql; }`.
B. `class com.shop.orders { requires java.sql; }`.
C. `module com.shop.orders implements java.sql { }`.
D. `package com.shop.orders { requires java.sql; }`.
Đáp án đúng: A

Câu 3. Với một named module bình thường, module nền tảng nào được đọc ngầm định?
A. `jdk.compiler` được đọc ngầm định bởi mọi Java module.
B. `java.desktop` được đọc mỗi khi khởi tạo module.
C. `java.sql` được đọc mà không cần khai báo dependencies.
D. `java.base` được đọc ngầm định dù module không khai báo `requires`.
Đáp án đúng: D

Câu 4. Trong `module-info.java` của module A, câu lệnh `requires B;` có tác dụng nào?
A. Mở private field của B để module A deep-reflect.
B. `requires B` giúp A đọc B trong module graph.
C. Xuất các package của A để module B import public type.
D. Đưa module B lên classpath thay vì module path.
Đáp án đúng: B

Câu 5. Giả sử A `requires B` và B `requires transitive C`; điều gì đúng về khả năng đọc module?
A. C chuyển thành unnamed module khi A gọi class trong C.
B. A tự động export toàn bộ package của C cho mọi module.
C. A có thể đọc C vì B khai báo `requires transitive C`.
D. A không thể đọc C trừ khi khai báo trực tiếp requires C.
Đáp án đúng: C

Câu 6. `requires static com.example.annotations;` trong module descriptor biểu thị điều gì?
A. Dependency được cấp quyền export ngược về module hiện tại.
B. Dependency cần lúc chạy nhưng có thể không có lúc compile.
C. Dependency cần lúc compile, có thể không có lúc chạy.
D. Dependency chỉ nạp lại khi có truy cập phản chiếu lần đầu.
Đáp án đúng: C

Câu 7. Module `core` khai báo `exports com.example.api;`; hiệu lực chính là gì?
A. Đưa các class của package vào classpath lúc chạy.
B. Mở private member cho deep reflection như `opens`.
C. Làm package cùng tên ở module khác cũng được export.
D. Export các public type cho module có quyền đọc `core`.
Đáp án đúng: D

Câu 8. Module B đọc module A nhưng package `internal` của A không export; code của B có thể làm gì?
A. B có thể import public class nếu A và B chạy cùng JVM.
B. B import được class nếu ghi `opens internal` trong B.
C. B import được class nếu đặt A trên module path.
D. Không import được class nếu A chưa export package đó.
Đáp án đúng: D

Câu 9. Trong `module-info.java`, `opens com.example.model;` chủ yếu hỗ trợ điều gì?
A. Cho phép module khác compile import public class của package.
B. Hỗ trợ deep reflection lúc chạy vào package được module mở.
C. Biến mọi method trong package thành public ở source code.
D. Xuất package thành Java API dùng qua requires transitive.
Đáp án đúng: B

Câu 10. Khai báo `open module com.example.app { ... }` có ý nghĩa nào?
A. Bỏ yêu cầu khai báo `requires` cho dependency bên ngoài.
B. Cho module được chạy trên classpath thay vì module path.
C. Export mọi package để module khác biên dịch trực tiếp.
D. Mở các package của module cho deep reflection lúc chạy.
Đáp án đúng: D

Câu 11. Khai báo `exports com.shop.spi to com.shop.desktop;` tạo ranh giới nào?
A. Giới hạn quyền export package tới module desktop được nêu.
B. Quyền export được cấp cho mọi module ngoại trừ desktop.
C. Module desktop được truy cập private field bằng reflection.
D. Package được export tới các JAR của unnamed module.
Đáp án đúng: A

Câu 12. Khai báo `opens com.shop.dto to com.fasterxml.jackson.databind;` cho phép gì?
A. Cho các module import type không public trong DTO.
B. Cho Jackson deep-reflect vào package DTO được mở.
C. Cho DTO thành public API đã được export bởi module.
D. Cho module Jackson thay đổi kiểu của các class DTO.
Đáp án đúng: B

Câu 13. Một module khai báo `exports p;` với class `p.Helper` package-private; nhận định nào đúng?
A. Helper vẫn package-private dù package p được export.
B. Export làm Helper trở thành public mà không sửa source.
C. Helper thành public nếu module khác requires module chứa.
D. Module khác có thể import Helper khi package được export.
Đáp án đúng: A

Câu 14. Framework JSON muốn set private field của DTO trong named module; phương án cấu hình JPMS nào phù hợp?
A. `exports` package DTO mở cả private field trong package DTO.
B. `requires` framework mở cả private field trong package DTO.
C. Mở package DTO bằng `opens` tới module framework.
D. Gắn `@JsonProperty` lên DTO sẽ thay thế việc mở package.
Đáp án đúng: C

Câu 15. Muốn mở package `com.app.model` của module `app.core` cho code classpath bằng JVM flag, cú pháp nào phù hợp?
A. `--add-modules app.core/com.app.model=ALL-UNNAMED`.
B. `--add-exports app.core/com.app.model=ALL-UNNAMED`.
C. `--add-opens app.core/com.app.model=ALL-UNNAMED`.
D. `--add-reads app.core/com.app.model=ALL-UNNAMED`.
Đáp án đúng: C

Câu 16. Flag nào chủ yếu mở quyền truy cập public type của package chưa export, không nhằm cấp deep reflection?
A. `--add-opens app.core/com.app.internal=app.client`.
B. `--add-exports app.core/com.app.internal=app.client`.
C. `--add-modules app.core/com.app.internal=app.client`.
D. `--add-reads app.core/com.app.internal=app.client`.
Đáp án đúng: B

Câu 17. Để JVM tìm named module từ thư mục `mods`, option dòng lệnh nào phù hợp?
A. Dùng `--module-path mods` để JVM tìm named module.
B. Dùng `--source-path mods` để thiết lập runtime graph.
C. Dùng `--class-path mods` để phân giải named modules.
D. Dùng `--patch-module mods` để tạo module path mới.
Đáp án đúng: A

Câu 18. Với module `com.app.main` chứa class `com.app.Main`, cách khởi chạy nào phù hợp?
A. `java --module-path mods -m com.app.main:com.app.Main`.
B. `java --class-path mods -m com.app.main/com.app.Main`.
C. `java --module-path mods --class-path mods com.app.main/com.app.Main`.
D. `java --module-path mods -m com.app.main/com.app.Main`.
Đáp án đúng: D

Câu 19. Khi chuyển ứng dụng từ classpath sang JPMS, công cụ JDK nào giúp phân tích phụ thuộc tĩnh?
A. `jdeps` để phân tích class/package/module dependencies.
B. `jstack` để suy luận module requirements từ thread dump.
C. `javap` để tính số API module phải export.
D. `javadoc` để kiểm tra module graph đã giải quyết.
Đáp án đúng: A

Câu 20. Vì sao kết quả `jdeps` chưa đủ để kết luận mọi phụ thuộc của ứng dụng?
A. Nó không thể đọc bytecode nằm bên trong bất kỳ JAR nào.
B. Nó phân tích runtime HTTP traffic thay vì bytecode hiện có.
C. Có thể bỏ sót dependency nạp bằng reflection hoặc tên class lúc chạy.
D. Nó chỉ có thể xử lý module mà không thể xử lý classpath.
Đáp án đúng: C

Câu 21. Trong JPMS, consumer module dùng `ServiceLoader` cần directive nào để khai báo service type được sử dụng?
A. `uses com.example.spi.PaymentService;` trong module-info.
B. `requires com.example.spi.PaymentService;` trong module-info.
C. `provides com.example.spi.PaymentService;` trong module-info.
D. `exports com.example.spi.PaymentService;` trong module-info.
Đáp án đúng: A

Câu 22. Provider module có implementation `FastPay` của service `PaymentService`; directive nào khai báo provider?
A. `exports com.example.spi.PaymentService with com.example.impl.FastPay;`.
B. `requires com.example.spi.PaymentService with com.example.impl.FastPay;`.
C. `uses com.example.spi.PaymentService with com.example.impl.FastPay;`.
D. `provides com.example.spi.PaymentService with com.example.impl.FastPay;`.
Đáp án đúng: D

Câu 23. Khi provider đã khai báo `provides ... with ...`, API nào tải các provider của service trong môi trường thích hợp?
A. `Class.forName(PaymentService.class)` tìm service provider.
B. `Package.getPackage(PaymentService.class)` tạo provider.
C. `ServiceLoader.load(PaymentService.class)` tìm service provider.
D. `ModuleLayer.boot().findModule(PaymentService.class)` tạo provider.
Đáp án đúng: C

Câu 24. JAR không có `module-info.class` được đặt trên module path dưới dạng automatic module; điểm nào đúng?
A. Nó trở thành unnamed module như JAR nằm trên classpath.
B. Nó chỉ export package được nêu trong module-info.java.
C. Named module khác không thể khai báo requires module này.
D. Automatic module có tên từ manifest/JAR và export package.
Đáp án đúng: D

Câu 25. Các class nằm trên classpath theo JPMS thường thuộc loại module nào?
A. Unnamed module, với khả năng truy cập khác named module.
B. Layer module mới với module-info.java được JVM tự tạo.
C. Automatic module vì mỗi JAR được gán module name riêng.
D. Named module mặc định tên `java.classpath` có descriptor.
Đáp án đúng: A

Câu 26. Trong module-info của named module `app.core`, có thể trực tiếp `requires` unnamed module trên classpath không?
A. Có, dùng `requires classpath` để đọc toàn bộ JAR.
B. Có, dùng `requires ALL-UNNAMED` trong module-info.java.
C. Không, unnamed module không có tên để khai báo requires.
D. Có, dùng `requires java.classpath` như một module tên cố định.
Đáp án đúng: C

Câu 27. Hai named module có package cùng tên trong cùng configuration/layer và cùng được resolved; vấn đề nào thường gặp?
A. Compiler đổi tên package ở module nạp sau để tránh trùng.
B. Split package có thể gây xung đột khi resolve named modules.
C. JVM gộp class của hai module thành một package hợp nhất.
D. JPMS ưu tiên module có tên ngắn hơn khi import package.
Đáp án đúng: B

Câu 28. Đặt nhiều module vào module path có đồng nghĩa tất cả đều trở thành resolved root modules?
A. Không; module graph được giải quyết từ roots và dependencies.
B. Không, module loader chỉ chọn JDK modules từ thư mục lib.
C. Có, mỗi module trên module path thành root ngay khi JVM chạy.
D. Có, JVM tự thêm `requires` từ root đến từng module có sẵn.
Đáp án đúng: A

Câu 29. Với `ModuleLayer` trong ứng dụng plugin, khả năng nào là phù hợp?
A. Đổi package đã định nghĩa để class cũ mang module identity mới.
B. Giải quyết module configuration mới và định nghĩa layer riêng.
C. Chuyển dependency của mọi module ở boot layer thành classpath.
D. Thêm class vào named module đã chạy bằng thay đổi module-info.
Đáp án đúng: B

Câu 30. Công cụ `jlink` có tác dụng chính nào trong quy trình phân phối JPMS?
A. Phân tích dependency rồi tự sinh module-info.java theo bytecode.
B. Đóng gói source và resources thành modular JAR để chạy ứng dụng.
C. Tạo installer dạng desktop bundle tương đương `jpackage`.
D. Tạo custom runtime image gồm các Java module cần thiết.
Đáp án đúng: D

Câu 31. Nếu một automatic module nằm trong tập module đưa vào `jlink`, điều gì cần lưu ý?
A. `jlink` biến automatic module thành unnamed module trong image.
B. `jlink` tự sinh descriptor đủ mạnh cho automatic module.
C. `jlink` không chấp nhận automatic module để tạo runtime image.
D. `jlink` đổi automatic module sang classpath rồi luôn thành công.
Đáp án đúng: C

Câu 32. Khi di trú ứng dụng có nhiều JAR cũ sang JPMS, chiến lược nào giảm lỗi phụ thuộc và reflection?
A. Chạy `--add-modules ALL-UNNAMED` nhằm sửa split package.
B. Dùng `jdeps`, rà dependency graph và sửa `opens`/`exports`.
C. Đưa các JAR cũ lên module path rồi xử lý lỗi sau deploy.
D. Đổi descriptor sang `open module` để bỏ yêu cầu requires.
Đáp án đúng: B
