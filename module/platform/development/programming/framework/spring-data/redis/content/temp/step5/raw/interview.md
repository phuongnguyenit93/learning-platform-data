Bạn giải thích Redis phù hợp với những bài toán nào khi ứng dụng Spring Boot cần truy cập dữ liệu độ trễ thấp?
Bạn phân biệt Redis là kho dữ liệu trong bộ nhớ với Redis được dùng làm cache trước database như thế nào?
Bạn lựa chọn Redis hay database quan hệ để lưu trạng thái nghiệp vụ theo yêu cầu độ bền và transaction nào?
Bạn đánh giá những hạn chế của Redis khi tập dữ liệu vượt dung lượng RAM sẵn có ra sao?
Bạn phân biệt Redis key-value đơn giản với mô hình nhiều kiểu dữ liệu của Redis theo nhu cầu nào?
Bạn giải thích vòng đời một lệnh Redis từ Spring application qua client connection tới server như thế nào?
Bạn phân biệt latency mạng với thời gian thực thi lệnh trong Redis khi đo hiệu năng ra sao?
Bạn đánh giá rủi ro khi một lệnh xử lý quá nhiều phần tử chặn luồng thực thi Redis như thế nào?
Bạn xác định khi nào Redis là nguồn dữ liệu chính và khi nào chỉ là bản sao có thể tái tạo?
Bạn so sánh Redis với bộ nhớ cache trong từng JVM khi triển khai nhiều replica ứng dụng như thế nào?
Bạn thiết kế cơ chế fallback khi Redis không khả dụng nhưng database nguồn vẫn hoạt động ra sao?
Bạn phân biệt tính bền vững của cache và yêu cầu khôi phục dữ liệu sau khi Redis restart như thế nào?
Bạn lựa chọn cách cô lập dữ liệu theo ứng dụng, tenant hoặc môi trường trong một cụm Redis dùng chung ra sao?
Bạn giải thích Redis logical databases khác gì physical isolation giữa nhiều Redis instances?
Bạn đánh giá giới hạn logical databases trong Redis Cluster khi thiết kế chia môi trường như thế nào?
Bạn xác định mục tiêu p95 latency và throughput của Redis dựa trên luồng request nghiệp vụ ra sao?
Bạn thiết kế kiểm soát truy cập để một dịch vụ không thể ghi đè keys của dịch vụ khác như thế nào?
Bạn đánh giá rủi ro sử dụng Redis làm hàng đợi công việc mà không xét yêu cầu xử lý lại ra sao?
Bạn phân biệt Redis Pub/Sub, Redis Streams và một message broker truyền thống ở các bảo đảm giao nhận nào?
Bạn xác định những tình huống nên giảm phụ thuộc vào Redis trong đường xử lý request đồng bộ ra sao?
Bạn thiết kế chuẩn naming và ownership cho keys để nhiều nhóm phát triển cùng quản lý mà không xung đột như thế nào?
Bạn xác định khi nào cần kết hợp Redis với database gốc thay vì lưu toàn bộ dữ liệu trực tiếp vào Redis ra sao?
Bạn đánh giá sự khác nhau giữa tính nhất quán dữ liệu trong Redis đơn node và hệ thống có replica hoặc cluster như thế nào?
Bạn lựa chọn mô hình triển khai Redis standalone, Sentinel hay Cluster dựa trên yêu cầu availability và scale nào?
Bạn thiết kế quy trình theo dõi thay đổi lược đồ key khi ứng dụng không có migration SQL như thế nào?
Bạn phân biệt Spring Data Redis với Redis client Lettuce hoặc Jedis ở trách nhiệm nào?
Bạn lựa chọn spring-boot-starter-data-redis hoặc starter reactive theo mô hình I/O của ứng dụng như thế nào?
Bạn mô tả vai trò của RedisConnectionFactory trong cấu hình Spring Data Redis ra sao?
Bạn giải thích cách Spring Boot cấu hình RedisConnectionFactory và RedisTemplate từ properties như thế nào?
Bạn xác định những điều kiện nên tự định nghĩa bean RedisTemplate thay vì dùng template mặc định ra sao?
Bạn cấu hình endpoint, port, username và secret Redis riêng theo môi trường triển khai như thế nào?
Bạn kiểm tra cơ chế kết nối Redis qua TLS và xác minh chứng chỉ ở client như thế nào?
Bạn quản lý Redis ACL credentials bằng secret manager và xử lý rotation không gián đoạn ra sao?
Bạn lựa chọn Lettuce hoặc Jedis theo hành vi connection, thread safety và yêu cầu vận hành như thế nào?
Bạn giải thích tác động của shared native connection trong Lettuce tới các thao tác blocking và transaction như thế nào?
Bạn xác định khi nào cần connection pooling thay vì chia sẻ connection đối với workload Redis nào?
Bạn phân biệt connection timeout, command timeout và timeout tổng thể của một HTTP request như thế nào?
Bạn cấu hình Redis Sentinel endpoints và master name cho ứng dụng Spring Boot ra sao?
Bạn thiết kế kết nối Redis Cluster để client phát hiện topology và xử lý chuyển hướng theo hash slot như thế nào?
Bạn đánh giá rủi ro cấu hình ứng dụng chỉ dùng một Redis node address khi node đó gặp lỗi?
Bạn xác định khi nào cần đọc từ replicas và ảnh hưởng của replication lag tới kết quả trả về ra sao?
Bạn phân biệt Lettuce topology refresh với DNS refresh khi Redis Cluster thay đổi nodes như thế nào?
Bạn theo dõi số connection, pending commands và pool exhaustion để chẩn đoán nghẽn client ra sao?
Bạn xử lý trường hợp RedisConnectionFactory tạo kết nối thành công nhưng command đầu tiên lại timeout như thế nào?
Bạn tổ chức nhiều RedisConnectionFactory cho các cụm Redis khác nhau mà không trộn lẫn templates ra sao?
Bạn quản lý lifecycle và đóng Redis client resources khi ApplicationContext shutdown như thế nào?
Bạn đánh giá ảnh hưởng của tự tạo Redis client cho mỗi request tới socket và RAM ra sao?
Bạn kiểm tra tác động của event-loop blocking nếu gọi RedisTemplate trong WebFlux handler như thế nào?
Bạn sử dụng ReactiveRedisTemplate để thao tác Redis mà không chặn Reactor event loop ra sao?
Bạn phân biệt reactive Redis operation với việc bọc RedisTemplate blocking bằng Mono theo hiệu quả thực tế như thế nào?
Bạn xác định cách truyền cancellation và timeout qua reactive Redis pipeline theo khả năng client như thế nào?
Bạn thiết kế health check Redis không khiến liveness của hàng trăm pods thất bại đồng loạt khi cache outage ra sao?
Bạn kiểm thử connection failover và Redis client reconnect trong môi trường staging như thế nào?
Bạn phân biệt RedisTemplate<K,V> và StringRedisTemplate về serializer cùng kiểu dữ liệu như thế nào?
Bạn giải thích vai trò của keySerializer, valueSerializer, hashKeySerializer và hashValueSerializer ra sao?
Bạn lựa chọn StringRedisSerializer cho keys theo các tiêu chí tương thích và khả năng debug nào?
Bạn so sánh JSON serialization với Java native serialization về bảo mật, kích thước và tương thích phiên bản như thế nào?
Bạn đánh giá rủi ro sử dụng JDK serialization cho các giá trị Redis có nguồn dữ liệu không tin cậy?
Bạn chọn Jackson-based serializer phù hợp theo phiên bản Spring Data Redis và cách kiểm soát type information ra sao?
Bạn thiết kế JSON serializer không cho phép polymorphic deserialization không kiểm soát từ Redis như thế nào?
Bạn phân biệt lưu dữ liệu dạng String thuần với JSON object trong Redis về khả năng thay đổi schema ra sao?
Bạn kiểm thử serializer round-trip cho LocalDateTime, BigDecimal, enum và Unicode tiếng Việt như thế nào?
Bạn đánh giá ảnh hưởng của việc đổi serializer khi trong Redis còn values do phiên bản cũ ghi ra sao?
Bạn thiết kế key versioning để hỗ trợ chuyển JSON schema mà không phải xóa toàn bộ Redis cache ra sao?
Bạn xác định cách phát hiện serialization mismatch khi một service đọc key do service khác ghi như thế nào?
Bạn kiểm soát memory footprint của serialized objects để tránh lưu payload quá lớn trong Redis ra sao?
Bạn lựa chọn nén giá trị trước khi lưu Redis dựa trên kích thước payload, chi phí CPU và mức tiết kiệm RAM ra sao?
Bạn phân biệt RedisTemplate.opsForValue với BoundValueOperations về cách thao tác một key ra sao?
Bạn tổ chức một Redis access adapter để business service không phụ thuộc trực tiếp vào RedisTemplate như thế nào?
Bạn kiểm soát null values khi RedisTemplate đọc key không tồn tại và khi converter trả null như thế nào?
Bạn phân biệt RedisCallback và SessionCallback khi cần thực hiện thao tác ở mức kết nối hoặc nhiều lệnh như thế nào?
Bạn lựa chọn thao tác value, hash hoặc sorted set thay vì serialize toàn bộ object theo access pattern nào?
Bạn kiểm tra key serializers tương thích với dữ liệu cũ khi đổi StringRedisTemplate sang template tùy chỉnh ra sao?
Bạn xử lý giá trị Redis bị hỏng hoặc không deserialize được mà không làm tất cả request thất bại như thế nào?
Bạn thiết kế metrics riêng cho hit, miss, serializer failure và Redis command latency ở adapter như thế nào?
Bạn phân biệt lỗi dữ liệu thiếu khỏi lỗi connection timeout trong API truy cập Redis như thế nào?
Bạn sử dụng StringRedisTemplate cho counter hoặc token đơn giản theo điều kiện nào?
Bạn kiểm thử hai RedisTemplates có serializer khác nhau không vô tình đọc cùng key namespace ra sao?
Bạn xác định độ dài và cấu trúc Redis key tối ưu giữa dễ quan sát với chi phí bộ nhớ ra sao?
Bạn thiết kế quy tắc đặt tên key gồm application, tenant, entity, ID và schema version như thế nào?
Bạn tránh dùng các chuỗi chứa thông tin cá nhân trực tiếp làm Redis key để bảo vệ dữ liệu như thế nào?
Bạn phân biệt key prefix với Redis Cluster hash tag trong chiến lược định tuyến dữ liệu như thế nào?
Bạn thiết kế key collision prevention khi hai loại dữ liệu dùng cùng một business ID ra sao?
Bạn lựa chọn TTL cho cache sản phẩm, phiên đăng nhập và rate limit theo yêu cầu dữ liệu nào?
Bạn phân biệt lệnh EXPIRE, PEXPIRE và expiration được gắn ngay khi SET về ngữ nghĩa như thế nào?
Bạn kiểm tra TTL -1 và -2 để phân biệt key không có expiration với key không tồn tại ra sao?
Bạn quyết định có refresh TTL khi đọc hay chỉ khi ghi theo semantics sliding expiration nào?
Bạn thiết kế cache key sao cho thay đổi tenant hoặc quyền truy cập không làm trả dữ liệu của người khác ra sao?
Bạn đánh giá rủi ro key không có TTL tồn tại vô hạn trong cache có dung lượng giới hạn?
Bạn áp dụng TTL jitter để giảm nguy cơ nhiều keys cùng hết hạn gây tải đột biến như thế nào?
Bạn thiết kế hard expiration và soft expiration khi hệ thống chấp nhận stale data trong thời gian ngắn ra sao?
Bạn phân biệt Redis key expiration với eviction do memory pressure trong chẩn đoán cache miss như thế nào?
Bạn lựa chọn maxmemory-policy phù hợp khi Redis đồng thời chứa cache và dữ liệu cần giữ lâu như thế nào?
Bạn đánh giá rủi ro eviction khi dùng chung Redis cho sessions, locks và cache ít quan trọng như thế nào?
Bạn thiết kế lifecycle xóa keys theo business deletion thay vì chỉ dựa vào TTL như thế nào?
Bạn xử lý trường hợp ghi đè value khiến TTL thay đổi ngoài ý muốn bằng cách kiểm tra semantics lệnh nào?
Bạn xác định khi nào dùng SET với NX hoặc XX và điều kiện TTL đi kèm theo use case nào?
Bạn tránh dùng KEYS pattern trên Redis production đông dữ liệu theo lý do hiệu năng nào?
Bạn dùng SCAN để duyệt keyspace có kiểm soát và giải thích giới hạn về trùng hoặc thiếu giữa các lần quét ra sao?
Bạn thiết kế công việc cleanup keys cũ theo phiên bản namespace mà không khóa Redis server như thế nào?
Bạn phân biệt DEL và UNLINK khi xóa giá trị lớn theo mục tiêu giảm blocking như thế nào?
Bạn đánh giá chi phí truy xuất một key có value cực lớn so với nhiều keys nhỏ như thế nào?
Bạn xác định tiêu chí chuyển dữ liệu ít dùng khỏi Redis sang storage có chi phí thấp hơn như thế nào?
Bạn thiết kế memory usage monitoring theo key prefix mà không chạy full scan gây quá tải như thế nào?
Bạn xử lý khi Redis trả OOM error do maxmemory không cho phép ghi mới theo chính sách fallback nào?
Bạn xác định cách tránh thundering herd sau khi cache key phổ biến hết hạn như thế nào?
Bạn so sánh Redis String, Hash, List, Set và Sorted Set theo dạng truy vấn được hỗ trợ như thế nào?
Bạn lựa chọn String với INCR/DECR để đếm lượt truy cập mà không gặp lost update ra sao?
Bạn phân biệt INCR atomic trên một key với transaction cập nhật nhiều business entities như thế nào?
Bạn thiết kế giới hạn số lần gọi API bằng counter và TTL dựa trên yêu cầu time window nào?
Bạn đánh giá lỗi race condition khi đặt TTL riêng sau INCR cho key mới như thế nào?
Bạn so sánh lưu các trường entity bằng Redis Hash với serialize toàn bộ object theo nhu cầu cập nhật và truy xuất ra sao?
Bạn thao tác HashOperations để đọc hoặc cập nhật một field mà không tải mọi field ra sao?
Bạn thiết kế schema evolution của Redis hash khi application version mới thêm field tùy chọn như thế nào?
Bạn đánh giá rủi ro lưu một hash có quá nhiều fields và chi phí memory của nó ra sao?
Bạn phân biệt TTL trên Redis key hash với TTL từng field dựa trên phiên bản Redis và client hỗ trợ như thế nào?
Bạn lựa chọn List cho FIFO queue đơn giản và xác định hạn chế trong đảm bảo delivery ra sao?
Bạn phân biệt LPUSH/RPOP và RPUSH/LPOP khi giữ thứ tự enqueue/dequeue như thế nào?
Bạn sử dụng ListOperations cho bounded recent-items list và xử lý trim thế nào?
Bạn thiết kế reliable work queue trên Redis List và đánh giá nhu cầu recovery khi worker crash ra sao?
Bạn xác định khi nào Redis Streams phù hợp hơn List để theo dõi consumer acknowledgments?
Bạn dùng SetOperations để quản lý tập user IDs không trùng và kiểm tra membership như thế nào?
Bạn phân biệt SADD/SREM atomic với việc cập nhật nhiều sets cần tính nhất quán nghiệp vụ ra sao?
Bạn thiết kế giao hoặc hợp của nhiều Redis sets để phục vụ bộ lọc theo quyền như thế nào?
Bạn đánh giá chi phí phép giao lớn giữa các sets có cardinality cao trước khi đưa vào hot path ra sao?
Bạn sử dụng Sorted Set để triển khai leaderboard với score và thứ hạng theo điều kiện nào?
Bạn cập nhật score trong ZSet khi sự kiện tính điểm có thể bị giao trùng bằng phương án nào?
Bạn phân biệt thứ hạng theo ZRANK và ZREVRANK về quy tắc sắp xếp ra sao?
Bạn thiết kế phân trang leaderboard với score đồng hạng và yêu cầu ổn định như thế nào?
Bạn xử lý member bị xóa hoặc score bị đổi giữa hai lượt lấy trang leaderboard ra sao?
Bạn lựa chọn ZSet cho sliding-window rate limiter và kiểm soát cleanup các phần tử cũ thế nào?
Bạn dùng GeoOperations để lưu vị trí và truy vấn điểm gần người dùng theo yêu cầu nào?
Bạn xác định giới hạn của Redis GEO so với một hệ thống GIS chuyên dụng như thế nào?
Bạn sử dụng HyperLogLogOperations khi cần ước lượng unique visitors theo sai số chấp nhận được ra sao?
Bạn phân biệt PFCOUNT ước lượng với tập Set chính xác về bộ nhớ và tính đúng đắn như thế nào?
Bạn xác định khi nào Redis bitmap phù hợp cho trạng thái boolean theo ID số và nhược điểm của sparse bitmap ra sao?
Bạn thiết kế cấu trúc Redis để lưu session activity mà tránh tạo quá nhiều keys ngắn hạn như thế nào?
Bạn đánh giá các chi phí lệnh LRANGE, SMEMBERS hoặc HGETALL trên cấu trúc rất lớn như thế nào?
Bạn giới hạn kích thước kết quả cho một Redis read để không tạo response payload khổng lồ ra sao?
Bạn kiểm thử thao tác trên các Redis data types bằng RedisTemplate Operations tương ứng như thế nào?
Bạn phân biệt Redis repository với RedisTemplate về mức trừu tượng và quyền kiểm soát Redis commands ra sao?
Bạn định nghĩa entity với @RedisHash và @Id trong Spring Data Redis repositories như thế nào?
Bạn giải thích cách Spring Data Redis repository biểu diễn entity và ID thành keys hoặc hashes như thế nào?
Bạn lựa chọn ID ổn định cho Redis entity khi dữ liệu được cập nhật hoặc đọc từ nhiều services ra sao?
Bạn xác định tác động của keyspace prefix trong @RedisHash khi có hai loại entity trùng business ID như thế nào?
Bạn quản lý expiration cho entity qua @RedisHash(timeToLive) hoặc @TimeToLive theo nhu cầu nào?
Bạn phân biệt TTL annotation trên Redis repository entity với TTL của một cache entry trong Spring Cache như thế nào?
Bạn kiểm tra @TimeToLive property được đọc hoặc cập nhật sau khi lưu entity như thế nào?
Bạn thiết kế repository derived queries dựa trên @Indexed và các giới hạn của secondary indexes trong Redis ra sao?
Bạn xác định chi phí cập nhật index sets khi repository save hoặc delete nhiều entity như thế nào?
Bạn giải thích vì sao Redis repository secondary indexes không phải search engine cho truy vấn tùy ý?
Bạn xử lý việc một repository query trả thiếu entity do secondary index không được đồng bộ khi dữ liệu hết hạn ra sao?
Bạn đánh giá vai trò keyspace notifications trong việc cleanup secondary indexes sau expiration như thế nào?
Bạn thiết kế hành vi khi Redis keyspace notifications bị tắt hoặc server cấu hình không cho thay đổi như thế nào?
Bạn kiểm tra expiry event không được phát tới listener đang offline và ảnh hưởng đến repository indexes ra sao?
Bạn phân biệt expiration event với dữ liệu gốc đã hết hạn theo tính bền vững của thông báo như thế nào?
Bạn thiết kế cách tái xây dựng secondary indexes khi phát hiện dữ liệu index bị sai lệch ra sao?
Bạn kiểm soát lưu ý @Reference trong repository khi các referenced entities có TTL khác nhau như thế nào?
Bạn tránh chu kỳ tham chiếu hoặc đọc quá nhiều đối tượng qua reference khi thiết kế Redis entities như thế nào?
Bạn xác định khi nào nên dùng RedisTemplate trực tiếp thay repository để thao tác key-specific cần atomicity?
Bạn kiểm thử repository read/write/delete và TTL trên Redis thực thay vì chỉ mock interface như thế nào?
Bạn quyết định tách Redis entity khỏi API DTO và domain model trong hệ thống có nhiều nguồn dữ liệu ra sao?
Bạn xác định cách migrate Redis repository entity khi serializer hoặc keyspace version thay đổi như thế nào?
Bạn giải thích Spring Cache abstraction sử dụng Redis làm backend qua RedisCacheManager như thế nào?
Bạn phân biệt @Cacheable, @CachePut và @CacheEvict theo tác động tới việc gọi phương thức như thế nào?
Bạn lựa chọn phương thức nên cache dựa trên độ tốn kém tính toán và tính ổn định của kết quả ra sao?
Bạn thiết kế cache key với SpEL gồm tenant và tham số nghiệp vụ để tránh cache poisoning như thế nào?
Bạn phân biệt cache name với key trong RedisCacheManager khi nhiều loại dữ liệu có TTL khác nhau ra sao?
Bạn cấu hình TTL riêng cho từng cache region qua RedisCacheConfiguration theo yêu cầu nào?
Bạn kiểm soát serializer của RedisCacheManager để không xung đột với RedisTemplate và data formats cũ ra sao?
Bạn lựa chọn cache null values hoặc bỏ qua null theo yêu cầu tránh cache penetration nào?
Bạn thiết kế cache-aside với Redis và database gốc theo thứ tự read, miss, load, write ra sao?
Bạn xử lý cache stampede khi nhiều requests cùng miss một hot key như thế nào?
Bạn giải thích giới hạn của @Cacheable(sync=true) đối với đồng bộ giữa nhiều JVM và provider cache ra sao?
Bạn thiết kế distributed single-flight hoặc locking để giảm cache stampede mà vẫn có timeout an toàn như thế nào?
Bạn phân biệt cache penetration với cache avalanche và cache breakdown theo triệu chứng nào?
Bạn bảo vệ database khỏi cache avalanche khi nhiều TTL hết hạn đồng thời bằng những cơ chế nào?
Bạn tổ chức negative caching với TTL ngắn cho ID không tồn tại mà tránh che giấu bản ghi mới ra sao?
Bạn quyết định thực hiện write-through, write-behind hay cache-aside theo yêu cầu consistency và failure nào?
Bạn lựa chọn thời điểm evict cache so với database commit để hạn chế dữ liệu không nhất quán ra sao?
Bạn đánh giá race condition giữa cập nhật database, xóa cache và request đọc đồng thời ra sao?
Bạn thiết kế cache invalidation khi thông tin user permissions hoặc product price thay đổi như thế nào?
Bạn xử lý cache được làm mới bằng dữ liệu cũ ngay sau khi một thread khác xóa cache như thế nào?
Bạn áp dụng versioned keys hoặc entity revision để tránh giá trị cache cũ ghi đè bản mới ra sao?
Bạn lựa chọn cache TTL cho dữ liệu nhạy cảm cần thu hồi ngay quyền truy cập theo tiêu chí nào?
Bạn phân biệt local cache và Redis distributed cache trong xử lý invalidation đa replica ra sao?
Bạn đánh giá rủi ro self-invocation khiến @Cacheable không được Spring proxy intercept như thế nào?
Bạn kiểm tra @EnableCaching và proxy configuration khi method cache annotations không có tác dụng ra sao?
Bạn thiết kế cache cho phương thức trả Mono/Flux phù hợp khả năng hỗ trợ của Spring Framework đang dùng như thế nào?
Bạn lựa chọn RedisCacheWriter có lock hay không lock tùy yêu cầu thao tác cache nào?
Bạn đánh giá rủi ro clear toàn bộ cache region bằng cơ chế quét keys trên Redis production như thế nào?
Bạn đánh giá vai trò và giới hạn của cache transaction awareness trong RedisCacheManager đối với vòng đời transaction như thế nào?
Bạn phân biệt transaction-aware cache operation với transaction nguyên tử giữa database và Redis ra sao?
Bạn đo cache hit ratio, miss rate và load latency để quyết định thay đổi TTL như thế nào?
Bạn tổ chức warm-up cho hot cache sau deployment mà không làm quá tải database nguồn ra sao?
Bạn thiết kế fallback khi Redis cache timeout: trả dữ liệu gốc, dữ liệu stale hay lỗi theo tình huống nào?
Bạn kiểm soát key cardinality và số lượng biến thể query được cache để tránh RAM tăng không giới hạn ra sao?
Những điều kiện nào khiến bạn không nên cache kết quả tìm kiếm phụ thuộc vào quyền truy cập thay đổi liên tục?
Bạn giải thích Redis Pub/Sub hoạt động theo channel và subscribers như thế nào?
Bạn phân biệt Redis Pub/Sub với Redis Streams về durability và khả năng đọc lại message ra sao?
Bạn lựa chọn Pub/Sub cho tín hiệu vô trạng thái nào và tránh dùng nó cho nghiệp vụ bắt buộc xử lý lại ra sao?
Bạn thiết kế RedisMessageListenerContainer nhận messages và quản lý lifecycle listeners như thế nào?
Bạn phân biệt channel subscription và pattern subscription theo cách định tuyến sự kiện ra sao?
Bạn cấu hình RedisMessageListener và MessageListenerAdapter để gọi handler application như thế nào?
Bạn lựa chọn serializer và message contract khi publisher hoặc subscriber triển khai phiên bản khác nhau ra sao?
Bạn sử dụng RedisTemplate.convertAndSend để phát thông báo và đánh giá giới hạn của kết quả publish như thế nào?
Bạn giải thích vì sao kết quả publish không chứng minh subscriber đã xử lý message thành công?
Bạn xử lý message được publish khi subscriber mất kết nối hoặc restart như thế nào?
Bạn thiết kế fallback reconciliation khi một Pub/Sub notification làm nhiệm vụ invalidate cache bị bỏ lỡ ra sao?
Bạn đánh giá ảnh hưởng của Pub/Sub fan-out tới bandwidth và memory khi số subscribers tăng nhanh?
Bạn lựa chọn channel naming để cô lập tenant và môi trường mà không lộ dữ liệu qua wildcard subscription ra sao?
Bạn ngăn application nhận thông báo không đáng tin cậy rồi thực hiện side effects đặc quyền như thế nào?
Bạn kiểm soát số lượng subscriptions khi nhiều pods cùng lắng nghe hàng nghìn channels ra sao?
Bạn xử lý subscriber callback blocking làm backlog hoặc chậm tiếp nhận Pub/Sub messages ra sao?
Bạn thiết kế event handler không phụ thuộc thứ tự nhận message giữa nhiều channels như thế nào?
Bạn phân biệt thông báo đổi trạng thái dùng để trigger refresh với sự kiện nghiệp vụ có ID cần deduplication như thế nào?
Bạn kiểm tra failover của Redis làm mất Pub/Sub messages và lập phương án chấp nhận mất thông báo như thế nào?
Bạn dùng reactive pubSub API khi ứng dụng cần subscribe nhưng không chặn thread theo yêu cầu nào?
Bạn kiểm thử subscribe/unsubscribe đúng khi Spring application shutdown hoặc restart như thế nào?
Bạn thiết kế observability đo số messages publish và receive nhưng không nhầm đó là số sự kiện xử lý thành công ra sao?
Bạn giải thích Redis Streams giải quyết hạn chế nào của Pub/Sub trong xử lý message cần lưu lại?
Bạn phân biệt Stream ID với business event ID và idempotency key như thế nào?
Bạn sử dụng StreamOperations.add để ghi event vào stream với field values theo contract nào?
Bạn lựa chọn server-generated stream ID hay ID do ứng dụng cung cấp theo ràng buộc nào?
Bạn đánh giá rủi ro dùng một stream chứa dữ liệu của mọi tenant khi throughput hoặc ACL bị giới hạn ra sao?
Bạn tạo consumer group và xác định vị trí đọc sự kiện cũ hoặc mới khi bắt đầu tiêu thụ như thế nào?
Bạn phân biệt XREAD và XREADGROUP về quản lý consumer progress và Pending Entries List ra sao?
Bạn mô tả vai trò của consumer name và group name khi nhiều instances cùng xử lý một Redis stream như thế nào?
Bạn thiết kế StreamMessageListenerContainer và listener để xử lý messages theo consumer group ra sao?
Bạn phân biệt StreamReceiver hoặc reactive stream consumption với listener container imperative trong Spring Data Redis như thế nào?
Bạn quyết định khi nào acknowledge Stream entry sau database commit theo yêu cầu nào?
Bạn giải thích Pending Entries List lưu những thông tin gì khi consumer nhận nhưng chưa acknowledge một message?
Bạn phát hiện pending messages cũ và consumer không còn sống bằng metrics hoặc XPENDING như thế nào?
Bạn sử dụng XCLAIM hoặc XAUTOCLAIM để chuyển messages chưa hoàn tất sang consumer khác theo điều kiện nào?
Bạn kiểm soát minimum idle time khi claim để tránh hai consumers cùng xử lý một business event như thế nào?
Bạn thiết kế idempotency cho Streams consumer khi message bị redeliver sau worker crash ra sao?
Bạn phân biệt at-least-once processing với exactly-once business side effects khi sử dụng Redis Streams như thế nào?
Bạn xử lý poison message trong Stream khi consumer luôn lỗi trước acknowledgment như thế nào?
Bạn xây dựng dead-letter stream và quy trình replay có audit thay cho retry vô hạn ra sao?
Bạn quản lý consumer retries và backoff mà không làm tắc mọi messages trong cùng group như thế nào?
Bạn xác định khi nào cần nhiều streams hoặc groups để tách event types và tốc độ tiêu thụ ra sao?
Bạn giới hạn stream length qua MAXLEN hoặc trimming policy theo yêu cầu lưu trữ như thế nào?
Bạn đánh giá nguy cơ trimming stream entry vẫn còn trong Pending Entries List trước khi consumer xử lý xong ra sao?
Bạn phân biệt xóa stream entry với acknowledgment của consumer group về hậu quả nào?
Bạn xác định cách khởi tạo consumer group khi stream đã tồn tại hoặc mới được tạo ra sao?
Bạn xử lý lỗi NOGROUP hoặc sai stream key khi ứng dụng khởi động nhiều replicas đồng thời như thế nào?
Bạn thiết kế backpressure cho Streams consumer khi database downstream không theo kịp tốc độ publish ra sao?
Bạn kiểm soát batch size, polling interval và block timeout khi đọc từ Redis Streams như thế nào?
Bạn phân biệt stream size, group lag, pending count và consumer idle time khi giám sát như thế nào?
Bạn thiết kế kế hoạch khôi phục khi consumer group metadata bị xóa nhầm nhưng stream events vẫn còn ra sao?
Bạn xác định cách partition công việc theo nhiều streams trong Redis Cluster để tăng throughput như thế nào?
Bạn so sánh Redis Streams với Kafka về retention, partitioning, replay và operational complexity ra sao?
Bạn kiểm thử consumer group cùng một message được xử lý đúng một worker tại một thời điểm bình thường như thế nào?
Bạn kiểm thử Redis Stream redelivery sau worker crash mà không phát sinh nghiệp vụ trùng như thế nào?
Bạn phân biệt atomicity của một Redis command với transaction MULTI/EXEC gồm nhiều commands như thế nào?
Bạn thiết kế thao tác chuyển tiền không thể dựa riêng vào Redis MULTI/EXEC để bảo đảm transaction với database nguồn như thế nào?
Bạn giải thích Redis MULTI/EXEC thực thi danh sách commands và khác rollback transaction của SQL ra sao?
Bạn xác định lỗi syntax trong queueing so với lỗi runtime trong EXEC ảnh hưởng kết quả transaction như thế nào?
Bạn sử dụng RedisTemplate.execute với SessionCallback cho các thao tác MULTI/EXEC trên cùng connection như thế nào?
Bạn lựa chọn bật transaction support cho RedisTemplate theo phạm vi request hoặc transaction nào?
Bạn xử lý thao tác đọc trong Redis transaction khi kết quả chỉ có sau EXEC như thế nào?
Bạn sử dụng WATCH để triển khai optimistic concurrency cho một key được nhiều workers cập nhật như thế nào?
Bạn kiểm tra transaction bị abort do watched key thay đổi và thiết kế retry budget ra sao?
Bạn giải thích các ràng buộc của WATCH/MULTI/EXEC khi thao tác nhiều keys phân bố ở các hash slots khác nhau ra sao?
Bạn thiết kế Lua script thực hiện cập nhật counter và đặt TTL atomically như thế nào?
Bạn lựa chọn Redis Lua script thay vì nhiều RedisTemplate commands theo yêu cầu atomicity nào?
Bạn xác định các giới hạn về thời gian chạy Lua script để tránh chặn Redis server như thế nào?
Bạn bảo vệ scripts khỏi dữ liệu input không hợp lệ hoặc lệnh thao tác keys ngoài namespace như thế nào?
Bạn phân biệt EVAL, EVALSHA và RedisScript abstraction khi thực thi script từ Spring Data Redis như thế nào?
Bạn quản lý versioning và kiểm thử Lua scripts khi nhiều phiên bản ứng dụng cùng chạy ra sao?
Bạn lựa chọn hash tags để nhiều keys cần atomic operation cùng nằm trên một Redis Cluster slot như thế nào?
Bạn đánh giá rủi ro hash tag quá rộng khiến một slot bị nóng khi gom keys của nhiều người dùng như thế nào?
Bạn triển khai distributed lock bằng SET NX với TTL theo những ràng buộc an toàn nào?
Vì sao distributed lock cần token duy nhất và cơ chế bảo đảm chỉ chủ sở hữu hiện tại được release?
Bạn dùng Lua compare-and-delete để tránh một worker xóa lock đã được worker khác lấy lại ra sao?
Bạn phân tích rủi ro lock TTL hết hạn khi critical section vẫn đang chạy và cách giảm tác động như thế nào?
Bạn phân biệt lock với fencing token khi cần bảo vệ tài nguyên bên ngoài Redis ra sao?
Bạn đánh giá giới hạn của distributed lock Redis trong hệ thống có failover và asynchronous replication như thế nào?
Bạn lựa chọn scheduler idempotency thay vì distributed locking khi workload cho phép theo tiêu chí nào?
Bạn sử dụng pipelining để giảm round trips khi cần gửi nhiều commands độc lập như thế nào?
Bạn phân biệt Redis pipelining với MULTI/EXEC về tính nguyên tử và cách trả kết quả ra sao?
Bạn dùng RedisTemplate.executePipelined để gửi batch operations và deserialize kết quả như thế nào?
Bạn xác định giới hạn kích thước pipeline để tránh tăng memory và network buffers không kiểm soát như thế nào?
Bạn phân biệt tốc độ gửi commands của pipeline với tốc độ Redis server xử lý để dự báo overload như thế nào?
Bạn thiết kế batch update nhiều Redis hashes và xử lý partial failure khi không có transaction chung như thế nào?
Bạn đánh giá chi phí của việc gom thousands of commands vào cùng một pipeline dưới tải cao ra sao?
Bạn chọn Redis MULTI/EXEC, Lua script hay pipelining dựa trên yêu cầu atomicity, latency và throughput nào?
Bạn kiểm tra các RedisTemplate operations hỗ trợ reactive pipeline và transaction theo phiên bản nào?
Bạn thiết kế integration test cho WATCH và Lua nhằm phát hiện race condition giữa hai workers như thế nào?
Bạn giải thích Redis replication hoạt động bất đồng bộ và ảnh hưởng tới dữ liệu vừa ghi như thế nào?
Bạn phân biệt Redis replica để tăng khả năng đọc với replica dùng để failover và những rủi ro staleness ra sao?
Bạn thiết kế đọc từ primary hoặc replica theo yêu cầu read-after-write của ứng dụng như thế nào?
Bạn đánh giá hậu quả failover xảy ra trước khi một write được replicate tới node thay thế như thế nào?
Bạn giải thích Redis Sentinel giám sát và quyết định failover trong mô hình master-replica như thế nào?
Bạn phân biệt Sentinel discovery với Redis Cluster slot discovery khi cấu hình Lettuce client ra sao?
Bạn xác định cấu hình quorum của Sentinel không phải số replica hay số ứng dụng Spring Boot như thế nào?
Bạn kiểm thử ứng dụng tự kết nối tới primary mới sau Sentinel failover bằng phương pháp nào?
Bạn phân tích nguy cơ stale DNS hoặc pooled connections trỏ primary cũ sau failover ra sao?
Bạn xác định chiến lược retry khi Redis trả READONLY vì client tiếp tục ghi vào replica cũ như thế nào?
Bạn giải thích Redis Cluster phân chia 16384 hash slots và định tuyến keys ra sao?
Bạn thiết kế key naming để data distribution giữa cluster nodes tương đối đều như thế nào?
Bạn phân biệt MOVED và ASK redirects khi Redis Cluster migration slot như thế nào?
Bạn kiểm tra Redis client đang dùng cluster topology mới sau khi reshard như thế nào?
Bạn giải thích vì sao multi-key commands yêu cầu keys nằm cùng hash slot trong những trường hợp nhất định?
Bạn lựa chọn hash tag cho nhóm keys liên quan mà vẫn tránh tạo hot slot trong Redis Cluster như thế nào?
Bạn đánh giá khả năng chạy Redis Lua scripts trên multiple slots và giới hạn áp dụng như thế nào?
Bạn thiết kế phân phối Streams theo nhiều keys hoặc slots khi throughput tăng ra sao?
Bạn phân biệt cluster failover với Sentinel failover về cách dữ liệu và địa chỉ được quản lý ra sao?
Bạn kiểm soát split-brain và khả năng mất writes khi Redis Cluster hoặc Sentinel xảy ra network partition như thế nào?
Bạn lựa chọn persistence RDB, AOF hoặc kết hợp tùy theo RPO và workload nào?
Bạn giải thích các giới hạn durability của Redis AOF khi fsync được cấu hình theo chính sách khác nhau như thế nào?
Bạn đánh giá tác động của RDB snapshot lên I/O, memory và thời gian recovery ra sao?
Bạn xác định trường hợp nào dữ liệu cache có thể tái tạo từ nguồn gốc nên không cần Redis persistence?
Bạn thiết kế backup và restore Redis dữ liệu quan trọng trong môi trường có replication như thế nào?
Bạn kiểm tra tính nhất quán của Redis snapshot phục hồi với database nguồn trước khi nhận traffic ra sao?
Bạn kiểm soát maxmemory eviction để không làm mất dữ liệu trong Streams, locks hoặc sessions quan trọng như thế nào?
Bạn theo dõi replication offset và replica lag để đánh giá rủi ro khi failover như thế nào?
Bạn thiết kế multi-region Redis strategy khi ứng dụng cần chạy ở hai địa điểm với latency và consistency constraints nào?
Bạn phân biệt backup, replication và high availability khi đánh giá kế hoạch disaster recovery ra sao?
Bạn kiểm thử Redis Cluster reshard không làm tăng đáng kể lỗi MOVED/ASK ở application như thế nào?
Bạn xác định cách nâng version Redis khi nhiều clients Spring Data khác nhau đang sử dụng như thế nào?
Bạn phân quyền Redis ACL cho service chỉ được thao tác trên key prefixes và commands cần thiết như thế nào?
Bạn thiết kế bảo vệ Redis bằng TLS, private networking và firewall phù hợp môi trường production ra sao?
Bạn đánh giá nguy cơ Redis exposed trên mạng public dù có password như thế nào?
Bạn quản lý Redis usernames, ACL rules và secret rotation mà không làm lộ credentials qua URI hoặc log ra sao?
Bạn tránh đưa PII vào key names, values và Redis command traces theo những quy tắc nào?
Bạn giới hạn quyền thực thi FLUSHALL, CONFIG và các commands quản trị trong tài khoản ứng dụng ra sao?
Bạn xây dựng audit trail khi một operator thay đổi Redis ACL hoặc maxmemory policy như thế nào?
Bạn xác định cách hạn chế Redis client command injection thông qua việc không cho user nhập lệnh thô ra sao?
Bạn phân biệt key-based authorization của Redis ACL với authorization nghiệp vụ cần áp ở Spring service ra sao?
Bạn thiết kế tenant isolation để user không thể đoán ID và đọc dữ liệu Redis của tenant khác như thế nào?
Bạn xử lý secret bị lộ và cần rotate trong lúc nhiều microservices đang kết nối Redis ra sao?
Bạn giới hạn kích thước payload do người dùng cung cấp trước khi serialize và lưu Redis như thế nào?
Bạn đánh giá rủi ro dùng Lua script động được ghép từ dữ liệu không tin cậy ra sao?
Bạn kiểm tra các operations được bật trên Redis managed service trước khi dùng scripts hoặc keyspace notifications như thế nào?
Bạn phân biệt CPU spikes do các commands O(N) với network latency tăng khi phân tích Redis SLOWLOG ra sao?
Bạn giám sát Redis used_memory, memory fragmentation và eviction count để phát hiện pressure như thế nào?
Bạn theo dõi instantaneous ops/sec, command latency và blocked clients để xác định nút thắt ra sao?
Bạn thiết kế dashboard phân biệt Redis cache hit ratio, application cache hit ratio và keyspace hit stats như thế nào?
Bạn sử dụng Micrometer metrics trong Spring Boot để theo dõi Redis client latency và error rate như thế nào?
Bạn tránh metric tag theo raw Redis key hoặc user ID gây high cardinality bằng biện pháp nào?
Bạn xác định khi nào Redis SLOWLOG cho biết server-side latency nhưng không phản ánh toàn bộ network timeout ra sao?
Bạn thiết kế alert khi memory usage tiến gần giới hạn và eviction tăng nhanh như thế nào?
Bạn kiểm tra sự khác biệt giữa Redis server metrics và pending connection pool trong ứng dụng ra sao?
Bạn đánh giá tác động của hot key tới một Redis Cluster slot và node cụ thể như thế nào?
Bạn sử dụng sampling hoặc keyspace scan có giới hạn để tìm hot keys mà không làm quá tải production ra sao?
Bạn kiểm soát rate limiting trên endpoint phụ thuộc Redis để bảo vệ cluster khi traffic đột biến như thế nào?
Bạn thiết kế backoff với jitter và retry budget khi Redis timeout để tránh retry storm như thế nào?
Bạn lựa chọn circuit breaker hoặc bulkhead để Redis outage không làm cạn toàn bộ HTTP threads ra sao?
Bạn đánh giá nguy cơ ứng dụng chuyển toàn bộ traffic xuống database khi Redis cache ngừng hoạt động như thế nào?
Bạn thiết kế degraded mode với stale cache hoặc cache bypass theo từng mức quan trọng của dữ liệu ra sao?
Bạn kiểm tra timeouts và queueing delay có làm p99 latency vượt SLO dù Redis CPU thấp như thế nào?
Bạn thiết kế capacity test với realistic key size và TTL churn thay vì chỉ GET/SET trên key nhỏ ra sao?
Bạn chọn tiêu chí scale up, scale out hoặc điều chỉnh data model khi Redis memory sắp đầy như thế nào?
Bạn kiểm tra ảnh hưởng của RDB snapshot hoặc AOF rewrite tới latency trong giờ cao điểm ra sao?
Bạn thiết kế runbook khôi phục khi Redis memory fragmentation tăng và eviction policy không phù hợp ra sao?
Bạn dùng Testcontainers Redis để kiểm thử RedisTemplate serialization và các operations thực như thế nào?
Bạn kiểm thử StringRedisTemplate và custom RedisTemplate không đọc lẫn key/value sai serializer như thế nào?
Bạn xây dựng integration test cho @RedisHash và @Indexed kiểm tra read/write/query trên Redis thật ra sao?
Bạn kiểm thử @TimeToLive của Redis repository và phản ứng của code khi key vừa hết hạn như thế nào?
Bạn xác minh secondary indexes được cleanup sau expiration trong môi trường đã bật keyspace notifications ra sao?
Bạn mô phỏng keyspace notifications bị tắt để kiểm tra phương án đối soát repository indexes như thế nào?
Bạn kiểm thử @Cacheable, @CachePut và @CacheEvict khi có database update trong Spring context như thế nào?
Bạn phát hiện @Cacheable bị self-invocation bypass bằng integration test nào?
Bạn mô phỏng concurrent cache miss để đo cache stampede và hành vi single-flight như thế nào?
Bạn kiểm tra cache key có chứa tenant ID và quyền truy cập để ngăn cross-tenant data leak như thế nào?
Bạn kiểm thử TTL jitter và expiration behavior mà không dùng Thread.sleep dài gây flaky CI ra sao?
Bạn kiểm thử Redis Hash, Set, ZSet và ListOperations với dữ liệu biên và các giá trị Unicode như thế nào?
Bạn xác minh INCR kèm TTL giữ được atomicity khi hai workers cùng khởi tạo counter ra sao?
Bạn kiểm thử distributed lock chỉ owner token hợp lệ có thể release sau khi lock hết hạn như thế nào?
Bạn mô phỏng lock holder bị pause vượt TTL để thấy giới hạn của Redis lock với resource bên ngoài ra sao?
Bạn kiểm thử RedisTemplate SessionCallback cho WATCH/MULTI/EXEC khi hai clients cập nhật cùng key như thế nào?
Bạn xác minh Lua script atomic update có xử lý retry sau timeout mà không tạo side effect trùng ra sao?
Bạn kiểm thử executePipelined trả về kết quả đúng serializer và thứ tự command ra sao?
Bạn kiểm chứng Pub/Sub subscriber bỏ lỡ message khi đang disconnect để không dùng nó như durable queue như thế nào?
Bạn dùng Testcontainers Redis Streams để kiểm thử consumer group và Pending Entries List ra sao?
Bạn mô phỏng worker crash trước XACK và xác minh XAUTOCLAIM cùng idempotency xử lý lại như thế nào?
Bạn kiểm tra dead-letter stream replay không vô tình làm xử lý lại giao dịch đã hoàn tất ra sao?
Bạn tạo môi trường nhiều Redis nodes để kiểm thử failover và replication lag thay vì chỉ single-node container như thế nào?
Bạn kiểm thử Sentinel failover để xác nhận Spring Data Redis client đổi master mà không restart ứng dụng ra sao?
Bạn kiểm thử Redis Cluster MOVED/ASK và multi-key cross-slot errors trong môi trường nhiều slots như thế nào?
Bạn đánh giá hạn chế Testcontainers Redis standalone khi cần xác thực Sentinel hoặc Cluster behavior ra sao?
Bạn chạy load test cache stampede và hot key để phát hiện bottleneck thực tế trước production ra sao?
Bạn tổ chức CI quality gates gồm serialization compatibility, TTL, consistency và resilience trước nâng Redis client như thế nào?
Nếu RedisTemplate.opsForValue().get không deserialize được dữ liệu sau deployment, bạn sẽ so sánh serializers và schema version ra sao?
Nếu một cache region chứa values do hai phiên bản service ghi khác JSON shape, bạn sẽ tổ chức migration và fallback như thế nào?
Nếu một key có TTL -1 dù được kỳ vọng hết hạn, bạn sẽ kiểm tra SET, EXPIRE và repository behavior ra sao?
Nếu Redis eviction làm mất session nhưng vẫn giữ cache ít quan trọng, bạn sẽ xem lại isolation và eviction policy như thế nào?
Nếu lệnh KEYS pattern làm Redis latency tăng đột biến, bạn sẽ thay bằng scan hoặc thiết kế lại namespace ra sao?
Nếu cache miss đồng loạt khiến database quá tải, bạn sẽ triển khai jitter, single-flight và warm-up như thế nào?
Nếu @CacheEvict đã chạy nhưng API vẫn trả dữ liệu cũ, bạn sẽ kiểm tra cache key, transaction và multi-layer caching ra sao?
Nếu Spring Cache không có tác dụng khi method được gọi nội bộ cùng class, bạn sẽ kiểm tra proxy và self-invocation ra sao?
Nếu repository findByName trả rỗng dù @RedisHash entity tồn tại, bạn sẽ kiểm tra @Indexed và index sets như thế nào?
Nếu Redis key hết hạn nhưng repository secondary index vẫn còn, bạn sẽ điều tra keyspace notifications và cleanup ra sao?
Nếu INCR hoàn tất nhưng EXPIRE chưa chạy khiến rate-limit key tồn tại vô hạn, bạn sẽ thiết kế Lua atomic operation ra sao?
Nếu leaderboard thứ hạng sai sau khi nhiều events bị giao trùng, bạn sẽ xem lại cách cập nhật ZSet score như thế nào?
Nếu Pub/Sub báo publish thành công nhưng một pod không nhận thông báo, bạn sẽ giải thích giới hạn giao nhận và xử lý ra sao?
Nếu Redis Streams pending messages tăng nhưng không có new deliveries, bạn sẽ kiểm tra consumer group và claim process ra sao?
Nếu XAUTOCLAIM khiến message được hai workers xử lý gần đồng thời, bạn sẽ bảo vệ business idempotency như thế nào?
Nếu stream trimming xóa records vẫn còn trong PEL, bạn sẽ đánh giá retention policy và recovery ra sao?
Nếu một Redis Lua script chạy quá lâu làm mọi commands khác chậm, bạn sẽ kiểm tra và thiết kế lại script ra sao?
Nếu transaction WATCH liên tục abort do hot key, bạn sẽ phân tích contention và chọn giải pháp thay thế như thế nào?
Nếu pipeline gửi hàng chục nghìn commands làm client tăng memory, bạn sẽ chia batch và hạn chế concurrency ra sao?
Nếu Sentinel failover khiến ứng dụng tiếp tục gửi writes tới replica cũ, bạn sẽ kiểm tra topology và reconnect ra sao?
Nếu Redis Cluster báo CROSSSLOT cho thao tác nhiều keys, bạn sẽ thiết kế hash tags và cân bằng slot như thế nào?
Nếu một Redis Cluster slot bị nóng dù cluster còn dư CPU, bạn sẽ kiểm tra key distribution và access patterns ra sao?
Nếu một write thành công trước failover nhưng mất sau khi primary đổi, bạn sẽ phân tích replication lag và durability ra sao?
Nếu AOF rewrite làm latency tăng và disk IO bão hòa, bạn sẽ điều chỉnh lịch vận hành và capacity như thế nào?
Nếu Redis báo OOM trong khi eviction count vẫn bằng không, bạn sẽ kiểm tra maxmemory-policy và loại dữ liệu như thế nào?
Nếu Spring WebFlux bị nghẽn do Redis access, bạn sẽ kiểm tra blocking RedisTemplate và reactive pipeline ra sao?
Nếu Redis credentials bị rotate nhưng connection pool giữ xác thực cũ, bạn sẽ tái tạo connections an toàn như thế nào?
Nếu Redis Pub/Sub notification chứa tenant metadata giả, bạn sẽ bảo vệ authorization và không tin payload ra sao?
Nếu ứng dụng phải tạm hoạt động không có Redis, bạn sẽ phân loại chức năng fail-open và fail-closed theo rủi ro nào?
Bạn xây dựng runbook khi Redis Cluster vừa failover, cache miss tăng, Streams backlog tồn đọng và application retry storm như thế nào?
