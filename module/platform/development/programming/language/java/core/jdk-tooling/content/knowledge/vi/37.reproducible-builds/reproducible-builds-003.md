# Pin compiler release trong Java và Maven

Pin compiler release là việc cố định phiên bản Java mà source code được phép sử dụng và class file được tạo ra. Trong Maven, cấu hình thường dùng là thuộc tính maven.compiler.release kết hợp với một phiên bản maven-compiler-plugin đã được pin rõ ràng.

Ví dụ, dự án đặt release 17. Compiler sẽ kiểm tra cú pháp Java 17, chỉ cho phép API thuộc nền tảng Java 17 và tạo bytecode có thể chạy trên Java 17 trở lên. Nhờ vậy, developer dùng JDK mới hơn vẫn có thể build ứng dụng nhắm tới một Java release đã thống nhất.

Cần phân biệt ba thứ: release mục tiêu của source, JDK thực tế chạy compiler và JDK chạy ứng dụng/test. Pin release không tự pin hai JDK còn lại. Muốn build ổn định, cần quản lý cả ba.

## 1. Compiler release là gì?

Java compiler có thể biên dịch source theo một Java release cụ thể. Release xác định:

- Quy tắc cú pháp và ngôn ngữ Java được chấp nhận.
- Tập API Java SE/JDK được phép tham chiếu.
- Phiên bản class-file mà compiler sinh ra.

Ví dụ, khi dùng JDK 24 để biên dịch với release 17, compiler phải từ chối cú pháp chỉ có từ Java 21 trở lên, không cho source sử dụng API mới hơn Java 17 và tạo class file có major version 61.

Đây là cơ chế cross-compilation: dùng compiler của một JDK mới hơn để tạo output tương thích với release cũ hơn mà compiler hỗ trợ.

Giá trị release theo Java version scheme hiện đại là số nguyên như 8, 11, 17, 21 hoặc 24. Với Java 8, ghi 8, không ghi 1.8.

## 2. Vì sao phải pin compiler release?

Nếu không pin release, compiler có thể dùng mặc định theo JDK đang chạy Maven. Khi developer nâng JDK, source mới có thể vô tình sử dụng cú pháp hoặc API mới; artifact cũng có thể được tạo với class-file version cao hơn.

Hệ quả thường gặp:

- Ứng dụng chạy trên máy developer nhưng lỗi UnsupportedClassVersionError trên production.
- Source dùng API chỉ có ở JDK mới hơn môi trường triển khai.
- Các module trong cùng dự án tạo bytecode ở những mức Java khác nhau.
- CI và máy developer chấp nhận source khác nhau.
- Việc nâng JDK làm thay đổi mục tiêu tương thích ngoài ý muốn.

Pin release giúp cả dự án có một hợp đồng tương thích rõ ràng. CI có thể kiểm tra hợp đồng này và thất bại ngay khi source vượt quá mức Java được phép.

## 3. Phân biệt release, source, target và JDK compiler

Đây là bốn khái niệm cần tách biệt:

| Cấu hình | Điều khiển điều gì? |
|---|---|
| JDK compiler | Phiên bản javac thực sự biên dịch source |
| source | Cú pháp/ngôn ngữ Java mà compiler chấp nhận |
| target | Phiên bản class-file mà compiler tạo ra |
| release | Kết hợp quy tắc ngôn ngữ, class-file target và API được công bố cho release đó |

Trước Java 9, các dự án thường dùng source và target. Hai tham số này không tự giới hạn API có sẵn trong JDK dùng để compile.

Ví dụ, dùng JDK 17 với source 8 và target 8 nhưng gọi String.strip() vẫn có thể biên dịch, vì method này tồn tại trong JDK 17. Class file tạo ra có thể mang version Java 8 nhưng chạy trên Java 8 sẽ lỗi NoSuchMethodError khi gọi API không tồn tại.

Với javac từ JDK 9 trở lên, nên dùng release. Tùy chọn này kiểm tra cả API của release đích nên phát hiện lỗi tương thích sớm hơn.

## 4. javac --release hoạt động như thế nào?

Tùy chọn --release được giới thiệu trong JDK 9. Nó yêu cầu javac:

1. Áp dụng quy tắc ngôn ngữ của release được chọn.
2. Tạo class file hướng tới release đó.
3. Biên dịch dựa trên API Java SE và JDK được công bố cho release đó.
4. Không cho dùng các API nội bộ hoặc API chỉ xuất hiện ở release mới hơn.

Ví dụ biên dịch Java 17:

~~~powershell
javac --release 17 -d out src\main\java\demo\App.java
~~~

Ví dụ biên dịch Java 8 bằng compiler JDK mới:

~~~powershell
javac --release 8 -d out src\main\java\demo\App.java
~~~

Compiler chỉ chấp nhận các release được JDK hiện tại hỗ trợ. Kiểm tra danh sách bằng:

~~~powershell
javac --help
~~~

Không thể dùng --release đồng thời với --source hoặc --target. javac cũng không cho dùng --add-exports để mở rộng API hệ thống khi đang dùng --release. Điều này giúp giữ đúng ranh giới API của nền tảng mục tiêu.

## 5. Vì sao source và target riêng lẻ chưa đủ?

Giả sử dự án phải chạy trên Java 8 nhưng compiler đang chạy trên JDK 17.

Cấu hình cũ:

~~~xml
<configuration>
  <source>8</source>
  <target>8</target>
</configuration>
~~~

Cấu hình này đặt cú pháp Java 8 và class-file target Java 8. Tuy nhiên, compiler vẫn nhìn thấy API của JDK 17. Source có thể gọi method không tồn tại trong Java 8.

Ví dụ:

~~~java
public final class ApiCheck {
    public String normalize(String value) {
        return value.strip();
    }
}
~~~

String.strip() được thêm từ Java 11. Khi compile bằng JDK 17 với source 8/target 8, API mới vẫn có thể được tham chiếu. Chạy trên Java 8 sẽ thất bại khi thực thi đường code đó.

Nếu dùng:

~~~powershell
javac --release 8 ApiCheck.java
~~~

compiler báo không tìm thấy method strip() trong String của Java 8. Đây là lợi ích quan trọng nhất của release so với source/target.

## 6. Cấu hình Maven Compiler Plugin

Maven Compiler Plugin hỗ trợ tham số release từ phiên bản 3.6.0. Nên pin version plugin để mọi máy build dùng cùng cấu hình và hành vi.

Ví dụ POM:

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
      <version>3.13.0</version>
      <configuration>
        <release>${maven.compiler.release}</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Thuộc tính maven.compiler.release là nơi lưu mục tiêu Java duy nhất của dự án. Cấu hình release trong plugin tham chiếu thuộc tính đó để tránh lặp số version.

Có thể chỉ đặt property mà không khai báo release trực tiếp vì Compiler Plugin nhận user property maven.compiler.release. Tuy nhiên, khai báo plugin version rõ ràng vẫn rất quan trọng; không nên phụ thuộc vào version mặc định từ Super POM.

## 7. Pin plugin version và quản lý trong parent POM

Một dự án nhiều module nên đặt release và plugin version ở parent POM để các module kế thừa cùng chính sách.

Ví dụ:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>${maven.compiler.release}</release>
          <encoding>${project.build.sourceEncoding}</encoding>
        </configuration>
      </plugin>
    </plugins>
  </pluginManagement>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
    </plugin>
  </plugins>
</build>
~~~

pluginManagement quản lý version và cấu hình mặc định. Plugin vẫn phải được khai báo trong build/plugins ở parent hoặc module cần chạy; chỉ đặt trong pluginManagement không tự kích hoạt plugin.

Với multi-module project, giữ một giá trị release ở parent trừ khi có module thật sự cần mức Java khác. Nếu module override release, ghi rõ lý do và kiểm tra dependency giữa các module.

## 8. Release ảnh hưởng cả main source và test source

Maven Compiler Plugin có hai goal chính:

- compiler:compile biên dịch source trong src/main/java.
- compiler:testCompile biên dịch source trong src/test/java.

Cấu hình release chung trong plugin được áp dụng cho cả hai goal. Điều này giữ test source ở cùng mức ngôn ngữ và API với production source, trừ khi dự án chủ ý cấu hình execution riêng.

Không nên để test source dùng API mới hơn chỉ vì máy CI có JDK mới. Test có thể pass trên CI nhưng che mất lỗi tương thích với Java runtime mục tiêu.

Nếu test cần một JDK runtime cụ thể, cấu hình Surefire/Failsafe hoặc Maven Toolchains riêng. Compiler release chỉ điều khiển việc biên dịch, không chọn JVM chạy test.

## 9. Release không pin JDK compiler

Giả sử hai máy đều cấu hình release 17:

- Máy A dùng javac từ JDK 17.
- Máy B dùng javac từ JDK 24.

Cả hai có thể tạo class file major version 61 và chỉ sử dụng API Java 17. Tuy nhiên, compiler implementation, optimization, bug fix và cách sinh bytecode có thể khác theo JDK patch/vendor.

Vì vậy, release pin bảo đảm mục tiêu tương thích của source và bytecode; nó không bảo đảm artifact giống từng byte.

Nếu cần build tái lập nghiêm ngặt, hãy cố định thêm:

- JDK vendor và version/patch.
- Maven distribution.
- Maven Compiler Plugin version.
- Annotation processor và dependency của nó.
- Toolchain compiler thực tế.
- Các plugin khác tham gia tạo artifact.

Maven Compiler Plugin mặc định sử dụng javac của JDK chạy Maven. Có thể chọn compiler JDK khác bằng Maven Toolchains khi cần. Luôn kiểm tra log để xác nhận toolchain được sử dụng.

## 10. Phân biệt compiler release với test/runtime JDK

Một cấu hình release 17 có thể được build trên JDK 24 và tạo bytecode Java 17. Nhưng lệnh mvn test có thể chạy test trong JVM của Maven hoặc một forked JVM khác.

Các trường hợp:

| Thành phần | Ví dụ version |
|---|---|
| Maven runtime JDK | 24 |
| Compiler toolchain JDK | 24 |
| Compiler release | 17 |
| Surefire forked test JDK | 17 |
| Production runtime | 17 |

Release 17 không tự chuyển Surefire sang Java 17. Nếu Surefire không fork, test chạy trong Maven JVM; nếu fork, JVM test phụ thuộc cấu hình plugin/toolchain.

Khi cần bảo đảm tương thích runtime, hãy chạy test trên đúng Java release mục tiêu hoặc dùng CI matrix với các JDK được hỗ trợ. Kiểm tra Runtime.version() trong test để xác nhận JVM đang thực thi.

## 11. Phiên bản Java và class-file major version

Mỗi Java release có class-file major version tương ứng. Một số mốc phổ biến:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Nếu class được tạo với major version 65, JVM Java 17 không thể nạp class đó. Nếu compiler dùng release 17, class file phải có major version 61.

Kiểm tra bằng javap:

~~~powershell
javap -verbose target\classes\demo\App.class | Select-String "major version"
~~~

Output mong đợi cho release 17:

~~~text
major version: 61
~~~

Class-file version là một kiểm tra hữu ích nhưng không chứng minh API compatibility một mình. Cần dùng release khi compile để kiểm tra API, và test trên runtime thật để kiểm tra hành vi.

## 12. Ví dụ Maven hoàn chỉnh: pin Java 17

Tạo cấu trúc:

~~~text
pin-release-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          App.java
~~~

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>pin-release-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-clean-plugin</artifactId>
        <version>3.4.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-resources-plugin</artifactId>
        <version>3.3.1</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>${maven.compiler.release}</release>
          <encoding>${project.build.sourceEncoding}</encoding>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>demo.App</mainClass>
            </manifest>
          </archive>
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
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Compiler release pinned to Java 17.");
    }
}
~~~

Build:

~~~powershell
mvn clean package
~~~

Chạy JAR:

~~~powershell
java -jar target\pin-release-demo-1.0.0.jar
~~~

Stdout:

~~~text
Compiler release pinned to Java 17.
~~~

Kiểm tra class-file version:

~~~powershell
javap -verbose target\classes\demo\App.class | Select-String "major version"
~~~

Output:

~~~text
major version: 61
~~~

Nếu Maven chạy bằng JDK 24, build vẫn tạo bytecode Java 17 nhờ release 17. Chạy JAR trên Java 17 sẽ in đúng dòng output như trên.

## 13. Kiểm tra compiler release thực tế trong Maven

Dùng các lệnh sau để kiểm tra cấu hình:

~~~powershell
mvn -version
mvn help:effective-pom
mvn help:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
mvn -X clean verify
~~~

Mỗi lệnh trả lời một câu hỏi:

- mvn -version: Maven đang chạy trên JDK nào?
- help:effective-pom: cấu hình compiler hiệu lực sau khi kế thừa parent/profile là gì?
- help:evaluate: giá trị release cuối cùng được Maven resolve là bao nhiêu?
- -X: plugin nhận cấu hình và gọi compiler như thế nào?

Không chỉ nhìn POM source vì parent POM, profile và command-line property có thể override giá trị. Kiểm tra effective POM và log trên đúng CI job tạo artifact.

## 14. Dùng Maven Enforcer và CI để ngăn cấu hình sai

Nếu tổ chức yêu cầu Maven phải chạy trên một JDK cụ thể, dùng Maven Enforcer Plugin để kiểm tra runtime. Ví dụ:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.6.3</version>
  <executions>
    <execution>
      <id>enforce-java-runtime</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireJavaVersion>
            <version>[17,18)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Ví dụ trên yêu cầu Maven runtime dùng Java 17. Nếu chính sách cho phép JDK 21 hoặc 24 làm compiler nhưng vẫn tạo release 17, không dùng range này; thay bằng range phù hợp hoặc pin compiler toolchain riêng.

Trong CI:

1. Dùng Maven Wrapper để pin Maven distribution.
2. Provision JDK compiler theo chính sách.
3. Đọc release từ POM/parent POM.
4. Chạy clean verify.
5. Kiểm tra class-file major version của artifact.
6. Chạy test trên các runtime Java mà sản phẩm tuyên bố hỗ trợ.
7. Lưu log JDK, Maven và compiler configuration cùng build.

Không để biến môi trường hoặc tham số -D thay đổi maven.compiler.release ngoài ý muốn.

## 15. Annotation processor và generated source

Annotation processor chạy trong môi trường compiler JDK. Release mục tiêu giới hạn source được compile và API nền tảng mà code đó được phép dùng, nhưng không tự giới hạn runtime API mà annotation processor sử dụng.

Nếu processor tạo source:

- Pin version của processor và dependency của nó.
- Kiểm tra generated source có dùng cú pháp/API mới hơn release không.
- Cố định đầu vào và thứ tự xử lý.
- Không ghi thời gian, username, đường dẫn tuyệt đối hoặc random value vào generated source.
- Kiểm tra generated source được compile trong cùng execution với release đã pin.

Một build có thể pin compiler release đúng nhưng vẫn tạo output khác nếu annotation processor thay đổi hoặc phụ thuộc môi trường.

## 16. Preview features và module system

Preview feature gắn với một Java release cụ thể. Khi bật preview, compiler và runtime phải tuân thủ yêu cầu của release tương ứng; preview bytecode không phải mục tiêu tương thích ổn định giữa các phiên bản.

Nếu dùng preview, cần cấu hình compiler argument --enable-preview và cấu hình JVM test/runtime tương ứng. Chỉ bật preview khi dự án thật sự cần, vì nó làm tăng yêu cầu version và giảm khả năng chạy trên các runtime khác.

Với module system, release cũng kiểm soát API/module của release đích. Không thể dùng --add-exports để mở rộng API hệ thống khi javac đang dùng --release. Nếu ứng dụng phụ thuộc JDK internal API, nên thay bằng API được hỗ trợ thay vì cố phá giới hạn tương thích.

## 17. Java 8 và giới hạn của --release

JDK 8 không có javac --release. Tùy chọn này chỉ xuất hiện từ JDK 9.

Maven Compiler Plugin 3.13.0 với compilerId mặc định javac có thể nhận cấu hình release khi chạy trên JDK 8 và chuyển sang source/target tương ứng. Trên JDK 9 trở lên, plugin sử dụng javac --release.

Điều này không biến JDK 8 thành compiler có khả năng kiểm tra API của một JDK cũ hơn. Nếu dùng JDK 8 để target Java 8, API compiler nhìn thấy chính là API Java 8. Nếu cần target thấp hơn JDK đang dùng và cần kiểm tra API chính xác, ưu tiên JDK 9+ với --release hoặc cung cấp platform API/boot class path phù hợp khi bắt buộc dùng source/target.

Không giả định mọi compilerId hoặc mọi phiên bản Maven Compiler Plugin có cùng fallback. Kiểm tra tài liệu đúng version plugin.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| UnsupportedClassVersionError | Class file mới hơn JVM runtime | Pin release đúng mức Java production hỗ trợ |
| Code dùng API mới vẫn compile | Chỉ đặt source/target | Dùng release với JDK 9+ |
| Unknown option --release | Đang chạy javac JDK 8 hoặc cũ hơn | Nâng compiler JDK hoặc dùng cấu hình tương thích |
| Maven bỏ qua release property | Compiler Plugin quá cũ hoặc cấu hình bị override | Pin plugin từ 3.6+ và xem effective POM |
| Một module có bytecode khác module khác | Module không kế thừa cùng parent/config | Đặt release tập trung ở parent và kiểm tra module |
| Test compile được nhưng chạy fail | Test/runtime JDK khác mục tiêu | Chạy test trên đúng runtime hoặc CI matrix |
| API mới xuất hiện trong generated code | Annotation processor/generator không tương thích release | Pin processor và kiểm tra generated source |
| Build local khác CI | JDK/toolchain/plugin version khác | Ghi nhận và pin compiler JDK, Maven và plugin |
| Preview feature không chạy | Compiler/runtime release không khớp hoặc thiếu enable-preview | Dùng cùng release và cấu hình preview cả hai phía |

### 18.1. Quy trình chẩn đoán

1. Chạy mvn -version để xác định JDK chạy Maven.
2. Kiểm tra maven.compiler.release trong effective POM.
3. Kiểm tra version Maven Compiler Plugin.
4. Đọc log compiler để xác định JDK/toolchain thực tế.
5. Dùng javap -verbose kiểm tra major version.
6. Tìm API mới hơn release trong source và generated source.
7. Kiểm tra JDK runtime của Surefire/Failsafe.
8. Tái hiện build bằng đúng Maven/JDK/toolchain của CI.

## 19. Thực hành tốt khi pin compiler release

- Chọn một Java release phù hợp với runtime production.
- Đặt maven.compiler.release ở parent POM.
- Pin Maven Compiler Plugin version rõ ràng.
- Không đồng thời cấu hình release với source/target trên JDK 9+.
- Dùng JDK compiler mới hơn chỉ khi release đích được hỗ trợ.
- Pin compiler JDK bằng Toolchains nếu cần reproducible bytecode.
- Kiểm tra cả main source và test source.
- Chạy test trên runtime Java thực tế được hỗ trợ.
- Pin annotation processor và code generator.
- Xác minh effective POM và class-file major version trong CI.
- Tránh thay release qua command-line property không được kiểm soát.
- Ghi lại Maven/JDK/plugin versions trong build metadata.

## 20. Checklist pin compiler release

- [ ] Đã chọn Java release mục tiêu theo runtime production.
- [ ] Đã đặt maven.compiler.release trong POM/parent POM.
- [ ] Đã pin version maven-compiler-plugin.
- [ ] Compiler Plugin có hỗ trợ tham số release.
- [ ] Không đặt source/target đồng thời với release trên JDK 9+.
- [ ] Đã hiểu JDK compiler thực tế có thể khác release mục tiêu.
- [ ] Đã dùng Maven Toolchains nếu cần pin compiler JDK riêng.
- [ ] Main source và test source dùng release nhất quán.
- [ ] Surefire/Failsafe chạy trên runtime đã được xác định.
- [ ] Annotation processor và generated source đã được kiểm tra.
- [ ] Preview features không bị bật ngoài ý muốn.
- [ ] Effective POM và Maven debug log đã được kiểm tra.
- [ ] Class-file major version khớp release mục tiêu.
- [ ] CI có bước kiểm tra compiler/runtime compatibility.
- [ ] Artifact đã được thử trên Java runtime thấp nhất được hỗ trợ.

Pin compiler release tạo ra một hợp đồng tương thích rõ ràng cho source và bytecode. Trong Maven, đặt maven.compiler.release, pin Maven Compiler Plugin và xác minh class-file version. Khi cần build tái lập ở mức byte-for-byte, tiếp tục pin JDK compiler, Maven, plugin và annotation processor; khi cần bảo đảm ứng dụng chạy được, kiểm thử trên runtime Java thực tế. Release, compiler JDK và test/runtime JDK phải được theo dõi như ba cấu hình riêng.

## Tài liệu tham khảo

- Oracle, Java SE 17 — The javac Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- OpenJDK, JEP 247 — Compile for Older Platform Versions: https://openjdk.org/jeps/247
- Apache Maven Compiler Plugin 3.13.0 — Setting the --release of the Java Compiler: https://maven.apache.org/components/plugins-archives/maven-compiler-plugin-3.13.0/examples/set-compiler-release.html
- Apache Maven Compiler Plugin — Plugin Documentation: https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/plugin-info.html
- Apache Maven Compiler Plugin — compiler:compile parameters: https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html
- Apache Maven Enforcer Plugin — Require Java Version: https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html
