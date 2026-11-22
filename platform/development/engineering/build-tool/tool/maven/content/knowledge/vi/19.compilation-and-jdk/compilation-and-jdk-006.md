# Chọn bộ công cụ cho biên dịch, kiểm thử và công cụ liên quan bằng Maven Toolchains

## 1. Bài toán: cùng một build có thể cần nhiều JDK

Khi một máy có nhiều bản Java Development Kit (JDK), lệnh `mvn -version` cho biết **JDK đang dùng để chạy chính tiến trình Maven**, nhưng chưa đủ để kết luận trình biên dịch `javac`, tiến trình kiểm thử hay công cụ tạo Javadoc sẽ dùng cùng bản JDK.

Ví dụ một hệ thống thực tế có thể cần:
- Maven được khởi động trên **JDK 21** vì bộ công cụ build của máy/CI dùng JDK đó;
- mã nguồn ứng dụng được biên dịch bằng **JDK 17**, với `--release 17`;
- các unit test chạy trên **JDK 17** để kiểm tra tương thích của runtime dự định;
- một lượt thử tương thích khác chạy test bằng **JDK 21** dù mã nguồn vẫn biên dịch với target Java 17;
- Maven Javadoc Plugin hoặc Maven Jarsigner Plugin sử dụng công cụ `javadoc`/`jarsigner` từ bộ JDK được chọn.

Nếu chỉ đổi `JAVA_HOME` cho cả máy, bạn sẽ thay môi trường chạy Maven và có thể ảnh hưởng nhiều công cụ. **Maven Toolchains** cho phép dự án khai báo **yêu cầu về bộ công cụ**, còn môi trường build cung cấp đường dẫn JDK đáp ứng yêu cầu. Các plugin có hỗ trợ toolchain sẽ lấy toolchain đã chọn trong build context, tách việc chọn compiler/test JVM khỏi JDK khởi động Maven.

**Mục tiêu của bài:** hiểu JDK toolchain, cấu hình `toolchains.xml` và Maven Toolchains Plugin, dùng cùng toolchain cho Compiler Plugin/Surefire/Javadoc và biết cách override JDK riêng từng plugin khi cần. Nội dung nằm trong nhóm **Biên dịch và JDK**, tập trung vào việc chọn công cụ nhất quán chứ không thay thế toàn bộ kiến thức về lifecycle hoặc dependency.

## 2. Phân biệt bốn lớp JDK/Java

| Lớp | Công cụ/cấu hình thường dùng | Ý nghĩa |
| --- | --- | --- |
| **JDK chạy Maven** | `JAVA_HOME`, `mvn -version`, Maven Wrapper | JVM khởi động Maven và các plugin chạy trong Maven process |
| **JDK biên dịch** | Maven Compiler Plugin, `javac`, JDK toolchain | JDK thực hiện biên dịch `src/main/java` và `src/test/java` |
| **Java release mục tiêu** | `maven.compiler.release` hoặc `<release>` | Mức cú pháp/API/class file được yêu cầu cho code đã biên dịch |
| **JVM chạy test** | Maven Surefire Plugin hoặc Failsafe Plugin, forked JVM, toolchain | JVM thực thi unit/integration tests |
| **Các JDK tool khác** | Maven Javadoc/Jarsigner Plugin và plugin toolchain-aware | `javadoc`, `jarsigner` hoặc công cụ được plugin yêu cầu |

**Ba nhầm lẫn quan trọng:**

1. `mvn -version` in `Java version: 21` **không loại trừ** Compiler Plugin đang dùng `javac` của JDK 17 qua toolchain.
2. `<maven.compiler.release>17</maven.compiler.release>` **không tự lựa chọn JDK 17**. Nếu Maven chạy bằng JDK 21 và không cấu hình toolchain, compiler có thể dùng trình biên dịch của JDK 21 nhưng phát ra bytecode/API target Java 17. Điều đó khác việc chạy compiler của chính JDK 17.
3. Biên dịch bằng JDK 17 **không chứng minh test chạy trên JDK 17**. Surefire có thể fork JVM khác tùy session toolchain, `<jdkToolchain>`, `<jvm>` và cấu hình forking.

Maven Toolchains là cơ chế **phối hợp giữa Maven và plugin hỗ trợ**. Nó không thay đổi JDK của tiến trình Maven đã khởi chạy, không tự thay biến `JAVA_HOME` toàn hệ thống và cũng không ép mọi plugin bên thứ ba phải hỗ trợ toolchain.

## 3. Mô hình làm việc của Maven Toolchains

Với kiểu toolchain `jdk`, ta có hai phía:

- **Phía máy build:** khai báo các JDK đã cài trong `${user.home}/.m2/toolchains.xml`. File chứa những entry `<toolchain>`: `<type>jdk</type>`, các thuộc tính trong `<provides>` và đường dẫn `<configuration><jdkHome>`.
- **Phía project:** POM dùng `maven-toolchains-plugin` để yêu cầu JDK đáp ứng phiên bản/vendor; plugin chọn toolchain và đưa vào **Maven build context**. Compiler/Surefire/Javadoc và các plugin có hỗ trợ có thể sử dụng toolchain đó.

Sơ đồ khái niệm:

```text
Maven process (có thể chạy bằng JDK 21)
            |
            | đọc project POM và toolchains.xml
            v
maven-toolchains-plugin:toolchain
            |
            | chọn jdk toolchain đáp ứng yêu cầu
            v
Build context: JDK 17
      |              |                 |
      v              v                 v
compiler          surefire          javadoc
(javac 17)        (test JVM 17)     (javadoc 17)
```

Đây là sơ đồ ở mức khái niệm. Một số plugin có thể có tham số **`jdkToolchain` riêng** để chọn phiên bản khác với toolchain chung; một số plugin không hỗ trợ toolchain thì vẫn dùng JDK của Maven hoặc một executable đã cấu hình tường minh.

### Những plugin có hỗ trợ JDK toolchain

Tài liệu Apache Maven liệt kê, trong những plugin có hỗ trợ toolchain loại `jdk`, có:
- Maven Compiler Plugin: compiler biên dịch nguồn Java;
- Maven Surefire Plugin: JVM chạy unit tests;
- Maven Javadoc Plugin: công cụ tạo Java API documentation;
- Maven Jarsigner Plugin: công cụ ký JAR;
- Maven PMD Plugin trong những phiên bản có hỗ trợ tương ứng.

Việc hỗ trợ **phụ thuộc phiên bản plugin**. Không suy mọi bản cũ của Surefire/Javadoc đều có cùng tham số hoặc hành vi với bản hiện hành. Đối với plugin khác (đặc biệt plugin bên thứ ba), đọc tài liệu của **phiên bản plugin được dùng trong POM**.

## 4. Cách thứ nhất: khai báo tường minh các JDK trong toolchains.xml

Tạo file `${user.home}/.m2/toolchains.xml` trên **máy chạy Maven**, không phải trong thư mục `src/` hoặc `target/` của dự án.

Ví dụ trên Linux/macOS, giả định máy có JDK 17 thực sự tại `/opt/jdks/temurin-17` và JDK 21 tại `/opt/jdks/temurin-21`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>

    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đây là **file toolchains.xml hoàn chỉnh** cho ví dụ. Các thư mục `/opt/jdks/temurin-17` và `/opt/jdks/temurin-21` **chỉ là đường dẫn minh họa**: phải thay thành đường dẫn JDK **thực sự được cài** trên máy. Khi chạy ví dụ chính chỉ cần entry JDK 17; entry JDK 21 phục vụ phần kiểm thử chéo ở mục sau.

### Ý nghĩa từng phần tử

- `<type>jdk</type>`: tên kiểu toolchain mà Compiler/Surefire/Javadoc có thể yêu cầu.
- `<provides><version>17</version>`: metadata công bố cho khâu **matching**; JDK Toolchains Plugin so yêu cầu với giá trị này.
- `<configuration><jdkHome>...</jdkHome>`: đường dẫn **thư mục gốc của JDK**. Đây là thư mục có `bin/java`, `bin/javac`, `bin/javadoc`..., **không** trỏ tới file `java` hoặc `javac` đơn lẻ.
- Có thể thêm `<vendor>...` trong `<provides>` nếu muốn chọn nhà phân phối, nhưng cần khai báo giá trị thật và biết quy tắc so sánh. Trong bài này bỏ `vendor` để tăng khả năng dùng trên những bản phân phối JDK khác nhau.

**Cực kỳ quan trọng về version matching:** theo tài liệu Maven, giá trị `<version>17</version>` trong toolchains.xml **không mặc nhiên bằng** `17.0.12` khi yêu cầu một phiên bản đúng bằng chuỗi `17`. Dùng version range như **`[17,18)`** để match cả giá trị `17` lẫn `17.0.x` khi phù hợp. Chúng ta sẽ dùng range này trong POM thay vì giả định mọi công cụ tạo file đều ghi cùng một định dạng phiên bản.

### Windows

Ví dụ một entry `toolchains.xml` trên Windows có thể viết:

```xml
<toolchain>
    <type>jdk</type>
    <provides>
        <version>17</version>
    </provides>
    <configuration>
        <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
</toolchain>
```

Đoạn XML trên thay **một entry** trong file `toolchains.xml` hoàn chỉnh, không phải toàn bộ file. `C:/Java/jdk-17` là ví dụ; cần dùng đúng thư mục JDK có thật. Dùng dấu `/` trong XML giúp tránh các nhầm lẫn khi xử lý backslash.

**Không commit đường dẫn JDK của từng thành viên vào POM chung**. POM chỉ khai báo **yêu cầu** như Java 17; mỗi máy tự ánh xạ yêu cầu đó tới JDK cài thực tế bằng toolchains.xml hoặc cơ chế discovery.

## 5. Cách thứ hai: cấu hình Maven Toolchains Plugin trong POM

Với entry toolchains.xml đã có, ta khai báo Maven Toolchains Plugin. Cách chuẩn, tường minh và hỗ trợ cả JDK lẫn loại toolchain khác là goal **`toolchains:toolchain`**.

Đoạn trong `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <id>select-build-jdk</id>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

**Đây là cấu hình plugin để đặt vào POM, không phải POM hoàn chỉnh.**

Tại sao hoạt động?

1. `<executions>` yêu cầu Maven thực hiện goal `toolchain`.
2. Goal `toolchains:toolchain` có default phase **`validate`**, nên execution trên có thể bỏ `<phase>validate</phase>`. Có thể thêm phase tường minh cho người đọc dễ hiểu.
3. `<configuration><toolchains><jdk>` yêu cầu một JDK toolchain có version **từ 17 tới trước 18**.
4. Plugin tìm một entry phù hợp trong `toolchains.xml` và đặt JDK toolchain đã chọn vào build context.
5. Các plugin **toolchain-aware** chạy sau đó trong lifecycle có thể lấy toolchain từ context.

Ví dụ hai yêu cầu:

```xml
<toolchains>
    <jdk>
        <version>[17,18)</version>
        <vendor>temurin</vendor>
    </jdk>
</toolchains>
```

Đây là **đoạn chỉ hợp lệ khi** file `toolchains.xml` có entry `<vendor>temurin</vendor>` tương ứng trong `provides`. Các thuộc tính đều phải match. Nếu file chỉ có version mà không có vendor, thêm ràng buộc vendor vào POM sẽ khiến không tìm được toolchain.

**Không nhầm** `<jdk>` trong POM với thư mục JDK: `<jdk>` chứa **yêu cầu**, còn `<jdkHome>` trong toolchains.xml chứa **đường dẫn**.

## 6. Bài thực hành Java 17 hoàn chỉnh: dùng một toolchain cho build và test

Ta xây dựng một dự án Java 17 có JUnit 5. Mục đích là chứng minh:
- Maven được phép chạy bằng JDK khác (ví dụ JDK 21);
- Compiler Plugin biên dịch thành class Java 17;
- Surefire chạy test bằng JVM Java 17 từ toolchain;
- Chương trình Java in output ổn định sau khi build.

### 6.1. Cấu trúc file

```text
toolchain-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/toolchain/App.java
    └── test/
        └── java/
            └── com/example/toolchain/AppTest.java
```

Yêu cầu:
- JDK 17 thật sự cài trên máy, đủ `bin/javac` và `bin/java`;
- `toolchains.xml` đúng đường dẫn JDK 17 ở mục 4;
- Maven 3.9.x tương thích các plugin được chốt phiên bản trong POM;
- Repository/mạng cho phép resolve các Maven plugins và JUnit ở lần đầu.

### 6.2. pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>toolchain-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <id>select-jdk-17</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>toolchain</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <toolchains>
                        <jdk>
                            <version>[17,18)</version>
                        </jdk>
                    </toolchains>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
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

Đây là **POM độc lập hoàn chỉnh**.

Giải thích:
- Toolchains Plugin chọn một JDK toolchain version `[17,18)` ở `validate`. Nếu không tìm thấy, Maven **dừng build sớm** thay vì âm thầm biên dịch bằng một bản JDK khác.
- `maven.compiler.release=17` yêu cầu compiler tạo bytecode/API Java 17. **Chọn toolchain** và **chọn release** là hai cơ chế khác nhau và được dùng **cùng nhau** ở đây.
- Compiler Plugin 3.14.1 được kích hoạt qua default lifecycle của packaging `jar`; nó có hỗ trợ JDK toolchain.
- Surefire Plugin 3.5.4 chạy unit test ở phase `test`. `forkCount=1` đảm bảo có fork test JVM; Surefire có thể dùng toolchain đã chọn thay vì luôn dùng JDK chạy Maven.
- Dependency JUnit 5 có scope `test`, không đưa vào runtime dependency của ứng dụng.

### 6.3. File src/main/java/com/example/toolchain/App.java

```java
package com.example.toolchain;

public final class App {
    private App() {
    }

    public static String message() {
        return "JDK toolchain demo";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Đây là Java 17 hợp lệ, không phụ thuộc thư viện ngoài. Maven sẽ biên dịch thành `target/classes/com/example/toolchain/App.class`.

### 6.4. File src/test/java/com/example/toolchain/AppTest.java

```java
package com.example.toolchain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("JDK toolchain demo", App.message());
    }

    @Test
    void testsActuallyRunOnJava17() {
        assertEquals(17, Runtime.version().feature());
    }
}
```

Test đầu kiểm tra logic của ứng dụng. Test thứ hai **cố ý kiểm tra feature version của JVM đang chạy test**, không kiểm tra JDK khởi chạy Maven. Khi Surefire thực sự chạy bằng JDK 17, `Runtime.version().feature()` có giá trị `17` và test pass.

Chú ý:
- `Runtime.version()` có từ Java 9; code dùng được trên Java 17.
- Test thứ hai là **bằng chứng runtime**, không phải chỉ dựa vào `mvn -version`.
- Nếu cấu hình riêng JDK 21 cho test ở mục sau, test này phải được điều chỉnh cho kỳ vọng mới; nếu không, nó **sẽ fail đúng mục đích** vì đang đòi JVM 17.
- Khi `forkCount=0`, Surefire chạy test trong Maven JVM và không thể đảm bảo sử dụng một forked JVM từ toolchain. Bài thực hành dùng `forkCount=1` để tránh tình huống đó.

### 6.5. Chạy build và kiểm tra

Từ thư mục `toolchain-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Giả sử `mvn -version` in Java 21, nhưng toolchains.xml có JDK 17 hợp lệ, build vẫn có thể:
- chọn JDK 17 tại phase validate;
- biên dịch code bằng compiler toolchain;
- chạy hai bài test với forked JVM JDK 17;
- tạo JAR chính ở phase package;
- hoàn tất verify nếu không có lỗi khác.

Trong log của Maven Toolchains Plugin, thường có dòng tương tự:

```text
Required toolchain: jdk [ version='[17,18)' ]
Found matching toolchain for type jdk: JDK[/opt/jdks/temurin-17]
```

Đây là **log minh họa**, không phải lời cam kết nguyên văn với mọi phiên bản plugin. Đường dẫn và định dạng thực tế tùy máy.

Kiểm tra bản Java class file:

```bash
javap -verbose target/classes/com/example/toolchain/App.class
```

Trong phần header, với `--release 17` sẽ thấy `major version: 61`. Lệnh `javap` bản thân có thể được gọi từ một JDK bất kỳ có khả năng đọc class file này; **major version 61 là bằng chứng về class file target Java 17**, không phải bằng chứng binary được biên dịch bằng bộ `javac` ở một đường dẫn cụ thể. Đường dẫn compiler cần được xác nhận bằng Toolchains Plugin và log compiler.

Để chạy ứng dụng, từ thư mục chứa POM:

```bash
java -cp target/classes com.example.toolchain.App
```

**Stdout chính xác** của lệnh Java:

```text
JDK toolchain demo
```

Lệnh `java` bên ngoài Maven dùng Java nằm trên `PATH` của shell. Toolchain của phiên Maven **không tự thay `PATH`**, nên một lệnh `java -version` ở terminal có thể in Java 21 dù Surefire trong Maven đã chạy bằng JDK 17.

### 6.6. Cách kiểm tra Surefire report

Sau build thành công, mở:

```text
target/surefire-reports/
```

Báo cáo JUnit cho `AppTest` thường cho biết **2 tests**, không có failure/error. Đó là bằng chứng Maven đã thực sự chạy test. Nếu không thấy báo cáo, kiểm tra tên test phù hợp convention của Surefire, JUnit provider, plugin version và exit code.

**Không coi “BUILD SUCCESS” của `mvn validate` là bằng chứng test đã chạy**: phase validate chưa đến `test`. Phải dùng `mvn test`, `mvn verify` hoặc phase phù hợp để thực thi Surefire.

## 7. Chọn riêng JDK cho compiler và JVM kiểm thử

Đôi khi project muốn **compile với JDK 17 nhưng chạy test trên JDK 21** để phát hiện lỗi tương thích trên runtime mới. Một số plugin cho phép cấu hình **`jdkToolchain` riêng**, ghi đè toolchain chung trong build context ở phạm vi plugin.

### 7.1. Compiler Plugin có jdkToolchain riêng

Maven Compiler Plugin hỗ trợ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>[17,18)</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Đây là **đoạn plugin thay cho khối Maven Compiler Plugin** trong POM, không phải một plugin thứ hai cần thêm. `<jdkToolchain>` dùng để chọn JDK compiler độc lập; tài liệu plugin xác nhận nó có ưu tiên hơn toolchain chung từ Maven Toolchains Plugin.

**Phân biệt `<release>17</release>` và `<jdkToolchain><version>...`**:
- release = mức Java API/bytecode được nhắm tới;
- jdkToolchain = JDK thực tế cung cấp compiler.

Ví dụ compile với JDK 21 và release17 cũng có thể đúng nếu toolchain compiler yêu cầu `[21,22)`. Nhưng việc dùng JDK 17 cho compiler bảo đảm hành vi compiler sát môi trường phát hành nếu đó là chính sách project.

### 7.2. Surefire Plugin dùng test JVM khác

Giả sử cả JDK 17 và JDK 21 được khai báo đúng trong toolchains.xml. Để giữ compiler chung ở JDK 17 nhưng thử test trên JDK 21, thay khối Surefire Plugin trong POM bằng:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <forkCount>1</forkCount>
        <jdkToolchain>
            <version>[21,22)</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Đây là **biến thể thay thế** cho khối Surefire ở mục 6, không thêm khối plugin trùng vào cùng POM. Khi Surefire tìm thấy JDK 21 toolchain:
- mã chính và mã test vẫn có thể được compile bằng JDK 17, mục tiêu `release17`;
- Surefire fork JVM Java 21 để thực thi JUnit tests;
- test `testsActuallyRunOnJava17` ở mục 6.4 **sẽ thất bại**, vì JVM lúc đó thực sự là 21.

Để kiểm chứng trường hợp này, điều chỉnh **chỉ kỳ vọng của test runtime** thành:

```java
@Test
void testsActuallyRunOnJava21() {
    assertEquals(21, Runtime.version().feature());
}
```

Đây là **đoạn method thay thế**, không phải một file Java độc lập. Trong `AppTest.java` cần thay test cũ bằng method này hoặc viết test parametrized theo chính sách CI; không giữ cả hai assertions đòi đồng thời Java 17 và Java 21.

**Tham số `<jvm>` của Surefire có ưu tiên hơn `jdkToolchain`** nếu cả hai cùng cấu hình. Vì thế, khi chọn bằng toolchain, không đồng thời hard-code một đường dẫn `<jvm>/some/jdk/bin/java</jvm>` trừ khi thật sự muốn override. Với `forkCount=0`, ý nghĩa chọn JVM bên ngoài bị thay đổi vì không có fork mới.

### 7.3. Khi nào nên kiểm thử ma trận JDK?

Một ứng dụng có target Java 17 có thể thử:
- compile bằng JDK 17 và chạy test bằng JDK 17 (tính tương thích nền);
- compile bằng JDK 17 và chạy test bằng JDK 21 (tính tương thích với runtime mới);
- hoặc build riêng mỗi job bằng JDK khác nhau trong CI matrix.

**Một build với hai toolchain không tự thay thế toàn bộ test matrix**. Các plugin, reflection, native libraries, annotation processors và API phụ thuộc runtime có thể hoạt động khác nhau. Nếu hỗ trợ nhiều JDK là cam kết sản phẩm, nên chạy các job độc lập với cấu hình/version được pin và kiểm tra test reports riêng.

## 8. Những công cụ khác: Javadoc, Jarsigner và plugin toolchain-aware

### 8.1. Maven Javadoc Plugin

Javadoc Plugin cần công cụ `javadoc`. Khi đã chọn JDK toolchain phù hợp trong Maven build context, những phiên bản Javadoc Plugin hỗ trợ toolchain có thể dùng công cụ từ JDK đó.

Ví dụ cấu hình plugin để tạo Javadoc trong phase liên quan hoặc gọi goal sau khi toolchain đã được chọn:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.10.1</version>
</plugin>
```

Đoạn trên chỉ **khai báo plugin và pin version**, không tự thêm một execution sinh Javadoc vào mọi `mvn package`. Muốn sinh API docs, phải gọi goal hoặc cấu hình lifecycle execution thích hợp. Không khẳng định `mvn package` mặc định luôn tạo Javadoc JAR.

**Cẩn thận khi gọi goal trực tiếp:** nếu chạy riêng `mvn javadoc:javadoc` mà **không** có một phase trước đó kích hoạt Toolchains Plugin trong cùng phiên Maven, session toolchain có thể chưa được chọn. Nên kiểm tra log, hoặc dùng một lệnh bao gồm lifecycle phase phù hợp, ví dụ:

```bash
mvn -B -ntp validate org.apache.maven.plugins:maven-javadoc-plugin:3.10.1:javadoc
```

Trong lệnh này, `validate` chạy Toolchains Plugin trước; goal Javadoc được gọi sau đó. Với một số dự án phức tạp, Javadoc có thể cần code/generated sources đã được tạo trước; khi đó chọn phase lifecycle thích hợp hơn `validate`.

### 8.2. Maven Jarsigner Plugin

Jarsigner Plugin sử dụng công cụ ký JAR `jarsigner` và có các phiên bản hỗ trợ JDK toolchain. Tuy nhiên, ký JAR là thao tác bảo mật/vận hành cần **keystore, certificates và quyền truy cập**. Việc chọn được JDK toolchain không đồng nghĩa tự có khóa ký hay quyền ký artifact.

Không commit keystore password vào POM/toolchains.xml; dùng secret manager/CI credentials và plugin configuration an toàn. Nếu mục tiêu chỉ là học chọn compiler/test toolchain, không cần bật Jarsigner trong project mẫu.

### 8.3. Plugin không hỗ trợ Toolchains

Không phải Maven goal nào cũng hỗ trợ `jdk` toolchain. Một plugin có thể:
- chạy hoàn toàn trong Maven JVM, không fork external Java tool;
- tự dùng `JAVA_HOME`;
- cho phép cấu hình `executable` hoặc `javaHome` theo API riêng;
- bỏ qua session toolchain vì chưa hỗ trợ cơ chế này.

Do đó, **không thể khẳng định mọi công cụ build đều đã đổi sang JDK 17** chỉ vì Toolchains Plugin in “Found matching toolchain”. Phải kiểm tra plugin có toolchain-aware không và xem log/behavior của **goal được gọi**.

## 9. Tự phát hiện JDK với select-jdk-toolchain (3.2.0+)

Từ **Maven Toolchains Plugin 3.2.0**, Apache Maven bổ sung goal **`toolchains:select-jdk-toolchain`** có cơ chế **JDK discovery**. Với phiên bản plugin 3.3.0, goal này tìm các JDK đã cài ở những vị trí phổ biến/env vars rồi chọn JDK match yêu cầu.

Ví dụ thay cách dùng file manual bằng một plugin execution:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <id>discover-jdk-17</id>
            <goals>
                <goal>select-jdk-toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <version>[17,18)</version>
    </configuration>
</plugin>
```

**Đây là cấu hình thay thế cho khối Toolchains Plugin của POM chính**, không phải một execution thứ hai cần chạy cùng goal `toolchain`. Goal `select-jdk-toolchain` cũng mặc định gắn ở phase `validate` và có thể lựa chọn toolchain JDK phù hợp cho những plugin hỗ trợ.

Các goal hỗ trợ discovery/kiểm tra:

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:generate-jdk-toolchains-xml
```

Goal `display-discovered-jdk-toolchains` in thông tin những JDK được phát hiện. Goal `generate-jdk-toolchains-xml` xuất ra dạng XML có thể tham khảo/áp dụng. **Việc discovery có tính heuristic**, phụ thuộc đường dẫn và biến môi trường; nếu JDK được cài ở vị trí lạ hoặc trong container, nó có thể không được tìm thấy.

### useJdk: vì sao discovery không nhất thiết tạo toolchain mới?

Theo tài liệu goal `select-jdk-toolchain` 3.3.0, tham số `useJdk` có các chế độ:
- `IfMatch` (mặc định): nếu JDK **đang chạy Maven** đã thỏa yêu cầu, có thể không chọn toolchain khác, tránh fork/chuyển JVM không cần thiết;
- `IfSame`: chỉ bỏ chọn toolchain nếu toolchain được chọn thật sự là cùng JDK đang chạy Maven;
- `Never`: luôn chọn toolchain phù hợp từ tập được phát hiện.

Ví dụ nếu buộc goal tự chọn JDK discovery ngay cả khi current JDK match:

```xml
<configuration>
    <version>[17,18)</version>
    <useJdk>Never</useJdk>
</configuration>
```

Đoạn này **chỉ là phần configuration** để thay trong Toolchains Plugin. Nó không tạo ra JDK mới nếu máy chưa có bản đáp ứng yêu cầu.

**Không nhầm** `select-jdk-toolchain` và `toolchain`:
- `toolchain` là cơ chế truyền thống, dựa vào `toolchains.xml` có thông tin toolchain được khai báo.
- `select-jdk-toolchain` ưu tiên cơ chế tự phát hiện JDK, không cần file thủ công cho case JDK.
- Cả hai nhằm cung cấp JDK toolchain cho toolchain-aware plugins, nhưng có tham số và điều kiện chọn khác nhau.

## 10. Version range, vendor và cách tránh lỗi matching

### 10.1. Version chính xác và range

Một entry `toolchains.xml` có:

```xml
<provides>
    <version>17.0.12</version>
</provides>
```

Nếu yêu cầu trong POM là:

```xml
<jdk>
    <version>17</version>
</jdk>
```

Maven có thể **không match**, vì một single version được so với chuỗi cung cấp theo quy tắc toolchain, không tự coi `17` bằng `17.0.12`. Nên dùng một range phù hợp:

```xml
<jdk>
    <version>[17,18)</version>
</jdk>
```

Cú pháp range:
- `[17,18)`: Java 17.x, không bao gồm Java 18;
- `[17,)`: Java 17 hoặc cao hơn;
- `[21,22)`: Java 21.x.

Hãy chọn chặt hay rộng tùy chính sách compatibility. Với bài test phải chạy chính xác Java 17, `[17,18)` là lựa chọn rõ ràng.

### 10.2. Vendor không phải lúc nào cũng cùng định dạng

Giá trị `vendor` là metadata trong toolchains.xml; Maven nhận diện nó bằng điều kiện matching, chứ không tự kiểm tra chứng thư hoặc nguồn cung thật của bộ JDK. Một công cụ sinh toolchains.xml có thể viết tên phân phối (ví dụ `temurin`), trong khi discovery báo Java vendor property khác.

Nếu POM đòi `<vendor>temurin</vendor>` nhưng toolchains.xml báo `Eclipse Adoptium`, có thể không match theo cách kỳ vọng. Trước khi thêm vendor constraint, đọc đầu ra discovery/toolchains.xml và xác minh mục tiêu thật sự cần một vendor cụ thể.

### 10.3. jdkHome phải hợp lệ

Một entry có thể cung cấp version metadata `17` nhưng `jdkHome` thực tế trỏ tới JDK 21, vì file được sửa sai. Toolchains Plugin kiểm tra matching dựa trên metadata/file configuration; **không dùng metadata tự khai báo làm bằng chứng cryptographic rằng JDK thực sự đúng bản**.

Cần kiểm tra file thực:
- Linux/macOS: `/opt/jdks/temurin-17/bin/java -version` và `/opt/jdks/temurin-17/bin/javac -version`;
- Windows PowerShell: `& 'C:\Java\jdk-17\bin\java.exe' -version` và `& 'C:\Java\jdk-17\bin\javac.exe' -version`.

Đường dẫn trong hai lệnh chỉ có tác dụng nếu máy **thật sự cài JDK ở đó**. Xác minh toolchain qua log và test runtime, không chỉ dựa trên tên folder chứa chuỗi "17".

## 11. Toolchains khác với JAVA_HOME, Maven Wrapper và --release

| Cơ chế | Điều khiển chính | Có quyết định compiler/test JVM không? |
| --- | --- | --- |
| `JAVA_HOME` / PATH | Chọn JDK khởi chạy Maven và lệnh `java` trong shell | Có thể ảnh hưởng mặc định khi **không có** toolchain/override |
| Maven Wrapper `./mvnw` | Chọn/cài phiên bản **Maven runtime/distribution** cho dự án | Không tự chọn riêng JDK compiler/test |
| `maven.compiler.release` | Java language/API/classfile target | **Không** chọn đường dẫn JDK |
| Toolchains Plugin `toolchain` | Chọn JDK toolchain vào Maven build context từ file machine-local | Có, với các plugin toolchain-aware |
| Toolchains Plugin `select-jdk-toolchain` | Chọn JDK đã discovery phù hợp yêu cầu | Có, với plugin toolchain-aware và khi selection được thực hiện |
| Compiler `jdkToolchain` | JDK compiler riêng cho Compiler Plugin | Có, ghi đè session toolchain ở compiler |
| Surefire `jdkToolchain` | JDK JVM dùng để fork test của Surefire | Có, khi chạy fork và match toolchain |
| Surefire `jvm` | Đường dẫn Java executable cụ thể cho fork | Có, và ưu tiên hơn `jdkToolchain` |
| `toolchains.xml` | Danh mục JDK/tool ngoài dự án | Chưa đủ; project phải chọn và plugin phải sử dụng |

**Tình huống cần chú ý:** Maven Wrapper có thể chọn phiên bản Maven đúng nhưng phiên bản JDK do hệ điều hành cung cấp không tương thích với bản Maven đó. Toolchain **không giúp Maven khởi chạy trên một JVM không tương thích**, vì lựa chọn toolchain xảy ra **sau khi Maven đã chạy**.

Ví dụ, một plugin yêu cầu JDK 17 để chạy logic plugin bên trong Maven JVM có thể vẫn cần Maven runtime tương thích, kể cả khi toolchain compiler là JDK 17. Không hiểu “toolchain 17” là lời hứa mọi plugin sẽ chạy bytecode trong JVM 17.

## 12. Toolchains.xml được lưu ở đâu và có nên commit không?

Vị trí khuyến nghị của user toolchains trong Maven 3:

```text
${user.home}/.m2/toolchains.xml
```

Maven 3.3.1+ hỗ trợ chỉ định file khác bằng:
- `-t` / `--toolchains`: user toolchains file;
- `-gt` / `--global-toolchains`: global toolchains file (trong Maven 3).

Ví dụ:

```bash
mvn -t /opt/ci/maven-toolchains.xml clean verify
```

**`-t` chỉ chọn file toolchains cấu hình, không chọn đường dẫn JDK trực tiếp.** File `/opt/ci/maven-toolchains.xml` cần tồn tại và chứa entry hợp lệ.

Trong Maven 4, tên tùy chọn global/installation toolchains có thay đổi (`-it` / `--install-toolchains`), còn `-gt` có thể chỉ tồn tại để tương thích và bị deprecated. Nếu pipeline hỗ trợ cả Maven 3 lẫn Maven 4, hãy dùng tài liệu CLI của bản Maven đang chạy, thay vì giả định mọi flag giống hệt.

Thông thường:
- **Commit POM** khai báo JDK requirement và plugin versions;
- **Không commit toolchains.xml với đường dẫn máy cá nhân cố định** vào source control dùng chung;
- CI tạo/cung cấp toolchains.xml phù hợp runner, hoặc dùng JDK discovery đã kiểm soát;
- Bảo vệ file và cấu hình đúng quyền; path máy có thể tiết lộ layout nội bộ nhưng bản thân toolchains.xml không phải nơi lưu credentials.

## 13. CI/CD: pin và quan sát đủ ba môi trường

Một quy trình CI đáng tin cậy nên kiểm tra **Maven JVM, compiler và test JVM**.

Ví dụ shell script:

```bash
mvn -version
mvn -B -ntp clean verify
```

Trong bản chạy có cấu hình Toolchains Plugin từ POM mẫu:
- Thông tin `mvn -version` cho biết JDK chạy Maven;
- Log Toolchains Plugin cho biết bản JDK được yêu cầu/chọn;
- Compiler Plugin có thể dùng `javac` theo toolchain đã chọn;
- Test `testsActuallyRunOnJava17` xác nhận test JVM feature version 17;
- Kết quả Maven verify/test reports xác nhận toàn build pass.

Nếu cần chụp bằng chứng ở CI:
1. Lưu `mvn -version` và log toolchains selection.
2. Kiểm tra JDK path đã chọn có `javac`, `java` đúng version.
3. Kiểm tra Surefire tests thật sự chạy, không bị skip qua `-DskipTests` hoặc `-Dmaven.test.skip=true`.
4. Kiểm tra classfile target bằng `javap`/Java binary compatibility tool nếu release là yêu cầu.
5. Nếu chạy test matrix, báo cáo từng JVM riêng; không gộp test trên Java 21 với test trên Java 17.
6. Với container, kiểm tra JDK tồn tại **bên trong container**, không chỉ trên host.
7. Không dựa duy nhất vào cache Maven `.m2/repository`: toolchains.xml và JDK installations là **cấu hình ngoài dependency cache**, cần thiết lập rõ cho mỗi runner.

**Đừng kỳ vọng `-Dmaven.repo.local=...` làm Maven tự tìm JDK mới.** Nó chỉ thay local artifact repository, không thay `toolchains.xml` hoặc JDK discovery.

## 14. Troubleshooting: những lỗi điển hình

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `No toolchain matched` | Không có entry cung cấp version/vendor đúng; range sai | Đọc toolchains.xml, đối chiếu `[17,18)` và vendor, kiểm tra file `-t` |
| Plugin chọn đúng metadata nhưng `javac` không chạy | `jdkHome` sai đường dẫn, trỏ JRE hoặc thiếu file bin | Trỏ tới thư mục **JDK** thực; xác minh `bin/javac` |
| `mvn -version` vẫn in Java 21 | Toolchain không đổi JVM chạy Maven | Đây là hành vi đúng; kiểm tra log/compiler/test riêng |
| `invalid target release: 17` | Compiler thực tế quá cũ, toolchain không được dùng hoặc Maven runtime khác | Xác minh JDK compiler, plugin và `maven.compiler.release` |
| `release version 21 not supported` | Dùng JDK 17 compiler nhưng đặt target 21 | Chọn compiler JDK 21 hoặc hạ release có chủ đích |
| Test assert runtime Java 17 thất bại | Surefire chạy JVM khác hoặc có `<jvm>` override | Kiểm tra forkCount, jdkToolchain, build context và actual `java.version` |
| Maven build thành công nhưng test không chạy | `-DskipTests`, không có test, Surefire config/provider | Kiểm tra reports và lệnh thực tế; không dựa vào BUILD SUCCESS |
| Compiler là JDK 17 nhưng Surefire dùng JDK 21 | Plugin có `jdkToolchain` riêng hoặc `jvm` | Xem Surefire config và điều chỉnh mục tiêu kiểm thử |
| `toolchains.xml` có `version=17.0.12` nhưng POM yêu cầu `17` | Exact value không match như kỳ vọng | Dùng version range `[17,18)` |
| JDK discovery không thấy JDK có sẵn | JDK ở đường dẫn không phổ biến hoặc env vars khác | Dùng manual toolchains.xml hoặc cấu hình discovery tương ứng |
| Javadoc vẫn dùng JDK chạy Maven | Goal Javadoc được gọi trước khi Toolchains Plugin chọn hoặc plugin/version không hỗ trợ | Chạy lifecycle selection trước goal và xem log Javadoc |
| Plugin bên thứ ba bỏ qua toolchain | Plugin không toolchain-aware | Tìm tham số executable/javaHome riêng hoặc thay plugin |
| CI khác local | JDK installations, vendor, settings/toolchains path khác | Pin plugin/version, tạo toolchains.xml theo runner, so log |
| Maven process khởi động lỗi trước validate | JVM chạy Maven không đủ yêu cầu cho chính Maven/plugin | Sửa JDK chạy Maven; Toolchains Plugin chưa thể can thiệp |
| Test chạy JDK 17 nhưng class file báo major version khác | `maven.compiler.release` bị override hoặc compiler không dùng cấu hình | Kiểm tra effective POM, compiler log và classfile |
| Dùng `-t` nhưng Maven vẫn không chọn toolchain mong muốn | File `-t` sai, XML thiếu entry, POM không có execution chọn JDK | Đọc file chỉ định và `mvn help:effective-pom` |
| JDK 17 chưa được cài | Toolchains chỉ **chọn** JDK đã có, không tải/cài JDK từ không khí | Cài JDK thích hợp trong môi trường hoặc cấu hình CI setup step |

### Quy trình điều tra đề xuất

1. **`mvn -version`:** Maven và Java runtime nào đang chạy?
2. **Đọc đúng `toolchains.xml`:** đã cung cấp JDK 17, `jdkHome` là thật, có `bin/javac`?
3. **`mvn help:effective-pom`:** Toolchains Plugin có execution `toolchain`/`select-jdk-toolchain` ở `validate`, compiler/Surefire có override riêng không?
4. **`mvn -B -ntp validate`:** Toolchains Plugin có chọn được JDK theo yêu cầu không?
5. **`mvn -B -ntp clean verify`:** Compiler/test lifecycle có thực sự chạy, có test reports không?
6. **`javap -verbose ...`:** classfile major version có đúng target Java không?
7. **Test runtime Java feature:** JVM thực sự chạy Surefire có đúng bản dự định không?
8. **Plugin liên quan:** Javadoc/Jarsigner/PMD có hỗ trợ toolchain trong phiên bản đã dùng không?
9. **Môi trường:** nếu CI/container khác local, so sánh file toolchains, JDK installs và command flags, không chỉ so `pom.xml`.

## 15. Bài tập tự kiểm tra

1. Máy chạy Maven bằng JDK 21, nhưng code được compile bằng JDK 17 thông qua toolchain: `mvn -version` sẽ in bản Java nào?
2. `maven.compiler.release=17` có đồng nghĩa `javac` chắc chắn là của JDK 17 không? Vì sao?
3. Vì sao `toolchains.xml` nên nằm ngoài POM chung của team?
4. `<jdkHome>` phải trỏ tới file `javac` hay thư mục gốc JDK?
5. Tại sao yêu cầu `version=17` có thể không match metadata `17.0.12`, trong khi `[17,18)` lại phù hợp?
6. Bằng cách nào chứng minh Surefire đã chạy test thật sự bằng Java 17, không chỉ hiển thị config?
7. Nếu compiler build release17 nhưng Surefire có `jdkToolchain=[21,22)`, kết quả kiểm tra `Runtime.version().feature()` bằng bao nhiêu?
8. Tham số Surefire `<jvm>` ảnh hưởng thế nào tới `jdkToolchain`?
9. Tại sao chạy riêng `mvn javadoc:javadoc` có thể không dùng session toolchain được chọn ở phase validate?
10. `toolchains:toolchain` và `toolchains:select-jdk-toolchain` khác nhau thế nào?
11. Toolchain có tự thay JDK của tiến trình Maven đã khởi chạy hay tự cài JDK còn thiếu không?
12. Nếu một plugin bên thứ ba không hỗ trợ toolchain, có nên kết luận nó đang dùng đúng JDK 17 không?
13. Vì sao cần kiểm tra **cả bytecode target, compiler JDK và test JVM** thay vì chỉ một thông tin `java.version`?

**Tổng kết:** Maven Toolchains giúp dự án khai báo yêu cầu về **JDK phục vụ biên dịch và công cụ liên quan**, độc lập với JDK đang chạy Maven. Cách tường minh sử dụng `toolchains.xml` cùng `maven-toolchains-plugin:toolchain` ở phase `validate`; cách hiện đại dùng `select-jdk-toolchain` để discovery. Compiler Plugin, Surefire, Javadoc và những plugin có hỗ trợ đọc toolchain đã chọn; một số có thể chỉ định `jdkToolchain` riêng. `--release` vẫn điều khiển mức Java API/classfile, không thay thế việc chọn JDK. Muốn tin kết quả, hãy xác minh **Maven runtime, compiler thực, test JVM, classfile version và test reports**.

## Tài liệu chính thức để đối chiếu

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Maven Toolchains Plugin — Introduction and Goals](https://maven.apache.org/plugins/maven-toolchains-plugin/)
- [Maven Toolchains Plugin — toolchains:toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchain-mojo.html)
- [Maven Toolchains Plugin — select-jdk-toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html)
- [Maven Toolchains Plugin — JDK discovery](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html)
- [Maven Compiler Plugin — Compiling Sources Using a Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Maven Compiler Plugin — compiler:compile và jdkToolchain](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Maven Surefire Plugin — Using Maven Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html)
- [Maven Surefire Plugin — surefire:test và jdkToolchain](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven — Configuring the Java Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
