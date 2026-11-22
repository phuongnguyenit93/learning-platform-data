# Phân tích classpath bằng jdeps

§jdeps§ là công cụ của JDK dùng để phân tích dependency của Java class file. Khi làm việc với ứng dụng hoặc thư viện chạy trên classpath, §jdeps§ giúp xác định package và class nào đang được tham chiếu, thư viện bên ngoài nào cần có để phân giải các tham chiếu đó, và module nền tảng Java nào được sử dụng.

Phân tích classpath hữu ích khi kiểm tra một JAR trước khi phát hành, tìm dependency bị thiếu, phát hiện việc dùng JDK internal API, chuẩn bị chuyển thư viện sang JPMS hoặc xác định các module cần cho runtime image bằng §jlink§.

Bài này sử dụng JDK 17 trở lên. Nội dung đi từ cách chọn đầu vào và cung cấp classpath, đến các mức phân tích package/class, lọc kết quả, phát hiện dependency thiếu, xuất sơ đồ và diễn giải giới hạn của phân tích tĩnh.

## 1. jdeps phân tích điều gì?

§jdeps§ đọc bytecode trong class file và tìm các tham chiếu dependency có thể nhận diện. Đầu vào có thể là:

- Một tệp §.class§.
- Một thư mục chứa class file.
- Một JAR chứa các class đã biên dịch.
- Nhiều class, thư mục hoặc JAR được truyền làm đầu vào.

Cú pháp tổng quát:

~~~text
jdeps [options] path ...
~~~

Mỗi đầu vào là thành phần được phân tích. Tùy chọn §--class-path§ cung cấp thêm vị trí để §jdeps§ tìm các class mà đầu vào tham chiếu.

Ví dụ:

~~~powershell
jdeps app.jar
~~~

Lệnh này phân tích các dependency có thể thấy trong §app.jar§. Kết quả mặc định tập trung ở mức package, cho biết package nào phụ thuộc package hoặc module nào.

Điều cần phân biệt:

- **Input path:** class file, thư mục hoặc JAR mà bạn muốn phân tích.
- **Class path:** thư mục/JAR bổ sung dùng để phân giải class được tham chiếu từ input.
- **Module path:** nơi tìm named module khi phân tích ứng dụng dùng JPMS.

Nếu thư viện nằm trong §lib/customer.jar§, chỉ truyền §app.jar§ làm input chưa đủ để §jdeps§ phân giải mọi tham chiếu tới thư viện đó. Hãy cung cấp thư viện qua §--class-path§.

## 2. Chuẩn bị ví dụ có dependency ngoài

Ta tạo ứng dụng classpath gồm hai JAR:

- §customer.jar§ chứa class §com.example.model.Customer§.
- §app.jar§ chứa class chính §com.example.app.Main§ và tham chiếu tới §Customer§.

Cấu trúc:

~~~text
project/
├── src/
│   ├── lib/
│   │   └── com/example/model/Customer.java
│   └── app/
│       └── com/example/app/Main.java
├── build/
│   ├── lib-classes/
│   └── app-classes/
├── lib/
│   └── customer.jar
└── app.jar
~~~

Nội dung §src/lib/com/example/model/Customer.java§:

~~~java
package com.example.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Nội dung §src/app/com/example/app/Main.java§:

~~~java
package com.example.app;

import com.example.model.Customer;
import java.time.LocalDate;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Ada" : args[0];
        Customer customer = new Customer(name);
        System.out.println(customer.name() + " | " + LocalDate.of(2026, 1, 1));
    }
}
~~~

Từ thư mục gốc §project§, biên dịch và đóng gói thư viện trước.

PowerShell trên Windows:

~~~powershell
New-Item -ItemType Directory -Force -Path build/lib-classes, build/app-classes, lib | Out-Null
javac -d build/lib-classes src/lib/com/example/model/Customer.java
jar --create --file lib/customer.jar -C build/lib-classes .
~~~

Biên dịch ứng dụng với thư viện trên classpath:

~~~powershell
javac --class-path lib/customer.jar -d build/app-classes src/app/com/example/app/Main.java
jar --create --file app.jar --main-class com.example.app.Main -C build/app-classes .
~~~

Chạy ứng dụng:

~~~powershell
java --class-path "app.jar;lib/customer.jar" com.example.app.Main Grace
~~~

Stdout:

~~~text
Grace | 2026-01-01
~~~

Trên Linux/macOS, dấu phân cách classpath là dấu hai chấm:

~~~bash
java --class-path "app.jar:lib/customer.jar" com.example.app.Main Grace
~~~

Ví dụ này có một dependency bên ngoài là §com.example.model.Customer§ và một dependency nền tảng là §java.time.LocalDate§. Đây là đầu vào phù hợp để xem §jdeps§ phân tích classpath như thế nào.

## 3. Cung cấp classpath cho jdeps

Dùng §--class-path§ (có alias §-cp§ hoặc §-classpath§) để chỉ định nơi tìm class file phụ thuộc.

Windows:

~~~powershell
jdeps --class-path "lib/customer.jar" app.jar
~~~

Linux/macOS:

~~~bash
jdeps --class-path "lib/customer.jar" app.jar
~~~

Nếu có nhiều thư viện, phân tách theo hệ điều hành.

Windows:

~~~powershell
jdeps --class-path "lib/customer.jar;lib/logging.jar;lib/model.jar" app.jar
~~~

Linux/macOS:

~~~bash
jdeps --class-path "lib/customer.jar:lib/logging.jar:lib/model.jar" app.jar
~~~

Có thể dùng wildcard cho các JAR trong một thư mục:

~~~powershell
jdeps --class-path "lib/*" app.jar
~~~

Một classpath đầy đủ rất quan trọng. Nếu thiếu dependency, §jdeps§ có thể báo class không tìm thấy hoặc liệt kê dependency chưa được phân giải. Kết quả khi thiếu class path không phản ánh đầy đủ đồ thị dependency của ứng dụng.

Đừng nhầm §--class-path§ với đầu vào cần phân tích. Ví dụ, trong lệnh:

~~~powershell
jdeps --class-path "lib/*" app.jar
~~~

§app.jar§ là archive được phân tích; §lib/*§ là nơi tìm các class phụ thuộc của nó.

## 4. Đọc kết quả mặc định và dependency summary

Chạy:

~~~powershell
jdeps --class-path "lib/customer.jar" app.jar
~~~

Kết quả mặc định cho biết quan hệ dependency ở mức package. Dạng output thường có các dòng archive/module đích và package nguồn, ví dụ:

~~~text
app.jar -> java.base
app.jar -> lib/customer.jar
   com.example.app -> java.lang
   com.example.app -> java.time
   com.example.app -> com.example.model
~~~

Tên archive, đường dẫn và cách nhóm dòng có thể thay đổi theo JDK, đầu vào và classpath. Hãy dùng output thực tế của dự án để kết luận.

Ý nghĩa:

- §java.base§ cung cấp các lớp nền tảng như §java.lang§.
- §java.time§ là package thuộc module §java.base§.
- §com.example.model§ đến từ thư viện §customer.jar§.
- Dòng dependency ở mức archive cho biết §app.jar§ tham chiếu tới thư viện ngoài và module JDK.

Chỉ in tóm tắt dependency:

~~~powershell
jdeps --summary --class-path "lib/customer.jar" app.jar
~~~

Alias ngắn là:

~~~powershell
jdeps -s --class-path "lib/customer.jar" app.jar
~~~

Dùng summary khi cần biết ứng dụng phụ thuộc archive/module nào mà chưa cần xem từng package hoặc class.

## 5. Chọn mức chi tiết package hoặc class

### 5.1. Phân tích ở mức package

§-verbose:package§ cho biết package nguồn phụ thuộc package đích:

~~~powershell
jdeps -verbose:package --class-path "lib/customer.jar" app.jar
~~~

Mức package phù hợp khi:

- Muốn nhìn tổng thể các khu vực của ứng dụng phụ thuộc lẫn nhau.
- Muốn tìm dependency giữa các package trong kiến trúc.
- Muốn xác định package nào cần một thư viện bên ngoài.
- Muốn tránh output quá dài khi archive có nhiều class.

### 5.2. Phân tích ở mức class

§-verbose:class§ hiển thị dependency cụ thể giữa các class:

~~~powershell
jdeps -verbose:class --class-path "lib/customer.jar" app.jar
~~~

Mức class hữu ích khi:

- Tìm chính xác class nào kéo theo một thư viện.
- Điều tra dependency ngoài dự kiến.
- Tìm class thuộc JDK internal API.
- Xem ảnh hưởng của một class cụ thể trước khi refactor.

### 5.3. Hiển thị tất cả dependency class

~~~powershell
jdeps -verbose:class -filter:none --class-path "lib/customer.jar" app.jar
~~~

Tùy chọn §-v§ tương đương hiển thị tất cả dependency ở mức class và không lọc các quan hệ nội bộ theo cách mặc định.

Output class-level có thể rất lớn. Bắt đầu bằng summary hoặc package view, sau đó chuyển sang class view khi đã xác định được khu vực cần điều tra.

## 6. Lọc dependency và giới hạn class được phân tích

§jdeps§ cung cấp các tùy chọn để thu hẹp kết quả.

| Tùy chọn | Tác dụng |
|---|---|
| §-p§ hoặc §--package§ | Chỉ tìm dependency liên quan tới package được chỉ định |
| §-e§ hoặc §--regex§ | Lọc dependency theo regular expression |
| §--require§ | Lọc dependency theo tên module |
| §-include§ | Giới hạn các class nguồn được phân tích theo regex |
| §-f§ hoặc §-filter§ | Lọc dependency trong output |
| §-filter:package§ | Lọc quan hệ trong cùng package; đây là mặc định |
| §-filter:archive§ | Lọc dependency trong cùng archive |
| §-filter:module§ | Lọc dependency trong cùng module |
| §-filter:none§ | Tắt các bộ lọc package/archive mặc định |

Ví dụ chỉ xem dependency liên quan tới package §com.example.model§:

~~~powershell
jdeps --package com.example.model --class-path "lib/*" app.jar
~~~

Ví dụ dùng regex để lọc package thuộc §com.example§:

~~~powershell
jdeps --regex "com\.example\..*" --class-path "lib/*" app.jar
~~~

§--package§ và §--regex§ loại trừ lẫn nhau trong cùng lệnh. Chọn một cách lọc phù hợp.

Dùng §-include§ để giới hạn class nguồn:

~~~powershell
jdeps -include "com\.example\.app\..*" --class-path "lib/*" app.jar
~~~

Phân biệt hai việc:

- §-include§ quyết định class nào trong input được đem ra phân tích.
- §--package§ và §--regex§ lọc các dependency được tìm thấy.

## 7. Phân tích dependency đệ quy

Mặc định, bạn thường bắt đầu từ dependency trực tiếp của input. Khi cần đi sâu qua các thư viện mà ứng dụng phụ thuộc, dùng §-R§ hoặc §--recursive§:

~~~powershell
jdeps --recursive --class-path "lib/*" app.jar
~~~

Phân tích đệ quy hữu ích khi:

- Muốn biết dependency gián tiếp của thư viện.
- Đánh giá toàn bộ chuỗi archive mà ứng dụng cần.
- Tìm một dependency nền tảng được kéo vào qua thư viện khác.
- Chuẩn bị di chuyển một hệ thống nhiều JAR sang module path.

Có thể tắt phân tích đệ quy bằng:

~~~powershell
jdeps --no-recursive --class-path "lib/*" app.jar
~~~

Phân tích đệ quy có thể làm output dài hơn và tốn thời gian hơn khi classpath chứa nhiều thư viện. Hãy dùng đúng mức cần thiết cho câu hỏi đang điều tra.

## 8. Tìm dependency bị thiếu

Một trong những mục tiêu quan trọng của classpath analysis là phát hiện class mà bytecode tham chiếu nhưng không thể tìm thấy.

Dùng:

~~~powershell
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Lệnh này tìm các dependency chưa được phân giải. Nếu kết quả có tên class thiếu, hãy kiểm tra:

1. Class đó thuộc JAR nào.
2. JAR đã có trong thư mục dependency chưa.
3. Đường dẫn JAR đã được đưa vào §--class-path§ chưa.
4. Phiên bản JAR có chứa class đó hay không.
5. Dependency có được tải động theo cấu hình hay không.

Có thể bỏ qua dependency thiếu bằng §--ignore-missing-deps§ trong một số trường hợp phân tích có chủ đích:

~~~powershell
jdeps --ignore-missing-deps --class-path "lib/*" app.jar
~~~

Tùy chọn này chỉ thay đổi cách công cụ xử lý dependency không tìm thấy. Nó không bổ sung thư viện và không chứng minh ứng dụng chạy được. Khi chuẩn bị release, hãy sửa classpath hoặc dependency thực tế thay vì dùng tùy chọn này để che lỗi.

Không nên kết luận mọi dependency thiếu đều là lỗi runtime chắc chắn. Có thể bytecode tham chiếu tới class trong một nhánh hiếm dùng hoặc tùy chọn triển khai. Tuy nhiên, cần xác định lý do trước khi chấp nhận dependency chưa phân giải.

## 9. Tìm việc sử dụng JDK internal API

Một ứng dụng có thể biên dịch được nhưng lại phụ thuộc vào API nội bộ của JDK, chẳng hạn các package dưới §sun.*§ hoặc §com.sun.*§ không thuộc API công khai được bảo đảm.

Dùng:

~~~powershell
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

Trong JDK 17, alias ngắn là §-jdkinternals§:

~~~powershell
jdeps -jdkinternals --class-path "lib/*" app.jar
~~~

Kết quả giúp xác định class nào tham chiếu tới JDK internal API. Đây là dấu hiệu cần xử lý vì API nội bộ có thể thay đổi hoặc bị đóng trong phiên bản JDK khác.

Khi phát hiện:

1. Xác định class và package nội bộ đang được tham chiếu.
2. Tìm API Java SE công khai có thể thay thế.
3. Kiểm tra tài liệu migration hoặc hướng dẫn thay thế tương ứng.
4. Cập nhật thư viện hoặc source.
5. Chạy lại §jdeps§ và test trên JDK mục tiêu.

Không dùng §--add-exports§ như giải pháp lâu dài nếu có API công khai thay thế. Tùy chọn này chỉ điều chỉnh quyền truy cập module cho trường hợp cần thiết, không biến internal API thành API ổn định.

## 10. Chỉ phân tích dependency trong public API

§--api-only§ giới hạn phân tích vào dependency xuất hiện trong chữ ký API public/protected của public class, ví dụ:

- Kiểu của field public/protected.
- Kiểu tham số method.
- Kiểu trả về.
- Kiểu checked exception được khai báo.

Lệnh:

~~~powershell
jdeps --api-only --class-path "lib/*" app.jar
~~~

Tùy chọn này hữu ích khi đánh giá dependency mà người dùng thư viện phải biết hoặc phải có để biên dịch code sử dụng API.

Phân tích API-only không đại diện cho toàn bộ dependency lúc runtime. Một implementation nội bộ có thể dùng thư viện khác dù dependency đó không xuất hiện trong public signature. Vì vậy, hãy dùng kết hợp với phân tích package/class đầy đủ.

## 11. Phân tích JAR đa phiên bản

Multi-release JAR có thể chứa nhiều bản class cho các phiên bản Java khác nhau dưới thư mục §META-INF/versions§.

Dùng §--multi-release§ để chỉ định phiên bản cần phân tích:

~~~powershell
jdeps --multi-release 17 --class-path "lib/*" app.jar
~~~

Có thể dùng §base§ để phân tích các class ở phiên bản nền:

~~~powershell
jdeps --multi-release base --class-path "lib/*" app.jar
~~~

Nếu bỏ qua tùy chọn này, kết quả có thể không tương ứng với class variant mà ứng dụng chạy trên runtime mục tiêu thực sự sử dụng. Khi đánh giá thư viện multi-release, hãy phân tích đúng phiên bản Java sẽ triển khai.

## 12. Xuất sơ đồ dependency bằng DOT

Để tạo file đồ thị, dùng §--dot-output§:

~~~powershell
jdeps --dot-output build/deps --class-path "lib/*" app.jar
~~~

§jdeps§ tạo các file DOT mô tả dependency của archive và file §summary.dot§ thể hiện quan hệ giữa các archive.

Có thể mở file DOT bằng Graphviz để chuyển thành hình:

~~~powershell
dot -Tpng build/deps/summary.dot -o build/deps/summary.png
~~~

Sơ đồ hữu ích khi:

- Trình bày dependency giữa nhiều JAR.
- Tìm vòng phụ thuộc giữa các thành phần.
- Xem package/archive nào có nhiều liên kết.
- Trao đổi với nhóm phát triển về việc tách module hoặc thư viện.

Nếu chưa cài Graphviz, file DOT vẫn là văn bản có cấu trúc và có thể mở bằng editor. Tùy chọn §--dot-output§ của §jdeps§ chỉ xuất dữ liệu đồ thị; nó không tự tạo PNG.

## 13. Từ classpath analysis đến module dependency

§jdeps§ cũng hỗ trợ phân tích module dependency. Với ứng dụng classpath, có thể dùng §--print-module-deps§ để in danh sách module JDK cần thiết theo phân tích:

~~~powershell
jdeps --print-module-deps --class-path "lib/*" app.jar
~~~

Kết quả là danh sách tên module phân tách bằng dấu phẩy. Danh sách này có thể dùng làm đầu vào cho §jlink --add-modules§ khi tạo custom runtime.

Ví dụ quy trình:

~~~powershell
jdeps --print-module-deps --class-path "lib/*" app.jar
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging --output runtime
~~~

Trong thực tế, hãy thay danh sách module trong lệnh §jlink§ bằng kết quả đã được kiểm tra từ §jdeps§. Không sao chép ví dụ §java.base,java.logging§ nếu ứng dụng cần module khác.

Lưu ý: runtime image do §jlink§ tạo chứa các module Java được liên kết, không tự đóng gói JAR ứng dụng và mọi thư viện classpath bên ngoài. Khi phân phối ứng dụng, vẫn phải đóng gói §app.jar§ và dependency JAR, rồi cấu hình launcher/classpath phù hợp.

Nếu muốn phân tích module đã có module descriptor, dùng §--module-path§ và các tùy chọn module như §--module§ hoặc §--check§. §jdeps --generate-module-info§ cũng có thể tạo bản nháp §module-info.java§ cho JAR, nhưng cần review thủ công các directive trước khi dùng làm module descriptor chính thức.

## 14. Những tùy chọn thường dùng

| Tùy chọn | Công dụng |
|---|---|
| §--class-path§, §-cp§ | Cung cấp thư mục/JAR để phân giải class |
| §--module-path§ | Cung cấp named module |
| §-summary§, §-s§ | Chỉ in dependency summary |
| §-verbose:package§ | In dependency ở mức package |
| §-verbose:class§ | In dependency ở mức class |
| §-R§, §--recursive§ | Phân tích dependency đệ quy |
| §--no-recursive§ | Không đi sâu dependency |
| §--missing-deps§ | Tìm dependency chưa phân giải |
| §--ignore-missing-deps§ | Bỏ qua dependency thiếu trong phân tích |
| §--jdk-internals§ | Tìm tham chiếu tới JDK internal API |
| §--api-only§ | Chỉ phân tích dependency trong public/protected API |
| §--multi-release§ | Chọn class variant của multi-release JAR |
| §--dot-output§ | Xuất dependency graph dưới dạng DOT |
| §--print-module-deps§ | In danh sách module phù hợp cho quy trình jlink |
| §--generate-module-info§ | Sinh bản nháp module descriptor cho JAR |
| §--check§ | Phân tích module graph của named module |

Xem trợ giúp của đúng JDK đang dùng:

~~~powershell
jdeps --help
~~~

Một số tùy chọn có thể khác giữa các phiên bản JDK. Hãy xem §jdeps --help§ và manual tương ứng với JDK mục tiêu trước khi đưa lệnh vào build script.

## 15. Giới hạn của phân tích tĩnh

§jdeps§ phân tích dependency có thể nhận diện trong bytecode. Nó không phải công cụ quan sát mọi class thực sự được nạp trong một phiên chạy.

Các trường hợp cần kiểm tra riêng:

- **Reflection:** tên class được tạo từ chuỗi hoặc file cấu hình có thể không xuất hiện như tham chiếu class thông thường.
- **ServiceLoader:** provider được tìm theo cơ chế service; cần kiểm tra service configuration và provider module.
- **Plugin:** plugin được phát hiện trong thư mục hoặc tải theo cấu hình có thể không nằm trong đầu vào phân tích.
- **JNI/native code:** dependency native không được mô tả đầy đủ bằng tham chiếu class Java.
- **Resource:** resource được nạp theo tên không nhất thiết hiện ra như dependency class.
- **Conditional code:** class chỉ được dùng trong một cấu hình hoặc môi trường cụ thể có thể không được kiểm tra trong lần phân tích này.

Vì vậy, kết quả §jdeps§ là bản đồ dependency tĩnh có giá trị, nhưng không thay thế integration test, kiểm tra cấu hình và theo dõi class loading ở runtime.

## 16. Lỗi thường gặp khi phân tích classpath

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| §Class ... not found§ hoặc missing dependency | Classpath chưa chứa thư viện được tham chiếu | Bổ sung đúng JAR/thư mục bằng §--class-path§ |
| Output chỉ hiện dependency JDK | Thư viện ngoài chưa được cung cấp hoặc không có tham chiếu tĩnh tới nó | Kiểm tra classpath và bytecode của input |
| Output quá dài | Dùng class-level hoặc recursive analysis trên nhiều thư viện | Bắt đầu bằng §-summary§ hoặc §-verbose:package§ |
| Không thấy dependency trong reflection | Tên class được tạo động từ chuỗi/cấu hình | Kiểm tra cấu hình runtime và test đường reflection |
| Kết quả multi-release không đúng runtime | Phân tích nhầm class variant | Dùng §--multi-release§ theo phiên bản triển khai |
| Dependency nội bộ bị ẩn | Bộ lọc mặc định loại một số quan hệ trong cùng package/archive | Dùng §-filter:none§ khi cần xem toàn bộ |
| Phát hiện JDK internal API | Code hoặc thư viện phụ thuộc package nội bộ | Tìm API công khai thay thế và nâng cấp thư viện |
| §--print-module-deps§ thiếu module runtime | Phân tích tĩnh không thấy dependency động hoặc provider | Bổ sung module theo cấu hình runtime và kiểm thử image |
| DOT không tạo được hình | Chưa có Graphviz hoặc gọi sai đường dẫn file | Kiểm tra file DOT; cài Graphviz nếu cần PNG/SVG |

## 17. Quy trình phân tích classpath trong dự án

Thực hiện theo trình tự:

1. Chọn JAR hoặc thư mục class thực sự được triển khai làm input.
2. Liệt kê dependency bên ngoài và đưa chúng vào §--class-path§.
3. Chạy §jdeps§ mặc định hoặc §-summary§ để có bức tranh tổng thể.
4. Chuyển sang §-verbose:package§ để tìm package liên quan.
5. Dùng §-verbose:class§ và §-filter:none§ để xác định class cụ thể.
6. Chạy §--missing-deps§ để tìm tham chiếu chưa phân giải.
7. Chạy §--jdk-internals§ để phát hiện API nội bộ.
8. Dùng §-R§ nếu cần phân tích dependency gián tiếp.
9. Dùng §--multi-release§ nếu input là multi-release JAR.
10. Xuất §--dot-output§ nếu cần sơ đồ dependency.
11. Dùng §--print-module-deps§ để hỗ trợ tạo runtime image khi phù hợp.
12. Kiểm tra riêng reflection, service, plugin, resource và native code bằng cấu hình/test thực tế.

## 18. Checklist trước khi kết luận

- [ ] Đầu vào là class file, thư mục class hoặc JAR đúng với artifact triển khai.
- [ ] Đã cung cấp đầy đủ thư viện phụ thuộc bằng §--class-path§.
- [ ] Đã chọn mức summary, package hoặc class phù hợp câu hỏi.
- [ ] Đã kiểm tra bộ lọc mặc định trước khi kết luận một dependency không tồn tại.
- [ ] Đã chạy §--missing-deps§ để tìm tham chiếu chưa phân giải.
- [ ] Đã kiểm tra JDK internal API bằng §--jdk-internals§.
- [ ] Đã dùng §-R§ nếu cần dependency gián tiếp.
- [ ] Đã chọn đúng §--multi-release§ cho multi-release JAR.
- [ ] Đã kiểm tra dependency reflection, service, plugin, resource và native riêng.
- [ ] Nếu dùng §--print-module-deps§, đã review danh sách trước khi đưa vào §jlink§.
- [ ] Đã giữ lại lệnh và phiên bản JDK để có thể tái lập kết quả.

Phân tích classpath bằng §jdeps§ giúp hiểu ứng dụng tham chiếu tới package, class, thư viện và module nền tảng nào. Bắt đầu với input đúng và classpath đầy đủ, đọc summary/package view trước, rồi dùng class view, recursive analysis và missing-dependency checks để điều tra sâu. Kết hợp kết quả tĩnh với kiểm thử runtime để không bỏ sót dependency được nạp động.

## Tài liệu tham khảo

- Oracle, The jdeps Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Oracle, Module jdk.jdeps, Java SE 17 API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdeps/module-summary.html
- Oracle, The javac Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
