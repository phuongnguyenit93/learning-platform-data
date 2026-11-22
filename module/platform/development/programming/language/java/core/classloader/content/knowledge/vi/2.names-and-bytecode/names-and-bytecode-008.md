# Vì sao trình nạp phải nhận đúng tên và bytecode tương ứng?

Khi JVM yêu cầu nạp một lớp có tên `com.example.Order`, bộ nạp lớp (*class loader*) phải cung cấp bytecode thực sự mô tả **`com.example.Order`**. Một tệp có đuôi `.class` hợp lệ chưa đủ: bytecode bên trong có **tên lớp được khai báo trong cấu trúc class file**. Nếu tên JVM đang yêu cầu và tên nằm trong bytecode không khớp, lớp không thể được định nghĩa dưới tên đó.

Quy tắc này bảo vệ tính nhất quán của danh tính lớp, các liên kết kiểu dữ liệu, lời gọi phương thức và quá trình tải động. Nó đặc biệt quan trọng khi viết `ClassLoader` tùy biến, đọc bytecode từ JAR, thư mục, mạng, cơ sở dữ liệu hoặc sau bước biến đổi bytecode.

## 1. Ba khái niệm tên cần phân biệt

Giả sử mã Java:

~~~java
package com.example;

public class Order {
}
~~~

| Khái niệm | Giá trị tương ứng | Ý nghĩa |
| --- | --- | --- |
| *Binary name* (tên nhị phân) | `com.example.Order` | Tên mà các API như `ClassLoader.loadClass(String)` và `defineClass(String, …)` sử dụng cho lớp thông thường. |
| *Internal name* (tên nội bộ JVM) | `com/example/Order` | Dạng dấu gạch chéo xuất hiện trong thông tin `this_class` của class file. |
| Đường dẫn tài nguyên thông dụng | `com/example/Order.class` | Vị trí thường dùng để tìm bytecode theo quy ước thư mục/JAR; đường dẫn không tự quyết định tên lớp bên trong. |

Trong class file, trường `this_class` trỏ đến một mục `CONSTANT_Class_info` trong constant pool, từ đó lấy tên nội bộ của chính lớp đang được định nghĩa. JVM có thể đổi dạng tên nội bộ `com/example/Order` thành binary name `com.example.Order` để đối chiếu với yêu cầu.

**Điểm mấu chốt:** đổi tên tệp `Another.class` thành `Order.class` hoặc di chuyển tệp sang đúng thư mục *không sửa* `this_class`. Bytecode vẫn mô tả tên cũ. Tên lớp cũng phân biệt chữ hoa/chữ thường: `Order` khác `order`.

Các lớp lồng nhau có binary name dạng `com.example.Outer$Inner` (nếu đó là tên do trình biên dịch tạo ra). Không tự thay `$` bằng `.` trong tên truyền cho `loadClass`.

## 2. Từ tên được yêu cầu đến bytecode

Luồng khái quát đối với **lớp có tên thông thường**:

~~~text
Yêu cầu nạp "com.example.Order"
             |
             v
ClassLoader.loadClass("com.example.Order")
             |
             +--> Lớp đã được nạp? / parent delegation có tìm thấy?
             |                   |
             |                   +--> Có: trả về Class đã tìm được
             |
             v
findClass("com.example.Order") của loader tùy biến
             |
             v
Tìm/đọc đúng nguồn bytecode và kiểm tra khả năng đọc
             |
             v
defineClass("com.example.Order", bytes, 0, bytes.length)
             |
             +--> Bytecode không hợp lệ/phiên bản không hỗ trợ: lỗi tương ứng
             +--> this_class mô tả tên khác: NoClassDefFoundError
             |
             v
Class<?> đại diện cho lớp được định nghĩa
~~~

Sơ đồ giản lược: `loadClass` thường kiểm tra lớp đã nạp và ủy quyền cho loader cha trước khi gọi `findClass`; một triển khai tùy biến có thể thay đổi chính sách này. Do đó, **không phải mọi lần gọi `loadClass` đều dẫn đến `defineClass`**, nhất là khi lớp đã được parent loader tìm thấy.

Một triển khai `findClass` phổ biến sẽ chuyển binary name sang đường dẫn tài nguyên:

~~~java
String resourcePath = binaryName.replace('.', '/') + ".class";
~~~

Phép chuyển đổi đó giúp **tìm đúng tài nguyên**, nhưng nó không xác nhận danh tính bytecode. Bước định nghĩa lớp vẫn phải đối chiếu tên yêu cầu với dữ liệu class file.

Với `defineClass(String name, byte[] b, int off, int len)`, tham số `name` là **binary name được kỳ vọng**. Theo hợp đồng API, nếu `name` khác `null` mà không khớp tên được mã hóa trong bytecode, JVM ném `NoClassDefFoundError`. JVM cũng kiểm tra class file có cấu trúc và phiên bản hợp lệ.

## 3. Vì sao JVM phải kiểm tra đúng tên?

### 3.1. Giữ danh tính kiểu nhất quán

Một lớp runtime không được nhận diện chỉ bằng nội dung tệp hay tên đơn lẻ. Với lớp thông thường, danh tính kiểu phụ thuộc vào **binary name và defining class loader**. Hai loader khác nhau có thể định nghĩa hai lớp đều tên `com.example.Order`, nhưng chúng là hai kiểu khác nhau trong JVM.

Ngược lại, trong *cùng một lần định nghĩa lớp*, nếu JVM cho phép yêu cầu tên `com.example.Order` nhưng chấp nhận bytecode khai báo `com.example.Customer`, cùng một đối tượng `Class` sẽ có hai cách gọi tên trái ngược nhau. Những nơi giữ tên hoặc liên kết lớp sẽ mất tính nhất quán.

### 3.2. Giữ các tham chiếu kiểu và liên kết chính xác

Bytecode có thể chứa tham chiếu biểu tượng tới superclass, interface, field, method và các kiểu khác theo tên. Quá trình *linking/resolution* dựa vào các tham chiếu và ngữ cảnh class loader để tìm chính xác kiểu được nói đến. Nếu có thể gán tùy ý tên cho một class file khác, mã dùng tên `com.example.Order` có nguy cơ liên kết tới cấu trúc hoàn toàn khác mong đợi.

So khớp tên giúp phát hiện sớm việc nạp nhầm lớp; nó không đảm bảo toàn bộ bytecode đều hợp lệ. JVM còn thực hiện các kiểm tra định dạng, quyền truy cập, ràng buộc tải lớp và xác minh bytecode tại các giai đoạn phù hợp.

### 3.3. Phát hiện sớm lỗi đóng gói và biến đổi bytecode

Sai tên thường là dấu hiệu của một thao tác bị lỗi: copy/đổi tên tệp `.class`, đóng gói sai JAR, áp dụng quy tắc *relocation/shading* nhưng không cập nhật bytecode, hoặc ánh xạ tên sang tài nguyên không đúng. Thay vì chạy một lớp khác dưới tên đang yêu cầu, JVM báo lỗi ngay khi định nghĩa.

Đây là kiểm tra **tính nhất quán**, không phải phép xác thực chữ ký số hay bằng chứng rằng bytecode an toàn. Quyền truy cập, nguồn mã và kiểm tra bảo mật khác là trách nhiệm riêng.

## 4. Ví dụ Java chạy được: cùng bytecode, tên đúng và tên sai

Lưu toàn bộ đoạn sau vào **`NameMismatchDemo.java`**. Lớp `Actual` không có `package` nên binary name của nó là `Actual`.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class NameMismatchDemo {
    static final class ByteArrayLoader extends ClassLoader {
        Class<?> define(String binaryName, byte[] bytes) {
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] bytecode = Files.readAllBytes(Path.of("Actual.class"));

        try {
            new ByteArrayLoader().define("Expected", bytecode);
            System.out.println("Khong phat hien loi");
        } catch (NoClassDefFoundError e) {
            System.out.println("Sai ten: " + e.getClass().getSimpleName());
        }

        Class<?> clazz = new ByteArrayLoader().define("Actual", bytecode);
        System.out.println("Ten dung: " + clazz.getName());
    }
}

class Actual {}
~~~

Mở terminal **ngay tại thư mục chứa tệp nguồn**, sử dụng JDK 17 trở lên:

~~~bash
javac NameMismatchDemo.java
java NameMismatchDemo
~~~

Kết quả tiêu chuẩn:

~~~text
Sai ten: NoClassDefFoundError
Ten dung: Actual
~~~

Lý giải từng phần:

1. `javac` tạo `NameMismatchDemo.class` và `Actual.class`. Tệp thứ hai có `this_class` ứng với tên `Actual`.
2. Lần gọi `define("Expected", bytecode)` chủ động yêu cầu tên `Expected` trong khi bytecode tự khai báo `Actual`. `defineClass` phát hiện không khớp và ném `NoClassDefFoundError`. Chương trình chỉ in **tên loại lỗi** vì thông báo chi tiết có thể khác giữa các JVM.
3. Lần gọi `define("Actual", bytecode)` sử dụng đúng tên nên tạo lớp thành công và in `Actual`.
4. Hai đối tượng `ByteArrayLoader` độc lập giúp ví dụ tách biệt hai lần định nghĩa. Mã cố ý gọi trực tiếp `defineClass` qua một phương thức của lớp con để kiểm tra chính hợp đồng giữa tên và bytecode; nó không mô phỏng toàn bộ thuật toán ủy quyền của `loadClass`.

**Lưu ý khi dùng thực tế:** `defineClass` là phương thức `protected final`. Ứng dụng thông thường không gọi trực tiếp từ bên ngoài; code tùy biến đặt lời gọi trong lớp kế thừa `ClassLoader`, thường ở `findClass`. Việc tạo hai lớp có cùng binary name bởi hai defining loader khác nhau vốn được JVM cho phép, nhưng đối tượng của hai kiểu đó không tự động ép kiểu qua lại.

## 5. Phân biệt lỗi tên với các lỗi tải lớp khác

| Tình huống | Kết quả thường gặp | Ý nghĩa |
| --- | --- | --- |
| Không tìm được lớp theo tên trong cơ chế tra cứu của `loadClass` | `ClassNotFoundException` | Loader không cung cấp được lớp được yêu cầu; đây là checked exception thường xuất hiện từ `loadClass`/`Class.forName`. |
| Có class file hợp lệ nhưng `this_class` không khớp `name` được truyền vào `defineClass` | `NoClassDefFoundError` | Bytecode mô tả **một lớp khác** tên mà JVM đang định nghĩa. |
| Bytecode không theo cấu trúc class file hợp lệ | `ClassFormatError` | Vấn đề định dạng nội dung, chưa chắc là sai tên. |
| Class file được biên dịch theo phiên bản JVM mà runtime không hỗ trợ | `UnsupportedClassVersionError` | Phiên bản bytecode không tương thích; thuộc họ `ClassFormatError`. |
| Lớp đã được định nghĩa không vượt qua quy tắc xác minh | `VerifyError` | Vấn đề ràng buộc kiểu/luồng bytecode trong quá trình xác minh, không đồng nghĩa sai tên. |
| Cố định nghĩa lại cùng binary name trong cùng defining loader | `LinkageError` | Trùng định nghĩa hoặc vi phạm ràng buộc tải lớp; khác với việc có hai loader riêng biệt. |

`NoClassDefFoundError` còn có các nguyên nhân khác, ví dụ khi một phụ thuộc đã có lúc biên dịch nhưng không thể tìm/nạp khi runtime. Vì vậy **không thể kết luận chỉ từ tên exception rằng `this_class` sai**; phải xem thông điệp, stack trace và đường đi nạp lớp.

## 6. Áp dụng khi tự viết ClassLoader

Một loader tùy biến cần duy trì các bất biến sau:

1. **Giữ nguyên binary name đang được yêu cầu.** Trong `findClass(String name)`, dùng `name` làm đầu vào định tuyến tới JAR, thư mục hoặc nguồn bytecode. Chuyển dấu chấm thành dấu gạch chéo chỉ khi tạo đường dẫn tài nguyên thông thường.
2. **Lấy đúng bytes của tệp class, đọc trọn dữ liệu.** Không gán tên yêu cầu dựa riêng trên tên file hoặc kết quả tìm kiếm gần đúng. Bytecode không có nghĩa là một đoạn source Java hoặc một chuỗi text UTF-8.
3. **Truyền đúng tên vào `defineClass(name, bytes, 0, bytes.length)`.** API cho phép truyền `null` khi không biết tên; tuy nhiên truyền binary name mong đợi tạo kiểm tra danh tính rõ ràng và là cách nên dùng cho loader dựa trên tên.
4. **Giữ cơ chế ủy quyền và phạm vi loader có chủ đích.** Nếu parent đã nạp một lớp, `loadClass` thông thường trả về lớp đó. Nếu thiết kế child-first, phải hiểu rằng cùng binary name dưới defining loader khác tạo ra một kiểu runtime riêng.
5. **Phân biệt lỗi tra cứu với lỗi định nghĩa.** Khi nguồn không chứa tên yêu cầu, `findClass` nên báo `ClassNotFoundException`; khi `defineClass` nhận bytecode không phù hợp, không nên che mất `LinkageError` thành thông báo “không tìm thấy file”.
6. **Quan sát đủ ngữ cảnh để chẩn đoán.** Khi lỗi, ghi nhận binary name được yêu cầu, nguồn tài nguyên/JAR, defining loader dự kiến và nguyên nhân gốc. Không cần ghi toàn bộ bytecode vào log.

### Hai lỗi thực tế dễ mắc

**Đổi tên file mà không sửa nội dung class file.** Một tệp chứa `com/vendor/OldName` được chép thành `com/app/NewName.class`. Loader tìm ra tài nguyên qua đường dẫn mới, nhưng `defineClass("com.app.NewName", bytes, …)` vẫn thất bại. Cần build/rewrite bytecode hợp lệ để cập nhật tên thực sự, chứ không chỉ đổi tên tệp.

**Lấy sai entry từ JAR.** Loader đang xử lý `com.example.Order` nhưng lỡ đọc entry `com/example/Customer.class`. Việc cả hai entry tồn tại và đều là class file hợp lệ không giúp sửa lỗi: `this_class` trong entry được đọc vẫn là `com/example/Customer`. Kiểm tra ánh xạ binary name → resource path → class-file content.

## 7. Những điều cần nhớ và tự kiểm tra

- **Yêu cầu một tên thì phải định nghĩa đúng lớp mang tên ấy:** `name` tại `defineClass` phải khớp binary name được mô tả bởi `this_class` khi `name` khác `null`.
- **Đường dẫn không phải danh tính:** tên file hoặc thư mục chỉ là cách lưu trữ/tra cứu; cấu trúc class file chứa thông tin danh tính thực sự.
- **Tên đúng vẫn chưa đủ:** bytecode còn phải đúng định dạng, phiên bản, quy tắc xác minh và các ràng buộc liên kết khác.
- **Tên cộng defining loader tạo danh tính runtime:** cùng tên dưới hai loader có thể biểu thị hai kiểu khác nhau; khi ủy quyền thành công, loader con có thể trả về lớp do loader cha định nghĩa.

Thử suy luận: loader nhận `loadClass("com.example.Invoice")`, tìm được tài nguyên `com/example/Invoice.class`, nhưng trường `this_class` trỏ đến `com/example/Receipt`. Có thể định nghĩa `Invoice` bằng bytecode này không? **Không.** Đường dẫn khớp nhưng tên bên trong bytecode sai; nếu gọi `defineClass("com.example.Invoice", …)` thì nhận `NoClassDefFoundError`. Sửa dữ liệu hoặc ánh xạ tới đúng bytecode; không đổi tên yêu cầu để “lách” hợp đồng với caller.

## Tài liệu chuẩn để đọc thêm

- [Java SE 21 – `ClassLoader.defineClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): hợp đồng `name`, `null`, các lỗi định nghĩa và ràng buộc gói.
- [JVM Specification, §5.3 và §5.3.5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): định danh lớp theo loader và nguyên tắc tạo lớp từ class file.
- [JVM Specification, §4.1 – The `ClassFile` Structure](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): trường `this_class` và cách class file biểu diễn tên.