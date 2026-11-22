# jdeps phát hiện phụ thuộc module JDK

## 1. jdeps dùng để làm gì?

**jdeps** là công cụ dòng lệnh đi kèm JDK, dùng để phân tích các phụ thuộc được thể hiện trong bytecode Java. Công cụ có thể đọc file **.class**, JAR hoặc thư mục chứa class, sau đó cho biết mã nguồn đã biên dịch đang tham chiếu đến package, class và module nào.

Trong Java Platform Module System (JPMS, từ Java 9), jdeps giúp trả lời những câu hỏi thực tế:

- Ứng dụng đang cần những module JDK nào, chẳng hạn **java.base**, **java.sql** hoặc **java.logging**?
- Một JAR có đang sử dụng API nội bộ của JDK hay không?
- Khi chuyển ứng dụng từ classpath sang module path, cần khai báo những phụ thuộc nào?
- Khi tạo runtime image tối giản bằng **jlink**, cần đưa những module JDK nào vào image?
- Vì sao jdeps không phân giải được một số class và cần bổ sung thư viện nào vào classpath hoặc module path?

jdeps thực hiện **phân tích tĩnh**. Nó đọc bytecode và các tham chiếu có thể xác định từ bytecode, không chạy ứng dụng. Vì vậy, kết quả phản ánh các phụ thuộc mà công cụ phát hiện được trong artifact tại thời điểm phân tích.

## 2. Chuẩn bị và phạm vi phân tích

jdeps nằm trong thư mục **bin** của JDK. Có thể kiểm tra phiên bản và cú pháp bằng:

~~~bash
jdeps --version
jdeps --help
~~~

Cú pháp tổng quát:

~~~bash
jdeps [options] <path>
~~~

Đối số **<path>** có thể là một file class, một JAR hoặc một thư mục chứa các class. Có thể phân tích nhiều artifact trong cùng một lần chạy. Nên dùng phiên bản jdeps phù hợp với JDK mục tiêu của ứng dụng, đặc biệt khi artifact có class được biên dịch cho nhiều phiên bản Java.

Một lượt phân tích thường bắt đầu từ JAR đã đóng gói. Phân tích artifact cuối giúp tránh bỏ sót khác biệt giữa mã nguồn và nội dung thực tế được đưa vào bản phát hành.

## 3. Quy trình tìm phụ thuộc module JDK

### Bước 1: Xem tổng quan phụ thuộc

Chạy chế độ summary:

~~~bash
jdeps --summary build/libs/app.jar
~~~

Kết quả thường cho biết artifact phụ thuộc vào những module nào. Ví dụ minh họa:

~~~text
app.jar -> java.base
app.jar -> java.logging
app.jar -> java.sql
~~~

Điều này cho thấy bytecode trong JAR có tham chiếu đến các API thuộc những module được liệt kê. **java.base** xuất hiện trong hầu hết ứng dụng Java vì đây là module nền tảng mà các module khác đọc ngầm theo quy tắc của JPMS.

Summary phù hợp để kiểm kê nhanh. Khi cần biết class hoặc package nào tạo ra một phụ thuộc, hãy chuyển sang chế độ chi tiết.

### Bước 2: Truy dấu phụ thuộc đến package hoặc class

Phân tích ở cấp package:

~~~bash
jdeps --verbose:package build/libs/app.jar
~~~

Phân tích ở cấp class:

~~~bash
jdeps --verbose:class build/libs/app.jar
~~~

Chế độ package giúp thu hẹp khu vực cần kiểm tra. Chế độ class hữu ích khi cần tìm chính xác class nào đang tham chiếu đến một API. Kết quả chi tiết thường dài hơn summary đáng kể, vì vậy nên dùng sau khi đã biết module hoặc package đáng chú ý.

### Bước 3: Liệt kê module JDK cần thiết

Dùng **--list-deps** để liệt kê các module phụ thuộc:

~~~bash
jdeps --list-deps build/libs/app.jar
~~~

Dùng **--print-module-deps** khi cần một danh sách module dạng phân tách bằng dấu phẩy:

~~~bash
jdeps --print-module-deps build/libs/app.jar
~~~

Ví dụ đầu ra có thể là:

~~~text
java.base,java.logging,java.sql
~~~

Danh sách này hữu ích làm đầu vào khi cấu hình **jlink**. Hãy xem đây là tập module được suy ra từ các tham chiếu mà jdeps phân tích được; vẫn cần kiểm thử ứng dụng trong runtime image thực tế.

### Bước 4: Kiểm tra API nội bộ của JDK

Chạy:

~~~bash
jdeps --jdk-internals build/libs/app.jar
~~~

Tùy chọn này tìm các tham chiếu đến API nội bộ của JDK, ví dụ những package có tiền tố như **sun.*** hoặc một số API **com.sun.***. Kết quả có thể chỉ ra class sử dụng API, API nội bộ được tham chiếu và gợi ý thay thế nếu công cụ biết cách thay thế phù hợp.

API nội bộ không phải hợp đồng tương thích công khai. Chúng có thể thay đổi hoặc bị đóng quyền truy cập giữa các phiên bản JDK. Khi phát hiện một tham chiếu, hãy tìm API công khai tương ứng và sửa mã sử dụng. Ví dụ, một số trường hợp dùng **sun.misc.Unsafe** có thể được chuyển sang **VarHandle**, **java.util.concurrent** hoặc API công khai khác; lựa chọn cụ thể phụ thuộc vào mục đích của đoạn mã.

Không nên xem việc jdeps không báo lỗi là bằng chứng tuyệt đối rằng ứng dụng không dùng API nội bộ. Những tham chiếu được tạo động hoặc ẩn trong cấu hình có thể nằm ngoài khả năng phân tích tĩnh.

### Bước 5: Phát hiện phụ thuộc bị thiếu

Chạy:

~~~bash
jdeps --missing-deps build/libs/app.jar
~~~

Nếu một class được tham chiếu nhưng không tìm thấy trong artifact, classpath hoặc module path đã cung cấp, jdeps có thể báo phụ thuộc bị thiếu. Khi đó, hãy kiểm tra xem thư viện có bị thiếu khỏi lệnh phân tích hay không, hoặc ứng dụng có thực sự đang tham chiếu đến một class không còn tồn tại hay không.

Có thể dùng **--ignore-missing-deps** để cho phép quá trình phân tích tiếp tục khi một số phụ thuộc không được phân giải:

~~~bash
jdeps --ignore-missing-deps --print-module-deps build/libs/app.jar
~~~

Tùy chọn này chỉ bỏ qua tình trạng thiếu trong quá trình phân tích; nó **không** tìm, tải hoặc bổ sung thư viện bị thiếu. Không nên dùng nó để che khuất lỗi phân giải khi cần xác nhận danh sách module chính xác.

## 4. Cung cấp đúng classpath và module path

Kết quả chỉ có ý nghĩa khi jdeps có thể phân giải các thư viện mà ứng dụng tham chiếu.

### Ứng dụng hoặc thư viện trên classpath

Dùng **--class-path** để cung cấp các JAR phụ thuộc:

~~~bash
jdeps --class-path "lib/*" --summary build/libs/app.jar
~~~

Dấu phân cách nhiều đường dẫn phụ thuộc hệ điều hành: Windows dùng dấu chấm phẩy (**;**), còn Linux và macOS dùng dấu hai chấm (**:**). Cú pháp wildcard và cách đặt dấu nháy cũng phụ thuộc shell đang dùng.

Khi thiếu thư viện trên classpath, jdeps có thể báo class không tìm thấy hoặc không thể suy ra đầy đủ phụ thuộc. Hãy thêm đúng các thư viện mà ứng dụng cần vào classpath phân tích.

### Ứng dụng dùng named module

Dùng **--module-path** để chỉ định nơi chứa các module có tên. Có thể yêu cầu phân tích một module cụ thể bằng **--module**:

~~~bash
jdeps --module-path mods --module com.example.app
~~~

Module path giúp jdeps phân giải module descriptor và các phụ thuộc module. Hãy chắc chắn thư mục được chỉ định chứa đúng các module cần thiết cho phiên bản ứng dụng đang phân tích.

Classpath và module path có vai trò khác nhau: thư viện trên classpath thuộc unnamed module, trong khi thư viện trên module path có thể được nhận diện như named module nếu có module descriptor phù hợp. Không nên chuyển một thư viện từ nơi này sang nơi kia chỉ để làm biến mất cảnh báo; cần hiểu cách ứng dụng thực sự được khởi chạy và phân giải class.

### Phân tích JAR đa phiên bản

Một multi-release JAR có thể chứa các class khác nhau cho từng phiên bản Java. Dùng **--multi-release** để yêu cầu jdeps phân tích phần class dành cho phiên bản mục tiêu:

~~~bash
jdeps --multi-release 17 --print-module-deps build/libs/app-mr.jar
~~~

Chọn đúng phiên bản Java mà ứng dụng sẽ chạy. Nếu phân tích phần class của phiên bản khác, danh sách phụ thuộc có thể không phản ánh đúng runtime mục tiêu.

## 5. Đọc và diễn giải kết quả

Khi xem kết quả, cần phân biệt ba cấp độ thông tin:

- **Artifact → module:** summary cho biết JAR hoặc thư mục đang tham chiếu đến module nào.
- **Package → package:** chế độ verbose theo package cho biết khu vực mã nào tạo ra liên kết phụ thuộc.
- **Class → class:** chế độ verbose theo class giúp truy ra điểm tham chiếu cụ thể để sửa hoặc kiểm tra.

Một dòng như **app.jar -> java.sql** có nghĩa là jdeps tìm thấy tham chiếu từ bytecode trong **app.jar** đến API thuộc module **java.sql**. Nó không có nghĩa mọi class trong module **java.sql** đều được ứng dụng sử dụng.

Danh sách module cũng không phải danh sách toàn bộ thư viện bên thứ ba. Phụ thuộc ngoài JDK có thể được biểu diễn bằng JAR hoặc module riêng và cần được cung cấp qua classpath hay module path để phân tích đầy đủ.

Nếu dùng chế độ recursive, jdeps có thể tiếp tục theo các phụ thuộc được phân giải để mở rộng phạm vi phân tích. Kết quả khi đó có thể bao gồm module mà thư viện phụ thuộc cần, không chỉ những module mà bytecode ứng dụng tham chiếu trực tiếp. Hãy chọn phạm vi phù hợp với câu hỏi đang cần trả lời.

## 6. Dùng kết quả để tạo runtime image với jlink

Một mục đích phổ biến của **--print-module-deps** là xác định các module JDK cần đưa vào runtime image.

Trước tiên, lấy danh sách:

~~~bash
jdeps --print-module-deps build/libs/app.jar
~~~

Giả sử kết quả minh họa là:

~~~text
java.base,java.logging,java.sql
~~~

Có thể dùng danh sách đó trong lệnh **jlink**:

~~~bash
jlink --add-modules java.base,java.logging,java.sql --output runtime-image
~~~

Trong dự án thực tế, hãy thay danh sách minh họa bằng kết quả của chính artifact. Với ứng dụng không modular chạy trên classpath, JAR ứng dụng vẫn cần được phân phối và đặt trên classpath khi khởi chạy; **jlink** tạo runtime image từ các module JDK chứ không tự đóng gói JAR ứng dụng theo cách đó.

Trước khi phát hành, hãy chạy ứng dụng bằng runtime image mới và thực hiện các luồng chức năng quan trọng. Nếu một chức năng tải class động hoặc chỉ chạy trong một cấu hình đặc biệt, module cần thiết có thể không xuất hiện trong kết quả phân tích tĩnh ban đầu.

## 7. Hỗ trợ chuyển JAR sang module

Với JAR chưa có **module-info.java**, jdeps có thể tạo bản nháp module descriptor bằng **--generate-module-info**:

~~~bash
jdeps --generate-module-info generated-modules build/libs/library.jar
~~~

Công cụ tạo cấu trúc **module-info.java** ban đầu dựa trên các phụ thuộc phát hiện được. Đây là điểm khởi đầu để chuyển đổi thư viện, không phải descriptor đã được thiết kế và xác nhận hoàn chỉnh.

Sau khi tạo bản nháp, cần xem lại tên module, các khai báo **requires**, **exports** và những yêu cầu đóng gói của thư viện. Phân biệt package cần công khai với package chỉ dùng nội bộ. Nếu thư viện cần hỗ trợ cả classpath và module path, hãy kiểm tra hành vi tương thích theo cách thư viện được phân phối và sử dụng.

## 8. Những giới hạn cần nhớ

jdeps rất hữu ích để lập bản đồ phụ thuộc bytecode, nhưng không thay thế việc kiểm thử ứng dụng:

1. **Phân tích tĩnh không thấy mọi hành vi lúc chạy.** Những class được nạp bằng reflection, tên class lấy từ chuỗi cấu hình, plugin, classloader tùy chỉnh hoặc mã được sinh trong lúc chạy có thể không được phát hiện đầy đủ.
2. **Không chứng minh một phụ thuộc có được thực thi hay không.** Một tham chiếu trong bytecode có thể thuộc nhánh hiếm khi chạy; ngược lại, một phụ thuộc chỉ xuất hiện ở cấu hình triển khai khác có thể không có trong artifact đang phân tích.
3. **Thiếu thư viện làm kết quả thiếu chính xác.** Cần cung cấp đầy đủ classpath và module path. Cảnh báo không tìm thấy class cần được điều tra trước khi kết luận.
4. **Kết quả phụ thuộc phiên bản JDK và artifact.** Hãy phân tích đúng JAR, đúng multi-release version và đúng JDK mục tiêu.
5. **Danh sách module không thay thế kiểm thử runtime.** Những tính năng tải động, service, cấu hình môi trường và đường chạy tùy chọn cần được xác minh bằng kiểm thử thực tế.

## 9. Quy trình thực hành đề xuất

Khi kiểm tra một ứng dụng trước khi phát hành hoặc chuyển sang JPMS, có thể thực hiện theo thứ tự sau:

1. Chọn JAR hoặc thư mục class của bản build cần phát hành.
2. Chạy **jdeps --summary** để có bức tranh tổng quan.
3. Chạy **jdeps --verbose:package** hoặc **--verbose:class** khi cần truy nguồn một phụ thuộc.
4. Chạy **jdeps --list-deps** hoặc **--print-module-deps** để lấy các module JDK được phát hiện.
5. Chạy **jdeps --jdk-internals** để tìm việc sử dụng API nội bộ.
6. Chạy **jdeps --missing-deps** và bổ sung đúng classpath/module path nếu có phụ thuộc chưa phân giải.
7. Nếu tạo runtime image, dùng danh sách module làm đầu vào cho **jlink**, sau đó kiểm thử ứng dụng trên image.
8. Lưu lại lệnh, phiên bản JDK, artifact và kết quả để có thể lặp lại phân tích trong CI.

Có thể đưa các lệnh này vào pipeline sau bước đóng gói JAR. Khi đó, mỗi bản build đều được kiểm tra phụ thuộc trên cùng loại artifact mà người dùng sẽ nhận. Đặc biệt, có thể đặt bước kiểm tra **--jdk-internals** thành điều kiện cảnh báo hoặc chặn build tùy theo chính sách tương thích của dự án.

## 10. Ghi nhớ

- **--summary**: xem nhanh phụ thuộc.
- **--verbose:package / --verbose:class**: tìm package hoặc class tạo ra phụ thuộc.
- **--list-deps / --print-module-deps**: liệt kê module JDK cần thiết.
- **--jdk-internals**: phát hiện tham chiếu đến API nội bộ của JDK.
- **--missing-deps**: tìm class phụ thuộc chưa được phân giải.
- **--class-path / --module-path**: cung cấp đúng nơi chứa thư viện.
- **--multi-release**: chọn phần class của phiên bản Java trong multi-release JAR.

Hãy dùng jdeps để hiểu và thu hẹp đồ thị phụ thuộc, sau đó xác nhận bằng build và kiểm thử runtime. Cách kết hợp này giúp phát hiện sớm phụ thuộc JDK không mong muốn, chuẩn bị khai báo module và tạo runtime image gọn hơn mà vẫn giữ được hành vi của ứng dụng.
