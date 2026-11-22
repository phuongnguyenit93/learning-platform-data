# Vai trò của AuditEvent và AuditEventRepository

## 1. Từ một thao tác nghiệp vụ đến bằng chứng kiểm toán

Giả sử một người vận hành thay đổi quyền truy cập của người dùng khác. Khi cần kiểm tra lại, câu hỏi không chỉ là “API trả về mã gì?” mà còn là:

- Ai thực hiện thao tác?
- Thao tác gì đã xảy ra?
- Thời điểm nào?
- Đối tượng nào bị tác động và kết quả ra sao?

Một dòng access log chứa `POST /permissions -> 200` có thể giúp tìm lần gọi HTTP, nhưng chưa mô tả đầy đủ ý nghĩa nghiệp vụ. Chúng ta cần một sự kiện có cấu trúc, rồi cần nơi tiếp nhận và truy vấn những sự kiện đó.

Trong Spring Boot Actuator:

- **`AuditEvent` là dữ liệu mô tả một sự kiện kiểm toán.**
- **`AuditEventRepository` là hợp đồng để thêm và tìm các sự kiện kiểm toán.**

Hai vai trò này tách biệt. Tạo một đối tượng sự kiện chưa có nghĩa đã lưu; có một repository cũng không có nghĩa ứng dụng đã tự biết mọi hành động cần kiểm toán.

Bài dùng API Spring Boot **3.3.x**. Cơ chế auditing của Actuator hỗ trợ các sự kiện bảo mật và sự kiện nghiệp vụ do ứng dụng công bố. [Spring Boot 3.3: Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

## 2. AuditEvent: mô tả điều đã xảy ra

### Bốn thành phần chính

| Thành phần | Kiểu dữ liệu Java | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| `timestamp` | `Instant` | Thời điểm sự kiện được ghi nhận theo cách tạo đối tượng | `2024-01-01T00:00:00Z` |
| `principal` | `String` | Tên chủ thể liên quan đến sự kiện | `operator-1` |
| `type` | `String` | Loại sự kiện | `ROLE_GRANTED` |
| `data` | `Map<String, Object>` | Thông tin bổ sung có cấu trúc | Đối tượng, quyền được cấp, kết quả, mã liên kết |

`principal` ở đây là một **chuỗi tên**, không phải toàn bộ đối tượng `Authentication`, danh sách credential hoặc một cơ chế xác thực mới.

`type` cũng là chuỗi. Các loại sự kiện nghiệp vụ cần quy ước rõ, ổn định và phân biệt được ý nghĩa. Ví dụ `ROLE_CHANGE_REQUESTED` mô tả yêu cầu thay đổi; `ROLE_GRANTED` nên thể hiện việc cấp quyền đã đạt trạng thái thành công mà hệ thống muốn xác nhận. Hai tên không nên được dùng lẫn lộn.

### Tạo sự kiện với timestamp rõ ràng

Đoạn Java minh họa, sử dụng các lớp của Actuator:

```java
AuditEvent event = new AuditEvent(
        Instant.parse("2024-01-01T00:00:00Z"),
        "operator-1",
        "ROLE_GRANTED",
        Map.of(
                "target", "user-7",
                "role", "REPORT_READER",
                "outcome", "SUCCESS",
                "eventId", "audit-demo-001"));
```

Đây là một đoạn mã tạo đối tượng, chưa phải chương trình độc lập và chưa có thao tác lưu.

Constructor nhận timestamp giúp tái lập thí nghiệm hoặc biểu diễn mốc sự kiện đã xác định. Các constructor không nhận timestamp dùng thời điểm tạo sự kiện. Không mặc định `timestamp` là thời điểm cơ sở dữ liệu đã xác nhận giao dịch (commit) hoặc thời điểm một hệ thống bên ngoài thực sự hoàn tất công việc.

Dữ liệu bổ sung cần giải thích được sự kiện, nhưng không nên trở thành bản sao của mọi đối tượng ứng dụng. Với một lần thay đổi quyền, tên quyền và mã đối tượng thường hữu ích hơn việc nhét toàn bộ hồ sơ người dùng vào `data`.

### AuditEvent không tự bảo đảm những gì?

Một đối tượng có các trường kiểm toán không tự:

- Xác thực rằng người ghi đúng là `principal` đã nêu.
- Kiểm chứng rằng thao tác nghiệp vụ thực sự thành công.
- Ghi vào cơ sở dữ liệu hoặc xuất ra hệ thống lưu trữ.
- Phát sinh định danh sự kiện duy nhất.
- Chống sửa/xóa dữ liệu trong toàn bộ vòng đời.
- Tạo ra một sự kiện kiểm toán cho mọi API.

Vì vậy, lấy tên chủ thể từ ngữ cảnh xác thực đáng tin cậy và phát sinh sự kiện ở đúng điểm nghiệp vụ là trách nhiệm của ứng dụng. Không tin một trường `actor` do client tự gửi rồi dùng nguyên nó như bằng chứng ai đã thực hiện thao tác.

### Cẩn thận với dữ liệu có thể thay đổi

Trong phần triển khai Spring Boot 3.3.0 được kiểm chứng ở bài, `data` được bọc thành một map không cho sửa qua `getData()`. Điều này không đồng nghĩa đã sao chép sâu toàn bộ map nguồn và các đối tượng lồng bên trong.

Nếu giữ lại một map nguồn có thể thay đổi, hoặc đặt entity/list có thể thay đổi vào đó, nội dung nhìn thấy sau này có thể khác thời điểm tạo sự kiện.

Ưu tiên các giá trị đơn giản và một ảnh chụp dữ liệu ổn định. `Map.of(...)` trong ví dụ dùng các chuỗi có sẵn, giúp tránh việc vô tình sửa lại map. Nếu dùng `Map.copyOf`, nhớ rằng đó vẫn không phải một phép sao chép sâu mọi đối tượng lồng bên trong.

## 3. AuditEventRepository: hợp đồng ghi và tìm

Giao diện trung tâm có hai thao tác:

```java
void add(AuditEvent event);

List<AuditEvent> find(String principal, Instant after, String type);
```

Đây là chữ ký để hiểu API, không phải một lớp repository hoàn chỉnh. Giao diện nằm trong package `org.springframework.boot.actuate.audit`.

### add nhận sự kiện để phần triển khai lưu theo hợp đồng của nó

Ví dụ:

```java
repository.add(event);
```

`AuditEventRepository` che đi chi tiết lưu trữ để nơi tạo sự kiện không cần biết phía sau là bộ nhớ, cơ sở dữ liệu hay một cơ chế được thiết kế riêng.

Tuy nhiên, cùng một chữ ký `add` không có nghĩa mọi phần triển khai có cùng độ bền dữ liệu. Một repository trong bộ nhớ nhận sự kiện khác với một phần triển khai đã ghi thành công vào kho bền vững theo cam kết của nó.

Kiểu trả về `void` cũng không phải một cam kết tự động rằng sự kiện đã được nhân bản, sao lưu hoặc chỉ xuất hiện đúng một lần.

### find lọc theo ba điều kiện

| Tham số | Khi có giá trị | Khi là `null` |
| --- | --- | --- |
| `principal` | Lọc theo tên chủ thể | Không hạn chế theo chủ thể |
| `after` | Chọn các sự kiện sau mốc thời gian đã cho | Không hạn chế theo mốc này |
| `type` | Lọc theo loại sự kiện | Không hạn chế theo loại |

Các điều kiện có giá trị được kết hợp với nhau. Ví dụ:

```java
repository.find(
        "operator-1",
        Instant.parse("2024-01-01T00:00:00Z"),
        "ROLE_GRANTED");
```

Truy vấn này tìm các sự kiện đúng chủ thể, đúng loại và nằm sau mốc đã cho, trong tập dữ liệu phần triển khai đang có. Ngữ nghĩa của các tham số được mô tả trong [API AuditEventRepository](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html); chữ ký tương ứng đã được đối chiếu trực tiếp trên thư viện 3.3.0 dùng trong thí nghiệm.

Với `InMemoryAuditEventRepository` được kiểm chứng dưới đây, `after` là điều kiện **sau nghiêm ngặt**: sự kiện có timestamp bằng đúng mốc bị loại. Không diễn giải nó thành `timestamp >= after`.

`null` ở tham số principal nghĩa là “không lọc theo chủ thể”, không phải “chỉ tìm các sự kiện của người dùng vô danh”.

### Đây không phải giao diện CRUD hoặc bộ phân quyền

Không gọi `save`, `findAll` hay các phương thức của Spring Data rồi mặc định chúng thuộc `AuditEventRepository`. Giao diện chuẩn này chỉ nêu hai thao tác trên; nó không mặc định cung cấp phân trang, cập nhật, xóa hoặc tìm theo mã đối tượng trong `data`.

Tham số `principal` là **điều kiện truy vấn dữ liệu**, không xác thực người đang gọi truy vấn. Một người có quyền gọi `find(null, null, null)` có thể nhận mọi sự kiện còn giữ theo phần triển khai. Quyền đọc và ranh giới dữ liệu cần được kiểm soát ở lớp sử dụng.

Cũng không nên dựa vào một thứ tự sắp xếp chung nếu hợp đồng phần triển khai chưa quy định. Khi cần phân trang hoặc thứ tự bền vững, hãy thiết kế API và kho lưu tương ứng.

## 4. Hai đường đưa sự kiện vào repository

### Đường trực tiếp

```text
Mã nghiệp vụ
    -> tạo AuditEvent
    -> gọi AuditEventRepository.add
    -> phần triển khai tiếp nhận/lưu
```

Cách này dễ nhìn thấy: lớp nghiệp vụ hoặc một dịch vụ chuyên trách kiểm toán nhận repository qua cơ chế tiêm phụ thuộc (dependency injection), rồi gọi `add`.

Ưu điểm là đường ghi rõ ràng. Đổi lại, nơi gọi cần có chính sách xử lý lỗi ghi, lựa chọn thời điểm ghi và hiểu việc ghi này có ràng buộc giao dịch nào với nghiệp vụ hay không.

### Đường qua sự kiện ứng dụng

```text
Mã nghiệp vụ hoặc bộ chuyển sự kiện bảo mật
    -> AuditApplicationEvent bọc AuditEvent
    -> ApplicationEventPublisher
    -> AuditListener
    -> AuditEventRepository.add
```

`AuditApplicationEvent` là lớp sự kiện dùng cho cơ chế sự kiện của Spring. Nó bọc `AuditEvent`, còn `AuditListener` mặc định nhận loại sự kiện đó và chuyển dữ liệu tới repository.

Ví dụ một đoạn công bố sự kiện trong ứng dụng đã có hạ tầng auditing phù hợp:

```java
publisher.publishEvent(new AuditApplicationEvent(event));
```

Đừng mặc định `publisher.publishEvent(event)` với `event` chỉ là một `AuditEvent` sẽ đi qua đúng listener mặc định. Spring có thể phát nó như một payload ứng dụng, nhưng listener nhận `AuditApplicationEvent` không tự trở thành listener của mọi kiểu dữ liệu.

Spring Boot hướng dẫn cả cách dùng repository trực tiếp lẫn công bố `AuditApplicationEvent` cho sự kiện nghiệp vụ. [Hướng dẫn custom auditing của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html#actuator.auditing.custom).

### Công bố sự kiện khác với lưu bền vững

Cơ chế sự kiện trong `ApplicationContext` là đường giao tiếp trong ứng dụng, không tự trở thành một hệ thống thông điệp bền vững. Với bộ phân phối sự kiện mặc định, listener được gọi đồng bộ trên luồng phát sự kiện; nếu thay cơ chế phân phối hoặc chuyển sang bất đồng bộ, phải đánh giá lại cách xử lý lỗi và thời điểm hoàn tất. [Spring Framework: Application events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).

Không vừa gọi `repository.add(event)` vừa công bố wrapper cho cùng sự kiện qua listener đó, trừ khi đã chủ đích xử lý hai đường ghi. Nếu không, một thao tác có thể thành hai bản ghi. Giao diện repository không cung cấp cơ chế tự loại trùng theo `eventId`.

## 5. Thí nghiệm thứ nhất: tạo, lưu, tìm và giới hạn bộ đệm

### Dự án thử

Hai chương trình trong bài là các chương trình Java có `main`, không mở máy chủ HTTP. Chúng dùng Spring Boot 3.3.0 và Spring Framework tương ứng để có kết quả kiểm chứng được với Java 17 trở lên.

Tạo `pom.xml` trong một thư mục thử riêng:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>audit-roles-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
    </dependencies>
</project>
```

Lưu chương trình thứ nhất tại `src/main/java/AuditRepositoryDemo.java`:

```java
import java.time.Instant;
import java.util.Map;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;

public class AuditRepositoryDemo {
    private static final Instant BASE = Instant.parse("2024-01-01T00:00:00Z");

    public static void main(String[] args) {
        AuditEventRepository repository = new InMemoryAuditEventRepository(3);
        AuditEvent first = event(0, "operator-1", "LIMIT_CHANGED");

        System.out.println("before.add=" + repository.find(null, null, null).size());
        repository.add(first);
        System.out.println("after.add=" + repository.find(null, null, null).size());
        System.out.println("first.type=" + first.getType());
        System.out.println("first.target=" + first.getData().get("target"));

        repository.add(event(1, "user-2", "AUTHENTICATION_FAILURE"));
        repository.add(event(2, "operator-1", "LIMIT_CHANGED"));

        System.out.println("all=" + repository.find(null, null, null).size());
        System.out.println("operator.limitChanges="
                + repository.find("operator-1", null, "LIMIT_CHANGED").size());
        System.out.println("after.t1="
                + repository.find(null, BASE.plusSeconds(1), null).size());
        System.out.println("after.t2.strict="
                + repository.find("operator-1", BASE.plusSeconds(2), "LIMIT_CHANGED").size());

        repository.add(event(3, "operator-1", "LIMIT_CHANGED"));
        System.out.println("after.overflow=" + repository.find(null, null, null).size());
        boolean oldestRetained = repository.find(null, null, null).stream()
                .anyMatch(item -> item.getTimestamp().equals(BASE));
        System.out.println("oldest.retained=" + oldestRetained);
        System.out.println("fresh.repository="
                + new InMemoryAuditEventRepository(3).find(null, null, null).size());
    }

    private static AuditEvent event(long seconds, String actor, String type) {
        return new AuditEvent(BASE.plusSeconds(seconds), actor, type,
                Map.of("target", "account-42", "eventId", "audit-" + seconds));
    }
}
```

Biên dịch và gom dependency bằng Maven:

```bash
mvn -q compile dependency:copy-dependencies
```

Chạy trên Windows PowerShell:

```powershell
java -cp 'target/classes;target/dependency/*' AuditRepositoryDemo
```

Trên Linux/macOS:

```bash
java -cp 'target/classes:target/dependency/*' AuditRepositoryDemo
```

Dependency cần được tải nếu cache chưa có. Các định danh và thao tác trong ví dụ đều là dữ liệu tổng hợp; không có thay đổi hạn mức thật.

Stdout chính xác:

```text
before.add=0
after.add=1
first.type=LIMIT_CHANGED
first.target=account-42
all=3
operator.limitChanges=2
after.t1=1
after.t2.strict=0
after.overflow=3
oldest.retained=false
fresh.repository=0
```

### Điều ví dụ chứng minh

1. Sau khi tạo `first`, repository vẫn chưa có bản ghi: `before.add=0`.
2. Gọi `add` đưa sự kiện vào kho đang dùng: `after.add=1`.
3. Sự kiện giữ dữ liệu mô tả như loại thao tác và đối tượng.
4. Bộ lọc chủ thể kết hợp loại sự kiện tìm được hai lần `LIMIT_CHANGED`.
5. Khi lọc sau `t1`, chỉ sự kiện tại `t2` còn phù hợp.
6. Sự kiện tại đúng `t2` không được chọn bởi điều kiện “sau `t2`”.
7. Thêm sự kiện thứ tư vào bộ đệm ba chỗ làm sự kiện cũ bị loại.
8. Tạo repository mới tạo ra một kho trong bộ nhớ rỗng.

Không coi kết quả `fresh.repository=0` là kiểm thử một hệ thống lưu bền vững bị khởi động lại. Nó chỉ minh họa rằng trạng thái thuộc về đối tượng repository trong bộ nhớ, không tự nằm ở một kho dùng chung bên ngoài.

## 6. Thí nghiệm thứ hai: wrapper và listener làm việc gì?

Lưu chương trình tiếp theo tại `src/main/java/AuditPublicationDemo.java` trong cùng dự án thử:

```java
import java.time.Instant;
import java.util.Map;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.boot.actuate.audit.listener.AuditListener;
import org.springframework.context.support.GenericApplicationContext;

public class AuditPublicationDemo {
    public static void main(String[] args) {
        var repository = new InMemoryAuditEventRepository(10);

        try (var context = new GenericApplicationContext()) {
            context.addApplicationListener(new AuditListener(repository));
            context.refresh();

            AuditEvent wrapped = new AuditEvent(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    "operator-1", "ROLE_GRANTED",
                    Map.of("target", "user-7", "role", "REPORT_READER"));
            context.publishEvent(new AuditApplicationEvent(wrapped));
            System.out.println("after.wrapper="
                    + repository.find(null, null, null).size());

            AuditEvent plain = new AuditEvent(
                    Instant.parse("2024-01-01T00:00:01Z"),
                    "operator-1", "ROLE_REVOKED",
                    Map.of("target", "user-7", "role", "REPORT_READER"));
            context.publishEvent(plain);
            System.out.println("after.plain="
                    + repository.find(null, null, null).size());

            repository.add(plain);
            System.out.println("after.direct="
                    + repository.find(null, null, null).size());
        }
    }
}
```

Biên dịch lại sau khi thêm tệp. Trên Windows PowerShell:

```powershell
mvn -q compile dependency:copy-dependencies
java -cp 'target/classes;target/dependency/*' AuditPublicationDemo
```

Trên Linux/macOS, đổi dấu phân cách classpath thành `:`.

Stdout chính xác:

```text
after.wrapper=1
after.plain=1
after.direct=2
```

Cách đọc:

- `after.wrapper=1`: listener đã nhận `AuditApplicationEvent` và thêm sự kiện vào repository.
- `after.plain=1`: công bố riêng `AuditEvent` không làm listener đang đăng ký nhận nhầm kiểu; số bản ghi không tăng.
- `after.direct=2`: gọi repository trực tiếp vẫn lưu được sự kiện thứ hai.

Chương trình chủ động tạo `GenericApplicationContext` và đăng ký `AuditListener` để nhìn rõ cơ chế. Nó không chạy cơ chế tự cấu hình của Spring Boot và không mô phỏng một lần đăng nhập thực tế.

Trong ứng dụng Boot có auditing tự cấu hình phù hợp, không đăng ký thêm một listener giống hệt chỉ vì ví dụ có `addApplicationListener`: cần kiểm tra bean hiện hữu để tránh hai listener cùng ghi một sự kiện.

Ví dụ cũng không khẳng định mọi `AuditEvent` được công bố riêng sẽ luôn bị bỏ qua trong mọi ứng dụng. Nếu ứng dụng tự có listener cho kiểu đó, hành vi phụ thuộc listener ấy. Kết luận ở đây là **đúng kiểu wrapper mới khớp với listener mặc định đang minh họa**.

## 7. Gắn repository vào ứng dụng Spring Boot

Một cấu hình phục vụ phát triển có thể khai báo bean:

```java
package example.audit;

import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditStorageConfiguration {

    @Bean
    AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(200);
    }
}
```

Đây là đoạn cấu hình bổ sung vào ứng dụng, không phải tệp cần thêm vào dự án `main` của hai thí nghiệm.

Bean repository cung cấp nơi nhận sự kiện cho hạ tầng auditing tương ứng. Khi Spring Security và cơ chế auditing được cấu hình phù hợp, các sự kiện như xác thực thành công/thất bại hoặc bị từ chối truy cập có thể được chuyển thành sự kiện kiểm toán.

Điều đó không có nghĩa mọi HTTP 401/403 đều tự có cùng một bản ghi kiểm toán. Cần kiểm tra điểm từ chối, cơ chế xác thực/phân quyền và đường phát sự kiện thực tế.

Các thao tác nghiệp vụ như cấp quyền báo cáo, xuất dữ liệu hoặc xác nhận thay đổi vẫn cần được ứng dụng phát sinh đúng ý nghĩa. Hạ tầng không tự hiểu rằng một method hoặc một URL tương ứng với sự kiện nghiệp vụ nào.

### Repository và endpoint có vai trò khác nhau

Nếu bật và expose endpoint `auditevents`, endpoint cung cấp đường đọc các sự kiện từ repository. Nó không thay thế việc tạo hoặc ghi sự kiện.

Quyền đọc endpoint phải được kiểm soát riêng. Việc một sự kiện có `principal=operator-1` không có nghĩa chỉ người dùng ấy mới xem được nó; đó là dữ liệu của sự kiện, không phải quy tắc truy cập.

Trong hệ thống nhiều đơn vị/khách hàng, các ranh giới dữ liệu cũng cần được thiết kế rõ. Không dùng một tham số lọc do client tùy ý chọn làm cơ chế phân quyền.

## 8. Chọn phần triển khai theo trách nhiệm lưu giữ

### Repository trong bộ nhớ

`InMemoryAuditEventRepository` thuận tiện để học, kiểm tra luồng sự kiện và chẩn đoán trong phát triển. Nó giữ một tập có sức chứa giới hạn trong tiến trình.

Hệ quả:

- Khởi động lại làm mất trạng thái của tiến trình.
- Mỗi instance có kho riêng.
- Vượt sức chứa thì các sự kiện cũ không còn.
- Giới hạn số bản ghi không đồng nghĩa giới hạn byte hoặc số ngày.
- Không có sẵn một lịch sử bền vững, chống sửa/xóa cho toàn hệ thống.

Spring khuyến nghị giải pháp repository khác theo yêu cầu môi trường vận hành thay vì dựa vào phần triển khai trong bộ nhớ cho môi trường vận hành. Không đánh giá mức đầy đủ của kiểm toán chỉ bằng việc endpoint hiện đang trả vài bản ghi.

### Repository tùy biến cần thêm hợp đồng vận hành

Nếu triển khai bằng cơ sở dữ liệu hoặc kho tập trung, cần xác định:

| Trách nhiệm | Câu hỏi cần giải quyết |
| --- | --- |
| Ghi dữ liệu | Khi nào một lần `add` được xem là đã tiếp nhận thành công? |
| Độ bền | Dữ liệu còn khi ứng dụng/instance kết thúc không? |
| Lỗi ghi | Cho phép nghiệp vụ tiếp tục, chặn thao tác hay chuyển qua cơ chế phục hồi nào? |
| Loại trùng | Nếu cùng sự kiện được gửi lại, nhận diện bằng khóa nào? |
| Truy vấn | Hỗ trợ các bộ lọc, thứ tự, giới hạn kết quả và phạm vi dữ liệu ra sao? |
| Vòng đời | Ai được đọc, dữ liệu giữ bao lâu và xóa theo quy trình nào? |
| Tính toàn vẹn | Ai có thể sửa/xóa; có cần biện pháp phát hiện can thiệp không? |

Giao diện `AuditEventRepository` là điểm nối để thay phần triển khai, không phải toàn bộ thiết kế đáp ứng các yêu cầu trên.

Timestamp không phải khóa duy nhất. Nhiều sự kiện có thể cùng mốc thời gian; riêng `after` không đủ làm cơ chế đọc tiếp chính xác một lần cho mọi kho dữ liệu. Nếu cần truyền/đồng bộ có mốc đọc tiếp, phải thiết kế định danh và thứ tự phù hợp.

## 9. Thời điểm nghiệp vụ và dữ liệu kiểm toán phải khớp nhau

Giả sử ứng dụng ghi `ROLE_GRANTED` trước khi giao dịch thay đổi quyền được xác nhận, rồi giao dịch bị hoàn tác (rollback). Repository độc lập có thể vẫn giữ sự kiện mô tả một thay đổi chưa thực sự thành công.

Ngược lại, nếu chỉ ghi sau khi nghiệp vụ hoàn tất mà tiến trình chết trước khi ghi kiểm toán, có thể thiếu sự kiện. Hai lớp `AuditEvent` và `AuditEventRepository` không tự giải quyết khoảng trống này.

Cần phân biệt sự kiện “đã yêu cầu”, “đã thử”, “đã thành công” và “đã thất bại”, rồi chọn ràng buộc giao dịch hoặc cơ chế lưu/chuyển tiếp phù hợp. Spring có listener gắn với giai đoạn giao dịch, nhưng việc chọn cơ chế đó là một thiết kế riêng; listener auditing mặc định không tự có mọi cam kết `AFTER_COMMIT` mà nghiệp vụ cần. [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Cũng không đặt một lời ghi “thành công” chỉ dựa vào HTTP 200. Một API có thể trả lời đã nhận yêu cầu trong khi công việc bất đồng bộ còn chưa chạy xong.

## 10. Giữ dữ liệu kiểm toán hữu ích và có kiểm soát

Một sự kiện tốt giúp trả lời câu hỏi mà không giữ thừa dữ liệu nhạy cảm:

- Chọn mã đối tượng, tên hành động và kết quả rõ ràng.
- Dùng mã liên kết để tra cứu khi cần, thay vì sao chép toàn bộ request.
- Không lưu mật khẩu, bearer token, cookie phiên hoặc toàn bộ đối tượng xác thực.
- Chỉ giữ các giá trị trước/sau thực sự cần thiết; có quy tắc riêng cho trường nhạy cảm.
- Giới hạn kích thước và hình dạng của `data`, tránh giữ cả đồ thị entity có thể thay đổi.
- Phân biệt danh tính thực hiện thao tác với đối tượng bị tác động.
- Không coi việc gọi `toString()` rồi ghi ra console là một kho kiểm toán hoàn chỉnh.

Đừng nhầm Actuator auditing với tính năng tự điền `createdBy`, `createdDate` của một công nghệ lưu trữ như Spring Data auditing. Một bên mô tả sự kiện; bên kia thường gắn metadata vào bản ghi dữ liệu. Chúng có thể bổ sung cho nhau nhưng không tự thay thế nhau.

## 11. Bài thực hành tự kiểm tra

1. Tạo `new AuditEvent(...)` rồi không gọi repository hoặc công bố wrapper. Repository có tự nhận sự kiện không?
2. Trong một sự kiện cấp quyền, đâu là chủ thể thực hiện, đâu là đối tượng bị tác động?
3. `find(null, null, null)` có nghĩa là chỉ tìm sự kiện vô danh không?
4. Vì sao sự kiện có timestamp bằng mốc `after` bị loại trong thí nghiệm?
5. Vì sao công bố `AuditEvent` riêng không làm số bản ghi tăng trong chương trình thứ hai?
6. Nếu repository chỉ giữ ba sự kiện, một kết quả truy vấn rỗng có chứng minh sự kiện chưa từng xảy ra không?
7. Nếu cần giữ sự kiện qua khởi động lại và không ghi trùng khi gửi lại, những trách nhiệm nào chưa được một repository trong bộ nhớ đáp ứng?

Đối chiếu: tạo đối tượng chưa lưu; principal và target có vai trò khác nhau; `null` trong bộ lọc nghĩa là không hạn chế. Repository trả dữ liệu theo những gì phần triển khai đang giữ, còn ý nghĩa, thời điểm và độ tin cậy của bằng chứng kiểm toán đòi hỏi một đường tạo–ghi–đọc được thiết kế nhất quán.
