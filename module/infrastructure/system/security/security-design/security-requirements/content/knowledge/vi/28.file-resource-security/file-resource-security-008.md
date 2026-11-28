# Archive extraction safety — Đặc tả yêu cầu giải nén an toàn

## 1. Mục tiêu bảo mật của giải nén

**Archive extraction safety** là tập yêu cầu bảo đảm việc đọc và giải nén một gói dữ liệu không làm ghi ra ngoài phạm vi được phép, ghi đè dữ liệu, tạo đối tượng hệ thống không được phép hoặc tiêu thụ tài nguyên vượt giới hạn.

Một archive là đầu vào không tin cậy. Tên từng mục, cấu trúc thư mục, thuộc tính liên kết, loại đối tượng, kích thước khai báo và nội dung sau giải nén đều cần được kiểm soát. Việc nhận diện tệp là ZIP hoặc một định dạng được phép chưa chứng minh quá trình giải nén an toàn.

Trong module chuyển mô hình đe dọa thành yêu cầu bảo mật, mục tiêu là trả lời:

> Archive nào được phép, từng mục được tạo ở đâu, thuộc loại gì, dùng tối đa bao nhiêu tài nguyên, khi lỗi phải xử lý thế nào và khi nào kết quả được đưa vào sử dụng?

Sau bài học, người đọc có thể:

- Đặc tả ranh giới đường dẫn và loại đối tượng được phép tạo.
- Xử lý tên mơ hồ, liên kết, trùng tên và thay đổi đường dẫn trong khi ghi.
- Đặt giới hạn dựa trên dữ liệu thực sự giải nén, thay vì chỉ tin metadata.
- Quy định cách ly, dọn dữ liệu lỗi và công bố một kết quả đầy đủ.
- Liên kết yêu cầu với kiến trúc và bằng chứng kiểm thử.

Bài học dùng hồ sơ ZIP giả định cho chức năng nhập bộ tài liệu. Các giới hạn số là ví dụ để minh họa cách viết yêu cầu đo được, không phải giá trị mặc định cho mọi ứng dụng.

## 2. Bề mặt tấn công nằm trong từng mục archive

Một mục trong archive có thể chứa tên tương đối, đường dẫn tuyệt đối, thông tin liên kết, quyền truy cập hoặc một khối dữ liệu có kích thước sau giải nén lớn hơn nhiều kích thước truyền.

| Kịch bản rủi ro | Tác động | Yêu cầu cần hình thành |
|---|---|---|
| Tên mục đi ra ngoài thư mục đích | Ghi vào cấu hình, dữ liệu tenant khác hoặc vị trí được thành phần khác sử dụng. | Giữ mọi thao tác tạo và ghi bên trong vùng làm việc đã xác lập. |
| Liên kết trỏ ra ngoài | Đường dẫn nhìn như ở trong vùng đích nhưng đối tượng thực nằm ngoài. | Chính sách rõ về liên kết và cơ chế không đi theo liên kết trái phép. |
| Hai mục cùng ánh xạ tới một tên | Ghi đè hoặc bộ kiểm tra và bộ sử dụng thấy nội dung khác nhau. | Từ chối trùng tên theo cách diễn giải của nơi lưu trữ. |
| Tên tệp xung đột với thư mục | Một mục thay đổi ý nghĩa của đường dẫn cho mục khác. | Kiểm tra cây đích và không thay thế loại đối tượng. |
| Dữ liệu bung ra quá lớn | Hết dung lượng, bộ nhớ, thời gian hoặc số đối tượng hệ thống tệp. | Giới hạn số mục, byte thực tế, thời gian và tài nguyên toàn cục. |
| Archive lồng nhiều tầng | Công việc tiếp tục tăng qua các lần giải nén. | Chính sách không giải nén lồng hoặc ngân sách chung cho mọi tầng. |
| Archive hỏng ở cuối | Một phần kết quả đã bị dùng trước khi phát hiện lỗi. | Chỉ công bố khi toàn bộ công việc đạt điều kiện. |
| Tên an toàn lúc kiểm tra nhưng đích thay đổi lúc ghi | Kiểm tra đường dẫn không còn đúng tại điểm sử dụng. | Bảo vệ ranh giới trong thao tác thực tế, không chỉ so chuỗi trước đó. |

Chuỗi truy vết nên có dạng:

> Rủi ro → bất biến → yêu cầu → điểm thực thi → ca kiểm thử → bằng chứng.

“Dùng thư viện giải nén” là một lựa chọn thiết kế. Cần kiểm chứng thư viện và cấu hình đã chọn có thực thi đầy đủ chính sách đường dẫn, loại mục và giới hạn tài nguyên của ứng dụng hay không.

## 3. Hồ sơ giải nén và các bất biến

### 3.1. Hồ sơ minh họa

Chức năng nhập bộ tài liệu chấp nhận một ZIP không mã hóa, không chia nhiều phần, thuộc phạm vi hỗ trợ đã được phê duyệt. Các mục được tạo chỉ là thư mục và tệp thông thường.

| Thuộc tính | Giới hạn của ví dụ |
|---|---|
| Archive đầu vào | Tối đa 25 MiB; 1 MiB bằng 1.048.576 byte. |
| Số mục | Tối đa 1.000 mục, tính cả thư mục. |
| Đối tượng được tạo | Tối đa 2.000 tệp và thư mục, gồm thư mục cha tạo bổ sung. |
| Một tệp sau giải nén | Tối đa 20 MiB. |
| Tổng byte tệp sau giải nén | Tối đa 200 MiB. |
| Tỷ lệ mở rộng tổng | Không quá 100 lần kích thước archive đã nhận đủ; đây là kiểm soát bổ sung. |
| Độ sâu đường dẫn | Tối đa tám thành phần tên, tính cả tên tệp nếu là tệp. |
| Thời gian công việc | Tối đa mười giây thời gian thực từ khi bắt đầu xử lý. |
| Bộ nhớ worker | Tối đa 128 MiB cho công việc trong cấu hình thử. |
| Dung lượng tạm một công việc | Tối đa 256 MiB, gồm đầu vào và dữ liệu tạm thuộc công việc. |
| Archive lồng | Không tự giải nén; tệp archive bên trong không thuộc hồ sơ nhập này. |
| Liên kết và loại đặc biệt | Không tạo symlink, hard link, thiết bị, pipe, socket hoặc loại ngoài hồ sơ. |
| Công bố | Chỉ sau khi toàn bộ gói và nội dung cần dùng đều đạt kiểm tra. |

Một thư mục khai báo trong archive và thư mục cha do ứng dụng tự tạo phải được tính riêng trong phép đo tài nguyên phù hợp. Giới hạn 1.000 mục không thay thế giới hạn số đối tượng thực tế hoặc dung lượng tạm.

Tỷ lệ mở rộng không phải kiểm soát duy nhất. Archive có thể vượt ngân sách tuyệt đối dù tỷ lệ thấp; dữ liệu thêm vào archive cũng có thể làm tỷ lệ nhìn nhỏ hơn mà không làm giảm lượng dữ liệu bung ra.

### 3.2. Bất biến cần giữ

1. Mọi đối tượng được tạo và mọi byte được ghi thuộc đúng vùng làm việc riêng của công việc.
2. Archive không được ghi đè dữ liệu có trước hoặc nội dung của công việc khác.
3. Không tạo hoặc đi theo loại liên kết và đối tượng bị cấm.
4. Tên mục không dẫn tới nhiều cách ánh xạ trái chính sách.
5. Tổng công việc và tài nguyên thực dùng không vượt hồ sơ.
6. Dữ liệu chưa được chấp nhận không được phục vụ hoặc dùng như kết quả hoàn chỉnh.
7. Lỗi ở bất kỳ bước bắt buộc nào làm toàn bộ gói không được công bố.
8. Kết quả và bằng chứng phải gắn với đúng phiên bản archive đã xử lý.

Các bất biến áp dụng cả khi xử lý đồng thời, retry, worker dừng hoặc archive hỏng. Không chỉ kiểm tra đường đi thành công.

## 4. Ranh giới đường dẫn: kiểm soát nơi ghi thực tế

### 4.1. Không ghép tên mục trực tiếp thành đích ghi

Tên mục là dữ liệu do bên gửi kiểm soát. Các nhóm cần kiểm tra gồm:

- Đường dẫn tuyệt đối, tên có gốc đĩa hoặc gốc mạng ngoài phạm vi cho phép.
- Thành phần đi lên thư mục cha hoặc cách mã hóa gây diễn giải khác nhau.
- Ký tự phân cách và tiền tố được môi trường đích hiểu là cấu trúc đường dẫn.
- Ký tự điều khiển, thành phần rỗng hoặc tên đặc biệt không được hồ sơ hỗ trợ.
- Tên dành riêng, luồng dữ liệu phụ hoặc dạng tên đặc thù của hệ thống đích.
- Tên quá dài hoặc quá sâu.

Một số ví dụ tên để đưa vào bộ mẫu kiểm thử là “../outside.txt”, đường dẫn bắt đầu từ gốc hoặc tên chứa tiền tố ổ đĩa. Đây là dữ liệu thử cho chính sách từ chối; không được dùng chúng làm đường ghi thật trên hệ thống sử dụng.

Hồ sơ phải nêu định dạng tên và cách giải mã. Không giải mã lặp nhiều vòng hoặc chuẩn hóa theo nhiều quy tắc không thống nhất giữa kiểm tra và ghi.

### 4.2. So chuỗi tiền tố không chứng minh nằm trong gốc

Một đường dẫn có cùng chuỗi đầu với tên thư mục gốc có thể là thư mục bên cạnh. Điều kiện phải được đánh giá theo thành phần đường dẫn và ngữ nghĩa của nơi lưu trữ, không chỉ bằng phép so chuỗi đơn giản.

Chuẩn hóa tên rồi kiểm tra đích còn nằm trong gốc là một bước cần thiết cho thiết kế giữ cấu trúc thư mục. Tuy nhiên, nó chưa giải quyết việc một thành phần đã là liên kết hoặc bị đổi sau kiểm tra.

Với đích chưa tồn tại, cũng không thể chỉ dựa vào việc “lấy đường dẫn thực của tệp cuối” mà bỏ qua cách tạo các thư mục cha. Cần bảo vệ từng thao tác tạo và mở đối tượng.

### 4.3. Ranh giới phải còn đúng khi thao tác hệ thống tệp

Thiết kế cần có vùng làm việc riêng do máy chủ tạo, quyền hạn chế và cơ chế tránh đi theo liên kết không được phép. Nếu nền tảng hỗ trợ thao tác tương đối theo handle thư mục và kiểm soát liên kết, có thể dùng để ràng buộc nơi tạo.

Nếu không thể chứng minh giữ ranh giới an toàn trên môi trường hiện tại, cần thay thiết kế, chẳng hạn lưu mỗi tệp bằng định danh máy chủ và quản lý cấu trúc logic bằng manifest. Không xem một phép kiểm tra tên trước đó là đủ để bù cho thao tác ghi không bảo vệ được.

Phương án lưu phẳng vẫn cần kiểm tra tên logic trước khi cho tải lại hoặc xuất thành archive. Nếu giữ nguyên một tên nguy hiểm trong manifest rồi tái dùng nó ở bước xuất, rủi ro có thể chuyển sang bước sau.

## 5. Liên kết, loại mục và quyền thuộc tính

### 5.1. Hồ sơ hẹp: chỉ tệp thông thường và thư mục

Trong ví dụ, mọi mục biểu diễn symlink, hard link hoặc loại đặc biệt đều bị từ chối. Không xử lý một mục chưa hiểu rõ loại như tệp thông thường để tiếp tục.

Cần xác minh thư viện có cung cấp đủ thông tin cho chính sách. Nếu không nhận diện được thuộc tính cần thiết, thiết kế chưa đủ căn cứ chấp nhận các mục đó.

Không khôi phục tùy ý quyền thực thi, chủ sở hữu, thuộc tính hệ thống hoặc metadata quyền từ archive. Đối tượng đầu ra dùng quyền do máy chủ xác lập theo nhu cầu nghiệp vụ.

Các nội dung giải nén không được tự chạy, tự nạp thành cấu hình hoặc đưa vào vị trí được hệ thống thực thi. Giải nén thành công chỉ tạo dữ liệu để bước kiểm tra tiếp theo xem xét.

### 5.2. Cấm liên kết không chỉ là kiểm tra metadata

Ngay cả khi archive không khai báo liên kết, vùng đích có thể chứa sẵn liên kết hoặc bị một chủ thể khác sửa. Vì vậy, cần đồng thời:

- Không dùng lại thư mục đích có nội dung không được kiểm soát.
- Không cho người tải lên hoặc công việc khác sửa vùng đang xử lý.
- Không đi theo liên kết trong các thành phần đường dẫn khi tạo và ghi.
- Không ghi đè đối tượng tồn tại mà chưa chứng minh đúng chính sách.

Việc chống liên kết và kiểm soát quyền vùng làm việc phải áp dụng tới thời điểm ghi dữ liệu, không chỉ trong một vòng duyệt archive trước đó.

## 6. Tên trùng, tên mơ hồ và cây đích

### 6.1. Định nghĩa trùng theo nơi lưu trữ

Hai tên khác chuỗi có thể ánh xạ tới cùng đích do phân biệt hoa thường, chuẩn hóa Unicode hoặc quy tắc tên của nền tảng.

Hồ sơ phải xác định quy tắc tên logic và kiểm tra tương thích với môi trường đích. Với môi trường không phân biệt hoa thường, các mục chỉ khác hoa thường không được âm thầm ghi đè nhau.

Trong ví dụ, phát hiện hai mục cùng ánh xạ tới một đích làm toàn bộ gói bị từ chối. Không dùng chính sách “mục cuối thắng” vì bộ kiểm tra và thành phần đọc có thể không chọn cùng một mục.

### 6.2. Kiểm tra cả xung đột tệp–thư mục

Nếu archive chứa tệp “reports” rồi chứa “reports/a.csv”, cây đích không thể coi “reports” đồng thời là tệp thông thường và thư mục. Phải từ chối xung đột, không thay loại đối tượng để tiếp tục.

Tương tự, không cho một mục xuất hiện sau thay thế thư mục cha đã được tạo cho mục trước. Việc tạo tệp mới cần có ngữ nghĩa không ghi đè và phát hiện xung đột thực tế tại nơi lưu trữ.

Có thể lập manifest cây dự kiến trước để phát hiện lỗi sớm. Vòng ghi vẫn phải áp lại các bảo vệ cần thiết; manifest không thay cho cơ chế tạo đối tượng an toàn.

### 6.3. Cùng dữ liệu, cùng cách diễn giải

Bước duyệt trước và bước giải nén phải dùng cùng phiên bản archive bất biến cùng quy tắc giải mã, chuẩn hóa và nhận diện mục.

Nếu metadata của archive mâu thuẫn hoặc thành phần đọc đưa ra cách diễn giải không nhất quán, phải có kết quả từ chối hoặc chưa thể kết luận. Không tự chọn cách diễn giải thuận lợi để vượt kiểm tra.

## 7. Giới hạn theo dữ liệu thực tế

### 7.1. Metadata là đầu vào, không phải ngân sách đã được chứng minh

Kích thước khai báo có thể sai, chưa đầy đủ hoặc không phản ánh toàn bộ chi phí xử lý. Có thể dùng nó để từ chối sớm khi chắc chắn vượt hồ sơ, nhưng vẫn phải đếm dữ liệu thực sự được tạo.

Không cấp phát bộ nhớ theo một kích thước khai báo chưa được kiểm tra. Thiết kế nên đọc theo bộ đệm hữu hạn và thực thi giới hạn trong quá trình giải nén.

Các bộ đếm cần có:

- Số mục đọc được thực tế, kể cả thư mục và các mục cuối cùng bị từ chối.
- Số đối tượng hệ thống tệp đã tạo, bao gồm thư mục cha tạo bổ sung.
- Byte thực tế của mỗi tệp và tổng các tệp.
- Dung lượng tạm, gồm đầu vào, dữ liệu dở dang và sản phẩm trung gian.
- Độ sâu và độ dài tên theo quy tắc của hồ sơ.
- Thời gian thực, bộ nhớ và công việc đang chạy.

Phép cộng phải được bảo vệ trước tràn số. Nếu không thể tính hoặc xác minh an toàn, không được coi giới hạn là chưa chạm.

### 7.2. Kiểm tra trước khi ghi thêm

Mã giả minh họa ngữ nghĩa:

~~~text
xác lập archive bất biến và vùng làm việc riêng
khởi tạo các bộ đếm và ngân sách

với mỗi mục do bộ đọc archive trả về:
  tăng và kiểm tra số mục
  xác minh loại mục và tên theo hồ sơ
  phát hiện trùng tên hoặc xung đột cây đích
  tạo đối tượng mới dưới gốc bằng thao tác bảo vệ được ranh giới

  nếu là tệp:
    đọc dữ liệu giải nén theo khối hữu hạn
    trước mỗi lần ghi:
      kiểm tra byte tệp, tổng byte, tỷ lệ và dung lượng tạm
      kiểm tra thời gian cùng trạng thái hủy
    chỉ ghi khối khi mọi giới hạn còn hợp lệ
    xác minh kết thúc mục và kiểm tra toàn vẹn theo định dạng

chỉ chuyển tới bước công bố sau khi toàn bộ archive kết thúc hợp lệ
~~~

Đây không phải đoạn mã có thể sao chép để giải nén an toàn trên mọi nền tảng. Các thao tác mở đối tượng, bảo vệ liên kết và điều phối tài nguyên cần được chọn theo môi trường triển khai.

Nếu thư viện tạo dữ liệu tạm hoặc cấp phát trước khi ứng dụng nhận được khối dữ liệu, các tài nguyên đó vẫn phải chịu giới hạn của môi trường worker. Bộ đếm byte do ứng dụng ghi không bao phủ mọi tài nguyên mà thư viện có thể dùng.

### 7.3. Tỷ lệ mở rộng là điều kiện bổ sung

Trong ví dụ:

~~~text
tỷ lệ mở rộng tổng
  = tổng byte tệp thực tế sau giải nén
    / số byte archive đầu vào đã nhận đủ
~~~

Archive rỗng hoặc không có kích thước đầu vào hợp lệ không được đi tới phép chia không xác định. Giới hạn tổng 200 MiB và giới hạn một tệp 20 MiB vẫn áp dụng độc lập với tỷ lệ 100 lần.

Tệp ít byte có thể tạo nhiều đối tượng nhỏ và metadata hệ thống tệp. Vì vậy, giới hạn dung lượng không thay thế giới hạn số mục và số đối tượng.

### 7.4. Archive lồng cần ngân sách chung nếu được hỗ trợ

Hồ sơ ví dụ không giải nén lồng. Phát hiện một archive bên trong làm nội dung không đáp ứng chính sách nhập, thay vì tự gọi bộ giải nén tiếp.

Nếu một sản phẩm khác cần giải nén lồng, phải xác định độ sâu tối đa và áp ngân sách chung cho mọi tầng. Không cấp lại toàn bộ ngân sách cho mỗi archive con; cách đó có thể cho tổng chi phí tăng vượt mục tiêu.

Đối tượng được mã hóa hoặc không thể kiểm tra không được coi là an toàn vì chưa phát hiện nội dung xấu. Hồ sơ cần quyết định rõ việc từ chối hoặc một quy trình xử lý riêng.

## 8. Cách ly, công bố và dọn kết quả lỗi

### 8.1. Vùng làm việc riêng cho từng lần xử lý

Mỗi lần xử lý có định danh và vùng làm việc do máy chủ tạo, thuộc đúng tenant và không dùng lại thư mục có nội dung không được kiểm soát.

Trong cấu hình minh họa, toàn nhóm có tối đa hai công việc chạy, 20 công việc chờ và 2 GiB dung lượng tạm. Dữ liệu của công việc lỗi chưa dọn vẫn được tính vào hạn mức. Hệ thống không nhận thêm công việc nếu không thể giữ giới hạn đã đặt.

Worker dùng quyền tối thiểu, không cần truy cập mạng cho hồ sơ này và không có quyền ghi vào vùng dữ liệu nghiệp vụ khác. Vùng cách ly không nằm trong đường thực thi hoặc đường phục vụ công khai.

### 8.2. Chỉ công bố gói đầy đủ

Giải nén xong một mục không đủ để công bố mục đó. Archive có thể hỏng ở mục cuối, chứa xung đột xuất hiện muộn hoặc không đạt kiểm tra nội dung sau giải nén.

Trước khi công bố cần xác nhận:

1. Archive đã được đọc và kết thúc hợp lệ theo hồ sơ.
2. Mọi mục đáp ứng chính sách tên, loại, giới hạn và tính nhất quán.
3. Kiểm tra toàn vẹn của định dạng đã hoàn tất nếu định dạng có yêu cầu.
4. Từng tệp cần sử dụng đã đạt hồ sơ loại và nội dung của nghiệp vụ.
5. Manifest đầu ra khớp tập đối tượng, kích thước và phiên bản thực tế.
6. Quyền đọc và liên kết tenant được xác lập.
7. Quyết định chấp nhận được cam kết và chỉ tham chiếu đầu ra đầy đủ.

Kiểm tra toàn vẹn như checksum của định dạng hỗ trợ phát hiện dữ liệu hỏng; nó không tự chứng minh nguồn gửi đáng tin hoặc nội dung không có mã độc.

Có thể công bố bằng manifest được kích hoạt sau cùng hoặc cơ chế khác có ngữ nghĩa tương đương. Không mặc định việc chuyển cả thư mục luôn nguyên tử, đặc biệt khi có nhiều nơi lưu trữ. Cần chứng minh người dùng không thấy tập kết quả dở dang.

### 8.3. Lỗi không để lại một gói “thành công một phần”

Nếu vi phạm hồ sơ, parser lỗi, hết ngân sách hoặc worker dừng, toàn bộ công việc không được đánh dấu chấp nhận. Các tệp đã tạo vẫn là dữ liệu cách ly.

Trong ví dụ, dọn dữ liệu phải hoàn tất trong 60 giây sau khi công việc bị kết luận thất bại, bị hủy hoặc bị từ chối. Nếu worker chết, bộ điều phối phải nhận diện công việc không còn hoạt động và áp quy trình thu hồi, thay vì để thư mục mồ côi không được tính hạn mức.

Nếu không dọn được, giữ dữ liệu không thể phục vụ, tiếp tục tính tài nguyên đã chiếm và phát cảnh báo. Không đánh dấu đã thu hồi chỉ vì đã phát lệnh xóa.

### 8.4. Dọn dữ liệu cũng phải giữ ranh giới

Quy trình dọn chỉ được tác động vùng làm việc mà máy chủ xác lập cho đúng công việc. Cần kiểm tra quyền sở hữu và đích thực tế, không dựng lệnh dọn từ tên mục trong archive hoặc chuỗi do client cung cấp.

Không đi theo liên kết để xóa dữ liệu ngoài vùng làm việc. Nếu đích có trạng thái bất thường, cần cô lập và xử lý theo quy trình thay vì mở rộng phạm vi xóa.

Chạy lại phải tạo lần xử lý và vùng làm việc mới, liên kết với đúng archive đầu vào. Không giải nén tiếp vào kết quả dở dang mà thiếu hợp đồng phục hồi riêng.

## 9. Bộ yêu cầu giải nén an toàn mẫu

### SR-AE-001 — Hồ sơ định dạng và đầu vào bất biến

Chức năng chỉ nhận ZIP thuộc hồ sơ hỗ trợ, không mã hóa, không chia nhiều phần và không phải gói tự giải nén. Định dạng phải được xác minh từ dữ liệu, không chỉ từ tên hoặc MIME khai báo.

Archive được nhận đủ trong giới hạn 25 MiB phải có định danh và phiên bản hoặc dấu vân tay do máy chủ xác lập. Các vòng kiểm tra và giải nén phải dùng đúng nội dung đó.

Archive lồng không được tự giải nén trong hồ sơ này. Tệp bên trong còn phải đáp ứng hồ sơ nội dung của chức năng nhập trước khi công bố.

### SR-AE-002 — Không ghi ngoài vùng làm việc

Mọi thao tác tạo thư mục, tạo tệp và ghi dữ liệu phải bị ràng buộc trong gốc riêng do máy chủ tạo cho công việc. Tên tuyệt đối, thành phần đi lên, gốc đĩa, gốc mạng và dạng đặc biệt ngoài hồ sơ phải bị từ chối.

Kiểm tra tên và thao tác ghi phải dùng cùng quy tắc diễn giải. Ranh giới phải được bảo vệ tại thời điểm sử dụng, kể cả khi có thay đổi đối tượng hệ thống tệp giữa các bước.

Bằng chứng phải gồm tên mục không hợp lệ, liên kết có sẵn tại đích và tình huống thay thành phần đường dẫn trong lúc xử lý. Không có dữ liệu ngoài gốc bị tạo hoặc thay đổi.

### SR-AE-003 — Chỉ tạo loại được phép và không ghi đè

Chỉ tạo thư mục và tệp thông thường. Không tạo hoặc đi theo symlink, hard link và loại đặc biệt; không khôi phục quyền, chủ sở hữu hoặc thuộc tính thực thi từ archive ngoài chính sách.

Mọi trùng đích, kể cả do quy tắc hoa thường hoặc chuẩn hóa của nơi lưu trữ, và mọi xung đột tệp–thư mục đều làm gói bị từ chối. Không sử dụng chính sách mục cuối ghi đè mục trước.

Việc tạo tệp phải phát hiện đối tượng đã tồn tại. Bằng chứng phải kiểm tra cả mục trùng rõ ràng lẫn tên khác chuỗi nhưng trùng đích trên môi trường triển khai.

### SR-AE-004 — Ngân sách giải nén thực tế

Mỗi công việc chịu các giới hạn: 1.000 mục archive, 2.000 đối tượng hệ thống tệp kể cả thư mục cha bổ sung, 20 MiB mỗi tệp, 200 MiB tổng dữ liệu tệp, độ sâu tám thành phần và tỷ lệ mở rộng tổng không quá 100 lần.

Thời gian thực không quá mười giây, bộ nhớ tối đa 128 MiB và dung lượng tạm tối đa 256 MiB theo cấu hình nghiệm thu. Các phép đo dùng dữ liệu thực tế, không chỉ giá trị khai báo.

Vượt bất kỳ giới hạn nào phải dừng chấp nhận đầu ra và kích hoạt thu hồi. Việc kết thúc chờ ở bên gọi không thay cho việc dừng hoặc cô lập công việc còn sử dụng tài nguyên.

### SR-AE-005 — Cô lập công việc và quyền tối thiểu

Vùng làm việc không được sửa bởi người tải lên, tenant khác hoặc công việc khác. Worker không có quyền ghi ngoài phạm vi cần thiết và không có quyền truy cập mạng trong hồ sơ ví dụ.

Toàn nhóm giới hạn hai công việc chạy, 20 chờ và 2 GiB dung lượng tạm. Hệ thống phải từ chối hoặc trì hoãn tiếp nhận theo hợp đồng khi thiếu tài nguyên, không chuyển sang một hàng đợi không giới hạn.

Bằng chứng gồm hai công việc dùng cùng tên mục, yêu cầu tenant khác, worker dừng và dữ liệu lỗi còn chiếm dung lượng.

### SR-AE-006 — Công bố đầy đủ và thu hồi có kiểm chứng

Chỉ công bố sau khi toàn bộ archive và nội dung bắt buộc đạt kiểm tra, manifest khớp đối tượng đầu ra và quyết định chấp nhận được cam kết.

Không có đường xem trước, tải tạm hoặc xử lý nghiệp vụ nào được dùng kết quả dở dang như dữ liệu đã chấp nhận. Kết quả lỗi phải được dọn trong 60 giây theo mốc kết luận ở mục 8; nếu không dọn được phải giữ cách ly, tiếp tục tính hạn mức và cảnh báo.

Bằng chứng phải chèn lỗi sau khi đã tạo một số tệp và trước khi công bố, sau đó kiểm tra cả trạng thái người dùng thấy và tài nguyên còn tồn tại.

### SR-AE-007 — Audit và liên kết kết quả

Mỗi lần xử lý phải ghi tenant, định danh archive, phiên bản nội dung, hồ sơ, phiên bản thành phần xử lý, định danh công việc, vùng làm việc nội bộ, kết quả và các bộ đếm tài nguyên.

Kết quả bất đồng bộ phải khớp công việc còn hiệu lực và đúng phiên bản đầu vào. Kết quả của lần xử lý cũ không được công bố dữ liệu của lần mới hoặc làm sống lại công việc đã bị từ chối.

Log không ghi bí mật, toàn bộ nội dung tệp hoặc tên chưa được xử lý an toàn. Đường dẫn nội bộ chỉ được cung cấp cho người có quyền vận hành phù hợp.

## 10. Ma trận kiểm thử và bằng chứng chấp nhận

Bộ mẫu nên được tạo trong môi trường thử cách ly bằng dữ liệu vô hại. Các tệp kiểm chứng ngoài gốc phải là dữ liệu thử được quản lý, không phải cấu hình hoặc tài liệu thật.

| Kịch bản | Điều kiện tạo | Kết quả phải chứng minh |
|---|---|---|
| Gói hợp lệ | Các thư mục và tệp hợp lệ, trong mọi giới hạn. | Công bố đúng manifest, quyền và nội dung. |
| Tên thoát gốc | Mục có thành phần đi lên hoặc dạng tuyệt đối. | Từ chối, không tạo hoặc thay đổi đối tượng ngoài gốc. |
| Dạng đường dẫn theo nền tảng | Tên có gốc đĩa, gốc mạng, tên dành riêng hoặc dạng ngoài hồ sơ. | Cách kiểm tra nhất quán với nơi lưu trữ thực tế. |
| Liên kết trong gói | Mục có loại liên kết bị cấm. | Không tạo liên kết và không dùng nó để ghi tiếp. |
| Liên kết ở đích | Tạo điều kiện kiểm thử với thành phần đích không còn là thư mục an toàn. | Thao tác ghi bị ngăn tại thời điểm dùng. |
| Trùng tên | Hai mục cùng tên hoặc trùng đích sau quy tắc nền tảng. | Không có chính sách ghi đè ngầm. |
| Xung đột cây | Một tên vừa được dùng làm tệp vừa làm thư mục cha. | Toàn gói bị từ chối, không thay loại đối tượng. |
| Vượt dữ liệu thực tế | Dòng giải nén thử đạt giới hạn rồi yêu cầu ghi thêm. | Không vượt byte tệp, tổng byte hoặc dung lượng tạm cho phép. |
| Nhiều mục nhỏ | Chạm số mục hoặc số đối tượng, dù tổng byte thấp. | Giới hạn đối tượng vẫn được thực thi. |
| Archive lồng hoặc mã hóa | Nội dung thuộc nhóm ngoài hồ sơ. | Không tự mở rộng xử lý hoặc cho qua vì chưa kiểm tra được. |
| Dữ liệu hỏng cuối gói | Một số mục đầu đọc được, phần cuối không hợp lệ. | Không có kết quả từng phần được phục vụ. |
| Worker timeout hoặc chết | Dừng xử lý khi đang có dữ liệu dở dang. | Cách ly, tính hạn mức, dọn và cảnh báo theo quy tắc. |
| Thay archive giữa các bước | Phiên bản dữ liệu không còn khớp vòng kiểm tra. | Kết quả cũ không áp dụng cho dữ liệu mới. |
| Công việc đồng thời | Nhiều job và tenant dùng tên mục giống nhau. | Không trộn hoặc ghi đè dữ liệu giữa công việc. |

Ví dụ kịch bản cho lỗi xuất hiện muộn:

~~~gherkin
Feature: Không công bố bộ tài liệu giải nén dở dang

  Scenario: Archive không hợp lệ sau khi đã tạo một số tệp
    Given công việc của tenant A đang ghi vào vùng cách ly riêng
    And một số mục đầu đã được giải nén trong giới hạn
    When bộ đọc phát hiện lỗi bắt buộc ở phần cuối archive
    Then toàn bộ công việc không được đánh dấu chấp nhận
    And không tệp dở dang nào được phục vụ qua đường sử dụng thông thường
    And dữ liệu tạm được thu hồi theo thời hạn
    And tài nguyên chưa thu hồi vẫn được tính vào hạn mức
    And audit liên kết kết quả lỗi với đúng archive và lần xử lý
~~~

Phải kiểm tra dữ liệu thực tế trên hệ thống tệp, không chỉ mã phản hồi. Một yêu cầu trả lỗi vẫn có thể đã ghi ra ngoài gốc hoặc để lại dữ liệu được đường khác phục vụ.

Các trường hợp cạnh tranh cần điều khiển được thời điểm giữa kiểm tra và tạo đối tượng. Bộ mẫu hợp lệ chạy tuần tự không đủ chứng minh an toàn trước thay đổi đồng thời.

## 11. Logging, giám sát và xử lý sự cố

Nên tách ba nhóm thông tin:

- **Quyết định chính sách:** tên không hợp lệ, loại mục bị cấm, trùng đích, archive ngoài hồ sơ.
- **Giới hạn tài nguyên:** byte thực tế, số mục, số đối tượng, thời gian, bộ nhớ và dung lượng tạm.
- **Vòng đời công việc:** đã nhận, đang xử lý, đang kiểm tra nội dung, đã chấp nhận, thất bại và chưa thu hồi xong.

Tên mục là dữ liệu không tin cậy. Khi ghi log hoặc hiển thị lý do lỗi, phải tránh việc tên gây chèn dòng, giả sự kiện hoặc làm lộ thông tin không cần thiết.

Các cảnh báo hữu ích gồm công việc mồ côi, dọn không thành công, tài nguyên tạm gần đầy, tỷ lệ parser lỗi tăng và nhiều lần thử cùng tên ngoài hồ sơ. Một tệp lỗi không tự chứng minh người dùng có ý đồ xấu; cần giữ ngữ cảnh để phân biệt lỗi dữ liệu và hành vi lạm dụng.

Khi xử lý sự cố, không giải nén lại vào thư mục đang có dữ liệu không rõ nguồn. Không mở rộng quyền worker hoặc bỏ kiểm tra đường dẫn để “khôi phục nhanh”. Nếu phải giữ mẫu phục vụ điều tra, lưu ở khu vực riêng có quyền và thời hạn rõ ràng.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Chỉ nhận ZIP nên an toàn.” | Loại gói không quyết định nơi ghi và lượng công việc. | Có hồ sơ mục, đường dẫn, tài nguyên và công bố. |
| “Ghép tên rồi kiểm tra tiền tố là được.” | So chuỗi có thể sai ranh giới; liên kết và cạnh tranh vẫn tồn tại. | Kiểm tra theo thành phần và bảo vệ thao tác ghi thực tế. |
| “Archive không có symlink thì không thể thoát gốc.” | Đích có thể chứa hoặc bị đổi thành liên kết. | Vùng riêng, quyền hạn chế và không đi theo liên kết trái phép. |
| “Kích thước khai báo nhỏ nên cho qua.” | Dữ liệu và tài nguyên thực tế có thể khác. | Đếm trong khi xử lý và áp giới hạn môi trường. |
| “Giới hạn tỷ lệ giải nén là đủ.” | Tổng byte hoặc số đối tượng vẫn có thể vượt nguồn lực. | Có nhiều giới hạn độc lập. |
| “Mục trùng thì lấy bản cuối.” | Các thành phần có thể chọn nội dung khác nhau. | Từ chối trùng theo ngữ nghĩa nơi lưu trữ. |
| “Tệp nào giải nén xong thì cho tải tệp đó.” | Phần cuối hoặc kiểm tra toàn gói có thể thất bại. | Chỉ công bố tập kết quả đã được chấp nhận. |
| “Timeout rồi thì công việc đã dừng.” | Parser hoặc worker có thể tiếp tục chiếm tài nguyên. | Xác minh dừng hoặc cô lập, rồi thu hồi. |
| “Xóa thư mục tạm là thao tác vô hại.” | Đích dọn hoặc liên kết có thể dẫn ra ngoài. | Giữ cùng ranh giới sở hữu và không đi theo đích trái phép. |

## 13. Duy trì yêu cầu trong vòng đời phát triển

Khi phân tích nghiệp vụ, xác định có thực sự cần giữ cấu trúc thư mục, giải nén lồng, metadata quyền hay định dạng đặc biệt không. Mỗi tính năng được cho phép làm tăng điều kiện phải kiểm chứng.

Khi mô hình hóa đe dọa, bao phủ đường dẫn, liên kết, tên trùng, tài nguyên bung ra, lỗi xuất hiện muộn và cách dọn dữ liệu. Liên kết từng rủi ro với SR-AE và phép thử tương ứng.

Khi thiết kế, xác định nguồn dữ liệu bất biến, vùng làm việc, quyền worker, cơ chế tạo đối tượng, giới hạn môi trường và điểm công bố. Nếu đổi hệ điều hành, hệ thống tệp, thư viện hoặc nơi lưu trữ, cần đánh giá lại ngữ nghĩa tên và tính nhất quán.

Khi nghiệm thu, kiểm tra cả nội dung ngoài gốc không bị đổi, kết quả dở dang không được phục vụ và tài nguyên được thu hồi. Khi vận hành, theo dõi dữ liệu mồ côi và thay đổi hành vi của parser sau cập nhật.

Bài tập áp dụng: một cổng nhập dữ liệu nhận archive của nhiều tenant và tạo bộ hồ sơ để người dùng tải lại. Hãy viết yêu cầu cho tên mục, loại đối tượng, giới hạn bung dữ liệu, archive lồng, cách ly, công bố và dọn lỗi. Với từng yêu cầu, nêu rủi ro, điểm thực thi trong kiến trúc và bằng chứng đủ để xác nhận không ghi ngoài gốc hoặc phục vụ một bộ hồ sơ chưa hoàn chỉnh.

