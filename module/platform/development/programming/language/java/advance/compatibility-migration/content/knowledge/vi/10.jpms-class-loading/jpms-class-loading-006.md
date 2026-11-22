# --add-modules, --add-reads và phạm vi sử dụng tạm thời

Trong Java Advance Compatibility Migration, thay đổi JDK hoặc chuyển ứng dụng từ classpath sang Java Platform Module System (JPMS) thường làm lộ các phụ thuộc trước đây không được khai báo rõ. Một class vẫn có trong JAR nhưng không được tìm thấy khi chạy, một named module không đọc được module khác, hoặc code cũ hoạt động trên classpath nhưng lỗi sau khi đưa lên module path. Trong giai đoạn chuyển tiếp, hai tùy chọn **--add-modules** và **--add-reads** có thể giúp nhóm phát triển khoanh vùng và tháo gỡ một số vấn đề về module resolution và readability.

Hai tùy chọn này **không tương đương** và cũng **không phải phương án thiết kế JPMS lâu dài**. --add-modules mở rộng danh sách module được đưa vào module graph. --add-reads thêm quan hệ đọc từ một named module sang một module đích. Không tùy chọn nào tự động mở package cho reflection, sửa API không tồn tại, bổ sung class vào JDK image hoặc biến một dependency bất tương thích thành tương thích.

Mục tiêu của bài là hiểu cơ chế, dùng hai tùy chọn đúng chỗ, xác minh bằng lệnh Java cụ thể và xây dựng kế hoạch thay thế các ngoại lệ tạm thời bằng cấu trúc module rõ ràng.

## 1. Mô hình JPMS cần nắm trước khi thêm option

JPMS được giới thiệu ở Java 9 và tổ chức code thành các **module**. Module được đặt tên thường có file module-info.java, mô tả phụ thuộc, package được export, các package được mở cho reflection và dịch vụ được cung cấp hoặc sử dụng.

Ví dụ module thư viện:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Ví dụ module ứng dụng:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Khi module ứng dụng declares requires, JPMS biết nó phải đọc module thư viện. Khi module thư viện declares exports, public type trong package tương ứng có thể được module khác truy cập theo quy tắc JPMS.

### 1.1. Bốn khái niệm dễ bị trộn lẫn

| Khái niệm | Câu hỏi | Cơ chế |
|---|---|---|
| Observable module | Hệ thống có thể tìm thấy module ở đâu? | System modules, module path, module finder |
| Resolved module | Module có được đưa vào module graph cho lần chạy này không? | Root modules và dependency resolution |
| Readability | Module A có quyền đọc module B không? | requires, requires transitive, --add-reads |
| Accessibility | Package/type/member của B có cho phép A truy cập theo cách đang dùng không? | exports, opens, --add-exports, --add-opens, quy tắc Java access |

**Observable không đồng nghĩa resolved.** Một JAR modular có thể nằm trên module path, nhưng không nằm trong module graph nếu không có root hoặc dependency phù hợp.

**Resolved không đồng nghĩa readable.** Module B có thể đã được thêm vào graph nhưng module A chưa có read edge tới B.

**Readable không đồng nghĩa accessible.** A đọc được B nhưng B không export package cần dùng thì code của A vẫn không thể truy cập public type theo cách thông thường. Với deep reflection, tình huống còn cần opens hoặc --add-opens.

Có thể hình dung:

~~~text
[Module B có trên module path]
               |
               v
[Module B được resolve vào graph?] -- chưa --> --add-modules hoặc requires phù hợp
               |
              có
               v
[Module A đọc được module B?] ----- chưa --> requires hoặc --add-reads
               |
              có
               v
[B export package cần truy cập?] -- chưa --> exports hoặc --add-exports
               |
              có
               v
[Java access rules hợp lệ?] ------ chưa --> chỉnh visibility/API
               |
              có
               v
[Truy cập public API có thể thành công]

Deep reflection: xem riêng opens / --add-opens.
~~~

### 1.2. Named, automatic và unnamed module

- **Named module tường minh:** có module-info.class; quan hệ requires, exports, opens được khai báo rõ.
- **Automatic module:** JAR thường được đặt trên module path và được JPMS coi như module có tên suy ra hoặc tên do manifest quy định. Nó giúp migration nhưng tên module suy ra từ tên JAR có thể thay đổi và cần được kiểm tra.
- **Unnamed module:** class/JAR trên classpath thuộc unnamed module của class loader tương ứng. Code cũ thường chạy theo mô hình này.

Một named module không mặc nhiên đọc được class nằm trong unnamed module. Trong giai đoạn chuyển dần, **--add-reads ten.module=ALL-UNNAMED** có thể tạo một cầu nối, nhưng nên xem đó là giải pháp quá độ.

## 2. --add-modules: thêm root module vào quá trình phân giải

Cú pháp chung của Java launcher:

~~~bash
java --add-modules module1,module2 [các tùy chọn khác] ...
~~~

Tùy chọn này yêu cầu launcher xem các module được liệt kê như **root modules bổ sung** khi giải module graph. Nếu module root có requires tới các module khác, resolution cũng đưa những dependency cần thiết vào graph theo quy tắc JPMS.

Ví dụ khái niệm:

~~~bash
java \
  --module-path mods \
  --add-modules com.example.plugin \
  --module com.example.app/com.example.app.Main
~~~

Ứng dụng com.example.app là main module; com.example.plugin được thêm làm root. Điều đó có thể cần khi module plugin được tìm qua ServiceLoader hoặc một cơ chế khám phá động, chứ không có quan hệ requires từ main module.

Tuy nhiên, --add-modules **không** có nghĩa com.example.app được phép import và gọi public API của com.example.plugin nếu hai module chưa có quan hệ readability phù hợp. Cũng không có nghĩa package của plugin được export cho app.

### 2.1. Module phải thực sự observable

Giả sử chạy:

~~~bash
java \
  --module-path mods \
  --add-modules com.vendor.connector \
  -m com.example.app/com.example.app.Main
~~~

Nếu com.vendor.connector không có trong module path, system modules hoặc nguồn module phù hợp thì launcher không thể tạo module đó từ tên và có thể báo lỗi resolution, chẳng hạn không tìm thấy module.

Các bước cần kiểm tra:

1. JAR/module có thực sự tồn tại ở đường dẫn dự kiến không?
2. Tên JPMS của module có đúng không, nhất là automatic module?
3. JAR được đặt trên module path hay classpath?
4. Runtime image có chứa JDK module được yêu cầu hay không?
5. Có xung đột tên module, package hoặc version không?

Với custom runtime image tạo bằng jlink, nếu một JDK module không có trong image thì --add-modules không tự thêm nội dung module đã bị lược bỏ. Cần tạo lại runtime image hoặc thay cấu hình triển khai.

### 2.2. Các giá trị đặc biệt của --add-modules

Java launcher hỗ trợ những token đặc biệt để chỉ tập module thay vì một tên module đơn:

| Token | Ý nghĩa tổng quát | Lưu ý |
|---|---|---|
| ALL-DEFAULT | Các module root mặc định trong tình huống khởi chạy tương ứng | Tập mặc định thay đổi theo mode khởi chạy và JDK |
| ALL-SYSTEM | Toàn bộ system modules có thể quan sát được | Có thể mở rộng graph đáng kể |
| ALL-MODULE-PATH | Các module tìm thấy trên module path | Có thể làm lộ xung đột module/package |

Ví dụ:

~~~bash
java \
  --module-path mods \
  --add-modules ALL-MODULE-PATH \
  -m com.example.app/com.example.app.Main
~~~

Đây là cách mở rộng phạm vi resolve, **không phải cấu hình production được khuyến nghị mặc định**. Nếu có các module không cần thiết trên module path, việc resolve tất cả có thể phát hiện hoặc tạo ra xung đột, làm phức tạp startup và khiến cấu hình phụ thuộc nội dung thư mục triển khai.

Khi cần một plugin cụ thể, ưu tiên tên module cụ thể. Khi kiểm tra resolution, có thể dùng token rộng trong môi trường kiểm thử để phân biệt vấn đề “module chưa resolve” với “module đã resolve nhưng thiếu read edge”.

### 2.3. Có phải cứ dùng --add-modules là cần thiết?

Không. Nếu module đã được đưa vào graph qua requires hoặc thuộc các root mặc định, thêm lại tên module thường không giải quyết gì. Một module có thể nằm trong runtime và được resolve sẵn; hãy kiểm tra bằng:

~~~bash
java --list-modules
java --show-module-resolution \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

--list-modules cho biết các module trong runtime image, không phải toàn bộ module mà một ứng dụng cụ thể sẽ resolve. --show-module-resolution cho thấy quá trình phân giải khi launcher chạy theo command đang dùng. Đó là hai góc quan sát khác nhau.

## 3. --add-reads: thêm một read edge giữa module

Cú pháp thường dùng:

~~~bash
java --add-reads module.nguon=module.dich ...
~~~

Hoặc với nhiều module đích:

~~~bash
java --add-reads module.nguon=module.dich1,module.dich2 ...
~~~

Một ví dụ:

~~~bash
java \
  --module-path mods \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  -m com.example.app/com.example.app.Main
~~~

Trong ví dụ này:

- com.example.library phải **được resolve**; --add-modules bảo đảm có root bổ sung nếu chưa có đường resolution từ app.
- --add-reads cho phép com.example.app đọc com.example.library.
- Package chứa API cần dùng vẫn phải được export hợp lệ từ com.example.library.
- Quy tắc visibility của Java vẫn áp dụng cho class, constructor, field và method.

Read edge là mối quan hệ **có hướng**. Nếu A đọc B, không suy ra B cũng đọc A. Nó cũng không ngụ ý A đọc toàn bộ dependency mà B đọc, trừ những quan hệ được module system truyền tiếp theo cơ chế tương ứng.

### 3.1. Khi module đích chưa được resolve

Nếu chỉ ghi:

~~~bash
java \
  --module-path mods \
  --add-reads com.example.app=com.example.library \
  -m com.example.app/com.example.app.Main
~~~

mà com.example.library chưa thuộc resolved graph, option --add-reads không tự biến B thành một root module. Trong nhiều tình huống JVM sẽ cảnh báo tên module không tồn tại trong graph hoặc không tạo được read edge hữu ích. Vì vậy, kiểm tra resolution trước; khi cần thiết có thể dùng đồng thời --add-modules và --add-reads.

Cũng cần phân biệt với trường hợp app đã có requires com.example.library: read edge đã tồn tại theo descriptor, thêm --add-reads có thể là dư thừa và làm cấu hình khó hiểu.

### 3.2. Read edge đến unnamed module

Một tình huống migration phổ biến: mã nguồn của module A đã có module-info.java nhưng vẫn phụ thuộc một JAR legacy mà nhà phát triển chưa đưa lên module path. JAR này đang nằm trên classpath, thuộc unnamed module.

Có thể mở read edge tạm thời bằng:

~~~bash
java \
  --module-path mods \
  --class-path "legacy/*" \
  --add-reads com.example.app=ALL-UNNAMED \
  -m com.example.app/com.example.app.Main
~~~

ALL-UNNAMED là token đặc biệt đại diện cho các unnamed modules tương ứng. Tùy chọn này cho named module đọc code classpath, nhưng:

- JAR legacy vẫn phải thật sự có mặt trên classpath.
- Không được đặt tên module giả cho JAR classpath rồi mong --add-reads tìm thấy.
- Cần kiểm tra class loader, reflection và cấu hình framework trong môi trường thật.
- Đây là cách nối hai mô hình triển khai tạm thời, không thay thế việc thiết kế dependency lâu dài.

Nếu code cần được biên dịch như một named module nhưng sử dụng classpath legacy, compiler cũng phải được cấu hình cho tình huống này. Việc chỉ thêm --add-reads lúc chạy không sửa lỗi compile-time của source.

### 3.3. Không tự sửa exports hoặc opens

Giả sử library có:

~~~java
module com.example.library {
    // Không exports com.example.library.internal;
}
~~~

Dù chạy với:

~~~bash
--add-reads com.example.app=com.example.library
~~~

com.example.app không tự nhiên có quyền sử dụng những public type trong package nội bộ không được export.

Ba option có mục đích khác nhau:

| Option | Điều chỉnh | Không thực hiện |
|---|---|---|
| --add-modules | Đưa module bổ sung vào resolved graph | Không cho phép A đọc B |
| --add-reads | Bổ sung readability A → B | Không export/open package |
| --add-exports | Export package của module nguồn đến module đích cho truy cập API thường | Không mở toàn bộ cho deep reflection |
| --add-opens | Mở package cho deep reflection tại runtime | Không thay thế requires hoặc sửa method descriptor |

Một cú pháp xuất package cho module cụ thể:

~~~bash
--add-exports com.example.library/com.example.library.internal=com.example.app
~~~

Một cú pháp mở package cho reflection:

~~~bash
--add-opens com.example.library/com.example.library.internal=com.example.app
~~~

Dùng đúng option cho đúng lỗi. Nếu chỉ thiếu readability, không nên mở package nội bộ. Nếu lỗi là InaccessibleObjectException do reflection, chỉ thêm read edge cũng không bảo đảm sửa được.

## 4. Ví dụ từ đầu đến cuối: hai named module không có requires

Đây là tình huống cố ý tạo lỗi: module app gọi library đã export public API, nhưng module-info.java của app chưa khai báo requires.

### 4.1. Cấu trúc source

~~~text
jpms-demo/
└── src/
    ├── com.example.library/
    │   ├── module-info.java
    │   └── com/example/library/Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

File src/com.example.library/module-info.java:

~~~java
module com.example.library {
    exports com.example.library;
}
~~~

File src/com.example.library/com/example/library/Greeter.java:

~~~java
package com.example.library;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Xin chao JPMS";
    }
}
~~~

File src/com.example.app/module-info.java cố tình không có requires:

~~~java
module com.example.app {
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.library.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

### 4.2. Biên dịch library trước

Từ thư mục jpms-demo:

~~~bash
mkdir -p mods

javac \
  --module-source-path src \
  -d mods \
  -m com.example.library
~~~

Output là exploded module trong mods/com.example.library.

### 4.3. Biên dịch app bằng ngoại lệ tạm thời

Nếu không khai báo requires, biên dịch app theo cách module chuẩn sẽ gặp vấn đề readability. Trong một migration chưa thể sửa module descriptor ngay, có thể bổ sung module và read edge tại compile time:

~~~bash
javac \
  --module-source-path src \
  --module-path mods \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  -d mods \
  -m com.example.app
~~~

Những option này giải quyết đúng hai bước: bảo đảm module thư viện được resolve trong ngữ cảnh biên dịch và cho module app đọc thư viện. Compiler option phải tương thích với JDK hiện đang dùng và các module descriptor cụ thể của project.

Chỉ định --add-modules mà thiếu --add-reads không đồng nghĩa compiler được phép dùng API từ app. Ngược lại, chỉ thêm --add-reads khi library chưa observable/resolved cũng không đủ.

### 4.4. Chạy app với hai option tương ứng

~~~bash
java \
  --module-path mods \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  --module com.example.app/com.example.app.Main
~~~

Kết quả minh họa:

~~~text
Xin chao JPMS
~~~

Điều quan trọng: ví dụ này giải thích cơ chế của hai option, **không khuyến nghị giữ nguyên cách xây module thiếu requires**.

### 4.5. Cách sửa bền vững

Khi đã có thể thay đổi module descriptor, sửa app thành:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Sau đó biên dịch lại theo quy tắc JPMS chuẩn:

~~~bash
javac \
  --module-source-path src \
  -d mods \
  -m com.example.library,com.example.app
~~~

Chạy mà không cần ngoại lệ:

~~~bash
java \
  --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

Giờ dependency là một phần của hợp đồng module; compiler, IDE, đóng gói và runtime đều có cùng thông tin. Đây thường là điểm kết thúc mong muốn của ngoại lệ --add-reads.

### 4.6. Lưu ý Windows

Trong ví dụ trên, --module-path chỉ dùng một thư mục mods, nên không cần dấu phân cách. Nếu module path có nhiều đường dẫn, Linux/macOS thường dùng dấu hai chấm, Windows dùng dấu chấm phẩy.

~~~bash
# Linux/macOS
java --module-path "mods:third-party" -m com.example.app/com.example.app.Main
~~~

~~~powershell
# Windows PowerShell
java --module-path "mods;third-party" -m com.example.app/com.example.app.Main
~~~

Khi gọi command trực tiếp qua PowerShell, để ý quy tắc quoting; khi đặt option trong Gradle/Maven, cấu trúc truyền từng argument thường khác với nhập một chuỗi shell.

## 5. Kịch bản thực tế: named module đọc thư viện legacy trên classpath

Nhiều ứng dụng không thể chuyển tất cả JAR sang named module cùng lúc. Giả sử com.company.orders đã có module descriptor, nhưng một thư viện cũ chỉ chạy đúng trên classpath.

~~~text
mods/
  com.company.orders/
legacy/
  legacy-client.jar
~~~

Một lệnh chạy tạm thời có thể là:

~~~bash
java \
  --module-path mods \
  --class-path "legacy/*" \
  --add-reads com.company.orders=ALL-UNNAMED \
  -m com.company.orders/com.company.orders.Main
~~~

Điểm cần hiểu:

1. --class-path đặt JAR legacy vào unnamed module.
2. --add-reads bổ sung cạnh đọc từ com.company.orders sang unnamed modules.
3. Option này không biến legacy-client.jar thành named module.
4. Cấu hình classpath vẫn phải đúng, kể cả transitive JAR và thứ tự nạp class.
5. Với code compile trực tiếp dựa vào legacy-client.jar, compiler cũng cần classpath và read edge phù hợp.

Một hướng lâu dài là nâng cấp thư viện có JPMS support, chuyển nó thành automatic module có tên được kiểm soát hoặc tách lớp adapter để giới hạn vùng code tiếp xúc với dependency legacy. Mỗi hướng có rủi ro riêng: automatic module name có thể không ổn định, module path có thể gặp split package, còn adapter có thể cần migration API và test hành vi.

### 5.1. Đừng ép mọi JAR lên module path bằng mọi giá

Một số thư viện cũ có:
- Package trùng giữa nhiều JAR.
- Cơ chế class loader riêng.
- Service/resource discovery phụ thuộc classpath.
- Reflection sâu vào các package không export.
- Automatic module name suy ra dễ thay đổi khi đổi tên artifact.

Di chuyển chúng ngay lên module path có thể tạo vấn đề mới. Việc giữ một phần trên classpath trong giai đoạn chuyển tiếp là lựa chọn có kiểm soát, nhưng cần ghi rõ giới hạn và thời điểm kết thúc.

## 6. Phạm vi hỗ trợ của các option trong build và runtime

Một khác biệt nguy hiểm: ứng dụng **compile thành công** với --add-reads nhưng khi chạy lại không có cùng tùy chọn; hoặc ứng dụng chạy được trên máy developer nhưng test runner/production process không có option đó.

| Ngữ cảnh | Những gì cần đối chiếu |
|---|---|
| javac | Module source/path, dependency đã resolve, --add-modules, --add-reads lúc biên dịch |
| java | Module path, classpath, root modules, read edge của process runtime |
| Test JVM | Cấu hình JVM args của từng fork/test worker; không mặc định giống compile |
| IDE run configuration | Có dùng cùng JDK và module VM options không |
| Gradle/Maven | Build tool process khác với compiler/test/app process |
| Container/service | ENTRYPOINT, command, args, launcher script và môi trường |
| jlink image | System modules cần dùng có thực sự nằm trong image không |
| Plugin/module layer | Module được nạp trong layer nào; command-line option có áp dụng cho layer đó không |

JPMS có thể liên quan nhiều module layer/class loader. Tùy chọn launcher thay đổi graph của boot layer theo cách tương ứng; nó không phải giấy phép sửa mọi layer do ứng dụng tạo động. Nếu framework tạo layer riêng, cần kiểm tra API và cơ chế resolution của layer đó thay vì đoán command-line option đã giải quyết mọi thứ.

### 6.1. Gradle: tách compile và run/test arguments

Với Gradle Java plugin, compiler arguments và JVM runtime arguments là các cấu hình khác nhau. Ví dụ ý tưởng về một task JavaExec, không phải cấu hình đầy đủ của toàn project:

~~~groovy
tasks.named("runOldModule", JavaExec) {
    jvmArgs(
        "--add-modules", "com.example.library",
        "--add-reads", "com.example.app=com.example.library"
    )
}
~~~

Đây chỉ là minh họa cách truyền từng JVM option. Nếu JavaExec chạy theo classpath thay vì module path, hoặc task chưa cấu hình mainModule, mainClass và module-path đúng, những option này không thay thế phần cấu hình còn thiếu.

Phần biên dịch có thể cần compiler args riêng và test task có thể cần jvmArgs riêng. Không giả định thêm jvmArgs cho Gradle daemon sẽ tự chuyển sang JVM chạy ứng dụng.

### 6.2. Maven: compiler, Surefire và runtime là các bước khác nhau

Trong Maven, plugin compiler, test runner (ví dụ Surefire/Failsafe) và bước chạy ứng dụng có thể tạo process JVM khác nhau. Tùy chọn dùng trong javac không tự xuất hiện ở fork test. Khi test dựa vào ngoại lệ module, phải đảm bảo cấu hình test runtime phản ánh đúng phạm vi cần thiết và không ghi đè các option của test framework.

Ví dụ khái niệm của Java launcher:

~~~bash
java --module-path target/modules \
  --add-modules com.example.library \
  --add-reads com.example.app=com.example.library \
  -m com.example.app/com.example.app.Main
~~~

Hãy ghi lại lệnh cuối cùng mà build/plugin tạo, không chỉ nhìn một property trong POM.

### 6.3. Không thay option module bằng tùy chọn môi trường không kiểm soát

Những biến như JAVA_TOOL_OPTIONS hay JDK_JAVA_OPTIONS có thể bổ sung JVM/launcher options, nhưng phạm vi và thời điểm được xử lý phụ thuộc cơ chế. Đưa --add-reads vào một biến môi trường dùng chung có thể vô tình áp dụng cho build tool, test, worker và ứng dụng không liên quan.

Ưu tiên cấu hình theo process/task cụ thể, có owner, có review và tài liệu. Nếu bắt buộc dùng environment injection trong container, phải xác minh option thực sự có hiệu lực cho launcher mục tiêu.

## 7. Chẩn đoán lỗi: thiếu module, thiếu readability hay thiếu exports?

### 7.1. Xác minh runtime và module đang observable

~~~bash
java --version
java --list-modules
jar --describe-module --file lib/example-library.jar
~~~

jar --describe-module giúp xem module descriptor của modular JAR hoặc thông tin automatic module khi phù hợp. Nếu tên module không đúng như dự kiến, --add-modules hoặc --add-reads với tên sai sẽ không đạt kết quả.

Với module ứng dụng:

~~~bash
java --show-module-resolution \
  --module-path mods \
  --add-modules com.example.library \
  -m com.example.app/com.example.app.Main
~~~

Xem module nào được resolve và root/dependency được chọn.

### 7.2. Xem phụ thuộc tĩnh với jdeps

~~~bash
jdeps --module-path mods \
  --print-module-deps \
  app.jar
~~~

Hoặc với một named module đã đóng gói:

~~~bash
jdeps --module-path mods \
  --check com.example.app
~~~

jdeps có thể hỗ trợ phát hiện dependency module của bytecode và kiểm tra descriptor theo chế độ tương ứng. Tuy nhiên, reflection, ServiceLoader theo tên, Class.forName và plugin runtime có thể không được thể hiện đủ qua phân tích tham chiếu tĩnh.

### 7.3. Bảng phân loại hiện tượng

| Thông báo/hiện tượng | Nguyên nhân nên kiểm tra trước | Hướng xử lý |
|---|---|---|
| Module ... not found | Module chưa observable hoặc sai module name | Kiểm tra module path, name, runtime image |
| Package ... is not visible / module A does not read B | Read edge thiếu | Khai báo requires hoặc tạm --add-reads |
| Module B does not export package ... to A | Package chưa được export phù hợp | Sửa API/module descriptor; cân nhắc --add-exports tạm |
| InaccessibleObjectException | Deep reflection bị chặn | Điều chỉnh reflection/API, opens hoặc --add-opens có giới hạn |
| NoClassDefFoundError / ClassNotFoundException | Class loader, resolution hoặc dependency thiếu | Tìm class nguồn và graph runtime thực tế |
| LayerInstantiationException / split package | Module graph hoặc package ownership xung đột | Sửa đóng gói/module path, không thêm modules bừa bãi |
| UnsupportedClassVersionError | Bytecode yêu cầu JDK mới hơn | Kiểm tra major version và runtime đích |
| Không tìm được plugin dù JAR có trên module path | Plugin module chưa resolve hoặc ServiceLoader config sai | Kiểm tra provider, uses/provides, root module và runtime layer |

Một công cụ chẩn đoán tốt không chỉ hỏi “có thêm flag nào cho chạy được không?” mà phải hỏi “đang lỗi ở bước resolution, readability, accessibility hay class loading?”

### 7.4. Điều gì xảy ra nếu option đặt sai vị trí?

Với Java launcher, option phải được truyền ở phần JVM/launcher options, trước main class, -jar target hoặc -m target theo cú pháp tương ứng.

Đúng:

~~~bash
java --add-modules com.example.library \
  --module-path mods \
  -m com.example.app/com.example.app.Main
~~~

Sai mục đích nếu truyền như application argument:

~~~bash
java -m com.example.app/com.example.app.Main \
  --add-modules com.example.library
~~~

Ở lệnh thứ hai, phần sau main target được chuyển thành đối số cho chương trình, không còn là option để Java launcher sửa module graph. Vấn đề tương tự có thể xảy ra khi chuyển lệnh chạy giữa shell, Docker ENTRYPOINT/CMD hoặc service manager.

## 8. Vì sao chỉ nên dùng tạm thời trong migration?

--add-modules và --add-reads là option hữu ích và có thể hợp lệ trong nhiều tình huống lâu dài được thiết kế rõ ràng, đặc biệt với plugin hoặc một môi trường launcher do người vận hành kiểm soát. Nhưng khi dùng để **bù cho cấu trúc JPMS thiếu chính xác**, chúng nên được xem là ngoại lệ có thời hạn.

### 8.1. Các rủi ro khi giữ flag như một dependency ẩn

- **Cấu hình khó tái lập:** build, test, IDE và production có bộ option khác nhau.
- **Dependency không được khai báo:** module-info.java không phản ánh những gì source hoặc runtime cần.
- **Phạm vi quá rộng:** ALL-MODULE-PATH resolve những module không liên quan; ALL-UNNAMED mở cầu nối tới toàn bộ classpath.
- **Lỗi được che tạm:** module đọc được nhưng package chưa export, reflection vẫn bị chặn hoặc API không tương thích.
- **Khó nâng version:** tên automatic module, dependency graph và runtime image thay đổi có thể làm flag hỏng.
- **Khó xác định owner:** một option nằm trong environment chung có thể được truyền vào nhiều process không ai quản lý.
- **Chi phí bảo mật/kiến trúc:** mở rộng đường truy cập giữa named module và unnamed module có thể làm yếu ranh giới đóng gói được thiết kế.

Không phải mọi read edge đều là vấn đề bảo mật: JPMS chủ yếu mang lại encapsulation và reliability của module graph. Tuy vậy, việc cấp quyền rộng hơn cần được xem xét trong cùng bối cảnh kiểm soát phụ thuộc và giảm truy cập ngoài thiết kế.

### 8.2. Hồ sơ ngoại lệ tạm thời nên có gì?

Ví dụ mô tả trong issue hoặc tài liệu deployment:

| Trường | Ví dụ |
|---|---|
| Process | orders-service trên JDK 21 |
| Flag | --add-reads com.company.orders=ALL-UNNAMED |
| Lý do | thư viện legacy-client chưa modular hóa |
| Owner | nhóm orders-platform |
| Phạm vi | chỉ task run/test/production của orders-service |
| Bằng chứng | lỗi compile/runtime khi bỏ flag, stack trace và module graph |
| Rủi ro | dependency classpath chưa thể được mô tả trong module-info |
| Hướng thay | nâng legacy-client và chuyển sang named/automatic module phù hợp |
| Điều kiện bỏ | build, test và runtime chạy không cần flag |
| Review date | kỳ nâng dependency tiếp theo |
| Theo dõi | issue/PR liên quan và compatibility test |

Một ngoại lệ tốt **có mô tả tác dụng cụ thể**, không phải một danh sách option copy từ một stack trace trên Internet.

### 8.3. Phạm vi hẹp nhất có thể

Ưu tiên:

~~~bash
--add-modules com.company.legacyadapter
--add-reads com.company.orders=com.company.legacyadapter
~~~

thay vì:

~~~bash
--add-modules ALL-MODULE-PATH
--add-reads com.company.orders=ALL-UNNAMED
~~~

nếu giải pháp theo tên module cụ thể đã đủ. ALL-UNNAMED có thể thật sự cần khi JAR legacy nằm trên classpath; khi ấy phải ghi lý do và xác định danh sách thư viện classpath liên quan, không coi nó như quyền mặc định cho mọi module.

Đừng thêm --add-exports hay --add-opens một cách dây chuyền chỉ vì thêm --add-reads chưa đủ. Mỗi option cần gắn với lỗi khác nhau và một kế hoạch loại bỏ tương ứng.

## 9. Lộ trình loại bỏ flag tạm thời

### Bước 1: Dựng baseline và tái hiện lỗi

Lưu command thực tế, JDK vendor/version, module path, classpath và lỗi khi bỏ flag. Chạy trên môi trường mô phỏng process production. Đừng phụ thuộc vào IDE có cấu hình khác.

### Bước 2: Xác định module graph thực tế

Dùng --show-module-resolution, jar --describe-module và jdeps. Xác định module nào observable, module nào resolved, module nào cần readability và package nào chưa export.

### Bước 3: Phân biệt nguyên nhân với triệu chứng

Nếu module chưa được resolve, tìm lý do tại sao nó không nằm trong graph: thiếu requires, thiếu root, service/plugin discovery hoặc module path sai. Nếu module đã resolve nhưng không được đọc, tìm dependency thiếu trong module-info.java. Nếu chỉ reflection thất bại, kiểm tra opens và cách thư viện sử dụng reflection.

### Bước 4: Thay bằng dependency/module descriptor rõ ràng

Những hướng thường dùng:
- Thêm requires vào module-info.java của module sở hữu dependency thật sự.
- Nếu public API của module A để lộ kiểu thuộc B, xem xét requires transitive khi phù hợp.
- Chỉnh exports/opens đúng package và đúng consumer, thay vì cấp quyền toàn cục.
- Nâng thư viện legacy để hỗ trợ JPMS hoặc giới hạn nó phía sau adapter.
- Sửa provider/uses/provides khi discovery theo ServiceLoader là nguyên nhân.
- Sửa module path, loại split package và bảo đảm runtime image chứa module cần thiết.

### Bước 5: Loại option từng bước

Loại lần lượt flag hẹp đã được thay bằng descriptor hoặc dependency đúng, chạy compile, unit test, integration test và smoke test trên JDK đích. Nếu có nhiều flag, việc bỏ từng flag giúp phát hiện ngoại lệ nào còn cần thiết.

### Bước 6: Khóa regression bằng CI

Khi JPMS structure đã ổn định, kiểm tra task chính chạy được mà không có các bypass flag cũ. Có thể thêm kiểm tra cấu hình launcher để tránh flag quay lại do copy template. Duy trì log/diagnostics cần thiết để nhận diện vấn đề khi nâng JDK hoặc dependency sau này.

## 10. Kịch bản migration minh họa

Một hệ thống ban đầu chạy trên classpath với JDK 8. Khi chuyển lên JDK 21, nhóm tạo module-info.java cho ứng dụng và đưa thư viện business mới lên module path. Một số JAR cũ vẫn nằm trên classpath.

Các triệu chứng được ghi nhận:

1. Một plugin JAR có mặt trên module path nhưng ứng dụng không nhìn thấy provider: kiểm tra root resolution và cấu hình ServiceLoader; nếu cần, tạm thêm module plugin bằng --add-modules.
2. Source của app nhập public type từ library module khác nhưng descriptor thiếu requires: để chuyển tiếp có thể thêm --add-reads, sau đó sửa module-info.java.
3. App cần gọi class legacy trên classpath: dùng --add-reads app=ALL-UNNAMED với phạm vi rõ, rồi nâng hoặc bao bọc thư viện legacy.
4. Reflection vào package nội bộ vẫn thất bại: không dùng thêm --add-reads như một phép sửa chung; xem lại opens, framework version và API replacement.
5. Một custom jlink runtime image không có module được yêu cầu: tạo lại image với module phù hợp, không chỉ sửa command-line flag.

Sau khi tái hiện, ghi chính xác option của từng process trong build, test và deployment. Lên kế hoạch thay từng flag bằng cấu trúc module bền vững, đồng thời kiểm tra hành vi ứng dụng thay vì chỉ xem JVM khởi động thành công.

## 11. Những nhầm lẫn thường gặp

- **Module có trên module path tức là app đọc được:** sai; nó còn cần resolved graph và readability.
- **--add-modules tự tạo read edge:** sai; option thêm root, không tự cho A reads B.
- **--add-reads tự giải quyết thiếu module:** sai; tên module đích phải được resolution xử lý phù hợp.
- **--add-reads tự export/open package:** sai; đây là một quan hệ khác.
- **Named module có thể đọc classpath mặc định:** thường phải xét riêng; ALL-UNNAMED là cầu nối tạm thời trong migration.
- **ALL-MODULE-PATH là cách dễ nhất và an toàn nhất:** resolve quá rộng có thể gây xung đột và che cấu trúc dependency sai.
- **Thêm flag chỉ vào javac là đủ:** runtime và test JVM có thể cần option tương ứng.
- **Thêm flag vào Gradle daemon là tự động ảnh hưởng app:** không; mỗi JVM/task có cấu hình riêng.
- **JPMS lỗi đều là do JDK nâng version:** có thể do module path, class loader, automatic module name, split package hoặc descriptor.
- **Runtime image có thể load module chưa được đóng gói:** không; custom image bị lược module cần được thay đổi.
- **Không cần theo dõi flag tạm:** những ngoại lệ không có owner thường tồn tại nhiều năm và làm tăng chi phí migration sau này.
- **Chạy được là đã tương thích hành vi:** module resolution thành công chưa chứng minh reflection, serialization, plugin discovery và hợp đồng nghiệp vụ đều đúng.

## 12. Checklist trước khi chấp nhận ngoại lệ module

- [ ] Đã xác định JDK vendor/version và lệnh chạy thực tế của process.
- [ ] Đã phân biệt classpath, module path và custom runtime image.
- [ ] Đã xác minh tên JPMS của từng module, kể cả automatic module.
- [ ] Đã xác định module nào observable, resolved và readable.
- [ ] Đã biết thiếu root module hay thiếu read edge; không thêm cả hai option theo thói quen.
- [ ] Đã phân biệt readability với exports và opens.
- [ ] Nếu dùng ALL-UNNAMED, đã ghi rõ thư viện classpath nào cần cầu nối.
- [ ] Đã áp dụng option đúng ở javac, Java launcher và test JVM theo nhu cầu.
- [ ] Đã review scope để tránh ALL-MODULE-PATH hoặc flag rộng không cần thiết.
- [ ] Đã kiểm tra runtime image có đủ module, không chỉ đường dẫn module path.
- [ ] Đã thực thi luồng chức năng, plugin discovery và reflection có liên quan.
- [ ] Mỗi ngoại lệ có owner, lý do, bằng chứng, điều kiện bỏ và ngày review.
- [ ] Đã có kế hoạch thay bằng requires, exports/opens, adapter hoặc cập nhật dependency.
- [ ] Đã kiểm chứng bước loại flag không làm hỏng build, test và runtime.

## 13. Kết luận

Trong JPMS, **--add-modules** điều chỉnh module được đưa vào quá trình resolution, còn **--add-reads** điều chỉnh quan hệ đọc từ một named module sang module khác hoặc unnamed modules. Hai tùy chọn xử lý hai mắt xích riêng biệt của module graph; chúng không thay thế exports, opens, Java access rules hoặc khả năng tương thích của bytecode và API.

Khi migration, hãy dùng chúng để giải quyết vấn đề đã xác định, với phạm vi nhỏ và bằng chứng cụ thể. Với dependency tĩnh giữa named modules, đích đến thường là khai báo requires đúng trong module-info.java; với thư viện legacy, cần kế hoạch modular hóa, nâng dependency hoặc tạo adapter. Các ngoại lệ chỉ nên được giữ khi có owner, kiểm thử và thời hạn xem xét, để cấu hình tạm thời không trở thành phụ thuộc ẩn của ứng dụng lâu dài.
