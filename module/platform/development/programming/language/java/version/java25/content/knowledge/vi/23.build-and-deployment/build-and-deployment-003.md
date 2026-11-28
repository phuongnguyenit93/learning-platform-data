# Cấu hình --release và phân biệt với source, target cùng phiên bản bytecode

Một dự án Java có thể được biên dịch bằng JDK mới nhưng vẫn cần chạy trên một JDK cũ hơn. Ví dụ, nhóm phát triển dùng JDK 27 để build, trong khi môi trường triển khai chuẩn hóa ở Java 25. Khi đó, chỉ đặt phiên bản cú pháp và phiên bản bytecode là chưa đủ: mã nguồn vẫn có thể vô tình gọi một API chỉ xuất hiện ở JDK 27.

Tùy chọn **`--release`** của `javac` giải quyết vấn đề này bằng cách kết hợp ba ràng buộc trong một cấu hình: quy tắc ngôn ngữ của release đích, API Java SE/JDK được công bố trong release đó và định dạng class file tương ứng. Đây là cách được khuyến nghị khi cross-compile cho một phiên bản Java khác với JDK đang chạy compiler.

Bài thuộc chương **Build và triển khai** của module **JAVA_VERSION_JAVA25**, tập trung vào đề bài **cấu hình --release và phân biệt với source, target cùng phiên bản bytecode**. Ví dụ sử dụng Java 25 làm phiên bản đích, JDK 25/27 làm compiler và Maven Compiler Plugin hoặc Gradle toolchains làm công cụ build.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt phiên bản JDK chạy compiler, phiên bản ngôn ngữ nguồn, API nền tảng được phép dùng, class-file version và JDK chạy ứng dụng.
2. Giải thích chính xác vai trò của `--source`, `--target` và `--release`.
3. Hiểu vì sao cặp `--source`/`--target` không bảo đảm API tương thích với runtime cũ.
4. Cấu hình `javac --release 25`.
5. Cấu hình Java release trong Maven Compiler Plugin hiện hành.
6. Kết hợp Java toolchain với `options.release` trong Gradle.
7. Đọc class-file major version và nhận biết lỗi `UnsupportedClassVersionError`.
8. Phân biệt tương thích bytecode với tương thích dependency, API, native library và hành vi runtime.
9. Xử lý đúng giới hạn của preview features khi build và triển khai.
10. Thiết kế kiểm tra CI để phát hiện việc dùng API mới hơn runtime mục tiêu.

## 2. Năm khái niệm cần tách biệt

Khi nói một ứng dụng “build bằng Java 25” hoặc “target Java 25”, cần xác định đang nói đến khía cạnh nào.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| JDK chạy compiler | Bộ JDK cung cấp javac và công cụ build | JDK 27 |
| Source level | Cú pháp và quy tắc ngôn ngữ mà compiler chấp nhận | Java 25 |
| Platform API level | Những API Java SE/JDK mà source được phép tham chiếu | API Java 25 |
| Target bytecode | Phiên bản class file được tạo ra | Major version 69 |
| Runtime JDK | JVM thực thi ứng dụng trong môi trường triển khai | JDK 25 hoặc mới hơn |

Các khái niệm này liên quan nhưng không đồng nghĩa.

Ví dụ, một máy CI có thể dùng JDK 27 để chạy compiler và tạo class file tương thích Java 25. Khi cấu hình đúng `--release 25`, compiler sẽ kiểm tra source theo Java 25, giới hạn API nền tảng theo Java 25 và tạo bytecode có major version 69.

~~~mermaid
flowchart TD
    A["JDK chạy javac: 27"] --> B["javac --release 25"]
    B --> C["Kiểm tra cú pháp Java 25"]
    B --> D["Kiểm tra API của Java 25"]
    B --> E["Sinh class file major 69"]
    C --> F["Artifact"]
    D --> F
    E --> F
    F --> G["Runtime Java 25 trở lên"]
~~~

`--release` không chọn JDK cài trên máy và cũng không tự cấu hình JVM production. Việc chọn compiler JDK và runtime JDK vẫn cần được quản lý riêng bằng toolchain, CI image, container base image hoặc cấu hình triển khai.

## 3. Vai trò của --source

`--source` quy định compiler chấp nhận cú pháp và quy tắc ngôn ngữ của phiên bản Java nào.

Ví dụ:

~~~bash
javac --source 25 Main.java
~~~

Lệnh trên yêu cầu compiler chấp nhận source theo quy tắc Java 25. Nó không có nghĩa là class file chắc chắn có định dạng Java 25, cũng không giới hạn toàn bộ API được tham chiếu xuống Java 25.

Nếu không chỉ định `--target`, compiler tạo class file theo mặc định của compiler đang chạy. Nếu compiler là JDK 27, bytecode mặc định có thể mang định dạng JDK 27.

`--source` hữu ích khi cần kiểm soát cú pháp trong một số quy trình biên dịch đặc thù. Với mục tiêu cross-compile một ứng dụng để chạy trên JDK cụ thể, chỉ dùng `--source` là chưa đủ.

## 4. Vai trò của --target

`--target` quy định phiên bản class-file format mà compiler tạo ra.

Ví dụ:

~~~bash
javac --source 25 --target 25 Main.java
~~~

Mục tiêu là tạo class file mà JVM Java 25 có thể hiểu. Tuy nhiên, `--target` không giới hạn các API mà source có thể gọi.

Compiler vẫn có thể nhìn thấy API từ JDK đang chạy. Nếu JDK 27 cung cấp một method chưa có trong JDK 25, source có thể biên dịch thành công khi chỉ đặt target bytecode 25. Khi chạy trên Java 25, chương trình có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.

`--target` cũng không thay thế việc chọn source level. Khi kết hợp hai tùy chọn riêng biệt, target phải bằng hoặc mới hơn source.

## 5. Vì sao source và target riêng lẻ chưa đủ?

Giả sử ứng dụng cần chạy trên Java 17, nhưng developer đang dùng JDK 25. Java 21 bổ sung method `List.getFirst()`. Method này có thể được compiler JDK 25 nhìn thấy dù source và target đều đặt là 17.

Ví dụ:

~~~java
import java.util.List;

class ApiCompatibilityExample {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        System.out.println(names.getFirst());
    }
}
~~~

Biên dịch bằng JDK 25 với source và target 17:

~~~bash
javac --source 17 --target 17 ApiCompatibilityExample.java
~~~

Compiler có thể chấp nhận lời gọi `getFirst()` vì API đang tham chiếu đến là API của JDK 25. Class file được tạo ở định dạng Java 17, nhưng method `List.getFirst()` không tồn tại trong Java 17. Khi chạy trên Java 17, chương trình thất bại lúc liên kết method.

Nếu biên dịch cùng source bằng:

~~~bash
javac --release 17 ApiCompatibilityExample.java
~~~

Compiler từ chối lời gọi `getFirst()` vì method đó không thuộc API của Java 17. Lỗi được phát hiện ngay trong build thay vì chờ tới runtime.

Đây là khác biệt quan trọng nhất giữa `--release` và việc tự ghép `--source` với `--target`.

## 6. --release kết hợp ba ràng buộc

`--release N` yêu cầu compiler:

1. Biên dịch source theo quy tắc ngôn ngữ của Java release N.
2. Kiểm tra source dựa trên API Java SE và JDK được công bố cho release N.
3. Tạo class file tương thích với release N.

Ví dụ:

~~~bash
javac --release 25 -d out src/com/example/Main.java
~~~

Nếu đang chạy JDK 27, compiler vẫn tạo bytecode mục tiêu Java 25 và kiểm tra API theo Java 25. Vì vậy, code không thể vô tình gọi một API chỉ có từ Java 26/27 nếu API đó không tồn tại trong Java 25.

Tùy chọn này được giới thiệu trong javac từ JDK 9 và là cách ưu tiên cho cross-compilation trên các JDK hiện đại.

### 6.1. --release không thể kết hợp với --source hoặc --target

Các lệnh sau không hợp lệ:

~~~bash
javac --release 25 --source 25 Main.java
javac --release 25 --target 25 Main.java
~~~

`--release` đã bao gồm vai trò của cả source level và target bytecode. Không cần khai báo lại chúng.

### 6.2. --release kiểm tra API nào?

Compiler kiểm tra các API Java SE và JDK được định nghĩa cho release đích, gồm các package được export theo module của release đó. Với release trước, tập API tương ứng với release lịch sử đó.

`--release` không cho phép dùng các tùy chọn mở rộng export để phá vỡ tập API được xác định cho release đích. Nó cũng không phải cơ chế kiểm tra mọi API của thư viện bên thứ ba.

## 7. Phiên bản bytecode và class-file major version

Mỗi class file có một cặp số phiên bản major và minor. JVM dùng chúng để xác định định dạng class file có được hỗ trợ hay không.

Một số phiên bản thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| Java 27 | 71 |

Java 25 tạo class file có major version **69**. Java 27 tạo class file có major version **71**.

Nếu một class file Java 27 được đưa vào ứng dụng chạy bằng Java 25, JVM Java 25 không hiểu major version 71 và có thể ném:

~~~text
java.lang.UnsupportedClassVersionError:
... class file version 71.0, this version of the Java Runtime only recognizes class file versions up to 69.0
~~~

Đây là lỗi khác với `NoSuchMethodError`:

- `UnsupportedClassVersionError`: JVM không hỗ trợ định dạng class file.
- `NoSuchMethodError`: class file tải được nhưng method được tham chiếu không tồn tại trong phiên bản class/API lúc runtime.

### 7.1. Kiểm tra major version bằng javap

Sau khi build:

~~~bash
javap -verbose -classpath out com.example.Main
~~~

Trong output, tìm dòng:

~~~text
major version: 69
~~~

Nếu thấy 69, class file được tạo theo định dạng Java 25. Nếu thấy 71, artifact đang chứa class file định dạng Java 27.

Lưu ý: kiểm tra một class đại diện chưa đủ để chứng minh toàn bộ artifact tương thích. Dependency JAR, generated class và module khác cũng có thể chứa class file mới hơn.

## 8. Ví dụ cấu hình javac cho Java 25

Giả sử cấu trúc source:

~~~text
project/
  src/
    com/
      example/
        Main.java
  out/
~~~

Dùng JDK 25 hoặc JDK mới hơn có hỗ trợ release 25:

~~~bash
javac --release 25 -encoding UTF-8 -d out src/com/example/Main.java
~~~

Chạy bằng Java 25:

~~~bash
java -cp out com.example.Main
~~~

Nếu dùng JDK 27 để biên dịch và muốn kiểm tra compiler đang được chọn:

~~~bash
javac -version
java -version
~~~

Trong CI, cần xác nhận đường dẫn JDK mà build tool thực sự sử dụng; kết quả của terminal developer không nhất thiết giống JVM của Maven/Gradle daemon.

## 9. Cấu hình --release trong Maven

Maven Compiler Plugin hỗ trợ cấu hình release bằng property `maven.compiler.release` hoặc phần tử `release` trong plugin configuration. Plugin hiện hành được tài liệu Apache công bố là phiên bản 3.16.0.

Ví dụ cấu hình trong `pom.xml`:

~~~xml
<project>
    <properties>
        <maven.compiler.release>25</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
</project>
~~~

Trong cấu hình trên:

- `maven.compiler.release` truyền release 25 cho compiler.
- Plugin version được khóa rõ ràng để build có thể tái lập.
- Maven dùng javac tương ứng với JDK/toolchain đã được chọn.
- Source, API và bytecode được kiểm tra theo Java 25.

Có thể đặt trực tiếp `<release>25</release>` trong phần `<configuration>` của plugin nếu dự án muốn gom cấu hình vào plugin. Chọn một cách cấu hình làm nguồn sự thật duy nhất để tránh các giá trị mâu thuẫn.

### 9.1. Chạy Maven Wrapper

Dùng Maven Wrapper của dự án để cố định phiên bản Maven:

~~~bash
./mvnw clean verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd clean verify
~~~

Kiểm tra JDK Maven đang chạy:

~~~bash
./mvnw -v
~~~

Maven Compiler Plugin dùng compiler JDK được Maven/toolchain cung cấp. Nếu cần biên dịch đúng bằng JDK 25 để dùng preview feature Java 25, phải chọn JDK 25 cho compiler; chỉ đặt release 25 trên compiler JDK 27 không biến preview feature Java 25 thành preview feature hợp lệ của JDK 27.

## 10. Cấu hình --release trong Gradle

Gradle cung cấp hai cơ chế có vai trò riêng:

- Java toolchain chọn bộ JDK được dùng cho compile/test/Javadoc tasks.
- `options.release` truyền tùy chọn release cho javac để giới hạn source, API và bytecode.

Ví dụ với `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 25
}
~~~

Ví dụ Groovy DSL trong `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 25
}
~~~

Trong ví dụ này, toolchain chọn JDK 25 để thực hiện tác vụ Java và `options.release` xác nhận rõ platform release cần target. Nếu tổ chức dùng JDK 27 làm compiler nhưng muốn tạo artifact Java 25, có thể chọn toolchain 27 và giữ `options.release = 25`; cần kiểm tra Gradle và compiler version được hỗ trợ trong môi trường build.

### 10.1. Toolchain không thay thế --release

Chỉ cấu hình toolchain 25 có nghĩa là build dùng JDK 25. Nó không phải cách diễn đạt đầy đủ yêu cầu cross-compile khi compiler có thể được thay bằng JDK khác trong tương lai.

Ngược lại, chỉ cấu hình `options.release = 25` giới hạn cách compiler xử lý source nhưng không chọn JDK chạy Gradle hoặc JDK được dùng cho các task khác.

Kết hợp toolchain và release giúp build mô tả rõ cả JDK được chọn lẫn compatibility target.

## 11. --release không bảo đảm toàn bộ ứng dụng tương thích runtime

`--release` kiểm tra source đang biên dịch đối với API của JDK release đích. Nó không tự động biến mọi thành phần của ứng dụng thành artifact tương thích.

Cần kiểm tra riêng:

| Thành phần | `--release` kiểm tra trực tiếp? | Việc cần làm |
|---|---|---|
| Source Java của module đang compile | Có | Chọn đúng release |
| API Java SE/JDK được source tham chiếu | Có | Tránh API mới hơn target |
| Class file được tạo | Có | Kiểm tra major version |
| Thư viện bên thứ ba trong dependency graph | Không bảo đảm | Chọn phiên bản hỗ trợ runtime đích |
| Generated class từ annotation processor | Không nên mặc định | Kiểm tra compiler/plugin và bytecode được sinh |
| Native library/JNI | Không | Build và test theo OS/architecture/runtime |
| Reflection, service loading, resource | Không đầy đủ | Test integration trên runtime mục tiêu |
| Hành vi API thay đổi giữa các JDK | Không | Chạy test trên JDK đích |
| Cấu hình container và JVM flags | Không | Kiểm tra image và command runtime |

Ví dụ, source của bạn có thể được biên dịch thành class file Java 25 nhưng một thư viện phụ thuộc lại chứa class file Java 27. Khi ứng dụng chạy trên Java 25, JVM vẫn có thể thất bại lúc tải dependency đó.

Tương tự, thư viện có thể có class file cũ nhưng gọi API mới bằng reflection hoặc tải native library chỉ hỗ trợ một số môi trường. Vì vậy, compatibility target cần được kiểm tra ở cấp toàn bộ dependency graph và runtime image.

## 12. Preview features và giới hạn phiên bản

Preview features có vòng đời riêng và được bật bằng `--enable-preview` ở cả compile time và runtime.

Nếu source dùng preview feature của Java 25, quy trình phải dùng compiler JDK 25:

~~~bash
javac --release 25 --enable-preview -d out src/com/example/Main.java
java --enable-preview -cp out com.example.Main
~~~

Class file dùng preview feature Java 25 có major version 69 và minor version 65535. Nó chỉ được JVM tương ứng với Java 25 tải khi preview được bật.

Không thể dùng JDK 27 compiler để bật preview của Java 25 bằng cách đặt `--release 25`. Preview được gắn với chính release của compiler/runtime; preview class từ release cũ không phải artifact tương thích để mang sang JDK mới.

Nếu ứng dụng không dùng preview feature, không bật `--enable-preview` chỉ vì đang build bằng JDK mới. Giữ build ở API final giúp giảm ràng buộc khi nâng cấp runtime.

## 13. Chọn JDK build và runtime

Một pipeline có thể dùng JDK mới hơn runtime đích để tận dụng compiler và công cụ hiện đại, miễn là target được kiểm soát.

| Mục tiêu | Compiler JDK | Release target | Runtime kiểm thử/production |
|---|---|---|---|
| Ứng dụng Java 25 thông thường | JDK 25 | 25 | JDK 25 |
| Cross-compile Java 25 bằng compiler mới hơn | JDK 27 | 25 | JDK 25 |
| Ứng dụng dùng preview feature Java 25 | JDK 25 | 25 + preview | JDK 25 + preview |
| Ứng dụng Java 27 | JDK 27 | 27 | JDK 27 |

Không suy ra runtime mục tiêu chỉ từ phiên bản compiler. Hãy khai báo rõ runtime JDK trong container image, deployment manifest hoặc cấu hình môi trường.

## 14. Kiểm tra trong CI/CD

Một pipeline build đáng tin cậy cần kiểm tra các tầng khác nhau:

1. In ra phiên bản JDK mà Maven/Gradle thực sự sử dụng.
2. Build với release target đã khai báo trong repository.
3. Chạy unit test bằng runtime mục tiêu.
4. Chạy integration test với các dependency thật hoặc môi trường tương đương.
5. Kiểm tra class-file version của artifact.
6. Kiểm tra dependency có yêu cầu JDK cao hơn runtime mục tiêu hay không.
7. Đóng gói và chạy thử đúng container image production.

Ví dụ một bước kiểm tra cơ bản:

~~~bash
java -version
javac -version
./mvnw -v
./mvnw clean verify
~~~

Với Gradle:

~~~bash
java -version
./gradlew --version
./gradlew clean test
~~~

Sau build, dùng `javap -verbose` để kiểm tra một số class đại diện. Với ứng dụng nhiều module, hãy kiểm tra thêm dependency JAR và generated output; một class đúng version không chứng minh tất cả class đều đúng.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `invalid flag: --release` | Compiler quá cũ hoặc không phải javac phù hợp | Kiểm tra JDK chạy compiler; `--release` được javac hỗ trợ từ JDK 9 |
| `release version 25 not supported` | Compiler JDK không hỗ trợ release 25 | Dùng JDK 25 trở lên có hỗ trợ target 25 |
| Source dùng cú pháp mới nhưng compile thất bại | Source level thấp hơn cú pháp đang dùng | Nâng release/source theo runtime mục tiêu được phép |
| `cannot find symbol` khi dùng API mới | API không tồn tại trong release đã chọn | Kiểm tra API availability; không hạ target chỉ để bỏ lỗi |
| `UnsupportedClassVersionError` | Một class file mới hơn JVM runtime | Tìm class file major version cao và build lại dependency phù hợp |
| `NoSuchMethodError` | Class file tải được nhưng runtime API không có method | Dùng `--release` và kiểm tra dependency/API thực tế |
| Maven dùng JDK khác terminal | Maven Wrapper/IDE/CI chọn JVM khác | Kiểm tra `mvnw -v`, Maven toolchains và CI image |
| Gradle dùng JDK khác dự kiến | Gradle daemon và Java toolchain là hai lựa chọn riêng | Kiểm tra `./gradlew --version` và toolchain |
| Dùng `--release` cùng `--source` hoặc `--target` bị từ chối | Các tùy chọn trùng trách nhiệm | Chỉ giữ `--release` |
| Preview class không chạy trên JDK khác | Preview gắn với đúng release | Biên dịch và chạy bằng cùng JDK release có preview đó |
| Ứng dụng target đúng nhưng dependency không tải được | Dependency có bytecode/API yêu cầu JDK mới hơn | Nâng/hạ phiên bản dependency và test trên runtime đích |
| Một số module đúng, module khác sai | Cấu hình compiler không đồng nhất | Đặt release ở parent/build convention và xác minh mọi compile task |

## 16. Bài tập thực hành

**Bài 1 — So sánh source và target:** dùng JDK 25 biên dịch ví dụ gọi `List.getFirst()` với `--source 17 --target 17`. Chạy trên JDK 17 và giải thích lỗi liên kết method.

**Bài 2 — Dùng release:** biên dịch cùng ví dụ với `--release 17`. Quan sát lỗi compiler và giải thích vì sao lỗi xuất hiện sớm.

**Bài 3 — Java 25 target:** dùng JDK 27 biên dịch một ứng dụng thông thường với `--release 25`. Kiểm tra major version bằng `javap -verbose`.

**Bài 4 — Maven:** cấu hình `maven.compiler.release` là 25, chạy Maven Wrapper và xác minh JDK Maven sử dụng.

**Bài 5 — Gradle:** cấu hình toolchain 25 cùng `options.release = 25`. Kiểm tra compile task và test task dùng đúng toolchain.

**Bài 6 — Dependency:** thêm một thư viện có yêu cầu runtime mới hơn target. Xác định vì sao source vẫn build nhưng ứng dụng không chạy trên runtime cũ.

**Bài 7 — Preview:** thử compile một preview feature Java 25 bằng JDK 25 và bằng JDK 27. Ghi nhận giới hạn của `--enable-preview`.

**Bài 8 — CI:** tạo bước xác minh phiên bản JDK, release target, class-file major version và runtime test.

## 17. Checklist hoàn thành

- [ ] Phân biệt JDK compiler, source level, platform API, bytecode target và runtime JDK.
- [ ] Hiểu `--source` chỉ điều khiển quy tắc ngôn ngữ.
- [ ] Hiểu `--target` điều khiển class-file version.
- [ ] Hiểu vì sao source/target không giới hạn API nền tảng.
- [ ] Dùng `--release 25` cho cross-compilation Java 25.
- [ ] Biết `--release` không kết hợp với `--source` hoặc `--target`.
- [ ] Biết Java 25 có class-file major version 69.
- [ ] Biết JDK 27 có class-file major version 71.
- [ ] Kiểm tra bytecode bằng `javap -verbose`.
- [ ] Cấu hình Maven Compiler Plugin release.
- [ ] Kết hợp Gradle Java toolchain và `options.release`.
- [ ] Kiểm tra dependency và generated class riêng.
- [ ] Hiểu preview class cần compiler/runtime cùng release.
- [ ] Chạy test trên runtime JDK thực tế.
- [ ] Có kiểm tra compatibility trong CI/CD.

## Tài liệu tham khảo chính thức

- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): định nghĩa `--release`, `--source`, `--target` và các giới hạn khi biên dịch cho release khác.
- [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): semantics hiện hành của các compiler option và hỗ trợ cross-release.
- [JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): thiết kế `--release`.
- [Java SE 25 — ClassFile](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html): major version 69 của Java 25 và minor version cho preview class.
- [Java SE 27 — ClassFile](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html): major version 71 của Java 27.
- [JVM Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): cấu trúc và phiên bản class file.
- [Preview Features — Java 25](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): bật preview ở compiler/runtime và giới hạn tương thích giữa các release.
- [Apache Maven Compiler Plugin — Setting the --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cấu hình release bằng Maven Compiler Plugin.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): kết hợp toolchain với release flag và phân biệt với source/target compatibility.

## Kết luận

`--source` điều khiển cú pháp Java được chấp nhận, `--target` điều khiển định dạng class file được tạo, còn **`--release` kết hợp source level, API nền tảng và bytecode target trong một cấu hình nhất quán**. Vì thế, khi build ứng dụng Java 25 bằng JDK 25 hoặc JDK mới hơn để chạy trên Java 25, hãy ưu tiên `--release 25`.

Toolchain giúp chọn đúng JDK cho compiler và các task build; release flag giúp kiểm soát compatibility của source và bytecode; runtime test xác nhận artifact cùng dependency thực sự hoạt động trên môi trường triển khai. **Ba lớp kiểm soát này cần được thể hiện rõ trong build configuration và CI/CD để tránh lỗi tương thích chỉ xuất hiện sau khi phát hành.**
