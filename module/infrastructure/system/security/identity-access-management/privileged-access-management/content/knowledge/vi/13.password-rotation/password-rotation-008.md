# Dual account rotation

## Mục tiêu bài học

Trong chương **Password rotation**, dual account rotation là mô hình luân phiên hai tài khoản cho cùng một nhu cầu dịch vụ. Khi ứng dụng đang sử dụng tài khoản A, hệ thống chuẩn bị credential của tài khoản B, xác minh B, chuyển ứng dụng sang B rồi xử lý credential và phiên của A. Lần tiếp theo có thể chuyển theo chiều ngược lại.

Trong **Privileged Access Management (PAM)**, mô hình này hữu ích với một số tài khoản dịch vụ và đường truy cập tới hạ tầng nhạy cảm. Nó cần kết hợp kiểm kê quyền, least privilege, vault, ownership, quản lý phụ thuộc, giám sát phiên và bằng chứng kiểm toán.

**Hai tài khoản tạo điều kiện chuyển đổi theo giai đoạn, không tự bảo đảm không gián đoạn.** Kết quả phụ thuộc khả năng của hệ thống đích, cách ứng dụng nhận cả tên tài khoản lẫn mật khẩu và cơ chế thu hồi đường sử dụng cũ.

Sau bài học, bạn có thể:

- Phân biệt dual account rotation với hai mật khẩu trên một tài khoản.
- Xác định điều kiện áp dụng và các giới hạn của mô hình.
- Thiết kế bộ credential nhất quán và cơ chế chuyển lựa chọn.
- Điều phối chuẩn bị, công bố, chuyển consumer và thu hồi.
- Xử lý lỗi từng giai đoạn mà không làm lệch trạng thái.
- Xác minh quyền, kết nối mới, phiên cũ và bằng chứng hoàn tất.

## 1. Mô hình hai tài khoản giải quyết vấn đề gì?

Với một tài khoản chỉ chấp nhận một mật khẩu hiện hành, đổi mật khẩu tại đích có thể khiến những consumer chưa cập nhật không mở được kết nối mới. Nếu cập nhật ứng dụng trước, mật khẩu mới lại có thể chưa được đích chấp nhận.

Dual account rotation tách giai đoạn chuẩn bị khỏi tài khoản đang phục vụ:

~~~text
Ban đầu:
  Consumer --> tài khoản A với credential A hiện hành
  Tài khoản B --> chưa được chọn cho luồng phục vụ này

Chuẩn bị:
  Consumer --> A
  Hệ thống quản lý --> tạo hoặc đổi credential B và xác minh

Chuyển đổi:
  Consumer chuyển dần --> B
  A còn được xử lý trong cửa sổ chuyển tiếp có kiểm soát

Hoàn tất:
  Consumer --> B
  Credential cũ và phiên A được xử lý theo chính sách
~~~

Lợi ích là có thể kiểm tra ứng viên B trước khi thay lựa chọn của consumer. Tuy nhiên, nếu consumer không hỗ trợ đổi tài khoản hoặc vẫn giữ cache vô thời hạn, mô hình chưa giải quyết được vấn đề.

### Ba mô hình dễ nhầm

| Mô hình | Đặc điểm |
| --- | --- |
| Hai tài khoản luân phiên | A và B là hai principal riêng, mỗi principal có credential riêng |
| Hai credential của một tài khoản | Một principal có nhiều vật liệu xác thực cùng hoặc khác hiệu lực |
| Tài khoản quản lý đổi mật khẩu cho tài khoản đích | Một principal dùng quyền quản lý để reset principal khác |

Một hệ thống có thể kết hợp các mô hình, nhưng không nên gọi chúng là cùng một cơ chế. Bài này tập trung vào hai principal luân phiên cho một mục đích dịch vụ.

## 2. Khi nào mô hình phù hợp?

Cần đánh giá các điều kiện sau:

- Hệ thống đích cho phép tồn tại hai principal phục vụ cùng nhu cầu.
- Ứng dụng có thể thay cả tên tài khoản và bí mật theo một bộ nhất quán.
- Có cách cấp các khả năng nghiệp vụ cần thiết cho từng principal.
- Có thể chuẩn bị và kiểm tra tài khoản chưa được chọn.
- Các consumer có cơ chế nạp lại hoặc chuyển đổi trong khoảng chấp nhận.
- Có cách ngăn consumer tiếp tục dùng credential cũ ngoài chính sách.
- Có owner, điều phối và bằng chứng cho cả cặp tài khoản.

### Những trường hợp cần thận trọng

| Trường hợp | Vấn đề |
| --- | --- |
| Đích chỉ có một tài khoản tích hợp duy nhất | Có thể không tạo được cặp principal tương đương |
| Ứng dụng cố định username | Chỉ đổi password không thực hiện được chuyển tài khoản |
| Quyền hoặc dữ liệu gắn chặt với principal | Hai tài khoản có thể không tương đương về hành vi |
| Nhiều consumer không được kiểm kê | Khó biết khi nào tài khoản cũ có thể ngừng phục vụ |
| Client không nạp lại hoặc giữ bí mật lâu dài | Lựa chọn mới không được áp dụng kịp thời |
| Không kiểm soát được đường truy cập ngoài PAM | Không thể kết luận toàn bộ việc sử dụng cũ đã kết thúc |

Nếu các điều kiện không phù hợp, cần đánh giá phương án khác như cải thiện khả năng nạp bí mật, dùng nhiều credential của một principal nếu được hỗ trợ hoặc chuyển sang danh tính có vòng đời phù hợp.

Không tạo tài khoản quản trị toàn quyền thứ hai chỉ để làm cho mô hình trông dễ triển khai.

## 3. Hai tài khoản cần tương đương về nhiệm vụ, không chỉ về tên role

A và B phải thực hiện được cùng những tác vụ cần giữ. Nhưng “cùng role” chưa chắc tạo cùng hành vi.

Cần xem xét theo nền tảng:

- Quyền trực tiếp, role, nhóm và kế thừa.
- Scope tài nguyên và điều kiện truy cập.
- Quyền sở hữu đối tượng.
- Không gian tên, schema mặc định hoặc môi trường làm việc.
- Chính sách dữ liệu phụ thuộc danh tính.
- Giới hạn tài nguyên và hạn mức theo tài khoản.
- Tác vụ hoặc cấu hình gắn với principal.
- Cơ chế audit và liên kết với workload.

Ví dụ, B đăng nhập được database nhưng không có quyền cần thiết trên đối tượng mà A đang sở hữu. Kiểm tra đăng nhập đơn thuần sẽ không phát hiện đầy đủ khác biệt đó.

### Least privilege cho cả hai

Mỗi tài khoản chỉ cần những khả năng phù hợp với nhiệm vụ. Nếu A đang có quyền dư, sao chép nguyên trạng sang B sẽ nhân đôi phạm vi cần xử lý.

Nên xác định tập khả năng mong muốn trước, triển khai cho cả hai rồi kiểm tra. Những khác biệt có chủ ý phải được ghi nhận, không để thành lệch quyền không ai biết.

Hai tài khoản có quyền tương tự vẫn là hai đường tấn công. Mức phơi lộ cần được giới hạn bằng chính sách sử dụng, nguồn kết nối, vòng đời credential và khả năng ngừng tài khoản không được chọn.

## 4. Phân biệt “được chọn” với “còn xác thực được”

Trong mô hình này, từ “active” có thể gây hiểu nhầm. Cần chỉ rõ trạng thái đang nói tới.

| Trạng thái | Ý nghĩa |
| --- | --- |
| Được chọn cho yêu cầu mới | Bộ lựa chọn hiện hành chỉ consumer sang tài khoản này |
| Có thể xác thực ở đích | Đích còn chấp nhận credential của tài khoản |
| Đang có phiên | Có kết nối hoặc phiên đã được thiết lập |
| Chưa được chọn | Không phải lựa chọn hiện hành, nhưng chưa chắc đã bị vô hiệu hóa |
| Đã ngừng credential cũ | Credential cũ không còn được chấp nhận trong phạm vi xác minh |
| Đã xử lý phiên | Những phiên thuộc mục tiêu đã kết thúc hoặc có trạng thái được chấp nhận |

Một tài khoản không được chọn có thể vẫn đang có phiên. Một tài khoản bị chặn đăng nhập mới cũng có thể còn phiên hoạt động, tùy cơ chế đích.

Vì vậy, không dùng một cờ “inactive” chung để kết luận cả ba lớp đã hết hiệu lực.

## 5. Kiến trúc logic

~~~mermaid
flowchart TD
    Consumer[Ứng dụng và job] --> Resolve[Bộ phân giải credential logic]
    Resolve --> Selection[Lựa chọn và thế hệ hiện hành]
    Selection --> BundleA[Bộ credential A]
    Selection --> BundleB[Bộ credential B]
    Controller[Bộ điều phối rotation] --> Selection
    Controller --> Vault[Vault và trạng thái được bảo vệ]
    Vault --> BundleA
    Vault --> BundleB
    Controller --> Target[Hệ thống đích]
    Consumer --> Target
    Controller --> Evidence[Audit và bằng chứng]
    Resolve --> Evidence
    Target --> Evidence
~~~

Đây là các trách nhiệm logic, không bắt buộc tương ứng với từng sản phẩm riêng.

### Credential logic

Consumer yêu cầu một tham chiếu ổn định cho nhiệm vụ, chẳng hạn “credential runtime dịch vụ A”. Tham chiếu đó được phân giải sang A hoặc B cùng dữ liệu cần thiết.

Ứng dụng không nên tự đoán tài khoản hiện hành từ tên file, thời gian hoặc quy tắc chẵn/lẻ.

### Tài khoản vật lý

Cả A và B cần được kiểm kê và quản lý riêng: ID principal, đích, quyền, owner, credential và trạng thái. Đồng thời phải biết chúng thuộc cùng một cặp luân phiên.

### Bộ điều phối

Bộ điều phối quản lý trạng thái thay đổi, tránh nhiều bên cùng thao tác, công bố lựa chọn và theo dõi chuyển đổi.

Nó không được xem một lần cập nhật con trỏ trong vault là bằng chứng mọi consumer đã chuyển xong.

## 6. Phân phối username và password như một bộ nhất quán

Một lỗi quan trọng là consumer đọc username A nhưng password B do hai trường được cập nhật độc lập.

Bộ dữ liệu phân phối cần nhất quán, có thể bao gồm:

~~~text
ID principal
Tên đăng nhập hoặc thông tin nhận diện
Credential và phiên bản
Nguồn xác thực hoặc endpoint cần thiết
Thế hệ lựa chọn
Thông tin vòng đời có liên quan
~~~

Cách lưu cụ thể phụ thuộc giải pháp. Ý tưởng là consumer sử dụng một bộ có phiên bản, không tự ghép các giá trị đọc ở những thời điểm khác nhau.

### Bộ bất biến và lựa chọn có phiên bản

Một thiết kế có thể tạo bộ credential ứng viên, xác minh rồi cập nhật lựa chọn sang bộ đó. Việc cập nhật lựa chọn cần có kiểm soát đồng thời theo khả năng nền tảng.

Tuy nhiên, một thay đổi nhất quán tại nơi công bố không tự làm mọi consumer cập nhật cùng lúc. Cache, lịch nạp lại và kết nối đang mở vẫn tạo giai đoạn nhiều trạng thái cùng tồn tại.

### Không ghi bộ bí mật vào log

Hồ sơ và audit nên dùng ID bộ, principal, phiên bản và thế hệ. Không ghi password hoặc payload phản hồi chứa bí mật.

Quyền đọc bộ A, bộ B và quyền đổi lựa chọn phải được thiết kế rõ. Không mặc định mọi consumer cần duyệt hoặc đọc lịch sử của cả cặp.

## 7. Những điều kiện phải giữ trong suốt chu trình

Một thiết kế nên có các điều kiện rõ ràng:

1. Mỗi principal và credential được ánh xạ đúng với đích.
2. Có một cơ chế điều phối có thẩm quyền cho cặp tài khoản.
3. Không đổi tài khoản dự phòng khi nó vẫn đang được consumer sử dụng ngoài kế hoạch.
4. Tài khoản ứng viên được xác minh trước khi công bố cho luồng mới.
5. Consumer nhận username và credential nhất quán.
6. Giai đoạn cùng tồn tại có giới hạn và người chịu trách nhiệm.
7. Không thu hồi tài khoản cũ chỉ dựa vào việc con trỏ đã đổi.
8. Không tự quay về credential cũ khi nó không còn được tin cậy.
9. Có bằng chứng cho kết quả và những phần chưa xác định.

### Tại sao phải kiểm tra tài khoản dự phòng?

Một consumer chậm có thể vẫn giữ B từ chu trình trước, dù lựa chọn hiện hành đã là A. Nếu lần này đổi B vì nghĩ nó “đang rảnh”, consumer đó có thể bị gián đoạn.

Vì vậy, trước khi chuẩn bị một slot, cần biết trạng thái sử dụng của nó trong phạm vi đã quản lý. Không chỉ nhìn nhãn lựa chọn hiện tại.

Nếu không đủ bằng chứng, cần giữ phần chưa rõ, xử lý consumer hoặc có quyết định theo mức rủi ro. Không giả định mọi cache đều đã hết hạn.

## 8. Chu trình minh họa: từ A sang B

### Giai đoạn 1: xác nhận trạng thái ban đầu

Xác nhận:

- A đang được chọn cho yêu cầu mới.
- Thế hệ lựa chọn hiện hành.
- Các consumer, cách nạp lại và phạm vi quan sát.
- B có thể được chuẩn bị mà không ảnh hưởng consumer còn dùng nó.
- Quyền và mapping đích của cả hai.
- Không có thao tác rotation xung đột đang diễn ra.

Nếu B đang bị vô hiệu hóa, cần quy trình chuẩn bị thích hợp để có thể xác minh. Nếu B còn bật nhưng chưa được chọn, cần hiểu mức phơi lộ và quyền tiếp cận hiện tại.

### Giai đoạn 2: chuẩn bị B

Tạo mật khẩu mới bằng cơ chế ngẫu nhiên phù hợp cho bảo mật, đáp ứng giới hạn đích và khác với credential của A.

Áp dụng thay đổi tại nguồn có thẩm quyền, giữ trạng thái ứng viên được bảo vệ và xác minh kết quả. Cần xử lý kết quả chưa rõ nếu yêu cầu đã gửi nhưng mất phản hồi.

Không công bố B chỉ vì một giá trị mới đã được lưu trong vault.

### Giai đoạn 3: kiểm tra B

Kiểm tra kết nối mới từ đường phù hợp và những tác vụ đại diện.

Cần xác nhận B có đủ quyền cần thiết nhưng không mở rộng quyền ngoài mục tiêu. Nếu lỗi do khác biệt principal, xử lý đúng nguyên nhân thay vì cấp admin tổng quát.

### Giai đoạn 4: công bố thế hệ mới

Cập nhật lựa chọn sang B với một thế hệ mới theo cơ chế kiểm soát đồng thời.

Từ đây, consumer nạp mới sẽ nhận B theo thiết kế. Những consumer đã cache A hoặc giữ phiên A có thể chưa chuyển.

Công bố là một mốc của chu trình, không phải kết thúc chu trình.

### Giai đoạn 5: chuyển consumer

Mỗi consumer owner thực hiện phần việc đã giao: nạp lại, triển khai, khởi động lại có kiểm soát hoặc cơ chế tương ứng.

Xác minh kết nối mới sử dụng B và tác vụ hợp lệ. Theo dõi từng consumer hoặc từng nhóm có cơ chế chuyển đổi tương đương đã được xác nhận.

### Giai đoạn 6: xử lý A

Khi đạt điều kiện, xử lý credential A cũ và những phiên liên quan theo chính sách.

Cách thực hiện có thể là vô hiệu hóa đăng nhập, đổi mật khẩu chưa phân phối hoặc cơ chế phù hợp khác. Mỗi cách có tác động khác nhau và phải được xác minh.

Nếu còn phiên A, cần tiếp tục xử lý hoặc ghi trạng thái được chấp nhận. Không tuyên bố mọi quyền A đã hết chỉ vì kết nối mới bị từ chối.

### Giai đoạn 7: ổn định và chuẩn bị lần sau

B là tài khoản được chọn. A trở thành slot cho chu trình tiếp theo, với trạng thái rõ ràng và không còn credential cũ được sử dụng ngoài chính sách.

Lần sau không chỉ đổi chữ B thành A. Cần kiểm tra lại quyền, consumer, trạng thái slot và những thay đổi từ chu trình trước.

## 9. Trạng thái chu trình phải biểu diễn được chuyển đổi

~~~text
Ổn định với A
      |
      v
Đang chuẩn bị B
      |
      v
B đã được xác minh
      |
      v
Đã công bố B, consumer đang chuyển
      |
      v
Đang xử lý credential và phiên A
      |
      v
Ổn định với B
~~~

Ở mỗi giai đoạn có thể xuất hiện trạng thái lỗi hoặc chưa xác định. Không nên chỉ có hai trạng thái “A active” và “B active”.

Một hồ sơ vận hành nên theo dõi:

- ID thao tác và cặp tài khoản.
- Thế hệ bắt đầu và thế hệ dự định công bố.
- Phiên bản credential ứng viên.
- Kết quả thay đổi tại đích.
- Kết quả công bố lựa chọn.
- Tiến độ consumer.
- Trạng thái credential và phiên cũ.
- Những việc cần đối soát.

Không lưu mật khẩu trong trường trạng thái hoặc thông báo lỗi.

## 10. Consumer, cache và connection pool

### 10.1. Nạp lại theo yêu cầu

Nếu consumer có thể lấy bộ hiện hành khi mở kết nối mới, cần kiểm tra cache và cách xử lý lỗi. Không mặc định mọi lần mở kết nối đều gọi vault.

### 10.2. Chỉ đọc lúc khởi động

Consumer có thể cần một lần triển khai hoặc khởi động lại phù hợp. Phải biết instance nào đã chuyển và instance nào chưa.

Không chấm dứt A khi còn instance bắt buộc dùng A mà chưa có kế hoạch xử lý.

### 10.3. Connection pool

Pool có thể giữ kết nối A trong khi kết nối B mới được tạo. Cần phân biệt:

- Đã nạp bộ B.
- Đã mở được kết nối B.
- Chức năng chạy đúng qua kết nối B.
- Không còn phụ thuộc vào việc mở kết nối A mới.
- Phiên A đã được xử lý theo mục tiêu.

Việc đóng hoặc rút dần pool phải phù hợp với tải và tác vụ đang chạy. Không đóng hàng loạt phiên production chỉ để có một dấu kiểm hoàn tất.

### 10.4. Job chạy hiếm hoặc tạm thời không hoạt động

Một job chưa chạy trong cửa sổ chuyển đổi vẫn cần cách bảo đảm lần chạy tiếp theo lấy bộ hiện hành.

Có thể phải xác minh cấu hình, quyền nạp bí mật và hành vi khởi tạo. Không dùng “không có log dùng A” làm bằng chứng duy nhất rằng job đã chuyển.

Những bảo đảm dựa trên thiết kế phải được ghi khác với bằng chứng đã quan sát thực thi. Nếu còn khoảng trống, nêu rõ người chịu trách nhiệm và điều kiện xử lý.

## 11. Điều phối đồng thời và công bố an toàn

### Một cặp tài khoản không nên bị hai chu trình điều khiển xung đột

Nếu hai controller cùng thấy A đang được chọn, một bên có thể chuẩn bị B trong khi bên kia đổi B lần nữa hoặc công bố dựa trên trạng thái đã cũ.

Cần cơ chế điều phối theo cặp và kiểm tra phiên bản lựa chọn trước khi công bố, chẳng hạn so sánh với thế hệ mong đợi nếu nền tảng hỗ trợ.

### Khóa có thời hạn chưa đủ trong mọi tình huống

Một tiến trình cũ có thể tiếp tục chạy sau khi mất quyền giữ khóa. Nếu nó vẫn được phép reset tài khoản, nó có thể phá trạng thái của controller mới.

Cần xem cách ngăn thao tác từ tiến trình đã hết quyền điều phối. Có thể là cơ chế fencing tại đường thực thi, một dịch vụ trung gian kiểm soát thao tác hoặc cơ chế loại trừ tương ứng.

Nếu đích không kiểm tra được quyền điều phối theo phiên bản, không nên tuyên bố một lease đơn giản đã ngăn mọi thao tác cũ. Phải thiết kế ranh giới thực thi phù hợp.

### Thao tác lặp và kết quả mất phản hồi

Gửi lại một yêu cầu đổi password có thể tạo password khác. Gửi lại yêu cầu công bố có thể xảy ra sau khi lần trước đã thành công.

Cần ID thao tác, trạng thái bền vững và quy tắc đối soát. Không mặc định timeout nghĩa là chưa có thay đổi.

### Thế hệ phải giúp nhận biết cập nhật cũ

Nếu phải quay lại dùng A, nên có một thế hệ mới cho quyết định đó. Không tái sử dụng một nhãn cũ theo cách khiến consumer không nhận biết đã có chu trình chuyển đổi.

Điều quan trọng là consumer có thể phát hiện một quyết định mới và không ghép trạng thái từ nhiều thế hệ.

## 12. Xử lý lỗi theo giai đoạn

| Thời điểm lỗi | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Trước khi đổi B | Chưa có ứng viên | Giữ A theo trạng thái hợp lệ, xử lý điều kiện chuẩn bị |
| Đổi B nhưng mất phản hồi | Không rõ password tại đích | Đối soát bằng trạng thái ứng viên được bảo vệ |
| B xác thực được nhưng thiếu chức năng | Chuyển đổi có thể làm hỏng dịch vụ | Sửa quyền hoặc cấu hình đúng phạm vi trước công bố |
| Công bố B thất bại chưa rõ | Consumer có thể đã thấy B | Xác định thế hệ thực tế trước thao tác tiếp |
| Một số consumer chuyển, số khác chưa | Hai principal cùng được dùng | Theo dõi tiến độ và xử lý trong cửa sổ được chấp nhận |
| Hết cửa sổ mà còn consumer A | Xung đột an toàn và tính sẵn sàng | Escalation và quyết định có thẩm quyền, không giữ mở vô hạn |
| A bị thu hồi nhưng còn phiên | Đặc quyền có thể tiếp tục | Xử lý vòng đời phiên theo mục tiêu |
| Controller phục hồi từ trạng thái cũ | Có thể công bố hoặc reset sai | Đối soát lựa chọn, đích và ledger trước tiếp tục |

Không để một cờ “rotation failed” che mất giai đoạn thực tế. Quyết định phục hồi phụ thuộc B đã được công bố hay chưa và consumer nào đã có thể nhận nó.

### Lỗi trước công bố

Nếu B chưa được phát hành và A vẫn đáng tin cậy, có thể giữ luồng A trong khi xử lý B theo chính sách. Nhưng phải biết chắc việc công bố chưa xảy ra.

### Lỗi sau công bố

Sau khi consumer có thể nhận B, cần xem trạng thái cả hai phía. Quay con trỏ về A không tự thu hồi B hoặc bảo đảm mọi consumer đổi trở lại.

Cần một kế hoạch chuyển có thế hệ, bằng chứng và xử lý các kết nối đã mở. Không chỉ sửa một giá trị rồi coi toàn hệ thống đã trở về ban đầu.

## 13. Fallback và rollback cần có giới hạn

Một client tự thử A rồi B khi gặp mọi lỗi có thể:

- Giữ credential cũ tồn tại ngoài chính sách.
- Che giấu việc chuyển đổi thất bại.
- Tạo nhiều lần xác thực sai và nguy cơ khóa tài khoản.
- Dùng tài khoản không còn phù hợp với quyết định hiện hành.
- Làm khó quy trách nhiệm và đo tiến độ.

Nếu thiết kế có fallback, cần xác định chính xác điều kiện, thời hạn, quyền truy xuất và bằng chứng. Không mặc định cấp cho mọi consumer cả lịch sử bí mật để tự tìm cái còn dùng được.

### Khi có thể cân nhắc quay lại

Chỉ xem xét một đường trước đó khi nó còn được tin cậy, còn hợp lệ và việc sử dụng phù hợp quyết định hiện tại.

Sau khi credential cũ đã bị thu hồi, không nên tự kích hoạt lại chỉ để giảm lỗi. Có thể cần chuẩn bị một bộ mới hoặc một phương án thay thế được xác minh.

Mọi quyết định quay lại đều phải xem các consumer đã nhận thế hệ mới và phiên đã tạo, thay vì chỉ xem lựa chọn tại vault.

## 14. Khi rotation do nghi bị lộ

Dual account rotation không làm một nguồn bị kiểm soát trở nên tin cậy.

Nếu A bị nghi lộ:

- Cần hạn chế khả năng dùng A theo mức khẩn cấp.
- Không mặc định chờ mọi consumer chuyển xong trong một cửa sổ dài.
- Có thể phải chấp nhận gián đoạn theo quyết định ứng phó.
- Phải xét phiên A, token và quyền phát sinh.
- Không dùng credential A cũ làm fallback thông thường.

Nếu môi trường nhận bí mật bị nghi kiểm soát, B cũng có thể bị lộ khi phân phối. Cần xử lý đường thực thi, vault, policy hoặc consumer liên quan theo bằng chứng.

Lựa chọn B chỉ thay principal và credential được dùng. Nó không tự xóa hành động đã xảy ra hoặc credential khác do chủ thể đặc quyền tạo.

## 15. Ownership, phân quyền và audit

### Ownership cho cặp và từng tài khoản

Cần biết ai chịu trách nhiệm về:

- Mục đích của credential logic.
- Tài khoản A và B tại đích.
- Quyền của cả hai.
- Bộ điều phối và quyền reset.
- Từng consumer.
- Quyết định xử lý khi quá cửa sổ hoặc có sự cố.

Đội PAM vận hành rotation không tự trở thành owner nghiệp vụ của mọi consumer.

### Phân quyền

Controller chỉ cần các thao tác được giao cho cặp tài khoản trong phạm vi. Consumer chỉ cần nhận bộ phù hợp theo thiết kế.

Quyền đổi lựa chọn, sửa mapping hoặc thêm tài khoản vào cặp là những khả năng nhạy cảm. Một người sửa mapping có thể chuyển consumer sang principal khác ngoài ý định.

### Bằng chứng

Cần liên kết được:

~~~text
Yêu cầu và người điều phối
       |
       v
Cặp tài khoản, phiên bản và thế hệ bắt đầu
       |
       v
Chuẩn bị và xác minh ứng viên
       |
       v
Công bố thế hệ mới
       |
       v
Consumer chuyển đổi và tác vụ hợp lệ
       |
       v
Thu hồi credential, xử lý phiên và kết luận
~~~

Tại đích, A và B có thể xuất hiện như hai danh tính khác nhau. Audit cần giữ quan hệ với cùng dịch vụ và chu trình nhưng vẫn phân biệt principal, thời gian và phiên.

Không ghi password hoặc bộ phản hồi có bí mật vào timeline.

## 16. Ví dụ: API và worker chuyển từ A sang B

Một dịch vụ có API và worker nền dùng cặp tài khoản trên database. A đang được chọn. B đã được kiểm tra không còn consumer thuộc phạm vi cần sử dụng trước khi chuẩn bị.

### Chuẩn bị

Nhóm xác nhận quyền mong muốn, tạo credential B mới và kiểm tra kết nối. B đăng nhập được nhưng thiếu một khả năng cần cho worker.

Nhóm sửa đúng phần quyền cần thiết theo quyết định đã được chấp nhận, rồi kiểm tra tác vụ đại diện. Không sao chép thêm toàn bộ quyền quản trị của A nếu đó là quyền dư.

### Công bố và chuyển

Một thế hệ mới chọn B được công bố.

- Các instance API nạp bộ mới và mở kết nối B thành công.
- Worker vẫn giữ A do chỉ nạp cấu hình khi khởi động.
- Một số phiên A của API còn tồn tại trong pool.

Trạng thái đúng là “đã công bố B, đang chuyển consumer và xử lý A”, chưa phải hoàn tất.

### Hoàn thiện

Consumer owner của worker thực hiện chuyển đổi theo kế hoạch, kiểm tra kết nối mới và tác vụ hợp lệ.

Nhóm xử lý pool và các phiên A theo chính sách, sau đó thu hồi khả năng dùng credential A cũ. Việc xác minh phân biệt từ chối đăng nhập mới với kết thúc phiên.

Khi đủ bằng chứng, B là lựa chọn ổn định. A có trạng thái rõ ràng cho chu trình tiếp theo.

### Điều cần tránh

Nếu worker chưa chuyển mà controller đã bắt đầu một chu trình mới chuẩn bị A, nó có thể tác động lên một tài khoản vẫn đang được dùng.

Không chỉ dựa vào việc B đang được chọn để cho phép chu trình kế tiếp. Phải kiểm tra trạng thái vòng đời của cả cặp.

## 17. Hồ sơ chu trình minh họa

Ví dụ sau là **mô tả dữ liệu vận hành, không phải cấu hình chạy trực tiếp của một sản phẩm**. Hồ sơ không chứa giá trị bí mật.

~~~yaml
rotation_pair:
  reference: service-a-runtime-pair
  logical_credential_reference: service-a-runtime
  account_a_reference: service-a-account-a
  account_b_reference: service-a-account-b
  owner_reference: application-a-operations
  target_reference: production-database-a

operation:
  reference: rotation-operation-example
  source_generation: generation-example-31
  candidate_generation: generation-example-32
  from_account: service-a-account-a
  to_account: service-a-account-b

candidate:
  credential_version_reference: protected-version-b-new
  target_authentication: verified
  required_capabilities: verified

publication:
  selected_account: service-a-account-b
  generation: generation-example-32
  result: confirmed

consumers:
  api:
    new_connection: verified
    required_operation: verified
  background_worker:
    adoption: pending

retirement:
  old_credential: pending
  old_sessions: pending

decision:
  operation_state: migrating-consumers
  rotation_complete: false

evidence:
  secret_value_in_record: false
  operation_evidence_reference: protected-evidence-reference
~~~

Công bố đã thành công nhưng consumer và retirement chưa hoàn tất, nên chu trình chưa được đóng.

Những trường “verified” phải có bằng chứng phù hợp. Một nhãn do client tự khai báo không thay thế xác minh ở đích và consumer.

## 18. Tiêu chí nghiệm thu và chỉ số

### Tiêu chí cho một chu trình

- Đúng cặp tài khoản, principal và đích.
- Slot ứng viên được chuẩn bị mà không phá consumer còn dùng nó.
- Credential ứng viên được bảo vệ và xác minh.
- Những khả năng cần thiết của tài khoản ứng viên được kiểm tra.
- Bộ username và credential được phân phối nhất quán.
- Lựa chọn mới có thế hệ và kết quả công bố rõ ràng.
- Consumer trong phạm vi chuyển theo tiêu chí đã định nghĩa.
- Credential cũ và phiên cũ được xử lý theo mục tiêu.
- Có bằng chứng, ownership và phần ngoại lệ rõ ràng.

Không cần thực hiện hành động phá hủy để chứng minh quyền bị hạn chế. Có thể dùng cách đánh giá hoặc môi trường phù hợp với mức tác động.

### Những chỉ số cần phân biệt

| Chỉ số | Ý nghĩa |
| --- | --- |
| Chu trình chuyển credential logic đã hoàn tất | Kết quả của toàn bộ quy trình được định nghĩa |
| Lần đổi mật khẩu gần nhất của từng principal | Tuổi credential riêng của A và B |
| Thời gian cùng tồn tại | Khoảng có nhiều đường xác thực trong chuyển tiếp |
| Consumer chưa chuyển | Phần phụ thuộc còn giữ trạng thái cũ |
| Phiên cũ chưa xử lý | Phần khả năng sử dụng còn tồn tại |
| Lỗi xác thực sau công bố | Dấu hiệu lệch bộ, cache hoặc cấu hình |
| Lệch quyền giữa hai tài khoản | Rủi ro chức năng và least privilege |
| Chu trình chưa rõ kết quả | Công việc cần đối soát |

Nếu luân phiên theo chu kỳ T, việc đổi lựa chọn mỗi T không tự chứng minh mỗi principal cũng được đổi mật khẩu mỗi T. Cần đo lịch thực tế của A và B, bao gồm cách xử lý slot sau retirement.

Không đánh giá an toàn chỉ bằng số lần con trỏ đã chuyển.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Tưởng hai tài khoản là hai password của một principal | Thiết kế sai quyền và cách chuyển | Xác định mô hình danh tính thực tế |
| Cập nhật username và password độc lập | Consumer có thể nhận bộ không khớp | Phân phối bộ có phiên bản nhất quán |
| Xem slot không được chọn là không ai dùng | Có thể làm hỏng consumer chậm | Kiểm tra vòng đời và phạm vi sử dụng |
| Chỉ kiểm tra đăng nhập ứng viên | Bỏ sót quyền hoặc hành vi gắn principal | Kiểm tra tác vụ và giới hạn cần thiết |
| Đổi con trỏ là báo hoàn tất | Bỏ sót cache, consumer và phiên cũ | Theo dõi các giai đoạn riêng |
| Hai controller cùng điều khiển một cặp | Lệch password và thế hệ | Có điều phối, kiểm tra phiên bản và ngăn thao tác cũ |
| Fallback vô thời hạn sang cả hai | Giữ đường cũ và che lỗi chuyển đổi | Giới hạn theo điều kiện và bằng chứng |
| Tạo B bằng toàn quyền để dễ chuyển | Nhân đôi quyền dư | Thiết kế quyền theo nhu cầu |
| Vô hiệu hóa đăng nhập rồi coi phiên đã hết | Khả năng cũ có thể tiếp tục | Xác minh phiên theo cơ chế đích |
| Quay lại credential nghi lộ | Khôi phục đường rủi ro | Chọn phương án được tin cậy theo quyết định ứng phó |

## 20. Bài tập tự đánh giá

Một ứng dụng dùng A và B luân phiên. Controller đã đổi password B và công bố B, nhưng ứng dụng đọc username và password từ hai nguồn riêng. Một số instance nhận bộ sai. Worker vẫn dùng A. Nhóm định thu hồi A ngay vì B đã là lựa chọn hiện hành, rồi cho client tự thử cả hai khi lỗi.

Hãy trả lời:

1. Vì sao bộ credential cần được nhận nhất quán?
2. Công bố B đã chứng minh phần nào và chưa chứng minh phần nào?
3. Vì sao chưa thể kết luận A không còn được sử dụng?
4. Fallback tự do sang cả hai tạo rủi ro gì?
5. Lần rotation tiếp theo cần kiểm tra gì trước khi chuẩn bị A?
6. Nếu A bị nghi lộ, quyết định xử lý có gì khác rotation thông thường?

### Gợi ý phân tích

**Bộ credential:** username và password của hai principal không thể ghép tùy ý. Cần ID bộ, phiên bản và cơ chế cập nhật phù hợp.

**Công bố:** chứng minh lựa chọn đã thay đổi theo kết quả xác nhận; chưa chứng minh consumer đã nạp hoặc phiên cũ đã kết thúc.

**A còn được dùng:** worker, cache và pool có thể giữ trạng thái trước đó. Cần kiểm tra bằng chứng và điều kiện chuyển đổi.

**Fallback:** có thể kéo dài hiệu lực bản cũ, che lỗi và tạo nhiều lần xác thực sai. Nếu có, phải được giới hạn rõ.

**Chu trình tiếp:** cần xác nhận A không còn phục vụ consumer ngoài kế hoạch, quyền và mapping còn đúng, không có thao tác xung đột.

**Nghi lộ:** có thể cần ngừng A sớm hơn theo quyết định ứng phó và chấp nhận tác động dịch vụ. Không dùng A cũ làm đường dự phòng thông thường.

## 21. Những điểm cần ghi nhớ

- Dual account rotation dùng hai principal riêng luân phiên cho một mục đích; không tự tạo bảo đảm không gián đoạn.
- Hai tài khoản phải phù hợp về khả năng cần thiết và đều tuân thủ least privilege.
- Username, credential, principal và thế hệ cần được phân phối thành bộ nhất quán.
- Không được chọn không đồng nghĩa không còn xác thực hoặc không còn phiên.
- Chu trình phải bao phủ chuẩn bị, công bố, chuyển consumer, xử lý credential cũ và phiên.
- Điều phối đồng thời, trạng thái bền vững và đối soát giúp tránh thay đổi từ dữ liệu đã cũ.
- Chỉ nghiệm thu theo phần đã xác minh; fallback, ngoại lệ và nghi lộ cần quyết định riêng có thẩm quyền.
