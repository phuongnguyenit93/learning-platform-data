# Lọc truy vấn auditevents theo chủ thể, thời gian và loại sự kiện

## 1. Từ lịch sử kiểm toán đến câu hỏi cần trả lời

Một sự kiện kiểm toán ghi lại việc một người hoặc dịch vụ thực hiện một hành động tại một thời điểm. Khi điều tra, ta thường không cần đọc toàn bộ lịch sử, mà muốn trả lời câu hỏi cụ thể:

> Những lần xác thực thất bại của tài khoản alice sau 10:02 UTC là những sự kiện nào?

Spring Boot Actuator cung cấp endpoint `auditevents` để đọc các sự kiện mà `AuditEventRepository` đang giữ. Ba bộ lọc của bài học tương ứng với ba phần của câu hỏi:

- **Chủ thể thực hiện:** `principal`.
- **Mốc thời gian phía dưới:** `after`.
- **Loại sự kiện:** `type`.

Hiểu đúng bộ lọc giúp thu hẹp dữ liệu, nhưng chưa đủ để kết luận lịch sử đầy đủ. Kết quả còn phụ thuộc việc sự kiện có được phát ra, được giữ trong repository và thuộc phạm vi người đọc được phép xem hay không.

## 2. Hình dung đường đi của một truy vấn

Với cấu hình đường dẫn mặc định và ứng dụng có web, một yêu cầu đọc có dạng:

```http
GET /actuator/auditevents?principal=alice&after=2026-01-01T10:02:00Z&type=AUTHENTICATION_FAILURE
```

Đường xử lý có thể hình dung như sau:

```text
HTTP GET và các query parameter
    -> chuyển đổi tham số thời gian
    -> AuditEventsEndpoint
    -> AuditEventRepository.find(principal, after, type)
    -> kết quả được đưa vào mảng events
```

Ba tham số là tùy chọn. Bỏ một tham số nghĩa là không yêu cầu lọc theo tiêu chí đó; không có nghĩa endpoint sẽ tự chọn tài khoản hiện tại hay tự giới hạn về một giờ gần nhất.

Hợp đồng Java của repository là:

```java
List<AuditEvent> find(String principal, Instant after, String type);
```

Đây là chữ ký API để đọc hiểu, không phải một tệp Java độc lập. Tại repository, `null` biểu thị việc không hạn chế theo tiêu chí tương ứng. Xem [AuditEventRepository trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html).

Endpoint cần một bean `AuditEventRepository` và cần được expose qua HTTP. Cấu hình expose chỉ mở đường truy cập; không tự tạo sự kiện hoặc cấp quyền cho người gọi. Xem [Spring Boot 3.3: Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 3. Ý nghĩa chính xác của từng bộ lọc

| Tham số | Ý nghĩa | Ví dụ | Khi không cần lọc |
| --- | --- | --- | --- |
| `principal` | Chọn sự kiện của một chủ thể đã được ghi trong sự kiện | `principal=alice` | Bỏ tham số |
| `after` | Chọn sự kiện xảy ra sau một thời điểm | `after=2026-01-01T10:02:00Z` | Bỏ tham số |
| `type` | Chọn một loại sự kiện | `type=AUTHENTICATION_FAILURE` | Bỏ tham số |

Đối với repository trong bộ nhớ dùng ở phần thực hành, principal và type được so khớp chính xác, có phân biệt chữ hoa/chữ thường. `alice` khác `Alice`; `AUTHENTICATION_FAILURE` khác `authentication_failure`. Không có tìm kiếm chứa chuỗi, biểu thức chính quy hoặc ký tự đại diện tự động.

Tên loại sự kiện là chuỗi do nguồn phát sử dụng. Các tên trong bài như `AUTHENTICATION_SUCCESS`, `AUTHENTICATION_FAILURE` và `AUTHORIZATION_FAILURE` chỉ có ý nghĩa nếu sự kiện thực sự được ghi với đúng tên đó. Ứng dụng cũng có thể có loại nghiệp vụ riêng.

Nếu dùng repository tùy chỉnh, cần kiểm chứng cách so khớp của cách hiện thực đó, đặc biệt khi collation của CSDL có thể không phân biệt hoa/thường. Không suy ra mọi backend giống hệt repository trong bộ nhớ.

### 3.1. Các điều kiện kết hợp theo AND

Truy vấn có cả ba tham số yêu cầu một sự kiện thỏa mãn đồng thời:

```text
principal của sự kiện = alice
VÀ timestamp của sự kiện > 2026-01-01T10:02:00Z
VÀ type của sự kiện = AUTHENTICATION_FAILURE
```

Một sự kiện của `bob` bị loại dù thời gian và loại đều đúng. Một sự kiện của `alice` sau mốc cũng bị loại nếu loại là `AUTHORIZATION_FAILURE`.

Thứ tự viết ba tham số trong URL không làm thay đổi ý nghĩa. Không được hiểu chúng là phép OR.

### 3.2. Bỏ tham số khác với gửi chuỗi "null"

Nếu muốn xem mọi principal, hãy bỏ `principal` khỏi URL. `principal=null` gửi chuỗi bốn ký tự `null`; đó không phải giá trị `null` của Java.

Tương tự, muốn không giới hạn thời gian thì bỏ `after`. Không gửi `after=null`, không trông chờ tham số rỗng được xử lý giống nhau trong mọi lớp client, proxy và bộ chuyển đổi.

Không gửi `principal=*` hoặc `type=*` để thay cho “tất cả”: dấu `*` không có hợp đồng là wildcard của endpoint.

## 4. after là mốc loại trừ và phải xác định được một thời điểm

### 4.1. Sự kiện đúng tại mốc không thuộc kết quả

Giả sử có sự kiện tại `10:02:00Z`:

```text
timestamp <  after  -> bị loại
timestamp == after  -> bị loại
timestamp >  after  -> được xét tiếp theo các điều kiện khác
```

Vì vậy, `after=2026-01-01T10:02:00Z` không trả sự kiện đúng `10:02:00Z`. Không được đọc “after” thành “từ thời điểm này trở đi, có bao gồm mốc”.

Nếu cần truy vấn chính xác một khoảng có biên bao gồm/không bao gồm, chẳng hạn `[start, end)`, phải có dịch vụ truy vấn hỗ trợ hợp đồng đó. Endpoint đang học chỉ cung cấp mốc dưới `after`, không có cặp `from/to` hay `before` tương ứng.

### 4.2. Dùng thời gian ISO-8601 có offset

Hai cách viết sau biểu diễn cùng một thời điểm:

```text
2026-01-01T10:02:00Z
2026-01-01T17:02:00+07:00
```

`Z` chỉ UTC. `+07:00` cho biết giờ hiển thị đi trước UTC bảy giờ. Đây là hai biểu diễn của cùng một mốc trên trục thời gian, không phải hai khoảng tìm kiếm khác nhau. Xem [Java OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html).

Dùng cách viết đầy đủ, chẳng hạn `2026-01-01T10:02:00Z`. Chuỗi chỉ có ngày hoặc giờ địa phương thiếu offset như `2026-01-01T10:02:00` không xác định rõ mốc cần tìm của endpoint. Trong ứng dụng Spring Boot 3.3.13 ở phần thực hành, chuỗi thiếu offset hoặc `not-a-time` trả HTTP `400`.

`after` áp dụng lên timestamp của sự kiện, không phải thời điểm ta gửi yêu cầu HTTP. Đồng hồ của nơi phát sự kiện hoặc sự kiện đến kho muộn có thể ảnh hưởng cách diễn giải kết quả.

## 5. Chuẩn bị một ứng dụng có dữ liệu cố định

Ví dụ này dùng Java 17+; có thể chọn JDK 21, Maven 3.6.3+ và Spring Boot 3.3.13. Phiên bản được cố định để học hành vi trong nhánh 3.3.x, không phải khuyến nghị chọn phiên bản mới cho dự án khác.

Tạo một thư mục học thử riêng:

```text
audit-filter-lab/
├── pom.xml
├── BuildAuditQuery.java
└── src/main/
    ├── java/demo/AuditFilterApplication.java
    └── resources/application.properties
```

`BuildAuditQuery.java` được dùng ở phần 9; chưa cần tạo nó để chạy server.

### 5.1. Khai báo phụ thuộc

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>audit-filter-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Ứng dụng cần phần web để nhận HTTP và Actuator để cung cấp endpoint. Không cần controller nghiệp vụ mới cho phép thử truy vấn này.

### 5.2. Khởi tạo repository và sáu sự kiện

Tệp `src/main/java/demo/AuditFilterApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.time.Instant;
import java.util.Map;

@SpringBootApplication
public class AuditFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuditFilterApplication.class, args);
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        var repository = new InMemoryAuditEventRepository(20);
        add(repository, "E1", "2026-01-01T10:00:00Z",
                "alice", "AUTHENTICATION_SUCCESS");
        add(repository, "E2", "2026-01-01T10:01:00Z",
                "alice", "AUTHENTICATION_FAILURE");
        add(repository, "E3", "2026-01-01T10:02:00Z",
                "bob", "AUTHENTICATION_FAILURE");
        add(repository, "E4", "2026-01-01T10:03:00Z",
                "alice", "AUTHORIZATION_FAILURE");
        add(repository, "E5", "2026-01-01T10:04:00Z",
                "alice", "AUTHENTICATION_FAILURE");
        add(repository, "E6", "2026-01-01T10:04:00Z",
                "ops+night@example.com", "AUTHENTICATION_FAILURE");
        return repository;
    }

    private static void add(AuditEventRepository repository, String ref,
                            String timestamp, String principal, String type) {
        repository.add(new AuditEvent(
                Instant.parse(timestamp), principal, type, Map.of("ref", ref)));
    }
}
```

Các sự kiện được thêm trực tiếp để tạo bộ dữ liệu lặp lại được. Chúng là dữ liệu mô phỏng; chương trình không thực hiện đăng nhập thật và không có Spring Security trong danh sách phụ thuộc.

Dung lượng repository được đặt là 20, đủ cho sáu sự kiện. Thời gian được cố định thay vì dùng `Instant.now()` để mọi kết quả dự đoán không phụ thuộc giờ chạy bài.

### 5.3. Expose đúng endpoint trong môi trường học thử

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18084
management.endpoint.auditevents.enabled=true
management.endpoints.web.exposure.include=health,auditevents
```

Server chỉ lắng nghe ở `127.0.0.1` trên máy chạy bài. Ví dụ không cấu hình xác thực, nên chỉ dùng trong môi trường học thử cục bộ. Với ứng dụng vận hành, phải bảo vệ đường truy cập lịch sử kiểm toán theo chính sách quyền của hệ thống.

Khởi động từ thư mục dự án:

```powershell
mvn -q package
java -jar target/audit-filter-lab-1.0.0.jar
```

Đợi ứng dụng khởi động xong rồi mở terminal thứ hai để gửi truy vấn. Nhấn `Ctrl+C` ở terminal chạy Java để kết thúc sau khi học.

Các lệnh HTTP dưới đây dùng `curl.exe` trên Windows nhằm gọi đúng chương trình curl. Trên Linux/macOS, thay `curl.exe` bằng `curl`. Nếu đổi cổng của server, đổi cùng cổng trong các lệnh và chương trình tạo URL.

### 5.4. Bảng dữ liệu để đối chiếu

| Nhãn trong data.ref | Timestamp UTC | Principal | Type |
| --- | --- | --- | --- |
| E1 | `2026-01-01T10:00:00Z` | `alice` | `AUTHENTICATION_SUCCESS` |
| E2 | `2026-01-01T10:01:00Z` | `alice` | `AUTHENTICATION_FAILURE` |
| E3 | `2026-01-01T10:02:00Z` | `bob` | `AUTHENTICATION_FAILURE` |
| E4 | `2026-01-01T10:03:00Z` | `alice` | `AUTHORIZATION_FAILURE` |
| E5 | `2026-01-01T10:04:00Z` | `alice` | `AUTHENTICATION_FAILURE` |
| E6 | `2026-01-01T10:04:00Z` | `ops+night@example.com` | `AUTHENTICATION_FAILURE` |

`ref` là dữ liệu bổ sung tự đặt để đọc ví dụ cho dễ. Nó không phải một trường mã sự kiện bắt buộc do endpoint sinh ra. Hai sự kiện E5 và E6 cùng timestamp để minh họa rằng thời gian không nhất thiết là định danh duy nhất.

## 6. Gửi truy vấn từ rộng đến hẹp

### 6.1. Không có bộ lọc

```powershell
curl.exe --silent --show-error "http://127.0.0.1:18084/actuator/auditevents"
```

Với đúng dữ liệu mẫu, mảng `events` chứa E1, E2, E3, E4, E5 và E6.

Điều này nghĩa là không đặt ba điều kiện lọc của bài. Nó chỉ trả các sự kiện repository đang giữ, không khôi phục sự kiện đã mất trước đó.

### 6.2. Chỉ lọc theo chủ thể

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice"
```

Kết quả gồm E1, E2, E4, E5. Ta đã biết chủ thể nhưng chưa giới hạn loại hoặc thời gian.

### 6.3. Chỉ lọc theo thời gian

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "after=2026-01-01T10:02:00Z"
```

Kết quả gồm E4, E5, E6. E3 bị loại vì nó xảy ra đúng tại mốc `10:02:00Z`.

### 6.4. Chỉ lọc theo loại

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

Kết quả gồm E2, E3, E5, E6. Những sự kiện này có thể thuộc các chủ thể và thời điểm khác nhau.

### 6.5. Kết hợp cả ba điều kiện

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice" --data-urlencode "after=2026-01-01T10:02:00Z" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

Chỉ E5 thỏa cả ba điều kiện. Phản hồi JSON, trình bày lại khoảng trắng cho dễ đọc:

```json
{
  "events": [
    {
      "timestamp": "2026-01-01T10:04:00Z",
      "principal": "alice",
      "type": "AUTHENTICATION_FAILURE",
      "data": {
        "ref": "E5"
      }
    }
  ]
}
```

Đọc `events` để lấy danh sách. `timestamp`, `principal` và `type` mô tả sự kiện; `data` chứa thông tin bổ sung được nguồn phát đưa vào. Không suy ra mọi loại sự kiện luôn có cùng các khóa trong `data`.

Các tập nhãn trong bài dùng để so sánh thành viên, không cam kết thứ tự phần tử của mọi repository. Giao diện `AuditEventRepository` không có tham số `sort`; client không nên dựa vào một thứ tự tình cờ thấy ở kho RAM.

### 6.6. Không có bản ghi khớp vẫn là truy vấn thành công

Đổi mốc của truy vấn kết hợp thành `2026-01-01T10:04:00Z`:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice" --data-urlencode "after=2026-01-01T10:04:00Z" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

E5 bằng đúng mốc nên bị loại. Phản hồi có HTTP `200` với nội dung:

```json
{"events":[]}
```

Danh sách rỗng không phải HTTP `404`. Nó cũng không tự chứng minh rằng trong thực tế chưa từng xảy ra hành động cần tìm; chỉ cho biết không có bản ghi khớp trong kết quả truy vấn hiện tại.

## 7. Mã hóa URL: dấu cộng rất dễ làm sai truy vấn

### 7.1. Dấu cộng trong offset thời gian

Có thể thay mốc UTC trong truy vấn kết hợp bằng `2026-01-01T17:02:00+07:00`:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice" --data-urlencode "after=2026-01-01T17:02:00+07:00" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

Kết quả vẫn chỉ là E5.

Trong cách giải mã tham số kiểu form, dấu `+` có thể được hiểu là dấu cách. Vì vậy, dấu cộng thật trong giá trị phải được mã hóa thành `%2B`. Chỉ bọc cả URL trong dấu nháy không thực hiện việc mã hóa này.

Một URL đã mã hóa tương ứng là:

```text
http://127.0.0.1:18084/actuator/auditevents?principal=alice&after=2026-01-01T17%3A02%3A00%2B07%3A00&type=AUTHENTICATION_FAILURE
```

Nếu ghép dấu cộng thô rồi gửi qua lớp giải mã coi nó là khoảng trắng, chuỗi thời gian sẽ sai và có thể trả `400`. Đây là lỗi biểu diễn trên đường truyền, không phải lỗi quy đổi UTC.

### 7.2. Dấu cộng trong principal

Tài khoản mẫu `ops+night@example.com` cũng cần giữ nguyên dấu cộng:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=ops+night@example.com"
```

Kết quả là E6. Giá trị mã hóa của principal này là `ops%2Bnight%40example.com`.

Lỗi ở principal có thể âm thầm tạo kết quả rỗng: máy chủ tìm `ops night@example.com` thay vì chủ thể có dấu cộng. Không phải mọi lỗi mã hóa đều trả `400`.

### 7.3. Dùng công cụ mã hóa một lần

`--get` đưa các dữ liệu được chỉ định thành query string của yêu cầu GET. `--data-urlencode` mã hóa giá trị trước khi đưa vào URL. Hai tùy chọn này giúp tránh tự thay thế từng ký tự. Xem [tài liệu curl](https://curl.se/docs/manpage.html#--data-urlencode).

Những nguyên tắc thực hành:

- Đưa giá trị gốc, chưa mã hóa, vào `--data-urlencode`. Không đưa sẵn `%2B` rồi mã hóa thêm lần nữa thành `%252B`.
- Bọc URL trong dấu nháy khi tự viết nhiều tham số để shell không xử lý `&`.
- Không dùng `-X GET` cùng dữ liệu ở request body rồi kỳ vọng nó giống query parameter. Dùng `--get` cho mẫu đang học.
- Với chữ tiếng Việt hoặc ký tự đặc biệt trong principal, dùng UTF-8 và bộ dựng URL phù hợp.
- Không đặt thông tin xác thực hoặc token trong query string; `principal` ở đây là điều kiện tìm sự kiện.

Quy tắc chuyển dấu `+` thành dấu cách và giải mã `%xx` được mô tả tại [Java URLDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html).

## 8. Đọc và chẩn đoán phản hồi đúng lớp

| Quan sát | Cách hiểu và bước kiểm tra |
| --- | --- |
| `200`, có sự kiện | Kiểm tra từng bản ghi có đúng principal, thời gian và type |
| `200`, `events` rỗng | Kiểm tra giá trị chính xác, biên thời gian, offset, mã hóa và dữ liệu repository còn giữ |
| `400` | Xem tham số không chuyển đổi được, đặc biệt `after` |
| `401` trong API có xác thực | Kiểm tra việc cung cấp thông tin xác thực hợp lệ theo cấu hình |
| `403` trong API có phân quyền | Kiểm tra quyền đọc endpoint; đổi principal lọc không tự cấp thêm quyền |
| `404` | Kiểm tra đúng host/cổng/base path, endpoint được expose và bean repository; không diễn giải thành không có sự kiện |
| `5xx` | Kiểm tra lỗi máy chủ hoặc repository; không đổi lỗi đọc thành một lịch sử rỗng |

Mã và nội dung lỗi cụ thể có thể còn chịu ảnh hưởng của proxy, cơ chế đăng nhập hoặc xử lý lỗi tùy chỉnh. Bảng tập trung vào cách phân loại khi điều tra, không quy định một JSON lỗi cố định cho mọi hệ thống.

Ví dụ kiểm tra thời gian sai:

```powershell
curl.exe --include --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "after=not-a-time"
```

Với ứng dụng mẫu, mã phản hồi là `400`. Một tham số được đặt tên đúng nhưng không chuyển đổi được khác với một truy vấn hợp lệ không tìm thấy bản ghi. Quy tắc lỗi chuyển đổi của Actuator được mô tả trong [Web Endpoint Response Status](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status).

## 9. Tạo URL bằng một chương trình Java chạy độc lập

Khi viết công cụ tra cứu, không nên nối trực tiếp dữ liệu nhập vào sau dấu `=`. Chương trình dưới tạo chính URL của truy vấn kết hợp, mã hóa từng tên/giá trị riêng và xác nhận mốc giờ tương đương UTC.

Tệp `BuildAuditQuery.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class BuildAuditQuery {
    public static void main(String[] args) {
        Map<String, String> parameters = new LinkedHashMap<>();
        parameters.put("principal", "alice");
        parameters.put("after", "2026-01-01T17:02:00+07:00");
        parameters.put("type", "AUTHENTICATION_FAILURE");

        String query = parameters.entrySet().stream()
                .map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
                .collect(Collectors.joining("&"));

        URI uri = URI.create(
                "http://127.0.0.1:18084/actuator/auditevents?" + query);
        System.out.println("afterInstant="
                + OffsetDateTime.parse(parameters.get("after")).toInstant());
        System.out.println(uri);
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```powershell
javac --release 17 BuildAuditQuery.java
java BuildAuditQuery
```

Stdout chính xác:

```text
afterInstant=2026-01-01T10:02:00Z
http://127.0.0.1:18084/actuator/auditevents?principal=alice&after=2026-01-01T17%3A02%3A00%2B07%3A00&type=AUTHENTICATION_FAILURE
```

Chương trình chỉ dựng URL, không gửi HTTP nên chạy được độc lập với server. Có thể dùng URL được in ra để gửi yêu cầu khi ứng dụng mẫu đang chạy.

`URLEncoder` dùng quy tắc `application/x-www-form-urlencoded`, phù hợp khi mã hóa các giá trị query được giải mã theo quy tắc này. Ở đây nó được áp dụng cho từng thành phần, không phải cho toàn bộ URL. Mã hóa nguyên URL sẽ làm biến dạng các dấu phân cách như `:`, `/`, `?` và `&`.

`LinkedHashMap` chỉ giúp thứ tự tham số được in ra ổn định; máy chủ không yêu cầu đúng thứ tự đó. Việc chỉ định `StandardCharsets.UTF_8` tránh phụ thuộc bảng mã mặc định của máy. Xem [Java URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html).

## 10. Gọi trực tiếp repository khi đã ở trong ứng dụng

Nếu đã có bean repository trong một thành phần Spring, không nhất thiết tự gọi HTTP về chính ứng dụng chỉ để lọc cùng dữ liệu.

Đoạn mã tích hợp minh họa, giả sử biến `repository` đã được tiêm và có kiểu `AuditEventRepository`:

```java
Instant after = OffsetDateTime.parse("2026-01-01T17:02:00+07:00").toInstant();

List<AuditEvent> result = repository.find(
        "alice",
        after,
        "AUTHENTICATION_FAILURE");
```

Các kiểu cần import là `java.time.Instant`, `java.time.OffsetDateTime`, `java.util.List`, `org.springframework.boot.actuate.audit.AuditEvent` và `AuditEventRepository` trong cùng package audit. Đoạn này không phải chương trình độc lập.

Với bộ dữ liệu mẫu, kết quả chỉ có E5. Nếu muốn không lọc principal ở tầng Java, truyền `null` vào tham số đầu; không truyền chuỗi `"null"`.

Gọi trực tiếp tránh bước URL và HTTP nhưng không thay thế việc phân quyền ở dịch vụ sử dụng dữ liệu. Nếu một API nghiệp vụ cho phép người dùng gửi principal tùy ý rồi gọi repository, dịch vụ đó vẫn phải kiểm tra quyền và phạm vi dữ liệu được xem.

## 11. Những giới hạn cần biết trước khi dùng để điều tra liên tục

### 11.1. Principal lọc dữ liệu không phải người đang đăng nhập

`principal=alice` nghĩa là tìm những sự kiện có principal được lưu là `alice`. Nó không yêu cầu người gửi HTTP phải chính là alice và không tự giới hạn kết quả theo danh tính đang đăng nhập.

Ví dụ, người vận hành được cấp quyền kiểm toán có thể có nhu cầu tra cứu sự kiện của nhiều tài khoản. Ngược lại, một người dùng thông thường không được phép xem dữ liệu của người khác chỉ vì biết cách đổi query parameter.

Với hệ thống nhiều tenant, ba bộ lọc của endpoint không tự tạo ranh giới tenant. Cần thực thi ranh giới đó ở thiết kế quyền và tầng truy vấn phù hợp.

### 11.2. Không có hợp đồng OR, phân trang hoặc khoảng thời gian hai đầu

Các cách viết sau không có nghĩa như nhiều người suy đoán:

| Cách viết | Suy đoán sai |
| --- | --- |
| `type=A,B` | Tự động tìm loại A hoặc B |
| `type=A&type=B` | Tự động tạo điều kiện OR |
| `principal=ali*` | Tìm mọi principal bắt đầu bằng ali |
| `before=...` | Tự động giới hạn mốc trên |
| `page=0&size=20` | Tự động có phân trang kiểu Spring Data |
| `sort=timestamp,asc` | Tự động sắp xếp tăng dần |

Trong bộ dữ liệu mẫu, `type=AUTHENTICATION_FAILURE,AUTHORIZATION_FAILURE` được xem là một giá trị chuỗi và không khớp sự kiện nào. Với tham số lặp, không dựa vào cách một phiên bản xử lý danh sách để suy ra hỗ trợ OR.

Tham số không được endpoint sử dụng cũng không nhất thiết gây lỗi. Với Spring Boot 3.3.13 của bài, thêm riêng `before=2026-01-01T10:02:00Z` vẫn trả sáu sự kiện: mốc trên đã không được áp dụng. Vì vậy, HTTP `200` không chứng minh một tham số tự đặt đã có hiệu lực.

Nếu cần hợp đồng tìm kiếm mở rộng, thiết kế API tra cứu có tài liệu và kiểm chứng riêng. Lọc tiếp ở client chỉ áp dụng lên dữ liệu đã được trả về, không bảo đảm truy xuất được phần lịch sử chưa nhận hoặc đã bị loại khỏi kho.

### 11.3. after không phải con trỏ đọc không bỏ sót

E5 và E6 cùng timestamp `10:04:00Z`. Giả sử một lần đọc chỉ thấy E5 và client ghi nhớ mốc này. Sau đó E6 mới được thêm vào kho với cùng timestamp. Lần đọc kế tiếp dùng `after=10:04:00Z` sẽ loại E6.

Một sự kiện đến muộn với timestamp nhỏ hơn mốc đã ghi nhớ cũng có thể bị bỏ qua. Không được quảng bá việc thăm dò endpoint bằng timestamp là luồng chuyển sự kiện đầy đủ.

Cửa sổ đọc chồng lấn có thể giảm nguy cơ, nhưng cần định danh ổn định để loại trùng và quy tắc xử lý sự kiện đến muộn. `data.ref` trong ví dụ không phải bảo đảm định danh của mọi sự kiện Actuator.

Nếu yêu cầu là xuất toàn bộ lịch sử một cách tin cậy, cần kho và giao thức đọc hỗ trợ thứ tự, con trỏ, phân trang và việc nhận trùng phù hợp. Đây là yêu cầu bổ sung ngoài ba tham số của bài.

### 11.4. Bộ lọc không quyết định thời hạn lưu

Repository trong bộ nhớ chỉ giữ dữ liệu của tiến trình và dung lượng đã chọn. Việc truy vấn đúng không làm nó thành kho lịch sử bền vững. Khởi động lại ứng dụng mẫu sẽ tạo lại sáu sự kiện từ mã khởi tạo, chứ không chứng minh dữ liệu cũ được phục hồi.

Với nhiều bản sao ứng dụng giữ repository riêng, các lần đọc qua bộ cân bằng tải có thể nhận các tập sự kiện khác nhau. Khi phân tích kết quả, cần biết truy vấn đang đọc kho nào và kho giữ được những dữ liệu nào.

Không dùng `events=[]` làm kết luận chắc chắn “không có sự cố”. Cần kiểm tra cả độ bao phủ của nguồn phát, thời hạn giữ và khả năng đọc kho.

## 12. Tự kiểm tra bằng kết quả dự đoán

Đối chiếu theo tập `data.ref`, không phụ thuộc thứ tự JSON:

| Điều kiện | Kết quả với dữ liệu mẫu |
| --- | --- |
| Không tham số | E1, E2, E3, E4, E5, E6 |
| `principal=alice` | E1, E2, E4, E5 |
| `after=2026-01-01T10:02:00Z` | E4, E5, E6 |
| `type=AUTHENTICATION_FAILURE` | E2, E3, E5, E6 |
| Ba điều kiện: alice, sau 10:02Z, xác thực thất bại | E5 |
| Ba điều kiện trên, đổi mốc thành 10:04Z | Rỗng |
| Đổi 10:02Z thành 17:02+07:00, mã hóa đúng | E5 |
| `principal=ops+night@example.com`, mã hóa đúng | E6 |
| `principal=Alice` | Rỗng trong repository mẫu |
| `principal=null` | Rỗng; đang tìm chuỗi `null` |
| `after=not-a-time` | HTTP 400 |
| `after=2026-01-01T10:02:00` thiếu offset | HTTP 400 |

**Bài tập 1:** Chỉ dùng principal và type, hãy tìm mọi lần xác thực thất bại của alice trong kho.

**Đáp án:** bỏ `after`, giữ `principal=alice` và `type=AUTHENTICATION_FAILURE`. Kết quả là E2, E5. Không gửi `after=null`.

**Bài tập 2:** Muốn các lần xác thực thất bại của bất kỳ chủ thể nào sau `10:01Z`, cần truyền tham số nào?

**Đáp án:** `after=2026-01-01T10:01:00Z` và `type=AUTHENTICATION_FAILURE`; bỏ principal. Kết quả là E3, E5, E6. E2 bị loại tại biên.

**Bài tập 3:** Đổi timestamp của E6 thành `2026-01-01T17:04:00+07:00` nhưng vẫn biểu diễn cùng thời điểm. Kết quả truy vấn theo thời gian có nên đổi không?

**Đáp án:** không nếu dữ liệu được chuyển đổi đúng về thời điểm. Mốc mới tương đương `10:04:00Z`. Với mã khởi tạo dùng `Instant.parse`, hãy dùng `OffsetDateTime.parse(...).toInstant()` nếu muốn thể hiện rõ bước nhận chuỗi có offset rồi chuyển sang Instant.

**Bài tập 4:** Một yêu cầu trả `200` khi gửi thêm `size=10`. Có thể kết luận endpoint chỉ trả tối đa mười sự kiện không?

**Đáp án:** không. Cần kiểm tra hợp đồng tham số và kết quả thực tế; mã thành công không xác nhận một tham số ngoài hợp đồng đã được áp dụng.

Khi sử dụng `auditevents`, hãy diễn đạt được truy vấn bằng một câu rõ ràng: đang tìm sự kiện của ai, sau mốc thời gian nào, với loại nào. Sau đó đối chiếu điều kiện, cách mã hóa và phạm vi dữ liệu repository thực sự đang giữ trước khi đưa ra kết luận.
