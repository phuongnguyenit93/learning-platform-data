# Account privilege và privileged function

## 1. Mục tiêu bài học

Trong chương **Khái niệm PAM**, việc phân biệt *account privilege* và *privileged function* giúp trả lời hai câu hỏi khác nhau: một tài khoản có thể làm gì, và một thao tác cụ thể có thể tác động đến hệ thống như thế nào. Đây là nền tảng để kiểm soát quyền truy cập đặc biệt đối với tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm.

Sau bài học, bạn có thể:

- Phân biệt quyền được cấp, quyền hiệu lực và chức năng đặc quyền.
- Nhận diện đặc quyền trực tiếp, kế thừa và khả năng giành thêm quyền thông qua tài nguyên trung gian.
- Liên kết tài khoản, hành động, tài nguyên, điều kiện truy cập và bằng chứng kiểm toán.
- Chọn biện pháp PAM phù hợp: least privilege, JIT/JEA, vault, luân chuyển credential và giám sát phiên.

Một nguyên tắc xuyên suốt: đừng chỉ hỏi “đây có phải tài khoản admin không?”. Hãy xác định **chủ thể nào có thể thực hiện hành động nào, trên tài nguyên nào, trong điều kiện nào, với hậu quả gì**.

## 2. Account privilege: đặc quyền gắn với tài khoản

### 2.1. Tài khoản, danh tính và quyền

**Danh tính** đại diện cho một người, dịch vụ hoặc workload. **Tài khoản** là cách một hệ thống biểu diễn danh tính đó để xác thực và gắn quyền. Một người có thể có tài khoản làm việc thông thường và tài khoản quản trị riêng; một ứng dụng có thể dùng nhiều danh tính dịch vụ cho các môi trường khác nhau.

**Account privilege** là quyền hoặc tập quyền cho phép tài khoản thực hiện các hành động nhạy cảm vượt khỏi phạm vi sử dụng thông thường. Tùy hệ thống, quyền có thể được cấp trực tiếp, qua vai trò, nhóm, chính sách hoặc cơ chế ủy quyền.

Ví dụ:

- Tài khoản vận hành được phép khởi động lại một dịch vụ trong môi trường sản xuất.
- Tài khoản quản trị được phép sửa chính sách truy cập của một kho credential.
- Tài khoản dịch vụ được phép đọc credential cơ sở dữ liệu dành cho ứng dụng của nó.
- Tài khoản quản lý danh tính được phép thêm thành viên vào nhóm quản trị.

Đặc quyền không chỉ là khả năng ghi hoặc thay đổi cấu hình. Quyền đọc bí mật, tải dữ liệu nhạy cảm, xem bản sao lưu hoặc truy cập bộ nhớ chứa credential cũng có thể tạo ra tác động nghiêm trọng.

Từ “privilege” có ý nghĩa kỹ thuật riêng trong một số hệ điều hành hoặc sản phẩm. Trong bài này, thuật ngữ được dùng ở mức khái niệm PAM: khả năng truy cập nhạy cảm cần được kiểm soát và truy vết. Khi triển khai, phải ánh xạ khái niệm này sang mô hình quyền thực tế của hệ thống đích.

### 2.2. Quyền được cấp chưa chắc là quyền đang sử dụng được

Cần phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Quyền được gán | Có bản ghi cấp quyền cho tài khoản, nhóm hoặc vai trò | Tài khoản nằm trong nhóm vận hành |
| Quyền đủ điều kiện kích hoạt | Có thể yêu cầu kích hoạt khi đáp ứng điều kiện | Kỹ sư có thể xin vai trò xử lý sự cố |
| Quyền hiệu lực trong ngữ cảnh hiện tại | Có thể thực hiện hành động tại thời điểm xét, sau khi áp dụng các điều kiện và ràng buộc | Vai trò đã kích hoạt, còn hạn, đúng tài nguyên và phiên truy cập được chấp nhận |

**Quyền hiệu lực** có thể phụ thuộc vào quyền trực tiếp, nhóm lồng nhau, vai trò kế thừa, chính sách trên tài nguyên, trạng thái phiên, thời gian và các điều kiện truy cập. Quy tắc kết hợp quyền và quy tắc từ chối khác nhau giữa các nền tảng; không thể mặc định cứ có một quyền cho phép là hành động sẽ thành công.

Một tài khoản được gắn nhãn “read-only” vẫn có thể đọc bí mật hoặc dữ liệu nhạy cảm nếu phạm vi được phép quá rộng. Ngược lại, tên tài khoản có chữ “admin” không đủ chứng minh nó hiện có quyền quản trị. Kiểm kê phải dựa vào khả năng thực tế và điều kiện áp dụng.

## 3. Privileged function: chức năng hoặc thao tác đặc quyền

**Privileged function** là thao tác có tác động nhạy cảm đến dữ liệu, hoạt động, cấu hình bảo mật hoặc quyền kiểm soát của hệ thống. Nó có thể được thực hiện qua giao diện quản trị, API, lệnh, tác vụ tự động hoặc một quy trình vận hành.

Ví dụ:

| Chức năng | Đối tượng chịu tác động | Tác động cần quan tâm |
| --- | --- | --- |
| Thêm thành viên vào nhóm quản trị | Hệ thống danh tính | Mở rộng tập chủ thể có quyền cao |
| Thay đổi quyền truy cập vault | Kho credential | Cho phép đọc hoặc quản lý bí mật |
| Khởi động lại dịch vụ quan trọng | Dịch vụ sản xuất | Gián đoạn hoặc khôi phục khả năng phục vụ |
| Đọc credential của ứng dụng | Bí mật xác thực | Có thể mở đường truy cập hệ thống khác |
| Sửa cấu hình thu thập log bảo mật | Hệ thống giám sát | Làm thay đổi khả năng phát hiện và điều tra |
| Xuất bản sao lưu chứa dữ liệu nhạy cảm | Dữ liệu và kho lưu trữ | Có thể làm lộ dữ liệu ngoài phạm vi sử dụng |
| Sửa pipeline triển khai sản xuất | Chuỗi triển khai | Có thể thay đổi mã chạy với quyền của workload |

Một chức năng không cần mang tên “quản trị” mới là đặc quyền. Nút “khôi phục quyền truy cập” của bộ phận hỗ trợ có thể đặc biệt nhạy cảm nếu nó thay đổi phương thức xác thực của người quản trị. Tương tự, quyền sửa một tác vụ tự động có thể quan trọng hơn quyền chạy tác vụ đó.

Mức độ đặc quyền còn phụ thuộc vào tài nguyên và ngữ cảnh. Khởi động lại một dịch vụ thử nghiệm độc lập và khởi động lại dịch vụ xác thực sản xuất có thể dùng thao tác tương tự nhưng khác đáng kể về tác động. Khi đánh giá, cần xác định rõ môi trường, dữ liệu, phạm vi ảnh hưởng và khả năng phục hồi.

## 4. Hai khái niệm liên hệ như thế nào?

### 4.1. Một bên là khả năng được trao, một bên là hành động cần kiểm soát

Có thể mô tả một quyết định truy cập bằng bộ thông tin:

> **Chủ thể → tài khoản hoặc danh tính thực thi → hành động → tài nguyên → điều kiện → kết quả và bằng chứng.**

Account privilege mô tả khả năng mà tài khoản có hoặc có thể kích hoạt. Privileged function mô tả hành động nhạy cảm mà hệ thống cần bảo vệ. Cơ chế phân quyền quyết định tài khoản đó có được thực hiện hành động ấy trong ngữ cảnh hiện tại hay không.

| Góc nhìn | Câu hỏi chính | Đầu ra hữu ích cho PAM |
| --- | --- | --- |
| Tài khoản và quyền | Tài khoản này có thể làm gì? | Danh mục quyền, chủ sở hữu, nguồn cấp quyền, thời hạn |
| Chức năng | Hành động nào có thể gây tác động nhạy cảm? | Danh mục hành động, phạm vi, yêu cầu kiểm soát |
| Quan hệ truy cập | Tài khoản nào được thực hiện hành động nào trên đích nào? | Ma trận quyền và điều kiện thực thi |
| Sử dụng thực tế | Ai đã dùng quyền, khi nào và kết quả ra sao? | Nhật ký, dữ liệu phiên và bằng chứng thay đổi |

Một tài khoản có thể có nhiều đặc quyền để thực hiện nhiều chức năng. Một chức năng cũng có thể được cung cấp cho nhiều tài khoản dưới các điều kiện khác nhau. Vì vậy, danh sách tài khoản quản trị và danh sách thao tác nhạy cảm bổ sung cho nhau; mỗi danh sách riêng lẻ đều có thể bỏ sót đường truy cập.

### 4.2. Tài khoản thông thường vẫn có thể yêu cầu một chức năng đặc quyền

Giả sử kỹ sư đăng nhập cổng vận hành bằng tài khoản cá nhân. Cổng cho phép gửi yêu cầu khởi động lại đúng một dịch vụ sau khi được duyệt. Tác vụ thực tế chạy bằng danh tính dịch vụ của hệ thống vận hành.

Ở đây có ít nhất hai lớp cần kiểm soát:

1. **Quyền yêu cầu:** kỹ sư được yêu cầu hành động nào, trên dịch vụ nào, theo điều kiện nào.
2. **Quyền thực thi:** danh tính dịch vụ có thể thực hiện những gì trên hệ thống đích.

Nếu hệ thống chỉ ghi danh tính dịch vụ, sẽ khó quy trách nhiệm cho người khởi tạo. Nếu nó chỉ kiểm soát quyền của kỹ sư nhưng để tác vụ nhận tham số tùy ý, người dùng có thể khiến danh tính dịch vụ thực hiện hành động vượt phạm vi được duyệt.

Cần liên kết yêu cầu, người khởi tạo, phê duyệt, tham số đã kiểm tra, danh tính thực thi và kết quả trên tài nguyên đích.

### 4.3. Có đặc quyền không có nghĩa mọi hành động đều là quản trị

Một tài khoản có quyền cao vẫn có thể thực hiện thao tác thông thường. Tuy nhiên, phiên đăng nhập của nó vẫn chứa khả năng sử dụng đặc quyền. Việc tách tài khoản làm việc thường ngày và tài khoản quản trị giúp giảm khả năng đặc quyền bị dùng ngoài mục đích, nhưng chưa thay thế được giới hạn hành động và giám sát sử dụng.

PAM cần quản lý cả **khả năng đang tồn tại** lẫn **hành động thực sự diễn ra**. Không có hành động nhạy cảm trong log chưa chứng minh rằng tài khoản không có đặc quyền dư thừa.

## 5. Đặc quyền trực tiếp, kế thừa và đường dẫn đến quyền cao

### 5.1. Đặc quyền trực tiếp và kế thừa

Đặc quyền trực tiếp xuất hiện khi tài khoản được cấp hành động cụ thể trên tài nguyên. Đặc quyền kế thừa xuất hiện thông qua nhóm, vai trò hoặc quan hệ phân cấp.

Ví dụ: một kỹ sư thuộc nhóm trực ca; nhóm trực ca được gắn vai trò vận hành; vai trò vận hành được phép khởi động lại một tập dịch vụ. Việc chỉ kiểm tra quyền gắn trực tiếp vào tài khoản sẽ bỏ sót khả năng này.

Để giải thích vì sao tài khoản có quyền, cần giữ được chuỗi liên hệ:

> Tài khoản → nhóm hoặc vai trò → chính sách cấp quyền → hành động và tài nguyên được phép.

Nếu quyền chỉ hiệu lực sau khi kích hoạt, cần ghi thêm điều kiện và khoảng thời gian kích hoạt.

### 5.2. Khả năng có được quyền thông qua tài nguyên trung gian

Một tài khoản chưa có quyền quản trị trực tiếp vẫn có thể kiểm soát thành phần được sử dụng bởi một danh tính quyền cao. Ví dụ, tài khoản được sửa một tác vụ mà sau đó chạy với quyền quản trị; hoặc nó được đổi chính sách để tự cấp thêm quyền.

Các câu hỏi cần kiểm tra gồm:

- Ai được sửa nội dung tác vụ hoặc pipeline chạy với quyền cao?
- Ai được thay đổi thành viên nhóm quản trị hoặc cơ chế cấp quyền?
- Ai được thay đổi phương thức xác thực hay credential của tài khoản đặc quyền?
- Ai được đọc bí mật cho phép đăng nhập vào một hệ thống nhạy cảm khác?
- Ai có thể sửa cấu hình thu thập bằng chứng hoặc quy tắc giám sát?

Không phải mọi khả năng sửa tài nguyên đều dẫn đến leo thang quyền. Cần xác định điều kiện cụ thể: tài nguyên có thực sự được thực thi không, chạy bằng danh tính nào, có kiểm tra thay đổi hay không, và còn ràng buộc nào ngăn đường truy cập. Mục tiêu của kiểm kê là nhận diện đường dẫn có cơ sở, thay vì suy đoán từ tên quyền.

## 6. Từ khái niệm đến một ma trận kiểm kê có ích

Danh mục PAM nên liên kết tài khoản với chức năng và tài nguyên, thay vì chỉ lưu cột “có phải admin”. Một bản ghi tối thiểu nên giải thích được:

| Trường | Nội dung cần ghi |
| --- | --- |
| Tài khoản và loại danh tính | Tài khoản cá nhân, tài khoản dùng chung có kiểm soát hoặc tài khoản dịch vụ |
| Chủ sở hữu | Người hoặc nhóm chịu trách nhiệm về nhu cầu và vòng đời quyền |
| Chức năng đặc quyền | Hành động cụ thể cần được phép |
| Tài nguyên và môi trường | Dịch vụ, máy chủ, vault hoặc dữ liệu được phép tác động |
| Nguồn quyền | Cấp trực tiếp, nhóm, vai trò, chính sách hoặc cơ chế ủy quyền |
| Điều kiện hiệu lực | Thời hạn, kích hoạt, phê duyệt, giới hạn phiên và điều kiện khác |
| Đường truy cập | Cổng vận hành, API, broker, truy cập trực tiếp hoặc công cụ tự động |
| Credential và phương thức xác thực | Cách cấp và bảo vệ credential; không ghi giá trị bí mật vào bảng |
| Bằng chứng | Nơi lưu yêu cầu, thay đổi quyền, hành động và kết quả |
| Thu hồi và rà soát | Cách kết thúc quyền, xử lý phiên tồn tại và người xác nhận nhu cầu |

Ví dụ rút gọn cho một hệ thống giả định:

| Tài khoản hoặc danh tính | Chức năng | Phạm vi | Cách cấp và kiểm soát |
| --- | --- | --- | --- |
| Kỹ sư trực ca | Yêu cầu khởi động lại dịch vụ | Dịch vụ A ở sản xuất | Xác thực bổ sung, yêu cầu sự cố, phê duyệt và thời hạn |
| Danh tính tác vụ vận hành | Thực hiện khởi động lại | Chỉ dịch vụ A | Quyền giới hạn hành động, kiểm tra tham số, ghi kết quả |
| Danh tính ứng dụng A | Đọc credential để kết nối dữ liệu | Bí mật riêng của ứng dụng A | Xác thực workload, chính sách đọc hẹp, theo dõi truy xuất |
| Người quản trị vault | Thay đổi chính sách truy cập | Phân vùng vault được giao | Kích hoạt có thời hạn, kiểm soát thay đổi và lưu bằng chứng |

Bảng này giúp phát hiện quyền quá rộng: nếu danh tính tác vụ chỉ cần khởi động lại dịch vụ A nhưng có thể sửa mọi dịch vụ, account privilege đã vượt nhu cầu của privileged function.

## 7. Áp dụng các biện pháp PAM đúng lớp

### 7.1. Least privilege: bắt đầu từ nhu cầu thực hiện chức năng

**Least privilege** yêu cầu chỉ cấp những quyền cần thiết cho nhiệm vụ được xác định. Nên mô tả hành động và tài nguyên trước, rồi tìm cách cấp quyền phù hợp.

Ví dụ, nhu cầu “khôi phục dịch vụ A khi gặp sự cố” không tự động đòi hỏi quyền sửa toàn bộ máy chủ, đọc tất cả bí mật hoặc thay đổi nhóm quản trị. Nếu công việc gồm nhiều thao tác, cần xác định tập thao tác thực sự cần thiết và giới hạn tham số tương ứng.

Đừng chỉ thu hẹp vai trò hiển thị. Cần kiểm tra quyền qua nhóm, khả năng truy cập credential khác và những thành phần tài khoản có thể sửa để mở rộng phạm vi thực thi.

### 7.2. JIT giới hạn thời gian; JEA giới hạn khả năng thực hiện

**Just-in-time (JIT)** giảm khoảng thời gian đặc quyền có hiệu lực bằng cách kích hoạt khi có nhu cầu và kết thúc sau một khoảng thời gian hoặc điều kiện xác định.

**Just-enough administration (JEA)** giới hạn hành động quản trị và phạm vi cần cho nhiệm vụ. Cách triển khai cụ thể tùy nền tảng; việc giới hạn có thể nằm ở vai trò, API, cổng vận hành hoặc bộ thực thi chỉ cho phép những thao tác đã xác định.

Ví dụ: kỹ sư được phép yêu cầu khởi động lại dịch vụ A trong 20 phút. Khoảng 20 phút minh họa cho JIT; quyền chỉ tác động đến đúng dịch vụ A minh họa cho JEA. Con số này là lựa chọn của tình huống, không phải thời hạn chuẩn cho mọi hệ thống.

Một quyền rất rộng được cấp trong thời gian ngắn vẫn có thể gây tác động lớn. Một quyền hẹp nhưng tồn tại không cần thiết lâu dài vẫn làm tăng khả năng bị lạm dụng. Hai hướng kiểm soát này hỗ trợ nhau.

Khi thời hạn kết thúc, cần xem hệ thống thực sự thu hồi điều gì. Xóa vai trò hoặc ngừng cấp credential mới không mặc nhiên chấm dứt mọi phiên, token hoặc kết nối đã được tạo. Cách xử lý phải phù hợp với cơ chế xác thực và phân quyền của hệ thống đích.

### 7.3. Vault và luân chuyển credential bảo vệ phương tiện truy cập

Vault giúp quản lý việc lưu giữ và cấp phát credential theo chính sách. Luân chuyển credential giúp giảm thời gian một giá trị bí mật cũ còn hữu dụng. Đây là lớp kiểm soát quan trọng, nhưng phạm vi quyền của tài khoản vẫn phải được thiết kế riêng.

Nếu vault cấp một credential có toàn quyền trên nhiều hệ thống, việc cất giữ credential an toàn không tự làm hẹp các account privilege đó. Tương tự, đổi mật khẩu không tự xóa vai trò hoặc nhóm đã gán cho tài khoản, và có thể không chấm dứt phiên đã xác thực.

Với tài khoản dịch vụ, cần xác định ứng dụng lấy credential mới như thế nào, cách xử lý credential cũ và khả năng tiếp tục hoạt động trong quá trình chuyển đổi. Chủ sở hữu dịch vụ phải chịu trách nhiệm cho cả nhu cầu quyền và vòng đời credential.

### 7.4. Giám sát phiên và ghi nhận hành động bổ sung cho nhau

Giám sát phiên có thể giúp quan sát hoạt động tương tác. Tuy nhiên, privileged function cũng có thể được gọi qua API, pipeline hoặc tác vụ không có màn hình tương tác.

Cần chọn bằng chứng phù hợp với đường truy cập:

- Phiên tương tác: danh tính người dùng, đích truy cập, thời gian, dữ liệu phiên phù hợp với chính sách.
- API hoặc tác vụ tự động: danh tính workload, hành động, tài nguyên, tham số an toàn để ghi log, kết quả và mã liên kết yêu cầu.
- Thay đổi quyền: ai yêu cầu, ai phê duyệt, quyền trước và sau, thời điểm bắt đầu và kết thúc.

Không ghi credential, token hoặc giá trị bí mật vào log. Khi cần ghi nhận việc đọc bí mật, có thể lưu định danh bí mật, danh tính truy cập và kết quả; nội dung bí mật không phải bằng chứng cần sao chép.

## 8. Ví dụ xuyên suốt: khởi động lại dịch vụ sản xuất

### 8.1. Bối cảnh và vấn đề

Một nhóm vận hành cần khởi động lại dịch vụ A khi xảy ra sự cố. Cách làm ban đầu là dùng chung một tài khoản có quyền quản trị toàn máy chủ. Tài khoản này vừa khởi động lại dịch vụ, vừa có thể sửa cấu hình bảo mật và đọc dữ liệu không liên quan.

Chức năng cần thiết khá hẹp, nhưng account privilege lại rộng và khó quy trách nhiệm. Việc đổi mật khẩu định kỳ chỉ xử lý một phần vòng đời credential; nó không giải quyết được sự chênh lệch giữa nhu cầu và quyền đã cấp.

### 8.2. Thiết kế lại quyền yêu cầu và quyền thực thi

Một phương án kiểm soát gồm:

1. Kỹ sư đăng nhập bằng danh tính cá nhân và gắn yêu cầu với mã sự cố.
2. Hệ thống kiểm tra kỹ sư có thuộc phạm vi trực ca được phép hay không.
3. Người có thẩm quyền phê duyệt hành động trên đúng dịch vụ và môi trường.
4. Quyền yêu cầu được kích hoạt có thời hạn; tác vụ chỉ nhận dịch vụ đã được cho phép.
5. Danh tính tác vụ thực thi quyền tối thiểu trên hệ thống đích.
6. Hệ thống ghi kết quả và kết thúc quyền theo điều kiện đã xác định.

Đặc tả dưới đây chỉ minh họa tư duy thiết kế; đây là mã giả, không phải cấu hình có thể triển khai trực tiếp:

```text
Yêu cầu:
  người_khởi_tạo = danh_tính_cá_nhân_đã_xác_thực
  hành_động = khởi_động_lại_dịch_vụ
  tài_nguyên = dịch_vụ_A
  môi_trường = sản_xuất
  lý_do = mã_sự_cố

Chỉ cho phép khi:
  người_khởi_tạo có quyền yêu cầu trong phạm vi này
  yêu cầu đã được phê duyệt theo chính sách
  thời hạn kích hoạt còn hiệu lực
  hành động và tài nguyên khớp với nội dung đã duyệt
  danh tính thực thi có quyền tương ứng trên hệ thống đích

Khi thực thi:
  chỉ nhận tham số thuộc tập đã cho phép
  từ chối lệnh tùy ý hoặc thay đổi đích ngoài phạm vi
  ghi người khởi tạo, người duyệt, danh tính thực thi và kết quả
```

Việc chặn lệnh tùy ý ở cổng là chưa đủ nếu kỹ sư vẫn có một đường đăng nhập trực tiếp với quyền rộng hơn. Cần kiểm tra các đường truy cập còn lại và cơ chế phân quyền tại đích. Nếu có cơ chế truy cập khẩn cấp, nó cũng cần chủ sở hữu, điều kiện sử dụng và bằng chứng riêng.

### 8.3. Bằng chứng cần giữ lại

Một chuỗi bằng chứng có ích cho kiểm toán và ứng phó sự cố gồm:

- Mã yêu cầu, lý do và tài nguyên được duyệt.
- Danh tính người khởi tạo, người phê duyệt và danh tính thực thi.
- Chức năng được phép, thời điểm kích hoạt và thời điểm hết hiệu lực.
- Hành động thực tế, đích thực tế, kết quả và dấu thời gian.
- Các thay đổi quyền liên quan, lỗi thu hồi hoặc sự kiện tiếp tục truy cập sau thời hạn.

Nhờ chuỗi này, người điều tra có thể kiểm tra hành động thực tế có phù hợp với quyền và mục đích được duyệt hay không. Bản ghi “đăng nhập thành công” riêng lẻ không trả lời được các câu hỏi đó.

## 9. Tài khoản dịch vụ: cùng nguyên tắc, cách thực hiện khác

Tài khoản dịch vụ thường hoạt động liên tục và không có con người thao tác trực tiếp trong từng lần gọi. Không nên áp dụng máy móc một quy trình phê duyệt thủ công cho mọi yêu cầu của ứng dụng.

Thay vào đó, cần xác định danh tính workload, chủ sở hữu, tài nguyên cần truy cập và chính sách được duyệt cho hoạt động thường lệ. Có thể dùng danh tính riêng theo dịch vụ và môi trường, giới hạn quyền và credential có thời hạn khi nền tảng hỗ trợ, cùng log cho các hành động nhạy cảm.

Ví dụ, ứng dụng A cần đọc bí mật kết nối dữ liệu của chính nó. Chức năng này nên được giới hạn vào bí mật đó; nó không kéo theo nhu cầu liệt kê, sửa hoặc xóa toàn bộ vault. Người quản trị thay đổi chính sách truy cập của ứng dụng lại đang thực hiện một privileged function khác, cần được kiểm soát riêng.

Khi dịch vụ ngừng hoạt động, việc thu hồi phải xem xét quyền, credential, token và các kết nối liên quan theo cơ chế của nền tảng. Chỉ xóa một giá trị bí mật khỏi nơi lưu chưa chắc đã kết thúc khả năng truy cập của workload.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu cần dùng |
| --- | --- |
| Chỉ tài khoản mang tên admin mới cần PAM | Nhận diện bằng khả năng và tác động, bao gồm danh tính dịch vụ và quyền đọc nhạy cảm |
| Tài khoản có nhãn read-only thì ít rủi ro | Xem nó đọc dữ liệu gì và dữ liệu đó có mở đường truy cập khác không |
| Phê duyệt đăng nhập đồng nghĩa phê duyệt mọi thao tác | Xác định riêng chức năng, tài nguyên và điều kiện được phép |
| Credential đã vào vault thì quyền đã tối thiểu | Quản lý credential và giới hạn quyền là hai công việc liên quan nhưng riêng biệt |
| Cấp quyền vài phút thì có thể cấp toàn quyền | Quy mô tác động trong vài phút vẫn cần được giới hạn |
| Vai trò hết hạn thì mọi phiên đều kết thúc | Kiểm tra cơ chế token, phiên và kết nối đang tồn tại |
| Ghi hình mọi phiên là đủ bằng chứng | Bổ sung log quyền, API, workload, yêu cầu và kết quả tại đích |
| Quyền yêu cầu tác vụ luôn tương đương quyền của danh tính chạy tác vụ | Phân biệt quyền yêu cầu và quyền thực thi; kiểm tra cách ràng buộc tham số và tài nguyên |

## 11. Bài tập vận dụng

Một danh tính pipeline được phép triển khai ứng dụng A vào môi trường sản xuất. Nó đồng thời có quyền đọc mọi bí mật của nhóm và sửa chính sách truy cập vault. Kỹ sư phát triển được sửa pipeline sau một bước phê duyệt mã nguồn.

Hãy phân tích theo trình tự:

1. Liệt kê riêng các privileged function: triển khai ứng dụng, đọc bí mật và thay đổi chính sách truy cập.
2. Xác định nguồn quyền và phạm vi hiệu lực của danh tính pipeline đối với từng chức năng.
3. Xác định ai có thể sửa phần thực thi của pipeline, điều kiện để thay đổi có hiệu lực và danh tính chạy thay đổi đó.
4. So sánh từng quyền với nhu cầu triển khai ứng dụng A; đánh dấu quyền chưa có nhu cầu nghiệp vụ rõ ràng.
5. Đề xuất giới hạn tài nguyên, tách trách nhiệm và cách cấp credential phù hợp với nền tảng.
6. Xác định bằng chứng cần có để nối người sửa, thay đổi được duyệt, lần chạy pipeline và hành động tại hệ thống đích.

**Định hướng trả lời:** quyền đọc mọi bí mật và sửa chính sách vault không đương nhiên cần cho việc triển khai một ứng dụng. Khả năng sửa pipeline là một điểm cần xem xét vì nó có thể tác động đến hành động chạy bằng danh tính dịch vụ. Tuy nhiên, phải kiểm tra quy trình phê duyệt, cơ chế bảo vệ phần thực thi và ràng buộc tại đích trước khi kết luận có đường leo thang quyền. Phương án giảm quyền cần bảo đảm tác vụ triển khai hợp lệ vẫn hoàn thành.

## 12. Ghi nhớ

Account privilege cho biết tài khoản có khả năng gì; privileged function cho biết hành động nhạy cảm nào cần bảo vệ. Mối liên hệ giữa hai khái niệm chỉ đầy đủ khi có tài nguyên, điều kiện hiệu lực và danh tính thực thi.

Khi xem xét một quyền, hãy lần lượt xác định: nhu cầu nghiệp vụ, chức năng, đích tác động, chủ thể được phép, nguồn quyền, thời hạn, đường truy cập và bằng chứng. Cách nhìn này giúp thiết kế least privilege, JIT/JEA và quản lý credential thành một cơ chế PAM có thể giải thích, kiểm toán và xử lý khi xảy ra sự cố.