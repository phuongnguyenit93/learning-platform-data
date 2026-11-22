# Multi-release JAR và module-info ở META-INF/versions

Multi-release JAR (MR-JAR) cho phép một thư viện đóng gói nhiều phiên bản class và resource trong cùng một file JAR. JVM chọn phiên bản phù hợp với major version của runtime, nhờ đó thư viện có thể giữ implementation tương thích với Java cũ nhưng vẫn tận dụng API mới trên Java mới.

Một trường hợp quan trọng là đặt module descriptor tại META-INF/versions/9/module-info.class. Cách này cho phép một JAR có các class nền tương thích Java 8, đồng thời trở thành explicit module khi được dùng trên Java 9 trở lên.

## 1. Cấu trúc của Multi-release JAR

Một MR-JAR được nhận diện bằng main attribute trong manifest:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Các file phụ thuộc phiên bản Java được đặt dưới thư mục:

~~~text
META-INF/versions/N/
~~~

N là major version của Java, bắt đầu từ 9. Ví dụ:

~~~text
library.jar
|-- META-INF/
|   |-- MANIFEST.MF
|   |-- versions/
|       |-- 9/
|       |   |-- module-info.class
|       |   |-- com/example/RuntimeFeature.class
|       |-- 17/
|           |-- com/example/RuntimeFeature.class
|-- com/
    |-- example/
        |-- Library.class
        |-- RuntimeFeature.class
~~~

Khi chạy trên Java N, class loader tìm entry ở version N trước, sau đó lần lượt ở các version thấp hơn nhưng không thấp hơn 9, cuối cùng mới dùng entry ở thư mục gốc. Các thư mục có version lớn hơn runtime hiện tại không được chọn.

Ví dụ, với runtime Java 17:

- Nếu có entry ở versions/17, dùng entry đó.
- Nếu không có versions/17 nhưng có versions/11, dùng entry ở versions/11.
- Nếu không có version phù hợp, dùng entry ở thư mục gốc.

Trên Java 8, runtime chưa hỗ trợ cơ chế multi-release nên dùng các entry nền ở thư mục gốc. Các thư mục versioned không được xử lý như phiên bản thay thế.

Tên N phải là số nguyên major hợp lệ từ 9 trở lên. Dùng đúng dạng META-INF/versions/9, không đặt module descriptor ở một đường dẫn lồng sâu hơn như META-INF/versions/9/META-INF/module-info.class.

## 2. Vì sao module-info có thể nằm trong META-INF/versions/9?

Một modular JAR thông thường có module descriptor tại root:

~~~text
module-info.class
com/example/Library.class
~~~

Nhưng một modular multi-release JAR có thể đặt module descriptor ở root hoặc trực tiếp trong một thư mục versioned. Do đó, JAR có thể có cấu trúc:

~~~text
library.jar
|-- META-INF/
|   |-- MANIFEST.MF
|   |-- versions/
|       |-- 9/
|           |-- module-info.class
|           |-- com/example/Java9Feature.class
|-- com/
    |-- example/
        |-- Library.class
~~~

Trong ví dụ này:

- Các class ở root là phần nền, có thể được biên dịch để chạy trên Java 8.
- module-info.class ở versions/9 mô tả module dành cho Java 9 trở lên.
- Trên Java 9+, khi JAR được đặt trên module path và manifest bật Multi-Release, JDK có thể nhận diện JAR này là một explicit module.
- Trên Java 8, không có module system và module descriptor versioned không được sử dụng; các class nền vẫn có thể chạy như JAR thông thường.

Đây là cách chuyển một thư viện tương thích Java 8 thành modular JAR mà không buộc người dùng Java 8 phải nâng cấp ngay.

Lưu ý: module-info.class phải nằm trực tiếp trong META-INF/versions/N. Một module descriptor chỉ được nhận diện theo quy tắc modular multi-release JAR khi archive được đánh dấu Multi-Release: true.

## 3. Manifest và quy tắc chọn phiên bản

Manifest phải có thuộc tính Multi-Release trong main section:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

Thuộc tính này áp dụng cho toàn bộ JAR. Chỉ tạo thư mục META-INF/versions/9 mà thiếu thuộc tính Multi-Release: true là chưa đủ để runtime xử lý các entry theo cơ chế MR-JAR.

Khi chạy trên một JDK hỗ trợ multi-release, runtime chọn entry có version lớn nhất không vượt quá major version hiện tại. Sau đó mới fallback về entry ở root.

Ví dụ với một class có ba bản:

~~~text
com/example/RuntimeFeature.class
META-INF/versions/9/com/example/RuntimeFeature.class
META-INF/versions/17/com/example/RuntimeFeature.class
~~~

| Runtime | Entry được chọn |
|---|---|
| Java 8 | Root |
| Java 9 | Version 9 |
| Java 11 | Version 9 |
| Java 17 | Version 17 |
| Java 21 | Version 17 |

Việc chọn phiên bản diễn ra theo từng entry. Một class có thể được lấy từ root trong khi class khác trong cùng JAR được lấy từ versions/17.

## 4. Quy tắc tương thích của module descriptor versioned

Module descriptor ở vùng versioned được xử lý gần giống một class hoặc resource versioned, nhưng có thêm ràng buộc để module giữ cấu trúc nhất quán giữa các phiên bản.

Nếu descriptor ở version cao hơn thay thế descriptor ở version thấp hơn hoặc descriptor ở root, hai descriptor phải giống nhau, ngoại trừ hai nhóm khác biệt được cho phép:

1. Các requires không có modifier transitive đối với module thuộc namespace java.* hoặc jdk.* có thể khác nhau.
2. Các uses clause có thể khác nhau, kể cả khi service type được định nghĩa ngoài các module java.* và jdk.*.

Những phần còn lại của module descriptor như tên module, exports, opens, provides và các requires khác phải được giữ nhất quán theo quy tắc của JAR specification.

Nếu JAR chỉ có module-info.class ở versions/9, descriptor đó là descriptor đầu tiên. Nếu có thêm descriptor ở versions/17, descriptor 17 phải nhất quán với descriptor 9 theo các ngoại lệ trên.

Ví dụ, một module có thể bổ sung uses cho một service chỉ tồn tại từ Java 17 trong module-info ở versions/17. Tuy nhiên, không nên thay đổi tùy ý exports hoặc danh sách provider giữa các descriptor versioned.

## 5. Quy tắc tương thích API của class versioned

MR-JAR được thiết kế để giữ API công khai nhất quán giữa các phiên bản Java. Vì vậy, class public hoặc protected nằm trong một versioned directory thông thường phải có class tương ứng cùng fully qualified name và access modifier ở root hoặc ở versioned directory thấp hơn mà nó thay thế.

Với modular MR-JAR, có một ngoại lệ: class public hoặc protected trong package không được export theo module descriptor không bắt buộc phải có class tương ứng ở root.

Ví dụ:

~~~text
com/example/api/Client.class
META-INF/versions/17/com/example/api/Client.class
~~~

Nếu package com.example.api được export, bản Java 17 của Client phải duy trì API công khai tương ứng với bản nền. Implementation bên trong có thể khác, nhưng chữ ký public/protected cần nhất quán.

Điều này giúp consumer biên dịch với một phiên bản Java vẫn có thể sử dụng thư viện trên phiên bản khác mà không gặp thay đổi API bất ngờ.

## 6. Tạo MR-JAR có module-info ở version 9

Giả sử thư viện hỗ trợ Java 8 và có module descriptor từ Java 9. Có thể tổ chức đầu ra build như sau:

~~~text
build/
|-- base/
|   |-- com/example/api/Library.class
|   |-- com/example/api/RuntimeFeature.class
|-- v9/
    |-- module-info.class
    |-- com/example/api/RuntimeFeature.class
~~~

Phần base chứa class tương thích Java 8. Phần v9 chứa module descriptor và implementation dành cho Java 9. Ví dụ module-info.java:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Biên dịch phần nền bằng JDK 9 trở lên với target Java 8:

~~~bash
javac --release 8 -d build/base \
    src/base/com/example/api/Library.java \
    src/base/com/example/api/RuntimeFeature.java
~~~

Biên dịch module descriptor và class version 9:

~~~bash
javac --release 9 -d build/v9 \
    src/v9/module-info.java \
    src/v9/com/example/api/RuntimeFeature.java
~~~

Đóng gói hai phần vào cùng JAR:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/v9 .
~~~

Tùy chọn --release 9 đưa các file tiếp theo vào META-INF/versions/9. Khi dùng jar tool để tạo các entry versioned, manifest được đánh dấu Multi-Release: true. Nếu dùng Maven, Gradle hoặc công cụ đóng gói khác, cần kiểm tra manifest được tạo đúng.

Có thể thêm nhiều release bằng cách lặp lại tùy chọn --release với version tương ứng:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/v9 . \
    --release 17 -C build/v17 .
~~~

Mỗi thư mục versioned phải chứa các class đã biên dịch phù hợp với major version của thư mục đó. Ví dụ class trong versions/17 không được có class file version cao hơn Java 17.

## 7. Kiểm tra cấu trúc JAR sau khi đóng gói

Đừng chỉ dựa vào việc build kết thúc thành công. Hãy kiểm tra cấu trúc archive và module descriptor.

Liệt kê các entry:

~~~bash
jar --list --file build/library.jar
~~~

Kết quả cần có các entry tương tự:

~~~text
META-INF/MANIFEST.MF
com/example/api/Library.class
com/example/api/RuntimeFeature.class
META-INF/versions/9/module-info.class
META-INF/versions/9/com/example/api/RuntimeFeature.class
~~~

Kiểm tra manifest:

~~~bash
unzip -p build/library.jar META-INF/MANIFEST.MF
~~~

Xác nhận main section chứa:

~~~text
Multi-Release: true
~~~

Trên JDK 9 trở lên, có thể yêu cầu jar tool mô tả module:

~~~bash
jar --describe-module --file build/library.jar
~~~

Nếu JAR chỉ có module descriptor trong versions/9, lệnh trên vẫn phải nhận diện module khi chạy bằng JDK hỗ trợ modular MR-JAR.

Có thể kiểm tra bằng ModuleFinder trong Java:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

ModuleReference reference = ModuleFinder.of(
        Path.of("build/library.jar"))
        .find("com.example.library")
        .orElseThrow(() ->
                new IllegalStateException("Không tìm thấy module"));

System.out.println(reference.descriptor().name());
System.out.println(reference.descriptor().packages());
~~~

ModuleFinder.of() dùng quy tắc module path để tìm module descriptor, bao gồm descriptor trong vùng versioned của MR-JAR hợp lệ. Đây là phép kiểm tra tốt để xác nhận JAR được nhận diện như explicit module trên JDK hiện tại.

Với JDK mới có hỗ trợ, jar --validate --file build/library.jar có thể kiểm tra integrity và tính nhất quán API của MR-JAR. Nếu dùng JDK cũ chưa hỗ trợ tùy chọn này, dùng các bước kiểm tra cấu trúc, manifest và ModuleFinder ở trên.

## 8. Kiểm thử hành vi theo từng JDK

Một test hữu ích phải xác minh cả cấu trúc archive lẫn cách runtime chọn phiên bản.

### Kiểm tra descriptor trên Java 9+

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ModularJarTest {

    @Test
    void recognizesVersionedModuleDescriptor() {
        var reference = ModuleFinder.of(Path.of("build/library.jar"))
                .find("com.example.library")
                .orElseThrow();

        assertEquals(
                "com.example.library",
                reference.descriptor().name());
    }
}
~~~

Test này nên chạy trên JDK 9 trở lên. Trên Java 8 không có ModuleFinder và không có khái niệm named module để kiểm tra.

### Kiểm tra entry được chọn theo runtime version

Có thể dùng JarFile với Runtime.Version để đọc view multi-release tương ứng:

~~~java
import java.io.IOException;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;
import java.nio.file.Path;

try (JarFile jar = new JarFile(
        Path.of("build/library.jar").toFile(),
        true,
        ZipFile.OPEN_READ,
        Runtime.version())) {

    JarEntry entry = jar.getJarEntry(
            "com/example/api/RuntimeFeature.class");

    if (entry == null) {
        throw new IllegalStateException("Không tìm thấy RuntimeFeature");
    }

    System.out.println(entry.getRealName());
}
~~~

getRealName() cho biết tên entry thực tế trong archive được chọn cho logical entry đó. Chẳng hạn, trên Java 17 nếu bản version 17 tồn tại, tên thực tế có thể là META-INF/versions/17/com/example/api/RuntimeFeature.class.

### Chạy kiểm thử trên nhiều runtime

Nên có test matrix tối thiểu:

| Runtime | Điều cần xác minh |
|---|---|
| Java 8 | Class nền ở root chạy được; module descriptor versioned không ảnh hưởng runtime |
| Java 9 | Nhận diện module-info ở versions/9 và chọn class version 9 |
| Java 11 | Chọn bản version cao nhất không vượt quá 11, ví dụ version 9 |
| Java 17 | Chọn bản version 17 nếu archive có entry tương ứng |
| Java mới hơn | Tiếp tục fallback về version cao nhất có sẵn không vượt runtime |

Java 8 chỉ kiểm tra khả năng tương thích classpath và các class nền. Các test ModuleFinder, ModuleDescriptor và module path phải chạy trên JDK 9 trở lên.

## 9. Những lỗi thường gặp

- **Quên Multi-Release: true:** các entry trong META-INF/versions không được xử lý như phiên bản thay thế.
- **Đặt sai đường dẫn module descriptor:** dùng META-INF/versions/9/module-info.class; không lồng module-info trong một thư mục con khác.
- **Nghĩ rằng JAR tự thành module chỉ vì có thư mục versions/9:** phải có module-info.class hợp lệ và manifest bật multi-release.
- **Biên dịch class versioned bằng target quá mới:** class file trong versions/N phải tương thích với major version N.
- **Thay đổi API public giữa các release:** giữ API công khai nhất quán theo quy tắc MR-JAR.
- **Thay đổi module descriptor tùy ý:** các descriptor versioned phải giống nhau, chỉ có ngoại lệ cụ thể cho requires không transitive của java.*/jdk.* và uses.
- **Đặt service configuration trong META-INF/versions:** các resource dưới META-INF như META-INF/services không được version hóa theo cơ chế này. Với named module, khai báo uses/provides trong module descriptor.
- **Chỉ kiểm tra trên JDK mới:** có thể bỏ sót lỗi tương thích của phần class nền. Chạy kiểm thử trên cả runtime cũ nhất mà thư viện cam kết hỗ trợ.
- **Đặt modular JAR trên classpath rồi kỳ vọng nó là named module:** module descriptor chỉ có ý nghĩa khi JAR được dùng trên module path; trên classpath nó hoạt động như JAR không modular.

## 10. Ghi nhớ

Multi-release JAR dùng manifest Multi-Release: true và các thư mục META-INF/versions/N để cung cấp class/resource theo từng major version. Module descriptor có thể nằm ở root hoặc trực tiếp trong một thư mục versioned, ví dụ META-INF/versions/9/module-info.class. Nhờ đó, một JAR có thể giữ class nền tương thích Java 8 và được nhận diện là explicit module trên Java 9 trở lên.

Khi phát hành, hãy kiểm tra manifest, đường dẫn module-info, descriptor bằng ModuleFinder, và class/resource thực tế được chọn bằng JarFile. Chạy test trên các JDK mục tiêu để xác nhận cả khả năng tương thích ngược lẫn hành vi modular ở runtime mới.

## Tài liệu tham khảo

- JAR File Specification — Multi-release JAR và Modular multi-release JAR: https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html
- The jar Command — tùy chọn --release, --describe-module và --validate: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html
