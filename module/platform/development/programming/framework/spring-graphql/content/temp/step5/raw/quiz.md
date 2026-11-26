Câu 1. Trong GraphQL SDL dùng với Spring for GraphQL, root type nào cung cấp các thao tác đọc dữ liệu?
A. type Mutation định nghĩa mọi field chỉ dùng để đọc
B. type Subscription định nghĩa tất cả truy vấn đồng bộ
C. input Query khai báo các response field trả về từ server
D. type Query định nghĩa các field để truy vấn dữ liệu
Đáp án đúng: D

Câu 2. Muốn khai báo thao tác tạo đơn hàng trong GraphQL SDL, root type nào phù hợp?
A. type Mutation khai báo operation thay đổi dữ liệu
B. type Query cho operation được gọi chỉ để cập nhật
C. type Subscription cho thao tác INSERT trả về tức thì
D. scalar Mutation cho đối tượng nhận tham số đầu vào
Đáp án đúng: A

Câu 3. Trong GraphQL SDL, Subscription thường phục vụ tình huống nào?
A. Thực hiện một truy vấn duy nhất trả một JSON response
B. Gửi lần lượt nhiều Mutation trong một transaction SQL
C. Đăng ký luồng sự kiện mới từ phía server theo thời gian
D. Tự làm cache cho tất cả field được resolve từ schema
Đáp án đúng: C

Câu 4. Một field định nghĩa kiểu String! trong schema có yêu cầu gì?
A. Field bắt buộc có đối số String trên mỗi truy vấn
B. Field phải được resolver trả về dưới dạng List<String>
C. Field phải trả String khác null khi client truy vấn
D. Field chỉ xuất hiện trong operation Mutation
Đáp án đúng: C

Câu 5. Kiểu [Book!]! trong GraphQL schema biểu thị điều gì?
A. List không null và từng phần tử Book đều không null
B. List có thể null nhưng item Book phải có dữ liệu
C. List bắt buộc có một phần tử Book khi thực thi
D. List có thể null và item trong list cũng có thể null
Đáp án đúng: A

Câu 6. Khi muốn định nghĩa đối số có các field lồng nhau trong SDL, dùng cấu trúc nào?
A. input object type mô tả cấu trúc dữ liệu lồng nhau
B. type object có thể đưa trực tiếp vào input argument
C. interface type dùng như biến input tại runtime
D. union type để kết hợp nhiều kiểu input object
Đáp án đúng: A

Câu 7. GraphQL variables hỗ trợ thao tác nào tốt hơn việc ghép trực tiếp giá trị vào query string?
A. Phải khai báo biến trong schema SDL ở từng lần gọi
B. Truyền giá trị đối số độc lập với văn bản operation
C. Cho phép truyền giá trị trái kiểu đã khai trong operation
D. Cho phép bỏ các tham số non-null khi server chạy query
Đáp án đúng: B

Câu 8. Một field kiểu ID trong GraphQL SDL nên được hiểu như thế nào?
A. Giá trị bắt buộc ánh xạ sang Java Long cho mọi resolver
B. Giá trị chỉ có thể dùng làm khóa chính của bảng SQL
C. GraphQL ID là scalar định danh, có thể biểu diễn bằng chuỗi
D. Giá trị sẽ tự được sinh bởi GraphQL engine trước mỗi query
Đáp án đúng: C

Câu 9. Khi định nghĩa enum OrderStatus trong SDL, client thường truyền gì?
A. Một field tuỳ ý ngoài danh sách enum đã định nghĩa
B. Dùng literal thuộc giá trị enum được phép
C. Một chuỗi kiểu JSON chứa toàn bộ enum constants
D. Một tên class Java trùng class của server
Đáp án đúng: B

Câu 10. Khi GraphQL cần scalar DateTime không có sẵn, phương án server nào phù hợp?
A. Đặt @QueryMapping lên field DateTime để tự tạo scalar
B. Chỉ khai type DateTime gồm một field String là đủ
C. Thêm DateTime vào enum rồi truyền ISO string tùy ý
D. Khai scalar SDL rồi đăng ký GraphQLScalarType
Đáp án đúng: D

Câu 11. Với Spring Boot for GraphQL, nơi nào thường đặt tệp SDL để được auto-load?
A. src/test/resources/templates/schema.html trong test runtime
B. src/main/java/graphql/schema.graphqls cạnh controller class
C. META-INF/services/graphql/Query.java thay cho SDL
D. src/main/resources/graphql/schema.graphqls trong classpath
Đáp án đúng: D

Câu 12. Khi schema SDL khai báo Query.book(id: ID!): Book, cần bổ sung gì để lấy dữ liệu thực tế?
A. Chỉ một entity JPA tên Book, không cần resolver
B. DataFetcher hay resolver phù hợp với field Query.book
C. Một @RestController cho endpoint GET /book/{id}
D. Chỉ đăng ký controller bean mà không map field Query.book
Đáp án đúng: B

Câu 13. Để Spring phát hiện annotation handler GraphQL, class thường cần vai trò nào?
A. Được đăng ký làm Spring controller bean trong context
B. Khai method trùng tên field SDL mà không cần Spring bean
C. Phải có @RestController và HTTP GET path cho từng field
D. Phải tự khởi tạo bằng new trong GraphQL schema parser
Đáp án đúng: A

Câu 14. Annotation nào gọn nhất để xử lý top-level field Query.books trong Spring GraphQL?
A. @MutationMapping trên method đọc field books
B. Dùng @QueryMapping để map field books trên root Query
C. @SchemaMapping(typeName="Mutation") trên Query.books
D. @SubscriptionMapping trên method trả về danh sách Book
Đáp án đúng: B

Câu 15. Muốn xử lý root Mutation.createOrder, nên chọn annotation nào?
A. @QueryMapping để buộc mutation chạy qua GET request
B. @SubscriptionMapping để áp transaction cho mọi insert
C. @MutationMapping cho field createOrder trên Mutation
D. @BatchMapping trên root Mutation cho một argument đầu vào
Đáp án đúng: C

Câu 16. Khi root Subscription.orderEvents được triển khai trong Spring GraphQL, annotation nào phù hợp?
A. @MutationMapping để tự phát sự kiện vào WebSocket
B. @QueryMapping để thiết lập stream với HTTP polling
C. @SchemaMapping trên Query để tạo durable subscription
D. @SubscriptionMapping cho method phát luồng sự kiện
Đáp án đúng: D

Câu 17. Khi Book.author không lưu sẵn trong dữ liệu Book, resolver nào phù hợp?
A. @SchemaMapping(typeName="Book", field="author")
B. @QueryMapping trên method tên author thuộc mọi root
C. @MutationMapping trên Book.author để tải Author
D. @SubscriptionMapping trên field Book.author để join
Đáp án đúng: A

Câu 18. Trong annotated controller GraphQL, @Argument("id") có chức năng nào?
A. Lấy field id từ source object của parent field resolver
B. Chọn GraphQL request context có key id lúc xử lý
C. Đọc HTTP path variable id của GraphQL endpoint
D. Bind đối số id của field từ GraphQL request vào method
Đáp án đúng: D

Câu 19. Trong field resolver Book.author, muốn nhận parent Book để tìm author nên dùng gì?
A. Tham số @Argument Book để lấy object từ query variable
B. Tham số @ContextValue Book để đọc root type Query
C. Dùng @Source Book để lấy parent Book của field author
D. Tham số @Header Book để tạo entity từ HTTP request
Đáp án đúng: C

Câu 20. Nếu resolver xử lý field author của type Book, phần typeName trong @SchemaMapping chỉ rõ điều gì?
A. Tên Java package chứa class Book trên server
B. typeName là GraphQL parent type chứa field author
C. Tên root Mutation sẽ luôn trả về object Book
D. Tên schema file mà controller phải tự nạp
Đáp án đúng: B

Câu 21. Khi resolver cần biết những subfield mà client yêu cầu, API nào có ích?
A. DataFetchingEnvironment cung cấp selection set
B. GraphQLContext mặc nhiên chứa mọi subfield client chọn
C. @Argument tự bind toàn bộ selection set vào Java bean
D. DataLoader.load(...) trả ra selection set của field
Đáp án đúng: A

Câu 22. Để chuyển request-scope metadata đã đặt trong GraphQLContext vào handler, cách nào phù hợp?
A. Dùng @ContextValue bind key của GraphQLContext
B. Dùng @Argument để đọc bất kỳ GraphQLContext entry
C. Dùng @Source để tự bind toàn bộ HTTP request headers
D. Dùng @BatchMapping chỉ để lấy một metadata key
Đáp án đúng: A

Câu 23. Khi nhiều Book cần resolve Author, @BatchMapping giúp việc gì?
A. Tự tạo nhiều HTTP request cho mỗi field Book.author
B. @BatchMapping gom Book nguồn để tải Author theo lô
C. Chạy mỗi author resolver trong transaction SQL riêng
D. Nhân bản Book list thành nhiều GraphQL operation mới
Đáp án đúng: B

Câu 24. Dấu hiệu N+1 điển hình khi query books { author { name } } là gì?
A. Một query duy nhất tải books kèm toàn bộ author bằng join
B. GraphQL engine trả nhiều lỗi parse cho một field đầu vào
C. Một subscription được mở cho mỗi row của bảng Author
D. Một query books rồi thêm một query author riêng cho từng Book
Đáp án đúng: D

Câu 25. Với @BatchMapping trả Map<Book, Author>, điều kiện ánh xạ quan trọng là gì?
A. Map key phải là authorId còn value là từng Book nguồn
B. Map key phải là index Book trong danh sách được tải
C. Map key là tên field author cho mọi Book của batch
D. Map key là Book nguồn, ghép Author đúng với mỗi field
Đáp án đúng: D

Câu 26. Nếu muốn đăng ký DataLoader tùy chỉnh ngoài @BatchMapping, thành phần nào phù hợp?
A. DataLoaderRegistry phải dùng dạng static giữa mọi request
B. @QueryMapping là cách duy nhất đăng ký DataLoader
C. BatchLoaderRegistry đăng ký batch loading function
D. @BatchMapping là lựa chọn duy nhất để tạo DataLoader
Đáp án đúng: C

Câu 27. Vì sao DataLoader cho dữ liệu phụ thuộc quyền người dùng nên có scope request?
A. Cache dùng chung luôn được gắn với danh tính người gọi
B. Tránh tái sử dụng cache kết quả nhạy cảm giữa các request
C. Cache phải tự ghi key authorization vào GraphQL schema
D. BatchLoaderRegistry tự loại bỏ mọi rủi ro khi dùng static cache
Đáp án đúng: B

Câu 28. Trong DataFetcher, DataLoader.load(authorId) thường mang ý nghĩa gì?
A. Yêu cầu load theo key để DataLoader có thể gom các key
B. Gửi SQL SELECT ngay cho từng authorId chưa được gom
C. Trả về Author ngay từ database trên thread caller
D. Tạo một GraphQL query con qua HTTP cho mỗi authorId
Đáp án đúng: A

Câu 29. Khi tối ưu lookup author cho nhiều bookId, câu SQL nào phù hợp với batch loading?
A. SELECT theo từng bookId trong vòng lặp ở resolver
B. SELECT toàn bộ bảng Author rồi trả bản ghi đầu tiên
C. SELECT Author theo tập key IN và map lại theo mỗi key
D. UPDATE Author cho mỗi Book trước khi lấy field name
Đáp án đúng: C

Câu 30. Nếu một Book không có Author và field author nullable, batch loader nên phản ánh thế nào?
A. Trả null cho Book thiếu Author do schema cho phép nullable
B. Tạo Author giả với một ID bất kỳ để field luôn non-null
C. Trả Author đầu tiên tìm thấy trong batch cho Book đó
D. Chuyển mọi Book khác sang GraphQL error không có data
Đáp án đúng: A

Câu 31. Vì sao không nên dùng một static DataLoader cache cho nhiều user?
A. Cache toàn cục được gắn GraphQLContext khác nhau theo key
B. Cache chung tự vô hiệu mỗi khi user gửi biến khác
C. Cache chung đảm bảo policy security được tái đánh giá
D. Cache toàn cục có thể gây lộ dữ liệu và kết quả cũ
Đáp án đúng: D

Câu 32. Một annotated GraphQL Query handler trả Mono<Book> có lợi ích nào khi nguồn dữ liệu reactive?
A. Mono tự biến Query thành GraphQL Subscription trong schema
B. Spring GraphQL có thể thích ứng kết quả async của resolver
C. Mono bỏ qua bước validation GraphQL SDL cho các field
D. Mono buộc client gửi operation qua WebSocket transport
Đáp án đúng: B

Câu 33. Khi Subscription trong Spring GraphQL phát nhiều event, kiểu trả nào thường phù hợp?
A. Mono<Event> chỉ phát một phần tử rồi đóng stream
B. Publisher hoặc Flux phát các payload theo thời gian
C. List<Event> bắt server tính trước toàn bộ event stream
D. CompletableFuture<Event> chỉ trả một event cho subscription
Đáp án đúng: B

Câu 34. Để client nhận subscription real-time qua kết nối tương tác, transport nào thường dùng?
A. HTTP query response đơn lẻ được tự nâng cấp thành stream
B. GraphQL SDL tĩnh được dùng thay WebSocket protocol
C. GraphQL Mutation trả một response thay subscription
D. Dùng GraphQL over WebSocket khi protocol được hỗ trợ
Đáp án đúng: D

Câu 35. Khi resolver của một field nullable bị lỗi, GraphQL response có thể trông thế nào?
A. Data phần thành công kèm errors có path của field lỗi
B. Mọi field đều bị xóa khỏi response dù không liên quan
C. Server luôn trả một danh sách error mà không có data
D. Error luôn được chuyển thành HTTP 302 và không trả JSON
Đáp án đúng: A

Câu 36. Nếu resolver trả null cho field SDL được đánh dấu non-null, GraphQL thực hiện gì?
A. Tự thay null bằng chuỗi rỗng để giữ schema hợp lệ
B. Bỏ qua field đó rồi giữ parent object bình thường
C. Lan truyền null lên cấp cha theo quy tắc nullability
D. Tự đổi kiểu field từ String! sang String ở runtime
Đáp án đúng: C

Câu 37. Khi muốn chuyển exception của resolver thành GraphQLError có kiểm soát, dùng extension nào?
A. @ExceptionHandler trên REST Controller cho mọi GraphQL field
B. WebGraphQlInterceptor phải catch từng exception trong SQL
C. @SchemaMapping tự biến tất cả exception thành ValidationError
D. DataFetcherExceptionResolver đổi exception thành GraphQLError
Đáp án đúng: D

Câu 38. Vì sao response lỗi GraphQL production nên hạn chế chi tiết exception nội bộ?
A. GraphQL errors mặc định chứa thông tin được mã hóa end-to-end
B. Lỗi có stack trace khiến query depth bị tự động giảm
C. GraphQLError phải chứa SQL statement để client retry
D. Ẩn chi tiết nội bộ trong GraphQL errors gửi client
Đáp án đúng: D

Câu 39. Với field order.customerEmail cần kiểm tra quyền đọc, hướng Spring nào phù hợp?
A. Chỉ xác thực POST /graphql là đủ để mở mọi field
B. Đổi tên field thành privateEmail để GraphQL tự chặn
C. Dùng @PreAuthorize ở resolver hoặc service
D. Để client tự ẩn field khi không có quyền đọc
Đáp án đúng: C

Câu 40. Vì sao chỉ bảo vệ HTTP endpoint /graphql chưa đủ cho field nhạy cảm?
A. Mỗi GraphQL field thực tế tạo endpoint HTTP riêng biệt
B. GraphQL schema tự suy luận vai trò người dùng từ typeName
C. Cùng endpoint GraphQL nhưng field có quyền truy cập khác nhau
D. Authorization của operation luôn giống nhau với mọi field
Đáp án đúng: C

Câu 41. Để hạn chế truy vấn GraphQL lồng quá sâu gây tốn tài nguyên, giải pháp nào thích hợp?
A. Áp depth/complexity instrumentation và giới hạn phù hợp
B. Chỉ tắt schema introspection để query tự nông hơn
C. Tăng timeout của mọi DataLoader lên vô hạn
D. Chuyển toàn bộ field thành Mutation để cấm nested query
Đáp án đúng: A

Câu 42. Khi client cần gửi tham số tìm kiếm linh hoạt, cách viết query an toàn, dễ cache hơn là gì?
A. Ghép chuỗi input thẳng vào SDL schema trước mỗi request
B. Dùng GraphQL variables với operation được tham số hóa
C. Tạo một @QueryMapping method mới cho mỗi giá trị lọc
D. Đưa toàn bộ giá trị lọc vào tên field của schema
Đáp án đúng: B

Câu 43. Khi field chỉ cần id và name, tối ưu truy xuất backend có thể dựa trên gì?
A. Luôn query mọi cột và relationship để tránh cache miss
B. Đọc selection set để chỉ fetch field được yêu cầu
C. Tắt @SchemaMapping để GraphQL bỏ qua validation
D. Bỏ qua arguments và query tất cả row khi client hỏi
Đáp án đúng: B

Câu 44. Với danh sách orders lớn, vì sao cursor pagination thường đáng cân nhắc?
A. Cursor hỗ trợ duyệt ổn định khi dữ liệu thay đổi
B. GraphQL tự tạo index database từ cursor client gửi
C. Bỏ yêu cầu ORDER BY cho mọi câu SQL backend
D. Biến mỗi trang dữ liệu thành một Subscription riêng
Đáp án đúng: A

Câu 45. Khi viết test Spring GraphQL, GraphQlTester thường hỗ trợ điều gì?
A. Tự tạo schema mới theo các assertions của từng testcase
B. Chỉ kiểm tra JSON body mà không execute GraphQL document
C. Buộc mọi test phải khởi động HTTP server riêng
D. GraphQlTester execute document và assert theo path
Đáp án đúng: D

Câu 46. Để kiểm thử transport HTTP của endpoint GraphQL Spring, API nào phù hợp?
A. GraphQlTester bắt buộc mở một WebSocket cho query đơn
B. GraphQlTester không hỗ trợ kiểm tra error của response
C. HttpGraphQlTester thực thi và kiểm tra GraphQL qua HTTP
D. HttpGraphQlTester chỉ hỗ trợ GraphQL schema validation
Đáp án đúng: C

Câu 47. Khi kiểm thử GraphQL Subscription qua WebSocket, công cụ nào thích hợp?
A. HttpGraphQlTester dùng SSE mặc định không cần server hỗ trợ
B. WebSocketGraphQlTester kiểm tra subscription trên socket
C. GraphQlTester không có cách kiểm tra subscription stream
D. BatchLoaderRegistry gửi WebSocket handshake cho client
Đáp án đúng: B

Câu 48. Muốn test slice chỉ phần controller/schema GraphQL trong Spring Boot, dùng gì?
A. @DataJpaTest để tự quét cả GraphQL controller và schema
B. @RestClientTest khởi chạy WebSocket subscription backend
C. @GraphQlTest để dựng slice và mock dependency cần thiết
D. @WebFluxTest luôn bao gồm đầy đủ GraphQL controller stack
Đáp án đúng: C
