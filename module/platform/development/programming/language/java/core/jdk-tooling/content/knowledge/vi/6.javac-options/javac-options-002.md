# Tùy chọn --release của javac

`--release` là tùy chọn của trình biên dịch `javac` dùng để biên dịch mã nguồn theo một phiên bản Java mục tiêu cụ thể. Tùy chọn này giúp dự án được biên dịch bằng JDK mới hơn nhưng vẫn giữ khả năng chạy trên phiên bản Java cũ hơn đã chọn, trong phạm vi tương thích mà nền tảng Java cung cấp.

Ví dụ: có thể dùng JDK 21 để biên dịch ứng dụng hướng tới Java 17:

```sh
javac --release 17 -d out src/com/example/Main.java
```

Lệnh trên yêu cầu trình biên dịch tuân thủ đồng thời cú pháp ngôn ngữ Java 17, định dạng bytecode Java 17 và tập API nền tảng Java được công bố cho Java 17. Đây là điểm khác biệt quan trọng so với việc chỉ chọn mức `-source` và `-target`.

## 1. Vì sao cần --release?

Một dự án thường phải hỗ trợ phiên bản Java thấp nhất mà người dùng hoặc môi trường triển khai đang sử dụng. Trong khi đó, máy lập trình viên hoặc CI có thể đã cài JDK mới hơn.

Nếu chỉ biên dịch bằng JDK mới nhất theo mặc định, mã nguồn có thể vô tình sử dụng cú pháp hoặc API chỉ xuất hiện ở phiên bản mới. Bytecode tạo ra cũng có thể yêu cầu JVM mới hơn. Khi đem ứng dụng sang máy có Java cũ hơn, ứng dụng có thể không khởi động hoặc gặp lỗi liên kết lớp.

Ví dụ, nhóm phát triển cài JDK 21 nhưng ứng dụng cần chạy trên Java 17. Việc đặt `--release 17` giúp trình biên dịch phát hiện sớm các trường hợp như:

- Sử dụng cú pháp ngôn ngữ chỉ có từ Java 18 trở lên.
- Gọi API Java SE chưa tồn tại trong Java 17.
- Tạo bytecode có phiên bản cao hơn Java 17 có thể đọc.

Nhờ đó, nhiều lỗi tương thích được phát hiện ngay ở bước biên dịch, thay vì chỉ xuất hiện khi triển khai lên môi trường Java mục tiêu.

## 2. Cú pháp và điều kiện sử dụng

Cú pháp cơ bản:

```text
javac --release <version> [other-options] source-files
```

Ví dụ biên dịch theo Java 17:

```sh
javac --release 17 Main.java
```

Có thể kết hợp với các tùy chọn khác:

```sh
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Main.java
```

Ý nghĩa:

- `--release 17`: chọn Java 17 làm phiên bản nền tảng mục tiêu.
- `-encoding UTF-8`: đọc mã nguồn theo UTF-8.
- `-Xlint:all`: bật các nhóm cảnh báo của trình biên dịch.
- `-d out`: đặt các tệp `.class` được tạo vào thư mục `out`.
- `src/com/example/Main.java`: tệp mã nguồn cần biên dịch.

Tùy chọn `--release` được hỗ trợ từ JDK 9. Vì vậy, cần dùng JDK 9 trở lên để gọi tùy chọn này. JDK 8 không nhận biết `--release`; với JDK 8, cần dùng chính JDK 8 để biên dịch cho Java 8 hoặc nâng cấp JDK biên dịch.

Giá trị phiên bản được hỗ trợ phụ thuộc JDK đang chạy `javac`. Ví dụ, JDK 21 hỗ trợ các release từ 8 đến 21. Hãy xem danh sách được JDK hiện tại chấp nhận bằng:

```sh
javac --help
```

Không thể chọn một release mới hơn phiên bản JDK đang chạy trình biên dịch. JDK 17 không thể biên dịch với `--release 21`; cần dùng JDK 21 trở lên cho mục tiêu đó.

## 3. Ba lớp tương thích mà --release kiểm soát

`--release N` kết hợp ba yêu cầu:

### 3.1. Phiên bản ngôn ngữ nguồn

Trình biên dịch chỉ chấp nhận cú pháp Java có trong phiên bản mục tiêu. Ví dụ, nếu biên dịch theo Java 8, mã nguồn không thể dùng `var` cho biến cục bộ vì cú pháp này được giới thiệu sau Java 8.

### 3.2. Phiên bản bytecode

Trình biên dịch tạo định dạng tệp lớp tương ứng với phiên bản Java mục tiêu. JVM cũ hơn sẽ từ chối bytecode mới hơn với lỗi như `UnsupportedClassVersionError`.

### 3.3. API nền tảng Java

Trình biên dịch giới hạn các API nền tảng có thể tham chiếu ở tập API được công bố cho phiên bản mục tiêu. Ví dụ, khi biên dịch cho Java 8, không thể gọi một phương thức chỉ được bổ sung vào Java 11 như `String.strip()`.

Ba lớp này cần được kiểm soát cùng nhau. Chỉ tạo bytecode cũ chưa đủ nếu mã vẫn gọi API chỉ có trên JDK mới.

## 4. Khác biệt giữa --release, -source và -target

Ba tùy chọn có mục đích liên quan nhưng không tương đương:

| Tùy chọn | Kiểm soát | Giới hạn |
|---|---|---|
| `-source N` | Cú pháp/ngôn ngữ nguồn được chấp nhận | Không tự giới hạn API nền tảng theo Java N |
| `-target N` | Phiên bản định dạng bytecode đầu ra | Không tự giới hạn API mà mã nguồn có thể gọi |
| `--release N` | Ngôn ngữ nguồn, bytecode và API nền tảng của release N | Chỉ chọn được các release mà JDK hiện tại hỗ trợ |

Giả sử dùng JDK 21 nhưng đặt:

```sh
javac -source 17 -target 17 Main.java
```

Trình biên dịch kiểm tra cú pháp theo Java 17 và tạo bytecode hướng tới Java 17. Tuy nhiên, nếu mã nguồn gọi một API chỉ tồn tại từ Java 21, việc biên dịch vẫn có thể thành công vì trình biên dịch đang nhìn thấy API của JDK 21. Khi chạy trên Java 17, chương trình có thể gặp lỗi liên kết như `NoSuchMethodError`.

Với:

```sh
javac --release 17 Main.java
```

Trình biên dịch cũng giới hạn tập API nền tảng theo Java 17 và sẽ phát hiện lời gọi API không có ở phiên bản đó.

Vì vậy, khi dùng JDK mới để xây dựng ứng dụng hỗ trợ một Java release cũ hơn, nên ưu tiên `--release`. Không kết hợp `--release` với `-source` hoặc `-target` trong cùng một lệnh; đây là các cách chọn phiên bản biên dịch loại trừ nhau.

## 5. Ví dụ thực hành: biên dịch Java 17 bằng JDK 21

Giả sử máy đã cài JDK 21 và muốn tạo ứng dụng chạy được trên Java 17.

Tạo tệp `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Compiled for Java 17");
    }
}
```

Biên dịch:

```sh
javac --release 17 -d out Main.java
```

Chạy trên máy có JDK 17 hoặc mới hơn:

```sh
java -cp out Main
```

Kết quả:

```text
Compiled for Java 17
```

Khi biên dịch thành công với JDK 21 và `--release 17`, tệp lớp được tạo theo định dạng Java 17. Máy chạy vẫn cần có JVM tương thích và mọi dependency của ứng dụng cũng phải tương thích với Java 17.

Có thể kiểm tra phiên bản bytecode bằng `javap`:

```sh
javap -verbose -classpath out Main
```

Trong kết quả, tìm dòng `major version`. Với Java 17, giá trị là:

```text
major version: 61
```

Một số giá trị thường gặp:

| Java | Class file major version |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

Đây là số phiên bản định dạng class file, không phải số phiên bản JDK được cài trên máy.

## 6. Ví dụ API: phát hiện phương thức không có trong phiên bản cũ

Phương thức `String.strip()` được bổ sung từ Java 11. Tạo tệp `ApiCompatibility.java`:

```java
public class ApiCompatibility {
    public static void main(String[] args) {
        String message = "  Java  ";
        System.out.println(message.strip());
    }
}
```

Nếu dùng JDK 21 để biên dịch theo Java 8:

```sh
javac --release 8 ApiCompatibility.java
```

Lệnh biên dịch thất bại vì API Java 8 không có phương thức `strip()`. Trình biên dịch báo không tìm thấy phương thức tương ứng trên kiểu `String`.

Đổi sang mục tiêu Java 11:

```sh
javac --release 11 ApiCompatibility.java
java ApiCompatibility
```

Kết quả:

```text
Java
```

Ví dụ cho thấy `--release` kiểm tra cả API nền tảng, không chỉ điều chỉnh số phiên bản bytecode.

## 7. Phạm vi và những điều --release không bảo đảm

`--release` là một cơ chế kiểm soát tương thích quan trọng, nhưng không tự giải quyết mọi vấn đề triển khai.

**Thư viện bên thứ ba:** tùy chọn này kiểm soát API nền tảng Java được trình biên dịch cung cấp. Nó không bảo đảm các JAR bên ngoài tương thích với phiên bản Java mục tiêu. Cần kiểm tra phiên bản tối thiểu của từng dependency và cách dependency được đóng gói.

**API nội bộ của JDK:** không nên dựa vào các lớp hoặc API nội bộ không được hỗ trợ như `sun.*` hoặc `com.sun.*`. Việc truy cập API nội bộ có thể bị giới hạn hoặc thay đổi giữa các bản JDK; `--release` hướng tới tập API nền tảng được hỗ trợ cho release mục tiêu.

**Hệ điều hành và kiến trúc CPU:** `--release` không biên dịch riêng cho Windows, Linux, macOS, x64 hay ARM. Bytecode Java thường có tính di động, nhưng ứng dụng vẫn có thể phụ thuộc thư viện native, đường dẫn tệp, quyền hệ thống hoặc hành vi riêng của nền tảng.

**Hành vi lúc chạy:** biên dịch thành công không chứng minh toàn bộ chương trình chạy đúng trên mọi môi trường. Cần chạy kiểm thử bằng đúng phiên bản JRE/JDK mục tiêu, đặc biệt khi ứng dụng có reflection, service loading, serialization, JNI hoặc phụ thuộc hành vi của thư viện.

**Cấu hình preview:** tính năng preview gắn với phiên bản JDK cụ thể. Nếu bật preview, phải biên dịch bằng JDK tương ứng với release hiện tại và chạy với `--enable-preview` trên cùng phiên bản Java đó. Preview không phải cách để tạo ứng dụng preview của một release cũ bằng JDK mới hơn.

## 8. --release và Java Preview Features

Tính năng preview cho phép thử nghiệm một phần thay đổi ngôn ngữ hoặc nền tảng trước khi tính năng đó trở thành chính thức. Preview được ràng buộc với đúng phiên bản Java phát hành nó.

Ví dụ, với JDK 21, có thể bật preview cho Java 21 bằng:

```sh
javac --enable-preview --release 21 Main.java
```

Khi chạy, cũng cần bật:

```sh
java --enable-preview Main
```

Không thể dùng JDK 21 để bật preview của Java 17 bằng cách đặt `--release 17`. Nếu cần dùng preview, compiler và runtime phải cùng release hỗ trợ tính năng đó. Với ứng dụng cần tương thích ổn định lâu dài, nên ưu tiên tính năng Java đã được chuẩn hóa thay vì preview.

## 9. Cấu hình --release trong Maven

Với Maven Compiler Plugin, có thể cấu hình release trong `pom.xml`. Ví dụ:

```xml
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
    </plugins>
</build>
```

Thuộc tính `maven.compiler.release` được Maven Compiler Plugin sử dụng để truyền lựa chọn release tới trình biên dịch. Ví dụ trên đặt Java 17 làm nền tảng mục tiêu và UTF-8 làm encoding mã nguồn.

Chạy build:

```sh
mvn clean compile
```

Maven vẫn cần một JDK đủ mới để hỗ trợ release được chọn. Nếu dùng JDK 21, cấu hình release 17 là hợp lệ. Nếu Maven thực tế chạy bằng JDK 8, trình biên dịch của JDK 8 không hiểu `--release`; hãy kiểm tra:

```sh
mvn -version
```

Kết quả lệnh cho biết Maven đang chạy bằng Java nào. IDE có thể cấu hình Maven runner dùng một JDK khác với Terminal, nên cần kiểm tra cả hai môi trường khi kết quả khác nhau.

## 10. Cấu hình --release trong Gradle

Trong Gradle, có thể chọn JDK dùng để chạy compiler bằng Java toolchain và chọn nền tảng mục tiêu bằng `options.release`.

Ví dụ Groovy DSL trong `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Trong cấu hình này:

- Toolchain chọn JDK 21 làm bộ công cụ biên dịch.
- `options.release = 17` yêu cầu compiler biên dịch theo Java 17.
- Máy chạy ứng dụng cần có Java 17 trở lên.
- Dependency và các task khác cũng cần được kiểm tra theo mục tiêu tương thích.

Chạy task biên dịch:

```sh
./gradlew clean compileJava
```

Trên Windows:

```powershell
gradlew.bat clean compileJava
```

Có thể xem phiên bản JVM mà Gradle sử dụng bằng:

```sh
./gradlew -version
```

JDK chạy Gradle, JDK toolchain của compiler và phiên bản Java mục tiêu là các khái niệm liên quan nhưng không nhất thiết giống nhau. Cần phân biệt chúng khi chẩn đoán lỗi build.

## 11. Lỗi thường gặp khi dùng --release

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `invalid flag: --release` | Đang dùng JDK quá cũ, chẳng hạn JDK 8 | Chọn JDK 9 trở lên; kiểm tra `javac --version` và `where.exe javac` hoặc `command -v javac` |
| `release version ... not supported` | Phiên bản mục tiêu mới hơn JDK đang chạy compiler hoặc nằm ngoài dải được hỗ trợ | Dùng JDK đủ mới hoặc chọn release được `javac --help` liệt kê |
| `option --source cannot be used together with --release` | Cùng lúc cấu hình `--release` và `-source` | Chọn một cơ chế; ưu tiên `--release` khi cần giới hạn API |
| `option --target cannot be used together with --release` | Cùng lúc cấu hình `--release` và `-target` | Xóa `-target`, giữ release mục tiêu |
| `cannot find symbol` sau khi đặt release thấp hơn | Mã nguồn gọi API không tồn tại ở release mục tiêu | Thay API bằng cách tương thích, nâng release mục tiêu hoặc dùng thư viện phù hợp |
| Build bằng Terminal thành công nhưng IDE thất bại | IDE và Terminal dùng JDK hoặc cấu hình compiler khác nhau | Đồng bộ Project SDK, Gradle JVM/Maven runner và release |
| Chạy trên máy cũ báo `UnsupportedClassVersionError` | Một phần bytecode được tạo bằng release cao hơn mục tiêu, hoặc một dependency yêu cầu Java mới hơn | Kiểm tra bytecode của ứng dụng và dependency; đặt release nhất quán và dùng thư viện tương thích |
| Compile thành công nhưng chạy lỗi `NoSuchMethodError` | Dependency hoặc bytecode khác tham chiếu API không có trong runtime, hoặc có xung đột phiên bản thư viện | Kiểm tra dependency tree, classpath lúc chạy và kiểm thử trên runtime mục tiêu |

Khi thấy lỗi, trước tiên kiểm tra compiler thực tế đang được gọi. Một máy có thể cài nhiều JDK, khiến `java` và `javac` trỏ tới hai phiên bản khác nhau. Trên Windows:

```powershell
where.exe java
where.exe javac
java -version
javac --version
```

Trên macOS/Linux:

```sh
command -v java
command -v javac
java -version
javac --version
```

Sau đó kiểm tra cấu hình build của IDE hoặc build tool. Không nên sửa mã nguồn trước khi xác định đúng compiler và release đang được sử dụng.

## 12. Quy trình chọn release cho một dự án

Khi bắt đầu dự án hoặc thay đổi phiên bản Java mục tiêu, thực hiện theo trình tự:

1. Xác định phiên bản Java thấp nhất mà môi trường triển khai hỗ trợ.
2. Chọn JDK dùng để biên dịch; JDK này có thể mới hơn release mục tiêu.
3. Đặt `--release` đúng phiên bản cần hỗ trợ.
4. Kiểm tra thư viện bên thứ ba có hỗ trợ cùng phiên bản hay không.
5. Biên dịch toàn bộ mã nguồn và xử lý cảnh báo/lỗi.
6. Chạy unit test và integration test bằng runtime của phiên bản mục tiêu.
7. Kiểm tra artifact và dependency trước khi phát hành.

Không chọn release chỉ vì máy lập trình viên đang cài phiên bản đó. Release cần phản ánh hợp đồng tương thích của sản phẩm với môi trường người dùng.

## 13. Checklist

- [ ] Đã xác định Java release tối thiểu mà sản phẩm hỗ trợ.
- [ ] JDK dùng để biên dịch đủ mới để hỗ trợ release mục tiêu.
- [ ] Đã cấu hình `--release N` hoặc cấu hình tương đương trong Maven/Gradle.
- [ ] Không kết hợp `--release` với `-source` hoặc `-target`.
- [ ] Mã nguồn không sử dụng cú pháp hoặc API mới hơn release mục tiêu.
- [ ] Dependency bên thứ ba cũng hỗ trợ phiên bản Java mục tiêu.
- [ ] Đã kiểm tra phiên bản bytecode khi cần.
- [ ] Đã chạy kiểm thử trên runtime mục tiêu thực tế.
- [ ] Không phụ thuộc preview feature hoặc API nội bộ ngoài chủ đích.

`--release` giúp biến yêu cầu tương thích Java thành một điều kiện có thể kiểm tra ngay trong quá trình biên dịch. Khi dùng đúng, nó giảm nguy cơ phát hành bytecode hoặc lời gọi API vượt quá phiên bản Java mà ứng dụng cam kết hỗ trợ.