# Quy tắc cho lớp, tài nguyên và thư mục META-INF trong Multi-Release JAR

Multi-Release JAR (MR-JAR) cho phép một JAR cung cấp các phiên bản class hoặc resource khác nhau theo phiên bản Java đang chạy. JAR giữ một bản nền ở thư mục gốc và có thể đặt các bản thay thế trong những thư mục có số phiên bản dưới META-INF/versions.

Từ Java 9, JVM có thể chọn bản phù hợp nhất với runtime hiện tại. Ví dụ, runtime Java 17 sẽ ưu tiên nội dung trong META-INF/versions/17; nếu không có bản 17 cho một đường dẫn, runtime có thể dùng bản gần nhất thấp hơn nhưng không thấp hơn 9. Nếu không có bản thay thế phù hợp, runtime dùng nội dung ở thư mục gốc.

MR-JAR rất hữu ích khi thư viện cần hỗ trợ nhiều phiên bản Java nhưng vẫn muốn tận dụng API hoặc tối ưu triển khai mới trên runtime mới hơn. Tuy nhiên, quy tắc áp dụng cho class, resource và META-INF khác nhau. Đặc biệt, không thể version hóa tùy ý nội dung META-INF.

## 1. Cấu trúc của Multi-Release JAR

Một MR-JAR có cấu trúc khái quát:

~~~text
library.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/example/library/
│   ├── Api.class
│   └── messages.properties
└── META-INF/
    └── versions/
        ├── 9/
        │   └── module-info.class
        └── 17/
            └── com/example/library/
                ├── Api.class
                └── messages.properties
~~~

Các phần có ý nghĩa:

- Thư mục gốc chứa bản nền của class và resource.
- META-INF/versions/9 chứa các entry chỉ áp dụng từ Java 9 trở lên.
- META-INF/versions/17 chứa các entry chỉ áp dụng từ Java 17 trở lên.
- Manifest ở META-INF/MANIFEST.MF phải có thuộc tính Multi-Release: true trong main section để runtime kích hoạt cách tra cứu MR-JAR.
- module-info.class có quy tắc đặc biệt và có thể nằm trong META-INF/versions/9 hoặc thư mục phiên bản cao hơn.

Một JAR chỉ có thư mục META-INF/versions chưa chắc đã là MR-JAR. Nếu manifest không khai báo Multi-Release: true, runtime không áp dụng quy tắc chọn phiên bản cho các entry đó.

### 1.1. Cách runtime chọn entry

Với mỗi đường dẫn class hoặc resource, runtime chọn entry có số phiên bản lớn nhất nhưng không vượt quá phiên bản runtime.

Ví dụ JAR có các bản:

| Entry | Nội dung |
|---|---|
| Thư mục gốc | Bản nền |
| META-INF/versions/9 | Bản Java 9 |
| META-INF/versions/17 | Bản Java 17 |
| META-INF/versions/21 | Bản Java 21 |

Kết quả lựa chọn:

| Runtime | Entry được chọn |
|---|---|
| Java 9 | Bản trong versions/9 nếu có, nếu không dùng bản gốc |
| Java 11 | Bản trong versions/9 nếu có, nếu không dùng bản gốc |
| Java 17 | Bản trong versions/17 nếu có, nếu không dùng versions/9 hoặc bản gốc |
| Java 21 | Bản trong versions/21 nếu có, nếu không dùng phiên bản thấp hơn phù hợp |

Các thư mục phiên bản bắt đầu từ 9. Runtime không dùng entry của phiên bản cao hơn runtime đang chạy. Ví dụ Java 17 không chọn class trong versions/21.

Việc chọn phiên bản diễn ra theo từng đường dẫn entry. Một class có thể được chọn từ versions/17 trong khi một resource khác không có bản thay thế ở đó và vẫn được lấy từ thư mục gốc.

## 2. Quy tắc đối với class

### 2.1. Đặt class nền ở thư mục gốc

Class nền phải nằm ở đường dẫn package bình thường, ví dụ:

~~~text
com/example/library/Api.class
~~~

Đây là bản dùng khi runtime không có bản thay thế phù hợp. Class nền phải biên dịch với mức Java thấp nhất mà thư viện cam kết hỗ trợ.

Ví dụ, nếu thư viện có baseline Java 9:

~~~bash
javac --release 9 -d base-out src-base/com/example/library/Api.java
~~~

Tùy chọn --release giúp giới hạn cú pháp, bytecode và Java API theo phiên bản đích. Nó giúp tránh vô tình gọi API chỉ có ở JDK mới trong class nền.

### 2.2. Đặt class thay thế trong thư mục phiên bản

Nếu muốn tối ưu implementation cho Java 17, đặt class cùng tên đầy đủ và cùng đường dẫn package vào:

~~~text
META-INF/versions/17/com/example/library/Api.class
~~~

Biên dịch bản này bằng API của Java 17:

~~~bash
javac --release 17 -d version-17-out src-17/com/example/library/Api.java
~~~

Runtime Java 17 trở lên có thể chọn bản thay thế này. Runtime Java 9 đến Java 16 tiếp tục dùng class nền hoặc bản ở một thư mục phiên bản thấp hơn.

Tên class và package phải khớp với entry mà nó thay thế. Hãy giữ các chữ ký public/protected ổn định giữa các phiên bản để consumer có thể biên dịch một lần và chạy trên nhiều runtime.

### 2.3. Giữ API tương thích giữa các phiên bản

Một MR-JAR thường dùng các class khác nhau để thay đổi implementation, tận dụng API mới hoặc cải thiện hiệu năng. Consumer vẫn nên nhìn thấy cùng một API công khai.

Ví dụ, hai bản có thể thực hiện cùng phương thức:

~~~java
public static String selected() {
    return "base";
}
~~~

và:

~~~java
public static String selected() {
    return "java-17".strip();
}
~~~

Bản Java 17 dùng String.strip(), nhưng tên class, tên phương thức, kiểu trả về và mức truy cập vẫn tương thích với bản nền.

JDK cung cấp lệnh kiểm tra API giữa các phiên bản:

~~~bash
jar --validate --file library.jar
~~~

Lệnh này kiểm tra tính nhất quán của API được export trong MR-JAR giữa các phiên bản release. Nếu API công khai thay đổi không nhất quán, hãy xem cảnh báo/lỗi và sửa các bản class trước khi phát hành.

Lệnh validate không thay thế kiểm thử runtime. Nó không chứng minh mọi nhánh logic, resource, cấu hình hoặc dependency động đều hoạt động đúng.

### 2.4. Không biên dịch class phiên bản mới bằng API của JDK hiện tại một cách tùy tiện

Nếu bản trong versions/17 dùng API chỉ có từ Java 21, runtime Java 17 có thể chọn class đó nhưng không tìm thấy method tương ứng khi chạy.

Hãy biên dịch theo đúng phiên bản thư mục:

~~~bash
javac --release 17 -d version-17-out src-17/com/example/library/Api.java
javac --release 21 -d version-21-out src-21/com/example/library/Api.java
~~~

Mỗi thư mục phiên bản phải chứa bytecode có thể chạy trên phiên bản Java tương ứng trở lên. Đừng đặt class biên dịch bằng JDK 24 vào versions/17 nếu nó sử dụng API chỉ tồn tại từ Java 24.

## 3. Quy tắc đối với resource

MR-JAR không chỉ thay thế class. Resource cũng có thể có bản riêng theo phiên bản runtime, miễn là resource nằm ngoài vùng META-INF bị loại trừ khỏi cơ chế versioning.

Ví dụ:

~~~text
com/example/library/messages.properties
META-INF/versions/17/com/example/library/messages.properties
~~~

Khi runtime phù hợp, resource trong versions/17 thay thế resource gốc cùng đường dẫn. Nếu không có bản tương ứng trong thư mục phiên bản đang xét, runtime tiếp tục tìm bản thấp hơn hoặc bản gốc.

Các resource có thể version hóa gồm:

- File properties và ResourceBundle.
- Template, schema hoặc dữ liệu cấu hình có nội dung phụ thuộc phiên bản Java.
- Resource được đọc bằng Class.getResource hoặc ClassLoader.getResource.
- Metadata ứng dụng đặt trong package thông thường, miễn là không thuộc các entry META-INF bị loại khỏi versioning.

Không cần version hóa resource chỉ vì thư viện chạy trên nhiều Java. Chỉ tạo bản thay thế khi nội dung thực sự khác nhau theo runtime.

### 3.1. Tên và đường dẫn resource phải khớp

Nếu resource gốc là:

~~~text
com/example/library/messages.properties
~~~

thì bản thay thế Java 17 phải ở:

~~~text
META-INF/versions/17/com/example/library/messages.properties
~~~

Không đặt nó thành một tên khác rồi kỳ vọng runtime tự nhận diện. MR-JAR thay thế entry theo đường dẫn, không tự tìm resource gần giống hoặc tự ghép nội dung từ nhiều file.

### 3.2. Resource trong named module còn chịu quy tắc đóng gói JPMS

Nếu MR-JAR có module descriptor và được chạy trên module path, resource nằm trong package của named module còn chịu quy tắc đóng gói module.

Việc export package cho phép module khác truy cập các kiểu public theo quy tắc JPMS; nó không tự động mở resource nội bộ của package cho module khác. Nếu module consumer gọi trực tiếp Class.getResourceAsStream trên class thuộc module provider và resource nằm trong package chưa mở, lời gọi có thể trả về null.

Có hai cách thiết kế phù hợp:

- Để code trong module sở hữu resource tự đọc resource và cung cấp dữ liệu qua API công khai.
- Nếu thực sự cần cho module khác đọc resource trực tiếp, mở package theo phạm vi cần thiết bằng opens hoặc qualified opens.

Ví dụ API tự đọc resource trong module sở hữu:

~~~java
public static String resourceValue() throws IOException {
    Properties properties = new Properties();

    try (InputStream input =
            VersionInfo.class.getResourceAsStream("messages.properties")) {
        if (input == null) {
            throw new IllegalStateException("Resource not found");
        }
        properties.load(input);
    }

    return properties.getProperty("message");
}
~~~

Khi class VersionInfo được thay thế theo phiên bản Java, implementation mới vẫn có thể đọc resource cùng đường dẫn trong phiên bản tương ứng. Consumer chỉ gọi phương thức công khai resourceValue().

## 4. Quy tắc đặc biệt cho thư mục META-INF

Đây là phần dễ nhầm nhất khi tạo MR-JAR.

**Không version hóa tùy ý thư mục META-INF hoặc nội dung của nó.** Các entry như manifest, service configuration và signature metadata không được thay thế theo cơ chế versioned resource thông thường.

Ví dụ, không dùng:

~~~text
META-INF/versions/17/META-INF/services/com.example.spi.Plugin
META-INF/versions/17/META-INF/MANIFEST.MF
META-INF/versions/17/META-INF/EXAMPLE.SF
~~~

Các entry META-INF được đặt dưới META-INF/versions/<N>/META-INF không được runtime sử dụng như bản thay thế versioned. Kiểm thử trên JDK 24 cho thấy ClassLoader vẫn đọc file service descriptor ở META-INF/services tại thư mục gốc, bỏ qua bản đặt dưới META-INF/versions/9/META-INF/services.

### 4.1. Manifest phải nằm ở vị trí gốc

Manifest luôn nằm tại:

~~~text
META-INF/MANIFEST.MF
~~~

Trong main section của manifest phải có:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Thuộc tính Multi-Release: true kích hoạt cơ chế MR-JAR. Khi tạo JAR bằng jar --release, công cụ jar hiện hành tự thêm thuộc tính này. Nếu đóng gói bằng ZIP tool hoặc build tool khác, phải xác nhận manifest cuối cùng có thuộc tính đó.

Không đặt manifest thay thế trong META-INF/versions/17. Runtime đọc manifest gốc để xác định JAR có phải multi-release hay không.

### 4.2. META-INF/services không được version hóa

ServiceLoader sử dụng các file service configuration theo đường dẫn:

~~~text
META-INF/services/com.example.spi.Plugin
~~~

File này phải ở thư mục META-INF/services gốc. Một bản nằm dưới META-INF/versions/17/META-INF/services không thay thế file gốc khi ServiceLoader tìm provider.

Nếu implementation provider cần khác nhau theo Java version, có thể giữ tên provider trong service descriptor gốc rồi version hóa class provider ở package bình thường:

~~~text
META-INF/services/com.example.spi.Plugin
com.example.plugin.DefaultPlugin

META-INF/versions/17/com/example/plugin/DefaultPlugin.class
~~~

Service descriptor vẫn trỏ tới cùng tên class. Runtime chọn implementation class phù hợp theo MR-JAR. Nếu danh sách provider thực sự phải khác nhau theo runtime, hãy thiết kế cơ chế lựa chọn provider trong code hoặc cấu hình ứng dụng thay vì version hóa file META-INF/services.

### 4.3. Signature metadata cũng nằm ở META-INF gốc

Các file chữ ký JAR thường nằm trong META-INF, ví dụ:

- File .SF.
- File chữ ký .RSA, .DSA hoặc .EC.
- File có tên bắt đầu bằng SIG-.

Không đặt bản thay thế của các file này dưới META-INF/versions. Chữ ký phải tương ứng với nội dung archive cuối cùng. Hãy hoàn thiện mọi versioned entry trước khi ký JAR; thay đổi archive sau khi ký có thể làm chữ ký không còn hợp lệ.

### 4.4. Ngoại lệ: module-info.class

module-info.class là trường hợp đặc biệt có thể đặt trong thư mục phiên bản:

~~~text
META-INF/versions/9/module-info.class
~~~

Điều này cho phép một JAR có class nền tương thích với classpath nhưng chỉ trở thành named module khi chạy trên module path của Java 9 trở lên.

Ví dụ:

- Runtime/module system Java 9 trở lên có thể nhận module descriptor trong versions/9.
- Khi JAR được đặt trên classpath, module descriptor không tạo ranh giới named module cho lần chạy đó.
- Các class và resource vẫn tuân theo cơ chế multi-release nếu manifest bật Multi-Release: true.

Có thể kiểm tra descriptor ở phiên bản cụ thể:

~~~bash
jar --describe-module --file library.jar --release 9
~~~

Nếu JAR chỉ có module descriptor trong thư mục phiên bản mà không có module-info.class ở root, jar --describe-module cần biết release muốn xem. Với modular MR-JAR, giữ module name và API module nhất quán giữa các release mà dự án hỗ trợ.

## 5. Ví dụ hoàn chỉnh: MR modular JAR với class và resource theo Java 17

Ví dụ tạo một thư viện có:

- Bản nền biên dịch với Java 9.
- Module descriptor trong META-INF/versions/9.
- Class và resource thay thế trong META-INF/versions/17.
- Một ứng dụng consumer chạy được trên cả classpath và module path.

### 5.1. Cấu trúc nguồn

~~~text
project/
├── base-src/
│   └── com.example.mr/
│       ├── module-info.java
│       └── com/example/mr/
│           ├── VersionInfo.java
│           └── message.properties
├── v17-src/
│   └── com/example/mr/
│       ├── VersionInfo.java
│       └── message.properties
├── app-src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/
│           └── Main.java
├── base-out/
├── v17-out/
├── app-out/
├── mr.jar
└── app.jar
~~~

### 5.2. Module descriptor và class nền

File base-src/com.example.mr/module-info.java:

~~~java
module com.example.mr {
    exports com.example.mr;
}
~~~

File base-src/com.example.mr/com/example/mr/VersionInfo.java:

~~~java
package com.example.mr;

import java.io.InputStream;
import java.util.Properties;

public final class VersionInfo {
    private VersionInfo() {
    }

    public static String selected() {
        return "base";
    }

    public static String resourceValue() throws Exception {
        Properties properties = new Properties();

        try (InputStream input =
                VersionInfo.class.getResourceAsStream("message.properties")) {
            if (input == null) {
                throw new IllegalStateException("missing message.properties");
            }
            properties.load(input);
        }

        return properties.getProperty("value");
    }
}
~~~

File base-src/com.example.mr/com/example/mr/message.properties:

~~~properties
value=base-resource
~~~

### 5.3. Class và resource thay thế cho Java 17

File v17-src/com/example/mr/VersionInfo.java:

~~~java
package com.example.mr;

import java.io.InputStream;
import java.util.Properties;

public final class VersionInfo {
    private VersionInfo() {
    }

    public static String selected() {
        return "java-17".strip();
    }

    public static String resourceValue() throws Exception {
        Properties properties = new Properties();

        try (InputStream input =
                VersionInfo.class.getResourceAsStream("message.properties")) {
            if (input == null) {
                throw new IllegalStateException("missing message.properties");
            }
            properties.load(input);
        }

        return properties.getProperty("value");
    }
}
~~~

File v17-src/com/example/mr/message.properties:

~~~properties
value=java-17-resource
~~~

Hai phiên bản VersionInfo có cùng public API. Bản Java 17 sử dụng String.strip(), còn bản nền không cần API đó. Resource message.properties cũng có cùng đường dẫn, nhưng nội dung thay đổi theo phiên bản.

### 5.4. Biên dịch bản nền và bản Java 17

Từ thư mục project, tạo thư mục output:

~~~bash
mkdir -p base-out v17-out app-out
~~~

Biên dịch module nền bằng Java 9:

~~~bash
javac --release 9 -d base-out --module-source-path base-src -m com.example.mr
~~~

Copy resource vào module output:

~~~bash
cp base-src/com.example.mr/com/example/mr/message.properties \
   base-out/com.example.mr/com/example/mr/
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force base-out, v17-out, app-out | Out-Null
javac --release 9 -d base-out --module-source-path base-src -m com.example.mr
Copy-Item -Path base-src/com.example.mr/com/example/mr/message.properties -Destination base-out/com.example.mr/com/example/mr/
~~~

Biên dịch bản thay thế Java 17:

~~~bash
javac --release 17 -d v17-out v17-src/com/example/mr/VersionInfo.java
cp v17-src/com/example/mr/message.properties v17-out/com/example/mr/
~~~

Trên Windows PowerShell:

~~~powershell
javac --release 17 -d v17-out v17-src/com/example/mr/VersionInfo.java
Copy-Item -Path v17-src/com/example/mr/message.properties -Destination v17-out/com/example/mr/
~~~

### 5.5. Tạo MR-JAR

Tạo JAR với ba nhóm entry:

1. Bản nền ở root.
2. module-info.class ở versions/9.
3. Class và resource Java 17 ở versions/17.

Lệnh:

~~~bash
jar --create --file mr.jar \
    -C base-out/com.example.mr com \
    --release 9 -C base-out/com.example.mr module-info.class \
    --release 17 -C v17-out com
~~~

Trên Windows PowerShell, có thể chạy cùng lệnh trên một dòng:

~~~powershell
jar --create --file mr.jar -C base-out/com.example.mr com --release 9 -C base-out/com.example.mr module-info.class --release 17 -C v17-out com
~~~

jar --release đặt các entry theo sau vào thư mục META-INF/versions/<N>. Khi tạo archive theo cách này, jar tự thêm Multi-Release: true vào manifest.

Kiểm tra danh sách entry:

~~~bash
jar --list --file mr.jar
~~~

Các entry quan trọng phải có dạng:

~~~text
META-INF/MANIFEST.MF
com/example/mr/VersionInfo.class
com/example/mr/message.properties
META-INF/versions/9/module-info.class
META-INF/versions/17/com/example/mr/VersionInfo.class
META-INF/versions/17/com/example/mr/message.properties
~~~

Kiểm tra manifest:

~~~bash
jar --extract --file mr.jar META-INF/MANIFEST.MF
~~~

Mở META-INF/MANIFEST.MF và xác nhận có Multi-Release: true.

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file mr.jar --release 9
~~~

Kiểm tra API nhất quán:

~~~bash
jar --validate --file mr.jar
~~~

Lệnh validate thành công thường không in thông báo và trả exit code 0.

### 5.6. Tạo ứng dụng consumer

File app-src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.mr;
}
~~~

File app-src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.mr.VersionInfo;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(VersionInfo.selected());
        System.out.println(VersionInfo.resourceValue());
    }
}
~~~

Biên dịch consumer với MR-JAR trên module path:

~~~bash
javac --release 9 -d app-out --module-source-path app-src \
      --module-path mr.jar -m com.example.app
~~~

Đóng gói ứng dụng:

~~~bash
jar --create --file app.jar -C app-out/com.example.app .
~~~

### 5.7. Chạy trên module path và classpath

Trên Windows PowerShell, chạy module path:

~~~powershell
java --module-path "mr.jar;app.jar" -m com.example.app/com.example.app.Main
~~~

Trên Linux hoặc macOS, dùng dấu hai chấm:

~~~bash
java --module-path "mr.jar:app.jar" -m com.example.app/com.example.app.Main
~~~

Kết quả trên OpenJDK 24.0.2:

~~~text
java-17
java-17-resource
~~~

Có thể chạy cùng hai JAR trên classpath:

~~~powershell
java -cp "app.jar;mr.jar" com.example.app.Main
~~~

Trên Linux hoặc macOS:

~~~bash
java -cp "app.jar:mr.jar" com.example.app.Main
~~~

Kết quả trên OpenJDK 24.0.2 cũng là:

~~~text
java-17
java-17-resource
~~~

Kết quả cho thấy:

- Cả classpath và module path đều áp dụng chọn class/resource theo Multi-Release: true.
- Trên module path, module descriptor trong versions/9 được nhận diện và consumer đọc module com.example.mr.
- Trên classpath, module descriptor không tạo named module cho lần chạy đó.
- Runtime 24 chọn class và resource trong versions/17.
- Nếu chạy trên Java 9 đến Java 16, bản nền được dùng cho hai entry vì JAR không có bản thay thế trong các release đó.

## 6. Quy tắc khi dùng ServiceLoader và resource trong META-INF

Nếu thư viện sử dụng ServiceLoader, service descriptor phải ở META-INF/services tại root. Không đặt bản khác trong META-INF/versions/<N>/META-INF/services.

Ví dụ:

~~~text
META-INF/services/com.example.spi.Plugin
com.example.plugin.DefaultPlugin
~~~

Class provider có thể có implementation khác nhau theo phiên bản:

~~~text
com/example/plugin/DefaultPlugin.class
META-INF/versions/17/com/example/plugin/DefaultPlugin.class
~~~

Khi ServiceLoader đọc descriptor gốc, nó tìm class provider theo tên đã khai báo. Class loader có thể chọn bản DefaultPlugin phù hợp với runtime theo cơ chế MR-JAR.

Điều này giúp thay đổi implementation mà không phải thay service descriptor. Nếu cần thay đổi tập provider theo phiên bản, hãy cân nhắc để một provider điều phối việc lựa chọn hoặc dùng cấu hình ở tầng ứng dụng.

Các resource khác của ứng dụng như file properties đặt trong package bình thường vẫn có thể version hóa. Chỉ cần tránh đặt chúng trong vùng META-INF vốn không được áp dụng versioned lookup.

## 7. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Runtime luôn dùng bản nền | Manifest thiếu Multi-Release: true hoặc entry đặt sai đường dẫn | Kiểm tra manifest và META-INF/versions/<N> |
| Java 17 không dùng class trong versions/17 | Tên file/package không khớp hoặc thư mục version không hợp lệ | Kiểm tra đường dẫn entry và số release |
| Java 17 chọn class biên dịch bằng API quá mới | Class được biên dịch với JDK mới hơn release của thư mục | Biên dịch bằng javac --release đúng phiên bản |
| Class nền chạy nhưng class versioned gây NoSuchMethodError | API public giữa các phiên bản không tương thích hoặc dependency không phù hợp | Giữ chữ ký API nhất quán và chạy jar --validate |
| Resource vẫn lấy bản gốc | Resource versioned không cùng đường dẫn với bản nền | Đặt cùng đường dẫn dưới META-INF/versions/<N> |
| ServiceLoader không đọc bản service descriptor versioned | META-INF/services không được version hóa | Giữ service descriptor ở root; version hóa provider class nếu cần |
| Resource trong named module trả về null | Package chứa resource chưa mở cho module gọi | Đọc resource qua API của module sở hữu hoặc dùng opens có phạm vi phù hợp |
| jar --describe-module báo không có root descriptor | Module descriptor chỉ nằm trong versions/<N> | Dùng jar --describe-module --release <N> |
| jar --validate báo API không nhất quán | Public/protected API giữa các bản release không đồng bộ | Sửa các bản class và chạy validate lại |
| Thay đổi JAR sau khi ký làm xác minh chữ ký thất bại | Nội dung archive đã thay đổi sau khi tạo signature | Tạo archive hoàn chỉnh rồi ký lại |

## 8. Quy trình kiểm tra MR-JAR trước khi phát hành

1. Xác định baseline Java và các runtime bổ sung cần hỗ trợ.
2. Đặt class/resource nền ở thư mục gốc.
3. Tạo các bản thay thế chỉ khi cần implementation hoặc resource riêng cho release mới.
4. Biên dịch từng bản bằng javac --release tương ứng với số thư mục phiên bản.
5. Kiểm tra class có cùng tên đầy đủ và resource có cùng đường dẫn với entry nền.
6. Đảm bảo manifest gốc có Multi-Release: true.
7. Kiểm tra META-INF: manifest, services và signature metadata vẫn ở root; chỉ module-info.class dùng ngoại lệ versioned.
8. Chạy jar --list để kiểm tra cấu trúc archive.
9. Chạy jar --describe-module --release N nếu module descriptor nằm trong thư mục phiên bản.
10. Chạy jar --validate để kiểm tra API giữa các release.
11. Chạy thử trên runtime thấp nhất và cao nhất mà thư viện hỗ trợ.
12. Kiểm tra cả classpath và module path nếu JAR cần hỗ trợ hai cách triển khai.
13. Kiểm thử resource, ServiceLoader, reflection và các dependency động trên runtime image thực tế.
14. Chỉ ký JAR sau khi hoàn tất mọi entry và kiểm tra.

## 9. Checklist

- [ ] Manifest gốc có Multi-Release: true.
- [ ] Class nền nằm ở package path bình thường.
- [ ] Versioned class nằm dưới META-INF/versions/<N> với N từ 9 trở lên.
- [ ] Versioned class được biên dịch bằng javac --release đúng release.
- [ ] Public/protected API nhất quán giữa các bản.
- [ ] Resource versioned có cùng đường dẫn với resource nền.
- [ ] Resource cần truy cập trong named module tuân thủ quy tắc đóng gói JPMS.
- [ ] META-INF/services vẫn nằm ở root.
- [ ] Manifest và signature metadata không bị version hóa.
- [ ] module-info.class chỉ dùng vị trí versioned theo quy tắc đặc biệt khi cần.
- [ ] jar --describe-module cho thấy descriptor mong muốn.
- [ ] jar --validate thành công.
- [ ] JAR chạy đúng trên các runtime được hỗ trợ.
- [ ] JAR được ký sau khi đã hoàn tất nội dung cuối cùng.

## 10. Tài liệu tham khảo

- [JAR File Specification — Multi-Release JAR Files](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html#multi-release-jar-files): quy tắc manifest, versioned entries và cách runtime lựa chọn.
- [Java SE 26 — jar command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): tạo, cập nhật, kiểm tra và mô tả JAR; tùy chọn --release và --validate.
- [Java SE 26 API — JarFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html): đọc JAR và truy cập phiên bản runtime của archive.
- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238): mục tiêu thiết kế và cơ chế Multi-Release JAR.
- [Java SE 26 API — Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): quy tắc truy cập và đóng gói resource trong named module.
