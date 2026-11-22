# Chạy JAR với jar, classpath và cấu hình manifest

## 1. JAR, classpath và manifest

Một chương trình Java thường được biên dịch thành nhiều file `.class` và có thể cần thư viện hoặc tài nguyên cấu hình. JAR (Java ARchive) gom class, resource và metadata vào một tệp archive theo định dạng ZIP để phân phối thuận tiện.

Ba khái niệm cần phân biệt:

- **JAR** là gói chứa class, resource và metadata của ứng dụng hoặc thư viện.
- **Classpath** là danh sách vị trí mà JVM tìm kiếm class và resource. Các vị trí có thể là thư mục class, JAR hoặc ZIP được hỗ trợ.
- **Manifest** là tệp metadata nằm tại `META-INF/MANIFEST.MF` bên trong JAR. Manifest có thể khai báo class khởi chạy, classpath phụ thuộc và thông tin phiên bản.

Lệnh `jar` của JDK dùng để tạo, xem và thao tác với archive. Nó không tự chạy ứng dụng. Java launcher `java` mới là chương trình khởi động JVM và chạy class hoặc JAR.

Có hai cách phổ biến để khởi chạy:

1. `java -jar app.jar`: chạy executable JAR. Manifest cần khai báo `Main-Class`; dependency ngoài có thể được khai báo trong `Class-Path`.
2. `java -cp ... com.example.Main`: chỉ định classpath rõ ràng và tên class có phương thức `main` cần chạy.

Apache Ant có task `<jar>` để tạo archive và task `<java>` để khởi chạy chương trình Java. Các task này có thể được kết hợp để tạo và chạy ứng dụng trong build.

## 2. Cấu trúc một ứng dụng Java có dependency

Giả sử ứng dụng có class chính, tài nguyên cấu hình và một thư viện ngoài:

```text
project/
├── build.xml
├── lib/
│   └── gson-2.11.0.jar
└── src/
    └── main/
        ├── java/
        │   └── com/example/Main.java
        └── resources/
            └── app.properties
```

Sau khi biên dịch và đóng gói, cấu trúc triển khai có thể là:

```text
build/
├── app.jar
└── lib/
    └── gson-2.11.0.jar
```

`app.jar` chứa class của ứng dụng và resource `app.properties`. Thư viện Gson được giữ ở một JAR riêng trong `build/lib`.

Cách tổ chức này không yêu cầu giải nén hoặc sao chép class của thư viện vào JAR chính. Manifest có thể chỉ ra vị trí JAR phụ thuộc để Java launcher tìm thấy chúng khi chạy executable JAR.

Nếu muốn tạo một JAR độc lập chứa cả dependency, cần quy trình đóng gói dạng fat/uber JAR, có xử lý trùng lặp resource và metadata của thư viện. Task `<jar>` cơ bản chỉ đóng gói những tệp được đưa vào; nó không tự giải quyết dependency và hợp nhất thư viện.

## 3. Manifest và thuộc tính Main-Class

Một manifest thường có dạng:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Sample Application
Implementation-Version: 1.0.0
```

`Main-Class` chỉ định class khởi chạy của executable JAR. Giá trị là tên class đầy đủ gồm package, dùng dấu chấm và không có phần mở rộng `.class`.

Ví dụ:

- Đúng: `com.example.Main`
- Sai: `com/example/Main.class`

Class được chỉ định phải có phương thức entry point phù hợp:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
```

Khi chạy:

```bash
java -jar build/app.jar
```

Java launcher đọc manifest, lấy tên class từ `Main-Class`, tạo JVM và gọi phương thức `main`. Nếu manifest không có `Main-Class`, thường sẽ gặp lỗi:

```text
no main manifest attribute, in build/app.jar
```

Một JAR thư viện thông thường không bắt buộc phải có `Main-Class`. Thuộc tính này cần khi muốn chạy JAR trực tiếp bằng `java -jar`.

## 4. Manifest Class-Path để tìm dependency

Nếu ứng dụng dùng thư viện bên ngoài, JVM phải tìm thấy class của thư viện đó tại runtime. Manifest hỗ trợ thuộc tính `Class-Path` để khai báo những vị trí bổ sung.

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/gson-2.11.0.jar
```

Khi `app.jar` nằm trong thư mục `build`, mục `lib/gson-2.11.0.jar` được diễn giải tương đối với vị trí của JAR chứa manifest. Vì vậy, cấu trúc triển khai phải có:

```text
build/
├── app.jar
└── lib/
    └── gson-2.11.0.jar
```

`Class-Path` là danh sách URL phân tách bằng khoảng trắng. Các mục có thể là đường dẫn tương đối hoặc URL phù hợp. Với ứng dụng phân phối theo thư mục, đường dẫn tương đối thường dễ đóng gói và di chuyển hơn đường dẫn tuyệt đối gắn với một máy.

Một số lưu ý:

- Đường dẫn được tính từ vị trí JAR khai báo manifest, không phải thư mục hiện tại của terminal.
- Tên thư mục và file phải khớp với cấu trúc triển khai thực tế.
- Nếu có nhiều dependency, liệt kê từng mục cách nhau bằng khoảng trắng.
- Đường dẫn có dấu cách phải được biểu diễn theo cú pháp URL phù hợp; nên tránh tên thư mục có khoảng trắng nếu không cần thiết.
- `Class-Path` không phải cú pháp wildcard kiểu `lib/*`; hãy khai báo các JAR cần thiết theo định dạng manifest.
- Manifest không tải thư viện từ Maven repository. Dependency phải được đặt ở vị trí mà đường dẫn trong manifest có thể truy cập.

Ví dụ có hai dependency:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/gson-2.11.0.jar lib/logging-api.jar
```

Nếu một dependency bị thiếu hoặc đường dẫn không đúng, ứng dụng có thể khởi chạy nhưng sau đó gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` khi code cần class đó.

## 5. Tạo executable JAR bằng Ant

Task `<jar>` đóng gói nội dung thư mục hoặc tập tệp thành JAR. Có thể khai báo manifest ngay bên trong task.

Ví dụ `build.xml`:

```xml
<project name="sample-app" default="jar" basedir=".">
    <path id="compile.classpath">
        <pathelement location="lib/gson-2.11.0.jar"/>
    </path>

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>

        <copy todir="build/classes">
            <fileset dir="src/main/resources"/>
        </copy>
    </target>

    <target name="stage-dependencies" depends="compile">
        <mkdir dir="build/lib"/>
        <copy file="lib/gson-2.11.0.jar"
              todir="build/lib"/>
    </target>

    <target name="jar" depends="stage-dependencies">
        <jar destfile="build/app.jar"
             basedir="build/classes">
            <manifest>
                <attribute name="Main-Class"
                           value="com.example.Main"/>
                <attribute name="Class-Path"
                           value="lib/gson-2.11.0.jar"/>
                <attribute name="Implementation-Title"
                           value="Sample Application"/>
                <attribute name="Implementation-Version"
                           value="1.0.0"/>
            </manifest>
        </jar>
    </target>
</project>
```

Các bước chính:

1. `compile` tạo thư mục class và biên dịch mã nguồn. Classpath lúc biên dịch chứa JAR Gson để compiler tìm thấy các kiểu được ứng dụng sử dụng.
2. Resource trong `src/main/resources` được copy vào thư mục class. Khi đóng gói, chúng nằm trong JAR cùng với class.
3. `stage-dependencies` tạo thư mục `build/lib` và copy JAR phụ thuộc vào đó.
4. `jar` đóng gói nội dung `build/classes` thành `build/app.jar` và ghi manifest.

Chạy build:

```bash
ant clean jar
```

Sau khi hoàn tất, thư mục triển khai gồm `build/app.jar` và `build/lib/gson-2.11.0.jar`. Giá trị `Class-Path` trong manifest khớp với cấu trúc này.

Nếu ứng dụng không có dependency ngoài, có thể bỏ `Class-Path` và bước copy thư viện. Nếu có nhiều thư viện, thêm các mục tương ứng vào manifest và bảo đảm các JAR đều được đưa vào thư mục triển khai.

## 6. Chạy executable JAR bằng java -jar

Cú pháp cơ bản:

```bash
java -jar build/app.jar
```

Có thể truyền tham số cho JVM trước `-jar`, và truyền tham số ứng dụng sau tên JAR:

```bash
java -Xms256m -Xmx1g -Dapp.profile=production -jar build/app.jar --port 8080
```

Trong lệnh trên:

- `-Xms256m` và `-Xmx1g` là tùy chọn JVM.
- `-Dapp.profile=production` tạo Java system property.
- `build/app.jar` là executable JAR.
- `--port 8080` là tham số được chuyển vào `main(String[] args)` của ứng dụng.

Khi dùng `-jar`, Java launcher sử dụng `Main-Class` trong manifest để xác định entry point. Classpath runtime của executable JAR được xây dựng từ JAR chính và các mục trong manifest `Class-Path`.

Một điểm rất dễ nhầm: nếu lệnh có dạng `java -cp ... -jar app.jar`, tùy chọn `-cp`/`-classpath` sẽ bị bỏ qua khi `-jar` được dùng. Không dựa vào `-cp` trên dòng lệnh để bổ sung dependency cho chế độ executable JAR; hãy cấu hình manifest `Class-Path` hoặc dùng cách khởi chạy class trực tiếp.

## 7. Chạy class trực tiếp bằng -cp

Không phải ứng dụng nào cũng cần executable JAR. Có thể chạy class chính trực tiếp nếu biết classpath và tên class:

```bash
java -cp "build/classes:lib/gson-2.11.0.jar" com.example.Main
```

Trên Linux và macOS, dấu phân cách các mục classpath là dấu hai chấm `:`. Trên Windows, dùng dấu chấm phẩy `;`:

```bat
java -cp "build\classes;lib\gson-2.11.0.jar" com.example.Main
```

Nếu thư mục `lib` chứa nhiều JAR ở ngay cấp đó, Java hỗ trợ wildcard:

```bash
java -cp "build/classes:lib/*" com.example.Main
```

Wildcard `lib/*` bao gồm các JAR trực tiếp trong thư mục `lib`, không quét đệ quy các thư mục con. Khi classpath chứa nhiều mục, thứ tự có thể ảnh hưởng nếu nhiều JAR có cùng tên class hoặc resource; tránh đưa các phiên bản trùng nhau vào cùng classpath.

Trong chế độ này, tên class được truyền rõ ràng là `com.example.Main`. Thuộc tính `Main-Class` trong manifest không quyết định class được chạy. Cách này phù hợp khi muốn điều khiển classpath trực tiếp từ script, IDE hoặc môi trường triển khai.

So sánh nhanh:

| Tiêu chí | `java -jar app.jar` | `java -cp ... com.example.Main` |
|---|---|---|
| Entry point | `Main-Class` trong manifest | Tên class ở cuối lệnh |
| Classpath | JAR chính và manifest `Class-Path` | Các mục chỉ định qua `-cp` |
| Dễ phân phối | Thuận tiện với một layout JAR và thư mục lib | Cần script hoặc cấu hình classpath |
| Tham số JVM | Đặt trước `-jar` | Đặt trước tên class |
| Tham số ứng dụng | Đặt sau tên JAR | Đặt sau tên class |

## 8. Dùng task java của Ant để chạy JAR

Ant có task `<java>` để thực thi chương trình Java. Khi muốn chạy executable JAR, dùng thuộc tính `jar` và thường đặt `fork="true"` để khởi chạy JVM riêng:

```xml
<target name="run-jar">
    <java jar="build/app.jar"
          fork="true"
          failonerror="true">
        <jvmarg value="-Xmx1g"/>
        <jvmarg value="-Dapp.profile=production"/>
        <arg value="--port"/>
        <arg value="8080"/>
    </java>
</target>
```

Trong ví dụ:

- `jar` chỉ định executable JAR cần chạy.
- `fork="true"` yêu cầu Ant tạo tiến trình JVM riêng.
- `failonerror="true"` làm build thất bại nếu chương trình trả về mã thoát khác 0.
- `<jvmarg>` truyền tham số cho JVM.
- `<arg>` truyền tham số cho ứng dụng.

Khi chạy theo chế độ `jar`, entry point được lấy từ manifest. Dependency runtime nên được khai báo trong manifest `Class-Path` của JAR. Không xem thuộc tính `classpath` của task như cách bổ sung classpath cho chế độ `jar`; thuộc tính đó được dùng khi chạy theo `classname`.

Chạy target:

```bash
ant run-jar
```

Nếu cần truyền đối số có khoảng trắng, dùng một phần tử `<arg>` cho toàn bộ giá trị và chọn thuộc tính `value` hoặc `line` theo cấu trúc tham số. Với dữ liệu người dùng, nên tránh tự ghép một chuỗi lệnh shell dài vì việc quoting phụ thuộc hệ điều hành.

## 9. Dùng task java của Ant để chạy class với classpath

Nếu không muốn dùng manifest `Main-Class`, có thể gọi class trực tiếp bằng thuộc tính `classname`:

```xml
<path id="runtime.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="lib/gson-2.11.0.jar"/>
</path>

<target name="run-main">
    <java classname="com.example.Main"
          classpathref="runtime.classpath"
          fork="true"
          failonerror="true">
        <jvmarg value="-Xmx1g"/>
        <arg value="--port"/>
        <arg value="8080"/>
    </java>
</target>
```

Ở chế độ này:

- `classname` chỉ định class có phương thức `main`.
- `classpathref` trỏ tới Path chứa thư mục class và các JAR phụ thuộc.
- `<jvmarg>` dành cho JVM.
- `<arg>` dành cho ứng dụng.

Khi classpath được dùng ở nhiều target, khai báo một Path có `id` giúp tránh lặp lại cấu hình. Nếu compile và runtime có dependency khác nhau, nên tách `compile.classpath` và `runtime.classpath` để thể hiện đúng phạm vi.

## 10. Kiểm tra nội dung JAR và manifest

Khi JAR không chạy được, cần xác nhận archive có chứa đúng class và manifest hay không.

Liệt kê nội dung:

```bash
jar tf build/app.jar
```

Kiểm tra manifest bằng cách giải nén nội dung entry:

```bash
unzip -p build/app.jar META-INF/MANIFEST.MF
```

Hoặc dùng công cụ ZIP tương ứng trên hệ điều hành. Manifest nên có tối thiểu:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/gson-2.11.0.jar
```

Kiểm tra:

- Class chính có nằm trong JAR ở đường dẫn tương ứng với package không, ví dụ `com/example/Main.class`.
- Tên `Main-Class` có đúng tên đầy đủ của class không.
- JAR phụ thuộc có nằm đúng vị trí tương đối với JAR chính không.
- Tên JAR trong `Class-Path` có đúng chữ hoa/chữ thường và phần mở rộng không.
- Resource ứng dụng có được copy vào output trước khi tạo JAR không.

Có thể chạy ứng dụng với chế độ verbose class loading để tìm nguồn mà JVM dùng khi nạp class:

```bash
java -verbose:class -jar build/app.jar
```

Trên các JDK mới, tùy chọn `-Xlog:class+load=info` cũng có thể hữu ích. Log class loading khá dài; hãy tìm class gây lỗi để xác định JVM đã nạp nó từ JAR hoặc thư mục nào.

## 11. Lỗi thường gặp khi chạy JAR

### no main manifest attribute

JAR không có thuộc tính `Main-Class` hoặc manifest không được đóng gói đúng. Thêm `Main-Class` vào phần manifest của task `<jar>` rồi tạo lại JAR.

### Could not find or load main class

Tên class chính sai, class chưa được biên dịch hoặc classpath không chứa thư mục/JAR có class đó. Kiểm tra cấu trúc package và nội dung JAR bằng `jar tf`.

### ClassNotFoundException hoặc NoClassDefFoundError

Ứng dụng tìm thấy class chính nhưng thiếu một class khác khi chạy. Kiểm tra dependency runtime, manifest `Class-Path`, vị trí JAR phụ thuộc và phiên bản thư viện. Dependency có thể cần ở runtime dù compiler đã tìm thấy nó lúc build.

### java -jar chạy được trên máy lập trình nhưng thất bại khi triển khai

Máy lập trình có thể vô tình cung cấp dependency qua biến môi trường, classpath IDE hoặc thư mục hiện tại. Hãy kiểm tra cấu trúc triển khai chỉ gồm những tệp được đóng gói và xác nhận manifest trỏ đúng các JAR được phân phối.

### Đã thêm -cp nhưng java -jar vẫn không tìm thấy dependency

Khi dùng `-jar`, tùy chọn `-cp` bị bỏ qua. Cập nhật `Class-Path` trong manifest hoặc chuyển sang chạy class bằng `-cp` và chỉ định tên class tường minh.

### NoClassDefFoundError: Could not initialize class

Đây có thể là lỗi khởi tạo class do exception xảy ra trong static initializer ở lần nạp trước. Đọc exception đầu tiên trong log để tìm nguyên nhân gốc; chỉ thêm JAR vào classpath không nhất thiết giải quyết được lỗi khởi tạo.

### Main class chạy nhưng không đọc được resource

Kiểm tra resource đã được copy vào thư mục classes trước khi đóng gói và tên resource được dùng theo đường dẫn classpath, ví dụ `app.properties`. Nếu resource nằm trong JAR, ứng dụng nên nạp qua classloader thay vì giả định nó là file ngoài filesystem.

### Dependency trùng phiên bản

Nhiều JAR chứa cùng class có thể làm JVM nạp phiên bản không mong muốn tùy thứ tự classpath. Loại bỏ phiên bản trùng và quản lý dependency nhất quán giữa build, runtime và CI.

## 12. Nguyên tắc đóng gói và triển khai

- Đặt `Main-Class` khi JAR cần chạy trực tiếp bằng `java -jar`.
- Dùng `Class-Path` để liệt kê dependency ngoài theo đường dẫn tương đối với JAR chính.
- Giữ cấu trúc thư mục triển khai khớp với các mục trong manifest.
- Đảm bảo dependency runtime được phân phối cùng ứng dụng hoặc có mặt tại vị trí đã cấu hình.
- Dùng `-cp` khi muốn chọn classpath và entry point trực tiếp từ lệnh chạy.
- Không kết hợp `-jar` với kỳ vọng rằng `-cp` sẽ bổ sung dependency.
- Trong Ant, dùng `<java jar="...">` cho executable JAR và `<java classname="..." classpathref="...">` khi chạy class trực tiếp.
- Phân biệt `<jvmarg>` với `<arg>` để không nhầm tùy chọn JVM và tham số ứng dụng.
- Kiểm tra nội dung JAR, manifest và layout triển khai trước khi phát hành.
- Kiểm soát phiên bản dependency và tránh class trùng lặp trong runtime classpath.

Task `<jar>` tạo archive, manifest xác định cách executable JAR khởi chạy và tìm dependency, còn Java launcher thực thi chương trình. Khi dùng `java -jar`, hãy cấu hình `Main-Class` và `Class-Path` đúng với layout triển khai. Khi dùng `-cp`, hãy chỉ định class chính và toàn bộ vị trí runtime cần thiết. Ant hỗ trợ cả hai cách thông qua task `<java>`, giúp quy trình build và chạy ứng dụng có thể được tự động hóa nhất quán.

