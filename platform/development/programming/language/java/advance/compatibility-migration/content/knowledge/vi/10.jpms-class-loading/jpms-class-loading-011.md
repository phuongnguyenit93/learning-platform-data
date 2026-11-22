# Chuyển dần dependency từ class path sang module path

Khi một ứng dụng Java lâu năm bắt đầu sử dụng Java Platform Module System (JPMS), việc chuyển toàn bộ thư viện từ **class path** sang **module path** trong một lần thường không thực tế. Ứng dụng có thể phụ thuộc vào hàng chục JAR, framework sử dụng reflection, thư viện chưa có `module-info.class`, công cụ sinh mã, Java agent, hoặc plugin được nạp bằng class loader riêng. Một số JAR có package trùng nhau; số khác dựa vào việc mọi class trên classpath nhìn thấy nhau mà không cần khai báo quan hệ phụ thuộc.

JPMS cho phép **di chuyển từng bước** từ mô hình classpath truyền thống sang một đồ thị named modules rõ ràng. Việc triển khai từng bước cần hiểu giới hạn giữa unnamed module, automatic module và explicit named module, đồng thời kiểm tra không chỉ biên dịch mà cả class loading, resource loading, reflection, service discovery, đóng gói và khả năng rollback.

Bài học này trình bày một lộ trình chuyển đổi có thể áp dụng cho dự án thư viện hoặc ứng dụng, kèm ví dụ cấu hình, lệnh kiểm tra và các tiêu chí quyết định khi nào nên chuyển một dependency.

## 1. Mục tiêu của quá trình chuyển đổi

**Classpath** là tập hợp vị trí chứa class và resource được JVM hoặc compiler tìm kiếm theo cơ chế class loader. Trong mô hình truyền thống, các JAR của ứng dụng thường được đặt cùng một classpath. Điều này thuận tiện cho các thư viện cũ nhưng không biểu diễn trực tiếp hợp đồng module, ranh giới API, quyền truy cập và các phụ thuộc cần thiết.

**Module path** là nơi JPMS tìm các module để xây dựng một cấu hình module. Mỗi named module có tên riêng, nhóm package và tập khai báo về những module mà nó đọc, package được export, package được open, cùng service được sử dụng/cung cấp.

Mục tiêu chuyển đổi nên cụ thể:

- Giữ hệ thống đang chạy ổn định trong quá trình đổi cách tổ chức dependency.
- Chuyển từng artifact theo mức sẵn sàng thay vì buộc mọi thư viện phải modularize đồng thời.
- Xác định chính xác API công khai qua `exports` và nhu cầu reflection qua `opens`.
- Phát hiện sớm xung đột module name, package trùng, dependency bị ẩn và class loader bất thường.
- Giữ khả năng hỗ trợ plugin, service provider và dữ liệu tài nguyên.
- Kiểm tra các tổ hợp classpath/module path có thể thực sự xuất hiện khi triển khai.
- Gỡ dần cờ JVM workaround khi thư viện và framework đã hỗ trợ JPMS tốt hơn.

Không nên coi “mọi JAR xuất hiện trên module path” là mục tiêu cuối cùng. Điều cần đạt là một cấu hình runtime có hợp đồng rõ ràng, được hỗ trợ và kiểm chứng, không phải chỉ đổi dấu phân cách trong lệnh `java`.

## 2. Ba loại module cần phân biệt

### 2.1. Unnamed module: mô hình classpath

Mã được nạp từ classpath thường thuộc **unnamed module** của defining class loader. Unnamed module không có tên để các explicit named module khai báo bằng `requires`. Nó có các đặc điểm thuận tiện cho tương thích với mã cũ, nhưng không mang cấu trúc khai báo tường minh của JPMS.

Ví dụ ứng dụng truyền thống:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

Trong ví dụ trên, `app.jar` và các JAR ở thư mục `lib` cùng tham gia classpath của application class loader. Dấu phân tách classpath trên Windows là dấu `;` thay vì `:`.

Ưu điểm là dễ chạy mã cũ. Hạn chế là các phụ thuộc và quyền nhìn thấy type thường không được mô hình hóa qua module descriptor. Thứ tự classpath và cách class loader tìm tài nguyên có thể ảnh hưởng kết quả, nhất là khi có nhiều phiên bản cùng một thư viện.

### 2.2. Automatic module: bước đệm từ JAR chưa modularize

Một JAR thông thường **không có module descriptor** nhưng được đặt trên module path có thể trở thành **automatic module**. JPMS suy ra module name theo metadata hoặc quy tắc tên file. Automatic module giúp một dependency cũ tham gia module graph mà không cần nhà cung cấp lập tức phát hành `module-info.java`.

Automatic module thường export các package của nó và có cơ chế đọc module mang tính chuyển tiếp, nhằm giảm rào cản khi đưa thư viện classpath cũ vào hệ thống modular. Tuy nhiên, điều đó **không biến thư viện thành explicit module đã được thiết kế kỹ**, cũng không giải quyết tự động tất cả vấn đề package, reflection, service loading và runtime.

Ví dụ:

~~~text
lib/
  payment-client-2.7.1.jar     # chưa có module-info.class
  json-codec-1.9.jar           # chưa có module-info.class
~~~

Khi đặt trên module path, mỗi JAR có thể được coi là một automatic module với module name xác định theo quy tắc của JVM.

Các rủi ro cần kiểm tra:

- Module name suy ra từ tên file có thể thay đổi khi đổi cách đặt tên artifact.
- Module name có thể không khớp tên nhà cung cấp dự kiến dùng khi phát hành explicit module.
- Package trùng nhau trong module graph có thể làm cấu hình không hợp lệ.
- Một JAR “chạy được trên classpath” chưa chắc hoạt động đúng khi trở thành automatic module.
- Cách module được resolve và loader được chọn có thể khiến resource/service không xuất hiện như mong muốn.

Automatic module là **cầu nối**, không phải bảo đảm rằng mọi binary cũ đã sẵn sàng cho kiến trúc modular.

### 2.3. Explicit named module: module khai báo đầy đủ

Một explicit named module có `module-info.java` trong source và `module-info.class` trong artifact đã biên dịch. Ví dụ:

~~~java
module com.acme.order.core {
    requires java.sql;
    requires com.acme.order.api;

    exports com.acme.order.core.publicapi;
    opens com.acme.order.core.entities
        to org.hibernate.orm.core;

    uses com.acme.order.spi.AuditSink;
}
~~~

Đây là ví dụ minh họa; tên module của Hibernate và mọi dependency khác phải được kiểm tra từ artifact/version thực tế trước khi dùng nguyên văn.

Các khai báo quan trọng:

| Khai báo | Tác dụng |
|---|---|
| `requires m;` | Module hiện tại đọc module `m` |
| `requires transitive m;` | Quan hệ đọc module `m` được lan truyền tới module đọc module hiện tại theo quy tắc JPMS |
| `requires static m;` | Phụ thuộc cần tại compile time nhưng có thể vắng mặt tại runtime |
| `exports p;` | Công khai public types của package `p` tới những module đọc được module này |
| `exports p to m;` | Export package `p` có điều kiện tới module `m` |
| `opens p;` | Cho phép deep reflection vào package `p` ở runtime |
| `opens p to m;` | Cho phép deep reflection có điều kiện tới module `m` |
| `uses S;` | Module khai báo sử dụng service `S` |
| `provides S with Impl;` | Module cung cấp implementation cho service `S` |

**Exports khác opens.** Export giúp sử dụng các public type trong package; opens phục vụ nhu cầu deep reflection và các quy tắc truy cập resource liên quan. Việc mở mọi package để vượt qua lỗi runtime thường làm mất một phần lợi ích encapsulation.

## 3. Không phải cứ đặt JAR trên module path là JVM sẽ sử dụng nó

Cần phân biệt **observable modules**, **resolved modules** và **readability**.

- **Observable:** module được tìm thấy trong vùng mà hệ thống có thể quan sát (ví dụ module path).
- **Resolved:** module được chọn tham gia cấu hình module graph, bắt đầu từ các root modules và đóng theo dependency.
- **Readable:** một module được phép đọc public types được export từ module khác theo các quan hệ JPMS.

Một JAR nằm trong thư mục module path chưa chắc đã được resolve. Một module đã resolve chưa chắc được code trong một named module khác đọc. Một module có thể được đọc nhưng các package nội bộ không được export nên code ngoài vẫn không truy cập được.

Ví dụ ứng dụng trên classpath cần dùng một library đặt trên module path:

~~~bash
java --module-path mods \
     --add-modules com.acme.catalog \
     -cp app.jar com.acme.app.Main
~~~

`--add-modules` yêu cầu resolve module `com.acme.catalog`, nhờ đó mã classpath có thể sử dụng API được export của module này theo quy tắc của unnamed module. Tên module phải là tên thực tế, không phải tên package hoặc tên file tùy đoán.

Có thể dùng `--add-modules ALL-MODULE-PATH` cho một số tình huống khám phá/chuyển đổi, nhưng không nên xem đó là thiết lập production mặc định: nó kéo thêm nhiều module vào cấu hình, có thể gây xung đột package, tăng phạm vi khởi tạo và làm che giấu danh sách dependency thực tế.

Với ứng dụng là named module:

~~~bash
java --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

Module `com.acme.app` là root; các module `requires` được resolve theo graph. Trong ví dụ dạng Unix, dấu `:` được dùng để nối các mục module path; trên Windows dùng dấu `;`.

## 4. Vì sao nên chuyển theo từng lớp thay vì đồng loạt?

Một hệ thống có nhiều phần không cùng độ sẵn sàng:

~~~text
Ứng dụng (legacy)
   |
   +-- HTTP framework
   +-- ORM / JDBC
   +-- JSON / XML
   +-- Thư viện nghiệp vụ tự phát triển
   +-- Plugin từ đối tác
   +-- Annotation processors và build plugins
   +-- Java agents và monitoring
~~~

Một số thư viện đã phát hành explicit module descriptor. Một số chỉ có `Automatic-Module-Name`. Một số chưa có tên ổn định. Một số framework cần reflective access tới entity, controller, serializer hoặc constructor nội bộ. Nếu chuyển mọi dependency trong một lần, khó phân biệt lỗi do module graph, reflection, provider discovery hay class loading.

Chiến lược thường hiệu quả:

1. Kiểm kê dependency và quan hệ chạy thực tế.
2. Phân loại mức độ sẵn sàng JPMS của từng artifact.
3. Chọn các thư viện ít phụ thuộc, API rõ ràng làm nhóm thử nghiệm.
4. Đặt từng nhóm dependency lên module path, giữ phần còn lại trên classpath khi thiết kế cho phép.
5. Dùng automatic module như cầu nối có kiểm soát.
6. Chỉ modularize ứng dụng/chủ thể khi quan hệ dependency đã đủ rõ.
7. Loại bỏ dần các cấu hình tạm và test trên đúng cách đóng gói production.

Cần lưu ý một ràng buộc cấu trúc: **explicit named module không thể khai báo `requires` tới unnamed module**. Vì vậy không thể mặc định “chỉ modularize ứng dụng trước, mọi dependency còn lại cứ ở classpath” rồi chờ JVM tự xử lý. Có thể sử dụng một số tùy chọn bridge như `--add-reads module=ALL-UNNAMED` trong giai đoạn chuyển tiếp, nhưng cách đó là ngoại lệ được quản lý và không thay thế việc phân định module graph lâu dài.

## 5. Kiểm kê dependency trước khi chuyển

Danh sách dependency từ Gradle/Maven là đầu vào, nhưng chưa đủ. Phải xét artifact được nạp ở runtime, bao gồm những JAR không xuất hiện trong compile classpath của một module chính.

Nên lập bảng:

| Artifact | Phiên bản | Vị trí hiện tại | JPMS status | Module name | Vấn đề dự kiến | Quyết định |
|---|---|---|---|---|---|---|
| `order-api.jar` | 1.x | Classpath | Explicit | `com.acme.order.api` | Ít reflection | Chuyển sớm |
| `legacy-json.jar` | 2.x | Classpath | Automatic | Cần xác minh | Package trùng? | Chuyển sau |
| `orm-driver.jar` | 5.x | Classpath | Cần kiểm tra | Chưa xác minh | Reflection/entity | Đánh giá riêng |
| `partner-plugin.jar` | 3.x | Custom loader | Chưa rõ | Chưa rõ | TCCL/service | Tách giai đoạn |
| `build-processor.jar` | 1.x | Processor path | Build-time | Không áp dụng trực tiếp | JDK/processor compatibility | Giữ tách biệt |

Các trường tối thiểu:

- Group/artifact/version và checksum của JAR dùng thực tế.
- Artifact là module explicit, automatic hay nằm trong unnamed module.
- Tên module đã được khai báo, lấy từ manifest hay được suy ra.
- Các package được export và mở; có package trùng với JAR khác không.
- Các module khác sử dụng public API hay chạm internal API.
- Có dynamic loading, reflection, serialization, service provider và resource loading không.
- Class loader nào nạp JAR và có custom module layer không.
- Phiên bản JDK, framework, plugin và vendor được hỗ trợ.

Không dùng một bảng “đã hỗ trợ JPMS: có/không” mà bỏ qua các tình huống runtime. Một thư viện có descriptor hợp lệ vẫn có thể không phù hợp với ứng dụng nếu module path làm thay đổi cách framework truy cập thành viên.

## 6. Công cụ kiểm tra module name và descriptor

### 6.1. `jar --describe-module`

Dùng công cụ `jar` của JDK phù hợp để xem module descriptor hoặc thông tin automatic module:

~~~bash
jar --file lib/order-api.jar --describe-module
jar --file lib/legacy-json.jar --describe-module
~~~

Nếu JAR có explicit descriptor, công cụ có thể hiển thị tên module, các `requires`, `exports`, `uses` và `provides`. Nếu JAR chưa modularize, output có thể cho thấy nó sẽ được coi là automatic module cùng module name được xác định.

Đối với multi-release JAR, có thể cần chỉ định tùy chọn release phù hợp để xem descriptor áp dụng cho JDK đích. Hãy kiểm tra `jar --help` của đúng JDK, tránh giả định mọi versioned entry có cùng descriptor.

### 6.2. `jdeps`

`jdeps` giúp phân tích dependency được thể hiện trong bytecode:

~~~bash
jdeps --summary lib/order-core.jar
jdeps --jdk-internals lib/order-core.jar
jdeps --print-module-deps --module-path lib lib/order-core.jar
~~~

Ý nghĩa:

- `--summary`: thống kê dependency ở mức tổng quát.
- `--jdk-internals`: phát hiện các tham chiếu bytecode tới API nội bộ JDK.
- `--print-module-deps`: đưa ra tập module dependency từ phân tích tĩnh mà có thể dùng khi chuẩn bị module configuration hoặc runtime image.

Kết quả `jdeps` phụ thuộc classpath/module path được cung cấp và tập class mà công cụ thực sự phân tích. Nó không phát hiện đầy đủ:

- `Class.forName("...")` với tên hình thành từ dữ liệu hoặc cấu hình.
- Provider được tìm qua `ServiceLoader` nhưng không xuất hiện trong tham chiếu bytecode trực tiếp.
- Các field/method được truy cập qua reflection hoặc method handles động.
- Tài nguyên file, template, schema hoặc plugin chỉ được tải theo tên chuỗi.
- Optional dependency chỉ có trong một môi trường cụ thể.

Vì thế, báo cáo `jdeps` là bằng chứng cấu trúc, không phải kết luận rằng module graph đã hoàn chỉnh.

### 6.3. Tạo bản nháp descriptor

`jdeps` có khả năng hỗ trợ tạo module descriptor ban đầu cho một số JAR chưa có descriptor. Ví dụ về dạng lệnh:

~~~bash
jdeps --generate-module-info generated-module-info \
      --module-path lib \
      lib/legacy-component.jar
~~~

Tập tùy chọn cụ thể phụ thuộc phiên bản JDK và loại JAR. Descriptor được tạo là **bản nháp** từ phân tích tĩnh; cần đọc lại để xác định public API, reflective access, services và optional dependencies. Không nên xem output tự sinh là hợp đồng cuối cùng.

Đặc biệt, `jdeps` không thể suy luận toàn bộ ý nghĩa nghiệp vụ của `exports` hoặc package nào chỉ dùng nội bộ. Chỉ nhóm sở hữu API mới có thể quyết định ranh giới ổn định cần công bố.

## 7. Đặt tên module ổn định cho dependency

### 7.1. Tên explicit module

Trong thư viện tự phát triển:

~~~java
module com.acme.metrics.api {
    exports com.acme.metrics;
}
~~~

Tên này được ghi trong module descriptor và nên được thiết kế như một phần của hợp đồng phát hành.

### 7.2. `Automatic-Module-Name` trong manifest

Nếu thư viện chưa sẵn sàng phát hành descriptor đầy đủ, tác giả JAR có thể công bố tên module ổn định trong manifest:

~~~text
Automatic-Module-Name: com.acme.legacy.metrics
~~~

Khi JAR nằm trên module path và được coi là automatic module, tên này có thể được sử dụng thay cho tên suy ra từ file. Điều đó giúp consumer khai báo `requires com.acme.legacy.metrics;` mà không phụ thuộc tên versioned JAR.

**Lưu ý:** `Automatic-Module-Name` không tạo explicit module và không tự định nghĩa ranh giới `exports` hoặc `opens` theo thiết kế mong muốn. Nó chỉ giải quyết một phần vấn đề đặt tên cho automatic module.

### 7.3. Tên suy ra từ filename

Nếu JAR không có descriptor hoặc tên manifest phù hợp, module name có thể được suy ra từ tên file theo quy tắc Java. Việc đổi artifact name hoặc thay naming convention có thể đổi tên mà consumer đang `requires`.

Vì vậy:

1. Lấy tên thật bằng `jar --describe-module`.
2. Ghi tên đó vào dependency inventory.
3. Ưu tiên artifact có tên module ổn định do vendor cung cấp.
4. Tránh tự suy ra module name chỉ bằng cách thay dấu `-` bằng `.`.
5. Khi chuyển từ automatic sang explicit module, xác nhận tên mới vẫn phù hợp hoặc có kế hoạch migration.

## 8. Xử lý split packages trước khi chuyển

**Split package** là tình huống nhiều module chứa cùng một package. Ở classpath, hai JAR có thể chứa class trong `com.acme.util` mà ứng dụng vẫn chạy tùy cách lookup. Trong module graph, package trùng nhau có thể gây lỗi resolution hoặc compiler không cho một module đọc hai nguồn chứa cùng package đó.

Ví dụ:

~~~text
legacy-core.jar
  com/acme/shared/Format.class

legacy-extra.jar
  com/acme/shared/DateUtil.class
~~~

Nếu hai JAR trở thành hai named modules riêng mà cùng định nghĩa `com.acme.shared`, cấu hình modular có thể không chấp nhận được. Không có tùy chọn `requires` nào biến split package thành thiết kế module lành mạnh.

Các chiến lược xử lý:

- Nâng thư viện lên bản được vendor tổ chức lại package.
- Hợp nhất các thành phần thành một module có chủ đích nếu nhóm sở hữu cả hai và phù hợp hợp đồng phát hành.
- Đổi namespace/package trong một nhánh phát triển mới khi có thể kiểm soát consumer.
- Thay một thư viện cũ bằng artifact thế hệ mới không có package trùng.
- Giữ một dependency ở classpath tạm thời nếu tổ hợp loader/graph cho phép, đồng thời ghi giới hạn và kế hoạch xử lý.

Không nên dùng `--patch-module` để “nuốt” tùy tiện JAR thứ hai vào module thứ nhất mà không kiểm soát source, class/resource trùng, security và lifecycle. Đây là cơ chế hữu ích cho các tình huống được thiết kế rõ như test/patch, không phải giải pháp chung cho split packages.

## 9. Một lộ trình chuyển dần theo bốn giai đoạn

### Giai đoạn A — Ứng dụng vẫn ở classpath

Đây là trạng thái phổ biến ban đầu:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

Trong giai đoạn này:

- Xây dựng inventory module/dependency.
- Chạy `jdeps` và xem module metadata.
- Nâng dependency lên phiên bản hỗ trợ JDK đích.
- Tách processor và công cụ build khỏi runtime dependency khi thích hợp.
- Xử lý package trùng, classpath conflict và API nội bộ JDK.
- Bổ sung integration test cho reflection, resource và service loading.

Ưu điểm là chưa làm thay đổi cấu trúc launch của ứng dụng. Đây là thời điểm tốt để giảm nợ kỹ thuật trước khi modularize.

### Giai đoạn B — Chuyển một số thư viện lên module path

Giữ app ở classpath nhưng đưa những dependency đã sẵn sàng lên module path:

~~~bash
java --module-path "mods:lib-modular" \
     --add-modules com.acme.metrics.api,com.acme.catalog.api \
     -cp "app.jar:lib-legacy/*" \
     com.acme.app.Main
~~~

Ở đây:

- `app.jar` và những dependency chưa chuyển còn trên classpath.
- Các module được chọn có mặt trên module path và được resolve qua `--add-modules`.
- Không nên đặt cùng một artifact đồng thời trên classpath lẫn module path.
- Cần kiểm tra các phụ thuộc transitive mà module mới cần.
- Các module có cùng package không được xung đột trong graph.

Sau mỗi nhóm chuyển, chạy test với launch command thực tế. Đặc biệt kiểm tra tài nguyên đọc qua `ClassLoader` và `ServiceLoader`, vì thay đổi từ unnamed sang named module có thể đổi behavior dù artifact giữ nguyên.

### Giai đoạn C — Dùng automatic modules cho dependency chưa có descriptor

Nếu thư viện chưa có `module-info.class` nhưng không gặp trở ngại nghiêm trọng, có thể đặt nó trên module path dưới dạng automatic module. Khi thư viện đã có tên module ổn định, một explicit module có thể khai báo:

~~~java
module com.acme.app {
    requires com.acme.catalog.api;
    requires com.acme.legacy.metrics;
}
~~~

Điều kiện là tên module thực tế phải đúng, dependency phải được resolve, và không có package conflict phá cấu hình.

Automatic module cung cấp cơ chế bridge cho thư viện cũ, nhưng rủi ro về reflective access, dynamic class loading, service discovery và hành vi runtime vẫn cần test. Một dependency automatic không mặc định là giải pháp lâu dài khi nhóm có thể nâng lên explicit module hỗ trợ đúng JPMS.

### Giai đoạn D — Modularize ứng dụng và loại bỏ workaround

Sau khi dependency graph tương đối ổn định, thêm `module-info.java` cho module ứng dụng, cấu hình build tool và chuyển điểm khởi chạy:

~~~java
module com.acme.app {
    requires com.acme.catalog.api;
    requires com.acme.metrics.api;

    uses com.acme.spi.ReportFormatter;
}
~~~

~~~bash
java --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

Khi đó cần xác minh các dependency mà app dùng đã trở thành named modules thích hợp. Mã classpath còn sót lại không thể được named module yêu cầu bằng `requires`, nên phải có kế hoạch cụ thể cho bridging, thay thế hoặc modularize từng thư viện.

Sau giai đoạn này, giảm dần `--add-reads`, `--add-exports`, `--add-opens`; chỉ giữ các mở rộng cần thiết đã được review.

## 10. Tương tác giữa named module và unnamed module

Đây là một trong các bẫy lớn nhất của migration.

Mã classpath thuộc unnamed module có khả năng tương tác với nhiều named modules đã resolve. Ngược lại, một explicit named module **không thể khai báo phụ thuộc tường minh vào unnamed module** bằng cú pháp `requires`.

Ví dụ, `com.acme.app` là named module nhưng thư viện `legacy-driver.jar` chỉ còn ở classpath. Nếu code của `com.acme.app` trực tiếp tham chiếu tới `legacy.driver.Client`, việc compile hoặc chạy có thể lỗi vì module app không có quan hệ đọc hợp lệ tới unnamed module và package chưa chắc được nhìn thấy như trước.

Trong một giai đoạn chuyển tiếp, có thể có cấu hình:

~~~bash
java --module-path mods \
     --class-path "lib-legacy/*" \
     --add-reads com.acme.app=ALL-UNNAMED \
     --module com.acme.app/com.acme.app.Main
~~~

`--add-reads` thêm quan hệ readability cho module được chỉ định tới unnamed modules tương ứng. Tuy nhiên, nó không tự giải quyết tất cả vấn đề accessibility, class loading, package conflicts hoặc dependency chưa có runtime. Cấu hình compile time cũng phải phù hợp; chỉ thêm cờ ở thời điểm chạy không sửa được compiler errors trong quá trình build.

Dùng cờ này có kiểm soát:

- Ghi rõ dependency chưa modularize và nơi cấu hình cờ được áp dụng.
- Tái hiện bằng launch tương đương production.
- Xác định kế hoạch thay cờ bằng module thực hoặc kiến trúc adapter.
- Kiểm tra cách IDE, test runner và build tool truyền cờ.
- Không coi `ALL-UNNAMED` là một module thật có thể `requires` trong descriptor.

## 11. Exports, opens và reflective frameworks

Một thư viện có thể được modularize đúng về API gọi trực tiếp nhưng vẫn lỗi khi framework dùng reflection. Ví dụ ORM, JSON serializer, dependency injection hoặc web framework có thể cần truy cập constructor không public, field private hoặc annotation trong package nội bộ.

Với module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Các public type trong `com.acme.domain.api` có thể được consumer đọc. Tuy nhiên, một framework muốn truy cập private field của entity ở `com.acme.domain.model` có thể gặp `InaccessibleObjectException` nếu package không được open phù hợp.

Nếu thư viện framework có named module rõ ràng, có thể mở có điều kiện:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.serialization;
}
~~~

Tên `com.acme.serialization` chỉ minh họa. Phải xác định đúng tên module của framework/runtime cụ thể; một framework trên classpath thuộc unnamed module và không thể dùng cùng tên module giả định.

Nếu framework đang ở classpath và cần mở package của named module, có thể dùng cờ runtime trong giai đoạn chuyển tiếp:

~~~bash
--add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED
~~~

Phân biệt:

- `--add-reads A=B`: thêm readability từ module A sang module B.
- `--add-exports A/p=B`: export package p từ A sang B cho access kiểu thông thường.
- `--add-opens A/p=B`: mở package p từ A sang B cho deep reflection ở runtime.

Các tùy chọn này không tương đương, và không nên sử dụng một cách rộng rãi để che lỗi. Nếu một API đã bị loại bỏ hoặc package nội bộ bị đổi tên, `--add-opens` không tạo lại class hoặc method đã mất.

Đối với JDK hiện đại, không dựa vào `--illegal-access` như giải pháp lâu dài; hành vi và mức hỗ trợ của cờ này thay đổi qua các phiên bản, và những phiên bản JDK mới đã tăng cường encapsulation mạnh hơn.

## 12. Resource loading khi dependency chuyển lên module path

Một lỗi migration ít hiển nhiên: source code không đổi, JAR vẫn có `config.xml`, nhưng `ClassLoader.getResourceAsStream` trả `null` sau khi đặt JAR trên module path.

Nguyên nhân có thể là resource nằm trong package của named module và bị module encapsulation hạn chế. Các API nạp tài nguyên không hoàn toàn giống nhau:

~~~java
// Class-relative, dùng class làm mốc.
InputStream a = SomeType.class.getResourceAsStream("rules.xml");

// Loader-relative, dùng tên từ gốc.
InputStream b = SomeType.class.getClassLoader()
        .getResourceAsStream("com/acme/api/rules.xml");

// Gắn rõ module và quy tắc truy cập của caller.
InputStream c = SomeType.class.getModule()
        .getResourceAsStream("com/acme/api/rules.xml");
~~~

Cần đóng stream sau khi dùng và xử lý trường hợp `null`. Trong named modules, `Module.getResourceAsStream` xét quyền truy cập theo module của caller; `ClassLoader.getResource` có quy tắc hạn chế khác đối với tài nguyên không phải `.class` trong package của named module.

Nếu thư viện tự đọc resource nội bộ, để chính mã trong module sở hữu resource thực hiện lookup thường rõ ràng hơn việc để consumer đoán đường dẫn package. Nếu resource là dữ liệu công khai, thiết kế API để xuất dữ liệu đó có thể tốt hơn mở cả package chỉ để đọc một file.

Khi chuyển dependency, kiểm tra cả:

- File resource có thực sự được đóng gói trong JAR không.
- Tên resource tương đối hay tuyệt đối có đúng không.
- Package chứa resource được `opens` thế nào.
- Resource được tìm qua class loader nào.
- Có resource cùng tên trong nhiều module hoặc JAR không.
- Framework có dùng TCCL để tìm template hoặc cấu hình không.

## 13. ServiceLoader và cách nạp provider qua JPMS

Nhiều thư viện dùng cơ chế plugin/service provider. Trước JPMS, JAR thường có:

~~~text
META-INF/services/com.acme.spi.ReportFormatter
~~~

Nội dung file liệt kê tên implementation. Khi modularize, provider trong explicit named module có thể được công bố bằng descriptor:

~~~java
module com.acme.format.json {
    requires com.acme.format.api;
    provides com.acme.spi.ReportFormatter
        with com.acme.format.json.JsonReportFormatter;
}
~~~

Module consumer khai báo:

~~~java
module com.acme.app {
    requires com.acme.format.api;
    uses com.acme.spi.ReportFormatter;
}
~~~

Code dùng:

~~~java
ServiceLoader<ReportFormatter> loader =
        ServiceLoader.load(ReportFormatter.class);

for (ReportFormatter formatter : loader) {
    System.out.println(formatter.getClass().getName());
}
~~~

Một số lỗi cần điều tra:

- Module provider không được resolve trong configuration.
- Provider JAR còn nằm trong loader/layer khác.
- Module consumer thiếu `uses`.
- Module provider thiếu `provides` hoặc cấu hình legacy provider không phù hợp.
- Service interface được nạp hai lần bởi loader khác nhau.
- Code dùng `ServiceLoader.load` với TCCL không nhìn thấy provider cần thiết.

Không suy luận rằng provider sẽ được tìm thấy chỉ vì `jar tf` có một file trong `META-INF/services`. Cần kiểm tra module descriptor, loader và layer. Với ứng dụng plugin tạo `ModuleLayer` riêng, API `ServiceLoader.load(layer, service)` có thể phù hợp hơn để tìm provider trong layer đó.

## 14. Module path không thay thế class loader design

JPMS bổ sung cấu trúc module, nhưng class loader vẫn định nghĩa class và tham gia runtime identity. Hai class có cùng binary name nhưng do hai defining loaders khác nhau nạp vẫn có thể là hai kiểu khác nhau.

Ứng dụng plugin có thể dùng:

~~~text
Application loader
   |
   +-- ModuleLayer chính
   |
   +-- Plugin layer A -> Loader A
   |
   +-- Plugin layer B -> Loader B
~~~

Chuyển một plugin JAR sang module path không tự làm plugin nhìn thấy API được nạp bởi loader khác hoặc khắc phục lỗi cast. Cần xác định module layer hierarchy, loader delegation, service discovery và API type nào được chia sẻ giữa plugin và host.

Nếu framework dùng Thread Context ClassLoader (TCCL), nên kiểm tra TCCL trên thread request, executor và thread nền. `ClassLoader.getResource` hoặc `ServiceLoader.load` có thể hoạt động khác khi context loader không như dự kiến.

Đối với dynamic plugin, lộ trình modularize cần được thiết kế riêng: module graph khởi động của ứng dụng và layer được tạo động không nhất thiết có cùng root modules hay quyền truy cập.

## 15. Cấu hình Gradle khi chuyển dependency

Gradle có hỗ trợ JPMS thông qua Java plugin và cơ chế suy ra module path trong những phiên bản phù hợp. Một cấu hình minh họa:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong ví dụ:

- Toolchain sử dụng JDK 21 để biên dịch.
- `options.release = 17` đặt source/API/bytecode baseline Java 17.
- `modularity.inferModulePath` cho phép Java plugin chọn module path hoặc classpath cho dependency theo metadata trong bối cảnh được hỗ trợ.

Đây là ví dụ về **module đã được modularize**, không phải một lệnh chuyển mọi JAR sang module path bất kể metadata. Hãy kiểm tra phiên bản Gradle/Java plugin và task compile thực tế. Nếu dự án không có `module-info.java`, kết quả cấu hình và cách inference có thể khác với kỳ vọng.

Một dependency Gradle vẫn được khai báo như thông thường:

~~~groovy
dependencies {
    implementation 'com.acme:catalog-api:2.0.0'
    implementation 'com.acme:legacy-json:1.9.0'
}
~~~

Việc artifact thực sự được đặt trên classpath hay module path trong task compile/runtime cần được xác nhận bằng cấu hình đã resolve và thông tin module của JAR, không suy đoán từ `implementation`.

Với test source set và plugin riêng, có thể cần thêm cấu hình module path/patching để test truy cập package không công khai. Không chạy thử chỉ test classpath rồi kết luận cấu hình module production sẽ hoạt động tương đương.

## 16. Cấu hình Maven và test theo module

Maven Compiler Plugin có thể hỗ trợ compile module-aware từ các phiên bản thích hợp. Một cấu hình release baseline minh họa:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version><!-- phiên bản đã được dự án phê duyệt --></version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Nội dung ví dụ chưa chứa số phiên bản plugin cụ thể vì cần chọn theo phiên bản Maven/JDK và chính sách dependency của dự án. Khi thêm `module-info.java`, compiler plugin sẽ có hành vi module-aware tương ứng với phiên bản công cụ và cách dependency được phân giải.

Với Maven Surefire/Failsafe, cần kiểm tra test engine, cấu hình `useModulePath` khi phù hợp, module descriptor của test artifacts và các cờ cần cho reflective access. Không phải mọi test runner hoặc framework mock cũ đều hỗ trợ module path giống nhau.

Một số dự án chạy application production dưới JPMS nhưng test lại chạy trên classpath. Điều đó có thể cần trong một giai đoạn chuyển tiếp, nhưng phải có thêm integration test thực sự khởi chạy artifact dưới module path nếu muốn bảo đảm migration thành công.

## 17. Kiểm tra class loading và resolution khi chạy

Tạo được module descriptor và biên dịch thành công chưa đảm bảo runtime graph hợp lệ. Những lỗi có thể gặp:

| Hiện tượng | Nguyên nhân cần khảo sát |
|---|---|
| `java.lang.module.FindException` | Không tìm thấy module, tên không khớp hoặc artifact/module path sai |
| `java.lang.module.ResolutionException` | Module graph mâu thuẫn, package conflict hoặc yêu cầu resolution không hợp lệ |
| `IllegalAccessError` | Bytecode đang truy cập type/member không còn accessible trong module graph |
| `InaccessibleObjectException` | Framework cố deep reflection vào package chưa mở |
| `NoClassDefFoundError` | Class thiếu, đường nạp sai, lỗi initialization trước đó hoặc binary không phù hợp |
| `ServiceConfigurationError` | Provider/service không hợp lệ hoặc không được nạp theo context đúng |
| Resource lookup trả `null` | Path sai, đóng gói thiếu, loader khác hoặc resource bị encapsulate |
| `ClassCastException` với cùng tên kiểu | Class được định nghĩa bởi các loader khác nhau |

Để xem module graph đang dùng, có thể tham khảo khả năng chẩn đoán của `java --show-module-resolution` trong JDK hỗ trợ:

~~~bash
java --show-module-resolution \
     --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

Log class loading hỗ trợ tìm class được nạp từ đâu:

~~~bash
java -Xlog:class+load=info \
     --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

Các lệnh áp dụng cho JDK có hỗ trợ option tương ứng. Đừng mở log mức lớn kéo dài trên production nếu chưa đánh giá ảnh hưởng đến dung lượng và hiệu năng.

## 18. Những vấn đề không được giải quyết chỉ bằng JPMS

Chuyển sang module path không tự sửa các vấn đề khác của compatibility migration:

### 18.1. Dependency xung đột phiên bản

Nếu ứng dụng kéo hai phiên bản không tương thích của cùng thư viện, cần giải quyết dependency management. Module graph có thể phát hiện một số xung đột rõ hơn, nhưng không tự đảm bảo semver hoặc behavioral compatibility.

### 18.2. API JDK bị deprecated/removed

Một thư viện dùng `sun.*` hoặc API bị xóa sẽ không tự hoạt động chỉ vì đã là named module. Cần nâng thư viện hoặc thay API; `--add-exports` và `--add-opens` không thể phục hồi API đã bị loại bỏ.

### 18.3. Annotation processors và generated code

Annotation processors chạy trong môi trường biên dịch, có thể có processor path/module path riêng. Việc modularize runtime không đồng nghĩa processor cũng phải hoặc đã chuyển sang module path. Cần kiểm tra toolchain, module visibility của compiler và code sinh ra.

### 18.4. Native libraries, JNI và instrumentation

JNI, native image, Java agent, bytecode enhancement và instrumentation có thể cần quyền truy cập hoặc cấu hình riêng. Cần kiểm tra tính tương thích với JDK/OS/CPU, không chỉ module descriptor.

### 18.5. Runtime artifact và launch packaging

Một cấu hình hoạt động với JAR rời có thể không hoạt động giống vậy khi đóng gói thành fat JAR hoặc custom runtime image. Tool `jlink` xây runtime image dựa trên module graph; automatic modules và một số dạng dependency chưa modularize có thể giới hạn khả năng sử dụng quy trình modular packaging đó. Cần xác nhận toolchain đóng gói với tập module thực tế.

## 19. Thiết kế chính sách chuyển đổi theo artifact

Một dependency nên được chuyển khi có đủ bằng chứng, không chỉ vì “JDK mới hơn đã hỗ trợ module path”.

### 19.1. Nhóm chuyển sớm

Phù hợp với:

- Thư viện do đội dự án sở hữu.
- API rõ ràng, ít deep reflection.
- Không có split package.
- Có module name ổn định.
- Có unit/integration tests và artifact tái tạo được.

Có thể bổ sung explicit `module-info.java`, chạy test, rồi công bố module name và exports như một phần hợp đồng API.

### 19.2. Nhóm bridge bằng automatic module

Phù hợp với:

- JAR chưa có descriptor nhưng có tên module ổn định hoặc dễ kiểm soát.
- Không có package trùng trong cấu hình module dự kiến.
- Các phụ thuộc có thể được resolve rõ ràng.
- Khả năng sử dụng reflective access và resources đã được kiểm thử.

Nên ghi rõ đây là bridge tạm, và có điều kiện nâng lên explicit module khi vendor hỗ trợ.

### 19.3. Nhóm giữ classpath tạm thời

Có thể giữ lại nếu:

- Framework/plugin chưa hỗ trợ module path đáng tin cậy.
- Có split package chưa thể tách.
- Resource/service loading bị ràng buộc bởi custom loader phức tạp.
- Module name của vendor chưa ổn định.
- Chuyển đổi ngay tạo rủi ro không chấp nhận được cho production.

Việc giữ classpath không đồng nghĩa bỏ qua vấn đề. Cần ghi owner, blocker, test và thời điểm đánh giá lại.

### 19.4. Nhóm bắt buộc thay thế hoặc refactor

Một số dependency phụ thuộc API nội bộ JDK bị loại bỏ, có xung đột package không giải được hoặc cần class loader behavior không thể duy trì. Với nhóm này, giải pháp có thể là nâng major version, thay thư viện, tách adapter hoặc thay kiến trúc plugin, chứ không phải thêm một JVM flag nữa.

## 20. Ma trận kiểm thử sau mỗi bước chuyển

Các môi trường cần kiểm tra tùy hệ thống, ví dụ:

| Kịch bản | Ứng dụng | Thư viện đã chuyển | Thư viện cũ | Nội dung cần xác minh |
|---|---|---|---|---|
| Baseline | Classpath | Chưa chuyển | Classpath | Hành vi cũ và kết quả test ban đầu |
| Hybrid | Classpath | Module path | Classpath | Resolution, exports và resource/service visibility |
| Mixed library | Named module | Automatic/explicit | Classpath có bridge | Readability, reflection, class loader |
| Modular | Named module | Named modules | Không còn trong đường phụ thuộc chính | Module graph và runtime behavior |
| Plugin | Host modular | Module layer/plugin loader | Một số plugin legacy | Discovery, isolation và loader identity |
| Rollback | Bản trước | Tùy chiến lược deploy | Bản trước | Có thể quay về cấu hình cũ an toàn |

Nhóm kiểm thử:

1. **Build và compiler:** `module-info.java` hợp lệ, source/API baseline phù hợp, không có package conflict.
2. **Binary API:** consumer cũ chạy với dependency mới khi đó là yêu cầu.
3. **Startup:** root modules và transitive dependencies resolve đầy đủ.
4. **Reflection:** ORM, JSON, DI, proxy, test framework và serialization truy cập đúng thành viên.
5. **Resources:** templates, file cấu hình, locale bundles, schema và file trong package kín.
6. **Services:** `ServiceLoader`, JDBC drivers, providers và plugin discovery.
7. **Networking/data:** HTTP, TLS, database, messaging và contract với hệ thống ngoài.
8. **Packaging:** JAR, container, launcher script, `jlink` image nếu có.
9. **Observability:** logging, metrics, tracing, agents và error reporting.
10. **Rollback:** artifact và lệnh chạy cũ vẫn dùng được nếu kế hoạch rollback yêu cầu.

Cần dùng **đúng artifact và launch command** của ứng dụng thực tế. Unit test trong IDE có thể chạy classpath mà không đi qua ranh giới module, nên không thay thế được integration test dưới module path.

## 21. Kiểm soát thay đổi và rollback

Khi chuyển một nhóm dependency, hãy ghi lại:

- Baseline JDK/vendor/version và module graph.
- Phiên bản artifact cùng checksum.
- Dependency nào từ classpath chuyển sang module path.
- Module name và descriptor thực tế.
- Các cờ `--add-modules`, `--add-reads`, `--add-exports`, `--add-opens` được thêm/bỏ.
- Thay đổi class loader/TCCL, service provider và resource lookup.
- Test đã chạy và kết quả quan sát.
- Điều kiện rollback cùng phiên bản artifact/cấu hình cần khôi phục.

Một kế hoạch rollback không nên chỉ nói “chuyển JAR về classpath”. Nếu ứng dụng đã thêm `module-info.java` và trở thành named module, có thể không còn chạy được nguyên trạng với toàn bộ dependency cũ ở classpath. Cần chuẩn bị artifact hoặc launch configuration tương thích với kiến trúc cũ; kiểm tra rollback như một tổ hợp thực sự.

Với rolling deployment hoặc nhiều service, thay đổi module path là thay đổi nội bộ quá trình chạy nhưng có thể làm lộ các lỗi binary behavior, provider discovery hoặc serialization. Không nên ghép nâng JDK, nâng major framework, modularize toàn bộ dependency và đổi giao thức ngoài cùng một đợt nếu có thể tách.

## 22. Checklist trước khi chuyển một dependency

- [ ] Đã xác định chính xác JAR/version/checksum đang dùng ở runtime.
- [ ] Đã biết artifact là explicit, automatic hay unnamed module trong cấu hình hiện tại.
- [ ] Đã xác minh module name bằng công cụ JDK, không tự đoán theo tên file.
- [ ] Đã tìm split packages và xung đột module name.
- [ ] Đã rà soát `requires`, `exports`, `opens`, `uses` và `provides` liên quan.
- [ ] Đã xác định có cần `--add-modules` để resolve module hay không.
- [ ] Đã kiểm tra giới hạn tương tác named module với unnamed module.
- [ ] Đã rà soát reflective access và chỉ dùng mở package có phạm vi rõ.
- [ ] Đã kiểm tra resource lookup, ServiceLoader và Thread Context ClassLoader.
- [ ] Đã kiểm tra custom loader, dynamic module layer và plugin nếu có.
- [ ] Đã chạy build/test theo module path thật và đúng JDK đích.
- [ ] Đã thử các tình huống chỉ có ở packaging production.
- [ ] Đã ghi lại các flag bridge, owner và kế hoạch loại bỏ.
- [ ] Đã chuẩn bị rollback artifact và launch configuration phù hợp.
- [ ] Đã cập nhật inventory sau khi nhóm dependency chuyển thành công.

## 23. Kết luận

Chuyển dependency từ classpath sang module path là một **quá trình thay đổi kiến trúc nạp lớp và quản lý hợp đồng API**, không phải chỉ thay `-cp` bằng `--module-path`. JPMS cung cấp unnamed module để tương thích với mã classpath, automatic module như cầu nối cho JAR chưa có descriptor và explicit named module để thể hiện dependency, exports, opens và service contracts một cách tường minh.

Lộ trình khả thi là kiểm kê artifact, xử lý package conflict, xác minh module name, chọn nhóm thư viện ít rủi ro, chạy hybrid configuration, chuyển dần sang explicit module và kiểm thử trên đúng runtime/packaging. Mỗi bước phải phân biệt **module có thể được tìm thấy**, **module đã được resolve**, **module đọc được module khác**, và **package thực sự được mở hoặc export**.

Chỉ khi đã có bằng chứng về compile, class loading, reflection, resources, services, compatibility với consumer và khả năng rollback, nhóm mới nên xem một dependency là đã chuyển đổi thành công. Một hệ thống còn một số dependency trên classpath nhưng được quản lý rõ ràng và kiểm thử đầy đủ thường an toàn hơn một hệ thống chuyển toàn bộ sang module path nhưng phụ thuộc nhiều workaround không ai theo dõi.
