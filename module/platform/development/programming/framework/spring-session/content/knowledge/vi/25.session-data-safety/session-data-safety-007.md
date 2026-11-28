# Cách ly môi trường, namespace và giới hạn tài nguyên lưu phiên

Spring Session cho phép nhiều instance ứng dụng dùng chung HttpSession thông qua Redis hoặc JDBC. Khả năng chia sẻ này giúp request tiếp theo khôi phục được phiên dù được xử lý ở node khác, nhưng cũng tạo ra yêu cầu cách ly rõ ràng: dữ liệu của môi trường phát triển không được lẫn với staging hoặc production; hai ứng dụng không được vô tình đọc cùng namespace; tenant không được nhìn thấy session của tenant khác; và kho session phải có giới hạn tài nguyên để không làm ảnh hưởng toàn hệ thống.

Cách ly session không chỉ là đổi tên cookie. Cần kết hợp ranh giới hạ tầng, quyền truy cập, namespace hoặc schema, cấu hình cookie, chính sách TTL, giới hạn kích thước dữ liệu, giới hạn số phiên và giám sát dung lượng. Namespace giúp phân vùng khóa hoặc bảng; nó không tự tạo ra một ranh giới bảo mật nếu mọi ứng dụng vẫn dùng cùng credential có quyền đọc toàn bộ kho.

Bài học tập trung vào ứng dụng Servlet dùng Spring Session với Redis hoặc JDBC. Các ví dụ cấu hình cần được đối chiếu với phiên bản Spring Boot/Spring Session của dự án, đặc biệt khi dùng auto-configuration hoặc annotation configuration.

## 1. Vì sao phải cách ly dữ liệu session?

Session thường chứa trạng thái có ý nghĩa bảo mật: SecurityContext, thông tin xác thực, CSRF token, thông tin giỏ hàng, tiến độ quy trình và các thuộc tính tạm thời khác. Nếu nhiều môi trường hoặc ứng dụng dùng chung một vùng lưu trữ mà không có phân vùng, có thể phát sinh các sự cố:

- Một ứng dụng đọc được session do ứng dụng khác tạo.
- Dữ liệu kiểm thử xuất hiện trong production.
- Một bản triển khai mới deserialize session theo class hoặc format không tương thích.
- Một tenant truy cập trạng thái của tenant khác do lỗi authorization hoặc tra cứu.
- Một môi trường test xóa nhầm session của môi trường đang hoạt động.
- Một ứng dụng tiêu thụ hết RAM Redis hoặc connection pool JDBC của ứng dụng khác.
- Cleanup job của một môi trường tác động đến bảng session của môi trường khác.

Session ID có entropy cao giúp khó đoán định danh, nhưng không thay thế cách ly. Nếu cookie bị lộ, namespace dùng chung hoặc credential quá rộng có thể làm tăng phạm vi ảnh hưởng. Cần thiết kế để một lỗi cấu hình hoặc thao tác vận hành chỉ ảnh hưởng đến đúng ứng dụng và môi trường.

## 2. Các lớp cách ly nên phối hợp

Một mô hình tốt dùng nhiều lớp độc lập:

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| Hạ tầng | Tách blast radius và tải tài nguyên | Redis riêng, database riêng, network policy |
| Credential | Giới hạn quyền đọc/ghi | Redis ACL, database user theo môi trường |
| Namespace/schema | Phân vùng dữ liệu | orders:prod:sessions, schema app_prod |
| Cookie | Tránh browser gửi nhầm credential | Cookie name, Domain, Path riêng |
| Ứng dụng | Giới hạn truy cập theo principal/tenant | Authorization theo tenant ID |
| Phiên bản | Quản lý thay đổi format | Serializer tương thích khi rolling deploy |
| Tài nguyên | Ngăn một client chiếm quá nhiều dung lượng | TTL, quota thuộc tính, giới hạn session đồng thời |
| Vận hành | Phát hiện tăng trưởng bất thường | Metrics, alert, cleanup và runbook |

Không phải hệ thống nào cũng cần Redis hoặc database riêng cho từng ứng dụng. Nhưng production và non-production nên có ranh giới hạ tầng/credential rõ ràng. Nếu phải chia sẻ một cụm, cần namespace riêng, ACL phù hợp, schema/table riêng và quy trình thay đổi có kiểm soát.

## 3. Cách ly môi trường: dev, test, staging và production

Mỗi môi trường nên có cấu hình session độc lập. Ví dụ, ứng dụng bán hàng có thể dùng các namespace:

- shop:dev:spring-session
- shop:test:spring-session
- shop:staging:spring-session
- shop:prod:spring-session

Với JDBC, có thể dùng database hoặc schema riêng, hoặc ít nhất tên bảng riêng theo môi trường. Credential của dev không nên có quyền truy cập schema production.

Ví dụ cấu hình Redis qua Spring Boot:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: shop:prod:spring-session
  data:
    redis:
      host: redis-prod.internal
      port: 6379
~~~

Tên host chỉ là ví dụ. Mỗi môi trường cần nhận endpoint và secret từ cấu hình triển khai hoặc secret manager. Không commit mật khẩu production vào file cấu hình trong repository.

Nếu dùng Java configuration, có thể đặt namespace trong annotation:

~~~java
@Configuration
@EnableRedisHttpSession(
    redisNamespace = "shop:prod:spring-session",
    maxInactiveIntervalInSeconds = 1800
)
public class SessionConfiguration {
}
~~~

Không cấu hình đồng thời annotation và auto-configuration theo cách tạo hai SessionRepositoryFilter hoặc hai repository cạnh tranh. Chọn một mô hình cấu hình rõ ràng và kiểm tra bean thực tế của ứng dụng.

## 4. Namespace Redis làm gì?

Spring Session Redis dùng namespace để tạo tiền tố cho các key mà repository quản lý. Namespace mặc định của Spring Session Redis thường là spring:session. Khi nhiều ứng dụng dùng chung một Redis, giữ nguyên namespace mặc định có thể khiến chúng truy cập cùng vùng dữ liệu nếu session ID trùng hoặc nếu một ứng dụng biết ID của phiên thuộc ứng dụng khác.

Đặt namespace riêng cho từng ứng dụng và môi trường giúp phân vùng key:

~~~java
@EnableRedisHttpSession(redisNamespace = "billing:prod:spring-session")
class BillingSessionConfiguration {
}
~~~

Namespace nên:

- Ổn định qua các lần triển khai tương thích.
- Phân biệt môi trường và ứng dụng.
- Không chứa dữ liệu người dùng hoặc giá trị lấy trực tiếp từ request.
- Có quy ước đặt tên được quản lý tập trung.
- Được dùng nhất quán trên mọi instance của cùng một cụm ứng dụng.

Không đưa version build vào namespace một cách mặc định. Nếu mỗi release dùng namespace mới, mọi session cũ sẽ trở nên không thể tìm thấy sau khi chuyển traffic; người dùng bị đăng xuất hàng loạt. Chỉ đổi namespace khi chủ đích là tạo vùng session mới và đã chấp nhận việc kết thúc các phiên cũ hoặc có kế hoạch migration.

## 5. Namespace không phải ranh giới bảo mật

Namespace chủ yếu là quy ước phân vùng key. Nếu mọi ứng dụng dùng cùng một Redis credential có quyền GET, SET, DEL trên toàn bộ keyspace, lỗi trong một ứng dụng vẫn có thể đọc hoặc xóa dữ liệu của ứng dụng khác.

Để cách ly mạnh hơn, phối hợp namespace với:

- Redis ACL user riêng, giới hạn command và key pattern phù hợp.
- Network policy chỉ cho workload cần thiết kết nối Redis.
- Credential riêng cho production và non-production.
- Redis instance/cluster riêng nếu yêu cầu bảo mật hoặc blast radius cao.
- Audit và quản lý secret rotation.
- Không cấp quyền quản trị Redis cho application user.

Khi dùng ACL key pattern, hãy xác minh các key thực tế do phiên bản Spring Session tạo ra, bao gồm key session, expiration và index. Không đoán pattern rồi áp dụng trong production; pattern quá hẹp có thể làm session event hoặc index không hoạt động, pattern quá rộng làm mất ý nghĩa phân quyền.

Nếu yêu cầu cách ly nghiêm ngặt, Redis riêng hoặc cluster riêng thường dễ chứng minh hơn việc chỉ dựa vào prefix.

## 6. Redis database index và Redis Cluster

Redis standalone có thể hỗ trợ nhiều logical database index, nhưng chúng vẫn dùng chung tiến trình và tài nguyên. Logical DB không cung cấp cách ly RAM, CPU, eviction, persistence hoặc quyền truy cập mạnh như instance riêng.

Redis Cluster chỉ hỗ trợ database index 0. Không dùng SELECT để tách môi trường trong Redis Cluster; dùng key namespace và ACL hoặc cluster riêng.

Một quy tắc thực tế:

| Kiểu triển khai | Cách phân vùng nên dùng |
|---|---|
| Redis standalone nhỏ | Namespace riêng; logical DB có thể bổ sung phân vùng nhưng không thay ACL |
| Redis Sentinel | Namespace riêng, credential và topology theo môi trường |
| Redis Cluster | Namespace/key prefix, ACL; cluster riêng khi cần cách ly mạnh |
| Redis dùng chung nhiều workload | Cân nhắc instance riêng cho session để tránh eviction/tải chéo |

Không coi logical DB index là cơ chế bảo vệ production khỏi lệnh FLUSHALL, quá tải bộ nhớ hoặc lỗi cấu hình toàn Redis process.

## 7. Cách ly Spring Session JDBC

Với JDBC, Spring Session tạo và sử dụng các bảng session cùng bảng attributes. Schema chuẩn thường có bảng SPRING_SESSION và SPRING_SESSION_ATTRIBUTES. Nếu nhiều ứng dụng hoặc môi trường dùng chung database mà không phân vùng, nguy cơ va chạm tên bảng và cleanup nhầm là đáng kể.

Có thể đặt tên bảng riêng:

~~~java
@Configuration
@EnableJdbcHttpSession(
    tableName = "SHOP_PROD_SESSION",
    maxInactiveIntervalInSeconds = 1800
)
public class JdbcSessionConfiguration {
}
~~~

Tên bảng attributes thường được suy ra theo quy ước từ tên bảng session của repository. Khi đổi table name, hãy tạo schema đúng theo script tương ứng và kiểm tra cả bảng attributes, index và foreign key nếu database sử dụng chúng.

Với Spring Boot, cấu hình table name có thể được khai báo qua property spring.session.jdbc.table-name tùy phiên bản. Cần kiểm tra metadata cấu hình của phiên bản thực tế thay vì sao chép property từ một dòng Boot khác.

Các mức cách ly JDBC:

1. Database riêng cho từng môi trường.
2. Schema riêng cho từng ứng dụng/môi trường.
3. Table name riêng khi không thể tách database/schema.
4. Database user chỉ có quyền trên đúng schema/table cần thiết.

Một table prefix riêng không thay thế quyền truy cập database. Nếu application user vẫn có quyền SELECT toàn bộ schema, ứng dụng vẫn có thể đọc session của ứng dụng khác bằng SQL.

## 8. Migration schema và quyền database

Spring Session JDBC phụ thuộc schema chính xác. Khi triển khai, cần quản lý schema bằng migration hoặc quy trình database deployment đã kiểm soát.

Hãy xác nhận:

- Bảng session và bảng attributes tồn tại đúng tên.
- Kiểu cột phù hợp với script của phiên bản Spring Session.
- Index trên session ID và expiry hỗ trợ truy vấn/cleanup.
- Quyền SELECT/INSERT/UPDATE/DELETE được cấp đúng phạm vi.
- Cleanup job chỉ tác động đến bảng thuộc ứng dụng/môi trường.
- Migration được thực hiện trước khi application mới nhận traffic.
- Rollback và backup có xét đến dữ liệu session tạm thời.

Không để nhiều ứng dụng tự chạy schema initialization trên cùng database production nếu chúng có thể ghi đè hoặc tạo cấu trúc không tương thích. Production thường nên dùng migration có version và quyền DDL tách khỏi credential runtime.

Session thường là dữ liệu tạm thời, nên restore database backup cũ có thể khôi phục session đã logout hoặc làm trạng thái phiên không khớp với các hệ thống bảo mật khác. Hãy xác định rõ có nên backup/restore session data cùng database nghiệp vụ hay không.

## 9. Cookie cần được cách ly cùng với namespace

Cookie session ID là phần định danh mà browser gửi lên server. Nếu hai ứng dụng chạy trên cùng host hoặc subdomain và cùng dùng tên cookie, Path hoặc Domain rộng, browser có thể gửi cookie đến ứng dụng không mong muốn.

Spring Session Servlet thường dùng DefaultCookieSerializer để cấu hình cookie. Ví dụ:

~~~java
@Bean
public CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SHOP_PROD_SESSION");
    serializer.setCookiePath("/");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
~~~

Các điểm cần thiết kế:

- Cookie name khác nhau khi nhiều ứng dụng cùng host cần cookie riêng.
- Domain càng hẹp càng tốt; chỉ chia sẻ subdomain khi có yêu cầu rõ.
- Path chỉ bao phủ ứng dụng cần cookie.
- Secure bật trong production để chỉ gửi qua HTTPS.
- HttpOnly bật để JavaScript không đọc session ID.
- SameSite phù hợp với luồng đăng nhập, redirect và kiến trúc cross-site.
- Không dùng cookie domain .example.com nếu không cần mọi subdomain nhận credential.

Cookie name khác nhau không tự cách ly Redis/JDBC. Namespace khác nhau cũng không ngăn browser gửi nhầm cookie nếu cookie scope sai. Cần cấu hình cả hai phía.

## 10. Tách môi trường trong browser và pipeline kiểm thử

Staging và production có thể cùng dùng một domain gốc nhưng nên dùng host riêng, ví dụ staging.example.test và app.example.com, với cookie name và domain policy phù hợp.

Không để browser automation dùng chung profile cho test và production. Cookie jar của test có thể chứa session ID từ môi trường khác, gây lỗi khó hiểu hoặc gửi credential sai host nếu cấu hình Domain quá rộng.

Trong CI:

- Dùng Redis/database ephemeral hoặc namespace duy nhất cho mỗi test run.
- Tạo dữ liệu session bằng test fixture riêng.
- Dọn namespace test sau khi test kết thúc, chỉ bằng credential test.
- Không chạy FLUSHDB/FLUSHALL trên Redis dùng chung.
- Không dùng session cookie production trong test.
- Không copy session dump production sang staging nếu chưa có quy trình bảo vệ dữ liệu và ẩn danh.
- Kiểm thử song song phải có namespace tách biệt để không xóa dữ liệu của job khác.

Nếu test chạy đồng thời trên cùng Redis, có thể thêm build ID hoặc run ID vào namespace của test. Điều này phù hợp với môi trường test ngắn hạn; không áp dụng tùy tiện cho production vì làm session bị phân mảnh sau mỗi lần deploy.

## 11. Namespace theo tenant: khi nào cần?

Trong một ứng dụng multi-tenant, một HttpSession thường gắn với một browser/client và có thể chứa tenant đang được chọn. Không nhất thiết tạo Redis namespace riêng cho từng tenant. Namespace thường phù hợp hơn với ranh giới ứng dụng và môi trường.

Ví dụ namespace theo tenant có thể tạo ra nhiều vùng key và phức tạp vận hành nếu có hàng nghìn tenant. Hơn nữa, namespace động từ tenant ID trong request có thể tạo nguy cơ nếu tenant chưa được xác minh hoặc nếu code cho phép client chọn tùy ý.

Thông thường:

- Dùng namespace riêng cho application/environment.
- Lưu tenant ID đã được xác minh trong SecurityContext hoặc session attribute nếu cần.
- Kiểm tra tenant authorization ở mỗi thao tác nghiệp vụ.
- Không tin tenant ID chỉ vì nó nằm trong session.
- Không dùng namespace làm thay thế cho kiểm soát truy cập dữ liệu.
- Nếu tenant có yêu cầu cách ly dữ liệu pháp lý hoặc bảo mật đặc biệt, đánh giá store/schema riêng hoặc tenant-specific encryption/access policy.

Session ID chỉ giúp tìm session. Nó không chứng minh principal được phép truy cập mọi tenant có thể được chọn trong ứng dụng.

## 12. Cách ly phiên bản và serializer

Spring Session lưu thuộc tính session ngoài JVM, do đó các instance phải deserialize dữ liệu tương thích. Trong rolling deployment, instance cũ và mới có thể cùng đọc/ghi session trong một khoảng thời gian.

Nếu session chứa class Java tùy chỉnh, thay đổi package, field, serialVersionUID hoặc kiểu thuộc tính có thể làm phiên cũ không deserialize được. Nếu dùng JSON serializer, thay đổi type metadata hoặc cấu trúc JSON cũng có thể gây lỗi.

Các nguyên tắc:

- Chỉ lưu các kiểu dữ liệu ổn định, nhỏ và cần thiết.
- Ưu tiên DTO đơn giản, có version hoặc schema evolution rõ.
- Tránh lưu entity JPA, proxy, service bean hoặc object graph lớn.
- Đảm bảo các node trong cùng rollout có serializer tương thích.
- Không thay serializer đồng thời với thay namespace mà không có kế hoạch chuyển đổi.
- Nếu thay đổi không tương thích, chấp nhận invalidate session có chủ đích hoặc thực hiện migration có kiểm thử.
- Không trộn nhiều phiên bản ứng dụng không tương thích vào cùng namespace.

Tạo namespace theo release có thể tránh deserialize chéo nhưng cũng khiến mọi session của release trước mất khả năng truy cập. Đây là một lựa chọn migration, không phải cách versioning mặc định.

## 13. Giới hạn thời gian sống của session

TTL là giới hạn tài nguyên cơ bản. Session không nên tồn tại lâu hơn nhu cầu sản phẩm.

Với Spring Boot, có thể đặt timeout chung:

~~~yaml
spring:
  session:
    timeout: 30m
~~~

Với Redis annotation configuration:

~~~java
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
class SessionConfiguration {
}
~~~

Với JDBC, cấu hình timeout tương ứng qua Spring Session JDBC hoặc property phù hợp của Boot.

Cần phân biệt:

| Thời hạn | Ý nghĩa |
|---|---|
| Idle timeout | Hết hạn sau khoảng không hoạt động |
| Absolute lifetime | Tuổi thọ tối đa kể từ lúc tạo/xác thực, cần policy bổ sung nếu muốn |
| Cookie Max-Age | Browser giữ session ID trong bao lâu |
| Remember-me validity | Thời hạn credential ghi nhớ của Spring Security |
| Redis TTL/JDBC expiry | Cơ chế lưu trữ và dọn dữ liệu theo repository |

Spring Session quản lý idle timeout. Nếu yêu cầu absolute lifetime, ứng dụng cần kiểm tra creation time hoặc mốc xác thực mạnh tại tầng bảo mật. Không gia hạn vô hạn chỉ vì background heartbeat hoặc request kỹ thuật.

## 14. Giới hạn số phiên trên mỗi người dùng

Một người dùng có thể mở nhiều browser profile hoặc thiết bị. Nếu không có giới hạn, tài khoản bị lạm dụng có thể tạo rất nhiều session, làm tăng bộ nhớ Redis hoặc số hàng JDBC.

Spring Security hỗ trợ giới hạn session đồng thời thông qua maximumSessions. Ví dụ:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(3)
);
~~~

Ví dụ giới hạn ba phiên đồng thời trên mỗi principal. Trong môi trường nhiều instance, cần SessionRegistry phù hợp với Spring Session repository, chẳng hạn SpringSessionBackedSessionRegistry và repository hỗ trợ tìm theo principal.

Không dùng SessionRegistry chỉ lưu trong bộ nhớ một JVM để giả định giới hạn toàn cụm. Hãy xác nhận index principal được cập nhật, session registry chia sẻ được trạng thái và hành vi khi hai login diễn ra đồng thời.

Giới hạn session theo principal khác giới hạn device registration. Nếu sản phẩm cần mỗi thiết bị một phiên, cần một model thiết bị riêng và logic thu hồi theo device ID đã đăng ký.

## 15. Giới hạn kích thước và số lượng thuộc tính session

Spring Session không cung cấp một quota phổ quát tự động cho số byte của mỗi session hoặc số thuộc tính mà ứng dụng được phép lưu. Ứng dụng phải thiết kế giới hạn ở tầng nghiệp vụ hoặc custom repository nếu cần.

Một session quá lớn có thể làm:

- Tăng Redis memory và network traffic.
- Tăng dung lượng bảng attributes trong JDBC.
- Tăng latency serialize/deserialize.
- Tăng thời gian save mỗi request.
- Làm replication và backup tốn kém.
- Tăng nguy cơ request đồng thời ghi đè object lớn.

Nên đặt các quy tắc:

- Giới hạn số thuộc tính được phép lưu.
- Giới hạn độ dài chuỗi và số phần tử collection.
- Giới hạn kích thước serialized payload cho các thuộc tính lớn.
- Không lưu file, ảnh, nội dung tài liệu hoặc dữ liệu binary lớn trong session.
- Không lưu toàn bộ entity graph.
- Không lưu cache có thể tái tạo hoặc dữ liệu nguồn chuẩn.
- Chỉ lưu ID/reference và tải dữ liệu cần thiết từ service/database.

Ví dụ kiểm tra payload trước khi thêm:

~~~java
public void storePreference(HttpSession session, String key, String value) {
    if (value == null || value.length() > 2048) {
        throw new IllegalArgumentException("Preference is too large");
    }

    if (!Set.of("locale", "theme", "timezone").contains(key)) {
        throw new IllegalArgumentException("Unsupported session attribute");
    }

    session.setAttribute("preference." + key, value);
}
~~~

Ví dụ chỉ minh họa allow-list và giới hạn ký tự; giới hạn byte thực tế cần tính theo encoding và serializer. Đặt giới hạn ở các điểm ghi dữ liệu, không đợi repository hết RAM mới phát hiện.

## 16. Giới hạn tài nguyên Redis

Redis session store cần dung lượng cho session data, index, expiration metadata, replication buffer và overhead của cấu trúc dữ liệu. Không chỉ cộng kích thước payload; chi phí thực tế còn phụ thuộc key count, object encoding, allocator fragmentation và replication.

Ước lượng sơ bộ:

    Bộ nhớ cần ≈ số session đồng thời
                 × kích thước trung bình một session
                 × hệ số overhead
                 + headroom vận hành

Ví dụ, 100.000 session với payload trung bình 4 KB không có nghĩa Redis chỉ cần 400 MB. Còn có key, hash fields, index, expiration structures, replication, fragmentation và các workload khác. Hãy đo memory usage trên dữ liệu đại diện thay vì dùng phép nhân payload làm capacity cuối cùng.

Các biện pháp:

- Dành Redis instance/cluster riêng cho session nếu workload cần ổn định.
- Đặt maxmemory theo dung lượng thực tế và giữ headroom.
- Theo dõi used_memory, used_memory_rss, fragmentation, key count và eviction.
- Theo dõi latency, rejected writes và replication lag.
- Đặt alert trước khi chạm ngưỡng.
- Xác định chính sách khi Redis không thể ghi do hết bộ nhớ.
- Không để cache không liên quan tiêu thụ hết ngân sách session.

Với session data, eviction có thể khiến người dùng bị logout bất ngờ. Chính sách noeviction thường đáng cân nhắc cho Redis chuyên lưu session: khi hết bộ nhớ, Redis từ chối các thao tác ghi thay vì âm thầm đẩy session đang có ra ngoài. Đổi lại, ứng dụng phải xử lý lỗi ghi và cảnh báo dung lượng trước khi chạm trần.

Các policy như allkeys-lru, allkeys-lfu hoặc volatile-* có thể loại bỏ key session theo tiêu chí eviction khi memory pressure xảy ra. Chỉ chọn nếu sản phẩm chấp nhận mất phiên và đã đánh giá semantics của các key có TTL. Không xem eviction là cách thay thế cho TTL hoặc capacity planning.

## 17. Giới hạn tài nguyên JDBC

JDBC session store tiêu thụ dung lượng bảng, index, connection pool, I/O và năng lực cleanup. Nếu session payload lớn hoặc số phiên tăng nhanh, bảng attributes có thể phát triển đáng kể.

Các biện pháp:

- Dùng database/schema hoặc table riêng khi cần cách ly workload.
- Đặt index theo schema Spring Session cung cấp.
- Theo dõi số hàng session và attributes, dung lượng bảng/index.
- Theo dõi query latency, lock wait, deadlock và connection pool saturation.
- Điều chỉnh cleanup schedule theo dung lượng và tải.
- Giới hạn số session mới được tạo bởi anonymous traffic.
- Đặt timeout và retry hợp lý cho kết nối database.
- Dùng connection pool có giới hạn và headroom cho workload nghiệp vụ.
- Không để cleanup job chạy quá dày gây tải đột biến.

Spring Session JDBC có cơ chế dọn các session hết hạn theo lịch. Cần xác minh cron, câu SQL và index theo phiên bản đang dùng. Cleanup chậm có thể làm bảng lớn hơn dự kiến; cleanup quá dày có thể tranh chấp với request đang cập nhật session.

Không chạy cleanup toàn schema bằng một câu SQL tự viết nếu chưa hiểu quan hệ giữa bảng session và attributes. Dùng script và cơ chế cleanup được tài liệu hỗ trợ, hoặc kiểm thử kỹ custom cleanup.

## 18. Giới hạn connection pool và timeout

Redis và JDBC có giới hạn kết nối riêng. Nếu mọi request đều truy cập session store, số request đồng thời có thể làm pool cạn trước khi CPU ứng dụng bận.

Cần theo dõi:

- Số connection đang dùng và đang chờ.
- Thời gian chờ lấy connection.
- Timeout và tỷ lệ lỗi kết nối.
- Thời gian load/save session.
- Tải theo từng node.
- Retry storm khi store chậm.
- Số session operations trên mỗi request.

Không đặt pool size quá lớn mà không xét giới hạn connection của Redis/database và số instance. Nếu có 20 instance, mỗi instance mở pool 50 connection thì hệ thống có thể tạo tới 1.000 connection ở trạng thái tối đa. Capacity planning phải tính tổng trên toàn cụm.

Timeout nên đủ ngắn để request không treo quá lâu khi session store gặp sự cố, nhưng cũng không thấp đến mức tạo lỗi giả dưới tải bình thường. Retry cần có backoff và giới hạn; retry dồn dập có thể làm store quá tải nặng hơn.

## 19. Hạn chế tạo session không cần thiết

Một endpoint công khai hoặc health check không nên vô tình tạo session ở mọi request. Nếu mỗi request bot hoặc crawler tạo một session mới, kho dữ liệu sẽ tăng nhanh dù không có người dùng thực sự đăng nhập.

Các cách giảm:

- Chỉ gọi request.getSession() khi thực sự cần.
- Dùng request.getSession(false) khi chỉ muốn kiểm tra session đã tồn tại.
- Không tạo session trong health check, static resource hoặc endpoint stateless.
- Cấu hình Spring Security SessionCreationPolicy phù hợp với từng filter chain.
- Kiểm tra framework hoặc view layer có tự tạo session hay không.
- Rate-limit endpoint có thể tạo anonymous session.
- Đặt TTL ngắn cho session ẩn danh nếu trải nghiệm cho phép.
- Theo dõi session creation rate theo endpoint và client class.

SessionCreationPolicy.STATELESS điều khiển cách Spring Security dùng HttpSession cho SecurityContext; nó không ngăn code nghiệp vụ tùy ý gọi getSession() để tạo session riêng. Cần kiểm tra cả code ứng dụng và filter.

## 20. Cách ly theo tenant và giới hạn tenant

Không nên tạo namespace Redis động cho mỗi tenant chỉ bằng cách nối tenant ID lấy từ request. Nếu client có thể gửi tùy ý tenant ID, có thể tạo keyspace không giới hạn hoặc truy cập sai vùng dữ liệu.

Trong mô hình thông thường, namespace được xác định theo application/environment; tenant ID được lưu hoặc xác định từ principal đã xác thực và được kiểm tra ở tầng nghiệp vụ.

Nếu cần quota theo tenant, có thể quản lý ở một service riêng:

- Số session active theo tenant.
- Số session mới trong một khoảng thời gian.
- Kích thước metadata/session được phép.
- Số device registration.
- Chính sách timeout riêng nếu sản phẩm hỗ trợ.
- Quy tắc thu hồi khi tenant bị khóa.

Đếm session theo tenant cần index hoặc registry phù hợp. Không quét toàn bộ Redis keyspace trong mỗi request để tính quota. Dùng counter có kiểm soát, event-driven accounting hoặc truy vấn index được hỗ trợ, đồng thời có tác vụ đối soát vì counter có thể lệch khi event bị mất hoặc retry.

## 21. Quan sát và cảnh báo

Cách ly và quota chỉ có hiệu quả khi vận hành quan sát được. Các chỉ số hữu ích:

| Nhóm | Chỉ số |
|---|---|
| Session lifecycle | Tạo, lưu, tải, xóa, hết hạn, lookup miss |
| Dung lượng | Session count, payload size phân vị, Redis memory, JDBC table size |
| Hiệu năng | Repository latency, serialize/deserialize time, request overhead |
| Redis | Eviction, rejected writes, connection count, replication lag |
| JDBC | Query latency, lock wait, cleanup duration, pool active/pending |
| Bảo mật | Login, logout, revoke, session fixation rotation, truy cập bất thường |
| Cách ly | Namespace/table theo môi trường, lỗi truy cập chéo, credential failure |

Không đưa session ID, cookie hoặc thuộc tính nhạy cảm vào metric label. Label có cardinality cao như session ID sẽ làm hỏng hệ thống metrics và có thể lộ credential.

Có thể ghi một hash không thể đảo ngược hoặc correlation ID đã được thiết kế riêng để điều tra, nhưng cần giới hạn quyền truy cập và retention của log.

## 22. Xử lý khi kho session chạm giới hạn hoặc không sẵn sàng

Khi Redis hết memory với noeviction, thao tác ghi có thể thất bại. Khi JDBC pool cạn, request có thể timeout trước khi lưu session. Ứng dụng phải có hành vi lỗi rõ ràng.

Các nguyên tắc:

- Không trả response đăng nhập thành công nếu SecurityContext/session bắt buộc chưa được lưu thành công.
- Không nuốt lỗi repository rồi tiếp tục như thể session đã persist.
- Phân biệt lỗi tạm thời với lỗi schema/serialization.
- Giới hạn retry và dùng backoff.
- Có circuit breaker hoặc bulkhead nếu phù hợp với kiến trúc.
- Tránh fallback sang local in-memory session trong một node nếu điều đó tạo trạng thái đăng nhập không nhất quán.
- Có cảnh báo dung lượng trước khi store đạt ngưỡng.
- Có runbook mở rộng Redis/database hoặc giảm session creation rate.
- Xác định rõ endpoint nào có thể tiếp tục stateless khi session store lỗi.

Fallback sang session local có thể khiến request tiếp theo đến node khác mất trạng thái hoặc tạo ra một phiên bảo mật khác. Không tự động bật fallback này nếu chưa có thiết kế và kiểm thử.

## 23. Kiểm thử cách ly và giới hạn tài nguyên

Nên có kiểm thử xác nhận các ranh giới, không chỉ kiểm tra một request tạo session thành công.

Các trường hợp nên kiểm thử:

1. Hai môi trường dùng namespace Redis khác nhau và không đọc được session của nhau.
2. Hai ứng dụng dùng table/schema JDBC khác nhau.
3. Cookie name, Domain và Path không khiến browser gửi nhầm session ID.
4. Credential của staging không thể truy cập key/table production.
5. Redis ACL chỉ cho phép key pattern của ứng dụng.
6. Rolling deployment giữ được session tương thích khi namespace ổn định.
7. Namespace đổi có hành vi logout/migration đúng dự kiến.
8. Session hết idle timeout và không được khôi phục.
9. Absolute lifetime được áp dụng dù client gửi request liên tục.
10. Giới hạn số session đồng thời được thực thi trên nhiều instance.
11. Payload quá lớn hoặc thuộc tính không được phép bị từ chối ở application boundary.
12. Anonymous endpoint không tạo session không cần thiết.
13. Redis memory pressure với policy đã chọn tạo hành vi lỗi đúng dự kiến.
14. JDBC cleanup xóa đúng bảng và không ảnh hưởng môi trường khác.
15. Connection pool saturation tạo timeout có kiểm soát.
16. Tenant authorization không dựa vào namespace hoặc tenant ID do client tự khai báo.
17. Metrics và logs không chứa session ID hoặc cookie.
18. Test chạy song song có namespace riêng, không xóa dữ liệu của job khác.

Dùng Redis/JDBC thật hoặc môi trường integration tương thích để kiểm thử TTL, ACL, cleanup và lỗi lưu trữ. Mock repository không chứng minh được eviction policy, database index, connection pool hoặc keyspace isolation.

## 24. Checklist triển khai production

- [ ] Production và non-production có endpoint/credential riêng hoặc lớp cách ly tương đương.
- [ ] Mỗi ứng dụng có namespace Redis riêng.
- [ ] Redis ACL giới hạn command và key pattern theo key thực tế.
- [ ] JDBC database/schema/table name được phân vùng rõ.
- [ ] Runtime database user không có quyền DDL hoặc truy cập schema không cần thiết.
- [ ] Cookie name, Domain, Path, Secure, HttpOnly và SameSite phù hợp.
- [ ] Namespace ổn định qua rolling deployment tương thích.
- [ ] Serializer tương thích giữa các instance trong cùng rollout.
- [ ] Idle timeout và absolute lifetime được xác định rõ.
- [ ] Có giới hạn số session theo principal khi sản phẩm yêu cầu.
- [ ] Có quota kích thước/thuộc tính ở application boundary.
- [ ] Không lưu file, entity graph hoặc dữ liệu lớn trong session.
- [ ] Redis maxmemory, eviction policy và headroom được cấu hình có chủ đích.
- [ ] JDBC cleanup, index, table size và connection pool được giám sát.
- [ ] Session creation rate và anonymous session được kiểm soát.
- [ ] Có metric/alert cho memory, eviction, repository errors và latency.
- [ ] Có runbook khi session store hết dung lượng hoặc mất kết nối.
- [ ] Test xác nhận không truy cập chéo môi trường, ứng dụng hoặc tenant.
- [ ] Log, trace và metric không chứa session ID hay cookie.

## Kết luận

Cách ly môi trường và namespace là nền tảng để tránh session của ứng dụng hoặc môi trường này ảnh hưởng đến môi trường khác. Redis nên có namespace riêng theo ứng dụng/môi trường và ACL hoặc instance riêng khi cần ranh giới bảo mật mạnh; JDBC nên dùng database/schema/table riêng cùng credential tối thiểu; cookie phải có scope phù hợp để browser không gửi nhầm định danh. Namespace không thay thế authorization. Đồng thời, cần giới hạn idle/absolute lifetime, số session, kích thước thuộc tính và tốc độ tạo session; quản lý Redis memory/eviction, JDBC cleanup/connection pool; và theo dõi repository latency, dung lượng, lỗi ghi và session lifecycle. Chỉ khi các lớp này được thiết kế và kiểm thử cùng nhau, Spring Session mới có thể chia sẻ trạng thái an toàn và ổn định khi ứng dụng chạy nhiều instance.

## Tài liệu tham khảo

- Spring Session Reference: https://docs.spring.io/spring-session/reference/
- Spring Session Redis Configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session JDBC Configuration: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Session HttpSession Integration: https://docs.spring.io/spring-session/reference/http-session.html
- Spring Boot Session Properties: https://docs.spring.io/spring-boot/appendix/application-properties/index.html
- Redis Security and ACL: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
- Redis Memory Optimization: https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/
