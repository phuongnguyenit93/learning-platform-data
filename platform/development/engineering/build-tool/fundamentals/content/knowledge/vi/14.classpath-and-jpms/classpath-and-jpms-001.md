# Classpath là gì và cách JVM tìm lớp từ thư mục hoặc JAR

Khi chạy một chương trình Java, JVM cần tìm được các lớp mà chương trình sử dụng. Một lớp có thể nằm trong thư mục chứa các file `.class` đã biên dịch, trong một file JAR, hoặc trong một thư viện được build tool đưa vào môi trường chạy. Danh sách các vị trí mà Java dùng để tìm lớp và tài nguyên được gọi là **classpath**.

Classpath là một phần quan trọng của môi trường biên dịch và chạy Java. Nếu một thư viện có trong compile classpath nhưng thiếu trong runtime classpath, mã nguồn có thể biên dịch thành công nhưng ứng dụng lại lỗi khi chạy. Nếu khai báo sai thư mục gốc, JVM có thể không tìm thấy lớp dù file `.class` đang tồn tại trên ổ đĩa. Nếu có nhiều JAR chứa cùng một lớp, kết quả còn có thể phụ thuộc vào thứ tự classpath và cách class loader nạp lớp.

## 1. Classpath là gì?

Classpath là danh sách các vị trí mà Java class loader có thể sử dụng để tìm bytecode và tài nguyên. Mỗi phần tử của danh sách thường là:

- Một thư mục gốc chứa cây thư mục package và các file `.class`.
- Một file JAR chứa các lớp và tài nguyên.
- Một file ZIP có cấu trúc phù hợp để được dùng như classpath entry.

Ví dụ một chương trình có cấu trúc:

```text
my-app/
├── out/
│   └── classes/
│       └── com/
│           └── example/
│               └── Main.class
└── libs/
    └── helper.jar
```

Classpath có thể gồm hai entry:

```text
out/classes
libs/helper.jar
```

Entry đầu tiên là thư mục chứa lớp ứng dụng. Entry thứ hai là JAR chứa thư viện phụ trợ.

Classpath không phải là danh sách file `.java`. JVM chạy bytecode đã được biên dịch. Khi biên dịch, `javac` cũng nhận classpath để tìm những lớp mà mã nguồn tham chiếu.

## 2. Từ tên lớp đến đường dẫn file

Java nhận diện một lớp thông thường bằng tên nhị phân (*binary name*). Ví dụ:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
```

Tên lớp đầy đủ là:

```text
com.example.Main
```

Khi tìm lớp này trong classpath, tên package được chuyển thành đường dẫn thư mục và tên lớp thành tên file `.class`:

```text
com.example.Main
       |
       v
com/example/Main.class
```

Nếu classpath entry là `out/classes`, class loader tìm:

```text
out/classes/com/example/Main.class
```

Nếu classpath entry là `libs/application.jar`, JAR phải chứa entry:

```text
com/example/Main.class
```

Điểm cần nhớ: classpath trỏ đến **thư mục gốc của cây package**, không trỏ trực tiếp đến thư mục package chứa file `.class`.

Ví dụ, nếu file nằm ở:

```text
build/classes/java/main/com/example/Main.class
```

thì classpath entry là:

```text
build/classes/java/main
```

Không phải:

```text
build/classes/java/main/com/example
```

Nếu trỏ đến thư mục package `com/example`, class loader sẽ tiếp tục tìm `com/example/Main.class` bên dưới nó và không tìm thấy lớp theo tên `com.example.Main`.

## 3. Class loader tìm lớp như thế nào?

JVM sử dụng các class loader để nạp định nghĩa lớp vào runtime. Trong ứng dụng Java thông thường, class loader ứng dụng (*application/system class loader*) có thể tìm lớp và tài nguyên từ classpath của ứng dụng. Class loader cũng có thể ủy quyền việc tìm kiếm cho class loader cha theo mô hình delegation.

Quy trình khái quát:

```text
Ứng dụng cần lớp com.example.Main
             |
             v
      Class loader nhận yêu cầu
             |
             v
   Kiểm tra lớp đã được nạp chưa
             |
             v
   Ủy quyền theo class-loader hierarchy
             |
             v
  Tìm định nghĩa lớp từ các nguồn được quản lý
             |
       +-----+-----+
       |           |
    Tìm thấy    Không tìm thấy
       |           |
       v           v
  Nạp và liên kết  Báo lỗi phù hợp
       |
       v
  JVM thực thi bytecode
```

Với các class loader tích hợp thông thường, cơ chế parent delegation thường được dùng: class loader con hỏi class loader cha trước, rồi mới tìm ở các nguồn do nó quản lý. Cơ chế này giúp những lớp nền tảng và lớp đã được nạp ở cấp cha có tính nhất quán trong phạm vi loader hierarchy.

Không nên hiểu rằng JVM luôn quét mọi thư mục và JAR từ đầu cho mỗi lần dùng lớp. Class loader quản lý quá trình nạp và lưu lớp đã nạp; lớp thường chỉ được nạp khi cần. Ngoài class loader mặc định, ứng dụng hoặc framework còn có thể tạo class loader riêng để nạp plugin, ứng dụng con hoặc thành phần cách ly.

## 4. Classpath gồm nhiều entry và thứ tự tìm kiếm

Một classpath có thể gồm nhiều thư mục và JAR:

```text
out/classes
libs/logging.jar
libs/json.jar
libs/database-driver.jar
```

Khi một lớp chưa được nạp cần được tìm từ classpath của cùng class loader, thứ tự entry có thể ảnh hưởng đến kết quả. Nếu hai entry cùng chứa một lớp có cùng binary name, lớp được tìm thấy trước theo quy tắc của loader sẽ được sử dụng.

Ví dụ:

```text
classpath = old-library.jar : new-library.jar
```

Giả sử cả hai JAR đều chứa:

```text
com/example/util/Formatter.class
```

Nếu loader tìm thấy lớp trong `old-library.jar` trước, ứng dụng có thể dùng định nghĩa cũ dù `new-library.jar` cũng nằm trong classpath.

Đây là một nguyên nhân phổ biến của lỗi khó hiểu sau khi nâng cấp thư viện: build file có thể đã thêm JAR mới nhưng vẫn còn một JAR cũ xuất hiện trước trong classpath.

### Tránh hai thư viện chứa cùng một lớp

Hai dependency không nên cùng đóng gói một binary class nếu không có chủ đích rõ ràng. Các tình huống này có thể gây:

- Chạy nhầm implementation cũ.
- Lỗi `NoSuchMethodError` khi mã được biên dịch với API mới nhưng runtime nạp lớp cũ.
- Hành vi không nhất quán giữa môi trường phát triển và CI do thứ tự dependency khác nhau.
- Lỗi liên quan đến kiểu dữ liệu hoặc serialization khi các thành phần không cùng phiên bản.

Khi nghi ngờ trùng lớp, hãy kiểm tra nội dung các JAR và dependency graph thay vì chỉ thêm JAR mới vào đầu hoặc cuối classpath.

## 5. Phân cách các entry theo hệ điều hành

Giá trị classpath là một danh sách đường dẫn. Ký tự phân cách khác nhau theo hệ điều hành:

| Hệ điều hành | Ký tự phân cách |
|---|---|
| Windows | Dấu chấm phẩy `;` |
| Linux | Dấu hai chấm `:` |
| macOS | Dấu hai chấm `:` |

Ví dụ Windows:

```powershell
java -cp "out\classes;libs\helper.jar" com.example.Main
```

Ví dụ Linux/macOS:

```bash
java -cp "out/classes:libs/helper.jar" com.example.Main
```

Nếu đường dẫn có dấu cách, hãy đặt toàn bộ giá trị classpath trong dấu ngoặc kép để shell truyền nó thành một đối số. Cần dùng đúng ký tự phân cách của môi trường đang chạy; dấu `:` không phải dấu phân cách classpath trên Windows.

## 6. Dùng `-cp` hoặc `-classpath` khi chạy Java

Java launcher cho phép chỉ định classpath bằng tùy chọn `-cp` hoặc `-classpath`. Hai tùy chọn này tương đương.

Ví dụ:

```bash
java -cp out/classes com.example.Main
```

Lệnh yêu cầu Java tìm lớp chính `com.example.Main` trong `out/classes` và các nguồn classpath được chỉ định.

Nếu ứng dụng cần thêm JAR:

```bash
java -cp "out/classes:libs/helper.jar" com.example.Main
```

Trên Windows:

```powershell
java -cp "out\classes;libs\helper.jar" com.example.Main
```

Khi có nhiều dependency, có thể liệt kê từng JAR hoặc dùng wildcard cho các JAR trực tiếp trong một thư mục.

### Wildcard cho thư mục chứa JAR

Java launcher hỗ trợ wildcard `*` trong classpath để đưa tất cả file JAR trong một thư mục vào danh sách:

```bash
java -cp "out/classes:libs/*" com.example.Main
```

Trên Windows:

```powershell
java -cp "out\classes;libs\*" com.example.Main
```

Wildcard này áp dụng cho các JAR trực tiếp trong thư mục `libs`, không tự quét đệ quy các thư mục con. Thứ tự các JAR được mở rộng từ wildcard không nên được dùng làm cơ chế chọn phiên bản. Nếu nhiều JAR có lớp trùng nhau, hãy loại bỏ xung đột hoặc khai báo classpath tường minh.

## 7. Biến môi trường CLASSPATH

Java launcher có thể nhận classpath mặc định từ biến môi trường `CLASSPATH` khi lệnh không chỉ định `-cp` hoặc `-classpath`. Nếu biến này không được đặt, classpath mặc định của user thường là thư mục hiện tại (`.`).

Ví dụ trên PowerShell:

```powershell
$env:CLASSPATH = 'out\classes;libs\helper.jar'
java com.example.Main
```

Ví dụ trên Linux/macOS:

```bash
export CLASSPATH="out/classes:libs/helper.jar"
java com.example.Main
```

Tuy nhiên, cấu hình classpath toàn cục qua biến môi trường dễ làm các dự án ảnh hưởng lẫn nhau. Một terminal có thể mang giá trị cũ khiến chương trình chạy được trên máy cá nhân nhưng không chạy được ở terminal hoặc CI khác.

Trong script chạy ứng dụng, nên chỉ định classpath rõ bằng `-cp`, hoặc để build tool tạo runtime classpath. Cách này giúp người đọc biết chính xác ứng dụng cần những thư viện nào.

## 8. Biên dịch và chạy chương trình với classpath

Classpath có hai vai trò thường gặp:

- Khi biên dịch, `javac` dùng classpath để tìm những lớp mà source code tham chiếu.
- Khi chạy, Java launcher truyền classpath cho môi trường chạy để class loader tìm lớp và tài nguyên.

Giả sử project có cấu trúc:

```text
sample/
├── src/
│   └── com/example/Main.java
├── libs/
│   └── helper.jar
└── out/
```

Mã nguồn `Main.java` sử dụng một lớp trong `helper.jar`:

```java
package com.example;

import com.vendor.Helper;

public class Main {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
```

### Biên dịch trên Linux/macOS

```bash
mkdir -p out/classes
javac -cp libs/helper.jar -d out/classes src/com/example/Main.java
```

`-cp` cung cấp JAR cần thiết cho compiler. `-d` chỉ định thư mục lưu lớp đã biên dịch. Vì `Main` thuộc package `com.example`, file kết quả nằm ở:

```text
out/classes/com/example/Main.class
```

### Chạy trên Linux/macOS

```bash
java -cp "out/classes:libs/helper.jar" com.example.Main
```

Runtime classpath cần chứa cả lớp ứng dụng đã biên dịch lẫn thư viện mà ứng dụng sử dụng.

### Biên dịch và chạy trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out\classes | Out-Null
javac -cp "libs\helper.jar" -d "out\classes" "src\com\example\Main.java"
java -cp "out\classes;libs\helper.jar" com.example.Main
```

Việc biên dịch thành công không đảm bảo lệnh chạy sẽ thành công nếu runtime classpath thiếu JAR. Hai classpath có thể giống nhau, nhưng không bắt buộc phải giống: compiler có thể cần annotation processor hoặc thư viện chỉ dùng lúc biên dịch; runtime cần những thư viện thực sự cần để thực thi.

## 9. Đóng gói lớp vào JAR

Một JAR là archive chứa lớp và tài nguyên theo cấu trúc đường dẫn. Ví dụ, từ thư mục `out/classes`, có thể tạo JAR:

```bash
jar --create --file app.jar -C out/classes .
```

JAR tạo ra có thể chứa:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── Main.class
```

Khi đưa `app.jar` vào classpath:

```bash
java -cp app.jar com.example.Main
```

Class loader có thể tìm `com/example/Main.class` bên trong JAR.

Có thể kiểm tra nội dung JAR bằng:

```bash
jar --list --file app.jar
```

Lệnh này hữu ích khi nghi ngờ JAR thiếu lớp hoặc cấu trúc package bên trong không đúng.

## 10. Khác biệt giữa `-cp` và `-jar`

Java launcher hỗ trợ hai kiểu khởi chạy phổ biến:

**Chạy lớp chính với classpath tường minh:**

```bash
java -cp "app.jar:libs/helper.jar" com.example.Main
```

Bạn chỉ rõ tên lớp chính và toàn bộ classpath cần dùng.

**Chạy JAR có manifest:**

```bash
java -jar app.jar
```

Trong trường hợp này, manifest của JAR cần khai báo `Main-Class`, ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
```

Khi dùng `-jar`, Java launcher lấy lớp chính từ manifest. Các thiết lập user classpath khác như `-cp` không được dùng để bổ sung classpath cho kiểu khởi chạy này. Nếu ứng dụng cần JAR phụ trợ, manifest có thể khai báo thuộc tính `Class-Path`, hoặc ứng dụng phải được đóng gói theo một cách phân phối có chứa và nạp các dependency đó.

Ví dụ manifest có dependency tương đối:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: libs/helper.jar libs/logging.jar
```

Các URL trong manifest `Class-Path` được phân giải tương đối với vị trí JAR chứa manifest. Vì vậy, nếu `app.jar` nằm ở thư mục gốc và helper nằm trong `libs/`, cấu trúc phân phối cần giữ đúng đường dẫn:

```text
distribution/
├── app.jar
└── libs/
    ├── helper.jar
    └── logging.jar
```

Nếu di chuyển JAR mà không di chuyển các dependency theo cấu trúc tương ứng, launcher có thể không tìm thấy chúng.

## 11. JAR lồng bên trong JAR không tự động có trên classpath

Một JAR có thể chứa một JAR khác như một file tài nguyên:

```text
application.jar
├── com/example/Main.class
└── libs/
    └── helper.jar
```

Classpath chuẩn không tự động mở `application.jar`, tìm các file JAR lồng trong đó rồi thêm chúng vào classpath. Nó chỉ xử lý các classpath entry được cung cấp theo cơ chế mà launcher/class loader hỗ trợ.

Để phân phối ứng dụng với dependency, có thể:

- Phân phối JAR ứng dụng cùng thư mục `libs/` và khai báo manifest `Class-Path`.
- Tạo một JAR hợp nhất (*fat JAR* hoặc *uber JAR*) chứa lớp ứng dụng và lớp dependency theo cấu trúc phù hợp.
- Dùng plugin hoặc launcher framework có khả năng nạp các JAR lồng theo cơ chế riêng.
- Để build tool hoặc hệ thống triển khai tạo runtime classpath và khởi chạy ứng dụng.

Không nên giả định chỉ cần copy các JAR vào `application.jar/libs/` là Java launcher có thể tìm thấy chúng.

## 12. Tìm tài nguyên trên classpath

Classpath không chỉ phục vụ tìm `.class`. Class loader còn có thể tìm tài nguyên như:

- `application.properties`.
- File JSON hoặc XML mẫu.
- Template HTML.
- Ảnh, schema hoặc dữ liệu tĩnh.

Ví dụ cấu trúc:

```text
out/classes/
├── com/example/Main.class
└── config/
    └── application.properties
```

Ứng dụng có thể đọc tài nguyên qua class loader:

```java
import java.io.InputStream;

public class ConfigLoader {
    public InputStream openConfig() {
        return getClass()
            .getClassLoader()
            .getResourceAsStream("config/application.properties");
    }
}
```

Đường dẫn truyền vào `ClassLoader.getResourceAsStream` được tính từ gốc classpath, thường không bắt đầu bằng dấu `/`.

`Class.getResource(...)` có quy tắc hơi khác:

```java
// Đường dẫn tuyệt đối từ classpath root
var rootResource = ConfigLoader.class.getResource("/config/application.properties");

// Đường dẫn tương đối với package của ConfigLoader
var packageResource = ConfigLoader.class.getResource("application.properties");
```

Với đường dẫn bắt đầu bằng `/`, `Class.getResource` tìm từ root. Không có `/` thì đường dẫn được tính tương đối với package của lớp gọi.

Nếu tài nguyên không có trong thư mục/JAR thuộc classpath runtime, kết quả có thể là `null`. Một lỗi thường gặp là file nằm trong `src/main/resources` nhưng quá trình build không đưa nó vào output directory hoặc JAR.

## 13. Classpath trong Maven và Gradle

Khi sử dụng build tool, thông thường không cần tự ghép danh sách JAR bằng tay. Plugin Java và dependency configurations tạo classpath phù hợp cho từng công việc.

### Gradle: compile classpath và runtime classpath

Với plugin Java, các configuration thường gặp:

- `compileClasspath`: dependency cần khi biên dịch mã nguồn chính.
- `runtimeClasspath`: dependency cần khi chạy ứng dụng hoặc thành phần chính.
- `testCompileClasspath`: dependency cần khi biên dịch mã kiểm thử.
- `testRuntimeClasspath`: dependency cần khi chạy kiểm thử.

Có thể xem dependency graph:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Đầu ra của các task như `compileJava` và `test` được cấu hình từ các source set và dependency configuration tương ứng. Nếu tự tạo task chạy Java, nên dùng runtime classpath provider của source set hoặc application plugin thay vì tự quét thư mục `libs`.

### Maven: dependency classpath

Maven Compiler Plugin sử dụng dependency phù hợp để biên dịch. Các plugin chạy ứng dụng hoặc kiểm thử cũng xây dựng classpath theo scope/configuration. Có thể xem dependency graph bằng:

```bash
mvn dependency:tree
```

Nếu cần in classpath thực tế để phục vụ một script, Maven Dependency Plugin có goal `build-classpath`, ví dụ:

```bash
mvn dependency:build-classpath -Dmdep.outputFile=target/classpath.txt
```

Kết quả có thể được dùng để chẩn đoán hoặc tích hợp với công cụ khác. Trong ứng dụng bình thường, nên để Maven plugin hoặc packaging plugin quản lý cách chạy và phân phối dependency.

## 14. Classpath và module path trong JPMS

Từ Java 9, Java Platform Module System (JPMS) bổ sung khái niệm module path. Classpath và module path đều có thể cung cấp lớp cho ứng dụng, nhưng chúng có ngữ nghĩa khác nhau.

| Classpath | Module path |
|---|---|
| Cung cấp lớp và tài nguyên theo mô hình classpath truyền thống | Cung cấp các module được nhận diện theo module descriptor hoặc quy tắc automatic module |
| Lớp ứng dụng thường thuộc unnamed module của class loader | Các lớp thuộc named module hoặc automatic module |
| Không áp dụng đầy đủ ranh giới `exports`/`requires` như named modules | JPMS kiểm tra quan hệ module, exports và readability |
| Khởi chạy lớp chính phổ biến với `-cp` | Có thể khởi chạy module với `--module-path` và `--module` |

Ví dụ classpath:

```bash
java -cp "app.jar:libs/*" com.example.Main
```

Ví dụ module path:

```bash
java --module-path mods -m com.example.app/com.example.Main
```

Với module path, module thường có `module-info.java` hoặc được nhận diện theo cơ chế automatic module. Không nên nhầm `--module-path` với `-cp`: cách Java tìm và kiểm tra lớp trong hai mô hình khác nhau.

Một ứng dụng cũ có thể tiếp tục chạy trên classpath dù các dependency chưa được modular hóa. Khi chuyển sang JPMS, cần xem xét tên module, `requires`, `exports`, module split package và khả năng tương thích của các thư viện.

## 15. Classpath và class loader tùy chỉnh

Trong ứng dụng thông thường, classpath do launcher hoặc build tool cung cấp thường là đủ. Tuy nhiên, một số ứng dụng cần nạp lớp động:

- IDE nạp plugin.
- Máy chủ ứng dụng cô lập từng web application.
- Hệ thống plugin nạp extension từ thư mục riêng.
- Công cụ chạy script hoặc kiểm thử tạo class loader riêng.

Java cho phép tạo class loader tùy chỉnh. Một class loader có thể lấy lớp từ thư mục hoặc nguồn riêng, nhưng cần tuân theo các nguyên tắc về delegation, identity và lifecycle.

Hai lớp có cùng tên nhị phân nhưng được định nghĩa bởi hai class loader khác nhau được xem là hai kiểu runtime khác nhau. Vì vậy, nếu một plugin và ứng dụng chính cùng nạp một bản sao của API class bằng hai loader độc lập, có thể xuất hiện lỗi ép kiểu dù tên lớp giống nhau.

Đây là lý do trong môi trường plugin hoặc application server, việc xác định class loader sở hữu một lớp quan trọng không kém việc xem classpath có chứa JAR hay không.

## 16. Những lỗi classpath thường gặp

### `Could not find or load main class`

Nguyên nhân thường gặp:

- Tên lớp chính viết sai.
- Classpath trỏ sai thư mục gốc.
- File `.class` chưa được biên dịch hoặc không nằm trong cấu trúc package mong đợi.
- Lệnh chạy thiếu output directory hoặc JAR.

Ví dụ, nếu file nằm ở `out/classes/com/example/Main.class`, hãy dùng:

```bash
java -cp out/classes com.example.Main
```

Không dùng `com/example/Main.class` làm tên lớp chính.

### `ClassNotFoundException`

Lỗi này thường xuất hiện khi ứng dụng yêu cầu nạp một lớp theo tên, ví dụ qua `Class.forName(...)`, nhưng class loader không tìm thấy định nghĩa lớp. Hãy kiểm tra tên lớp, runtime classpath và class loader đang thực hiện yêu cầu.

### `NoClassDefFoundError`

Lỗi này xảy ra khi runtime cần một định nghĩa lớp mà không thể sử dụng được. Một trường hợp phổ biến là lớp có khi biên dịch nhưng thiếu ở runtime. Cũng có thể lớp từng thất bại khi khởi tạo hoặc một lỗi liên kết trước đó khiến lớp không dùng được.

Hãy kiểm tra runtime classpath và dependency graph, đồng thời đọc phần `Caused by` trong stack trace.

### `NoSuchMethodError` hoặc `NoSuchFieldError`

Các lỗi này thường cho thấy runtime đã nạp một phiên bản lớp khác với phiên bản mà mã được biên dịch dựa trên đó. Nguyên nhân có thể là hai JAR chứa cùng lớp, dependency bắc cầu chọn phiên bản cũ hoặc classpath order không như mong đợi.

Kiểm tra dependency graph, nội dung JAR và thứ tự classpath. Chỉ thêm một bản JAR mới mà không loại bỏ bản cũ có thể không giải quyết được lỗi.

### `ClassCastException` với hai lớp có cùng tên

Nếu cùng một binary class được nạp bởi hai class loader khác nhau, hai kiểu runtime không nhất thiết tương thích để ép kiểu. Thông báo lỗi có thể hiển thị hai lớp cùng tên nhưng kèm thông tin loader khác nhau. Cần kiểm tra kiến trúc class loader và tránh nạp trùng API dùng chung ở các loader độc lập khi không có chủ đích.

## 17. Cách kiểm tra JAR và classpath khi gặp lỗi

Khi nghi ngờ một lớp không có trong JAR, có thể kiểm tra nội dung:

```bash
jar --list --file libs/helper.jar
```

Tìm entry theo đường dẫn package, ví dụ:

```text
com/vendor/Helper.class
```

Nếu muốn xác định lớp được nạp từ nguồn nào, có thể bật log class loading của JVM:

```bash
java -Xlog:class+load=info -cp "out/classes:libs/*" com.example.Main
```

Trên Windows:

```powershell
java -Xlog:class+load=info -cp "out\classes;libs\*" com.example.Main
```

Log này cho biết các lớp được nạp và nguồn liên quan. Nó hữu ích khi có nhiều JAR hoặc class loader tùy chỉnh. Đầu ra có thể rất dài, vì vậy có thể lọc theo tên lớp hoặc package cần điều tra.

Trong Java code, có thể xem class loader của một lớp:

```java
System.out.println(Main.class.getClassLoader());
System.out.println(Main.class.getResource("Main.class"));
```

`getResource` có thể trả về URL chỉ ra lớp đến từ thư mục hoặc JAR nào. Cách này hữu ích để chẩn đoán lớp bị nạp từ nguồn không mong đợi.

## 18. Quy trình chẩn đoán lỗi classpath

Khi ứng dụng báo không tìm thấy lớp hoặc dùng sai phiên bản, hãy kiểm tra theo trình tự:

1. **Xác định binary name của lớp.** Ví dụ `com.example.Main` tương ứng với `com/example/Main.class`.
2. **Xác định vị trí thật của file.** File nằm trong output directory hay JAR nào?
3. **Xác định classpath root.** Nếu là thư mục, entry phải là thư mục gốc trước phần package; nếu là JAR, JAR phải chứa entry đúng.
4. **Kiểm tra lệnh chạy.** Có `-cp` hoặc `-classpath` chưa? Dấu phân cách có đúng hệ điều hành không? Có dùng `-jar` khiến classpath ngoài bị bỏ qua không?
5. **Kiểm tra compile và runtime riêng.** Dependency có ở compile classpath nhưng thiếu runtime classpath không?
6. **Kiểm tra thứ tự và lớp trùng.** Có nhiều JAR chứa cùng binary class không?
7. **Kiểm tra class loader.** Lớp có được nạp bởi loader tùy chỉnh hoặc loader cha không?
8. **Xem log và dependency graph.** Dùng `-Xlog:class+load=info`, `gradle dependencies` hoặc `mvn dependency:tree` để xác định nguồn.

Không nên giải quyết lỗi bằng cách copy ngẫu nhiên thêm JAR vào thư mục hoặc thêm mọi JAR trên máy vào classpath. Cách đó có thể làm build chạy được tạm thời nhưng khiến dependency không được quản lý và khó tái lập.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Classpath trỏ trực tiếp đến thư mục package | Classpath trỏ đến root của cây package, phía trên `com/`, `org/`... |
| JVM tìm file `.java` khi chạy | JVM nạp bytecode `.class` và tài nguyên; mã nguồn phải được biên dịch trước. |
| `import` trong Java tự thêm thư viện | `import` chỉ giúp tham chiếu tên lớp; build phải cung cấp dependency trên classpath. |
| Có JAR trên ổ đĩa nghĩa là JVM tự tìm thấy | JAR phải được đưa vào classpath hoặc được một loader phù hợp nạp. |
| `-cp` và `-jar` có thể cộng dồn tùy ý | Khi dùng `-jar`, user classpath từ `-cp` không được dùng như classpath bổ sung. |
| Wildcard `libs/*` tìm JAR ở mọi thư mục con | Wildcard chỉ mở rộng các JAR trực tiếp trong thư mục được chỉ định. |
| JAR lồng trong JAR tự động được tìm thấy | Classpath chuẩn không tự nạp JAR lồng; cần packaging hoặc loader hỗ trợ. |
| Compile classpath và runtime classpath luôn giống nhau | Mỗi giai đoạn có nhu cầu khác nhau và build tool quản lý configuration riêng. |
| Classpath và module path giống nhau | Module path áp dụng mô hình JPMS với named/automatic module và quy tắc module. |

## 20. Các nguyên tắc nên nhớ

- Đặt classpath entry ở thư mục gốc chứa cây package hoặc chỉ định trực tiếp JAR.
- Dùng tên lớp đầy đủ khi chạy main class, ví dụ `com.example.Main`.
- Dùng `-cp`/`-classpath` để làm rõ classpath của lệnh chạy.
- Dùng đúng dấu phân cách classpath: `;` trên Windows, `:` trên Linux/macOS.
- Kiểm tra cả compile classpath và runtime classpath.
- Tránh nhiều JAR chứa cùng một binary class.
- Không dựa vào thứ tự mở rộng wildcard để chọn phiên bản.
- Dùng manifest `Class-Path` hoặc packaging/launcher phù hợp khi phân phối JAR cùng dependency.
- Không giả định JAR lồng được nạp bởi classpath chuẩn.
- Phân biệt classpath truyền thống với module path của JPMS.
- Dùng log class loading và dependency graph để xác định nguồn lớp khi có lỗi.

Classpath là danh sách nguồn mà class loader sử dụng để tìm bytecode và tài nguyên. Hiểu cách tên lớp ánh xạ thành đường dẫn, cách thư mục và JAR được đưa vào classpath, cũng như cách launcher và class loader phối hợp sẽ giúp chẩn đoán chính xác lỗi thiếu lớp, nạp nhầm phiên bản và khác biệt giữa môi trường biên dịch với môi trường chạy.
