# Maven Parent POM: relativePath và cách tìm parent từ hệ thống tệp hoặc repository

## 1. Vấn đề cần giải quyết

Trong Maven, một dự án con có thể khai báo `<parent>` để **kế thừa cấu hình** từ một POM cha: phiên bản Java, properties, `dependencyManagement`, `pluginManagement`, cấu hình build và các thành phần được phép kế thừa. Trước khi Maven biết toàn bộ cấu hình của dự án con, nó phải **tìm, đọc và xác thực đúng POM cha**.

`<relativePath>` là gợi ý cho Maven tìm file POM cha trong **bản checkout trên máy hiện tại**. Nếu không tìm được POM phù hợp ở vị trí đó, Maven có thể phân giải parent theo tọa độ `groupId:artifactId:version` thông qua **local Maven repository** và **remote repositories**. Vì vậy cần hiểu cả đường dẫn file, tọa độ Maven và thứ tự phân giải.

Bài này tập trung vào Maven **3.x**, với ghi chú riêng về khác biệt Maven 4. Ví dụ hoàn chỉnh dùng Java 17+ và một dự án cha–con có thể build trên Windows, Linux hoặc macOS.

Sau bài học, bạn có thể:

1. Giải thích vì sao thiếu `relativePath` có nghĩa khác với `<relativePath/>`.
2. Chọn đường dẫn cha chính xác trong cấu trúc thư mục lồng nhau hoặc nằm ngang.
3. Hiểu vì sao Maven chỉ nhận POM cục bộ khi **tọa độ của nó khớp** `<parent>`.
4. Phân biệt lấy parent từ workspace, cache `~/.m2/repository` và repository từ xa.
5. Tự xây dựng và kiểm tra dự án kế thừa POM, xử lý `Non-resolvable parent POM` hoặc cảnh báo `parent.relativePath`.

## 2. Một parent được khai báo bằng những thông tin nào?

Một POM con thường có fragment:

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Ba trường **`groupId`, `artifactId`, `version`** chỉ rõ *parent nào* được yêu cầu. `relativePath` chỉ rõ *nơi nên thử tìm file parent đó trong hệ thống tệp*. Nó không thay thế ba tọa độ trên. Khi Maven đọc một POM tại vị trí được gợi ý, parent trong file đó phải có tọa độ phù hợp; chỉ trùng tên file `pom.xml` là chưa đủ.

Trong các dự án Maven thông thường, parent POM sử dụng **`<packaging>pom</packaging>`** vì mục đích của nó là quản lý mô hình và cấu hình, không tạo JAR từ mã nguồn của root. Project con có thể dùng `jar`, `war` hoặc packaging khác tùy nhiệm vụ.

**Khác biệt với dependency:** `<parent>` phục vụ *kế thừa mô hình build*. Một dependency trong `<dependencies>` phục vụ bổ sung thư viện cho chương trình. Maven phải giải quyết parent rất sớm để dựng **effective POM**; parent không được chọn đơn giản như một thư viện runtime thông thường.

## 3. Thuật toán tìm parent trong Maven 3.x

Đối với trường hợp phổ biến với **Maven 3**, có thể hình dung như sau:

~~~text
Maven đọc POM con
       |
       v
Đọc <parent>: groupId, artifactId, version
       |
       v
relativePath có giá trị không?
       | có                         | rỗng
       v                             v
Thử POM tại đường dẫn          Bỏ bước tìm POM
tương đối trên hệ thống tệp    trên hệ thống tệp
       |
       v
POM tồn tại và GAV khớp?
       | có             | không
       v                 |
Chấp nhận parent         v
từ file cục bộ       Tra parent theo tọa độ
                         |
                         v
                  Local Maven repository
                         |
                         v (nếu chưa có hoặc cần kiểm tra)
                  Remote repositories đã cấu hình
                         |
                         v
                  Đọc parent / báo lỗi
~~~

Sơ đồ mô tả **trình tự ưu tiên thông dụng của Maven 3**, không phải mọi chi tiết bộ phân giải trong từng phiên bản Maven hay cấu hình reactor. Điểm quan trọng: **`relativePath` không buộc Maven dùng một POM sai tọa độ**. Nếu file ở vị trí đó thiếu hoặc GAV không khớp, Maven tiếp tục tìm theo tọa độ qua cơ chế repository; khi không phân giải được thì build dừng.

Các vị trí cần phân biệt:

| Nơi tìm | Bản chất | Cách nhận biết |
| --- | --- | --- |
| Đường dẫn `relativePath` | File trong source checkout; ví dụ `../pom.xml` | Dễ thay đổi khi bạn checkout/di chuyển project |
| **Local Maven repository** | Kho artifact đã cài hoặc tải về; mặc định `~/.m2/repository` | File parent nằm dưới đường dẫn dựa trên groupId/artifactId/version |
| **Remote repository** | Kho Maven truy cập qua mạng (Maven Central, kho tổ chức, mirror…) | Có thể yêu cầu cấu hình repository, chứng thực hoặc proxy |

**`~/.m2/repository` không phải cùng khái niệm với `relativePath`.** Đường dẫn đến POM ngay trong workspace là lựa chọn phục vụ phát triển một checkout. Local repository là cache/kho artifact Maven, có thể dùng cả khi source của parent không nằm trên máy.

### Cần biết thêm về Maven 4

Tài liệu chính thức của Maven nêu rõ: với **Maven 3**, `<relativePath/>` bỏ tra cứu parent trên hệ thống tệp và tìm bằng repositories; **Maven 4** còn có khả năng tra parent trong các project của build/reactor. Vì thế phần mô tả chi tiết dưới đây nhắm Maven 3.x; không suy đoán thứ tự nội bộ của Maven 4 giống hệt. Luôn xem phiên bản bằng `mvn -version`.

## 4. Ba cách viết relativePath và kết quả khác nhau

### 4.1. Bỏ hoàn toàn phần tử relativePath

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Trong **Maven 3**, không khai báo `relativePath` có nghĩa Maven dùng giá trị **mặc định `../pom.xml`**. Maven tìm một POM ở thư mục cha của thư mục chứa POM con. Nếu file có tọa độ khớp thì lấy làm parent ngay; nếu không, Maven phân giải theo repository.

Tình huống điển hình:

~~~text
training-parent/
├── pom.xml                # parent
└── app/
    ├── pom.xml            # child, mặc định ../pom.xml
    └── src/main/java/
~~~

Ở đây `../pom.xml` được tính **từ vị trí `app/pom.xml`**, không phải từ thư mục hiện tại của terminal.

### 4.2. Khai báo relativePath cụ thể

Khi thư mục parent **không nằm ngay trên project con**, phải chỉ rõ đường dẫn hợp lý. Ví dụ:

~~~text
workspace/
├── parent-config/
│   └── pom.xml
└── application/
    └── pom.xml
~~~

Trong `application/pom.xml`:

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../parent-config/pom.xml</relativePath>
</parent>
~~~

Maven thử POM ở `workspace/parent-config/pom.xml`. Hãy đối chiếu GAV trong file đó với `<parent>`. Đường dẫn có thể đi lên nhiều cấp, ví dụ `../../build/parent/pom.xml`, miễn kết quả trỏ đến file POM mong muốn.

**Đường dẫn tương đối không phụ thuộc việc bạn chạy `mvn` từ thư mục nào.** Nếu gọi `mvn -f application/pom.xml validate` ở `workspace/`, `relativePath` vẫn được hiểu từ `application/pom.xml`.

### 4.3. relativePath rỗng: <relativePath/>

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <relativePath/>
</parent>
~~~

Trong **Maven 3**, phần tử rỗng có nghĩa **không dùng gợi ý filesystem parent**; Maven phân giải parent bằng tọa độ từ repository. Cách viết `<relativePath></relativePath>` cũng có nội dung rỗng, nhưng dạng tự đóng `<relativePath/>` thường rõ ràng hơn.

Trường hợp này có ích với **parent được phát hành độc lập**, ví dụ parent POM của một framework, tổ chức hoặc bộ build dùng chung. Bạn muốn dùng bản parent đã phát hành theo `groupId:artifactId:version`, tránh Maven vô tình đọc một `../pom.xml` không liên quan.

Điểm cần nhớ: **rỗng khác với không khai báo**. Không khai báo = thử `../pom.xml`. Rỗng = bỏ bước đó trong Maven 3.

| Cách viết trong `<parent>` | Maven 3 tìm trong filesystem | Khi thích hợp |
| --- | --- | --- |
| Không có `relativePath` | `../pom.xml` | Parent ở thư mục ngay phía trên |
| `<relativePath>../pom.xml</relativePath>` | `../pom.xml` | Muốn ghi rõ mặc định |
| `<relativePath>../parent-config/pom.xml</relativePath>` | Đường dẫn tự chọn | Parent ở sibling/nhiều cấp |
| `<relativePath/>` | Bỏ bước này | Parent phải được phân giải qua repository |

## 5. Ví dụ hoàn chỉnh: parent ngay trên child

Ví dụ này minh họa **parent trên hệ thống tệp**. Không cần cài parent vào `~/.m2/repository` trước khi build child nếu file parent hợp lệ nằm đúng vị trí.

### 5.1. Cấu trúc project

~~~text
training-parent/
├── pom.xml
└── app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── org/
                    └── example/
                        └── Main.java
~~~

### 5.2. POM cha: training-parent/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
~~~

Parent đặt phiên bản Java qua `maven.compiler.release` và phiên bản Compiler Plugin. Các cấu hình build này có thể được project con kế thừa. Parent có `packaging=pom` nên bản thân parent không mặc định tạo một JAR.

Ví dụ root này **không khai báo `<modules>`**: việc kế thừa của child vẫn hoạt động, dù parent không phải aggregator. Điều này giúp thấy rõ inheritance là quan hệ do `<parent>` trong child khai báo.

### 5.3. POM con: training-parent/app/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.training</groupId>
        <artifactId>training-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>demo-app</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Ở đây child **không khai báo `groupId` và `version` riêng**, vì hai giá trị đó được kế thừa từ parent. Artifact con sẽ có tọa độ `org.example.training:demo-app:1.0.0`. Parent được tìm qua mặc định `../pom.xml`, trỏ đến `training-parent/pom.xml`.

### 5.4. Mã nguồn: training-parent/app/src/main/java/org/example/Main.java

~~~java
package org.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Parent resolved; Java 17 build OK");
    }
}
~~~

Đây là chương trình Java hoàn chỉnh. Dùng **JDK 17+**, Maven 3.x với kết nối repository khi plugin chưa được cache. Tại thư mục **training-parent/** chạy:

~~~bash
java -version
javac -version
mvn -version
mvn -f app/pom.xml clean package
java -cp app/target/demo-app-1.0.0.jar org.example.Main
~~~

**Stdout của dòng chạy Java (không tính log Maven):**

~~~text
Parent resolved; Java 17 build OK
~~~

Giải thích kết quả:

1. Maven đọc `app/pom.xml` rồi tra `../pom.xml` — file parent trong cùng checkout.
2. Maven xác nhận GAV của parent là `org.example.training:training-parent:1.0.0`, khớp `<parent>`.
3. Child thừa hưởng các properties và cấu hình Compiler Plugin; phase `compile` biên dịch `Main.java` nhắm Java 17.
4. Phase `package` tạo `app/target/demo-app-1.0.0.jar`. Vì ví dụ không khai báo `Main-Class` trong manifest, lệnh chạy sử dụng `java -cp` với main class đầy đủ thay vì mặc định `java -jar`.

**Kết quả không phụ thuộc parent đã được `mvn install` hay chưa**, miễn file parent có mặt tại vị trí phù hợp và các plugin cần thiết tải được. Parent trong workspace không có nghĩa Maven sẽ build cả source của một aggregator; ví dụ chỉ build child được chỉ định bởi `-f`.

## 6. Thử chuyển từ đường dẫn local sang repository

Giả sử vẫn dùng cấu trúc parent–child ở trên. Hãy làm hai bước tách biệt để thấy được khác biệt.

### 6.1. Cài parent POM vào local Maven repository

Tại thư mục `training-parent/`, chạy:

~~~bash
mvn -f pom.xml install
~~~

Với parent có `packaging=pom` và không có module, phase `install` đưa POM (và metadata liên quan) vào local repository. Theo cấu hình mặc định, file POM sẽ nằm ở vị trí có dạng:

~~~text
~/.m2/repository/org/example/training/training-parent/1.0.0/training-parent-1.0.0.pom
~~~

Trên Windows, thư mục repository mặc định là `C:\Users\<ten-tai-khoan>\.m2\repository`. Nếu `settings.xml` đã đặt `<localRepository>` riêng hoặc lệnh Maven dùng tùy chọn thay đổi repository, đường dẫn thực tế có thể khác. Đây là **bản artifact POM đã cài**, không phải file gốc tại `training-parent/pom.xml`.

### 6.2. Sửa duy nhất fragment parent của child

Trong `app/pom.xml`, dùng:

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <relativePath/>
</parent>
~~~

Đây là fragment thay thế **bên trong POM con**, không phải file POM đầy đủ mới. Bây giờ Maven 3 **không dùng file `../pom.xml` để tìm parent** và phân giải theo tọa độ qua repository. Nếu parent 1.0.0 đã được `install` vào local repository đúng chỗ, lệnh:

~~~bash
mvn -f app/pom.xml clean package
java -cp app/target/demo-app-1.0.0.jar org.example.Main
~~~

vẫn chạy được và stdout vẫn là:

~~~text
Parent resolved; Java 17 build OK
~~~

Điều này cho thấy **cùng GAV có thể được phân giải qua hai nguồn khác nhau**. Nếu chưa cài parent, Maven có thể cố tìm trong remote repositories được cấu hình; với GAV minh họa `org.example.training:training-parent:1.0.0`, đừng giả định có một artifact thật trên Maven Central.

Để xác minh rõ hơn tác động của repository, có thể tạo một local repository tách biệt bằng tùy chọn `-Dmaven.repo.local=...` hoặc dùng môi trường sạch. Thao tác đó thay đổi nơi Maven cache cả plugin, vì vậy cần chuẩn bị sẵn plugin hoặc mạng. Không xóa toàn bộ `~/.m2/repository` chỉ để thử một bài học.

### 6.3. Tại sao parent POM phải được install/deploy khi dùng repository?

Nếu child yêu cầu parent qua repository, Maven cần tìm **artifact POM đúng tọa độ và phiên bản**. File parent chỉ có trong source checkout nhưng không nằm ở đường dẫn `relativePath` được dùng, cũng chưa được cài/phát hành, thì Maven 3 có thể không phân giải được.

- **`mvn install`** trên parent: đưa bản POM vào **local repository của máy đang build**.
- **`mvn deploy`** trên parent: phát hành POM lên **remote repository** đã cấu hình, để máy đồng đội/CI tải được.
- **Build trong cùng checkout** với `relativePath` chính xác: Maven có thể dùng file parent trực tiếp mà không cần phát hành trước.

Một POM đã được install vào máy lập trình viên **không tự xuất hiện** trên CI hoặc máy khác. Nếu project cần build độc lập với source parent, hãy bảo đảm parent POM có thể lấy từ repository được các môi trường truy cập, và phiên bản được phát hành phù hợp.

## 7. Phân giải qua local repository và remote repositories

Khi Maven không dùng được parent trên filesystem, bộ phân giải phải tìm artifact POM bằng tọa độ:

~~~text
org.example.training:training-parent:1.0.0
                  |
                  v
Local Maven repository (~/.m2/repository)
                  |
            nếu không có
                  v
Remote repositories/mirror được cấu hình
                  |
         có artifact POM hợp lệ?
             | có        | không
             v            v
          Cache và      Non-resolvable
          dùng parent    parent POM
~~~

Đây là luồng **khái quát**, còn việc kiểm tra cập nhật metadata, cache và SNAPSHOT phụ thuộc phiên bản, repository policies và cài đặt Maven.

**Local repository** mặc định ở `~/.m2/repository`, với cấu trúc thư mục theo groupId/artifactId/version. Nó có thể chứa parent được cài bằng `mvn install` hoặc được tải từ server. Khi parent là **release** đã cache, Maven có thể dùng bản đã có; một version cố định không có nghĩa Maven tự động phát hiện bạn vừa sửa file nguồn parent ngoài workspace.

**Remote repositories** có thể gồm Maven Central và kho riêng của tổ chức. Parent tự phát triển thường không tồn tại trên Central; cần phát hành qua repository quản lý nội bộ hoặc có cách khác để truy cập POM.

### 7.1. Chọn repository bằng settings.xml

Trong Maven 3, user settings thường ở `~/.m2/settings.xml`; trên Windows là thư mục `.m2` thuộc user profile. Cấu hình dưới đây chỉ minh họa một repository nội bộ. URL `repo.example.org` là **địa chỉ ví dụ**, không phải server hoạt động:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <profiles>
        <profile>
            <id>internal-releases</id>
            <repositories>
                <repository>
                    <id>internal-releases</id>
                    <url>https://repo.example.org/maven/releases</url>
                </repository>
            </repositories>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>internal-releases</activeProfile>
    </activeProfiles>
</settings>
~~~

File trên là **một ví dụ settings độc lập**; khi áp dụng phải hòa vào `settings.xml` hiện có, tránh ghi đè cấu hình khác. Một repository profile chỉ có tác dụng khi **được kích hoạt**. Doanh nghiệp có thể dùng mirror/repository manager thay vì khai báo trực tiếp từng repository.

Thông tin đăng nhập (nếu có) nên nằm trong phần `<servers>` của settings với ID khớp repository/mirror, được bảo vệ theo quy trình quản lý thông tin nhạy cảm; **không ghi mật khẩu trực tiếp vào POM được commit**. Nếu parent không tải được, ngoài GAV và URL cần kiểm tra active profile, mirror, proxy, xác thực và quyền truy cập.

**Một lưu ý về thứ tự bootstrap:** Maven cần phân giải parent để xây dựng effective POM của child; không thể trông chờ một cấu hình chỉ được kế thừa từ **chính parent chưa tải được** sẽ luôn “tự cứu” quá trình tải parent ấy. Khi phụ thuộc repository riêng, cấu hình môi trường/build ban đầu (chẳng hạn active settings profile hoặc mirror) phải đủ để tìm parent.

### 7.2. Offline, SNAPSHOT và version release

- `mvn -o -f app/pom.xml validate` bật **offline mode**: không tải parent mới từ remote. Lệnh chỉ thành công nếu những artifact/plugin cần thiết đã có trong local repository hoặc parent được tìm theo đường local hợp lệ.
- `mvn -U -f app/pom.xml validate` yêu cầu Maven cập nhật thông tin cần thiết, đặc biệt liên quan SNAPSHOT và trạng thái kiểm tra remote. Nó **không** sửa sai tọa độ `groupId/artifactId/version` hay tự phát hành parent chưa có.
- Bản `1.0.0-SNAPSHOT` có quy tắc cập nhật metadata/checksum khác một release `1.0.0`. Nếu nội dung parent thay đổi nhưng vẫn dùng version release cũ đã công bố, giải pháp tốt là **phát hành version mới và cập nhật child**, thay vì ghi đè một release bất biến.
- Tùy chọn `-Dmaven.repo.local=<duong-dan>` chỉ đổi **local repository** cho lệnh Maven; nó không thay đổi `relativePath` hoặc tọa độ parent.

## 8. Inheritance và aggregation là hai quan hệ khác nhau

**Inheritance** được khai báo ở POM **con** bằng `<parent>`. Nó giải thích vì sao con nhận các properties, dependencyManagement, pluginManagement và cấu hình build từ parent. Đó là quan hệ mà `relativePath` hỗ trợ.

**Aggregation** được khai báo ở POM **root** bằng `<modules>`; nó cho Maven biết các module nào nằm trong cùng **reactor build**. Một root POM có thể đồng thời làm parent và aggregator, nhưng **không bắt buộc**.

Ví dụ một aggregator có:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>app</module>
    <module>common</module>
</modules>
~~~

Đây là fragment trong root POM. Nếu mỗi module tự khai báo parent hoặc các cấu hình riêng, reactor có thể build cả các module khi chạy ở root. Tuy nhiên:

- Chỉ thêm `<modules>` ở root **không tự tạo quan hệ kế thừa** trong POM con.
- Chỉ thêm `<parent>` ở POM con **không tự khiến root build con** khi chạy `mvn package` tại root không có `<modules>`.
- `<relativePath>` là đường từ **child tới parent POM** để kế thừa; nó không phải mục thay thế cho `<module>`, cũng không dùng để khai báo thư viện dependency.

Ví dụ ở phần 5 không có `<modules>` mà vẫn build child bằng `mvn -f app/pom.xml clean package`, chứng minh inheritance có thể độc lập với aggregation.

## 9. Những trường hợp đường dẫn và tọa độ không khớp

### Trường hợp A: POM nằm đúng chỗ nhưng version sai

Child yêu cầu:

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Nhưng file `../pom.xml` thực sự khai báo `<version>2.0.0</version>`. Maven **không được tự chọn 2.0.0** chỉ vì file nằm đúng chỗ: nó cần parent 1.0.0. Tùy phiên bản Maven, log có thể cảnh báo `'parent.relativePath' points at wrong local POM` trước khi thử repository.

Nếu bạn thực sự muốn 2.0.0, cập nhật `<parent><version>2.0.0</version>` và xác minh tính tương thích. Nếu project yêu cầu 1.0.0, dùng đúng POM local của bản đó hoặc bảo đảm 1.0.0 có trong repository. Đừng sửa ngẫu nhiên `relativePath` để “che” việc sai version.

### Trường hợp B: Đường dẫn trỏ nhầm một POM khác

Cây thư mục:

~~~text
workspace/
├── pom.xml                   # aggregator khác
├── parent-config/pom.xml     # parent mong muốn
└── application/pom.xml       # child
~~~

Nếu child bỏ `relativePath`, mặc định `../pom.xml` trỏ đến `workspace/pom.xml`. File này có thể khác GAV parent mong muốn; Maven cảnh báo rồi tra repository. Cách sửa phù hợp là:

~~~xml
<relativePath>../parent-config/pom.xml</relativePath>
~~~

với điều kiện GAV trong `parent-config/pom.xml` khớp `<parent>`. Nếu đó là parent đã phát hành độc lập và không cần đọc POM trong checkout, có thể chọn `<relativePath/>`.

### Trường hợp C: POM local được sửa nhưng child vẫn dùng bản từ repository

Có thể child chứa `<relativePath/>` nên Maven 3 bỏ qua file parent local dù file đó tồn tại. Khi ấy child dùng bản cache/repository theo GAV. Kiểm tra lựa chọn của bạn: muốn thử thay đổi parent ngay trong checkout thì dùng `relativePath` đúng, muốn ổn định theo bản đã phát hành thì giữ rỗng và tăng/phát hành version khi thay đổi.

### Trường hợp D: Dự án build trên máy bạn nhưng CI lỗi

Trên máy bạn có thể đã chạy `mvn install` cho parent hoặc có file parent bên cạnh child. CI checkout chỉ mỗi child hoặc có local repository trống. Vì vậy lỗi `Non-resolvable parent POM` trên CI không có nghĩa Maven đang tìm sai tên: CI có thể **thiếu parent tại cả filesystem lẫn repository được phép truy cập**.

Giải pháp tùy cách thiết kế: checkout đúng cấu trúc parent–child, phát hành parent POM lên repository có thể truy cập từ CI, hoặc cấu hình settings/mirror và credentials phù hợp. Không dựa vào local repository cá nhân như một phần của build có thể tái lập.

## 10. Cách chẩn đoán theo từng bước

1. **Ghi lại Maven version** với `mvn -version`; thuật toán tìm parent có khác biệt giữa Maven 3 và 4.
2. **Mở đúng POM con**; xem `<parent>`, ba tọa độ và giá trị `<relativePath>`. Xác định rõ không có phần tử hay phần tử rỗng.
3. **Tính đường dẫn từ POM con**, không từ thư mục terminal. Kiểm tra file ở đó tồn tại, có `packaging=pom` và GAV đúng hay không.
4. **Nếu lookup qua repository**, kiểm tra parent GAV đã được install/deploy, repository URL có đúng, settings profile có active và mirror/credentials hoạt động. Với local repository mặc định, kiểm tra đường dẫn tương ứng theo GAV.
5. **Chạy Maven ở chế độ báo lỗi rõ hơn**, nhưng chỉ sau khi hiểu vị trí POM:

~~~bash
mvn -f app/pom.xml validate -e
mvn -f app/pom.xml validate -X
~~~

`-e` in stack trace khi cần; `-X` in debug log rất dài, hữu ích để xem repository/model resolution. Trong ví dụ, chạy các lệnh từ root `training-parent/`. Khi parent không phân giải được, ngay cả `validate` cũng có thể dừng, vì Maven phải dựng model trước.

6. **Sau khi parent phân giải thành công**, kiểm tra POM hiệu lực:

~~~bash
mvn -f app/pom.xml help:effective-pom -Doutput=effective-pom.xml
~~~

Mở file output thực tế để tìm `groupId`, `version`, `maven.compiler.release` và plugin mà child thừa hưởng. File output có thể được ghi theo thư mục module/cách gọi plugin; không giả định vị trí trước khi xem log. Help Plugin có thể cần Internet trong lần dùng đầu.

7. Nếu cần xem cấu hình Maven về repository và active profile, sử dụng `mvn help:effective-settings` trong một Maven project đã dựng được model; khi child còn lỗi phân giải parent, hãy kiểm tra trực tiếp `settings.xml` hoặc chạy goal tại một project độc lập hợp lệ.

### Bảng lỗi và cách khắc phục

| Lỗi / hiện tượng | Nguyên nhân thường gặp | Xử lý có mục tiêu |
| --- | --- | --- |
| `Non-resolvable parent POM` | Không có parent đúng GAV tại path hoặc repository | Đối chiếu GAV, relativePath, local cache và remote |
| `parent.relativePath points at wrong local POM` | File tại relativePath là POM khác hoặc sai version | Trỏ đúng file, sửa GAV nếu chủ đích, hoặc bỏ local lookup |
| `parent.relativePath points at no local POM` | Không có đường dẫn phù hợp hoặc đã dùng relativePath rỗng, kèm lỗi repo | Nếu parent ở checkout, sửa path; nếu parent phát hành, kiểm tra repository |
| Parent version không đúng dù file tồn tại | `<parent><version>` khác version trong POM local | Đồng bộ version/đường dẫn, không ép Maven chấp nhận POM sai |
| `Could not find artifact ... :pom:...` | Parent POM chưa install/deploy hoặc repo không chứa version | Install/deploy đúng POM và GAV, cấu hình repository |
| `401 Unauthorized` / `403 Forbidden` | Repository yêu cầu quyền truy cập | Kiểm tra credentials trong settings, server ID và quyền |
| `Unknown host` / timeout / TLS error | Mạng, DNS, proxy, chứng chỉ hoặc mirror có vấn đề | Kiểm tra mạng, proxy, CA/JDK và cấu hình repo |
| Build offline không tìm được parent | Parent chưa có trong local repo và không có POM local được dùng | Chuẩn bị cache hoặc build online, kiểm tra relativePath |
| Chạy từ thư mục khác tưởng relativePath đổi | Nhầm base path của `relativePath` với working directory | Tính từ POM con; dùng `-f` và đường dẫn nhất quán |
| Thay parent POM local nhưng không thấy thay đổi | Child dùng `<relativePath/>` hoặc bản parent từ cache | Kiểm tra cách resolve; phát hành version mới khi dùng repo |
| Build root thành công nhưng child lẻ thất bại | Reactor có đủ parent/module nhưng checkout độc lập không có POM cần thiết | Bảo đảm parent đã phát hành hoặc đường dẫn checkout phù hợp |
| Build child được nhưng chạy `mvn package` ở root không tạo child JAR | Root chỉ có `<parent>`/packaging POM và không có `<modules>` | Thêm aggregation nếu muốn build module từ root; không nhầm inheritance |
| Lỗi vòng lặp kế thừa / model không hợp lệ | Parent tham chiếu vòng về child hoặc cấu trúc POM sai | Kiểm tra các `<parent>` liên tiếp và phá vòng phụ thuộc |

**Không “sửa” bằng cách xóa toàn bộ `~/.m2/repository`** như bước đầu tiên. Việc đó làm mất cache của nhiều dự án, phải tải lại plugin/dependency và không xử lý được lỗi GAV hay `relativePath`. Khoanh vùng chính xác parent artifact, metadata và repository đang dùng trước.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong `app/pom.xml` không có phần tử `relativePath`. Parent nằm ở đâu nếu cấu trúc là `root/app/pom.xml`?  
**Đáp án:** Maven 3 thử `root/pom.xml` (tương đương `../pom.xml` tính từ child POM), kiểm tra GAV rồi mới dùng repository khi cần.

**Câu 2.** Ghi `<relativePath/>` khác bỏ phần tử ra sao?  
**Đáp án:** Bỏ phần tử dùng mặc định `../pom.xml`; rỗng bỏ tìm parent filesystem trong Maven 3 và tra theo tọa độ qua repository.

**Câu 3.** Parent nằm ở `workspace/parent-config/pom.xml`, child ở `workspace/application/pom.xml`. Viết relativePath thế nào?  
**Đáp án:** `<relativePath>../parent-config/pom.xml</relativePath>`.

**Câu 4.** Đúng vị trí relativePath nhưng parent `version=2.0.0` trong khi child yêu cầu `1.0.0`. Maven có kế thừa 2.0.0 không?  
**Đáp án:** Không, file ở đường local không thỏa GAV; Maven cần tìm parent 1.0.0 theo repository hoặc đổi cấu hình child có chủ đích.

**Câu 5.** Parent đã được `mvn install` trên laptop, còn CI có local repo trống và `<relativePath/>`. Điều gì xảy ra?  
**Đáp án:** CI cần tải parent từ một remote repository được cấu hình và có quyền truy cập; nếu không có, phân giải parent thất bại.

**Câu 6.** Root có `<modules>` trỏ tới app, nhưng app không có `<parent>`. App có kế thừa properties của root không?  
**Đáp án:** Không mặc định. `<modules>` thiết lập aggregation; inheritance cần `<parent>` trong child.

**Câu 7.** Có thể dùng parent POM từ remote nhưng vẫn tham chiếu dependency trong POM con không?  
**Đáp án:** Có. Parent xác định cấu hình build được kế thừa; dependency của child là các artifact phục vụ compile/runtime/test. Hai cơ chế có mục đích khác nhau.

## 12. Checklist khi cấu hình parent cho dự án thực tế

- Parent POM có packaging `pom` và tọa độ **groupId:artifactId:version** ổn định, có thể kiểm tra rõ ràng.
- Child khai báo chính xác ba tọa độ trong `<parent>`, không cố dùng `relativePath` để thay thế.
- Nếu parent nằm trong cùng checkout, dùng `../pom.xml` mặc định hoặc path tùy chỉnh **tính từ child POM**.
- Nếu parent được phát hành độc lập, cân nhắc `<relativePath/>` để tránh chọn nhầm parent trong filesystem, và bảo đảm repo có bản POM đã phát hành.
- Không nhầm `relativePath` với `<modules>`, dependency path, hay đường dẫn local Maven repository.
- Kiểm tra build độc lập trên CI/môi trường sạch: parent phải có trong đúng checkout hoặc repository/mirror truy cập được; không phụ thuộc cache cá nhân.
- Khi thay đổi parent đã phát hành, cập nhật version và theo dõi compatibility; không dựa vào việc ghi đè release cũ.
- Sau khi phân giải thành công, xem effective POM để xác nhận các properties, dependencyManagement/pluginManagement và cấu hình kế thừa thực sự có hiệu lực.

## Tài liệu chính thức

1. [Apache Maven — POM Reference: Inheritance và relativePath](https://maven.apache.org/pom.html)
2. [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
3. [Apache Maven — Parent model, Maven 3](https://maven.apache.org/ref/3-LATEST/xref/org/apache/maven/model/Parent.html)
4. [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
5. [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
6. [Apache Maven — Configuring Maven và localRepository](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
7. [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
