# Lựa chọn hiệu năng volume theo IOPS và throughput

## Mục tiêu bài học

Một volume còn nhiều dung lượng trống vẫn có thể không đáp ứng được tốc độ truy cập của ứng dụng. Ngược lại, cấp thêm hiệu năng cho volume chưa chắc làm ứng dụng nhanh hơn nếu giới hạn nằm ở Compute, attachment, filesystem hoặc cơ sở dữ liệu.

Bài học thuộc chương **Block Volume và Boot Volume** của module **CLOUD_PROVIDERS_ORACLE**. Trọng tâm là chọn cấu hình lưu trữ OCI dựa trên workload, đặt nó trong bối cảnh giám sát, giới hạn hạ tầng, chi phí và khả năng duy trì dịch vụ.

Sau bài này, bạn có thể:

- Phân biệt dung lượng, IOPS, throughput và latency.
- Tính quan hệ giữa số thao tác I/O, kích thước I/O và lượng dữ liệu truyền.
- Giải thích vai trò của mức hiệu năng volume và VPU/GB trong OCI.
- Nhận diện giới hạn phía volume, instance và đường attachment trước khi điều chỉnh.
- Thiết kế phép đo đại diện cho workload thay vì chỉ tìm một con số benchmark lớn.
- Đưa ra quyết định tăng, giảm hoặc giữ cấu hình với bằng chứng và điều kiện chấp nhận rõ ràng.

Các mức hiệu năng, phạm vi VPU/GB, giới hạn và khả năng hỗ trợ có thể khác theo tài nguyên, shape và cấu hình. Bài không dùng một bảng số liệu dịch vụ cố định làm cam kết; khi triển khai, phải lấy thông số của đúng môi trường OCI đích.

## 1. Bốn đại lượng cần đọc cùng nhau

| Đại lượng | Ý nghĩa | Đơn vị thường gặp | Không thể kết luận chỉ từ đại lượng này |
| --- | --- | --- | --- |
| Dung lượng | Lượng dữ liệu có thể lưu | GB, GiB, TB, TiB | Volume có đủ nhanh không |
| IOPS | Số thao tác I/O hoàn thành mỗi giây | operation/second | Mỗi thao tác lớn bao nhiêu, mất bao lâu |
| Throughput | Lượng dữ liệu truyền trong một giây | MB/s, MiB/s | Tốc độ xử lý giao dịch nhỏ hoặc độ trễ đuôi |
| Latency | Thời gian hoàn thành một thao tác | ms, microsecond | Toàn hệ thống có đủ năng lực khi nhiều tác vụ cùng chạy không |

Một ứng dụng đọc nhiều khối nhỏ ngẫu nhiên có thể quan tâm mạnh đến IOPS và latency. Một tác vụ đọc file lớn liên tục có thể quan tâm nhiều đến throughput. Cơ sở dữ liệu thường có nhiều kiểu I/O cùng tồn tại, nên cần phân tích từng nhóm thao tác.

Với Boot Volume, hệ điều hành, log và ứng dụng có thể cùng tạo tải. Với Block Volume dữ liệu, loại workload và cách truy cập quyết định nhu cầu. Không mặc định một boot volume không bao giờ cần hiệu năng cao, hoặc một data volume luôn phải chọn mức cao nhất.

### 1.1. Thống nhất đơn vị trước khi tính

Trong bài:

```text
1 KiB = 1.024 byte
1 MiB = 1.024 KiB
1 GiB = 1.024 MiB

1 MB = 1.000.000 byte
```

MiB/s và MB/s không phải cùng một đơn vị. Khi đối chiếu Console, tài liệu dịch vụ và công cụ trong hệ điều hành, cần đọc định nghĩa đơn vị của từng nguồn. Không đổi nhãn từ MB/s sang MiB/s mà giữ nguyên số rồi so sánh như thể chúng bằng nhau.

## 2. Quan hệ giữa IOPS và throughput

### 2.1. Khi kích thước I/O tương đối đồng nhất

Một ước lượng cơ bản:

```text
Throughput = IOPS x kích thước trung bình mỗi I/O
```

Ví dụ với I/O 8 KiB:

```text
20.000 IOPS x 8 KiB
  = 160.000 KiB/s
  = 156,25 MiB/s
```

Nếu giữ 20.000 IOPS nhưng tăng kích thước I/O lên 32 KiB:

```text
20.000 IOPS x 32 KiB
  = 640.000 KiB/s
  = 625 MiB/s
```

Để đạt cùng số IOPS với I/O lớn hơn, đường lưu trữ phải cung cấp throughput lớn hơn. Một giới hạn throughput có thể làm số IOPS quan sát được thấp hơn mức IOPS danh nghĩa.

### 2.2. Hai workload có thể cần cấu hình khác nhau

| Workload minh họa | Kích thước I/O | Mục tiêu | Throughput/IOPS tương ứng theo phép tính đơn giản |
| --- | --- | --- | --- |
| Truy cập dữ liệu nhỏ | 8 KiB | 20.000 IOPS | 156,25 MiB/s |
| Batch đọc file lớn | 1 MiB | 600 MiB/s | Khoảng 600 IOPS |

Chỉ nhìn con số 20.000 và 600 có thể khiến người đọc nghĩ workload đầu “nặng hơn”. Thực tế workload thứ hai yêu cầu lượng dữ liệu truyền cao hơn nhiều. Cả hai vẫn có thể có yêu cầu latency và tính bền vững khác nhau.

### 2.3. Workload hỗn hợp cần cộng theo từng nhóm

Giả sử trong cùng một giây, ứng dụng thực hiện:

- 8.000 I/O, mỗi I/O 8 KiB.
- 2.000 I/O, mỗi I/O 256 KiB.

Ta có:

```text
Tổng IOPS = 8.000 + 2.000 = 10.000

Nhóm nhỏ: 8.000 x 8 KiB = 62,5 MiB/s
Nhóm lớn: 2.000 x 256 KiB = 500 MiB/s

Tổng throughput = 562,5 MiB/s
```

Nếu mặc định mọi I/O đều 8 KiB, bạn sẽ đánh giá thiếu rất nhiều throughput. Cũng cần biết tỷ lệ đọc/ghi, truy cập tuần tự/ngẫu nhiên và mức đồng thời thay vì chỉ có một kích thước trung bình.

Các phép tính này mô tả lượng công việc I/O, chưa bao gồm mọi khác biệt do chia/gộp request, cache, metadata và overhead của các lớp phần mềm. Chúng giúp ước lượng và kiểm tra tính hợp lý, không thay thế phép đo thực tế.

## 3. Mức hiệu năng volume trong OCI

### 3.1. Hiệu năng được cấu hình ở lớp dịch vụ

OCI Block Volume cung cấp các lựa chọn hiệu năng cho volume, với các mức như Lower Cost, Balanced, Higher Performance và Ultra High Performance theo phạm vi hỗ trợ của dịch vụ. Khi xem cấu hình, cần kiểm tra mức nào áp dụng được cho loại volume, dung lượng và attachment đang dùng.

Một tham số quan trọng là **VPU/GB**, viết tắt của Volume Performance Units per GB. Đây là cách dịch vụ biểu diễn tài nguyên hiệu năng được cấp theo dung lượng volume; không phải số CPU của Compute instance.

Các yếu tố cần đọc cùng nhau:

- Dung lượng volume.
- Mức hiệu năng hoặc VPU/GB đã chọn.
- Mức IOPS và throughput theo dung lượng ở cấu hình đó.
- Giới hạn tuyệt đối của một volume.
- Điều kiện phía instance và attachment để khai thác hiệu năng.

Không suy ra tăng gấp đôi VPU/GB sẽ luôn làm giao dịch nhanh gấp đôi. Nếu workload không chạm giới hạn cũ hoặc bị nghẽn ở lớp khác, hiệu quả có thể rất nhỏ.

### 3.2. Dung lượng và giới hạn tuyệt đối đều có vai trò

Một mô hình khái niệm để đọc thông số:

```text
IOPS phía volume
  <= nhỏ hơn giữa:
       dung lượng x IOPS trên mỗi đơn vị dung lượng
       giới hạn IOPS của volume ở mức đã chọn

Throughput phía volume
  <= nhỏ hơn giữa:
       dung lượng x throughput trên mỗi đơn vị dung lượng
       giới hạn throughput của volume ở mức đã chọn
```

Đây là mô hình giải thích, không phải công thức API chung cho mọi loại volume. Dùng đúng thông số và đơn vị mà OCI công bố cho cấu hình cụ thể.

Mô hình cho thấy hai lỗi suy luận:

1. Volume nhỏ chọn mức hiệu năng cao chưa chắc đạt cùng giới hạn tổng như một volume lớn hơn.
2. Tăng dung lượng mãi không làm hiệu năng tăng mãi khi đã chạm trần.

Đừng tự tăng dung lượng chỉ để tìm thêm hiệu năng mà chưa so sánh các lựa chọn được hỗ trợ. Dung lượng tăng còn ảnh hưởng chi phí, quản lý filesystem và cách chuyển dữ liệu nếu sau này muốn thay thiết kế.

### 3.3. Điều kiện khai thác mức cao phải được đáp ứng

Một số cấu hình hiệu năng cao có yêu cầu về shape, attachment, multipath hoặc thành phần phần mềm trong instance. Không chỉ nhìn mức hiệu năng ở phía volume rồi giả định toàn đường I/O đã đủ điều kiện.

Cần xác nhận:

- Shape có hỗ trợ cấu hình dự kiến hay không.
- Kiểu attachment đang dùng có đáp ứng điều kiện không.
- Nếu có yêu cầu multipath, các đường cần thiết có thực sự hoạt động không.
- Driver, agent/plugin và hệ điều hành có đúng trạng thái được hỗ trợ không.
- Giới hạn tổng của instance có đủ cho các volume cùng hoạt động không.

Không thay đổi driver hoặc cấu hình multipath theo một ví dụ không khớp hệ điều hành. Đây là thay đổi trên đường lưu trữ, cần kế hoạch và hướng dẫn đúng môi trường.

## 4. Hiệu năng thực tế là kết quả của cả đường I/O

Có thể hình dung:

```text
Ứng dụng
  -> filesystem và cache của hệ điều hành
  -> lớp block, driver và attachment
  -> đường kết nối cùng giới hạn Compute
  -> dịch vụ volume
```

Khả năng quan sát được bị giới hạn bởi thành phần chậm hoặc có trần thấp nhất trong đường đi, và còn chịu đặc điểm workload.

### 4.1. Giới hạn phía Compute

Một instance có thể gắn nhiều volume, nhưng không thể coi tổng hiệu năng thực tế luôn bằng tổng mọi mức tối đa trên từng volume. Giới hạn lưu trữ và đường kết nối của shape có thể được chia sẻ giữa nhiều tải I/O.

Ví dụ giả định, không phải số liệu shape OCI:

```text
Volume A có thể cung cấp tới 400 MiB/s trong điều kiện phù hợp.
Volume B có thể cung cấp tới 400 MiB/s trong điều kiện phù hợp.
Đường I/O của cấu hình instance chỉ đạt tổng 600 MiB/s cho bài đo đó.

A và B cùng hoạt động không mặc định đạt 800 MiB/s.
```

Nếu cả hai cùng chia sẻ giới hạn phía instance, tăng mức hiệu năng A lên nữa chưa chắc có ích. Cần xác định đúng loại giới hạn; cũng không suy ra tốc độ NIC của ứng dụng chính là toàn bộ thông số lưu trữ của mọi shape và kiểu attachment.

### 4.2. Cache có thể làm kết quả đo dễ gây nhầm

Đọc dữ liệu đã có trong RAM thường không phát sinh cùng lượng I/O xuống volume như đọc dữ liệu chưa có trong cache. Một lần benchmark chạy nhanh không chứng minh volume có thể giữ tốc độ đó khi tập dữ liệu lớn hơn RAM.

Tương tự, ứng dụng ghi vào bộ đệm không đồng nghĩa dữ liệu đã được ghi bền vững theo yêu cầu giao dịch. Workload đòi hỏi đồng bộ ghi có thể có latency và throughput khác workload cho phép ghi đệm.

Kết quả thử cần ghi rõ:

- Dữ liệu nằm trong cache hay phải đọc từ lưu trữ.
- Cách sử dụng buffered I/O hoặc direct I/O.
- Yêu cầu đồng bộ và bảo đảm bền vững của thao tác ghi.
- Kích thước tập dữ liệu, thời gian thử và mức tải nền.

Không tắt bảo đảm ghi bền vững chỉ để có benchmark đẹp rồi dùng kết quả đó cho một workload giao dịch yêu cầu khác.

### 4.3. Mức song song và latency liên quan đến IOPS

Nếu ứng dụng chỉ gửi một I/O rồi chờ xong mới gửi tiếp, nó có thể không khai thác được năng lực xử lý đồng thời của volume.

Theo quan hệ hàng đợi trong trạng thái ổn định, có thể ước lượng:

```text
Số I/O đang xử lý/chờ trung bình
  xấp xỉ IOPS x latency trung bình tính bằng giây

20.000 IOPS x 0,001 giây = khoảng 20 I/O đồng thời
```

Đây là quan hệ giữa các đại lượng đo trên cùng phạm vi, không phải công thức bảo đảm đạt hiệu năng khi đặt queue depth bằng 20. Khi tăng mức đồng thời quá xa năng lực hệ thống, hàng đợi và latency có thể tăng mạnh mà throughput không tăng tương ứng.

Cần tìm mức đồng thời đáp ứng mục tiêu ứng dụng, không chỉ mức tạo ra IOPS cao nhất.

## 5. Bắt đầu bằng yêu cầu workload

### 5.1. Thu thập hồ sơ I/O

Trước khi chọn mức hiệu năng, ghi lại:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Mục tiêu ứng dụng | Độ trễ giao dịch, throughput nghiệp vụ hoặc thời gian hoàn thành batch là bao nhiêu? |
| Dữ liệu | Dung lượng hiện tại, tốc độ tăng và không gian cho log/file tạm là bao nhiêu? |
| Kích thước I/O | Chủ yếu nhỏ, lớn hay hỗn hợp? |
| Mẫu truy cập | Ngẫu nhiên, tuần tự, đọc nhiều, ghi nhiều hay thay đổi theo giai đoạn? |
| Mức đồng thời | Bao nhiêu tiến trình/luồng/tác vụ tạo I/O cùng lúc? |
| Tính bền vững | Có yêu cầu đồng bộ ghi hoặc thứ tự ghi chặt chẽ không? |
| Chu kỳ tải | Giờ cao điểm, backup, batch và bảo trì có trùng nhau không? |
| Khi có lỗi | Tải có dồn sang volume hoặc instance còn lại không? |

Ứng dụng Java truy cập cơ sở dữ liệu Oracle ở dịch vụ riêng không nhất thiết tạo nhiều I/O dữ liệu trên volume của máy ứng dụng. Nếu thời gian chậm nằm trong truy vấn DB từ xa, tăng hiệu năng Boot Volume của máy Java có thể không giải quyết vấn đề.

### 5.2. Đọc nhiều thời điểm, không chỉ trung bình ngày

Trung bình 24 giờ có thể che khuất một đợt tải vài phút gây lỗi hoặc vi phạm độ trễ. Cần xem các giai đoạn:

- Khởi động và nạp dữ liệu ban đầu.
- Tải bình thường.
- Đỉnh tải nghiệp vụ.
- Backup hoặc batch chạy đồng thời.
- Phục hồi sau khi một thành phần bị lỗi.

Khoảng dự phòng cần dựa vào biến động và thời gian điều chỉnh, không có một tỷ lệ cố định đúng cho mọi hệ thống. Nếu yêu cầu chịu tải khi một instance mất, phải đo tình huống đó thay vì chỉ cộng một tỷ lệ nhỏ vào trung bình.

## 6. Quy trình lựa chọn cấu hình

### Bước 1: Xác định mục tiêu có thể kiểm chứng

Ví dụ: “Hoàn thành batch trong 20 phút, không làm p95 API vượt mục tiêu trong thời gian chạy chung” cụ thể hơn “cần ổ đĩa nhanh”.

Gắn mục tiêu với dữ liệu thử nghiệm và phiên bản phần mềm. Nêu rõ kiểu ghi bền vững, mức đồng thời và các công việc nền đi kèm.

### Bước 2: Tính cả nhu cầu IOPS lẫn throughput

Dùng hồ sơ workload để ước lượng từng nhóm I/O rồi cộng hợp lý. Nếu workload cần 25.000 IOPS với khối 8 KiB:

```text
Throughput tương ứng
  = 25.000 x 8 / 1.024
  = 195,3125 MiB/s
```

Ứng viên phải đáp ứng cả hai yêu cầu trong điều kiện phù hợp, đồng thời giữ latency chấp nhận được. Mức IOPS đủ nhưng trần throughput thấp hơn nhu cầu vẫn không đáp ứng.

### Bước 3: Đối chiếu thông số OCI và đường attachment

Lấy thông số cho dung lượng, mức hiệu năng, loại volume, shape và attachment cụ thể. Kiểm tra giới hạn từng volume và tổng phía instance.

Đối chiếu thêm cấu hình trong hệ điều hành: thiết bị có đúng volume dự kiến, filesystem có mount đúng, và các thành phần đường I/O có hoạt động như thiết kế hay không.

### Bước 4: Đo ứng dụng cùng metric hạ tầng

Giữ điều kiện đo đủ nhất quán và thay đổi một yếu tố chính mỗi lần. Ghi lại thời gian, workload, cấu hình cũ/mới và cách xác định giai đoạn ổn định.

Một cấu hình chỉ được coi là tốt hơn nếu cải thiện mục tiêu cần thiết hoặc giữ mục tiêu với chi phí phù hợp hơn. IOPS tăng nhưng latency giao dịch xấu đi chưa phải kết quả thành công.

### Bước 5: Quyết định thay đổi và quan sát sau thay đổi

Các hướng xử lý có thể gồm:

- Tăng mức hiệu năng volume khi có bằng chứng volume đang là giới hạn.
- Điều chỉnh Compute hoặc attachment khi nút thắt ở đường phía instance.
- Tối ưu truy vấn, cách đọc/ghi hoặc mức đồng thời nếu ứng dụng tạo I/O không hiệu quả.
- Tách hoặc đổi lịch công việc nền đang cạnh tranh tài nguyên.
- Giữ nguyên cấu hình khi đã đáp ứng yêu cầu và chưa có bằng chứng cần thay đổi.

Khả năng điều chỉnh volume không miễn trừ việc theo dõi latency và lỗi khi áp dụng. Ghi điều kiện quay lại hoặc chuyển phương án nếu kết quả không đạt. Không coi thu nhỏ dung lượng là thao tác hoàn tác tự động khi đã tăng volume.

## 7. Ví dụ đọc kết quả và chọn hướng xử lý

### 7.1. Cơ sở dữ liệu tự quản trị có nhiều I/O nhỏ

Bối cảnh giả định: dữ liệu đặt trên Block Volume, nhu cầu cao điểm khoảng 25.000 IOPS với I/O 8 KiB. Mục tiêu độ trễ giao dịch được kiểm tra riêng.

Các câu hỏi:

1. Cấu hình volume có đủ IOPS và khoảng 195,31 MiB/s theo ước lượng không?
2. Instance và attachment có khai thác được mức đó không?
3. Hàng đợi I/O tăng cùng thời gian chậm hay ứng dụng đang chờ lock/CPU?
4. Ghi đồng bộ, log và dữ liệu có tạo các mẫu I/O khác nhau không?
5. Backup chạy chung có làm tăng tải vượt mức đã tính không?

Nếu metric phía volume gần giới hạn, hàng đợi và latency cùng tăng khi tải tăng, việc thử mức hiệu năng cao hơn có cơ sở. Nếu IOPS thấp nhưng giao dịch chờ khóa, tăng VPU/GB có thể không xử lý được nguyên nhân.

### 7.2. Batch đọc dữ liệu lớn

Một batch cần duy trì 600 MiB/s với I/O khoảng 1 MiB. Nhu cầu theo phép tính đơn giản là khoảng 600 IOPS, nhưng ứng viên vẫn phải đủ throughput và đường I/O phía instance.

Nếu chỉ so sánh “IOPS tối đa”, có thể chọn cấu hình trông dư thừa mà batch vẫn không đạt thời gian. Cần quan sát đọc tuần tự, cache, CPU giải nén/xử lý, đường truyền nguồn dữ liệu và các công việc cùng sử dụng volume.

### 7.3. Boot Volume chứa log của backend Java

Trong ngày bình thường, Boot Volume đáp ứng tốt. Khi ứng dụng gặp lỗi, tốc độ ghi log tăng, latency I/O và dung lượng sử dụng cùng tăng.

Trước khi tăng mức hiệu năng, kiểm tra:

- Log có đang lặp bất thường do một lỗi phần mềm không?
- Rotation và giới hạn dung lượng có hoạt động không?
- Cơ chế chuyển log tập trung có bị tắc không?
- Ứng dụng có dùng kiểu ghi đồng bộ không cần thiết cho loại log đó không?
- Có cần tách luồng I/O hoặc phân bổ tài nguyên khác theo yêu cầu vận hành không?

Tăng hiệu năng có thể giúp một phần, nhưng không thay thế việc xử lý log tăng không giới hạn hoặc lỗi gây ra nó.

### 7.4. Bảng kết quả giả định

Các số trong bảng chỉ để luyện cách chẩn đoán, không phải thông số của shape hoặc volume OCI cụ thể.

| Quan sát | Giả thuyết đáng kiểm tra | Thử nghiệm tiếp theo |
| --- | --- | --- |
| IOPS gần giới hạn đã xác nhận, latency tăng khi thêm tải | Volume có thể thiếu năng lực IOPS | Thử cấu hình phù hợp hơn, giữ workload và đường attachment nhất quán |
| IOPS chưa cao nhưng throughput gần giới hạn | I/O lớn đang chạm trần truyền dữ liệu | Đối chiếu giới hạn throughput thay vì chỉ tăng kỳ vọng IOPS |
| Nhiều volume cùng chậm ở một instance | Giới hạn chung phía Compute/attachment hoặc tải nền | Kiểm tra tổng I/O, shape và điều kiện kết nối |
| I/O thực xuống volume thấp, CPU ứng dụng cao | Tính toán hoặc phần mềm có thể là nút thắt | Profile CPU, truy vấn và mức đồng thời |
| Lần đọc thứ hai nhanh hơn rất nhiều | Cache có thể chi phối phép đo | Đo với điều kiện cache và tập dữ liệu được mô tả rõ |
| Tăng mức volume nhưng mục tiêu ứng dụng không đổi | Nút thắt khác hoặc phép đo chưa đủ đại diện | Đối chiếu các lớp, không tiếp tục tăng cấu hình một cách suy đoán |

## 8. Quan sát bằng Monitoring và hệ điều hành

### 8.1. Kết hợp nhiều lớp thông tin

Ở lớp OCI, quan sát các metric được dịch vụ cung cấp cho volume và tài nguyên liên quan, chẳng hạn thao tác đọc/ghi và lượng dữ liệu đọc/ghi theo định nghĩa của từng metric. Kiểm tra đúng compartment, resource, khoảng thời gian, đơn vị và phép tổng hợp.

Ở lớp hệ điều hành, xem thiết bị, filesystem, hàng đợi và độ trễ I/O. Ở lớp ứng dụng, xem latency, throughput nghiệp vụ, tỷ lệ lỗi và thời gian chờ.

Không cộng hay so sánh trực tiếp các số khác phạm vi đo. Hệ điều hành có thể chia/gộp I/O; cache có thể giữ lại thao tác chưa xuống volume; thời gian lấy mẫu giữa các nguồn có thể khác nhau.

Một ví dụ về cách chuẩn hóa số liệu, không phải biểu thức Monitoring cụ thể:

```text
Trong 60 giây quan sát:
  120.000 thao tác hoàn thành
  937,5 MiB dữ liệu truyền

IOPS trung bình = 120.000 / 60 = 2.000
Throughput trung bình = 937,5 / 60 = 15,625 MiB/s
Kích thước trung bình = 8 KiB mỗi thao tác
```

Trước khi chia cho thời gian, phải biết nguồn trả về tổng số, tốc độ đã tính sẵn hay bộ đếm tích lũy. Không chia một giá trị đã là operation/second thêm lần nữa.

### 8.2. Lệnh đọc trong Linux

Nếu đã có máy Linux thử nghiệm được phép sử dụng, có thể quan sát bằng các lệnh sau. Công cụ `iostat` thường thuộc gói `sysstat` và cần được cài sẵn.

```bash
# Xem thiết bị và filesystem đang sử dụng
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT

# Thay bằng đường dẫn dữ liệu thực sự tồn tại trên máy
findmnt -T /srv/app-data

# Quan sát I/O thiết bị theo các khoảng một giây
iostat -xz 1 10
```

Khi đọc `iostat`:

- Kiểm tra đơn vị và ý nghĩa cột của phiên bản công cụ đang dùng.
- Mẫu đầu có thể phản ánh trung bình từ khi máy khởi động; các mẫu sau phản ánh khoảng lấy mẫu.
- `await` là độ trễ trung bình quan sát ở lớp thiết bị, bao gồm thời gian chờ theo cách công cụ đo; không coi đó là latency nội bộ thuần của dịch vụ volume.
- `%util` cao là tín hiệu để điều tra, không phải quy tắc kết luận mọi thiết bị nhiều hàng đợi đã hết toàn bộ năng lực.
- CPU `iowait` không phải phần trăm bận của một volume cụ thể.

Không tạo tải ghi thử lên volume đang chứa dữ liệu chỉ để tìm giới hạn. Nếu cần benchmark riêng, dùng môi trường và dữ liệu thử phù hợp, mô tả workload, điều kiện cache và bảo đảm ghi bền vững trước khi so kết quả.

## 9. Chi phí, IAM và tính sẵn sàng khi thay đổi hiệu năng

### 9.1. So sánh ở cùng mục tiêu phục vụ

Dung lượng và tài nguyên hiệu năng đều có thể ảnh hưởng chi phí lưu trữ. Chọn mức thấp nhất có thể nhìn thấy trong danh sách không đồng nghĩa chi phí tổng thể thấp nhất nếu batch kéo dài hoặc cần thêm Compute để hoàn thành công việc.

Ngược lại, mức cao nhất có thể tạo tài nguyên không được dùng đến. So sánh các phương án khi chúng cùng đáp ứng yêu cầu, rồi ghi chi phí và giới hạn vận hành của từng phương án dựa trên thông tin môi trường thực tế.

Đừng bỏ qua backup, các bản sao, volume còn giữ và tài nguyên Compute phục vụ cùng workload. Một lần tăng dung lượng để lấy hiệu năng có thể để lại chi phí kéo dài dù tải đã giảm.

### 9.2. Quyền thay đổi cần đúng phạm vi

Người quan sát metric và người thay cấu hình volume có thể cần các quyền khác nhau. Cấp quyền phù hợp theo compartment và trách nhiệm vận hành; không dùng quyền quản trị toàn tenancy làm mặc định chỉ để kiểm tra hiệu năng.

Việc hệ điều hành mount đúng volume cũng cần được xác nhận trước khi thay đổi tài nguyên trong OCI. Điều chỉnh nhầm volume sẽ không cải thiện workload dự kiến và làm sai đánh giá chi phí.

### 9.3. Hiệu năng cao không thay thế backup hoặc dự phòng

Tăng VPU/GB không tạo bản backup, không bảo vệ khỏi xóa nhầm và không làm một instance duy nhất tự có tính sẵn sàng cao.

Nếu hệ thống cần giữ mức dịch vụ khi mất một thành phần, đánh giá tải sau lỗi và phương án phục hồi. Khi dữ liệu nằm trên nhiều volume, cũng cần thiết kế tính nhất quán và phục hồi phù hợp; chia tải I/O không tự giải quyết hai yêu cầu này.

## 10. Phiếu lựa chọn và tự kiểm tra

Hoàn thành phiếu dưới đây trước khi đề xuất đổi mức hiệu năng:

| Nội dung | Bằng chứng cần ghi |
| --- | --- |
| Tài nguyên đích | Volume, attachment, instance, compartment và đường dẫn ứng dụng |
| Mục tiêu ứng dụng | Latency, throughput nghiệp vụ, tỷ lệ lỗi hoặc thời gian batch |
| Hồ sơ I/O | Kích thước, đọc/ghi, tuần tự/ngẫu nhiên, đồng thời, yêu cầu ghi bền vững |
| Nhu cầu định lượng | IOPS, throughput, dung lượng và mức tải cần chịu khi có lỗi |
| Cấu hình OCI | Dung lượng, mức hiệu năng/VPU, giới hạn và điều kiện được hỗ trợ |
| Giới hạn liên quan | Shape, tổng I/O nhiều volume, attachment và các phụ thuộc |
| Số liệu nền | Khoảng đo, metric, latency, hàng đợi, cache và tải nền |
| Thay đổi đề xuất | Tăng/giảm hiệu năng, thay đường I/O, tối ưu phần mềm hoặc giữ nguyên |
| Kết quả đo | Cùng workload, cùng bảo đảm dữ liệu, tác động đến mục tiêu ứng dụng |
| Vận hành | Chi phí dự kiến, quyền thực hiện, điều kiện theo dõi và phương án khi không đạt |

Tự kiểm tra:

1. Vì sao một volume có IOPS danh nghĩa cao vẫn có thể không đạt throughput của batch đọc file lớn?
2. Workload 20.000 IOPS với I/O 8 KiB cần throughput xấp xỉ bao nhiêu? Nếu I/O thành 32 KiB thì thay đổi thế nào?
3. VPU/GB có phải số CPU cấp cho instance không? Cần đọc thêm những giới hạn nào ngoài giá trị này?
4. Vì sao tăng dung lượng không bảo đảm hiệu năng tiếp tục tăng khi đã chạm giới hạn tuyệt đối?
5. Hai volume cùng gắn một instance có mặc nhiên đạt tổng mọi mức hiệu năng tối đa của chúng không?
6. Một benchmark đọc lần hai nhanh hơn lần đầu có thể đang đo yếu tố gì?
7. Vì sao throughput cao nhưng p99 giao dịch xấu hơn chưa phải kết quả thành công?
8. Nếu API Java chậm vì truy vấn DB từ xa, tăng hiệu năng Boot Volume cần bằng chứng gì để được xem là hợp lý?
9. Khi đọc Monitoring, vì sao phải xác định giá trị là tổng, tốc độ hay bộ đếm trước khi tính IOPS?
10. Bằng chứng nào sẽ khiến bạn giữ nguyên mức volume và chuyển sang điều tra attachment hoặc phần mềm?

Đầu ra của bài thực hành là một quyết định có số liệu: workload cần bao nhiêu IOPS và throughput, giới hạn nằm ở đâu, cấu hình nào đáp ứng mục tiêu, và điều gì đã được đo để xác nhận quyết định đó.
