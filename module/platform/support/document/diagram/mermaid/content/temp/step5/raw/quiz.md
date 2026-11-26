Trong tài liệu Markdown, cách nào giúp công cụ hỗ trợ Mermaid nhận diện nguồn sơ đồ?
A. Đặt mã sơ đồ trong fenced code block có nhãn ngôn ngữ mermaid
B. Đưa mô tả vào đoạn văn thường và thêm hậu tố .svg ở cuối dòng
C. Lưu cú pháp vào bảng Markdown và không khai báo ngôn ngữ của bảng
D. Đặt mã trong chú thích HTML và mong trình xem tự nhận dạng sơ đồ
Đáp án đúng: A

Muốn vẽ luồng xử lý từ trên xuống trong Mermaid, khai báo mở đầu nào thích hợp?
A. Khai báo sequenceDiagram rồi đặt các thông điệp theo thứ tự thời gian
B. Khai báo flowchart TD rồi định nghĩa các nút và cạnh liên kết
C. Khai báo erDiagram rồi đặt các thực thể quan hệ trong một sơ đồ
D. Khai báo gantt rồi đặt các công việc theo lịch và ngày bắt đầu
Đáp án đúng: B

Khi muốn luồng xử lý chạy từ trái sang phải, nên đổi phần nào?
A. Đổi tên mọi node thành các giá trị số tăng dần từ trái sang phải
B. Đổi nhãn hiển thị của cạnh nhưng giữ nguyên hướng flowchart
C. Đổi loại sơ đồ thành classDiagram mà không đổi quan hệ các nút
D. Đổi hướng flowchart từ TD sang LR trong khai báo của sơ đồ
Đáp án đúng: D

Trong flowchart, mã định danh node và nhãn hiển thị khác nhau ở điểm nào?
A. Mã dùng để tham chiếu node, còn nhãn mô tả nội dung người xem đọc
B. Mã chỉ dùng cho theme, còn nhãn xác định cách tính hướng của cạnh
C. Mã luôn là văn bản hiển thị, còn nhãn là tên tệp sau khi xuất ảnh
D. Mã xác định thứ tự render, còn nhãn quyết định toàn bộ cấu trúc luồng
Đáp án đúng: A

Khi có hai bước liên tiếp trong flowchart, cách biểu diễn phù hợp là gì?
A. Dùng cạnh có hướng nối node bước trước với node bước tiếp theo
B. Dùng quan hệ kế thừa giữa hai lớp rồi đặt tên theo bước xử lý
C. Dùng cặp thực thể trong ER để chỉ ra bảng dữ liệu liên quan
D. Dùng hai mục thời gian trong Gantt mà không tạo quan hệ luồng
Đáp án đúng: A

Khi biểu diễn một câu hỏi rẽ nhánh trong flowchart, hình nào thường phù hợp?
A. Hình trụ cho điểm quyết định, cạnh chỉ cần số thứ tự của bước
B. Hình chữ nhật cho thực thể dữ liệu, cạnh biểu diễn khóa ngoại
C. Hình người cho thành viên xử lý, cạnh biểu diễn trao đổi thông điệp
D. Hình thoi cho điểm quyết định, cạnh có nhãn mô tả từng hướng đi
Đáp án đúng: D

Nếu cần ghi điều kiện trên hai hướng ra khỏi node quyết định, nên làm gì?
A. Đổi ID của node quyết định cho mỗi lần một cạnh đi qua nó
B. Đặt nhãn khác nhau trên các cạnh dẫn tới từng nhánh của luồng
C. Thêm các participant giả vào sơ đồ để đại diện cho điều kiện
D. Đặt tên một class cho từng điều kiện rồi nối bằng quan hệ kế thừa
Đáp án đúng: B

Khi một node xuất hiện ở nhiều chỗ trong cú pháp flowchart, yếu tố nào giữ nó là một node?
A. Viết cùng nội dung nhãn dù dùng các mã định danh khác nhau
B. Đặt các dòng mã gần nhau trong khối code để gộp theo vị trí
C. Sử dụng cùng mã định danh node khi khai báo và tham chiếu lại
D. Chọn cùng hình dạng node dù hai định danh biểu diễn khác nhau
Đáp án đúng: C

Để nhóm các bước thuộc một phân hệ trong flowchart, thành phần nào phù hợp?
A. Sử dụng subgraph bao quanh các node thuộc cùng khu vực trách nhiệm
B. Khai báo participant mới rồi chuyển mọi bước thành lời gọi tuần tự
C. Tạo một entity trong erDiagram chứa các khóa của các bước xử lý
D. Tạo một state kết thúc cho toàn bộ nhóm bước chưa hoàn thành
Đáp án đúng: A

Vì sao nên giữ một flowchart nghiệp vụ ở mức trừu tượng nhất quán?
A. Hình ảnh có thể bỏ qua mọi trường hợp lỗi vì sơ đồ không phải mã chạy
B. Người xem dễ theo dõi luồng mà không trộn bước nghiệp vụ với từng lệnh mã
C. Sơ đồ sẽ tự động kiểm chứng tính đúng đắn của mọi thuật toán được vẽ
D. Các node nên dùng cùng nhãn để tránh thay đổi ngoài dự kiến
Đáp án đúng: B

Khi mô tả các lời gọi qua lại theo thời gian giữa dịch vụ, loại sơ đồ nào hợp lý?
A. Sequence diagram nhấn mạnh người tham gia và thứ tự thông điệp
B. Class diagram nhấn mạnh thuộc tính và phương thức của từng lớp Java
C. ER diagram nhấn mạnh thực thể và bội số trong mô hình cơ sở dữ liệu
D. Gantt chart nhấn mạnh công việc và mốc thời gian của dự án
Đáp án đúng: A

Trong sequence diagram, participant có nhiệm vụ chính nào?
A. Đại diện thuộc tính của một thực thể dùng để kiểm tra khóa ngoại
B. Đại diện tác nhân hoặc thành phần tham gia trao đổi thông điệp
C. Đại diện cột trạng thái trên bảng Kanban của nhóm phát triển
D. Đại diện cấu hình theme để thay đổi màu của các lời gọi
Đáp án đúng: B

Khi muốn thể hiện client gửi request đến server, nên dùng gì trong sequence diagram?
A. Một cạnh biểu diễn khóa ngoại từ client sang server trong ER
B. Một quan hệ kế thừa từ client đến server trong class diagram
C. Một thanh tiến độ trong Gantt giữa hai thời điểm yêu cầu
D. Một mũi tên thông điệp giữa hai participant kèm tên hành động
Đáp án đúng: D

Khi phản hồi có thể thành công hoặc thất bại, biểu diễn nào rõ nhất trong sequence diagram?
A. Dùng thuộc tính static để gắn nhãn kết quả vào participant nhận
B. Dùng khóa chính để phân biệt hai nhánh của cùng một thực thể
C. Dùng nhánh điều kiện alt để mô tả các kịch bản thông điệp khác nhau
D. Dùng các mốc thời gian Gantt để thay thế hoàn toàn thông điệp
Đáp án đúng: C

Để biểu diễn một tương tác lặp đi lặp lại trong sequence diagram, dùng gì?
A. Khối subgraph để phân nhóm node và đường đi trong flowchart
B. Khối class để khai báo thuộc tính và phương thức của đối tượng
C. Khối entity để mô tả bảng có quan hệ một-nhiều
D. Khối loop bao lấy các thông điệp được thực hiện lặp lại
Đáp án đúng: D

Khi muốn nhấn mạnh một khoảng xử lý của participant, thành phần nào hữu ích?
A. Theme chọn bảng màu theo vai trò của participant trong hệ thống
B. Namespace biểu diễn khóa định danh của participant với hệ thống
C. Activation biểu diễn đoạn participant đang thực hiện công việc
D. Subgraph biểu diễn ranh giới giữa các bảng dữ liệu nghiệp vụ
Đáp án đúng: C

Câu lệnh mở đầu nào xác định nguồn Mermaid là class diagram?
A. Sử dụng sequenceDiagram trước phần khai báo lớp và quan hệ
B. Sử dụng stateDiagram-v2 trước phần khai báo lớp và quan hệ
C. Sử dụng classDiagram trước phần khai báo lớp và quan hệ
D. Sử dụng erDiagram trước phần khai báo lớp và quan hệ
Đáp án đúng: C

Trong class diagram, thông tin nào phù hợp đặt bên trong một lớp?
A. Thuộc tính và phương thức đại diện cho cấu trúc của lớp
B. Thông điệp theo trục thời gian giữa hai ứng dụng cộng tác
C. Mốc phát hành và ngày bắt đầu của các công việc dự án
D. Quan hệ khóa ngoại giữa các bảng cùng kiểu trong CSDL
Đáp án đúng: A

Khi sơ đồ hóa quan hệ giữa interface và lớp triển khai, điều gì quan trọng?
A. Dùng quan hệ phù hợp với ngữ nghĩa triển khai thay vì cạnh luồng xử lý
B. Dùng cạnh rẽ nhánh của flowchart thay cho tất cả quan hệ loại lớp
C. Dùng mốc thời gian Gantt để minh họa thứ tự tạo các đối tượng
D. Dùng đường liên kết ER để bắt buộc tạo khóa ngoại ở lớp con
Đáp án đúng: A

Trong class diagram, quan hệ kế thừa cần được hiểu như thế nào?
A. Một đối tượng sở hữu tài nguyên khác theo quan hệ has-a thông thường
B. Một participant gửi request tới participant khác trong thời gian chạy
C. Lớp chuyên biệt mở rộng hoặc thay thế kiểu cơ sở theo quan hệ is-a
D. Hai bảng được kết nối do có một khóa tham chiếu chung
Đáp án đúng: C

Muốn mô hình hóa thực thể và quan hệ dữ liệu, mở đầu Mermaid nào phù hợp?
A. Dùng gantt và khai báo các thanh thời gian của hoạt động triển khai
B. Dùng erDiagram và khai báo thực thể cùng quan hệ bội số của chúng
C. Dùng flowchart LR và khai báo các bước xử lý trong quy trình
D. Dùng sequenceDiagram và khai báo các lời gọi giữa các dịch vụ
Đáp án đúng: B

Trong ER diagram, bội số của quan hệ thể hiện khía cạnh nào?
A. Số lượng bản ghi mỗi phía có thể liên kết với phía còn lại
B. Thứ tự thời gian mà hệ thống sẽ ghi các bản ghi vào cơ sở dữ liệu
C. Kiểu hiển thị mũi tên khi flowchart có nhiều nhánh xử lý
D. Mức độ ưu tiên của các thực thể trong kế hoạch triển khai
Đáp án đúng: A

Khi biểu diễn CUSTOMER có nhiều ORDER trong ER, nên kiểm tra điều gì?
A. Hướng của quan hệ và cardinality ở từng đầu để tránh hiểu sai
B. Thứ tự gọi API từ CUSTOMER sang ORDER trên trục thời gian
C. Số điểm story point để tạo các bảng dữ liệu trong sprint tiếp theo
D. Số lượng participant được phép khai báo cho quan hệ một-nhiều
Đáp án đúng: A

Mục đích của state diagram là mô tả điều gì?
A. Các lớp Java cùng phương thức và quan hệ kế thừa ở thời điểm biên dịch
B. Các thư viện phụ thuộc và kích thước tệp của một bản phát hành
C. Các trạng thái và chuyển tiếp hợp lệ của một đối tượng hoặc quy trình
D. Các công việc theo trục thời gian với lịch bắt đầu và kết thúc
Đáp án đúng: C

Khi một trạng thái chỉ được rời đi khi có điều kiện, nên mô tả gì?
A. Thay mọi trạng thái bằng các bảng dữ liệu với tên cột tương ứng
B. Chuyển thành chuỗi participant để thể hiện số dòng code thay đổi
C. Ghi sự kiện hoặc điều kiện trên chuyển tiếp tới trạng thái tiếp theo
D. Đổi sang Gantt để loại bỏ sự kiện và chỉ giữ lại mốc thời gian
Đáp án đúng: C

Khi sơ đồ trạng thái có điểm bắt đầu và kết thúc, cần làm rõ điều gì?
A. Tổng số phương thức private trong mọi lớp liên quan đến trạng thái
B. Thời điểm cập nhật theme của trình kết xuất sơ đồ trong tài liệu
C. Số bảng dữ liệu tham gia lưu trữ trạng thái của các đối tượng
D. Đường chuyển tiếp từ trạng thái khởi đầu và các kết thúc hợp lệ
Đáp án đúng: D

Khi mô tả một luồng duyệt yêu cầu gồm chờ, duyệt và từ chối, nên dùng gì?
A. ER diagram thể hiện khóa dữ liệu của các nhân viên tham gia duyệt
B. Class diagram thể hiện tên từng phương thức trả về của API
C. State diagram thể hiện các trạng thái và hành động chuyển đổi
D. Gantt chart thể hiện lịch triển khai mà không có các chuyển tiếp
Đáp án đúng: C

Loại sơ đồ Mermaid nào phù hợp để trình bày kế hoạch công việc theo mốc ngày?
A. Sequence diagram dùng lời gọi hàm giữa hai đối tượng theo thứ tự
B. Class diagram dùng phương thức và thuộc tính của module trong dự án
C. Gantt chart dùng thanh thời gian cùng mốc và quan hệ công việc
D. ER diagram dùng bảng dữ liệu để lưu ngày phát hành của hệ thống
Đáp án đúng: C

Khi một công việc Gantt phải đợi công việc trước kết thúc, nên làm gì?
A. Đổi tên cả hai công việc thành một mã ID để không còn phụ thuộc
B. Biểu diễn phụ thuộc thời gian để thay đổi lịch có thể được đánh giá
C. Đặt hai task vào cùng class rồi dùng quan hệ kế thừa giữa chúng
D. Dùng hai trạng thái có cùng nhãn mà không cần mốc bắt đầu riêng
Đáp án đúng: B

Khi Gantt chứa nhiều công việc song song, cần làm rõ điều gì?
A. Số lượng trường dữ liệu của mỗi công việc để quyết định hướng vẽ
B. Tên participant trao đổi thông điệp thay cho ngày bắt đầu công việc
C. Các đường liên kết khóa ngoại để bảo đảm không có công việc độc lập
D. Mốc thời gian và phụ thuộc thực tế thay vì xếp tất cả nối đuôi
Đáp án đúng: D

Muốn mô tả kiến trúc hệ thống bằng Mermaid, cách tiếp cận nào hợp lý?
A. Đặt toàn bộ chi tiết mã nguồn vào một node lớn để tránh chia module
B. Dùng Gantt làm sơ đồ kiến trúc vì có ngày tạo của mọi dịch vụ
C. Dùng ER cho mọi quan hệ vì các module luôn tương ứng một bảng dữ liệu
D. Chọn loại sơ đồ và mức trừu tượng thể hiện thành phần cùng liên kết
Đáp án đúng: D

Khi sơ đồ kiến trúc bị quá nhiều cạnh chồng nhau, nên cải thiện thế nào?
A. Thêm cùng một node ở nhiều ID để mọi cạnh trở nên độc lập
B. Giảm số mũi tên bằng cách gộp các liên kết quan hệ tương đương
C. Chia sơ đồ theo phạm vi và nhóm các thành phần liên quan rõ ràng
D. Đưa tất cả cạnh vào cùng một màu để che đi đường giao nhau
Đáp án đúng: C

Vì sao sơ đồ nguồn dạng văn bản có lợi cho việc review cùng mã nguồn?
A. Diff thể hiện thay đổi về node và liên kết qua hệ thống quản lý phiên bản
B. Trình render sẽ tự xác nhận mọi đường đi đều đúng với mã đang chạy
C. Ảnh PNG luôn nhỏ hơn văn bản nguồn và không bao giờ cần chỉnh sửa
D. Ngôn ngữ Mermaid loại bỏ yêu cầu đồng bộ giữa thiết kế và triển khai
Đáp án đúng: A

Khi một label chứa ký tự đặc biệt có thể gây lỗi parse, nên làm gì?
A. Đổi toàn bộ nhãn thành tên file để trình vẽ tự khôi phục ký tự
B. Tắt mọi kiểm tra cú pháp vì parser không cần đọc nội dung nhãn
C. Sử dụng cú pháp nhãn hợp lệ và escape ký tự theo loại sơ đồ
D. Thay toàn bộ label bằng khoảng trắng để giữ nguyên cấu trúc liên kết
Đáp án đúng: C

Khi đặt tên ID cho node Mermaid, điều gì giúp bảo trì tốt hơn?
A. Đổi ID ngẫu nhiên khi cập nhật nhãn để có nhiều thay đổi trong diff
B. Dùng cùng một ID cho mọi node để giảm số ký tự nguồn cần viết
C. Đặt ID phụ thuộc vào vị trí render để sơ đồ ổn định khi chỉnh layout
D. Giữ ID nhất quán, không trùng nhau và tách khỏi nhãn hiển thị
Đáp án đúng: D

Khi muốn đổi bảng màu của sơ đồ Mermaid, nên ưu tiên thay đổi gì?
A. Cấu hình theme hoặc style mà không sửa quan hệ logic của sơ đồ
B. Sửa nhãn node và thứ tự khai báo để màu tự đổi khi render
C. Đổi tất cả quan hệ có hướng thành quan hệ không hướng
D. Chuyển sơ đồ từ flowchart sang ER dù ngữ nghĩa hoàn toàn khác
Đáp án đúng: A

Nếu một sơ đồ hiển thị khác nhau giữa hai công cụ Markdown, nguyên nhân nào hợp lý?
A. Mỗi tài liệu cần một ảnh được xuất và gắn cố định vào nguồn
B. Khác phiên bản Mermaid hoặc chính sách render và hỗ trợ cú pháp
C. Mã nguồn Markdown không thể chứa phần khai báo theme của sơ đồ
D. Các công cụ Markdown đều dùng cùng một phiên bản parser mặc định
Đáp án đúng: B

Khi lưu sơ đồ Mermaid trong tài liệu kỹ thuật, nên tổ chức nguồn thế nào?
A. Lưu ảnh kết xuất vào tài liệu thay vì mã Mermaid có thể biên tập
B. Chép cùng sơ đồ ở nhiều chỗ mà không có nơi làm nguồn chuẩn
C. Để nguồn ở máy cá nhân vì tài liệu chỉ cần nội dung hiển thị
D. Giữ mã nguồn gần mô tả và kiểm tra khả năng render trong CI
Đáp án đúng: D

Khi cần đưa sơ đồ vào tài liệu PDF hoặc slide, định dạng nào hợp lý?
A. Chọn PNG để chỉnh sửa từng node dưới dạng văn bản và diff dễ dàng
B. Chọn SVG vì trình duyệt luôn chấp nhận mọi nội dung không cần kiểm tra
C. Chọn văn bản Mermaid thô vì mọi trình chiếu đều tự render được
D. Chọn SVG khi cần phóng to vector và PNG khi cần ảnh raster tương thích
Đáp án đúng: D

Khi muốn xuất Mermaid sang SVG hoặc PNG tự động, cần chú ý gì?
A. Đổi phần mở rộng của tệp nguồn mà không thực hiện kết xuất
B. Dùng công cụ render phù hợp và cố định phiên bản trong pipeline
C. Mã hóa nội dung bằng Base64 rồi coi đó là dữ liệu ảnh hợp lệ
D. Sao chép Markdown vào thư mục ảnh để tự chuyển thành SVG
Đáp án đúng: B

Điểm khác biệt quan trọng giữa SVG và PNG đối với sơ đồ là gì?
A. SVG chỉ chứa pixel cố định, PNG chứa các đường vector có thể chỉnh
B. SVG không hỗ trợ văn bản trong ảnh, PNG giữ nguyên ID của node
C. SVG dạng vector dễ phóng lớn, PNG là ảnh raster theo độ phân giải
D. SVG chỉ dùng trong web, PNG chỉ dùng trong mã nguồn Java
Đáp án đúng: C

Khi một thay đổi nhỏ làm sơ đồ render không thành công trong CI, nên làm gì?
A. Báo lỗi cú pháp ở commit đó trước khi cập nhật tài liệu phát hành
B. Bỏ kiểm tra sơ đồ khỏi CI để những lần thay đổi tiếp theo luôn qua
C. Kiểm tra ảnh kết xuất trước đó và trì hoãn sửa source gặp lỗi
D. Chuyển tệp thành .txt rồi tiếp tục công bố ảnh sơ đồ từ lần trước
Đáp án đúng: A

Một bài kiểm thử tự động cho nguồn Mermaid nên ưu tiên xác minh gì?
A. Hình ảnh luôn có cùng vị trí pixel trên mọi nền tảng và mọi font
B. Số dòng sơ đồ bằng đúng số dòng mã ứng dụng được mô tả
C. Tên mọi node trùng hoàn toàn với tên thư mục chứa file tài liệu
D. Kiểm tra sơ đồ parse và render bằng phiên bản công cụ đã chọn
Đáp án đúng: D

Khi cập nhật kiến trúc khiến một service đổi tên, cách sửa sơ đồ nào bền vững?
A. Đổi tên ảnh xuất mà không cập nhật mã nguồn hay liên kết Mermaid
B. Sửa nhãn hoặc ID liên quan và kiểm tra lại toàn bộ cạnh tham chiếu
C. Thêm một service thứ hai không dùng để giữ cấu trúc sơ đồ cũ
D. Tái tạo sơ đồ từ đầu để bảo đảm các liên kết đều được cập nhật
Đáp án đúng: B

Khi tạo sơ đồ từ dữ liệu không đáng tin cậy, rủi ro nào cần xem xét?
A. Mermaid sẽ tự loại bỏ mọi rủi ro ngay cả khi bật chế độ render lỏng
B. Nhãn, liên kết và cấu hình có thể chứa nội dung gây hại khi hiển thị
C. Cú pháp dạng văn bản không thể sinh bất kỳ hành vi liên kết nào
D. Đánh giá rủi ro riêng ở ảnh PNG, bỏ qua liên kết được tạo từ SVG
Đáp án đúng: B

Khi nhúng SVG xuất từ Mermaid vào trang web, bước phòng vệ nào quan trọng?
A. Xem xét sanitization và chính sách nội dung đối với SVG không tin cậy
B. Tin tưởng mọi SVG vì định dạng vector không có khả năng chứa nội dung
C. Chuyển SVG sang tên tệp khác để loại bỏ liên kết bên trong mã
D. Bỏ kiểm tra nguồn Mermaid nếu tệp xuất có kích thước đủ nhỏ
Đáp án đúng: A

Khi một nhóm cần sử dụng chung theme Mermaid, chiến lược nào hữu ích?
A. Yêu cầu mỗi người tự thay đổi màu ở từng node khi cập nhật tài liệu
B. Thống nhất cấu hình render để các tài liệu có hình thức nhất quán
C. Đổi mọi sơ đồ sang một loại để không cần cấu hình theo ngữ cảnh
D. Lưu theme riêng trong mỗi ảnh PNG mà không có nguồn cấu hình
Đáp án đúng: B

Khi cần giữ sơ đồ và mã triển khai đồng bộ, quy trình nào phù hợp?
A. Đợi đến cuối dự án mới rà lại toàn bộ sơ đồ theo trí nhớ của nhóm
B. Tự động coi mọi sơ đồ là đúng nếu các bài unit test của mã đều qua
C. Giao cho một người lưu ảnh tĩnh rồi không cho thay đổi khi phát hành
D. Đưa cập nhật sơ đồ vào review thay đổi chức năng và kiểm tra render
Đáp án đúng: D

Khi Mermaid không hỗ trợ một chi tiết sơ đồ mong muốn, bạn nên làm gì?
A. Tự thêm cú pháp không được parser hỗ trợ rồi giữ nguyên trong tài liệu
B. Đánh giá giản lược biểu diễn hoặc chọn công cụ khác cho yêu cầu đó
C. Thay tên sơ đồ thành kiến trúc dù nội dung đang là luồng xử lý
D. Đổi thứ tự các dòng Markdown và giả định trình render sẽ hiểu thêm
Đáp án đúng: B

Khi hai node đáng ra khác nhau bị hiển thị gộp, nên kiểm tra điều gì?
A. Các nhãn hiển thị có dùng nhiều dấu cách khiến font thay đổi
B. Các mã ID có bị tái sử dụng dù biểu thị hai thành phần khác nhau
C. Theme sáng tối có bị chuyển trong lúc trình render khởi chạy
D. Tệp SVG có bị phóng lớn quá mức so với kích thước gốc
Đáp án đúng: B
