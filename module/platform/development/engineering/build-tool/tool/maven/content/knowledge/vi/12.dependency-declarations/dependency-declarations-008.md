# Phụ thuộc có classifier và artifact kiểm thử được đính kèm trong Maven

## 1. Vì sao một dependency cần classifier?

Trong Apache Maven, một project thông thường tạo artifact chính, chẳng hạn `math-core-1.0.0.jar`. Tuy nhiên, cùng một phiên bản project có thể cần xuất bản **nhiều artifact liên quan**:

- JAR chính chứa mã ở `src/main/java`;
- JAR chứa các lớp và tài nguyên kiểm thử từ `src/test/java`;
- JAR mã nguồn, JAR Javadoc hoặc một bản đóng gói chuyên biệt cho một mục đích cụ thể.

Các artifact phụ được phân biệt bằng **classifier**. Một classifier là nhãn bổ sung vào tọa độ artifact, ví dụ `tests`, `sources` hoặc `javadoc`. Cùng `groupId`, `artifactId` và `version`, classifier cho Maven biết **cần biến thể nào**.

Ví dụ một project:

```text
groupId:    com.example
artifactId: math-core
version:    1.0.0

Artifact chính:
    math-core-1.0.0.jar

Artifact có classifier "tests":
    math-core-1.0.0-tests.jar
```

Hai file có **cùng project và cùng version**, nhưng **nội dung khác nhau**. Artifact có classifier `tests` không phải bản copy của JAR chính: trong cấu hình `jar:test-jar`, nó thường đóng gói các lớp đã biên dịch từ thư mục test.

**Mục tiêu bài học:** hiểu classifier trong `<dependency>`, tạo **attached test artifact** bằng Maven JAR Plugin, dùng artifact đó từ một module khác, và tránh nhầm lẫn giữa `test-jar` với `scope=test`.

## 2. Classifier, type, extension và scope: bốn điều khác nhau

Khai báo dependency thường gặp:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>math-core</artifactId>
    <version>1.0.0</version>
    <classifier>tests</classifier>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

Đây chỉ là **một đoạn trong `<dependencies>` của POM sử dụng**, chưa phải file POM hoàn chỉnh.

| Thành phần | Ý nghĩa trong ví dụ | Không được hiểu nhầm thành |
| --- | --- | --- |
| `groupId` | Nhóm phát hành `com.example` | Java package của mọi lớp trong JAR |
| `artifactId` | Tên project `math-core` | Tên riêng của artifact kiểm thử |
| `version` | Phiên bản `1.0.0` | Phiên bản JUnit hoặc Maven |
| `classifier` | Biến thể `tests` | Một Maven build profile |
| `type` | `test-jar`: kiểu dependency ánh xạ tới JAR classifier `tests` | Bằng chứng rằng test đã chạy |
| `scope` | `test`: chỉ có trong classpath phục vụ biên dịch/chạy test của project tiêu thụ | Thông tin về nội dung JAR |

Cần phân biệt hai câu:

- `<type>test-jar</type>` cho Maven biết **artifact phải tìm**; type này được Maven ánh xạ thành file **đuôi `.jar` có classifier `tests`**.
- `<scope>test</scope>` cho Maven biết **khi nào dependency có trên classpath của project đang dùng nó**. Scope không tạo file `-tests.jar` và cũng không chọn classifier.

Theo cơ chế dependency type của Maven, hai cách sau trỏ tới cùng một biến thể JAR nếu classifier mặc định của test-jar là `tests`:

```xml
<!-- Cách A: type test-jar suy ra classifier tests -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>math-core</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
```

```xml
<!-- Cách B: JAR thông thường nhưng chỉ rõ classifier -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>math-core</artifactId>
    <version>1.0.0</version>
    <type>jar</type>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
```

Trong thực tế tài liệu về **attached test JAR** thường ghi cả `<type>test-jar</type>` và `<classifier>tests</classifier>` để ý định được rõ ràng. Nếu publisher cố ý đặt classifier khác, consumer phải khai báo đúng classifier thực tế, không mặc định `tests`.

## 3. Attached test JAR là gì?

Maven Java project theo quy ước có hai thư mục:

```text
src/main/java/  -> target/classes/       -> JAR chính
src/test/java/  -> target/test-classes/  -> test JAR đính kèm nếu cấu hình
```

Trong Maven JAR Plugin, goal **`jar:test-jar`** tạo một JAR từ **lớp test đã biên dịch và tài nguyên test**. Theo cấu hình mặc định của goal này:

- nguồn đóng gói: `${project.build.testOutputDirectory}`, thường là `target/test-classes`;
- classifier: `tests`;
- phase liên kết mặc định: `package`;
- output nằm trong `${project.build.directory}`, thường là `target`;
- artifact được **attach** vào Maven project theo mặc định.

*Attach* nghĩa là Maven đăng ký JAR phụ như một artifact bổ sung của **cùng Maven project**. Khi project được `install` hoặc `deploy` hợp lệ, artifact phụ cũng có thể được cài lên kho cục bộ hoặc xuất bản lên repository cùng artifact chính.

Ví dụ project `com.example:math-core:1.0.0` sau `mvn package` có thể sinh:

```text
math-core/target/math-core-1.0.0.jar
math-core/target/math-core-1.0.0-tests.jar
```

File thứ nhất chứa mã ứng dụng; file thứ hai chứa các lớp/tài nguyên test được Maven đóng gói. **Tạo test JAR không đồng nghĩa chạy những bài test bên trong JAR trên project khác**. Nếu muốn thực thi test của dependency, cần cấu hình test runner riêng; phần thực hành ở dưới dùng test JAR như **thư viện fixture/helper** cho test của consumer.

## 4. Khai báo Maven JAR Plugin để attach test artifact

Trong POM của module **phát hành** (producer), khai báo một execution cho goal `test-jar`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.5.1</version>
            <executions>
                <execution>
                    <id>attach-tests</id>
                    <goals>
                        <goal>test-jar</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn cấu hình** đặt bên trong `<project>`, không phải file `pom.xml` độc lập.

Tại sao cấu hình này hoạt động?

1. `<executions><execution>` khai báo Maven phải gọi goal `test-jar` trong lifecycle.
2. Goal `jar:test-jar` gắn với phase `package` theo mặc định, nên không bắt buộc thêm `<phase>package</phase>`.
3. Khi chạy đến `package`, Maven đã đi qua `test-compile`; vì thế test class đã được biên dịch vào `target/test-classes` nếu không có lỗi trước đó.
4. JAR Plugin sử dụng classifier mặc định `tests` và attach file JAR mới vào project.
5. Với packaging `jar` thông thường, Maven cũng tạo JAR chính thông qua goal `jar:jar` của default lifecycle.

Có thể thêm `<phase>package</phase>` tường minh cho dễ đọc; kết quả cơ bản tương đương. Tránh gọi trực tiếp `mvn jar:test-jar` trên một project chưa biên dịch test nếu muốn sản phẩm đầy đủ: goal trực tiếp không thay thế việc đi qua chuỗi lifecycle thích hợp.

**Không thêm một JAR Plugin execution không có classifier để đóng gói cùng nội dung với JAR mặc định** nếu mục tiêu chỉ là attach test classes. Attached artifact cần được phân biệt, còn `jar:test-jar` đã cung cấp classifier `tests` theo mặc định.

## 5. Bài thực hành Java 17: producer cung cấp fixture, consumer sử dụng

Ta tạo một project đa module:

- `math-core` có mã sản phẩm `MathOps` và một helper kiểm thử `MathFixtures` trong `src/test/java`.
- `math-consumer` dùng JAR chính của `math-core` khi biên dịch code ứng dụng, đồng thời dùng `math-core-1.0.0-tests.jar` và JUnit 5 trong bài test của chính consumer.

Kết quả sẽ cho thấy **một project có thể vừa phụ thuộc JAR chính vừa phụ thuộc test JAR của cùng artifact**.

### 5.1. Cây thư mục đầy đủ

```text
attached-tests-demo/
├── pom.xml
├── math-core/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   └── java/com/example/math/MathOps.java
│       └── test/
│           └── java/com/example/math/MathFixtures.java
└── math-consumer/
    ├── pom.xml
    └── src/
        ├── main/
        │   └── java/com/example/consumer/App.java
        └── test/
            └── java/com/example/consumer/MathConsumerTest.java
```

Các đường dẫn `java/com/example/...` trong cây là cách rút gọn của đường dẫn package chuẩn: file thực tế phải nằm đúng `src/main/java/com/example/...` hoặc `src/test/java/com/example/...`.

### 5.2. File gốc attached-tests-demo/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>attached-tests-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>math-core</module>
        <module>math-consumer</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.5.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

File gốc là **aggregator và parent POM**. `<modules>` cho reactor biết module nào cần build; `<pluginManagement>` chốt phiên bản plugin dùng bởi các module nhưng **không tự tạo execution attach test JAR**. Execution sẽ được khai báo trong `math-core`.

### 5.3. File math-core/pom.xml — phát hành cả hai JAR

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>attached-tests-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>math-core</artifactId>
    <packaging>jar</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <executions>
                    <execution>
                        <id>attach-tests</id>
                        <goals>
                            <goal>test-jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM con**. Nó kế thừa `groupId/version` và cấu hình plugin management từ POM gốc. Goal `test-jar` sinh attached artifact khi module hoàn tất `package`. Version của JAR Plugin đến từ `pluginManagement` của parent.

**Chú ý khi tạo file thực tế:** phần `xsi:schemaLocation` của POM này phải gồm **namespace URI** làm phần đầu, giống POM gốc. Cách viết đúng là `http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd`. Giữ nguyên cặp giá trị đúng như ở POM gốc để trình chỉnh sửa XML và các công cụ schema nhận diện chính xác.

### 5.4. File math-core/src/main/java/com/example/math/MathOps.java

```java
package com.example.math;

public final class MathOps {
    private MathOps() {
    }

    public static int doubleValue(int value) {
        return value * 2;
    }
}
```

`MathOps` là **mã sản phẩm**. Lớp này được biên dịch vào `math-core/target/classes` và đóng gói trong JAR chính `math-core-1.0.0.jar`.

### 5.5. File math-core/src/test/java/com/example/math/MathFixtures.java

```java
package com.example.math;

public final class MathFixtures {
    private MathFixtures() {
    }

    public static int expectedDoubleOf(int value) {
        return value + value;
    }
}
```

`MathFixtures` là một **test helper/fixture**, không phải JUnit test tự chạy. Nó nằm trong `src/test/java` của producer, vì vậy Maven biên dịch vào `target/test-classes`. Khi chạy `jar:test-jar`, file `MathFixtures.class` được đưa vào JAR `-tests.jar`.

Ví dụ cố ý chỉ dùng thư viện chuẩn Java trong fixture, để dễ hiểu cấu trúc và không thêm dependency chỉ dành cho test của producer. Trong dự án thực, helper có thể phụ thuộc JUnit, AssertJ hoặc Mockito; khi đó consumer phải quản lý dependency cần thiết rõ ràng (xem mục 8).

### 5.6. File math-consumer/pom.xml — dùng JAR chính và test JAR

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>attached-tests-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>math-consumer</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>math-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.example</groupId>
            <artifactId>math-core</artifactId>
            <version>1.0.0</version>
            <type>test-jar</type>
            <classifier>tests</classifier>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Điểm quan trọng ở đây là **hai dependency cùng `groupId/artifactId/version` nhưng khác biến thể**:

- Dependency đầu không có classifier và có scope mặc định `compile`: cung cấp `MathOps` cho mã chính và test của consumer.
- Dependency thứ hai chọn **classifier `tests`**, type `test-jar`, scope `test`: cung cấp `MathFixtures` chỉ cho việc compile/chạy test của consumer.
- Dependency `junit-jupiter` cung cấp JUnit 5 để viết và thực thi `MathConsumerTest`. Vì JUnit là dependency được source test của consumer trực tiếp sử dụng, nên khai báo trực tiếp là phù hợp.

**Không thay dependency chính bằng chỉ một dependency test-jar** nếu mã `src/main/java` của consumer còn cần dùng `MathOps`: JAR `-tests.jar` không phải bản đóng gói đầy đủ các lớp `src/main/java`.

### 5.7. File math-consumer/src/main/java/com/example/consumer/App.java

```java
package com.example.consumer;

import com.example.math.MathOps;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Double 7 = " + MathOps.doubleValue(7));
    }
}
```

`App.java` sử dụng **JAR chính** của `math-core`. Việc biên dịch mã chính không cần `MathFixtures`, đúng với việc dependency test-jar chỉ có `scope=test`.

### 5.8. File math-consumer/src/test/java/com/example/consumer/MathConsumerTest.java

```java
package com.example.consumer;

import com.example.math.MathFixtures;
import com.example.math.MathOps;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MathConsumerTest {
    @Test
    void comparesAgainstSharedFixture() {
        int input = 7;
        assertEquals(
            MathFixtures.expectedDoubleOf(input),
            MathOps.doubleValue(input)
        );
    }
}
```

Test này sử dụng:
- `MathFixtures` từ **attached test JAR** của producer;
- `MathOps` từ **JAR chính** của producer;
- `@Test` và `assertEquals` từ **JUnit 5**, dependency riêng của consumer.

Khi Surefire chạy `MathConsumerTest`, phép so sánh là `14 == 14` và test thành công. Không có lệnh `System.out.println` trong bài test; đừng tự suy ra nó in `14` ra stdout.

### 5.9. Chạy Maven và xác nhận artifact

Tại **thư mục gốc `attached-tests-demo`**:

```bash
mvn -version
mvn -B -ntp clean verify
```

Maven dùng **reactor** để xây dựng parent và hai module theo phụ thuộc thực tế. `math-core` được build trước `math-consumer`, bao gồm phase `package` nơi test JAR được attach. `math-consumer` sau đó resolve dependency `tests` và thực hiện test của chính nó.

Nếu build thành công, các file cần kiểm tra bao gồm:

```text
math-core/target/math-core-1.0.0.jar
math-core/target/math-core-1.0.0-tests.jar
math-consumer/target/math-consumer-1.0.0.jar
math-consumer/target/surefire-reports/
```

Kiểm tra **nội dung JAR** bằng lệnh `jar` đi kèm JDK:

```bash
jar tf math-core/target/math-core-1.0.0.jar
jar tf math-core/target/math-core-1.0.0-tests.jar
```

Ở JAR chính cần có `com/example/math/MathOps.class`. Trong test JAR cần có `com/example/math/MathFixtures.class`. Các tệp manifest/metadata khác có thể xuất hiện; không dự đoán toàn bộ danh sách.

Chạy ứng dụng từ thư mục gốc trên Linux/macOS:

```bash
java -cp "math-consumer/target/classes:math-core/target/classes" com.example.consumer.App
```

**Stdout chính xác** của lệnh `java`:

```text
Double 7 = 14
```

Trên Windows PowerShell, dấu phân cách classpath là **dấu chấm phẩy**, không phải dấu hai chấm:

```powershell
java -cp "math-consumer\target\classes;math-core\target\classes" com.example.consumer.App
```

Vì ví dụ không khai báo `Main-Class` trong manifest và `math-consumer` còn phụ thuộc `math-core`, **không** tự giả định `java -jar math-consumer/target/math-consumer-1.0.0.jar` chạy được một mình. Chạy bằng classpath phù hợp hoặc cấu hình phân phối ứng dụng là bước riêng.

## 6. Điểm mấu chốt về vòng đời: test-jar được attach ở package

Goal `jar:test-jar` gắn với phase **`package`** mặc định. Từ đó có hệ quả:

```text
test-compile -> test -> package
                         |
                         +--> jar:jar (JAR chính)
                         +--> jar:test-jar (JAR classifier tests)
```

Đây là **sơ đồ rút gọn**, bỏ qua nhiều phase trung gian. Mục đích là thấy rằng sau `test-compile` Maven mới có lớp test, nhưng **attached test JAR thường chưa sẵn sàng cho tới phase `package`**.

| Lệnh | Kết quả nên mong đợi |
| --- | --- |
| `mvn test` trong producer | Biên dịch và chạy test; **chưa bắt buộc tạo `-tests.jar`** |
| `mvn package` trong producer | Đi qua các bước trước, tạo JAR chính và test JAR nếu plugin đã cấu hình |
| `mvn install` trong producer | Tạo cả hai JAR và cài vào local repository |
| `mvn deploy` trong producer | Tạo và có thể xuất bản các attached artifact lên remote repository nếu cấu hình/credentials hợp lệ |
| `mvn clean verify` tại reactor gốc | Producer đi qua package, sau đó consumer có thể dùng artifact đính kèm |
| `mvn -pl math-consumer -am verify` | Chọn consumer và những module cần thiết, build đến verify để producer có test JAR |

Một lỗi dễ gặp là chạy từ root:

```bash
mvn -pl math-consumer -am test
```

Lệnh trên **có thể thất bại khi cần artifact `tests`**: reactor mới đi đến `test` cho producer, nhưng execution `test-jar` được gắn ở `package`, chưa chạy. Khi consumer cần classifier artifact, Maven không có file attached tương ứng. Để xây dựng cả producer và consumer theo cấu hình này, dùng `package`/`verify` hoặc `install` tùy mục đích.

**Lưu ý:** nếu đã cài test JAR ở local repository từ lần build trước thì kết quả có thể khác, nên với chẩn đoán hãy chạy từ môi trường sạch và xem đúng artifact/version đang được resolve. Không nên dựa vào cache cũ để chứng minh một reactor configuration đúng.

## 7. Cài đặt và sử dụng ở một project khác

Nếu consumer là một repository khác, không cùng reactor, phải bảo đảm producer **đã phát hành artifact** ở nơi consumer resolve được.

Cách đơn giản trên cùng máy: từ module producer chạy:

```bash
mvn -f math-core/pom.xml -B -ntp clean install
```

Sau khi thành công, hai artifact thường xuất hiện trong Maven local repository:

```text
~/.m2/repository/com/example/math-core/1.0.0/
    math-core-1.0.0.jar
    math-core-1.0.0-tests.jar
    math-core-1.0.0.pom
```

Đây là đường dẫn mặc định **thông thường** của local repository. Nếu người dùng cấu hình `settings.xml` hoặc `-Dmaven.repo.local` thì vị trí khác; nếu Maven Resolver dùng cấu trúc lưu trữ tùy chỉnh thì không nên thao tác thủ công dựa vào bố cục này.

Có thể thử consumer độc lập:

```bash
mvn -f math-consumer/pom.xml -B -ntp clean verify
```

Vì producer đã được `install` trước, consumer có thể resolve cả JAR chính lẫn test JAR cùng version. Việc cài parent POM riêng cũng có thể cần thiết trong các mô hình khác, nhưng trong ví dụ này parent vẫn có thể được tìm qua `../pom.xml` khi các thư mục còn nguyên.

Để dùng trên máy CI khác, cần **deploy** producer lên repository từ xa và bảo đảm cả artifact classifier được lưu/chia sẻ có quyền truy cập. Chỉ có file test JAR trong `target` của máy producer **không đủ** cho một project khác tự tải bằng Maven.

Nếu Maven báo thiếu `math-core:jar:tests:1.0.0`, đừng tự sửa tên JAR trong `target` bằng tay. Kiểm tra producer đã attach, đã install/deploy phiên bản đó, và consumer dùng đúng classifier/type/version.

## 8. Giới hạn quan trọng: test dependency không tự được truyền theo test JAR

Giả sử `src/test/java` của producer dùng JUnit, AssertJ hoặc Mockito. Producer có thể có các dependency này với `<scope>test</scope>`.

Khi consumer phụ thuộc vào artifact `math-core-1.0.0-tests.jar`, các dependency chỉ dành cho test của producer **không tự động được kéo qua đầy đủ như một tập transitive test dependencies**. Maven hạn chế tính bắc cầu của scope `test`. Đó là hạn chế được Apache Maven nêu rõ khi hướng dẫn dùng attached test JAR.

Hệ quả:

- Consumer cần khai báo trực tiếp thư viện mà test/helper của nó sử dụng; ví dụ `org.junit.jupiter:junit-jupiter`.
- Nếu helper công khai từ producer có chữ ký chứa kiểu của một thư viện chỉ scope test, consumer cũng phải cung cấp thư viện cần thiết để compile/test.
- `jar:test-jar` chỉ đóng gói **lớp/tài nguyên test**, không đóng gói JUnit/Mockito vào JAR và không thay thế dependency management.
- Phiên bản của các thư viện test phải được quản lý rõ ràng để tránh xung đột classpath.

Trong ví dụ mục 5, `MathFixtures` không phụ thuộc JUnit hay Mockito, nên consumer chỉ phải thêm JUnit để **chạy bài test do chính consumer viết**, và không cần thư viện phụ nào để gọi fixture.

### Khi nào nên tạo module test-support riêng?

Nếu rất nhiều module phụ thuộc vào những helper kiểm thử có dependency phức tạp, một **module riêng cho test utilities** thường dễ duy trì hơn:

```text
math-test-support/
└── src/main/java/com/example/testing/MathFixtures.java
```

Khi đó:
- Helper được biên dịch như **mã chính của module test-support**;
- Những thư viện bắt buộc để helper hoạt động có thể được khai báo ở scope phù hợp của module này;
- Consumer dùng module test-support với `<scope>test</scope>` thông thường.

Đây cũng là hướng được tài liệu chính thức Maven gợi ý khi muốn tái sử dụng test classes mà vẫn quản lý được các dependency bắc cầu một cách đúng đắn. **Trade-off:** tăng thêm một Maven module/artifact nhưng làm ranh giới dependency rõ hơn.

## 9. Classifier tùy chỉnh và attached artifact khác

Classifier `tests` là mặc định cho goal `jar:test-jar`, nhưng có thể đổi classifier trong cấu hình goal:

```xml
<execution>
    <id>attach-test-fixtures</id>
    <goals>
        <goal>test-jar</goal>
    </goals>
    <configuration>
        <classifier>test-fixtures</classifier>
    </configuration>
</execution>
```

Đây là **đoạn execution** để đặt trong Maven JAR Plugin của producer, không phải một file POM độc lập. Nếu dùng cấu hình này thay cho execution `attach-tests`, tên JAR phụ có thể là `math-core-1.0.0-test-fixtures.jar`. Consumer phải trỏ tới đúng biến thể:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>math-core</artifactId>
    <version>1.0.0</version>
    <type>jar</type>
    <classifier>test-fixtures</classifier>
    <scope>test</scope>
</dependency>
```

Ở đây dùng `type=jar` với classifier tường minh để thể hiện chính xác biến thể tùy chỉnh. **Không giữ classifier mặc định `tests` trong consumer nếu producer đã đổi thành `test-fixtures`.**

Với artifact phụ không phải test classes, Maven JAR Plugin còn có thể attach JAR khác bằng goal `jar:jar` cùng một execution riêng và classifier như `client`. Đừng tùy tiện thay goal `test-jar` bằng `jar` nếu bạn thật sự muốn đóng gói `target/test-classes`: hai goal có nguồn file mặc định khác nhau.

Một classifier **không phải**:
- một Maven profile (không bật bằng `-Ptests` trừ khi dự án tự khai báo profile ID đó);
- một dependency scope;
- một file extension;
- một version mới;
- một classifier mặc định do Maven tự tạo cho mọi project.

Để artifact classifier tồn tại, **producer phải thật sự tạo và attach/publish nó**. Chỉ ghi `<classifier>tests</classifier>` trong consumer không khiến producer sinh JAR tương ứng.

## 10. Quản lý version khi có classifier

Khi dùng `dependencyManagement`, Maven nhận diện biến thể dependency bằng tổ hợp gồm `groupId`, `artifactId`, `type` và `classifier`. Vì thế một khai báo quản lý dành cho JAR chính không nhất thiết quản lý đúng biến thể test JAR.

Ví dụ **đoạn XML** trong parent POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>math-core</artifactId>
            <version>1.0.0</version>
            <type>test-jar</type>
            <classifier>tests</classifier>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau khi có quản lý phiên bản phù hợp, consumer có thể khai báo test-jar mà không lặp version:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>math-core</artifactId>
    <type>test-jar</type>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
```

**Các đoạn này chỉ minh họa dependency management**, không tự thêm dependency vào consumer và không tự tạo attached test artifact ở producer. Test JAR vẫn phải được phát hành bằng plugin/lifecycle phù hợp.

## 11. Test JAR có tự làm test runner quét và chạy những test đã đóng gói không?

**Không nên giả định như vậy.** Với cấu hình Maven Surefire thông thường, plugin tập trung tìm test trong output test classes của **project đang chạy**. Một dependency JAR có thể nằm trên test classpath nhưng các class chứa `@Test` bên trong nó không mặc nhiên được phát hiện và chạy như test của consumer.

Khi thực sự muốn consumer **chạy các test nằm trong dependency test JAR**, Maven Surefire hỗ trợ tham số `dependenciesToScan` (phiên bản và cú pháp cần đối chiếu với Surefire đang dùng):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <dependenciesToScan>
            <dependency>com.example:math-core:test-jar:tests</dependency>
        </dependenciesToScan>
    </configuration>
</plugin>
```

Đây là **đoạn plugin** để bổ sung trong `<build><plugins>` của consumer nếu mục tiêu có thay đổi sang quét test trong dependency. Đừng chèn thêm nguyên một `<build>` lặp vào cùng POM.

Trong ví dụ chạy được ở mục 5, ta **không cần `dependenciesToScan`** vì `MathFixtures` chỉ là helper, còn `MathConsumerTest` là bài test nằm ở `src/test/java` của consumer và được Surefire tự phát hiện.

## 12. Những lỗi phổ biến và cách điều tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Could not find artifact ...:jar:tests:...` | Producer chưa attach/publish `-tests.jar`, version hoặc classifier sai | Kiểm tra execution `jar:test-jar`, chạy `package/install`, xem tên file và local/remote repo |
| Producer có `target/test-classes` nhưng không có `-tests.jar` | Đã chạy `test` nhưng chưa tới `package`, hoặc chưa khai báo `test-jar` | Chạy `mvn package` với plugin execution đúng |
| Consumer import được `MathOps` nhưng không thấy `MathFixtures` | Consumer chỉ phụ thuộc JAR chính, chưa thêm classifier `tests` | Thêm dependency test-jar scope test đúng tọa độ |
| Consumer thấy `MathFixtures` nhưng `src/main/java` không import được | Dependency test-jar đặt `scope=test` | Đây là ranh giới classpath đúng: test fixture không dành cho source chính |
| Consumer không thấy `MathOps` khi chỉ thêm test-jar | Test JAR không chứa mã `src/main/java` | Thêm dependency JAR chính nếu code cần nó |
| `mvn -pl math-consumer -am test` thất bại | Test JAR attach ở `package` nhưng reactor mới chạy tới `test` | Dùng `-am verify/package`, hoặc cài artifact từ producer trước |
| Test helper thiếu JUnit/Mockito khi consumer biên dịch test | Scope `test` của producer không tự được truyền đủ qua test JAR | Khai báo dependency test cần thiết ở consumer |
| Test class trong attached JAR không được chạy | Surefire không mặc định scan toàn bộ dependency JAR | Cân nhắc `dependenciesToScan` nếu thực sự cần chạy lại test đó |
| Consumer resolve JAR classifier cũ | Local repository có phiên bản đã install từ trước, version trùng nhưng output khác | Kiểm tra reactor, artifact timestamp/hash và quy trình versioning; tránh tái phát hành release khác nội dung |
| JAR phụ có classifier tùy chỉnh nhưng consumer dùng `tests` | Classifier giữa producer/consumer không khớp | Dùng đúng classifier ở cả hai phía |
| Test JAR rỗng | Không có lớp test/resources phù hợp hoặc đã bỏ bước compile test | Kiểm tra `src/test/java`, `target/test-classes`, cấu hình skip và `jar:test-jar` |
| Bật `-Dmaven.test.skip=true` rồi thiếu test JAR | Test compile/test-jar có thể bị skip | Tránh bỏ test compilation khi cần đóng gói fixture |
| `mvn deploy` không xuất bản JAR phụ | Artifact không được attach, hoặc lỗi cấu hình/permission deploy | Kiểm tra artifact attached trong build và repository đích |

**Quy trình chẩn đoán:**

1. Kiểm tra POM producer đã có `maven-jar-plugin` với goal `test-jar` trong `executions` chưa.
2. Chạy build producer tới ít nhất `package`; tìm `target/<artifactId>-<version>-tests.jar`.
3. Dùng `jar tf` để kiểm tra file chứa đúng `.class` và test resources mong muốn.
4. Kiểm tra dependency consumer có đúng `groupId/artifactId/version/classifier/type/scope`.
5. Nếu build reactor, kiểm tra phase gọi có đến `package` cho producer trước khi consumer cần attached JAR.
6. Nếu có lỗi classpath, xem dependency tree bằng `mvn dependency:tree` và rà soát các dependency scope test cần khai báo trực tiếp.
7. Khi đã sửa, chạy `mvn -B -ntp clean verify`, kiểm tra exit code, Surefire reports và không lẫn log Maven với stdout chương trình.

## 13. Bài tập tự kiểm tra

1. Với project `com.example:math-core:1.0.0`, JAR chính và JAR classifier `tests` có tên file gì?
2. `<classifier>tests</classifier>` và `<scope>test</scope>` quyết định hai điều khác nhau như thế nào?
3. Vì sao một module có `target/test-classes` nhưng chưa chắc có `math-core-1.0.0-tests.jar`?
4. Cấu hình plugin nào cần thêm để Maven attach test classes vào một artifact phụ ở phase `package`?
5. Nếu `math-consumer` muốn gọi `MathOps` trong source chính và `MathFixtures` trong test, nó cần những dependency nào?
6. `<type>test-jar</type>` được Maven ánh xạ tới extension và classifier nào theo mặc định?
7. Vì sao khi producer có dependency Mockito scope test, consumer không nên trông chờ test JAR mang đủ dependency transitive?
8. Tại sao `mvn -pl math-consumer -am test` có thể thất bại dù `mvn -pl math-consumer -am verify` thành công?
9. Vì sao thêm test JAR vào `<dependencies>` không có nghĩa Surefire sẽ chạy mọi test nằm trong JAR đó?
10. Nếu helper được tái sử dụng rộng rãi và có nhiều dependency, module `math-test-support` riêng có ưu điểm gì?

**Kết luận:** Classifier giúp Maven phân biệt **nhiều artifact thuộc cùng project/version**. Với test classes, producer dùng `maven-jar-plugin` và goal `test-jar` để tạo artifact **`-tests.jar` đính kèm** tại phase `package`; consumer sử dụng nó qua dependency có classifier `tests` (thường kèm type `test-jar`) và scope `test`. Phải phân biệt **chọn artifact**, **phạm vi classpath**, **thời điểm artifact được tạo**, và **các dependency test không tự lan truyền đầy đủ**.

## Tài liệu Apache Maven chính thức

- [Maven JAR Plugin — How to create a JAR containing test classes](https://maven.apache.org/plugins/maven-jar-plugin/examples/create-test-jar.html)
- [Maven JAR Plugin — jar:test-jar goal và tham số classifier/phase](https://maven.apache.org/plugins/maven-jar-plugin/test-jar-mojo.html)
- [Apache Maven — Guide to using attached tests](https://maven.apache.org/guides/mini/guide-attached-tests.html)
- [Apache Maven — Dependency types, classifiers và test-jar mapping](https://maven.apache.org/repositories/dependencies)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
