# Dữ liệu cần xóa

## 1. Mục tiêu và phạm vi

Trong chương **Phân loại dữ liệu**, “dữ liệu cần xóa” là một nhóm cần được xác định bằng điều kiện và thời điểm trong vòng đời xử lý. Một bản ghi có thể đang phục vụ mục đích hợp lệ hôm nay nhưng trở thành dữ liệu cần xóa khi mục đích đó kết thúc, thời hạn lưu hết hoặc yêu cầu xóa được xác nhận. Độ nhạy cảm của bản ghi không tự biến mất khi bản ghi chuyển sang trạng thái chờ xóa.

Mục tiêu của bài học là chuyển quyết định xóa thành **yêu cầu bảo mật cụ thể, đo được và có thể kiểm chứng**. Thiết kế phải bảo vệ cả hai phía: dữ liệu thuộc phạm vi phải được xóa đúng hạn, còn dữ liệu ngoài phạm vi phải được bảo vệ khỏi xóa nhầm hoặc xóa trái phép.

Sau bài học, người học có thể:

- Xác định lý do, phạm vi, thẩm quyền và mốc thời gian làm dữ liệu trở thành đối tượng cần xóa.
- Phân biệt ngăn truy cập, xóa logic, xóa khỏi kho hoạt động và xử lý bản sao lưu.
- Theo dõi dữ liệu qua cache, chỉ mục, hàng đợi, tệp xuất và hệ thống bên ngoài.
- Đặc tả xác thực, phân quyền, logging và khả năng phục hồi cho quy trình xóa.
- Xây dựng chuỗi bằng chứng đủ để kết luận đúng mức độ hoàn thành.

Các thời hạn và tên trạng thái trong bài là giả định cho ví dụ thiết kế, cần được điều chỉnh theo mục đích sử dụng, rủi ro và năng lực hệ thống. Bài học không đặt ra thời hạn pháp lý áp dụng chung.

## 2. Khi nào dữ liệu được phân loại là cần xóa?

### 2.1. Dựa vào mục đích và điều kiện vòng đời

Quyết định xóa cần nêu được **dữ liệu nào, vì sao, khi nào và ai có thẩm quyền quyết định**. “Dữ liệu cũ” hoặc “dữ liệu không dùng nữa” chưa đủ rõ để tự động hóa.

| Điều kiện phát sinh | Ví dụ | Thông tin phải xác nhận |
|---|---|---|
| Hết thời hạn phục vụ mục đích | Tệp xuất báo cáo chỉ được giữ tạm để tải | Mốc bắt đầu tính hạn, thời gian tồn tại và các nơi có bản sao |
| Kết thúc một quan hệ hoặc chức năng | Hồ sơ nháp không còn được người dùng sử dụng | Sự kiện kết thúc, người có quyền xác nhận và dữ liệu còn phụ thuộc |
| Yêu cầu xóa đã được xác nhận | Người dùng đề nghị xóa nội dung thuộc quyền quản lý của mình | Danh tính, quyền trên dữ liệu, phạm vi và ngoại lệ đã được phê duyệt |
| Thu thập sai hoặc vượt phạm vi | Payload lỗi vô tình chứa thông tin riêng trong log | Các bản sao bị ảnh hưởng và cách ngăn tiếp tục phát sinh |
| Dữ liệu thử nghiệm đã hết nhu cầu | Hồ sơ tạm dùng cho một lần kiểm tra | Dữ liệu có thật hay giả, môi trường và thời hạn đã xác định |
| Hết giá trị sử dụng của bí mật | Token khôi phục đã dùng hoặc hết hạn | Cách vô hiệu hóa ngay và cách xử lý bản lưu không còn cần thiết |
| Kết thúc sử dụng một dịch vụ bên ngoài | Bản sao tài liệu tại nhà cung cấp cũ | Dữ liệu hoạt động, bản sao lưu, bên xử lý tiếp theo và bằng chứng xóa |

Một loại dữ liệu có thể có nhiều mục đích sử dụng, mỗi mục đích có điều kiện lưu giữ riêng. Nếu một phần còn cần giữ theo quyết định đã được phê duyệt, cần tách phần đó, giới hạn cách sử dụng và xác định thời điểm xem lại. Không dùng lý do “có thể cần sau này” để giữ nguyên toàn bộ dữ liệu vô thời hạn.

### 2.2. Tách ba thuộc tính thường bị nhầm lẫn

- **Độ nhạy cảm:** hậu quả khi dữ liệu bị lộ, bị sửa hoặc mất khả năng sử dụng.
- **Trạng thái lưu giữ:** dữ liệu đang được phép giữ, đã đến hạn xóa hay đang có ngoại lệ giữ lại.
- **Trạng thái thực hiện xóa:** chưa xử lý, đã chặn truy cập, đã xóa khỏi kho hoạt động hoặc đang chờ xử lý bản sao còn lại.

Ví dụ, một tệp xuất chứa thông tin cá nhân có thể đồng thời mang nhãn “hạn chế cao”, “hết hạn lưu” và “đang chờ xóa khỏi kho tệp”. Nhãn hết hạn không làm quyền truy cập trở nên ít quan trọng hơn. Trong thời gian chờ xóa, dữ liệu vẫn cần được bảo vệ.

### 2.3. Ngoại lệ giữ lại phải có phạm vi

Một quyết định tạm giữ dữ liệu để giải quyết tranh chấp hoặc điều tra nội bộ phải được chuyển thành thông tin có thể thực thi: ai phê duyệt, phần dữ liệu nào, cho mục đích gì, ai được truy cập và khi nào đánh giá lại. Điều kiện cụ thể phải do đầu mối có thẩm quyền xác định, không để nhóm phát triển tự suy đoán.

Ngoại lệ đối với một tập hồ sơ không mặc nhiên áp dụng cho mọi cache, tệp xuất hoặc bản sao phục vụ tiện ích. Nếu cần giữ một bản chứng cứ được kiểm soát, phải phân biệt bản đó với các bản sao không còn phục vụ mục đích nào.

## 3. Xác định đơn vị và phạm vi xóa

### 3.1. Đơn vị xóa không nhất thiết là cả tài khoản

Một yêu cầu có thể áp dụng cho một trường, một tài liệu, một nhóm sự kiện, một khoảng thời gian hoặc toàn bộ hồ sơ của một chủ thể. Lựa chọn đơn vị xóa ảnh hưởng trực tiếp tới quyền, thao tác dữ liệu và tiêu chí kiểm thử.

Ví dụ, xóa một tệp đính kèm hỗ trợ không có nghĩa xóa tài khoản người gửi. Xóa hồ sơ học tập cũng không tự động có nghĩa xóa mọi dấu vết điều tra đã được phê duyệt giữ với mục đích riêng. Phạm vi cần được mô tả bằng đối tượng và quan hệ dữ liệu, thay vì một câu “xóa toàn bộ” không có danh mục cụ thể.

### 3.2. Theo dõi các bản sao và dữ liệu dẫn xuất

```text
[Bản ghi gốc] -> [Cache / chỉ mục tìm kiếm]
      |------> [Tệp đính kèm / phiên bản cũ của đối tượng]
      |------> [Hàng đợi / sự kiện / tác vụ đang chạy]
      |------> [Tệp xuất / dữ liệu phân tích]
      |------> [Log / báo cáo sự cố]
      |------> [Nhà cung cấp bên ngoài]
      +------> [Bản sao lưu / ảnh chụp dữ liệu]
```

Mỗi đường đi tạo ra một câu hỏi xóa riêng. Xóa bản ghi gốc không chứng minh cache đã hết dữ liệu, chỉ mục đã cập nhật hay tệp xuất đã mất khả năng tải. Một hệ thống có phiên bản đối tượng còn cần xác định thao tác xóa tác động tới phiên bản hiện tại hay cả những phiên bản trước đó.

Dữ liệu dẫn xuất phải được xem xét theo khả năng còn chứa hoặc liên kết tới thông tin thuộc phạm vi xóa. Một báo cáo đã loại tên nhưng giữ mã có thể tra ngược chưa chắc đã thoát khỏi phạm vi. Ngược lại, không nên tự động xóa mọi kết quả tổng hợp nếu đã có đánh giá chứng minh kết quả không còn mang thông tin thuộc phạm vi cần xử lý.

Với dữ liệu đã chuyển cho bên khác hoặc đã được tải ra ngoài phạm vi kiểm soát, cần xác định rõ khả năng thực hiện. Hệ thống có thể xóa bản trên kho do mình quản lý nhưng không thể mặc nhiên chứng minh bản đã được người nhận tải về cũng đã bị xóa. Giới hạn này phải xuất hiện trong mô tả phạm vi và bằng chứng.

### 3.3. Hồ sơ dữ liệu cần xóa

| Trường hồ sơ | Nội dung cần có |
|---|---|
| Mã phạm vi | Định danh tập dữ liệu, đối tượng và môi trường áp dụng |
| Chủ thể và thẩm quyền | Ai yêu cầu, ai quyết định, ai thực hiện và ai xác nhận |
| Điều kiện xóa | Sự kiện hoặc thời hạn làm phát sinh nghĩa vụ xử lý trong hệ thống |
| Mốc tính thời gian | Thời điểm yêu cầu hợp lệ được tiếp nhận hoặc thời điểm hết hạn lưu |
| Các nơi tồn tại | Kho chính, bản sao đọc, cache, chỉ mục, tệp, hàng đợi, log, bên ngoài và backup |
| Quan hệ phụ thuộc | Dữ liệu nào phải xóa cùng, dữ liệu nào cần tách, quan hệ nào không được làm hỏng |
| Ngoại lệ | Phần còn giữ, lý do, người phê duyệt, quyền truy cập và ngày xem lại |
| Cách xử lý | Ngăn truy cập, xóa khỏi kho, hết hạn phiên bản, xử lý khóa hoặc yêu cầu bên ngoài |
| Bằng chứng | Trạng thái từng nơi, thời điểm xử lý, kết quả kiểm tra và giới hạn kiểm chứng |

Hồ sơ điều phối nên dùng mã nội bộ và tham chiếu. Không sao chép nguyên nội dung cần xóa vào vé công việc, log hoặc thông báo hoàn tất, vì chính bằng chứng có thể trở thành một bản sao mới ngoài kế hoạch.

## 4. Phân biệt các mức kết quả của việc xóa

| Mức xử lý | Có thể kết luận gì? | Chưa thể kết luận gì? |
|---|---|---|
| Ẩn trên giao diện | Một giao diện không còn hiển thị | API, tìm kiếm, liên kết tải hoặc người khác không còn đọc được |
| Chặn truy cập nghiệp vụ | Các đường truy cập đã kiểm soát từ chối sử dụng dữ liệu | Dữ liệu đã được loại khỏi kho lưu trữ |
| Xóa logic | Dữ liệu được đánh dấu không còn hoạt động theo quy tắc ứng dụng | Bản ghi hoặc tệp không còn tồn tại trong lưu trữ |
| Xóa khỏi kho hoạt động | Các kho trong phạm vi hoạt động đã thực hiện thao tác xóa và kiểm tra tương ứng | Mọi backup, phiên bản cũ và bản sao bên ngoài cũng đã hết |
| Xử lý hết bản sao còn lại | Các lớp lưu trữ đã khai báo hoàn tất theo cơ chế và thời hạn thống nhất | Mọi thiết bị vật lý ngoài khả năng quan sát đã được kiểm tra trực tiếp |

Các mức này có thể là những mốc trong một quy trình, không nhất thiết là các lựa chọn thay thế nhau. Một hệ thống có thể cần chặn truy cập ngay, xóa khỏi kho hoạt động trong một ngày và chờ bản sao lưu hết hạn sau đó.

### 4.1. Giới hạn của thao tác xóa trên kho lưu trữ

Truy vấn không tìm thấy dữ liệu là bằng chứng cho đường truy vấn đã kiểm tra, không phải bằng chứng duy nhất về toàn bộ lưu trữ. Cần kết hợp kết quả thao tác của kho, cấu hình vòng đời, trạng thái phiên bản và quyền truy cập với phạm vi kiểm tra đã xác định.

Trong dịch vụ lưu trữ được quản lý, nhóm ứng dụng thường không quan sát trực tiếp cách xử lý từng vùng lưu trữ vật lý. Yêu cầu phải nêu mức bảo đảm cần có và bằng chứng nhà cung cấp cung cấp được, thay vì tuyên bố đã xác minh vật lý chỉ từ một phản hồi API thành công.

### 4.2. Giới hạn của xóa bằng cách hủy khóa

Hủy khóa có thể là một cơ chế làm dữ liệu mã hóa không còn giải mã được, nhưng chỉ đáp ứng mục tiêu khi phạm vi và các giả định phù hợp. Cần biết khóa bảo vệ những dữ liệu nào, có bản sao khóa hay quyền khôi phục nào khác không, và có bản rõ hoặc bản mã được bảo vệ bằng khóa khác không.

Nếu một khóa dùng chung cho nhiều người, hủy khóa để xử lý dữ liệu của một người có thể làm mất dữ liệu của những người khác. Nếu khóa vẫn tồn tại trong backup hoặc một dịch vụ khác, việc hủy một bản khóa chưa đủ. Không dùng cụm từ “đã hủy khóa” thay cho phân tích phạm vi xóa và hậu quả phục hồi.

## 5. Ví dụ thiết kế quy trình xóa hồ sơ học tập

### 5.1. Bối cảnh và mục tiêu

Giả sử một nền tảng học trực tuyến cho phép người học yêu cầu xóa một hồ sơ học tập đã kết thúc sử dụng. Trong ví dụ, phạm vi đã được phê duyệt gồm bản ghi hồ sơ, tệp đính kèm, tiến độ chi tiết, chỉ mục tìm kiếm, cache và các tệp xuất do nền tảng đang quản lý. Dấu vết kiểm tra tối thiểu có thời hạn và mục đích riêng, không chứa nội dung hồ sơ.

Hệ thống phục vụ nhiều tổ chức, vì vậy mã hồ sơ phải luôn được ràng buộc với tổ chức và chủ thể có quyền. Một người học không được xóa hồ sơ người khác bằng cách đổi mã trên URL. Tác vụ xóa tự động cũng không được nhận phạm vi rộng hơn quyết định đã phê duyệt.

Đặt **T0** là thời điểm hệ thống tiếp nhận yêu cầu đã xác thực, đã kiểm tra quyền và xác định phạm vi được phép xóa. Các mốc minh họa là:

- Trong 60 giây từ T0: dữ liệu không còn được cung cấp qua các luồng nghiệp vụ thuộc phạm vi.
- Trong 24 giờ từ T0: hoàn tất xóa khỏi các kho hoạt động đã khai báo.
- Trong 35 ngày từ T0: hoàn tất xử lý các bản sao lưu thuộc phạm vi theo cơ chế hết hạn đã thống nhất.

Các mốc cần được kiểm tra với thiết kế backup thực tế. Cấu hình “giữ mỗi backup 35 ngày” chưa tự chứng minh mốc cuối, nếu sau T0 vẫn tiếp tục tạo backup chứa dữ liệu chờ xóa. Phải kiểm soát thời điểm tạo bản sao cuối, cơ chế hết hạn hoặc chọn thời hạn khác có thể đáp ứng và công bố chính xác.

### 5.2. Mô hình trạng thái

```text
RECEIVED
   |
   +--> REJECTED                Sai danh tính, quyền hoặc phạm vi
   |
   +--> HELD                   Có quyết định giữ lại cần giải quyết
   |
   v
ACCEPTED                       Ghi nhận T0 và danh mục phạm vi
   |
   v
ACCESS_BLOCKED                 Chặn truy cập và việc tạo lại dữ liệu
   |
   v
ACTIVE_PURGED                  Đã xử lý các kho hoạt động
   |
   v
PENDING_REMAINING_COPIES        Chờ backup hoặc bên ngoài hoàn tất
   |
   v
COMPLETED                      Đủ bằng chứng cho phạm vi đã cam kết
```

Lỗi kỹ thuật và số lần thử lại là thông tin gắn với từng bước. Chúng không được làm yêu cầu nhảy sang `COMPLETED` và không được đặt lại T0 để che việc quá hạn. Một yêu cầu có phần bị giữ lại và phần được xóa phải báo trạng thái từng phần, không tự coi toàn bộ yêu cầu đã hoàn tất.

Với `HELD`, cần ghi người chịu trách nhiệm và thời điểm xem lại. Việc chờ giải quyết phải được báo rõ; không được ngầm đưa một yêu cầu bị giữ vào cam kết thời gian dành cho phạm vi đã được phép xóa.

### 5.3. Điều phối nhiều nơi lưu

Khi có nhiều dịch vụ, một thao tác xóa thường không phải một giao dịch đơn bao trùm mọi nơi. Cần một bộ điều phối theo dõi danh mục đích và kết quả, có thể tiếp tục sau khi tiến trình dừng.

```text
[Tiếp nhận yêu cầu hợp lệ]
          |
          v
[Lưu quyết định + phạm vi + T0 + trạng thái điều phối]
          |
          v
[Chặn đọc / chặn ghi lại dữ liệu thuộc phạm vi]
          |
          +--> [Cơ sở dữ liệu và bản sao đọc]
          +--> [Cache và chỉ mục]
          +--> [Kho tệp và phiên bản]
          +--> [Tác vụ nền / nhà cung cấp]
          +--> [Theo dõi backup]
          |
          v
[Đối chiếu bằng chứng từng đích trước khi kết luận]
```

Thông tin điều phối phải được lưu bền vững trước khi báo tiếp nhận thành công. Nếu hệ thống không bảo đảm việc ghi quyết định và phát công việc cùng hoàn tất, có thể dùng một cơ chế ghi công việc bền vững cùng giao dịch dữ liệu phù hợp rồi chuyển tiếp. Tên kỹ thuật không quan trọng bằng bằng chứng rằng yêu cầu không bị mất khi tiến trình dừng giữa các bước.

## 6. Đặc tả yêu cầu bảo mật có thể kiểm chứng

### 6.1. Xác thực và chống xóa trái phép

**REQ-DEL-AUTH-01:** Điểm tiếp nhận xóa chỉ chấp nhận yêu cầu từ danh tính hợp lệ. Với thao tác xóa hồ sơ đầy đủ trong ví dụ, người dùng phải xác nhận lại danh tính trong 5 phút gần nhất, gắn với tài khoản và phiên thực hiện. Yêu cầu thiếu xác thực, hết phiên hoặc xác nhận lại quá hạn không được tạo công việc xóa.

**REQ-DEL-AUTHZ-01:** Máy chủ phải kiểm tra người gọi có quyền xóa đúng hồ sơ trong đúng tổ chức. Danh tính và quyền được lấy từ ngữ cảnh xác thực cùng dữ liệu phân quyền phía máy chủ; mã đối tượng trong payload không phải bằng chứng sở hữu.

**REQ-DEL-AUTHZ-02:** Tác vụ nền chỉ được xử lý danh mục đã được phê duyệt cho mã yêu cầu đó. Các thao tác xóa hàng loạt hoặc vượt phạm vi người dùng thông thường phải có luồng quyền riêng và dấu vết quyết định tương ứng. Danh tính thực thi xóa không được cấp quyền quản trị toàn bộ hệ thống chỉ để thuận tiện triển khai.

Kiểm thử chấp nhận gồm đổi mã hồ sơ, đổi tổ chức, dùng quyền đã thu hồi, sửa phạm vi công việc và gọi lại yêu cầu bằng tài khoản khác. Kết quả phải cho thấy dữ liệu ngoài phạm vi không bị thay đổi và phản hồi không tiết lộ nội dung hồ sơ bị từ chối.

### 6.2. Xác định phạm vi, ngoại lệ và mốc thời gian

**REQ-DEL-SCOPE-01:** Mỗi yêu cầu được tiếp nhận phải có mã yêu cầu, chủ thể có quyền, tổ chức, phiên bản quy tắc lưu giữ, danh mục nhóm dữ liệu và các kho cần xử lý. Ngoại lệ giữ lại phải có quyết định riêng; công việc xóa không được tự bỏ qua ngoại lệ mà không ghi nhận.

**REQ-DEL-SCOPE-02:** Hệ thống phải giữ nguyên T0 và các hạn xử lý qua mọi lần thử lại. Bổ sung một kho mới hoặc phát hiện thiếu phạm vi phải được ghi nhận, đánh giá ảnh hưởng và xử lý; không tạo T0 mới chỉ để yêu cầu còn trong hạn.

Kiểm chứng bằng yêu cầu thử có một phần được phép xóa và một phần đang giữ lại. Đối chiếu danh mục với các kho, kiểm tra phần giữ lại không bị xóa, phần được phép vẫn tiến triển và báo cáo không gọi toàn bộ yêu cầu là hoàn tất.

### 6.3. Ngăn truy cập trong thời gian chờ xóa

**REQ-DEL-BLOCK-01:** Trong 60 giây từ T0, mọi đường đọc nghiệp vụ thuộc phạm vi phải từ chối cung cấp dữ liệu: API chi tiết, danh sách, tìm kiếm, tệp tải và tác vụ xuất. Kiểm tra phải có hiệu lực với bản sao đọc và cache, không chỉ với cơ sở dữ liệu chính.

**REQ-DEL-BLOCK-02:** Khi một luồng ghi hoặc sự kiện cũ tham chiếu tới đối tượng đã được xác nhận xóa, hệ thống không được tạo lại dữ liệu thuộc phạm vi. Việc kiểm tra phải dựa trên trạng thái xóa hoặc dấu điều khiển có hiệu lực với đúng định danh và thế hệ dữ liệu.

Nếu liên kết tải trực tiếp từ kho vẫn còn hiệu lực sau khi ứng dụng đánh dấu xóa, yêu cầu chặn đọc chưa được đáp ứng. Thiết kế có thể dùng điểm tải kiểm tra quyền và trạng thái, hoặc cơ chế thu hồi có thể kiểm chứng tại kho. Phải thử bằng chính liên kết đã cấp trước T0.

### 6.4. Xóa khỏi kho hoạt động và xử lý lỗi

**REQ-DEL-ACTIVE-01:** Trong 24 giờ từ T0, từng đích trong danh mục kho hoạt động phải hoàn tất xử lý xóa đối với phạm vi đã phê duyệt. Đích không phản hồi hoặc trả lỗi phải giữ trạng thái chưa hoàn tất và kích hoạt cơ chế thử lại có giới hạn cùng cảnh báo theo ngưỡng vận hành đã xác định.

**REQ-DEL-ACTIVE-02:** Thực hiện lại cùng một công việc không được mở rộng phạm vi, gây lỗi nghiệp vụ mới hoặc làm dữ liệu quay lại. Khóa công việc phải gắn với mã yêu cầu và đích xử lý; bằng chứng phải phản ánh kết quả cuối của từng đích.

Tính lặp an toàn không có nghĩa bảo đảm thông điệp chỉ được giao đúng một lần. Hệ thống cần chịu được thông điệp trùng, tiến trình dừng sau khi xóa nhưng trước khi xác nhận, hoặc hai tác vụ xử lý đồng thời. Các điều kiện này phải được kiểm thử bằng dữ liệu giả có thể đối chiếu.

### 6.5. Chống dữ liệu quay lại do đồng bộ hoặc phục hồi

**REQ-DEL-RECREATE-01:** Cơ chế nhập, đồng bộ và xử lý sự kiện phải kiểm tra quyết định xóa trước khi công bố lại dữ liệu của đối tượng. Dấu điều khiển xóa phải tồn tại đủ lâu để bao phủ thời gian sự kiện, bản sao hoặc nguồn nhập cũ còn có thể được đưa vào hệ thống.

**REQ-DEL-RECREATE-02:** Định danh đã xóa không được tái sử dụng theo cách làm công việc xóa cũ tác động vào dữ liệu mới. Nếu nghiệp vụ cho phép tạo lại một hồ sơ, phải phân biệt thế hệ hoặc định danh mới, đồng thời kiểm tra các quan hệ và công việc còn tồn tại.

**REQ-DEL-RESTORE-01:** Một bản phục hồi chưa được mở cho người dùng cho tới khi các quyết định xóa và hạn chế truy cập phát sinh sau thời điểm backup đã được áp dụng. Sổ điều khiển xóa phải sẵn sàng từ nguồn được bảo vệ phù hợp, không bị thay thế bằng trạng thái cũ trong cùng lần phục hồi.

Kiểm thử bằng cách phát lại sự kiện cũ sau xóa, chạy tác vụ xuất đã khởi động trước T0, đồng bộ từ nguồn chưa cập nhật và phục hồi backup có chứa bản ghi. Kết quả cần chứng minh dữ liệu không được cung cấp trở lại, thay vì chỉ chứng minh tác vụ xóa ban đầu đã chạy.

### 6.6. Backup và khả năng phục hồi dữ liệu còn hợp lệ

**REQ-DEL-BACKUP-01:** Với ví dụ này, đến T0 cộng 35 ngày, mọi backup thuộc phạm vi phải hết khả năng được sử dụng để đưa dữ liệu cần xóa trở lại theo cơ chế đã thống nhất. Hồ sơ phải ghi tập backup liên quan, cách hết hạn hoặc xử lý tương ứng, kết quả và giới hạn bằng chứng. Một lịch xóa được cấu hình nhưng chưa tới hạn chỉ chứng minh đang chờ, chưa chứng minh hoàn tất.

**REQ-DEL-REC-01:** Quy trình xóa phải giữ khả năng phục hồi dữ liệu còn trong thời hạn lưu và ngoài phạm vi xóa. Mục tiêu minh họa cho dữ liệu học tập còn hợp lệ là RPO không quá 24 giờ và RTO không quá 4 giờ. RPO là mức mất dữ liệu tối đa chấp nhận được tính theo thời gian; RTO là thời gian mục tiêu khôi phục hoạt động sau gián đoạn.

Thời gian áp dụng quyết định xóa trước khi mở lại dịch vụ phải được tính trong kế hoạch RTO. Không đạt yêu cầu phục hồi nếu hệ thống chỉ đáp ứng thời gian bằng cách đưa dữ liệu đã xóa trở lại. Đồng thời, không được hủy một backup dùng chung nếu việc đó làm mất khả năng phục hồi của dữ liệu khác mà chưa có quyết định phù hợp.

### 6.7. Dữ liệu tại bên thứ ba

**REQ-DEL-EXTERNAL-01:** Với mỗi bên tiếp nhận dữ liệu, yêu cầu xóa phải có phạm vi, thời hạn, cách gửi, cơ chế theo dõi và loại bằng chứng được chấp nhận. Phản hồi “đã nhận yêu cầu” không được coi là “đã xóa”. Bản hoạt động, log và backup của bên ngoài phải được phân định nếu có cơ chế hoặc lịch xử lý khác nhau.

**REQ-DEL-EXTERNAL-02:** Nếu bên ngoài chưa xác nhận hoàn tất hoặc chỉ xác nhận một phần, trạng thái nội bộ phải phản ánh phần còn chờ. Không kết luận toàn bộ phạm vi hoàn tất chỉ vì dữ liệu trong cơ sở dữ liệu của tổ chức đã bị xóa.

Nhóm tích hợp cần xác nhận năng lực của nhà cung cấp trước khi cam kết thời hạn với người dùng. Nếu không có khả năng đáp ứng hoặc kiểm chứng một yêu cầu quan trọng, phải ghi khoảng thiếu và quyết định xử lý rủi ro, thay vì tự điền trạng thái thành công.

### 6.8. Logging và bằng chứng hoàn tất

**REQ-DEL-LOG-01:** Dấu vết phải cho biết ai yêu cầu, ai quyết định, phạm vi, T0, hạn xử lý, đích, thời điểm, kết quả, lần thử lại và ngoại lệ. Không ghi bản sao nội dung cần xóa, token xác thực hoặc bí mật kết nối vào log.

**REQ-DEL-LOG-02:** Trong ví dụ, dấu vết điều phối tối thiểu được giữ 90 ngày từ khi yêu cầu kết thúc, với mục đích điều tra đã xác định và quyền đọc hạn chế. Dấu điều khiển phục vụ chống phục hồi có thời hạn riêng, phải bao phủ toàn bộ cửa sổ đưa dữ liệu cũ trở lại; không tự áp cùng mốc 90 ngày nếu cửa sổ đó dài hơn.

**REQ-DEL-COMPLETE-01:** Chỉ chuyển sang `COMPLETED` khi mọi đích bắt buộc trong phạm vi đã có bằng chứng đạt, không còn lỗi chưa xử lý hoặc bản sao đang chờ. Thông báo kết quả phải phân biệt dữ liệu hoạt động đã xóa, bản sao còn chờ và phần được giữ lại theo quyết định riêng.

Mã nội bộ trong bằng chứng vẫn có thể liên quan tới một cá nhân. Bằng chứng phải có phân loại, quyền và vòng đời của chính nó. Chỉ giữ thông tin đủ để chứng minh việc thực hiện; không giữ nguyên hồ sơ dưới tên gọi “bằng chứng đã xóa”.

## 7. Ma trận truy vết từ rủi ro đến kiểm thử

| Kịch bản rủi ro | Yêu cầu liên quan | Cơ chế kiến trúc | Bằng chứng chấp nhận |
|---|---|---|---|
| Người dùng đổi mã để xóa hồ sơ người khác | REQ-DEL-AUTH-01, REQ-DEL-AUTHZ-01 | Xác thực lại; kiểm tra quyền theo đối tượng và tổ chức | Kiểm thử chéo tài khoản, chéo tổ chức; dữ liệu ngoài phạm vi còn nguyên |
| Tác vụ nền xóa vượt phạm vi | REQ-DEL-AUTHZ-02, REQ-DEL-SCOPE-01 | Danh mục phê duyệt; danh tính thực thi giới hạn; kiểm tra phạm vi | Thử sửa payload công việc và đích; đối chiếu các bản ghi ngoài phạm vi |
| Bản ghi bị ẩn nhưng còn tải được từ cache hoặc tệp | REQ-DEL-BLOCK-01, REQ-DEL-ACTIVE-01 | Chặn đọc có hiệu lực trên các đường; xử lý từng kho và phiên bản | Thử API, cache, tìm kiếm, liên kết cũ và kho tệp trực tiếp theo quyền kiểm thử |
| Tiến trình dừng làm mất yêu cầu hoặc báo hoàn tất sai | REQ-DEL-SCOPE-02, REQ-DEL-ACTIVE-02, REQ-DEL-COMPLETE-01 | Điều phối bền vững; xử lý lặp an toàn; đối chiếu trạng thái từng đích | Dừng tiến trình ở các điểm; gửi trùng; tạo lỗi một đích và kiểm tra trạng thái |
| Sự kiện cũ tạo lại dữ liệu hoặc công việc cũ xóa dữ liệu mới | REQ-DEL-BLOCK-02, REQ-DEL-RECREATE-01, REQ-DEL-RECREATE-02 | Dấu điều khiển xóa; phân biệt định danh hoặc thế hệ; kiểm tra trước ghi | Phát lại sự kiện; tạo hồ sơ mới; xử lý công việc cũ và kiểm tra phạm vi |
| Phục hồi làm dữ liệu đã xóa xuất hiện trở lại | REQ-DEL-RESTORE-01, REQ-DEL-BACKUP-01, REQ-DEL-REC-01 | Áp dụng quyết định xóa trước mở dịch vụ; theo dõi cửa sổ backup | Diễn tập phục hồi; đo thời gian; kiểm tra cả dữ liệu đã xóa và dữ liệu còn hợp lệ |
| Nhà cung cấp chưa xóa nhưng hệ thống báo xong | REQ-DEL-EXTERNAL-01, REQ-DEL-EXTERNAL-02 | Theo dõi xác nhận bên ngoài theo phạm vi và lớp lưu trữ | Giả lập phản hồi tiếp nhận, hoàn tất một phần, quá hạn và hoàn tất đầy đủ |
| Log hoặc hồ sơ công việc giữ nguyên dữ liệu cần xóa | REQ-DEL-LOG-01, REQ-DEL-LOG-02 | Log tối thiểu; mã tham chiếu; quyền và thời hạn riêng | Dùng dữ liệu giả đánh dấu để kiểm tra log và thông báo ở cả luồng lỗi |

Mỗi yêu cầu cần một nhóm thực hiện, một người chịu trách nhiệm chấp nhận, liên kết tới bằng chứng và ngày kiểm chứng. Bằng chứng của một lần thử không bao phủ kho mới, thay đổi lịch backup hoặc thay đổi cách cấp liên kết tải sau đó.

## 8. Thiết kế phép kiểm chứng đúng phạm vi

### 8.1. Bộ dữ liệu thử có thể đối chiếu

Tạo một bộ dữ liệu giả gồm nhiều chủ thể, ít nhất hai tổ chức và các đối tượng có quan hệ rõ ràng. Đặt các giá trị đánh dấu riêng cho dữ liệu cần xóa, dữ liệu ngoài phạm vi và dữ liệu đang giữ lại. Phân phối chúng vào những kho đã khai báo, bao gồm phiên bản tệp và một bản sao lưu dùng cho diễn tập.

Điều này cho phép kiểm tra đồng thời hai điều: dữ liệu cần xóa đã được xử lý và dữ liệu còn hợp lệ không bị ảnh hưởng. Chỉ xác nhận “không tìm thấy bản ghi A” có thể bỏ sót việc công việc đã xóa luôn bản ghi B.

### 8.2. Kiểm thử cả thời gian và trạng thái

Đo từ T0 gốc, không đo từ lần thử lại thành công. Quan sát mốc chặn truy cập, mốc từng kho hoạt động hoàn tất và mốc bản sao còn lại được xử lý. Với tác vụ chạy theo lịch, phải xét trường hợp yêu cầu đến ngay sau lần chạy, không chỉ trường hợp thuận lợi ngay trước lịch xử lý.

Thử một đích bị lỗi trong khi các đích khác thành công. Kết quả cần cho thấy phạm vi đã hoàn tất được giữ, phần lỗi có thể thử lại, quá hạn được phát hiện và trạng thái chung chưa bị đánh dấu hoàn tất. Việc một đích trả thành công quá sớm cũng cần được đối chiếu theo loại bằng chứng mà kho đó thực sự cung cấp.

### 8.3. Phân biệt bằng chứng và giới hạn

| Bằng chứng | Điều hỗ trợ kết luận | Giới hạn cần ghi |
|---|---|---|
| Kiểm thử API và truy vấn | Không còn đọc được qua đường đã thử với danh tính đã dùng | Không tự bao phủ mọi kho hoặc mọi đường truy cập |
| Kết quả tác vụ theo từng đích | Công việc đã chạy với phạm vi và kết quả cụ thể | Cần hiểu đích xác nhận đã xóa hay chỉ đã tiếp nhận |
| Danh mục phiên bản và cấu hình vòng đời | Các bản sao được theo dõi theo lịch xử lý | Cấu hình chưa chứng minh tác vụ đã hoàn tất tại thời điểm hiện tại |
| Xác nhận của nhà cung cấp | Nhà cung cấp xác nhận trong phạm vi đã nêu | Không phải quan sát trực tiếp mọi lớp lưu trữ nội bộ của họ |
| Diễn tập phục hồi | Dữ liệu không quay lại trong kịch bản đã thử; dữ liệu hợp lệ còn dùng được | Phụ thuộc phiên bản, nguồn backup và phạm vi diễn tập |

Không cần tuyên bố mức bảo đảm vượt quá khả năng quan sát. Nếu không đủ bằng chứng cho một đích quan trọng, phải ghi rõ phần chưa xác minh và người chịu trách nhiệm xử lý. Quyết định chấp nhận rủi ro không được làm thay đổi sự thật rằng bằng chứng còn thiếu.

## 9. Những sai sót thường gặp

| Sai sót | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Xóa theo tuổi bản ghi mà không biết mục đích | Giữ quá lâu hoặc xóa dữ liệu vẫn cần cho chức năng hợp lệ | Gắn lịch xóa với mục đích, sự kiện và thẩm quyền |
| Coi cờ `deleted` là đã xóa mọi nơi | Dữ liệu còn trong kho, chỉ mục, tệp và backup | Tách mốc chặn truy cập với mốc xử lý từng lớp lưu trữ |
| Xóa bản hiện tại nhưng bỏ qua phiên bản tệp | Người có quyền phù hợp vẫn có thể đọc phiên bản cũ | Đưa phiên bản và lịch hết hạn vào danh mục phạm vi |
| Không chặn ghi lại khi đang xóa | Đồng bộ hoặc tác vụ cũ tạo lại dữ liệu | Kiểm tra quyết định xóa trên đường nhập, xử lý nền và phục hồi |
| Đặt lại đồng hồ khi thử lại | Che yêu cầu quá hạn | Giữ T0 và hạn xử lý xuyên suốt vòng đời |
| Hủy khóa dùng chung để xóa một người | Mất dữ liệu ngoài phạm vi | Phân tích phạm vi khóa và khả năng phục hồi trước khi chọn cơ chế |
| Báo hoàn tất khi mới gửi yêu cầu cho bên ngoài | Không biết dữ liệu thực sự còn ở đâu | Theo dõi xác nhận theo lớp dữ liệu và loại kết quả |
| Giữ nguyên nội dung trong bằng chứng xóa | Tạo một bản sao mới không có vòng đời | Chỉ ghi thông tin điều phối tối thiểu và quản lý vòng đời bằng chứng |
| Khôi phục backup rồi mới xử lý xóa khi dịch vụ đã mở | Dữ liệu đã xóa bị cung cấp lại trong khoảng chuyển tiếp | Áp dụng quyết định xóa trước khi mở truy cập |

## 10. Bài tập vận dụng

Một ứng dụng quản lý hồ sơ tuyển dụng cho phép xóa một hồ sơ đã kết thúc xử lý. Hồ sơ có thông tin liên hệ, tệp đính kèm với nhiều phiên bản, ghi chú nội bộ và một tệp xuất do ứng dụng tạo. Dữ liệu được lập chỉ mục tìm kiếm, chuyển qua hàng đợi để phân tích và sao lưu định kỳ. Một nhà cung cấp còn giữ bản sao tệp để xử lý; một phần ghi chú đang có quyết định giữ lại có thời hạn.

Hãy thực hiện:

1. Phân định dữ liệu được phép xóa, phần giữ lại và các bản sao ngoài phạm vi kiểm soát. Ghi rõ ai quyết định từng phạm vi.
2. Lập hồ sơ dữ liệu cần xóa, bao gồm phiên bản tệp, hàng đợi, chỉ mục, tệp xuất, nhà cung cấp và backup.
3. Đặt mốc chặn truy cập, xóa kho hoạt động và xử lý bản sao còn lại. Giải thích mốc bắt đầu đo và bằng chứng cho mỗi mốc.
4. Viết yêu cầu xác thực, phân quyền và giới hạn danh tính thực thi để chống xóa nhầm hoặc xóa trái phép.
5. Đặc tả xử lý một sự kiện phân tích đến muộn và một lần phục hồi từ backup cũ. Nêu cách tránh tạo lại dữ liệu đã xóa.
6. Thiết kế trạng thái báo cáo khi kho chính đã xóa nhưng nhà cung cấp chưa xác nhận và phần ghi chú vẫn được giữ lại.
7. Tạo ma trận truy vết, trong đó mỗi rủi ro có yêu cầu và phép kiểm chứng tương ứng, kể cả kiểm tra dữ liệu ngoài phạm vi còn nguyên.

Một phương án đạt yêu cầu phải cho biết chính xác phần nào đã được xử lý, phần nào còn chờ, vì sao được giữ và bằng chứng hỗ trợ từng kết luận. Quyết định xóa chỉ trở thành yêu cầu bảo mật có thể thực thi khi phạm vi, thời gian, trách nhiệm, hành vi khi lỗi và điều kiện hoàn tất đều đã được xác định.
