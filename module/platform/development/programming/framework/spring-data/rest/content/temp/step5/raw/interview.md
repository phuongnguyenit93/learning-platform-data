Bạn giải thích Spring Data REST giải quyết bài toán công bố repository dưới dạng HTTP API như thế nào?
Bạn phân biệt Spring Data REST với @RestController tự viết về trách nhiệm và khả năng tùy biến ra sao?
Bạn xác định loại ứng dụng nào phù hợp với API được sinh trực tiếp từ repository theo tiêu chí nào?
Bạn đánh giá rủi ro khi mô hình persistence vô tình trở thành hợp đồng API công khai như thế nào?
Bạn phân biệt repository abstraction của Spring Data với lớp HTTP resource được Spring Data REST xuất bản ra sao?
Bạn mô tả các bước từ lúc Spring Boot khởi động tới khi repository endpoint xuất hiện như thế nào?
Bạn xác định dependency nào cần thiết để kích hoạt Spring Data REST trong ứng dụng Spring Boot như thế nào?
Bạn đánh giá ảnh hưởng của việc thêm Spring Data REST starter vào ứng dụng đã có nhiều repositories ra sao?
Bạn giải thích nguyên tắc REST resource khác gì việc công bố trực tiếp bảng database như thế nào?
Bạn phân biệt collection resource với item resource của một repository qua đường dẫn và biểu diễn như thế nào?
Bạn lựa chọn đặt tên public resource theo domain concept hay tên Java entity dựa trên mục tiêu nào?
Bạn quyết định có nên expose toàn bộ entity repository hay chỉ tập API được phê duyệt theo yêu cầu nào?
Bạn so sánh mô hình API CRUD sinh tự động với API hướng nghiệp vụ về tốc độ phát triển và quản trị ra sao?
Bạn phân tích sự gắn kết giữa HTTP semantics và các phương thức CRUD do repository hỗ trợ như thế nào?
Bạn phân biệt discoverable API và tài liệu OpenAPI tĩnh về cách client tìm khả năng truy cập ra sao?
Vì sao HAL hyperlinks giúp client giảm phụ thuộc vào các đường dẫn resource bị hardcode?
Bạn đánh giá sự phù hợp của HAL/HATEOAS đối với ứng dụng web, mobile và service-to-service ra sao?
Những hành động nghiệp vụ nào cần endpoint chuyên biệt thay vì chỉ sử dụng CRUD repository tự động?
Bạn thiết kế ranh giới giữa Spring Data REST cho thao tác quản trị và controller riêng cho quy trình nghiệp vụ như thế nào?
Bạn đánh giá tác động của API tự sinh đến versioning, audit và backward compatibility khi entity thay đổi ra sao?
Bạn lựa chọn cách công bố tài nguyên liên quan khi domain gồm order, customer và line items như thế nào?
Bạn thiết kế quy trình review các endpoint được xuất bản trước khi phát hành production ra sao?
Bạn giải thích vai trò của HAL representation trong Spring Data REST theo khái niệm nào?
Bạn phân biệt biểu diễn JSON entity thuần với application/hal+json về thông tin điều hướng ra sao?
Bạn phân tích ý nghĩa của _links, self và các relation names trong một HAL resource như thế nào?
Bạn kiểm tra sự xuất hiện của _embedded trong HAL collection response và thiết kế client parsing phù hợp ra sao?
Bạn thiết kế client follow hyperlink relation thay vì tự nối URL từ entity ID như thế nào?
Bạn đánh giá rủi ro client phụ thuộc vào thứ tự các phần tử trong _links hoặc _embedded ra sao?
Bạn phân biệt URI thực thể với business identifier được trình bày trong JSON như thế nào?
Bạn giải thích vì sao các trường ID persistence có thể không được xuất như thuộc tính thường theo cấu hình mặc định?
Bạn lựa chọn có expose entity IDs trong representation thông qua RepositoryRestConfiguration theo yêu cầu nào?
Bạn thiết kế cách biểu diễn ID ổn định cho external clients khi khóa database thay đổi như thế nào?
Bạn phân biệt href của collection, item và association link trong một HAL response như thế nào?
Bạn xác định khi nào một HAL link biểu diễn quan hệ tới resource khác và khi nào chỉ là thuộc tính JSON?
Bạn thiết kế relation names dễ hiểu và ổn định cho client xuyên nhiều phiên bản API như thế nào?
Bạn kiểm tra self links được tạo chính xác sau khi đổi tên đường dẫn repository như thế nào?
Bạn đánh giá khả năng client xử lý URL có template parameters trong HAL link ra sao?
Bạn phân biệt CURIE hoặc compact relation name với relation URL đầy đủ theo khả năng hỗ trợ nào?
Bạn xác định trường hợp cần mô tả endpoint profile để client hiểu schema và khả năng chỉnh sửa ra sao?
Bạn giải thích cách Spring Data REST công bố metadata hoặc profile để ứng dụng client khám phá tài nguyên như thế nào?
Bạn đánh giá vai trò của ALPS metadata so với JSON Schema hoặc OpenAPI trong môi trường Spring Data REST ra sao?
Bạn thiết kế test kiểm chứng clients không bị hỏng khi thứ tự HAL links thay đổi như thế nào?
Bạn lựa chọn cách phát triển client khi response có thêm relation mới nhưng vẫn giữ relation cũ ra sao?
Bạn kiểm soát mức độ lộ cấu trúc domain qua tên relation và embedded resources như thế nào?
Bạn phân biệt HAL pagination navigation links với các tham số query tùy chọn của resource ra sao?
Bạn xác định cách giải quyết vấn đề proxy hoặc gateway làm HAL links dùng sai scheme hoặc host như thế nào?
Bạn xử lý X-Forwarded headers hoặc Forwarded headers đúng mức tin cậy khi xây self link ra sao?
Bạn đánh giá nguy cơ trust mọi forwarded host header dẫn đến liên kết điều hướng độc hại như thế nào?
Bạn thiết kế khả năng chuyển từ HAL sang representation khác mà hạn chế breaking changes như thế nào?
Bạn xác định giới hạn của HATEOAS khi client cần dữ liệu tổng hợp phức tạp trên nhiều resources ra sao?
Bạn sử dụng @RepositoryRestResource để tùy chỉnh collection path và item resource relation như thế nào?
Bạn phân biệt thuộc tính path với collectionResourceRel của @RepositoryRestResource như thế nào?
Bạn xác định cách tùy chỉnh itemResourceRel để relation name không phụ thuộc Java class như thế nào?
Bạn dùng @RestResource trên repository method để thay đổi path và rel của finder endpoint ra sao?
Bạn xác định trường hợp dùng @RepositoryRestResource(exported=false) để tắt export cả repository như thế nào?
Bạn đánh giá khác biệt giữa tắt export bằng annotation và chặn truy cập qua Spring Security ra sao?
Bạn kiểm soát một phương thức repository cụ thể không được export bằng @RestResource(exported=false) như thế nào?
Bạn xác minh các CRUD methods nào được export theo interface repository đang sử dụng ra sao?
Bạn phân biệt CrudRepository, PagingAndSortingRepository và JpaRepository về các khả năng HTTP có thể xuất hiện theo phiên bản nào?
Bạn kiểm tra exported endpoints thực tế thay vì giả định mọi phương thức repository đều có đường dẫn REST như thế nào?
Bạn cấu hình base path toàn cục cho repository REST endpoints bằng cách nào?
Bạn đánh giá ảnh hưởng của thay base path đối với HAL self links, gateway routes và bookmarks như thế nào?
Bạn tổ chức API prefix để tránh xung đột với controllers đã có trong cùng ứng dụng như thế nào?
Bạn lựa chọn quy ước plural resource path phù hợp với tên miền nghiệp vụ bằng nguyên tắc nào?
Bạn phân biệt tự động export repositories với một whitelist public repositories khi thiết kế security boundary ra sao?
Bạn đánh giá rủi ro tạo repository mới vô tình sinh endpoint chưa được review như thế nào?
Bạn thiết kế cách phát hiện endpoint mới trong CI sau khi thêm một Spring Data repository ra sao?
Bạn lựa chọn @RepositoryRestResource để xuất bản repository hay giữ repository nội bộ dựa trên chính sách API nào?
Bạn quản lý search finder endpoints khi method name thay đổi trong refactoring mà external clients đã sử dụng như thế nào?
Bạn kiểm soát độ ổn định của resource rel và path trong một release có thay entity class name ra sao?
Bạn phân biệt customization qua RepositoryRestConfigurer với annotation ở repository interface về phạm vi tác động như thế nào?
Bạn áp dụng RepositoryRestConfigurer khi muốn cấu hình expose IDs hoặc basePath toàn cục theo chính sách nào?
Bạn quyết định dùng RepositoryRestConfigurer thay controller advice cho nhu cầu tùy biến HTTP nào?
Bạn kiểm tra khả năng thay media type hoặc default page size qua cấu hình theo phiên bản Spring Data REST ra sao?
Bạn quyết định tùy chỉnh Jackson serialization cho entity nhằm đáp ứng hợp đồng API theo những yêu cầu nào?
Bạn đánh giá nguy cơ sửa serializer toàn cục làm ảnh hưởng các controller ngoài Spring Data REST ra sao?
Bạn tổ chức cấu hình ResourceMapping không để domain model phụ thuộc tên public URLs như thế nào?
Bạn phân biệt customization tên JSON property và customization tên HAL relation như thế nào?
Bạn lựa chọn cách ẩn thuộc tính bằng Jackson annotation hay dùng projection theo mức độ nhạy cảm nào?
Vì sao việc ẩn một field khỏi JSON response không đủ để bảo đảm client không thể ghi field đó?
Bạn thiết kế contract review sau khi thay @JsonIgnore hoặc Jackson mixins cho entity như thế nào?
Bạn áp dụng tính năng exposure theo môi trường mà không vô tình bật endpoints quản trị ở production ra sao?
Bạn đánh giá rủi ro sử dụng path dựa trên tên collection entity khi mô hình persistence thay đổi như thế nào?
Bạn kiểm thử đường dẫn và relation của tài nguyên khi base path được định tuyến qua reverse proxy như thế nào?
Bạn mô tả cách Spring Data REST ánh xạ GET collection sang lời gọi repository ra sao?
Bạn phân biệt GET item resource với GET collection resource về kết quả và mã HTTP như thế nào?
Bạn thiết kế hành vi khi GET một ID không tồn tại để không tiết lộ bản ghi thuộc tenant khác ra sao?
Bạn đánh giá cách POST tới collection resource tạo entity và trả Location header như thế nào?
Bạn phân biệt POST tạo resource với PUT thay thế resource theo HTTP semantics ra sao?
Bạn giải thích sự khác nhau giữa PUT và PATCH khi client cập nhật một phần document như thế nào?
Bạn xác định các content types hỗ trợ bởi PATCH theo phiên bản Spring Data REST thực tế bằng cách nào?
Bạn kiểm tra thao tác cập nhật null hoặc field thiếu trong JSON có khác nhau giữa PUT và PATCH như thế nào?
Bạn đánh giá nguy cơ client gửi full entity snapshot cũ qua PUT làm ghi đè cập nhật từ người khác như thế nào?
Bạn thiết kế thao tác DELETE item resource và xử lý repeated DELETE theo idempotency semantics ra sao?
Bạn phân biệt trạng thái HTTP của tạo thành công, cập nhật thành công và xóa thành công theo hợp đồng nào?
Bạn xác định cách kiểm tra HTTP status 400, 404, 405 và 409 được sinh trong các trường hợp lỗi khác nhau như thế nào?
Bạn thiết kế kiểm thử Allow header hoặc lỗi Method Not Allowed khi repository không cho thao tác ghi ra sao?
Bạn phân biệt response body rỗng và HAL resource body sau một request mutation theo cấu hình nào?
Bạn đánh giá rủi ro cho phép mass assignment của các trường giá, vai trò hoặc owner qua generic CRUD endpoint như thế nào?
Bạn thiết kế service-level business invariants khi API được expose trực tiếp từ repository như thế nào?
Bạn xác định bước nào cần kiểm tra tenant ownership trước khi repository save hoặc delete ra sao?
Bạn phân biệt validation của dữ liệu nhập với authorization để thực hiện CRUD operation như thế nào?
Vì sao một entity persistence event không đương nhiên thể hiện domain command đã được kiểm soát?
Bạn lựa chọn controller chuyên biệt khi thao tác cần nhiều bước và side effects vượt khỏi CRUD như thế nào?
Bạn đánh giá khả năng hỗ trợ optimistic locking qua @Version và HTTP conditional requests theo phiên bản nào?
Bạn thiết kế xử lý concurrent PATCH requests để không xảy ra lost update trong tài nguyên quan trọng như thế nào?
Bạn phân biệt ETag HTTP với JPA @Version và quy tắc đối chiếu If-Match theo hợp đồng nào?
Bạn lựa chọn hỗ trợ If-None-Match cho GET resource dựa trên chính sách cache và yêu cầu độ mới dữ liệu nào?
Bạn kiểm tra HTTP caching headers không làm lộ dữ liệu stale sau thay đổi quyền truy cập như thế nào?
Bạn thiết kế response lỗi nhất quán khi database unique constraint bị vi phạm qua repository endpoint như thế nào?
Bạn phân biệt lỗi validation được phát hiện trước save với lỗi database constraints tại thời điểm commit ra sao?
Bạn kiểm soát stacktrace và tên bảng hoặc cột database không xuất hiện trong HTTP error body như thế nào?
Bạn xác định ranh giới transaction của một HTTP CRUD request do Spring Data REST xử lý ra sao?
Bạn đánh giá rủi ro lazy loading hoặc Open Session In View khi serialization HAL cần đọc association ra sao?
Bạn thiết kế fallback khi database tạm lỗi nhưng REST resource endpoint vẫn cần trả thông tin lỗi rõ ràng như thế nào?
Bạn phân biệt association link trong HAL với thuộc tính foreign key trong JSON representation như thế nào?
Bạn giải thích cách Spring Data REST công bố association resources cho quan hệ giữa entities ra sao?
Bạn xác định khi nào một quan hệ nên được trình bày dưới dạng link thay vì nhúng object đầy đủ?
Bạn thiết kế API cho Order và Customer để client follow association link mà không hardcode customer ID như thế nào?
Bạn phân biệt to-one relationship với to-many relationship về endpoint và cách cập nhật links ra sao?
Bạn kiểm tra Content-Type text/uri-list cho các thao tác quản lý association theo hợp đồng của Spring Data REST như thế nào?
Bạn xác định cách liên kết một resource đã tồn tại vào association endpoint qua HTTP method phù hợp ra sao?
Bạn đánh giá ảnh hưởng của việc thay toàn bộ tập association so với thêm một phần tử mới như thế nào?
Bạn thiết kế cập nhật quan hệ many-to-many có kiểm tra quyền của cả hai phía như thế nào?
Bạn kiểm tra association URL do client gửi thuộc domain và base path được phép ra sao?
Bạn ngăn client tạo liên kết giữa entities của hai tenants khác nhau bằng kiểm soát nào?
Bạn phân biệt xóa link tới entity với xóa hẳn target entity trong thao tác HTTP ra sao?
Bạn kiểm tra hành vi khi một liên kết trỏ đến resource không tồn tại hoặc đã bị xóa ra sao?
Bạn giải thích ảnh hưởng của JPA cascade delete hoặc orphanRemoval tới thao tác xóa resource như thế nào?
Bạn lựa chọn expose associations nào và ẩn associations nào theo quy tắc nghiệp vụ nào?
Bạn xử lý vòng tham chiếu giữa các entities để HAL serialization không đệ quy vô hạn như thế nào?
Bạn phân biệt xử lý bidirectional JPA relationships với biểu diễn HAL links như thế nào?
Bạn kiểm tra N+1 queries phát sinh khi xuất collection tài nguyên có associations ra sao?
Bạn lựa chọn fetch plan, projections hoặc query optimization để giảm số truy vấn khi sinh HAL response như thế nào?
Bạn đánh giá tác động của association lớn tới số lượng links và payload size như thế nào?
Bạn thiết kế pagination riêng cho tập association rất lớn khi cơ chế được hỗ trợ theo phiên bản nào?
Bạn xử lý cập nhật association khi cả parent và target có optimistic version nhằm tránh lost update như thế nào?
Bạn lựa chọn service endpoint riêng thay cho association mutation tự động khi có ràng buộc nghiệp vụ phức tạp như thế nào?
Bạn kiểm thử client không thay đổi association ownership chỉ bằng cách gửi một URI ngoài phạm vi như thế nào?
Bạn giải thích cơ chế xuất bản repository finder methods thành search endpoints như thế nào?
Bạn phân biệt collection path và search resource path của một repository ra sao?
Bạn sử dụng @RestResource(path, rel) trên finder method để ổn định contract URL như thế nào?
Bạn xác định khi nào finder method được export và khi nào không được export theo access policy nào?
Bạn thiết kế tên query parameters của search finder methods phù hợp với method signature như thế nào?
Bạn đánh giá nguy cơ sửa tên Java method làm client gọi search endpoint cũ bị hỏng ra sao?
Bạn tổ chức tìm kiếm theo customer ID, trạng thái và thời gian mà không expose truy vấn tùy ý như thế nào?
Bạn phân biệt derived query method với @Query trong Spring Data repository dưới góc nhìn REST contract như thế nào?
Bạn chọn Page, Slice hoặc List cho finder method theo nhu cầu paging và chi phí truy vấn nào?
Bạn đánh giá rủi ro của finder method không phân trang khi trả hàng triệu bản ghi ra sao?
Bạn kiểm soát số parameters và điều kiện lọc để ngăn query quá nặng hoặc thiếu giới hạn ra sao?
Bạn xác định khả năng QuerydslPredicateExecutor đưa thêm những trường lọc nào ra HTTP và cần bảo vệ ra sao?
Bạn đánh giá nguy cơ client truy vấn được các property không intended thông qua Querydsl binding mặc định ra sao?
Bạn thiết kế whitelist searchable fields bằng custom Querydsl bindings khi công khai API như thế nào?
Bạn phân biệt filter nghiệp vụ cố định với biểu thức tìm kiếm động do client cung cấp theo mức độ tin cậy nào?
Bạn kiểm thử user input không thể đưa tên field đặc quyền vào tìm kiếm và suy ra dữ liệu nhạy cảm như thế nào?
Bạn xác định cách xử lý tham số tìm kiếm sai kiểu hoặc enum không hợp lệ trong HTTP response như thế nào?
Bạn kiểm soát sorting parameters để client không yêu cầu sắp xếp theo trường chi phí cao như thế nào?
Bạn phân biệt sorting bằng property JPA với ordering theo HAL collection link khi tiêu thụ client như thế nào?
Bạn thiết kế tìm kiếm text qua repository REST và nhận diện giới hạn full-text search của database như thế nào?
Bạn quyết định tách search phức tạp sang Elasticsearch hoặc API chuyên biệt khi nào?
Bạn đánh giá ảnh hưởng của query method trả projection tới biểu diễn HAL và link metadata ra sao?
Bạn phân biệt search finder endpoint được export với search backend được phép gọi trong nội bộ ra sao?
Bạn quản lý request rate và per-user quotas khi các finder methods có query cost khác nhau như thế nào?
Bạn kiểm tra multi-tenant predicate có được áp cho mọi search method theo chính sách nào?
Bạn thiết kế test cho các search finder methods khi entity data set có dữ liệu của nhiều tenants như thế nào?
Bạn giải thích cơ chế phân trang của Spring Data REST dựa trên Pageable như thế nào?
Bạn phân biệt page, size và sort query parameters trong collection endpoint theo ý nghĩa nào?
Bạn xác định page index bắt đầu từ số nào và cách cấu hình theo client contract ra sao?
Bạn thiết kế default page size phù hợp payload, database latency và khả năng của client như thế nào?
Bạn giới hạn maximum page size để ngăn truy vấn bị lạm dụng mà vẫn hỗ trợ người dùng hợp lệ ra sao?
Bạn sử dụng RepositoryRestConfigurer để thiết lập pagination defaults theo chính sách nào?
Bạn phân biệt thông tin page.number, page.size, totalElements và totalPages trong response HAL như thế nào?
Bạn đánh giá chi phí của count query khi yêu cầu trả tổng số phần tử trên bảng lớn ra sao?
Bạn lựa chọn Slice thay vì Page để tránh count query khi client chỉ cần biết trang tiếp theo như thế nào?
Bạn xác định các HAL first, prev, next và last links hoạt động ra sao ở các trang biên?
Bạn thiết kế client sử dụng next link thay vì tự tính page number khi nhận response ra sao?
Bạn kiểm thử hành vi khi page vượt ngoài phạm vi kết quả mà vẫn không gây lỗi dữ liệu như thế nào?
Bạn xác định sorting trên nhiều properties được biểu diễn trong URL và xử lý thứ tự ưu tiên như thế nào?
Bạn kiểm tra sort direction asc hoặc desc và tên thuộc tính sai được xử lý ra sao?
Bạn đánh giá giới hạn offset pagination khi dữ liệu bị thêm hoặc xóa giữa hai requests như thế nào?
Bạn thiết kế API cursor hoặc keyset pagination riêng khi repository REST paging mặc định không đáp ứng quy mô nào?
Bạn phân tích tác động của transaction isolation và dữ liệu cập nhật đồng thời tới kết quả phân trang ra sao?
Bạn kiểm tra response page metadata không làm lộ số records của tenant khác ra sao?
Bạn thiết kế pagination cho finder query trả nhiều bản ghi có sort field trùng nhau như thế nào?
Bạn lựa chọn stable secondary sort để giảm kết quả trùng hoặc bị bỏ sót giữa các trang ra sao?
Bạn xác định số lượng DB queries phát sinh khi lấy page kèm HAL association metadata như thế nào?
Bạn thiết kế load test cho page lớn và truy vấn sắp xếp trên cột chưa có index ra sao?
Bạn đánh giá sự khác nhau giữa size limit ở API và giới hạn query thực tế ở tầng repository như thế nào?
Bạn kiểm thử HAL links giữ nguyên search/filter/sort parameters khi client theo next page ra sao?
Bạn kiểm soát request có page size bằng không, số âm hoặc quá lớn bằng validation như thế nào?
Bạn giải thích projection trong Spring Data REST giúp biến đổi representation của entity ra sao?
Bạn phân biệt projection với DTO trả về từ @RestController theo khả năng kiểm soát hợp đồng như thế nào?
Bạn sử dụng @Projection cho một interface để chọn các thuộc tính được thể hiện như thế nào?
Bạn xác định vai trò của thuộc tính types và name trong @Projection theo phiên bản hỗ trợ như thế nào?
Bạn thiết kế lựa chọn projection qua query parameter của Spring Data REST theo contract nào?
Bạn kiểm tra client nhận được HAL links phù hợp khi response dùng projection thay cho entity mặc định như thế nào?
Bạn đánh giá nguy cơ projection vô tình expose email, số điện thoại hoặc dữ liệu nhạy cảm ra sao?
Vì sao Spring Data REST projection không thể thay thế authorization hoặc field-level access control?
Bạn phân biệt closed projection với open projection sử dụng SpEL về tính toán và tác động hiệu năng ra sao?
Bạn kiểm soát SpEL projection không gọi service hoặc thao tác phức tạp gây N+1 queries như thế nào?
Bạn thiết kế projection cho card sản phẩm chỉ cần tên, giá và category label như thế nào?
Bạn lựa chọn projection để nhúng association hay để client tự follow link theo chi phí nào?
Bạn đánh giá nguy cơ expose cyclic associations hoặc payload lớn qua projection lồng nhau như thế nào?
Bạn sử dụng excerpt projection trên collection để giảm kích thước danh sách theo cấu hình nào?
Bạn phân biệt excerpt projection với projection client yêu cầu tường minh trên item endpoint ra sao?
Bạn kiểm tra @RepositoryRestResource(excerptProjection) tác động tới collection và embedded results theo phiên bản nào?
Bạn lựa chọn excerpt fields phù hợp với UX của danh sách và quyền truy cập của user như thế nào?
Bạn xử lý projection versioning khi Java interface bị đổi tên hoặc thêm field như thế nào?
Bạn thiết kế projection song song cho phiên bản API cũ và mới mà không phá clients đang dùng ra sao?
Bạn lựa chọn resource assembler hoặc custom endpoint thay projection khi yêu cầu biểu diễn phức tạp theo những tiêu chí nào?
Bạn đánh giá sự khác nhau giữa projection của Spring Data REST với database-level projection từ query performance ra sao?
Bạn kiểm tra một projection có gây lazy load hàng trăm entities trong một page response như thế nào?
Bạn thiết kế test đảm bảo projection không bỏ thiếu required HAL relation names như thế nào?
Bạn phân biệt Jackson @JsonIgnore, repository field exposure và projection về mục tiêu sử dụng ra sao?
Bạn xác định có cần giới hạn client được phép chọn projection bằng authorization hoặc cấu hình riêng như thế nào?
Bạn kiểm soát tên projection không bị coi là public data access policy duy nhất trong code review ra sao?
Bạn thiết kế phương thức trả dữ liệu aggregate không phù hợp entity projection bằng API riêng như thế nào?
Bạn giải thích cơ chế validation của Spring Data REST diễn ra quanh repository events như thế nào?
Bạn phân biệt Java Bean Validation trên entity với validator được gắn vào sự kiện repository như thế nào?
Bạn thiết kế các ràng buộc @NotNull, @Size hoặc @Pattern phù hợp cho một resource được tạo qua HTTP ra sao?
Bạn xác định validation ở create khác update khi thuộc tính bắt buộc chỉ có trong thao tác tạo như thế nào?
Bạn cấu hình ValidatingRepositoryEventListener hoặc cơ chế validation tương ứng theo phiên bản như thế nào?
Bạn phân biệt validate before create với validate before save khi entity có trạng thái và quy tắc khác nhau như thế nào?
Bạn kiểm thử validator trả thông điệp lỗi có cấu trúc thay vì exception thô ra HTTP như thế nào?
Bạn xử lý lỗi nested object validation khi request cập nhật một association như thế nào?
Bạn đánh giá rủi ro chỉ xác thực request body mà bỏ qua các ràng buộc nghiệp vụ dựa trên database ra sao?
Bạn quyết định bổ sung unique constraint ở database bên cạnh validation trước save dựa trên rủi ro cạnh tranh nào?
Bạn thiết kế cross-field validation khi giá khuyến mãi phải thấp hơn giá gốc trong entity như thế nào?
Bạn ngăn trường role hoặc status bị cập nhật trái phép dù validation về cú pháp vẫn đạt như thế nào?
Bạn phân biệt validation failure với optimistic locking conflict trong API errors như thế nào?
Bạn lựa chọn thông điệp lỗi an toàn không tiết lộ entity IDs của tenant khác theo nguyên tắc nào?
Bạn thiết kế validation khi một request chỉ PATCH một vài fields và các field khác không xuất hiện ra sao?
Bạn kiểm tra validation được chạy nhất quán khi repository được gọi qua REST và từ service nội bộ như thế nào?
Bạn xử lý các lỗi mapping JSON trước lúc tạo entity khác với lỗi validator phát hiện sau binding như thế nào?
Bạn tổ chức bản dịch thông điệp validation theo locale mà không làm thay đổi error codes ổn định ra sao?
Bạn xác định vai trò của RepositoryEventHandler trong lifecycle mutation của Spring Data REST như thế nào?
Bạn sử dụng @RepositoryEventHandler để gom logic xử lý liên quan tới một loại entity như thế nào?
Bạn phân biệt @HandleBeforeCreate với @HandleAfterCreate theo thời điểm và dữ liệu có sẵn như thế nào?
Bạn phân biệt @HandleBeforeSave với @HandleAfterSave khi cập nhật một resource như thế nào?
Bạn thiết kế handler before delete kiểm tra business invariant trước khi cho phép xóa ra sao?
Bạn sử dụng AbstractRepositoryEventListener khi cần xử lý các sự kiện repository theo cách thống nhất như thế nào?
Bạn so sánh annotation-based handlers và event listener subclass về testability và coupling ra sao?
Bạn xác định sự khác nhau giữa before link save và before entity save trong cập nhật associations như thế nào?
Bạn kiểm soát số lần event handler được gọi khi một HTTP operation tác động tới nhiều entities như thế nào?
Bạn đánh giá rủi ro dùng repository event handler để phát external event trước khi database commit ra sao?
Bạn thiết kế transactional outbox nếu một mutation REST phải phát sự kiện sang message broker sau commit như thế nào?
Bạn phân biệt repository lifecycle events với domain events phát sinh từ aggregate trong domain-driven design ra sao?
Bạn xử lý retry hoặc rollback khi event handler gọi một hệ thống ngoài bị timeout như thế nào?
Bạn đánh giá dấu hiệu cần chuyển business logic từ before-save handler sang domain service có transaction rõ ràng ra sao?
Bạn kiểm thử listener không tạo recursion khi nó lưu một entity khác bằng repository như thế nào?
Bạn đánh giá thứ tự thực thi của nhiều repository event handlers và tránh dựa vào thứ tự không được bảo đảm ra sao?
Bạn kiểm soát event handlers không ngầm sửa các trường audit nhạy cảm nếu client không có quyền như thế nào?
Bạn thiết kế kiểm thử end-to-end POST/PATCH để bảo đảm cả validation và repository hooks được kích hoạt như thế nào?
Bạn xác định những luồng cập nhật nào bỏ qua Spring Data REST repository events và kiểm tra hậu quả ra sao?
Bạn đánh giá ảnh hưởng của exception trong after-save handler tới HTTP status và trạng thái transaction theo môi trường như thế nào?
Bạn quản lý audit trail khi entity được thay đổi qua REST, batch job và service code khác nhau ra sao?
Bạn thiết kế event handler có idempotency khi HTTP client retry sau timeout như thế nào?
Bạn lựa chọn application event hay explicit service method để phát domain event khi cần tính toán nhiều thực thể ra sao?
Bạn xác định ranh giới chịu trách nhiệm validation, event handling và persistence trong kiến trúc Spring Data REST như thế nào?
Vì sao tắt repository export không thể thay thế cơ chế authentication và authorization của ứng dụng?
Bạn tổ chức SecurityFilterChain để yêu cầu authentication cho repository REST endpoints như thế nào?
Bạn phân biệt URL-based authorization với method-level @PreAuthorize trên repository về khả năng áp dụng như thế nào?
Bạn thiết kế quyền chỉ đọc cho một repository được expose mà không cấp quyền save/delete như thế nào?
Bạn kiểm tra các finder methods có chịu cùng chính sách authorization với CRUD methods không ra sao?
Bạn áp dụng least privilege để tài khoản ứng dụng không thể sửa dữ liệu không thuộc chức năng của nó như thế nào?
Bạn xác định nguy cơ client dùng search endpoint để đọc entities bị cấm ở item endpoint ra sao?
Bạn thiết kế tenant isolation đồng nhất cho collection, item, search và association resources như thế nào?
Bạn phân biệt che thông tin tồn tại của entity bằng 404 với từ chối truy cập bằng 403 theo security policy ra sao?
Bạn ngăn client thay đổi foreign key hoặc association để tham chiếu sang tenant khác như thế nào?
Bạn kiểm soát HTTP methods và exposed repositories bằng SecurityFilterChain cùng cấu hình export như thế nào?
Bạn đánh giá rủi ro path-based access rule bỏ sót đường dẫn /search hoặc association endpoints như thế nào?
Bạn kiểm thử một tài khoản chỉ có quyền đọc không thể thực hiện PATCH, PUT hay DELETE ra sao?
Bạn quản lý CSRF cho client trình duyệt dùng session authentication khi gửi mutation requests như thế nào?
Bạn phân biệt stateless bearer token API với cookie session về CSRF và logout theo mô hình nào?
Bạn thiết kế OAuth2 resource server cho API sinh từ repository mà vẫn kiểm soát scopes như thế nào?
Bạn kiểm tra CORS chỉ mở cho origins hợp lệ và không vô tình cho credentials từ mọi domain như thế nào?
Bạn xác định cách áp dụng request rate limits cho finder endpoints dễ bị lạm dụng ra sao?
Bạn giới hạn size, sort và query parameters để chống enumeration và truy vấn nặng như thế nào?
Bạn ngăn JSON mass assignment cập nhật field owner, createdBy hoặc security flags bằng cách nào?
Bạn kiểm soát response projections không lộ password hash, access token hoặc PII như thế nào?
Bạn đánh giá rủi ro _links hoặc profile metadata làm lộ tên nội bộ của repository và entities ra sao?
Bạn thiết kế policy ẩn và bảo vệ endpoints /profile hoặc các tài nguyên metadata liên quan như thế nào?
Bạn xác minh HTTPS và Forwarded header processing không tạo HAL links trỏ về HTTP không mã hóa ra sao?
Bạn đánh giá cách xử lý malicious Host headers khi generating absolute resource URLs như thế nào?
Bạn phân biệt database row-level security với filter tenant ở application để tăng phòng vệ như thế nào?
Bạn thiết kế security regression tests khi thêm repository mới khiến endpoint vô tình được export như thế nào?
Bạn kiểm tra người dùng không thể truy cập API thông qua alternate paths hoặc rel names ngoài ACL như thế nào?
Bạn xử lý validation và authorization cho bulk actions khi Spring Data REST không cung cấp workflow nghiệp vụ sẵn ra sao?
Bạn lựa chọn Audit logging cho create, update, delete mà không ghi dữ liệu cá nhân quá mức như thế nào?
Bạn thiết kế chiến lược versioning cho Spring Data REST API khi entity và repository cùng phát triển ra sao?
Bạn phân biệt phiên bản Java entity với public HTTP resource contract về vòng đời như thế nào?
Bạn xác định những thay đổi nào về HAL relation hoặc path có khả năng breaking changes cho client ra sao?
Bạn thiết kế deprecation policy để duy trì đường dẫn cũ khi đổi tên một exported repository như thế nào?
Bạn tổ chức nhiều projections hoặc API prefixes khi cần hỗ trợ client cũ và mới song song như thế nào?
Bạn đánh giá rủi ro expose entity fields mới trong response mặc định mà client không dự kiến ra sao?
Bạn quản lý schema migrations theo expand-contract khi nhiều ứng dụng dùng chung database và REST API như thế nào?
Bạn quyết định tách DTO boundary và controller riêng để ổn định public API contract dựa trên các yêu cầu nào?
Bạn tạo tài liệu REST contract cho repository-generated endpoints bằng công cụ và test phù hợp nào?
Bạn so sánh HAL profile discovery với OpenAPI contract trong việc giúp client phát hiện thay đổi như thế nào?
Bạn thiết kế contract tests ghi nhận các path, rel names, media types và status codes quan trọng ra sao?
Bạn kiểm soát HTTP caching, ETag và concurrency semantics khi cập nhật entity schema như thế nào?
Bạn xử lý rename của entity property khi query parameters trong finder URL đã được client sử dụng như thế nào?
Bạn xác định cách giữ compatibility khi đổi kiểu ID từ số sang UUID nhưng public links đã được lưu như thế nào?
Bạn đánh giá tác động của việc thay @RepositoryRestResource(path) tới external bookmarks và incoming links ra sao?
Bạn lựa chọn cách chuyển resource từ Spring Data REST sang custom controller mà không đổi contract như thế nào?
Bạn lựa chọn đặt API gateway trước Spring Data REST dựa trên nhu cầu authentication, throttling và routing nào?
Bạn đánh giá các tiêu chí khiến Spring Data REST phù hợp với internal admin API nhưng không phù hợp với public domain API ra sao?
Bạn tổ chức quy trình kiểm thử compatibility với các client tiêu thụ HAL khi nâng cấp Spring Data REST ra sao?
Bạn sử dụng @SpringBootTest và MockMvc để kiểm thử repository REST endpoints trong Spring Boot như thế nào?
Bạn quyết định dùng WebTestClient hoặc HTTP client thực trong integration test theo web stack nào?
Bạn kiểm thử GET collection trả application/hal+json với _links và _embedded phù hợp ra sao?
Bạn xây dựng JSONPath assertions cho self, search, next và association links mà không hardcode host như thế nào?
Bạn kiểm tra repository export false thật sự không tạo endpoints có thể truy cập từ bên ngoài ra sao?
Bạn kiểm thử @RestResource(path, rel) giữ ổn định finder URI sau khi refactor repository method như thế nào?
Bạn xác nhận POST tạo item trả Location trỏ tới resource thực tế và có thể GET được như thế nào?
Bạn kiểm thử PUT, PATCH và DELETE theo media types và HTTP status của phiên bản đang chạy ra sao?
Bạn thiết kế test validation cho invalid entity không lưu dữ liệu và trả lỗi có cấu trúc ra sao?
Bạn kiểm thử optimistic concurrency bằng hai phiên cập nhật entity với ETag hoặc version theo cơ chế hỗ trợ ra sao?
Bạn tạo fixtures với liên kết to-one và to-many để kiểm thử association mutation qua text/uri-list như thế nào?
Bạn kiểm thử association URI của tenant khác bị từ chối mà không sửa database như thế nào?
Bạn xác minh handler @HandleBeforeSave và @HandleAfterSave được chạy đúng khi cập nhật qua REST như thế nào?
Bạn kiểm thử repository event listener không phát side effect bên ngoài khi database transaction rollback như thế nào?
Bạn dùng Testcontainers PostgreSQL hoặc database thực tương ứng để phát hiện lỗi JPA relation và constraints ra sao?
Bạn phân biệt @DataJpaTest kiểm thử repository với end-to-end HTTP test có Spring Data REST đầy đủ như thế nào?
Bạn kiểm tra finder search methods không bị N+1 hoặc count queries quá đắt trên dữ liệu gần production như thế nào?
Bạn xây dựng integration test phân trang và sort khi nhiều bản ghi có cùng sort key như thế nào?
Bạn kiểm thử HTTP pagination links bảo toàn filter parameters khi người dùng chuyển trang ra sao?
Bạn mô phỏng page size cực lớn hoặc sort field không tồn tại để kiểm tra query limits như thế nào?
Bạn tạo dataset nhiều tenants để kiểm thử endpoint collection không lộ số lượng và dữ liệu tenant khác ra sao?
Bạn xác minh projection và excerpt projection không xuất lộ các trường PII trong JSON như thế nào?
Bạn kiểm thử interface open projection có SpEL không gây tải database bất ngờ như thế nào?
Bạn dùng Spring Security test support để kiểm tra anonymous, read-only và admin roles trên cùng resource ra sao?
Bạn kiểm thử browser cookie authentication và CSRF protections cho POST/PATCH/DELETE như thế nào?
Bạn kiểm thử 401/403/404 behavior nhất quán giữa item, search và association resources ra sao?
Bạn thiết kế contract tests phát hiện thay đổi ngoài ý muốn từ @JsonIgnore hoặc Jackson configuration trong HTTP resource như thế nào?
Bạn tổ chức snapshot tests HAL representation sao cho không thất bại vì thay đổi thứ tự links vô nghĩa ra sao?
Bạn kiểm thử reverse proxy forwarded headers để self links có đúng HTTPS host và base path như thế nào?
Bạn mô phỏng HTTP client retry POST sau timeout để kiểm tra nguy cơ tạo entity trùng ra sao?
Bạn kiểm thử custom controller và repository REST endpoint dùng cùng path không gây mapping conflict như thế nào?
Bạn đo p95 latency của GET collection theo page size và số associations được serialize như thế nào?
Bạn thiết kế load test cho finder methods phức tạp để tìm query cost và bottleneck trước production ra sao?
Bạn lựa chọn quality gates cho API gồm security, HAL contract, persistence integrity và response size như thế nào?
Bạn theo dõi số requests theo resource path, method và status mà không dùng raw entity IDs làm metric tag ra sao?
Bạn đo HTTP latency riêng cho serialization, database query và repository event handler như thế nào?
Bạn xác định N+1 queries từ HAL associations hoặc projections qua SQL metrics và tracing như thế nào?
Bạn thiết kế rate limiting cho search endpoints có thể tạo truy vấn tốn tài nguyên ra sao?
Bạn phân biệt lỗi 400 do binding query parameter với 500 do repository exception khi quan sát logs như thế nào?
Bạn kiểm soát logging request body để không ghi password hoặc dữ liệu cá nhân từ entity như thế nào?
Bạn thiết kế tracing từ HTTP resource tới repository SQL query và event handler như thế nào?
Bạn xác định cách đặt alert khi HTTP 5xx tăng đồng thời với DB connection pool saturation ra sao?
Bạn phân biệt slowdown do JSON serialization với slowdown do pageable count query như thế nào?
Bạn kiểm tra response payload tăng mạnh sau thêm association mới bằng những metrics nào?
Bạn tổ chức canary release cho thay đổi repository REST contract và quan sát client errors ra sao?
Bạn xử lý cache invalidation khi GET collection dùng CDN nhưng POST/PATCH cập nhật database như thế nào?
Bạn đánh giá nguy cơ caching HAL representation chứa absolute links theo host hoặc tenant khác nhau ra sao?
Bạn thiết kế runbook phát hiện repository mới vô tình được public sau một lần deploy như thế nào?
Bạn theo dõi tần suất gọi các finder methods để loại bỏ hoặc tối ưu endpoint ít dùng ra sao?
Bạn lựa chọn tách truy vấn aggregation tốn kém khỏi exported repository dựa trên các chỉ số vận hành nào?
Bạn đánh giá sức chịu tải của Spring Data REST API khi database có nhiều quan hệ lazy và page size lớn ra sao?
Bạn kiểm tra transaction timeouts và các lỗi optimistic locking qua metrics và HTTP responses như thế nào?
Bạn tổ chức migration khi chuyển một API nội bộ đang dùng HAL sang custom BFF mà vẫn duy trì link relations ra sao?
Nếu thêm Spring Data REST starter làm xuất hiện endpoint không mong muốn, bạn sẽ kiểm tra repository export và security ra sao?
Nếu GET /orders trả 404 dù repository tồn tại, bạn sẽ kiểm tra base path, export flags và resource path như thế nào?
Nếu client cũ không nhận ra relation sau khi đổi tên repository, bạn sẽ phục hồi compatibility như thế nào?
Nếu HAL self link dùng HTTP thay vì HTTPS sau reverse proxy, bạn sẽ kiểm tra forwarded headers và trust settings ra sao?
Nếu GET collection không có _embedded như frontend dự kiến, bạn sẽ kiểm tra dữ liệu, media type và representation ra sao?
Nếu POST entity thành công nhưng response không có ID field, bạn sẽ giải thích HAL link và ID exposure như thế nào?
Nếu client gửi PATCH với media type không được hỗ trợ, bạn sẽ kiểm tra API contract và HTTP 415 ra sao?
Nếu PATCH một field làm giá trị cũ của field khác bị mất, bạn sẽ đối chiếu payload semantics và entity mapping ra sao?
Nếu hai clients cùng cập nhật resource khiến dữ liệu bị ghi đè, bạn sẽ áp dụng optimistic locking hoặc conditional requests như thế nào?
Nếu DELETE một parent làm xóa cả children ngoài dự kiến, bạn sẽ kiểm tra JPA cascade và orphanRemoval ra sao?
Nếu client liên kết một Order với Customer của tenant khác, bạn sẽ chặn thao tác ở tầng nào và kiểm thử ra sao?
Nếu HAL response lặp associations gây N+1 queries, bạn sẽ chẩn đoán fetch plan, pagination và projections như thế nào?
Nếu search finder method vừa được thêm khiến dữ liệu nhạy cảm bị truy vấn được, bạn sẽ siết export và authorization ra sao?
Nếu Querydsl filter cho phép client dò giá trị trường nội bộ, bạn sẽ giới hạn bindings như thế nào?
Nếu repository method đổi tên làm URL /search cũ biến mất, bạn sẽ thiết kế tương thích ngược ra sao?
Nếu client yêu cầu size=100000 gây quá tải database, bạn sẽ đặt max page size và query limits như thế nào?
Nếu collection pagination có bản ghi trùng do dữ liệu thay đổi giữa các trang, bạn sẽ xử lý sorting và contract như thế nào?
Nếu một projection expose thêm thuộc tính salary ngoài mong muốn, bạn sẽ sửa contract và kiểm thử bảo mật ra sao?
Nếu excerpt projection kéo theo lazy associations khiến page chậm, bạn sẽ kiểm tra SQL và thiết kế lại projection như thế nào?
Nếu @RepositoryEventHandler không được gọi sau POST, bạn sẽ kiểm tra đăng ký bean và lifecycle hooks như thế nào?
Nếu validator không chặn dữ liệu không hợp lệ qua REST nhưng repository test vẫn xanh, bạn sẽ kiểm tra listener wiring ra sao?
Nếu event handler gửi broker message trước commit rồi transaction rollback, bạn sẽ triển khai outbox như thế nào?
Nếu một API trả 403 trên item nhưng finder vẫn trả entity đó, bạn sẽ tìm lỗ hổng authorization ở đâu?
Nếu người dùng read-only vẫn sửa association qua một đường dẫn khác, bạn sẽ rà soát security rules như thế nào?
Nếu @Cacheable ở service layer trả HAL links của tenant trước, bạn sẽ thiết kế cache key và invalidation ra sao?
Nếu một entity field được đổi tên khiến client parse HAL response lỗi, bạn sẽ thực hiện deprecation và versioning như thế nào?
Nếu sản phẩm nhận 500 do lazy loading exception lúc sinh response, bạn sẽ xử lý transaction, projection và fetch strategy ra sao?
Nếu metrics báo 200 nhiều nhưng client không nhận các links cần thiết, bạn sẽ thêm contract monitoring như thế nào?
Nếu Spring Data REST upgrade làm thay đổi behavior của association endpoint, bạn sẽ kiểm chứng regression bằng bộ test nào?
Nếu repository được export cho admin nhưng vô tình đi qua gateway public, bạn sẽ bổ sung lớp phòng vệ nào?
Bạn xây dựng runbook khi Spring Data REST phát sinh endpoint ngoài ý muốn, finder truy vấn quá nặng và nhiều clients báo lỗi HAL contract như thế nào?
