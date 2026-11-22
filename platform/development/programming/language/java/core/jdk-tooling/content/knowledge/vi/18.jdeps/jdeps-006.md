# Tóm tắt dependency bằng jdeps

**jdeps** là công cụ phân tích phụ thuộc tĩnh đi kèm JDK. Công cụ đọc class file, thư mục class hoặc JAR để xác định mã Java tham chiếu đến package, class và module nào. Chế độ **summary** gom các quan hệ phụ thuộc thành báo cáo ngắn, giúp nhìn nhanh thư viện hoặc module nào đang phụ thuộc vào thành phần nào.

Tóm tắt dependency hữu ích khi kiểm tra thư viện trước khi nâng cấp, tìm phạm vi ảnh hưởng của một module, chuẩn bị runtime image bằng jlink và phát hiện phụ thuộc ngoài dự kiến. jdeps chỉ phân tích bytecode và metadata; nó không chạy ứng dụng và không tự sửa dependency.

## 1. jdeps và dependency summary

Một dependency là quan hệ trong đó mã của một thành phần tham chiếu đến kiểu hoặc package được cung cấp bởi thành phần khác. Ví dụ, class trong com.example.app có thể gọi java.sql.Connection, do đó ứng dụng có dependency đến package java.sql.

jdeps có thể phân tích ở nhiều mức:

- **Archive/module level:** tóm tắt quan hệ giữa JAR, thư mục archive hoặc module.
- **Package level:** liệt kê package nguồn phụ thuộc package đích.
- **Class level:** liệt kê class nguồn tham chiếu class đích.
- **Module graph:** phân tích quan hệ requires giữa các named module.

Tùy đầu vào và tùy chọn, một báo cáo có thể dùng tên JAR, package hoặc module làm hai đầu của quan hệ.

### Khi nào dùng summary?

Dùng summary khi cần trả lời nhanh:

- JAR hoặc module này phụ thuộc vào những archive/module nào?
- Một thư viện có kéo theo module JDK nào?
- Sau khi thay đổi dependency, đồ thị phụ thuộc ở mức tổng thể có thay đổi không?
- Những module nào cần được đưa vào custom runtime image?
- Có nên điều tra sâu một dependency trước khi nâng cấp hoặc loại bỏ nó không?

Nếu cần biết chính xác class hoặc package nào tạo ra quan hệ, hãy chuyển sang chế độ verbose hoặc package-level analysis.

## 2. Cú pháp và tùy chọn summary

Cú pháp tổng quát:

~~~bash
jdeps [options] <path ...>
~~~

path có thể là đường dẫn đến class file, thư mục chứa class file hoặc JAR. Với phân tích module, có thể chỉ định module bằng --module.

Hai dạng bật summary:

~~~bash
jdeps -s app.jar
jdeps --summary app.jar
~~~

-s là dạng ngắn của --summary. Tùy chọn này yêu cầu jdeps chỉ in dependency summary, thay vì chi tiết từng class.

Một số tùy chọn thường đi cùng summary:

| Tùy chọn | Ý nghĩa |
|---|---|
| -s, --summary | Chỉ in tóm tắt dependency |
| --class-path, -cp | Chỉ định nơi tìm class và thư viện không modular |
| --module-path | Chỉ định module path |
| --module, -m | Chỉ định module gốc cần phân tích |
| --system | Dùng system module path của một JDK khác |
| --add-modules | Thêm module vào root set khi phân tích |
| --recursive, -R | Phân tích đệ quy các dependency runtime |
| --no-recursive | Không đi tiếp qua dependency |
| --dot-output | Ghi đồ thị dependency dạng DOT |
| --multi-release | Chọn phiên bản khi phân tích multi-release JAR |

Xem phiên bản và cú pháp của toolchain:

~~~bash
jdeps --version
jdeps --help
~~~

Tùy chọn có thể thay đổi theo JDK. Nên dùng jdeps --help của chính JDK trong build pipeline để xác nhận trước khi đưa lệnh vào CI.

## 3. Đọc kết quả summary

Với module JDK java.sql, chạy:

~~~bash
jdeps -s --module java.sql
~~~

Trên OpenJDK 24.0.2, kết quả được xác minh:

~~~text
java.sql -> java.base
java.sql -> java.logging
java.sql -> java.transaction.xa
java.sql -> java.xml
~~~

Cách đọc:

- java.sql là module đang được phân tích.
- Dấu -> biểu thị quan hệ phụ thuộc.
- Tên ở bên phải là module mà java.sql tham chiếu.
- Mỗi dòng là một quan hệ dependency được tổng hợp.

Kết quả có thể khác giữa các phiên bản JDK vì module descriptor hoặc implementation có thể thay đổi. Khi so sánh báo cáo giữa hai máy, hãy ghi lại JDK vendor và version.

### Summary không phải danh sách class

Báo cáo trên không nói class cụ thể nào trong java.sql tham chiếu đến java.xml. Nó chỉ cho thấy quan hệ ở mức module. Muốn truy tìm nguồn phụ thuộc, hãy dùng -verbose:package hoặc -verbose:class.

## 4. Phân tích một JAR hoặc thư mục ứng dụng

Với ứng dụng không modular, có thể truyền trực tiếp JAR:

~~~bash
jdeps --summary build/app.jar
~~~

Nếu ứng dụng dùng thư viện bên ngoài, thêm class path:

~~~bash
jdeps --summary --class-path "lib/*" build/app.jar
~~~

Trên Windows PowerShell, wildcard trong class path cũng có thể được đặt trong dấu nháy:

~~~powershell
jdeps --summary --class-path "lib/*" build/app.jar
~~~

Nếu thư viện nằm ngoài thư mục lib, hãy đưa đường dẫn của nó vào class path theo cú pháp phân tách đường dẫn của hệ điều hành. Trên Linux/macOS, dấu phân cách thường là :; trên Windows là ;.

Có thể phân tích một thư mục class đã biên dịch:

~~~bash
jdeps --summary build/classes
~~~

Điều này hữu ích khi muốn phân tích output của compiler trước khi đóng gói thành JAR.

### Vì sao cần class path đúng?

Nếu jdeps không tìm thấy một class được tham chiếu, kết quả có thể chứa cảnh báo hoặc dependency chưa phân giải. Một báo cáo thiếu thư viện trên class path có thể khiến dependency summary không đầy đủ.

Khi phân tích JAR, hãy cung cấp các dependency mà JAR cần để resolve kiểu. Không thêm mọi thư viện trong máy một cách tùy tiện vì điều đó có thể làm báo cáo chứa những dependency không thuộc build thực tế.

## 5. Summary cho named module

Với ứng dụng modular, cung cấp module path và tên module:

~~~bash
jdeps --summary --module-path "$JAVA_HOME/jmods:mods" --module com.example.app
~~~

Trong ví dụ trên:

- JAVA_HOME/jmods chứa các JMOD của JDK đang dùng.
- mods chứa exploded module hoặc modular JAR của ứng dụng.
- --module com.example.app chọn module cần phân tích.
- --summary gom kết quả thành quan hệ module.

Trên Windows PowerShell, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jdeps --summary --module-path "$env:JAVA_HOME\jmods;mods" --module com.example.app
~~~

Dùng đúng module path rất quan trọng. Nếu module không được tìm thấy, kiểm tra tên trong module-info.java, vị trí artifact và JDK tương ứng. Tên file JAR không nhất thiết giống module name.

## 6. Phân biệt các chế độ báo cáo module

jdeps có một số chế độ module-level liên quan nhưng không giống nhau.

### --summary

~~~bash
jdeps -s --module java.sql
~~~

Tóm tắt quan hệ nguồn → đích. Đây là chế độ phù hợp để xem dependency tổng quan.

### --list-deps

~~~bash
jdeps --list-deps --module java.sql
~~~

Liệt kê các module dependency được phân giải. Tùy đầu vào, output cũng có thể hiển thị package thuộc JDK internal API nếu mã tham chiếu đến chúng.

Ví dụ với OpenJDK 24.0.2, --list-deps --module java.sql hiển thị:

~~~text
   java.base/jdk.internal.reflect
   java.logging
   java.transaction.xa
   java.xml
~~~

Dòng java.base/jdk.internal.reflect là package nội bộ được tham chiếu, không nên nhầm nó với tên module độc lập.

### --list-reduced-deps

~~~bash
jdeps --list-reduced-deps --module java.sql
~~~

Liệt kê dependency sau khi loại bỏ các cạnh đọc được suy ra từ requires transitive trong module graph. Cách nhìn này giúp tập trung vào các quan hệ cần khai báo trực tiếp sau khi giảm đồ thị.

### --print-module-deps

~~~bash
jdeps --print-module-deps --module java.sql
~~~

In danh sách module phân tách bằng dấu phẩy. Với OpenJDK 24.0.2, output đã xác minh là:

~~~text
java.base,java.logging,java.transaction.xa,java.xml
~~~

Danh sách này có thể dùng làm đầu vào cho jlink --add-modules để tạo runtime image chứa các module cần thiết và dependency bắc cầu tương ứng.

### --check

~~~bash
jdeps --check java.sql
~~~

Phân tích module descriptor, dependency sau phân giải và đồ thị sau khi giảm cạnh. Tùy module, kết quả còn chỉ ra qualified export không được sử dụng.

Tóm lại:

| Chế độ | Mục tiêu |
|---|---|
| --summary | Quan hệ dependency dạng tóm tắt |
| --list-deps | Danh sách module dependency |
| --list-reduced-deps | Danh sách dependency sau khi giảm cạnh suy ra |
| --print-module-deps | Danh sách module dạng CSV để dùng với jlink |
| --check | Kiểm tra module descriptor và module graph |

Không dùng các chế độ này như thể chúng có cùng output hoặc cùng mục đích. Chọn theo câu hỏi cần trả lời.

## 7. Từ summary đến phân tích chi tiết

Summary cho biết có quan hệ dependency, nhưng thường không đủ để quyết định sửa mã nào. Có thể tăng mức chi tiết theo từng bước.

### Package-level

~~~bash
jdeps -verbose:package app.jar
~~~

Lệnh này hiển thị quan hệ giữa package nguồn và package đích. Theo mặc định, dependency trong cùng package được lọc khỏi output.

### Class-level

~~~bash
jdeps -verbose:class app.jar
~~~

Hiển thị quan hệ giữa các class. Chế độ này hữu ích khi cần tìm class cụ thể tham chiếu thư viện nào.

### Tất cả class dependency

~~~bash
jdeps -verbose app.jar
~~~

-verbose tương đương -verbose:class -filter:none, vì vậy có thể tạo output lớn. Chỉ dùng khi cần điều tra sâu.

### Lọc theo package hoặc module

Chỉ tìm dependency khớp package:

~~~bash
jdeps --package java.sql app.jar
~~~

Chỉ tìm dependency đến một module:

~~~bash
jdeps --require java.sql app.jar
~~~

Lọc bằng biểu thức regular expression:

~~~bash
jdeps --regex "javax\\..*" app.jar
~~~

--package, --require và --regex là các cách lọc loại trừ lẫn nhau; chọn một kiểu lọc cho mỗi lần chạy. Dùng --include nếu muốn giới hạn tập class nguồn được phân tích.

## 8. Đệ quy và bộ lọc dependency

Mặc định, jdeps có thể lọc các dependency nội bộ trong cùng package. Một số bộ lọc hữu ích:

| Tùy chọn | Ý nghĩa |
|---|---|
| -filter:package | Lọc dependency trong cùng package; đây là mặc định |
| -filter:archive | Lọc dependency trong cùng archive |
| -filter:module | Lọc dependency trong cùng module |
| -filter:none | Không áp dụng các bộ lọc package/archive mặc định |
| -R, --recursive | Duyệt đệ quy dependency runtime; hàm ý -filter:none |
| --no-recursive | Không đi tiếp qua dependency |

Ví dụ phân tích đệ quy:

~~~bash
jdeps -R --summary --class-path "lib/*" build/app.jar
~~~

Dùng đệ quy khi muốn biết cả dependency bắc cầu được tham chiếu thông qua thư viện khác. Kết quả có thể lớn hơn nhiều so với phân tích trực tiếp.

Nếu cần biết dependency trực tiếp của chính ứng dụng, hãy dùng --no-recursive hoặc không bật -R, rồi so sánh với báo cáo đệ quy để xác định dependency nào đến từ thư viện phụ thuộc.

### Phân tích ngược

--inverse tìm các artifact phụ thuộc trực tiếp hoặc gián tiếp vào node được chọn. Tùy chọn này phải đi cùng một tiêu chí như --require, --package hoặc --regex.

Ví dụ tìm các artifact phụ thuộc vào package:

~~~bash
jdeps --inverse --package java.sql --class-path "lib/*" build/app.jar
~~~

Phân tích ngược hữu ích khi đánh giá tác động của việc thay thế hoặc loại bỏ một package/thư viện.

## 9. Tìm dependency bị thiếu và JDK internal API

### Dependency chưa phân giải

Dùng:

~~~bash
jdeps --missing-deps --class-path "lib/*" build/app.jar
~~~

Tùy chọn này tìm các dependency mà jdeps không thể phân giải trong các đầu vào và đường dẫn được cung cấp. Nó đặc biệt hữu ích khi kiểm tra JAR nhận từ bên thứ ba hoặc khi dependency bị thiếu trong build packaging.

--missing-deps không dùng cùng -p/--package, -e/--regex hoặc -s/--summary. Hãy chạy nó như một bước phân tích riêng.

Có thể dùng --ignore-missing-deps để bỏ qua dependency chưa tìm thấy trong một số quy trình phân tích, nhưng điều đó không làm thư viện tự xuất hiện lúc runtime. Chỉ bỏ qua khi đã hiểu và chấp nhận dependency đó được cung cấp theo cách khác.

### JDK internal API

Dùng:

~~~bash
jdeps --jdk-internals app.jar
~~~

Tùy chọn này tìm dependency ở cấp class đến API nội bộ của JDK. API nội bộ không phải hợp đồng tương thích công khai; ứng dụng có thể hỏng khi nâng cấp JDK hoặc khi API đó bị đóng truy cập.

--jdk-internals không dùng cùng -p, -e hoặc -s. Vì vậy, hãy chạy riêng khi cần kiểm tra internal API thay vì cố ghép vào lệnh summary.

Khi phát hiện dependency nội bộ, ưu tiên thay bằng API Java SE được hỗ trợ. Không xem --add-exports hoặc --add-opens là giải pháp lâu dài cho thư viện phụ thuộc internal API.

## 10. Tạo đồ thị dependency

Có thể yêu cầu jdeps xuất file DOT:

~~~bash
jdeps --dot-output build/dependency-graphs app.jar
~~~

DOT là định dạng mô tả đồ thị, có thể dùng với Graphviz để tạo hình ảnh. Output thường gồm file đồ thị tổng hợp và file theo từng archive/module tùy đầu vào.

Có thể chuyển một file DOT thành ảnh bằng Graphviz:

~~~bash
dot -Tpng build/dependency-graphs/summary.dot -o build/dependency-graphs/summary.png
~~~

Tên file DOT cụ thể phụ thuộc đầu vào và phiên bản công cụ; hãy kiểm tra thư mục output sau khi chạy jdeps. Đồ thị trực quan hữu ích với dự án nhiều module, nhưng với một ứng dụng nhỏ, summary dạng văn bản thường dễ đọc hơn.

## 11. Kết hợp dependency summary với jlink

Một ứng dụng modular cần runtime image chứa module ứng dụng và các module phụ thuộc. --print-module-deps có thể tạo danh sách module để chuyển cho jlink.

Ví dụ quy trình:

~~~bash
jdeps --print-module-deps \
  --module-path "$JAVA_HOME/jmods:mods" \
  --module com.example.app
~~~

Giả sử output là danh sách module phân tách bằng dấu phẩy, dùng danh sách đó trong:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,java.sql,java.logging \
  --output runtime
~~~

Danh sách trong lệnh jlink ở trên chỉ minh họa cú pháp. Trong build thật, thay bằng chính output module đã được phân tích và kiểm thử. Không lấy output --summary dạng mũi tên làm giá trị --add-modules; hãy dùng --print-module-deps.

Sau khi tạo runtime image, kiểm tra module đã được đưa vào:

~~~bash
runtime/bin/java --list-modules
~~~

Trên Windows, dùng runtime\bin\java.exe --list-modules.

jdeps giúp xác định dependency tĩnh; ứng dụng vẫn cần được smoke test trên runtime image vì các thành phần được nạp động có thể không xuất hiện trong báo cáo.

## 12. Multi-release JAR và JDK thay thế

Với multi-release JAR, có thể chọn phiên bản cần phân tích:

~~~bash
jdeps --multi-release 17 --summary library.jar
~~~

Giá trị có thể là một số nguyên từ 9 trở lên hoặc base. Hãy chọn phiên bản phù hợp với runtime mục tiêu; kết quả có thể khác nếu JAR chứa implementation riêng cho từng Java release.

Có thể chọn system module path của một JDK khác:

~~~powershell
jdeps --system "C:\Java\jdk-21" --summary app.jar
~~~

Tùy chọn --system giúp phân tích với bộ system modules của JDK được chỉ định. Dùng cùng JDK release với môi trường triển khai để giảm sai khác khi đánh giá module dependency.

## 13. Giới hạn của jdeps

jdeps phân tích dependency tĩnh từ class file và module metadata. Vì vậy, có những dependency có thể không xuất hiện trong summary:

- Class được nạp bằng reflection với tên class lấy từ cấu hình hoặc chuỗi runtime.
- Plugin hoặc provider được tìm theo cơ chế riêng.
- Class name được ghép động rồi truyền cho class loader.
- Native library và dependency bên ngoài JVM.
- Tệp cấu hình, script hoặc tài nguyên chứa tên class/module mà chương trình đọc lúc chạy.

Ví dụ, nếu ứng dụng gọi Class.forName(configuredClassName), jdeps có thể không biết giá trị configuredClassName sẽ là gì khi chạy. Hãy bổ sung thông tin dependency động vào cấu hình build, kiểm thử tích hợp và kiểm tra runtime image trên môi trường gần production.

jdeps cũng không chứng minh rằng dependency là cần thiết về mặt nghiệp vụ; nó chỉ báo quan hệ được tìm thấy trong dữ liệu đã phân tích.

## 14. Lỗi thường gặp

### Warning: Path does not exist

Đường dẫn JAR, thư mục hoặc class path bị sai. Kiểm tra thư mục hiện tại, tên file và đường dẫn tương đối/tuyệt đối.

### Class not found

Thiếu dependency trên --class-path hoặc module path. Bổ sung đúng JAR/module cần thiết rồi chạy lại. Đừng nhầm class path với module path.

### Module not found

Tên module hoặc vị trí artifact không đúng. Dùng jar --describe-module để xem module name của modular JAR và kiểm tra --module-path.

### Summary thiếu dependency bắc cầu

Có thể chưa bật -R hoặc dependency được cung cấp qua thư viện khác. So sánh phân tích trực tiếp với --recursive/--list-deps và kiểm tra class path.

### Output quá lớn

Đang dùng -verbose, -filter:none hoặc -R. Quay lại --summary, dùng --no-recursive, hoặc lọc bằng --package, --require, --regex và --include.

### Dependency không xuất hiện dù ứng dụng vẫn nạp class lúc chạy

Có thể class được nạp bằng reflection hoặc plugin discovery. Bổ sung dependency động từ cấu hình và kiểm tra runtime bằng test tích hợp.

### Không thể ghép --missing-deps với --summary

Đây là giới hạn tùy chọn được jdeps quy định. Chạy hai lệnh riêng: một lệnh summary và một lệnh --missing-deps.

### Không thể ghép --jdk-internals với --summary

--jdk-internals không tương thích với -s. Chạy riêng jdeps --jdk-internals để tìm tham chiếu đến API nội bộ.

## 15. Quy trình phân tích dependency đề xuất

1. Chạy jdeps --summary trên JAR hoặc module để có bức tranh tổng thể.
2. Cung cấp đúng --class-path hoặc --module-path để dependency được phân giải.
3. Dùng --list-deps hoặc --print-module-deps nếu cần danh sách module.
4. Dùng -verbose:package hoặc -verbose:class để tìm nguồn của một dependency cụ thể.
5. Chạy --missing-deps để tìm dependency chưa phân giải.
6. Chạy --jdk-internals riêng để phát hiện API nội bộ.
7. Dùng --recursive khi cần đánh giá dependency bắc cầu.
8. Tạo đồ thị DOT nếu module graph quá lớn để đọc bằng văn bản.
9. Dùng --print-module-deps làm đầu vào cho jlink khi tạo runtime image.
10. Kiểm thử ứng dụng trên runtime image vì reflection và dependency động có thể nằm ngoài kết quả phân tích tĩnh.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| jdeps | Công cụ phân tích dependency tĩnh trong JDK |
| Dependency summary | Báo cáo tóm tắt quan hệ phụ thuộc |
| -s, --summary | Chỉ in dependency summary |
| Class path | Vị trí tìm class và thư viện không modular |
| Module path | Vị trí tìm named module |
| Direct dependency | Dependency được tham chiếu trực tiếp bởi thành phần đang phân tích |
| Transitive dependency | Dependency xuất hiện qua một dependency khác |
| --list-deps | Liệt kê module dependency |
| --print-module-deps | In danh sách module phù hợp để chuyển cho jlink |
| --missing-deps | Tìm dependency chưa phân giải |
| JDK internal API | API nội bộ không thuộc hợp đồng tương thích công khai |
| DOT | Định dạng văn bản mô tả đồ thị |
| Multi-release JAR | JAR chứa nội dung dành cho nhiều Java release |

Dependency summary giúp hiểu nhanh cấu trúc phụ thuộc của JAR và module. Hãy dùng --summary để quan sát tổng thể, chuyển sang báo cáo package/class khi cần tìm nguyên nhân, và dùng --print-module-deps khi chuẩn bị runtime image bằng jlink.

## Tài liệu tham khảo

- Oracle JDK 24 — The jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- Oracle — Java Dependency Analysis Tool: https://docs.oracle.com/javase/8/docs/technotes/tools/unix/jdeps.html
- OpenJDK — jdeps source and tool documentation: https://github.com/openjdk/jdk/tree/master/src/jdk.jdeps