# Module patching và rủi ro production

## 1. Module patching trong JPMS là gì?

Java Platform Module System (JPMS) tổ chức class và resource theo module có tên. Khi một named module được resolve và nạp, các class của module đó thuộc về module và class loader tương ứng. Trong một số tình huống cần thay thế hoặc bổ sung class/resource của module mà không sửa trực tiếp JAR gốc, Java cung cấp tùy chọn **--patch-module**.

\`--patch-module\` cho phép thêm một hoặc nhiều thư mục/JAR vào nội dung của một module đã tồn tại. Khi class hoặc resource cùng đường dẫn xuất hiện cả trong patch path và module gốc, nội dung trên patch path được tìm trước. Vì vậy, patch có thể ghi đè class/resource cùng tên hoặc bổ sung class/resource mới vào module.

Cú pháp tổng quát:

~~~text
--patch-module module=patch-path
~~~

Trong đó:

- \`module\` là tên named module cần patch, ví dụ \`com.acme.core\` hoặc \`java.base\`.
- \`patch-path\` là một hoặc nhiều thư mục/JAR chứa class và resource cần bổ sung.
- Nhiều entry được nối bằng path separator của hệ điều hành: \`:\` trên Linux/macOS và \`;\` trên Windows.

Ví dụ:

~~~bash
java --patch-module=com.acme.core=patches/com.acme.core ...
~~~

Tùy chọn này có thể xuất hiện trong môi trường compile hoặc lúc khởi chạy JVM. Hai nơi có vai trò khác nhau và cần được cấu hình nhất quán.

## 2. Patch module khác gì thay JAR hoặc sửa module descriptor?

Module patching tác động tới nội dung class/resource được nạp cho một module trong lần chạy JVM đó. Nó không tự sửa JAR gốc trên đĩa, không tạo một bản phát hành mới và không thay thế module descriptor.

Một số điểm cần phân biệt:

- **Thay JAR:** thay artifact gốc bằng một artifact khác trong module path. Đây thường là cách phát hành phiên bản sửa lỗi chính thức.
- **--patch-module:** giữ artifact gốc trong module path, đồng thời bổ sung nội dung patch được ưu tiên tìm trước nội dung module.
- **--add-exports:** bổ sung quyền truy cập public types của package cho module đích.
- **--add-opens:** mở package cho deep reflection tại runtime.
- **Java agent/instrumentation:** có cơ chế riêng để biến đổi hoặc redefine class trong JVM đang chạy, với các giới hạn của Instrumentation API.

\`--patch-module\` không phải cơ chế hot patch một process đang hoạt động. Patch path được áp dụng khi JVM khởi động và module được thiết lập; thay đổi file trên đĩa sau khi class đã được nạp không làm class trong bộ nhớ tự thay đổi.

Module descriptor vẫn là descriptor của module gốc. Patch không tự thêm chỉ thị \`requires\`, \`exports\`, \`opens\`, \`uses\` hoặc \`provides\`. Nếu patch bổ sung một package mới, package đó thuộc nội dung module khi được nạp, nhưng không tự động trở thành package được export cho module khác. Nếu cần quyền truy cập module, phải xử lý riêng bằng descriptor phù hợp hoặc tùy chọn access tương ứng.

## 3. Khi nào nên dùng module patching?

Một số trường hợp có thể cân nhắc:

1. **Kiểm thử module:** thêm test class vào chính module đang kiểm thử để test có thể truy cập package-private API theo cùng module boundary.
2. **Kiểm thử JDK hoặc framework:** thay một class/resource trong module để tái hiện lỗi, kiểm tra hành vi hoặc xác minh bản sửa trước khi có artifact chính thức.
3. **Tương thích tạm thời:** áp dụng một bản sửa nhỏ trong môi trường kiểm soát khi chưa thể phát hành ngay dependency mới.
4. **Bổ sung resource:** cung cấp resource được module tìm qua module/class loader, ví dụ dữ liệu kiểm thử hoặc cấu hình phục vụ một lần chạy đặc biệt.
5. **Điều tra sự cố:** thử một implementation thay thế để xác định lỗi có nằm trong một class cụ thể hay không.

Với production, patching chỉ nên là ngoại lệ có chủ sở hữu, thời hạn và kế hoạch loại bỏ rõ ràng. Nếu đã xác nhận bản sửa là cần thiết lâu dài, nên cập nhật source và phát hành lại module/JAR chính thức. Việc giữ một patch riêng bên ngoài artifact làm tăng số thành phần phải kiểm soát và có thể khiến môi trường chạy không còn tái lập được từ dependency declaration thông thường.

## 4. Patch class và resource

Giả sử module \`com.acme.core\` chứa:

~~~text
com.acme.core.jar
  module-info.class
  com/acme/core/Parser.class
  com/acme/core/internal/TokenReader.class
  com/acme/core/messages.properties
~~~

Ta muốn thay \`Parser.class\` và resource \`messages.properties\`. Patch directory có cấu trúc tương ứng:

~~~text
patches/com.acme.core/
  com/acme/core/Parser.class
  com/acme/core/messages.properties
~~~

Khi khởi chạy:

~~~bash
java \
  --patch-module=com.acme.core=patches/com.acme.core \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

JVM tìm class/resource trên patch path trước nội dung gốc của module. Nếu patch có \`com/acme/core/Parser.class\`, class đó được dùng thay cho class cùng tên trong module gốc. Nếu patch có resource mới mà module gốc không chứa, module có thể truy cập resource đó qua cơ chế resource lookup thích hợp.

Cần giữ đúng package path và tên resource. Tên class Java phân biệt chữ hoa/chữ thường trên nhiều filesystem. Patch directory phải là root của cây package; không đặt thêm một tầng thư mục tùy ý khiến đường dẫn entry không còn khớp với tên class/resource.

Một patch JAR cũng có thể được dùng:

~~~bash
java \
  --patch-module=com.acme.core=patches/core-fix.jar \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Khi có nhiều patch entry, nối chúng bằng path separator của hệ điều hành. Hãy giữ danh sách entry ngắn và rõ thứ tự để người vận hành có thể xác định chính xác nguồn class đang được nạp.

## 5. Dùng --patch-module khi compile

Compiler cũng hỗ trợ \`--patch-module\`. Cách này hữu ích khi biên dịch source cần được xem như một phần của module đã tồn tại, chẳng hạn test code cần truy cập package-private members hoặc source thay thế cho một class trong module.

Ví dụ module chính đã được biên dịch nằm trong \`mods\`, còn source patch nằm trong \`src/patches/com.acme.core\`:

~~~bash
mkdir -p build/patches/com.acme.core

javac \
  --module-path mods \
  --patch-module com.acme.core=src/patches/com.acme.core \
  -d build/patches/com.acme.core \
  src/patches/com.acme.core/com/acme/core/Parser.java
~~~

Kết quả là class đã biên dịch nằm trong patch output. Khi chạy ứng dụng, phải truyền đúng output đó cho JVM:

~~~bash
java \
  --patch-module=com.acme.core=build/patches/com.acme.core \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Nếu chỉ dùng patch khi compile mà không dùng patch tương ứng khi runtime, compiler và JVM có thể nhìn thấy hai implementation khác nhau. Ngược lại, chỉ patch runtime mà không compile/test với đúng source và API tương ứng có thể dẫn tới lỗi linkage hoặc hành vi không mong đợi.

Khi patch một module JDK hoặc chạy test cần truy cập package nội bộ, có thể cần các tùy chọn access bổ sung tùy mục tiêu compile. \`--patch-module\` không tự export package hoặc mở package cho reflection.

## 6. Module patching trong unit test

Một ứng dụng modular thường muốn test class nằm trong cùng module với code cần kiểm thử. Điều này cho phép test gọi package-private method hoặc truy cập package-private type mà không phải biến implementation thành public API chỉ để phục vụ test.

Ví dụ source tree:

~~~text
src/main/java/
  module-info.java
  com/acme/core/Parser.java

src/test/java/
  com/acme/core/ParserTest.java
~~~

Nếu test được biên dịch như patch của module \`com.acme.core\`, nó có thể tham gia cùng module boundary với code chính. Một lệnh minh họa:

~~~bash
javac \
  --module-path mods:test-libs \
  --patch-module com.acme.core=src/test/java \
  -d build/test-patches/com.acme.core \
  src/test/java/com/acme/core/ParserTest.java
~~~

Cấu hình test thực tế còn phụ thuộc framework test, module chứa JUnit và cách build tool tạo test runtime. Có thể cần thêm readability hoặc access options để module được patch đọc module test framework. Không nên thêm \`opens\` hoặc \`--add-opens\` rộng nếu test chỉ cần gọi package-private API trong cùng module.

Khi chạy test, phải đưa patch output vào JVM:

~~~bash
java \
  --patch-module=com.acme.core=build/test-patches/com.acme.core \
  --module-path mods:test-libs \
  ...
~~~

Với Gradle hoặc Maven, kiểm tra command line compiler và test JVM mà build tool thực sự tạo ra. Đừng giả định một cấu hình compiler argument sẽ tự được chuyển sang test runtime.

## 7. Patch module JDK

Có thể gặp các ví dụ patch module nền tảng, chẳng hạn \`java.base\`, trong kiểm thử JDK hoặc điều tra một lỗi phụ thuộc vào implementation detail của runtime.

Ví dụ hình thức:

~~~bash
java \
  --patch-module=java.base=patches/java.base \
  -jar diagnostic-tool.jar
~~~

Đây là thao tác có rủi ro cao hơn patch một module ứng dụng:

- Module nền tảng được nhiều thành phần JVM và thư viện dùng chung.
- Một class thay thế có thể ảnh hưởng tới nhiều subsystem không liên quan trực tiếp đến ứng dụng đang điều tra.
- Implementation detail có thể thay đổi giữa JDK vendor, bản cập nhật và phiên bản Java.
- Một class patch không tương thích có thể làm JVM hoặc công cụ nền tảng lỗi trước khi ứng dụng khởi động.
- Patch có thể làm sai lệch hành vi mà các công cụ giám sát hoặc kiểm tra bảo mật mong đợi.

Chỉ thử nghiệm với JDK cụ thể, trong môi trường cô lập và có thể dựng lại. Không lấy patch dành cho một bản JDK rồi triển khai sang bản cập nhật hoặc vendor khác mà không build và kiểm thử lại.

## 8. Rủi ro production khi patch module

### 8.1. Ghi đè implementation ngoài quy trình phát hành

Patch class cùng tên có thể thay implementation trong module gốc. Người vận hành nhìn thấy JAR/version gốc vẫn đúng, nhưng code thực sự chạy đến từ patch path.

Nếu patch không được quản lý như artifact phát hành, quá trình điều tra có thể khó xác định vì sao hai instance cùng version lại có hành vi khác nhau.

### 8.2. Lỗi tương thích nhị phân

Class patch có thể được compile dựa trên một API khác với API runtime. Những khác biệt về method, field, constructor, modifier hoặc hierarchy có thể gây:

- \`NoSuchMethodError\`
- \`NoSuchFieldError\`
- \`AbstractMethodError\`
- \`IncompatibleClassChangeError\`
- \`VerifyError\`
- \`ClassCastException\`
- \`NoClassDefFoundError\`

Không phải mọi lỗi đều xuất hiện ngay lúc startup. Một nhánh code ít dùng có thể chỉ thất bại khi production nhận một request hoặc tải một plugin cụ thể.

### 8.3. Thay đổi hành vi security

Một class trong module có thể thực hiện xác thực, kiểm tra quyền, parsing input, kiểm tra certificate hoặc quản lý tài nguyên. Patch sai hoặc không được review có thể bỏ qua validation, làm thay đổi trust boundary hoặc mở rộng khả năng truy cập.

Vì vậy, patch artifact cần cùng quy trình review, kiểm soát nguồn và kiểm tra bảo mật như code chính. Không lấy patch từ một nguồn không xác minh và không cho phép người dùng không tin cậy ghi vào patch directory.

### 8.4. Sai lệch module boundary

Patch không thay thế module descriptor. Nó không tự tạo dependency, export hoặc opens cần thiết. Một patch có thể thêm class vào package nhưng caller ở module khác vẫn không truy cập được nếu package chưa export; reflection vẫn bị chặn nếu package chưa mở.

Cố thêm nhiều flag \`--add-exports\` hoặc \`--add-opens\` để làm patch chạy được có thể che giấu một thay đổi kiến trúc rộng hơn. Hãy xác định chính xác module/package/target cần quyền và giới hạn quyền ở mức nhỏ nhất.

### 8.5. Khó tái lập và rollback

Nếu patch được mount từ volume hoặc copy thủ công vào container, hai instance có thể chạy patch khác nhau dù cùng image tag. Nếu patch path được lưu trong biến môi trường hoặc script bên ngoài, cấu hình đó có thể bị bỏ sót trong quy trình phát hành.

Rollback cũng cần khôi phục đồng thời:
- JAR/module gốc.
- Patch directory/JAR và thứ tự patch path.
- JVM flags.
- Cấu hình container hoặc service.
- Bản ghi version/hash của patch.

Chỉ rollback JAR gốc mà quên patch path có thể không khôi phục hành vi ban đầu.

## 9. Kiểm soát patch trước khi triển khai

Nếu buộc phải dùng patch trong production, hãy coi patch là một artifact độc lập có version và provenance.

Một quy trình kiểm soát nên có:

1. **Lý do rõ ràng:** ghi lại lỗi hoặc yêu cầu tương thích mà patch giải quyết.
2. **Source có quản lý:** lưu patch source trong repository hoặc hệ thống artifact được kiểm soát.
3. **Build tái lập:** compile với đúng JDK, module graph và compiler options.
4. **Hash artifact:** ghi SHA-256 của patch JAR hoặc manifest của patch directory.
5. **Compatibility check:** xác nhận patch được compile với đúng version module gốc và chạy trên đúng JDK vendor/update.
6. **Automated tests:** chạy unit, integration và regression tests trên đúng runtime image có patch.
7. **Security review:** review thay đổi ở authentication, authorization, parsing, serialization, cryptography và các API nhạy cảm.
8. **Deployment traceability:** ghi nhận patch version/hash và JVM flags trong metadata triển khai.
9. **Rollback plan:** chuẩn bị image/configuration trước patch và cách khôi phục có thể thực hiện.
10. **Expiry/removal:** đặt điều kiện hoặc thời hạn để thay patch bằng bản sửa chính thức.

Patch path nên nằm trong image bất biến hoặc artifact được version hóa. Tránh mount một thư mục có thể bị thay đổi âm thầm sau khi container đã được triển khai.

## 10. Kiểm tra patch đang được áp dụng

Khi một process có kết quả khác thường, hãy kiểm tra command line khởi chạy và cấu hình môi trường của đúng JVM process. Tìm các tùy chọn:

~~~text
--patch-module
--add-exports
--add-opens
--add-reads
~~~

Kiểm tra patch directory/JAR:

~~~bash
jar --list --file patches/core-fix.jar
sha256sum patches/core-fix.jar
~~~

Trên Windows, có thể dùng:

~~~powershell
jar --list --file patches/core-fix.jar
Get-FileHash patches/core-fix.jar -Algorithm SHA256
~~~

Đối chiếu danh sách class/resource trong patch với module gốc. Nếu patch thay class, xác nhận fully qualified class name và package. Nếu patch thêm resource, kiểm tra đúng đường dẫn và cách code tìm resource.

Có thể kiểm tra descriptor của module gốc:

~~~bash
jar --describe-module --file mods/com.acme.core.jar
~~~

Descriptor cho biết cấu trúc module gốc; nó không phải danh sách đầy đủ nội dung patch đang được áp dụng tại runtime. Vì vậy, cần kiểm tra cả module artifact, patch artifact và JVM command line.

Nếu cần xác minh class thực tế được nạp từ đâu, có thể bật class loading log:

~~~bash
java -Xlog:class+load=info \
  --patch-module=com.acme.core=patches/com.acme.core \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Log class loading giúp xác định class được nạp trong lần chạy đó và nguồn location mà JVM báo cáo. Hãy dùng log trong môi trường kiểm thử hoặc điều tra có kiểm soát; output có thể lớn và có thể chứa đường dẫn filesystem nội bộ.

## 11. Những cơ chế không nên nhầm với module patching

| Cơ chế | Tác động | Khi phù hợp |
| --- | --- | --- |
| \`--patch-module\` | Thêm/ghi đè class và resource của named module khi JVM/compiler thiết lập module | Test hoặc patch module có kiểm soát. |
| \`--upgrade-module-path\` | Ưu tiên module thay thế để nâng cấp module có cùng tên theo cơ chế module resolution | Phân phối module thay thế hoàn chỉnh theo thiết kế nâng cấp. |
| \`--add-exports\` | Bổ sung public package access | Caller cần tham chiếu public type trong package chưa export. |
| \`--add-opens\` | Bổ sung deep reflection access | Framework cần reflection vào package chưa mở. |
| Java agent | Instrument/redefine class theo Instrumentation API | Giám sát hoặc biến đổi class trong JVM đang chạy, trong giới hạn API. |
| Thay JAR và phát hành lại | Thay artifact module chính thức | Bản sửa lâu dài, có version và provenance rõ ràng. |

Nếu mục tiêu là thay thế toàn bộ module bằng phiên bản mới, hãy xem xét \`--upgrade-module-path\` hoặc cập nhật dependency/artifact. \`--patch-module\` thường phù hợp hơn với phần bổ sung/ghi đè có phạm vi hẹp, đặc biệt trong kiểm thử.

## 12. Quy trình chẩn đoán và quyết định production

Khi một bản patch được đề xuất cho môi trường production, thực hiện theo thứ tự:

1. Xác định module và class/resource cần thay đổi; ghi nhận fully qualified name.
2. Xác nhận lỗi không thể giải quyết bằng nâng cấp dependency hoặc sửa source chính thức.
3. Kiểm tra patch có thay class đang tồn tại hay chỉ bổ sung class/resource.
4. Compile patch với đúng JDK và đúng module version; kiểm tra compiler/module options.
5. Chạy test với cả patch ở compile time và runtime để bảo đảm hai môi trường nhìn cùng nội dung.
6. Chạy integration test trên đúng runtime image/container dự kiến triển khai.
7. Kiểm tra module resolution, service provider, reflection và các luồng code liên quan.
8. Đánh giá rủi ro security, binary compatibility, startup và hiệu năng.
9. Đóng gói patch cùng image bất biến, ghi hash và JVM flags.
10. Thử rollback bằng đúng quy trình vận hành trước khi triển khai rộng.
11. Theo dõi lỗi linkage, startup, request failure và log class loading sau triển khai.
12. Loại bỏ patch khi bản sửa chính thức đã được phát hành và kiểm thử.

Không nên dùng module patching để che lỗi split package, thiếu dependency hoặc module descriptor sai. Patching không phải công cụ sửa mọi lỗi JPMS; nó chỉ thay đổi nội dung class/resource mà module nhận được. Khi vấn đề nằm ở package ownership, readability, exports hoặc opens, hãy sửa đúng phần cấu trúc/access tương ứng.

## 13. Nguyên tắc sử dụng an toàn

Module patching rất hữu ích trong kiểm thử và điều tra, nhưng nó tạo ra một lớp nội dung chạy ngoài artifact module chính. Trong production, điều này ảnh hưởng tới khả năng truy vết, bảo mật và tái lập môi trường.

Hãy chỉ sử dụng khi có lý do cụ thể, giới hạn patch vào class/resource cần thiết, quản lý hash và nguồn patch, kiểm thử trên đúng JDK/runtime image, đồng thời có rollback đã được thử. Với bản sửa lâu dài, đưa thay đổi trở lại module source và phát hành artifact mới có version rõ ràng.

