# Biểu đồ phân bố, giá trị phổ biến và dữ liệu lệch

## 1. Vì sao phân bố dữ liệu quan trọng với bộ tối ưu?

Khi lập kế hoạch thực thi SQL, bộ tối ưu phải dự đoán một điều kiện lọc sẽ giữ lại bao nhiêu dòng, phép nối sẽ tạo ra bao nhiêu dòng và mỗi toán tử cần xử lý lượng dữ liệu lớn đến mức nào. Các dự đoán này ảnh hưởng đến lựa chọn quét bảng hay dùng chỉ mục, thứ tự nối, nested loop hay hash join, cách nhóm dữ liệu và lượng bộ nhớ cần cấp.

Nếu dữ liệu phân bố đồng đều, một số giả định đơn giản có thể cho kết quả tương đối gần thực tế. Nhưng dữ liệu nghiệp vụ thường lệch: một vài trạng thái xuất hiện rất nhiều, một số khách hàng có lượng giao dịch vượt xa phần còn lại, hoặc một giá trị khóa nối tập trung phần lớn bản ghi. Khi đó, giả định rằng mọi giá trị có tần suất gần bằng nhau sẽ tạo ra ước lượng sai.

Trong tối ưu hiệu năng cơ sở dữ liệu, thống kê phân bố giúp bộ tối ưu nhận biết hình dạng dữ liệu. Biểu đồ phân bố (histogram) mô tả cách giá trị trải trên một cột; danh sách giá trị phổ biến (most common values, MCV) ghi nhận các giá trị xuất hiện nhiều; số giá trị phân biệt (NDV), tỷ lệ NULL và các thống kê đa cột bổ sung những thông tin cần thiết để ước lượng độ chọn lọc (selectivity).

Bài học này giải thích cách đọc histogram, MCV và dữ liệu lệch, cách chúng ảnh hưởng đến kế hoạch thực thi, giới hạn của thống kê một cột và quy trình kiểm chứng khi ước lượng sai. Tên trường, thuật toán lấy mẫu và kiểu histogram khác nhau theo hệ quản trị cơ sở dữ liệu; cần đối chiếu tài liệu của hệ thống đang vận hành trước khi diễn giải một trường cụ thể.

## 2. Các khái niệm nền tảng

### 2.1. Phân bố và độ lệch

Phân bố cho biết mỗi giá trị hoặc nhóm giá trị chiếm bao nhiêu phần trong tập dữ liệu. Nếu 1.000.000 đơn hàng có 10 trạng thái và mỗi trạng thái chiếm xấp xỉ 10%, phân bố trạng thái tương đối đồng đều. Nếu trạng thái `COMPLETED` chiếm 85%, `CANCELLED` chiếm 10% và các trạng thái còn lại chỉ chiếm 5%, dữ liệu bị lệch về `COMPLETED`.

Độ lệch (skew) là mức độ một vài giá trị hoặc nhóm giá trị chiếm tỷ trọng lớn hơn hẳn phần còn lại. Độ lệch có thể xuất hiện theo nhiều cách:

- **Lệch tần suất giá trị:** một vài giá trị có số dòng rất cao, chẳng hạn một tenant lớn có gần một nửa số bản ghi.
- **Lệch theo khoảng giá trị:** phần lớn số liệu tập trung trong một vùng hẹp, còn một số ít giá trị nằm ở đuôi phân bố.
- **Lệch theo nhóm hoặc phân vùng:** một partition, shard hoặc worker nhận nhiều dữ liệu hơn hẳn các phần khác.
- **Lệch kết hợp nhiều cột:** từng cột riêng lẻ có vẻ bình thường nhưng một số tổ hợp giá trị xuất hiện rất thường xuyên.

Độ lệch không tự động là lỗi thiết kế. Nó thường phản ánh đúng nghiệp vụ. Vấn đề xuất hiện khi bộ tối ưu không có đủ thông tin để dự đoán tần suất và chọn kế hoạch phù hợp.

### 2.2. Độ chọn lọc (selectivity)

Độ chọn lọc của một điều kiện là tỷ lệ dòng thỏa điều kiện trong tổng số dòng thuộc phạm vi xét:

\[
\text{Selectivity} = \frac{\text{số dòng thỏa điều kiện}}{\text{tổng số dòng}}
\]

Ví dụ, bảng có 1.000.000 dòng và điều kiện `status = 'CANCELLED'` trả về 50.000 dòng. Độ chọn lọc là 0,05, tức 5%. Điều kiện có độ chọn lọc thấp thường giữ lại ít dòng; điều kiện có độ chọn lọc cao giữ lại phần lớn bảng. Cách gọi này cần thống nhất trong nhóm vì một số tài liệu dùng từ “selective” để nói điều kiện lọc mạnh, tức tỷ lệ kết quả nhỏ.

Độ chọn lọc ảnh hưởng đến lợi ích của chỉ mục. Nếu điều kiện chỉ giữ một số ít dòng và chỉ mục phù hợp, truy cập qua chỉ mục có thể tránh đọc phần lớn bảng. Nếu điều kiện giữ lại phần lớn bảng, quét tuần tự có thể hiệu quả hơn do đọc liên tục và giảm chi phí truy cập ngẫu nhiên. Kết luận cuối cùng còn phụ thuộc kích thước dòng, clustering, cache, phân vùng, khả năng covering của chỉ mục và chi phí truy cập thực tế.

### 2.3. NDV, NULL và tần suất

NDV (number of distinct values) là số giá trị phân biệt mà thống kê ghi nhận hoặc ước lượng trong một cột. Nếu một bảng có 1.000.000 dòng và `country_code` có 20 giá trị khác nhau, NDV của cột xấp xỉ 20. NDV giúp bộ tối ưu ước lượng số dòng trung bình cho một giá trị khi không có thông tin tần suất cụ thể.

Tỷ lệ NULL cho biết phần dòng có giá trị NULL. Điều kiện so sánh bằng thông thường như `column = value` không khớp với NULL theo logic SQL ba giá trị. Vì vậy, thống kê NULL có ý nghĩa riêng khi ước lượng `IS NULL`, `IS NOT NULL` hoặc các phép nối có thể bị ảnh hưởng bởi NULL.

Nếu giả định phân bố đều, với tổng số dòng không NULL là \(N\) và NDV là \(D\), bộ tối ưu có thể ước lượng một giá trị bất kỳ chiếm khoảng:

\[
\text{Rows per value} \approx \frac{N}{D}
\]

Đây chỉ là ước lượng nền khi thiếu thông tin tốt hơn. Nếu dữ liệu lệch, giá trị phổ biến có thể có số dòng lớn gấp nhiều lần mức trung bình và giá trị hiếm có thể ít hơn rất nhiều.

## 3. Biểu đồ phân bố (histogram)

### 3.1. Histogram mô tả điều gì?

Histogram tóm tắt phân bố của một cột bằng các khoảng giá trị hoặc các nhóm giá trị. Thay vì lưu tần suất của mọi giá trị trong một bảng rất lớn, hệ quản trị lưu một số điểm biên, số dòng hoặc tần suất tích lũy để bộ tối ưu ước lượng điều kiện bằng, điều kiện khoảng và một số biểu thức lọc.

Ví dụ, với cột `amount`, histogram có thể cho biết phần lớn đơn hàng nằm trong khoảng giá trị thấp, một phần nhỏ nằm trong khoảng trung bình và rất ít đơn hàng có giá trị cực lớn. Khi truy vấn yêu cầu `amount > 100000`, bộ tối ưu có thể dựa vào histogram để dự đoán tỷ lệ dòng thỏa điều kiện thay vì giả định mọi giá trị phân bố đều.

Histogram là bản tóm tắt thống kê tại thời điểm thu thập, không phải bản sao đầy đủ của dữ liệu. Các khoảng và tần suất có thể được lấy từ mẫu; giá trị hiển thị có thể là biên bucket hoặc giá trị đại diện tùy thuật toán. Vì vậy, không nên diễn giải một bucket như thể mọi giá trị bên trong đều có cùng tần suất chính xác.

### 3.2. Một số kiểu histogram thường gặp

| Kiểu histogram | Cách chia dữ liệu | Điểm mạnh | Giới hạn cần lưu ý |
|---|---|---|---|
| Equal-width | Chia miền giá trị thành các khoảng có độ rộng gần bằng nhau | Dễ hình dung phạm vi số học | Nếu dữ liệu tập trung ở một vùng, số dòng giữa các bucket có thể rất khác nhau |
| Equal-height/equi-depth | Chia thành các bucket có số dòng gần bằng nhau | Thể hiện mật độ dữ liệu qua độ rộng bucket | Bucket có thể rất hẹp ở vùng dày và rất rộng ở vùng thưa |
| Frequency | Lưu tần suất của từng giá trị hoặc nhóm giá trị trong giới hạn thống kê | Phù hợp khi số giá trị phân biệt không quá lớn | Có thể tốn dung lượng nếu NDV rất cao |
| Top-N/MCV kết hợp histogram | Tách các giá trị phổ biến ra riêng, mô tả phần còn lại bằng bucket | Giữ được thông tin về các giá trị lệch nổi bật | Phần đuôi vẫn có thể được ước lượng gần đúng |

Đây là cách phân loại khái niệm. Mỗi hệ quản trị có thể dùng tên khác, kết hợp nhiều kỹ thuật hoặc xây dựng histogram theo thuật toán riêng. Một số hệ thống có histogram dạng singleton, height-balanced, hybrid hoặc dạng khác; không nên giả định mọi hệ thống đều có đúng các loại trong bảng.

### 3.3. Đọc bucket và tần suất tích lũy

Một histogram thường có các thông tin như biên dưới, biên trên, số dòng trong bucket, tần suất tích lũy hoặc độ phân biệt của bucket. Khi đọc, cần xác định rõ:

1. Bucket biểu diễn khoảng giá trị nào và biên có bao gồm giá trị đầu/cuối hay không.
2. Con số là số dòng trong bucket hay tần suất tích lũy đến biên đó.
3. Histogram có loại trừ các giá trị MCV được lưu riêng hay không.
4. Số liệu là thống kê chính xác hay ước lượng từ mẫu.
5. Histogram áp dụng cho toàn bảng, partition riêng hay một phạm vi dữ liệu khác.

Nếu histogram lưu tần suất tích lũy, có thể ước lượng số dòng trong một bucket bằng hiệu giữa tần suất tích lũy ở hai biên liên tiếp, tùy quy ước của hệ quản trị. Khi ước lượng điều kiện khoảng nằm bên trong bucket, bộ tối ưu có thể nội suy dựa trên giả định phân bố trong bucket. Nếu các giá trị tập trung ở một đầu bucket, nội suy đều có thể sai.

### 3.4. Histogram giúp ước lượng điều kiện khoảng

Giả sử cột `score` có 1.000.000 giá trị không NULL. Thống kê cho biết khoảng từ 0 đến 100 có 100.000 dòng, từ 100 đến 500 có 700.000 dòng, và từ 500 đến 1.000 có 200.000 dòng. Điều kiện `score >= 500` có thể được ước lượng dựa trên các bucket liên quan, cho kết quả gần 20% nếu biên bucket được xác định như ví dụ.

Nếu chỉ dùng min, max và NDV, bộ tối ưu có thể phải giả định các giá trị phân bố đều trong miền. Histogram cung cấp thêm hình dạng phân bố để cải thiện dự đoán. Tuy nhiên, nếu dữ liệu thay đổi nhanh sau lần thu thập thống kê, histogram có thể không còn phản ánh đúng hiện trạng.

## 4. Giá trị phổ biến (MCV) và giá trị hiếm

### 4.1. Vì sao cần lưu MCV riêng?

Một số giá trị xuất hiện nhiều bất thường so với phần còn lại. Nếu chỉ dùng NDV để chia đều số dòng, bộ tối ưu sẽ đánh giá thấp các giá trị phổ biến và đánh giá cao các giá trị hiếm. Danh sách MCV ghi nhận một số giá trị có tần suất nổi bật cùng tỷ lệ hoặc số dòng tương ứng.

Ví dụ, bảng `orders` có 1.000.000 dòng với phân bố trạng thái:

| Giá trị `status` | Số dòng | Tỷ lệ |
|---|---:|---:|
| `COMPLETED` | 850.000 | 85% |
| `CANCELLED` | 100.000 | 10% |
| `PENDING` | 40.000 | 4% |
| `REVIEW` | 10.000 | 1% |

Nếu chỉ biết có bốn giá trị phân biệt và giả định đồng đều, bộ tối ưu có thể ước lượng mỗi giá trị có 250.000 dòng. Dự đoán này thấp hơn nhiều so với `COMPLETED` thực tế và cao hơn nhiều so với `REVIEW`. MCV giúp lưu riêng các tần suất nổi bật, nhờ đó ước lượng điều kiện bằng chính xác hơn.

### 4.2. Ước lượng giá trị phổ biến và phần còn lại

Về mặt khái niệm, khi điều kiện bằng khớp một giá trị có trong MCV, bộ tối ưu có thể dùng tần suất đã lưu cho giá trị đó. Với giá trị không nằm trong MCV, bộ tối ưu có thể ước lượng từ phần dòng còn lại và số giá trị phân biệt còn lại.

Một mô hình minh họa đơn giản:

\[
\text{Rows for non-MCV value} \approx
\frac{\text{rows not represented by MCV}}{\text{NDV not represented by MCV}}
\]

Đây không phải công thức bắt buộc của mọi hệ quản trị. Các bộ tối ưu thực tế có thể hiệu chỉnh theo NULL, tần suất MCV, bucket, lấy mẫu và các thống kê bổ sung.

Điều quan trọng là nhận ra hai trường hợp có thể cần kế hoạch khác nhau:

- `WHERE status = 'COMPLETED'` trả về phần lớn bảng. Quét tuần tự hoặc một kế hoạch xử lý theo lô có thể hiệu quả.
- `WHERE status = 'REVIEW'` chỉ trả về một tỷ lệ nhỏ. Chỉ mục có thể giảm lượng dữ liệu phải đọc nếu cấu trúc truy vấn và cách lưu trữ phù hợp.

Một chỉ mục trên cột có ít giá trị phân biệt không phải lúc nào cũng vô ích. Nếu một giá trị hiếm và truy vấn thường xuyên tìm đúng giá trị đó, chỉ mục vẫn có thể hữu ích. Ngược lại, giá trị phổ biến có thể khiến truy cập chỉ mục phải đọc quá nhiều dòng và trang dữ liệu.

### 4.3. Giá trị phổ biến thay đổi theo thời gian

MCV có thể thay đổi khi quy mô dữ liệu tăng, trạng thái nghiệp vụ thay đổi hoặc dữ liệu được nạp theo đợt. Ví dụ, trong một chiến dịch, trạng thái `PENDING` có thể tăng từ 4% lên 40%. Thống kê cũ tiếp tục dự đoán 4% và khiến kế hoạch không còn phù hợp.

Vì MCV thường chỉ lưu một số lượng giới hạn giá trị, một giá trị mới nổi lên có thể chưa được ghi nhận cho đến khi thống kê được cập nhật hoặc mức chi tiết thống kê được điều chỉnh. Hãy xem tần suất thực tế của các giá trị quan trọng khi nghi ngờ thống kê đã lỗi thời.

## 5. Dữ liệu lệch và ảnh hưởng đến kế hoạch thực thi

### 5.1. Sai lệch cardinality ở điều kiện lọc

Giả sử bộ tối ưu dự đoán `tenant_id = 42` trả về 1.000 dòng nhưng thực tế trả về 300.000 dòng. Kế hoạch dùng nested loop và tra cứu chỉ mục nhiều lần có thể trở nên đắt khi phải xử lý số dòng lớn hơn dự kiến. Nếu bộ tối ưu dự đoán quá cao cho một tenant hiếm, nó có thể chọn quét bảng dù một index seek phù hợp hơn.

Khi thấy estimated rows và actual rows khác xa, hãy xác định sai lệch bắt đầu tại điều kiện lọc nào. Kiểm tra histogram, MCV, NDV, tỷ lệ NULL, thống kê có còn mới không và giá trị tham số thực tế có phải giá trị phổ biến hay không.

### 5.2. Dữ liệu lệch trong phép nối

Độ lệch trên khóa nối có thể làm số dòng kết quả tăng rất lớn. Một mô hình ước lượng join đơn giản thường dựa vào số dòng của hai đầu vào và NDV của khóa nối, với giả định phân bố tương đối đồng đều. Khi một khóa xuất hiện rất nhiều ở cả hai phía, giả định đó có thể sai nghiêm trọng.

Ví dụ, một giá trị khóa `customer_id = 7` xuất hiện 20.000 lần ở bảng A và 5.000 lần ở bảng B. Nếu phép nối ghép mọi dòng có cùng khóa, riêng giá trị này có thể tạo:

\[
20.000 \times 5.000 = 100.000.000\text{ cặp dòng}
\]

Đây là hiệu ứng nhiều-nhiều do dữ liệu thực tế. Bộ tối ưu cần biết tần suất của các khóa lệch để dự đoán quy mô phép nối. MCV trên hai cột nối, thống kê đa cột hoặc thông tin phân bố khác có thể giúp cải thiện dự đoán, tùy khả năng của hệ quản trị.

Không phải mọi join có đầu ra lớn đều là lỗi. Trước tiên hãy xác nhận ngữ nghĩa truy vấn và quan hệ dữ liệu: khóa có duy nhất không, có cần toàn bộ tổ hợp không, có thể lọc trước khi nối không, và có thể tổng hợp hoặc loại trùng trước khi nối mà vẫn giữ nguyên kết quả không.

### 5.3. Skew trong xử lý song song và phân vùng

Trong hệ thống xử lý song song, dữ liệu thường được chia theo partition key hoặc hash key. Nếu một giá trị phổ biến tập trung vào một partition hoặc một worker, phần đó có thể xử lý lâu hơn nhiều so với các phần còn lại. CPU của một worker có thể bão hòa trong khi các worker khác nhàn rỗi; thời gian hoàn tất toàn truy vấn bị quyết định bởi nhánh chậm nhất.

Độ lệch cũng ảnh hưởng đến hash join, hash aggregate và phân phối dữ liệu giữa các node. Một vài bucket hash chứa quá nhiều dòng có thể gây áp lực bộ nhớ hoặc spill. Vì vậy, khi kế hoạch có thời gian thực tế bất thường, hãy xem phân bố theo partition, worker, khóa nối và số dòng xử lý tại từng nhánh nếu hệ quản trị cung cấp.

## 6. Giới hạn của histogram một cột

### 6.1. Tương quan giữa các cột

Histogram trên từng cột mô tả phân bố biên (marginal distribution), nhưng không nhất thiết mô tả được quan hệ giữa nhiều cột. Ví dụ, `country = 'VN'` và `currency = 'VND'` có thể xuất hiện cùng nhau gần như luôn luôn. Nếu bộ tối ưu giả định hai điều kiện độc lập, nó có thể nhân độ chọn lọc của từng điều kiện và dự đoán số dòng thấp hơn thực tế.

Một ví dụ khác là `status` và `closed_at`: bản ghi có `status = 'CLOSED'` thường có `closed_at` khác NULL, trong khi bản ghi `OPEN` thường có `closed_at` là NULL. Histogram riêng cho từng cột không đủ để mô tả đầy đủ quan hệ này.

Một số hệ quản trị hỗ trợ thống kê đa cột hoặc thống kê mở rộng như:

- **NDV đa cột:** ước lượng số tổ hợp giá trị phân biệt của nhiều cột.
- **Thống kê phụ thuộc (dependencies):** mô tả mức độ một cột phụ thuộc vào cột khác.
- **MCV đa cột:** lưu các tổ hợp giá trị thường xuất hiện cùng nhau.

Khả năng hỗ trợ và cách khai báo khác nhau theo hệ quản trị. Nếu sai lệch chỉ xuất hiện khi kết hợp nhiều điều kiện, hãy điều tra tương quan trước khi tăng mức chi tiết histogram của từng cột riêng lẻ.

### 6.2. Phân bố thay đổi theo partition

Một bảng partition có thể có phân bố khác nhau giữa các partition. Ví dụ, dữ liệu của tháng hiện tại có tỷ lệ `PENDING` cao, trong khi các tháng cũ chủ yếu là `COMPLETED`. Thống kê toàn cục có thể làm mờ khác biệt của từng partition; thống kê cục bộ lại có thể không đủ nếu truy vấn thường truy cập nhiều partition.

Hãy kiểm tra hệ quản trị sử dụng thống kê toàn cục, thống kê partition hay kết hợp cả hai. Nếu truy vấn có partition pruning, số liệu thống kê áp dụng cho các partition được chọn có thể ảnh hưởng trực tiếp đến ước lượng. Cập nhật thống kê cần tính đến quy trình nạp dữ liệu và cách hệ thống tổng hợp thống kê phân vùng.

### 6.3. Giá trị ngoài phạm vi thống kê

Histogram được xây dựng từ dữ liệu quan sát tại thời điểm thu thập. Nếu truy vấn tìm giá trị mới hơn giá trị lớn nhất đã ghi nhận, hoặc dữ liệu mới được nạp vào một khoảng chưa có trong histogram, bộ tối ưu phải dùng một quy tắc ước lượng ngoài phạm vi (out-of-range estimation). Quy tắc này khác nhau giữa các hệ quản trị và có thể không chính xác khi dữ liệu mới tăng nhanh.

Đây là vấn đề thường gặp ở cột thời gian tăng liên tục như `created_at` hoặc `event_time`. Thống kê được cập nhật quá thưa có thể khiến truy vấn lấy dữ liệu “mới nhất” ước lượng sai. Hãy xem min/max, thời điểm cập nhật thống kê và lượng dữ liệu mới phát sinh kể từ lần thu thập gần nhất.

## 7. Vì sao thống kê có thể không phản ánh dữ liệu hiện tại?

### 7.1. Thống kê lỗi thời

Sau một đợt nạp dữ liệu lớn, xóa hàng loạt hoặc thay đổi trạng thái theo nghiệp vụ, histogram và MCV có thể không còn đại diện cho phân bố hiện tại. Một số hệ quản trị tự động cập nhật thống kê khi đạt ngưỡng thay đổi; ngưỡng, lịch chạy và phạm vi cập nhật phụ thuộc cấu hình.

Không nên chỉ dựa vào ngày cập nhật. Một thống kê mới vẫn có thể không phù hợp nếu lấy mẫu quá nhỏ, bỏ qua partition quan trọng hoặc không mô tả tương quan cần thiết. Ngược lại, thống kê cũ chưa chắc sai nếu dữ liệu gần như không đổi.

### 7.2. Lấy mẫu và sai số

Để giảm chi phí thu thập, hệ quản trị có thể lấy mẫu thay vì quét toàn bộ bảng. Lấy mẫu giúp tiết kiệm I/O và thời gian, nhưng có thể bỏ sót giá trị hiếm hoặc ước lượng sai tần suất của giá trị phổ biến, đặc biệt khi dữ liệu có độ lệch cao hoặc mẫu không đại diện.

Tăng mức chi tiết thống kê hoặc kích thước mẫu có thể cải thiện histogram/MCV, nhưng cũng làm tăng chi phí cập nhật thống kê và dung lượng metadata. Hãy điều chỉnh có mục tiêu cho các cột quan trọng, sau đó đo xem sai lệch ước lượng có thực sự giảm hay không.

### 7.3. Thống kê theo cột và biểu thức

Nếu truy vấn lọc theo biểu thức, phép ép kiểu hoặc hàm trên cột, thống kê của cột gốc có thể không đủ để ước lượng kết quả. Ví dụ, `WHERE LOWER(email) = ...` không nhất thiết được ước lượng tốt chỉ nhờ histogram của `email` ở dạng gốc. Một số hệ quản trị hỗ trợ thống kê biểu thức hoặc cột tính toán; cách dùng tùy nền tảng.

Hãy kiểm tra kiểu dữ liệu của tham số, phép chuyển kiểu ngầm định, collation, hàm được áp dụng và khả năng dùng thống kê/ chỉ mục trên biểu thức tương ứng.

## 8. Tham số truy vấn và giá trị phổ biến

Cùng một câu SQL có thể nhận các giá trị tham số có tần suất rất khác nhau. Một truy vấn `WHERE tenant_id = @tenant` có thể chạy cho tenant chiếm 40% bảng và tenant chỉ chiếm 0,001% bảng. Một kế hoạch được tối ưu cho giá trị phổ biến có thể không phù hợp với giá trị hiếm, và ngược lại.

Một số hệ quản trị có cơ chế sniffing/peeking tham số khi biên dịch kế hoạch; một số có thể lưu kế hoạch dùng lại; một số hỗ trợ kế hoạch thích ứng hoặc nhiều biến thể kế hoạch theo dải tham số. Cách xử lý cụ thể phụ thuộc hệ thống.

Khi hiệu năng thay đổi theo tham số:

1. Ghi lại giá trị tham số của lần chạy nhanh và lần chạy chậm.
2. Đối chiếu tần suất của các giá trị đó với MCV/histogram.
3. So sánh estimated rows, actual rows và kế hoạch được chọn.
4. Kiểm tra kế hoạch có được dùng lại từ lần biên dịch trước không.
5. Đánh giá chiến lược phù hợp: kế hoạch chuyên biệt, nhiều biến thể kế hoạch, truy vấn tách nhánh hoặc biện pháp tối ưu theo nền tảng.

Không nên ép một kế hoạch cố định chỉ để cải thiện một giá trị tham số nếu điều đó làm các giá trị khác suy giảm. Mục tiêu là xử lý được dải phân bố tham số trong tải thực tế.

## 9. Quy trình điều tra histogram, MCV và dữ liệu lệch

Khi execution plan cho thấy estimated rows khác xa actual rows, có thể làm theo trình tự sau:

1. **Xác định điểm sai lệch đầu tiên.** Đọc kế hoạch từ các nhánh đầu vào đi lên; tìm điều kiện lọc hoặc phép nối đầu tiên có số hàng ước lượng khác xa thực tế.
2. **Xác định đúng dữ liệu và tham số.** Ghi nhận bảng, partition, cột, biểu thức, kiểu dữ liệu và giá trị tham số của lần chạy.
3. **Kiểm tra thống kê cơ bản.** Xem số dòng, NDV, tỷ lệ NULL, min/max, thời điểm cập nhật và phương pháp lấy mẫu nếu công cụ cung cấp.
4. **Đọc histogram và MCV.** Xác định giá trị phổ biến có được ghi nhận không, tần suất của chúng có gần dữ liệu hiện tại không, và điều kiện truy vấn nằm ở bucket nào.
5. **Kiểm tra độ lệch.** So sánh tần suất của giá trị phổ biến với mức trung bình; kiểm tra phân bố theo partition, tenant hoặc khóa nối khi phù hợp.
6. **Kiểm tra tương quan.** Nếu nhiều điều kiện cùng xuất hiện, xem xét thống kê đa cột hoặc phụ thuộc giữa các cột. Không giả định các điều kiện độc lập nếu nghiệp vụ cho thấy chúng liên hệ.
7. **Kiểm tra tác động của tham số.** So sánh giá trị phổ biến và hiếm, kế hoạch được biên dịch và kế hoạch được tái sử dụng.
8. **Chọn điều chỉnh phù hợp.** Có thể cập nhật thống kê, tăng chi tiết thống kê có mục tiêu, bổ sung thống kê đa cột/biểu thức, điều chỉnh truy vấn hoặc xem xét chỉ mục khi có bằng chứng.
9. **Đo lại.** Thu thập lại estimated rows và actual rows trong cùng điều kiện; kiểm tra thời gian, logical/physical reads, CPU, I/O tạm và kết quả truy vấn.

Ví dụ bảng ghi nhận trước/sau:

| Chỉ số tại điều kiện `tenant_id = 42` | Trước | Sau cập nhật thống kê phù hợp |
|---|---:|---:|
| Tổng số dòng bảng | 1.000.000 | 1.000.000 |
| Số dòng thực tế của tenant | 300.000 | 300.000 |
| Số dòng ước lượng | 1.000 | 280.000 |
| Sai lệch ước lượng | 300 lần | gần 1,07 lần |
| Thời gian thực tế | 1.200 ms | 430 ms |

Đây là số liệu minh họa. Việc ước lượng chính xác hơn không bảo đảm thời gian luôn giảm; bộ tối ưu còn phải chọn được kế hoạch phù hợp và môi trường thực thi phải tương đương. Sau thay đổi, hãy kiểm tra nhiều giá trị tham số và các truy vấn khác dùng cùng bảng hoặc chỉ mục.

## 10. Những lỗi thường gặp khi diễn giải thống kê

- **Giả định mọi giá trị có tần suất bằng nhau:** NDV chỉ cho biết số giá trị phân biệt; nó không chứng minh phân bố đồng đều.
- **Chỉ xem histogram mà bỏ qua MCV:** một số giá trị rất phổ biến có thể được lưu riêng và không được mô tả đầy đủ bằng bucket.
- **Coi bucket là phân bố chính xác:** histogram là bản tóm tắt, có thể dựa trên mẫu và giả định nội suy.
- **Nhầm thống kê một cột với thống kê nhiều cột:** hai histogram riêng lẻ không mô tả đầy đủ tương quan giữa các điều kiện.
- **Chỉ cập nhật thống kê toàn bảng:** dữ liệu partition hoặc tenant có thể có phân bố riêng cần được xem xét.
- **Bỏ qua giá trị mới ngoài phạm vi:** cột thời gian tăng liên tục có thể có nhiều dữ liệu mới hơn thống kê hiện có.
- **Tăng độ chi tiết thống kê cho mọi cột:** điều này có chi phí thu thập và lưu trữ; nên ưu tiên cột ảnh hưởng đến truy vấn quan trọng.
- **Ép một kế hoạch cho mọi tham số:** giá trị phổ biến và hiếm có thể cần cách truy cập khác nhau.
- **Đổ lỗi cho chỉ mục trước khi kiểm tra cardinality:** sai lệch thống kê có thể khiến bộ tối ưu chọn sai kế hoạch dù chỉ mục hiện có vẫn phù hợp.
- **Đánh giá bằng một lần chạy:** cache, tải đồng thời, tham số và dữ liệu thay đổi có thể làm kết quả dao động.

## 11. Bài tập tự kiểm tra

**Bài 1.** Một bảng có 1.000.000 dòng và cột `status` có bốn giá trị. Một giá trị chiếm 85% số dòng, ba giá trị còn lại chia nhau 15%. Nếu bộ tối ưu giả định phân bố đều, nó ước lượng mỗi giá trị có bao nhiêu dòng? Sai lệch với giá trị phổ biến là bao nhiêu lần?

*Gợi ý:* Ước lượng đều là 250.000 dòng mỗi giá trị. Giá trị phổ biến có 850.000 dòng, tức gấp 3,4 lần ước lượng.

**Bài 2.** Histogram cho biết một bucket có 200.000 dòng. Một điều kiện khoảng chỉ lấy một phần nhỏ của bucket. Vì sao phép nội suy đều có thể sai?

*Gợi ý:* Các giá trị có thể tập trung ở một đầu bucket; số dòng không nhất thiết phân bố đều theo độ rộng số học. Hãy xem kiểu histogram, biên bucket và dữ liệu thực tế.

**Bài 3.** Hai cột `country` và `currency` có tương quan mạnh. Mỗi histogram riêng lẻ có vẻ hợp lý nhưng truy vấn lọc đồng thời cả hai cột bị ước lượng thấp. Bạn nên điều tra gì?

*Gợi ý:* Kiểm tra giả định độc lập, phân bố tổ hợp giá trị và khả năng dùng thống kê đa cột, dependency hoặc MCV đa cột của hệ quản trị.

**Bài 4.** Một truy vấn cùng câu SQL chạy nhanh với tenant nhỏ nhưng chậm với tenant lớn. Cần thu thập thông tin nào để xác định nguyên nhân?

*Gợi ý:* Ghi lại tham số, tần suất MCV, estimated/actual rows, kế hoạch được biên dịch và tái sử dụng, số lần đọc, thời gian và mức tải khi chạy.

## 12. Ghi nhớ khi tối ưu

Histogram mô tả hình dạng phân bố qua các khoảng giá trị; MCV lưu tần suất của một số giá trị nổi bật; NDV và tỷ lệ NULL bổ sung thông tin cho ước lượng điều kiện lọc. Các thống kê này giúp bộ tối ưu dự đoán số hàng và chọn cách truy cập dữ liệu phù hợp hơn, đặc biệt khi dữ liệu lệch.

Khi một truy vấn có ước lượng sai, hãy tìm điểm sai lệch đầu tiên, kiểm tra MCV và bucket liên quan, xem dữ liệu có tương quan hoặc lệch theo partition/khóa nối không, rồi đánh giá độ mới và chất lượng lấy mẫu của thống kê. Điều chỉnh thống kê cần có mục tiêu và được kiểm chứng bằng kế hoạch thực tế, thời gian, I/O và kết quả truy vấn. Cách làm này giúp phân biệt lỗi ước lượng với nút thắt thực thi và chọn biện pháp tối ưu dựa trên dữ liệu.
