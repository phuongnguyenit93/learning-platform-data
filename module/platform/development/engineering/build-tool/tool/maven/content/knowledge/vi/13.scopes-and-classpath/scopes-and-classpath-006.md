# Maven scope system, đường dẫn máy cục bộ và hạn chế khả chuyển

Trong Maven, **`scope=system`** là một cách khai báo dependency đặc biệt: thay vì yêu cầu Maven tìm artifact theo tọa độ từ local/remote repository, bạn cung cấp **đường dẫn tới một tệp JAR có sẵn trên máy đang build** thông qua `<systemPath>`. Cách này từng được dùng với thư viện thương mại, SDK cài sẵn hoặc một JAR mà nhóm chưa đưa vào repository.

Ví dụ rút gọn:

```xml
<dependency>
    <groupId>org.example.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/../vendor-lib/vendor-sdk.jar</systemPath>
</dependency>
```

**Đây là đoạn XML trong `<dependencies>` của một POM**, không phải toàn bộ POM. Maven chỉ dùng tệp ở đường dẫn sau khi nội suy; nó **không tải JAR này từ Maven Central hay repository manager**, kể cả khi `groupId:artifactId:version` trông như tọa độ Maven bình thường.

Apache Maven vẫn mô tả phạm vi `system` trong tài liệu, nhưng **không khuyến nghị sử dụng** vì nó khóa build vào một đường dẫn cục bộ, làm giảm tính khả chuyển và khó quản lý artifact. Hướng tốt hơn cho dự án lâu dài là **đưa thư viện có quyền phân phối vào Maven repository được quản lý**, rồi khai báo dependency `compile`, `provided`, `runtime` hoặc `test` đúng mục đích.

Mục tiêu bài này là hiểu chính xác cơ chế `system`, thử một ví dụ Java 17 có thể biên dịch và chạy, nhận biết các tình huống build hỏng trên CI/Windows/Linux/container, và biết cách chuyển khỏi `systemPath` mà không làm rơi mất dependency quan trọng.

## 1. Scope quyết định điều gì?

Maven dependency có các thông tin như `groupId`, `artifactId`, `version`, `type`, `classifier` và `scope`. Scope xác định cách dependency tham gia những classpath và liệu nó có được truyền theo quan hệ phụ thuộc bắc cầu hay không.

| Scope | Ý nghĩa chính | Cần nguồn JAR như thế nào? |
| --- | --- | --- |
| `compile` (mặc định) | Thường cần khi compile và chạy; có thể truyền bắc cầu. | Maven giải quyết artifact từ repository/reactor. |
| `provided` | Cần lúc compile/test nhưng kỳ vọng JDK/container cung cấp ở runtime; không truyền bắc cầu. | Thường vẫn giải quyết artifact theo tọa độ repository. |
| `runtime` | Không cần cho main compile, nhưng cần khi chạy hoặc test. | Maven giải quyết theo tọa độ repository. |
| `test` | Dành cho test compile/test execution; không truyền tiếp tới consumer. | Maven giải quyết theo tọa độ repository. |
| **`system`** | Dùng tệp cục bộ được chỉ định, phù hợp cho tình huống di sản đặc biệt; không dựa vào repository. | **Chính xác tệp ở `systemPath`.** |
| `import` | Chỉ dùng cho POM kiểu BOM trong `dependencyManagement`. | Nhập danh sách managed dependencies, không phải một JAR thông thường. |

Một số tài liệu Maven diễn giải `system` gần với `provided` về vai trò dependency không được phân phối theo cách thông thường; tài liệu cơ chế dependency cũng mô tả thư viện system có thể cần cho biên dịch và thực thi. Đừng suy ra rằng Maven sẽ **tự sao chép hoặc đóng gói** JAR đó vào sản phẩm. Thực tế cần kiểm tra classpath của plugin và cách đóng gói/khởi chạy ứng dụng; phần thực hành bên dưới đưa tệp JAR vào lệnh `java -cp` một cách tường minh.

**Định nghĩa chính xác của `system` là lựa chọn nguồn artifact cục bộ và cách scope tham gia quá trình giải quyết dependency**, chứ không phải lệnh “nhúng JAR vào file ứng dụng”. Nếu bạn muốn tạo fat JAR, WAR hoặc distribution, cần cấu hình plugin đóng gói thích hợp và kiểm tra nội dung đầu ra.

## 2. Bốn thành phần của một dependency system

Trong Maven POM, một dependency system thường có:

```xml
<dependency>
    <groupId>org.example.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/../vendor-lib/vendor-sdk.jar</systemPath>
</dependency>
```

- **`groupId` và `artifactId`**: tên logic dùng để định danh dependency trong mô hình Maven.
- **`version`**: phiên bản bạn gắn cho dependency; nó **không biến đường dẫn thành một artifact repository** và không giúp Maven tải JAR từ mạng.
- **`scope=system`**: bảo Maven sử dụng đường dẫn tệp thay vì cơ chế repository resolution thông thường.
- **`systemPath`**: đường dẫn đến JAR được cung cấp trước. Maven kiểm tra đường dẫn và tệp tương ứng; tệp thiếu sẽ làm build/đánh giá mô hình không đạt yêu cầu.

Đối với dependency hệ thống, **`<systemPath>` chỉ hợp lệ khi scope là `system`**. Đừng giữ `systemPath` sau khi chuyển scope sang `compile` hay `provided`: hãy bỏ phần tử này.

Đường dẫn `systemPath` **phải là đường dẫn tuyệt đối sau khi nội suy**. Ví dụ:

```xml
<systemPath>C:/sdk/vendor/vendor-sdk.jar</systemPath>
```

có thể là đường dẫn tuyệt đối trên một máy Windows, nhưng không tồn tại trên Linux/macOS. Dạng:

```xml
<systemPath>${project.basedir}/../vendor-lib/vendor-sdk.jar</systemPath>
```

sử dụng `project.basedir` (thư mục dự án Maven chứa POM hiện tại) để hình thành đường dẫn tuyệt đối trên máy chạy. Điều đó **giảm việc ghi cứng ổ đĩa hoặc username**, nhưng **không làm dependency khả chuyển theo nghĩa đầy đủ**: tệp vẫn phải tồn tại đúng cấu trúc và phải được cấp cho mọi máy/runner.

### Điều gì xảy ra nếu JAR không ở đường dẫn đó?

Maven **không tự thay thế bằng JAR ở `~/.m2/repository`**, không tự thử Maven Central và không suy ra nơi khác dựa vào tên `vendor-sdk`. Lỗi thường biểu hiện như “tệp ở systemPath không tồn tại hoặc không hợp lệ”, “systemPath must specify an absolute path” hoặc cảnh báo trong quá trình validation, tùy phiên bản Maven và dạng sai.

Ngược lại, với scope thông thường, Maven có thể tìm artifact theo tọa độ ở reactor, local repository rồi remote repositories được cấu hình, theo quy tắc của Maven Resolver.

## 3. Vì sao groupId/version không cứu được tính khả chuyển?

Hãy so hai máy:

```text
Máy A:
    /workspace/legacy-system-demo/
        app/pom.xml
        vendor-lib/vendor-sdk.jar    <-- có
    Kết quả: Maven đọc JAR tại chỗ

Máy B/CI:
    /workspace/legacy-system-demo/
        app/pom.xml
        vendor-lib/                  <-- trống
    Kết quả: Maven không tìm thấy tệp được yêu cầu
```

Ngay cả khi:

```xml
<groupId>org.example.vendor</groupId>
<artifactId>vendor-sdk</artifactId>
<version>1.0.0</version>
```

trùng với tọa độ của một JAR từng được cài trong cache Maven, `system` vẫn chỉ định **đường dẫn cục bộ**. Vì vậy, “đã từng tải được trên máy tôi” không chứng minh CI sẽ build được.

Một mặt khác là **kiểm soát phiên bản**. Nếu người A và B đều có tệp tên `vendor-sdk.jar` nhưng nội dung bytecode khác nhau, cùng POM có thể biên dịch hoặc chạy ra kết quả khác nhau dù version trong XML không đổi. Maven không tự dùng repository checksum/metadata để bảo đảm tính nhất quán cho tệp được khai báo bằng `systemPath`.

Tính khả chuyển ở đây có ít nhất ba tầng:

1. **Đường dẫn:** file có tồn tại ở đúng chỗ trên máy build?
2. **Nội dung:** file có đúng phiên bản, checksum, giấy phép và API tương thích?
3. **Phân phối:** file có được chuyển tới nơi chạy ứng dụng hoặc hệ thống đóng gói một cách hợp lệ?

Sửa được tầng thứ nhất bằng `${project.basedir}` chưa giải quyết được hai tầng còn lại.

## 4. Ví dụ chạy được: tạo một JAR cục bộ và khai báo system

Ví dụ dùng **JDK 17 trở lên** để tạo một thư viện JAR nhỏ, sau đó viết ứng dụng Maven phụ thuộc vào nó bằng `system`. Mọi giá trị trong bài là giả lập, không chứa SDK thương mại hay bí mật thật.

### 4.1. Cấu trúc thư mục

```text
legacy-system-demo/
├── vendor-src/
│   └── org/example/vendor/
│       └── VendorGreeting.java
├── vendor-classes/              (được javac tạo)
├── vendor-lib/
│   └── vendor-sdk.jar           (được jar tạo)
└── app/
    ├── pom.xml
    └── src/main/java/org/example/app/
        └── App.java
```

Tệp `vendor-sdk.jar` được đặt **bên ngoài dự án Maven `app`**, để tránh một trường hợp cảnh báo thường gặp khi `systemPath` trỏ trực tiếp tới một JAR bên trong chính thư mục dự án. Cách bố trí này **chỉ phục vụ học tập**, không phải giải pháp lâu dài: tệp ngoài module vẫn có thể thiếu khi checkout riêng module hoặc chạy CI.

### 4.2. Tạo thư mục

Linux/macOS, đứng tại thư mục muốn tạo ví dụ:

```bash
mkdir -p legacy-system-demo/vendor-src/org/example/vendor
mkdir -p legacy-system-demo/vendor-classes
mkdir -p legacy-system-demo/vendor-lib
mkdir -p legacy-system-demo/app/src/main/java/org/example/app
cd legacy-system-demo
```

Windows PowerShell, đứng tại thư mục muốn tạo ví dụ:

```powershell
New-Item -ItemType Directory -Force -Path "legacy-system-demo/vendor-src/org/example/vendor" | Out-Null
New-Item -ItemType Directory -Force -Path "legacy-system-demo/vendor-classes" | Out-Null
New-Item -ItemType Directory -Force -Path "legacy-system-demo/vendor-lib" | Out-Null
New-Item -ItemType Directory -Force -Path "legacy-system-demo/app/src/main/java/org/example/app" | Out-Null
Set-Location legacy-system-demo
```

Các thư mục `vendor-classes` và `vendor-lib` có thể rỗng ban đầu. Lệnh `jar` sẽ tạo JAR sau khi mã nguồn vendor được biên dịch.

### 4.3. Viết mã của thư viện ngoài Maven

Tệp `vendor-src/org/example/vendor/VendorGreeting.java`:

```java
package org.example.vendor;

public final class VendorGreeting {
    private VendorGreeting() {
    }

    public static String text(String name) {
        return "Hello, " + name + " (vendor)!";
    }
}
```

Đây là class Java 17+ có thể biên dịch độc lập, không cần dependency ngoài JDK.

Từ thư mục `legacy-system-demo`, biên dịch class và tạo JAR:

```bash
javac -d vendor-classes vendor-src/org/example/vendor/VendorGreeting.java
jar --create --file vendor-lib/vendor-sdk.jar -C vendor-classes .
```

Lệnh trên hoạt động tương tự trong PowerShell khi `javac` và `jar` có trong `PATH`. Sau khi thành công, JAR chứa class `org/example/vendor/VendorGreeting.class`. Có thể kiểm tra bằng:

```bash
jar --list --file vendor-lib/vendor-sdk.jar
```

Kết quả của `jar --list` có thể gồm manifest và các thư mục; không cần dự đoán toàn bộ thứ tự dòng. Điều quan trọng là có entry `org/example/vendor/VendorGreeting.class`.

Nếu dùng một SDK thật, không tự build lại JAR hoặc thay đổi file do nhà cung cấp cung cấp nếu giấy phép/kiểm soát integrity không cho phép. Ví dụ này tự tạo class giả để người học có thể thực hành mà không phụ thuộc file riêng của công ty nào.

### 4.4. POM ứng dụng: `app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.demo</groupId>
    <artifactId>system-scope-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.vendor</groupId>
            <artifactId>vendor-sdk</artifactId>
            <version>1.0.0</version>
            <scope>system</scope>
            <systemPath>${project.basedir}/../vendor-lib/vendor-sdk.jar</systemPath>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Phân tích:

- Dự án gốc Maven của ví dụ là **`app`**, không phải thư mục `legacy-system-demo`. Dùng `mvn -f app/pom.xml ...` khi đứng ở root để chọn đúng POM.
- `${project.basedir}` trở thành đường dẫn tuyệt đối tới `legacy-system-demo/app`.
- Phần `/../vendor-lib/vendor-sdk.jar` tìm JAR ở thư mục cùng cấp với `app`.
- Maven nhận dependency `org.example.vendor:vendor-sdk:1.0.0` từ **file tại systemPath**, không giải quyết từ repository.
- Plugin compiler có thể dùng class `VendorGreeting` khi biên dịch `App.java`.
- `<packaging>jar</packaging>` là loại đóng gói của ứng dụng, **không có nghĩa JAR của vendor được nhúng vào JAR ứng dụng**.

Maven có thể đưa ra cảnh báo về dependency `system` hoặc đường dẫn tùy phiên bản và bố cục. Đó là tín hiệu nên thay đổi cách quản lý artifact trong dự án thực tế; đừng bỏ qua cảnh báo chỉ vì compile thành công.

### 4.5. Mã ứng dụng: `app/src/main/java/org/example/app/App.java`

```java
package org.example.app;

import org.example.vendor.VendorGreeting;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(VendorGreeting.text("Maven"));
    }
}
```

Dòng `import org.example.vendor.VendorGreeting` cho thấy mã nguồn app **trực tiếp dùng API** của JAR vendor. Compiler phải tìm thấy class đó trong compile classpath. Không có classpath phù hợp sẽ phát sinh lỗi như `package org.example.vendor does not exist`.

### 4.6. Build và chạy ứng dụng

Đứng tại thư mục `legacy-system-demo` (đã chứa JAR vendor được tạo ở mục 4.3):

```bash
mvn -version
mvn -B -ntp -f app/pom.xml clean package
```

Nếu máy có JDK/Maven phù hợp và tải được các Maven plugins cần thiết, lệnh build thành công, tạo JAR ứng dụng trong `app/target`. **Toàn bộ log Maven** phụ thuộc phiên bản plugin, cache và môi trường nên không dự đoán cố định.

Chạy chương trình bằng cách **đưa cả thư mục class ứng dụng và JAR vendor vào runtime classpath**.

Linux/macOS:

```bash
java -cp "app/target/classes:vendor-lib/vendor-sdk.jar" org.example.app.App
```

Windows PowerShell:

```powershell
java -cp "app\target\classes;vendor-lib\vendor-sdk.jar" org.example.app.App
```

**Stdout chính xác của chương trình Java** sau khi chạy đúng:

```text
Hello, Maven (vendor)!
```

Dấu phân cách các entry classpath trên Linux/macOS là `:`, còn trên Windows là `;`. Khi chạy ứng dụng thực tế từ JAR, bạn cần chuẩn bị manifest/launcher/classpath hoặc cách đóng gói phù hợp. Ví dụ này dùng `target/classes` và một JAR rời để tránh nhầm rằng `mvn package` mặc định đã đưa mọi dependency vào `system-scope-app-1.0.0.jar`.

## 5. Điều gì xảy ra khi di chuyển hoặc xóa tệp JAR?

Giả sử JAR có tại:

```text
legacy-system-demo/vendor-lib/vendor-sdk.jar
```

Sau đó bạn đổi tên folder `vendor-lib`, chỉ checkout `app` trên máy khác hoặc CI không tạo `vendor-sdk.jar`. Khi chạy:

```bash
mvn -B -ntp -f app/pom.xml clean package
```

Maven không thể dùng dependency system vì tệp ở đường dẫn đã cấu hình không tồn tại. Lỗi có thể xuất hiện ngay khi xác thực mô hình, kiểm tra dependency hoặc biên dịch, tùy trường hợp; **đừng khẳng định rằng Maven sẽ tự tải bản khác từ Maven Central**.

Kiểm tra bằng công cụ hệ điều hành trước khi build.

Linux/macOS, từ thư mục `legacy-system-demo`:

```bash
test -f vendor-lib/vendor-sdk.jar && echo 'JAR exists'
```

PowerShell:

```powershell
Test-Path -LiteralPath "vendor-lib/vendor-sdk.jar" -PathType Leaf
```

Nếu file không tồn tại, hãy kiểm tra quy trình cung cấp file, chứ không chỉ chạy lại `mvn -U`. Tùy chọn cập nhật repository metadata không thể tạo ra một JAR cục bộ thiếu ở `systemPath`.

Đừng trông đợi `mvn clean` hay `mvn install` của ứng dụng sẽ tự sinh JAR vendor không có trong nguồn dự án. Trong ví dụ, JAR vendor được tạo **bằng `javac` và `jar` riêng** trước khi Maven build ứng dụng.

## 6. Cách Maven sử dụng tọa độ và classpath với system

Đây là điểm dễ hiểu nhầm:

```xml
<groupId>org.example.vendor</groupId>
<artifactId>vendor-sdk</artifactId>
<version>1.0.0</version>
<scope>system</scope>
<systemPath>${project.basedir}/../vendor-lib/vendor-sdk.jar</systemPath>
```

Maven vẫn giữ `groupId:artifactId:version` trong mô hình dependency, và các công cụ có thể hiển thị tọa độ đó. Nhưng **nguồn bytecode mà compiler dùng là file được `systemPath` chỉ ra**, không phải artifact repository mang tọa độ ấy.

Bản chất điều này gây ra những hạn chế:

- **Không tự giải quyết dependency bắc cầu:** tệp JAR rời không được Maven tìm POM metadata qua repository để xây dựng đầy đủ graph dependency của chính thư viện.
- **Không tự trở thành dependency truyền tiếp đáng tin cậy:** một dự án khác dùng JAR ứng dụng từ repository không thể mặc định nhận tệp system từ đường dẫn trên máy bạn.
- **Không tự publish:** việc `mvn install` hoặc `mvn deploy` chạy với ứng dụng không đồng nghĩa JAR vendor ở `systemPath` được upload thành artifact Maven độc lập.
- **Không tự package:** JAR mặc định của ứng dụng thường chỉ chứa bytecode và resources của ứng dụng; các dependency rời phải được cấp/đóng gói theo cơ chế khác.
- **Tọa độ không xác thực bytecode:** Maven không dùng version để kiểm tra rằng file cục bộ đúng là vendor SDK 1.0.0. Nếu ai đó thay file mà giữ tên, rủi ro khác biệt build tăng.

Trong các dự án lớn, hệ quả có thể là **build trên máy phát triển thành công nhưng deployment gặp `NoClassDefFoundError`**, vì quá trình đóng gói hoặc launch script không đưa JAR vendor vào runtime classpath.

Một scope được hỗ trợ trong Maven không đồng nghĩa phương thức quản lý artifact đó nên được chọn cho ứng dụng cần build tái lập.

## 7. So sánh system, provided, compile và test qua tình huống

### 7.1. `system`: tệp chỉ có trên một máy

Một SDK nằm trên ổ đĩa do chương trình cài đặt bên ngoài tạo:

```xml
<dependency>
    <groupId>org.example.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${env.VENDOR_HOME}/lib/vendor-sdk.jar</systemPath>
</dependency>
```

Ở đây `VENDOR_HOME` là biến môi trường được đặt **trước khi Maven chạy**. Nếu biến không có giá trị, đường dẫn sau nội suy có thể không hợp lệ. Trường hợp này giúp tránh hardcode đường dẫn, nhưng buộc mọi máy/CI phải cài SDK và cấu hình biến tương ứng.

Lưu ý: `${env.VENDOR_HOME}` chỉ đọc biến môi trường; nó **không tải SDK**, không xác nhận nội dung tệp và không đảm bảo Maven đã hiểu được giá trị nếu môi trường chưa đặt biến.

### 7.2. `provided`: artifact vẫn lấy qua repository, runtime do nền tảng cấp

Ví dụ một API mà container được kỳ vọng cung cấp:

```xml
<dependency>
    <groupId>org.example.platform</groupId>
    <artifactId>platform-api</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
</dependency>
```

Tọa độ chỉ mang tính minh họa. Maven giải quyết API theo repository; ứng dụng compile được nhờ artifact đó, nhưng khi chạy trên container, container phải thực sự cung cấp API phù hợp.

**Không dùng `system` chỉ vì một thư viện “được máy chủ cung cấp”.** Nếu thư viện có thể được xuất bản trong repository cho mục đích biên dịch, `provided` thường mô tả kỳ vọng runtime tốt hơn.

### 7.3. `compile`: thư viện thông thường

```xml
<dependency>
    <groupId>org.example.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
```

Không có `scope` nghĩa là `compile` theo mặc định. Với thư viện thật được publish vào repository, đây thường là lựa chọn khi ứng dụng dùng API lúc compile và cần mã lúc chạy.

### 7.4. `test`: thư viện chỉ dùng trong test

```xml
<dependency>
    <groupId>org.example.test</groupId>
    <artifactId>test-helper</artifactId>
    <version>1.0.0</version>
    <scope>test</scope>
</dependency>
```

Nếu chỉ unit tests cần `test-helper`, scope test tránh đưa nó thành dependency chính của ứng dụng.

**Chú ý:** thay `system` bằng `test` hoặc `provided` chỉ để loại bỏ cảnh báo **không đảm bảo đúng ngữ nghĩa**. Hãy xác định thư viện thực sự cần ở giai đoạn nào, ai cung cấp tại runtime và nó đã được publish ra repository hay chưa.

## 8. Những điểm khiến systemPath phụ thuộc máy

### 8.1. Đường dẫn tuyệt đối ghi cứng

Ví dụ:

```xml
<systemPath>C:/Users/alice/Desktop/sdk/vendor-sdk.jar</systemPath>
```

Đường dẫn trên chỉ có ý nghĩa trên máy hoặc ổ đĩa tương ứng. Máy đồng nghiệp thường khác username, ổ đĩa, folder hoặc quyền. Trên Linux/macOS, dạng đường dẫn Windows không có ý nghĩa như một absolute path hợp lệ.

Dùng `${project.basedir}` hoặc `${env.VENDOR_HOME}` giúp **mô tả đường dẫn theo ngữ cảnh**, nhưng tất cả máy vẫn phải cung cấp file có đúng bytecode.

### 8.2. Đường dẫn tương đối không được nội suy thành tuyệt đối

Ví dụ:

```xml
<systemPath>lib/vendor-sdk.jar</systemPath>
```

Lỗi: Maven yêu cầu `systemPath` là đường dẫn tuyệt đối sau nội suy. Không nên dựa vào thư mục hiện hành của terminal để giải thích một chuỗi tương đối. Có thể viết `${project.basedir}/lib/vendor-sdk.jar` cho ví dụ học tập, nhưng Maven có thể cảnh báo khi system dependency nằm **bên trong thư mục project**, vì POM đó khó giải quyết được ở dự án tiêu thụ khác.

### 8.3. JAR nằm trong repository Git

Một số dự án giữ `lib/vendor-sdk.jar` trong Git rồi dùng:

```xml
<systemPath>${project.basedir}/lib/vendor-sdk.jar</systemPath>
```

Cách này có thể làm checkout chạy được hơn, nhưng **không loại bỏ bản chất không khả chuyển** của system scope. Maven có thể cảnh báo rằng path trỏ vào thư mục dự án và sẽ không giải quyết được cho dự án khác phụ thuộc artifact này. Ngoài ra còn có các rủi ro về dung lượng Git, bản quyền phân phối, kiểm tra checksum, cập nhật bảo mật và SBOM.

Nếu thư viện được phép phân phối trong tổ chức, **private Maven repository** thường là nơi phù hợp hơn để quản lý binary artifact. Nếu giấy phép cấm upload hoặc phân phối lại, cần hỏi bên quản lý giấy phép và thiết kế quy trình cài đặt SDK trước khi chọn kiến trúc khác.

### 8.4. Đường dẫn của IDE khác đường dẫn của Maven

IDE có thể tự thêm một JAR trong cấu hình dự án, khiến người lập trình thấy code compile được trong IDE. Nhưng build Maven CLI/CI dùng **POM và môi trường của phiên Maven**. Nếu IDE classpath khác Maven classpath, kết quả sẽ khác nhau.

Nên đối chiếu:

- JDK mà IDE dùng.
- JDK mà `mvn -version` hiển thị.
- `systemPath` sau nội suy.
- File thực trên disk.
- POM/module thực sự được CLI chọn bằng `-f`.
- Classpath mà plugin compile/test/launcher sử dụng.

Không sửa IDE classpath như một giải pháp thay cho một POM sai nếu dự án phải được build bởi CI.

### 8.5. Docker/container và CI ephemeral runner

Một Docker image hoặc runner mới có filesystem riêng. File ở `C:/sdk` trên máy người dùng hoặc `/opt/vendor` trên host **không tự xuất hiện** bên trong container. Nếu mount volume hoặc copy file, cần kiểm tra quyền, kiến trúc, phiên bản và chính sách phân phối.

Đừng đưa secret hoặc binary có giấy phép hạn chế vào Docker build context công khai để “chữa” lỗi systemPath. Một dependency quản lý qua repository có thể cho phép pipeline kiểm soát quyền tải, phiên bản và cache tốt hơn.

## 9. Quan sát Maven đang dùng systemPath bằng công cụ nào?

### 9.1. Kiểm tra effective POM

```bash
mvn -f app/pom.xml help:effective-pom
```

Maven Help Plugin tạo mô hình POM có hiệu lực. Tìm dependency có `<scope>system</scope>` và `<systemPath>`; kiểm tra path được nội suy có đúng thư mục app và tên file không.

Không mặc định mọi placeholder đều đã được thay trong mọi ngữ cảnh plugin; với vấn đề filesystem, **kiểm tra trực tiếp file tồn tại** vẫn rất quan trọng.

### 9.2. Xem dependency tree của app

```bash
mvn -f app/pom.xml dependency:tree
```

Cây có thể hiển thị dependency `org.example.vendor:vendor-sdk:jar:1.0.0:system` (format có thể thay đổi theo phiên bản plugin). Điều này giúp biết dependency được khai báo trong graph của app, **nhưng không xác nhận**:
- JAR có được publish vào repository không;
- JAR có nằm trong artifact ứng dụng sau package không;
- Một máy khác có cùng file ở cùng đường dẫn không;
- File chứa đúng version thật hay không.

Goal `dependency:tree` có thể cần tải Maven Dependency Plugin lần đầu. Đừng nhầm lỗi tải **plugin Maven** từ repository với việc Maven cố tải **system dependency**.

### 9.3. Kiểm tra class bên trong JAR

Từ root ví dụ:

```bash
jar --list --file vendor-lib/vendor-sdk.jar
```

Kết quả cần có entry `org/example/vendor/VendorGreeting.class`. Nếu thiếu class, bạn có thể đã trỏ đến JAR sai dù file có tồn tại.

Để kiểm tra JDK, dùng:

```bash
java -version
javac -version
mvn -version
```

Trên Java 17+, `java` và `javac` phải phù hợp với bytecode của thư viện. File tồn tại không bảo đảm binary tương thích JDK/kiến trúc hoặc API mà code cần.

## 10. Hướng thay thế 1: cài JAR vào local Maven repository

Nếu bạn có JAR và cần thử nhanh trên **một máy**, Maven Install Plugin cho phép gán tọa độ và cài tệp vào local repository:

```bash
mvn org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file \
  -Dfile=vendor-lib/vendor-sdk.jar \
  -DgroupId=org.example.vendor \
  -DartifactId=vendor-sdk \
  -Dversion=1.0.0 \
  -Dpackaging=jar
```

Lệnh này được viết theo cú pháp dòng nối `\` của Bash trên Linux/macOS, chạy từ thư mục `legacy-system-demo`. Trong Windows PowerShell, viết **một dòng** để không nhầm cách xuống dòng của shell:

```powershell
mvn org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor-lib/vendor-sdk.jar -DgroupId=org.example.vendor -DartifactId=vendor-sdk -Dversion=1.0.0 -Dpackaging=jar
```

Maven Install Plugin đọc JAR thật từ `vendor-lib/vendor-sdk.jar` và cài artifact/POM metadata phù hợp vào **local repository của người đang chạy Maven**. Vị trí local repository có thể được cấu hình qua settings, không nhất thiết luôn là `~/.m2/repository`.

Sau khi install-file thành công, thay dependency của app bằng:

```xml
<dependency>
    <groupId>org.example.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
```

**Đã bỏ cả `scope=system` và `systemPath`.** Không khai báo scope nên Maven dùng `compile` mặc định. Compiler sẽ tìm dependency theo tọa độ trong repository; không còn cần `systemPath` của POM app.

**Nhưng đây chưa phải giải pháp đủ cho team hoặc CI.** Install-file chỉ cài vào cache của **máy đã chạy lệnh**. Một developer khác hoặc CI runner sạch chưa có artifact này. Bạn phải cung cấp một quy trình cài riêng cho từng máy hoặc tốt hơn là publish artifact vào một repository dùng chung theo quyền và giấy phép cho phép.

### Ưu điểm của bước trung gian

- POM app trở nên gần với khai báo Maven chuẩn hơn.
- Có thể dùng các scope thông thường.
- Dễ thử nghiệm việc đổi dependency mà không cần thay code ứng dụng.
- Có thể dùng `dependency:tree` và các công cụ Maven khác theo tọa độ.

### Giới hạn của bước trung gian

- Local repository **không tự đồng bộ** giữa developer và runner.
- Nếu người khác tự cài một file khác dưới cùng tọa độ, chất lượng build vẫn không được bảo đảm.
- POM metadata tối thiểu được tạo khi cài JAR rời có thể không mô tả chính xác các dependency bắc cầu của SDK thật. Nếu nhà cung cấp có POM đi kèm, cần sử dụng metadata hợp lệ thay vì giả định thư viện không có dependency nào.
- Không được cài/redistribute một thư viện trái giấy phép hoặc chính sách bảo mật chỉ vì công cụ Maven hỗ trợ.

Đây là **cách chuyển tiếp để kiểm tra** chứ không phải giải pháp quản trị artifact ở quy mô tổ chức.

## 11. Hướng thay thế 2: dùng private Maven repository

Khi dự án cần nhiều developer và CI, **repository quản lý artifact nội bộ** là lựa chọn thường được Apache Maven khuyến nghị thay vì `system`.

Mô hình:

```text
Nhà cung cấp / artifact được phê duyệt
                   |
                   v
       Kiểm tra license, checksum,
       provenance và phiên bản
                   |
                   v
      Private Maven repository
      - groupId: org.example.vendor
      - artifactId: vendor-sdk
      - version: 1.0.0
                   |
       +-----------+-----------+
       |                       |
       v                       v
 Developer A                 CI runner
 mvn package                 mvn verify
       |                       |
       +------- cùng GAV -------+
```

Khi có quyền phân phối hợp lệ, nhóm quản trị có thể publish JAR và POM metadata đúng vào repository được phép truy cập. Project dùng dependency Maven thông thường:

```xml
<dependency>
    <groupId>org.example.vendor</groupId>
    <artifactId>vendor-sdk</artifactId>
    <version>1.0.0</version>
</dependency>
```

Maven cấu hình repository hoặc mirror, credentials theo thiết lập phù hợp của tổ chức. Nếu build có mạng và quyền truy cập, các máy có thể giải quyết cùng tọa độ thay vì tự biết đường dẫn JAR cục bộ.

Điều cần quản lý:

1. **GAV và version ổn định:** không thay nội dung JAR đã publish ở cùng một release coordinate.
2. **POM metadata chính xác:** nếu SDK có dependency bắc cầu, khai báo đúng để Maven Resolution hoạt động.
3. **Quyền truy cập:** credentials trong settings/CI secret store, không hardcode password trong POM.
4. **Nguồn gốc:** xác minh checksum/chữ ký/phê duyệt nhà cung cấp nếu có.
5. **Giấy phép:** chỉ upload và phân phối lại khi có quyền.
6. **Quét bảo mật/SBOM:** đảm bảo artifact được nhận diện, đánh giá và cập nhật.
7. **Vòng đời:** có quy trình nâng cấp, thu hồi hoặc thay thế phiên bản nếu phát hiện lỗi.

Lợi ích không chỉ là “build chạy được trên mọi máy”; một artifact được quản lý tốt giúp truy vết dependency, cập nhật phiên bản và áp dụng chính sách nhất quán hơn.

## 12. Hướng thay thế 3: nếu có mã nguồn, tạo module Maven

Nếu team **sở hữu mã nguồn** của thư viện và có quyền build nó, có thể tạo một module Maven thay vì đóng JAR bằng tay.

Ví dụ:

```text
multi-module/
├── pom.xml
├── vendor-adapter/
│   ├── pom.xml
│   └── src/main/java/...
└── app/
    ├── pom.xml
    └── src/main/java/...
```

POM aggregator có `<modules>` cho hai module; POM `app` khai báo dependency theo tọa độ của `vendor-adapter`, scope bình thường. Maven reactor xử lý thứ tự build và có thể cung cấp artifact của module upstream trong cùng invocation.

**Đừng nhầm aggregation với dependency**: chỉ đưa module vào `<modules>` không tự đặt classes của nó vào classpath `app`. App vẫn phải khai báo `<dependency>` đúng tọa độ.

Phương án này phù hợp khi bạn thật sự quản lý source và muốn dùng build/release Maven thống nhất. Nó không giải quyết quyền phân phối của một SDK thương mại mà bạn không có mã nguồn hay giấy phép chia sẻ.

## 13. Tại sao system không thay thế dependency management?

Một số POM có `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.vendor</groupId>
            <artifactId>vendor-sdk</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`dependencyManagement` giúp quản lý version và metadata dependency khi chúng được tham chiếu phù hợp, **không tự tạo file JAR** và không đưa một dependency mới vào classpath nếu không có khai báo/đường dẫn dependency tương ứng.

Nếu app tiếp tục dùng `scope=system` và `systemPath`, quản lý version trong parent **không khiến Maven tải JAR từ repository**. Muốn bỏ ràng buộc tệp cục bộ, phải chuyển dependency sang cơ chế repository bình thường hoặc thiết kế khác được quản trị hợp lệ.

Tương tự, `repositories`, `mirrors` và `settings.xml` không thay thế cơ chế systemPath. Những thiết lập đó điều khiển resolution của repository artifacts, **không quyết định một thư viện system sẽ tự xuất hiện ở filesystem**.

## 14. Cơ chế classpath và rủi ro sau khi đóng gói

Trong Java, **compile classpath** giúp compiler tìm class và API lúc tạo `.class`; **runtime classpath** giúp JVM nạp class khi ứng dụng chạy.

Với ví dụ:

```text
app/src/main/java/org/example/app/App.java
    |
    | import org.example.vendor.VendorGreeting
    v
vendor-lib/vendor-sdk.jar
```

Khi Maven compile, dependency system có thể cấp bytecode `VendorGreeting` cho compiler. Nhưng sau khi `mvn package` tạo file:

```text
app/target/system-scope-app-1.0.0.jar
```

JAR ứng dụng thông thường **không tự chứa thư viện vendor**. Nếu chạy bằng một launcher không có JAR vendor trong classpath, ứng dụng có thể thất bại khi gọi class của vendor.

Những điều cần kiểm tra khi phát hành:
- Runtime JVM có được cung cấp đúng JAR vendor hay không?
- Launcher, container, WAR hoặc distribution có đặt JAR đúng chỗ không?
- Bản vendor JAR có tương thích với JDK và ứng dụng không?
- Khi tạo fat JAR hoặc container image, plugin có thực sự đóng gói dependency này theo chính sách không?
- Máy chạy có giấy phép dùng SDK/driver thương mại không?

**Một build thành công không tự chứng minh sản phẩm có thể triển khai ở nơi khác.** Đây là rủi ro chung của việc phụ thuộc vào tệp cục bộ mà không có quy trình phân phối và kiểm chứng.

## 15. Lỗi thường gặp và cách sửa

### Lỗi 1 — `systemPath` là đường dẫn tương đối

```xml
<systemPath>lib/vendor-sdk.jar</systemPath>
```

Maven yêu cầu absolute path sau nội suy. Dùng một thuộc tính đường dẫn hợp lệ như `${project.basedir}` nếu chỉ cần chẩn đoán/duy trì một ví dụ cục bộ; với dự án thật, ưu tiên bỏ `system`.

### Lỗi 2 — Nhầm `project.basedir` với thư mục chạy terminal

Nếu bạn ở root `legacy-system-demo` nhưng dùng `-f app/pom.xml`, `project.basedir` vẫn tham chiếu thư mục Maven project `app`. Đường dẫn `../vendor-lib` đi từ `app` lên thư mục cha, không đi từ current working directory tùy ý.

### Lỗi 3 — Cài JAR vào `~/.m2` nhưng POM vẫn là `system`

Maven vẫn đi theo `systemPath`. Không tự chuyển sang repository chỉ vì bản tương ứng xuất hiện trong local Maven repository. Để sử dụng artifact đã cài, xóa `systemPath`, đổi sang dependency scope bình thường và kiểm tra tọa độ.

### Lỗi 4 — Sao chép đường dẫn Windows sang Linux

Một đường dẫn `C:/...` không giải quyết được trên Linux. Ngay cả đường dẫn cục bộ có vẻ tương đối “đa nền tảng” vẫn cần JAR thật tồn tại trên máy và đúng quyền truy cập.

### Lỗi 5 — Chỉ commit POM, quên cấp file JAR cho CI

Một fresh checkout không có các tệp SDK cục bộ ngoài Git. Nếu không có cơ chế lấy được SDK theo giấy phép, CI có thể thất bại trước compile. Hãy chuẩn hóa nguồn cấp artifact bằng repository hoặc quy trình cài đặt SDK được phép.

### Lỗi 6 — Đổi tên JAR nhưng không đổi `systemPath`

Maven tìm đúng đường dẫn đã khai báo, không quét thư mục rồi đoán file có cùng API. Cần kiểm tra tên thực, đường dẫn và quyền đọc.

### Lỗi 7 — Ghi version 2.0 nhưng tệp vẫn là bytecode 1.0

`version` trong POM system không xác minh nội dung JAR được chỉ định. Việc đổi tag version có thể tạo cảm giác an toàn giả. Dùng checksum và provenance để quản lý binary.

### Lỗi 8 — Cho rằng system dependency tự truyền bắc cầu cho consumer

Artifact app được publish sang repository không mang theo file JAR ở đường dẫn máy tạo build. Consumer khác có thể không giải quyết được dependency đó. Không dùng system như một hợp đồng phân phối thư viện.

### Lỗi 9 — Dùng `mvn -U` để sửa lỗi thiếu system JAR

`-U` ảnh hưởng một số kiểm tra cập nhật liên quan repository; nó không có khả năng sinh/tải file chỉ định ở systemPath. Cần sửa nguồn cung cấp JAR hoặc chuyển sang dependency repository.

### Lỗi 10 — Dùng `system` thay cho `provided` với API có trong repository

Nếu một API do servlet container cung cấp nhưng có artifact được publish, khai báo `provided` thường phù hợp hơn. System chỉ làm build phụ thuộc vào một file cục bộ không cần thiết.

### Lỗi 11 — Đóng gói JAR ứng dụng rồi tin rằng đã có JAR vendor bên trong

Maven JAR Plugin mặc định không tạo uber JAR. Kiểm tra file artifact, manifest, runtime classpath và cơ chế đóng gói. Trong ví dụ dùng `java -cp` để đưa JAR vendor vào rõ ràng.

### Lỗi 12 — Đưa binary có giấy phép hạn chế vào Git hoặc container image công khai

Maven chạy được không đồng nghĩa tổ chức có quyền phân phối lại SDK. Xem license và quy trình kiểm duyệt nội bộ trước khi upload lên repository, Git hoặc image registry.

### Lỗi 13 — Dùng shell command tạo JAR nhưng không kiểm tra exit code

Nếu lệnh `javac` thất bại mà script vẫn chạy `jar` với thư mục classes cũ, có thể tạo ra binary không đúng. Trong CI, dừng khi bước biên dịch/thao tác sinh artifact báo lỗi; nếu cần, xóa thư mục output cũ trước khi build.

### Lỗi 14 — Chỉ so tên file mà bỏ qua SHA-256/checksum

Hai file cùng tên có thể khác bytecode. Khi phải xử lý binary vendor, lập danh mục version/checksum, nguồn cung cấp và giấy phép. Việc kiểm tra checksum không thay thế kiểm chứng chữ ký/nguồn gốc nếu chính sách yêu cầu cao hơn.

## 16. Checklist chuyển từ system sang repository dependency

Đối với một dự án đang dùng `scope=system`, quy trình chuyển đổi nên bao gồm:

1. **Liệt kê các dependency system** trong POM hiện tại và parent, kiểm tra effective POM ở đúng module.
2. **Xác định tệp và quyền sử dụng**: tên nhà cung cấp, phiên bản, nguồn cấp, license, checksum, lớp Java mà ứng dụng cần.
3. **Kiểm tra có artifact tương ứng trong Maven repository hay không**, nhưng không thay bằng dependency có tên giống nhau mà chưa xác minh API.
4. Nếu chỉ cần thử trên một máy, dùng `install:install-file` để kiểm chứng tọa độ và cấu hình mới.
5. Nếu cần team/CI, **publish lên private repository** theo quy trình được cấp phép, kèm metadata phù hợp.
6. **Đổi POM** từ system sang scope đúng: bỏ `<scope>system</scope>` và `<systemPath>`; thêm scope thích hợp nếu không dùng mặc định compile.
7. **Kiểm tra dependency graph/classpath** của đúng module bằng `dependency:tree` và goal cần thiết.
8. **Chạy build trên môi trường sạch** để xác minh không dựa vào tệp máy cá nhân hoặc cache được cài thủ công.
9. **Kiểm tra runtime/packaging**, vì compile thành công không có nghĩa mọi binary cần thiết đã được phân phối.
10. **Đánh giá CI, bảo mật và giấy phép** trước khi chuyển pipeline phát hành sang dùng repository mới.

Nếu thư viện bị ràng buộc bởi installer hoặc chính sách không được upload, có thể vẫn cần một bước cài đặt SDK trên runner/host. Nhưng khi đó nên xem đây là **ràng buộc hệ thống được mô tả và quản lý**, với bước kiểm tra tồn tại/phiên bản/checksum, không coi `systemPath` là thay thế cho quản trị dependency chuẩn.

## 17. Bài tập kiểm tra kiến thức

**Câu 1.** POM khai báo `org.example.vendor:vendor-sdk:1.0.0` với `scope=system`. Local Maven repository đã có tọa độ này, nhưng `systemPath` trỏ đến JAR không tồn tại. Maven có tự dùng bản từ repository không?

**Đáp án:** Không theo cơ chế system scope. Maven vẫn kỳ vọng tệp ở đường dẫn đã chỉ định; cần cấp đúng file hoặc chuyển sang dependency scope repository thông thường.

**Câu 2.** Vì sao `${project.basedir}/lib/vendor-sdk.jar` có thể khiến build chạy trên hai máy nhưng vẫn không được xem là phương pháp portable tốt?

**Đáp án:** Hai máy vẫn phải có cùng file đúng nội dung, giấy phép và cấu trúc; hệ thống build không quản lý việc phân phối JAR bằng repository resolution. Maven cũng có thể cảnh báo khi dependency system nằm ngay trong thư mục project.

**Câu 3.** Khi app được đóng gói thành JAR, có chắc JAR vendor được chép vào file đó không?

**Đáp án:** Không. Đóng gói `jar` mặc định không tạo fat/uber JAR. Cần kiểm tra launcher/runtime classpath hoặc plugin đóng gói thực tế.

**Câu 4.** Scope `system` và `provided` khác nhau ở điểm nguồn artifact nào?

**Đáp án:** `system` yêu cầu tệp ở `systemPath` và không tải từ repository; `provided` thường vẫn giải quyết artifact theo tọa độ Maven nhưng giả định nền tảng sẽ cung cấp API ở runtime.

**Câu 5.** Nếu một máy dùng `/opt/sdk/vendor-sdk.jar` và một máy khác dùng `D:/sdk/vendor-sdk.jar`, khai báo absolute path cố định có vấn đề gì?

**Đáp án:** Đường dẫn phụ thuộc máy/OS. Dùng property hoặc biến môi trường có thể giảm hardcode, nhưng để build tái lập tốt hơn cần quản lý artifact/phiên bản qua repository hoặc một quy trình cung cấp SDK thống nhất.

**Câu 6.** Dùng `mvn install:install-file` có làm JAR xuất hiện trên mọi máy CI không?

**Đáp án:** Không. Nó cài artifact vào local repository của máy chạy lệnh. CI khác cần cài riêng hoặc lấy artifact từ remote repository được quản lý.

**Câu 7.** Sau khi chuyển dependency từ system sang compile trong POM, bạn có được giữ `<systemPath>` để “dự phòng” không?

**Đáp án:** Không. `systemPath` chỉ hợp lệ trong dependency system; với dependency repository thông thường phải bỏ nó.

**Câu 8.** Một SDK không được phân phối lại theo giấy phép. Bạn có nên upload nó lên Maven Central hoặc public Git chỉ để CI chạy được không?

**Đáp án:** Không. Cần tuân thủ giấy phép và chính sách tổ chức; cân nhắc quy trình cung cấp SDK được cấp phép trên runner hoặc repository hạn chế có quyền phù hợp nếu được phép.

**Câu 9.** Nếu app source có `import org.example.vendor.VendorGreeting;` nhưng Maven báo không tìm thấy package, bạn sẽ kiểm tra gì trước?

**Đáp án:** Kiểm tra systemPath sau nội suy, file có tồn tại không, JAR có class đúng package không, JDK/compiler có phù hợp không và lệnh Maven có đang chọn đúng POM không.

**Câu 10.** Vì sao một dependency `system` có version trong POM vẫn cần kiểm tra checksum tệp?

**Đáp án:** Maven không dùng version của tọa độ để xác minh binary nằm ở đường dẫn hệ thống. Tệp có thể bị thay dù giữ nguyên tên/version.

## Tài liệu tham khảo chính thức

- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): các scope; mục *System Dependencies* giải thích cách dùng systemPath và vì sao Apache Maven không khuyến nghị.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): `scope`, `systemPath`, yêu cầu absolute path và cách Maven kiểm tra tệp.
- [Apache Maven – Dependencies](https://maven.apache.org/repositories/dependencies): khái niệm dependency, scope và classpath.
- [Apache Maven Install Plugin – Installing 3rd party JARs](https://maven.apache.org/guides/mini/guide-3rd-party-jars-local.html): cách đưa JAR ngoài Maven vào local repository.
- [Apache Maven Install Plugin – install:install-file](https://maven.apache.org/plugins/maven-install-plugin/install-file-mojo.html): các tham số file, groupId, artifactId, version và packaging.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): quan sát dependency graph theo module.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): aggregation, reactor và quan hệ module.
