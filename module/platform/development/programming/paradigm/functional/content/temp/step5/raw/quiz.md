Câu 1. Một biểu thức có tính referential transparency khi nào?
A. Tính biểu thức nhiều lần sẽ tạo giá trị ngẫu nhiên khác.
B. Thay biểu thức bằng giá trị tương ứng mà không đổi hành vi quan sát.
C. Đổi thứ tự gọi hàm vẫn giữ thứ tự side effect cũ.
D. Thay kiểu dữ liệu đầu vào vẫn giữ nguyên mã thực thi.
Đáp án đúng: B

Câu 2. Trường hợp nào minh họa một pure function khi truyền cùng tham số?
A. Tính tổng tham số rồi ghi log ra thiết bị quan sát.
B. Tăng bộ đếm toàn cục rồi trả tổng tham số.
C. Tính tổng từ tham số mà không tạo side effect.
D. Đọc đồng hồ hệ thống để quyết định kết quả hàm.
Đáp án đúng: C

Câu 3. Vì sao hàm trả cùng kết quả với cùng đầu vào vẫn có thể không pure?
A. Hàm có thể cấp phát các biến local để tính toán kết quả.
B. Hàm có thể dùng kiểu trả về khác kiểu dữ liệu đầu vào.
C. Hàm có thể ghi log mà vẫn trả cùng kết quả.
D. Hàm có thể dùng một biểu thức đệ quy thay cho vòng lặp.
Đáp án đúng: C

Câu 4. Khi cập nhật persistent immutable list, hành vi nào phù hợp?
A. Phiên bản cũ tự thay đổi để phản ánh giá trị mới.
B. Phiên bản mới có thể chia sẻ các nút không đổi.
C. Mỗi cập nhật phải đặt lock trên toàn bộ các nút cũ.
D. Phải sao chép toàn bộ nút dữ liệu ở mỗi lần cập nhật.
Đáp án đúng: B

Câu 5. Một object có field final giữ tham chiếu tới List mutable; điều gì đúng?
A. Field final tự cấm các method chỉnh sửa trên List.
B. Field final làm mọi phần tử List trở nên bất biến sâu.
C. Field không gán lại nhưng List bên trong vẫn sửa được.
D. Field final tự sao chép List khi object được tạo.
Đáp án đúng: C

Câu 6. Trong mô hình pure core và imperative shell, trách nhiệm phù hợp của shell là gì?
A. Quản lý I/O rồi cung cấp dữ liệu cho phần tính toán thuần.
B. Thay phép tính thuần bằng callback với lịch chạy biến đổi.
C. Cho pure function ghi log và sửa dữ liệu chia sẻ.
D. Giấu lỗi đọc dữ liệu để pure core nhận giá trị cũ.
Đáp án đúng: A

Câu 7. Định nghĩa nào mô tả higher-order function?
A. Hàm gọi method của object mà không nhận hàm.
B. Hàm nhận một hàm làm đối số hoặc trả về một hàm.
C. Hàm nhận nhiều tham số nguyên thủy cùng kiểu số.
D. Hàm chạy trong nhiều thread và trả về một giá trị.
Đáp án đúng: B

Câu 8. Khi một hàm lọc nhận predicate do caller truyền, lợi ích thiết kế chính là gì?
A. Bảo đảm mọi điều kiện chạy cùng lúc trên nhiều CPU core.
B. Tách quy tắc chọn phần tử khỏi cơ chế duyệt tập dữ liệu.
C. Bỏ được bước kiểm tra kiểu dữ liệu đầu vào predicate.
D. Cho predicate sửa trạng thái ngoài mà không có nguy cơ race.
Đáp án đúng: B

Câu 9. Closure giữ điều gì mà một hàm không capture môi trường không giữ?
A. Các binding từ lexical scope ở thời điểm tạo closure.
B. Bản sao sâu của mọi object mà closure truy cập.
C. Toàn bộ kết quả của các lời gọi hàm sẽ chạy sau đó.
D. Toàn bộ stack của thread và mọi biến global tại lúc tạo.
Đáp án đúng: A

Câu 10. Khi closure capture tham chiếu tới object mutable, rủi ro nào có thể phát sinh?
A. Closure không thể được dùng sau khi lexical scope kết thúc.
B. Kết quả có thể đổi khi object capture bị sửa.
C. Compiler tự đóng băng object mutable tại thời điểm capture.
D. Object capture tự trở thành bản sao bất biến khi truyền.
Đáp án đúng: B

Câu 11. Với f(x)=x+2 và g(x)=x*3, kết quả của (f∘g)(4) là bao nhiêu?
A. 18 vì thực hiện f(4) rồi mới đưa giá trị vào g.
B. 12 vì tính g(4) xong sẽ bỏ qua phép gọi f.
C. 6 vì phép hợp thành chỉ tính f(4) rồi kết thúc.
D. 14 vì g(4) tạo 12, rồi f(12) tạo 14.
Đáp án đúng: D

Câu 12. Với f: B→C và g: A→B, hàm hợp thành f∘g có chữ ký nào?
A. A→C vì giá trị ra từ g là đầu vào cho f.
B. C→B vì thứ tự kiểu dữ liệu được đảo khi ghép.
C. A→B vì hợp thành không cần chạy hàm f.
D. B→A vì f được chạy trước khi thực hiện g.
Đáp án đúng: A

Câu 13. Partial application biến đổi hàm nhiều đối số theo cách nào?
A. Thực thi trước hàm rồi lưu lại giá trị trả về cuối.
B. Biến mọi hàm thành chuỗi hàm nhận đúng một đối số.
C. Ghép hai hàm độc lập thành một pipeline chạy nối tiếp.
D. Cố định vài đối số để nhận hàm còn thiếu đối số.
Đáp án đúng: D

Câu 14. Currying biến hàm hai đối số kiểu (A,B)→C thành dạng nào?
A. B→A, tức hàm đổi thứ tự hai kiểu đầu vào.
B. (A,B)→B, tức giữ nguyên chữ ký nhưng đổi kết quả.
C. A→C, tức loại bỏ hoàn toàn tham số thứ hai.
D. A→(B→C), tức chuỗi các hàm nhận một đối số.
Đáp án đúng: D

Câu 15. Một hàm đệ quy muốn kết thúc với đầu vào hữu hạn cần điều kiện nào?
A. Có base case và mỗi bước tiến gần trường hợp dừng.
B. Hàm phải chuyển thành generic trước khi tự gọi.
C. Mỗi lời gọi phải dùng đúng đầu vào của lần gọi trước.
D. Mỗi bước phải tạo hai nhánh đệ quy có cùng kết quả.
Đáp án đúng: A

Câu 16. Vì sao tail recursion không bảo đảm bộ nhớ stack O(1) trên mọi runtime?
A. Tối ưu tail call phụ thuộc ngôn ngữ và trình thực thi.
B. Mọi trình biên dịch đều chuyển đệ quy thành thread.
C. Tail recursion không được dùng với dữ liệu immutable.
D. Tail recursion tự sinh bản sao stack trước khi trả kết quả.
Đáp án đúng: A

Câu 17. Khi thuật toán đệ quy có nhiều bài toán con trùng nhau, kỹ thuật nào giảm tính toán lặp?
A. Tail recursion tự gộp mọi bài toán con cùng kích thước.
B. Memoization lưu kết quả bài toán con theo input.
C. Lazy evaluation bảo đảm tự bỏ mọi nhánh đã chạy trước.
D. Currying tự biến nhiều lời gọi đệ quy thành một.
Đáp án đúng: B

Câu 18. Trong fold, accumulator giữ vai trò gì?
A. Sao chép nguồn mỗi lần áp dụng một phép biến đổi.
B. Mang kết quả trung gian qua mỗi bước gộp dữ liệu.
C. Xác định lịch chạy thread ở mọi bước xử lý song song.
D. Biến mọi giá trị nguồn thành cùng một tham chiếu.
Đáp án đúng: B

Câu 19. Vì sao phép gộp của parallel fold nên có tính kết hợp?
A. Đổi cách chia nhóm tính toán không làm đổi kết quả.
B. Mọi phép gộp phải thực thi theo thứ tự trái sang phải.
C. Mọi giá trị trung gian phải là một immutable List.
D. Hàm gộp phải chạy trên thread đã tạo collection.
Đáp án đúng: A

Câu 20. API cần trả về thành công hoặc lỗi nghiệp vụ có chi tiết; kiểu trừu tượng nào phù hợp?
A. List<Value> đại diện một nhánh lỗi hoặc thành công.
B. Function<Error,Value> tự chứa dữ liệu hai trạng thái.
C. Option<Value> lưu đầy đủ chi tiết từng lỗi nghiệp vụ.
D. Either<Error,Value> mang nhánh lỗi hoặc thành công.
Đáp án đúng: D

Câu 21. Trong functional pipeline, map thường thực hiện điều gì?
A. Biến đổi từng giá trị thành kết quả ứng với nó.
B. Gộp toàn bộ tập phần tử thành một kết quả cuối.
C. Chỉnh sửa trực tiếp nguồn đầu vào để giữ nguyên bộ nhớ.
D. Lọc bỏ các phần tử không đạt điều kiện predicate.
Đáp án đúng: A

Câu 22. Trong functional pipeline, filter khác map chủ yếu ở điểm nào?
A. Đổi mỗi phần tử sang kiểu mới nhưng giữ số lượng.
B. Gộp các phần tử thành một giá trị tích lũy duy nhất.
C. Giữ phần tử thỏa predicate và có thể giảm số lượng.
D. Tạo nhiều phần tử đầu ra từ một phần tử đầu vào.
Đáp án đúng: C

Câu 23. Lazy evaluation mô tả chiến lược tính toán nào?
A. Hoãn mọi side effect đến sau khi chương trình kết thúc.
B. Tính biểu thức trên CPU khác ngay lúc được khai báo.
C. Hoãn tính biểu thức đến lúc kết quả thực sự được cần.
D. Tính trước toàn bộ biểu thức rồi lưu vào cache chung.
Đáp án đúng: C

Câu 24. Vì sao có thể lấy prefix hữu hạn của một lazy infinite sequence?
A. Dãy lazy không cần tính phần đuôi chưa được yêu cầu.
B. Nguồn vô hạn tự trở thành hữu hạn khi xây pipeline.
C. Các phần còn lại được tính hết trên background thread.
D. Mọi phần tử đã được lưu sẵn trước khi gọi take.
Đáp án đúng: A

Câu 25. Nếu biểu thức lazy có side effect bị đánh giá lại mà không memoize, điều gì có thể xảy ra?
A. Giá trị trả về tự trở thành immutable nên không đổi.
B. Compiler loại side effect khỏi mọi biểu thức lazy.
C. Side effect có thể được thực hiện lại ở lần đánh giá sau.
D. Runtime tự nhớ kết quả đầu dù không có cơ chế cache.
Đáp án đúng: C

Câu 26. Memoization phù hợp cho pure function với input ổn định bởi lý do nào?
A. Cache làm phép đọc thời gian thực trở thành pure function.
B. Cache dùng lại kết quả cùng input mà không đổi hành vi.
C. Bộ nhớ cache không cần giới hạn vì không phát sinh rò rỉ.
D. Mỗi lời gọi sau phải tạo kết quả mới khác kết quả cũ.
Đáp án đúng: B

Câu 27. Vì sao immutable values hữu ích khi nhiều worker đọc chung dữ liệu?
A. Ứng dụng không cần đồng bộ những tài nguyên mutable khác.
B. Mọi lời gọi đọc chung trở thành database transaction.
C. Không có worker khác sửa giá trị đã được chia sẻ.
D. Các phép ghi vào shared object tự được khóa nguyên tử.
Đáp án đúng: C

Câu 28. Trong mô hình Functor, map có vai trò gì?
A. Nhân đôi từng giá trị để tăng số phần tử trong context.
B. Chạy tác dụng phụ kể cả khi context không mang giá trị.
C. Bỏ toàn bộ context rồi chỉ trả một giá trị trần.
D. Áp dụng hàm lên giá trị mà giữ lại cấu trúc context.
Đáp án đúng: D

Câu 29. Luật identity của Functor phát biểu điều nào?
A. map(identity) làm context trở nên rỗng sau khi áp dụng.
B. map(identity) thay từng giá trị bằng phần tử mặc định.
C. map(identity) phải đảo thứ tự phần tử ở mọi cấu trúc.
D. map(identity) giữ nguyên Functor theo ngữ nghĩa.
Đáp án đúng: D

Câu 30. Luật composition của Functor với map(f) rồi map(g) tương đương điều gì?
A. map(f∘g), tức áp dụng g rồi mới áp dụng f.
B. map(f) rồi bỏ qua g để giữ kết quả bước đầu.
C. map(g∘f), tức áp dụng f rồi mới áp dụng g.
D. flatMap(g) dù g có kiểu kết quả không tương thích.
Đáp án đúng: C

Câu 31. Trong Monad, bind/flatMap khác map cơ bản ở điểm nào?
A. Bind bỏ context để thực thi theo thứ tự ngẫu nhiên.
B. Bind buộc mọi loại context phải chuyển thành một List.
C. Bind chỉ nhận hàm có giá trị trả về kiểu Boolean.
D. flatMap nhận hàm trả context rồi làm phẳng kết quả.
Đáp án đúng: D

Câu 32. Luật kết hợp của Monad diễn tả mối quan hệ nào với f và g?
A. m.flatMap(f).flatMap(g) tương đương m.flatMap(g).flatMap(f).
B. m.flatMap(f).flatMap(g) tương đương g(f(m)) không xét context.
C. m.flatMap(f) tương đương m dù f biến đổi giá trị của context.
D. m.flatMap(f).flatMap(g) tương đương m.flatMap(x -> f(x).flatMap(g)).
Đáp án đúng: D
