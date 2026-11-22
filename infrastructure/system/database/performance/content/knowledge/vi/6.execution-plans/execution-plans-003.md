# Đọc số hàng, chi phí ước lượng, thời gian thực tế và lượng dữ liệu trung gian

## 1. Vì sao cần đọc các con số trong kế hoạch thực thi?

Kế hoạch thực thi (execution plan) cho biết hệ quản trị cơ sở dữ liệu dự định hoặc đã thực hiện những bước nào để trả về kết quả truy vấn. Kế hoạch có thể gồm quét bảng, tìm kiếm qua chỉ mục, lọc dòng, nối bảng, sắp xếp, nhóm dữ liệu và ghi dữ liệu trung gian ra vùng lưu trữ tạm.

Tên toán tử chỉ cho biết loại công việc. Các con số đi kèm mới giúp ta đánh giá quy mô và hiệu quả của từng bước: hệ thống dự đoán bao nhiêu dòng, đã xử lý bao nhiêu dòng, chi phí mà bộ tối ưu gán cho kế hoạch là bao nhiêu, thời gian thực thi được đo ra sao và bao nhiêu dữ liệu trung gian phải đi qua bộ nhớ hoặc đĩa.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần đọc các số liệu này cùng với thống kê, chỉ mục, điều kiện lọc, cơ chế nối và tài nguyên CPU, bộ nhớ, I/O. Một kế hoạch có chi phí ước lượng thấp vẫn có thể chạy chậm nếu thống kê sai hoặc dữ liệu thực tế khác giả định của bộ tối ưu. Ngược lại, chi phí ước lượng cao hơn không tự động chứng minh truy vấn chậm nếu hai kế hoạch được so sánh trong điều kiện khác nhau.

Bài học này tập trung vào bốn nhóm thông tin: số hàng (row count/cardinality), chi phí ước lượng (estimated cost), thời gian thực tế (actual time) và lượng dữ liệu trung gian (intermediate data volume). Cách hiển thị cụ thể phụ thuộc hệ quản trị và công cụ, nhưng nguyên tắc đọc và đối chiếu có thể áp dụng rộng rãi.

## 2. Phân biệt kế hoạch ước lượng và kế hoạch thực tế

Hầu hết hệ quản trị cung cấp cách xem kế hoạch mà không thực thi truy vấn, thường được gọi là `EXPLAIN` hoặc estimated execution plan. Một số hệ thống còn cung cấp chế độ thực thi và ghi lại số liệu thực tế, chẳng hạn `EXPLAIN ANALYZE`, actual execution plan hoặc tính năng tương đương.

- **Kế hoạch ước lượng** mô tả lựa chọn của bộ tối ưu dựa trên câu SQL, chỉ mục, thống kê và các giả định về dữ liệu. Nó thường có số hàng và chi phí ước lượng, nhưng không có thời gian thực thi thực tế.
- **Kế hoạch thực tế** được thu thập khi truy vấn chạy. Ngoài cấu trúc kế hoạch, nó có thể ghi số hàng thực tế, số vòng lặp, thời gian, số lần đọc trang, bộ nhớ và hoạt động trên vùng lưu trữ tạm.

Không phải mọi hệ quản trị đều hiển thị cùng trường hoặc dùng cùng quy ước. Một số công cụ ghi thời gian tại từng toán tử; một số hiển thị thời gian CPU và thời gian trôi qua; một số ghi số hàng trung bình mỗi vòng lặp. Hãy đọc chú giải của đúng hệ quản trị và phiên bản trước khi tính toán hoặc so sánh.

**Lưu ý về an toàn:** chế độ đo thực tế thường thực thi truy vấn. Truy vấn đọc có thể tiêu tốn nhiều CPU, bộ nhớ và I/O; truy vấn ghi có thể thay đổi dữ liệu. Trước khi dùng trên môi trường production, hãy đánh giá phạm vi dữ liệu, tải hiện tại, thời gian chạy và tác động của câu lệnh. Bắt đầu bằng kế hoạch ước lượng; dùng môi trường thử nghiệm hoặc cửa sổ tải phù hợp để thu thập số liệu thực tế. Không giả định rằng bọc một câu lệnh trong transaction rồi rollback sẽ đảo ngược mọi tác động phụ.

## 3. Đọc số hàng ước lượng và số hàng thực tế

### 3.1. Số hàng (cardinality)

Số hàng tại một toán tử là số dòng mà toán tử dự kiến tạo ra hoặc thực tế tạo ra. Đây là thông tin nền tảng vì bộ tối ưu thường dùng cardinality để lựa chọn cách truy cập và thứ tự nối bảng.

Ví dụ, nếu điều kiện lọc chỉ giữ lại 1% số dòng, bộ tối ưu có thể cân nhắc dùng chỉ mục để tránh quét toàn bộ bảng. Nếu một phép nối dự kiến tạo ra vài trăm dòng nhưng thực tế tạo ra hàng triệu dòng, kế hoạch đã được lựa chọn trên một giả định sai lệch lớn.

Trong kế hoạch ước lượng, hãy tìm trường có tên như `rows`, `estimated rows` hoặc `cardinality`. Trong kế hoạch thực tế, trường tương ứng có thể là `actual rows`, `rows produced` hoặc tên riêng của công cụ.

### 3.2. So sánh ước lượng với thực tế

Với mỗi toán tử, so sánh số hàng ước lượng và số hàng thực tế. Có thể dùng tỷ lệ sai lệch:

\[
\text{Sai lệch} = \frac{\max(\text{ước lượng},\text{thực tế})}{\max(\min(\text{ước lượng},\text{thực tế}),\epsilon)}
\]

Trong đó \(\epsilon\) là giá trị nhỏ dùng để tránh chia cho 0 khi trình bày tỷ lệ. Khi ước lượng và thực tế đều lớn hơn 0, cách đọc đơn giản hơn là lấy số lớn chia số nhỏ. Ví dụ, ước lượng 1.000 dòng nhưng thực tế 50.000 dòng là sai lệch 50 lần.

Sai lệch lớn là tín hiệu cần điều tra, đặc biệt ở các toán tử gần đầu vào của kế hoạch. Nếu một bước lọc tạo ra nhiều dòng hơn dự kiến, các bước nối, sắp xếp hoặc tổng hợp phía trên có thể phải xử lý nhiều dữ liệu hơn và tiêu tốn thêm tài nguyên.

Không nên chỉ nhìn toán tử cuối cùng. Hãy tìm **điểm sai lệch đầu tiên** từ các nhánh đầu vào đi lên. Nếu một phép quét đã ước lượng sai mạnh, lỗi đó có thể lan truyền qua nhiều phép nối. Sửa toán tử phía trên mà bỏ qua nguyên nhân ở đầu vào thường không giải quyết được vấn đề gốc.

### 3.3. Số vòng lặp và số hàng mỗi vòng

Một số toán tử có thể chạy nhiều lần. Ví dụ, trong nested loop join, truy vấn đọc một dòng từ nhánh ngoài rồi tra cứu nhánh trong; thao tác tra cứu nhánh trong được lặp lại cho từng dòng của nhánh ngoài.

Nếu kế hoạch cho biết một toán tử tạo trung bình 3 dòng mỗi vòng và chạy 2.000 vòng, tổng lượng dòng đi qua toán tử xấp xỉ:

\[
3 \times 2.000 = 6.000\text{ dòng}
\]

Trong một số định dạng kế hoạch, `actual rows` là số trung bình mỗi vòng lặp; trong định dạng khác, công cụ có thể hiển thị tổng hoặc cách tổng hợp riêng. Đừng nhân hoặc cộng máy móc trước khi xác nhận quy ước. Với kế hoạch kiểu PostgreSQL, trường `actual rows` thường được hiển thị theo trung bình mỗi loop, còn `loops` cho biết số vòng lặp.

Số vòng lặp rất quan trọng khi đánh giá nested loop. Một phép tra cứu chỉ mục có vẻ rẻ khi chạy một lần nhưng có thể trở thành chi phí lớn khi bị lặp hàng trăm nghìn lần. Hãy xem đồng thời số hàng của nhánh ngoài, số vòng lặp của nhánh trong, số hàng trả về mỗi vòng và thời gian thực tế.

## 4. Đọc chi phí ước lượng

### 4.1. Chi phí là điểm số của bộ tối ưu

Chi phí (cost) là điểm số mà bộ tối ưu dùng để so sánh các phương án thực thi. Mô hình chi phí có thể tính đến đọc trang dữ liệu, truy cập chỉ mục, CPU, so sánh, xử lý hàng và các yếu tố khác. Công thức và đơn vị khác nhau theo hệ quản trị, cấu hình và phiên bản.

Chi phí thường **không phải thời gian tính bằng mili giây**. Không nên đọc `cost=500` thành truy vấn sẽ chạy 500 ms, cũng không nên so sánh trực tiếp cost giữa hai hệ quản trị hoặc hai môi trường có cấu hình khác nhau.

Chi phí hữu ích nhất khi so sánh các phương án trong cùng hệ thống và điều kiện tương đương. Nếu một thay đổi làm bộ tối ưu chọn kế hoạch có cost thấp hơn, đó là tín hiệu về dự đoán của bộ tối ưu, chưa phải bằng chứng truy vấn thực tế đã nhanh hơn.

### 4.2. Startup cost và total cost

Một số hệ quản trị hiển thị chi phí khởi động (startup cost) và chi phí toàn phần (total cost):

- **Startup cost** ước lượng công việc cần làm trước khi toán tử có thể trả dòng đầu tiên. Sắp xếp toàn bộ đầu vào thường có startup cost đáng kể vì phải đọc và sắp xếp dữ liệu trước khi phát ra kết quả.
- **Total cost** ước lượng công việc để toán tử hoàn tất toàn bộ đầu ra.

Hai giá trị giúp phân biệt truy vấn cần kết quả đầu tiên nhanh với truy vấn cần xử lý hết tập kết quả. Với truy vấn có `LIMIT`, bộ tối ưu có thể ưu tiên phương án có startup cost thấp để trả một số dòng sớm, ngay cả khi total cost của phương án đó không thấp nhất cho toàn bộ tập dữ liệu.

Trong một số hệ quản trị, cost ở nút cha đã bao gồm chi phí của các nút con. Vì vậy, không cộng cost của nút cha với cost của từng nút con để suy ra tổng chi phí kế hoạch. Cần hiểu cách công cụ trình bày chi phí trước khi tổng hợp.

### 4.3. Khi nào cost thay đổi đáng chú ý?

Cost có thể thay đổi khi dữ liệu lớn lên, thống kê được cập nhật, chỉ mục được thêm hoặc xóa, điều kiện lọc thay đổi, tham số truy vấn khác đi hoặc cấu hình bộ tối ưu thay đổi. Hãy xem thay đổi đó có dẫn đến một kế hoạch khác hay không, chẳng hạn:

- Quét toàn bảng chuyển thành index scan hoặc ngược lại.
- Thứ tự nối bảng thay đổi.
- Nested loop chuyển thành hash join hoặc merge join.
- Sắp xếp hoặc nhóm dữ liệu được thực hiện bằng cách khác.
- Một bước trung gian bắt đầu ghi ra vùng lưu trữ tạm.

Đừng tối ưu chỉ để giảm một con số cost. Hãy xác nhận kế hoạch mới xử lý đúng dữ liệu, có số đo thực tế tốt hơn và không làm truy vấn khác bị suy giảm do thay đổi chỉ mục, thống kê hoặc tài nguyên dùng chung.

## 5. Đọc thời gian thực tế

### 5.1. Thời gian tại toán tử và thời gian toàn truy vấn

Kế hoạch thực tế có thể cung cấp thời gian tại từng toán tử và thời gian tổng thể. Các tên thường gặp gồm `actual time`, elapsed time, execution time hoặc duration. Thời gian ở một toán tử có thể gồm công việc của các nút con tùy cách công cụ đo và hiển thị; vì vậy không nên cộng tất cả thời gian của mọi nút để suy ra thời gian truy vấn.

Một số định dạng hiển thị thời gian bắt đầu phát dòng đầu tiên và thời gian hoàn tất phát dòng cuối cùng. Một số định dạng khác cung cấp CPU time, elapsed time hoặc thời gian trung bình mỗi lần thực thi. Cần phân biệt:

- **Thời gian trả dòng đầu tiên:** hữu ích với truy vấn streaming hoặc ứng dụng hiển thị kết quả từng phần.
- **Thời gian hoàn tất:** thời gian để truy vấn xử lý xong toàn bộ công việc trong phạm vi đo.
- **CPU time:** lượng thời gian CPU tiêu thụ; tổng CPU có thể lớn hơn thời gian trôi qua khi có xử lý song song.
- **Elapsed time:** thời gian đồng hồ thực tế từ lúc bắt đầu đến lúc hoàn tất trong điều kiện đo.

Thời gian thực tế chịu ảnh hưởng của cache, tải đồng thời, khóa, I/O, lịch CPU, mạng, cấu hình, kích thước bộ nhớ và overhead của công cụ đo. Một lần chạy nhanh hơn chưa đủ để kết luận một thay đổi đã cải thiện hiệu năng ổn định.

### 5.2. Kết hợp thời gian với số hàng và loops

Một toán tử có thời gian nhỏ trong một lần chạy vẫn có thể tiêu tốn nhiều thời gian tổng nếu được gọi rất nhiều lần. Ngược lại, một toán tử có thời gian lớn có thể chỉ là nút cha đang tổng hợp thời gian của các bước con.

Khi xem thời gian tại một toán tử, hãy đối chiếu với số hàng thực tế, số vòng lặp, số hàng mỗi vòng và thời gian của nhánh con. Đối với nested loop, cần đặc biệt chú ý phép tra cứu bên trong bị lặp nhiều lần. Đối với sort hoặc hash, hãy xem thời gian tăng ở bước chuẩn bị, bước xử lý hay bước phát kết quả.

### 5.3. Thận trọng khi đo

Thu thập kế hoạch thực tế có thể tạo overhead do ghi thời gian, đếm dòng hoặc thu thập buffer. Truy vấn chạy song song cũng có thể có số liệu theo worker và số liệu tổng hợp khác nhau. Khi so sánh trước và sau, hãy dùng cùng phương thức đo, cùng dữ liệu, tham số, mức tải và trạng thái cache gần tương đương; chạy lặp lại đủ để phân biệt cải thiện thật với dao động ngẫu nhiên.

## 6. Ước lượng lượng dữ liệu trung gian

### 6.1. Số dòng chưa nói hết kích thước dữ liệu

Hai toán tử cùng tạo 100.000 dòng có thể tiêu tốn bộ nhớ rất khác nhau nếu một toán tử chỉ mang vài cột số nhỏ, còn toán tử kia mang nhiều cột văn bản hoặc dữ liệu lớn. Có thể ước lượng sơ bộ kích thước dữ liệu trung gian bằng:

\[
\text{Dung lượng gần đúng} \approx \text{số dòng} \times \text{độ rộng dòng trung bình}
\]

Trong kế hoạch, độ rộng dòng có thể xuất hiện dưới tên `width`, estimated row size hoặc thông tin tương đương. Đây là ước lượng để so sánh, không phải số byte chính xác của bộ nhớ thực tế. Kích thước thực còn phụ thuộc overhead của tuple/row, cấu trúc hash, con trỏ, alignment, encoding và cách hệ quản trị lưu trữ dữ liệu.

Ví dụ, một toán tử dự kiến tạo 200.000 dòng với độ rộng 160 byte. Dung lượng dữ liệu thô ước tính là:

\[
200.000 \times 160 = 32.000.000\text{ byte} \approx 30{,}5\text{ MiB}
\]

Nếu số dòng thực tế tăng lên 2.000.000, phần dữ liệu thô đã xấp xỉ 305 MiB. Cấu trúc hash hoặc sort có thể cần thêm bộ nhớ ngoài kích thước dòng. Điều này có thể vượt giới hạn bộ nhớ dành cho toán tử và khiến hệ thống phải chia nhỏ công việc hoặc ghi dữ liệu tạm ra đĩa.

### 6.2. Các toán tử thường tạo dữ liệu trung gian lớn

- **Sort:** cần tổ chức các dòng theo thứ tự. Nếu dữ liệu vượt ngân sách bộ nhớ, thao tác sắp xếp có thể tạo các run tạm và trộn từ đĩa.
- **Hash join:** xây dựng bảng băm từ một nhánh đầu vào. Kích thước nhánh build, số dòng thực tế và độ rộng dòng ảnh hưởng mạnh đến bộ nhớ.
- **Hash aggregate/group by:** giữ trạng thái cho các nhóm. Số nhóm thực tế lớn hơn dự kiến có thể làm tăng bộ nhớ hoặc phát sinh spill.
- **Materialize/spool:** lưu kết quả trung gian để dùng lại hoặc hỗ trợ một chiến lược thực thi. Số lần đọc lại và kích thước lưu trữ có thể đáng kể.
- **Join:** có thể làm số dòng tăng mạnh khi khóa nối không duy nhất hoặc dữ liệu có quan hệ nhiều-nhiều. Số dòng đầu ra có thể lớn hơn nhiều so với từng đầu vào.

Hãy tìm toán tử nào tạo ra nhiều dòng hoặc dòng rộng trước khi lọc, sắp xếp, nối hay nhóm. Đưa điều kiện lọc xuống gần nguồn dữ liệu hơn, loại bỏ cột không cần thiết hoặc cải thiện điều kiện nối có thể giảm lượng dữ liệu phải truyền qua các bước sau, nếu việc thay đổi vẫn giữ nguyên ngữ nghĩa truy vấn.

### 6.3. Nhận biết spill và I/O tạm

Khi dữ liệu trung gian vượt ngân sách bộ nhớ, một số toán tử có thể ghi ra vùng lưu trữ tạm. Tên trường tùy hệ quản trị, ví dụ temp read/write, disk-based sort, hash batches, spill, workfile hoặc temporary tablespace.

Nếu kế hoạch cho thấy sort hoặc hash spill, hãy kiểm tra đồng thời:

1. Số hàng thực tế và độ rộng dữ liệu ở đầu vào toán tử.
2. Số nhóm hoặc số khóa băm được tạo.
3. Bộ nhớ được cấp và giới hạn bộ nhớ cho mỗi toán tử hoặc mỗi truy vấn.
4. Số byte hoặc block tạm đã đọc/ghi, nếu công cụ cung cấp.
5. Số worker và số thao tác đồng thời có thể cùng sử dụng bộ nhớ.

Tăng bộ nhớ có thể giảm spill, nhưng tăng quá cao có thể làm nhiều truy vấn đồng thời tranh chấp RAM hoặc gây áp lực lên hệ điều hành. Trước khi điều chỉnh, cần xác định dữ liệu trung gian phình to do ước lượng sai, truy vấn xử lý quá nhiều cột/dòng hay do giới hạn bộ nhớ chưa phù hợp.

## 7. Ví dụ phân tích một kế hoạch

Giả sử một truy vấn nối khách hàng với đơn hàng đang hoạt động. Kế hoạch rút gọn dưới đây chỉ minh họa cách đọc; cú pháp và tên trường không đại diện cho một hệ quản trị cụ thể:

```text
Hash Join
  estimated rows: 800
  actual rows:    48,000
  estimated cost: 2,400
  actual time:    1,850 ms
  Hash
    estimated rows: 1,200
    actual rows:    72,000
    actual width:   180 bytes
    temp writes:    present
    Scan orders
      estimated rows after filter: 1,200
      actual rows after filter:    72,000
  Scan customers
    estimated rows: 800
    actual rows:    800
```

Ta có thể rút ra các câu hỏi theo thứ tự:

1. Nhánh quét `orders` dự kiến 1.200 dòng nhưng thực tế có 72.000 dòng, sai lệch 60 lần. Đây là điểm sai lệch lớn đầu tiên cần điều tra.
2. Nhánh khách hàng có số dòng ước lượng và thực tế khớp nhau. Vì vậy, dữ liệu khách hàng chưa phải nơi gây ra sai lệch cardinality trong ví dụ.
3. Hash join dự kiến 800 dòng nhưng thực tế tạo 48.000 dòng. Số dòng đầu ra cao hơn dự kiến 60 lần, có thể do số đơn hàng phù hợp hoặc tính duy nhất của khóa nối khác giả định.
4. Nhánh hash có 72.000 dòng, độ rộng 180 byte. Dữ liệu thô đã xấp xỉ 12,96 MB trước overhead. Thông tin ghi tạm cho thấy cần kiểm tra bộ nhớ và hoạt động I/O tạm.
5. Thời gian 1.850 ms cho biết truy vấn có độ trễ đáng kể trong lần đo, nhưng chưa đủ để quy nguyên nhân cho hash join. Cần đọc thời gian của từng nhánh, buffer, temp I/O và các lần lặp để xác định công việc chiếm thời gian.

Điểm điều tra đầu tiên là điều kiện lọc trên `orders`. Hãy kiểm tra thống kê của cột lọc, thời điểm cập nhật thống kê, phân bố giá trị, độ lệch dữ liệu (skew), tham số thực tế và tương quan giữa các cột. Nếu bộ tối ưu giả định các điều kiện độc lập trong khi dữ liệu có tương quan, số dòng ước lượng có thể sai lớn. Sau khi xác định nguyên nhân, có thể cập nhật thống kê phù hợp, dùng thống kê mở rộng nếu hệ quản trị hỗ trợ, điều chỉnh truy vấn hoặc chỉ mục khi có cơ sở.

Tiếp theo, kiểm tra khóa nối có duy nhất hay không và số đơn hàng trung bình trên mỗi khách hàng. Nếu quan hệ thực tế là một-nhiều, số dòng sau join tăng là đúng về mặt dữ liệu; cần đánh giá truy vấn có thực sự cần toàn bộ các dòng đó không. Không nên thêm chỉ mục hoặc thay đổi thuật toán join chỉ vì thấy một toán tử có thời gian lớn mà chưa hiểu số dòng đầu vào.

## 8. Nguyên nhân phổ biến khiến ước lượng sai

| Nguyên nhân | Dấu hiệu trong kế hoạch | Hướng điều tra |
|---|---|---|
| Thống kê cũ hoặc thiếu | Ước lượng số dòng khác xa thực tế sau lọc | Kiểm tra thời điểm và phạm vi cập nhật thống kê; xem số liệu phân bố |
| Dữ liệu lệch (skew) | Một số giá trị phổ biến tạo ra nhiều dòng hơn phần còn lại | Kiểm tra histogram, tần suất giá trị phổ biến và tham số truy vấn |
| Các cột có tương quan | Ước lượng kết hợp nhiều điều kiện sai mạnh | Kiểm tra tương quan và thống kê đa cột nếu được hỗ trợ |
| Biểu thức hoặc hàm trên cột | Bộ tối ưu khó ước lượng độ chọn lọc của điều kiện | Xem thống kê biểu thức, kiểu dữ liệu, phép ép kiểu và khả năng dùng chỉ mục |
| Tham số thay đổi theo lần chạy | Cùng câu SQL nhưng cardinality thực tế thay đổi lớn | Kiểm tra parameter sniffing/plan caching và độ nhạy của kế hoạch theo tham số |
| Điều kiện nối không duy nhất | Số dòng sau join lớn hơn nhiều đầu vào | Kiểm tra khóa duy nhất, quan hệ một-nhiều/nhiều-nhiều và dữ liệu trùng |
| Thiếu thông tin về phân bố dữ liệu | Kế hoạch chọn thứ tự nối hoặc thuật toán không phù hợp | Đối chiếu thống kê, số dòng thực tế và các phương án kế hoạch khả thi |

Một kế hoạch sai lệch không nhất thiết do thiếu chỉ mục. Chỉ mục giúp truy cập dữ liệu theo cách khác, nhưng không tự sửa mọi ước lượng cardinality. Nếu thống kê hoặc giả định về phân bố sai, bộ tối ưu vẫn có thể chọn kế hoạch kém ngay cả khi đã có chỉ mục.

## 9. Quy trình đọc và điều tra execution plan

Hãy áp dụng trình tự sau để tránh tập trung quá sớm vào một toán tử:

1. **Xác định câu truy vấn và điều kiện chạy.** Ghi lại câu SQL, tham số, loại dữ liệu, mức tải, hệ quản trị và phiên bản. Đảm bảo đang phân tích đúng truy vấn cần tối ưu.
2. **Thu thập kế hoạch ước lượng.** Đọc cấu trúc cây từ các nhánh đầu vào đến nút gốc. Ghi lại số hàng, cost, kiểu truy cập, thứ tự join và các bước sort/hash/materialize.
3. **Thu thập kế hoạch thực tế an toàn.** Dùng môi trường thử nghiệm hoặc cách đo phù hợp để ghi số hàng thực tế, loops, thời gian, buffer và temp I/O. Xác nhận việc thu thập có thực thi câu lệnh hay không.
4. **Tìm sai lệch cardinality đầu tiên.** So sánh estimated rows với actual rows ở các toán tử đầu vào. Xem loops và quy ước hiển thị số hàng của công cụ.
5. **Đánh giá dữ liệu trung gian.** Ước lượng số dòng nhân độ rộng dòng; tìm sort/hash spill, temp read/write và các bước tạo nhiều dòng trước khi lọc.
6. **Đối chiếu thời gian và tài nguyên.** Xem thời gian toàn truy vấn, thời gian tại toán tử, CPU, buffer/cache hit, đọc vật lý, khóa và mức dùng bộ nhớ. Không cộng thời gian các nút nếu cách đo đã bao gồm thời gian nút con.
7. **Đặt giả thuyết có thể kiểm chứng.** Ví dụ: thống kê cũ làm sai số dòng; một điều kiện lọc có độ chọn lọc thấp; nested loop bị lặp quá nhiều; hash bị spill; truy vấn đọc các cột không cần thiết.
8. **Thay đổi có kiểm soát.** Điều chỉnh một yếu tố có giả thuyết rõ ràng, chẳng hạn cập nhật thống kê, viết lại điều kiện, bổ sung chỉ mục phù hợp hoặc giảm dữ liệu trung gian.
9. **Đo lại trong điều kiện tương đương.** So sánh kế hoạch, số hàng ước lượng/thực tế, loops, thời gian, buffer, temp I/O và kết quả truy vấn. Kiểm tra cả các truy vấn khác bị ảnh hưởng.

Khi ghi nhận kết quả, nên dùng một bảng nhất quán:

| Hạng mục | Trước điều chỉnh | Sau điều chỉnh |
|---|---:|---:|
| Số hàng ước lượng tại điểm lọc quan trọng | 1.200 | 70.000 |
| Số hàng thực tế tại điểm lọc | 72.000 | 72.000 |
| Sai lệch ước lượng/thực tế | 60 lần | gần 1 lần |
| Dữ liệu tạm ghi ra đĩa | Có | Không |
| Thời gian hoàn tất | 1.850 ms | 620 ms |
| Kết quả và số dòng trả về | Đúng | Đúng |

Các số liệu trong bảng là ví dụ minh họa. Nếu sau điều chỉnh số hàng thực tế không đổi nhưng số hàng ước lượng sát hơn, điều đó có thể giúp bộ tối ưu chọn kế hoạch tốt hơn. Tuy vậy, cần kiểm tra rằng thời gian giảm ổn định qua nhiều lần chạy và kết quả truy vấn vẫn đúng.

## 10. Những lỗi diễn giải thường gặp

- **Coi cost là mili giây:** cost là điểm số theo mô hình của bộ tối ưu. Dùng actual time và số đo vận hành để đánh giá thời gian thực tế.
- **Chỉ nhìn nút gốc:** sai lệch ở nhánh đầu vào có thể lan lên toàn cây. Tìm điểm sai lệch đầu tiên từ các nhánh con.
- **Bỏ qua loops:** một toán tử rẻ mỗi lần có thể rất đắt khi bị lặp nhiều lần.
- **Cộng thời gian mọi nút:** thời gian nút cha có thể bao gồm thời gian nút con. Đọc theo quy ước của hệ quản trị.
- **Coi số hàng bằng kích thước dữ liệu:** cần xem thêm độ rộng dòng, overhead và dữ liệu tạm.
- **Cho rằng mọi quét toàn bảng đều xấu:** quét tuần tự có thể hiệu quả khi cần phần lớn bảng hoặc bảng nhỏ. Cần so sánh lượng dữ liệu đọc và chi phí thực tế.
- **Thêm chỉ mục khi thấy truy vấn chậm:** trước tiên xác định sai lệch cardinality, lượng dữ liệu trung gian, số lần lặp và nút thắt tài nguyên.
- **Chạy đo thực tế mà không đánh giá tác động:** chế độ phân tích có thể thực thi truy vấn và tiêu tốn tài nguyên hoặc thay đổi dữ liệu.
- **So sánh hai lần chạy khác điều kiện:** cache, tải đồng thời, tham số, dữ liệu và cấu hình khác nhau có thể làm số liệu không tương đương.

## 11. Bài tập tự kiểm tra

**Bài 1.** Một toán tử được ước lượng tạo 2.000 dòng nhưng thực tế tạo 80.000 dòng. Sai lệch là bao nhiêu lần và bạn sẽ kiểm tra điều gì đầu tiên?

*Gợi ý:* Sai lệch là 40 lần. Kiểm tra điều kiện lọc và thống kê tại toán tử đó; sau đó xem sai lệch có xuất hiện từ một nút đầu vào trước nó hay không.

**Bài 2.** Một phép tra cứu bên trong nested loop tạo trung bình 2 dòng mỗi vòng và chạy 5.000 vòng. Xấp xỉ bao nhiêu dòng đi qua toán tử trong toàn bộ lần thực thi?

*Gợi ý:* Nếu định dạng báo số dòng trung bình mỗi vòng, tổng xấp xỉ là \(2 \times 5.000 = 10.000\) dòng. Hãy xác nhận quy ước actual rows của công cụ trước khi tính.

**Bài 3.** Một hash join có số hàng ước lượng gần với thực tế nhưng kế hoạch ghi nhận nhiều dữ liệu tạm. Những yếu tố nào cần xem xét?

*Gợi ý:* Kiểm tra độ rộng dòng, số hàng của nhánh build, số nhóm/khóa băm, bộ nhớ cấp cho toán tử, số batch hoặc spill, temp I/O và mức đồng thời của các truy vấn khác.

**Bài 4.** Cost giảm sau khi thêm chỉ mục nhưng thời gian thực tế tăng. Hãy nêu các khả năng cần kiểm tra.

*Gợi ý:* Kiểm tra kế hoạch thực tế có thay đổi cách truy cập hoặc số vòng lặp không; cache, tải đồng thời và I/O có khác không; thống kê có phản ánh dữ liệu hiện tại không; cost có được so sánh trong cùng điều kiện và cùng mô hình hay không.

## 12. Ghi nhớ khi tối ưu

Đọc execution plan hiệu quả đòi hỏi kết hợp bốn góc nhìn. Số hàng cho biết quy mô công việc mà mỗi toán tử xử lý; cost cho biết cách bộ tối ưu đánh giá phương án; thời gian thực tế cho biết lần chạy đã tiêu tốn bao lâu; còn lượng dữ liệu trung gian giúp giải thích áp lực lên bộ nhớ và I/O.

Khi các con số không khớp, hãy lần theo cây kế hoạch để tìm sai lệch cardinality đầu tiên, kiểm tra loops và độ rộng dòng, rồi đối chiếu với thống kê, chỉ mục, điều kiện truy vấn và tài nguyên. Sau mỗi điều chỉnh, đo lại trong điều kiện tương đương và xác nhận kết quả truy vấn. Cách làm dựa trên số liệu này giúp xác định đúng nút thắt và đánh giá được hiệu quả thực tế của thay đổi.
