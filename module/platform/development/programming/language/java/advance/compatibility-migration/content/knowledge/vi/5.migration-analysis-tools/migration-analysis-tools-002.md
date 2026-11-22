# Phân tích phụ thuộc lớp, package và module bằng jdeps

Khi nâng cấp JDK hoặc chuyển một ứng dụng Java sang Java Platform Module System (JPMS), một trong những câu hỏi quan trọng nhất là: mã nguồn và bytecode hiện tại đang phụ thuộc vào những lớp, package và module nào? Một thư viện tưởng như độc lập có thể đang gọi API nội bộ của JDK, sử dụng package từ một module không còn được cài mặc định, hoặc kéo theo nhiều phụ thuộc gián tiếp.

`jdeps` là công cụ phân tích phụ thuộc tĩnh đi kèm JDK. Công cụ đọc class file, JAR hoặc module để tìm các tham chiếu giữa lớp, package, archive và module. Kết quả giúp nhóm phát triển hiểu cấu trúc phụ thuộc, phát hiện tham chiếu tới API nội bộ của JDK, chuẩn bị module descriptor và xác định tập module cần thiết cho một runtime tùy chỉnh.

`jdeps` phân tích bytecode đã biên dịch. Nó bổ sung cho việc đọc mã nguồn và công cụ quản lý dependency của Maven hoặc Gradle; mỗi công cụ trả lời một loại câu hỏi khác nhau. Bài học này trình bày cách chọn mức phân tích, cung cấp classpath/module path, đọc kết quả và dùng `jdeps` trong quá trình migration.

## 1. jdeps dùng để làm gì?

`jdeps` (Java Dependency Analysis Tool) được cung cấp trong JDK. Nó phân tích các tham chiếu phụ thuộc mà công cụ có thể nhận diện từ class file và module descriptor.

Các công việc thường dùng gồm:

- Xem một JAR phụ thuộc vào những module nền tảng hoặc thư viện nào.
- Tìm package và class mà một lớp đang tham chiếu.
- Mở rộng phân tích sang các dependency được tham chiếu gián tiếp.
- Phát hiện class hoặc package còn thiếu trên classpath/module path.
- Tìm việc sử dụng JDK internal API có nguy cơ bị giới hạn hoặc loại bỏ.
- Kiểm tra quan hệ `requires` trong module descriptor.
- Tạo bản nháp `module-info.java` khi chuyển một thư viện sang module.
- Liệt kê các module cần thiết để tạo runtime image bằng `jlink`.

Ví dụ, một ứng dụng có thể trực tiếp gọi `java.sql.Connection`, sử dụng `com.example.common.Strings` từ một thư viện riêng và gián tiếp cần `java.xml` thông qua một thư viện khác. `jdeps` giúp làm rõ những quan hệ đó trong bytecode.

## 2. Phụ thuộc lớp, package và module khác nhau thế nào?

Trước khi chạy công cụ, cần hiểu ba mức biểu diễn:

| Mức | Đối tượng được phân tích | Câu hỏi điển hình |
|---|---|---|
| Class | Lớp hoặc interface cụ thể | `OrderService` tham chiếu tới lớp nào? |
| Package | Nhóm lớp cùng namespace | Package `com.example.service` phụ thuộc package nào? |
| Module | Đơn vị đóng gói và khai báo phụ thuộc của JPMS | Module `com.example.orders` cần những module nào? |

Giả sử có cấu trúc:

```text
com.example.orders
├── service
│   └── OrderService
├── model
│   └── Order
└── persistence
    └── OrderRepository
```

`OrderService` có thể tham chiếu tới `Order`, `OrderRepository` và `java.sql.Connection`. Ở mức class, công cụ cho biết những lớp cụ thể được tham chiếu. Ở mức package, các tham chiếu được gom thành quan hệ như `service -> model` và `persistence -> java.sql`. Ở mức module, những package thuộc các module khác nhau được tổng hợp thành quan hệ module.

Ba mức này không thay thế nhau. Class-level hữu ích khi tìm đúng vị trí cần sửa; package-level giúp hiểu ranh giới kiến trúc; module-level hỗ trợ thiết kế `module-info.java` và kiểm tra khả năng chạy trong môi trường modular.

## 3. Chuẩn bị môi trường và đầu vào

### 3.1. Kiểm tra jdeps có sẵn

`jdeps` nằm trong thư mục `bin` của JDK. Mở terminal và chạy:

```bash
jdeps --version
```

Nếu shell báo không tìm thấy lệnh, hãy kiểm tra `JAVA_HOME` và `PATH`, hoặc gọi trực tiếp file thực thi trong thư mục JDK:

```text
<JDK_HOME>/bin/jdeps
```

Trên Windows, file thực thi thường là `jdeps.exe` trong `<JDK_HOME>\bin`. Cần dùng JDK có chứa công cụ này; một runtime image tối giản có thể không bao gồm toàn bộ công cụ phát triển.

### 3.2. Những loại đầu vào có thể phân tích

Thông thường, có thể truyền vào `jdeps`:

- Một file `.class`.
- Một thư mục chứa các class đã biên dịch.
- Một file JAR.
- Một module hoặc tập archive/module phù hợp với đường dẫn phân giải.

Ví dụ, sau khi build dự án, có thể phân tích JAR:

```bash
jdeps build/libs/orders-app.jar
```

Hoặc phân tích thư mục class đã biên dịch:

```bash
jdeps build/classes/java/main
```

Kết quả phụ thuộc vào những dependency mà công cụ có thể tìm thấy. Nếu ứng dụng dùng thư viện bên ngoài, hãy cung cấp classpath hoặc module path phù hợp để tránh kết quả thiếu hoặc xuất hiện cảnh báo `not found`.

### 3.3. Phân biệt classpath và module path

`--class-path` (viết tắt `-cp`) chỉ nơi tìm các class và JAR được nạp theo cơ chế classpath. `--module-path` chỉ nơi tìm các module có tên theo JPMS. Hai đường dẫn này phục vụ hai mô hình phân giải khác nhau.

Ví dụ:

```bash
jdeps --class-path "lib/*" -verbose:package app.jar
```

Lệnh trên phân tích `app.jar` và tìm dependency trên classpath `lib/*`.

Với ứng dụng modular:

```bash
jdeps --module-path "mods" -verbose:module app.jar
```

Lệnh trên cho phép công cụ phân giải module từ thư mục `mods`. Khi phân tích một ứng dụng modular thực tế, hãy dùng đúng module path mà ứng dụng hoặc lệnh chạy production sử dụng.

Trên Windows, có thể cần đặt đường dẫn trong dấu nháy kép để shell xử lý khoảng trắng. Dấu phân cách nhiều phần tử trong classpath/module path cũng phụ thuộc hệ điều hành: `;` trên Windows và `:` trên Linux/macOS.

## 4. Phân tích phụ thuộc tổng quan

### 4.1. Summary mode

Lệnh cơ bản:

```bash
jdeps -summary app.jar
```

Hoặc dùng dạng dài:

```bash
jdeps --summary app.jar
```

Summary mode gom kết quả ở mức archive, giúp xem nhanh JAR đang phụ thuộc vào những archive hoặc module nào. Đây là điểm bắt đầu tốt khi kiểm tra một thư viện lớn.

Một kết quả minh họa:

```text
orders-app.jar -> java.base
orders-app.jar -> java.sql
orders-app.jar -> common-utils.jar
```

Trong ví dụ, ứng dụng có quan hệ phụ thuộc với `java.base`, `java.sql` và `common-utils.jar`. Tên và cách trình bày thực tế phụ thuộc đầu vào, classpath/module path và phiên bản JDK.

Summary không cho biết ngay lớp nào tạo ra từng quan hệ. Khi cần tìm nguồn gốc một dependency, hãy chuyển sang mức package hoặc class.

### 4.2. Phân tích đệ quy

Một JAR có thể phụ thuộc vào thư viện khác, thư viện đó lại phụ thuộc vào một thư viện thứ ba. Tùy chọn `-R` (recursive) mở rộng phân tích sang các dependency được tìm thấy trên đường dẫn phân giải:

```bash
jdeps -R -summary --class-path "lib/*" app.jar
```

Phân tích đệ quy hữu ích khi muốn hiểu phạm vi dependency rộng hơn một archive. Tuy nhiên, kết quả có thể lớn và cần được đọc theo từng tầng. Nó không đồng nghĩa với việc công cụ sẽ khám phá mọi dependency được tải động khi chương trình chạy.

## 5. Phân tích phụ thuộc ở mức package

Dùng `-verbose:package` để hiển thị quan hệ giữa các package:

```bash
jdeps -verbose:package app.jar
```

Ví dụ đầu ra minh họa:

```text
com.example.orders.service -> com.example.orders.model
com.example.orders.service -> com.example.orders.persistence
com.example.orders.persistence -> java.sql
com.example.orders.service -> java.util
```

Kết quả cho thấy package service sử dụng model và persistence; package persistence sử dụng `java.sql`; package service cũng sử dụng `java.util`.

### 5.1. Dùng package dependency để xem ranh giới kiến trúc

Package dependency hữu ích khi kiểm tra các nguyên tắc kiến trúc:

- Package domain có phụ thuộc vào package web hoặc persistence không?
- Package dùng chung có vô tình phụ thuộc ngược vào ứng dụng cụ thể không?
- Có vòng phụ thuộc giữa các nhóm package không?
- Một package có phụ thuộc quá nhiều package bên ngoài không?

Ví dụ, nếu kiến trúc mong muốn là:

```text
web -> application -> domain
                  -> persistence
```

nhưng kết quả cho thấy:

```text
domain -> web
```

thì có thể đang tồn tại phụ thuộc ngược cần xem xét. `jdeps` chỉ cung cấp bằng chứng về quan hệ tham chiếu; nhóm phát triển cần quyết định quan hệ đó có vi phạm kiến trúc hay không.

### 5.2. Lọc kết quả

Khi một dự án có nhiều package, có thể dùng các tùy chọn lọc của `jdeps` để giảm nhiễu. Ví dụ:

```bash
jdeps -verbose:package -filter:archive app.jar
```

Các bộ lọc như `-filter:archive`, `-filter:package`, `-filter:module` hoặc `-filter:none` điều khiển những quan hệ nào được giữ hoặc loại khỏi kết quả. `-filter:none` hữu ích khi cần xem cả các quan hệ nội bộ mà chế độ lọc mặc định có thể ẩn. Hãy đọc phần Options của `jdeps --help` trên JDK đang dùng để xác nhận cách lọc cụ thể của phiên bản đó.

Không nên lọc quá mạnh trong lần khảo sát đầu tiên. Một quan hệ nội bộ giữa hai package trong cùng archive vẫn có thể quan trọng khi kiểm tra vòng phụ thuộc hoặc ranh giới module.

## 6. Phân tích phụ thuộc ở mức class

Khi cần biết chính xác lớp nào tham chiếu tới lớp nào, dùng `-verbose:class`:

```bash
jdeps -verbose:class app.jar
```

Để xem nhiều quan hệ hơn, kể cả một số dependency nội bộ bị lọc, có thể chạy:

```bash
jdeps -verbose:class -filter:none app.jar
```

Ví dụ đầu ra minh họa:

```text
com.example.orders.service.OrderService
  -> com.example.orders.model.Order
  -> com.example.orders.persistence.OrderRepository
  -> java.sql.Connection

com.example.orders.persistence.JdbcOrderRepository
  -> java.sql.PreparedStatement
  -> java.sql.ResultSet
```

Class-level đặc biệt hữu ích khi:

- Tìm lớp sử dụng một API đã deprecated hoặc API nội bộ.
- Xác định vì sao một package cần module cụ thể.
- Tìm lớp gây ra phụ thuộc vào thư viện không còn muốn sử dụng.
- Chia nhỏ một thư viện lớn thành các module có ranh giới rõ ràng.

### 6.1. Cung cấp thư viện phụ thuộc

Nếu class được tham chiếu nằm trong một JAR ngoài, hãy cung cấp classpath:

```bash
jdeps -verbose:class --class-path "lib/*" app.jar
```

Nếu không cung cấp thư viện cần thiết, kết quả có thể chứa `not found` hoặc báo thiếu dependency. Điều này không nhất thiết chứng minh JAR nguồn bị hỏng; có thể chỉ là lệnh phân tích chưa nhận đủ đường dẫn.

Hãy dùng cùng bộ thư viện và phiên bản dependency mà ứng dụng thực tế sử dụng. Nếu đưa một phiên bản khác vào classpath, kết quả phân tích có thể không phản ánh đúng môi trường production.

## 7. Phát hiện dependency bị thiếu

Tùy chọn `--missing-deps` yêu cầu `jdeps` liệt kê các phụ thuộc không thể phân giải:

```bash
jdeps --missing-deps --class-path "lib/*" app.jar
```

Một tình huống minh họa:

```text
app.jar -> not found
   com.example.orders.ReportService -> com.vendor.reporting.PdfWriter not found
```

Thông tin này giúp tìm ra class mà bytecode tham chiếu nhưng công cụ không tìm được trên các đường dẫn đã cung cấp.

Khi gặp dependency thiếu, nên xử lý theo trình tự:

1. Xác định class được báo thiếu và module/package dự kiến chứa nó.
2. Kiểm tra dependency có được tải trong build hay không.
3. Kiểm tra classpath/module path của lệnh `jdeps` có giống cấu hình chạy ứng dụng không.
4. Kiểm tra phiên bản JAR và tên module, đặc biệt khi thư viện đã được modular hóa.
5. Chạy lại phân tích sau khi sửa đường dẫn hoặc dependency.

`--ignore-missing-deps` có thể được dùng trong một số tác vụ phân tích/generate khi người vận hành chủ động chấp nhận bỏ qua dependency chưa phân giải. Không nên dùng nó để che giấu lỗi môi trường trong một lần kiểm tra đầy đủ.

## 8. Phát hiện việc sử dụng JDK internal API

Một rủi ro quan trọng khi nâng cấp JDK là ứng dụng phụ thuộc vào các package nội bộ như `sun.*`, `com.sun.*` hoặc những API không thuộc Java SE được cam kết ổn định.

Chạy:

```bash
jdeps --jdk-internals app.jar
```

Để phân tích cả dependency ngoài trên classpath:

```bash
jdeps --jdk-internals --class-path "lib/*" app.jar
```

Kết quả có thể chỉ ra class đang tham chiếu internal API và gợi ý API thay thế nếu công cụ có thông tin tương ứng.

Ví dụ về một đoạn kết quả minh họa:

```text
JDK Internal API                         Suggested Replacement
----------------                         ---------------------
sun.misc.BASE64Encoder                   java.util.Base64
```

Đây chỉ là ví dụ minh họa dạng báo cáo; danh sách thực tế phụ thuộc JDK và class file được phân tích.

### 8.1. Vì sao internal API nguy hiểm?

API công khai của Java SE có hợp đồng tương thích được tài liệu hóa. Internal API thường là chi tiết triển khai của JDK, không có cam kết ổn định tương tự. Chúng có thể bị đóng gói, giới hạn truy cập, thay đổi hoặc loại bỏ qua các phiên bản.

JEP 260 và JEP 403 là những mốc quan trọng trong việc đóng gói và đóng quyền truy cập tới nhiều internal API. Vì vậy, một ứng dụng chạy được trên JDK cũ có thể phát sinh lỗi truy cập hoặc không biên dịch được trên JDK mới.

### 8.2. Cách xử lý

Khi `jdeps --jdk-internals` tìm thấy tham chiếu:

1. Tìm lớp và package trong ứng dụng đang sử dụng API đó.
2. Đọc gợi ý thay thế và tài liệu API công khai tương ứng.
3. Thay thế bằng API chuẩn nếu có, ví dụ dùng `java.util.Base64` thay cho encoder/decoder nội bộ cũ.
4. Nếu chưa có API thay thế, đánh giá thư viện bên ngoài được hỗ trợ hoặc thiết kế lại phần phụ thuộc.
5. Chạy kiểm thử trên JDK mục tiêu và kiểm tra cảnh báo truy cập phản chiếu.

Các tùy chọn như `--add-exports` hoặc `--add-opens` có thể giúp ứng dụng cũ tiếp tục chạy trong giai đoạn chuyển tiếp. Chúng cần được xem là cấu hình tương thích tạm thời có kiểm soát, không phải giải pháp thay thế lâu dài cho việc bỏ phụ thuộc internal API.

## 9. Phân tích module và quan hệ JPMS

Từ Java 9, JPMS đưa vào khái niệm module có tên, module descriptor và cơ chế kiểm soát phụ thuộc/khả năng truy cập. `jdeps` có thể tổng hợp dependency theo module để hỗ trợ chuyển một ứng dụng từ classpath sang module path.

### 9.1. Hiển thị phụ thuộc module

Dùng `-verbose:module`:

```bash
jdeps -verbose:module --module-path mods app.jar
```

Kết quả cho biết module nào được tham chiếu. Ví dụ minh họa:

```text
orders.app -> java.base
orders.app -> java.sql
orders.app -> com.example.persistence
```

Nếu archive chưa có module descriptor, cách công cụ suy ra module name có thể dựa trên `Automatic-Module-Name` trong manifest hoặc tên JAR. Với module đã khai báo rõ, tên module được lấy từ descriptor.

### 9.2. Phân tích một module cụ thể

Khi module đã nằm trên module path, có thể chỉ định tên module cần phân tích:

```bash
jdeps --module-path mods --module com.example.orders -verbose:module
```

Lệnh này tập trung vào module `com.example.orders` và các quan hệ mà công cụ phân tích được từ module đó. Nếu không phân giải được module, hãy kiểm tra module path và tên trong `module-info.java`.

### 9.3. Hiểu module descriptor

Một module descriptor có thể chứa các khai báo như:

```java
module com.example.orders {
    requires java.sql;
    requires com.example.persistence;

    exports com.example.orders.api;
}
```

Các chỉ thị quan trọng:

| Chỉ thị | Ý nghĩa |
|---|---|
| `requires` | Module hiện tại phụ thuộc vào một module khác. |
| `requires transitive` | Module phụ thuộc được yêu cầu cũng được đưa vào quan hệ đọc của các module phụ thuộc module hiện tại. |
| `requires static` | Dependency cần ở compile time nhưng có thể không bắt buộc lúc runtime. |
| `exports` | Cho phép module khác truy cập các kiểu public trong package được export. |
| `opens` | Cho phép truy cập phản chiếu sâu tới package theo phạm vi khai báo. |
| `uses` | Khai báo module sử dụng một service. |
| `provides ... with ...` | Khai báo provider cho một service. |

`jdeps` giúp tìm các quan hệ tham chiếu, nhưng người thiết kế module vẫn phải quyết định package nào nên export, dependency nào cần `transitive` hoặc `static`, và service nào cần khai báo. Không nên biến mọi package mà công cụ nhìn thấy thành package được export công khai.

### 9.4. Kiểm tra module descriptor với `--check`

`--check` phân tích module được chỉ định và cung cấp thông tin về dependency trong module graph, bao gồm những yêu cầu có thể dư thừa hoặc phụ thuộc gián tiếp:

```bash
jdeps --module-path mods --check com.example.orders
```

Đây là bước hữu ích sau khi đã có `module-info.java`. Hãy đọc kết quả cùng descriptor hiện tại để xác định khai báo nào thực sự cần giữ. Không xóa `requires` chỉ vì một báo cáo đơn lẻ gợi ý rằng dependency có thể được suy ra gián tiếp; cần xem xét API công khai của module và các module downstream.

## 10. Liệt kê module cần thiết cho runtime

Khi tạo runtime image tối giản bằng `jlink`, cần biết những module nền tảng nào ứng dụng sử dụng.

### 10.1. Liệt kê dependency module

```bash
jdeps --list-deps --module-path mods app.jar
```

Tùy chọn này liệt kê các module phụ thuộc cần thiết theo phân tích của công cụ.

### 10.2. In danh sách module gọn

```bash
jdeps --print-module-deps --module-path mods app.jar
```

`--print-module-deps` in danh sách tên module dạng phù hợp để dùng làm đầu vào cho bước tạo runtime image. Ví dụ, nếu kết quả là:

```text
java.base,java.sql
```

có thể dùng danh sách đó làm cơ sở cho:

```bash
jlink --add-modules java.base,java.sql --output runtime-image
```

Đây là ví dụ tối giản; ứng dụng thực tế có thể cần module bổ sung do service binding, provider, locale, charset, logging hoặc cơ chế nạp động. Cần kiểm thử runtime image với toàn bộ luồng nghiệp vụ trước khi phân phối.

### 10.3. Phân biệt danh sách đầy đủ và reduced dependencies

`--list-deps` liệt kê module phụ thuộc được phân tích. `--list-reduced-deps` cố gắng loại bỏ một số dependency có thể suy ra thông qua quan hệ `requires transitive` trong module graph. Hai kết quả phục vụ mục đích khác nhau; khi tạo runtime image, cần hiểu danh sách được dùng và kiểm thử image thực tế.

Không nên xem kết quả `jdeps` là bảo đảm tuyệt đối rằng runtime image đã đủ cho mọi đường chạy. Những class được tải bằng reflection, cấu hình plugin, JNI hoặc service/provider tùy cách triển khai có thể cần kiểm tra bổ sung.

## 11. Tạo module descriptor bằng jdeps

Khi một JAR chưa có `module-info.java`, có thể dùng `--generate-module-info` để tạo bản nháp descriptor:

```bash
jdeps --generate-module-info generated-modules legacy-library.jar
```

Công cụ tạo thư mục/file nguồn module descriptor trong `generated-modules` dựa trên dependency và package mà nó phân tích được. Đây là điểm khởi đầu cho quá trình modular hóa.

Ví dụ bản nháp có thể trông như sau:

```java
module legacy.library {
    requires java.base;
    requires java.logging;

    exports com.example.legacy.api;
    exports com.example.legacy.model;
}
```

Tên module và danh sách export trong ví dụ chỉ minh họa. Hãy đọc file được tạo trong dự án thực tế.

### 11.1. Vì sao phải review module-info.java được sinh ra?

`jdeps` suy ra quan hệ từ bytecode, nhưng không hiểu đầy đủ ý định thiết kế API. Một package có lớp public không có nghĩa package đó nên được export. Một dependency xuất hiện trong chữ ký API có thể cần `requires transitive`; một dependency chỉ dùng nội bộ có thể chỉ cần `requires` thông thường. Một số service cần khai báo `uses` hoặc `provides` theo thiết kế.

Sau khi sinh descriptor, cần:

1. Kiểm tra tên module và `Automatic-Module-Name` nếu có.
2. Rà soát từng `requires`, bỏ dependency không còn cần thiết và xác nhận dependency cần thiết không bị thiếu.
3. Chỉ export package là API được hỗ trợ.
4. Xác định `requires transitive`, `requires static`, `opens`, `uses` và `provides` theo hợp đồng của thư viện.
5. Biên dịch lại trên module path và chạy kiểm thử từ một module client.

Với thư viện cần hỗ trợ reflection framework, cần xem xét package nào phải `opens` và mở cho module nào. `exports` và `opens` có mục đích khác nhau; không dùng chúng thay thế tùy tiện.

### 11.2. Open module

Trong trường hợp cần mở toàn bộ package cho deep reflection, `jdeps` cung cấp tùy chọn `--generate-open-module` để tạo descriptor dạng open module. Đây là lựa chọn rộng và cần đánh giá cẩn thận vì nó làm giảm mức đóng gói phản chiếu của JPMS. Chỉ dùng khi yêu cầu framework hoặc thiết kế thực sự cần mở toàn bộ module.

## 12. Xuất đồ thị phụ thuộc

Khi quan hệ phụ thuộc quá nhiều để đọc bằng văn bản, có thể dùng `--dot-output` để xuất các file DOT:

```bash
jdeps --dot-output dependency-report --class-path "lib/*" -R app.jar
```

Thư mục `dependency-report` sẽ chứa các biểu diễn đồ thị để xem bằng công cụ hỗ trợ Graphviz/DOT. Đồ thị giúp nhận diện:

- Package hoặc archive có nhiều dependency.
- Các nhóm package kết nối chặt với nhau.
- Quan hệ phụ thuộc giữa các module.
- Các đường phụ thuộc gián tiếp cần điều tra.

DOT mô tả các nút và cạnh. Có thể chuyển file `.dot` sang ảnh bằng Graphviz nếu công cụ đó đã được cài đặt:

```bash
dot -Tpng dependency-report/app.jar.dot -o dependency-report/app-dependencies.png
```

Tên file DOT thực tế được tạo ra phụ thuộc archive và phiên bản công cụ; hãy xem nội dung thư mục sau khi chạy `jdeps` rồi dùng đúng tên file.

## 13. Multi-release JAR

Multi-release JAR có thể chứa nhiều phiên bản class cho các phiên bản Java khác nhau trong cùng một archive. Cấu trúc thường có thư mục `META-INF/versions/<N>` bên cạnh class cơ sở.

Khi phân tích loại JAR này, có thể chỉ định phiên bản mục tiêu:

```bash
jdeps --multi-release 21 -verbose:package library.jar
```

Tùy chọn `--multi-release` yêu cầu công cụ xem xét nội dung phù hợp với phiên bản Java được chỉ định. Điều này quan trọng khi thư viện cung cấp implementation riêng cho JDK mới hơn.

Nếu đang migration lên JDK 21, hãy phân tích theo target phù hợp và kiểm tra class nào sẽ được runtime chọn. Chỉ phân tích phần class cơ sở có thể bỏ qua dependency của implementation dành riêng cho JDK mới.

## 14. Các tùy chọn jdeps thường dùng

| Tùy chọn | Công dụng |
|---|---|
| `-summary` | Hiển thị dependency ở mức tổng quan. |
| `-verbose:package` | Hiển thị dependency ở mức package. |
| `-verbose:class` | Hiển thị dependency ở mức class. |
| `-verbose:module` | Hiển thị dependency ở mức module. |
| `-R` | Phân tích đệ quy dependency được tìm thấy. |
| `--class-path` / `-cp` | Chỉ định classpath chứa dependency. |
| `--module-path` | Chỉ định module path. |
| `--module` | Chọn module cần phân tích. |
| `--missing-deps` | Liệt kê dependency không thể phân giải. |
| `--jdk-internals` | Tìm tham chiếu tới JDK internal API. |
| `--api-only` | Giới hạn phân tích vào API public/protected. |
| `--check` | Kiểm tra dependency/module descriptor của module. |
| `--list-deps` | Liệt kê module dependency. |
| `--list-reduced-deps` | Liệt kê dependency module sau khi rút gọn theo module graph. |
| `--print-module-deps` | In danh sách module gọn để dùng trong bước tạo runtime image. |
| `--generate-module-info` | Sinh bản nháp `module-info.java`. |
| `--generate-open-module` | Sinh descriptor dạng open module. |
| `--dot-output` | Xuất đồ thị dependency dạng DOT. |
| `--multi-release` | Chọn phiên bản để phân tích multi-release JAR. |
| `--ignore-missing-deps` | Bỏ qua dependency thiếu trong những tác vụ hỗ trợ tùy chọn này. |

Tên tùy chọn ngắn và dài có thể khác nhau theo JDK. Luôn kiểm tra `jdeps --help` trên JDK thực tế trong pipeline trước khi đưa lệnh vào script dùng chung.

## 15. Quy trình phân tích dependency khi migration

Một quy trình thực tế có thể thực hiện theo thứ tự sau.

### Bước 1: Build đúng artifact

Build ứng dụng bằng cấu hình và JDK đã chọn. Phân tích đúng JAR/class output sẽ được phát hành. Tránh phân tích một thư mục build cũ còn sót class từ lần biên dịch trước.

### Bước 2: Cung cấp dependency đầy đủ

Thu thập classpath hoặc module path tương ứng với runtime. Với Maven/Gradle, lấy dependency đã resolve từ cấu hình build; không tự chọn ngẫu nhiên các JAR có cùng tên.

### Bước 3: Chạy summary và package analysis

```bash
jdeps -summary --class-path "lib/*" app.jar
jdeps -verbose:package --class-path "lib/*" app.jar
```

Đọc các nhóm package và dependency bên ngoài. Nếu phát hiện quan hệ không mong muốn, chuyển sang class-level để tìm đúng lớp tạo ra quan hệ.

### Bước 4: Kiểm tra class-level và dependency thiếu

```bash
jdeps -verbose:class --class-path "lib/*" -filter:none app.jar
jdeps --missing-deps --class-path "lib/*" app.jar
```

Xác định lớp thiếu, thư viện không được đưa vào build hoặc tham chiếu không còn hợp lệ.

### Bước 5: Tìm JDK internal API

```bash
jdeps --jdk-internals --class-path "lib/*" app.jar
```

Ưu tiên loại bỏ các phụ thuộc internal API trước khi nâng feature release, nhất là các thư viện cũ chưa được cập nhật.

### Bước 6: Đánh giá module hóa

Nếu chuyển sang JPMS, phân tích ở mức module, kiểm tra module descriptor và tạo bản nháp nếu cần. Review kỹ `requires`, `exports`, `opens` và service declaration.

### Bước 7: Kiểm thử runtime thực tế

Biên dịch, chạy unit/integration test trên module path hoặc runtime image mục tiêu. Bổ sung test cho plugin, reflection, service loading và các luồng chỉ xảy ra trong production.

### Bước 8: Lưu kết quả làm baseline

Lưu lệnh đã chạy, phiên bản JDK, classpath/module path, báo cáo dependency và kết luận xử lý. Ở lần nâng cấp sau, có thể so sánh để phát hiện dependency mới hoặc internal API xuất hiện trở lại.

## 16. jdeps không thay thế dependency tree của Maven/Gradle

`jdeps` phân tích tham chiếu ở mức bytecode và module. Maven/Gradle dependency report lại tập trung vào dependency được khai báo và resolve trong build.

| Công cụ | Trả lời câu hỏi |
|---|---|
| `jdeps` | Class/package/module nào tham chiếu tới class/package/module nào trong bytecode? |
| `mvn dependency:tree` | Artifact Maven nào được khai báo trực tiếp hoặc kéo vào gián tiếp, theo group/artifact/version? |
| `gradle dependencies` | Dependency nào được resolve trong configuration của Gradle và theo quan hệ nào? |
| Unit/integration test | Những đường chạy đã kiểm thử có hoạt động đúng ở runtime không? |

Một dependency có thể xuất hiện trong dependency tree nhưng không được bytecode sử dụng. Ngược lại, một tham chiếu class có thể không được `jdeps` phân giải nếu thiếu JAR trên classpath. Cần kết hợp báo cáo build và phân tích bytecode để hiểu cả artifact graph lẫn class reference graph.

## 17. Giới hạn của phân tích tĩnh

`jdeps` không quan sát mọi hành vi xảy ra khi chương trình chạy. Nó không thể bảo đảm tìm được toàn bộ class được nạp bằng tên chuỗi, reflection, plugin, cấu hình ngoài, JNI hoặc custom class loader.

Ví dụ:

```java
String className = configuration.get("driver.class");
Class<?> driverClass = Class.forName(className);
```

Nếu giá trị `driver.class` chỉ xuất hiện trong file cấu hình lúc chạy, bytecode không nhất thiết chứa tham chiếu trực tiếp tới class driver cụ thể. `jdeps` có thể không suy ra dependency này.

Tương tự, framework có thể quét package, đọc file service provider hoặc nạp implementation theo cấu hình. Hãy bổ sung kiểm tra:

- Kiểm thử tích hợp trên môi trường gần production.
- Kiểm tra file `META-INF/services` và service provider.
- Kiểm tra cấu hình plugin, driver, logging, serializer và provider.
- Theo dõi class loading hoặc log khởi động khi cần.
- Kiểm tra native library và các thành phần JNI riêng.

Vì vậy, báo cáo `jdeps` là một nguồn bằng chứng tĩnh quan trọng, không phải danh sách tuyệt đối mọi dependency runtime.

## 18. Những lỗi thường gặp khi dùng jdeps

**Không cung cấp classpath/module path.** Kết quả có `not found` vì thiếu thư viện cần thiết. Hãy xác minh đường dẫn trước khi kết luận artifact bị lỗi.

**Phân tích nhầm artifact.** JAR trong thư mục build có thể không phải artifact cuối cùng được deploy. Hãy phân tích đúng file phát hành.

**Chỉ xem summary.** Summary không chỉ ra class gây ra quan hệ. Dùng package/class verbosity để khoanh vùng.

**Nhầm package dependency với module readability.** Một tham chiếu package không tự động có nghĩa module hiện tại có thể truy cập package đó. JPMS còn kiểm soát `requires`, `exports` và `opens`.

**Coi module-info được sinh ra là hoàn chỉnh.** Descriptor do công cụ tạo chỉ là bản nháp. Cần review API và ý định đóng gói.

**Bỏ qua internal API trong thư viện bên thứ ba.** Phân tích cả dependency trên classpath và cập nhật thư viện nếu có tham chiếu nội bộ.

**Cho rằng không có kết quả nghĩa là không có dependency.** Có thể đầu vào sai, đường dẫn thiếu, class file chưa được build hoặc dependency được nạp động.

**Dùng kết quả jdeps làm runtime image mà không thử.** Reflection, service loading, plugin và native library có thể cần thêm thành phần.

## 19. Checklist khi phân tích dependency

- [ ] Đã dùng đúng artifact/class output của lần build cần phát hành.
- [ ] Đã ghi lại phiên bản JDK và lệnh `jdeps` sử dụng.
- [ ] Đã cung cấp classpath hoặc module path đầy đủ.
- [ ] Đã xem dependency tổng quan.
- [ ] Đã phân tích package-level để hiểu ranh giới kiến trúc.
- [ ] Đã dùng class-level để truy ra dependency đáng ngờ.
- [ ] Đã xử lý các dependency `not found`.
- [ ] Đã chạy `--jdk-internals` và đánh giá API thay thế.
- [ ] Đã kiểm tra module descriptor nếu dự án dùng JPMS.
- [ ] Đã review mọi `module-info.java` được sinh tự động.
- [ ] Đã xem xét dependency tải động, reflection, service provider và JNI.
- [ ] Đã chạy kiểm thử trên runtime/module path mục tiêu.
- [ ] Đã lưu báo cáo để so sánh trong các lần migration tiếp theo.

## Kết luận

`jdeps` giúp phân tích dependency Java theo nhiều mức: class để tìm tham chiếu cụ thể, package để đánh giá ranh giới kiến trúc và module để chuẩn bị hoặc kiểm tra JPMS. Các tùy chọn như `--missing-deps`, `--jdk-internals`, `--check`, `--print-module-deps`, `--generate-module-info` và `--dot-output` hỗ trợ những bước khác nhau của migration. Để có kết luận đáng tin cậy, hãy phân tích đúng artifact với classpath/module path đầy đủ, kết hợp dependency report của Maven/Gradle và xác minh các đường chạy động bằng kiểm thử runtime.
