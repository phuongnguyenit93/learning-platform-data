# Vendor session recording — Ghi lại phiên truy cập của nhà cung cấp

## 1. Mục tiêu và phạm vi

Trong chương Vendor access, **vendor session recording** là khả năng ghi lại hoạt động diễn ra trong phiên truy cập của kỹ thuật viên thuộc nhà cung cấp, đối tác bảo trì hoặc đơn vị hỗ trợ bên ngoài. Trong hệ thống Privileged Access Management (PAM), bản ghi được gắn với danh tính người thực hiện, yêu cầu công việc, tài nguyên đích và quyền đã được cấp để tổ chức có thể kiểm tra lại một phiên đặc quyền.

Ví dụ, kỹ thuật viên của một nhà cung cấp cần xử lý lỗi ứng dụng trên máy chủ sản xuất. Việc họ đăng nhập thành công chỉ chứng minh cơ chế xác thực đã chấp nhận một danh tính. Tổ chức còn cần biết phiên đó thuộc yêu cầu nào, có truy cập đúng máy chủ được duyệt không, đã chạy lệnh gì trong phạm vi có thể quan sát, có truyền tệp hay không và phiên đã bị chấm dứt đúng thời hạn chưa.

Sau bài học, người học có thể:

- Phân biệt bản ghi phiên với nhật ký xác thực, nhật ký lệnh và nhật ký nghiệp vụ.
- Xác định điểm thu thập bằng chứng cho SSH, RDP và các kênh truy cập bổ sung.
- Thiết kế liên kết giữa danh tính kỹ thuật viên, quyền JIT/JEA, tài khoản đích và bản ghi.
- Xử lý phiên thiếu bản ghi, gián đoạn recorder hoặc truy cập vòng qua PAM.
- Bảo vệ nội dung ghi được, kiểm tra tính toàn vẹn và quản lý việc xem lại.
- Xây dựng tiêu chí nghiệm thu cho một phiên bảo trì của nhà cung cấp.

Bản ghi phục vụ giám sát, điều tra và kiểm toán. Nó không thay thế việc kiểm kê tài khoản, cấp quyền tối thiểu, dùng vault, luân chuyển credential hay thu hồi quyền truy cập sau công việc.

## 2. Bản ghi phiên cung cấp loại bằng chứng nào?

### 2.1. Bốn lớp dữ liệu cần phân biệt

| Lớp dữ liệu | Câu hỏi được hỗ trợ | Ví dụ | Giới hạn cần nhớ |
|---|---|---|---|
| Nhật ký xác thực | Ai đã vượt qua bước đăng nhập, bằng cơ chế nào? | Danh tính liên kết, MFA, thời điểm đăng nhập | Không mô tả đầy đủ hoạt động sau đăng nhập |
| Nhật ký điều khiển phiên | Phiên nào được mở, theo quyền nào, khi nào kết thúc? | Session ID, grant ID, đích truy cập, lý do đóng | Không tự chứa nội dung thao tác |
| Bản ghi tương tác | Người dùng đã nhìn thấy hoặc thực hiện những gì trên kênh được ghi? | Luồng terminal, màn hình RDP, sự kiện bàn phím theo khả năng sản phẩm | Có điểm mù về tác động hệ thống và hoạt động ngoài kênh |
| Nhật ký tại đích | Hệ điều hành hoặc ứng dụng ghi nhận thay đổi nào? | Thực thi tiến trình, thay đổi cấu hình, giao dịch ứng dụng | Có thể thiếu, trễ hoặc chịu tác động khi máy đích bị chiếm quyền |

Một kết luận đáng tin cậy thường cần kết hợp nhiều lớp. Nếu video RDP cho thấy người dùng bấm nút “Lưu”, điều đó chưa chứng minh dữ liệu đã được cập nhật thành công. Cần đối chiếu với nhật ký ứng dụng hoặc trạng thái hệ thống sau thao tác.

### 2.2. Ghi màn hình không đồng nghĩa có nhật ký lệnh

SSH có thể được ghi bằng luồng đầu vào/đầu ra terminal, nhật ký lệnh có cấu trúc hoặc kết hợp các phương thức. RDP thường có bản ghi màn hình hoặc các khung hình cùng metadata, tùy giải pháp.

Một dòng hiển thị trên terminal không phải lúc nào cũng là một lệnh đã được hệ điều hành thực thi. Người dùng có thể chỉnh sửa dòng, dùng ứng dụng toàn màn hình, chạy script hoặc mở một chương trình tạo ra các tiến trình con. Ngược lại, một lệnh khởi chạy script không tự bộc lộ toàn bộ nội dung và tác động của script đó.

Với giao diện đồ họa, nhận dạng chữ trên màn hình có thể giúp tìm kiếm nhưng không nên được xem là bằng chứng duy nhất về một thao tác nghiệp vụ. Cần giữ liên hệ tới khung hình gốc, thời điểm và sự kiện tại đích.

### 2.3. Ghi phiên không tự ngăn hành vi sai

Một phiên được ghi đầy đủ vẫn có thể thực hiện thay đổi phá hỏng hệ thống nếu quyền được cấp quá rộng. Trong mô hình PAM:

- **Least privilege** giới hạn tài nguyên và hành động.
- **JIT** giới hạn thời gian quyền có hiệu lực.
- **JEA hoặc cơ chế ủy quyền tương đương** giới hạn chức năng quản trị được phép.
- **Vault và credential injection** giảm nhu cầu tiết lộ credential cho kỹ thuật viên.
- **Session recording** cung cấp khả năng quan sát và bằng chứng trong phạm vi kênh được ghi.
- **Giám sát và thu hồi phiên** giúp phản ứng khi có dấu hiệu bất thường.

Các lớp này bổ sung cho nhau. Không nên dùng khả năng phát lại phiên để biện minh cho việc cấp tài khoản quản trị thường trực cho nhà cung cấp.

## 3. Kiến trúc và luồng ghi phiên

### 3.1. Điểm đặt recorder

Một kiến trúc phổ biến đưa truy cập của nhà cung cấp qua cổng hoặc broker PAM:

```text
Kỹ thuật viên nhà cung cấp
          |
          | danh tính cá nhân + MFA
          v
Cổng truy cập / Broker PAM <---- Quyền JIT + yêu cầu công việc đã duyệt
          |
          +---- Điều khiển phiên và kiểm tra sức khỏe recorder
          |
          +---- Thu tương tác ----> Recorder ----> Kho bằng chứng
          |                            |
          |                            +---- Manifest + sự kiện chất lượng
          |
          v
Tài nguyên đích
          |
          +---- Nhật ký hệ điều hành / ứng dụng ----> Hệ thống giám sát
```

Sơ đồ mô tả trách nhiệm logic. Recorder có thể nằm trong gateway, chạy như dịch vụ tách biệt hoặc dùng agent tại đích. Cần xác minh khả năng thực tế của từng giải pháp, giao thức và cấu hình triển khai.

Điểm thu thập phải nhìn thấy loại tương tác cần ghi. Một thiết bị chỉ chuyển tiếp luồng mã hóa mà không kết thúc hoặc xử lý giao thức ở lớp phù hợp thường không thể tự tái tạo nội dung terminal hay màn hình từ các gói tin đó.

### 3.2. Chuỗi xử lý của một phiên

1. Kỹ thuật viên xác thực bằng danh tính cá nhân đã được liên kết với tổ chức nhà cung cấp.
2. PAM kiểm tra hợp đồng hoặc quan hệ hỗ trợ còn hiệu lực, yêu cầu công việc, người duyệt, tài nguyên, giao thức và cửa sổ thời gian.
3. Hệ thống tạo Session ID và liên kết nó với grant JIT cụ thể.
4. Trước khi mở đường tới tài nguyên đích, hệ thống kiểm tra recorder, dung lượng đệm và khả năng bảo vệ dữ liệu ghi.
5. PAM cấp kết nối bằng tài khoản đích phù hợp; nếu hỗ trợ thì credential được đưa vào phiên mà không hiển thị cho kỹ thuật viên.
6. Trong phiên, dữ liệu tương tác và sự kiện điều khiển được thu theo giao thức đã cấu hình.
7. Khi phiên đóng, hết hạn hoặc bị thu hồi, hệ thống kết thúc các kênh liên quan và hoàn thiện bản ghi.
8. Hệ thống xác nhận các phần dữ liệu đã được lưu, lập manifest, kiểm tra chất lượng và phát hành trạng thái cuối.
9. Nếu có credential thực sự bị tiết lộ hoặc chính sách yêu cầu, quy trình quản lý credential tiếp tục xử lý luân chuyển hoặc thu hồi tương ứng.

Một thông báo “recording enabled” lúc bắt đầu không đủ để xác nhận toàn bộ chuỗi này đã thành công.

### 3.3. Cổng kiểm soát trước khi kết nối

Việc kiểm tra quyền truy cập và việc bảo đảm có thể ghi phiên cần được gắn vào cùng quyết định mở kết nối. Nếu gateway mở phiên trước rồi mới khởi động recorder bất đồng bộ, những giây đầu có thể bị bỏ sót.

Có thể định nghĩa cổng kiểm soát như sau:

```text
Chỉ mở kết nối đặc quyền khi:
  danh tính đã được xác thực
  VÀ grant còn hiệu lực và đúng tài nguyên
  VÀ chính sách kênh đã được áp dụng
  VÀ recorder đã sẵn sàng theo tiêu chuẩn của loại tài nguyên
  VÀ phiên có định danh để liên kết bằng chứng
```

“Sẵn sàng” không nhất thiết có nghĩa mọi byte đã nằm ở kho lưu trữ cuối cùng. Nó có thể cho phép ghi vào bộ đệm bền vững được bảo vệ khi đường truyền tới kho đang gián đoạn. Điều kiện đó phải được định nghĩa rõ, đo được và có giới hạn.

## 4. Liên kết danh tính và ngữ cảnh công việc

### 4.1. Từ kỹ thuật viên tới tài khoản đích

Nhà cung cấp có thể dùng danh tính liên kết để vào PAM, trong khi kết nối tới máy đích dùng một tài khoản quản trị kỹ thuật do tổ chức quản lý. Vì vậy cần giữ được chuỗi:

```text
vendor_org_id
    -> human_subject_id
    -> authentication_event_id
    -> access_request_id
    -> approval_id / grant_id
    -> session_id
    -> target_account_ref + target_resource_id
    -> recording_id
```

Không dùng tên hiển thị hoặc địa chỉ IP làm khóa duy nhất. Tên có thể trùng hoặc thay đổi; nhiều kỹ thuật viên có thể đi qua cùng NAT. Định danh ổn định giúp giữ lịch sử ngay cả khi tài khoản nhà cung cấp đã được vô hiệu hóa.

Nếu nhà cung cấp dùng chung một danh tính đầu vào, bản ghi không thể tự khôi phục một cách đáng tin cậy người thực sự đứng sau phiên. Cần giải quyết vấn đề danh tính trước khi dựa vào tính quy trách nhiệm của bản ghi.

### 4.2. Metadata tối thiểu

| Nhóm | Dữ liệu nên có | Mục đích |
|---|---|---|
| Người và tổ chức | ID cá nhân, ID nhà cung cấp, phương thức xác thực | Quy trách nhiệm và điều tra |
| Cấp quyền | Request ID, grant ID, người duyệt, thời hạn, phiên bản chính sách | Chứng minh phạm vi được cho phép |
| Đích truy cập | Resource ID, môi trường, giao thức, tham chiếu tài khoản đích | Xác định đối tượng tác động |
| Phiên | Session ID, parent session nếu có, gateway, thời điểm mở/đóng, lý do đóng | Dựng lại diễn biến |
| Bản ghi | Recording ID, segment ID, trạng thái thu thập, khoảng trống, manifest | Đánh giá độ đầy đủ |
| Giám sát | Cảnh báo, người quan sát, lệnh chấm dứt, kết quả thu hồi | Giải thích phản ứng vận hành |

Không đưa mật khẩu, khóa riêng hoặc token còn hiệu lực vào metadata. Nếu cần liên hệ với vault, dùng một định danh tham chiếu không chứa giá trị bí mật.

### 4.3. Mốc thời gian và reconnect

Nên có mốc thời gian thống nhất, kèm múi giờ rõ ràng, cùng số thứ tự sự kiện hoặc segment. Trong nội bộ một phiên, số thứ tự hoặc đồng hồ đơn điệu giúp phát hiện mất đoạn khi đồng hồ hệ thống thay đổi.

Một lần ngắt kết nối phía người dùng có thể để lại phiên RDP đang chạy trên máy đích. Khi người dùng kết nối lại, hệ thống cần xác định đó là tiếp tục phiên cũ hay mở phiên mới, đồng thời liên kết các đoạn ghi phù hợp.

Không tự nối hai bản ghi chỉ vì chúng cùng username và gần nhau về thời gian. Việc ghép sai có thể khiến hoạt động của người này bị quy cho người khác.

## 5. Phạm vi ghi theo giao thức và các kênh phụ

### 5.1. SSH và terminal

Với SSH, cần xác minh riêng những chế độ được phép:

- Shell tương tác có terminal.
- Thực thi lệnh không cấp terminal.
- SFTP, SCP hoặc cơ chế truyền tệp được sản phẩm hỗ trợ.
- Port forwarding, tunneling và các kênh SSH bổ sung.
- Kết nối tiếp từ máy đích sang máy khác.

Một chính sách ghi terminal tốt không tự chứng minh SFTP cũng đã được quan sát đầy đủ. Một tunnel có thể mang lưu lượng tới tài nguyên khác mà bản ghi shell không mô tả được nội dung.

Biện pháp triển khai gồm giới hạn các chế độ SSH cần dùng, chặn forwarding không cần thiết, ghi sự kiện truyền tệp riêng và kiểm soát đường mạng từ máy đích tới các hệ thống khác. Không chỉ dựa vào việc phát lại terminal để suy ra đã không có truyền tệp.

Khi kỹ thuật viên dùng công cụ tương tác toàn màn hình hoặc thực thi script, nhật ký tại đích giúp bổ sung tiến trình, tài khoản thực thi và thay đổi thực tế. Khả năng ghi đầu vào/đầu ra cụ thể phải được kiểm thử với bộ công cụ nhà cung cấp thực sự sử dụng.

### 5.2. RDP và giao diện đồ họa

Với RDP, cần đánh giá cả bản ghi màn hình và các chức năng chia sẻ:

- Clipboard giữa máy người dùng và máy đích.
- Ánh xạ ổ đĩa, chuyển tệp, in và thiết bị ngoại vi.
- Nhiều màn hình, thay đổi độ phân giải, khóa màn hình và reconnect.
- Chuyển phiên người dùng hoặc mở ứng dụng bằng tài khoản khác.
- Các thao tác diễn ra nền, không thể hiện trực tiếp trên màn hình.

Nếu cho phép truyền tệp qua ổ đĩa được ánh xạ, bản ghi video có thể chỉ cho thấy một thao tác kéo thả mà không có danh sách đầy đủ các byte đã truyền. Cần chính sách kênh phụ và sự kiện truyền tệp tương ứng nếu tổ chức yêu cầu bằng chứng đó.

Ghi phím cũng có thể làm tăng nguy cơ thu thập bí mật. Không mặc định bật mọi hình thức ghi đầu vào chỉ vì hệ thống hỗ trợ; cần cân đối yêu cầu bằng chứng với việc bảo vệ credential và dữ liệu nhạy cảm.

### 5.3. Console web và công cụ hỗ trợ riêng

Kỹ thuật viên có thể mở một console quản trị web từ jump host hoặc dùng phần mềm hỗ trợ của hãng. Nếu phiên này nằm ngoài điểm thu thập đã thiết kế, tổ chức có thể chỉ ghi được bước mở trình duyệt hoặc ứng dụng ban đầu.

Cần kiểm kê từng đường truy cập và xác định:

1. Kênh nào được broker PAM kiểm soát.
2. Nội dung nào thực sự được ghi.
3. Tài nguyên nào có thể được tiếp cận từ trong phiên.
4. Nhật ký bổ sung nào cần thu tại ứng dụng hoặc thiết bị.
5. Kênh nào bị cấm vì chưa đáp ứng chính sách ghi phiên.

Một kết nối hỗ trợ chạy nền hoặc được thiết bị tự khởi tạo tới hạ tầng nhà cung cấp có thể không đi qua gateway dành cho người dùng. Kiểm kê đường truy cập phải bao gồm cả loại kết nối này.

### 5.4. Chặn đường vòng

Ghi phiên chỉ có giá trị bao phủ nếu các đường truy cập đặc quyền khác đã được kiểm soát. Cần đối chiếu với inventory để phát hiện VPN cũ, firewall rule cũ, tài khoản local của nhà cung cấp, khóa SSH tồn tại lâu dài hoặc công cụ remote support chưa được quản lý.

Để xác minh đường vòng, có thể thử trong môi trường kiểm thử: dùng danh tính đã duyệt nhưng kết nối trực tiếp tới tài nguyên ngoài broker. Kết quả mong đợi là kết nối bị từ chối hoặc được xử lý theo một tuyến được phê duyệt và có bằng chứng tương đương.

## 6. Độ đầy đủ của bản ghi và trạng thái phiên

### 6.1. Tách trạng thái truy cập khỏi trạng thái bằng chứng

Một phiên có thể đóng bình thường trong khi bản ghi vẫn đang tải lên kho. Vì vậy cần theo dõi hai nhóm trạng thái độc lập.

Ví dụ trạng thái điều khiển phiên:

```text
REQUESTED -> AUTHORIZED -> CONNECTING -> ACTIVE -> CLOSED
                                  |          |
                                  +-> DENIED +-> TERMINATED
```

Ví dụ trạng thái bằng chứng:

```text
INITIALIZING -> CAPTURING -> FINALIZING -> COMPLETE
                    |             |
                    v             v
                 DEGRADED     INCOMPLETE / FAILED
```

Đây là mô hình minh họa, không phải tên trạng thái bắt buộc của sản phẩm. Một phiên có thể từng bị DEGRADED rồi phục hồi. Trạng thái cuối phải giữ được thông tin về khoảng trống đã xảy ra; không chỉ thay nhãn thành COMPLETE và xóa dấu vết lỗi.

### 6.2. Định nghĩa COMPLETE

Một bản ghi chỉ nên được coi là hoàn chỉnh khi đáp ứng các điều kiện kỹ thuật đã đặt ra, chẳng hạn:

- Có metadata và liên kết danh tính, grant, tài nguyên đầy đủ.
- Có dấu mốc bắt đầu/kết thúc hoặc lý do kết thúc bất thường.
- Các segment được kỳ vọng đã hiện diện và có thứ tự.
- Không có khoảng trống chưa được giải thích trong kênh bắt buộc ghi.
- Kiểm tra toàn vẹn từng segment và manifest thành công.
- Dữ liệu đã được lưu theo yêu cầu độ bền, không chỉ tồn tại trong bộ đệm tạm.
- Việc phát lại hoặc kiểm tra định dạng đáp ứng tiêu chuẩn kỹ thuật của hệ thống.

COMPLETE là kết luận về chất lượng thu thập theo định nghĩa đó. Nó không khẳng định công việc của nhà cung cấp đã được thực hiện đúng, cũng không bảo đảm không tồn tại tác động ngoài tầm quan sát.

### 6.3. Chỉ số theo dõi

Một số chỉ số hữu ích:

| Chỉ số | Cách hiểu | Cảnh báo khi diễn giải |
|---|---|---|
| Tỷ lệ phiên có liên kết bản ghi | Phiên thuộc diện phải ghi và có Recording ID / tổng phiên thuộc diện phải ghi | Có ID chưa chứng minh có nội dung hợp lệ |
| Tỷ lệ bản ghi hoàn chỉnh | Phiên đạt tiêu chí COMPLETE / tổng phiên thuộc diện phải ghi | Cần tính cả phiên bị lỗi trước khi hoàn thiện |
| Khoảng trống ghi nhận | Thời gian mất thu thập được xác định trong từng phiên | Không có sự kiện lỗi chưa chắc không có mất dữ liệu |
| Độ trễ sẵn sàng | Thời gian từ đóng phiên đến khi bằng chứng có thể truy xuất | Phải tách khỏi thời gian bắt đầu ghi |
| Số phiên ngoại lệ | Phiên tiếp tục khi điều kiện ghi không đạt | Cần có người duyệt và lý do |
| Mức sử dụng bộ đệm | Dữ liệu đang chờ chuyển và dung lượng còn lại | Tốc độ tăng và thời gian đầy quan trọng hơn một con số đơn lẻ |

Mẫu số phải được xác định từ danh sách phiên do lớp điều khiển tạo ra, không chỉ từ những bản ghi đã tồn tại. Nếu chỉ đếm trong kho recorder, các phiên hoàn toàn thiếu bản ghi có thể biến mất khỏi báo cáo.

## 7. Xử lý sự cố recorder

### 7.1. Chính sách trước và trong phiên

Có hai thời điểm cần quyết định: trước khi mở phiên và sau khi phiên đã hoạt động.

| Tình huống | Xử lý minh họa cho tài nguyên rủi ro cao | Bằng chứng cần lưu |
|---|---|---|
| Recorder chưa sẵn sàng trước kết nối | Từ chối hoặc chờ khôi phục | Lý do từ chối, request ID, kiểm tra sức khỏe |
| Kho cuối gián đoạn nhưng bộ đệm bền vững vẫn đạt yêu cầu | Có thể tiếp tục trong giới hạn được duyệt | Vị trí đệm, dung lượng, tuổi dữ liệu, trạng thái tải lên |
| Recorder dừng thu, bộ đệm không an toàn | Chặn thêm thao tác hoặc chấm dứt theo quy trình | Thời điểm mất thu, khoảng trống, hành động điều khiển |
| Bộ đệm sắp đầy | Giảm tiếp nhận phiên mới; xử lý phiên đang chạy theo chính sách | Ngưỡng, cảnh báo, quyết định vận hành |
| Kết thúc phiên nhưng thiếu segment | Đánh dấu INCOMPLETE và mở xử lý sự cố bằng chứng | Segment thiếu, mốc thời gian, người phụ trách |

Các ngưỡng và hành động cụ thể thuộc chính sách của tổ chức. Không dùng một giá trị thời gian hoặc tỷ lệ mặc định cho mọi tài nguyên.

### 7.2. Fail-closed và ngoại lệ có kiểm soát

**Fail-closed** nghĩa là không cho phép truy cập tiếp khi điều kiện bắt buộc của kiểm soát không còn đáp ứng. Tuy nhiên, việc cắt ngay một phiên đang cập nhật firmware hoặc thực hiện thay đổi không thể ngắt giữa chừng có thể tạo thêm tác động vận hành.

Do đó, cần định nghĩa trước cách xử lý theo loại công việc: có cho chờ trong giới hạn không, có thể dừng thao tác an toàn ở đâu, ai có quyền quyết định và có kênh khôi phục nào. Không để kỹ thuật viên tự quyết định tiếp tục mà không có dấu vết.

Nếu tổ chức cho phép ngoại lệ khẩn cấp, ngoại lệ cần có phạm vi, thời hạn, người chịu trách nhiệm, lý do và hình thức giám sát bổ sung được chấp thuận. Biên bản của người quan sát có thể bổ sung bằng chứng, nhưng không được trình bày như một bản ghi phiên đầy đủ.

### 7.3. Thu hồi phải chạm tới phiên đang hoạt động

Vô hiệu hóa tài khoản trong IdP hoặc xóa một grant có thể chỉ chặn lần đăng nhập kế tiếp. Phiên đã có kết nối, token còn hiệu lực, tunnel hoặc phiên RDP bị ngắt ở phía client vẫn có thể tồn tại.

Quy trình thu hồi cần kiểm tra ít nhất:

1. Broker đã ngừng hoặc từ chối các kênh đang hoạt động theo khả năng hệ thống.
2. Các kết nối và kênh phụ gắn với Session ID đã được xử lý.
3. Máy đích không còn phiên hoặc tiến trình do nhà cung cấp khởi chạy ngoài phạm vi được phép.
4. Credential đã tiết lộ hoặc cấp ra ngoài được thu hồi, luân chuyển hay xử lý theo loại credential.
5. Sự kiện thu hồi và kết quả thực tế được liên kết với bản ghi.

Đóng cửa sổ phát lại hoặc ngắt màn hình người dùng khỏi cổng truy cập không phải bằng chứng đủ rằng hoạt động trên máy đích đã chấm dứt.

## 8. Bảo vệ nội dung và tính toàn vẹn

### 8.1. Bản ghi có thể chứa dữ liệu nhạy cảm

Bản ghi đặc quyền có thể vô tình chứa khóa truy cập, thông tin khách hàng, cấu hình hạ tầng, dữ liệu vận hành hoặc thông tin cá nhân. Vì vậy người có quyền quản trị PAM không nên mặc nhiên có quyền xem mọi bản ghi.

Có thể tách các vai trò:

- Người quản trị nền tảng cấu hình và vận hành recorder.
- Người kiểm tra được xem bản ghi trong phạm vi công việc được giao.
- Người xử lý sự cố có quyền truy xuất theo hồ sơ sự cố.
- Người quản lý lưu giữ xử lý hết hạn hoặc yêu cầu giữ lại.
- Người quản lý khóa thực hiện nhiệm vụ mật mã theo phân quyền.

Nếu cần xem hoặc xuất bản ghi đặc biệt nhạy cảm, có thể yêu cầu người thứ hai phê duyệt theo chính sách. Mọi lần tìm kiếm, xem, tải xuống, xuất hoặc xóa cần để lại nhật ký có người thực hiện và lý do.

### 8.2. Giảm thu thập bí mật ngay từ đầu

Biện pháp ưu tiên là tránh đưa bí mật vào kênh tương tác: dùng credential injection khi phù hợp, hạn chế lệnh in biến môi trường nhạy cảm, tránh truyền mật khẩu trên dòng lệnh và thiết kế thao tác bảo trì không cần hiển thị dữ liệu thật.

Che vùng màn hình hoặc redaction có thể giảm lộ lọt, nhưng cũng tạo điểm mù. Nhận dạng tự động không bảo đảm phát hiện mọi bí mật, và một bản video đã che không loại bỏ bí mật nếu luồng phím hoặc log phụ vẫn giữ nó.

Nếu tạo bản đã che để chia sẻ, cần phân biệt rõ bản gốc được bảo vệ và bản dẫn xuất. Bản dẫn xuất nên có định danh, liên kết nguồn, thời điểm tạo và dấu vết xử lý. Không âm thầm sửa nội dung bản gốc rồi tiếp tục gọi đó là bằng chứng nguyên trạng.

### 8.3. Hash, chữ ký và kho chống sửa đổi

Một thiết kế có thể chia bản ghi thành các segment, tính hash từng phần và tạo manifest liệt kê thứ tự, mốc thời gian cùng hash tương ứng.

Hash giúp phát hiện thay đổi khi có giá trị tham chiếu đáng tin cậy để đối chiếu. Nếu một người sửa được cả dữ liệu lẫn manifest không được bảo vệ, họ có thể tính lại hash; chỉ có hash không đủ để chứng minh nguồn gốc hoặc chống sửa đổi có chủ đích.

Có thể tăng độ tin cậy bằng cách bảo vệ manifest bằng chữ ký hoặc cơ chế xác thực phù hợp, tách quyền ghi dữ liệu khỏi quyền quản lý khóa, lưu nhật ký ở miền quyền khác và sử dụng lưu trữ có chính sách bất biến theo khả năng hạ tầng.

Mã hóa khi truyền và khi lưu bảo vệ tính bí mật trong các tình huống nhất định. Nó không tự chứng minh bản ghi đầy đủ hoặc người dùng đã thực hiện thao tác hợp lệ. Việc quản lý khóa, thời hạn khóa và khả năng giải mã trong suốt thời gian lưu giữ cũng cần được kiểm thử.

### 8.4. Lưu giữ và bàn giao bằng chứng

Thời gian lưu giữ nên dựa trên mục đích công việc, yêu cầu hợp đồng, phân loại dữ liệu và chính sách đã được tổ chức xác định. Không mặc định giữ vô hạn.

Khi một hồ sơ điều tra cần giữ lại bản ghi, cơ chế giữ bằng chứng phải ngăn việc xóa tự động theo chính sách được phê duyệt. Sau khi hết lý do giữ, dữ liệu quay về quy trình xử lý vòng đời phù hợp.

Một lần xuất bằng chứng nên ghi nhận:

- Ai yêu cầu, ai phê duyệt và mục đích sử dụng.
- Session ID, Recording ID và phạm vi thời gian được xuất.
- Bản gốc hay bản dẫn xuất đã che dữ liệu.
- Hash của gói xuất, định dạng và công cụ cần để đọc.
- Người bàn giao, người nhận và thời điểm bàn giao.
- Kết quả kiểm tra toàn vẹn khi nhận.

Hash của gói xuất chứng minh gói đó không thay đổi so với giá trị tham chiếu đã bảo vệ, không tự chứng minh nguồn đã ghi đầy đủ trước lúc xuất.

Thông báo cho kỹ thuật viên về việc ghi phiên nên được thực hiện trước khi truy cập theo chính sách và quy trình của tổ chức. Không mặc định một thông báo trên giao diện đã giải quyết mọi yêu cầu về quyền riêng tư.

## 9. Ví dụ mô hình dữ liệu và quyết định điều khiển

Các ví dụ dưới đây là mô hình minh họa để học thiết kế, không phải cấu hình có thể nhập trực tiếp vào một sản phẩm PAM.

### 9.1. Sự kiện điều khiển phiên

```json
{
  "event_type": "vendor_session.started",
  "event_id": "evt-example-001",
  "occurred_at": "2026-06-12T02:00:00Z",
  "session_id": "vs-example-005",
  "vendor_org_id": "vendor-ops-a",
  "human_subject_id": "subject-482",
  "authentication_event_id": "auth-219",
  "access_request_id": "req-736",
  "grant_id": "grant-736-1",
  "target_resource_id": "prod-app-node-02",
  "target_account_ref": "vault-account-91",
  "protocol": "ssh",
  "recording_id": "rec-example-005",
  "recording_policy_version": "vendor-prod-v3",
  "recorder_state": "CAPTURING"
}
```

Ví dụ chỉ giữ tham chiếu tài khoản trong vault. Không đưa credential thật vào sự kiện để làm bản ghi “đầy đủ hơn”.

### 9.2. Manifest đơn giản

```yaml
recording_id: rec-example-005
session_id: vs-example-005
capture_scope:
  - ssh_terminal
  - session_control_events
segments:
  - sequence: 1
    object_ref: evidence/rec-example-005/segment-0001
    started_at: "2026-06-12T02:00:00Z"
    ended_at: "2026-06-12T02:05:00Z"
    digest_algorithm: SHA-256
    digest: "<hash tính từ byte thực của segment>"
known_gaps: []
final_state: COMPLETE
manifest_authentication_ref: "<tham chiếu xác thực manifest>"
```

Bộ manifest này chỉ minh họa trường dữ liệu. Trong triển khai thực, mốc bắt đầu/kết thúc, số segment kỳ vọng, cách đóng gói, cơ chế xác thực và tiêu chí COMPLETE phải nhất quán với hệ thống thu thập.

Một manifest được xác thực vẫn không chứng minh rằng recorder đã nhìn thấy mọi tác động tại máy đích. Phạm vi ghi phải luôn được giữ cùng bằng chứng.

### 9.3. Pseudocode xử lý mất khả năng ghi

```text
on_capture_health_changed(session, health):
    policy = load_bound_policy(session.policy_version)

    if health.capture_is_valid:
        record_health_event(session, health)
        return

    preserve_known_gap_start(session)
    alert_internal_owner(session, health)

    if policy.allows_protected_buffering
       and health.durable_buffer_is_valid
       and health.remaining_capacity_meets_policy:
        mark_evidence_state(session, DEGRADED)
        apply_buffering_time_limit(session, policy)
        return

    block_new_sessions_for_affected_route()

    if policy.requires_termination_for_this_work:
        terminate_session_and_related_channels(session)
        verify_target_session_end(session)
    else:
        invoke_preapproved_safe_stop_or_exception_process(session)

    preserve_control_event_even_if_capture_is_unavailable(session)
    mark_evidence_for_reconciliation(session)
```

Luồng điều khiển cần có nơi ghi sự kiện độc lập hoặc hàng đợi bền vững phù hợp để tránh mất cả thông báo lỗi khi recorder gặp sự cố. Không ghi nhãn COMPLETE chỉ vì phiên đã bị chấm dứt thành công.

## 10. Tình huống thực hành: bảo trì ngoài giờ

### 10.1. Bối cảnh

Nhà cung cấp được phép xử lý một lỗi trên máy chủ ứng dụng sản xuất qua SSH trong cửa sổ 30 phút. Kỹ thuật viên có danh tính cá nhân, xác thực MFA và grant JIT chỉ tới một máy đích. Chính sách yêu cầu ghi terminal, chặn forwarding và chỉ cho phép truyền gói chẩn đoán qua một kênh tệp được kiểm soát riêng.

Các con số trong tình huống dùng để luyện tập, không phải thời hạn hay ngưỡng khuyến nghị cho mọi hệ thống.

Tại phút thứ 12, đường truyền tới kho bằng chứng bị gián đoạn. Recorder vẫn thu vào bộ đệm bền vững được mã hóa. Tại phút thứ 16, recorder mất khả năng thu và báo khoảng trống. Kỹ thuật viên vẫn đang sửa cấu hình.

### 10.2. Phân tích quyết định

**Từ phút 12 tới trước phút 16:** chưa thể kết luận mất nội dung nếu bộ đệm vẫn thu đầy đủ và đáp ứng giới hạn đã duyệt. Hệ thống cần theo dõi dung lượng, độ tuổi dữ liệu đang chờ, khả năng khôi phục và chặn phiên mới nếu ngưỡng yêu cầu.

**Từ phút 16:** điều kiện bảo đảm ghi phiên đã thay đổi. Có một khoảng trống cần được ghi nhận rõ. Nếu công việc sửa cấu hình thuộc loại có thể dừng an toàn và chính sách yêu cầu chấm dứt khi mất ghi, broker phải dừng phiên cùng kênh phụ, sau đó xác minh tại đích.

Nếu công việc thuộc loại không thể ngắt ngay, quy trình dừng an toàn hoặc ngoại lệ khẩn cấp đã duyệt phải được kích hoạt. Người trực nội bộ chịu trách nhiệm quyết định trong phạm vi chính sách; kỹ thuật viên không tự kéo dài quyền.

### 10.3. Sau khi recorder phục hồi

Người vận hành cần:

1. Đối chiếu Session ID với toàn bộ segment đã lưu và đang nằm trong bộ đệm.
2. Xác nhận segment nào đã chuyển thành công, có trùng hoặc thiếu không.
3. Lập thời tuyến về thời điểm lỗi, thời điểm chấm dứt và hoạt động tại đích.
4. Giữ trạng thái INCOMPLETE nếu khoảng trống không thể phục hồi.
5. Đối chiếu nhật ký hệ điều hành, thay đổi cấu hình và kết quả kiểm tra dịch vụ.
6. Kiểm tra grant đã hết hiệu lực, không còn phiên hoặc kênh được tạo ra ngoài phạm vi.
7. Gắn sự cố recorder với hồ sơ công việc và quy trình khắc phục.

Không mở một phiên mới rồi dùng bản ghi của phiên mới để lấp danh nghĩa cho thời gian đã mất của phiên cũ. Nhật ký tại đích có thể bổ sung diễn biến, nhưng không tái tạo chắc chắn màn hình hoặc tương tác đã không được ghi.

### 10.4. Kết quả đạt yêu cầu

Một kết quả kỹ thuật đạt yêu cầu trong tình huống này không nhất thiết có nhãn COMPLETE. Kết quả đúng có thể là: phiên đã được dừng theo chính sách, khoảng trống được công khai, bằng chứng còn lại được bảo vệ, tác động được kiểm tra và quyền của nhà cung cấp đã được thu hồi.

Giấu khoảng trống để làm đẹp tỷ lệ bản ghi hoàn chỉnh là lỗi kiểm soát nghiêm trọng hơn việc ghi nhận trung thực một phiên chưa đầy đủ.

## 11. Kiểm thử nghiệm thu

Bộ kiểm thử nên chạy trong môi trường được cho phép, dùng dữ liệu giả và đúng các giao thức nhà cung cấp sẽ sử dụng.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Phiên SSH thông thường | Mở phiên, chạy lệnh vô hại, đóng phiên | Liên kết đúng danh tính và grant, phát lại được, trạng thái bằng chứng hợp lệ |
| RDP reconnect | Ngắt client rồi kết nối lại theo quy trình | Không nhầm người, phân biệt rõ đoạn ngắt và đoạn tiếp tục |
| Thực thi SSH không terminal | Gửi tác vụ kiểm thử được cho phép | Bị chặn hoặc được ghi theo chính sách thực sự hỗ trợ |
| Truyền tệp | Dùng kênh tệp đã duyệt và thử kênh bị cấm | Có sự kiện tương ứng; kênh bị cấm không hoạt động |
| Đường vòng | Thử kết nối trực tiếp tới đích ngoài broker | Không có đường đặc quyền trái chính sách |
| Kho lưu trữ mất kết nối | Mô phỏng lỗi mạng tới kho | Bộ đệm và cảnh báo đúng; không báo hoàn tất khi chưa bền vững |
| Recorder mất thu | Dừng thành phần thu trong môi trường kiểm thử | Có khoảng trống và hành động điều khiển đúng chính sách |
| Grant hết hạn giữa phiên | Chờ tới hạn của grant kiểm thử | Phiên và kênh phụ được xử lý đúng, không chỉ chặn đăng nhập mới |
| Người không có quyền xem | Yêu cầu phát lại hoặc xuất bản ghi | Bị từ chối và có audit event |
| Bản ghi bị sửa | Thay một bản sao kiểm thử của segment | Kiểm tra toàn vẹn thất bại rõ ràng |
| Hết thời hạn lưu | Dùng chính sách thử nghiệm với dữ liệu giả | Dữ liệu và bản dẫn xuất được xử lý theo vòng đời; cơ chế giữ bằng chứng hoạt động |
| Khôi phục bằng chứng | Khôi phục một bản ghi kiểm thử cùng metadata | Có thể giải mã, xác thực và phát lại bằng công cụ được quản lý |

Không sửa bản ghi sản xuất để thử khả năng phát hiện can thiệp. Dùng bản sao hoặc bộ dữ liệu thử có nguồn gốc rõ ràng.

Nghiệm thu cũng cần kiểm tra tình huống một nhà cung cấp có nhiều kỹ thuật viên cùng hoạt động. Mỗi phiên phải giữ được danh tính người tham gia; nếu giải pháp hỗ trợ cùng quan sát hoặc chia sẻ phiên, cần phân biệt người chỉ xem với người có quyền điều khiển và các lần chuyển quyền.

## 12. Lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng bật tùy chọn ghi là đã có bằng chứng | Có phiên không lưu được hoặc không phát lại được | Đo chất lượng từ đầu tới cuối và đối chiếu với danh sách phiên |
| Dùng tài khoản đầu vào chung cho cả nhà cung cấp | Khó xác định ai thực hiện | Dùng danh tính cá nhân và giữ liên kết lịch sử |
| Ghi terminal nhưng cho tunnel tự do | Có hoạt động ngoài phạm vi bản ghi | Giới hạn kênh và kiểm soát đường mạng |
| Gắn bản ghi với username thay cho Session ID | Ghép sai phiên hoặc sai người khi reconnect | Dùng định danh ổn định và quan hệ cha/con rõ ràng |
| Giữ credential trong sự kiện để dễ tra cứu | Kho bằng chứng trở thành nguồn rò rỉ bí mật | Dùng tham chiếu, giảm hiển thị và phân quyền |
| Một quản trị viên sửa được cả nội dung, hash và log | Khó phát hiện can thiệp có chủ đích | Tách miền quyền, bảo vệ manifest và nhật ký |
| Cấp quyền xem bản ghi quá rộng | Lộ dữ liệu sản xuất qua hệ thống giám sát | Phân quyền theo hồ sơ, ghi audit, kiểm soát xuất |
| Gọi mọi bản ghi là COMPLETE sau khi đóng phiên | Che mất khoảng trống và lỗi tải lên | Tách trạng thái phiên khỏi trạng thái bằng chứng |
| Chỉ vô hiệu hóa tài khoản sau công việc | Phiên hoặc kênh cũ vẫn hoạt động | Thu hồi và xác minh tại broker lẫn tài nguyên đích |
| Giữ mọi bản ghi vô thời hạn | Tăng lượng dữ liệu nhạy cảm và chi phí quản lý | Có chính sách vòng đời và cơ chế giữ phục vụ hồ sơ cụ thể |

## 13. Câu hỏi tự kiểm tra

**1. Có video RDP đầy đủ thì đã chứng minh nhà cung cấp không sao chép dữ liệu chưa?**

Chưa. Cần xem phạm vi kênh được ghi, clipboard, ổ đĩa được ánh xạ, truyền tệp và các đường mạng khác. Video có thể hỗ trợ điều tra nhưng không chứng minh mọi luồng dữ liệu đã được quan sát.

**2. Vì sao không dùng danh sách Recording ID trong kho làm mẫu số cho tỷ lệ bao phủ?**

Vì phiên không tạo được bản ghi có thể không xuất hiện trong kho. Mẫu số cần đến từ nguồn quản lý phiên độc lập và đúng tập phiên bắt buộc ghi.

**3. Hash của một segment hợp lệ có bảo đảm nội dung không bị người quản trị thay thế không?**

Chỉ khi giá trị tham chiếu và chuỗi xác thực được bảo vệ đủ để đối chiếu. Nếu người quản trị có thể thay cả segment lẫn hash, việc tính hash đơn thuần không phát hiện được sự thay thế đó.

**4. Mất kết nối tới kho bằng chứng có luôn buộc phải cắt phiên không?**

Không thể quyết định chỉ từ lỗi đường truyền. Cần biết recorder có tiếp tục thu vào bộ đệm bền vững được bảo vệ không, giới hạn còn đáp ứng không và chính sách của tài nguyên yêu cầu gì. Mất khả năng thu là tình huống khác với chậm chuyển dữ liệu đã thu.

**5. Có thể đổi INCOMPLETE thành COMPLETE sau khi bổ sung biên bản người quan sát không?**

Biên bản bổ sung bối cảnh nhưng không biến phần tương tác đã mất thành bản ghi đầy đủ. Có thể đóng hồ sơ xử lý sự cố sau khi đánh giá, trong khi vẫn giữ nhãn chất lượng bản ghi trung thực.

**6. Điều gì cần xảy ra khi quyền JIT hết hạn?**

Hệ thống phải xử lý phiên và kênh đang hoạt động theo chính sách, kiểm tra kết quả tại các điểm kiểm soát và lưu dấu vết. Chỉ từ chối lần đăng nhập tiếp theo thường chưa đủ để chứng minh quyền truy cập đã kết thúc.

## 14. Điểm ghi nhớ

Vendor session recording hiệu quả khi tổ chức biết rõ ai đang truy cập, theo quyền nào, qua kênh nào và bằng chứng thực sự bao phủ tới đâu. Bản ghi cần được liên kết với quyền JIT, giới hạn chức năng quản trị, tài khoản đích và hồ sơ công việc.

Chất lượng bằng chứng phải được kiểm tra từ lúc bắt đầu thu tới lúc lưu, phát lại và bàn giao. Khi có khoảng trống, hệ thống cần ghi nhận trung thực, thực thi chính sách điều khiển phiên và đối chiếu các nguồn nhật ký khác. Đồng thời, chính bản ghi đặc quyền phải được bảo vệ như một tập dữ liệu nhạy cảm.

