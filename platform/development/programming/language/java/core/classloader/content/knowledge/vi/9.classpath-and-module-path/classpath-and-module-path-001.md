# Classpath là gì và cách xác định thư mục gốc trong Java

Một chương trình Java muốn nạp `com.example.app.Main` cần biết **tìm bytecode ở đâu**. JVM không quét toàn bộ ổ đĩa để tìm file tên `Main.class`; trong mô hình classpath truyền thống, class loader dùng **tên nhị phân** của class và những **classpath entry** được cấu hình để xác định vị trí tương đối chính xác.

Điểm quan trọng nhất: **classpath root là thư mục đứng trước toàn bộ đường dẫn package**. Nếu file nằm tại `project/out/com/example/app/Main.class` và khai báo `package com.example.app;` thì root là `project/out`, không phải `project/out/com/example/app`.

Bài thuộc nhóm **Đường dẫn tìm kiếm** của Java core – classloader. Mục tiêu là hiểu định nghĩa classpath, xác định thư mục gốc cho package/default package, biên dịch và chạy Java 17+ với đúng root, dùng JAR/resource/classpath wildcard và chẩn đoán lỗi.

## 1. Classpath là gì?

Classpath là danh sách vị trí dùng để tìm class và resource trong mô hình class loading dựa trên class path. Một entry thông dụng gồm:

- **Thư mục** chứa cây package đã biên dịch, ví dụ `out` hoặc `build/classes/java/main`.
- **JAR** chứa các entry `.class` và resource, ví dụ `lib/helper.jar`.
- **Wildcard** `lib/*` được Java launcher mở rộng thành các JAR trực tiếp trong thư mục đó.

Classpath của lệnh `javac` giúp compiler tìm những class/type phụ thuộc khi biên dịch. Classpath của lệnh `java` giúp runtime tìm các class/resource lúc thực thi. Hai tập này có thể khác nhau; dependency cần dùng lúc chạy phải có trong đường tìm runtime thích hợp.

**Các loại đường dẫn khác nhau:**

| Khái niệm | Dùng cho việc gì? | Ví dụ |
| --- | --- | --- |
| Source root | Chứa file nguồn `.java` cho compiler/build tool | `src/main/java` |
| Classpath root | Chứa cây package của `.class` hoặc các resource | `out`, `target/classes` |
| Working directory | Thư mục hiện tại của tiến trình, làm mốc cho path tương đối | `project`, `user.dir` |
| `PATH` | Biến của hệ điều hành tìm lệnh `java`/`javac` | `JDK/bin` |
| `CLASSPATH` | Biến môi trường có thể cung cấp classpath khi không có `-cp` | `out;lib/x.jar` trên Windows |
| Module path | Nơi Java module finder tìm module artifacts của JPMS | `--module-path mods` |

Không nhầm `PATH` với `CLASSPATH`. Nếu máy nhận lệnh `java` nhưng ném `ClassNotFoundException`, việc chỉ sửa `PATH` thường không giải quyết được nguyên nhân.

`import com.example.Foo;` trong source cũng **không tự thêm** thư viện vào classpath. `import` chỉ là cú pháp Java cho phép tham chiếu tên ngắn; compiler và JVM vẫn cần nguồn class thích hợp.

## 2. Cách tính classpath root từ package

Ví dụ:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
```

Binary name: `com.example.app.Main`.

Đường dẫn bytecode **tương đối với một directory classpath entry**: `com/example/app/Main.class`. Dấu chấm ngăn package trong tên nhị phân được ánh xạ thành ký tự phân tách thư mục tương ứng trong đường dẫn class file, rồi thêm hậu tố `.class`.

Nếu cây output là:

```text
project/
├── src/
│   └── com/example/app/Main.java
└── out/
    └── com/
        └── example/
            └── app/
                └── Main.class
```

thì root đúng là `out`:

```text
Classpath entry        Relative class path
      out         +    com/example/app/Main.class
                       |
                       v
             out/com/example/app/Main.class
```

Từ thư mục `project`, chạy:

```bash
java -cp out com.example.app.Main
```

Lệnh dưới đây **sai root**:

```bash
java -cp out/com/example/app com.example.app.Main
```

JVM sẽ thử tìm `out/com/example/app/com/example/app/Main.class`, nên có thể báo `Could not find or load main class com.example.app.Main`.

### Phương pháp xác định root khi biết file thực tế

1. Tìm **binary name** từ `package` và tên class, ví dụ `org.acme.Parser`.
2. Chuyển thành đường dẫn tương đối `org/acme/Parser.class`.
3. Bỏ đường dẫn tương đối đó khỏi cuối đường dẫn class file thật; phần còn lại là **directory root**.

| File thực tế | Binary name | Root |
| --- | --- | --- |
| `D:\work\build\classes\org\acme\Parser.class` | `org.acme.Parser` | `D:\work\build\classes` |
| `/srv/demo/out/a/b/Task.class` | `a.b.Task` | `/srv/demo/out` |
| `out/Hello.class`, không khai báo package | `Hello` | `out` |
| `target/classes/com/demo/Main.class` | `com.demo.Main` | `target/classes` |

**Default package:** Nếu class không có dòng `package`, binary name là `Hello`, đường tương đối chỉ là `Hello.class`, root chính là thư mục trực tiếp chứa file. Không khuyến khích default package cho ứng dụng nhiều module/package vì khó quản lý namespace.

**Nested class:** `com.example.Outer.Inner` trong cú pháp source thường có binary name `com.example.Outer$Inner`; file có thể là `Outer$Inner.class` dưới cây `com/example`. Classpath root vẫn là thư mục trước `com`.

**Source layout so với runtime:** Vị trí `src/com/example/Main.java` là source path. `javac -d out` có thể tự đặt output đúng cây package vào `out`. Runtime cần thư mục chứa **class output**, không tự nạp mã nguồn dưới `src` chỉ vì đã `import`.

## 3. Cấu hình với `-cp` và sự khác nhau của hệ điều hành

Java launcher có ba cách viết tương đương: `-cp`, `-classpath` và `--class-path`.

```bash
java --class-path out com.example.app.Main
```

Nhiều entry được nối bằng ký tự do OS quy định:

| Hệ điều hành | Separator | Ví dụ |
| --- | --- | --- |
| Windows | Dấu chấm phẩy `;` | `java -cp "out;resources;lib/helper.jar" com.example.app.Main` |
| Linux/macOS | Dấu hai chấm `:` | `java -cp "out:resources:lib/helper.jar" com.example.app.Main` |

Đặt giá trị classpath trong dấu nháy là thói quen tốt, đặc biệt nếu path có khoảng trắng hoặc ký tự shell đặc biệt. `:` trong `C:\work` của Windows **không phải** ký tự phân cách giữa các classpath entry.

Nếu `out` là đường tương đối, nó được diễn giải dựa trên **working directory** nơi tiến trình được khởi động:

```bash
cd out
java -cp . com.example.app.Main
```

Lúc này `.` chính là `out`. Nếu chạy từ `project`, `-cp .` chỉ trỏ tới `project` và **không tự tìm xuống `project/out`**. Classpath không phải cơ chế quét đệ quy mọi thư mục con.

### Giá trị mặc định và biến môi trường

Với chế độ chạy class trên classpath, khi **không cung cấp `-cp` và không đặt biến `CLASSPATH`**, classpath mặc định là working directory `.`. Nhưng **khi đã cung cấp `-cp`**, Java không tự thêm `.` vào cuối. Muốn dùng cả working directory lẫn JAR, ghi rõ:

```bash
java -cp ".;lib/helper.jar" com.example.app.Main
```

Dòng trên dành cho Windows; trên Unix đổi `;` thành `:`. Nếu class output nằm trong `out`, phải ghi `out` thay cho `.`.

Nên cung cấp classpath tường minh trong script/IDE/build tool thay vì dựa vào `CLASSPATH` toàn máy, vì biến môi trường rất dễ gây khác biệt giữa các máy. `-cp` trên command line ghi đè `CLASSPATH` cho tiến trình launcher đó.

## 4. Ví dụ Java 17+ độc lập: hai class, hai root

Tạo cấu trúc:

```text
classpath-demo/
├── src/
│   └── com/
│       └── example/
│           ├── app/Main.java
│           └── util/Greeter.java
├── resources/
│   └── com/example/app/config.properties
└── out/   (được tạo trước khi biên dịch)
```

File `src/com/example/util/Greeter.java`:

```java
package com.example.util;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Hello from Greeter";
    }
}
```

File `src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.util.Greeter;
import java.io.InputStream;
import java.util.Properties;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(Greeter.message());

        Properties properties = new Properties();
        try (InputStream stream =
                Main.class.getResourceAsStream("config.properties")) {
            if (stream == null) {
                throw new IllegalStateException("Resource not found");
            }
            properties.load(stream);
        }

        System.out.println("mode=" + properties.getProperty("mode"));
        System.out.println("main=" + Main.class.getName());
    }
}
```

File `resources/com/example/app/config.properties`:

```properties
mode=demo
```

Từ thư mục `classpath-demo`, nếu chưa có `out` thì tạo:

```bash
mkdir out
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -d out src/com/example/util/Greeter.java src/com/example/app/Main.java
```

Với `-d out`, compiler tạo:

```text
out/
└── com/example/
    ├── app/Main.class
    └── util/Greeter.class
```

Đường dẫn thực tế của resource vẫn là `resources/com/example/app/config.properties`; `javac` không tự copy file resource vào `out`.

Chạy trên **Windows**:

```bash
java -cp "out;resources" com.example.app.Main
```

Chạy trên **Linux/macOS**:

```bash
java -cp "out:resources" com.example.app.Main
```

Stdout chính xác của cả hai:

```text
Hello from Greeter
mode=demo
main=com.example.app.Main
```

Giải thích:

- Root `out` cho phép tìm `com/example/app/Main.class` và `com/example/util/Greeter.class`.
- Root `resources` cho phép tìm `com/example/app/config.properties`.
- `Main.class.getResourceAsStream("config.properties")` tìm tương đối theo package của `Main`, tức `com/example/app`.
- `Main.class.getName()` trả binary name `com.example.app.Main`.

Thử **bỏ `resources`**:

```bash
java -cp out com.example.app.Main
```

Chương trình vẫn tìm được `Main` và `Greeter`, in dòng đầu rồi ném `IllegalStateException: Resource not found`. Điều này cho thấy **root của class** và **root của resource** có thể là hai entry riêng. Nếu resource được copy vào `out/com/example/app` khi build, chỉ `out` cũng có thể đủ.

Thử **chạy nhầm tên `Main`**:

```bash
java -cp out Main
```

Lệnh không tìm được `Main` trong default package; binary name thực sự là `com.example.app.Main`. Đây là vấn đề tên class, không chỉ đường dẫn.

## 5. `javac -cp` khác `javac -d`

Hai tùy chọn thường xuất hiện cùng nhau nhưng có chức năng khác:

- `-d out`: **đưa output `.class` vào root `out`**, kèm cây package.
- `-cp something`: **chỉ nơi compiler tìm class và thư viện phụ thuộc**.

Giả sử `Greeter.class` đã được biên dịch vào `out`, và chỉ muốn compile lại `Main.java`:

```bash
javac --release 17 -cp out -d out src/com/example/app/Main.java
```

Compiler dùng `out` để resolve `com.example.util.Greeter`, còn output mới của `Main` cũng được ghi vào `out`.

Classpath lúc chạy là lựa chọn khác:

```bash
java -cp "out;resources" com.example.app.Main
```

(Windows; trên Linux/macOS thay `;` bằng `:`.)

Một dependency có trong compile classpath **không tự động xuất hiện** trên runtime classpath. Điều này giải thích lỗi “`javac` chạy tốt nhưng `java` thiếu class” khi khởi chạy thủ công mà quên JAR cần thiết.

Trong dự án dùng Gradle/Maven, build tool tổng hợp compile và runtime classpath từ các dependency scopes/configurations. Khi chạy qua IDE hoặc build tool, kiểm tra **run configuration thực tế** thay vì suy rằng compiler tự ghi lại mọi thư viện phụ thuộc vào `Main.class`.

## 6. Classpath root bên trong JAR

JAR là archive ZIP chứa các entry tương đối tính từ **root của archive**. Nếu muốn JAR cung cấp `com.example.app.Main`, entry phải là:

```text
com/example/app/Main.class
```

Không được vô tình lưu thành `out/com/example/app/Main.class` hoặc `src/com/example/app/Main.java` rồi mong loader hiểu đó là class runtime tương ứng.

Sau khi biên dịch ví dụ ở mục 4, đóng gói bằng JDK `jar` trên **một dòng tương thích đa nền tảng**:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out . -C resources .
```

`-C out .` yêu cầu `jar` lấy nội dung dưới `out` và lưu **tương đối từ root `out`**. `-C resources .` làm tương tự với resource. `--main-class` ghi `Main-Class` trong manifest.

Kiểm tra:

```bash
jar --list --file app.jar
java -jar app.jar
```

Trong danh sách của `jar --list`, ngoài manifest và các directory entries, các tệp quan trọng sẽ là:

```text
com/example/app/Main.class
com/example/util/Greeter.class
com/example/app/config.properties
```

Stdout của `java -jar app.jar` vẫn là:

```text
Hello from Greeter
mode=demo
main=com.example.app.Main
```

Có thể chạy JAR như một classpath entry:

```bash
java -cp app.jar com.example.app.Main
```

### `-jar` không vận hành giống `-cp`

`java -cp app.jar com.example.app.Main` nạp main class theo tên bạn truyền từ classpath entry. `java -jar app.jar` lấy main class từ manifest và **không dùng classpath được chỉ định bởi `-cp` hoặc biến `CLASSPATH` như trong chế độ chạy class thông thường**. Để tham chiếu dependency nằm ngoài executable JAR, có thể dùng manifest `Class-Path` hoặc launcher/packaging được thiết kế phù hợp.

Manifest `Class-Path` tham chiếu các URL/JAR theo quy tắc liên quan **vị trí của JAR chứa manifest**, không đơn giản là mọi path tương đối lấy mốc từ `user.dir`.

Đặc biệt, **Spring Boot executable JAR** thường có cấu trúc `BOOT-INF/classes` và `BOOT-INF/lib` với launcher riêng. Không coi cấu trúc đó là flat JAR mà `java -cp boot.jar com.example.Main` luôn hoạt động; dùng launcher hoặc `java -jar` được hỗ trợ.

## 7. `lib/*` có thêm tất cả mọi thứ không?

Không. Ký hiệu wildcard của Java launcher dạng `lib/*` mở rộng đến các JAR trực tiếp trong thư mục `lib`. Ví dụ:

```bash
java -cp "out;lib/*" com.example.app.Main
```

trên Windows; Linux/macOS:

```bash
java -cp "out:lib/*" com.example.app.Main
```

Giới hạn:

- `lib/*` **không quét đệ quy** `lib/plugins/**` hay các thư mục con.
- `lib/*` **không tự thêm** directory root `lib/classes` hoặc những file `.class` nằm trực tiếp dưới `lib`.
- Nếu cần cả class directory `lib/classes`, thêm entry `lib/classes` tường minh.
- Thứ tự mở rộng các JAR bởi wildcard không nhất thiết ổn định; nếu nhiều JAR chứa cùng tên class, đừng dựa vào “JAR nào thắng” như hợp đồng lâu dài.
- Đặt dấu nháy quanh classpath thường giúp tránh shell tự mở rộng wildcard trước khi Java launcher xử lý.

Classpath entry được tìm theo cơ chế của loader tương ứng. Trong đường dẫn classpath thông thường, nhiều bản của một class trong các entry khác nhau có thể dẫn tới nạp nhầm phiên bản dependency và lỗi `NoSuchMethodError` hoặc `NoSuchFieldError` khi thực thi.

## 8. Resource path: khác class binary name

Classpath có thể chứa file `config.properties`, JSON, XML, template, ảnh hoặc tài nguyên khác. Với `Main` thuộc package `com.example.app`:

```java
java.net.URL relative =
        Main.class.getResource("config.properties");

java.net.URL absolute =
        Main.class.getResource(
                "/com/example/app/config.properties");

java.net.URL loaderResource =
        Main.class.getClassLoader()
                .getResource("com/example/app/config.properties");
```

Đây là **đoạn mã minh họa chèn vào class `Main`**. Cả ba đường dẫn trên cùng trỏ tới tài nguyên phù hợp trong ví dụ mục 4 nếu đang dùng classloader ứng dụng thông thường.

| API | Quy tắc tìm |
| --- | --- |
| `Class.getResource("x")` | Tương đối theo package của class đó |
| `Class.getResource("/a/b/x")` | Tuyệt đối từ root resource (dấu `/` đầu được API này xử lý) |
| `ClassLoader.getResource("a/b/x")` | Tên resource tương đối từ root loader; thường **không** có dấu `/` đầu |

Với class bootstrap, `SomeCoreClass.class.getClassLoader()` có thể là `null`, nên không gọi `getResource` lên giá trị `null`.

Khi resource nằm trong JAR, URL có thể giống `jar:file:/.../app.jar!/com/example/app/config.properties`. Không phải mọi resource là một `java.io.File` vật lý trên filesystem. Đọc bằng `getResourceAsStream` thường an toàn hơn trong cả directory và JAR.

Named modules còn áp dụng module encapsulation, đặc biệt cho resource trong package không mở. Vì vậy cách resource được nhìn thấy qua API có thể khác khi chuyển một ứng dụng từ classpath sang module path.

## 9. Classpath và module path khác nhau

Từ Java 9, JPMS có **module path**. Ví dụ dạng chạy named module:

```bash
java --module-path mods --module m.example/com.example.Main
```

Đây là **cú pháp minh họa**, chỉ hoạt động khi `mods` có named module `m.example` phù hợp. Không áp dụng trực tiếp cho chương trình không có `module-info.java` ở mục 4.

| Classpath | Module path |
| --- | --- |
| Thường chứa class của unnamed module theo loader | Module finder xác định named modules |
| Cấu hình bằng `-cp`/`--class-path` | Cấu hình bằng `-p`/`--module-path` |
| Không cần `module-info.java` | Explicit module dùng `module-info.class` |
| Mapping directory/JAR entry theo package | Thêm module graph, readability, exports, opens |
| Phù hợp ứng dụng Java truyền thống | Phù hợp code được tổ chức theo JPMS |

Dù module cũng có class file theo cấu trúc package, việc đặt artifact trên module path **không hoàn toàn đồng nghĩa** đặt chính artifact đó trên classpath. Module boundaries và ánh xạ loader của `ModuleLayer` có thể thay đổi khả năng truy cập và hành vi resolution.

## 10. Làm sao xác định classpath thực tế của ứng dụng đang chạy?

Một số API quan sát:

```java
System.out.println("classpath="
        + System.getProperty("java.class.path"));

System.out.println("working directory="
        + System.getProperty("user.dir"));

System.out.println("defining loader="
        + Main.class.getClassLoader());

System.out.println("code source="
        + Main.class.getProtectionDomain().getCodeSource());
```

Đây là **đoạn minh họa thêm vào `Main.main`**, không có stdout cố định vì còn phụ thuộc OS, launcher và build tool.

- `java.class.path` hữu ích với app chạy theo classpath; nó **không liệt kê toàn bộ mọi nguồn** mà custom loader có thể đọc.
- `user.dir` xác định working directory của tiến trình tại startup; không nhất thiết bằng thư mục chứa tệp `Main.java` hoặc JAR.
- `Main.class.getClassLoader()` cho biết **defining loader** của `Main`.
- `getProtectionDomain().getCodeSource()` có thể gợi ý artifact/thư mục gốc, nhưng **có thể `null`** hoặc không mang filesystem location hữu ích với bootstrap/custom loader.

Công cụ kiểm tra:

```bash
javap -classpath out com.example.app.Main
jar --list --file app.jar
```

Lệnh `javap` kiểm tra class file có tìm thấy từ root `out` và in thông tin class/bytecode; `jar --list` cho biết đường dẫn các entry trong JAR. Nếu cần điều tra HotSpot class loading, có thể bật:

```bash
java -Xlog:class+load=info -cp out com.example.app.Main
```

Log dạng này khá dài và định dạng phụ thuộc JDK. Nó giúp tìm nguồn class, nhưng không chứng minh rằng tất cả class loader của ứng dụng đều dùng cùng classpath.

### Quy ước output trong build tools

| Build tool | Source root mặc định | Classes runtime root thường gặp | Resource output thường gặp |
| --- | --- | --- | --- |
| Gradle Java plugin | `src/main/java` | `build/classes/java/main` | `build/resources/main` |
| Maven | `src/main/java` | `target/classes` | `target/classes` |

Các đường dẫn là **quy ước có thể tùy biến**. IDE hoặc build tool có thể tổng hợp nhiều root và dependency JAR cho run configuration. Không chỉ nhìn `src/main/java` rồi giả định thư mục đó là runtime classpath.

## 11. Classpath có phải cách tìm của mọi ClassLoader không?

Không. Java có các loader tích hợp và custom loaders:

- **Bootstrap loader** định nghĩa những lớp cốt lõi của JVM/Java SE; `String.class.getClassLoader()` thường là `null`.
- **Platform loader** phụ trách các platform classes phù hợp trong runtime image/module system.
- **Application loader** thường định nghĩa lớp chạy từ application classpath và những module phù hợp.
- **Custom loader** có thể tự tìm class từ URL, memory, database, plugin archive hoặc nguồn khác; nó có thể dùng classpath hoặc không.

Ví dụ:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
Class<?> type = system.loadClass("com.example.app.Main");
System.out.println(type.getClassLoader());
```

Đây là **đoạn minh họa**, cần đặt trong method xử lý `ClassNotFoundException`, và class phải thấy được từ system loader. `loadClass` có thể delegate tới parent; loader nhận yêu cầu không nhất thiết là loader **định nghĩa** class.

Một runtime class được xác định bằng **binary name + defining loader**. Hai loader khác nhau có thể định nghĩa hai class cùng tên nhưng là hai kiểu runtime khác nhau, dễ dẫn tới `ClassCastException`. Khi nhiều plugin/container tham gia, cần kiểm tra loader và module layer, không chỉ chuỗi `-cp`.

## 12. Bảng lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| `Could not find or load main class` | Binary name sai hoặc root sai | Ghép root với đường tương đối `a/b/C.class` và so file |
| `NoClassDefFoundError: ... (wrong name: ...)` | Class file được tìm nhưng tên bên trong không khớp | Kiểm tra `package`, vị trí output, tên chạy |
| `ClassNotFoundException` ở `Class.forName` | Loader được chọn không thấy class | Kiểm tra caller loader/explicit loader, dependency và binary name |
| `NoClassDefFoundError` trong runtime | Dependency mất, lỗi linking hoặc initialization thất bại từ trước | Đọc nguyên nhân ban đầu và runtime artifacts |
| `NoSuchMethodError` / `NoSuchFieldError` | Version JAR runtime không tương thích | Kiểm tra dependency duplicate/version, method/field descriptor |
| Resource luôn `null` | Root tài nguyên thiếu hoặc đường lookup khác package | Kiểm tra file bên trong root/JAR và API `getResource` |
| Chạy trong IDE được, terminal không | IDE có runtime classpath khác | So lệnh Java và output roots thật |
| Chạy `-jar` thì thiếu thư viện | Đặt nhầm niềm tin vào `-cp` của chế độ `-jar` | Kiểm tra manifest/launcher/đóng gói dependency |
| `lib/*` bỏ sót `.class` trong thư mục con | Wildcard chỉ xử lý các JAR phù hợp | Bổ sung directory entry thực tế |
| Spring Boot JAR không chạy bằng `java -cp` thường | JAR có layout đặc thù `BOOT-INF` | Chạy bằng launcher hỗ trợ, thường `java -jar` |

### Quy trình debug có thể áp dụng ngay

1. **Xác định binary name.** Xem `package`, tên class và dấu `$` của nested class.
2. **Tìm `.class` thực tế.** Trong output folder hoặc entry trong JAR, có phải `a/b/C.class` không?
3. **Tìm root.** Bỏ đúng cây `a/b/C.class` khỏi đường dẫn thực tế; phần trước nó mới là root.
4. **Xác nhận command và OS.** `-cp` đang là gì, separator đúng chưa, đang chạy từ working directory nào?
5. **So compile/runtime.** `javac -cp` có dependency nhưng `java -cp` thiếu không?
6. **Kiểm tra resource riêng.** `Class.getResource` và `ClassLoader.getResource` xử lý tên path khác nhau.
7. **Nếu vẫn lỗi, kiểm tra loader/module.** Ai định nghĩa class, có custom policy hoặc named module không?
8. **Kiểm tra nguyên nhân gốc.** Lỗi còn có thể do binary incompatibility và initialization, không đơn giản là đường dẫn thiếu.

## 13. Tự kiểm tra

**Câu 1.** `Main.class` ở `C:\work\out\com\acme\Main.class` và package là `com.acme`. Dùng `-cp` nào?

**Đáp án:** `C:\work\out` vì JVM sẽ tìm `com/acme/Main.class` bên dưới root.

**Câu 2.** Từ thư mục dự án ví dụ, tại sao `java -cp . com.example.app.Main` không chạy nếu chỉ compile bằng `-d out`?

**Đáp án:** `.` chỉ vào thư mục dự án, còn file thực tế nằm dưới `out/com/example/app`. Cần dùng `-cp out` hoặc chuyển working directory sang `out` và dùng `-cp .`.

**Câu 3.** Trên Windows, muốn class ở `out` và resource ở `resources` thì lệnh nào đúng?

**Đáp án:** `java -cp "out;resources" com.example.app.Main`; trên Linux/macOS dùng `"out:resources"`.

**Câu 4.** `-cp lib/*` có tự tìm `lib/classes/com/acme/Thing.class` không?

**Đáp án:** Không. Wildcard launcher xử lý JAR trực tiếp trong `lib`, không đệ quy tới directory class root `lib/classes`.

**Câu 5.** Khi `com.example.app.Main` được đóng gói trong `app.jar`, entry trong JAR tên gì?

**Đáp án:** `com/example/app/Main.class`, không mang tiền tố `out/` hoặc `src/`.

**Câu 6.** Vì sao `Main.class.getResource("config.properties")` tìm file dưới `resources/com/example/app`?

**Đáp án:** API này dùng tên resource tương đối theo package `com.example.app`. Runtime còn phải có entry `resources` trong classpath.

**Câu 7.** Có thể dùng `java -cp "extra.jar" -jar app.jar` để tùy ý thêm dependency vào classpath của chế độ `-jar` không?

**Đáp án:** Không theo cơ chế lựa chọn classpath thông thường của launcher `-jar`. Cần dùng manifest `Class-Path` hoặc launcher/packaging hỗ trợ.

**Câu 8.** Biên dịch thành công bằng `javac -cp lib/helper.jar` nhưng lúc chạy gặp thiếu `helper.SomeType`. Điều gì cần xem?

**Đáp án:** Runtime classpath có `helper.jar` hoặc cách cung cấp dependency tương đương chưa. `javac` không ghi nhớ và tự bổ sung `-cp` cho lệnh `java`.

**Câu 9.** Vì sao class có trong classpath vẫn có thể không dùng được trong một plugin?

**Đáp án:** Loader plugin có thể dùng namespace/source/policy khác, class thực tế được định nghĩa ở loader khác, hoặc có giới hạn module access. Cần kiểm tra defining loader và module layer.

**Câu 10.** Default package có class `Hello.class` ở `out`; chạy thế nào?

**Đáp án:** `java -cp out Hello` vì binary name là `Hello`, và relative class path là `Hello.class`.

## Ghi nhớ

**Root không phải folder chứa trực tiếp class có package: root đứng ở phía trên toàn bộ cây thư mục package.** Hãy luôn tính:

```text
Classpath root + binaryName.replace('.', '/') + ".class"
        = đường dẫn class trong một directory entry
```

Với JAR, phần tương đối phải là entry từ **root bên trong archive**. Sau đó kiểm tra riêng resource root, runtime dependencies, launcher mode (`-cp` hay `-jar`) và class loader thực tế khi dự án phức tạp hơn.

Nguồn chuẩn:

- [Java 17 `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) – classpath, wildcard, `-jar` và module path.
- [Java 17 `javac`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) – `-d`, classpath biên dịch và tìm type.
- [Java 17 `jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) – archive entries và manifest.
- [Java SE 17 `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) – tìm class/resource và parent delegation.
