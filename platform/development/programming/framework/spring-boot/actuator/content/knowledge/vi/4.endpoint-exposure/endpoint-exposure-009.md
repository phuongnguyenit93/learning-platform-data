# Cấu hình cache.time-to-live cho thao tác đọc đủ điều kiện

## 1. Cache kết quả đọc để giải quyết vấn đề gì?

Một endpoint quản trị có thể phải tổng hợp dữ liệu hoặc tạo một bản báo cáo trước khi trả lời. Nếu nhiều yêu cầu đọc liên tiếp đều thực hiện lại công việc đó, chi phí có thể tăng trong khi người vận hành không cần dữ liệu mới tới từng mili giây.

Cache kết quả cho phép dùng lại bản kết quả đã tạo trong một khoảng thời gian. **Thời gian sống (time to live, TTL)** quy định khoảng thời gian bản kết quả còn được xem là hợp lệ. Đổi lại, người đọc có thể nhận một ảnh chụp cũ trong cửa sổ đó.

Trong Actuator, thuộc tính `cache.time-to-live` cấu hình việc giữ kết quả cho **thao tác đọc đủ điều kiện**. Nó không phải công tắc biến mọi yêu cầu GET trong ứng dụng thành yêu cầu có cache.

Bài viết dùng Spring Boot 3.3.x; chương trình thực nghiệm và các trường hợp đầu vào bên dưới được kiểm tra với Boot 3.3.0 và Java 21.

## 2. Cấu hình đúng endpoint và đúng thời lượng

Ví dụ đặt TTL cho endpoint `beans`:

```properties
management.endpoint.beans.cache.time-to-live=10s
```

Trong YAML:

```yaml
management:
  endpoint:
    beans:
      cache:
        time-to-live: "10s"
```

`management.endpoint` ở đây dùng `endpoint` **số ít**, theo sau là ID cụ thể. Không dùng đường dẫn `/actuator/beans` làm một phần tên thuộc tính. Cấu hình công bố HTTP lại thuộc nhánh khác, chẳng hạn `management.endpoints.web.exposure.include`.

Tài liệu Boot mô tả trường hợp cơ bản là thao tác đọc không có tham số; thuộc tính này đặt thời gian giữ kết quả của endpoint đó. [Cấu hình cache cho endpoint trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.configuring).

| Giá trị minh họa | Ý nghĩa |
| --- | --- |
| `500ms` | Nửa giây |
| `5s` | Năm giây |
| `1m` | Một phút |
| `0ms` | Không giữ lại kết quả bằng cơ chế TTL này |

Nên ghi rõ đơn vị để tránh hiểu nhầm khi chuyển cấu hình hoặc đọc lại sau này. Trong YAML, `"5s"` được đọc thành chuỗi thời lượng; dấu nháy không thuộc giá trị sau khi YAML đã đọc.

Các thuộc tính TTL chuẩn như `management.endpoint.beans.cache.time-to-live` mặc định là `0ms`. Vì vậy, việc một thao tác thuộc loại có thể cache không đồng nghĩa nó đang giữ kết quả với một TTL dương. [Các giá trị mặc định của thuộc tính Actuator 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 2.1. Cấu hình TTL không tự công bố endpoint

Hai dòng sau giải quyết hai việc riêng:

```properties
management.endpoints.web.exposure.include=health,beans
management.endpoint.beans.cache.time-to-live=10s
```

Dòng đầu chọn endpoint để công bố qua HTTP. Dòng sau cấu hình thời gian giữ kết quả đọc đủ điều kiện của `beans`. TTL không tự bật một endpoint đã bị tắt, không bổ sung thư viện còn thiếu và không thay thế quyền truy cập.

### 2.2. Đặt TTL bằng 0 để quan sát dữ liệu mới qua thao tác

```properties
management.endpoint.beans.cache.time-to-live=0ms
```

Cấu hình này không giữ bản kết quả bằng bộ cache TTL của thao tác Actuator. Nó không hứa rằng dữ liệu nguồn bên trong ứng dụng không có một lớp cache khác.

Với cấu hình thông thường của dự án thực nghiệm, giá trị TTL được đọc khi khởi tạo cơ chế endpoint. Sửa tệp nguồn rồi tiếp tục gọi tiến trình cũ không phải cách kiểm tra một cấu hình TTL mới; cần xây dựng lại nếu tệp nằm trong JAR và khởi động lại ứng dụng.

## 3. Hiểu đúng “thao tác đọc đủ điều kiện”

Trường hợp dễ nhận biết nhất là một phương thức `@ReadOperation` không có đầu vào nghiệp vụ. Nếu TTL dương, kết quả có thể được dùng lại cho lời gọi phù hợp trong thời gian còn hiệu lực.

Tuy nhiên, không nên phân loại chỉ bằng hai câu hỏi “có phải GET không?” hoặc “chữ ký Java có bao nhiêu tham số?”. Trong Boot 3.3.0, cơ chế thực thi còn xét tham số bắt buộc, đầu vào thực tế của lời gọi và ngữ cảnh do framework cung cấp.

| Loại thao tác / đầu vào | Hành vi cần hiểu trong Boot 3.3.0 |
| --- | --- |
| `@ReadOperation` không có đầu vào nghiệp vụ | Trường hợp cơ bản có thể cache khi TTL dương |
| Thao tác đọc có tham số nghiệp vụ bắt buộc, như `@Selector String key` | Không được cơ chế này biến thành bộ cache theo từng giá trị key |
| Thao tác đọc có tham số tùy chọn, không truyền giá trị | Có thể dùng cache cho lời gọi không có đầu vào nghiệp vụ |
| Cùng thao tác tùy chọn nhưng đã truyền giá trị | Lời gọi có đầu vào đó đi qua thực thi, không dùng lại bản cache không có đầu vào |
| `@WriteOperation` hoặc `@DeleteOperation` | TTL đọc không lưu kết quả để bỏ qua việc thực hiện lệnh ghi/xóa |

Ví dụ, một thao tác thử nghiệm có tham số `@Nullable String filter` và TTL dương cho kết quả quan sát sau:

```text
GET không truyền filter       → thực hiện phương thức lần 1
GET không truyền filter       → dùng lại kết quả lần 1
GET với filter=blue           → thực hiện phương thức lần 2
GET với filter=blue lần nữa   → thực hiện phương thức lần 3
GET không truyền filter       → vẫn có thể dùng bản cache lần 1 nếu chưa hết TTL
```

Đây là hành vi của cơ chế chuẩn được kiểm tra với Boot 3.3.0, không phải một bộ cache tự tạo khóa theo mọi tổ hợp tham số. Không kết luận rằng thêm `@Nullable` sẽ làm mọi lời gọi có tham số được cache.

### 3.1. Ngữ cảnh người gọi cũng cần được giữ nhất quán khi thử

Cơ chế cache của Boot 3.3.0 còn phân biệt ngữ cảnh như người gọi và phiên bản API Actuator. Do đó, không nên giả định mọi người dùng và mọi dạng lời gọi đều dùng chung duy nhất một mục cache.

Khi thử hiệu lực TTL, giữ nguyên endpoint, người gọi, dạng yêu cầu và đầu vào. Nếu thay các yếu tố đó đồng thời, việc phương thức chạy lại chưa đủ chứng minh TTL không hoạt động. Đặc biệt, cũng không nên khẳng định rằng cứ có xác thực là mọi cache đọc đều bị vô hiệu hóa.

## 4. TTL hoạt động theo yêu cầu, không phải lịch chạy nền

Với một lời gọi đủ điều kiện và cùng ngữ cảnh:

```text
Chưa có kết quả hợp lệ
  → thực hiện thao tác đọc
  → giữ kết quả

Có kết quả còn trong TTL
  → dùng lại kết quả

Kết quả đã hết TTL và có yêu cầu mới
  → thực hiện thao tác đọc để tạo kết quả mới
```

TTL không có nghĩa là framework cứ đúng mỗi N giây lại chạy phương thức. Nếu không có yêu cầu mới sau khi bản kết quả hết hạn, không có lý do từ cơ chế này để tạo báo cáo mới chỉ vì thời gian đã trôi qua.

Trong Boot 3.3.0, dùng lại một kết quả còn hạn không đặt lại mốc tuổi của nó. Đây không phải thời gian hết hạn trượt theo lần đọc cuối.

Ví dụ giả định việc tính toán nhanh, TTL là 5 giây và các lời gọi có cùng ngữ cảnh:

| Mốc tương đối | Sự kiện | Kết quả |
| --- | --- | --- |
| `t=0` | Đọc lần đầu | Tạo bản kết quả A |
| `t=1s` | Đọc lại | Dùng A |
| `t=3s` | Đọc lại | Vẫn dùng A; không kéo dài hạn thêm 5 giây từ mốc này |
| `t=5,5s` | Có yêu cầu đọc tiếp | A đã hết hạn, tạo bản kết quả B |

Các mốc trên minh họa cơ chế, không phải cam kết lập lịch chính xác tới từng mili giây. Không nên thiết kế kiểm tra vận hành dựa vào việc phải đổi kết quả đúng tại ranh giới đồng hồ.

## 5. Thao tác ghi không tự bảo đảm đọc ngay dữ liệu mới

Giả sử lần đọc đầu tạo ảnh chụp giá trị 100 và giữ nó trong 5 giây. Sau đó một POST đổi dữ liệu nguồn thành 200.

Trong cơ chế chuẩn được kiểm tra với Boot 3.3.0, POST không tự xóa bản kết quả đọc đang còn hạn. GET tiếp theo có thể vẫn trả 100 cho đến khi bản cache hết hạn và một lần đọc mới được thực hiện.

```text
Đọc nguồn = 100 → cache ảnh chụp 100
Ghi nguồn = 200 → dữ liệu nguồn đã đổi
Đọc trong TTL  → vẫn có thể nhận ảnh chụp 100
Đọc sau TTL   → tạo ảnh chụp mới từ nguồn 200
```

Vì thế, phải chọn TTL theo yêu cầu về độ mới của dữ liệu. Với thông tin cần xác nhận ngay sau một lệnh quản trị, TTL bằng 0 hoặc một cơ chế xác nhận phù hợp có thể cần thiết. Không mặc nhiên coi GET ngay sau POST là bằng chứng đọc trực tiếp từ nguồn.

## 6. Thực nghiệm với một endpoint tạo ảnh chụp

Dự án dưới đây chạy độc lập bằng Java 21, Gradle 8.5 và Spring Boot 3.3.0. Không thêm Spring Security; máy chủ chỉ lắng nghe trên loopback để thí nghiệm trên máy cá nhân. Lần xây dựng đầu cần tải plugin và thư viện.

`snapshot` có một giá trị nguồn ban đầu bằng 100. Khi phương thức đọc thật sự chạy, nó tăng bộ đếm `sequence` rồi tạo một bản kết quả bất biến. Bộ đếm chỉ phục vụ quan sát số lần tính toán trong thí nghiệm; nó không đại diện cho một lệnh thay đổi dữ liệu nghiệp vụ.

### 6.1. Tạo các tệp

```text
actuator-ttl-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/ttl/
    │   ├── TtlApplication.java
    │   └── SnapshotEndpoint.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-ttl-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'actuator-ttl-demo.jar'
}
```

Tệp `src/main/java/lab/ttl/TtlApplication.java`:

```java
package lab.ttl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TtlApplication {
    public static void main(String[] args) {
        SpringApplication.run(TtlApplication.class, args);
    }
}
```

Tệp `src/main/java/lab/ttl/SnapshotEndpoint.java`:

```java
package lab.ttl;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "snapshot")
public class SnapshotEndpoint {
    private final AtomicInteger sequence = new AtomicInteger();
    private final AtomicInteger value = new AtomicInteger(100);

    @ReadOperation
    public Snapshot read() {
        return new Snapshot(sequence.incrementAndGet(), value.get());
    }

    @WriteOperation
    public void update(int value) {
        this.value.set(value);
    }

    public record Snapshot(int sequence, int value) {
    }
}
```

`read()` không nhận tham số nghiệp vụ và trả về một `record` mới. Khi bộ cache dùng lại record cũ, `sequence` trong JSON không tăng. `update(int value)` thay giá trị nguồn, nhưng không sửa record đã tạo trước đó.

Việc dùng bản kết quả bất biến giúp thí nghiệm tách bạch dữ liệu nguồn với ảnh chụp đã cache. Nếu trả về một đối tượng có thể bị sửa và tiếp tục thay đổi chính đối tượng ấy, việc quan sát dữ liệu cũ/mới sẽ khó diễn giải hơn.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,snapshot
management.endpoint.snapshot.cache.time-to-live=5s
```

Không cần `@EnableCaching`, `@Cacheable`, Redis hay Caffeine để dùng cơ chế cache kết quả thao tác Actuator trong ví dụ này.

### 6.2. Xây dựng và khởi động

Kiểm tra JDK/Gradle, rồi chạy tại thư mục chứa `build.gradle`:

```shell
gradle bootJar
java -jar build/libs/actuator-ttl-demo.jar
```

Giữ tiến trình đó hoạt động. Không mở công cụ tự thăm dò endpoint `snapshot` trước bài thử, vì nó có thể tạo bản cache đầu tiên làm thay đổi số thứ tự quan sát.

### 6.3. Thử chuỗi đọc → ghi → đọc sau TTL

Khối sau dành cho **PowerShell trên Windows**. Sao chép chạy cả khối trong một cửa sổ khác để các lời gọi đầu nằm trong cùng cửa sổ TTL. `curl.exe` tránh trường hợp `curl` là bí danh của PowerShell. Mỗi tùy chọn `-w` thêm ký tự xuống dòng hoặc in mã HTTP.

```powershell
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
curl.exe -sS -o NUL -w "%{http_code}\n" -X POST -H "Content-Type: application/json" "http://127.0.0.1:8080/actuator/snapshot?value=200"
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
Start-Sleep -Seconds 6
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
```

Từ một tiến trình mới, không có lời gọi khác và các lời gọi đầu hoàn thành trước khi TTL 5 giây hết hạn, nội dung kết quả là:

```text
{"sequence":1,"value":100}
{"sequence":1,"value":100}
204
{"sequence":1,"value":100}
{"sequence":2,"value":200}
```

Giải thích từng bước:

1. GET đầu thực thi `read()`, tạo record có `sequence=1`, `value=100`.
2. GET tiếp theo dùng record đó nên số thứ tự vẫn bằng 1.
3. POST cập nhật nguồn thành 200 và trả 204 do phương thức ghi trả `void`.
4. GET trong TTL vẫn dùng record có giá trị 100.
5. Sau khi đợi hơn TTL, GET thực thi `read()` lại, tạo record có số thứ tự 2 và giá trị 200.

Header `Content-Type: application/json` trong POST đáp ứng điều kiện nhận dữ liệu của thao tác ghi; giá trị đơn giản `value` trong ví dụ được truyền qua query string. Đây vẫn là lệnh ghi, không phải thao tác đọc được cache.

Nếu người chạy dừng lâu giữa các lệnh hoặc có công cụ khác gọi endpoint, số thứ tự có thể khác. Khi đó, kiểm tra lại thời điểm và tiến trình trước khi kết luận có lỗi cache.

### 6.4. Đối chiếu với TTL bằng 0

Dừng tiến trình trước bằng Ctrl+C, rồi chạy cùng JAR với tham số ghi đè:

```shell
java -jar build/libs/actuator-ttl-demo.jar --management.endpoint.snapshot.cache.time-to-live=0ms
```

Gọi hai GET liên tiếp:

```powershell
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
```

Từ tiến trình mới và không có lời gọi xen vào:

```text
{"sequence":1,"value":100}
{"sequence":2,"value":100}
```

Giá trị nguồn không đổi nhưng `sequence` tăng, cho thấy phương thức đọc đã được thực hiện hai lần.

## 7. Phạm vi và giới hạn của bộ cache này

| Điều dễ nhầm | Phạm vi đúng |
| --- | --- |
| Cache của browser, proxy hoặc CDN | TTL này thuộc cơ chế thực thi thao tác Actuator ở phía ứng dụng; không phải cấu hình `Cache-Control: max-age` cho mọi phản hồi HTTP |
| Cache nghiệp vụ qua Spring Cache | Đây là cơ chế khác với `@Cacheable` và cấu hình `spring.cache.*` |
| Endpoint `caches` | Không mặc nhiên xem các thao tác quản lý cache nghiệp vụ là lệnh xóa mọi bản kết quả TTL của Actuator |
| Cache dùng chung giữa nhiều bản sao ứng dụng | Mỗi tiến trình/ngữ cảnh ứng dụng có bộ nhớ và bản kết quả riêng; TTL này không tạo kho chia sẻ giữa các máy |
| Khóa chống nhiều lần tính toán đồng thời | Không dùng TTL như bảo đảm rằng mọi yêu cầu đồng thời chỉ làm phương thức chạy đúng một lần |

Ví dụ trong bài gửi các yêu cầu tuần tự. Khi đánh giá tải thực tế, phải xét cả nhiều người gọi, nhiều bản sao ứng dụng và các cache miss cùng lúc. Việc hai yêu cầu tuần tự dùng cùng một bản kết quả không chứng minh toàn bộ hệ thống có đúng một lần tính toán trong mỗi khoảng TTL.

Cache cũng không thay thế kiểm soát truy cập. Một yêu cầu HTTP vẫn đi qua các lớp xử lý bảo mật áp dụng cho ứng dụng; cấu hình TTL không phải cách cho phép người chưa có quyền đọc dữ liệu.

## 8. Chọn TTL và chẩn đoán kết quả không như dự kiến

Cân nhắc đồng thời ba yếu tố: chi phí tạo kết quả, tần suất đọc và mức chậm cập nhật người dùng chấp nhận được. Báo cáo tốn công tổng hợp nhưng ít thay đổi có thể phù hợp với TTL dương; thông tin cần đối chiếu ngay sau một thay đổi đòi hỏi kiểm soát độ mới chặt hơn.

TTL không phải cam kết độ mới tuyệt đối của toàn hệ thống: dữ liệu nguồn có thể đã được tổng hợp hoặc cache ở một lớp khác. Trước khi tăng TTL để giảm tải, cần biết bản kết quả đang đại diện cho thời điểm nào.

Khi kết quả không đổi hoặc phương thức vẫn chạy lại, kiểm tra theo thứ tự:

1. **Đúng thuộc tính và ID:** `management.endpoint.snapshot.cache.time-to-live`, không nhầm với nhánh `endpoints.web` hoặc tên đường dẫn.
2. **Đúng giá trị có hiệu lực:** TTL có dương không, có bị profile hoặc tham số khởi động ghi đè không?
3. **Đúng thao tác:** có thực sự gọi thao tác đọc của Actuator, hay một controller GET thông thường?
4. **Đúng đầu vào và ngữ cảnh:** có tham số nghiệp vụ bắt buộc hoặc giá trị tùy chọn được truyền vào; người gọi có thay đổi không?
5. **Đúng thời điểm và tiến trình:** đã qua TTL chưa; đang gọi cùng một bản sao ứng dụng hay qua bộ cân bằng tải?
6. **Đúng lớp cache:** dữ liệu cũ đến từ Actuator hay một thành phần khác trong ứng dụng, proxy hoặc trình duyệt?

Không dùng việc hai JSON giống nhau làm bằng chứng duy nhất cho cache: phương thức có thể chạy hai lần và vẫn trả cùng dữ liệu. Bộ đếm `sequence` trong thí nghiệm giúp quan sát số lần tính toán thật.

## 9. Lỗi phổ biến

| Nhận định sai | Cách hiểu hoặc sửa |
| --- | --- |
| “Cứ GET là được cache” | Xét loại thao tác Actuator và điều kiện đầu vào; GET của controller không được thuộc tính này tự động bao phủ |
| “Có TTL trong tệp là cache đang bật” | Kiểm tra TTL hiệu lực; `0ms` không giữ kết quả bằng cơ chế này |
| “Mọi phương thức có tham số đều giống nhau” | Tách tham số bắt buộc, tùy chọn và ngữ cảnh framework; xem cả đầu vào thực tế |
| “Gọi liên tục thì bản cache không hết hạn” | Cache hit không kéo dài hạn như kiểu hết hạn trượt trong Boot 3.3.0 |
| “Đến hạn là có tác vụ nền tự làm mới” | Yêu cầu đọc sau khi hết hạn mới cần tạo kết quả mới |
| “POST xong thì GET chắc chắn thấy dữ liệu vừa ghi” | Bản đọc còn TTL có thể vẫn được dùng lại |
| “Tăng TTL sẽ công bố thêm endpoint” | Công bố và TTL là hai cấu hình riêng |
| “Một số thứ tự bị lặp nghĩa là mọi máy dùng chung cache” | Kiểm tra từng tiến trình và ngữ cảnh; TTL không tạo cache phân tán |

## 10. Tự kiểm tra

**Câu 1.** Phương thức đọc không có tham số nhưng TTL hiệu lực là `0ms`. Hai GET liên tiếp có được kỳ vọng bỏ qua lần thực thi thứ hai không?

**Đáp án:** Không. Tính đủ điều kiện không thay thế yêu cầu TTL dương; với `0ms`, bộ cache kết quả này không giữ bản đọc.

**Câu 2.** TTL là 5 giây. Đọc lại tại giây thứ 3 có tự kéo dài bản kết quả thêm 5 giây không?

**Đáp án:** Không theo cơ chế chuẩn được kiểm tra với Boot 3.3.0. Cache hit không đặt lại mốc tuổi của bản kết quả.

**Câu 3.** Vì sao một GET sau POST thành công có thể vẫn trả giá trị cũ?

**Đáp án:** POST đã đổi nguồn nhưng bản kết quả đọc đang cache chưa hết hạn; thao tác ghi không tự bảo đảm hủy bản cache đó.

**Câu 4.** Một tham số tùy chọn được bỏ trống và cùng tham số đó được truyền `filter=blue` có nhất thiết dùng cùng một cách cache không?

**Đáp án:** Không. Trong Boot 3.3.0, lời gọi không có đầu vào nghiệp vụ có thể cache, còn lời gọi có giá trị filter đi qua thực thi; đây không phải cache theo mọi giá trị filter.

**Câu 5.** Hai GET trả JSON giống hệt nhau đã đủ chứng minh có cache chưa?

**Đáp án:** Chưa. Cần thêm bằng chứng về số lần thực thi hoặc đo lường phù hợp. Dữ liệu nguồn không đổi cũng có thể làm hai kết quả tính riêng giống nhau.

**Câu 6.** Cần thêm `@EnableCaching` và một máy chủ Redis để chạy ví dụ này không?

**Đáp án:** Không. Ví dụ sử dụng bộ cache kết quả thao tác của Actuator, không yêu cầu hạ tầng cache nghiệp vụ đó.
