# Settings cấp cài đặt, cấp người dùng và cấu hình được hợp nhất trong Maven

## 1. Vì sao Maven cần `settings.xml` ngoài `pom.xml`?

Một dự án Java dùng Maven thường có `pom.xml` để định nghĩa **danh tính dự án, dependencies, plugin và cách build**. Nhưng bản thân Maven còn phải biết **môi trường đang chạy**: local repository đặt ở đâu, có đi qua proxy không, artifact được tải từ mirror nào, và dùng credentials nào để truy cập repository riêng.

Những thiết lập mang tính **máy cài đặt hoặc người dùng** không nên được sao chép vào POM chung của dự án. Đó là mục đích của **`settings.xml`**.

Bài này tập trung vào ba khái niệm:

1. **Settings cấp cài đặt (global/installation settings):** cấu hình mặc định của một bản cài Maven.
2. **Settings cấp người dùng (user settings):** cấu hình riêng của người chạy Maven trên máy đó.
3. **Effective settings:** cấu hình Maven thực sự thấy sau khi **hợp nhất** các settings thích hợp và áp dụng giá trị hiệu lực.

Bạn sẽ biết vị trí file, quy tắc ưu tiên, cách sử dụng `-s` và `-gs`, cách xem `help:effective-settings`, và cách chẩn đoán khi một máy build được còn máy khác không.

> **Phạm vi ví dụ:** các quy tắc hai cấp dưới đây là mô hình quen thuộc của Maven 3.x. Maven 4 có thêm một số cơ chế cấu hình, trong đó có project settings ở `.mvn/settings.xml` ở các phiên bản hỗ trợ. Vì vậy, với Maven 4, cần kiểm tra tài liệu của **đúng phiên bản** trước khi khẳng định toàn bộ thứ tự ưu tiên.

## 2. Ba cấp cấu hình hay gặp: project, installation, user

### 2.1. Cấu hình của dự án — `pom.xml`

`pom.xml` nằm trong dự án và thường được commit lên Git. Nó mô tả:

- `groupId`, `artifactId`, `version`, `packaging`;
- `dependencies`, `dependencyManagement`;
- `build/plugins`, compiler/test/packaging settings;
- repositories liên quan đến dự án khi thích hợp;
- profiles và những cấu hình build có thể chia sẻ.

POM nên cố gắng **portable**: người khác clone repository vẫn hiểu cách biên dịch/test mà không phải chép đường dẫn hoặc password riêng của máy phát triển.

### 2.2. Cấu hình cấp cài đặt — global settings

Với Maven 3, đường dẫn mặc định:

```text
${maven.home}/conf/settings.xml
```

Tức là tệp `conf/settings.xml` trong thư mục **bản phân phối Maven đang được sử dụng**, không nhất thiết là thư mục code Java và không nhất thiết trùng với `JAVA_HOME`. Ví dụ một máy có Maven 3.9.x được cài ở `C:\tools\apache-maven` thì file toàn cục thường là `C:\tools\apache-maven\conf\settings.xml`.

Global settings thích hợp cho các giá trị chung của một Maven installation, chẳng hạn chính sách repository/mirror được quản trị tại một image hoặc máy build. Khi **nâng cấp/thay Maven installation**, file global có thể khác; đừng giả định nhiều bản Maven trên cùng máy chia sẻ chung một global settings.

### 2.3. Cấu hình cấp người dùng — user settings

Đường dẫn mặc định:

```text
${user.home}/.m2/settings.xml
```

Trên Linux/macOS, đường dẫn thường tương ứng `~/.m2/settings.xml`. Trên Windows, thường nằm trong `.m2` dưới thư mục home của tài khoản đang chạy Maven.

User settings thường chứa tùy chỉnh của **một người dùng**: local repository riêng, proxy, server credentials, mirror, profile, activeProfiles. File này **không bắt buộc phải tồn tại**: nếu thiếu, Maven vẫn dùng defaults và cấu hình global sẵn có.

Đặc biệt trong CI, “người dùng” có thể là **tài khoản service/runner**, không phải tài khoản đang mở giao diện máy. Hãy tìm `user.home` của **process Maven thực tế** thay vì đoán dựa vào tên người đăng nhập.

### 2.4. Bảng phân biệt

| Tiêu chí | `pom.xml` | Global `settings.xml` | User `settings.xml` |
| --- | --- | --- | --- |
| Phạm vi | Một project / chuỗi kế thừa POM | Bản cài Maven | Tài khoản chạy Maven |
| Vị trí Maven 3 | Dự án | `${maven.home}/conf/settings.xml` | `${user.home}/.m2/settings.xml` |
| Nên commit cùng source? | Thường có | Không | Không; nhất là khi chứa credentials |
| Điều khiển dependency/plugin build? | Có, trực tiếp | Không thay POM | Không thay POM |
| Có thể cấu hình mirror, proxy, server credentials? | Không nên lưu credentials trong POM | Có | Có |
| Nếu cả hai settings cùng định nghĩa một giá trị? | Không thuộc phép merge settings | Cơ sở | User settings **ưu tiên** khi xung đột |

**Hai settings.xml không phải hai project, không phải parent/child POM**, và Maven không dùng `<parent>` để hợp nhất chúng. Cấu hình `settings.xml` có sơ đồ XML riêng, khác POM.

## 3. Những phần quan trọng trong `settings.xml`

Một `settings.xml` có root `<settings>`, với những nhóm phần tử thường gặp:

| Phần tử | Tác dụng |
| --- | --- |
| `<localRepository>` | Đường dẫn local Maven repository; mặc định thường `${user.home}/.m2/repository` |
| `<offline>` | `true` để chạy offline; mặc định `false` |
| `<interactiveMode>` | Có cho Maven hỏi người dùng khi cần hay không |
| `<pluginGroups>` | Bổ sung các groupId để tìm plugin khi gọi goal bằng tiền tố ngắn |
| `<servers>` | Credentials và cấu hình kết nối của server/repository theo `id` |
| `<mirrors>` | Định tuyến request tới mirror của một hoặc nhiều repository |
| `<proxies>` | Proxy dùng khi Maven kết nối network |
| `<profiles>` | Environment-specific properties/repositories/pluginRepositories |
| `<activeProfiles>` | Danh sách id của profile được kích hoạt mặc định |

**Settings profiles có phạm vi giới hạn.** Trong Maven 3, profile khai báo trong `settings.xml` chỉ được dùng để đóng góp các phần tử liên quan đến properties, repositories và pluginRepositories; nó **không phải chỗ để khai báo toàn bộ `<build>`, `<dependencies>`, plugin executions** như một profile POM. Khi cần quy tắc build chung cho công ty, dùng **parent POM** hoặc cách chia sẻ cấu hình project thích hợp.

### 3.1. `<servers>` và mirror/repository phải khớp `id`

Ví dụ một repository nội bộ cần xác thực: trong POM, profile hoặc settings có thể khai báo repository với `id=company-releases`. Nếu Maven sử dụng một mirror có `id=company-mirror`, cấu hình credentials cần được liên kết với **id của server/mirror được chọn thực tế**, không suy luận từ URL hoặc artifactId.

Ví dụ **cấu trúc minh họa, không phải file độc lập**:

```xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>your-login</username>
        <password>DO_NOT_STORE_REAL_PASSWORD_IN_EXAMPLES</password>
    </server>
</servers>
```

Không copy placeholder thành thông tin thật hay đưa file chứa password lên Git. Hãy dùng cơ chế quản lý secret/credentials của CI và phương pháp mã hóa password mà Maven phiên bản tương ứng hỗ trợ. **Settings có thể chứa thông tin nhạy cảm**, cần hạn chế quyền đọc và kiểm soát log khi debug.

### 3.2. `<mirrors>` không đồng nghĩa `<repositories>`

`<mirror>` có `<id>`, `<url>` và `<mirrorOf>` để chuyển hướng các repository được chọn. Nó không tự tạo nội dung repository, không tự cấp quyền, và không biến một địa chỉ không truy cập được thành artifact có thật.

Ví dụ với một tổ chức có repository manager:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <url>https://repo.example.invalid/maven</url>
        <mirrorOf>*</mirrorOf>
    </mirror>
</mirrors>
```

Đây là **đoạn XML minh họa**, URL `example.invalid` cố ý không dùng được và **không** nằm trong bộ ví dụ thực hành ở mục 5. Trong thực tế, dùng URL chính thức được bộ phận quản trị cung cấp. `mirrorOf=*` có phạm vi rộng và có thể ảnh hưởng tất cả repository mà Maven định truy cập; không áp dụng bừa cho mọi máy.

### 3.3. `<profiles>` và `<activeProfiles>`

Settings profile là cách bật repository hoặc thuộc tính theo môi trường:

```xml
<profiles>
    <profile>
        <id>internal-repo</id>
        <repositories>
            <repository>
                <id>internal-releases</id>
                <url>https://repo.example.invalid/releases</url>
            </repository>
        </repositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>internal-repo</activeProfile>
</activeProfiles>
```

Hai phần này là **đoạn minh họa**, không dùng URL giả trong bài thực hành runnable. Nếu profile không được kích hoạt, các repositories/properties được định nghĩa trong profile đó không đương nhiên có hiệu lực.

Bạn cũng có thể chọn profile bằng `-P profile-id`. Để xem profile đang kích hoạt, có thể dùng Maven Help Plugin. Hãy nhớ rằng **profile trong settings** và **profile trong POM** tham gia các giai đoạn xử lý khác nhau; đừng gộp chúng thành một giả định “settings luôn thắng POM ở mọi trường hợp”.

## 4. Cấu hình được hợp nhất: Maven xử lý hai settings thế nào?

Với mô hình Maven 3 điển hình:

```text
Global settings                     User settings
${maven.home}/conf/settings.xml      ${user.home}/.m2/settings.xml
            \                            /
             \                          /
              +---[Maven settings merge]+
                            |
                            v
                   Effective settings
                            |
                            v
         Artifact resolution / plugins / profiles
```

Tài liệu Maven chính thức nêu rõ: **nếu tồn tại cả global settings và user settings, Maven hợp nhất chúng, user settings là bên được ưu tiên khi có xung đột**.

Đừng hiểu nhầm thao tác này thành “đọc user settings rồi bỏ hoàn toàn global settings”. Những cấu hình chỉ có ở global vẫn có thể tiếp tục xuất hiện ở effective settings, miễn không bị giá trị khác thay thế hoặc bị ảnh hưởng bởi logic merge đặc thù.

### 4.1. Với thuộc tính đơn: user override khi cùng được khai báo

Giả sử global settings có:

```xml
<offline>true</offline>
<interactiveMode>false</interactiveMode>
```

Trong user settings, bạn ghi:

```xml
<offline>false</offline>
```

Kết quả mong đợi trong effective settings:

- `offline=false` vì **user đã override** global.
- `interactiveMode=false` vì user không khai báo giá trị khác nên giá trị global còn hiệu lực.

Nếu global định nghĩa `localRepository` là đường dẫn A và user định nghĩa là B, effective settings sẽ chọn **B**. Nhưng nếu cấu hình user **không tồn tại**, giá trị global hoặc mặc định Maven tiếp tục được dùng.

### 4.2. Với danh sách phần tử: cần xét `id` và quy tắc merge

Các nhóm như `servers`, `mirrors`, `proxies`, `profiles` là **collections**, có những mục phân biệt bằng `id`. Khi hợp nhất, Maven có thể giữ các mục không xung đột từ cả hai cấp, còn mục trùng khóa chịu quy tắc ưu tiên/merge tương ứng với loại phần tử. **Không nên giả định** rằng Maven sẽ lấy tất cả các dòng XML ở user rồi nối nguyên văn phía sau global, hoặc lúc nào cũng thay nguyên cả danh sách chỉ vì user khai báo một mục.

Một ví dụ khái niệm:

- Global định nghĩa server `id=ci-readonly` và server `id=shared-repo`.
- User định nghĩa server `id=shared-repo` để sử dụng credentials riêng.
- Effective settings cần được kiểm tra để biết mục `shared-repo` đang lấy thông tin nào, và `ci-readonly` có còn được giữ lại không.

Trong nhóm có nhiều cấu hình, hãy **dựa vào `help:effective-settings` để đọc kết quả thực tế**, đặc biệt khi mirror/proxy/profile có cùng `id` hoặc thay đổi qua Maven version.

### 4.3. Vì sao thứ tự file trên ổ đĩa chưa đủ?

Kết quả chạy Maven còn có thể chịu tác động của:

- **`-s` / `--settings`:** chọn một user settings file khác thay mặc định.
- **`-gs` / `--global-settings`:** chọn một global settings file khác thay mặc định.
- **`-o` / `--offline`, `-P`:** tùy chọn runtime/profile được truyền vào lệnh.
- **`MAVEN_ARGS` (Maven 3.9+)** hoặc `.mvn/maven.config`: có thể đưa thêm tham số dòng lệnh, tùy môi trường/dự án.
- **Maven Wrapper (`mvnw`)**: có thể dùng một Maven distribution khác với lệnh `mvn` cài trên máy, nên global settings cũng có thể đổi theo.
- **POM và active profiles:** ảnh hưởng repository, plugin và dependency được chọn; kết quả build tổng thể không thể suy ra chỉ từ hai tệp settings.

Vì vậy, **effective settings không đồng nghĩa effective POM**; cần kiểm tra cả cấu hình đang hoạt động và lệnh chạy thực tế khi điều tra lỗi môi trường.

## 5. Thực hành an toàn: hợp nhất hai file không sửa settings thật

Ví dụ này dùng **hai file giả lập global/user** trong một thư mục học tập và chỉ định đường dẫn với `-gs`/`-s`. Nó không yêu cầu chỉnh sửa `conf/settings.xml` trong Maven installation hay `~/.m2/settings.xml` thực tế.

Cần JDK 17+, Maven 3.9.x, terminal và kết nối repository trong lần đầu Maven tải các plugin. Hãy tạo cấu trúc:

```text
settings-lab/
├── global-demo.xml
├── user-demo.xml
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/settingslab/App.java
```

### 5.1. `global-demo.xml` — mô phỏng cấp cài đặt

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>${user.home}/.m2/settings-lab-global-repo</localRepository>
    <offline>true</offline>
    <interactiveMode>false</interactiveMode>
</settings>
```

Đây là XML hoàn chỉnh của một settings file. Giả sử chỉ áp dụng file này, Maven chạy offline, không hỏi người dùng và dùng local repository riêng theo đường dẫn global demo.

### 5.2. `user-demo.xml` — mô phỏng cấp người dùng

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>${user.home}/.m2/settings-lab-user-repo</localRepository>
    <offline>false</offline>
</settings>
```

User settings đặt lại local repository và bật chế độ online. Nó **không khai báo** `interactiveMode`, nên giá trị ở global là phần được giữ lại.

### 5.3. `pom.xml` — project Java 17 độc lập

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>settings-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

POM không chứa URL repository giả, password hoặc các cấu hình đặc thù của máy. Bản thân class Java không cần biết các settings file; Maven dùng chúng để quyết định môi trường build.

### 5.4. `src/main/java/com/example/settingslab/App.java`

```java
package com.example.settingslab;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Maven settings lab OK");
    }
}
```

Đây là một chương trình Java hoàn chỉnh, tương thích JDK 17. Nó chỉ có nhiệm vụ xác nhận artifact đã compile/run được; bản thân nó không hiển thị effective settings.

### 5.5. Hiển thị effective settings theo hai cấp

Mở terminal ở thư mục `settings-lab` (nơi chứa `global-demo.xml`, `user-demo.xml` và `pom.xml`):

```bash
mvn -version
mvn -gs global-demo.xml -s user-demo.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings -DshowPasswords=false
```

Cờ CLI:

- `-gs global-demo.xml`: **chọn global settings file** nằm trong thư mục bài thực hành, thay vì file global mặc định.
- `-s user-demo.xml`: **chọn user settings file** nằm trong thư mục bài thực hành, thay vì user settings mặc định.
- Goal `help:effective-settings`: in cấu hình Maven đã hợp nhất (ở đây gọi bằng tọa độ plugin đầy đủ và version xác định).
- `-DshowPasswords=false`: yêu cầu Help Plugin **không hiển thị mật khẩu**; đây cũng là giá trị mặc định của goal.

Tìm các trường sau trong output effective settings (đường dẫn có thể đã được thay `${user.home}` thành đường dẫn tuyệt đối thực tế):

```xml
<localRepository>.../.m2/settings-lab-user-repo</localRepository>
<offline>false</offline>
<interactiveMode>false</interactiveMode>
```

Ba dòng này là **đoạn minh họa được rút gọn**, không nhất thiết xuất hiện liền nhau và không phải XML đầy đủ. Dấu `...` là ký hiệu giải thích đường dẫn, **không** nhập vào settings thật.

Bạn vừa kiểm tra được:

1. User settings override `localRepository` từ `settings-lab-global-repo` thành `settings-lab-user-repo`.
2. User settings override `offline=true` thành `offline=false`.
3. Global settings vẫn đóng góp `interactiveMode=false` vì user không khai báo mục đó.

**Chú ý khi chạy:** vì user-demo chọn một local repository riêng, lần đầu Maven có thể phải tải Maven Help Plugin/compiler/JAR plugin từ remote vào kho này, dù bạn đã tải ở `~/.m2/repository` trước đó. Đây là hậu quả của việc đổi local repository, **không phải** hiệu ứng của việc hợp nhất `pom.xml`.

### 5.6. Build và chạy chương trình theo effective settings vừa dùng

Tiếp tục trong thư mục `settings-lab`:

```bash
mvn -gs global-demo.xml -s user-demo.xml clean package
java -cp target/classes com.example.settingslab.App
```

Lệnh Maven dùng **cùng hai file settings** như khi kiểm tra effective settings. Khi online và có thể tải plugin, Maven biên dịch `App.java`, tạo `target/classes/com/example/settingslab/App.class` và JAR `target/settings-lab-1.0.0.jar`. Log Maven không cố định giữa các máy.

Stdout **chính xác** của lệnh Java:

```text
Maven settings lab OK
```

Nếu bạn không muốn tạo local repository mới trong thư mục `~/.m2`, có thể dùng đường dẫn demo riêng phù hợp với hệ điều hành. Đừng vô tình đổi hay xóa local repository thật đang được các project khác sử dụng.

### 5.7. Thử thấy ngay tác động của ưu tiên user

Tạm đổi `<offline>false</offline>` trong **user-demo.xml** thành `<offline>true</offline>`, rồi chạy lại goal effective settings. Giá trị hiển thị sẽ đổi thành `offline=true`. Khi offline, Maven chỉ có thể sử dụng những plugin/dependency đã có trong local repository đã chọn; nếu chưa được cache đủ, một số goal có thể fail. Sửa lại `false` sau thí nghiệm.

Tiếp đó, thử xóa **chỉ phần tử `<interactiveMode>false</interactiveMode>`** ở global demo. Effective settings sẽ trở về giá trị mặc định hoặc giá trị đang được áp dụng từ nguồn khác, nếu có. Thử nghiệm này giúp phân biệt **override** với **fallback**.

## 6. Điều gì xảy ra khi có thêm mirror, server và profile ở cả hai cấp?

Tình huống doanh nghiệp thường phức tạp hơn `offline` và `localRepository`:

- Global settings của một image CI có mirror quản lý bởi tổ chức.
- User settings của developer có proxy khi làm việc ở mạng khác.
- Một số server credentials nằm trong user settings hoặc được cung cấp thông qua cơ chế bí mật của CI.
- Các profiles định nghĩa nhiều repository cho các môi trường khác nhau.
- CLI bật/tắt profile bằng `-P`; Maven Wrapper có thể dùng distribution khác.

Do đó, có thể thấy cùng repository chạy được trên máy A, nhưng máy B báo `401`, `403`, `Could not find artifact` hoặc có plugin không tải được.

### 6.1. Ví dụ hai mirror có cùng `id`

Nếu global và user cùng chứa `<mirror><id>company-mirror</id>...` nhưng khai báo URL khác nhau, hãy **đọc effective settings** để xác định cấu hình mirror nào thực sự được chọn. Không nhìn mỗi file global rồi kết luận Maven chắc chắn dùng URL của global. Trong mô hình hợp nhất hai cấp, user settings có ưu tiên khi xung đột, nhưng lựa chọn mirror **còn phụ thuộc `mirrorOf`, thứ tự/logic chọn mirror và các repository đang có**.

Tương tự, các `server` với cùng `id` không đơn giản được “cộng password”; hãy xem mục kết quả và tính hợp lệ của credential theo phiên bản Maven. **Không bao giờ in rõ credential** để “kiểm tra merge” nếu chỉ cần biết ID hay URL.

### 6.2. Profile trong settings là cấu hình môi trường, không thay toàn bộ project

Một profile trong user settings có thể bổ sung repository nội bộ chỉ cho máy có quyền truy cập. Một profile trong global settings có thể áp dụng cho toàn bộ build agents. Nhưng việc profile nào đang active còn phải xét `<activeProfiles>`, điều kiện kích hoạt và CLI `-P`. Dùng:

```bash
mvn help:active-profiles
mvn help:effective-pom
```

để kiểm tra profile đang hiệu lực và POM kết quả **khi dự án load được**. Các lệnh này hỗ trợ giải thích build nhưng không thay thế `help:effective-settings` cho mục đích xem hai file settings đã hợp nhất thế nào.

### 6.3. Đừng đặt secrets trong POM hoặc repo chung

POM là tài sản dự án và thường được commit; password của user/CI thì không. Ngay cả khi sử dụng mã hóa password của Maven, vẫn phải bảo vệ các file liên quan và quyền trên tài khoản build, không chia sẻ token hoặc file đã giải mã.

Maven Help Plugin ẩn password theo mặc định trong `help:effective-settings`. Dù vậy, output vẫn có thể chứa **địa chỉ kho nội bộ, tên tài khoản, đường dẫn home và thông tin hạ tầng**. Không đăng nguyên log, ảnh chụp hoặc effective settings lên issue công khai trước khi lọc dữ liệu nhạy cảm.

## 7. Các lỗi điển hình và quy trình chẩn đoán

| Hiện tượng | Nên kiểm tra |
| --- | --- |
| Đã sửa `~/.m2/settings.xml` nhưng Maven không đổi hành vi | Có dùng `-s`, Maven Wrapper, CI user khác, IDE Maven distribution khác hoặc file chưa lưu không? |
| Không tìm thấy `settings.xml` trong `~/.m2` | File này không bắt buộc phải tồn tại; Maven có thể đang dùng global/defaults |
| Local repository không phải `~/.m2/repository` | Xem effective `localRepository`, CLI/system config hoặc user settings override |
| Build thất bại do “offline” dù có mạng | Kiểm tra effective `offline` và cờ CLI `-o` |
| Build máy A tải được artifact, máy B báo `401/403` | Kiểm tra `servers/id`, repository/mirror ID, credentials, mạng và quyền |
| Maven dùng repository URL khác POM | Kiểm tra `mirrors` và `mirrorOf` trong effective settings |
| Dependency tải được nhưng plugin không tải được | Kiểm tra cả `repositories` và `pluginRepositories`/mirror, không giả định chúng giống nhau |
| `-gs` đã đổi nhưng mirror cũ vẫn xuất hiện | Có thể user settings đang override hoặc cung cấp mirror riêng; xem effective settings |
| Profile trong settings không có tác dụng | Kiểm tra `activeProfiles`, điều kiện activation, `-P` và tên profile |
| Chạy `help:effective-settings` báo không tải được plugin | Help Plugin cũng cần được phân giải từ repository/cache; kiểm tra offline, mirror, proxy và quyền |
| Dùng Maven 4 nhưng kết quả khác ví dụ Maven 3 | Kiểm tra `mvn -version`, project settings/CLI và tài liệu của version đang chạy |

Quy trình tối thiểu:

1. **Xác định môi trường thật:** chạy `mvn -version` hoặc `./mvnw -version`, xác nhận Maven distribution và JDK.
2. **Xác định hai settings được chọn:** có `-s`/`-gs` trong terminal, IDE, CI, `MAVEN_ARGS` hoặc `.mvn/maven.config` không?
3. **Xem effective settings:** dùng `mvn help:effective-settings -DshowPasswords=false` (hoặc dạng gọi plugin đầy đủ như mục 5) và tìm `localRepository`, `offline`, `mirrors`, `servers`, `profiles`.
4. **Xem active profiles/effective POM:** dùng `help:active-profiles` và `help:effective-pom` khi cần hiểu repository/dependency cấu hình của dự án.
5. **Đọc lỗi thật:** `401/403` cần xem auth/quyền, timeout cần xem network/proxy, “not found” cần xem repository/tọa độ, offline cần xem cache/chế độ chạy.
6. **Giữ thay đổi nhỏ và kiểm chứng lại:** thay đúng file/ID có lỗi, chạy lại goal và xác nhận effective settings; không xóa cả `.m2` hoặc bỏ kiểm tra bảo mật chỉ để thử.

### Ghi chú về `-s`, `-gs` và các biến môi trường

- `-s path/to/settings.xml` chỉ chọn **user settings thay thế**, không tự nói rằng global settings biến mất.
- `-gs path/to/global-settings.xml` chỉ chọn **global settings thay thế**, không tự nói rằng user settings bị bỏ qua.
- `-o` (offline) là tùy chọn dòng lệnh; giá trị runtime có thể chịu ảnh hưởng CLI ngoài nội dung XML.
- `MAVEN_OPTS` chủ yếu dùng để truyền tham số khởi chạy JVM của Maven; không đồng nghĩa với XML settings và không trực tiếp là chỗ thay `-s` theo cú pháp JVM. Với Maven 3.9+, `MAVEN_ARGS` là nơi có thể chứa các đối số Maven; cần xem phiên bản đang dùng.
- `${user.home}` và `${env.HOME}` là ví dụ interpolation Maven có thể hỗ trợ trong settings. **Properties khai báo ngay trong settings profile không được sử dụng để nội suy giá trị của chính settings file** theo hướng dẫn chính thức.

## 8. Kết luận và bài tập tự đánh giá

**Tóm lại:** Global settings tạo điểm bắt đầu cho một bản cài Maven; user settings bổ sung hoặc override theo ngữ nghĩa merge, với **user là bên ưu tiên khi xung đột**; effective settings là kết quả cần kiểm tra. POM vẫn chịu trách nhiệm mô tả dự án, và không nên nhét secrets/đường dẫn riêng của developer vào POM.

**Bài tập A — dự đoán rồi kiểm chứng:** với `global-demo.xml` chứa `offline=true`, `interactiveMode=false` và `user-demo.xml` chứa `offline=false`, hãy dự đoán effective settings. Chạy `help:effective-settings` để kiểm chứng từng giá trị.

**Bài tập B — đổi local repository:** thay `localRepository` trong user-demo thành một thư mục khác, chạy lại effective settings và build; quan sát Maven có thể phải tải plugin/artifact lần đầu vì kho local mới rỗng.

**Bài tập C — phân biệt file được chọn:** bỏ `-s` khi gọi Maven và so sánh effective settings. Kết quả sẽ phụ thuộc user settings thật của máy; đừng coi đây là một kết quả cố định cho mọi máy.

**Bài tập D — lý giải vấn đề CI:** một developer có credentials cho `company-mirror` ở user settings, runner không có, cùng POM lại build khác kết quả. Hãy giải thích vì sao đây là vấn đề **môi trường/settings**, không thể giải quyết chỉ bằng việc sửa `groupId` hay `artifactId` trong POM.

**Câu hỏi cuối bài:**

- Hai đường dẫn mặc định của `settings.xml` trong Maven 3 là gì?
- File nào ưu tiên khi global và user cùng khai báo `offline`?
- Vì sao cần `help:effective-settings` thay vì chỉ đọc một file?
- `-s` và `-gs` khác nhau thế nào?
- Settings profile có thể chứa những nhóm cấu hình nào, và điều gì nên nằm trong parent POM?
- Vì sao không nên đưa password lên Git ngay cả khi cấu hình đang hoạt động tốt?
- Khi dùng Maven Wrapper hoặc CI, điều gì khiến global/user settings thực tế khác với terminal cá nhân?

### Tài liệu Maven chính thức

- [Maven Settings Reference — vị trí, cấu trúc và quy tắc hợp nhất](https://maven.apache.org/settings.html)
- [Configuring Maven — các lớp cấu hình và Maven arguments](https://maven.apache.org/configure.html)
- [Guide to Configuring Maven — project, installation, user](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Maven Help Plugin — help:effective-settings và an toàn password](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Introduction to Build Profiles — profile trong POM/settings](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Maven CLI Options Reference — -s và -gs](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html)
