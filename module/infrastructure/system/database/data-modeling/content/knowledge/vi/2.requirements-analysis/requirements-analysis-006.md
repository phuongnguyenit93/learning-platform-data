# Ước lượng khối lượng, tốc độ tăng trưởng, độ trễ và thời gian lưu

## 1. Vì sao cần ước lượng quy mô và vòng đời dữ liệu?

Một mô hình dữ liệu phải đáp ứng cả nhu cầu hiện tại lẫn lượng dữ liệu hệ thống sẽ tạo ra trong tương lai. Số lượng bản ghi, kích thước mỗi bản ghi, tốc độ phát sinh, thời gian lưu giữ và cách người dùng truy cập đều ảnh hưởng đến cấu trúc dữ liệu, khóa, chỉ mục, phân vùng, lưu trữ và chi phí vận hành.

Nếu chỉ thiết kế theo số bản ghi hiện có, một bảng giao dịch có thể tăng lên hàng trăm triệu dòng sau vài năm. Nếu chỉ ước lượng dung lượng mà không xem xét độ trễ, truy vấn có thể vẫn chậm dù hệ thống còn nhiều dung lượng trống. Nếu lưu mọi dữ liệu vô thời hạn, chi phí lưu trữ và sao lưu tiếp tục tăng, trong khi phần lớn truy vấn nghiệp vụ chỉ cần dữ liệu gần đây.

Bước khảo sát này cần trả lời bốn nhóm câu hỏi:

- **Khối lượng:** hiện có bao nhiêu dữ liệu và một bản ghi chiếm khoảng bao nhiêu dung lượng?
- **Tăng trưởng:** dữ liệu mới phát sinh và dữ liệu cũ thay đổi với tốc độ nào?
- **Độ trễ:** mỗi thao tác cần hoàn tất trong bao lâu, ở tải bình thường và tải cao điểm?
- **Thời gian lưu:** dữ liệu cần được giữ trực tuyến, lưu trữ dài hạn hoặc xóa sau bao lâu?

Các con số cần gắn với giả định, nguồn đo và mốc thời gian. Mục tiêu của ước lượng không phải dự đoán chính xác tuyệt đối, mà là tạo cơ sở có thể kiểm chứng để lựa chọn mô hình và lập kế hoạch dung lượng.

## 2. Ước lượng khối lượng dữ liệu

### 2.1. Đếm dữ liệu theo thực thể và quan hệ

Bắt đầu bằng cách liệt kê các nhóm dữ liệu mà hệ thống lưu trữ, sau đó ước lượng số lượng bản ghi cho từng nhóm. Không nên chỉ đếm thực thể chính; các quan hệ một-nhiều, bảng liên kết, lịch sử và sự kiện thường tạo ra lượng dữ liệu đáng kể.

Ví dụ, trong hệ thống bán hàng có thể cần ước lượng:

| Nhóm dữ liệu | Đơn vị đếm | Yếu tố làm tăng số lượng |
|---|---|---|
| Khách hàng | Khách hàng | Đăng ký mới, nhập dữ liệu, tài khoản trùng |
| Sản phẩm | Sản phẩm và biến thể | Danh mục mới, kích cỡ, màu sắc |
| Đơn hàng | Đơn hàng | Số khách mua, số đơn mỗi khách |
| Dòng hàng | Dòng hàng trong đơn | Số sản phẩm trung bình trong mỗi đơn |
| Thanh toán | Giao dịch thanh toán | Thanh toán nhiều lần, hoàn tiền, thử lại |
| Lịch sử trạng thái | Lần chuyển trạng thái | Số bước xử lý và số lần cập nhật |
| Sự kiện kiểm toán | Sự kiện thay đổi | Số thao tác cần ghi vết |

Nếu một đơn hàng có trung bình 3,2 dòng hàng thì 100.000 đơn tạo ra khoảng 320.000 dòng hàng. Số lượng bản ghi ở bảng con có thể lớn hơn bảng cha nhiều lần. Khi mô hình hóa, cần ước lượng cả số lượng thực thể và lực lượng quan hệ (cardinality) giữa chúng.

Với dữ liệu đồ thị, cần đếm cả đỉnh và cạnh. Với document, cần xem một document trung bình chứa bao nhiêu phần tử lồng nhau và kích thước của các mảng có thể tăng đến đâu. Với mô hình phân tích, cần ước lượng số dòng fact theo từng sự kiện và số bản ghi dimension. Đơn vị đếm phải phù hợp với cấu trúc dữ liệu thực tế.

### 2.2. Ước lượng kích thước bản ghi

Kích thước bản ghi phụ thuộc vào kiểu dữ liệu, độ dài giá trị thực tế, trường tùy chọn, cấu trúc lồng nhau và cách hệ quản trị lưu trữ. Có thể lập ước lượng ban đầu bằng cách cộng kích thước dự kiến của các thuộc tính.

Ví dụ một bản ghi đơn hàng có thể gồm:

| Thuộc tính | Kiểu dữ liệu minh họa | Giả định kích thước dữ liệu |
|---|---|---:|
| ID | BIGINT | 8 byte |
| Customer ID | BIGINT | 8 byte |
| Trạng thái | Mã số nhỏ | 2 byte |
| Thời điểm tạo | Timestamp | 8 byte |
| Tổng tiền | Decimal | 8 byte |
| Ghi chú | Văn bản ngắn | Trung bình 120 byte |
| Mã tham chiếu | Chuỗi | Trung bình 32 byte |

Tổng các giá trị ví dụ là 186 byte dữ liệu trường. Đây chưa phải kích thước vật lý chính xác của một hàng. Cơ sở dữ liệu còn có thể lưu metadata hàng, bitmap NULL, căn chỉnh bộ nhớ, header trang, thông tin MVCC, padding, cấu trúc quản lý và các chi tiết phụ thuộc engine.

Với document JSON, kích thước phụ thuộc cả tên trường, dấu phân cách, cách biểu diễn số, chuỗi và phần lồng nhau. Với dữ liệu nhị phân như ảnh hoặc tệp, cần ước lượng riêng theo kích thước nội dung và metadata.

Cách đáng tin cậy hơn là tạo dữ liệu mẫu đại diện, nạp vào môi trường thử nghiệm và đo kích thước bằng công cụ của hệ quản trị hoặc hệ thống lưu trữ. Khi chưa thể đo, hãy ghi rõ đây là ước lượng logic và bổ sung biên sai số.

### 2.3. Phân biệt dung lượng logic và dung lượng vật lý

Có ít nhất ba lớp dung lượng cần phân biệt:

1. **Dung lượng payload logic:** tổng kích thước dữ liệu nghiệp vụ theo cách biểu diễn đã chọn, chưa tính đầy đủ overhead của hệ thống lưu trữ.
2. **Dung lượng cơ sở dữ liệu:** phần dữ liệu cộng với cấu trúc hàng/trang, chỉ mục, metadata, phiên bản hàng và không gian trống do engine quản lý.
3. **Dung lượng triển khai:** dung lượng cơ sở dữ liệu cộng các bản sao, bản sao lưu, log, vùng tạm, bản xuất dữ liệu và phần dự phòng vận hành.

Có thể dùng công thức khái quát để lập kế hoạch ban đầu:

```text
Dung lượng logic
  = Tổng số bản ghi của từng nhóm × Kích thước trung bình mỗi bản ghi

Dung lượng cơ sở dữ liệu
  ≈ Dung lượng logic + Chỉ mục + Overhead lưu trữ

Dung lượng triển khai
  ≈ Dung lượng cơ sở dữ liệu
    + Bản sao + Backup + Log + Vùng tạm + Dự phòng
```

Không nên áp dụng một hệ số overhead chung cho mọi hệ thống mà không kiểm chứng. Chỉ mục có thể chiếm tỷ trọng lớn nếu có nhiều khóa hoặc giá trị dài; dữ liệu nén có thể giảm dung lượng; cập nhật thường xuyên có thể tạo thêm phiên bản hàng và làm tăng bloat; bản sao và backup còn phụ thuộc cấu hình triển khai.

Khi lập dự toán, hãy tách từng thành phần và đo lại sau khi có schema, chỉ mục và dữ liệu mẫu.

### 2.4. Ví dụ tính dung lượng logic

Giả sử một hệ thống bán hàng tạo trung bình 15.000 đơn mỗi ngày. Mỗi đơn có một bản ghi đơn hàng khoảng 400 byte, trung bình 3,2 dòng hàng với mỗi dòng 180 byte và 4 sự kiện lịch sử với mỗi sự kiện 120 byte.

Dung lượng logic ước tính cho một đơn:

```text
Đơn hàng:          1 × 400 = 400 byte
Dòng hàng:       3,2 × 180 = 576 byte
Lịch sử:           4 × 120 = 480 byte
Tổng:                       1.456 byte/đơn
```

Dung lượng logic mỗi ngày:

```text
15.000 × 1.456 = 21.840.000 byte
                 ≈ 21,84 MB/ngày (đơn vị thập phân)
```

Dung lượng logic trong một năm 365 ngày:

```text
21,84 MB × 365 ≈ 7.971,6 MB
                 ≈ 7,97 GB/năm
```

Nếu lưu năm năm và giả định lượng đơn mỗi ngày không đổi, tổng payload logic xấp xỉ 39,86 GB. Dung lượng thực tế của cơ sở dữ liệu sẽ cao hơn hoặc thấp hơn tùy kiểu dữ liệu, overhead, nén, chỉ mục, cập nhật và cách lưu lịch sử. Phép tính này cũng chưa tính các nhóm dữ liệu khác như khách hàng, sản phẩm, thanh toán, tệp đính kèm và bản sao lưu.

## 3. Ước lượng tốc độ tăng trưởng

### 3.1. Phân biệt tăng bản ghi và thay đổi dữ liệu

Dữ liệu tăng theo nhiều cách:

- **Insert:** phát sinh bản ghi mới, như đơn hàng hoặc sự kiện.
- **Update:** thay đổi thuộc tính của bản ghi hiện có, như địa chỉ hoặc trạng thái.
- **Append:** thêm lịch sử, phiên bản hoặc sự kiện thay vì ghi đè.
- **Delete:** xóa hoặc hết hạn dữ liệu, làm giảm dữ liệu trực tuyến nhưng có thể tạo log và backup trong một khoảng thời gian.
- **Import hoặc batch:** tạo ra lượng dữ liệu lớn trong thời gian ngắn.

Một hệ thống có thể có số lượng khách hàng gần như ổn định nhưng vẫn tạo nhiều bản ghi lịch sử, giao dịch và audit log. Vì vậy, cần tách tốc độ tăng số thực thể chính khỏi tốc độ phát sinh dữ liệu phụ trợ.

### 3.2. Tính tốc độ phát sinh

Với nhóm dữ liệu tăng gần tuyến tính, có thể ước lượng:

```text
Số bản ghi tăng trong kỳ
  = Số bản ghi phát sinh trung bình mỗi ngày
    × Số ngày trong kỳ

Dung lượng tăng trong kỳ
  ≈ Số bản ghi tăng × Kích thước trung bình mỗi bản ghi
```

Ví dụ, nếu hệ thống phát sinh 15.000 đơn mỗi ngày và 4 sự kiện lịch sử cho mỗi đơn thì số bản ghi mới mỗi ngày gồm 15.000 đơn và khoảng 60.000 sự kiện. Chỉ tính hai nhóm này đã có 75.000 bản ghi mới mỗi ngày, chưa kể dòng hàng và thanh toán.

Cần dùng số ngày hoạt động thực tế nếu nghiệp vụ không chạy liên tục. Với hệ thống bán lẻ, ngày nghỉ, mùa khuyến mại và chu kỳ lương có thể khiến lượng dữ liệu theo ngày khác nhau đáng kể.

### 3.3. Dự báo tăng trưởng tuyến tính và theo tỷ lệ

Nếu mỗi kỳ phát sinh thêm một lượng tương đối ổn định, dùng mô hình tuyến tính:

```text
N(t) = N0 + r × t
```

Trong đó:

- N0 là số lượng hoặc dung lượng tại thời điểm bắt đầu.
- r là lượng tăng trung bình trong một đơn vị thời gian.
- t là số đơn vị thời gian đã trôi qua.

Nếu tốc độ tăng theo tỷ lệ phần trăm, có thể dùng mô hình lũy thừa:

```text
N(t) = N0 × (1 + g)^t
```

Trong đó g là tỷ lệ tăng trưởng mỗi kỳ, biểu diễn dưới dạng số thập phân. Chẳng hạn, tăng 12% mỗi năm tương ứng với g = 0,12.

Hai mô hình có thể cho kết quả rất khác sau nhiều năm. Cần chọn dựa trên dữ liệu quan sát và hiểu biết về nghiệp vụ. Một chiến dịch mở rộng thị trường có thể làm tăng nhanh số đơn trong vài tháng, nhưng không có nghĩa tốc độ đó sẽ tiếp tục mãi.

### 3.4. Lập kịch bản thay vì một con số duy nhất

Dự báo nên có ít nhất ba kịch bản:

| Kịch bản | Giả định | Cách sử dụng |
|---|---|---|
| Thấp | Tăng trưởng chậm, ít chiến dịch, lượng sử dụng ổn định | Ước lượng nhu cầu tối thiểu |
| Cơ sở | Theo xu hướng và kế hoạch đã được xác nhận | Lập kế hoạch vận hành thông thường |
| Cao | Tăng người dùng, mùa vụ hoặc mở rộng thị trường | Kiểm tra khả năng chịu tải và thời điểm cần mở rộng |

Không nên tùy ý gán tỷ lệ tăng trưởng cho các kịch bản rồi xem đó là dữ liệu thật. Hãy lấy cơ sở từ lịch sử, kế hoạch kinh doanh, số người dùng dự kiến, số giao dịch mỗi người và mùa vụ. Ghi rõ ngày bắt đầu, kỳ dự báo và giả định.

### 3.5. Tách tăng trưởng dữ liệu khỏi tăng trưởng tải

Dung lượng tăng không đồng nghĩa số truy vấn tăng cùng tỷ lệ. Ví dụ, bảng lịch sử có thể tăng hàng triệu dòng nhưng chỉ được đọc khi kiểm tra tranh chấp; bảng danh mục có thể nhỏ nhưng được đọc hàng nghìn lần mỗi giây.

Cần theo dõi riêng:

- Tốc độ tạo bản ghi và cập nhật bản ghi.
- Số lần đọc, ghi và tìm kiếm theo từng mẫu workload.
- Tỷ lệ dữ liệu nóng được truy cập thường xuyên.
- Mức tăng số người dùng và số nghiệp vụ trên mỗi người.
- Tải cao điểm theo thời gian và theo sự kiện.

Thông tin này giúp phân biệt nhu cầu mở rộng lưu trữ với nhu cầu tăng năng lực xử lý.

## 4. Ước lượng độ trễ

### 4.1. Độ trễ là một yêu cầu nghiệp vụ

Độ trễ là khoảng thời gian từ lúc một thao tác được bắt đầu đến khi kết quả cần thiết sẵn sàng. Mục tiêu độ trễ nên được xác định theo trải nghiệm và hậu quả nghiệp vụ.

Ví dụ:

- Tra cứu số dư hoặc xác nhận thanh toán cần phản hồi nhanh để người dùng tiếp tục giao dịch.
- Màn hình danh sách có thể chấp nhận thời gian phản hồi dài hơn một chút nếu có phân trang.
- Báo cáo quản trị có thể mất vài giây hoặc chạy nền nếu người dùng chấp nhận chờ.
- Đồng bộ dữ liệu phân tích có thể trễ vài phút hoặc vài giờ tùy mục đích.

Không nên đặt cùng một ngưỡng cho mọi thao tác. Hãy phân nhóm theo mức quan trọng, khối lượng dữ liệu và kỳ vọng của người dùng.

### 4.2. Phân biệt thời gian phản hồi và thời gian truy vấn

Một yêu cầu từ ứng dụng thường đi qua nhiều bước: mạng, xác thực, xử lý nghiệp vụ, chờ connection pool, truy vấn cơ sở dữ liệu, xử lý kết quả và trả phản hồi. Vì vậy, thời gian truy vấn cơ sở dữ liệu chỉ là một phần của thời gian đầu-cuối.

Có thể mô tả ngân sách độ trễ:

```text
Độ trễ đầu-cuối
  = Thời gian mạng
    + Thời gian ứng dụng
    + Thời gian chờ tài nguyên
    + Thời gian cơ sở dữ liệu
    + Thời gian xử lý kết quả
```

Các thành phần có thể chồng lấp hoặc được thực hiện song song, nên đây là mô hình phân tích đơn giản. Khi đo thực tế, cần dùng tracing hoặc các mốc thời gian nhất quán để xác định phần nào đang chiếm nhiều thời gian.

Nếu yêu cầu nghiệp vụ cần phản hồi trong 300 ms, không thể mặc định toàn bộ 300 ms dành cho truy vấn SQL. Cần phân bổ ngân sách cho các tầng và đo xem cơ sở dữ liệu có đáp ứng phần được giao hay không.

### 4.3. Dùng phân vị thay vì chỉ dùng trung bình

Thời gian trung bình có thể che khuất một nhóm yêu cầu rất chậm. Nên ghi nhận các phân vị:

- **p50:** một nửa số yêu cầu hoàn tất trong thời gian này hoặc nhanh hơn.
- **p95:** 95% số yêu cầu hoàn tất trong thời gian này hoặc nhanh hơn.
- **p99:** 99% số yêu cầu hoàn tất trong thời gian này hoặc nhanh hơn.

Ví dụ, p50 = 40 ms và p99 = 900 ms cho thấy phần lớn truy vấn nhanh nhưng một tỷ lệ nhỏ bị chậm đáng kể. Với thao tác quan trọng, đuôi phân phối có thể ảnh hưởng trực tiếp đến trải nghiệm và thời gian hoàn tất giao dịch.

Khi ghi yêu cầu, hãy nêu rõ phân vị và điều kiện tải. Một mục tiêu p95 khi chỉ có 10 người dùng thử nghiệm không tương đương p95 khi hệ thống có hàng nghìn yêu cầu đồng thời.

### 4.4. Độ trễ đọc, ghi và xử lý bất đồng bộ

Các thao tác có thể có yêu cầu khác nhau:

| Loại thao tác | Câu hỏi cần xác định |
|---|---|
| Đọc theo khóa | Người dùng cần kết quả trong bao lâu? |
| Đọc danh sách | Có giới hạn số dòng và phân trang không? |
| Tìm kiếm | Kết quả mới cần xuất hiện sau bao lâu? |
| Ghi giao dịch | Khi nào có thể xác nhận thành công cho người dùng? |
| Ghi lịch sử/sự kiện | Có cần hoàn tất đồng bộ trong giao dịch chính không? |
| Tổng hợp | Số liệu có thể cũ tối đa bao lâu? |
| Đồng bộ nền | Độ trễ từ lúc phát sinh đến lúc hệ thống đích nhận được là bao nhiêu? |

Đặc biệt, cần phân biệt **độ trễ xử lý** và **độ trễ dữ liệu**. Một báo cáo có thể chạy trong 200 ms nhưng đọc từ dữ liệu được cập nhật cách đây 15 phút. Thời gian phản hồi nhanh không đồng nghĩa dữ liệu mới.

Với xử lý bất đồng bộ, hãy xác định thời gian chờ tối đa trong hàng đợi, thời gian xử lý và thời gian đồng bộ đến nơi tiêu thụ. Tổng các khoảng này tạo thành độ trễ mà nghiệp vụ thực sự quan tâm.

### 4.5. Độ trễ dưới tải cao điểm

Một truy vấn nhanh ở tải thấp có thể chậm khi nhiều giao dịch cùng tranh chấp CPU, I/O, khóa hoặc kết nối. Cần xác định độ trễ mục tiêu tại mức tải đại diện và tải cao điểm.

Những yếu tố thường ảnh hưởng gồm:

- Số yêu cầu đồng thời và số kết nối được cấp.
- Kích thước dữ liệu phải đọc hoặc ghi.
- Độ chọn lọc của bộ lọc và khả năng sử dụng chỉ mục.
- Số lần ghép bảng hoặc duyệt quan hệ.
- Tranh chấp khóa và thời gian chờ giao dịch.
- Cache hit/miss, I/O và hoạt động checkpoint.
- Kích thước batch, retry và hàng đợi nền.

Trong giai đoạn khảo sát, không cần tự quyết định cách tối ưu từng truy vấn. Hãy ghi mẫu truy cập, quy mô, tải và mục tiêu độ trễ để bước thiết kế và kiểm thử có tiêu chí rõ ràng.

## 5. Xác định thời gian lưu dữ liệu

### 5.1. Không phải dữ liệu nào cũng có cùng vòng đời

Thời gian lưu giữ là khoảng thời gian dữ liệu phải được giữ lại để phục vụ nghiệp vụ, kiểm toán, phân tích hoặc yêu cầu pháp lý. Chính sách này nên được xác định theo loại dữ liệu và mục đích sử dụng.

| Nhóm dữ liệu | Ví dụ | Câu hỏi về thời gian lưu |
|---|---|---|
| Dữ liệu giao dịch | Đơn hàng, thanh toán | Cần tra cứu trực tuyến trong bao lâu? |
| Dữ liệu hồ sơ | Khách hàng, nhà cung cấp | Khi nào được ẩn danh hoặc xóa? |
| Lịch sử nghiệp vụ | Chuyển trạng thái, hoàn tiền | Cần giữ để giải quyết khiếu nại trong bao lâu? |
| Audit log | Ai đã thay đổi dữ liệu và lúc nào | Có thời hạn kiểm toán hoặc tuân thủ nào? |
| Sự kiện kỹ thuật | Log ứng dụng, trace | Cần phục vụ điều tra lỗi trong bao lâu? |
| Dữ liệu phân tích | Fact, snapshot, số liệu tổng hợp | Cần so sánh lịch sử trong bao nhiêu kỳ? |
| Dữ liệu tạm | Cache, token, session | Khi nào hết hạn hoặc có thể tái tạo? |

Không nên áp dụng cùng một thời hạn lưu cho toàn bộ hệ thống. Dữ liệu giao dịch có thể cần lưu lâu hơn log kỹ thuật; dữ liệu cá nhân có thể cần xóa hoặc ẩn danh khi hết mục đích xử lý.

### 5.2. Phân biệt lưu trực tuyến, lưu trữ dài hạn và xóa

Một vòng đời dữ liệu có thể có các giai đoạn:

1. **Hot/online:** dữ liệu được truy cập thường xuyên và cần phản hồi nhanh.
2. **Warm:** dữ liệu ít truy cập hơn nhưng vẫn cần tra cứu tương đối thuận tiện.
3. **Cold/archive:** dữ liệu hiếm khi truy cập, có thể lưu trên tầng lưu trữ rẻ hơn và chấp nhận thời gian phục hồi dài hơn.
4. **Expired/deleted:** dữ liệu hết thời hạn hoặc không còn mục đích lưu giữ và được xóa theo chính sách.

Không phải hệ thống nào cũng cần đủ bốn tầng. Việc phân tầng phụ thuộc tần suất truy cập, yêu cầu phục hồi, chi phí và quy định áp dụng.

Khi di chuyển dữ liệu sang archive, cần giữ khả năng truy vết, khóa liên kết và thông tin nguồn. Một truy vấn lịch sử có thể phải đọc cả dữ liệu online và archive; điều này cần được phản ánh trong yêu cầu độ trễ.

### 5.3. Phân biệt xóa nghiệp vụ và xóa vật lý

Một bản ghi bị đánh dấu đã xóa không nhất thiết đã biến mất khỏi mọi nơi. Có thể tồn tại:

- Bản ghi soft delete trong cơ sở dữ liệu chính.
- Bản sao trong replica hoặc cache.
- Bản sao lưu định kỳ.
- Log giao dịch và log kiểm toán.
- Bản trích xuất hoặc hệ thống phân tích.
- Tệp được lưu trong object storage.

Vì vậy, chính sách xóa cần xác định phạm vi, thời điểm và cách xử lý từng bản sao. Nếu yêu cầu là xóa dữ liệu cá nhân, cần làm rõ cách xử lý dữ liệu dẫn xuất, chỉ mục tìm kiếm, backup và dữ liệu đã chia sẻ sang hệ thống khác. Thời gian backup còn hiệu lực cũng cần được xem xét trong chính sách tổng thể.

### 5.4. Chính sách lưu giữ phải có thể thực thi

Một chính sách hữu ích nên ghi rõ:

- Loại dữ liệu và mục đích lưu.
- Thời hạn hoặc điều kiện kết thúc lưu giữ.
- Ngày bắt đầu tính thời hạn: ngày tạo, ngày kết thúc giao dịch hay ngày không còn hoạt động.
- Cách chuyển tầng hoặc xóa dữ liệu.
- Vai trò có quyền phê duyệt hoặc giữ lại dữ liệu.
- Ngoại lệ như legal hold, tranh chấp hoặc điều tra.
- Cách xác minh dữ liệu đã được xử lý ở các hệ thống liên quan.

Không nên chỉ ghi “lưu theo quy định” mà không chỉ ra quy định nào, ai xác nhận và cách triển khai. Khi yêu cầu pháp lý chưa rõ, cần ghi thành giả định hoặc câu hỏi mở để chủ nghiệp vụ và bộ phận phụ trách xác nhận.

## 6. Kết hợp bốn yếu tố trong một mô hình khảo sát

Khối lượng, tăng trưởng, độ trễ và thời gian lưu có quan hệ với nhau. Thời gian lưu càng dài thì tổng số bản ghi tích lũy càng lớn. Tăng trưởng cao có thể làm tăng chi phí chỉ mục và backup. Mục tiêu độ trễ thấp có thể đòi hỏi dữ liệu thường dùng nằm ở tầng lưu trữ nhanh hoặc có cấu trúc truy cập phù hợp.

Có thể dùng bảng sau cho mỗi nhóm dữ liệu:

| Nội dung | Câu hỏi cần trả lời | Ví dụ đơn vị |
|---|---|---|
| Số lượng hiện tại | Có bao nhiêu bản ghi/đỉnh/cạnh/document? | bản ghi |
| Kích thước trung bình | Một bản ghi hoặc document chiếm bao nhiêu? | byte, KB |
| Phát sinh mới | Mỗi ngày hoặc mỗi tháng tạo thêm bao nhiêu? | bản ghi/ngày |
| Tốc độ cập nhật | Bao nhiêu bản ghi thay đổi trong kỳ? | update/giờ |
| Độ trễ truy cập | p95/p99 cần đạt bao nhiêu? | ms, giây |
| Tải cao điểm | Có bao nhiêu yêu cầu hoặc giao dịch tại đỉnh? | QPS, TPS |
| Thời gian online | Cần truy cập nhanh trong bao lâu? | ngày, tháng, năm |
| Thời gian lưu tổng thể | Dữ liệu phải được giữ đến khi nào? | tháng, năm, điều kiện |
| Cách kết thúc vòng đời | Archive, ẩn danh, xóa hoặc giữ lại? | chính sách |

Nên lập một hồ sơ riêng cho các nhóm có đặc tính khác nhau. Ví dụ, đơn hàng, audit log và ảnh sản phẩm không nên dùng cùng một kích thước trung bình, tốc độ tăng hay thời gian lưu.

## 7. Dùng kết quả để định hướng thiết kế dữ liệu

Các ước lượng giúp đưa ra câu hỏi thiết kế cụ thể:

- **Khối lượng lớn và tăng liên tục:** xem xét cách phân vùng, chiến lược khóa, lưu trữ lịch sử và giới hạn phạm vi truy vấn.
- **Quan hệ một-nhiều có cardinality cao:** kiểm tra kích thước tập con, cách phân trang và nguy cơ tải quá nhiều dữ liệu cùng lúc.
- **Tìm kiếm trên dữ liệu lớn:** xác định trường lọc, tính chọn lọc, chỉ mục và yêu cầu độ mới của kết quả.
- **Đọc lịch sử dài hạn:** xác định có cần archive, partition theo thời gian hoặc kho phân tích.
- **Ghi đồng thời cao:** xác định điểm tranh chấp, ranh giới giao dịch và yêu cầu nhất quán.
- **Độ trễ nghiêm ngặt:** xác định dữ liệu nào cần truy cập nhanh, đường đi của yêu cầu và ngân sách thời gian cho từng tầng.
- **Yêu cầu lưu giữ khác nhau:** tách chính sách theo nhóm dữ liệu để tránh lưu mọi thứ cùng thời hạn.

Những kết quả này có thể ảnh hưởng đến mô hình quan hệ, document, đồ thị hoặc phân tích. Chẳng hạn, document có thể phù hợp khi dữ liệu thường được đọc theo một aggregate có kích thước kiểm soát được; mô hình quan hệ có thể phù hợp với giao dịch cần ràng buộc và tính nhất quán giữa nhiều thực thể; mô hình phân tích phù hợp với lịch sử lớn và truy vấn tổng hợp. Quyết định cuối cùng còn phụ thuộc workload, quan hệ, tính nhất quán và khả năng vận hành.

## 8. Các sai sót thường gặp

- Chỉ đếm bảng chính mà bỏ qua bảng con, bảng liên kết, lịch sử và audit log.
- Dùng kích thước khai báo của kiểu dữ liệu làm kích thước hàng thực tế mà không đo dữ liệu mẫu.
- Nhầm dung lượng logic với dung lượng database hoặc dung lượng triển khai có backup và replica.
- Ngoại suy tốc độ tăng trưởng từ một giai đoạn ngắn có mùa vụ bất thường.
- Dùng một tỷ lệ tăng trưởng duy nhất cho mọi nhóm dữ liệu.
- Đồng nhất tốc độ tăng dung lượng với tốc độ tăng truy vấn.
- Chỉ đặt mục tiêu độ trễ trung bình, không xem p95, p99 và điều kiện tải.
- Chỉ đo thời gian truy vấn mà bỏ qua thời gian chờ connection pool, mạng và xử lý ứng dụng.
- Lưu dữ liệu vô thời hạn mà không có mục đích và chính sách.
- Xem soft delete là đã xóa hoàn toàn khỏi backup, cache và hệ thống phụ.
- Chuyển dữ liệu sang archive nhưng không xác định cách tìm kiếm và thời gian phục hồi.

## 9. Checklist hoàn tất ước lượng

Trước khi chuyển sang thiết kế chi tiết, hãy kiểm tra:

- [ ] Đã liệt kê các nhóm dữ liệu chính, dữ liệu liên quan, lịch sử và sự kiện.
- [ ] Đã ước lượng số lượng bản ghi và cardinality của các quan hệ.
- [ ] Đã xác định kích thước trung bình bằng dữ liệu mẫu hoặc ghi rõ giả định.
- [ ] Đã tách dung lượng logic, dung lượng cơ sở dữ liệu và dung lượng triển khai.
- [ ] Đã ước lượng insert, update, append và delete theo từng nhóm.
- [ ] Đã có kịch bản tăng trưởng thấp, cơ sở và cao cùng thời hạn dự báo.
- [ ] Đã phân biệt tăng trưởng dữ liệu với tăng trưởng workload.
- [ ] Đã đặt mục tiêu độ trễ theo loại thao tác và phân vị phù hợp.
- [ ] Đã tính đến tải cao điểm, thời gian chờ và xử lý bất đồng bộ.
- [ ] Đã xác định thời gian online, thời gian lưu tổng thể và điều kiện xóa.
- [ ] Đã xem xét archive, backup, replica, cache và các bản sao liên quan.
- [ ] Các số liệu đã được phân loại là đo thực tế, ước lượng hay mục tiêu; giả định chưa xác nhận đã được ghi lại.

Một ước lượng tốt giúp nhóm thiết kế hiểu dữ liệu sẽ lớn đến đâu, tăng nhanh như thế nào, cần phục vụ trong thời gian bao lâu và phải được giữ lại đến khi nào. Khi những yêu cầu này được ghi rõ, quyết định về lược đồ, khóa, chỉ mục, phân vùng, tầng lưu trữ và vòng đời dữ liệu sẽ có cơ sở để kiểm chứng trong quá trình phát triển.

