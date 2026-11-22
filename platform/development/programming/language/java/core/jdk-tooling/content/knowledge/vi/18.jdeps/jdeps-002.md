# Phân tích dependency bằng jdeps

## 1. jdeps là gì?

`jdeps` là công cụ dòng lệnh đi kèm JDK dùng để phân tích các quan hệ phụ thuộc (dependency) trong class file, thư mục class, JAR và module Java. Công cụ đọc bytecode và metadata để xác định class hoặc package nào tham chiếu tới class, package hay module khác.

Phân tích dependency giúp trả lời những câu hỏi như:

- Một thư viện đang phụ thuộc vào những package hoặc module nào?
- Ứng dụng có đang sử dụng API nội bộ của JDK hay không?
- Dependency nào bị thiếu khi phân tích artifact?
- Một JAR cũ có thể được chuyển thành module JPMS như thế nào?
- Những module JDK nào cần có trong runtime image được tạo bằng `jlink`?
- Module descriptor có khai báo thừa hoặc thiếu quan hệ phụ thuộc không?

`jdeps` thực hiện **static analysis** (phân tích tĩnh). Nó đọc tham chiếu có thể nhận diện từ bytecode và module descriptor; nó không chạy ứng dụng và không ghi nhận mọi class được nạp trong một lần chạy thực tế.

Công cụ này đặc biệt hữu ích khi nâng cấp JDK, chuyển ứng dụng sang JPMS, giảm kích thước runtime image, kiểm tra thư viện bên thứ ba và tìm dependency tới JDK internal API.

## 2. Dependency trong Java có nghĩa là gì?

Một class phụ thuộc vào class khác khi nó sử dụng kiểu, field, method hoặc thành phần của class đó. Ví dụ:

```java
package com.example;

import java.time.LocalDate;
import java.util.List;

public class Report {
    private final List<LocalDate> dates;

    public Report(List<LocalDate> dates) {
        this.dates = dates;
    }
}
```

Class `Report` có các dependency có thể nhận diện tới `java.time.LocalDate` và `java.util.List`. Những kiểu này thuộc module `java.base`.

Dependency có thể được quan sát ở nhiều mức:

| Mức phân tích | Điều được thể hiện |
|---|---|
| Class | Class nào tham chiếu tới class nào |
| Package | Package nguồn phụ thuộc package đích nào |
| Archive/JAR | JAR nào phụ thuộc vào archive hoặc thư viện khác |
| Module | Module nào đọc hoặc yêu cầu module nào |
| API công khai | Các kiểu xuất hiện trong chữ ký public/protected của API |

Một dependency có thể xuất hiện trong chữ ký method, kiểu field, superclass, interface, annotation, exception hoặc bytecode của method. Tùy tùy chọn, `jdeps` có thể phân tích toàn bộ class hoặc chỉ các dependency xuất hiện trong API công khai.

## 3. Cài đặt và kiểm tra jdeps

`jdeps` được phân phối cùng JDK. Mở Terminal, Command Prompt hoặc PowerShell và chạy:

```bash
jdeps --version
jdeps --help
```

Nếu hệ thống không nhận diện `jdeps`, hãy kiểm tra JDK đã được cài và thư mục `bin` của JDK có nằm trong PATH hay chưa.

Có thể xác định vị trí công cụ:

Linux/macOS:

```bash
command -v jdeps
echo "$JAVA_HOME"
```

Windows PowerShell:

```powershell
Get-Command jdeps -All
$env:JAVA_HOME
```

`JAVA_HOME` nên trỏ tới thư mục gốc JDK. Thư mục `bin` bên trong JDK chứa `jdeps`, `javac`, `java` và các công cụ liên quan.

Phiên bản JDK dùng để chạy `jdeps` có thể ảnh hưởng các module hệ thống và class file mà công cụ nhận diện. Khi so sánh kết quả giữa máy CI và máy lập trình viên, hãy ghi lại phiên bản JDK.

## 4. Cú pháp tổng quát của jdeps

Cú pháp cơ bản:

```bash
jdeps [options] <path...>
```

`<path...>` có thể là đường dẫn tới:

- Một tệp `.class`.
- Một thư mục chứa class file.
- Một tệp JAR.
- Nhiều đường dẫn đầu vào được cung cấp trong cùng lệnh.

Ví dụ:

```bash
jdeps app.jar
jdeps -summary app.jar
jdeps -verbose:class app.jar
```

Nếu không chỉ định tùy chọn, `jdeps` hiển thị quan hệ phụ thuộc ở mức package theo chế độ mặc định. Có thể thêm tùy chọn để xem tóm tắt, class cụ thể, module, dependency bị thiếu hoặc đồ thị.

Xem toàn bộ tùy chọn mà JDK hiện tại hỗ trợ bằng:

```bash
jdeps --help
```

Một số tên tùy chọn có dạng dài và dạng viết tắt. Ví dụ `-s` tương đương `--summary`; `-v` tương đương `--verbose`.

## 5. Phân tích một JAR hoặc thư mục class

Với một thư viện đã build, truyền đường dẫn JAR:

```bash
jdeps app.jar
```

Với thư mục chứa class file:

```bash
jdeps build/classes
```

Với một class file cụ thể:

```bash
jdeps build/classes/com/example/Report.class
```

Kết quả cho biết package nguồn phụ thuộc vào package đích. Định dạng và số dòng phụ thuộc cấu trúc artifact, dependency có sẵn và tùy chọn lọc.

Ví dụ minh họa về dạng kết quả package-level:

```text
Report.class -> java.base
   com.example -> java.time
   com.example -> java.util
```

Đây là cách đọc khái niệm: class hoặc package thuộc ứng dụng tham chiếu tới các package Java tương ứng. Kết quả thực tế có thể chứa thêm package, archive hoặc module khác.

`jdeps` không yêu cầu phải giải nén JAR trước. Nếu mục tiêu là xem dependency, truyền trực tiếp đường dẫn JAR thường đơn giản hơn.

## 6. Xem dependency ở các mức chi tiết

`jdeps` hỗ trợ nhiều mức hiển thị. Chọn mức phù hợp giúp kết quả dễ đọc và dễ khoanh vùng.

### 6.1. Tóm tắt bằng --summary

`--summary` (dạng ngắn `-s`) hiển thị dependency ở mức tổng quát:

```bash
jdeps --summary app.jar
```

Lệnh này phù hợp để kiểm tra nhanh một JAR đang phụ thuộc vào những archive hoặc module nào mà không cần đọc từng class.

### 6.2. Xem dependency ở mức package

`--verbose:package` hiển thị quan hệ phụ thuộc giữa các package:

```bash
jdeps --verbose:package app.jar
```

Mức package hữu ích khi muốn hiểu cấu trúc tổng thể của thư viện, chẳng hạn package nghiệp vụ nào phụ thuộc vào package tiện ích hoặc package framework nào.

### 6.3. Xem dependency ở mức class

`--verbose:class` hiển thị quan hệ class-to-class:

```bash
jdeps --verbose:class app.jar
```

Đây là mức chi tiết hơn, phù hợp khi cần tìm class cụ thể tạo ra dependency hoặc điều tra một tham chiếu tới API không mong muốn.

Dạng viết tắt `-v` tương đương chế độ verbose class-level và thường cho lượng kết quả lớn:

```bash
jdeps -v app.jar
```

### 6.4. Giới hạn class được phân tích

Tùy chọn `-include` nhận regular expression để giới hạn những class được đưa vào phân tích:

```bash
jdeps -include 'com\.example\..*' app.jar
```

Tùy chọn này lọc class đầu vào được phân tích. Nó khác với `--package` hoặc `--regex`, vốn lọc các dependency được tìm thấy.

## 7. Phân tích dependency của module

`jdeps` có thể phân tích các module JPMS trên module path hoặc module hệ thống của JDK.

Ví dụ phân tích module `java.sql` trong JDK hiện tại:

```bash
jdeps --module java.sql
```

Dạng viết tắt:

```bash
jdeps -m java.sql
```

Nếu cần chỉ rõ module path:

```bash
jdeps --module-path lib --module com.example.app
```

Trong đó:

- `--module-path lib` chỉ định nơi tìm các module ứng dụng hoặc dependency.
- `--module com.example.app` chọn module gốc cần phân tích.
- Các module được khai báo qua `requires` sẽ được xem xét khi xây dựng module graph.

Đối với module JDK, `jdeps` dùng module hệ thống tương ứng với JDK đang chạy. Có thể chỉ định system image khác bằng `--system` nếu cần phân tích theo một Java runtime khác.

## 8. Liệt kê module dependency bằng --list-deps

`--list-deps` liệt kê module phụ thuộc được phát hiện. Ví dụ:

```bash
jdeps --list-deps --module java.sql
```

Trên JDK 24.0.2 trong môi trường kiểm tra, kết quả là:

```text
   java.base/jdk.internal.reflect
   java.logging
   java.transaction.xa
   java.xml
```

Kết quả cụ thể có thể khác theo phiên bản JDK. Dòng đầu thể hiện tham chiếu package nội bộ trong module `java.base`; các dòng còn lại là module dependency được nhận diện.

Có thể yêu cầu danh sách dependency rút gọn bằng:

```bash
jdeps --list-reduced-deps --module java.sql
```

Chế độ reduced không liệt kê những cạnh đọc module đã được suy ra từ quan hệ `requires transitive` trong module graph.

Nếu chỉ cần danh sách module dạng dấu phẩy để đưa vào lệnh `jlink`, dùng `--print-module-deps`:

```bash
jdeps --print-module-deps --module java.sql
```

Kết quả đã kiểm tra trên JDK 24.0.2:

```text
java.base,java.logging,java.transaction.xa,java.xml
```

Đây là định dạng comma-separated module names, phù hợp để làm đầu vào cho `jlink --add-modules` khi cấu hình module path tương ứng.

## 9. Kiểm tra module descriptor bằng --check

Với module đã có descriptor, `--check` phân tích dependency và thông tin khai báo module:

```bash
jdeps --check java.sql
```

Trên JDK 24.0.2, phần đầu kết quả có dạng:

```text
java.sql (jrt:/java.sql)
  [Module descriptor]
    requires mandated java.base;
    requires transitive java.logging;
    requires transitive java.transaction.xa;
    requires transitive java.xml;
```

`--check` có thể hiển thị descriptor, dependency sau phân tích và module graph sau khi rút gọn các cạnh được suy ra. Nó cũng nhận diện một số qualified export không được sử dụng.

Có thể kiểm tra nhiều module bằng cách phân tách tên module bằng dấu phẩy:

```bash
jdeps --check java.sql,java.xml
```

Khi module có descriptor, hãy so sánh dependency thực tế được phát hiện với các directive `requires` đang khai báo. Một descriptor có thể khai báo dependency dư thừa hoặc cần điều chỉnh khi API và implementation thay đổi.

Không nên tự động xóa mọi dependency mà công cụ gợi ý là dư. Hãy kiểm tra yêu cầu API, service loading, reflection và hành vi runtime trước khi chỉnh module descriptor.

## 10. Tìm dependency tới JDK internal API

JDK internal API là những class hoặc package nội bộ không được bảo đảm là API công khai, ổn định. Ứng dụng phụ thuộc vào chúng có nguy cơ lỗi khi nâng cấp JDK.

Dùng:

```bash
jdeps --jdk-internals app.jar
```

Hoặc phân tích module:

```bash
jdeps --jdk-internals --module java.sql
```

Trong JDK 24.0.2, phân tích `java.sql` phát hiện các tham chiếu tới `jdk.internal.reflect` từ `java.sql.DriverManager`. Kết quả cũng hiển thị cảnh báo rằng JDK internal API không được hỗ trợ và có thể thay đổi không tương thích.

Khi phát hiện dependency nội bộ:

1. Xác định class và package nội bộ được tham chiếu.
2. Tìm API công khai được khuyến nghị thay thế.
3. Cập nhật mã nguồn hoặc nâng cấp thư viện tạo ra dependency.
4. Build lại và chạy test trên JDK mục tiêu.
5. Chạy lại `jdeps --jdk-internals` để xác nhận dependency đã được loại bỏ.

Không nên xử lý cảnh báo bằng cách chỉ thêm tùy chọn mở package hoặc export nội bộ. Các tùy chọn đó có thể tạm thay đổi khả năng truy cập nhưng không biến API nội bộ thành API được hỗ trợ.

`--jdk-internals` không dùng đồng thời với một số tùy chọn lọc như `--package`, `--regex` và `--summary`. Kiểm tra `jdeps --help` của JDK đang sử dụng trước khi kết hợp các tùy chọn.

## 11. Tìm dependency bị thiếu

Khi một artifact tham chiếu class không có trong các vị trí phân tích, `jdeps` có thể báo missing dependency.

Dùng:

```bash
jdeps --missing-deps app.jar
```

Nếu cần phân giải các dependency ngoài JDK, cung cấp classpath:

```bash
jdeps --class-path "lib/*" --missing-deps app.jar
```

`--class-path` có dạng viết tắt `-cp` hoặc `-classpath`. Trên Windows, dùng dấu chấm phẩy giữa nhiều path element; trên Linux/macOS, dùng dấu hai chấm.

Có thể dùng `--ignore-missing-deps` để tiếp tục phân tích trong trường hợp có dependency không thể phân giải:

```bash
jdeps --ignore-missing-deps --summary app.jar
```

Tùy chọn này bỏ qua dependency thiếu trong quá trình phân tích; nó không bổ sung thư viện còn thiếu và không sửa lỗi runtime. Không nên dùng nó để kết luận artifact đã đầy đủ nếu chưa xác định lý do dependency không được tìm thấy.

`--missing-deps` không kết hợp với một số tùy chọn lọc như `--package`, `--regex` và `--summary`. Nếu lệnh báo tùy chọn xung đột, xem help của đúng phiên bản JDK.

## 12. Lọc dependency theo package, regex hoặc module

Với ứng dụng lớn, có thể giới hạn kết quả theo tiêu chí cụ thể.

| Tùy chọn | Công dụng |
|---|---|
| `--package <package>` | Chỉ tìm dependency khớp tên package |
| `--regex <pattern>` | Lọc dependency theo regular expression |
| `--require <module>` | Lọc dependency theo tên module |
| `--inverse` | Tìm artifact phụ thuộc trực tiếp hoặc gián tiếp vào node khớp bộ lọc |
| `-include <regex>` | Giới hạn class đầu vào được phân tích |

Ví dụ tìm dependency tới package `java.sql`:

```bash
jdeps --package java.sql app.jar
```

Tìm dependency theo module:

```bash
jdeps --require java.sql app.jar
```

Tìm ngược các artifact phụ thuộc vào package:

```bash
jdeps --inverse --package java.sql app.jar
```

`--inverse` phải đi cùng một bộ lọc như `--require`, `--package` hoặc `--regex`. Nó giúp trả lời câu hỏi “những phần nào phụ thuộc vào package hoặc module này?” thay vì chỉ liệt kê dependency đi ra từ đầu vào.

Các bộ lọc `--package`, `--regex` và `--require` loại trừ lẫn nhau trong cùng một lệnh. Dùng từng tiêu chí riêng hoặc thực hiện các lần phân tích độc lập.

## 13. Phân tích riêng dependency của API công khai

Một thư viện có thể dùng nhiều dependency nội bộ trong implementation nhưng chỉ phơi bày một phần nhỏ qua API public/protected.

Dùng `--api-only`:

```bash
jdeps --api-only app.jar
```

Tùy chọn này giới hạn phân tích vào dependency xuất hiện trong chữ ký public và protected của public class, bao gồm kiểu field, tham số method, kiểu trả về và checked exception.

Nó hữu ích khi:

- Đánh giá dependency mà người dùng thư viện cần nhìn thấy.
- Kiểm tra API công khai trước khi tách module.
- Tìm kiểu dữ liệu từ thư viện khác đang xuất hiện trong chữ ký public.
- Phân biệt dependency của API với dependency chỉ dùng bên trong implementation.

`--api-only` không thay thế phân tích toàn bộ. Một thư viện có thể không lộ dependency ra API nhưng vẫn cần dependency đó để chạy method bên trong.

## 14. Phân tích đệ quy dependency

Theo mặc định, `jdeps` phân tích các dependency theo phạm vi của đầu vào và tùy chọn được chỉ định. Có thể yêu cầu công cụ tiếp tục duyệt dependency runtime bằng `--recursive` hoặc `-R`:

```bash
jdeps --recursive --class-path "lib/*" app.jar
```

Chế độ đệ quy giúp thấy dependency gián tiếp qua các thư viện mà ứng dụng tham chiếu.

Nếu chỉ muốn phân tích trực tiếp và không tiếp tục duyệt dependency, dùng:

```bash
jdeps --no-recursive --class-path "lib/*" app.jar
```

Đệ quy có thể làm kết quả lớn hơn đáng kể, nhất là khi classpath chứa framework và nhiều thư viện. Hãy chọn chế độ theo câu hỏi cần trả lời và bảo đảm các dependency cần phân tích đã nằm trong classpath hoặc module path.

## 15. Xuất dependency graph dạng DOT

`jdeps` có thể ghi đồ thị dependency ra file DOT để trực quan hóa:

```bash
jdeps --dot-output dependency-graphs app.jar
```

Dạng viết tắt cũ là `-dotoutput`. Thư mục đích sẽ chứa các file DOT được tạo từ quá trình phân tích, thường gồm đồ thị theo archive hoặc module tùy đầu vào.

Có thể dùng Graphviz để chuyển DOT thành hình:

```bash
dot -Tpng dependency-graphs/app.jar.dot -o dependency-graph.png
```

Tên file DOT cụ thể phụ thuộc artifact và phiên bản công cụ; hãy liệt kê thư mục output để xác định đúng file được tạo.

Đồ thị hữu ích để:

- Nhìn thấy các package phụ thuộc chéo nhau.
- Nhận diện cụm module có kết nối dày đặc.
- Tìm dependency vòng ở mức package hoặc archive.
- Giải thích kiến trúc thư viện trong tài liệu kỹ thuật.

DOT chỉ là định dạng mô tả đồ thị; `jdeps` không tự tạo ảnh PNG. Cần Graphviz hoặc công cụ tương thích để render.

## 16. Kiểm tra JAR cũ và tạo module descriptor gợi ý

Khi chuyển một JAR chưa modular sang JPMS, `jdeps` có thể tạo module descriptor gợi ý.

Dùng:

```bash
jdeps --generate-module-info generated-modules legacy-library.jar
```

Công cụ phân tích JAR và tạo tệp `module-info.java` trong thư mục đích. Descriptor được sinh là điểm khởi đầu để nhà phát triển kiểm tra và chỉnh sửa.

Có thể tạo gợi ý cho open module:

```bash
jdeps --generate-open-module generated-open-modules legacy-library.jar
```

Open module cho phép reflection sâu vào các package của module theo quy tắc JPMS. Chỉ chọn cách này khi framework hoặc ứng dụng thực sự cần reflective access rộng.

Không nên đưa descriptor sinh tự động vào production mà chưa review. Hãy kiểm tra:

- Các directive `requires` và phiên bản dependency.
- Package nào cần `exports`.
- Package nào thực sự cần `opens`.
- Service provider và service consumer.
- API công khai có làm lộ kiểu từ dependency khác không.
- Tên module có ổn định và phù hợp quy ước dự án không.

Các tùy chọn tạo module descriptor có giới hạn kết hợp với `--dot-output` và `--class-path`. Khi cần sinh descriptor, hãy dùng lệnh riêng và kiểm tra help của JDK đang chạy.

## 17. Dependency và multi-release JAR

Multi-release JAR có thể chứa các class thay thế cho những phiên bản Java khác nhau dưới `META-INF/versions/`.

Khi phân tích một phiên bản cụ thể, dùng `--multi-release`:

```bash
jdeps --multi-release 17 --summary library.jar
```

Giá trị có thể là số phiên bản Java từ 9 trở lên hoặc `base` để phân tích nội dung gốc. Điều này quan trọng khi dependency của class thay đổi theo phiên bản runtime.

Nếu bỏ qua phiên bản mục tiêu, kết quả có thể không phản ánh đúng phần class mà JVM sẽ chọn khi chạy trên phiên bản Java cụ thể. Hãy phân tích đúng phiên bản mà ứng dụng hỗ trợ.

## 18. Dùng kết quả jdeps để tạo runtime image bằng jlink

Một ứng dụng modular có thể dùng `jdeps --print-module-deps` để lấy danh sách module cần thiết, rồi đưa danh sách đó vào `jlink`.

Ví dụ với module JDK:

```bash
jdeps --print-module-deps --module java.sql
```

Kết quả comma-separated có thể dùng cho `--add-modules`:

```bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.transaction.xa,java.xml --output sql-runtime
```

Lệnh ví dụ tạo runtime image có các module được nêu. Trong dự án thực tế, hãy dùng danh sách được tạo từ chính artifact và thêm module path chứa dependency ứng dụng nếu cần.

Quy trình thường dùng:

1. Build ứng dụng và các modular dependency.
2. Phân tích dependency bằng `jdeps` với module path và classpath đúng.
3. Lấy danh sách module bằng `--print-module-deps`.
4. Kiểm tra các service, reflection và resource được nạp động.
5. Dùng `jlink` để tạo runtime image.
6. Chạy test và smoke test trên image mới để xác nhận không thiếu module.

Danh sách từ static analysis là cơ sở tốt để bắt đầu, nhưng không thay thế kiểm thử runtime. Service loading, reflection, plugin hoặc tên class được tạo từ cấu hình có thể tạo nhu cầu mà bytecode không thể hiện đầy đủ.

## 19. Giới hạn của phân tích tĩnh

`jdeps` rất hữu ích nhưng không thể biết mọi hành vi xảy ra lúc chạy.

Những trường hợp có thể không được phát hiện đầy đủ:

- Reflection sử dụng tên class hoặc method được tạo từ chuỗi.
- `Class.forName` nhận tên class từ cấu hình hoặc dữ liệu runtime.
- `ServiceLoader` và provider được phát hiện thông qua metadata.
- Plugin được nạp từ thư mục hoặc JAR bên ngoài.
- Class được tạo động hoặc được nạp bởi custom class loader.
- Dependency chỉ xuất hiện trong cấu hình, script hoặc resource.
- Các nhánh mã chỉ được chạy trong một môi trường đặc biệt.

Vì vậy, kết quả “không tìm thấy dependency” không chứng minh ứng dụng không cần thư viện đó. Hãy kết hợp static analysis với test, log runtime, kiểm tra cấu hình và kiến thức về framework đang dùng.

Tương tự, dependency xuất hiện trong báo cáo không nhất thiết là lỗi. Có thể đó là quan hệ hợp lệ, một API được dùng có chủ đích hoặc một dependency chỉ cần trong môi trường cụ thể.

## 20. Lỗi thường gặp khi sử dụng jdeps

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jdeps` không được nhận diện | JDK chưa cài hoặc PATH thiếu thư mục `bin` | Kiểm tra `JAVA_HOME`, PATH và `jdeps --version` |
| Không tìm thấy class dependency | Thiếu thư viện trong classpath hoặc module path | Thêm đúng dependency bằng `--class-path` hoặc `--module-path` |
| Báo missing dependencies | Artifact tham chiếu class không có trong phạm vi phân tích | Dùng `--missing-deps`, kiểm tra dependency và phiên bản JAR |
| Kết quả quá dài | Đang xem class-level hoặc recursive dependency | Dùng `--summary`, `--verbose:package` hoặc lọc kết quả |
| Không thấy dependency được nạp bằng reflection | Static analysis không biết tên class runtime được tạo động | Kiểm tra cấu hình, service metadata và test runtime |
| Cảnh báo JDK internal API | Mã hoặc thư viện tham chiếu package nội bộ | Tìm API công khai thay thế và nâng cấp dependency |
| Module không resolve được | Module path thiếu module hoặc descriptor không hợp lệ | Dùng `--module-path`, `--check` và xác minh module name |
| Tùy chọn bị xung đột | Kết hợp các bộ lọc không tương thích | Xem `jdeps --help` và tách thành các lần chạy |
| DOT output không có hình ảnh | `jdeps` chỉ ghi file DOT | Dùng Graphviz hoặc công cụ render DOT |
| Runtime image thiếu class/service | Chỉ dựa vào static dependency list | Kiểm tra reflection, service loader, plugin và chạy test trên image |

Không nên dùng `--ignore-missing-deps` để che cảnh báo mà chưa hiểu nguyên nhân. Một dependency bị thiếu có thể khiến ứng dụng lỗi ngay khi khởi chạy hoặc chỉ lỗi khi chạy một chức năng cụ thể.

## 21. Quy trình phân tích dependency trong dự án

Một quy trình thực tế có thể thực hiện theo thứ tự:

1. Xác định JDK và phiên bản artifact cần phân tích.
2. Build JAR hoặc thư mục class từ đúng commit và cấu hình.
3. Xác định dependency nằm trên classpath hay module path.
4. Chạy `jdeps --summary` để có bức tranh tổng quát.
5. Dùng `--verbose:package` hoặc `--verbose:class` để tìm nguồn dependency cụ thể.
6. Dùng `--missing-deps` để kiểm tra tham chiếu chưa được phân giải.
7. Dùng `--jdk-internals` để tìm dependency tới API nội bộ.
8. Với modular application, dùng `--check` và `--list-deps` để kiểm tra module graph.
9. Dùng `--api-only` khi đánh giá dependency bị lộ qua API công khai.
10. Dùng `--dot-output` nếu cần đồ thị cho tài liệu hoặc review kiến trúc.
11. Dùng `--print-module-deps` nếu chuẩn bị tạo runtime image.
12. Kiểm tra lại reflection, service loading, plugin và cấu hình runtime.
13. Chạy test trên đúng JDK hoặc runtime image mục tiêu.
14. Lưu lệnh, phiên bản JDK và kết quả phân tích để có thể tái lập.

Không nên xóa dependency chỉ dựa trên một dòng báo cáo. Hãy xác minh cả quan hệ compile-time, API công khai và hành vi runtime trước khi thay đổi build configuration.

## 22. Tổng kết

`jdeps` là công cụ JDK dùng để phân tích dependency tĩnh của class, package, JAR và module Java. Nó giúp hiểu cấu trúc thư viện, tìm dependency thiếu, phát hiện việc sử dụng JDK internal API và xác định module cần thiết cho runtime image.

Những tùy chọn quan trọng:

- `jdeps --summary`: xem dependency tóm tắt.
- `jdeps --verbose:package`: xem quan hệ ở mức package.
- `jdeps --verbose:class`: xem quan hệ ở mức class.
- `jdeps --module-path ... --module ...`: phân tích module trên module path.
- `jdeps --list-deps` và `--print-module-deps`: liệt kê module dependency.
- `jdeps --check`: kiểm tra module descriptor và module graph.
- `jdeps --jdk-internals`: tìm tham chiếu tới JDK internal API.
- `jdeps --missing-deps`: tìm dependency bị thiếu.
- `jdeps --api-only`: chỉ phân tích dependency trong API public/protected.
- `jdeps --dot-output`: xuất dependency graph dạng DOT.
- `jdeps --generate-module-info`: tạo module descriptor gợi ý cho JAR cũ.

Kết hợp `jdeps` với `javac`, `jar`, `jlink` và kiểm thử runtime giúp quản lý dependency tốt hơn, chuẩn bị chuyển đổi sang JPMS và giảm rủi ro khi nâng cấp JDK.

**Tài liệu tham khảo chính thức:**

- [The jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [The jlink Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
