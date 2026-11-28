# Đồng bộ tùy chọn module cho môi trường test, IDE và launcher đóng gói

Khi ứng dụng cần một tùy chọn JPMS như `--add-exports` hoặc `--add-opens` để tương thích với thư viện, tùy chọn đó phải được đặt đúng giai đoạn và đúng JVM. Cấu hình chạy trong IDE không tự động áp dụng cho Maven/Gradle test worker; tùy chọn compiler không tự động đi theo ứng dụng khi chạy; và launcher do `jpackage` tạo cần nhận cấu hình runtime riêng.

Muốn kết quả nhất quán, hãy xác định module nguồn, package, module đích và lý do cần mở quyền, sau đó đồng bộ cấu hình ở các nơi thực sự biên dịch hoặc chạy ứng dụng. Với module do bạn sở hữu, ưu tiên sửa `module-info.java` bằng `requires`, `exports` hoặc `opens`. Tùy chọn dòng lệnh nên là cầu nối có phạm vi khi chưa thể sửa dependency hoặc cần kiểm thử một cấu hình cụ thể.

Bài học thuộc chương **Đóng gói JDK** của module **JAVA_VERSION_JAVA16**. Strong encapsulation từ Java 16/17 vẫn được duy trì trong JDK hiện đại. Nội dung tập trung vào cách phối hợp tùy chọn module giữa compiler, test JVM, IDE, lệnh chạy và launcher đóng gói; không sử dụng cờ tương thích đã bị loại bỏ.

## 1. Vì sao phải đồng bộ cấu hình?

Một dự án Java thường được biên dịch và chạy qua nhiều môi trường:

- Compiler trong Maven hoặc Gradle.
- JVM riêng chạy unit test và integration test.
- IDE compiler và IDE test runner.
- JVM chạy ứng dụng khi phát triển.
- Launcher được tạo bằng `jpackage` khi phân phối.

Mỗi môi trường có thể dùng JDK khác nhau và nhận tham số từ một cấu hình khác. Ví dụ, test có thể chạy thành công vì IDE đã được cấu hình `--add-opens`, trong khi lệnh Maven trên CI thất bại vì test worker không nhận tùy chọn đó. Ứng dụng chạy trong IDE cũng có thể hoạt động, nhưng launcher đóng gói lại thiếu cấu hình runtime.

Quy tắc quan trọng: **đặt tùy chọn ở đúng nơi thực thi hành vi cần quyền truy cập**. Tùy chọn cho compiler đi vào compiler arguments; tùy chọn cho test đi vào JVM của test worker; tùy chọn cho ứng dụng đã đóng gói đi vào cấu hình launcher.

## 2. Xác định chính xác quyền truy cập cần cấp

Trước khi sửa build script, xác định ba thành phần:

1. **Source module:** module chứa package cần được export hoặc open.
2. **Package:** package cụ thể mà ứng dụng cần truy cập.
3. **Target module:** module cần nhận quyền; nếu code chạy trên classpath, target là `ALL-UNNAMED`.

Ba loại quyền JPMS thường gặp:

| Nhu cầu | Tùy chọn | Công dụng |
| --- | --- | --- |
| Cho module nguồn đọc module đích | `--add-reads source=target` | Bổ sung quan hệ readability |
| Cho phép truy cập kiểu public trong package | `--add-exports source/package=target` | Bổ sung quyền truy cập API thông thường |
| Cho phép reflection sâu vào package | `--add-opens source/package=target` | Cho phép framework truy cập private/protected/package members bằng reflection |

Ví dụ framework trên classpath cần reflection sâu vào package `java.lang`:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

Nếu framework là named module `com.example.json`, hãy giới hạn target:

```text
--add-opens=java.base/java.lang=com.example.json
```

`ALL-UNNAMED` mở package cho code thuộc unnamed module, thường là ứng dụng và thư viện trên classpath. Khi có thể, dùng tên module cụ thể để giảm phạm vi quyền.

## 3. Phân biệt compiler options và runtime options

Không phải mọi tùy chọn module đều dùng ở mọi giai đoạn:

| Tùy chọn | javac | JVM chạy ứng dụng/test | Mục đích |
| --- | --- | --- | --- |
| `--add-reads` | Có | Có | Điều chỉnh quan hệ đọc module |
| `--add-exports` | Có | Có | Cho phép truy cập API public trong package |
| `--add-opens` | Không dùng để biên dịch | Có | Cho phép deep reflection lúc chạy |

Nếu source code import kiểu từ package chưa export, compiler có thể từ chối. Trong tình huống tương thích có kiểm soát, `javac --add-exports` có thể cho phép biên dịch; JVM chạy ứng dụng cũng cần cấu hình export tương ứng. Chỉ đặt cờ ở một phía có thể dẫn tới build thành công nhưng runtime ném `IllegalAccessError`.

`--add-opens` chỉ có ý nghĩa cho reflection sâu khi chạy. Nó không làm cho source code có thể import một kiểu từ package chưa export và không sửa lỗi biên dịch thông thường.

Với module do bạn quản lý, cách bền vững hơn là khai báo quyền cần thiết trong module descriptor:

```java
module com.example.provider {
    exports com.example.provider.api;
    opens com.example.provider.model to com.example.json;
}
```

Module client khai báo dependency:

```java
module com.example.client {
    requires com.example.provider;
}
```

## 4. Đồng bộ tùy chọn cho javac và java

Giả sử module `com.example.provider` có package `com.example.provider.spi` chưa export. Module client cần gọi API public trong package đó. Ví dụ này minh họa một cấu hình tương thích tạm thời.

Biên dịch module client:

```powershell
javac --module-path mods --add-exports com.example.provider/com.example.provider.spi=com.example.client -d out -m com.example.client
```

Chạy ứng dụng:

```powershell
java --module-path "mods;out" --add-exports com.example.provider/com.example.provider.spi=com.example.client --module com.example.client/com.example.client.Main
```

Ví dụ trên dùng PowerShell. Dấu chấm phẩy là ký tự phân cách module path trên Windows; Linux và macOS dùng dấu hai chấm.

Nếu client chỉ chạy trên classpath, target tương ứng là `ALL-UNNAMED`:

```powershell
javac --add-exports com.example.provider/com.example.provider.spi=ALL-UNNAMED -cp lib\provider.jar -d out src\Main.java
java --add-exports com.example.provider/com.example.provider.spi=ALL-UNNAMED -cp "out;lib\provider.jar" com.example.Main
```

Không thêm `--add-opens` vào lệnh javac để sửa lỗi import. Nếu lỗi là reflection sâu trong test hoặc ứng dụng, thêm `--add-opens` vào JVM thực thi test hoặc ứng dụng.

Với Maven Compiler Plugin, đặt compiler argument trong cấu hình compiler:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <compilerArgs>
      <arg>--add-exports</arg>
      <arg>com.example.provider/com.example.provider.spi=com.example.client</arg>
    </compilerArgs>
  </configuration>
</plugin>
```

Với Gradle Kotlin DSL, cấu hình task biên dịch:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf(
            "--add-exports",
            "com.example.provider/com.example.provider.spi=com.example.client"
        )
    )
}
```

Compiler arguments này chỉ giải quyết bước biên dịch. Nếu bytecode cần quyền export đó khi chạy, cấu hình JVM runtime tương ứng cũng phải có `--add-exports`.

## 5. Đặt tùy chọn cho Maven Surefire

Maven Surefire chạy test trong JVM test fork. Tùy chọn cần thiết cho test phải được truyền vào JVM đó bằng cấu hình `argLine`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>--add-opens=java.base/java.lang=ALL-UNNAMED</argLine>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Chạy test:

```powershell
mvn test
```

Một số dự án dùng JaCoCo hoặc plugin khác để thêm JVM arguments vào `argLine`. Khi đó, không ghi đè giá trị mà plugin khác đã thiết lập; hãy kết hợp các giá trị theo cấu hình của dự án và dùng cơ chế late property evaluation của Surefire khi phù hợp.

`argLine` được truyền cho JVM fork của Surefire. Nếu dự án đặt `forkCount` bằng `0`, test chạy trong tiến trình Maven và `argLine` không được áp dụng như JVM argument của một fork riêng; hãy cấu hình JVM khởi chạy Maven hoặc bật fork theo nhu cầu dự án.

Nếu integration test chạy bằng Maven Failsafe, cấu hình JVM cho Failsafe riêng. Đừng giả định `argLine` của Surefire tự động áp dụng cho Failsafe hoặc cho ứng dụng chạy ngoài test.

## 6. Đặt tùy chọn cho Gradle Test

Gradle chạy test trong test worker JVM. Dùng `jvmArgs` để truyền tùy chọn cho tiến trình đó:

Groovy DSL trong `build.gradle`:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
```

Kotlin DSL trong `build.gradle.kts`:

```kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("--add-opens=java.base/java.lang=ALL-UNNAMED")
}
```

Chạy test:

```powershell
gradlew test
```

`jvmArgs` áp dụng cho test JVM do Gradle khởi chạy. Nó không tự thêm tùy chọn vào ứng dụng được chạy bởi một task JavaExec riêng, một service process hay launcher được đóng gói.

Nếu chỉ một test task cần quyền reflection, cấu hình đúng task đó thay vì mở package cho toàn bộ test suite. Điều này giúp giới hạn quyền và dễ gỡ bỏ sau khi nâng cấp thư viện.

## 7. Cấu hình trong IDE

IDE có thể có nhiều cấu hình độc lập: compiler, chạy ứng dụng, chạy test và chạy build tool. Đặt cờ ở cấu hình không đúng sẽ tạo cảm giác “chạy được trong IDE” nhưng thất bại khi chạy từ terminal hoặc CI.

| Nơi cấu hình trong IDE | Đặt loại tùy chọn |
| --- | --- |
| Compiler/build configuration | Compiler arguments như `--add-exports` khi biên dịch thật sự cần |
| Application Run Configuration | VM options như `--add-opens` hoặc `--add-exports` |
| JUnit/Test Run Configuration | VM options của test runner |
| Maven/Gradle tool window | Cấu hình trong build file hoặc JVM của build/test worker |
| IDE runtime | JDK dùng để chạy chính IDE; không phải nơi cấu hình ứng dụng |

Ví dụ VM options của test runner:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

Ví dụ VM options của application run configuration:

```text
--add-opens=java.base/java.lang=com.example.application
```

Nếu test chạy bằng named module, target phải là tên module thực tế. Nếu test runner đặt test code trên classpath, target có thể là `ALL-UNNAMED`. Xác minh module path/classpath mà IDE sử dụng thay vì sao chép máy móc một giá trị từ dự án khác.

## 8. Cấu hình launcher đóng gói bằng jpackage

Sau khi ứng dụng đã đóng gói, launcher cần nhận các runtime options tương ứng. Dùng `--java-options` của `jpackage`:

Ứng dụng classpath:

```powershell
jpackage --type app-image --name Orders --input build\input --main-jar orders.jar --main-class com.example.orders.Main --java-options "--add-opens=java.base/java.lang=ALL-UNNAMED" --dest build\image
```

Ứng dụng modular có thể mở package cho module cụ thể:

```powershell
jpackage --type app-image --name Orders --module-path build\mods --module com.example.orders/com.example.orders.Main --java-options "--add-opens=java.base/java.lang=com.example.orders" --dest build\image
```

`--java-options` ghi tùy chọn cho JVM của launcher. Nó không thay thế compiler options và không có tác dụng với JVM test worker đã chạy trước đó. Nếu có nhiều tùy chọn JVM, có thể truyền `--java-options` nhiều lần.

Sau khi tạo image, chạy launcher thực tế để xác nhận tùy chọn đã được áp dụng. Nếu tạo installer từ image bằng `--app-image`, launcher và cấu hình runtime của image sẽ được đưa vào package.

## 9. Bảng đồng bộ theo môi trường

Ví dụ một thư viện cần deep reflection vào `java.lang` trong test và ứng dụng classpath:

| Môi trường | Vị trí cấu hình | Giá trị ví dụ |
| --- | --- | --- |
| Maven Surefire | `argLine` của test JVM | `--add-opens=java.base/java.lang=ALL-UNNAMED` |
| Maven Failsafe | `argLine` của integration-test JVM | Cùng tùy chọn nếu integration test cần |
| Gradle Test | `Test.jvmArgs` | Cùng tùy chọn nếu test worker cần |
| IDE JUnit runner | VM options của test run configuration | Cùng tùy chọn nếu test runner cần |
| IDE application runner | VM options của application run configuration | Chỉ thêm nếu ứng dụng khi chạy cần |
| java command | JVM arguments trước tên main class/module | Chỉ thêm nếu runtime cần |
| jpackage launcher | `--java-options` | Chỉ thêm nếu launcher cần |

Không nhất thiết mọi môi trường đều cần cùng một cờ. Ví dụ, chỉ test framework có thể cần mở package trong khi ứng dụng production không dùng reflection đó. Khi ấy, chỉ cấu hình test JVM và giữ launcher production không có quyền mở dư thừa.

## 10. Đồng bộ JDK và phiên bản công cụ

Ngay cả khi cờ giống nhau, kết quả có thể khác nếu compiler và runtime dùng JDK khác phiên bản hoặc khác module graph.

Kiểm tra các phiên bản thực tế:

```powershell
java -version
javac -version
mvn -version
gradlew --version
jpackage --version
```

Trong IDE, kiểm tra riêng:

- Project SDK/JDK dùng để biên dịch.
- JRE/JDK của application run configuration.
- JRE/JDK của test runner.
- JDK được Maven/Gradle tool window sử dụng.

Trong CI, kiểm tra JDK được chọn bởi toolchain và JDK chạy build daemon. Đừng chỉ dựa vào biến môi trường `JAVA_HOME` nếu build tool hoặc IDE có cấu hình JDK riêng.

## 11. Chẩn đoán khi môi trường này chạy được, môi trường kia thất bại

Thực hiện theo thứ tự:

1. Thu thập exception đầy đủ và xác định thao tác thất bại là compile, linkage hay reflection.
2. Ghi lại command line/JVM arguments thực tế của tiến trình lỗi.
3. Xác định target module là named module hay `ALL-UNNAMED`.
4. Kiểm tra tùy chọn được đặt ở compiler, test worker hay application launcher.
5. So sánh JDK vendor/version và module path giữa hai môi trường.
6. Kiểm tra dependency tree và module descriptor ở runtime.

Các lệnh hữu ích:

```powershell
java --show-module-resolution --module-path mods --module com.example.application/com.example.application.Main
jdeps --jdk-internals build\libs\application.jar
jar --describe-module --file build\libs\provider.jar
```

`--show-module-resolution` cho biết module nào được resolve khi chạy. `jdeps --jdk-internals` tìm phụ thuộc vào API nội bộ JDK trong artifact. `jar --describe-module` giúp kiểm tra descriptor của modular JAR.

Khi IDE chạy được nhưng CI thất bại, hãy so sánh JVM options của test worker trước. Khi test chạy được nhưng launcher thất bại, kiểm tra `--java-options` đã được truyền lúc tạo image chưa và chạy đúng launcher thay vì gọi JDK cài trên máy.

## 12. Loại bỏ workaround sau khi dependency đã được nâng cấp

Các cờ mở module thường được thêm để tương thích với framework, ORM, serializer, mocking library hoặc thư viện cũ. Sau khi nâng cấp dependency, hãy thử bỏ từng cờ và chạy lại test cùng ứng dụng.

Không tiếp tục giữ một tùy chọn chỉ vì nó từng sửa lỗi. Mỗi `--add-opens` hoặc `--add-exports` là một ngoại lệ về ranh giới module và cần có lý do cụ thể, module nguồn, package, target và người chịu trách nhiệm.

Không dùng `--illegal-access` như một giải pháp hiện hành. Từ JDK 17, tùy chọn này không còn khôi phục chế độ relaxed strong encapsulation và không mở lại các package nội bộ theo cách cũ. Tùy phiên bản JDK, tùy chọn có thể bị bỏ qua hoặc phát cảnh báo; đừng dựa vào nó để sửa lỗi. Hãy cập nhật thư viện để dùng API được hỗ trợ hoặc khai báo quyền module cần thiết với phạm vi nhỏ.

## 13. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| javac báo package không export | Thiếu compiler option hoặc module descriptor chưa export | Sửa `exports` hoặc thêm `--add-exports` vào compiler khi cần tương thích |
| Test trong IDE chạy nhưng Maven thất bại | IDE test runner có VM options riêng, Surefire không có | Cấu hình `argLine` cho đúng test JVM |
| Gradle test chạy nhưng ứng dụng task thất bại | `Test.jvmArgs` không áp dụng cho JavaExec/application process | Cấu hình JVM arguments cho đúng task/process |
| Test pass nhưng launcher lỗi | `jpackage` không nhận runtime option cần thiết | Thêm `--java-options` khi tạo image và build lại |
| `--add-opens` không sửa lỗi compile | Đã dùng tùy chọn runtime cho vấn đề compile-time | Dùng module descriptor hoặc compiler `--add-exports` phù hợp |
| `--add-exports` không sửa lỗi reflection sâu | Export API không mở private member | Dùng `opens` hoặc `--add-opens` đúng package/target |
| Cờ có ở build nhưng không ở runtime | Compiler và JVM là hai tiến trình/cấu hình khác nhau | Truyền cờ ở cả giai đoạn cần thiết |
| `ALL-UNNAMED` không có tác dụng | Code caller thực tế thuộc named module | Dùng đúng tên module làm target |
| Lỗi xuất hiện sau khi nâng JDK | Dependency dùng JDK internals hoặc reflection sâu | Nâng cấp dependency, kiểm tra module flags và thay API nội bộ |

## 14. Bài tập tự kiểm tra

Một dự án dùng framework test chạy reflection sâu vào `java.lang`. Unit test chạy bằng IDE thành công, nhưng Maven Surefire thất bại với `InaccessibleObjectException`. Ứng dụng production không dùng framework test này.

Hãy trả lời:

1. Cờ nào phù hợp cho deep reflection?
2. Cần đặt cờ ở đâu để Maven Surefire test worker nhận được?
3. Có cần thêm cờ vào compiler `javac` không?
4. Có nên thêm cờ vào launcher production không?
5. Nếu sau khi nâng framework, test vẫn chạy khi bỏ cờ, nên làm gì?

**Đáp án:**

1. `--add-opens=java.base/java.lang=ALL-UNNAMED`, nếu test caller thực sự chạy trên classpath.
2. Trong `argLine` của Maven Surefire, vì đây là JVM thực thi test.
3. Không. `--add-opens` là tùy chọn runtime, không giải quyết compile-time access.
4. Không, nếu ứng dụng production không cần reflection đó.
5. Xóa cờ khỏi cấu hình test và chạy lại toàn bộ test để xác nhận không còn phụ thuộc.

## Checklist đồng bộ tùy chọn module

- [ ] Xác định chính xác source module, package và target module.
- [ ] Phân biệt readability, public API export và deep reflection.
- [ ] Chọn `requires`/`exports`/`opens` nếu sở hữu module.
- [ ] Đặt compiler options ở javac/build compiler khi cần biên dịch.
- [ ] Đặt runtime options ở đúng test worker hoặc application JVM.
- [ ] Cấu hình riêng Maven Surefire/Failsafe hoặc Gradle Test khi cần.
- [ ] Cấu hình đúng compiler, application runner và test runner trong IDE.
- [ ] Truyền runtime options cho launcher bằng `jpackage --java-options`.
- [ ] So sánh JDK thực tế ở local, CI, IDE và môi trường đóng gói.
- [ ] Thử gỡ bỏ cờ sau khi nâng dependency.
- [ ] Không dùng `--illegal-access` hoặc mở toàn bộ module không cần thiết.

## Ghi nhớ

**Một tùy chọn module chỉ có tác dụng trong tiến trình và giai đoạn nhận được nó.** `javac` cần compiler options; Maven Surefire/Failsafe và Gradle Test cần JVM arguments của test worker; IDE cần cấu hình riêng cho compiler, application runner và test runner; launcher đóng gói nhận runtime options qua `jpackage --java-options`. Phân biệt `--add-exports` với `--add-opens`, dùng target module chính xác và giữ JDK đồng nhất. Sau khi dependency đã hỗ trợ strong encapsulation, loại bỏ workaround không còn cần thiết.

## Tài liệu tham khảo

- [Oracle Java SE 26 — The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Oracle Java SE 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Oracle Java SE 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Apache Maven Surefire — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html)
- [Gradle — Test JVM Configuration](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
