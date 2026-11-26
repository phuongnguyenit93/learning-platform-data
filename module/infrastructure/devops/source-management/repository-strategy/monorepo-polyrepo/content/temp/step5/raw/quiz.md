Câu 1: Một thay đổi API nội bộ buộc sửa đồng thời thư viện và ba dịch vụ. Lợi thế phối hợp nào của monorepo là phù hợp nhất?
A. Phát hành cả ba dịch vụ tự động chỉ vì chúng cùng repository.
B. Sửa mã liên quan trong một change set và chạy kiểm thử chung.
C. Tách mọi thay đổi sang ba pull request không có liên kết.
D. Cho phép bỏ kiểm tra tương thích giữa thư viện và dịch vụ.
Đáp án đúng: B

Câu 2: Bốn dịch vụ có lịch phát hành và nhóm vận hành độc lập trong polyrepo. Cách tổ chức nào phù hợp nhất?
A. Gộp một pipeline duy nhất để bắt buộc phát hành cùng lúc.
B. Bắt mọi repo chờ hoàn tất unit test của các repo không liên quan.
C. Dùng chung một version tag cho tất cả repository dịch vụ.
D. Thiết lập pipeline riêng, duy trì hợp đồng API giữa các repo.
Đáp án đúng: D

Câu 3: Trong monorepo, thư viện `core` vừa đổi và `api`, `worker` phụ thuộc vào nó. Chọn tập kiểm thử nào?
A. Chỉ kiểm thử `api` vì nó nhận lưu lượng bên ngoài.
B. Chỉ kiểm thử thư mục `core` do thay đổi nằm ở đó.
C. Kiểm thử `core` và các module phụ thuộc theo đồ thị build.
D. Kiểm thử các module không phụ thuộc để tránh cache cũ.
Đáp án đúng: C

Câu 4: Build cache dùng lại kết quả biên dịch sai sau khi nâng compiler. Thành phần nào cần có trong cache key?
A. Chỉ tên nhánh và thời điểm pipeline được tạo.
B. Chỉ danh sách tác giả các commit trong repository đang được build.
C. Mã nguồn, dependency và cấu hình toolchain liên quan.
D. Chỉ tên module và tên workflow đang chạy trên CI.
Đáp án đúng: C

Câu 5: Monorepo lớn mất nhiều giờ CI vì mọi PR đều chạy toàn bộ job. Điều chỉnh nào ít bỏ sót tác động?
A. Chỉ chạy unit test tại file vừa được chỉnh sửa.
B. Chạy job bị ảnh hưởng dựa trên đồ thị phụ thuộc.
C. Bỏ integration test cho các module không sửa trực tiếp.
D. Chỉ chạy CI đầy đủ trên bản release sau khi merge.
Đáp án đúng: B

Câu 6: Một module monorepo thường xuyên import thẳng lớp `internal` của module khác. Cách bảo vệ ranh giới nào phù hợp?
A. Cho mọi module dùng trực tiếp `internal` để giảm mã lặp.
B. Định nghĩa API công khai và kiểm quy tắc phụ thuộc chéo.
C. Yêu cầu các đội đặt tiền tố trong tên lớp nội bộ.
D. Chỉ đặt mỗi module trong một thư mục có tên riêng.
Đáp án đúng: B

Câu 7: Đội `payments` phải duyệt các thay đổi tại `services/payments/` trong monorepo. Cấu hình nào phù hợp?
A. Đặt tên nhóm vào README mà không cấu hình điều kiện bắt buộc merge.
B. Cho phép người mở PR tự phê duyệt thay đổi của họ.
C. Chỉ thêm nhãn `payments` sau khi mã đã được merge.
D. Gán owner theo đường dẫn và bắt buộc review trước merge.
Đáp án đúng: D

Câu 8: Hai dịch vụ ở polyrepo cùng dùng thư viện kiểm tra dữ liệu. Cách chia sẻ nào dễ truy vết phiên bản?
A. Phát hành package có phiên bản, nâng phụ thuộc qua PR.
B. Đọc trực tiếp nhánh `main` của repo thư viện lúc chạy.
C. Sao chép mã thư viện vào từng repo khi có lỗi build.
D. Để từng dịch vụ tự sửa bản sao thư viện mà không đồng bộ.
Đáp án đúng: A

Câu 9: Monorepo chứa bốn dịch vụ nhưng mỗi đội cần phát hành một dịch vụ riêng. Thiết kế nào thích hợp?
A. Luôn tăng version và phát hành cả bốn sau mỗi commit.
B. Tạo artifact và luồng release riêng cho từng dịch vụ.
C. Bắt mọi đội dùng một lịch deploy vì cùng Git history.
D. Chỉ phát hành khi tất cả dịch vụ cùng đổi source.
Đáp án đúng: B

Câu 10: Hai dịch vụ ở polyrepo cần nâng API có thay đổi phá vỡ client cũ. Cách triển khai nào giảm gián đoạn?
A. Duy trì tương thích chuyển tiếp, kiểm contract và chuyển dần.
B. Chỉ đổi tag repository mà giữ hợp đồng đang không khớp.
C. Đồng thời xóa endpoint cũ mà không kiểm ứng dụng gọi tới.
D. Triển khai provider phá vỡ API trước rồi sửa client sau khi lỗi xuất hiện.
Đáp án đúng: A

Câu 11: Các polyrepo đang sao chép cùng logic xác thực, khiến bản vá phân tán. Biện pháp quản trị nào phù hợp?
A. Tách thành package dùng chung có version và quy trình cập nhật.
B. Giữ bản sao ở mọi repo để mỗi đội sửa lỗi độc lập.
C. Đồng bộ mã bằng thao tác copy thủ công khi có sự cố.
D. Chỉ ghi danh sách nơi dùng mã trong wiki rồi để nguyên.
Đáp án đúng: A

Câu 12: Đội chuyển nhiều polyrepo vào một monorepo và muốn tránh gián đoạn CI. Cách thực hiện nào hợp lý?
A. Chuyển toàn bộ vào thư mục gốc, bỏ pipeline cũ ngay lập tức.
B. Buộc các dịch vụ phát hành cùng lúc sau khi chuyển repository.
C. Lập bản đồ owner, dependency, chuyển dần và kiểm chứng CI.
D. Xóa nhánh phát hành cũ trước khi kiểm đủ các workflow.
Đáp án đúng: C

Câu 13: Một phần monorepo chuẩn bị tách thành repo độc lập nhưng còn import trực tiếp code nội bộ. Bước nào ưu tiên?
A. Chỉ đổi URL repository mà không sửa phụ thuộc mã nguồn.
B. Copy mọi module phụ thuộc rồi giữ các bản sao vô thời hạn.
C. Xóa các kiểm thử liên module để tránh lỗi lúc tách repository.
D. Tách ranh giới rõ, thay import chéo bằng API hoặc package.
Đáp án đúng: D

Câu 14: CI monorepo chạy PR từ fork; job deploy giữ secret môi trường production. Kiểm soát nào đúng?
A. Cấp secret production cho mọi PR để kiểm thử thống nhất.
B. Chỉ dùng CODEOWNERS, vì nó chặn toàn bộ script độc hại.
C. Đưa secret vào file cấu hình chung để job nào cũng đọc.
D. Giới hạn secret ở job tin cậy và kiểm nguồn thực thi.
Đáp án đúng: D

Câu 15: Cần quyết định giữ monorepo hay chuyển polyrepo khi tổ chức mở rộng. Dữ liệu nào có ích nhất?
A. Chỉ đếm tổng số commit trong repository hiện tại theo từng tháng.
B. Chỉ so kích thước thư mục `.git` giữa hai mô hình.
C. Đo coupling, thời gian CI, lead time và ranh giới đội.
D. Chỉ xem số lượng branch còn mở ở ngày tổng kết.
Đáp án đúng: C

Câu 16: Hai sản phẩm phải có nhóm người được đọc mã nguồn hoàn toàn tách biệt. Chiến lược nào thuận lợi hơn?
A. Dùng repo riêng, áp quyền truy cập theo từng repository.
B. Dùng một monorepo và gán CODEOWNERS cho mỗi thư mục.
C. Giữ monorepo và chỉ ẩn đường dẫn trên giao diện web.
D. Dùng một nhánh Git riêng trong cùng repo cho từng nhóm để phân quyền đọc.
Đáp án đúng: A
