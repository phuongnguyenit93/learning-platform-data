# Đọc thông tin commit từ git.properties và lựa chọn chế độ công bố

## 1. Từ bản mã nguồn đến thông tin của ứng dụng đang chạy

Khi hai máy cùng chạy phiên bản ứng dụng `1.0.0` nhưng chỉ một máy có bản sửa lỗi mới, tên phiên bản chưa đủ để xác định mã nguồn đã triển khai. Mã commit giúp đối chiếu bản chạy với thay đổi trong Git; thời điểm commit và nhánh bổ sung ngữ cảnh khi điều tra sự cố.

Trong Spring Boot Actuator, `git.properties` là tài nguyên chứa thông tin Git được chụp tại lúc dựng ứng dụng. Luồng thông thường là:

```text
Kho Git tại lúc dựng
    -> công cụ dựng sinh git.properties
    -> tài nguyên được đóng gói vào ứng dụng
    -> Spring Boot tạo GitProperties
    -> GitInfoContributor chọn thông tin cần công bố
    -> /actuator/info trả về phần git
```

Đây là thông tin của bản dựng, không phải truy vấn trực tiếp kho Git mỗi khi có HTTP request. Một container chỉ mang JAR vẫn có thể công bố commit dù không có thư mục `.git`. Ngược lại, có `.git` cạnh tiến trình không tự làm xuất hiện phần `git` nếu ứng dụng không nạp được tài nguyên tương ứng.

Mục tiêu của bài là đọc đúng thông tin đã đóng gói, phân biệt dữ liệu có sẵn với dữ liệu được công bố, và chọn chế độ phù hợp cho người sử dụng endpoint. Các ví dụ dùng Spring Boot 3.3.x và Java 17 trở lên; API minh họa cũng dùng được với Java 21.

## 2. Ba quyết định cần tách riêng

| Quyết định | Thành phần chịu trách nhiệm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Thu thập | Công cụ dựng hoặc quy trình CI | Những thuộc tính Git nào được đưa vào bản dựng? |
| Chọn nội dung | `GitInfoContributor` | Dùng `simple`, `full`, hay tắt contributor? |
| Cho phép truy cập | Cấu hình endpoint và lớp bảo vệ HTTP | Ai được gọi `/actuator/info`? |

`management.info.git.mode=full` không sinh `git.properties`, không tự mở endpoint qua HTTP và không cấp quyền truy cập. Tương tự, đưa `info` vào danh sách endpoint được mở không bảo đảm tài nguyên Git tồn tại.

Trong cấu hình tự động của Spring Boot 3.3, contributor Git cần một `GitProperties` phù hợp; nếu ứng dụng tự khai báo `GitInfoContributor`, cấu hình tự động sẽ nhường lại. Khi đó phải kiểm tra constructor và logic của bean tự tạo, thay vì mặc định rằng thuộc tính `management.info.git.mode` vẫn điều khiển nó. [Mã cấu hình tự động contributor của Spring Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.java).

## 3. Tệp được nạp từ đâu, và tên khóa thay đổi thế nào?

Vị trí mặc định là `classpath:git.properties`. Trong dự án Java thông thường, tài nguyên đặt tại `src/main/resources/git.properties` sẽ được đưa tới gốc classpath. Với executable JAR của Spring Boot, vị trí tương ứng là `BOOT-INF/classes/git.properties`.

Có thể đổi vị trí bằng cấu hình sau, chẳng hạn khi quy trình dựng sử dụng tên tài nguyên riêng:

```properties
spring.info.git.location=classpath:metadata/git.properties
```

Khi nạp, cấu hình tự động chỉ lấy các khóa bắt đầu bằng `git.` rồi bỏ tiền tố này để tạo `GitProperties`. Vì thế:

| Trong tệp | Khi đọc từ `GitProperties` | Đường dẫn thường thấy trong JSON |
| --- | --- | --- |
| `git.branch` | `getBranch()` hoặc `get("branch")` | `git.branch` |
| `git.commit.id` | `getCommitId()` | Tùy chế độ, xem phần 5 |
| `git.commit.id.abbrev` | `getShortCommitId()` | `git.commit.id` ở simple |
| `git.commit.time` | `getCommitTime()` | `git.commit.time` |
| `git.commit.user.email` | `get("commit.user.email")` | Có thể xuất hiện ở full |

Gọi `gitProperties.get("git.branch")` là dùng sai tên khóa sau khi nạp. Việc có một dòng `git.commit.id=...` trong `application.properties` cũng không thay thế tài nguyên `git.properties`: đó là hai đường nạp khác nhau. [Cơ chế nạp và loại bỏ tiền tố trong Spring Boot](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/info/ProjectInfoAutoConfiguration.java).

Nếu tự gọi `new GitProperties(properties)` trong Java, đối tượng `Properties` đầu vào phải chứa các khóa đã bỏ `git.`. Constructor không thực hiện bước chọn tiền tố thay cho cấu hình tự động.

## 4. Bộ dữ liệu cố định để quan sát cơ chế

Để kết quả không phụ thuộc commit hiện tại của người học, dùng tệp sau làm dữ liệu thực hành:

```properties
git.branch=main
git.commit.id=0123456789abcdef0123456789abcdef01234567
git.commit.id.abbrev=0123456789
git.commit.time=2024-06-01T09:15:00+0000
git.commit.user.email=demo@example.invalid
git.remote.origin.url=https://example.invalid/team/demo.git
git.dirty=false
```

Mã commit và địa chỉ trong ví dụ là dữ liệu giả để thử nghiệm. Không đưa tệp cố định này vào bản phát hành thực tế: khi mã nguồn đổi, một tệp chép tay có thể tiếp tục báo commit cũ.

Ý nghĩa của các thuộc tính:

- `branch`: nhãn nhánh do công cụ dựng thu thập. Nhánh có thể thay đổi hoặc không mang tên quen thuộc trong môi trường CI.
- `commit.id`: mã commit đầy đủ của bản nguồn được ghi nhận.
- `commit.id.abbrev`: dạng rút gọn do công cụ sinh dữ liệu cung cấp; ví dụ cố ý dùng 10 ký tự.
- `commit.time`: thời điểm commit, không phải thời điểm JVM khởi động hoặc thời điểm triển khai.
- `commit.user.email`, `remote.origin.url`: chi tiết có ích cho điều tra nội bộ nhưng cần cân nhắc trước khi công bố.
- `dirty`: thông tin về thay đổi chưa commit tại lúc thu thập, nếu công cụ dựng tạo trường này.

Một mã commit đúng không chứng minh bản dựng không chứa thay đổi chưa commit. Khi cần truy nguyên bản phát hành, phải kết hợp mã commit, trạng thái kho lúc dựng và bằng chứng từ quy trình CI; phần `info` chỉ phản ánh dữ liệu mà bản dựng đã mang theo.

## 5. Simple, full và tắt contributor

### 5.1. Simple: chỉ chọn nhóm thuộc tính cốt lõi

`simple` là chế độ mặc định của `GitInfoContributor`. Nó chọn nhánh, mã commit rút gọn và thời điểm commit nếu có dữ liệu tương ứng; các trường như email, URL kho hay `dirty` không được chọn chỉ vì chúng tồn tại trong tệp. [Cơ chế chọn dữ liệu của GitInfoContributor](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/GitInfoContributor.java).

Cấu hình tường minh:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: [health, info]
  info:
    git:
      enabled: true
      mode: simple
```

Với bộ dữ liệu phần 4 và cấu hình JSON mặc định của Spring Boot, phần Git có nội dung sau; thứ tự các khóa không phải hợp đồng:

```json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": "0123456789",
      "time": "2024-06-01T09:15:00Z"
    }
  }
}
```

`getShortCommitId()` ưu tiên `commit.id.abbrev`. Nếu thiếu khóa này, nó lấy tối đa 7 ký tự đầu của `commit.id`; nếu không có cả hai thì không có mã commit để công bố. Vì vậy không được giả định `simple` luôn trả đúng 7 ký tự. `getCommitTime()` cung cấp `Instant` khi phân tích được thời gian; mã cần xử lý khả năng thiếu hoặc không phân tích được dữ liệu, thay vì mặc định luôn có giá trị. [API và xử lý dữ liệu trong GitProperties](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/info/GitProperties.java).

### 5.2. Full: công bố dữ liệu đã nạp, có cấu trúc lồng nhau

Chỉ thay chế độ:

```properties
management.info.git.mode=full
```

Với cùng bộ dữ liệu, phần Git có dạng:

```json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": {
        "abbrev": "0123456789",
        "full": "0123456789abcdef0123456789abcdef01234567"
      },
      "time": "2024-06-01T09:15:00Z",
      "user": {
        "email": "demo@example.invalid"
      }
    },
    "remote": {
      "origin": {
        "url": "https://example.invalid/team/demo.git"
      }
    },
    "dirty": "false"
  }
}
```

Ở đây `git.commit.id` là một đối tượng, trong khi ở `simple` nó là chuỗi. Với bộ dữ liệu này, mã đầy đủ nằm ở `git.commit.id.full`. Bộ đọc JSON phải biết hợp đồng đang dùng; đổi sang `full` có thể làm hỏng chương trình đang đọc `git.commit.id` như chuỗi.

`full` đưa tập thuộc tính đã nạp vào bước chuyển đổi cấu trúc; nó không đọc thêm lịch sử Git hay tự điền trường bị thiếu. Các giá trị `.properties` như `dirty=false` vẫn có thể là chuỗi JSON `"false"`, không phải boolean `false`. Ngoài ra, đây là biểu diễn có cấu trúc, không phải bản sao nguyên văn từng byte của tệp: khóa có dấu chấm được nhóm lại, và thời gian hợp lệ được xử lý thành kiểu thời gian. [Cơ chế chuyển thuộc tính thành dữ liệu contributor](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoPropertiesInfoContributor.java).

### 5.3. Không công bố Git qua contributor tự động

```properties
management.info.git.enabled=false
```

Thiết lập này tắt contributor Git tự động. Nó không xóa tài nguyên khỏi JAR và không cấm mã Java khác đọc `GitProperties` hoặc một contributor tự viết công bố lại dữ liệu đó. Endpoint `info` cũng có thể tiếp tục trả các nhóm dữ liệu khác.

Hai chế độ được hỗ trợ là `simple` và `full`; không dùng `mode=none` để thay cho `enabled=false`. Cũng không nhầm `management.info.git.enabled` với `management.endpoint.info.enabled`: thuộc tính thứ hai điều khiển cả endpoint. [Cấu hình Application Information của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info).

## 6. Thực hành HTTP trong một ứng dụng Spring Boot

Giả sử đã có dự án Spring Boot 3.3.x dùng Java 17+ và Gradle Wrapper. Bổ sung hai dependency vào khối `dependencies` hiện có:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Các dòng trên là phần cấu hình bổ sung, không phải toàn bộ `build.gradle`; dự án phải có sẵn quản lý phiên bản dependency của Spring Boot. Nếu ứng dụng đã có starter web thì không khai báo lại.

Một lớp khởi động tối thiểu tại `src/main/java/example/gitinfo/GitInfoApplication.java`:

```java
package example.gitinfo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GitInfoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GitInfoApplication.class, args);
    }
}
```

Đặt tệp phần 4 vào `src/main/resources/git.properties`, rồi dùng cấu hình `simple` phần 5.1 trong `application.yml`. Riêng phòng thực hành chạy tại máy cá nhân, bổ sung:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Chạy ứng dụng:

```bash
./gradlew bootRun
```

Trên Windows PowerShell, lệnh tương ứng là `.\gradlew.bat bootRun`. Ở terminal khác:

```bash
curl -i http://127.0.0.1:8080/actuator/info
```

Với ứng dụng tối thiểu không cài Spring Security và không có contributor khác, mong đợi HTTP 200 cùng JSON `simple` phần 5.1. Trên Windows có thể dùng `curl.exe` để tránh khác biệt alias. Nếu dự án có Spring Security, phải dùng thông tin xác thực và quy tắc truy cập của dự án; không suy ra endpoint bị lỗi chỉ từ HTTP 401/403.

Dừng tiến trình, thay chế độ thành `full`, khởi động lại và gọi lại cùng URL. Kết quả cần khớp nội dung phần 5.2. Việc sửa tệp cấu hình không bảo đảm tiến trình đang chạy tự thay contributor; trong bài này mỗi lần đổi chế độ đều khởi động lại.

Sau đó thử `enabled=false`: khi không có contributor khác, endpoint đang mở trả `{}`, không phải tự chuyển sang HTTP 404.

Trong Spring Boot 3.3, chỉ `health` được mở qua HTTP theo mặc định. `include: [health, info]` là lựa chọn mở endpoint, còn xác thực và phân quyền do lớp bảo vệ của ứng dụng quyết định. [Quy tắc exposure và bảo vệ endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 7. Chạy Java để quan sát dữ liệu trước và sau khi chọn chế độ

Ví dụ sau kiểm tra trực tiếp `GitProperties` và `GitInfoContributor`, không khởi động web server. Việc tự nạp và bỏ tiền tố chỉ nhằm làm rõ cơ chế; trong ứng dụng thông thường hãy dùng bean Spring Boot tạo sẵn.

Tạo `src/main/java/example/gitinfo/GitModesDemo.java`:

```java
package example.gitinfo;

import java.io.InputStream;
import java.util.Map;
import java.util.Properties;

import org.springframework.boot.actuate.info.GitInfoContributor;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoPropertiesInfoContributor.Mode;
import org.springframework.boot.info.GitProperties;

public class GitModesDemo {
    public static void main(String[] args) throws Exception {
        Properties raw = new Properties();
        try (InputStream input = GitModesDemo.class.getClassLoader()
                .getResourceAsStream("git.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing classpath:git.properties");
            }
            raw.load(input);
        }

        Properties entries = new Properties();
        for (String key : raw.stringPropertyNames()) {
            if (key.startsWith("git.")) {
                entries.setProperty(key.substring(4), raw.getProperty(key));
            }
        }
        GitProperties properties = new GitProperties(entries);
        Map<String, Object> simple = content(properties, Mode.SIMPLE);
        Map<String, Object> full = content(properties, Mode.FULL);
        Map<String, Object> simpleCommit = map(simple.get("commit"));
        Map<String, Object> fullCommit = map(full.get("commit"));

        System.out.println("branch=" + properties.getBranch());
        System.out.println("commit.full=" + properties.getCommitId());
        System.out.println("commit.short=" + properties.getShortCommitId());
        System.out.println("commit.time=" + properties.getCommitTime());
        System.out.println("simple.id=" + simpleCommit.get("id"));
        System.out.println("simple.hasUser=" + simpleCommit.containsKey("user"));
        System.out.println("full.id=" + map(fullCommit.get("id")).get("full"));
        System.out.println("full.email=" + map(fullCommit.get("user")).get("email"));
        System.out.println("full.dirtyType=" + full.get("dirty").getClass().getSimpleName());

        Properties fallbackEntries = new Properties();
        fallbackEntries.setProperty("commit.id", properties.getCommitId());
        GitProperties withoutAbbreviation = new GitProperties(fallbackEntries);
        System.out.println("fallback.short=" + withoutAbbreviation.getShortCommitId());
    }

    private static Map<String, Object> content(GitProperties properties, Mode mode) {
        Info.Builder builder = new Info.Builder();
        new GitInfoContributor(properties, mode).contribute(builder);
        return map(builder.build().get("git"));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return (Map<String, Object>) value;
    }
}
```

Thêm task sau vào `build.gradle` của dự án thực hành:

```groovy
tasks.register('runGitModesDemo', JavaExec) {
    dependsOn tasks.named('classes')
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'example.gitinfo.GitModesDemo'
}
```

Chạy `./gradlew --quiet runGitModesDemo` hoặc `.\gradlew.bat --quiet runGitModesDemo`. Với đúng tệp phần 4, stdout của chương trình là:

```text
branch=main
commit.full=0123456789abcdef0123456789abcdef01234567
commit.short=0123456789
commit.time=2024-06-01T09:15:00Z
simple.id=0123456789
simple.hasUser=false
full.id=0123456789abcdef0123456789abcdef01234567
full.email=demo@example.invalid
full.dirtyType=String
fallback.short=0123456
```

Đọc kết quả theo hai tầng: Java vẫn đọc được email qua dữ liệu gốc, nhưng `simple` không đưa nhánh `commit.user` vào nội dung công bố. Chuyển sang `full` thay đổi phép chọn dữ liệu, không bổ sung dữ liệu từ Git.

Trong ứng dụng thật, có thể nhận `GitProperties` qua constructor của một bean thay vì tự nạp tệp. Nếu tài nguyên có thể không tồn tại ở môi trường phát triển, dùng `ObjectProvider<GitProperties>` hoặc điều kiện tạo bean phù hợp; inject bắt buộc mà thiếu bean có thể làm ứng dụng không khởi động. Không cần viết một REST controller riêng chỉ để đọc Git khi `info` đã đáp ứng nhu cầu.

## 8. Sinh dữ liệu thực thay cho tệp thực hành

Sau khi hiểu cơ chế, bỏ tệp dữ liệu giả và để công cụ dựng sinh thông tin từ kho Git. Spring Boot hướng dẫn dùng plugin Git riêng; `springBoot { buildInfo() }` tạo build metadata, không thay thế việc sinh Git metadata. [Hướng dẫn sinh Git information của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/how-to/build.html#howto.build.generate-git-info).

Ví dụ cấu hình cho một dự án Gradle độc lập, dùng plugin `2.4.1` được tài liệu Spring Boot 3.3 minh họa. Đây là phần ghép vào cấu hình hiện có, không phải yêu cầu đổi phiên bản plugin mà dự án đang quản lý:

```groovy
// Ghép dòng id vào khối plugins hiện có.
plugins {
    id 'com.gorylenko.gradle-git-properties' version '2.4.1'
}

gitProperties {
    keys = ['git.branch', 'git.commit.id', 'git.commit.time']
    dateFormat = "yyyy-MM-dd'T'HH:mm:ssZ"
    dateFormatTimeZone = 'UTC'
}
```

Danh sách `keys` giới hạn dữ liệu được đưa vào tài nguyên. Ví dụ này không đưa email hay URL kho vào JAR. Nếu cần chế độ `simple` trả mã rút gọn do plugin quy định, thêm `git.commit.id.abbrev` vào danh sách; khi không có, Spring Boot dùng nhánh dự phòng đã thử ở phần 7. Các tùy chọn chọn khóa và định dạng thời gian thuộc plugin sinh dữ liệu, không thuộc `management.info.git.mode`. [Tài liệu của plugin gradle-git-properties](https://github.com/n0mer/gradle-git-properties#configuration).

Dựng và kiểm tra tài nguyên cuối cùng trong JAR, không chỉ xem tệp trong thư mục nguồn:

```bash
./gradlew clean bootJar
```

Ví dụ nếu sản phẩm là `build/libs/demo-1.0.0.jar`:

```bash
jar tf build/libs/demo-1.0.0.jar
```

Danh sách phải có `BOOT-INF/classes/git.properties`. Tên JAR trong lệnh cần khớp sản phẩm thực tế. Có thể mở JAR bằng công cụ ZIP để đọc tài nguyên, đối chiếu mã commit với commit mà CI dự định dựng rồi chạy chính JAR đó.

Không giữ đồng thời tệp giả trong `src/main/resources` và tệp sinh tự động ở cùng vị trí đầu ra. Cần một nguồn tạo dữ liệu rõ ràng; nếu có nhiều bản sao cùng tên trên classpath, phải xử lý sự trùng lặp trước khi tin kết quả.

Trong CI, chú ý kho rỗng, checkout thiếu dữ liệu lịch sử, detached HEAD và bước tái sử dụng sản phẩm cũ. Những tình trạng này có thể ảnh hưởng thuộc tính công cụ sinh ra. Không đặt tên nhánh giả để che mất vấn đề truy nguyên; đối chiếu mã commit của sản phẩm với đầu vào dựng.

## 9. Chọn mức công bố theo nhu cầu

| Nhu cầu | Cách cấu hình phù hợp để xem xét | Điều vẫn phải kiểm tra |
| --- | --- | --- |
| Nhận diện nhanh bản chạy | `simple` với dữ liệu tối thiểu | Tên nhánh và mã rút gọn có được phép công bố không? |
| Điều tra chi tiết trong mạng quản trị | `full` với tập khóa đã duyệt | Email, URL kho, thông điệp commit, tên máy dựng có nằm trong dữ liệu không? |
| Không cung cấp thông tin Git qua info | `management.info.git.enabled=false` | Có contributor tự viết đang công bố lại không? |
| Chỉ cho người vận hành xem | Chọn nội dung và bảo vệ endpoint | Quy tắc truy cập HTTP có thực sự áp dụng cho info không? |

Chọn `simple` không làm tài nguyên trong JAR bớt dữ liệu; người nhận được JAR vẫn có thể đọc tệp. Khi thông tin không được phép rời hệ thống dựng, phải loại bỏ ngay ở bước sinh dữ liệu. Khi chỉ cần hạn chế người gọi HTTP, áp dụng thêm xác thực, phân quyền và giới hạn đường truy cập.

`full` cũng không phải cơ chế tự che giá trị nhạy cảm. Đừng giả định một thuộc tính tự đặt có tên giống mật khẩu sẽ được che giống một số endpoint khác. Cách kiểm soát chắc chắn là không đưa bí mật vào Git metadata và kiểm tra tập trường thực tế được trả về.

Nếu cần công bố mã commit đầy đủ nhưng không cần các chi tiết còn lại, có thể sinh một tập khóa rất hẹp rồi đánh giá JSON `full` của tập đó. Nếu cần hợp đồng JSON ổn định riêng, thiết kế contributor tùy chỉnh có danh sách trường cho phép; đó là phần mở rộng cần kiểm thử độc lập, không phải tính năng tự có của `simple`.

## 10. Chẩn đoán theo từng tầng

| Hiện tượng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| `/actuator/info` trả 404 | Endpoint có được bật và mở qua HTTP không; base path/port có đổi không? | Sửa vị trí gọi hoặc cấu hình endpoint, chưa vội sửa tệp Git |
| HTTP 401 hoặc 403 | Cơ chế xác thực và quyền truy cập | Gọi bằng danh tính phù hợp và xem quy tắc bảo vệ |
| HTTP 200 nhưng không có `git` | Tài nguyên cuối cùng, `GitProperties`, trạng thái contributor | Kiểm tra đúng JAR đang chạy, vị trí tài nguyên và `enabled` |
| Có `git` nhưng thiếu email | Có đang dùng `simple` không; tệp có email không? | Đây có thể là kết quả đúng của phép chọn dữ liệu |
| Đã đặt `full` nhưng không có thêm trường | Tập thuộc tính được sinh và bean contributor thực tế | `full` không tạo dữ liệu mới; kiểm tra cấu hình tự tạo |
| Mã commit không đổi sau bản dựng mới | Tệp giả, task sinh dữ liệu, sản phẩm hoặc image cũ | So sánh tài nguyên trong đúng sản phẩm vừa triển khai |
| Thời gian còn dạng chuỗi lạ hoặc Java đọc ra null | Giá trị đầu vào và định dạng thời gian | Dùng định dạng có offset được hỗ trợ và kiểm tra dữ liệu gốc |
| Bộ đọc JSON lỗi sau khi bật full | Kiểu của `git.commit.id` | Cập nhật hợp đồng đọc và kiểm thử cả dữ liệu thiếu |
| Java lấy `branch` ra null | Tên khóa truyền vào `GitProperties.get(...)` | Dùng `branch`, không dùng `git.branch` |

Nếu đã tắt các contributor mặc định qua `management.info.defaults.enabled=false`, hãy kiểm tra cấu hình riêng `management.info.git.enabled=true` trước khi kết luận tài nguyên bị hỏng. Chẩn đoán phải dựa trên cấu hình hiệu lực của môi trường chạy, vì profile hoặc tham số dòng lệnh có thể ghi đè tệp cấu hình.

## 11. Tự kiểm tra bằng thay đổi nhỏ có dự đoán

1. Với tệp phần 4, chạy cả HTTP và chương trình Java. Giải thích vì sao `simple.id` dài 10 ký tự.
2. Xóa riêng dòng `git.commit.id.abbrev`, dựng hoặc nạp lại rồi chạy chương trình Java. Dự đoán mã rút gọn còn `0123456`; mã đầy đủ vẫn giữ nguyên.
3. Khôi phục tệp, xóa email và URL kho. Bật `full`, kiểm tra các trường đó không còn xuất hiện. Đổi chế độ không thể tái tạo dữ liệu đã bị loại bỏ.
4. Tắt contributor Git, khởi động lại ứng dụng và gọi info. Phân biệt việc thiếu phần `git` với endpoint không tồn tại.
5. Đổi từ tệp cố định sang dữ liệu sinh tự động. Chọn một commit đã biết, dựng JAR và chứng minh mã trong tài nguyên, JSON và đầu vào CI cùng chỉ tới commit đó.

Các phép thử 1–3 dùng dữ liệu giả nên có thể dự đoán chính xác giá trị. Phép thử 5 dùng kho thật nên kết quả cụ thể phụ thuộc commit đang dựng; không chép các giá trị giả của bài vào báo cáo vận hành.

## 12. Những điểm cần nhớ khi áp dụng

Để tin thông tin commit của một bản chạy, hãy kiểm tra từ nguồn tạo tài nguyên tới sản phẩm được triển khai, rồi mới tới nội dung endpoint. `GitProperties` là dữ liệu đã nạp; `GitInfoContributor` quyết định phần được đưa ra ngoài; cấu hình HTTP quyết định đường truy cập.

Một lựa chọn công bố hợp lý cần đồng thời đúng dữ liệu, đúng cấu trúc JSON mà bên đọc mong đợi và đúng phạm vi người được xem. Tăng số trường bằng `full` chỉ có ý nghĩa sau khi đã xác nhận những trường đó thật sự cần thiết và đã có trong bản dựng.
