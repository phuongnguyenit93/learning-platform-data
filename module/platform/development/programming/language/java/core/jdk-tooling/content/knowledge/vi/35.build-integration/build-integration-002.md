# Maven Toolchain: quản lý JDK cho quá trình build

Maven Toolchains cho phép một dự án chọn JDK hoặc công cụ build phù hợp mà không buộc Maven phải chạy bằng chính JDK đó. Nhờ vậy, Maven có thể chạy trên JDK 21 nhưng dùng JDK 17 để biên dịch source, chạy unit test, tạo Javadoc hoặc ký artifact nếu các plugin tương ứng hỗ trợ toolchain.

Toolchain tách cấu hình yêu cầu của dự án khỏi đường dẫn cài đặt trên từng máy. POM mô tả loại JDK và version/vendor cần dùng; file toolchains.xml trên máy build ánh xạ các tiêu chí đó tới thư mục JDK thực tế. Bài này dùng Maven 3.6.3 trở lên, Maven Toolchains Plugin 3.3.0 và ví dụ JDK 17.

## 1. Maven Toolchain là gì?

Toolchain là một đối tượng cấu hình mô tả một công cụ có thể được Maven plugin sử dụng. Với JDK toolchain, thông tin quan trọng nhất là:

- Loại toolchain: jdk.
- Các thuộc tính dùng để nhận diện: version, vendor hoặc metadata khác.
- Thư mục gốc cài đặt JDK: jdkHome.

Maven Toolchains Plugin đọc các toolchain đã cấu hình trên máy build, so khớp chúng với yêu cầu trong POM và đưa toolchain được chọn vào Maven build context. Những plugin hiểu toolchain có thể lấy JDK đã chọn để chạy công việc của mình.

Ví dụ, dự án yêu cầu JDK 17. Máy developer có JDK 17 và JDK 21; CI cũng có thể có nhiều JDK. POM chỉ yêu cầu JDK 17, còn mỗi máy khai báo đường dẫn JDK 17 trong toolchains.xml của riêng mình.

Toolchain không cài đặt JDK. Nó chỉ chọn một cài đặt đã tồn tại và cung cấp thông tin đó cho plugin hỗ trợ.

## 2. Phân biệt JDK chạy Maven, JDK toolchain và target release

Ba khái niệm này thường bị nhầm lẫn:

| Khái niệm | Cách xác định | Ảnh hưởng |
|---|---|---|
| JDK chạy Maven | JAVA_HOME, PATH hoặc cấu hình Maven/IDE | Chạy Maven core và phần lớn plugin code |
| JDK toolchain | Maven Toolchains Plugin chọn từ toolchains.xml hoặc discovery | Cung cấp JDK cho plugin có hỗ trợ toolchain |
| Java release/target | maven.compiler.release hoặc cấu hình compiler tương đương | Quy định ngôn ngữ, API và bytecode mà source được phép sử dụng |

Ví dụ:

- Maven chạy bằng JDK 21.
- Toolchain cung cấp JDK 17 cho Compiler Plugin và Surefire.
- Compiler dùng release 17 để tạo bytecode tương thích Java 17.

Trong trường hợp đó, Maven process vẫn chạy trên JDK 21. Toolchain không thay JAVA_HOME, PATH, java.home hoặc JDK của mọi plugin. Chỉ các plugin có hỗ trợ toolchain mới sử dụng JDK được chọn.

Thuộc tính maven.compiler.release không chọn JDK cài đặt. Nó giới hạn API và phiên bản bytecode mà compiler tạo ra. Nếu cần một javac cụ thể, hãy chọn toolchain; nếu cần artifact chạy được trên một Java release, hãy đặt release tương ứng. Thường cần cả hai cấu hình.

## 3. Khi nào nên dùng Maven Toolchains?

Toolchains hữu ích trong các trường hợp:

- Build dự án Java 17 trong khi Maven hoặc IDE đang chạy trên JDK 21.
- Kiểm tra tương thích trên nhiều JDK mà không đổi JAVA_HOME toàn hệ thống.
- Dùng cùng JDK cho compile, test, Javadoc và các plugin toolchain-aware.
- Chuẩn hóa build giữa máy developer, build server và CI runner.
- Hỗ trợ nhiều nhánh dự án yêu cầu các JDK khác nhau.
- Chọn JDK theo vendor hoặc version range.
- Tránh hardcode đường dẫn máy cá nhân vào POM.

Toolchains đặc biệt hữu ích ở dự án lớn, nơi nhiều plugin cùng gọi các công cụ như javac, java, javadoc, jdeps hoặc jarsigner.

Nếu toàn bộ team và CI đã chạy Maven trên cùng một JDK, không có plugin nào cần JDK khác và không cần kiểm thử đa phiên bản, cấu hình toolchain có thể không cần thiết.

## 4. Kiến trúc cấu hình gồm hai phía

Có hai phần chính:

1. POM của dự án khai báo yêu cầu toolchain và gọi Maven Toolchains Plugin.
2. toolchains.xml trên máy build mô tả những JDK đã cài và đường dẫn tới chúng.

Luồng hoạt động:

~~~text
mvn clean verify
       |
       v
Maven khởi chạy trên JDK của JAVA_HOME
       |
       v
Maven Toolchains Plugin chạy ở phase validate
       |
       v
Đọc toolchains.xml và so khớp yêu cầu từ POM
       |
       v
Chọn JDK toolchain và lưu trong Maven build context
       |
       v
Các plugin hỗ trợ toolchain lấy JDK đã chọn
       |
       +---- Compiler Plugin: biên dịch
       |
       +---- Surefire/Failsafe: chạy test JVM
       |
       +---- Javadoc/Jarsigner: gọi công cụ JDK
~~~

Toolchain được chọn ở phase validate để các plugin chạy ở phase sau có thể sử dụng nó. Một plugin không hỗ trợ toolchain vẫn có thể chạy bằng JVM hoặc công cụ mà chính plugin đó cấu hình.

## 5. Cài đặt và kiểm tra các JDK

Cài các JDK cần dùng trên máy developer hoặc CI runner. Mỗi JDK phải là bản JDK đầy đủ, có các công cụ cần thiết trong thư mục bin.

Ví dụ đường dẫn:

~~~text
Windows:
C:/Java/jdk-17
C:/Java/jdk-21

Linux:
 /opt/jdk-17
 /opt/jdk-21

macOS:
 /Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home
~~~

Kiểm tra JDK trực tiếp:

~~~powershell
C:\Java\jdk-17\bin\java -version
C:\Java\jdk-17\bin\javac -version
~~~

Trên Linux/macOS:

~~~bash
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/javac -version
~~~

Kiểm tra Maven runtime:

~~~powershell
mvn -version
~~~

Lệnh này cho biết Maven version, Java version, Java home và hệ điều hành mà Maven đang dùng. Nó không chứng minh toolchain đã được chọn; cần xem log của Maven Toolchains Plugin và plugin sử dụng JDK.

## 6. Tạo file toolchains.xml

Theo mặc định, Maven tìm file user-level tại:

~~~text
~/.m2/toolchains.xml
~~~

Trên Windows, thư mục tương ứng thường là:

~~~text
%USERPROFILE%\.m2\toolchains.xml
~~~

Ví dụ khai báo một JDK 17 và một JDK 21:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17.0.12</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
  </toolchain>

  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21.0.4</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-21</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Các phần tử:

- type: loại toolchain. Với JDK chuẩn, giá trị là jdk.
- provides: metadata để plugin so khớp, ví dụ version và vendor.
- configuration: cấu hình đường dẫn truy cập toolchain.
- jdkHome: thư mục gốc của JDK, không phải đường dẫn tới java.exe hoặc javac.exe.

Có thể khai báo nhiều toolchain cùng type. Mỗi toolchain cần một bộ metadata đủ để phân biệt và một đường dẫn cài đặt hợp lệ.

Dùng dấu gạch chéo xuôi trong đường dẫn Windows giúp XML dễ đọc và tránh nhầm lẫn với escape sequence. Thay các đường dẫn ví dụ bằng vị trí JDK thật trên máy.

## 7. Cấu hình Maven Toolchains Plugin trong POM

Ví dụ yêu cầu JDK 17 của vendor có metadata là temurin:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.3.0</version>
      <executions>
        <execution>
          <goals>
            <goal>toolchain</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <toolchains>
          <jdk>
            <version>[17,18)</version>
            <vendor>temurin</vendor>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Plugin sẽ tìm một entry có type jdk, version nằm trong khoảng [17,18) và vendor khớp temurin. Nếu tìm được, plugin lưu toolchain vào build context để các plugin hỗ trợ sử dụng.

Goal toolchain được gắn với phase validate. Trong POM vẫn cần khai báo execution và yêu cầu cần match như ví dụ trên.

Maven Toolchains Plugin 3.3.0 yêu cầu Maven 3.6.3 trở lên và JDK 8 trở lên để chạy plugin. Kiểm tra Maven runtime trước khi dùng phiên bản plugin này.

## 8. Hiểu cách match version và vendor

Đây là phần dễ gây lỗi cấu hình.

Nếu toolchains.xml khai báo:

~~~xml
<version>17.0.12</version>
~~~

thì yêu cầu:

~~~xml
<version>17</version>
~~~

không nhất thiết khớp. Với version dạng đầy đủ, dùng version range:

~~~xml
<version>[17,18)</version>
~~~

Khoảng này chấp nhận các phiên bản từ 17 trở lên nhưng nhỏ hơn 18, ví dụ 17 hoặc 17.0.12.

Một số ví dụ version range:

| Yêu cầu | Ý nghĩa |
|---|---|
| [17,18) | JDK 17.x, không nhận JDK 18 |
| [17,) | JDK 17 trở lên |
| [21,22) | JDK 21.x |
| [8,9) | Version metadata 8.x theo cách ghi tương ứng |
| [1.8,1.9) | Cách biểu diễn version Java 8 dạng 1.8.x |

Các thuộc tính khác như vendor được so khớp theo chuỗi chính xác, không phải tìm gần đúng; so sánh không phân biệt chữ hoa/thường. Hãy dùng cùng một giá trị ở POM và toolchains.xml.

Lưu ý quan trọng: version và vendor trong provides là metadata để match. Maven không xác minh JDK thực tế ở jdkHome có đúng version hoặc vendor mà metadata khai báo. Plugin kiểm tra đường dẫn tồn tại; người cấu hình phải bảo đảm đường dẫn trỏ tới đúng JDK.

## 9. Plugin nào hỗ trợ JDK toolchain?

Một số plugin Apache Maven có hỗ trợ JDK toolchain:

| Plugin | Công việc |
|---|---|
| maven-compiler-plugin | Biên dịch source bằng javac của toolchain |
| maven-surefire-plugin | Chạy unit test bằng JDK toolchain |
| maven-failsafe-plugin | Chạy integration test bằng JDK toolchain |
| maven-javadoc-plugin | Tạo Javadoc bằng công cụ JDK |
| maven-jarsigner-plugin | Ký JAR |
| maven-jdeps-plugin | Phân tích dependency/module |
| maven-jlink-plugin | Tạo runtime image |
| maven-jmod-plugin | Tạo JMOD |

Danh sách và phiên bản hỗ trợ được duy trì trong tài liệu Maven. Một plugin bên thứ ba có thể không hỗ trợ toolchain, ngay cả khi plugin đó gọi một công cụ có trong JDK.

Đừng giả định mọi plugin trong lifecycle đều tự động chuyển sang JDK đã chọn. Kiểm tra tài liệu plugin hoặc log để xác nhận plugin cụ thể có đọc toolchain hay không.

## 10. Cấu hình Compiler Plugin với toolchain

Compiler Plugin là một trong những plugin sử dụng JDK toolchain phổ biến nhất.

Ví dụ:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.16.0</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Khi Maven Toolchains Plugin đã chọn JDK 17, Compiler Plugin có thể dùng javac từ JDK đó. release 17 quy định source language, Java API và bytecode mục tiêu.

Phân biệt:

- Toolchain quyết định compiler JDK nào được gọi.
- release quyết định phiên bản Java mà source được phép dùng và bytecode được tạo ra.
- source/target chỉ điều khiển mức ngôn ngữ và bytecode ở mức thấp hơn; release thường là lựa chọn phù hợp hơn khi dùng JDK 9 trở lên vì còn giới hạn API.

Nếu chỉ đặt release 17 nhưng Maven đang chạy trên JDK 21, compiler vẫn có thể chạy bằng JDK 21 và tạo bytecode Java 17. Muốn chắc chắn dùng javac 17, cần toolchain hoặc cấu hình compiler executable riêng.

## 11. Dùng toolchain cho Surefire và Failsafe

Surefire chạy unit test; Failsafe chạy integration test. Khi cấu hình toolchain chung, Surefire/Failsafe có thể khởi chạy test JVM bằng JDK đã chọn.

Ví dụ:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.4</version>
  <configuration>
    <forkCount>1</forkCount>
  </configuration>
</plugin>
~~~

Mặc định Surefire có thể dùng toolchain chính để chạy test JVM. Toolchain chỉ ảnh hưởng test process được fork. Nếu đặt forkCount bằng 0, test chạy trong Maven process và không thể chuyển JVM đang chạy sang một JDK khác.

Vì vậy, khi test cần xác nhận JDK thực tế, hãy để Surefire fork process và kiểm tra Runtime.version() bên trong test.

Failsafe có cơ chế toolchain tương tự, phù hợp với các integration-test và verify phase. Đọc tài liệu phiên bản plugin đang dùng nếu có cấu hình JVM riêng hoặc fork tùy chỉnh.

## 12. Chọn JDK khác nhau cho từng plugin

Toolchains Plugin chọn một JDK chung cho các plugin toolchain-aware. Trong một số dự án, compiler và test cần JDK khác nhau.

Các plugin hỗ trợ tham số jdkToolchain có thể chỉ định toolchain riêng:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.16.0</version>
  <configuration>
    <jdkToolchain>
      <version>[17,18)</version>
    </jdkToolchain>
  </configuration>
</plugin>
~~~

Cấu hình jdkToolchain riêng sẽ ghi đè toolchain chung được Maven Toolchains Plugin chọn cho plugin đó.

Hỗ trợ này có điều kiện theo phiên bản:

- Compiler Plugin hỗ trợ jdkToolchain từ phiên bản 3.6, cùng Maven 3.3.1 trở lên.
- Surefire và Failsafe hỗ trợ từ 3.0.0-M5.
- Javadoc Plugin hỗ trợ từ 3.0.0.

Chỉ dùng override khi có yêu cầu thực tế, ví dụ compile bằng JDK 17 nhưng chạy test trên JDK 21. Nếu không cần tách, giữ một toolchain chung sẽ dễ kiểm soát hơn.

## 13. Khám phá JDK tự động từ Maven Toolchains Plugin

Từ phiên bản 3.2.0, Maven Toolchains Plugin có cơ chế discovery JDK. Plugin dùng heuristic để tìm JDK ở các vị trí cài đặt quen thuộc và qua environment variable.

Liệt kê JDK đã phát hiện:

~~~powershell
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

Output có thể cho biết:

- Đường dẫn cài đặt.
- Version và runtime version.
- Vendor và vendor version.
- JDK hiện tại có phải JDK đang chạy Maven hay không.
- Có phải bản LTS hay không.
- Environment variable liên quan.

Nếu muốn plugin tự chọn JDK phù hợp, dùng goal select-jdk-toolchain. Ví dụ chọn JDK 17:

~~~powershell
mvn toolchains:select-jdk-toolchain -Dtoolchain.jdk.version="[17,18)" compile
~~~

Có thể khai báo goal trong POM:

~~~xml
<properties>
  <toolchain.jdk.version>[17,18)</toolchain.jdk.version>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.3.0</version>
      <executions>
        <execution>
          <goals>
            <goal>select-jdk-toolchain</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Goal select-jdk-toolchain có thể lựa chọn trong các JDK được khai báo tường minh và các JDK được discovery. Danh sách discovery được cache để giảm thời gian tìm kiếm.

Discovery phụ thuộc heuristic và cách cài JDK. Nếu plugin không phát hiện một JDK, hãy khai báo thủ công trong toolchains.xml hoặc kiểm tra environment variable và vị trí cài đặt.

Không cấu hình đồng thời hai execution khác nhau chỉ để chọn cùng một JDK mà không hiểu thứ tự và mục đích của từng goal. Chọn cách quản lý phù hợp với môi trường build.

## 14. Ví dụ hoàn chỉnh: Maven chạy JDK 21, build và test bằng JDK 17

Ví dụ này kiểm tra toolchain bằng một unit test. Maven có thể chạy bằng JDK 21; Toolchains Plugin chọn JDK 17; Surefire fork test JVM bằng JDK 17.

Cấu trúc dự án:

~~~text
toolchain-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          App.java
    test/
      java/
        demo/
          ToolchainTest.java
~~~

Tạo toolchains.xml ở ~/.m2/toolchains.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17.0.12</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>C:/Java/jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Thay version, vendor và jdkHome bằng metadata/đường dẫn JDK thật của bạn. POM dùng version range [17,18) để khớp metadata 17 hoặc 17.0.12.

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>toolchain-demo</artifactId>
  <version>1.0.0</version>

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
        <artifactId>maven-toolchains-plugin</artifactId>
        <version>3.3.0</version>
        <executions>
          <execution>
            <goals>
              <goal>toolchain</goal>
            </goals>
          </execution>
        </executions>
        <configuration>
          <toolchains>
            <jdk>
              <version>[17,18)</version>
              <vendor>temurin</vendor>
            </jdk>
          </toolchains>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.4</version>
        <configuration>
          <forkCount>1</forkCount>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tạo src/main/java/demo/App.java:

~~~java
package demo;

public final class App {
    public static String message() {
        return "Built with Maven toolchain.";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo src/test/java/demo/ToolchainTest.java:

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ToolchainTest {
    @Test
    void surefireRunsOnJdk17() {
        assertEquals(17, Runtime.version().feature());
    }

    @Test
    void applicationReturnsExpectedMessage() {
        assertEquals("Built with Maven toolchain.", App.message());
    }
}
~~~

Chạy:

~~~powershell
mvn -version
mvn clean verify
~~~

Lệnh đầu cho biết JDK chạy Maven. Lệnh thứ hai thực hiện toolchain selection ở validate, biên dịch source bằng Compiler Plugin và chạy test bằng Surefire.

Khi chọn được JDK, log sẽ có thông tin tương tự:

~~~text
[INFO] --- toolchains:3.3.0:toolchain (default) @ toolchain-demo ---
[INFO] Required toolchain: jdk [ version='[17,18)', vendor='temurin' ]
[INFO] Found matching toolchain for type jdk: JDK[C:/Java/jdk-17]
~~~

Kết quả test mong đợi:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Hai test xác nhận Surefire fork JVM dùng Java feature version 17 và method ứng dụng trả đúng kết quả. Đường dẫn JDK và các dòng log đầy đủ phụ thuộc máy; phần version của Maven runtime có thể là 21 trong khi test vẫn chạy trên 17.

Nếu Maven không tìm được toolchain, build phải dừng ở bước chọn toolchain. Không bỏ qua lỗi đó bằng cách đổi release hoặc chỉ đổi JAVA_HOME nếu mục tiêu là xác minh JDK 17 được chọn.

## 15. Dùng toolchains.xml riêng cho CI

Mỗi CI runner có thể cài JDK tại đường dẫn khác. Vì vậy:

- Cài JDK cần thiết trên runner trước khi chạy Maven.
- Tạo toolchains.xml trong home của user chạy CI hoặc truyền file bằng tham số -t.
- Dùng đường dẫn JDK thực tế của runner.
- Đặt metadata version/vendor nhất quán với yêu cầu trong POM.
- Chạy Maven Wrapper để chuẩn hóa Maven distribution.
- Lưu log chọn toolchain trong build log để dễ kiểm tra.

Ví dụ dùng file toolchains riêng:

~~~powershell
mvn -t C:\ci\config\toolchains.xml clean verify
~~~

Từ Maven 3.3.1, tham số -t hoặc --toolchains cho phép chỉ định file toolchains thay thế. Đường dẫn file này thuộc môi trường build, không cần hardcode trong POM.

Không nên commit toolchains.xml chứa đường dẫn tuyệt đối máy developer vào repository. Mỗi developer/runner quản lý file riêng; POM chỉ chứa tiêu chí chung của dự án.

Maven Wrapper pin phiên bản Maven cho dự án nhưng không cài hoặc chọn JDK thay cho toolchain. CI vẫn phải provision JDK và cấu hình đường dẫn đúng.

## 16. Xác minh JDK nào thực sự được sử dụng

Dùng nhiều lớp bằng chứng:

1. Chạy mvn -version để biết JDK của Maven process.
2. Đọc log Maven Toolchains Plugin để thấy yêu cầu và JDK được chọn.
3. Kiểm tra log Compiler Plugin để xác nhận compiler toolchain được sử dụng.
4. Với Surefire/Failsafe, xác nhận test JVM được fork bằng toolchain.
5. Dùng test đọc Runtime.version() khi cần kiểm tra phiên bản JVM chạy test.
6. Xem artifact bytecode bằng javap -verbose nếu cần xác minh class-file major version.

Ví dụ:

~~~powershell
mvn -X clean verify
~~~

Chế độ debug cung cấp thêm thông tin về plugin execution và toolchain. Log có thể dài; lọc các dòng chứa toolchains, maven-compiler-plugin, maven-surefire-plugin và JDK path.

Kiểm tra bytecode:

~~~powershell
javap -verbose target/classes/demo/App.class
~~~

Với Java 17, class-file major version là 61. Bytecode version xác nhận mức target của class; nó không chứng minh compiler executable đã được lấy từ thư mục JDK nào. Để chứng minh compiler JDK, xem toolchain selection và compiler log.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| No toolchain matched | Không có entry thỏa version/vendor trong toolchains.xml | Kiểm tra metadata ở cả POM và toolchains.xml |
| JDK 17 không match | POM dùng version 17 nhưng file ghi 17.0.x | Dùng range [17,18) hoặc ghi metadata khớp chính xác |
| Vendor không match | Chuỗi vendor khác nhau | Dùng cùng chuỗi metadata, chú ý so khớp exact |
| jdkHome không hợp lệ | Đường dẫn trỏ tới JRE hoặc thư mục không tồn tại | Trỏ tới root của JDK đầy đủ |
| Maven vẫn hiển thị Java 21 | Maven process vẫn chạy trên JAVA_HOME JDK 21 | Đây là hành vi bình thường; xem toolchain log và test JVM |
| Compiler dùng sai JDK | Compiler plugin không đọc toolchain hoặc cấu hình override | Kiểm tra phiên bản plugin và jdkToolchain |
| Test chạy trên JDK khác | Surefire không fork hoặc có cấu hình JVM riêng | Kiểm tra forkCount, jdkToolchain và log forked JVM |
| CI chạy được local nhưng fail | CI không có JDK hoặc toolchains.xml khác | Provision JDK và tạo file toolchain cho runner |
| Discovery không thấy JDK | JDK nằm ngoài vị trí heuristic hoặc env chưa được khai báo | Dùng toolchains.xml thủ công hoặc kiểm tra JAVA17_HOME |
| Plugin không dùng JDK đã chọn | Plugin không hỗ trợ toolchain | Xem tài liệu plugin hoặc cấu hình executable riêng nếu plugin hỗ trợ |

### 17.1. Chẩn đoán từng bước

Khi gặp lỗi:

1. Xác nhận Maven runtime bằng mvn -version.
2. Xác nhận file toolchains.xml đúng user và đúng đường dẫn.
3. Mở file XML và kiểm tra cấu trúc type/provides/configuration.
4. Kiểm tra thư mục jdkHome có tồn tại và chứa bin/javac, bin/java.
5. So sánh version/vendor yêu cầu trong POM với metadata của entry.
6. Chạy mvn -X validate để xem plugin chọn toolchain nào.
7. Kiểm tra plugin cần dùng có hỗ trợ toolchain và phiên bản đủ mới không.
8. Nếu lỗi ở test, kiểm tra Surefire/Failsafe fork và jdkToolchain.
9. Chạy lại cùng lệnh trong môi trường CI với log chọn JDK được lưu.

## 18. Các lựa chọn thay thế và giới hạn

Có thể chỉ định javac executable trực tiếp trong Compiler Plugin bằng fork và executable. Cách này chỉ cấu hình compiler plugin; không tự động cung cấp cùng JDK cho Surefire, Javadoc hoặc plugin khác.

Ví dụ:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.16.0</version>
  <configuration>
    <fork>true</fork>
    <executable>C:/Java/jdk-17/bin/javac</executable>
  </configuration>
</plugin>
~~~

Cách này phụ thuộc đường dẫn hệ thống và làm POM kém portable. Toolchains thường phù hợp hơn khi nhiều plugin cần cùng JDK.

Một số giới hạn cần nhớ:

- Toolchain chỉ áp dụng cho plugin có hỗ trợ.
- Toolchain không thay đổi JVM đang chạy Maven.
- toolchains.xml không cài đặt, cập nhật hoặc xác minh nguồn gốc JDK.
- Version/vendor trong provides là metadata match.
- Plugin có thể override toolchain chung bằng jdkToolchain.
- JDK toolchain và compiler release là hai cấu hình độc lập.
- Công cụ native hoặc plugin tùy chỉnh cần hỗ trợ toolchain riêng mới sử dụng được.

## 19. Thực hành tốt cho build ổn định

- Pin phiên bản Maven Wrapper và phiên bản các plugin build quan trọng.
- Chọn version range đủ chặt, ví dụ [17,18), thay vì [17,) nếu dự án yêu cầu đúng major.
- Thống nhất vendor metadata trong team và CI.
- Provision cùng distribution/patch level JDK nếu build cần tái lập chặt chẽ.
- Giữ toolchains.xml ở user home hoặc CI secret/config riêng, không commit đường dẫn local.
- Để build fail sớm khi không tìm thấy JDK bắt buộc.
- Ghi log JDK runtime và toolchain selection.
- Dùng test xác minh Runtime.version() khi JDK test là yêu cầu quan trọng.
- Xem xét plugin-specific jdkToolchain chỉ khi thật sự cần nhiều JDK trong một build.
- Không giả định plugin nào cũng sử dụng toolchain.
- Đối chiếu Maven runtime, compiler JDK, test JDK và release target khi điều tra lỗi tương thích.

## 20. Checklist Maven Toolchain

- [ ] Đã xác định JDK dùng để chạy Maven.
- [ ] Đã xác định JDK toolchain mà dự án yêu cầu.
- [ ] Đã phân biệt toolchain JDK với maven.compiler.release.
- [ ] JDK đầy đủ đã được cài trên máy/CI runner.
- [ ] toolchains.xml có entry type jdk và jdkHome hợp lệ.
- [ ] Version range và vendor metadata match với entry.
- [ ] Maven Toolchains Plugin được pin phiên bản và có execution goal toolchain.
- [ ] Compiler Plugin hỗ trợ toolchain và cấu hình release đúng.
- [ ] Surefire/Failsafe sử dụng JDK mong muốn khi chạy test.
- [ ] Đã kiểm tra plugin-specific jdkToolchain nếu có override.
- [ ] Đã xác minh log toolchain selection.
- [ ] Đã kiểm tra Runtime.version() trong test nếu cần.
- [ ] CI runner có JDK và toolchains.xml phù hợp.
- [ ] Đường dẫn local không bị hardcode vào POM hoặc commit nhầm.
- [ ] Build fail rõ ràng khi không tìm được toolchain bắt buộc.

Maven Toolchains giúp tách yêu cầu JDK của dự án khỏi JDK đang chạy Maven. POM khai báo tiêu chí, toolchains.xml hoặc discovery cung cấp JDK đã cài, và các plugin hỗ trợ sử dụng toolchain đã chọn. Hãy kiểm tra cả Maven runtime, compiler JDK, test JVM và release target để bảo đảm build thực sự dùng đúng Java version ở từng bước.

## Tài liệu tham khảo

- Apache Maven, Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Apache Maven Toolchains Plugin, Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Apache Maven Toolchains Plugin, JDK Discovery Mechanism: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html
- Apache Maven Toolchains Plugin, JDK Toolchain: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html
- Apache Maven Compiler Plugin, Compiling Sources Using a Different JDK: https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html
- Apache Maven Surefire Plugin, Using Maven Toolchains: https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html
- Apache Maven Toolchains Plugin, Plugin Details and System Requirements: https://maven.apache.org/plugins/maven-toolchains-plugin/plugin-info.html
