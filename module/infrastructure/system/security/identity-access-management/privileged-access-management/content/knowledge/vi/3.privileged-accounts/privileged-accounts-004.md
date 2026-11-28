# Built-in administrator account

## 1. Mục tiêu và bối cảnh

Trong chương **Tài khoản đặc quyền**, *built-in administrator account* là tài khoản quản trị được tích hợp sẵn trong hệ thống hoặc sản phẩm để phục vụ những chức năng quản trị nền tảng. Tài khoản này có thể xuất hiện ngay khi cài đặt, khởi tạo hoặc đưa thiết bị vào sử dụng.

Trong PAM, đây là nhóm tài khoản cần được nhận diện và quản lý rõ ràng vì thường có quyền mạnh, có thể tồn tại ngoài hệ thống danh tính tập trung và dễ bị nhiều người dùng chung. Việc quản lý cần bao gồm kiểm kê quyền, least privilege, giới hạn đường truy cập, bảo vệ và luân chuyển credential, giám sát phiên và giữ bằng chứng cho kiểm toán, ứng phó sự cố.

Sau bài học, bạn có thể:

- Phân biệt tài khoản quản trị tích hợp với tài khoản quản trị tự tạo, tài khoản dịch vụ và tài khoản khẩn cấp.
- Nhận diện tài khoản theo hệ thống đích và định danh thực tế, thay vì chỉ dựa vào tên.
- Đánh giá phạm vi quyền, phương thức xác thực và các phụ thuộc trước khi thay đổi trạng thái tài khoản.
- Chọn cách bảo quản credential, luân chuyển và kiểm soát sử dụng phù hợp.
- Giải thích giới hạn của đổi tên, vô hiệu hóa mật khẩu, JIT và ghi hình phiên.

## 2. Tài khoản quản trị tích hợp là gì?

### 2.1. Đặc điểm cốt lõi

Tài khoản quản trị tích hợp là tài khoản được nền tảng định nghĩa sẵn cho một mục đích quản trị. Ví dụ quen thuộc gồm tài khoản Administrator tích hợp trong một số hệ thống Windows, tài khoản root trên hệ Unix/Linux hoặc tài khoản quản trị tích hợp của thiết bị và ứng dụng.

Những ví dụ này không có nghĩa chúng có cùng hành vi. Cách xác thực, phạm vi quyền, khả năng đổi tên, vô hiệu hóa hoặc xóa tài khoản khác nhau giữa các nền tảng và cấu hình. Một tài khoản có thể mang quyền đặc biệt do định danh hoặc ngữ nghĩa nội tại của hệ thống, chứ không chỉ do được thêm vào một nhóm quản trị.

Vì vậy, cần đánh giá trên đúng hệ thống đích:

- Tài khoản nào thực sự được tích hợp sẵn?
- Nó được hệ thống nhận diện bằng tên hay định danh nào?
- Quyền nào gắn với nó và có giới hạn gì?
- Nó cho phép những cách đăng nhập hoặc sử dụng nào?
- Những thành phần vận hành hoặc phục hồi nào còn cần đến nó?

Tên hiển thị chỉ là một thuộc tính. Một tài khoản đã đổi tên vẫn có thể là tài khoản tích hợp, còn một tài khoản tự tạo mang tên “admin” chưa chắc là tài khoản tích hợp.

### 2.2. Không đồng nhất các khái niệm gần nhau

| Khái niệm | Ý nghĩa | Điểm cần phân biệt |
| --- | --- | --- |
| Tài khoản quản trị tích hợp | Được nền tảng định nghĩa sẵn cho quản trị | Có thể có hành vi đặc biệt và giới hạn quản lý riêng |
| Tài khoản quản trị tự tạo | Được tổ chức hoặc người triển khai tạo và cấp quyền | Quyền thường được gán qua vai trò, nhóm hoặc chính sách |
| Tài khoản quản trị mặc định | Tài khoản được dùng ban đầu theo quy trình của sản phẩm | Có thể là tài khoản tích hợp hoặc tài khoản được tạo khi khởi tạo |
| Credential mặc định | Giá trị hoặc cách xác thực ban đầu do quá trình triển khai cung cấp | Là phương tiện xác thực, không phải bản thân tài khoản |
| Tài khoản dịch vụ | Danh tính dùng để chạy ứng dụng hoặc tác vụ | Không nên tự động dùng tài khoản quản trị tích hợp cho mục đích này |
| Tài khoản khẩn cấp | Danh tính được chuẩn bị cho tình huống phục hồi | Chỉ là vai trò sử dụng của tài khoản nếu có thiết kế và quy trình tương ứng |

Tài khoản tích hợp không nhất thiết có một mật khẩu mặc định chung, và không phải tài khoản mặc định nào cũng có quyền quản trị cao. Phải xác minh trạng thái thực tế thay vì suy luận từ nhãn.

### 2.3. Đăng nhập và sự tồn tại của danh tính là hai việc khác nhau

Một nền tảng có thể vẫn cần danh tính đặc quyền cho hoạt động nội bộ, ngay cả khi không cho phép con người đăng nhập trực tiếp bằng danh tính đó. Chẳng hạn, việc hạn chế đăng nhập trực tiếp với root không đồng nghĩa mọi tiến trình chạy với quyền root đều ngừng tồn tại.

Do đó, khi nói “vô hiệu hóa tài khoản”, cần chỉ rõ đang thay đổi điều gì: trạng thái tài khoản, xác thực bằng mật khẩu, đăng nhập từ xa, truy cập console hay một phương thức cụ thể khác. Những thay đổi này không nhất thiết tương đương nhau.

## 3. Phạm vi quyền phải gắn với miền quản trị

Hai tài khoản có cùng tên nhưng thuộc hai hệ thống khác nhau có thể là hai chủ thể hoàn toàn riêng biệt. Ví dụ, tài khoản quản trị cục bộ trên máy A và tài khoản cùng tên trên máy B không tự trở thành một danh tính chỉ vì tên giống nhau.

Tương tự, tài khoản quản trị cục bộ, tài khoản quản trị của miền danh tính và tài khoản quản trị của một ứng dụng cần được phân biệt theo nơi chúng tồn tại và được phân quyền.

Một bản ghi nhận diện nên gắn ít nhất:

> Tài nguyên hoặc miền quản trị → định danh tài khoản → tên hiện tại → loại tài khoản → phạm vi quyền.

Cụm từ “toàn quyền” cũng cần được hiểu trong phạm vi. Tài khoản có thể có quyền rất cao đối với một máy chủ hoặc một ứng dụng, nhưng vẫn chịu các ranh giới, cơ chế bảo vệ hoặc giới hạn do nền tảng bên dưới áp dụng. Không nên suy ra quyền vô hạn trên toàn bộ hạ tầng từ quyền quản trị một đích.

Ngược lại, một tài khoản cục bộ có quyền mạnh có thể ảnh hưởng đến credential, dữ liệu và cấu hình nằm trên máy đó. Nếu các tài nguyên ấy mở đường sang hệ thống khác, phạm vi tác động có thể rộng hơn đích ban đầu. Cần xác định đường tác động cụ thể và các điều kiện cần có.

## 4. Vì sao nhóm tài khoản này quan trọng với PAM?

### 4.1. Có thể nằm ngoài quản lý danh tính tập trung

Một tổ chức có thể thu hồi tài khoản nhân viên ở hệ thống danh tính trung tâm nhưng chưa xử lý credential quản trị cục bộ mà người đó từng biết. Nếu mật khẩu hoặc khóa vẫn hợp lệ, việc nghỉ việc hay đổi nhiệm vụ chưa chắc đã kết thúc khả năng truy cập.

Do đó, quản lý vòng đời con người cần liên kết với các credential đặc quyền dùng chung và hệ thống đích ngoài miền tập trung.

### 4.2. Dễ mất khả năng quy trách nhiệm

Nếu nhiều người đăng nhập bằng cùng tài khoản tích hợp, log ở đích có thể chỉ ghi tên tài khoản đó. Khi xảy ra thay đổi hoặc sự cố, sẽ khó xác định ai thực hiện nếu không có chuỗi liên kết bổ sung.

PAM có thể giúp nối danh tính cá nhân, yêu cầu, lần cấp credential hoặc phiên được mở với tài khoản tại đích. Tuy nhiên, nếu người dùng vẫn có thể lấy credential và đi đường khác không được ghi nhận, chuỗi quy trách nhiệm có thể bị đứt.

### 4.3. Credential dùng lại làm tăng phạm vi ảnh hưởng

Dùng cùng một mật khẩu hoặc cùng một khóa quản trị trên nhiều máy có thể khiến việc lộ một giá trị ảnh hưởng đến nhiều đích. Việc clone máy hoặc triển khai từ một mẫu cũng có thể vô tình nhân bản credential nếu quy trình khởi tạo không xử lý điều này.

Mục tiêu là quản lý credential riêng theo phạm vi phù hợp và có khả năng thay tại từng đích. Việc một bí mật được cất trong vault không giải quyết được tình trạng dùng lại nếu tất cả các đích vẫn chấp nhận cùng bí mật đó.

### 4.4. Có thể là đường phục hồi quan trọng

Khi hệ thống danh tính hoặc cổng PAM gặp lỗi, tài khoản tích hợp có thể là một phần của đường phục hồi được nền tảng hỗ trợ. Điều này không biến nó thành tài khoản được phép sử dụng tùy ý.

Nếu dùng cho khẩn cấp, cần xác định trước điều kiện sử dụng, người quyết định, cách nhận phương tiện xác thực, đường truy cập và xử lý sau sử dụng. Cũng phải kiểm tra vòng phụ thuộc: credential phục hồi chỉ nằm trong vault đang hỏng sẽ không giúp được tình huống đó.

## 5. Kiểm kê trước khi thay đổi

### 5.1. Những thông tin cần có

| Nhóm thông tin | Nội dung cần xác định |
| --- | --- |
| Tài nguyên | Máy chủ, thiết bị, ứng dụng hoặc miền mà tài khoản thuộc về |
| Định danh | Định danh nội bộ nếu có, tên hiện tại, dấu hiệu xác nhận là tài khoản tích hợp |
| Quyền | Quyền đặc biệt, nhóm, vai trò và ràng buộc có hiệu lực |
| Trạng thái | Được phép sử dụng hay không, trạng thái khóa và các phương thức còn được chấp nhận |
| Đường truy cập | Console, đăng nhập từ xa, API, broker hoặc cơ chế khác |
| Credential | Loại phương tiện xác thực và tham chiếu nơi quản lý; không lưu giá trị bí mật |
| Chủ sở hữu | Người chịu trách nhiệm về tài nguyên, tài khoản và vòng đời credential |
| Người sử dụng | Nhóm người hoặc workload đang có khả năng dùng tài khoản |
| Phụ thuộc | Dịch vụ, tác vụ định kỳ, backup, tích hợp hoặc quy trình phục hồi liên quan |
| Bằng chứng | Nguồn log, dữ liệu phiên và cách nối với danh tính cá nhân |
| Kết thúc truy cập | Cách thu hồi quyền sử dụng, phiên, token và phương tiện xác thực |

Tài khoản có thể chấp nhận nhiều phương thức xác thực. Thay mật khẩu chưa chắc xử lý khóa hoặc phương tiện khác vẫn được phép. Tắt đăng nhập từ xa theo một giao thức cũng chưa chắc chặn được console hoặc đường truy cập khác.

### 5.2. Xác nhận phụ thuộc vận hành

Trước khi đổi credential hoặc hạn chế đăng nhập, cần xác định ứng dụng và tác vụ nào đang dùng tài khoản. Có thể tồn tại việc dùng sai mục đích từ trước, như một dịch vụ nghiệp vụ chạy bằng tài khoản quản trị tích hợp.

Phát hiện phụ thuộc không có nghĩa phải duy trì nó vô thời hạn. Cần có kế hoạch chuyển sang danh tính dịch vụ riêng với quyền cần thiết, đồng thời xác nhận công việc vẫn vận hành sau chuyển đổi.

Không có sự kiện đăng nhập gần đây chưa chứng minh tài khoản không cần thiết. Nó có thể chỉ được dùng trong một tác vụ ít chạy hoặc quy trình phục hồi chưa xảy ra. Cần đối chiếu dữ liệu sử dụng với chủ sở hữu và thiết kế vận hành.

## 6. Chọn trạng thái và mục đích sử dụng

Không có một hành động duy nhất phù hợp cho mọi tài khoản tích hợp. Quyết định phải dựa vào khả năng nền tảng, nhu cầu và đường phục hồi.

| Tình huống | Hướng xử lý cần xem xét | Điều cần xác nhận |
| --- | --- | --- |
| Không cần đăng nhập trực tiếp và nền tảng cho phép hạn chế | Chặn hoặc vô hiệu hóa cách đăng nhập tương ứng | Không làm hỏng vận hành nội bộ và còn đường quản trị hợp lệ |
| Cần cho cài đặt hoặc khởi tạo | Chỉ dùng trong phạm vi triển khai đã xác định | Kết thúc giai đoạn khởi tạo, xử lý credential và chuyển sang quản trị thường lệ |
| Cần cho phục hồi khẩn cấp | Duy trì đường phục hồi được quản lý riêng | Độc lập với kiểu sự cố dự kiến, có bằng chứng và kiểm tra định kỳ |
| Còn được dùng cho vận hành thường xuyên | Chuyển dần sang tài khoản cá nhân và ủy quyền hẹp khi có thể | Công việc hoàn thành mà không cần chia sẻ quyền quản trị rộng |
| Sản phẩm buộc phải duy trì một số khả năng của tài khoản | Ghi nhận giới hạn và bổ sung kiểm soát đường truy cập, credential, giám sát | Quyền và các ngoại lệ được hiểu rõ, có chủ sở hữu |

Không nên xóa hoặc sửa tùy tiện một tài khoản nền tảng khi chưa xác định sản phẩm có hỗ trợ và hậu quả ra sao. Một số đặc tính của tài khoản tích hợp không thể thay đổi như tài khoản thông thường.

Đổi tên có thể giúp phù hợp quy ước quản lý trong nền tảng cho phép, nhưng không phải biện pháp xác thực hay giảm quyền. Nếu định danh nội bộ và quyền vẫn giữ nguyên, khả năng truy cập vẫn cần được kiểm soát bằng các lớp khác.

## 7. Giảm sử dụng trực tiếp bằng least privilege và JIT/JEA

### 7.1. Ưu tiên danh tính cá nhân và ủy quyền theo nhiệm vụ

Đối với công việc thường lệ, nên xem xét cho người quản trị dùng danh tính cá nhân, rồi nhận quyền thực hiện đúng chức năng cần thiết. Ví dụ, nhu cầu khởi động lại một dịch vụ không tự đòi hỏi khả năng đăng nhập bằng tài khoản quản trị tích hợp và sửa mọi cấu hình.

Lợi ích gồm khả năng quy trách nhiệm rõ hơn và giảm việc chia sẻ credential mạnh. Tuy nhiên, cần kiểm tra quyền được ủy quyền, tham số và những đường truy cập khác để tránh tạo ra một giao diện hẹp nhưng vẫn có khả năng thực thi tùy ý phía sau.

### 7.2. Hiểu JIT đang giới hạn lớp nào

Với tài khoản tích hợp có đặc quyền nội tại, JIT có thể giới hạn thời điểm người dùng được phép mở phiên, nhận credential hoặc đi qua broker. Điều này không nhất thiết làm bản thân tài khoản chỉ có quyền thấp khi hết cửa sổ sử dụng.

Ví dụ, một kỹ sư được mở phiên quản trị trên máy A trong 20 phút. Đây là giới hạn sử dụng tài khoản qua cơ chế được cho phép. Nếu credential vẫn có thể dùng trực tiếp từ bên ngoài cơ chế đó, thời hạn trên cổng chưa bảo đảm truy cập tại đích đã kết thúc.

Vì vậy, cần xác định quyền nào được kích hoạt, đường nào được mở và cơ chế nào thực thi thời hạn. JEA bổ sung giới hạn hành động và tài nguyên; cửa sổ ngắn không thay thế được giới hạn khả năng thực hiện.

### 7.3. Kết thúc quyền sử dụng khác kết thúc phiên

Khi yêu cầu hết hạn, hệ thống có thể ngừng mở phiên mới hoặc ngừng cấp credential. Phiên, token hoặc kết nối đã tạo có thể cần xử lý riêng theo cơ chế của hệ thống đích.

Đổi mật khẩu cũng không bảo đảm mọi phiên đã xác thực bị chấm dứt. Cần có cách xác nhận kết quả và ghi rõ những giới hạn còn tồn tại thay vì kết luận thành công chỉ từ trạng thái hiển thị.

## 8. Quản lý credential bằng vault và luân chuyển

### 8.1. Đưa vào quản lý phải phản ánh đúng trạng thái tại đích

Một tài khoản được ghi trong vault chưa chắc đã được quản lý đầy đủ. Cần xác nhận định danh đích chính xác, credential hiện hành hợp lệ, chính sách truy xuất đúng và khả năng đổi credential thực sự hoạt động.

Nếu có thể, cơ chế broker có thể sử dụng credential thay người dùng để giảm việc tiết lộ bí mật. Dù có hay không có cơ chế này, người khởi tạo vẫn cần được xác thực và liên kết với hoạt động tại đích.

### 8.2. Vòng luân chuyển có kiểm tra

Một quy trình luân chuyển ở mức khái niệm gồm:

1. Xác định đúng tài khoản, đích, phương thức xác thực và các phụ thuộc.
2. Chuẩn bị giá trị mới hoặc phương tiện mới theo cơ chế hỗ trợ.
3. Áp dụng thay đổi tại đích và cập nhật trạng thái quản lý tương ứng.
4. Xác nhận phương tiện mới hoạt động và xử lý phương tiện cũ theo chính sách.
5. Kiểm tra các dịch vụ hoặc tác vụ có phụ thuộc.
6. Lưu kết quả, phần lỗi và người chịu trách nhiệm xử lý tiếp.

Thứ tự chi tiết và khả năng phối hợp nhiều phương tiện phụ thuộc vào nền tảng. Điều quan trọng là không coi “đã gửi yêu cầu đổi” là “đã xác nhận trạng thái nhất quán”.

Nếu thay ở đích thành công nhưng cập nhật vault thất bại, có thể mất khả năng lấy credential đúng. Nếu chỉ cập nhật vault mà đích chưa thay, phương tiện mới không dùng được trong khi phương tiện cũ có thể vẫn còn hiệu lực.

Cần có quy trình đối chiếu và khôi phục trạng thái quản lý khi xảy ra lỗi. Khi bí mật cũ đã bị lộ, không nên mặc định khôi phục bằng cách đưa nó trở lại sử dụng; phải chọn phương án phù hợp với tình trạng sự cố.

### 8.3. Tránh xung đột sử dụng đồng thời

Nếu nhiều người hoặc tác vụ dùng cùng tài khoản, luân chuyển sau một lần sử dụng có thể ảnh hưởng lần khác. Ngược lại, trì hoãn vô hạn vì luôn có tác vụ đang chạy làm mất mục tiêu kiểm soát credential.

Cần nhận diện các lần sử dụng đang hoạt động, phương thức xác thực và chính sách phiên. Về lâu dài, nên tách tác vụ dịch vụ khỏi tài khoản quản trị dùng chung và giảm số người cần nhận bí mật trực tiếp.

### 8.4. Xử lý credential trong mẫu triển khai

Credential không nên được đưa vào mẫu máy, mã triển khai hoặc đầu ra tác vụ theo cách khiến nhiều đích có chung bí mật. Mỗi tài nguyên mới cần trải qua bước khởi tạo phương tiện xác thực và đưa vào quản lý phù hợp.

Khi tái tạo hoặc thay tài nguyên, cần đối chiếu lại định danh. Tên máy có thể được dùng lại, nhưng tài nguyên mới không nhất thiết là cùng đối tượng quản lý cũ. Nếu chỉ bám vào tên, vault hoặc hệ thống kiểm kê có thể gắn sai credential.

## 9. Ví dụ: đưa tài khoản quản trị cục bộ vào PAM

### 9.1. Bối cảnh

Một nhóm vận hành quản lý 12 máy chủ. Trên mỗi máy có một tài khoản quản trị tích hợp cục bộ, nhưng nhóm đang dùng cùng một mật khẩu. Mọi người biết mật khẩu và truy cập trực tiếp. Một tác vụ bảo trì trên hai máy cũng dùng tài khoản này.

Có ba vấn đề khác nhau:

- Credential dùng lại làm tăng số tài nguyên có thể bị ảnh hưởng nếu lộ một bí mật.
- Tài khoản dùng chung làm yếu khả năng quy trách nhiệm.
- Tác vụ phụ thuộc có thể bị hỏng nếu đổi credential hoặc hạn chế đăng nhập mà chưa chuyển đổi.

### 9.2. Thiết kế chuyển đổi

| Giai đoạn | Việc cần thực hiện | Bằng chứng kết quả |
| --- | --- | --- |
| Kiểm kê | Xác nhận từng đích, định danh tài khoản và phương thức xác thực | Danh mục tài khoản theo từng máy |
| Phân tích phụ thuộc | Xác định người và tác vụ đang dùng | Chủ sở hữu, nhu cầu và kế hoạch chuyển đổi |
| Chuẩn bị quản trị thường lệ | Dùng danh tính cá nhân, quyền theo nhiệm vụ và đường truy cập được kiểm soát | Công việc hợp lệ thực hiện được trong phạm vi |
| Tách tác vụ | Chuyển bảo trì sang danh tính dịch vụ phù hợp | Tác vụ hoạt động và không còn cần credential quản trị tích hợp |
| Quản lý credential | Áp dụng phương tiện riêng cho từng đích và đưa vào quản lý | Xác nhận trạng thái tại vault và đích |
| Hạn chế đường cũ | Chặn những cách truy cập không còn cần theo khả năng nền tảng | Kiểm tra đường được phép và đường bị chặn |
| Giám sát, phục hồi | Theo dõi sử dụng và kiểm tra đường phục hồi đã chọn | Cảnh báo, bằng chứng phiên, kết quả kiểm tra phục hồi |

Con số 12 chỉ mô tả tình huống, không tạo thành một quy mô chuẩn. Phương án chuyển đổi cần chia bước phù hợp với mức độ quan trọng và khả năng kiểm tra của môi trường.

### 9.3. Chính sách sử dụng ở mức khái niệm

Mã giả sau minh họa điều kiện mở một phiên, không phải cấu hình triển khai của một sản phẩm:

```text
Yêu cầu truy cập:
  người_khởi_tạo = danh_tính_cá_nhân
  đích = máy_chủ_được_duyệt
  tài_khoản = định_danh_tích_hợp_trên_chính_đích_đó
  mục_đích = công_việc_được_ghi_nhận
  thời_hạn = giới_hạn_được_chấp_nhận

Trước khi mở phiên:
  kiểm_tra quyền_yêu_cầu, đích, mục_đích và điều_kiện
  từ_chối nếu không_còn_hợp_lệ hoặc ngoài_phạm_vi
  mở phiên bằng cơ_chế quản_lý_credential phù_hợp
  ghi mã_yêu_cầu, người_khởi_tạo, tài_khoản_đích và mã_phiên

Khi kết thúc:
  ngừng cho_phép truy_cập_mới theo yêu_cầu
  xử_lý phiên_và_phương_tiện liên_quan theo cơ_chế_tại_đích
  luân_chuyển nếu chính_sách yêu_cầu
  đối_chiếu trạng_thái và ghi lỗi_còn_tồn_tại
```

Nếu người dùng đã từng biết mật khẩu cũ, chỉ yêu cầu họ chuyển sang broker mà vẫn để mật khẩu đó hợp lệ sẽ chưa kết thúc đường truy cập cũ. Cần xử lý credential và cách truy cập thực tế theo kế hoạch chuyển đổi.

## 10. Giám sát và bằng chứng

### 10.1. Những sự kiện cần quan sát

Các sự kiện có ích gồm truy xuất credential, mở phiên, đăng nhập trực tiếp, thay phương thức xác thực, thay trạng thái tài khoản, thay quyền và thay đổi cấu hình nhạy cảm tại đích.

Có thể cần cảnh báo khi tài khoản tích hợp được dùng ngoài quy trình cho phép, từ nguồn không dự kiến hoặc trong tình huống lẽ ra không còn cho phép đăng nhập. Những tín hiệu này cần được đối chiếu với thay đổi được duyệt và ngữ cảnh vận hành; một lần xác thực lỗi riêng lẻ chưa đủ kết luận có xâm nhập.

### 10.2. Chuỗi quy trách nhiệm

| Lớp | Bằng chứng cần nối |
| --- | --- |
| Danh tính cá nhân | Ai yêu cầu và xác thực với hệ thống quản lý |
| Quyết định | Mục đích, đích, tài khoản và thời hạn được cho phép |
| Truy cập | Ai nhận credential hoặc được mở phiên; thời điểm và cơ chế |
| Hoạt động tại đích | Tài khoản, nguồn, phiên, hành động và kết quả |
| Kết thúc | Kết quả chấm dứt truy cập, luân chuyển và lỗi cần xử lý |

Ghi hình phiên tương tác có thể hỗ trợ điều tra nhưng không bao phủ mọi đường như console, API hay tác vụ tự động. Cần kết hợp dữ liệu phiên với log phù hợp tại đích và log của cơ chế cấp quyền.

Không đưa credential vào ticket, bản chụp, log lệnh hoặc bản ghi chẩn đoán. Bằng chứng nên chứa định danh và kết quả xử lý, không chứa giá trị bí mật. Những cấu hình hoặc đầu ra nhạy cảm cũng cần được quản lý theo phạm vi truy cập phù hợp.

Người có quyền quản trị cao có thể có khả năng tác động đến log tại đích. Cần đánh giá nguồn bằng chứng bổ sung, quyền quản lý nơi lưu và giới hạn còn tồn tại, thay vì mặc định mọi log đều chống sửa được.

## 11. Khi credential bị nghi lộ

Kế hoạch ứng phó cần xem cả phương tiện xác thực, quyền của tài khoản và hoạt động đã xảy ra.

Những việc cần đưa vào xử lý gồm:

1. Xác định tài khoản và tài nguyên thực tế bị ảnh hưởng, bao gồm nơi dùng lại cùng credential.
2. Giữ bằng chứng từ các nguồn phù hợp để đánh giá thời điểm và phạm vi sử dụng.
3. Thu hồi hoặc thay phương tiện xác thực bị ảnh hưởng bằng một đường quản trị đủ tin cậy.
4. Xử lý phiên, token, khóa hoặc phương thức khác có thể còn cho phép truy cập.
5. Rà soát tài khoản, quyền, tác vụ và cấu hình đã được tạo hoặc thay đổi để duy trì truy cập.
6. Khôi phục trạng thái quản lý nhất quán và xác nhận khả năng vận hành, phục hồi.

Nếu nhiều đích dùng chung bí mật, không nên coi việc đổi trên một máy là đã xử lý xong toàn bộ phạm vi. Đồng thời, cần kiểm tra phụ thuộc để thay đổi có kiểm soát mà không để quyền nguy hiểm tiếp tục tồn tại ngoài dự kiến.

Không xóa tùy tiện danh tính nền tảng hoặc loại bỏ đường phục hồi cuối cùng để xử lý một credential bị lộ. Mục tiêu là chấm dứt khả năng truy cập không được phép, xử lý hậu quả và khôi phục quyền kiểm soát theo cơ chế phù hợp của nền tảng.

## 12. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu cần dùng |
| --- | --- |
| Tài khoản tên admin chắc chắn là tích hợp | Xác nhận theo nền tảng và định danh thực tế |
| Đổi tên đã làm tài khoản an toàn | Tên không thay thế xác thực, giới hạn quyền và giám sát |
| Vô hiệu hóa mật khẩu đã chặn mọi truy cập | Kiểm tra các phương thức xác thực và đường truy cập khác |
| Tắt đăng nhập trực tiếp đồng nghĩa xóa danh tính khỏi hoạt động hệ thống | Phân biệt truy cập của người dùng và nhu cầu nội bộ của nền tảng |
| Cùng tên ở nhiều máy nghĩa là cùng một tài khoản | Gắn định danh với đúng tài nguyên và miền quản trị |
| Đưa credential vào vault là đã giải quyết quyền quá rộng | Quản lý phương tiện xác thực và giới hạn quyền là các lớp liên quan nhưng riêng biệt |
| Cấp tài khoản tích hợp trong ít phút là đã có JEA | Giới hạn thời gian không tự giới hạn hành động |
| Đổi mật khẩu sẽ đóng mọi phiên | Kiểm tra cơ chế phiên và xử lý liên quan tại đích |
| Không thấy đăng nhập nên có thể vô hiệu hóa ngay | Đối chiếu phụ thuộc, tác vụ ít chạy và nhu cầu phục hồi |
| Tài khoản tích hợp tự nhiên là tài khoản break-glass | Cần mục đích, điều kiện, bảo quản, kiểm tra và bằng chứng riêng |

## 13. Bài tập vận dụng

Một thiết bị có tài khoản quản trị tích hợp. Nhóm đã đổi tên tài khoản và cất mật khẩu trong vault, nhưng vẫn dùng cùng mật khẩu cho các thiết bị khác. Một số người giữ bản sao riêng. Truy cập qua PAM hết hạn sau 30 phút, còn đăng nhập trực tiếp vẫn được phép. Chưa ai xác định liệu tác vụ sao lưu có dùng tài khoản này hay không.

Hãy phân tích:

1. Những việc đã làm tác động đến tên, credential, quyền và đường truy cập ở lớp nào?
2. Vì sao cơ chế hiện tại chưa đủ bảo đảm truy cập kết thúc sau 30 phút?
3. Cần xác minh điều gì trước khi luân chuyển hoặc hạn chế đăng nhập?
4. Làm thế nào giảm phạm vi ảnh hưởng của một credential bị lộ?
5. Bằng chứng nào cần có để xác định người thực hiện một thay đổi trên thiết bị?

**Định hướng trả lời:** đổi tên không thay quyền; vault không xử lý được việc dùng lại và bản sao còn hợp lệ; thời hạn tại PAM không chặn đường trực tiếp ngoài PAM. Cần kiểm kê phụ thuộc, quản lý credential riêng theo đích, xử lý phương tiện cũ và kiểm tra cơ chế phiên. Chuỗi bằng chứng phải nối người khởi tạo, yêu cầu, tài khoản tại đích, hành động và kết thúc sử dụng.

## 14. Ghi nhớ

Built-in administrator account cần được quản lý theo định danh, phạm vi quyền và hành vi thực tế của nền tảng. Tài khoản có thể tiếp tục tồn tại vì nhu cầu nội bộ hoặc phục hồi, trong khi việc đăng nhập trực tiếp được hạn chế theo thiết kế.

PAM hiệu quả với nhóm tài khoản này cần giảm sử dụng dùng chung, quản lý credential theo từng phạm vi phù hợp, kiểm soát đường truy cập và xác nhận kết thúc bằng cơ chế tại đích. Mọi quyết định đổi credential, vô hiệu hóa hay giữ lại đều phải dựa trên kiểm kê quyền, phụ thuộc và khả năng phục hồi có thể kiểm chứng.