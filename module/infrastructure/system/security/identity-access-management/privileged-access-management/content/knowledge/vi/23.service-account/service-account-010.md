# Rotate service credential

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích vì sao luân chuyển credential dịch vụ là một quy trình phối hợp giữa hệ thống đích, kho bí mật và các ứng dụng sử dụng.
- Lập kế hoạch luân chuyển dựa trên danh sách consumer, quyền, cách phân phối secret và yêu cầu sẵn sàng.
- Phân biệt quy trình có hai credential hợp lệ đồng thời với quy trình chỉ cho phép một credential.
- Xác minh credential mới hoạt động và credential cũ đã mất hiệu lực mà không làm lộ giá trị bí mật.
- Thiết kế xử lý lỗi, phục hồi, giám sát và bằng chứng phục vụ kiểm toán hoặc ứng phó sự cố.

## 1. Luân chuyển credential dịch vụ nghĩa là gì?

Luân chuyển credential dịch vụ là thay thế thông tin xác thực đang được một workload sử dụng bằng thông tin mới, chuyển các consumer sang sử dụng thông tin mới và vô hiệu hóa thông tin cũ theo quy trình đã xác minh.

Credential có thể là mật khẩu tài khoản cơ sở dữ liệu, API key, client secret, khóa SSH hoặc khóa riêng đi cùng chứng chỉ. Workload có thể là ứng dụng, job theo lịch, pipeline, agent hoặc tiến trình tích hợp.

Trong PAM, luân chuyển nhằm giới hạn thời gian một bí mật có thể bị tái sử dụng, xử lý khả năng bị lộ và duy trì khả năng quy trách nhiệm. Nó cũng giúp loại bỏ credential mặc định, credential không rõ nguồn gốc và các bản sao không còn được kiểm soát.

Tạo một secret mới trong vault chưa phải là luân chuyển hoàn tất. Cần trả lời được cả ba câu hỏi:

1. Hệ thống đích có chấp nhận credential mới không?
2. Mọi consumer cần thiết đã sử dụng credential mới chưa?
3. Credential cũ còn tạo được truy cập mới hoặc duy trì truy cập hiện có không?

### 1.1. Tách danh tính khỏi credential

Một tài khoản dịch vụ có thể giữ nguyên danh tính và quyền trong khi credential của nó thay đổi. Ví dụ, tài khoản cơ sở dữ liệu vẫn là `svc_invoice_reader`, nhưng mật khẩu A được thay bằng B.

Một số phương án thay thế lại tạo danh tính mới, rồi chuyển workload sang danh tính đó. Khi ấy, cần kiểm tra thêm quyền, ownership tài nguyên, ràng buộc chính sách và ảnh hưởng tới audit log. Không coi việc tạo tài khoản mới là tương đương hoàn toàn với đổi mật khẩu.

Luân chuyển cũng không sửa được quyền quá rộng. Nếu tài khoản có quyền quản trị không cần thiết, credential mới vẫn mang cùng rủi ro đặc quyền.

### 1.2. Không nhầm luân chuyển với thay giá trị lưu trữ

Có ít nhất ba nơi chứa trạng thái liên quan:

| Thành phần | Trạng thái cần biết |
|---|---|
| Hệ thống đích | Credential nào đang được chấp nhận cho tài khoản |
| Kho bí mật hoặc vault | Phiên bản nào đang được lưu và phân phối |
| Consumer | Phiên bản nào thực sự đang được dùng trong bộ nhớ, tệp hoặc cấu hình |

Nếu chỉ cập nhật vault, ứng dụng có thể nhận giá trị mà hệ thống đích chưa chấp nhận. Nếu chỉ đổi phía đích, consumer có thể tiếp tục lấy giá trị cũ. Nếu cả hai đã đổi nhưng ứng dụng chỉ đọc secret lúc khởi động, nó vẫn có thể dùng bản cache cũ.

Một quy trình hoàn chỉnh phải phối hợp và đối soát cả ba.

## 2. Khi nào cần luân chuyển?

Các tác nhân thường gặp gồm:

- Đến kỳ theo chính sách nội bộ hoặc yêu cầu của hệ thống đích.
- Credential sắp hết hạn.
- Nghi ngờ secret bị lộ qua mã nguồn, log, ticket hoặc môi trường chạy.
- Phát hiện consumer không được phép sử dụng.
- Bàn giao vận hành khi có khả năng người không còn trách nhiệm vẫn giữ bí mật.
- Chuyển ứng dụng vào cơ chế quản lý bằng vault/PAM.
- Loại bỏ credential mặc định hoặc credential chia sẻ quá rộng.
- Thay đổi thuật toán, cơ chế xác thực hoặc thiết kế danh tính.
- Kết thúc một lần sử dụng khẩn cấp có làm lộ giá trị credential cho con người.

Chu kỳ định kỳ cần dựa trên mức rủi ro, khả năng vận hành, giới hạn sản phẩm và chính sách áp dụng. Không có một con số duy nhất phù hợp cho mọi loại credential.

Credential bị nghi lộ cần được xử lý theo mức độ khẩn cấp; không chờ tới lịch định kỳ. Tuy nhiên, chỉ đổi secret mà không xử lý workload bị xâm nhập có thể khiến secret mới tiếp tục bị lấy đi.

## 3. Lập bản đồ phụ thuộc trước khi thay đổi

### 3.1. Consumer không chỉ là ứng dụng chính

Một credential có thể được dùng bởi:

- Các replica đang phục vụ lưu lượng.
- Worker chạy nền.
- Job hàng giờ, hàng ngày hoặc cuối tháng.
- Pipeline triển khai và tác vụ bảo trì.
- Hệ thống sao lưu hoặc giám sát.
- Cụm dự phòng, vùng khôi phục thảm họa.
- Công cụ tích hợp của đối tác.
- Công cụ vận hành thủ công đang dùng chung tài khoản.

Một job chưa chạy trong tuần này vẫn có thể là consumer hợp lệ. Không có log gần đây chưa đủ để kết luận consumer đã ngừng hoạt động.

### 3.2. Thông tin tối thiểu của một kế hoạch

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Danh tính và quyền | Tài khoản nào, quyền hiệu lực nào, có đặc quyền nhạy cảm không? |
| Loại credential | Mật khẩu, API key, client secret, SSH key hay chứng chỉ? |
| Consumer | Ai đang dùng, ở môi trường nào, lịch hoạt động ra sao? |
| Phân phối | Lấy trực tiếp từ vault, qua agent, tệp hay biến môi trường? |
| Cache | Secret được giữ bao lâu, có reload hay cần restart? |
| Phiên | Kết nối và token đã phát hành có tiếp tục hoạt động sau khi đổi không? |
| Khả năng phía đích | Có thể dùng hai credential cùng lúc hay chỉ một? |
| Sức khỏe | Kiểm tra xác thực mới và kiểm tra nghiệp vụ bằng cách nào? |
| Thu hồi | Làm sao chứng minh credential cũ không còn được chấp nhận? |
| Phục hồi | Khi lỗi sẽ dừng, tiếp tục, tạo giá trị thứ ba hay dùng phương án khác? |
| Trách nhiệm | Ai điều phối, ai có quyền thay đổi, ai xác minh và ai nhận cảnh báo? |

### 3.3. Xác minh quyền truy cập của cơ chế luân chuyển

Thành phần tự động hóa cần đủ quyền để thực hiện nhiệm vụ, nhưng không nên có quyền rộng hơn cần thiết.

Ví dụ, khả năng cập nhật credential của một nhóm tài khoản không đồng nghĩa phải được đọc mọi secret trong tổ chức. Nếu cùng một danh tính có thể đổi mật khẩu, lấy secret, sửa log và phê duyệt công việc của chính nó, khả năng kiểm soát độc lập bị giảm.

Trong điều kiện sản phẩm cho phép, nên phân tách quyền thực hiện, quyền quản lý chính sách và quyền xem bằng chứng.

## 4. Ba mô hình chuyển đổi phổ biến

### 4.1. Hai credential có thể cùng hợp lệ

Một số hệ thống hỗ trợ hai API key hoặc nhiều client secret cho cùng một principal.

```text
Chỉ A hợp lệ
    ↓ tạo B
A và B hợp lệ
    ↓ kiểm tra B, chuyển consumer
A và B hợp lệ trong khoảng chuyển tiếp
    ↓ thu hồi A, xác minh
Chỉ B hợp lệ
```

Ưu điểm là có thể chuyển consumer dần. Rủi ro là A tiếp tục có tác dụng trong khoảng chuyển tiếp. Nếu không có hạn chót và chủ sở hữu, hai credential có thể tồn tại vô thời hạn.

Khả năng có nhiều secret không bảo đảm consumer có thể thay đổi mà không gián đoạn. Vẫn cần kiểm tra reload, connection pool và hành vi khi xác thực thất bại.

### 4.2. Chỉ một credential hợp lệ

Một tài khoản có thể chỉ chấp nhận một mật khẩu tại một thời điểm.

```text
A hợp lệ
    ↓ điều phối cửa sổ thay đổi
Đổi phía đích sang B
    ↓ cập nhật phân phối và consumer theo runbook
B hoạt động trên các consumer cần thiết
    ↓ xác minh A bị từ chối, xử lý phiên tồn dư
Hoàn tất
```

Các bước không nhất thiết diễn ra tức thời hoặc trong một giao dịch duy nhất. Có thể phải tạm dừng job, giảm lưu lượng, drain kết nối hoặc restart theo đợt.

Không nên cam kết không gián đoạn nếu hệ thống đích và consumer không hỗ trợ cách chuyển đổi phù hợp. Một khoảng bảo trì ngắn có kiểm soát có thể phù hợp hơn một quy trình thiếu khả năng phục hồi.

### 4.3. Thay thế bằng danh tính khác

Trong một số kiến trúc, có thể chuẩn bị tài khoản hoặc principal B, kiểm tra quyền rồi chuyển consumer khỏi principal A.

Phải đánh giá:

- Quyền của B có đúng phạm vi dự kiến không?
- Có tài nguyên hoặc ownership gắn chặt với A không?
- Audit log và chính sách ràng buộc có cần cập nhật không?
- A có thể bị vô hiệu hóa sau khi chuyển không?
- Có nguy cơ để lại hai danh tính mạnh cùng tồn tại lâu dài không?

Đây là chuyển đổi danh tính kèm credential. Không chỉ sao chép mọi quyền của A sang B mà bỏ qua rà soát least privilege.

## 5. Quy trình tham chiếu khi hỗ trợ hai credential

### Bước 1: Chuẩn bị và xác nhận điều kiện đầu vào

Ghi mã công việc, credential ID, phiên bản hiện tại, danh sách consumer, hạn chót thu hồi và người điều phối.

Kiểm tra quyền thực hiện, kết nối tới hệ thống đích và vault, tình trạng dịch vụ, lịch job và khả năng quan sát. Nếu một nguồn bằng chứng thiết yếu đang mất, cần đánh giá có đủ khả năng xác minh để bắt đầu hay không.

Xác định trước tiêu chí dừng. Ví dụ: không chuyển nhóm consumer tiếp theo nếu lỗi xác thực vượt ngưỡng đã chấp nhận hoặc chưa rõ phiên bản đang được dùng.

### Bước 2: Tạo credential mới

Tạo B bằng cơ chế phù hợp với hệ thống đích. Nếu cần sinh giá trị, dùng nguồn ngẫu nhiên mật mã và quy tắc tương thích với giới hạn của hệ thống.

Không dùng quy luật dễ đoán như tăng hậu tố tháng, lấy tên dịch vụ cộng năm hoặc dẫn xuất từ mật khẩu trước.

Không đưa secret vào tham số dòng lệnh, log, ticket hoặc nội dung phê duyệt. Việc xử lý ký tự đặc biệt phải thông qua API hoặc thư viện phù hợp, tránh nối chuỗi shell chứa bí mật.

### Bước 3: Lưu phiên bản mới có kiểm soát

Lưu B vào đúng vị trí của dịch vụ và môi trường. Gắn metadata như mã công việc, phiên bản và tài khoản đích; không cần ghi lại giá trị bí mật trong hồ sơ vận hành.

Có thể dùng trạng thái ứng viên trước khi đưa vào phân phối chính thức nếu hệ thống hỗ trợ. Cách đặt tên như “candidate”, “current” hay “previous” là quy ước triển khai, không phải bảo đảm rằng phía đích đã ở cùng trạng thái.

Giữ riêng định danh phiên bản với giá trị secret. Không tạo bằng chứng bằng cách công khai một phần secret hoặc một giá trị băm tùy tiện của secret.

### Bước 4: Kiểm tra B bằng xác thực mới

Một phép thử phù hợp cần tạo một lần xác thực mới bằng B trên đúng hệ thống đích.

Kiểm tra tiếp một hành động nghiệp vụ tối thiểu, an toàn và có ý nghĩa đối với dịch vụ. “Đăng nhập được” không chứng minh các quyền cần thiết đều đúng; ngược lại, tài khoản có thể được cấp quá nhiều quyền.

Không thực hiện thay đổi dữ liệu sản xuất chỉ để thử nếu không có quy trình cho phép. Có thể chọn thao tác chỉ đọc hoặc đối tượng thử nghiệm được quản lý.

### Bước 5: Chuyển consumer theo đợt

Chuyển một nhóm nhỏ trước khi mở rộng, nếu kiến trúc cho phép.

Với mỗi nhóm:

1. Cập nhật tham chiếu hoặc phiên bản phân phối.
2. Kích hoạt reload, restart hoặc tái tạo kết nối theo cơ chế thực tế.
3. Xác minh consumer nhận được phiên bản dự kiến.
4. Kiểm tra kết nối mới và chức năng dịch vụ.
5. Quan sát lỗi và độ trễ trong khoảng theo dõi đã định.
6. Ghi nhận kết quả rồi mới chuyển nhóm tiếp theo.

Không chỉ kiểm tra giá trị trong manifest hoặc tệp triển khai. Tiến trình đang chạy có thể vẫn giữ giá trị cũ.

### Bước 6: Xử lý consumer ít hoạt động

Job hàng tháng không nên được coi là đã chuyển chỉ vì cấu hình đã sửa. Có thể cần chạy kiểm thử được phép, kiểm tra khởi tạo kết nối hoặc một diễn tập tương đương.

Nơi dự phòng cần được kiểm tra theo thiết kế khôi phục. Một bản sao cấu hình cũ có thể chỉ bộc lộ lỗi trong đúng lúc hệ thống chính đang gặp sự cố.

Nếu chưa kiểm tra được một consumer, ghi rõ ngoại lệ, người sở hữu và hạn xử lý. Không dùng sự im lặng của consumer làm bằng chứng thành công.

### Bước 7: Thu hồi A

Khi đạt tiêu chí chuyển đổi, vô hiệu hóa A tại hệ thống đích. Việc xóa A khỏi vault không thay thế bước này.

Nếu hệ thống cho phép phân biệt key ID, ghi nhận ID đã thu hồi. Nếu dùng mật khẩu không có ID riêng, dựa vào kết quả thay đổi, phiên bản và các phép kiểm tra được thiết kế.

Hạn chế khoảng A và B cùng hợp lệ theo chính sách và mức rủi ro. Khi A bị nghi lộ, có thể phải thu hồi sớm hơn và chấp nhận tác động dịch vụ theo quyết định ứng phó sự cố.

### Bước 8: Xác minh thu hồi và xử lý truy cập tồn dư

Kiểm tra A không còn được chấp nhận cho xác thực mới bằng phương thức được phép và có kiểm soát. Phép thử cần tránh gây khóa tài khoản, tạo vòng retry hoặc ghi secret vào log.

Đồng thời kiểm tra các phiên, token hoặc khóa phái sinh. Kết quả “A không đăng nhập mới được” chưa đồng nghĩa mọi truy cập được tạo bằng A đã chấm dứt.

### Bước 9: Hoàn tất và lưu bằng chứng

Ghi lại trạng thái cuối của phía đích, vault, consumer và truy cập tồn dư. Xóa hoặc xử lý bản sao vận hành không còn cần thiết theo chính sách, đồng thời bảo vệ các bản sao lưu còn phải giữ.

Chỉ đóng khi các điều kiện hoàn tất đã đạt hoặc ngoại lệ được xử lý đúng thẩm quyền. Nếu công việc còn bước chưa rõ, trạng thái phải phản ánh điều đó.

## 6. Quy trình khi chỉ có một mật khẩu

Luồng này thường cần điều phối chặt hơn vì không có khoảng A và B cùng hợp lệ.

Một runbook tham chiếu có thể gồm:

1. Kiểm kê và xác nhận toàn bộ consumer.
2. Đặt cửa sổ thay đổi, thông báo bên liên quan và bố trí người xử lý.
3. Tạm dừng những job có thể xung đột.
4. Điều phối lưu lượng và kết nối theo kiến trúc.
5. Tạo B và bảo vệ giá trị trong toàn bộ luồng thay đổi.
6. Đổi mật khẩu ở phía đích và cập nhật kho theo thứ tự đã được thử.
7. Reload hoặc restart consumer theo kế hoạch.
8. Kiểm tra xác thực mới và chức năng từng nhóm.
9. Mở lại lưu lượng, job và theo dõi.
10. Xác minh A mất hiệu lực, xử lý phiên tồn dư và lưu bằng chứng.

Thứ tự cập nhật cụ thể phụ thuộc sản phẩm và cơ chế phân phối. Không có một thứ tự duy nhất bảo đảm an toàn cho mọi hệ thống. Runbook cần xác định rõ trạng thái trung gian và phương án khi lỗi ở từng bước.

Nếu connection pool còn giữ kết nối cũ, dịch vụ có thể trông vẫn hoạt động trong khi mọi kết nối mới đều thất bại. Vì vậy, kiểm tra kết nối mới là một điều kiện quan trọng trước khi kết luận thay đổi thành công.

## 7. Điều chỉnh theo từng loại credential

### 7.1. Mật khẩu cơ sở dữ liệu

Cần kiểm tra connection pool, chính sách khóa tài khoản và việc tài khoản có được dùng ngoài ứng dụng chính hay không.

Đổi mật khẩu có thể chỉ ảnh hưởng lần xác thực tiếp theo. Phiên đang mở có thể tiếp tục hoạt động tùy hệ thống. Khi cần chấm dứt truy cập do sự cố, phải đánh giá thêm việc ngắt phiên và tác động tới giao dịch.

Không dùng một vòng thử lại liên tục với mật khẩu cũ để kiểm tra thu hồi. Việc đó có thể làm khóa tài khoản hoặc tạo tải không cần thiết.

### 7.2. API key

Cần biết API key gắn với principal nào, quyền gì, phạm vi tài nguyên nào và có thể tồn tại bao nhiêu key đồng thời.

Nếu hệ thống có key ID, dùng ID để theo dõi vòng đời mà không ghi giá trị key. Kiểm tra rằng key cũ thực sự bị vô hiệu hóa ở phía nhà cung cấp, không chỉ bị gỡ khỏi cấu hình ứng dụng.

Các thao tác tạo, kích hoạt và thu hồi có thể có thời gian lan truyền. Chỉ kết luận theo kết quả đã xác minh, có xử lý sự chậm trễ trong tiêu chí theo dõi.

### 7.3. Client secret dùng để lấy token

Có hai vòng đời khác nhau:

```text
Client secret
     ↓ dùng để yêu cầu
Access token / token khác
     ↓ dùng để truy cập
Tài nguyên
```

Thu hồi client secret có thể ngăn việc lấy token mới bằng secret đó. Nó không mặc nhiên vô hiệu hóa mọi token đã phát hành.

Cần hiểu thời hạn token, cache, khả năng thu hồi và chính sách xác minh của tài nguyên. Nếu không có cơ chế thu hồi tức thời, hồ sơ phải thể hiện khoảng thời gian rủi ro còn lại và biện pháp hạn chế phù hợp.

### 7.4. SSH key

Tạo private key mới nhưng chưa cập nhật nơi xác minh thì consumer không thể xác thực bằng key đó. Ngược lại, thêm public key mới mà quên gỡ public key cũ vẫn để key cũ hoạt động.

Cần xác định đủ các máy đích, tài khoản, tệp hoặc hệ thống quản lý khóa liên quan. Kiểm tra phiên SSH hiện có và các cơ chế chuyển tiếp quyền nếu chúng nằm trong phạm vi xử lý.

Private key mới cần được bảo vệ trong quá trình tạo và phân phối. Không đính kèm private key vào ticket để bàn giao.

### 7.5. Chứng chỉ và private key

Gia hạn chứng chỉ dùng lại cùng private key khác với thay private key bằng key pair mới. Nếu mục tiêu là xử lý nghi ngờ private key bị lộ, chỉ cấp chứng chỉ mới cho cùng key không giải quyết được vấn đề đó.

Cần kiểm tra:

- Bên xác minh tin cậy chuỗi chứng chỉ nào.
- Ràng buộc tên, mục đích sử dụng và danh tính có phù hợp không.
- Consumer đã nạp cặp chứng chỉ và private key tương ứng chưa.
- Bên xác minh xử lý thu hồi và hết hạn như thế nào.
- Kết nối hiện có có cần được tái lập hay chấm dứt không.

Không mặc định việc đánh dấu chứng chỉ đã thu hồi sẽ được mọi bên xác minh áp dụng ngay. Hành vi thực tế phụ thuộc cơ chế kiểm tra và cấu hình triển khai.

## 8. Thiết kế tự động hóa có thể đối soát

### 8.1. Lưu trạng thái từng bước

Một công việc có thể được theo dõi bằng các trạng thái khái niệm:

| Trạng thái | Ý nghĩa |
|---|---|
| PLANNED | Đã có phạm vi, chủ sở hữu và tiêu chí |
| CANDIDATE_CREATED | Credential ứng viên đã được tạo |
| CANDIDATE_VERIFIED | Xác thực và kiểm tra ban đầu đã đạt |
| CONSUMERS_MIGRATING | Đang chuyển các consumer |
| READY_TO_REVOKE | Đã đạt điều kiện thu hồi cũ |
| OLD_REVOKED | Đã thực hiện thu hồi tại phía đích |
| FINAL_VERIFICATION | Đang kiểm tra hiệu lực thu hồi và truy cập tồn dư |
| COMPLETED | Đủ điều kiện đóng theo chính sách |
| NEEDS_ATTENTION | Có lỗi hoặc điều kiện chưa rõ cần xử lý |

Các tên trên chỉ là ví dụ thiết kế. Hệ thống thực tế có thể dùng tên khác, nhưng phải phân biệt được “đã yêu cầu thao tác” với “đã xác minh kết quả”.

Nếu quy trình dừng sau khi tạo credential ở đích nhưng trước khi lưu trạng thái, lần chạy tiếp theo phải tìm và đối soát kết quả đã có. Không tạo thêm credential mù quáng cho mỗi lần retry.

### 8.2. Tách ý định khỏi trạng thái quan sát được

Một phản hồi timeout không chứng minh thao tác thất bại. Hệ thống đích có thể đã hoàn tất nhưng phản hồi không quay về.

Cần ghi:

- Thao tác dự định.
- Định danh tài nguyên và phiên bản liên quan.
- Thời điểm gửi yêu cầu.
- Kết quả nhận được.
- Kết quả kiểm tra trạng thái sau đó.

Tránh đánh dấu B đã được kích hoạt chỉ vì lệnh kích hoạt đã được gửi. Cũng tránh thu hồi B khi chưa hiểu một lần retry có đang tham chiếu đúng phiên bản hay không.

### 8.3. Ngăn hai lần luân chuyển chồng chéo

Nếu hai controller cùng thay một credential, chúng có thể cập nhật vault và hệ thống đích theo thứ tự khác nhau.

Cần có cơ chế điều phối theo tài khoản hoặc credential, cùng kiểm tra phiên bản để tránh một lần xử lý cũ ghi đè kết quả mới.

Chỉ có khóa hết hạn chưa đủ trong mọi thiết kế. Một controller bị treo có thể tiếp tục chạy sau khi khóa của nó hết hạn và đã được cấp cho controller khác. Khi nền tảng hỗ trợ, cần cơ chế từ chối thao tác từ người giữ quyền xử lý đã cũ hoặc kiểm tra điều kiện phiên bản trước khi ghi. Khi không hỗ trợ, phải có cách điều phối và đối soát tương ứng.

Cơ chế phục hồi cũng phải xử lý khóa bị bỏ quên; không để một khóa lỗi chặn luân chuyển mãi mãi.

### 8.4. Mã giả mô tả luồng hai credential

Đoạn sau là mã giả, không phải script có thể chạy trực tiếp:

```text
rotate(credential_ref, expected_version):
    acquire_coordination(credential_ref)
    verify_current_version(expected_version)
    job = load_or_create_rotation_job()

    observed = inspect_target_vault_and_consumers(job)
    reconcile_previous_attempts(job, observed)

    candidate = ensure_candidate_exists(job)
    verify_new_authentication(candidate)
    verify_required_permissions(candidate)

    for group in consumer_groups(job):
        migrate(group, candidate)
        verify_runtime_version(group)
        verify_new_connection_and_service(group)

    require_revocation_conditions(job)
    revoke_old_at_target(job)
    verify_old_authentication_is_rejected(job)
    handle_existing_sessions_and_derived_access(job)

    record_evidence_without_secret_values(job)
    mark_completed_only_if_conditions_hold(job)
    release_coordination()
```

Mỗi thao tác phải có xử lý lỗi, thời hạn và khả năng đối soát. Mã giả không thể hiện mọi nhánh, nhưng nhấn mạnh rằng cập nhật secret chỉ là một phần của luồng.

## 9. Xử lý lỗi và phục hồi

### 9.1. Các trạng thái lệch thường gặp

| Tình huống | Tác động | Hướng xử lý |
|---|---|---|
| Tạo B ở đích thành công, lưu vault thất bại | Có credential chưa được quản lý đầy đủ | Đối soát, lưu an toàn hoặc thu hồi B theo runbook |
| Vault phân phối B nhưng đích chưa chấp nhận | Consumer có thể không đăng nhập được | Dừng mở rộng, kiểm tra trạng thái đích và khôi phục nhất quán |
| Một nhóm consumer còn dùng A | Lỗi xuất hiện khi A bị thu hồi | Tìm consumer và xử lý reload; giữ giới hạn thời gian chuyển tiếp |
| Thu hồi A thất bại | Credential cũ vẫn có thể bị lạm dụng | Giữ công việc mở, chuyển cấp, cân nhắc biện pháp hạn chế |
| Controller dừng giữa quy trình | Không rõ bước nào đã hoàn tất | Quan sát trạng thái thực tế trước khi tiếp tục |
| Job cũ chỉ chạy sau nhiều ngày | Lỗi muộn sau khi tưởng đã xong | Kiểm tra chủ động và hoàn thiện danh sách consumer |
| B có quyền thiếu hoặc thừa | Lỗi nghiệp vụ hoặc tăng đặc quyền | Kiểm tra quyền hiệu lực, không chỉ xác thực |
| Vault khôi phục từ bản sao lưu cũ | Phiên bản phân phối có thể không còn hợp lệ | Đối soát lại với đích, không tự tái kích hoạt giá trị đã thu hồi |

### 9.2. Rollback không phải lúc nào cũng là dùng lại A

Cần phân biệt hai tình huống.

**Thay đổi định kỳ thất bại nhưng A chưa bị nghi lộ:** có thể có một phương án phục hồi giới hạn tùy cơ chế và chính sách. Ví dụ, trong mô hình hai key, tạm thời chuyển consumer về A khi A vẫn còn hợp lệ, đồng thời giữ công việc mở và điều tra lỗi B.

**A đã bị nghi lộ:** khôi phục A có thể khôi phục truy cập cho kẻ tấn công. Phương án phù hợp có thể là tạo C, sửa consumer trên môi trường tin cậy và thu hồi cả phần không còn an toàn theo quyết định ứng phó sự cố.

Không tạo C một cách tùy tiện mà bỏ qua B. Mọi phiên bản đã tạo phải có trạng thái và người chịu trách nhiệm.

### 9.3. Không dùng lỗi vault làm lý do giữ secret cũ vô hạn

Consumer có thể có cache để chịu được gián đoạn ngắn. Nhưng nếu fallback tiếp tục dùng bản cũ không thời hạn, tổ chức không thể đảm bảo thu hồi.

Chính sách cache cần xác định:

- Khi nào còn được dùng bản đã có.
- Thời hạn tối đa.
- Hành vi nếu phía đích từ chối.
- Cách thông báo tình trạng degraded.
- Ai quyết định kéo dài ngoại lệ.
- Cách cập nhật sau khi kho bí mật phục hồi.

Ứng dụng không nên âm thầm chuyển qua nhiều credential lịch sử mỗi khi lỗi. Cơ chế đó có thể che lỗi luân chuyển và mở rộng bề mặt sử dụng secret cũ.

## 10. Phân biệt thành công kỹ thuật và hoàn tất kiểm soát

Một lần luân chuyển có thể thành công một phần:

- B đã được tạo.
- API chính đã dùng B.
- A vẫn hợp lệ.
- Job tháng chưa được kiểm tra.
- Token phát hành bằng A vẫn còn hiệu lực.
- Một bản ghi bằng chứng chưa thu thập được.

Thông báo “luân chuyển thành công” trong tình trạng này là quá sớm.

Có thể dùng các tiêu chí đóng như sau:

| Tiêu chí | Bằng chứng phù hợp |
|---|---|
| B hoạt động | Kết quả xác thực mới và kiểm tra chức năng |
| Quyền B đúng phạm vi | Kết quả kiểm tra quyền hiệu lực |
| Consumer đã chuyển | Metadata phiên bản lúc chạy và kiểm tra từng nhóm |
| A không tạo truy cập mới | Kết quả thu hồi phía đích và kiểm tra được phép |
| Truy cập tồn dư đã xử lý | Kết quả kiểm tra phiên, token và khóa phái sinh |
| Bản sao được kiểm soát | Kết quả xử lý cấu hình, cache và nguồn phân phối |
| Lỗi đã được giải quyết | Công việc khắc phục hoặc ngoại lệ có thẩm quyền |
| Hồ sơ đầy đủ | Mã công việc, thời gian, người thực hiện và người xác minh |

Việc không phát hiện sử dụng A trong một khoảng thời gian là tín hiệu hữu ích, nhưng không tự chứng minh A đã bị vô hiệu hóa. Cần bằng chứng từ phía chấp nhận credential.

Cũng không thể chỉ dựa vào việc một consumer báo đã nhận B để kết luận nó đã dùng B. Cần phép kiểm tra phù hợp với thời điểm xác thực thực tế.

## 11. Ví dụ triển khai: API, worker và nơi dự phòng

Một dịch vụ xử lý hóa đơn dùng client secret A để lấy access token từ hệ thống danh tính. Có ba consumer:

- API phục vụ yêu cầu.
- Worker xử lý hàng đợi.
- Bản triển khai dự phòng chỉ chạy khi chuyển vùng.

Hệ thống cho phép A và B cùng hợp lệ trong thời gian chuyển tiếp. Các consumer cache access token và chỉ yêu cầu token mới khi cần.

### 11.1. Nguy cơ của phép kiểm tra đơn giản

Đội vận hành tạo B, cập nhật vault và thấy API vẫn gọi dịch vụ đích thành công.

Điều đó chưa đủ vì:

- API có thể đang dùng access token được lấy trước khi chuyển.
- Worker có thể chỉ đọc client secret lúc khởi động.
- Nơi dự phòng có thể giữ cấu hình cũ.
- A vẫn có thể được dùng để lấy token mới.
- Thu hồi A không mặc nhiên làm access token cũ mất hiệu lực.

### 11.2. Quy trình phù hợp hơn

1. Gắn mã công việc và xác nhận ba consumer.
2. Tạo B, lưu phiên bản ứng viên và kiểm tra lấy token mới bằng B.
3. Kiểm tra quyền truy cập tài nguyên của token mới.
4. Chuyển một nhóm API, chủ động xác minh một luồng lấy token mới có kiểm soát.
5. Chuyển API còn lại và worker, theo dõi lỗi xác thực.
6. Kiểm tra khả năng khởi động của nơi dự phòng với phiên bản mới.
7. Xác nhận không còn consumer hợp lệ cần A.
8. Thu hồi A và kiểm tra việc lấy token mới bằng A bị từ chối theo phương thức được phép.
9. Xác định trạng thái token đã phát hành; xử lý theo cơ chế và mức rủi ro.
10. Lưu bằng chứng và kết luận theo điều kiện thực tế.

Không cần đưa giá trị client secret hoặc access token vào hồ sơ để chứng minh. Có thể dùng ID phiên bản, thời điểm, mã yêu cầu và kết quả đã được làm sạch.

### 11.3. Mốc thời gian minh họa

| Mốc | Việc xảy ra | Trạng thái kiểm soát |
|---|---|---|
| T0 | Tạo và kiểm tra B | A và B cùng hợp lệ |
| T1 | Chuyển API | Worker và nơi dự phòng còn cần xác minh |
| T2 | Chuyển worker, thử nơi dự phòng | Đủ consumer đã chuyển |
| T3 | Thu hồi A | Chưa kết luận về token đã phát hành |
| T4 | Hoàn tất xử lý truy cập tồn dư | Đủ dữ kiện để đánh giá đóng |
| T5 | Người có trách nhiệm xác minh hồ sơ | Hoàn tất nếu không còn ngoại lệ chưa xử lý |

Khoảng T0–T3 là khoảng credential cùng hợp lệ, cần được theo dõi riêng. Khoảng T3–T4 phản ánh phần truy cập có thể còn tồn tại sau khi thu hồi bí mật gốc.

## 12. Giám sát và thông báo trong quá trình luân chuyển

### 12.1. Các chỉ số vận hành

Có thể theo dõi:

- Số công việc đến hạn, đang chạy và quá hạn.
- Thời gian hoàn thành từng giai đoạn.
- Thời gian hai credential cùng hợp lệ.
- Số consumer chưa chuyển hoặc chưa xác minh.
- Lỗi xác thực mới sau thay đổi.
- Số lần thu hồi thất bại.
- Số lần phục hồi hoặc tạo phiên bản thay thế.
- Số credential không có chủ sở hữu hay runbook.
- Số ngoại lệ còn mở và thời gian tồn đọng.

Không nên chỉ báo cáo tỷ lệ “secret đã cập nhật trong vault”. Chỉ số đó bỏ qua việc consumer chưa đổi và phía đích vẫn chấp nhận credential cũ.

### 12.2. Cảnh báo cần có hành động

Cảnh báo phải chỉ ra credential ID, công việc, giai đoạn lỗi, người sở hữu và bước xử lý tiếp theo, nhưng không chứa secret.

Các trường hợp cần chú ý:

- Đến hạn mà chưa bắt đầu.
- Công việc dừng quá lâu ở một trạng thái.
- Credential cũ vẫn hợp lệ sau hạn chót.
- Có consumer đọc phiên bản cũ sau thời điểm chuyển.
- Có lỗi xác thực tăng trên tài nguyên quan trọng.
- Có thay đổi ngoài controller hoặc quy trình được phép.
- Credential mới sắp hết hạn nhưng chưa có kế hoạch tiếp theo.

Một công việc thất bại không nên chỉ ghi log rồi kết thúc im lặng.

### 12.3. Thông báo kết quả phải phản ánh phần còn mở

Ví dụ phù hợp:

> API và worker đã chuyển sang phiên bản B. Nơi dự phòng đã kiểm tra khởi động thành công. A đã bị thu hồi cho yêu cầu token mới. Việc xác minh token đã phát hành còn đang xử lý; hồ sơ chưa đóng, đội IAM chịu trách nhiệm cập nhật.

Không ghi “đã thu hồi toàn bộ truy cập” nếu chỉ mới vô hiệu hóa client secret.

## 13. Bảo vệ bí mật trong chính quy trình luân chuyển

Quy trình thay secret thường có quyền cao và tiếp xúc với cả giá trị cũ lẫn mới. Nếu nó ghi log quá mức hoặc chạy trên môi trường không tin cậy, luân chuyển có thể trở thành nguồn lộ bí mật.

Cần chú ý:

- Không log request hoặc response chứa mật khẩu, API key hay private key.
- Không truyền secret qua kênh chat, email hoặc tệp đính kèm công việc.
- Không lưu giá trị trong lịch sử lệnh hoặc tham số dễ bị công cụ vận hành thu thập.
- Bảo vệ tệp tạm nếu bắt buộc sử dụng, giới hạn quyền và xử lý sau khi dùng.
- Hạn chế quyền đọc dữ liệu chẩn đoán của controller.
- Kiểm soát danh tính triển khai và cập nhật mã tự động hóa.
- Ghi audit về người hoặc hệ thống đã thay đổi mà không ghi giá trị bí mật.
- Giới hạn khả năng sửa hoặc xóa bằng chứng của chính người thực hiện.

Nếu công cụ tự động hóa bị xâm nhập, chỉ thay các credential do nó quản lý có thể chưa đủ. Cần xử lý danh tính của công cụ, môi trường chạy và các quan hệ tin cậy liên quan.

## 14. Kiểm thử trước khi áp dụng rộng

Dùng tài khoản và dữ liệu thử nghiệm phù hợp để kiểm tra:

1. Luồng bình thường hoàn tất và có đủ bằng chứng.
2. Consumer chỉ đọc secret lúc khởi động.
3. Connection pool giữ phiên cũ.
4. Job ít hoạt động và nơi dự phòng.
5. Vault không phản hồi ở từng giai đoạn.
6. Hệ thống đích timeout sau khi có thể đã thực hiện thay đổi.
7. Controller khởi động lại giữa quy trình.
8. Hai yêu cầu luân chuyển xuất hiện đồng thời.
9. Một consumer chưa có quyền đọc phiên bản mới.
10. Thu hồi credential cũ thất bại.
11. Credential mới có quyền thiếu hoặc sai phạm vi.
12. Credential cũ bị nghi lộ trong lúc chuyển đổi.
13. Token hoặc phiên cũ tiếp tục hoạt động sau khi bí mật gốc bị thu hồi.
14. Khôi phục vault hoặc ứng dụng từ bản sao lưu cũ.
15. Không có người nhận cảnh báo lỗi trong thời hạn yêu cầu.

Một thử nghiệm lỗi đạt yêu cầu khi hệ thống phát hiện đúng vấn đề, giữ trạng thái có thể đối soát, thông báo cho người xử lý và phục hồi theo thiết kế. Không chỉ đánh giá việc hệ thống có tự chạy lại hay không.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Đồng nhất đổi secret với đổi dữ liệu trong vault | Phía đích và consumer có thể lệch nhau | Theo dõi cả ba trạng thái |
| Không kiểm kê consumer ít chạy | Lỗi xuất hiện muộn | Kiểm tra job, nơi dự phòng và công cụ phụ |
| Dùng health check trên kết nối cũ | Không phát hiện lỗi xác thực mới | Tạo kết nối mới có kiểm soát |
| Giữ key cũ để “phòng khi cần” vô hạn | Không hoàn tất giảm rủi ro | Đặt hạn thu hồi và chuyển cấp |
| Retry mà không đọc trạng thái thực | Tạo key thừa hoặc thu hồi sai | Đối soát trước mỗi lần tiếp tục |
| Cho phép hai controller cùng xử lý | Cập nhật chồng chéo | Điều phối và kiểm tra phiên bản |
| Rollback về credential bị nghi lộ | Khôi phục khả năng lạm dụng | Dùng phương án phục hồi tin cậy, có thể tạo giá trị mới khác |
| Tin rằng đổi mật khẩu cắt mọi phiên | Truy cập tồn dư bị bỏ sót | Xác minh và xử lý phiên, token riêng |
| Đóng hồ sơ dù thu hồi chưa xác minh | Báo cáo sai tình trạng | Dùng tiêu chí đóng rõ ràng |
| Tạo tài khoản thay thế với quyền sao chép toàn bộ | Duy trì hoặc tăng đặc quyền | Rà soát quyền hiệu lực và nhu cầu thực tế |
| Đưa secret vào bằng chứng | Mở thêm nguồn lộ | Dùng ID, phiên bản và kết quả đã làm sạch |

## 16. Bài tập thực hành

### Bài tập 1: Viết runbook cho một mật khẩu cơ sở dữ liệu

Giả sử ba replica API và một job đêm dùng chung một tài khoản chỉ có một mật khẩu hợp lệ.

Hãy xác định cửa sổ thay đổi, cách tạm dừng job, thứ tự cập nhật, cách tạo kết nối mới để thử và điều kiện phục hồi. Nêu rõ điều gì xảy ra nếu một replica không restart được.

### Bài tập 2: Phân tích trường hợp token còn tồn tại

Một client secret đã bị thu hồi nhưng một access token được phát hành trước đó vẫn truy cập được tài nguyên.

Hãy giải thích vì sao đây không nhất thiết là bằng chứng thu hồi client secret thất bại. Xác định thêm dữ liệu cần biết để đánh giá truy cập tồn dư và quyết định hành động phù hợp.

### Bài tập 3: Sửa báo cáo hoàn tất

Báo cáo ban đầu:

> Secret mới đã lưu vào vault. Ứng dụng đang chạy bình thường. Luân chuyển thành công.

Hãy bổ sung bằng chứng xác thực mới, quyền hiệu lực, danh sách consumer, thu hồi cũ, phiên/token tồn dư và người xác minh. Nếu còn một nơi dự phòng chưa được kiểm tra, báo cáo phải thể hiện ngoại lệ hoặc trạng thái chưa hoàn tất.

## 17. Điểm cần ghi nhớ

Luân chuyển credential dịch vụ là chuyển đổi có kiểm soát giữa credential cũ và mới trên toàn bộ chuỗi xác thực. Thành công không chỉ là tạo được bí mật mới, mà còn là consumer dùng đúng giá trị, quyền vẫn đúng phạm vi và credential cũ được xử lý tại nơi chấp nhận nó.

Một runbook tốt dự liệu trạng thái trung gian, lỗi từng bước, cách đối soát và phục hồi. Bằng chứng hoàn tất phải phân biệt xác thực mới, phiên đang mở và quyền phái sinh để việc quản lý credential phục vụ được cả vận hành, kiểm toán và ứng phó sự cố.
