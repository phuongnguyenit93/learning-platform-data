# Phân biệt module với package, JAR và project build

Khi học Java Platform Module System (JPMS), bốn khái niệm **package**, **JAR**, **project build** và **module** thường xuất hiện cùng lúc. Chúng có thể liên quan một-một trong một dự án đơn giản, nhưng không phải cùng một đối tượng và cũng không giải quyết cùng một vấn đề.

Hiểu ngắn gọn:

- **Package** tổ chức các kiểu Java thành những không gian tên và ranh giới truy cập ở mức ngôn ngữ.
- **JAR** là định dạng file đóng gói class, resource và metadata.
- **Project build** là đơn vị mà Maven, Gradle hoặc công cụ build quản lý để biên dịch, kiểm thử và phát hành artifact.
- **Java module** là đơn vị có tên trong JPMS, khai báo dependency và quyết định package nào được công khai ra bên ngoài.

Điều quan trọng là **ranh giới của bốn khái niệm không tự động trùng nhau**. Một Maven project có thể tạo một JAR, JAR ấy có thể chứa một Java module, và Java module có thể chứa nhiều package. Nhưng đó là một cách tổ chức thường gặp, không phải định nghĩa bắt buộc.

## 1. Package là gì?

Package là cách nhóm class, interface, enum, record và các kiểu Java khác vào một không gian tên.

Ví dụ:

~~~java
package com.example.catalog.api;

public interface ProductCatalog {
    String titleFor(String sku);
}
~~~

Tên đầy đủ của kiểu này là:

~~~text
com.example.catalog.api.ProductCatalog
~~~

Một package giúp:

- Tránh trùng tên class giữa các phần code.
- Tổ chức code theo tính năng hoặc trách nhiệm.
- Hỗ trợ quyền truy cập package-private trong ngôn ngữ Java.
- Tạo nền tảng để module export hoặc open một tập API.

Thông thường, cấu trúc source phản ánh package:

~~~text
src/main/java/
└── com/example/catalog/api/
    └── ProductCatalog.java
~~~

Tuy nhiên, package **không phải** file JAR, project build hay một Java module. Nhiều package có thể thuộc một module; trong môi trường classpath truyền thống, cùng một package có thể xuất hiện trong nhiều JAR.

Package có tên tương tự cũng không nhất thiết là cùng package. **com.example.catalog** và **com.example.catalog.internal** là hai package riêng biệt, dù một tên là tiền tố của tên kia.

## 2. JAR là gì?

JAR là viết tắt của **Java ARchive**. Về bản chất, nó là archive theo định dạng ZIP để đóng gói các file:

- **.class** đã biên dịch.
- Resource như properties, JSON, template hoặc ảnh.
- Metadata, đặc biệt là **META-INF/MANIFEST.MF**.
- Thông tin khác như service provider configuration.
- Với modular JAR, **module-info.class**.

Ví dụ:

~~~text
catalog-api.jar
├── META-INF/
│   └── MANIFEST.MF
├── module-info.class
├── com/example/catalog/api/ProductCatalog.class
└── com/example/catalog/internal/MemoryCatalog.class
~~~

Có thể xem nội dung bằng:

~~~bash
jar --list --file catalog-api.jar
~~~

JAR là **đơn vị đóng gói**, không phải tự nó luôn là một JPMS named module.

Cùng một JAR có thể được Java nhìn nhận khác nhau tùy vị trí và metadata:

- JAR có **module-info.class** hợp lệ và đặt trên module path: được nhận diện thành explicit named module.
- JAR không có descriptor nhưng đặt trên module path: có thể trở thành automatic module.
- JAR được nạp từ classpath: các class được định nghĩa trong unnamed module của class loader tương ứng.

Đặt một file tên **catalog.jar** trên module path không tự động làm Java module của nó có tên **catalog** nếu JAR có descriptor khai báo một tên khác.

## 3. Project build là gì?

Project build là đơn vị được Maven, Gradle hoặc một hệ thống build quản lý. Nó mô tả source set, dependency, compiler options, test, packaging và artifact đầu ra.

Trong Maven, một project thường có file **pom.xml**:

~~~text
catalog-api/
├── pom.xml
└── src/
    └── main/
        └── java/
~~~

Trong Gradle, project có thể được cấu hình bằng **build.gradle**, **build.gradle.kts** và các file settings:

~~~text
catalog-api/
├── build.gradle.kts
└── src/
    └── main/
        └── java/
~~~

Một project build có thể:

- Biên dịch source thành class.
- Resolve dependency từ repository hoặc project khác.
- Chạy unit test/integration test.
- Đóng gói JAR hoặc artifact khác.
- Xuất bản artifact với version và metadata.

Trong Maven, tên artifact và tọa độ thường có dạng:

~~~text
groupId    = com.example
artifactId = catalog-api
version    = 1.0.0
~~~

Những giá trị này dùng để nhận diện **artifact trong hệ sinh thái Maven**, không tự động trở thành tên Java module trong JPMS.

Maven còn có khái niệm **multi-module reactor**, nghĩa là một POM tổng điều phối nhiều project con. Đây là “module” theo cách gọi của Maven; không đồng nghĩa mỗi project con bắt buộc là một JPMS module.

## 4. Java module trong JPMS là gì?

Java module là một đơn vị cấu hình gồm tên module, các package mà module sở hữu và những quan hệ với module khác.

Một explicit named module thường có file **module-info.java**:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Descriptor có thể khai báo:

- **requires**: module khác mà module hiện tại cần đọc.
- **exports**: package được cho phép truy cập public API từ module khác.
- **opens**: package được mở cho deep reflection ở runtime.
- **uses**: service interface mà module sử dụng.
- **provides ... with ...**: provider cho service.

Ví dụ:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Module **com.example.catalog.app** đọc module **com.example.catalog.api**. Để app sử dụng **ProductCatalog**, module API còn phải export package chứa kiểu đó.

Do đó, JPMS không chỉ đặt tên nhóm class. Nó tạo ra **module graph**, giúp Java phân giải dependency và thực thi ranh giới truy cập giữa named modules.

## 5. Bảng so sánh bốn khái niệm

| Tiêu chí | Package | JAR | Project build | Java module |
|---|---|---|---|---|
| Bản chất | Namespace của kiểu Java | File archive | Đơn vị build và quản lý artifact | Đơn vị dependency/encapsulation của JPMS |
| Được định nghĩa bởi | Khai báo package | Cấu trúc file archive | POM, Gradle script, cấu hình build | Module descriptor hoặc quy tắc automatic module |
| Tên ví dụ | com.example.catalog.api | catalog-api-1.0.0.jar | Maven artifactId catalog-api | com.example.catalog.api |
| Chứa gì? | Kiểu thuộc package | Class, resource, metadata | Source, dependency, test, build tasks | Package, quan hệ đọc và chính sách export/open |
| Mục đích chính | Tổ chức kiểu và package access | Phân phối code | Tự động hóa build/test/release | Đóng gói mạnh và kiểm soát dependency |
| Có version riêng? | Không có cơ chế package version chuẩn trong ngôn ngữ | Có thể có tên/version metadata | Thường có version của artifact | Descriptor có thể mang version metadata; runtime resolution không vận hành như Maven dependency version |
| Quan hệ phụ thuộc | Không khai báo kiểu requires | Có thể có metadata tùy cơ chế | Maven/Gradle dependency | requires, requires transitive, requires static |
| Ranh giới công khai | public và package-private | Không tự tạo JPMS boundary | Không tự tạo JPMS boundary | exports, opens và readability |

Khi nghe một câu như “đưa module vào JAR”, cần hỏi đang nói đến **Java module** hay **Maven module**. Một modular JAR là một JAR được đóng gói dưới dạng module JPMS; nó vẫn chỉ là **một cách phân phối** module.

## 6. Quan hệ giữa module, package, JAR và project

Trong một dự án nhỏ, có thể sắp xếp:

~~~text
Maven project: catalog-api
       |
       | build
       v
JAR: catalog-api-1.0.0.jar
       |
       | chứa module-info.class
       v
Java module: com.example.catalog.api
       |
       +-- package com.example.catalog.api
       |
       +-- package com.example.catalog.internal
~~~

Trong ví dụ:

- Maven project chịu trách nhiệm build.
- JAR là kết quả đóng gói.
- module-info.class xác định JPMS module.
- Module sở hữu nhiều package.
- Có thể export package API mà giữ package internal không export.

Nhưng không phải tất cả module đều được phân phối dưới dạng JAR. Java cũng có **exploded module** (thư mục chứa module-info.class và các class), system module trong runtime image và các dạng packaging khác của công cụ JDK.

Vì vậy, mệnh đề “một module luôn bằng một JAR” là **không chính xác**.

## 7. Ví dụ hoàn chỉnh: hai Java module trong hai project

Giả sử muốn xây dựng ứng dụng catalog:

~~~text
workspace/
├── src/
│   ├── com.example.catalog.api/
│   │   ├── module-info.java
│   │   └── com/example/catalog/
│   │       ├── api/
│   │       │   ├── ProductCatalog.java
│   │       │   └── Catalogs.java
│   │       └── internal/
│   │           └── MemoryCatalog.java
│   └── com.example.catalog.app/
│       ├── module-info.java
│       └── com/example/catalog/app/
│           └── Main.java
├── out/
└── dist/
~~~

Đây là cấu trúc source minh họa theo **--module-source-path** của javac. Trong Maven/Gradle, có thể đặt mỗi module trong project riêng, với source nằm dưới **src/main/java** của project tương ứng.

### Module API: module-info.java

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Module export API package nhưng không export implementation package.

### Interface công khai

~~~java
package com.example.catalog.api;

public interface ProductCatalog {
    String titleFor(String sku);
}
~~~

### Implementation không export

~~~java
package com.example.catalog.internal;

import com.example.catalog.api.ProductCatalog;

public final class MemoryCatalog implements ProductCatalog {
    @Override
    public String titleFor(String sku) {
        return "Sản phẩm " + sku;
    }
}
~~~

Class **MemoryCatalog** là public để factory của cùng module có thể khởi tạo nó, nhưng package chứa class **không được export**. Một named module khác không thể import class này theo cách thông thường chỉ vì class được khai báo public.

### Factory thuộc API package

~~~java
package com.example.catalog.api;

import com.example.catalog.internal.MemoryCatalog;

public final class Catalogs {
    private Catalogs() {
    }

    public static ProductCatalog create() {
        return new MemoryCatalog();
    }
}
~~~

Các module tiêu thụ dùng interface **ProductCatalog** và factory **Catalogs**, không cần biết tên implementation.

### Module ứng dụng

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Main:

~~~java
package com.example.catalog.app;

import com.example.catalog.api.Catalogs;
import com.example.catalog.api.ProductCatalog;

public final class Main {
    public static void main(String[] args) {
        ProductCatalog catalog = Catalogs.create();
        System.out.println(catalog.titleFor("A-100"));
    }
}
~~~

Trong cấu trúc này, app không phụ thuộc trực tiếp vào package implementation. Nếu module API thay MemoryCatalog bằng implementation khác nhưng giữ hợp đồng API, code của app có thể không cần thay đổi.

## 8. Biên dịch các module mà không cần JAR

Ngay khi chưa đóng gói, hai module vẫn có thể được biên dịch thành **exploded modules**.

Từ thư mục workspace, chạy:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.catalog.api,com.example.catalog.app
~~~

Sau biên dịch:

~~~text
out/
├── com.example.catalog.api/
│   ├── module-info.class
│   └── com/example/catalog/...
└── com.example.catalog.app/
    ├── module-info.class
    └── com/example/catalog/app/Main.class
~~~

Chạy trực tiếp:

~~~bash
java --module-path out \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Ở đây, **out** chứa các exploded modules và được sử dụng như module path. Không cần tạo JAR trước để những module này được nhận diện.

Đây là một minh chứng rằng **Java module là khái niệm của JPMS, không phải đồng nghĩa với file JAR**.

## 9. Đóng gói module thành modular JAR

Sau khi compile, có thể đóng gói:

~~~bash
mkdir -p dist

jar --create \
    --file dist/com.example.catalog.api.jar \
    -C out/com.example.catalog.api .

jar --create \
    --file dist/com.example.catalog.app.jar \
    -C out/com.example.catalog.app .
~~~

Hai JAR chứa các class đã biên dịch và module-info.class tương ứng.

Chạy từ JAR:

~~~bash
java --module-path dist \
     --module com.example.catalog.app/com.example.catalog.app.Main
~~~

Ở thời điểm này:

- Project hoặc source code không còn cần thiết cho JVM.
- Hai modular JAR là phương tiện phân phối.
- Java module name vẫn đến từ **module-info.class**.
- Module graph vẫn được xây dựng dựa trên requires.
- Module API vẫn chỉ export package được khai báo.

Tên JAR ở đây được chọn cho dễ đọc; về nguyên tắc không bắt buộc trùng với module name.

## 10. Maven dependency và JPMS requires là hai quan hệ khác nhau

Nếu dùng Maven với hai project **catalog-api** và **catalog-app**, POM của app có thể khai báo dependency:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Maven dependency cho biết app cần artifact **catalog-api** để build.

Trong source Java của app:

~~~java
module com.example.catalog.app {
    requires com.example.catalog.api;
}
~~~

Directive **requires** cho biết named module app đọc named module API.

Hai khai báo cần nhất quán nhưng **không thay thế nhau**.

Nếu chỉ có Maven dependency mà không có requires phù hợp, javac có thể báo module app không đọc module API. Nếu chỉ có requires nhưng build không cung cấp artifact, compiler có thể báo **module not found**.

Tương tự, một Gradle dependency như **implementation(project(":catalog-api"))** xác định dependency của build, không tự biến nó thành directive requires trong module-info.java.

## 11. Vì sao Java module name không nhất thiết giống tên JAR?

Ví dụ file được phát hành tên:

~~~text
catalog-api-1.0.0.jar
~~~

Nhưng descriptor bên trong là:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Tên Java module là **com.example.catalog.api**; tên file JAR chỉ là tên artifact. Đổi tên file JAR không tự đổi tên module đã khai báo.

Có thể kiểm tra:

~~~bash
jar --describe-module --file catalog-api-1.0.0.jar
~~~

Lệnh này hữu ích khi đọc tài liệu build hoặc tích hợp thư viện bên thứ ba: đừng viết requires dựa trên giả định rằng artifactId chính là module name.

Đối với JAR không có descriptor nhưng được đặt trên module path, Java có thể suy ra tên automatic module theo quy tắc riêng hoặc sử dụng manifest **Automatic-Module-Name** nếu có. Đó là cơ chế khác với explicit named module.

## 12. Named, automatic và unnamed module

Ba trường hợp thường gặp:

| Trường hợp | Đặc điểm | Ví dụ |
|---|---|---|
| Explicit named module | Có module descriptor tường minh | JAR có module-info.class trên module path |
| Automatic module | JAR chưa modular hóa được đặt trên module path | legacy-util.jar trên module path |
| Unnamed module | Class được định nghĩa từ classpath | legacy-util.jar trên classpath |

Ví dụ cùng file JAR cũ:

~~~bash
java --class-path libs/legacy-util.jar com.example.Main
~~~

Class trong JAR được nạp qua classpath và thuộc unnamed module của class loader liên quan.

Khi đưa JAR đó lên module path, Java có thể nhận diện nó thành automatic module:

~~~bash
java --module-path libs \
     --add-modules legacy.util \
     --class-path app \
     com.example.Main
~~~

Tên **legacy.util** chỉ là minh họa; tên automatic module thực tế phải được xác minh bằng công cụ JDK. Automatic module export mọi package của nó và giúp tích hợp thư viện cũ, nhưng không có ranh giới exports chọn lọc như explicit named module.

Điểm cần nhớ: **JAR là artifact; việc đặt artifact ở classpath hay module path và metadata bên trong sẽ ảnh hưởng cách JPMS nhận diện nó**.

## 13. Package có thể nằm trong nhiều JAR không?

Trong môi trường classpath truyền thống, một package có thể có các class được đóng gói trong nhiều JAR:

~~~text
utils-a.jar -> com/example/common/TextUtil.class
utils-b.jar -> com/example/common/DateUtil.class
~~~

Class loader có thể tìm class từ cả hai JAR trong cùng classpath, dù có những rủi ro về duplicate class và phụ thuộc thứ tự tìm kiếm.

Nhưng khi mỗi JAR trở thành **một named module riêng**, cùng package **com.example.common** xuất hiện ở hai module là **split package**.

JPMS áp dụng các ràng buộc về readability, exports và ánh xạ class loader. Split package có thể gây lỗi biên dịch, module resolution hoặc định nghĩa module khi các module liên quan được dùng cùng nhau.

Vì vậy, thiết kế module nên có **package ownership rõ ràng**: mỗi package thuộc một module trong cùng bộ module dự kiến hoạt động chung. Không nên coi “đang chạy tốt trên classpath” là bằng chứng rằng JAR đã phù hợp để chuyển sang module path.

## 14. Một project có thể xuất nhiều JAR không?

Có. Công cụ build có thể tạo nhiều artifact, chẳng hạn:

- JAR chứa class chính.
- JAR chứa test fixtures.
- JAR chứa source.
- JAR chứa Javadoc.
- JAR có classifier khác phục vụ môi trường riêng.
- Artifact được shading, đóng gói lại hoặc tạo theo profile.

Điều này không đồng nghĩa mỗi JAR đều là một Java module mới. Ví dụ source JAR không phải artifact chạy như named module trong module graph chỉ vì nó có đuôi **.jar**.

Ngược lại, một Java module có thể được định nghĩa từ một thư mục exploded module thay vì một file JAR.

Khi thiết kế build, cần phân biệt rõ **artifact đầu ra nào thực sự được đưa lên module path của runtime**.

## 15. Một project build có thể chứa nhiều Java module không?

Về mặt kỹ thuật, công cụ build có thể được cấu hình để quản lý và biên dịch nhiều Java module từ một tập source. **javac** có hỗ trợ **--module-source-path** và **-m** để biên dịch nhiều named module.

Ví dụ minh họa ở trên đặt hai module dưới một thư mục **src** rồi biên dịch cùng một lệnh. Điều đó không yêu cầu phải có hai Maven project.

Tuy nhiên, trong Maven/Gradle thông thường, mô hình dễ quản lý thường là **một project con cho mỗi modular JAR chính**, để dependency, test, packaging và publish được tổ chức rõ ràng.

Vì vậy:

- “Một build project = một Java module” là **quy ước kiến trúc phổ biến**.
- “Một build project bắt buộc bằng một Java module” là **không đúng về mặt khái niệm**.

Hãy chọn cách tổ chức phù hợp với nhu cầu build và phiên bản công cụ, không dùng một quy ước như định nghĩa của JPMS.

## 16. Module boundary khác package boundary

Package cung cấp mức truy cập **package-private** trong ngôn ngữ Java. Các kiểu và member không có modifier public/protected/private có thể được truy cập trong phạm vi package theo quy tắc Java.

JPMS bổ sung cấp độ lớn hơn:

~~~text
com.example.catalog.api module
├── exports com.example.catalog.api
│   ├── ProductCatalog
│   └── Catalogs
└── com.example.catalog.internal
    └── MemoryCatalog
~~~

Trong module descriptor:

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Nếu code trong module app cố import:

~~~java
import com.example.catalog.internal.MemoryCatalog;
~~~

javac không cho phép truy cập theo cách thông thường vì package internal không được export, dù class có modifier public.

JPMS vì thế cho phép module **công khai API của một số package và giữ implementation package nội bộ**. Chỉ đặt package tên “internal” hoặc chỉ tách thư mục build chưa tạo được ranh giới kiểu này.

## 17. requires, exports, opens và uses/provides thuộc cấp độ nào?

Các directive sau nằm trong **module descriptor**:

~~~java
module com.example.app {
    requires com.example.catalog.api;
}
~~~

~~~java
module com.example.catalog.api {
    exports com.example.catalog.api;
}
~~~

Một module dùng framework reflection có thể mở package:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.entity to com.example.serializer;
}
~~~

Đối với service providers:

~~~java
module com.example.app {
    requires com.example.catalog.api;
    uses com.example.catalog.api.ProductCatalog;
}
~~~

~~~java
module com.example.catalog.memory {
    requires com.example.catalog.api;

    provides com.example.catalog.api.ProductCatalog
        with com.example.catalog.memory.MemoryCatalog;
}
~~~

Vai trò từng directive:

- **requires** tạo dependency đọc module.
- **exports** chỉ định package được công khai cho các module khác.
- **opens** phục vụ deep reflection ở runtime.
- **uses** công bố service mà module tiêu thụ.
- **provides ... with ...** đăng ký provider cho service.

Những thông tin này **không nằm trong khai báo package của từng class**, cũng không tự xuất hiện chỉ vì một Maven dependency được thêm vào POM.

## 18. Các trường hợp dễ nhầm trong thực tế

**“Tôi đã tạo package mới, vậy là có module mới.”**

Sai. Package mới chỉ tổ chức thêm các kiểu. Muốn có named module riêng, cần cấu hình module độc lập tương ứng.

**“Tôi tách project Maven, vậy là hai JPMS modules.”**

Chưa chắc. Hai project có thể chỉ tạo các JAR không có module descriptor và chạy trên classpath.

**“JAR này là module vì có đuôi .jar.”**

Chưa chính xác. JAR có thể là modular JAR, automatic module khi ở module path, hoặc chỉ là classpath artifact.

**“Một module chỉ được chứa một package.”**

Sai. Một named module có thể sở hữu nhiều package, kể cả package không được export.

**“Tất cả public class trong module đều truy cập được từ module khác.”**

Sai. Một kiểu public trong package không export không tự trở thành public API ở ranh giới module.

**“Tên module phải bằng Maven artifactId.”**

Sai. Tên module explicit đến từ module-info.java; Maven coordinate là tên artifact của build system.

**“Classpath và module path chỉ khác tên tham số.”**

Sai. Module path tham gia module resolution và áp dụng quy tắc của JPMS. Classpath truyền thống không tạo những named module boundary tương tự.

**“module-info.java luôn là một file đóng gói độc lập.”**

Sai. Module descriptor được biên dịch thành module-info.class và thường nằm trong exploded module hoặc modular JAR.

## 19. Cách chọn ranh giới module khi thiết kế dự án

Nên cân nhắc Java module khi muốn xác định:

1. Những API nào được các phần khác của hệ thống sử dụng.
2. Những package nào cần giữ implementation riêng.
3. Dependency giữa các thành phần lớn có hướng và được khai báo rõ.
4. Tính năng có thể phát hành hoặc kiểm thử như một khối.
5. Service interface và provider nào cần kết nối giữa các module.
6. Những phần code nào có thể thay đổi implementation mà không làm gãy consumer.

Đừng tách một module mới chỉ vì package có nhiều class. Việc tách module kéo theo descriptor, module path, dependency graph, kiểm thử và packaging.

Một module quá nhỏ có thể làm tăng số lượng dependency và phức tạp hóa build. Một module quá lớn có thể export nhiều package không cần thiết và khó giữ encapsulation. Ranh giới tốt thường đi theo **trách nhiệm và hợp đồng API ổn định**, không chỉ theo số lượng file.

## 20. Checklist khi thấy cấu trúc dự án Java

Khi tiếp nhận một repository, hãy trả lời theo thứ tự:

1. **Đâu là project build?** Tìm pom.xml, build.gradle hoặc build.gradle.kts.
2. **Project build tạo artifact nào?** Xác định JAR và output thực tế.
3. **Artifact có module-info.class không?** Dùng jar --list hoặc jar --describe-module.
4. **Tên Java module là gì?** Đọc module-info.java hoặc descriptor trong JAR.
5. **Module sở hữu package nào?** Xem source và package trong descriptor.
6. **Package nào được export/open?** Không suy luận từ modifier public.
7. **Module đọc module khác bằng requires nào?** Đối chiếu Maven/Gradle dependency.
8. **Ứng dụng chạy bằng classpath hay module path?** Xem launcher/script thực tế.
9. **Có automatic hoặc unnamed module không?** Kiểm tra dependency chưa modular hóa.
10. **Có split package không?** Tránh cùng package tồn tại ở nhiều named modules dùng chung.

Một dự án có thể có POM hoàn toàn hợp lệ nhưng module graph không hợp lệ, hoặc module graph hợp lệ nhưng script runtime không cung cấp đủ JAR. Vì vậy, cần kiểm tra cả **build model** và **runtime module model**.

## 21. Ghi nhớ

- **Package** tổ chức kiểu Java trong namespace; nó không phải đơn vị build hoặc artifact.
- **JAR** là archive đóng gói code/resource; nó có thể chứa module descriptor nhưng không phải JAR nào cũng là explicit named module.
- **Project build** là đơn vị của Maven/Gradle, quản lý source, dependency, task và artifact.
- **Java module** là đơn vị của JPMS, có module name, package ownership và các khai báo requires/exports/opens/uses/provides.
- Một Java module có thể chứa nhiều package.
- Một Java module có thể tồn tại dưới dạng exploded module, không bắt buộc phải là JAR.
- Một Maven project có thể tạo modular JAR nhưng project name và module name không buộc phải trùng.
- **pom.xml dependency** khác với directive **requires**.
- **public** không vượt qua được ranh giới package chưa export của named module.
- JAR trên classpath thường thuộc unnamed module; JAR không có descriptor trên module path có thể trở thành automatic module.
- Tách một package giữa nhiều module có thể gây split package; tách một project build chưa chắc tạo JPMS boundary.

**Kết luận:** package trả lời câu hỏi “kiểu này thuộc namespace nào?”, JAR trả lời “code được đóng gói trong file nào?”, project build trả lời “artifact được xây dựng thế nào?”, còn Java module trả lời “thành phần này đọc module nào và công khai package nào?”. Phân biệt đúng bốn tầng này là nền tảng để hiểu module path, module graph và thiết kế encapsulation trong Java hiện đại.
