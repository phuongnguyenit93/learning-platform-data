# Cấu trúc JAR: lớp, tài nguyên và thư mục `META-INF`

JAR (Java Archive) là định dạng đóng gói dựa trên ZIP, dùng để phân phối các lớp Java, tài nguyên và metadata liên quan trong một file. Một JAR có thể là thư viện được project khác sử dụng, một ứng dụng có lớp chính để khởi chạy, hoặc một gói chứa module và các biến thể class theo phiên bản Java.

Để hiểu một JAR, cần nhìn vào các entry bên trong archive. Đường dẫn của một file `.class` thể hiện package và tên lớp; resource được lưu theo đường dẫn mà code dùng để tìm; còn `META-INF/` chứa manifest cùng nhiều metadata tiêu chuẩn hoặc theo quy ước của nền tảng. Build tool tạo cấu trúc này từ class output, resource output và cấu hình đóng gói.

Bài này trình bày cấu trúc JAR từ bên trong, vai trò của từng nhóm file, cách JVM và ứng dụng tìm lớp/tài nguyên, các thành phần quan trọng trong `META-INF/`, cũng như cách tạo và kiểm tra JAR bằng JDK, Maven và Gradle.

## 1. JAR là một ZIP archive có quy ước dành cho Java

Về mặt lưu trữ, JAR sử dụng định dạng ZIP. Vì vậy, có thể xem nội dung JAR bằng công cụ `jar`, `unzip` hoặc phần mềm đọc ZIP. Điểm làm JAR khác một file ZIP thông thường là các quy ước và metadata mà công cụ Java hiểu, chẳng hạn:

- Các file `.class` được đặt theo đường dẫn package.
- Resource được đặt ở đường dẫn mà ứng dụng hoặc framework mong đợi.
- `META-INF/MANIFEST.MF` có thể khai báo lớp chính, class path hoặc thông tin khác.
- `META-INF/services/` có thể đăng ký implementation cho `ServiceLoader`.
- `module-info.class` có thể xác định JAR là một explicit named module.
- `META-INF/versions/` có thể chứa implementation riêng cho từng phiên bản Java trong multi-release JAR.
- Metadata chữ ký có thể xác minh nội dung archive theo quy trình ký JAR.

Một JAR không bắt buộc phải chứa tất cả những thành phần trên. JAR thư viện đơn giản có thể chỉ có `.class` và resource. `META-INF/` thường xuất hiện trong JAR được build bằng công cụ Java, nhưng nội dung bên trong phụ thuộc mục đích của artifact.

Ví dụ một JAR thư viện:

```text
customer-model.jar
├── com/
│   └── example/
│       └── customer/
│           ├── Customer.class
│           ├── Customer$Builder.class
│           ├── CustomerMapper.class
│           └── messages.properties
└── META-INF/
    ├── MANIFEST.MF
    └── services/
        └── com.example.spi.CustomerProvider
```

Đây là ví dụ minh họa. Một JAR thực tế có thể có thêm package, resource, module descriptor, file chữ ký hoặc metadata do build plugin tạo.

## 2. Cách đọc đường dẫn bên trong JAR

JAR lưu các entry theo đường dẫn tương đối bên trong archive. Các đường dẫn package thường dùng dấu `/`, không dùng dấu `.` như tên package trong mã nguồn Java.

Ví dụ mã nguồn:

```java
package com.example.customer;

public class CustomerService {
}
```

Sau khi biên dịch, class file thường có đường dẫn:

```text
com/example/customer/CustomerService.class
```

Tên đầy đủ của lớp (binary name) là:

```text
com.example.customer.CustomerService
```

JVM dùng tên lớp và classloader để tìm entry tương ứng trong classpath/module path. Package path là cách tổ chức file trong archive; tên package trong source code vẫn dùng dấu chấm.

### 2.1. Lớp lồng nhau, lớp ẩn danh và các file class liên quan

Một khai báo Java có thể tạo ra nhiều file `.class`. Ví dụ:

```java
package com.example.customer;

public class Customer {
    static class Address {
    }

    public Runnable task() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("running");
            }
        };
    }
}
```

Compiler có thể tạo các entry như:

```text
com/example/customer/Customer.class
com/example/customer/Customer$Address.class
com/example/customer/Customer$1.class
```

Tên có ký tự `$` là quy ước tên binary của nested/anonymous class trong bytecode. Không nên xóa các file class phụ chỉ vì chúng không có file `.java` cùng tên. Chúng có thể cần thiết để lớp chính hoạt động.

### 2.2. `package-info.class` và `module-info.class`

Ngoài class thông thường, output có thể chứa:

- `package-info.class`: lưu annotation hoặc tài liệu gắn với package, tùy cách khai báo trong `package-info.java`.
- `module-info.class`: module descriptor đã biên dịch từ `module-info.java`, dùng bởi Java Platform Module System.

Hai file này có ý nghĩa khác nhau. `package-info.class` nằm trong package tương ứng; `module-info.class` của module thường nằm ở root của module artifact.

## 3. Resource trong JAR

Resource là file không phải bytecode mà ứng dụng cần đọc khi chạy hoặc khi khởi tạo framework. Ví dụ:

- File `.properties`, `.xml`, `.json` hoặc `.yaml`.
- Template HTML, email hoặc report.
- Ảnh, font, dữ liệu mẫu hoặc schema.
- File cấu hình logging.
- Metadata dùng để đăng ký plugin hoặc service provider.
- File dữ liệu được thư viện nạp bằng classloader.

Resource thường được copy vào JAR theo đường dẫn tương ứng với vị trí trong resource root. Ví dụ dự án Maven:

```text
src/main/resources/
├── application.properties
├── logback.xml
└── com/example/customer/
    └── messages.properties
```

Sau khi build, các entry có thể nằm tại:

```text
application.properties
logback.xml
com/example/customer/messages.properties
```

Các file trong `src/main/resources` được đặt tương đối với resource root, vì vậy `application.properties` nằm ở root của JAR, còn `messages.properties` nằm trong package path.

### 3.1. Đọc resource bằng classloader

Có thể dùng `ClassLoader.getResource` hoặc `Class.getResource` để tìm resource trong classpath/module theo cơ chế tương ứng.

Ví dụ dùng classloader:

```java
try (var input = CustomerService.class
        .getClassLoader()
        .getResourceAsStream("application.properties")) {

    if (input == null) {
        throw new IllegalStateException("Không tìm thấy application.properties");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
```

Đường dẫn truyền cho `ClassLoader.getResourceAsStream` không bắt đầu bằng `/`; nó được tính từ root của classpath. Với `Class.getResourceAsStream`, đường dẫn bắt đầu bằng `/` được tính từ root, còn đường dẫn không có `/` ở đầu được tính tương đối với package của class.

Ví dụ:

```java
// Tính từ root classpath
CustomerService.class.getResourceAsStream("/application.properties");

// Tính tương đối với package com.example.customer
CustomerService.class.getResourceAsStream("messages.properties");
```

Nếu resource có trong source tree nhưng không có trong JAR, hãy kiểm tra resource directory và cấu hình xử lý resource của build tool. Nếu resource nằm trong JAR nhưng code không tìm thấy, hãy kiểm tra chính xác đường dẫn, chữ hoa/chữ thường và API đang dùng.

### 3.2. Resource trùng tên trong nhiều JAR

Hai dependency có thể cùng chứa resource tên `application.properties`, `META-INF/services/...` hoặc một file cấu hình giống nhau. Khi đó kết quả tìm resource phụ thuộc classloader và thứ tự/chiến lược tìm kiếm của môi trường.

Không nên dựa vào việc một resource trùng tên “tình cờ” được chọn đúng trên máy developer. Với resource cần hợp nhất, ví dụ file service provider, phải dùng cơ chế merge phù hợp khi tạo fat JAR. Với cấu hình ứng dụng, nên dùng tên/đường dẫn có namespace rõ ràng hoặc quy tắc nạp xác định.

## 4. `META-INF/` là gì?

`META-INF/` là thư mục metadata ở root của JAR. Nó chứa manifest và nhiều loại metadata khác mà Java platform, thư viện hoặc công cụ build có thể đọc.

Một cấu trúc ví dụ:

```text
META-INF/
├── MANIFEST.MF
├── services/
│   └── com.example.spi.CustomerProvider
├── versions/
│   └── 17/
│       └── com/example/ModernCustomer.class
├── maven/
│   └── com.example/
│       └── customer-model/
│           ├── pom.xml
│           └── pom.properties
├── LICENSE
└── NOTICE
```

Các mục trong ví dụ không bắt buộc phải cùng xuất hiện. `META-INF/maven/...` thường do Maven packaging tạo để giữ metadata tọa độ/POM của artifact; `LICENSE` và `NOTICE` phụ thuộc chính sách phát hành; `versions/` chỉ có ý nghĩa đặc biệt khi JAR được đánh dấu multi-release trong manifest.

Không nên xem mọi file dưới `META-INF/` là metadata được JVM tự động thực thi. Một số file có ý nghĩa chuẩn với Java platform; một số là quy ước của framework/plugin; một số chỉ là tài liệu hoặc metadata phục vụ repository và license.

## 5. `META-INF/MANIFEST.MF`

Manifest là file metadata chính của JAR, thường nằm ở:

```text
META-INF/MANIFEST.MF
```

Manifest chứa các thuộc tính dạng key-value. Ví dụ tối thiểu:

```text
Manifest-Version: 1.0
Created-By: 21.0.5 (Eclipse Adoptium)
```

Manifest có thể chỉ chứa `Manifest-Version` hoặc thêm các thuộc tính phục vụ launcher, module, instrumentation và công cụ khác. Không phải JAR nào cũng cần `Main-Class`.

### 5.1. `Main-Class`

Thuộc tính `Main-Class` chỉ định lớp có phương thức main mà Java launcher sẽ gọi khi chạy JAR bằng `java -jar`:

```text
Manifest-Version: 1.0
Main-Class: com.example.customer.Main
```

Lớp phải có entry point hợp lệ cho Java launcher, thường là:

```java
public static void main(String[] args)
```

Chạy:

```bash
java -jar customer-app.jar
```

`Main-Class` chỉ chỉ định điểm bắt đầu. Nó không tự động nhúng dependency vào JAR. Nếu ứng dụng cần thư viện bên ngoài, chúng phải được cung cấp qua manifest `Class-Path`, launcher, container hoặc một dạng executable archive có cơ chế nạp dependency riêng.

### 5.2. `Class-Path`

Thuộc tính `Class-Path` có thể liệt kê các URL/đường dẫn tương đối đến JAR hoặc thư mục bổ sung mà launcher dùng khi chạy executable JAR.

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.customer.Main
Class-Path: lib/customer-api.jar lib/jackson-databind.jar lib/jackson-core.jar
```

Các đường dẫn được phân tách bằng khoảng trắng và được diễn giải tương đối với vị trí JAR chứa manifest. Các file được tham chiếu phải được phân phối ở đúng vị trí. `Class-Path` không copy hoặc nhúng chúng vào archive.

Khi dùng `java -jar`, không thể kỳ vọng `-cp` trên dòng lệnh bổ sung classpath theo cách giống khi chạy tên lớp. Nếu cần nhiều thư viện ngoài, hãy dùng manifest, script launcher hoặc packaging plugin phù hợp.

### 5.3. `Automatic-Module-Name`

Một JAR chưa có `module-info.class` có thể được dùng như automatic module trên module path. Manifest có thể khai báo tên module ổn định bằng:

```text
Automatic-Module-Name: com.example.customer.model
```

Điều này giúp tên module không phải suy ra từ tên file JAR. Tên automatic module phải là tên module hợp lệ và không trùng module khác trong module graph.

`Automatic-Module-Name` không thay thế một `module-info.class` đầy đủ. Nó không khai báo chi tiết `requires`, `exports`, `opens` hoặc `uses/provides` như explicit module descriptor.

### 5.4. Thuộc tính liên quan đến Java agent

JAR có thể được dùng làm Java agent hoặc launcher agent nếu manifest khai báo thuộc tính phù hợp, chẳng hạn:

```text
Premain-Class: com.example.agent.MonitorAgent
```

`Premain-Class` chỉ định agent được nạp khi JVM khởi động với tùy chọn `-javaagent`. Có các thuộc tính agent khác cho những kiểu attach/launcher agent, ví dụ `Agent-Class` và `Launcher-Agent-Class`. Đây là trường hợp chuyên biệt; JAR ứng dụng thông thường không cần khai báo các thuộc tính này.

### 5.5. Manifest có thể có section theo entry

Manifest không chỉ có main section. Nó còn có thể có section riêng cho từng entry trong archive, được phân cách bằng dòng trống và bắt đầu bằng `Name:`.

Ví dụ rút gọn:

```text
Manifest-Version: 1.0
Created-By: 21

Name: com/example/customer/Customer.class
Sealed: true
```

Section theo entry có thể cung cấp thuộc tính áp dụng cho entry tương ứng, chẳng hạn thông tin sealing hoặc metadata liên quan đến chữ ký. Cách dùng cụ thể phụ thuộc manifest specification và công cụ tạo JAR.

### 5.6. Quy tắc định dạng manifest

Manifest là văn bản có cấu trúc, không phải file properties tùy ý. Mỗi thuộc tính có dạng `Name: Value`, section được phân cách bằng dòng trống. Dòng dài cần được wrap theo quy tắc manifest; dòng tiếp nối bắt đầu bằng một dấu cách. Tên thuộc tính và giá trị phải tuân theo giới hạn/cú pháp của manifest specification.

Không nên tự tạo manifest bằng cách nối chuỗi tùy tiện nếu nội dung có thể dài, chứa ký tự đặc biệt hoặc cần nhiều section. Dùng tùy chọn `jar --manifest` hoặc cơ chế manifest của Maven/Gradle giúp tránh lỗi định dạng.

## 6. `META-INF/services/` và Java Service Provider Interface

Java Service Provider Interface (SPI) cho phép một thư viện khai báo interface, còn các JAR khác cung cấp implementation. `ServiceLoader` tìm provider thông qua metadata service.

Ví dụ interface:

```java
package com.example.spi;

public interface CustomerProvider {
    String name();
}
```

Một JAR provider có implementation:

```java
package com.example.provider;

import com.example.spi.CustomerProvider;

public final class DefaultCustomerProvider implements CustomerProvider {
    @Override
    public String name() {
        return "default";
    }
}
```

Provider JAR tạo file:

```text
META-INF/services/com.example.spi.CustomerProvider
```

Nội dung:

```text
com.example.provider.DefaultCustomerProvider
```

Ứng dụng có thể tìm provider:

```java
ServiceLoader<CustomerProvider> providers =
        ServiceLoader.load(CustomerProvider.class);

for (CustomerProvider provider : providers) {
    System.out.println(provider.name());
}
```

Service configuration file dùng tên đầy đủ của service interface trong tên file và tên đầy đủ của provider implementation trong nội dung. Một file có thể liệt kê nhiều provider, mỗi provider trên một dòng; comment có thể được đặt theo cú pháp service configuration.

### 6.1. Vì sao `META-INF/services` quan trọng khi tạo fat JAR?

Nếu nhiều dependency có file service cùng tên, việc đóng gói đơn giản có thể khiến file sau ghi đè file trước. Kết quả là một số provider biến mất dù các class implementation vẫn nằm trong fat JAR.

Khi dùng Maven Shade Plugin hoặc Gradle Shadow Plugin, cần cấu hình service file transformer/merging tương ứng để kết hợp danh sách provider. Không nên chỉ kiểm tra rằng JAR chứa các class; phải kiểm tra metadata service có còn đầy đủ hay không.

### 6.2. SPI trong module system

Với explicit named module, service provider có thể được khai báo trong `module-info.java`:

```java
module com.example.customer.provider {
    requires com.example.customer.api;
    provides com.example.spi.CustomerProvider
        with com.example.provider.DefaultCustomerProvider;
}
```

Module sử dụng service có thể khai báo:

```java
module com.example.customer.app {
    requires com.example.customer.api;
    uses com.example.spi.CustomerProvider;
}
```

Trong named module, `uses` và `provides` mô tả service relationship trong module descriptor. Cách đăng ký này khác metadata file `META-INF/services` dùng cho classpath-based service loading, dù cả hai cùng phục vụ SPI.

## 7. `module-info.class` và cấu trúc JAR modular

Một explicit named module thường có `module-info.class` ở root của JAR:

```text
customer-api.jar
├── module-info.class
└── com/example/customer/api/
    ├── Customer.class
    └── CustomerRepository.class
```

`module-info.class` được biên dịch từ `module-info.java`. Nó mô tả tên module, các module cần đọc, package được export/open và service được sử dụng/cung cấp.

Ví dụ source descriptor:

```java
module com.example.customer.api {
    exports com.example.customer.api;
    requires java.logging;
}
```

Khi chạy trên module path, JVM resolve module graph theo các descriptor và quy tắc JPMS. Một JAR có `module-info.class` ở root là explicit module. Một JAR không có descriptor có thể được xem như automatic module khi đặt trên module path, tùy metadata và tên module được suy ra.

### 7.1. Kiểm tra module descriptor

Dùng:

```bash
jar --describe-module --file customer-api.jar
```

Lệnh này hiển thị thông tin module mà JAR cung cấp hoặc cách module được nhận diện. Nó hữu ích khi dependency hoạt động trên classpath nhưng không resolve được trên module path.

### 7.2. Module descriptor và `META-INF/`

Với JAR modular thông thường, `module-info.class` nằm ở root, không nằm trong `META-INF/`. Tuy nhiên, multi-release JAR có thể chứa module descriptor phiên bản hóa trong `META-INF/versions/<N>/module-info.class` để mô tả module phù hợp với phiên bản Java nhất định.

Đừng nhầm `META-INF/MANIFEST.MF` với `module-info.class`: manifest là metadata archive; module descriptor là bytecode đặc biệt được module system sử dụng để mô tả module.

## 8. Multi-release JAR: nhiều implementation trong một archive

Multi-release JAR cho phép một artifact chứa implementation khác nhau cho các phiên bản Java khác nhau. Cấu trúc thường có:

```text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── com/example/PlatformHelper.class
│       └── 17/
│           └── com/example/PlatformHelper.class
└── com/
    └── example/
        └── PlatformHelper.class
```

Manifest cần khai báo:

```text
Multi-Release: true
```

Entry ở root cung cấp implementation cơ sở. Khi JAR được nạp trên Java runtime hỗ trợ multi-release JAR, JVM có thể chọn entry trong `META-INF/versions/<N>/` phù hợp với phiên bản runtime đang chạy, theo quy tắc multi-release JAR.

Nếu thiếu `Multi-Release: true`, các entry dưới `META-INF/versions/` không được xử lý như phiên bản thay thế theo cơ chế multi-release thông thường.

Multi-release JAR hữu ích khi thư viện muốn dùng API mới trên JDK mới nhưng vẫn cung cấp implementation tương thích cho JDK cũ. Tuy nhiên, cần bảo đảm class cơ sở vẫn có thể chạy trên phiên bản thấp nhất được hỗ trợ và các entry versioned có cấu trúc/tên lớp phù hợp.

## 9. Chữ ký JAR và metadata bảo mật

JAR có thể được ký để người nhận kiểm tra nội dung archive và thông tin signer. Các file liên quan thường nằm dưới `META-INF/`, ví dụ:

```text
META-INF/
├── MANIFEST.MF
├── APP.SF
├── APP.RSA
└── ...
```

Tên file và định dạng cụ thể phụ thuộc công cụ/kỹ thuật ký. Thường gặp:

- File `.SF`: chứa digest/metadata chữ ký cho manifest và các section liên quan.
- File `.RSA`, `.DSA` hoặc `.EC`: chứa block chữ ký tương ứng với thuật toán/cơ chế được sử dụng.
- Manifest: có thể chứa digest của từng entry.

Có thể dùng `jarsigner` để ký và xác minh JAR:

```bash
# Ký JAR bằng keystore/alias đã cấu hình
jarsigner -keystore release-keystore.jks customer-app.jar release-key

# Xác minh chữ ký
jarsigner -verify -verbose -certs customer-app.jar
```

Ví dụ lệnh chỉ mang tính minh họa; việc ký thực tế cần keystore, private key, certificate chain và chính sách bảo vệ khóa phù hợp. Không đưa private key vào source repository hoặc build log.

Nếu thay đổi một entry sau khi ký, chữ ký có thể không còn hợp lệ. Khi tạo fat JAR, các file chữ ký từ dependency gốc thường không thể giữ nguyên như thể toàn bộ archive mới có cùng chữ ký. Packaging plugin thường cần loại bỏ signature metadata của dependency khi hợp nhất, sau đó tổ chức phát hành ký lại artifact cuối nếu quy trình yêu cầu.

Chữ ký JAR giúp kiểm tra tính toàn vẹn/nguồn gốc theo mô hình ký, nhưng không thay thế kiểm tra dependency, provenance, quyền phát hành hoặc đánh giá bảo mật của thư viện.

## 10. Metadata Maven thường thấy trong `META-INF/maven/`

JAR được tạo từ Maven có thể chứa metadata tọa độ và POM trong:

```text
META-INF/maven/<groupId>/<artifactId>/
├── pom.xml
└── pom.properties
```

Ví dụ `pom.properties`:

```properties
groupId=vn.acme.customer
artifactId=customer-model
version=1.4.0
```

Metadata này có thể hữu ích cho công cụ hoặc ứng dụng muốn đọc thông tin artifact từ JAR. Tuy nhiên, không phải mọi JAR đều có `META-INF/maven/`; sự hiện diện và vị trí phụ thuộc công cụ đóng gói. Tọa độ chính thức vẫn được quản lý bởi POM/repository metadata, không nên chỉ dựa vào một file properties trong JAR.

## 11. Những file khác có thể xuất hiện trong `META-INF/`

Tùy công cụ và mục đích phát hành, `META-INF/` có thể chứa:

| Entry | Vai trò |
|---|---|
| `MANIFEST.MF` | Metadata chính của JAR |
| `services/<service-interface>` | Danh sách provider cho `ServiceLoader` theo classpath convention |
| `versions/<N>/...` | Entry thay thế trong multi-release JAR |
| `maven/<group>/<artifact>/pom.xml` | POM được đóng gói kèm trong một số artifact Maven |
| `maven/<group>/<artifact>/pom.properties` | Tọa độ Maven ở dạng properties trong một số artifact |
| `*.SF` | Metadata digest/chữ ký |
| `*.RSA`, `*.DSA`, `*.EC` | Block chữ ký |
| `INDEX.LIST` | JAR index trong một số archive cũ/công cụ sử dụng |
| `LICENSE`, `NOTICE` | Thông tin giấy phép/thông báo được đóng gói theo chính sách dự án |
| `native-image/` hoặc metadata riêng | Tài nguyên/metadata do công cụ cụ thể định nghĩa |

Không phải tất cả entry trên là chuẩn bắt buộc của mọi JAR. Một số là quy ước của Java platform, một số là quy ước build tool/framework, và một số là tài liệu do nhà phát hành đưa vào.

## 12. Tạo JAR bằng công cụ `jar` của JDK

Giả sử các class đã được biên dịch vào `build/classes` và resource đã được copy vào cùng output tree.

### 12.1. Tạo JAR thường

```bash
jar --create --file customer-model.jar -C build/classes .
```

Ý nghĩa:

- `--create` tạo archive mới.
- `--file customer-model.jar` chỉ định tên file đầu ra.
- `-C build/classes .` chuyển vào thư mục output và thêm nội dung của thư mục đó vào JAR.

JAR tạo ra chứa các entry tương ứng với cấu trúc bên trong `build/classes`, ví dụ `com/example/customer/Customer.class` và resource nếu chúng đã được copy vào output tree.

### 12.2. Tạo executable JAR

Nếu có lớp chính `com.example.customer.Main`:

```bash
jar --create \
    --file customer-app.jar \
    --main-class com.example.customer.Main \
    -C build/classes .
```

Lệnh tạo manifest với `Main-Class` phù hợp để chạy:

```bash
java -jar customer-app.jar
```

JAR vẫn chỉ chứa nội dung đã đưa vào archive. Nếu dependency nằm ở thư mục khác, phải phân phối và cấu hình nó riêng hoặc dùng packaging tạo executable archive có dependency.

### 12.3. Tạo JAR với manifest riêng

Tạo file `manifest.mf`:

```text
Manifest-Version: 1.0
Main-Class: com.example.customer.Main
Class-Path: lib/customer-api.jar lib/logging.jar
```

Sau đó tạo JAR:

```bash
jar --create \
    --file customer-app.jar \
    --manifest manifest.mf \
    -C build/classes .
```

Manifest phải tuân theo định dạng; nên dùng file UTF-8/ASCII phù hợp và bảo đảm có dòng trống kết thúc section. `jar` sẽ thêm manifest vào `META-INF/MANIFEST.MF`.

### 12.4. Liệt kê, giải nén và cập nhật

```bash
# Liệt kê entry
jar --list --file customer-app.jar

# Giải nén vào thư mục hiện tại
jar --extract --file customer-app.jar

# Cập nhật/thêm entry vào archive hiện có
jar --update --file customer-app.jar -C extra-resources .
```

Khi cập nhật JAR đã ký, thay đổi nội dung có thể làm chữ ký không còn hợp lệ. Sau khi chỉnh archive, cần ký lại nếu artifact phải được phát hành dưới dạng signed JAR.

## 13. Maven: lớp, resource và cấu hình JAR Plugin

Maven Standard Directory Layout quy định các thư mục phổ biến:

```text
src/
├── main/
│   ├── java/       # source Java chính
│   └── resources/  # resource chính
└── test/
    ├── java/       # source test
    └── resources/  # resource test
```

Trong lifecycle thông thường:

1. `process-resources` copy/xử lý `src/main/resources` vào `target/classes`.
2. `compile` biên dịch `src/main/java` vào `target/classes`.
3. `package` dùng Maven JAR Plugin để đóng gói nội dung output chính thành JAR.

JAR thông thường không đóng gói `src/test/java`, `src/test/resources` hoặc các class test vào artifact production. Test output và report được quản lý trong các thư mục riêng.

### 13.1. Cấu hình resource trong POM

Maven mặc định copy resource từ `src/main/resources`. Có thể khai báo resource directory hoặc filter:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/filtered-resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>application.properties</include>
            </includes>
        </resource>
    </resources>
</build>
```

Filtering cho phép thay placeholder bằng project properties trong lúc build. Không nên filter tất cả file một cách tùy tiện: binary resource hoặc file có ký tự giống placeholder có thể bị thay đổi ngoài ý muốn. Không đưa secret môi trường vào resource đã đóng gói nếu artifact sẽ được chia sẻ rộng.

### 13.2. Cấu hình manifest với Maven JAR Plugin

Có thể cấu hình `Main-Class` qua Maven JAR Plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>com.example.customer.Main</mainClass>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Cấu hình này tạo manifest entry `Main-Class`. Nó không tự nhúng dependency vào JAR. Nếu ứng dụng cần dependency bên ngoài, phải dùng cơ chế phân phối classpath hoặc plugin đóng gói phù hợp.

### 13.3. Metadata POM bên trong JAR

Maven JAR Plugin có thể thêm metadata Maven vào `META-INF/maven/` theo cấu hình plugin. Nếu cần kiểm tra tọa độ trong archive, có thể liệt kê:

```bash
jar --list --file target/customer-model-1.4.0.jar
```

Tìm `META-INF/maven/.../pom.properties` hoặc `pom.xml` nếu plugin đã đưa chúng vào. Không nên dựa vào việc mọi artifact đều có các file này.

## 14. Gradle: lớp, resource và task `jar`

Gradle Java plugin sử dụng source set và task để tạo output:

```text
src/main/java/       -> compileJava       -> build/classes/java/main/
src/main/resources/  -> processResources  -> build/resources/main/
                                              |
                                              v
                                      classes output
                                              |
                                              v
                                            jar
                                              |
                                              v
                                    build/libs/project.jar
```

Task `jar` đóng gói output của source set chính, bao gồm class và resource được xử lý. Test source/resource không nằm trong JAR production thông thường.

### 14.1. Cấu hình manifest trong Gradle

Kotlin DSL:

```kotlin
tasks.jar {
    manifest {
        attributes[
            "Main-Class" to "com.example.customer.Main"
        ]
    }
}
```

Groovy DSL:

```groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.customer.Main'
        )
    }
}
```

Sau khi build, kiểm tra:

```bash
./gradlew clean jar
jar --list --file build/libs/project.jar
```

Có thể xem manifest bằng cách giải nén archive hoặc dùng công cụ ZIP. Nếu project có dependency runtime, plain `jar` task không tự nhúng tất cả dependency.

### 14.2. Thêm resource tùy chỉnh

Gradle mặc định lấy resource chính từ `src/main/resources`. Có thể cấu hình source set:

```kotlin
sourceSets {
    main {
        resources {
            srcDir("src/main/config")
            exclude("local-only/**")
        }
    }
}
```

Các resource phù hợp sẽ được xử lý bởi `processResources` và đưa vào JAR. Nếu cần filtering hoặc đổi tên resource, có thể cấu hình task `processResources` theo nhu cầu. Cần tránh đưa file cấu hình local hoặc secret vào artifact production.

## 15. Cấu trúc JAR thư viện, executable JAR và fat JAR

Ba khái niệm này thường bị nhầm:

| Loại JAR | Nội dung điển hình | Cách sử dụng |
|---|---|---|
| JAR thư viện | Class và resource mà thư viện cung cấp; có thể có metadata/module descriptor | Được thêm vào classpath/module path của ứng dụng khác |
| Executable JAR | Nội dung ứng dụng và manifest có `Main-Class` | Khởi chạy bằng `java -jar`; dependency ngoài cần được cung cấp riêng hoặc qua cơ chế đóng gói |
| Fat JAR/Uber JAR | Ứng dụng cùng dependency runtime được gom hoặc tổ chức trong archive | Dễ phân phối hơn; cách nạp phụ thuộc plugin/launcher tạo archive |

Một JAR có `Main-Class` không tự động trở thành fat JAR. `Main-Class` chỉ xác định entry point. Một fat JAR cũng có thể cần launcher đặc biệt nếu dependency được đặt trong các thư mục lồng bên trong thay vì root classpath thông thường.

Khi tạo fat JAR, cần xử lý các entry trùng tên:

- `META-INF/services/*` thường cần merge.
- Manifest cần được tạo lại phù hợp với artifact cuối.
- Signature metadata của JAR dependency thường phải loại bỏ vì nội dung archive mới đã thay đổi.
- License/NOTICE cần được tổng hợp theo yêu cầu phân phối.
- File module descriptor có thể cần xử lý đặc biệt khi nhiều module được gộp thành một archive.

Không nên giải nén và chép tất cả JAR vào một thư mục rồi zip lại mà không xử lý metadata. Cách làm đó có thể làm mất provider, phá chữ ký, ghi đè resource hoặc tạo archive không khởi chạy được.

## 16. Đọc và kiểm tra cấu trúc JAR

Khi nhận một JAR từ repository hoặc pipeline, hãy kiểm tra nội dung trước khi kết luận artifact thiếu hoặc sai.

### 16.1. Liệt kê entry

```bash
jar --list --file customer-app.jar
```

Tìm các mục quan trọng:

- `com/.../*.class`: bytecode của ứng dụng/thư viện.
- Resource ở root hoặc package path.
- `META-INF/MANIFEST.MF`.
- `META-INF/services/...` nếu có SPI.
- `module-info.class` nếu là explicit module.
- `META-INF/versions/...` nếu là multi-release JAR.
- Metadata Maven hoặc signature files nếu có.

### 16.2. Đọc manifest

Có thể giải nén riêng manifest bằng công cụ ZIP hoặc giải nén toàn bộ JAR:

```bash
jar --extract --file customer-app.jar META-INF/MANIFEST.MF
```

Sau đó đọc file `META-INF/MANIFEST.MF` bằng text editor. Kiểm tra `Main-Class`, `Class-Path`, `Automatic-Module-Name`, `Multi-Release` và các thuộc tính liên quan đến mục đích của artifact.

### 16.3. Xem thông tin module

```bash
jar --describe-module --file customer-app.jar
```

Nếu JAR không phải explicit module, công cụ có thể hiển thị tên automatic module hoặc thông tin tương ứng với cách nhận diện module.

### 16.4. Kiểm tra chữ ký

```bash
jarsigner -verify -verbose -certs customer-app.jar
```

Lệnh này giúp xác định chữ ký có hợp lệ theo nội dung archive hiện tại và thông tin certificate được cung cấp hay không. Việc xác minh certificate trust còn phụ thuộc trust store và chính sách kiểm tra của môi trường.

## 17. Các lỗi cấu trúc JAR thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `no main manifest attribute` | Manifest thiếu `Main-Class` | Mở `META-INF/MANIFEST.MF`, kiểm tra cấu hình JAR plugin |
| `Could not find or load main class` | Sai tên lớp, class không ở đúng package path hoặc JAR/classpath sai | Liệt kê archive, kiểm tra binary name và manifest |
| Resource trả về `null` | Resource không được đóng gói hoặc đường dẫn sai | Kiểm tra entry path và cách gọi `getResource` |
| `ServiceLoader` không tìm thấy provider | Thiếu `META-INF/services` hoặc provider không có trong module graph | Kiểm tra service file/module descriptor và fat JAR merge |
| JAR chạy được trên JDK mới nhưng không chạy trên JDK cũ | Bytecode/API mục tiêu không tương thích | Kiểm tra class version, `--release` và multi-release layout |
| `FindException` hoặc module resolution error | Module descriptor hoặc module path không phù hợp | Dùng `jar --describe-module`, kiểm tra `requires` và module path |
| `SecurityException: Invalid signature file digest` | Archive bị thay đổi sau khi ký hoặc signature metadata không phù hợp | Kiểm tra chữ ký, tạo lại archive và ký lại nếu cần |
| JAR thiếu class phụ | Chỉ copy một file `.class` mà bỏ nested/anonymous class hoặc output liên quan | Kiểm tra toàn bộ class output trước packaging |
| File cấu hình bị thay đổi nội dung | Resource filtering không phù hợp | Kiểm tra `processResources` hoặc Maven resource filtering |
| Provider mất sau khi tạo fat JAR | File service bị ghi đè thay vì merge | Cấu hình service transformer của packaging plugin |

## 18. Quy trình lần theo một file từ source đến JAR

Khi cần biết một lớp hoặc resource có được đóng gói hay không, có thể lần theo luồng sau:

```text
Source / resource input
          |
          v
Compile hoặc processResources
          |
          v
Output directory
  target/classes hoặc build/classes + resources
          |
          v
Packaging task (jar/war/shade/bootJar)
          |
          v
Archive entry path
          |
          v
JVM / classloader / framework đọc khi chạy
```

Với class, xác định package và binary name, rồi kiểm tra file `.class` trong output directory. Với resource, xác định resource root và đường dẫn được code dùng để nạp. Sau đó kiểm tra archive để biết entry có được đưa vào hay không.

Nếu file có trong output directory nhưng không có trong JAR, xem include/exclude và cấu hình packaging. Nếu file có trong JAR nhưng ứng dụng không tìm thấy, xem classpath/module path, classloader, tên resource và môi trường triển khai.

## 19. Quy tắc thực hành khi tổ chức JAR

- Để class file theo đúng package path và giữ nguyên các class phụ do compiler tạo.
- Đặt resource theo đường dẫn ổn định; tránh nhiều dependency có cùng tên resource nếu không có chiến lược hợp nhất.
- Chỉ thêm `Main-Class` khi JAR có entry point phù hợp.
- Không nhầm executable JAR với fat JAR; kiểm tra cách dependency được phân phối.
- Dùng `META-INF/services` đúng quy ước nếu thư viện cung cấp SPI và kiểm tra file này sau khi shade/merge.
- Dùng `module-info.class` khi dự án chủ động áp dụng JPMS; không đặt nhầm nó vào `META-INF/` ở JAR modular thông thường.
- Đặt `Multi-Release: true` chỉ khi archive thực sự có cấu trúc multi-release phù hợp.
- Không sửa nội dung JAR sau khi ký nếu chưa có kế hoạch ký lại.
- Không đóng gói secret, file local hoặc resource không dành cho môi trường production.
- Kiểm tra artifact cuối cùng bằng `jar --list`, đọc manifest và xác minh chữ ký/module khi cần.

## 20. Những điều cần ghi nhớ

- JAR là ZIP archive theo quy ước Java; bên trong chứa entry theo đường dẫn tương đối.
- Class file nằm theo package path, ví dụ `com/example/Main.class`; nested/anonymous class có thể tạo thêm file `.class` với ký tự `$`.
- Resource được copy từ resource root vào archive và được tìm qua classloader hoặc API `Class.getResource`.
- `META-INF/MANIFEST.MF` chứa metadata như `Main-Class`, `Class-Path`, `Automatic-Module-Name` và `Multi-Release`.
- `Main-Class` chỉ xác định entry point; nó không tự đóng gói dependency.
- `META-INF/services/` đăng ký provider cho SPI theo classpath convention; khi tạo fat JAR cần merge service files đúng cách.
- `module-info.class` ở root mô tả explicit module; multi-release module descriptor có thể nằm dưới `META-INF/versions/`.
- Multi-release JAR dùng `Multi-Release: true` và các entry `META-INF/versions/<N>/...` để cung cấp implementation theo Java version.
- Signature metadata dưới `META-INF/` cần được xử lý đúng nếu archive thay đổi sau khi ký.
- Maven và Gradle copy resource, compile class rồi dùng packaging task để tạo JAR; kiểm tra archive cuối là cách xác nhận nội dung thực tế.

Khi đọc hoặc tạo một JAR, hãy bắt đầu từ cấu trúc entry: lớp nằm ở package path nào, resource được đặt ở đâu và `META-INF/` khai báo điều gì. Từ đó có thể xác định JAR là thư viện, executable archive hay modular/multi-release artifact, hiểu JVM sẽ tìm lớp và tài nguyên như thế nào, đồng thời phát hiện sớm các lỗi do manifest, service metadata, module descriptor hoặc packaging configuration.
