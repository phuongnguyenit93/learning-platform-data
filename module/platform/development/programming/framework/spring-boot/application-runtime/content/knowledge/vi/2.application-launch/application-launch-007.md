# Ảnh hưởng của classpath, thư mục làm việc và ResourceLoader khi khởi chạy Spring Boot

## 1. Vì sao cùng một ứng dụng lại tìm thấy tài nguyên ở máy này nhưng không thấy ở máy khác?

Một ứng dụng Spring Boot có thể đọc thành công tệp khi chạy trong IDE, nhưng báo `FileNotFoundException` khi chạy bằng `java -jar` hoặc trong container. Nguyên nhân thường không nằm ở nội dung tệp mà ở **cách xác định vị trí của tệp**. Có ba khái niệm cần tách rõ:

1. **Classpath lúc chạy (runtime classpath)** là tập hợp các thư mục chứa lớp đã biên dịch, tài nguyên và thư viện mà bộ nạp lớp Java có thể tìm kiếm. Tài nguyên đóng gói cùng ứng dụng thường được tìm theo classpath.
2. **Thư mục làm việc (working directory)** là thư mục hiện tại của **tiến trình Java** khi khởi chạy. Đường dẫn tệp tương đối như `config/message.txt` thường được diễn giải từ đây, không phải từ thư mục chứa JAR.
3. **`ResourceLoader` của Spring** là cơ chế biến chuỗi mô tả vị trí thành đối tượng `Resource`. Tiền tố như `classpath:` hoặc `file:` quyết định nơi tra cứu; nếu không có tiền tố thì kết quả còn phụ thuộc triển khai `ResourceLoader` và ngữ cảnh ứng dụng.

Hãy nhớ: **đường dẫn trong mã nguồn, đường dẫn tài nguyên trên classpath, đường dẫn tệp của hệ điều hành và vị trí của JAR là những thứ khác nhau**.

| Cách truy cập | Tìm ở đâu? | Có phụ thuộc working directory? |
| --- | --- | --- |
| `new ClassPathResource("demo/message.txt")` | Runtime classpath | Thường không, nếu classpath đã được thiết lập đúng |
| `resourceLoader.getResource("classpath:demo/message.txt")` | Runtime classpath | Thường không, với cùng classpath |
| `Path.of("config/message.txt")` | Hệ thống tệp, tương đối với thư mục làm việc | Có |
| `resourceLoader.getResource("file:./config/message.txt")` | Hệ thống tệp, tương đối với thư mục làm việc | Có |
| `resourceLoader.getResource("file:/opt/demo/config/message.txt")` | Đường dẫn tuyệt đối trên hệ thống Unix/Linux | Không |
| `resourceLoader.getResource("demo/message.txt")` | Vị trí tương đối theo loại `ResourceLoader` | Không nên mặc định là classpath hay working directory |

Dấu `./` chỉ thư mục hiện tại theo ngữ cảnh giải quyết đường dẫn. Nó không có nghĩa là “cạnh tệp `.jar`”.

## 2. Classpath hình thành thế nào khi build và chạy?

Giả sử dự án có cấu trúc:

```text
src/
  main/
    java/
      demo/runtime/RuntimePathsApplication.java
    resources/
      demo/message.txt
      application.properties
config/
  message.txt
```

Ở đây:

- `src/main/java` là mã nguồn Java. Khi build, nó được biên dịch thành các tệp `.class`.
- `src/main/resources/demo/message.txt` là tài nguyên ứng dụng. Gradle hoặc Maven sao chép nó vào đầu ra tài nguyên, để có thể tra cứu bằng tên classpath `demo/message.txt`.
- `config/message.txt` nằm **ngoài** `src/main/resources`. Nó là tệp của hệ thống tệp; chỉ được tìm thấy nếu đường dẫn và working directory phù hợp, hoặc quá trình đóng gói được cấu hình riêng.
- `src/test/resources` thường chỉ được thêm vào classpath khi chạy kiểm thử. Không được dựa vào tệp chỉ có trong `src/test/resources` để ứng dụng đóng gói chạy ngoài môi trường kiểm thử.

Với executable Spring Boot JAR được tạo bởi tác vụ `bootJar`, bố cục thường có dạng:

```text
demo.jar
  BOOT-INF/
    classes/
      demo/runtime/RuntimePathsApplication.class
      demo/message.txt
      application.properties
    lib/
      ...cac-thu-vien-phu-thuoc.jar
```

Bộ nạp lớp của Spring Boot có thể đọc tài nguyên dưới `BOOT-INF/classes` và thư viện lồng bên trong JAR. Vì vậy `classpath:demo/message.txt` vẫn hợp lệ khi chạy JAR, dù không có thư mục thật tên `src/main/resources` trên máy triển khai.

Tuy nhiên classpath **được quyết định lúc khởi chạy**. Nếu dùng `java -cp` với các mục classpath tương đối, việc đổi working directory có thể làm Java tìm nhầm thư mục hoặc thư viện ngay từ đầu. Với executable Boot JAR được gọi bằng đường dẫn hợp lệ qua `java -jar`, Spring Boot tự xây dựng classpath từ cấu trúc JAR. Phân biệt **ảnh hưởng lên cách tạo classpath** với **cách tìm một resource sau khi classpath đã sẵn sàng**.

Một lỗi phổ biến là:

```java
// Cách này chỉ trỏ tới thư mục source trong một số môi trường phát triển:
Path sourcePath = Path.of("src/main/resources/demo/message.txt");
```

Đường dẫn trên không phải tên classpath. Khi chạy JAR đã đóng gói ở một thư mục khác, cây `src/main/resources` thường không tồn tại. Với tài nguyên nội bộ, hãy dùng `classpath:demo/message.txt` và đọc qua luồng dữ liệu.

## 3. Working directory khác thư mục chứa JAR

Ví dụ cùng một tệp `/opt/demo/app.jar` nhưng có hai cách gọi:

```bash
cd /opt/demo
java -jar /opt/demo/app.jar
```

Ở lần này, `file:./config/message.txt` tương ứng với `/opt/demo/config/message.txt`.

```bash
cd /tmp
java -jar /opt/demo/app.jar
```

Ở lần này, cùng chuỗi `file:./config/message.txt` lại tương ứng với `/tmp/config/message.txt`. Vị trí JAR không hề đổi.

Trong Java, có thể quan sát thư mục làm việc bằng:

```java
System.out.println(Path.of("").toAbsolutePath().normalize());
System.out.println(System.getProperty("user.dir"));
```

Giá trị hiển thị phụ thuộc cách tiến trình được khởi chạy: IDE run configuration, terminal, Gradle `bootRun`, cấu hình dịch vụ hệ điều hành hoặc `WORKDIR` trong Docker. **Đừng giả định** rằng mọi công cụ đều đặt working directory bằng thư mục dự án. Hãy kiểm tra đầu ra thực tế khi chẩn đoán.

Nếu muốn đọc tệp nằm cạnh JAR, cần **xác định rõ thư mục chứa JAR**, chẳng hạn qua cơ chế `ApplicationHome` của Spring Boot hoặc một đường dẫn cấu hình riêng. Không dùng `./` để ngầm suy ra vị trí JAR. Giải pháp vận hành dễ kiểm soát hơn thường là truyền đường dẫn tệp tuyệt đối qua cấu hình triển khai.

## 4. ResourceLoader giải quyết chuỗi vị trí như thế nào?

Spring cung cấp giao diện `Resource` làm lớp trừu tượng cho các nguồn dữ liệu khác nhau và giao diện `ResourceLoader` để tra cứu nguồn dữ liệu theo vị trí:

```java
Resource internal = resourceLoader.getResource("classpath:demo/message.txt");
Resource external = resourceLoader.getResource("file:./config/message.txt");
```

Các dạng quan trọng:

- **`classpath:`**: yêu cầu tài nguyên từ classpath. Cách này phù hợp với mẫu, dữ liệu tĩnh, tài nguyên đọc-only được đóng gói trong ứng dụng.
- **`file:`**: yêu cầu tài nguyên từ hệ thống tệp. Đường dẫn có thể tương đối với working directory hoặc tuyệt đối; phù hợp với dữ liệu do bên triển khai cung cấp, cấu hình ngoài ứng dụng và tệp có vòng đời độc lập với bản build.
- **`https:` / `http:`**: tùy cơ chế tải tài nguyên, có thể tạo tài nguyên URL và phát sinh kết nối mạng khi đọc. Không lấy URL tùy ý từ đầu vào không tin cậy.
- **Không có tiền tố**: hành vi phụ thuộc vào `ResourceLoader` cụ thể. Chẳng hạn `DefaultResourceLoader` có cách giải quyết vị trí tương đối khác một `WebApplicationContext` có gốc servlet context. Hãy đặt tiền tố để thể hiện rõ ý định.

Một số loại triển khai thường gặp là `ClassPathResource`, `FileSystemResource`, `UrlResource` và `ServletContextResource`. Khi code chỉ cần đọc, nên nhận `Resource` thay vì phụ thuộc vào loại triển khai cụ thể.

`Resource` cung cấp các thao tác như `exists()`, `isReadable()`, `getInputStream()`, `getURL()` và `getDescription()`. **`getFile()` không phải lúc nào cũng dùng được**: tài nguyên nằm trong JAR không bắt buộc tồn tại như một tệp riêng trên hệ thống tệp, nên `ClassPathResource#getFile()` có thể hoạt động khi chạy từ thư mục build nhưng thất bại sau khi đóng JAR.

```java
// Ưu tiên cách đọc dùng được cả khi tài nguyên nằm trong JAR:
try (InputStream input = resource.getInputStream()) {
    byte[] bytes = input.readAllBytes();
    // Xử lý bytes theo đúng định dạng của tài nguyên.
}
```

Đừng dùng `resource.getFile().toPath()` chỉ để đọc tệp classpath. Mỗi lần đọc một luồng mới và đóng bằng `try-with-resources`. Tài nguyên đóng gói trong JAR cũng không phải chỗ thích hợp để ghi dữ liệu thay đổi khi ứng dụng chạy.

Nếu cần tìm **nhiều** tài nguyên theo pattern xuyên các JAR, dùng `ResourcePatternResolver#getResources("classpath*:...")`; `ResourceLoader#getResource(...)` chỉ trả về một `Resource` theo một vị trí. Khi có các tệp trùng tên ở nhiều mục classpath, kết quả chọn “bản đầu tiên” có thể phụ thuộc thứ tự classpath; nên tránh đặt trùng tên nếu cần tính dự đoán được.

## 5. Ví dụ Spring Boot 3.x có thể chạy được

Tạo một dự án Spring Boot 3.x dùng Java 17 trở lên với dependency `spring-boot-starter`. Đặt tệp `src/main/java/demo/runtime/RuntimePathsApplication.java`:

```java
package demo.runtime;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@SpringBootApplication
public class RuntimePathsApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimePathsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectResources(ResourceLoader loader) {
        return args -> {
            System.out.println("cwd=" + Path.of("").toAbsolutePath().normalize());

            printResource("classpath",
                    loader.getResource("classpath:demo/message.txt"));
            printResource("file",
                    loader.getResource("file:./config/message.txt"));
        };
    }

    private static void printResource(String label, Resource resource)
            throws IOException {
        System.out.println(label + " exists=" + resource.exists());
        if (!resource.exists() || !resource.isReadable()) {
            return;
        }

        try (InputStream input = resource.getInputStream()) {
            String content = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            System.out.println(label + " content=" + content);
        }
    }
}
```

Tạo `src/main/resources/demo/message.txt` với nội dung:

```text
Xin chào từ classpath
```

Tạo thêm tệp `config/message.txt` tại **gốc dự án** với nội dung:

```text
Xin chào từ thư mục làm việc
```

Khi chạy từ gốc dự án, nếu thư mục làm việc thực sự là gốc dự án và tệp ngoài tồn tại, phần kết quả liên quan sẽ giống:

```text
cwd=<duong-dan-goc-du-an>
classpath exists=true
classpath content=Xin chào từ classpath
file exists=true
file content=Xin chào từ thư mục làm việc
```

Dòng `cwd=...` là minh họa; đường dẫn thực tế được chương trình in ra. Ngoài các dòng này, Spring Boot còn có log khởi động.

Đóng gói bằng `./gradlew bootJar` trong dự án Gradle có Spring Boot plugin, sau đó chạy JAR tạo ra từ `build/libs/`. Nếu đứng ở thư mục không có `config/message.txt` nhưng cung cấp đúng đường dẫn đến JAR, kết quả phần chính sẽ là:

```text
classpath exists=true
classpath content=Xin chào từ classpath
file exists=false
```

Ví dụ này chứng minh **cùng một ứng dụng có thể tìm thấy tài nguyên trong JAR nhưng không tìm thấy tệp ngoài khi working directory đổi**. `file exists=false` chỉ đúng khi tệp tương ứng thực sự không tồn tại trong working directory mới.

Để biết tài nguyên nào đang được giải quyết, có thể bổ sung `resource.getDescription()` vào log chẩn đoán. Không in nguyên văn nội dung tệp nhạy cảm, mật khẩu hay token trong ứng dụng thực tế.

## 6. Chọn đúng cách truy cập theo mục đích

**Tài nguyên nội bộ, gắn với bản phát hành:** ảnh mẫu, tệp mẫu, cấu hình mặc định không chứa bí mật, tài nguyên phục vụ mã nguồn nên nằm trong `src/main/resources` và được đọc qua `classpath:`. Khi phát hành bản mới, nội dung thay đổi theo artifact.

**Tệp do vận hành cung cấp hoặc có thể thay đổi sau triển khai:** tệp chứng chỉ, dữ liệu được mount từ volume, đường dẫn lưu báo cáo, tài nguyên tải về nên nằm ngoài JAR. Khai báo vị trí qua biến môi trường, tham số khởi động hoặc cấu hình ứng dụng; làm rõ liệu đó là đường dẫn tuyệt đối hay tương đối. Kiểm soát quyền truy cập của tiến trình.

**Đường dẫn trong mã Java:** với thao tác tệp hệ điều hành dùng `Path` / `Files`, ví dụ:

```java
Path configDir = Path.of("/opt/demo/config");
Path settingsFile = configDir.resolve("settings.json");
String settings = Files.readString(settingsFile, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa thao tác filesystem, giả định tệp tồn tại; không phải ví dụ đọc classpath. Nếu cấu hình truyền từ bên ngoài dưới dạng chuỗi có tiền tố như `classpath:`, `file:` hoặc URL, `ResourceLoader` giúp thống nhất cách đọc. Nếu ứng dụng cần **ghi** dữ liệu, dùng API hệ thống tệp và một đường dẫn ghi được; đừng ghi vào tài nguyên classpath.

**Tệp tương đối không có tiền tố:** tránh viết `loader.getResource("config/message.txt")` rồi suy luận nó tương đương `file:./config/message.txt`. Hãy ghi rõ `file:` khi cần filesystem, hoặc `classpath:` khi cần tài nguyên đã đóng gói.

## 7. Liên hệ với application.properties và cấu hình khởi động

Spring Boot có **cơ chế Config Data** riêng để nạp `application.properties` / `application.yml`. Cơ chế này có nhiều vị trí tìm kiếm mặc định, gồm các vị trí trên classpath và các vị trí bên ngoài tương đối với working directory, chẳng hạn `./` và `./config/`. Nguồn cấu hình bên ngoài phù hợp có thể ghi đè khóa cấu hình cùng tên ở nguồn bên trong JAR theo thứ tự ưu tiên của Spring Boot.

Do đó khi chuyển từ IDE sang JAR hoặc container, ứng dụng có thể **thay đổi giá trị cấu hình** dù tệp `application.properties` đóng gói vẫn giữ nguyên: working directory mới có thể khiến Spring Boot tìm thấy hoặc không thấy cấu hình ngoài. Đây là quy tắc nạp cấu hình của Spring Boot, **không đồng nghĩa** với việc mỗi lần gọi `ResourceLoader#getResource(...)` đều áp dụng chuỗi ưu tiên Config Data.

Ví dụ muốn cung cấp thêm một thư mục cấu hình ngoài cố định khi khởi động:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/demo/
```

Thư mục là ví dụ trên Unix/Linux. `additional-location` bổ sung vị trí tìm kiếm; `spring.config.location` có thể thay thế tập vị trí mặc định, nên không dùng hai thuộc tính này như thể chúng tương đương. Tiền tố `optional:` cho phép vị trí không tồn tại mà không khiến quá trình nạp cấu hình thất bại chỉ vì vị trí đó bị thiếu. Một số thuộc tính cấu hình vị trí cần có từ giai đoạn khởi động sớm (chẳng hạn tham số dòng lệnh hoặc biến môi trường).

Sự khác nhau cần nhớ:

- `classpath:application.properties`: mô tả tài nguyên trên classpath.
- `file:./config/application.properties`: mô tả một tệp tương đối với working directory.
- Việc **Spring Boot chọn và hợp nhất nguồn cấu hình** là trách nhiệm của Config Data, có thứ tự ưu tiên riêng.
- Việc **mã ứng dụng chủ động đọc tài nguyên** là trách nhiệm của đoạn mã sử dụng `Resource` / `ResourceLoader`.

## 8. Các lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| Chạy IDE được, chạy JAR báo không thấy `src/main/resources/...` | Đã dùng đường dẫn mã nguồn như đường dẫn filesystem khi chạy | Đưa tài nguyên vào `src/main/resources`, truy cập bằng `classpath:...` |
| `ClassPathResource#getFile()` thất bại trong JAR | Tài nguyên là entry trong JAR, không phải một tệp rời | Đọc bằng `getInputStream()` thay vì buộc chuyển sang `File` |
| Chạy cùng JAR ở thư mục khác cho kết quả khác | `file:./...`, `Path.of("...")` hoặc cấu hình ngoài phụ thuộc working directory | Kiểm tra `Path.of("").toAbsolutePath()`, truyền đường dẫn tuyệt đối hoặc cấu hình working directory rõ ràng |
| Docker chạy thiếu tệp mà máy phát triển có | Tệp ngoài chưa được copy/mount; `WORKDIR` khác | Kiểm tra `WORKDIR`, volume mount, vị trí và quyền đọc tệp trong container |
| Tên tài nguyên đúng trên Windows nhưng lỗi trên Linux | Khác biệt chữ hoa/thường của tên tệp hoặc đường dẫn | Đối chiếu chính xác tên và chữ hoa/thường trong artifact |
| Kiểm thử có tài nguyên nhưng bản phát hành thiếu | Tài nguyên chỉ nằm trong `src/test/resources` | Chuyển đúng tài nguyên phát hành vào `src/main/resources` |
| Cấu hình dường như bị thay đổi sau triển khai | Có `application.properties` bên ngoài với ưu tiên cao hơn hoặc vị trí tra cứu đổi theo cwd | Kiểm tra các nguồn cấu hình đang hoạt động, tham số khởi động và vị trí Config Data |
| Dùng chuỗi không tiền tố mà kết quả bất ngờ | Loại `ResourceLoader` quyết định ý nghĩa của đường dẫn tương đối | Ghi rõ `classpath:` hoặc `file:` |

Quy trình chẩn đoán có thứ tự:

1. Xác định tài nguyên đang được kỳ vọng là **classpath** hay **filesystem**. Ghi lại chuỗi location đầy đủ, gồm tiền tố.
2. In working directory thực của tiến trình và `resource.getDescription()`; kiểm tra `exists()` / `isReadable()`. Nếu lỗi khi đọc, ghi exception đúng từ `getInputStream()`.
3. Nếu là tài nguyên classpath, kiểm tra artifact: có thể dùng `jar tf build/libs/ten-ung-dung.jar` để xem tài nguyên có nằm dưới `BOOT-INF/classes/` hay không; kiểm tra cách dựng runtime classpath nếu chạy bằng `-cp`.
4. Nếu là tệp ngoài, kiểm tra đường dẫn tuyệt đối, quyền đọc, mount volume, working directory và cấu hình khởi chạy. Không suy ra working directory từ vị trí JAR.
5. Nếu lỗi liên quan `application.properties`, kiểm tra thứ tự nguồn Config Data và các tham số như `spring.config.location` / `spring.config.additional-location` trước khi sửa mã đọc resource.

Không nên chữa lỗi đường dẫn bằng cách thay đổi `System.setProperty("user.dir", ...)` trong lúc ứng dụng đang chạy. Nhiều API và thành phần đã giải quyết đường dẫn theo ngữ cảnh trước đó; cấu hình working directory của tiến trình hoặc sử dụng đường dẫn tuyệt đối rõ ràng giúp hành vi nhất quán hơn.

## 9. Thực hành kiểm chứng trước khi triển khai

Hãy tự thực hiện ba phép thử nhỏ với ví dụ ở mục 5:

1. **Giữ nguyên artifact, đổi working directory:** chạy JAR từ hai thư mục khác nhau. So sánh `cwd` và kết quả của hai resource. Giải thích vì sao classpath vẫn đọc được trong khi `file:./...` thay đổi.
2. **Giữ working directory, bỏ tệp ngoài:** đổi tên `config/message.txt` và chạy lại. `classpath` vẫn đọc được; resource `file` phải báo không tồn tại. Phục hồi tệp sau thử nghiệm.
3. **Kiểm tra cấu trúc JAR:** xem `demo/message.txt` có được đóng gói dưới `BOOT-INF/classes/demo/message.txt` hay không. Nếu thiếu, sửa cấu hình build hoặc vị trí nguồn tài nguyên, không sửa tên resource bằng một đường dẫn `src/main/resources` ở môi trường triển khai.

Khi viết test, tạo tệp ngoài trong thư mục tạm biệt lập (ví dụ JUnit `@TempDir`), rồi truyền đường dẫn đã biết vào code cần kiểm tra. Điều này tránh việc test tình cờ chỉ đúng vì IDE và Gradle dùng cùng một working directory.

## 10. Những nguyên tắc nên giữ trong codebase

- Chọn nơi lưu tài nguyên theo vòng đời: **đóng gói cố định** thì classpath; **thay đổi theo môi trường** thì filesystem hoặc kho lưu trữ ngoài.
- Với Spring `ResourceLoader`, **viết tiền tố rõ ràng** để biết nơi tra cứu và không phụ thuộc ngầm vào context.
- Với tài nguyên trong JAR, **đọc qua InputStream**; chỉ dùng `File`/`Path` khi có tệp thực trên filesystem.
- Khi dùng đường dẫn tương đối, xác định và kiểm thử **working directory** của từng cách khởi động (IDE, Gradle, JAR, container, service).
- Với cấu hình Spring Boot, phân biệt **quá trình nạp Config Data** với thao tác **đọc Resource thủ công**, và kiểm soát các nguồn cấu hình ngoài có thể ghi đè cấu hình trong JAR.

Hiểu đúng ba khái niệm này sẽ giúp việc khởi chạy Spring Boot có thể lặp lại giữa môi trường phát triển và triển khai, đồng thời giúp xác định nhanh lỗi do đóng gói, classpath, working directory hay cách giải quyết resource. 
