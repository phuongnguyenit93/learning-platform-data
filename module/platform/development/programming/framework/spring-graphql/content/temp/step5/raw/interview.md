Bạn giải thích Spring for GraphQL cung cấp các thành phần nào để triển khai GraphQL API trên nền Spring Framework?
Bạn phân biệt trách nhiệm của Spring for GraphQL và graphql-java trong quá trình tiếp nhận và thực thi một request như thế nào?
Bạn sẽ lựa chọn GraphQL API thay vì REST trong một ứng dụng Spring theo đặc điểm dữ liệu và nhu cầu client nào?
Bạn mô tả đường đi của một GraphQL query từ HTTP endpoint tới data fetcher và database trong ứng dụng Spring Boot ra sao?
Bạn phân biệt schema-first development bằng GraphQL SDL với việc chỉ xuất các Java DTO từ code như thế nào?
Bạn sẽ xác định ranh giới giữa GraphQL schema public và domain model nội bộ của service ra sao?
Bạn phân tích rủi ro trả trực tiếp entity JPA hoặc document database qua GraphQL schema như thế nào?
Bạn sẽ phân chia các type trong schema để không làm GraphQL clients phụ thuộc vào chi tiết persistence ra sao?
Bạn phân biệt Query, Mutation và Subscription trong schema với các method xử lý tương ứng của Spring như thế nào?
Bạn mô tả cách schema SDL xác định type, field, argument và return type mà GraphQL runtime dùng để kiểm tra request ra sao?
Bạn sẽ thiết kế schema cho truy vấn sản phẩm và người bán có liên kết lồng nhau như thế nào?
Bạn phân biệt object type và input type trong thiết kế payload cho mutation như thế nào?
Bạn sẽ lựa chọn scalar, enum hoặc object type cho một thuộc tính nghiệp vụ theo tiêu chí nào?
Bạn giải thích ý nghĩa của dấu ! khi định nghĩa field non-null trong GraphQL SDL và hệ quả khi data fetcher trả null như thế nào?
Bạn phân biệt [Item], [Item!] và [Item!]! về các vị trí có thể chứa null như thế nào?
Bạn sẽ thiết kế field nullable để biểu diễn dữ liệu chưa có thay vì giả định mọi repository luôn trả kết quả như thế nào?
Bạn phân tích vì sao một resolver trả null vào field non-null có thể làm null lan lên cấp object cha trong GraphQL response ra sao?
Bạn sẽ lựa chọn custom scalar cho UUID, ngày giờ hoặc số tiền theo yêu cầu chuẩn hóa nào?
Bạn mô tả cách đăng ký GraphQLScalarType vào runtime wiring của Spring khi schema khai báo custom scalar như thế nào?
Bạn sẽ kiểm thử serialize và parse custom scalar với các giá trị hợp lệ và không hợp lệ ra sao?
Bạn phân biệt interface và union trong schema SDL khi một field có thể trả nhiều loại object như thế nào?
Bạn sẽ xử lý xác định concrete GraphQL type cho một interface hoặc union khi Java object được trả về như thế nào?
Bạn phân tích tradeoff giữa schema có nhiều type cụ thể và schema dùng một JSON scalar mở cho mọi payload như thế nào?
Bạn sẽ thiết kế pagination types hoặc connection-style schema để client lấy dữ liệu theo từng trang ra sao?
Bạn phân biệt cursor pagination với offset pagination khi danh sách có thay đổi liên tục như thế nào?
Bạn sẽ xác định cách đặt tên field và mutation để GraphQL schema dễ mở rộng mà không gây breaking change ra sao?
Bạn mô tả việc đánh dấu một field deprecated trong SDL giúp triển khai migration cho clients như thế nào?
Bạn sẽ tổ chức lộ trình thay thế field deprecated khi nhiều ứng dụng client được cập nhật ở tốc độ khác nhau ra sao?
Bạn phân tích rủi ro đổi field từ nullable sang non-null trong một schema đang được nhiều clients sử dụng như thế nào?
Bạn sẽ đánh giá tác động khi xóa enum value hoặc thay kiểu argument của một query đang public ra sao?
Bạn mô tả cơ chế fragments giúp client tái sử dụng selections và ảnh hưởng tới dữ liệu server cần fetch như thế nào?
Bạn phân biệt GraphQL variables với việc nối trực tiếp giá trị user vào query string về khả năng kiểm thử và an toàn ra sao?
Bạn sẽ thiết kế default argument trong SDL mà không che giấu những tham số bắt buộc của nghiệp vụ như thế nào?
Bạn phân tích vì sao GraphQL aliases có thể làm cùng một field được gọi nhiều lần với các arguments khác nhau trong một request ra sao?
Bạn sẽ xác định khi nào client overfetching vẫn xảy ra dù dùng GraphQL vì thiết kế resolver không xét selection set như thế nào?
Bạn phân biệt GraphQL introspection dùng khám phá schema với chính sách phân quyền dữ liệu runtime như thế nào?
Bạn sẽ tạo schema documentation cho các field có điều kiện quyền truy cập theo nguyên tắc nào?
Bạn đánh giá sự khác nhau giữa validation của GraphQL type system và validation nghiệp vụ trong Spring service như thế nào?
Bạn giải thích Spring Boot starter dành cho GraphQL hỗ trợ cấu hình schema và runtime execution như thế nào?
Bạn mô tả cách Spring nạp các tệp schema.graphqls từ classpath khi ApplicationContext khởi động ra sao?
Bạn sẽ tổ chức nhiều tệp SDL theo bounded context để schema vẫn kết hợp thành một API nhất quán như thế nào?
Bạn phân tích nguyên nhân ứng dụng không khởi động khi schema có type bị khai báo xung đột giữa các tệp như thế nào?
Bạn sẽ xác định cách Spring GraphQL phát hiện @Controller beans chứa các phương thức mapping vào schema ra sao?
Bạn phân biệt GraphQlSource với GraphQlService về nhiệm vụ tạo schema và thực thi request như thế nào?
Bạn mô tả vai trò của ExecutionGraphQlService khi yêu cầu GraphQL được xử lý qua graphql-java ra sao?
Bạn sẽ dùng RuntimeWiringConfigurer để đăng ký scalar, resolver đặc biệt hoặc type resolver theo những trường hợp nào?
Bạn phân biệt annotated controller methods với data fetcher đăng ký trực tiếp qua RuntimeWiringConfigurer theo mức coupling như thế nào?
Bạn sẽ kiểm tra một field trong SDL không có custom resolver và kết quả rơi về default property fetcher ra sao?
Bạn phân tích nguy cơ default property fetching làm truy cập getter gây database query ngoài ý muốn như thế nào?
Bạn sẽ lựa chọn dùng @SchemaMapping thay vì custom graphql-java DataFetcher cho một field theo điều kiện nào?
Bạn mô tả các vai trò của WebGraphQlHandler và WebGraphQlInterceptor khi phục vụ GraphQL qua HTTP hoặc WebSocket ra sao?
Bạn sẽ thiết kế một WebGraphQlInterceptor bổ sung correlation ID hoặc context mà không sửa trực tiếp business query như thế nào?
Bạn phân biệt intercept ở lớp HTTP filter với WebGraphQlInterceptor khi cần dữ liệu của GraphQL request ra sao?
Bạn sẽ đưa Principal hoặc tenant context đã xác thực vào GraphQLContext theo cơ chế nào?
Bạn phân tích rủi ro ghi metadata nhạy cảm vào GraphQLContext rồi để data fetcher trả dữ liệu đó cho client như thế nào?
Bạn sẽ xác minh một WebGraphQlInterceptor có chạy trước resolver khi request mang operationName khác nhau ra sao?
Bạn đánh giá khi nào cần cấu hình GraphQL Java Instrumentation để theo dõi execution hoặc giới hạn query như thế nào?
Bạn sẽ sử dụng GraphQlSourceBuilderCustomizer trong Spring Boot khi cần điều chỉnh GraphQL engine theo nguyên tắc nào?
Bạn phân biệt cấu hình GraphQL transport endpoint với cấu hình GraphQL schema khi triển khai Spring Boot ra sao?
Bạn sẽ xác định cách bảo vệ endpoint GraphQL HTTP và endpoint WebSocket subscriptions bằng các chính sách riêng như thế nào?
Bạn mô tả tác động của GraphQL request gồm query, variables và operationName lên cách Spring thực thi như thế nào?
Bạn sẽ chẩn đoán lỗi operationName không khớp khi một document chứa nhiều operations như thế nào?
Bạn phân tích khi nào nên bật GraphiQL trong môi trường phát triển nhưng hạn chế truy cập ở production ra sao?
Bạn sẽ thiết kế logging cho GraphQL request không ghi raw query hoặc variables chứa PII vào mọi log như thế nào?
Bạn phân biệt GraphQL HTTP status với trường errors trong response khi báo lỗi parse, validation hoặc data fetching ra sao?
Bạn sẽ cấu hình application cho phép health checks mà không dùng một truy vấn GraphQL nặng ra sao?
Bạn đánh giá rủi ro cấu hình schema scanning quá rộng khiến các SDL fragments ngoài dự kiến bị public ra sao?
Bạn sẽ kiểm thử GraphQlSource tạo schema hợp lệ khi thêm một type hoặc custom directive mới như thế nào?
Bạn giải thích @Controller trong Spring for GraphQL được sử dụng cùng @QueryMapping để xử lý field thuộc Query type như thế nào?
Bạn phân biệt @QueryMapping với @SchemaMapping(typeName="Query") về ý nghĩa cấu hình ra sao?
Bạn sẽ tổ chức một @QueryMapping nhận tham số ID rồi gọi service trả DTO như thế nào?
Bạn mô tả cách @Argument ánh xạ GraphQL field argument vào method parameter của controller ra sao?
Bạn sẽ sử dụng @Arguments khi một resolver cần toàn bộ các arguments theo hợp đồng nào?
Bạn phân tích rủi ro một argument thiếu validation khiến service xử lý mã định danh không hợp lệ như thế nào?
Bạn sẽ xử lý trường hợp GraphQL argument không có giá trị mặc định và client bỏ qua nó như thế nào?
Bạn phân biệt GraphQL null argument và argument không được truyền theo ý nghĩa của một mutation update ra sao?
Bạn sẽ thiết kế input object cho mutation cập nhật một phần mà không nhầm trường chưa gửi với trường đặt null như thế nào?
Bạn mô tả @MutationMapping ánh xạ field thuộc Mutation type tới controller như thế nào?
Bạn sẽ thiết kế một mutation tạo đơn hàng trả payload đủ thông tin nhưng không lộ entity persistence ra sao?
Bạn phân biệt mutation cần transaction ở service với resolver chỉ điều phối request theo trách nhiệm như thế nào?
Bạn sẽ xác định cách xử lý validation errors của @Argument DTO trước khi bắt đầu side effects như thế nào?
Bạn phân tích rủi ro một GraphQL mutation có nhiều top-level fields cùng thực thi các side effects không cùng một database transaction như thế nào?
Bạn sẽ thiết kế clientMutationId hoặc idempotency key khi client gửi lại một mutation do timeout ra sao?
Bạn mô tả @SchemaMapping dùng để cung cấp dữ liệu cho field lồng nhau của một GraphQL type như thế nào?
Bạn phân biệt @SchemaMapping(typeName="Order", field="customer") với resolver trực tiếp của Query như thế nào?
Bạn sẽ viết một @SchemaMapping nhận source object như argument để resolve field quan hệ như thế nào?
Bạn phân tích lý do field resolver lồng nhau có thể bị gọi nhiều lần trong cùng một GraphQL request như thế nào?
Bạn sẽ xác định khi nào default PropertyDataFetcher đủ dùng mà không cần khai báo @SchemaMapping như thế nào?
Bạn phân biệt value lấy từ source object với value cần truy vấn service khác trong một field resolver ra sao?
Bạn sẽ sử dụng DataFetchingEnvironment khi cần xem selection set, arguments hoặc execution context như thế nào?
Bạn mô tả DataFetchingFieldSelectionSet giúp quyết định dữ liệu nào cần truy vấn từ database ra sao?
Bạn sẽ tránh dùng DataFetchingEnvironment để đưa chi tiết GraphQL engine tràn vào domain service như thế nào?
Bạn giải thích vai trò của @ContextValue khi method cần đọc dữ liệu từ GraphQLContext của request như thế nào?
Bạn phân biệt @ContextValue với @LocalContextValue trong việc truyền metadata tới nested field resolvers như thế nào?
Bạn sẽ đưa thông tin tenant đã xác thực vào context mà không tin tenantId do client tự truyền như thế nào?
Bạn sẽ dùng Principal hoặc Authentication trong resolver khi cần xác định caller như thế nào?
Bạn phân tích khi nào trả Optional hoặc null từ query resolver tạo field null trong GraphQL response như thế nào?
Bạn sẽ quyết định khi nào trả Mono hoặc CompletableFuture thay vì một object đồng bộ từ resolver ra sao?
Bạn mô tả cách Spring for GraphQL xử lý Mono hoặc Flux từ controller methods theo loại operation như thế nào?
Bạn sẽ bảo đảm blocking JPA repository call không chạy trực tiếp trên Reactor event loop nếu ứng dụng dùng WebFlux ra sao?
Bạn phân tích giới hạn của việc trả Flux từ Query resolver so với @SubscriptionMapping trả luồng sự kiện như thế nào?
Bạn sẽ kiểm tra source parameter của @SchemaMapping được bind đúng type khi có nhiều GraphQL types dùng field cùng tên như thế nào?
Bạn sẽ thiết kế reusable field resolver cho nhiều schema types mà không tạo controller quá nhiều trách nhiệm ra sao?
Bạn phân tích cách @SchemaMapping có thể trigger thêm query ngay cả khi parent field đã được fetch cùng dữ liệu từ database như thế nào?
Bạn sẽ xây dựng interface giữa resolver và domain service để unit test không cần GraphQL engine như thế nào?
Bạn đánh giá khi nào trả field-level authorization error thay vì loại toàn bộ parent object khỏi kết quả như thế nào?
Bạn giải thích vấn đề N+1 phát sinh thế nào khi @SchemaMapping truy vấn database riêng cho từng source object trong một danh sách?
Bạn sẽ đo số lượt gọi repository khi GraphQL query chọn orders và customer của mỗi order như thế nào?
Bạn mô tả cách DataLoader gom nhiều keys thành một batch load trong một GraphQL request như thế nào?
Bạn phân biệt DataLoader với cache ứng dụng toàn cục về vòng đời và mục tiêu tối ưu như thế nào?
Bạn sẽ sử dụng @BatchMapping để thay thế nhiều @SchemaMapping có thể gây N+1 ra sao?
Bạn phân biệt @BatchMapping và @SchemaMapping theo kiểu source argument và kết quả trả về như thế nào?
Bạn sẽ khai báo @BatchMapping cho một type để nhận danh sách parent objects theo cách nào?
Bạn giải thích vì sao @BatchMapping có thể trả Map<Source, Value> hoặc kết quả có thứ tự theo contract tương ứng như thế nào?
Bạn sẽ xác định điều kiện dùng Map kết quả thay vì List kết quả để tránh gắn nhầm dữ liệu giữa các nguồn ra sao?
Bạn phân tích rủi ro sử dụng equals hoặc hashCode không ổn định của source object làm key Map trong @BatchMapping như thế nào?
Bạn sẽ xử lý các keys không tìm thấy dữ liệu khi trả Map từ @BatchMapping như thế nào?
Bạn sẽ thiết kế batch fetching cho mối quan hệ một-nhiều bằng một SQL IN query hoặc truy vấn tương đương ra sao?
Bạn phân tích ảnh hưởng của một batch gồm nhiều keys tới giới hạn parameter của database như thế nào?
Bạn sẽ giới hạn kích thước batch khi một request chọn hàng nghìn objects cùng lúc như thế nào?
Bạn mô tả vai trò của BatchLoaderRegistry trong việc đăng ký batch loader cho DataLoader như thế nào?
Bạn phân biệt BatchLoaderRegistry với việc tạo DataLoader thủ công tại mỗi resolver như thế nào?
Bạn sẽ dùng DataLoaderRegistry để xác định các loaders có mặt trong một GraphQL execution như thế nào?
Bạn giải thích vì sao DataLoader thường được tạo hoặc đăng ký theo request để tránh rò dữ liệu giữa users ra sao?
Bạn phân tích rủi ro DataLoader cache theo ID mà không xét tenant hoặc authorization context như thế nào?
Bạn sẽ đưa GraphQLContext vào BatchLoader để xác thực quyền trên từng key theo quy tắc nào?
Bạn phân biệt BatchLoader và MappedBatchLoader theo contract về thứ tự và keys không tìm thấy ra sao?
Bạn sẽ chọn MappedBatchLoader khi backend không bảo đảm trả kết quả cùng thứ tự input keys ra sao?
Bạn mô tả DataLoader.load và cơ chế dispatch liên quan đến thời điểm batch thực thi như thế nào?
Bạn sẽ xác định vì sao DataLoader trả CompletionStage nhưng một query không kết thúc do batch chưa được dispatch như thế nào?
Bạn phân tích vì sao tự tạo DataLoader bên ngoài GraphQL execution engine có thể làm mất scheduling đúng của dispatch ra sao?
Bạn sẽ dùng DataLoader trong @SchemaMapping khi cần tối ưu việc lấy dữ liệu theo những entity IDs nào?
Bạn phân biệt @BatchMapping tự đăng ký loader với một @SchemaMapping dùng DataLoader đã đăng ký trong BatchLoaderRegistry ra sao?
Bạn sẽ thiết kế batch loader khi một phần key gây lỗi mà vẫn muốn giữ các kết quả hợp lệ khác như thế nào?
Bạn phân tích cách DataLoader cache cùng key trong một request có thể làm resolver thấy dữ liệu cũ sau mutation ra sao?
Bạn sẽ quyết định khi nào cần clear hoặc prime DataLoader cache để phản ánh dữ liệu mới theo ngữ nghĩa nào?
Bạn đánh giá vì sao không nên dùng DataLoader làm cache cross-request mà không có chính sách invalidation rõ ràng ra sao?
Bạn sẽ kiểm tra DataLoader có thực sự giảm round trips khi query dùng aliases hoặc các nested fragments như thế nào?
Bạn phân tích tác động của depth GraphQL và fan-out dữ liệu tới số batch queries được tạo như thế nào?
Bạn sẽ kết hợp projection và DataLoader để chỉ lấy fields được client yêu cầu theo cách nào?
Bạn đánh giá tình huống một DataLoader gom nhiều keys nhưng lại trả về quá nhiều columns gây overfetching như thế nào?
Bạn sẽ thiết kế metrics cho batch size, loader latency và cache hit theo loader name như thế nào?
Bạn phân tích nguy cơ gắn từng key của DataLoader vào metric labels làm cardinality tăng quá cao như thế nào?
Bạn sẽ viết kiểm thử chứng minh 100 parent objects chỉ kích hoạt số lượt fetch cần thiết thay vì 100 truy vấn riêng như thế nào?
Bạn sẽ kiểm thử @BatchMapping trả đúng child cho từng parent khi database trả kết quả không theo thứ tự như thế nào?
Bạn đánh giá cách sử dụng DataLoader trong reactive execution mà không block hoặc subscribe thủ công như thế nào?
Bạn phân biệt tối ưu N+1 ở GraphQL field layer với tối ưu N+1 của ORM khi data fetcher đã tải entity relationships như thế nào?
Bạn giải thích @SubscriptionMapping ánh xạ GraphQL Subscription field tới publisher trong Spring như thế nào?
Bạn phân biệt @SubscriptionMapping với @QueryMapping và @MutationMapping về vòng đời dữ liệu trả về ra sao?
Bạn sẽ thiết kế một @SubscriptionMapping trả Flux các cập nhật trạng thái đơn hàng cho một người dùng như thế nào?
Bạn phân tích vì sao Subscription đòi hỏi quản lý vòng đời kết nối và subscriber khác với Query thường như thế nào?
Bạn sẽ lựa chọn WebSocket transport cho GraphQL subscriptions trong Spring theo yêu cầu ứng dụng như thế nào?
Bạn mô tả cách WebSocket handler của Spring for GraphQL tham gia xử lý các GraphQL subscription operations ra sao?
Bạn sẽ bảo đảm authentication của một HTTP query và một WebSocket subscription được áp dụng nhất quán như thế nào?
Bạn phân biệt xác thực tại WebSocket handshake hoặc connection init với authorization trên từng subscription field như thế nào?
Bạn sẽ ngăn một user đăng ký subscription theo orderId của user khác bằng cách nào?
Bạn phân tích rủi ro chỉ kiểm tra quyền lúc đăng ký subscription nhưng quyền truy cập bị thu hồi trong lúc stream còn chạy ra sao?
Bạn sẽ thiết kế lọc sự kiện tại subscription theo Principal hoặc tenant đã xác thực như thế nào?
Bạn mô tả cách Reactor Flux có thể kết hợp với sink hoặc event publisher để phân phối domain events tới subscribers ra sao?
Bạn sẽ xác định khi nào dùng multicast sink và chính sách xử lý subscribers chậm như thế nào?
Bạn phân tích tác động của backpressure và client đọc chậm lên memory trong một luồng subscription nhiều sự kiện ra sao?
Bạn sẽ giới hạn số lượng subscriptions và thời lượng cho một WebSocket session ra sao?
Bạn mô tả cách hủy subscription khi client disconnect giúp giải phóng resource ở service và database như thế nào?
Bạn phân biệt Flux bị cancel với Flux kết thúc bình thường trong log và metric như thế nào?
Bạn sẽ xử lý lỗi phát sinh giữa subscription stream mà không gửi thông tin nội bộ nhạy cảm cho client ra sao?
Bạn đánh giá cách hỗ trợ client reconnect và đồng bộ lại các sự kiện đã bỏ lỡ khi Subscription không lưu lịch sử bền vững ra sao?
Bạn sẽ xác định nhu cầu replay từ event store hoặc message broker khi một client offline lâu như thế nào?
Bạn phân tích vì sao GraphQL Subscription không tự bảo đảm exactly-once hoặc durable delivery tới client như thế nào?
Bạn sẽ kiểm thử nhiều clients có subscription filters khác nhau mà không làm lộ events giữa tenants ra sao?
Bạn sẽ áp dụng timeout hoặc keepalive cho WebSocket subscription theo môi trường mạng nào?
Bạn đánh giá khi nào RSocket transport thích hợp cho subscription-style data streams nếu server và clients hỗ trợ ra sao?
Bạn giải thích Spring Security có thể bảo vệ GraphQL field resolvers thay vì chỉ URL /graphql như thế nào?
Bạn phân biệt authentication của GraphQL request ở HTTP filter với authorization thực hiện trong resolver như thế nào?
Bạn sẽ áp dụng @PreAuthorize trên @QueryMapping hoặc service method để kiểm soát trường nhạy cảm ra sao?
Bạn phân tích rủi ro query root đã kiểm tra quyền nhưng nested @SchemaMapping vẫn trả dữ liệu của tenant khác như thế nào?
Bạn sẽ thiết kế kiểm tra ownership cho field customer.billingInfo mà không phụ thuộc vào ID do client truyền như thế nào?
Bạn phân biệt field-level security với object-level security trong GraphQL graph nhiều quan hệ ra sao?
Bạn sẽ lấy Principal hoặc SecurityContext của caller để lọc dữ liệu server-side theo cách nào?
Bạn phân tích nguy cơ dùng ThreadLocal SecurityContext sai khi resolver chạy trên reactive scheduler như thế nào?
Bạn sẽ truyền authentication hoặc tenant context tới DataLoader để mỗi batch chỉ trả dữ liệu được phép ra sao?
Bạn đánh giá rủi ro cùng một DataLoader cache được chia sẻ sai giữa nhiều requests hoặc users như thế nào?
Bạn sẽ quyết định khi nào trả null cho field không được truy cập và khi nào trả một GraphQL authorization error ra sao?
Bạn phân tích hệ quả null propagation nếu field cần chặn truy cập được khai báo non-null trong SDL như thế nào?
Bạn sẽ thiết kế schema không vô tình tiết lộ sự tồn tại của tài nguyên qua khác biệt giữa lỗi và null như thế nào?
Bạn phân biệt hạn chế introspection với thực thi authorization thật trên data fetchers như thế nào?
Bạn sẽ kiểm soát quyền thực hiện mutation cập nhật nhiều resources khi input chứa IDs ngoài tenant như thế nào?
Bạn đánh giá nguy cơ một GraphQL query gắn nhiều aliases để lặp lại resolver tốn tài nguyên ngoài ý muốn ra sao?
Bạn sẽ giới hạn query depth và complexity để ngăn yêu cầu GraphQL chiếm quá nhiều CPU hoặc database connections ra sao?
Bạn phân tích vì sao chỉ giới hạn kích thước HTTP body không đủ ngăn GraphQL query gây tải lớn như thế nào?
Bạn sẽ áp dụng rate limit theo user, tenant hoặc operation type mà không tạo lỗ hổng với aliases ra sao?
Bạn sẽ thiết kế một allowlist hoặc persisted queries cho clients cố định theo điều kiện nào?
Bạn phân tích tradeoff khi tắt introspection ở production về trải nghiệm developer và an ninh ra sao?
Bạn sẽ bảo vệ endpoint GraphQL trước CSRF khi dùng cookie authentication và Mutation requests như thế nào?
Bạn đánh giá rủi ro logging GraphQL variables chứa token hoặc dữ liệu cá nhân như thế nào?
Bạn sẽ thiết kế audit cho mutation có business event ID và caller identity nhưng không ghi PII thô ra sao?
Bạn sẽ giới hạn errors.extensions được gửi tới client để tránh làm lộ stack trace và SQL exception details ra sao?
Bạn giải thích GraphQL response có thể chứa đồng thời data và errors khi một field resolver thất bại như thế nào?
Bạn phân biệt lỗi parse, validation và data fetching theo giai đoạn request GraphQL được xử lý ra sao?
Bạn mô tả vai trò của DataFetcherExceptionResolver trong việc chuyển Java exceptions thành GraphQLError ra sao?
Bạn sẽ sử dụng DataFetcherExceptionResolverAdapter để chuẩn hóa lỗi từ service thành phản hồi GraphQL như thế nào?
Bạn phân biệt ErrorType do Spring for GraphQL cung cấp với exception class cụ thể từ database ra sao?
Bạn sẽ xác định khi nào trả lỗi NOT_FOUND hoặc FORBIDDEN cho một field thay vì một generic internal error ra sao?
Bạn phân tích lý do không nên trả nguyên exception message từ repository cho GraphQL client như thế nào?
Bạn sẽ sử dụng path và locations của GraphQLError để hỗ trợ debug mà không lộ thông tin bí mật ra sao?
Bạn phân biệt errors.extensions với các fields thuộc business payload khi thiết kế contract lỗi của mutation như thế nào?
Bạn sẽ xử lý validation cho input object trước khi chạy business transaction theo quy trình nào?
Bạn phân tích rủi ro một mutation nhận dữ liệu không hợp lệ nhưng đã tạo side effects trước khi exception được xử lý ra sao?
Bạn sẽ định nghĩa transaction boundary trong service xử lý @MutationMapping để bảo đảm commit hoặc rollback như thế nào?
Bạn phân biệt một GraphQL operation gồm nhiều mutation root fields với một database transaction duy nhất theo ngữ nghĩa nào?
Bạn sẽ thiết kế idempotency cho một mutation khi client retry sau network timeout mà commit trước có thể đã thành công ra sao?
Bạn đánh giá nguy cơ mutation có external API call bên trong @Transactional làm giữ database locks quá lâu như thế nào?
Bạn sẽ tổ chức transactional outbox khi mutation phải gửi notification đến WebSocket subscribers sau commit ra sao?
Bạn phân tích khi nào DataFetcherExceptionResolver có thể chuyển lỗi nhưng không thể tự rollback dữ liệu đã commit ra sao?
Bạn sẽ xử lý lỗi từ Mono hoặc CompletionStage resolver bằng cách nào để GraphQL execution nhận được lỗi đúng field?
Bạn sẽ phân biệt @ExceptionHandler ở controller GraphQL với DataFetcherExceptionResolver trong xử lý lỗi theo phiên bản Spring được dùng ra sao?
Bạn sẽ kiểm thử GraphQL null bubbling khi child field non-null ném exception như thế nào?
Bạn đánh giá khi nào GraphQL client nên kiểm tra cả data và errors thay vì chỉ kiểm tra HTTP status ra sao?
Bạn giải thích vì sao GraphQL API vẫn có thể gây N+1, overfetching và expensive queries dù client tự chọn fields như thế nào?
Bạn sẽ sử dụng DataFetchingFieldSelectionSet để thực hiện projection chỉ lấy columns được yêu cầu ra sao?
Bạn phân tích rủi ro selection set phức tạp làm xuất hiện nhiều joins hoặc subqueries tốn kém như thế nào?
Bạn sẽ thiết kế giới hạn nested depth trên server nhưng vẫn cho phép những truy vấn hợp lệ phổ biến ra sao?
Bạn sẽ đo query complexity theo field weight hoặc dự kiến database cost thay vì chỉ đếm số fields như thế nào?
Bạn đánh giá tác động của aliases và fragments tới cách tính chi phí một operation ra sao?
Bạn sẽ đặt giới hạn page size ngay tại resolver để ngăn client yêu cầu quá nhiều records như thế nào?
Bạn phân biệt offset pagination và cursor-based connection cho danh sách thay đổi liên tục theo nhu cầu nào?
Bạn sẽ thiết kế các chỉ số p95 latency theo operationName mà không đưa toàn bộ query text vào metric labels ra sao?
Bạn mô tả vai trò của Micrometer metrics và GraphQL Java instrumentation trong quan sát thời gian execution như thế nào?
Bạn sẽ phân biệt thời gian GraphQL parsing/validation, resolver execution và database calls khi điều tra latency ra sao?
Bạn phân tích nguy cơ logging mỗi nested resolver invocation khiến số lượng log tăng theo kích thước graph như thế nào?
Bạn sẽ sử dụng tracing để tìm field resolver nào tạo nhiều round trips trên một request ra sao?
Bạn sẽ xây dựng dashboard theo query count, DataLoader batch size, execution errors và query complexity như thế nào?
Bạn đánh giá cách giới hạn concurrency của resolver gọi dịch vụ bên ngoài để tránh làm cạn thread pool hoặc connection pool ra sao?
Bạn sẽ xử lý slow external service trong nested resolver để trả dữ liệu một phần theo schema semantics như thế nào?
Bạn phân tích rủi ro cache kết quả GraphQL response khi cache key không chứa user hoặc tenant context như thế nào?
Bạn sẽ xác định trường hợp nào nên cache field result, DataLoader request cache hoặc whole operation response ra sao?
Bạn đánh giá tác động của cache invalidation sau mutation lên dữ liệu mà client nhìn thấy như thế nào?
Bạn sẽ thiết kế persisted queries hoặc allowlisted operations để vừa tăng an toàn vừa kiểm soát cost như thế nào?
Bạn phân tích vì sao bật HTTP compression không giải quyết được N+1 database calls do resolver ra sao?
Bạn sẽ kiểm thử hiệu năng với graph có nhiều levels và high fan-out để dự đoán worst-case execution ra sao?
Bạn phân biệt unit test service nghiệp vụ với integration test GraphQL schema và resolver wiring như thế nào?
Bạn sẽ dùng @GraphQlTest để kiểm tra annotated controllers mà không khởi động toàn bộ ứng dụng theo điều kiện nào?
Bạn mô tả GraphQlTester hỗ trợ gửi document và xác nhận data hoặc errors trong test như thế nào?
Bạn sẽ dùng GraphQlTester.document để kiểm tra một query có variables theo cách nào?
Bạn sẽ kiểm thử GraphQlTester.path trên nested fields thay vì so sánh nguyên JSON response ra sao?
Bạn phân biệt HttpGraphQlTester với GraphQlTester dùng execution trực tiếp về phạm vi kiểm thử như thế nào?
Bạn sẽ dùng @AutoConfigureHttpGraphQlTester khi cần test qua transport HTTP trong ứng dụng Spring Boot ra sao?
Bạn mô tả cách WebSocketGraphQlTester hỗ trợ kiểm thử GraphQL subscriptions như thế nào?
Bạn sẽ dùng StepVerifier để kiểm tra một Subscription Flux phát ra đúng chuỗi events và kết thúc theo điều kiện nào?
Bạn phân tích nguy cơ test subscriptions dựa vào Thread.sleep cố định khiến CI flaky như thế nào?
Bạn sẽ mock domain service và kiểm tra một @QueryMapping chuyển đúng @Argument như thế nào?
Bạn sẽ kiểm thử @MutationMapping gọi business service và ánh xạ payload response đúng schema như thế nào?
Bạn sẽ thiết kế integration test phát hiện field schema không có mapping phù hợp sau khi refactor method names ra sao?
Bạn đánh giá cách kiểm thử @SchemaMapping trả dữ liệu cho field chỉ xuất hiện trong một GraphQL fragment ra sao?
Bạn sẽ test @BatchMapping không phát sinh N+1 bằng cách đếm lượt gọi repository như thế nào?
Bạn phân tích cách kiểm thử DataLoader xử lý đúng dữ liệu khi batch result trả không theo thứ tự input keys ra sao?
Bạn sẽ xác minh DataLoader cache không rò dữ liệu giữa hai GraphQL requests với hai tenant khác nhau như thế nào?
Bạn sẽ kiểm thử scalar parsing với dữ liệu không hợp lệ để chắc chắn lỗi đến trước business service ra sao?
Bạn sẽ xác minh nullability violation của một nested field làm errors chứa path phù hợp như thế nào?
Bạn sẽ tạo test DataFetcherExceptionResolverAdapter để bảo đảm exception nội bộ không lộ stack trace ra sao?
Bạn sẽ thiết kế test @PreAuthorize trên nested @SchemaMapping để người không có quyền không đọc được field nhạy cảm như thế nào?
Bạn đánh giá khi nào cần tích hợp Testcontainers để kiểm chứng DataLoader thực sự giảm số SQL queries ra sao?
Bạn sẽ kiểm thử mutation rollback khi domain service ném exception giữa nhiều bước ghi dữ liệu như thế nào?
Bạn sẽ xác minh idempotent mutation không tạo bản ghi trùng khi cùng request được gửi lặp như thế nào?
Bạn sẽ kiểm tra subscription của user A không nhận event dành cho user B qua WebSocketGraphQlTester ra sao?
Bạn sẽ mô phỏng client cancel subscription và xác nhận publisher giải phóng tài nguyên ra sao?
Bạn sẽ thiết kế load test cho GraphQL operation có nhiều aliases, fragments và nested selections như thế nào?
Bạn sẽ kiểm tra query depth và complexity guard chặn request độc hại nhưng không chặn queries hợp lệ ra sao?
Bạn sẽ kiểm thử persisted query hoặc operation allowlist từ các clients có quyền khác nhau như thế nào?
Bạn sẽ xác minh response chứa cả data và errors khi một resolver thất bại nhưng các fields khác vẫn hợp lệ như thế nào?
Bạn đánh giá checklist production cho schema compatibility, authentication, depth limits, N+1 và observability như thế nào?
Nếu một GraphQL Query trả orders kèm customer và thực hiện hàng trăm SQL queries, bạn sẽ dùng @BatchMapping và DataLoader để cải thiện ra sao?
Nếu @SchemaMapping không chạy cho một field lồng nhau, bạn sẽ kiểm tra SDL typeName, field name và resolver registration như thế nào?
Nếu Query resolver trả đúng object nhưng field non-null bị null và làm biến mất parent data, bạn sẽ điều tra null bubbling ra sao?
Nếu @MutationMapping được retry sau HTTP timeout và tạo hai đơn hàng, bạn sẽ sửa transaction và idempotency như thế nào?
Nếu GraphQL response có HTTP 200 nhưng errors chứa lỗi database, bạn sẽ điều chỉnh client và monitoring như thế nào?
Nếu dữ liệu tenant A xuất hiện trong field nested của tenant B, bạn sẽ kiểm tra DataLoader cache scope và authorization ra sao?
Nếu client dùng nhiều aliases lặp một field đắt đỏ và database quá tải, bạn sẽ thiết kế complexity guard và rate limit ra sao?
Nếu @BatchMapping trả List sai thứ tự khiến order gắn nhầm customer, bạn sẽ thay contract hoặc map keys như thế nào?
Nếu DataLoader được tái sử dụng qua nhiều requests làm người dùng thấy dữ liệu cũ, bạn sẽ sửa scope và cache policy ra sao?
Nếu GraphQL mutation trả lỗi sau khi transaction đã commit, bạn sẽ phân biệt business commit với lỗi fetch các fields trả về như thế nào?
Nếu Subscription qua WebSocket bị ngắt khi client offline, bạn sẽ thiết kế reconnect và replay các cập nhật quan trọng ra sao?
Nếu một subscription gửi dữ liệu riêng tư cho user vừa bị thu hồi quyền, bạn sẽ thiết kế kiểm tra authorization liên tục ra sao?
Nếu DataFetcherExceptionResolver trả nguyên SQL error vào extensions, bạn sẽ chuẩn hóa lỗi và cấu hình logs như thế nào?
Nếu @GraphQlTest PASS nhưng production HTTP transport lỗi xác thực, bạn sẽ bổ sung integration test về interceptor và Spring Security ra sao?
Nếu một custom scalar được khai báo trong SDL nhưng app không khởi động, bạn sẽ kiểm tra RuntimeWiringConfigurer và schema initialization như thế nào?
Nếu selection set sâu khiến resolver gọi REST backend hàng nghìn lần, bạn sẽ kết hợp DataLoader, projection và giới hạn query ra sao?
Nếu GraphQL field-level authorization trả null cho field non-null làm mất cả object, bạn sẽ cân nhắc lại schema và error contract như thế nào?
Nếu GraphQL subscriptions tồn tại sau khi client đã disconnect và làm memory tăng, bạn sẽ kiểm tra cancellation và resource cleanup ra sao?
Nếu nhiều phiên bản client sử dụng SDL fields cũ và mới, bạn sẽ triển khai deprecation và schema compatibility tests ra sao?
Nếu xây dựng GraphQL API Spring mới cho production, bạn sẽ tổ chức SDL, controller mappings, DataLoader, bảo mật, xử lý lỗi, subscription, testing và performance theo những bước nào?
