# Kiểm tra JAR bằng jar --describe-module

## 1. Mục đích của jar --describe-module

Từ Java 9, Java Platform Module System (JPMS) cho phép đóng gói ứng dụng và thư viện thành các named module. Một JAR có thể chứa module descriptor module-info.class, hoặc không có descriptor và được xem là automatic module khi đặt trên module path.

Công cụ **jar** đi kèm JDK hỗ trợ đọc thông tin module của một JAR:

    jar --describe-module --file path/to/library.jar

Lệnh này giúp trả lời các câu hỏi:

- JAR có module descriptor tường minh hay không?
- Tên module là gì?
- Module export những package nào?
- Module yêu cầu các module nào?
- Module khai báo service nào bằng uses và cung cấp provider nào bằng provides?
- JAR không có descriptor thì tên automatic module được suy ra như thế nào?

**jar --describe-module** là thao tác đọc metadata. Nó không chạy ứng dụng, không khởi tạo lớp, không tự giải quyết toàn bộ dependency và không chứng minh rằng mọi đường dẫn chạy thực tế đều hoạt động.

## 2. Cú pháp cơ bản

Cú pháp thường dùng:

    jar --describe-module --file <jar-file>

Ví dụ trên Windows:

    jar --describe-module --file .\lib\codec-api.jar

Ví dụ trên Linux hoặc macOS:

    jar --describe-module --file ./lib/codec-api.jar

Có thể viết option theo thứ tự khác:

    jar --file ./lib/codec-api.jar --describe-module

Điều quan trọng là chạy **jar** từ JDK có phiên bản phù hợp. Kiểm tra phiên bản công cụ:

    jar --version
    java --version

Nếu máy chỉ có JRE hoặc PATH trỏ đến một JDK khác với phiên bản dự kiến, kết quả kiểm tra có thể khác môi trường build hoặc deploy. Nên kiểm tra cả đường dẫn thực tế của công cụ khi có nhiều JDK được cài đặt.

## 3. Đọc kết quả của một modular JAR

Giả sử JAR được tạo từ module descriptor sau:

    module com.example.codec {
        requires java.logging;

        exports com.example.codec;
        exports com.example.codec.spi to com.example.application;

        uses com.example.codec.spi.CodecProvider;

        provides com.example.codec.spi.CodecProvider
            with com.example.codec.internal.JsonCodecProvider;
    }

Chạy:

    jar --describe-module --file codec.jar

Kết quả minh họa có thể có dạng:

    com.example.codec jar:file:///.../codec.jar!/module-info.class
    exports com.example.codec
    qualified exports com.example.codec.spi to com.example.application
    requires java.base mandated
    requires java.logging
    uses com.example.codec.spi.CodecProvider
    provides com.example.codec.spi.CodecProvider
        with com.example.codec.internal.JsonCodecProvider
    contains com.example.codec.internal

Cách đọc các dòng chính:

- **Tên module và nguồn descriptor:** dòng đầu cho biết tên module và vị trí module descriptor mà công cụ đọc được.
- **exports:** package được công khai cho các module khác theo quy tắc JPMS. Nếu có danh sách to, đây là qualified export, chỉ các module được nêu mới nhận quyền truy cập package theo directive đó.
- **requires:** module dependency được khai báo. java.base mandated là dependency nền tảng được compiler thêm ngầm cho module thông thường.
- **uses:** module này cần tìm provider của service được nêu.
- **provides ... with ...:** module này đăng ký một hoặc nhiều lớp provider cho service.
- **contains:** package nằm trong module nhưng không được export. Dòng này giúp nhận diện package nội bộ; nó không phải directive trong module-info.java.

Kết quả thực tế phụ thuộc nội dung descriptor và JDK đang dùng. Không phải JAR nào cũng có đủ tất cả các dòng trên.

## 4. Phân biệt explicit module và automatic module

### JAR có module-info.class

Nếu JAR có module-info.class hợp lệ ở vị trí gốc, nó là explicit modular JAR. Tên module và các directive được lấy từ descriptor đã biên dịch.

Có thể xem cấu trúc archive bằng:

    jar --list --file codec.jar

Trong danh sách, tìm module-info.class ở gốc JAR. Ví dụ:

    META-INF/
    META-INF/MANIFEST.MF
    module-info.class
    com/example/codec/Codec.class

Khi đó, kết quả **jar --describe-module** sẽ mô tả module được khai báo tường minh.

### JAR không có module-info.class

Nếu JAR không chứa descriptor module, công cụ có thể suy ra automatic module khi kiểm tra:

    jar --describe-module --file legacy-codec.jar

Thông báo thường có dạng:

    No module descriptor found. Derived automatic module.

Sau đó công cụ in tên automatic module và các package được suy ra từ nội dung JAR. JAR dạng này vẫn có thể được đặt trên module path để module khác phụ thuộc vào nó, nhưng metadata của nó không giống một explicit module.

Automatic module thường có các đặc điểm:

- Đọc mọi named module khác và unnamed module theo quy tắc automatic module.
- Export các package mà nó chứa theo quy tắc automatic module.
- Tên module có thể được lấy từ thuộc tính manifest Automatic-Module-Name hoặc suy ra từ tên file JAR.
- Không có các directive requires, exports, opens, uses và provides tường minh như trong module descriptor của explicit module.

Đối với thư viện muốn giữ tên module ổn định qua các lần đổi tên file hoặc phiên bản phát hành, nên khai báo **Automatic-Module-Name** trong manifest khi chưa thể chuyển ngay sang explicit module. Ví dụ:

    Manifest-Version: 1.0
    Automatic-Module-Name: com.example.legacycodec

Nếu không có thuộc tính này, tên automatic module được suy ra từ tên file theo quy tắc đặt tên của JPMS. Đổi tên JAR có thể làm thay đổi tên module được suy ra; vì thế không nên dựa vào tên tự suy ra như một hợp đồng ổn định lâu dài.

**Lưu ý:** một JAR thông thường nằm trên classpath được nạp vào unnamed module. Việc công cụ có thể mô tả nó như automatic module không có nghĩa nó tự trở thành automatic module trong mọi cách chạy. Vai trò automatic module phát sinh khi JAR được đưa vào module path.

## 5. Kiểm tra Multi-Release JAR

Multi-Release JAR (MR JAR) có thể chứa các lớp hoặc module descriptor thay thế theo phiên bản Java trong thư mục META-INF/versions/.

Một cấu trúc minh họa:

    META-INF/
    META-INF/MANIFEST.MF
    com/example/api/Codec.class
    META-INF/versions/9/module-info.class
    META-INF/versions/11/com/example/api/Codec.class

Manifest của MR JAR phải có thuộc tính:

    Multi-Release: true

Để xem module descriptor dành cho một phiên bản cụ thể, dùng option **--release**:

    jar --describe-module --file codec-mr.jar --release 9

Option này yêu cầu jar tool mô tả nội dung phù hợp với phiên bản được chỉ định. Khi kiểm tra MR JAR, nên đối chiếu descriptor ở các phiên bản mục tiêu mà ứng dụng hỗ trợ; descriptor có thể khác nhau giữa các release.

Có thể liệt kê nội dung archive để xác nhận các file nằm trong thư mục phiên bản:

    jar --list --file codec-mr.jar

Đừng suy luận rằng một descriptor trong META-INF/versions/9/ sẽ luôn được dùng trong mọi môi trường. Việc chọn nội dung phụ thuộc phiên bản runtime và quy tắc multi-release JAR.

## 6. Đối chiếu descriptor với cấu trúc JAR

Khi kết quả module không như mong đợi, hãy kiểm tra nội dung archive:

    jar --list --file codec.jar

Các vị trí thường cần chú ý:

| Đường dẫn trong JAR | Ý nghĩa |
|---|---|
| module-info.class | Descriptor của explicit module ở gốc archive |
| META-INF/versions/<N>/module-info.class | Descriptor dành cho phiên bản Java N trong MR JAR |
| META-INF/MANIFEST.MF | Manifest, có thể chứa Automatic-Module-Name và Multi-Release |
| META-INF/services/<service-name> | Metadata provider kiểu classpath |
| com/example/.../*.class | Các lớp và package của module |

Với JAR có module descriptor, tên module trong kết quả phải phù hợp với tên khai báo trong source module-info.java đã biên dịch. Nếu tên hoặc directive sai, cần kiểm tra đúng artifact đã build, không chỉ kiểm tra source trong repository.

Không nên chỉnh sửa trực tiếp một file JAR đang được phát hành để sửa descriptor. Hãy sửa source/module-info.java hoặc cấu hình build, build lại artifact rồi chạy **jar --describe-module** trên chính file đầu ra mới.

## 7. Phân biệt kết quả mô tả với kiểm tra khả năng chạy

**jar --describe-module** cho biết metadata của một JAR. Kết quả này chưa trả lời được mọi vấn đề khi đưa module vào ứng dụng.

Ví dụ, dòng:

    requires com.example.logging

chỉ cho biết descriptor khai báo dependency đó. Nó không chứng minh rằng module com.example.logging có sẵn trên module path khi chạy ứng dụng.

Để kiểm tra tính nhất quán của tập module trên module path, có thể dùng launcher:

    java --module-path mods --validate-modules

Lệnh này yêu cầu JVM kiểm tra module configuration trong module path rồi kết thúc. Đây là bước kiểm tra bổ sung, không thay thế việc chạy ứng dụng bằng cấu hình thực tế.

Có thể dùng thêm **jdeps** để phân tích dependency ở cấp lớp/package:

    jdeps --module-path mods --check com.example.codec

jdeps trả lời câu hỏi về phụ thuộc bytecode và module ở phạm vi phân tích của nó; nó không thay thế việc kiểm tra service provider, reflection hoặc cấu hình runtime đặc thù.

Một quy trình kiểm tra thường dùng:

1. Chạy jar --describe-module --file ... để xác định tên module và các directive.
2. Chạy jar --list --file ... để kiểm tra descriptor, manifest và cấu trúc package.
3. Nếu là MR JAR, lặp lại mô tả với --release cho các phiên bản mục tiêu.
4. Đặt artifact cùng dependency lên module path và chạy java --validate-modules.
5. Chạy ứng dụng hoặc bài kiểm tra integration để xác nhận service discovery, reflection và luồng khởi động thực tế.

## 8. Những lỗi thường gặp

### Không tìm thấy file JAR

Nếu jar tool báo không tìm thấy archive, kiểm tra đường dẫn và thư mục làm việc:

    jar --describe-module --file ./build/libs/codec.jar

Có thể dùng đường dẫn tuyệt đối để loại bỏ nhầm lẫn về thư mục hiện tại. Đường dẫn có dấu cách nên đặt trong dấu ngoặc kép:

    jar --describe-module --file "C:/work/my project/codec.jar"

### Kết quả là automatic module ngoài dự kiến

Nếu mong đợi explicit module nhưng công cụ báo không tìm thấy module descriptor:

- Kiểm tra JAR đầu ra có module-info.class ở gốc hay không.
- Kiểm tra build tool có thực sự biên dịch và đóng gói module-info.java không.
- Với MR JAR, kiểm tra descriptor trong META-INF/versions/<N>/ và dùng --release tương ứng.
- Xác nhận đang kiểm tra đúng JAR mới build, không phải bản cũ trong thư mục khác.

### Tên automatic module thay đổi

Nếu tên module được suy ra từ tên file, việc đổi tên file hoặc thêm hậu tố phiên bản có thể ảnh hưởng tên module. Để tên ổn định, khai báo **Automatic-Module-Name** trong manifest hoặc chuyển sang explicit module descriptor.

### Thiếu dependency khi chạy

jar --describe-module có thể hiển thị requires nhưng không tìm thấy module dependency ở thời điểm chạy. Hãy kiểm tra module path, phiên bản artifact và kết quả java --validate-modules. Không giả định rằng một dependency xuất hiện trong descriptor đã được đóng gói hoặc cài đặt cùng JAR.

### Dùng nhầm JDK

Nếu nhiều JDK cùng tồn tại, lệnh jar và java có thể đến từ hai phiên bản khác nhau. Kiểm tra jar --version, java --version và đường dẫn executable để bảo đảm đang phân tích artifact bằng bộ công cụ dự kiến.

## 9. Ví dụ kiểm tra theo từng bước

Giả sử có artifact:

    build/libs/codec.jar

Bước 1 — đọc descriptor hoặc automatic module:

    jar --describe-module --file build/libs/codec.jar

Bước 2 — xem các file bên trong:

    jar --list --file build/libs/codec.jar

Bước 3 — nếu đây là MR JAR, xem descriptor cho Java 9:

    jar --describe-module --file build/libs/codec.jar --release 9

Bước 4 — kiểm tra tập module sau khi đặt các JAR vào thư mục mods:

    java --module-path mods --validate-modules

Bước 5 — chạy ứng dụng bằng module path thực tế:

    java --module-path mods --module com.example.application/com.example.application.Main

Ví dụ trên dùng tên module và lớp main minh họa; thay bằng tên được khai báo trong module descriptor của dự án. Trên Windows PowerShell, có thể viết lệnh launcher trên một dòng để tránh khác biệt cú pháp nối dòng.

## 10. Ghi nhớ

- **jar --describe-module --file <jar-file>** đọc và hiển thị module metadata của JAR.
- Explicit modular JAR có module descriptor module-info.class; automatic module không có descriptor tường minh và được suy ra khi dùng trên module path.
- **Automatic-Module-Name** trong manifest giúp giữ tên automatic module ổn định.
- JAR trên classpath thuộc unnamed module; việc mô tả automatic module không làm JAR tự chuyển thành automatic module trong classpath.
- **--release** hữu ích khi kiểm tra descriptor trong Multi-Release JAR.
- **exports**, **requires**, **uses** và **provides** trong kết quả giúp đọc cấu hình module; contains cho biết package nội bộ.
- **jar --describe-module** không chứng minh dependency đã có mặt hoặc ứng dụng chạy thành công.
- Dùng **jar --list**, **java --validate-modules**, **jdeps** và integration test để bổ sung các góc kiểm tra khác nhau.
- Luôn kiểm tra đúng JAR đầu ra và đúng phiên bản JDK.

**jar --describe-module là bước đầu để hiểu một JAR được nhìn nhận như module nào và khai báo những quan hệ gì.** Kết hợp nó với kiểm tra cấu trúc archive và module path sẽ giúp phát hiện sớm sai lệch giữa artifact, descriptor và cấu hình chạy.

## Tài liệu tham khảo

- Java SE 21 Tool Specifications — jar: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 Tool Specifications — jdeps: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html