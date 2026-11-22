# Biên dịch và chạy chương trình đầu tiên ngoài IDE

## Bạn sẽ làm được gì?

Sau bài học này, bạn có thể tự tạo một chương trình Java 17+ bằng trình soạn thảo văn bản, dùng terminal để **biên dịch bằng `javac`**, chạy bằng `java`, hiểu vì sao phải cấu hình classpath và xử lý các lỗi cơ bản. Bạn cũng sẽ biết cách biên dịch mã có `package` và, như một bước mở rộng, đóng gói chương trình thành JAR có thể chạy.

Bài này tập trung vào **thao tác thực tế ngoài IDE**: bạn không cần IntelliJ IDEA, Eclipse hay VS Code để hoàn thành. Một terminal, một JDK và trình soạn thảo lưu được file văn bản UTF-8 là đủ.

## 1. Quy trình ba bước

```text
Viết mã nguồn                 Biên dịch                    Thực thi
src/HelloApp.java --javac--> out/HelloApp.class --java--> JVM chạy main(...)
                       ^                                  |
                Lệnh từ JDK                        Hiển thị kết quả
```

- **`HelloApp.java`** chứa source code dễ đọc, là thứ bạn tự sửa.
- **`javac`** (Java compiler trong JDK) kiểm tra cú pháp/kiểu và dịch source thành `.class`, tức **JVM bytecode**, không phải file mã máy chạy trực tiếp.
- **`java`** là launcher khởi động JVM, nạp class file và gọi điểm vào ứng dụng. JVM có thể dùng interpreter và các cơ chế như JIT khi phù hợp.
- **`out/`** là thư mục output do bạn chọn với `-d out`; đây không phải tên thư mục mà Java bắt buộc.

Bạn **không cần biên dịch lại** chỉ để chạy nhiều lần nếu source và dependency không đổi. Khi sửa source, hãy chạy `javac` lại để cập nhật class file trước khi chạy.

## 2. Chuẩn bị JDK và terminal

Hãy cài **JDK 17 hoặc mới hơn**, chẳng hạn JDK 17 hoặc 21, và mở terminal:

- Windows: PowerShell, Command Prompt hoặc Windows Terminal.
- macOS/Linux: Terminal với Bash, Zsh hoặc shell thông dụng.

Kiểm tra:

```bash
java -version
javac -version
```

Kết quả thực tế chứa **phiên bản, vendor và thông tin build** của JDK đang cài; ví dụ đầu ra của `javac -version` trên một JDK 21 có dạng `javac 21.0.x`. Đừng coi một phiên bản ví dụ là kết quả bắt buộc trên mọi máy.

Nếu **cả hai lệnh chạy được**, bạn đã có công cụ cần thiết. Nếu terminal báo không tìm được lệnh:

1. Xác nhận đã cài **JDK**, không chỉ một runtime thiếu `javac`.
2. Kiểm tra biến môi trường `PATH` có trỏ tới thư mục `bin` của JDK hay chưa.
3. Mở terminal mới sau khi thay đổi cấu hình môi trường.
4. Kiểm tra cấu hình JDK độc lập của IDE, Gradle hoặc Maven nếu bạn có dùng những công cụ đó.

Trên PowerShell, xem file thực thi nào đang được tìm thấy:

```powershell
Get-Command java
Get-Command javac
```

Trên Bash/Zsh:

```bash
command -v java
command -v javac
```

Biến `JAVA_HOME` thường được build tool dùng để chọn JDK, nhưng lệnh `java`/`javac` trong terminal còn chịu ảnh hưởng của `PATH`. Không mặc định chúng luôn trỏ về cùng một bản cài.

### 2.1 Mở đúng thư mục dự án

Tạo thư mục `java-terminal-demo` ở vị trí bạn có quyền ghi và **mở terminal trong thư mục đó**. Ta sẽ có cấu trúc:

```text
java-terminal-demo/
└── src/
    └── HelloApp.java
```

Tạo thư mục `src` bằng một trong hai lệnh:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force src | Out-Null
```

**Bash/Zsh:**

```bash
mkdir -p src
```

Nếu đang ở sai thư mục, dùng `cd` tới `java-terminal-demo`. Để xác nhận thư mục hiện tại: `Get-Location` (PowerShell) hoặc `pwd` (Bash/Zsh). Các đường dẫn `src/` và `out/` trong bài là **đường dẫn tương đối so với thư mục hiện tại**.

## 3. Chương trình Java đầu tiên: tạo, biên dịch, chạy

Dùng bất kỳ editor văn bản nào để tạo đúng file **`src/HelloApp.java`** và lưu bằng mã hóa **UTF-8**:

```java
public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Xin chào từ terminal!");
        System.out.println("Số đối số: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
```

Hiểu nhanh về code:

- `public class HelloApp` khai báo một lớp public. Theo quy tắc đặt tên file với top-level public class, file cần có tên **`HelloApp.java`** đúng chữ hoa/chữ thường.
- `public static void main(String[] args)` là chữ ký điểm vào quen thuộc được Java launcher hỗ trợ từ lâu; `args` chứa các đối số bạn truyền khi chạy, **không chứa** tên lớp.
- `System.out.println(...)` in ra standard output và xuống dòng.
- Vòng `for` in từng phần tử của `args`; không có đối số thì vòng lặp không chạy.

### 3.1 Biên dịch bằng `javac`

Đứng ở **thư mục gốc `java-terminal-demo`**, chạy:

```bash
javac -encoding UTF-8 -d out src/HelloApp.java
```

Lệnh biên dịch thành công thường **không in gì** ra terminal. Kiểm tra cấu trúc mới:

```text
java-terminal-demo/
├── src/
│   └── HelloApp.java
└── out/
    └── HelloApp.class
```

Ý nghĩa từng phần:

| Phần lệnh | Ý nghĩa |
| --- | --- |
| `javac` | Gọi trình biên dịch Java trong JDK |
| `-encoding UTF-8` | Đọc source theo UTF-8, tránh phụ thuộc charset mặc định của một số môi trường |
| `-d out` | Đặt class file được tạo trong thư mục output `out`, theo cấu trúc package |
| `src/HelloApp.java` | Đường dẫn đến tệp source cần biên dịch |

`javac` **có thể tự tạo** thư mục output `out` nếu chưa tồn tại, nhưng thư mục cha phải khả dụng và có quyền ghi. Thông thường exit code 0 nghĩa là compiler hoàn tất thành công; lỗi cú pháp/kiểu dẫn đến diagnostic và exit code khác 0.

### 3.2 Chạy bằng `java`

```bash
java -cp out HelloApp
```

Đầu ra chính xác của code trên khi **không truyền đối số**:

```text
Xin chào từ terminal!
Số đối số: 0
```

Chạy lần nữa với **hai đối số**:

```bash
java -cp out HelloApp Lan Java
```

Đầu ra của code trên:

```text
Xin chào từ terminal!
Số đối số: 2
args[0] = Lan
args[1] = Java
```

Giải thích:

- `-cp` (viết đầy đủ `-classpath` hoặc `--class-path`) đặt **classpath** để Java launcher tìm class.
- `out` là thư mục gốc chứa `HelloApp.class`, không phải đường dẫn tới file `.class`.
- `HelloApp` là **tên lớp** cần chạy; không có hậu tố `.java` hoặc `.class`.
- `Lan Java` là hai đối số tách theo khoảng trắng. Nếu muốn truyền **một** đối số chứa khoảng trắng, dùng dấu nháy: `"Lan Java"`.

**Lưu ý khi kiểm tra output tiếng Việt:** source đã được compiler đọc UTF-8 nhờ `-encoding UTF-8`, nhưng cách terminal thể hiện ký tự còn phụ thuộc font/encoding và cấu hình console. Nếu nhìn thấy ký tự lỗi dù chương trình chạy, hãy kiểm tra khả năng hiển thị Unicode của terminal.

### 3.3 Một vòng sửa → biên dịch → chạy

Đổi dòng đầu trong source thành:

```java
System.out.println("Chạy Java không cần IDE!");
```

Sau đó chạy lại **cả hai bước**:

```bash
javac -encoding UTF-8 -d out src/HelloApp.java
java -cp out HelloApp
```

Đầu ra mới (không truyền đối số):

```text
Chạy Java không cần IDE!
Số đối số: 0
```

Nếu bạn chỉ sửa `.java` rồi chạy `java` mà **không biên dịch lại**, JVM vẫn có thể chạy **class file cũ**, nên chưa thấy thay đổi. Đây là lỗi rất thường gặp khi rời IDE, vì IDE vốn tự động làm bước compile trong nhiều workflow.

## 4. Điều gì xảy ra đằng sau hai lệnh?

### `javac` thực hiện bước compile-time

Compiler đọc source, phân tích cú pháp, xác định tên/kiểu và tạo class file. Với đoạn mã hợp lệ, bạn sẽ có `HelloApp.class` chứa bytecode cùng thông tin lớp và phương thức. Những lỗi như thiếu dấu `;`, không khớp kiểu, gọi tên phương thức không tồn tại… thường được báo ở bước này.

### `java` thực hiện bước runtime

Launcher tạo JVM, cung cấp classpath, tìm/nạp lớp `HelloApp` và gọi `main`. Từ đó chương trình tương tác với thư viện chuẩn, hệ điều hành và terminal. Các lỗi như thiếu đối số, phép toán không hợp lệ, lỗi đọc file hay cấu hình tài nguyên thường chỉ biểu hiện khi chạy.

Cách phân biệt hai lệnh:

```text
javac ...    ==> Source (.java) thành bytecode (.class)
java ...     ==> JVM nạp class và chạy phương thức main
```

Thành công ở bước `javac` **không đảm bảo** mọi đường chạy của chương trình đều đúng. Ví dụ, code truy cập `args[0]` mà không kiểm tra độ dài có thể biên dịch bình thường nhưng ném `ArrayIndexOutOfBoundsException` khi chạy không có đối số.

## 5. Xem bytecode đầu tiên bằng `javap`

Một công cụ hữu ích có sẵn trong JDK là `javap`:

```bash
javap -classpath out HelloApp
javap -c -classpath out HelloApp
```

- Lệnh đầu hiển thị mô tả lớp cùng chữ ký thành viên được chọn, ví dụ constructor và `main`.
- `-c` hiển thị các chỉ thị bytecode của các method có mã, như `getstatic`, `invokevirtual`, `arraylength`, `iinc` hoặc những chỉ thị nhảy.
- Output chi tiết, thứ tự chỉ thị và constant-pool index là kết quả của compiler/class file thực tế; **không nên học thuộc offset cố định**.

`javap` đọc class file đã biên dịch; nó **không chạy `main`** và **không làm nhiệm vụ JIT**. Dùng nó để hiểu ranh giới từ mã nguồn Java sang bytecode.

## 6. Khi ứng dụng có package và nhiều tệp

Trong project thật, Java class thường nằm trong một `package`, thay vì default package. Đây là nơi cần hiểu rõ sự khác nhau giữa **đường dẫn source**, **cấu trúc output** và **fully qualified class name**.

Ta tạo cấu trúc:

```text
java-terminal-demo/
└── src/
    └── com/
        └── example/
            ├── GreetingApp.java
            └── text/
                └── Greeting.java
```

Bạn có thể tạo thư mục cha bằng trình quản lý file hoặc lệnh tương ứng.

**File `src/com/example/text/Greeting.java`:**

```java
package com.example.text;

public class Greeting {
    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

**File `src/com/example/GreetingApp.java`:**

```java
package com.example;

import com.example.text.Greeting;

public class GreetingApp {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";
        System.out.println(Greeting.message(name));
    }
}
```

Biên dịch **hai source file** trong một lời gọi:

```bash
javac -encoding UTF-8 -d out src/com/example/text/Greeting.java src/com/example/GreetingApp.java
```

Lệnh dùng dấu cách để ngăn các path; nó dùng được trong PowerShell, Bash hoặc Command Prompt khi project nằm trong thư mục có path không chứa dấu cách. Nếu path chứa dấu cách, bao từng đường dẫn trong dấu nháy kép.

Sau biên dịch, `out` có:

```text
out/
└── com/
    └── example/
        ├── GreetingApp.class
        └── text/
            └── Greeting.class
```

Chạy đúng **tên lớp đầy đủ**:

```bash
java -cp out com.example.GreetingApp Minh
```

Đầu ra:

```text
Xin chào, Minh!
```

**Điểm quan trọng:**

- `package com.example;` là phần của tên lớp. Launcher cần `com.example.GreetingApp`, không chỉ `GreetingApp`.
- `-cp out` trỏ tới **gốc cây package**. Không dùng `-cp out/com/example` để chạy `com.example.GreetingApp`.
- `-d out` hướng dẫn compiler tạo cấu trúc thư mục tương ứng package.
- `import` giúp source tham chiếu tên lớp thuận tiện; nó không tự thêm JAR hay file vào classpath runtime.
- Hai lớp có thể biên dịch cùng lúc hoặc được cung cấp qua sourcepath/classpath phù hợp; ở ví dụ này ta truyền cả hai source file để lệnh rõ ràng và tái lập được.

### 6.1 Phân biệt `classpath` của compiler và runtime

Giả sử `Greeting.class` đã được biên dịch vào `out`, còn bạn muốn biên dịch lại riêng `GreetingApp.java`. Có thể dùng:

```bash
javac -encoding UTF-8 -cp out -d out src/com/example/GreetingApp.java
java -cp out com.example.GreetingApp Minh
```

Ở đây:

- `javac -cp out` cho compiler biết nơi tìm **các dependency đã biên dịch**.
- `java -cp out` cho JVM biết nơi tìm class **khi chạy**.

Nếu compile-time và runtime classpath khác nhau, mã có thể build thành công rồi gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` lúc chạy tùy nguyên nhân và cơ chế nạp lớp.

Với nhiều mục trong classpath, dấu phân cách phụ thuộc hệ điều hành:

- macOS/Linux: `-cp "out:libs/example.jar"`.
- Windows: `-cp "out;libs/example.jar"`.

Đây là **dấu phân cách giữa các entry trong classpath**, không phải dấu phân cách thư mục. Với bài đầu tiên chỉ có `out` thì không cần xử lý khác biệt này.

## 7. Mở rộng: tạo JAR và chạy không cần chỉ định classpath

JAR là định dạng lưu trữ, thường chứa class file/tài nguyên. Có thể đóng gói bài `GreetingApp` thành **executable JAR** có thông tin `Main-Class` trong manifest.

Sau khi biên dịch thành công hai file ở mục 6, tạo thư mục `build`:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force build | Out-Null
```

**Bash/Zsh:**

```bash
mkdir -p build
```

Đóng gói bằng công cụ `jar` có sẵn trong JDK 17+:

```bash
jar --create --file build/greeting-app.jar --main-class com.example.GreetingApp -C out .
```

Giải thích:

- `--create` tạo JAR.
- `--file build/greeting-app.jar` xác định đường dẫn file JAR.
- `--main-class com.example.GreetingApp` ghi entry point vào manifest.
- `-C out .` yêu cầu `jar` chuyển tới `out` và đóng gói các file bên trong, không mang tiền tố `out/` vào đường dẫn của entry.

Chạy:

```bash
java -jar build/greeting-app.jar Minh
```

Đầu ra của ví dụ:

```text
Xin chào, Minh!
```

Lúc này launcher lấy tên lớp chính từ manifest; bạn không cần tự gõ `com.example.GreetingApp`. Nhưng **`java -jar` không tự tải dependency ngoài JAR**. Nếu ứng dụng dùng các thư viện bên ngoài, vẫn cần chiến lược đóng gói hoặc classpath phù hợp; mục này mới chỉ dùng hai class được gói chung.

Để xem nội dung JAR:

```bash
jar --list --file build/greeting-app.jar
```

Danh sách có manifest và class files; thứ tự các entry không nên được dùng làm điều kiện kiểm thử. Không nhầm **JAR có `Main-Class`** với mọi JAR thư viện: nhiều JAR chỉ cung cấp class, không có điểm vào để dùng `java -jar`.

## 8. Lỗi thường gặp và cách tự chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `javac: command not found` / `'javac' is not recognized` | Chưa có compiler trong môi trường hoặc `PATH` sai | Kiểm tra cài JDK và nơi chứa `bin/javac`; mở terminal mới |
| `error: file not found: src/HelloApp.java` | Sai thư mục hiện tại, sai tên file hoặc file chưa được lưu | Dùng `pwd`/`Get-Location`; xem thư mục `src` và tên file thực tế |
| `class HelloApp is public, should be declared in a file named HelloApp.java` | File và top-level public class không cùng tên | Đổi file thành `HelloApp.java` với chữ hoa đúng |
| `';' expected`, `cannot find symbol` | Lỗi cú pháp, tên biến/lớp hoặc tham chiếu không hợp lệ | Xem đường dẫn và số dòng mà compiler báo, sửa source rồi compile lại |
| `Could not find or load main class HelloApp` | Classpath sai hoặc tên lớp không đúng package | Kiểm tra `out/HelloApp.class`, dùng `java -cp out HelloApp` |
| `Could not find or load main class com.example.GreetingApp` | Chạy sai fully qualified name hoặc classpath root | Dùng `java -cp out com.example.GreetingApp`, kiểm tra cây `out/com/example` |
| `Main method not found in class ...` | Không có điểm vào hợp lệ cho dạng launcher đang sử dụng | Dùng `public static void main(String[] args)` trong ví dụ Java 17+ |
| `UnsupportedClassVersionError` | Class file biên dịch với mức JVM mới hơn runtime | Kiểm tra `java -version`, `javac -version`; dùng runtime phù hợp hoặc `--release` khi compile |
| `NoClassDefFoundError` | Thiếu một lớp/không thể hoàn tất nạp hoặc khởi tạo lớp cần thiết | Soát runtime classpath, dependency và nguyên nhân `Caused by` |
| Chạy ra **kết quả cũ** | Chưa biên dịch lại hoặc đang chạy class từ thư mục khác | Compile lại; kiểm tra path đầu ra và classpath của launcher |
| Ký tự tiếng Việt lỗi font | Console font/encoding không hỗ trợ hoặc file lưu sai encoding | Lưu source UTF-8; dùng `-encoding UTF-8`; điều chỉnh terminal Unicode |
| `Unable to access jarfile ...` | File JAR chưa tạo, sai đường dẫn hoặc thiếu quyền truy cập | Xem đường dẫn `build/greeting-app.jar`, build lại rồi chạy |

### 8.1 Đọc diagnostic của compiler

Giả sử bạn vô tình bỏ dấu `;`:

```java
public class Broken {
    public static void main(String[] args) {
        System.out.println("Hello")
    }
}
```

Chạy `javac Broken.java` có thể cho diagnostic chỉ vào dòng bị thiếu dấu `;` và báo `';' expected`. Số dòng/định dạng tùy JDK; điều cần nắm là **compiler không tạo ra một bản chương trình hợp lệ từ source đang sai**. Sửa lại:

```java
System.out.println("Hello");
```

sau đó compile lại.

### 8.2 Thứ tự đối số của `java` rất quan trọng

Đúng:

```bash
java -cp out HelloApp Lan
```

Sai về ý định:

```bash
java HelloApp -cp out
```

Trong lời gọi thứ hai, sau tên main class, `-cp` và `out` là **đối số của ứng dụng**, chứ không còn là tùy chọn launcher để đặt classpath. Nếu JVM không tìm được class trước đó thì chương trình vẫn lỗi.

Mẫu dễ nhớ là:

```text
java [tùy chọn JVM/launcher] -cp <classpath> <tên.lớp.đầy.đủ> [đối số ứng dụng]
```

Dấu ngoặc vuông trong dòng trên chỉ **phần tùy chọn trong mô tả cú pháp**, không gõ chúng vào lệnh thực tế.

### 8.3 Hiểu sự khác biệt giữa file path và class name

Với source `src/com/example/GreetingApp.java`:

- `javac ... src/com/example/GreetingApp.java` nhận **đường dẫn tệp source**.
- `java -cp out com.example.GreetingApp` nhận **tên nhị phân đầy đủ của lớp** và classpath root.
- `java -jar build/greeting-app.jar` nhận **đường dẫn tệp JAR**, sau đó tìm main class qua manifest.

Không tráo `.java`, `.class`, `.jar` hoặc tên lớp giữa các chế độ.

## 9. Những tùy chọn cần biết sau khi chạy được ví dụ

| Lệnh / tùy chọn | Mục đích |
| --- | --- |
| `javac -help` | Xem trợ giúp và các tùy chọn compiler hiện có |
| `java --help` | Xem cách chạy class, JAR, module hoặc source phù hợp phiên bản |
| `javac -d out ...` | Đặt root thư mục output của class |
| `javac -encoding UTF-8 ...` | Quy định charset đọc source |
| `javac --release 17 -d out ...` | Với JDK hỗ trợ, biên dịch source/API/bytecode hướng tới Java 17 |
| `javac -cp out ...` | Cho compiler tìm dependency đã biên dịch |
| `java -cp out ...` | Cho JVM tìm class tại runtime |
| `javap -c -classpath out ...` | Xem chỉ thị bytecode |
| `jar --create --file ...` | Tạo JAR |
| `java -jar ...` | Chạy executable JAR theo manifest |

Ví dụ khi dùng **JDK 21** để biên dịch nguồn cho runtime Java 17:

```bash
javac --release 17 -encoding UTF-8 -d out src/HelloApp.java
java -cp out HelloApp
```

`--release 17` giới hạn cả cú pháp, API Java platform và class-file target tới release được chỉ định; điều đó không bảo đảm một thư viện ngoài vẫn tương thích hoặc ứng dụng không có lỗi runtime. Đặc biệt, chạy compiler trên JDK cũ **không thể** chọn release mới hơn mức nó hỗ trợ.

**Source-file mode không thay thế bài luyện tập này.** Trên JDK phù hợp, lệnh như `java src/HelloApp.java` có thể biên dịch và thực thi một file source trực tiếp. Nhưng để hiểu quy trình ngoài IDE, hãy làm riêng `javac ...` và `java -cp ...` trước; đó là cách dễ quan sát đầu ra `.class`, classpath và tác động của việc sửa source.

## 10. Bài tập tự thực hành có đáp án kiểm chứng

### Bài tập 1: tính tổng hai số nguyên

Tạo file **`src/SumApp.java`**:

```java
public class SumApp {
    public static void main(String[] args) {
        int a = 7;
        int b = 12;
        System.out.println("Tổng = " + (a + b));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 -d out src/SumApp.java
java -cp out SumApp
```

Kết quả kỳ vọng:

```text
Tổng = 19
```

Câu hỏi: Nếu chỉ sửa `b` thành `20` rồi gọi ngay `java -cp out SumApp` mà chưa compile lại, tại sao kết quả vẫn có thể là `19`? Vì JVM dùng `SumApp.class` cũ. Sau khi biên dịch lại, kết quả mới là `Tổng = 27`.

### Bài tập 2: truyền một đối số có khoảng trắng

Dùng `HelloApp` ở mục 3, chạy:

```bash
java -cp out HelloApp "Nguyen Van A"
```

Nếu bạn vẫn dùng source ban đầu, output là:

```text
Xin chào từ terminal!
Số đối số: 1
args[0] = Nguyen Van A
```

Nếu đã sửa source như mục 3.3 và biên dịch lại, dòng đầu sẽ là `Chạy Java không cần IDE!`; hai dòng đối số không đổi. Đây là cách tự kiểm tra chính xác phiên bản class file đang được dùng.

### Bài tập 3: giải thích lỗi classpath

Sau khi compile `HelloApp` vào `out`, thử:

```bash
java -cp src HelloApp
```

Lệnh này thường không tìm được `HelloApp` vì `src` chứa file source chứ không chứa class file đã biên dịch. Sửa thành:

```bash
java -cp out HelloApp
```

Mấu chốt: classpath ở chế độ chạy lớp chỉ ra **nơi chứa bytecode và các phụ thuộc tại runtime**, không phải mặc định tìm mọi source code trong project.

### Bài tập 4: kiểm tra package

Biên dịch hai file trong mục 6, rồi thử gọi `java -cp out GreetingApp`. Hãy giải thích lỗi và viết lại lệnh đúng:

```bash
java -cp out com.example.GreetingApp
```

Đầu ra nếu không truyền tên:

```text
Xin chào, Java!
```

Lý do: package là thành phần của tên lớp; `GreetingApp` ở đây thực chất mang tên đầy đủ `com.example.GreetingApp`.

## 11. Checklist hoàn thành

- [ ] `java -version` và `javac -version` chạy được trong terminal.
- [ ] Tạo đúng `src/HelloApp.java` lưu UTF-8.
- [ ] Biên dịch bằng `javac -encoding UTF-8 -d out src/HelloApp.java` và thấy `out/HelloApp.class`.
- [ ] Chạy `java -cp out HelloApp`, xác nhận output không có đối số.
- [ ] Chạy với hai đối số và giải thích `args.length`.
- [ ] Sửa source, compile lại và thấy output mới.
- [ ] Dùng `javap -c` để biết class file chứa bytecode.
- [ ] Biên dịch/chạy `com.example.GreetingApp` bằng tên lớp đầy đủ.
- [ ] Tự xử lý một lỗi sai classpath/tên file mà không cần thao tác IDE.
- [ ] (Mở rộng) Tạo và chạy `build/greeting-app.jar`.

## Ghi nhớ

**`javac` nhận đường dẫn source để tạo bytecode; `java` nhận tên lớp cùng classpath để chạy bytecode trong JVM.** Khi tự thực hiện hai bước ngoài IDE, bạn nhìn rõ file nào được tạo, JVM đang tìm class ở đâu, đối số được truyền như thế nào và vì sao sửa code phải đi kèm biên dịch lại. Những kỹ năng này là nền tảng để sau này hiểu Gradle/Maven, lỗi dependency, khác biệt build-time/run-time và triển khai ứng dụng Java trên máy chủ.