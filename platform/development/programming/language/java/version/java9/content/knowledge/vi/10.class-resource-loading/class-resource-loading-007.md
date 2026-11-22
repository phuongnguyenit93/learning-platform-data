# Tài nguyên trong runtime image và URI jrt

## 1. Runtime image trong JPMS

Từ Java 9, JDK sử dụng một runtime image dạng mô-đun. Các module nền tảng và tài nguyên đi kèm được tổ chức trong image thay vì bố trí theo mô hình thư viện runtime đơn lẻ như các JDK cũ.

Runtime image chứa nhiều loại nội dung:

- Class của các module nền tảng, ví dụ **java.base**.
- Tài nguyên đi kèm module như file cấu hình, metadata, properties và dữ liệu cần thiết cho runtime.
- Các module JDK được đưa vào bản phân phối hoặc custom runtime image.
- Những tài nguyên và class được giữ lại khi tạo runtime image rút gọn bằng **jlink**.

Trong JDK hiện đại, không nên tìm class nền tảng bằng cách dò một file **rt.jar**. Cấu trúc runtime image được truy cập bằng các công cụ và cơ chế dành cho mô hình mô-đun.

Java cung cấp filesystem provider với URI scheme **jrt:** để quan sát nội dung runtime image đang được JVM sử dụng. URI gốc của filesystem này là:

~~~text
jrt:/
~~~

Filesystem **jrt** cung cấp một góc nhìn có cấu trúc về module và tài nguyên trong runtime image. Nó hữu ích cho công cụ phát triển, kiểm tra JDK, chẩn đoán môi trường và các tác vụ cần xác định tài nguyên nào hiện diện trong runtime.

## 2. Cấu trúc đường dẫn trong jrt filesystem

Trong jrt filesystem, nội dung module được tổ chức dưới thư mục **/modules**. Mỗi module có một thư mục riêng:

~~~text
/modules/<module-name>/<resource-path>
~~~

Ví dụ:

~~~text
/modules/java.base/java/lang/Object.class
/modules/java.base/java/lang/String.class
~~~

Đường dẫn đầu tiên trỏ tới bytecode của **java.lang.Object** trong module **java.base**. Đường dẫn thứ hai trỏ tới bytecode của **java.lang.String**.

Một đường dẫn jrt có ba phần cần nhận biết:

1. **jrt:/** là URI gốc xác định filesystem provider.
2. **modules/** là thư mục chứa nội dung được phân theo module.
3. Phần tiếp theo là tên module và đường dẫn tương đối của tài nguyên bên trong module đó.

Tên module là tên JPMS, chẳng hạn **java.base**, **java.logging** hoặc **java.sql**. Tên này không phải tên package và cũng không phải tên file JAR.

JRT filesystem cũng cung cấp góc nhìn theo package qua cấu trúc **/packages**. Khi cần xác định tài nguyên cụ thể, đường dẫn dưới **/modules** thường trực tiếp và dễ hiểu hơn vì nó chỉ rõ module sở hữu nội dung.

## 3. URI jrt khác URI file và jar

Các URI scheme đại diện cho những loại tài nguyên khác nhau:

| URI scheme | Dùng cho |
|---|---|
| **file:** | File hoặc thư mục trên filesystem của hệ điều hành. |
| **jar:** | Nội dung bên trong một JAR, thường có dạng jar:file:/path/library.jar!/. |
| **jrt:** | Nội dung trong runtime image của JDK đang chạy. |

Ví dụ, **jrt:/modules/java.base/java/lang/Object.class** biểu diễn tài nguyên trong runtime image. Nó không phải đường dẫn file thông thường trên ổ đĩa và cũng không phải entry trong một JAR.

URI **jrt:/** không trỏ tới runtime image tùy ý trên máy. Nó đại diện cho runtime image gắn với JDK/runtime đang chạy JVM hiện tại. Nếu cần kiểm tra một runtime image khác, có thể dùng công cụ **jimage** với image đó thay vì giả định jrt filesystem hiện tại sẽ chuyển sang image khác.

Cần phân biệt URI với Path:

- **URI** xác định tài nguyên bằng scheme và đường dẫn.
- **FileSystem** cung cấp cách truy cập tài nguyên theo một scheme.
- **Path** là đường dẫn bên trong một filesystem cụ thể.
- **Files** thực hiện các thao tác đọc metadata hoặc nội dung trên Path.

Vì vậy, trước khi gọi các thao tác như **Files.exists** hay **Files.newInputStream**, cần có Path thuộc đúng filesystem provider.

## 4. Truy cập jrt filesystem bằng Java NIO

Java NIO cung cấp API để làm việc với filesystem. Với jrt, lấy filesystem hiện có bằng URI gốc:

~~~java
URI jrtUri = URI.create("jrt:/");
FileSystem jrt = FileSystems.getFileSystem(jrtUri);
~~~

Sau đó tạo Path cho tài nguyên cần kiểm tra:

~~~java
Path objectClass = jrt.getPath(
    "/modules/java.base/java/lang/Object.class"
);
~~~

Có thể dùng **Files** để kiểm tra sự tồn tại, loại file hoặc đọc nội dung:

~~~java
boolean exists = Files.exists(objectClass);
boolean regularFile = Files.isRegularFile(objectClass);
~~~

Các API thường dùng:

| API | Công dụng |
|---|---|
| **FileSystems.getFileSystem(URI)** | Lấy filesystem đã được đăng ký cho URI scheme. |
| **FileSystem.getPath(String)** | Tạo Path trong filesystem đó. |
| **Files.exists(Path)** | Kiểm tra đường dẫn có tồn tại hay không. |
| **Files.isRegularFile(Path)** | Kiểm tra đường dẫn có trỏ tới file thông thường hay không. |
| **Files.size(Path)** | Lấy kích thước file tính theo byte. |
| **Files.newInputStream(Path)** | Mở luồng đọc nội dung file. |
| **Files.list(Path)** | Liệt kê các entry trực tiếp trong một thư mục. |
| **Path.toUri()** | Lấy URI tương ứng với Path. |

Filesystem trả về từ **FileSystems.getFileSystem** là filesystem dùng chung của provider. Không nên đóng filesystem này sau mỗi lần đọc. Chỉ đóng filesystem do chính chương trình tạo và sở hữu trong trường hợp provider yêu cầu tạo riêng.

## 5. Ví dụ hoàn chỉnh: kiểm tra Object.class trong runtime image

Chương trình sau truy cập bytecode của **java.lang.Object** trong module **java.base**, xác nhận file tồn tại và đọc bốn byte đầu tiên của class file.

File **JrtImageDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;

public class JrtImageDemo {
    public static void main(String[] args) throws IOException {
        URI jrtUri = URI.create("jrt:/");
        FileSystem jrt = FileSystems.getFileSystem(jrtUri);

        Path objectClass = jrt.getPath(
            "/modules/java.base/java/lang/Object.class"
        );

        System.out.println("Path: " + objectClass);
        System.out.println(
            "Regular file: " + Files.isRegularFile(objectClass)
        );

        try (InputStream input = Files.newInputStream(objectClass)) {
            byte[] magic = input.readNBytes(4);

            if (magic.length != 4) {
                throw new IOException("Class file header is incomplete");
            }

            System.out.printf(
                "Class-file magic: %02X %02X %02X %02X%n",
                magic[0] & 0xFF,
                magic[1] & 0xFF,
                magic[2] & 0xFF,
                magic[3] & 0xFF
            );
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 JrtImageDemo.java
java JrtImageDemo
~~~

Kết quả:

~~~text
Path: /modules/java.base/java/lang/Object.class
Regular file: true
Class-file magic: CA FE BA BE
~~~

Bốn byte **CA FE BA BE** là magic number ở đầu một Java class file. Kết quả này xác nhận chương trình đã đọc được bytecode từ tài nguyên nằm trong runtime image.

Ví dụ không cần tự tạo JAR, thêm thư viện bên ngoài hay đưa đường dẫn cài đặt JDK vào mã nguồn. URI **jrt:/** và filesystem provider xác định runtime image đang được JVM sử dụng.

## 6. Liệt kê module và tài nguyên

Có thể liệt kê các module có mặt trong runtime image bằng thư mục **/modules**. Đoạn mã sau tiếp tục sử dụng biến jrt đã lấy ở phần truy cập filesystem:

~~~java
Path modules = jrt.getPath("/modules");

try (var entries = Files.list(modules)) {
    entries
        .filter(Files::isDirectory)
        .sorted()
        .forEach(System.out::println);
}
~~~

Danh sách thu được phụ thuộc bản JDK và cách runtime image được tạo. Một custom runtime image tạo bằng **jlink** có thể chỉ chứa các module cần thiết cho ứng dụng.

Tương tự, có thể liệt kê nội dung của một package:

~~~java
Path javaLang = jrt.getPath("/modules/java.base/java/lang");

try (var entries = Files.list(javaLang)) {
    entries
        .filter(Files::isRegularFile)
        .sorted()
        .limit(10)
        .forEach(path -> System.out.println(path.getFileName()));
}
~~~

Đoạn mã trên chỉ liệt kê các file trực tiếp trong thư mục package, không duyệt đệ quy các thư mục con. Danh sách tên file thay đổi theo phiên bản JDK, vì vậy không nên dùng một danh sách cụ thể làm hợp đồng cho ứng dụng.

Nếu cần duyệt cây thư mục sâu hơn, có thể dùng **Files.walk**. Hãy giới hạn phạm vi duyệt để tránh xử lý quá nhiều entry trong runtime image lớn.

## 7. Đọc nội dung tài nguyên và giới hạn truy cập

JRT filesystem hỗ trợ đọc tài nguyên bằng các API NIO như **Files.newInputStream**. Ví dụ ở phần trước đọc header của một class file mà không cần tải toàn bộ nội dung vào bộ nhớ.

Khi đọc một resource, cần xác định đúng module và đường dẫn tương đối. Không nên giả định mọi module đều có cùng cấu trúc package hoặc có cùng một file tài nguyên.

Một số điểm cần lưu ý:

- **jrt filesystem là read-only.** Không thể sửa, xóa hoặc tạo file trong runtime image thông qua filesystem này.
- **Không phải mọi JDK đều có cùng tập module.** Runtime image được rút gọn bằng jlink có thể không chứa module hoặc resource mà chương trình đang tìm.
- **Không phải mọi đường dẫn đều tồn tại.** Kiểm tra bằng Files.exists hoặc Files.isRegularFile trước khi đọc.
- **Không đọc toàn bộ file lớn nếu chỉ cần metadata.** Dùng Files.size hoặc đọc một phần bằng InputStream khi phù hợp.
- **Đọc được file class không đồng nghĩa với việc package được export.** Việc đọc bytecode từ runtime image không làm thay đổi quy tắc readability, exports hay opens của JPMS.
- **Không phụ thuộc vào class nội bộ của JDK.** Những package không được export là chi tiết triển khai, không phải API ổn định cho ứng dụng.

Nếu cố ghi vào JRT filesystem, thao tác ghi sẽ thất bại vì filesystem chỉ đọc. Hãy dùng API hoặc cơ chế cấu hình được hỗ trợ để quản lý dữ liệu ứng dụng; không sửa trực tiếp runtime image.

## 8. Khi nào nên dùng jrt và khi nào nên dùng API tài nguyên của module?

JRT filesystem thích hợp cho công cụ kiểm tra runtime image, công cụ phân tích JDK, chẩn đoán môi trường và tác vụ cần xác định nội dung của một module trong runtime hiện tại.

Trong mã ứng dụng thông thường, nếu mục tiêu là đọc resource do chính ứng dụng hoặc thư viện cung cấp, hãy dùng API tài nguyên của Java:

~~~java
try (InputStream input =
         JrtImageDemo.class.getResourceAsStream("config.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }

    // Đọc nội dung resource tại đây.
}
~~~

Đường dẫn resource tương đối trong ví dụ được phân giải theo package của class **JrtImageDemo**. Có thể dùng đường dẫn bắt đầu bằng dấu / để phân giải từ gốc resource theo quy tắc của Class.

Với resource thuộc một module khác, cần tuân theo API và quy tắc đóng gói của module đó. **Class.getResourceAsStream**, **ClassLoader.getResourceAsStream** và **Module.getResourceAsStream** phục vụ việc nạp resource ở cấp ứng dụng; jrt filesystem phục vụ việc quan sát runtime image.

Không nên thay việc nạp resource của ứng dụng bằng cách ghép đường dẫn nội bộ dưới **/modules**. Cách làm đó khiến ứng dụng phụ thuộc vào bố cục runtime image và module đang chạy.

## 9. Kiểm tra runtime image bằng công cụ JDK

Ngoài API Java, JDK cung cấp công cụ **jimage** để kiểm tra image file. Công cụ này hữu ích khi cần xem nội dung của một runtime image cụ thể, kể cả image không phải runtime đang chạy.

Ví dụ trên hệ thống có JDK:

~~~bash
jimage list "$JAVA_HOME/lib/modules"
~~~

Lệnh hiển thị các module và entry có trong runtime image tại đường dẫn được cung cấp. Trên Windows, có thể dùng biến môi trường **%JAVA_HOME%** trong Command Prompt hoặc **$env:JAVA_HOME** trong PowerShell để tạo đường dẫn tương ứng.

Phân biệt hai cách:

- **jrt filesystem** cho phép chương trình Java truy cập runtime image hiện tại bằng URI và Path.
- **jimage** là công cụ dòng lệnh để kiểm tra image file được chỉ định.

Khi một resource không xuất hiện qua jrt, có thể kiểm tra image thực tế bằng jimage để xác định module hoặc resource đó có được đóng gói hay không.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| FileSystemNotFoundException với jrt:/ | Runtime hoặc provider hiện tại không cung cấp filesystem tương ứng. Kiểm tra đang chạy bằng JDK/runtime phù hợp và provider có sẵn. |
| NoSuchFileException | Sai tên module hoặc sai đường dẫn resource; module/resource có thể không được đưa vào custom runtime image. |
| Files.exists trả về false | Đường dẫn không tồn tại trong image đang chạy. Kiểm tra module name, package path và nội dung image. |
| Dùng file: để mở đường dẫn jrt | jrt không phải filesystem của hệ điều hành. Lấy FileSystem từ URI jrt:/ rồi tạo Path bên trong filesystem đó. |
| Không ghi được vào jrt | JRT filesystem chỉ đọc. Không dùng Files.write hoặc thao tác sửa/xóa trên runtime image. |
| Không tìm thấy rt.jar | Bố cục runtime image hiện đại không dùng rt.jar theo cách của JDK cũ. Dùng jrt filesystem hoặc jimage để kiểm tra. |
| Resource có trong JDK đầy đủ nhưng thiếu ở môi trường triển khai | Runtime image có thể được tạo bằng jlink và loại bỏ module không cần thiết. Kiểm tra tập module của image được triển khai. |
| Đọc được class file nhưng không import được class | Khả năng đọc file không cấp quyền truy cập API. Kiểm tra requires và exports theo quy tắc JPMS. |

## 11. Quy trình kiểm tra một resource trong runtime image

Khi cần xác minh một class hoặc resource có nằm trong runtime image hay không, có thể thực hiện theo trình tự:

1. Xác định JVM đang chạy và runtime image mà nó sử dụng.
2. Xác định module sở hữu resource, ví dụ **java.base**.
3. Tạo URI gốc bằng **URI.create("jrt:/")**.
4. Lấy filesystem bằng **FileSystems.getFileSystem**.
5. Tạo Path theo cấu trúc **/modules/<module-name>/<resource-path>**.
6. Kiểm tra bằng **Files.exists** hoặc **Files.isRegularFile**.
7. Đọc metadata hoặc nội dung bằng API NIO nếu cần.
8. Nếu resource không có mặt, kiểm tra tập module trong runtime image, đặc biệt khi image được tạo bằng jlink.

Quy trình này tách bạch việc xác định resource, xác định module sở hữu và kiểm tra nội dung thực tế. Nó cũng giúp phân biệt lỗi đường dẫn với trường hợp resource thật sự không được đóng gói.

## 12. Kết luận

Runtime image là cách JDK hiện đại tổ chức các module và tài nguyên cần thiết cho môi trường chạy Java. URI **jrt:/** cung cấp điểm truy cập tới filesystem đại diện cho runtime image hiện tại, còn thư mục **/modules** cho phép xác định tài nguyên theo tên module.

Kết hợp **FileSystems**, **Path** và **Files**, chương trình có thể kiểm tra hoặc đọc tài nguyên trong runtime image mà không cần dựa vào bố cục JAR cũ. Dùng jrt cho công cụ chẩn đoán và kiểm tra runtime; dùng API resource của class hoặc module cho nhu cầu nạp tài nguyên trong ứng dụng. Luôn kiểm tra sự hiện diện của module và resource, đặc biệt với runtime image rút gọn được tạo bằng jlink.
