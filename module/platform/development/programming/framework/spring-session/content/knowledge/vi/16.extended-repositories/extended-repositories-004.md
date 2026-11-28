# MongoDB và các phần mở rộng: xác minh đơn vị duy trì, phiên bản, khả năng

Spring Session cung cấp API chung để ứng dụng quản lý phiên mà không phụ thuộc trực tiếp vào nơi lưu trữ. Redis và JDBC có các module quen thuộc trong hệ sinh thái Spring Session; MongoDB và một số kho khác được cung cấp qua module hoặc phần mở rộng riêng. Khi chọn một phần mở rộng, điều quan trọng là xác minh ai đang duy trì nó, nó tương thích với phiên bản Spring nào và những khả năng nào thực sự được triển khai.

Không nên đánh giá một extension chỉ bằng việc nó có thể tạo được bean SessionRepository. Một kho lưu phiên chạy production còn phải đáp ứng thời hạn phiên, cập nhật đồng thời, thu hồi, sự kiện vòng đời, serialization, khả năng phục hồi, quan sát và nâng cấp. Các khả năng đó có thể khác nhau giữa các extension dù chúng cùng triển khai API Spring Session.

Bài học tập trung vào Spring Session MongoDB và cách đánh giá các phần mở rộng repository. Phạm vi của module SPRING_SESSION là quản lý phiên ứng dụng Spring độc lập với một máy chủ, dùng kho dữ liệu chia sẻ như Redis hoặc JDBC; MongoDB là một lựa chọn mở rộng cần được đánh giá theo phiên bản và đơn vị duy trì cụ thể.

## 1. Hiểu đúng khái niệm extension trong Spring Session

Spring Session tách API quản lý phiên khỏi implementation lưu trữ. Ứng dụng Servlet có thể tiếp tục dùng HttpSession; SessionRepositoryFilter kết nối API đó với repository được cấu hình. Với kho dữ liệu khác nhau, repository đảm nhận việc tạo, tìm, lưu, cập nhật và xóa phiên theo hợp đồng Spring Session.

Một extension thường cung cấp một hoặc nhiều thành phần sau:

- Implementation của SessionRepository hoặc FindByIndexNameSessionRepository.
- Cấu hình để thay HttpSession mặc định bằng phiên lưu trong kho dữ liệu.
- Converter hoặc serializer để chuyển thuộc tính phiên thành dạng dữ liệu lưu trữ.
- Cơ chế hết hạn, xóa dữ liệu và phát sự kiện vòng đời.
- Tích hợp với Spring Boot hoặc cấu hình Java thủ công.
- Tài liệu, ví dụ, kiểm thử tích hợp và hướng dẫn nâng cấp.

Có repository không đồng nghĩa mọi tính năng của Spring Session đều được hỗ trợ giống nhau. Ví dụ, một extension có thể lưu và khôi phục HttpSession nhưng không cung cấp truy vấn theo principal; extension khác có thể có TTL nhưng không phát sự kiện expiration đáng tin cậy. Hãy xác định từng khả năng qua tài liệu, API, mã nguồn và kiểm thử của đúng phiên bản.

## 2. Phân biệt module chính thức và phần mở rộng cộng đồng

Trong hệ sinh thái Spring, một số implementation được phát triển trong dự án Spring Session; một số khác được duy trì ở repository riêng bởi nhà cung cấp hoặc cộng đồng. Tài liệu Spring Session hiện liệt kê MongoDB, Hazelcast, Infinispan và Caffeine trong nhóm community extensions. Spring Session Data Geode cũng có repository và hướng dẫn riêng.

Điều này tạo ra khác biệt về trách nhiệm:

| Loại implementation | Đơn vị duy trì | Điều cần xác minh |
|---|---|---|
| Module trong dự án Spring Session | Nhóm duy trì Spring Session | Spring support policy, release tương thích, quy trình xử lý lỗi |
| Extension do nhà cung cấp duy trì | Nhà cung cấp kho dữ liệu hoặc nhóm sản phẩm | Chính sách hỗ trợ của nhà cung cấp, lịch phát hành, ma trận tương thích |
| Extension cộng đồng hoặc bên thứ ba | Tác giả hoặc tổ chức độc lập | Mức độ hoạt động, người review, quy trình phát hành, xử lý CVE và khả năng tiếp tục duy trì |
| Repository tự xây dựng nội bộ | Đội phát triển ứng dụng | Người chịu trách nhiệm dài hạn, kiểm thử hợp đồng, nâng cấp Spring và kho dữ liệu |

Không nên suy ra đơn vị duy trì chỉ từ tên artifact hoặc package. Hãy mở repository nguồn, đọc phần About/README, release notes, license, chính sách hỗ trợ và liên kết issue. Một thư viện có tên chứa Spring Session vẫn có thể là sản phẩm do bên khác phát triển.

## 3. Trường hợp MongoDB: thay đổi đơn vị duy trì qua các thế hệ

MongoDB là ví dụ điển hình cho lý do cần kiểm tra lịch sử và phiên bản extension. Trước thế hệ Spring Session 4.0, tích hợp MongoDB được phát hành dưới tọa độ Maven của Spring, thường là:

~~~xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-mongodb</artifactId>
    <version>SPRING_SESSION_VERSION</version>
</dependency>
~~~

Trong thế hệ cũ, package thường nằm dưới namespace org.springframework.session.data.mongo. Cách bật Servlet integration, converter và cấu hình MongoDB cần theo tài liệu của đúng nhánh Spring Session đang dùng.

Từ Spring Session 4.0, dự án MongoDB Spring Session được chuyển sang sự lãnh đạo và duy trì trực tiếp của nhóm MongoDB. Extension mới có tọa độ Maven:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-spring-session</artifactId>
    <version>MONGODB_SPRING_SESSION_VERSION</version>
</dependency>
~~~

Namespace API mới là org.mongodb.spring.session. Đây là thay đổi về artifact và package, nên việc nâng cấp không chỉ là tăng số phiên bản trong dependency. Import, cấu hình, converter và quy trình kiểm thử cũng cần được xem xét. Tài liệu extension mới nêu Jackson 2 converter là hướng cũ/deprecated và bổ sung converter cho Jackson 3.

Spring Boot 4 cũng thay đổi ranh giới tích hợp: direct support/auto-configuration cho Spring Session MongoDB đã được loại khỏi Boot khi phần tích hợp chuyển sang nhóm MongoDB. Vì vậy, ứng dụng Boot 4 cần khai báo dependency extension mới và làm theo hướng dẫn bật tích hợp của extension, thay vì giả định Boot tự chọn MongoDB như một store được Boot quản lý trực tiếp.

Các mốc trên là ranh giới quan trọng khi đọc tài liệu cũ và mới:

| Dòng ứng dụng | Artifact thường gặp | Namespace | Cách tiếp cận |
|---|---|---|---|
| Spring Session trước 4.0 | org.springframework.session:spring-session-data-mongodb | org.springframework.session.data.mongo | Theo tài liệu Spring Session của nhánh tương ứng |
| Spring Session 4.0 trở lên | org.mongodb:mongodb-spring-session | org.mongodb.spring.session | Theo tài liệu và release của MongoDB-maintained extension |
| Spring Boot 4 | Extension MongoDB khai báo riêng | Namespace mới của extension | Không mặc định có Boot auto-configuration trực tiếp cho MongoDB Session |

Không lấy một ví dụ cấu hình của Spring Session 3.x rồi áp dụng nguyên trạng cho Spring Session 4.x. Ngược lại, cũng không thay dependency cũ bằng dependency mới mà bỏ qua hướng dẫn migration của dự án.

## 4. Xác minh đơn vị duy trì và sức khỏe dự án

Trước khi đưa extension vào production, hãy xác minh nhóm nào chịu trách nhiệm cho mã nguồn và cách liên hệ khi có sự cố. Các tín hiệu cần xem xét gồm:

1. **Repository chính thức:** tổ chức sở hữu repository có đúng là nhóm duy trì được công bố không? Có liên kết từ trang sản phẩm hoặc tài liệu chính thức không?
2. **Release gần nhất:** có bản phát hành ổn định phù hợp với dòng Spring đang dùng không? Release note có nêu thay đổi API, serializer và yêu cầu runtime không?
3. **Hoạt động bảo trì:** issue và pull request có được phản hồi không? Có CI chạy thường xuyên không? Các lỗi bảo mật có quy trình xử lý không?
4. **License:** license có tương thích với chính sách phân phối và sử dụng của tổ chức không?
5. **Hỗ trợ:** có kênh issue, tracker hoặc support policy được công bố không? Thời hạn hỗ trợ của phiên bản có rõ ràng không?
6. **Tính liên tục:** nếu maintainer chính ngừng phát triển, tổ chức có thể fork, tiếp quản hoặc chuyển sang implementation khác không?

Số lượng star hoặc lượt tải không đủ để kết luận một thư viện được duy trì tốt. Một extension ít phổ biến nhưng được nhà cung cấp sản phẩm hỗ trợ chính thức có thể phù hợp hơn một thư viện phổ biến nhưng không có cam kết xử lý lỗi.

Với MongoDB Spring Session hiện tại, repository nguồn do tổ chức mongodb quản lý, tài liệu MongoDB cung cấp hướng dẫn tích hợp, migration và kênh phản hồi. Đây là cơ sở để xác định đơn vị duy trì của thế hệ mới. Tuy vậy, vẫn cần xem release cụ thể mà dự án định dùng, không suy ra rằng mọi version cũ và mới có cùng chính sách hỗ trợ.

## 5. Xác minh ma trận tương thích phiên bản

Tương thích cần được kiểm tra theo cả chuỗi dependency, không chỉ Spring Boot. Một extension có thể phụ thuộc đồng thời vào:

- Java/JDK.
- Spring Boot.
- Spring Framework.
- Spring Session Core.
- Spring Data MongoDB.
- MongoDB Java Driver.
- Jackson hoặc converter khác.
- MongoDB Server/Atlas và topology đang triển khai.

Ví dụ, việc extension biên dịch với Spring Session 4.x không tự chứng minh nó tương thích với mọi Spring Data MongoDB hoặc Java Driver. Phiên bản driver có thể thay đổi API, cấu hình UUID, kiểu dữ liệu BSON hoặc hành vi kết nối.

Dùng bảng sau để ghi nhận tương thích trước khi chọn release:

| Thành phần | Phiên bản ứng dụng | Phiên bản extension yêu cầu | Bằng chứng cần lưu |
|---|---|---|---|
| JDK | Phiên bản runtime và build | Minimum/maximum được công bố | Tài liệu yêu cầu và CI |
| Spring Boot | Dòng Boot đang chạy | Dòng được extension hỗ trợ | Compatibility page/release note |
| Spring Session | Core API đang dùng | Phiên bản API mà extension biên dịch | Dependency metadata và release note |
| Spring Data MongoDB | Module MongoDB đang dùng | Dòng tương thích | BOM hoặc ma trận của nhà cung cấp |
| MongoDB Java Driver | Driver thực tế trong dependency tree | Dòng driver được hỗ trợ | Compatibility table |
| MongoDB Server | Community/Enterprise/Atlas, version và topology | Dải server được kiểm thử | Bảng tương thích server/driver |
| Jackson | Jackson 2 hay 3 | Converter được hỗ trợ | Tài liệu migration và test |
| Servlet container | Servlet API và container | Baseline mà Boot/Spring yêu cầu | Tài liệu runtime |

Không dùng một bảng compatibility cũ làm bằng chứng cho bản release mới. Khi nâng cấp, hãy kiểm tra lại tất cả hàng trong bảng và lưu URL hoặc commit/release note đã dùng để quyết định.

## 6. Ví dụ kiểm tra dependency và namespace MongoDB

Với extension do MongoDB duy trì, dependency mới có tọa độ Maven như sau:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-spring-session</artifactId>
    <version>MONGODB_SPRING_SESSION_VERSION</version>
</dependency>
~~~

Ứng dụng cũng cần cấu hình Spring Data MongoDB/MongoDB Java Driver theo dòng Spring Boot đang dùng. Tên starter và property kết nối có thể thay đổi giữa các thế hệ Boot; hãy dùng dependency management và tài liệu của chính phiên bản ứng dụng.

Ví dụ cấu hình Servlet theo hướng extension mới:

~~~java
import org.mongodb.spring.session.config.annotation.web.http.EnableMongoHttpSession;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableMongoHttpSession
public class SessionConfiguration {
}
~~~

Annotation bật tích hợp cần được import từ namespace mới. Đoạn code chỉ minh họa việc bật MongoDB-backed HttpSession; cấu hình converter, timeout, collection, database và các tùy chọn khác cần theo API của phiên bản extension đang dùng.

Với extension cũ, package annotation thường thuộc namespace org.springframework.session.data.mongo. Không trộn annotation cũ với artifact mới. Một lỗi import không tồn tại sau nâng cấp thường là dấu hiệu dự án đang dùng tài liệu của thế hệ khác.

Khi dùng Spring Boot 4, không dựa vào việc Boot tự động tạo MongoDB session repository. Migration guide của Boot nêu rõ direct support cho Spring Session MongoDB đã được gỡ sau khi dự án chuyển sang nhóm MongoDB. Hãy xác nhận bean repository và springSessionRepositoryFilter thực sự có trong application context.

## 7. Khả năng lưu phiên phải được đánh giá theo từng tính năng

Trước khi chọn MongoDB hoặc một extension khác, hãy lập ma trận tính năng. Những mục dưới đây là câu hỏi cần xác minh, không phải cam kết rằng mọi extension đều hỗ trợ:

| Khả năng | Câu hỏi phải trả lời |
|---|---|
| Servlet HttpSession | Có thay thế HttpSession qua SessionRepositoryFilter không? |
| Reactive WebSession | Có implementation WebSessionRepository riêng không? |
| Session ID resolver | Có hỗ trợ cookie và header resolver chuẩn không? |
| TTL/expiration | Dữ liệu được hết hạn bằng TTL index, scheduler hay cơ chế khác? |
| Invalidate/delete | Xóa phiên có xóa mọi thuộc tính và dữ liệu phụ không? |
| Principal lookup | Có hỗ trợ FindByIndexNameSessionRepository và tìm theo principal không? |
| Session events | Có phát created/deleted/expired events không? Sự kiện có thể bị trễ hoặc mất không? |
| Flush/save policy | Có hỗ trợ flush mode và save mode tương tự Redis/JDBC không? |
| Concurrent update | Hai request cùng sửa một phiên được xử lý ra sao? Có optimistic locking/version không? |
| Serialization | Converter nào được dùng? Có hỗ trợ schema evolution và allowlist type không? |
| Transaction | Lưu session có tham gia transaction nghiệp vụ không? Ranh giới transaction là gì? |
| Multi-instance | Nhiều instance có thể đọc/ghi cùng phiên và cùng namespace không? |
| Observability | Có metric, log, tracing và thông tin lỗi đủ để vận hành không? |
| Backup/restore | Khôi phục database có giữ TTL/index và dữ liệu phiên đúng không? |

Một extension chỉ hỗ trợ CRUD cơ bản vẫn có thể đủ cho ứng dụng nhỏ. Nhưng nếu hệ thống cần giới hạn số phiên đồng thời, logout mọi thiết bị, phát sự kiện expiration hoặc xử lý đồng thời nghiêm ngặt, các tính năng đó phải được chứng minh trước khi chọn.

## 8. Đánh giá mô hình dữ liệu MongoDB

MongoDB lưu dữ liệu phiên dưới dạng document trong collection. Cách tổ chức document, tên collection, các field metadata và biểu diễn thuộc tính phụ thuộc extension và converter. Không nên giả định cấu trúc document nội bộ là API ổn định nếu tài liệu không cam kết.

Khi đánh giá schema, cần biết:

- Một session được lưu trong một document hay nhiều document.
- Session ID có được index duy nhất không.
- Principal name có index để tìm phiên không.
- Thời điểm hết hạn được lưu ở field nào và kiểu BSON nào.
- Có TTL index không, ai tạo index và khi nào index được cập nhật.
- Thuộc tính session được lưu dưới dạng BSON, JSON hay byte payload.
- Có version field hoặc optimistic locking không.
- Collection có hỗ trợ custom name/database không.

MongoDB TTL index là cơ chế dọn document hết hạn theo thời gian, nhưng tác vụ TTL chạy nền và không bảo đảm xóa đúng vào mili giây hết hạn. Vì vậy, repository vẫn phải kiểm tra thời hạn phiên trước khi chấp nhận một phiên. Không xem việc document còn nằm trong collection là bằng chứng phiên vẫn hợp lệ.

Nếu extension yêu cầu index, hãy xác định ai tạo index: application startup, migration, script triển khai hay DBA. Trong production, không nên để mọi instance tự tranh nhau tạo hoặc thay đổi index mà không có kế hoạch. Kiểm tra index sau triển khai và xác nhận kế hoạch query cho các thao tác đọc/ghi phổ biến.

## 9. Đánh giá topology, độ bền và khả năng phục hồi

Session thường được truy cập trên mỗi request, vì vậy độ trễ và độ sẵn sàng của kho dữ liệu ảnh hưởng trực tiếp đến trải nghiệm đăng nhập. Với MongoDB, hãy xác định extension hỗ trợ và đã kiểm thử với topology nào:

- Replica set.
- Sharded cluster.
- MongoDB Atlas.
- Cấu hình TLS và xác thực.
- Read preference và write concern.
- Retryable writes và retry policy.
- Failover khi primary thay đổi.
- Connection pool và giới hạn kết nối.

Không tự chọn read preference secondary cho session chỉ vì muốn giảm tải primary. Dữ liệu session cần được đọc nhất quán với các lần cập nhật gần nhất; đọc từ secondary có độ trễ sao chép có thể làm request thấy trạng thái cũ. Chính sách đọc/ghi cần theo tài liệu extension và yêu cầu nghiệp vụ.

Cũng cần quyết định write concern. Nếu xác nhận login thành công trước khi session được ghi đủ bền, failover có thể làm mất trạng thái mới. Write concern cao hơn có thể tăng độ trễ; lựa chọn phải được đo và thống nhất với yêu cầu sẵn sàng.

Đối với nhiều instance Spring, tất cả instance cần trỏ đến cùng deployment, cùng database/collection và cùng cách serialize. Một node dùng namespace hoặc converter khác có thể không đọc được session do node kia ghi.

## 10. Serialization và tương thích dữ liệu

Dữ liệu session tồn tại qua lần restart và có thể được đọc bởi phiên bản ứng dụng mới hơn. Với MongoDB extension, cần xác định converter đang dùng và format dữ liệu được lưu.

Các câu hỏi quan trọng:

- Dùng Java serialization, BSON mapping hay JSON converter?
- Type metadata có chứa tên package/class không?
- Jackson 2 hay Jackson 3 được hỗ trợ ở version này?
- Khi thêm hoặc đổi field, dữ liệu cũ được đọc như thế nào?
- Khi xóa class, session cũ có gây lỗi deserialize không?
- Có schema version và migration strategy không?
- Converter có giới hạn kiểu dữ liệu được phép khôi phục không?

Tài liệu extension MongoDB thế hệ mới đánh dấu Jackson 2 converter là deprecated và bổ sung Jackson 3 converter. Khi nâng cấp, không chỉ đổi import; cần kiểm tra cấu trúc payload, default value, type metadata và khả năng đọc session được ghi bởi version trước.

Nên lưu DTO nhỏ, ổn định trong session thay vì toàn bộ entity hoặc object graph của domain. Khi schema thay đổi, có thể chuyển đổi DTO theo version hoặc để session cũ hết hạn theo chính sách. Không nới lỏng deserialization filter chỉ để đọc mọi payload cũ.

## 11. TTL, expiration và sự kiện vòng đời

Một kho session cần xử lý thời hạn không hoạt động, invalidate và xóa dữ liệu. MongoDB TTL index có thể dọn document sau thời điểm hết hạn, nhưng cơ chế xóa nền không thay thế việc kiểm tra expiration khi tải phiên.

Khi đánh giá extension, hãy xác minh:

1. Timeout được cấu hình ở đâu và đơn vị là gì.
2. Last access time có được cập nhật theo mỗi request hay theo flush policy.
3. Expiry field có được tính lại khi session được truy cập không.
4. TTL index có được tạo tự động hay phải triển khai riêng.
5. Repository có từ chối session hết hạn trước khi TTL worker xóa document không.
6. Invalidate có xóa document ngay và phát sự kiện không.
7. SessionExpiredEvent có được phát khi TTL xóa document không, và cơ chế nào phát sự kiện đó.
8. Nếu instance tắt hoặc listener mất kết nối, sự kiện có được phát lại không.

Không giả định MongoDB extension có cùng semantics expiration events như Redis. Redis keyspace notifications, JDBC cleanup job và MongoDB TTL monitor là các cơ chế khác nhau. Nếu nghiệp vụ cần dọn tài nguyên ngoài session khi phiên hết hạn, cần kiểm tra khả năng phát event của extension và thiết kế TTL/cleanup job hoặc reconciliation bổ sung.

## 12. Kiểm tra cập nhật đồng thời

Hai request cùng dùng một session có thể cùng đọc một trạng thái rồi ghi lại gần như đồng thời. Nếu extension dùng thao tác đọc-sửa-ghi toàn document mà không có version check, lần ghi sau có thể ghi đè thay đổi của lần ghi trước.

Không thể suy ra hành vi cạnh tranh chỉ từ việc repository dùng MongoDB. Hãy tìm trong tài liệu hoặc mã nguồn xem implementation có dùng version field, optimistic locking, atomic update, find-and-modify hoặc cơ chế đồng bộ khác không.

Bài kiểm thử cần có:

- Hai request cùng sửa một thuộc tính.
- Hai request sửa hai thuộc tính khác nhau.
- Một request logout trong khi request khác đang lưu.
- Một request đổi session ID trong khi request khác đang sử dụng ID cũ.
- Hai instance cùng cập nhật một phiên.
- Timeout xảy ra trong lúc request đang xử lý.

Nếu cập nhật bị ghi đè, cân nhắc giảm dữ liệu mutable trong session, chuyển dữ liệu nghiệp vụ quan trọng sang repository có transaction/locking phù hợp hoặc tuần tự hóa thao tác cần thiết. Không dùng session repository như một distributed lock nếu extension không cam kết semantics đó.

## 13. Tích hợp Spring Boot và Servlet

Với Servlet application, extension cần đăng ký filter thay thế HttpSession mặc định. Trong các phiên bản MongoDB extension mới, ví dụ cấu hình dùng annotation EnableMongoHttpSession trong namespace org.mongodb.spring.session. Với thế hệ cũ, package và dependency khác.

Khi kiểm tra ứng dụng, xác nhận:

- Annotation hoặc cấu hình repository đã được nạp.
- Có bean SessionRepository đúng implementation.
- Có bean filter tên springSessionRepositoryFilter.
- Filter được áp dụng cho request cần quản lý session.
- Filter order phù hợp với Spring Security và các filter đọc HttpSession.
- MongoClient/ MongoDatabase được cấu hình từ nguồn tin cậy.
- Timeout, converter và index được cấu hình đúng.
- Không có hai repository khác nhau cùng được đăng ký ngoài ý muốn.

Với Spring Boot 4, direct support cho MongoDB Session đã được loại khỏi auto-configuration của Boot. Vì vậy, việc có starter MongoDB và artifact extension trên classpath không tự chứng minh toàn bộ cấu hình Session đã hoạt động. Dùng hướng dẫn chính thức của extension để bật tích hợp và kiểm tra application context.

Các property kết nối MongoDB có thể đổi prefix giữa các thế hệ Boot. Hãy đối chiếu migration guide của Boot thay vì sao chép application.yml từ một ví dụ Boot cũ.

## 14. So sánh MongoDB extension với Redis và JDBC

Lựa chọn kho phiên phụ thuộc hệ thống hiện tại, yêu cầu latency và các khả năng vận hành.

| Tiêu chí | MongoDB extension | Redis | JDBC |
|---|---|---|---|
| Mô hình dữ liệu | Document/collection | Key/value, hash và cấu trúc Redis | Bảng quan hệ |
| Phù hợp khi | Tổ chức đã vận hành MongoDB và muốn dùng cùng nền tảng document | Cần truy cập nhanh và TTL với hạ tầng Redis | Muốn lưu trong database quan hệ hiện có |
| Quản lý schema | Document schema và index | Namespace/key structure | DDL, index, migration SQL |
| Hết hạn | Phụ thuộc repository và TTL/index/scheduler | TTL và cơ chế expiration notification | Expiry metadata và cleanup job |
| Tìm theo principal | Phải xác minh extension hỗ trợ index API | Có thể dùng indexed repository | Tùy repository/schema |
| Sự kiện vòng đời | Phải xác minh implementation | Phụ thuộc event/notification configuration | Phụ thuộc cleanup và repository |
| Tương thích phiên bản | Có ranh giới extension và maintainer riêng | Module Spring Session Redis | Module Spring Session JDBC |
| Trách nhiệm tích hợp | Có thể cần cấu hình thủ công, đặc biệt từ Boot 4 | Hệ sinh thái Spring Boot tích hợp sâu | Hệ sinh thái Spring Boot tích hợp sâu |

MongoDB không tự động là lựa chọn tốt hơn chỉ vì ứng dụng đã dùng MongoDB cho dữ liệu nghiệp vụ. Session có đặc điểm tải và vòng đời khác document nghiệp vụ. Hãy cân nhắc tách database hoặc collection, index riêng, quyền truy cập riêng và giới hạn tài nguyên để session traffic không ảnh hưởng workload chính.

## 15. Đánh giá các extension khác

Spring Session có thể được mở rộng cho các kho dữ liệu khác. Tài liệu hiện tại liệt kê một số community extensions:

| Extension | Hướng sử dụng | Điều cần xác minh |
|---|---|---|
| MongoDB | Lưu session dưới dạng document qua Spring Data MongoDB | Maintainer, artifact mới/cũ, Boot 4, converter, TTL và concurrency |
| Hazelcast | Kho dữ liệu phân tán trong hệ sinh thái Hazelcast | Version của Hazelcast, Spring Session adapter, support policy và cluster semantics |
| Infinispan | Kho dữ liệu phân tán theo Infinispan | Module tích hợp, cache mode, expiration, transaction và compatibility |
| Caffeine | Cache trong JVM | Có phù hợp một instance hay không; không mặc định là kho chia sẻ nhiều node |
| Geode | Kho dữ liệu phân tán qua dự án Spring Session Data Geode | Repository riêng, version Spring Data Geode và chính sách hỗ trợ |

Không chọn extension chỉ vì tên công nghệ xuất hiện trong danh sách community. Cần xem tài liệu của extension có cập nhật không, tương thích Spring Session core version nào, hỗ trợ Servlet hay WebFlux, có release ổn định và có kiểm thử với phiên bản kho dữ liệu đang vận hành không.

Đặc biệt, cache cục bộ như Caffeine không tự cung cấp chia sẻ session giữa nhiều instance. Nếu mỗi JVM có cache riêng, request chuyển sang node khác có thể không khôi phục được phiên. Muốn dùng trong môi trường nhiều node phải có cơ chế đồng bộ/replication được extension cam kết và kiểm thử.

## 16. Bộ kiểm tra khả năng trước khi phê duyệt extension

Có thể dùng checklist dưới đây trong review kỹ thuật:

- [ ] Xác định tổ chức hoặc nhóm duy trì extension.
- [ ] Xác nhận repository nguồn và license.
- [ ] Kiểm tra release ổn định và chính sách hỗ trợ.
- [ ] Đối chiếu JDK, Spring Boot, Spring Framework và Spring Session.
- [ ] Đối chiếu Spring Data và driver của kho dữ liệu.
- [ ] Xác nhận version server/database được hỗ trợ.
- [ ] Xác nhận Servlet HttpSession hoặc reactive WebSession theo nhu cầu.
- [ ] Kiểm tra TTL, expiration và cleanup.
- [ ] Kiểm tra invalidate, delete và session ID rotation.
- [ ] Kiểm tra principal index, session events và concurrent update nếu cần.
- [ ] Kiểm tra converter, schema evolution và deserialization security.
- [ ] Kiểm tra multi-instance, failover, backup và restore.
- [ ] Kiểm tra metric, logging, tracing và quy trình xử lý lỗi.
- [ ] Chạy integration test với đúng database/cluster của môi trường triển khai.
- [ ] Có kế hoạch rollback hoặc chuyển sang repository khác.

Nếu một khả năng là yêu cầu bắt buộc nhưng extension không có tài liệu hoặc kiểm thử chứng minh, hãy xem đó là rủi ro chưa được giải quyết. Có thể tự kiểm chứng bằng test tích hợp hoặc chọn repository khác.

## 17. Kiểm thử tích hợp MongoDB

Một bài kiểm thử chỉ xác nhận Spring context khởi động không chứng minh session được lưu bền vững. Cần kiểm tra qua HTTP và MongoDB deployment tương tự production.

Các trường hợp nên có:

1. Request đầu tiên tạo session và ghi một thuộc tính.
2. Xác nhận response trả session ID qua cookie hoặc header theo resolver.
3. Request kế tiếp gửi lại ID và đọc được thuộc tính đã lưu.
4. Gửi request đến instance khác và xác nhận cùng session được khôi phục.
5. Restart một instance rồi gửi lại ID, xác nhận phiên vẫn tồn tại trong thời hạn.
6. Đợi quá timeout và xác nhận repository từ chối phiên hết hạn.
7. Invalidate phiên và xác nhận phiên không thể khôi phục lại.
8. Kiểm tra collection/index cần thiết đã được tạo đúng.
9. Chạy hai request đồng thời cùng sửa session để quan sát lost update.
10. Kiểm tra logout và session ID rotation.
11. Kiểm tra converter đọc được fixture được tạo từ phiên bản trước nếu đang nâng cấp.
12. Ngắt kết nối MongoDB hoặc mô phỏng failover để xác nhận timeout, retry và lỗi được xử lý đúng.

MongoDB extension do MongoDB duy trì có unit test và integration test riêng; hướng dẫn của dự án nêu integration test cần một MongoDB deployment. Điều đó là tín hiệu cần có môi trường database thật hoặc tương thích trong pipeline của ứng dụng, thay vì chỉ dựa vào mock repository.

## 18. Kế hoạch nâng cấp từ extension cũ sang mới

Khi nâng cấp từ Spring Session MongoDB cũ sang thế hệ MongoDB-maintained, hãy coi đây là một migration tích hợp:

1. Ghi lại artifact, version, package, converter và cấu hình đang chạy.
2. Đọc migration guide của MongoDB extension và release notes của Spring Session/Boot.
3. Đối chiếu ma trận tương thích của JDK, Boot, Spring Session, Spring Data MongoDB, Java Driver và MongoDB Server.
4. Chuyển dependency sang tọa độ mới theo version đã xác minh.
5. Cập nhật import từ org.springframework.session.data.mongo sang org.mongodb.spring.session.
6. Chuyển sang converter phù hợp; ưu tiên Jackson 3 converter ở thế hệ mới nếu ứng dụng dùng JSON.
7. Kiểm tra cấu hình Boot 4 vì auto-configuration MongoDB Session trực tiếp đã bị loại.
8. Kiểm tra dữ liệu session cũ có thể đọc được bằng converter mới hay cần migration.
9. Chạy test với session fixture từ phiên bản cũ và các luồng login/logout.
10. Triển khai theo chiến lược tương thích đọc/ghi hoặc chấp nhận tạo namespace mới và yêu cầu xác thực lại.
11. Theo dõi lỗi deserialize, session miss, TTL cleanup và độ trễ repository sau rollout.

Trong rolling deployment, không để instance cũ đọc dữ liệu đã được instance mới ghi bằng format mà nó không hiểu. Nếu không thể duy trì tương thích giữa hai thế hệ extension, hãy lập kế hoạch cắt chuyển rõ ràng, gồm tác động đến người dùng và phương án rollback.

## 19. Nguồn kiểm tra phiên bản và khả năng

Khi triển khai thực tế, dùng tài liệu của đúng bên duy trì và đúng release:

- [Spring Session Reference](https://docs.spring.io/spring-session/reference/index.html): API chung, các module và danh sách community extensions.
- [MongoDB Spring Session Integration](https://www.mongodb.com/docs/drivers/java/sync/current/integrations/spring-session/): trạng thái duy trì, artifact mới, namespace và converter.
- [MongoDB Spring Session source repository](https://github.com/mongodb/mongo-spring-session): release, issue, mã nguồn và hướng dẫn đóng góp.
- [MongoDB Spring Session getting started](https://www.mongodb.com/docs/drivers/java/sync/current/integrations/spring-session/spring-session-get-started/): cấu hình ứng dụng Boot và kiểm tra session.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi auto-configuration và dependency.
- [Spring Session MongoDB guide for older releases](https://docs.spring.io/spring-session/reference/3.3/guides/boot-mongo.html): tham khảo cấu hình thế hệ cũ; không áp dụng nguyên trạng cho extension mới.

Hãy lưu phiên bản tài liệu, tọa độ artifact và kết quả compatibility review trong hồ sơ kỹ thuật của dự án. Tài liệu trực tuyến có thể cập nhật theo release mới, vì vậy khi nâng cấp cần kiểm tra lại thay vì dựa vào ghi chú cũ.

## Kết luận

MongoDB và các repository mở rộng giúp Spring Session dùng thêm những nền tảng lưu trữ ngoài Redis và JDBC, nhưng mức độ tích hợp và trách nhiệm bảo trì không giống nhau. Với MongoDB, cần phân biệt extension cũ do Spring phát hành với thế hệ từ Spring Session 4.0 do MongoDB duy trì, gồm tọa độ Maven và namespace API mới. Spring Boot 4 đã bỏ direct support cho MongoDB Session, nên phải xác minh cách bật repository của extension. Trước khi chọn bất kỳ extension nào, hãy kiểm tra đơn vị duy trì, ma trận JDK/Spring/driver/server, TTL, sự kiện, truy vấn principal, serialization, cập nhật đồng thời và hành vi nhiều instance. Chỉ phê duyệt khi các khả năng bắt buộc đã được tài liệu hoặc integration test chứng minh.
