# Recursive analysis với jdeps

**jdeps** là công cụ phân tích dependency tĩnh đi kèm JDK. Công cụ đọc class file, thư mục class hoặc JAR để xác định package, class và module mà một thành phần Java tham chiếu. Chế độ **recursive analysis** mở rộng việc phân tích từ dependency trực tiếp sang các dependency ở những tầng tiếp theo, giúp nhìn thấy dependency graph cần thiết để hiểu cấu trúc ứng dụng.

Ví dụ, ứng dụng A gọi thư viện B, B sử dụng thư viện C, còn C phụ thuộc vào module D. Phân tích trực tiếp chỉ cho biết A cần B. Phân tích đệ quy tiếp tục đi từ B tới C và từ C tới D, giúp người phát triển thấy các dependency gián tiếp có thể ảnh hưởng tới đóng gói, nâng cấp, bảo mật hoặc chuyển đổi module.

Trong jdeps, tùy chọn **-R** hoặc **--recursive** yêu cầu công cụ duyệt đệ quy các runtime dependencies. Tùy chọn này cũng ngầm bật **-filter:none**, vì vậy kết quả có thể nhiều hơn đáng kể so với phân tích mặc định.

## 1. Dependency trực tiếp và dependency gián tiếp

Một dependency trực tiếp xuất hiện khi bytecode của class trong ứng dụng tham chiếu tới class hoặc package khác.

Ví dụ:

- Main gọi CustomerService.
- CustomerService tạo Customer.
- Customer dùng String từ java.base.

Đồ thị phụ thuộc:

~~~text
app.jar
  |
  v
service.jar
  |
  v
model.jar
  |
  v
java.base
~~~

Nếu chỉ phân tích app.jar mà không yêu cầu duyệt đệ quy, jdeps tập trung vào những dependency trực tiếp mà bytecode của app.jar tham chiếu. Khi dùng -R, jdeps tiếp tục phân tích các archive dependency được tìm thấy trên classpath/module path và mở rộng đồ thị.

Phân biệt:

| Loại dependency | Ý nghĩa | Ví dụ |
|---|---|---|
| Direct dependency | Thành phần đầu vào tham chiếu trực tiếp | app.jar dùng service.jar |
| Transitive dependency | Dependency được sử dụng bởi một dependency khác | service.jar dùng model.jar |
| JDK dependency | Dependency tới module/package của JDK | Class dùng java.base hoặc java.sql |
| Missing dependency | Class được tham chiếu nhưng không phân giải được trong môi trường phân tích | Thiếu một thư viện trên classpath |

Dependency gián tiếp vẫn có thể ảnh hưởng tới ứng dụng: thay đổi phiên bản của nó có thể gây xung đột, thiếu class hoặc thay đổi hành vi khi chạy.

## 2. Cú pháp recursive analysis

Cú pháp tổng quát:

~~~bash
jdeps --recursive [options] path...
~~~

Dạng viết tắt:

~~~bash
jdeps -R [options] path...
~~~

path có thể là:

- Một file .class.
- Một thư mục chứa class file.
- Một JAR.
- Một tên class đầy đủ để phân tích class file tương ứng.

Ví dụ đơn giản:

~~~bash
jdeps -R app.jar
~~~

Phân tích đệ quy cùng output theo package:

~~~bash
jdeps -R -verbose:package app.jar
~~~

Phân tích đệ quy theo class:

~~~bash
jdeps -R -verbose:class app.jar
~~~

Tóm tắt dependency:

~~~bash
jdeps -R -summary app.jar
~~~

Tùy chọn -R và --recursive tương đương nhau. Dùng dạng dài trong script mới để ý nghĩa rõ ràng; dạng ngắn thường xuất hiện trong tài liệu và câu lệnh hiện có.

## 3. -R thay đổi phạm vi phân tích như thế nào?

Theo manual của JDK, -R duyệt đệ quy các runtime dependencies và ngầm áp dụng -filter:none. Mặc định jdeps lọc một số dependency nội bộ package; các chế độ verbose cũng có bộ lọc mặc định riêng. Khi bật recursive, công cụ hiển thị các cạnh dependency mà bộ lọc mặc định có thể ẩn.

| Cấu hình | Phạm vi |
|---|---|
| jdeps app.jar | Phân tích dependency trực tiếp theo chế độ mặc định |
| jdeps -R app.jar | Duyệt runtime dependencies ở các tầng tiếp theo |
| jdeps --no-recursive app.jar | Không duyệt đệ quy dependency |
| jdeps -R -filter:none app.jar | Duyệt đệ quy và hiển thị dependency không bị lọc |
| jdeps -R -filter:archive app.jar | Duyệt đệ quy nhưng lọc các dependency trong cùng archive theo lựa chọn filter |

Vì -R đã ngầm bật -filter:none, không cần thêm -filter:none trong lệnh thông thường. Có thể dùng filter khác khi muốn giới hạn output; tùy chọn filter được chỉ định vẫn có hiệu lực.

Kết quả recursive có thể chứa nhiều dòng hơn, bao gồm dependency nội bộ cùng archive, cùng package và dependency từ các thư viện được phân giải. Khi output quá lớn, hãy chọn chế độ package, summary hoặc lọc theo package/class cần điều tra.

## 4. Recursive analysis cần classpath hoặc module path đúng

Recursive analysis chỉ có thể đi tiếp khi jdeps tìm thấy dependency để phân tích. Tùy chọn -R không tự tải thư viện từ Maven Central, không tự đoán phiên bản và không thay thế cấu hình dependency của build tool.

### Ứng dụng dùng classpath

Dùng **--class-path** để chỉ định JAR hoặc thư mục class cần phân giải:

~~~bash
jdeps -R --class-path "lib/service.jar:lib/model.jar" app.jar
~~~

Trên Windows, dùng dấu chấm phẩy làm path separator:

~~~powershell
jdeps -R --class-path "lib\service.jar;lib\model.jar" app.jar
~~~

Nếu có nhiều dependency, liệt kê tất cả thư viện cần thiết. Có thể chỉ định thư mục chứa class đã biên dịch cùng các JAR.

### Ứng dụng modular

Dùng **--module-path** để chỉ định nơi chứa named modules hoặc automatic modules:

~~~bash
jdeps -R --module-path mods --module com.acme.app
~~~

Có thể chỉ định thêm root module bằng --add-modules khi phân tích cần một tập module cụ thể:

~~~bash
jdeps -R --module-path mods --add-modules com.acme.app,com.acme.reporting
~~~

Với module system, hãy kiểm tra module name trong module-info.class hoặc tên automatic module của JAR. Tên file JAR không nhất thiết trùng tên module.

### Những đường dẫn khác

jdeps còn hỗ trợ:

- **--upgrade-module-path**: chỉ định upgrade module path.
- **--system**: chọn system module path của một Java home khác.
- **--multi-release**: chọn phiên bản entry khi phân tích multi-release JAR.

Các tùy chọn này hữu ích khi phân tích artifact được build cho một runtime hoặc Java release cụ thể.

## 5. Ví dụ hoàn chỉnh: app phụ thuộc qua nhiều tầng JAR

Tạo một project nhỏ với ba JAR:

~~~text
project/
  src/
    model/com/acme/model/Customer.java
    service/com/acme/service/CustomerService.java
    app/com/acme/app/Main.java
  lib/
  build/
~~~

### JAR model

Tệp src/model/com/acme/model/Customer.java:

~~~java
package com.acme.model;

public record Customer(String name) {
}
~~~

Biên dịch và đóng gói:

~~~bash
javac --release 17 -d build/model src/model/com/acme/model/Customer.java
jar --create --file lib/model.jar -C build/model .
~~~

### JAR service

Tệp src/service/com/acme/service/CustomerService.java:

~~~java
package com.acme.service;

import com.acme.model.Customer;

public class CustomerService {
    public Customer load() {
        return new Customer("Ada Lovelace");
    }
}
~~~

Biên dịch với model.jar trên classpath:

~~~bash
javac --release 17 --class-path lib/model.jar -d build/service src/service/com/acme/service/CustomerService.java
jar --create --file lib/service.jar -C build/service .
~~~

### JAR app

Tệp src/app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.service.CustomerService;

public class Main {
    public static void main(String[] args) {
        var customer = new CustomerService().load();
        System.out.println(customer.name());
    }
}
~~~

Biên dịch app với service.jar và model.jar:

Linux/macOS:

~~~bash
javac --release 17 --class-path "lib/service.jar:lib/model.jar" -d build/app src/app/com/acme/app/Main.java
~~~

Windows PowerShell:

~~~powershell
javac --release 17 --class-path "lib\service.jar;lib\model.jar" -d build\app src\app\com\acme\app\Main.java
~~~

Đóng gói app:

~~~bash
jar --create --file lib/app.jar -C build/app .
~~~

Chạy ứng dụng để xác nhận dependency hoạt động:

Linux/macOS:

~~~bash
java --class-path "lib/app.jar:lib/service.jar:lib/model.jar" com.acme.app.Main
~~~

Windows PowerShell:

~~~powershell
java --class-path "lib\app.jar;lib\service.jar;lib\model.jar" com.acme.app.Main
~~~

Stdout:

~~~text
Ada Lovelace
~~~

### Phân tích trực tiếp và đệ quy

Phân tích app.jar:

~~~bash
jdeps --verbose:package --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Phân tích đệ quy:

~~~bash
jdeps -R --verbose:package --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Lệnh thứ hai bắt đầu từ app.jar, sau đó phân tích service.jar và model.jar khi các dependency này được phân giải. Kết quả có thể cho thấy các cạnh như:

~~~text
app.jar -> service.jar
service.jar -> model.jar
app.jar -> java.base
service.jar -> java.base
model.jar -> java.base
~~~

Đây là sơ đồ quan hệ archive minh họa, không phải output nguyên văn cố định. Output thực tế phụ thuộc JDK, chế độ verbose, class được phân tích, đường dẫn thư viện và dependency mà compiler tạo ra.

Phân tích class-level chi tiết:

~~~bash
jdeps -R --verbose:class --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Chế độ này hữu ích khi muốn biết chính xác class nào tham chiếu tới class nào. Nếu chỉ cần bức tranh tổng quát, dùng -verbose:package hoặc -summary để giảm lượng output.

## 6. Recursive analysis ở cấp module

Với ứng dụng modular, jdeps có thể liệt kê module dependency và phân tích transitive dependencies của thư viện trên module path nếu chúng được tham chiếu.

Ví dụ:

~~~bash
jdeps --list-deps --module-path mods --module com.acme.app
~~~

--list-deps liệt kê module dependencies và package của JDK internal APIs nếu có tham chiếu. Tùy chọn này đã phân tích đệ quy các thư viện trên classpath/module path khi được tham chiếu.

Nếu chỉ muốn dependency trực tiếp, dùng:

~~~bash
jdeps --list-deps --no-recursive --module-path mods --module com.acme.app
~~~

Để xem dependency sau khi loại các cạnh đọc module đã được suy ra từ requires transitive:

~~~bash
jdeps --list-reduced-deps --module-path mods --module com.acme.app
~~~

Để in danh sách module dạng phân tách bằng dấu phẩy:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.app
~~~

Output của --print-module-deps có thể dùng làm đầu vào cho jlink:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime
~~~

Khi dùng kết quả này, vẫn cần kiểm tra module root và các service/runtime requirement của ứng dụng. Một danh sách dependency tĩnh không thay thế test của custom runtime image.

## 7. Chọn mức chi tiết của output

jdeps có nhiều chế độ hiển thị:

| Tùy chọn | Output |
|---|---|
| Mặc định | Dependency theo package |
| -verbose:package | Dependency package-level |
| -verbose:class | Dependency class-level |
| -v hoặc -verbose | Tất cả class-level dependencies; tương đương -verbose:class -filter:none |
| -s hoặc -summary | Tóm tắt dependency theo archive |
| --list-deps | Danh sách module dependency |
| --list-reduced-deps | Module dependency sau khi loại implied reads |
| --print-module-deps | Danh sách module dạng comma-separated |

Ví dụ:

~~~bash
jdeps -R -summary --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Dùng summary để trả lời câu hỏi "ứng dụng này kéo theo những archive/module nào?". Dùng package-level để tìm nhóm API được sử dụng. Dùng class-level khi cần điều tra một dependency cụ thể hoặc tìm đường dẫn tham chiếu.

## 8. Lọc dependency trong recursive analysis

Phân tích đệ quy có thể tạo output lớn. jdeps hỗ trợ lọc theo package, regex, module hoặc class.

### Lọc theo package

~~~bash
jdeps -R --package com.acme.model --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Có thể dùng -p hoặc --package. Tùy chọn này tìm các dependency khớp package được chỉ định và có thể được lặp lại cho nhiều package. Nó không dùng đồng thời với -e/--regex.

### Lọc theo regular expression

~~~bash
jdeps -R --regex "com\.acme\..*" --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

-e hoặc --regex lọc dependency theo pattern. Dùng khi muốn tìm nhiều package thuộc cùng namespace.

### Lọc theo module

~~~bash
jdeps -R --require java.sql --module-path mods --module com.acme.app
~~~

--require tìm dependency khớp tên module. Nó không dùng đồng thời với --package hoặc --regex.

### Giới hạn class được phân tích bằng -include

~~~bash
jdeps -R -include "com\.acme\.app\..*" --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

-include giới hạn tập class được phân tích. Nó khác với --package và --regex, vốn lọc dependency được tìm thấy. Có thể kết hợp -include với -p hoặc -e khi muốn giới hạn cả class nguồn và dependency được báo cáo.

### Lọc các cạnh dependency

Các chế độ filter phổ biến:

| Tùy chọn | Ý nghĩa |
|---|---|
| -filter:package | Lọc dependency trong cùng package; là mặc định |
| -filter:archive | Lọc dependency trong cùng archive |
| -filter:module | Lọc dependency trong cùng module |
| -filter:none | Không lọc theo package/archive |
| -filter regex | Lọc dependency khớp regular expression |

-R ngầm bật -filter:none. Nếu thêm một filter cụ thể, filter đó vẫn được áp dụng. Khi kết quả quá rộng, nên lọc có chủ đích và ghi lại tùy chọn đã dùng để người khác có thể tái tạo phân tích.

## 9. Recursive analysis và inverse analysis

**Recursive analysis** đi xuôi từ thành phần đầu vào tới dependency của nó:

~~~text
app -> service -> model -> java.base
~~~

**Inverse analysis** đi theo chiều ngược: tìm những artifact trực tiếp hoặc gián tiếp phụ thuộc vào một module, package hoặc regex mục tiêu.

Dùng **-I** hoặc **--inverse** cùng với --require, --package hoặc --regex.

Ví dụ tìm artifact phụ thuộc vào package model:

~~~bash
jdeps --inverse --package com.acme.model --class-path "lib/model.jar:lib/service.jar" lib/app.jar lib/service.jar
~~~

Ví dụ tìm module phụ thuộc vào java.sql:

~~~bash
jdeps --inverse --require java.sql --module-path mods
~~~

Inverse analysis hữu ích khi:

- Muốn biết thư viện nào bị ảnh hưởng nếu một package bị loại bỏ.
- Chuẩn bị nâng cấp hoặc thay thế dependency.
- Tìm consumer của một module nội bộ.
- Điều tra tác động khi chuyển API sang module khác.

Không nhầm -R với --inverse: -R mở rộng dependency theo hướng mà đầu vào sử dụng; --inverse tìm artifact sử dụng mục tiêu được lọc.

## 10. Tạo dependency graph bằng DOT

Có thể yêu cầu jdeps xuất graph để trực quan hóa dependency:

~~~bash
jdeps -R --dot-output build/jdeps-dot --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Tùy chọn --dot-output tạo thư mục chứa file DOT cho từng archive được phân tích và file tổng hợp **summary.dot** mô tả dependency giữa các archive.

Cấu trúc output minh họa:

~~~text
build/
  jdeps-dot/
    app.jar.dot
    service.jar.dot
    model.jar.dot
    summary.dot
~~~

Tên file cụ thể phụ thuộc các archive đầu vào và dependency được phân giải.

Nếu đã cài Graphviz, chuyển summary.dot thành SVG:

~~~bash
dot -Tsvg build/jdeps-dot/summary.dot -o build/jdeps-summary.svg
~~~

Hoặc tạo ảnh PNG:

~~~bash
dot -Tpng build/jdeps-dot/summary.dot -o build/jdeps-summary.png
~~~

Graph giúp nhận diện:

- Dependency nhiều tầng.
- Archive có quá nhiều dependency đi ra.
- Dependency vòng giữa các archive.
- Thư viện dùng chung bởi nhiều thành phần.
- Các điểm có thể tách module hoặc thay thế dependency.

Graph thể hiện dependency mà jdeps phát hiện từ bytecode và module metadata. Nó không tự chứng minh thứ tự khởi tạo hoặc luồng thực thi runtime.

## 11. Tìm dependency bị thiếu

Khi một class tham chiếu tới class khác nhưng jdeps không thể phân giải, kết quả có thể chứa cảnh báo missing dependency.

Dùng:

~~~bash
jdeps --missing-deps --class-path "lib/service.jar" lib/app.jar
~~~

--missing-deps tìm dependency không phân giải được. Tùy chọn này không dùng cùng -p, -e hoặc -s.

Nếu cần phân tích một archive cô lập, có thể dùng:

~~~bash
jdeps --ignore-missing-deps -R app.jar
~~~

--ignore-missing-deps bỏ qua dependency bị thiếu trong một số dạng phân tích. Nó không sửa classpath, không bổ sung thư viện và không chứng minh ứng dụng có thể chạy. Chỉ dùng khi hiểu rõ vì sao dependency không có mặt trong môi trường phân tích.

Cách xử lý missing dependency:

1. Đọc class nguồn và class đích được nêu trong cảnh báo.
2. Xác định JAR hoặc module cung cấp class đích.
3. Thêm đúng artifact vào --class-path hoặc --module-path.
4. Kiểm tra package path và module exports.
5. Chạy lại jdeps.
6. Chạy test ứng dụng với cùng tập dependency.

Nếu dependency thực sự không được đóng gói, cần sửa build configuration hoặc dependency declaration thay vì che cảnh báo.

## 12. Tìm JDK internal API trong dependency graph

Một thư viện có thể phụ thuộc vào API nội bộ của JDK, chẳng hạn package thuộc jdk.internal.* hoặc com.sun.*. Những API này không phải hợp đồng public ổn định và có thể thay đổi hoặc bị đóng quyền truy cập giữa các JDK release.

Dùng:

~~~bash
jdeps -R --jdk-internals --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Tùy chọn --jdk-internals tìm class-level dependency tới JDK internal APIs. Manual cảnh báo các API nội bộ có thể không truy cập được. Hãy xem cả dependency bắc cầu, vì internal API có thể được sử dụng trong một thư viện bên ngoài chứ không xuất hiện trực tiếp trong source của ứng dụng.

Khi phát hiện:

- Xác định artifact và class chứa tham chiếu.
- Tìm public API thay thế được Oracle/JDK cung cấp.
- Nâng cấp thư viện bên thứ ba nếu nhà cung cấp đã sửa.
- Kiểm tra lại trên JDK mục tiêu.
- Tránh dùng --add-exports như một giải pháp lâu dài nếu có API công khai thay thế.

Tùy chọn --jdk-internals không dùng cùng -p, -e hoặc -s theo manual. Nếu cần kết quả class-level, để chế độ mặc định của tùy chọn này hoặc dùng các tổ hợp được jdeps hỗ trợ.

## 13. Recursive analysis cho multi-release JAR

Multi-release JAR chứa các class implementation khác nhau theo Java release, thường nằm dưới META-INF/versions/N/.

Dùng --multi-release để chỉ định phiên bản cần phân tích:

~~~bash
jdeps -R --multi-release 17 --class-path "lib/dependency.jar" app.jar
~~~

Giá trị có thể là một số release từ 9 trở lên hoặc base để phân tích entry nền. Hãy dùng cùng release mục tiêu với runtime mà ứng dụng sẽ chạy để kết quả phản ánh đúng class implementation được chọn.

Khi so sánh hai release:

~~~bash
jdeps -R --multi-release 17 --class-path "lib/dependency.jar" app.jar
jdeps -R --multi-release 21 --class-path "lib/dependency.jar" app.jar
~~~

Sự khác biệt có thể đến từ class được chọn trong multi-release JAR. Không kết luận dependency thay đổi nếu chưa xác nhận cùng artifact, cùng module path và cùng cấu hình phân tích.

## 14. API-only và compile-time dependency

Không phải mọi dependency trong bytecode đều là một phần của public API. jdeps có tùy chọn **--api-only** để giới hạn phân tích vào API signatures, ví dụ kiểu của field, tham số method, kiểu trả về và checked exceptions trong public/protected members của public classes.

Ví dụ:

~~~bash
jdeps -R --api-only --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Chế độ này hữu ích khi muốn biết dependency nào lộ ra qua API công khai và có thể ảnh hưởng consumer khi thay đổi thư viện.

Tùy chọn **--compile-time** phân tích compile-time view của transitive dependencies. Nó phù hợp khi cần hiểu các dependency cần thiết trong quá trình biên dịch, đặc biệt khi phân tích một directory, JAR hoặc module có nhiều class.

Ví dụ:

~~~bash
jdeps --compile-time --class-path "lib/service.jar:lib/model.jar" lib/app.jar
~~~

Phân biệt API-only và compile-time:

- API-only tập trung vào dependency xuất hiện trong public/protected API signatures.
- Compile-time xem xét dependency cần thiết cho compile-time view.
- Recursive runtime analysis theo -R duyệt runtime dependencies.

Chọn chế độ theo câu hỏi cần trả lời; chúng không thay thế lẫn nhau.

## 15. Giới hạn của recursive analysis

jdeps là static analyzer. Công cụ đọc class file và module metadata, không chạy ứng dụng để quan sát mọi đường đi thực tế.

Các trường hợp có thể không được phản ánh đầy đủ:

- Nạp class bằng reflection từ tên được tạo trong runtime.
- Class.forName với chuỗi lấy từ file cấu hình hoặc database.
- Plugin được phát hiện và nạp động theo thư mục.
- Bytecode được tạo trong lúc chạy.
- Dependency được chọn qua environment variable hoặc feature flag.
- Tài nguyên/service được tìm qua cơ chế không biểu hiện thành dependency class thông thường.

Vì vậy:

1. Dùng jdeps để hiểu dependency tĩnh.
2. Kiểm tra build descriptor của Maven/Gradle để biết dependency được khai báo.
3. Kiểm tra cấu hình runtime, plugin và reflection.
4. Chạy integration test trên đúng runtime.
5. Theo dõi lỗi nạp class và module khi chạy.

Một kết quả jdeps sạch không bảo đảm ứng dụng không cần dependency động. Ngược lại, dependency được phát hiện không nhất thiết được thực thi trong mọi luồng chạy.

## 16. Quy trình phân tích dependency đệ quy

1. **Chọn đầu vào**: xác định JAR, thư mục class hoặc module cần phân tích.
2. **Chuẩn bị đường dẫn**: cung cấp toàn bộ dependency cần phân giải bằng --class-path hoặc --module-path.
3. **Chạy baseline**: dùng jdeps mặc định để xem dependency trực tiếp.
4. **Bật recursive**: dùng -R hoặc --recursive để duyệt runtime dependencies.
5. **Chọn mức chi tiết**: package, class hoặc summary tùy mục tiêu.
6. **Lọc kết quả**: dùng --package, --regex, --require hoặc -include khi cần.
7. **Tìm thiếu dependency**: chạy --missing-deps và xử lý class không phân giải được.
8. **Kiểm tra internal APIs**: chạy --jdk-internals nếu chuẩn bị nâng cấp JDK.
9. **Xuất graph**: dùng --dot-output khi cần trực quan hóa quan hệ giữa archive.
10. **Kiểm tra module dependencies**: dùng --list-deps hoặc --print-module-deps với ứng dụng modular.
11. **Đối chiếu runtime**: kiểm tra reflection, plugin, service và dependency động.
12. **Lưu lệnh và môi trường**: ghi lại JDK version, classpath/module path và tùy chọn để có thể tái lập phân tích.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy dependency bắc cầu | Chưa bật -R hoặc dependency không được phân giải | Dùng -R và cung cấp classpath/module path |
| Output quá lớn | -R ngầm dùng -filter:none | Dùng summary/package output hoặc lọc có chủ đích |
| Báo missing dependency | Thiếu JAR/module hoặc sai đường dẫn | Bổ sung artifact và chạy lại |
| Chỉ thấy package thay vì class | Đang dùng output mặc định/package | Dùng -verbose:class |
| Không thấy cạnh nội bộ archive | Bộ lọc mặc định đang loại dependency đó | Dùng -R hoặc -filter:none |
| Tên module không được nhận diện | Module path hoặc module name sai | Kiểm tra module-info.class và --module-path |
| Kết quả khác giữa các Java release | Multi-release JAR chọn class khác nhau | Chỉ định --multi-release rõ ràng |
| Không tìm được thư viện được nạp bằng reflection | Dependency không hiện thành tham chiếu bytecode tĩnh | Kiểm tra cấu hình runtime và integration test |
| DOT graph thiếu archive | Dependency không được phân giải hoặc không thuộc phạm vi đầu vào | Kiểm tra classpath/module path và đầu vào |
| Cảnh báo internal API từ thư viện bên thứ ba | Dependency bắc cầu sử dụng JDK internal API | Xác định artifact và nâng cấp/thay thế thư viện |

## 18. Ghi nhớ

- jdeps phân tích dependency tĩnh từ class file, directory, JAR hoặc module.
- -R và --recursive duyệt runtime dependencies qua nhiều tầng.
- -R ngầm bật -filter:none, nên output có thể rất lớn.
- --no-recursive giới hạn phân tích ở dependency trực tiếp.
- Recursive analysis cần classpath/module path đúng để tìm thư viện ở các tầng tiếp theo.
- --list-deps tự phân tích transitive library dependencies trên classpath/module path; có thể dùng --no-recursive để giới hạn.
- --inverse tìm artifact trực tiếp và gián tiếp phụ thuộc vào package, regex hoặc module được chỉ định.
- --dot-output tạo DOT graph và summary.dot để trực quan hóa dependency giữa archive.
- --missing-deps tìm dependency không phân giải được; --ignore-missing-deps chỉ bỏ qua cảnh báo, không sửa nguyên nhân.
- --jdk-internals phát hiện dependency tới JDK internal APIs.
- --multi-release chọn implementation trong multi-release JAR cần phân tích.
- jdeps không phát hiện đầy đủ dependency được nạp động hoặc bằng reflection; cần kết hợp kiểm tra runtime và test.

## Tài liệu tham khảo chính thức

- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Java Platform Module System — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/)