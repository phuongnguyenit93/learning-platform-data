# Split package, package trùng và lỗi phân giải module

Trong **Java Advance Compatibility Migration**, việc chuyển từ classpath truyền thống sang **Java Platform Module System (JPMS)** không đơn thuần là bổ sung một file **module-info.java**. Một cấu trúc dependency từng hoạt động trên classpath có thể trở nên không hợp lệ khi các JAR được đưa lên module path. Nguyên nhân thường gặp là **split package**: cùng một package Java được phân bố giữa nhiều module thay vì thuộc về một module rõ ràng.

Bài học này thuộc nhóm **JPMS và nạp lớp**, tập trung vào cách nhận diện package trùng, các điều kiện gây lỗi ở bước biên dịch hoặc khi tạo module layer, mối liên hệ với class loader, và các phương án sửa để migration không phá vỡ ứng dụng hoặc consumer đã phát hành.

Mục tiêu sau bài học:

- Phân biệt **split package**, **class trùng tên đầy đủ**, resource trùng và package được sử dụng trong nhiều class loader khác nhau.
- Hiểu vì sao classpath có thể chấp nhận một cách bố trí mà JPMS không thể phân giải an toàn.
- Đọc được các thông báo như **reads package ... from both**, **ResolutionException**, **LayerInstantiationException**, cùng những lỗi nạp lớp dễ bị nhầm với split package.
- Tìm nguồn gốc package trùng trong JAR, dependency trực tiếp và dependency bắc cầu.
- Chọn phương án xử lý: gom package vào một module, đổi package, loại trừ dependency, cải tổ API, hoặc sử dụng cơ chế chuyển tiếp có kiểm soát.
- Xây dựng test cho cả classpath, module path, automatic module và ứng dụng có plugin.

## 1. Khái niệm nền tảng về package và module

### 1.1. Package là không gian tên, không phải artifact

Trong Java, khai báo:

~~~java
package com.example.shared;
~~~

xác định package của một kiểu. Một package có thể chứa nhiều class và interface. Trên classpath truyền thống, các class trong cùng package thường nằm rải rác ở nhiều thư mục hoặc JAR.

Ví dụ:

~~~text
legacy-a.jar
└── com/example/shared/Alpha.class

legacy-b.jar
└── com/example/shared/Beta.class
~~~

Dù thuộc hai JAR, **Alpha** và **Beta** vẫn nằm trong cùng package **com.example.shared**.

JAR là một đơn vị đóng gói file, không tự động đồng nghĩa với một JPMS module. Một JAR có thể được đặt trên classpath, trở thành automatic module khi đặt trên module path, hoặc chứa descriptor để trở thành explicit named module.

### 1.2. JPMS module thêm một ranh giới sở hữu

JPMS được giới thiệu trong Java 9. Một **named module** có tên, tập package và các quan hệ như **requires**, **exports**, **opens**, **uses** và **provides**.

Ví dụ:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
    requires java.logging;
}
~~~

Ở đây:

- **com.example.catalog** là tên module.
- **com.example.catalog.api** là package được export.
- **java.logging** là một module mà catalog đọc thông qua requires.
- Những package không được export không tự động trở thành API truy cập được từ module khác.

JPMS dùng module graph để xác định khả năng đọc (**readability**) và quyền truy cập đến package. Vì vậy, việc hai module cùng cung cấp một package có thể gây mơ hồ: một module tiêu thụ sẽ lấy package đó từ nơi nào?

### 1.3. Các loại module cần phân biệt

| Loại | Cách xuất hiện | Đặc điểm liên quan đến split package |
|---|---|---|
| **Explicit named module** | Có module descriptor, thường là module-info.class | Tập package và quan hệ module được mô tả rõ |
| **Automatic module** | JAR không có descriptor, đặt trên module path | Được cấp tên module tự động; thường export các package của nó và có cơ chế đọc thuận tiện cho migration |
| **Unnamed module** | Classpath, theo class loader | Có thể chứa class từ nhiều JAR, nhưng không được quản lý như named module thông thường |
| **Module được patch** | Named module nhận thêm nội dung bằng --patch-module | Nội dung được đưa vào module được patch; không phải một cách tự do hợp nhất các named module đang xung đột |

**Gradle module** hay **Maven module** không đồng nghĩa với JPMS module. Một subproject của Gradle có thể xuất JAR không có module-info, và một dự án Maven cũng không mặc định là một JPMS named module.

## 2. Split package là gì?

Một **split package** xuất hiện khi các class thuộc **cùng một package Java** được phân bố trên nhiều module, trong khi module system cần xử lý chúng như những nguồn package riêng biệt.

Ví dụ:

~~~text
com.example.alpha (named module)
└── com/example/shared/Alpha.class

com.example.beta (named module)
└── com/example/shared/Beta.class
~~~

Cả hai module đều chứa **com.example.shared**. Nếu một module thứ ba cần đọc package này từ cả hai module, hệ thống gặp mơ hồ.

Lưu ý: split package không nhất thiết đòi hỏi class trùng tên. Hai class **Alpha** và **Beta** khác tên nhưng vẫn gây xung đột vì package giống nhau.

### 2.1. Phân biệt ba dạng “trùng”

| Hiện tượng | Ví dụ | Có phải split package? | Rủi ro chính |
|---|---|---|---|
| Cùng package, khác class | JAR A có **p.A**, JAR B có **p.B** | Có thể là split package khi nằm ở các module khác nhau | JPMS không xác định nguồn package duy nhất |
| Cùng tên class đầy đủ | Cả A và B đều có **p.Config** | Đồng thời có package trùng; còn là duplicate class | Class bị che khuất hoặc nạp sai phiên bản |
| Cùng resource path | Hai JAR có **META-INF/config.properties** | Không nhất thiết | Resource lookup theo thứ tự/loader, merge hoặc ghi đè |
| Cùng package ở hai loader cô lập | Hai plugin loader có riêng **p.Helper** | Không tự động là split package trong cùng graph | Danh tính class, cast, service bridge và tương tác giữa loader |

**Duplicate class** thường nghiêm trọng hơn ở mặt ứng dụng: classloader có thể nạp bản không mong muốn dù biên dịch không báo lỗi. Nhưng việc hai JAR chứa class khác nhau trong cùng package cũng đã đủ gây rủi ro JPMS.

### 2.2. Vì sao classpath truyền thống thường “chạy được”?

Trên classpath, nhiều JAR có thể đóng góp class vào cùng không gian tên của unnamed module gắn với một class loader. JVM không áp dụng đầy đủ ranh giới named module cho cách bố trí đó.

Ví dụ:

~~~bash
java -cp "legacy-a.jar:legacy-b.jar:app.jar" com.example.app.Main
~~~

Trên Windows, ký tự phân tách classpath thường là dấu chấm phẩy (**;**) thay cho dấu hai chấm (**:**).

Ở cấu hình này, việc có **com.example.shared.Alpha** trong JAR A và **com.example.shared.Beta** trong JAR B có thể hoạt động bình thường.

Điều đó không chứng minh hai JAR có thể chuyển lên module path mà không thay đổi. JPMS bổ sung kiểm tra package ownership, readability và module graph.

## 3. Vì sao JPMS hạn chế split package?

Module system hướng tới sự rõ ràng: khi module **M** đọc một package cụ thể, cấu hình phải xác định được nguồn gói hợp lệ, thay vì dựa vào thứ tự tình cờ của các JAR.

Một module cũng cần được tạo trong module layer với cơ chế ánh xạ package, class loader và module phù hợp. Nếu nhiều module được định nghĩa vào cùng loader mà khai báo cùng package, việc tạo layer có thể thất bại.

Hai loại xung đột thường gặp:

1. **Xung đột readability/exports:** một module đọc cùng package được export từ hai nguồn khác nhau.
2. **Xung đột khi định nghĩa module vào class loader:** hai module chứa cùng package nhưng được ánh xạ vào cùng loader theo một cấu hình không hợp lệ.

Không nên phát biểu rằng **bất cứ** hai JAR nào có cùng package đều làm mọi JVM khởi động thất bại. Kết quả phụ thuộc vào chúng nằm trên classpath hay module path, module nào được resolve, graph có đọc package từ cả hai nguồn không, và cách các module được định nghĩa vào class loader/layer.

### 3.1. Readability và exports khác với classpath lookup

~~~text
com.example.app
   | requires
   +-------------------> com.example.alpha
   |                       exports com.example.shared
   |
   | requires
   +-------------------> com.example.beta
                           exports com.example.shared
~~~

Nếu **com.example.app** đọc **com.example.shared** từ cả alpha và beta, compiler có thể báo:

~~~text
module com.example.app reads package com.example.shared
from both com.example.alpha and com.example.beta
~~~

Thông báo thực tế có thể khác theo công cụ và phiên bản JDK. Ý nghĩa vẫn là: cấu hình đang đưa cùng package đến module tiêu thụ từ hai nguồn module.

**exports** xác định khả năng truy cập package từ module khác; **requires** tạo quan hệ đọc. Chúng không phải cơ chế chuyển quyền sở hữu package giữa các module.

### 3.2. JPMS cố định ranh giới ở mức module

Ở classpath, nhiều dependency có thể chia nhau các class trong một package mà không báo lỗi ngay. Với JPMS, cấu trúc như vậy cần được xem lại:

- Các class thuộc một library logical duy nhất hay không?
- Package có cần được gom vào một named module không?
- Hai dependency có thực sự độc lập về API và vòng đời không?
- Có thể đổi tên package để thể hiện ranh giới sở hữu không?
- Một dependency chỉ nên ở classpath trong giai đoạn chuyển tiếp không?

Thay đổi cách đóng gói có thể đụng đến public API và consumer, vì package là một phần trong tên đầy đủ của class.

## 4. Ví dụ tái hiện lỗi reads package ... from both

Xét ba named module độc lập.

### 4.1. Module alpha

File **src/com.example.alpha/module-info.java**:

~~~java
module com.example.alpha {
    exports com.example.shared;
}
~~~

File **src/com.example.alpha/com/example/shared/Alpha.java**:

~~~java
package com.example.shared;

public class Alpha {
    public static String name() {
        return "alpha";
    }
}
~~~

### 4.2. Module beta

File **src/com.example.beta/module-info.java**:

~~~java
module com.example.beta {
    exports com.example.shared;
}
~~~

File **src/com.example.beta/com/example/shared/Beta.java**:

~~~java
package com.example.shared;

public class Beta {
    public static String name() {
        return "beta";
    }
}
~~~

Module alpha và beta khác tên nhưng export cùng package **com.example.shared**.

### 4.3. Module app

File **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
~~~

File **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("start");
    }
}
~~~

Dù Main chưa trực tiếp gọi Alpha hoặc Beta, module descriptor vẫn có cả hai quan hệ **requires**.

### 4.4. Biên dịch từng module

Tạo trước các thư mục đầu ra rồi biên dịch từng module độc lập:

~~~bash
# Ví dụ shell Linux/macOS
mkdir -p mods/com.example.alpha mods/com.example.beta mods/com.example.app

javac -d mods/com.example.alpha \
  src/com.example.alpha/module-info.java \
  src/com.example.alpha/com/example/shared/Alpha.java

javac -d mods/com.example.beta \
  src/com.example.beta/module-info.java \
  src/com.example.beta/com/example/shared/Beta.java
~~~

Khi biên dịch app:

~~~bash
javac --module-path mods -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
~~~

Compiler có thể báo lỗi vì app đọc package **com.example.shared** từ cả alpha và beta. Ví dụ là lỗi về module graph chứ không phải do tên class Alpha/Beta trùng nhau.

Nếu chuyển alpha và beta thành JAR rồi đưa cả hai lên module path, cùng mô hình xung đột có thể xuất hiện khi module app resolve dependencies.

### 4.5. Thay package để xử lý tận gốc

Một hướng sửa là giao cho mỗi module package riêng:

~~~text
com.example.alpha
└── com/example/alpha/api/Alpha.class

com.example.beta
└── com/example/beta/api/Beta.class
~~~

Descriptor sau khi sửa:

~~~java
module com.example.alpha {
    exports com.example.alpha.api;
}
~~~

~~~java
module com.example.beta {
    exports com.example.beta.api;
}
~~~

Khi đó app có thể đọc cả hai package mà không bị mơ hồ. Tuy nhiên, việc đổi package làm đổi tên binary của class, vì vậy consumer đang import hoặc liên kết với tên cũ cần được cập nhật hoặc có một phương án tương thích chuyển tiếp.

## 5. Split package với automatic module

Một JAR thư viện cũ không có **module-info.class** khi đặt trên module path có thể trở thành **automatic module**. Module này được đặt tên từ metadata như **Automatic-Module-Name** trong manifest hoặc tên JAR theo quy tắc của JPMS.

Ví dụ:

~~~text
legacy-utils-1.0.jar
├── META-INF/MANIFEST.MF
└── com/example/common/Helper.class
~~~

Khi nó nằm trên module path:

~~~bash
java --module-path lib:mods -m com.example.app/com.example.app.Main
~~~

nó có thể được resolve như một automatic module, thay vì chỉ là tập class trong unnamed module.

### 5.1. Automatic module không xóa rủi ro split package

Automatic module hỗ trợ đưa thư viện cũ vào module graph trong giai đoạn migration. Nhưng nó vẫn là một **named module** khi được resolve và có package set của riêng mình.

Nếu hai automatic module chứa cùng package, hoặc automatic module chồng package với explicit named module, module graph có thể xung đột. Việc chúng không có descriptor do tác giả viết không làm package trùng biến mất.

Một automatic module thường export các package của nó để dễ tương tác với module khác. Điều này có thể khiến trùng package bộc lộ ngay khi các dependency được đưa vào cùng graph.

### 5.2. Kiểm tra tên module thực tế

Dùng:

~~~bash
jar --describe-module --file legacy-utils-1.0.jar
~~~

Nếu JAR không có explicit descriptor, kết quả có thể cho biết đây là automatic module và tên module suy ra từ tên file/manifest.

Tên suy ra từ tên JAR có thể thay đổi khi tên artifact đổi. Vì vậy, khi quyết định sử dụng automatic module dài hạn, cần ổn định module name và kiểm tra mọi phụ thuộc đang khai báo **requires** tới tên đó.

### 5.3. Không coi Automatic-Module-Name là giải pháp split package

Thêm manifest:

~~~text
Automatic-Module-Name: com.example.legacy
~~~

giúp ổn định **tên module**, không đổi tên các package bên trong JAR. Hai JAR dù có module name khác nhau vẫn split package nếu chúng cùng chứa **com.example.common**.

Một số hệ thống chỉ gặp lỗi sau khi nâng dependency vì bản mới thêm **Automatic-Module-Name** hoặc bắt đầu có **module-info.class**. Cần phân tích bản JAR thực tế tại runtime, không chỉ POM hoặc build file.

## 6. Named module và classpath trong giai đoạn chuyển đổi

Một chiến lược migration thường gặp là chuyển dần thư viện sang JPMS, trong khi phần còn lại vẫn ở classpath.

~~~text
               Application
                  |
             Named modules
                  |
             Automatic modules
                  |
               Classpath
              (unnamed)
~~~

Sơ đồ chỉ minh họa các vùng có thể tồn tại, không có nghĩa named module tự động đọc classpath.

### 6.1. Unnamed module có quy tắc riêng

Code trên classpath thuộc unnamed module gắn với class loader. Unnamed module có thể đọc các named module được resolve, nhưng named module **không mặc định** đọc unnamed module như một dependency được khai báo bằng **requires**.

Nếu code trong named module cần gọi thư viện chỉ có trên classpath, có thể gặp lỗi về readability hoặc không tìm được kiểu như mong đợi. Trong một số cấu hình migration, cờ:

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

có thể được sử dụng để thêm read edge từ named module sang các unnamed module.

Đây là cơ chế điều chỉnh readability, **không phải cách sửa split package giữa hai named module**. Nếu package vẫn xuất hiện từ hai nguồn được đọc, thêm read edge không làm nó trở thành một package duy nhất.

### 6.2. Classpath có thể che giấu xung đột

Ví dụ:

~~~text
classpath:
  vendor-a.jar -> com.example.util.Parser
  vendor-b.jar -> com.example.util.Validator
~~~

Cấu hình này có thể chạy. Nhưng sau khi cả hai JAR chuyển thành automatic modules trên module path, hai module đều mang package **com.example.util**, làm phát sinh xung đột.

Do đó, phép thử “ứng dụng cũ chạy trên classpath” chỉ chứng minh baseline cũ, không chứng minh thiết kế module path sẽ hoạt động.

### 6.3. Tránh lạm dụng chuyển ngược về classpath

Đưa một dependency về classpath có thể là giải pháp chuyển tiếp nếu kiến trúc cho phép. Nhưng cần xét:

- Named module có cần trực tiếp tham chiếu các kiểu từ dependency đó không?
- Có cần cờ **--add-reads** và cơ chế truy cập khác không?
- Có phụ thuộc transitive vào package trùng không?
- Có thay đổi về ServiceLoader và reflective access không?
- Có thể giữ cấu hình này trong bao lâu?
- Có kế hoạch chuyển package ownership về mô hình rõ ràng không?

Không nên trình bày “để tất cả lên classpath” như giải pháp migration JPMS hoàn chỉnh. Nó loại bỏ một số kiểm tra của JPMS và có thể giữ lại mơ hồ của classpath.

## 7. Phân biệt lỗi phân giải module và lỗi nạp lớp

Không phải lỗi phát sinh sau khi chuyển module path đều do split package. Cần đọc đúng loại lỗi và giai đoạn xảy ra.

| Lỗi hoặc thông báo | Giai đoạn thường gặp | Nguyên nhân điển hình | Liên hệ split package |
|---|---|---|---|
| **module X reads package p from both A and B** | javac hoặc kiểm tra graph | X đọc package p từ hai named module | Dấu hiệu trực tiếp |
| **ResolutionException** | Phân giải module graph | Graph không thỏa ràng buộc readability hoặc package | Có thể do split package, nhưng còn nguyên nhân khác |
| **LayerInstantiationException** | Tạo module layer/class loader mapping | Module layer không thể được định nghĩa theo mapping package/module | Có thể do package trùng trong cùng loader |
| **FindException** | Tìm/đọc module trên module path | Module không tìm được, descriptor/JAR lỗi, cấu hình module không hợp lệ | Có thể liên quan nhưng không mặc định |
| **ClassNotFoundException** | Nạp class theo tên | Class thiếu hoặc loader không nhìn thấy class | Không đủ kết luận split package |
| **NoClassDefFoundError** | Liên kết hoặc nạp class | Class phụ thuộc không có hoặc lỗi nạp trước đó | Có thể là hậu quả khác của migration |
| **IllegalAccessError** | Liên kết/truy cập kiểu hoặc member | Runtime access không hợp lệ | Thường là exports/access, không phải split package thuần |
| **InaccessibleObjectException** | Reflection | Package chưa opens đúng với caller | Không phải split package |
| **NoSuchMethodError** | Liên kết lời gọi method | Artifact phiên bản khác descriptor hoặc API | Thường do dependency conflict/duplicate class |

Không chỉ nhìn tên exception rồi tự động chỉnh **--add-exports** hoặc **--add-opens**. Cần xác định module nào đang đọc package nào và artifact thực tế nào được nạp.

### 7.1. ResolutionException và module graph

Module resolution là quá trình chọn tập module và thiết lập quan hệ đọc hợp lệ từ root modules và các dependency. Một xung đột package có thể làm graph không hợp lệ trước khi ứng dụng chạy vào phương thức **main**.

Nếu thấy lỗi từ **java.lang.module.Resolver** hoặc thông báo nêu module đọc cùng package từ hai nguồn, hãy lập lại đường đi:

~~~text
Root module
   |
   +---- requires A
   |
   +---- requires B
               |
               +---- exports package p
A also exports package p
~~~

Kiểm tra cả **requires transitive**, không chỉ các requires viết trực tiếp trong root.

### 7.2. LayerInstantiationException và module-to-loader mapping

Một **ModuleLayer** là tập module được cấu hình và định nghĩa cùng nhau. Tùy cách tạo layer, nhiều module có thể dùng cùng class loader hoặc có loader khác nhau.

Nếu hai module cùng sở hữu package mà việc định nghĩa chúng trong cùng loader không được phép, quá trình tạo layer có thể ném **LayerInstantiationException**.

Ví dụ trong plugin architecture, một tùy chỉnh dùng **defineModulesWithOneLoader** có thể gặp ràng buộc khác với thiết kế loader cho từng module. Đây không phải lý do để tắt các ràng buộc: cần phân tích module graph, package set và cách loader được tạo.

### 7.3. FindException không tự động là split package

**FindException** có thể xuất hiện khi module path có file JAR hỏng, module descriptor không hợp lệ, tên module không tìm được, hoặc lỗi khác khi đọc metadata.

Khi thấy FindException, hãy ưu tiên đọc message và cause trước. Nếu thông báo không chỉ rõ package trùng, cần kiểm tra artifact và module descriptors trước khi kết luận.

### 7.4. Lỗi “không thấy class” khác lỗi package trùng

**ClassNotFoundException** thường xảy ra ở class loading động như **Class.forName**, hoặc class loader không nhìn thấy class cần nạp. **NoClassDefFoundError** có thể xảy ra nếu class phụ thuộc thiếu tại runtime.

Trong khi đó, split package là vấn đề về nguồn package trong module graph hoặc loader mapping. Hai nhóm lỗi có thể cùng xuất hiện trong một migration, nhưng cách sửa không giống nhau.

## 8. Vai trò của class loader

### 8.1. Danh tính class gồm class name và defining loader

Hai class có cùng tên đầy đủ nhưng do hai defining class loader khác nhau tạo ra không nhất thiết là cùng một kiểu đối với JVM.

Ví dụ:

~~~text
PluginLoader A:
  com.example.spi.PluginImpl

PluginLoader B:
  com.example.spi.PluginImpl
~~~

Dù tên giống nhau, hai class có thể không cast được sang nhau nếu loader khác nhau và API bị nhân bản không đúng cách. Một lỗi kiểu **ClassCastException** có thể xuất hiện, nhưng đó không phải lúc nào cũng là split package trong JPMS.

### 8.2. Package ownership và loader mapping là hai lớp kiểm soát

JPMS kiểm tra package, readability và access ở mức module. JVM class loading kiểm tra class identity và mapping tới defining loader.

Cần xem đồng thời:

1. Module nào có package.
2. Module nào được resolve trong layer.
3. Module nào đọc hoặc export package đó.
4. Defining class loader của module.
5. Class hoặc resource nào thực sự được nạp.
6. Có class khác cùng tên trên classpath hoặc trong plugin loader không.

Một sơ đồ đơn giản:

~~~text
ModuleLayer
   |
   +---- Module A ---> Loader L1 ---> package p
   |
   +---- Module B ---> Loader L2 ---> package p
   |
   +---- Module C ---> Loader L3 ---> package q
~~~

Một số cấu hình class loader cô lập có thể tránh xung đột định nghĩa package trong cùng loader. Tuy nhiên, điều đó không tự động giải quyết mọi quy tắc module resolution, readability, service type identity và giao tiếp giữa các plugin. Không nên dùng loader cô lập như một “mẹo” để bỏ qua thiết kế package ownership.

### 8.3. Plugin systems cần kiểm tra thêm

Khi nạp plugin vào layer khác hoặc loader riêng:

- Plugin có cần import API công khai của host không?
- API type có bị nhân bản trong mỗi plugin JAR không?
- Host và plugin có cùng nhìn một kiểu **com.example.spi.Plugin** từ một module/loader không?
- Có split package nội bộ giữa các plugin không?
- Có yêu cầu **opens** cho reflection không?
- Có loader mapping nào định nghĩa nhiều module cùng package vào một loader không?

Giải pháp bền vững thường là giữ API hợp đồng dùng chung trong một module rõ ràng, còn phần implementation riêng trong package/module khác nhau.

## 9. Nguyên nhân phổ biến trong dự án thực tế

### 9.1. Chia một package logic thành nhiều artifact

Trong hệ thống cũ:

~~~text
client-api.jar
  com.example.client.Request

client-impl.jar
  com.example.client.DefaultRequest
~~~

Hai artifact cùng package để chia API và implementation. Trên classpath, cấu trúc này có thể hoạt động.

Khi biến hai artifact thành hai named module riêng biệt, package **com.example.client** bị chia. Giải pháp có thể là gom lại thành một module hoặc chuyển implementation sang **com.example.client.internal** nếu API cho phép.

### 9.2. JAR cũ và JAR mới cùng xuất hiện

Dependency graph có thể chứa đồng thời:

~~~text
legacy-core.jar  -> com.example.common.*
new-core.jar     -> com.example.common.*
~~~

Đây có thể là kết quả của dependency trực tiếp, transitive dependency hoặc shading không đúng cách.

Khi đó cần loại trừ artifact cũ hoặc hợp nhất version constraints, không chỉ đổi tên module.

### 9.3. Thư viện “all-in-one” và thư viện thành phần

Một bộ thư viện có thể cung cấp cả artifact tổng hợp và artifact con:

~~~text
vendor-all.jar
  com.vendor.api.*
  com.vendor.impl.*

vendor-api.jar
  com.vendor.api.*
~~~

Nếu cả hai cùng lên module path, package **com.vendor.api** bị lặp. Tùy cấu trúc cụ thể, còn có thể có duplicate class.

Cách xử lý thường là chọn một chiến lược dependency duy nhất, không dùng cả “all” và “api” nếu tài liệu vendor không yêu cầu.

### 9.4. Shaded JAR không relocate package

Một thư viện có thể nhúng dependency vào JAR của nó mà không đổi package:

~~~text
my-sdk.jar
  com.example.sdk.*
  org.thirdparty.codec.*

thirdparty-codec.jar
  org.thirdparty.codec.*
~~~

Lúc đó cùng package **org.thirdparty.codec** xuất hiện từ hai module. Chỉ “shade” vào JAR khác không tự tránh split package. Cần xem chính sách relocation và tác động tới API.

### 9.5. Generated code hoặc annotation processor

Code generator có thể tạo class trong package đã được một module khác sở hữu. Chẳng hạn:

- ORM-generated metamodel.
- Protocol buffer hoặc gRPC-generated classes.
- SOAP/JAXB-generated classes.
- Annotation processor tự sinh helper vào package của thư viện.
- Adapter tự sinh được đóng gói thành JAR riêng.

Nếu generator tạo code vào cùng package như thư viện gốc nhưng thành artifact/module khác, migration JPMS có thể gặp split package. Cần xác định module sở hữu generated source và đưa nó vào đúng chỗ.

### 9.6. Test fixtures và test dependencies

Test source hoặc fixture JAR có thể dùng cùng package như production code để truy cập package-private helpers. Khi chuyển sang named modules, test configuration có thể bắt đầu xung đột.

Một cách xử lý có kiểm soát là **patch** test classes vào module được test trong giai đoạn test, nếu build tool hỗ trợ, thay vì đóng test fixture thành named module khác sở hữu cùng package. Đây là lựa chọn cấu hình test cụ thể, không phải giải pháp chung cho hai library module sản xuất.

## 10. Khảo sát package trùng từ JAR thực tế

Để sửa lỗi, cần biết **artifact nào** chứa package trùng. Đọc dependency declaration chưa đủ vì có dependency bắc cầu và JAR được đóng gói lại.

### 10.1. Liệt kê class trong JAR

Dùng lệnh:

~~~bash
jar --list --file path/to/library.jar
~~~

Tìm các entry:

~~~text
com/example/shared/Alpha.class
com/example/shared/Beta.class
~~~

Chuyển đường dẫn class file thành tên package bằng cách bỏ phần tên class sau dấu gạch chéo cuối cùng.

Lưu ý tránh gán nhầm file resource vào package hoặc xem **META-INF/** là Java package. Với **multi-release JAR**, các class dưới **META-INF/versions/** cũng cần được phân tích theo release runtime; không đơn giản xem mọi entry là một module khác nhau.

### 10.2. Xem module descriptor

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Với explicit named module, kết quả giúp kiểm tra:

- Module name.
- Exports.
- Requires.
- Provides/uses khi có.
- Package metadata theo descriptor/định dạng JAR.

Với automatic module, hãy kiểm tra tên module được suy ra hoặc khai báo trong manifest.

Kết quả module descriptor giúp xác định package được export, nhưng split package có thể liên quan cả package không export trong một tình huống loader mapping. Vì vậy, cần xem tập class thực tế, không chỉ các exports.

### 10.3. Kiểm tra module path

Java launcher có tùy chọn:

~~~bash
java --validate-modules --module-path path/to/libs
~~~

Tùy chọn này hữu ích để phát hiện một số vấn đề về module path trước khi chạy ứng dụng. Tuy nhiên, nó không thay thế việc test **đúng root module** và module graph mà ứng dụng thực sự resolve.

Trong một số dự án, cần chạy lệnh kiểm tra với cùng module path, module name và launcher arguments được dùng ở production để tái hiện lỗi.

### 10.4. Kiểm tra quan hệ phụ thuộc

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh này giúp truy nguồn transitive dependency hoặc artifact tổng hợp. Ở những dự án có source set/task khác nhau, cần xem đúng configuration của ứng dụng hoặc test tương ứng.

Đừng chỉ nhìn dependency trực tiếp. Hai module bị trùng package có thể đến từ hai đường transitive khác nhau.

### 10.5. Kiểm tra module graph và phụ thuộc tĩnh

**jdeps** có thể hỗ trợ xem dependency ở mức package hoặc module, tùy tham số:

~~~bash
jdeps --module-path path/to/libs --check com.example.app
~~~

Với một artifact JAR:

~~~bash
jdeps --summary path/to/app.jar
~~~

**jdeps** chủ yếu quan sát dependency tĩnh. Reflection, ServiceLoader, code generation và các class chỉ được nạp qua cấu hình có thể không xuất hiện đầy đủ. Vì vậy, cần kết hợp khảo sát runtime.

### 10.6. Lập bảng chứng cứ

| Package | Artifact 1 | Artifact 2 | Loại module | Điểm phát hiện |
|---|---|---|---|---|
| com.example.shared | alpha.jar | beta.jar | Hai named modules | Compile module app |
| org.thirdparty.codec | sdk-shaded.jar | codec.jar | Automatic + explicit/automatic | Validate module path |
| com.example.generated | app.jar | fixtures.jar | Named + test fixture | Test task |
| com.vendor.api | vendor-all.jar | vendor-api.jar | Hai JAR vendor | Dependency graph |

Bảng cần ghi thêm version, checksum, nguồn dependency và owner khi áp dụng thực tế. Không đủ thông tin nếu chỉ ghi tên file: hai môi trường có thể chứa JAR cùng tên nhưng khác nội dung.

## 11. Quy trình chẩn đoán theo từng bước

### Bước 1: Ghi nhận đúng lỗi

Lưu nguyên văn:

- Command line khởi chạy.
- JDK version và vendor.
- Module path và classpath.
- Root module hoặc main class.
- Stack trace và message.
- Danh sách artifact/version tại runtime.

Nếu lỗi xảy ra trong Gradle/Maven/IDE, xác định tiến trình nào báo lỗi: compiler, test worker, JavaExec hay application JVM.

### Bước 2: Xác định package và hai nguồn

Nếu message là **reads package p from both A and B**, ghi rõ p, A, B. Kiểm tra JAR và module descriptor để xác nhận package tồn tại ở mỗi nguồn.

Nếu lỗi chỉ nêu **LayerInstantiationException**, kiểm tra nguyên nhân và mapping module-to-classloader. Nếu lỗi là **NoClassDefFoundError**, chưa đủ chứng cứ kết luận split package.

### Bước 3: Vẽ dependency/module graph tối thiểu

Ví dụ:

~~~text
app
 | \
 |  \-- requires lib-b
 |
 +----- requires lib-a

lib-a -> exports p
lib-b -> exports p
~~~

Đánh dấu dependency trực tiếp và bắc cầu, automatic modules, unnamed code và các module được thêm qua launcher arguments.

### Bước 4: Xác định mức trùng

Có thể là:

1. Chỉ trùng package, class khác nhau.
2. Trùng cả package và fully qualified class.
3. Trùng package chỉ trong test/generated code.
4. Trùng trong shaded JAR.
5. Trùng giữa named module và một thư viện trên classpath.
6. Trùng giữa module layers/loaders nhưng không ở cùng graph đọc.

Mỗi loại có phương án sửa khác nhau. Chỉ rename module không xử lý được class/package trùng.

### Bước 5: Chọn phương án sửa theo ownership

Xác định module **nên sở hữu package**. Nếu cùng một library logical, có thể gom class vào một module. Nếu là hai library độc lập, nên tách namespace. Nếu một dependency bị lặp không cần thiết, loại trừ nó.

### Bước 6: Kiểm tra lại cả binary và behavior

Sau sửa, cần:

- Build lại named modules cần thiết.
- Verify module graph.
- Chạy ứng dụng trên đúng module path mục tiêu.
- Chạy test API/consumer.
- Kiểm tra reflection, ServiceLoader và plugin.
- Đảm bảo không làm thay đổi FQCN công khai mà chưa có kế hoạch migration.
- Lưu artifact và log test.

Đừng dừng ở chỗ compiler hết báo **reads package**. Một workaround về package có thể làm class cast, serialization hoặc ServiceLoader hỏng ở runtime.

## 12. Các chiến lược xử lý split package

### 12.1. Gom các class thuộc cùng package vào một named module

Nếu A và B thực chất là hai phần của một thư viện logical, một named module có thể sở hữu toàn bộ package:

~~~text
Trước:
  module A -> com.example.shared.Alpha
  module B -> com.example.shared.Beta

Sau:
  module com.example.sharedlib
    -> com.example.shared.Alpha
    -> com.example.shared.Beta
~~~

Ưu điểm:

- Package ownership rõ ràng.
- Có thể giữ nguyên tên package và FQCN của class.
- Giảm split package trên module path.

Cần cân nhắc:

- Build/dependency graph thay đổi.
- Không nên đóng gói cùng class hai lần trong artifact cũ và mới.
- Consumer phải biết module name mới nếu dùng module-info.
- Có thể phải giữ artifact chuyển tiếp trên classpath cho consumer cũ.
- Hợp đồng public API và OSGi/JPMS integration có thể chịu ảnh hưởng.

### 12.2. Đổi package của một bên

Ví dụ:

~~~text
Trước:
  alpha -> com.example.common.Alpha
  beta  -> com.example.common.Beta

Sau:
  alpha -> com.example.alpha.Alpha
  beta  -> com.example.beta.Beta
~~~

Ưu điểm: mỗi module có namespace riêng, giảm phụ thuộc không cần thiết.

Nhược điểm: FQCN của class thay đổi, dẫn tới breaking change cho source import, bytecode consumer, reflection, serialized data và cấu hình. Cần adapter/migration guide hoặc major version phù hợp.

### 12.3. Loại trừ dependency trùng

Nếu conflict do một artifact cũ được kéo transitively nhưng không còn cần thiết, loại trừ nó tại dependency declaration hoặc chọn đúng bộ artifact của vendor.

Ví dụ Gradle Groovy DSL, minh họa:

~~~groovy
dependencies {
    implementation('com.example:feature:2.0') {
        exclude group: 'com.vendor', module: 'legacy-api'
    }
    implementation 'com.vendor:modern-api:3.0'
}
~~~

Điều kiện là **feature** thực sự tương thích với **modern-api**. Loại trừ bằng tay không chứng minh runtime còn đủ class. Sau khi exclude, kiểm tra dependency graph, compile và integration test.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>feature</artifactId>
    <version>2.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.vendor</groupId>
            <artifactId>legacy-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Cũng cần khai báo artifact thay thế thích hợp nếu code còn sử dụng API của vendor.

### 12.4. Relocation khi shading dependency

Nếu một thư viện nội bộ nhúng dependency vào JAR, có thể relocate package private của dependency:

~~~text
Trước:
  sdk.jar        -> org.thirdparty.codec.*
  codec.jar      -> org.thirdparty.codec.*

Sau:
  sdk.jar        -> com.example.sdk.internal.codec.*
  codec.jar      -> org.thirdparty.codec.*
~~~

Relocation có thể ngăn split package giữa hai module. Nhưng cần lưu ý:

- Không relocate tùy tiện kiểu xuất hiện trong public API.
- Reflection dùng tên class dạng chuỗi có thể cần điều chỉnh.
- Service provider configuration dưới **META-INF/services** phải được xử lý.
- Serialization có thể phụ thuộc tên class cũ.
- Native/JNI binding hoặc resource paths có thể cần đổi.
- License và chính sách phân phối của dependency phải được tôn trọng.

Relocation phù hợp nhất với implementation detail được đóng gói riêng, không phải API được nhiều consumer chia sẻ.

### 12.5. Di chuyển generated source về đúng module sở hữu

Nếu generated classes cần nằm cùng package với API để truy cập package-private members, có thể cấu hình build để các source đó được compile như một phần của module sở hữu package.

Một phương án tạm thời trong test/tooling là **--patch-module**. Tuy nhiên, việc ghép generated source vào module cần tuân theo ownership và quy trình build rõ ràng; không nên tạo một named module riêng chứa cùng package chỉ để chuyển artifact từ classpath sang module path.

### 12.6. Giữ một phần legacy trên classpath có kiểm soát

Có thể giữ thư viện cũ trong unnamed module nếu ứng dụng vẫn có phần code classpath và chưa thể module hóa tất cả.

Đây là lựa chọn chuyển tiếp, không nên xem là kiến trúc đích nếu mục tiêu là JPMS hoàn chỉnh. Cần ghi:

- Module nào còn ở classpath.
- Named module nào cần truy cập chúng.
- Những cờ runtime tạm thời.
- Kiểm thử với đúng class loader.
- Thời điểm loại bỏ workaround.

### 12.7. Tách API chung khỏi implementation riêng

Nếu hai module chia package vì cùng dùng một interface/DTO, nên cân nhắc tạo một module API chung và chuyển implementation sang package riêng:

~~~text
com.example.contract
└── com.example.contract.api.Request

com.example.client
└── com.example.client.impl.ClientRequest

com.example.server
└── com.example.server.impl.ServerRequest
~~~

Module client/server có thể **requires com.example.contract**, thay vì copy class API hoặc tạo một nửa package chung trong mỗi JAR.

Điều này giúp API có một nguồn định nghĩa và giảm lỗi về class identity khi các service hoặc plugin giao tiếp.

## 13. Các tùy chọn dòng lệnh: cái gì sửa được và không sửa được?

### 13.1. --patch-module

Cú pháp minh họa:

~~~bash
java --patch-module com.example.app=path/to/extra-classes \
     --module-path path/to/mods \
     -m com.example.app/com.example.app.Main
~~~

**--patch-module** đưa thêm class/resource vào một module đã tồn tại. Cơ chế này hữu ích cho test, một số tình huống migration hoặc sửa đổi có kiểm soát. Nó không phải lệnh “cho phép hai named module khác nhau cùng sở hữu package p”.

Không nên sử dụng patch-module để che một cấu trúc dependency trùng lặp lâu dài. Cần đặc biệt thận trọng khi class mới và class gốc có cùng FQCN.

### 13.2. --add-reads

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

Thêm khả năng đọc, thường dùng như cầu nối named/unnamed code. Không chuyển package từ module này sang module khác; không tự xử lý việc package xuất hiện ở hai named module được đọc.

### 13.3. --add-exports

~~~bash
--add-exports com.example.core/com.example.core.internal=com.example.app
~~~

Mở quyền truy cập **compile/runtime** tới một package từ module khác theo cơ chế export bổ sung. Không đổi package ownership và không giúp phân biệt hai module cùng export package p cho cùng consumer.

### 13.4. --add-opens

~~~bash
--add-opens com.example.core/com.example.core.internal=com.example.app
~~~

Cho phép deep reflection đối với package được chỉ định, trong phạm vi tùy chọn. Nó giải quyết vấn đề reflective access, không phải split package.

### 13.5. --module-path và --class-path

- **--module-path** khai báo nơi tìm named modules.
- **--class-path** khai báo các class/resource thuộc unnamed module.

Chuyển một JAR từ classpath sang module path có thể thay đổi hoàn toàn cách package được diễn giải. Ngược lại, chuyển JAR về classpath có thể tạm tránh một xung đột giữa named modules nhưng đổi các ràng buộc readability, access và service loading.

### 13.6. Bảng chọn nhanh

| Triệu chứng | Công cụ/cách xử lý phù hợp | Không nên dùng như lời giải |
|---|---|---|
| Hai module export cùng package cho app | Sửa package ownership hoặc dependency graph | Chỉ thêm --add-exports |
| Named module cần đọc code classpath | Thiết kế cầu nối hoặc --add-reads có kiểm soát | Tự động rename module |
| Reflection không truy cập được internal package | Thiết kế API/opens, có thể --add-opens | Relocate package khi chưa hiểu rủi ro |
| Test classes cần nằm trong package của module | Cấu hình test patch-module phù hợp | Tạo named test module split package |
| JAR shaded lặp package với dependency gốc | Bỏ bản trùng hoặc relocate implementation | Chỉ đổi Automatic-Module-Name |
| Class mới không được tìm thấy | Kiểm tra classpath/module path, module resolution và loader | Mặc định kết luận split package |

## 14. Ảnh hưởng đến tương thích nhị phân và consumer cũ

Khi đổi package, tên đầy đủ của class thay đổi:

~~~text
com.example.shared.Helper
             |
             v
com.example.alpha.Helper
~~~

Bytecode consumer cũ vẫn tham chiếu đến **com.example.shared.Helper**. Nếu bản mới không còn class với tên đó, JVM có thể không liên kết được. Vì vậy, đổi package có thể giải quyết JPMS nhưng lại tạo breaking change đối với consumer cũ.

### 14.1. Phân biệt migration nội bộ và public library

**Ứng dụng nội bộ:** nếu toàn bộ source và binary đều thuộc một nhóm kiểm soát, có thể refactor package và rebuild đồng thời, miễn test đầy đủ.

**Thư viện dùng chung:** cần quan tâm binary của consumer đã phát hành, plugin của đối tác, service loader, reflection, serialization và API signature.

Lộ trình cho thư viện public có thể bao gồm:

1. Công bố module structure mục tiêu.
2. Xác định package nào đổi.
3. Đánh dấu API cũ deprecated khi khả thi.
4. Cung cấp API/adapter mới.
5. Lưu bản tương thích chuyển tiếp nếu thiết kế cho phép.
6. Chạy binary consumer cũ với artifact mới.
7. Phát hành breaking change theo chính sách versioning được công bố.

Không phải mọi kiểu cũ đều có thể giữ cùng FQCN nếu nó tiếp tục gây split package. Một bridge class đặt trong package cũ cũng phải có một module chủ sở hữu hợp lệ.

### 14.2. Binary compatibility không đồng nghĩa JPMS compatibility

Một JAR mới có thể giữ nguyên mọi public method và class name, nhưng nếu việc đóng gói package thay đổi khiến module graph không resolve được, ứng dụng trên module path vẫn thất bại.

Ngược lại, việc sửa split package bằng cách đổi FQCN có thể tạo một module graph hợp lệ nhưng phá vỡ consumer đã biên dịch trước đó.

Do đó, acceptance criteria nên bao gồm cả:

- Binary API compatibility.
- Module graph resolution.
- Class loading.
- Service discovery.
- Runtime behavior và data compatibility.

## 15. Mô hình migration theo nhiều giai đoạn

Một lộ trình thực tế có thể thực hiện như sau:

~~~text
M0 — Baseline classpath
     Chốt JAR, dependency graph, plugin và test
                  |
                  v
M1 — Phân tích package ownership
     Liệt kê package, module name, source artifact
                  |
                  v
M2 — Thiết kế module graph
     Tách namespace hoặc gom package, xác định API
                  |
                  v
M3 — Chuyển dependency và module descriptors
     Explicit/automatic modules, requires/exports/opens
                  |
                  v
M4 — Tái hiện và xử lý lỗi
     Compile, validate modules, startup, plugin loading
                  |
                  v
M5 — Kiểm thử consumer và rollout
     Binary compatibility, runtime, rollback
~~~

Mỗi mốc cần có điều kiện đầu vào, bằng chứng và quyết định Go/No-Go.

### 15.1. Acceptance criteria mẫu

| Mã | Tiêu chí chấp nhận | Bằng chứng |
|---|---|---|
| AC-01 | Không còn package trùng giữa các named modules trong graph mục tiêu gây xung đột | Báo cáo package ownership và module graph |
| AC-02 | Module app compile thành công với đúng module path | CI compiler log |
| AC-03 | Module graph resolve và application khởi động được | Java launcher/smoke test |
| AC-04 | Không có dependency trùng hoặc bản JAR cũ ngoài kế hoạch | Dependency report và checksum |
| AC-05 | ServiceLoader, reflection, proxy và plugin chính hoạt động | Integration tests |
| AC-06 | Consumer cũ cần hỗ trợ vẫn liên kết và chạy | Test bằng binary consumer cũ |
| AC-07 | Không có regressions của hành vi quan trọng | Regression tests |
| AC-08 | Có rollback đối với packaging hoặc dependency migration | Diễn tập rollback và tài liệu release |

Nếu còn một workaround như **--patch-module** hoặc **--add-reads**, ghi rõ owner, lý do, test và điều kiện loại bỏ trước khi xem migration hoàn tất.

### 15.2. Test matrix cần có

| Môi trường | Classpath/module path | Mục đích |
|---|---|---|
| Baseline cũ | Classpath trước migration | Chụp hành vi hiện có |
| Compile mục tiêu | Module path theo thiết kế | Phát hiện reads-package conflict |
| Runtime mục tiêu | Cùng graph với production | Phát hiện lỗi resolution/layer |
| Test tích hợp | Module path + runtime integrations | Reflection, ServiceLoader, plugin |
| Consumer cũ | Binary cũ + JAR mới | Binary compatibility |
| Test fixtures | Cấu hình module test thực tế | Phát hiện package trùng do fixtures |
| Container/runtime image | Đúng JDK và artifact triển khai | Loại trừ lệch môi trường |

Không được chỉ chạy test trên classpath rồi kết luận module path đã hợp lệ.

## 16. Tình huống phân tích thực tế

Giả sử một ứng dụng có hai dependency:

~~~text
reporting-api.jar
  module com.example.reporting.api
  package com.example.reports
  class Report

reporting-extras.jar
  automatic module com.example.reporting.extras
  package com.example.reports
  class PdfReport
~~~

Trên classpath cũ, ứng dụng sử dụng cả **Report** và **PdfReport** bình thường. Khi chuyển lên module path, module app khai báo requires cả hai module. Cấu hình này có thể tạo lỗi **reads package com.example.reports from both ...**.

### 16.1. Phân tích nguyên nhân

- Hai module có tên khác nhau.
- Cả hai cùng chứa package **com.example.reports**.
- Automatic module extras không có descriptor viết tay, nhưng vẫn có package set.
- App đọc cùng package từ hai module.
- Không có vấn đề trùng tên class; xung đột ở mức package.

### 16.2. Phương án A: gom vào một module

Nếu hai artifact do cùng đội phát hành và có thể xuất bản chung, gom Report và PdfReport trong một named module **com.example.reporting**.

Ưu điểm: có thể giữ tên package cũ. Rủi ro: module name và dependency declarations của consumer cần cập nhật.

### 16.3. Phương án B: đổi package extras

Chuyển PdfReport sang:

~~~java
package com.example.reports.pdf;
~~~

và để extras export package mới. Ưu điểm: các artifact vẫn tách độc lập. Rủi ro: code cũ dùng **com.example.reports.PdfReport** phải migrate.

### 16.4. Phương án C: loại extras nếu không còn cần

Nếu PdfReport đã được tích hợp vào reporting-api bản mới, loại dependency extras. Nhưng phải kiểm tra không có consumer runtime đang dùng class chỉ có trong extras.

### 16.5. Lựa chọn

Không thể chọn phương án chỉ từ error message. Cần xét quyền sở hữu package, hợp đồng public API, lịch phát hành consumer và cách đảm bảo binary compatibility. Lộ trình được chấp nhận phải có test thực tế và chiến lược rollback.

## 17. Những ngộ nhận thường gặp

### “Hai JAR không có class cùng tên thì không bị split package.”

Sai. Chỉ cần chúng cùng có class thuộc một package, dù tên class khác nhau.

### “Đặt Automatic-Module-Name khác nhau là đủ.”

Sai. Module name khác nhau không đổi package bên trong JAR.

### “Thêm --add-exports hoặc --add-opens sẽ bỏ qua lỗi package trùng.”

Sai. Hai tùy chọn đó xử lý quyền truy cập/reflective access, không giải quyết sở hữu package hoặc xung đột module graph.

### “Bật classpath cho một JAR là đã sửa xong JPMS.”

Chưa chắc. Đó có thể là workaround, nhưng named module, unnamed module và class loader có ràng buộc riêng; cần xem xét lại readability, access và mục tiêu migration.

### “Lỗi NoClassDefFoundError luôn do split package.”

Sai. Nó có thể do thiếu class, lệch dependency, lỗi initialization hoặc class loading. Phải xem message và cause.

### “Nếu javac hết lỗi thì mọi plugin đều sẽ chạy.”

Sai. Reflection, ServiceLoader, generated proxy, serialization và plugin loader có thể lỗi ở runtime. Cần integration test trên artifact thật.

### “Đổi package chỉ là refactor source.”

Không đúng với consumer đã biên dịch. FQCN nằm trong bytecode, service configuration và có thể nằm trong serialized data. Đổi package có thể gây breaking change.

### “Một package có thể nằm ở nhiều module miễn là mỗi module export những class khác nhau.”

Export hoạt động theo **package**, không theo tập class chọn lọc. Không thể thiết kế module graph an toàn dựa trên giả định rằng app sẽ chọn class Alpha từ module A và class Beta cùng package từ module B trong một quan hệ đọc mơ hồ.

## 18. Checklist trước khi phát hành JPMS migration

### Package và artifact

- [ ] Đã liệt kê package trong mọi JAR trên module path mục tiêu.
- [ ] Đã phát hiện package trùng, duplicate class và shaded dependency.
- [ ] Đã xác định package owner hợp lý.
- [ ] Đã ghi module name của explicit và automatic module.
- [ ] Đã kiểm tra dependency trực tiếp và transitive.
- [ ] Đã kiểm tra generated sources, tests và fixtures.

### Module graph và class loader

- [ ] Đã ghi requires/exports/opens và root modules.
- [ ] Đã kiểm tra package được đọc từ một nguồn hợp lệ.
- [ ] Đã kiểm tra các module cùng loader/layer theo cấu hình runtime.
- [ ] Đã phân biệt named, automatic và unnamed modules.
- [ ] Đã xác định module path/classpath chính xác của CI và production.
- [ ] Đã xác minh plugin API không bị nhân bản qua loader.

### Cách xử lý

- [ ] Đã chọn gom package, đổi namespace, loại dependency hoặc phương án chuyển tiếp có lý do.
- [ ] Không dùng --add-exports/--add-opens như lời giải giả cho split package.
- [ ] Nếu dùng --patch-module, có owner và phạm vi rõ ràng.
- [ ] Đã đánh giá breaking change khi đổi FQCN.
- [ ] Đã cập nhật module descriptors và dependency versions.
- [ ] Đã cập nhật hướng dẫn migration cho consumer.

### Kiểm thử và bằng chứng

- [ ] Module app compile và resolve thành công.
- [ ] Application khởi động trên đúng JDK và module path.
- [ ] Reflection, ServiceLoader, proxy và plugin paths đã được chạy.
- [ ] Consumer cũ cần hỗ trợ đã được thử bằng binary gốc.
- [ ] Đã xác minh class/resource thực sự được nạp từ artifact nào khi cần.
- [ ] Đã có integration/regression tests và rollback plan.
- [ ] Đã lưu log, checksum và danh sách module/package mục tiêu.

## 19. Tài liệu chuẩn nên tham khảo

Khi xử lý các trường hợp đặc biệt, ưu tiên tài liệu Java SE và JPMS của release mục tiêu:

- **JEP 261 — Module System:** https://openjdk.org/jeps/261
- **Java Platform Module System specification:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- **Java SE tools documentation** cho **java**, **javac**, **jar** và **jdeps** của JDK đang triển khai.
- **java.lang.module** API, gồm ModuleFinder, Configuration, Resolver và ModuleLayer, để hiểu quy trình tìm, resolve và định nghĩa modules.

Tài liệu của Gradle/Maven và vendor dependency bổ sung cách cấu hình module path, nhưng không thay thế quy tắc của Java module system.

---

**Kết luận:** Split package là dấu hiệu ranh giới đóng gói cũ chưa phù hợp với ownership ở mức JPMS module. Vấn đề không chỉ là trùng class name; hai module cùng chứa các class khác nhau trong cùng package cũng có thể khiến module graph hoặc module layer không hợp lệ. Cách sửa bền vững là xác định **một nơi sở hữu package**, điều chỉnh dependency và public API có chủ đích, rồi kiểm tra trên đúng compiler, module path, runtime và consumer thực tế.
