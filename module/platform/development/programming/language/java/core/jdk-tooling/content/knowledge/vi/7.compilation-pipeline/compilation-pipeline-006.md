# Ghi class file

Khi biên dịch mã nguồn Java, `javac` tạo ra các tệp **class file** có phần mở rộng `.class`. Đây là các tệp nhị phân chứa bytecode và metadata mà Java Virtual Machine (JVM) sử dụng để nạp lớp, kiểm tra và thực thi chương trình.

Ví dụ, mã nguồn khai báo lớp `com.example.App` thường được biểu diễn trong class file có đường dẫn:

```text
com/example/App.class
```

Tệp `.class` không phải mã nguồn Java và cũng không phải tệp thực thi native dành riêng cho Windows, macOS hay Linux. Bytecode có thể chạy trên các hệ điều hành khác nhau nếu môi trường JVM tương thích với phiên bản class file, API và các phụ thuộc mà chương trình sử dụng.

## 1. Vai trò của class file trong pipeline biên dịch

Một quy trình Java cơ bản có thể mô tả như sau:

```text
Mã nguồn .java
      |
      v
javac: phân tích cú pháp, kiểm tra kiểu,
       phân giải phụ thuộc và biên dịch
      |
      v
Class file .class (bytecode + metadata)
      |
      v
JVM: nạp lớp, kiểm tra và liên kết
      |
      v
Thực thi chương trình
```

`javac` chịu trách nhiệm chuyển mã nguồn thành class file. Khi chạy chương trình, JVM tìm và nạp các class file cần thiết từ classpath hoặc module path. JVM có thể diễn giải bytecode hoặc biên dịch các đoạn mã nóng sang mã máy bằng JIT compiler.

Cần phân biệt:

- `.java`: tệp văn bản chứa mã nguồn do lập trình viên viết.
- `.class`: tệp nhị phân chứa định nghĩa lớp đã biên dịch.
- `.jar`: gói ZIP dùng để phân phối nhiều class file và tài nguyên cùng metadata.
- Mã máy: lệnh CPU được tạo trong quá trình thực thi/JIT hoặc được cung cấp bởi thư viện native.

Biên dịch thành công chỉ có nghĩa là compiler đã tạo được đầu ra theo cấu hình. Nó không tự bảo đảm rằng mọi dependency đều có mặt khi chạy hoặc logic ứng dụng hoạt động đúng.

## 2. Biên dịch và quan sát class file đầu tiên

Tạo tệp `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, class file!");
    }
}
```

Từ thư mục chứa tệp, chạy:

```sh
javac Hello.java
```

Nếu không có lỗi, thư mục hiện tại sẽ có thêm:

```text
Hello.java
Hello.class
```

Thông thường, `javac` không in thông báo khi biên dịch thành công. Có thể xem tệp đã được tạo bằng lệnh hệ điều hành:

```sh
ls -l Hello.class
```

Trên PowerShell:

```powershell
Get-Item .\Hello.class
```

Chạy chương trình:

```sh
java Hello
```

Kết quả:

```text
Hello, class file!
```

Lệnh `javac` nhận tên tệp nguồn có phần mở rộng `.java`; lệnh `java` nhận tên lớp để khởi chạy, không thêm phần mở rộng `.class`.

## 3. Vị trí ghi class file

Có hai cách phổ biến để xác định nơi `javac` ghi đầu ra.

### 3.1. Không dùng -d

Nếu không chỉ định `-d`, compiler thường đặt class file trong cùng thư mục với tệp nguồn tương ứng.

Ví dụ:

```text
project/
└── src/
    └── com/
        └── example/
            └── App.java
```

Biên dịch từ thư mục `project`:

```sh
javac src/com/example/App.java
```

Đầu ra mặc định nằm cạnh tệp nguồn:

```text
project/
└── src/
    └── com/
        └── example/
            ├── App.java
            └── App.class
```

Với cách này, nếu muốn chạy lớp có package `com.example`, classpath phải trỏ đến thư mục gốc của cấu trúc package, trong ví dụ là `src`:

```sh
java -cp src com.example.App
```

Cách biên dịch mặc định phù hợp với thử nghiệm nhỏ, nhưng dễ trộn mã nguồn và đầu ra. Với dự án thực tế, nên tách chúng thành các thư mục riêng.

### 3.2. Dùng -d để chọn thư mục đầu ra

Tùy chọn `-d` chỉ định thư mục gốc để ghi class file:

```sh
javac -d out src/com/example/App.java
```

Thư mục `out` phải tồn tại trước khi gọi `javac`. Compiler tạo các thư mục con tương ứng với package bên dưới thư mục này.

Trên macOS/Linux, có thể tạo thư mục bằng:

```sh
mkdir -p out
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

Sau khi biên dịch, cấu trúc sẽ có dạng:

```text
project/
├── src/
│   └── com/example/App.java
└── out/
    └── com/
        └── example/
            └── App.class
```

Chạy lớp bằng cách đặt thư mục gốc đầu ra lên classpath:

```sh
java -cp out com.example.App
```

Nếu lớp không thuộc package nào (default package), class file được ghi trực tiếp ở thư mục đầu ra, ví dụ `out/Hello.class`.

**Điểm cần nhớ:** `-d` là thư mục gốc chứa bytecode, không phải đường dẫn của một tệp `.class`. Với package `com.example`, compiler tự tạo đường dẫn `com/example` bên dưới thư mục đầu ra.

## 4. Một tệp nguồn có thể tạo nhiều class file

Không có quy tắc một tệp `.java` luôn tương ứng với đúng một tệp `.class`. Một tệp nguồn có thể khai báo nhiều lớp cấp cao nhất, lớp lồng nhau, enum hoặc record; compiler có thể tạo nhiều class file tương ứng.

Ví dụ `App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        Helper helper = new Helper();
        Formatter formatter = new Formatter();

        System.out.println(formatter.format(helper.message()));
    }

    static class Formatter {
        String format(String value) {
            return "[" + value + "]";
        }
    }
}

class Helper {
    String message() {
        return "class files";
    }
}
```

Biên dịch:

```sh
mkdir -p out
javac -d out App.java
```

Nếu tệp được lưu trong thư mục hiện tại và có package như ví dụ, hãy đặt nó đúng vị trí hoặc chạy lệnh từ cấu trúc nguồn thích hợp. Khi biên dịch thành công, các class file tương ứng gồm:

```text
out/
└── com/
    └── example/
        ├── App.class
        ├── App$Formatter.class
        └── Helper.class
```

Tên `App$Formatter.class` là cách compiler biểu diễn class lồng nhau trong tên nhị phân. Dấu `$` cũng có thể xuất hiện trong tên định danh Java do người lập trình đặt, vì vậy không nên dựa riêng vào ký tự này để suy luận một lớp chắc chắn là lớp lồng nhau.

Chạy lớp chính:

```sh
java -cp out com.example.App
```

Kết quả:

```text
[class files]
```

Các lớp cục bộ và lớp vô danh cũng có thể tạo class file riêng. Tên nội bộ của những class file này có thể chứa số hoặc ký hiệu do compiler sinh ra; không nên coi tên đó là một API ổn định để tham chiếu trong mã nguồn.

## 5. Package quyết định cấu trúc thư mục đầu ra

Tên package đầy đủ của lớp được ánh xạ thành đường dẫn thư mục. Ví dụ:

| Tên lớp đầy đủ | Đường dẫn class file dưới output root |
|---|---|
| `com.example.App` | `com/example/App.class` |
| `com.example.util.Texts` | `com/example/util/Texts.class` |
| `org.acme.data.RecordMapper` | `org/acme/data/RecordMapper.class` |
| `Hello` trong default package | `Hello.class` |

Nếu một lớp khai báo `package com.example.util;`, đường dẫn đầu ra của lớp phải phản ánh package đó. Khi chạy, classpath phải trỏ đến thư mục cha của `com`, không trỏ trực tiếp vào thư mục `com/example/util`.

Ví dụ, với:

```text
out/com/example/util/Texts.class
```

Classpath đúng là `out`, và tên lớp đầy đủ là `com.example.util.Texts`:

```sh
java -cp out com.example.util.Texts
```

Nếu classpath trỏ nhầm đến `out/com/example`, JVM sẽ tìm sai đường dẫn và thường báo `ClassNotFoundException` hoặc `NoClassDefFoundError`, tùy cách lớp được yêu cầu nạp.

## 6. Class file chứa những gì?

Class file là định dạng nhị phân được đặc tả bởi Java Virtual Machine Specification. Cấu trúc của nó gồm các phần chính:

1. **Magic number:** bốn byte đầu có giá trị hex `CAFEBABE`, dùng để nhận diện định dạng class file.
2. **Minor và major version:** biểu thị phiên bản định dạng class file và một số trạng thái phiên bản đặc biệt.
3. **Constant pool:** bảng hằng số chứa các chuỗi, tên lớp, tên phương thức, mô tả kiểu, tham chiếu trường/phương thức và các giá trị cần thiết khác.
4. **Access flags:** thông tin cờ truy cập và thuộc tính của lớp.
5. **This class và super class:** lớp hiện tại và lớp cha trực tiếp.
6. **Interfaces:** các interface mà lớp triển khai.
7. **Fields:** thông tin trường của lớp.
8. **Methods:** thông tin phương thức, constructor và bytecode của chúng.
9. **Attributes:** metadata bổ sung, chẳng hạn thông tin mã nguồn, bảng biến cục bộ, annotation, generic signature, stack map và các thuộc tính khác.

Sơ đồ khái quát:

```text
Class file
├── Magic number
├── Minor / major version
├── Constant pool
├── Access flags
├── This class / Super class
├── Interfaces
├── Fields
├── Methods
│   └── Code attributes (bytecode)
└── Other attributes
```

Không phải mọi method đều có phần `Code`: method abstract hoặc native không có thân bytecode thông thường trong class file. Một số thông tin generic được lưu dưới dạng signature metadata; kiểu generic thường được xóa trong quá trình type erasure trước khi chạy.

Class file không phải văn bản có thể chỉnh sửa bằng trình soạn thảo thông thường. Hãy thay đổi mã nguồn rồi biên dịch lại, hoặc dùng công cụ chuyên dụng khi cần phân tích bytecode.

## 7. Kiểm tra class file bằng javap

JDK cung cấp công cụ `javap` để xem cấu trúc lớp đã biên dịch. Ví dụ:

```sh
javap -classpath out com.example.App
```

Lệnh này hiển thị các thành viên mà lớp công khai ra bên ngoài, chẳng hạn constructor và phương thức.

Để xem chi tiết class file:

```sh
javap -verbose -classpath out com.example.App
```

Có thể xem bytecode của các phương thức:

```sh
javap -c -classpath out com.example.App
```

Một số tùy chọn hữu ích:

| Tùy chọn | Nội dung |
|---|---|
| `-c` | Hiển thị bytecode trong các phương thức |
| `-p` | Hiển thị cả thành viên private |
| `-s` | Hiển thị internal type signature |
| `-l` | Hiển thị thông tin số dòng và biến cục bộ nếu có |
| `-verbose` | Hiển thị thông tin chi tiết như constant pool, flags, version và attributes |

Ví dụ phần đầu của kết quả `javap -verbose` có thể chứa:

```text
Classfile .../App.class
  Last modified ...; size ...
  SHA-256 checksum ...
  Compiled from "App.java"
public class com.example.App
  minor version: 0
  major version: 61
```

Các dòng thời gian, kích thước và checksum phụ thuộc tệp thực tế. Với Java 17, class file major version là 61; Java 21 là 65. Không nên nhầm số major version của class file với số phiên bản JDK in ra bởi `java -version`.

## 8. Các tùy chọn javac ảnh hưởng đến đầu ra

Ngoài `-d`, một số tùy chọn tác động trực tiếp đến các tệp được sinh ra hoặc metadata bên trong class file:

| Tùy chọn | Tác dụng |
|---|---|
| `-d <dir>` | Chọn thư mục ghi class file |
| `-s <dir>` | Chọn thư mục ghi mã nguồn được annotation processor sinh ra |
| `-h <dir>` | Chọn thư mục ghi header C dùng với native method |
| `--release <N>` | Chọn ngôn ngữ, bytecode và API nền tảng theo Java release N |
| `-g` | Sinh thông tin gỡ lỗi |
| `-g:none` | Không sinh thông tin gỡ lỗi |
| `-g:lines,vars,source` | Chọn các loại thông tin gỡ lỗi cụ thể |
| `-parameters` | Lưu tên tham số phương thức trong class file |
| `-encoding UTF-8` | Chọn encoding đọc tệp nguồn |
| `-proc:none` | Tắt annotation processing |
| `-implicit:none` | Không tạo class file cho các tệp nguồn được biên dịch ngầm định |

Ví dụ tách class file và mã nguồn sinh ra:

```sh
javac -d out -s generated-sources -parameters src/com/example/App.java
```

`-d` và `-s` có vai trò khác nhau. `-d` nhận class file; `-s` nhận mã nguồn được annotation processor sinh ra. Nếu dùng annotation processing, compiler có thể cần biên dịch thêm mã được sinh ra trong cùng lượt hoặc ở các vòng xử lý tiếp theo.

Nếu dùng native method và cần tạo C header, tùy chọn `-h` có thể chỉ định thư mục đầu ra header. Đây là đầu ra riêng, không thay thế class file.

## 9. Ghi đè và class file cũ còn sót lại

Khi biên dịch lại một lớp vào cùng thư mục đầu ra, `javac` có thể ghi class file mới đè lên tệp cùng tên. Tuy nhiên, compiler không phải công cụ dọn dẹp toàn bộ thư mục đầu ra.

Ví dụ, lần đầu `App.java` khai báo:

```java
public class App {
    static class OldHelper {
    }
}
```

Sau lần biên dịch, thư mục đầu ra có thể chứa:

```text
App.class
App$OldHelper.class
```

Sau đó lập trình viên xóa `OldHelper` khỏi mã nguồn và biên dịch lại `App.java`. Tệp `App$OldHelper.class` cũ có thể vẫn nằm trong thư mục đầu ra vì compiler không xóa mọi class file không còn được sinh ra ở lượt hiện tại.

Tệp cũ có thể gây nhầm lẫn khi đóng gói hoặc chạy chương trình, đặc biệt nếu classpath chứa nhiều thư mục đầu ra. Vì vậy, trong build sạch, hãy xóa thư mục đầu ra trước khi biên dịch lại.

macOS/Linux:

```sh
rm -rf out
mkdir -p out
javac -d out src/com/example/App.java
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force out
javac -d out src/com/example/App.java
```

Chỉ xóa thư mục build do dự án sở hữu và đã xác định đúng đường dẫn. Không dùng lệnh xóa rộng trên thư mục làm việc hoặc thư mục chứa dữ liệu nguồn.

Gradle và Maven thường có task `clean` để xóa đầu ra build được quản lý trước khi biên dịch lại:

```sh
./gradlew clean compileJava
mvn clean compile
```

Trên Windows, Gradle Wrapper có thể gọi bằng `gradlew.bat clean compileJava`.

## 10. Phân biệt class file và các đầu ra khác của compiler

Một lần biên dịch có thể tạo ra nhiều loại tệp khác nhau:

- Class file `.class`: định nghĩa lớp đã biên dịch, thường nằm dưới `-d`.
- Mã nguồn sinh ra `.java`: đầu ra của annotation processor, thường nằm dưới `-s`.
- Native header `.h`: đầu ra phục vụ JNI, có thể được đặt dưới `-h`.
- Tệp tài nguyên: thường được quản lý bởi build tool hoặc được đóng gói riêng; `javac` không tự sao chép mọi tài nguyên ứng dụng vào thư mục class file.
- JAR: được tạo bằng công cụ `jar` hoặc build tool từ class file và tài nguyên, không phải đầu ra mặc định của lệnh `javac`.

Ví dụ, nếu dự án có `src/main/resources/application.properties`, lệnh `javac` đơn thuần không tự sao chép tệp này sang `out`. Build tool cần có bước xử lý resources riêng.

Để đóng gói class file và tài nguyên, có thể dùng Gradle/Maven hoặc lệnh `jar`. Ví dụ đơn giản khi đã có `out`:

```sh
jar --create --file app.jar -C out .
```

Lệnh trên đóng gói nội dung thư mục `out` vào JAR. Nó không tự thêm dependency bên ngoài hoặc tạo cấu hình khởi chạy nếu chưa được khai báo.

## 11. Quy trình thực hành hoàn chỉnh

Giả sử có dự án nhỏ:

```text
project/
└── src/
    └── com/
        └── example/
            ├── App.java
            └── Message.java
```

`Message.java`:

```java
package com.example;

public class Message {
    public String text() {
        return "Build output is ready";
    }
}
```

`App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        Message message = new Message();
        System.out.println(message.text());
    }
}
```

Tạo thư mục đầu ra, biên dịch và chạy trên macOS/Linux:

```sh
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/com/example/Message.java src/com/example/App.java
java -cp out com.example.App
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac --release 17 -encoding UTF-8 -d out src/com/example/Message.java src/com/example/App.java
java -cp out com.example.App
```

Kết quả:

```text
Build output is ready
```

Đầu ra quan trọng:

```text
out/
└── com/
    └── example/
        ├── App.class
        └── Message.class
```

Có thể kiểm tra lớp đã biên dịch:

```sh
javap -classpath out com.example.App
javap -verbose -classpath out com.example.App
```

Quy trình này minh họa đầy đủ việc tách mã nguồn, class file, chọn phiên bản nền tảng và chạy lớp bằng classpath phù hợp.

## 12. Lỗi thường gặp khi ghi class file

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac` báo không ghi được class file | Thư mục đầu ra không tồn tại, không có quyền ghi hoặc đường dẫn sai | Tạo đúng thư mục, kiểm tra quyền ghi và truyền đường dẫn hợp lệ cho `-d` |
| Không tìm thấy `.class` sau khi biên dịch | Đang tìm sai thư mục; compiler đã ghi cạnh nguồn hoặc dưới output root | Kiểm tra có dùng `-d` hay không và tìm theo package |
| `ClassNotFoundException` | Classpath không trỏ đến thư mục gốc của package hoặc thiếu JAR | Thêm đúng output root và dependency vào classpath |
| `NoClassDefFoundError` | Một lớp cần thiết không có hoặc không thể nạp khi chạy | Kiểm tra dependency và classpath runtime; xác định lớp bị thiếu trong thông báo |
| `UnsupportedClassVersionError` | JVM chạy cũ hơn phiên bản class file | Dùng JVM đủ mới hoặc biên dịch với `--release` phù hợp |
| Class file cũ vẫn xuất hiện sau khi sửa/xóa lớp | Compiler không dọn toàn bộ đầu ra cũ | Chạy clean, xóa đúng thư mục build rồi biên dịch lại |
| Thiếu class file của lớp lồng nhau | Chỉ một phần đầu ra được sao chép hoặc đóng gói | Giữ toàn bộ class file được sinh ra, kể cả các tệp có tên chứa `$` |
| Chương trình thiếu tệp cấu hình khi chạy | Tài nguyên không được `javac` tự sao chép | Cấu hình task resources hoặc đưa tài nguyên vào JAR |

Khi xử lý lỗi, cần xác định lỗi xuất hiện ở bước nào: compiler không ghi được tệp, JVM không tìm thấy lớp, hay JVM tìm thấy nhưng không thể nạp/định nghĩa lớp. Ba tình huống có nguyên nhân và cách khắc phục khác nhau.

## 13. Checklist về class file

- [ ] Đã chọn đúng thư mục nguồn và thư mục làm việc.
- [ ] Đã dùng `-d` để tách đầu ra khỏi mã nguồn khi cần.
- [ ] Thư mục gốc đầu ra đã tồn tại và có quyền ghi.
- [ ] Package được ánh xạ đúng thành cấu trúc thư mục.
- [ ] Đã giữ đầy đủ class file của lớp lồng nhau và các lớp phụ thuộc.
- [ ] Class file được tạo bằng phiên bản bytecode phù hợp với runtime.
- [ ] Đã phân biệt đầu ra class file với mã nguồn sinh ra, native header và resource.
- [ ] Đã dọn đầu ra cũ khi cần bảo đảm build sạch.
- [ ] Đã kiểm tra class file bằng `javap` khi cần chẩn đoán.
- [ ] Classpath/module path khi chạy trỏ đúng thư mục gốc và thư viện cần thiết.

Class file là sản phẩm trực tiếp của bước biên dịch Java. Hiểu cách `javac` đặt tên, tổ chức và ghi các tệp này giúp kiểm soát pipeline build, tránh class file cũ gây nhiễu và chẩn đoán chính xác lỗi giữa biên dịch, đóng gói và thực thi.