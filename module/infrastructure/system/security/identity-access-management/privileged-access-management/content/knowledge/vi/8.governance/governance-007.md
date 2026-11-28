# Password rotation policy

Trong quản lý truy cập đặc quyền (PAM), **password rotation policy** là chính sách xác định mật khẩu nào phải được luân chuyển, khi nào thực hiện, ai chịu trách nhiệm và bằng chứng nào chứng minh quá trình đã hoàn tất. Mục tiêu là giảm thời gian một mật khẩu đặc quyền có thể bị sử dụng ngoài ý muốn, đồng thời kiểm soát ảnh hưởng tới các hệ thống đang phụ thuộc vào nó.

Bài học thuộc chương **Governance**, tập trung vào mật khẩu của tài khoản quản trị được PAM quản lý, tài khoản dùng chung và tài khoản dịch vụ trên hạ tầng nhạy cảm. Chính sách phải kết nối với kiểm kê quyền, ownership, đặc quyền tối thiểu, JIT/JEA, vault, giám sát phiên và quy trình ứng phó sự cố.

Đổi một giá trị trong vault chưa chứng minh mật khẩu ở hệ thống đích đã đổi. Đổi mật khẩu ở đích cũng chưa chứng minh mọi consumer đã cập nhật, mật khẩu cũ không còn được chấp nhận hoặc các phiên cũ đã mất quyền. Một chính sách có thể vận hành phải phân biệt được những trạng thái này.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Xác định phạm vi và phân loại tài khoản cần chính sách luân chuyển phù hợp.
- Kết hợp lịch định kỳ với sự kiện kích hoạt theo rủi ro.
- Gán trách nhiệm cho tài khoản, credential, consumer và cơ chế thực thi.
- Định nghĩa điều kiện hoàn tất có bằng chứng ở vault, hệ thống đích và consumer.
- Xử lý lỗi từng phần, timeout, mất đồng bộ và khôi phục có kiểm soát.
- Quản trị ngoại lệ, thông số thời hạn và chỉ số mà không che giấu đối tượng chưa xác minh.

## 2. Phạm vi chính sách và các khái niệm cần tách

### 2.1. Không áp một lịch đổi mật khẩu cho mọi loại danh tính

Tài khoản quản trị dùng chung, mật khẩu dịch vụ do máy quản lý và mật khẩu cá nhân của người dùng có đặc điểm khác nhau. Không suy rằng một lịch dành cho tài khoản đặc quyền do PAM quản lý phải áp nguyên vẹn cho mọi mật khẩu con người sử dụng.

Đối với từng lớp, cần xác định mức đặc quyền, khả năng bị lộ, cách sử dụng, mức tự động hóa, phụ thuộc và yêu cầu vận hành. Lịch định kỳ là một phần của thiết kế; sự kiện nghi lộ mật khẩu không được chờ đến lịch tiếp theo mới xử lý.

| Đối tượng | Điểm cần cân nhắc |
|---|---|
| Tài khoản quản trị dùng chung | Ai có thể nhận giá trị mật khẩu, khả năng dùng ngoài broker và quy trách nhiệm từng lần |
| Tài khoản quản trị khẩn cấp | Khả năng sử dụng khi hạ tầng thông thường lỗi, bảo quản, kiểm tra sẵn sàng và xử lý sau sử dụng |
| Tài khoản dịch vụ dùng mật khẩu tĩnh | Danh sách consumer, lịch chạy, cache, kết nối sống lâu và cách nạp phiên bản mới |
| Tài khoản quản trị cá nhân | Chính sách xác thực cá nhân, mức đặc quyền và cách thu hồi quyền; không mặc nhiên giống tài khoản dùng chung |
| Danh tính có credential ngắn hạn hoặc không dùng mật khẩu | Cơ chế cấp, hết hạn và thu hồi riêng; không báo cáo là đã xử lý chỉ bằng đổi mật khẩu khác |

API key, token, private key và chứng thư có vòng đời riêng. Chính sách mật khẩu có thể liên kết với các chính sách credential đó nhưng không thay thế chúng. Đổi mật khẩu không tự thu hồi khóa SSH, API key hoặc token độc lập của cùng tài khoản.

### 2.2. Phân biệt các thao tác

| Khái niệm | Ý nghĩa trong bài |
|---|---|
| Đổi mật khẩu | Thay mật khẩu của tài khoản theo cơ chế đích hỗ trợ |
| Reset mật khẩu | Đặt lại bằng thẩm quyền quản trị hoặc khôi phục, có thể không cần mật khẩu hiện tại |
| Luân chuyển có quản lý | Phối hợp tạo giá trị mới, thay đổi ở đích, cập nhật nơi cấp phát/consumer và xác minh kết quả |
| Đối soát credential | Xác định trạng thái thực tế khi vault, đích hoặc bộ điều phối không thống nhất |
| Thu hồi quyền/phiên | Chấm dứt khả năng truy cập hoặc phiên hiện hữu theo cơ chế liên quan |

Một lần reset thành công chưa tự đáp ứng toàn bộ yêu cầu luân chuyển. Tương tự, một phiên được đóng không chứng minh giá trị mật khẩu đã bị vô hiệu hóa.

## 3. Kiểm kê và ownership trước khi đặt lịch

Trước khi áp dụng chính sách, mỗi mật khẩu cần gắn với đúng danh tính và miền quản lý. Tên tài khoản giống nhau trên hai máy không chứng minh cùng tài khoản hoặc cùng mật khẩu.

Thông tin cần có gồm:

- Định danh tài khoản, nguồn thẩm quyền, tài nguyên đích và mức đặc quyền.
- Credential reference trong vault, trường bí mật, phiên bản và cơ chế phân phối.
- Chủ sở hữu tài khoản, đơn vị quản lý credential và người chịu trách nhiệm consumer.
- Những người hoặc workload có quyền lấy mật khẩu, dùng qua broker hoặc giữ bản sao.
- Dịch vụ, tác vụ định kỳ, pipeline, máy và ứng dụng phụ thuộc.
- Khả năng đổi/reset, hạn chế định dạng và cơ chế khôi phục được cho phép.
- Các mốc thay đổi đã xác nhận, kiểm tra gần nhất, trạng thái lỗi và ngoại lệ.

Danh sách consumer phải bao gồm tác vụ ít chạy, công việc khôi phục và hệ thống ngoài giờ. Không thấy hoạt động trong một cửa sổ ngắn chưa đủ kết luận mật khẩu không còn cần thiết.

### Trách nhiệm điển hình

| Vai trò | Trách nhiệm |
|---|---|
| Chủ sở hữu chính sách | Duy trì lớp tài khoản, điều kiện, thời hạn, ngoại lệ và tiêu chí đánh giá |
| Chủ sở hữu tài khoản/hệ thống | Xác nhận nhu cầu, quyền và mức ảnh hưởng khi thay đổi |
| Chủ sở hữu consumer | Cập nhật ứng dụng/tác vụ, xác minh khả năng sử dụng và xử lý lỗi |
| Đơn vị vận hành vault/PAM | Bảo vệ giá trị mới, điều phối phiên bản, cấp phát và đối soát |
| Đơn vị quản trị hệ thống đích | Cung cấp hoặc thực hiện thao tác đổi/reset theo thẩm quyền |
| Đội ứng phó sự cố | Quyết định ưu tiên cô lập, thu hồi và bảo toàn bằng chứng khi nghi lộ |

Tài khoản không có owner là một thiếu sót cần xử lý. Không loại nó khỏi mẫu số, coi là đã được miễn hoặc tự đổi mật khẩu mà không biết tác động.

## 4. Xác định thời điểm luân chuyển

### 4.1. Theo lịch dựa trên phân loại

Tổ chức cần quy định cho từng lớp tài khoản:

- Tuổi mật khẩu tối đa hoặc lịch thực hiện tương ứng với rủi ro.
- Cửa sổ vận hành và thời gian hoàn tất dự kiến.
- Thời điểm cảnh báo trước hạn và đầu mối nhận việc.
- Hành vi khi quá hạn hoặc không xác minh được lần đổi gần nhất.
- Điều kiện được trì hoãn và thẩm quyền cho phép.

Không có một con số duy nhất phù hợp với mọi tài khoản đặc quyền. Khoảng thời gian ngắn nhưng không thực thi được hoặc làm dịch vụ liên tục gián đoạn không phải một chính sách hiệu quả. Cần cân nhắc giảm quyền, hạn chế xuất secret hoặc chuyển sang credential ngắn hạn bên cạnh việc điều chỉnh lịch.

Tuổi mật khẩu phải dựa trên lần thay đổi có hiệu lực ở đích đã được xác minh theo tiêu chí chính sách. Không đặt lại tuổi chỉ vì tạo thêm một version trong vault, cập nhật metadata hoặc chạy job nhưng chưa đổi được mật khẩu.

Nếu thiếu bằng chứng về lần thay đổi ở đích, trạng thái là chưa xác minh. Không mặc định ngày tạo bản ghi inventory là ngày đổi mật khẩu.

### 4.2. Theo sự kiện

| Sự kiện | Hướng xử lý cần được chính sách xác định |
|---|---|
| Nghi ngờ hoặc xác nhận lộ mật khẩu | Ưu tiên ứng phó, xác định đích/consumer và quyền còn hiệu lực; không chờ lịch định kỳ |
| Mật khẩu đặc quyền được tiết lộ trực tiếp cho người dùng | Xác định yêu cầu đổi sau sử dụng hoặc trước lần cấp tiếp, có xử lý sử dụng đồng thời |
| Nhân sự hoặc bên hỗ trợ không còn được giữ secret | Đánh giá khả năng họ biết/giữ bản sao và xử lý credential, quyền và phiên liên quan |
| Tiếp nhận tài khoản vào PAM | Xác minh quyền quản lý, phụ thuộc và thực hiện thay đổi ban đầu theo luồng được phép |
| Sử dụng tài khoản khẩn cấp | Xử lý sau sử dụng, kiểm tra sẵn sàng và cập nhật nơi bảo quản có kiểm soát |
| Phát hiện bản sao ngoài nguồn quản lý | Điều tra phạm vi, thu hồi hoặc luân chuyển phù hợp và xử lý nơi lưu bản sao |
| Vault và đích không đồng bộ | Đối soát và khôi phục theo luồng riêng, không coi là một lần đổi đã hoàn tất |

Không phải mọi phiên qua broker đều đồng nghĩa người dùng đã nhận mật khẩu. Chính sách có thể phân biệt phiên không xuất secret với checkout hiển thị giá trị, nhưng phải dựa trên cơ chế thực tế.

Với sự cố, tốc độ luân chuyển phải được quyết định cùng biện pháp cô lập và tác động vận hành. Có thể cần ngăn cấp phát hoặc hạn chế truy cập trước khi hoàn tất phân phối credential mới. Không để lo ngại thiếu consumer trở thành trì hoãn vô thời hạn; cần đầu mối và quyết định rõ ràng.

## 5. Những yêu cầu chính sách cần quy định

| Nhóm yêu cầu | Câu hỏi cần trả lời |
|---|---|
| Giá trị mới | Ai sinh, bằng cơ chế nào, có tương thích đích và tránh tái sử dụng không? |
| Bảo vệ secret | Giá trị mới và cũ được bảo quản ở đâu; ai được đọc; có bị lộ qua log hoặc tham số tiến trình không? |
| Thực thi | Dùng danh tính nào để đổi; quyền có giới hạn theo tài khoản và đích không? |
| Phê duyệt và cửa sổ | Khi nào tự động, khi nào cần phối hợp thay đổi hoặc phê duyệt riêng? |
| Phụ thuộc | Consumer nào phải cập nhật và ai xác nhận? |
| Xác minh | Tiêu chí nào chứng minh đích chấp nhận mới và xử lý cũ đúng yêu cầu? |
| Lỗi | Retry, đối soát, khôi phục và chuyển cấp theo điều kiện nào? |
| Phiên và token | Những quyền phát sinh trước đó có còn hiệu lực và được xử lý ra sao? |
| Ngoại lệ | Ai có thẩm quyền, được trì hoãn bao lâu và điều kiện kết thúc là gì? |
| Bằng chứng | Ghi gì để xác minh kết quả mà không lưu nội dung mật khẩu? |

Mật khẩu mới nên được sinh bằng cơ chế ngẫu nhiên an toàn phù hợp với khả năng của đích, không xây từ tên hệ thống, ngày tháng hoặc quy luật đổi số đuôi. Cần kiểm tra các ràng buộc đầu vào của hệ thống trước khi áp dụng để tránh cắt ngắn hoặc xử lý ký tự ngoài dự kiến.

Không đưa mật khẩu vào mã nguồn, file cấu hình không được bảo vệ, ticket, log debug hoặc tham số dòng lệnh có thể bị quan sát. Quyền đọc credential cũng phải được giới hạn theo nhiệm vụ; tài khoản vận hành job không mặc nhiên cần quyền đọc mọi secret trong vault.

## 6. Vòng đời một lần luân chuyển

Luồng tham khảo:

```text
Đến hạn hoặc có sự kiện
    ↓
Kiểm tra tài khoản, đích, ownership và consumer
    ↓
Chuẩn bị giá trị mới trong vùng được bảo vệ
    ↓
Thay đổi mật khẩu ở đích theo chiến lược đã chọn
    ↓
Xác minh trạng thái đích và công bố phiên bản phù hợp
    ↓
Cập nhật/đối soát consumer và kiểm tra chức năng
    ↓
Xác minh mật khẩu cũ và xử lý phiên/token theo yêu cầu
    ↓
Hoàn tất bằng chứng hoặc chuyển đối soát/khôi phục
```

Không có một thứ tự cập nhật vault–đích–consumer duy nhất an toàn cho mọi hệ thống. Chính sách phải yêu cầu chiến lược phù hợp với khả năng đích và giới hạn gián đoạn; quy trình kỹ thuật cụ thể hiện thực chiến lược đó.

### 6.1. Chuẩn bị

Xác minh đúng danh tính đích, miền quản lý và kênh kết nối trước khi truyền credential. Không bỏ kiểm tra danh tính máy chủ hoặc hạ bảo vệ kết nối chỉ vì job gặp lỗi.

Cần biết tài khoản có đang được nhiều phiên hoặc workload sử dụng không. Với thay đổi có tác động, phối hợp cửa sổ vận hành và cơ chế tạm dừng cấp phát phù hợp. Chính sách phê duyệt truy cập của người thực hiện và quy trình thay đổi dịch vụ có thể liên kết nhưng không thay thế nhau.

Giá trị mới có thể được lưu ở trạng thái chờ trong vault hoặc vùng bảo vệ tương ứng. Không công bố nó cho consumer như phiên bản đang hoạt động trước khi điều kiện chuyển đổi đã được đáp ứng.

### 6.2. Các chiến lược cần phân biệt

| Khả năng của hệ thống | Chiến lược có thể lựa chọn | Điều cần kiểm soát |
|---|---|---|
| Một tài khoản chỉ có một mật khẩu được chấp nhận | Phối hợp thời điểm đổi và cập nhật consumer, có thể cần cửa sổ gián đoạn | Khoảng không đồng bộ, cache và cách khôi phục |
| Đích hỗ trợ hai credential đồng thời | Chuyển consumer sang credential mới rồi thu hồi cũ theo hạn | Thời gian chồng lấn và bằng chứng mọi consumer đã chuyển |
| Có thể dùng hai danh tính thay thế | Chuyển đổi có kiểm soát giữa hai tài khoản với quyền tương ứng | Tổng quyền, hai vòng đời danh tính và việc vô hiệu hóa bên cũ |
| Có cơ chế credential ngắn hạn phù hợp | Cấp và hết hạn theo cơ chế đó | Danh tính consumer, tái đánh giá và thu hồi thực tế |

Không giả định mọi tài khoản đều hỗ trợ hai mật khẩu cùng lúc. Hai tài khoản thay thế cũng không phải cùng một tài khoản có hai mật khẩu; phải kiểm kê và quản lý quyền của cả hai.

Giai đoạn chồng lấn, nếu có, cần thời hạn và người chịu trách nhiệm. Không giữ mật khẩu cũ vô thời hạn chỉ để tránh xử lý một consumer chưa rõ.

### 6.3. Xác minh kết quả

Tùy khả năng và phạm vi được phép, xác minh có thể gồm phản hồi thay đổi tin cậy, kiểm tra xác thực được giới hạn trên đúng đích, đối chiếu phiên bản được cấp phát và kiểm tra sức khỏe consumer.

Các phép xác minh phải tránh gây khóa tài khoản, tạo tải bất thường hoặc thử mật khẩu trên các đích ngoài phạm vi. Không dùng việc thử đăng nhập hàng loạt như cách suy ra nơi nào đang dùng chung mật khẩu.

Đăng nhập thành công bằng mật khẩu mới chưa chứng minh mọi consumer đã cập nhật. Nếu có nhiều đường xác thực, cache hoặc cơ chế đồng bộ, cần kiểm tra những đường liên quan theo tiêu chí và thời gian chấp nhận được của hệ thống.

### 6.4. Tiêu chí hoàn tất

Một lần luân chuyển chỉ được ghi hoàn tất khi đáp ứng các điều kiện áp dụng, chẳng hạn:

- Đích đã thay đổi và trạng thái được xác minh.
- Nguồn cấp phát đang công bố đúng phiên bản đã xác minh.
- Consumer trong phạm vi đã chuyển và chức năng cần thiết đạt tiêu chí kiểm tra.
- Mật khẩu cũ được xử lý theo yêu cầu của chiến lược, không còn được cấp lại ngoài ý muốn.
- Phiên, token hoặc đường xác thực khác đã được đánh giá và xử lý theo yêu cầu.
- Bằng chứng, thời điểm và phần ngoại lệ còn lại được ghi đúng trạng thái.

Nếu còn thiếu một điều kiện bắt buộc, giữ trạng thái chưa hoàn tất hoặc ngoại lệ được xác minh. Không cập nhật nhãn thành công chỉ vì job đã chạy hết bước cuối.

## 7. Quản lý trạng thái và lỗi từng phần

Một mô hình trạng thái có thể gồm:

```text
PLANNED → PREPARED → TARGET_CHANGE_REQUESTED
                           ↓
                TARGET_STATE_VERIFIED
                           ↓
                CONSUMERS_UPDATED
                           ↓
                 RETIREMENT_VERIFIED
                           ↓
                       COMPLETED

Bất kỳ giai đoạn có kết quả chưa rõ:
    RECONCILIATION_REQUIRED → RECOVERY hoặc tiếp tục sau xác minh
```

Đây là mô hình minh họa. Các hệ thống có thể cần thêm trạng thái để phân biệt lỗi đã xác định, kết quả chưa rõ, chờ consumer và chờ thu hồi phiên.

### 7.1. Timeout không đồng nghĩa thay đổi thất bại

Hệ thống đích có thể đã đổi mật khẩu nhưng phản hồi bị mất. Nếu bộ điều phối gọi lại mù hoặc tiếp tục cấp mật khẩu cũ, nó có thể tạo mất đồng bộ hoặc gây nhiều lỗi xác thực.

Cần mã thao tác ổn định, lịch sử bước, tham chiếu phiên bản được bảo vệ và cách đối soát trạng thái đích. Cơ chế điều phối phải xử lý gọi lặp; không giả định API đổi mật khẩu của đích tự có tính idempotent.

Một tài khoản chỉ nên có một luồng luân chuyển chủ động tại một thời điểm theo cơ chế điều phối. Nếu dùng khóa có thời hạn, cần xử lý worker cũ tiếp tục chạy sau khi khóa hết hạn. Khóa trong kho điều phối không tự tạo giao dịch nguyên tử với hệ thống đích.

### 7.2. Đích đã đổi nhưng vault chưa công bố được

Không đánh dấu hoàn tất và không tiếp tục phát credential chưa được xác minh. Giữ giá trị chờ trong vùng bảo vệ, đối soát kết quả và công bố sau khi đủ điều kiện. Cần xác định consumer nào vẫn giữ bản cũ và mức ảnh hưởng.

Nếu giá trị mới không thể phục hồi an toàn, có thể cần reset có thẩm quyền rồi phân phối lại theo quy trình khôi phục. Không tìm mật khẩu từ log debug hoặc bản sao không kiểm soát để xử lý nhanh.

### 7.3. Vault có bản mới nhưng đích vẫn dùng bản cũ

Phiên bản mới cần được giữ ở trạng thái chưa sẵn sàng hoặc được xử lý theo mô hình đã thiết kế. Bộ cấp phát không nên coi version mới nhất là đang hoạt động chỉ vì nó tồn tại.

Các trường như `created_at`, `published_at`, `target_change_verified_at` và `consumers_verified_at` trả lời những câu hỏi khác nhau. Có thể lưu riêng để tránh nhầm một lần ghi vault với một lần luân chuyển hoàn tất.

### 7.4. Consumer cập nhật không đồng đều

Theo dõi consumer và instance chưa chuyển, kể cả tác vụ ít chạy. Phân biệt đã cập nhật cấu hình với đã nạp vào tiến trình hoặc đã sử dụng thành công. Không chỉ kiểm tra một replica rồi suy ra cả cụm đã chuyển.

Nếu quá hạn, chuyển cấp hoặc áp dụng quyết định đã định về thu hồi, gián đoạn có kiểm soát hoặc ngoại lệ. Không tự mở rộng thời gian giữ credential cũ mà không có trách nhiệm và mốc kết thúc.

### 7.5. Không tự quay lại mật khẩu nghi đã lộ

Khôi phục dịch vụ không nhất thiết là khôi phục giá trị mật khẩu cũ. Nếu lý do luân chuyển là nghi lộ, đưa lại giá trị cũ có thể khôi phục đường truy cập của bên không được phép.

Cần phương án khôi phục phù hợp, có thể là credential mới khác hoặc danh tính dự phòng đã được quản trị. Việc giữ lịch sử secret hoặc bản sao lưu cần kiểm soát quyền và thời gian lưu, đồng thời ngăn khôi phục hệ thống cũ làm phát hành lại credential đã bị thu hồi.

## 8. Mật khẩu cũ, token và phiên là các đối tượng khác nhau

Đổi mật khẩu có thể ngăn một số lần xác thực mới bằng giá trị cũ. Tuy nhiên, nó không bảo đảm mọi phiên, kết nối, token hoặc credential khác của tài khoản đều mất hiệu lực.

Chính sách cần xác định khi nào phải:

- Kết thúc phiên quản trị hoặc phiên broker liên quan.
- Thu hồi token, refresh token hoặc credential dẫn xuất nếu cơ chế hỗ trợ.
- Đóng hoặc tái xác thực kết nối dịch vụ theo mức rủi ro.
- Xử lý các khóa hoặc API key độc lập của danh tính.
- Xác minh quyền thực tế đã chấm dứt sau sự kiện lộ credential.

Với luân chuyển định kỳ, việc xử lý kết nối sống lâu có thể khác với ứng phó xâm nhập. Sự khác biệt cần được quyết định trong chính sách và quy trình, không để mỗi job tự chọn.

JIT/JEA giúp giảm thời gian và phạm vi của quyền được cấp, nhưng không thay thế quản lý mật khẩu nền nếu danh tính đặc quyền vẫn dùng mật khẩu tĩnh. Ngược lại, mật khẩu được đổi thường xuyên chưa chứng minh quyền của tài khoản đã tối thiểu.

## 9. Ví dụ đặc tả chính sách

YAML dưới đây là **mô hình minh họa**, không phải cấu hình thực thi của một sản phẩm. Các lịch và thời hạn cụ thể phải được tổ chức định nghĩa trong catalog được tham chiếu.

```yaml
policy_id: PAM-PASSWORD-ROTATION
version: 5
state: active
owner_ref: team-credential-governance
scope:
  credential_type: password
  account_classes:
    - managed_shared_admin
    - managed_emergency_admin
    - static_privileged_service
classification_rules_ref: credential-risk-catalog-v3
schedule_rules_ref: privileged-password-schedules-v4
event_triggers:
  - suspected_disclosure
  - confirmed_disclosure
  - authorized_secret_export_followup
  - emergency_account_use
  - unmanaged_copy_detected
  - vault_target_mismatch
prerequisites:
  verified_account_and_target_required: true
  accountable_owner_required: true
  consumer_inventory_required: true
  supported_recovery_plan_required: true
execution:
  single_active_rotation_per_account: true
  protect_pending_secret: true
  publish_only_after_defined_verification: true
  retry_requires_state_awareness: true
  unknown_target_result: reconciliation_required
completion:
  target_change_verified: required
  active_vault_version_verified: required
  consumer_transition_verified: required
  old_password_retirement_verified: required
  session_and_token_disposition_recorded: required
  evidence_without_secret_values: required
exceptions:
  authorized_decision_required: true
  explicit_expiry_required: true
  compensating_controls_required: true
```

Các tham chiếu catalog phải có nội dung và phiên bản thực sự được kiểm soát. Nếu chưa xác định lịch, consumer hoặc khả năng khôi phục, không được coi chính sách đã triển khai đầy đủ chỉ vì bản ghi YAML hợp lệ.

`old_password_retirement_verified` cần được giải thích theo khả năng đích. Không bắt buộc thử giá trị cũ lặp lại khi có cách xác minh phù hợp khác; cách kiểm tra phải được cho phép và tránh gây khóa tài khoản.

## 10. Tình huống: tài khoản database có ba consumer

Danh tính `svc-orders-db` được dùng bởi API production, batch worker và tác vụ backup cuối tháng. Mật khẩu được quản lý trong vault. Đội vận hành chỉ nhìn log bảy ngày nên ban đầu không thấy tác vụ backup.

### Thiết kế trước khi luân chuyển

Cần xác nhận đủ ba consumer, cách mỗi nơi nạp credential, lịch chạy, chủ sở hữu và điều kiện kiểm tra. Đặc biệt, kiểm tra tác vụ backup không nên bị hoãn đến cuối tháng mới biết mật khẩu mới có hoạt động; cần phương án xác minh phù hợp được cho phép.

Nếu đích chỉ hỗ trợ một mật khẩu, kế hoạch phải tính khoảng chuyển đổi giữa đích và consumer. Không giả định có thể giữ mật khẩu cũ và mới cho cùng tài khoản để chuyển dần. Nếu chọn hai danh tính thay thế, phải đánh giá quyền và vòng đời của cả hai.

### Lỗi xảy ra

Đích nhận yêu cầu đổi, nhưng kết nối tới bộ điều phối bị ngắt trước phản hồi. Vault vẫn đang công bố phiên bản cũ.

Hướng xử lý:

1. Ghi trạng thái chưa rõ ở đích và chặn việc luân chuyển đồng thời hoặc cấp phát không an toàn theo thiết kế.
2. Dùng bằng chứng thao tác và giá trị chờ được bảo vệ để xác minh trạng thái, với giới hạn thử phù hợp.
3. Nếu xác nhận giá trị mới đã có hiệu lực, công bố phiên bản tương ứng và tiếp tục cập nhật consumer.
4. Nếu không thể xác định hoặc khôi phục an toàn, chuyển luồng phục hồi có thẩm quyền.
5. Kiểm tra cả API, batch và backup; ghi phần còn chờ thay vì đánh dấu toàn bộ đã xong.
6. Xử lý credential cũ, kết nối và token theo loại sự kiện; lưu kết quả không chứa secret.

Nếu đợt này bắt đầu vì nghi lộ, việc quyền hoặc phiên cũ còn tồn tại cần được xem xét trong ứng phó sự cố. Không chỉ tập trung làm cho ứng dụng hết lỗi rồi đóng phát hiện lộ credential.

## 11. Ngoại lệ và hệ thống khó luân chuyển

Một hệ thống cũ có thể không hỗ trợ tự động đổi mật khẩu hoặc có consumer chưa thể cập nhật an toàn. Chính sách cần cơ chế ngoại lệ, không nên có danh sách miễn vô thời hạn chỉ ghi tên hệ thống.

Một ngoại lệ nên có:

- Tài khoản, tài nguyên, yêu cầu chưa đáp ứng và nguyên nhân kỹ thuật.
- Rủi ro, chủ thể chịu trách nhiệm và người có thẩm quyền chấp nhận.
- Biện pháp bổ sung như hạn chế nơi kết nối, giảm người có thể lấy secret, giới hạn quyền hoặc tăng giám sát.
- Lịch kiểm tra, thời hạn và kế hoạch khắc phục.
- Hành vi khi nghi lộ hoặc khi ngoại lệ hết hiệu lực.

Các biện pháp bổ sung không làm mật khẩu cũ tự hết rủi ro. Nếu hệ thống không thể đổi trong thời gian mong muốn, cần phản ánh đúng trạng thái để quyết định ưu tiên và kiểm soát.

Không coi “đang dùng trong production” là đủ lý do trì hoãn mọi lần. Cũng không đổi đột ngột một tài khoản dịch vụ chưa biết phụ thuộc chỉ để làm chỉ số đúng hạn. Quyết định phải có căn cứ, trách nhiệm và mốc xử lý.

## 12. Bằng chứng và chỉ số quản trị

### 12.1. Bằng chứng cần nối được các bước

| Nhóm bằng chứng | Thông tin |
|---|---|
| Căn cứ | Policy ID/phiên bản, lớp tài khoản, lịch hoặc sự kiện kích hoạt |
| Đối tượng | Danh tính, miền quản lý, đích, credential reference và owner |
| Điều phối | Mã thao tác, thời điểm, danh tính thực thi, bước và kết quả |
| Đích | Thay đổi và xác minh hiệu lực theo phương pháp được phép |
| Vault | Phiên bản chờ/hoạt động, thời điểm công bố và kết quả đối soát |
| Consumer | Danh sách, trạng thái cập nhật, kiểm tra và phần chưa hoàn tất |
| Thu hồi | Xử lý mật khẩu cũ, token, phiên và đường xác thực liên quan |
| Ngoại lệ/lỗi | Lý do, trách nhiệm, thời hạn và quyết định xử lý |

Không cần ghi giá trị mật khẩu để chứng minh đã luân chuyển. Bản ghi có thể dùng mã credential, phiên bản, mã thao tác và kết quả xác minh. Tránh lưu cả dấu băm mật khẩu vào kho báo cáo thông thường như cách thay thế việc bảo vệ secret; mật khẩu có thể đoán được và dữ liệu đó tạo rủi ro riêng.

Bảo vệ log khỏi sửa/xóa trái phép, hạn chế người xem và giữ thời gian nhất quán để ghép sự kiện. Thời điểm cập nhật vault, thời điểm đích đổi và thời điểm consumer hoàn tất nên được tách khi cần.

### 12.2. Chỉ số với định nghĩa rõ

```text
Tỷ lệ đúng hạn có xác minh =
    số credential trong phạm vi đáp ứng lịch/sự kiện
    và tiêu chí hoàn tất đã quy định
    / tổng số credential thuộc phạm vi đánh giá
```

Nên báo cáo riêng các nhóm đúng hạn, quá hạn, chưa xác minh, đang lỗi và ngoại lệ còn hiệu lực. Ngoại lệ không nên biến mất khỏi báo cáo rủi ro hoặc được tự tính như một lần luân chuyển thành công.

Ví dụ, có mười credential trong phạm vi: bảy đạt tiêu chí, một quá hạn, một đang đối soát và một có ngoại lệ còn hiệu lực. Không báo `10/10` đã hoàn tất. Có thể báo `7/10` đạt tiêu chí luân chuyển, đồng thời nêu trạng thái ba đối tượng còn lại theo quy tắc báo cáo.

Các chỉ số bổ sung có thể gồm:

- Thời gian xử lý từ khi phát hiện nghi lộ đến khi đạt mục tiêu thu hồi đã xác định.
- Số lần mất đồng bộ vault–đích và thời gian đối soát.
- Tỷ lệ consumer đã xác minh cập nhật.
- Số lần job gây lỗi xác thực, khóa tài khoản hoặc gián đoạn.
- Tuổi ngoại lệ và số credential chưa có owner/consumer inventory đầy đủ.

Số lần job chạy hoặc số version mới tạo trong vault không phải số lần luân chuyển hoàn tất. Tỷ lệ tốt hơn sau khi bỏ các đích lỗi khỏi inventory cũng không chứng minh rủi ro giảm.

## 13. Bài tập và ma trận nghiệm thu

### Bài tập thiết kế

Chọn một tài khoản dịch vụ dùng mật khẩu tĩnh trên dữ liệu tổng hợp. Giả định nó có ba consumer với cách nạp credential khác nhau. Viết chính sách áp dụng, nguồn ownership, lịch và sự kiện kích hoạt, chiến lược chuyển đổi, điều kiện hoàn tất và cách xử lý timeout.

Sau đó bổ sung tình huống mật khẩu đã bị lộ. Chỉ ra phần nào phải thay đổi so với luân chuyển định kỳ, đặc biệt với mật khẩu cũ, phiên đang mở và khả năng khôi phục.

### Ma trận nghiệm thu trên môi trường thực hành được phép

Không dùng credential thật trong tài liệu, dữ liệu kiểm thử hoặc đầu ra minh họa.

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Job chỉ tạo version mới trong vault, chưa đổi được đích | Chưa ghi luân chuyển hoàn tất hoặc đặt lại tuổi mật khẩu |
| Đích đổi thành công nhưng phản hồi bị mất | Chuyển đối soát, không retry mù hoặc kết luận chưa đổi |
| Vault không công bố được sau khi đích đã đổi | Giữ trạng thái lỗi rõ, bảo vệ giá trị chờ và xử lý cấp phát/khôi phục |
| Hai job cùng nhắm một tài khoản | Điều phối ngăn xung đột và xử lý worker cũ theo thiết kế |
| Một consumer hoặc replica chưa nhận phiên bản mới | Không tự coi mọi consumer đã chuyển |
| Tác vụ ít chạy không có log trong cửa sổ quan sát | Vẫn được xác minh qua inventory và chủ sở hữu |
| Đích không hỗ trợ hai mật khẩu | Không áp chiến lược chồng lấn như thể có hỗ trợ |
| Mật khẩu mới hoạt động nhưng token/phiên cũ còn hiệu lực | Đánh giá và xử lý theo chính sách, không suy ra đã thu hồi toàn bộ |
| Sự kiện nghi lộ xảy ra ngay sau lần đổi định kỳ | Kích hoạt ứng phó theo sự kiện, không chờ chu kỳ kế tiếp |
| Khôi phục sau lỗi có nguy cơ đưa lại giá trị nghi lộ | Dùng quyết định khôi phục an toàn có thẩm quyền |
| Mật khẩu không phù hợp giới hạn đích | Phát hiện trước khi công bố, không tạo mất đồng bộ ngoài kiểm soát |
| Ngoại lệ hết hạn hoặc owner không còn hợp lệ | Phát hiện, chuyển xử lý và giữ đúng trạng thái báo cáo |
| Kiểm tra log và bằng chứng | Có mã thao tác/phiên bản cần thiết, không có nội dung secret |
| Đánh giá hoàn tất | Đối chiếu đích, vault, consumer và yêu cầu thu hồi, không chỉ trạng thái job |

Một password rotation policy có hiệu quả phải xác định được khi nào cần đổi, cách đổi an toàn và bằng chứng nào cho thấy trạng thái mới đã có hiệu lực. Việc duy trì phụ thuộc, ownership và xử lý lỗi là điều kiện để luân chuyển giảm rủi ro mà vẫn hỗ trợ vận hành hệ thống.