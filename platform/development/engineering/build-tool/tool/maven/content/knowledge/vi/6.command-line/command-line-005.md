# Chọn settings riêng bằng `-s` và thư mục kho cục bộ riêng trong Maven

## 1. Vì sao cần hai loại cấu hình?

Một dự án Maven thường có cùng `pom.xml` nhưng được build trên nhiều máy: máy lập trình viên, máy CI, môi trường có proxy công ty hoặc máy thử nghiệm. Các máy có thể cần **máy chủ tải thư viện**, **thông tin xác thực** và **nơi lưu thư viện đã tải** khác nhau. Maven tách những lựa chọn này khỏi cấu hình dự án.

Có ba thành phần cần phân biệt:

- **`pom.xml`** định nghĩa dự án: tọa độ, dependencies, plugins, cách biên dịch và kiểm thử. Nhóm thường commit tệp này vào Git.
- **`settings.xml`** định nghĩa cấu hình của môi trường chạy Maven: kho cục bộ, mirror, proxy, máy chủ và thông tin xác thực. Có thể chọn một tệp settings riêng bằng tham số dòng lệnh `-s`.
- **Local repository** là kho lưu trữ trên **máy đang chạy Maven**, thường chứa JAR/POM của dependencies, plugins và artifact đã `mvn install`. Nó khác với thư mục `target/` của một dự án và khác remote repository trên mạng.

Hai câu hỏi độc lập thường xuất hiện:

1. **Maven đọc settings nào?** Dùng `mvn -s <đường-dẫn-settings> ...` hoặc `mvn --settings <đường-dẫn-settings> ...`.
2. **Maven lưu và tìm artifact cục bộ ở đâu?** Khai báo `<localRepository>` trong settings hoặc truyền thuộc tính `-Dmaven.repo.local=<đường-dẫn-kho>` khi chạy Maven.

Ví dụ, một lập trình viên có thể dùng settings của công ty để truy cập Nexus/Artifactory, nhưng vẫn muốn kho local riêng cho thử nghiệm nhằm tránh dùng chung cache với các dự án khác. Một tác vụ CI có thể dùng cùng settings về mirror nhưng đặt kho local trong một thư mục cache dành riêng cho job.

```text
                    pom.xml (cau hinh du an)
                            |
            mvn -s settings-lab.xml
                            |
            settings-lab.xml (moi truong)
                            |
       -Dmaven.repo.local=/.../repo-ci (neu co)
                            |
          local repository duoc Maven chon
               /                   \
      thu vien/plugin       artifact sau install
               \                   /
                 Maven build va test
                           |
                 target/ cua du an
```

Trong sơ đồ, `target/` là đầu ra của quá trình build. Kho local chứa các artifact phục vụ **phân giải phụ thuộc và plugin**, không phải nơi Maven thường ghi `target/classes` hay JAR mới sinh bởi phase `package`.

## 2. Settings mặc định, settings riêng và thứ tự áp dụng

Với cách chạy Maven thông dụng, có hai tệp settings chính:

| Loại | Đường dẫn thường gặp | Ý nghĩa |
| --- | --- | --- |
| Global settings | `${maven.home}/conf/settings.xml` | Cấu hình ở mức bản cài Maven |
| User settings | `${user.home}/.m2/settings.xml` | Cấu hình riêng cho tài khoản đang chạy Maven |
| User settings do bạn chọn | Ví dụ `${user.home}/.m2/settings-lab.xml` | Được Maven dùng khi truyền `-s` |
| Kho local mặc định | `${user.home}/.m2/repository` | Dùng khi không cấu hình nơi khác |

Nếu cả global và user settings tồn tại, Maven hợp nhất chúng thành **effective settings**, trong đó cấu hình phía user được ưu tiên ở các phần tương ứng. `-s` thay đường dẫn **user settings** mà Maven đọc trong lần chạy đó; nó không tự bỏ global settings. Cần thay riêng global settings thì có tùy chọn `-gs` (hay `--global-settings`).

Các tùy chọn dễ nhầm:

| Tùy chọn | Thay đổi cái gì? | Không có tác dụng gì? |
| --- | --- | --- |
| `-s PATH` / `--settings PATH` | Chọn user `settings.xml` khác | Không tự chọn một POM khác |
| `-gs PATH` / `--global-settings PATH` | Chọn global settings khác | Không thay thế cờ `-s` |
| `-f PATH` / `--file PATH` | Chọn `pom.xml` hoặc dự án Maven cần chạy | Không chọn settings |
| `-Dmaven.repo.local=PATH` | Chọn kho artifact cục bộ cho lần chạy | Không đổi địa chỉ remote repository |
| `-o` / `--offline` | Không truy cập mạng khi phân giải artifact | Không tự tải dependencies còn thiếu |
| `-U` | Buộc Maven kiểm tra lại cập nhật một số artifact/SNAPSHOT theo chính sách | Không xóa toàn bộ kho local |

**Lưu ý phiên bản:** phần giải thích và các lệnh thực hành dưới đây áp dụng cho Maven 3.9.x theo cách dùng phổ biến; kiểm tra `mvn -version` để biết Maven/JDK thật đang dùng. Maven 4 có thêm một số khả năng cấu hình theo dự án, vì vậy nếu dùng Maven 4 hãy đối chiếu tài liệu đúng phiên bản.

## 3. Tạo một tệp settings riêng

Giả sử tài khoản hiện tại vẫn cần giữ `~/.m2/settings.xml` cho công việc thường ngày. Ta tạo thêm một tệp tên `settings-lab.xml` trong `~/.m2/`. Phần `~` ở đây chỉ mang nghĩa thư mục home của người dùng; trong các lệnh shell phía sau, chúng ta dùng biến `$HOME` hoặc `$env:USERPROFILE` để có đường dẫn rõ ràng.

Nội dung **đầy đủ và hợp lệ** của `settings-lab.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>${user.home}/.m2/repository-lab</localRepository>
</settings>
```

Đường dẫn `${user.home}` là **thuộc tính hệ thống Maven/Java sẽ nội suy khi đọc settings**, không phải đoạn cần thay thủ công bằng tên tài khoản. Vì vậy cùng một nội dung XML có thể dùng trên Linux, macOS và Windows. Maven yêu cầu local repository có **đường dẫn tuyệt đối sau khi nội suy**. Nếu viết một đường dẫn tương đối hoặc dùng ký hiệu `~` như một phần của XML, không nên giả định Maven sẽ hiểu nó giống shell.

Giá trị `<localRepository>` ở ví dụ hướng Maven tới kho `repository-lab` nằm cạnh kho `repository` mặc định. Khi chạy:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" test
```

Maven đọc tệp user settings mới, lấy đường dẫn kho local từ `<localRepository>` và chạy goal/phase `test` của dự án hiện tại. Nếu không truyền `-s`, Maven lại dùng user settings mặc định (nếu có).

**Điều kiện của ví dụ trên:** tệp `$HOME/.m2/settings-lab.xml` phải được tạo đúng nội dung trước khi chạy; Maven không tự tạo tệp settings thay thế khi `-s` trỏ tới đường dẫn không tồn tại.

## 4. Chọn kho local trực tiếp trên dòng lệnh

Khi chỉ muốn thử một lần chạy khác mà chưa cần sửa XML, dùng:

```bash
mvn "-Dmaven.repo.local=$HOME/.m2/repository-experiment" clean test
```

Dấu ngoặc kép bao quanh **toàn bộ một đối số** `-D...` giúp giữ nguyên đường dẫn nếu thư mục home có khoảng trắng. Trên máy người dùng, shell mở rộng `$HOME` trước khi gọi Maven nên giá trị truyền đi thường là đường dẫn tuyệt đối.

Khi kết hợp cả hai lựa chọn:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" "-Dmaven.repo.local=$HOME/.m2/repository-experiment" clean verify
```

Trong lần chạy đó:

1. Maven dùng `settings-lab.xml` làm user settings, cùng các global settings có hiệu lực.
2. Nếu settings có mirror, proxy, server hoặc profile, những cấu hình hợp lệ đó vẫn áp dụng.
3. **`-Dmaven.repo.local` chọn kho local `repository-experiment`**, ghi đè lựa chọn `<localRepository>` cho lần chạy này.
4. Các thư viện/plugin Maven cần sẽ được phân giải từ kho local đã chọn và tải về nếu còn thiếu.
5. Đầu ra build của dự án vẫn nằm trong `target/` theo POM, không chuyển vào kho local mới.

Cờ `-D` ở đây tạo thuộc tính Maven có tên chính xác **`maven.repo.local`**. Đừng dùng `-DlocalRepository` hoặc `-Drepo.local` rồi kỳ vọng Maven tự hiểu đó là thuộc tính đặc biệt.

Bảng quyết định nhanh:

| Cách gọi | User settings được dùng | Kho local được chọn |
| --- | --- | --- |
| `mvn test` | Settings mặc định của user, nếu có | `<localRepository>` trong settings có hiệu lực hoặc đường dẫn mặc định |
| `mvn -s settings-lab.xml test` | `settings-lab.xml` | `<localRepository>` trong file đó, nếu được cấu hình |
| `mvn -Dmaven.repo.local=/abs/repo-b test` | Settings mặc định của user | `/abs/repo-b` |
| `mvn -s settings-lab.xml -Dmaven.repo.local=/abs/repo-c test` | `settings-lab.xml` | `/abs/repo-c` |

Trong bảng, các đường dẫn `/abs/repo-b` và `/abs/repo-c` chỉ minh họa cấu trúc một đường dẫn tuyệt đối trên Unix. Để chạy thật, dùng đường dẫn tồn tại và có thể ghi trên máy, như các lệnh đầy đủ ở trên hoặc ví dụ PowerShell tiếp theo.

## 5. Lệnh tương đương trên Windows PowerShell

PowerShell dùng `$env:USERPROFILE` để tham chiếu thư mục người dùng Windows. Tạo settings tại thư mục `.m2` trong hồ sơ người dùng rồi dùng các lệnh:

```powershell
$settings = Join-Path $env:USERPROFILE ".m2/settings-lab.xml"
$repo = Join-Path $env:USERPROFILE ".m2/repository-experiment"

mvn -s "$settings" "-Dmaven.repo.local=$repo" clean verify
```

Đây là lệnh PowerShell; không dùng nguyên cú pháp `$env:USERPROFILE` trong Bash hoặc zsh. Những đường dẫn do `Join-Path` trả về là đường dẫn Windows đầy đủ. Truyền `"-Dmaven.repo.local=$repo"` thành **một argument** để tránh lỗi tách từ khi thư mục chứa khoảng trắng.

Nếu không cần đổi kho local mà chỉ muốn dùng đường dẫn từ `<localRepository>` của settings:

```powershell
mvn -s "$settings" test
```

Nếu chạy trong Command Prompt (`cmd.exe`) thay vì PowerShell, cách lấy biến môi trường sẽ khác: dùng `%USERPROFILE%` hoặc khai báo biến đúng cú pháp CMD. Đường dẫn kho local không bắt buộc nằm trong `.m2`; ví dụ `D:/maven-cache/course` cũng hợp lệ nếu ổ đĩa có thể ghi.

## 6. Thực hành đầy đủ: một dự án Java 17 dùng kho riêng

Ta dùng một dự án nhỏ để thấy **Maven build vào `target/` nhưng lưu các dependency/plugin tải về trong local repository được chọn**.

Cấu trúc:

```text
maven-settings-lab/
├── pom.xml
└── src/
    ├── main/java/dev/learn/App.java
    └── test/java/dev/learn/AppTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learn</groupId>
    <artifactId>maven-settings-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/dev/learn/App.java`:

```java
package dev.learn;

public final class App {
    private App() {
    }

    public static int doubleOf(int value) {
        return Math.multiplyExact(value, 2);
    }

    public static void main(String[] args) {
        System.out.println(doubleOf(7));
    }
}
```

Tạo `src/test/java/dev/learn/AppTest.java`:

```java
package dev.learn;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AppTest {
    @Test
    void doublesANumber() {
        assertEquals(14, App.doubleOf(7));
    }

    @Test
    void refusesIntegerOverflow() {
        assertThrows(ArithmeticException.class,
                () -> App.doubleOf(Integer.MAX_VALUE));
    }
}
```

Điều kiện: terminal đang ở thư mục `maven-settings-lab`, có JDK 17+ và Maven; tệp `settings-lab.xml` ở mục 3 đã được tạo. Trên Linux/macOS chạy:

```bash
mvn -version
mvn -s "$HOME/.m2/settings-lab.xml" "-Dmaven.repo.local=$HOME/.m2/repository-experiment" clean verify
java -cp target/classes dev.learn.App
```

Lệnh Java in chính xác:

```text
14
```

Maven chạy hai unit test; khi đạt, mục tiêu `verify` hoàn tất, và Maven tạo các đường dẫn điển hình:

```text
maven-settings-lab/target/classes/dev/learn/App.class
maven-settings-lab/target/test-classes/dev/learn/AppTest.class
maven-settings-lab/target/surefire-reports/
maven-settings-lab/target/maven-settings-lab-1.0.0-SNAPSHOT.jar
```

Đồng thời, do dự án có JUnit và Maven plugins, kho local được chọn có thể chứa đường dẫn như:

```text
~/.m2/repository-experiment/org/junit/jupiter/junit-jupiter/5.11.4/
~/.m2/repository-experiment/org/apache/maven/plugins/maven-compiler-plugin/3.14.1/
```

Các đường dẫn bên trong `repository-experiment` biểu thị **artifact đã tải vào cache**, không phải các tệp `.class` do chương trình của bạn biên dịch. Lần đầu dùng một kho mới có thể chậm hơn vì Maven cần tải lại dependencies và plugin từ nguồn từ xa. Bạn không cần sao chép nội dung của `~/.m2/repository` mặc định sang kho mới chỉ để dự án build được khi có mạng và repository hợp lệ.

**Quan sát thêm:** lệnh `mvn package` tạo JAR trong `target/`, nhưng không đồng nghĩa cài JAR đó vào local repository. Chỉ khi bạn chạy `mvn install` (hoặc thao tác cài đặt tương đương) Maven mới cài artifact dự án vào local repository đã chọn, ví dụ:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" "-Dmaven.repo.local=$HOME/.m2/repository-experiment" install
```

Sau khi lệnh thành công, kiểm tra thư mục:

```text
~/.m2/repository-experiment/dev/learn/maven-settings-lab/1.0.0-SNAPSHOT/
```

Dự án Maven khác chạy **với cùng kho local** có thể phân giải artifact này theo tọa độ `dev.learn:maven-settings-lab:1.0.0-SNAPSHOT`. Dự án dùng kho local khác không tự nhìn thấy artifact đã cài, trừ khi artifact có sẵn ở remote repository hoặc được đưa tới kho đó bằng cách phù hợp.

## 7. Kiểm chứng Maven đã dùng đúng settings và kho local

Không nên chỉ suy luận từ tên tệp hay một lần build thành công. Kiểm chứng theo từng mục tiêu:

### 7.1. Xác nhận tệp settings đã được chọn

Chạy Maven Help Plugin, truyền đúng `-s`:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" help:effective-settings
```

Kết quả là **effective settings** sau khi Maven kết hợp những cấu hình có hiệu lực, gồm phần từ global settings. Kiểm tra các mục `<localRepository>`, `<mirrors>`, `<profiles>` hoặc `<proxies>` liên quan. Lệnh này có thể cần tải Help Plugin về kho local lần đầu.

Để tiết kiệm đầu ra trên terminal, có thể ghi kết quả vào một tệp **ngoài thư mục dự án và được bảo vệ quyền truy cập phù hợp**, sau đó xem và xóa khi không còn cần thiết. Không commit hoặc gửi công khai effective settings: nó có thể tiết lộ cấu hình máy chủ, tài khoản hoặc các chi tiết nội bộ.

### 7.2. Xác nhận kho local thực sự được Maven chọn

`help:effective-settings` hiển thị **cấu hình settings**, nhưng khi có cả `-Dmaven.repo.local` thì chỉ đọc `<localRepository>` trong effective settings **chưa đủ** để kết luận kho thực tế của lần chạy. Hãy dùng lệnh debug của chính lần build cần kiểm tra:

```bash
mvn -s "$HOME/.m2/settings-lab.xml" "-Dmaven.repo.local=$HOME/.m2/repository-experiment" -X -B -ntp test
```

Trong log debug, tìm thông tin Maven dùng **local repository** hoặc **local repository manager** và đường dẫn tương ứng. Nội dung/log format có thể thay đổi theo phiên bản Maven. `-X` in nhiều dữ liệu chẩn đoán; tránh chia sẻ toàn bộ log nếu có URL nội bộ, cấu hình hoặc thông tin nhạy cảm.

Cách xác nhận thực tế khác là quan sát trong thư mục kho được chọn sau khi Maven phân giải thành công JUnit/plugin:

```bash
ls "$HOME/.m2/repository-experiment/org/junit/jupiter/junit-jupiter/5.11.4/"
```

Nếu không thấy, kiểm tra log lỗi tải artifact, đường dẫn và xem test thực sự chạy thành công hay chưa. Chỉ nhìn thư mục có tồn tại **không đủ chứng minh lần chạy hiện tại đã chọn kho đó**, bởi thư mục có thể được tạo bởi lần chạy cũ; kết hợp đối chiếu lệnh và log.

### 7.3. Xem tác dụng của `clean`, `test` và `install`

- `mvn clean` chủ yếu xóa **đầu ra build** của dự án (thường là `target/`); nó không phải lệnh xóa kho local.
- `mvn test` phân giải thư viện/plugin từ kho local, tải thêm nếu còn thiếu và chạy test.
- `mvn install` ngoài việc build/verify còn cài artifact của dự án vào kho local đang được dùng.
- `mvn deploy` liên quan việc xuất bản artifact tới **remote repository** được cấu hình; đổi `maven.repo.local` không tự định nghĩa nơi deploy.

## 8. Settings riêng có thể định tuyến tới mirror và cần quản lý bí mật

`-s` đặc biệt hữu ích khi môi trường cần các cấu hình khác ngoài đường dẫn kho local:

- **`<mirrors>`**: chọn máy chủ thay thế khi tải dependencies/plugins từ repository tương ứng; ví dụ mirror một `central` repository bằng repository manager được công ty quản lý.
- **`<proxies>`**: đi qua proxy khi môi trường yêu cầu.
- **`<servers>`**: cấu hình thông tin xác thực cho repository có `id` tương ứng khi tải hoặc xuất bản.
- **`<profiles>` / `<activeProfiles>`**: kích hoạt một tập repository, plugin repository hay thuộc tính môi trường nhất định.

Một ví dụ cú pháp mirror, **chỉ để minh họa và không dùng trực tiếp nếu chưa có repository manager thật**:

```xml
<mirrors>
    <mirror>
        <id>company-proxy</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.org/repository/maven-public/</url>
    </mirror>
</mirrors>
```

Đây là **một đoạn con** để đặt bên trong thẻ `<settings>`, không phải tệp XML đầy đủ. URL dưới tên miền `example.org` là địa chỉ minh họa; khi cấu hình thật phải dùng URL repository manager đã được cấp và có thể truy cập. Không thêm mirror này vào bài thực hành ở mục 6 vì nó sẽ khiến máy không có repository tương ứng tải dependencies thất bại.

Lưu ý về mirror:

1. `mirrorOf=central` áp dụng cho repository có ID `central`; `mirrorOf=*` có phạm vi rộng hơn và cần repository manager có khả năng cung cấp mọi artifact cần thiết.
2. Mirror quyết định **nguồn tải từ xa**; `localRepository` quyết định **nơi Maven cache các artifact trên máy**. Chọn một cái không thay đổi cái còn lại theo mặc định.
3. `<servers><server><id>...` dùng ID tương ứng theo cách Maven/transport phân giải máy chủ; thông tin xác thực cần đặt trong settings của môi trường, không trong `pom.xml` được chia sẻ.
4. Nếu settings riêng có username, password hoặc token, **không commit, không log nội dung, không đăng lên issue/chat công khai**; dùng cơ chế lưu bí mật phù hợp trong CI và quy trình phát hành.

Ví dụ thật thường sử dụng settings do CI tạo từ biến bí mật. Tệp này chỉ có hiệu lực đối với job được truyền `-s`, giúp cùng một POM build trong nhiều môi trường mà không phải thay đổi dữ liệu xác thực trong source code.

## 9. Ứng dụng cho CI và nhiều môi trường

Một pipeline có thể chủ động chọn settings của build agent và kho local riêng:

```bash
mvn -B -ntp -s "$HOME/.m2/settings-lab.xml" "-Dmaven.repo.local=$HOME/.m2/repository-experiment" clean verify
```

Các thành phần lệnh:

- `-B`: chạy ở chế độ batch để hạn chế tương tác người dùng.
- `-ntp`: không in thanh tiến trình truyền dữ liệu, log CI dễ đọc hơn.
- `-s`: dùng cấu hình repository/proxy/credential phù hợp với agent.
- `-Dmaven.repo.local`: đặt kho cache local có thể gắn với workspace, người dùng hoặc job.
- `clean verify`: build, kiểm thử và chạy các bước xác minh đã cấu hình trên một đầu ra mới.

Với CI chạy nhiều job song song, cần cân nhắc **quyền ghi, dung lượng và tính an toàn của việc dùng chung kho local**. Có thể dành kho riêng cho từng job để dễ cách ly, hoặc dùng cơ chế cache mà hệ thống CI hỗ trợ để giảm lần tải sau. Nếu khởi tạo một cache trống, lần build đầu cần mạng và quyền truy cập repository hợp lệ.

**Không đồng nhất việc tách kho local với việc tách hoàn toàn môi trường.** Khi đổi đường dẫn `maven.repo.local`, những thứ như phiên bản JDK, biến môi trường, global settings, cấu hình trong `.mvn/` hoặc kết quả sinh ra ở `target/` vẫn có thể tác động đến build. Khi cần tái lập kết quả, kiểm soát và ghi lại các yếu tố đó riêng.

## 10. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Maven báo không tìm thấy settings file | `-s` trỏ sai hoặc tệp chưa được tạo | Kiểm tra đường dẫn tuyệt đối, tên file và quyền đọc |
| XML settings không parse được | Sai cấu trúc `<settings>`, thẻ chưa đóng, ký tự không hợp lệ | Kiểm tra XML và lỗi dòng/cột Maven in ra |
| Maven vẫn dùng kho không mong muốn | Truyền sai tên property; quên `-s`; một cấu hình có hiệu lực khác đặt kho local | Kiểm tra nguyên văn command, `help:effective-settings` và log `-X` |
| `-Dmaven.repo.local` có khoảng trắng bị tách thành nhiều argument | Shell tách chuỗi đường dẫn | Đặt toàn bộ `"-Dmaven.repo.local=..."` trong dấu ngoặc kép |
| Báo `Permission denied` hoặc không tạo được thư mục | Đường dẫn kho cục bộ không thể ghi hoặc ổ đĩa hết chỗ | Chọn thư mục có quyền ghi, kiểm tra quyền/dung lượng |
| Lần đầu build với kho mới rất chậm | Cache mới trống nên Maven tải dependencies/plugins | Kiểm tra mạng, mirror, proxy; dùng cache phù hợp trong CI |
| `mvn -o` thất bại ở kho riêng | Artifact/plugin chưa có trong kho riêng | Chạy online để tải trước, rồi mới thử offline |
| `401 Unauthorized` hoặc `403 Forbidden` | Cấu hình server ID, token, URL hoặc quyền repository sai | Kiểm tra ID, credentials, quyền; không in secret vào log |
| `404` hoặc không tìm thấy artifact dù máy khác build được | Mirror/repository profile khác; artifact chưa được xuất bản | Kiểm tra effective settings và vị trí repository từ xa |
| JAR vừa `package` không có trong local repo | `package` chỉ tạo sản phẩm trong `target/` | Chạy `install` nếu cần cài artifact vào local repository |
| `clean` rồi kho local vẫn còn nguyên | `clean` dọn đầu ra dự án, không dọn cache Maven | Đây là hành vi bình thường; không xóa kho cục bộ để khắc phục một lỗi chưa xác định |

**Đặc biệt:** không dùng `-o` (offline) để xác minh một kho local hoàn toàn mới. Maven vẫn cần plugin, dependencies và metadata đã có sẵn; thiếu bất kỳ phần cần thiết nào thì build có thể thất bại dù mã Java và POM đúng.

## 11. Bài tập tự kiểm tra

1. Tạo một settings riêng đặt `<localRepository>` là `${user.home}/.m2/repository-lab`. Dự đoán kho local khi chạy `mvn -s ... test`.
2. Dùng cùng settings đó nhưng bổ sung `-Dmaven.repo.local` trỏ tới `repository-experiment`. Dự đoán kho local nào được Maven ưu tiên và giải thích vì sao.
3. Chạy dự án `maven-settings-lab` tới phase `test` hoặc `verify` với kho local riêng. Xác định hai đường dẫn khác nhau: nơi chứa `App.class` và nơi cache JUnit.
4. Chạy `install` với kho local riêng; tìm artifact `dev.learn:maven-settings-lab:1.0.0-SNAPSHOT` trong kho ấy.
5. Chạy `help:effective-settings` với `-s`. Giải thích vì sao nội dung `<localRepository>` ở đầu ra này chưa phải bằng chứng cuối cùng khi cũng truyền `-Dmaven.repo.local`.
6. Giải thích khác biệt giữa `-s`, `-f`, `-gs` và `-Dmaven.repo.local`. Tại sao chọn kho local riêng không thay đổi máy chủ remote repository?
7. Nếu build offline thất bại trong kho mới, xác định cần tải gì ở chế độ online trước khi thử lại; giải thích tại sao không nên mặc định xem đó là lỗi logic của dự án.

Bạn đã hiểu bài khi có thể thực hiện và giải thích một lệnh Maven với **settings xác định**, **kho local xác định**, và tự kiểm chứng rằng cả hai thực sự đang được sử dụng. Đây là kỹ năng quan trọng để debug sự khác biệt giữa máy cá nhân, máy đồng nghiệp và pipeline CI.

## 12. Nguồn tham khảo chính thức

- [Maven — CLI Options Reference](https://maven.apache.org/ref/3.9.7/maven-embedder/cli.html)
- [Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
