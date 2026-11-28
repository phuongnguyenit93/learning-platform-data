# Discovery connector

## Mục tiêu bài học

Trong chương **Kiến trúc PAM**, discovery connector là thành phần kết nối đến một nguồn hoặc hệ thống đích để phát hiện tài nguyên, tài khoản, quan hệ cấp quyền và những dấu hiệu liên quan đến đặc quyền. Nó cung cấp dữ liệu cho hoạt động kiểm kê và đánh giá phạm vi quản lý của **Privileged Access Management (PAM)**.

Trong module kiểm soát quyền truy cập đặc biệt đối với tài khoản quản trị, dịch vụ và hạ tầng nhạy cảm, discovery giúp trả lời: **đang có những đường truy cập đặc quyền nào, ở đâu, thuộc về ai và đã được kiểm soát đến mức nào?** Dữ liệu này hỗ trợ least privilege, lựa chọn cơ chế JIT/JEA, đưa tài khoản vào vault, luân chuyển credential và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố.

Sau bài học, bạn có thể:

- Giải thích vị trí và trách nhiệm của discovery connector trong kiến trúc PAM.
- Xác định nguồn dữ liệu, quyền truy cập, phạm vi mạng và ranh giới tin cậy.
- Phân biệt phát hiện đối tượng với kết luận quyền hiệu lực và trạng thái đã được PAM quản lý.
- Thiết kế thu thập, chuẩn hóa, định danh, đối soát và xử lý dữ liệu thiếu.
- Xử lý phân trang, thay đổi theo thời gian, lỗi từng phần và tài nguyên ngắn hạn.
- Chuyển phát hiện thành công việc có chủ sở hữu và bằng chứng thay vì tự động thay đổi tài khoản.

## 1. Discovery connector giải quyết vấn đề gì?

Một tổ chức có thể có nhiều nguồn danh tính và hệ thống đích:

- Tài khoản cục bộ trên máy chủ.
- Nhóm và tài khoản trong hệ thống thư mục.
- Tài khoản quản trị của cơ sở dữ liệu.
- Role, principal và quan hệ tin cậy trên nền tảng đám mây.
- Tài khoản dịch vụ, pipeline và danh tính workload.
- Tài khoản trên thiết bị mạng hoặc nền tảng vận hành chuyên biệt.

Danh sách trong vault chỉ phản ánh những tài khoản đã được ghi nhận ở đó. Nó không tự chứng minh toàn bộ tài khoản đặc quyền trong hạ tầng đều đã được quản lý.

Discovery connector giúp thu hẹp khoảng cách này bằng cách thu thập dữ liệu từ nguồn đã được cho phép, xác định những đối tượng cần xem xét và theo dõi sự thay đổi.

Ví dụ, connector phát hiện một tài khoản cơ sở dữ liệu có quyền quản trị nhưng chưa tìm thấy liên kết với bản ghi PAM. Kết luận thích hợp là:

> Có một ứng viên tài khoản đặc quyền cần đối soát trạng thái quản lý.

Chưa thể lập tức kết luận tài khoản đó đã bị lộ, không có chủ sở hữu hoặc phải bị vô hiệu hóa. Những quyết định này cần thêm ngữ cảnh và bằng chứng.

## 2. Phạm vi trách nhiệm và những việc cần tách biệt

Discovery thường làm các việc sau:

1. Xác định những tài nguyên thuộc phạm vi.
2. Liệt kê tài khoản, role, nhóm và quan hệ liên quan.
3. Thu thập thuộc tính được phép, chẳng hạn trạng thái tài khoản hoặc chủ sở hữu đã khai báo.
4. Ghi nhận nguồn, thời điểm và độ đầy đủ của quan sát.
5. Chuyển dữ liệu sang nơi chuẩn hóa và đối soát.
6. Báo các thay đổi hoặc trường hợp cần xử lý.

Các chức năng khác có thể dùng chung nền tảng nhưng cần được phân biệt:

| Chức năng | Câu hỏi chính |
| --- | --- |
| Discovery | Có những đối tượng và quan hệ nào trong phạm vi quan sát? |
| Phân tích đặc quyền | Những quan hệ đó tạo ra khả năng gì trên hệ thống đích? |
| Đối soát PAM | Đối tượng nào đã có bản ghi và cơ chế quản lý tương ứng? |
| Onboarding | Làm thế nào đưa tài khoản vào quy trình PAM được chấp nhận? |
| Rotation | Làm thế nào thay credential và xác minh ở đích? |
| Điều phối phiên | Làm thế nào kiểm soát một lần sử dụng tài khoản? |
| Thu hồi | Làm thế nào chấm dứt khả năng truy cập thực tế? |

**Phát hiện không đồng nghĩa được phép thay đổi.** Quyền thu thập metadata không nên mặc định bao gồm đổi mật khẩu, thêm role, kích hoạt tài khoản hoặc mở phiên quản trị.

Một sản phẩm có thể tích hợp nhiều chức năng. Khi thiết kế, vẫn cần kiểm soát riêng hành động, danh tính thực thi và bằng chứng của từng chức năng.

## 3. Vị trí trong kiến trúc PAM

~~~mermaid
flowchart LR
    Scope[Phạm vi được chấp nhận] --> Scheduler[Bộ lập lịch và điều phối]
    Scheduler --> Connector[Discovery connector]
    Source[Nguồn hoặc hệ thống đích] --> Connector
    Identity[Danh tính thu thập giới hạn] --> Connector
    Connector --> Intake[Điểm tiếp nhận dữ liệu]
    Intake --> Normalize[Chuẩn hóa và kiểm tra]
    Normalize --> Inventory[Kiểm kê và quan hệ]
    Inventory --> Reconcile[Đối soát với phạm vi PAM]
    Reconcile --> Review[Review và xác nhận chủ sở hữu]
    Review --> Workflow[Luồng onboarding hoặc xử lý]
    Connector --> Evidence[Bằng chứng và trạng thái thu thập]
    Reconcile --> Evidence
~~~

Sơ đồ thể hiện trách nhiệm logic. Tùy giải pháp, một số khối có thể chạy trong cùng dịch vụ.

### 3.1. Bộ điều phối

Bộ điều phối xác định nguồn nào được thu thập, thời điểm chạy, phạm vi tài nguyên, phiên bản connector và giới hạn tải. Nó cũng theo dõi lần chạy bị treo, bị hủy hoặc chỉ hoàn tất một phần.

### 3.2. Connector

Connector hiểu giao thức và mô hình dữ liệu của nguồn. Nó gọi API, truy vấn hoặc đọc giao diện quản lý đã được cho phép rồi chuyển kết quả về định dạng tiếp nhận.

Connector không nên tự mở rộng phạm vi chỉ vì nguồn trả về địa chỉ hoặc liên kết đến một hệ thống khác.

### 3.3. Chuẩn hóa và kho kiểm kê

Lớp này kiểm tra dữ liệu, ánh xạ định danh và lưu các quan hệ. Nó phải giữ được nguồn gốc thông tin, thay vì biến mọi trường đầu vào thành một kết luận chắc chắn.

### 3.4. Đối soát và workflow

Đối soát liên kết đối tượng được phát hiện với bản ghi PAM hiện có. Workflow đưa những trường hợp mới, mâu thuẫn hoặc thiếu chủ sở hữu đến người có trách nhiệm.

Vault có thể là nguồn tham chiếu hoặc nơi cung cấp credential cho connector theo chính sách. Discovery không cần quyền đọc toàn bộ bí mật trong vault để thực hiện mọi lần thu thập.

## 4. Chọn nguồn dữ liệu và mô hình thu thập

### 4.1. Nguồn dữ liệu có những giới hạn khác nhau

| Nguồn | Dữ liệu có thể cung cấp | Giới hạn cần kiểm tra |
| --- | --- | --- |
| Danh mục tài nguyên | Tài nguyên dự kiến thuộc phạm vi, chủ sở hữu khai báo | Có thể chậm cập nhật hoặc thiếu tài nguyên ngoài quy trình |
| Hệ thống thư mục | Danh tính, nhóm, thành viên | Chưa phản ánh toàn bộ tài khoản cục bộ hoặc quyền ở đích |
| API quản lý nền tảng | Role, binding, principal, cấu hình tài nguyên | Phụ thuộc scope, quyền đọc và cách phân trang |
| Giao diện quản lý hệ điều hành | Tài khoản cục bộ, nhóm quản trị, dịch vụ | Khả năng quan sát khác nhau theo hệ điều hành và cơ chế kết nối |
| Metadata cơ sở dữ liệu | Tài khoản, role, quyền trong cơ sở dữ liệu | Không tự bao phủ quyền trên máy chủ hoặc nền tảng bên ngoài |
| Metadata cấu hình ứng dụng | Tham chiếu credential, tên tài khoản, phụ thuộc được khai báo | Không chứng minh mọi phụ thuộc thực tế đã được thấy |
| Sự kiện và audit | Tạo, đổi hoặc sử dụng đối tượng trong phần log được thu thập | Thiếu sự kiện không chứng minh đối tượng không tồn tại |

Không nên coi một nguồn duy nhất là đầy đủ cho mọi loại tài khoản và quyền.

Ví dụ, thấy một máy chủ trong danh mục tài nguyên không có nghĩa đã đọc được tài khoản cục bộ của máy đó. Ngược lại, không thấy tài khoản trong thư mục không có nghĩa tài khoản cục bộ không tồn tại.

### 4.2. Thu thập chủ động và nhận dữ liệu sẵn có

**Thu thập chủ động** truy vấn trực tiếp nguồn. Nó có thể cung cấp trạng thái hiện tại nhưng tạo tải, kết nối và sự kiện xác thực.

**Nhận dữ liệu sẵn có** sử dụng sự kiện, bản xuất hoặc dữ liệu do hệ thống khác cung cấp. Nó giảm nhu cầu kết nối trực tiếp trong một số trường hợp nhưng phụ thuộc độ trễ, độ đầy đủ và chất lượng của nguồn trung gian.

Hai cách có thể bổ sung cho nhau. Sự kiện giúp nhận biết thay đổi nhanh, còn một lần đối soát đầy đủ có thể phát hiện khoảng trống do sự kiện bị bỏ lỡ.

### 4.3. Có agent hoặc không có agent

| Mô hình | Điểm cần đánh giá |
| --- | --- |
| Không có agent tại đích | Quyền truy cập từ xa, khả năng tiếp cận mạng, tải lên giao diện quản lý |
| Có agent | Quyền của agent, cách cập nhật, bảo vệ tiến trình, độ tin cậy dữ liệu gửi về |
| Qua nguồn quản lý trung gian | Phạm vi nguồn trung gian thấy được, độ trễ và quyền tổng hợp |

Không có mô hình nào tự bảo đảm ít đặc quyền hơn trong mọi môi trường. Cần xem quyền thực tế, khả năng sửa cấu hình và ảnh hưởng khi thành phần bị kiểm soát.

## 5. Xác định hợp đồng phạm vi trước khi chạy

Một lần discovery cần có phạm vi đủ rõ để giải thích kết quả.

Những thông tin tối thiểu gồm:

- Nguồn, tenant, tài khoản nền tảng hoặc miền quản lý được phép.
- Tập tài nguyên hoặc tiêu chí lựa chọn tài nguyên.
- Loại đối tượng và quan hệ cần thu thập.
- Hành động được phép và hành động không thuộc nhiệm vụ.
- Danh tính thực thi, quyền cần có và cách cấp credential.
- Khu vực mạng được kết nối, điểm đích và cách xác thực máy chủ.
- Thời gian chạy, giới hạn đồng thời, timeout và retry.
- Chủ sở hữu, nơi nhận kết quả và cách xử lý khi thu thập thiếu.

Một connector được phép đọc tài khoản của cơ sở dữ liệu A không tự có quyền quét các cơ sở dữ liệu khác được nhắc đến trong cấu hình của A.

### Phân biệt phạm vi mong muốn và phạm vi thực sự quan sát

~~~text
Phạm vi được giao
      |
      v
Tài nguyên đã tiếp cận được
      |
      v
Loại đối tượng đã đọc thành công
      |
      v
Quan hệ có đủ dữ liệu để phân tích
~~~

Mỗi bước có thể làm phạm vi quan sát hẹp lại. Báo cáo cần phản ánh sự thu hẹp đó, thay vì chỉ ghi “discovery hoàn tất”.

## 6. Danh tính và least privilege của connector

Connector cần một danh tính có thể xác định và quản lý vòng đời. Tránh dùng tài khoản cá nhân của quản trị viên để chạy một dịch vụ thu thập định kỳ.

### 6.1. Quyền theo nhu cầu dữ liệu

Bắt đầu từ các thao tác cần thực hiện:

- Liệt kê tài nguyên trong phạm vi.
- Đọc thuộc tính tài khoản.
- Đọc role, binding và thành viên nhóm cần thiết.
- Đọc metadata dịch vụ hoặc tham chiếu đã được cho phép.
- Gửi kết quả đến đúng nơi tiếp nhận.

Sau đó xác định quyền nhỏ nhất mà hệ thống hỗ trợ cho những thao tác này.

Nếu một nguồn yêu cầu quyền mạnh hơn để đọc một loại metadata, cần đánh giá rõ rủi ro và khả năng thay thế. Không mặc định cấp quản trị toàn hệ thống để loại bỏ mọi lỗi thiếu quyền.

### 6.2. Credential khởi tạo

Connector cũng cần xác thực. Khi nền tảng hỗ trợ, có thể dùng danh tính workload, chứng thư hoặc cơ chế xác thực phù hợp để giảm phụ thuộc vào bí mật dài hạn được sao chép thủ công.

Nếu phải dùng mật khẩu hoặc token tĩnh:

- Lưu và phân phối qua cơ chế được kiểm soát.
- Giới hạn scope và bên được sử dụng.
- Có chủ sở hữu, vòng đời và cách thu hồi.
- Xác định ảnh hưởng của rotation đến các lần chạy.
- Không ghi credential vào cấu hình công khai hoặc log.

Không cấp quyền đọc mọi bản ghi vault chỉ để connector lấy credential cho một nguồn.

### 6.3. Đọc metadata vẫn có tác động

Một connector không thay đổi tài khoản vẫn có thể gây tải, tạo nhiều sự kiện xác thực hoặc làm lộ thông tin kiểm kê nếu bị kiểm soát.

Các lần xác thực sai lặp lại còn có thể chạm cơ chế khóa tài khoản của hệ thống đích. Vì vậy cần giới hạn retry, theo dõi lỗi và dừng khi có dấu hiệu cần can thiệp.

## 7. Những dữ liệu nên thu thập và nên tránh

### 7.1. Dữ liệu phục vụ phân tích

Một quan sát có ích thường gồm:

| Nhóm | Nội dung |
| --- | --- |
| Định danh nguồn | Hệ thống, tenant, miền quản lý, phạm vi |
| Định danh đối tượng | ID gốc, loại đối tượng, tên hiển thị |
| Trạng thái | Hoạt động, bị vô hiệu hóa hoặc trạng thái nguồn cung cấp |
| Quan hệ | Thành viên nhóm, gán role, kế thừa, quan hệ tin cậy |
| Phạm vi quyền | Tài nguyên và điều kiện áp dụng khi nguồn cung cấp |
| Chủ sở hữu | Tham chiếu người hoặc đội đã khai báo, nguồn của thông tin |
| Phụ thuộc | Dịch vụ hoặc workload có tham chiếu được quan sát |
| Bằng chứng | Thời điểm, lần chạy, phương thức thu thập, độ đầy đủ |

Ngày sử dụng gần nhất chỉ có ý nghĩa trong phạm vi dữ liệu mà nguồn đo được. Không mặc định đó là toàn bộ lịch sử sử dụng hoặc căn cứ duy nhất để thu hồi quyền.

### 7.2. Không cần lấy giá trị bí mật để biết tài khoản tồn tại

Discovery tài khoản thông thường không cần đọc mật khẩu, token, khóa riêng hoặc hash mật khẩu.

Nếu mục tiêu là phát hiện tham chiếu credential trong cấu hình, nên thu thập định danh và quan hệ cần thiết thay vì sao chép giá trị bí mật. Một tác vụ tìm bí mật lộ trong nội dung là phạm vi khác, cần quyền và cách xử lý dữ liệu riêng.

Nếu dữ liệu phản hồi bất ngờ chứa bí mật, cần ngăn nó lan vào log, kho kiểm kê hoặc thông báo thông thường và xử lý theo quy trình phù hợp.

## 8. Định danh và chuẩn hóa: tránh gộp nhầm hoặc đếm trùng

Tên hiển thị không đủ để làm khóa duy nhất.

Hai máy chủ có thể cùng có tài khoản tên “admin” nhưng đó là hai principal cục bộ khác nhau. Một tài khoản thư mục cũng có thể được biểu diễn ở nhiều hệ thống đích với tên hoặc bí danh khác nhau.

Một khóa định danh khái niệm có thể dựa trên:

~~~text
Miền nguồn + phạm vi quản lý + loại đối tượng + ID gốc
~~~

Nếu nguồn chỉ có tên, cần ghi rõ giới hạn định danh. Nếu ID có thể được tái sử dụng sau khi xóa đối tượng, cần thêm thông tin vòng đời hoặc cơ chế phân biệt lần tồn tại theo khả năng nguồn.

### 8.1. Giữ bản gốc và dạng chuẩn hóa

Nên giữ được:

- ID và tên theo nguồn.
- ID nội bộ dùng để liên kết.
- Quy tắc ánh xạ và phiên bản quy tắc.
- Nguồn, thời điểm và lý do liên kết.

Không nên gộp hai đối tượng chỉ vì tên giống nhau. Cũng không nên tạo hai tài khoản độc lập khi thực chất chỉ là hai cách gọi của cùng một principal đã được xác minh.

### 8.2. Định danh quan hệ

Quan hệ cần đủ ngữ cảnh, chẳng hạn:

~~~text
Principal X
    -- nhận role R -->
Tài nguyên A
    với điều kiện C
    theo quan sát của nguồn S
~~~

Bỏ scope hoặc điều kiện có thể biến một quyền giới hạn thành quyền toàn cục trong báo cáo. Bỏ loại quan hệ có thể làm lẫn “thành viên nhóm”, “có thể nhận role” và “đang dùng role”.

## 9. Từ dữ liệu phát hiện đến kết luận đặc quyền

Một connector có thể thấy tài khoản nằm trong nhóm quản trị. Đây là bằng chứng về một quan hệ, còn kết luận khả năng thực tế phụ thuộc quy tắc của nền tảng.

Cần xem xét:

- Quyền trực tiếp và quyền qua nhóm.
- Nhóm lồng nhau và kế thừa theo phạm vi.
- Role có thể kích hoạt nhưng chưa hoạt động.
- Chính sách tài nguyên và điều kiện truy cập.
- Cơ chế hạn chế hoặc từ chối.
- Khả năng đổi credential, sửa workload hoặc sửa chính sách của principal khác.

Không nên tính quyền hiệu lực bằng cách hợp mọi role một cách máy móc cho tất cả hệ thống.

### Ba lớp kết quả nên phân biệt

| Lớp | Ví dụ | Mức khẳng định |
| --- | --- | --- |
| Quan sát | Nguồn trả về quan hệ X là thành viên nhóm Y | Sự kiện dữ liệu đã đọc được |
| Phân tích | Theo mô hình nền tảng, quan hệ này có thể tạo quyền quản trị A | Kết luận có điều kiện và phạm vi |
| Xác nhận | Chủ sở hữu và bằng chứng kỹ thuật xác nhận đường quyền cần xử lý | Cơ sở cho quyết định vận hành |

Nếu thiếu dữ liệu nhóm lồng nhau hoặc điều kiện policy, phải đánh dấu giới hạn phân tích. Không biến “chưa thấy đường quyền” thành “không có đặc quyền”.

JIT cũng cần được đưa vào mô hình: chưa có role hoạt động ở thời điểm thu thập không có nghĩa không có khả năng nhận role đặc quyền khi kích hoạt.

## 10. Chu trình thu thập chịu được lỗi

Một chu trình khái niệm có thể gồm:

1. Đọc phạm vi được chấp nhận và nhận diện lần chạy.
2. Xác thực connector và hệ thống đích.
3. Kiểm tra khả năng đọc từng loại dữ liệu cần thiết.
4. Thu thập theo phân trang hoặc từng phần có giới hạn.
5. Kiểm tra và gửi kết quả cùng metadata nguồn.
6. Ghi trạng thái hoàn tất của từng phần phạm vi.
7. Đối soát theo mức đầy đủ đã chứng minh.
8. Phát cảnh báo hoặc công việc khi có lỗi, thay đổi hoặc khoảng trống.

### 10.1. Phân trang

Đọc trang đầu thành công không chứng minh đã đọc toàn bộ danh sách. Cần theo dõi trang tiếp theo hoặc cursor theo quy tắc của nguồn, xử lý lỗi giữa chừng và ghi rõ phần nào chưa hoàn thành.

Dữ liệu có thể thay đổi trong lúc đọc nhiều trang. Nếu nguồn không cung cấp snapshot nhất quán, cần ghi nhận cửa sổ thời gian thu thập và giới hạn của kết quả.

### 10.2. Giới hạn tải và retry

Connector cần tôn trọng giới hạn của nguồn, giảm đồng thời khi cần và có retry hữu hạn cho lỗi phù hợp.

Cần phân biệt lỗi tạm thời với:

- Không đủ quyền.
- Credential không còn hợp lệ.
- Sai phạm vi hoặc cấu hình.
- Dữ liệu không còn tương thích.
- Phản hồi không đạt yêu cầu xác thực hoặc kiểm tra.

Retry không giới hạn không làm một lỗi quyền trở thành lần thu thập đầy đủ.

### 10.3. Checkpoint và xử lý lặp

Checkpoint giúp tiếp tục từ phần đã xử lý nếu nguồn hỗ trợ. Chỉ ghi tiến độ đã được tiếp nhận bền vững theo thiết kế, tránh bỏ qua dữ liệu do đánh dấu quá sớm.

Kết quả có thể được gửi lại. Nơi tiếp nhận cần xử lý lặp theo ID đối tượng, lần chạy, phiên bản hoặc cơ chế tương đương, thay vì tạo bản ghi mới cho mọi lần nhận.

Cursor có thể hết hạn. Khi đó cần một phương án đối soát lại phù hợp, không tự giả định những thay đổi trong khoảng mất dữ liệu đã được bao phủ.

### 10.4. Lỗi từng phần

Một lần chạy có thể đọc được tài khoản nhưng không đọc được role. Trạng thái này phải là “thu thập một phần” đối với mục tiêu phân tích đặc quyền, thay vì báo thành công toàn bộ.

Nên theo dõi độ đầy đủ theo nguồn, tài nguyên và loại dữ liệu cần thiết. Một cờ thành công chung thường không đủ diễn tả chất lượng kết quả.

## 11. Đối soát trạng thái và xử lý đối tượng không còn xuất hiện

Đối soát so sánh các quan sát với kiểm kê trước đó và bản ghi PAM. Những trạng thái có thể gồm:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Mới phát hiện | Chưa có quan sát tương ứng trước đây |
| Đã liên kết PAM | Có ánh xạ được xác nhận với bản ghi quản lý |
| Chưa rõ trạng thái quản lý | Chưa tìm được ánh xạ đủ tin cậy |
| Thay đổi thuộc tính hoặc quyền | Có khác biệt cần đánh giá |
| Không còn được quan sát | Thiếu trong một hoặc nhiều lần thu thập |
| Dữ liệu đã cũ | Quan sát cuối không còn đáp ứng yêu cầu độ mới |
| Mâu thuẫn nguồn | Các nguồn đưa ra thông tin chưa thống nhất |

### Không còn thấy không đồng nghĩa đã bị xóa

Một tài khoản biến mất khỏi kết quả có thể do:

- Tài khoản đã bị xóa thật.
- Connector mất quyền đọc.
- Phạm vi bị thay đổi.
- Lỗi phân trang hoặc kết nối.
- Tài nguyên đang tạm ngừng.
- API thay đổi cách biểu diễn.
- Bộ lọc hoặc quy tắc chuẩn hóa có lỗi.

Chỉ đối soát sự vắng mặt khi đã biết lần thu thập đủ đầy cho phần phạm vi tương ứng. Có thể cần thêm bằng chứng, thời gian chờ hoặc xác nhận chủ sở hữu tùy hệ thống.

Đặc biệt, không tự xóa bản ghi vault hoặc vô hiệu hóa tài khoản chỉ vì một lần discovery không trả về đối tượng.

### Không đánh đồng “có bản ghi” và “được kiểm soát đầy đủ”

Một tài khoản có thể đã nằm trong vault nhưng:

- Credential không còn khớp với đích.
- Rotation chưa hoạt động.
- Chủ sở hữu chưa được xác nhận.
- Người dùng vẫn có đường truy cập trực tiếp bên ngoài PAM.
- Phiên hoặc credential cũ chưa được xử lý.

Đối soát nên mô tả chính xác mức quản lý đã được chứng minh, thay vì dùng một nhãn “managed” để che mọi khoảng trống.

## 12. Tài nguyên ngắn hạn và sự kiện đến không đúng thứ tự

Workload, job hoặc tài khoản tạm thời có thể tồn tại ngắn hơn chu kỳ thu thập. Vì vậy, một lịch quét định kỳ có thể bỏ lỡ chúng.

Một thiết kế có thể kết hợp:

- Sự kiện tạo, thay đổi và xóa.
- Truy vấn trạng thái hiện tại.
- Đối soát định kỳ để tìm phần bị bỏ lỡ.
- Liên kết workload với cấu hình, pipeline hoặc danh tính cấp trên khi có bằng chứng.

Sự kiện cũng có giới hạn: có thể đến muộn, đến lặp hoặc không đúng thứ tự. Nếu nhận một sự kiện cũ sau một trạng thái mới hơn, không nên tự động ghi đè trạng thái hiện tại.

Cần giữ thời điểm quan sát, thời điểm tiếp nhận và phiên bản hoặc thứ tự nguồn nếu có. Khi không thể xác định thứ tự chắc chắn, nên ghi mâu thuẫn hoặc yêu cầu xác minh thay vì đưa ra kết luận tùy ý.

Độ mới yêu cầu phụ thuộc loại tài nguyên. Không có một khoảng quét cố định phù hợp với mọi môi trường.

## 13. Chuyển phát hiện sang quy trình PAM

Kết quả discovery cần tạo được công việc cụ thể.

### 13.1. Xác nhận đối tượng và chủ sở hữu

Trước hết cần kiểm tra ánh xạ định danh, môi trường và người chịu trách nhiệm. Không suy chủ sở hữu chỉ từ tên tài khoản nếu chưa có căn cứ.

### 13.2. Đánh giá nhu cầu và rủi ro

Những câu hỏi chính gồm:

- Tài khoản còn cần cho nhiệm vụ nào?
- Quyền có vượt nhu cầu không?
- Có credential dài hạn hoặc dùng chung không?
- Có khả năng quản lý IAM, bí mật, audit hoặc tài nguyên nhạy cảm không?
- Đường sử dụng có thể chuyển sang JIT/JEA hay danh tính riêng không?
- Có dấu hiệu cần chuyển sang ứng phó sự cố không?

### 13.3. Chọn hướng xử lý

| Hướng | Điều kiện cần làm rõ |
| --- | --- |
| Đưa vào vault | Quyền quản lý, credential hiện tại, phụ thuộc và cách xác minh |
| Thu hẹp quyền | Nhu cầu, quyền hiệu lực và tác vụ cần giữ |
| Chuyển sang JIT/JEA | Cơ chế cấp, thực thi giới hạn và thu hồi ở đích |
| Tách tài khoản | Người dùng, workload và nhiệm vụ đang dùng chung |
| Thu hồi hoặc xóa | Không còn nhu cầu, phụ thuộc và phiên đang tồn tại |
| Ngoại lệ có thời hạn | Lý do, chủ sở hữu, biện pháp bù đắp và lần xem xét tiếp |

Discovery cung cấp đầu vào cho quyết định. Nó không thay thế xác nhận tác động vận hành, đặc biệt với tài khoản dịch vụ và credential dùng bởi nhiều hệ thống.

Nếu có dấu hiệu lạm dụng đang diễn ra, cần chuyển theo quy trình ứng phó thay vì chờ hết một đợt kiểm kê thông thường.

## 14. Ví dụ xuyên suốt: cơ sở dữ liệu production

Một tổ chức giao connector kiểm kê tài khoản và role trên 12 cơ sở dữ liệu đã đăng ký trong phạm vi.

Kết quả một lần chạy:

- 10 cơ sở dữ liệu hoàn tất các loại dữ liệu bắt buộc.
- 1 cơ sở dữ liệu đọc được tài khoản nhưng không đọc được role.
- 1 cơ sở dữ liệu không kết nối được.

Trong phần đã thu thập, có các phát hiện:

| Quan sát | Cách diễn giải phù hợp | Công việc tiếp theo |
| --- | --- | --- |
| Tài khoản A có role quản trị, chưa có ánh xạ PAM | Ứng viên đặc quyền chưa rõ trạng thái quản lý | Đối soát, xác nhận chủ sở hữu và nhu cầu |
| Tài khoản B có cùng tên với một tài khoản trên máy chủ | Hai đối tượng chưa đủ căn cứ để gộp | Dùng định danh nguồn và quan hệ được xác minh |
| Tài khoản C đã có bản ghi vault | Có liên kết kiểm kê | Kiểm tra trạng thái quản lý nếu mục tiêu yêu cầu |
| Tài khoản D không còn xuất hiện ở nguồn lỗi kết nối | Chưa có quan sát mới | Giữ thông tin cũ cùng trạng thái đã cũ, xử lý lỗi |
| Một ứng dụng tham chiếu tài khoản A | Có dấu hiệu phụ thuộc | Xác nhận với chủ sở hữu trước rotation hoặc thu hồi |

### 14.1. Hồ sơ một quan sát

Đây là **mô tả dữ liệu minh họa, không phải cấu hình có thể chạy cho một sản phẩm**. Hồ sơ không chứa credential.

~~~yaml
observation:
  run_reference: discovery-run-example
  source:
    system: database-management
    scope: production-group-a
  object:
    native_id: principal-example-42
    kind: database-account
    display_name: application-a-maintenance
    target_reference: database-a

observed_relations:
  - relation: assigned-role
    role_reference: maintenance-role
    resource_scope: database-a

collection:
  accounts: complete
  role_assignments: complete
  nested_relations: not-collected
  evidence_reference: protected-evidence-example

assessment:
  pam_mapping: unresolved
  privilege_analysis: requires-context
  owner_confirmation: pending
  permitted_next_step: review
~~~

Trường “complete” chỉ nói về loại dữ liệu và scope đã định nghĩa. Nó không khẳng định mọi đường đặc quyền ở mọi tầng hạ tầng đã được phát hiện.

### 14.2. Quyết định tiếp theo

Chủ sở hữu xác nhận tài khoản A phục vụ một tác vụ bảo trì hiếm, nhưng đang dùng chung với một job. Hướng xử lý có thể là tách danh tính, thu hẹp quyền và đưa từng đường sử dụng vào cơ chế phù hợp.

Trước khi đổi mật khẩu cần xác nhận job lấy credential thế nào, có cache không và thời điểm chạy. Discovery đã phát hiện quan hệ để đặt câu hỏi; chưa chứng minh đầy đủ mọi phụ thuộc.

Với hai nguồn chưa thu thập đầy đủ, cần khôi phục khả năng quan sát và chạy lại phần liên quan. Không báo đã kiểm kê đầy đủ 12 cơ sở dữ liệu.

## 15. Bảo vệ chính connector và dữ liệu tiếp nhận

Connector có thể nhìn thấy cấu trúc hạ tầng và có quyền đọc nhiều hệ thống. Đây là thành phần cần được bảo vệ như một dịch vụ nhạy cảm.

### 15.1. Giới hạn đường mạng và đích kết nối

Cần xác định nguồn nào connector được phép kết nối, cách kiểm tra danh tính máy chủ và nơi nhận kết quả.

Không dùng địa chỉ do dữ liệu đầu vào tùy ý cung cấp làm đích truy vấn tiếp theo. Metadata từ nguồn phải được coi là dữ liệu cần kiểm tra; nó không phải lệnh yêu cầu connector mở rộng phạm vi.

### 15.2. Kiểm tra dữ liệu không đáng tin cậy

Tên tài khoản, nhãn và mô tả có thể chứa nội dung bất thường hoặc gây hiểu nhầm. Lớp tiếp nhận cần kiểm tra kiểu, kích thước, cấu trúc và cách hiển thị.

Không thực thi chuỗi tên hoặc mô tả như mã lệnh. Không coi một nhãn “approved” từ hệ thống đích là bằng chứng đã được người có thẩm quyền phê duyệt trong PAM.

### 15.3. Bảo vệ triển khai và cập nhật

Cần kiểm soát ai được sửa mã, cấu hình, danh tính và endpoint của connector. Một người sửa được connector có thể đổi dữ liệu gửi về hoặc lạm dụng quyền của danh tính thu thập.

Phiên bản connector và schema nên được ghi nhận cùng lần chạy để giải thích thay đổi kết quả sau cập nhật.

### 15.4. Bảo vệ kho kiểm kê

Dù không chứa mật khẩu, kho kiểm kê có thể mô tả nơi tồn tại tài khoản mạnh và quan hệ truy cập. Cần giới hạn người xem, người xuất dữ liệu và người sửa kết quả.

Bằng chứng gốc hoặc tham chiếu đến bằng chứng phải được bảo vệ để có thể kiểm tra lại kết luận khi cần.

## 16. Theo dõi chất lượng và bằng chứng

### 16.1. Chỉ số phải có mẫu số rõ ràng

Với ví dụ 12 cơ sở dữ liệu:

- Tỷ lệ hoàn tất các loại dữ liệu bắt buộc trong danh sách được giao là **10/12**.
- Một nguồn thu thập một phần và một nguồn chưa quan sát được phải được nêu riêng.
- Không thể suy ra tỷ lệ bao phủ toàn bộ hạ tầng nếu chưa có danh sách phạm vi đáng tin cậy.

Cũng cần phân biệt số tài khoản được phát hiện, số tài khoản được xác nhận đặc quyền và số tài khoản đã được PAM kiểm soát theo tiêu chí cụ thể. Đây là các tập khác nhau.

### 16.2. Những chỉ số hữu ích

| Chỉ số | Ý nghĩa |
| --- | --- |
| Phạm vi thu thập hoàn tất | Mức đáp ứng mục tiêu quan sát đã định nghĩa |
| Tuổi của quan sát | Độ mới của dữ liệu theo nguồn và đối tượng |
| Lỗi quyền hoặc xác thực | Khoảng trống do danh tính connector |
| Lỗi phân trang hoặc dữ liệu | Rủi ro danh sách không đầy đủ |
| Đối tượng chưa rõ chủ sở hữu | Công việc cần xác nhận trách nhiệm |
| Ánh xạ chưa chắc chắn | Rủi ro gộp nhầm hoặc bỏ sót khi đối soát |
| Phát hiện chờ xử lý | Khoảng cách giữa discovery và thay đổi kiểm soát |
| Thay đổi đặc quyền chưa được review | Phần cần xem xét theo sự kiện |

Không tối ưu bằng cách chỉ tăng số bản ghi. Nhiều dữ liệu trùng lặp hoặc cũ có thể làm báo cáo lớn hơn nhưng ít đáng tin cậy hơn.

### 16.3. Bằng chứng của một lần chạy

Nên liên kết được:

1. Phạm vi và cấu hình được chấp nhận.
2. Danh tính, phiên bản connector và thời gian chạy.
3. Nguồn đã truy vấn và phần dữ liệu hoàn tất.
4. Lỗi, khoảng trống và giới hạn quan sát.
5. Kết quả chuẩn hóa, ánh xạ và quy tắc phân tích.
6. Phát hiện tạo ra và quyết định xử lý tiếp theo.

Log cần đủ để giải thích kết quả nhưng không chứa credential, token truy cập hoặc nội dung nhạy cảm không cần thiết.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Cấp quản trị toàn cục để dễ discovery | Tăng phạm vi ảnh hưởng khi connector bị kiểm soát | Thiết kế quyền theo thao tác và nguồn |
| Gộp tài khoản theo tên | Liên kết nhầm principal và quyền | Dùng định danh nguồn, scope và bằng chứng |
| Chỉ đọc trang đầu | Thiếu đối tượng nhưng báo thành công | Theo dõi phân trang và độ đầy đủ |
| Xem lỗi quyền là danh sách rỗng | Kết luận sai rằng không có tài khoản | Phân biệt lỗi, không quan sát được và kết quả rỗng hợp lệ |
| Tự xóa bản ghi khi đối tượng không xuất hiện | Mất thông tin quản lý hoặc gây gián đoạn | Đối soát sự vắng mặt với phạm vi đã hoàn tất |
| Coi mọi role là quyền đang hoạt động | Đánh giá sai điều kiện hoặc trạng thái JIT | Giữ loại quan hệ và quy tắc nền tảng |
| Thu thập cả giá trị bí mật | Tạo thêm nơi lộ credential | Chỉ lấy metadata cần thiết |
| Tự rotation ngay sau phát hiện | Có thể phá vỡ bên phụ thuộc chưa biết | Chuyển sang workflow có xác nhận |
| Chỉ đo số tài khoản tìm thấy | Không thể đánh giá độ bao phủ và độ mới | Định nghĩa scope, chất lượng và mẫu số |
| Không lưu nguồn gốc kết luận | Khó kiểm toán hoặc điều tra sai lệch | Liên kết quan sát, quy tắc và quyết định |

## 18. Bài tập tự đánh giá

Một connector chạy mỗi đợt đều trả về ít tài khoản hơn. Nhóm vận hành định tự động xóa các bản ghi không còn thấy khỏi vault. Trong cùng thời gian đó, danh tính connector vừa bị thay đổi quyền; một API chỉ trả được trang đầu và một số workload có vòng đời ngắn.

Hãy xác định:

1. Vì sao số tài khoản giảm chưa chứng minh đặc quyền đã được giảm?
2. Cần bằng chứng gì trước khi kết luận một tài khoản đã bị xóa?
3. Những phần nào phải đánh dấu là quan sát không đầy đủ?
4. Có thể cải thiện việc phát hiện workload ngắn hạn thế nào?
5. Vì sao không nên xóa bản ghi vault tự động theo kết quả này?

### Gợi ý phân tích

**Số lượng:** có thể giảm do thiếu quyền, lỗi phân trang hoặc bỏ lỡ đối tượng ngắn hạn. Đó là giảm khả năng quan sát, chưa chắc là thay đổi thật ở hệ thống đích.

**Bằng chứng xóa:** cần lần thu thập đủ đầy trong đúng phạm vi và thêm xác nhận phù hợp, chẳng hạn sự kiện nguồn hoặc kiểm tra trạng thái theo cơ chế được phép.

**Độ đầy đủ:** phải phản ánh theo nguồn và loại dữ liệu. Không dùng một trạng thái thành công chung để che những phần đã thất bại.

**Workload ngắn hạn:** có thể kết hợp sự kiện, dữ liệu điều phối và đối soát định kỳ, đồng thời xử lý độ trễ, trùng lặp và thứ tự.

**Bản ghi vault:** xóa khỏi kho không thu hồi tài khoản ở đích, có thể làm mất tham chiếu cần quản lý và khiến xử lý sự cố khó hơn. Quyết định cần được đưa qua quy trình quản lý vòng đời.

## 19. Những điểm cần ghi nhớ

- Discovery connector cung cấp quan sát về tài nguyên, danh tính và quan hệ đặc quyền trong một phạm vi cụ thể.
- Phải tách phát hiện, phân tích quyền, đối soát PAM và hành động thay đổi tài khoản.
- Least privilege áp dụng cho chính connector, danh tính của nó và các đường truy cập vault, mạng, dữ liệu.
- Định danh nguồn và ngữ cảnh quan hệ quan trọng hơn việc so tên tài khoản.
- Lỗi, phân trang, dữ liệu cũ và quan sát một phần phải được thể hiện trong kết quả.
- Không còn thấy một đối tượng không tự chứng minh nó đã bị xóa; có bản ghi PAM cũng không tự chứng minh mọi kiểm soát đã hiệu lực.
- Kết quả có ích cần dẫn đến công việc có chủ sở hữu, xác nhận phụ thuộc và bằng chứng có thể truy vết.
