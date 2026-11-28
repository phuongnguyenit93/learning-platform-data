# Test case từ security requirement

## 1. Từ yêu cầu bảo mật đến phép kiểm chứng

Một **security requirement** mô tả điều hệ thống phải đáp ứng để bảo vệ tài sản, xử lý rủi ro hoặc thực hiện một nghĩa vụ trong phạm vi xác định. Một **test case** mô tả cách thiết lập, kích hoạt và quan sát một tình huống để đánh giá một phần của yêu cầu đó.

Liên kết cần giữ là:

> Yêu cầu có phiên bản → điều kiện cần kiểm chứng → tình huống và dữ liệu thử → kết quả kỳ vọng → kết quả thực tế và bằng chứng.

Ví dụ, yêu cầu “chỉ người có quyền được xuất dữ liệu của đúng khách hàng” không thể kiểm chứng đầy đủ chỉ bằng việc cho một người có quyền bấm xuất thành công. Cần thử người thiếu quyền, người thuộc khách hàng khác, API trực tiếp, tác vụ nền và đường tải kết quả nếu những đường này thuộc phạm vi yêu cầu.

### Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
| --- | --- |
| Yêu cầu | Hành vi hoặc ràng buộc hệ thống phải đáp ứng |
| Điều kiện kiểm thử | Một khía cạnh của yêu cầu cần đánh giá |
| Kịch bản | Tình huống nghiệp vụ hoặc bảo mật cần diễn ra |
| Test case | Điều kiện đầu, dữ liệu, bước thực hiện và kết quả kỳ vọng cụ thể |
| Test script | Cách thực hiện test case bằng tay hoặc bằng chương trình |
| Test oracle | Căn cứ và quy tắc để kết luận kết quả quan sát có đúng không |
| Bằng chứng | Hiện vật hỗ trợ kết luận, gắn với phạm vi và phiên bản đã kiểm tra |

Một yêu cầu có thể cần nhiều test case. Một test case cũng có thể kiểm chứng nhiều yêu cầu, nhưng phải chỉ rõ từng kết luận và bằng chứng tương ứng.

Bài học dùng ví dụ giả định về xuất hồ sơ thanh toán trong một dịch vụ nhiều tenant. Mọi mã, ngưỡng số và quyết định API trong ví dụ đều được đặt riêng để minh họa phương pháp, không phải quy tắc mặc định cho mọi hệ thống.

## 2. Đọc yêu cầu trước khi viết test case

Trước hết, kiểm tra yêu cầu đã đủ rõ để tạo ra kết quả kỳ vọng hay chưa.

| Thành phần cần đọc | Câu hỏi |
| --- | --- |
| Mã và phiên bản | Đang kiểm chứng bản yêu cầu nào? |
| Nguồn và mục tiêu | Rủi ro hoặc mục tiêu bảo vệ nào dẫn đến yêu cầu? |
| Chủ thể | Người dùng, dịch vụ, worker hoặc quản trị viên nào? |
| Hành động và đối tượng | Được hoặc không được làm gì với dữ liệu nào? |
| Phạm vi | Tenant, môi trường, API và đường xử lý nào? |
| Điều kiện | Danh tính, quyền, trạng thái dữ liệu và thời điểm nào? |
| Ngưỡng | Giá trị, đơn vị, mốc đo và điều kiện áp dụng? |
| Hành vi lỗi | Hệ thống phải làm gì khi phụ thuộc không đáp ứng? |
| Bằng chứng | Cần quan sát phản hồi, dữ liệu, trạng thái hay sự kiện nào? |

Nếu yêu cầu chỉ ghi “thu hồi quyền nhanh chóng”, người kiểm thử chưa có căn cứ chọn 5 giây, 5 phút hay 1 giờ làm ngưỡng đạt.

Khi thiếu thông tin:

1. Ghi câu hỏi gắn với mã yêu cầu.
2. Chỉ rõ phần nào chưa tạo được kết quả kỳ vọng.
3. Chuyển tới người có trách nhiệm xác nhận.
4. Tiếp tục thiết kế những phần đã rõ.
5. Cập nhật test case khi yêu cầu được xác nhận.

Không tự chốt chính sách trong test script rồi coi kết quả chạy script là bằng chứng yêu cầu đã được đáp ứng.

### Bộ yêu cầu giả định dùng xuyên suốt

**SEC-EXP-AUTHZ-01, phiên bản 2 — phân quyền xuất hồ sơ**

- Chỉ người dùng đã xác thực, đang hoạt động và có quyền xuất trên đúng tenant mới được yêu cầu xuất và nhận dữ liệu.
- API xuất, điểm worker quyết định công bố kết quả và đường tải phải thực thi phân quyền ở phía máy chủ.
- Theo hợp đồng API của ví dụ, thiếu xác thực trả 401; người đã xác thực nhưng không đủ quyền hoặc sai tenant trả 403.
- Yêu cầu tạo tác vụ bị từ chối không được tạo tác vụ xuất.
- Trường hợp bị từ chối không được cung cấp dữ liệu hồ sơ hoặc liên kết có thể dùng để nhận dữ liệu.

**SEC-EXP-REV-01, phiên bản 1 — thu hồi quyền**

- Trong tối đa 300 giây từ t0, các quyết định cấp mới dữ liệu phải ngừng dựa trên quyền xuất đã bị thu hồi.
- t0 là thời điểm hệ thống ghi nhận lệnh thu hồi hợp lệ và trả mã xác nhận.
- Phạm vi gồm yêu cầu xuất mới, quyết định công bố kết quả của worker và lần tải mới qua liên kết đã tạo.
- Phiên, cache và thử lại không được kéo dài quyền cũ vượt giới hạn.
- Khi không thể xác minh một quyết định quyền đáp ứng giới hạn hiệu lực, hệ thống không được cấp mới dữ liệu theo quyền đó.

Ví dụ này xét các quyết định cấp mới dữ liệu. Nếu hệ thống có lượt tải đang truyền, hành vi ngừng truyền phải được xác định bằng yêu cầu và test case tương ứng; kết quả cho lần tải mới không tự chứng minh việc dừng luồng đang chạy.

**SEC-EXP-AUD-01, phiên bản 1 — bằng chứng truy cập**

- Yêu cầu xuất, quyết định từ chối và kết quả công bố tệp phải có sự kiện liên kết được với luồng xử lý.
- Sự kiện có thời điểm, định danh chủ thể nếu đã xác định, tenant liên quan, hành động, đối tượng, kết quả và mã liên kết.
- Trong điều kiện vận hành bình thường đã xác định cho phép thử, sự kiện phải đến kho tập trung trong tối đa 60 giây từ lúc phát sinh.
- Nội dung hồ sơ, token truy cập và bí mật không được ghi vào nhật ký.
- Hành vi khi kho nhật ký gián đoạn cần được đặc tả riêng; không suy ra từ ngưỡng của điều kiện bình thường.

Các trạng thái và mã phản hồi trên là một phần của đặc tả ví dụ. Một hệ thống chọn chính sách phản hồi khác phải tạo oracle từ chính hợp đồng của nó.

## 3. Tách yêu cầu thành điều kiện kiểm thử

Mỗi mệnh đề trong yêu cầu có thể tạo ra một hoặc nhiều điều kiện cần kiểm tra.

Với SEC-EXP-AUTHZ-01:

| Mệnh đề | Điều kiện kiểm thử |
| --- | --- |
| Đã xác thực | Không có thông tin xác thực; thông tin hợp lệ; thông tin hết hiệu lực |
| Đang hoạt động | Tài khoản hoạt động; bị vô hiệu hóa |
| Có quyền xuất | Có quyền; thiếu quyền; chỉ có quyền trên thao tác khác |
| Đúng tenant | Chủ thể và dữ liệu cùng tenant; khác tenant |
| Thực thi phía máy chủ | Gọi API trực tiếp; sửa định danh đối tượng; không đi qua giao diện |
| Worker phải kiểm tra | Trạng thái quyền thay đổi trước thời điểm quyết định công bố |
| Đường tải phải kiểm tra | Liên kết đúng chủ thể; liên kết được người khác dùng; quyền đã thay đổi |
| Từ chối không tạo tác vụ | Phản hồi từ chối đồng thời không có tác vụ mới của yêu cầu đó |
| Không cung cấp dữ liệu | Không có payload nhạy cảm hoặc đường lấy dữ liệu hữu dụng |

Với SEC-EXP-REV-01, cần thêm thời gian, phiên cũ, cache, tác vụ đang chờ và liên kết cũ. Với SEC-EXP-AUD-01, cần kiểm tra sự kiện, nội dung, liên kết và độ trễ.

Một cách làm có hệ thống:

1. Gạch ra chủ thể, hành động, đối tượng, điều kiện và ngưỡng.
2. Tạo một trường hợp hợp lệ để chứng minh chức năng vẫn hoạt động.
3. Đảo từng điều kiện quan trọng để tạo trường hợp bị cấm.
4. Thử ranh giới và thay đổi trạng thái.
5. Thử các điểm thực thi trong phạm vi.
6. Thử lỗi phụ thuộc theo hành vi đã được yêu cầu.
7. Xác định oracle và điểm thu bằng chứng.
8. Liên kết test case về đúng mã và phiên bản yêu cầu.

Không cần nhân toàn bộ tổ hợp một cách máy móc. Ưu tiên tổ hợp theo rủi ro và bảo đảm mỗi ranh giới quan trọng có tình huống đại diện. Các tổ hợp đã chọn phải được ghi rõ để người đánh giá biết phần nào còn chưa được thử.

## 4. Chọn các nhóm test case cần thiết

### 4.1. Trường hợp được phép

Người dùng có quyền phù hợp thao tác với dữ liệu đúng tenant và nhận kết quả đúng phạm vi.

Trường hợp này giúp phát hiện hệ thống “an toàn” chỉ vì mọi yêu cầu đều bị từ chối hoặc tính năng đang hỏng. Nó cũng xác nhận dữ liệu và tài khoản thử thực sự dùng được.

### 4.2. Trường hợp bị cấm

Thử chủ thể thiếu quyền, sai tenant, bị vô hiệu hóa hoặc không có xác thực. Giữ các yếu tố khác hợp lệ để biết điều kiện nào dẫn đến kết quả.

Ví dụ, muốn kiểm tra cô lập tenant thì nên dùng một tài khoản có quyền xuất hợp lệ trong tenant A và một tài nguyên có thật của B. Nếu tài khoản cũng không có quyền xuất, kết quả từ chối chưa cô lập được nguyên nhân sai tenant.

### 4.3. Đường đi bỏ qua

Một nút bị ẩn trên giao diện không chứng minh API có phân quyền. Cần xét:

- Gọi API trực tiếp.
- Dùng định danh đối tượng hoặc tenant khác.
- Tải tệp đã tạo mà không qua màn hình xuất.
- Tác vụ được thử lại ở worker.
- Công cụ vận hành hoặc kênh tích hợp thuộc phạm vi.

Các phép thử phải nằm trong môi trường và phạm vi được phép. Dữ liệu khác tenant có thể được tạo hoàn toàn bằng fixture giả lập.

### 4.4. Chuyển trạng thái

Bảo mật có thể đúng tại lúc bắt đầu nhưng sai sau khi trạng thái thay đổi:

- Người dùng chuyển từ có quyền sang mất quyền.
- Tài khoản đang hoạt động bị vô hiệu hóa.
- Tác vụ đang chờ chuyển sang đang chạy.
- Tệp đã tạo chuyển sang được công bố.
- Hệ thống phục hồi từ bản sao có trạng thái quyền cũ.

Test case cần điều khiển được thời điểm thay đổi và thời điểm quan sát, thay vì chỉ kiểm tra trạng thái ban đầu.

### 4.5. Ranh giới

Với giới hạn 300 giây, có thể quan sát tại 299, 300 và 301 giây nếu độ phân giải và sai số của phép thử phù hợp.

| Thời điểm từ t0 | Cách hiểu với yêu cầu “trong tối đa 300 giây” |
| --- | --- |
| 299 giây | Có thể đã từ chối; việc từ chối sớm không phải lỗi |
| 300 giây | Phải ngừng cấp mới dữ liệu theo quyền đã bị thu hồi |
| 301 giây | Không được tiếp tục cấp mới dữ liệu theo quyền đó |

**Giới hạn tối đa không phải cam kết phải giữ quyền đến sát hạn.** Một test case yêu cầu người dùng vẫn được phép ở giây 299 sẽ thêm một quy tắc mà yêu cầu chưa nêu.

Khi đồng hồ và cơ chế quan sát không đủ chính xác để kết luận tại ranh giới, cần cải thiện phép đo hoặc ghi giới hạn bằng chứng. Không tự cộng khoảng dung sai vào ngưỡng nghiệp vụ để biến một trường hợp vượt hạn thành đạt.

### 4.6. Lỗi phụ thuộc

Thử dịch vụ quyền không phản hồi, cache cũ hoặc kho dữ liệu tạm gián đoạn khi yêu cầu đã xác định hành vi tương ứng.

Không áp dụng máy móc một câu “mọi lỗi đều phải fail closed” cho toàn hệ thống. Cần xác định thao tác nào phải ngừng, thao tác nào được tiếp tục và theo điều kiện nào. Oracle phải đến từ đặc tả hành vi lỗi đã xác nhận.

## 5. Cấu trúc một test case có thể thực hiện lại

| Trường | Nội dung cần có |
| --- | --- |
| Mã test case | Định danh ổn định |
| Yêu cầu liên kết | Mã và phiên bản |
| Mục tiêu | Điều kiện bảo mật cụ thể cần đánh giá |
| Mức kiểm thử | Thành phần, tích hợp hoặc toàn luồng tùy mục tiêu |
| Điều kiện đầu | Tài khoản, quyền, dữ liệu, cấu hình, phụ thuộc và trạng thái |
| Dữ liệu thử | Tenant, đối tượng, dấu nhận diện và phạm vi riêng cho lần chạy |
| Các bước | Thao tác đủ cụ thể để lặp lại |
| Kết quả kỳ vọng | Phản hồi, trạng thái, dữ liệu và sự kiện cần quan sát |
| Oracle | Quy tắc đối chiếu và nguồn của kết luận |
| Bằng chứng | Hiện vật cần thu, kèm thời gian và định danh liên kết |
| Dọn dẹp | Xóa fixture, quyền tạm và tệp sinh ra |
| Giới hạn | Những phần không được phép thử hoặc chưa quan sát được |

### Đặt điều kiện đầu đủ mạnh

“Có người dùng A và B” chưa đủ. Cần biết:

- Mỗi người thuộc tenant nào.
- Quyền nào đang có hiệu lực.
- Tài khoản có đang hoạt động không.
- Dữ liệu mục tiêu có thực sự tồn tại không.
- Hệ thống đang kiểm tra đúng bản cấu hình nào.
- Các phụ thuộc cần thiết có đang sẵn sàng không.

Nên dùng namespace riêng theo lần chạy để tránh tác vụ của một bài thử bị lẫn với tác vụ của bài khác.

Dữ liệu giả có dấu nhận diện riêng giúp phát hiện rò rỉ. Ví dụ, nội dung hồ sơ của tenant B chứa một chuỗi thử chỉ có trong fixture B; nếu chuỗi xuất hiện ở phản hồi hoặc tệp mà người dùng A nhận được, có bằng chứng cụ thể về sai phạm vi.

## 6. Ví dụ test case hợp lệ

**Mã:** TC-EXP-ALLOW-001.  
**Yêu cầu:** SEC-EXP-AUTHZ-01@2.  
**Mục tiêu:** người có quyền nhận được dữ liệu đúng tenant.

**Điều kiện đầu:**

- Người dùng Alice đang hoạt động, thuộc tenant A.
- Alice có quyền xuất hồ sơ của A.
- Tenant A và B có dữ liệu giả lập với dấu nhận diện khác nhau.
- API, worker và đường tải hoạt động trong môi trường thử.
- Fixture của lần chạy có định danh riêng.

**Các bước:**

1. Xác thực Alice bằng cơ chế hợp lệ của môi trường thử.
2. Gửi yêu cầu xuất hồ sơ thuộc A.
3. Chờ tác vụ đạt trạng thái hoàn tất theo cơ chế quan sát của bộ thử.
4. Tải kết quả bằng danh tính Alice.
5. Đối chiếu nội dung và phạm vi tệp.

**Kết quả kỳ vọng:**

- Yêu cầu được chấp nhận theo hợp đồng API.
- Tác vụ hoàn thành và Alice tải được kết quả.
- Kết quả chứa dữ liệu A được yêu cầu.
- Không chứa dấu nhận diện dữ liệu B.
- Không cần dùng danh tính vận hành để vượt qua đường tải thông thường.

Nếu quy trình có timeout của bộ thử, phải phân biệt timeout đó với một yêu cầu hiệu năng nghiệp vụ. Việc chờ quá thời gian của harness có thể khiến bài thử chưa hoàn tất; nó không tự chứng minh hệ thống vi phạm một SLA chưa được đặc tả.

Trường hợp này là đối chứng quan trọng cho các test từ chối. Tuy vậy, một lần xuất thành công chỉ chứng minh phạm vi dữ liệu và trạng thái đã thực hiện, không bao phủ mọi loại hồ sơ hoặc mọi vai trò.

## 7. Ví dụ test case truy cập chéo tenant

**Mã:** TC-EXP-TENANT-002.  
**Yêu cầu:** SEC-EXP-AUTHZ-01@2 và SEC-EXP-AUD-01@1.  
**Mục tiêu:** Alice có quyền xuất của A nhưng không thể xuất dữ liệu B.

**Điều kiện đầu:**

- Alice đã xác thực, đang hoạt động, có quyền xuất của A.
- Tài nguyên mục tiêu của B tồn tại và có dấu nhận diện riêng.
- Alice không có quyền trên B.
- Có cách quan sát tác vụ và nhật ký trong phạm vi lần chạy.
- Khả năng xuất hợp lệ của Alice trong A đã được xác nhận bằng fixture phù hợp.

**Các bước:**

1. Ghi định danh lần chạy và trạng thái các tác vụ liên quan.
2. Dùng danh tính Alice gọi API xuất trực tiếp với dữ liệu mục tiêu của B.
3. Thu mã phản hồi, nội dung lỗi và mã liên kết.
4. Kiểm tra có tác vụ mới gắn với yêu cầu bị từ chối hay không.
5. Kiểm tra phản hồi có cung cấp dữ liệu B hoặc liên kết nhận dữ liệu không.
6. Chờ có giới hạn để tìm sự kiện tương ứng trong kho nhật ký.
7. Kiểm tra trường sự kiện và dữ liệu không được ghi.

**Kết quả kỳ vọng:**

- API trả 403 theo hợp đồng của ví dụ.
- Phản hồi không có dữ liệu hồ sơ B hoặc liên kết hữu dụng để nhận dữ liệu.
- Không có tác vụ xuất mới của yêu cầu bị từ chối.
- Có sự kiện từ chối liên kết đúng chủ thể, hành động và yêu cầu.
- Trong điều kiện bình thường đã xác định, sự kiện đến kho tập trung trong tối đa 60 giây.
- Nhật ký không chứa nội dung hồ sơ hoặc token thử.

**Bằng chứng:**

- Yêu cầu và phản hồi đã che thông tin xác thực.
- Mã bản dựng, cấu hình, môi trường và thời điểm.
- Kết quả truy vấn trạng thái tác vụ bằng mã liên kết hoặc namespace.
- Sự kiện audit tương ứng và thời gian quan sát.

Chỉ thấy 403 là chưa đủ. Một lỗi triển khai có thể trả 403 nhưng vẫn tạo tác vụ, công bố tệp hoặc ghi dữ liệu nhạy cảm vào log.

Ngược lại, nếu không quan sát được hàng đợi hoặc kho nhật ký, cần ghi phần chưa thể kết luận. Không đổi “không nhìn thấy” thành “chắc chắn không xảy ra” khi công cụ quan sát chưa đáng tin cậy.

## 8. Ví dụ test case thu hồi quyền theo thời gian

**Mã:** TC-EXP-REVOKE-003.  
**Yêu cầu:** SEC-EXP-REV-01@1.  
**Mục tiêu:** quyền cũ không tiếp tục tạo ra quyết định cấp mới dữ liệu vượt giới hạn 300 giây.

**Điều kiện đầu:**

- Alice có quyền xuất của A và một phiên còn hiệu lực.
- Có một tệp hợp lệ và liên kết tải đã tạo trước khi thu hồi.
- Có một tác vụ chưa đi qua điểm quyết định công bố kết quả.
- Những điểm thực thi và nhóm cache thuộc phạm vi đã được liệt kê.
- Bộ thử quan sát được t0 và thời điểm quyết định ở các điểm thực thi.
- Cách điều khiển thời gian hoặc cách đo đã được thống nhất.

**Các bước:**

1. Xác nhận Alice có thể thực hiện thao tác hợp lệ trước khi thu hồi.
2. Gửi lệnh thu hồi quyền từ một danh tính có thẩm quyền.
3. Thu mã xác nhận và t0 theo định nghĩa của yêu cầu.
4. Giữ nguyên phiên cũ để không vô tình chỉ kiểm tra một lần đăng nhập mới.
5. Quan sát quyết định tại các mốc quanh giới hạn, theo khả năng đo đã xác định.
6. Tại và sau hạn, thử yêu cầu xuất mới và lần tải mới qua liên kết cũ.
7. Cho tác vụ đang chờ đi qua điểm quyết định công bố sau hạn.
8. Lặp lại trên các nhóm điểm thực thi có trạng thái quyền độc lập.
9. Thu kết quả và mốc quyết định, không chỉ mốc gửi request.

**Kết quả kỳ vọng:**

- Hệ thống có thể ngừng cho phép sớm hơn 300 giây.
- Tại và sau hạn 300 giây, không có quyết định cấp mới dữ liệu dựa trên quyền đã thu hồi trong các tình huống được thử.
- Phiên cũ hoặc liên kết cũ không kéo dài quyền.
- Worker không công bố dữ liệu theo quyền đã mất sau hạn.
- Mỗi kết luận gắn được với t0, điểm thực thi và thời điểm quyết định.

Một request gửi ở giây 299 nhưng được đánh giá quyền ở giây 301 phải được đối chiếu với thời điểm được yêu cầu quy định. Trong ví dụ, đối tượng kiểm soát là quyết định cấp mới dữ liệu, vì vậy không dùng thời điểm gửi request để hợp thức hóa một quyết định sau hạn.

### Kiểm thử tích hợp và đồng hồ ảo

Có thể dùng đồng hồ điều khiển được để kiểm tra logic hết hạn và ranh giới mà không chờ thật 300 giây cho mọi lần chạy. Cách này chỉ có ý nghĩa nếu các thành phần liên quan trong phép thử dùng nguồn thời gian phù hợp với thiết kế thử.

Đồng hồ ảo của một thành phần không tự làm đồng hồ của dịch vụ khác, bộ cache hoặc token bên ngoài tiến theo. Cần có phép kiểm thử tích hợp phù hợp để đánh giá độ trễ cập nhật và tương tác thật.

Cơ chế điều khiển thời gian hoặc tạm dừng worker phải thuộc hạ tầng thử nghiệm, được cô lập và kiểm soát. Không đưa một đường bỏ qua bảo mật vào môi trường sử dụng thực chỉ để bài thử dễ chạy.

### Giới hạn kết luận

Một vài mẫu gọi API không thể chứng minh rằng mọi nút ở mọi thời điểm đều đáp ứng. Báo cáo cần nói rõ các điểm thực thi, cấu hình và trạng thái đã thử, kết hợp với kiểm tra thiết kế và cấu hình khi cần đánh giá phạm vi rộng hơn.

## 9. Kiểm tra race condition và tác vụ bất đồng bộ

Các kiểm soát có thể sai khi quyền hoặc dữ liệu thay đổi giữa hai bước. Đây là nhóm tình huống cần mô hình hóa thứ tự sự kiện, thay vì dùng nhiều lệnh gọi đồng thời rồi hy vọng lỗi xuất hiện.

Một lịch thử cho worker:

```text
1. Tạo tác vụ khi người dùng còn quyền.
2. Tạm giữ tác vụ trước điểm quyết định công bố kết quả.
3. Thu hồi quyền và ghi t0.
4. Đưa thời gian hoặc chờ tới sau hạn thu hồi bằng cơ chế đã xác định.
5. Cho worker tiếp tục.
6. Quan sát quyết định và khả năng lấy dữ liệu.
```

Oracle là kết quả bảo mật đã đặc tả: không công bố dữ liệu theo quyền hết hiệu lực sau hạn. Không bắt buộc worker phải dùng một tên trạng thái nội bộ cụ thể nếu yêu cầu chưa quy định tên đó.

Có thể mở rộng các lịch thử:

| Thay đổi xen giữa | Điểm cần quan sát |
| --- | --- |
| Thu hồi quyền trước khi worker công bố | Có kiểm tra hiệu lực quyền tại điểm cần thiết không |
| Thử lại tác vụ sau lỗi | Lần thử lại có dùng quyết định quyền cũ không |
| Liên kết tạo khi còn quyền, sử dụng sau thu hồi | Đường tải có kiểm soát quyền hiện hành không |
| Chuyển hoặc sửa phạm vi dữ liệu trước khi công bố | Kết quả có còn đúng đối tượng và tenant được phép không |
| Khởi động lại thành phần có cache | Trạng thái cũ có tạo cửa sổ cung cấp dữ liệu trái yêu cầu không |

Nếu chưa rõ yêu cầu đòi quyền hợp lệ ở lúc nhận tác vụ, lúc chạy hay lúc công bố, cần làm rõ trước khi kết luận một lịch xen kẽ là lỗi.

Để kiểm tra một race condition đáng tin cậy, cần quan sát hoặc điều khiển được thứ tự các mốc. Một bài thử chạy không ổn định vì không biết bước nào xảy ra trước chưa phải bằng chứng vững chắc về hành vi hệ thống.

## 10. Xây dựng oracle đủ mạnh

Test oracle không chỉ là một mã HTTP. Tùy yêu cầu, cần kết hợp nhiều lớp quan sát.

| Lớp | Ví dụ điều cần kiểm tra |
| --- | --- |
| Phản hồi | Mã, trường dữ liệu, thông báo và liên kết trả về |
| Dữ liệu nghiệp vụ | Có đọc, sửa, xuất hoặc xóa ngoài phạm vi không |
| Trạng thái xử lý | Có tạo tác vụ, công bố tệp hoặc thử lại trái quy tắc không |
| Quyết định bảo mật | Chủ thể, quyền, tenant và thời điểm đánh giá |
| Audit | Có sự kiện đúng luồng, đúng kết quả và không chứa dữ liệu bị cấm không |
| Bản sao hoặc kênh phụ | Có đường nhận cùng dữ liệu ngoài điểm kiểm soát đã thử không |

Không cần mọi test case quan sát tất cả các lớp. Cần chọn lớp tương ứng với tuyên bố đang kiểm chứng.

### Quan sát “không xảy ra” có điều kiện

Muốn khẳng định yêu cầu bị từ chối không tạo tác vụ, phải biết:

- Đang truy vấn đúng phạm vi tác vụ của lần chạy.
- Hệ thống quan sát có nhận đủ dữ liệu không.
- Tác vụ có thể xuất hiện trễ không.
- Khoảng quan sát nào đủ theo hợp đồng hoặc thiết kế đã xác nhận.
- Có kênh xử lý khác cần xét không.

Nếu chưa có cơ sở xác định khoảng quan sát, ghi giới hạn và làm rõ. Không chọn một lần truy vấn tức thời rồi coi danh sách trống là bằng chứng tuyệt đối.

### Đo thời gian với sai số rõ ràng

Nếu độ trễ đo được là d và sai số tổng của khoảng đo bị chặn bởi ε, giá trị thật nằm trong khoảng từ d − ε đến d + ε.

Với ngưỡng tối đa 60 giây của sự kiện audit:

- Khi d + ε không vượt 60 giây, phép đo hỗ trợ kết luận đạt về độ trễ.
- Khi d − ε lớn hơn 60 giây, phép đo hỗ trợ kết luận vượt hạn.
- Khi khoảng sai số cắt qua 60 giây, phép đo chưa đủ để kết luận tại ranh giới.

Cần biết ε được xác định bằng cách nào. Công thức không có giá trị nếu nhóm chỉ tự đặt một mức sai số tiện lợi.

Với thời gian trong cùng một tiến trình, có thể dùng nguồn đo khoảng thời gian phù hợp. Với nhiều hệ thống, cần kiểm soát hoặc đánh giá sai lệch đồng hồ và làm rõ ý nghĩa từng timestamp.

### Kiểm tra dữ liệu nhạy cảm

Dấu nhận diện trong fixture giúp tìm dữ liệu bị lộ, nhưng một phép tìm chuỗi không chứng minh mọi dạng rò rỉ đều vắng mặt. Có thể cần giải mã định dạng tệp, kiểm tra trường có cấu trúc, lỗi hiển thị và các đường log liên quan.

Dùng token hoặc bí mật thử có thể nhận diện được, không dùng thông tin xác thực thực của người khác. Bằng chứng chia sẻ phải được che hoặc giới hạn quyền phù hợp.

## 11. Mở rộng phương pháp sang các miền bảo mật khác

Các ví dụ dưới đây là cách thiết kế test khi đã có yêu cầu tương ứng. Chúng không tự bổ sung nghĩa vụ mới vào bộ ba yêu cầu xuất dữ liệu ở trên.

| Miền | Điều kiện kiểm thử tiêu biểu | Oracle cần có |
| --- | --- | --- |
| Xác thực | Thiếu thông tin, thông tin hết hiệu lực, tài khoản vô hiệu hóa, mức xác minh chưa đủ cho thao tác | Hợp đồng xác thực, hành vi từ chối và phạm vi dữ liệu không được cung cấp |
| Phân quyền | Sai hành động, sai đối tượng, sai tenant, quyền bị thu hồi | Quy tắc quyền ở các điểm thực thi và tác động nghiệp vụ |
| Mã hóa và khóa | Cấu hình truyền ngoài baseline, nơi lưu không đúng cấu hình, danh tính thiếu quyền dùng khóa, dịch vụ khóa lỗi | Baseline có phiên bản, cấu hình thực tế và hành vi truy cập |
| Logging | Thiếu sự kiện, sai chủ thể, mất liên kết, trường nhạy cảm, gián đoạn kho log | Lược đồ, lưu giữ, quyền truy cập, giới hạn độ trễ và hành vi lỗi đã xác nhận |
| Xóa dữ liệu | Dữ liệu còn ở tệp xuất, cache, bản sao hoặc sau phục hồi | Danh mục nơi lưu, thời hạn, ngoại lệ và cách chứng minh xử lý từng bản sao |
| Phục hồi | Mất thành phần, phục hồi dữ liệu, trạng thái quyền hoặc khóa không đầy đủ | Kịch bản, RTO, RPO, tính nhất quán và điều kiện dịch vụ hoạt động an toàn |

### Không dùng sai loại bằng chứng

Ví dụ, yêu cầu giữ nhật ký trong 180 ngày không thể được chứng minh đầy đủ bằng cách tăng đồng hồ của một bài thử rồi kiểm tra bộ xóa có hoạt động.

Phép thử tăng tốc hỗ trợ xác minh logic lưu giữ. Đánh giá đầy đủ còn cần cấu hình thực tế, quyền xóa, các đường lưu, cơ chế hết hạn và bằng chứng vận hành phù hợp với phạm vi cần kết luận.

Tương tự, đọc thất bại một tệp đã mã hóa không đủ chứng minh mọi nơi lưu đều được mã hóa. Khởi động lại được máy chủ cũng chưa chứng minh dịch vụ đáp ứng RTO nếu xác thực, phân quyền hoặc khóa chưa hoạt động.

## 12. Tổ chức tự động hóa mà vẫn giữ ý nghĩa test case

Nên tự động hóa những phép thử có oracle rõ, dữ liệu có thể tạo lại và khả năng quan sát đủ tin cậy. Chọn mức thực hiện theo hành vi cần chứng minh:

- Kiểm thử thành phần hỗ trợ đánh giá logic quyết định và ranh giới.
- Kiểm thử tích hợp kiểm tra truyền ngữ cảnh, phụ thuộc, cache và sự kiện.
- Kiểm thử toàn luồng xác minh các đường tiếp cận dữ liệu quan trọng.
- Kiểm tra cấu hình, rà soát và diễn tập bổ sung những phần khó chứng minh chỉ bằng test script.

Mock dịch vụ quyền hữu ích để điều khiển tình huống, nhưng không chứng minh tích hợp thực đang truyền đúng tenant hoặc nhận đúng cập nhật quyền.

Mã giả sau minh họa cấu trúc test chéo tenant; đây không phải API của một thư viện cụ thể:

```text
fixture = create_isolated_fixture()
try:
    alice = fixture.active_user(tenant="A", permission="export")
    target_b = fixture.payment_record(tenant="B", unique_marker=true)

    verify_allowed_export(alice, fixture.record_of("A"))

    response = call_export_api(
        identity=alice,
        target=target_b,
        run_id=fixture.run_id
    )

    assert response.status == 403
    assert no_business_data_or_usable_download_link(response)
    assert no_export_job_for(response.correlation_id)

    event = await_audit_event(
        correlation_id=response.correlation_id,
        deadline=expected_event_deadline(response)
    )

    assert event.result == "DENIED"
    assert event.actor == alice.id
    assert event.is_linked_to(response.correlation_id)
    assert no_sensitive_fixture_content(event)
finally:
    cleanup_fixture(fixture)
```

Các hàm quan sát trong mã giả cần được định nghĩa theo hệ thống thực. Ví dụ, kiểm tra không có tác vụ phải xét tính bất đồng bộ như đã nêu, không chỉ gọi một truy vấn tức thời.

### Chờ có điều kiện thay vì ngủ cố định

Với hệ thống bất đồng bộ, nên đợi một điều kiện có deadline và thu bằng chứng khi hết hạn. Đợi quá lâu có thể che vi phạm; đợi quá ngắn có thể gây kết quả không ổn định.

Không thử lại toàn bộ test nhiều lần rồi chỉ giữ lần đạt. Nếu có cơ chế chạy lại để phân tích lỗi hạ tầng, phải giữ kết quả và lý do của những lần trước.

Dọn dẹp fixture phải diễn ra cả khi assertion thất bại. Dữ liệu còn sót có thể làm lần chạy sau nhận sai tác vụ, sai sự kiện hoặc sai trạng thái quyền.

## 13. Truy vết và đánh giá độ bao phủ

Một ma trận nhỏ giúp thấy mỗi yêu cầu đã được kiểm tra ở đâu.

| Yêu cầu | Nhóm test case | Phạm vi chính |
| --- | --- | --- |
| SEC-EXP-AUTHZ-01@2 | Trường hợp hợp lệ | Quyền đúng, tenant đúng, dữ liệu đúng |
| SEC-EXP-AUTHZ-01@2 | Thiếu xác thực hoặc thiếu quyền | Từ chối theo hợp đồng |
| SEC-EXP-AUTHZ-01@2 | Truy cập chéo tenant | API và đối tượng thuộc tenant khác |
| SEC-EXP-AUTHZ-01@2 | Đường tải và worker | Điểm thực thi ngoài màn hình chính |
| SEC-EXP-REV-01@1 | Phiên cũ và cache | Quyền cũ không tồn tại quá hạn |
| SEC-EXP-REV-01@1 | Tác vụ chờ, thử lại, liên kết cũ | Chuyển trạng thái và các quyết định cấp mới |
| SEC-EXP-REV-01@1 | Lỗi dịch vụ quyền | Hành vi khi không xác minh được quyền |
| SEC-EXP-AUD-01@1 | Audit của thành công và từ chối | Sự kiện, trường, liên kết và độ trễ |
| SEC-EXP-AUD-01@1 | Nội dung bị cấm | Không ghi hồ sơ, token hoặc bí mật |

Để đánh giá độ bao phủ, hỏi:

1. Mỗi mệnh đề quan trọng của yêu cầu có phép kiểm tra nào?
2. Mỗi điểm thực thi trong phạm vi đã được xét chưa?
3. Có cả trường hợp được phép và bị cấm không?
4. Các ranh giới, chuyển trạng thái và lỗi phụ thuộc liên quan đã được kiểm tra chưa?
5. Phần nào cần bằng chứng ngoài test script?
6. Phần nào đang bị chặn hoặc chưa thể quan sát?

Số lượng test case hoặc tỷ lệ bao phủ dòng mã không tự chứng minh yêu cầu đã được kiểm chứng đầy đủ. Nhiều test cùng kiểm tra một đường giao diện vẫn có thể bỏ sót một đường tải không phân quyền.

Khi yêu cầu đổi phiên bản, cần phân tích test nào còn đúng, test nào cần sửa và bằng chứng cũ còn hỗ trợ kết luận nào. Không tự gắn kết quả của phiên bản cũ cho tiêu chí mới.

## 14. Kết quả chạy và bằng chứng

Có thể phân loại kết quả như sau, với ý nghĩa được thống nhất trong nhóm:

| Kết quả | Ý nghĩa |
| --- | --- |
| PASS | Đã thực hiện và các quan sát cần thiết đáp ứng oracle trong phạm vi bài thử |
| FAIL | Có quan sát đáng tin cậy trái kết quả kỳ vọng |
| BLOCKED | Không thể thực hiện do thiếu điều kiện đầu hoặc phụ thuộc cần thiết |
| INCONCLUSIVE | Đã có quan sát nhưng chưa đủ hoặc không đủ tin cậy để kết luận |
| NOT_RUN | Chưa thực hiện |

Nếu yêu cầu bắt buộc audit và kho audit thực sự không nhận sự kiện đúng hạn trong điều kiện thử hợp lệ, đó có thể là FAIL. Nếu hệ thống quan sát của bộ thử không kết nối được và không xác định được sự kiện có tồn tại không, cần phân biệt với lỗi sản phẩm.

Một gói bằng chứng nên có:

- Mã test case, phiên bản yêu cầu và kết quả.
- Bản dựng, phiên bản cấu hình và môi trường.
- Fixture, namespace và trạng thái đầu liên quan.
- Mốc thời gian, mã yêu cầu, mã tác vụ và mã liên kết.
- Phản hồi, trạng thái hoặc sự kiện cần thiết đã được bảo vệ phù hợp.
- Bước thực tế, khác biệt so với kế hoạch và giới hạn quan sát.
- Lỗi được tạo và phạm vi ảnh hưởng nếu kết quả không đạt.

Bằng chứng phải đủ để đánh giá kết luận, không phải thu mọi dữ liệu có thể thu. Hạn chế nội dung nhạy cảm và không ghi token vào log của chính bộ thử.

Một test case có nhiều mục tiêu cần phản ánh phần nào thất bại. Ví dụ API từ chối đúng nhưng audit thiếu sự kiện: yêu cầu phân quyền có thể đạt trong tình huống đó, còn yêu cầu audit không đạt. Không dùng một nhãn chung để che khác biệt này.

## 15. Những lỗi thường gặp

| Lỗi thiết kế hoặc thực hiện | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ kiểm tra trường hợp hợp lệ | Chưa kiểm chứng điều cấm | Thêm trường hợp thiếu quyền, sai đối tượng và sai tenant |
| Chỉ nhìn nút bị ẩn | Bỏ sót thực thi phía máy chủ | Gọi đường API và đường nhận dữ liệu thực |
| Chỉ khẳng định mã 403 | Bỏ sót tác dụng phụ hoặc rò rỉ | Kiểm tra dữ liệu, tác vụ, tệp và audit theo yêu cầu |
| Dùng đối tượng không tồn tại để thử chéo tenant | Không biết từ chối vì sai tenant hay không tìm thấy | Tạo fixture mục tiêu có thật và giữ điều kiện khác hợp lệ |
| Bắt buộc vẫn cho phép ngay trước hạn thu hồi | Thêm quy tắc không có trong yêu cầu | Hiểu ngưỡng tối đa và kỳ vọng tại ranh giới |
| Dùng thời điểm gửi request thay thời điểm quyết định | Đánh giá sai trường hợp gần hạn | Ghi đúng mốc theo đặc tả |
| Tăng đồng hồ của một thành phần rồi kết luận toàn hệ thống | Bỏ qua thời gian và trạng thái của phụ thuộc | Tách thử logic khỏi thử tích hợp |
| Thêm sleep dài để tránh lỗi không ổn định | Chậm và có thể che vượt hạn | Chờ điều kiện có deadline và bằng chứng |
| Chạy lại tới khi đạt | Che lỗi hoặc mất dấu lần thất bại | Giữ lịch sử và phân tích nguyên nhân |
| Không gắn test với phiên bản yêu cầu | Kết quả không biết áp dụng cho tiêu chí nào | Giữ liên kết phiên bản |
| Không dọn dữ liệu thử | Lần chạy sau bị nhiễu | Cô lập fixture và dọn dẹp cả khi lỗi |
| Ghi toàn bộ request để làm bằng chứng | Bộ thử làm lộ bí mật | Che thông tin và giới hạn hiện vật cần lưu |

## 16. Tiêu chí sẵn sàng của bộ test case

Một bộ test case từ security requirement sẵn sàng để thực hiện khi:

- Yêu cầu nguồn có mã, phiên bản và các điểm mơ hồ trọng yếu đã được xử lý hoặc ghi rõ là việc còn mở.
- Mỗi test case có mục tiêu riêng và điều kiện đầu đủ để cô lập điều cần kiểm tra.
- Dữ liệu thử không cần dùng bí mật hoặc dữ liệu thật ngoài phạm vi cho phép.
- Có kết quả kỳ vọng cho phản hồi và các tác động liên quan.
- Đã xét các trường hợp được phép, bị cấm, ranh giới, chuyển trạng thái và lỗi phù hợp với rủi ro.
- Có cách quan sát API, worker, đường tải hoặc các điểm thực thi thuộc phạm vi.
- Các phép đo thời gian có mốc, deadline và giới hạn sai số rõ ràng.
- Những phần chưa thể kết luận không bị coi là PASS.
- Bằng chứng, phiên bản môi trường và trách nhiệm xử lý lỗi đã được xác định.
- Việc dọn dẹp và cập nhật khi yêu cầu thay đổi đã được tính đến.

Giá trị của test case nằm ở khả năng kiểm chứng một tuyên bố bảo mật cụ thể bằng quan sát đáng tin cậy. Giữ chặt liên kết giữa yêu cầu, tình huống, oracle và bằng chứng giúp kết quả kiểm thử trở thành căn cứ có thể xem xét trong toàn bộ vòng đời phát triển.
