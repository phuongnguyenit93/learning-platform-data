# Phân biệt Boot Volume, Block Volume và local NVMe

## Mục tiêu bài học

Một OCI Compute instance có thể sử dụng nhiều loại thiết bị lưu trữ. Trong hệ điều hành, chúng đều có thể xuất hiện dưới dạng ổ đĩa, nhưng vị trí vật lý, vai trò, vòng đời và cách phục hồi dữ liệu rất khác nhau.

Bài học thuộc chương **Block Volume và Boot Volume** của module **CLOUD_PROVIDERS_ORACLE**. Người học cần hiểu cách chọn lưu trữ cho hạ tầng OCI, đồng thời liên hệ với Compute, IAM, giám sát, chi phí và tính sẵn sàng.

Sau bài này, bạn có thể:

- Giải thích Boot Volume, Block Volume và local NVMe dùng để làm gì.
- Phân biệt lưu trữ dạng block, thiết bị gắn vào máy, filesystem và thư mục ứng dụng.
- Nhận diện dữ liệu nào cần tồn tại độc lập với instance và dữ liệu nào có thể tái tạo.
- Đọc các chỉ số dung lượng, IOPS, throughput và latency mà không suy luận chỉ từ tên thiết bị.
- Lập phương án backup, phục hồi, thay thế instance và kiểm soát tài nguyên lưu trữ còn lại.

Bài không đặt một shape, mức dung lượng, hiệu năng hay giá cụ thể làm mặc định. Các khả năng gắn volume và vòng đời local NVMe phải được kiểm tra theo đúng loại instance, shape, hệ điều hành và thao tác OCI dự kiến thực hiện.

## 1. Ba khái niệm khác nhau ở điểm nào?

**Boot Volume** là volume khởi động của instance trong mô hình khởi động từ Boot Volume của OCI. Nó chứa các thành phần cần thiết để khởi động và vận hành hệ điều hành, thường gồm phân vùng root cùng các thành phần boot liên quan.

**Block Volume** là volume lưu trữ dạng block mà bạn tạo và gắn vào instance để sử dụng theo nhu cầu. Nó thường chứa dữ liệu ứng dụng, filesystem dữ liệu hoặc dữ liệu của phần mềm có cơ chế sử dụng block device riêng.

**Local NVMe** là lưu trữ NVMe gắn cục bộ với máy chủ Compute, có trên những shape cung cấp phần cứng này. Nó không phải một Block Volume độc lập để bạn tháo khỏi máy chủ rồi gắn sang một instance khác theo quy trình thông thường của dịch vụ Block Volume.

| Tiêu chí | Boot Volume | Block Volume | Local NVMe |
| --- | --- | --- | --- |
| Vai trò chính | Khởi động và chứa hệ điều hành | Lưu trữ block bổ sung theo nhu cầu | Lưu trữ cục bộ của máy chủ trên shape hỗ trợ |
| Quan hệ với Compute | Được dùng làm volume khởi động | Được gắn vào instance bằng attachment phù hợp | Gắn với phần cứng và vòng đời của môi trường Compute |
| Có thể chứa dữ liệu ứng dụng? | Có thể, nhưng cần cân nhắc tách dữ liệu | Có, đây là nhu cầu phổ biến | Có, nếu chấp nhận và xử lý đúng rủi ro vòng đời |
| Tồn tại độc lập với instance | Có thể giữ lại, tùy chính sách và thao tác | Có vòng đời riêng, vẫn có thể bị xóa theo thao tác/chính sách | Không coi là tài nguyên độc lập có thể chuyển máy như volume dịch vụ |
| Bảo vệ dữ liệu | Backup và kế hoạch phục hồi cho boot | Backup, sao chép và kế hoạch phục hồi phù hợp | Tái tạo dữ liệu hoặc sao chép/backup sang nơi bền vững khác |
| Hiệu năng | Theo cấu hình volume và đường I/O | Theo cấu hình volume, attachment và giới hạn instance | Theo phần cứng cục bộ, shape và workload |

“Boot” mô tả vai trò khởi động; “block” mô tả cách cung cấp lưu trữ ở mức khối; “local NVMe” mô tả công nghệ và vị trí kết nối. Đây không phải ba cấp chất lượng được xếp từ thấp đến cao.

## 2. Từ thiết bị lưu trữ đến dữ liệu ứng dụng

### 2.1. Lưu trữ block chưa phải một thư mục

Dịch vụ lưu trữ block cung cấp một dải khối có thể đọc/ghi. Để một ứng dụng thông thường lưu file lên đó, hệ điều hành cần nhận thiết bị và có cấu trúc lưu trữ phù hợp.

Một luồng điển hình:

```text
Volume trong OCI
  -> Attachment giữa volume và instance
  -> Thiết bị mà hệ điều hành nhận diện
  -> Phân vùng hoặc lớp quản lý volume, nếu sử dụng
  -> Filesystem
  -> Mount point
  -> Thư mục dữ liệu của ứng dụng
```

**Attach không đồng nghĩa mount.** Một volume đã được OCI gắn vào instance vẫn có thể chưa được hệ điều hành sử dụng hoặc chưa được mount vào đúng nơi ứng dụng cần.

Một Block Volume mới tạo trống và một volume phục hồi từ backup cũng khác nhau: volume phục hồi có thể đã chứa phân vùng và filesystem. Không xử lý mọi thiết bị mới xuất hiện như một ổ trống cần khởi tạo lại.

Một số phần mềm dùng block device thông qua cơ chế quản lý riêng thay vì mount thành filesystem thông thường. Khi đó phải làm theo kiến trúc lưu trữ của phần mềm, không áp dụng máy móc luồng tạo filesystem.

### 2.2. Mount point quyết định ứng dụng thực sự ghi đi đâu

Giả sử dữ liệu dự kiến nằm ở `/srv/app-data`, được mount từ một Block Volume. Nếu mount thất bại nhưng thư mục vẫn tồn tại trên filesystem root, ứng dụng có thể tiếp tục ghi vào Boot Volume.

Hậu quả có thể gồm:

- Boot Volume đầy dù Block Volume dữ liệu còn trống.
- Người vận hành backup nhầm nơi và bỏ sót dữ liệu vừa ghi.
- Khi volume được mount trở lại, các file nằm bên dưới mount point bị che khuất khỏi đường dẫn đang nhìn thấy.
- Instance thay thế không có những file vô tình được ghi lên boot của máy cũ.

Cần kiểm tra mount và đặt điều kiện khởi động ứng dụng phụ thuộc vào filesystem dữ liệu theo cơ chế quản lý dịch vụ của hệ điều hành. Đừng chỉ kiểm tra rằng thư mục tồn tại.

### 2.3. Tên thiết bị không đủ để kết luận nguồn lưu trữ

Một đường dẫn như `/dev/sdb` không phải bằng chứng rằng đó luôn là Block Volume dữ liệu. Thứ tự và tên thiết bị có thể thay đổi theo hệ điều hành, attachment hoặc quá trình khởi động.

Tương tự, tên chứa `nvme` mô tả giao diện thiết bị mà hệ điều hành nhìn thấy, chưa đủ để kết luận dữ liệu có vòng đời local NVMe của một shape cụ thể. Cần đối chiếu cả cấu hình OCI, thông tin attachment và định danh thiết bị phù hợp.

Khi cấu hình mount lâu dài, dùng định danh ổn định được hệ điều hành và kiểu attachment hỗ trợ. Nếu sao chép hoặc phục hồi volume, cũng cần kiểm tra định danh filesystem để tránh giả định rằng mọi bản sao đều có UUID khác nhau.

## 3. Boot Volume: nơi hệ điều hành khởi động

### 3.1. Thành phần thường đặt trên boot

Boot Volume thường chứa:

- Bootloader và các phân vùng khởi động liên quan.
- Hệ điều hành, kernel, package và thư viện nền.
- Cấu hình máy, agent vận hành và dịch vụ hệ thống.
- Log, file tạm hoặc ứng dụng nếu chưa tách ra filesystem khác.

Image là nguồn để tạo môi trường máy ban đầu, còn Boot Volume là tài nguyên lưu trữ được instance sử dụng khi chạy theo mô hình này. Image không thay thế cho backup dữ liệu phát sinh trong quá trình hoạt động.

Ví dụ, một image có JDK và ứng dụng không tự chứa các file người dùng tải lên sau khi instance đã chạy ba tháng.

### 3.2. Có nên chứa dữ liệu nghiệp vụ trên boot?

Về mặt kỹ thuật, hệ điều hành có thể ghi dữ liệu lên filesystem nằm trên Boot Volume. Tuy nhiên, việc trộn hệ điều hành với dữ liệu nghiệp vụ tạo ra sự phụ thuộc vận hành:

- Nâng cấp hoặc thay máy dễ phải xử lý đồng thời cả hệ điều hành lẫn dữ liệu.
- Log tăng đột biến có thể làm đầy filesystem dùng cho hoạt động của hệ điều hành.
- Nhu cầu dung lượng và backup của hệ điều hành khác nhu cầu của dữ liệu nghiệp vụ.
- Quy trình tạo lại máy từ image trở nên khó hơn nếu còn dữ liệu duy nhất trên máy cũ.

Với hệ thống nhỏ, cách bố trí chung có thể chấp nhận được nếu có chủ đích và đã thiết kế backup/restore. Với hệ thống cần thay thế instance thường xuyên, tách dữ liệu giúp quản lý vòng đời rõ ràng hơn.

Tách dữ liệu không có nghĩa chỉ đổi tên thư mục. Cần xác nhận thư mục thực sự nằm trên volume dữ liệu hoặc dịch vụ lưu trữ đã chọn.

### 3.3. Boot Volume có vòng đời cần quản lý riêng

Khi kết thúc instance, cách xử lý Boot Volume phụ thuộc lựa chọn giữ/xóa và các công cụ quản lý vòng đời đang dùng. Không suy ra rằng xóa instance luôn xóa boot, hoặc luôn giữ boot.

Nếu giữ lại Boot Volume, dữ liệu vẫn cần được quản lý về quyền truy cập, backup, chi phí và khả năng phục hồi. Nếu xóa boot mà không có bản phục hồi phù hợp, image ban đầu không bảo đảm khôi phục được mọi thay đổi sau này.

Có các quy trình phục hồi và bảo trì liên quan đến Boot Volume, nhưng chúng phải đáp ứng điều kiện về vị trí, trạng thái instance, image và khả năng hỗ trợ của OCI. Không thao tác với boot như một data volume thông thường khi hệ điều hành còn đang phụ thuộc vào nó.

## 4. Block Volume: dữ liệu có vòng đời riêng

### 4.1. Tách dữ liệu khỏi vòng đời máy chủ

Một lợi ích quan trọng của Block Volume là khả năng quản lý dữ liệu độc lập hơn với instance. Khi máy ứng dụng cần thay thế, bạn có thể thiết kế quy trình giữ volume dữ liệu và kết nối nó với môi trường thay thế đáp ứng điều kiện gắn volume.

Các trường hợp phổ biến:

- Dữ liệu ứng dụng tự quản trị cần filesystem riêng.
- Dữ liệu và log của phần mềm cơ sở dữ liệu tự vận hành.
- Bộ dữ liệu làm việc cần tồn tại qua nhiều lần thay instance.
- Dung lượng tăng độc lập với nhu cầu CPU/RAM.

Block Volume không tự biến ứng dụng thành hệ thống có tính sẵn sàng cao. Một filesystem chỉ được một máy phục vụ vẫn có thể cần thời gian gắn lại, kiểm tra và khởi động ứng dụng khi máy đó gặp lỗi.

### 4.2. Địa điểm và kiểu attachment có ràng buộc

Volume và instance phải thỏa điều kiện vị trí gắn của dịch vụ, điển hình là cùng availability domain đối với việc gắn volume thông thường. Không coi volume như một ổ có thể gắn trực tiếp vào mọi region hoặc availability domain tùy ý.

Nếu cần phục hồi ở vị trí khác, có thể phải dùng luồng backup/restore, sao chép hoặc replication phù hợp thay vì attachment trực tiếp. Khả năng hỗ trợ và phạm vi của từng cơ chế cần được xác nhận riêng.

Các kiểu attachment như paravirtualized hoặc iSCSI có yêu cầu hệ điều hành và thao tác kết nối khác nhau. Thành công ở phía OCI chưa đủ chứng minh filesystem đã sẵn sàng trong máy khách.

### 4.3. Gắn cùng một volume cho nhiều máy không tạo ra filesystem dùng chung an toàn

Một số cấu hình hỗ trợ nhiều attachment với chế độ truy cập phù hợp. Điều đó không có nghĩa có thể mount read/write một filesystem thông thường trên nhiều instance rồi ghi đồng thời.

Để nhiều máy cùng sử dụng một block device an toàn, cần kiến trúc ứng dụng, filesystem hoặc phần mềm quản lý cụm hỗ trợ truy cập đồng thời và điều phối nhất quán. Nếu thiếu cơ chế này, dữ liệu có thể bị hỏng dù mọi attachment đều được tạo thành công.

Nếu ứng dụng cần chia sẻ file qua mạng, hãy đánh giá dịch vụ file storage hoặc giải pháp chia sẻ phù hợp. Block storage và file storage giải quyết các lớp giao diện khác nhau.

### 4.4. Dung lượng trong OCI và dung lượng filesystem là hai lớp

Khi tăng dung lượng volume, hệ điều hành còn có thể cần nhận lại kích thước thiết bị, mở rộng phân vùng hoặc lớp quản lý volume, rồi mở rộng filesystem theo cách được hỗ trợ.

Không kết luận tác vụ đã hoàn thành chỉ vì Console hiển thị dung lượng mới. Ngược lại, cách thu nhỏ hoặc chuyển dữ liệu không được giả định là phép đảo ngược đơn giản của tăng dung lượng; cần chọn quy trình phù hợp với dịch vụ và filesystem.

## 5. Local NVMe: hiệu năng cục bộ đi kèm vòng đời máy chủ

### 5.1. Local nghĩa là dữ liệu gắn với phần cứng Compute

Trên shape có local NVMe, ứng dụng sử dụng thiết bị lưu trữ cục bộ của máy chủ. Điều này có thể mang lại đặc điểm độ trễ và throughput hữu ích, nhưng thiết bị không có mô hình tài nguyên độc lập như một Block Volume từ xa.

Các workload có thể phù hợp:

- Cache có thể nạp lại từ nguồn dữ liệu chính.
- File trung gian của batch hoặc pipeline xử lý dữ liệu.
- Scratch space cho tác vụ tính toán.
- Thành phần của hệ thống đã có cơ chế sao chép và phục hồi dữ liệu được kiểm chứng.

Cần tính cả thời gian dựng lại cache hoặc dữ liệu trung gian khi mất máy. Một thiết kế chạy nhanh trong trạng thái ổn định vẫn có thể phục hồi quá chậm nếu phải tải lại lượng dữ liệu lớn.

### 5.2. Không suy luận vòng đời từ một lần reboot thành công

Local NVMe không có một quy tắc đơn giản kiểu “mọi lần reboot đều mất dữ liệu”. Hành vi phụ thuộc shape và thao tác thực tế. Nhưng một lần dữ liệu còn sau reboot cũng không chứng minh nó tồn tại qua stop/start, thay shape, di chuyển máy chủ, bảo trì hoặc terminate.

Trước khi dùng, lập bảng cho đúng môi trường:

| Sự kiện | Câu hỏi phải xác nhận |
| --- | --- |
| Reboot hệ điều hành | Thiết bị và dữ liệu được giữ như thế nào theo loại instance? |
| Stop/start | Phần cứng cũ có tiếp tục được dùng, dữ liệu cục bộ có được bảo toàn không? |
| Thay đổi shape hoặc thay instance | Có còn truy cập được các thiết bị cục bộ trước đó không? |
| Bảo trì hoặc lỗi máy chủ | Phương án khôi phục dữ liệu khi máy cũ không truy cập được là gì? |
| Terminate hoặc scale-in | Dữ liệu nào cần được lưu ở nơi khác trước khi máy bị loại bỏ? |

Khi yêu cầu nghiệp vụ là “không được mất bản dữ liệu duy nhất nếu máy chủ biến mất”, không dùng local NVMe như nơi bảo vệ duy nhất.

### 5.3. Dùng local NVMe cho dữ liệu có thể tái tạo

Ví dụ một tác vụ xử lý ảnh:

```text
Ảnh gốc ở nơi lưu trữ bền vững
  -> tải về local NVMe để giải mã và xử lý
  -> ghi kết quả cuối vào nơi lưu trữ bền vững
  -> xác nhận tác vụ hoàn thành
  -> có thể xóa file trung gian
```

Nếu instance mất giữa chừng, hệ thống có thể nhận lại tác vụ và xử lý từ ảnh gốc. Cần kiểm soát việc ghi kết quả trùng hoặc tác dụng phụ khi retry.

Ngược lại, nếu ứng dụng xác nhận upload thành công ngay khi file chỉ nằm trên local NVMe mà chưa có bản bền vững, hệ thống có thể mất dữ liệu đã được báo thành công cho người dùng.

## 6. Hiệu năng: đọc đúng dung lượng, IOPS, throughput và latency

### 6.1. Bốn đại lượng khác nhau

| Đại lượng | Mô tả | Ví dụ câu hỏi |
| --- | --- | --- |
| Dung lượng | Tổng lượng dữ liệu có thể lưu | Có đủ chỗ cho dữ liệu, log và tăng trưởng không? |
| IOPS | Số thao tác I/O hoàn thành trong một giây | Có xử lý được nhiều truy cập nhỏ không? |
| Throughput | Lượng dữ liệu truyền trong một giây | Đọc/ghi file lớn có đủ nhanh không? |
| Latency | Thời gian hoàn tất một thao tác | Mỗi lần đọc/ghi có làm chậm giao dịch không? |

Với giả định cùng kích thước I/O và chưa xét overhead:

```text
Throughput xấp xỉ = IOPS x kích thước mỗi I/O

20.000 IOPS x 8 KiB = 160.000 KiB/s
                         = 156,25 MiB/s
```

Một workload đọc các khối 1 MiB ở 300 MiB/s chỉ cần khoảng 300 thao tác mỗi giây theo mô hình đơn giản. Vì vậy, một con số IOPS lớn không đủ để kết luận mọi workload sẽ nhanh.

### 6.2. Nút thắt có thể nằm ngoài volume

Hiệu năng quan sát được chịu ảnh hưởng của cả đường I/O:

- Mức hiệu năng và dung lượng volume theo cấu hình dịch vụ.
- Giới hạn của shape và tài nguyên instance được cấp phát.
- Kiểu attachment, driver và cấu hình hệ điều hành.
- Đường kết nối của lưu trữ từ xa.
- Kích thước I/O, độ sâu hàng đợi, đọc/ghi tuần tự hay ngẫu nhiên.
- Filesystem, cache, cơ chế đồng bộ dữ liệu và cách ứng dụng truy cập.

Tăng tài nguyên volume không bảo đảm cải thiện nếu giới hạn nằm ở phía Compute hoặc ứng dụng. Tương tự, local NVMe nhanh không giải quyết được một request chủ yếu chờ cơ sở dữ liệu ở xa.

Kết quả thử nghiệm cần mô tả điều kiện đo, nhất là cache và yêu cầu ghi bền vững. Đọc dữ liệu đã có trong RAM không phải phép đo trực tiếp tốc độ ổ đĩa.

### 6.3. Boot cũng có thể là nơi gây nghẽn

Nếu log và file tạm của ứng dụng cùng nằm trên filesystem root, một đợt ghi lớn có thể ảnh hưởng các hoạt động khác của hệ điều hành. Giám sát Boot Volume không chỉ là theo dõi đủ chỗ cài package; cần quan sát dung lượng trống, độ trễ và hành vi I/O khi ứng dụng chạy.

Tách filesystem dữ liệu hoặc log khi có lý do giúp phân định nhu cầu và giảm việc cạnh tranh trên cùng volume. Tuy nhiên, các volume vẫn có thể cùng chịu giới hạn phía instance, nên việc tách không tự động nhân đôi năng lực I/O của máy.

## 7. Độ bền dữ liệu, backup và tính nhất quán

### 7.1. Ba mục tiêu không thể dùng thay nhau

- **Độ bền lưu trữ**: bảo vệ dữ liệu trước những lỗi trong phạm vi mà dịch vụ lưu trữ thiết kế để xử lý.
- **Backup và phục hồi**: quay lại một bản dữ liệu phù hợp sau xóa nhầm, hỏng logic hoặc sự cố khác.
- **Tính sẵn sàng**: tiếp tục phục vụ hoặc khôi phục dịch vụ trong thời gian đáp ứng yêu cầu.

Volume có độ bền cao vẫn có thể chứa dữ liệu đã bị ứng dụng ghi sai. Giữ lại volume sau khi máy hỏng vẫn có thể cần thời gian phục hồi dịch vụ. Một bản backup còn nguyên nhưng chưa từng restore cũng chưa chứng minh đạt mục tiêu khôi phục.

### 7.2. Backup boot không thay thế backup dữ liệu ở volume khác

Nếu hệ điều hành ở Boot Volume còn dữ liệu DB ở hai Block Volume, chỉ backup boot không bảo vệ được hai volume dữ liệu. Tương tự, backup volume dữ liệu không tự bao gồm cấu hình runtime nằm ở boot hoặc secrets được quản lý trong dịch vụ khác.

Cần lập danh sách những thành phần cần để phục hồi toàn bộ dịch vụ:

| Thành phần | Nguồn phục hồi cần xác định |
| --- | --- |
| Hệ điều hành và ứng dụng | Image, cấu hình triển khai hoặc backup boot phù hợp |
| Dữ liệu nghiệp vụ | Backup/replication và cơ chế phục hồi của dữ liệu |
| Dữ liệu trải trên nhiều volume | Bản phục hồi có quan hệ thời điểm và tính nhất quán phù hợp |
| Cấu hình, quyền, mạng | Cấu hình hạ tầng, policy và tài liệu vận hành |
| Khóa mã hóa và secrets | Dịch vụ quản lý cùng quyền truy cập cần thiết |
| Dữ liệu trên local NVMe | Nguồn để tái tạo hoặc bản sao ở nơi khác |

### 7.3. Bản sao volume chưa chắc nhất quán ở mức ứng dụng

Hệ điều hành, database và ứng dụng có thể giữ dữ liệu trong bộ nhớ hoặc ghi qua nhiều bước. Một bản backup ở mức block không tự hiểu một giao dịch nghiệp vụ đã hoàn thành hay chưa.

Với phần mềm cơ sở dữ liệu tự quản trị, cần dùng quy trình backup/restore được phần mềm hỗ trợ, kết hợp quiesce hoặc cơ chế phối hợp khi cần. Nếu dữ liệu trải trên nhiều volume, cần đánh giá sự nhất quán giữa các volume và trạng thái giao dịch.

Cơ chế backup nhóm volume, khi phù hợp, hỗ trợ phối hợp ở lớp lưu trữ nhưng không tự thay thế yêu cầu application-consistent backup. Không coi backup là bản chụp đầy đủ của bộ nhớ tiến trình đang chạy.

### 7.4. Đặt mục tiêu và thử phục hồi

Hai câu hỏi cần trả lời:

- **RPO**: chấp nhận mất tối đa bao nhiêu dữ liệu theo thời gian?
- **RTO**: cần phục hồi dịch vụ trong bao lâu?

Ví dụ, nếu dữ liệu nghiệp vụ phát sinh liên tục nhưng chỉ có bản backup mỗi ngày, yêu cầu mất không quá vài phút dữ liệu cần thêm cơ chế phù hợp; không thể kết luận được đáp ứng chỉ vì đã có backup policy.

Một lần thử phục hồi nên kiểm tra cả dữ liệu, khả năng khởi động ứng dụng, quyền, kết nối và thời gian hoàn tất. Với cache dùng local NVMe, thời gian nạp lại cache cũng thuộc kế hoạch phục hồi.

## 8. Bảo mật, IAM và chi phí

### 8.1. Mã hóa và quyền truy cập là các lớp khác nhau

OCI cung cấp mã hóa dữ liệu lưu trữ cho Boot Volume và Block Volume, với lựa chọn quản lý khóa theo khả năng của dịch vụ. Cần phân biệt mã hóa at-rest với mã hóa trên đường truyền; không suy ra lớp này chỉ từ việc lớp kia đang bật.

Mã hóa at-rest không ngăn ứng dụng đã có quyền đọc dữ liệu sau khi volume được gắn và mở cho hệ điều hành sử dụng. Cần phối hợp:

- IAM cho thao tác tạo, gắn, xóa và quản lý backup/volume.
- Quyền trên khóa khi dùng khóa do khách hàng quản lý.
- Quyền hệ điều hành, tài khoản dịch vụ và quyền truy cập file.
- Quản lý secrets và kiểm soát phần mềm có thể đọc dữ liệu.

Không coi NSG hoặc security list của ứng dụng là cơ chế duy nhất quyết định ai có thể quản lý volume qua API OCI. Quyền điều khiển tài nguyên và quyền đọc dữ liệu trong máy khách là các lớp khác nhau.

### 8.2. Volume còn lại vẫn cần được quản lý

Dừng instance không có nghĩa các Boot Volume, Block Volume và backup liên quan đều hết chi phí. Tương tự, một volume đã detach vẫn là tài nguyên cần quản lý.

Theo dõi ít nhất:

- Dung lượng và mức hiệu năng được cấu hình.
- Volume còn giữ sau khi kết thúc instance hoặc thay môi trường.
- Backup, retention và các bản sao được tạo ra.
- Chủ sở hữu, mục đích và yêu cầu giữ dữ liệu.

Tag và compartment giúp tổ chức trách nhiệm, nhưng không thay thế chính sách xóa và giữ dữ liệu. Trước khi loại bỏ một tài nguyên, phải biết nó có còn là bản dữ liệu cần thiết cho phục hồi hay không.

Với local NVMe, chi phí và khả năng cung cấp gắn với lựa chọn Compute shape. Không mặc định nó là tài nguyên bổ sung miễn phí chỉ vì không quản lý như một Block Volume riêng.

## 9. Ví dụ: bố trí lưu trữ cho một ứng dụng Java trên OCI

### 9.1. Bối cảnh

Một ứng dụng Java nhận file tài liệu, xử lý nội dung và lưu kết quả nghiệp vụ vào dịch vụ cơ sở dữ liệu Oracle triển khai riêng. Ứng dụng có thể được thay thế hoặc scale-in khi tải giảm.

Các nhóm dữ liệu:

1. Hệ điều hành, JDK, agent và chương trình ứng dụng.
2. File tài liệu người dùng đã được xác nhận tải lên thành công.
3. File giải nén và dữ liệu trung gian trong lúc xử lý.
4. Log dùng để chẩn đoán và kiểm toán theo yêu cầu.
5. Cấu hình và secrets để truy cập các dịch vụ.

### 9.2. Một phương án có thể đánh giá

| Nhóm dữ liệu | Nơi bố trí minh họa | Lý do và điều kiện |
| --- | --- | --- |
| Hệ điều hành và phần mềm nền | Boot Volume | Có quy trình tạo lại từ image/cấu hình và quản lý thay đổi |
| File đã xác nhận với người dùng | Nơi lưu trữ bền vững phù hợp, không chỉ ổ cục bộ máy xử lý | Tồn tại khi instance bị thay hoặc scale-in |
| Dữ liệu cần filesystem riêng của một instance | Block Volume nếu kiến trúc thực sự cần | Quản lý mount, backup và quy trình gắn lại khi thay máy |
| File trung gian có thể tạo lại | Local NVMe nếu shape có và hiệu năng cần thiết | Có nguồn dữ liệu chính và cơ chế retry |
| Log | Bộ đệm cục bộ có giới hạn, chuyển đến nơi lưu tập trung theo yêu cầu | Không phụ thuộc hoàn toàn vào máy sẽ bị loại bỏ |
| Cấu hình và secrets | Cơ chế quản lý cấu hình/secrets phù hợp | Không dựa vào một file duy nhất chép tay trên boot |

Block Volume là một lựa chọn cho dữ liệu dạng block, không phải đáp án cho mọi loại dữ liệu. Nếu nhiều instance cần truy cập cùng file, cần chọn giao diện lưu trữ và mô hình đồng thời phù hợp thay vì tự gắn cùng một filesystem read/write lên tất cả máy.

Việc ứng dụng truy cập cơ sở dữ liệu Oracle không có nghĩa phải mua local NVMe cho máy ứng dụng. Cần đo nơi phát sinh I/O và độ trễ thực sự trước khi chọn phần cứng.

### 9.3. Tình huống lỗi và kết quả cần có

- **Máy xử lý biến mất giữa tác vụ**: file gốc vẫn còn; tác vụ có thể được nhận lại và xử lý không gây kết quả trùng sai.
- **Boot đầy do log**: phát hiện qua giám sát; log có giới hạn và không làm mất bản dữ liệu nghiệp vụ duy nhất.
- **Volume dữ liệu chưa mount**: ứng dụng không tiếp tục ghi nhầm vào root như thể mọi thứ đã sẵn sàng.
- **Instance bị thay thế**: có thể tạo lại phần mềm, kết nối nguồn dữ liệu và khôi phục dịch vụ theo kế hoạch.
- **Xóa nhầm file nghiệp vụ**: có phương án phục hồi ngoài việc giữ lại filesystem đang phản ánh thao tác xóa.

## 10. Thực hành đọc thông tin lưu trữ trong Linux

Nếu đã có một máy Linux thử nghiệm được phép sử dụng, các lệnh đọc sau giúp đối chiếu thiết bị với filesystem. Chúng không tạo, định dạng hoặc mount volume; một số công cụ cần được cài sẵn.

```bash
# Xem thiết bị, filesystem, UUID và nơi mount
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,UUID

# Xác định filesystem đang chứa đường dẫn root
findmnt -T /

# Xem dung lượng và loại filesystem đã mount
df -hT

# Thay đường dẫn này bằng thư mục dữ liệu thực sự tồn tại trên máy
findmnt -T /srv/app-data
```

Cách đọc kết quả:

1. Dùng `findmnt -T /` xác định nguồn của filesystem root.
2. Dùng `lsblk` để xem quan hệ giữa thiết bị, phân vùng và các lớp lưu trữ, nếu có.
3. Dùng `findmnt -T` với đường dẫn dữ liệu để xác định filesystem đang chứa nó.
4. So sánh với filesystem root: dữ liệu có thật sự nằm trên volume riêng không?
5. Đối chiếu với thông tin Boot Volume, Block Volume và attachment trong OCI bằng định danh được hỗ trợ.
6. Kiểm tra dung lượng filesystem bằng `df`, không chỉ kích thước thiết bị trong `lsblk`.

Nếu thư mục dữ liệu chưa có mount riêng, `findmnt -T` có thể trả về filesystem cha đang chứa thư mục. Đó là thông tin quan trọng để phát hiện việc ghi vào boot ngoài dự kiến.

Kết quả từ hệ điều hành không xác nhận đầy đủ chính sách giữ/xóa, backup, mức hiệu năng hay quy tắc bảo toàn local NVMe. Những thuộc tính đó cần đối chiếu ở lớp dịch vụ OCI và cấu hình vận hành.

Hoàn thành phiếu kiểm kê sau:

| Nội dung | Kết quả cần ghi |
| --- | --- |
| Đường dẫn hoặc thiết bị | Root, dữ liệu ứng dụng, log, cache, file tạm |
| Loại tài nguyên thực tế | Boot Volume, Block Volume, local NVMe hoặc loại khác |
| Định danh | Volume/attachment trong OCI và định danh thiết bị trong máy khách |
| Vòng đời | Khi reboot, thay máy, stop/start, terminate hoặc scale-in |
| Nhu cầu hiệu năng | Dung lượng, IOPS, throughput, latency và cách đo |
| Tính bền vững | Bản dữ liệu chính ở đâu, có thể tái tạo được không |
| Bảo vệ và phục hồi | Backup, nguồn tái tạo, RPO/RTO và bằng chứng restore |
| Quyền và chi phí | Chủ sở hữu, IAM, khóa, retention và tài nguyên còn giữ |

## 11. Những nhầm lẫn thường gặp

| Nhận định | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Boot Volume chỉ có hệ điều hành nên không cần quan tâm dữ liệu” | Ứng dụng, log hoặc upload có thể đang ghi lên root | Kiểm tra đường dẫn và filesystem thực tế |
| “Attach thành công là ứng dụng dùng được ngay” | Còn thiết bị, filesystem, mount và quyền | Xác minh đầy đủ từ attachment đến đường dẫn ứng dụng |
| “Block Volume là ổ chia sẻ file cho mọi máy” | Block device không tự điều phối ghi đồng thời | Dùng cơ chế đồng thời hoặc dịch vụ file phù hợp |
| “Local NVMe luôn mất dữ liệu khi reboot” | Hành vi còn phụ thuộc môi trường và thao tác | Kiểm tra vòng đời cụ thể; không dùng suy đoán |
| “Local NVMe còn dữ liệu sau reboot thì có thể giữ bản duy nhất” | Không chứng minh khả năng sống qua mất máy hoặc terminate | Bảo vệ dữ liệu ở nơi khác hoặc có thể tái tạo |
| “Volume bền vững thì không cần backup” | Không xử lý xóa nhầm hoặc hỏng dữ liệu logic | Thiết kế backup và thử phục hồi |
| “Backup boot bảo vệ toàn bộ máy và dữ liệu” | Dữ liệu có thể ở các volume/dịch vụ khác | Kiểm kê từng thành phần cần phục hồi |
| “Tăng volume là filesystem tự có thêm chỗ trong mọi trường hợp” | Các lớp thiết bị/phân vùng/filesystem có thể cần thao tác riêng | Xác minh dung lượng ở từng lớp |
| “Thiết bị có tên NVMe thì chắc chắn là local storage” | Tên giao diện không đủ mô tả vòng đời dịch vụ | Đối chiếu nguồn tài nguyên và cấu hình OCI |
| “Xóa instance là kết thúc mọi chi phí lưu trữ” | Volume và backup có thể vẫn còn | Quản lý vòng đời từng tài nguyên |

## 12. Tự kiểm tra

1. Boot Volume và Block Volume khác nhau chủ yếu ở vai trò nào? Vì sao cả hai vẫn cần kế hoạch phục hồi?
2. Một ứng dụng ghi vào `/srv/app-data` nhưng `findmnt -T` cho thấy đường dẫn nằm trên filesystem root. Điều gì có thể đã xảy ra?
3. Vì sao không thể suy ra loại lưu trữ OCI chỉ từ tên `/dev/sdb` hoặc một tên thiết bị chứa `nvme`?
4. Một Block Volume được attach vào hai instance có đủ điều kiện để mount read/write một filesystem thông thường trên cả hai không?
5. Khi nào local NVMe là lựa chọn hợp lý cho file trung gian? Phải hoàn tất bước nào trước khi xác nhận kết quả với người dùng?
6. Vì sao một bản backup dữ liệu trên volume chưa chắc nhất quán ở mức giao dịch ứng dụng?
7. Tại sao 20.000 IOPS với I/O 8 KiB chỉ tương đương khoảng 156,25 MiB/s theo phép tính đơn giản?
8. Sau khi tăng dung lượng volume, cần kiểm tra những lớp nào để ứng dụng thực sự có thêm chỗ lưu?
9. Nếu instance bị terminate, thông tin nào quyết định Boot Volume và Block Volume được giữ hay bị xóa?
10. Phiếu kiểm kê cần ghi gì để người khác phục hồi ứng dụng khi máy chủ cũ không còn truy cập được?

Một phương án lưu trữ có thể vận hành được phải chỉ rõ dữ liệu nằm ở đâu, tồn tại qua những sự kiện nào, được bảo vệ bằng cách nào và cần bao lâu để phục hồi. Tên thiết bị hoặc mức hiệu năng cao không thay thế cho những quyết định này.
