# Thông lượng giao dịch, truy vấn và số yêu cầu xử lý thành công

Trong tối ưu hiệu năng cơ sở dữ liệu, thời gian xử lý của một truy vấn chỉ cho biết một phần trải nghiệm. Khi hệ thống phục vụ nhiều người dùng đồng thời, ta còn cần biết trong một giây cơ sở dữ liệu và ứng dụng hoàn thành được bao nhiêu công việc. Đại lượng đó gọi là **thông lượng** (*throughput*).

Thông lượng giúp trả lời những câu hỏi như: hệ thống xử lý được bao nhiêu giao dịch mỗi giây, thực thi bao nhiêu câu lệnh SQL mỗi giây, có bao nhiêu yêu cầu hoàn tất thành công, và năng lực xử lý thay đổi ra sao khi tải tăng. Để con số có ý nghĩa, cần xác định rõ đang đếm loại công việc nào, đếm ở lớp nào và chỉ công nhận những kết quả nào là thành công.

## 1. Phân biệt thông lượng yêu cầu, truy vấn và giao dịch

Một yêu cầu từ người dùng có thể đi qua nhiều lớp trước khi hoàn tất. Ví dụ, thao tác đặt hàng gửi một yêu cầu HTTP đến ứng dụng; ứng dụng kiểm tra tồn kho, ghi đơn hàng và cập nhật số lượng bằng nhiều câu lệnh SQL trong một hoặc vài giao dịch. Vì vậy, số yêu cầu, số câu lệnh SQL và số giao dịch không nhất thiết bằng nhau.

| Chỉ số | Đơn vị thường dùng | Sự kiện được đếm | Ý nghĩa |
|---|---|---|---|
| RPS (*requests per second*) | yêu cầu/giây | Yêu cầu ứng dụng được tiếp nhận hoặc hoàn tất, tùy định nghĩa đo | Năng lực phục vụ ở lớp API hoặc dịch vụ |
| QPS (*queries per second*) | truy vấn/giây | Câu lệnh truy vấn được cơ sở dữ liệu thực thi | Mức hoạt động của lớp truy cập dữ liệu |
| TPS (*transactions per second*) | giao dịch/giây | Giao dịch cơ sở dữ liệu kết thúc bằng commit | Số đơn vị công việc giao dịch được ghi nhận hoàn tất |
| Goodput | công việc thành công/giây | Yêu cầu hoặc giao dịch đáp ứng điều kiện thành công đã định nghĩa | Lượng công việc hữu ích mà hệ thống thực sự hoàn thành |

### RPS: thông lượng yêu cầu

RPS thường được đo ở cổng API hoặc dịch vụ ứng dụng. Cần phân biệt **tốc độ yêu cầu đến** với **tốc độ yêu cầu hoàn tất**. Tốc độ đến cho biết tải mà hệ thống phải tiếp nhận; tốc độ hoàn tất cho biết hệ thống thực sự xử lý xong bao nhiêu yêu cầu trong khoảng thời gian đó. Nếu hàng đợi tăng liên tục, tốc độ đến có thể cao hơn tốc độ hoàn tất dù biểu đồ tiếp nhận vẫn đẹp.

Khi đo ở lớp ứng dụng, hãy ghi rõ phạm vi: một yêu cầu HTTP, một lệnh nghiệp vụ hay một lần gọi dịch vụ. Một yêu cầu có thể không truy cập cơ sở dữ liệu vì dữ liệu được lấy từ bộ nhớ đệm; cũng có thể phát sinh nhiều lần đọc hoặc ghi dữ liệu.

### QPS: thông lượng truy vấn

QPS biểu thị số câu lệnh truy vấn mà hệ quản trị cơ sở dữ liệu thực thi trong một giây. Chỉ số này giúp quan sát tải truy cập dữ liệu, nhưng không phản ánh trực tiếp số nghiệp vụ đã hoàn tất. Một truy vấn đọc đơn giản và một truy vấn tổng hợp nhiều bảng đều có thể được tính là một lần thực thi, dù chi phí CPU, I/O và thời gian xử lý rất khác nhau.

Khi đếm QPS, cần thống nhất cách tính với câu lệnh theo lô (*batch*), câu lệnh được gọi lặp lại và truy vấn nội bộ. Một lần gửi batch có thể chứa nhiều câu lệnh; tùy công cụ đo, nó có thể được ghi nhận như một lần gọi hoặc nhiều lần thực thi. Hãy dùng cùng một quy ước khi so sánh các lần kiểm thử.

### TPS: thông lượng giao dịch

TPS thường được tính bằng số giao dịch đã commit trong một giây. Một giao dịch có thể chứa nhiều câu lệnh SQL nhưng chỉ được tính là một giao dịch khi hoàn tất. Giao dịch bị rollback, bị hủy hoặc chưa kết thúc không được tính là giao dịch thành công.

Đừng đồng nhất TPS của cơ sở dữ liệu với số giao dịch nghiệp vụ. Một nghiệp vụ có thể sử dụng nhiều giao dịch cơ sở dữ liệu, hoặc nhiều thao tác nghiệp vụ có thể được xử lý trong cùng một giao dịch. Cần chọn ranh giới đếm phù hợp với câu hỏi đang đo và ghi rõ ranh giới đó trong báo cáo.

### Goodput: thông lượng thành công

Goodput đo lượng công việc hữu ích hoàn tất trong một đơn vị thời gian. Với một API, đó có thể là số yêu cầu trả về kết quả thành công theo hợp đồng của API mỗi giây. Với cơ sở dữ liệu, đó có thể là số giao dịch commit và thỏa điều kiện dữ liệu đúng mỗi giây.

Goodput đặc biệt quan trọng khi hệ thống chịu tải cao. Nếu hệ thống nhận 1.000 yêu cầu mỗi giây nhưng chỉ hoàn tất thành công 700 yêu cầu, con số 1.000 RPS không thể hiện năng lực phục vụ thành công. Khi báo cáo, nên đặt thông lượng tổng và thông lượng thành công cạnh nhau.

## 2. Công thức và quy ước đếm

Với một khoảng đo có thời lượng \(T\) giây, thông lượng được tính như sau:

\[
\text{Throughput} = \frac{\text{Số sự kiện được đếm trong khoảng đo}}{T}
\]

Thông lượng thành công được tính bằng:

\[
\text{Goodput} = \frac{\text{Số sự kiện hoàn tất thành công}}{T}
\]

Tỷ lệ thành công và tỷ lệ lỗi bổ sung góc nhìn về chất lượng xử lý:

\[
\text{Tỷ lệ thành công} = \frac{\text{Số lần thành công}}{\text{Tổng số lần hoàn tất}} \times 100\%
\]

\[
\text{Tỷ lệ lỗi} = \frac{\text{Số lần lỗi}}{\text{Tổng số lần hoàn tất}} \times 100\%
\]

Mẫu số phải được định nghĩa nhất quán. Nếu báo cáo bao gồm cả yêu cầu hết thời gian chờ, yêu cầu bị từ chối và yêu cầu thất bại trước khi hoàn tất, hãy nêu rõ cách phân loại. Với yêu cầu đang còn trong hàng đợi khi kết thúc phép đo, không nên tính chúng là yêu cầu hoàn tất.

### Xác định thế nào là thành công

Điều kiện thành công cần gắn với ý nghĩa của thao tác:

- Với yêu cầu đọc, kết quả phải trả về hợp lệ và đáp ứng hợp đồng dữ liệu.
- Với yêu cầu ghi, dữ liệu phải được commit và thỏa các bất biến nghiệp vụ cần thiết.
- Với giao dịch, kết quả commit là dấu mốc hoàn tất ở lớp cơ sở dữ liệu; nếu cần đo thành công nghiệp vụ, phải kiểm tra thêm kết quả mà ứng dụng trả về.
- Với thao tác có thời hạn phục vụ, một kết quả trả về sau ngưỡng thời gian quy định có thể được phân loại là không đạt mục tiêu, dù cuối cùng vẫn hoàn tất.

Không nên coi mọi phản hồi HTTP 2xx là thành công nghiệp vụ nếu ứng dụng trả lỗi trong phần thân phản hồi. Tương tự, việc câu lệnh SQL không phát sinh lỗi cú pháp không chứng minh rằng giao dịch đã commit hoặc dữ liệu đạt trạng thái mong muốn.

### Xử lý retry và yêu cầu trùng

Khi một yêu cầu thất bại tạm thời, ứng dụng có thể gửi lại. Cần tách **lượt thử** khỏi **thao tác logic**. Nếu đếm mỗi lần retry như một yêu cầu mới, RPS có thể tăng trong khi số công việc thực sự hoàn tất không tăng. Với nghiệp vụ có khóa idempotency, hãy đếm một thao tác logic thành công một lần; đồng thời ghi riêng số lượt thử, số lần retry và số yêu cầu trùng được loại bỏ.

Đối với ghi dữ liệu, phải kiểm tra khả năng một lần thử đầu đã commit nhưng phản hồi bị mất. Retry thiếu cơ chế idempotency có thể tạo bản ghi hoặc giao dịch trùng. Báo cáo thông lượng nên dựa trên kết quả nghiệp vụ duy nhất, đồng thời giữ số lần thực thi SQL để phân tích chi phí phát sinh.

### Chọn khoảng thời gian đo

Luôn ghi rõ thời lượng và cách tổng hợp. Ví dụ, 60.000 yêu cầu hoàn tất trong 5 phút tương đương trung bình 200 yêu cầu/giây. Tuy nhiên, trung bình 5 phút có thể che khuất một phút bị nghẽn hoặc một khoảng ngắn có lỗi tăng cao.

Nên lưu số liệu theo các cửa sổ ngắn, chẳng hạn 10 hoặc 60 giây, rồi tổng hợp cho toàn bài kiểm thử. Khi so sánh hai lần chạy, dùng cùng độ dài cửa sổ và cùng quy tắc loại bỏ giai đoạn khởi động. Tránh so sánh một lần chạy lấy trung bình toàn thời gian với lần khác chỉ lấy giai đoạn ổn định.

## 3. Thiết kế phép đo thông lượng có thể lặp lại

Một con số thông lượng chỉ có thể so sánh khi tải thử được mô tả đủ rõ. Trước khi chạy, hãy xác định:

1. **Phạm vi đo:** API, truy vấn SQL, giao dịch cơ sở dữ liệu hay nghiệp vụ hoàn chỉnh.
2. **Hỗn hợp công việc:** tỷ lệ đọc/ghi, loại truy vấn, kích thước dữ liệu, số bảng tham gia và độ dài giao dịch.
3. **Mức tải:** tốc độ yêu cầu đến, số người dùng đồng thời, cách tăng tải và thời gian duy trì tải.
4. **Điều kiện dữ liệu:** kích thước tập dữ liệu, phân bố khóa, mức độ nóng của bộ nhớ đệm và trạng thái chỉ mục.
5. **Điều kiện môi trường:** cấu hình máy, phiên bản phần mềm, cấu hình kết nối, giới hạn tài nguyên và các tác vụ nền.
6. **Tiêu chí thành công:** kết quả nào được tính, cách xử lý timeout, rollback, retry và yêu cầu bị từ chối.

### Thu thập số liệu ở nhiều lớp

Không nên chỉ dựa vào một bộ đếm ở cơ sở dữ liệu. Hãy ghép số liệu ứng dụng với số liệu hệ quản trị để biết lượng công việc đi vào đã chuyển thành kết quả như thế nào.

| Lớp quan sát | Số liệu nên thu thập | Câu hỏi cần trả lời |
|---|---|---|
| Ứng dụng | yêu cầu đến, hoàn tất, thành công, lỗi, timeout, retry, độ dài hàng đợi, số yêu cầu đang xử lý | Ứng dụng tiếp nhận và hoàn tất được bao nhiêu công việc? |
| Giao dịch | số commit, rollback, thời gian giao dịch, giao dịch đang mở | Bao nhiêu giao dịch kết thúc thành công và giao dịch có bị giữ quá lâu không? |
| Truy vấn | số lần thực thi theo nhóm truy vấn, số hàng đọc/ghi, thời gian thực thi | Truy vấn nào chiếm phần lớn hoạt động hoặc chi phí? |
| Tài nguyên cơ sở dữ liệu | CPU, I/O, độ trễ lưu trữ, bộ nhớ đệm, khóa, kết nối và hàng đợi | Tài nguyên nào đang giới hạn thông lượng? |

Nên nhóm truy vấn theo mẫu hoặc loại thao tác thay vì gắn nhãn bằng toàn bộ câu SQL chứa giá trị riêng của từng người dùng. Việc này giúp nhận diện truy vấn tốn tài nguyên mà vẫn giữ số liệu gọn và dễ tổng hợp.

### Quy trình kiểm thử tải

Một quy trình thực tế có thể gồm các bước sau:

1. Chuẩn bị tập dữ liệu gần với quy mô và phân bố dữ liệu dự kiến trong môi trường thật.
2. Khởi động hệ thống và chạy một giai đoạn làm nóng để bộ nhớ đệm, kết nối và các thành phần nền đạt trạng thái phù hợp.
3. Tăng tải theo từng mức có kiểm soát, ghi lại tốc độ đến, số yêu cầu đang xử lý và thông lượng hoàn tất.
4. Duy trì mỗi mức tải đủ lâu để quan sát trạng thái ổn định, độ trễ, lỗi và mức sử dụng tài nguyên.
5. Lặp lại phép đo để đánh giá độ biến động; giữ nguyên cấu hình và kịch bản giữa các lần chạy.
6. Nếu cần đánh giá khởi động lạnh, thực hiện thành một kịch bản riêng và ghi rõ trạng thái cache.

Máy tạo tải cũng phải đủ năng lực. Nếu CPU, mạng hoặc số luồng của công cụ kiểm thử đã chạm giới hạn, kết quả sẽ phản ánh giới hạn của máy tạo tải thay vì của cơ sở dữ liệu. Hãy theo dõi tài nguyên ở cả hai phía.

## 4. Quan hệ giữa thông lượng, độ trễ và mức đồng thời

Thông lượng không thể được đánh giá độc lập với độ trễ. Khi tải tăng, hệ thống thường tăng thông lượng cho đến khi một tài nguyên trở thành nút thắt. Sau điểm đó, hàng đợi và thời gian chờ có thể tăng nhanh trong khi thông lượng chỉ tăng rất ít, giữ nguyên hoặc giảm.

Một hệ thống có thể đạt thông lượng cao bằng cách giữ nhiều yêu cầu đồng thời, nhưng điều đó không có nghĩa từng yêu cầu phản hồi nhanh. Vì vậy, hãy xem thông lượng cùng độ trễ trung bình, p95 hoặc p99, tỷ lệ lỗi và số yêu cầu đang chờ. Phân vị độ trễ cho biết trải nghiệm của nhóm yêu cầu chậm, điều mà giá trị trung bình thường che giấu.

Định luật Little mô tả quan hệ giữa số công việc trung bình đang ở trong hệ thống, thông lượng và thời gian lưu lại trong hệ thống:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\) là số yêu cầu trung bình đang được xử lý hoặc chờ xử lý.
- \(\lambda\) là thông lượng hoàn tất trung bình trong một đơn vị thời gian.
- \(W\) là thời gian trung bình một yêu cầu ở trong hệ thống.

Ví dụ, nếu hệ thống hoàn tất trung bình 200 yêu cầu/giây và mỗi yêu cầu ở trong hệ thống trung bình 0,25 giây, số yêu cầu đang xử lý hoặc chờ trung bình xấp xỉ 50. Đây là cách kiểm tra tính hợp lý của số liệu đồng thời, không phải công thức thay thế phép đo.

Khi thông lượng không tăng theo tải, hãy kiểm tra CPU, độ trễ đọc/ghi đĩa, tỷ lệ cache hit, tranh chấp khóa, số kết nối, thời gian chờ lấy kết nối và kích thước hàng đợi. Chẳng hạn, tăng số kết nối có thể làm tăng mức đồng thời nhưng cũng có thể khiến nhiều truy vấn tranh CPU hoặc khóa hơn, khiến thông lượng thành công giảm.

## 5. Ví dụ tính toán và đọc kết quả

Giả sử một bài kiểm thử chạy ổn định trong 300 giây và ghi nhận:

- 33.000 yêu cầu ứng dụng đã kết thúc; trong đó 30.000 yêu cầu thành công và 3.000 yêu cầu thất bại.
- 30.000 giao dịch cơ sở dữ liệu đã commit; các giao dịch thất bại không được tính vào số này.
- 450.000 câu lệnh SQL đã được thực thi trong cùng khoảng đo.

Ta tính được:

| Chỉ số | Phép tính | Kết quả |
|---|---:|---:|
| Tốc độ yêu cầu hoàn tất | 33.000 / 300 | 110 RPS |
| Thông lượng yêu cầu thành công | 30.000 / 300 | 100 yêu cầu/giây |
| Tỷ lệ thành công | 30.000 / 33.000 × 100% | khoảng 90,9% |
| Thông lượng giao dịch commit | 30.000 / 300 | 100 TPS |
| Thông lượng câu lệnh SQL | 450.000 / 300 | 1.500 QPS |

Nếu toàn bộ 450.000 câu lệnh thuộc 30.000 giao dịch đã commit, trung bình mỗi giao dịch thực thi 15 câu lệnh. Nếu số câu lệnh còn bao gồm giao dịch rollback, truy vấn thăm dò hoặc công việc nền, không thể dùng phép chia này để kết luận số câu lệnh trung bình của một giao dịch thành công. Cần có số liệu phân nhóm theo giao dịch hoặc loại thao tác để xác nhận.

Kết quả cho thấy cơ sở dữ liệu thực thi 1.500 câu lệnh mỗi giây và commit 100 giao dịch mỗi giây, trong khi ứng dụng chỉ hoàn tất thành công 100 yêu cầu mỗi giây. Tỷ lệ lỗi khoảng 9,1% là dấu hiệu cần điều tra. Chỉ tăng QPS hoặc RPS tổng không giải quyết được vấn đề nếu tỷ lệ thành công không cải thiện.

## 6. Đặt mục tiêu thông lượng có ý nghĩa

Mục tiêu kiểu “cơ sở dữ liệu phải đạt 2.000 QPS” thường chưa đủ để định hướng tối ưu. QPS cao có thể đến từ việc ứng dụng phát sinh quá nhiều truy vấn nhỏ, truy vấn lặp hoặc retry. Một mục tiêu hữu ích cần mô tả tải, điều kiện thành công và giới hạn chất lượng dịch vụ.

Có thể viết mục tiêu theo mẫu:

> Với tập dữ liệu có quy mô đã xác định, hỗn hợp đọc/ghi và mức đồng thời đã xác định, hệ thống phải duy trì ít nhất **N giao dịch thành công mỗi giây** trong **T phút**, với p95 không vượt quá **L**, tỷ lệ lỗi không vượt quá **E**, đồng thời mức sử dụng CPU, I/O và kết nối nằm trong giới hạn vận hành.

Trong đó, N, T, L và E phải được xác định từ nhu cầu sản phẩm, tải dự kiến và cam kết dịch vụ. Không nên lấy một con số tối đa đo được trong vài giây làm mục tiêu vận hành dài hạn.

Khi lập bảng mục tiêu, nên có tối thiểu các trường sau:

| Thành phần mục tiêu | Nội dung cần ghi |
|---|---|
| Kịch bản tải | loại nghiệp vụ, tỷ lệ đọc/ghi, kích thước dữ liệu |
| Mức tải | tốc độ đến và số thao tác đồng thời |
| Goodput tối thiểu | số yêu cầu hoặc giao dịch thành công mỗi giây |
| Giới hạn độ trễ | p95/p99 hoặc ngưỡng thời gian theo yêu cầu |
| Giới hạn lỗi | timeout, rollback và lỗi ứng dụng cho phép |
| Giới hạn tài nguyên | CPU, I/O, bộ nhớ và kết nối |
| Thời gian duy trì | khoảng thời gian hệ thống phải giữ được mục tiêu |

Hãy đặt mục tiêu riêng cho các nhóm công việc có đặc tính khác nhau, ví dụ đọc theo khóa, truy vấn báo cáo và ghi giao dịch. Gộp tất cả thành một số duy nhất có thể che khuất việc một nhóm truy vấn đang làm giảm chất lượng của nhóm khác.

## 7. Dùng thông lượng để đánh giá thay đổi tối ưu

Khi thay đổi chỉ mục, câu SQL, cấu hình kết nối hoặc cách quản lý giao dịch, hãy chạy lại cùng kịch bản tải và so sánh các chỉ số trước/sau. Một thay đổi được xem là có ích khi lượng công việc thành công tăng hoặc được duy trì ổn định hơn, trong khi độ trễ, lỗi và mức tiêu thụ tài nguyên vẫn đáp ứng mục tiêu.

Ví dụ, sau khi thêm chỉ mục, QPS có thể giảm vì mỗi nghiệp vụ cần ít câu lệnh hơn, nhưng TPS và goodput lại tăng do thời gian truy vấn ngắn hơn. Đây vẫn có thể là kết quả tốt. Ngược lại, QPS tăng mạnh do retry hoặc truy vấn lặp không phải dấu hiệu cải thiện nếu số giao dịch thành công không tăng.

Để phép so sánh đáng tin cậy:

- Dùng cùng dữ liệu, kịch bản, hỗn hợp đọc/ghi, mức đồng thời và thời lượng đo.
- Giữ nguyên điều kiện warm-up hoặc cold-cache giữa các lần chạy.
- Ghi lại phiên bản ứng dụng, cấu hình cơ sở dữ liệu và thay đổi môi trường.
- So sánh theo từng cửa sổ thời gian, không chỉ nhìn trung bình toàn bài kiểm thử.
- Đối chiếu thông lượng với p95/p99, tỷ lệ lỗi, rollback, retry và tài nguyên.
- Chạy lặp lại để xác định kết quả có ổn định hay chỉ là dao động ngẫu nhiên.

Nếu thông lượng thành công tăng nhưng độ trễ p99 vượt ngưỡng, thay đổi có thể đang làm một nhóm người dùng chịu ảnh hưởng lớn. Nếu thông lượng giữ nguyên nhưng CPU hoặc I/O giảm đáng kể, thay đổi có thể tạo thêm dư địa cho tải đỉnh. Hãy đánh giá theo mục tiêu đã thống nhất thay vì chỉ chọn chỉ số có vẻ tăng.

## 8. Những sai lầm thường gặp

1. **Đếm yêu cầu đến như yêu cầu hoàn tất:** hàng đợi có thể tăng dù hệ thống không xử lý kịp.
2. **Đồng nhất QPS, TPS và RPS:** ba chỉ số đếm các loại sự kiện khác nhau.
3. **Bỏ qua lỗi và timeout:** thông lượng tổng cao có thể đi cùng goodput thấp.
4. **Tính retry thành công việc mới:** số lượt thử tăng nhưng số thao tác logic hoàn tất không tăng.
5. **Chỉ đo trong thời gian ngắn:** kết quả có thể chưa phản ánh trạng thái ổn định hoặc tải nền.
6. **Dùng dữ liệu quá nhỏ:** cache và chỉ mục có thể hoạt động khác xa khi dữ liệu đạt quy mô thực tế.
7. **Không kiểm tra máy tạo tải:** giới hạn của công cụ kiểm thử có thể làm sai kết luận về cơ sở dữ liệu.
8. **Chỉ báo cáo một giá trị trung bình:** các đợt nghẽn ngắn và độ trễ đuôi có thể bị che khuất.
9. **Không ghi lại quy ước đếm:** hai lần đo có thể không cùng định nghĩa thành công hoặc cùng phạm vi truy vấn.

## 9. Danh sách kiểm tra trước khi công bố kết quả

- [ ] Đã xác định rõ sự kiện được đếm ở lớp ứng dụng, truy vấn hay giao dịch.
- [ ] Đã phân biệt tốc độ yêu cầu đến, tốc độ hoàn tất và goodput.
- [ ] Đã quy định cách tính commit, rollback, timeout, retry và yêu cầu trùng.
- [ ] Đã ghi thời lượng đo, cửa sổ tổng hợp và giai đoạn warm-up.
- [ ] Đã mô tả tập dữ liệu, hỗn hợp đọc/ghi và mức tải đồng thời.
- [ ] Đã thu thập số liệu ứng dụng, giao dịch, truy vấn và tài nguyên cơ sở dữ liệu.
- [ ] Đã theo dõi độ trễ phân vị, tỷ lệ lỗi và hàng đợi cùng thông lượng.
- [ ] Đã xác nhận công cụ tạo tải không phải nút thắt.
- [ ] Đã chạy lặp lại và so sánh trong cùng điều kiện.
- [ ] Mục tiêu thông lượng gắn với điều kiện thành công và giới hạn chất lượng dịch vụ.

Thông lượng là thước đo lượng công việc hệ thống hoàn thành trong một khoảng thời gian. RPS cho biết nhịp phục vụ yêu cầu ở lớp ứng dụng, QPS mô tả hoạt động thực thi truy vấn, TPS phản ánh giao dịch commit, còn goodput cho biết lượng công việc thành công. Khi định nghĩa ranh giới đếm rõ ràng và kết hợp các chỉ số này với độ trễ, lỗi cùng mức sử dụng tài nguyên, nhóm phát triển có thể xác định đúng giới hạn hiện tại và kiểm chứng hiệu quả của từng thay đổi tối ưu cơ sở dữ liệu.
