# Chọn `--release` theo đúng ngôn ngữ và API đích

Khi phát triển bằng JDK 26, dự án vẫn có thể cần chạy trên JDK 21 hoặc một phiên bản Java khác. Cài JDK mới nhất để biên dịch không có nghĩa ứng dụng tự động tương thích với mọi JDK cũ hơn. Cần khai báo rõ phiên bản Java thấp nhất mà sản phẩm hỗ trợ, rồi để trình biên dịch kiểm tra cả cú pháp, bytecode và API theo phiên bản đó.

Tùy chọn `javac --release N` là cách chuẩn để đặt mục tiêu này. Nó giúp tránh tình huống mã nguồn được biên dịch thành bytecode cũ nhưng vô tình gọi API chỉ có ở JDK mới.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt JDK dùng để chạy quá trình build với phiên bản Java mà sản phẩm hỗ trợ.
- Giải thích `--release` kiểm soát những gì và vì sao `--source` kết hợp `--target` chưa đủ để bảo đảm tương thích API.
- Chọn release dựa trên môi trường chạy thấp nhất và API mà mã nguồn thực sự cần.
- Cấu hình release trong `javac`, Maven hoặc Gradle; kết hợp với Java toolchain khi cần cố định JDK biên dịch.
- Nhận biết trường hợp preview feature hoặc incubator API cần điều kiện biên dịch và chạy riêng.

## 1. Phân biệt ba phiên bản trong một quy trình Java

Một dự án có thể đồng thời có ba phiên bản Java khác nhau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| JDK chạy build | JDK thực thi Maven, Gradle hoặc `javac` | JDK 26 trên máy lập trình và CI |
| Release biên dịch | Phiên bản ngôn ngữ, bytecode và API mà compiler cho phép sử dụng | `--release 21` |
| JDK chạy ứng dụng | Phiên bản JVM thấp nhất được cam kết hỗ trợ khi triển khai | JDK 21 trở lên |

Ví dụ, nhóm có thể dùng JDK 26 để biên dịch và vẫn phát hành ứng dụng cho môi trường JDK 21. Khi đó, mã nguồn phải tuân thủ cú pháp và API của Java 21, bytecode phải tương thích với JVM 21, và kiểm thử phải có bước chạy trên JDK 21.

Điểm cần nhớ: **phiên bản JDK cài trên máy không tự quyết định phiên bản Java tối thiểu của sản phẩm**. Mục tiêu chạy thực tế mới quyết định release cần chọn.

## 2. `--release` bảo đảm điều gì?

Với lệnh:

```bash
javac --release 21 -d out src/main/java/com/example/Main.java
```

compiler áp dụng đồng thời ba giới hạn:

1. **Quy tắc ngôn ngữ Java 21:** không chấp nhận cú pháp chỉ được bổ sung ở các phiên bản sau Java 21.
2. **Định dạng bytecode Java 21:** tạo class file có thể được JVM Java 21 đọc.
3. **API của Java 21:** chỉ cho phép mã nguồn tham chiếu các API Java SE và JDK được công bố cho release 21.

Giới hạn API rất quan trọng. Ví dụ, `List.getFirst()` có từ Java 21. Nếu dự án phải chạy trên Java 17, biên dịch bằng JDK 26 với `--release 17` sẽ phát hiện lời gọi này ngay trong lúc build:

```java
import java.util.List;

class FirstItem {
    static String first(List<String> values) {
        return values.getFirst();
    }
}
```

Đổi compiler sang `--release 21` thì lời gọi trên hợp lệ, nhưng sản phẩm lúc này yêu cầu runtime Java 21 trở lên. Nếu yêu cầu vẫn là Java 17, cần thay lời gọi bằng API có trong Java 17 hoặc thay đổi chính sách phiên bản runtime của sản phẩm.

### Vì sao chỉ đặt `--source` và `--target` chưa đủ?

Hai tùy chọn này kiểm soát hai phần riêng:

| Tùy chọn | Kiểm soát | Không tự bảo đảm |
|---|---|---|
| `--source 17` | Quy tắc cú pháp và ngôn ngữ Java 17 | Bytecode và API chỉ thuộc Java 17 |
| `--target 17` | Phiên bản bytecode được tạo ra | API được gọi có tồn tại trên Java 17 |
| `--release 17` | Ngôn ngữ, bytecode và API của Java 17 | Tương thích của dependency, runtime, hệ điều hành hoặc hành vi ứng dụng |

Nếu dùng JDK 26 cùng `--source 17 --target 17`, compiler vẫn có thể nhìn thấy API của JDK 26. Mã nguồn có thể gọi một phương thức chỉ xuất hiện sau Java 17 rồi tạo bytecode ở định dạng Java 17. Ứng dụng sẽ gặp lỗi khi chạy trên JVM 17 vì phương thức đó không tồn tại. `--release 17` ngăn lỗi tương thích API kiểu này ngay từ bước biên dịch.

Vì vậy, với dự án mới hoặc dự án cần kiểm soát tương thích nền tảng, ưu tiên `--release`. Không ghép `--release` với `--source` hoặc `--target` trong cùng một lệnh; `javac` không cho phép kết hợp các tùy chọn này.

## 3. Chọn release theo môi trường triển khai

Hãy xác định release theo trình tự sau:

1. **Xác định runtime thấp nhất được hỗ trợ.** Kiểm tra máy chủ, container image, nền tảng cloud, thiết bị người dùng và chính sách vận hành. Nếu môi trường thấp nhất là Java 21, release tối thiểu phải là 21.
2. **Đối chiếu API cần dùng.** Nếu mã nguồn cần API chỉ có từ Java 25 hoặc Java 26, không thể giữ cam kết chạy trên Java 21 chỉ bằng cách đổi cờ compiler. Phải thay API hoặc nâng phiên bản runtime tối thiểu.
3. **Chọn release bằng số phiên bản Java.** Dùng `21`, `25`, `26`...; không viết theo dạng `1.21` hoặc `1.26`.
4. **Kiểm tra compiler hỗ trợ release đó.** Chạy `javac --help` trên đúng JDK được dùng để build. Compiler chỉ hỗ trợ release hiện tại và một số release trước đó; không giả định mọi phiên bản JDK đều biên dịch được mọi release cũ.
5. **Kiểm thử trên runtime tối thiểu.** Biên dịch thành công không thay thế được việc chạy test trên đúng JDK mà sản phẩm cam kết hỗ trợ.

Một số tình huống thường gặp:

| Yêu cầu sản phẩm | Cách chọn |
|---|---|
| Dùng JDK 26 để build, ứng dụng phải chạy trên Java 21 | Dùng compiler JDK 26 và `--release 21`; chạy test trên JDK 21 |
| Ứng dụng cần API chính thức chỉ có từ Java 25 | Chọn `--release 25` và đặt runtime tối thiểu là Java 25 |
| Ứng dụng cần API chính thức của Java 26 | Chọn `--release 26` và triển khai trên JDK 26 tương thích |
| Dự án dùng preview feature của Java 26 | Dùng JDK 26, `--release 26` và `--enable-preview`; runtime cũng phải bật preview trên JDK 26 |

Đối với thư viện dùng bởi nhiều ứng dụng, release thường được quyết định bởi phiên bản Java thấp nhất mà thư viện cam kết hỗ trợ. Nâng release có thể buộc mọi ứng dụng tiêu thụ thư viện phải nâng runtime theo.

## 4. Preview feature và incubator API cần được xử lý riêng

`--release` đặt nền tảng ngôn ngữ và API đích. Nó không tự bật các tính năng đang ở giai đoạn preview hoặc incubator.

### Preview feature

Preview feature là tính năng ngôn ngữ hoặc API được cung cấp để đánh giá trước khi trở thành chính thức. Với preview feature của JDK 26, biên dịch cần dùng đúng JDK 26 và bật preview:

```bash
javac --release 26 --enable-preview -d out src/main/java/com/example/Main.java
java --enable-preview -cp out com.example.Main
```

Khi chạy, JVM phải bật `--enable-preview` và dùng đúng phiên bản Java đã tạo preview feature đó. Preview của một release không phải cam kết tương thích ngược hoặc tương thích tiến. Không thể dùng JDK 26 để bật preview của Java 25 bằng cách đặt `--release 25`.

Chỉ bật preview khi bài toán thực sự cần tính năng đó và nhóm chấp nhận theo dõi thay đổi giữa các release. Nếu API đã trở thành chính thức ở một release sau, hãy ưu tiên API chính thức và cập nhật release đích khi chính sách runtime cho phép.

### Incubator API

Incubator API được phân phối qua module incubator và có thể thay đổi giữa các release. Ví dụ, Vector API thuộc module `jdk.incubator.vector` trong các JDK đang cung cấp API này ở trạng thái incubator.

Khi dùng incubator API, cần kiểm tra tài liệu của đúng JDK, khai báo module cần thiết theo hướng dẫn (chẳng hạn `--add-modules jdk.incubator.vector` khi phù hợp), rồi kiểm thử trên runtime có module tương ứng. Việc đặt `--release` không biến incubator API thành API ổn định, cũng không tự thêm module vào ứng dụng. Nếu sản phẩm cần cam kết tương thích dài hạn, hãy đánh giá kỹ rủi ro trước khi phụ thuộc vào incubator API.

## 5. Cấu hình trong các công cụ build

### Dùng `javac` trực tiếp

```bash
javac --release 21 -d out src/main/java/com/example/Main.java
java -cp out com.example.Main
```

Lệnh đầu tiên cần một JDK có compiler hỗ trợ release 21. Lệnh thứ hai chạy ứng dụng bằng JVM đang được gọi qua `PATH`; hãy xác nhận đó là Java 21 hoặc phiên bản mới hơn. `--release` là tùy chọn của compiler, không phải tùy chọn của lệnh `java` để chọn JVM chạy chương trình.

### Dùng Maven

Khai báo release trong `pom.xml` và cố định phiên bản Maven Compiler Plugin phù hợp với JDK của dự án:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
        </plugin>
    </plugins>
</build>
```

`maven.compiler.release` truyền mục tiêu tương đương `javac --release` cho Maven Compiler Plugin. Thuộc tính này không tự chọn JDK mà Maven hoặc compiler sẽ sử dụng. Nếu cần cố định JDK biên dịch giữa máy cá nhân và CI, cấu hình Maven Toolchains và kiểm tra JDK thực tế bằng `mvn -v` cùng cấu hình toolchain của dự án.

### Dùng Gradle Kotlin DSL

Kết hợp Java toolchain với `options.release` để chỉ định riêng JDK biên dịch và nền tảng đích:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(26)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

Ví dụ trên yêu cầu Gradle tìm JDK 26 làm compiler, đồng thời yêu cầu compiler giới hạn mã nguồn ở Java 21. Máy chạy ứng dụng vẫn cần Java 21 trở lên. Dùng phiên bản Gradle có hỗ trợ toolchain cho JDK 26; theo ma trận tương thích hiện hành, hỗ trợ toolchain Java 26 bắt đầu từ Gradle 9.4.0. Kiểm tra lại ma trận khi nâng JDK hoặc Gradle.

`options.release` không chọn compiler JDK. Toolchain mới đảm nhiệm việc chọn JDK. Nếu chỉ cấu hình `sourceCompatibility` và `targetCompatibility`, Gradle không tự bảo đảm mã nguồn chỉ dùng API có trong release đích. Với yêu cầu tương thích nghiêm ngặt, dùng `options.release`.

## 6. Kiểm tra cấu hình trước khi phát hành

Thực hiện các bước sau trên máy lập trình và trong CI:

```bash
java -version
javac -version
javac --help
mvn -v
```

Với Gradle, kiểm tra phiên bản wrapper và JVM của Gradle bằng:

```bash
./gradlew --version
```

Sau đó xác minh:

- JDK chạy build và JDK được toolchain chọn đúng như cấu hình.
- `--release` trùng với phiên bản runtime thấp nhất mà sản phẩm hỗ trợ.
- Maven Compiler Plugin hoặc Gradle wrapper đủ mới để hỗ trợ JDK và cấu hình release đang dùng.
- Các thư viện phụ thuộc cũng hỗ trợ runtime mục tiêu; `--release` chỉ kiểm soát mã nguồn được biên dịch trong tác vụ đó, không hạ phiên bản bytecode của dependency đã biên dịch sẵn.
- Unit test, integration test và smoke test chạy được trên runtime tối thiểu, không chỉ trên JDK mới nhất của máy phát triển.
- Nếu dùng preview feature, lệnh chạy test và lệnh khởi động ứng dụng cũng bật preview trên đúng JDK.
- Nếu dùng incubator module, module đó tồn tại và được cấu hình đúng trên môi trường chạy.

`--release` là kiểm tra tĩnh quan trọng ở thời điểm biên dịch. Nó không bảo đảm dependency bên thứ ba tương thích, không phát hiện mọi khác biệt hành vi giữa các JDK, không xác nhận native library hoặc cấu hình hệ điều hành, và không thay thế kiểm thử trên môi trường triển khai thật.

## 7. Nhận biết lỗi cấu hình thường gặp

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `release version ... not supported` | Compiler đang dùng quá cũ so với release yêu cầu | Chọn JDK compiler mới hơn có hỗ trợ release đó, hoặc điều chỉnh release theo runtime mục tiêu |
| `cannot find symbol` với một phương thức JDK mới | API đó không thuộc release đang đặt trong `--release` | Dùng API có trong release đích hoặc nâng runtime tối thiểu và release |
| `invalid flag: --release` | Đang gọi compiler không hỗ trợ tùy chọn này, thường là JDK quá cũ | Kiểm tra `javac -version`, `PATH`, `JAVA_HOME` và toolchain |
| `class file has wrong version` hoặc `UnsupportedClassVersionError` | JVM chạy ứng dụng cũ hơn phiên bản bytecode của class file | Nâng JVM chạy hoặc build lại với release phù hợp |
| `Preview features are not enabled` | Chưa bật preview khi biên dịch hoặc chạy | Bật `--enable-preview` ở cả hai bước và dùng đúng JDK của preview |
| `--release` không được kết hợp với `--source` hoặc `--target` | Build script đang đặt các tùy chọn loại trừ nhau | Giữ `--release`, bỏ các cấu hình `source`/`target` trùng lặp |

Khi gặp lỗi, hãy tìm nơi cấu hình compiler thực sự nhận tham số. IDE, Maven, Gradle và CI có thể dùng JDK hoặc cấu hình riêng; sửa `JAVA_HOME` mà không kiểm tra toolchain có thể không thay đổi compiler đang chạy.

## 8. Bài tập thực hành

Một dịch vụ được build trên máy phát triển có JDK 26. Môi trường triển khai thấp nhất là Java 21. Mã nguồn dùng `List.getFirst()` và `Thread.ofVirtual()`, đều là API có từ Java 21.

**Yêu cầu:**

1. Chọn release phù hợp và giải thích vì sao không chọn 26 chỉ vì máy build đã cài JDK 26.
2. Viết lệnh `javac` để biên dịch một file `Main.java` vào thư mục `out`.
3. Nếu dự án dùng Gradle, nêu cấu hình toolchain JDK 26 và release 21.
4. Nêu ít nhất hai bước kiểm tra để chứng minh ứng dụng chạy trên runtime tối thiểu.
5. Giả sử nhóm muốn dùng một API chính thức chỉ xuất hiện ở Java 25. Hãy nêu hai lựa chọn để giải quyết mà không che giấu yêu cầu runtime mới.

**Kết quả mong đợi:**

- Chọn `--release 21`, vì Java 21 là runtime thấp nhất và đã cung cấp các API được nêu.
- Biên dịch bằng `javac --release 21 -d out Main.java`.
- Trong Gradle, chọn toolchain 26 và đặt `options.release = 21`.
- Chạy test hoặc smoke test bằng JDK 21; đồng thời kiểm tra dependency và cấu hình khởi động trên cùng runtime.
- Với API chỉ có từ Java 25, hoặc thay API bằng cách triển khai tương đương có trong Java 21, hoặc nâng runtime tối thiểu lên Java 25 và đổi release thành 25.

## Tài liệu tham khảo

- [The `javac` Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): ý nghĩa `--release`, giới hạn API và các tùy chọn biên dịch liên quan.
- [Preparing for Migration — Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html): khuyến nghị dùng `--release` khi biên dịch cho phiên bản Java đích.
- [Setting the `--release` of the Java Compiler — Maven Compiler Plugin](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cấu hình release trong Maven.
- [Building Java & JVM Projects — Gradle](https://docs.gradle.org/current/userguide/building_java_projects.html) và [Toolchains for JVM Projects — Gradle](https://docs.gradle.org/current/userguide/toolchains.html): cấu hình toolchain, release và khác biệt với source/target compatibility.
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): kiểm tra phiên bản Gradle hỗ trợ JDK dùng cho toolchain.
