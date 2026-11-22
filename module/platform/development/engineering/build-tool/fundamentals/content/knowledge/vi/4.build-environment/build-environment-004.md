# Java toolchain và mục tiêu chuẩn hóa bộ công cụ biên dịch

Một dự án Java có thể được mở và build trên nhiều máy phát triển, máy CI và môi trường phát hành. Nếu mỗi nơi tự chọn JDK theo `PATH` hoặc `JAVA_HOME`, cùng một mã nguồn có thể được biên dịch bằng các phiên bản compiler khác nhau. Khác biệt đó có thể làm thay đổi khả năng sử dụng API, bytecode đầu ra, kết quả kiểm thử hoặc hành vi của plugin build.

Gradle Java Toolchains giúp dự án khai báo bộ công cụ Java cần dùng cho các tác vụ như biên dịch, chạy test và tạo Javadoc. Khi kết hợp toolchain với một mục tiêu tương thích Java được công bố rõ ràng, nhóm có thể chuẩn hóa cách build trên máy cá nhân và CI, đồng thời kiểm soát được phiên bản Java mà sản phẩm hướng tới.

## 1. Vì sao cần chuẩn hóa bộ công cụ biên dịch?

JDK không chỉ là một chương trình `java` nằm trên máy. Một JDK chứa nhiều công cụ và thành phần, trong đó có compiler `javac`, Java launcher, thư viện nền tảng và công cụ tài liệu hóa. Gradle cùng các plugin cũng chạy trên một JVM cụ thể. Vì thế, khi nói về phiên bản Java của một dự án, cần xác định đang nói đến vai trò nào.

Ví dụ, một nhóm có thể gặp tình huống:

- Máy của lập trình viên dùng JDK 21 vì đó là JDK mặc định trong terminal.
- Máy CI dùng JDK 17 vì image build chưa được cập nhật.
- Dự án cần tạo bytecode có thể chạy trên Java 17 để tương thích với môi trường triển khai.
- Một số test cần được chạy bằng JDK 21 để xác minh hành vi trên runtime mới.

Nếu chỉ dựa vào JDK mặc định của từng máy, build không thể hiện đầy đủ các quyết định trên. Một máy có thể vô tình biên dịch bằng Java 21 và sử dụng API chỉ có từ Java 21, trong khi môi trường triển khai chỉ có Java 17. Build thành công trên máy phát triển nhưng ứng dụng lại lỗi khi chạy ở môi trường đích.

Chuẩn hóa bộ công cụ giúp trả lời rõ các câu hỏi:

1. JDK nào được dùng để biên dịch mã nguồn?
2. JDK nào được dùng để chạy test và các công cụ Java liên quan?
3. Mã nguồn được phép sử dụng ngôn ngữ và API ở mức Java nào?
4. Bytecode được tạo ra có thể chạy trên phiên bản Java nào?
5. Máy phát triển và CI lấy đúng JDK từ đâu, và xử lý thế nào nếu máy chưa cài JDK đó?

## 2. Phân biệt JVM chạy Gradle, toolchain và phiên bản Java mục tiêu

Đây là ba khái niệm có liên quan nhưng không đồng nghĩa.

| Thành phần | Vai trò | Cách xác định thường gặp |
|---|---|---|
| JVM chạy Gradle | Chạy Gradle daemon, build logic và các plugin trong quá trình cấu hình/thực thi build. | JDK/JRE được chọn qua môi trường chạy Gradle, chẳng hạn `JAVA_HOME`, cấu hình IDE hoặc `org.gradle.java.home`. |
| Java toolchain | Chọn JDK phù hợp cho compiler, test launcher và một số tác vụ Java khác. | Khai báo trong Gradle build script bằng Java toolchain API. |
| Java compatibility target | Quy định mức ngôn ngữ, API nền tảng và định dạng bytecode mà mã nguồn được phép hướng tới. | Compiler options như `options.release`, hoặc các thuộc tính tương thích cũ `sourceCompatibility` và `targetCompatibility`. |

Ba giá trị có thể giống nhau, nhưng không bắt buộc phải giống nhau. Chẳng hạn, Gradle có thể chạy trên JDK 17, dùng compiler JDK 21 từ toolchain và biên dịch sản phẩm với `--release 17`. Trong trường hợp đó, Gradle chạy bằng một JVM, compiler là một JDK khác, còn sản phẩm vẫn tuân theo API và bytecode của Java 17.

`JAVA_HOME` thường ảnh hưởng đến JVM dùng để khởi động Gradle khi không có cấu hình khác. Chỉ đổi `JAVA_HOME` không phải là cách khai báo đầy đủ toolchain cho mọi project. Ngược lại, khai báo toolchain trong build script không tự bảo đảm JVM khởi chạy Gradle phù hợp với phiên bản Gradle và plugin đang sử dụng. Cả hai lớp môi trường đều cần được kiểm soát.

## 3. Khai báo Java toolchain trong Gradle

Khi project áp dụng Java Plugin hoặc một plugin cung cấp Java extension, có thể khai báo toolchain ngay trong khối `java`.

Ví dụ với Groovy DSL trong `build.gradle`:

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

Ví dụ với Kotlin DSL trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
```

Khai báo này yêu cầu Gradle tìm một JDK có major version 21 để dùng cho các tác vụ Java được tích hợp với toolchain. Với Java Plugin, compiler của các task biên dịch và launcher của các task kiểm thử được cấu hình theo toolchain. Các tác vụ Java khác như Javadoc cũng có thể sử dụng toolchain tương ứng.

`JavaLanguageVersion.of(21)` khai báo major version. Nó không phải chuỗi phiên bản đầy đủ như `21.0.2` và cũng không chỉ định duy nhất một nhà cung cấp JDK. Nếu có nhiều JDK 21 trên máy, Gradle có thể chọn một bản phù hợp với các tiêu chí đã khai báo. Vì vậy, nếu tổ chức cần thống nhất vendor, có thể bổ sung tiêu chí nhà cung cấp.

### 3.1. Chọn vendor và implementation

Toolchain API cho phép ràng buộc thêm nhà cung cấp JDK và loại implementation. Ví dụ Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Hoặc Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

Trong ví dụ, Gradle tìm JDK 21 từ vendor Adoptium. Dự án có thể chọn vendor khác theo chính sách hỗ trợ, chứng nhận, bản vá bảo mật hoặc image CI của tổ chức.

Chỉ nên ràng buộc vendor khi có lý do vận hành cụ thể. Ràng buộc càng chặt thì số JDK có thể đáp ứng càng ít; nếu máy phát triển hoặc CI không có bản phù hợp và chưa cấu hình cơ chế tải xuống, Gradle sẽ không thể tìm được toolchain. Cần chọn tiêu chí đủ để chuẩn hóa mà vẫn phù hợp với cách nhóm phân phối JDK.

## 4. Gradle tìm và cung cấp JDK như thế nào?

Khi một task yêu cầu toolchain, Gradle tìm các JDK đã cài đặt và có thể phát hiện trên máy. Việc phát hiện có thể dựa vào các vị trí cài đặt phổ biến, biến môi trường và những đường dẫn được cấu hình bổ sung.

Nếu máy đã có nhiều JDK, Gradle lọc các bản theo tiêu chí của toolchain, chẳng hạn major version, vendor và implementation. Nếu không có bản phù hợp, task có thể thất bại với thông báo không tìm thấy toolchain phù hợp.

### 4.1. Khai báo vị trí JDK cài đặt riêng

Trong môi trường có cấu trúc cài đặt JDK riêng, có thể khai báo đường dẫn trong `gradle.properties`:

```properties
org.gradle.java.installations.paths=/opt/jdks/temurin-21,/opt/jdks/zulu-17
```

Trên Windows, giá trị phải dùng đường dẫn phù hợp với máy, ví dụ:

```properties
org.gradle.java.installations.paths=C:/Java/temurin-21,C:/Java/temurin-17
```

Gradle cũng hỗ trợ chỉ định các biến môi trường chứa đường dẫn cài đặt JDK:

```properties
org.gradle.java.installations.fromEnv=JDK_17,JDK_21
```

Khi đó môi trường phải cung cấp các biến `JDK_17` và `JDK_21` với giá trị là đường dẫn đến JDK tương ứng. Cách này hữu ích trong CI hoặc máy có quy ước cài đặt riêng. Không nên ghi đường dẫn cá nhân của một lập trình viên vào cấu hình dùng chung của repository; hãy dùng cấu hình môi trường hoặc tài liệu hóa cách mỗi môi trường cung cấp JDK.

### 4.2. Tự động tải toolchain

Gradle có thể tải JDK còn thiếu nếu build đã cấu hình một toolchain resolver hỗ trợ provisioning và môi trường cho phép truy cập nguồn phân phối. Cơ chế này giúp máy mới có thể lấy đúng major version mà không cần mỗi lập trình viên tự tìm và cài đặt thủ công.

Một cách thường gặp là khai báo plugin resolver trong `settings.gradle` hoặc `settings.gradle.kts`, chẳng hạn plugin dựa trên Foojay Toolchains. Phiên bản resolver cần được nhóm lựa chọn và pin tập trung theo phiên bản Gradle, chính sách bảo mật và nguồn JDK được chấp nhận. Chỉ khai báo `languageVersion` không tự động có nghĩa mọi môi trường đều đã sẵn sàng tải xuống JDK.

Khi dùng provisioning, cần tính đến:

- Máy build cần truy cập mạng hoặc có mirror nội bộ phù hợp.
- Chính sách proxy, firewall và chứng chỉ có thể ảnh hưởng quá trình tải.
- JDK được tải sẽ được lưu trong cache Gradle để tái sử dụng.
- CI nên có cache hoặc image phù hợp để tránh tải lại không cần thiết.
- Tổ chức cần xác định nguồn phân phối JDK và quy tắc cập nhật bản vá.

Nếu build chạy trong mạng hạn chế, có thể cài JDK sẵn trên image CI hoặc cấu hình đường dẫn cài đặt được quản lý. Quan trọng là mọi môi trường đều cung cấp một toolchain đáp ứng cùng tiêu chí.

## 5. Chuẩn hóa phiên bản Java mà mã nguồn hướng tới

Chọn JDK để biên dịch chưa mô tả đầy đủ phiên bản Java mà sản phẩm hỗ trợ. Cần xác định cả mức ngôn ngữ, API và bytecode mục tiêu.

### 5.1. `sourceCompatibility` và `targetCompatibility`

Hai thuộc tính này là cơ chế tương thích truyền thống của Java Plugin:

- `sourceCompatibility` xác định phiên bản cú pháp/ngôn ngữ Java mà compiler chấp nhận.
- `targetCompatibility` xác định phiên bản định dạng bytecode mà compiler tạo ra.

Ví dụ:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

Các thuộc tính này không chọn JDK cài đặt để chạy compiler. Việc chọn JDK vẫn thuộc về toolchain hoặc môi trường build. Ngoài ra, chỉ đặt source/target không bảo đảm compiler sẽ từ chối mọi lời gọi đến API được bổ sung trong JDK mới hơn. Vì vậy, có thể tạo bytecode mang phiên bản cũ nhưng vẫn vô tình tham chiếu API chỉ tồn tại trên runtime mới.

### 5.2. Dùng `options.release` để khóa API và bytecode

Với JDK 9 trở lên, tùy chọn `--release` của `javac` cho phép biên dịch theo một bản phát hành Java mục tiêu. Tùy chọn này kết hợp kiểm soát cú pháp, bytecode và tập API Java SE được công bố cho phiên bản đó.

Trong Gradle Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Trong Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Ví dụ trên yêu cầu compiler biên dịch theo Java 17. Nếu compiler được cung cấp bởi toolchain JDK 21, compiler vẫn là JDK 21 nhưng đầu ra được giới hạn theo API và bytecode Java 17. Đây là cách hữu ích để dùng JDK mới trong quá trình build nhưng duy trì khả năng chạy trên runtime Java cũ hơn.

Khi đã dùng `options.release`, không nên đồng thời cấu hình `sourceCompatibility` hoặc `targetCompatibility` cho cùng một mục đích trên task đó. `--release` là hợp đồng tương thích rõ ràng hơn và được compiler kiểm tra thống nhất. Compiler JDK phải hỗ trợ phiên bản release được chọn; ví dụ, không thể dùng compiler JDK 17 để tạo đầu ra Java 21.

### 5.3. Toolchain và release target trong cùng một cấu hình

Một cấu hình có thể tách rõ JDK compiler và Java target:

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

Trong ví dụ này:

- JDK 21 được chọn làm bộ compiler.
- Mã nguồn được biên dịch theo quy tắc Java 17.
- Bytecode đầu ra hướng tới runtime Java 17.
- API Java SE chỉ xuất hiện từ Java 18 trở lên không được phép dùng trong mã được biên dịch theo release 17.

Ứng dụng vẫn cần được kiểm thử và triển khai trên runtime phù hợp với mục tiêu đã công bố. `options.release` không tự đóng gói JRE, không bảo đảm mọi thư viện bên thứ ba đều tương thích Java 17 và không thay thế kiểm thử trên môi trường triển khai.

## 6. Chuẩn hóa compiler và test launcher

Java toolchain không chỉ phục vụ `compileJava`. Java Plugin tích hợp toolchain vào các tác vụ Java phổ biến, nhờ đó cùng một project có thể dùng compiler và launcher đúng phiên bản đã khai báo.

Nếu cần cấu hình riêng từng task, Gradle cung cấp các API `javaToolchains.compilerFor` và `javaToolchains.launcherFor`.

Ví dụ chọn compiler cho các task biên dịch:

```groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
    options.release = 17
}
```

Ví dụ chọn launcher cho các task kiểm thử:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Cách cấu hình riêng hữu ích khi một build có nhiều nhóm task hoặc nhiều mục tiêu Java. Tuy nhiên, nếu toàn bộ project dùng cùng một toolchain, khai báo ở `java.toolchain` thường ngắn gọn và dễ hiểu hơn. Tránh cấu hình cùng một quyết định ở nhiều nơi vì chúng có thể lệch nhau khi được cập nhật.

Một dự án cũng có thể cố ý kiểm thử trên nhiều runtime. Ví dụ, compiler dùng JDK 21 để tạo bytecode Java 17, còn test matrix chạy trên Java 17 và Java 21. Khi đó cần cấu hình launcher theo từng task hoặc từng test suite, đồng thời ghi rõ mục đích của mỗi nhóm test. Không nên giả định rằng test launcher luôn phải bằng compiler JDK.

## 7. Áp dụng toolchain nhất quán cho nhiều Gradle project

Trong một multi-project build, từng subproject có thể áp dụng Java Plugin riêng. Nếu mỗi module tự khai báo toolchain, cấu hình có nguy cơ bị lệch hoặc bị quên khi thêm module mới.

Một cách quản lý tốt là tạo convention plugin nội bộ. Plugin này áp dụng hoặc cấu hình Java Plugin, đặt toolchain và release target dùng chung. Các module Java áp dụng convention plugin đó để nhận cùng chính sách.

Ví dụ minh họa logic trong một convention plugin dùng Groovy:

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

Các module cần tuân theo chính sách chỉ cần áp dụng plugin quy ước của tổ chức. Khi cần nâng compiler JDK hoặc thay Java target, nhóm có một điểm quản lý rõ ràng và có thể xem xét ảnh hưởng đến toàn bộ module.

Nếu chưa có convention plugin, có thể cấu hình các project đã áp dụng Java Plugin bằng callback `plugins.withId('java')` trong logic build dùng chung. Cách này cần cẩn thận với thứ tự áp dụng plugin và cấu hình Gradle multi-project. Với build lớn, convention plugin thường dễ kiểm thử, tái sử dụng và bảo trì hơn một khối cấu hình rải trong root build script.

Không phải mọi Gradle project đều là ứng dụng Java. Các project chỉ chứa tài liệu, cấu hình, platform hoặc tác vụ đóng gói có thể không cần Java toolchain. Chính sách nên được áp dụng cho đúng nhóm project sử dụng Java Plugin, thay vì giả định mọi subproject đều có cùng vai trò.

## 8. Toolchain ảnh hưởng đến cache và tính lặp lại của build

Gradle dùng thông tin về task, đầu vào, đầu ra và môi trường để xác định khả năng tái sử dụng kết quả. Compiler JDK và các tùy chọn biên dịch là những yếu tố có thể ảnh hưởng đến đầu ra. Việc khai báo toolchain rõ ràng giúp Gradle biết task cần một bộ công cụ nào, thay vì phụ thuộc ngầm vào JDK mặc định trên máy.

Tuy vậy, toolchain chỉ giải quyết một phần của tính lặp lại. Build vẫn có thể khác nhau nếu:

- Dependency được khai báo bằng phiên bản động hoặc không được khóa.
- Plugin build thay đổi giữa các lần chạy.
- Compiler flags hoặc annotation processor khác nhau.
- Tài nguyên được sinh từ thời gian, môi trường hoặc dữ liệu bên ngoài.
- Test phụ thuộc vào service, timezone, locale hoặc trạng thái dùng chung.
- Các máy dùng bản vá JDK khác nhau dù cùng major version và vendor.

`JavaLanguageVersion.of(21)` khóa major version 21, nhưng không nhất thiết khóa chính xác từng bản vá JDK. Nếu cần mức tái lập nghiêm ngặt hơn, tổ chức nên quản lý nguồn JDK, bản phân phối, image CI, dependency, plugin và cấu hình build theo cùng một chính sách. Gradle toolchain có thể lọc theo vendor và implementation, nhưng không thay thế hoàn toàn việc quản lý image hoặc phân phối JDK.

Đối với CI, nên dùng cùng Gradle Wrapper với máy phát triển và cung cấp JDK đáp ứng hai yêu cầu: JVM chạy Gradle phải tương thích với phiên bản Gradle đang dùng, còn toolchain phải đáp ứng cấu hình compiler/test của project. Việc cache thư mục Gradle và JDK đã tải có thể rút ngắn build, nhưng cache không nên là nguồn duy nhất bảo đảm toolchain tồn tại.

## 9. Kiểm tra toolchain đang được sử dụng

Khi build không dùng đúng JDK mong đợi, hãy kiểm tra từng lớp thay vì chỉ xem `JAVA_HOME`.

Kiểm tra phiên bản Gradle và JVM đang chạy Gradle:

```bash
./gradlew --version
```

Lệnh này cho biết phiên bản Gradle và JVM được dùng để chạy Gradle. Trên Windows, dùng `gradlew.bat --version`.

Liệt kê các toolchain mà Gradle phát hiện:

```bash
./gradlew -q javaToolchains
```

Task `javaToolchains` hiển thị các JDK được phát hiện, gồm thông tin như đường dẫn, vendor và phiên bản. Có thể dùng kết quả này để xác định vì sao một JDK không đáp ứng tiêu chí.

Tăng log khi chạy task biên dịch hoặc kiểm thử:

```bash
./gradlew compileJava --info
./gradlew test --info
```

Log chi tiết giúp tìm thông tin compiler hoặc launcher được chọn và vị trí lỗi. Nếu Gradle báo không tìm thấy toolchain, hãy kiểm tra:

1. Máy đã cài đúng major version chưa?
2. Gradle có phát hiện được đường dẫn cài đặt đó không?
3. Tiêu chí vendor/implementation có loại JDK hiện có không?
4. Nếu dùng provisioning, resolver đã được cấu hình và môi trường có thể tải JDK không?
5. JVM chạy Gradle có tương thích với phiên bản Gradle và plugin đang dùng không?
6. Compiler có hỗ trợ `options.release` mà project yêu cầu không?

Nếu `compileJava` thành công nhưng ứng dụng lỗi `UnsupportedClassVersionError` khi khởi chạy, hãy so sánh major version bytecode với phiên bản runtime thực tế. Đây thường là dấu hiệu môi trường chạy ứng dụng cũ hơn mức bytecode mà compiler tạo ra, hoặc artifact đang được triển khai không đúng bản đã kiểm tra.

## 10. Các tình huống thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build báo không tìm thấy Java toolchain | Không có JDK đúng major version hoặc Gradle không phát hiện được đường dẫn. | Cài JDK, khai báo đường dẫn cài đặt hoặc cấu hình resolver provisioning. |
| Máy cá nhân build được nhưng CI thất bại | Máy cá nhân có JDK cục bộ phù hợp, CI không có hoặc không được phép tải xuống. | Chuẩn hóa image CI hoặc cấu hình nguồn cung cấp toolchain cho CI. |
| `JAVA_HOME` là Java 17 nhưng compiler được chọn là Java 21 | Build script đã yêu cầu toolchain 21. | Kiểm tra cấu hình toolchain và task compiler; `JAVA_HOME` chỉ mô tả JVM khởi chạy Gradle trong cấu hình thông thường. |
| Bytecode mới hơn runtime triển khai | Compiler tạo class file theo mức Java cao hơn runtime hỗ trợ. | Đặt `options.release` theo phiên bản hỗ trợ và kiểm thử trên runtime mục tiêu. |
| Compiler mới nhưng mã nguồn phải hỗ trợ Java cũ | Chưa khóa API mục tiêu; mã có thể vô tình gọi API mới. | Dùng `options.release` với phiên bản Java cần hỗ trợ. |
| Gradle không khởi động được trên JDK hiện tại | Phiên bản Gradle Wrapper chưa hỗ trợ JVM dùng để chạy Gradle. | Chọn JVM chạy Gradle tương thích; toolchain cho compiler là cấu hình riêng. |
| Nhiều module dùng các JDK khác nhau ngoài dự kiến | Cấu hình toolchain bị phân tán hoặc một số module không áp dụng chính sách chung. | Đưa cấu hình vào convention plugin và áp dụng có chủ đích cho các project Java. |

### 10.1. Ví dụ: compiler mới, runtime mục tiêu cũ

Giả sử sản phẩm cần chạy trên Java 17, trong khi nhóm muốn dùng JDK 21 làm compiler. Cấu hình có thể là:

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

Khi đó, compiler được lấy từ JDK 21 và biên dịch mã theo release 17. CI cần cung cấp toolchain JDK 21, còn môi trường kiểm thử triển khai phải có Java 17 hoặc runtime mới hơn tương thích. Nếu sản phẩm có thư viện bên thứ ba chỉ hỗ trợ Java 21, cấu hình compiler không thể tự làm thư viện đó tương thích Java 17; cần kiểm tra dependency và chạy test trên runtime mục tiêu.

### 10.2. Ví dụ: chạy test trên nhiều phiên bản Java

Một sản phẩm hỗ trợ Java 17 và 21 có thể cần kiểm thử trên cả hai runtime. Có thể định nghĩa các task test riêng, mỗi task chọn một launcher:

```groovy
tasks.register('testOnJava17', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.register('testOnJava21', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đây là ví dụ khung để minh họa lựa chọn runtime. Trong dự án thực tế, cần cấu hình các task dùng đúng test classes, classpath, report destination và quan hệ phụ thuộc theo mục đích. Nếu chỉ muốn chạy cùng test suite trên nhiều JDK, có thể tổ chức test matrix ở CI để mỗi job chạy cùng lệnh với một launcher hoặc toolchain khác nhau.

## 11. Quy trình xây dựng chính sách toolchain cho nhóm

Để chuẩn hóa mà không gây nhầm lẫn, nhóm nên thống nhất theo trình tự:

1. **Xác định runtime hỗ trợ:** ghi rõ phiên bản Java thấp nhất mà sản phẩm phải chạy được và các runtime được kiểm thử.
2. **Chọn compiler JDK:** quyết định major version, vendor và implementation nếu tổ chức cần ràng buộc.
3. **Khai báo Java target:** dùng `options.release` để giới hạn API và bytecode theo runtime mục tiêu.
4. **Chọn cách cung cấp JDK:** cài sẵn trên máy/CI, cấu hình đường dẫn hoặc dùng resolver để provisioning.
5. **Đưa chính sách vào cấu hình dùng chung:** ưu tiên convention plugin cho multi-project build.
6. **Chuẩn hóa JVM chạy Gradle:** đảm bảo Gradle Wrapper và plugin có thể chạy trên JVM được chọn cho build.
7. **Kiểm tra trên CI:** xác nhận compiler, test launcher, release target và runtime triển khai đáp ứng cùng hợp đồng.
8. **Quản lý nâng cấp:** cập nhật JDK, Gradle Wrapper, plugin resolver và image CI có chủ đích; chạy lại các kiểm tra liên quan.

Một chính sách đơn giản có thể được ghi thành bảng trong tài liệu dự án:

| Quyết định | Ví dụ chính sách |
|---|---|
| JVM chạy Gradle | JDK được hỗ trợ bởi Gradle Wrapper và plugin đang dùng. |
| Compiler toolchain | JDK 21, vendor theo phân phối được tổ chức hỗ trợ. |
| Java release target | 17 nếu sản phẩm phải tương thích Java 17. |
| Test runtime | Java 17 và 21 nếu cả hai đều thuộc phạm vi hỗ trợ. |
| Nguồn JDK | Image CI hoặc toolchain resolver đã được tổ chức phê duyệt. |
| Cấu hình dùng chung | Convention plugin áp dụng cho các Gradle project Java. |

Các con số trong bảng là ví dụ minh họa, không phải mặc định phù hợp với mọi sản phẩm. Nhóm cần chọn phiên bản theo runtime thực tế, yêu cầu thư viện, chính sách bảo mật và phiên bản Gradle đang sử dụng.

## 12. Những điểm cần nhớ khi thiết kế toolchain

- Java toolchain khai báo JDK mà Gradle dùng cho các tác vụ Java; nó giúp build không phụ thuộc ngầm vào JDK mặc định của từng máy.
- JVM chạy Gradle và JDK dùng để biên dịch có thể khác nhau. Cả hai phải đáp ứng yêu cầu tương thích của Gradle, plugin và dự án.
- Major version trong toolchain chưa phải toàn bộ hợp đồng tương thích. Cần xác định thêm vendor, implementation và cách cung cấp JDK nếu tổ chức yêu cầu.
- `sourceCompatibility` và `targetCompatibility` mô tả tương thích ngôn ngữ/bytecode theo cách truyền thống; chúng không chọn JDK compiler.
- `options.release` giúp compiler giới hạn cú pháp, API Java SE và bytecode theo phiên bản mục tiêu.
- Toolchain không bảo đảm thư viện bên thứ ba, runtime triển khai hoặc dịch vụ ngoài tương thích; cần kiểm thử trên môi trường mục tiêu.
- Convention plugin giúp nhiều module áp dụng cùng một chính sách và giảm cấu hình bị lệch.
- Tính lặp lại của build còn phụ thuộc dependency, plugin, compiler flags, môi trường và dữ liệu kiểm thử.

Java toolchain biến lựa chọn JDK thành một phần có thể đọc và quản lý trong cấu hình build. Khi nhóm xác định riêng JVM chạy Gradle, compiler toolchain, test launcher và Java release target, mỗi lần build sẽ có một hợp đồng công cụ rõ ràng hơn. Hợp đồng đó giúp phát hiện sớm sai lệch giữa máy phát triển, CI và môi trường triển khai, đồng thời tạo nền tảng cho việc nâng cấp Java có kiểm soát.
