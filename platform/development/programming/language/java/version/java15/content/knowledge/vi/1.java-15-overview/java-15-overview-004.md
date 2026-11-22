# Xác định mức nguồn, thư viện và runtime cho ví dụ Java 15

## Mục tiêu

Sau bài này, bạn có thể chọn và ghi rõ **phiên bản ngôn ngữ dùng để biên dịch**, **thư viện mà mã phụ thuộc**, và **JVM dùng để chạy** một ví dụ; kiểm tra ba lựa chọn có tương thích hay không; tái hiện kết quả trên máy khác hoặc trong CI.

Java 15 là một bản phát hành **không LTS** và không còn là lựa chọn runtime được duy trì cho ứng dụng mới. Tuy vậy, quy tắc tương thích Java 15 vẫn hữu ích khi học những tính năng đã trở thành chính thức ở Java 15 hoặc khi kiểm tra một mã nguồn có cam kết chạy từ Java 15. Với môi trường học tập và vận hành hiện nay, hãy dùng bản JDK/JVM còn được nhà cung cấp hỗ trợ (chẳng hạn một bản LTS phù hợp như Java 21 hoặc 25), đồng thời đặt mức biên dịch một cách tường minh. **Không cần cài một JVM Java 15 đã hết hỗ trợ chỉ để học cú pháp Java 15.**

## 1. Tách bốn thông số thường bị nhầm lẫn

| Thông số | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Source level** | Trình biên dịch cho phép cú pháp/tính năng ngôn ngữ đến bản Java nào? | Java 15 |
| **API và thư viện** | Mã được phép gọi những API chuẩn nào và cần dependency bên ngoài nào? | API chuẩn có trong Java 15; không có dependency ngoài |
| **Bytecode target** | File `.class` được tạo cho mức JVM tối thiểu nào? | Class file version **59** tương ứng Java 15 |
| **Compiler JDK / Runtime JDK** | Dùng JDK nào để biên dịch, và dùng JVM nào để chạy? | Biên dịch bằng JDK 21; chạy bằng JVM 21 hoặc 25 |

**Source level không phải phiên bản JDK đang cài.** JDK 21 có thể biên dịch mã theo mức Java 15 khi `javac` của nó hỗ trợ tùy chọn đó. Ngược lại, chỉ hạ bytecode target chưa chứng minh mã không gọi API mới hơn target.

Đối với ví dụ Java 15 có yêu cầu tương thích thật với Java 15, cách chuẩn là:

```bash
javac --release 15 -encoding UTF-8 -d out Java15Example.java
```

`--release 15` đồng thời ràng buộc **cú pháp Java 15**, **API của nền tảng Java 15 có thể truy cập công khai** và **định dạng bytecode Java 15**. Khác với việc chỉ ghép `-source 15 -target 15`, nó ngăn mã vô tình sử dụng API chuẩn chỉ xuất hiện ở các JDK mới hơn. Không kết hợp `--release` với `-source` hoặc `-target` trong cùng lời gọi. Kiểm tra các mức hỗ trợ trên máy bằng `javac --help`, bởi compiler chỉ hỗ trợ một số bản phát hành trước đó.

## 2. Chọn mức nguồn theo mục tiêu của ví dụ

Trước hết xác định ví dụ đang **minh họa điều gì** và **cam kết chạy ở đâu**:

1. **Dạy tính năng chính thức của Java 15:** dùng `--release 15`, chỉ dùng cú pháp và API đã có trong Java 15. Ví dụ phù hợp: *text blocks* (chuỗi nhiều dòng) và `String.formatted(...)`; cả hai vẫn dùng được trong Java hiện đại.
2. **Dạy API/thư viện cần Java mới hơn:** chọn mức `--release` bằng hoặc cao hơn mức tối thiểu mà API đó yêu cầu. Không gắn nhãn “tương thích Java 15” nếu mã cần API mới hơn.
3. **Viết ứng dụng mới, không có yêu cầu Java 15:** chọn một bản Java LTS đang được duy trì và phù hợp môi trường triển khai, sau đó đặt mức nguồn, dependency và runtime theo quyết định đó. Không hạ về 15 chỉ vì ví dụ nằm trong một chương về Java 15.

Một chi tiết quan trọng: ở Java 15, **text blocks là tính năng chính thức**, còn một số tính năng khác của thời kỳ Java 15 vẫn ở trạng thái *preview*. Với ví dụ có thể chạy và được duy trì lâu dài, ưu tiên tính năng đã chính thức ở mức nguồn đã chọn; không đưa mã preview Java 15 vào ví dụ Java 15 thông thường. Một cú pháp chỉ được chuẩn hóa ở bản Java sau thì cần source level của bản đó trở lên.

## 3. Chọn thư viện: bắt đầu từ Java SE, chỉ thêm dependency khi thật cần

### Thư viện chuẩn

Nếu bài toán chỉ xử lý chuỗi, danh sách, file, thời gian, luồng hoặc các thao tác cơ bản, hãy kiểm tra API Java SE trước. Ví dụ dưới đây chỉ dùng `java.lang` và `java.util` trong module chuẩn `java.base` nên không cần tải JAR, không cần repository, không cần khai báo dependency:

- `List.of(...)` đã có trước Java 15.
- `String.formatted(...)` có từ Java 15.
- Text blocks là cú pháp chính thức từ Java 15.

Không suy ra API có mặt trong “JDK cài trên máy” thì API đó thuộc Java 15. Ví dụ, `Stream.toList()` xuất hiện sau Java 15: mã gọi phương thức này sẽ không biên dịch khi đặt `--release 15`, dù compiler đang chạy trên JDK mới.

### Thư viện bên ngoài

Chỉ thêm một dependency khi nó giải quyết yêu cầu mà API chuẩn chưa đáp ứng hợp lý. Với mỗi dependency (kể cả dependency bắc cầu), kiểm tra:

- **Java tối thiểu:** thư viện và các dependency của nó có yêu cầu JVM cao hơn target của ví dụ không? Bản mới nhất của một thư viện không mặc nhiên hỗ trợ Java 15.
- **Mục đích và phạm vi:** thư viện có thực sự cần cho ví dụ, hay chỉ khiến người học phải cấu hình thêm?
- **Khả năng duy trì:** ưu tiên phiên bản còn nhận bản sửa lỗi và phù hợp runtime được hỗ trợ; dùng lockfile/BOM hoặc cơ chế cố định phiên bản của dự án khi cần tái lập build.
- **Classpath/module path:** mã không modular có thể chạy qua `-cp`; nếu dự án có `module-info.java` thì phải khai báo và kiểm tra module path theo cấu trúc thực tế. Không chuyển sang module path chỉ vì đang dùng Java 15.
- **Runtime classpath:** thư viện cần lúc chạy cũng phải hiện diện lúc chạy; `--release` chỉ kiểm tra API của nền tảng Java, **không xác nhận phiên bản bytecode hay tính tương thích của mọi JAR bên ngoài**.

Khi dùng build tool, kiểm tra cây dependency bằng `./gradlew dependencies --configuration runtimeClasspath` hoặc `mvn dependency:tree` (trên Windows dùng `gradlew.bat` thay cho `./gradlew`). Nếu hứa hỗ trợ JVM cũ, cần chạy thử với đúng JVM mục tiêu và các JAR đã khóa phiên bản.

## 4. Ví dụ Java 15 hoàn chỉnh, không có dependency ngoài

Tạo file **`Java15Example.java`** với nội dung:

```java
import java.util.List;

public class Java15Example {
    public static void main(String[] args) {
        List<String> topics = List.of("source", "libraries", "runtime");
        String message = """
                Java 15: %d thanh phan
                Thu vien: java.base
                """.formatted(topics.size());

        System.out.print(message);
    }
}
```

Ở đây, `List.of` thuộc thư viện chuẩn, `"""..."""` là text block chính thức từ Java 15 và `formatted` điền số phần tử vào `%d`. Dòng đóng text block giữ quy tắc xử lý lề; nội dung in ra không có các khoảng trắng thụt lề của mã nguồn.

Dùng **JDK có `javac` hỗ trợ `--release 15`** (ví dụ JDK 21) rồi chạy từ thư mục chứa file:

```bash
javac -version
java -version
javac --release 15 -encoding UTF-8 -d out Java15Example.java
java -cp out Java15Example
```

**Kết quả chuẩn trên stdout:**

```text
Java 15: 3 thanh phan
Thu vien: java.base
```

Hai lệnh kiểm tra phiên bản ở đầu chỉ để biết bạn đang gọi compiler và runtime nào; chuỗi phiên bản hiển thị phụ thuộc môi trường. `javac` tạo `out/Java15Example.class`, còn `java -cp out Java15Example` chạy class theo tên lớp, **không** thêm `.class`. Không cần tham số `--enable-preview` vì ví dụ chỉ dùng tính năng chính thức.

Muốn xem target class file:

```bash
javap -verbose -classpath out Java15Example
```

Trong kết quả tìm `major version: 59`, tức bytecode nhắm Java 15. Chỉ số đó **không tự chứng minh** toàn bộ ứng dụng và thư viện ngoài sẽ chạy trên JVM Java 15: vẫn cần kiểm tra dependency, API và thử nghiệm runtime thực tế nếu dự án cam kết tương thích.

## 5. Chọn runtime phù hợp

Quy tắc nền tảng: **JVM phải hiểu bytecode của tất cả các lớp được tải**, bao gồm mã của bạn và thư viện. Class file Java 15 (major 59) không chạy trên JVM thấp hơn Java 15; JVM mới hơn thường chạy được bytecode cũ, nhưng còn phải xét các dependency và thay đổi hành vi/API khi triển khai.

| Trường hợp | Lựa chọn phù hợp |
| --- | --- |
| Học một cú pháp Java 15 đã chính thức | Biên dịch `--release 15` trên JDK được hỗ trợ; chạy trên một JVM LTS hiện đại mà build/test xác nhận |
| Ứng dụng mới chỉ triển khai trên Java 21 | Đặt `--release 21` và runtime Java 21; không cần ép target 15 |
| Ví dụ yêu cầu dependency chỉ hỗ trợ từ Java 17 | Chọn target/runtime từ Java 17 trở lên hoặc thay dependency; không tuyên bố hỗ trợ Java 15 |
| Phải giữ cam kết chạy trên Java 15 | Biên dịch `--release 15`, kiểm tra **tất cả** JAR và thử trên đúng JVM đó trong môi trường kiểm thử cô lập; đối với môi trường sản xuất, lên kế hoạch nâng cấp sang Java còn được hỗ trợ |

Phân biệt **JDK dùng để build** (có `javac`) với **runtime** dùng để chạy (có lệnh `java`). Trong ứng dụng được đóng gói hoặc container, phiên bản runtime còn phụ thuộc image và cách đóng gói, không nhất thiết trùng với JDK trên máy phát triển. Hãy chọn image/runtime còn nhận cập nhật bảo mật và cố định phiên bản theo chính sách dự án.

## 6. Cấu hình dự án để không phụ thuộc JDK của từng máy

Nếu ví dụ lớn hơn một file, dùng build tool và ghi rõ mức phát hành.

**Gradle, `build.gradle.kts` (ví dụ compiler JDK 21, mã tương thích API Java 15):**

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(15)
    options.encoding = "UTF-8"
}
```

Toolchain chọn **JDK biên dịch**; `options.release` mới giới hạn **ngôn ngữ/API/bytecode**. Việc Gradle chạy test bằng JDK 21 không thay thế phép thử trên JVM 15 nếu dự án có cam kết tương thích đến mức đó. Dùng phiên bản Gradle hỗ trợ JDK toolchain đã chọn và cấu hình nguồn cung toolchain khi môi trường chưa có JDK.

**Maven, phần `<properties>` trong `pom.xml`:**

```xml
<properties>
    <maven.compiler.release>15</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Cấu hình này yêu cầu Maven Compiler Plugin phù hợp truyền mức `--release 15` cho `javac`; nó **không tự chọn** JDK chạy Maven. Cố định phiên bản plugin trong cấu hình build của dự án, dùng JDK hỗ trợ release 15 và kiểm tra kết quả bằng lệnh build/test thực tế.

Chọn **một** công cụ build theo dự án; ví dụ một file trong mục 4 không bắt buộc cần Gradle hoặc Maven.

## 7. Kiểm tra lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `release version 15 not supported` hoặc `invalid target release: 15` | `javac` đang dùng không hỗ trợ target 15 | Xem `javac -version`, `javac --help`; chọn JDK compiler có hỗ trợ |
| `cannot find symbol` khi gọi API mới hơn Java 15 | API bị giới hạn bởi `--release 15` | Thay bằng API có trong Java 15 hoặc nâng target theo yêu cầu thực |
| `UnsupportedClassVersionError` | JVM chạy không hiểu bytecode của một lớp, có thể thuộc dependency | Đọc class file version trong lỗi; kiểm tra cả mã ứng dụng và JAR; chọn runtime tương thích |
| `NoClassDefFoundError` / `ClassNotFoundException` | Thiếu class/JAR trên runtime classpath hoặc module path | Kiểm tra cách đóng gói, dependency runtime, tên class/module |
| `NoSuchMethodError` | Thư viện được biên dịch với API khác phiên bản nạp lúc chạy | Kiểm tra dependency tree và phiên bản JAR thực sự được nạp, đồng bộ compile/runtime |
| Chạy được ở IDE nhưng lỗi trong CI/container | IDE, build và runtime chọn các JDK/classpath khác nhau | Ghi `javac -version`, `java -version`, cấu hình toolchain và dependency; kiểm tra lại trên môi trường triển khai |

Đừng xử lý các lỗi trên bằng cách bỏ `--release` hoặc tự ý bật preview. Trước tiên xác định chính xác compiler, target, dependency và JVM nào đang tham gia.

## 8. Checklist trước khi công bố một ví dụ

1. **Mục tiêu:** Ví dụ dạy tính năng chính thức nào? Mức Java tối thiểu là bao nhiêu?
2. **Source/API/bytecode:** `--release` đã đặt đúng chưa? Có API mới hơn target lọt vào không?
3. **Dependencies:** Có thể dùng hoàn toàn Java SE không? Nếu không, các JAR có tương thích và được duy trì không?
4. **Build:** Lưu phiên bản JDK compiler/toolchain, encoding và lệnh biên dịch; không phụ thuộc thiết lập ngầm của IDE.
5. **Runtime:** Chỉ rõ bản JVM dùng để chạy, kiểm tra classpath/module path; test trên môi trường thực tế.
6. **Kết quả:** Chạy lại từ thư mục sạch, xác nhận stdout, mã thoát và hành vi; không công bố kết quả phụ thuộc phiên bản như thể nó luôn cố định.

**Cấu hình tham chiếu cho bài này:** `source/API/bytecode = Java 15` qua `--release 15`; `dependencies = Java SE`; `compiler = JDK 21 có hỗ trợ release 15`; `runtime = JVM 21 được duy trì`. Bộ ba này thể hiện đúng kiến thức Java 15 còn sử dụng được hôm nay và tạo ví dụ dễ tái lập.

## Tài liệu chính thức để tra cứu

- Oracle, `javac` và ý nghĩa `--release`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- Oracle, Java SE 15 `String.formatted`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html
- Oracle, hướng dẫn text blocks (Java 15 trở lên): https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
- Gradle, Java Toolchains và `options.release`: https://docs.gradle.org/current/userguide/toolchains.html
- Apache Maven Compiler Plugin, cấu hình compiler release: https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html
