# Tùy chọn --strip-debug của jlink

Khi tạo runtime image tùy biến cho ứng dụng Java, công cụ **jlink** có thể loại bỏ thông tin debug khỏi image bằng tùy chọn **--strip-debug**. Thông tin debug hỗ trợ debugger và công cụ phân tích mã; nó thường không cần thiết để JVM thực thi chương trình. Loại bỏ phần này có thể giảm kích thước runtime image, nhưng cũng làm giảm dữ liệu có sẵn khi cần điều tra lỗi ở mức source hoặc native code.

--strip-debug là một plugin của jlink. Nó được áp dụng trong bước liên kết runtime image, sau khi module đã được biên dịch và được chọn để đưa vào image. Tùy chọn này không thay thế javac và không chọn module nào được đưa vào runtime.

## 1. Debug information là gì?

**Debug information** là metadata được tạo cùng mã đã biên dịch hoặc lưu trong thành phần native để hỗ trợ công cụ debug, profiler và phân tích lỗi.

Trong Java class file, một số thuộc tính debug có thể gồm:

- **LineNumberTable:** ánh xạ bytecode offset với số dòng trong mã nguồn. JVM và công cụ debug có thể dùng thông tin này để hiển thị vị trí lỗi.
- **LocalVariableTable:** tên và phạm vi của biến cục bộ trong phương thức, nếu compiler tạo metadata này.
- **LocalVariableTypeTable:** thông tin kiểu tổng quát của biến cục bộ, nếu được tạo.
- **SourceFile:** tên tệp nguồn gắn với class file.

Các thuộc tính cụ thể có mặt phụ thuộc compiler, tùy chọn biên dịch và bản build JDK. Chúng không phải là logic nghiệp vụ của chương trình. Bytecode vẫn có thể thực thi khi một số metadata debug bị loại bỏ.

Với thư viện native, debug symbols có thể giúp debugger ánh xạ địa chỉ máy về tên hàm, tệp nguồn và dòng mã native. Phạm vi xử lý native debug symbols phụ thuộc JDK, nền tảng và plugin được cung cấp.

## 2. --strip-debug làm gì?

Tùy chọn:

~~~bash
jlink --strip-debug ...
~~~

yêu cầu jlink loại bỏ thông tin debug khỏi **runtime image đầu ra**.

Những mục tiêu chính:

1. Giảm metadata debug không cần thiết trong runtime image.
2. Có thể giảm dung lượng image cần phân phối hoặc lưu trữ.
3. Giữ các module và chức năng runtime đã chọn để ứng dụng tiếp tục chạy.
4. Giảm dữ liệu source-level hoặc native-level có sẵn cho một số công cụ chẩn đoán.

Theo tài liệu jlink, plugin strip-debug loại bỏ debug information khỏi output image. Tác động đến từng loại metadata và native symbol phụ thuộc phiên bản JDK cùng nền tảng. Không nên giả định mọi bản JDK đều xử lý cùng một tập dữ liệu.

### Tác động đến chương trình

Với ứng dụng được liên kết đúng và không phụ thuộc vào metadata debug, việc strip debug không thay đổi ý nghĩa thực thi của bytecode. JVM vẫn nạp module, gọi phương thức và xử lý dữ liệu như trước.

Tác động dễ thấy nhất nằm ở khả năng chẩn đoán:

- Debugger có thể thiếu thông tin để hiển thị tên biến cục bộ.
- Breakpoint theo dòng có thể kém chính xác hoặc không hoạt động như mong đợi nếu line metadata đã bị loại bỏ.
- Stack trace có thể thiếu số dòng nguồn.
- Native debugger có thể thiếu symbol nếu native debug symbols đã được strip.

Mức độ ảnh hưởng tùy dữ liệu nào bị loại bỏ và công cụ đang dùng.

## 3. Phân biệt jlink --strip-debug và javac -g

Hai công cụ hoạt động ở hai giai đoạn khác nhau:

| Tùy chọn | Công cụ | Giai đoạn | Phạm vi |
|---|---|---|---|
| -g | javac | Biên dịch | Tạo đầy đủ debug information trong class file |
| -g:none | javac | Biên dịch | Không tạo debug information cho class file được biên dịch |
| -g:lines,vars,source | javac | Biên dịch | Chọn nhóm debug information cần tạo |
| --strip-debug | jlink | Liên kết runtime image | Loại bỏ debug information khỏi image đầu ra |

javac -g:none ảnh hưởng đến class file do lần biên dịch đó tạo ra. jlink --strip-debug xử lý runtime image sau khi module đã được biên dịch và chọn để liên kết. Vì vậy, jlink có thể xử lý metadata của các module trong image, bao gồm cả module do JDK cung cấp, theo khả năng của plugin.

Nếu chỉ muốn kiểm soát debug metadata của mã nguồn ứng dụng, có thể cân nhắc tùy chọn javac. Nếu mục tiêu là tối ưu runtime image cuối cùng, hãy đánh giá --strip-debug và kiểm tra image sau khi tạo.

Không nên dùng javac -g:none như bằng chứng rằng runtime image đã được strip toàn bộ debug information; các module khác trong image có thể được biên dịch trước bằng cấu hình khác.

## 4. Phiên bản JDK và plugin strip debug

Hành vi của plugin đã thay đổi theo các bản phát hành Java và có khác biệt giữa nhà cung cấp hoặc nền tảng.

- Tài liệu jlink hiện hành mô tả --strip-debug là tùy chọn loại bỏ debug information khỏi output image.
- Theo bài viết kỹ thuật của nhóm Inside Java, trước JDK 13, strip-debug chỉ loại bỏ Java debug attributes. Từ JDK 13, việc strip được mở rộng để có thể loại bỏ thêm native debug symbols trên nền tảng được hỗ trợ.
- Native symbol stripping có phụ thuộc nền tảng và công cụ hệ thống. Bài viết Inside Java mô tả việc sử dụng objcopy trên Linux.
- Một số JDK cung cấp plugin riêng như --strip-java-debug-attributes. Tên và tập plugin khả dụng có thể khác nhau theo bản phân phối.

Trước khi dùng tùy chọn trong CI hoặc build script, hãy kiểm tra:

~~~bash
jlink --version
jlink --list-plugins
~~~

Dùng đúng tùy chọn mà JDK mục tiêu liệt kê. Nếu build trên một vendor JDK nhưng triển khai bằng runtime image của vendor khác, cần kiểm tra lại hành vi và tính tương thích.

Tài liệu tham khảo:

- [Oracle: The jlink Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [Inside Java: Stripping debug info from jlink runtime images](https://inside.java/2019/10/02/strippingdebug-jlink/)

## 5. Ví dụ hoàn chỉnh: tạo hai runtime image để so sánh

Ví dụ sau tạo cùng một ứng dụng modular Java 17 thành hai runtime image:

- runtime-base: image không dùng --strip-debug.
- runtime-stripped: image có dùng --strip-debug.

Hai lệnh jlink giữ nguyên module, launcher và module path để có thể so sánh tác động của tùy chọn.

### Cấu trúc dự án

~~~text
strip-debug-demo/
└── src/
    └── com.acme.demo/
        ├── module-info.java
        └── com/
            └── acme/
                └── demo/
                    └── Main.java
~~~

Tệp src/com.acme.demo/module-info.java:

~~~java
module com.acme.demo {
}
~~~

Tệp src/com.acme.demo/com/acme/demo/Main.java:

~~~java
package com.acme.demo;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello from " + target + "!");
    }
}
~~~

### Bước 1: Biên dịch module

Dùng JDK 17 trở lên, từ thư mục gốc dự án:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.acme.demo
~~~

Kết quả là exploded module:

~~~text
mods/
└── com.acme.demo/
    ├── module-info.class
    └── com/
        └── acme/
            └── demo/
                └── Main.class
~~~

### Bước 2: Tạo runtime image cơ sở

Trên Linux/macOS, giả sử JAVA_HOME trỏ đến JDK đang dùng:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.demo \
  --launcher demo=com.acme.demo/com.acme.demo.Main \
  --output runtime-base
~~~

### Bước 3: Tạo runtime image có strip debug

Dùng cùng module path và module được chọn, thêm --strip-debug:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.demo \
  --launcher demo=com.acme.demo/com.acme.demo.Main \
  --strip-debug \
  --output runtime-stripped
~~~

Trên Windows PowerShell, module path có thể viết:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.demo --launcher demo=com.acme.demo/com.acme.demo.Main --output runtime-base

jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.demo --launcher demo=com.acme.demo/com.acme.demo.Main --strip-debug --output runtime-stripped
~~~

Hai thư mục output phải chưa tồn tại khi chạy jlink. Nếu đã có image cũ, hãy chọn tên thư mục mới hoặc xử lý image cũ theo quy trình build của dự án.

### Bước 4: Chạy cả hai image

Trên Linux/macOS:

~~~bash
./runtime-base/bin/demo
./runtime-stripped/bin/demo
~~~

Cả hai lần chạy đều cho output:

~~~text
Hello from Java!
~~~

Truyền tham số:

~~~bash
./runtime-stripped/bin/demo "JDK tooling"
~~~

Output:

~~~text
Hello from JDK tooling!
~~~

Trên Windows có thể gọi launcher trong thư mục runtime-stripped/bin hoặc gọi runtime-stripped/bin/java.exe với module và lớp main tương ứng.

### Bước 5: Kiểm tra module và kích thước

Xem các module có trong runtime image:

~~~bash
runtime-stripped/bin/java --list-modules
~~~

So sánh kích thước trên Linux/macOS:

~~~bash
du -sh runtime-base runtime-stripped
~~~

Kết quả kích thước phụ thuộc JDK vendor, nền tảng, module, cách build và dữ liệu debug ban đầu. Không có một tỷ lệ giảm cố định. Nếu image không nhỏ đi đáng kể, có thể bản JDK đã strip sẵn một số metadata hoặc các module được chọn vốn không chứa nhiều debug information.

Ví dụ này so sánh chức năng chạy và dung lượng của hai image. Để xác nhận chính xác metadata nào đã bị loại bỏ, cần kiểm tra class/native artifacts bằng công cụ phù hợp với định dạng image và JDK đang dùng.

## 6. Khi nào nên dùng --strip-debug?

Phù hợp khi:

- Tạo runtime image production hoặc container image cần tối ưu kích thước.
- Ứng dụng đã được kiểm thử trên runtime image tương ứng.
- Có hệ thống quan sát khác như log, metrics, tracing và crash reporting.
- Đội vận hành có cách lấy thông tin chẩn đoán bổ sung khi cần.
- Không cần debugger source-level đầy đủ bên trong image production.

Cân nhắc giữ debug information khi:

- Đang phát triển hoặc debug lỗi khó tái hiện.
- Cần breakpoint theo dòng hoặc xem biến cục bộ trong debugger.
- Đang phân tích crash native hoặc cần symbol để ánh xạ stack.
- Cần profiling hoặc công cụ chẩn đoán dựa trên metadata đã bị strip.
- Tạo image phục vụ kiểm thử, staging hoặc điều tra sự cố.

Có thể duy trì hai kiểu image trong pipeline: một image debug phục vụ kiểm thử/chẩn đoán và một image production đã tối ưu. Cả hai cần được tạo từ cùng source revision và cùng cấu hình module để kết quả so sánh có ý nghĩa.

## 7. Kết hợp với các tùy chọn jlink khác

--strip-debug có thể được kết hợp với các tùy chọn tối ưu runtime image khác, miễn là JDK hiện tại hỗ trợ:

- **--add-modules:** chọn module gốc cần liên kết.
- **--module-path:** cung cấp JMOD, modular JAR hoặc exploded module.
- **--compress:** nén resource trong image.
- **--no-header-files:** loại header files.
- **--no-man-pages:** loại man pages.
- **--launcher:** tạo lệnh chạy thuận tiện cho module và lớp main.
- **--output:** chỉ định thư mục image đầu ra.

Ví dụ kết hợp strip debug với nén resource:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.demo \
  --compress=zip-6 \
  --strip-debug \
  --output runtime-production
~~~

Khi so sánh dung lượng, giữ nguyên các tùy chọn khác giữa hai lần build và chỉ thay đổi --strip-debug. Nếu đồng thời thay module, compression hoặc locale, sẽ khó xác định mức giảm đến từ yếu tố nào.

## 8. Lỗi thường gặp

### Unknown option hoặc plugin not found

JDK hiện tại có thể không hỗ trợ tùy chọn hoặc plugin đang dùng. Kiểm tra jlink --version và jlink --list-plugins; chọn option có trong đúng toolchain mục tiêu.

### Thiếu công cụ strip native symbols

Một số cách strip native debug symbols cần công cụ hệ thống như objcopy trên Linux. Nếu plugin báo không tìm thấy công cụ, kiểm tra yêu cầu của JDK/vendor, cài hoặc chỉ định công cụ đúng theo tài liệu nền tảng. Không giả định tùy chọn native stripping có mặt trên mọi OS.

### Runtime image chạy được nhưng debugger thiếu thông tin

Đây có thể là kết quả mong đợi khi debug metadata đã bị strip. Dùng image debug chưa strip hoặc lưu artifact debug phù hợp với quy trình phát hành để điều tra.

### Image không giảm kích thước

JDK vendor có thể đã loại bỏ một số metadata từ trước; module được chọn có thể ít debug data; hoặc dung lượng chủ yếu đến từ native library và resource. Đo kích thước trước/sau với cùng cấu hình và kiểm tra plugin thực tế.

### jlink báo module not found

Đây là lỗi module path hoặc dependency, không phải lỗi strip debug. Kiểm tra JMOD của JDK, exploded module ứng dụng, module name và requires trong module descriptor.

### Output directory already exists

jlink yêu cầu vị trí output phù hợp để tạo image. Dùng thư mục output mới cho mỗi lần build hoặc để pipeline dọn image cũ theo chính sách artifact của dự án.

### Image chạy khác với image build thường

Kiểm tra module graph, launcher, resource và cấu hình của hai lệnh jlink. Nếu hai lệnh chỉ khác --strip-debug mà ứng dụng thay đổi hành vi, hãy tái hiện bằng image chưa strip và báo lỗi kèm JDK vendor/version, OS, module list và lệnh build đầy đủ.

## 9. Checklist trước khi strip debug

- Kiểm tra phiên bản và vendor của JDK dùng để link.
- Chạy jlink --list-plugins để xác nhận plugin khả dụng.
- Xác định mục tiêu là giảm Java debug attributes, native symbols hay cả hai.
- Giữ nguyên module path và --add-modules giữa các lần build so sánh.
- Tạo image debug và image production từ cùng source revision khi cần.
- Chạy smoke test trên image đã strip.
- Kiểm tra log, stack trace, metrics và crash reporting trong môi trường triển khai.
- Đánh giá debugger và profiler có cần metadata đã bị loại bỏ hay không.
- Đo kích thước thực tế; không giả định mức giảm cố định.
- Ghi lại JDK vendor/version, OS, plugin và các tùy chọn jlink trong build log.
- Giữ artifact hoặc image debug phù hợp để điều tra sự cố nếu production image đã tối giản.

## 10. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| jlink | Công cụ liên kết module và dependency thành runtime image tùy biến |
| --strip-debug | Plugin jlink loại bỏ debug information khỏi output image |
| Debug information | Metadata hỗ trợ debugger và công cụ phân tích |
| LineNumberTable | Ánh xạ bytecode offset với số dòng nguồn |
| LocalVariableTable | Metadata tên và phạm vi biến cục bộ |
| SourceFile | Metadata tên tệp nguồn trong class file |
| Native debug symbols | Symbol hỗ trợ debug và phân tích mã native |
| javac -g | Yêu cầu compiler tạo debug information |
| javac -g:none | Không tạo debug information trong class file được biên dịch |
| Runtime image | Môi trường chạy được liên kết từ các module được chọn |
| jlink plugin | Phần mở rộng xử lý hoặc tối ưu image trong quá trình link |

--strip-debug là một bước tối ưu ở giai đoạn tạo runtime image. Hãy xác nhận plugin trên đúng JDK, so sánh image với cùng cấu hình, kiểm thử chức năng sau khi strip và giữ đủ artifact chẩn đoán để đội vận hành có thể điều tra sự cố khi cần.