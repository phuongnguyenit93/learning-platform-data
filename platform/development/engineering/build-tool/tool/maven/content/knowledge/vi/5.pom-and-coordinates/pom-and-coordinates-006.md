# Maven artifact: type, classifier và phần mở rộng tệp

## 1. Mục tiêu và mô hình tư duy

Khi khai báo một dependency trong `pom.xml`, nhiều người chỉ nhìn ba thông tin `groupId`, `artifactId` và `version` (thường gọi là **GAV**). Ba thông tin đó xác định một dự án hoặc một dòng phiên bản, nhưng Maven vẫn cần biết **biến thể artifact** nào được lấy về: JAR chính, JAR chứa lớp test, source JAR, Javadoc JAR, POM hay gói WAR. Đây là lý do tồn tại các khái niệm **`type`**, **`classifier`** và **phần mở rộng tệp (file extension)**.

Sau bài này, bạn có thể:

1. Phân biệt `packaging` của dự án, `type` trong dependency, `classifier` và phần mở rộng thực tế của tệp artifact.
2. Giải thích Maven ánh xạ một dependency sang tệp có tên `artifactId-version[-classifier].extension` như thế nào.
3. Nhận ra vì sao `<type>test-jar</type>` tìm `-tests.jar`, còn `<type>pom</type>` tìm `.pom`.
4. Tạo hai artifact cùng GAV: JAR chính và JAR có classifier `tests`; cài chúng vào kho Maven cục bộ.
5. Khai báo dependency lấy đúng biến thể, xác minh kết quả và xử lý các lỗi “artifact not found” do type/classifier.

**Ý chính:** Một artifact không được xác định duy nhất chỉ bằng đuôi `.jar` hay tên dự án. Maven dùng tọa độ của nó và ánh xạ từ `type` sang `extension` cùng `classifier` để xác định tệp trong repository. `type` và `extension` liên quan chặt chẽ nhưng **không phải lúc nào cũng bằng nhau**.

## 2. Các thuật ngữ và mối quan hệ

| Thuật ngữ | Ý nghĩa | Vị trí thường gặp |
| --- | --- | --- |
| `groupId` | Không gian định danh của nhóm/tổ chức | `<project>` hoặc `<dependency>` trong `pom.xml` |
| `artifactId` | Tên kỹ thuật của artifact/dự án | `<project>` hoặc `<dependency>` |
| `version` | Phiên bản cần xây dựng hoặc tải | `<project>` hoặc `<dependency>` |
| `packaging` | Kiểu đóng gói **dự án đang được build**, quyết định lifecycle/goal và artifact chính | `<project><packaging>...` |
| `type` | Kiểu dependency **mà bên tiêu thụ yêu cầu**; Maven dùng artifact handler để suy ra extension và đôi khi classifier | `<dependency><type>...` |
| `classifier` | Nhãn phân biệt một biến thể của artifact có cùng GAV, ví dụ `tests`, `sources`, `javadoc` | `<dependency><classifier>...` hoặc plugin tạo artifact đính kèm |
| `extension` | Đuôi thực của tệp trong repository, ví dụ `jar`, `pom`, `war` hoặc `zip` | Được tính từ `type`/artifact handler; không có phần tử `<extension>` trong dependency Maven thông thường |
| `scope` | Quy định dependency tham gia classpath/giai đoạn nào, chẳng hạn `compile` hay `test` | `<dependency><scope>...` |

**Phân biệt hai chiều khác nhau:**

- **Bên sản xuất** chọn `<packaging>jar</packaging>` để Maven chạy lifecycle tạo JAR chính. Plugin có thể tạo thêm artifact đính kèm (*attached artifact*) dùng classifier khác, ví dụ `tests`.
- **Bên tiêu thụ** chọn `<type>` và `<classifier>` trong dependency để Maven tìm chính xác tệp cần dùng.

Có thể hình dung:

~~~text
POM của bên sản xuất
  groupId = dev.example
  artifactId = artifact-demo
  version = 1.0.0
  packaging = jar
       │
       ├── artifact chính
       │     artifact-demo-1.0.0.jar
       │     extension=jar, classifier=(không có)
       │
       └── artifact đính kèm do plugin tạo
             artifact-demo-1.0.0-tests.jar
             extension=jar, classifier=tests
                               ▲
                               │
POM của bên tiêu thụ   <type>test-jar</type>
                       <scope>test</scope>
                       (Maven suy ra extension=jar, classifier=tests)
~~~

Với các ví dụ thông thường, đường dẫn repository cục bộ tương ứng:

~~~text
~/.m2/repository/dev/example/artifact-demo/1.0.0/
    artifact-demo-1.0.0.pom
    artifact-demo-1.0.0.jar
    artifact-demo-1.0.0-tests.jar
~~~

`groupId` với dấu chấm được chuyển thành các thư mục, ví dụ `dev.example` → `dev/example`. File `.pom` đi kèm mô tả metadata dự án. Không phải artifact nào cũng có cả ba tệp: file `-tests.jar` chỉ xuất hiện nếu có plugin tạo và cài/triển khai nó.

## 3. Định danh artifact và công thức đặt tên

Trong phần lớn artifact Maven đã phát hành thông thường, quy tắc tên tệp là:

~~~text
artifactId-version.extension
artifactId-version-classifier.extension
~~~

Ví dụ cùng `groupId=dev.example`, `artifactId=artifact-demo`, `version=1.0.0`:

| Biến thể | Extension | Classifier | Tên tệp |
| --- | --- | --- | --- |
| JAR chính | `jar` | không có | `artifact-demo-1.0.0.jar` |
| JAR chứa lớp test | `jar` | `tests` | `artifact-demo-1.0.0-tests.jar` |
| Source JAR | `jar` | `sources` | `artifact-demo-1.0.0-sources.jar` |
| Javadoc JAR | `jar` | `javadoc` | `artifact-demo-1.0.0-javadoc.jar` |
| File POM | `pom` | không có | `artifact-demo-1.0.0.pom` |
| Biến thể tùy chọn | `zip` | `distribution` | `artifact-demo-1.0.0-distribution.zip` |

**Classifier là phần trước extension**, không phải thay thế extension: `-tests.jar` là JAR có classifier `tests`; bản thân classifier **không phải** `tests.jar`. Các classifier như `sources`, `javadoc`, `tests` là quy ước phổ biến, nhưng có thể có classifier dự án tự đặt (ví dụ `linux-x86_64` hoặc `all`); tên classifier không tự động biến JAR thành chương trình chạy được hay không chạy được.

**Lưu ý về SNAPSHOT:** Với `1.0-SNAPSHOT`, bản lưu tại repository từ xa có thể dùng phiên bản được đánh dấu thời gian và số build trong tên tệp sau khi deploy. Vì vậy công thức trên là mô hình cơ bản; không nên tự ghép tên file để thay Maven resolver. Để Maven tự giải quyết metadata, snapshot, repository và checksum.

**Không đưa `scope` vào tên tệp:** `<scope>test</scope>` quyết định dependency được dùng trong quá trình test, còn classifier `tests` quyết định Maven chọn `-tests.jar`. Hai giá trị là hai khái niệm độc lập.

## 4. `type` không đồng nhất với extension

Trong `<dependency>`, nếu bỏ qua `<type>`, Maven mặc định dùng `jar`. Từ giá trị `type`, Maven tra **artifact handler** để xác định phần mở rộng thực tế và classifier mặc định.

Một số ánh xạ quan trọng trong Maven core:

| `<type>` | Extension của artifact | Classifier mặc định | Kết quả điển hình |
| --- | --- | --- | --- |
| `jar` | `jar` | không có | JAR chính |
| `pom` | `pom` | không có | POM hoặc BOM |
| `war` | `war` | không có | Web archive |
| `ear` | `ear` | không có | Enterprise archive |
| `rar` | `rar` | không có | Resource adapter |
| `maven-plugin` | `jar` | không có | Maven plugin đóng gói thành JAR |
| `ejb` | `jar` | không có | EJB artifact |
| `test-jar` | `jar` | `tests` | JAR chứa lớp test |
| `java-source` | `jar` | `sources` | Source JAR |
| `javadoc` | `jar` | `javadoc` | Javadoc JAR |

Với loại khác chưa được artifact handler nhận diện (chẳng hạn `zip` hoặc `tar.gz`), Maven thường dùng chính chuỗi `type` làm extension, và classifier lấy theo khai báo tường minh nếu có. Plugin/extension có thể bổ sung handler, vì thế **phải kiểm tra handler của môi trường thực tế** khi dự án dùng packaging/type tùy biến.

Một số handler mặc định thay đổi giữa các nhánh Maven; bảng tập trung vào ánh xạ có ý nghĩa thực tế trong Maven 3.9/3.10. Không giả định danh sách là bất biến với mọi phiên bản Maven và extension.

### 4.1. Hai cách viết cùng lấy JAR `tests`

**Cách A — khai báo classifier một cách tường minh, type mặc định `jar`:**

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
~~~

**Cách B — sử dụng type handler `test-jar`:**

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
~~~

Trong ánh xạ mặc định, **cả hai đều yêu cầu**:

~~~text
dev/example/artifact-demo/1.0.0/artifact-demo-1.0.0-tests.jar
~~~

`test-jar` là tên type, còn file vẫn có extension `jar`. Bạn cũng có thể gặp ví dụ khai báo **cả** `<type>test-jar</type>` lẫn `<classifier>tests</classifier>`; khi hai giá trị thống nhất, chúng cùng trỏ tới biến thể trên.

Nếu khai báo classifier tường minh khác với classifier được type gợi ý, classifier tường minh được ưu tiên. Không nên trộn các biến thể mà không hiểu chính xác artifact nào đã được xuất bản.

### 4.2. Tại sao `type=java-source` không có nghĩa là `.java`?

`java-source` là một **type handler**: Maven ánh xạ sang file `-sources.jar`. Tệp này là archive chứa file `.java`, không phải một tệp đơn có extension `.java` và cũng không phải JAR chính chứa bytecode. Cách gọi type mô tả **vai trò** của artifact, không nhất thiết mô tả đuôi vật lý.

Ví dụ:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <type>java-source</type>
</dependency>
~~~

Maven ánh xạ đến `artifact-demo-1.0.0-sources.jar` nếu repository có artifact đó. Tuy vậy, source JAR thường phục vụ IDE hoặc công cụ phân tích; không nên thêm source JAR như dependency biên dịch Java thông thường. Maven thường tự tìm `sources` khi IDE có nhu cầu.

## 5. `packaging` của dự án khác `type` của dependency

Trong POM của **dự án đang được build**:

~~~xml
<groupId>dev.example</groupId>
<artifactId>artifact-demo</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

`packaging=jar` (cũng là mặc định nếu không khai báo) chọn lifecycle và bộ goal đóng gói cho JAR chính. Đổi thành `war` khiến lifecycle và plugin đóng gói thay đổi để tạo WAR (nếu dự án có cấu trúc/cấu hình phù hợp). Dùng `packaging=pom` thường phục vụ parent POM, aggregator và BOM: file POM là artifact chính.

Ngược lại, `<dependency><type>...` mô tả **bản artifact người tiêu thụ yêu cầu**, không làm thay đổi packaging của dự án đang build. Ví dụ consumer có `<packaging>jar</packaging>` nhưng hoàn toàn có thể khai báo dependency `<type>pom</type>` trong một lần import BOM.

| Vị trí | Ví dụ | Tác dụng |
| --- | --- | --- |
| `<project><packaging>jar</packaging>` | Dự án thư viện Java | Tạo JAR chính trong giai đoạn package |
| `<project><packaging>pom</packaging>` | Parent/BOM/aggregator | Dùng POM làm artifact chính; không tạo JAR ứng dụng theo mặc định |
| `<dependency><type>jar</type>` | Consumer lấy thư viện | Resolver tìm tệp JAR |
| `<dependency><type>pom</type>` | Import BOM | Resolver lấy POM, không thêm bytecode vào classpath |
| `<dependency><type>test-jar</type>` | Consumer lấy fixture test | Resolver tìm JAR có classifier `tests` |

**Sai lầm phổ biến:** thấy dự án producer có `packaging=jar` rồi kết luận producer không thể xuất bản `-tests.jar`. Thực tế Maven plugin có thể **đính kèm nhiều artifact** lên cùng GAV với classifier/extension khác nhau, trong khi packaging chính vẫn là `jar`.

## 6. Thực hành từ đầu: xuất bản JAR chính và JAR `tests`

Ví dụ hoàn chỉnh dưới đây dùng **Java 17+**, Maven 3.x tương thích và plugin phiên bản xác định. Mục tiêu là quan sát file tạo ra, đưa vào local repository và tiêu thụ đúng biến thể; không cần framework bên thứ ba. Một lần chạy đầu cần tải plugin từ Maven repository nếu cache chưa có.

Cấu trúc hai dự án **độc lập** (không cần parent POM):

~~~text
artifact-lab/
├── producer/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/Greeting.java
│       └── test/java/dev/example/SampleFixture.java
└── consumer/
    ├── pom.xml
    └── src/test/java/dev/consumer/FixtureUse.java
~~~

### 6.1. Producer POM

Nội dung toàn bộ `producer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>artifact-demo</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <executions>
                    <execution>
                        <id>attach-test-classes</id>
                        <goals>
                            <goal>test-jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`maven-jar-plugin:test-jar` có giai đoạn mặc định `package`. Vì goal được khai báo trong `executions`, lúc `mvn package` Maven tạo JAR đính kèm từ nội dung `target/test-classes`. Đây **không** phải một dependency khai báo trong `<dependencies>`: plugin đang **sản xuất artifact**. Nếu gọi riêng `mvn compile`, chưa tới giai đoạn đóng gói nên không nên mong có `-tests.jar`.

### 6.2. Mã Java của producer

Tạo `producer/src/main/java/dev/example/Greeting.java`:

~~~java
package dev.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello, artifact!";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo `producer/src/test/java/dev/example/SampleFixture.java`:

~~~java
package dev.example;

public final class SampleFixture {
    private SampleFixture() {
    }

    public static String sample() {
        return "sample-fixture";
    }
}
~~~

`SampleFixture` nằm trong thư mục source test nhưng **không phải** bài test JUnit; đây chỉ là một class dùng lại ở consumer để chứng minh Maven có thể đóng gói và tìm JAR `tests`. Vì ví dụ không có test framework, việc `mvn package` báo thành công không có nghĩa dự án đã chạy bộ test nghiệp vụ.

### 6.3. Biên dịch, đóng gói, cài đặt và quan sát

Mở terminal trong **`artifact-lab/producer`**:

~~~bash
java -version
mvn -version
mvn -B -ntp clean install
java -cp target/classes dev.example.Greeting
jar tf target/artifact-demo-1.0.0.jar
jar tf target/artifact-demo-1.0.0-tests.jar
~~~

Lệnh `install` chạy các phase trước nó, gồm `compile`, `test-compile`, `package` rồi cài artifact vào `~/.m2/repository`. Kết quả **stdout của lệnh `java`** ở trên là:

~~~text
Hello, artifact!
~~~

Trong danh sách `jar tf`, JAR chính phải chứa đường dẫn class:

~~~text
dev/example/Greeting.class
~~~

Còn JAR `tests` phải chứa:

~~~text
dev/example/SampleFixture.class
~~~

`jar tf` còn in những mục như `META-INF/` và `META-INF/MANIFEST.MF`, không cần coi các dòng phụ đó là lỗi. Hai lệnh `jar tf` hiển thị **các archive khác nhau**.

Các file mong đợi sau khi build, nếu giữ `finalName` mặc định:

~~~text
producer/target/artifact-demo-1.0.0.jar
producer/target/artifact-demo-1.0.0-tests.jar

~/.m2/repository/dev/example/artifact-demo/1.0.0/
    artifact-demo-1.0.0.pom
    artifact-demo-1.0.0.jar
    artifact-demo-1.0.0-tests.jar
~~~

Đường dẫn local repository có thể khác `~/.m2/repository` nếu máy/CI dùng cài đặt `settings.xml` hoặc tùy chọn `-Dmaven.repo.local`. Trên Windows, ký hiệu `~` thường tương ứng thư mục người dùng, chẳng hạn `C:\Users\<username>\.m2\repository`.

Maven tạo POM metadata cho artifact. **Không chỉnh sửa trực tiếp** nội dung thư mục `.m2/repository` để tự đặt classifier: hãy sửa POM/plugin ở producer và build lại.

## 7. Consumer chọn đúng artifact bằng `type` hoặc `classifier`

Bên consumer muốn biên dịch một lớp trong `src/test/java` dùng `SampleFixture` đã đóng gói. Hai cách khai báo ở mục 4.1 cho cùng một đích; dưới đây dùng `type=test-jar` để thấy rõ cơ chế.

Tạo toàn bộ `consumer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.consumer</groupId>
    <artifactId>fixture-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>artifact-demo</artifactId>
            <version>1.0.0</version>
            <type>test-jar</type>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `consumer/src/test/java/dev/consumer/FixtureUse.java`:

~~~java
package dev.consumer;

import dev.example.SampleFixture;

public final class FixtureUse {
    private FixtureUse() {
    }

    public static String example() {
        return SampleFixture.sample();
    }
}
~~~

Sau khi producer đã **`install`**, vào thư mục `artifact-lab/consumer` và chạy:

~~~bash
mvn -B -ntp clean test-compile
~~~

Khi thành công, Maven biên dịch `FixtureUse.class` vào `target/test-classes`. Compiler thấy `dev.example.SampleFixture` nhờ dependency có `type=test-jar`, tức là file **`artifact-demo-1.0.0-tests.jar`** trong local repository. `scope=test` đưa nó vào classpath test, không vào classpath biên dịch mã ứng dụng trong `src/main/java`.

Nếu chuyển dependency thành:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
~~~

thì dependency vẫn chọn đúng biến thể `-tests.jar` (type mặc định `jar`). **Không cần khai báo cả hai** khi chúng tương đương; cấu hình tường minh `classifier=tests` thường rõ ý định hơn khi bạn chỉ muốn một JAR thông thường có nhãn `tests`.

**Thử sai có kiểm soát:** bỏ cả `<type>test-jar</type>` lẫn `<classifier>tests</classifier>`; khi đó dependency chọn **JAR chính** `artifact-demo-1.0.0.jar`, là file chỉ chứa `Greeting.class` theo ví dụ. `FixtureUse.java` sẽ không biên dịch được vì `SampleFixture` không có trên test classpath. Đây là bằng chứng `type/classifier` ảnh hưởng đến **file thực sự được chọn**.

### Giới hạn khi chia sẻ test JAR

JAR `tests` **không tự mang theo** các dependency mà producer khai báo ở `scope=test` như JUnit hoặc thư viện tạo dữ liệu test. Consumer phải khai báo các dependency cần thiết cho fixture của nó. Nếu tập fixture lớn và dùng lại dài hạn, thường nên tách thành một module/thư viện `test-support` riêng với source ở `src/main/java`, dependency được quản lý rõ ràng, thay vì chia sẻ test-jar của ứng dụng khác. Đây là điểm lưu ý quan trọng ngay cả khi `-tests.jar` được Maven tìm đúng.

## 8. BOM và trường hợp `type=pom`

Một **BOM** (*Bill of Materials*) là POM dùng để quản lý phiên bản dependency, không phải một JAR cung cấp class Java. POM producer thường có `<packaging>pom</packaging>`. Consumer nhập BOM tại `dependencyManagement` bằng **`type=pom`** và **`scope=import`**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **đoạn cấu hình minh họa** và chỉ chạy khi artifact BOM `dev.example:platform-bom:1.0.0` thực sự tồn tại trong repository. Khi Maven xử lý import, nó đọc phần quản lý dependency từ POM tương ứng; không thêm class nào từ BOM vào runtime classpath.

Thiếu `<type>pom</type>`, Maven sẽ mặc định `jar` và có thể tìm nhầm `platform-bom-1.0.0.jar` dù artifact thực tế chỉ có `.pom`. Thiếu `<scope>import</scope>` sẽ không đạt semantics nhập dependency management như mong muốn.

**Khác nhau giữa parent POM và BOM:** parent được khai báo trong `<parent>` và có cơ chế kế thừa model; BOM được đưa vào `dependencyManagement` với `type=pom` và `scope=import` để dùng tập phiên bản. Cả hai đều là POM, nhưng cách Maven xử lý khác nhau.

## 9. Artifact đính kèm: sources, javadoc và biến thể tùy biến

Cùng một producer có thể xuất bản artifact chính và thêm biến thể dùng cho mục đích khác:

| Mục đích | Plugin/goal thường dùng | Classifier | Extension |
| --- | --- | --- | --- |
| Bytecode chính | `maven-jar-plugin:jar` | không có | `jar` |
| Bytecode được biên dịch từ `src/test/java` | `maven-jar-plugin:test-jar` | `tests` | `jar` |
| Nguồn Java đóng gói | `maven-source-plugin:jar-no-fork` | `sources` | `jar` |
| Tài liệu API | `maven-javadoc-plugin:jar` | `javadoc` | `jar` |
| Bản phân phối tùy biến | Plugin đóng gói tương ứng | Do dự án quy định | Ví dụ `zip`, `tar.gz` |

Một artifact đính kèm dùng **cùng GAV**, nhưng có classifier và/hoặc extension khác để không va chạm với artifact chính. `-sources.jar` chứa `.java`, `-javadoc.jar` chứa tài liệu, không nên khai báo như dependency bytecode chỉ vì cả hai đều có extension `.jar`.

Không phải mọi plugin tự tạo attached artifact ở mỗi build: phải cấu hình goal/phase tương ứng và xác nhận có file sau `package`, `install` hoặc `deploy`. Một JAR tên `all`, `shaded` hoặc `exec` chỉ là tên nếu chưa xem plugin đã đóng gói những gì; classifier không bảo đảm archive là “fat JAR”.

### `finalName` không đổi tọa độ

Khai báo:

~~~xml
<build>
    <finalName>app</finalName>
</build>
~~~

có thể làm tên file **trong `target/`** thành `app.jar` (tùy plugin/packaging), nhưng GAV và tên lưu chính thức trong Maven repository sau `install/deploy` vẫn dựa trên `groupId`, `artifactId` và `version` cùng classifier/extension. Đừng thay `artifactId` trong consumer chỉ vì thấy `target/app.jar`.

## 10. Quan hệ với dependencyManagement, scope và dependency mediation

Ngoài GAV, loại và classifier của dependency còn quan trọng khi Maven quản lý dependency:

- `<dependencyManagement>` có thể quản lý version và các thuộc tính của dependency. Khi quản lý nhiều biến thể cùng group/artifact, cần dùng **type/classifier phù hợp** để mục quản lý khớp với dependency cần áp dụng.
- `<scope>` không chọn artifact `-tests.jar`; nó chọn classpath và giai đoạn dùng dependency sau khi artifact đã được xác định. `<scope>test</scope>` kết hợp với `type=test-jar` là cách thường gặp để dùng fixture test.
- `<optional>` ảnh hưởng cách dependency được truyền tiếp sang consumer, **không phải** phần mở rộng file.
- Resolver và dependency plugin có thể hiển thị các tọa độ theo nhiều thứ tự khi log, ví dụ `groupId:artifactId:type:version` hoặc `groupId:artifactId:type:classifier:version`. Đó là cách **biểu diễn tọa độ trong từng công cụ**, không phải chính định dạng của đường dẫn repository; đừng tự hoán đổi vị trí classifier và version theo cảm tính.

Ví dụ hai dependency cùng GAV có thể cùng nằm trong một POM nếu chúng là **biến thể khác**:

~~~xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>artifact-demo</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>artifact-demo</artifactId>
        <version>1.0.0</version>
        <classifier>tests</classifier>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dependency thứ nhất lấy JAR chính vào classpath phù hợp với scope mặc định `compile`; thứ hai lấy `-tests.jar` vào classpath test. Nếu copy-paste hai mục **trùng cả type và classifier**, Maven có thể cảnh báo dependency trùng, và cách chọn version/configuration trở nên khó đoán. Đừng dùng nhiều dependency trùng để giải quyết vấn đề version.

## 11. Cách kiểm chứng Maven thực sự chọn file nào

Không chỉ suy ra từ tên dependency trong `pom.xml`; hãy dùng kết quả build và metadata thực tế.

### 11.1. Trên producer

~~~bash
mvn -B -ntp clean install
jar tf target/artifact-demo-1.0.0.jar
jar tf target/artifact-demo-1.0.0-tests.jar
~~~

Nếu chỉ có JAR chính mà không có `-tests.jar`: kiểm tra goal `maven-jar-plugin:test-jar` có nằm trong `<executions>`, đã chạy đến `package` và thực sự có class ở `target/test-classes` chưa. Nếu `target/...-tests.jar` có nhưng consumer vẫn không tìm được, xác nhận đã `install` hoặc `deploy` artifact đính kèm.

### 11.2. Trên consumer

~~~bash
mvn -B -ntp test-compile
mvn -B -ntp dependency:tree
~~~

`dependency:tree` do Maven Dependency Plugin cung cấp, giúp quan sát artifact và scope Maven phân giải. Cách plugin hiển thị tọa độ phụ thuộc phiên bản; với `test-jar`, có thể thấy type `test-jar` và classifier `tests` trong biểu diễn. Lệnh `test-compile` là bằng chứng mạnh hơn cho ví dụ này vì compiler cần tìm được `SampleFixture.class`.

Để xem POM sau khi áp dụng parent, profile và dependency management, có thể dùng Maven Help Plugin:

~~~bash
mvn -B -ntp help:effective-pom
~~~

Thông tin ở effective POM có thể rất dài. Chỉ kiểm tra phần dependency và plugin liên quan đến artifact cần tìm; không nhầm `dependencyManagement` với một dependency đã được thêm vào classpath.

### 11.3. Khi dùng repository từ xa

Một artifact có GAV đúng nhưng classifier sai vẫn là một artifact **khác**. Nếu `artifact-demo-1.0.0.jar` đã deploy mà `artifact-demo-1.0.0-tests.jar` chưa deploy, consumer đòi `tests` vẫn lỗi. Kiểm tra tệp/metadata trên repository server và phiên bản mà CI thực sự xuất bản, không sửa `scope` với hy vọng Maven sẽ chọn file khác.

## 12. Lỗi thường gặp và hướng khắc phục

### Lỗi A — `Could not find artifact ...:jar:tests:1.0.0`

**Ý nghĩa:** Maven đã yêu cầu một biến thể có classifier `tests`, nhưng không tìm thấy tại repository được cấu hình. Điều này không đồng nghĩa với việc JAR chính không tồn tại.

**Kiểm tra:** `target/artifact-demo-1.0.0-tests.jar` có được tạo không? Producer đã chạy `install` hoặc `deploy` chưa? Consumer có đúng GAV và classifier không? Có đang dùng repository local khác hoặc mirror/proxy không? Maven có thể cache lần phân giải thất bại, cần xử lý đúng nguyên nhân trước khi thử cập nhật metadata theo chính sách nhóm.

### Lỗi B — Đổi `<type>test-jar</type>` thành `<type>jar</type>` rồi lớp test biến mất

**Nguyên nhân:** `type=jar` mặc định không suy ra classifier `tests`; Maven chuyển sang JAR chính.

**Khắc phục:** khai báo `<classifier>tests</classifier>` hoặc dùng `<type>test-jar</type>`. Chọn một cách nhất quán với artifact mà producer đã publish.

### Lỗi C — Viết `<type>tests</type>` để tìm `-tests.jar`

**Nguyên nhân:** `tests` là **classifier**, không phải type handler chuẩn. Khi type không được nhận diện, Maven có thể xem nó là phần mở rộng file `.tests`.

**Khắc phục:** sử dụng `<classifier>tests</classifier>` (type mặc định `jar`) hoặc `<type>test-jar</type>`.

### Lỗi D — Khai báo `<classifier>jar</classifier>` để lấy JAR chính

**Nguyên nhân:** `jar` là extension và là type, **không phải** classifier của JAR chính. Maven sẽ tìm biến thể `-jar.jar` nếu classifier được đặt thành `jar`.

**Khắc phục:** bỏ `<classifier>` và dùng `<type>jar</type>` hoặc bỏ `<type>` để lấy JAR chính.

### Lỗi E — BOM báo không tìm thấy `.jar`

**Nguyên nhân:** khai báo BOM như dependency JAR thông thường hoặc quên `<type>pom</type>` trong `dependencyManagement`.

**Khắc phục:** dùng `<type>pom</type>` và `<scope>import</scope>` trong `dependencyManagement`; bảo đảm BOM POM được xuất bản và có đúng tọa độ.

### Lỗi F — Thấy `artifactId-version.zip` nhưng đặt `<type>jar</type>`

**Nguyên nhân:** Maven tìm `.jar` vì type mặc định không biết ZIP.

**Khắc phục:** dùng `<type>zip</type>` nếu repository lưu artifact với extension đó và không có handler tùy biến ghi đè. Nếu ZIP có classifier, khai báo classifier khớp. Dependency ZIP không tự động được đưa vào Java classpath như JAR; cần plugin/goal phù hợp để giải nén hoặc xử lý.

### Lỗi G — Consumer dùng `-tests.jar` nhưng thiếu JUnit/test library

**Nguyên nhân:** test JAR có các class test, nhưng dependency `scope=test` từ producer không tự đi theo như dependency transitive cho consumer.

**Khắc phục:** consumer khai báo những test dependencies cần thiết, hoặc chuyển fixture được chia sẻ sang module test-support riêng với dependencies rõ ràng.

### Lỗi H — `finalName` đã đổi nhưng dependency vẫn tìm tên cũ

**Nguyên nhân:** `finalName` chủ yếu đổi tên file đầu ra trong `target/`; repository artifact được xác định theo tọa độ GAV/classifier/extension.

**Khắc phục:** đối chiếu vị trí dưới `~/.m2/repository` hoặc remote; dùng tọa độ dự án chứ không dùng tên tệp local.

### Lỗi I — Khai báo `packaging` bằng tên custom nhưng Maven không biết lifecycle

**Nguyên nhân:** `packaging` cần lifecycle mapping phù hợp. Đặt một chuỗi mới vào `<packaging>` không tự tạo plugin đóng gói và artifact handler tương ứng.

**Khắc phục:** dùng packaging được Maven/plugin hỗ trợ, hoặc cấu hình build extension và plugin theo tài liệu của công cụ tạo kiểu packaging đó. Không coi quy tắc fallback `type=extension` là bằng chứng packaging custom đã hoạt động.

## 13. Bài tập thực hành và câu hỏi tự kiểm tra

**Bài 1 — suy ra file được tải.** Giả sử GAV `dev.example:artifact-demo:1.0.0`. Điền tên file cho từng dependency:

| Khai báo trong dependency | File dự kiến |
| --- | --- |
| Không có `type`, `classifier` | `artifact-demo-1.0.0.jar` |
| `<classifier>tests</classifier>` | `artifact-demo-1.0.0-tests.jar` |
| `<type>test-jar</type>` | `artifact-demo-1.0.0-tests.jar` |
| `<type>java-source</type>` | `artifact-demo-1.0.0-sources.jar` |
| `<type>pom</type>` | `artifact-demo-1.0.0.pom` |
| `<type>zip</type><classifier>dist</classifier>` | `artifact-demo-1.0.0-dist.zip` |

**Bài 2 — dự án producer.** Tạo đúng ba tệp `pom.xml`, `Greeting.java` và `SampleFixture.java` ở mục 6. Chạy `mvn clean install` rồi so sánh đầu ra của `jar tf` trên JAR chính và JAR `tests`. Kiểm tra local repository. Trả lời: hai archive có chung GAV nhưng khác thành phần tọa độ nào?

**Bài 3 — dự án consumer.** Thêm `consumer/pom.xml` và `FixtureUse.java`. Chạy `mvn test-compile`. Sau đó thử bỏ `type=test-jar` để chỉ dùng JAR chính. Giải thích vì sao file `FixtureUse.java` không còn biên dịch được.

**Bài 4 — BOM.** Viết đúng hai phần tử `type` và `scope` để nhập BOM qua `dependencyManagement`. Trả lời vì sao BOM không nên được đưa như một JAR vào classpath Java.

**Bài 5 — phát hiện lỗi tọa độ.** Một dependency có `<type>test-jar</type>` nhưng trên repository chỉ thấy `lib-2.0.jar`. Có thể kết luận lỗi mạng ngay chưa? **Chưa**: trước hết cần xác định producer có xuất bản `lib-2.0-tests.jar` hay không. Nếu chưa, lỗi ở artifact/variant yêu cầu chứ không phải tự động do mạng.

**Câu hỏi nền tảng:**

- `packaging=jar` trong producer có cấm xuất bản source JAR/test JAR không? **Không.** Plugin có thể tạo artifact đính kèm.
- `scope=test` có tự tìm `-tests.jar` không? **Không.** Nó điều khiển classpath; `type/classifier` mới chọn biến thể.
- `type=test-jar` có nghĩa file `.test-jar` không? **Không.** Handler chọn `-tests.jar`.
- Có cần tự thêm `<extension>jar</extension>` vào `<dependency>` không? **Không.** POM dependency Maven dùng `type`; extension được suy ra.
- Có thể dùng `<classifier>sources</classifier>` để tải `-sources.jar` không? **Có**, nhưng đây thường không phải dependency bytecode cần cho trình biên dịch của ứng dụng.

## 14. Checklist khi khai báo hoặc xuất bản biến thể artifact

- [ ] Đã xác định **GAV** của artifact cần dùng.
- [ ] Đã hiểu bên sản xuất dùng `packaging` gì và có xuất bản attached artifact hay không.
- [ ] `type` trong dependency phù hợp với extension thực tế hoặc artifact handler.
- [ ] `classifier` được khai báo đúng hoặc được handler suy ra.
- [ ] Phân biệt rõ `scope` với lựa chọn classifier/extension.
- [ ] `package` đã tạo đúng archive; `install` hoặc `deploy` đã lưu cả biến thể cần tiêu thụ.
- [ ] Consumer lấy artifact từ repository đã cấu hình, không dựa vào tệp còn sót trong `target/` của producer.
- [ ] Các dependency dùng cho test JAR đã được khai báo đầy đủ ở consumer.
- [ ] Nếu dùng BOM, đã đặt `type=pom` và `scope=import` dưới `dependencyManagement`.
- [ ] Khi lỗi phân giải dependency, đã kiểm tra **toàn bộ GAV + type + classifier + extension** trước khi đổi phiên bản hoặc xóa cache.

## 15. Tài liệu chính thức

1. [Apache Maven — Artifacts and coordinates](https://maven.apache.org/repositories/artifacts.html): cơ chế suy ra extension/classifier từ `type` và artifact handler.
2. [Maven Core — Default Artifact Handlers](https://maven.apache.org/ref/3-LATEST/maven-core/artifact-handlers.html): bảng các loại artifact mặc định theo nhánh Maven.
3. [Apache Maven — Dependencies](https://maven.apache.org/repositories/dependencies): dependency type, classifier, scope và cách resolver chọn artifact.
4. [Apache Maven — POM Reference](https://maven.apache.org/pom.html): ý nghĩa `packaging`, `type`, `classifier` và `dependencyManagement`.
5. [Apache Maven — Guide to Using Attached Tests](https://maven.apache.org/guides/mini/guide-attached-tests.html): tạo và tiêu thụ test JAR.
6. [Apache Maven JAR Plugin — Create a Test JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/create-test-jar.html): ví dụ plugin `test-jar` và giới hạn dependency test truyền tiếp.
7. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phân biệt `compile`, `package`, `install`, `deploy`.
