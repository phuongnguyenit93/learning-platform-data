# Multi-release JAR trong Java

Multi-release JAR (MR-JAR) là định dạng JAR cho phép một thư viện hoặc ứng dụng đóng gói nhiều phiên bản của cùng một class hoặc resource để JVM chọn nội dung phù hợp với phiên bản Java đang chạy. Nhờ đó, một artifact có thể giữ implementation nền tương thích với Java cũ, đồng thời cung cấp implementation tận dụng API mới trên Java 9, 11, 17 hoặc các release mới hơn.

Cơ chế này được giới thiệu từ Java 9 cùng Java Platform Module System. Một MR-JAR vẫn là file JAR thông thường, nhưng có thêm các thư mục phiên bản bên dưới META-INF/versions và một manifest attribute bắt buộc:

~~~text
Multi-Release: true
~~~

Ví dụ một JAR có thể chứa:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/RuntimeInfo.class
│       └── 17/
│           └── com/example/RuntimeInfo.class
└── com/
    └── example/
        └── RuntimeInfo.class
~~~

JVM Java 8 dùng class ở thư mục gốc. JVM Java 11 chọn bản trong META-INF/versions/9. JVM Java 17 hoặc mới hơn chọn bản trong META-INF/versions/17 nếu có; nếu không có, nó dùng phiên bản cao nhất không vượt quá runtime hiện tại. Điều kiện quan trọng là manifest phải khai báo Multi-Release: true.

## 1. Cấu trúc và quy tắc chọn phiên bản

Một MR-JAR có hai loại nội dung:

- **Base entries:** class và resource nằm ở gốc JAR như một JAR truyền thống. Đây là nội dung nền dành cho runtime cũ và làm fallback khi không có phiên bản phù hợp.
- **Versioned entries:** nội dung nằm dưới META-INF/versions/N/, trong đó N là số release Java từ 9 trở lên.

Ví dụ class có tên đầy đủ com.example.RuntimeInfo có đường dẫn base:

~~~text
com/example/RuntimeInfo.class
~~~

Bản dành cho Java 9 nằm tại:

~~~text
META-INF/versions/9/com/example/RuntimeInfo.class
~~~

Bản dành cho Java 17 nằm tại:

~~~text
META-INF/versions/17/com/example/RuntimeInfo.class
~~~

Khi class loader tìm class trong MR-JAR, runtime thực hiện lựa chọn theo feature version của Java đang chạy:

1. Xác định phiên bản Java hiện tại.
2. Tìm versioned entry có số phiên bản lớn nhất nhưng không vượt quá phiên bản runtime.
3. Nếu tìm thấy, dùng entry đó.
4. Nếu không có versioned entry phù hợp, dùng entry ở gốc JAR.

Ví dụ:

| Runtime | Entry được chọn |
|---|---|
| Java 8 | Base entry ở gốc JAR |
| Java 9 | META-INF/versions/9 |
| Java 11 | META-INF/versions/9 nếu chưa có bản 11 |
| Java 17 | META-INF/versions/17 nếu có; nếu không, bản 9 |
| Java 21 | Bản 21 nếu có; nếu không, bản cao nhất không vượt 21 |

Các thư mục version không phải một cơ chế classpath độc lập. JVM nhận diện chúng như một phần của cùng JAR khi manifest bật multi-release. Nếu thiếu attribute hoặc attribute không có giá trị true, runtime xử lý JAR theo cách thông thường và bỏ qua các bản trong META-INF/versions.

Tên thư mục version phải là số release hợp lệ từ 9 trở lên. Không dùng tên tùy ý như latest, java17 hoặc current.

## 2. Manifest Multi-Release

Một JAR chỉ hoạt động theo quy tắc multi-release khi manifest chính có attribute:

~~~text
Multi-Release: true
~~~

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Multi-Release: true

~~~

Dòng trống cuối manifest kết thúc phần main attributes. Attribute Multi-Release phải nằm trong phần chính của manifest; không đặt nó trong section dành riêng cho một entry.

Tên attribute trong manifest không phân biệt hoa thường theo quy tắc manifest, nhưng nên dùng chính tả chuẩn Multi-Release để dễ đọc và tương thích công cụ.

Nếu dùng jar tool với tùy chọn --release để tạo versioned entries, hãy kiểm tra manifest đầu ra để bảo đảm Multi-Release: true được thiết lập. Trong ví dụ thực hành bên dưới, manifest được tạo tường minh để kết quả dễ kiểm soát.

Có thể xem manifest bên trong JAR bằng:

~~~bash
jar --extract --file build/mr-demo.jar META-INF/MANIFEST.MF
~~~

Sau đó đọc file META-INF/MANIFEST.MF. Có thể dùng jar --list để xác nhận manifest và các entry versioned đã được đóng gói.

## 3. Vì sao cần Multi-release JAR?

Một thư viện có thể muốn hỗ trợ nhiều phiên bản Java nhưng vẫn tận dụng API mới khi runtime hỗ trợ.

Ví dụ, implementation nền có thể dùng API tiêu chuẩn cũ:

~~~java
public final class RuntimeInfo {
    public static String message() {
        return "Base implementation";
    }
}
~~~

Implementation Java 9+ có thể dùng API mới hơn, chẳng hạn API của ProcessHandle:

~~~java
public final class RuntimeInfo {
    public static String message() {
        return "Process id: " + ProcessHandle.current().pid();
    }
}
~~~

Nếu đưa class dùng ProcessHandle vào root JAR, Java 8 không thể nạp class đó vì API không tồn tại trong Java 8. MR-JAR cho phép giữ class nền tương thích trong root và đặt implementation mới dưới META-INF/versions/9.

Những trường hợp sử dụng thường gặp:

- Dùng API JDK mới trong implementation mà vẫn giữ baseline Java cũ.
- Tối ưu implementation theo runtime, ví dụ dùng API hoặc thuật toán mới hơn.
- Cung cấp implementation riêng cho một release có thay đổi hiệu năng hoặc hành vi.
- Đóng gói module descriptor cho Java 9+ trong khi vẫn giữ khả năng sử dụng như JAR trên classpath cũ.
- Thay thế resource hoặc implementation nội bộ theo phiên bản Java.

MR-JAR hữu ích nhất cho thư viện có cùng API công khai qua nhiều runtime. Ứng dụng triển khai trên một phiên bản Java cố định thường không cần nhiều bản class trong cùng artifact.

## 4. Quy tắc tương thích giữa các phiên bản

Các bản class của cùng một kiểu nên giữ API công khai tương thích nhị phân. Một chương trình được biên dịch dựa trên base class phải có thể liên kết với implementation được runtime chọn.

Ví dụ, nếu base version cung cấp:

~~~java
public static String message()
~~~

thì bản trong META-INF/versions/9 nên tiếp tục cung cấp method có cùng tên, modifier phù hợp, kiểu trả về và descriptor tương thích. Nếu versioned class loại bỏ method hoặc thay đổi descriptor, chương trình đã compile có thể gặp NoSuchMethodError, IllegalAccessError hoặc lỗi liên kết khác khi chạy trên runtime mới.

Có thể thay đổi phần implementation bên trong mà vẫn giữ API:

- Dùng API JDK mới hơn trong thân method.
- Thay đổi thuật toán nội bộ.
- Tối ưu cách lưu trữ hoặc xử lý.
- Gọi implementation helper chỉ tồn tại trong versioned tree nếu helper đó không bị code nền tham chiếu.

Không nên giả định mọi class trong các thư mục version được thay thế theo cùng một cách nếu cấu trúc package hoặc dependency không nhất quán. Hãy xác định rõ class nào là điểm thay thế và class nào chỉ tồn tại trên runtime mới.

Nếu chỉ thêm một class mới vào versioned tree mà không có ở base, class đó chỉ có thể được sử dụng trên runtime có versioned entry tương ứng. Mã nguồn hoặc bytecode nền không được phụ thuộc vào class chỉ có ở phiên bản mới hơn nếu cần chạy trên Java cũ.

## 5. Biên dịch base và versioned class

Cách tổ chức thường dùng là tách source theo release:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/
│   └── java9/
│       └── java/
└── build/
    ├── base/
    └── java9/
~~~

Base source được biên dịch bằng release thấp nhất mà thư viện hỗ trợ. Source cho Java 9 được biên dịch với --release 9 và classpath chứa base output nếu cần tham chiếu API chung.

Ví dụ:

~~~bash
javac --release 8 -d build/base src/main/java/com/example/RuntimeInfo.java
javac --release 9 -cp build/base -d build/java9 src/java9/java/com/example/RuntimeInfo.java
~~~

Tùy chọn --release kiểm soát ngôn ngữ, API nền tảng và class file target cho release được chỉ định. Điều này giúp tránh vô tình dùng API mới trong base implementation.

Không dùng -source 8 -target 8 như lựa chọn mặc định cho build mới nếu có thể dùng --release. Chỉ định source/target riêng không tự giới hạn API JDK mà mã nguồn được phép gọi.

Nếu base target là Java 8, versioned implementation dành cho Java 9 phải được compile với API Java 9 trở lên. Một versioned class ở META-INF/versions/17 nên được compile với --release 17 hoặc môi trường tương ứng, không được đặt class file có version cao hơn vào thư mục version thấp hơn.

Mỗi versioned source thường giữ cùng package và binary name với class nền mà nó thay thế. Điều này giúp runtime chọn một implementation theo cùng tên class mà code gọi đã biên dịch.

## 6. Đóng gói bằng jar --release

JDK jar tool hỗ trợ tùy chọn --release VERSION khi tạo hoặc cập nhật MR-JAR. Tùy chọn này đặt các file tiếp theo vào thư mục META-INF/versions/VERSION trong archive.

Cú pháp minh họa:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/java9 .
~~~

Trong ví dụ này:

- Nội dung từ build/base được đưa vào gốc JAR.
- Các file sau --release 9 được đặt dưới META-INF/versions/9.
- Cây thư mục package được giữ nguyên bên trong từng vùng.

Có thể thêm nhiều release:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/java9 . \
    --release 17 -C build/java17 .
~~~

Khi đóng gói nhiều release, mỗi thư mục output cần chứa đúng các class/resource dành cho release tương ứng. Không đưa toàn bộ source tree hoặc thư mục build vào archive một cách tùy tiện.

Nếu tự tạo JAR bằng zip tool hoặc công cụ đóng gói khác, phải tự bảo đảm cấu trúc META-INF/versions/N và manifest Multi-Release: true đúng chuẩn. Dùng jar tool giảm rủi ro sai vị trí entry.

## 7. Ví dụ hoàn chỉnh: một JAR chạy trên Java 8 và Java 9+

Ví dụ này tạo một chương trình có base implementation tương thích Java 8 và implementation khác cho Java 9 trở lên. Cả hai đều cung cấp cùng method message().

Cấu trúc project:

~~~text
mr-demo/
├── src/
│   ├── base/
│   │   └── com/example/runtime/
│   │       ├── Main.java
│   │       └── RuntimeInfo.java
│   └── java9/
│       └── com/example/runtime/
│           └── RuntimeInfo.java
└── build/
~~~

### Bước 1: base implementation

Tạo src/base/com/example/runtime/RuntimeInfo.java:

~~~java
package com.example.runtime;

public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static String message() {
        return "Base implementation";
    }
}
~~~

Class này chỉ dùng cú pháp và API có trong Java 8.

Tạo src/base/com/example/runtime/Main.java:

~~~java
package com.example.runtime;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(RuntimeInfo.message());
    }
}
~~~

Main chỉ gọi API chung có trong base class. Vì vậy cùng một Main.class có thể chạy với RuntimeInfo.class được chọn từ root hoặc từ versioned directory.

### Bước 2: implementation cho Java 9+

Tạo src/java9/com/example/runtime/RuntimeInfo.java:

~~~java
package com.example.runtime;

public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static String message() {
        long pid = ProcessHandle.current().pid();
        return "Java 9+ implementation, pid=" + pid;
    }
}
~~~

ProcessHandle được thêm từ Java 9. Nếu class này nằm ở root, Java 8 không thể nạp nó. Đặt nó trong source riêng và đóng gói dưới META-INF/versions/9 để Java 8 tiếp tục dùng base implementation.

### Bước 3: biên dịch hai phiên bản

Từ thư mục gốc mr-demo, tạo output directories:

~~~bash
mkdir -p build/base build/java9
~~~

Biên dịch base cho Java 8:

~~~bash
javac --release 8 -d build/base \
    src/base/com/example/runtime/RuntimeInfo.java \
    src/base/com/example/runtime/Main.java
~~~

Biên dịch implementation Java 9:

~~~bash
javac --release 9 -cp build/base -d build/java9 \
    src/java9/com/example/runtime/RuntimeInfo.java
~~~

Bước này tạo:

~~~text
build/
├── base/
│   └── com/example/runtime/
│       ├── Main.class
│       └── RuntimeInfo.class
└── java9/
    └── com/example/runtime/
        └── RuntimeInfo.class
~~~

### Bước 4: tạo manifest

Tạo file build/manifest.mf:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.runtime.Main
Multi-Release: true

~~~

Manifest phải có dòng trống cuối cùng. Multi-Release: true bật quy tắc chọn versioned entries. Main-Class cho phép chạy JAR bằng java -jar.

### Bước 5: đóng gói MR-JAR

Tạo archive:

~~~bash
jar --create --file build/mr-demo.jar \
    --manifest build/manifest.mf \
    -C build/base . \
    --release 9 -C build/java9 .
~~~

Nội dung archive cần có:

~~~text
META-INF/MANIFEST.MF
com/example/runtime/Main.class
com/example/runtime/RuntimeInfo.class
META-INF/versions/9/com/example/runtime/RuntimeInfo.class
~~~

Base RuntimeInfo.class nằm ở gốc. Bản Java 9 nằm dưới META-INF/versions/9.

### Bước 6: kiểm tra cấu trúc JAR

Liệt kê archive:

~~~bash
jar --list --file build/mr-demo.jar
~~~

Xác nhận có cả hai entry:

~~~text
com/example/runtime/RuntimeInfo.class
META-INF/versions/9/com/example/runtime/RuntimeInfo.class
~~~

Đọc manifest:

~~~bash
jar --extract --file build/mr-demo.jar META-INF/MANIFEST.MF
~~~

Kiểm tra file manifest có Multi-Release: true.

JDK mới cũng cung cấp chế độ kiểm tra MR-JAR:

~~~bash
jar --validate --file build/mr-demo.jar
~~~

Lệnh này hỗ trợ kiểm tra tính hợp lệ của nội dung multi-release theo quy tắc mà jar tool biết. Nó không thay thế việc chạy thử trên từng runtime mục tiêu.

### Bước 7: chạy trên runtime

Trên Java 8:

~~~bash
java -jar build/mr-demo.jar
~~~

Output:

~~~text
Base implementation
~~~

Java 8 không áp dụng quy tắc multi-release nên dùng class ở gốc JAR.

Trên Java 9 trở lên:

~~~bash
java -jar build/mr-demo.jar
~~~

Output có dạng:

~~~text
Java 9+ implementation, pid=12345
~~~

Giá trị PID thay đổi theo tiến trình thực tế. Trên Java 17 hoặc Java 21, runtime vẫn chọn version 9 nếu JAR không có bản versioned cao hơn phù hợp.

Đây là cùng một file JAR. Sự khác biệt đến từ việc runtime chọn entry nào khi nạp class com.example.runtime.RuntimeInfo.

## 8. Kiểm tra từng phiên bản bằng javap

Có thể dùng javap để xem class mà MR-JAR cung cấp theo một release cụ thể.

Xem base version:

~~~bash
javap --multi-release base -classpath build/mr-demo.jar -c com.example.runtime.RuntimeInfo
~~~

Xem phiên bản 9:

~~~bash
javap --multi-release 9 -classpath build/mr-demo.jar -c com.example.runtime.RuntimeInfo
~~~

Tùy chọn --multi-release cho phép chọn góc nhìn base hoặc một release cụ thể khi đọc class từ multi-release archive. Dùng -c để xem bytecode và xác nhận implementation nào được chọn.

Nếu muốn xem descriptor hoặc flags chi tiết:

~~~bash
javap --multi-release 9 -classpath build/mr-demo.jar -v com.example.runtime.RuntimeInfo
~~~

Đừng dùng javap trên một class file đã được giải nén rồi kết luận đó là phiên bản runtime sẽ nạp. Hãy chỉ định --multi-release khi mục tiêu là kiểm tra cách javap chọn entry từ MR-JAR.

## 9. Multi-release JAR và module-info.class

MR-JAR có thể cung cấp module descriptor cho Java 9+ mà vẫn giữ nội dung class dùng được trên Java 8. Một cách phổ biến là đặt module-info.class dưới:

~~~text
META-INF/versions/9/module-info.class
~~~

JVM Java 8 không hiểu JPMS nên bỏ qua descriptor trong thư mục versioned và vẫn dùng các class ở gốc JAR như một thư viện thông thường.

JVM Java 9+ có thể đọc descriptor versioned để coi JAR là named module khi đặt trên module path. Descriptor cần mô tả đúng tên module, requires, exports, opens, uses và provides.

Có thể kiểm tra module descriptor trong archive bằng:

~~~bash
javap --multi-release 9 -v -classpath build/library.jar module-info
~~~

Hoặc dùng:

~~~bash
jar --describe-module --file build/library.jar
~~~

Lệnh jar --describe-module đưa ra bản mô tả module dễ đọc. Javap cho phép kiểm tra class file và Module attribute chi tiết hơn.

Nếu một module descriptor chỉ có ở version 9, JAR vẫn có thể hoạt động như JAR thông thường trên Java 8. Đây là một lợi ích quan trọng khi thư viện muốn hỗ trợ classpath cũ và module path mới.

## 10. Versioned resources

MR-JAR cũng có thể chứa resource theo phiên bản, không chỉ class file. Ví dụ một resource có thể nằm ở:

~~~text
config/defaults.properties
META-INF/versions/11/config/defaults.properties
~~~

Khi truy cập resource thông qua cơ chế JAR/class loader có hỗ trợ multi-release, runtime có thể chọn bản phù hợp theo phiên bản. Điều này hữu ích khi nội dung resource phụ thuộc runtime hoặc khi cần thay đổi cấu hình mặc định theo API nền tảng.

Không nên nhầm versioned resource với một file cấu hình riêng mà ứng dụng tự chọn bằng cách kiểm tra java.version. Nếu muốn JVM tự áp dụng quy tắc MR-JAR, resource phải nằm đúng vị trí và manifest phải bật Multi-Release.

Hãy kiểm thử cách thư viện đọc resource trên runtime mục tiêu, đặc biệt nếu dùng API resource tùy chỉnh, framework hoặc công cụ đóng gói có cách xử lý JAR riêng.

## 11. Tổ chức source và build trong dự án thực tế

Một dự án có thể tổ chức source theo baseline và các release:

~~~text
library/
├── src/
│   ├── main/
│   │   └── java/
│   ├── java9/
│   │   └── java/
│   └── java17/
│       └── java/
├── build/
│   ├── classes/
│   │   ├── base/
│   │   ├── java9/
│   │   └── java17/
│   └── libs/
└── build.gradle
~~~

Build pipeline cần:

1. Biên dịch source nền với release thấp nhất được hỗ trợ.
2. Biên dịch từng source set versioned bằng release tương ứng.
3. Đặt class output vào thư mục riêng.
4. Kiểm tra binary name và API giữa các bản thay thế.
5. Tạo manifest có Multi-Release: true.
6. Đóng gói base entries và versioned entries vào cùng archive.
7. Kiểm tra danh sách entry và manifest.
8. Chạy test trên từng JDK mục tiêu.

### Gradle

Gradle Java plugin có thể dùng source set riêng hoặc cấu hình task compile riêng cho từng release. Một cấu hình thực tế cần đảm bảo output của source set Java 9 được đặt vào versioned path khi đóng gói.

Mô hình khái niệm:

~~~groovy
tasks.jar {
    manifest {
        attributes("Multi-Release": "true")
    }

    into("META-INF/versions/9") {
        from(sourceSets.java9.output)
    }
}
~~~

Đây là phần đóng gói minh họa. Dự án cần định nghĩa sourceSets.java9 và task biên dịch tương ứng, đặt release 9 và dependency classpath phù hợp. Nếu dùng convention plugin hoặc plugin MR-JAR chuyên dụng, kiểm tra cấu hình của đúng phiên bản plugin.

### Maven

Với Maven, có thể cấu hình compiler executions hoặc profile riêng cho base và từng release, sau đó dùng jar plugin để đưa output versioned vào META-INF/versions/N. Cấu hình chính xác phụ thuộc phiên bản Maven Compiler Plugin và Jar Plugin.

Không nên chỉ đổi maven.compiler.release một lần cho toàn dự án nếu cần nhiều implementation. Mỗi source set cần được compile với target release riêng và đóng gói vào đúng thư mục versioned.

Dù dùng Gradle, Maven hay script javac/jar, kết quả cuối cùng phải tuân theo cùng cấu trúc JAR và manifest attribute.

## 12. Những giới hạn và lỗi thường gặp

### Thiếu Multi-Release: true

Nếu manifest không có attribute này, JVM không chọn các entry dưới META-INF/versions. Nó sẽ dùng class ở gốc như một JAR thông thường.

Kiểm tra manifest thực tế thay vì chỉ xem file manifest đầu vào. Một số build task có thể ghi đè hoặc hợp nhất manifest theo cách không mong muốn.

### Đặt sai thư mục versioned

Đường dẫn phải có dạng:

~~~text
META-INF/versions/9/com/example/RuntimeInfo.class
~~~

Các đường dẫn như versions/9, META-INF/version/9 hoặc META-INF/versions/java17 không hợp lệ theo quy ước MR-JAR.

### Dùng class file mới trong thư mục release thấp

Một class được đặt dưới META-INF/versions/9 phải tương thích với release 9. Nếu biên dịch bằng JDK mới mà không giới hạn release, class file có thể yêu cầu JVM mới hơn và gây UnsupportedClassVersionError khi runtime chọn nó trên Java 9 hoặc 11.

Dùng javac --release N cho từng source set và kiểm tra major version của class file.

### Versioned implementation không giữ API tương thích

Nếu class nền có method mà versioned class không có, code đã compile có thể lỗi liên kết trên runtime mới. Giữ descriptor và contract công khai tương thích, rồi chỉ thay đổi implementation bên trong.

### Quên compile dependency chung

Versioned source thường cần tham chiếu class nền hoặc annotation/interface dùng chung. Đặt base output vào classpath khi compile versioned source.

### Đóng gói sai cấp thư mục

Khi tạo JAR, dùng -C để đưa nội dung của output directory vào archive. Nếu đưa cả thư mục build/java9 thay vì nội dung bên trong, entry có thể bị lồng thêm một cấp và JVM không tìm đúng đường dẫn versioned.

### Nghĩ Java 8 đọc được implementation mới

Java 8 không áp dụng MR-JAR. Nó dùng base entries. Vì vậy, mọi class được code nền tham chiếu phải có trong root JAR và tương thích Java 8.

### Chỉ test trên một JDK

Một MR-JAR được thiết kế để hoạt động trên nhiều runtime. Test trên một JDK không chứng minh base version chạy trên Java cũ hoặc versioned implementation hoạt động trên Java mới. Cần kiểm thử matrix theo baseline và từng release có source override.

### Sửa JAR sau khi ký

Nếu JAR đã được ký, thay đổi nội dung hoặc manifest có thể làm chữ ký không còn hợp lệ. Hãy hoàn tất việc tạo base/versioned entries và manifest trước khi ký artifact cuối cùng.

## 13. Kiểm thử và chẩn đoán MR-JAR

Một checklist hữu ích:

- Xác nhận manifest có Multi-Release: true trong main section.
- Xác nhận base class nằm ở root JAR.
- Xác nhận versioned class nằm dưới META-INF/versions/N.
- Xác nhận N từ 9 trở lên.
- Kiểm tra class file version phù hợp release của thư mục.
- Dùng javap --multi-release base và javap --multi-release N để so sánh.
- Chạy trên baseline Java cũ để xác nhận base implementation.
- Chạy trên từng runtime mới để xác nhận versioned implementation.
- Kiểm tra API và binary compatibility giữa các phiên bản.
- Dùng jar --validate khi phù hợp với JDK đang dùng.
- Kiểm tra manifest và danh sách archive sau khi build.
- Chạy test cho resource loading và module path nếu JAR cung cấp những nội dung đó.

Khi gặp lỗi, xác định trước runtime đã chọn entry nào. Nếu class không được thay thế, kiểm tra manifest và đường dẫn. Nếu gặp UnsupportedClassVersionError, kiểm tra release dùng để biên dịch class. Nếu gặp NoSuchMethodError hoặc AbstractMethodError, so sánh API giữa base và versioned class.

Không chỉ kiểm tra source tree. Hãy kiểm tra JAR thực tế được phát hành vì lỗi thường nằm ở bước đóng gói, manifest merge hoặc output directory.

## 14. Khi nào nên dùng Multi-release JAR?

Nên cân nhắc MR-JAR khi:

- Thư viện cần giữ một baseline Java cũ nhưng muốn tận dụng API mới.
- Có implementation thay thế rõ ràng theo release.
- Có thể duy trì cùng contract công khai giữa các phiên bản.
- Build pipeline có thể compile và test từng source set.
- Artifact cần phân phối dưới một tên và một phiên bản duy nhất.

Không nên dùng chỉ để đóng gói nhiều bản sao của class mà không có lý do runtime cụ thể. Mỗi versioned source làm tăng độ phức tạp build, kiểm thử, debug và phát hành. Nếu chỉ hỗ trợ một phiên bản Java, một implementation duy nhất thường dễ duy trì hơn.

Multi-release JAR giúp một artifact thích nghi với nhiều runtime bằng cách chọn class hoặc resource theo feature version. Để sử dụng đúng, cần có base implementation tương thích, versioned entries đúng đường dẫn, manifest Multi-Release: true, API nhất quán và kiểm thử trên các JDK mục tiêu.
