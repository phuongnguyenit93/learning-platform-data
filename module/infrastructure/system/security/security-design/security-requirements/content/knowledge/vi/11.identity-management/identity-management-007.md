# Machine identity

## 1. Danh tính máy trong quản trị identity

Machine identity là danh tính của một thực thể không phải con người dùng để tương tác với hệ thống: dịch vụ, workload, tiến trình tự động, pipeline triển khai, thiết bị hoặc ứng dụng tích hợp. Hệ thống dựa vào danh tính đó để xác định bên đang yêu cầu truy cập, áp dụng quyền và quy trách nhiệm cho hành động.

Ví dụ, dịch vụ xử lý thanh toán gọi dịch vụ hóa đơn; một job định kỳ đọc dữ liệu để lập báo cáo; pipeline phát hành cập nhật ứng dụng lên môi trường production. Những thực thể này cần danh tính riêng, thay vì dùng tài khoản của lập trình viên hoặc cùng chia sẻ một tài khoản quản trị.

Trong thiết kế yêu cầu bảo mật, câu hỏi quan trọng không dừng ở “dùng certificate hay token?”. Cần xác định:

- Thực thể nào được cấp danh tính và bằng chứng nào cho phép cấp?
- Danh tính đó được làm gì, ở môi trường nào và với dữ liệu nào?
- Ai chịu trách nhiệm duy trì, rà soát và thu hồi?
- Khi credential bị lộ, hệ thống chặn truy cập trong bao lâu?
- Bằng chứng nào cho thấy các yêu cầu trên được thực thi?

Mục tiêu là chuyển rủi ro giả mạo, lạm dụng quyền và mất kiểm soát vòng đời thành yêu cầu cụ thể, đo được và kiểm chứng được.

## 2. Phân biệt identity, principal, credential và quyền

Các khái niệm này liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Identity | Danh tính logic của thực thể | Dịch vụ đối soát thanh toán ở production |
| Principal | Biểu diễn danh tính mà hệ thống xác thực và áp chính sách | Subject được ánh xạ vào principal nội bộ |
| Credential | Bằng chứng thực thể xuất trình để xác thực | Khóa riêng kèm certificate, token, API key |
| Permission | Hành động được phép trên tài nguyên trong điều kiện xác định | Đọc các hóa đơn thuộc phạm vi đối soát |
| Owner | Nhóm hoặc cá nhân chịu trách nhiệm quản trị danh tính | Nhóm phụ trách nền tảng thanh toán |

Một service account thường là principal được hệ thống lưu trữ; credential là thứ dùng để chứng minh quyền sử dụng principal đó. Thay khóa không nhất thiết tạo một identity mới. Ngược lại, giữ nguyên một khóa nhưng dùng nó cho hai workload độc lập làm mất khả năng phân biệt bên thực sự thực hiện hành động.

Certificate chứa thông tin về khóa công khai và danh tính theo cơ chế chứng nhận; khả năng xác thực còn phụ thuộc vào việc kiểm tra chuỗi tin cậy, thời hạn, mục đích sử dụng và bằng chứng sở hữu khóa riêng. Token chỉ có giá trị khi bên nhận xác minh nó theo đúng giao thức và chính sách. Một chuỗi trông giống JWT không tự trở thành danh tính đáng tin cậy.

Tên dịch vụ trong HTTP header, địa chỉ IP, nhãn pod hoặc tên máy có thể hỗ trợ định tuyến và quan sát. Chúng không tự chứng minh nguồn gốc nếu bên gọi có thể tự khai báo hoặc giả mạo.

### Danh tính logic và instance

Một dịch vụ có thể có nhiều instance cùng chạy với một danh tính logic để áp cùng chính sách. Điều này không đồng nghĩa các instance phải chia sẻ một khóa riêng dài hạn.

Có thể thiết kế:

- Danh tính logic để quyết định quyền ở mức dịch vụ.
- Credential riêng cho từng instance hoặc phiên chạy để giới hạn phạm vi lộ lọt.
- Mã instance, deployment hoặc job run để điều tra hành động cụ thể.

Mức tách biệt phải dựa vào rủi ro. Hai workload có cùng owner nhưng khác môi trường hoặc mức quyền vẫn có thể cần hai danh tính riêng.

## 3. Những loại machine identity cần đưa vào phạm vi

| Loại thực thể | Tình huống | Rủi ro cần phản ánh trong yêu cầu |
| --- | --- | --- |
| Dịch vụ và workload | API gọi API, worker xử lý hàng đợi | Giả mạo dịch vụ, di chuyển ngang, quyền quá rộng |
| Job và tiến trình định kỳ | Xuất báo cáo, đồng bộ dữ liệu | Tài khoản tồn tại sau khi job ngừng hoạt động |
| Pipeline CI/CD | Build, ký và triển khai artifact | Mã từ nhánh không tin cậy lấy credential production |
| Thiết bị | Gateway, thiết bị chuyên dụng | Sao chép khóa, mất thiết bị, kết nối gián đoạn |
| Ứng dụng tích hợp | Đối tác gọi API | Credential dùng chung giữa đối tác, tenant hoặc môi trường |
| Tác vụ quản trị tự động | Backup, bảo trì, phục hồi | Quyền đặc biệt không bị giới hạn thời gian hoặc phạm vi |

Không nên gom tất cả thành một tài khoản “automation”. Mỗi nhóm có cách bootstrap, giới hạn tin cậy và điều kiện vận hành khác nhau.

Machine identity cũng có thể là bên thực thi thay cho người dùng. Khi đó cần phân biệt danh tính workload và chủ thể người dùng được ủy quyền; việc xác thực workload không tự cho phép nó thao tác mọi dữ liệu người dùng.

## 4. Từ mô hình đe dọa đến yêu cầu

Giả sử một hệ thống có luồng xử lý:

~~~text
Pipeline phát hành -> Triển khai workload đối soát
Workload đối soát -> Dịch vụ hóa đơn -> Kho dữ liệu
~~~

Tài sản cần bảo vệ gồm dữ liệu hóa đơn, quyền triển khai, credential và bằng chứng audit. Các ranh giới tin cậy nằm giữa pipeline với môi trường chạy, workload với nhà cấp credential, và workload với dịch vụ nhận yêu cầu.

| Đe dọa | Hậu quả | Hướng yêu cầu |
| --- | --- | --- |
| Credential được commit vào repository | Người đọc repository giả mạo workload | Không nhúng credential tĩnh; phát hiện và xử lý credential bị lộ |
| Workload tự khai tên dịch vụ để xin token | Cấp quyền cho thực thể giả mạo | Cấp danh tính dựa trên bằng chứng nguồn chạy đã xác minh |
| Token của staging dùng được ở production | Vượt ranh giới môi trường | Tách chính sách cấp và chấp nhận theo môi trường |
| Token dành cho API khác được chấp nhận | Sử dụng sai đối tượng nhận | Xác minh audience hoặc ràng buộc đối tượng nhận tương ứng |
| Dùng chung tài khoản cho nhiều workload | Không xác định được nguồn hành động | Tách principal theo ranh giới quản trị và rủi ro |
| Thu hồi tài khoản nhưng token cũ còn hiệu lực | Tiếp tục truy cập sau sự cố | Đặc tả riêng việc ngừng cấp mới và chặn credential đã cấp |
| Pipeline không tin cậy nhận quyền triển khai | Chiếm quyền production | Ràng buộc federation với repository, workflow và ngữ cảnh phát hành được phép |

Bảng này là điểm bắt đầu. Một yêu cầu hoàn chỉnh còn cần đối tượng áp dụng, điều kiện, hành vi bắt buộc, ngưỡng thời gian, cách kiểm chứng và owner.

## 5. Vòng đời của machine identity

### 5.1. Đăng ký và xác định owner

Trước khi cấp quyền, phải biết thực thể là gì, phục vụ mục đích nào và ai chịu trách nhiệm. Bản ghi inventory nên có:

- ID ổn định; loại thực thể và hệ thống phát hành danh tính.
- Owner vận hành, owner phê duyệt quyền và kênh liên hệ sự cố.
- Môi trường, phạm vi tenant nếu có, tài nguyên được truy cập.
- Cơ chế cấp credential và nơi lưu khóa riêng hoặc secret.
- Quyền được cấp, lý do nghiệp vụ, ngày rà soát tiếp theo.
- Trạng thái hoạt động, ngoại lệ được phê duyệt và hạn ngoại lệ.

Tên hiển thị có thể thay đổi; liên kết audit không nên chỉ dựa vào tên đó. Khi chuyển owner, hệ thống phải cập nhật trách nhiệm và rà soát quyền, không mặc định coi danh tính đã được phê duyệt vĩnh viễn.

### 5.2. Bootstrap: ai được xin danh tính?

Bootstrap là bước thiết lập tin cậy ban đầu. Nếu ai cũng có thể xin credential cho tên “payment-service”, các bước xác thực phía sau không giải quyết được giả mạo.

Nguồn bằng chứng có thể gồm danh tính nền tảng chạy, assertion do nhà cung cấp tin cậy ký, quy trình đăng ký thiết bị hoặc bằng chứng phần cứng. Yêu cầu phải xác định bằng chứng nào được chấp nhận và nó được ánh xạ vào principal nào.

Ví dụ:

> Nhà cấp credential chỉ cấp danh tính workload production khi bằng chứng nguồn chạy hợp lệ và các thuộc tính đã xác minh khớp chính sách đăng ký của workload; yêu cầu tự khai cùng tên nhưng không có bằng chứng hợp lệ phải bị từ chối.

Nhãn workload chỉ đáng tin đến mức cơ chế bảo vệ nhãn đó. Nếu bất kỳ lập trình viên nào cũng có thể gắn nhãn production hoặc chạy dưới một service account đặc quyền, cần bổ sung yêu cầu kiểm soát quyền triển khai và quyền gán danh tính.

Attestation có thể tăng độ tin cậy về nguồn chạy hoặc trạng thái được kiểm tra. Nó không chứng minh workload sẽ luôn hành xử an toàn, cũng không thay thế phân quyền.

### 5.3. Cấp credential

Credential nên được cấp cho đúng đối tượng, có thời hạn và phạm vi phù hợp với tác vụ. Với workload ngắn hạn, cơ chế cấp credential động giúp giảm nhu cầu phát tán secret dài hạn.

Cần xác định rõ:

- Nhà cấp nào được tin cậy.
- Điều kiện được nhận credential.
- Thời hạn tối đa và điều kiện gia hạn.
- Credential dành cho tài nguyên hoặc đối tượng nhận nào.
- Có yêu cầu ràng buộc credential với khóa hoặc kênh giao tiếp hay không.
- Hành vi khi nhà cấp không sẵn sàng.

Không nên dùng một credential cấp cao chung cho mọi workload chỉ để thuận tiện gọi nhà cấp credential thứ hai. Bootstrap secret đó có thể trở thành điểm tập trung rủi ro.

### 5.4. Sử dụng và gia hạn

Workload cần nhận credential qua kênh bảo vệ, giữ credential ngoài source code và tránh làm lộ qua log, trace, thông báo lỗi hoặc artifact build.

“Không lưu trên đĩa” có thể là một lựa chọn nhưng không phải lời bảo đảm tuyệt đối: credential trong bộ nhớ vẫn có thể bị đánh cắp khi runtime bị kiểm soát. Yêu cầu cần mô tả mô hình đe dọa và biện pháp tương ứng, như hạn chế truy cập tiến trình, cô lập workload hoặc dùng khóa không xuất được khi phù hợp.

Gia hạn tự động phải có quan sát lỗi, giới hạn retry và hành vi an toàn khi hết hạn. Không kéo dài credential vô hạn khi hệ thống cấp mới gặp sự cố.

### 5.5. Rotation và thu hồi

Rotation thay credential theo kế hoạch hoặc khi có sự cố. Thu hồi làm mất khả năng sử dụng credential hoặc danh tính theo chính sách. Hai việc này cần được đặc tả riêng.

Một cơ chế rotation có thể cần khoảng chồng lấn để duy trì dịch vụ. Khoảng chồng lấn phải có thời điểm kết thúc; credential cũ không được sống vô hạn vì một consumer chưa cập nhật.

Việc vô hiệu hóa principal có thể ngừng cấp token mới nhưng không tự chặn token đã phát hành nếu API chỉ xác minh chữ ký và thời hạn tại chỗ. Tương tự, kết nối đã được xác thực có thể tiếp tục tồn tại sau khi thay certificate nếu không có cơ chế đánh giá lại hoặc đóng kết nối.

Yêu cầu thu hồi cần xác định:

1. Khi nào ngừng cấp hoặc gia hạn credential mới.
2. Credential đã cấp bị từ chối trong bao lâu.
3. Kết nối hoặc phiên đang hoạt động được xử lý thế nào.
4. Cache quyết định và độ lệch đồng hồ ảnh hưởng ra sao.
5. Có cần phát hành lại danh tính hoặc credential sau sự cố hay không.

### 5.6. Ngừng sử dụng

Khi job, dịch vụ hoặc tích hợp bị loại bỏ, cần thu hồi quyền, ngừng phát hành credential và xử lý credential còn hiệu lực theo chính sách. Bằng chứng audit được lưu theo chính sách lưu trữ; không xóa lịch sử chỉ vì identity đã bị vô hiệu hóa.

Tín hiệu “không thấy truy cập” là đầu vào cho rà soát, chưa đủ để kết luận một danh tính chắc chắn không còn dùng. Job chạy theo quý hoặc tài khoản phục hồi cần có quy trình xác nhận riêng.

## 6. Xác thực không thay thế phân quyền

### 6.1. Kiểm tra ở bên nhận

Bên nhận cần xác định credential hợp lệ và ánh xạ về principal đáng tin cậy. Tùy cơ chế, điều này bao gồm kiểm tra chữ ký hoặc chuỗi tin cậy, nhà phát hành, thời hạn, đối tượng nhận, mục đích sử dụng và các ràng buộc được yêu cầu.

Không dùng subject hoặc client ID do bên gọi gửi kèm để thay cho danh tính đã được xác minh. Principal nội bộ nên được ánh xạ từ kết quả xác thực và ngữ cảnh tin cậy.

Trong hệ thống đa tenant, cùng một chuỗi subject từ hai nhà phát hành không mặc nhiên đại diện cùng một thực thể. Không gian định danh phải tránh va chạm, thường cần xét cả miền tin cậy hoặc nhà phát hành.

### 6.2. Quyền nhỏ nhất theo tài nguyên và hành động

Một workload đọc hóa đơn để đối soát không cần quyền sửa tài khoản khách hàng hoặc cấp quyền cho dịch vụ khác.

Quyết định truy cập nên xét các yếu tố cần thiết:

~~~text
Danh tính đã xác thực
+ hành động yêu cầu
+ tài nguyên cụ thể
+ môi trường và tenant
+ ngữ cảnh ủy quyền hợp lệ
-> cho phép hoặc từ chối
~~~

Quyền mặc định nên là từ chối khi không có chính sách cho phép phù hợp. Tuy nhiên, “default deny” chưa đủ nếu policy cho phép quá rộng; phải kiểm tra cả phạm vi của các quyền đã cấp.

Không lấy tenant ID từ request làm bằng chứng workload có quyền trên tenant đó. Dịch vụ cần đối chiếu nó với quyền hoặc ngữ cảnh đã xác minh.

### 6.3. mTLS và ranh giới của nó

mTLS có thể xác thực hai đầu kết nối và bảo vệ dữ liệu truyền khi được cấu hình đúng. Nó không tự quyết định principal được đọc hóa đơn nào, có thể ghi dữ liệu không, hay có quyền thay mặt người dùng nào.

Nếu proxy kết thúc mTLS và chuyển tiếp danh tính đến ứng dụng, đoạn proxy–ứng dụng trở thành một ranh giới tin cậy cần thiết kế. Ứng dụng phải chỉ chấp nhận danh tính chuyển tiếp qua đường đi và cơ chế được bảo vệ; không tin header giống tên đó từ một client tùy ý.

### 6.4. Bearer credential và bằng chứng sở hữu

Bearer token hoặc API key thường có thể được người đang giữ sử dụng nếu không có ràng buộc bổ sung. Thời hạn ngắn giảm cửa sổ khai thác nhưng không ngăn token bị dùng ngay sau khi đánh cắp.

Với tác vụ nhạy cảm, có thể yêu cầu cơ chế chứng minh sở hữu khóa hoặc ràng buộc token với bên gửi, nếu kiến trúc hỗ trợ. Yêu cầu phải chỉ rõ bên nhận kiểm tra ràng buộc đó; chỉ ghi thêm một trường vào token chưa đủ.

Không phải mọi hệ thống đều cần cùng một cơ chế. Chọn kiểm soát dựa trên rủi ro, khả năng vận hành và tiêu chí chấp nhận đã thống nhất.

## 7. Danh tính qua nhiều chặng và quyền đại diện

Giả sử dịch vụ A nhận yêu cầu của người dùng rồi gọi dịch vụ B. Có hai câu hỏi độc lập:

- Workload nào đang gọi B?
- Workload đó có được thực hiện hành động này cho người dùng hoặc tenant đang xét không?

Nếu B chỉ thấy danh tính A với quyền toàn hệ thống, một lỗi ở A có thể trở thành đường truy cập mọi tenant. Đây là lý do cần mô hình ủy quyền rõ ràng, thay vì coi “dịch vụ nội bộ” là đủ tin cậy.

Không chuyển tiếp nguyên token qua mọi chặng nếu token không được cấp cho những đối tượng nhận đó. Có thể dùng cơ chế trao đổi hoặc cấp credential cho chặng tiếp theo với phạm vi hẹp hơn, khi giao thức và kiến trúc hỗ trợ.

Yêu cầu cần quy định việc bảo toàn hoặc ánh xạ thông tin actor, chủ thể được đại diện, phạm vi và mục đích. Audit cần phân biệt workload thực thi với người dùng gốc.

Với hàng đợi và tác vụ bất đồng bộ, credential ban đầu có thể hết hạn trước khi job chạy. Cần xác định:

- Job chạy theo quyền của dịch vụ hay quyền được ủy quyền từ người gửi?
- Quyền có được kiểm tra lại tại thời điểm thực thi không?
- Việc người dùng bị vô hiệu hóa ảnh hưởng thế nào đến job đang chờ?
- Thông tin gắn với job được bảo vệ khỏi sửa đổi và phát lại ra sao?

Không lưu bearer token dài hạn trong payload chỉ để né việc thiết kế quyền thực thi.

## 8. Bộ yêu cầu minh họa có thể kiểm chứng

Các ngưỡng dưới đây là giả định cho một hệ thống đối soát, không phải giá trị bắt buộc cho mọi tổ chức. Owner phải xác nhận chúng theo mức rủi ro và yêu cầu sẵn sàng.

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| MI-01 | Mọi machine identity được cấp quyền production phải có owner còn hiệu lực và mục đích được phê duyệt | Yêu cầu cấp mới thiếu owner hoặc phê duyệt bị từ chối; danh tính mất owner đi vào quy trình xử lý đã định |
| MI-02 | Workload staging không được nhận hoặc sử dụng danh tính production | Dùng bằng chứng staging xin credential production và gọi API production đều bị từ chối |
| MI-03 | Credential của workload đối soát chỉ được cấp sau khi bằng chứng nguồn chạy được xác minh | Assertion sai chữ ký, sai nguồn hoặc thuộc tính không được phép không tạo ra credential |
| MI-04 | Access token đối soát có thời hạn tối đa 10 phút; API chỉ chấp nhận token dành cho nó từ nhà phát hành được phê duyệt | Token quá hạn, sai issuer hoặc sai audience bị từ chối; kiểm tra cả đường cấp và đường nhận |
| MI-05 | Principal đối soát chỉ có quyền đọc hóa đơn trong phạm vi được cấp | Đọc ngoài phạm vi, sửa hóa đơn và cấp quyền cho principal khác đều bị từ chối |
| MI-06 | Sau lệnh vô hiệu hóa identity, hệ thống ngừng cấp hoặc gia hạn credential trong 60 giây | Mọi lần xin credential sau giới hạn đó thất bại; đo trên các điểm cấp liên quan |
| MI-07 | Sau lệnh vô hiệu hóa identity, mọi yêu cầu mới đến các API trong phạm vi bị từ chối trong tối đa 120 giây, kể cả dùng credential đã cấp | Credential còn hạn bị từ chối trên mọi instance sau ngưỡng; kiểm tra cả trường hợp cache |
| MI-08 | Credential không được xuất hiện nguyên giá trị trong application log, trace, thông báo lỗi và artifact build thuộc phạm vi | Kích hoạt đường thành công và lỗi với credential thử nghiệm; không tìm thấy credential trong đầu ra được thu thập |
| MI-09 | Identity ngừng sử dụng phải được ngừng cấp mới và thu hồi quyền theo quy trình decommission được phê duyệt | Sau đóng tích hợp, không cấp thêm credential; yêu cầu truy cập bị từ chối theo thời hạn thu hồi đã cam kết |
| MI-10 | Quyết định truy cập nhạy cảm phải có audit liên kết được với principal và phiên bản policy | Từ sự kiện truy cập mẫu truy ngược được principal, tài nguyên, hành động, kết quả và policy áp dụng |

MI-04 và MI-07 cần được thiết kế cùng nhau. Token sống 10 phút và chỉ kiểm tra offline không tự đáp ứng cam kết chặn trong 120 giây. Hệ thống có thể cần tra trạng thái, deny list, phân phối chính sách thu hồi hoặc một cơ chế khác có độ trễ được kiểm soát.

Nếu chọn cơ chế chỉ chờ token hết hạn, phải đặc tả thời gian chặn theo thực tế, gồm cả khoảng dung sai thời gian và các phiên đã thiết lập; không ghi một cam kết thu hồi nhanh hơn khả năng của thiết kế.

Đối với kết nối lâu dài, cần bổ sung yêu cầu riêng, ví dụ đóng hoặc tái xác thực kết nối trong một thời hạn được phê duyệt. Cam kết về “yêu cầu mới” không mặc nhiên bao gồm toàn bộ luồng dữ liệu trên kết nối cũ.

### Ví dụ một đặc tả chi tiết

~~~yaml
requirement_id: MI-07
subject: Identity của workload đối soát production
trigger: Lệnh vô hiệu hóa được hệ thống quản trị xác nhận
scope: Mọi instance API hóa đơn thuộc production
required_behavior: Từ chối yêu cầu mới của identity đã bị vô hiệu hóa
maximum_propagation_seconds: 120
includes:
  - Credential đã phát hành và còn hạn
  - Cache xác thực hoặc cache quyết định phân quyền
verification:
  - Ghi nhận thời điểm xác nhận lệnh và định danh identity thử nghiệm
  - Gửi yêu cầu liên tục tới từng instance bằng credential còn hạn
  - Đối chiếu thời điểm từ chối và audit của mọi điểm thực thi
owner: Nhóm vận hành identity và nhóm API hóa đơn
~~~

Đây là ví dụ nội dung yêu cầu, không phải cấu hình triển khai hay schema bắt buộc. Điểm quan trọng là phạm vi và phép đo đủ rõ để hai nhóm triển khai không hiểu khác nhau.

## 9. Thiết kế tiêu chí kiểm thử theo rủi ro

Chỉ có ca “credential hợp lệ gọi được API” chưa chứng minh yêu cầu bảo mật được đáp ứng. Cần có ca sai, ca ranh giới và ca vận hành.

### 9.1. Xác thực và ánh xạ danh tính

- Credential hợp lệ ánh xạ đúng principal.
- Credential bị sửa, hết hạn hoặc từ nhà phát hành không được tin cậy bị từ chối.
- Credential của cùng workload nhưng sai môi trường không được dùng chéo.
- Hai miền tin cậy có cùng subject không bị gộp principal ngoài ý muốn.
- Client tự thêm header danh tính không vượt qua đường xác thực.
- Khi áp dụng ràng buộc với bên gửi, token không dùng được nếu thiếu bằng chứng sở hữu tương ứng.

Phép thử cần đi qua cơ chế xác thực thực tế. Một unit test tự tạo principal đã xác thực chỉ kiểm tra phần logic phía sau, không kiểm tra chữ ký, trust chain hoặc bootstrap.

### 9.2. Phân quyền và giới hạn ảnh hưởng

Với một principal đã xác thực, kiểm tra cả hành động được phép lẫn các hành động liền kề bị cấm: đọc thay vì ghi, tenant được cấp thay vì tenant khác, môi trường staging thay vì production.

Nếu thiết kế tách credential theo instance, kiểm tra việc thu hồi một credential có ảnh hưởng đúng phạm vi hay không. Nếu vô hiệu hóa cả identity, kiểm tra mọi credential thuộc identity đó thay vì chỉ một token mẫu.

### 9.3. Rotation, thu hồi và sự cố

Cần kiểm tra rotation trong điều kiện tải phù hợp, sự kết thúc khoảng chồng lấn, lỗi gia hạn, độ trễ cập nhật cache và credential cũ còn hạn.

Phép đo thu hồi phải chỉ rõ mốc bắt đầu và mốc kết thúc. Chẳng hạn, lấy thời điểm hệ thống quản trị xác nhận lệnh làm mốc đầu, và thời điểm mọi điểm thực thi trong phạm vi bắt đầu từ chối làm mốc cuối. Không chỉ đo thời gian cập nhật một bản ghi trong cơ sở dữ liệu quản trị.

Với truy cập đặc quyền, cần đánh giá cả lúc mất kết nối tới hệ thống quyết định chính sách. Nếu có cơ chế dùng kết quả đã cache, phải giới hạn thời gian và phạm vi; không âm thầm cho phép vô thời hạn.

### 9.4. Audit và bảo vệ credential

Một sự kiện audit hữu ích có thể gồm:

~~~json
{
  "event": "machine_access_decision",
  "principal_id": "reconciliation-prod",
  "credential_reference": "credential-ref-042",
  "instance_id": "worker-instance-17",
  "action": "invoice.read",
  "resource_id": "invoice-2048",
  "environment": "production",
  "decision": "DENY",
  "reason": "identity_disabled",
  "policy_version": "policy-revision-28",
  "correlation_id": "request-991"
}
~~~

Credential reference là mã tham chiếu phục vụ điều tra, không phải token, API key hoặc khóa riêng. Hệ thống thực tế cũng cần thời gian sự kiện và nguồn phát sinh đáng tin cậy.

Log cần được kiểm soát truy cập và bảo vệ tính toàn vẹn theo mức rủi ro. Chỉ có nhiều log chưa bảo đảm điều tra được nếu thiếu liên kết principal, phiên bản policy hoặc thời điểm chính xác.

## 10. Đánh đổi về sẵn sàng và vận hành

### Credential ngắn hạn

Credential ngắn hạn giảm thời gian sử dụng credential bị lộ, nhưng tăng phụ thuộc vào khả năng cấp mới và gia hạn. Cần dự phòng năng lực, quan sát lỗi và giới hạn ảnh hưởng khi nhà cấp gặp sự cố.

Không xử lý sự cố cấp mới bằng cách tự động chuyển sang một secret quản trị dùng chung. Cơ chế khẩn cấp, nếu cần, phải có quyền, thời hạn, phê duyệt và audit riêng.

### Thiết bị có kết nối gián đoạn

Thiết bị offline có thể không kiểm tra thu hồi ngay. Phải nêu rõ cửa sổ rủi ro, thời hạn credential, khả năng lưu khóa và hành vi khi kết nối trở lại.

Không áp cùng một cam kết thu hồi thời gian thực cho thiết bị ngoại tuyến mà không có cơ chế thực thi tương ứng. Với dữ liệu hoặc hành động rủi ro cao, có thể yêu cầu kết nối để đánh giá quyền trước khi thực hiện.

### Legacy và ngoại lệ

Một tích hợp cũ có thể chỉ hỗ trợ API key tĩnh. Yêu cầu nên xác định owner, phạm vi hẹp, nơi lưu, khả năng rotation, kiểm soát truy cập và kế hoạch thay thế.

Ngoại lệ cần có hạn và điều kiện rà soát. Việc chưa chuyển sang credential động không có nghĩa được bỏ qua inventory, phân quyền và thu hồi.

### Identity quá nhiều hoặc quá ít

Tách mọi thao tác thành một identity riêng có thể tạo gánh nặng vận hành. Gộp quá nhiều workload lại làm tăng phạm vi ảnh hưởng và giảm khả năng quy trách nhiệm.

Ranh giới tách hợp lý thường dựa trên môi trường, quyền, owner, tenant hoặc miền tin cậy, và vòng đời. Hệ thống inventory và tự động hóa cần theo kịp mức tách được chọn.

## 11. Những cách viết yêu cầu dễ gây hiểu nhầm

| Cách viết mơ hồ | Vấn đề | Cách cụ thể hóa |
| --- | --- | --- |
| Mọi service phải bảo mật | Không có hành vi hoặc tiêu chí đo | Xác định thực thể, tài nguyên, cơ chế xác thực và ca từ chối |
| Có certificate là được phép gọi | Đồng nhất xác thực với phân quyền | Sau xác thực phải đánh giá quyền trên hành động và tài nguyên |
| Đổi secret định kỳ | Thiếu phạm vi, thời hạn và xử lý credential cũ | Nêu chu kỳ, trigger sự cố, khoảng chồng lấn và tiêu chí kết thúc |
| Thu hồi ngay lập tức | Không xét cache, token còn hạn và kết nối cũ | Nêu giới hạn truyền trạng thái và phạm vi phiên hoặc yêu cầu bị chặn |
| Mỗi máy một tài khoản | Có thể sai ranh giới workload và instance | Xác định danh tính logic, credential instance và mục đích tách |
| Chỉ cho phép IP nội bộ | Không chứng minh principal và quyền | Dùng kiểm soát mạng bổ trợ cho danh tính được xác minh |
| Không ghi log secret | Chưa xác định các đầu ra cần kiểm tra | Bao gồm log, trace, lỗi, pipeline và artifact trong phạm vi |

Yêu cầu tốt cũng phải xác định ai chịu trách nhiệm khi nhiều thành phần cùng thực thi: nền tảng identity cấp credential, nền tảng chạy bảo vệ ngữ cảnh workload, dịch vụ nhận xác thực và phân quyền, nhóm vận hành xử lý vòng đời.

## 12. Áp dụng vào một bài toán cụ thể

Một job đối soát chạy theo lịch cần đọc hóa đơn của một nhóm khách hàng, tạo kết quả vào một vị trí lưu trữ riêng và không được cập nhật hóa đơn.

Thiết kế yêu cầu có thể bắt đầu bằng các quyết định:

1. Tạo identity logic riêng cho job production, có owner và mục đích đối soát.
2. Chỉ cấp credential cho phiên chạy đã được xác minh của job.
3. Tách quyền đọc hóa đơn và quyền ghi kết quả; giới hạn từng quyền vào đúng tài nguyên.
4. Cấp credential có thời hạn phù hợp và cơ chế gia hạn rõ ràng nếu job chạy lâu.
5. Cấm credential của staging gọi tài nguyên production.
6. Đặc tả riêng thời gian chặn cấp mới, thời gian chặn credential đã cấp và xử lý phiên đang chạy khi có sự cố.
7. Ghi audit theo principal, job run và phạm vi dữ liệu; không ghi giá trị credential.
8. Khi bỏ job, ngừng cấp credential, thu hồi quyền và giữ lịch sử cần thiết.

Nếu job cần xử lý tenant bổ sung, việc đổi tham số đầu vào không tự mở rộng quyền. Quyền phải được thay đổi qua quy trình đã phê duyệt, rồi kiểm chứng bằng cả ca truy cập hợp lệ và ca vượt phạm vi.

Đầu ra của thiết kế là tập yêu cầu liên kết được với rủi ro, điểm thực thi, owner và bằng chứng kiểm thử. Nhờ đó, danh tính máy được quản trị xuyên suốt vòng đời thay vì chỉ được tạo một lần rồi tồn tại không kiểm soát.
