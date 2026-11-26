# Đơn vị thời gian và cấu hình thời hạn bằng thuộc tính ứng dụng

## 1. Vì sao đơn vị thời gian là vấn đề về tính đúng đắn dữ liệu?

Một lỗi cấu hình có thể khiến document hết hạn sau **900 mili giây** thay vì **900 giây**, hoặc khiến mã xác minh được gia hạn thêm năm phút mỗi khi người dùng thử lại. Với Spring Data Couchbase, những lỗi này dễ xuất hiện khi trộn số giây của annotation, `Duration` từ Spring Boot, expiry options của Couchbase Java SDK và `maxTTL` ở server.

Bài thuộc chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Module hướng đến xây dựng tầng truy cập Couchbase qua document mapping, repository, `CouchbaseTemplate` và SQL++; đồng thời học bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive API để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

Sau bài, bạn có thể:

1. Phân biệt **giây** trong `@Document(expiry = ...)` với cú pháp thời lượng trong `application.yml`.
2. Bind `30s`, `15m`, `2h` hoặc `PT15M` vào `java.time.Duration`.
3. Tổ chức thuộc tính ứng dụng cho TTL, xác minh đơn vị và từ chối giá trị không hợp lệ.
4. Đưa giá trị đã bind vào Couchbase SDK hoặc mapper Spring Data theo phiên bản hỗ trợ.
5. Phân biệt TTL tương đối với deadline tuyệt đối, reset TTL với preserve expiry.
6. Kiểm tra expiry hiệu lực khi bucket/collection có `maxTTL` và viết test chống lỗi hồi quy.

Ví dụ dùng Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x và Couchbase Java SDK 3.x tương thích. Các API expression và kiểu giá trị expiry phải được xác minh bằng Javadoc của **phiên bản đang sử dụng**.

## 2. Bốn cách diễn đạt thời hạn không nên đánh đồng

| Biểu diễn | Nơi sử dụng | Diễn giải |
| --- | --- | --- |
| `@Document(expiry = 900)` | Annotation Spring Data Couchbase | Thông thường là **900 giây**, tức 15 phút |
| `app.couchbase.expiration.cart: 30m` | YAML do ứng dụng định nghĩa và bind thành `Duration` | 30 phút |
| `Duration.ofMinutes(30)` | Java SDK `expiry(Duration)` | 30 phút tương đối khi áp mutation |
| `Instant.parse("2026-12-01T00:00:00Z")` | Java SDK `expiry(Instant)` | Mốc thời gian tuyệt đối UTC |

`Duration` là độ dài khoảng thời gian, không phải một thời điểm. `Instant` là một mốc UTC, không phải số phút từ hiện tại. `@Document(expiry)` là metadata entity, khác với `spring.couchbase.env.timeouts.kv` vốn chỉ giới hạn thời gian **chờ thao tác KV**.

### 2.1. Đơn vị trong Spring Boot `Duration`

| Giá trị | Khi bind vào `Duration` | Cạm bẫy |
| --- | --- | --- |
| `500ms` | 500 mili giây | Expiry document không nên dựa vào độ chính xác mili giây |
| `30s` | 30 giây | Dễ đọc, thích hợp test hoặc TTL ngắn |
| `15m` | 15 phút | Thích hợp cho session idle |
| `2h` | 2 giờ | Thích hợp cache/giỏ hàng nếu policy yêu cầu |
| `1d` | 24 giờ | Khác “hết cuối ngày lịch” theo timezone |
| `PT15M` | 15 phút (ISO-8601 duration) | Cần phân biệt `M` là minute ở đoạn time |
| `900` | Mặc định có thể là **900 ms** với `Duration` trong Boot | Không dùng số trần khi muốn 900 giây |

Hãy viết đơn vị tường minh. Nếu một API mong đợi **số giây nguyên**, `900s` và `15m` tương đương về ý nghĩa, nhưng số nguyên `900` trong annotation không thể tự suy ra rằng property `900` cũng là giây.

### 2.2. Timezone và “một ngày” theo lịch

`Duration.ofDays(1)` là 24 giờ. Nó không tự biểu diễn “đến 00:00 ngày mai theo giờ Hà Nội” hay “đến cuối ngày khuyến mãi”. Khi nghiệp vụ có ranh giới ngày lịch, dùng `LocalDate` cùng `ZoneId` để tạo `Instant`. Trong hệ thống có DST, một ngày lịch thậm chí có thể dài 23 hoặc 25 giờ.

## 3. Bắt đầu từ chính sách nghiệp vụ, không bắt đầu từ YAML

Một hệ thống bán hàng có keyspace:

~~~text
Bucket commerce
├── Scope catalog
│   └── Collection products
└── Scope checkout
    ├── Collection carts
    ├── Collection sessions
    └── Collection otp_codes
~~~

| Loại dữ liệu | Chính sách | Nên biểu diễn |
| --- | --- | --- |
| Sản phẩm | Không tự hết hạn | Không TTL ở document, kiểm tra `maxTTL` |
| Giỏ hàng | 30 phút sau lần sửa hợp lệ | `Duration`, gia hạn có chủ đích |
| Session | Idle 15 phút, tối đa 8 giờ kể từ lúc tạo | Hai `Duration` và deadline nhỏ hơn |
| OTP | 5 phút sau khi phát hành, không gia hạn khi nhập sai | Deadline cố định hoặc preserve expiry |
| Chiến dịch | Hết hạn 00:00 UTC ngày 1/12/2026 | `Instant` |

Cùng giá trị “5 phút” nhưng **gia hạn** hay **không gia hạn** mới quyết định cách ghi document. Đơn vị đúng chỉ là điều kiện cần; nghiệp vụ phải xác định lúc nào TTL được đặt lại.

## 4. Khai báo thuộc tính ứng dụng trong `application.yml`

Ví dụ:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:commerce}"

app:
  couchbase:
    expiration:
      cart: "${CART_TTL:30m}"
      otp: "${OTP_TTL:5m}"
      session-idle: "${SESSION_IDLE_TTL:15m}"
      session-absolute: "${SESSION_ABSOLUTE_TTL:8h}"
~~~

Cần phân biệt nguồn tiêu thụ:

- `spring.couchbase.*`: nhóm cấu hình SDK được Spring Boot hỗ trợ.
- `spring.data.couchbase.bucket-name`: bucket mặc định cho Spring Data.
- `app.couchbase.expiration.*`: **property do ứng dụng tự định nghĩa**, chưa tác động tới document nếu không có Java code bind và sử dụng.

Các tên biến môi trường `CART_TTL`, `OTP_TTL` v.v. do dự án quy ước. Chúng không phải tùy chọn đặc biệt của Couchbase. Credentials cần được cung cấp bằng secret runtime; không commit password vào source.

**Lưu ý:** không nên tự thêm khóa `spring.data.couchbase.ttl: 15m` rồi tin rằng Boot sẽ áp expiry cho mọi repository. Một property không nằm trong API cấu hình hoặc không được code sử dụng có thể bị bỏ qua.

## 5. Bind sang `Duration` với `@ConfigurationProperties`

Dùng một record để việc kiểm soát TTL có một điểm vào:

~~~java
package com.example.checkout.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.couchbase.expiration")
public record ExpirationProperties(
        Duration cart,
        Duration otp,
        Duration sessionIdle,
        Duration sessionAbsolute
) {
    public ExpirationProperties {
        requirePositive("cart", cart);
        requirePositive("otp", otp);
        requirePositive("sessionIdle", sessionIdle);
        requirePositive("sessionAbsolute", sessionAbsolute);
    }

    private static void requirePositive(String name, Duration value) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(
                    "Invalid expiration: " + name
            );
        }
    }
}
~~~

Ý nghĩa:

1. Spring Boot chuyển chuỗi `30m` thành `Duration.ofMinutes(30)`.
2. Trường `session-idle` được bind vào `sessionIdle` theo quy tắc relaxed binding.
3. Constructor từ chối thiếu, zero hoặc âm vì cả bốn TTL trong bài đều **bắt buộc dương**.
4. Record không kết nối Couchbase; nó chỉ lưu chính sách đã được kiểm tra.

Kích hoạt scan:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Nếu không dùng `@ConfigurationPropertiesScan`, có thể khai báo `@EnableConfigurationProperties(ExpirationProperties.class)` trong configuration phù hợp. Không cần đăng ký hai lần.

**Đừng nhầm `@ConfigurationPropertiesScan` với entity scan hay repository scan.** Nó chỉ tìm class cấu hình do ứng dụng định nghĩa.

### 5.1. Có nên cho phép `0s`?

Đối với OTP, `0s` thường là cấu hình sai và cần **fail fast**. Với cache mà có quy ước “0 nghĩa là không tự hết hạn”, có thể chấp nhận 0 nhưng phải định nghĩa bằng policy riêng, không áp cùng validation cho mọi entity.

`Duration.ZERO` ở Java và giá trị expiry 0 ở Couchbase cũng không nhất thiết bảo đảm document tồn tại mãi: bucket/collection `maxTTL` có thể giới hạn thời gian sống.

## 6. Đưa property vào SDK mutation

Ví dụ giỏ hàng ghi bằng Couchbase Java SDK, sử dụng client factory của Spring Data thay vì tạo cluster mới:

~~~java
package com.example.checkout.service;

import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;
import com.example.checkout.config.ExpirationProperties;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;
import org.springframework.stereotype.Service;

@Service
public class CartWriter {

    private final Collection carts;
    private final ExpirationProperties expiration;

    public CartWriter(
            CouchbaseClientFactory factory,
            ExpirationProperties expiration) {
        this.carts = factory.getBucket()
                .scope("checkout")
                .collection("carts");
        this.expiration = expiration;
    }

    public void saveCart(String userId, int itemCount) {
        carts.upsert(
                "cart::" + userId,
                JsonObject.create()
                        .put("userId", userId)
                        .put("itemCount", itemCount),
                UpsertOptions.upsertOptions()
                        .expiry(expiration.cart())
        );
    }
}
~~~

`UpsertOptions.expiry(Duration)` diễn đạt TTL tương đối cho **mutation này**. Giả sử `cart = 30m` và không bị `maxTTL` thấp hơn, hạn dự kiến được tính từ lúc ghi. Khi `saveCart` chạy lại, TTL tương đối có thể được đặt lại.

Ví dụ giả định bucket `commerce`, scope `checkout` và collection `carts` đã tồn tại. Lấy handle không tự tạo tài nguyên trên server. Cũng không cần tự gọi `Cluster.connect()` hoặc `disconnect()` trong mỗi request.

**Giới hạn của cách dùng SDK trực tiếp:** operation JSON không tự áp mapper `@Document`, `@Version` hay converter của Spring Data. Nếu repository và SDK cùng sửa một document, phải thống nhất chính sách mapping, CAS và expiry.

## 7. `@Document(expiry = ...)` nhận số giây, không nhận `Duration` tự do

Một entity có TTL tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(expiry = 900) // 900 giây = 15 phút
public class LoginSessionDocument {

    @Id
    private String id;
    private String userId;

    protected LoginSessionDocument() {
    }

    public LoginSessionDocument(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
}
~~~

Với các bản Spring Data Couchbase hỗ trợ, `expiry = 900` mô tả số giây trong metadata class. Đây là một giá trị **compile-time**.

Có thể dùng hằng số:

~~~java
public final class ExpiryConstants {
    public static final int SESSION_SECONDS = 15 * 60;

    private ExpiryConstants() {
    }
}
~~~

~~~java
@Document(expiry = ExpiryConstants.SESSION_SECONDS)
public class AnotherSessionDocument {
    // ...
}
~~~

Không thể thay một thuộc tính annotation kiểu số bằng chuỗi placeholder của Spring:

~~~java
// SAI nếu thuộc tính expiry cần một số nguyên compile-time:
@Document(expiry = "${app.couchbase.expiration.session-idle}")
public class InvalidSessionDocument {
}
~~~

Java annotation phải thỏa kiểu và ràng buộc compile-time; `@Value` hay YAML không tự thay đổi một `int` trong class đã biên dịch. Nếu muốn TTL cấu hình từ property ngay trên annotation, cần API **expression** do Spring Data version hỗ trợ.

## 8. Dùng expiry expression từ property: kiểm tra đúng phiên bản

Một số phiên bản Spring Data Couchbase cung cấp thuộc tính `expiryExpression` ở `@Document`. Nếu release đang dùng xác nhận hỗ trợ placeholder và kiểu giá trị mong đợi, có thể dùng mô hình:

~~~yaml
app:
  couchbase:
    expiration:
      session-seconds: 900
~~~

~~~java
import org.springframework.data.couchbase.core.mapping.Document;

// Ví dụ có điều kiện: kiểm tra Javadoc và mapping behavior của version.
@Document(
        expiryExpression = "${app.couchbase.expiration.session-seconds}"
)
public class PropertyDrivenSessionDocument {
    // @Id và các property thực tế.
}
~~~

Tại sao dùng `session-seconds` thay vì `session-idle: 15m`? Vì **nếu mapper yêu cầu kết quả expression là số giây**, chuỗi `900` có loại/đơn vị rõ ràng hơn chuỗi `15m`. Không mặc định mapper sẽ bind expression thành `Duration` giống `@ConfigurationProperties`.

Trước khi triển khai, xác minh:

1. `expiryExpression` có trong annotation của artifact thực tế không?
2. Mapper có resolve `${...}` tại vị trí này không?
3. Biểu thức cần trả về `int`, `long`, `Duration` hay kiểu khác?
4. Nếu đồng thời khai báo `expiry` và `expiryExpression`, cái nào có hiệu lực?
5. Update qua repository có reset TTL hay preserve expiry?
6. Mapping có hoạt động với reactive repository/template đang dùng?

Đừng sao chép cú pháp từ release mới sang release cũ mà không kiểm tra.

### 8.1. Kiểm tra API thật

Mở Javadoc/IDE của `org.springframework.data.couchbase.core.mapping.Document` trong dependency đã resolve. Một đoạn reflection đơn giản có thể cho biết **tên method** được khai báo trên annotation:

~~~java
import java.util.Arrays;
import org.springframework.data.couchbase.core.mapping.Document;

Arrays.stream(Document.class.getDeclaredMethods())
        .map(method -> method.getName())
        .sorted()
        .forEach(System.out::println);
~~~

Reflection **không** chứng minh cách Spring xử lý property. Sau khi biết API tồn tại, phải integration test trên Couchbase thật.

### 8.2. Tránh hai nguồn sự thật

Hai property dưới đây cùng nói về một session nhưng có thể bị sửa lệch nhau:

~~~yaml
app:
  couchbase:
    expiration:
      session-idle: 15m
      session-seconds: 900
~~~

Nếu developer sửa `session-idle` thành `20m` nhưng quên `session-seconds`, code SDK và entity mapper có thể áp TTL khác nhau. Nên chọn một con đường ghi có **nguồn cấu hình chủ đạo**, hoặc có kiểm thử khẳng định hai giá trị luôn tương đương.

## 9. Khi phải chuyển `Duration` thành số giây nguyên

Một số API yêu cầu số nguyên thay vì `Duration`. Nếu cần chuyển đổi runtime, không nên âm thầm làm tròn:

~~~java
import java.time.Duration;

static int requireWholePositiveSeconds(Duration ttl) {
    if (ttl == null || ttl.isZero() || ttl.isNegative()) {
        throw new IllegalArgumentException("TTL must be positive");
    }
    if (ttl.getNano() != 0) {
        throw new IllegalArgumentException(
                "TTL must have whole-second precision"
        );
    }
    return Math.toIntExact(ttl.getSeconds());
}
~~~

Các rủi ro:

- `Duration.ofMillis(1500).toSeconds()` mất phần nửa giây.
- `Math.toIntExact` phát hiện tràn khi số giây không còn nằm trong `int`.
- `Duration.ofMillis(500)` có thể bị chuyển sai thành 0 nếu chỉ cắt lấy giây nguyên.
- Một API cấp thấp có thể sử dụng số expiry với ngữ nghĩa tương đối/tuyệt đối khác nhau; không suy đoán chỉ từ kiểu `int`.

Hàm này xử lý **runtime value**, không làm kết quả trở thành compile-time constant cho `@Document(expiry = ...)`. Khi SDK đã chấp nhận `Duration`, thường không cần chuyển nó về `int`.

## 10. Expiry tương đối và deadline tuyệt đối

Giá trị YAML `cart: 30m` mô tả “sống thêm 30 phút khi áp TTL”. Nhưng một chiến dịch kết thúc lúc 00:00 UTC ngày 1/12/2026 cần `Instant`:

~~~java
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Instant deadline = Instant.parse("2026-12-01T00:00:00Z");

campaigns.upsert(
        "campaign::winter",
        JsonObject.create().put("name", "Winter"),
        UpsertOptions.upsertOptions().expiry(deadline)
);
~~~

Muốn “hết lúc bắt đầu ngày 1/12 theo giờ Việt Nam”:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Instant localMidnight = LocalDate.of(2026, 12, 1)
        .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
~~~

Hai mốc này **không giống nhau**: 00:00 theo giờ Việt Nam diễn ra sớm hơn 00:00 UTC bảy giờ. Nếu property cấu hình deadline, hãy dùng ISO-8601 có `Z`/offset rõ ràng, chẳng hạn:

~~~yaml
app:
  campaign:
    winter-end-at: "2026-12-01T00:00:00Z"
~~~

`Duration.ofDays(1)` không phải cách thay thế cho một ngày lịch đã định.

## 11. Thời hạn có thể khác nhau theo môi trường

Với profile test, có thể dùng TTL ngắn hơn để tích hợp test. Ví dụ một YAML gồm hai document:

~~~yaml
app:
  couchbase:
    expiration:
      cart: 30m
      otp: 5m
      session-idle: 15m
      session-absolute: 8h

---
spring:
  config:
    activate:
      on-profile: test-expiry

app:
  couchbase:
    expiration:
      cart: 30s
      otp: 10s
      session-idle: 20s
      session-absolute: 1m
~~~

Cần bảo đảm profile `test-expiry` **không** được bật tại production. Spring Boot có thứ tự ưu tiên giữa các property sources; muốn biết TTL cuối cùng, kiểm tra active profiles, environment và record đã bind, không chỉ nhìn file YAML mặc định.

### 11.1. Đổi config không đổi document đang tồn tại

Nếu team giảm `cart` từ `30m` xuống `15m`, document đã được ghi trước đó có thể vẫn giữ hạn cũ. `@ConfigurationProperties` chỉ cung cấp giá trị cho những thao tác áp dụng chính sách **sau khi thay đổi có hiệu lực**.

Khi cần rút ngắn TTL document cũ, hãy thiết kế migration/touch theo keyspace, kiểm soát tải và kiểm tra CAS. Không tự động touch toàn bộ collection mà chưa xem tác động nghiệp vụ.

## 12. Server `maxTTL` có thể giới hạn giá trị ứng dụng

Couchbase Server có thể đặt maximum TTL ở bucket hoặc collection, tùy phiên bản và policy. Đây là **cấu hình phía server**, không phải `app.*` property.

| Property ứng dụng | Chính sách server | Ý nghĩa cần kiểm chứng |
| --- | --- | --- |
| `cart: 30m` | Không có maxTTL ngắn hơn | Thường hết hạn sau khoảng 30 phút |
| `cart: 30m` | Collection maxTTL 10 phút | Server có thể rút ngắn thời gian |
| Không khai báo expiry | Collection maxTTL đã bật | Document vẫn có thể tự hết hạn |
| `otp: 5m` | Collection maxTTL 2 phút | OTP có thể hết sớm hơn yêu cầu |
| `product: 0s` | Bucket có maxTTL | Không bảo đảm sản phẩm không tự hết hạn |

~~~mermaid
flowchart LR
    A["YAML TTL = 30m"] --> B["Duration đã bind"]
    B --> C["Mutation options"]
    C --> D["Couchbase Server"]
    E["Bucket / Collection maxTTL"] --> D
    D --> F["Expiry metadata thực tế"]
~~~

Vì vậy **giá trị đã bind đúng không bảo đảm expiry cuối cùng đúng policy nghiệp vụ**. Cần kiểm tra cấu hình server và đọc metadata document. Thứ tự kế thừa maxTTL giữa bucket/collection phải được xác nhận với server version hiện hành.

## 13. Update: reset, preserve hay touch?

Giả sử document được ghi lúc 10:00 với TTL 15 phút và cập nhật lúc 10:10:

~~~text
10:00: tạo document với TTL 15 phút
10:15: deadline ban đầu
10:10: cập nhật một field
~~~

Có ba nhóm kết quả:

- **Reset:** đặt TTL 15 phút mới → deadline chuyển gần 10:25.
- **Preserve:** giữ expiry cũ → vẫn hết hạn gần 10:15.
- **Không chỉ định expiry:** kết quả phụ thuộc operation, mapper và server; không tự coi là preserve.

Ví dụ SDK preserve:

~~~java
import com.couchbase.client.java.kv.ReplaceOptions;

sessions.replace(
        sessionId,
        completeUpdatedJson,
        ReplaceOptions.replaceOptions().preserveExpiry(true)
);
~~~

Đây là minh họa khi `completeUpdatedJson` chứa nội dung document đầy đủ. `replace` không phải partial update. Preserve expiry **không** chống cập nhật cạnh tranh: nếu có hai writer, cần thêm CAS/`@Version` theo nghiệp vụ.

Gia hạn chủ động:

~~~java
carts.touch("cart::u-42", expiration.cart());
~~~

Chỉ gọi `touch` khi nghiệp vụ cho phép, ví dụ **sau khi sửa giỏ**. Nếu mỗi lần xem giỏ đều touch, TTL trở thành sliding trên mọi lượt đọc, khác với “30 phút sau lần sửa giỏ gần nhất”.

## 14. Session cần cả idle TTL và hard deadline

Một session có thể yêu cầu:

~~~yaml
app:
  couchbase:
    expiration:
      session-idle: 15m
      session-absolute: 8h
~~~

Giả sử `issuedAt` = 09:00, user hoạt động lúc 16:50. Idle deadline = 17:05; absolute deadline = 17:00. **Expiry hiệu lực phải là 17:00.**

Hàm tính deadline:

~~~java
import java.time.Duration;
import java.time.Instant;

static Instant effectiveDeadline(
        Instant issuedAt,
        Instant now,
        Duration idleTtl,
        Duration absoluteLifetime) {

    Instant idleDeadline = now.plus(idleTtl);
    Instant absoluteDeadline = issuedAt.plus(absoluteLifetime);

    return idleDeadline.isBefore(absoluteDeadline)
            ? idleDeadline
            : absoluteDeadline;
}
~~~

Nếu kết quả đã ở quá khứ, ứng dụng phải từ chối phiên theo chính sách; không được phát hành một session “mới” bằng cách âm thầm đặt lại `issuedAt`. Khi áp expiry của session vào SDK, nên sử dụng cùng `Instant` đã tính thay vì mỗi lần retry lại cộng một `Duration` mới.

## 15. Test riêng việc bind property, không cần Couchbase

Một unit test có thể chứng minh `30m` được diễn giải đúng, và do đó bắt lỗi `900` bị đọc thành mili giây ngay từ tầng cấu hình.

~~~java
import java.time.Duration;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class ExpirationPropertiesBindingTest {

    @Test
    void bindsExplicitTimeUnits() {
        var source = new MapConfigurationPropertySource(Map.of(
                "app.couchbase.expiration.cart", "30m",
                "app.couchbase.expiration.otp", "5m",
                "app.couchbase.expiration.session-idle", "15m",
                "app.couchbase.expiration.session-absolute", "8h"
        ));

        ExpirationProperties props = new Binder(source)
                .bind(
                        "app.couchbase.expiration",
                        Bindable.of(ExpirationProperties.class)
                )
                .orElseThrow();

        assertThat(props.cart()).isEqualTo(Duration.ofMinutes(30));
        assertThat(props.otp()).isEqualTo(Duration.ofMinutes(5));
        assertThat(props.sessionIdle()).isEqualTo(Duration.ofMinutes(15));
        assertThat(props.sessionAbsolute()).isEqualTo(Duration.ofHours(8));
    }
}
~~~

Bổ sung test cho thiếu property, zero, âm và chuỗi không parse được. Nếu business chọn không cho phép thời lượng dưới một giây, có thêm validation phần nano giây. Đây là **unit test configuration**, chưa kiểm tra Couchbase Server.

## 16. Kiểm chứng expiry metadata bằng Couchbase Java SDK

Sau khi ghi document, xác minh điều server đã áp dụng trên đúng collection:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = carts.get(
        "cart::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(deadline ->
        System.out.println("Document expiry: " + deadline)
);
~~~

API `withExpiry(true)` cho phép yêu cầu metadata ở các version SDK hỗ trợ. `expiryTime()` có kiểu tùy chọn; không tự suy rằng không có giá trị đồng nghĩa mọi API đều hiểu “không TTL”. Đọc Javadoc chính xác và so sánh với trạng thái server.

Một integration test có thể:

1. Tạo key riêng `ttl-test::UUID`.
2. Ghi document với `UpsertOptions.expiry(props.otp())`.
3. Đọc expiry metadata ngay sau khi ghi.
4. So sánh mốc expiry với khoảng thời gian dự kiến, có dung sai clock/độ phân giải.
5. Poll với deadline để kiểm chứng sau khi expiry đã qua, tránh assert ở một mili giây sát ranh giới.
6. Thử lại sau mutation preserve/touch để so sánh.
7. Kiểm tra hành vi ở collection có `maxTTL` đã biết.

Expiry logic và thu hồi vật lý không nhất thiết xảy ra cùng thời điểm. Test không nên dùng việc disk usage giảm như bằng chứng duy nhất cho TTL.

## 17. Reactive, retry và deadline

Ví dụ SDK reactive:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;
import reactor.core.publisher.Mono;

Mono<?> write = carts.reactive().upsert(
        "cart::u-42",
        JsonObject.create().put("itemCount", 2),
        UpsertOptions.upsertOptions()
                .expiry(expiration.cart())
);
~~~

Cần nhớ:

- Tạo `Mono` không đồng nghĩa mutation đã được thực thi; cần subscriber.
- Re-subscribe/retry có thể áp **TTL tương đối mới**, vô tình kéo dài deadline.
- Reactor `timeout(Duration.ofSeconds(2))` là pipeline timeout, không phải expiry của document.
- Cancellation không bảo đảm mutation đã gửi tới server được rollback.
- Trong WebFlux, tránh `block()` trên event-loop.

Với `AmbiguousTimeoutException` của mutation, client có thể không biết server đã ghi hay chưa. Không retry mù một nghiệp vụ như tạo OTP, tăng tồn kho hoặc trừ tiền; dùng idempotency key, CAS/`@Version` và đối soát kết quả.

## 18. Tình huống thực hành

Một `checkout-service` có:

~~~text
commerce.checkout.sessions
commerce.checkout.carts
commerce.checkout.otp_codes
commerce.catalog.products
~~~

Yêu cầu:

- OTP: 5 phút từ khi phát hành, không gia hạn sau lần nhập sai.
- Cart: 30 phút từ lần sửa giỏ gần nhất.
- Session: idle 15 phút, absolute lifetime tối đa 8 giờ.
- Product: không tự hết hạn.
- Collection `otp_codes` có `maxTTL` 2 phút.
- Một developer viết `app.couchbase.expiration.otp: 300` và tưởng đó là 300 giây.

**Hãy giải quyết:**

1. Viết lại `300` thành `5m` hoặc `300s` khi bind `Duration`.
2. Xây dựng `ExpirationProperties` và validation để tránh TTL thiếu/âm/zero.
3. Giải thích vì sao `maxTTL` 2 phút có thể khiến OTP hết trước chính sách 5 phút.
4. So sánh `@Document(expiry = 300)`, expiry expression theo version và SDK `expiry(Duration)`.
5. Thiết kế update OTP bảo toàn deadline, không tự gia hạn bởi retry.
6. Chỉ gia hạn cart khi có sự kiện sửa giỏ hợp lệ.
7. Tính hạn session bằng `min(now + idleTTL, issuedAt + absoluteLifetime)`.
8. Viết một unit test cho binder và một integration test đọc expiry metadata.
9. Giải thích vì sao thay config không tự điều chỉnh document đã ghi trước đó.

**Đáp án định hướng:** giá trị property cần đúng đơn vị và được code sử dụng thực sự; server policy có thể giới hạn TTL; deadline cố định phải được giữ khi update/retry; test ở hai tầng configuration và server mới phát hiện đủ lỗi.

## 19. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân khả dĩ | Giải pháp |
| --- | --- | --- |
| TTL 15 phút thành dưới 1 giây | Bind `900` như mili giây | Dùng `900s` hoặc `15m` |
| `@Document(expiry)` không đổi theo YAML | Annotation numeric cần constant | Chọn expression theo version hoặc SDK/service |
| `app.*` property không tác động | Không có code sử dụng | Kiểm tra binder và mutation |
| TTL đúng ở local, sai staging | Profile/biến môi trường khác | Kiểm tra nguồn property thực tế |
| TTL server ngắn hơn YAML | `maxTTL` bucket/collection | Kiểm tra chính sách server |
| OTP sống lâu hơn 5 phút | Update/reset/touch hoặc retry | Preserve expiry/absolute deadline |
| Expiry expression không biên dịch | Version API khác | Đọc dependency Javadoc |
| Expression biên dịch nhưng TTL sai | Kiểu kết quả/resolve không đúng | Đọc expiry metadata |
| Cart kéo dài vô hạn | Touch ở mọi lượt xem | Chỉ touch theo sự kiện hợp lệ |
| Deadline theo ngày lịch lệch giờ | Nhầm `Duration` và timezone | `LocalDate` + `ZoneId` + `Instant` |
| Reactive ghi không chạy | Publisher chưa subscribe | Kiểm tra subscription/error |
| KV còn document nhưng SQL++ không thấy | Query/index/consistency | Chẩn đoán Query riêng |
| Document hết hạn nhưng disk chưa giảm | Purge vật lý không đồng thời | Kiểm tra metrics server |

## 20. Checklist trước production

- [ ] Mọi `Duration` trong YAML có suffix thời gian tường minh.
- [ ] Không nhầm đơn vị giây của `@Document(expiry)` với đơn vị mặc định của Boot Duration.
- [ ] `app.couchbase.expiration.*` được bind và dùng trong thao tác ghi.
- [ ] Có validation cho TTL thiếu, 0, âm, quá nhỏ và quá lớn.
- [ ] Một chính sách TTL có một nguồn giá trị chủ đạo.
- [ ] `expiryExpression` chỉ được dùng sau khi xác nhận version/API.
- [ ] Đã phân biệt relative `Duration` với absolute `Instant`.
- [ ] Quy tắc ngày lịch/UTC/timezone được diễn đạt rõ.
- [ ] Đã đối chiếu `maxTTL` của bucket và collection.
- [ ] Reset, preserve, touch và retry có chính sách riêng theo entity.
- [ ] Đã xét hard deadline cho sliding session khi cần.
- [ ] Có unit test binding và integration test expiry metadata.
- [ ] Profile test không bật nhầm trong production.
- [ ] Thay đổi property đã tính đến document cũ.
- [ ] CAS, transaction deadline và KV/Query timeout không bị nhầm với TTL.
- [ ] Không dùng TTL làm cam kết xóa vật lý tức thời khỏi backup/replica.

## 21. Tổng kết

**Đơn vị thời gian là một phần của hợp đồng dữ liệu.** `@Document(expiry = 900)` thường có nghĩa 900 **giây**, trong khi `Duration` từ Spring Boot nên được viết `15m` hoặc `900s` thay vì `900` không rõ đơn vị. `Duration` là thời lượng tương đối; `Instant` là thời điểm tuyệt đối.

Property `app.couchbase.expiration.*` không tự áp TTL: ứng dụng phải bind, validate và truyền nó vào SDK hoặc cơ chế mapper expression mà **Spring Data version hiện tại hỗ trợ**. Expiry hiệu lực còn chịu `maxTTL` và hành vi reset/preserve khi document được cập nhật.

Khi thống nhất nguồn cấu hình và kiểm chứng metadata trên Couchbase Server, hệ thống có thể vận hành TTL ổn định bên cạnh repository, `CouchbaseTemplate`, SQL++ index, CAS, giao dịch và reactive API mà không đánh đổi tính đúng đắn dữ liệu.

