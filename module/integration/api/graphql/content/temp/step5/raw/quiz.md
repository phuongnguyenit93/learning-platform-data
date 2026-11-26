Câu 1. Trong schema GraphQL SDL, khai báo `type Article { id: ID! }` có nghĩa gì đối với `id`?
A. Giá trị `id` luôn được tạo tự động bởi server.
B. Giá trị `id` trả về không được là `null`.
C. Giá trị `id` bắt buộc là số nguyên duy nhất.
D. Giá trị `id` không thể dùng làm input argument.
Đáp án đúng: B

Câu 2. Kiểu gốc `Query` trong schema GraphQL thường có vai trò nào?
A. Liệt kê các kiểu scalar do server hỗ trợ.
B. Liệt kê các field dùng để thay đổi trạng thái dữ liệu.
C. Liệt kê các field mà client có thể truy vấn.
D. Liệt kê các field phát sự kiện đến client.
Đáp án đúng: C

Câu 3. Kiểu GraphQL `[Book!]!` ràng buộc `null` như thế nào?
A. Danh sách không `null`; các phần tử không `null`.
B. Danh sách có thể `null`; các phần tử có thể `null`.
C. Danh sách không `null`; các phần tử có thể `null`.
D. Danh sách có thể `null`; các phần tử không `null`.
Đáp án đúng: A

Câu 4. Khi truy vấn một field trả về object, selection set phải đáp ứng điều gì?
A. Không cần selection set nếu field nhận một đối số.
B. Chỉ cần selection set nếu field trả danh sách object.
C. Selection set phải chọn ít nhất một field con.
D. Selection set phải chứa mọi field của kiểu object.
Đáp án đúng: C

Câu 5. Với biến `$id: ID!` trong GraphQL operation, client truyền giá trị bằng cách nào?
A. Gửi giá trị qua `operationName` khi gọi operation.
B. Truyền giá trị trong `variables` đi kèm operation.
C. Gửi giá trị qua `extensions` của request GraphQL.
D. Gửi giá trị trong `arguments` ở cấp HTTP body.
Đáp án đúng: B

Câu 6. Kiểu `input` trong GraphQL schema chủ yếu dùng để làm gì?
A. Thay cho `scalar` để xử lý giá trị tùy ý.
B. Thay cho `type` để định nghĩa object trả về.
C. Thay cho `enum` để giới hạn các giá trị.
D. Khai báo cấu trúc object dùng làm đối số đầu vào.
Đáp án đúng: D

Câu 7. Khác biệt nào đúng giữa GraphQL interface và union?
A. Interface định nghĩa enum; union định nghĩa input object.
B. Interface định nghĩa field chung; union liệt kê các kiểu.
C. Interface chỉ dùng trong mutation; union dùng trong query.
D. Interface nhận scalar làm member; union chỉ nhận object.
Đáp án đúng: B

Câu 8. Field có kiểu `Node` interface; muốn chọn `title` chỉ có trên `Article`, client làm gì?
A. Chọn thẳng `title` trên `Node` mà không dùng fragment.
B. Thêm directive `@skip` vào selection set trên `Node`.
C. Dùng `... on Article { title }` trong selection set.
D. Khai báo variable chứa `title` tại GraphQL operation.
Đáp án đúng: C

Câu 9. Trong GraphQL Java, `DataFetcher` thực hiện vai trò nào?
A. Xác thực quyền của mọi subscription trong server.
B. Chuyển query document thành schema khởi động.
C. Xác định các kiểu scalar hợp lệ cho argument.
D. Gắn logic lấy giá trị cho field khi thực thi.
Đáp án đúng: D

Câu 10. `DataFetchingEnvironment.getArgument("id")` trong GraphQL Java dùng để làm gì?
A. Lấy danh sách các field trong response GraphQL.
B. Lấy toàn bộ các mutation đã đăng ký trong schema.
C. Lấy danh sách các subscription đang hoạt động.
D. Lấy giá trị argument đã được xử lý theo schema.
Đáp án đúng: D

Câu 11. Resolver của field `Order.customer` được thực thi khi nào?
A. Khi field `customer` được chọn và cần giải quyết.
B. Khi tạo một object `Order` trong repository.
C. Khi khai báo type `Order` lần đầu trong schema.
D. Với mọi `Order`, kể cả không chọn `customer`.
Đáp án đúng: A

Câu 12. Nếu resolver của một field nullable gặp lỗi, GraphQL thường trả kết quả ra sao?
A. Server xóa tất cả các field khác trong kết quả.
B. GraphQL tự thử lại field đến khi có giá trị.
C. Field lỗi có thể thành `null`, kèm mục trong `errors`.
D. Toàn bộ HTTP response bắt buộc trả về mã 500.
Đáp án đúng: C

Câu 13. Khi lấy danh sách order kèm customer, cách xử lý nào dễ gây N+1 truy vấn dữ liệu?
A. Lấy danh sách order rồi truy vấn customer cho từng order.
B. Nạp customer liên quan bằng một truy vấn `IN`.
C. Dùng một truy vấn JOIN để lấy order và customer.
D. Lấy danh sách order rồi nạp customer theo một batch.
Đáp án đúng: A

Câu 14. Trong GraphQL Java, DataLoader giúp hạn chế N+1 chủ yếu bằng cách nào?
A. Chia một field thành nhiều resolver chạy song song.
B. Gộp các khóa cần nạp vào lời gọi xử lý theo batch.
C. Cache một response GraphQL chung cho mọi tài khoản.
D. Tự chạy lại query GraphQL khi field còn thiếu dữ liệu.
Đáp án đúng: B

Câu 15. Vì sao DataLoader cache thường gắn với từng request GraphQL?
A. Để duy trì kết nối WebSocket cho subscription.
B. Để tái sử dụng toàn bộ cache qua nhiều tài khoản.
C. Để thay thế chức năng phân quyền trong resolver.
D. Để nhóm khóa và cache dữ liệu riêng cho từng request.
Đáp án đúng: D

Câu 16. `MappedBatchLoader<K, V>` trong GraphQL Java thường trả về kết quả dạng nào?
A. Một `CompletionStage<Map<K, V>>` ánh xạ khóa tới giá trị nạp.
B. Danh sách `V` bắt buộc cùng thứ tự các khóa `K` đầu vào.
C. Một `DataFetcher` mới sau mỗi lần dispatch.
D. Đối tượng resolver riêng cho từng scalar type.
Đáp án đúng: A

Câu 17. Trong Spring for GraphQL, `@QueryMapping` dùng để làm gì?
A. Ánh xạ phương thức vào field của root `Query`.
B. Khởi tạo DataLoader registry từ tên các field trong schema.
C. Ánh xạ phương thức vào root `Subscription`.
D. Ánh xạ field bên dưới object type bất kỳ.
Đáp án đúng: A

Câu 18. Trong Spring for GraphQL, `@SchemaMapping` dùng cho trường hợp nào?
A. Ánh xạ scalar GraphQL sang một Java enum.
B. Ánh xạ root `Query` theo đường dẫn HTTP của REST.
C. Ánh xạ GraphQL variable vào kết nối WebSocket.
D. Ánh xạ resolver vào field của một GraphQL object.
Đáp án đúng: D

Câu 19. `@BatchMapping` của Spring for GraphQL hỗ trợ cách xử lý nào?
A. Cấu hình quyền truy cập cho các field trong schema.
B. Khởi tạo schema từ nhiều file `.graphqls`.
C. Gộp việc lấy field cho nhiều source object.
D. Định tuyến subscription qua nhiều kết nối.
Đáp án đúng: C

Câu 20. `@MutationMapping` trong Spring for GraphQL ánh xạ tới đâu?
A. Argument của mutation trong header HTTP request.
B. Resolver cho field của root `Query` trong schema.
C. Publisher sự kiện cho field root `Subscription`.
D. Phương thức xử lý field của root `Mutation`.
Đáp án đúng: D

Câu 21. Phương thức Spring `@SubscriptionMapping` thường trả về gì để phát các bản cập nhật?
A. Một `Optional` được đọc lặp lại từng chu kỳ.
B. Luồng dữ liệu như `Flux` phát nhiều sự kiện.
C. `DataLoader` dùng chung cho mọi subscription.
D. Danh sách cố định trước khi client subscribe.
Đáp án đúng: B

Câu 22. Điểm khác nhau chính giữa GraphQL subscription và query thông thường là gì?
A. Subscription chỉ nhận sự kiện từ mutation của client.
B. Subscription có thể phát nhiều kết quả khi sự kiện tới.
C. Subscription chỉ có một response sau khi stream kết thúc.
D. Subscription yêu cầu client gửi lại query theo mỗi giây.
Đáp án đúng: B

Câu 23. Để phân trang cursor ổn định khi dữ liệu thay đổi, cách nào phù hợp nhất?
A. Luôn tải hết dữ liệu rồi chia trang tại client.
B. Dùng offset để bỏ qua số hàng đã tải trước.
C. Dùng cursor gắn với vị trí và thứ tự sắp xếp ổn định.
D. Dùng số lượng field để tính vị trí trang tiếp.
Đáp án đúng: C

Câu 24. Trong phân trang GraphQL theo kiểu Connection, `pageInfo` cung cấp gì?
A. Danh sách `edges` gồm node và cursor của từng cạnh.
B. `totalCount` của toàn bộ tập kết quả trong connection.
C. `hasNextPage` cùng cursor để tiếp tục phân trang.
D. Các argument `first`, `after` đã truyền khi gọi field.
Đáp án đúng: C

Câu 25. Với field GraphQL chứa dữ liệu nhạy cảm, biện pháp phân quyền nào phù hợp?
A. Kiểm tra token rồi cấp quyền truy cập mọi field.
B. Ẩn field khỏi tài liệu API cho người không có quyền.
C. Cho phép client dùng alias để lọc field khi truy vấn.
D. Kiểm tra quyền khi thực thi resolver của field đó.
Đáp án đúng: D

Câu 26. Để hạn chế truy vấn GraphQL phức tạp gây quá tải, nên áp dụng gì?
A. Đánh giá độ sâu và chi phí truy vấn rồi đặt ngưỡng.
B. Chỉ bật cache response chung cho mọi operation.
C. Chỉ giới hạn số HTTP request, bỏ qua chi phí truy vấn bên trong.
D. Chỉ giới hạn field ở root mà bỏ qua field lồng nhau.
Đáp án đúng: A

Câu 27. Server nên xử lý đối số `first` của phân trang Connection như thế nào để giới hạn tải?
A. Giới hạn `first` bằng số field trong truy vấn.
B. Giới hạn `first` tối đa theo cấu hình server.
C. Cho phép `first` tùy ý nếu user đăng nhập.
D. Cho phép `first` vô hạn vì đã dùng cursor.
Đáp án đúng: B

Câu 28. Bài kiểm thử nào phát hiện hiệu quả tình trạng N+1 trong GraphQL API?
A. Đếm truy vấn dữ liệu khi tăng số object cha.
B. Chỉ kiểm tra HTTP status của một query đơn.
C. Đếm số biến được khai báo trong GraphQL query.
D. Chỉ so kích thước schema trước và sau khi chạy.
Đáp án đúng: A
