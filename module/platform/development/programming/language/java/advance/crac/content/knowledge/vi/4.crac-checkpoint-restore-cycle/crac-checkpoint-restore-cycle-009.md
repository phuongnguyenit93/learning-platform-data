# Khôi phục nhiều tiến trình từ cùng một ảnh

Một lợi ích quan trọng của checkpoint/restore là có thể chuẩn bị ứng dụng một lần rồi dùng trạng thái đã chuẩn bị làm điểm xuất phát cho nhiều instance. Thay vì khởi tạo JVM, nạp framework và làm nóng ứng dụng từ đầu cho từng instance, hệ thống tạo một checkpoint sau khi ứng dụng đã đạt trạng thái nền phù hợp. Khi cần mở rộng, nhiều tiến trình có thể được khôi phục từ cùng bộ ảnh checkpoint, nếu bản dựng JDK CRaC và nền tảng triển khai hỗ trợ cách sử dụng đó.

Mỗi lần restore tạo ra một tiến trình độc lập với không gian địa chỉ và vòng đời riêng. Các tiến trình có thể bắt đầu từ trạng thái bộ nhớ giống nhau, nhưng sau khi chạy, trạng thái của chúng sẽ thay đổi độc lập. Chúng không phải nhiều luồng cùng truy cập một heap Java và cũng không phải nhiều người dùng cùng điều khiển một tiến trình duy nhất.

Điểm khó của mô hình này nằm ở những gì được sao chép cùng checkpoint. Nếu ảnh chứa danh tính instance, kết nối mạng, token, lịch tác vụ hoặc trạng thái nghiệp vụ riêng của tiến trình tạo ảnh, các bản restore có thể khởi đầu với dữ liệu trùng lặp hoặc đã lỗi thời. Muốn dùng một ảnh làm mẫu an toàn, cần chuẩn bị trạng thái nền có thể dùng chung và tạo lại trạng thái riêng cho từng instance sau restore.

## 1. Khái niệm khôi phục nhiều tiến trình từ cùng một ảnh

Checkpoint là bản lưu trạng thái của một tiến trình tại một thời điểm. Trong ứng dụng Java dùng CRaC, trạng thái đó có thể bao gồm heap, trạng thái runtime và những thông tin cần thiết khác để môi trường checkpoint/restore tái tạo tiến trình.

Khi khôi phục nhiều tiến trình từ cùng một ảnh, quy trình có dạng:

1. Khởi chạy một tiến trình chuẩn bị.
2. Khởi tạo ứng dụng, nạp cấu hình nền và làm nóng các luồng xử lý cần thiết.
3. Đưa tài nguyên về trạng thái an toàn cho checkpoint rồi tạo ảnh.
4. Giữ bộ ảnh làm artifact nền.
5. Khi cần nhiều instance, yêu cầu môi trường tạo nhiều tiến trình restore từ artifact đó.
6. Mỗi tiến trình phục hồi tài nguyên, thiết lập danh tính riêng, kiểm tra readiness và bắt đầu nhận công việc.

```text
                 Tiến trình chuẩn bị
                         |
                         v
             Khởi tạo ứng dụng và warm-up
                         |
                         v
                 Tạo checkpoint
                         |
                         v
                Bộ ảnh checkpoint gốc
                  /       |       \
                 /        |        \
                v         v         v
           Restore A  Restore B  Restore C
                |         |         |
                v         v         v
           Process A  Process B  Process C
                |         |         |
                v         v         v
           Tài nguyên  Tài nguyên  Tài nguyên
           riêng A     riêng B     riêng C
```

Sơ đồ mô tả mô hình logic. Cách gọi lệnh restore, cách tổ chức thư mục ảnh, khả năng chạy nhiều restore đồng thời và giới hạn số lần restore phụ thuộc vào bản dựng JDK, công cụ checkpoint/restore và nền tảng cụ thể. Không phải mọi bản JDK có hỗ trợ CRaC đều mặc nhiên hỗ trợ mọi kiểu fan-out hoặc restore song song. Cần xác nhận khả năng này trong tài liệu của nhà cung cấp và thử trên môi trường mục tiêu.

## 2. Một ảnh có thể tạo ra nhiều tiến trình độc lập

Hãy hình dung ứng dụng dịch vụ sản phẩm cần mở rộng từ một instance lên ba instance khi lượng request tăng. Nếu mỗi instance khởi động từ đầu, cả ba phải lặp lại một phần công việc khởi tạo và warm-up. Với mô hình checkpoint, nhóm có thể chuẩn bị ứng dụng một lần rồi dùng ảnh đã chuẩn bị làm điểm xuất phát cho ba lần restore.

Các tiến trình sau restore có một số đặc điểm:

- **Trạng thái ban đầu có thể giống nhau:** Các đối tượng và cache đã tồn tại trong checkpoint có thể xuất hiện trong từng tiến trình restore.
- **Bộ nhớ được quản lý riêng:** Mỗi tiến trình có không gian địa chỉ và trạng thái runtime của riêng nó. Thay đổi một đối tượng trong tiến trình A không tự động thay đổi đối tượng tương ứng trong tiến trình B.
- **Tài nguyên hệ điều hành cần được xử lý riêng:** File descriptor, socket, thread, namespace và tài nguyên bên ngoài phải đáp ứng quy tắc của cơ chế restore và ứng dụng.
- **Trạng thái sẽ phân kỳ:** Sau khi nhận request khác nhau, các cache, bộ đếm, thread và trạng thái nghiệp vụ trong từng tiến trình có thể khác nhau.

Không nên hiểu “cùng một ảnh” là các tiến trình cùng dùng một heap có thể ghi. Cũng không nên hiểu đây là thao tác sao chép một file JAR. Ảnh checkpoint thường là một tập hợp dữ liệu và metadata gắn với trạng thái tiến trình, môi trường runtime và cách bố trí tài nguyên cụ thể.

Một số hệ điều hành hoặc cơ chế lưu trữ có thể tối ưu bộ nhớ vật lý bằng copy-on-write hoặc chia sẻ trang chỉ đọc. Đây là tối ưu ở tầng hệ thống, phụ thuộc vào công cụ và môi trường. Ứng dụng không được dựa vào đó để chia sẻ đối tượng Java có thể thay đổi, và không nên giả định rằng các restore luôn dùng chung RAM vật lý.

## 3. Phân biệt ảnh checkpoint gốc với tiến trình đã restore

Trong một hệ thống có nhiều instance, cần phân biệt ba loại đối tượng:

| Thành phần | Vai trò | Vòng đời |
|---|---|---|
| Ảnh checkpoint gốc | Artifact làm mẫu chứa trạng thái nền đã chuẩn bị | Được lưu, quản lý phiên bản và dùng cho các lần restore theo chính sách |
| Tiến trình chuẩn bị | Chạy ứng dụng để tạo trạng thái nền và checkpoint | Thường chỉ tồn tại trong giai đoạn chuẩn bị ảnh |
| Tiến trình restore | Instance độc lập được tạo từ ảnh | Có danh tính, tài nguyên và vòng đời riêng |

Ảnh gốc nên được quản lý như một artifact bất biến sau khi tạo thành công. Nếu công cụ restore hoặc quy trình của nhà cung cấp yêu cầu thư mục làm việc riêng, hãy tạo bản sao hoặc workspace riêng cho từng lần restore. Không để nhiều tiến trình cùng ghi vào một thư mục ảnh hoặc sửa metadata của cùng một bộ checkpoint nếu tài liệu nền tảng không xác nhận thao tác đó an toàn.

Hãy xem checkpoint như một bộ artifact hoàn chỉnh. Đừng chỉ sao chép một file mà bỏ qua các file dữ liệu, metadata, quyền truy cập hoặc cấu trúc thư mục đi kèm. Trước khi phân phối, có thể tính checksum cho bộ artifact theo cách phù hợp với định dạng lưu trữ để xác minh các bản sao không bị thiếu hoặc hỏng.

Một quy trình phát hành an toàn thường giữ bản gốc chỉ đọc, tạo workspace restore riêng và gắn mỗi instance với một mã nhận diện của lần triển khai. Việc có thể đọc đồng thời một ảnh từ nhiều restore hay phải nhân bản thư mục ảnh trước cần được xác nhận theo đúng công cụ đang dùng.

## 4. Điều kiện tương thích khi restore nhiều lần

Khôi phục một ảnh nhiều lần không làm mất các yêu cầu tương thích vốn có của checkpoint/restore. Mỗi lần restore vẫn phải chạy trong môi trường đáp ứng yêu cầu của bản JDK và công cụ đã tạo ảnh.

Các yếu tố cần xác nhận gồm:

- Nhà cung cấp, phiên bản, số build và cấu hình của JDK CRaC.
- Hệ điều hành, phiên bản kernel, kiến trúc CPU và các tính năng kernel cần thiết.
- Phiên bản CRIU hoặc cơ chế checkpoint/restore mà bản dựng sử dụng.
- Container runtime, PID namespace, network namespace, user namespace, cgroup và quyền hệ thống.
- Thư viện native, biến môi trường, đường dẫn file, mount và các file phụ thuộc.
- Cách cấp phát tài nguyên hệ điều hành cho mỗi lần restore.

Không mặc định rằng ảnh được tạo trên máy phát triển có thể restore trên bất kỳ node nào trong cluster. Các node trong cùng cluster cũng có thể khác nhau về kernel, kiến trúc, thư viện, cấu hình bảo mật hoặc mount. Nên cố định môi trường tạo ảnh và môi trường restore bằng image triển khai, cấu hình node và tài liệu tương thích của nhà cung cấp.

Khi nhiều restore chạy đồng thời, nền tảng còn phải cấp phát tài nguyên hệ thống cho từng tiến trình. Ví dụ, mỗi tiến trình cần PID phù hợp, giới hạn cgroup, bộ nhớ, file descriptor và vị trí lưu trữ riêng. Cách các namespace được tạo hoặc tái sử dụng ảnh hưởng trực tiếp đến việc những tiến trình đó có thể cùng tồn tại hay không.

## 5. Danh tính riêng cho từng tiến trình

Đây là yêu cầu quan trọng nhất khi một ảnh được dùng làm mẫu cho nhiều instance. Tiến trình chuẩn bị có thể đã đọc một số thông tin nhận diện của chính nó. Nếu những giá trị đó được giữ nguyên trong checkpoint, mọi bản restore có nguy cơ dùng cùng một danh tính.

Các giá trị cần được xác định lại theo từng instance có thể gồm:

- Instance ID, pod name, hostname hoặc mã replica.
- Địa chỉ IP, cổng lắng nghe và thông tin network interface.
- Vùng triển khai, availability zone hoặc node identity.
- Token, credential hoặc thông tin xác thực gắn với instance.
- Tên consumer, client ID hoặc tên worker phải duy nhất.
- Đường dẫn file tạm, thư mục log và vị trí ghi dữ liệu cục bộ.

Không nên đưa danh tính của tiến trình chuẩn bị vào trạng thái nền nếu các giá trị đó phải khác nhau giữa các replica. Có thể đọc thông tin riêng từ biến môi trường, file cấu hình được mount, metadata service hoặc hệ thống điều phối sau restore. Nguồn và thời điểm đọc phải phù hợp với môi trường triển khai.

Một mô hình cấu hình thường dùng là tách cấu hình thành hai nhóm:

| Nhóm cấu hình | Ví dụ | Thời điểm xử lý |
|---|---|---|
| Cấu hình nền dùng chung | Quy tắc nghiệp vụ, metadata bất biến, cấu hình serializer | Có thể nạp trước checkpoint nếu an toàn và không chứa dữ liệu riêng |
| Cấu hình theo instance | Instance ID, IP, port, consumer ID, thông tin node | Đọc hoặc làm mới sau restore |

Nếu một thư viện lưu cache của cấu hình vào static field, việc thay biến môi trường sau restore không tự động cập nhật giá trị đã đọc trước đó. Ứng dụng cần có cơ chế nạp lại hoặc khởi tạo lại thành phần đó. Vì vậy, phải xác định dữ liệu nào được đọc lúc khởi tạo và dữ liệu nào cần được làm mới trong callback `afterRestore(...)` hoặc một bước phục hồi tương đương.

## 6. Xử lý kết nối mạng và cổng lắng nghe

Kết nối mạng là một trong những nguyên nhân phổ biến khiến mô hình restore nhiều tiến trình gặp lỗi. Một kết nối TCP đang mở trong tiến trình chuẩn bị có thể không còn hợp lệ sau khi checkpoint được lưu, và việc khôi phục cùng một socket cho nhiều tiến trình có thể tạo ra hành vi không mong muốn.

Trước checkpoint, ứng dụng thường cần dừng nhận kết nối mới và đóng các socket hoặc client phụ thuộc môi trường theo hướng dẫn CRaC của thư viện. Sau restore, từng tiến trình tạo lại các kết nối cần thiết bằng thông tin mạng của chính nó.

Đặc biệt chú ý đến cổng HTTP hoặc cổng dịch vụ:

- Nếu các tiến trình nằm trong những network namespace khác nhau, chúng có thể dùng cùng số cổng trong namespace riêng, tùy cấu hình nền tảng.
- Nếu nhiều tiến trình nằm trong cùng network namespace và cùng bind một địa chỉ/cổng, thao tác bind có thể thất bại do cổng đã được sử dụng.
- Một số hệ thống hỗ trợ `SO_REUSEPORT` cho trường hợp nhiều socket cùng bind một cổng, nhưng cần xác minh khả năng của hệ điều hành, JVM và server framework. Không nên mặc định rằng ứng dụng Java đang dùng hỗ trợ cấu hình đó.
- Một lựa chọn khác là cấp cổng riêng cho từng instance hoặc đặt reverse proxy/load balancer phía trước để phân phối traffic.

Ví dụ, ba replica trong ba container có network namespace riêng có thể cùng lắng nghe cổng 8080 bên trong container. Load balancer hoặc service discovery định tuyến đến địa chỉ từng container. Nếu cả ba tiến trình cùng chạy trực tiếp trong một namespace của host, cần có thiết kế cấp cổng rõ ràng.

Các kết nối đi ra cũng cần được tạo lại khi phù hợp. Connection pool đến database, HTTP client, TLS session, channel đến message broker và DNS cache có thể chứa trạng thái đã hết hạn hoặc gắn với node cũ. Sau restore, từng instance nên tạo kết nối của riêng mình và xác minh kết nối trước khi báo sẵn sàng.

## 7. Quản lý database, message broker và dịch vụ bên ngoài

Một checkpoint được tạo từ tiến trình chuẩn bị có thể chứa trạng thái của các client bên ngoài. Khi nhiều tiến trình restore, không nên để tất cả tiếp tục dùng một kết nối hoặc một định danh client cũ.

### 7.1. Database và connection pool

Mỗi instance nên có pool riêng hoặc một cơ chế kết nối được thư viện và nền tảng hỗ trợ rõ ràng. Trước checkpoint, đóng hoặc đưa pool về trạng thái an toàn theo tích hợp CRaC. Sau restore, tạo pool mới với cấu hình của instance và kiểm tra khả năng kết nối.

Nếu ba tiến trình cùng restore một pool đã có sẵn kết nối, có thể xảy ra lỗi do socket không hợp lệ, giới hạn số kết nối, hoặc việc cả ba tiến trình đồng thời dùng một định danh không phù hợp. Cũng cần tính tổng số kết nối dự kiến: nếu mỗi replica tạo một pool tối đa 30 connection, 20 replica có thể tạo nhu cầu lên đến 600 connection.

### 7.2. Message broker và consumer

Các consumer thường cần định danh hoặc nhóm tiêu thụ phù hợp. Khi nhiều instance dùng cùng consumer ID trong một hệ thống yêu cầu ID duy nhất, chúng có thể ghi đè trạng thái hoặc tranh chấp. Với Kafka, chẳng hạn, consumer group có thể được chia sẻ có chủ đích để phân phối partition, nhưng mỗi consumer instance vẫn cần được tạo và quản lý đúng vòng đời của client. Không nên sao chép một consumer đang hoạt động từ checkpoint rồi để các bản restore tiếp tục cùng trạng thái nội bộ.

Trước checkpoint, cần dừng nhận message mới, xử lý hoặc hoàn tác message đang chạy, và bảo đảm offset/acknowledgement không ở trạng thái không nhất quán. Sau restore, mỗi instance kết nối lại, tham gia group hoặc đăng ký subscription theo thiết kế của hệ thống.

### 7.3. Secret và token

Token hoặc credential được lưu trong heap có thể hết hạn giữa thời điểm tạo checkpoint và thời điểm restore. Nếu mọi instance dùng chung một token ngắn hạn, chúng có thể cùng thất bại sau khi token hết hạn hoặc bị thu hồi. Hãy lấy secret theo chính sách của hệ thống sau restore, hoặc xác minh thời hạn và làm mới trước khi sử dụng.

## 8. Thread nền, scheduler và tác vụ định kỳ

Một tiến trình chuẩn bị có thể có thread nền, executor, timer và scheduler. Khi tạo checkpoint, các thread này cần ở trạng thái được hỗ trợ và không được giữ một công việc dở dang làm mất tính nhất quán.

Trước checkpoint, ứng dụng nên có quy trình quiesce:

1. Ngừng nhận tác vụ mới.
2. Chờ tác vụ đang chạy hoàn tất trong giới hạn thời gian đã định.
3. Lưu trạng thái công việc bền vững nếu cần tiếp tục sau restore.
4. Dừng executor hoặc timer có tài nguyên phụ thuộc môi trường.
5. Đảm bảo không còn lock hoặc giao dịch bị giữ ở trạng thái không thể phục hồi.

Sau restore, từng tiến trình khởi động worker và scheduler theo cấu hình riêng. Cần chú ý rằng một lịch tác vụ đã được lưu trong checkpoint có thể được nhiều tiến trình khôi phục cùng lúc. Nếu tất cả đều chạy cùng một tác vụ định kỳ, hệ thống có thể gửi email nhiều lần, tạo báo cáo trùng lặp hoặc thực hiện cùng một thao tác nghiệp vụ nhiều lần.

Các cách xử lý phổ biến:

- Dùng distributed lock hoặc leader election khi chỉ một instance được phép chạy tác vụ.
- Dùng cơ chế phân chia partition hoặc shard để mỗi instance xử lý phần việc riêng.
- Dùng hàng đợi bền vững và acknowledgement để điều phối công việc giữa các worker.
- Thiết kế tác vụ idempotent, có khóa chống xử lý trùng và kiểm tra trạng thái trước khi ghi kết quả.
- Tính lại thời điểm chạy tiếp theo sau restore thay vì phát lại tất cả lịch đã bỏ lỡ.

Không nên dựa vào một biến `static` trong bộ nhớ để bảo đảm “chỉ một instance chạy tác vụ”. Biến đó được sao chép cùng checkpoint, vì vậy tất cả tiến trình có thể cùng thấy giá trị ban đầu giống nhau. Điều phối giữa các tiến trình phải dựa trên một cơ chế phối hợp bên ngoài hoặc một cách phân chia công việc có thể kiểm chứng.

## 9. Cache và dữ liệu trong bộ nhớ

Một trong những lý do tạo checkpoint sau warm-up là tái sử dụng cache đã được nạp. Tuy nhiên, không phải cache nào cũng phù hợp để nhân bản sang nhiều tiến trình.

**Cache nền có thể chia sẻ về mặt logic:** metadata bất biến, bảng tra cứu ít thay đổi, cấu trúc đã phân tích hoặc dữ liệu tham chiếu có thể được chuẩn bị trước checkpoint. Mỗi tiến trình nhận bản trạng thái ban đầu tương tự và có thể đọc nhanh sau restore.

**Cache thay đổi theo instance:** bộ đếm request, trạng thái session, dữ liệu riêng của người dùng hoặc cache chứa thông tin định danh không nên được xem như trạng thái dùng chung. Mỗi tiến trình có bản sao độc lập; cập nhật trong một tiến trình không tự đồng bộ sang các tiến trình khác.

**Cache có thời hạn:** dữ liệu có TTL, DNS, chứng thư, token hoặc cấu hình có thể đã lỗi thời khi restore. Cần kiểm tra thời hạn, vô hiệu hóa hoặc làm mới sau restore.

Nếu ứng dụng cần cache nhất quán giữa nhiều replica, hãy dùng hệ thống cache hoặc kho dữ liệu ngoài được thiết kế cho truy cập đồng thời. Việc mỗi tiến trình có một bản sao heap không thay thế được distributed cache.

## 10. Ngẫu nhiên, thời gian và dữ liệu duy nhất

Vì các tiến trình bắt đầu từ cùng một trạng thái bộ nhớ, những bộ sinh số giả ngẫu nhiên được khởi tạo trước checkpoint có thể mang trạng thái giống nhau ở từng bản restore. Nếu tiếp tục dùng trạng thái đó, các tiến trình có thể sinh ra chuỗi giá trị trùng hoặc có tương quan ngoài dự kiến.

Với các giá trị cần duy nhất hoặc khó đoán, hãy chọn cơ chế phù hợp:

- Tạo instance ID từ hệ thống điều phối hoặc nguồn định danh có bảo đảm duy nhất.
- Dùng `SecureRandom` hoặc cơ chế entropy phù hợp và xác minh hành vi của runtime sau restore.
- Làm mới bộ sinh số giả ngẫu nhiên theo hướng dẫn của thư viện khi trạng thái của nó được lưu trong checkpoint.
- Không dùng bộ đếm trong heap làm nguồn duy nhất để tạo ID toàn hệ thống.

Thời gian cũng cần được xem xét. Một đối tượng cache có timestamp được tạo trước checkpoint có thể đã hết hạn khi restore. Scheduler hoặc logic timeout có thể mang deadline cũ. Sau restore, hãy đánh giá lại thời gian hết hạn, lease, token và lịch chạy dựa trên đồng hồ hiện tại.

## 11. Ngăn side effect bị lặp

Khi một ảnh được dùng để tạo nhiều instance, mọi trạng thái và công việc đã thực hiện trước checkpoint cần được xem xét về side effect.

Ví dụ, tiến trình chuẩn bị có thể chạy một đoạn khởi tạo tạo bản ghi mặc định trong database. Bản ghi đó đã tồn tại một lần trước checkpoint. Các bản restore không nên thực hiện lại thao tác tạo bản ghi như thể đây là lần đầu ứng dụng chạy.

Ngược lại, nếu một callback `afterRestore(...)` gửi email chào mừng, tạo đơn hàng hoặc ghi dữ liệu nghiệp vụ không có khóa chống trùng, thao tác đó sẽ được thực hiện trong mỗi tiến trình restore. Khi tạo 10 instance, side effect có thể xuất hiện 10 lần.

Hãy phân loại công việc thành:

| Loại công việc | Ví dụ | Cách xử lý |
|---|---|---|
| Chuẩn bị nền một lần | Phân tích schema, nạp metadata bất biến | Thực hiện trước checkpoint nếu có thể tái sử dụng |
| Khởi tạo riêng mỗi instance | Tạo pool, bind cổng, lấy instance ID | Thực hiện sau restore cho từng tiến trình |
| Side effect nghiệp vụ | Gửi email, tạo đơn, ghi giao dịch | Chỉ chạy theo sự kiện nghiệp vụ thật; dùng idempotency và lưu trạng thái bền vững |
| Tác vụ cần một chủ thể | Cron toàn hệ thống, điều phối migration | Dùng leader election, lock hoặc cơ chế điều phối tập trung |

Một quy trình warm-up an toàn nên dùng dữ liệu thử và các thao tác không gây side effect nghiệp vụ. Callback phục hồi nên tập trung tái tạo tài nguyên runtime. Nếu cần chạy migration hoặc tác vụ khởi tạo toàn hệ thống, hãy quản lý nó như một bước triển khai riêng có kiểm soát.

## 12. Điều phối nhiều lần restore

Ngay cả khi một ảnh có thể tạo nhiều tiến trình, khôi phục tất cả instance cùng một lúc chưa chắc là lựa chọn tốt. Mỗi restore có thể tạo tải lớn lên CPU, bộ nhớ, filesystem, database, DNS và các dịch vụ phụ thuộc.

Ví dụ, một ảnh được dùng để mở rộng từ 2 lên 40 replica. Nếu tất cả 38 tiến trình mới đồng thời restore rồi mở connection pool, database có thể nhận hàng trăm kết nối trong vài giây. Cache ngoài có thể bị nhiều instance cùng tải lại. Hệ thống log và service discovery cũng có thể nhận một đợt đăng ký lớn.

Một bộ điều phối nên kiểm soát:

- **Concurrency:** số lượng restore chạy đồng thời trên mỗi node và toàn cluster.
- **Staggering:** chia restore thành từng đợt hoặc thêm độ lệch thời gian giữa các instance.
- **Backoff và retry:** giới hạn retry, dùng exponential backoff và jitter khi dịch vụ phụ thuộc chưa sẵn sàng.
- **Capacity:** kiểm tra trước CPU, RAM, file descriptor, PID, cgroup, dung lượng lưu trữ và giới hạn kết nối.
- **Readiness:** chỉ đưa instance vào load balancer khi callback, kết nối và kiểm tra sức khỏe đã hoàn tất.
- **Scale-in:** dừng nhận công việc, drain request và đóng tài nguyên khi loại bỏ instance.

Không nên coi thời điểm tiến trình restore xong là thời điểm ứng dụng đã sẵn sàng. Một tiến trình có thể đã tồn tại nhưng vẫn đang tạo pool, lấy secret, đăng ký consumer hoặc khởi động worker. Readiness cần phản ánh trạng thái phục vụ thực tế.

## 13. Quy trình chuẩn bị một ảnh dùng cho nhiều instance

Một quy trình có thể tổ chức thành các giai đoạn sau.

### Giai đoạn 1: Chọn cấu hình nền

Chọn đúng JDK CRaC, phiên bản ứng dụng, dependency, cấu hình framework và image triển khai. Cấu hình được nạp trước checkpoint chỉ nên chứa dữ liệu có thể dùng chung an toàn. Không đưa ID, IP, token hoặc thông tin gắn với một replica cụ thể vào trạng thái nền.

### Giai đoạn 2: Khởi tạo và làm nóng

Khởi chạy ứng dụng, hoàn tất các bước khởi tạo nền và chạy workload đại diện. Xác nhận những đường đi quan trọng đã được làm nóng. Tránh chạy nghiệp vụ thật hoặc tạo side effect không thể lặp lại an toàn.

### Giai đoạn 3: Đưa tiến trình về trạng thái có thể checkpoint

Ngừng nhận công việc mới, drain request, hoàn tất giao dịch, dừng consumer và scheduler theo thiết kế. Đóng hoặc chuẩn bị tạo lại các kết nối, socket, pool và tài nguyên phụ thuộc môi trường. Đăng ký các resource CRaC cần thiết để callback được gọi trong vòng đời checkpoint/restore.

### Giai đoạn 4: Tạo và đóng gói ảnh

Tạo checkpoint theo hướng dẫn của bản JDK và công cụ nền tảng. Xác nhận checkpoint hoàn tất, ghi lại metadata phát hành như phiên bản JDK, phiên bản ứng dụng, digest của image và cấu hình nền. Bảo vệ ảnh vì nó có thể chứa dữ liệu nhạy cảm trong bộ nhớ.

### Giai đoạn 5: Kiểm thử một lần restore

Trước khi mở rộng, restore một instance từ ảnh. Kiểm tra callback, kết nối, danh tính, cổng, readiness, log và một số request đại diện. Đây là bước xác nhận cơ bản rằng ảnh có thể được khôi phục trên môi trường đích.

### Giai đoạn 6: Kiểm thử nhiều lần restore

Tạo ít nhất hai instance từ cùng bộ ảnh theo cách được nền tảng hỗ trợ. Xác nhận chúng có PID/identity và tài nguyên riêng, không bind trùng ngoài dự kiến, không lặp side effect, và có thể cùng phục vụ request. Thử cả restore tuần tự lẫn đồng thời nếu production dự định sử dụng chế độ đồng thời.

### Giai đoạn 7: Phát hành và giám sát

Đưa ảnh vào kho artifact, áp dụng quyền truy cập và chính sách lưu trữ. Khi triển khai, điều phối số lượng restore theo năng lực hệ thống. Theo dõi restore duration, readiness duration, lỗi callback, tỷ lệ kết nối thành công, latency, throughput, CPU, memory và số lần retry.

## 14. Ví dụ thiết kế callback theo từng instance

Đoạn mã dưới đây minh họa một resource quản lý kết nối được tạo riêng sau mỗi lần restore. `ConnectionManager` là lớp ứng dụng giả định; việc đóng và tạo kết nối thực tế phải theo API của thư viện đang sử dụng.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class InstanceConnectionResource implements Resource {
    private final ConnectionManager manager;

    public InstanceConnectionResource(ConnectionManager manager) {
        this.manager = manager;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Ngừng nhận công việc mới và đóng kết nối cũ một cách an toàn.
        manager.quiesceAndClose();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Đọc cấu hình/danh tính của instance hiện tại rồi tạo kết nối mới.
        manager.reinitializeForCurrentInstance();
    }

    public interface ConnectionManager {
        void quiesceAndClose() throws Exception;
        void reinitializeForCurrentInstance() throws Exception;
    }
}
```

Trong mô hình nhiều tiến trình, mỗi lần restore có một bản `InstanceConnectionResource` trong tiến trình riêng. Callback `afterRestore(...)` chạy trong ngữ cảnh của từng tiến trình và cần khởi tạo tài nguyên phù hợp với instance đó.

Đây là ví dụ minh họa ranh giới trách nhiệm. Một ứng dụng thực tế cần bảo đảm resource được đăng ký đúng một lần trong mỗi tiến trình, callback an toàn khi lỗi, các thành phần phụ thuộc không sử dụng manager trong lúc đang đóng/mở và readiness chỉ thành công sau khi tái khởi tạo hoàn tất. Không nên đặt các thao tác nghiệp vụ có side effect vào callback này.

## 15. Kiểm thử tính độc lập của các tiến trình

Một phép thử nhiều restore cần chứng minh rằng các tiến trình không chỉ khởi động được mà còn hoạt động độc lập.

Giả sử tạo ba tiến trình A, B và C từ cùng ảnh. Có thể kiểm tra theo bảng sau:

| Nội dung | Kết quả mong đợi |
|---|---|
| Process ID và instance ID | Mỗi tiến trình có định danh riêng theo môi trường |
| Heap và bộ đếm nội bộ | Mỗi tiến trình có trạng thái runtime riêng; cập nhật ở A không tự thay đổi B hoặc C |
| Cổng và địa chỉ mạng | Không có xung đột ngoài thiết kế; mỗi instance nhận endpoint phù hợp |
| Database connection | Mỗi instance tạo hoặc sở hữu kết nối theo chính sách đã định |
| Message consumer | Mỗi consumer tham gia hệ thống theo group/partition và ID hợp lệ |
| Scheduler | Tác vụ chỉ chạy theo cơ chế điều phối đã chọn, không bị nhân bản ngoài ý muốn |
| Secret và token | Mỗi instance dùng credential còn hiệu lực và đúng phạm vi |
| Side effect | Không có email, giao dịch hoặc bản ghi bị lặp chỉ vì restore nhiều lần |
| Readiness | Chỉ thành công sau khi resource phục hồi và dependency sẵn sàng |

Hãy gửi request khác nhau đến từng instance và quan sát log/metric có gắn instance ID. Kiểm tra rằng thay đổi bộ nhớ cục bộ không lan sang tiến trình khác, đồng thời dữ liệu cần chia sẻ vẫn được đồng bộ qua kho dữ liệu hoặc dịch vụ bên ngoài đúng thiết kế.

Nên kiểm thử cả tình huống lỗi: một callback thất bại, database chưa sẵn sàng, token hết hạn, cổng bị chiếm, hoặc một restore bị dừng giữa chừng. Xác nhận bộ điều phối không đưa instance lỗi vào nhận traffic và có thể dọn tài nguyên đã cấp phát.

## 16. Hiệu năng và giới hạn khi nhân bản từ cùng ảnh

Checkpoint giúp giảm công việc lặp lại, nhưng restore nhiều tiến trình vẫn tiêu thụ tài nguyên. Mỗi tiến trình cần CPU để phục hồi và chạy callback, bộ nhớ cho trạng thái riêng, thread, file descriptor và kết nối đến các dịch vụ bên ngoài.

Các chỉ số cần đo gồm:

- Thời gian từ lúc yêu cầu restore đến khi tiến trình tồn tại.
- Thời gian từ lúc tiến trình tồn tại đến khi readiness thành công.
- CPU và RAM của từng instance và toàn node trong lúc restore.
- Số kết nối mới đến database, broker và các dịch vụ khác.
- Thời gian đến request đầu tiên và latency ở các request đầu.
- Throughput khi số lượng instance tăng.
- Tỷ lệ restore lỗi, callback lỗi và retry.

Đừng chỉ so sánh thời gian restore của một instance với cold start của một instance. Cần đo cả trường hợp mở rộng nhiều replica, vì tải đồng thời có thể khiến filesystem, CPU, memory bandwidth hoặc dịch vụ phụ thuộc trở thành nút thắt.

Nếu nền tảng hỗ trợ copy-on-write hoặc chia sẻ trang bộ nhớ, có thể ghi nhận mức tiết kiệm RAM trong phép đo. Tuy nhiên, khi mỗi tiến trình sửa dữ liệu, các trang có thể tách thành bản riêng. Dung lượng bộ nhớ thực tế còn phụ thuộc workload sau restore và không thể suy ra chỉ từ kích thước ảnh checkpoint.

## 17. Các lỗi thường gặp

**Dùng chung danh tính của tiến trình chuẩn bị.** Nhiều replica cùng đăng ký một instance ID, consumer ID hoặc hostname. Hãy tạo danh tính riêng sau restore.

**Khôi phục socket và cổng không phù hợp.** Nhiều tiến trình cố dùng cùng một socket hoặc bind cùng địa chỉ/cổng trong một namespace. Hãy đóng và tạo lại kết nối, đồng thời thiết kế namespace hoặc cấp cổng rõ ràng.

**Dùng chung connection pool cũ.** Kết nối đã hết hạn hoặc không còn hợp lệ được sao chép vào nhiều tiến trình. Hãy đóng pool trước checkpoint và tạo pool mới trong từng tiến trình restore.

**Chạy trùng scheduler hoặc consumer.** Các bản restore đều tiếp tục một lịch hoặc trạng thái consumer giống nhau. Hãy dùng cơ chế điều phối, partition và idempotency phù hợp.

**Dùng lại trạng thái ngẫu nhiên.** Bộ sinh số giả ngẫu nhiên được lưu trong checkpoint có thể bắt đầu từ cùng trạng thái ở mọi tiến trình. Hãy khởi tạo nguồn ngẫu nhiên và ID theo yêu cầu bảo mật, tính duy nhất.

**Đọc cấu hình riêng quá sớm.** Ứng dụng lưu hostname hoặc token của tiến trình chuẩn bị vào static field. Hãy làm mới cấu hình phụ thuộc instance sau restore.

**Restore đồng thời vượt năng lực dịch vụ.** Một đợt mở rộng tạo quá nhiều kết nối và request khởi tạo. Hãy giới hạn concurrency, chia đợt và dùng backoff.

**Cho rằng một ảnh có thể dùng ở mọi môi trường.** Khác biệt JDK, kernel, CPU, namespace, mount hoặc quyền có thể làm restore thất bại. Hãy cố định và xác minh ma trận tương thích.

**Cho rằng tiến trình đã restore là đã ready.** Callback hoặc kết nối thiết yếu chưa hoàn tất. Hãy gắn readiness với trạng thái phục hồi thực tế.

**Sửa ảnh gốc trong lúc nhiều restore đang chạy.** Một thao tác ghi hoặc dọn dẹp có thể làm hỏng lần restore khác. Hãy quản lý ảnh gốc bất biến và workspace riêng theo quy tắc của nền tảng.

## 18. Checklist trước khi dùng một ảnh cho nhiều tiến trình

- [ ] Bản dựng JDK CRaC và nền tảng có tài liệu xác nhận hỗ trợ nhiều lần restore theo cách dự kiến chưa?
- [ ] Ảnh checkpoint đã được tạo từ ứng dụng khởi tạo và warm-up đúng cách chưa?
- [ ] Bộ ảnh đầy đủ đã được đóng gói, kiểm tra checksum và quản lý phiên bản chưa?
- [ ] Các lần restore có workspace riêng nếu công cụ yêu cầu không?
- [ ] Mỗi tiến trình có PID, instance ID và cấu hình riêng chưa?
- [ ] Socket, cổng, DNS, HTTP client và kết nối outbound được tạo lại phù hợp chưa?
- [ ] Database pool, message consumer và credential được khởi tạo riêng hoặc điều phối đúng chưa?
- [ ] Thread nền, scheduler, timer và lock đã có quy trình dừng/khởi động chưa?
- [ ] Cache dùng chung, cache riêng và cache hết hạn đã được phân loại chưa?
- [ ] Nguồn ngẫu nhiên, token và ID duy nhất được xử lý an toàn sau restore chưa?
- [ ] Side effect được kiểm soát bằng idempotency hoặc cơ chế điều phối chưa?
- [ ] Đã thử ít nhất hai restore từ cùng ảnh, cả tuần tự và đồng thời nếu cần chưa?
- [ ] Bộ điều phối giới hạn số restore đồng thời và kiểm soát readiness chưa?
- [ ] Đã đo CPU, RAM, latency, throughput, kết nối và tỷ lệ lỗi khi mở rộng chưa?
- [ ] Ảnh checkpoint được bảo vệ như dữ liệu có thể chứa secret và thông tin người dùng chưa?

## Kết luận

Khôi phục nhiều tiến trình từ cùng một ảnh cho phép dùng một trạng thái ứng dụng đã chuẩn bị làm điểm xuất phát cho nhiều instance. Mỗi lần restore tạo một tiến trình độc lập với bộ nhớ và vòng đời riêng, dù trạng thái ban đầu có thể giống nhau. Mô hình này có thể giảm công việc khởi tạo lặp lại, nhưng chỉ hoạt động an toàn khi bản dựng JDK và nền tảng hỗ trợ quy trình restore nhiều lần.

Thiết kế quan trọng nhất là tách trạng thái nền có thể tái sử dụng khỏi trạng thái riêng của từng instance. Hãy làm mới danh tính, kết nối, secret, worker và lịch tác vụ sau restore; kiểm soát side effect; điều phối số lượng restore; và xác minh readiness trước khi nhận traffic. Khi các điều kiện này được đáp ứng và đo kiểm trên môi trường triển khai thật, một ảnh checkpoint có thể trở thành nền tảng để tạo nhiều instance Java nhất quán và nhanh chóng.
