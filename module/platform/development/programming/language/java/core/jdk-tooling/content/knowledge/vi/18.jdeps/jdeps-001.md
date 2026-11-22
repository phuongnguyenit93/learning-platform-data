# Lệnh jdeps trong Java

## Mục tiêu

Sau bài này, bạn có thể dùng jdeps để phân tích dependency của file .class, thư mục class và JAR; đọc dependency ở cấp package, class và module; tìm dependency bị thiếu và JDK internal API; phân tích module graph; tạo danh sách module cho jlink; xuất dependency graph dạng DOT; xử lý multi-release JAR; và hiểu giới hạn của phân tích tĩnh khi điều tra ứng dụng thực tế.

## 1. jdeps là gì?

**jdeps** là công cụ dòng lệnh đi kèm JDK để phân tích dependency của Java bytecode. Công cụ có thể hiển thị quan hệ phụ thuộc ở cấp package hoặc class, đồng thời hỗ trợ phân tích module trong Java Platform Module System (JPMS).

jdeps thường được dùng khi:

- Kiểm tra thư viện đang phụ thuộc vào package/class nào.
- Xác định module JDK cần thiết trước khi tạo runtime image bằng jlink.
- Tìm dependency bị thiếu trong classpath hoặc module path.
- Phát hiện ứng dụng đang gọi JDK internal API không được hỗ trợ.
- Chuẩn bị chuyển một JAR chưa có module descriptor thành modular JAR.
- Rà soát module graph và các directive requires dư thừa.
- Hiểu ảnh hưởng của một package hoặc module lên những thành phần khác.

jdeps phân tích class file đã biên dịch, không phân tích source code như javac. Kết quả cho biết các tham chiếu mà bytecode thể hiện; nó không chứng minh mọi đường chạy của chương trình đều đã được kiểm tra.

## 2. Kiểm tra JDK và cú pháp cơ bản

jdeps được cung cấp cùng JDK. Mở terminal và kiểm tra:

~~~bash
jdeps --version
~~~

Xem trợ giúp:

~~~bash
jdeps --help
~~~

Cú pháp tổng quát:

~~~bash
jdeps [options] path...
~~~

Đối số path có thể là:

- Một file .class.
- Một thư mục chứa các class file.
- Một file JAR.
- Tên class đầy đủ (fully qualified class name) để phân tích các class file tương ứng.

Ví dụ:

~~~bash
jdeps build/classes
jdeps build/classes/com/example/Main.class
jdeps app.jar
~~~

Nếu phân tích tên class thay vì đường dẫn, cần cung cấp nơi tìm class qua classpath hoặc module path thích hợp.

Hãy dùng jdeps từ JDK tương ứng với release mà bạn muốn kiểm tra. Với multi-release JAR, phải chọn phiên bản class cần phân tích bằng tùy chọn --multi-release.

## 3. Xem dependency ở các mức độ khác nhau

### Dependency summary

Tùy chọn -summary hoặc -s in bản tổng hợp dependency:

~~~bash
jdeps -summary app.jar
~~~

Dạng output thường thể hiện archive phụ thuộc vào module hoặc archive nào. Đây là cách bắt đầu tốt khi chỉ cần bức tranh tổng thể.

### Dependency ở cấp package

~~~bash
jdeps -verbose:package app.jar
~~~

Lệnh hiển thị quan hệ giữa các package. Mặc định, dependency bên trong cùng package được lọc khỏi kết quả.

Cách xem này hữu ích khi thiết kế package, phân chia layer hoặc kiểm tra một package có phụ thuộc ngược vào package khác hay không.

### Dependency ở cấp class

~~~bash
jdeps -verbose:class app.jar
~~~

Lệnh hiển thị class nguồn tham chiếu đến class đích. Mặc định, dependency nằm trong cùng archive được lọc khỏi kết quả.

### Hiển thị tất cả class-level dependency

~~~bash
jdeps -verbose app.jar
~~~

Tùy chọn -verbose tương đương -verbose:class kết hợp -filter:none. Kết quả có thể rất dài đối với ứng dụng lớn.

| Tùy chọn | Kết quả |
|---|---|
| -summary hoặc -s | Tóm tắt dependency |
| -verbose:package | Dependency ở cấp package |
| -verbose:class | Dependency ở cấp class |
| -verbose | Tất cả class-level dependency, kể cả dependency trong cùng archive |

Khi đọc kết quả, mũi tên từ A đến B biểu thị A phụ thuộc vào B. Đây là quan hệ tham chiếu, không nhất thiết có nghĩa B được gọi ở mọi lần chạy.

## 4. Phân tích dependency của ứng dụng có thư viện bên ngoài

Nếu JAR phụ thuộc thư viện khác, hãy chỉ định classpath để jdeps phân giải được các type bên ngoài.

Ví dụ, thư viện phụ thuộc nằm trong thư mục lib:

~~~bash
jdeps --class-path "lib/*" app.jar
~~~

Có thể kết hợp với phân tích module:

~~~bash
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

Trên Windows, dấu phân tách các phần tử classpath là dấu chấm phẩy; trên Linux/macOS là dấu hai chấm. Wildcard trong classpath như lib/* cho phép nạp các JAR trong thư mục theo quy tắc classpath của Java.

Với ứng dụng modular, dùng module path:

~~~bash
jdeps --module-path mods --module com.example.app
~~~

Một số tùy chọn liên quan:

- --class-path: nơi tìm class file và thư viện trên classpath.
- --module-path: nơi tìm các module.
- --upgrade-module-path: module path chứa module thay thế hoặc nâng cấp.
- --system: chỉ định Java home khác làm system module path.
- --add-modules: bổ sung module vào tập root được phân tích.

Nếu thiếu thư viện khi chạy jdeps, hãy kiểm tra classpath/module path trước khi kết luận ứng dụng có dependency lỗi. Phân tích không có đủ đầu vào có thể tạo ra kết quả not found hoặc cảnh báo missing.

## 5. Phân tích dependency ở cấp module

jdeps cung cấp các tùy chọn chuyên biệt cho JPMS.

### --list-deps

~~~bash
jdeps --list-deps app.jar
~~~

Liệt kê module dependency và package JDK internal API nếu được tham chiếu. Tùy chọn này phân tích bắc cầu các thư viện trên classpath/module path nếu chúng được tham chiếu.

Muốn không đi tiếp qua dependency bắc cầu, dùng:

~~~bash
jdeps --list-deps --no-recursive app.jar
~~~

### --list-reduced-deps

~~~bash
jdeps --list-reduced-deps app.jar
~~~

Kết quả bỏ qua các cạnh đọc module được suy ra từ quan hệ requires transitive. Ví dụ, nếu M1 đọc M2 và M2 requires transitive M3 thì quan hệ đọc M1 đến M3 là quan hệ được suy ra và không cần hiển thị lại.

### --print-module-deps

~~~bash
jdeps --print-module-deps app.jar
~~~

Tùy chọn này in danh sách module dependency được phân tách bằng dấu phẩy. Kết quả tương ứng với reduced dependency list và có thể dùng làm đầu vào cho jlink --add-modules.

Ví dụ kết quả có thể có dạng:

~~~text
java.base,java.logging,java.sql
~~~

Danh sách thực tế phụ thuộc bytecode và thư viện được phân tích; không sao chép danh sách ví dụ này cho mọi ứng dụng.

### Phân biệt ba lựa chọn

| Tùy chọn | Dùng khi |
|---|---|
| --list-deps | Muốn xem module dependency và package internal API |
| --list-reduced-deps | Muốn xem dependency sau khi loại các cạnh reads được suy ra |
| --print-module-deps | Cần danh sách module dạng comma-separated cho jlink |

Với modular application, dùng --module để chọn module gốc:

~~~bash
jdeps --module-path mods --module com.example.app --list-deps
~~~

Nếu ứng dụng cần các service provider được phát hiện qua service binding, hãy rà soát riêng service/provider và tùy chọn jlink --bind-services. Danh sách dependency tĩnh không thay thế kiểm thử ServiceLoader trong runtime image.

## 6. Dùng jdeps để hỗ trợ tạo runtime image với jlink

Một trong những ứng dụng phổ biến của jdeps là xác định các module JDK mà ứng dụng cần trước khi tạo runtime image.

Đối với classpath application:

~~~bash
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

Giả sử kết quả là:

~~~text
java.base,java.logging,java.sql
~~~

Có thể dùng các module đó để tạo runtime image:

~~~bash
jlink --add-modules java.base,java.logging,java.sql --output runtime
~~~

Sau đó chạy ứng dụng bằng runtime image, giữ app.jar và các dependency của ứng dụng trên classpath:

Linux/macOS:

~~~bash
runtime/bin/java -cp "app.jar:lib/*" com.example.Main
~~~

Windows PowerShell:

~~~powershell
.\runtime\bin\java.exe -cp "app.jar;lib/*" com.example.Main
~~~

Lưu ý:

- jdeps không tạo runtime image; jlink mới thực hiện việc đó.
- jdeps chỉ gợi ý module dựa trên dependency bytecode mà nó quan sát được.
- Classpath application vẫn cần JAR ứng dụng và thư viện bên ngoài khi chạy.
- Với modular application, cần đưa module ứng dụng vào module path và chọn nó làm root module khi dùng jlink.
- Reflection, service loading, resource, native library và dependency lấy từ cấu hình có thể cần được bổ sung sau khi rà soát.

Không nên xóa module khỏi image chỉ vì jdeps không báo dependency đến module đó. Trước khi phát hành, hãy chạy ứng dụng bằng chính runtime image và thực hiện integration test.

## 7. Tìm dependency tới JDK internal API

JDK internal API là những class/package nội bộ không phải API Java SE được hỗ trợ ổn định. Sử dụng chúng có thể làm ứng dụng hỏng khi nâng cấp JDK hoặc khi module encapsulation được thực thi chặt hơn.

Tìm tham chiếu đến internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu có thư viện phụ thuộc bên ngoài:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

jdeps có thể hiển thị class sử dụng internal API và gợi ý API thay thế khi biết được. Kết quả này đặc biệt hữu ích khi nâng cấp từ JDK cũ sang JDK mới.

Ví dụ, nếu một thư viện truy cập package sun.* hoặc com.sun.* nội bộ, hãy kiểm tra xem có API công khai trong java.* hoặc javax.* đáp ứng nhu cầu hay không.

**Không nên coi --add-exports hoặc --add-opens là cách sửa lâu dài.** Các tùy chọn này có thể tạm thời cho phép truy cập trong một cấu hình cụ thể, nhưng không biến internal API thành API được hỗ trợ. Ưu tiên thay bằng API công khai và được tài liệu hóa.

Tùy chọn --jdk-internals không dùng cùng các bộ lọc -p, -e và -s. Hãy chạy lệnh riêng khi cần kiểm tra internal API.

## 8. Tìm dependency bị thiếu

Dùng --missing-deps để tìm các dependency mà jdeps không thể phân giải:

~~~bash
jdeps --missing-deps app.jar
~~~

Nếu thư viện bên ngoài nằm trong thư mục lib:

~~~bash
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Các nguyên nhân phổ biến:

- JAR dependency không có trong classpath/module path.
- Phân tích sai phiên bản thư viện.
- Class file được biên dịch với API không có trong JDK mục tiêu.
- Dependency bị loại khỏi build output hoặc bị đóng gói thiếu.
- Phân tích một phần artifact thay vì toàn bộ ứng dụng.

Tùy chọn --ignore-missing-deps yêu cầu jdeps bỏ qua dependency không tìm thấy:

~~~bash
jdeps --ignore-missing-deps app.jar
~~~

Đây chỉ là tùy chọn điều chỉnh báo cáo. Nó không tải thư viện, không thêm dependency và không sửa ứng dụng. Không dùng nó để che một dependency thực sự cần thiết.

--missing-deps không thể kết hợp với -p/--package, -e/--regex và -s/--summary. Khi cần điều tra dependency thiếu, hãy chạy một lệnh riêng không dùng các tùy chọn loại trừ đó.

## 9. Lọc dependency và giới hạn phạm vi phân tích

Khi kết quả quá lớn, có thể lọc theo package, regex hoặc module.

### Lọc theo package

~~~bash
jdeps --package java.sql app.jar
~~~

Có thể chỉ định --package nhiều lần để kiểm tra nhiều package. Tùy chọn này không dùng đồng thời với --regex.

### Lọc theo regular expression

~~~bash
jdeps --regex 'java\..*' app.jar
~~~

Regex được áp dụng lên dependency cần tìm. Dùng dấu nháy phù hợp shell để tránh ký tự đặc biệt bị diễn giải trước khi truyền cho jdeps.

### Lọc theo module

~~~bash
jdeps --require java.sql app.jar
~~~

Tùy chọn --require tìm dependency phù hợp module được chỉ định. Có thể dùng nhiều lần.

### Lọc class được phân tích

~~~bash
jdeps --include 'com\.example\..*' app.jar
~~~

--include giới hạn những class được đưa vào phân tích. Nó khác với --package hoặc --regex: include lọc class nguồn được phân tích, còn package/regex lọc dependency được tìm.

### Các chế độ filter

| Tùy chọn | Ý nghĩa |
|---|---|
| -filter:package | Lọc dependency trong cùng package; mặc định |
| -filter:archive | Lọc dependency trong cùng archive |
| -filter:module | Lọc dependency trong cùng module |
| -filter:none | Không lọc dependency trong cùng package/archive |
| -filter regex | Lọc dependency khớp regular expression |

Khi cần xem đầy đủ quan hệ trong một archive:

~~~bash
jdeps -verbose:class -filter:none app.jar
~~~

### Phân tích đệ quy

~~~bash
jdeps -R app.jar
~~~

-R hoặc --recursive đi tiếp qua dependency runtime và ngầm bật -filter:none. Dùng khi cần nhìn sâu vào dependency bắc cầu.

Để chỉ phân tích trực tiếp, dùng:

~~~bash
jdeps --no-recursive app.jar
~~~

Phân tích đệ quy có thể làm output lớn đáng kể, đặc biệt khi classpath chứa nhiều thư viện.

## 10. Phân tích dependency ngược và compile-time view

### Dependency ngược với --inverse

--inverse tìm những artifact phụ thuộc trực tiếp hoặc gián tiếp vào dependency được chọn. Nó cần đi cùng một bộ lọc --require, --package hoặc --regex.

Ví dụ:

~~~bash
jdeps --inverse --require java.sql app.jar
~~~

Cách này hữu ích khi cần biết module/package nào bị ảnh hưởng nếu thay đổi hoặc loại bỏ một dependency.

### Compile-time dependency view

~~~bash
jdeps --compile-time --module-path mods --module com.example.app
~~~

--compile-time phân tích compile-time view của dependency bắc cầu. Nó có thể giúp hiểu type nào cần thiết khi biên dịch và quan hệ phụ thuộc mà module graph biểu diễn.

Compile-time view và runtime view có mục đích khác nhau. Không nên dùng một kết quả để thay thế kết quả còn lại khi đang điều tra vấn đề liên kết hoặc triển khai.

## 11. Xuất dependency graph dạng DOT

jdeps có thể xuất graph theo định dạng DOT để trực quan hóa dependency.

~~~bash
jdeps --dot-output deps-dot app.jar lib/parser.jar lib/common.jar
~~~

Thư mục deps-dot có thể chứa:

- Một file .dot cho từng archive được phân tích.
- summary.dot thể hiện quan hệ dependency giữa các archive.

Có thể chuyển summary.dot thành SVG bằng Graphviz:

~~~bash
dot -Tsvg deps-dot/summary.dot -o deps.svg
~~~

Graphviz là công cụ bên ngoài JDK; jdeps chỉ tạo file DOT. Với ứng dụng lớn, nên lọc package/module trước khi tạo graph để sơ đồ dễ đọc và tập trung vào khu vực cần điều tra.

## 12. Phân tích multi-release JAR

Multi-release JAR có thể chứa nhiều phiên bản class trong cùng archive, ví dụ class gốc và class thay thế trong META-INF/versions.

Khi phân tích loại JAR này, chọn release cụ thể:

~~~bash
jdeps --multi-release 17 app.jar
~~~

Có thể dùng release khác, chẳng hạn:

~~~bash
jdeps --multi-release 21 app.jar
~~~

Hoặc phân tích phần base:

~~~bash
jdeps --multi-release base app.jar
~~~

Giá trị version phải là base hoặc số nguyên từ 9 trở lên. Chọn đúng release mục tiêu rất quan trọng vì implementation trong META-INF/versions có thể phụ thuộc module/API khác với class base.

Khi phát hành thư viện multi-release, nên phân tích và kiểm thử từng release mà sản phẩm hỗ trợ thay vì chỉ chạy một lần trên base.

## 13. Kiểm tra module graph với --check

Đối với named module, --check phân tích dependency của module và in:

- Module descriptor.
- Dependency sau khi phân tích.
- Module graph sau khi rút gọn các cạnh được suy ra.
- Các qualified export không được dùng nếu phát hiện.

Ví dụ:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Có thể kiểm tra nhiều module trong cùng lệnh:

~~~bash
jdeps --module-path mods --check com.example.app,com.example.api
~~~

Kết quả hỗ trợ review module-info.java, phát hiện requires không cần thiết hoặc export có điều kiện không được sử dụng.

Đây là công cụ phân tích module graph, không tự sửa module descriptor. Hãy xem xét kết quả trước khi xóa requires hoặc thay đổi exports, đặc biệt khi API công khai được consumer bên ngoài sử dụng.

## 14. Tạo module-info.java cho JAR chưa modular

Một JAR cũ có thể chưa có module descriptor. jdeps hỗ trợ tạo bản nháp module-info.java từ dependency quan sát được:

~~~bash
jdeps --generate-module-info generated-modules library.jar
~~~

Với module cần mở cho reflection:

~~~bash
jdeps --generate-open-module generated-open-modules library.jar
~~~

Công cụ tạo file module-info.java trong thư mục chỉ định. Đây là điểm khởi đầu cho quá trình modularization, không phải module descriptor đã được review và sẵn sàng phát hành.

Sau khi tạo:

1. Mở module-info.java được sinh ra.
2. Kiểm tra module name và các directive requires.
3. Kiểm tra package thực sự cần exports.
4. Bổ sung uses/provides nếu thư viện có service contract.
5. Rà soát reflection, serialization, framework và resource.
6. Biên dịch lại module descriptor cùng source hoặc class.
7. Kiểm tra bằng jar --describe-module và chạy test trên module path.

--generate-module-info không dùng cùng --dot-output hoặc --class-path. Nếu cần phân tích dependency ngoài, hãy chuẩn bị module path thích hợp và làm theo ràng buộc của tùy chọn này.

Không nên export mọi package chỉ để module compile được. Chỉ export API mà consumer cần truy cập; giữ implementation package ở trạng thái encapsulated khi có thể.

## 15. Ví dụ thực hành hoàn chỉnh

Ví dụ tạo một chương trình nhỏ có dependency đến java.sql và java.logging để đọc kết quả jdeps.

Tạo file src/com/example/DependencyDemo.java:

~~~java
package com.example;

import java.sql.Connection;
import java.util.logging.Logger;

public class DependencyDemo {

    private static final Logger LOG =
            Logger.getLogger(DependencyDemo.class.getName());

    public static void main(String[] args) {
        System.out.println("class=" + DependencyDemo.class.getSimpleName());
        System.out.println("sqlApi=" + Connection.class.getSimpleName());
        System.out.println("logger=" + LOG.getName());
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d build/classes src/com/example/DependencyDemo.java
~~~

Chạy chương trình:

~~~bash
java -cp build/classes com.example.DependencyDemo
~~~

Output chính xác:

~~~text
class=DependencyDemo
sqlApi=Connection
logger=com.example.DependencyDemo
~~~

Phân tích dependency ở cấp package:

~~~bash
jdeps -verbose:package -filter:none build/classes
~~~

Phân tích dependency ở cấp class:

~~~bash
jdeps -verbose:class -filter:none build/classes
~~~

In danh sách module dependency:

~~~bash
jdeps --print-module-deps build/classes
~~~

Với ví dụ này, hãy kiểm tra kết quả có các module JDK cần cho bytecode, bao gồm java.base, java.logging và java.sql. Chi tiết output và cách trình bày có thể thay đổi theo JDK.

Tìm internal API:

~~~bash
jdeps --jdk-internals build/classes
~~~

Tìm dependency không phân giải được:

~~~bash
jdeps --missing-deps build/classes
~~~

Tạo graph:

~~~bash
jdeps --dot-output build/dependency-graph build/classes
~~~

Ví dụ này minh họa cùng một đầu vào có thể được phân tích theo nhiều góc nhìn. Chương trình chạy được không có nghĩa mọi dependency động hoặc native dependency đã được phát hiện.

## 16. Các lỗi thường gặp và cách xử lý

### Không tìm thấy class hoặc dependency

**Dấu hiệu:** output có not found hoặc jdeps không phân giải được type.

**Nguyên nhân:** thiếu JAR trong classpath, thiếu module trong module path hoặc phân tích một phần artifact.

**Cách xử lý:** bổ sung --class-path hoặc --module-path; kiểm tra đường dẫn và phiên bản dependency.

### Phân tích sai phiên bản multi-release JAR

**Dấu hiệu:** dependency báo ra không khớp với runtime mà ứng dụng hỗ trợ.

**Nguyên nhân:** không chỉ định --multi-release hoặc chọn sai release.

**Cách xử lý:** chạy lại với đúng số release mục tiêu hoặc base.

### Output quá dài

**Dấu hiệu:** kết quả có hàng nghìn dòng class dependency.

**Nguyên nhân:** dùng -verbose hoặc -R trên toàn bộ ứng dụng và dependency bắc cầu.

**Cách xử lý:** bắt đầu bằng -summary, --list-deps hoặc -verbose:package; dùng --include, --package, --regex hoặc --require để thu hẹp phạm vi.

### Hiểu nhầm kết quả --print-module-deps

**Dấu hiệu:** runtime image được tạo nhưng ứng dụng vẫn thiếu class hoặc provider.

**Nguyên nhân:** coi kết quả phân tích bytecode là danh sách hoàn chỉnh mọi thành phần runtime.

**Cách xử lý:** rà soát reflection, ServiceLoader, resource, JNI/JNA, native library và cấu hình; chạy integration test trên image thực tế.

### Nhầm internal API với API được hỗ trợ

**Dấu hiệu:** ứng dụng chạy trên JDK cũ nhưng lỗi sau khi nâng cấp.

**Nguyên nhân:** phụ thuộc package nội bộ như sun.* hoặc com.sun.*.

**Cách xử lý:** chạy --jdk-internals và thay bằng API công khai được hỗ trợ. Chỉ dùng tùy chọn export/open tạm thời khi có kế hoạch loại bỏ rõ ràng.

### Lỗi khi tạo module descriptor

**Dấu hiệu:** module-info.java được sinh nhưng không biên dịch hoặc không chạy được.

**Nguyên nhân:** descriptor tự động chưa xử lý đầy đủ service, reflection, package export hoặc dependency động.

**Cách xử lý:** xem file được sinh như bản nháp, chỉnh sửa module descriptor, biên dịch lại và chạy test trên module path.

### Dùng tùy chọn không tương thích

**Dấu hiệu:** jdeps báo không thể kết hợp các option.

**Nguyên nhân:** ví dụ --missing-deps với --package/--regex/--summary, hoặc --generate-module-info với --class-path/--dot-output.

**Cách xử lý:** tách thành các lần phân tích riêng theo nhóm tùy chọn được hỗ trợ.

## 17. Giới hạn của jdeps

jdeps thực hiện phân tích tĩnh dựa trên class file. Nó không thể bảo đảm phát hiện mọi thứ ứng dụng có thể nạp hoặc sử dụng khi chạy.

Những trường hợp cần kiểm tra bổ sung:

- Class được nạp bằng Class.forName hoặc tên lấy từ file cấu hình.
- Reflection và truy cập member được xác định ở runtime.
- ServiceLoader, plugin và provider được chọn theo cấu hình hoặc môi trường.
- Native library qua JNI/JNA và thư viện hệ điều hành.
- Resource, file template, locale data, certificate và file cấu hình.
- Class được sinh động hoặc tải từ network/đường dẫn ngoài.
- Quyền file, network, process và các điều kiện môi trường triển khai.

jdeps cũng không phải công cụ đánh giá lỗ hổng, không xác minh logic nghiệp vụ, không đo hiệu năng và không chứng minh ứng dụng chạy đúng.

Kết quả tốt nhất đến từ việc kết hợp:

1. Phân tích tĩnh bằng jdeps.
2. Review module/classpath và dependency khai báo.
3. Test runtime bằng đúng JDK hoặc runtime image mục tiêu.
4. Integration test cho service, resource, database, TLS và native code.
5. Theo dõi log và lỗi thực tế ở môi trường triển khai.

## 18. Checklist sử dụng jdeps

- [ ] Chạy jdeps --version để xác nhận JDK.
- [ ] Phân tích đúng file class, thư mục hoặc JAR.
- [ ] Dùng -summary để có cái nhìn tổng thể.
- [ ] Dùng -verbose:package hoặc -verbose:class khi cần chi tiết.
- [ ] Cung cấp classpath/module path đầy đủ.
- [ ] Dùng --list-deps hoặc --print-module-deps khi phân tích module.
- [ ] Rà soát kết quả trước khi dùng với jlink.
- [ ] Chạy --jdk-internals trước khi nâng cấp JDK.
- [ ] Chạy --missing-deps để tìm dependency chưa phân giải.
- [ ] Dùng filter/--include để thu hẹp output.
- [ ] Dùng --multi-release đúng phiên bản với multi-release JAR.
- [ ] Dùng --check để review module graph.
- [ ] Xem module-info.java được generate là bản nháp cần review.
- [ ] Kết hợp phân tích tĩnh với test runtime cho dependency động.
- [ ] Lưu kết quả phân tích trong build/CI khi cần theo dõi thay đổi dependency.

## 19. Tài liệu tham khảo chính thức

- [The jdeps Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — cú pháp lệnh, dependency cấp class/package, module analysis, filters, recursive/inverse analysis và ví dụ.
- [Java Platform Module System — JLS Chapter 7](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html) — quy tắc module, requires, exports, uses và provides.
- [The jlink Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — tạo runtime image và sử dụng danh sách module dependency.
- [The jar Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html) — kiểm tra module descriptor của JAR bằng jar --describe-module.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — thiết kế và các nguyên tắc của Java Platform Module System.

jdeps giúp biến dependency ẩn trong bytecode thành thông tin có thể kiểm tra và đưa vào quy trình build. Hãy chọn đúng classpath/module path và release, đọc kết quả theo đúng mức phân tích, rồi xác minh dependency động bằng runtime test trước khi thay đổi module graph hoặc tạo runtime image.
