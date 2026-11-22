# Classpath trong javac

Khi biên dịch một chương trình Java có sử dụng lớp từ thư viện bên ngoài, trình biên dịch `javac` cần biết nơi tìm các lớp đó. **Classpath (đường dẫn lớp)** là danh sách thư mục, tệp JAR hoặc ZIP mà trình biên dịch và JVM tìm kiếm để nạp các lớp Java.

Trong lúc biên dịch, classpath giúp `javac` tìm các lớp đã biên dịch mà mã nguồn đang tham chiếu. Khi chạy ứng dụng, JVM cũng cần classpath tương ứng để tìm các lớp đó. Hai lần cấu hình này là hai thao tác riêng biệt.

## 1. Classpath là gì?

Classpath là danh sách vị trí chứa các tệp lớp `.class` và thư viện Java dạng JAR/ZIP. Một mục classpath có thể là:

- Một thư mục gốc chứa cấu trúc package và các tệp `.class`.
- Một tệp thư viện `.jar`.
- Một tệp ZIP chứa các lớp Java.

Ví dụ cấu trúc thư mục:

```text
project/
  out/
    app/
      Main.class
  lib/
    helper.jar
```

Nếu lớp `app.Main` cần dùng lớp trong `helper.jar`, classpath cần chứa thư mục gốc `out` khi chạy và tệp JAR `lib/helper.jar`.

**Đường dẫn phải trỏ đến gốc của cấu trúc package.** Nếu một lớp có tên đầy đủ là `com.example.Tool`, thư mục classpath phải là thư mục chứa thư mục con `com`, không phải chính thư mục `com/example`.

Classpath không phải là nơi lưu mã nguồn bắt buộc. Mã nguồn được truyền trực tiếp cho `javac` hoặc được tìm thông qua source path; classpath chủ yếu xác định nơi tìm các lớp và thư viện đã biên dịch.

## 2. Tùy chọn classpath của javac

Có ba cách viết tương đương để chỉ định classpath:

- `-cp`
- `-classpath`
- `--class-path`

Ví dụ:

```bash
javac -cp lib/helper.jar -d out src/app/Main.java
```

Lệnh trên có nghĩa:

- `javac`: gọi trình biên dịch Java.
- `-cp lib/helper.jar`: tìm các lớp phụ thuộc trong JAR.
- `-d out`: ghi các tệp `.class` được tạo ra vào thư mục `out`.
- `src/app/Main.java`: tệp nguồn cần biên dịch.

Có thể viết tương đương:

```bash
javac --class-path lib/helper.jar -d out src/app/Main.java
```

Nếu thư viện có nhiều JAR, đặt các mục trong cùng một chuỗi classpath và phân cách bằng ký tự phù hợp với hệ điều hành.

**Windows (dấu chấm phẩy):**

```powershell
javac -cp "lib\helper.jar;lib\logging.jar" -d out src\app\Main.java
```

**macOS/Linux (dấu hai chấm):**

```bash
javac -cp "lib/helper.jar:lib/logging.jar" -d out src/app/Main.java
```

Nếu đường dẫn có dấu cách, đặt toàn bộ giá trị classpath trong dấu nháy để shell truyền nó thành một đối số.

## 3. Classpath mặc định và biến CLASSPATH

Nếu không truyền `-cp`, `-classpath` hoặc `--class-path`, `javac` sử dụng classpath mặc định. Giá trị này có thể đến từ biến môi trường `CLASSPATH`; nếu biến đó không được đặt, thư mục hiện tại thường được sử dụng.

Ví dụ, nếu terminal đang ở thư mục dự án và không có cấu hình `CLASSPATH`, trình biên dịch có thể tìm lớp trong thư mục hiện tại.

Khi chỉ định `-cp` rõ ràng, giá trị đó thay thế classpath mặc định cho lần biên dịch. Nó không tự động cộng thêm thư mục hiện tại hoặc giá trị `CLASSPATH`.

Nếu cần cả thư mục hiện tại và thư viện, hãy đưa cả hai vào danh sách.

**Windows:**

```powershell
javac -cp ".;lib\helper.jar" -d out src\app\Main.java
```

**macOS/Linux:**

```bash
javac -cp ".:lib/helper.jar" -d out src/app/Main.java
```

Trong dự án thực tế, nên chỉ định classpath rõ ràng trong lệnh build hoặc cấu hình Maven/Gradle thay vì phụ thuộc vào `CLASSPATH` toàn cục. Cách này giúp kết quả biên dịch nhất quán giữa máy cá nhân, IDE và CI.

## 4. Ví dụ hoàn chỉnh: biên dịch với thư viện JAR

Ví dụ sau tạo một thư viện nhỏ, đóng gói thành JAR, rồi dùng thư viện đó khi biên dịch ứng dụng.

Cấu trúc tệp nguồn:

```text
project/
  lib-src/
    greeter/
      Greeting.java
  src/
    app/
      Main.java
```

### Bước 1: Tạo lớp thư viện

Tệp **`lib-src/greeter/Greeting.java`**:

```java
package greeter;

public class Greeting {
    public static String message() {
        return "Hello from dependency JAR";
    }
}
```

### Bước 2: Tạo lớp ứng dụng

Tệp **`src/app/Main.java`**:

```java
package app;

import greeter.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Lớp `Main` sử dụng `greeter.Greeting`, nhưng lớp này nằm trong một thư viện riêng. Vì vậy, cần biên dịch và đóng gói thư viện trước.

### Bước 3: Biên dịch thư viện

Tại thư mục gốc `project`, tạo các thư mục đầu ra:

**macOS/Linux:**

```bash
mkdir -p lib-classes lib out
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force lib-classes, lib, out | Out-Null
```

Biên dịch lớp thư viện:

```bash
javac -d lib-classes lib-src/greeter/Greeting.java
```

Sau khi biên dịch, lớp được tạo tại:

```text
lib-classes/
  greeter/
    Greeting.class
```

Tùy chọn `-d lib-classes` chỉ định thư mục gốc chứa kết quả biên dịch. `javac` tự tạo các thư mục con tương ứng với package `greeter`.

### Bước 4: Đóng gói thành JAR

Chạy:

```bash
jar --create --file lib/greeter.jar -C lib-classes .
```

Lệnh này tạo `lib/greeter.jar` từ nội dung trong `lib-classes`. Tùy chọn `-C` chuyển thư mục làm việc của lệnh `jar` sang `lib-classes` trước khi thêm nội dung.

Có thể kiểm tra nội dung JAR:

```bash
jar --list --file lib/greeter.jar
```

Danh sách cần có mục:

```text
greeter/Greeting.class
```

### Bước 5: Biên dịch ứng dụng với classpath

Chạy tại thư mục gốc `project`:

```bash
javac -cp lib/greeter.jar -d out src/app/Main.java
```

Lúc này, `javac` tìm lớp `greeter.Greeting` bên trong `lib/greeter.jar` để kiểm tra lời gọi `Greeting.message()`.

Lớp ứng dụng được tạo tại:

```text
out/
  app/
    Main.class
```

Nếu bỏ tùy chọn `-cp lib/greeter.jar`, trình biên dịch không tìm thấy lớp `greeter.Greeting` và thường báo lỗi kiểu `package greeter does not exist` hoặc `cannot find symbol`.

### Bước 6: Chạy ứng dụng

Classpath lúc chạy phải có cả thư mục chứa lớp ứng dụng và JAR thư viện.

**Windows:**

```powershell
java -cp "out;lib\greeter.jar" app.Main
```

**macOS/Linux:**

```bash
java -cp "out:lib/greeter.jar" app.Main
```

Kết quả chính xác:

```text
Hello from dependency JAR
```

Ví dụ này minh họa hai classpath riêng:

- Khi biên dịch: `javac -cp lib/greeter.jar ...` để tìm lớp thư viện.
- Khi chạy: `java -cp "out;lib/greeter.jar" ...` trên Windows hoặc `java -cp "out:lib/greeter.jar" ...` trên macOS/Linux để tìm cả lớp ứng dụng và thư viện.

Classpath dùng lúc biên dịch không được lưu tự động vào tệp `.class`. JVM cần được cung cấp classpath khi chạy, hoặc ứng dụng cần được đóng gói và khởi chạy bằng một cơ chế khác có khai báo đường dẫn thư viện phù hợp.

## 5. Phân biệt classpath và sourcepath

Classpath và source path phục vụ hai mục đích liên quan nhưng khác nhau:

- **Classpath (`-cp`, `--class-path`):** nơi tìm các lớp đã biên dịch và thư viện.
- **Source path (`-sourcepath`):** nơi tìm các tệp nguồn `.java` mà trình biên dịch cần biên dịch bổ sung.

Nếu không chỉ định `-sourcepath`, classpath cũng có thể được dùng để tìm mã nguồn phụ thuộc. Khi chỉ định source path riêng, hãy đưa các thư mục nguồn cần thiết vào đó.

Ví dụ, nếu thư viện phụ thuộc có mã nguồn tại `lib-src` và chưa được đóng gói thành JAR, có thể dùng:

```bash
javac -sourcepath lib-src -d out src/app/Main.java
```

Khi đó, `javac` có thể tìm `greeter/Greeting.java` trong `lib-src` và biên dịch lớp phụ thuộc khi cần.

Trong trường hợp này, không cần JAR có sẵn cho thư viện `greeter`. Tuy nhiên, với dự án lớn, việc biên dịch tường minh tất cả mã nguồn hoặc dùng build tool thường giúp kiểm soát phụ thuộc và đầu ra rõ ràng hơn.

Có thể chỉ định cả classpath và source path:

```bash
javac -cp lib/external.jar -sourcepath src:lib-src -d out src/app/Main.java
```

Dấu phân cách trong ví dụ trên là dấu hai chấm của macOS/Linux. Trên Windows, dùng dấu chấm phẩy giữa các mục source path.

## 6. Dùng thư mục chứa class đã biên dịch làm dependency

Classpath không bắt buộc phải là JAR. Một thư mục chứa các tệp `.class` cũng có thể được dùng làm dependency.

Với cấu trúc:

```text
project/
  library-classes/
    greeter/
      Greeting.class
  src/
    app/
      Main.java
```

Biên dịch ứng dụng:

```bash
javac -cp library-classes -d out src/app/Main.java
```

`javac` tìm `greeter/Greeting.class` tương đối với thư mục gốc `library-classes`.

Khi chạy, cần thêm cả `out` và `library-classes` vào classpath.

**Windows:**

```powershell
java -cp "out;library-classes" app.Main
```

**macOS/Linux:**

```bash
java -cp "out:library-classes" app.Main
```

Cách này hữu ích khi các module được build vào những thư mục riêng trước khi đóng gói thành JAR.

## 7. Dùng wildcard để thêm nhiều JAR

Khi thư mục có nhiều thư viện, có thể dùng wildcard `*` để đưa tất cả tệp JAR trực tiếp trong thư mục đó vào classpath.

Ví dụ:

```bash
javac -cp "lib/*" -d out src/app/Main.java
```

Một số điểm cần nhớ:

- Wildcard `lib/*` bao gồm các tệp JAR trong thư mục `lib`.
- Không tìm đệ quy trong các thư mục con.
- Thư mục `lib` phải tồn tại và chứa các JAR cần dùng.
- Đặt giá trị trong dấu nháy giúp shell không tự mở rộng dấu `*` trước khi truyền cho Java tool.
- Không nên dựa vào thứ tự của các JAR được wildcard nạp nếu có lớp trùng tên.

Có thể kết hợp thư mục hiện tại và các JAR:

**Windows:**

```powershell
javac -cp ".;lib\*" -d out src\app\Main.java
```

**macOS/Linux:**

```bash
javac -cp ".:lib/*" -d out src/app/Main.java
```

Wildcard tiện cho thử nghiệm hoặc thư mục thư viện được quản lý đồng bộ. Với build production, nên để Maven, Gradle hoặc công cụ build tạo classpath chính xác từ dependency đã khai báo.

## 8. Thứ tự classpath và lớp trùng tên

Khi classpath chứa nhiều mục, JVM và trình biên dịch tìm lớp theo thứ tự các mục được liệt kê. Nếu hai JAR cùng chứa một lớp có tên đầy đủ giống nhau, mục xuất hiện trước có thể được dùng.

Ví dụ trên macOS/Linux:

```bash
javac -cp "lib/v2.jar:lib/v1.jar" -d out src/app/Main.java
```

Trên Windows, dùng dấu chấm phẩy:

```powershell
javac -cp "lib\v2.jar;lib\v1.jar" -d out src\app\Main.java
```

Nếu cả hai JAR đều chứa `com.example.Helper`, thứ tự classpath có thể làm thay đổi phiên bản lớp được chọn. Điều này dễ gây lỗi khó tìm, nhất là khi API giữa hai phiên bản khác nhau.

Để tránh xung đột:

- Loại bỏ dependency trùng phiên bản.
- Dùng dependency tree của Maven/Gradle để tìm nguồn thư viện.
- Tránh đưa cả thư viện cũ và mới vào classpath.
- Không dựa vào thứ tự wildcard khi nhiều JAR chứa lớp trùng tên.

## 9. Classpath và module path

Từ Java 9, nền tảng Java có hệ thống module. Classpath và module path không tương đương.

| Tiêu chí | Classpath | Module path |
| --- | --- | --- |
| Tùy chọn javac | `-cp`, `--class-path` | `-p`, `--module-path` |
| Đơn vị chính | Lớp và package | Module |
| Mô tả module | Không yêu cầu `module-info.java` | Module có thể khai báo `module-info.java` |
| Quan hệ truy cập | Các lớp trên classpath thuộc unnamed module | Module có ranh giới và quy tắc đọc/exports |
| Phù hợp | Ứng dụng và thư viện classpath truyền thống | Ứng dụng/module dùng Java Platform Module System |

Nếu dự án dùng module, cần đọc hướng dẫn của `javac` về `--module-path`, `--module-source-path` và cách biên dịch module. Không đưa mọi dependency vào classpath chỉ vì lệnh `-cp` dễ dùng hơn; việc đó có thể làm thay đổi cách hệ thống module xử lý thư viện.

## 10. Tùy chọn javac thường đi cùng classpath

| Tùy chọn | Công dụng |
| --- | --- |
| `-cp` / `--class-path` | Chỉ định nơi tìm lớp và thư viện |
| `-sourcepath` | Chỉ định nơi tìm mã nguồn phụ thuộc |
| `-d` | Chỉ định thư mục gốc chứa tệp `.class` đầu ra |
| `-encoding` | Chỉ định encoding của tệp nguồn |
| `--release` | Chỉ định phiên bản nền tảng Java mục tiêu |
| `-verbose` | Hiển thị thông tin chi tiết về hoạt động biên dịch và nạp lớp |
| `-implicit:none` | Không tạo tệp class cho các nguồn được biên dịch ngầm định |

Ví dụ kết hợp các tùy chọn:

```bash
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/app/Main.java
```

Lệnh dùng JDK hỗ trợ `--release 17`, đọc mã nguồn UTF-8, tìm dependency trong các JAR của `lib`, và ghi lớp đã biên dịch vào `out`.

Tùy chọn `--release` không thay thế classpath. Nó điều khiển phiên bản nền tảng Java mà mã được biên dịch hướng tới; classpath vẫn xác định nơi tìm thư viện phụ thuộc.

## 11. Lỗi thường gặp khi cấu hình classpath

| Lỗi hoặc hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `package ... does not exist` | Thiếu JAR/thư mục dependency hoặc đường dẫn classpath sai | Kiểm tra JAR có chứa package và thêm đúng mục vào `-cp` |
| `cannot find symbol` | Thiếu lớp, sai import/tên lớp hoặc phiên bản thư viện không có API đang gọi | Xác minh dependency và phiên bản của nó |
| Biên dịch được nhưng chạy báo `ClassNotFoundException` | Classpath lúc chạy thiếu thư viện hoặc thư mục output | Thêm cả thư mục class đã biên dịch và các JAR cần thiết vào `java -cp` |
| `NoClassDefFoundError` | Lớp cần thiết không có lúc runtime hoặc quá trình khởi tạo lớp thất bại | Xem nguyên nhân gốc và classpath runtime; kiểm tra dependency bắc cầu |
| Thư viện có trong thư mục nhưng javac không tìm thấy | Đưa thư mục package thay vì thư mục gốc, sai tên JAR hoặc wildcard không được truyền đúng | Kiểm tra cấu trúc JAR bằng `jar --list` và giá trị `-cp` |
| Windows dùng classpath nhiều mục không được | Dùng dấu hai chấm thay vì dấu chấm phẩy | Dùng `;` để phân cách các mục trên Windows |
| macOS/Linux dùng classpath nhiều mục không được | Dùng dấu chấm phẩy thay vì dấu hai chấm | Dùng `:` để phân cách các mục |
| Chương trình nạp nhầm phiên bản thư viện | Có nhiều JAR chứa cùng lớp và thứ tự classpath không mong muốn | Loại bỏ dependency trùng và kiểm tra thứ tự classpath |

### Cách chẩn đoán

Khi không biết trình biên dịch đang tìm lớp ở đâu, thử:

```bash
javac -verbose -cp "lib/*" -d out src/app/Main.java
```

Thông tin verbose giúp quan sát quá trình tìm và nạp lớp. Có thể kết hợp với `jar --list --file lib/helper.jar` để kiểm tra thư viện có chứa đúng đường dẫn lớp hay không.

Hãy kiểm tra từng yếu tố theo thứ tự:

1. Tên package trong mã nguồn.
2. Đường dẫn package bên trong thư mục hoặc JAR.
3. Classpath có trỏ đến thư mục gốc/JAR đúng không.
4. Phiên bản thư viện có chứa lớp và phương thức đang dùng không.
5. Classpath runtime có đủ dependency như classpath compile không.

## 12. Thực hành tốt khi quản lý classpath

- Khai báo dependency rõ ràng và có phiên bản cụ thể.
- Dùng đường dẫn tương đối với thư mục dự án hoặc classpath do build tool sinh ra.
- Không phụ thuộc vào `CLASSPATH` toàn cục trên máy phát triển.
- Tách thư mục mã nguồn, thư mục class đầu ra và thư mục thư viện.
- Giữ classpath lúc biên dịch và lúc chạy tương thích với nhau.
- Tránh đặt nhiều phiên bản của cùng một thư viện trên classpath.
- Không đưa thư viện không đáng tin cậy vào classpath; mã trong thư viện có thể thực thi trong tiến trình ứng dụng.
- Với dự án nhiều dependency, ưu tiên Maven hoặc Gradle để giải quyết dependency và tạo classpath nhất quán.
- Nếu dùng Java modules, cấu hình module path thay vì mặc định coi mọi thư viện là classpath.

## 13. Ghi nhớ

- Classpath là danh sách thư mục, JAR hoặc ZIP mà Java tools tìm kiếm các lớp.
- Dùng `javac -cp`, `-classpath` hoặc `--class-path` để khai báo dependency khi biên dịch.
- Dùng `-d` để đặt thư mục gốc cho các tệp class được tạo.
- Dùng `-sourcepath` khi cần chỉ rõ nơi tìm mã nguồn phụ thuộc.
- Dùng `-cp` cho `java` lúc chạy nữa; classpath lúc biên dịch không tự lưu vào tệp class.
- Windows phân cách classpath bằng `;`; macOS/Linux dùng `:`.
- Có thể dùng `lib/*` để thêm các JAR trực tiếp trong một thư mục.
- Classpath khác module path; chọn đúng cơ chế theo cấu trúc dự án.

Khi hiểu rõ classpath, bạn có thể biên dịch chương trình Java phụ thuộc vào thư viện bên ngoài, chẩn đoán lỗi thiếu lớp và kiểm soát chính xác những dependency mà trình biên dịch và JVM sử dụng.
