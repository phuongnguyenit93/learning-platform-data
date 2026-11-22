# Phân biệt phiên bản Maven, phiên bản POM và phiên bản plugin

Một dự án Maven có thể đồng thời hiển thị các số như `3.9.x`, `4.0.0`, `1.2.0-SNAPSHOT`, `3.13.0` và `17`. Chúng thuộc **những thành phần khác nhau**, không cần giống nhau và không tự tăng cùng lúc. Bài này giúp xác định từng số, nơi cấu hình, cách kiểm tra và tác động khi nâng cấp.

## 1. Bản đồ các loại phiên bản

| Thành phần | Ví dụ | Ý nghĩa | Xem/cấu hình ở đâu? |
| --- | --- | --- | --- |
| **Maven runtime (Maven Core)** | `3.9.x` hoặc `4.x` | Phiên bản chương trình Maven thực sự chạy lệnh build | `mvn --version`; hoặc phiên bản Maven Wrapper được ghim trong `.mvn/wrapper/maven-wrapper.properties` |
| **POM model version** | `<modelVersion>4.0.0</modelVersion>` | Phiên bản **mô hình/cấu trúc POM** mà tệp `pom.xml` tuân theo | Phần tử `<modelVersion>` của `pom.xml` |
| **Project/artifact version** | `<version>1.2.0-SNAPSHOT</version>` | Phiên bản sản phẩm mà dự án tạo và có thể publish | `<project><version>` hoặc kế thừa từ `<parent>` |
| **Plugin version** | `maven-compiler-plugin:3.13.0` | Phiên bản công cụ mở rộng Maven để thực hiện một goal, ví dụ biên dịch | `<build><plugins>`, `<pluginManagement>` và effective POM |
| **Java release** (khác cả bốn mục trên) | `<maven.compiler.release>17</maven.compiler.release>` | Phiên bản Java API/ngôn ngữ/bytecode mục tiêu của trình biên dịch | Thuộc tính hoặc cấu hình compiler plugin |

Trong cách nói “phiên bản POM”, cần phân biệt **`<modelVersion>`** (định dạng POM) với **`<project><version>`** (phiên bản artifact). Đây là hai giá trị thường bị gọi chung nhưng mang ý nghĩa hoàn toàn khác.

## 2. Phiên bản Maven: chương trình thực thi build

Apache Maven là chương trình đọc POM, lập kế hoạch lifecycle, giải quyết dependencies và gọi các plugin. Lệnh sau cho biết phiên bản Maven mà terminal đang dùng:

```bash
mvn --version
```

Đầu ra sẽ bao gồm một dòng dạng `Apache Maven 3.9.x` hoặc `Apache Maven 4.x`, cùng thông tin Java runtime và hệ điều hành. Giá trị thực phụ thuộc bản cài đặt và `PATH` của máy.

Nếu dự án có **Maven Wrapper**, ưu tiên chạy script đi kèm dự án để dùng phiên bản Maven đã được nhóm thống nhất:

```bash
# Linux/macOS
./mvnw --version

# Windows (Command Prompt/PowerShell)
mvnw.cmd --version
```

Wrapper lấy bản Maven theo `distributionUrl` trong `.mvn/wrapper/maven-wrapper.properties`. Phiên bản *Maven Wrapper/Wrapper Plugin* cũng là một thành phần riêng, không đồng nghĩa với phiên bản Maven distribution mà wrapper tải về. Vì vậy `mvn --version` và `./mvnw --version` có thể cho hai phiên bản Maven khác nhau.

**Điểm cần nhớ:** đổi `<version>`, `<modelVersion>` hoặc phiên bản compiler plugin trong `pom.xml` **không đổi** chương trình Maven đang được gọi. Muốn đổi Maven runtime, cập nhật bản cài đặt/toolchain CI hoặc cấu hình wrapper rồi xác minh lại bằng lệnh `--version`.

## 3. Phiên bản POM: modelVersion khác project.version

### 3.1. `<modelVersion>` mô tả kiểu cấu trúc POM

Với dự án Maven 3, cấu trúc POM thông dụng là:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>vn.example</groupId>
  <artifactId>version-demo</artifactId>
  <version>1.2.0-SNAPSHOT</version>
</project>
```

Số `4.0.0` ở `<modelVersion>` **không có nghĩa dự án đang chạy Maven 4**, và không phải phiên bản phát hành của `version-demo`. Một dự án chạy Maven 3 vẫn dùng POM model `4.0.0`.

**Với Maven 4:** Maven 4 vẫn hỗ trợ build POM model `4.0.0`; model `4.1.0` dành cho build POM sử dụng các tính năng mới của Maven 4. POM `4.1.0` đòi hỏi công cụ hỗ trợ mô hình đó, vì vậy không nên đổi `4.0.0` thành `4.1.0` chỉ để “nâng phiên bản Maven”. Maven 4 thường tạo *consumer POM* model `4.0.0` khi publish để giữ khả năng tương thích với hệ sinh thái; có ngoại lệ với những tính năng không chuyển đổi được.

### 3.2. `<project><version>` là phiên bản artifact

Ba tọa độ chính của artifact là `groupId:artifactId:version`. Trong ví dụ trên, chúng tạo tọa độ:

```text
vn.example:version-demo:1.2.0-SNAPSHOT
```

- `1.2.0-SNAPSHOT` là phiên bản đang phát triển; `1.2.0` thường chỉ bản phát hành tương ứng theo quy ước của nhóm.
- Khi đóng gói `jar`, tên file thường chứa `artifactId` và `version`, ví dụ `version-demo-1.2.0-SNAPSHOT.jar` (nếu không tùy biến `finalName`).
- `groupId` và `version` của dự án con có thể kế thừa từ POM cha; trong trường hợp này không nhất thiết xuất hiện trực tiếp tại root `pom.xml` của dự án con.

Số `<parent><version>` là **phiên bản POM cha** mà dự án tham chiếu; số `<dependency><version>` là **phiên bản thư viện phụ thuộc**; cả hai đều không phải phiên bản Maven Core hay compiler plugin. Một POM có nhiều thẻ `<version>`, nên cần xem **đường dẫn XML đầy đủ** trước khi kết luận.

Ví dụ các phiên bản thuộc những đối tượng khác nhau:

```xml
<parent>
  <groupId>vn.example</groupId>
  <artifactId>company-parent</artifactId>
  <version>2.5.0</version>
</parent>
<!-- ... -->
<dependencies>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter-api</artifactId>
    <version>5.11.0</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Đây là **đoạn minh họa**, chưa phải một POM hoàn chỉnh. `2.5.0` thuộc parent, `5.11.0` thuộc JUnit; chúng không buộc phải khớp phiên bản dự án.

## 4. Phiên bản plugin: công cụ thực hiện từng việc trong build

Maven Core điều phối build, còn các **plugin** thực hiện công việc cụ thể. Ví dụ:

- `maven-compiler-plugin`: biên dịch Java (`compile`, `testCompile`).
- `maven-surefire-plugin`: chạy unit tests theo cấu hình của plugin.
- `maven-jar-plugin`: đóng gói JAR.

Mỗi plugin là một artifact có tọa độ và **version riêng**. `maven-compiler-plugin:3.13.0` không có nghĩa Maven Core phải là `3.13.0`; nó chỉ có nghĩa đang dùng bản `3.13.0` của Compiler Plugin. Một plugin có thể có yêu cầu tối thiểu riêng đối với Maven runtime và JDK. Ví dụ, Compiler Plugin `3.13.0` yêu cầu Maven từ `3.6.3` và JDK để chạy plugin từ `8`, trong khi cấu hình biên dịch mã Java 17 vẫn cần JDK/toolchain thích hợp.

Nên **ghim phiên bản plugin** để build có thể tái lập. Nếu bỏ `<version>` của plugin, Maven có thể lấy phiên bản theo cấu hình được kế thừa, `pluginManagement`, super POM, lifecycle binding hoặc cơ chế phân giải plugin; vì thế hai môi trường Maven khác nhau có thể dùng plugin khác phiên bản.

### `<plugins>` và `<pluginManagement>`

- `<build><plugins>` khai báo các plugin được cấu hình/tham gia build của dự án.
- `<build><pluginManagement>` đặt phiên bản/cấu hình mặc định cho plugin được tham chiếu hoặc gắn với lifecycle; **không tự nó tạo một execution mới** cho mọi plugin được liệt kê.
- Dự án con có thể kế thừa quản lý phiên bản từ parent và có thể ghi đè khi cần.

Ví dụ dưới đây quản lý phiên bản compiler plugin tập trung, rồi tham chiếu plugin đó trong build:

```xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
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
```

Đây là **đoạn XML đặt trong `<project>`**, không phải một tệp POM độc lập.

## 5. Ví dụ POM đầy đủ: bốn số cùng xuất hiện

Giả sử môi trường chạy **Maven 3.9.x**, có **JDK 17**, với tệp `pom.xml` sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>vn.example</groupId>
  <artifactId>version-demo</artifactId>
  <version>1.2.0-SNAPSHOT</version>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Đọc đúng ví dụ:

1. **`Maven 3.9.x`**: phiên bản Maven runtime giả định, xác định bằng `mvn --version`; không nằm trong POM này.
2. **`<modelVersion>4.0.0</modelVersion>`**: mô hình POM tương thích Maven 3.
3. **`<version>1.2.0-SNAPSHOT</version>`** dưới `<project>`: phiên bản của artifact `vn.example:version-demo`.
4. **`<version>3.13.0</version>`** dưới `maven-compiler-plugin`: phiên bản plugin biên dịch.
5. **`<maven.compiler.release>17</maven.compiler.release>`**: Java release mục tiêu; **không** phải phiên bản Maven, model hay plugin. Cần JDK phù hợp để biên dịch Java 17.

Có thể tạo tệp `src/main/java/vn/example/App.java`:

```java
package vn.example;

public class App {
    public static void main(String[] args) {
        System.out.println("Hello Maven");
    }
}
```

Sau đó, tại thư mục chứa `pom.xml`:

```bash
mvn --version
mvn package
java -cp target/version-demo-1.2.0-SNAPSHOT.jar vn.example.App
```

Nếu build thành công trên JDK 17 và dùng packaging JAR mặc định, lệnh `java` in chính xác:

```text
Hello Maven
```

Lưu ý: log `mvn package`, quá trình tải plugin/dependency lần đầu và tên phiên bản Maven thật phụ thuộc môi trường, nên không có một stdout chung để sao chép cho các lệnh Maven.

## 6. Kiểm tra phiên bản đang có hiệu lực

Chạy lệnh tại thư mục dự án:

```bash
# Phiên bản công cụ Maven thực thi từ PATH
mvn --version

# Phiên bản artifact dự án đã tính cả kế thừa/nội suy
mvn help:evaluate -Dexpression=project.version -q -DforceStdout

# POM hiệu lực sau khi ghép parent, profiles, pluginManagement...
mvn help:effective-pom -Doutput=effective-pom.xml
```

Với POM độc lập của mục 5, lệnh `help:evaluate` trả về `1.2.0-SNAPSHOT` (khi help plugin thực thi bình thường). Mở `effective-pom.xml` để kiểm tra phiên bản plugin thực tế, nhất là khi dự án dùng parent POM, profile, lifecycle mặc định hoặc `pluginManagement`. Nếu dùng Wrapper, thay `mvn` bằng `./mvnw` trên Unix hoặc `mvnw.cmd` trên Windows trong các lệnh trên.

**Cẩn thận:** `mvn --version` chỉ cho biết Maven/Core và Java đang chạy; nó không liệt kê phiên bản của tất cả plugin. `help:effective-pom` mô tả POM hiệu lực, nhưng plugin gọi trực tiếp qua CLI với tọa độ đầy đủ như `org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile` có thể chỉ định phiên bản riêng ngay trong lệnh.

## 7. Khi nào cần đổi số nào?

| Mục đích | Thay đổi đúng chỗ | Điều cần xác minh |
| --- | --- | --- |
| Cập nhật Maven dùng trong máy/CI | Cài đặt Maven, `PATH` hoặc `distributionUrl` của Wrapper | `mvn --version` hoặc `mvnw --version`, phiên bản JDK dùng chạy Maven |
| Phát hành artifact mới | `<project><version>` hoặc quy trình quản lý release của dự án | `groupId:artifactId:version`, dependency tham chiếu và tên artifact tạo ra |
| Dùng tính năng POM dành riêng Maven 4 | Migrate sang Maven 4, rồi cân nhắc POM model `4.1.0` | Maven runtime/JDK, cú pháp POM, khả năng tương thích công cụ |
| Nâng compiler/test/package plugin | `<plugin><version>` hoặc bản được quản lý trong `pluginManagement` | Yêu cầu Maven/JDK tối thiểu, thay đổi behavior và kết quả build |
| Đổi Java language/API target | `<maven.compiler.release>` hay `<configuration><release>` | JDK/toolchain thực sự sử dụng, khả năng chạy trên Java đích |

Khi nâng Maven 3 lên Maven 4, **không cần** nâng `modelVersion` lên `4.1.0` nếu chưa dùng tính năng POM mới; đồng thời phải xem yêu cầu Java của Maven Core và độ tương thích của các plugin. Nâng plugin có thể phá vỡ build cũ dù `<modelVersion>` và `<project><version>` giữ nguyên.

## 8. Lỗi hiểu nhầm thường gặp

- **“`modelVersion` là `4.0.0` nên đang dùng Maven 4.”** Sai: Maven 3 thường dùng model `4.0.0`; cần xem `mvn --version`.
- **“Đổi `<project><version>` thì nâng Maven.”** Sai: thay đổi danh tính artifact, không cập nhật runtime.
- **“Compiler plugin `3.13.0` phải chạy trên Maven `3.13.0`.”** Sai: plugin và Core có đường phát hành khác nhau; kiểm tra *System Requirements* của plugin.
- **“`maven.compiler.release=17` nghĩa Maven phiên bản 17.”** Sai: đây là Java release target.
- **“Chỉ cần nâng Maven thì mọi plugin cũng lên bản mới.”** Sai: bản plugin có thể được ghim trong POM/parent; kiểm tra effective POM.
- **“Thêm plugin vào `pluginManagement` luôn khiến goal đó chạy.”** Sai: còn phụ thuộc lifecycle binding, `<plugins>` và executions.
- **“Thấy thẻ `<version>` nào cũng là version của project.”** Sai: xác định nó thuộc `parent`, `dependency`, `plugin` hay root `project`.
- **“Tăng `modelVersion` lên `4.1.0` giúp Maven 3 dùng tính năng mới.”** Sai: các tính năng model `4.1.0` yêu cầu Maven 4 hỗ trợ.

## 9. Bài tự kiểm tra nhanh

Một máy báo `Apache Maven 3.9.x` khi chạy `mvn --version`, trong `pom.xml` có `<modelVersion>4.0.0</modelVersion>`, root `<version>2.1.0</version>` và `maven-surefire-plugin` ở bản `3.5.2`. Hỏi bốn phiên bản nào tương ứng với runtime, mô hình POM, artifact và plugin?

**Đáp án:** Maven runtime = `3.9.x`; POM model = `4.0.0`; artifact = `2.1.0`; Surefire plugin = `3.5.2`. Các số được quản lý độc lập theo mục đích sử dụng.

## Tài liệu chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven — Compiler Plugin 3.13.0](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/plugin-info.html)
