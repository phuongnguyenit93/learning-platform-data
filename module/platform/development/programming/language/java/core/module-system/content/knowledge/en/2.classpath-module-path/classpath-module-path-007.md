# Vì sao cùng một JAR có thể có hành vi khác theo vị trí đặt

Một JAR chỉ là gói chứa class, resource và metadata. Bản thân file JAR không quyết định cách Java áp dụng quy tắc module. Khi khởi chạy, vị trí đưa JAR vào `--class-path` hay `--module-path` quyết định nó được nạp như một phần của unnamed module, một explicit module hay một automatic module. Vì vậy, cùng một file có thể chạy được ở chế độ này nhưng phát sinh lỗi truy cập hoặc phân giải phụ thuộc ở chế độ kia.

## 1. Đặt JAR trên classpath

Classpath được truyền bằng `-cp` hoặc `--class-path`. Class loader tìm class và resource trong các thư mục/JAR đã liệt kê. Các class được nạp từ classpath thuộc unnamed module gắn với class loader tương ứng.

Nếu JAR có `module-info.class`, Java bỏ qua descriptor đó khi JAR nằm trên classpath. Các khai báo `requires`, `exports`, `opens`, `uses` và `provides` không được dùng để áp dụng ranh giới module cho JAR này. Mã ứng dụng vẫn chịu các quy tắc truy cập Java thông thường như `public`, `protected`, package-private và `private`, nhưng không bị giới hạn bởi `exports` của module descriptor.

Nếu JAR không có `module-info.class`, kết quả cũng là các class thuộc unnamed module. Vì vậy, hai JAR có cấu trúc module khác nhau vẫn có thể hoạt động tương tự khi cả hai được đưa lên classpath: descriptor module không tham gia vào quá trình phân giải.

## 2. Đặt JAR trên module path

Module path được truyền bằng `--module-path` hoặc `-p`. Java tìm module, đọc descriptor và xây dựng cấu hình module trước khi chạy ứng dụng.

Có hai trường hợp:

- **Explicit module:** JAR có `module-info.class`. Tên module và các quan hệ phụ thuộc được khai báo trong descriptor. Một module chỉ đọc các module mà nó khai báo bằng `requires`; mã bên ngoài chỉ truy cập được các package được `exports`. Truy cập reflection sâu còn phụ thuộc vào `opens` hoặc `open module`.
- **Automatic module:** JAR không có `module-info.class`. Java tạo một module có tên từ thuộc tính `Automatic-Module-Name` trong manifest nếu có; nếu không, tên được suy ra từ tên file JAR. Automatic module đọc các module khác và export tất cả package, giúp thư viện cũ tham gia module path trong giai đoạn chuyển đổi.

Automatic module có tên module và tham gia vào module resolution, dù chưa có descriptor do tác giả thư viện khai báo. Nó là cầu nối tương thích, không cung cấp mức đóng gói chặt như explicit module.

## 3. Cùng một JAR được hiểu khác nhau như thế nào?

| Nội dung của JAR | Khi đặt trên classpath | Khi đặt trên module path |
|---|---|---|
| Có `module-info.class` | Descriptor bị bỏ qua; class thuộc unnamed module | Là explicit module; descriptor được áp dụng |
| Không có `module-info.class` | Class thuộc unnamed module | Là automatic module; tên được suy ra hoặc lấy từ manifest |
| Có `Automatic-Module-Name` | Thuộc tính này không tạo module trên classpath | Thuộc tính được dùng làm tên automatic module |
| Có package không export | Package vẫn có thể được dùng theo access modifier Java thông thường | Module khác không thể truy cập package đó qua ranh giới module |
| Có package cần reflection sâu | Không có ranh giới module của JAR để chặn reflection | Cần package được mở bằng `opens` hoặc cơ chế mở phù hợp |

Điểm khác biệt lớn nhất là module identity và ranh giới truy cập. Một class public nằm trong package không export có thể được ứng dụng classpath sử dụng, nhưng ứng dụng thuộc named module sẽ không truy cập được package đó nếu module chứa nó không export package. Tương tự, thư viện dùng reflection sâu có thể hoạt động trên classpath nhưng gặp `InaccessibleObjectException` khi chạy dưới explicit module chưa mở package tương ứng.

## 4. Các khác biệt dễ xuất hiện trong ứng dụng

### Readability và dependency

Unnamed module đọc các module khác. Ngược lại, named module không tự động đọc unnamed module. Vì thế, một ứng dụng đã chuyển sang module path có thể không nhìn thấy thư viện chỉ được đặt trên classpath, dù thư viện đó vẫn có mặt trong lệnh chạy. Hãy kiểm tra module khai báo `requires` và vị trí thực tế của từng dependency.

### Export và reflection

`exports` cho phép module khác truy cập các kiểu public trong package được export. `opens` cho phép framework hoặc thư viện reflection truy cập sâu vào package theo phạm vi được khai báo. Hai directive này có mục đích khác nhau: export phục vụ truy cập kiểu ở mức Java; open phục vụ reflection.

### Service loading và resource scanning

Ứng dụng classpath thường khai báo provider của `ServiceLoader` qua file `META-INF/services/<tên-interface>`. Ứng dụng modular có thể khai báo `uses` và `provides ... with ...` trong `module-info.java`. Khi chuyển JAR giữa hai vị trí, hãy kiểm tra cách thư viện đăng ký và tìm provider.

Một số framework quét class dựa trên classpath hoặc thuộc tính `java.class.path`. Khi thư viện chuyển sang module path, cách quét đó có thể không nhìn thấy mọi JAR/resource như trước. Kết quả phụ thuộc vào framework và cách nó hỗ trợ module path.

### Trùng package

Classpath có thể nhận class từ nhiều JAR cùng đóng góp vào một package. Trong module path, việc hai named module cùng chứa một package có thể gây lỗi split package khi dựng cấu hình module. Vì vậy, một cách đóng gói từng chạy được trên classpath có thể thất bại sau khi tách thành nhiều named module.

## 5. Ví dụ khởi chạy

Giả sử `lib.jar` là thư viện có module descriptor:

```java
module com.example.lib {
    exports com.example.lib.api;
}
```

Ứng dụng modular khai báo:

```java
module com.example.app {
    requires com.example.lib;
}
```

Khi chạy trên classpath, descriptor của cả hai JAR bị bỏ qua. Ví dụ trên Windows:

```shell
java -cp "app.jar;lib.jar" com.example.app.Main
```

Khi chạy như ứng dụng modular, đặt hai JAR trong thư mục `mods` và khởi chạy module:

```shell
java --module-path mods --module com.example.app/com.example.app.Main
```

Ở lệnh thứ hai, Java phân giải `com.example.app`, đọc `requires com.example.lib` và chỉ cho phép ứng dụng truy cập các package mà thư viện export. Nếu `lib.jar` không export package chứa một kiểu mà ứng dụng sử dụng, quá trình biên dịch hoặc chạy sẽ báo lỗi truy cập module.

Với JAR cũ không có `module-info.class`, đặt nó trên module path sẽ biến nó thành automatic module. Ứng dụng named module phải dùng đúng tên automatic module trong `requires`; nên khai báo `Automatic-Module-Name` trong manifest để tên không thay đổi khi tên file JAR thay đổi.

## 6. Cách xác định JAR đang được dùng theo chế độ nào

Có thể dùng các lệnh sau để kiểm tra artifact và quá trình phân giải module:

```shell
# Xem descriptor hoặc tên automatic module của JAR
jar --describe-module --file lib.jar

# Hiển thị module được phân giải khi khởi chạy ứng dụng modular
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
```

Khi một ứng dụng chạy khác giữa IDE, Gradle/Maven và dòng lệnh, hãy so sánh lệnh Java thực tế của từng môi trường. Kiểm tra `-cp`, `--class-path`, `--module-path`, module descriptor, dependency graph và các tham số mở module. Cấu hình trong file build chưa đủ để kết luận JVM đang nhận JAR theo chế độ nào; lệnh chạy cuối cùng mới cho biết điều đó.

## 7. Quy tắc lựa chọn

- Dùng classpath khi duy trì ứng dụng legacy và chưa cần ranh giới module.
- Dùng module path với explicit module khi muốn khai báo dependency rõ ràng, kiểm soát package được export và giới hạn reflection.
- Dùng automatic module như bước chuyển tiếp cho thư viện cũ; ưu tiên tên ổn định bằng `Automatic-Module-Name`, sau đó bổ sung `module-info.java` khi thư viện sẵn sàng.
- Không đưa cùng một artifact vào cả classpath lẫn module path trong cùng ứng dụng nếu không có lý do rõ ràng; việc nạp trùng có thể tạo ra class identity và dependency khó dự đoán.
- Khi chuyển một ứng dụng từ classpath sang module path, kiểm tra lại `requires`, `exports`, `opens`, service provider, resource scanning và split package.

Java Platform Module System có từ Java 9. Vì vậy, khi điều tra hành vi khác nhau, hãy xác định JDK đang chạy và vị trí thật của JAR trước khi sửa mã nguồn.