# Phần mở rộng Hazelcast, MongoDB và thay đổi đơn vị duy trì

Spring Session tách API quản lý phiên khỏi nơi lưu dữ liệu. Ứng dụng Servlet tiếp tục dùng `HttpSession`; ứng dụng WebFlux dùng `WebSession`. Phần triển khai phía dưới có thể dùng Redis, JDBC hoặc một repository mở rộng như Hazelcast và MongoDB. Nhờ ranh giới này, ứng dụng có thể thay đổi kho lưu phiên mà không phải viết lại toàn bộ controller và nghiệp vụ.

Tuy nhiên, thay repository không chỉ là thay dependency. Mỗi kho có mô hình dữ liệu, serialization, TTL, chỉ mục, tính nhất quán, khả năng chịu lỗi và cách cấu hình khác nhau. Nếu nhiều node cùng phục vụ request, mọi node phải dùng cấu hình tương thích và cùng nhìn thấy dữ liệu phiên. Khi chuyển kho, cần có kế hoạch di chuyển dữ liệu, xử lý session ID cũ, theo dõi request đang chạy và phương án rollback.

Trong bài này, “đơn vị duy trì” được hiểu là tổ hợp repository, backend, schema/namespace, serializer và chính sách hết hạn dùng để lưu session. Đây là ranh giới persistence của Spring Session, không phải JPA persistence unit.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt API Spring Session với implementation theo từng kho dữ liệu.
- Chọn Hazelcast hoặc MongoDB theo đặc tính tải và yêu cầu vận hành.
- Cấu hình extension, cluster, serialization, collection và TTL theo đúng phiên bản.
- Nhận biết khác biệt giữa module Spring Session chính thức và community extension.
- Tránh auto-configuration chọn nhầm repository khi có nhiều implementation trên classpath.
- Lập kế hoạch chuyển Redis/JDBC sang Hazelcast hoặc MongoDB mà không làm mất phiên ngoài dự kiến.
- Kiểm thử cookie, session ID, thuộc tính, timeout, logout và nhiều instance sau migration.

## 1. Kiến trúc persistence của Spring Session

Ứng dụng thường thao tác với session qua Servlet API hoặc WebFlux API. Filter hoặc WebSession manager chuyển các thao tác đó sang repository được cấu hình:

~~~mermaid
flowchart TD
    A[Controller / Spring Security] --> B{Web stack}
    B -->|Servlet| C[SessionRepositoryFilter]
    B -->|WebFlux| D[WebSessionManager]
    C --> E[SessionRepository]
    D --> F[ReactiveSessionRepository]
    E --> G{Store implementation}
    F --> G
    G --> H[Redis]
    G --> I[JDBC]
    G --> J[Hazelcast]
    G --> K[MongoDB]
~~~

Các lớp có trách nhiệm khác nhau:

| Lớp | Trách nhiệm |
|---|---|
| `HttpSession` / `WebSession` | API mà ứng dụng sử dụng để đọc và cập nhật thuộc tính phiên |
| `SessionRepository` / `ReactiveSessionRepository` | Hợp đồng tạo, tìm, lưu và xóa session |
| Repository implementation | Ánh xạ session sang cấu trúc của Redis, JDBC, Hazelcast hoặc MongoDB |
| Backend | Quản lý phân vùng, replication, durability, index và expiry |
| Cookie resolver/serializer | Trao đổi session ID giữa client và server |

Spring Session giữ nguyên mô hình session ở tầng ứng dụng, nhưng không bảo đảm dữ liệu được tự động chuyển từ repository cũ sang repository mới. Cookie thường chỉ mang session ID; nếu backend mới chưa có bản ghi mang ID đó, request sẽ không khôi phục được session cũ.

## 2. Module chính thức, community extension và tương thích phiên bản

Không nên coi mọi integration đều được phát hành và quản lý trong cùng repository. Tài liệu Spring Session hiện liệt kê Hazelcast và MongoDB trong nhóm community extensions. Spring Boot cũng thay đổi phạm vi auto-configuration giữa các dòng phiên bản.

Một ví dụ về khác biệt theo phiên bản:

| Nền tảng | Auto-configuration được tài liệu mô tả |
|---|---|
| Spring Boot 4.2 | Servlet: Redis và JDBC; WebFlux: Redis |
| Spring Boot 3.4 | Servlet: Redis, JDBC, Hazelcast và MongoDB; WebFlux: Redis và MongoDB |
| Các dòng Boot cũ hơn | Phạm vi store và thứ tự lựa chọn phụ thuộc đúng phiên bản |

Vì vậy, không sao chép cấu hình auto-configuration của Boot 3.x sang Boot 4.x. Trước khi nâng cấp hoặc thêm extension, kiểm tra:

- Phiên bản Spring Boot, Spring Framework và Spring Session.
- Java baseline của release đang dùng.
- Phiên bản Hazelcast hoặc MongoDB Java driver.
- Artifact coordinates và package namespace hiện hành của extension.
- Extension cung cấp Servlet repository, reactive repository hay cả hai.
- Extension có starter/auto-configuration riêng hay yêu cầu khai báo cấu hình thủ công.

Với Spring Boot mới, Redis/JDBC có starter chính thức; Hazelcast và MongoDB cần kiểm tra extension tương ứng. Không đưa hai implementation vào classpath rồi phó mặc việc lựa chọn repository cho auto-configuration. Nếu nhiều implementation hiện diện, cấu hình tường minh hoặc chỉ giữ dependency cần dùng.

## 3. Khi nào nên cân nhắc Hazelcast?

Hazelcast là nền tảng dữ liệu phân tán trong bộ nhớ. Integration Spring Session Hazelcast dùng `IMap` để lưu session trong cluster. Các ứng dụng thành viên hoặc client kết nối vào cùng cluster có thể đọc phiên mà node khác đã tạo.

Hazelcast phù hợp khi:

- Cần truy cập session độ trễ thấp trong một cluster.
- Hạ tầng đã vận hành Hazelcast cho dữ liệu phân tán hoặc cache.
- Muốn phân vùng dữ liệu và cấu hình số bản sao trong cluster.
- Đội vận hành hiểu rõ membership, split-brain, backup partition và serialization của Hazelcast.

Hazelcast không tự động đồng nghĩa với lưu trữ bền vững. Một cấu hình IMap trong bộ nhớ có thể mất dữ liệu khi toàn cluster dừng hoặc khi không có persistence được cấu hình và hỗ trợ bởi phiên bản/edition đang dùng. Phải xác định rõ yêu cầu chịu lỗi: mất một member, mất nhiều member, mất toàn cluster hay restart toàn bộ hạ tầng.

### 3.1. Thêm Hazelcast Spring Session

Với extension Hazelcast hiện hành, dependency có dạng:

~~~kotlin
dependencies {
    implementation("com.hazelcast.spring:hazelcast-spring-session:<compatible-version>")
    implementation("com.hazelcast:hazelcast:<compatible-version>")
}
~~~

Thay placeholder bằng phiên bản tương thích trong release matrix của Hazelcast Spring Session. Không tự chọn version mới nhất của từng artifact nếu chúng không được kiểm thử cùng nhau.

Cấu hình Servlet cơ bản dùng annotation:

~~~java
@Configuration
@EnableHazelcastHttpSession
class HazelcastSessionConfiguration {
}
~~~

Extension cần một Hazelcast instance hoặc client được cấu hình để kết nối tới cluster. Ví dụ cấu hình embedded instance:

~~~java
@Bean
HazelcastInstance hazelcastInstance() {
    Config config = new Config();

    config.getMapConfig(
            HazelcastIndexedSessionRepository.DEFAULT_SESSION_MAP_NAME)
        .addIndexConfig(new IndexConfig(
                IndexType.HASH,
                HazelcastIndexedSessionRepository.PRINCIPAL_NAME_ATTRIBUTE));

    HazelcastSessionConfiguration.applySerializationConfig(config);

    return Hazelcast.newHazelcastInstance(config);
}
~~~

Ví dụ minh họa API của extension Hazelcast 4.x. Import class và cấu hình cụ thể phải khớp đúng version đang dùng. Chỉ thêm index principal khi ứng dụng cần truy vấn session theo người dùng; index làm tăng chi phí ghi và dung lượng metadata.

Với kiến trúc client/server, application node thường dùng Hazelcast client để kết nối cluster thay vì tự tạo thêm member. Điều này giúp tách vòng đời ứng dụng khỏi vòng đời data cluster. Nếu chạy embedded members, phải cấu hình discovery, network, cluster name, security và partition backup đồng nhất.

### 3.2. Serialization và classpath của Hazelcast

Session có thể chứa principal, SecurityContext, thuộc tính nghiệp vụ và object do ứng dụng tự định nghĩa. Các object phải được serialize và deserialize tương thích trên các member/client.

Lưu ý:

- Ưu tiên lưu string, số, boolean, UUID và DTO nhỏ có schema ổn định.
- Tránh lưu entity JPA lớn, lazy proxy, connection hoặc object không thể serialize.
- Cấu hình serialization theo extension; ví dụ Hazelcast 4.x cung cấp `HazelcastSessionConfiguration.applySerializationConfig(config)`.
- Trong client/server deployment, kiểm tra yêu cầu classpath/code deployment của extension trên các member.
- Rolling deployment cần bảo đảm phiên được ghi bởi version cũ vẫn đọc được bởi version mới và ngược lại trong thời gian hai version cùng chạy.

Không chỉ kiểm tra ứng dụng ghi được session. Hãy kiểm tra một node khác có thể đọc cùng session và deserialize tất cả thuộc tính cần thiết.

### 3.3. TTL, backup và phân vùng

Session phải hết hạn theo inactivity timeout. Với Hazelcast, xác định rõ cách extension ánh xạ timeout Spring Session sang TTL/expiration của map. Không giả định cấu hình TTL mặc định của IMap tự động giống chính sách session.

Kiểm tra:

- TTL của entry và max inactive interval trong session.
- Số backup partition và khả năng phục hồi khi member rời cluster.
- Eviction policy có thể xóa session còn hiệu lực khi memory pressure tăng.
- Split-brain và merge policy có thể tạo xung đột khi hai phía cùng cập nhật một session.
- Giới hạn memory, heap/off-heap, serialization cost và network latency.

Với session authentication, mất một phiên có thể khiến người dùng phải đăng nhập lại; phục hồi sai phiên hoặc xung đột dữ liệu có thể gây rủi ro bảo mật. Chọn consistency/backup policy theo hậu quả của mất dữ liệu, không chỉ theo throughput.

## 4. Khi nào nên cân nhắc MongoDB?

MongoDB là document database. Extension Spring Session MongoDB lưu session dưới dạng document bằng Spring Data MongoDB. Đây là lựa chọn phù hợp khi tổ chức đã vận hành MongoDB, muốn session dùng chung database service và cần lưu dữ liệu phiên theo cấu trúc document.

MongoDB có thể phù hợp khi:

- Cần persistence trên database có replica set và backup.
- Hạ tầng đã có MongoDB vận hành, giám sát và quy trình backup.
- Muốn dùng TTL index để dọn document hết hạn.
- Muốn quản lý session cùng nền tảng dữ liệu document nhưng vẫn tách database/collection và quyền truy cập.

Session là dữ liệu truy cập thường xuyên và có vòng đời ngắn. Không nên chọn MongoDB chỉ vì ứng dụng đã có MongoDB nếu workload session làm ảnh hưởng workload nghiệp vụ hoặc gây tranh chấp tài nguyên. Có thể dùng database/collection riêng, giới hạn quyền và capacity riêng.

### 4.1. Dependency và API MongoDB hiện hành

Extension MongoDB hiện hành có tọa độ Maven dạng:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-spring-session</artifactId>
    <version>${mongodb.spring.session.version}</version>
</dependency>
~~~

Quản lý version bằng property hoặc dependency management đã được kiểm chứng với Spring Boot/Spring Session đang dùng. Extension mới đã đổi package namespace từ `org.springframework.session.data.mongo` sang `org.mongodb.spring.session`. Jackson 2 converter được đánh dấu deprecated trong extension mới và có converter dành cho Jackson 3.

Các dự án cũ có thể vẫn dùng artifact `org.springframework.session:spring-session-data-mongodb` và package cũ. Không trộn hai thế hệ artifact hoặc import class cũ với dependency mới. Khi nâng cấp, cập nhật package, converter và cấu hình theo migration guide của extension MongoDB.

### 4.2. Cấu hình MongoDB

Một cấu hình Servlet minh họa dùng annotation của extension:

~~~java
@Configuration
@EnableMongoHttpSession
class MongoSessionConfiguration {
}
~~~

Tên annotation và package import cần được xác minh trong release đang dùng. Cấu hình phải cung cấp MongoDB operations/template và database phù hợp; Spring Boot có thể tự cấu hình client/template nếu có Spring Data MongoDB starter và URI hợp lệ.

Ví dụ cấu hình kết nối:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Không ghi username/password trực tiếp vào file cấu hình được commit. Dùng secret manager hoặc environment variable. Dùng database/collection session riêng khi cần phân quyền, retention và capacity độc lập.

### 4.3. Document, index và hết hạn

MongoDB extension lưu session trong document. Các trường và cấu trúc chính xác phụ thuộc version/converter, nhưng thường cần biểu diễn:

- Session ID.
- Thời điểm tạo và truy cập gần nhất.
- Inactivity interval hoặc thời điểm hết hạn.
- Principal/index data nếu repository hỗ trợ.
- Các session attributes.

TTL index có thể tự dọn document sau khi trường expiry đạt thời điểm hết hạn. TTL monitor chạy nền nên việc xóa không nhất thiết xảy ra đúng tại mili giây hết hạn. Repository vẫn phải áp dụng semantics hết hạn khi đọc; không dùng sự xuất hiện tạm thời của document đã hết hạn làm bằng chứng session còn hợp lệ.

Kiểm tra:

- TTL index được tạo trên đúng field và đúng collection.
- Expiry được cập nhật khi request hợp lệ làm mới session.
- TTL cleanup không xóa nhầm session đang hoạt động do sai timezone hoặc sai kiểu dữ liệu.
- Index principal/lookup chỉ được tạo khi use case cần.
- Kích thước document session không tiến gần giới hạn document của MongoDB.

Không lưu object lớn hoặc binary không cần thiết trong session. Session nên chứa thông tin định danh và trạng thái giao diện tối thiểu; dữ liệu nghiệp vụ dài hạn nên ở collection nghiệp vụ riêng.

### 4.4. Read/write consistency và replica set

Với nhiều application node, tất cả phải kết nối cùng MongoDB deployment và database/collection. Chọn write concern, read preference và topology sao cho request tiếp theo không đọc một bản session cũ sau khi request trước đã ghi thành công.

Đối với dữ liệu xác thực, tránh cấu hình read preference có thể trả dữ liệu stale nếu yêu cầu của ứng dụng cần read-after-write. Kiểm tra hành vi khi primary failover, retryable write, timeout và network partition.

TTL index chỉ đảm nhiệm dọn dữ liệu. Nó không thay thế backup, replica set, write concern hoặc kiểm thử failover.

## 5. So sánh Hazelcast và MongoDB

| Tiêu chí | Hazelcast | MongoDB |
|---|---|---|
| Mô hình dữ liệu | IMap phân tán trong cluster | Document trong collection |
| Đặc tính truy cập | Thường độ trễ thấp, dữ liệu trong bộ nhớ | Truy cập database, phụ thuộc index và topology |
| Durability | Cần cấu hình backup/persistence; in-memory mặc định không tương đương database bền vững | Có persistence, replication và backup theo cấu hình MongoDB |
| Expiry | TTL/expiration của map và semantics repository | Expiry field và TTL index |
| Scale | Partition/backup giữa các Hazelcast members | Sharding/replica set tùy workload và deployment |
| Vận hành | Cluster membership, split-brain, memory và serialization | Replica set, index, write concern, connection pool và storage |
| Tích hợp | Hazelcast Spring Session extension | MongoDB Spring Session extension |
| Rủi ro migration | Map name, serialization và package/version | Collection/schema, converter, index và BSON representation |

Không có backend nào tốt nhất cho mọi ứng dụng. Chọn theo yêu cầu durability, latency, query/index, chi phí vận hành, kỹ năng đội ngũ và mức chấp nhận người dùng đăng nhập lại khi có sự cố.

## 6. Chọn đúng repository khi có nhiều dependency

Một ứng dụng có thể vô tình đưa nhiều session store lên classpath vì starter được kéo gián tiếp. Hậu quả là Boot chọn repository khác với kỳ vọng hoặc có nhiều bean cạnh tranh.

Trước khi chạy production:

1. Kiểm tra dependency tree để biết implementation nào hiện diện.
2. Đọc tài liệu auto-configuration của đúng Spring Boot version.
3. Nếu Boot hỗ trợ store type cho backend cần dùng, cấu hình tường minh.
4. Nếu extension cần manual configuration, dùng đúng annotation/configuration của extension và tránh tạo repository thứ hai.
5. Khởi động ứng dụng và xác minh đúng một repository được dùng cho filter/session manager.
6. Kiểm tra request round-trip thực tế và backend nhận dữ liệu.

Không chỉ kiểm tra context khởi động thành công. Một ứng dụng có thể khởi động với repository hợp lệ nhưng repository đó không phải backend mà đội vận hành đang theo dõi.

## 7. Đổi đơn vị duy trì có ảnh hưởng gì?

Ở tầng ứng dụng, code có thể tiếp tục gọi:

~~~java
HttpSession session = request.getSession();
session.setAttribute("cartReference", cartId);
~~~

Nhưng khi đổi backend, các phần sau có thể thay đổi:

- Artifact và repository implementation.
- Annotation hoặc Boot auto-configuration.
- Redis namespace, JDBC schema, Hazelcast map name hoặc Mongo collection.
- Serializer và định dạng thuộc tính.
- TTL, cleanup và index.
- Event phát sinh khi tạo, hết hạn hoặc xóa session.
- Cách tìm session theo principal.
- Tính nhất quán và độ bền khi node/backend lỗi.

Cookie không tự chuyển dữ liệu. Nếu giữ nguyên cookie name và session ID nhưng backend mới trống, request sẽ mang một ID mà repository mới không tìm thấy. Nếu thay cookie name, browser có thể tạo session mới ngay cả khi dữ liệu đã được copy.

Vì thế, thay backend là một migration dữ liệu và hành vi, không đơn thuần là thay connection string.

## 8. Chiến lược migration

Có ba chiến lược thường gặp:

| Chiến lược | Cách làm | Khi phù hợp |
|---|---|---|
| Re-login có kiểm soát | Chuyển sang store mới, invalidate/expire cookie cũ và yêu cầu đăng nhập lại | Session có thể tái tạo, ưu tiên đơn giản và an toàn |
| Backfill rồi cutover | Copy session còn hiệu lực sang store mới trước khi chuyển traffic | Cần giữ phiên và có thể dừng/giảm ghi trong migration |
| Dual-read hoặc dual-write có kiểm soát | Đọc nguồn chính, fallback/migrate hoặc ghi đồng thời trong giai đoạn ngắn | Hệ thống lớn cần giảm downtime, có cơ chế nhất quán và rollback rõ |

Không triển khai dual-write tùy tiện trong controller. Hai repository không có transaction phân tán chung; một ghi có thể thành công trong store A nhưng thất bại trong store B. Cần quyết định nguồn nào là authoritative và cách sửa lệch dữ liệu.

### 8.1. Re-login có kiểm soát

Đây thường là phương án ít rủi ro nhất khi session chỉ chứa trạng thái tạm:

1. Thông báo thời điểm chuyển đổi.
2. Chọn thời điểm cutover và ngừng nhận request mới trong khoảng cần thiết.
3. Chuyển ứng dụng sang repository mới.
4. Thay đổi hoặc expire cookie theo kế hoạch để browser không gửi ID cũ.
5. Xác minh login tạo session mới ở backend mới.
6. Theo dõi lỗi xác thực và hỗ trợ người dùng đăng nhập lại.

Không xóa store cũ ngay lập tức. Giữ snapshot/backup theo retention để điều tra hoặc rollback, nhưng không để ứng dụng mới vô tình đọc dữ liệu cũ.

### 8.2. Backfill session còn hiệu lực

Nếu cần giữ session:

1. Tạo snapshot nguồn tại checkpoint đã xác định.
2. Tạm giảm hoặc dừng các request cập nhật session, hoặc bật cơ chế ghi nhận thay đổi phát sinh trong lúc copy.
3. Đọc session bằng repository API hoặc adapter có hiểu schema nguồn.
4. Lọc session hết hạn theo thời gian hiện tại.
5. Chuyển ID, creation time, last accessed time, max inactive interval và attributes.
6. Chuyển principal index và metadata cần thiết.
7. Chuyển đổi serialization sang định dạng mà repository đích đọc được.
8. Ghi vào repository đích và kiểm tra số lượng/độ toàn vẹn.
9. Bắt kịp các thay đổi phát sinh sau snapshot.
10. Chuyển traffic và kiểm thử cookie round-trip.

Không copy raw Redis bytes sang MongoDB hoặc raw MongoDB BSON sang Hazelcast rồi kỳ vọng repository mới tự hiểu. Dữ liệu có thể dùng serializer, wrapper, field name và cấu trúc index riêng.

### 8.3. Dual-read/dual-write

Trong migration không downtime, có thể dùng adapter trung gian:

- Giai đoạn đầu: store cũ là nguồn chính; ghi thêm sang store mới.
- Backfill: copy các session đang còn hiệu lực.
- Catch-up: xử lý các lần cập nhật/xóa kể từ snapshot.
- Giai đoạn đọc thử: đọc store mới ở chế độ shadow và so sánh kết quả, không dùng kết quả shadow để xác thực người dùng.
- Cutover: chuyển nguồn đọc chính sang store mới; tiếp tục ghi theo policy đã chọn.
- Stabilize: theo dõi miss rate, lỗi serialization, TTL và độ lệch dữ liệu.
- Retire: chỉ dừng store cũ sau thời gian rollback đã định.

Nếu có logout/invalidate trong migration, sự kiện xóa phải được truyền sang cả hai store. Nếu chỉ dual-write khi save mà bỏ qua delete/expire, session đã thu hồi có thể xuất hiện lại khi fallback hoặc rollback.

## 9. Giữ cookie và session ID tương thích

Nếu muốn browser tiếp tục gửi cookie hiện có:

- Giữ cookie name, Domain, Path, Secure, HttpOnly và SameSite tương thích.
- Giữ định dạng session ID mà resolver đích có thể đọc.
- Chuyển session ID cùng thuộc tính và expiry.
- Bảo đảm mọi node đã cutover đọc cùng store mới.
- Không chạy đồng thời node cũ đọc store cũ và node mới đọc store mới nếu cùng nhận một cookie mà không có migration bridge.

Nếu không thể chuyển ID hoặc serializer an toàn, expire cookie cũ và yêu cầu login lại là lựa chọn rõ ràng hơn. Không đổi cookie name để che giấu lỗi migration; cần hiểu client nào còn gửi cookie cũ và thời điểm loại bỏ nó.

## 10. Serialization và thay đổi schema

Session attributes có thể chứa object Java, principal, SecurityContext hoặc DTO. Đổi backend thường kéo theo đổi serializer:

- Java serialization có thể phụ thuộc class name, package, serialVersionUID.
- JSON phụ thuộc type metadata, naming strategy và module Jackson.
- BSON có mapping riêng cho kiểu dữ liệu MongoDB.
- Hazelcast có serializer và yêu cầu class deployment trong cluster.

Khuyến nghị:

- Chỉ lưu các thuộc tính nhỏ, ổn định và cần thiết giữa request.
- Ưu tiên DTO có version hoặc primitive/string/UUID.
- Không lưu entity persistence có lazy association.
- Có converter/migration version rõ ràng.
- Kiểm thử đọc session do version cũ ghi bằng version mới.
- Nếu không thể chuyển đổi một thuộc tính an toàn, loại bỏ thuộc tính đó hoặc yêu cầu re-authentication theo policy.

Với MongoDB extension hiện hành, cần kiểm tra converter Jackson 2/Jackson 3 theo phiên bản. Với Hazelcast extension hiện hành, dùng serialization configuration của extension và bảo đảm các member có thể giải mã object tương ứng.

## 11. TTL, index và session event khi chuyển store

Mỗi backend có cơ chế expiry riêng:

| Backend | Cần xác minh |
|---|---|
| Hazelcast | Entry TTL/max-idle, eviction, backup map và cleanup |
| MongoDB | Expiry field, TTL index, kiểu BSON date và TTL monitor |
| Redis | Key TTL, metadata/index liên quan và expiration event |
| JDBC | Expiry column, cleanup job và index của bảng session |

Không chuyển một con số timeout mà bỏ qua semantics. Ví dụ, TTL index MongoDB dọn document theo chu kỳ nền; Hazelcast entry expiration có thể dựa trên TTL/max-idle; JDBC có thể dùng job cleanup. Repository phải từ chối session hết hạn ngay cả khi backend chưa xóa vật lý.

Session event có thể khác giữa implementation. Nếu ứng dụng dựa vào event để cập nhật active-session list, concurrency control hoặc audit, phải kiểm tra extension có phát event nào và khi nào. Không giả định mọi repository phát cùng một tập event hoặc phát event theo cùng thời điểm.

Trong migration, cần xử lý cả create, update, delete, expire và ID rotation. Chỉ copy record hiện tại mà không tái tạo index/event phụ có thể làm mất chức năng “logout all sessions”, truy vấn theo principal hoặc dashboard phiên hoạt động.

## 12. Kiểm thử trước và sau cutover

Kiểm thử ở cấp HTTP thay vì chỉ kiểm tra repository bean:

1. Request A tạo session và lưu thuộc tính test.
2. Lấy session cookie từ response.
3. Request B gửi cookie tới node khác và đọc lại thuộc tính.
4. Cập nhật thuộc tính, kết thúc response và xác minh request C đọc giá trị mới.
5. Kiểm tra last access time và inactivity timeout.
6. Logout/invalidate và xác minh ID cũ không khôi phục session.
7. Thử request với session hết hạn.
8. Khởi động lại một application node và xác minh session vẫn dùng được.
9. Với Hazelcast, loại một member theo kịch bản test và kiểm tra backup/failover.
10. Với MongoDB, thử primary failover, index TTL và lỗi kết nối.
11. Với migration, replay cookie được tạo trước cutover và xác minh hành vi theo kế hoạch.

Kiểm thử thêm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Session được tạo trên node A | Node B đọc được cùng thuộc tính |
| Session được cập nhật | Request kế tiếp thấy giá trị mới |
| Session đã logout | Cookie cũ không khôi phục phiên |
| Session quá hạn | Repository từ chối phiên dù record chưa bị cleanup vật lý |
| Attribute không deserialize được | Có lỗi quan sát được hoặc policy loại bỏ phiên; không xác thực bằng dữ liệu thiếu |
| Backend tạm mất kết nối | Hành vi lỗi phù hợp policy, không âm thầm tạo session giả |
| Hai implementation cùng classpath | Ứng dụng vẫn dùng repository đã chỉ định rõ |
| Rollback về store cũ | Các thay đổi mới hơn cutover không bị mất hoặc rollback có kế hoạch re-login |

## 13. Rollback và ranh giới an toàn

Rollback không đơn giản là đổi property về store cũ. Sau cutover, session có thể đã được tạo, cập nhật, logout hoặc rotate chỉ trong store mới.

Trước khi migration, quyết định:

- Có tiếp tục dual-write trong cửa sổ rollback không?
- Có cơ chế reverse sync từ store mới về store cũ không?
- Nếu reverse sync thất bại, có chấp nhận logout toàn bộ không?
- Cookie/session ID có còn tương thích với store cũ không?
- Có thể khôi phục index, TTL và event metadata không?

Nếu không có reverse sync đáng tin cậy, rollback nên đi kèm expire cookie và yêu cầu đăng nhập lại. Tránh đưa store cũ trở lại phục vụ các ID có thể đã bị thu hồi hoặc thay đổi sau cutover.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Boot khởi động nhưng dùng Redis thay vì Hazelcast | Auto-configuration chọn store khác do dependency/classpath hoặc version | Kiểm tra dependency tree và cấu hình repository tường minh |
| Hazelcast cluster có session nhưng node khác không đọc được | Khác cluster name, map config, serializer hoặc member classpath | Đồng nhất cấu hình và kiểm tra serialization liên node |
| Hazelcast mất session sau restart toàn cluster | Chỉ dùng IMap in-memory, chưa cấu hình durability phù hợp | Thiết kế persistence/backup hoặc chấp nhận re-login |
| Mongo document còn nhưng session đã hết hạn | TTL monitor chưa xóa document ngay | Repository phải kiểm tra expiry; xác minh TTL index |
| Mongo không dọn session | TTL index sai field/kiểu dữ liệu hoặc chưa được tạo | Kiểm tra index và BSON date |
| Mongo session không deserialize sau nâng cấp | Package/converter/Jackson version thay đổi | Theo migration guide và kiểm thử dữ liệu cũ |
| Sau đổi store mọi người bị logout | Store mới không có dữ liệu hoặc cookie ID không khớp | Backfill/cutover theo kế hoạch hoặc expire cookie có chủ đích |
| Logout ở store cũ nhưng phiên còn trong store mới | Delete event không được đồng bộ trong dual-write | Đồng bộ invalidate/delete và replay các sự kiện |
| Chỉ một node mất session | Node dùng backend, namespace hoặc serializer khác | So sánh cấu hình runtime giữa các instance |
| Principal session lookup không hoạt động | Thiếu index hoặc repository không hỗ trợ principal index | Tạo index/cấu hình hỗ trợ và kiểm thử truy vấn |

## 15. Checklist chọn extension và thay đổi persistence

- [ ] Xác định Servlet hay WebFlux và repository interface tương ứng.
- [ ] Kiểm tra extension Hazelcast/MongoDB có tương thích với Spring Boot, Spring Session và Java version.
- [ ] Phân biệt module chính thức với community extension và artifact cũ đã đổi namespace.
- [ ] Chỉ đưa implementation cần thiết vào classpath.
- [ ] Cấu hình đúng cluster/map/serialization của Hazelcast hoặc database/collection/converter/index của MongoDB.
- [ ] Xác minh TTL và cleanup theo semantics backend.
- [ ] Đặt cookie name, Domain, Path và session ID policy rõ ràng.
- [ ] Chọn re-login, backfill hay dual-read/write trước khi cutover.
- [ ] Đồng bộ cả save, delete, expire và ID rotation trong migration.
- [ ] Có phương án xử lý serialization/schema cũ.
- [ ] Kiểm thử request round-trip qua nhiều node và backend failover.
- [ ] Có rollback plan; nếu không thể đồng bộ ngược, chuẩn bị expire cookie và re-authentication.

## 16. Tài liệu tham khảo

- [Spring Session Reference và danh sách community extensions](https://docs.spring.io/spring-session/reference/index.html)
- [Spring Boot: Spring Session auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Hazelcast Spring Session extension và hướng dẫn migration 3.x sang 4.x](https://github.com/hazelcast/hazelcast-spring-session)
- [MongoDB Spring Session extension và migration package/converter](https://github.com/mongodb/mongo-spring-session)

Hazelcast và MongoDB mở rộng lựa chọn repository cho Spring Session, nhưng mỗi backend có yêu cầu riêng về cluster, durability, serialization, index và expiry. Khi thay đổi đơn vị duy trì, hãy xác định rõ repository đích, version compatibility, cookie/session ID, dữ liệu thuộc tính và sự kiện xóa. Nếu cần giữ phiên, di chuyển bằng quy trình backfill/catch-up có kiểm thử; nếu không thể chứng minh dữ liệu và semantics tương thích, expire cookie và yêu cầu đăng nhập lại là phương án an toàn hơn việc để session ID cũ trỏ tới một kho trống hoặc sai định dạng.
