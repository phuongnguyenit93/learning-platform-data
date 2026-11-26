# Cấu hình expiry trên @Document theo phiên bản sử dụng

## 1. Mục tiêu bài học

Trong **Spring Data Couchbase**, một document có thể tự hết hạn theo metadata expiration mà Couchbase Server lưu giữ. Một cách thuận tiện để mô tả thời hạn sống mặc định là annotation `@Document(expiry = ...)` ngay trên entity Java. Chẳng hạn, một phiên đăng nhập có thời hạn 15 phút có thể được biểu diễn bằng `@Document(expiry = 900)`.

Điểm khó là **cấu hình annotation không phải toàn bộ hợp đồng expiry**. Cú pháp và khả năng của annotation phụ thuộc phiên bản Spring Data Couchbase; đường ghi có thể đi qua repository, `CouchbaseTemplate`, SDK hoặc SQL++; bucket/collection có thể áp `maxTTL`; những lần cập nhật cũng có thể giữ hoặc đặt lại thời điểm hết hạn. Nếu không kiểm tra các tầng đó, một giá trị 900 trong source code không bảo đảm mọi document thực tế sống đúng 900 giây.

Bài nằm trong chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Các kiến thức document mapping, repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive đều liên quan đến việc xác định **ai đặt expiry và khi nào**.

Sau bài học, bạn có thể:

1. Xác định đúng phiên bản Spring Boot, Spring Data Couchbase, Couchbase Java SDK và server trước khi chọn API expiry.
2. Khai báo TTL tĩnh bằng `@Document(expiry = ...)` và giải thích đơn vị thời gian.
3. Phân biệt TTL tĩnh với expiry động, absolute deadline và `maxTTL`.
4. Nhận diện sự khác nhau giữa `repository.save(...)` và SDK mutation bỏ qua mapper.
5. Kiểm chứng expiry thực tế qua metadata của Couchbase Java SDK.
6. Thiết kế test bảo vệ TTL khi nâng cấp dependency, đổi collection hoặc chuyển API ghi.

Các ví dụ theo phong cách **Spring Boot 3.x / Spring Data Couchbase 5.x / Couchbase Java SDK 3.x**. Với một bản minor/patch cụ thể, hãy kiểm tra API trong dependency đã được resolve; không giả định toàn bộ phiên bản hỗ trợ những extension expiry giống nhau.

## 2. Luồng từ annotation đến dữ liệu trên server

~~~mermaid
flowchart TD
    A["Java entity: @Document(expiry)"] --> B["Spring Data Mapping Context"]
    B --> C["Repository hoặc CouchbaseTemplate"]
    C --> D["SDK KV mutation"]
    D --> E["Couchbase Server"]
    F["maxTTL của bucket/collection"] --> E
    E --> G["Expiry metadata có hiệu lực"]
    G --> H["KV get / SQL++ đọc document"]
~~~

Đặt expiry trên entity có ý nghĩa khi **pipeline ghi thật sự đi qua mapper Spring Data**. Một lời gọi SDK thuần hoặc câu lệnh SQL++ không tự đọc annotation Java.

| Tầng | Nhiệm vụ | Không tự làm |
| --- | --- | --- |
| `@Document(expiry = ...)` | Khai báo TTL tĩnh ở metadata entity | Không tạo bucket/collection |
| Mapping Context | Đọc metadata class theo Spring Data version | Không quy định chính sách retention của server |
| `CouchbaseRepository` | CRUD entity qua hạ tầng Spring Data | Không áp annotation lên các mutation SDK độc lập |
| `CouchbaseTemplate` | Thao tác entity với mapping và options | Không vượt qua giới hạn server |
| SDK `Collection` | Gửi request KV, sử dụng operation options | Không biết annotation Spring Data trừ khi tầng gọi chuyển đổi |
| Bucket/collection `maxTTL` | Ràng buộc expiry trên server | Không sửa giá trị annotation trong source |
| Query service/index | Tìm document qua SQL++ | Không tự tạo TTL từ tên field JSON |

**Ví dụ:** repository có thể ghi một `LoginSessionDocument` với TTL 15 phút, trong khi collection có maxTTL 10 phút. Thời gian có hiệu lực cuối cùng phải được kiểm chứng theo cấu hình server, không chỉ đọc dòng annotation.

## 3. Kiểm tra phiên bản đang sử dụng

### 3.1. Bốn phiên bản ảnh hưởng hành vi

- **Spring Boot:** quản lý dependency và auto-configuration khi dùng starter.
- **Spring Data Couchbase:** định nghĩa `org.springframework.data.couchbase.core.mapping.Document`, mapper, repository, template và khả năng expiry động.
- **Couchbase Java SDK:** định nghĩa `UpsertOptions`, `GetOptions`, `preserveExpiry`, `Duration`, `Instant`.
- **Couchbase Server:** thực thi expiration, chính sách `maxTTL`, xử lý dữ liệu đã hết hạn và khả năng collection.

Bộ ba Boot/Spring Data/SDK có thể bị **override** bởi dependency trực tiếp. Vì vậy không suy phiên bản Spring Data chỉ từ tên Boot starter.

### 3.2. Bảng định hướng

| Họ phiên bản thường thấy | Điều cần xác minh |
| --- | --- |
| Boot 2.x và Spring Data Couchbase 4.x | Hợp đồng `@Document.expiry`, khả năng expiry động, Java SDK thực tế |
| Boot 3.x và Spring Data Couchbase 5.x | API `@Document`, các thay đổi mapping, behavior create/update |
| Dự án override Spring Data hoặc SDK | Binary compatibility và API thật trong dependency graph |
| Server khác phiên bản local | `maxTTL`, collection policy và cách quan sát metadata |

Bảng chỉ mô tả các họ phiên bản phổ biến, **không phải mapping chính xác cho mọi bản vá**. Dự án phải đối chiếu dependency graph.

Ví dụ Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-couchbase --configuration runtimeClasspath
./gradlew dependencyInsight --dependency java-client --configuration runtimeClasspath
~~~

Ví dụ Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-couchbase
mvn dependency:tree -Dincludes=com.couchbase.client:java-client
~~~

Đây là **lệnh để bạn chạy trong dự án khi cần**, không phải kết quả kiểm thử thực thi trong bài học.

### 3.3. Xem API đúng artifact

Mở class `org.springframework.data.couchbase.core.mapping.Document` bằng IDE hoặc Javadoc tương ứng artifact đã resolve. Kiểm tra:

1. Thuộc tính `expiry` còn tồn tại không, kiểu dữ liệu và giá trị mặc định là gì?
2. Javadoc quy định đơn vị nào: giây hay đơn vị khác?
3. Có cơ chế như expiry expression hoặc `@Expiry` trong release đó không?
4. Mapper xử lý expiry như thế nào khi tạo document và khi cập nhật?
5. Có thay đổi về option preservation hoặc precedence với expiry động không?

Một cách quan sát các thuộc tính annotation đang hiện diện trong classpath:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import org.springframework.data.couchbase.core.mapping.Document;

Arrays.stream(Document.class.getDeclaredMethods())
        .map(Method::getName)
        .sorted()
        .forEach(System.out::println);
~~~

Reflection chỉ giúp phát hiện **tên thuộc tính đang có**, không thể thay thế Javadoc và integration test về ngữ nghĩa.

## 4. `@Document(expiry = ...)` cho TTL tĩnh

Ví dụ một phiên đăng nhập trong bucket `commerce`, scope `checkout`, collection `sessions`:

~~~java
package com.example.checkout.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(expiry = 900) // 900 giây = 15 phút
@Scope("checkout")
@Collection("sessions")
public class LoginSessionDocument {

    @Id
    private String id;

    private String userId;
    private String deviceId;

    protected LoginSessionDocument() {
    }

    public LoginSessionDocument(
            String id, String userId, String deviceId) {
        this.id = id;
        this.userId = userId;
        this.deviceId = deviceId;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
    public String getDeviceId() { return deviceId; }
}
~~~

Giải thích:

- `@Document(expiry = 900)` mô tả TTL mặc định trong mapping Spring Data theo hợp đồng version đã xác nhận.
- `@Id` xác định document key; không đặt expiry.
- `@Scope` và `@Collection` xác định keyspace con trong bucket mặc định.
- `expiry = 900` **không phải 900 mili giây**; thông thường giá trị annotation này biểu diễn số giây.

Khi TTL áp dụng đúng trên một lần tạo document lúc 10:00, thời điểm hết hạn dự kiến khoảng 10:15. Nhưng nếu một lần `save` khác xảy ra lúc 10:10, thời điểm hết hạn mới phụ thuộc behavior update của mapper và server. Không kết luận chỉ từ annotation.

### 4.1. Hằng số compile-time cho expiry

Có thể tránh magic number bằng hằng số Java:

~~~java
public final class ExpiryPolicy {
    public static final int LOGIN_SESSION_SECONDS = 15 * 60;
    public static final int OTP_SECONDS = 5 * 60;

    private ExpiryPolicy() {
    }
}
~~~

~~~java
@Document(expiry = ExpiryPolicy.LOGIN_SESSION_SECONDS)
public class LoginSessionDocument {
    // @Id và các field khác
}
~~~

Annotation argument cần là **compile-time constant** phù hợp kiểu property. Không thể trực tiếp đưa một kết quả method call làm giá trị cho annotation numeric:

~~~java
// Không biên dịch nếu thuộc tính expiry cần một hằng số nguyên:
@Document(expiry = java.time.Duration.ofMinutes(15))
public class InvalidSession {
}
~~~

Nếu chính sách cần `Duration` được tính lúc runtime theo từng entity, phải chọn cơ chế expiry động được release hỗ trợ hoặc API mutation khác.

## 5. Đúng import là điều kiện đầu tiên

Dự án Spring có nhiều store dễ import nhầm `@Document`.

Đúng:

~~~java
import org.springframework.data.couchbase.core.mapping.Document;
~~~

Không dùng annotation của data store khác rồi chờ Spring Data Couchbase hiểu metadata đó:

~~~text
org.springframework.data.mongodb.core.mapping.Document
~~~

Spring Data Couchbase cần scanning và mapping context phù hợp. Một class có annotation đúng nhưng nằm ngoài package entity scan hoặc một repository không được đăng ký cũng khiến code không tạo ra mutation theo kỳ vọng.

`@Document` là metadata class, không phải Spring `@Component`; entity không trở thành singleton bean để inject chỉ vì được annotate.

## 6. Ví dụ end-to-end với Spring Boot và repository

Dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

`application.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${CB_BUCKET:commerce}"
~~~

Repository:

~~~java
package com.example.checkout.repository;

import com.example.checkout.domain.LoginSessionDocument;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface LoginSessionRepository
        extends CouchbaseRepository<LoginSessionDocument, String> {
}
~~~

Service:

~~~java
package com.example.checkout.service;

import com.example.checkout.domain.LoginSessionDocument;
import com.example.checkout.repository.LoginSessionRepository;
import org.springframework.stereotype.Service;

@Service
public class LoginSessionService {

    private final LoginSessionRepository repository;

    public LoginSessionService(LoginSessionRepository repository) {
        this.repository = repository;
    }

    public LoginSessionDocument create(
            String id, String userId, String deviceId) {
        return repository.save(
                new LoginSessionDocument(id, userId, deviceId)
        );
    }
}
~~~

**Điều kiện triển khai:** bucket `commerce`, scope `checkout` và collection `sessions` đã tồn tại; user có quyền KV; starter/bean/scan hoạt động; connection string và TLS phù hợp môi trường. Annotation không tạo tài nguyên trên Couchbase Server.

Khi repository `save` thành công, vẫn cần **đọc expiry metadata thực** để chứng minh mapping annotation đã có tác dụng. Một test chỉ kiểm tra repository bean tồn tại là chưa đủ.

## 7. TTL tĩnh không đồng nghĩa deadline tuyệt đối

Giả sử mã OTP có hiệu lực đúng 5 phút kể từ lần phát hành:

~~~text
10:00 Phát hành mã, deadline = 10:05
10:03 Ghi nhận một lần nhập sai
10:05 Mã phải hết hiệu lực
~~~

Nếu cập nhật lượt nhập sai bằng một mutation áp TTL 5 phút mới ở 10:03, deadline có thể chuyển tới 10:08. Điều đó vi phạm chính sách.

Ba mô hình:

| Mô hình | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| TTL tĩnh khi tạo | Document sống N giây từ thời điểm ghi | Giỏ hàng đơn giản |
| Preserve expiry | Giữ deadline đã có khi cập nhật | OTP không gia hạn |
| Absolute deadline | Hết hạn tại đúng một mốc cố định | Mã xác minh/campaign có hạn cuối |

`@Document(expiry = 300)` chỉ diễn đạt thời lượng mặc định của loại entity. Nếu muốn **đúng 10:05 dù có update**, cần biết mutation giữ expiry hay không, và có thể phải chủ động dùng metadata preservation hoặc một mốc `Instant` cố định.

## 8. `expiry = 0`, không khai báo expiry và maxTTL

Một entity sản phẩm thường không cần TTL tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class ProductDocument {

    @Id
    private String id;
    private String sku;
    private String name;

    protected ProductDocument() {
    }

    public ProductDocument(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
~~~

Ở nhiều phiên bản, giá trị expiry mặc định trên annotation là 0. Nó thường có nghĩa không khai báo thời hạn tại **cấp entity/document**. Nhưng cần lưu ý:

- **maxTTL của bucket/collection:** server có thể áp giới hạn expiry dù ứng dụng không khai báo.
- **Xóa có chủ đích:** dữ liệu vẫn có thể bị xóa thủ công hoặc qua nghiệp vụ.
- **Mutation hiện có:** ghi lại một document từng có expiry có thể giữ hoặc reset expiry tùy operation.
- **Retention và backup:** expiry không tự bảo đảm dữ liệu được xóa vật lý ngay khỏi tất cả bản sao/backup.

Đừng coi `@Document(expiry = 0)`, SDK mutation **không truyền expiry**, và SDK `preserveExpiry(true)` là cùng một thao tác. **Không đặt expiry mới** khác với **giữ nguyên expiry đã có**.

### 8.1. maxTTL có thể thay đổi kết quả

Giả sử:

~~~text
Bucket: commerce
└── Scope: checkout
    ├── sessions      (maxTTL 1 giờ)
    ├── otp_codes     (maxTTL 5 phút)
    └── audit_records (chính sách giữ lâu dài)
~~~

Nếu entity khai báo `expiry = 3600` nhưng server đặt maxTTL thấp hơn, TTL thực tế có thể bị giới hạn. Nếu entity không khai báo TTL nhưng collection vẫn có maxTTL, document vẫn có thể hết hạn.

Thứ tự áp dụng và khả năng kế thừa maxTTL giữa bucket và collection cần được xác minh trên **Couchbase Server version thực**. Đây là cấu hình server, không phải một thuộc tính YAML tùy ý của Spring Data.

## 9. Expiry động theo phiên bản

Nhiều nghiệp vụ cần TTL khác nhau cho từng instance hoặc deadline cố định:

- Giỏ hàng: 30 phút từ lần sửa gần nhất.
- OTP: 5 phút kể từ lần cấp, không reset khi cập nhật.
- Session: idle timeout 20 phút và absolute lifetime 8 giờ.
- Campaign: hết hạn lúc một ngày/giờ UTC cụ thể.

`@Document(expiry = 900)` có giá trị cố định cho cả class. Một số phiên bản Spring Data Couchbase có các khả năng liên quan **expiry expression** hoặc `@Expiry` để mô tả giá trị được tính từ entity; tuy nhiên cú pháp, kiểu dữ liệu, vị trí annotation, thứ tự ưu tiên và behavior khi update phải kiểm tra ở đúng version.

**Quy trình lựa chọn:**

1. Mở `Document` và các annotation expiry liên quan trong Javadoc của dependency.
2. Xác định có thuộc tính expression hay annotation dynamic expiry thực sự được release hỗ trợ.
3. Kiểm tra SpEL syntax, kiểu thời gian/giá trị được phép, đơn vị và thứ tự ưu tiên với TTL tĩnh.
4. Tạo hai entity instance với thời hạn khác nhau và kiểm tra expiry metadata sau khi lưu.
5. Kiểm tra create **và** update; không chỉ xác nhận lần insert đầu tiên.
6. Nếu API mapping không biểu đạt đúng policy, sử dụng SDK `Duration`/`Instant` hoặc điểm mở rộng `CouchbaseTemplate` thích hợp.

Không nên sao chép một ví dụ `expiryExpression` hoặc `@Expiry` từ release khác vào production mà chưa xác minh API. Một method/annotation có tên giống nhau chưa đủ để kết luận hiệu lực của metadata.

### 9.1. Không nhầm JSON property với expiry metadata

Một field Java/JSON tên `expiresAt` chỉ là dữ liệu nghiệp vụ. Couchbase không tự xem nó là thời điểm hết hạn của document. Nếu ứng dụng vừa lưu `expiresAt` trong JSON vừa đặt metadata expiry, phải giữ chúng nhất quán hoặc định nghĩa cái nào là nguồn sự thật.

## 10. Đặt expiry trực tiếp bằng Couchbase Java SDK

Nếu API của mapper không hỗ trợ policy cần thiết, Couchbase Java SDK 3.x thường cho phép đặt thời hạn trên mutation.

TTL tương đối:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

// carts: handle Collection commerce.checkout.carts.
carts.upsert(
        "cart::u-42",
        JsonObject.create().put("itemCount", 2),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Deadline tuyệt đối:

~~~java
import java.time.Instant;

Instant deadline = Instant.parse("2026-12-01T00:00:00Z");

campaigns.upsert(
        "campaign::WINTER",
        JsonObject.create().put("name", "Winter"),
        UpsertOptions.upsertOptions().expiry(deadline)
);
~~~

`Duration` biểu đạt “sống thêm bao lâu”, `Instant` biểu đạt “hết hạn lúc nào”. Những kiểu này giúp tránh tự biểu diễn một số giây không rõ nó là thời lượng tương đối hay Unix epoch.

**Quan trọng:** SDK `upsert` không tự đọc `@Document(expiry = ...)` của class Java, cũng không mặc nhiên chạy Spring Data converter hoặc optimistic locking. Khi trộn repository và SDK, cần đồng bộ policy TTL, schema JSON, CAS và idempotency.

### 10.1. Quy tắc raw numeric expiry và ranh giới 30 ngày

Một số giao thức và API Couchbase lịch sử có quy tắc giá trị số expiry: thời lượng ngắn được hiểu tương đối, giá trị lớn có thể được hiểu là Unix timestamp tuyệt đối, thường được nhắc tới tại ranh giới 30 ngày.

Vì quy tắc có thể khác giữa server versions và API, tránh truyền raw integer khi chưa xác minh semantics. Với SDK Java, ưu tiên `Duration.ofDays(45)` nếu muốn thời lượng tương đối, và `Instant` nếu muốn giờ kết thúc cụ thể.

## 11. Update: reset hay giữ thời hạn đã có?

Một document được tạo lúc 10:00 với TTL 15 phút. Lúc 10:10 ứng dụng sửa một field. Kết quả có thể thuộc một trong các mẫu:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant DB as Couchbase
    App->>DB: 10:00 tạo document TTL 15 phút
    Note over DB: Hạn dự kiến 10:15
    alt Đặt TTL mới
      App->>DB: 10:10 mutation TTL 15 phút
      Note over DB: Hạn dự kiến chuyển tới 10:25
    else Bảo toàn expiry
      App->>DB: 10:10 mutation preserve expiry
      Note over DB: Giữ hạn 10:15
    end
~~~

Đối với mutation SDK hỗ trợ, có thể bảo toàn expiry:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.ReplaceOptions;

products.replace(
        "product::SKU-001",
        JsonObject.create().put("name", "Updated"),
        ReplaceOptions.replaceOptions().preserveExpiry(true)
);
~~~

**Cảnh báo về code trên:** `replace` ghi lại toàn bộ content document. Nếu document ban đầu có nhiều field, JSON chỉ chứa `name` có thể làm mất các field khác; code này chỉ minh họa option preserve. Trong sản phẩm thật hãy đọc/merge đủ dữ liệu, dùng subdocument hoặc cách update phù hợp.

Preserve expiry **không phải CAS**. Nếu hai request sửa cùng document, cần thêm CAS/`@Version` khi nghiệp vụ cần optimistic concurrency.

### 11.1. Gia hạn có chủ đích bằng touch

~~~java
import java.time.Duration;

carts.touch("cart::u-42", Duration.ofMinutes(30));
~~~

`touch` đổi metadata expiry mà không cần thay JSON content. Dùng cho session/cart chỉ khi hành vi tương tác được phép gia hạn. Không gọi `touch` vô điều kiện trong mọi lần đọc nếu còn có hạn sử dụng tuyệt đối.

### 11.2. Hard deadline của session

Giả sử:

~~~text
issuedAt:            09:00
absoluteDeadline:    17:00
lastActivity:        16:50
idleDeadline:        17:10
effectiveDeadline:   17:00
~~~

Nếu chỉ `@Document(expiry = 1200)` rồi cập nhật session lúc 16:50, có thể đẩy hạn tới 17:10, trái với hard deadline. Chính sách đúng cần dùng **mốc sớm hơn** giữa idle và absolute deadline, qua dynamic expiry hoặc API `Instant` và xử lý update nhất quán.

## 12. Kiểm chứng metadata expiry thay vì đoán

Sau `repository.save(...)`, đọc expiry bằng SDK trên **đúng collection**:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = sessions.get(
        "session::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(expiry ->
        System.out.println("Expiry: " + expiry)
);
~~~

`withExpiry(true)` yêu cầu trả metadata expiry theo API hỗ trợ; `expiryTime()` thường trả một giá trị tùy chọn. Nếu không có expiry, phải xác minh semantics theo SDK version thay vì tự gán một mốc giả định.

Đây là **nguồn kiểm tra tốt hơn** so với chỉ đọc `@Document`, bởi nó phản ánh mutation thực tế cộng với chính sách server.

### 12.1. Quy trình kiểm chứng

1. Ghi một document test có key duy nhất bằng repository.
2. Đọc ngay bằng SDK `get` với expiry metadata.
3. So sánh mốc expiry nhận được với thời điểm ghi và TTL mong đợi, có dung sai hợp lý.
4. Cập nhật cùng entity bằng repository rồi đọc metadata lại.
5. Cập nhật bằng SDK với preserve expiry; so sánh.
6. Thử trong collection có chính sách maxTTL được biết rõ.
7. Kiểm chứng reactive pipeline bằng subscription thật thay vì chỉ tạo `Mono`.

Không nên chỉ ngủ đúng 3 giây và assert doc biến mất ở mili giây cuối: độ phân giải thời gian, scheduling và việc server thu hồi dữ liệu có thể khiến test flaky.

### 12.2. Expiry logic khác với thu hồi vật lý

Khi hết hạn, document thường không còn được coi là hợp lệ cho KV operations. Tuy vậy, tài nguyên vật lý có thể được thu hồi theo các cơ chế nền và nhịp compaction/purge khác nhau. TTL không tự chứng minh rằng mọi bản sao, snapshot, backup đã được xóa vật lý ngay tại một thời điểm.

## 13. Unit test bảo vệ chính sách annotation

Một unit test rất nhỏ có thể phát hiện việc vô tình sửa hằng số:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.data.couchbase.core.mapping.Document;

import static org.assertj.core.api.Assertions.assertThat;

class SessionAnnotationTest {

    @Test
    void sessionExpiryIsFifteenMinutes() {
        Document meta =
                LoginSessionDocument.class.getAnnotation(Document.class);

        assertThat(meta).isNotNull();
        assertThat(meta.expiry()).isEqualTo(900);
    }
}
~~~

Test này **chỉ kiểm tra metadata annotation**, không chứng minh mapper áp TTL hay server bảo lưu thời hạn khi update. Đó là lý do phải có integration test bên cạnh.

## 14. Integration test chứng minh TTL thực tế

Một phác thảo integration test dùng repository và SDK:

~~~java
import java.time.Instant;
import java.util.UUID;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetOptions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LoginSessionExpiryIT {

    private final LoginSessionRepository repository;
    private final Collection sessions;

    LoginSessionExpiryIT(
            LoginSessionRepository repository,
            Collection sessions) {
        this.repository = repository;
        this.sessions = sessions;
    }

    @Test
    void saveAppliesExpiry() {
        String id = "session::test::" + UUID.randomUUID();
        Instant before = Instant.now();

        repository.save(new LoginSessionDocument(
                id, "test-user", "test-device"
        ));

        var read = sessions.get(
                id, GetOptions.getOptions().withExpiry(true)
        );

        Instant deadline = read.expiryTime().orElseThrow();
        assertThat(deadline).isAfter(before);
        // Assert thêm gần 15 phút với dung sai clock/server.
    }
}
~~~

**Đây là skeleton, không phải test độc lập chạy ngay**. Nó giả định fixture đã inject đúng repository/`Collection` và Couchbase test server có bucket/scope/collection tương ứng. Phải bổ sung Spring test context, setup và cleanup để chạy thật. Một `Collection` đúng scope thường được tạo từ `CouchbaseClientFactory` hoặc test fixture; đừng mặc định Boot đăng ký sẵn bean Collection đúng keyspace.

Bộ regression test nên gồm:

| Test | Điều xác minh |
| --- | --- |
| Insert với annotation | TTL tĩnh được áp dụng |
| Save lại entity | Deadline reset hay preserve như policy |
| SDK update sau repository | Đường SDK có options phù hợp |
| maxTTL thấp hơn annotation | Server áp giới hạn đúng |
| Entity `expiry = 0` | Không TTL khi collection không ép maxTTL |
| Expiry động nếu được hỗ trợ | Mỗi instance nhận deadline riêng |
| Reactive save | Mutation xảy ra sau subscribe, TTL có hiệu lực |
| Retry/ambiguous write | Không gia hạn OTP hoặc làm sai deadline |

## 15. Reactive không thay đổi bản chất expiry

Với `ReactiveCouchbaseRepository`, mapping annotation vẫn thuộc tầng entity, nhưng việc lưu document diễn ra trong reactive publisher:

~~~java
import reactor.core.publisher.Mono;

public Mono<LoginSessionDocument> create(
        ReactiveLoginSessionRepository repository,
        LoginSessionDocument entity) {
    return repository.save(entity);
}
~~~

- Chỉ tạo `Mono` **không có nghĩa document đã được ghi**.
- `Mono.timeout(Duration.ofSeconds(2))` là timeout của pipeline, **không phải** TTL document.
- Retry/resubscribe có thể lặp mutation; nếu mỗi mutation lại áp TTL tương đối thì deadline có thể thay đổi.
- Cancellation không bảo đảm thao tác đã gửi tới Couchbase được rollback.
- WebFlux không nên gọi `block()` trên event-loop chỉ để đợi expiry.

Nếu API reactive dùng SDK trực tiếp, nó cũng không tự đọc annotation Spring Data; expiry phải đi qua đúng mapping pipeline hoặc operation options.

## 16. Tương tác với CAS, transaction và SQL++

### 16.1. CAS / `@Version`

TTL là thời điểm document hết hiệu lực; CAS là cơ chế kiểm soát **xung đột cập nhật**. Một document có thể hết hạn trong lúc hai request đang tranh cập nhật. Phải phân biệt:

- Document not found do hết hạn hoặc bị xóa.
- CAS mismatch do phiên bản thay đổi.
- Operation timeout khi client không nhận response trong ngân sách.

`@Document(expiry)` không tự chống lost update. Khi dùng `@Version` hoặc CAS, cần giữ cả chính sách expiry trong các mutation.

### 16.2. Transaction

Thời hạn sống document khác với transaction timeout và điều kiện commit/rollback. Không sử dụng `@Document(expiry = 900)` như một “lịch hẹn” để tự động commit hoặc hủy một giao dịch ở phút thứ 15.

### 16.3. SQL++ và chỉ mục

SQL++ qua Query service không tự đọc annotation entity khi chạy lệnh `UPDATE` hoặc `UPSERT`. Nếu code đổi từ repository sang SQL++ mutation, cần xác minh semantics expiry của statement đó ở server version đang dùng.

Query theo thuộc tính như `findBySku(...)` có thể cần secondary index; `findById(...)` thường dùng KV. Một document không thấy qua SQL++ chưa đủ để kết luận TTL đã hết; trước hết kiểm tra keyspace và KV theo ID.

## 17. Nâng cấp version và thay đổi đường ghi

Khi nâng cấp Spring Boot hoặc Spring Data Couchbase:

1. Chụp dependency graph trước và sau.
2. Đọc Javadoc của `@Document` cùng các annotation expiry nâng cao.
3. So sánh behavior insert/update với cùng một test fixture.
4. Xác minh default/precedence giữa mapper và operation options.
5. Kiểm tra chính sách `maxTTL` của bucket/collection ở staging và production.
6. Kiểm tra reactive và transaction paths nếu dự án dùng.
7. Theo dõi số document hết hạn, p95/p99 và lỗi document-not-found theo keyspace sau rollout.

Ví dụ refactor làm thay đổi policy:

~~~java
// Trước: Spring Data entity mapping đọc @Document.
sessionRepository.save(session);
~~~

~~~java
// Sau: SDK thuần không đọc annotation Java.
sessions.upsert(
        session.getId(),
        JsonObject.create().put("userId", session.getUserId())
);
~~~

Nếu không cấu hình `UpsertOptions.expiry(...)`, đường ghi sau có thể có expiry khác trước. Đây là một **thay đổi hành vi dữ liệu**, không chỉ tối ưu hiệu năng.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân nên xem | Hướng khắc phục |
| --- | --- | --- |
| `@Document(expiry = ...)` không biên dịch | Sai import hoặc version API | Kiểm tra dependency/annotation thật |
| `900` được hiểu là 900 ms | Nhầm đơn vị số trong annotation | Kiểm tra Javadoc và test |
| Document biến mất sớm | `maxTTL` server hoặc deadline sai | Kiểm tra collection/bucket và metadata |
| Document sống lâu hơn mong đợi | Save/replace/touch reset TTL | Xác minh update semantics |
| SDK update không giữ TTL | SDK không đọc annotation | Thêm operation options/preserve expiry |
| OTP được gia hạn khi retry | Dùng relative TTL mỗi mutation | Giữ deadline tuyệt đối hoặc preserve |
| `expiry = 0` mà vẫn hết hạn | maxTTL khác 0 hoặc thao tác xóa khác | Kiểm tra server policy |
| Entity không được mapping đúng | Sai keyspace, entity scan, repository scan | Kiểm tra cấu hình Spring Data |
| Query không thấy document nhưng KV còn | Query service/index/consistency | Chẩn đoán SQL++ riêng |
| Test thỉnh thoảng thất bại | Assert quá sát thời điểm | Poll có deadline, key độc lập |
| Nâng cấp làm TTL thay đổi | API/mapper/server config khác | Regression test metadata |
| Reactive save không ghi | Publisher chưa được subscribe | Kiểm tra subscription và signal |
| Document khác nội dung sau replace | Replace ghi toàn bộ content | Merge/subdocument phù hợp |

### 18.1. Cây kiểm tra

~~~mermaid
flowchart TD
    A["TTL thực tế không như mong đợi"] --> B{"Import đúng @Document Couchbase?"}
    B -- "Không" --> C["Sửa import/mapping"]
    B -- "Có" --> D{"Mutation có đi qua Spring Data?"}
    D -- "Không" --> E["Xem SDK/SQL++ expiry options"]
    D -- "Có" --> F["Kiểm tra version, mapper, update path"]
    E --> G["Kiểm tra bucket/collection maxTTL"]
    F --> G
    G --> H["Đọc expiry metadata"]
    H --> I["Xác minh reset/preserve/touch"]
    I --> J["Bổ sung integration regression test"]
~~~

## 19. Bài tập tình huống

Một `checkout-service` quản lý bốn loại dữ liệu:

~~~text
Bucket: commerce
Scope: checkout
├── sessions
├── otp_codes
├── carts
└── orders
~~~

Yêu cầu nghiệp vụ:

- Session: idle TTL 15 phút, hard deadline tối đa 8 giờ.
- OTP: 5 phút từ lúc phát hành, không gia hạn sau lần nhập sai.
- Cart: 30 phút từ lần sửa giỏ gần nhất.
- Order: không tự hết hạn theo chính sách phiên đăng nhập.

Sau khi nâng cấp Spring Boot, nhóm thay một phần repository save bằng SDK upsert. Session có thời hạn không ổn định; OTP đôi khi sống lâu hơn 5 phút; collection mới chứa order lại có `maxTTL` 24 giờ.

**Yêu cầu thực hành:**

1. Xác minh version Boot, Spring Data, SDK và server đang chạy.
2. Phân tích `@Document(expiry = 900)` có thể làm gì và không thể làm gì.
3. Giải thích vì sao hard deadline 8 giờ không nên chỉ dựa vào TTL 15 phút mỗi lần update.
4. Chỉ ra cách giữ deadline OTP khi ghi thêm số lần nhập sai.
5. Mô tả việc đặt `UpsertOptions.expiry(...)` hoặc preserve expiry cho SDK path.
6. Kiểm tra và sửa `maxTTL` nếu order phải sống lâu.
7. Thiết kế integration test so sánh repository save, SDK update và reactive save.
8. Nêu cách CAS/`@Version` giúp tránh xung đột cập nhật mà không thay TTL.

**Đáp án định hướng:** annotation tĩnh phù hợp với thời lượng mặc định; các deadline/đường ghi khác cần cơ chế expiry động hoặc operation options rõ ràng. SDK không tự đọc mapper; server maxTTL luôn phải xét. Đọc metadata và viết test behavior là cách chứng minh kết quả.

## 20. Checklist áp dụng

- [ ] Đã xác định phiên bản thực tế của Boot, Spring Data, SDK và Couchbase Server.
- [ ] Import đúng `org.springframework.data.couchbase.core.mapping.Document`.
- [ ] Đã kiểm tra đơn vị, giá trị mặc định và kiểu của `expiry` theo Javadoc release.
- [ ] TTL tĩnh thực sự phù hợp mọi entity instance trong class.
- [ ] Đã kiểm tra khả năng `expiryExpression`/`@Expiry` trước khi dùng expiry động.
- [ ] Có chính sách cho create/update: reset, preserve hay dùng absolute deadline.
- [ ] Đã xác minh `maxTTL` bucket/collection ở môi trường đích.
- [ ] Đường SDK/SQL++ không vô tình bỏ qua TTL mapper.
- [ ] Đã đọc metadata expiry sau khi ghi trong integration test.
- [ ] Test có key duy nhất, dung sai clock và polling deadline hợp lý.
- [ ] Có regression test khi nâng version hoặc đổi keyspace.
- [ ] Retry mutation có xét idempotency và ambiguous timeout.
- [ ] Reactive subscription được thực thi trong test.
- [ ] Không nhầm TTL với KV timeout, Query timeout, CAS hoặc transaction deadline.
- [ ] Không xem TTL là cam kết xóa vật lý ngay khỏi mọi bản sao/backup.

## 21. Tổng kết

`@Document(expiry = ...)` là cách diễn đạt súc tích một **TTL tĩnh mặc định** trong Spring Data Couchbase. Giá trị như `@Document(expiry = 900)` thường biểu thị 900 giây theo hợp đồng annotation tương ứng. Nhưng kết quả trên server còn phụ thuộc phiên bản mapper, con đường mutation, chính sách maxTTL, cách update và deadline nghiệp vụ.

Để sử dụng an toàn, hãy **kiểm tra phiên bản trước, kiểm tra metadata sau**, phân biệt rõ TTL tĩnh/động và preserve/reset, cũng như chứng minh hành vi bằng integration test. Khi đó repository, `CouchbaseTemplate`, SQL++ index, CAS, giao dịch và reactive API có thể cùng vận hành mà không vô tình thay đổi vòng đời của document.

