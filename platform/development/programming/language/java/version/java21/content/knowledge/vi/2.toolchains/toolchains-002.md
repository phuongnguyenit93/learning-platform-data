# Kiểm tra `java`, `javac`, `JAVA_HOME` và phiên bản JVM thực thi

## Mục tiêu

Khi làm việc với Java 21, cần xác định rõ máy đang gọi lệnh `java` và `javac` nào, hai lệnh đó thuộc JDK nào, biến `JAVA_HOME` đang trỏ đến đâu và JVM thực tế đang chạy phiên bản nào. Việc kiểm tra này giúp phát hiện sớm lỗi cấu hình như cài nhiều JDK nhưng `PATH` chọn nhầm bản, `JAVA_HOME` trỏ sai thư mục hoặc chương trình được chạy bằng một JVM khác với JDK dùng để biên dịch.

Bài viết tập trung vào cách kiểm tra trên các hệ điều hành hiện hành. Ví dụ dùng Java 21; các lệnh kiểm tra phiên bản cũng áp dụng cho những bản JDK hiện đại khác.

## 1. Phân biệt `java`, `javac`, JDK và JVM

- **JDK (Java Development Kit)** là bộ công cụ phát triển. JDK 21 có trình biên dịch `javac`, trình khởi chạy `java` cùng các công cụ phát triển khác.
- **`javac`** biên dịch mã nguồn `.java` thành bytecode, thường được lưu trong tệp `.class`.
- **`java`** khởi chạy ứng dụng và tạo JVM để thực thi bytecode.
- **JVM (Java Virtual Machine)** là môi trường thực thi bytecode. Phiên bản JVM đang chạy được xác định bởi runtime thực tế đã khởi chạy tiến trình.
- **`JAVA_HOME`** là biến môi trường thường được các công cụ phát triển và build sử dụng để tìm JDK. Thông thường biến này trỏ đến thư mục gốc của JDK, không phải thư mục `bin` và cũng không phải đường dẫn đến tệp thực thi `java`.
- **`PATH`** là danh sách thư mục hệ điều hành tìm kiếm khi người dùng gõ lệnh. Lệnh `java` hoặc `javac` được gọi thường là tệp thực thi đầu tiên phù hợp được tìm thấy theo thứ tự trong `PATH`.

Một máy có thể cài nhiều JDK cùng lúc. Vì vậy, việc `JAVA_HOME` trỏ đến JDK 21 không tự động bảo đảm lệnh `java` và `javac` đang chạy cũng thuộc JDK 21. Cần kiểm tra cả biến môi trường lẫn đường dẫn thực tế mà shell phân giải.

## 2. Kiểm tra phiên bản `java` và `javac`

Mở terminal mới sau khi cấu hình môi trường, rồi chạy:

```bash
java --version
javac --version
```

Với JDK 21, kết quả thường có dạng tương tự:

```text
openjdk 21.0.x 20xx-xx-xx
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...

javac 21.0.x
```

Các thành phần cụ thể như số bản cập nhật, ngày phát hành, tên nhà cung cấp và thông tin VM có thể khác nhau giữa các bản phân phối JDK. Điều cần xác nhận là phiên bản chính hiển thị là `21` khi dự án yêu cầu Java 21.

`java --version` cho biết phiên bản của trình chạy/runtime được gọi qua lệnh `java`. `javac --version` cho biết phiên bản trình biên dịch được gọi qua lệnh `javac`. Hai kết quả nên thuộc cùng dòng JDK mà dự án yêu cầu. Nếu một lệnh báo phiên bản 21 còn lệnh kia báo phiên bản khác, hãy kiểm tra `PATH` và `JAVA_HOME` ở các bước tiếp theo.

> Lưu ý: `java` và `javac` là hai lệnh độc lập. Chỉ kiểm tra một lệnh không đủ để kết luận toàn bộ toolchain đang dùng đúng JDK.

## 3. Xác định tệp thực thi được shell lựa chọn

Khi cài nhiều JDK, cần biết chính xác đường dẫn mà hệ điều hành chọn cho từng lệnh.

### Windows PowerShell

```powershell
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

`Get-Command -All` hiển thị các lệnh PowerShell có thể phân giải, còn `where.exe` tìm các tệp thực thi theo `PATH`. Hãy xem kết quả đầu tiên được dùng và kiểm tra xem đường dẫn có nằm trong thư mục JDK mong muốn hay không. Nếu có nhiều kết quả, các JDK khác có thể đang xuất hiện ở những vị trí tiếp theo trong `PATH`.

### Linux

```bash
command -v java
command -v javac
```

Trên hệ thống có tiện ích `readlink`, có thể kiểm tra thêm đường dẫn đích của symbolic link:

```bash
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
```

`command -v` cho biết shell sẽ gọi lệnh ở đâu. Kết quả `readlink -f` giúp lần theo các symbolic link, thường hữu ích khi bản Java được quản lý qua trình quản lý gói hoặc công cụ quản lý phiên bản.

### macOS

```bash
command -v java
command -v javac
/usr/libexec/java_home -V
```

Lệnh `java_home -V` liệt kê các JDK mà macOS nhận diện được. Có thể dùng kết quả này để đối chiếu bản JDK mong muốn với đường dẫn mà shell đang sử dụng. `command -v` vẫn là bước cần thiết để biết lệnh trong shell hiện tại được phân giải từ đâu.

## 4. Kiểm tra biến `JAVA_HOME`

`JAVA_HOME` thường cần trỏ đến thư mục gốc của một bản JDK. Ví dụ cấu trúc cài đặt có thể như sau:

```text
/opt/jdk-21/
├── bin/
│   ├── java
│   └── javac
└── ...
```

Trong ví dụ này, giá trị đúng là `/opt/jdk-21`, không phải `/opt/jdk-21/bin` và cũng không phải `/opt/jdk-21/bin/java`.

### Windows PowerShell

```powershell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
```

Hai lệnh `Test-Path` nên trả về `True` nếu `JAVA_HOME` trỏ đến một JDK có đủ các tệp thực thi tương ứng. Nếu biến chưa được đặt, biểu thức kiểm tra sẽ không tìm được đường dẫn hợp lệ.

### Linux và macOS

```bash
printf '%s\n' "$JAVA_HOME"
test -x "$JAVA_HOME/bin/java" && echo "java: OK" || echo "java: NOT FOUND"
test -x "$JAVA_HOME/bin/javac" && echo "javac: OK" || echo "javac: NOT FOUND"
```

Nếu `JAVA_HOME` chưa được đặt hoặc trỏ sai, các kiểm tra sẽ báo `NOT FOUND`. Hãy sửa cấu hình tại nơi đang quản lý biến môi trường, sau đó mở terminal mới hoặc nạp lại cấu hình shell để kiểm tra lại.

### Đối chiếu `JAVA_HOME` với `PATH`

Có thể gọi trực tiếp các tệp trong `JAVA_HOME` để kiểm tra phiên bản của chính JDK mà biến này tham chiếu:

PowerShell:

```powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\javac.exe" --version
```

Linux hoặc macOS:

```bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
```

So sánh kết quả này với `java --version` và `javac --version`. Nếu kết quả khác nhau, `PATH` đang dẫn đến một bản cài đặt khác với bản được chỉ định bởi `JAVA_HOME`.

Không phải mọi ứng dụng Java đều bắt buộc phải có `JAVA_HOME` để chạy lệnh `java` từ `PATH`. Tuy nhiên, nhiều IDE, công cụ build và script dùng biến này để tìm JDK, vì vậy cấu hình đúng giúp các công cụ cùng sử dụng một bộ công cụ như dự kiến.

## 5. Xác minh JVM thực sự đang thực thi

Phiên bản của lệnh `java` cho biết runtime sẽ được khởi chạy khi gọi lệnh đó. Để xem thông tin runtime và JVM của tiến trình được tạo ra, dùng:

```bash
java -XshowSettings:properties -version
```

Trong phần thuộc tính hệ thống, chú ý các khóa:

| Thuộc tính | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java của runtime đang chạy, ví dụ `21.0.x` |
| `java.vendor` | Nhà cung cấp bản runtime |
| `java.home` | Thư mục runtime đang được tiến trình sử dụng |
| `os.arch` | Kiến trúc hệ điều hành mà runtime báo cáo |

Lệnh này in thông tin phiên bản và các thuộc tính của runtime vừa khởi chạy. `java.home` mô tả vị trí runtime của tiến trình; không nên mặc định rằng giá trị này phải giống tuyệt đối với chuỗi `JAVA_HOME`, vì cách đóng gói JDK/runtime có thể khiến hai đường dẫn khác nhau.

Để xác minh từ bên trong một ứng dụng Java, tạo tệp `RuntimeInfo.java`:

```java
public class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println("Java version: "
                + System.getProperty("java.version"));
        System.out.println("Java vendor: "
                + System.getProperty("java.vendor"));
        System.out.println("Java home: "
                + System.getProperty("java.home"));
        System.out.println("JVM name: "
                + System.getProperty("java.vm.name"));
        System.out.println("JVM version: "
                + System.getProperty("java.vm.version"));
    }
}
```

Biên dịch và chạy chương trình:

```bash
javac RuntimeInfo.java
java RuntimeInfo
```

Các giá trị được in ra đến từ chính tiến trình JVM đang thực thi chương trình. Đây là cách kiểm tra hữu ích khi cần xác nhận runtime của một ứng dụng cụ thể, đặc biệt khi ứng dụng được khởi chạy bởi IDE, script hoặc một công cụ build.

## 6. Kiểm tra nhanh toàn bộ toolchain bằng một chương trình

Thực hiện các bước sau trong cùng một terminal:

```bash
java --version
javac --version
java -XshowSettings:properties -version
javac RuntimeInfo.java
java RuntimeInfo
```

Sau đó đối chiếu:

1. `java --version` báo runtime thuộc Java 21.
2. `javac --version` báo trình biên dịch thuộc Java 21.
3. Đường dẫn `java` và `javac` được shell phân giải thuộc bản JDK dự kiến.
4. `JAVA_HOME` trỏ đến thư mục gốc của JDK và trong đó có `bin/java`, `bin/javac`.
5. Chương trình `RuntimeInfo` in ra `java.version` có phiên bản chính là `21`.

Nếu các bước trên được thực hiện trong cùng terminal và cho kết quả nhất quán, cấu hình Java 21 cơ bản đã sẵn sàng cho việc biên dịch và chạy chương trình bằng các lệnh đó.

## 7. Xử lý các tình huống cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra và xử lý |
|---|---|---|
| `java --version` không chạy | Chưa cài JDK hoặc thư mục `bin` chưa có trong `PATH` | Xác nhận JDK đã cài; kiểm tra `PATH` và mở terminal mới sau khi cập nhật |
| Có `java` nhưng không có `javac` | Lệnh `java` đang đến từ runtime không có compiler hoặc `PATH` không trỏ đến JDK phù hợp | Kiểm tra đường dẫn bằng `where.exe`, `Get-Command` hoặc `command -v`; cấu hình `PATH` đến `bin` của JDK |
| `java` và `javac` báo phiên bản khác nhau | Hai lệnh được phân giải từ các bản cài đặt khác nhau | Kiểm tra tất cả đường dẫn tìm được; điều chỉnh thứ tự `PATH` và `JAVA_HOME` |
| `JAVA_HOME` có giá trị nhưng không tìm thấy `bin/java` | Biến trỏ nhầm vào thư mục `bin`, thư mục cha hoặc một đường dẫn không còn tồn tại | Đặt lại biến về thư mục gốc của JDK đang cài |
| Terminal mới vẫn dùng phiên bản cũ | `PATH` có đường dẫn cũ đứng trước hoặc shell/IDE giữ môi trường cũ | Kiểm tra thứ tự `PATH`, mở lại terminal/IDE và kiểm tra lại đường dẫn lệnh |
| Terminal dùng Java 21 nhưng IDE hoặc ứng dụng dùng bản khác | IDE, dịch vụ hoặc công cụ build có cấu hình JDK riêng | Kiểm tra JDK được cấu hình trong chính IDE/công cụ và kiểm tra `java.version` bên trong tiến trình ứng dụng |

Khi chỉnh sửa `PATH`, đặt thư mục `bin` của JDK mong muốn ở vị trí phù hợp trong danh sách tìm kiếm. Khi chỉnh sửa `JAVA_HOME`, dùng thư mục gốc của JDK. Sau khi thay đổi biến môi trường ở cấp hệ điều hành hoặc tài khoản, khởi động lại terminal và ứng dụng cần nhận cấu hình mới.

## Kết luận

Để xác nhận môi trường Java 21, hãy kiểm tra đồng thời phiên bản `java`, phiên bản `javac`, đường dẫn thực thi do shell lựa chọn và giá trị `JAVA_HOME`. Khi cần biết JVM của một chương trình cụ thể, đọc các thuộc tính `java.version`, `java.home` và `java.vm.version` ngay trong tiến trình đó. Những kiểm tra này cho biết rõ bộ công cụ nào đang biên dịch mã nguồn và runtime nào đang thực thi ứng dụng.
