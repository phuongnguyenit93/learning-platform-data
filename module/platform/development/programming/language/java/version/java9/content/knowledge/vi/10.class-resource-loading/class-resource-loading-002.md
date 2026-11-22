# Lấy platform class loader bằng API được hỗ trợ

Từ Java 9, ứng dụng có thể lấy **platform class loader** trực tiếp bằng API công khai:

~~~java
ClassLoader platformLoader = ClassLoader.getPlatformClassLoader();
~~~

Đây là cách được hỗ trợ để lấy class loader cha của system/application class loader trong cấu hình launcher tiêu chuẩn. Platform class loader chịu trách nhiệm nạp các lớp thuộc nền tảng Java mà bootstrap class loader không nạp. Nó cho phép mã tùy chỉnh phân biệt rõ lớp thuộc nền tảng với lớp của ứng dụng.

Hãy dùng kiểu trừu tượng `ClassLoader` và các phương thức công khai của nó. Không cần truy cập class nội bộ của JDK, phản chiếu vào implementation hoặc suy đoán tên class loader cụ thể.

## 1. Vị trí của platform class loader trong hệ thống

Trong cấu hình Java launcher thông thường, thứ tự cha-con của các built-in class loader là:

~~~text
Bootstrap class loader
        |
        v
Platform class loader
        |
        v
System (application) class loader
        |
        v
Các class loader do ứng dụng tạo
~~~

Mỗi loader có phạm vi tìm kiếm và vai trò riêng:

- **Bootstrap class loader** nạp các lớp nền tảng cốt lõi, chẳng hạn `java.lang.String`. Trong API Java, bootstrap loader được biểu diễn bằng `null` khi gọi `Class.getClassLoader()` hoặc `ClassLoader.getParent()`.
- **Platform class loader** nạp các lớp thuộc nền tảng Java mà bootstrap loader không nạp. Ví dụ trong JDK tiêu chuẩn, `java.sql.Driver` thuộc module `java.sql` và được platform loader định nghĩa.
- **System class loader** thường được gọi là application class loader. Nó nạp các lớp ứng dụng từ classpath và các mô-đun ứng dụng theo cấu hình launcher.
- **Custom class loader** được ứng dụng tạo để nạp plugin, mã động hoặc các lớp từ nguồn riêng. Nó thường nhận một parent loader để xác định nơi tìm lớp khi delegation.

Platform loader là parent của system loader trong cấu hình tiêu chuẩn. Platform loader có parent là bootstrap loader, nhưng `getParent()` trả về `null` vì bootstrap loader không phải đối tượng `ClassLoader` có thể tham chiếu trực tiếp.

## 2. API công khai để lấy platform class loader

Phương thức cần dùng:

~~~java
ClassLoader platformLoader = ClassLoader.getPlatformClassLoader();
~~~

Một số phương thức liên quan:

| API | Ý nghĩa |
|---|---|
| `ClassLoader.getPlatformClassLoader()` | Trả về platform class loader |
| `ClassLoader.getSystemClassLoader()` | Trả về system/application class loader |
| `platformLoader.getParent()` | Trả về parent của platform loader; trong cấu hình tiêu chuẩn là `null` (bootstrap) |
| `systemLoader.getParent()` | Trả về parent của system loader; trong cấu hình tiêu chuẩn là platform loader |
| `SomeClass.class.getClassLoader()` | Cho biết loader đã định nghĩa class đó; kết quả `null` biểu thị bootstrap loader |

`ClassLoader.getPlatformClassLoader()` được bổ sung từ Java 9. Vì vậy, khi biên dịch mã sử dụng API này, phiên bản Java mục tiêu tối thiểu phải là Java 9. Ví dụ dưới đây dùng Java 17 trở lên để phù hợp với môi trường Java hiện hành.

Không phụ thuộc vào lớp triển khai cụ thể của platform loader. JDK có thể thay đổi implementation giữa các phiên bản; hợp đồng ổn định mà ứng dụng nên dùng là kiểu `ClassLoader` và các phương thức API được công bố.

## 3. Ví dụ: lấy và kiểm tra các class loader

Tạo tệp `PlatformLoaderDemo.java`:

~~~java
public final class PlatformLoaderDemo {

    private PlatformLoaderDemo() {
    }

    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println(
                "system-parent-is-platform=" + (system.getParent() == platform)
        );

        System.out.println(
                "platform-parent-is-bootstrap=" + (platform.getParent() == null)
        );

        System.out.println(
                "String-loader-is-bootstrap=" + (String.class.getClassLoader() == null)
        );

        Class<?> driver = platform.loadClass("java.sql.Driver");

        System.out.println("Driver-module=" + driver.getModule().getName());

        System.out.println(
                "Driver-loader-is-platform=" + (driver.getClassLoader() == platform)
        );

        System.out.println(
                "Demo-loader-is-system="
                        + (PlatformLoaderDemo.class.getClassLoader() == system)
        );
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~powershell
javac --release 17 -d out PlatformLoaderDemo.java
java -cp out PlatformLoaderDemo
~~~

Stdout trên JDK tiêu chuẩn:

~~~text
system-parent-is-platform=true
platform-parent-is-bootstrap=true
String-loader-is-bootstrap=true
Driver-module=java.sql
Driver-loader-is-platform=true
Demo-loader-is-system=true
~~~

Giải thích kết quả:

1. System loader có parent là platform loader.
2. Parent của platform loader là bootstrap loader, được biểu diễn bằng `null`.
3. `String` được bootstrap loader định nghĩa.
4. `java.sql.Driver` thuộc module `java.sql`.
5. Trong cấu hình JDK được kiểm tra, platform loader định nghĩa `java.sql.Driver`.
6. Class demo nằm trên classpath nên được system/application loader định nghĩa.

Các phép so sánh object loader có ý nghĩa hơn việc in tên class triển khai nội bộ. Tên implementation có thể thay đổi theo JDK hoặc môi trường chạy.

## 4. Phân biệt platform loader với system loader

Hai loader này không thể dùng thay thế nhau:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

- Dùng **platform loader** khi cần tham chiếu tới phạm vi lớp của nền tảng Java.
- Dùng **system loader** khi cần tham chiếu tới phạm vi lớp ứng dụng được launcher cấu hình.
- Nếu cần nạp một class ứng dụng từ classpath, thông thường dùng system loader.
- Nếu cần nạp một class thuộc platform module, có thể dùng platform loader.

Ví dụ:

~~~java
Class<?> platformClass =
        ClassLoader.getPlatformClassLoader().loadClass("java.sql.Driver");

Class<?> applicationClass =
        ClassLoader.getSystemClassLoader().loadClass("com.example.app.Main");
~~~

Lời gọi thứ hai chỉ thành công khi class `com.example.app.Main` thực sự có mặt trong phạm vi tìm kiếm của system loader. Tên class phải là tên đầy đủ gồm package.

Không nên dùng platform loader để nạp class nghiệp vụ của ứng dụng. Platform loader là parent của system loader, nên nó không tìm ngược xuống các class do system loader định nghĩa.

## 5. Dùng platform loader làm parent cho custom class loader

Một ứng dụng có thể tạo class loader riêng và chỉ định platform loader làm parent:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();

URLClassLoader pluginLoader = new URLClassLoader(
        pluginUrls,
        platform
);
~~~

Ví dụ này dùng `URLClassLoader` để nạp lớp từ các URL của plugin. `pluginUrls` là mảng URL trỏ đến JAR hoặc thư mục chứa lớp plugin.

Khi dùng platform loader làm parent:

- Plugin loader có thể delegation lên platform loader để tìm các lớp nền tảng Java.
- Plugin loader không tự động nhìn thấy mọi class chỉ có trong application classpath thông qua system loader.
- Các API chia sẻ giữa ứng dụng và plugin cần được bố trí rõ ràng, ví dụ đưa vào một thư viện/module mà cả hai bên đều có thể đọc hoặc thiết kế một parent loader chung phù hợp.
- Nên đóng `URLClassLoader` khi không còn sử dụng để giải phóng các tài nguyên JAR đang mở.

Nếu plugin cần dùng trực tiếp API do ứng dụng cung cấp, chọn parent là system loader hoặc một loader chuyên chứa API chia sẻ có thể phù hợp hơn. Quyết định phụ thuộc vào ranh giới cách ly mong muốn và dependency của plugin.

## 6. Quan hệ giữa class loader và JPMS module

Trong JPMS, một class được gắn với một module và được định nghĩa bởi một class loader. Có thể kiểm tra hai thông tin này:

~~~java
Class<?> type = java.sql.Driver.class;

Module module = type.getModule();
ClassLoader loader = type.getClassLoader();

System.out.println("module=" + module.getName());
System.out.println("platform-loaded="
        + (loader == ClassLoader.getPlatformClassLoader()));
~~~

Kết quả trên JDK tiêu chuẩn:

~~~text
module=java.sql
platform-loaded=true
~~~

Module name và class loader là hai thuộc tính khác nhau:

- Module name xác định module mà class thuộc về.
- Class loader xác định loader đã định nghĩa class.
- Nhiều module có thể được định nghĩa bởi cùng một loader.
- Một class loader có thể định nghĩa các lớp thuộc nhiều module khác nhau theo cấu hình runtime.

Không suy ra module name từ tên class loader hoặc suy ra loader từ tên module. Dùng `Class.getModule()` và `Class.getClassLoader()` để kiểm tra trực tiếp.

## 7. Xử lý lỗi và lưu ý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Compiler không nhận diện `getPlatformClassLoader()` | Source/release target thấp hơn Java 9 hoặc compiler quá cũ | Dùng JDK hỗ trợ API và đặt release target từ 9 trở lên |
| `loadClass` ném `ClassNotFoundException` | Class không thuộc phạm vi tìm kiếm của loader đang dùng hoặc module chưa được cung cấp/phân giải | Xác định module/class cần nạp và dùng đúng loader cùng module path |
| Platform loader không tìm thấy class ứng dụng | Class ứng dụng thuộc phạm vi system loader hoặc custom loader | Dùng system loader hoặc loader sở hữu class ứng dụng |
| `getParent()` trả về `null` | Parent là bootstrap loader | Đây là cách API biểu diễn bootstrap loader, không phải lỗi |
| Class được nạp nhưng module không như mong đợi | Nhầm class loader với module hoặc dùng class từ dependency khác | Kiểm tra đồng thời `getClassLoader()` và `getModule()` |
| Plugin không nhìn thấy API của ứng dụng | Plugin loader có parent là platform loader, không có đường delegation tới system/application API | Đưa API chia sẻ vào parent phù hợp hoặc cấu hình dependency của plugin rõ ràng |

Một class có thể tồn tại trong module path nhưng chưa được phân giải hoặc không thuộc phạm vi của loader đang gọi. Khi debug, hãy kiểm tra tên class đầy đủ, module configuration và class loader thực tế thay vì chỉ kiểm tra file JAR có tồn tại.

## 8. Checklist sử dụng

- Lấy platform loader bằng `ClassLoader.getPlatformClassLoader()`.
- Dùng API từ Java 9 trở lên; ưu tiên Java 17+ cho ví dụ và ứng dụng mới.
- Dùng `ClassLoader.getSystemClassLoader()` cho phạm vi class ứng dụng theo launcher.
- Hiểu `null` từ `getParent()` hoặc `getClassLoader()` có thể biểu thị bootstrap loader.
- Không phụ thuộc vào tên hoặc kiểu implementation nội bộ của JDK.
- Không dùng platform loader để nạp class nghiệp vụ chỉ có trong application classpath.
- Khi tạo custom loader, chọn parent theo dependency và ranh giới cách ly thực tế.
- Kiểm tra cả module bằng `getModule()` và loader bằng `getClassLoader()` khi chẩn đoán.
- Dùng `loadClass` với tên đầy đủ và xử lý `ClassNotFoundException`.

`ClassLoader.getPlatformClassLoader()` là API công khai, trực tiếp và ổn định để lấy platform class loader. Kết hợp nó với `getSystemClassLoader()`, `getParent()`, `getClassLoader()` và `getModule()` giúp ứng dụng xác định đúng phạm vi nạp lớp trong môi trường Java modular mà không cần phụ thuộc vào chi tiết nội bộ của JDK.
