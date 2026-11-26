Câu 1. Ứng dụng đã có CacheManager; `@EnableCaching` trên cấu hình Spring có vai trò gì?
A. Tự chọn TTL cố định cho entry ở các cache provider.
B. Ép mọi method của ứng dụng thực thi ở chế độ async.
C. Tạo Redis server mới để lưu cache cho toàn bộ bean.
D. Bật interceptor cache cho method được gọi qua Spring proxy.
Đáp án đúng: D

Câu 2. Method gắn `@Cacheable("products")` được gọi với key đã có trong cache; điều gì xảy ra?
A. Trả dữ liệu đã lưu mà không gọi method mục tiêu.
B. Xóa entry hiện có rồi mới cho method thực thi.
C. Chạy method rồi ghi đè cache bằng kết quả mới.
D. Gọi method để kiểm tra thay đổi trước khi trả cache.
Đáp án đúng: A

Câu 3. Khi `@Cacheable` không tìm thấy key và method chạy thành công, hành vi thường là gì?
A. Chạy method rồi lưu result vào cache nếu đủ điều kiện.
B. Trả null rồi đợi lần gọi sau mới tải dữ liệu.
C. Thử đọc lần nữa rồi xóa toàn bộ cache của service.
D. Đẩy kết quả vào cache khác dù chưa cấu hình cache name.
Đáp án đúng: A

Câu 4. Khác biệt chính của `@CachePut` so với `@Cacheable` là gì?
A. `@CachePut` chỉ xóa entry theo key sau khi method chạy.
B. `@CachePut` lấy cached value rồi bỏ qua method gốc.
C. `@CachePut` chỉ chạy method khi cache miss xảy ra.
D. Gọi method bất kể cache hit, rồi ghi result vào cache.
Đáp án đúng: D

Câu 5. Mặc định, `@CacheEvict` xóa entry vào thời điểm nào?
A. Sau khi method chạy thành công theo cấu hình mặc định.
B. Sau khi ứng dụng restart và CacheManager tái tạo.
C. Trước lúc method chạy dù lời gọi kết thúc bằng exception.
D. Trước khi transaction DB mở, dù method chưa được gọi.
Đáp án đúng: A

Câu 6. Với `@CacheEvict(cacheNames="products", allEntries=true)`, tác động chủ yếu là gì?
A. Xóa toàn bộ entry thuộc cache `products` được chọn.
B. Xóa mọi cache name mà CacheManager quản lý.
C. Xóa các bản ghi product trực tiếp trong database.
D. Xóa entry theo các tham số method được dùng khi gọi.
Đáp án đúng: A

Câu 7. Khi một method cần thực hiện nhiều thao tác cache annotation cùng lúc, nên dùng gì?
A. Đặt hai `@EnableCaching` trên cùng một method.
B. Nhóm nhiều annotation cache qua `@Caching`.
C. Dùng `@CacheConfig` để thay các thao tác runtime.
D. Dùng `@Order` để tự phát sinh thao tác cache thứ hai.
Đáp án đúng: B

Câu 8. `@CacheConfig(cacheNames="books")` ở cấp class chủ yếu mang ý nghĩa gì?
A. Tự tạo cache phân tán trong Redis khi ứng dụng chạy.
B. Xóa toàn bộ cache books trước mỗi lời gọi method.
C. Cung cấp cache name mặc định cho annotation trong class.
D. Tự làm mọi method có cache dù không gắn annotation.
Đáp án đúng: C

Câu 9. Trong Spring cache abstraction, `CacheManager` cung cấp chức năng nào?
A. Quyết định HTTP status trả cho request cache hit.
B. Xác định version mới nhất của một entity trong DB.
C. Điều phối transaction DB giữa các repository call.
D. Tra cứu các cache có tên để interceptor sử dụng.
Đáp án đúng: D

Câu 10. Ứng dụng có hai CacheManager; muốn chọn bean `fastCacheManager` cho một method, dùng gì?
A. Đặt `condition="fastCacheManager"` trên annotation cache.
B. Đặt `keyGenerator="fastCacheManager"` trên annotation cache.
C. Chọn `cacheManager="fastCacheManager"` trên annotation.
D. Đặt `unless="fastCacheManager"` trên annotation cache.
Đáp án đúng: C

Câu 11. Muốn chọn cache theo tenant hoặc tham số tại thời điểm gọi method, thành phần nào phù hợp?
A. Triển khai `CacheErrorHandler` để thay cache đích.
B. Dùng `CacheResolver` chọn cache theo ngữ cảnh lời gọi.
C. Triển khai `CacheManager` để đổi đối số của method.
D. Triển khai `KeyGenerator` để đổi danh sách cache name.
Đáp án đúng: B

Câu 12. Với `@Cacheable(key="#p0")`, khóa cache được tính từ đâu?
A. Từ kết quả method sau khi đã thực thi.
B. Đối số đầu tiên của lời gọi method được dùng làm key.
C. Từ tên class có khai báo method cache.
D. Từ tên của bean cung cấp CacheManager.
Đáp án đúng: B

Câu 13. `SimpleKeyGenerator` mặc định tạo key nào cho method không có tham số?
A. Dùng UUID ngẫu nhiên để mỗi lượt gọi có một key.
B. Dùng giá trị `null` rồi nhờ cache provider đổi khóa.
C. Dùng `SimpleKey.EMPTY` làm khóa cho lời gọi đó.
D. Dùng tên method dưới dạng String trong mọi trường hợp.
Đáp án đúng: C

Câu 14. Khi method có đúng một tham số khác null, key mặc định thường là gì?
A. Một `SimpleKey` chứa cả tên class và tên method.
B. Dùng trực tiếp đối số đó làm key mặc định của method.
C. Một chuỗi gồm tên cache nối với vị trí đối số.
D. Một UUID mới được sinh bởi `SimpleKeyGenerator`.
Đáp án đúng: B

Câu 15. Với method có hai tham số, key mặc định của `SimpleKeyGenerator` là gì?
A. Chỉ đối số cuối cùng vì nó quyết định lời gọi.
B. Chỉ đối số đầu tiên do nó là partition key.
C. Một chuỗi tên method và số lượng đối số hiện tại.
D. Đối tượng `SimpleKey` được tạo từ cả hai đối số.
Đáp án đúng: D

Câu 16. Cache kết quả `getPrice(tenantId, productId)` cho nhiều tenant; thiết kế key nào tốt hơn?
A. Dùng key theo `productId` rồi phân quyền ở controller.
B. Dùng key theo `tenantId` và bỏ ID của sản phẩm.
C. Dùng key gồm cả `tenantId` và `productId` để cách ly.
D. Dùng key theo timestamp để tránh sử dụng lại kết quả.
Đáp án đúng: C

Câu 17. Với `@Cacheable(condition="#p0 > 0")`, biểu thức `condition` được xét lúc nào?
A. Kiểm tra trước method để quyết định tương tác với cache.
B. Sau khi trả result để xác định có cache null không.
C. Sau khi transaction commit để bắt đầu tải lại entry.
D. Sau khi CacheManager bị đóng để quyết định ghi cache.
Đáp án đúng: A

Câu 18. `@Cacheable(unless="#result == null")` có tác dụng gì?
A. Không gọi method nếu dữ liệu được cache là null.
B. Không lưu cache khi kết quả method trả về null.
C. Ngăn cache hit khi các tham số là null.
D. Chỉ chạy method khi key truyền vào là null.
Đáp án đúng: B

Câu 19. `@Cacheable(sync=true)` với provider hỗ trợ đồng bộ tải cache hướng tới mục tiêu nào?
A. Đồng bộ nội dung cache giữa mọi JVM trong cluster.
B. Giảm việc nhiều thread cùng tính một key bị miss.
C. Đặt cùng TTL cho các instance của cache provider.
D. Đảm bảo mọi cache operation tham gia DB transaction.
Đáp án đúng: B

Câu 20. Bean gọi `this.findBook(id)` trong cùng class, trong đó `findBook` gắn `@Cacheable`; vấn đề gì?
A. Spring luôn tạo key khác do lần gọi bắt đầu từ `this`.
B. Redis bỏ qua dữ liệu cache khi method được gọi nội bộ.
C. CacheManager tự đổi cache name cho method được gọi.
D. Lời gọi nội bộ bỏ qua proxy nên caching advice không chạy.
Đáp án đúng: D

Câu 21. Với Spring AOP proxy mode, vì sao `@Cacheable` trên private method thường không có hiệu lực?
A. Method private không thể có giá trị trả về để cache.
B. KeyGenerator chỉ hỗ trợ tham số của public static method.
C. Proxy không intercept được lời gọi private method như mong muốn.
D. CacheManager mặc định bỏ qua cache có tên từ method private.
Đáp án đúng: C

Câu 22. Khi dùng `ConcurrentMapCacheManager` trong nhiều replica, giới hạn nào cần nhớ?
A. Cache ghi trực tiếp vào Redis nên replica thấy chung dữ liệu.
B. Cache lưu trong bộ nhớ từng JVM và không chia sẻ entry.
C. Cache yêu cầu mọi replica chạy cùng một transaction manager.
D. Cache phân phối key bằng consistent hashing giữa các JVM.
Đáp án đúng: B

Câu 23. Cache Caffeine trong ứng dụng Spring phù hợp nhất với đặc điểm nào?
A. Cache đọc từ Pub/Sub như một hệ lưu trữ bền vững.
B. Cache lưu ở database chính và đọc bằng Spring Data JPA.
C. Cache phân tán qua mạng với transaction ACID đa node.
D. Cache trong JVM có thể cấu hình giới hạn size và TTL.
Đáp án đúng: D

Câu 24. Dùng Redis với `RedisCacheManager` thay cache local có lợi ích nào đáng chú ý?
A. Annotation cache tự áp khóa phân tán cho mọi lần gọi method.
B. Cache manager tự thay transaction DB khi ghi dữ liệu cache.
C. Mỗi instance được tạo Redis primary riêng hoàn toàn biệt lập.
D. Nhiều instance có thể dùng chung cache từ Redis backend.
Đáp án đúng: D

Câu 25. Muốn đặt TTL cho entry Spring Cache dùng Caffeine, cấu hình nên đặt ở đâu?
A. Ở Caffeine cache builder hoặc cấu hình cache provider.
B. Trong thuộc tính `condition` để xóa entry sau mỗi lần gọi.
C. Trong thuộc tính `key` của annotation `@Cacheable`.
D. Trong `@EnableCaching` để cấu hình TTL chung mọi provider.
Đáp án đúng: A

Câu 26. Khi sửa sản phẩm trong DB, vì sao thường đặt `@CacheEvict` cho key sản phẩm đó?
A. Để lần đọc tiếp theo không lấy bản cũ từ cache.
B. Để sản phẩm tự được index vào Elasticsearch sau update.
C. Để cache hit trong quá khứ được ghi ngược trở lại DB.
D. Để transaction DB được commit trước mọi câu SQL khác.
Đáp án đúng: A

Câu 27. Method cập nhật sản phẩm trả entity mới; muốn ghi ngay kết quả vào cache, lựa chọn nào phù hợp?
A. Dùng `@CacheConfig` để tự ghi result mà không cần annotation.
B. Dùng `@Cacheable` và để method không thực thi nếu cache có.
C. Dùng `@CachePut` với cache name và key thống nhất cách đọc.
D. Dùng `@CacheEvict(allEntries=true)` để thay kết quả cần cache.
Đáp án đúng: C

Câu 28. Trong method có `@Transactional` và thao tác Redis Cache, cần lưu ý điều gì?
A. Spring mặc định dùng transaction XA cho DB và Redis cache.
B. Cache eviction tự rollback khi transaction DB lỗi ở commit.
C. RedisCacheManager đảm bảo mọi thay đổi DB và cache cùng ACID.
D. Transaction DB không tự làm thao tác cache commit nguyên tử.
Đáp án đúng: D

Câu 29. Để tránh xóa cache trước khi transaction DB thực sự commit, giải pháp nào phù hợp?
A. Tăng TTL của cache để tự chờ database transaction kết thúc.
B. Dùng `beforeInvocation=true` để eviction chạy trước lời gọi.
C. Hoãn eviction đến after-commit hoặc dùng cache transaction-aware.
D. Chuyển mọi cache key thành UUID mới để tránh transaction lỗi.
Đáp án đúng: C

Câu 30. Một hệ thống khác sửa DB mà không đi qua service có `@CacheEvict`; rủi ro nào có thể xảy ra?
A. KeyGenerator tự so sánh row version trước mỗi cache hit.
B. Spring tự dò table thay đổi và xóa key tương ứng.
C. Cache giữ kết quả cũ đến khi bị invalidate hoặc hết hạn.
D. Cache tự nhận DB commit qua Spring proxy của ứng dụng khác.
Đáp án đúng: C

Câu 31. Muốn kiểm thử `@Cacheable` thực sự bỏ qua backend khi cache hit, cách nào phù hợp?
A. Chỉ unit test KeyGenerator mà không thực thi method cache.
B. Gọi bean qua Spring proxy hai lần cùng key và kiểm số lượt tải.
C. Chỉ mock CacheManager rồi kết luận interceptor đã hoạt động.
D. Gọi `this.method()` hai lần để kiểm cache advice của proxy.
Đáp án đúng: B

Câu 32. Khi cache hit rate giảm và độ trễ tăng, nhóm chỉ số nào hữu ích để tìm nguyên nhân?
A. Theo dõi hit/miss, eviction, load time và lỗi cache backend.
B. Quan sát số migration và tên các cột mới của database.
C. Quan sát số controller và tốc độ Maven compile của ứng dụng.
D. Quan sát số bean `@Component` mà không đo cache access.
Đáp án đúng: A
