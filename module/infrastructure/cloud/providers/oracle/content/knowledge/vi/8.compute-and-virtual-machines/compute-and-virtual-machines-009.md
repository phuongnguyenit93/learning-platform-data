# Autoscaling theo lịch và theo metric

## Mục tiêu bài học

Autoscaling là cơ chế tự động điều chỉnh tài nguyên theo chính sách đã định. Trong bối cảnh OCI Compute, bài này tập trung vào thay đổi số lượng instance của một **instance pool**: tăng số máy khi cần thêm năng lực xử lý và giảm số máy khi nhu cầu giảm.

Bài học thuộc chương **Compute và máy chủ ảo**, module **CLOUD_PROVIDERS_ORACLE**. Người học cần liên hệ autoscaling với IAM, VCN, Compute, giám sát, chi phí và khả năng chịu lỗi của toàn bộ hệ thống OCI.

Sau bài học, bạn có thể:

- Phân biệt autoscaling theo lịch và theo metric, chọn cơ chế theo đặc điểm tải.
- Giải thích quan hệ giữa instance configuration, instance pool, autoscaling policy và load balancer.
- Đặt giới hạn quy mô, ngưỡng tăng/giảm và thời gian ổn định dựa trên dữ liệu thử nghiệm.
- Đọc lịch bằng UTC, tính thời gian chuẩn bị máy và nhận diện sai lệch múi giờ.
- Lập kế hoạch kiểm thử scale-out, scale-in, thiếu capacity và metric bị gián đoạn.
- Đánh giá tác động lên cơ sở dữ liệu, dữ liệu ứng dụng, tính sẵn sàng và chi phí.

Các số liệu trong bài là giả định minh họa. Khả năng hỗ trợ shape, hệ điều hành, policy và giới hạn cụ thể phải được kiểm tra trong môi trường OCI triển khai. Các bảng chính sách là bản thiết kế, không phải schema để gửi trực tiếp vào API.

## 1. Autoscaling của instance pool làm gì?

### 1.1. Scale-out và scale-in

- **Scale-out**: tăng số instance để chia tải cho nhiều máy hơn.
- **Scale-in**: giảm số instance khi hệ thống có thể phục vụ bằng ít máy hơn.
- **Scale-up/scale-down**: tăng/giảm tài nguyên của từng máy, chẳng hạn CPU hoặc RAM; đây là thao tác khác với việc đổi kích thước instance pool.

Không nên hiểu “bật autoscaling” là OCI sẽ tự chọn shape, điều chỉnh JVM heap, tối ưu truy vấn và tăng công suất cơ sở dữ liệu. Chính sách scaling chỉ điều khiển phạm vi tài nguyên mà nó được cấu hình quản lý.

Ví dụ, một API Java đang có hai instance. Scale-out lên bốn instance tạo thêm hai nơi chạy ứng dụng. Nếu mọi request vẫn chờ một truy vấn chậm trên cùng cơ sở dữ liệu, việc thêm máy ứng dụng chưa chắc cải thiện độ trễ.

### 1.2. Các thành phần trong OCI

| Thành phần | Vai trò | Điều cần chuẩn bị |
| --- | --- | --- |
| Instance configuration | Mô tả cách tạo instance | Image, shape, cấu hình khởi tạo, mạng và các tham số liên quan |
| Instance pool | Quản lý một nhóm instance theo cấu hình và vị trí triển khai | Số lượng, placement, vòng đời và kết nối đến ứng dụng |
| Autoscaling configuration và policy | Quy định điều kiện hoặc thời điểm thay đổi quy mô | Loại policy, giới hạn, hành động và thời gian áp dụng |
| Monitoring và nguồn metric | Cung cấp tín hiệu hiệu năng cho policy theo metric | Agent/plugin phù hợp, dữ liệu đủ và đúng phạm vi |
| Load balancer, nếu ứng dụng cần | Phân phối request tới các backend đủ điều kiện | Liên kết với pool, backend set và health check phù hợp |
| IAM | Quy định ai được cấu hình và thao tác các tài nguyên | Policy tối thiểu cần thiết theo compartment và mô hình vận hành |

Instance mới phải có khả năng tự khởi tạo từ cấu hình đã lưu. Nếu mỗi lần tạo máy còn cần đăng nhập SSH để chép file hoặc sửa địa chỉ máy thủ công, quá trình scale-out chưa thực sự hoàn chỉnh.

Cũng không nên giả định đổi instance configuration sẽ tự nâng cấp toàn bộ máy đang chạy. Cần quản lý phiên bản cấu hình và kế hoạch thay thế instance hiện hữu riêng với chính sách thay đổi số lượng.

## 2. Hai cơ chế: theo lịch và theo metric

| Cơ chế | Tín hiệu quyết định | Phù hợp với | Hạn chế cần nhớ |
| --- | --- | --- | --- |
| Theo lịch | Thời điểm đã cấu hình | Giờ làm việc, tác vụ định kỳ, sự kiện biết trước | Không tự nhận ra mức tải thực tế ngoài dự báo |
| Theo metric | Chỉ số hiệu năng vượt điều kiện | Tải biến động và tài nguyên có quan hệ rõ với nhu cầu xử lý | Có độ trễ đo, đánh giá, cấp phát và khởi động |

Theo lịch có thể chuẩn bị trước đỉnh tải. Theo metric phản ứng khi hệ thống quan sát được điều kiện đã định. Cả hai đều cần thời gian để máy mới sẵn sàng và đều bị ràng buộc bởi quyền, cấu hình, limits/quota cùng capacity thực tế.

Không mặc định hai loại policy có thể đặt chung trong một autoscaling configuration hoặc cùng tự do điều khiển một pool. Trước khi thiết kế phối hợp, phải xác nhận các ràng buộc của OCI về loại policy và quan hệ với instance pool. Hai ví dụ trong bài được đánh giá độc lập; chúng không hướng dẫn gắn đồng thời hai bộ điều khiển vào cùng một pool.

## 3. Điều kiện để autoscaling tạo ra năng lực phục vụ thực

### 3.1. Ứng dụng phải chấp nhận việc thêm và mất instance

Ứng dụng mở rộng ngang thuận lợi khi request không phụ thuộc vào một máy cụ thể. Trạng thái quan trọng cần được quản lý ở nơi phù hợp, chẳng hạn cơ sở dữ liệu hoặc dịch vụ trạng thái dùng chung, với cơ chế đồng thời và phục hồi đã thiết kế.

Những ví dụ gây trở ngại cho scaling:

- Session chỉ lưu trong bộ nhớ của một instance.
- File người dùng vừa tải lên chỉ nằm trên ổ cục bộ của máy nhận request.
- Worker nhận việc nhưng không có cơ chế xác nhận, retry hoặc xử lý trùng.
- Scheduled job chạy trên mọi máy mới và cùng thực hiện một tác vụ đáng lẽ chỉ chạy một lần.
- Địa chỉ IP của instance được hardcode trong thành phần khác.

Sticky session không bảo vệ session khi máy bị loại bỏ hoặc gặp sự cố. Với worker, việc “nhận lại tác vụ” chỉ an toàn khi mô hình xử lý cho phép retry và kiểm soát tác dụng phụ.

### 3.2. Máy đã chạy chưa đồng nghĩa ứng dụng đã sẵn sàng

Một chuỗi scale-out điển hình:

```text
Policy yêu cầu tăng pool
  -> OCI cấp phát và khởi động instance
  -> Hệ điều hành, agent và bootstrap chạy
  -> Ứng dụng lấy cấu hình, khởi động và kết nối dịch vụ phụ thuộc
  -> Backend được đăng ký, health check xác nhận sẵn sàng
  -> Instance mới nhận request
```

Thời gian cần dự phòng là tổng các giai đoạn, không chỉ thời gian máy xuất hiện ở trạng thái chạy. Với Java, quá trình nạp ứng dụng, làm nóng JVM/JIT, tạo connection pool và nạp cache có thể ảnh hưởng thêm.

Health check nên phản ánh khả năng nhận request theo thiết kế. Một TCP port đã mở chưa chứng minh ứng dụng hoàn tất khởi tạo. Ngược lại, một kiểm tra quá nặng hoặc phụ thuộc vào mọi dịch vụ không thiết yếu cũng có thể loại backend không cần thiết.

### 3.3. Quyền và đường mạng phải hoạt động từ lúc bootstrap

Instance mới phải thực hiện được các thao tác cần thiết bằng danh tính và quyền đã cấp, thay vì dựa vào credential chép tay từ máy cũ. Phân biệt quyền của người cấu hình autoscaling với quyền runtime của ứng dụng trên instance.

Trong VCN, kiểm tra đường truy cập đến nguồn artifact, cấu hình, secrets và dịch vụ phụ thuộc. Instance ở private subnet không tự có đường ra Internet chỉ vì thuộc instance pool; cần thiết kế route cùng gateway hoặc đường truy cập riêng phù hợp với từng đích.

Tách quyền theo compartment và chức năng. Việc bật autoscaling không phải lý do để cấp quyền quản trị toàn tenancy cho người vận hành hoặc cho mọi instance.

## 4. Autoscaling theo metric

### 4.1. Chọn tín hiệu có quan hệ với năng lực xử lý

Với metric-based autoscaling của OCI Compute, các tín hiệu tiêu biểu là mức sử dụng CPU hoặc bộ nhớ trên instance pool theo khả năng được hỗ trợ. Không suy ra rằng mọi metric tùy chỉnh trong Monitoring đều có thể dùng trực tiếp làm trigger cho policy chuẩn.

Việc lựa chọn metric phải bắt đầu từ thử nghiệm workload:

| Hiện tượng | CPU có thể là tín hiệu tốt? | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Request cần tính toán và CPU tăng cùng throughput | Có thể | Khả năng phân tải và điểm bắt đầu tăng độ trễ |
| Request chủ yếu chờ cơ sở dữ liệu | Thường không đủ | Truy vấn, connection pool, giới hạn DB và độ trễ mạng |
| Bộ nhớ tăng theo số tác vụ đồng thời | Có thể cân nhắc memory | Bộ nhớ ngoài heap, GC và mức thực sự thu hồi sau tải |
| Worker chờ queue nhưng CPU không cao | Không nhất thiết | Queue depth/tuổi tác vụ như tín hiệu vận hành, khả năng policy hỗ trợ |
| Một instance nóng hơn các instance còn lại | Trung bình pool có thể che khuất vấn đề | Phân tải, session, tác vụ lệch và metric từng instance |

Nếu hệ thống cần scaling bằng queue depth hoặc tín hiệu nghiệp vụ, cần xác định giải pháp điều khiển có hỗ trợ thay vì gán một metric bất kỳ vào policy chuẩn. Đây là quyết định kiến trúc khác, không phải một thuộc tính mặc nhiên của metric-based autoscaling.

### 4.2. Xác nhận metric thực sự được thu thập

Với metric của Compute do agent cung cấp, kiểm tra Oracle Cloud Agent và plugin **Compute Instance Monitoring** theo image/hệ điều hành được hỗ trợ. Cần xác nhận dữ liệu xuất hiện cho các instance thực tế, không chỉ nhìn thấy trạng thái bật trong cấu hình.

Một preflight hữu ích:

1. Kiểm tra đúng instance pool và danh sách instance được quản lý.
2. Xác nhận metric CPU hoặc memory cần dùng đang có dữ liệu với timestamp mới.
3. Kiểm tra compartment, namespace và phạm vi tài nguyên khi quan sát Monitoring.
4. Đối chiếu thời điểm có metric với lúc bootstrap và tải thử.
5. Xác nhận quyền và đường liên lạc cần thiết để hệ thống giám sát hoạt động.

**Không có dữ liệu không đồng nghĩa mức sử dụng bằng 0.** Khi metric gián đoạn, phải điều tra nguồn dữ liệu và quan sát hành vi của policy theo cơ chế OCI hỗ trợ, thay vì kết luận workload đã hết tải.

### 4.3. Ngưỡng tăng và giảm nên có khoảng cách

Ví dụ thiết kế cho API CPU-bound:

| Tham số | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| Quy mô tối thiểu | 2 instance | Mức nền ban đầu, còn phải kiểm tra với yêu cầu chịu lỗi |
| Quy mô ban đầu | 2 instance | Kích thước khi bắt đầu bài thử |
| Quy mô tối đa | 8 instance | Chặn mở rộng vượt phạm vi đã dự trù |
| Điều kiện tăng | CPU của pool vượt 65% theo đánh giá của policy | Có dấu hiệu cần thêm năng lực CPU |
| Hành động tăng | Thêm 1 instance | Bước tăng ban đầu để thử nghiệm |
| Điều kiện giảm | CPU của pool dưới 30% theo đánh giá của policy | Có thể đang dư năng lực |
| Hành động giảm | Bớt 1 instance | Bước giảm ban đầu để thử nghiệm |

Các ngưỡng này không phải khuyến nghị chung cho mọi ứng dụng. Cần xác nhận cách OCI tổng hợp dữ liệu, đánh giá ngưỡng và hỗ trợ hành động trước khi chuyển bảng thành cấu hình thật.

Nếu cùng dùng một ngưỡng cho tăng và giảm, hệ thống dễ dao động quanh điểm đó. Khoảng cách giữa hai ngưỡng gọi là **hysteresis**: phải vượt một vùng đủ rõ mới đổi hướng.

Ví dụ, CPU từ 67% giảm xuống 50% sau scale-out không nên lập tức kích hoạt scale-in. Ngưỡng giảm thấp hơn tạo khoảng ổn định, nhưng vẫn cần thời gian quan sát và các điều kiện khác phù hợp.

### 4.4. Cooldown và độ trễ phản ứng

Cooldown là khoảng chờ điều khiển giữa các hành động scaling theo cơ chế policy hỗ trợ. Nó giúp tránh việc tiếp tục thay đổi kích thước quá sớm khi tác động của lần trước chưa thể hiện đầy đủ.

Phân biệt các khoảng thời gian:

- Thời gian lấy mẫu và tổng hợp metric.
- Thời gian đánh giá điều kiện.
- Cooldown của bộ điều khiển.
- Thời gian cấp phát và khởi động instance.
- Thời gian ứng dụng sẵn sàng và workload ổn định.

Không xem cooldown là bảo đảm ứng dụng đã warm-up xong. Cũng không mặc định mọi khoảng thời gian trên đều là tham số cho phép người dùng tùy chỉnh. Cần đọc đúng các trường mà policy OCI hỗ trợ.

Nếu máy mới cần vài phút để phục vụ, việc đặt nhịp điều khiển quá gấp có thể tạo nhiều máy trước khi nhìn thấy tác dụng. Ngược lại, nhịp phản ứng quá chậm có thể làm request bị chậm hoặc lỗi trước khi có thêm capacity. Quyết định phải dựa vào cả tốc độ tăng tải và thời gian sẵn sàng đã đo.

### 4.5. Bộ nhớ JVM có thể khiến scale-in khó xảy ra

Heap đã mở rộng, cache hoặc hành vi thu hồi bộ nhớ có thể làm metric memory không giảm nhanh sau khi tải hết. Một ứng dụng có thể xử lý ít request nhưng vẫn giữ nhiều bộ nhớ.

Vì vậy, không chọn memory chỉ vì đó là một tín hiệu có sẵn. Cần xác định metric đo phần nào, nó biến thiên thế nào theo workload, và việc giảm máy có đẩy các máy còn lại vào áp lực GC hoặc thiếu bộ nhớ hay không.

## 5. Autoscaling theo lịch

### 5.1. Dùng lịch khi nhu cầu có thể dự báo

Ví dụ, hệ thống nội bộ có tải cao từ 08:00 đến 18:00 vào các ngày làm việc. Nhóm có thể tăng pool trước giờ bắt đầu và giảm sau khi công việc cuối ngày hoàn tất.

Lịch phù hợp không chỉ với giờ làm việc. Nó còn có thể phục vụ một batch định kỳ hoặc một sự kiện có thời điểm bắt đầu rõ ràng. Tuy nhiên, lịch không đo xem sự kiện kết thúc muộn hay số người tham gia tăng bất thường.

Bài này xét lịch thay đổi số lượng instance. Những hành động vòng đời khác, nếu OCI hỗ trợ cho policy và loại pool đang dùng, cần được đánh giá riêng; giảm số instance và dừng instance có hậu quả khác nhau.

### 5.2. Chuyển giờ nghiệp vụ sang UTC

Schedule-based autoscaling của OCI sử dụng lịch theo UTC. Người thiết kế phải chuyển giờ nghiệp vụ sang UTC trước khi nhập biểu thức lịch theo định dạng được dịch vụ hỗ trợ.

Ví dụ với múi giờ Việt Nam, UTC+7:

| Hoạt động | Giờ Việt Nam | Giờ UTC | Quy mô đích minh họa |
| --- | --- | --- | --- |
| Chuẩn bị trước giờ làm việc, thứ Hai đến thứ Sáu | 07:45 | 00:45 cùng ngày | 6 instance |
| Giảm sau giờ làm việc, thứ Hai đến thứ Sáu | 18:30 | 11:30 cùng ngày | 2 instance |

Đây là bảng mô tả yêu cầu, chưa phải biểu thức cron có thể sao chép vào OCI. Không dùng cú pháp cron của Linux làm mặc định cho mọi trường lịch trong dịch vụ. Khi nhập lịch, kiểm tra định dạng mà OCI yêu cầu và các lần thực thi tiếp theo được hiển thị.

Nếu giờ nghiệp vụ nằm gần nửa đêm, ngày UTC có thể là ngày trước hoặc ngày sau. Với người dùng ở múi giờ có giờ mùa hè, một lịch UTC cố định cũng có thể lệch giờ địa phương khi mùa thay đổi. Các ngày nghỉ và sự kiện ngoại lệ cần được xử lý như yêu cầu riêng, không mặc định được suy ra từ “thứ Hai đến thứ Sáu”.

### 5.3. Tăng trước đỉnh tải, giảm sau khi hoàn tất công việc

Giả sử từ lúc yêu cầu thêm máy đến lúc backend sẵn sàng thường mất 6 phút, và nhóm muốn có thêm 5 phút dự phòng. Tăng đúng lúc 08:00 sẽ quá muộn nếu người dùng bắt đầu truy cập ngay lúc đó. Lịch 07:45 trong ví dụ tạo khoảng chuẩn bị, nhưng vẫn phải kiểm chứng bằng thời gian thực tế và biến động capacity.

Tương tự, lịch giảm lúc 18:00 có thể cắt ngang batch tổng hợp còn chạy. Hãy phân biệt “giờ kết thúc nhận tác vụ mới” với “giờ mọi tác vụ đã hoàn thành”.

Một lịch đặt quy mô đích không bảo đảm có đúng số backend khỏe mạnh ngay tại thời điểm kích hoạt. Sau hành động lịch, vẫn cần quan sát tiến trình của pool, bootstrap, health check và số backend có thể phục vụ.

### 5.4. Kiểm tra xung đột điều khiển

Không đặt hai chính sách có mục tiêu trái ngược tại cùng thời điểm. Nếu có thay đổi thủ công, cần hiểu lần chạy lịch sau sẽ áp dụng mục tiêu được cấu hình thế nào.

Lưu cả yêu cầu nghiệp vụ lẫn lịch UTC trong tài liệu vận hành, kèm người chịu trách nhiệm. Điều này giúp tránh trường hợp người trực nghĩ “hệ thống tự giảm máy bất thường” trong khi đó là một chính sách đã được cấu hình từ trước.

## 6. Chọn min/max và bước thay đổi bằng dữ liệu

### 6.1. Min là năng lực nền, không chỉ là con số rẻ nhất

Giả sử thử nghiệm cho thấy một instance phục vụ an toàn 150 request/giây ở mục tiêu độ trễ đã chọn. Với tải nền 600 request/giây:

```text
Số instance phục vụ tối thiểu theo tải
  = làm tròn lên(600 / 150)
  = 4
```

Nếu còn yêu cầu chịu được việc mất một instance ở chính mức tải đó, cần ít nhất 5 instance đang phục vụ trong mô hình cân bằng tải lý tưởng của ví dụ. Bốn máy còn lại sau lỗi mới đủ xử lý 600 request/giây.

Đây chưa phải mô hình đầy đủ cho việc mất cả availability domain hoặc cho sai lệch phân tải. Cũng không thể thay 5 bằng 2 chỉ vì có hai vùng đặt máy: số miền lỗi và năng lực còn lại sau lỗi là hai vấn đề khác nhau.

### 6.2. Max phải tôn trọng cả hệ thống phía sau

Tăng instance ứng dụng còn tăng số kết nối, request và tác vụ tới các dịch vụ khác.

Ví dụ, nếu mỗi instance đặt tối đa 30 kết nối DB, tám instance có thể mở tổng cộng tới 240 kết nối từ nhóm ứng dụng đó. Cần cộng cả nhóm dịch vụ khác, phiên quản trị và giai đoạn triển khai có đồng thời phiên bản cũ/mới.

Quy mô tối đa cần đối chiếu với:

- Service limits và compartment quotas liên quan.
- Capacity của shape tại vị trí triển khai.
- Dung lượng subnet và các tài nguyên mạng liên quan.
- Giới hạn kết nối và năng lực của cơ sở dữ liệu Oracle.
- Load balancer, dịch vụ lưu trữ, hàng đợi và các phụ thuộc khác.
- Ngân sách và chính sách vận hành.

Max là giới hạn điều khiển, không phải khoản ngân sách cứng. Một shape đắt hơn, volume lớn hơn, lưu lượng mạng cao hoặc thời gian chạy dài vẫn có thể làm chi phí tăng dù số instance không vượt max. Cảnh báo ngân sách cũng không mặc nhiên là cơ chế dừng tài nguyên.

### 6.3. Bước tăng nhỏ hay lớn?

Bước nhỏ giảm nguy cơ cấp phát dư nhưng cần nhiều vòng để theo kịp một đợt tải tăng mạnh. Bước lớn phản ứng nhanh hơn nhưng tăng áp lực capacity, bootstrap và dịch vụ phụ thuộc.

Nếu workload có đỉnh tăng nhanh hơn thời gian khởi động máy, chỉ thay đổi bước tăng có thể chưa đủ. Có thể cần nhiều capacity nền hơn, chuẩn bị theo lịch, giảm thời gian khởi tạo hoặc một thiết kế xử lý tải dồn phù hợp. Việc phối hợp cơ chế phải tuân theo mô hình policy mà nền tảng hỗ trợ.

## 7. Scale-in là một tình huống mất máy có kế hoạch

Khi pool giảm số lượng, một số instance có thể bị kết thúc. Không nên dựa vào việc luôn biết trước máy nào sẽ bị chọn hoặc coi scale-in như thao tác tạm dừng mọi tiến trình một cách an toàn.

Với API, cần kiểm tra thực tế:

- Backend được gỡ khỏi luồng nhận request mới theo cơ chế liên kết pool/load balancer ra sao.
- Request đang xử lý có thời gian hoàn thành phù hợp hay bị ngắt.
- Ứng dụng có hỗ trợ graceful shutdown và cơ chế đó có thực sự được gọi trong đường kết thúc instance hay không.
- Client có timeout/retry hợp lý; request có tác dụng phụ có tránh thực hiện trùng hay không.

Không mặc định OCI sẽ tự cung cấp một lifecycle hook hoặc khoảng drain tùy ý cho ứng dụng chỉ vì có autoscaling policy. Phải xác minh các khả năng và thời hạn của từng thành phần. Ngay cả khi có graceful shutdown, ứng dụng vẫn cần chịu được trường hợp mất máy đột ngột.

Với worker xử lý queue, nên thiết kế theo mô hình nhận việc, xác nhận kết quả và nhận lại khi lỗi của hệ thống hàng đợi đang dùng. Lưu tiến độ cần thiết ở nơi bền vững; xử lý trùng bằng idempotency hoặc cơ chế giao dịch phù hợp với nghiệp vụ.

Dữ liệu trên ổ cục bộ của instance không được mặc định tồn tại sau scale-in. Boot volume và các volume liên quan cũng có chính sách vòng đời riêng cần kiểm tra, bao gồm cả khả năng để lại volume tính phí sau khi instance không còn.

## 8. Hai kịch bản triển khai minh họa

### 8.1. API Java có tải bất ngờ: đánh giá theo metric

Bối cảnh: ứng dụng stateless, CPU tăng khá đều theo lưu lượng; cơ sở dữ liệu Oracle còn năng lực dự phòng trong khoảng mở rộng đã thử.

Trình tự thiết kế:

1. Chọn image và shape đã kiểm chứng với JDK, thư viện và agent.
2. Tạo quy trình bootstrap có thể lặp lại, không cần thao tác SSH sau mỗi lần tạo máy.
3. Thiết lập instance pool, placement và đường mạng đến cơ sở dữ liệu.
4. Liên kết load balancer, xác minh backend khỏe mạnh trước khi nhận tải.
5. Kiểm tra metric CPU thực sự xuất hiện cho các instance trong pool.
6. Chọn min/max, ngưỡng tăng/giảm, bước thay đổi và cooldown theo thử nghiệm.
7. Phát tải có kiểm soát, theo dõi từ lần vượt ngưỡng đến khi máy mới phục vụ.
8. Giảm tải, xác nhận scale-in không làm mất giao dịch và không vượt khả năng máy còn lại.

Nếu CPU thấp nhưng p95 tiếp tục tăng do DB chậm, dừng việc điều chỉnh ngưỡng một cách mò mẫm. Cần xác định nút thắt; scale-out ứng dụng khi đó còn có thể làm cơ sở dữ liệu nhận thêm kết nối.

### 8.2. Hệ thống nội bộ có giờ làm việc ổn định: đánh giá theo lịch

Bối cảnh: tải được dự báo theo ngày làm việc, đỉnh đầu giờ khá đều và môi trường ngoài giờ vẫn phải phục vụ một số tác vụ.

Trình tự thiết kế:

1. Đo thời gian máy mới sẵn sàng và lưu lượng thực tế đầu/cuối ngày.
2. Chọn quy mô giờ làm việc và quy mô ngoài giờ, kiểm tra năng lực còn lại khi lỗi.
3. Chuyển lịch nghiệp vụ sang UTC và kiểm tra ngày trong tuần.
4. Đặt lịch tăng trước đỉnh tải đủ sớm.
5. Đặt lịch giảm sau giai đoạn xử lý công việc còn lại.
6. Thử một lịch gần thời điểm hiện tại trong môi trường thử nghiệm để quan sát hành vi.
7. Kiểm tra cuối tuần, ngày nghỉ và sự kiện tăng tải ngoại lệ.
8. Ghi cách tạm thay đổi policy, phục hồi lịch chuẩn và xác nhận quy mô hiện tại.

Không nên chọn quy mô ngoài giờ bằng 0 chỉ để giảm chi phí nếu vẫn có health check, tác vụ nền hoặc yêu cầu truy cập cần được đáp ứng. Khả năng cho phép kích thước cụ thể cũng phải được xác nhận theo cấu hình OCI sử dụng.

## 9. Kế hoạch kiểm thử trước khi dùng cho production

Bảng sau là kế hoạch thực hành trong môi trường được phép thử; không phải yêu cầu thực hiện trực tiếp trên hệ thống đang phục vụ người dùng.

| Tình huống | Quan sát cần có | Kết quả mong đợi |
| --- | --- | --- |
| Tăng tải từ từ | Metric, thời điểm policy hành động, số máy và backend khỏe mạnh | Quy mô tăng và độ trễ trở về mục tiêu trong khoảng chấp nhận |
| Tăng tải đột ngột | Tỷ lệ lỗi và thời gian chờ máy mới | Biết giới hạn phản ứng và nhu cầu capacity nền |
| Giảm tải | Điều kiện giảm, cooldown, request đang xử lý | Giảm có kiểm soát, không mất công việc đã xác nhận |
| Tải dao động gần ngưỡng | Chuỗi tăng/giảm và metric trước/sau hành động | Không thay đổi quy mô liên tục gây bất ổn |
| Bootstrap lỗi | Log khởi tạo, trạng thái instance và health check | Không coi máy lỗi là năng lực phục vụ thành công |
| Metric gián đoạn | Timestamp, agent/plugin và hành vi policy | Có cảnh báo, không diễn giải dữ liệu thiếu thành tải bằng 0 |
| Thiếu capacity hoặc hết limit | Sự kiện thao tác và quy mô thực tế | Phát hiện hành động chưa hoàn tất, có hướng xử lý phù hợp |
| Đến lịch tăng/giảm | Thời gian UTC, ngày và quy mô mục tiêu | Hành động đúng lịch, số backend sẵn sàng được xác nhận |
| Scale-in khi đang có tác vụ | Request, xác nhận queue và trạng thái giao dịch | Tác vụ hoàn tất hoặc được nhận lại theo thiết kế |
| Mất một instance | Năng lực máy còn lại và độ trễ | Đáp ứng yêu cầu chịu lỗi đã cam kết |

Ghi lại thời gian từ trigger đến phục hồi mục tiêu độ trễ. Chỉ nhìn thấy số instance tăng chưa đủ chứng minh autoscaling đạt mục đích.

## 10. Giám sát và xử lý tình huống bất thường

### 10.1. Ba lớp quan sát cần đối chiếu

- **Điều khiển**: policy đang bật hay tắt, lịch/ngưỡng nào áp dụng, khi nào có yêu cầu thay đổi quy mô.
- **Hạ tầng**: kích thước pool được yêu cầu, instance thực tế, trạng thái khởi tạo, capacity và backend khỏe mạnh.
- **Ứng dụng**: throughput, tỷ lệ lỗi, latency, hàng đợi, thời gian truy vấn và số kết nối DB.

Ba lớp này có thể lệch nhau. Policy có thể yêu cầu sáu máy nhưng chỉ bốn máy phục vụ được vì hai máy bootstrap lỗi. Metric CPU có thể giảm nhưng người dùng vẫn chậm vì vấn đề nằm ở cơ sở dữ liệu.

### 10.2. Bảng chẩn đoán

| Triệu chứng | Hướng kiểm tra đầu tiên |
| --- | --- |
| CPU cao nhưng pool không tăng | Policy, điều kiện đánh giá, cooldown, max và metric đúng pool |
| Có yêu cầu tăng nhưng thiếu máy mới | Limits/quota, capacity, placement, image/shape và sự kiện thao tác |
| Máy mới có mặt nhưng không nhận request | Bootstrap, mạng, đăng ký backend và health check |
| Pool tăng mãi mà latency không giảm | Nút thắt ngoài Compute, phân tải hoặc nguồn metric không phản ánh nhu cầu |
| Tải hết nhưng pool không giảm | Ngưỡng giảm, dữ liệu còn giữ, cooldown, min và trạng thái policy |
| Lịch chạy sai giờ | UTC, ngày trong tuần, biểu thức lịch và các thay đổi mùa của múi giờ nghiệp vụ |
| Chi phí tăng ngoài dự báo | Thời gian ở quy mô lớn, shape, volume, mạng và tài nguyên còn lại sau scale-in |
| Scale-in làm mất session hoặc tác vụ | Trạng thái cục bộ, cơ chế retry, idempotency và đường shutdown |

Nếu cần tạm ngừng autoscaling để điều tra, thực hiện theo quy trình vận hành đã được phép, chọn quy mô an toàn và ghi rõ người chịu trách nhiệm khôi phục. Tạm dừng policy không tự giải quyết thiếu capacity hoặc lỗi ứng dụng; cũng không nên giả định nó sẽ hoàn tác các thao tác đã bắt đầu.

## 11. Phiếu thiết kế và câu hỏi tự kiểm tra

Hoàn thành phiếu sau trước khi chuyển thiết kế thành cấu hình triển khai:

| Nội dung | Kết quả cần ghi |
| --- | --- |
| Workload và mục tiêu | Throughput, p95/p99, tỷ lệ lỗi, thời gian xử lý tác vụ |
| Cơ chế được chọn | Theo lịch hoặc theo metric, lý do và ràng buộc OCI đã xác nhận |
| Instance pool | Compartment, cấu hình máy, shape, image và placement |
| Tính lặp lại | Cách bootstrap, phiên bản ứng dụng và quyền runtime |
| Quy mô | Min/ban đầu/max hoặc các quy mô đích theo lịch phù hợp policy |
| Trigger | Metric/ngưỡng/hành động hoặc lịch UTC và giờ nghiệp vụ tương ứng |
| Thời gian | Độ trễ quan sát, cooldown khi áp dụng, thời gian máy sẵn sàng |
| Dữ liệu và scale-in | Session, file, queue, giao dịch, retry và phục hồi |
| Phụ thuộc | Cơ sở dữ liệu, load balancer, subnet, limits/quota và capacity |
| Vận hành và chi phí | Metrics, cảnh báo, chủ sở hữu, dự toán và cách xử lý ngoại lệ |
| Bằng chứng | Kết quả thử tăng tải, giảm tải, mất máy và lỗi khởi tạo |

Tự kiểm tra:

1. Vì sao instance ở trạng thái chạy vẫn có thể chưa tăng được năng lực phục vụ của API?
2. Khi nào một lịch tăng trước 08:00 hiệu quả hơn việc chỉ chờ CPU vượt ngưỡng?
3. Nếu CPU của pool thấp nhưng p95 cao và DB đang quá tải, thêm instance ứng dụng có thể gây hệ quả gì?
4. Khoảng cách giữa ngưỡng tăng và giảm giải quyết vấn đề gì, và vì sao vẫn cần cân nhắc thời gian phản ứng?
5. Một lịch 07:45 giờ Việt Nam tương ứng giờ UTC nào? Vì sao vẫn phải kiểm tra các lần chạy kế tiếp?
6. Tại sao metric không có dữ liệu không thể được xem như CPU bằng 0?
7. Với 600 request/giây và năng lực an toàn 150 request/giây mỗi máy, cần bao nhiêu máy nếu muốn chịu mất một máy theo giả định của bài?
8. Những dữ liệu nào sẽ gặp rủi ro nếu chỉ tồn tại trên instance bị chọn scale-in?
9. Vì sao max instance và cảnh báo ngân sách chưa tạo ra một giới hạn chi phí tuyệt đối?
10. Bạn cần kiểm tra điều gì trước khi muốn phối hợp lịch và metric để điều khiển cùng một pool?

Đầu ra của bài thực hành là một chính sách có mục tiêu rõ ràng cùng bằng chứng rằng việc thêm và giảm instance giữ được chất lượng phục vụ, an toàn dữ liệu và phạm vi chi phí đã dự trù.
