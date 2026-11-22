# Tự biên dịch và chạy chương trình Java bằng dòng lệnh

Khi làm việc với Java, IDE thường giúp tạo cấu trúc dự án, biên dịch mã nguồn và chạy chương trình chỉ bằng một nút bấm. Tuy nhiên, phía sau thao tác đó vẫn là các công cụ dòng lệnh của JDK. Hiểu cách gọi những công cụ này giúp bạn nắm rõ chương trình đi từ tệp mã nguồn đến lúc chạy trên JVM như thế nào, tự kiểm tra môi trường Java và xử lý lỗi khi IDE hoặc build tool báo lỗi.

Quy trình cơ bản có ba phần:

```text
Tệp mã nguồn .java
       |
       | javac
       v
Tệp bytecode .class
       |
       | java
       v
JVM nạp và thực thi chương trình
```

`javac` là trình biên dịch đi kèm JDK. Nó đọc mã nguồn Java và tạo bytecode trong các tệp `.class`. Lệnh `java` khởi chạy JVM, nạp lớp có phương thức `main` và bắt đầu thực thi chương trình. Hai lệnh này thường được dùng riêng biệt: biên dịch trước, sau đó chạy kết quả vừa biên dịch.

## 1. Chuẩn bị JDK và kiểm tra môi trường

Bạn cần cài **JDK (Java Development Kit)** để biên dịch chương trình. JDK cung cấp trình chạy Java cùng các công cụ phát triển như `javac` và `jar`. JVM là thành phần thực thi bytecode; thư viện chuẩn Java cung cấp các lớp mà chương trình có thể sử dụng.

Một máy chỉ có môi trường chạy Java có thể thực thi ứng dụng đã biên dịch nhưng chưa chắc có `javac`. Vì vậy, khi học cách tự biên dịch, hãy kiểm tra rằng bạn đang dùng JDK.

Mở Terminal, PowerShell hoặc Command Prompt và chạy:

```shell
java -version
javac -version
```

Lệnh đầu tiên hiển thị phiên bản Java runtime. Lệnh thứ hai hiển thị phiên bản trình biên dịch. Hai lệnh đều phải chạy thành công. Nếu `java` có kết quả nhưng `javac` báo không tìm thấy lệnh, hãy kiểm tra lại gói JDK đã cài và đường dẫn thực thi.

### `JAVA_HOME` và `PATH`

Hai biến môi trường thường gặp có vai trò khác nhau:

- `JAVA_HOME` trỏ đến thư mục gốc của JDK, chẳng hạn thư mục cài đặt JDK trên máy. Giá trị này không kết thúc bằng thư mục `bin`.
- `PATH` chứa các thư mục mà hệ điều hành tìm kiếm khi bạn gõ một lệnh. Đưa thư mục `bin` của JDK vào `PATH` giúp Terminal tìm thấy `java`, `javac` và `jar`.

Ví dụ cấu hình tạm thời trong PowerShell, thay đường dẫn mẫu bằng thư mục JDK thực tế:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

Ví dụ trong shell trên Linux hoặc macOS:

```shell
export JAVA_HOME=/path/to/jdk
export PATH="$JAVA_HOME/bin:$PATH"
```

Các lệnh trên chỉ thay đổi môi trường của cửa sổ Terminal hiện tại. Muốn giữ cấu hình sau khi mở cửa sổ mới, hãy cập nhật biến môi trường trong phần cài đặt của hệ điều hành hoặc tệp cấu hình shell tương ứng. Sau khi thay đổi, mở Terminal mới và chạy lại hai lệnh kiểm tra phiên bản.

Nếu máy có nhiều bản JDK, hãy kiểm tra chính xác tệp thực thi mà Terminal đang chọn. Trong PowerShell có thể dùng:

```powershell
Get-Command java, javac | Select-Object Name, Source
```

Trong Command Prompt của Windows:

```bat
where java
where javac
```

Trong Linux hoặc macOS:

```shell
command -v java
command -v javac
```

Nếu `java` và `javac` đến từ hai thư mục JDK khác nhau, hãy sắp xếp lại `PATH` để cả hai lệnh sử dụng cùng một bộ công cụ phù hợp với dự án.

## 2. Tạo và biên dịch chương trình Java đầu tiên

Trước tiên, tạo một thư mục làm việc. Trong ví dụ này, mã nguồn nằm trong `src`, còn kết quả biên dịch nằm trong `out`:

```text
hello-java/
├── src/
│   └── Hello.java
└── out/
```

Mở Terminal tại thư mục `hello-java`. Tạo hai thư mục nếu chúng chưa tồn tại.

PowerShell:

```powershell
New-Item -ItemType Directory -Force src, out | Out-Null
```

Linux hoặc macOS:

```shell
mkdir -p src out
```

Tạo tệp `src/Hello.java` với nội dung:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Java!");
    }
}
```

Tên tệp là `Hello.java` vì lớp public cấp cao nhất có tên `Hello`. Trong Java, tên tệp phải khớp chính xác với tên lớp public đó, bao gồm chữ hoa và chữ thường.

Phương thức `main` là điểm bắt đầu quen thuộc của một ứng dụng Java độc lập:

```java
public static void main(String[] args)
```

- `public`: JVM có thể truy cập phương thức này để khởi chạy chương trình.
- `static`: JVM gọi phương thức mà không cần tạo đối tượng từ lớp `Hello`.
- `void`: phương thức không trả về giá trị.
- `String[] args`: mảng chứa các đối số dòng lệnh truyền cho chương trình.

### Biên dịch bằng `javac`

Từ thư mục gốc `hello-java`, chạy:

```shell
javac -encoding UTF-8 -d out src/Hello.java
```

Ý nghĩa các thành phần:

- `javac`: gọi trình biên dịch Java.
- `-encoding UTF-8`: đọc tệp mã nguồn theo bảng mã UTF-8. Tùy chọn này hữu ích khi mã nguồn có tiếng Việt hoặc ký tự ngoài ASCII.
- `-d out`: đặt các tệp `.class` được tạo ra trong thư mục `out`.
- `src/Hello.java`: đường dẫn đến tệp mã nguồn cần biên dịch.

Nếu biên dịch thành công, `javac` thường không in thông báo nào. Kiểm tra thư mục `out`, bạn sẽ thấy:

```text
out/
└── Hello.class
```

`Hello.class` chứa bytecode mà JVM có thể nạp. Đây không phải mã nguồn Java để tiếp tục chỉnh sửa trực tiếp.

### Chạy bằng `java`

Tiếp tục đứng tại thư mục `hello-java`, chạy:

```shell
java -cp out Hello
```

Kết quả:

```text
Xin chào Java!
```

Ở đây:

- `java` khởi chạy môi trường thực thi Java.
- `-cp out` đặt thư mục `out` vào classpath để JVM tìm các lớp đã biên dịch.
- `Hello` là tên lớp cần khởi chạy.

Tên lớp được truyền cho `java` không có phần mở rộng `.class`, cũng không phải đường dẫn `out/Hello.class`. JVM tìm lớp dựa trên tên lớp và classpath.

Khi sửa `Hello.java`, bạn phải biên dịch lại trước khi chạy để chương trình sử dụng bytecode mới. Nếu lệnh biên dịch thất bại nhưng thư mục `out` còn tệp `.class` từ lần trước, lệnh chạy sau đó có thể vô tình chạy phiên bản cũ. Khi cần kiểm tra chắc chắn, hãy xóa hoặc tạo lại thư mục đầu ra rồi biên dịch lại.

## 3. Biên dịch và chạy lớp có khai báo package

Trong ứng dụng thực tế, các lớp thường được đặt trong package để tổ chức mã nguồn và tránh trùng tên. Khai báo package ở đầu tệp quyết định tên đầy đủ của lớp.

Tạo tệp `src/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Chương trình nằm trong package com.example.app");
    }
}
```

Cấu trúc thư mục nguồn tương ứng:

```text
src/
└── com/
    └── example/
        └── app/
            └── Main.java
```

Từ thư mục gốc dự án, biên dịch:

```shell
javac -encoding UTF-8 -d out src/com/example/app/Main.java
```

Sau khi biên dịch, cấu trúc đầu ra là:

```text
out/
└── com/
    └── example/
        └── app/
            └── Main.class
```

Tùy chọn `-d out` yêu cầu trình biên dịch tạo cấu trúc thư mục package trong `out`. Khi chạy, dùng tên đầy đủ của lớp, gồm package và tên lớp:

```shell
java -cp out com.example.app.Main
```

Class path phải trỏ đến **thư mục gốc của cây package** là `out`, không trỏ thẳng vào `out/com/example/app`. JVM sẽ ghép tên đầy đủ `com.example.app.Main` với classpath để tìm `com/example/app/Main.class`.

## 4. Biên dịch nhiều lớp có quan hệ với nhau

Một chương trình thường gồm nhiều lớp. Khi một lớp sử dụng lớp khác, trình biên dịch phải tìm được mã nguồn hoặc bytecode của lớp được tham chiếu.

Giả sử ứng dụng có ba lớp sau.

Tệp `src/com/example/model/User.java`:

```java
package com.example.model;

public class User {
    private final String name;

    public User(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

Tệp `src/com/example/service/GreetingService.java`:

```java
package com.example.service;

import com.example.model.User;

public class GreetingService {
    public String greet(User user) {
        return "Xin chào, " + user.getName() + "!";
    }
}
```

Tệp `src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.model.User;
import com.example.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        User user = new User("Lan");
        GreetingService service = new GreetingService();
        System.out.println(service.greet(user));
    }
}
```

### Cách 1: liệt kê các tệp nguồn

Bạn có thể truyền tất cả tệp cần biên dịch vào cùng một lệnh:

```shell
javac -encoding UTF-8 -d out \
  src/com/example/model/User.java \
  src/com/example/service/GreetingService.java \
  src/com/example/app/Main.java
```

Ký tự `\` ở cuối dòng là cách nối dòng trong shell Linux/macOS. Trong PowerShell, có thể viết lệnh trên thành một dòng hoặc dùng dấu backtick để nối dòng. Việc truyền ba đường dẫn trên một dòng hoạt động trên cả hai môi trường:

```shell
javac -encoding UTF-8 -d out src/com/example/model/User.java src/com/example/service/GreetingService.java src/com/example/app/Main.java
```

Chạy lớp chính:

```shell
java -cp out com.example.app.Main
```

Kết quả:

```text
Xin chào, Lan!
```

### Cách 2: khai báo nơi tìm mã nguồn bằng `-sourcepath`

Khi dự án có nhiều tệp, bạn có thể chỉ định thư mục gốc mã nguồn để `javac` tìm các lớp phụ thuộc cần thiết:

```shell
javac -encoding UTF-8 -sourcepath src -d out src/com/example/app/Main.java
```

`-sourcepath src` cho trình biên dịch biết rằng mã nguồn được tổ chức bên dưới thư mục `src`. Khi biên dịch `Main.java`, `javac` có thể tìm `User.java` và `GreetingService.java` theo package tương ứng.

`-sourcepath` chỉ chỉ ra nơi tìm **mã nguồn**. Nó không thay thế classpath dùng để tìm các lớp đã biên dịch hoặc thư viện JAR. Khi dự án sử dụng thư viện bên ngoài, bạn vẫn cần cấu hình classpath phù hợp.

## 5. Hiểu và sử dụng classpath

Classpath là danh sách vị trí mà trình biên dịch hoặc JVM tìm kiếm lớp và tài nguyên. Một mục trong classpath thường là:

- Thư mục gốc chứa các thư mục package và tệp `.class`.
- Tệp JAR chứa lớp đã biên dịch và tài nguyên.

Tùy chọn `-cp` (viết đầy đủ là `-classpath`) dùng để chỉ định classpath cho một lần biên dịch hoặc chạy. Đây là cách rõ ràng để khai báo các phụ thuộc của từng lệnh.

### Dùng JAR khi biên dịch

Giả sử thư viện bên ngoài nằm tại `lib/example-library.jar` và mã nguồn của bạn gọi các lớp trong thư viện đó. Hãy thêm JAR vào classpath khi biên dịch:

```shell
javac -encoding UTF-8 -cp "lib/example-library.jar" -d out src/com/example/app/Main.java
```

Nếu ứng dụng còn có mã nguồn nội bộ trong `src`, bạn có thể kết hợp `-sourcepath`:

```shell
javac -encoding UTF-8 -sourcepath src -cp "lib/example-library.jar" -d out src/com/example/app/Main.java
```

### Dùng JAR khi chạy

JVM cũng cần tìm thấy thư viện tại thời điểm chạy. Classpath khi chạy phải có thư mục chứa bytecode của ứng dụng và các JAR mà ứng dụng sử dụng.

Trên Windows, dấu phân cách giữa các mục classpath là dấu chấm phẩy `;`:

```powershell
java -cp "out;lib/example-library.jar" com.example.app.Main
```

Trên Linux và macOS, dấu phân cách là dấu hai chấm `:`:

```shell
java -cp "out:lib/example-library.jar" com.example.app.Main
```

Nếu có nhiều JAR trong một thư mục, Java hỗ trợ ký tự đại diện `*` để đưa các JAR trực tiếp trong thư mục đó vào classpath:

Windows:

```powershell
java -cp "out;lib/*" com.example.app.Main
```

Linux hoặc macOS:

```shell
java -cp "out:lib/*" com.example.app.Main
```

Ký tự `*` ở đây áp dụng cho các tệp JAR trong `lib`, không tự tìm JAR trong mọi thư mục con.

Khi đã chỉ định `-cp`, hãy khai báo đầy đủ những vị trí cần thiết cho lệnh đó. Không nên dựa vào một biến `CLASSPATH` toàn cục khó kiểm soát, vì nó có thể khiến chương trình chạy được trên máy này nhưng thất bại trên máy khác.

## 6. Một số tùy chọn `javac` hữu ích

Các tùy chọn sau thường xuất hiện trong lệnh biên dịch:

| Tùy chọn | Công dụng |
|---|---|
| `-d <dir>` | Đặt các tệp `.class` vào thư mục đầu ra. |
| `-cp <path>` | Khai báo nơi tìm các lớp đã biên dịch và thư viện. |
| `-sourcepath <path>` | Khai báo nơi tìm các tệp mã nguồn phụ thuộc. |
| `-encoding UTF-8` | Chọn bảng mã dùng để đọc mã nguồn. |
| `-Xlint:all` | Yêu cầu trình biên dịch hiển thị thêm các cảnh báo phổ biến. |
| `--release <version>` | Biên dịch theo phiên bản Java mục tiêu, gồm cả giới hạn API của phiên bản đó. |

Ví dụ, nếu đang dùng JDK mới nhưng muốn tạo bytecode và chỉ sử dụng API của Java 17:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/app/Main.java
```

Tùy chọn `--release` có từ JDK 9. Phiên bản mục tiêu phải được JDK đang dùng hỗ trợ. Việc chọn phiên bản mục tiêu cũng cần thống nhất với các thư viện phụ thuộc và môi trường triển khai.

## 7. Đóng gói lớp đã biên dịch thành JAR có thể chạy

Sau khi có các tệp `.class`, bạn có thể dùng công cụ `jar` trong JDK để đóng gói chúng. Với ví dụ có lớp chính `com.example.app.Main`, chạy lệnh sau từ thư mục dự án:

```shell
jar --create --file app.jar --main-class com.example.app.Main -C out .
```

Ý nghĩa:

- `--create`: tạo một tệp JAR mới.
- `--file app.jar`: đặt tên tệp đầu ra là `app.jar`.
- `--main-class com.example.app.Main`: khai báo lớp chính trong manifest của JAR.
- `-C out .`: chuyển đến thư mục `out` rồi thêm nội dung của thư mục đó vào JAR.

Chạy ứng dụng:

```shell
java -jar app.jar
```

Khi dùng `-jar`, JVM đọc lớp chính từ manifest của JAR. Một JAR thông thường chỉ chứa những gì bạn đã đóng gói; lệnh trên không tự gom các thư viện bên ngoài vào trong JAR. Nếu ứng dụng phụ thuộc vào JAR khác, bạn cần đóng gói các phụ thuộc theo một cách phù hợp hoặc khai báo đường dẫn phụ thuộc trong manifest. Đây là một trong những công việc mà build tool thường tự động hóa.

## 8. Chạy trực tiếp tệp nguồn với `java`

Từ Java 11, lệnh `java` hỗ trợ chế độ chạy trực tiếp một tệp nguồn:

```shell
java src/Hello.java
```

Ở chế độ này, bạn không cần gọi `javac` riêng cho ví dụ đơn giản. Lệnh `java` biên dịch và chạy chương trình từ tệp nguồn trong một thao tác. Đây là cách nhanh để thử một đoạn mã độc lập.

Tuy nhiên, khi cần quan sát rõ bước biên dịch, tạo thư mục bytecode, tổ chức package, quản lý nhiều tệp nguồn hoặc cấu hình phụ thuộc, hãy dùng quy trình `javac` rồi `java` như các phần trước. Chế độ chạy tệp nguồn không làm mất đi các yêu cầu về phiên bản JDK, package và thư viện mà chương trình sử dụng.

## 9. Đọc lỗi thường gặp

Khi biên dịch hoặc chạy chương trình, hãy xác định lỗi xuất hiện ở bước nào. Lỗi do `javac` thường liên quan đến mã nguồn, đường dẫn nguồn hoặc phụ thuộc lúc biên dịch. Lỗi do `java` thường liên quan đến classpath, lớp chính, phiên bản bytecode hoặc phụ thuộc lúc chạy.

| Thông báo hoặc biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `javac` không được nhận diện là lệnh | Chưa cài JDK hoặc thư mục `bin` của JDK chưa có trong `PATH`. | Kiểm tra JDK, `JAVA_HOME`, `PATH` và chạy lại `javac -version`. |
| `error: file not found` | Đường dẫn tệp nguồn sai hoặc Terminal đang đứng ở thư mục khác. | Chạy lệnh từ thư mục dự án và kiểm tra đường dẫn tương đối. |
| `class ... is public, should be declared in a file named ...` | Tên tệp không khớp tên lớp public. | Đổi tên tệp hoặc lớp để chúng khớp chính xác. |
| `cannot find symbol` hoặc `package ... does not exist` | Thiếu tệp nguồn, thiếu thư viện hoặc classpath chưa đúng. | Kiểm tra import, danh sách tệp biên dịch, `-sourcepath` và `-cp`. |
| `Could not find or load main class` | JVM không tìm thấy lớp cần chạy. | Kiểm tra classpath, tên đầy đủ của lớp và cấu trúc thư mục đầu ra. |
| `NoClassDefFoundError` | Một lớp cần thiết không có trên classpath tại thời điểm chạy, hoặc lớp không thể khởi tạo do lỗi trước đó. | Kiểm tra classpath lúc chạy và nguyên nhân gốc trong stack trace. |
| `Main method not found` | Lớp được gọi không có phương thức khởi chạy với chữ ký phù hợp. | Kiểm tra `public static void main(String[] args)` và tên lớp đang chạy. |
| `UnsupportedClassVersionError` | Runtime đang dùng không hỗ trợ phiên bản bytecode đã biên dịch. | Dùng JDK/runtime tương thích hoặc biên dịch với `--release` phù hợp. |
| Ký tự tiếng Việt hiển thị sai | Mã nguồn hoặc Terminal đang dùng bảng mã không thống nhất. | Lưu tệp bằng UTF-8, biên dịch với `-encoding UTF-8` và kiểm tra cấu hình Terminal. |

Một số nguyên tắc giúp tìm lỗi nhanh hơn:

1. Đọc thông báo lỗi đầu tiên và vị trí dòng được chỉ ra. Những lỗi phía sau đôi khi chỉ là hệ quả của lỗi đầu tiên.
2. Kiểm tra thư mục hiện tại trước khi sửa mã nguồn. Đường dẫn tương đối được tính từ thư mục mà Terminal đang đứng.
3. Phân biệt classpath lúc biên dịch và classpath lúc chạy. Một JAR có thể đã được `javac` nhìn thấy nhưng lại thiếu trong lệnh `java`.
4. Kiểm tra phiên bản của cả `java` và `javac` khi gặp lỗi tương thích bytecode.
5. Nếu nghi ngờ đang chạy bytecode cũ, xóa thư mục đầu ra, biên dịch lại và chạy lại.

## 10. Thói quen tốt khi làm việc bằng dòng lệnh

- **Chạy lệnh từ thư mục gốc dự án.** Khi đó các đường dẫn như `src/...`, `out` và `lib/...` có ý nghĩa nhất quán.
- **Tách mã nguồn và kết quả biên dịch.** Đặt mã nguồn trong `src`, bytecode trong `out` hoặc `build`, để dễ kiểm tra và làm sạch.
- **Biên dịch lại sau khi sửa mã nguồn.** Lệnh `java` chỉ thực thi bytecode hiện có; nó không tự biết tệp `.java` vừa được thay đổi khi bạn chạy theo cách `java -cp ... ClassName`.
- **Giữ classpath tường minh.** Ghi rõ thư mục đầu ra và thư viện cần thiết trong lệnh để người khác có thể tái hiện cách chạy.
- **Đồng bộ phiên bản Java.** Phiên bản JDK dùng để biên dịch phải phù hợp với phiên bản runtime ở nơi chương trình được chạy.
- **Không xem `.class` là mã nguồn.** Khi cần thay đổi hành vi, hãy sửa `.java` rồi biên dịch lại.
- **Không đưa đầu ra biên dịch vào quản lý phiên bản nếu không có lý do cụ thể.** Thư mục `out` thường là kết quả có thể tạo lại từ mã nguồn và có thể được loại khỏi Git.
- **Đặt dấu ngoặc kép quanh đường dẫn có khoảng trắng.** Ví dụ: `javac -d "build output" src/Hello.java`.

## 11. Mối liên hệ với build tool

Tự gọi `javac`, `java` và `jar` giúp bạn hiểu những bước cơ bản mà một dự án Java cần thực hiện. Khi dự án chỉ có một vài lớp, các lệnh thủ công có thể đủ dùng. Khi số lượng lớp, thư viện, môi trường và tác vụ tăng lên, việc ghi nhớ và chạy thủ công từng lệnh trở nên khó duy trì.

Build tool như Gradle hoặc Maven tự động hóa những công việc này. Tùy cấu hình dự án, build tool có thể:

- Xác định thư mục mã nguồn và tài nguyên.
- Phát hiện các lớp cần biên dịch và thứ tự phụ thuộc.
- Tải và đưa thư viện vào classpath.
- Chọn phiên bản Java hoặc cấu hình tương thích bytecode.
- Tạo thư mục đầu ra, JAR hoặc các gói phân phối khác.
- Chạy kiểm thử và báo cáo kết quả.

Khi một build tool báo lỗi biên dịch, kiến thức về `javac`, classpath, package và bytecode giúp bạn hiểu vấn đề nằm ở mã nguồn hay cấu hình build. Khi một ứng dụng chạy được trong IDE nhưng không chạy được từ Terminal, hãy kiểm tra lại lệnh chạy, thư mục làm việc, classpath và phiên bản Java. Đó cũng là những thành phần mà IDE và build tool phải cấu hình phía sau giao diện của chúng.

## 12. Bài thực hành

Thực hiện các bước sau trong một thư mục dự án mới:

1. Chạy `java -version` và `javac -version`, ghi lại phiên bản hiển thị.
2. Tạo `src/Hello.java` với một lớp có phương thức `main` in ra một câu tiếng Việt.
3. Tạo thư mục `out`, sau đó biên dịch bằng `javac -encoding UTF-8 -d out src/Hello.java`.
4. Kiểm tra rằng `out/Hello.class` đã được tạo.
5. Chạy bằng `java -cp out Hello` và đối chiếu kết quả.
6. Chuyển lớp `Hello` vào package `com.example.app`, cập nhật vị trí tệp và biên dịch lại.
7. Chạy lớp bằng tên đầy đủ `com.example.app.Hello` với classpath trỏ đến thư mục gốc của bytecode.
8. Tạo thêm một lớp phụ thuộc, biên dịch cả hai lớp hoặc thử dùng `-sourcepath`.
9. Cố ý bỏ classpath khi chạy, quan sát lỗi, sau đó khôi phục classpath đúng.
10. Đóng gói các lớp thành JAR có khai báo lớp chính và chạy bằng `java -jar`.

Sau bài thực hành, bạn cần giải thích được vì sao phải có JDK để biên dịch, `javac` tạo ra tệp gì, `java` tìm lớp thông qua classpath như thế nào, tên package liên quan ra sao đến cấu trúc thư mục và vì sao một thư viện cần có mặt ở cả bước biên dịch lẫn bước chạy.
