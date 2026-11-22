# `includes`, `excludes` và lựa chọn tài nguyên cần sao chép trong Maven

## 1. Mục tiêu bài học

Một dự án Java không chỉ có mã nguồn `.java`. Ứng dụng còn cần file cấu hình, mẫu văn bản, message bundle, JSON, ảnh, template và các tài nguyên khác. Maven đưa những file phù hợp vào thư mục output để Java và framework có thể đọc chúng từ **classpath**.

Nếu cứ copy tất cả file trong `src/main/resources`, một bản phát hành có thể chứa file nháp, fixture, cấu hình nội bộ hoặc tài nguyên nhạy cảm. Nếu chọn quá hẹp, chương trình có thể không tìm được file cần thiết. Hai cơ chế quan trọng để cân bằng là:

- **`includes`:** chỉ ra những file hoặc nhóm đường dẫn muốn copy.
- **`excludes`:** chỉ ra những file hoặc nhóm đường dẫn phải loại khỏi tập đang xét.

Bài học thuộc nhóm **Tài nguyên và sinh mã**. Sau khi học, bạn có thể:

1. Phân biệt `src/main/resources`, `src/test/resources`, `target/classes` và `target/test-classes`.
2. Viết pattern `include`/`exclude` kiểu Ant tương đối với resource directory.
3. Hiểu trường hợp một file khớp cả include và exclude; nhận diện việc nhiều resource entries cùng chọn một file.
4. Kết hợp selection với `filtering` để xử lý file text mà không làm hỏng nhị phân.
5. Viết POM đầy đủ và chạy ứng dụng Java 17 đọc tài nguyên từ JAR.
6. Kiểm tra file được copy, file bị loại, kết quả filtering và test resource.
7. Dùng clean build và kiểm tra artifact để tránh tài nguyên cũ lọt vào bản phát hành.

Các ví dụ sử dụng Maven 3.x, JDK 17 và Maven Resources Plugin được ghim phiên bản. Chúng tập trung vào cơ chế chứ không ngụ ý phiên bản plugin nêu trong bài là bản mới nhất.

## 2. Đường đi của resource trong Maven

Cấu trúc thông dụng:

~~~text
project/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/             # Java source
    │   └── resources/        # Main resources
    └── test/
        ├── java/             # Test source
        └── resources/        # Test resources
~~~

Với packaging `jar` thông thường:

| Thư mục đầu vào | Đầu ra | Vai trò |
| --- | --- | --- |
| `src/main/java` | `target/classes` | Mã bytecode `.class` của ứng dụng. |
| `src/main/resources` | `target/classes` | Tài nguyên dùng bởi ứng dụng và thường được đóng gói vào JAR. |
| `src/test/java` | `target/test-classes` | Lớp kiểm thử. |
| `src/test/resources` | `target/test-classes` | Fixture/config cho test; không tự nằm trong JAR ứng dụng chính. |

Ví dụ file:

~~~text
src/main/resources/config/app.properties
~~~

sẽ được đặt dưới:

~~~text
target/classes/config/app.properties
~~~

và trong JAR chính dưới entry:

~~~text
config/app.properties
~~~

Nếu không đổi đường đích, Java đọc bằng đường dẫn classpath `/config/app.properties`. Maven **không giữ tiền tố `src/main/resources`** bên trong JAR.

### Các phase và goal liên quan

| Lệnh | Ý nghĩa |
| --- | --- |
| `mvn process-resources` | Chạy lifecycle tới phase xử lý main resources. |
| `mvn resources:resources` | Gọi trực tiếp goal copy main resources. |
| `mvn process-test-resources` | Chạy lifecycle tới phase xử lý test resources; các phase trước cũng được thực hiện. |
| `mvn resources:testResources` | Gọi trực tiếp goal xử lý test resources. |
| `mvn package` | Chạy các phase cần thiết rồi đóng gói artifact theo packaging. |

`resources:resources` không tự biên dịch Java; `mvn package` không chỉ copy tài nguyên. Những plugin khác có thể can thiệp vào lifecycle, nên khi kiểm tra dự án thật phải xem POM hiệu lực và log build.

## 3. `includes`: tập file được phép chọn

Ví dụ một resource entry trong `<build><resources>`:

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <includes>
        <include>**/*.properties</include>
        <include>**/*.xml</include>
    </includes>
</resource>
~~~

Resource entry này chỉ chọn file `.properties` hoặc `.xml` bên dưới `src/main/resources`, gồm các thư mục con. File `messages/welcome.txt` không được entry đó copy.

**Quan trọng:** include pattern được so khớp **tương đối với `<directory>`**, không phải tương đối với tên repository hay toàn đường dẫn từ root dự án.

Ví dụ:

~~~xml
<directory>src/main/resources</directory>
<includes>
    <include>config/**/*.properties</include>
</includes>
~~~

sẽ xem xét:

~~~text
src/main/resources/config/app.properties
src/main/resources/config/env/prod.properties
~~~

Trong `<include>`, chỉ viết `config/**/*.properties`. Nếu viết lại cả `src/main/resources/config/**/*.properties`, phần tiền tố bị lặp khi so đường dẫn và pattern có thể không khớp file nào.

### Pattern kiểu Ant, không phải regex

| Pattern | Tác dụng | Ví dụ khớp |
| --- | --- | --- |
| `**/*` | File ở root hoặc các cấp con. | `logo.png`, `config/app.properties`. |
| `**/*.properties` | Tất cả file `.properties` dưới resource root. | `app.properties`, `config/db.properties`. |
| `config/**/*.properties` | Properties thuộc cây `config`. | `config/app.properties`, `config/prod/app.properties`. |
| `messages/**/*.txt` | File text dưới cây `messages`. | `messages/welcome.txt`. |
| `assets/**/*.png` | Ảnh PNG thuộc cây `assets`. | `assets/logo.png`. |
| `**/private/**` | Nội dung trong thư mục `private` ở các cấp. | `config/private/password.properties`. |
| `**/*.draft.txt` | File có hậu tố `.draft.txt`. | `messages/internal.draft.txt`. |

`*` khớp một phần tên trong một thành phần đường dẫn; `?` thường khớp một ký tự; `**` khớp nhiều cấp thư mục, kể cả không có cấp trung gian theo ngữ nghĩa Ant-style. Đây là **glob**, không phải biểu thức chính quy. Đừng dùng cú pháp regex kiểu `.*\\.properties$`.

Dùng dấu `/` trong POM để viết pattern di động trên Windows và Linux. Tên file trên hệ thống phân biệt chữ hoa/thường có thể cho kết quả khác hệ thống không phân biệt; vì vậy cần thống nhất chính tả tên tài nguyên.

### Không có includes thì sao?

Trong cấu hình resource thông thường, nếu không khai báo danh sách includes, Maven xét các file trong directory theo quy tắc mặc định, sau đó loại theo excludes và default excludes của scanner. Điều này có nghĩa **một entry không có includes có thể copy rộng hơn dự định**.

Nếu mục tiêu chỉ đóng gói một số loại file, hãy định nghĩa allowlist rõ ràng thay vì phụ thuộc vào việc file “hiện chưa tồn tại” trong thư mục nguồn.

## 4. `excludes`: loại file dù nó khớp includes

Ví dụ:

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <includes>
        <include>config/**/*.properties</include>
    </includes>
    <excludes>
        <exclude>**/private/**</exclude>
        <exclude>**/*.secret.properties</exclude>
    </excludes>
</resource>
~~~

Bảng kết quả:

| File tương đối với `src/main/resources` | Khớp include? | Khớp exclude? | Copy? |
| --- | :---: | :---: | :---: |
| `config/app.properties` | Có | Không | **Có** |
| `config/env/dev.properties` | Có | Không | **Có** |
| `config/private/credential.properties` | Có | Có | **Không** |
| `config/password.secret.properties` | Có | Có | **Không** |
| `docs/app.properties` | Không | Không | **Không** |
| `config/readme.txt` | Không | Không | **Không** |

Một file phải khớp **ít nhất một include**, nhưng chỉ cần khớp **một exclude** trong cùng resource entry là bị loại. Exclude có hiệu lực cao hơn include trong entry đó, không phụ thuộc thứ tự ghi chúng trong XML.

Đây là quy tắc:

~~~text
File nằm dưới resource directory?
          │
          ▼
Khớp ít nhất một include nếu includes được khai báo?
          ├── Không → bỏ
          └── Có
                 │
                 ▼
         Khớp bất kỳ exclude nào?
                 ├── Có → bỏ
                 └── Không → được chọn để copy
~~~

### Chỉ dùng excludes

Có thể viết:

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <excludes>
        <exclude>**/private/**</exclude>
        <exclude>**/*.tmp</exclude>
    </excludes>
</resource>
~~~

Cấu hình này có nghĩa rộng: copy những file không bị loại theo excludes và scanner defaults. Nếu có `docs/internal.md`, file đó vẫn có thể được copy. Để bảo đảm chỉ đưa các loại được phép vào JAR, hãy cân nhắc kết hợp **includes + excludes**.

## 5. Nhiều resource entries và vấn đề chồng lấn

Bạn có thể khai báo nhiều `<resource>` trong `<resources>`. Mỗi entry có `<directory>`, `<includes>`, `<excludes>`, `<filtering>` và `<targetPath>` riêng.

Ví dụ:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>config/**/*.properties</include>
        </includes>
        <excludes>
            <exclude>**/private/**</exclude>
        </excludes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <includes>
            <include>messages/**/*.txt</include>
            <include>data/**/*.json</include>
        </includes>
        <excludes>
            <exclude>**/*.draft.txt</exclude>
        </excludes>
    </resource>
</resources>
~~~

Ý nghĩa:

- Entry 1 chọn config properties và **filter nội dung**.
- Entry 2 chọn message text và JSON nhưng **copy nguyên văn**.
- Hai tập include không trùng nên tránh việc cùng file bị xử lý hai lần.

**Bẫy quan trọng nhất:** exclude trong entry 2 **không áp dụng cho entry 1**. Nếu entry 1 có `<include>**/*</include>`, file bị exclude bởi entry 2 có thể vẫn được copy qua entry 1. Một danh sách `<excludes>` không phải “lệnh cấm toàn cục” của cả build.

Do đó cần:

1. Kiểm tra **tất cả** resource entries, kể cả từ parent và profiles.
2. Ưu tiên các tập includes không chồng lấn.
3. Nếu phải chồng lấn, xác nhận excludes trên mọi entry liên quan.
4. Tránh hai entries cùng ghi vào một output path; có nguy cơ ghi đè và kết quả khó tái hiện.
5. Kiểm tra artifact cuối cùng, không chỉ đọc POM.

### Vì sao không nên dựa vào thứ tự ghi đè?

Nếu hai resource entries cùng chọn `config/app.properties` nhưng một entry filtered và entry khác unfiltered, chúng có thể nhắm tới cùng `target/classes/config/app.properties`. Kết quả phụ thuộc cách plugin xử lý copy/overwrite và trạng thái lần build. Không nên coi “entry cuối chắc chắn thắng” là hợp đồng dùng để quyết định nội dung JAR; thiết kế entry rõ ràng sẽ an toàn hơn.

## 6. `filtering` khác includes/excludes

Selection quyết định **file nào** được copy; filtering quyết định **nội dung có bị biến đổi hay không**.

File `src/main/resources/config/app.properties`:

~~~properties
app.name=@project.artifactId@
app.environment=@app.environment@
app.version=@project.version@
~~~

Nếu resource entry có:

~~~xml
<filtering>true</filtering>
~~~

Maven Resources Plugin hỗ trợ placeholder dạng `@...@` và `${...}`, lấy giá trị từ POM/Maven properties, filter files và CLI theo cơ chế plugin. Sau build, file có thể thành:

~~~properties
app.name=resource-selection-demo
app.environment=dev
app.version=1.0-SNAPSHOT
~~~

Ngược lại, nếu `<filtering>false</filtering>`, nội dung placeholder thường được copy nguyên trạng.

### Cẩn trọng với file nhị phân

Không filter PNG/JPEG/PDF/ZIP/font hoặc file nhị phân khác: thay thế byte có thể làm chúng hỏng. Apache Maven khuyến nghị tách nhóm tài nguyên cần filter và nhóm không filter; tùy plugin version còn có cấu hình `nonFilteredFileExtensions`, nhưng việc thiết kế resource entries riêng giúp thấy rõ phạm vi.

Không dùng Maven filtering để chèn mật khẩu, API token hoặc secret thật vào file được đóng gói: bất kỳ ai nhận JAR có thể giải nén file. Hãy cấp secret ở runtime theo hệ thống triển khai và kiểm tra artifact trước khi phát hành.

## 7. Dự án Java 17 hoàn chỉnh

Tạo project `resource-selection-demo` có cả resource cần giữ và file cần loại. Ví dụ này dùng Maven 3.x, JDK 17 và các plugin được chỉ định rõ phiên bản.

### 7.1. Cấu trúc thư mục

~~~text
resource-selection-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/App.java
    │   └── resources/
    │       ├── config/
    │       │   ├── app.properties
    │       │   ├── extra.yml
    │       │   └── private/
    │       │       └── credential.properties
    │       ├── messages/
    │       │   ├── welcome.txt
    │       │   └── internal.draft.txt
    │       ├── data/
    │       │   ├── example.json
    │       │   └── notes.csv
    │       └── docs/
    │           └── internal.md
    └── test/
        └── resources/
            └── fixtures/
                ├── sample.json
                ├── debug-request.json
                └── notes.txt
~~~

File `credential.properties` trong bài chỉ chứa dữ liệu **giả**. Trong dự án thật, credential nên được quản lý ngoài repository/source/resources thay vì trông đợi mỗi excludes đủ bảo mật.

### 7.2. POM hoàn chỉnh

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>resource-selection-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <app.environment>dev</app.environment>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>config/**/*.properties</include>
                </includes>
                <excludes>
                    <exclude>**/private/**</exclude>
                </excludes>
            </resource>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
                <includes>
                    <include>messages/**/*.txt</include>
                    <include>data/**/*.json</include>
                </includes>
                <excludes>
                    <exclude>**/*.draft.txt</exclude>
                </excludes>
            </resource>
        </resources>

        <testResources>
            <testResource>
                <directory>src/test/resources</directory>
                <filtering>false</filtering>
                <includes>
                    <include>fixtures/**/*.json</include>
                </includes>
                <excludes>
                    <exclude>fixtures/**/debug*.json</exclude>
                </excludes>
            </testResource>
        </testResources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>production</id>
            <properties>
                <app.environment>prod</app.environment>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Trong POM này:

- Resource entry 1 chọn `config/**/*.properties`, **bật filtering**, loại `**/private/**`.
- Resource entry 2 chọn `messages/**/*.txt` và `data/**/*.json`, **không filtering**, loại `**/*.draft.txt`.
- `<testResources>` chỉ chọn `fixtures/**/*.json`, loại `fixtures/**/debug*.json`.
- `project.build.sourceEncoding` và Resources Plugin encoding bảo đảm việc lọc text ví dụ được xử lý theo UTF-8.
- Compiler Plugin dùng Java release 17; JAR Plugin tạo artifact JAR thường.
- Profile `production` đổi `app.environment` thành `prod`.
- Chỉ những resource entries được khai báo mới được dùng cho bộ main resources này; **không tự thêm một entry “copy everything”** do project đã có `<resources>` tường minh.

### 7.3. Nội dung các file main resources

Tạo `src/main/resources/config/app.properties`:

~~~properties
app.name=@project.artifactId@
app.environment=@app.environment@
app.version=@project.version@
~~~

Tạo `src/main/resources/config/extra.yml`:

~~~yaml
feature:
  enabled: true
~~~

Tạo `src/main/resources/config/private/credential.properties`:

~~~properties
demo.credential=NOT_A_REAL_SECRET
~~~

Tạo `src/main/resources/messages/welcome.txt`:

~~~text
Welcome to Maven resources!
~~~

Tạo `src/main/resources/messages/internal.draft.txt`:

~~~text
DRAFT - not for release.
~~~

Tạo `src/main/resources/data/example.json`:

~~~json
{
  "kind": "example",
  "enabled": true
}
~~~

Tạo `src/main/resources/data/notes.csv`:

~~~text
name,flag
sample,true
~~~

Tạo `src/main/resources/docs/internal.md`:

~~~markdown
# Internal notes

Not selected for the JAR.
~~~

**Không tạo credential thật** để thử exclude; hãy dùng đúng dữ liệu giả ở trên.

### 7.4. Nội dung test resources

Tạo `src/test/resources/fixtures/sample.json`:

~~~json
{
  "case": "success",
  "id": 1
}
~~~

Tạo `src/test/resources/fixtures/debug-request.json`:

~~~json
{
  "case": "debug"
}
~~~

Tạo `src/test/resources/fixtures/notes.txt`:

~~~text
Test-only notes.
~~~

Kết quả mong đợi:

- `fixtures/sample.json` được copy vì khớp include và không bị exclude.
- `fixtures/debug-request.json` không được copy vì khớp exclude `fixtures/**/debug*.json`.
- `fixtures/notes.txt` không được copy vì không khớp include `.json`.
- Test resources được đặt ở `target/test-classes`, không tự nằm trong JAR chính.

### 7.5. Java 17 đọc tài nguyên từ classpath

Tạo `src/main/java/com/example/App.java`:

~~~java
package com.example;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    private static InputStream open(String resource) {
        InputStream stream = App.class.getResourceAsStream(resource);
        if (stream == null) {
            throw new IllegalStateException(
                    "Missing classpath resource: " + resource);
        }
        return stream;
    }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();
        try (InputStream stream = open("/config/app.properties");
             InputStreamReader reader = new InputStreamReader(
                     stream, StandardCharsets.UTF_8)) {
            config.load(reader);
        }

        String message;
        try (InputStream stream = open("/messages/welcome.txt");
             BufferedReader reader = new BufferedReader(
                     new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            message = reader.readLine();
        }

        if (message == null) {
            throw new IllegalStateException("Empty message");
        }

        System.out.println("Artifact: " + config.getProperty("app.name"));
        System.out.println("Environment: "
                + config.getProperty("app.environment"));
        System.out.println("Version: "
                + config.getProperty("app.version"));
        System.out.println("Message: " + message);
        System.out.println("Private present: "
                + (App.class.getResource(
                        "/config/private/credential.properties") != null));
        System.out.println("Draft present: "
                + (App.class.getResource(
                        "/messages/internal.draft.txt") != null));
    }
}
~~~

Java code không dùng dependency bên ngoài JDK. `getResourceAsStream` đọc tài nguyên classpath và sẽ báo lỗi rõ nếu resource bắt buộc bị bỏ sót. `Properties.load(Reader)` sử dụng reader UTF-8, giúp tránh nhầm về encoding của bản Properties nạp qua InputStream.

`getResource(... ) != null` là phép kiểm tra file có nhìn thấy trên classpath hay không; trong demo chỉ chạy JAR này, nó giúp kiểm tra hai file bị loại. Trong một ứng dụng có nhiều JAR, có thể có resource cùng đường dẫn ở dependency khác, nên không dùng kết quả này để chứng minh file thuộc riêng JAR nào.

## 8. Build và kết quả cần xác minh

Đứng tại thư mục chứa `pom.xml`:

~~~bash
mvn --version
java -version
mvn clean package
~~~

**`clean` rất quan trọng:** nếu trước đó đã copy một resource rồi mới thay excludes, file cũ có thể vẫn tồn tại dưới `target/classes` sau một lần chạy không clean. Clean build giúp đánh giá chính sách selection hiện tại thay vì dữ liệu sót.

Sau build thành công, cây output rút gọn:

~~~text
target/
├── classes/
│   ├── com/example/App.class
│   ├── config/app.properties
│   ├── messages/welcome.txt
│   └── data/example.json
├── test-classes/
│   └── fixtures/sample.json
└── resource-selection-demo-1.0-SNAPSHOT.jar
~~~

Các file `config/private/credential.properties`, `messages/internal.draft.txt`, `config/extra.yml`, `data/notes.csv` và `docs/internal.md` không được chọn cho main output.

### 8.1. Chạy chương trình từ JAR

~~~bash
java -cp target/resource-selection-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác khi build mặc định và không có override properties:**

~~~text
Artifact: resource-selection-demo
Environment: dev
Version: 1.0-SNAPSHOT
Message: Welcome to Maven resources!
Private present: false
Draft present: false
~~~

POM không khai báo `Main-Class` trong JAR manifest; do đó ví dụ chạy bằng `-cp` cộng với tên class, không giả định `java -jar` hoạt động.

### 8.2. Kiểm tra các entry của JAR

~~~bash
jar tf target/resource-selection-demo-1.0-SNAPSHOT.jar
~~~

Các entry quan trọng **phải có**:

~~~text
com/example/App.class
config/app.properties
messages/welcome.txt
data/example.json
~~~

Các đường dẫn **không nên có**:

~~~text
config/private/credential.properties
messages/internal.draft.txt
config/extra.yml
data/notes.csv
docs/internal.md
fixtures/sample.json
~~~

`jar tf` chỉ liệt kê tên file. Để xác nhận filtering, hãy xem nội dung `target/classes/config/app.properties`; nó dự kiến là:

~~~properties
app.name=resource-selection-demo
app.environment=dev
app.version=1.0-SNAPSHOT
~~~

Test fixture `fixtures/sample.json` nằm dưới `target/test-classes`, nhưng JAR chính đóng gói `target/classes`, không tự lấy test resources.

### 8.3. Đổi profile production

Chạy:

~~~bash
mvn -Pproduction clean package
java -cp target/resource-selection-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác:**

~~~text
Artifact: resource-selection-demo
Environment: prod
Version: 1.0-SNAPSHOT
Message: Welcome to Maven resources!
Private present: false
Draft present: false
~~~

Profile `production` chỉ thay property được lọc **lúc Maven build**. Nó không tự khiến Java runtime đọc một biến môi trường `prod` sau đó. Nội dung file trong JAR được quyết định ở lần build.

### 8.4. Maven user property từ `-D`

Chạy:

~~~bash
mvn -Dapp.environment=qa clean package
java -cp target/resource-selection-demo-1.0-SNAPSHOT.jar com.example.App
~~~

Với POM mẫu, CLI user property được Resources Plugin sử dụng để thay `@app.environment@` thành `qa`. Stdout dự kiến:

~~~text
Artifact: resource-selection-demo
Environment: qa
Version: 1.0-SNAPSHOT
Message: Welcome to Maven resources!
Private present: false
Draft present: false
~~~

Đừng nhầm `mvn -Dapp.environment=qa` với `java -Dapp.environment=qa`. Lệnh Maven đổi **dữ liệu đầu vào lúc build**, còn Java launcher đặt JVM system property cho tiến trình runtime. Class `App` trong ví dụ không đọc system property để override resource đã lọc.

## 9. `testResources`: cùng pattern nhưng đầu ra khác

`<resources>` và `<testResources>` phục vụ hai nhóm khác nhau:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
        </resource>
    </resources>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
        </testResource>
    </testResources>
</build>
~~~

Đây là **mảnh XML minh họa**, không cần chèn thêm vào POM runnable. POM ở mục 7 đã khai báo testResources có includes/excludes cụ thể.

Các lệnh hữu ích:

~~~bash
mvn clean process-resources
mvn process-test-resources
~~~

Lệnh đầu xử lý main resources. Lệnh thứ hai chạy default lifecycle đến phase process-test-resources và xử lý test resources. Nếu chỉ muốn gọi goal trực tiếp, Maven có `resources:testResources`, nhưng gọi goal trực tiếp không tương đương chạy toàn bộ lifecycle.

**Không đưa fixture vào main resources** chỉ vì code test cần đọc nó. Khi chạy unit tests, Maven thường đưa `target/test-classes` lên test classpath. Khi phát hành JAR chính, nội dung này thường không được đóng gói trừ khi bạn cấu hình thêm test-jar hoặc plugin đặc biệt.

## 10. `targetPath`: quyết định đặt file ở đâu

Nếu một file nguồn:

~~~text
src/main/resources/config/app.properties
~~~

được chọn theo cấu hình thông thường, nó ra:

~~~text
target/classes/config/app.properties
~~~

Có thể thay vị trí tương đối trong output bằng `<targetPath>`:

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <targetPath>defaults</targetPath>
    <includes>
        <include>config/**/*.properties</include>
    </includes>
</resource>
~~~

Khi đó output có thể là:

~~~text
target/classes/defaults/config/app.properties
~~~

Đường dẫn Java phải đổi sang `/defaults/config/app.properties` nếu muốn đọc file mới. Đây là ví dụ riêng, **không phải thay đổi trong POM runnable**.

Phân biệt các thuộc tính:

| Thuộc tính | Trả lời câu hỏi |
| --- | --- |
| `directory` | Tài nguyên lấy từ thư mục nào? |
| `includes` | File nào được xem xét? |
| `excludes` | File nào bị loại khỏi entry này? |
| `filtering` | Nội dung có được thay placeholder không? |
| `targetPath` | Bản sao được đặt vào thư mục con nào của output? |
| `outputDirectory` của goal | Root của output, thường là `target/classes` hoặc `target/test-classes`. |

## 11. Tài nguyên sinh mã và thư mục bổ sung

Trong dự án có bước sinh file, tài nguyên có thể được tạo ở `generate-resources` hoặc một phase khác. Bạn có thể khai báo một thư mục riêng:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <includes>
            <include>**/*.txt</include>
        </includes>
    </resource>
    <resource>
        <directory>src/generated-resources</directory>
        <filtering>false</filtering>
        <includes>
            <include>**/*.json</include>
        </includes>
    </resource>
</resources>
~~~

Đây là mảnh cấu hình minh họa; nếu thư mục `src/generated-resources` không có hoặc được tạo **sau** `process-resources`, những file dự kiến sẽ không được copy. Với plugin sinh mã, phải xác định đúng phase, output directory và resource root được đăng ký.

### `resources:copy-resources` không phải copy mặc định

Maven Resources Plugin có goal `copy-resources` để copy file tới một nơi tùy ý. Ví dụ một execution minh họa:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>copy-extra</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>copy-resources</goal>
            </goals>
            <configuration>
                <outputDirectory>${project.build.directory}/extra</outputDirectory>
                <resources>
                    <resource>
                        <directory>src/extra-resources</directory>
                        <filtering>false</filtering>
                        <includes>
                            <include>**/*.txt</include>
                        </includes>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Cần đặt fragment này trong `<build><plugins>` và có thư mục `src/extra-resources` thực sự nếu muốn thử. Nó copy tới `target/extra`, **không tự khiến file xuất hiện trong JAR hoặc Java runtime classpath**. Muốn đóng gói output bổ sung, cần cấu hình packaging/resource path tương ứng.

## 12. Default excludes của scanner và file ẩn

Ngoài excludes do bạn khai báo, Maven Resources Plugin có thể sử dụng các **default excludes** của scanner, thường nhằm tránh copy các file VCS metadata, backup hoặc file tạm. Ví dụ các thư mục `.git`, `.svn` và một số file dạng editor backups thường không nên nằm trong artifact.

Với plugin 3.x, tham số `addDefaultExcludes` có thể điều khiển việc áp dụng danh sách này. Không nên tắt nó một cách tùy tiện chỉ để copy một dotfile, vì có thể đưa metadata hoặc file không mong muốn vào sản phẩm.

Quan trọng: **không suy luận mọi dotfile đều bị loại hoặc mọi file không khớp default excludes đều an toàn**. File chứa secret vẫn có thể được copy nếu pattern/entry cho phép. Cần allowlist và kiểm tra artifact để bảo đảm chính sách phát hành.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `getResourceAsStream("/config/app.properties")` trả về `null`. | Không được chọn, sai path/case, sai `targetPath` hoặc thiếu JAR trên classpath. | Kiểm tra `target/classes`, `jar tf`, POM và lệnh Java. |
| File draft vẫn có sau khi thêm exclude. | File cũ trong `target/classes` hoặc một entry khác vẫn copy. | Chạy `mvn clean package`, kiểm tra mọi resource entries. |
| File `config/extra.yml` bị bỏ sót. | Includes chỉ chọn `config/**/*.properties`. | Thêm include `config/**/*.yml` nếu ứng dụng cần. |
| File trong thư mục `private` vẫn được copy. | Exclude nằm ở entry khác hoặc bị một entry rộng chọn lại. | Loại khỏi mọi entry có khả năng chọn nó; kiểm tra JAR. |
| File `messages/welcome.txt` không xuất hiện. | Không có include cho messages hoặc directory sai. | Thêm entry unfiltered đúng thư mục/pattern. |
| Placeholder còn nguyên trong file output. | Filtering false, property thiếu hoặc file bị một entry unfiltered xử lý. | Kiểm tra `filtering`, placeholder, active profile và output. |
| Ảnh, PDF hoặc ZIP hỏng sau build. | Đã filtering nội dung nhị phân. | Tách unfiltered resource entry. |
| Test fixture xuất hiện trong JAR chính. | Cấu hình copy fixture vào main resources hoặc plugin đóng gói đặc biệt. | Tách `testResources` và rà soát packaging. |
| File có trong `target/extra` nhưng Java không đọc được. | Extra folder không nằm trên classpath. | Cấu hình resource output/packaging đúng mục đích. |
| Pattern chạy trên Windows nhưng không khớp Linux. | Sai tên hoa/thường hoặc cách biểu diễn path. | Chuẩn hóa file names và dùng `/`. |
| Resource mới xuất hiện ngoài ý muốn. | Không có includes hoặc wildcard quá rộng. | Dùng allowlist và kiểm tra JAR trong CI. |
| `resources:resources` chạy mà test fixture không đổi. | Goal đó chỉ xử lý main resources. | Dùng `process-test-resources` hoặc `resources:testResources`. |
| Một file output có nội dung lạ. | Nhiều entries trùng destination hoặc plugin khác ghi đè. | Kiểm tra mọi nguồn, executions và tránh chồng lấn. |

### Lỗi đặc biệt: build không clean

Ví dụ sau khi thay POM để exclude `messages/internal.draft.txt`, bạn chỉ chạy:

~~~bash
mvn resources:resources
~~~

File cũ **có thể** còn ở `target/classes` từ lần build trước. Đây không nhất thiết là include/exclude sai; goal copy không phải công cụ dọn toàn bộ output cũ. Dùng:

~~~bash
mvn clean package
~~~

để kiểm chứng lại sau khi thay chính sách resources. Nếu hệ thống production đang chứa secret trong JAR cũ, cần cả việc thu hồi/xử lý artifact, không chỉ sửa bản build mới.

## 14. Kiểm tra bằng Maven trước khi phát hành

### 14.1. Xem POM hiệu lực

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Tìm `<resources>`, `<testResources>`, `<includes>`, `<excludes>`, `<filtering>` và phiên bản Resources Plugin. Parent POM hoặc active profiles có thể tác động cấu hình; file POM hiện tại không nhất thiết là toàn bộ model Maven đang sử dụng.

### 14.2. Thu hẹp vào phase resources

~~~bash
mvn clean process-resources
~~~

Sau đó kiểm tra `target/classes`. Với test resources, chạy `mvn process-test-resources` và xem `target/test-classes`.

### 14.3. Xem tham số Resources Plugin

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-resources-plugin:3.3.1 -Dgoal=resources -Ddetail=true
~~~

Đây là goal của Help Plugin để **mô tả** Resources Plugin, không trực tiếp copy file. Nó giúp xem tham số như `resources`, `outputDirectory`, `encoding` và `addDefaultExcludes` ở phiên bản tương ứng.

### 14.4. Kiểm tra debug log khi cần

~~~bash
mvn -X process-resources
~~~

Debug log có thể có thông tin về resource scanning và plugin configuration. Cách log chi tiết phụ thuộc phiên bản, không có định dạng ổn định để parse cứng. Hãy che đường dẫn, thông tin mạng nội bộ và properties nhạy cảm trước khi chia sẻ.

### 14.5. Kiểm tra artifact cuối

~~~bash
mvn clean package
jar tf target/resource-selection-demo-1.0-SNAPSHOT.jar
~~~

Đây là kiểm chứng **sản phẩm phát hành**. Kết hợp với việc đọc `target/classes/config/app.properties` hoặc chạy chương trình mẫu để biết nội dung đã được lọc đúng.

Ba tầng kiểm tra:

~~~text
Effective POM       → các resource entries và patterns được cấu hình?
target/classes      → những file nào thực tế được copy?
JAR/runtime         → những file nào có trong artifact và Java đọc được?
~~~

## 15. Checklist lựa chọn tài nguyên an toàn

- [ ] `<directory>` trỏ đúng thư mục hiện hữu, đúng module/POM.
- [ ] Patterns tương đối so với resource directory, không lặp `src/main/resources`.
- [ ] Includes có phạm vi đủ để chứa mọi file cần chạy, không chọn tràn lan.
- [ ] Excludes áp dụng trong **mọi resource entry** có thể chọn file nhạy cảm.
- [ ] Không có các entries chồng lấn và ghi đè cùng đường dẫn đích ngoài ý muốn.
- [ ] Text có placeholder được filtering với encoding phù hợp.
- [ ] Ảnh và file nhị phân được copy unfiltered.
- [ ] File nháp, file nội bộ, secret, backup và debug fixture không lọt vào JAR.
- [ ] Test resources được copy vào test output, không nằm trong JAR chính.
- [ ] Nếu dùng `targetPath`, đường dẫn runtime classpath đã điều chỉnh.
- [ ] Sau thay đổi config, đã chạy `mvn clean package` và kiểm tra JAR thật.
- [ ] CI có thể xác nhận các resource bắt buộc, nhất là config/template/i18n/service descriptors.

**Chú ý:** excludes là một phần của chính sách đóng gói, không phải ranh giới bảo mật tuyệt đối. Một plugin khác, một resource entry khác hoặc một bước upload khác vẫn có thể làm rò rỉ file nếu pipeline không được kiểm soát.

## 16. Bài tập tự đánh giá

### Bài A — Dự đoán kết quả

Với:

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <includes>
        <include>config/**/*.properties</include>
        <include>messages/**/*.txt</include>
    </includes>
    <excludes>
        <exclude>**/private/**</exclude>
        <exclude>**/*.draft.txt</exclude>
    </excludes>
</resource>
~~~

Những file nào được copy?

1. `config/app.properties`
2. `config/private/credential.properties`
3. `messages/welcome.txt`
4. `messages/internal.draft.txt`
5. `docs/readme.md`
6. `config/env/staging.properties`
7. `assets/logo.png`

**Đáp án:** copy (1), (3) và (6). File (2), (4) bị exclude; file (5), (7) không khớp includes. Nếu có resource entries khác, cần xét thêm chúng.

### Bài B — Thực hành Java 17

1. Tạo POM, Java class và các file ở mục 7.
2. Chạy `mvn clean package`, kiểm tra `target/classes` và `target/test-classes`.
3. Chạy Java từ JAR, xác nhận sáu dòng stdout.
4. Chạy `jar tf` và chỉ ra bốn entry phải có trong JAR.
5. Xem file `target/classes/config/app.properties`, phân biệt bản được filter và bản nguồn.
6. Build lại bằng `-Pproduction`; giải thích vì sao Environment thay thành `prod`.
7. Build bằng `-Dapp.environment=qa`; so với profile production.
8. Thêm file `docs/new.md`; dự đoán nó có được copy không.
9. Giải thích tại sao `fixtures/sample.json` có trong test output nhưng không ở JAR chính.
10. Thêm một resource entry `<filtering>false</filtering>` cho `assets/**/*.png` nếu dự án có hình ảnh.

### Bài C — Điều tra lỗi production

Sau khi exclude một file cấu hình nháp, nhóm chạy `mvn package` nhưng file vẫn xuất hiện trong JAR. Hãy kiểm tra theo thứ tự: file cũ trong `target/classes`, resource entries chồng lấn, parent POM/profile, plugin khác copy file, và JAR đang được inspect có đúng artifact vừa build không. Cuối cùng chạy clean build, kiểm tra `jar tf` và quy trình phát hành.

## 17. Kết luận

**`includes` quyết định file nào được phép copy; `excludes` loại file khỏi một resource entry; `filtering` biến đổi nội dung; `targetPath` quyết định vị trí tương đối trong output.** Patterns được so khớp từ `<directory>` của từng entry, vì thế excludes của entry này không tự bảo vệ entry khác.

Đường đi điển hình:

~~~text
src/main/resources
      │ selection + filtering
      ▼
target/classes
      │ package
      ▼
JAR chính
      │ classpath
      ▼
App.class.getResourceAsStream("/config/app.properties")
~~~

Test resources đi riêng qua `target/test-classes`. Để bảo đảm một bản phát hành vừa đủ tài nguyên cần thiết vừa không lẫn file ngoài ý muốn, hãy kết hợp allowlist, exclusions, unfiltered binary resources, clean build và kiểm tra **artifact thực tế**.

## Tài liệu chính thức

- Maven Resources Plugin — Including and excluding files and directories: https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
- Maven Resources Plugin — Resource directories: https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html
- Maven Resources Plugin — Copy resources: https://maven.apache.org/plugins/maven-resources-plugin/examples/copy-resources.html
- Maven Resources Plugin — resources:resources: https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html
- Maven Resources Plugin — resources:testResources: https://maven.apache.org/plugins/maven-resources-plugin/testResources-mojo.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
