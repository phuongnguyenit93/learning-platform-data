# Điều kiện chạy Gradle và phân biệt JDK chạy build với JDK biên dịch

Một dự án Java có thể **chạy Gradle bằng JDK 17**, **biên dịch bằng JDK 21** nhưng **tạo ứng dụng chạy được trên Java 17**. Ba con số này không mâu thuẫn: chúng thuộc ba lớp khác nhau. Hiểu rõ các lớp giúp cấu hình máy cá nhân, IDE và CI nhất quán, đồng thời tránh lỗi phiên bản Java.

## 1. Ba vai trò cần phân biệt

| Vai trò | Dùng để làm gì? | Cách xác định |
| --- | --- | --- |
| **JVM/JDK chạy Gradle** (*Gradle runtime/Daemon JVM*) | Chạy engine Gradle, đánh giá script `build.gradle`/`build.gradle.kts`, chạy plugin và điều phối task | Phiên bản Gradle có hỗ trợ JVM đó không; cấu hình launcher/Daemon/IDE |
| **JDK biên dịch** (*compiler toolchain*) | Cung cấp `javac` để dịch mã nguồn Java thành `.class` | `java.toolchain` hoặc cấu hình compiler riêng cho task |
| **Java chạy sản phẩm hoặc test** (*execution runtime*) | Chạy `main()`, JUnit, ứng dụng sau khi build; đọc bytecode và API mà ứng dụng sử dụng | JVM thực sự dùng để chạy chương trình, `Test`/`JavaExec` launcher, môi trường triển khai |

Một tiến trình Gradle phải có JVM để khởi động, nhưng `JavaCompile` có thể dùng compiler từ **JDK khác**. Phiên bản Java mục tiêu của sản phẩm còn có thể khác phiên bản compiler, thông qua `--release`.

Ví dụ: Gradle chạy trên JDK 17; Gradle Toolchains chọn JDK 21 để biên dịch; `options.release = 17` tạo bytecode và giới hạn API về Java 17; chương trình chạy trên Java 17 trở lên, với điều kiện các thư viện phụ thuộc và cấu hình runtime cũng tương thích.

## 2. Điều kiện để chạy một Gradle build

1. **Dùng đúng phiên bản Gradle của dự án.** Ưu tiên **Gradle Wrapper** gồm `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và `gradle-wrapper.jar`. Từ thư mục gốc dự án, chạy `./gradlew ...` (Linux/macOS) hoặc `.\gradlew.bat ...` (PowerShell). Wrapper sử dụng Gradle distribution được khai báo cho dự án, nên thường không cần cài Gradle toàn hệ thống.
2. **Có JVM tương thích với phiên bản Gradle đó.** Điều kiện tối thiểu thay đổi theo đời Gradle; không được suy ra rằng “cài JDK mới nhất là luôn chạy được Gradle cũ”. Ví dụ, Gradle **8.4** đã hỗ trợ **Java 21 làm toolchain** nhưng **chưa hỗ trợ chạy Gradle trên Java 21**; từ **Gradle 8.5** mới hỗ trợ chạy trên Java 21. Từ **Gradle 9.0**, Gradle Daemon cần **JVM 17 trở lên**. Giới hạn trên và khả năng hỗ trợ mỗi bản Java cần xem **Compatibility Matrix** theo phiên bản Gradle.
3. **Có các công cụ cần cho task.** Với project Java dùng `JavaCompile`, phải có JDK chứa compiler `javac`, được Gradle tìm thấy hoặc cấp phát thông qua toolchain. Chỉ có JRE có thể đủ cho vài tác vụ chạy, nhưng không đủ để tự biên dịch Java.
4. **Đáp ứng yêu cầu của plugin/build logic.** Plugin hoặc Android/Kotlin/Spring plugin có thể yêu cầu một bản Gradle hay JVM mới hơn mức tối thiểu của Gradle. Cần kiểm tra cả plugin, không chỉ ma trận Java của Gradle.
5. **Có tài nguyên/đường truyền khi cần.** Lần đầu Wrapper có thể tải Gradle distribution; build có thể phải tải dependency, plugin hoặc toolchain qua repository. Mạng/offline cache, quyền truy cập thư mục và cấu hình repository vì thế ảnh hưởng đến khả năng hoàn thành build, dù Java đã đúng.

**Chú ý về Gradle 9:** script Wrapper/launcher có thể khởi động từ JVM 8 trong một số cấu hình, nhưng JVM dùng để thực thi Gradle Daemon vẫn phải từ 17 trở lên. Khi nói “JDK chạy build”, cần xác định đúng **Daemon JVM thực hiện build**, không chỉ JVM khởi chạy script ban đầu.

### Bảng tình huống tiêu biểu

| Cấu hình | Kết luận |
| --- | --- |
| Gradle 8.4 chạy trên JDK 21 | **Không được hỗ trợ** để chạy engine Gradle; dùng JVM phù hợp hoặc nâng Wrapper |
| Gradle 8.4 chạy trên JDK 17, toolchain JDK 21 | **Được hỗ trợ** để biên dịch/test Java 21 bằng toolchain |
| Gradle 8.5 chạy trên JDK 21 | **Được hỗ trợ** với Java 21 |
| Gradle 9.x chạy Daemon bằng JDK 11 | **Không được hỗ trợ**; cần JVM 17+ và vẫn phải kiểm tra giới hạn trên của bản 9.x cụ thể |
| Gradle chạy bằng JDK 17, biên dịch bằng JDK 21, `--release 17` | **Hợp lệ** nếu phiên bản Gradle hỗ trợ toolchain JDK 21; output nhắm Java 17 |

Các ví dụ là **khả năng tương thích của Gradle/JDK**, không bảo đảm mọi plugin của dự án đều hỗ trợ các phiên bản đó.

## 3. JDK nào thực sự chạy Gradle?

Có nhiều nguồn cấu hình, tùy cách khởi chạy:

- **Terminal:** script Wrapper thường tìm Java qua `JAVA_HOME` (nếu được đặt) hoặc `java` trên `PATH`. `JAVA_HOME` phải trỏ tới **thư mục gốc JDK**, không phải `bin/java`.
- **Gradle Daemon:** có thể dùng JVM được chọn riêng qua `org.gradle.java.home` hoặc cấu hình **Daemon JVM criteria**; do đó JVM của Daemon có thể khác JVM của launcher.
- **IDE (ví dụ IntelliJ IDEA):** mục **Gradle JVM** của IDE có thể chọn một JDK khác terminal. Vì vậy chạy build từ IDE và terminal có thể cho kết quả khác nhau.
- **CI:** image, environment variables và cấu hình Java setup có thể quyết định JVM chạy Gradle; cần khai báo rõ trong pipeline.

Các lệnh kiểm tra (Linux/macOS):

```bash
java -version
javac -version
echo "$JAVA_HOME"
./gradlew --version
./gradlew -q javaToolchains
```

Tương ứng trong PowerShell:

```powershell
java -version
javac -version
$env:JAVA_HOME
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
```

Cách đọc:

- `java -version`: Java đang tìm được từ **terminal**. Không đủ để kết luận JDK mà Daemon hay compiler sử dụng.
- `javac -version`: compiler trên `PATH`, chưa chắc là compiler do Gradle Toolchains chọn.
- `gradlew --version`: kiểm tra distribution Gradle và thông tin JVM; bản Gradle mới có thể hiển thị **Launcher JVM** và **Daemon JVM** tách biệt.
- `gradlew -q javaToolchains`: liệt kê các Java installation mà Gradle phát hiện, dùng để kiểm tra có JDK cần thiết không. Lệnh này không có nghĩa mọi toolchain đều đã được chọn cho task.

Để xem chi tiết lựa chọn JVM và compiler khi build, chạy `./gradlew compileJava --info` (hoặc `.\gradlew.bat compileJava --info`). Log có thể khác nhau theo phiên bản Gradle và build.

Có thể chọn JDK chạy Daemon qua Gradle property, ví dụ trong **cấu hình cục bộ**:

```properties
org.gradle.java.home=/opt/jdks/jdk-17
```

Đường dẫn ở đây chỉ là **ví dụ**, phải thay bằng đường dẫn JDK thực tế. Tránh commit đường dẫn tuyệt đối phụ thuộc một máy vào `gradle.properties` dùng chung; cân nhắc biến môi trường, thiết lập CI hoặc Daemon JVM criteria cho môi trường chuẩn hóa. Property này chọn JVM để chạy Gradle, **không thay thế** khai báo Java toolchain của project.

## 4. JDK biên dịch: dùng Java Toolchains

Nếu project không khai báo toolchain/compiler riêng, Gradle thường dùng JDK đang chạy Gradle để xử lý Java. Khi đó đổi `JAVA_HOME` hoặc **Gradle JVM** trong IDE có thể vô tình đổi phiên bản compiler và output.

Cách kiểm soát đáng tin cậy hơn là khai báo Java Toolchains ngay trong build. Ví dụ Groovy DSL ở `build.gradle`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Với Java plugin, Gradle sẽ tìm JDK 21 phù hợp và sử dụng nó cho các task có hỗ trợ toolchain, như `JavaCompile`, `Test`, `Javadoc`. **Điều này không yêu cầu Gradle engine phải chạy trên JDK 21**; Gradle có thể vẫn chạy bằng JDK 17 nếu phiên bản Gradle hỗ trợ Java 21 toolchain.

Nếu máy chưa có JDK 21, có thể chỉ dẫn Gradle tìm JDK ở vị trí riêng (ví dụ `org.gradle.java.installations.paths`) hoặc cấu hình cơ chế tự cấp phát toolchain qua **toolchain download repository/resolver**. **Không mặc định giả định Gradle sẽ tự tải được mọi JDK**: khi chưa có repository/resolver được cấu hình, task có thể báo không tìm thấy toolchain phù hợp.

Khi một project cần nhiều Java version, có thể đặt launcher/compiler riêng theo task. Ví dụ sau đây **chỉ là đoạn bổ sung** vào build đã áp dụng Java plugin để yêu cầu test chạy trên JDK 17:

```groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Điều này có ý nghĩa khi muốn xác minh ứng dụng thực sự chạy trên Java 17, thay vì chỉ biên dịch ra bytecode Java 17 rồi chạy test bằng JDK 21. Phải có thêm JDK 17 được Gradle tìm thấy.

## 5. Phiên bản compiler, bytecode và API không phải một thứ

Ba lựa chọn thường bị nhầm:

| Cấu hình | Tác động chính | Điều **không** bảo đảm |
| --- | --- | --- |
| `java.toolchain.languageVersion = 21` | Chọn **JDK 21 / javac 21** cho các task được hỗ trợ | Không tự bảo đảm sản phẩm chạy Java 17 |
| `sourceCompatibility = 17`, `targetCompatibility = 17` | Ràng buộc cú pháp nguồn và phiên bản bytecode | Không chặn triệt để việc gọi API chỉ có ở JDK mới hơn |
| `options.release = 17` | Yêu cầu `javac` biên dịch theo cú pháp, bytecode và **API Java 17** | Không chọn compiler JDK nào; không bảo đảm thư viện bên thứ ba tương thích Java 17 |

Với compiler đủ mới, nên kết hợp **toolchain** để chọn đúng JDK với **`--release`** để kiểm soát mức Java mà sản phẩm hỗ trợ. Ví dụ compiler JDK 21 + `--release 17` tạo file `.class` **major version 61** (Java 17), thay vì major version 65 (Java 21).

`--release` kiểm tra Java API của JDK mục tiêu khi compile, nhưng không biến dependency bên thứ ba thành dependency tương thích và không kiểm chứng mọi điều kiện khi triển khai. Cần chạy test trên Java runtime mục tiêu, đặc biệt khi đóng gói ứng dụng với thư viện ngoài.

## 6. Ví dụ đầy đủ: Gradle chạy JDK 17, biên dịch JDK 21, ứng dụng chạy Java 17

**Giả định:** sử dụng một bản Gradle tương thích với JDK 17 khi chạy và JDK 21 làm toolchain (ví dụ Gradle 8.5), máy có JDK 17 và JDK 21, và Wrapper đã có trong project. Dùng Groovy DSL trong `build.gradle`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Tạo `src/main/java/demo/Hello.java`:

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Java 17 bytecode");
    }
}
```

Chạy trên Linux/macOS với **Gradle runtime JDK 17** đã được thiết lập:

```bash
./gradlew clean classes
java -cp build/classes/java/main demo.Hello
```

Trên PowerShell:

```powershell
.\gradlew.bat clean classes
java -cp build/classes/java/main demo.Hello
```

Đầu ra **của lệnh `java ... demo.Hello`**, khi chạy thành công:

```text
Hello from Java 17 bytecode
```

Kết quả in của `gradlew clean classes` thay đổi theo Gradle, cache và môi trường, nên không có một stdout cố định. Ví dụ dùng JDK 21 để **biên dịch** nhưng giới hạn sản phẩm về **Java 17**; nếu muốn chứng minh tương thích thực tế, lệnh `java` ở trên phải trỏ tới Java 17 (kiểm tra bằng `java -version`). Không sử dụng cú pháp hoặc API Java 21 trong source khi đã đặt `--release 17`.

Đọc cấu hình theo từng tầng:

```text
Wrapper Gradle 8.5
  └── Gradle Daemon: JDK 17            (chạy build scripts, plugins)
       └── JavaCompile: javac JDK 21   (được chọn bằng toolchain)
            └── --release 17           (bytecode + Java APIs mục tiêu)
                 └── Hello.class       (chạy bằng Java 17)
```

Nếu có task `test` và muốn kiểm thử bằng JDK 17, áp dụng cấu hình `javaLauncher` trong mục 4. Nếu không, test có thể sử dụng JDK 21 từ project toolchain, dù `--release` là 17.

## 7. Chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `JAVA_HOME is set to an invalid directory` | `JAVA_HOME` trỏ sai hoặc trỏ vào `bin` thay vì thư mục JDK | Kiểm tra và đặt lại đường dẫn JDK gốc |
| Gradle báo JVM hiện tại quá cũ/không được hỗ trợ | JDK **chạy Gradle** không tương thích với Gradle/Plugin | Đối chiếu compatibility matrix; điều chỉnh Gradle JVM hoặc nâng Wrapper |
| Gradle cũ lỗi khi chạy trên JDK quá mới | Phiên bản Gradle chưa hỗ trợ JVM đó để chạy engine | Dùng JDK runtime được hỗ trợ hoặc nâng Gradle sau khi xét plugin |
| `No matching toolchains found` hoặc không tìm thấy Java installation | Thiếu JDK toolchain đã khai báo hoặc Gradle chưa phát hiện nó | Cài JDK đúng version, khai báo path hoặc cấu hình resolver |
| `invalid source release: 21` | Task đang dùng compiler cũ (ví dụ `javac` 17) nhưng yêu cầu source 21 | Kiểm tra compiler thực tế và toolchain 21; chỉ đổi source level nếu phù hợp |
| `UnsupportedClassVersionError` | JVM chạy chương trình/plugin không hiểu bytecode được biên dịch bởi Java mới hơn | Xác định class nào lỗi; nâng JVM chạy đối tượng đó hoặc build lại với release thích hợp |
| Chạy từ IDE khác terminal | IDE chọn Gradle JVM/toolchain khác hoặc vẫn dùng Daemon cũ | So sánh Gradle JVM, `JAVA_HOME`, `javaToolchains` và log; khởi động lại Daemon khi thực sự cần |
| Build thành công nhưng lỗi `NoSuchMethodError` trên Java cũ | Có thể dùng API/library không tương thích runtime mục tiêu | Kết hợp `--release`, kiểm tra dependency và test trên đúng Java mục tiêu |

Một quy trình kiểm tra hiệu quả:

1. Xác định **phiên bản Gradle của Wrapper** và JDK mà Gradle Daemon thực sự dùng.
2. Đối chiếu **Gradle ↔ JVM chạy build** với compatibility matrix và yêu cầu plugin.
3. Kiểm tra **JDK compiler** qua toolchain/log của task, không suy từ `javac -version` của terminal.
4. Kiểm tra `options.release` hoặc target level, rồi chạy/test sản phẩm trên **runtime mục tiêu**.
5. Nếu chuyển JVM hoặc sửa đường dẫn mà build vẫn dùng Daemon cũ, có thể chạy `./gradlew --stop` rồi build lại; chỉ làm khi cần.

## 8. Tự kiểm tra kiến thức

- **Hỏi:** Có bắt buộc dùng cùng một JDK để chạy Gradle và biên dịch không? **Đáp:** Không. Java Toolchains cho phép compiler khác Gradle Daemon JVM.
- **Hỏi:** Dùng JDK 21 để compile có bảo đảm ứng dụng chạy trên Java 17 không? **Đáp:** Không. Cần `--release 17`, dependency tương thích và kiểm tra bằng runtime 17.
- **Hỏi:** Vì sao `java -version` có thể là 17 nhưng Gradle vẫn biên dịch bằng 21? **Đáp:** Toolchain chọn `javac` 21 độc lập với Java trên `PATH`.
- **Hỏi:** Wrapper có tự bảo đảm tải đủ mọi JDK toolchain không? **Đáp:** Không. Wrapper chủ yếu cố định/cấp phát **Gradle distribution**; JDK toolchain cần cài sẵn hoặc cấu hình resolver để cấp phát.

## Nguồn chính thức và hướng đọc tiếp

- [Gradle: Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — xác minh Gradle nào chạy được trên JVM nào và bản Java nào được hỗ trợ qua toolchains.
- [Gradle: Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html) — cấu hình compiler, launcher và phát hiện/cấp phát JDK.
- [Gradle: Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html) — `org.gradle.java.home`, Java installation và cấu hình môi trường.
- [Gradle: Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — cách chạy đúng Gradle distribution theo project.
- [Gradle 8.5 Release Notes](https://docs.gradle.org/8.5/release-notes.html) — mốc hỗ trợ chạy Gradle trên Java 21.
