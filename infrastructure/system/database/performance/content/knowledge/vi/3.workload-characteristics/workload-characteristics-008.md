# Ưu tiên tối ưu theo tổng chi phí, tần suất và tác động nghiệp vụ

Trong một hệ thống cơ sở dữ liệu đang vận hành, có thể tồn tại hàng trăm hoặc hàng nghìn mẫu truy vấn. Nhóm phát triển thường không có đủ thời gian để tối ưu tất cả cùng lúc. Chọn truy vấn chậm nhất theo một lần đo, hoặc chọn truy vấn xuất hiện nhiều nhất, đều có thể dẫn đến quyết định sai. Một truy vấn mất 2 giây nhưng chỉ chạy một lần mỗi tháng có thể ít ảnh hưởng đến tải tổng thể hơn một truy vấn mất 5 mili giây nhưng được gọi hàng chục nghìn lần mỗi phút. Ngược lại, truy vấn hiếm nhưng nằm trên đường xử lý thanh toán hoặc chốt sổ có thể có tác động nghiệp vụ rất lớn.

Vì vậy, tối ưu hiệu năng cơ sở dữ liệu cần bắt đầu bằng việc hiểu **khối lượng công việc** (*workload*): hệ thống đang thực hiện những loại thao tác nào, mỗi loại xuất hiện bao nhiêu lần, tiêu thụ tài nguyên ra sao và ảnh hưởng đến nghiệp vụ nào. Thứ tự ưu tiên nên kết hợp ba góc nhìn: **tổng chi phí tích lũy**, **tần suất thực thi** và **tác động nghiệp vụ**. Các kế hoạch thực thi, thống kê truy vấn và phép đo tải cung cấp bằng chứng để lựa chọn đúng điểm cần cải thiện.

## 1. Hiểu khối lượng công việc trước khi tối ưu

Khối lượng công việc là tập hợp các thao tác đọc, ghi, cập nhật, xóa, giao dịch và tác vụ nền mà cơ sở dữ liệu phải phục vụ trong một khoảng thời gian. Mỗi thao tác có đặc điểm riêng về tần suất, kích thước dữ liệu, mức đồng thời, thời gian xử lý và tài nguyên sử dụng.

Ví dụ, một hệ thống bán hàng có thể đồng thời phục vụ:

- Tra cứu thông tin sản phẩm và tồn kho từ trang danh sách.
- Đọc giỏ hàng và thông tin khách hàng trong quá trình thanh toán.
- Ghi đơn hàng, trừ tồn kho và lưu lịch sử giao dịch.
- Tạo báo cáo doanh thu theo ngày hoặc theo tháng.
- Đồng bộ dữ liệu với hệ thống kho và chạy tác vụ dọn dữ liệu cũ.

Các thao tác này không có cùng mức độ quan trọng. Tra cứu sản phẩm có thể xuất hiện rất thường xuyên; ghi nhận thanh toán có thể ít hơn nhưng ảnh hưởng trực tiếp đến doanh thu; báo cáo tháng có thể tiêu thụ nhiều I/O trong một khoảng thời gian ngắn nhưng không ảnh hưởng đến từng lượt mua hàng.

### Phân biệt truy vấn, giao dịch và nghiệp vụ

Một mẫu truy vấn SQL là một đơn vị quan sát hữu ích, nhưng không phải lúc nào cũng là đơn vị nghiệp vụ. Một thao tác thanh toán có thể gọi nhiều truy vấn và nằm trong một giao dịch. Một truy vấn lấy thông tin khách hàng có thể được dùng bởi nhiều luồng nghiệp vụ khác nhau.

Khi phân tích, cần giữ được mối liên hệ giữa ba lớp:

| Lớp | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Truy vấn | Đọc tồn kho theo mã sản phẩm | Câu SQL này chạy bao nhiêu lần và tiêu tốn gì? |
| Giao dịch | Tạo đơn hàng và cập nhật tồn kho | Toàn bộ giao dịch mất bao lâu, chờ khóa ở đâu, có rollback không? |
| Nghiệp vụ | Hoàn tất thanh toán | Người dùng có hoàn thành được việc mua hàng đúng thời hạn không? |

Nếu chỉ tối ưu một truy vấn riêng lẻ, ta có thể bỏ qua thời gian chờ kết nối, tranh chấp khóa hoặc các truy vấn khác trong cùng giao dịch. Do đó, số liệu truy vấn cần được liên hệ với thời gian hoàn tất của giao dịch và nghiệp vụ tương ứng.

## 2. Tần suất và chi phí mỗi lần thực thi

Hai yếu tố đầu tiên để đánh giá một mẫu truy vấn là số lần thực thi và chi phí của mỗi lần thực thi.

- **Tần suất** (*frequency*): số lần một mẫu truy vấn được thực thi trong một khoảng thời gian.
- **Chi phí mỗi lần** (*per-execution cost*): lượng tài nguyên hoặc thời gian cần thiết cho một lần thực thi trong điều kiện đo xác định.
- **Tổng chi phí tích lũy** (*total cumulative cost*): tổng lượng công việc mà mẫu truy vấn tạo ra trong khoảng đo.

Một cách ước lượng ban đầu là:

\[
\text{Tổng chi phí truy vấn} = \text{Số lần thực thi} \times \text{Chi phí trung bình mỗi lần}
\]

Nếu dùng tổng thời gian thực thi làm đại diện cho chi phí:

\[
T_{total} = N_{calls} \times T_{avg}
\]

Trong đó \(N_{calls}\) là số lần gọi và \(T_{avg}\) là thời gian thực thi trung bình. Kết quả cho biết tổng thời gian thực thi được cộng dồn qua các lần gọi trong cửa sổ đo. Nó không đồng nghĩa với thời gian đồng hồ thực tế mà người dùng phải chờ, bởi nhiều truy vấn có thể chạy song song.

Ví dụ, một mẫu truy vấn được gọi 20.000 lần trong một phút, mỗi lần mất trung bình 4 ms. Tổng thời gian thực thi cộng dồn là 80.000 ms, tương đương 80 giây thời gian thực thi tích lũy trong một phút đo. Một truy vấn khác chạy 10 lần, mỗi lần mất 300 ms, chỉ tạo ra 3 giây thời gian thực thi tích lũy. Truy vấn thứ nhất có thể là mục tiêu tối ưu tốt hơn đối với tải tổng thể, dù từng lần thực thi rất nhanh.

### Không chỉ dùng thời gian để biểu diễn chi phí

Thời gian thực thi là chỉ số dễ hiểu nhưng không mô tả đầy đủ chi phí cơ sở dữ liệu. Nên quan sát thêm các tài nguyên sau:

| Thành phần | Dấu hiệu cần quan sát | Ý nghĩa khi đánh giá |
|---|---|---|
| CPU | Thời gian CPU, mức sử dụng CPU, số phép tính hoặc thao tác xử lý | Truy vấn có thể đang tiêu tốn nhiều năng lực tính toán |
| I/O | Số khối đọc/ghi, byte đọc/ghi, độ trễ lưu trữ | Truy vấn có thể đọc quá nhiều trang hoặc ghi dữ liệu lớn |
| Bộ nhớ | Bộ nhớ làm việc, cache hit, cấp phát bộ nhớ, dữ liệu tràn ra đĩa | Truy vấn có thể cần sắp xếp hoặc hash lớn |
| Khóa và đồng thời | Thời gian chờ khóa, deadlock, thời gian giữ khóa | Truy vấn hoặc giao dịch có thể làm các yêu cầu khác bị chặn |
| Kết nối | Thời gian chờ lấy kết nối, số kết nối đang dùng | Ứng dụng có thể bị nghẽn trước khi câu SQL bắt đầu |
| Mạng và truyền dữ liệu | Số hàng trả về, kích thước kết quả, thời gian truyền | Truy vấn có thể chuyển quá nhiều dữ liệu lên ứng dụng |

Không nên cộng trực tiếp mili giây CPU, byte I/O, số trang bộ nhớ và thời gian chờ khóa thành một con số khi chưa có quy tắc quy đổi. Đây là các đại lượng khác đơn vị và có thể cùng phản ánh một phần của một thao tác. Hãy giữ chúng thành các chiều riêng để xác định tài nguyên đang giới hạn hệ thống. Nếu cần một điểm tổng hợp để xếp hạng, phải chuẩn hóa từng chiều và công bố cách gán trọng số.

### Tần suất phải được đo trong cửa sổ đại diện

Tần suất thay đổi theo thời gian và theo loại tải. Truy vấn báo cáo có thể chỉ xuất hiện vào đầu ngày; truy vấn tra cứu có thể tăng mạnh vào giờ cao điểm; tác vụ đồng bộ có thể chạy theo lịch. Một lần lấy số liệu ngắn ở giờ thấp điểm không đủ để đại diện cho cả ngày.

Nên thu thập số liệu ở nhiều cửa sổ phù hợp với hệ thống, chẳng hạn giờ bình thường, giờ cao điểm, thời điểm chạy tác vụ nền và chu kỳ chốt dữ liệu. Ghi lại thời lượng cửa sổ, múi giờ, số lượng yêu cầu đến và trạng thái tải để có thể so sánh các lần đo.

## 3. Tác động nghiệp vụ quyết định mức độ ưu tiên

Chi phí tài nguyên cao không tự động có nghĩa truy vấn đó cần được tối ưu trước. Một truy vấn có thể tiêu thụ nhiều I/O nhưng chỉ phục vụ báo cáo nội bộ chạy ngoài giờ. Một truy vấn khác có chi phí nhỏ nhưng nằm trên đường xử lý đăng nhập, đặt hàng hoặc thanh toán. Nếu truy vấn thứ hai chậm, hàng nghìn người dùng có thể bị ảnh hưởng.

Khi đánh giá tác động nghiệp vụ, cần xem xét:

1. **Mức độ quan trọng của luồng:** truy vấn phục vụ chức năng cốt lõi như đăng nhập, thanh toán, đặt hàng hay chỉ phục vụ báo cáo phụ trợ.
2. **Số người dùng hoặc giao dịch bị ảnh hưởng:** một thao tác được dùng rộng rãi có thể gây tác động lớn dù chi phí mỗi lần thấp.
3. **Ảnh hưởng đến doanh thu và vận hành:** chậm thanh toán, sai tồn kho hoặc chậm chốt sổ có thể gây thiệt hại trực tiếp.
4. **Cam kết thời gian:** thao tác có nằm trong SLA/SLO hoặc ngưỡng thời gian sản phẩm đã công bố không.
5. **Tính đúng đắn và nhất quán dữ liệu:** một thay đổi có thể ảnh hưởng đến kết quả nghiệp vụ, thứ tự cập nhật hoặc tính toàn vẹn giao dịch.
6. **Thời điểm xảy ra:** một tác vụ hiếm nhưng bắt buộc hoàn tất trước thời hạn đóng sổ có thể có mức độ khẩn cấp cao.

Hãy trao đổi với người phụ trách sản phẩm hoặc vận hành để xác nhận ý nghĩa của từng luồng. Không nên suy ra mức độ quan trọng chỉ từ tên bảng, tên câu SQL hoặc mức tiêu thụ tài nguyên.

## 4. Kết hợp ba yếu tố để xếp thứ tự tối ưu

Một cách thực tế là xem xét đồng thời ba câu hỏi:

- Truy vấn được gọi thường xuyên đến mức nào?
- Mỗi lần gọi tốn bao nhiêu tài nguyên và tổng chi phí tích lũy là bao nhiêu?
- Nếu truy vấn chậm hoặc thất bại, nghiệp vụ nào và bao nhiêu người dùng bị ảnh hưởng?

Bảng sau minh họa cách so sánh ba mẫu truy vấn trong cùng một phút đo:

| Mẫu truy vấn | Số lần gọi/phút | Thời gian trung bình/lần | Thời gian tích lũy | Tác động nghiệp vụ |
|---|---:|---:|---:|---|
| A. Đọc tồn kho | 60.000 | 4 ms | 240 giây | Cao: nằm trong luồng xem và đặt hàng |
| B. Báo cáo doanh thu | 40 | 500 ms | 20 giây | Trung bình: phục vụ quản lý, không chặn thanh toán |
| C. Chốt giao dịch | 1 | 10.000 ms | 10 giây | Rất cao: cần hoàn tất trước hạn chốt sổ |

Mẫu A tạo tổng thời gian thực thi cộng dồn lớn nhất, vì vậy có thể là mục tiêu đầu tiên để giảm tải thường xuyên. Mẫu C có tần suất thấp nhưng tác động nghiệp vụ rất cao; nó cần được đánh giá riêng theo thời hạn hoàn tất và rủi ro vận hành. Mẫu B có tổng chi phí thấp hơn trong cửa sổ này, nên có thể xếp sau nếu chưa có yêu cầu cụ thể về thời gian báo cáo.

Ví dụ cho thấy không thể chỉ sắp xếp theo thời gian trung bình, số lần gọi hoặc tổng thời gian tích lũy. Cần kết hợp cả ba yếu tố và mục tiêu dịch vụ của từng luồng.

### Dùng điểm ưu tiên như công cụ hỗ trợ

Đội ngũ có thể xây dựng điểm ưu tiên để sắp xếp danh sách ứng viên. Chẳng hạn, trước hết chuẩn hóa tổng chi phí tích lũy về thang điểm 0–100; sau đó đánh giá tác động nghiệp vụ trên thang 1–5 và áp lực độ trễ/SLO trên thang 1–3:

\[
P = C_{normalized} \times B \times S
\]

Trong đó:

- \(C_{normalized}\) là điểm tổng chi phí đã chuẩn hóa từ số liệu đo.
- \(B\) là mức tác động nghiệp vụ do nhóm sản phẩm và vận hành thống nhất.
- \(S\) là hệ số áp lực dịch vụ, cao hơn khi truy vấn thường xuyên vượt ngưỡng độ trễ hoặc đe dọa SLO.

Điểm này chỉ là công cụ sàng lọc. Nó không thay thế phân tích nguyên nhân, và không nên được dùng để tự động quyết định thay đổi. Một truy vấn hiếm nhưng có thời hạn nghiệp vụ bắt buộc có thể cần được đưa vào danh sách ưu tiên khẩn cấp dù điểm tổng hợp thấp. Cần lưu cả các thành phần gốc bên cạnh điểm cuối để người xem hiểu vì sao một mục được xếp hạng cao.

Nếu các tài nguyên khác nhau là nguyên nhân chính, hãy lập thêm bảng xếp hạng riêng cho CPU, I/O, bộ nhớ và thời gian chờ khóa. Một chỉ số tổng hợp duy nhất có thể che mất nút thắt cụ thể hoặc khiến một truy vấn có nhiều loại chi phí bị tính trùng.

## 5. Thu thập và đọc thống kê khối lượng công việc

Để lựa chọn ứng viên chính xác, cần thống kê theo mẫu truy vấn thay vì chỉ xem log từng câu SQL riêng lẻ. Nhiều câu lệnh có giá trị tham số khác nhau nhưng cùng một cấu trúc có thể được gom thành một mẫu hoặc *query fingerprint*. Ví dụ, các câu lệnh sau có cùng hình dạng truy vấn:

```sql
SELECT product_id, quantity
FROM inventory
WHERE warehouse_id = 12 AND product_id = 501;

SELECT product_id, quantity
FROM inventory
WHERE warehouse_id = 12 AND product_id = 907;
```

Khi chuẩn hóa, giá trị cụ thể có thể được thay bằng tham số:

```sql
SELECT product_id, quantity
FROM inventory
WHERE warehouse_id = ? AND product_id = ?;
```

Gom nhóm giúp nhận diện mẫu truy vấn có tần suất cao. Tuy nhiên, cần kiểm tra phân bố tham số: một số giá trị có thể rất phổ biến, trong khi một số giá trị hiếm có lượng dữ liệu lớn hoặc kế hoạch thực thi khác. Nếu gộp tất cả quá mức, thống kê trung bình có thể che khuất một nhóm tham số chậm.

### Các trường thống kê nên có

Với mỗi mẫu truy vấn, nên thu thập ít nhất:

| Nhóm dữ liệu | Trường thống kê | Mục đích |
|---|---|---|
| Tần suất | số lần thực thi, số lần mỗi giây/phút | Xác định truy vấn thường xuyên |
| Thời gian | tổng thời gian, trung bình, p95/p99 hoặc phân bố thời gian | Đánh giá chi phí tích lũy và các lần chạy chậm |
| Dữ liệu | số hàng trả về, số hàng đọc/ghi, số vòng lặp | Nhận diện đọc thừa hoặc xử lý quá nhiều dữ liệu |
| I/O | khối đọc từ lưu trữ, khối lấy từ cache, khối ghi | Xác định áp lực đọc/ghi |
| Bộ nhớ | bộ nhớ cấp phát, thao tác sort/hash, dữ liệu tràn ra đĩa | Tìm truy vấn tiêu thụ nhiều bộ nhớ |
| Đồng thời | thời gian chờ khóa, deadlock, thời gian giao dịch mở | Xác định tranh chấp giữa các phiên |
| Kế hoạch | loại scan, join, sort, ước lượng và số hàng thực tế | Tìm nguyên nhân trong cách thực thi |

Nên phân biệt số liệu trung bình với phân vị. Trung bình 5 ms có thể che giấu một tỷ lệ nhỏ truy vấn mất vài giây. Với luồng nghiệp vụ nhạy cảm về thời gian, p95/p99 và số lần vượt ngưỡng thường có ý nghĩa hơn một giá trị trung bình duy nhất.

### Đọc kế hoạch thực thi cùng số liệu thực tế

Kế hoạch thực thi cho biết hệ quản trị dự kiến hoặc đã thực hiện các bước như quét bảng, quét chỉ mục, nối bảng, sắp xếp và tổng hợp. Dùng kế hoạch để giải thích chi phí quan sát được:

- Quét toàn bảng trên tập dữ liệu lớn có thể làm tăng số trang đọc.
- Chỉ mục không phù hợp có thể khiến truy vấn phải đọc nhiều hàng rồi mới lọc.
- Thứ tự join hoặc thuật toán join không phù hợp có thể làm tăng CPU và bộ nhớ.
- Sort hoặc hash lớn có thể cần thêm bộ nhớ và tràn dữ liệu tạm ra đĩa.
- Ước lượng số hàng sai lệch lớn so với số hàng thực tế có thể dẫn đến lựa chọn kế hoạch không phù hợp.

Chi phí do bộ tối ưu hóa hiển thị trong kế hoạch thường là ước lượng nội bộ theo mô hình của hệ quản trị. Không nên coi con số đó là mili giây thực tế hoặc so sánh trực tiếp giữa các hệ quản trị, phiên bản hay cấu hình khác nhau. Hãy đối chiếu ước lượng với số hàng thực tế, thời gian thực thi và thống kê I/O.

Kế hoạch có đo thời gian thực tế hữu ích để xác nhận giả thuyết, nhưng một số công cụ sẽ thực sự chạy câu truy vấn khi thu thập số liệu. Với câu lệnh ghi hoặc truy vấn tốn tài nguyên, cần chọn môi trường và phương pháp kiểm tra phù hợp để tránh gây thay đổi dữ liệu hoặc tải ngoài dự kiến.

## 6. Quy trình chọn ứng viên tối ưu

Một quy trình có thể áp dụng cho hệ thống đang vận hành gồm các bước sau.

### Bước 1: Xác định mục tiêu và ranh giới tải

Chọn luồng nghiệp vụ cần cải thiện, chẳng hạn thanh toán p95 dưới một ngưỡng xác định hoặc giảm mức sử dụng I/O trong giờ cao điểm. Xác định cửa sổ đo, loại người dùng, tỷ lệ đọc/ghi và tác vụ nền có mặt trong thời gian đó.

### Bước 2: Thu thập số liệu đại diện

Ghi số lần thực thi, tổng thời gian, thời gian phân vị, số hàng, I/O, CPU, bộ nhớ và thời gian chờ. Thu thập trong các cửa sổ có ý nghĩa, bao gồm thời điểm cao điểm hoặc thời điểm tác vụ định kỳ chạy.

### Bước 3: Gom nhóm theo mẫu truy vấn

Chuẩn hóa truy vấn theo cấu trúc để nhận diện mẫu lặp lại. Giữ thông tin phân biệt khi tham số hoặc phân bố dữ liệu làm thay đổi đáng kể kế hoạch thực thi. Gắn mẫu truy vấn với giao dịch hoặc luồng nghiệp vụ nếu có thể.

### Bước 4: Xếp hạng theo tổng chi phí và tần suất

Tính số lần thực thi và tổng chi phí tích lũy trong cùng cửa sổ. Kiểm tra riêng CPU, I/O, bộ nhớ và chờ khóa để xác định loại tài nguyên bị tiêu thụ. Dùng Pareto như một gợi ý: một nhóm nhỏ mẫu truy vấn thường có thể tạo ra phần lớn chi phí, nhưng phải kiểm chứng trên số liệu thực tế.

### Bước 5: Bổ sung tác động nghiệp vụ

Xác định luồng nào bị ảnh hưởng, số người dùng, mức độ quan trọng, thời hạn và SLO. Đưa các truy vấn hiếm nhưng có tác động cao vào danh sách theo dõi riêng, tránh để chúng biến mất khi xếp hạng chỉ theo tổng chi phí.

### Bước 6: Kiểm tra nguyên nhân trước khi chọn giải pháp

Đọc kế hoạch thực thi, thống kê hàng, chỉ mục hiện có, điều kiện lọc, join, sort, mức đồng thời và thời gian chờ. Một truy vấn tốn thời gian có thể do đọc dữ liệu lớn, nhưng cũng có thể do bị chặn bởi giao dịch khác hoặc chờ kết nối. Giải pháp phải nhắm đúng nguyên nhân.

### Bước 7: Ước lượng lợi ích và chi phí thay đổi

Ước lượng lượng chi phí có thể giảm, số luồng nghiệp vụ được cải thiện và rủi ro phát sinh. Ví dụ, thêm chỉ mục có thể tăng tốc đọc nhưng làm tăng chi phí ghi và dung lượng lưu trữ. Viết lại SQL có thể giảm số hàng đọc nhưng thay đổi kết quả nếu điều kiện lọc không tương đương. Cần tính cả tác động phụ trước khi triển khai.

### Bước 8: Kiểm chứng sau điều chỉnh

Chạy lại cùng kịch bản, dữ liệu, mức đồng thời và cửa sổ đo. So sánh tổng chi phí, tần suất, độ trễ p95/p99, tỷ lệ lỗi, tài nguyên và kết quả nghiệp vụ. Một tối ưu chỉ được xác nhận khi cải thiện đo được và không vi phạm tính đúng đắn hoặc mục tiêu dịch vụ.

## 7. Chọn giải pháp theo loại chi phí và tác động

Sau khi xếp hạng, hãy chọn giải pháp theo nguyên nhân được xác nhận.

| Dấu hiệu | Hướng kiểm tra | Ví dụ giải pháp cần đánh giá |
|---|---|---|
| Nhiều lần đọc và quét nhiều hàng | Điều kiện lọc, tính chọn lọc, kế hoạch scan, số hàng ước lượng | Thiết kế chỉ mục phù hợp, giảm số cột/hàng cần đọc, viết lại điều kiện truy vấn |
| CPU cao do join hoặc tổng hợp | Số hàng trung gian, thứ tự join, biểu thức tính toán | Điều chỉnh SQL, giảm dữ liệu trung gian, tổng hợp theo nhu cầu |
| I/O đọc cao | Số trang đọc, cache hit, kích thước dữ liệu và chỉ mục | Giảm đọc thừa, chọn chỉ mục, phân vùng hoặc tổ chức dữ liệu khi phù hợp |
| I/O ghi cao | Tần suất cập nhật, chỉ mục phải duy trì, ghi ngẫu nhiên | Giảm ghi không cần thiết, xem lại số lượng chỉ mục và cách ghi theo lô |
| Chờ khóa cao | Giao dịch dài, thứ tự cập nhật, vùng dữ liệu nóng | Rút ngắn giao dịch, thống nhất thứ tự khóa, giảm phạm vi cập nhật |
| Bộ nhớ cao hoặc tràn sort/hash | Kích thước tập trung gian, sort, hash, số phiên đồng thời | Giảm dữ liệu trung gian, tối ưu join/sort, điều chỉnh mức đồng thời phù hợp |
| Thời gian chờ kết nối cao | Kích thước pool, thời gian giữ kết nối, thời gian truy vấn | Rút ngắn thời gian giữ kết nối, xử lý truy vấn lâu, điều chỉnh pool dựa trên năng lực DB |

Không nên thêm chỉ mục cho mọi truy vấn xuất hiện trong danh sách. Chỉ mục làm tăng dung lượng lưu trữ và có thể làm chậm INSERT, UPDATE, DELETE vì hệ quản trị phải duy trì cấu trúc chỉ mục. Chọn chỉ mục dựa trên mẫu truy vấn quan trọng, tính chọn lọc, thứ tự cột, tải ghi và kế hoạch thực thi thực tế.

Tương tự, tăng số kết nối hoặc mức đồng thời không đảm bảo tăng thông lượng. Khi cơ sở dữ liệu đã bão hòa CPU, I/O hoặc khóa, thêm phiên có thể làm hàng đợi dài hơn và giảm thông lượng thành công. Hãy xử lý nút thắt trước khi tăng tải đồng thời.

## 8. Ví dụ lập danh sách ưu tiên cho hệ thống bán hàng

Giả sử số liệu trong giờ cao điểm cho thấy ba mẫu truy vấn:

| Mẫu | Tần suất | Chi phí quan sát | Luồng nghiệp vụ | Nhận định ban đầu |
|---|---:|---|---|---|
| Tra cứu tồn kho theo kho và sản phẩm | 60.000 lần/phút | Tổng thời gian cao, đọc lặp lại cùng nhóm dữ liệu | Xem sản phẩm và đặt hàng | Ưu tiên điều tra đầu tiên để giảm tải thường xuyên |
| Báo cáo doanh thu theo ngày | 40 lần/phút | Mỗi lần lâu, đọc nhiều hàng | Báo cáo quản trị | Kiểm tra lịch chạy, I/O và yêu cầu thời gian báo cáo |
| Chốt giao dịch cuối ngày | 1 lần/phút trong thời điểm chốt | Một lần chạy dài và có thời hạn hoàn tất | Đóng sổ và đối soát | Ưu tiên cao theo thời hạn nghiệp vụ, dù tần suất thấp |

Với truy vấn tồn kho, kiểm tra kế hoạch có quét quá nhiều hàng hay không, chỉ mục có phù hợp với cặp điều kiện kho và sản phẩm không, và ứng dụng có gửi cùng một truy vấn lặp lại trong một yêu cầu hay không. Nếu dữ liệu ít thay đổi trong một khoảng ngắn, có thể đánh giá cache ở lớp phù hợp, nhưng phải xác định rõ yêu cầu nhất quán tồn kho.

Với báo cáo doanh thu, xem xét số hàng đọc, cách tổng hợp, thời điểm chạy và mức độ cạnh tranh I/O với giao dịch trực tuyến. Có thể đánh giá bảng tổng hợp hoặc dữ liệu đã tính trước nếu yêu cầu cập nhật cho phép, nhưng phải xác định cách đồng bộ và độ trễ dữ liệu chấp nhận được.

Với chốt giao dịch, phân tích thời gian của toàn quy trình, các giao dịch mở, thời gian chờ khóa và khả năng xử lý theo lô. Vì đây là luồng có thời hạn, tiêu chí thành công có thể là hoàn tất toàn bộ đối soát trước một mốc cụ thể và bảo toàn tính nhất quán, không đơn thuần là giảm tổng CPU.

Sau khi xác định giải pháp, lập baseline riêng cho từng luồng. Một thay đổi cải thiện truy vấn tồn kho nhưng làm tăng thời gian ghi tồn kho có thể ảnh hưởng ngược đến thanh toán. Phải chạy kịch bản hỗn hợp đọc/ghi để quan sát tác động toàn hệ thống.

## 9. Đo lại và chứng minh hiệu quả

Mọi quyết định tối ưu cần có số liệu trước và sau. Trước thay đổi, lưu lại:

- Phiên bản ứng dụng và cấu hình cơ sở dữ liệu.
- Tập dữ liệu, kích thước bảng, phân bố dữ liệu và trạng thái thống kê.
- Kịch bản tải, tỷ lệ đọc/ghi, tốc độ đến và mức đồng thời.
- Số lần thực thi, tổng thời gian, thời gian trung bình và phân vị.
- CPU, I/O, bộ nhớ, cache, khóa, rollback, timeout và retry.
- Kết quả nghiệp vụ và các ngưỡng SLO cần giữ.

Sau thay đổi, lặp lại phép đo trong điều kiện tương đương. Kiểm tra cả truy vấn mục tiêu lẫn các luồng liên quan, đặc biệt khi thay đổi chỉ mục, thứ tự cập nhật hoặc cấu hình kết nối. Nếu có khác biệt về dữ liệu hoặc trạng thái cache, ghi rõ để tránh kết luận sai.

Ví dụ, sau khi thêm chỉ mục cho truy vấn tồn kho, thời gian trung bình có thể giảm từ 4 ms xuống 1,5 ms. Nếu tần suất vẫn là 60.000 lần/phút, tổng thời gian thực thi cộng dồn giảm từ 240 giây xuống 90 giây mỗi phút đo. Tuy nhiên, cần kiểm tra thêm chi phí ghi tăng thêm do duy trì chỉ mục, dung lượng lưu trữ, p95/p99 và hiệu năng của luồng cập nhật tồn kho. Chỉ số đọc cải thiện là bằng chứng quan trọng nhưng chưa đủ để xác nhận toàn bộ workload tốt hơn.

Nếu tổng thời gian truy vấn giảm nhưng thời gian nghiệp vụ không giảm, có thể nút thắt nằm ở kết nối, khóa, xử lý ứng dụng hoặc một truy vấn khác trong cùng giao dịch. Nếu thông lượng tăng nhưng tỷ lệ lỗi hoặc p99 xấu đi, thay đổi chưa đáp ứng mục tiêu. Hãy truy vết toàn luồng để tìm phần chi phí còn lại.

## 10. Những sai lầm khi chọn thứ tự tối ưu

1. **Chỉ tối ưu truy vấn có thời gian trung bình cao nhất:** truy vấn hiếm có thể không tạo ra tải tổng thể lớn.
2. **Chỉ chọn truy vấn chạy nhiều nhất:** tần suất cao nhưng chi phí rất nhỏ có thể không phải nút thắt.
3. **Bỏ qua tác động nghiệp vụ:** truy vấn hiếm nhưng nằm trên luồng thanh toán hoặc chốt sổ vẫn có thể rất quan trọng.
4. **Dùng một cửa sổ đo không đại diện:** bỏ qua giờ cao điểm hoặc tác vụ nền sẽ làm sai thứ tự ưu tiên.
5. **Coi cost trong execution plan là thời gian thực:** đây thường là đơn vị ước lượng nội bộ của bộ tối ưu hóa.
6. **Gộp mọi truy vấn có cùng cấu trúc mà bỏ qua phân bố tham số:** một nhóm tham số có thể có kế hoạch và chi phí khác biệt.
7. **Cộng các tài nguyên khác đơn vị mà không chuẩn hóa:** điểm tổng hợp có thể tạo cảm giác chính xác nhưng không có ý nghĩa đo lường.
8. **Thêm chỉ mục mà không tính chi phí ghi:** đọc nhanh hơn có thể làm cập nhật chậm hơn và tăng dung lượng.
9. **Không kiểm tra toàn giao dịch:** truy vấn riêng lẻ nhanh hơn chưa chắc nghiệp vụ hoàn tất nhanh hơn.
10. **Không đo lại sau thay đổi:** giả thuyết hợp lý không thay thế được bằng chứng thực nghiệm.

## 11. Danh sách kiểm tra trước khi chọn mục tiêu tối ưu

- [ ] Đã xác định workload, luồng nghiệp vụ và cửa sổ thời gian đại diện.
- [ ] Đã gom nhóm truy vấn theo mẫu và kiểm tra ảnh hưởng của phân bố tham số.
- [ ] Đã đo số lần thực thi, chi phí mỗi lần và tổng chi phí tích lũy.
- [ ] Đã theo dõi riêng CPU, I/O, bộ nhớ, khóa, kết nối và lượng dữ liệu trả về.
- [ ] Đã xem thời gian trung bình cùng p95/p99 và số lần vượt ngưỡng.
- [ ] Đã liên hệ truy vấn với giao dịch và tác động đến người dùng hoặc nghiệp vụ.
- [ ] Đã đọc kế hoạch thực thi và đối chiếu ước lượng với số liệu thực tế.
- [ ] Đã đánh giá chi phí phụ của giải pháp, đặc biệt với chỉ mục và tải ghi.
- [ ] Đã xác định baseline và điều kiện kiểm thử trước khi điều chỉnh.
- [ ] Đã kiểm tra lại hiệu năng, tính đúng đắn và SLO sau thay đổi.

Ưu tiên tối ưu hiệu năng cơ sở dữ liệu là bài toán phân bổ công sức vào đúng điểm có giá trị cao nhất. Tần suất cho biết truy vấn xuất hiện bao nhiêu lần; chi phí mỗi lần và tổng chi phí tích lũy cho biết nó tiêu thụ bao nhiêu tài nguyên; tác động nghiệp vụ cho biết hậu quả khi truy vấn chậm hoặc thất bại. Kết hợp ba góc nhìn với thống kê tải, kế hoạch thực thi và phép đo trước/sau giúp nhóm phát triển chọn được thay đổi có cơ sở, giảm nút thắt thực sự và bảo vệ các luồng nghiệp vụ quan trọng.
