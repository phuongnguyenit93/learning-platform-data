# Dữ liệu cá nhân

## 1. Mục tiêu và phạm vi

Trong chương **Phân loại dữ liệu**, dữ liệu cá nhân cần được nhận diện theo khả năng gắn thông tin với một con người trong bối cảnh sử dụng thực tế. Tên trường hay vị trí lưu không đủ để quyết định mức bảo vệ: một mã học viên không thể hiện tên vẫn có thể dẫn đến hồ sơ đầy đủ khi được nối với dữ liệu khác.

Mục tiêu của bài học là chuyển việc nhận diện và phân loại dữ liệu cá nhân thành **yêu cầu bảo mật cụ thể, đo được và có thể kiểm chứng**. Người học sẽ thực hành xác định dữ liệu cần bảo vệ, mô tả rủi ro, chọn ranh giới kiến trúc và đặt tiêu chí chấp nhận cho xác thực, phân quyền, xử lý dữ liệu, logging và phục hồi.

Sau bài học, người học có thể:

- Phân biệt định danh trực tiếp, định danh gián tiếp, dữ liệu suy ra và dữ liệu đã biến đổi.
- Lập hồ sơ dữ liệu theo mục đích, chủ thể, luồng xử lý, nơi lưu và thời hạn tồn tại.
- Đánh giá bí mật, toàn vẹn, sẵn sàng cùng hậu quả đối với cá nhân.
- Viết yêu cầu kiểm soát truy cập, xuất dữ liệu, lưu giữ, xóa và phục hồi có cách kiểm chứng.
- Truy vết từ trường dữ liệu đến kịch bản đe dọa, yêu cầu và bằng chứng kiểm thử.

Phân loại trong bài phục vụ thiết kế bảo mật. Các nhãn mức độ và thời gian minh họa là quy ước của hệ thống giả định, không phải định nghĩa pháp lý hay ngưỡng áp dụng chung.

## 2. Nhận diện dữ liệu cá nhân theo ngữ cảnh

### 2.1. Khái niệm làm việc

Trong phạm vi bài học, **dữ liệu cá nhân** là thông tin gắn với hoặc có thể được dùng để nhận diện một cá nhân, trực tiếp hay khi kết hợp với thông tin khác trong bối cảnh xử lý. Việc đánh giá cần xét ai có thể tiếp cận dữ liệu, họ có thêm nguồn thông tin nào và có thể thực hiện phép liên kết nào.

Ví dụ, chuỗi `learner_8f2c` có vẻ chỉ là một mã kỹ thuật. Tuy nhiên, nếu bộ phận hỗ trợ có thể tra mã này để lấy tên và email, lịch sử hoạt động gắn với mã vẫn cần được quản lý như dữ liệu liên quan tới cá nhân.

Không nên chỉ hỏi “trường này có chứa tên không?”. Những câu hỏi hữu ích hơn là:

- Có thể biết, phân biệt hoặc theo dõi hoạt động của cùng một người từ dữ liệu này không?
- Có thể nối dữ liệu với tài khoản, thiết bị, vị trí hoặc một nguồn thông tin khác không?
- Ai có bảng ánh xạ, quyền truy vấn hoặc kiến thức bổ sung để thực hiện việc nối?
- Dữ liệu có tiết lộ điều gì về hành vi, năng lực, hoàn cảnh hay quan hệ của người đó không?
- Khả năng nhận diện và hậu quả thay đổi thế nào nếu tập dữ liệu bị xuất hàng loạt?

### 2.2. Các dạng thường gặp

| Dạng dữ liệu | Ví dụ trong nền tảng học trực tuyến | Vì sao cần xem xét |
|---|---|---|
| Định danh trực tiếp | Họ tên, email, số điện thoại | Có thể liên hệ hoặc đối chiếu với một người tương đối trực tiếp |
| Mã định danh nội bộ | Mã tài khoản, mã học viên, mã hồ sơ hỗ trợ | Cho phép nối các bản ghi và thường có đường dẫn tới danh tính |
| Dấu vết thiết bị và truy cập | Địa chỉ IP, dấu thời gian đăng nhập, mã thiết bị | Có thể hỗ trợ nhận diện hoặc liên kết hoạt động tùy dữ liệu bổ sung |
| Dữ liệu hoạt động | Khóa học đã đăng ký, lịch sử làm bài, tiến độ học | Mô tả hành vi và kết quả của người gắn với tài khoản |
| Dữ liệu suy ra | Nhận định về năng lực, dự đoán khả năng bỏ học | Là thông tin mới được suy từ dữ liệu khác và có thể ảnh hưởng cách đối xử với người học |
| Nội dung tự do | Tin nhắn hỗ trợ, bài tự giới thiệu, tệp đính kèm | Có thể chứa thông tin ngoài dự kiến, kể cả về những người khác |
| Dữ liệu xác thực gắn với tài khoản | Thông tin kiểm chứng mật khẩu, token khôi phục, bí mật xác thực | Vừa liên quan tới cá nhân vừa có khả năng mở quyền truy cập; cần lớp bảo vệ riêng |

Dữ liệu cá nhân không chỉ nằm trong bảng `users`. Nó có thể xuất hiện trong URL, log, bản sao lưu, chỉ mục tìm kiếm, tệp xuất, thông báo email, công cụ phân tích và bộ dữ liệu dùng để thử nghiệm.

### 2.3. Đánh giá khả năng liên kết

Một bản ghi chỉ có thời điểm học và mã lớp có thể khó nhận diện nếu đứng riêng. Khi nối với lịch học công khai hoặc danh sách lớp ít người, khả năng nhận diện có thể tăng lên. Vì vậy, mức bảo vệ của một tập dữ liệu không thể suy ra chỉ từ từng cột độc lập.

```text
[Mã học viên + tiến độ] ----+
                          +--> [Hồ sơ học tập gắn với người cụ thể]
[Mã học viên + email] -----+
```

Quyền đọc từng tập dữ liệu và quyền nối các tập dữ liệu đều cần được xem xét. Tách bảng nhưng cho cùng một tài khoản truy vấn tự do toàn bộ các bảng chưa tạo ra ranh giới bảo vệ có ý nghĩa.

## 3. Phân biệt tính cá nhân, mức nhạy cảm và mức quan trọng

### 3.1. Dữ liệu cá nhân không có cùng một mức bảo vệ

Tính cá nhân trả lời câu hỏi dữ liệu có liên quan tới một người có thể nhận diện hay không. Mức nhạy cảm và mức quan trọng trả lời câu hỏi hậu quả khi dữ liệu bị lộ, bị sửa hoặc không còn sử dụng được nghiêm trọng đến đâu.

Tên người giảng dạy được phê duyệt hiển thị công khai vẫn là thông tin liên quan tới cá nhân. Việc công khai đúng mục đích không có nghĩa mọi thông tin khác của giảng viên cũng được công khai, hoặc không cần bảo vệ tính toàn vẹn của hồ sơ đó.

Ngược lại, thông tin đăng nhập hay token khôi phục có thể tạo ra rủi ro chiếm tài khoản ngay cả khi bản thân chuỗi bí mật không thể hiện tên người dùng. Nhãn “dữ liệu cá nhân” không thay thế nhãn “bí mật xác thực”. Một dữ liệu có thể cần nhiều thuộc tính kiểm soát cùng lúc.

### 3.2. Đánh giá theo hậu quả

| Thuộc tính | Câu hỏi đánh giá | Ví dụ hậu quả |
|---|---|---|
| Bí mật | Ai được biết dữ liệu? Việc lộ từng bản ghi hoặc cả tập gây ảnh hưởng gì? | Lộ email, lịch học, nội dung trao đổi riêng hoặc kết quả học tập |
| Toàn vẹn | Ai được sửa? Sai lệch có thể thay đổi quyết định nào? | Điểm bị chỉnh sai, email nhận thông báo bị đổi, chứng nhận cấp nhầm |
| Sẵn sàng | Khi nào người dùng hoặc nghiệp vụ cần dữ liệu? Mất dữ liệu có thể phục hồi không? | Không truy cập được tiến độ, không xác minh được kết quả trước hạn đăng ký |
| Phạm vi tác động | Một lỗi ảnh hưởng bao nhiêu người và kéo dài bao lâu? | Tệp xuất chứa dữ liệu của cả tổ chức bị chia sẻ sai |
| Khả năng kết hợp | Những nguồn nào giúp nhận diện hoặc suy ra thêm thông tin? | Nối tiến độ, lịch truy cập và hồ sơ tổ chức để suy ra hành vi cá nhân |

Với dữ liệu suy ra, còn cần quan tâm nguồn gốc, thời điểm tính và khả năng sai. Một nhãn dự đoán “nguy cơ bỏ học” không phải sự thật chắc chắn về người học; quyền truy cập và việc dùng nhãn để ra quyết định phải được xác định riêng.

### 3.3. Một quy ước phân loại minh họa

Giả sử nhóm thiết kế dùng bốn mức sau cho **mức kiểm soát truy cập và tiết lộ**, đồng thời ghi riêng yêu cầu toàn vẹn và sẵn sàng:

| Mức minh họa | Ý nghĩa sử dụng | Ví dụ | Kiểm soát cần dẫn xuất |
|---|---|---|---|
| Công khai đã duyệt | Được phép hiển thị cho mọi người theo phạm vi đã xác định | Tên hiển thị và phần giới thiệu giảng viên đã duyệt | Kiểm soát xuất bản, chỉnh sửa và trường được phép công khai |
| Hạn chế theo nhiệm vụ | Chỉ người có quan hệ công việc phù hợp được đọc | Tên và mã học viên trong danh sách lớp của giảng viên phụ trách | Giới hạn theo lớp, tổ chức, chức năng và danh tính |
| Hạn chế cao | Việc tiết lộ có hậu quả lớn hoặc tập hợp nhiều thông tin về cá nhân | Hồ sơ liên hệ, điểm chi tiết, nội dung hỗ trợ riêng, tệp xuất nhiều người | Quyền chi tiết, kiểm soát xuất, lưu giữ và truy vết truy cập |
| Bí mật xác thực | Dữ liệu có thể dùng để mở hoặc khôi phục quyền truy cập | Token khôi phục, bí mật xác thực | Không đưa vào phản hồi thông thường; bảo vệ chuyên biệt và có khả năng vô hiệu hóa |

Đây là một quy ước minh họa, không phải hệ thống nhãn bắt buộc. Trong hồ sơ thực tế, mức cuối có thể được thể hiện bằng một thuộc tính bổ sung thay vì một bậc trong thang phân loại. Điều quan trọng là nhãn phải dẫn tới kiểm soát cụ thể và có người chịu trách nhiệm phê duyệt.

## 4. Lập hồ sơ dữ liệu và theo dõi các bản sao

### 4.1. Mẫu hồ sơ tối thiểu

| Trường hồ sơ | Nội dung cần làm rõ |
|---|---|
| Mã và tên dữ liệu | Định danh ổn định của tập dữ liệu hoặc nhóm trường |
| Chủ thể được mô tả | Người học, giảng viên, người liên hệ hoặc người được nhắc tới trong nội dung |
| Mục đích | Chức năng cụ thể cần dữ liệu và các mục đích khác phải xin phê duyệt nội bộ riêng |
| Nguồn | Người dùng nhập, dịch vụ bên ngoài cung cấp, hệ thống quan sát hay mô hình suy ra |
| Khả năng nhận diện | Trường nhận diện trực tiếp, mã liên kết, nguồn thông tin bổ sung và người có thể nối |
| Mức phân loại | Mức kiểm soát truy cập, yêu cầu toàn vẹn, sẵn sàng và lý do |
| Luồng và nơi tồn tại | Cơ sở dữ liệu, cache, log, chỉ mục, hàng đợi, tệp xuất, nhà cung cấp và bản sao lưu |
| Truy cập | Danh tính, vai trò, quan hệ với chủ thể, thao tác và điều kiện cho phép |
| Vòng đời | Thời điểm thu thập, điều kiện hết mục đích, thời hạn lưu, xóa và xử lý khi phục hồi |
| Trách nhiệm và bằng chứng | Người quyết định mục đích, nhóm vận hành, yêu cầu bảo mật và bằng chứng kiểm chứng |

Không ghi dữ liệu cá nhân thật hoặc bí mật thật vào ví dụ hồ sơ. Có thể dùng tên trường, dữ liệu giả và mã tham chiếu tới hệ thống quản lý phù hợp.

### 4.2. Hồ sơ ví dụ

Giả sử một nền tảng học trực tuyến phục vụ nhiều tổ chức. Mỗi người học thuộc một tổ chức; giảng viên chỉ được xem thông tin cần thiết của lớp được phân công. Bộ phận hỗ trợ chỉ được truy cập hồ sơ theo yêu cầu hỗ trợ có phạm vi xác định.

| Mã | Nhóm dữ liệu | Mục đích | Phân loại và lý do |
|---|---|---|---|
| PD-01 | Mã tài khoản, tên, email liên hệ | Đăng nhập, hiển thị hồ sơ, gửi thông báo | Email và hồ sơ liên hệ bị hạn chế cao; tên hiển thị chỉ công khai nếu đã được duyệt cho mục đích đó |
| PD-02 | Đăng ký khóa học, tiến độ, điểm từng bài | Hiển thị kết quả và quản lý việc học | Hạn chế theo quan hệ lớp; điểm chi tiết cần giới hạn chặt việc đọc và sửa |
| PD-03 | Sự kiện truy cập, thời gian, IP | Phát hiện và điều tra sự cố | Dữ liệu liên quan cá nhân; chỉ nhóm có nhiệm vụ điều tra được tra cứu phần cần thiết |
| PD-04 | Nội dung và tệp đính kèm hỗ trợ | Giải quyết vấn đề do người dùng báo | Hạn chế cao vì nội dung tự do có thể chứa thông tin không dự kiến |
| PD-05 | Tệp xuất hồ sơ cá nhân | Cho người dùng xem và tải dữ liệu thuộc phạm vi của mình | Hạn chế cao vì tập hợp thông tin, dễ bị sao chép và chuyển tiếp |
| SEC-01 | Token khôi phục và thông tin kiểm chứng mật khẩu | Xác thực hoặc khôi phục truy cập | Bí mật xác thực, không được đưa vào tệp xuất hồ sơ thông thường |

Giới hạn nghiệp vụ này là đầu vào của yêu cầu bảo mật. Nếu sau đó cần báo cáo cho quản lý tổ chức, phải xác định thêm vai trò, trường dữ liệu và phạm vi được đọc; không tự mở toàn bộ dữ liệu cho mọi người mang vai trò quản lý.

### 4.3. Luồng dữ liệu và kế thừa kiểm soát

```text
[Người học] -> [API hồ sơ] -> [Cơ sở dữ liệu]
                    |               |
                    |               +--> [Cache / chỉ mục tìm kiếm]
                    |               +--> [Tác vụ tạo tệp xuất]
                    |               +--> [Bản sao lưu]
                    +--> [Log sự kiện]

[Thông báo] -> [Dữ liệu tối thiểu] -> [Dịch vụ gửi email bên ngoài]
```

Bản sao, trường suy ra và tập dữ liệu sau khi ghép phải được đánh giá lại. Nếu tệp xuất giữ nguyên email và kết quả học, không thể hạ mức bảo vệ chỉ vì nó là “tệp tạm”. Nếu bỏ email nhưng vẫn giữ mã học viên có thể tra ngược, thông tin vẫn còn khả năng liên kết.

Ngược lại, không cần giữ nguyên mọi kiểm soát của dữ liệu nguồn một cách máy móc khi đã có phép biến đổi làm giảm rủi ro thực sự. Việc thay đổi mức phân loại phải dựa trên phân tích kết quả, điều kiện truy cập và bằng chứng phù hợp.

## 5. Che dữ liệu, thay mã và ẩn danh

Các kỹ thuật biến đổi giải quyết những vấn đề khác nhau. Cần mô tả chính xác điều kiện chúng bảo vệ được và phần rủi ro vẫn còn.

| Kỹ thuật | Ví dụ | Giới hạn cần ghi trong yêu cầu |
|---|---|---|
| Che trên giao diện | Hiển thị `n***@example.invalid` | Nếu API vẫn trả email đầy đủ, người có quyền gọi API vẫn nhận được dữ liệu gốc |
| Mã hóa | Lưu trường liên hệ dưới dạng mã hóa | Bên có quyền giải mã vẫn có thể đọc; không làm dữ liệu tự trở thành vô danh |
| Thay định danh bằng mã | Thay email bằng mã học viên và giữ bảng ánh xạ riêng | Cần bảo vệ bảng ánh xạ, quyền nối và các dấu vết có thể liên kết khác |
| Tổng hợp | Chỉ báo cáo số người hoàn thành theo nhóm | Nhóm quá nhỏ hoặc truy vấn chồng lấn có thể làm lộ thông tin cá nhân |
| Dữ liệu giả | Tạo hồ sơ và kết quả học không dựa trên bản ghi thật | Cần bảo đảm quy trình sinh hoặc làm mẫu không vô tình sao chép dữ liệu thật |
| Ẩn danh theo đánh giá ngữ cảnh | Biến đổi để không còn khả năng nhận diện theo giả định đã đánh giá | Cần xem xét nhiều trường, nguồn phụ trợ, cách công bố và khả năng suy ra; không chỉ xóa tên |

**Thay mã định danh không đồng nghĩa với ẩn danh.** Nếu hệ thống còn giữ bảng ánh xạ hoặc vẫn có thể nối các dấu vết để nhận diện, dữ liệu cần tiếp tục được quản lý theo khả năng liên kết đó.

Băm email cũng không tự động loại bỏ khả năng nhận diện. Email có thể được đoán và đối chiếu; một giá trị băm ổn định còn có thể giúp nối nhiều tập dữ liệu. Muốn dùng kỹ thuật biến đổi để giảm mức kiểm soát, phải nêu mô hình đối thủ, thông tin phụ trợ và phép kiểm chứng thay vì chỉ nêu tên thuật toán.

Ví dụ, quy tắc “không hiển thị nhóm dưới 10 người” có thể là một biện pháp giảm rủi ro cho báo cáo cụ thể. Nó không tự chứng minh báo cáo đã ẩn danh: người xem có thể so sánh nhiều bộ lọc hoặc nhiều thời điểm để suy ra dữ liệu của một người. Cần đánh giá cả tập truy vấn được phép, không chỉ từng ô kết quả.

## 6. Chuyển phân loại thành yêu cầu bảo mật

### 6.1. Cấu trúc yêu cầu có thể kiểm chứng

Mỗi yêu cầu nên có mã, dữ liệu được bảo vệ, điều kiện áp dụng, hành vi bắt buộc, trách nhiệm thực hiện và cách chấp nhận. Khi dùng chỉ số, cần xác định điểm bắt đầu đo và kết quả quan sát được.

```text
Dữ liệu -> Mục tiêu bảo vệ -> Đe dọa -> Rủi ro
        -> Yêu cầu -> Cơ chế kiến trúc -> Kiểm thử / bằng chứng
```

Ví dụ: PD-02 chứa điểm từng bài; mục tiêu là chỉ người có nhiệm vụ phù hợp được đọc và sửa; đe dọa là người học đổi mã hồ sơ trong URL; rủi ro là lộ điểm của người khác; yêu cầu là kiểm tra quan hệ chủ thể trên mỗi yêu cầu; bằng chứng là kiểm thử truy cập chéo tài khoản, chéo tổ chức và qua các đường truy vấn khác nhau.

Những câu như “bảo mật dữ liệu người dùng”, “chỉ người có quyền được xem” hoặc “xóa khi không cần” chưa nêu đủ điều kiện kiểm thử. Các yêu cầu dưới đây cụ thể hóa cho hệ thống giả định; mọi con số đều cần được xác nhận khi áp dụng.

### 6.2. Xác thực và hành động cần xác nhận lại

**REQ-PII-AUTH-01:** Mọi API đọc hoặc thay đổi hồ sơ riêng phải xác định người gọi qua cơ chế xác thực được ứng dụng chấp nhận trước khi thực hiện truy cập. Yêu cầu thiếu thông tin xác thực, phiên hết hiệu lực hoặc thông tin xác thực không hợp lệ không được trả trường hồ sơ riêng.

**REQ-PII-AUTH-02:** Trước khi tạo tệp xuất hồ sơ hoặc đổi email liên hệ, người dùng phải có một lần xác nhận lại danh tính thành công trong 5 phút gần nhất, gắn với đúng tài khoản và phiên thực hiện. Kiểm thử phải chứng minh rằng phiên hợp lệ nhưng chưa xác nhận lại, hoặc có kết quả xác nhận quá hạn, không thực hiện được hành động.

Xác thực thành công chỉ cho biết người gọi được hệ thống nhận diện theo cơ chế đã chọn. Nó không chứng minh người đó được đọc mọi hồ sơ; bước phân quyền vẫn phải diễn ra với đối tượng cụ thể.

### 6.3. Phân quyền theo đối tượng, trường và quan hệ

**REQ-PII-AUTHZ-01:** Người học chỉ được đọc hồ sơ cá nhân, tiến độ và điểm thuộc chính tài khoản của mình. Phía máy chủ phải lấy danh tính từ ngữ cảnh xác thực đáng tin cậy và kiểm tra quyền trên đối tượng được yêu cầu; không dùng mã người dùng do trình duyệt gửi như bằng chứng sở hữu.

**REQ-PII-AUTHZ-02:** Giảng viên chỉ được đọc danh sách và kết quả học cần thiết của lớp đang được phân công trong đúng tổ chức. Phản hồi không chứa trường liên hệ riêng, nội dung hỗ trợ hoặc bí mật xác thực ngoài phạm vi chức năng đã phê duyệt.

**REQ-PII-AUTHZ-03:** Quyền hỗ trợ được gắn với mã yêu cầu hỗ trợ, tập hồ sơ được phép đọc và thời hạn tối đa 2 giờ. Kiểm tra quyền phải áp dụng khi truy cập, kể cả qua API tải tệp và tác vụ xử lý nền, không chỉ ở màn hình mở yêu cầu hỗ trợ.

Các tiêu chí chấp nhận cần bao gồm: đổi mã hồ sơ sang người khác; đổi mã tổ chức; truy vấn danh sách, tìm kiếm và xuất dữ liệu; yêu cầu thêm trường; sử dụng liên kết tệp sau khi hết quyền; gọi đồng thời với việc thu hồi quyền. Hệ thống không được tiết lộ trường bị cấm qua thông báo lỗi hoặc phản hồi từng phần.

Cache cũng phải có phạm vi dữ liệu và quyền rõ ràng. Ví dụ, cache phản hồi hồ sơ dùng chung khóa giữa hai tổ chức có thể làm lộ dữ liệu dù truy vấn cơ sở dữ liệu đã kiểm tra quyền đúng.

### 6.4. Tối thiểu hóa và kiểm soát mục đích

**REQ-PII-DATA-01:** API tạo tài khoản chỉ chấp nhận tập trường đã phê duyệt cho đăng ký. Mọi trường được lưu phải có mục đích, nhóm sử dụng và điều kiện lưu giữ trong hồ sơ dữ liệu. Trường không thuộc hợp đồng đầu vào phải bị từ chối hoặc bị loại bỏ theo hành vi đã đặc tả; kiểm thử phải xác nhận chúng không được lưu vào cơ sở dữ liệu, log hoặc sự kiện xử lý nền.

**REQ-PII-DATA-02:** Dịch vụ gửi email chỉ nhận địa chỉ người nhận, mã mẫu và tham số tối thiểu cho thông báo tương ứng. Không chuyển toàn bộ hồ sơ, điểm chi tiết hoặc nội dung hỗ trợ chỉ để thuận tiện lập trình. Dữ liệu dùng trong kiểm thử hợp đồng là dữ liệu giả.

**REQ-PII-DATA-03:** Dữ liệu vận hành không được tự động chuyển sang môi trường phát triển hoặc thử nghiệm. Nếu một luồng xử lý thật cần dữ liệu nguồn đặc biệt, phạm vi, phép biến đổi, người được truy cập và thời hạn phải được phê duyệt trước; kiểm thử thông thường sử dụng dữ liệu giả.

Giảm số trường chưa đủ nếu một trường văn bản tự do nhận mọi nội dung. Với nội dung hỗ trợ, cần thiết kế hướng dẫn nhập, giới hạn truy cập, xử lý tệp đính kèm và cách tránh đưa nội dung đó vào log hay công cụ quan sát ngoài phạm vi.

### 6.5. Bảo vệ khi truyền và lưu trữ

**REQ-PII-CRYPT-01:** Luồng truyền hồ sơ riêng qua các kết nối mạng được xác định trong sơ đồ dữ liệu phải sử dụng cơ chế mã hóa và xác thực đầu cuối kết nối theo cấu hình được phê duyệt. Kết nối tới dịch vụ có chứng chỉ không được tin cậy hoặc sai tên phải thất bại; không có cơ chế tự chuyển sang truyền không mã hóa.

**REQ-PII-CRYPT-02:** Cơ sở dữ liệu, bản sao lưu và kho tệp xuất phải có mã hóa khi lưu theo cơ chế được phê duyệt. Quyền quản trị kho và quyền sử dụng khóa phải được xác định; kiểm thử bằng danh tính không được cấp quyền phải cho thấy không thể đọc hoặc giải mã dữ liệu qua đường truy cập đó.

Phải mô tả dữ liệu ở đâu được giải mã để xử lý, ai có quyền đọc và nơi nào có thể xuất hiện bản rõ như bộ nhớ, tệp tạm hoặc log lỗi. Việc đĩa được mã hóa không ngăn ứng dụng trả dữ liệu sai người và không thay thế yêu cầu phân quyền.

Thông tin kiểm chứng mật khẩu cần cơ chế băm mật khẩu chuyên dụng theo chính sách xác thực; token khôi phục cần vòng đời và khả năng vô hiệu hóa riêng. Không đưa các dữ liệu này vào quy trình xuất hồ sơ chỉ vì chúng cùng nằm trong bảng tài khoản.

### 6.6. Bảo vệ tính toàn vẹn

**REQ-PII-INT-01:** Người học không được tự cập nhật điểm hoặc vai trò qua API chỉnh hồ sơ. Danh sách trường được sửa phải được xác định ở phía máy chủ; gửi thêm trường `score`, `role` hoặc `organizationId` không được làm thay đổi các giá trị được bảo vệ.

**REQ-PII-INT-02:** Thay đổi email phải qua quy trình xác nhận địa chỉ mới trước khi địa chỉ đó được dùng cho chức năng khôi phục truy cập. Mã xác nhận phải gắn với tài khoản, địa chỉ đích, mục đích, thời hạn và chỉ được sử dụng thành công một lần.

**REQ-PII-INT-03:** Thay đổi điểm do người có quyền thực hiện phải ghi được chủ thể, đối tượng, thời điểm, lý do và kết quả. Bằng chứng trước và sau thay đổi chỉ được lưu trong nơi có quyền truy cập phù hợp với độ nhạy cảm của điểm, thay vì đưa toàn bộ chi tiết vào log ứng dụng chung.

Kiểm thử cần thử cập nhật trường ngoài phạm vi, sử dụng mã xác nhận của tài khoản khác, dùng lại mã đã tiêu thụ và gửi hai yêu cầu xác nhận đồng thời. Thành công của một ca cập nhật hợp lệ chưa chứng minh các đường cập nhật trái phép đã bị chặn.

### 6.7. Logging phục vụ điều tra mà không tạo bản sao dư thừa

**REQ-PII-LOG-01:** Sự kiện đọc hồ sơ theo quyền hỗ trợ, tạo tệp xuất, đổi quyền, đổi email và xử lý xóa phải có mã chủ thể thực hiện, mã đối tượng nội bộ, loại thao tác, thời điểm, kết quả và mã tương quan. Không ghi nội dung hồ sơ, mật khẩu, token, email đầy đủ hoặc nội dung tệp xuất trong log sự kiện chung.

**REQ-PII-LOG-02:** Log kiểm tra được giữ 90 ngày theo mục đích điều tra đã xác định trong ví dụ, chỉ nhóm có nhiệm vụ phù hợp được tra cứu. Các truy vấn và việc xuất log cũng phải chịu kiểm soát truy cập. Mã nội bộ trong log vẫn được phân loại theo khả năng liên kết với cá nhân.

Kiểm chứng bằng dữ liệu giả có các giá trị đánh dấu dễ nhận biết: thực hiện luồng thành công, luồng lỗi và luồng bị từ chối, rồi kiểm tra log tại những nơi đã khai báo trong sơ đồ. Không ghi giá trị nhạy cảm thật vào một hệ thống tìm kiếm khác chỉ để kiểm tra việc rò rỉ.

### 6.8. Xuất dữ liệu và kiểm soát bản sao

**REQ-PII-EXPORT-01:** Tệp xuất cá nhân chỉ chứa dữ liệu thuộc tài khoản đã xác thực và danh sách trường được phép xuất. Không chứa bí mật xác thực, nội dung của người khác hoặc trường nội bộ chưa được duyệt. Tác vụ nền phải giữ ràng buộc giữa người yêu cầu, tổ chức, phạm vi dữ liệu và kết quả xuất.

**REQ-PII-EXPORT-02:** Tệp chỉ được tải qua điểm truy cập có xác thực và kiểm tra quyền ở mỗi lần tải. Thời hạn tải tối đa là 15 phút kể từ khi tác vụ chuyển sang trạng thái sẵn sàng. Sau thời hạn hoặc khi yêu cầu xuất bị hủy, điểm tải phải từ chối truy cập; tệp được xóa khỏi kho hoạt động trong tối đa 24 giờ kể từ khi hết hạn hoặc bị hủy.

Thiết kế ví dụ không dựa riêng vào một URL dài khó đoán để phân quyền. Kho chứa tệp không công khai; điểm tải kiểm tra tài khoản, quyền hiện tại, trạng thái và thời hạn. Nếu sử dụng liên kết ký sẵn có thể tải trực tiếp, cần đặc tả lại khả năng thu hồi và kiểm chứng tương ứng, thay vì giả định việc hủy tác vụ tự làm liên kết mất hiệu lực.

Kiểm thử gồm tải bằng tài khoản khác, đổi mã tác vụ, truy cập kho trực tiếp, tải trước khi sẵn sàng, tải sau hạn và tải sau khi quyền bị thu hồi. Cần kiểm tra cả dữ liệu trong tệp, không chỉ mã trạng thái HTTP.

### 6.9. Lưu giữ, xóa và phục hồi

Thời hạn lưu phải có mốc bắt đầu rõ ràng, chẳng hạn từ khi kết thúc mục đích xử lý hoặc từ khi yêu cầu xóa đã được xác nhận hợp lệ. Dữ liệu còn cần giữ cho một mục đích đã được phê duyệt phải có phạm vi và thời hạn riêng; không dùng một ngoại lệ không xác định để giữ toàn bộ hồ sơ mãi mãi.

**REQ-PII-LIFE-01:** Với nhóm dữ liệu đã được phê duyệt xóa, hệ thống phải ngăn truy cập qua các luồng nghiệp vụ thông thường ngay khi yêu cầu xóa hợp lệ được tiếp nhận, và xóa khỏi kho hoạt động trong 24 giờ. Phạm vi kho hoạt động gồm cơ sở dữ liệu, cache, chỉ mục và tệp xuất thuộc phạm vi xóa. Mỗi nơi phải có xác nhận hoàn tất hoặc trạng thái lỗi có thể theo dõi.

**REQ-PII-LIFE-02:** Bản sao lưu chứa dữ liệu trong phạm vi xóa hết hạn trong tối đa 35 ngày. Hệ thống giữ sổ điều khiển xóa được bảo vệ phù hợp, chỉ có thông tin tối thiểu để áp dụng lại việc xóa. Trước khi bản phục hồi được mở cho người dùng, phải áp dụng những yêu cầu xóa và hạn chế truy cập phát sinh sau thời điểm bản sao lưu đó.

**REQ-PII-REC-01:** Với dữ liệu học tập còn trong thời hạn lưu, mục tiêu phục hồi minh họa là RPO không quá 24 giờ và RTO không quá 4 giờ. RPO là mức mất dữ liệu tối đa chấp nhận được tính theo thời gian; RTO là thời gian mục tiêu khôi phục hoạt động sau gián đoạn. Việc đo RTO phải bao gồm kiểm tra quyền và xử lý các yêu cầu xóa liên quan trước khi mở lại dịch vụ.

Sổ điều khiển xóa cũng có thể chứa dữ liệu liên quan tới cá nhân, nên cần quyền truy cập và thời hạn tồn tại riêng. Nó phải sẵn sàng khi phục hồi, với phạm vi bảo vệ phù hợp để không bị thay thế bằng trạng thái cũ trong cùng lần khôi phục. Nếu không thể thực hiện cơ chế này, yêu cầu phục hồi cần được thiết kế lại hoặc ghi nhận khoảng thiếu để có quyết định xử lý.

Kiểm chứng vòng đời bằng cách tạo dữ liệu giả ở các kho đã khai báo, xác nhận xóa, đo thời gian, thử truy vấn qua mọi luồng còn được phép và diễn tập phục hồi từ một bản sao trước thời điểm xóa. Dữ liệu đã xóa không được xuất hiện trở lại qua dịch vụ vừa khôi phục. Một cờ `deleted=true` tự nó chưa chứng minh đã xóa khỏi mọi bản sao thuộc phạm vi.

## 7. Ma trận truy vết từ rủi ro đến kiểm chứng

| Dữ liệu và kịch bản rủi ro | Yêu cầu liên quan | Cơ chế kiến trúc | Bằng chứng chấp nhận |
|---|---|---|---|
| PD-01, PD-02: Đổi mã hồ sơ để đọc thông tin người khác | REQ-PII-AUTH-01, REQ-PII-AUTHZ-01, REQ-PII-AUTHZ-02 | Kiểm tra quan hệ với đối tượng ở máy chủ; giới hạn trường; cache có phạm vi | Kiểm thử chéo tài khoản, lớp, tổ chức; kiểm tra trường và phản hồi cache |
| PD-02: Sửa điểm hoặc vai trò bằng cách thêm trường vào payload | REQ-PII-INT-01, REQ-PII-INT-03 | Hợp đồng cập nhật cho phép; kiểm tra quyền riêng cho thao tác sửa điểm | Thử gửi trường bị cấm; kiểm tra dữ liệu trước và sau; đối chiếu dấu vết |
| PD-03, PD-04: Rò rỉ qua log và công cụ điều tra | REQ-PII-LOG-01, REQ-PII-LOG-02 | Danh sách trường log; kho log hạn chế; tách dữ liệu nghiệp vụ | Thử luồng lỗi bằng dữ liệu giả; kiểm tra log; thử tra cứu trái quyền |
| PD-05: Tệp xuất bị tải sai người hoặc sau khi hết quyền | REQ-PII-AUTH-02, REQ-PII-EXPORT-01, REQ-PII-EXPORT-02 | Tác vụ gắn danh tính; kho riêng; điểm tải kiểm tra quyền và hạn dùng | Kiểm tra nội dung tệp; thử tải sai tài khoản, sau hạn, sau hủy và qua kho trực tiếp |
| PD-01, PD-02: Dữ liệu bị đưa sang mục đích không được phê duyệt | REQ-PII-DATA-01, REQ-PII-DATA-02, REQ-PII-DATA-03 | Hợp đồng dữ liệu, bộ ánh xạ tối thiểu, tách môi trường | Kiểm thử payload và sự kiện; hồ sơ mục đích; xác nhận dữ liệu thử là dữ liệu giả |
| Dữ liệu đã được xác nhận xóa xuất hiện sau phục hồi | REQ-PII-LIFE-01, REQ-PII-LIFE-02, REQ-PII-REC-01 | Theo dõi các kho; sổ điều khiển xóa; chặn mở dịch vụ đến khi xử lý xong | Diễn tập xóa và khôi phục; đối chiếu trạng thái từng kho; đo thời gian |

Mỗi yêu cầu cần một nhóm triển khai và một người chịu trách nhiệm xác nhận. Ví dụ, nhóm API thực hiện kiểm tra quyền, nhóm dữ liệu quản lý vòng đời các kho, nhóm nền tảng quản lý kho tệp và phục hồi, còn chủ sở hữu nghiệp vụ xác định mục đích và phạm vi sử dụng. Trách nhiệm phải được thống nhất; tên nhóm trong bảng không tự tạo ra cam kết.

Nếu không có khả năng đáp ứng một yêu cầu, hồ sơ cần ghi rõ dữ liệu chịu ảnh hưởng, rủi ro còn lại, biện pháp thay thế, người có thẩm quyền quyết định và thời điểm xem lại. Không hạ mức phân loại để làm cho một thiết kế thiếu kiểm soát trở thành có vẻ phù hợp.

## 8. Duy trì yêu cầu trong vòng đời phát triển

Phân loại phải được xem lại khi thay đổi cách nhận diện, mục đích, quyền hoặc nơi tồn tại dữ liệu. Những thay đổi sau có thể làm bằng chứng cũ không còn đủ:

- Thêm trường văn bản tự do, tệp đính kèm hoặc dữ liệu suy ra.
- Ghép hai tập dữ liệu trước đây được xem xét riêng.
- Mở một vai trò mới, chức năng tìm kiếm, báo cáo hoặc xuất hàng loạt.
- Gửi dữ liệu sang nhà cung cấp, công cụ quan sát hoặc mô hình phân tích mới.
- Đổi cách cache, định dạng log, nơi sao lưu hoặc quy trình phục hồi.
- Công bố dữ liệu ra bên ngoài hoặc cho một tập người xem rộng hơn.

Trong bước thiết kế, cập nhật hồ sơ và mô hình đe dọa. Trong bước triển khai, gắn yêu cầu với điểm thực thi cụ thể. Trước phát hành, thu thập bằng chứng ở các đường truy cập và cấu hình có liên quan. Khi vận hành, theo dõi thay đổi quyền, công việc xóa thất bại và khả năng phục hồi theo phạm vi đã xác định.

Không cần chạy lại mọi kiểm thử chỉ vì có thay đổi nhỏ. Cần chọn các kiểm thử bị ảnh hưởng dựa trên truy vết dữ liệu và yêu cầu; mở rộng phạm vi khi thay đổi chạm tới ranh giới quyền, khả năng liên kết hoặc một nơi lưu mới.

## 9. Những sai sót thường gặp

| Sai sót | Vì sao không đủ | Cách điều chỉnh |
|---|---|---|
| Chỉ đánh dấu tên, email và điện thoại | Bỏ sót mã nội bộ, dấu vết và dữ liệu suy ra có thể gắn với người | Đánh giá khả năng nhận diện, liên kết và hậu quả theo ngữ cảnh |
| Dùng một nhãn cho toàn bộ bảng hoặc toàn bộ cơ sở dữ liệu | Các trường, tập con và cách sử dụng có thể cần quyền khác nhau | Đặc tả tới nhóm trường và luồng cần kiểm soát; có thể dùng mức bảo vệ chung cao hơn nếu có lý do |
| Che giao diện nhưng trả dữ liệu đầy đủ trong API | Dữ liệu vẫn đến thiết bị người dùng | Lọc trường và kiểm tra quyền ở máy chủ |
| Đã đăng nhập nên được xem dữ liệu | Thiếu kiểm tra quyền theo đối tượng và tổ chức | Kiểm tra quan hệ với dữ liệu ở mọi đường truy cập |
| Băm email hoặc xóa tên rồi coi là vô danh | Vẫn có thể đoán, nối hoặc suy ra danh tính | Đánh giá thông tin phụ trợ, phép nối và cách công bố |
| Mã hóa kho nhưng cho tài khoản ứng dụng quyền quá rộng | Dữ liệu vẫn có thể bị đọc qua ứng dụng hoặc danh tính có quyền | Giới hạn quyền, trường, mục đích và khả năng xuất |
| Ghi toàn bộ payload để dễ gỡ lỗi | Log trở thành một kho hồ sơ có phạm vi truy cập rộng | Chỉ ghi trường cần điều tra, dùng mã tương quan và quản lý kho log |
| Xóa bản ghi chính nhưng bỏ qua cache, tệp xuất và backup | Dữ liệu vẫn tồn tại hoặc quay lại sau khôi phục | Lập bản đồ các bản sao, đặt thời hạn riêng và thử phục hồi sau xóa |
| Chỉ kiểm thử một hồ sơ hợp lệ | Không phát hiện truy cập chéo người, tổ chức hoặc đường xuất | Kiểm thử cả từ chối quyền, biên thời gian, xử lý nền và các bản sao |

## 10. Bài tập vận dụng

Một nhóm muốn xây dựng báo cáo tiến độ học cho quản lý tổ chức. Dữ liệu gồm mã học viên, email, nhóm làm việc, khóa học, điểm và thời điểm truy cập gần nhất. Màn hình ban đầu chỉ hiển thị tỷ lệ hoàn thành theo nhóm, nhưng dự kiến có thêm tải bảng tính và lọc theo thời gian. Một số nhóm chỉ có một hoặc hai người.

Hãy thực hiện:

1. Xác định dữ liệu cá nhân trực tiếp, gián tiếp, dữ liệu hoạt động và dữ liệu suy ra. Nêu những nguồn có thể giúp liên kết với một người cụ thể.
2. Lập hồ sơ cho dữ liệu nguồn, kết quả tổng hợp, tệp xuất và log. Ghi mục đích, người được xem, thời hạn và nơi tồn tại của từng nhóm.
3. Đánh giá hậu quả về bí mật, toàn vẹn và sẵn sàng. Giải thích vì sao báo cáo tổng hợp không tự động loại bỏ rủi ro đối với cá nhân.
4. Viết yêu cầu cho quản lý chỉ xem đúng tổ chức, giới hạn các trường được xuất và kiểm tra quyền ở cả tác vụ nền lẫn lần tải tệp.
5. Đề xuất biện pháp hạn chế suy ra thông tin từ nhóm nhỏ và truy vấn chồng lấn. Nêu giới hạn của biện pháp, không chỉ chọn một ngưỡng số lượng.
6. Đặt tiêu chí lưu giữ, xóa và phục hồi, bao gồm xử lý tệp đã xuất trong kho hệ thống và dữ liệu còn trong bản sao lưu.
7. Tạo ma trận nối mỗi rủi ro với yêu cầu và một phép kiểm chứng quan sát được.

Một phương án có cơ sở phải chỉ ra đường dữ liệu từ nguồn tới từng kết quả, giải thích ai có thể nhận diện người học và chứng minh quyền được kiểm tra tại các điểm thực thi. Việc một màn hình hiển thị ít thông tin hơn không đủ để kết luận rằng API, tệp xuất, log và bản phục hồi cũng đã có mức bảo vệ tương ứng.
