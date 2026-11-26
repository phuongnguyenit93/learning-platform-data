Câu 1: Trong Prolog, cú pháp nào biểu diễn fact không điều kiện?
A. :- parent(mai,an). là directive chạy khi nạp chương trình.
B. ?- parent(mai,an). là khai báo một fact mới.
C. parent(mai,an) :- known(mai,an). là rule có điều kiện.
D. parent(mai,an). là fact không có điều kiện.
Đáp án đúng: D

Câu 2: Với truy vấn ?- parent(mai,X)., biến X có vai trò gì?
A. Tạo fact parent mới không kèm điều kiện.
B. Đổi tên predicate parent tại lúc thực thi.
C. Nhận giá trị sao cho quan hệ parent(mai,X) đúng.
D. Đếm tổng số fact parent có trong chương trình.
Đáp án đúng: C

Câu 3: Trong cú pháp Prolog thông thường, tên nào được hiểu là biến?
A. Person vì bắt đầu bằng ký tự viết hoa.
B. person vì bắt đầu bằng ký tự viết thường.
C. 'Person' vì nằm trong hai dấu nháy đơn.
D. person_name vì chứa dấu gạch dưới ở giữa.
Đáp án đúng: A

Câu 4: Rule grandparent(X,Z) :- parent(X,Y), parent(Y,Z). cần điều gì?
A. Y phải là hằng được khai báo từ trước.
B. Một Y làm cả hai quan hệ parent đều đúng.
C. Hai biến X và Z cần có giá trị trùng nhau.
D. Một trong hai quan hệ parent đúng là đủ.
Đáp án đúng: B

Câu 5: Trong thân rule Prolog, dấu phẩy giữa hai goal biểu diễn gì?
A. Hai goal đều phải thỏa theo phép hội logic.
B. Hai goal được phân phối cho hai thread khác nhau.
C. Goal trái bỏ qua khi goal phải thành công.
D. Một goal cần thỏa theo phép tuyển logic.
Đáp án đúng: A

Câu 6: Trong biểu thức (p(X) ; q(X)), dấu chấm phẩy mang nghĩa gì?
A. Hai nhánh được xét theo phép tuyển logic.
B. Cắt bỏ mọi nhánh trừ mục tiêu bên trái.
C. Hai mục tiêu phải thỏa theo phép hội logic.
D. So sánh số học giữa kết quả của p và q.
Đáp án đúng: A

Câu 7: Trong truy vấn edge(a,_), ký hiệu gạch dưới đơn có ý nghĩa gì?
A. Biến được chia sẻ ở mọi vị trí gạch dưới.
B. Hằng đặc biệt chỉ khớp với giá trị null.
C. Ký hiệu phủ định trực tiếp quan hệ edge.
D. Biến ẩn danh, không cần dùng lại giá trị đã khớp.
Đáp án đúng: D

Câu 8: Vì sao mỗi lần áp dụng một rule lại cần làm mới biến cục bộ của nó?
A. Không dùng chung binding của các lần gọi rule.
B. Đảm bảo rule chỉ có thể sinh đúng một nghiệm.
C. Cho phép các lần gọi sử dụng một biến toàn cục.
D. Ngăn mọi fact cũ tham gia quá trình suy diễn.
Đáp án đúng: A

Câu 9: Với hai fact color(red). và color(blue)., truy vấn color(X) có thể trả gì?
A. X phải đồng thời bằng red và blue trong một nghiệm.
B. Chỉ X=red và không được quay lui để tìm tiếp.
C. X=red rồi X=blue nếu yêu cầu thêm nghiệm.
D. Có thêm X=green nhờ suy diễn một màu mới.
Đáp án đúng: C

Câu 10: Rule reachable(X,Y) :- edge(X,Y). suy diễn kết quả nào?
A. Mỗi đỉnh cần có đúng một cạnh đi ra.
B. Mọi cặp đỉnh đều reachable dù không có edge.
C. Từ edge trực tiếp suy ra quan hệ reachable.
D. Có reachable thì tự thêm edge vào tập fact.
Đáp án đúng: C

Câu 11: Khi unification pair(X,2) với pair(1,Y), binding nào đúng?
A. X=2 và Y=2 do hằng 2 áp lên cả term.
B. X=1 và Y=1 do hai biến phải bằng nhau.
C. X=2 và Y=1 do hoán đổi vị trí đối số.
D. X=1 và Y=2 theo vị trí đối số tương ứng.
Đáp án đúng: D

Câu 12: Tại sao pair(X,X) = pair(1,2) thất bại trong unification?
A. Mọi đối số của hai term phải là biến.
B. Cùng biến X cần bằng hai hằng số khác nhau.
C. Functor pair không thể có hai đối số.
D. Toán tử = chỉ kiểm tra đồng nhất term.
Đáp án đúng: B

Câu 13: Với truy vấn ?- X = 2+3., Prolog gán X theo cách nào?
A. X nhận chuỗi có nội dung các ký tự 2+3.
B. X nhận số 5 sau khi biểu thức được tính.
C. X nhận term có cấu trúc phép cộng 2+3.
D. X thất bại vì dấu = không chấp nhận toán tử cộng.
Đáp án đúng: C

Câu 14: Với truy vấn ?- X is 2+3., kết quả của X là gì?
A. Truy vấn thất bại do is cần các biến tự do.
B. X=2+3 vì is chỉ hợp nhất cấu trúc term.
C. X=5 vì vế phải được đánh giá số học.
D. X=23 vì số được ghép theo dạng chuỗi.
Đáp án đúng: C

Câu 15: Trong Prolog, biểu thức 2 =:= 1+1 kiểm tra điều gì khi chạy?
A. Giá trị số học của hai biểu thức bằng nhau.
B. Hai vế có thể hợp nhất về cùng một term.
C. Hai vế là cùng một biến logic chưa gán.
D. Hai term có cấu trúc cú pháp giống nhau.
Đáp án đúng: A

Câu 16: Khi gọi X is Y+1 với Y chưa gán giá trị, điều gì thường xảy ra?
A. Y được hiểu là 0 nên X nhận giá trị 1.
B. X nhận term Y+1 rồi đợi đến lúc labeling.
C. Prolog sinh ra mọi số nguyên cho Y bằng backtracking.
D. Lỗi instantiation vì không thể tính biểu thức còn Y.
Đáp án đúng: D

Câu 17: Khi X và Y là hai biến tự do khác nhau, X == Y sẽ làm gì?
A. Gán cho cả X và Y một giá trị mặc định.
B. Hợp nhất X và Y thành một biến logic chung.
C. Hai biến khác nhau nên kiểm tra == thất bại.
D. Thành công vì cả hai biến đều chưa có giá trị.
Đáp án đúng: C

Câu 18: Với hai biến tự do X và Y, dấu = khác dấu == thế nào?
A. = tạo hai biến khác nhau; == tạo bản sao chung.
B. = hợp nhất biến; == kiểm tra term đồng nhất.
C. = cần biến đã gán; == tự tìm số cho biến.
D. = so sánh số học; == tính rồi gán biểu thức.
Đáp án đúng: B

Câu 19: Khi [H|T] = [a,b,c], kết quả unification nào là đúng?
A. H=c và T=[a,b] vì danh sách tự bị đảo.
B. H=a và T=[b,c] theo cấu trúc đầu–đuôi list.
C. H=[a,b] và T=c khi tách ở phần tử cuối.
D. H=a và T=b vì Prolog bỏ qua phần tử c.
Đáp án đúng: B

Câu 20: Với X tự do, unify_with_occurs_check(X,f(X)) sẽ làm gì?
A. Thành công vì occurs check bỏ qua chu trình.
B. Chuyển f(X) thành số để thực hiện so sánh.
C. Gán X=f(X) rồi xóa mọi chu kỳ term.
D. Không hợp nhất để ngăn X chứa chính X.
Đáp án đúng: D

Câu 21: Trong Prolog thông dụng, các goal trong thân rule được thử theo thứ tự nào?
A. Từ phải qua trái, kết hợp tìm kiếm theo chiều rộng.
B. Tự xếp các goal theo ước lượng chi phí mỗi lần.
C. Thực thi song song rồi giao các tập kết quả.
D. Từ trái qua phải, kết hợp tìm kiếm theo chiều sâu.
Đáp án đúng: D

Câu 22: Khi một goal thất bại sau các binding trước đó, backtracking làm gì?
A. Xóa mọi fact trong chương trình để chạy lại.
B. Hoàn tác binding nhánh đó rồi thử lựa chọn khác.
C. Giữ binding cũ để tái sử dụng ở các nghiệm sau.
D. Bỏ các goal còn lại và báo truy vấn thành công.
Đáp án đúng: B

Câu 23: Một predicate có nhiều clause; dấu ; khi hỏi thêm nghiệm gây hành vi nào?
A. Chèn một fact từ lời giải cũ vào chương trình.
B. Xóa các clause vừa xét trước khi tìm tiếp.
C. Khởi động một thread mới để chạy lại toàn bộ.
D. Quay lui tới các nhánh còn lựa chọn để tìm lời giải.
Đáp án đúng: D

Câu 24: Clause loop(X) :- loop(X). nằm trước base case có nguy cơ gì?
A. Đệ quy trái không kết thúc dưới DFS thông thường.
B. Chỉ tạo thêm nghiệm nhưng không ảnh hưởng tính dừng.
C. Được Prolog tự giới hạn thành một lần gọi.
D. Thành công ngay vì rule gọi đúng tên chính nó.
Đáp án đúng: A

Câu 25: Toán tử cut ! trong Prolog tác động gì đến quá trình tìm lời giải?
A. Tạo thêm nhánh để tìm lại các nghiệm đã bỏ.
B. Giới hạn các lựa chọn quay lui trong lời gọi.
C. Hợp nhất tất cả biến tự do với giá trị mặc định.
D. Đổi phép hội trong rule thành phép tuyển logic.
Đáp án đúng: B

Câu 26: Predicate once(Goal) thường được dùng để đạt điều gì?
A. Tạo fact mới từ mỗi lời giải của Goal.
B. Tự lặp Goal đến khi mọi fact được xóa.
C. Yêu cầu Goal trả tối thiểu hai nghiệm khác nhau.
D. Chỉ trả nghiệm đầu rồi dừng các nhánh khác.
Đáp án đúng: D

Câu 27: Nếu p(X) không có nghiệm, findall(X,p(X),L) xử lý ra sao?
A. Thành công với L=[] vì không thu được nghiệm nào.
B. Ném lỗi vì findall đòi hỏi phải có một nghiệm.
C. Thành công với L=[X] chứa một biến chưa gán.
D. Thất bại hoàn toàn giống truy vấn p(X) trực tiếp.
Đáp án đúng: A

Câu 28: Khác biệt quan trọng giữa setof/3 và findall/3 là gì?
A. Setof sắp xếp, loại trùng và nhóm biến tự do.
B. Findall chỉ xử lý số còn setof chỉ xử lý atom.
C. Findall luôn sắp xếp và loại bỏ phần tử trùng.
D. Setof giữ mọi phần tử trùng theo thứ tự gốc.
Đáp án đúng: A

Câu 29: Không dùng cut, đổi thứ tự clause trong Prolog có thể gây gì?
A. Khiến mọi nghiệm logic đúng biến thành sai hoàn toàn.
B. Chuyển tất cả predicate thành hàm tất định.
C. Không ảnh hưởng thứ tự nghiệm hoặc tính dừng.
D. Đổi thứ tự nghiệm hoặc tính kết thúc khi chạy DFS.
Đáp án đúng: D

Câu 30: Trong trace Prolog, sự kiện Redo thường cho biết điều gì?
A. Toàn bộ truy vấn kết thúc và không còn lời giải.
B. Hệ thống cắt mọi lựa chọn và không quay lui nữa.
C. Một biến được tự thêm thành fact trong chương trình.
D. Hệ thống quay lại một goal để thử suy diễn khác.
Đáp án đúng: D

Câu 31: Trong định nghĩa đệ quy ancestor/2, base case nào thường phù hợp?
A. parent(Y,X) để đảo chiều quan hệ tổ tiên.
B. X=Y để một người là tổ tiên của chính họ.
C. Base case là quan hệ parent(X,Y) trực tiếp.
D. ancestor(X,Y) tự gọi lại không cần điều kiện.
Đáp án đúng: C

Câu 32: Rule ancestor(X,Z) :- parent(X,Y), ancestor(Y,Z). thể hiện gì?
A. Chỉ thành công khi X và Z được hợp nhất.
B. Chỉ tìm parent trong đúng một thế hệ duy nhất.
C. Tiếp tục tìm tổ tiên qua mối quan hệ parent.
D. Ngăn việc tìm thêm thế hệ qua backtracking.
Đáp án đúng: C

Câu 33: Vì sao đệ quy duyệt đồ thị có chu trình có thể không kết thúc?
A. Thăm lại trạng thái nếu thiếu cơ chế kiểm soát chu trình.
B. Unification luôn tạo đỉnh mới ở mỗi bước đi.
C. Backtracking mặc định loại mọi lần thăm đỉnh cũ.
D. Mọi cạnh trở thành fact sai ngay sau lần gọi đầu.
Đáp án đúng: A

Câu 34: Với member(X,[red,blue]), yêu cầu các nghiệm liên tiếp sẽ cho kết quả nào?
A. X=[red,blue] do list là một term duy nhất.
B. X=red rồi X=blue nhờ backtracking.
C. Chỉ X=red vì member không thể quay lui.
D. X phải đồng thời là red và blue trong một nghiệm.
Đáp án đúng: B

Câu 35: Với length(L,3) và L chưa gán, Prolog thông dụng có thể làm gì?
A. Tạo list [3] vì 3 là phần tử duy nhất.
B. Dựng list gồm ba phần tử là các biến tự do.
C. Chỉ tính được length khi list đã được khởi tạo.
D. Gán cho mọi phần tử của list giá trị số 3.
Đáp án đúng: B

Câu 36: Difference list trong Prolog hỗ trợ tốt cho thao tác nào?
A. Sắp xếp list mà không cần bất kỳ phép so sánh.
B. Tự biến list thành một set không có phần tử trùng.
C. Ghép list hiệu quả nhờ một đuôi mở dùng chung.
D. Xóa mọi biến tự do khỏi list khi mới tạo.
Đáp án đúng: C

Câu 37: Tại sao predicate thuần không có side effect dễ suy luận hơn?
A. Ít phụ thuộc trạng thái ngoài và thứ tự chạy.
B. Mọi truy vấn thuần đều kết thúc trong thời gian hằng.
C. Predicate thuần không được dùng đệ quy hay unification.
D. Predicate thuần chỉ có một lời giải trong mọi trường hợp.
Đáp án đúng: A

Câu 38: Trong suy diễn Prolog, sử dụng assertz/1 tạo tác động nào?
A. Chỉ cập nhật một tham số cục bộ của predicate.
B. Biến toàn bộ rule đang chạy thành fact bất biến.
C. Cập nhật cơ sở clause động, sinh side effect.
D. Thay mọi phép unification bằng tính toán số học.
Đáp án đúng: C

Câu 39: Tabling giúp đệ quy nhiều subgoal lặp theo hướng nào?
A. Bắt mọi rule chỉ chạy một lần trong tất cả query.
B. Ghi nhớ lời giải subgoal để tránh tính toán lại.
C. Thay unification bằng phép so sánh đồng nhất.
D. Xóa các fact cũ trước lần backtracking kế tiếp.
Đáp án đúng: B

Câu 40: Trong Prolog, DCG (Definite Clause Grammar) thường dùng vào việc gì?
A. Mô tả ngữ pháp bằng rule và danh sách chênh lệch.
B. Thay unification bằng so sánh hằng trực tiếp.
C. Tự gửi truy vấn SQL trong quá trình suy diễn.
D. Tạo chỉ mục số học cho mọi predicate hai biến.
Đáp án đúng: A

Câu 41: Trong CLP(FD), X #= Y+1 khác X is Y+1 ở đặc điểm nào?
A. is suy diễn ngược miền số của mọi biến.
B. #= đặt ràng buộc ngay cả khi biến chưa gán số.
C. #= chỉ chạy khi mọi biến đã có giá trị số.
D. is chờ tới khi labeling mới đánh giá phép cộng.
Đáp án đúng: B

Câu 42: Trong CLP(FD), ràng buộc X in 1..9 thực hiện nhiệm vụ gì?
A. Buộc X bằng tổng của tất cả số từ 1 đến 9.
B. Gán X thành list chứa chín số nguyên liên tiếp.
C. Chọn ngay một số ngẫu nhiên cho X làm giá trị.
D. Giới hạn miền số nguyên X từ 1 đến 9.
Đáp án đúng: D

Câu 43: Sau khi khai báo các ràng buộc CLP(FD), labeling/2 có vai trò gì?
A. Chuyển biến chưa gán thành atom có tên cố định.
B. Loại toàn bộ ràng buộc trước lần truy vấn.
C. Thay propagation bằng các fact không có biến.
D. Tìm các giá trị cụ thể thỏa miền và ràng buộc.
Đáp án đúng: D

Câu 44: Trong CLP(FD), all_distinct([A,B,C]) yêu cầu điều gì?
A. Các biến nhận giá trị nguyên đôi một khác nhau.
B. Tổng ba giá trị luôn bằng số nguyên ba.
C. Các biến phải nhận cùng một giá trị nguyên.
D. Chỉ A và B cần khác nhau, còn C tùy ý.
Đáp án đúng: A

Câu 45: Khi X,Y còn tự do, dif(X,Y) thường được sử dụng nhằm gì?
A. Ràng buộc khác nhau được hoãn tới lúc gán.
B. Liệt kê mọi cặp số nguyên ngay khi được gọi.
C. Tính biểu thức X-Y rồi so với số không.
D. Tạo hai hằng ngẫu nhiên khác nhau cho biến.
Đáp án đúng: A

Câu 46: Propagation của CLP(FD) giúp hạn chế tìm kiếm nhờ đâu?
A. Xóa những ràng buộc khó để solver hoạt động nhanh.
B. Thu hẹp miền biến từ các điều kiện trước khi phân nhánh.
C. Tìm ngay nghiệm tối ưu dù không có hàm mục tiêu.
D. Loại mọi nhánh tìm kiếm cho mọi CSP hữu hạn.
Đáp án đúng: B

Câu 47: Trong Datalog dương, điều kiện an toàn với biến ở rule head là gì?
A. Mọi head bắt buộc có hai biến khác nhau.
B. Biến head chỉ xuất hiện trong atom phủ định.
C. Biến head có mặt trong atom dương của rule body.
D. Body không được có quan hệ cơ sở dữ liệu.
Đáp án đúng: C

Câu 48: Khi đánh giá bottom-up Datalog dương, solver dừng khi nào?
A. Chạy xong rule đầu tiên một lần là đủ.
B. Đạt fixed point, không sinh thêm fact mới.
C. Tìm thấy fact đầu tiên phù hợp câu truy vấn.
D. Mỗi quan hệ chỉ còn một tuple chưa xét.
Đáp án đúng: B

Câu 49: Semi-naive evaluation trong Datalog giảm việc tính lặp bằng cách nào?
A. Gộp mọi tuple thành một chuỗi để duyệt.
B. Dùng fact mới để tránh lặp phép join cũ.
C. Chọn ngẫu nhiên một tuple ở mỗi quan hệ.
D. Chỉ đánh giá rule đầu tiên, bỏ toàn bộ đệ quy.
Đáp án đúng: B

Câu 50: Trong Datalog có stratified negation, yêu cầu quan trọng nào đúng?
A. Mỗi quan hệ cần phủ định chính nó trong rule.
B. Rule luôn phải có một hàm dựng term trong body.
C. Không có chu trình phụ thuộc âm giữa các predicate.
D. Các vị từ phủ định bắt buộc đệ quy trực tiếp.
Đáp án đúng: C
