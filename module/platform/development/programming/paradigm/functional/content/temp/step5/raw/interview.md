Bạn giải thích tư duy lập trình hàm khác tư duy lập trình mệnh lệnh ở cách mô tả phép tính và thay đổi trạng thái như thế nào?
Bạn phân biệt functional programming như một mô hình lập trình với việc chỉ sử dụng lambda hoặc Stream API trong ngôn ngữ đa mô hình ra sao?
Bạn xác định những đặc điểm của một pure function và kiểm tra từng đặc điểm bằng ví dụ xử lý dữ liệu như thế nào?
Bạn giải thích khái niệm referential transparency và cách thay một lời gọi hàm bằng giá trị kết quả mà không đổi hành vi chương trình ra sao?
Bạn phân biệt pure function với một hàm chỉ có kết quả ổn định trong điều kiện môi trường hiện tại như thế nào?
Bạn phân tích vì sao một hàm đọc thời gian hệ thống có thể vi phạm tính thuần dù không ghi vào biến toàn cục ra sao?
Bạn đánh giá một hàm gọi random generator không được truyền qua đối số dưới góc nhìn tính xác định và referential transparency như thế nào?
Bạn thiết kế lại một phép tính phụ thuộc cấu hình toàn cục để biến dữ liệu đầu vào cần thiết thành tham số tường minh ra sao?
Bạn giải thích vì sao việc sửa phần tử của danh sách được truyền vào khiến một hàm không còn thuần ngay cả khi nó trả kết quả đúng như thế nào?
Bạn phân biệt local mutation không quan sát được từ bên ngoài với side effect làm thay đổi ngữ nghĩa chương trình như thế nào?
Bạn xác định những side effect nào có thể xuất hiện ngoài thao tác ghi file hoặc database, chẳng hạn log, exception hay thay đổi trạng thái chia sẻ?
Bạn phân tích vì sao tính thuần giúp đơn giản hóa việc suy luận về kết quả khi thứ tự gọi hàm thay đổi ra sao?
Bạn đánh giá khi nào một hàm có thể được memoize an toàn dựa trên đầu vào và những giả định cần kiểm chứng như thế nào?
Bạn giải thích quan hệ giữa pure function, deterministic computation và khả năng tái lập kết quả kiểm thử ra sao?
Bạn thiết kế một phần xử lý đơn hàng có lõi hàm thuần và lớp điều phối tác dụng phụ ở ranh giới hệ thống như thế nào?
Bạn lựa chọn cách biểu diễn lỗi tính toán thuần thay cho việc ghi log hoặc kết thúc tiến trình ngay trong hàm nghiệp vụ ra sao?
Bạn phân biệt ngoại lệ được mô tả trong hợp đồng hàm với tác dụng phụ khó quan sát trong một phép tính như thế nào?
Bạn phân tích rủi ro một hàm được xem là thuần nhưng đọc dữ liệu từ singleton mutable hoặc cache toàn cục ra sao?
Bạn kiểm chứng một phép biến đổi được cho là thuần bằng cách gọi lặp với cùng input và quan sát trạng thái bên ngoài như thế nào?
Bạn giải thích vì sao hàm thuần có thể giúp giảm nhu cầu đồng bộ hóa khi nhiều tác vụ cùng tính toán ra sao?
Bạn phân biệt bất biến của giá trị dữ liệu với việc cấm hoàn toàn mọi thao tác cấp phát hoặc tạo đối tượng mới như thế nào?
Bạn thiết kế một immutable value object có các trường liên quan mà không cho phép caller thay đổi trạng thái sau khi tạo ra sao?
Bạn phân tích vì sao một trường final giữ tham chiếu đến danh sách mutable chưa đủ bảo đảm bất biến sâu như thế nào?
Bạn lựa chọn defensive copy hoặc persistent collection để bảo vệ bất biến khi API nhận dữ liệu từ code không tin cậy ra sao?
Bạn giải thích structural sharing cho phép một persistent data structure tạo phiên bản mới mà không sao chép toàn bộ dữ liệu như thế nào?
Bạn so sánh chi phí cập nhật một persistent list với array-backed mutable list theo thời gian và bộ nhớ ra sao?
Bạn đánh giá lợi ích của persistent map khi ứng dụng cần lưu nhiều phiên bản trạng thái để undo hoặc audit như thế nào?
Bạn phân tích nguy cơ giữ tham chiếu đến nhiều phiên bản persistent collection khiến bộ nhớ không được giải phóng như mong đợi ra sao?
Bạn phân biệt immutable collection với read-only view trỏ tới dữ liệu gốc còn có thể bị sửa ra sao?
Bạn thiết kế cách trả về một bản trạng thái mới từ thao tác cập nhật thay vì sửa trực tiếp object đầu vào như thế nào?
Bạn giải thích vì sao value semantics khiến việc so sánh theo nội dung quan trọng hơn so sánh identity trong nhiều mô hình hàm ra sao?
Bạn phân tích vai trò của equality và hashing khi dùng immutable value làm key của map hoặc trong cache như thế nào?
Bạn lựa chọn cấu trúc dữ liệu bất biến hoặc mutable cục bộ khi thực hiện thuật toán cần hàng triệu lần cập nhật tạm thời như thế nào?
Bạn thiết kế một pipeline dùng mutable builder trong phạm vi nội bộ nhưng chỉ công bố kết quả bất biến ra ngoài như thế nào?
Bạn đánh giá tác động của immutable state lên snapshot consistency khi nhiều thread đọc phiên bản dữ liệu khác nhau ra sao?
Bạn giải thích vì sao quản lý trạng thái bằng các giá trị mới không tự động giải quyết xung đột cập nhật đồng thời vào cùng một reference ra sao?
Bạn lựa chọn atomic swap hoặc message passing để công bố phiên bản immutable state trong ứng dụng concurrent như thế nào?
Bạn phân biệt copy-on-write thông thường với persistent data structure theo mức tái sử dụng cấu trúc dữ liệu như thế nào?
Bạn thiết kế model sự kiện và state transition thuần để dựng lại trạng thái từ một chuỗi event ra sao?
Bạn xác định những rủi ro khi một đối tượng được cho là bất biến lại chứa lazy cache mutable không có bảo đảm thread safety như thế nào?
Bạn giải thích ý nghĩa của first-class function khi hàm có thể được truyền, trả về hoặc lưu trong cấu trúc dữ liệu ra sao?
Bạn phân biệt higher-order function với một method chỉ nhận đối tượng dữ liệu thông thường như thế nào?
Bạn thiết kế hàm bậc cao nhận một predicate để áp dụng cùng thuật toán lọc cho nhiều quy tắc nghiệp vụ ra sao?
Bạn mô tả cách hàm map biến đổi từng phần tử của một collection mà không buộc caller tự viết vòng lặp như thế nào?
Bạn phân biệt map với forEach theo việc tạo kết quả biến đổi hay thực hiện một hành động phụ như thế nào?
Bạn thiết kế phép filter trên danh sách bất biến mà không sửa dữ liệu gốc như thế nào?
Bạn lựa chọn flatMap khi một phần tử đầu vào có thể tạo ra không, một hoặc nhiều kết quả như thế nào?
Bạn giải thích vai trò của fold trong việc gom một cấu trúc dữ liệu bằng accumulator và phép kết hợp như thế nào?
Bạn phân biệt foldLeft với foldRight theo thứ tự duyệt, tính kết hợp và tác động lên kết quả như thế nào?
Bạn thiết kế phép fold tính tổng và đếm phần tử cùng lúc mà không duyệt dữ liệu nhiều lần ra sao?
Bạn phân biệt phép reduce không có giá trị khởi tạo với fold có identity khi collection rỗng theo những điều kiện nào?
Bạn xác định những điều kiện về associativity, identity và cách gộp accumulator để fold song song bảo toàn ngữ nghĩa như thế nào?
Bạn đánh giá ảnh hưởng của tính không kết hợp hoàn toàn của số thực dấu phẩy động đến kết quả reduce song song như thế nào?
Bạn lựa chọn map, filter, fold hay vòng lặp khi thuật toán yêu cầu dừng sớm và phải giữ tính dễ đọc ra sao?
Bạn phân biệt scan với fold theo việc phát các giá trị tích lũy trung gian và chỉ trả kết quả cuối cùng như thế nào?
Bạn thiết kế phép groupBy rồi tổng hợp để xử lý đơn hàng theo khách hàng và đánh giá chi phí lưu nhóm như thế nào?
Bạn mô tả vai trò của zip khi ghép hai chuỗi giá trị theo vị trí và trường hợp độ dài không khớp ra sao?
Bạn phân biệt zip với Cartesian product khi tổ hợp phần tử của hai collection theo yêu cầu nghiệp vụ như thế nào?
Bạn sử dụng partition theo predicate để chia dữ liệu thành hai nhóm mà không lặp lại logic kiểm tra như thế nào?
Bạn giải thích vì sao tính toán dựa trên hàm bậc cao có thể trừu tượng hóa cơ chế duyệt dữ liệu mà vẫn giữ ý nghĩa thuật toán ra sao?
Bạn đánh giá rủi ro đặt logic nhiều bước vào một lambda quá dài so với tách thành những hàm nhỏ có tên như thế nào?
Bạn thiết kế API biến đổi có tham số là một hàm nhưng vẫn thể hiện rõ hợp đồng về side effect và exception ra sao?
Bạn giải thích function composition và cách dùng kết quả của một hàm làm đầu vào của hàm tiếp theo như thế nào?
Bạn phân biệt thứ tự áp dụng f sau g với g sau f khi hai hàm có kiểu đầu vào và đầu ra tương thích ra sao?
Bạn xây dựng một pipeline chuẩn hóa dữ liệu từ các hàm nhỏ mà mỗi bước có một trách nhiệm rõ ràng như thế nào?
Bạn phân tích vì sao composition cho phép thay thế một bước xử lý mà không cần biết chi tiết những bước còn lại ra sao?
Bạn giải thích tính kết hợp của phép hợp thành hàm và ý nghĩa đối với cách nhóm các bước trong pipeline như thế nào?
Bạn mô tả identity function và kiểm chứng vai trò phần tử trung hòa của nó trong composition ra sao?
Bạn thiết kế kiểm thử cho ba hàm hợp thành bằng cách so sánh các cách nhóm ngoặc của cùng phép hợp thành như thế nào?
Bạn xác định những điều kiện khiến việc đổi thứ tự các phép biến đổi không còn hợp lệ dù từng phép đều thuần như thế nào?
Bạn phân biệt function composition với pipeline có side effect và phụ thuộc thứ tự thực thi ra sao?
Bạn lựa chọn composition, decorator hoặc middleware khi cần bổ sung validation và logging quanh một phép xử lý như thế nào?
Bạn giải thích currying biến một hàm nhiều tham số thành chuỗi các hàm một tham số như thế nào?
Bạn phân biệt currying với partial application bằng ví dụ cố định trước một tham số cấu hình như thế nào?
Bạn thiết kế hàm tính chiết khấu được tham số hóa theo chính sách để tái sử dụng bằng partial application ra sao?
Bạn giải thích cách một hàm được trả về tạo closure và giữ những giá trị cần thiết từ môi trường khai báo ra sao?
Bạn giải thích cách lexical scope xác định các biến được closure tham chiếu dù hàm bao quanh đã kết thúc ra sao?
Bạn phân tích rủi ro closure bắt giữ một đối tượng mutable làm hành vi callback phụ thuộc trạng thái tại thời điểm gọi như thế nào?
Bạn đánh giá nguy cơ giữ tài nguyên lớn trong bộ nhớ vì closure còn tham chiếu đến object không cần thiết ra sao?
Bạn thiết kế một factory trả về function với cấu hình bất biến để phục vụ nhiều request đồng thời như thế nào?
Bạn phân biệt việc truyền tham số tường minh với closure capture trong yêu cầu kiểm thử và quan sát dependency như thế nào?
Bạn lựa chọn point-free style hoặc tham số có tên khi cần cân bằng tính gọn và khả năng đọc hiểu của mã ra sao?
Bạn giải thích vai trò của recursion khi định nghĩa phép tính dựa trên các bài toán con cùng cấu trúc như thế nào?
Bạn xác định base case và recursive case để chứng minh một hàm đệ quy sẽ kết thúc với input hữu hạn ra sao?
Bạn thiết kế hàm duyệt cây nhị phân bằng pattern matching và recursion mà không dùng trạng thái mutable toàn cục như thế nào?
Bạn phân biệt recursion tuyến tính với tree recursion theo số lời gọi và độ sâu call stack ra sao?
Bạn phân tích vì sao Fibonacci đệ quy trực tiếp có thể lặp nhiều phép tính dù mã rất gần định nghĩa toán học như thế nào?
Bạn sử dụng memoization để tránh tính lại bài toán con và xác định điều kiện cache key hợp lệ ra sao?
Bạn phân biệt memoization với dynamic programming theo cách tổ chức trạng thái và thứ tự tính toán như thế nào?
Bạn giải thích tail recursion và điều kiện để lời gọi đệ quy nằm ở vị trí cuối cùng của hàm ra sao?
Bạn phân tích tác động của tail-call optimization đến stack usage và vì sao không thể mặc định mọi runtime đều hỗ trợ như thế nào?
Bạn thiết kế lại một phép đệ quy dùng accumulator theo dạng tail-recursive nhưng vẫn bảo toàn kết quả như thế nào?
Bạn lựa chọn vòng lặp hoặc explicit stack thay cho recursion sâu khi phải kiểm soát giới hạn call stack theo những tiêu chí nào?
Bạn giải thích cách trampoline có thể biểu diễn các bước đệ quy kế tiếp dưới dạng giá trị chờ chạy nhằm giảm sử dụng call stack ra sao?
Bạn thiết kế phép đệ quy qua một cây có thể rất sâu mà vẫn kiểm soát bộ nhớ và tránh lưu toàn bộ kết quả trung gian như thế nào?
Bạn phân biệt structural recursion và recursion phụ thuộc điều kiện dữ liệu động khi chứng minh tính kết thúc như thế nào?
Bạn xác định độ phức tạp thời gian và bộ nhớ của một fold trên danh sách so với recursion thủ công như thế nào?
Bạn phân tích khả năng xử lý một cấu trúc chu trình bằng recursion khi đầu vào không bảo đảm là cây như thế nào?
Bạn thiết kế kiểm thử property-based cho hàm đệ quy bằng cách so sánh với một triển khai tham chiếu trên input nhỏ như thế nào?
Bạn giải thích lazy evaluation và sự khác biệt với eager evaluation về thời điểm biểu thức được tính như thế nào?
Bạn phân biệt call-by-name và call-by-need theo việc một biểu thức bị đánh giá lại hay ghi nhớ kết quả ra sao?
Bạn giải thích vì sao một lazy stream chỉ xử lý các phần tử được demand thay vì luôn tạo toàn bộ danh sách như thế nào?
Bạn thiết kế pipeline trên chuỗi vô hạn có điều kiện dừng để trả về một số lượng kết quả hữu hạn ra sao?
Bạn phân tích nguy cơ treo chương trình khi một phép toán eager yêu cầu xử lý toàn bộ dữ liệu của một nguồn vô hạn như thế nào?
Bạn phân biệt lazy collection view với một danh sách đã materialize khi dữ liệu nguồn còn có thể thay đổi như thế nào?
Bạn giải thích vì sao deferred computation có thể làm exception xuất hiện muộn hơn vị trí tạo pipeline ra sao?
Bạn thiết kế cách ghi log và đo thời gian cho một pipeline lazy mà không làm thay đổi tính toán hoặc kích hoạt nó sớm ngoài ý muốn như thế nào?
Bạn phân tích rủi ro nhúng side effect vào phép biến đổi lazy khi framework có thể không đánh giá mọi phần tử như thế nào?
Bạn lựa chọn strict evaluation cho bước xác thực đầu vào và lazy evaluation cho bước biến đổi tốn kém theo những tiêu chí nào?
Bạn giải thích cách memoize một giá trị lazy thay đổi đặc tính thời gian và lượng bộ nhớ được giữ lại như thế nào?
Bạn phân tích hiện tượng space leak khi một lazy computation giữ tham chiếu đến phần đầu của stream lớn không còn cần dùng ra sao?
Bạn đánh giá tình huống lazy evaluation tạo nhiều thunk chưa được đánh giá khiến heap tăng khi producer nhanh hơn consumer như thế nào?
Bạn thiết kế cách xử lý tài nguyên file hoặc connection trong pipeline lazy để không đóng trước khi tiêu thụ hoặc giữ mở quá lâu như thế nào?
Bạn phân biệt lazy evaluation với asynchronous execution và giải thích vì sao một phép tính lazy vẫn có thể chạy đồng bộ ra sao?
Bạn giải thích cách short-circuit operation tận dụng lazy evaluation để không xử lý các phần tử không cần thiết như thế nào?
Bạn kiểm thử một phép biến đổi lazy để xác định số lần hàm ánh xạ được gọi khi consumer dừng sớm như thế nào?
Bạn phân tích việc đánh giá lazy expression từ nhiều thread có thể yêu cầu cơ chế đồng bộ khi cache kết quả ra sao?
Bạn lựa chọn eager materialization ở ranh giới API khi caller cần snapshot ổn định thay vì một view phụ thuộc nguồn như thế nào?
Bạn giải thích algebraic data type và vai trò của product type với sum type trong mô hình hóa trạng thái như thế nào?
Bạn phân biệt product type có nhiều trường đồng thời với sum type có nhiều biến thể loại trừ nhau như thế nào?
Bạn thiết kế kiểu biểu diễn kết quả thanh toán thành success, declined và error mà tránh các tổ hợp field vô nghĩa ra sao?
Bạn giải thích cách tagged union hoặc sealed hierarchy giúp compiler kiểm tra các biến thể dữ liệu hợp lệ như thế nào?
Bạn dùng pattern matching để xử lý các biến thể của sum type và nhận diện nhánh chưa được bao phủ ra sao?
Bạn phân biệt exhaustiveness checking với một nhánh default rộng có thể che giấu biến thể mới như thế nào?
Bạn thiết kế kiểu Option hoặc Maybe khi dữ liệu có thể không tồn tại và phân biệt với trường hợp giá trị null hợp lệ ra sao?
Bạn giải thích cách Option.map cho phép biến đổi giá trị có mặt mà không làm mất trường hợp rỗng ra sao?
Bạn phân biệt kiểu Either chứa lỗi hoặc giá trị với Option chỉ thể hiện có hoặc không có giá trị như thế nào?
Bạn thiết kế hàm parse trả về Result hoặc Either chứa lỗi có cấu trúc thay vì ném exception cho lỗi dữ liệu dự kiến ra sao?
Bạn giải thích vì sao một sum type giúp thể hiện các trạng thái lỗi có thể kiểm soát ngay trong chữ ký hàm như thế nào?
Bạn phân biệt validation tích lũy nhiều lỗi độc lập với chuỗi tính toán dừng tại lỗi đầu tiên như thế nào?
Bạn thiết kế cách kết hợp kết quả xác thực nhiều field để hiển thị đầy đủ lỗi cho người dùng ra sao?
Bạn phân tích rủi ro tạo một dữ liệu có quá nhiều trường nullable thay cho các biến thể cụ thể của sum type như thế nào?
Bạn giải thích higher-kinded abstraction ở mức khái niệm và lý do khó biểu diễn trực tiếp trong một số hệ thống kiểu như thế nào?
Bạn phân biệt parametric polymorphism với subtype polymorphism khi thiết kế một API biến đổi collection theo kiểu tổng quát ra sao?
Bạn giải thích vì sao tính tham số hóa có thể hỗ trợ suy luận rằng một hàm generic không thể tùy ý tạo giá trị thuộc kiểu chưa biết như thế nào?
Bạn kiểm tra hợp đồng generic type bằng các tính chất có thể suy ra từ kiểu tham số và kiểu trả về như thế nào?
Bạn giải thích Functor như một cấu trúc có phép map giữ nguyên dạng ngữ cảnh trong khi biến đổi giá trị bên trong ra sao?
Bạn mô tả cách List, Option hoặc một container có ngữ cảnh có thể được nhìn dưới góc độ Functor như thế nào?
Bạn giải thích luật identity của Functor và cách kiểm chứng việc map hàm đồng nhất không đổi cấu trúc ra sao?
Bạn giải thích luật composition của Functor và sự tương đương giữa hai lần map liên tiếp với map hàm hợp thành như thế nào?
Bạn thiết kế property-based test để kiểm tra hai luật Functor cho một cấu trúc dữ liệu tự định nghĩa ra sao?
Bạn phân tích tác động của side effect trong hàm được map đến khả năng quan sát các luật Functor như thế nào?
Bạn phân biệt map giữ nguyên ngữ cảnh với flatMap có thể thay đổi cách lồng ngữ cảnh như thế nào?
Bạn thiết kế một kiểu container biểu diễn giá trị kèm metadata và xác định map phải bảo toàn metadata như thế nào?
Bạn giải thích Applicative ở mức khái niệm và khả năng áp dụng một hàm nằm trong ngữ cảnh lên giá trị cũng nằm trong ngữ cảnh như thế nào?
Bạn phân biệt Applicative với Monad theo khả năng kết hợp các phép tính độc lập và có phụ thuộc kết quả trước như thế nào?
Bạn thiết kế validation của nhiều trường độc lập bằng phong cách applicative để tích lũy lỗi thay vì dừng sớm ra sao?
Bạn mô tả vai trò của pure và apply trong Applicative khi đưa giá trị thông thường vào ngữ cảnh và áp dụng hàm ra sao?
Bạn giải thích vì sao mô hình Applicative có thể biểu lộ các phép tính độc lập phù hợp để thực hiện song song như thế nào?
Bạn đánh giá điều kiện cần kiểm chứng trước khi thực thi song song hai phép tính applicative có thể có side effect ra sao?
Bạn giải thích Monad như một mô hình hợp thành các phép tính mà bước kế tiếp có thể phụ thuộc giá trị bên trong ngữ cảnh như thế nào?
Bạn phân biệt map, flatMap hoặc bind và flatten bằng một ví dụ trả về Option lồng nhau như thế nào?
Bạn giải thích vai trò của unit hoặc return trong Monad khi đưa một giá trị thường vào ngữ cảnh như thế nào?
Bạn mô tả luật left identity của Monad và cách nó ràng buộc unit với bind ra sao?
Bạn mô tả luật right identity của Monad và lý do bind với unit không được thay đổi một phép tính ra sao?
Bạn giải thích luật associativity của Monad và ý nghĩa của cách nhóm các bước bind liên tiếp như thế nào?
Bạn thiết kế property-based test kiểm tra ba luật Monad cho một kiểu dữ liệu có constructor và bind do bạn định nghĩa ra sao?
Bạn phân tích vì sao một kiểu có method tên flatMap chưa đủ để khẳng định nó là Monad nếu các luật hợp thành không được thỏa mãn ra sao?
Bạn giải thích cách Option hoặc Maybe thể hiện việc dừng chuỗi tính toán khi một bước không có giá trị như thế nào?
Bạn thiết kế chuỗi xử lý Either để chuyển lỗi có cấu trúc qua nhiều bước phụ thuộc mà không làm mất bối cảnh ra sao?
Bạn phân biệt cách một Future-like Monad mô hình hóa kết quả bất đồng bộ với cách Option mô hình hóa giá trị có thể vắng mặt như thế nào?
Bạn đánh giá giới hạn của giả định Future hoặc Promise luôn thỏa các luật Monad khi có side effect, cancellation và cách triển khai cụ thể ra sao?
Bạn giải thích do-notation hoặc cú pháp tương tự giúp trình bày chuỗi bind trông như mã tuần tự nhưng vẫn giữ ngữ nghĩa ngữ cảnh như thế nào?
Bạn thiết kế một chuỗi thao tác có thể thất bại theo phong cách Monad và so sánh khả năng đọc với if-else lồng nhau ra sao?
Bạn phân biệt phép hợp thành các hàm thông thường với Kleisli composition khi mỗi hàm trả về một giá trị trong ngữ cảnh như thế nào?
Bạn xây dựng pipeline Kleisli cho các bước validate, parse và tra cứu dữ liệu có thể thất bại ra sao?
Bạn phân tích khi nào lồng nhiều lớp ngữ cảnh như Option của Future khiến xử lý khó đọc và cần cấu trúc hợp thành khác như thế nào?
Bạn giải thích vai trò của Traverse khi biến một cấu trúc chứa các phép tính có ngữ cảnh thành một phép tính cho cả cấu trúc như thế nào?
Bạn thiết kế thao tác traverse danh sách dữ liệu cần validation và xác định chiến lược xử lý khi có phần tử không hợp lệ ra sao?
Bạn phân biệt sequence với traverse trong việc hoán đổi cấu trúc và ngữ cảnh tính toán ra sao?
Bạn đánh giá mức cần thiết của các abstraction Functor, Applicative và Monad so với dùng phép toán thông thường trong một nhóm phát triển ra sao?
Bạn giải thích vì sao mô hình hóa side effect là giá trị mô tả thao tác có thể giúp tách lúc xây dựng chương trình với lúc thực thi như thế nào?
Bạn phân biệt mô tả một thao tác I/O chưa chạy với thực hiện I/O ngay khi lời gọi hàm được đánh giá ra sao?
Bạn thiết kế một lớp effect boundary nhận input, thực hiện truy cập dữ liệu và đưa kết quả về lõi nghiệp vụ thuần như thế nào?
Bạn mô tả cách Reader abstraction có thể truyền một môi trường cấu hình qua nhiều hàm mà không dùng biến toàn cục ra sao?
Bạn phân biệt Reader với dependency injection thông thường theo cách biểu diễn môi trường và hợp thành phép tính như thế nào?
Bạn giải thích State abstraction mô hình hóa chuyển trạng thái bằng hàm nhận state và trả về giá trị cùng state mới ra sao?
Bạn thiết kế một state transition thuần cho bộ đếm hoặc giỏ hàng và kiểm chứng invariant sau mỗi bước như thế nào?
Bạn so sánh State abstraction với việc sửa shared mutable object dưới lock theo khả năng suy luận và kiểm thử như thế nào?
Bạn mô tả Writer abstraction và cách tích lũy thông tin phụ trợ mà không ghi log trực tiếp trong hàm nghiệp vụ như thế nào?
Bạn đánh giá rủi ro dùng Writer để gom một lượng log không giới hạn trong bộ nhớ khi xử lý luồng dữ liệu lớn ra sao?
Bạn phân biệt error effect với exception được ném ngay ở runtime về khả năng kiểm soát nhánh thất bại trong kiểu dữ liệu ra sao?
Bạn thiết kế cơ chế quản lý tài nguyên mở file, sử dụng và đóng có xử lý lỗi ở cả bước chính lẫn cleanup như thế nào?
Bạn giải thích vì sao lazy effect phải đi kèm chiến lược quản lý vòng đời tài nguyên để tránh leak khi tác vụ không được chạy như thế nào?
Bạn phân tích cancellation và interruption ảnh hưởng đến các effect gồm nhiều bước và cleanup bắt buộc ra sao?
Bạn lựa chọn transactional boundary cho chuỗi side effect khi một bước đã ghi dữ liệu nhưng bước tiếp theo thất bại như thế nào?
Bạn thiết kế retry cho effect có thể thất bại mà không vô tình lặp một side effect không idempotent ra sao?
Bạn phân biệt idempotency của phép biến đổi thuần với idempotency của lời gọi API hoặc database có side effect như thế nào?
Bạn đánh giá tradeoff khi dùng một effect system tường minh trong ngôn ngữ không có hỗ trợ native về mặt độ rõ ràng và chi phí trừu tượng ra sao?
Bạn thiết kế cách phân loại effect về đọc cấu hình, ghi log, gọi mạng và cập nhật dữ liệu để review mã dễ dàng hơn như thế nào?
Bạn xác định điểm nào trong kiến trúc cần chuyển từ mô tả effect sang interpreter hoặc runtime thực thi cụ thể ra sao?
Bạn giải thích vì sao functional core và imperative shell có thể cùng tồn tại trong một ứng dụng hướng đối tượng như thế nào?
Bạn thiết kế hệ thống xử lý yêu cầu HTTP giữ validation và tính toán trong functional core nhưng thực hiện I/O trong shell ra sao?
Bạn phân biệt dependency injection ở ranh giới với việc truyền trực tiếp một service mutable vào từng hàm nghiệp vụ như thế nào?
Bạn lựa chọn domain model bất biến hay entity mutable khi nghiệp vụ có nhiều quy tắc cập nhật và tích hợp ORM như thế nào?
Bạn đánh giá ảnh hưởng của bất biến đến chi phí tạo object, pressure lên GC và khả năng tối ưu của runtime như thế nào?
Bạn phân tích trường hợp chuỗi map và filter tạo nhiều giá trị trung gian và cách giảm allocation mà không mất tính rõ ràng ra sao?
Bạn so sánh pipeline lazy với materialized collection khi dữ liệu được tiêu thụ nhiều lần và cần snapshot ổn định như thế nào?
Bạn lựa chọn persistent data structure hay mutable builder tạm thời để cân bằng hiệu năng và tính đúng đắn của API ra sao?
Bạn giải thích vì sao referential transparency hỗ trợ cache, parallel execution và kiểm thử nhưng không tự tạo ra hiệu năng tốt hơn như thế nào?
Bạn phân tích giới hạn của tự động song song hóa khi một fold không có phép kết hợp có tính associative như thế nào?
Bạn thiết kế phép xử lý batch song song bằng các pure transformations rồi gộp kết quả có tính deterministic như thế nào?
Bạn phân biệt concurrency safety của immutable input với việc callback có thể ghi vào database hoặc log từ nhiều thread như thế nào?
Bạn lựa chọn nơi xử lý lỗi và retry khi một pipeline functional được triển khai trên nhiều service và mạng có thể thất bại như thế nào?
Bạn đánh giá độ phức tạp mà các generic abstraction sâu có thể tạo ra cho đội ngũ chưa quen với lý thuyết kiểu như thế nào?
Bạn phân tích cách dùng kiểu dữ liệu để biểu đạt invariant có thể giảm số nhánh kiểm tra runtime trong code như thế nào?
Bạn thiết kế chiến lược refactor một phương thức dài có nhiều biến mutable thành các transformation có đầu vào và đầu ra rõ ràng ra sao?
Bạn giải thích lợi ích của unit test cho pure function khi không cần mock đồng hồ, network hoặc database như thế nào?
Bạn thiết kế property-based test cho hàm sắp xếp hoặc chuẩn hóa thay vì chỉ kiểm thử vài ví dụ đầu vào cố định ra sao?
Bạn lựa chọn những algebraic laws nào để kiểm chứng phép hợp thành hoặc fold do thư viện nội bộ triển khai?
Bạn phân tích lý do equality của giá trị dấu phẩy động hoặc thứ tự kết hợp phép tính có thể làm property test thất bại ra sao?
Bạn xây dựng bộ sinh dữ liệu đầu vào có cấu trúc và shrinker để tìm một phản ví dụ nhỏ khi property test thất bại như thế nào?
Bạn phân biệt example-based test, property-based test và model-based test khi kiểm chứng một state transition thuần ra sao?
Bạn thiết kế kiểm thử so sánh kết quả giữa phiên bản imperative ban đầu và phiên bản functional sau refactor như thế nào?
Bạn đánh giá cách đo benchmark cho hàm hợp thành mà tránh constant folding và dead-code elimination làm sai kết quả như thế nào?
Bạn xác định dấu hiệu space leak trong một pipeline lazy qua heap profiling và object retention graph như thế nào?
Bạn lựa chọn tracing hoặc logging ở effect boundary để theo dõi pipeline mà không làm mỗi pure function phụ thuộc logger như thế nào?
Bạn phân tích ảnh hưởng của một chuỗi function composition quá sâu tới stack trace và khả năng xác định bước gây lỗi ra sao?
Bạn thiết kế tiêu chí code review cho một hàm khai báo là pure nhưng nhận dependency có thể thay đổi giữa các lần gọi như thế nào?
Bạn giải thích vì sao sử dụng functional programming không loại bỏ nhu cầu hiểu thuật toán, độ phức tạp và hiệu ứng hệ thống như thế nào?
Một hàm tính giá đơn hàng đọc tỷ giá từ biến global nên đôi lúc trả kết quả khác cho cùng input, bạn sẽ thiết kế lại chữ ký như thế nào?
Một object immutable chứa List mutable bị thay đổi sau khi lưu vào cache, bạn sẽ phân tích giới hạn bất biến và sửa API ra sao?
Một phép reduce chạy đúng tuần tự nhưng sai khi chạy song song do accumulator không kết hợp được, bạn sẽ tìm lỗi và thiết kế lại như thế nào?
Một pipeline lazy chỉ báo exception khi consumer bắt đầu đọc dữ liệu, bạn sẽ xác định điểm đánh giá và thiết kế xử lý lỗi ra sao?
Một phép memoization khiến ứng dụng giữ quá nhiều trạng thái lịch sử, bạn sẽ đánh giá chiến lược cache key và eviction như thế nào?
Một hàm đệ quy duyệt cây rất sâu bị stack overflow trên runtime không hỗ trợ tail-call optimization, bạn sẽ thay đổi thuật toán như thế nào?
Một chương trình dùng Either nhưng toàn bộ lỗi bị chuyển thành một chuỗi chung làm mất nguyên nhân, bạn sẽ thiết kế error type như thế nào?
Một nhóm tạo kiểu dữ liệu có method flatMap nhưng vi phạm luật associativity, bạn sẽ thiết kế phép thử và điều chỉnh semantics ra sao?
Một chuỗi effect được retry sau timeout làm ghi trùng thanh toán, bạn sẽ bố trí idempotency và effect boundary như thế nào?
Một kiến trúc áp dụng Monad cho mọi phương thức khiến code khó onboarding, bạn sẽ chọn lại mức abstraction theo tiêu chí nào?
Bạn xây dựng checklist review lập trình hàm dựa trên purity, immutability, composition, recursion, laziness, lawfulness, effect isolation và tradeoff như thế nào?
