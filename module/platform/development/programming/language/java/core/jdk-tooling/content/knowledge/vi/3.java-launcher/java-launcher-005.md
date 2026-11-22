# Classpath runtime

**Runtime classpath** là danh sách vị trí mà Java application class loader tìm kiếm các lớp và thư viện khi chương trình đang chạy. Các vị trí này thường là thư mục chứa file `.class`, hoặc tệp JAR/ZIP chứa bytecode. Nếu chương trình tham chiếu đến một lớp bên ngoài JDK mà lớp đó không có trong runtime classpath, ứng dụng có thể biên dịch thành công nhưng vẫn lỗi khi chạy.

Classpath là một phần trong cách Java launcher khởi động ứng dụng. Nó trả lời câu hỏi: **JVM sẽ tìm bytecode của lớp ứng dụng và dependency ở đâu?** Việc hiểu đúng runtime classpath giúp xử lý các lỗi như `ClassNotFoundException`, `NoClassDefFoundError` và tình trạng chạy nhầm phiên bản thư viện.

## 1. Phân biệt compile-time classpath và runtime classpath

Hai giai đoạn cần tìm dependency ở hai thời điểm khác nhau:

- **Compile-time classpath:** được trình biên dịch `javac` sử dụng để tìm các kiểu mà mã nguồn tham chiếu đến. Tùy chọn thường dùng là `-cp` hoặc `--class-path` khi gọi `javac`.
- **Runtime classpath:** được Java launcher/JVM sử dụng khi chạy chương trình để tìm các lớp cần nạp. Tùy chọn thường dùng là `-cp` hoặc `--class-path` khi gọi `java`.

Ví dụ, nếu `Main.java` import lớp `com.example.Greeter`, `javac` cần tìm được lớp đó khi biên dịch. Sau khi tạo ra `Main.class`, bytecode vẫn chứa các tham chiếu đến tên lớp và thành viên mà nó sử dụng; việc biên dịch không tự động nhúng mọi dependency vào file `.class`. Khi chạy, runtime vẫn phải tìm được `Greeter.class` hoặc JAR chứa lớp này.

Vì vậy, một lệnh biên dịch có classpath đúng không bảo đảm lệnh chạy cũng có classpath đúng. Hãy cấu hình dependency ở cả hai giai đoạn, hoặc để Maven/Gradle quản lý compile classpath và runtime classpath theo cấu hình dự án.

## 2. Những gì có thể đặt trên classpath

Một entry trong classpath thường là một trong các loại sau:

1. **Thư mục chứa package đã biên dịch.** Nếu tên lớp là `com.example.app.Main`, thư mục classpath phải là thư mục gốc chứa thư mục con `com/example/app/Main.class`.
2. **Tệp JAR.** JAR là định dạng đóng gói các lớp và tài nguyên Java phổ biến nhất.
3. **Tệp ZIP.** Java launcher cũng có thể tìm lớp trong ZIP có cấu trúc phù hợp.
4. **Wildcard cho các JAR trong một thư mục.** Ví dụ `lib/*` đại diện cho các tệp JAR trong thư mục `lib`; wildcard này không tìm đệ quy trong các thư mục con.

Classpath không phải là danh sách file `.java`. Nó chỉ đến các vị trí chứa lớp đã biên dịch và tài nguyên mà ứng dụng cần ở runtime.

### Thư mục classpath phải là package root

Giả sử file được đặt tại:

```text
build/classes/
└── com/
    └── example/
        └── app/
            └── Main.class
```

Tên lớp đầy đủ là `com.example.app.Main`. Classpath phải chứa `build/classes`, vì từ gốc đó JVM mới ghép được đường dẫn `com/example/app/Main.class`.

Nếu đặt classpath thành `build/classes/com/example/app` rồi vẫn chạy tên `com.example.app.Main`, JVM sẽ tìm sai vị trí. Khi chạy một lớp có package, hãy dùng tên đầy đủ của lớp và trỏ classpath đến thư mục nằm phía trên cây package.

## 3. Truyền runtime classpath cho Java launcher

Dùng `-cp` hoặc tên đầy đủ `--class-path`:

```sh
java --class-path "<cac-entry>" ten.package.Main
```

Hai dạng sau tương đương:

```sh
java -cp "app-classes:lib/greeter.jar" com.example.app.Main
java --class-path "app-classes:lib/greeter.jar" com.example.app.Main
```

Dấu phân cách giữa các entry phụ thuộc hệ điều hành:

| Hệ điều hành | Dấu phân cách | Ví dụ |
|---|---|---|
| Windows | Dấu chấm phẩy `;` | `app-classes;lib/greeter.jar` |
| macOS, Linux và Unix | Dấu hai chấm `:` | `app-classes:lib/greeter.jar` |

Đặt toàn bộ giá trị classpath trong dấu ngoặc kép khi có khoảng trắng hoặc khi dùng wildcard. Điều này giúp shell truyền nguyên một đối số cho Java launcher. Dấu phân cách giữa các entry vẫn là ký tự theo hệ điều hành, không phải dấu phân cách thư mục `/` hoặc `\`.

### Classpath mặc định và biến CLASSPATH

Nếu không truyền `-cp` hoặc `--class-path`, Java launcher sử dụng biến môi trường `CLASSPATH` nếu biến này được thiết lập. Nếu biến đó không được thiết lập, thư mục hiện tại (`.`) là classpath mặc định.

Ví dụ trên macOS/Linux:

```sh
export CLASSPATH="build/classes:lib/greeter.jar"
java com.example.app.Main
```

Trên Windows PowerShell:

```powershell
$env:CLASSPATH = "build\classes;lib\greeter.jar"
java com.example.app.Main
```

Khi đã truyền `-cp` hoặc `--class-path`, giá trị đó được dùng làm classpath của ứng dụng thay cho biến môi trường `CLASSPATH`. Không nên phụ thuộc vào `CLASSPATH` toàn cục trong môi trường phát triển hoặc CI: cấu hình ẩn này dễ khiến chương trình chạy được trên máy này nhưng lỗi trên máy khác. Lệnh chạy nên thể hiện dependency rõ ràng hoặc dùng build tool để dựng runtime classpath.

## 4. Ví dụ chạy ứng dụng có dependency riêng

Ví dụ dưới đây có hai phần: thư viện `Greeter` và ứng dụng `Main` sử dụng thư viện đó.

Cấu trúc thư mục:

```text
classpath-demo/
├── src/
│   ├── library/
│   │   └── com/example/greeting/Greeter.java
│   └── app/
│       └── com/example/app/Main.java
├── build/
└── lib/
```

Tệp `src/library/com/example/greeting/Greeter.java`:

```java
package com.example.greeting;

public class Greeter {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Tệp `src/app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeting.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java"));
    }
}
```

### 4.1. Biên dịch hai phần riêng biệt

Mở Terminal tại thư mục gốc `classpath-demo`. Tạo thư mục output trước khi biên dịch.

macOS/Linux:

```sh
mkdir -p build/library build/app lib
javac -d build/library src/library/com/example/greeting/Greeter.java
javac --class-path build/library -d build/app src/app/com/example/app/Main.java
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force build\library, build\app, lib | Out-Null
javac -d build\library src\library\com\example\greeting\Greeter.java
javac --class-path build\library -d build\app src\app\com\example\app\Main.java
```

Ở lệnh đầu, `javac -d build/library` đặt bytecode của thư viện vào `build/library`. Ở lệnh thứ hai, `--class-path build/library` giúp trình biên dịch tìm được `Greeter` trong lúc biên dịch `Main`; bytecode của ứng dụng được đặt vào `build/app`.

### 4.2. Chạy với hai thư mục classpath

macOS/Linux:

```sh
java --class-path "build/app:build/library" com.example.app.Main
```

Windows PowerShell:

```powershell
java --class-path "build\app;build\library" com.example.app.Main
```

Kết quả trên cả hai hệ điều hành:

```text
Xin chào, Java!
```

Lệnh chạy cần cả hai entry: `build/app` chứa `Main.class`, còn `build/library` chứa `Greeter.class`. Nếu bỏ entry thư viện, ứng dụng có thể báo không tìm thấy `com.example.greeting.Greeter` khi JVM cần nạp lớp đó.

## 5. Đưa thư viện vào JAR và chạy bằng classpath

Thay vì trỏ đến thư mục bytecode, có thể đóng gói thư viện thành JAR:

macOS/Linux:

```sh
jar --create --file lib/greeter.jar -C build/library .
java --class-path "build/app:lib/greeter.jar" com.example.app.Main
```

Windows PowerShell:

```powershell
jar --create --file lib\greeter.jar -C build\library .
java --class-path "build\app;lib\greeter.jar" com.example.app.Main
```

Kết quả vẫn là:

```text
Xin chào, Java!
```

Tùy chọn `-C build/library .` yêu cầu công cụ `jar` chuyển vào thư mục `build/library` rồi đóng gói nội dung bên trong. Nhờ đó, JAR giữ nguyên cấu trúc package, chẳng hạn `com/example/greeting/Greeter.class`.

Classpath có thể chứa đồng thời thư mục và JAR. Ứng dụng không cần biết thư viện được lưu dưới dạng thư mục bytecode hay tệp JAR, miễn là entry classpath trỏ đúng vị trí và chứa đúng cấu trúc lớp.

## 6. Runtime dependency trong manifest của executable JAR

Có thể đóng gói lớp ứng dụng vào một JAR và khai báo điểm vào cùng thư viện phụ thuộc trong manifest. Cách này hữu ích khi muốn khởi chạy bằng `java -jar`.

Tạo tệp `manifest.mf` tại thư mục gốc:

```text
Main-Class: com.example.app.Main
Class-Path: lib/greeter.jar

```

Dòng trống cuối manifest là cần thiết để kết thúc phần khai báo. Thuộc tính:

- `Main-Class`: tên đầy đủ của lớp có phương thức `public static void main(String[] args)`.
- `Class-Path`: các URL của thư viện hoặc vị trí bổ sung mà JAR cần. Các mục được phân cách bằng khoảng trắng; đường dẫn tương đối được phân giải tương đối với vị trí của JAR chứa manifest.

Đóng gói ứng dụng:

```sh
jar --create --file app.jar --manifest manifest.mf -C build/app .
```

Cấu trúc kết quả:

```text
classpath-demo/
├── app.jar
├── manifest.mf
└── lib/
    └── greeter.jar
```

Chạy ứng dụng:

```sh
java -jar app.jar
```

Kết quả:

```text
Xin chào, Java!
```

Trong ví dụ này, `app.jar` chứa `Main.class`, còn `lib/greeter.jar` chứa `Greeter.class`. Manifest cho Java biết vị trí dependency khi khởi chạy JAR.

**Lưu ý:** Khi dùng tùy chọn `-jar`, các thiết lập classpath khác trên dòng lệnh và biến môi trường `CLASSPATH` bị bỏ qua. Nếu cần dùng `java -jar app.jar`, hãy khai báo dependency phù hợp trong manifest hoặc đóng gói ứng dụng theo cách khác. Không kỳ vọng `java -cp ... -jar app.jar` sẽ bổ sung classpath như khi chạy trực tiếp tên lớp.

Thuộc tính `Class-Path` trong manifest sử dụng URL, có quy tắc phân cách bằng khoảng trắng và phân giải tương đối với JAR chứa manifest. Nó không dùng chuỗi classpath theo hệ điều hành như `-cp`. Với tên tệp có khoảng trắng hoặc ký tự đặc biệt, cần mã hóa URL phù hợp.

## 7. Wildcard cho thư mục chứa nhiều JAR

Khi thư mục `lib` có nhiều thư viện, có thể dùng wildcard:

macOS/Linux:

```sh
java --class-path "build/app:lib/*" com.example.app.Main
```

Windows PowerShell:

```powershell
java --class-path "build\app;lib\*" com.example.app.Main
```

`lib/*` bao gồm các tệp JAR trong chính thư mục `lib`. Wildcard không quét các thư mục con và không có nghĩa là mọi file trong thư mục đều được thêm vào classpath. Thứ tự các JAR được mở rộng từ wildcard không được bảo đảm; vì vậy, không dựa vào thứ tự đó khi có nhiều JAR chứa cùng một lớp.

Wildcard hữu ích cho thư mục dependency được quản lý như một tập hợp. Trong ứng dụng cần tái lập chính xác, nên để Gradle/Maven quản lý dependency và runtime classpath, tránh để kết quả phụ thuộc vào những JAR thừa hoặc phiên bản không mong muốn trong thư mục.

## 8. Thứ tự tìm lớp và xung đột phiên bản

Với classpath thông thường của application class loader, các entry được xét theo thứ tự khai báo. Nếu nhiều entry chứa cùng một tên lớp đầy đủ, lớp được tìm thấy trước có thể che khuất lớp ở entry phía sau. Đây là nguyên nhân thường gặp khi một ứng dụng vô tình nạp phiên bản thư viện cũ.

Ví dụ, nếu cả `lib/old-api.jar` và `lib/new-api.jar` đều chứa `com.example.ApiClient`, việc đặt JAR nào trước có thể ảnh hưởng lớp được nạp. Không nên giải quyết xung đột bằng cách tùy tiện đổi thứ tự nếu chưa xác định phiên bản dependency mà ứng dụng thực sự cần.

Các nguyên tắc thực tế:

- Chỉ đưa vào classpath những dependency mà ứng dụng cần.
- Tránh chứa nhiều phiên bản của cùng một thư viện nếu không có chủ đích.
- Không giả định thứ tự JAR khi dùng wildcard.
- Dùng cùng một dependency set ở bước chạy local, kiểm thử và triển khai.
- Nếu dùng Gradle hoặc Maven, kiểm tra runtime dependency graph khi có xung đột thay vì tự thêm JAR bằng tay.

Class loader còn có cơ chế delegation giữa các loader. Vì thế, thứ tự entry trong classpath chỉ là một phần của quá trình nạp lớp; nó không có nghĩa ứng dụng có thể thay thế tùy ý mọi lớp thuộc nền tảng Java hoặc mọi lớp do loader cha cung cấp.

## 9. Classpath và module path

Từ Java 9, Java Platform Module System bổ sung **module path** để tìm các module có tên. Hai cơ chế này phục vụ hai kiểu tổ chức ứng dụng khác nhau:

| Cơ chế | Mục đích | Tùy chọn Java launcher |
|---|---|---|
| Classpath | Chạy ứng dụng và thư viện theo mô hình classpath truyền thống | `-cp`, `--class-path` |
| Module path | Tìm module có tên, thường được mô tả bằng `module-info.java` | `-p`, `--module-path` |

Các lớp được nạp từ classpath thông thường thuộc unnamed module. Đặt một JAR có `module-info.class` lên classpath không làm nó tự động được khởi chạy như một named module.

Nếu dự án sử dụng module system, hãy dùng module path và cách khởi chạy module tương ứng, ví dụ:

```sh
java --module-path mods --module com.example.app/com.example.app.Main
```

Lệnh trên minh họa cú pháp chạy một module có tên `com.example.app`, với main class `com.example.app.Main`. Tên module và cấu trúc thư mục phải khớp với module đã biên dịch. Với ứng dụng chưa dùng module system, tiếp tục dùng classpath là lựa chọn phù hợp.

## 10. Kiểm tra classpath và theo dõi việc nạp lớp

Có thể in classpath mà ứng dụng được khởi chạy với:

```java
System.out.println(System.getProperty("java.class.path"));
```

Thuộc tính này hữu ích để kiểm tra các entry được truyền cho ứng dụng. Nó không phải danh sách đầy đủ mọi lớp đã nạp, cũng không phản ánh mọi dependency có thể được thêm động bởi custom class loader.

Để quan sát JVM nạp lớp từ đâu trên JDK 9 trở lên, chạy:

```sh
java -Xlog:class+load=info --class-path "build/app:lib/greeter.jar" com.example.app.Main
```

Log có thể dài vì JVM nạp cả lớp nền tảng lẫn lớp ứng dụng. Tìm tên lớp cần kiểm tra, chẳng hạn `com.example.greeting.Greeter`, và xem nguồn được ghi trong log. Trên Windows, thay dấu `:` giữa các entry bằng dấu `;`.

Khi cần kiểm tra thủ công, cũng hãy xem thư mục làm việc hiện tại. Các entry tương đối như `lib/greeter.jar` được phân giải từ **working directory của tiến trình** khi dùng classpath trên dòng lệnh; chúng không tự động tính từ thư mục chứa file `.java` hoặc file cấu hình của IDE.

## 11. Lỗi runtime classpath thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Error: Could not find or load main class ...` | Classpath thiếu thư mục/JAR chứa lớp main, package root sai hoặc tên lớp đầy đủ không đúng | Kiểm tra tên package, tên lớp và vị trí `.class`; classpath phải trỏ đến gốc của cây package |
| `ClassNotFoundException` | Mã dùng cơ chế nạp lớp theo tên, ví dụ `Class.forName`, nhưng loader không tìm thấy lớp | Xác nhận tên lớp và dependency có mặt trong classpath của loader đang dùng |
| `NoClassDefFoundError` | Lớp cần thiết có thể có lúc biên dịch nhưng không còn tìm thấy khi runtime cần nạp hoặc liên kết | Kiểm tra runtime classpath và các dependency gián tiếp; bảo đảm JAR được triển khai cùng ứng dụng |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Runtime nạp phiên bản thư viện không tương thích với phiên bản đã dùng khi biên dịch | Kiểm tra trùng JAR, thứ tự classpath và phiên bản dependency thực tế |
| Chạy được trong IDE nhưng lỗi khi chạy từ Terminal | IDE tự cấu hình runtime classpath hoặc working directory khác | Kiểm tra cấu hình Run/Debug của IDE và tái tạo classpath trong lệnh chạy |
| Chạy được trên máy phát triển nhưng lỗi trên máy khác | Dependency chỉ tồn tại cục bộ, phụ thuộc `CLASSPATH` ẩn hoặc đường dẫn tương đối khác | Đóng gói/cung cấp đủ dependency và dùng lệnh chạy tái lập được |
| Sửa JAR nhưng chương trình vẫn dùng API cũ | Có nhiều bản JAR hoặc tiến trình/daemon cũ vẫn chạy | Kiểm tra log nạp lớp, runtime dependency graph và khởi động lại tiến trình |

Phân biệt hai lỗi thường bị nhầm:

- `ClassNotFoundException` là exception thường xuất hiện khi ứng dụng yêu cầu loader tìm một lớp theo tên nhưng không tìm thấy.
- `NoClassDefFoundError` là lỗi liên kết/nạp lớp khi JVM cần một định nghĩa lớp mà runtime không thể cung cấp. Một trường hợp thường gặp là thiếu dependency lúc chạy dù mã nguồn đã biên dịch được.

Nếu lớp đã tìm thấy nhưng API của phiên bản runtime khác với API mà ứng dụng đã biên dịch, có thể gặp `NoSuchMethodError` hoặc `NoSuchFieldError`. Khi đó, chỉ thêm một JAR bất kỳ có thể làm tình hình khó chẩn đoán hơn; hãy xác định phiên bản thư viện thực sự được nạp.

## 12. Checklist trước khi kết luận ứng dụng thiếu dependency

1. Xác nhận tên lớp đầy đủ và package root.
2. Xác nhận file `.class` hoặc JAR chứa lớp tồn tại tại đường dẫn được khai báo.
3. Kiểm tra classpath của lệnh chạy, không chỉ classpath của lệnh biên dịch.
4. Dùng dấu phân cách đúng hệ điều hành: `;` trên Windows, `:` trên macOS/Linux.
5. Kiểm tra working directory nếu classpath chứa đường dẫn tương đối.
6. Kiểm tra JAR trùng tên lớp hoặc nhiều phiên bản của cùng dependency.
7. Nếu chạy bằng `java -jar`, kiểm tra `Main-Class` và `Class-Path` trong manifest.
8. Nếu dự án dùng module system, xác nhận đang cấu hình module path thay vì nhầm với classpath.
9. Dùng log nạp lớp hoặc runtime dependency graph để tìm đúng nguồn của lớp.

Runtime classpath là cấu hình tìm lớp tại thời điểm chạy. Khi compile-time classpath và runtime classpath nhất quán, các thư viện được cung cấp đầy đủ, và đường dẫn được phân giải đúng, Java launcher có thể nạp lớp ứng dụng cùng dependency một cách ổn định.