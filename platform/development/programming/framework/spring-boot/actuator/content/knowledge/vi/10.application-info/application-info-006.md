# Công bố thông tin Java, hệ điều hành và tiến trình

## 1. Biết ứng dụng đang chạy trong môi trường nào

Cùng một tệp JAR có thể chạy đúng trên máy lập trình viên nhưng gặp vấn đề sau khi triển khai: máy chủ dùng bản Java khác dự kiến, kiến trúc bộ xử lý khác, hoặc người vận hành đang đối chiếu nhầm tiến trình. Trước khi phân tích lỗi nghiệp vụ, cần xác định môi trường thực sự đang chạy ứng dụng.

Trong Spring Boot Actuator, endpoint `info` tập hợp các phần thông tin do những thành phần triển khai `InfoContributor` cung cấp. Bài này tập trung vào ba nguồn có sẵn: `java`, `os` và `process`. Chúng trả lời ba câu hỏi liên tiếp: **chạy bằng Java nào → JVM nhìn thấy hệ điều hành nào → đây là tiến trình nào**.

| Phần thông tin | Câu hỏi cần trả lời | Ví dụ sử dụng |
| --- | --- | --- |
| `java` | Phiên bản và nhà cung cấp Java/JVM đang chạy là gì? | Kiểm tra môi trường chạy sau khi đổi ảnh triển khai |
| `os` | Tên, phiên bản và kiến trúc hệ điều hành mà JVM báo cáo là gì? | Đối chiếu môi trường Windows/Linux hoặc `amd64`/`aarch64` |
| `process` | Tiến trình có PID, tiến trình cha, tài khoản chạy và số CPU khả dụng nào? | Liên hệ thông tin ứng dụng với công cụ vận hành |

Bài sử dụng **Spring Boot 3.3.x và JDK 21**. `ProcessInfoContributor` được bổ sung từ Spring Boot 3.3.0; ứng dụng dùng phiên bản cũ hơn không có sẵn tính năng này chỉ bằng cách thêm thuộc tính cấu hình. Xem [ghi chú phát hành Spring Boot 3.3](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes).

## 2. Phân biệt nguồn dữ liệu, endpoint và quyền truy cập

Ba nguồn `java`, `os`, `process` **mặc định đều tắt** trong Spring Boot 3.3. Để nhận dữ liệu qua HTTP, cần phân biệt ba việc:

1. Bật từng nguồn bằng `management.info.<id>.enabled`.
2. Endpoint `info` phải được bật và được công bố qua HTTP.
3. Yêu cầu HTTP phải được cơ chế bảo mật cho phép.

Bật nguồn `java` không tự công bố URL. Ngược lại, công bố `info` không tự bật ba nguồn. Cấu hình và mặc định được mô tả trong [tài liệu endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info).

Về luồng dữ liệu, có thể hình dung:

```text
Java/JVM, hệ điều hành, tiến trình hiện tại
                  ↓
JavaInfoContributor + OsInfoContributor + ProcessInfoContributor
                  ↓
              InfoEndpoint
                  ↓
       GET /actuator/info → JSON
```

Không cần viết Controller riêng cho URL này. Cũng không cần tạo `build-info.properties` hoặc `git.properties` để ba nguồn đang học hoạt động; các tệp đó phục vụ thông tin build/Git.

## 3. Cấu hình để quan sát trong một ứng dụng web

### 3.1. Điều kiện của ví dụ

Dùng một ứng dụng Spring Boot 3.3.x có sẵn lớp khởi động và môi trường web. Với Gradle, bảo đảm có các dependency sau trong khối `dependencies`; phiên bản được quản lý bởi cấu hình Spring Boot của dự án:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là **đoạn cấu hình bổ sung**, không phải toàn bộ dự án Gradle độc lập. Nếu ứng dụng đã dùng WebFlux, giữ `spring-boot-starter-webflux` hiện có; không thêm MVC chỉ để đọc `info`.

Ví dụ HTTP dưới đây giả định không có context path tùy chỉnh, không có proxy phía trước và không có Spring Security. Nếu dự án có bảo mật, hãy dùng tài khoản có quyền đọc endpoint theo chính sách của dự án.

### 3.2. Bật rõ từng nguồn

Trong `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    java:
      enabled: true
    os:
      enabled: true
    process:
      enabled: true
```

Ở ví dụ học trên máy cá nhân, `server.address` giới hạn máy chủ vào loopback. Đây là lựa chọn của ví dụ, không phải yêu cầu của Actuator. Khi tích hợp vào ứng dụng khác, hợp nhất các khóa YAML với cấu hình hiện có; tránh tạo hai khóa `management` ngang hàng.

Nếu dùng `application.properties`, phần tương đương để bật ba nguồn là:

```properties
management.info.java.enabled=true
management.info.os.enabled=true
management.info.process.enabled=true
```

Ba dòng này chỉ thay cho phần `management.info` ở YAML; các thiết lập endpoint và HTTP vẫn cần được giữ. Không cần bật `management.info.env.enabled` cho bài này.

### 3.3. Chạy và gọi endpoint

Từ thư mục gốc của ứng dụng ví dụ có Gradle Wrapper, chạy trên Windows:

```powershell
.\gradlew.bat bootRun
```

Với macOS/Linux:

```bash
./gradlew bootRun
```

Đây là lệnh cho một ứng dụng riêng có task `bootRun`; trong một repository nhiều module, dùng đường dẫn task của module cần chạy.

Khi ứng dụng đã khởi động, mở terminal khác. Trên Windows dùng `curl.exe` để tránh nhầm với bí danh PowerShell:

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/info
```

Trên macOS/Linux:

```bash
curl -i http://127.0.0.1:8080/actuator/info
```

Phản hồi thành công có mã HTTP `200`. Nội dung sau là **JSON minh họa**, không phải các giá trị cố định phải xuất hiện trên máy của bạn; thứ tự các khóa cũng không phải điều kiện kiểm tra:

```json
{
  "java": {
    "version": "21.0.9",
    "vendor": {
      "name": "Microsoft"
    },
    "runtime": {
      "name": "OpenJDK Runtime Environment",
      "version": "21.0.9+10-LTS"
    },
    "jvm": {
      "name": "OpenJDK 64-Bit Server VM",
      "vendor": "Microsoft",
      "version": "21.0.9+10-LTS"
    }
  },
  "os": {
    "name": "Linux",
    "version": "6.8.0",
    "arch": "amd64"
  },
  "process": {
    "pid": 24580,
    "parentPid": 24410,
    "owner": "appuser",
    "cpus": 4
  }
}
```

Nếu dự án còn có nguồn build/Git hoặc contributor tự viết, JSON có thể có thêm các phần khác. Không dùng phép so sánh toàn bộ phản hồi với mẫu minh họa để kết luận ba nguồn này đúng hay sai.

## 4. Đọc đúng phần `java`

`java` mô tả **môi trường đang chạy ứng dụng**. Spring Boot biểu diễn nó bằng `JavaInfo`, gồm phiên bản Java, nhà cung cấp, môi trường chạy và máy ảo. Cấu trúc này được mô tả tại [JavaInfo của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/JavaInfo.html).

| Đường dẫn thường gặp | Ý nghĩa |
| --- | --- |
| `java.version` | Phiên bản Java đang được JVM báo cáo |
| `java.vendor.name` | Nhà cung cấp Java |
| `java.vendor.version` | Thông tin phiên bản riêng của nhà cung cấp, khi có |
| `java.runtime.name`, `java.runtime.version` | Tên và phiên bản môi trường chạy |
| `java.jvm.name`, `java.jvm.vendor`, `java.jvm.version` | Tên, nhà cung cấp và phiên bản máy ảo |

Các trường phụ thuộc dữ liệu của JDK; đừng giả định mọi nhà cung cấp đều có `vendor.version` hoặc cùng một cách định dạng chuỗi phiên bản.

Ví dụ, dự án cấu hình Java toolchain 21 cho việc biên dịch chưa đủ chứng minh tiến trình đang phục vụ HTTP cũng chạy bằng đúng bản JDK đó. IDE, dịch vụ hệ điều hành hoặc ảnh container có thể khởi động ứng dụng bằng một Java khác. Khi điều tra, lấy phần `java` từ chính instance đang gặp lỗi.

Tương tự, `java -version` trong terminal mới chỉ mô tả lệnh `java` mà terminal đó tìm thấy. Hãy đối chiếu nó với thông tin runtime của ứng dụng trước khi kết luận hai bên dùng cùng JDK.

Thông tin này giúp xác minh môi trường; nó không tự chứng minh ứng dụng không có lỗi tương thích hoặc không cần cập nhật bảo mật.

## 5. Đọc đúng phần `os`

`os` có ba trường chính trong API Spring Boot 3.3:

| Trường | Nguồn thông tin được công bố |
| --- | --- |
| `os.name` | System property `os.name` |
| `os.version` | System property `os.version` |
| `os.arch` | System property `os.arch` |

Đây là cách JVM mô tả môi trường hệ điều hành. Cấu trúc các trường được xác nhận trong [API `info` của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html#actuator-api.info.response-structure).

Khi so sánh môi trường triển khai, dùng các giá trị thực tế thay vì suy đoán từ tên máy. Chẳng hạn, nếu hai instance trả `amd64` và `aarch64`, hãy kiểm tra lại ảnh triển khai và thư viện native mà ứng dụng sử dụng.

Trong container, cũng cần phân biệt ảnh hệ điều hành người dùng, kernel và góc nhìn của JVM. Từ riêng `os.name`/`os.version` không thể suy ra đầy đủ bản phân phối, phiên bản ảnh container hoặc cấu hình máy chủ vật lý. Muốn biết image tag/digest, phải đối chiếu dữ liệu triển khai.

Không dùng `os.arch` như một số đo hiệu năng: hai máy có cùng kiến trúc vẫn có thể khác số CPU được cấp, giới hạn bộ nhớ và tải hiện tại.

## 6. Đọc đúng phần `process`

### 6.1. Những trường có trong Spring Boot 3.3

| Trường | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `process.pid` | Mã định danh tiến trình ứng dụng | Đối chiếu với tiến trình Java cần kiểm tra |
| `process.parentPid` | PID tiến trình cha; có thể là `-1` khi không xác định được | Tìm hiểu ứng dụng được khởi động qua trình chạy nào |
| `process.owner` | Tài khoản sở hữu/chạy tiến trình được báo cáo | Đối chiếu tài khoản vận hành dự kiến |
| `process.cpus` | Số bộ xử lý khả dụng với tiến trình theo JVM | Kiểm tra góc nhìn tài nguyên của tiến trình |

Đây là schema của **Spring Boot 3.3**, không phải danh sách mọi trường của các bản Spring Boot mới hơn. Không lấy mẫu `process.memory` hoặc thông tin luồng ảo từ tài liệu phiên bản khác rồi coi chúng là đầu ra bắt buộc của 3.3.

### 6.2. PID chỉ có ý nghĩa trong đúng môi trường

Một ứng dụng có thể được khởi động từ IDE, Gradle, script hoặc trình quản lý dịch vụ. Vì vậy, tiến trình cha không nhất thiết là shell bạn đang mở. Sau khi khởi động lại, PID cũng không được bảo đảm giữ nguyên.

Java cung cấp `ProcessHandle` để nhận diện tiến trình hiện tại và truy vấn tiến trình cha. PID có thể được hệ điều hành tái sử dụng sau khi tiến trình kết thúc; vì vậy không dùng PID làm định danh nghiệp vụ lâu dài. Xem [ProcessHandle trong Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html).

Trong container hoặc môi trường có phân tách không gian PID, cần đối chiếu từ đúng góc nhìn của tiến trình. Không tìm thấy PID `1` của container trong danh sách tiến trình theo cách bạn dự kiến trên máy chủ chưa đủ để kết luận Actuator trả sai.

Với nhiều replica phía sau bộ cân bằng tải, hai lần gọi cùng một URL có thể đi vào hai tiến trình khác nhau. Muốn so sánh PID trước/sau, hãy truy cập đúng instance hoặc dùng công cụ định tuyến nội bộ của môi trường triển khai.

### 6.3. Số CPU khả dụng không phải phần trăm sử dụng CPU

`Runtime.availableProcessors()` trả số bộ xử lý khả dụng với JVM; giá trị tối thiểu là `1` và có thể thay đổi trong vòng đời JVM. Đây là số lượng tài nguyên nhìn thấy, không phải phần trăm CPU đang bận. Xem [Runtime.availableProcessors() của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html#availableProcessors()).

Ví dụ, `process.cpus = 4` không có nghĩa ứng dụng đang dùng 4% CPU, cũng không chứng minh máy chủ vật lý chỉ có bốn lõi. Nếu con số khác dự kiến, hãy kiểm tra giới hạn container, lựa chọn JVM và môi trường thực thi; không vội sửa thuật toán chỉ từ một giá trị này.

Để theo dõi tải, bộ nhớ hoặc thời gian sống theo thời gian, dùng hệ thống metrics phù hợp. Spring Boot tích hợp Micrometer cho nhóm nhu cầu đó; xem [tài liệu metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 7. Chương trình Java để quan sát nguồn thông tin

Chương trình sau chạy độc lập, không cần Spring. Nó giúp thấy những dữ liệu mà Java có thể truy vấn từ môi trường chạy. Lưu nguyên nội dung thành `RuntimeProbe.java`:

```java
public class RuntimeProbe {
    public static void main(String[] args) {
        ProcessHandle current = ProcessHandle.current();

        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.version=" + System.getProperty("os.version"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("pid=" + current.pid());
        System.out.println("parentPid="
                + current.parent().map(ProcessHandle::pid).orElse(-1L));
        System.out.println("owner=" + current.info().user().orElse("unknown"));
        System.out.println("cpus=" + Runtime.getRuntime().availableProcessors());
    }
}
```

Biên dịch và chạy bằng JDK 21:

```text
javac --release 21 RuntimeProbe.java
java RuntimeProbe
```

Đầu ra luôn theo thứ tự chín dòng được viết trong chương trình; **các giá trị thay đổi theo máy và lần chạy**. Một ví dụ minh họa là:

```text
java.version=21.0.9
java.vendor=Microsoft
os.name=Linux
os.version=6.8.0
os.arch=amd64
pid=24620
parentPid=24410
owner=appuser
cpus=4
```

Đây là một tiến trình Java mới, nên PID của chương trình này không phải PID của ứng dụng Spring Boot đang phục vụ `/actuator/info`. Muốn kiểm tra cùng một tiến trình, hãy quan sát bên trong ứng dụng hoặc đối chiếu công cụ hệ điều hành với PID do chính endpoint trả về.

`parent()` và `user()` biểu diễn dữ liệu có thể không sẵn có. Ví dụ chủ động dùng `-1` và chuỗi `unknown` làm giá trị thay thế trong chương trình tự viết; không coi chuỗi `unknown` là cam kết đầu ra của mọi bản Actuator. Quyền hệ điều hành có thể giới hạn thông tin tiến trình được truy vấn, như mô tả tại [ProcessHandle.Info của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html).

## 8. Công bố đúng phạm vi và hiểu các lỗi thường gặp

Thông tin nhà cung cấp Java, phiên bản hệ điều hành, PID và tài khoản chạy có giá trị vận hành. Khi đưa vào môi trường triển khai, hãy xác định đối tượng cần đọc và áp dụng quyền truy cập phù hợp; không tự động mở tất cả endpoint chỉ để thấy phần `java`.

Với một nhu cầu chỉ dành cho công cụ trên máy chạy ứng dụng, có thể tách cổng quản trị và giới hạn địa chỉ lắng nghe:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Đoạn này được **hợp nhất** vào cấu hình ở phần 3; khi đó gọi `http://127.0.0.1:8081/actuator/info`. Spring Boot cho phép cấu hình địa chỉ riêng của management server khi cổng quản trị khác cổng ứng dụng. Xem [cấu hình HTTP quản trị của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Giới hạn địa chỉ không thay thế mọi chính sách xác thực/phân quyền. Ngược lại, chỉ chuyển sang cổng khác mà vẫn lắng nghe trên mạng công khai cũng chưa xác định ai được quyền đọc.

| Hiện tượng | Nhánh cần kiểm tra | Hành động phù hợp |
| --- | --- | --- |
| HTTP `404` | Sai cổng/đường dẫn; endpoint chưa bật hoặc chưa được công bố | Kiểm tra cấu hình endpoint, exposure, context path và cổng quản trị |
| HTTP `401` hoặc `403` | Chính sách xác thực/phân quyền hoặc lớp trung gian từ chối | Dùng thông tin xác thực đúng và kiểm tra quy tắc truy cập thực tế |
| HTTP `200` nhưng không có `java`/`os`/`process` | Các nguồn tương ứng chưa được bật hoặc cấu hình đang chạy khác dự kiến | Kiểm tra profile và ba thuộc tính `management.info.*.enabled` |
| Chỉ có `{}` | Không có contributor nào đang đóng góp dữ liệu | Kiểm tra từng nguồn; không đồng nhất phản hồi rỗng với lỗi HTTP |
| Thiếu `process` khi dùng Spring Boot cũ | Phiên bản chưa có contributor tích hợp | Đối chiếu phiên bản; không tiếp tục đổi exposure để tìm một tính năng chưa tồn tại |
| Không có `process.memory` trên 3.3 | Đang so sánh với schema phiên bản khác | Dùng tài liệu đúng phiên bản và nguồn đo thích hợp |
| PID hoặc số CPU khác dự kiến | Khác instance, không gian PID hoặc giới hạn tài nguyên | Xác minh đúng tiến trình và môi trường trước khi kết luận |

Bảng trên là hướng điều tra, không phải kết luận duy nhất cho mọi hệ thống. Proxy hoặc cấu hình bảo mật riêng có thể trả mã lỗi khác.

Không dùng `management.endpoint.health.show-details` để điều khiển nội dung của `info`: đó là thuộc tính thuộc endpoint `health`. Cũng không cho rằng quy tắc che dữ liệu của `/env` tự áp dụng cho mọi thông tin ở `/info`.

## 9. Thực hành kiểm chứng từng lớp

Thực hiện với ứng dụng ví dụ trên máy cá nhân:

1. Bật ba nguồn và gọi `info`. Xác nhận ba khóa `java`, `os`, `process` xuất hiện; ghi lại phiên bản Java và PID thực tế.
2. Đặt riêng `management.info.os.enabled=false`, khởi động lại rồi gọi lại. Phần `os` phải vắng mặt, còn `java` và `process` vẫn có nếu cấu hình còn lại giữ nguyên.
3. Bật lại `os`; bỏ `info` khỏi danh sách HTTP exposure và khởi động lại. Với ứng dụng ví dụ không có lớp bảo mật/proxy bổ sung, đường dẫn đó không còn được công bố và trả `404`. Việc bật contributor không làm URL tự xuất hiện.
4. Khôi phục exposure và gọi lại. Đối chiếu `java.version` với Java thực sự được dùng để khởi động ứng dụng, không chỉ Java trên terminal khác.
5. Chạy `RuntimeProbe` bằng cùng bản JDK. So sánh nhóm thông tin Java/hệ điều hành; giải thích vì sao PID của hai chương trình khác nhau.

Trong bài kiểm tra tự động, ưu tiên kiểm tra sự có mặt của từng phần, kiểu dữ liệu và điều kiện như PID dương hoặc số CPU tối thiểu là `1`; tránh cố định PID, chuỗi phiên bản kernel hay thứ tự khóa JSON.

Sau thực hành, người học cần giải thích được: vì sao bật nguồn và công bố endpoint là hai bước khác nhau; phần nào xác nhận runtime; vì sao PID cần gắn với instance; và vì sao số CPU khả dụng không phải tải CPU.
