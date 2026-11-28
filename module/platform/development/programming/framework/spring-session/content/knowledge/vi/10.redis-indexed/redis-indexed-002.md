# @EnableRedisIndexedHttpSession và lựa chọn repository theo phiên bản

Spring Session có thể lưu `HttpSession` trong Redis để nhiều instance Spring cùng tra cứu một phiên. Redis có hai hướng repository cần phân biệt: repository cơ bản tối ưu cho thao tác theo session ID và repository có chỉ mục hỗ trợ tìm phiên theo principal. Từ Spring Session 3.5, hai lựa chọn này được thể hiện rõ qua `@EnableRedisHttpSession` và `@EnableRedisIndexedHttpSession`. Việc chọn annotation hoặc cấu hình Boot không đúng phiên bản có thể làm mất khả năng tra cứu session theo người dùng dù ứng dụng vẫn khởi động và đăng nhập bình thường.

Bài này giải thích khác biệt giữa repository Redis có chỉ mục và không có chỉ mục, cách chọn theo phiên bản Spring Session/Spring Boot, cách cấu hình tường minh và cách kiểm tra tính năng sau khi nâng cấp.

## 1. Vì sao có hai loại Redis session repository?

Spring Session tách API `HttpSession` khỏi nơi lưu dữ liệu. Trong ứng dụng Servlet, `SessionRepositoryFilter` đọc session ID từ request, tìm session trong repository và ghi các thay đổi trở lại kho dữ liệu. Với Redis, repository dùng `RedisConnectionFactory` để thao tác với Redis.

Một ứng dụng có thể chỉ cần các thao tác cơ bản:

- Tìm session theo ID do client gửi.
- Tạo session mới.
- Lưu thay đổi thuộc tính.
- Xóa session khi logout hoặc invalidate.
- Áp dụng thời hạn không hoạt động.

Những nhu cầu này không nhất thiết cần chỉ mục theo người dùng. Tuy nhiên, một số nghiệp vụ cần tìm tất cả session đang hoạt động của một principal, chẳng hạn:

- Hiển thị danh sách thiết bị đang đăng nhập.
- Giới hạn số phiên đăng nhập đồng thời.
- Đăng xuất người dùng khỏi mọi thiết bị.
- Thu hồi các phiên của một tài khoản khi có sự cố bảo mật.
- Tích hợp Spring Security với `SpringSessionBackedSessionRegistry` để quản lý phiên đồng thời.

Repository có chỉ mục duy trì thêm dữ liệu để hỗ trợ các truy vấn này. Chi phí đó cần được cân nhắc theo lưu lượng và nhu cầu nghiệp vụ.

## 2. Hai repository và khác biệt chức năng

Spring Session Redis có hai implementation chính:

| Repository | Chức năng chính | Khi nên cân nhắc |
|---|---|---|
| `RedisSessionRepository` | Lưu và tìm session theo session ID; không duy trì principal index | Ứng dụng chỉ cần tiếp tục phiên bằng ID, không cần tìm session theo người dùng |
| `RedisIndexedSessionRepository` | Lưu session và duy trì chỉ mục, trong đó có thể tìm theo principal | Ứng dụng cần liệt kê hoặc thu hồi session theo tài khoản, hoặc tích hợp quản lý phiên đồng thời |

Cả hai đều có thể dùng Redis dùng chung giữa nhiều instance. Sự khác biệt không nằm ở việc repository nào “cluster” hơn; khác biệt chính là khả năng lập chỉ mục và các cơ chế phụ trợ đi kèm.

`RedisSessionRepository` thường có cấu trúc đơn giản hơn và ít chi phí duy trì chỉ mục. `RedisIndexedSessionRepository` cần cập nhật các key/index phụ trợ khi session được tạo, thay đổi principal hoặc bị xóa. Điều đó làm tăng số thao tác Redis và dung lượng lưu trữ, nhưng đổi lại hỗ trợ truy vấn theo principal.

Không nên chọn repository indexed chỉ vì ứng dụng chạy nhiều instance. Nếu mọi request đều đã có session ID và chỉ cần tra cứu đúng phiên đó, repository cơ bản có thể đáp ứng. Chọn indexed khi có yêu cầu thực tế về tra cứu theo người dùng hoặc tính năng phụ thuộc vào interface indexed.

## 3. Thay đổi quan trọng từ Spring Session 3.5

Tên annotation có ý nghĩa khác nhau tùy phiên bản. Đây là điểm cần kiểm tra đầu tiên khi nâng cấp.

| Phiên bản Spring Session | Annotation | Repository được cấu hình |
|---|---|---|
| Trước 3.5 | `@EnableRedisHttpSession` | `RedisIndexedSessionRepository` |
| Từ 3.5 trở lên | `@EnableRedisHttpSession` | `RedisSessionRepository` (không indexed) |
| Từ 3.5 trở lên | `@EnableRedisIndexedHttpSession` | `RedisIndexedSessionRepository` |

Từ Spring Session 3.5, annotation `@EnableRedisIndexedHttpSession` được dùng để yêu cầu rõ repository indexed. `@EnableRedisHttpSession` chọn repository Redis cơ bản. Vì vậy, ứng dụng cũ đang dùng `@EnableRedisHttpSession` và dựa vào `findByPrincipalName` hoặc tính năng quản lý phiên theo principal cần rà soát khi nâng cấp lên 3.5.

Nếu nâng dependency nhưng giữ nguyên annotation cũ, ứng dụng có thể tiếp tục tạo session và đọc session theo ID thành công, trong khi tính năng tìm session theo principal không còn được cung cấp. Đây là kiểu thay đổi dễ lọt qua kiểm thử đăng nhập cơ bản.

Bảng trên áp dụng cho các annotation của Spring Session Redis. Cấu hình auto-configuration của Spring Boot có thể chọn repository thông qua thuộc tính riêng; cần phân biệt annotation cấu hình tường minh với lựa chọn tự động của Boot.

## 4. Dùng @EnableRedisIndexedHttpSession trong cấu hình Servlet

Khi ứng dụng cần repository indexed và muốn bật cấu hình tường minh, có thể dùng annotation mới:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisIndexedHttpSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisIndexedHttpSession(
        maxInactiveIntervalInSeconds = 1800,
        redisNamespace = "shop:session"
)
public class RedisSessionConfiguration {
}
```

`maxInactiveIntervalInSeconds` đặt thời gian không hoạt động tối đa của session, tính bằng giây. Ví dụ `1800` tương ứng 30 phút. `redisNamespace` tách key của ứng dụng khỏi ứng dụng khác dùng cùng Redis.

Cấu hình này cần một `RedisConnectionFactory` hợp lệ. Trong Spring Boot, bean factory thường được tạo từ cấu hình Redis nếu dependency và auto-configuration tương ứng có mặt. Ví dụ:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD:}
```

Nếu ứng dụng tự tạo `RedisConnectionFactory`, cần bảo đảm cấu hình pool, TLS, xác thực, timeout và topology Redis phù hợp với môi trường. Annotation không tự tạo Redis server và không thay thế việc cấu hình kết nối.

Các thuộc tính của annotation có thể thay đổi theo phiên bản. Hãy kiểm tra Javadoc của đúng phiên bản Spring Session được quản lý bởi dự án, đặc biệt nếu ứng dụng dùng thêm flush mode, save mode, cleanup cron hoặc serializer.

## 5. Dùng @EnableRedisHttpSession khi chỉ cần repository cơ bản

Từ Spring Session 3.5 trở lên, nếu ứng dụng chỉ cần lưu và tìm session theo ID, có thể dùng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisHttpSession(
        maxInactiveIntervalInSeconds = 1800,
        redisNamespace = "shop:session"
)
public class RedisSessionConfiguration {
}
```

Cấu hình này chọn `RedisSessionRepository` trong dòng Spring Session 3.5+. Không nên dùng nó khi nghiệp vụ cần principal index, nếu không có cơ chế lập chỉ mục khác được thiết kế và kiểm thử riêng.

Với các phiên bản Spring Session trước 3.5, `@EnableRedisHttpSession` cấu hình `RedisIndexedSessionRepository`. Không thể áp dụng kết luận của phiên bản mới cho ứng dụng cũ. Hãy kiểm tra phiên bản dependency đang chạy trước khi diễn giải annotation.

Không khai báo đồng thời `@EnableRedisHttpSession` và `@EnableRedisIndexedHttpSession` trong cùng một ApplicationContext. Hai cấu hình cùng cố gắng thiết lập cơ chế Redis session, có thể gây trùng bean hoặc tạo cấu hình không rõ ràng.

## 6. Chọn repository qua Spring Boot auto-configuration

Nếu ứng dụng dùng Spring Boot và muốn để Boot cấu hình session, có thể chọn loại repository bằng thuộc tính `spring.session.redis.repository-type` ở các phiên bản Boot hỗ trợ thuộc tính này, chẳng hạn dòng Boot 3.5 trở lên:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 30m
    redis:
      namespace: shop:session
      repository-type: indexed
```

Các giá trị repository type thường dùng là:

- `default`: repository Redis cơ bản, không indexed.
- `indexed`: repository `RedisIndexedSessionRepository`.

Thuộc tính này thuộc cấu hình auto-configuration của Spring Boot. Tên, giá trị hợp lệ và phiên bản hỗ trợ cần được xác minh trong configuration metadata của đúng phiên bản Boot. Không giả định một file `application.yml` của Boot cũ sẽ hiểu thuộc tính mới.

Khi dùng auto-configuration, thông thường không cần thêm `@EnableRedisHttpSession` hoặc `@EnableRedisIndexedHttpSession` vào lớp cấu hình ứng dụng. Chỉ dùng annotation nếu chủ động chọn cấu hình tường minh và đã hiểu auto-configuration nào sẽ back off.

Ví dụ dependency Maven cho Spring Session Redis:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
</dependencies>
```

Nên để Spring Boot dependency management quản lý phiên bản Spring Data Redis và Spring Session tương thích. Tránh nâng riêng `spring-session-data-redis` mà không kiểm tra tương thích với Spring Framework, Spring Data và Boot đang dùng.

## 7. Khi nào nghiệp vụ thật sự cần repository indexed?

Một dấu hiệu rõ ràng là ứng dụng cần tìm session theo principal. Interface `FindByIndexNameSessionRepository` cung cấp khả năng truy vấn theo tên index và giá trị index. Spring Session định nghĩa tên index principal phổ biến qua `PRINCIPAL_NAME_INDEX_NAME`.

Ví dụ khái quát:

```java
@Autowired
FindByIndexNameSessionRepository<? extends Session> sessions;

public Map<String, ? extends Session> sessionsFor(String principalName) {
    return sessions.findByPrincipalName(principalName);
}
```

Đoạn code trên giả định repository thực tế triển khai `FindByIndexNameSessionRepository`. Không phải mọi `SessionRepository` đều hỗ trợ method này.

Để principal index có dữ liệu, repository phải nhận diện được principal của session. Với Spring Security, Spring Session có thể tích hợp để xác định principal từ security context. Với ứng dụng tự quản lý đăng nhập, cần lưu hoặc cung cấp thông tin principal theo quy ước index mà repository sử dụng.

Không nên mặc định rằng session nào cũng được index chỉ vì repository là indexed. Hãy xác minh cách principal được ghi nhận trong session và kiểm tra truy vấn `findByPrincipalName` trả đúng kết quả trong integration test.

Một số ứng dụng không cần liệt kê session nhưng vẫn muốn giới hạn số phiên đồng thời. Khi đó có thể tích hợp Spring Security với `SpringSessionBackedSessionRegistry` nếu repository đáp ứng interface cần thiết. Tính năng này cần được kiểm tra end-to-end vì việc index principal là một phần quan trọng của cơ chế tìm các phiên đang hoạt động.

## 8. Chi phí và vận hành của repository indexed

Chỉ mục làm tăng chi phí lưu trữ và cập nhật. Khi session được tạo, thay đổi hoặc xóa, repository có thể cần cập nhật thêm key index và các cấu trúc phụ trợ. Với số lượng session lớn, cần tính đến:

- Số key Redis trên mỗi session.
- Kích thước session và thuộc tính principal.
- Số thao tác ghi bổ sung khi cập nhật index.
- Chi phí cleanup khi session hết hạn hoặc bị xóa.
- Bộ nhớ cho các key hết hạn và index phụ trợ.
- Độ trễ khi tìm session theo principal.

Namespace Redis cần tách theo ứng dụng và môi trường, ví dụ `shop:dev:session` và `shop:prod:session`. Các instance trong cùng cụm phải dùng cùng namespace, còn ứng dụng độc lập không nên vô tình chia sẻ namespace.

Không lưu đối tượng lớn hoặc dữ liệu nghiệp vụ không cần thiết trong session. Session càng lớn, chi phí đọc/ghi Redis càng cao và quá trình serialize/deserialize càng tốn thời gian. Chỉ mục theo principal không thay thế database nghiệp vụ hoặc một hệ thống quản lý thiết bị chuyên dụng.

## 9. Redis keyspace notifications và vòng đời session

`RedisIndexedSessionRepository` sử dụng các cơ chế Redis để xử lý thông tin hết hạn và phát các sự kiện vòng đời session. Một phần hành vi này dựa trên Redis keyspace notifications, đặc biệt là thông báo hết hạn key.

Redis có thuộc tính `notify-keyspace-events` để bật nhóm sự kiện cần thiết. Trong cấu hình Spring Session Redis, giá trị thường cần hỗ trợ sự kiện hết hạn và các sự kiện thao tác key tương ứng; `Egx` là một cấu hình thường gặp. Hãy đối chiếu tài liệu của đúng phiên bản và môi trường Redis trước khi thay đổi giá trị vì cấu hình này có thể ảnh hưởng các ứng dụng khác.

Một số dịch vụ Redis managed giới hạn lệnh `CONFIG SET`. Khi đó, cần bật keyspace notifications qua cấu hình của nhà cung cấp và thiết lập hành vi Spring Session không cố thay đổi cấu hình Redis nếu phiên bản đang dùng cung cấp tùy chọn tương ứng.

Không coi keyspace notification là hàng đợi bền vững. Subscriber có thể bỏ lỡ thông báo khi mất kết nối; thời điểm thông báo đến có thể trễ so với lúc TTL đạt ngưỡng. Nếu nghiệp vụ cần audit đầy đủ hoặc đảm bảo một side effect chỉ xảy ra một lần, hãy dùng outbox hoặc message broker bền vững và thiết kế idempotency.

Với repository cơ bản, không nên giả định các tính năng index hoặc event có cùng hành vi như repository indexed. Hãy kiểm tra API và tài liệu phiên bản đang chạy trước khi phụ thuộc vào event listener.

## 10. Nâng cấp từ phiên bản cũ: điều cần rà soát

Khi nâng Spring Session từ dòng trước 3.5 lên 3.5 trở lên, cần xác định ứng dụng đang dựa vào repository nào trước khi thay đổi dependency.

Quy trình rà soát:

1. Xác định phiên bản Spring Boot và phiên bản Spring Session thực tế trong runtime.
2. Tìm cấu hình `@EnableRedisHttpSession` hoặc auto-configuration Redis session đang sử dụng.
3. Kiểm tra mã nguồn có gọi `findByPrincipalName`, `findByIndexNameAndIndexValue` hoặc dùng `SpringSessionBackedSessionRegistry` không.
4. Xác định ứng dụng có cần session events hoặc tra cứu theo principal không.
5. Nếu cần index, dùng `@EnableRedisIndexedHttpSession` hoặc chọn `repository-type: indexed` trong Boot có hỗ trợ.
6. Nếu chỉ cần tra cứu theo session ID, repository cơ bản có thể phù hợp.
7. Kiểm tra namespace, cấu trúc key, serializer và khả năng tương thích dữ liệu khi triển khai rolling update.
8. Chạy integration test với session đã tồn tại và session mới trước khi phát hành.

Không giả định hai repository có thể đọc và ghi mọi dữ liệu session theo cùng một định dạng trong mọi phiên bản. Khi triển khai rolling update với nhiều instance, tránh để các phiên bản hoặc loại repository không tương thích cùng ghi vào một namespace. Có thể cần kế hoạch buộc đăng nhập lại, tách namespace hoặc chuyển đổi dữ liệu có kiểm soát tùy mức độ tương thích đã xác minh.

Nếu ứng dụng không còn dùng principal index, có thể chuyển sang repository cơ bản để giảm chi phí. Trước khi làm, hãy tìm toàn bộ điểm phụ thuộc ở tầng nghiệp vụ và Spring Security, rồi kiểm thử các chức năng quản lý phiên.

## 11. Các lỗi cấu hình thường gặp

### Dùng annotation cũ sau khi nâng lên Spring Session 3.5

Ứng dụng vẫn khởi động với `@EnableRedisHttpSession`, nhưng repository được cấu hình là loại không indexed theo semantics mới. Các tính năng cần principal index có thể không còn hoạt động. Kiểm tra loại bean thực tế và đổi sang `@EnableRedisIndexedHttpSession` khi cần.

### Dùng annotation không tồn tại trong phiên bản cũ

`@EnableRedisIndexedHttpSession` không có trong các dòng Spring Session trước khi annotation này được giới thiệu. Nếu compile báo không tìm thấy class, kiểm tra dependency và BOM trước khi đổi import hoặc tự tạo annotation thay thế.

### Chọn indexed nhưng principal index rỗng

Repository indexed không thể tìm session theo principal nếu không xác định được principal tương ứng. Kiểm tra session có lưu security context hoặc thuộc tính principal theo cơ chế mà repository hỗ trợ hay không. Kiểm tra thêm việc đăng nhập có thực sự tạo session và repository đã ghi index.

### Dùng thuộc tính Boot ở phiên bản không hỗ trợ

Một thuộc tính mới có thể bị bỏ qua hoặc không được bind trong Boot cũ. Kiểm tra configuration metadata và log binding; nếu cần, dùng cách cấu hình được phiên bản đó hỗ trợ.

### Bật auto-configuration và annotation tường minh cùng lúc

Cả hai cơ chế có thể cố tạo repository hoặc filter. Chọn một đường cấu hình rõ ràng và kiểm tra ApplicationContext chỉ có một repository cùng một `SessionRepositoryFilter` phù hợp.

### Các instance dùng repository type hoặc namespace khác nhau

Một instance có thể ghi session theo cơ chế hoặc namespace mà instance khác không đọc đúng. Đảm bảo cấu hình được triển khai đồng nhất trên toàn cụm trước khi đưa traffic vào.

## 12. Kiểm thử repository selection

Một bài kiểm thử khởi động đơn giản chưa đủ để chứng minh repository được chọn đúng. Nên kiểm tra cả loại bean và hành vi nghiệp vụ.

Với ứng dụng cần indexed repository:

- Xác nhận ApplicationContext có `RedisIndexedSessionRepository` hoặc bean triển khai `FindByIndexNameSessionRepository`.
- Tạo session gắn với một principal.
- Truy vấn `findByPrincipalName` và xác nhận session được tìm thấy.
- Xóa session và xác nhận truy vấn không còn trả phiên đó.
- Kiểm thử tính năng giới hạn session đồng thời nếu Spring Security sử dụng repository này.
- Kiểm tra Redis keyspace notifications nếu ứng dụng phụ thuộc event hết hạn.

Với repository cơ bản:

- Xác nhận bean là `RedisSessionRepository` trong phiên bản hỗ trợ implementation này.
- Tạo session, lưu thuộc tính và đọc lại bằng cùng session ID.
- Xác nhận request đến instance khác đọc được cùng session khi hai instance dùng chung Redis.
- Kiểm tra timeout, logout và xử lý lỗi Redis.
- Xác nhận ứng dụng không vô tình gọi API chỉ có ở repository indexed.

Có thể kiểm tra bean qua test ApplicationContext hoặc Spring Boot integration test. Với Redis, nên dùng Redis thật trong môi trường test, ví dụ container dùng chung cho test suite, để kiểm tra TTL, notification và cấu trúc dữ liệu thay vì chỉ mock repository.

## 13. Quyết định lựa chọn trong dự án

Dùng `RedisSessionRepository` khi ứng dụng cần lưu session dùng chung và truy xuất theo session ID, đồng thời không có yêu cầu tìm phiên theo principal. Dùng `RedisIndexedSessionRepository` khi cần tra cứu các phiên của người dùng, quản lý đăng nhập đồng thời hoặc chức năng dựa trên principal index.

Với Spring Session trước 3.5, `@EnableRedisHttpSession` cấu hình repository indexed. Từ Spring Session 3.5 trở lên, hãy dùng `@EnableRedisIndexedHttpSession` nếu cần indexed repository; dùng `@EnableRedisHttpSession` cho repository Redis cơ bản. Khi để Spring Boot auto-configure, chọn `spring.session.redis.repository-type` theo giá trị được phiên bản Boot hỗ trợ.

Trước khi nâng cấp, rà soát các API tìm session theo principal, cấu hình Spring Security, session events, namespace và dữ liệu đang tồn tại trong Redis. Chỉ khi repository, cấu hình và các instance trong cụm thống nhất, Spring Session mới duy trì được hành vi phiên dự kiến qua các lần triển khai.

