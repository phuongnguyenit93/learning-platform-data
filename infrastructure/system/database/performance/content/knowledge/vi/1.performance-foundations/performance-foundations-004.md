# Phân biệt truy vấn chậm, hệ thống quá tải và thời gian chờ tài nguyên

Trong vận hành cơ sở dữ liệu, một yêu cầu phản hồi chậm có thể xuất phát từ nhiều nguyên nhân khác nhau. Một câu SQL có thể có kế hoạch thực thi kém; toàn bộ hệ thống có thể nhận nhiều việc hơn năng lực xử lý; hoặc truy vấn có thể dành phần lớn thời gian chờ khóa, đĩa, kết nối hay một tài nguyên dùng chung. Ba tình huống này có thể tạo ra cùng một biểu hiện ở phía ứng dụng, nhưng cần cách xử lý khác nhau.

Trong phạm vi **DATABASE_PERFORMANCE**, mục tiêu là rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, bước đầu tiên không phải là thêm chỉ mục hay tăng cấu hình máy chủ. Bước đầu tiên là xác định đúng phạm vi của vấn đề, đo được điều gì đang xảy ra và tìm bằng chứng cho giả thuyết nguyên nhân.

## 1. Ba khái niệm cần phân biệt

### Truy vấn chậm

Truy vấn chậm là tình huống một câu SQL hoặc một nhóm nhỏ câu SQL có thời gian thực thi cao hơn kỳ vọng, trong khi phần còn lại của hệ thống vẫn có thể hoạt động bình thường. Nguyên nhân thường nằm ở chính câu truy vấn, cách truy cập dữ liệu hoặc kế hoạch thực thi:

- Truy vấn đọc quá nhiều dòng hoặc quá nhiều trang dữ liệu.
- Điều kiện lọc không tận dụng được chỉ mục phù hợp.
- Phép nối, sắp xếp hoặc tổng hợp xử lý tập dữ liệu lớn.
- Thống kê không phản ánh phân bố dữ liệu hiện tại, khiến bộ tối ưu chọn kế hoạch chưa phù hợp.
- Câu SQL được gọi lặp lại quá nhiều lần, dù mỗi lần chạy riêng lẻ không quá lâu.

Dấu hiệu quan trọng là mức chậm tập trung vào một số mẫu truy vấn. Những truy vấn khác vẫn có độ trễ gần với đường cơ sở.

### Hệ thống quá tải

Hệ thống quá tải xảy ra khi tổng khối lượng công việc đồng thời vượt quá năng lực phục vụ hiện tại của cơ sở dữ liệu hoặc một thành phần hạ tầng. Mỗi truy vấn riêng lẻ có thể hợp lý, nhưng nhiều truy vấn cùng tranh phần CPU, bộ nhớ, I/O, kết nối hoặc năng lực lập lịch.

Các dấu hiệu thường gặp:

- Nhiều loại truy vấn cùng chậm trong một khoảng thời gian.
- Lưu lượng, số phiên hoạt động hoặc số giao dịch tăng mạnh.
- CPU duy trì ở mức cao, hàng đợi công việc tăng hoặc hệ điều hành phải chuyển đổi tiến trình liên tục.
- Bộ nhớ chịu áp lực, phát sinh đọc ghi vùng nhớ tạm hoặc hoán đổi bộ nhớ.
- Throughput không tăng tương ứng với số yêu cầu mới; khi tải tăng, độ trễ tăng nhanh.

Quá tải là vấn đề ở cấp khối lượng công việc và năng lực phục vụ. Tối ưu một câu SQL có thể giúp giảm tải, nhưng không phải lúc nào cũng giải quyết được nguyên nhân chính như đỉnh lưu lượng, số kết nối quá lớn hoặc giới hạn tài nguyên.

### Thời gian chờ tài nguyên

Thời gian chờ tài nguyên là khoảng thời gian truy vấn hoặc giao dịch chưa thể tiếp tục vì đang đợi một điều kiện hay tài nguyên cần thiết. Trong thời gian chờ, truy vấn có thể không tiêu thụ nhiều CPU nhưng thời gian phản hồi vẫn tăng.

Một số dạng chờ phổ biến:

- **Chờ khóa giao dịch:** phiên khác đang giữ khóa trên dòng hoặc bảng mà giao dịch hiện tại cần truy cập.
- **Chờ I/O:** cơ sở dữ liệu cần đọc hoặc ghi dữ liệu nhưng thiết bị lưu trữ chưa đáp ứng kịp.
- **Chờ kết nối:** ứng dụng phải đợi một kết nối khả dụng từ connection pool, hoặc cơ sở dữ liệu đã gần giới hạn phiên.
- **Chờ bộ nhớ hay vùng nhớ tạm:** thao tác sắp xếp, hash join hoặc tổng hợp cần thêm bộ nhớ; khi không đủ, hệ thống có thể phải dùng vùng lưu trữ tạm.
- **Chờ đồng bộ nội bộ:** nhiều tiến trình cùng cần một cấu trúc hoặc tài nguyên nội bộ, gây tranh chấp.

Chờ tài nguyên mô tả điều truy vấn đang đợi. Nó chưa tự động chỉ ra nguyên nhân gốc. Ví dụ, chờ I/O có thể do lưu trữ chậm, do truy vấn đọc quá nhiều dữ liệu, hoặc do một đợt tải đồng thời tạo ra lượng I/O vượt khả năng xử lý.

| Hiện tượng | Phạm vi thường gặp | Bằng chứng cần tìm | Hướng điều tra ban đầu |
|---|---|---|---|
| Một số truy vấn chậm | Một mẫu SQL hoặc một luồng nghiệp vụ | Thời gian theo query fingerprint, số dòng thực tế, kế hoạch thực thi | Điều kiện lọc, chỉ mục, phép nối, thống kê |
| Nhiều truy vấn cùng chậm | Toàn hệ thống hoặc một nhóm tài nguyên | Throughput, concurrency, CPU, bộ nhớ, I/O, hàng đợi | Tải tổng thể, năng lực phục vụ, giới hạn kết nối |
| Truy vấn có thời gian chờ lớn | Một phiên, giao dịch hoặc nhóm phiên | Loại sự kiện chờ, thời lượng chờ, phiên đang giữ tài nguyên | Khóa, I/O, pool kết nối, bộ nhớ và đồng bộ |

Ba tình huống có thể xuất hiện đồng thời. Một truy vấn đọc quá nhiều dữ liệu có thể làm tăng I/O cho toàn hệ thống; tải cao có thể làm thời gian chờ khóa tăng; hoặc một giao dịch giữ khóa lâu có thể khiến nhiều truy vấn khác bị ùn lại. Do đó, cần tìm nguyên nhân chi phối thay vì ép mọi sự cố vào một nhãn duy nhất.

## 2. Đo độ trễ và tải trước khi kết luận

Một con số thời gian phản hồi đơn lẻ không đủ để chẩn đoán. Hãy xác định phạm vi đo, khoảng thời gian, mức tải và đường cơ sở để có thể so sánh.

### Độ trễ và phân vị

Độ trễ (latency) cho biết một yêu cầu mất bao lâu để hoàn thành. Khi đánh giá truy vấn hoặc API dùng cơ sở dữ liệu, nên theo dõi ít nhất:

- **p50:** một nửa số lần thực thi hoàn thành trong thời gian bằng hoặc thấp hơn giá trị này.
- **p95:** 95% số lần thực thi hoàn thành trong thời gian bằng hoặc thấp hơn giá trị này.
- **p99:** phản ánh nhóm yêu cầu chậm nhất và giúp phát hiện các đợt chậm bất thường.
- **Số lần gọi và throughput:** cho biết truy vấn được gọi bao nhiêu lần và hệ thống hoàn thành bao nhiêu công việc trong một đơn vị thời gian.

Thời gian trung bình có thể che khuất một nhóm nhỏ truy vấn cực chậm. Chẳng hạn, phần lớn yêu cầu hoàn thành trong 20 ms nhưng một số yêu cầu mất vài giây vẫn có thể làm trải nghiệm của một nhóm người dùng rất kém. Vì vậy, hãy xem phân vị cùng số lượng mẫu và lưu lượng.

### Tải và mức sử dụng tài nguyên

Ghi nhận các chỉ số theo cùng trục thời gian với độ trễ:

- Số phiên kết nối, số phiên đang hoạt động và số phiên chờ.
- CPU của máy chủ cơ sở dữ liệu và CPU của máy chủ lưu trữ.
- Lượng bộ nhớ khả dụng, bộ nhớ được cơ sở dữ liệu sử dụng, áp lực bộ nhớ và hoạt động swap.
- IOPS, thông lượng đọc ghi, độ trễ thiết bị lưu trữ và hàng đợi I/O.
- Số lần đọc từ bộ nhớ đệm so với đọc từ lưu trữ, nếu hệ quản trị cung cấp.
- Số giao dịch, số lần commit/rollback và tốc độ phát sinh truy vấn.
- Số lượng giao dịch mở lâu, khóa đang được giữ và thời gian chờ khóa.
- Hoạt động ghi vào vùng nhớ tạm hoặc file tạm do sort/hash, nếu có.

Không nên diễn giải một chỉ số đứng riêng lẻ. CPU 90% có thể là dấu hiệu bão hòa, nhưng cũng có thể là mức sử dụng bình thường trong một đợt xử lý ngắn nếu độ trễ và hàng đợi vẫn ổn định. Ngược lại, CPU thấp không chứng minh cơ sở dữ liệu đang khỏe: truy vấn có thể đang đợi khóa hoặc lưu trữ.

### Đường cơ sở và bối cảnh

Đường cơ sở (baseline) là mức hoạt động bình thường trong điều kiện có thể so sánh. Khi ghi nhận một bất thường, hãy lưu lại:

1. Thời điểm bắt đầu và kết thúc sự cố.
2. Lưu lượng và số phiên đồng thời trong khoảng đó.
3. Các truy vấn có tổng thời gian tiêu thụ lớn hoặc độ trễ tăng mạnh.
4. Các chỉ số CPU, bộ nhớ, I/O, khóa và kết nối.
5. Thay đổi gần thời điểm xảy ra vấn đề: phiên bản ứng dụng, câu SQL, dữ liệu tăng trưởng, cấu hình, lịch tác vụ hoặc triển khai mới.

So sánh cùng khung giờ, cùng loại tải và cùng điều kiện dữ liệu nếu có thể. So sánh một giờ cao điểm với một giờ ít người dùng dễ dẫn đến kết luận sai.

## 3. Quy trình xác định phạm vi vấn đề

### Bước 1: Xác nhận biểu hiện từ phía người dùng

Làm rõ điều gì đang chậm: một màn hình, một thao tác, một API hay mọi chức năng dùng chung cơ sở dữ liệu. Xác định thời gian phản hồi đo từ phía ứng dụng hay chỉ thời gian thực thi bên trong cơ sở dữ liệu.

Thời gian phía ứng dụng có thể bao gồm thời gian chờ lấy kết nối, truyền dữ liệu qua mạng, xử lý ở tầng ứng dụng và thời gian cơ sở dữ liệu thực thi. Nếu chỉ nhìn thời gian SQL, bạn có thể bỏ sót việc ứng dụng đang chờ connection pool. Nếu chỉ nhìn thời gian API, bạn có thể nhầm thời gian xử lý ứng dụng với thời gian truy vấn.

### Bước 2: Xác định một truy vấn hay nhiều truy vấn bị ảnh hưởng

Nhóm các câu SQL tương đương theo mẫu truy vấn (query fingerprint), bỏ qua các giá trị tham số thay đổi. Tìm các mẫu có tổng thời gian tiêu thụ cao, thời gian trung bình hoặc phân vị tăng bất thường, số lần gọi tăng đột biến hay lượng dòng đọc lớn.

Hãy phân biệt hai trường hợp:

- Một truy vấn có thời gian mỗi lần chạy cao: cần xem kế hoạch thực thi và dữ liệu mà truy vấn đọc.
- Một truy vấn có thời gian mỗi lần chạy thấp nhưng được gọi hàng chục nghìn lần: tổng chi phí có thể rất lớn do tần suất gọi, round trip hoặc cách ứng dụng truy xuất từng dòng.

Không chỉ xếp hạng theo thời gian trung bình. Một truy vấn chạy 5 ms nhưng gọi một triệu lần có thể tiêu thụ tài nguyên nhiều hơn truy vấn chạy 2 giây nhưng chỉ chạy một lần.

### Bước 3: Đối chiếu với tài nguyên và sự kiện chờ

Đặt thời gian truy vấn lên cùng biểu đồ CPU, I/O, bộ nhớ, kết nối và lock wait. Tìm sự trùng khớp về thời điểm:

- Nhiều truy vấn cùng tăng độ trễ, CPU bão hòa và hàng đợi tăng: nghiêng về quá tải CPU hoặc tải công việc tăng.
- Nhiều truy vấn cùng chậm, I/O latency và hàng đợi đĩa tăng: nghiêng về nút thắt lưu trữ hoặc khối lượng đọc ghi quá lớn.
- Truy vấn chậm nhưng CPU thấp, có wait event về khóa: điều tra giao dịch đang giữ khóa.
- API chậm, thời gian SQL thấp nhưng thời gian lấy kết nối cao: điều tra connection pool và giới hạn kết nối.
- Chỉ một mẫu SQL chậm, trong khi tải và truy vấn khác ổn định: ưu tiên phân tích câu SQL và kế hoạch thực thi.

### Bước 4: Kiểm tra một phiên và một giao dịch cụ thể

Khi có dấu hiệu chờ, xác định phiên đang chờ, loại chờ, tài nguyên liên quan và phiên nào đang giữ tài nguyên đó. Với chờ khóa, cần tìm giao dịch chặn (blocking transaction), thời điểm bắt đầu, câu SQL liên quan và lý do giao dịch chưa kết thúc.

Không nên kết luận rằng phiên đang chờ là thủ phạm. Phiên chờ thường là nạn nhân của một phiên khác đang giữ khóa. Việc hủy phiên chờ có thể chỉ xóa biểu hiện tạm thời mà không giải quyết giao dịch chặn.

### Bước 5: Đọc kế hoạch thực thi nếu bằng chứng hướng đến truy vấn

Dùng kế hoạch thực thi để kiểm tra cách hệ quản trị truy cập dữ liệu, thứ tự phép nối, phương pháp sắp xếp và ước lượng số dòng. So sánh số dòng ước lượng với số dòng thực tế nếu công cụ hỗ trợ.

Các câu hỏi cần trả lời:

- Có quét tuần tự một bảng lớn trong khi điều kiện lọc chỉ chọn rất ít dòng không?
- Chỉ mục được chọn có phù hợp với điều kiện lọc và thứ tự sắp xếp không?
- Có phép nối tạo ra nhiều dòng trung gian hơn dự kiến không?
- Có bước sort/hash tiêu thụ nhiều bộ nhớ hoặc ghi ra vùng nhớ tạm không?
- Ước lượng số dòng có sai lệch lớn so với thực tế không?
- Một truy vấn đọc cùng dữ liệu nhiều lần do vòng lặp hoặc cách gọi lặp không?

Kế hoạch thực thi cần được đọc cùng thống kê dữ liệu và mức tải tại thời điểm đo. Một kế hoạch tốt trên tập dữ liệu nhỏ có thể trở nên đắt đỏ khi dữ liệu tăng lên.

## 4. Nhận diện các nhóm chờ tài nguyên

### Chờ CPU

Nếu truy vấn đang hoạt động, tiêu thụ CPU cao và hệ thống có nhiều công việc sẵn sàng chạy, CPU có thể là nút thắt. Các nguyên nhân gồm biểu thức tính toán nặng, phép nối trên tập dữ liệu lớn, sắp xếp, tổng hợp, hoặc số lượng truy vấn đồng thời quá cao.

Cách kiểm tra:

- Xem CPU theo tiến trình và theo máy chủ trong cùng khoảng thời gian với độ trễ.
- Tìm các mẫu SQL tiêu thụ tổng thời gian CPU lớn.
- Kiểm tra số dòng đầu vào của join, sort và aggregate trong kế hoạch.
- Đối chiếu throughput với mức sử dụng CPU: khi CPU tăng mà throughput đứng yên hoặc giảm, có thể hệ thống đã gần bão hòa.

Hướng xử lý có thể là giảm dữ liệu phải xử lý, sửa phép nối hoặc điều kiện lọc, giảm số lần gọi, giới hạn concurrency, hoặc phân bổ thêm năng lực xử lý khi tải thực tế đã vượt thiết kế.

### Chờ I/O

Chờ I/O xuất hiện khi cơ sở dữ liệu cần đọc hoặc ghi trang dữ liệu nhưng thao tác lưu trữ chưa hoàn tất. Cần phân biệt lượng I/O lớn do truy vấn với độ trễ cao của thiết bị lưu trữ.

Cách kiểm tra:

- Xem read/write latency, IOPS, throughput và hàng đợi thiết bị.
- Đối chiếu lượng trang đọc của truy vấn với số dòng kết quả.
- Kiểm tra tỷ lệ cache hit hoặc các chỉ số đọc từ buffer/cache do hệ quản trị cung cấp.
- Tìm truy vấn quét bảng lớn, đọc nhiều cột không cần thiết hoặc lặp lại cùng một lần đọc.
- Kiểm tra tác vụ nền như backup, batch import, vacuum, checkpoint hoặc báo cáo chạy đồng thời, tùy hệ quản trị.

Nếu truy vấn đọc hàng triệu dòng để trả về vài dòng, cần xem lại điều kiện lọc, chỉ mục và cách lấy dữ liệu. Nếu lượng I/O hợp lý nhưng thiết bị có độ trễ cao hoặc hàng đợi dài, cần điều tra tầng lưu trữ và các tác vụ cạnh tranh I/O.

### Chờ khóa và tranh chấp giao dịch

Khóa giúp duy trì tính nhất quán khi nhiều giao dịch cùng đọc và ghi dữ liệu. Tuy nhiên, giao dịch giữ khóa quá lâu hoặc nhiều giao dịch cập nhật cùng một vùng dữ liệu có thể làm các phiên khác phải chờ.

Các tình huống thường gặp:

- Một giao dịch mở lâu nhưng chưa commit hoặc rollback.
- Ứng dụng thực hiện thao tác mạng hoặc chờ người dùng trong khi giao dịch vẫn mở.
- Nhiều giao dịch cập nhật cùng một dòng, tài khoản tổng hợp hoặc bản ghi trạng thái.
- Các giao dịch truy cập nhiều bảng theo thứ tự khác nhau, làm tăng nguy cơ deadlock.
- Một lệnh cập nhật diện rộng giữ nhiều khóa trong thời gian dài.

Cách điều tra:

1. Xác định phiên đang chờ và loại khóa đang chờ.
2. Tìm phiên chặn và thời điểm giao dịch bắt đầu.
3. Xem câu SQL đã chạy, phạm vi dòng bị tác động và trạng thái commit.
4. Kiểm tra vì sao giao dịch giữ khóa lâu: truy vấn chậm, xử lý ứng dụng nằm trong transaction, hoặc khối lượng cập nhật lớn.
5. Xem log deadlock và thứ tự truy cập tài nguyên nếu có.

Hướng cải thiện thường gồm rút ngắn thời gian giao dịch, chỉ giữ transaction quanh phần đọc ghi cần thiết, cập nhật theo lô phù hợp, thống nhất thứ tự truy cập tài nguyên và thiết kế lại điểm nóng ghi. Chỉ tăng timeout thường khiến thời gian chờ kéo dài hơn mà không giảm tranh chấp.

### Chờ kết nối

Một ứng dụng có thể chậm trước cả khi câu SQL được gửi đến cơ sở dữ liệu. Nếu mọi kết nối trong pool đang được sử dụng, yêu cầu mới phải đợi một kết nối được trả lại.

Hãy đo riêng thời gian lấy kết nối, thời gian giữ kết nối và thời gian thực thi SQL. Kiểm tra kích thước pool, số pool trên từng instance ứng dụng, số instance đang chạy và giới hạn kết nối của cơ sở dữ liệu. Tăng pool một cách tùy tiện có thể làm số phiên đồng thời tăng mạnh, khiến CPU, bộ nhớ hoặc khóa chịu áp lực lớn hơn.

### Chờ bộ nhớ và vùng nhớ tạm

Sort, hash join, hash aggregate và một số thao tác khác cần bộ nhớ làm việc. Khi không đủ bộ nhớ, hệ quản trị có thể ghi dữ liệu trung gian ra đĩa tạm. Dấu hiệu có thể gồm lượng temp read/write tăng, thời gian sort/hash cao và I/O tạm xuất hiện trong lúc truy vấn chạy.

Kiểm tra kế hoạch thực thi, số dòng trung gian, kích thước dữ liệu và cấu hình bộ nhớ áp dụng cho từng truy vấn hoặc phiên. Tăng bộ nhớ có thể giúp trong một số trường hợp, nhưng nếu quá nhiều truy vấn đồng thời cùng nhận mức cấp phát lớn, tổng mức tiêu thụ bộ nhớ có thể vượt giới hạn máy chủ.

## 5. Đọc thống kê truy vấn và kế hoạch thực thi

Thống kê truy vấn giúp trả lời câu hỏi hệ thống đang tiêu tốn thời gian ở đâu. Hãy xem cả số lần gọi, tổng thời gian và lượng dữ liệu đọc. Một truy vấn có thời gian trung bình thấp vẫn đáng quan tâm nếu được gọi với tần suất rất cao.

Ví dụ dưới đây dùng PostgreSQL để minh họa cách tìm các mẫu truy vấn có tổng thời gian thực thi lớn. Tên cột và khả năng thống kê có thể khác theo phiên bản hoặc hệ quản trị:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_read,
    shared_blks_hit,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

Kết quả cần được diễn giải theo bối cảnh:

- `calls` cao cho biết mẫu SQL được gọi thường xuyên.
- `total_exec_time` cao cho biết mẫu SQL tiêu thụ nhiều thời gian cộng dồn.
- `mean_exec_time` cao gợi ý mỗi lần thực thi tương đối chậm.
- `shared_blks_read` cao cho biết có nhiều block phải được nạp vào shared buffer; chỉ số này không tự khẳng định toàn bộ dữ liệu được đọc vật lý từ thiết bị lưu trữ.
- `temp_blks_read` và `temp_blks_written` cao có thể gợi ý thao tác trung gian dùng vùng nhớ tạm.

Các bộ đếm có thể được reset và có thể tích lũy qua một khoảng thời gian khác với khoảng xảy ra sự cố. Vì vậy, hãy ghi nhận thời điểm lấy mẫu, thời gian tích lũy và cách reset thống kê trước khi so sánh.

Để xem phiên đang hoạt động và sự kiện chờ, PostgreSQL có thể cung cấp dữ liệu từ `pg_stat_activity`:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS elapsed
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
```

Đây là ví dụ quan sát phiên tại một thời điểm. Cần lấy nhiều mẫu theo thời gian để phân biệt một lần chờ ngắn với trạng thái chờ kéo dài. Khi điều tra khóa, hãy nối thông tin phiên chờ với phiên chặn bằng cơ chế phù hợp của hệ quản trị.

Khi đã xác định được câu SQL đáng chú ý, xem kế hoạch thực thi. Với PostgreSQL, ví dụ cho một truy vấn đọc:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

`EXPLAIN` cho biết kế hoạch được chọn; `ANALYZE` thực thi câu truy vấn và ghi nhận số liệu thực tế; `BUFFERS` cho biết hoạt động truy cập buffer. Vì `ANALYZE` thực sự chạy truy vấn, hãy cân nhắc tải phát sinh và chỉ dùng với câu đọc an toàn trong môi trường phù hợp. Cú pháp và chi tiết đầu ra thay đổi theo hệ quản trị.

Khi đọc kết quả, tập trung vào:

- **Actual rows so với estimated rows:** sai lệch lớn có thể khiến bộ tối ưu chọn sai thứ tự join hoặc phương pháp truy cập.
- **Số vòng lặp (loops):** một node có thể chạy nhiều lần trong nested loop; chi phí mỗi vòng nhỏ nhưng tổng chi phí lớn.
- **Seq scan và index scan:** quét tuần tự không phải lúc nào cũng xấu. Với bảng nhỏ hoặc truy vấn đọc phần lớn bảng, sequential scan có thể rẻ hơn dùng chỉ mục.
- **Buffer hit/read:** giúp nhận diện lượng dữ liệu được phục vụ từ bộ nhớ và lượng phải đọc từ lưu trữ.
- **Sort, hash và temporary I/O:** xem kích thước dữ liệu trung gian, bộ nhớ được cấp và việc tràn ra đĩa.
- **Join order và điều kiện join:** kiểm tra xem các tập dữ liệu lớn có được thu hẹp trước khi kết hợp hay không.

Không nên chọn một chỉ mục chỉ vì thấy node sequential scan. Hãy xét số dòng được chọn, độ chọn lọc, kích thước bảng, chi phí duy trì chỉ mục và các truy vấn ghi. Một chỉ mục mới có thể cải thiện truy vấn đọc nhưng làm tăng dung lượng lưu trữ và chi phí insert/update/delete.

## 6. Bảng định hướng chẩn đoán

| Dấu hiệu quan sát | Giả thuyết ưu tiên | Bằng chứng xác nhận | Việc nên thử |
|---|---|---|---|
| Một query fingerprint có p95 tăng, các query khác ổn định | Truy vấn hoặc kế hoạch thực thi kém | Actual rows, buffers, loops, thời gian theo mẫu SQL | Tối ưu SQL, kiểm tra thống kê và chỉ mục |
| Một truy vấn có mean thấp nhưng tổng thời gian cao | Tần suất gọi quá lớn | Calls và total execution time | Giảm gọi lặp, gom truy vấn, phân trang hoặc batch phù hợp |
| Nhiều truy vấn cùng chậm, CPU cao và throughput không tăng | Bão hòa CPU hoặc quá nhiều concurrency | CPU, runnable queue, số phiên hoạt động, mẫu SQL tiêu thụ CPU | Giảm công việc không cần thiết, giới hạn concurrency, tối ưu truy vấn chi phối |
| Nhiều truy vấn chậm cùng lúc, I/O latency tăng | Nút thắt lưu trữ hoặc tải đọc ghi quá lớn | IOPS, hàng đợi, read/write latency, block reads | Giảm dữ liệu đọc ghi, xem tác vụ cạnh tranh I/O, đánh giá lưu trữ |
| Một nhóm phiên có lock wait kéo dài | Tranh chấp giao dịch | Phiên chặn, transaction age, lock graph hoặc wait event | Rút ngắn transaction, giảm điểm nóng ghi, thống nhất thứ tự cập nhật |
| API chậm nhưng SQL chạy nhanh | Chờ connection pool hoặc xử lý ngoài DB | Pool wait, connection usage, thời gian mạng và ứng dụng | Điều chỉnh vòng đời kết nối và luồng gọi |
| Temp I/O tăng cùng truy vấn sort/hash | Áp lực bộ nhớ làm việc hoặc tập trung gian quá lớn | Kế hoạch sort/hash, temp blocks, số dòng trung gian | Giảm dữ liệu trung gian, xem lại join/sort và cấu hình bộ nhớ |

Bảng này dùng để chọn hướng kiểm tra đầu tiên. Một dấu hiệu chỉ tạo ra giả thuyết; cần dữ liệu đo được để xác nhận.

## 7. Ví dụ thực tế

### Tình huống A: Một truy vấn báo cáo chậm

Một báo cáo trước đây hoàn thành trong 300 ms, nay mất 4 giây. Các API khác vẫn ổn định, CPU và I/O tổng thể không tăng đáng kể. Thống kê cho thấy mẫu SQL này có thời gian trung bình tăng. Kế hoạch thực thi ghi nhận bảng lớn bị quét tuần tự, trong khi điều kiện lọc chỉ trả về một tỷ lệ rất nhỏ dữ liệu; số dòng thực tế cũng lệch xa ước lượng.

Cách xử lý hợp lý:

1. Kiểm tra điều kiện lọc và kiểu dữ liệu tham số để bảo đảm điều kiện có thể tận dụng đường truy cập phù hợp.
2. Xác minh thống kê của bảng và phân bố dữ liệu.
3. Đánh giá chỉ mục phù hợp với điều kiện lọc và thứ tự sắp xếp, dựa trên các truy vấn đọc lẫn ghi đang có.
4. Chạy lại truy vấn trong điều kiện đo tương đương, so sánh actual rows, buffers và p95.
5. Kiểm tra các truy vấn liên quan để bảo đảm thay đổi không làm tăng đáng kể chi phí ghi hoặc dung lượng.

Kết luận ở đây hướng đến truy vấn và kế hoạch thực thi vì phạm vi ảnh hưởng hẹp và bằng chứng tập trung vào một mẫu SQL.

### Tình huống B: Toàn hệ thống chậm vào giờ cao điểm

Vào đầu giờ làm việc, nhiều chức năng cùng chậm. Số yêu cầu và số phiên đồng thời tăng mạnh; CPU duy trì gần mức tối đa; throughput không tăng dù số yêu cầu tiếp tục tăng. Nhiều mẫu SQL khác nhau đều có độ trễ cao.

Cần kiểm tra phân bố tải theo ứng dụng và mẫu SQL, tìm tác vụ nền chạy trùng giờ cao điểm, xem số kết nối từ từng instance và xác định nhóm công việc chiếm nhiều CPU. Các biện pháp có thể gồm giới hạn concurrency ở ứng dụng, dàn lịch batch sang thời điểm khác, loại bỏ truy vấn dư thừa, giảm dữ liệu xử lý và mở rộng năng lực khi đã xác nhận nhu cầu dài hạn.

Chỉ tăng số kết nối trong tình huống này có thể làm nhiều truy vấn tranh CPU hơn và khiến hệ thống quá tải nhanh hơn.

### Tình huống C: CPU thấp nhưng thao tác cập nhật vẫn treo

Một thao tác cập nhật đơn hàng mất nhiều giây. CPU cơ sở dữ liệu thấp, nhưng phiên thực thi có wait event liên quan đến khóa. Điều tra cho thấy một giao dịch khác đã mở từ lâu và đang giữ khóa trên bản ghi cần cập nhật.

Cần tìm phiên giữ khóa, xác định giao dịch bắt đầu khi nào và vì sao chưa kết thúc. Nếu ứng dụng giữ transaction trong lúc gọi dịch vụ bên ngoài hoặc chờ thao tác người dùng, hãy thu hẹp phạm vi transaction để khóa được giải phóng sớm. Sau khi sửa, kiểm tra thời gian giữ khóa và phân vị độ trễ của các thao tác cập nhật đồng thời.

Tăng CPU hoặc thêm chỉ mục không giải quyết trực tiếp một phiên đang đợi khóa. Bằng chứng về wait event và phiên chặn mới là căn cứ cho hướng xử lý.

## 8. Kiểm chứng sau khi điều chỉnh

Một thay đổi chỉ được xem là có hiệu quả khi số liệu sau thay đổi cải thiện trong điều kiện có thể so sánh. Trước khi áp dụng, ghi lại các chỉ số ban đầu; sau khi áp dụng, đo lại cùng mẫu truy vấn, cùng khung tải và cùng khoảng thời gian.

Nên kiểm chứng ít nhất:

- p50, p95, p99 và số lần thực thi của truy vấn hoặc nghiệp vụ mục tiêu.
- Throughput và số phiên đồng thời để bảo đảm độ trễ giảm không phải vì tải đã giảm.
- CPU, bộ nhớ, I/O và thời gian chờ để xem nút thắt có chuyển sang tài nguyên khác không.
- Actual rows, buffers, loops và thời gian node trong kế hoạch thực thi, nếu thay đổi liên quan đến SQL hoặc chỉ mục.
- Lock wait, thời gian giao dịch và số deadlock nếu thay đổi liên quan đến ghi hoặc transaction.
- Chi phí phụ: dung lượng chỉ mục, thời gian ghi, thời gian batch, tải nền và ảnh hưởng đến các truy vấn khác.

Thực hiện thay đổi có phạm vi nhỏ, ghi lại cấu hình hoặc câu SQL trước và sau, rồi so sánh kết quả. Nếu một chỉ số tốt lên nhưng chỉ số khác xấu đi, cần đánh giá tác động tổng thể. Ví dụ, thêm chỉ mục có thể giảm thời gian đọc nhưng tăng thời gian ghi; tăng bộ nhớ cho sort có thể giảm temp I/O nhưng làm tăng mức dùng RAM khi nhiều truy vấn chạy đồng thời.

## 9. Những lỗi chẩn đoán thường gặp

- **Chỉ nhìn thời gian trung bình:** có thể bỏ qua p95/p99 hoặc một nhóm yêu cầu bị chậm nặng.
- **Chỉ nhìn CPU:** CPU thấp vẫn có thể đi kèm chờ khóa, I/O hoặc kết nối; CPU cao cũng cần được đối chiếu với throughput và hàng đợi.
- **Thấy truy vấn chậm là thêm chỉ mục:** chỉ mục không phù hợp có thể không được dùng, làm tăng chi phí ghi và dung lượng.
- **Thấy nhiều phiên là tăng pool:** nhiều kết nối hơn có thể làm tăng tranh chấp và số công việc đồng thời.
- **Hủy phiên đang chờ mà không tìm phiên chặn:** vấn đề có thể tiếp tục với các phiên khác.
- **So sánh số liệu ở hai mức tải khác nhau:** kết quả không đủ cơ sở để kết luận thay đổi đã cải thiện hiệu năng.
- **Chạy benchmark mà không ghi lại dữ liệu và cấu hình:** kết quả khó tái lập và khó giải thích.
- **Thay nhiều yếu tố cùng lúc:** không thể xác định thay đổi nào tạo ra tác động và khó quay lại trạng thái ổn định.

## 10. Checklist chẩn đoán

Khi nhận báo cáo cơ sở dữ liệu chậm, hãy tự kiểm tra lần lượt:

1. Đã xác định đúng thao tác, khoảng thời gian và nơi đo độ trễ chưa?
2. Một mẫu SQL bị ảnh hưởng hay nhiều mẫu SQL cùng chậm?
3. p50, p95, p99, số lần gọi và throughput thay đổi ra sao?
4. CPU, bộ nhớ, I/O, kết nối và hàng đợi có biến động cùng thời điểm không?
5. Có wait event hoặc giao dịch chặn nào giải thích được thời gian chậm không?
6. Thống kê truy vấn cho thấy mẫu SQL nào tiêu thụ tổng thời gian hoặc đọc dữ liệu nhiều nhất?
7. Kế hoạch thực thi có sai lệch ước lượng, đọc quá nhiều dòng hoặc tạo dữ liệu trung gian lớn không?
8. Giả thuyết nguyên nhân có bằng chứng trực tiếp và có thể kiểm chứng không?
9. Sau điều chỉnh, độ trễ và throughput có cải thiện ở cùng điều kiện tải không?
10. Có tác động phụ lên truy vấn khác, giao dịch ghi, bộ nhớ hoặc lưu trữ không?

Nếu chưa có đủ bằng chứng, hãy ghi rõ điều đã quan sát, giả thuyết đang kiểm tra và số liệu còn thiếu. Cách làm này giúp nhóm vận hành tránh thay đổi cấu hình theo cảm tính và giữ được khả năng giải thích kết quả.

## Kết luận

Truy vấn chậm tập trung vào một câu SQL hoặc một nhóm nhỏ mẫu truy vấn; hệ thống quá tải phản ánh tổng khối lượng công việc vượt năng lực phục vụ; thời gian chờ tài nguyên cho biết truy vấn đang bị giữ lại bởi khóa, I/O, kết nối, bộ nhớ hoặc cơ chế đồng bộ. Ba hiện tượng có thể liên quan và khuếch đại lẫn nhau.

Một quy trình chẩn đoán đáng tin cậy bắt đầu từ phạm vi ảnh hưởng, đo độ trễ cùng tải, phân tích thống kê truy vấn và sự kiện chờ, sau đó đọc kế hoạch thực thi khi có dấu hiệu truy vấn là nguyên nhân. Mỗi điều chỉnh cần có số liệu trước và sau để chứng minh tác động. Đây là nền tảng để tối ưu cơ sở dữ liệu có kiểm soát, giảm rủi ro và duy trì hiệu năng ổn định khi dữ liệu cũng như lưu lượng tăng lên.

