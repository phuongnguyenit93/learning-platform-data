# Module path và cách module được phân giải

Trong Java Platform Module System (JPMS), **module path** là nơi công cụ Java tìm các named module. Tuy nhiên, việc một modular JAR nằm trên module path không có nghĩa module ấy tự động xuất hiện trong ứng dụng đang chạy. Trước khi thực thi mã, Java cần chọn **root modules**, lần theo các dependency và tạo một **module graph** hợp lệ. Quá trình này được gọi là **module resolution**.

Hiểu module path và resolution giúp giải thích những tình huống thường gặp: JAR đã ở đúng thư mục nhưng Java vẫn báo module not found; một module được tìm thấy nhưng không thể truy cập package của module khác; thư viện chuyển từ classpath sang module path bỗng xuất hiện xung đột package; hoặc plugin chưa được phân giải dù JAR tồn tại.

Bài học này giới thiệu các khái niệm cốt lõi, một ví dụ build và chạy có thể thực hành, cách root modules và requires quyết định module graph, sự khác biệt giữa readability với package access, cùng công cụ kiểm tra và chẩn đoán cấu hình.

## 1. Phân biệt classpath và module path

Hai đường tìm kiếm có vai trò khác nhau:

| Khía cạnh | Classpath | Module path |
| --- | --- | --- |
| Tùy chọn phổ biến | --class-path hoặc -cp | --module-path hoặc -p |
| Đơn vị tìm kiếm | Class và resource | Module và module descriptor |
| Mô hình module | Unnamed module của class loader tương ứng | Named modules |
| Dependency | Không khai báo requires ở cấp JAR | Explicit module dùng requires trong descriptor |
| Encapsulation | Không có ranh giới named module giữa các JAR trên cùng classpath | exports và opens kiểm soát truy cập package |
| Lựa chọn để chạy | Class main theo tên đầy đủ | Module chính và class main qua -m |
| Rủi ro nổi bật | Trùng class, thứ tự classpath và dependency ngầm | Thiếu module, xung đột resolution, split package, quyền access |

Ví dụ chạy ứng dụng truyền thống:

~~~bash
java --class-path "out:libs/*" com.example.app.Main
~~~

Ví dụ chạy một named module:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Trên Windows, các entry trong một đường dẫn gồm nhiều thành phần thường phân cách bằng dấu chấm phẩy **;** thay vì dấu hai chấm **:** của Linux/macOS. Một thư mục chứa nhiều modular JAR có thể được truyền như một entry module path.

Classpath và module path có thể cùng tồn tại trong một lần khởi chạy. Khi đó các class thuộc JAR trên classpath nằm trong unnamed module, còn các module được chọn trên module path tham gia named module graph.

## 2. Module path là nơi tìm module, không phải danh sách module phải chạy

Giả sử có:

~~~text
project/
└── mods/
    ├── com.example.app.jar
    ├── com.example.catalog.jar
    ├── com.example.audit.jar
    └── com.example.metrics.jar
~~~

Với lệnh:

~~~bash
java -p mods -m com.example.app/com.example.app.Main
~~~

Java có thể tìm thấy các module trong thư mục mods. Nhưng Java không có nghĩa vụ đưa cả bốn module vào module graph chỉ vì bốn JAR cùng nằm trong thư mục đó.

Nếu module app khai báo dependency trực tiếp đến catalog:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

thì ít nhất app, catalog và những dependency bắt buộc của chúng phải được xem xét để phân giải. Audit và metrics có thể vẫn là module **observable** nhưng không thuộc cấu hình được chọn nếu không có root hoặc dependency khác kéo chúng vào.

Đó là lý do cần tách ba câu hỏi:

1. Java có **tìm thấy descriptor** của module không?
2. Module có được **chọn để phân giải** cùng root và dependency không?
3. Một module consumer có **quyền đọc và truy cập package** cần sử dụng không?

Một câu trả lời "có" cho câu đầu không đủ để suy ra hai câu sau.

## 3. Ba khái niệm: observable, root và resolved modules

**Observable modules** là các module mà cơ chế tìm kiếm có thể quan sát được trong môi trường phân giải, thường gồm module của runtime image và module trên các đường module path được cấu hình.

**Root modules** là các module đầu vào của quá trình resolution. Khi chạy ứng dụng bằng **-m**, module chứa class main là một root. Có thể bổ sung root bằng **--add-modules**.

**Resolved modules** là tập module được chọn sau khi JPMS đi từ roots, tìm các dependency bắt buộc và kiểm tra tính hợp lệ của configuration.

Ví dụ:

~~~text
Observable modules:
    com.example.app
    com.example.catalog
    com.example.audit
    com.example.metrics
    java.base
    java.logging

Root:
    com.example.app

Dependencies:
    com.example.app -> com.example.catalog
    com.example.catalog -> java.logging
    tất cả module thông thường -> java.base ngầm định
~~~

Trong trường hợp chỉ có các quan hệ nêu trên, module graph được phân giải chứa app, catalog, java.logging và java.base; audit và metrics không tự tham gia.

Trong thực tế, một số cơ chế khác như service binding hoặc root bổ sung có thể làm tập resolved modules rộng hơn; nên kiểm tra bằng **--show-module-resolution** thay vì suy đoán từ số JAR.

## 4. module-info.java quyết định dependency của explicit module

Explicit named module có file **module-info.java** nằm ở gốc source của module:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Descriptor được compiler biên dịch thành **module-info.class**. Khi module được đóng gói thành modular JAR, file này nằm ở gốc JAR.

Các directive quan trọng:

| Directive | Tác dụng chính |
| --- | --- |
| requires M | Module hiện tại cần đọc module M |
| requires transitive M | Module hiện tại đọc M và truyền readability của M tới các module đọc module hiện tại |
| requires static M | Dependency cần khi biên dịch nhưng có thể tùy chọn ở runtime |
| exports p | Công bố package p cho các module khác có quan hệ đọc phù hợp |
| exports p to M | Chỉ export package p cho một số module được nêu |
| opens p | Mở package p cho deep reflection |
| opens p to M | Chỉ mở package p cho module được nêu |
| uses S | Module là consumer của service S |
| provides S with I | Module cung cấp implementation I cho service S |

**requires** ảnh hưởng trực tiếp đến việc tìm dependency trong resolution. **exports** và **opens** chủ yếu quyết định quyền truy cập package; chúng không được dùng thay cho requires.

Mọi ordinary named module có quan hệ đọc ngầm định tới **java.base**; không cần khai báo requires java.base trong module-info.java.

## 5. Ví dụ hoàn chỉnh với hai module

Tạo source tree:

~~~text
module-demo/
└── src/
    ├── com.example.catalog/
    │   ├── module-info.java
    │   └── com/example/catalog/api/Book.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Descriptor catalog:

~~~java
// src/com.example.catalog/module-info.java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Class catalog:

~~~java
// src/com.example.catalog/com/example/catalog/api/Book.java
package com.example.catalog.api;

public record Book(String title) {
}
~~~

Descriptor app:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.catalog;
}
~~~

Class main:

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.catalog.api.Book;

public final class Main {
    public static void main(String[] args) {
        Book book = new Book("Effective Modular Java");
        System.out.println(book.title());
    }
}
~~~

Đây là hai explicit named modules: catalog cung cấp API và app tiêu thụ API. Module app khai báo **requires**, còn catalog khai báo **exports** để app sử dụng class Book.

## 6. Biên dịch theo module source path

Đứng tại thư mục module-demo, chạy:

~~~bash
javac \
  --module-source-path src \
  -d mods \
  -m com.example.catalog,com.example.app
~~~

Giải thích:

- **--module-source-path src** cho javac biết source được tổ chức theo thư mục module.
- **-d mods** chọn thư mục output.
- **-m** chỉ định các module source cần biên dịch.

Sau khi biên dịch, kết quả thường có dạng:

~~~text
mods/
├── com.example.catalog/
│   ├── module-info.class
│   └── com/example/catalog/api/Book.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Mỗi thư mục con là một **exploded module**: module đã biên dịch nhưng chưa được đóng gói JAR. Java launcher có thể sử dụng chúng trên module path.

Chạy ứng dụng:

~~~bash
java \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Effective Modular Java
~~~

Java lấy com.example.app làm root, thấy descriptor của app yêu cầu com.example.catalog và phân giải catalog cùng các module hệ thống cần thiết. Vì package api đã được catalog export, Main có thể dùng Book.

## 7. Đóng gói thành modular JAR

Nếu cần phân phối JAR, có thể đóng gói hai exploded modules:

~~~bash
mkdir -p dist
~~~

~~~bash
jar --create \
    --file dist/com.example.catalog.jar \
    -C mods/com.example.catalog .
~~~

~~~bash
jar --create \
    --file dist/com.example.app.jar \
    -C mods/com.example.app .
~~~

Kiểm tra descriptor trong artifact:

~~~bash
jar --describe-module \
    --file dist/com.example.catalog.jar
~~~

~~~bash
jar --describe-module \
    --file dist/com.example.app.jar
~~~

Sau đó chạy:

~~~bash
java -p dist \
     -m com.example.app/com.example.app.Main
~~~

Tên file JAR có thể khác tên module. Với explicit module, tên trong module-info.class mới là danh tính được JPMS dùng để phân giải **requires** và tên module truyền vào **-m**.

Đảm bảo mỗi modular JAR chứa module-info.class ở gốc. Nếu build vô tình bỏ file này, JAR sẽ không còn được nhận diện như explicit named module như dự định.

## 8. Resolution diễn ra theo các bước nào?

Với lệnh:

~~~bash
java --module-path dist \
     -m com.example.app/com.example.app.Main
~~~

quá trình ở mức khái niệm là:

1. **Xây dựng nguồn module quan sát được.** Java có thể tìm module hệ thống và module từ đường dẫn được cấu hình.
2. **Xác định root modules.** Module com.example.app là root vì nó được chọn bằng -m; có thể có roots bổ sung.
3. **Tìm descriptor của root.** Java lấy thông tin dependency từ module-info.class.
4. **Theo các requires bắt buộc.** Nếu app yêu cầu catalog thì catalog phải được tìm thấy trong cấu hình có thể phân giải.
5. **Phân giải tiếp dependency bắc cầu.** Nếu catalog yêu cầu module khác, resolution tiếp tục tìm module đó.
6. **Kiểm tra các ràng buộc module.** Module system phát hiện một số xung đột về dependency, readability và package.
7. **Tạo configuration hợp lệ.** Các module đã phân giải có thể được định nghĩa trong runtime layer.
8. **Bắt đầu thực thi class main.** Class loading và initialization thực tế diễn ra theo nhu cầu của JVM.

Đây là mô hình khái quát; cơ chế chính xác còn tùy Java launcher, root selection, service binding và cấu hình cha.

Điều quan trọng là **resolution ở cấp module không đồng nghĩa JVM đã nạp tất cả class** trong mọi JAR được phân giải.

## 9. Readability khác với exports

Một module được phép **đọc** module khác chưa chắc đã sử dụng được tất cả class public của module đó.

Giả sử catalog khai báo:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Trong catalog có thêm package:

~~~text
com.example.catalog.internal
~~~

Module app khai báo:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Lúc này:

- App đọc được module catalog.
- App truy cập được các kiểu public trong **com.example.catalog.api**.
- App không được import các kiểu trong **com.example.catalog.internal** như một API thông thường vì package chưa export.

Đó là hai lớp kiểm soát:

~~~text
requires -> module readability
exports  -> package accessibility
~~~

Thêm catalog lên module path hoặc thêm catalog làm root không tự thay đổi exports của catalog. Nếu source app import package internal, javac có thể báo **package ... is not visible** dù resolution tìm đủ module.

Nếu framework cần reflection sâu, cần xem **opens**, vốn khác với exports. Không nên sửa lỗi module not found bằng opens, hoặc sửa lỗi thiếu quyền truy cập package bằng cách chỉ thêm --module-path.

## 10. requires transitive và quan hệ đọc truyền tiếp

Giả sử có ba module:

~~~text
com.example.app
     |
     v
com.example.service
     |
     v
com.example.catalog
~~~

Nếu service khai báo:

~~~java
module com.example.service {
    requires com.example.catalog;
    exports com.example.service.api;
}
~~~

App yêu cầu service:

~~~java
module com.example.app {
    requires com.example.service;
}
~~~

Catalog được phân giải vì service cần nó, nhưng app không mặc nhiên được quyền đọc trực tiếp catalog chỉ nhờ chuỗi requires thông thường.

Nếu public API của service đưa kiểu Book từ catalog vào method signature, service có thể khai báo:

~~~java
module com.example.service {
    requires transitive com.example.catalog;
    exports com.example.service.api;
}
~~~

Khi app đọc service, quan hệ readability tới catalog có thể được suy ra qua requires transitive. Điều này hữu ích khi dependency là một phần của API công khai mà consumer cần nhìn thấy.

Lưu ý: **requires transitive** truyền readability, không tự export package nội bộ của catalog. Catalog vẫn cần export package chứa kiểu API mà app sử dụng.

## 11. requires static và dependency tùy chọn tại runtime

Với dependency chỉ cần lúc biên dịch hoặc có khả năng vắng mặt khi chạy:

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

**requires static** cho phép biên dịch dựa trên module annotations nhưng không buộc runtime luôn phải phân giải module ấy chỉ vì directive này.

Nếu runtime có một đường code thực sự dùng class thuộc dependency tùy chọn, ứng dụng vẫn cần bảo đảm module và class đó có thể truy cập được khi thực thi. Chỉ viết requires static không bảo đảm mọi tình huống runtime đều chạy khi module vắng mặt.

Tùy mục đích, có thể đưa module tùy chọn vào graph bằng root bổ sung hoặc vì dependency khác yêu cầu nó. Nên thiết kế đường code fallback rõ ràng khi chức năng tùy chọn không sẵn có.

Điểm khác nhau:

- **requires M**: dependency bắt buộc cần được đáp ứng trong resolution.
- **requires transitive M**: dependency bắt buộc và truyền readability tới consumer.
- **requires static M**: cần khi compile nhưng không bắt buộc phải có khi runtime resolution chỉ dựa vào directive đó.

## 12. --add-modules bổ sung root modules

Giả sử thư mục dist còn có:

~~~text
com.example.audit.jar
~~~

Module audit là observable nhưng không được app hoặc catalog requires. Nếu muốn đưa audit vào boot layer ngay lúc khởi chạy:

~~~bash
java --module-path dist \
     --add-modules com.example.audit \
     -m com.example.app/com.example.app.Main
~~~

Tùy chọn **--add-modules** yêu cầu JPMS coi audit là root bổ sung. Các dependency của audit được phân giải theo descriptor của nó.

Có thể chỉ định nhiều module:

~~~bash
--add-modules com.example.audit,com.example.metrics
~~~

Nhưng **--add-modules không có nghĩa app tự động đọc audit**. Quan hệ reads và quyền package access vẫn tuân theo descriptor/module graph. Nếu mã của app cần import API từ audit, cách khai báo dependency bền vững thường là requires com.example.audit.

Một số giá trị đặc biệt:

| Giá trị | Ý nghĩa |
| --- | --- |
| ALL-DEFAULT | Bổ sung nhóm module gốc mặc định do launcher xác định |
| ALL-SYSTEM | Bổ sung các module hệ thống quan sát được làm roots |
| ALL-MODULE-PATH | Bổ sung toàn bộ module quan sát được trên application module path làm roots |

Ví dụ:

~~~bash
java -p dist \
     --add-modules ALL-MODULE-PATH \
     -m com.example.app/com.example.app.Main
~~~

Không nên lạm dụng ALL-MODULE-PATH chỉ để giải quyết lỗi module thiếu. Việc đưa quá nhiều module vào graph có thể làm lộ dependency không tương thích hoặc xung đột package vốn không xảy ra khi chỉ phân giải module cần thiết.

## 13. --limit-modules giới hạn tập observable modules

Ngoài thêm root, Java launcher còn hỗ trợ **--limit-modules** để giới hạn tập module quan sát được.

Ví dụ khái quát:

~~~bash
java -p dist \
     --limit-modules java.base,com.example.app \
     -m com.example.app/com.example.app.Main
~~~

Tùy chọn này không chỉ giới hạn ở đúng hai tên được ghi. Java còn xét các dependency cần thiết theo quy tắc của nó để hình thành tập module quan sát được đã giới hạn.

Nếu ứng dụng cần một module nằm ngoài tập còn quan sát được, resolution có thể báo module not found ngay cả khi artifact vật lý tồn tại trên module path.

Do đó, khi debug lỗi thiếu module, cần kiểm tra cả module path, --add-modules và --limit-modules. Một lệnh chạy hoặc container entrypoint có thể đặt giới hạn module khác với môi trường IDE.

## 14. Automatic module trên module path

Không phải mọi JAR trên module path đều có file module-info.class. Với JAR không modular hóa nhưng được đặt trên module path, JPMS có thể nhận diện JAR đó thành **automatic module**.

Tên automatic module được lấy từ:

1. Thuộc tính manifest **Automatic-Module-Name**, nếu có và hợp lệ.
2. Hoặc quy tắc suy ra tên từ tên JAR.

Ví dụ một thư viện legacy:

~~~text
dist/legacy-json-2.0.jar
~~~

Nếu được nhận diện như automatic module mang tên **legacy.json**, explicit module khác có thể viết:

~~~java
module com.example.app {
    requires legacy.json;
}
~~~

Tên chính xác phải được xác nhận từ artifact:

~~~bash
jar --describe-module \
    --file dist/legacy-json-2.0.jar
~~~

Automatic module giúp thư viện cũ tham gia module graph trong giai đoạn chuyển đổi. Nó thường export các package của mình và có hành vi tương thích với mã chưa modular hóa.

Tuy nhiên, automatic module không thay thế descriptor explicit được thiết kế rõ ràng. Việc chuyển nhiều JAR legacy lên module path cùng lúc có thể gây xung đột package hoặc phụ thuộc chưa được tổ chức tốt.

## 15. Unnamed module trên classpath không được requires trực tiếp

Một JAR chưa modular hóa đặt trên **classpath** thuộc unnamed module của class loader tương ứng. Named module không thể khai báo:

~~~java
module com.example.app {
    requires ALL-UNNAMED;
}
~~~

Vì ALL-UNNAMED không phải tên module hợp lệ trong directive requires.

Trong giai đoạn migration, có thể tạm dùng:

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

khi module app cần tham chiếu thư viện classpath, đồng thời cấu hình classpath cho thư viện đó. Tùy chọn add-reads có thể cần ở compile-time và runtime tùy mã được biên dịch và chạy.

Ví dụ chạy:

~~~bash
java --module-path mods \
     --class-path "libs/*" \
     --add-reads com.example.app=ALL-UNNAMED \
     -m com.example.app/com.example.app.Main
~~~

Đây là giải pháp tương thích có kiểm soát, không phải thay thế lâu dài cho việc khai báo dependency rõ ràng. Thư viện được chuyển thành automatic hoặc explicit named module sẽ có danh tính module riêng; khi đó nên điều chỉnh module descriptor phù hợp.

## 16. Resolution và service binding

Module có thể khai báo service consumer:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.ReportProvider;
}
~~~

Một provider module:

~~~java
module com.example.report.csv {
    requires com.example.spi;
    provides com.example.spi.ReportProvider
        with com.example.report.csv.CsvReportProvider;
}
~~~

JPMS có cơ chế service binding giúp tìm thêm các provider module phù hợp trong một số quá trình resolution. Trong API lập trình, **Configuration.resolveAndBind** minh họa rõ điều này: ngoài dependency requires, quá trình còn có thể tìm module cung cấp service.

Do đó, không nên khẳng định module provider chỉ có thể xuất hiện trong graph khi có requires trực tiếp hoặc --add-modules. Trong một cấu hình có service binding, nó có thể được đưa vào vì vai trò provider.

Khi ứng dụng dùng ServiceLoader:

~~~java
ServiceLoader<ReportProvider> loader =
    ServiceLoader.load(ReportProvider.class);

for (ReportProvider provider : loader) {
    System.out.println(provider.getClass().getName());
}
~~~

nó cần bảo đảm service contract và module provider được cấu hình đúng. Nhưng việc module provider đã được phân giải không có nghĩa mọi provider instance đã được tạo: class loading và provider instantiation là công việc diễn ra sau theo nhu cầu sử dụng.

## 17. Module graph khác ClassLoader và class loading

Module resolution xác định tập module và quan hệ đọc. Quá trình nạp từng class diễn ra khi JVM cần sử dụng class đó.

Luồng khái quát:

~~~text
module path
    |
    v
Tìm module descriptor
    |
    v
Chọn roots và phân giải requires
    |
    v
Configuration / module graph
    |
    v
ModuleLayer định nghĩa module runtime
    |
    v
ClassLoader nạp class cụ thể khi cần
    |
    v
Linking và initialization theo quy tắc JVM
~~~

Một module đã được phân giải có thể chứa hàng trăm class chưa từng được ứng dụng sử dụng. Ngược lại, một lỗi NoClassDefFoundError có thể xuất hiện muộn khi ứng dụng lần đầu cần class dependency không sẵn có, dù phần resolution ban đầu đã thành công.

Với custom plugin layer, các API **ModuleFinder**, **Configuration** và **ModuleLayer** cho phép ứng dụng chủ động tạo module graph khác với boot layer. Tuy nhiên, --module-path của Java launcher không tự tạo một layer độc lập cho từng JAR.

## 18. Các lỗi thường gặp và cách xác định nguyên nhân

**Module not found**

Ví dụ:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.catalog not found,
required by com.example.app
~~~

Cần kiểm tra tên module thật trong module-info.class, vị trí artifact trên module path, tên file JAR và dependency requires. Module chưa được tìm thấy là vấn đề khác với package chưa export.

**Package is not visible**

Module đã tìm thấy nhưng consumer không đọc được module sở hữu package hoặc package chưa được export cho consumer. Kiểm tra requires rồi exports/qualified exports.

**Reads package ... from both ...**

Một module đọc cùng package từ hai module export khác nhau. Đây là xung đột split package trong module graph. Kiểm tra các JAR chứa package trùng, đặc biệt khi chuyển nhiều automatic modules lên module path.

**Module có trong thư mục mods nhưng không ở boot layer**

Module có thể chỉ observable và chưa được chọn làm root/dependency/provider cần thiết. Dùng --show-module-resolution và kiểm tra roots; không tự suy rằng module phải xuất hiện chỉ vì JAR hiện diện.

**Java chạy được trong IDE nhưng không chạy trên terminal**

IDE có thể tự thêm module path, --add-modules, classpath hoặc --add-reads. So sánh command line thực tế giữa hai môi trường.

**NoClassDefFoundError sau khi resolution thành công**

Kiểm tra dependency runtime, version library, class loader và code path lần đầu sử dụng class. Đây thường là lỗi ở tầng class loading/linking, không nhất thiết là lỗi tìm descriptor.

**Framework reflection bị chặn**

Nếu lỗi là InaccessibleObjectException, xem package có được opens đúng module framework không. Exports không tự cho phép deep reflection vào private field.

## 19. Công cụ quan sát module path và resolution

### Kiểm tra descriptor của JAR

~~~bash
jar --describe-module \
    --file dist/com.example.catalog.jar
~~~

Lệnh này cho biết tên module, requires, exports và thông tin descriptor liên quan.

### Liệt kê các module có thể quan sát

~~~bash
java --module-path dist --list-modules
~~~

Lệnh này giúp xác nhận module có thể được tìm thấy; nó không phải danh sách tất cả module chắc chắn đã được phân giải cho một lần chạy ứng dụng.

### Hiển thị quá trình resolution

~~~bash
java --show-module-resolution \
     --module-path dist \
     -m com.example.app/com.example.app.Main
~~~

Có thể so sánh hai lệnh có và không có --add-modules để thấy module nào được thêm vào graph và dependency nào được chọn.

### Kiểm tra module trong boot layer

~~~java
ModuleLayer boot = ModuleLayer.boot();

boot.modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
~~~

Hoặc kiểm tra module cụ thể:

~~~java
boolean catalogResolved =
    boot.findModule("com.example.catalog").isPresent();

System.out.println("Catalog in boot layer: " + catalogResolved);
~~~

**ModuleLayer.findModule** trả về kết quả từ runtime layer; không đơn thuần kiểm tra sự tồn tại của một JAR trên ổ đĩa.

### Phân tích dependency với jdeps

~~~bash
jdeps --module-path dist \
      --module com.example.app
~~~

jdeps giúp xem dependency ở cấp class/module. Kết quả phân tích bytecode nên được kết hợp với module descriptor và lệnh chạy thực tế, nhất là khi ứng dụng nạp class hoặc service bằng reflection.

## 20. Quy trình debug có thứ tự

Khi gặp lỗi lúc chuyển sang module path, làm theo thứ tự:

1. Ghi lại JDK version, lệnh javac/java và toàn bộ JVM arguments.
2. Kiểm tra JAR nằm trên classpath hay module path.
3. Dùng jar --describe-module xác nhận tên module thực tế.
4. Kiểm tra root module được chọn bằng -m và các roots do --add-modules bổ sung.
5. Dùng --list-modules để xác nhận module có thể quan sát được.
6. Dùng --show-module-resolution để xem module graph thực sự.
7. Đọc requires, requires transitive và requires static trong descriptor.
8. Nếu resolution đã qua nhưng compiler báo package không visible, kiểm tra readability và exports.
9. Nếu framework reflection lỗi, kiểm tra opens đúng module caller.
10. Nếu class loading lỗi, kiểm tra class loader, dependency runtime và log class loading.
11. Khi dùng automatic module, kiểm tra package trùng và tên module suy ra.
12. Xác minh kết quả trên JDK, build artifact và lệnh chạy tương đương production.

Một bảng giúp phân loại nhanh:

| Hiện tượng | Tầng cần xem đầu tiên |
| --- | --- |
| Module not found | Module discovery và resolution |
| Resolved module không có trong boot layer | Root selection hoặc runtime configuration |
| Package is not visible | Readability và exports |
| Reflection bị chặn | opens và module identity của caller |
| ClassNotFoundException | ClassLoader và classpath/module path |
| NoClassDefFoundError | Runtime dependency và linking |
| Split package conflict | Dependency graph và package ownership |

## 21. Bài tập củng cố

Từ dự án hai module ở phần trên:

1. Chạy ứng dụng với --module-path và -m; xác nhận dòng tiêu đề sách được in ra.
2. Dùng --show-module-resolution xác định các module đã được chọn.
3. Tạo module com.example.audit độc lập, đặt artifact lên module path và kiểm tra module có xuất hiện trong boot layer không.
4. Thử --add-modules com.example.audit, rồi quan sát sự khác biệt.
5. Xóa **requires com.example.catalog** khỏi descriptor app nhưng vẫn giữ import Book; quan sát thông báo javac.
6. Khôi phục requires, rồi xóa exports của package api trong catalog; so sánh lỗi với bước 5.
7. Tạo module service có requires transitive tới catalog và kiểm tra tác động tới consumer.
8. Thử dùng một JAR không có module-info.class trên module path; xác nhận tên automatic module bằng jar --describe-module.
9. Đặt một JAR legacy trên classpath và phân biệt hành vi unnamed module với automatic module.
10. Ghi lại lệnh nào thay đổi tập observable modules, lệnh nào thêm root và khai báo nào kiểm soát quyền truy cập package.

**Module path không phải danh sách lệnh tải mọi module vào JVM.** Nó là nguồn tìm module để JPMS tạo một cấu hình hợp lệ từ root modules và dependency. Khi phân biệt rõ observable modules, root selection, resolution, readability và package access, bạn có thể cấu hình ứng dụng modular chính xác hơn, xử lý lỗi dependency nhanh hơn và chuyển đổi thư viện classpath sang JPMS một cách có kiểm soát.