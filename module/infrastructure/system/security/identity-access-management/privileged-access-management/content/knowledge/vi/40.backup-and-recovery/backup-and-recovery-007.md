# Recovery order: thứ tự khôi phục hệ thống PAM

## Mục tiêu bài học

Một bản sao lưu có thể chứa đủ dữ liệu nhưng vẫn không đưa hệ thống Privileged Access Management (PAM) trở lại trạng thái sử dụng được. Kho mật khẩu khởi động thành công chưa chứng minh rằng khóa giải mã còn đúng, danh tính người dùng còn đáng tin, quyền truy cập còn hiệu lực hoặc credential trong kho khớp với credential trên hệ thống đích.

**Recovery order** là thứ tự khôi phục các thành phần và mở lại từng năng lực theo quan hệ phụ thuộc, mức ưu tiên nghiệp vụ và điều kiện an toàn. Trong PAM, kết quả cần đạt không chỉ là “dịch vụ đã chạy”, mà là:

- Người đúng được cấp đúng quyền, trong đúng khoảng thời gian.
- Credential được sử dụng là credential hiện hành và không bị lộ trong quá trình khôi phục.
- Phiên đặc quyền có thể được kiểm soát, dừng và truy vết.
- Các thành phần cũ không còn quyền ghi hoặc phát hành quyền song song.
- Mỗi năng lực được mở lại đều có bằng chứng kiểm chứng và người chịu trách nhiệm.

Bài học thuộc chương **Backup và khôi phục**, tập trung vào cách xây dựng thứ tự phục hồi cho vault, chính sách quyền, xác thực, luân chuyển credential, kết nối hệ thống đích và giám sát phiên. Các trình tự minh họa là mô hình thiết kế; thao tác khôi phục vật lý và bộ dữ liệu nhất quán phải tuân theo kiến trúc, cơ chế mã hóa và runbook của hệ thống thực tế.

## 1. Phân biệt thứ tự restore và thứ tự mở lại quyền

Trong một sự cố PAM có ít nhất ba tiến trình liên quan nhưng không đồng nhất.

| Tiến trình | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Restore dữ liệu | Phải đưa những dữ liệu nào về môi trường phục hồi? | Bản sao vault, cơ sở dữ liệu cấu hình, bản ghi phiên, metadata mã hóa |
| Khôi phục năng lực | Năng lực nào đã có đủ phụ thuộc để vận hành? | Giải mã một mục thử, xác thực người dùng phục hồi, kiểm tra quyền |
| Mở lại sử dụng | Nhóm nào được phép dùng năng lực đó và trong phạm vi nào? | Chỉ nhóm phục hồi, nhóm pilot, rồi từng nhóm production |

Có thể restore một cơ sở dữ liệu mã hóa trước khi khôi phục quyền truy cập vào khóa. Tuy nhiên, dịch vụ phụ thuộc vào dữ liệu đó chưa được phép mở cho người dùng cho tới khi việc giải mã, kiểm tra tính toàn vẹn và xác nhận nguồn khóa hoàn tất.

Tương tự, dữ liệu phiên cũ có thể tiếp tục được phục hồi ở nền trong khi các phiên mới đã có tuyến ghi bằng chứng riêng. Điều đó chỉ hợp lệ khi tuyến ghi mới đã được kiểm chứng và phương án thiếu lịch sử tạm thời đã được chấp thuận cho đúng phạm vi. Không được để phiên mới diễn ra mà không có bằng chứng chỉ vì kho lịch sử chưa restore xong.

### 1.1. Khôi phục dữ liệu không khôi phục sự thật hiện tại

Giả sử:

- 01:00: backup vault chứa credential phiên bản 18.
- 01:20: hệ thống xoay credential trên máy đích sang phiên bản 19.
- 01:40: PAM gặp sự cố.
- 02:10: vault được restore từ backup 01:00.

Vault có thể đọc được phiên bản 18, nhưng máy đích đang chấp nhận phiên bản 19. Nếu chỉ kiểm tra trạng thái dịch vụ, đội phục hồi có thể mở lại một kho credential hoạt động về kỹ thuật nhưng không sử dụng được.

Rủi ro tương tự xuất hiện với quyền:

- Một người dùng bị thu hồi quyền lúc 01:15.
- Backup chính sách được chụp lúc 01:00.
- Restore nguyên trạng có thể đưa quyền cũ quay trở lại.

Vì vậy, thứ tự phục hồi phải bao gồm **đối soát trạng thái mới hơn bản backup** trước khi mở quyền: thay đổi credential, thu hồi quyền, phê duyệt truy cập, ngoại lệ khẩn cấp và danh tính dịch vụ.

### 1.2. Recovery order cần thể hiện điều kiện, không chỉ số thứ tự

Danh sách “database → vault → connector → người dùng” thiếu thông tin quan trọng. Nó không giải thích khi nào database đáng tin, khi nào connector được phép chạy tác vụ tự động hoặc khi nào người dùng được cấp quyền.

Một bước khôi phục hữu ích phải có:

1. Phụ thuộc đầu vào đã được xác minh.
2. Thao tác khôi phục trong phạm vi cụ thể.
3. Bằng chứng kiểm tra đầu ra.
4. Điều kiện cho phép chuyển bước.
5. Cách giữ hệ thống ở trạng thái hạn chế nếu kiểm tra thất bại.

Một dịch vụ có thể đã được restore nhưng vẫn ở trạng thái **cách ly** hoặc **chỉ phục vụ đội phục hồi**. Đây là trạng thái vận hành có chủ đích, không phải bằng chứng đã hoàn tất phục hồi.

## 2. Xây dựng đồ thị phụ thuộc

Thứ tự khôi phục xuất phát từ một đồ thị phụ thuộc. Mỗi nút nên biểu diễn một năng lực đủ nhỏ để kiểm chứng; mỗi cạnh thể hiện “B cần kết quả đã được xác minh của A”.

Ví dụ khái niệm:

~~~text
Quyền phê duyệt phục hồi + bộ công cụ sạch
                    |
                    v
Môi trường phục hồi cách ly + mạng quản trị + thời gian đáng tin
          |                    |                  |
          v                    v                  v
Dữ liệu backup đã xác minh   Vật liệu khóa    Tuyến ghi bằng chứng mới
          |                    |
          +----------+---------+
                     v
        Vault / trạng thái dữ liệu nhất quán
                     |
                     v
      Chính sách hiện hành + xác thực phục hồi
                     |
                     v
      Connector cách ly + đối soát hệ thống đích
                     |
                     v
       Truy cập pilot có kiểm soát và ghi phiên
                     |
                     v
       Mở rộng theo nhóm dịch vụ ưu tiên
~~~

Sơ đồ không ngụ ý mọi sản phẩm đều cần đúng các thành phần hoặc đúng thứ tự restore vật lý như nhau. Chẳng hạn, một kiến trúc có HSM bên ngoài khác với kiến trúc sử dụng bộ vật liệu phục hồi khóa được bảo vệ riêng. Điều bất biến là **năng lực sử dụng dữ liệu mật phải có nguồn khóa hợp lệ và các kiểm chứng cần thiết trước khi mở**.

### 2.1. Phụ thuộc kỹ thuật

Các phụ thuộc thường phải khảo sát gồm:

- Tên miền, phân giải tên và định tuyến giữa thành phần PAM với hệ thống đích.
- Nguồn thời gian phục vụ chứng thư, token, thời hạn JIT và thứ tự sự kiện.
- Lưu trữ, cơ sở dữ liệu và bộ dữ liệu nhất quán của vault.
- Khóa, chứng thư, chuỗi tin cậy và quyền sử dụng vật liệu khóa.
- Dịch vụ danh tính, MFA hoặc cơ chế xác thực phục hồi thay thế.
- Session broker, gateway, agent và connector.
- Kho ghi phiên, hàng đợi sự kiện và nơi tiếp nhận log.
- Các ứng dụng đang phụ thuộc vào secret được PAM phân phối.

Không cần mở toàn bộ mạng production để kiểm tra một phụ thuộc. Có thể kiểm chứng trên một tuyến được phép, một máy đích thử nghiệm và một danh tính phục hồi có quyền giới hạn.

### 2.2. Phụ thuộc an toàn

Một thành phần có thể không cần thiết để tiến trình chạy nhưng vẫn cần thiết để cho phép sử dụng.

Ví dụ:

- Broker có thể tạo phiên khi recorder chưa sẵn sàng, nhưng chính sách yêu cầu ghi phiên thì phiên đó chưa được mở.
- Vault có thể phát hành secret trước khi hoàn tất rà soát quyền bị thu hồi, nhưng việc phát hành có thể cấp lại quyền sai.
- Connector có thể hoạt động trước khi cô lập cụm cũ, nhưng hai bên có thể cùng xoay credential và làm mất nhất quán.
- Tác vụ rotation có thể đăng nhập thành công, nhưng chưa được chạy hàng loạt nếu chưa biết ứng dụng nào đang giữ secret cũ.

Vì vậy, cạnh phụ thuộc trong recovery order phải bao gồm cả điều kiện **được phép sử dụng**, không chỉ kết nối kỹ thuật.

### 2.3. Phụ thuộc nghiệp vụ

Nhóm máy chủ thanh toán, hệ thống điều phối hạ tầng và máy thử nghiệm có thể cùng dùng PAM nhưng không có cùng thời hạn phục hồi.

Ưu tiên nghiệp vụ quyết định chọn nhánh nào trước trong đồ thị, chứ không cho phép bỏ qua tiền đề an toàn của nhánh đó. Một dịch vụ quan trọng vẫn cần cơ chế xác thực, credential hiện hành và bằng chứng tương ứng trước khi được mở.

Nên mô tả đơn vị phục hồi bằng năng lực cụ thể, chẳng hạn:

> Đội trực được mở phiên quản trị giới hạn tới ba máy chủ cơ sở dữ liệu trọng yếu qua gateway đã ghi phiên, với quyền JIT hết hạn sau cửa sổ xử lý được phê duyệt.

Câu này có thể kiểm chứng tốt hơn “PAM production đã lên”.

## 3. Xử lý vòng phụ thuộc trước khi sự cố xảy ra

Một trong những vòng phụ thuộc khó xử lý nhất là:

~~~text
Cần PAM để lấy tài khoản quản trị dịch vụ danh tính
          ^
          |
Dịch vụ danh tính phải hoạt động để đăng nhập PAM
~~~

Vòng khác có thể xuất hiện giữa vault và hạ tầng khóa, giữa PAM và nền tảng ảo hóa, hoặc giữa kho backup và tài khoản dịch vụ được lưu trong chính vault đang hỏng.

Nếu chỉ phát hiện vòng này trong sự cố, đội phục hồi thường bị ép mở quyền quá rộng hoặc tìm credential qua kênh không được kiểm soát.

### 3.1. Tạo một điểm khởi đầu độc lập có kiểm soát

Cần xác định trước một đường khởi động phục hồi, có thể gồm:

- Danh tính phục hồi không phụ thuộc hoàn toàn vào dịch vụ đang bị khôi phục.
- Vật liệu phục hồi được lưu riêng theo cơ chế bảo vệ đã thiết kế.
- Runbook khả dụng khi PAM, thư mục danh tính hoặc hệ thống quản lý tài liệu chính bị gián đoạn.
- Người giữ quyền phê duyệt và người giữ vật liệu phục hồi theo phân tách trách nhiệm.
- Thiết bị hoặc môi trường sạch để thực hiện bước đầu.
- Tuyến ghi bằng chứng tạm thời được bảo vệ cho giai đoạn chưa có đầy đủ log tập trung.

Đường khởi động độc lập không đồng nghĩa với một tài khoản quản trị luôn mở cho mọi mục đích. Quyền sử dụng phải bị giới hạn bởi sự kiện phục hồi, phạm vi tác động, thời hạn và yêu cầu hậu kiểm.

Không đưa giá trị credential, khóa giải mã hay recovery code vào runbook. Runbook ghi nơi quản lý, điều kiện truy xuất và người được phép thực hiện; vật liệu mật nằm trong cơ chế bảo vệ riêng.

### 3.2. Giới hạn quyền bootstrap theo từng bước

Tài khoản có khả năng khởi tạo vault không mặc nhiên cần quyền quản trị mọi máy đích. Người có quyền lấy bộ backup không mặc nhiên được giải mã toàn bộ secret. Một người kiểm tra tuyến ghi phiên cũng không cần đọc nội dung credential.

Thiết kế quyền phục hồi nên chỉ rõ:

| Vai trò | Nhiệm vụ | Ranh giới cần giữ |
|---|---|---|
| Người chỉ huy phục hồi | Xác định phạm vi và cho phép chuyển giai đoạn | Không tự thay mọi bằng chứng kiểm tra kỹ thuật |
| Người quản lý backup | Cấp đúng tập backup và thông tin nguồn gốc | Không tự cấp quyền sử dụng secret trong vault |
| Người quản lý khóa | Thực hiện nghi thức phục hồi khóa | Không đưa khóa vào ticket hoặc log |
| Kỹ sư PAM | Restore và kiểm chứng các năng lực PAM | Chỉ mở các nhóm đã được phê duyệt |
| Chủ hệ thống đích | Xác nhận credential và tác động ứng dụng | Không tự reset hàng loạt ngoài kế hoạch |
| Người giám sát bằng chứng | Xác nhận sự kiện và phiên được lưu | Phát hiện khoảng trống và sai lệch thời gian |

Trong tổ chức nhỏ, một người có thể đảm nhiệm nhiều nhiệm vụ, nhưng các quyền nhạy cảm và quyết định ngoại lệ vẫn cần được nhận diện rõ. Không nên làm mờ trách nhiệm bằng một tài khoản dùng chung không có dấu vết.

## 4. Một trình tự khôi phục PAM theo các cổng kiểm chứng

Bảng sau mô tả thứ tự mở năng lực. Các công việc chuẩn bị độc lập có thể chạy song song; chỉ chuyển cổng khi các phụ thuộc của cổng đó đã đạt.

| Giai đoạn | Công việc chính | Bằng chứng để chuyển tiếp |
|---|---|---|
| 0. Kiểm soát sự cố | Xác định phạm vi ảnh hưởng, ngăn thay đổi trái phép, cô lập bên cũ có thể ghi | Phạm vi và người chỉ huy được xác nhận; không còn bên cũ có thể tự ý ghi vào tài nguyên được phục hồi |
| 1. Thiết lập nền phục hồi | Chuẩn bị môi trường sạch, kết nối giới hạn, thời gian, định danh phục hồi và tuyến log ban đầu | Kiểm tra đường vào, quyền bootstrap và nơi lưu bằng chứng đạt |
| 2. Kiểm chứng đầu vào | Xác minh backup, vật liệu khóa, chứng thư và bộ dữ liệu cần phục hồi | Nguồn gốc, tính toàn vẹn và sự tương thích được kiểm tra theo cơ chế thực tế |
| 3. Phục hồi dữ liệu lõi | Restore bộ dữ liệu nhất quán, đưa vault lên trong phạm vi cách ly | Dữ liệu đọc được, một phép thử giải mã được kiểm soát đạt, không có ghi đồng thời ngoài ý muốn |
| 4. Phục hồi điều khiển quyền | Nạp và đối soát chính sách, danh tính, phê duyệt, quyền bị thu hồi | Thử cho phép và từ chối đúng; quyền cũ không tự quay lại |
| 5. Phục hồi kiểm soát phiên | Kiểm tra broker, recorder, tuyến sự kiện và lưu trữ phiên mới | Phiên thử có đủ bằng chứng, gắn đúng người và hệ thống đích |
| 6. Đối soát credential và connector | Kiểm tra trạng thái mục tiêu, kết nối từng nhóm, kiểm soát tác vụ tự động | Credential hiện hành được xác nhận hoặc được hòa giải an toàn; connector chỉ hoạt động trong phạm vi đã mở |
| 7. Mở pilot và từng đợt | Mở nhóm nhỏ rồi mở rộng theo ưu tiên | Kiểm thử trọn luồng đạt; chủ dịch vụ chấp nhận phạm vi mở |
| 8. Kết thúc phục hồi | Thu hồi bootstrap, xử lý quyền tạm, đối soát backlog và cập nhật backup | Đã trở về vận hành có kiểm soát; ngoại lệ còn lại có chủ sở hữu và thời hạn |

Giai đoạn 5 và 6 có thể có phần việc chạy song song. Ví dụ, đội recorder kiểm tra lưu phiên với mục tiêu thử trong khi đội credential kiểm tra metadata của nhóm production. Tuy nhiên, việc mở một phiên quản trị production phải chờ đủ cả hai nhánh mà chính sách yêu cầu.

### 4.1. Cổng 0: kiểm soát bên cũ trước khi đưa bên mới hoạt động

Nếu node PAM cũ, connector cũ hoặc tác vụ rotation cũ có thể tự hoạt động trở lại, việc khôi phục bên mới có thể tạo hai nguồn điều khiển.

Cần xử lý quyền ghi và đường truy cập của bên cũ bằng biện pháp phù hợp với kiến trúc: cô lập mạng, thu hồi quyền điều khiển, vô hiệu tác vụ hoặc cơ chế fencing đã được kiểm chứng. Không chỉ dựa vào nhận định “máy cũ có vẻ đang tắt”.

Kiểm tra tối thiểu:

- Bên cũ có còn khả năng đổi credential trên máy đích không?
- Hai môi trường có đang chia sẻ cùng hàng đợi hoặc lịch tác vụ không?
- Secret provider cũ có còn phát hành credential không?
- Một tuyến DNS hoặc cân bằng tải có thể đưa người dùng trở lại môi trường cũ không?
- Tài khoản dịch vụ cũ còn quyền ghi vào cơ sở dữ liệu hay lưu trữ phục hồi không?

Khi chưa loại bỏ được ghi đồng thời, nên giữ môi trường mới ở chế độ cách ly và tiếp tục điều tra phạm vi đó.

### 4.2. Cổng 1 và 2: tạo nền đáng tin và chọn điểm phục hồi

Cần phân biệt hai câu hỏi:

1. Backup có nguyên vẹn so với thời điểm được tạo không?
2. Trạng thái trong backup có phù hợp để phục hồi không?

Checksum có thể giúp phát hiện thay đổi dữ liệu khi có giá trị đối chiếu đáng tin. Nó không tự chứng minh backup được tạo trước khi hệ thống bị xâm nhập, cũng không chứng minh các quyền bên trong còn phù hợp.

Việc chọn điểm phục hồi phải dựa vào thời điểm sự cố, nguồn gốc bản sao, kiểm tra tính nhất quán và thông tin điều tra sẵn có. Nếu phạm vi ảnh hưởng chưa rõ, không tự gán nhãn “sạch” chỉ vì backup restore thành công.

Dữ liệu, khóa và metadata cần được đối chiếu như một bộ:

- Backup nào gắn với phiên bản cấu hình và sơ đồ dữ liệu nào?
- Khóa hoặc metadata mã hóa nào cần để đọc dữ liệu đó?
- Khóa có bị thu hồi, nghi lộ hoặc không còn được phép sử dụng không?
- Chứng thư và danh tính dịch vụ nào cần được cấp mới thay vì khôi phục nguyên trạng?
- Cơ chế phục hồi được hỗ trợ yêu cầu trình tự vật lý nào?

Không tự thay khóa, ghép tùy ý các snapshot hoặc sao chép file database riêng lẻ để “làm cho dịch vụ lên”. Các thao tác đó có thể phá tính nhất quán hoặc làm dữ liệu mất khả năng giải mã.

### 4.3. Cổng 3: chứng minh vault sử dụng được trong phạm vi giới hạn

Sau khi dịch vụ lõi chạy, phép thử nên xác nhận năng lực, không chỉ kiểm tra cổng mạng.

Ví dụ các kiểm tra có kiểm soát:

- Đọc được cấu hình và metadata dự kiến.
- Giải mã một mục thử đã được chuẩn bị cho kiểm tra phục hồi.
- Người không có quyền không đọc được mục đó.
- Một thao tác hợp lệ và một thao tác bị từ chối đều tạo sự kiện.
- Các thao tác ghi mới không làm phát sinh xung đột với node cũ.
- Không có tác vụ tự động nào chạy ngoài danh sách được cho phép.

Không xuất hàng loạt secret để kiểm tra khả năng giải mã. Dùng phạm vi tối thiểu, tránh đưa giá trị mật vào output hoặc ảnh chụp bằng chứng.

### 4.4. Cổng 4: phục hồi trạng thái quyền hiện hành

Chính sách từ backup là dữ liệu lịch sử. Trước khi mở cho người dùng, cần đối soát với nguồn thẩm quyền còn đáng tin:

- Người đã nghỉ việc hoặc bị đình chỉ.
- Nhóm đã thay đổi thành viên.
- Quyền được thu hồi sau thời điểm backup.
- Yêu cầu JIT và phê duyệt đã hết hạn.
- Ngoại lệ break-glass được tạo hoặc đóng trong khoảng mất dữ liệu.
- Danh tính dịch vụ đã được thay thế hay thu hồi.

Nếu chưa lấy được đầy đủ thay đổi, có thể mở một tập quyền phục hồi nhỏ đã được xác nhận độc lập. Không mặc nhiên chấp nhận toàn bộ nhóm quyền cũ.

Đặc biệt, không làm sống lại một quyền JIT chỉ vì bản ghi phê duyệt vẫn có trong backup. Quyết định cấp quyền phải xét thời hạn, thời gian hiện tại, việc thu hồi và ngữ cảnh sử dụng. Một phê duyệt đã hết hạn cần được xử lý như đã hết hạn.

### 4.5. Cổng 5: bằng chứng phải sẵn sàng trước phiên đặc quyền

Với tuyến truy cập yêu cầu ghi phiên, một phiên thử cần chứng minh:

1. Người dùng và danh tính đích được ánh xạ đúng.
2. Sự kiện phê duyệt hoặc lý do khẩn cấp được liên kết với phiên.
3. Nội dung ghi phiên hoặc bằng chứng lệnh được lưu theo loại truy cập.
4. Bản ghi có thể tìm lại và đọc bằng quyền kiểm toán phù hợp.
5. Kết thúc hoặc chấm dứt phiên có dấu vết.
6. Người dùng phiên không có quyền tự sửa hay xóa bằng chứng của mình.

Nếu hệ thống log tập trung chưa hoạt động, một tuyến lưu cục bộ được bảo vệ có thể là phương án tạm theo chính sách đã chấp thuận. Phải kiểm tra dung lượng, quyền truy cập, tính toàn vẹn, đồng bộ về sau và hành vi khi nơi lưu đầy.

Không coi “agent đang chạy” là bằng chứng rằng phiên thực tế đã được ghi.

## 5. Đối soát credential là một giai đoạn riêng

Credential là nơi recovery order thường thất bại dù hạ tầng đã phục hồi. Điểm khó nằm ở việc dữ liệu secret trong backup và trạng thái trên hệ thống đích có thể khác nhau.

### 5.1. Phân loại trước khi hành động

| Trạng thái xác định được | Hành động phù hợp | Hành động cần tránh |
|---|---|---|
| Vault và đích khớp, credential không nghi lộ | Kiểm tra có giới hạn rồi cho phép nhóm tương ứng sử dụng | Đổi hàng loạt chỉ để tạo cảm giác đã phục hồi |
| Vault cũ hơn đích | Hòa giải theo cơ chế được hỗ trợ hoặc thay credential có điều phối | Ghi đè đích bằng giá trị cũ trong backup |
| Chưa biết có khớp hay không | Cách ly nhóm, điều tra thay đổi và thử theo giới hạn chống khóa tài khoản | Thử nhiều secret liên tiếp trên toàn bộ tài khoản |
| Credential nghi bị lộ | Thực hiện quy trình thay thế, thu hồi và kiểm tra phụ thuộc | Xem restore là đã loại bỏ rủi ro lộ secret |
| Vault đã đổi nhưng ứng dụng còn dùng bản cũ | Cập nhật theo cơ chế phân phối đã thiết kế và kiểm tra ứng dụng | Chỉ xác nhận đăng nhập quản trị rồi bỏ qua ứng dụng |
| Chỉ có token hoặc chứng thư đã hết hạn | Xin cấp lại theo nguồn thẩm quyền và chính sách hiện hành | Giả định restore làm token hoặc chứng thư có hiệu lực trở lại |

Có những secret không thể đọc ngược từ hệ thống đích. Khi đó, “đối soát” không nhất thiết là so sánh hai chuỗi ký tự. Có thể cần kiểm tra phiên bản đáng tin, xác thực thử có giới hạn hoặc thiết lập credential mới qua cơ chế quản trị được cho phép.

Không ghi giá trị credential vào bảng đối soát. Chỉ ghi mã tài khoản, hệ thống đích, nguồn xác nhận, trạng thái, thời điểm và người thực hiện.

### 5.2. Trình tự xử lý một nhóm credential

Một nhóm nên đủ nhỏ để kiểm soát phạm vi sự cố. Ví dụ: tài khoản quản trị của một cụm máy chủ hoặc một danh tính dịch vụ cùng các ứng dụng tiêu thụ secret của nó.

Trình tự minh họa:

1. Xác định owner của tài khoản và các thành phần tiêu thụ credential.
2. Chặn tác vụ rotation cũ và tác vụ thử lại tự động ngoài kế hoạch.
3. Kiểm tra lịch sử thay đổi sau thời điểm backup từ các nguồn còn đáng tin.
4. Chọn cách xác nhận hoặc thiết lập trạng thái hiện hành.
5. Thực hiện với quyền tối thiểu và giới hạn tác động đã thống nhất.
6. Xác nhận máy đích chấp nhận credential dự kiến.
7. Xác nhận ứng dụng hoặc broker sử dụng được credential qua đường đi thực tế.
8. Xác nhận ghi bằng chứng và xử lý trạng thái cũ theo cơ chế được hỗ trợ.
9. Mới cho phép tác vụ rotation tự động hoạt động lại trong nhóm đó.

Nếu trạng thái vault và đích lệch sau một thao tác thay đổi bị gián đoạn, giữ nhóm ở trạng thái hạn chế. Dùng quy trình hòa giải của nền tảng để đưa về trạng thái nhất quán; không tự suy ra rằng rollback mật khẩu là lựa chọn an toàn.

### 5.3. Không đồng nhất rollback dịch vụ với rollback secret

Một cấu hình gateway có thể quay về bản đã kiểm chứng. Credential đã đổi trên máy đích không thể được xử lý như một file cấu hình thông thường.

Việc đặt lại secret cũ có thể:

- Đưa một giá trị từng bị lộ quay lại sử dụng.
- Xung đột chính sách lịch sử mật khẩu.
- Làm các ứng dụng đang dùng giá trị mới mất kết nối.
- Gây khóa tài khoản do thử lại bằng nhiều giá trị.
- Phá bằng chứng về trạng thái credential trong sự cố.

Vì thế, rollback kế hoạch mở quyền thường có nghĩa là **đóng phạm vi vừa mở, thu hồi quyền tạm và giữ bằng chứng**, không có nghĩa là tự động quay credential về giá trị trước đó.

## 6. Mở hệ thống theo từng lát cắt dịch vụ

Một lát cắt phục hồi bao gồm đủ thành phần để cung cấp một năng lực có ích từ đầu đến cuối.

Ví dụ, lát cắt “quản trị cơ sở dữ liệu trọng yếu” có thể cần:

- Một nhóm người trực đã được xác minh.
- Một chính sách JIT giới hạn đúng máy và đúng thời hạn.
- Kho credential đã đối soát cho nhóm mục tiêu.
- Một đường broker hoặc gateway hoạt động.
- Tuyến ghi phiên và sự kiện đã kiểm thử.
- Quy trình chấm dứt quyền khi hết cửa sổ phục hồi.

Khôi phục riêng tất cả gateway chưa chắc giúp người trực hoàn thành công việc. Ngược lại, một gateway cùng một tập credential và quyền đúng có thể phục vụ lát cắt ưu tiên trước khi toàn bộ hệ thống quay lại.

### 6.1. Chọn nhóm pilot

Nhóm pilot nên đại diện cho đường đi thực tế nhưng có phạm vi tác động được kiểm soát.

Phép thử trọn luồng nên bao gồm:

- Đăng nhập bằng danh tính được phép và cơ chế xác thực dự kiến.
- Yêu cầu quyền cho đúng mục đích.
- Kiểm tra phê duyệt và thời hạn.
- Mở phiên tới mục tiêu đã chọn.
- Thực hiện một thao tác kiểm tra ít tác động.
- Xác nhận bằng chứng có thể truy xuất.
- Kết thúc phiên và xác nhận quyền bị thu hồi đúng.
- Thử một yêu cầu ngoài phạm vi và xác nhận bị từ chối.

Chỉ thử luồng “được phép” sẽ bỏ sót lỗi chính sách cấp quyền quá rộng. Một cổng mở quyền cần cả bằng chứng cho phép đúng và từ chối đúng.

### 6.2. Mở rộng theo đợt có điểm dừng

Mỗi đợt cần ghi rõ nhóm tài nguyên, người phê duyệt, kiểm tra trước mở và điều kiện dừng.

Điều kiện dừng có thể gồm:

- Không lưu được bản ghi phiên thử.
- Credential bị lệch với máy đích.
- Tăng bất thường số lần xác thực thất bại.
- Phát hiện node cũ còn phát hành quyền.
- Chính sách từ chối sai hoặc cho phép ngoài phạm vi.
- Hệ thống tiêu thụ secret không hoạt động sau khi chuyển đổi.
- Dung lượng tuyến ghi bằng chứng không đủ cho đợt tiếp theo.

Khi dừng, đóng đợt liên quan và giữ nguyên các nhóm đã được xác minh nếu không có bằng chứng cho thấy cùng lỗi ảnh hưởng đến chúng. Không cần mở toàn bộ hoặc đóng toàn bộ theo một quyết định duy nhất nếu kiến trúc hỗ trợ phân tách an toàn.

## 7. Dùng RTO và RPO đúng trong recovery order

**RTO** mô tả mục tiêu thời gian khôi phục một dịch vụ hoặc năng lực đã được định nghĩa. **RPO** mô tả mục tiêu về khoảng dữ liệu có thể mất tính theo thời gian. Hai mục tiêu giúp đánh giá kế hoạch, nhưng không thay thế kiểm chứng.

Với PAM, cần nói rõ RTO áp dụng cho năng lực nào:

- Đường truy cập khẩn cấp giới hạn.
- Phiên quản trị qua PAM cho nhóm trọng yếu.
- Tự động phân phối secret cho ứng dụng.
- Luân chuyển credential đầy đủ.
- Truy xuất toàn bộ lịch sử kiểm toán.

Các năng lực này có thể có thời điểm khôi phục khác nhau.

RPO của vault không tự đại diện cho RPO của bằng chứng phiên. RPO dữ liệu cũng không cho phép bỏ qua một thay đổi quyền quan trọng: một bản thu hồi quyền nằm trong khoảng mất dữ liệu vẫn cần được đối soát trước khi mở lại đối tượng liên quan.

### 7.1. Đo đường găng và công việc song song

Giả sử một cuộc diễn tập giả định có các khoảng thời gian:

| Công việc | Thời gian giả định | Có thể bắt đầu khi |
|---|---:|---|
| Chuẩn bị môi trường cách ly | 20 phút | Bắt đầu phục hồi |
| Kiểm tra backup và vật liệu khóa | 25 phút | Đội có quyền tiếp cận đầu vào |
| Khôi phục lõi vault | 30 phút | Môi trường và đầu vào đã sẵn sàng |
| Kiểm tra tuyến ghi phiên | 20 phút | Có môi trường thử phù hợp |
| Đối soát nhóm credential ưu tiên | 25 phút | Lõi vault và máy đích sẵn sàng |
| Pilot trọn luồng | 15 phút | Quyền, credential, đường phiên và bằng chứng đều đạt |

Nếu hai việc đầu bắt đầu cùng lúc, riêng đường “đầu vào → vault → đối soát → pilot” mất 25 + 30 + 25 + 15 = 95 phút trong giả định này. Thời gian thực tế còn phụ thuộc khi nào tuyến ghi phiên và các điều kiện khác đạt.

Không cộng mọi dòng rồi kết luận đó là RTO. Cũng không lấy thời điểm vault chạy làm thời điểm đã đáp ứng RTO truy cập quản trị. Phải đo tới khi lát cắt dịch vụ đã vượt cổng nghiệm thu được định nghĩa.

Các con số trên chỉ minh họa cách lập kế hoạch; không phải định mức cho sản phẩm hay tổ chức cụ thể.

## 8. Ví dụ runbook có điều kiện chuyển bước

Một runbook tốt tách rõ “thành phần đã chạy” khỏi “đã được phép phục vụ”. Dưới đây là mô hình dữ liệu minh họa, không phải cấu hình có thể nạp trực tiếp vào một sản phẩm PAM.

~~~yaml
recoveryPlan:
  id: pam-recovery-priority-access
  scope:
    - critical-admin-access
  initialState: isolated

  phases:
    - id: trusted-foundation
      requires:
        - recovery-authority-confirmed
        - previous-writers-fenced
        - clean-recovery-environment-ready
      evidence:
        - recovery-network-check
        - bootstrap-access-check
        - initial-audit-sink-check
      release: recovery-team-only

    - id: vault-core
      requires:
        - trusted-foundation-passed
        - backup-origin-and-integrity-checked
        - key-recovery-prerequisites-checked
        - consistent-restore-set-confirmed
      evidence:
        - supported-restore-result
        - controlled-decryption-check
        - unauthorized-read-denied
      release: isolated-vault

    - id: priority-access
      requires:
        - vault-core-passed
        - current-entitlements-reconciled
        - target-credentials-reconciled
        - session-evidence-path-verified
      evidence:
        - pilot-allowed-action
        - pilot-denied-action
        - session-record-found
        - temporary-access-expired
      release: approved-priority-group

  onGateFailure:
    releaseNextScope: false
    preserveEvidence: true
    requireOwnerReview: true
~~~

Trong triển khai thực tế, mỗi bằng chứng cần có định danh, thời điểm, người kiểm tra và kết quả. Một chuỗi văn bản như “session-record-found” trong kế hoạch chưa phải bằng chứng nếu không liên kết tới một bản ghi thực tế đã được xác nhận.

Không đặt giá trị secret, khóa, recovery code hoặc token vào runbook. Các tham chiếu nhạy cảm phải tuân theo cơ chế kiểm soát truy cập của tổ chức.

### 8.1. Trạng thái một đơn vị phục hồi

Có thể dùng chuỗi trạng thái sau để đội vận hành hiểu cùng một nghĩa:

~~~text
PLANNED
   |
   v
RESTORED_ISOLATED
   |
   v
VERIFIED_RESTRICTED
   |
   v
PILOT_PASSED
   |
   v
RELEASED

Bất kỳ cổng nào thất bại:
giữ hoặc đưa phạm vi liên quan về HOLD, bảo toàn bằng chứng
~~~

“RELEASED” chỉ áp dụng cho phạm vi đã ghi trong đơn vị đó. Một nhóm tài khoản được release không có nghĩa tất cả connector, tất cả ứng dụng hoặc toàn bộ module PAM đều hoàn tất phục hồi.

## 9. Tình huống thực hành: vault cũ, máy đích mới

Một tổ chức vận hành PAM cho nhóm quản trị và một số dịch vụ tự động. Tại thời điểm sự cố:

- Backup vault gần nhất lúc 08:00.
- Tài khoản quản trị của nhóm máy A được xoay lúc 08:15.
- Một kỹ sư bị thu hồi quyền quản trị lúc 08:20.
- Một danh tính dịch vụ của ứng dụng B được cập nhật lúc 08:25.
- Vault gặp sự cố lúc 08:40.
- Đội phục hồi đưa bản backup 08:00 lên môi trường cách ly.

### 9.1. Điều gì sẽ xảy ra nếu mở toàn bộ ngay?

Nhóm máy A có thể từ chối secret cũ. Cơ chế thử lại làm tăng nguy cơ khóa tài khoản. Người bị thu hồi quyền lúc 08:20 có thể thấy lại quyền lịch sử trong bản restore. Ứng dụng B có thể nhận secret cũ nếu secret provider phục hồi tự phát hành ngay.

Nếu scheduler rotation được bật cùng lúc, nhiều trạng thái có thể thay đổi trước khi đội biết trạng thái ban đầu, làm đối soát và điều tra khó hơn.

### 9.2. Trình tự xử lý hợp lý

**Bước 1: kiểm soát nguồn ghi và đường phát hành.** Cô lập thành phần cũ, giữ scheduler và provider ở phạm vi hạn chế. Ghi nhận những hệ thống có thể vẫn đang hoạt động bình thường bằng credential mới.

**Bước 2: xác nhận nền và lõi vault.** Kiểm tra đầu vào, thực hiện restore theo cơ chế được hỗ trợ, kiểm chứng giải mã và quyền đọc trong môi trường cách ly.

**Bước 3: cập nhật quyết định quyền.** Đối soát thông tin thu hồi lúc 08:20 từ nguồn thẩm quyền còn đáng tin trước khi cho nhóm quản trị đăng nhập production. Không mở lại quyền chỉ vì bản restore còn chứa membership cũ.

**Bước 4: kiểm tra đường phiên và bằng chứng.** Xác nhận một phiên thử được ghi, truy xuất và gắn đúng danh tính. Đặt điều kiện chặn nếu không có tuyến ghi đạt yêu cầu.

**Bước 5: tách nhóm A và ứng dụng B.** Nhóm A được xử lý bằng quy trình hòa giải credential có kiểm soát. Với B, trước hết xác định ứng dụng đang dùng phiên bản nào, nguồn cấp nào và có thực sự cần thay đổi ngay hay không. Không phá một kết nối đang ổn định chỉ để làm dữ liệu trong vault trông giống backup.

**Bước 6: pilot từng đường sử dụng.** Một người được phép mở phiên tới mục tiêu đã đối soát; một yêu cầu của người đã bị thu hồi phải bị từ chối. Ứng dụng B được kiểm tra qua luồng lấy secret và kết nối thực tế.

**Bước 7: mở lại tác vụ tự động có giới hạn.** Chỉ khi trạng thái credential đã rõ và kiểm tra đạt, mở scheduler cho nhóm được phê duyệt. Theo dõi kết quả trước khi mở tiếp.

### 9.3. Bằng chứng hoàn thành nên nói gì?

Báo cáo hữu ích không chỉ ghi “restore thành công”. Nó nên chỉ ra:

- Backup nào đã được sử dụng và trạng thái lõi nào được phục hồi.
- Quyền bị thu hồi sau backup đã được xử lý ra sao.
- Nhóm credential nào đã đối soát, nhóm nào còn đang giữ hạn chế.
- Phiên thử nào chứng minh đường truy cập và ghi bằng chứng hoạt động.
- Ứng dụng nào đã được kiểm tra qua luồng sử dụng thật.
- Thành phần cũ đã bị ngăn ghi bằng cách nào.
- Tác vụ nào đã được mở lại, ai phê duyệt và thời điểm nào.

Không cần đưa secret vào bất kỳ mục bằng chứng nào.

## 10. Điều chỉnh thứ tự theo loại sự cố

### 10.1. Chỉ mất một thành phần, còn nền tảng đáng tin

Nếu chỉ một gateway bị hỏng, không nên mặc định restore cả vault và cơ sở dữ liệu. Phạm vi phục hồi có thể giới hạn ở gateway, cấu hình tin cậy, đường ghi phiên và pilot các nhóm liên quan.

Đồ thị phụ thuộc vẫn cần được kiểm tra, nhưng các nút còn hoạt động và đã được xác minh không nhất thiết phải restore lại.

### 10.2. Sự cố rộng hoặc nghi xâm nhập

Khi nguồn danh tính, khóa, máy quản trị hoặc cụm PAM có khả năng bị ảnh hưởng, thứ tự phải ưu tiên dựng nền phục hồi đáng tin và xác định đầu vào phù hợp trước khi mở kết nối trở lại.

Restore bản sao từ trước thời điểm gián đoạn không tự chứng minh đã loại bỏ nguyên nhân. Có thể cần cấp lại danh tính máy, chứng thư, credential và kiểm tra lại chính sách theo phạm vi điều tra.

Đội phục hồi nên ghi rõ điều đã biết, điều chưa biết và giới hạn phạm vi đang cho phép. Không dùng chữ “sạch” cho một môi trường mới chỉ vượt qua kiểm tra khởi động.

### 10.3. Dịch vụ danh tính chưa sẵn sàng

Chỉ mở đường phục hồi độc lập cho nhóm đã được xác nhận theo chính sách. Khi dịch vụ danh tính quay lại, kiểm tra đồng bộ danh tính, membership và các quyết định thu hồi trước khi chuyển người dùng sang đường xác thực bình thường.

Phải có bước đóng quyền bootstrap và kiểm tra lại; nếu không, đường khẩn cấp dễ trở thành một đường quản trị tồn tại lâu dài ngoài vòng quản lý thường lệ.

### 10.4. Kho bằng chứng lịch sử chưa phục hồi đủ

Tách hai bài toán:

- Bảo đảm các sự kiện và phiên mới được ghi đúng ngay từ khi mở quyền.
- Phục hồi và đối soát kho lịch sử theo kế hoạch riêng.

Nếu có hàng đợi sự kiện tạm, cần ghi nhận định danh nguồn, thứ tự hoặc số thứ tự khi có, thời gian nguồn và thời gian tiếp nhận. Khi nhập lại, phải xử lý nguy cơ trùng hoặc thiếu theo cơ chế của hệ thống.

Không sửa timestamp cũ để tạo cảm giác dòng thời gian liền mạch. Ghi nhận sai lệch đồng hồ và khoảng trống bằng chứng như một phần của hồ sơ phục hồi.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao gây vấn đề | Cách cải thiện |
|---|---|---|
| Dùng một danh sách cố định cho mọi sự cố | Phụ thuộc và phạm vi ảnh hưởng khác nhau | Lập đồ thị, chọn nhánh phục hồi theo tình huống |
| Coi vault khởi động là PAM đã phục hồi | Chưa kiểm tra quyền, credential và phiên | Nghiệm thu theo năng lực trọn luồng |
| Mở rotation ngay sau restore | Có thể đổi trạng thái trước khi đối soát | Giữ hạn chế, mở theo nhóm đã kiểm chứng |
| Đặt credential cũ trở lại máy đích | Có thể tái sử dụng secret lộ hoặc phá ứng dụng | Hòa giải bằng cơ chế được hỗ trợ, có owner |
| Khôi phục quyền nguyên trạng | Có thể làm sống lại quyền đã thu hồi | Đối soát thay đổi sau backup |
| Dùng credential nằm trong chính vault đang hỏng để phục hồi vault | Tạo vòng phụ thuộc bootstrap | Thiết kế và diễn tập điểm khởi đầu độc lập |
| Chờ đầy đủ kho lịch sử rồi mới nghĩ tới log mới | Giai đoạn phục hồi có thể thiếu bằng chứng | Chuẩn bị tuyến ghi mới từ sớm |
| Chỉ kiểm tra yêu cầu được phép | Không phát hiện cấp quyền quá rộng | Thử cả cho phép, từ chối và hết hạn |
| Không ngăn cụm cũ ghi trở lại | Có thể tạo hai nguồn điều khiển | Kiểm chứng fencing và quyền ghi |
| Không thu hồi quyền phục hồi | Để lại quyền đặc biệt kéo dài | Đưa thu hồi bootstrap vào cổng kết thúc |

## 12. Diễn tập recovery order

Diễn tập cần thực hiện trong phạm vi được cho phép, với dữ liệu và mục tiêu phù hợp. Giá trị của diễn tập nằm ở việc chứng minh các phụ thuộc và cổng chuyển bước thực sự hoạt động.

Một kịch bản hữu ích nên có ít nhất một sai lệch có chủ đích:

- Credential đã thay đổi sau thời điểm backup.
- Một người dùng đã bị thu hồi quyền.
- Một tuyến ghi phiên chưa sẵn sàng.
- Một thành phần cũ cố kết nối lại.
- Một ứng dụng còn giữ secret khác phiên bản.
- Một nguồn thời gian hoặc chứng thư chưa đạt yêu cầu.

Đội thực hiện phải phát hiện sai lệch và giữ đúng nhóm ở trạng thái hạn chế. Một cuộc diễn tập chỉ có các bước thành công sẽ khó cho biết cổng kiểm chứng có thực sự ngăn mở quyền sai hay không.

### 12.1. Các chỉ số nên ghi nhận

- Thời gian tới khi có môi trường phục hồi đáng tin.
- Thời gian tới khi lõi vault được kiểm chứng trong phạm vi cách ly.
- Thời gian tới khi lát cắt nghiệp vụ ưu tiên đầu tiên được nghiệm thu.
- Số tài khoản đã đối soát so với tổng phạm vi cần mở.
- Số quyền lịch sử bị chặn trước khi release.
- Thời gian tới khi tuyến ghi bằng chứng mới được xác minh.
- Số nhóm phải dừng do cổng kiểm tra thất bại.
- Số quyền tạm còn tồn tại sau khi kết thúc.

Không cải thiện số đo bằng cách đổi định nghĩa hoàn thành giữa chừng. Nếu chỉ đạt đường truy cập khẩn cấp giới hạn, báo đúng năng lực đó và phần còn lại chưa phục hồi.

### 12.2. Câu hỏi tự kiểm tra

**1. Vì sao vault đã giải mã được dữ liệu nhưng chưa nên mở toàn bộ connector?**

Vì còn phải đối soát quyền hiện hành, credential trên hệ thống đích, nguồn ghi cũ và đường bằng chứng. Connector có thể kích hoạt thay đổi hoặc phát hành secret trước khi các trạng thái này được xác nhận.

**2. Có nên chờ restore toàn bộ bản ghi phiên cũ rồi mới mở một nhóm quản trị ưu tiên?**

Tùy yêu cầu của nhóm đó và phương án được chấp thuận. Điều kiện bắt buộc của tuyến truy cập cần ghi phiên là có tuyến ghi bằng chứng mới đạt yêu cầu trước khi mở. Nếu truy cập lịch sử cũng là phụ thuộc bắt buộc của nghiệp vụ hoặc chính sách, nhóm đó phải chờ phụ thuộc tương ứng.

**3. Backup vault cũ hơn credential trên máy đích thì có nên đặt máy đích về credential trong backup?**

Không tự động làm như vậy. Cần xác định trạng thái, owner, phụ thuộc ứng dụng và thực hiện quy trình hòa giải được hỗ trợ. Khôi phục dịch vụ không đồng nghĩa quay secret về giá trị lịch sử.

**4. Tại sao RTO của PAM nên gắn với một năng lực cụ thể?**

Vì đường truy cập khẩn cấp, quản trị có ghi phiên, phân phối secret và truy xuất lịch sử có các phụ thuộc khác nhau. Một mốc “PAM đã lên” không thể hiện đầy đủ khả năng sử dụng thực tế.

**5. Bước nào kết thúc quyền bootstrap?**

Cổng kết thúc phục hồi phải thu hồi hoặc đóng đường bootstrap theo thiết kế, hết hạn các quyền tạm, xử lý credential đã sử dụng trong khẩn cấp khi cần và lưu bằng chứng hậu kiểm. Việc dịch vụ chính hoạt động trở lại không tự làm các quyền này biến mất.

## Kết luận

Recovery order của PAM là một kế hoạch **khôi phục năng lực có điều kiện**. Đồ thị phụ thuộc xác định điều gì phải sẵn sàng; ưu tiên nghiệp vụ xác định nhánh cần phục hồi trước; các cổng kiểm chứng xác định khi nào được mở quyền.

Trình tự tốt bắt đầu từ nền phục hồi đáng tin, kiểm chứng dữ liệu và vật liệu khóa, phục hồi điều khiển quyền và bằng chứng, đối soát credential rồi mở từng lát cắt dịch vụ. Kết thúc chỉ khi các đường đặc quyền đã trở lại quản lý bình thường và quyền phục hồi tạm thời đã được xử lý.
