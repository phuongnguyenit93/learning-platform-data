# requires module JDK và runtime image

## 1. Vai trò của requires trong Java Module System

Trong Java Platform Module System (JPMS), mỗi named module mô tả các phụ thuộc trực tiếp của nó trong file **module-info.java**. Chỉ thị **requires** khai báo rằng module hiện tại cần đọc một module khác để biên dịch và chạy.

Ví dụ, một ứng dụng dùng JDBC và Java Logging có thể khai báo:

~~~java
module com.example.app {
    requires java.sql;
    requires java.logging;

    exports com.example.app.api;
}
~~~

Ở đây, module **com.example.app** phụ thuộc vào hai module JDK là **java.sql** và **java.logging**. Khi biên dịch hoặc khởi chạy ứng dụng theo module path, hệ thống module phải phân giải được các module được yêu cầu cùng những phụ thuộc bắt buộc của chúng.

**requires** tạo quan hệ readability giữa các module. Nhờ quan hệ này, mã trong module hiện tại có thể truy cập các kiểu được module phụ thuộc xuất ra bằng **exports**, đồng thời tuân theo quy tắc đóng gói và truy cập của JPMS.

Cần phân biệt ba khái niệm:

- **requires** khai báo phụ thuộc module và khả năng đọc module đó.
- **exports** công khai một package để module khác có thể truy cập các kiểu public trong package.
- **opens** cho phép truy cập phản chiếu sâu vào package, thường phục vụ framework hoặc thư viện cần reflection.

Một module có thể đọc module khác nhưng không tự động truy cập được mọi package bên trong module đó. Package phải được xuất hoặc mở phù hợp với cách truy cập.

## 2. Khai báo phụ thuộc vào module JDK

JDK được tổ chức thành nhiều module có tên. Một số module thường gặp:

| Module | Chức năng tiêu biểu |
|---|---|
| **java.base** | Các kiểu nền tảng như Object, String, collections, I/O cơ bản và concurrency |
| **java.logging** | API logging chuẩn của Java |
| **java.sql** | JDBC API |
| **java.xml** | XML, DOM, SAX và các API XML liên quan |
| **java.net.http** | HTTP Client API |
| **java.desktop** | AWT, Swing và một số API desktop |
| **java.naming** | JNDI |
| **java.management** | JMX và API quản lý JVM |

Có thể xem các module có sẵn trong JDK đang sử dụng bằng:

~~~bash
java --list-modules
~~~

Để xem nội dung và các khai báo của một module:

~~~bash
java --describe-module java.sql
~~~

Module **java.base** được hệ thống module đọc ngầm bởi mọi named module. Vì vậy, thông thường không cần viết **requires java.base** trong module descriptor.

Ví dụ, nếu ứng dụng gọi JDBC, có thể khai báo **requires java.sql**. Nếu ứng dụng dùng HTTP Client chuẩn, khai báo **requires java.net.http**. Hãy khai báo theo API mà mã của module thực sự sử dụng, không thêm hàng loạt module JDK chỉ vì chúng có mặt trong một bản JDK đầy đủ.

Một module JDK có thể phụ thuộc vào module JDK khác. Khi hệ thống phân giải module graph, các phụ thuộc bắt buộc sẽ được đưa vào đồ thị. Do đó, runtime image cuối cùng có thể chứa nhiều module hơn các dòng **requires** được viết trực tiếp trong ứng dụng.

## 3. Ba dạng requires cần phân biệt

### requires thông thường

Đây là dạng phổ biến nhất:

~~~java
module com.example.report {
    requires java.sql;
}
~~~

Module **java.sql** phải có mặt và được phân giải khi biên dịch cũng như khi chạy module graph. Dùng dạng này khi mã cần API của module phụ thuộc trong hoạt động thông thường.

### requires transitive

Dùng **requires transitive** khi module hiện tại công khai API có kiểu thuộc module phụ thuộc, và các module đọc API của bạn cũng cần đọc module đó.

~~~java
module com.example.data.api {
    requires transitive java.sql;

    exports com.example.data.api;
}
~~~

Giả sử một phương thức public của **com.example.data.api** trả về **java.sql.Connection**. Module tiêu thụ API này cần đọc **java.sql** để sử dụng kiểu trong chữ ký phương thức. Khai báo transitive truyền khả năng đọc module phụ thuộc đến các module đọc module hiện tại.

Không nên dùng transitive cho mọi phụ thuộc. Nếu module chỉ dùng một thư viện bên trong implementation và không để kiểu của thư viện đó xuất hiện trong API công khai, **requires** thông thường thường phù hợp hơn. Khai báo transitive rộng quá mức làm tăng các phụ thuộc mà người dùng module phải đọc.

### requires static

Dùng **requires static** khi module cần một phụ thuộc lúc biên dịch nhưng phụ thuộc đó là tùy chọn trong quá trình phân giải runtime:

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

Một trường hợp thường gặp là thư viện annotation chỉ cần trong quá trình biên dịch hoặc xử lý công cụ. Module được yêu cầu vẫn phải có mặt trên module path khi biên dịch. Ở runtime, module có thể không được cài đặt mà module hiện tại vẫn phân giải được.

Tuy nhiên, nếu ứng dụng thực sự gọi class hoặc method của module tùy chọn khi chạy, việc bỏ module đó khỏi runtime có thể dẫn đến lỗi khi đường chạy tương ứng được thực thi. **requires static** không tự tải thư viện và cũng không làm cho việc sử dụng API runtime trở nên an toàn khi thiếu module.

Có thể ghi nhớ:

| Cú pháp | Ý nghĩa chính |
|---|---|
| **requires M** | Phụ thuộc bắt buộc khi biên dịch và khi phân giải runtime |
| **requires transitive M** | Phụ thuộc bắt buộc, đồng thời truyền readability đến module đọc module hiện tại |
| **requires static M** | Bắt buộc khi biên dịch, tùy chọn khi phân giải runtime |

## 4. Chọn phụ thuộc đúng cho module ứng dụng

Trước khi tạo runtime image, hãy xác định module nào thực sự thuộc đồ thị ứng dụng.

Ví dụ một ứng dụng có các package sau:

~~~text
com.example.app
com.example.app.api
com.example.app.db
com.example.app.internal
~~~

Ứng dụng dùng JDBC để truy cập cơ sở dữ liệu, ghi log và công khai một API không để kiểu JDBC xuất hiện trong chữ ký public. Descriptor có thể là:

~~~java
module com.example.app {
    requires java.sql;
    requires java.logging;

    exports com.example.app.api;
}
~~~

Nếu API public của ứng dụng trả về kiểu **java.sql.Connection** hoặc nhận kiểu này làm tham số, hãy cân nhắc **requires transitive java.sql** để các module tiêu thụ API đọc được kiểu đó. Nếu JDBC chỉ được dùng bên trong implementation, giữ **requires java.sql** thông thường.

Các package không được **exports** vẫn có thể được sử dụng bên trong module. Đây là cách giữ implementation nội bộ và giảm bề mặt API công khai.

Nếu framework cần reflection sâu vào package nội bộ, cân nhắc **opens** hoặc **opens ... to** cho đúng module framework. Không thêm **opens** chỉ để giải quyết một lỗi readability do thiếu **requires**; hai chỉ thị xử lý hai khía cạnh khác nhau.

## 5. Từ module descriptor đến module graph

Khi biên dịch hoặc khởi chạy named module, JPMS xây dựng module graph từ các module gốc và những phụ thuộc được khai báo. Các module phải được tìm thấy trên module path hoặc trong các module của runtime đang sử dụng.

Ví dụ, một module ứng dụng yêu cầu **java.sql**. Module **java.sql** lại có những phụ thuộc riêng. Hệ thống phân giải tiếp tục theo các quan hệ bắt buộc để tạo đồ thị nhất quán.

Có thể xem descriptor của module JDK để hiểu các phụ thuộc đó:

~~~bash
java --describe-module java.sql
~~~

Các phụ thuộc được hệ thống module đưa vào graph không đồng nghĩa ứng dụng phải viết tất cả chúng trong **module-info.java**. Mỗi module chỉ nên khai báo phụ thuộc trực tiếp mà mã hoặc API của chính nó cần.

Đối với module service, cần phân biệt khai báo **uses** và **provides** với **requires**:

~~~java
module com.example.app {
    uses com.example.spi.PaymentProvider;
}
~~~

**uses** khai báo module sử dụng một service; **provides ... with ...** khai báo module cung cấp implementation. Nếu muốn runtime image chứa các provider được phát hiện trên module path, có thể dùng tùy chọn **--bind-services** của jlink ở bước tạo image.

## 6. Chuẩn bị module để tạo runtime image

Công cụ **jlink** tạo một runtime image tùy chỉnh từ các module. Image bao gồm runtime Java và những module được chọn cùng phụ thuộc cần thiết. Việc tạo image thường có ý nghĩa khi ứng dụng đã được tổ chức thành named module.

Một cấu trúc dự án minh họa:

~~~text
project/
  src/
    com.example.app/
      module-info.java
      com/example/app/Main.java
      com/example/app/api/
    com.example.data/
      module-info.java
      com/example/data/
  mods/
~~~

Ví dụ **module-info.java** của ứng dụng:

~~~java
module com.example.app {
    requires java.sql;
    requires java.logging;
}
~~~

Ví dụ class khởi chạy:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Biên dịch module ứng dụng:

~~~bash
javac -d mods --module-source-path src -m com.example.app
~~~

Sau khi biên dịch, thư mục **mods** chứa các module đã biên dịch. Nếu ứng dụng phụ thuộc vào module thư viện riêng, các module đó cũng phải được biên dịch hoặc đặt trên module path để jlink phân giải được.

Có thể kiểm tra module đã biên dịch bằng:

~~~bash
java --module-path mods --list-modules
~~~

Lệnh này cho biết những module quan sát được trên module path kết hợp với runtime hiện tại. Nó giúp xác nhận tên module và vị trí module trước khi tạo image.

## 7. Tạo runtime image bằng jlink

Một lệnh cơ bản trên Linux hoặc macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output runtime-image
~~~

Trong đó:

- **--module-path** chỉ định nơi jlink tìm module. Thư mục **$JAVA_HOME/jmods** chứa các module của JDK; **mods** chứa module ứng dụng đã biên dịch.
- **--add-modules** chỉ định module gốc cần đưa vào image. jlink sẽ phân giải các phụ thuộc bắt buộc của module gốc.
- **--output** là thư mục runtime image được tạo ra.

Trên Windows, dấu phân cách các phần tử module path là dấu chấm phẩy. Ví dụ trong PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime-image
~~~

Thay **com.example.app** bằng tên module thực tế. Nếu ứng dụng phụ thuộc vào các module ứng dụng khác, jlink sẽ phân giải chúng khi chúng có mặt trên module path và được khai báo đúng.

Không cần liệt kê từng module JDK phụ thuộc một cách thủ công nếu module graph đã được khai báo chính xác. Tuy vậy, có thể chỉ định nhiều module gốc bằng danh sách phân tách dấu phẩy khi image cần chứa thêm module độc lập:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.app,java.xml \
      --output runtime-image
~~~

Chỉ thêm **java.xml** nếu ứng dụng hoặc yêu cầu triển khai thực sự cần module đó.

## 8. Tạo launcher và tối ưu runtime image

Có thể yêu cầu jlink tạo launcher cho module và class main:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --launcher app=com.example.app/com.example.app.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime-image
~~~

Sau khi tạo image, launcher có thể được gọi bằng:

~~~bash
./runtime-image/bin/app
~~~

Nếu không tạo launcher riêng, có thể chạy module bằng Java executable nằm trong image:

~~~bash
./runtime-image/bin/java -m com.example.app/com.example.app.Main
~~~

Một số tùy chọn thường dùng:

- **--strip-debug** loại bỏ thông tin debug khỏi runtime image.
- **--no-header-files** bỏ các header native.
- **--no-man-pages** bỏ trang hướng dẫn.
- **--compress=2** bật mức nén tài nguyên trong image trên các JDK hỗ trợ tùy chọn này.
- **--bind-services** liên kết các service provider phù hợp và các module phụ thuộc của chúng.
- **--launcher** tạo lệnh khởi chạy tiện dụng cho module và main class đã chỉ định.

Tùy chọn tối ưu làm thay đổi nội dung hoặc kích thước image. Hãy kiểm tra danh sách tùy chọn bằng **jlink --help** trên đúng phiên bản JDK đang dùng. Với ứng dụng dựa vào ServiceLoader, hãy kiểm tra service provider được đưa vào image và cân nhắc **--bind-services**.

## 9. Kiểm tra runtime image sau khi tạo

Sau khi jlink hoàn tất, không nên xem việc tạo thư mục thành công là bằng chứng ứng dụng đã sẵn sàng. Hãy chạy ứng dụng bằng chính runtime image:

~~~bash
./runtime-image/bin/app
~~~

Hoặc nếu không tạo launcher:

~~~bash
./runtime-image/bin/java -m com.example.app/com.example.app.Main
~~~

Có thể liệt kê các module có trong image:

~~~bash
./runtime-image/bin/java --list-modules
~~~

Nên kiểm tra ít nhất:

1. Ứng dụng khởi động được bằng Java executable trong image.
2. Các chức năng truy cập database, logging, XML, HTTP hoặc desktop hoạt động đúng nếu ứng dụng sử dụng chúng.
3. Các service provider được tìm thấy nếu ứng dụng dùng ServiceLoader.
4. Các class được nạp qua reflection hoặc cấu hình động hoạt động đúng.
5. Tệp cấu hình, tài nguyên, native library và dữ liệu bên ngoài được phân phối cùng ứng dụng.
6. Kết quả chạy trên môi trường triển khai mục tiêu tương thích với môi trường đã tạo image.

Runtime image được tạo cho nền tảng hệ điều hành và kiến trúc tương ứng. Thông thường, hãy tạo và kiểm thử image trên từng nền tảng đích bằng JDK phù hợp.

## 10. Trường hợp ứng dụng chưa modular

Nếu ứng dụng vẫn chạy trên classpath và chưa có **module-info.java**, jlink không thể biến các JAR classpath tùy ý thành named module chỉ bằng cách đưa chúng vào **--add-modules**.

Có hai hướng phổ biến:

- Chuyển ứng dụng và các thư viện phù hợp sang named module, bổ sung module descriptor và đặt chúng trên module path.
- Tạo runtime image chỉ chứa các module JDK cần thiết, sau đó phân phối JAR ứng dụng riêng và khởi chạy bằng classpath của image.

Ví dụ cho hướng thứ hai, sau khi tạo image với các module JDK cần thiết, có thể chạy:

~~~bash
runtime-image/bin/java -cp "lib/*:app.jar" com.example.app.Main
~~~

Trên Windows, classpath dùng dấu chấm phẩy thay cho dấu hai chấm. Cách này vẫn cho phép dùng runtime image gọn hơn, nhưng ứng dụng và các JAR classpath vẫn phải được phân phối riêng.

Nếu muốn jlink đưa chính module ứng dụng vào image, module đó cần có dạng module phù hợp trên module path. Các automatic module thường dùng để tương thích module path không phải đầu vào thay thế cho named module khi tạo image bằng jlink; cần kiểm tra yêu cầu module của JDK đang dùng.

## 11. Các lỗi thường gặp

**Module not found**

Tên module được yêu cầu không tìm thấy trên module path. Kiểm tra tên trong **module-info.java**, vị trí thư mục **mods**, module path và JDK được dùng để chạy lệnh.

**Module does not read ...**

Module hiện tại chưa khai báo quan hệ readability phù hợp. Kiểm tra **requires** trong descriptor của module gọi API. Nếu kiểu của module phụ thuộc xuất hiện trong API công khai, cân nhắc **requires transitive**.

**Package is not visible**

Module có thể đã được đọc nhưng package cần dùng chưa được module sở hữu xuất ra. Kiểm tra **exports** của module đó. Nếu lỗi đến từ reflection sâu, kiểm tra chính sách **opens** và cấu hình truy cập phản chiếu.

**jlink không phân giải được module ứng dụng**

Kiểm tra module path có chứa module đã biên dịch, module descriptor có tên đúng và tất cả phụ thuộc bắt buộc đều có thể phân giải. Dùng **java --describe-module** hoặc **java --module-path ... --list-modules** để hỗ trợ chẩn đoán.

**Ứng dụng chạy trên JDK đầy đủ nhưng lỗi trong image**

Image có thể thiếu module được tải động, service provider, tài nguyên, native library hoặc thành phần runtime chỉ dùng trong một cấu hình. Kiểm tra luồng thực thi thực tế, khai báo service và các module gốc truyền cho jlink. Có thể thêm module cần thiết vào **--add-modules**, rồi tạo lại và kiểm thử image.

## 12. Quy trình thực hành đề xuất

Khi chuyển một ứng dụng sang runtime image tối giản, hãy đi theo thứ tự:

1. Xác định module ứng dụng và các module thư viện cần thiết.
2. Viết **module-info.java** với các khai báo **requires** trực tiếp phù hợp.
3. Dùng **requires transitive** chỉ khi API công khai cần truyền readability đến module phụ thuộc.
4. Dùng **requires static** cho phụ thuộc tùy chọn ở runtime nhưng cần có khi biên dịch.
5. Kiểm tra module graph bằng công cụ của JDK và bảo đảm các module đều phân giải được.
6. Biên dịch module ứng dụng và thư viện trên module path.
7. Dùng **jlink --add-modules** để tạo image từ module gốc của ứng dụng.
8. Thêm launcher hoặc các tùy chọn tối ưu khi có nhu cầu.
9. Chạy và kiểm thử các chức năng thực tế bằng runtime image.
10. Tạo image riêng cho từng nền tảng triển khai và lưu lại JDK, lệnh build cùng danh sách module đã chọn.

## 13. Ghi nhớ

- **requires** khai báo module mà mã hiện tại cần đọc.
- **requires transitive** truyền readability của phụ thuộc tới module tiêu thụ API.
- **requires static** bắt buộc khi biên dịch nhưng có thể vắng mặt khi phân giải runtime.
- **java.base** được mọi named module đọc ngầm.
- **exports** điều khiển package nào được module khác truy cập; **opens** phục vụ truy cập phản chiếu sâu.
- **jlink** tạo runtime image từ các module đã phân giải, bắt đầu từ những module được chọn qua **--add-modules**.
- Module graph và runtime image phải được xác nhận bằng cách chạy ứng dụng trên image đã tạo.

Một module descriptor chính xác giúp JPMS xây dựng đồ thị phụ thuộc rõ ràng. jlink dùng đồ thị đó để chọn các module cần thiết cho runtime image. Khi kiểm thử image trên đúng môi trường triển khai, ứng dụng có thể chạy với một runtime Java nhỏ hơn mà vẫn giữ đủ các thành phần mà chức năng thực tế yêu cầu.
