# Những vấn đề JPMS giải quyết và những vấn đề không giải quyết

Java Platform Module System (JPMS), được đưa vào nền tảng Java từ Java 9, bổ sung một mô hình module chính thức cho ứng dụng Java. Trước JPMS, nhiều ứng dụng tổ chức thư viện bằng JAR và classpath. Cách đó vẫn hoạt động, nhưng ranh giới phụ thuộc và phạm vi truy cập package thường không được mô tả đầy đủ. JPMS giúp ứng dụng khai báo phụ thuộc rõ ràng, giới hạn package được công bố và xây dựng một đồ thị module có thể được kiểm tra khi biên dịch hoặc khởi chạy.

Để đánh giá đúng JPMS, cần phân biệt những vấn đề thuộc về cấu trúc module với những vấn đề thuộc về build, phân phối, bảo mật và vận hành. JPMS tạo ra ranh giới và quy tắc ở cấp module; nó không tự thay thế toàn bộ hệ sinh thái công cụ Java.

## 1. Vì sao Java cần mô hình module?

Trong mô hình classpath truyền thống, JVM và compiler tìm class từ danh sách thư mục hoặc JAR. Một class có thể được tìm thấy mà không cần một khai báo phụ thuộc ở cấp thư viện cho biết module nào đang sử dụng nó. Package cũng chủ yếu là cách nhóm class theo tên; package không tự tạo ra ranh giới truy cập giữa các JAR.

Điều này tạo ra một số khó khăn:

- **Phụ thuộc khó nhìn thấy:** một thư viện có thể dùng class từ thư viện khác vì JAR đó tình cờ có trên classpath. Người đọc build file và mã nguồn khó xác định đầy đủ quan hệ phụ thuộc.
- **Phạm vi truy cập rộng:** class public trong package có thể trở thành điểm truy cập cho code ở nơi khác, kể cả khi tác giả chỉ muốn dùng package đó như chi tiết nội bộ.
- **Lỗi cấu hình xuất hiện muộn:** thiếu class hoặc thiếu phiên bản thư viện có thể chỉ lộ ra khi một đường chạy cụ thể được thực thi.
- **Khó tạo runtime nhỏ:** một ứng dụng có thể mang theo nhiều thành phần của JDK hơn mức cần thiết nếu quy trình triển khai không xác định được tập module thực sự được sử dụng.
- **Khó tách API khỏi implementation:** code gọi thường phải biết class triển khai cụ thể thay vì chỉ phụ thuộc vào một service contract.

JPMS cung cấp ngôn ngữ mô tả module và cơ chế runtime để giải quyết phần cấu trúc của các vấn đề đó.

## 2. Những vấn đề JPMS giải quyết

### 2.1. Khai báo phụ thuộc tường minh

Một named module mô tả phụ thuộc bằng directive **requires** trong **module-info.java**. Ví dụ:

~~~java
module com.acme.orders {
    requires com.acme.customer;
    requires java.logging;

    exports com.acme.orders.api;
}
~~~

Descriptor cho biết module **com.acme.orders** cần đọc module **com.acme.customer** và module **java.logging**. Compiler có thể kiểm tra các kiểu được tham chiếu có nằm trong module mà module hiện tại đọc được hay không. Khi chạy, module system resolve đồ thị phụ thuộc từ các root module và báo lỗi nếu một dependency bắt buộc không thể được tìm thấy hoặc cấu hình không hợp lệ.

Khai báo này giúp:

- Nhìn thấy quan hệ module trực tiếp ngay trong source.
- Phân biệt dependency bắt buộc với dependency tùy chọn ở mức biên dịch qua **requires static**.
- Công bố dependency mà consumer cũng cần đọc bằng **requires transitive** khi kiểu của dependency xuất hiện trong API của module.
- Phát hiện một số lỗi thiếu module hoặc cấu hình module trước khi đường code tương ứng được gọi.

Ví dụ, **requires transitive** có ý nghĩa khi API public của module A trả về hoặc nhận kiểu thuộc module B. Module C chỉ khai báo **requires A** vẫn có thể đọc B theo quan hệ transitive mà A công bố.

Đây là cải thiện về cấu trúc và khả năng kiểm tra. Nó không có nghĩa JPMS tự tải thư viện từ Internet hoặc chọn phiên bản dependency phù hợp; các công việc đó thuộc công cụ build và phân phối.

### 2.2. Kiểm soát package nào là API công khai

JPMS đưa ranh giới truy cập lên cấp module. Một package chỉ được module khác truy cập như API khi module sở hữu package đó export package.

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Consumer có thể dùng kiểu public trong **com.acme.catalog.api** nếu nó đọc module **com.acme.catalog**. Những package khác của module vẫn được giữ kín với named module bên ngoài, dù class trong đó có khai báo public.

Cơ chế này giúp tác giả thư viện:

- Công bố một tập package API có chủ đích.
- Giữ package implementation ở trạng thái nội bộ.
- Giảm phụ thuộc ngoài ý muốn vào class và package không được hỗ trợ như API.
- Có không gian thay đổi implementation mà ít ảnh hưởng đến consumer hơn.

Có thể giới hạn consumer bằng qualified export:

~~~java
exports com.acme.catalog.internal.spi to com.acme.application;
~~~

Khi đó package được export cho module đích được chỉ định. Đây là công cụ để mô tả một API nội bộ dùng chung có kiểm soát, chẳng hạn SPI giữa hai module thuộc cùng một hệ thống.

### 2.3. Phân biệt truy cập API với deep reflection

Framework có thể cần reflection để đọc field, constructor hoặc method không public. JPMS tách quyền này khỏi quyền truy cập API thông thường.

- **exports** cho phép truy cập các kiểu public trong package theo quy tắc ngôn ngữ Java.
- **opens** cho phép deep reflection vào các kiểu trong package tại runtime, trong phạm vi module được mở.

Ví dụ:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Module consumer có thể import API từ package **com.acme.domain.api**. Module **com.acme.json** có thể dùng deep reflection trên package model được mở cho nó. Package model không vì thế trở thành API có thể import tự do.

JPMS còn cho phép mở toàn module bằng **open module**, hoặc mở package có giới hạn bằng qualified opens. Việc mở đúng package và đúng consumer giúp duy trì encapsulation tốt hơn so với việc mở toàn bộ ứng dụng cho mọi thư viện reflection.

### 2.4. Xác định đồ thị module hợp lệ

Module system resolve một tập module và các quan hệ phụ thuộc thành **Configuration**. Các module cần thiết được tìm qua những nguồn module có thể quan sát, ví dụ system modules hoặc module path. Tập module được đưa vào cấu hình phụ thuộc vào root module và các dependency cần thiết; việc một JAR nằm trên module path không tự động có nghĩa nó luôn được resolve vào ứng dụng.

Quá trình resolve giúp kiểm tra:

- Module bắt buộc có tìm thấy được không.
- Tên module và dependency có khớp với descriptor không.
- Đồ thị phụ thuộc có hợp lệ không.
- Package có bị chia theo cách không được phép trong cùng cấu hình named module không.
- Module nào được đưa vào cấu hình khởi chạy.

Module system cũng tạo ra quy tắc readability: module phải đọc một module khác thì code mới có thể tham chiếu kiểu public được export từ module đó. Vì vậy, có class trên đĩa và có quyền truy cập class là hai điều kiện khác nhau.

Nhờ có đồ thị module, lỗi cấu hình có thể được phát hiện ở giai đoạn biên dịch hoặc khởi chạy thay vì chỉ xuất hiện khi một chức năng hiếm khi được sử dụng.

### 2.5. Giảm phụ thuộc trực tiếp bằng service

JPMS tích hợp mô hình service của Java. Module cần một service khai báo **uses**; module cung cấp implementation khai báo **provides ... with ...**.

~~~java
module com.acme.application {
    requires com.acme.spi;
    uses com.acme.spi.ReportExporter;
}
~~~

~~~java
module com.acme.csv.exporter {
    requires com.acme.spi;

    provides com.acme.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

Ứng dụng có thể tìm provider qua **ServiceLoader**:

~~~java
ServiceLoader.load(ReportExporter.class)
    .forEach(exporter -> exporter.export(report));
~~~

Ứng dụng phụ thuộc vào interface service thay vì phải biết trước class triển khai cụ thể. Có thể thêm một provider mới mà không cần viết lại đoạn code gọi service, miễn là provider tuân theo contract và được đưa vào cấu hình/layer thích hợp.

Cơ chế này hữu ích cho driver, serializer, exporter, adapter và plugin. Tuy nhiên, ServiceLoader chỉ giải quyết việc khai báo và tìm provider; nó không phải một hệ thống quản lý vòng đời plugin hoàn chỉnh.

### 2.6. Tạo runtime image phù hợp với ứng dụng

Khi ứng dụng và các thành phần cần thiết có thể được mô tả bằng module, công cụ **jlink** có thể tạo runtime image chỉ chứa tập module được chọn cùng runtime cần thiết. Điều này hỗ trợ phân phối ứng dụng với một runtime phù hợp thay vì luôn yêu cầu cài đặt một JDK đầy đủ.

Ví dụ minh họa:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.application   --output app-runtime
~~~

Root module **com.acme.application** kéo theo các module phụ thuộc cần thiết trong cấu hình. Runtime image có thể nhỏ hơn một JDK đầy đủ và giúp kiểm soát thành phần runtime đi cùng ứng dụng.

Lợi ích này phụ thuộc vào cách đóng gói. Những thư viện vẫn nằm trên classpath hoặc thành phần không tương thích với quy trình liên kết module cần được xử lý riêng. **jlink** cũng không tự cập nhật runtime image khi ứng dụng thay đổi; quy trình build và phát hành vẫn phải tạo và phân phối image mới.

### 2.7. Hỗ trợ chuyển đổi từng bước

JPMS không bắt buộc mọi thư viện trong hệ sinh thái phải chuyển đổi cùng một lúc. Ứng dụng có thể cùng tồn tại với:

- Named module có **module-info.class**.
- Automatic module được suy ra tên từ manifest hoặc tên JAR khi đặt trên module path.
- Code trên classpath thuộc unnamed module.

Cách này giúp chuyển đổi theo từng phần. Tuy nhiên, automatic module và unnamed module có quy tắc đóng gói, readability và encapsulation khác named module. Nếu muốn tận dụng đầy đủ lợi ích của JPMS, cần chuyển các thành phần quan trọng sang descriptor rõ ràng và xác định package API phù hợp.

## 3. Những vấn đề JPMS không giải quyết

### 3.1. Không thay thế Maven, Gradle hoặc công cụ quản lý dependency

JPMS không phải package manager và không phải hệ thống giải quyết phiên bản thư viện. Directive **requires** khai báo module mà ứng dụng cần đọc; nó không mô tả dải phiên bản như một dependency declaration của Maven hoặc Gradle.

JPMS không tự:

- Tải JAR từ repository.
- Chọn phiên bản mới nhất hoặc phiên bản thỏa mãn một dải phiên bản.
- Giải quyết xung đột phiên bản theo quy tắc mediation.
- Khóa phiên bản để tạo build tái lập.
- Quản lý checksum, repository, credential hoặc quy trình publish artifact.

Ví dụ, build file vẫn cần chọn artifact và phiên bản:

~~~groovy
dependencies {
    implementation 'com.acme:customer-api:2.4.0'
}
~~~

Trong module descriptor, ứng dụng khai báo tên module mà artifact cung cấp:

~~~java
module com.acme.orders {
    requires com.acme.customer;
}
~~~

Build tool chọn JAR cụ thể; module system kiểm tra tên module và quan hệ phụ thuộc của JAR đó. Hai cơ chế bổ trợ nhau.

Trong một resolved configuration, tên module là định danh để resolve và không có cơ chế mediation phiên bản tổng quát. Việc đưa hai phiên bản cùng một thư viện vào cùng module configuration không phải cách xử lý xung đột được JPMS tự động hỗ trợ. Các layer riêng có thể phục vụ một số thiết kế nâng cao, nhưng không thay thế quản lý phiên bản dependency của build system.

### 3.2. Không phải sandbox bảo mật

Encapsulation của JPMS kiểm soát khả năng đọc module và truy cập package. Nó không cô lập mã độc hoặc giới hạn quyền hệ điều hành của một module.

Một plugin được nạp trong cùng JVM vẫn có thể thực hiện những hành động mà tiến trình có quyền thực hiện, ví dụ truy cập file, mở kết nối mạng hoặc tạo thread, tùy môi trường và quyền chạy. Module descriptor không cấp một bộ permission độc lập cho từng module.

Vì vậy:

- Không chạy plugin không đáng tin cậy chỉ vì nó nằm trong named module.
- Không xem package chưa export là ranh giới chống mã độc.
- Không dùng **ModuleLayer** thay cho process isolation, container, tài khoản hệ điều hành riêng hoặc cơ chế sandbox phù hợp.
- Không coi **opens** là cơ chế cấp quyền bảo mật tổng quát; nó chỉ điều chỉnh deep reflection giữa các module.

Strong encapsulation là ranh giới cấu trúc trong Java platform, không phải ranh giới tin cậy giữa hai tiến trình.

### 3.3. Không tự thiết kế domain boundary hoặc kiến trúc ứng dụng

JPMS cho phép chia ứng dụng thành module, nhưng không tự quyết định cách chia domain. Nếu gom quá nhiều chức năng không liên quan vào một module, hoặc tạo module quá nhỏ chỉ để tăng số lượng, kiến trúc vẫn có thể khó hiểu.

JPMS không tự:

- Xác định bounded context hoặc domain model.
- Quyết định module nào sở hữu dữ liệu và nghiệp vụ.
- Thiết kế API ổn định giữa các team.
- Ngăn mọi dependency ngược về mặt kiến trúc nếu các module vẫn được khai báo cho phép.
- Tự phát hiện một package API đang chứa quá nhiều trách nhiệm.

Nhóm phát triển vẫn phải quyết định ranh giới module, quyền sở hữu code, hợp đồng API và hướng phụ thuộc. JPMS giúp thực thi một phần các quyết định đó ở cấp package/module.

### 3.4. Không thay thế hệ thống plugin và quản lý vòng đời

**ServiceLoader** và **ModuleLayer** cung cấp nền tảng để tìm service và định nghĩa module trong layer riêng. Nhưng một hệ thống plugin hoàn chỉnh còn cần nhiều chức năng khác:

- Quy tắc phát hiện và cài đặt plugin.
- Kiểm tra phiên bản API tương thích.
- Quản lý trạng thái khởi tạo, hoạt động, lỗi và dừng plugin.
- Cấu hình, logging, metrics và xử lý lỗi riêng cho plugin.
- Chính sách nâng cấp hoặc rollback.
- Quy tắc giao tiếp và chia sẻ dữ liệu giữa host với plugin.

Tạo được layer không đồng nghĩa plugin đã có lifecycle. Module system cũng không cung cấp thao tác unload module theo nghĩa một lệnh đảm bảo giải phóng ngay toàn bộ class và tài nguyên. Class unloading phụ thuộc vào khả năng thu hồi class loader và các tham chiếu liên quan của JVM; layer hoặc class loader còn được tham chiếu thì class có thể tiếp tục tồn tại.

Một ứng dụng cần plugin động phải tự thiết kế hợp đồng lifecycle và quy trình thu hồi tài nguyên. Nếu cần cập nhật plugin an toàn hoặc chạy mã không đáng tin cậy, có thể cần tiến trình riêng.

### 3.5. Không loại bỏ hoàn toàn classpath và thư viện legacy

JPMS hỗ trợ giai đoạn chuyển đổi, nhưng không tự biến mọi JAR cũ thành module được thiết kế tốt. Automatic module là cầu nối tương thích. Unnamed module giúp code trên classpath tiếp tục chạy. Cả hai đều có thể khiến ranh giới module chưa chặt chẽ.

Nếu phần lớn code vẫn nằm trên classpath:

- Phụ thuộc ở cấp module chưa được khai báo đầy đủ.
- Package nội bộ của thư viện legacy có thể chưa có encapsulation như mong muốn.
- Một số tùy chọn tương thích như **--add-reads**, **--add-exports** hoặc **--add-opens** có thể được dùng để ứng dụng cũ tiếp tục hoạt động.
- Lợi ích kiểm soát truy cập của named module chỉ áp dụng trong phạm vi module system quản lý.

Do đó, việc thêm một file descriptor vào một phần project không đồng nghĩa toàn bộ ứng dụng đã có kiến trúc module rõ ràng.

### 3.6. Không tự đảm bảo tương thích API và khả năng nâng cấp

JPMS giúp công bố package API và ẩn package nội bộ. Nó không tự bảo đảm rằng API đã export sẽ tương thích giữa các phiên bản. Một thay đổi có thể phá vỡ source compatibility hoặc binary compatibility dù descriptor vẫn giữ nguyên.

Nhóm phát triển vẫn cần:

- Chính sách versioning cho API.
- Kiểm thử tương thích.
- Quy trình deprecation và migration.
- Kiểm tra dependency trước khi nâng cấp.
- Tài liệu về hành vi và hợp đồng của API.

Một package được export chỉ có nghĩa module cho phép truy cập package đó; nó không phải cam kết rằng mọi class và method trong package sẽ ổn định mãi mãi.

### 3.7. Không tự giải quyết mọi vấn đề đóng gói và triển khai

JPMS mô tả module và hỗ trợ runtime image, nhưng không thay thế toàn bộ pipeline phát hành. Ứng dụng vẫn cần quyết định:

- Cách tạo JAR, image hoặc installer.
- Cách cấu hình môi trường và secret.
- Cách phát hành, cập nhật, rollback và theo dõi phiên bản.
- Cách phân phối native library hoặc tài nguyên ngoài module.
- Cách triển khai trên máy chủ, container hoặc thiết bị đích.

Module descriptor không chứa quy trình vận hành ứng dụng. **jlink** tạo runtime image; pipeline vẫn phải kiểm thử và phát hành image đó.

## 4. Bảng phân định trách nhiệm

| Nhu cầu | JPMS hỗ trợ đến đâu? | Cơ chế/công cụ thường đi kèm |
|---|---|---|
| Khai báo module phụ thuộc module nào | Có, qua **requires** và module resolution | Maven, Gradle để chọn artifact và phiên bản |
| Công bố package API | Có, qua **exports** | Thiết kế API, review kiến trúc |
| Cho framework deep reflection | Có, qua **opens** | Cấu hình framework và kiểm soát quyền truy cập |
| Tìm implementation của service | Có, qua **uses**, **provides** và **ServiceLoader** | Plugin manager để quản lý lifecycle và cấu hình |
| Resolve module graph khi khởi chạy | Có | Module path, launcher và cấu hình triển khai |
| Tạo runtime image theo module cần thiết | Có, thông qua **jlink** | CI/CD và quy trình phân phối runtime |
| Tải dependency và mediation phiên bản | Không | Maven, Gradle hoặc công cụ dependency tương ứng |
| Sandbox mã không đáng tin cậy | Không | Process isolation, container và chính sách hệ điều hành |
| Thiết kế domain boundary | Không tự quyết định | Kiến trúc ứng dụng và quy ước của nhóm |
| Nâng cấp, rollback, lifecycle plugin | Không cung cấp đầy đủ | Plugin framework hoặc logic quản lý riêng |
| Đảm bảo API tương thích qua phiên bản | Không | Versioning, compatibility tests và quy trình phát hành |

## 5. Ví dụ: chọn đúng công cụ cho một vấn đề

Giả sử ứng dụng báo cáo có ba phần: module nghiệp vụ, thư viện CSV và một plugin xuất báo cáo PDF.

**Tình huống A — ứng dụng tham chiếu package nội bộ ngoài ý muốn**

Nếu module nghiệp vụ import một class trong package implementation của thư viện CSV, hãy kiểm tra descriptor của thư viện. Chỉ export package API cần thiết và giữ package implementation không export. Đây là vấn đề JPMS giải quyết trực tiếp.

**Tình huống B — build đang kéo hai phiên bản thư viện CSV**

Nếu dependency graph chứa hai phiên bản artifact, hãy xử lý bằng dependency constraints, version catalog, exclusion hoặc quy tắc resolution của Maven/Gradle. JPMS không tự chọn phiên bản mong muốn. Sau khi build chọn được artifact, descriptor xác định module mà code cần đọc.

**Tình huống C — muốn thêm provider PDF mà không sửa code gọi service**

Định nghĩa interface service trong module API, khai báo **uses** ở module ứng dụng và **provides** ở module plugin. Đây là trường hợp phù hợp với ServiceLoader. Nếu cần bật/tắt, cấu hình hoặc cập nhật plugin, hãy bổ sung lifecycle manager.

**Tình huống D — plugin do bên thứ ba cung cấp**

Tạo custom ModuleLayer có thể giúp tổ chức module và class loader. Nhưng nếu plugin không đáng tin cậy, vẫn cần chạy trong tiến trình hoặc môi trường cô lập phù hợp. Layer không giới hạn quyền file system hay mạng của plugin.

**Tình huống E — muốn giảm kích thước runtime**

Phân tích module cần thiết và tạo runtime image bằng jlink. Đây là công việc thuộc JPMS/JDK tooling. Việc đóng gói image vào installer, container và cập nhật image vẫn thuộc pipeline triển khai.

## 6. Cách quyết định có nên dùng JPMS

Hãy bắt đầu bằng câu hỏi về loại vấn đề:

1. **Muốn phụ thuộc rõ ràng và kiểm tra được?** Dùng named module và khai báo **requires**.
2. **Muốn giới hạn API mà consumer nhìn thấy?** Dùng **exports** và giữ package nội bộ không export.
3. **Framework cần reflection?** Mở đúng package bằng **opens**, giới hạn module đích nếu có thể.
4. **Muốn thay implementation qua service?** Dùng **uses**, **provides** và **ServiceLoader**.
5. **Muốn tạo runtime image nhỏ hơn?** Xem xét **jlink** sau khi xác định dependency module.
6. **Muốn tải dependency, giải quyết phiên bản hoặc khóa build?** Cấu hình Maven/Gradle.
7. **Muốn chạy mã không tin cậy?** Thiết kế sandbox hoặc process isolation ở tầng vận hành.
8. **Muốn nâng cấp và quản lý plugin?** Xây dựng lifecycle, compatibility và rollback bên cạnh ModuleLayer.

Không phải mọi ứng dụng đều cần chuyển đổi toàn bộ ngay lập tức. Với ứng dụng nhỏ, classpath có thể vẫn đủ cho mục tiêu hiện tại. Với thư viện dùng chung, ứng dụng lớn có nhiều nhóm phát triển, hoặc runtime cần được tinh gọn, named module có thể đem lại lợi ích rõ ràng hơn. Hãy chọn phạm vi chuyển đổi dựa trên lợi ích của ranh giới phụ thuộc và encapsulation mà hệ thống thực sự cần.

## 7. Kết luận

JPMS giải quyết một khoảng trống quan trọng của Java: mô tả phụ thuộc và quyền truy cập ở cấp module. Nó giúp compiler và runtime hiểu module cần gì, package nào được công bố, package nào được mở cho reflection, service nào được tiêu thụ và provider nào được đăng ký. Khi các module được thiết kế tốt, ứng dụng có thể có đồ thị phụ thuộc rõ ràng hơn và tạo runtime image theo nhu cầu.

Những trách nhiệm khác vẫn nằm ở các tầng khác. Maven/Gradle quản lý dependency và phiên bản; kiến trúc ứng dụng xác định ranh giới domain; ServiceLoader chỉ là cơ chế tìm service; ModuleLayer không phải sandbox; pipeline phát hành quản lý triển khai và cập nhật. Hiểu đúng giới hạn này giúp dùng JPMS cho đúng việc và tránh kỳ vọng nó thay thế các công cụ vốn giải quyết những bài toán khác.
