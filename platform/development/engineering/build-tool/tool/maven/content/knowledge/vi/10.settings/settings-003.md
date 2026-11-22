# localRepository và cách thay đổi vị trí kho cục bộ trong Maven

## 1. localRepository là gì?

Khi chạy Apache Maven, có hai khái niệm rất dễ nhầm:

- **Local repository (kho cục bộ):** vùng lưu trữ trên ổ đĩa của máy chạy Maven. Maven sử dụng nó để lưu các artifact đã tải về từ remote repository và các artifact do chính máy này tạo rồi `install`.
- **Remote repository (kho từ xa):** máy chủ chứa artifact để Maven tải về hoặc triển khai lên, ví dụ Maven Central hoặc repository manager của tổ chức.

Đường dẫn mặc định của local repository trong Maven thông thường là:

```text
${user.home}/.m2/repository
```

Trong đó `${user.home}` là **Java system property chỉ thư mục home của tài khoản chạy Maven**, không phải đường dẫn của dự án. Ví dụ:

| Môi trường | Vị trí thường gặp |
| --- | --- |
| Linux | `/home/alice/.m2/repository` |
| macOS | `/Users/alice/.m2/repository` |
| Windows | `C:\Users\Alice\.m2\repository` |
| CI/container | Home của tài khoản chạy job/container, có thể khác máy cá nhân |

Các giá trị ví dụ không phải đường dẫn cố định trên mọi máy. Hãy kiểm tra Java user home và cấu hình Maven đang có hiệu lực khi cần xác định chính xác.

**Vì sao có local repository?** Maven không cần tải lại toàn bộ dependency/plugin ở mỗi lần build nếu artifact phù hợp đã có trong kho cục bộ. Khi gọi `mvn install`, Maven còn ghi artifact của project vào đây để các dự án Maven khác trên cùng môi trường sử dụng được.

Local repository không phải `target/`. `target/` là output build trong từng module; local repository là kho dùng khi Maven giải quyết tọa độ artifact (groupId, artifactId, version, loại artifact...) cho nhiều project.

## 2. Kho cục bộ chứa những gì?

Một local repository thông dụng có đường dẫn lưu artifact theo cấu trúc suy ra từ Maven coordinates. Ví dụ artifact `org.apache.commons:commons-lang3:3.14.0` có thể xuất hiện:

```text
~/.m2/repository/
└── org/
    └── apache/
        └── commons/
            └── commons-lang3/
                └── 3.14.0/
                    ├── commons-lang3-3.14.0.jar
                    ├── commons-lang3-3.14.0.pom
                    └── ... các tệp metadata/checksum liên quan
```

Kho cục bộ thường chứa:

- Dependency JAR, POM và metadata đi kèm;
- Maven plugin và các dependency của plugin;
- Parent POM, BOM và các artifact cần để phân giải build;
- Artifact do `mvn install` cài vào kho;
- Một số metadata liên quan trạng thái tải, nguồn remote và cập nhật.

**Đừng coi đây là thư mục quản lý thủ công.** Maven Resolver có thể sử dụng metadata, locking và cách bố trí repo khác nhau (kể cả cơ chế *split local repository* khi được cấu hình). Không nên tự thả JAR vào các folder hoặc sửa những file metadata để “làm Maven nhận ra dependency”. Muốn cài artifact do dự án tạo, dùng `mvn install`; muốn xử lý artifact bên ngoài theo cách được hỗ trợ, dùng công cụ/plugin tương ứng.

Một local repository vừa là **cache tải về**, vừa là **nơi lưu artifact cài cục bộ**. Di chuyển nó tác động đến hai vai trò đó.

## 3. Cấu hình localRepository nằm ở đâu?

Trong Maven 3, nơi cấu hình phổ biến và được Apache Maven khuyến nghị là **`settings.xml`** ở một trong hai cấp:

| Cấp | Đường dẫn | Phạm vi |
| --- | --- | --- |
| User settings | `${user.home}/.m2/settings.xml` | Người dùng chạy Maven |
| Global/installation settings | `${maven.home}/conf/settings.xml` | Bản cài Maven và người dùng thuộc bản cài đó |

Khi cả hai tồn tại, Maven kết hợp cấu hình và **user settings có ưu tiên so với global settings** ở các giá trị xung đột theo quy tắc merge. Nếu không có user `settings.xml`, Maven vẫn dùng mặc định; không cần tạo file này chỉ để build Maven.

Đường dẫn `${maven.home}` thuộc bản cài Maven thực tế, không phải thư mục project; Maven Wrapper có thể sử dụng một bản Maven riêng. Vì vậy kiểm tra `mvn -version` hoặc `./mvnw -version` để biết Maven đang chạy từ đâu.

**Đặt `<localRepository>` ở cấp trực tiếp dưới phần tử gốc `<settings>`**, không phải trong `pom.xml`, `<profile>` hay `<repositories>`.

Lưu ý với Maven 4: nó cũng có cơ chế *project settings* ở `.mvn/settings.xml`, nhưng các mục dành riêng cho người dùng/máy như `localRepository` bị bỏ qua tại đó. Hãy dùng user/installation settings hoặc cách chỉ định local repo của Maven cho môi trường build, không đặt đường dẫn cache cá nhân vào project settings.

## 4. Cách 1 — Đổi vị trí lâu dài bằng user settings.xml

Đây là lựa chọn phù hợp khi một người dùng muốn Maven **mặc định** dùng kho khác trong mọi project của mình.

Ví dụ Linux/macOS: mong muốn đặt kho ở `/home/alice/maven-cache/repository`. Trong `~/.m2/settings.xml` của chính tài khoản `alice`, đặt:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">
    <localRepository>/home/alice/maven-cache/repository</localRepository>
</settings>
```

Ví dụ trên là **tệp settings.xml đầy đủ và tối thiểu** cho mục đích đổi local repository. Hãy thay đường dẫn theo tài khoản và ổ đĩa **thực tế** của máy, không chép nguyên tên `alice` vào máy mình.

Maven Settings Reference cũng hỗ trợ nội suy Java system properties; nếu muốn đặt trong home mà không hard-code tài khoản, có thể thay nội dung phần tử bằng:

```xml
<localRepository>${user.home}/maven-cache/repository</localRepository>
```

Dòng trên là **một phần tử để thay thế trong settings.xml**, không phải tệp XML độc lập. Vì `${user.home}` được Maven giải quyết từ Java system property, giá trị cuối cùng là đường dẫn tuyệt đối nếu Java home được xác định bình thường.

### Thao tác trên Linux/macOS

Tạo thư mục cấu hình nếu chưa có:

```bash
mkdir -p "$HOME/.m2"
```

Nếu `~/.m2/settings.xml` **đã tồn tại**, mở file đó và thêm/chỉnh **một** phần tử `<localRepository>` trực tiếp dưới `<settings>`. Không ghi đè toàn bộ file đang chứa `mirrors`, `proxies`, `servers` hoặc profile mà bạn cần giữ. Nếu chưa tồn tại, có thể tạo file theo mẫu XML ở trên, sửa đường dẫn trước khi lưu.

Có thể chủ động tạo thư mục kho:

```bash
mkdir -p "$HOME/maven-cache/repository"
```

Maven cũng có thể tạo phần thư mục cần thiết khi nó có quyền ghi, nhưng tạo trước giúp phát hiện vấn đề permission sớm.

### Thao tác trên Windows

Vị trí user settings thường là `C:\Users\<TênNgườiDùng>\.m2\settings.xml`. Ví dụ cấu hình đường dẫn tuyệt đối ở ổ `D:`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">
    <localRepository>D:/maven-cache/repository</localRepository>
</settings>
```

Trong XML nên dùng dấu `/` để tránh nhầm việc escape đường dẫn Windows; Java/Maven có thể xử lý đường dẫn Windows hợp lệ. Không dùng ví dụ ổ `D:` nếu máy không có ổ đó.

Tạo thư mục trên PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path 'D:\maven-cache\repository' | Out-Null
```

PowerShell cũng có thể mở file theo `$env:USERPROFILE` nhưng Java `user.home` mới là giá trị Maven dựa vào. Trên môi trường có dịch vụ, user khác hoặc container, hai đường dẫn không nhất thiết tương đương với home của tài khoản đang đăng nhập giao diện.

### Quy tắc quan trọng: luôn dùng đường dẫn tuyệt đối

Theo tài liệu cấu hình Apache Maven, `localRepository` cần là **đường dẫn tuyệt đối**. Tránh:

```xml
<localRepository>../repository</localRepository>
```

vì nó là đường dẫn tương đối; đổi working directory có thể khiến việc định vị không nhất quán hoặc không hợp lệ.

Dùng giá trị tuyệt đối, ví dụ `/opt/maven-cache/repository` hoặc `C:/maven-cache/repository`, hoặc biểu thức `${user.home}/maven-cache/repository` được Maven nội suy đúng.

## 5. Cách 2 — Đổi kho chỉ cho một lần chạy bằng -Dmaven.repo.local

Nếu chỉ muốn một build dùng local repository riêng, không cần sửa user settings:

```bash
mvn -B -ntp -Dmaven.repo.local=/tmp/maven-repo-isolated clean verify
```

Trong Maven 3, `-Dmaven.repo.local=<đường-dẫn>` là **user property** để chỉ định local repo cho tiến trình Maven đang chạy; nó được ưu tiên hơn giá trị `localRepository` có trong `settings.xml` cho việc chọn repo thực tế của phiên chạy đó. Đây là cách quen thuộc cho CI job, container và build thử nghiệm độc lập.

Ví dụ dự án có Maven Wrapper:

```bash
./mvnw -B -ntp -Dmaven.repo.local=/opt/build-cache/maven-repository clean package
```

Trong Bash, khi đường dẫn có khoảng trắng, nên trích dẫn **toàn bộ đối số**:

```bash
mvn -B -ntp "-Dmaven.repo.local=$HOME/Maven Cache/repository" clean package
```

Cách này vẫn truyền một đối số duy nhất `-Dmaven.repo.local=...` cho Maven. Tuy nhiên chọn đường dẫn cache không có khoảng trắng thường giúp script và công cụ phụ trợ dễ xử lý hơn.

### Windows PowerShell

```powershell
$repoPath = 'D:\maven-cache\repository'
New-Item -ItemType Directory -Force -Path $repoPath | Out-Null
mvn "-Dmaven.repo.local=$repoPath" -B -ntp clean package
$exitCode = $LASTEXITCODE
Write-Host "Maven exit code: $exitCode"
```

Ví dụ cần Maven trong `PATH` và ổ `D:` hợp lệ. Nếu dùng Wrapper, đổi `mvn` thành `.\mvnw.cmd`. Biến `$LASTEXITCODE` phải được đọc ngay sau lệnh native Maven để đánh giá thành công/thất bại, tránh để một chương trình native khác thay đổi nó.

**Khác biệt cốt lõi:**
- `settings.xml`: thay đổi hành vi mặc định cho tài khoản/bản cài trong các lượt chạy sau.
- `-Dmaven.repo.local`: áp dụng cho **lượt chạy cụ thể**; không tự sửa `settings.xml`.
- Khi dùng cả hai, kiểm tra vị trí **Maven thực sự dùng** theo lệnh, không chỉ nhìn file settings.

Trong CI, nếu dùng workspace tạm, tên đường dẫn cache có thể cần tách theo phiên bản Java/Maven, runner hoặc nhánh công việc. Quyết định phạm vi cache tùy công cụ CI và cách tổ chức build.

## 6. Cách 3 — Dùng một settings.xml thay thế với -s

Ngoài việc chỉnh user settings mặc định, Maven hỗ trợ dùng **file user settings riêng**:

```bash
mvn -s /opt/ci/config/maven-settings.xml -B -ntp clean verify
```

Tương đương cờ dài `--settings` trong Maven 3. File chỉ định là một **settings.xml** hợp lệ, có thể chứa `localRepository` cùng mirror/proxy/servers cần thiết. Đường dẫn file cũng nên được xác định rõ và có quyền đọc.

Trên Windows PowerShell:

```powershell
mvn -s 'D:\ci-config\settings.xml' -B -ntp clean verify
```

**Không nhầm hai đường dẫn:**
- `-s /opt/ci/config/maven-settings.xml` chỉ **vị trí file cấu hình** mà Maven đọc.
- `<localRepository>/opt/ci/cache/repository</localRepository>` trong file đó chỉ **vị trí kho artifact**.

Nếu dùng `-Dmaven.repo.local=...` cùng với `-s`, local repo thực tế thường theo giá trị user property `maven.repo.local`, không chỉ theo phần tử `localRepository` trong file settings. Khi cần xác minh, xem phần kiểm tra thực tế dưới đây.

Có thể dùng `-gs`/`--global-settings` trong Maven 3 để thay global settings; đó là file cấu hình khác, không phải cờ thay local repository trực tiếp. Cú pháp CLI và tổ chức settings có thể thay đổi ở Maven 4, nên kiểm tra tài liệu đúng phiên bản chạy nếu cần portable script nhiều bản Maven.

## 7. Cách xác minh Maven đã chuyển sang kho mới

**Đổi file cấu hình không đủ để kết luận.** Cần xác minh lệnh Maven được chạy bằng đúng user, đúng settings và đường dẫn local repository thực sự.

### Bước 1: xác định Maven và Java đang chạy

```bash
mvn -version
```

Nếu dùng Wrapper:

```bash
./mvnw -version
```

Chú ý `Java home`, Maven version, hệ điều hành và tài khoản thực thi. Trong CI hoặc IDE, Maven có thể dùng bản cài và tài khoản khác terminal của bạn.

### Bước 2: xem Effective Settings

```bash
mvn help:effective-settings -Doutput=effective-settings.xml
```

Maven Help Plugin tạo biểu diễn **effective settings**, giúp thấy giá trị `localRepository` đã được kết hợp từ user/global settings. Mở `effective-settings.xml` và tìm `<localRepository>`.

Có thể chỉ định file settings trong lệnh:

```bash
mvn -s /opt/ci/config/maven-settings.xml help:effective-settings -Doutput=effective-settings.xml
```

**Giới hạn:** effective settings là kiểm tra **mô hình settings**; khi còn có override từ CLI/JVM property (như `-Dmaven.repo.local`), không nên suy ra đường dẫn repo thực sự chỉ từ giá trị in trong output effective-settings. Phải đối chiếu lệnh được sử dụng và quan sát phiên build thật.

**Lưu ý bảo mật:** `help:effective-settings` có thể cho thấy địa chỉ server, mirror, proxy hoặc những cấu hình nhạy cảm khác. Không đăng file này lên issue công khai hoặc commit Git tùy tiện; rà soát và ẩn dữ liệu nhạy cảm trước khi chia sẻ.

### Bước 3: kiểm tra log của phiên build thật

Chạy một lệnh có repo override và bật debug trong **môi trường kiểm chứng**, ví dụ:

```bash
mvn -X -B -ntp -Dmaven.repo.local=/tmp/maven-repo-isolated validate
```

Trong debug log của Maven 3, thường có thông tin tương tự `Using local repository at ...`. Hãy đối chiếu đường dẫn được ghi, kiểm tra nó tương ứng với `-Dmaven.repo.local` hoặc settings đang dùng.

Đừng bật `-X` thường xuyên trong CI công khai: debug output rất dài và có thể lộ cấu hình/URL/nội dung nhạy cảm do plugin hoặc môi trường ghi ra. Nếu cần xác minh riêng, lưu log ở nơi an toàn rồi tắt `-X`.

### Bước 4: xác minh artifact đã xuất hiện ở kho mới

Chạy một build có dependency/plugin hoặc dùng `mvn install` với project nhỏ. Nếu kho mới trống, Maven sẽ phải tải về các thành phần chưa có (nếu không ở offline mode và repository truy cập được).

Không nhầm file sinh ở `target/` với artifact trong local repository. Với một project tự build có tọa độ `com.example:repo-location-demo:1.0.0`, sau khi `mvn install` thành công, file được cài thông thường nằm dưới:

```text
<localRepo>/com/example/repo-location-demo/1.0.0/
```

Cấu trúc này là ví dụ cho bố trí artifact thông thường, không phải API được khuyến nghị để script tự sửa hay tự thả artifact vào.

## 8. Bài thực hành độc lập với Java 17 và Maven

Tạo project nhỏ có hai file sau, để người học **tự xác minh repo bị đổi nhưng output build trong project không đổi**.

```text
repo-location-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/repo/App.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>repo-location-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ví dụ không khai báo dependency ngoài JDK, nhưng lần chạy đầu vẫn có thể phải tải Maven plugins và các thành phần liên quan từ remote repositories. `maven.compiler.release=17` yêu cầu build bằng JDK hỗ trợ release 17.

### `src/main/java/com/example/repo/App.java`

```java
package com.example.repo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Local repository demo");
    }
}
```

Tên file, package và public class phù hợp. Đây là chương trình Java độc lập, có thể biên dịch bằng cấu hình Maven ở trên.

### Chạy trên Linux/macOS

Từ thư mục chứa `pom.xml`:

```bash
mkdir -p "$HOME/maven-cache/repository"
mvn -B -ntp "-Dmaven.repo.local=$HOME/maven-cache/repository" clean install
java -cp target/classes com.example.repo.App
```

Trong build thành công, Maven sẽ đi qua các phase đến `install`: biên dịch nguồn chính, tạo `target/repo-location-demo-1.0.0.jar` rồi cài artifact vào local repository mới. Thư mục `target/` **vẫn ở project**, không bị chuyển sang `$HOME/maven-cache`.

**Stdout chính xác của lệnh Java cuối cùng:**

```text
Local repository demo
```

Log của lệnh Maven có thông báo INFO riêng; không nhầm chúng với stdout Java.

Để xem artifact `install` theo bố trí thông thường:

```bash
ls "$HOME/maven-cache/repository/com/example/repo-location-demo/1.0.0"
```

Tại đây thường có file JAR và POM cùng các metadata liên quan. Trên hệ thống có cơ chế local repository manager/split repo khác, bố trí nội bộ có thể không giống hoàn toàn, nên hãy ưu tiên kết quả `mvn install` và kiểm tra qua Maven thay vì phụ thuộc đường dẫn vật lý trong automation.

### Chạy trên Windows PowerShell

Từ thư mục chứa `pom.xml`:

```powershell
$repoPath = 'D:\maven-cache\repository'
New-Item -ItemType Directory -Force -Path $repoPath | Out-Null
mvn "-Dmaven.repo.local=$repoPath" -B -ntp clean install
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "Maven install failed (exit code $exitCode)"
    exit $exitCode
}
java -cp target/classes com.example.repo.App
```

Kết quả stdout của Java tương tự Linux/macOS nếu JDK, Maven và POM hợp lệ. Thay đường dẫn `D:` theo ổ đĩa của máy. Đừng xem việc thư mục được tạo là bằng chứng build thành công; hãy kiểm tra mã thoát và artifact.

**Nếu muốn kiểm tra cấu hình mặc định qua settings.xml**, hãy bỏ `-Dmaven.repo.local=...` khỏi lệnh ở trên. Như vậy bạn có thể phân biệt hiệu quả của **một cấu hình lâu dài** với **một override theo lượt chạy**.

## 9. Chuyển vị trí từ kho cũ sang kho mới: làm gì với cache?

Khi thay đường dẫn local repo, Maven **không tự chuyển toàn bộ artifact từ kho cũ sang kho mới** chỉ vì bạn đổi `<localRepository>` hoặc thêm `-Dmaven.repo.local`. Kho mới ban đầu có thể trống; Maven sẽ tải lại dependency/plugin cần thiết khi build, miễn là có kết nối và repository phù hợp.

Có hai lựa chọn vận hành:

**A. Cho Maven tải lại vào kho mới (cách đơn giản, thường an toàn nhất).**

1. Chọn đường dẫn mới, bảo đảm có đủ dung lượng và quyền đọc/ghi.
2. Cấu hình bằng user settings hoặc một cờ CLI cho lượt thử.
3. Chạy build trực tuyến phù hợp, ví dụ `mvn -B -ntp clean verify`.
4. Xác minh cache hoạt động và build hoàn tất trước khi cân nhắc dọn kho cũ.
5. Nếu còn những artifact chỉ được `install` trên máy cũ mà không có remote repository, cần xây dựng/cài lại các artifact đó trong kho mới.

**B. Di chuyển/copy cache cũ khi thật sự cần tránh tải lại lớn.**

Việc copy cần được đánh giá cẩn thận vì local repo có metadata về nguồn remote, snapshot và trạng thái phân giải. Nếu tổ chức quyết định chuyển cache vật lý, hãy **dừng những tiến trình Maven đang dùng kho**, sao lưu, copy đầy đủ bằng công cụ phù hợp hệ điều hành rồi kiểm tra build; không sửa từng file .jar/.pom hay metadata theo phỏng đoán. Trong môi trường dùng custom repository manager/split repo, nên tuân theo hướng dẫn sản phẩm và không giả định bố cục cổ điển.

**Không xóa kho cũ ngay sau khi đổi cấu hình.** Ngoài cache có thể còn artifact snapshot/phiên bản nội bộ chỉ tồn tại cục bộ, cần kiểm kê trước khi dọn.

## 10. Local repo trong CI/CD, Docker và môi trường nhiều người dùng

### CI/CD

Mỗi runner có thể có home và filesystem khác. Nếu dùng workspace tạm, kho mặc định `~/.m2/repository` có thể mất sau job; nếu CI hỗ trợ cache, cần chỉ định rõ thư mục giữ lại. Ví dụ:

```bash
mvn -B -ntp "-Dmaven.repo.local=$HOME/.cache/maven-repo" clean verify
```

Cấu hình lưu/khôi phục cache tại CI là bước **riêng**. Chỉ đặt `-Dmaven.repo.local` không tự khiến cache tồn tại qua nhiều runner hoặc nhiều job.

Thiết kế cache nên xem xét quyền ghi, tính tương thích Java/Maven, thay đổi dependencies và chính sách lưu giữ. Nếu runner có nhiều job song song chia sẻ một thư mục local repo, cần chắc chắn cơ chế locking/cách triển khai hỗ trợ dùng đồng thời; tốt hơn là cache riêng khi không có sự bảo đảm này.

### Docker/container

Trong container, `user.home` có thể là `/root` hoặc home của user không phải root. Các lớp image và volume cũng quyết định local repo có được giữ lại sau lần chạy hay không. Có thể dùng cờ repo trỏ đến một volume được mount, nhưng phải bảo đảm user chạy Maven có quyền ghi. Không giả định `~/.m2` trên host và trong container là cùng một thư mục.

### Máy dùng chung

Apache Maven Settings Reference nhắc tới tình huống build server dùng một local repo chung. Tuy nhiên, repo chung phải giải quyết **quyền truy cập, concurrent writers, metadata/locking và isolation**. Đối với nhiều người dùng/runner độc lập, nên cân nhắc repository manager từ xa và cache cục bộ riêng thay vì cho mọi tiến trình chỉnh một thư mục chung không kiểm soát.

## 11. So sánh các tùy chọn và các chỗ dễ nhầm

| Cấu hình/lệnh | Mục đích | Có đổi localRepository không? |
| --- | --- | --- |
| `<localRepository>...` trong user `settings.xml` | Đường dẫn kho mặc định cho người dùng | **Có** |
| `-Dmaven.repo.local=/abs/path` | Override repo cho lượt chạy Maven | **Có** |
| `-s /abs/path/settings.xml` | Chọn file user settings khác | **Gián tiếp** nếu file đó định nghĩa localRepository |
| `-gs /abs/path/settings.xml` (Maven 3) | Chọn global settings khác | **Gián tiếp** theo nội dung và merge |
| `<repositories>...` trong POM/settings profile | Khai báo địa chỉ **remote** artifact repositories | **Không** |
| `<distributionManagement>...` trong POM | Định nghĩa đích triển khai artifact từ xa | **Không** |
| `-o` / `--offline` | Không kết nối remote khi giải quyết artifact | **Không** |
| `-U` | Buộc cập nhật kiểm tra snapshot/metadata phù hợp | **Không** |
| `mvn clean` | Dọn output build của project (thường `target/`) | **Không** |
| `<build><directory>...` trong POM | Đổi thư mục output build của project | **Không** |
| `<localRepository>...` trong `pom.xml` | Sai vị trí mô hình POM | **Không hợp lệ** |
| `<localRepository>...` trong project settings Maven 4 | Settings gắn với project | **Bị bỏ qua** ở nơi này |

Đặc biệt: `mvn clean` **không dọn local repository**. Nó gọi Clean Plugin để xóa output build, thường `target/`. Xóa cache local repository là một thao tác quản trị dữ liệu khác, có thể gây tải lại lớn và mất artifact chỉ cài cục bộ.

## 12. Lỗi thường gặp khi đổi localRepository

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Maven vẫn dùng `~/.m2/repository` | Sửa nhầm `settings.xml`, lệnh chạy bằng user khác, settings không được đọc hoặc CLI override | Kiểm tra `mvn -version`, file user/global settings, `-s`, `-Dmaven.repo.local` và debug log |
| `Non-parseable settings` | XML hỏng: thiếu thẻ đóng, sai namespace/cú pháp, ký tự `&` chưa escape | Sửa XML, giữ phần tử `<localRepository>` ngay dưới `<settings>` |
| Maven báo đường dẫn không hợp lệ | Dùng path tương đối, ký tự không hợp lệ, drive không tồn tại | Dùng path tuyệt đối và ổ đĩa có thật |
| Permission denied khi tải artifact | Tài khoản Maven không được tạo/ghi vào kho mới | Cấp quyền phù hợp cho tài khoản chạy, không mặc định chạy root/admin |
| Sau khi đổi đường dẫn thì tải lại rất nhiều | Repo mới trống hoặc khác repo cũ | Đây là hiện tượng bình thường; kiểm tra network, dung lượng và cache |
| Offline build thất bại vì thiếu artifact | Bật `-o` trong khi repo mới chưa có đủ dependency/plugin/parent | Tải trước khi offline hoặc dùng repo đủ cache |
| IDE dùng repo khác terminal | IDE có Maven runtime/settings/VM options riêng | Kiểm tra cấu hình Maven trong IDE và đồng bộ với mục tiêu |
| CI cache không được tái dùng | Cache workflow lưu sai thư mục hoặc path thay đổi giữa job | Đối chiếu path Maven dùng và path CI cache thực sự lưu |
| Maven không tải từ Maven Central/proxy | Sai mirror/proxy/server trong settings, lỗi mạng/TLS | Kiểm tra remote settings, credentials và kết nối; đổi local repo không sửa network |
| Có artifact trong repo cũ nhưng repo mới không thấy | `-Dmaven.repo.local` hoặc user settings đã chọn kho khác | Kiểm tra cấu hình đang hoạt động; nếu cần cài lại artifact qua Maven |
| Dùng chung repo gây lỗi lạ khi song song | Quá trình ghi/chia sẻ repo không an toàn hoặc metadata bị tranh chấp | Tách cache, cấu hình cơ chế quản lý repo phù hợp, tránh sửa trực tiếp file |
| Effective settings cho thấy path A nhưng Maven dùng path B | Có thể có override CLI/JVM property | Kiểm tra lệnh và debug log, không chỉ nhìn file effective-settings |

### Quy trình chẩn đoán có thứ tự

1. **Ghi lại câu lệnh thật** đang chạy, bao gồm `-s`, `-gs` (nếu Maven 3), `-Dmaven.repo.local` và Wrapper.
2. **Kiểm tra Maven/JDK**: `mvn -version` hoặc `./mvnw -version`; xác định user account chạy job.
3. **Kiểm tra user/global settings**: mở đúng file đã dùng, tìm `<localRepository>`; không sửa `pom.xml` để đổi cache.
4. **Sinh effective settings** để xem cấu hình settings sau merge; lưu ý file này có thể chứa dữ liệu nhạy cảm và không nhất thiết phản ánh CLI override.
5. **Chạy build thử có log kiểm chứng** rồi kiểm tra đường dẫn repo thực tế, quyền ghi và artifact mới được cài/tải.
6. **Xác minh exit code**. Repo đúng vị trí không đồng nghĩa build thành công; khi cần, xem Maven log để phân biệt lỗi dependency, network, test hay quyền truy cập.

## 13. Checklist và câu hỏi tự kiểm tra

**Checklist:**

- Tôi hiểu `localRepository` là kho artifact/cached metadata, **không** phải output build `target/`.
- Tôi biết mặc định Maven là `${user.home}/.m2/repository` và biết user thực tế đang chạy Maven.
- Tôi đặt `<localRepository>` trong **user/global settings.xml**, không đặt trong `pom.xml`.
- Đường dẫn repo cuối cùng là **absolute path**, có ổ đĩa thật và quyền đọc/ghi.
- Tôi biết dùng `-Dmaven.repo.local` để tạm thời chọn repo riêng cho **một lượt chạy**.
- Tôi phân biệt `-s` (chọn file cấu hình) với `-Dmaven.repo.local` (chọn repo).
- Tôi đã kiểm chứng bằng effective settings **và**, khi có override, bằng lệnh/log/artifact thực tế.
- Tôi không xóa hoặc tự sửa metadata local repo khi chưa hiểu tác động tới Maven Resolver.
- Nếu dùng CI/container, tôi đã xét cache persistence, user permissions, concurrency và bảo mật.

**Câu hỏi ôn tập:**

1. Tại sao hai project Maven cùng một máy thường tái sử dụng được dependency đã tải?
2. `target/repo-location-demo-1.0.0.jar` và file JAR được cài bởi `mvn install` khác nhau ở đâu?
3. Nếu chuyển `<localRepository>` sang một ổ mới trống, lần build đầu có thể diễn ra chuyện gì?
4. Khi nào nên dùng user `settings.xml`, khi nào nên dùng `-Dmaven.repo.local`?
5. Có nên đặt đường dẫn `./.m2/repository` vào `<localRepository>` để tạo cache ngay trong project không? Vì sao?
6. `mvn clean` có xóa local repository không?
7. Nếu Help Plugin in đường dẫn settings A nhưng Maven đang chạy với `-Dmaven.repo.local=B`, cần xác minh điều gì?
8. Vì sao không nên đưa settings chứa mật khẩu hoặc file effective settings nội bộ vào Git công khai?

**Tóm tắt:** `localRepository` chỉ **vị trí lưu cache và artifact Maven trên máy**. Mặc định là `${user.home}/.m2/repository`. Để thay đổi lâu dài, đặt `<localRepository>` trong user/global `settings.xml`; để tách cache cho một lượt build hoặc CI, dùng `-Dmaven.repo.local=/đường/dẫn/tuyệt/đối`. Sau khi thay đổi, cần kiểm tra Maven chạy bằng user/settings nào, đường dẫn thực tế có được sử dụng và build có thành công hay không.

## Tài liệu Apache Maven

- [Settings Reference — localRepository, user/global settings](https://maven.apache.org/settings.html)
- [Guide: Configuring Maven — Changing Your Local Repository](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Maven Local Repositories — cache và artifact đã cài](https://maven.apache.org/repositories/local.html)
- [Maven Help Plugin: help:effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven — Maven CLI Options](https://maven.apache.org/ref/3.9.16/maven-embedder/cli.html)
