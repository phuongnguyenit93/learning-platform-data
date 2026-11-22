# Thư viện JAR cục bộ: giới hạn của systemPath và cách quản lý qua kho Maven

## 1. Tình huống: có file .jar nhưng không có trên Maven Central

Một nhóm nhận thư viện Java dạng nhị phân từ đối tác, chẳng hạn `legacy-math-1.0.0.jar`. Bên cung cấp không phát hành nó lên Maven Central, nhưng ứng dụng cần import một class nằm trong JAR để biên dịch.

Một giải pháp nhanh thường thấy là đặt file trong thư mục `lib/` rồi khai báo dependency có `<scope>system</scope>` và `<systemPath>` trong `pom.xml`. Cách này có thể giúp dự án **biên dịch trên máy đã có file**, nhưng dễ khiến CI, máy đồng đội, IDE, container build và những module dùng lại thư viện bị lỗi.

Maven chính thức hỗ trợ `system` scope nhưng **không khuyến nghị sử dụng**. Hướng đi nên ưu tiên là quản lý nhị phân bằng tọa độ Maven `groupId:artifactId:version` (**GAV**) và kho artifact, thay vì ràng buộc POM với một vị trí trên đĩa cứng.

Bài này hướng dẫn từ tình huống có JAR đơn lẻ tới cách quản lý tương thích Maven:

1. Hiểu `system` scope, `systemPath`, cách Maven tìm JAR và giới hạn thực tế.
2. Phân biệt thư mục `lib/` của dự án, Maven local repository và remote repository.
3. Đưa JAR không có trên Maven Central vào local repository bằng `maven-install-plugin:install-file`.
4. Khai báo dependency Maven bình thường và tự kiểm chứng bằng mã Java 17.
5. Xuất bản JAR của bên thứ ba lên repository nội bộ qua `maven-deploy-plugin:deploy-file` để CI/đồng đội có thể tải.
6. Quản lý metadata POM, dependencies transitively, version, checksum, license và quyền truy cập.
7. Chẩn đoán các lỗi thường gặp và lập kế hoạch thay thế dần `systemPath` trong dự án hiện có.

**Thông điệp chính:** local repository chỉ làm cho **một máy** phân giải được dependency. Remote repository có kiểm soát mới là cách phổ biến để **mọi môi trường build** truy cập cùng một artifact có phiên bản rõ ràng.

## 2. Ba cách đưa thư viện JAR vào một ứng dụng Maven

| Cách | Maven lấy JAR từ đâu? | Dùng ở đâu? | Nhược điểm chính |
| --- | --- | --- | --- |
| `scope=system` + `systemPath` | Đường dẫn file cố định trên máy | Tình huống tạm thời, rất hạn chế | Không qua Maven repository, build phụ thuộc đường dẫn; không có metadata dependency transitively |
| `install:install-file` rồi dependency bình thường | Local Maven repository của máy | Phát triển/kiểm thử trên một máy | CI và máy khác không tự có bản JAR đó |
| `deploy:deploy-file` lên kho riêng rồi dependency bình thường | Hosted remote repository được khai báo/được mirror | Nhóm phát triển, CI, artifact dùng chung | Cần quản lý kho, quyền publish, metadata, bảo mật và chính sách phiên bản |

Maven local repository thường nằm tại:

~~~text
~/.m2/repository/
~~~

trên Linux/macOS, và tương đương `%USERPROFILE%\.m2\repository` trên Windows. Đường dẫn thực tế có thể đổi qua Maven settings hoặc `-Dmaven.repo.local`.

Một dependency có GAV `dev.vendor:legacy-math:1.0.0` thường được lưu theo layout:

~~~text
~/.m2/repository/
└── dev/
    └── vendor/
        └── legacy-math/
            └── 1.0.0/
                ├── legacy-math-1.0.0.jar
                └── legacy-math-1.0.0.pom
~~~

**Quan trọng:** thư mục `lib/` trong project **không phải** local Maven repository, dù đều là thư mục trên máy. Chép JAR vào `lib/` không tự biến nó thành dependency theo GAV. Cũng không nên tự chép file vào một đường dẫn đoán trước dưới `.m2/repository`, vì Maven repository còn có cấu trúc POM, metadata, checksum và trạng thái resolver.

## 3. system scope và systemPath hoạt động như thế nào?

Ví dụ phụ thuộc trực tiếp vào JAR cục bộ:

~~~xml
<dependencies>
    <dependency>
        <groupId>dev.vendor</groupId>
        <artifactId>legacy-math</artifactId>
        <version>1.0.0</version>
        <scope>system</scope>
        <systemPath>${project.basedir}/lib/legacy-math-1.0.0.jar</systemPath>
    </dependency>
</dependencies>
~~~

Đây là một đoạn bên trong `<project>` của POM. Với project có file ở đường dẫn tương ứng, Maven có thể đưa JAR đó vào classpath biên dịch.

Ý nghĩa:

- `groupId`, `artifactId`, `version` vẫn được khai báo, nhưng **Maven không tìm JAR qua repository** khi dependency mang `scope=system`.
- `systemPath` chỉ rõ file vật lý trên đĩa. Với dependency hệ thống, Maven yêu cầu đường dẫn file được giải quyết thành đường dẫn tuyệt đối; sử dụng `${project.basedir}` giúp biến nó thành đường dẫn tuyệt đối cho dự án hiện tại.
- Nếu file không tồn tại, đã đổi tên hoặc bị xóa, Maven không thể giải quyết dependency.
- `system` làm dependency có mặt trong một số classpath biên dịch và chạy của **chính dự án khai báo**, nhưng nó không tự biến nhị phân thành một dependency có khả năng chia sẻ qua repository.
- `system` scope không được sử dụng để quản lý các dependency transitively qua POM của thư viện như một dependency bình thường.
- `systemPath` chỉ có ý nghĩa với `scope=system`; thêm nó bên cạnh `scope=compile` sẽ không buộc Maven dùng file đó.

### 3.1. Những cảnh báo thường gặp

Maven có thể đưa ra cảnh báo tương tự:

~~~text
'dependencies.dependency.systemPath' ... should not point at files within the project directory
~~~

Vì khi file nằm trong dự án, đường dẫn của nó có thể không còn hợp lệ đối với project tiêu thụ POM này như một dependency. Văn bản log chính xác phụ thuộc Maven version và đường dẫn, nhưng bản chất cảnh báo là: **POM không di động**.

Đừng hiểu việc `mvn package` thành công trên laptop là bằng chứng cách cấu hình `systemPath` phù hợp để chia sẻ hoặc đưa lên production.

### 3.2. Scope system khác compile, provided, runtime, test

| Scope | Đặc điểm quan trọng |
| --- | --- |
| `compile` | Mặc định; Maven resolver lấy artifact từ repository; có thể tham gia dependency transitively theo quy tắc |
| `provided` | Cần cho biên dịch/test; runtime container/JDK dự kiến cung cấp; không nằm trong runtime dependency classpath của Maven |
| `runtime` | Không dùng để compile source chính, dùng ở runtime/test |
| `test` | Phục vụ biên dịch/chạy tests; không cho runtime ứng dụng |
| `system` | Dùng file JAR có đường dẫn cục bộ, bỏ qua phân giải qua repository; không nên dùng làm cơ chế phát hành |
| `import` | Chỉ có ý nghĩa trong `dependencyManagement` cho dependency có `type=pom`, thường để nhập BOM |

Không dùng `system` chỉ vì thư viện là “thư viện riêng của công ty”; thư viện riêng **vẫn nên** được xuất bản ở private Maven repository và khai báo `compile`, `runtime` hoặc `test` theo nhu cầu thật.

### 3.3. Lịch sử Java EE không áp dụng nguyên xi cho Java 17+

Một số tài liệu cũ từng minh họa `systemPath` trỏ đến các JAR nằm trong JDK, ví dụ `rt.jar` của Java 8. **Java 9 trở lên, trong đó có Java 17, không còn cấu trúc `rt.jar` như trước**. Không copy cấu hình `${java.home}/lib/rt.jar` từ dự án lịch sử sang dự án Java hiện đại. API thuộc JDK không cần tự khai báo dependency system; thư viện Java EE/Jakarta EE bên ngoài JDK cần dependency và scope phù hợp.

## 4. Rủi ro của systemPath trong dự án thật

### 4.1. Build phụ thuộc máy

Nếu đường dẫn là `C:\vendor\lib\legacy.jar`, máy Linux hoặc runner CI có thể không có file tương ứng. Ngay cả đường dẫn tương đối qua `${project.basedir}` cũng chỉ đúng với thư mục của project hiện tại.

Hai developer có thể cùng `pom.xml` nhưng file JAR tại cùng đường dẫn lại chứa **các byte khác nhau**, ví dụ một người được đối tác gửi bản vá ngoài phiên bản. Khi đó cả hai đều ghi `version=1.0.0` nhưng thực chất đang build trên hai nhị phân không giống nhau.

### 4.2. Không có metadata dependency như artifact từ kho

File `.jar` chỉ chứa bytecode và resource; bản thân nó không đảm bảo có POM mô tả các dependency transitively, license, version phối hợp hoặc dependency exclusions. `scope=system` không cung cấp cho Maven một artifact chuẩn để resolver truy được thông tin này.

Nếu `legacy-math.jar` thực sự cần `commons-io.jar` ở runtime, compiler có thể thấy class trong JAR nhưng khi chạy ứng dụng phát sinh `NoClassDefFoundError` vì dependency thứ hai không được khai báo hoặc không có trên classpath.

### 4.3. Dự án khác không tự dùng lại được

Một module A khai báo system-scoped dependency không khiến module B phụ thuộc A **tự tải** file system path đó trên máy khác. POM của thư viện A chứa đường dẫn vốn mang nghĩa trên môi trường đã build A, không bảo đảm tiêu thụ được khi phát hành A.

### 4.4. Khó triển khai, đóng gói và kiểm toán

Plugin đóng gói shaded/assembly, Docker image và plugin tạo runtime có cách xử lý dependency khác nhau. Không nên giả định system-scoped JAR tự động nằm trong fat JAR hoặc mọi kiểu package. Phải kiểm tra output thực tế và classpath runtime.

Công cụ SBOM, vulnerability scanning và license compliance cũng làm việc tốt hơn khi artifact có định danh/version và provenance rõ ràng. JAR được copy tay dễ bị mất nguồn gốc, thiếu thông tin phiên bản và tạo lỗ hổng kiểm toán.

### 4.5. Bảo mật và pháp lý

Một file được gửi qua email hoặc trang tải không đáng tin có thể chứa mã độc hoặc lớp đã bị sửa. Trước khi đưa lên kho nội bộ: xác minh nhà cung cấp, license/quyền được phép phân phối nội bộ, chữ ký hoặc checksum từ nguồn tin cậy, rà soát vulnerability và lưu hồ sơ nguồn gốc. **Có checksum chỉ chứng minh file chưa thay đổi so với checksum tham chiếu, không chứng minh nhà phát hành đáng tin nếu cả hai đến từ cùng nguồn không đáng tin.**

## 5. Cách 1: cài một JAR vào local Maven repository bằng install-file

Đây là giải pháp **đúng chuẩn tọa độ Maven** khi bạn cần kiểm thử trên một máy. Apache Maven Install Plugin cung cấp goal `install:install-file` cho các thư viện không có ở repository.

Lệnh ví dụ với Maven Install Plugin **3.2.0**:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor/build/legacy-math-1.0.0.jar -DgroupId=dev.vendor -DartifactId=legacy-math -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true
~~~

Đây là một lệnh một dòng, chạy ở thư mục chứa file JAR. Tham số:

| Tham số | Vai trò |
| --- | --- |
| `-Dfile=...` | Đường dẫn JAR nhị phân cần cài |
| `-DgroupId=dev.vendor` | Namespace artifact |
| `-DartifactId=legacy-math` | Tên artifact |
| `-Dversion=1.0.0` | Phiên bản được quản lý |
| `-Dpackaging=jar` | Loại file/packaging |
| `-DgeneratePom=true` | Tạo POM tối thiểu nếu không có POM đi kèm |

Maven sẽ đưa artifact và POM metadata vào **local repository hiện tại**. Plugin `install-file` là cách được thiết kế cho JAR của bên thứ ba; **không** đồng nhất với `mvn install`: `mvn install` chạy lifecycle của dự án đang được build, còn `install-file` nhận một file nhị phân có sẵn.

Nếu đã có **POM thật từ nhà cung cấp**, ưu tiên dùng `-DpomFile` thay vì tạo POM tối thiểu:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor/build/legacy-math-1.0.0.jar -DpomFile=vendor/legacy-math-1.0.0.pom
~~~

POM thật có thể mô tả GAV, license và các dependency mà nhị phân cần. Nhưng không được tự tin dùng POM lấy từ nguồn không xác thực: **phải kiểm tra metadata và tính tương thích với đúng JAR**. Nếu file POM của nhà cung cấp thiếu hoặc sai dependency, cần bổ sung theo bằng chứng thay vì mặc định Maven tự suy ra từ bytecode.

### 5.1. Tọa độ artifact quan trọng hơn tên file

File đầu vào `legacy-math-1.0.0.jar` được cài theo GAV mà bạn truyền; Maven dùng GAV để xây tên file trong repository. Không nên chọn GAV giả mạo của một artifact công khai: có thể tạo collision hoặc dependency confusion khi sau này thêm repository.

Quy tắc khuyến nghị:

- Chọn `groupId` trong namespace do tổ chức kiểm soát, ví dụ `com.example.vendor` hoặc `dev.company.thirdparty`, tùy chính sách.
- Duy trì `artifactId` ổn định cho cùng thư viện.
- Dùng `version` phản ánh đúng bản phát hành nhị phân; nếu vendor phát hành patch mới, dùng version mới thay vì âm thầm thay byte của release cũ.
- Nếu có classifier `tests`, `sources` hoặc `native`, quản lý đúng classifier/extension thay vì đổi tên file tùy tiện.

### 5.2. Không nên cài đi cài lại vào cùng GAV với byte khác

`install-file` có thể làm thay đổi artifact cục bộ của cùng một tọa độ. Nếu trên máy A file `dev.vendor:legacy-math:1.0.0` là một nhị phân và máy B là nhị phân khác, build không còn tái lập.

Khi nhận một bản binary mới: kiểm tra checksum và nguồn, quyết định version mới, cập nhật POM consumer theo version mới; không âm thầm ghi đè version đã phát hành. Có thể ghi lại SHA-256 trong hồ sơ quản lý artifact hoặc cơ chế provenance của repository.

### 5.3. Local repository không đồng bộ sang CI

Sau khi cài thành công, project trên máy đó phân giải được dependency. Nhưng thư mục `~/.m2/repository` **không được commit vào Git và không được tự động chia sẻ** với CI.

Nếu CI chạy trên runner sạch, Maven sẽ không tìm được artifact chỉ có trong repository cục bộ của laptop. Đó không phải lỗi compile: đó là **thiếu nguồn phân phối artifact**. Cần deploy lên remote repository, hoặc trong trường hợp thử nghiệm đặc biệt phải có bước cài file hợp lệ và kiểm soát trên từng môi trường.

## 6. Thực hành chạy được trên Java 17: tạo JAR và dùng qua local repository

Ví dụ có hai phần:

- **vendor:** tạo một JAR Java 17 thuần bằng `javac`/`jar`, giả lập file nhị phân do bên thứ ba giao.
- **consumer:** ứng dụng Maven khai báo dependency chuẩn bằng GAV, không dùng `systemPath`.

Mục tiêu là tự chứng minh JAR được tìm qua local repository. Không cần JUnit hay thư viện ngoài; cần JDK 17+ và Maven có thể tải plugin trong lần đầu.

Cấu trúc:

~~~text
local-jar-lab/
├── vendor/
│   ├── src/dev/vendor/LegacyMath.java
│   └── build/                       (được tạo khi biên dịch)
└── consumer/
    ├── pom.xml
    └── src/main/java/dev/consumer/Main.java
~~~

### 6.1. Viết class sẽ được đóng gói trong JAR

Tạo `vendor/src/dev/vendor/LegacyMath.java`:

~~~java
package dev.vendor;

public final class LegacyMath {
    private LegacyMath() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
~~~

Class có một phương thức `add` trả tổng hai số. Không dùng thư viện khác, nên JAR thử nghiệm này **không có dependency runtime bổ sung**.

### 6.2. Dùng javac và jar để tạo nhị phân

Chạy từ **`local-jar-lab`** trên Linux/macOS:

~~~bash
mkdir -p vendor/build/classes
javac --release 17 -d vendor/build/classes vendor/src/dev/vendor/LegacyMath.java
jar --create --file vendor/build/legacy-math-1.0.0.jar -C vendor/build/classes .
jar --list --file vendor/build/legacy-math-1.0.0.jar
~~~

Lệnh `javac --release 17` tạo bytecode tương thích Java 17; `jar --create` nén nội dung thư mục classes. Lệnh `jar --list` cần hiển thị ít nhất:

~~~text
dev/vendor/LegacyMath.class
~~~

Nó có thể in thêm `META-INF/` và manifest, nên đoạn trên **không phải toàn bộ stdout cố định**.

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\vendor\build\classes | Out-Null
javac --release 17 -d .\vendor\build\classes .\vendor\src\dev\vendor\LegacyMath.java
jar --create --file .\vendor\build\legacy-math-1.0.0.jar -C .\vendor\build\classes .
jar --list --file .\vendor\build\legacy-math-1.0.0.jar
~~~

Cần chạy **JDK 17+** vì `--release 17` không được JDK cũ hỗ trợ. Trên cả hai OS, nếu Java source không có lỗi, thư mục `vendor/build` chứa `legacy-math-1.0.0.jar`.

### 6.3. Cài JAR vào local repository

Đứng ở thư mục `local-jar-lab`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor/build/legacy-math-1.0.0.jar -DgroupId=dev.vendor -DartifactId=legacy-math -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true
~~~

Lệnh này có thể chạy **không có POM ở thư mục hiện tại** vì goal `install-file` xử lý file nhị phân độc lập với project build. Thành công sẽ tạo artifact tại local repository, thường:

~~~text
~/.m2/repository/dev/vendor/legacy-math/1.0.0/
    legacy-math-1.0.0.jar
    legacy-math-1.0.0.pom
~~~

Nếu có cấu hình local repository riêng trong `settings.xml` hoặc `-Dmaven.repo.local`, hãy kiểm tra đường dẫn thực tế thay vì mặc định luôn là `~/.m2/repository`.

### 6.4. POM của consumer — dependency bình thường

Tạo `consumer/pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.consumer</groupId>
    <artifactId>local-jar-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.vendor</groupId>
            <artifactId>legacy-math</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`<scope>` không có nên Maven dùng mặc định **`compile`**. Không có `<systemPath>`; Maven resolver chọn artifact dựa trên GAV từ local repository hoặc các remote repository được cấu hình. `exec-maven-plugin` dùng để chạy main class với dependency classpath, tránh tự ghép classpath khác nhau giữa Windows/Linux.

### 6.5. Main.java và stdout

Tạo `consumer/src/main/java/dev/consumer/Main.java`:

~~~java
package dev.consumer;

import dev.vendor.LegacyMath;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        int result = LegacyMath.add(7, 5);
        System.out.println("Local repository dependency OK: " + result);
    }
}
~~~

Tại thư mục **`local-jar-lab/consumer`**:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=dev.consumer.Main
~~~

Goal `clean package` biên dịch và đóng gói project sau khi Maven resolver tìm được `dev.vendor:legacy-math:1.0.0`. Goal `exec:java` chạy class đã biên dịch và dùng dependency classpath của project. Dòng **ứng dụng in ra stdout** là:

~~~text
Local repository dependency OK: 12
~~~

Log Maven có thêm thông tin plugin, build, thời gian và dependency; **đừng hiểu đó là toàn bộ stdout**.

Nếu `mvn clean package` báo `Could not find artifact dev.vendor:legacy-math:jar:1.0.0`, kiểm tra bước `install-file` đã thành công trên **cùng local repository** và GAV trong POM khớp tuyệt đối hay chưa.

### 6.6. Tự chứng minh systemPath không còn cần thiết

Ở `consumer/pom.xml`, **không có**:

~~~xml
<scope>system</scope>
<systemPath>...</systemPath>
~~~

Vẫn biên dịch/chạy được. Đó là bằng chứng cho một máy: thư viện đã được Maven quản lý qua GAV. Muốn kiểm tra graph mà Maven thực sự đọc:

~~~bash
mvn -B -ntp dependency:tree
~~~

Trong cây dependency, tìm tọa độ tương đương:

~~~text
dev.vendor:legacy-math:jar:1.0.0:compile
~~~

Đoạn trên là **mẫu nhận diện**, cách biểu diễn trong log có thể khác theo Maven Dependency Plugin và version. Vì thư viện mẫu chỉ chứa một class Java thuần, nó không có dependency transitively để đi kèm.

### 6.7. Bài kiểm tra quan trọng: chạy trên runner sạch

`install-file` chỉ làm bài thử thành công **trên máy đã cài JAR**. Nếu consumer được build trong container/CI có local repository sạch và không có remote repository chứa `dev.vendor:legacy-math:1.0.0`, resolver sẽ không tìm được JAR; đây là hành vi đúng.

`mvn -o` (offline) chỉ dùng artifact đã cache. Một build offline thành công trên laptop đã cài JAR **không chứng minh** đồng đội hay CI có thể tự tải artifact đó. Chứng cứ tái lập là build thành công từ **một máy/runner sạch** chỉ với cấu hình repository được quản lý và credentials hợp lệ, **không cần cài tay file JAR**.

## 7. Cách 2: phát hành JAR lên remote repository do tổ chức quản lý

Đối với thư viện dùng chung giữa developer, CI và các module, lựa chọn khuyến nghị là một **hosted Maven repository** có quản lý phân quyền và phiên bản. Các giải pháp thường gặp gồm Nexus Repository, Artifactory hoặc dịch vụ artifact repository tương thích Maven của cloud provider. Các sản phẩm đó là **ví dụ về hạ tầng**, không phải bắt buộc.

Quy trình:

~~~text
Nhà cung cấp / đối tác
    |
    v
file JAR đã xác minh nguồn gốc, checksum, license
    |
    v
Gắn GAV và POM metadata chính xác
    |
    v
maven-deploy-plugin:deploy-file
    |
    v
Hosted private Maven repository
    |                         |
    v                         v
Developer Maven            CI Maven
(resolver downloads)       (resolver downloads)
    |                         |
    v                         v
same GAV + same bytes + controlled version
~~~

**Không nên upload thư viện proprietary lên Maven Central hoặc một kho public** nếu bạn không có quyền phát hành. Chọn repository **private**, có policy read/write và kiểm soát access.

### 7.1. deploy-file cho artifact do bên thứ ba cung cấp

Khi repository nội bộ đã được quản trị viên tạo, dùng Maven Deploy Plugin. Ví dụ đầy đủ **dạng mẫu**, với domain `repo.example.invalid` cố ý **không hoạt động** và phải được thay bằng URL thật có quyền publish:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file -Dfile=vendor/build/legacy-math-1.0.0.jar -DgroupId=dev.vendor -DartifactId=legacy-math -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true -DrepositoryId=internal-thirdparty -Durl=https://repo.example.invalid/repository/third-party-releases/
~~~

Tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `-Dfile` | Tệp JAR đã xác minh |
| `-DgroupId`, `-DartifactId`, `-Dversion` | Tọa độ artifact mà consumer dùng |
| `-Dpackaging=jar` | Đóng gói loại JAR |
| `-DgeneratePom=true` | Sinh POM tối thiểu nếu không có POM phù hợp |
| `-DrepositoryId` | ID dùng ghép credentials trong `settings.xml` |
| `-Durl` | URL **hosted** repository nhận upload (không phải trang giao diện hoặc URL proxy thông thường) |

Đây là **lệnh publish có tác động lên repository từ xa**: trong môi trường thật chỉ chạy khi được phép phát hành và đã kiểm tra license, nội dung, version và quyền. Không chạy với URL tùy ý, không đưa mật khẩu lên command line, không publish binary chưa xác minh nguồn.

Nếu đã có POM đúng do vendor cung cấp, dùng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file -Dfile=vendor/build/legacy-math-1.0.0.jar -DpomFile=vendor/legacy-math-1.0.0.pom -DrepositoryId=internal-thirdparty -Durl=https://repo.example.invalid/repository/third-party-releases/
~~~

Khi dùng `-DpomFile`, plugin có thể lấy GAV/packaging từ POM đó. Hãy kiểm tra POM và JAR **thuộc cùng phiên bản**, không tự tin mọi thông tin từ vendor đều chuẩn.

### 7.2. Credentials trong settings.xml

Một mẫu cấu hình `~/.m2/settings.xml`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>internal-thirdparty</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Đây là **mẫu phần tử settings**, chưa bao gồm các cấu hình khác có thể tồn tại trên máy; không thay toàn bộ settings của công ty bằng ví dụ nếu đã có mirrors/proxies/profiles. `id` trong `<server>` cần khớp **chính xác** với `-DrepositoryId=internal-thirdparty`.

`MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` cần được CI/credential manager cấp an toàn; không commit `settings.xml` có secret thật vào Git. Maven hỗ trợ mã hóa/chuyển credentials theo cơ chế và phiên bản tương ứng, nhưng CI secret store/token ngắn hạn và nguyên tắc quyền tối thiểu vẫn quan trọng.

### 7.3. Consumer cấu hình nơi tải artifact

Nếu tổ chức đã dùng Maven mirror hoặc repository manager qua settings, consumer có thể **không cần thêm `<repositories>` vào POM**. Việc định tuyến repository thường nên được quản lý tập trung để tránh mỗi module có danh sách URL riêng.

Nếu cần minh họa một repository cụ thể trong POM:

~~~xml
<repositories>
    <repository>
        <id>internal-thirdparty</id>
        <url>https://repo.example.invalid/repository/third-party-releases/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

Đây là đoạn dưới `<project>`, **không phải POM đầy đủ**. URL chỉ là placeholder cố ý không truy cập được; thay bằng repository **read URL** do đội hạ tầng cung cấp (có thể khác URL publish). Cấu hình này nói cho Maven biết nơi **đọc dependency**, còn cấu hình `-Durl` của `deploy-file` nói nơi **ghi artifact**.

Ở nhiều tổ chức, repository manager tạo group/virtual repository để gộp proxy Maven Central và hosted nội bộ; người dùng chỉ cần một URL đọc thống nhất. Đừng trỏ mọi developer vào endpoint publish nếu policy của tổ chức tách quyền read/write.

### 7.4. settings.xml cho thông tin đọc

Nếu repository đọc yêu cầu xác thực, `<server><id>` trong settings phải khớp `<repository><id>` tương ứng. Với cấu hình mirror, ID được Maven dùng cho credentials có thể là ID của **mirror**, không phải repository gốc. Khi gặp 401/403, kiểm tra ID và quyền thay vì đặt user/password trực tiếp trong `pom.xml`.

### 7.5. Vì sao không dùng distributionManagement để tải dependency?

`<distributionManagement>` trong POM **dùng để chỉ đích xuất bản artifact của chính project** khi gọi `mvn deploy`. Nó **không phải** danh sách repository để Maven tải dependencies.

Để tải artifact, Maven dùng `<repositories>`, active settings profiles, mirrors và cơ chế resolver. Để deploy artifact bên thứ ba đã có dưới dạng file, `deploy:deploy-file` nhận `repositoryId/url`. Hai luồng là hai việc khác nhau.

## 8. POM metadata và bài toán dependencies transitively

### 8.1. generatePom chỉ tạo POM tối thiểu

Khi `install:install-file` hoặc `deploy:deploy-file` được gọi với `-DgeneratePom=true`, plugin có thể tạo một POM tối thiểu với GAV/packaging. Điều này đủ để Maven biết tọa độ artifact nhưng **không tự suy ra dependencies transitively từ file .class**.

Giả sử JAR thật cần một thư viện parser X tại runtime. Nếu chỉ publish JAR với POM tối thiểu, người dùng có thể compile thành công nhưng lỗi:

~~~text
java.lang.NoClassDefFoundError: example/parser/Parser
~~~

Đây là lỗi classpath runtime, không nhất thiết là lỗi resolver của JAR chính.

**Cách xử lý đúng:** tìm POM/metadata chính thức từ vendor, đọc tài liệu phần dependency của vendor và publish POM mô tả dependencies đúng, hoặc khai báo dependency cần thiết trực tiếp tại consumer khi chưa thể xây POM chuẩn. Không “đoán” tên artifact từ class name rồi publish metadata sai.

### 8.2. Ví dụ một POM metadata tự quản lý

Nếu bên cung cấp **không có POM**, đội dự án có thể tạo metadata POM theo tài liệu vendor và quy trình kiểm chứng. Ví dụ minh họa với JAR **độc lập** từ phần thực hành:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.vendor</groupId>
    <artifactId>legacy-math</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Legacy Math demo artifact</name>
    <description>Independent Java 17 training artifact</description>
</project>
~~~

Lưu file làm `vendor/legacy-math-1.0.0.pom`. Nó **không có `<dependencies>`** vì class `LegacyMath` trong bài tập không sử dụng thư viện khác.

Đối với **binary thật**, metadata có thể cần `dependencies`, `licenses`, `developers`, `scm` hoặc các thông tin provenance phù hợp. Không bịa license hợp lệ hoặc khai tên nhà sản xuất không có xác nhận. Nếu license chưa rõ và repository policy yêu cầu, **không publish** cho tới khi được xác minh.

### 8.3. Một artifact và một nhãn version có ý nghĩa

Nếu JAR đã publish với GAV `dev.vendor:legacy-math:1.0.0` và sau đó vendor gửi file đã thay đổi, đừng thay file của cùng release `1.0.0` một cách bí mật. Nên tạo version mới theo chính sách, ví dụ `1.0.1` hoặc version nội bộ đã được kiểm duyệt. Việc “release immutable” thường là chính sách repository, không phải bảo đảm tự động cho mọi kho.

Với artifact SNAPSHOT, semantics và metadata có thể khác release; không sử dụng `-SNAPSHOT` để tùy tiện phân phối binary production mà không có chính sách rõ ràng.

## 9. Cách chuyển từ systemPath sang kho mà không làm vỡ dự án

### Bước 1: kiểm kê JAR và nơi sử dụng

Tìm trong POM được kiểm soát nguồn:

~~~text
<scope>system</scope>
<systemPath>...</systemPath>
~~~

Ghi lại file nào đang được dùng, version thật, publisher, SHA-256, license, module nào sử dụng và các dependencies liên quan. Kiểm tra tên JAR so với nội dung thực bằng `jar --list --file` hoặc công cụ phân tích phù hợp.

### Bước 2: xác minh nguồn và quyền dùng

Yêu cầu vendor cung cấp thông tin version, checksum/chữ ký, license và POM/dependency list nếu có. Không upload JAR nhặt từ máy cá nhân khi chưa xác minh. Với binary proprietary, repository phải giữ private và có quyền hạn phù hợp.

### Bước 3: xác định GAV

Chọn namespace nội bộ kiểm soát được; dùng một version cho một nội dung binary đã xác minh. Tránh trùng GAV với artifact public và tránh giả mạo tọa độ vendor chính thức nếu không có cơ sở.

### Bước 4: thử local install trước

Chạy `install:install-file` trên môi trường phát triển và đổi POM consumer từ `systemPath` sang dependency thường. Chạy `mvn clean verify`; nếu ứng dụng cần chạy thật, kiểm tra runtime qua goal `exec:java` hoặc integration test tương ứng.

### Bước 5: deploy lên hosted repository

Khi được phép, phát hành JAR và POM đúng bằng `deploy:deploy-file`. Tạo quyền read/write tách biệt và giữ log publish, checksum, người phê duyệt nếu quy trình yêu cầu.

### Bước 6: xóa system scope khỏi consumer

**Trước:**

~~~xml
<dependency>
    <groupId>dev.vendor</groupId>
    <artifactId>legacy-math</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/lib/legacy-math-1.0.0.jar</systemPath>
</dependency>
~~~

**Sau:**

~~~xml
<dependency>
    <groupId>dev.vendor</groupId>
    <artifactId>legacy-math</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Không cần `<scope>compile</scope>` vì đây là mặc định, nhưng có thể khai báo rõ nếu quy tắc nhóm yêu cầu. Nếu thư viện chỉ phục vụ test thì dùng `<scope>test</scope>`; nếu container cung cấp ở runtime thì xem `provided` theo semantics thật. **Không chuyển mọi system-scoped dependency thành compile một cách máy móc.**

### Bước 7: kiểm tra build trên môi trường sạch

Chạy trên runner/container mới có thông tin repository read:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp dependency:tree
~~~

Chứng cứ mong muốn: dependency được resolver phân giải qua GAV; không cần file `lib/` đã được copy riêng trên từng máy; build/test/run thành công theo các kiểm tra dự án thiết lập. Nếu CI không có quyền read repository, cần sửa phân quyền và settings, không quay lại `systemPath`.

### Bước 8: loại bỏ các file/vết phụ thuộc thừa

Chỉ sau khi xác minh release và CI thành công, cập nhật tài liệu onboarding, bỏ bước “copy JAR vào lib” và quyết định có cần giữ JAR gốc trong kho lưu trữ nội bộ để audit hay không. Đừng xóa bản gốc khỏi nơi lưu giữ đã được phê duyệt; không tự động xóa file của các developer khác.

## 10. Các lỗi phổ biến và cách xử lý

### 10.1. Could not find artifact dev.vendor:legacy-math:jar:1.0.0

**Nguyên nhân có thể:** chưa chạy `install-file` ở máy này; cài vào local repository khác; sai GAV; artifact chưa publish/không truy cập được từ remote; URL repo/proxy/mirror sai; CI không có credentials.

**Cách xử lý:** so `pom.xml` consumer với GAV đã cài/deploy; xác nhận repository path và trạng thái publish; kiểm tra settings, mirror, thông tin 401/403/404. Tránh sửa version ngẫu nhiên hoặc cài lại JAR khác nội dung với cùng GAV.

### 10.2. 'systemPath' should not point to files within the project directory

**Nguyên nhân:** POM đang dùng `scope=system` và trỏ vào JAR nằm trong thư mục của dự án, gây POM khó tái sử dụng ở project khác.

**Cách xử lý:** chuyển sang repository theo hướng dẫn. Đổi `${project.basedir}/lib/...` thành đường dẫn absolute khác chỉ né một số cảnh báo, **không giải quyết** vấn đề không di động.

### 10.3. The specified file ... not exists

**Nguyên nhân:** `systemPath` sai hoặc file đầu vào `-Dfile` cho `install-file` không tồn tại trong current working directory.

**Cách xử lý:** kiểm tra bằng công cụ file của OS và working directory. Nếu file có khoảng trắng, quote đúng tham số/path theo shell. Đừng kết luận Maven Central lỗi khi Maven đang được chỉ dùng `systemPath`.

### 10.4. JAR có trong lib nhưng Maven không tìm thấy

**Nguyên nhân:** Maven resolver không tự quét thư mục `lib/` cho dependency chuẩn.

**Cách xử lý:** dùng `install:install-file` hoặc upload remote repository, không bổ sung thư mục vào POM bằng system scope như giải pháp lâu dài.

### 10.5. Cài được JAR nhưng IDE vẫn đỏ

**Nguyên nhân:** IDE chưa reload Maven project, đang dùng local repository hoặc settings khác, sai `version` hoặc thiếu dependency metadata.

**Cách xử lý:** Maven reload/reimport, kiểm tra Maven home/settings/local repo của IDE, chạy `mvn dependency:tree` và `mvn compile` trên terminal để phân biệt lỗi IDE với lỗi Maven.

### 10.6. NoClassDefFoundError khi chạy

**Nguyên nhân:** compiler thấy JAR chính nhưng runtime thiếu một thư viện transitively hoặc ứng dụng đóng gói thiếu dependency.

**Cách xử lý:** đối chiếu POM metadata thật, scope runtime, `dependency:tree` và nội dung package/distribution. Không sửa bằng cách nhét ngẫu nhiên nhiều JAR vào `lib/` rồi bỏ qua quản lý version.

### 10.7. JAR dùng được trên laptop nhưng CI không thấy

**Nguyên nhân:** local repository mỗi máy khác nhau; `install-file` không đồng bộ artifact sang CI.

**Cách xử lý:** publish artifact lên hosted remote repository, khai read URL/credentials đúng. Kiểm tra trên runner sạch để xác nhận build thực sự tái lập.

### 10.8. Deploy-file nhận HTTP 401/403

**Nguyên nhân:** server ID không khớp, token hết hạn/không có quyền publish, endpoint repo chỉ cho read, hoặc credentials không được nạp.

**Cách xử lý:** kiểm tra `-DrepositoryId`, `<servers><server><id>`, quyền và URL write; dùng secret store và principle of least privilege. Không dán token vào ticket hoặc repository.

### 10.9. Deploy-file nhận HTTP 400/409

**Nguyên nhân có thể:** policy kho không nhận overwrite release cùng version, đăng artifact nhầm snapshot vào releases, metadata thiếu hoặc artifact path không hợp lệ.

**Cách xử lý:** kiểm tra chính sách repository và tọa độ/version. Nếu bản binary mới, dùng version mới; không cố bypass release immutability.

### 10.10. Máy CI tải dependency từ kho không đúng

**Nguyên nhân:** `settings.xml` có `<mirrors>`, active profiles hoặc repository order khác, hoặc URL trong POM không đúng repository nhóm sử dụng.

**Cách xử lý:** đối chiếu `mvn help:effective-settings` và log resolver. Đừng đặt credentials trong `pom.xml`. Khi bật debug `-X`, phải lọc thông tin nhạy cảm trước khi chia sẻ log.

### 10.11. Offline build chỉ chạy được trên một máy

**Nguyên nhân:** `mvn -o` chỉ dùng artifacts cache. Máy đã `install-file` có JAR, máy khác không.

**Cách xử lý:** bật online trên môi trường có quyền remote repo hoặc seed cache theo quy trình được phê duyệt; offline mode không thay thế phân phối artifact.

### 10.12. System scope không có dependency transitive

**Nguyên nhân:** `system` bỏ qua cơ chế lấy artifact/POM metadata từ repository. JAR mà bạn dẫn vào không tự mô tả đủ dependencies cho consumer.

**Cách xử lý:** publish JAR cùng POM có dependency metadata chính xác; nếu chưa có, khai những dependencies thật sự cần trực tiếp và test runtime. Tránh phát hành POM “tự đoán” gây dependency graph sai.

## 11. Quản lý repository và chuỗi cung ứng phần mềm

Khi nhóm bắt đầu quản lý những JAR bên ngoài Maven Central, nên đặt các quy tắc rõ ràng:

1. **Nguồn gốc:** lưu URL/bên phát hành, thông tin bản phát hành, SHA-256 và người phê duyệt khi thích hợp.
2. **License:** xác minh quyền sử dụng, quyền phân phối nội bộ, các ràng buộc license; proprietary JAR thường không được phát hành public.
3. **Phiên bản:** mỗi release GAV có bytes cố định theo chính sách; bản sửa lỗi dùng version mới.
4. **Metadata:** ưu tiên vendor POM; nếu tự tạo, mô tả GAV/dependencies chính xác, không dựng giả.
5. **Quyền:** tài khoản publish tách tài khoản read, token có thời hạn và quyền tối thiểu.
6. **An ninh:** vulnerability/SBOM scanning nếu quy trình yêu cầu; ghi nhận trường hợp binary không có mã nguồn hoặc ký nhận từ vendor.
7. **Repository:** phân biệt hosted, proxy, group/virtual; publish vào hosted đúng loại, resolve qua read URL do nhóm định nghĩa.
8. **Tái lập:** build trên runner sạch, không phụ thuộc artifacts do một người đã cài local trước đó.
9. **Audit:** giữ log publish và hồ sơ thay đổi; không xóa hoặc ghi đè artifact đã được build/deploy rộng rãi.
10. **Thu hồi:** nếu phát hiện JAR lỗi nghiêm trọng, quy trình có khả năng ngừng cấp quyền, chặn phiên bản và chuyển sang version thay thế.

**Lưu ý về file-based repository:** Maven có thể hỗ trợ URL `file://` trong một số tình huống, nhưng dùng thư mục chung qua network share hoặc commit một cấu trúc repository vào source tree thường tạo vấn đề quyền ghi, nhất quán và bảo trì. Với team/CI thực tế, ưu tiên repository manager có metadata và kiểm soát quyền.

## 12. Khi nào systemPath vẫn có thể xuất hiện?

Một số codebase cũ hoặc SDK nhị phân có điều kiện phân phối đặc biệt vẫn dùng system scope. Nếu **bắt buộc** phải giữ trong ngắn hạn, hãy quản lý rủi ro:

- Ghi rõ lý do pháp lý/kỹ thuật và thời hạn loại bỏ.
- Bảo đảm đường dẫn tồn tại trên mọi môi trường build được hỗ trợ; dùng `${project.basedir}` nếu tạm nằm trong project, đồng thời chấp nhận cảnh báo Maven.
- Xác minh JAR có đúng checksum và version trên mỗi môi trường.
- Kiểm tra runtime và packaging, vì compile thành công chưa đủ.
- Không phát hành POM của một module có system path rồi giả định downstream tự giải quyết được nó.
- Lập kế hoạch chuyển sang kho internal ngay khi quyền và hạ tầng cho phép.

**Không nên:** dùng `systemPath` để né lỗi resolver vì nhập sai GAV; để file JAR trong Git không có hồ sơ license; tự xóa local Maven cache như cách sửa đầu tiên; hay đưa mật khẩu repository vào POM.

## 13. Bài tập thực hành

**Bài 1 — xác định sai lầm:**

~~~xml
<dependency>
    <groupId>dev.vendor</groupId>
    <artifactId>legacy-math</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>${project.basedir}/lib/legacy-math-1.0.0.jar</systemPath>
</dependency>
~~~

Vì sao build có thể thành công trên máy A nhưng fail trên CI? **Đáp án:** JAR tại đường dẫn project có thể không tồn tại trong CI; Maven không tải system dependency từ repository. Scope này cũng không cung cấp cơ chế phân phối artifact có metadata chuẩn.

**Bài 2 — đổi sang dependency bình thường:** Viết lại POM chỉ còn `groupId`, `artifactId`, `version`. Cần thao tác gì trước đó? **Đáp án:** install JAR vào local repo của môi trường cần chạy hoặc publish lên remote repo mà Maven có thể đọc; sau đó kiểm tra GAV và classpath.

**Bài 3 — GAV và layout:** Với `com.example.vendor:invoice-sdk:2.4.0`, chỉ ra đường dẫn dự kiến dưới `~/.m2/repository`. **Đáp án:** `com/example/vendor/invoice-sdk/2.4.0/invoice-sdk-2.4.0.jar` và POM cùng tọa độ nếu được cài/publish đúng.

**Bài 4 — chứng minh tính cục bộ:** Chạy bài thực hành mục 6 trên máy có JAR đã được install, rồi xét máy chưa có JAR và không được truy cập remote. Kết quả khác nhau vì đâu? **Đáp án:** local repository không được chia sẻ tự động; machine/CI sạch cần remote repository hoặc bước cài được kiểm soát.

**Bài 5 — phân biệt install và deploy:** Lệnh nào dùng cho laptop, lệnh nào dùng để cả nhóm có thể download? **Đáp án:** `install:install-file` ghi local repo, `deploy:deploy-file` publish lên remote hosted repository.

**Bài 6 — metadata:** JAR A chạy cần JAR B, nhưng được publish bằng `generatePom=true` với POM tối thiểu. Điều gì xảy ra? **Đáp án:** Maven không tự suy ra dependency B; cần metadata thật/đúng hoặc dependency trực tiếp ở consumer.

**Bài 7 — bảo mật:** Đối tác gửi một JAR không có license document và không có checksum được đối chiếu. Có nên publish ngay lên repository công ty? **Đáp án:** không; xác minh nguồn gốc, license và tính toàn vẹn theo policy trước khi phân phối.

**Bài 8 — lỗi deploy:** `deploy-file` trả 403 dù bạn có thể tải các artifacts từ cùng URL. Vì sao? **Đáp án:** tài khoản có thể chỉ có quyền read; endpoint có thể không phải hosted write repository hoặc `repositoryId` không ghép đúng credentials trong settings.

## 14. Checklist trước khi kết thúc chuyển đổi

- [ ] Đã xác định đúng file JAR, version, nhà phát hành và quyền sử dụng.
- [ ] Đã lưu checksum/provenance và so với nguồn tin cậy.
- [ ] Đã chọn GAV do tổ chức kiểm soát, không collision với artifact public.
- [ ] Đã dùng `install:install-file` để thử trên máy phát triển.
- [ ] Đã thay `scope=system` và `systemPath` bằng dependency GAV chuẩn trong POM consumer.
- [ ] Đã xác nhận compile, test và runtime/classpath trên Java 17+ phù hợp.
- [ ] Đã xác nhận POM metadata và các dependencies transitively quan trọng.
- [ ] Nếu dùng chung trong team, đã publish lên remote hosted Maven repository có quyền hạn phù hợp.
- [ ] Consumer/CI được cấu hình URL read, mirror và credentials an toàn.
- [ ] Đã chạy thử với local repository sạch hoặc CI runner sạch, không cài JAR bằng tay.
- [ ] Đã kiểm tra artifact bytes/version thống nhất, không ghi đè release một cách im lặng.
- [ ] Đã cập nhật tài liệu dự án, loại bỏ bước copy JAR bằng tay nếu không còn cần.
- [ ] Đã lưu báo cáo/quy trình thu hồi nếu phát hiện lỗ hổng hoặc license issue.

## 15. Tài liệu chính thức

1. [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): các dependency scope, đặc biệt `system` và cảnh báo không khuyến nghị.
2. [Apache Maven — Guide to installing third-party JARs](https://maven.apache.org/guides/mini/guide-3rd-party-jars-local.html): cách đưa JAR vào Maven local repository.
3. [Maven Install Plugin — install-file](https://maven.apache.org/plugins/maven-install-plugin/install-file-mojo.html): cú pháp và các tham số `file`, `groupId`, `artifactId`, `version`, `packaging`, `pomFile`.
4. [Apache Maven — Guide to deploying third-party JARs](https://maven.apache.org/guides/mini/guide-3rd-party-jars-remote.html): triển khai artifact bên thứ ba lên remote repository.
5. [Maven Deploy Plugin — deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html): cấu hình `repositoryId`, `url`, `file` và `pomFile`.
6. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): `servers`, `mirrors`, repositories, proxies, credentials và local repository.
7. [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): phân biệt local/remote repositories và cách Maven phân giải artifact.
8. [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `dependencies`, `dependencyManagement`, `repositories` và `distributionManagement`.
