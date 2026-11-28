# Test session termination

## 1. Mục tiêu và phạm vi

Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), **session termination** là việc kết thúc một phiên truy cập để phiên đó không còn thực hiện được thao tác đặc quyền trong phạm vi đã cam kết. Nguyên nhân có thể là quản trị viên chủ động ngắt phiên, yêu cầu của đội ứng phó sự cố, hết thời gian cho phép, vi phạm chính sách hoặc thu hồi quyền.

Kiểm thử session termination phải trả lời được một câu hỏi cụ thể: **sau khi có yêu cầu kết thúc, người dùng còn làm được gì, trên tài nguyên nào, trong bao lâu?** Việc giao diện hiển thị “Terminated” chỉ là một tín hiệu. Kết luận cần dựa vào hành vi thực tế tại điểm thực thi quyền và bằng chứng có thể đối chiếu.

Bài học thuộc chương Testing của module kiểm soát quyền truy cập đặc biệt đối với tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Trọng tâm là thiết kế phép thử cho các phiên PAM, gắn với least privilege, JIT/JEA, vault, credential và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố.

Sau bài học, người học có thể:

- Phân biệt kết thúc phiên với đăng xuất, khóa tài khoản, thu hồi quyền và luân chuyển credential.
- Xác định đúng các thành phần phải thực thi lệnh ngắt phiên.
- Thiết kế ca kiểm thử chức năng, phân quyền, thời gian, lỗi mạng và tình huống đồng thời.
- Chứng minh phiên cũ bị vô hiệu hóa bằng thao tác kiểm chứng an toàn.
- Đánh giá phần việc đang chạy tại hệ thống đích, khả năng kết nối lại và các phiên liên quan.
- Lập báo cáo có mốc thời gian, kết quả quan sát và giới hạn phạm vi rõ ràng.

## 2. “Kết thúc phiên” cần được định nghĩa ở đâu?

Một phiên PAM thường đi qua nhiều lớp:

```text
Người dùng
   |
   v
Cổng truy cập / client
   |
   v
Bộ điều khiển PAM -- quyết định chính sách / yêu cầu terminate
   |
   v
Proxy hoặc gateway -- kênh truyền và điểm chặn phiên
   |
   v
Tài nguyên đích -- SSH, RDP, database, thiết bị mạng, ứng dụng
   |
   +--> shell, tiến trình, giao dịch hoặc tác vụ đã được khởi chạy

Bằng chứng có thể xuất hiện tại từng lớp và tại hệ thống thu thập log.
```

Đóng cửa sổ trình duyệt chỉ tác động đến phía người dùng. Cắt một kết nối TCP có thể làm gián đoạn kênh truyền nhưng không bảo đảm mọi tiến trình ở đích đã dừng. Thu hồi JIT có thể ngăn cấp phiên mới mà chưa tác động tới phiên được cấp trước đó. Vì vậy, trước khi viết test, phải mô tả hợp đồng thực thi của loại phiên đang xét.

Ví dụ, một hợp đồng cho phiên SSH qua proxy có thể là:

> Sau khi yêu cầu ngắt được chấp nhận, proxy ngừng chuyển dữ liệu tương tác của đúng phiên trong thời hạn đã quy định; đích đóng phiên đăng nhập tương ứng nếu đó là khả năng được triển khai. Tác vụ nền được xử lý theo chính sách riêng, không suy diễn từ trạng thái trên cổng PAM.

Đối với RDP, cần nêu rõ hành động là **disconnect** hay **logoff**. Disconnect có thể để lại desktop và ứng dụng đang chạy. Logoff nhằm kết thúc phiên đăng nhập, nhưng vẫn cần kiểm tra kết quả ở đích. Không dùng hai thuật ngữ này thay thế cho nhau trong tiêu chí chấp nhận.

### 2.1. Các trạng thái không tương đương

| Hành động hoặc tín hiệu | Có thể chứng minh | Chưa đủ để chứng minh |
|---|---|---|
| Người dùng đóng client | Client tại thời điểm đó không còn mở | Phiên phía server đã kết thúc |
| PAM nhận yêu cầu terminate | Yêu cầu đã đi vào luồng xử lý | Điểm thực thi đã áp dụng |
| Proxy đóng kênh | Kênh được quan sát đã bị ngắt | Tiến trình nền hoặc kênh độc lập đã dừng |
| Tài khoản bị khóa | Một cơ chế xác thực có thể từ chối đăng nhập mới | Mọi phiên đã xác thực trước đó bị hủy |
| Thu hồi role/JIT | Quyền hoặc điều kiện cấp quyền đã đổi | Phiên/token cũ lập tức mất hiệu lực |
| Đổi mật khẩu hoặc secret | Credential mới được thiết lập theo kết quả kiểm chứng | Credential đã cấp hoặc phiên cũ đều bị vô hiệu hóa |
| Đích xác nhận kết thúc phiên đăng nhập | Phiên đăng nhập cụ thể không còn tại đích | Mọi tác vụ, token hay kết nối phát sinh từ phiên đều biến mất |

Kết quả test cần dùng đúng phạm vi của bằng chứng. Nếu chỉ kiểm thử SSH qua proxy, không kết luận rằng mọi quyền của người dùng trên toàn bộ hạ tầng đã bị thu hồi.

## 3. Xây dựng hợp đồng chấp nhận trước khi chạy

Một ca kiểm thử hữu ích cần ghi rõ **trigger, đối tượng, hành vi mong đợi, thời hạn và bằng chứng**. Không lấy trạng thái giao diện làm tiêu chí duy nhất.

Ví dụ minh họa dưới đây sử dụng các con số do nhóm kiểm thử giả định cho phòng lab, không phải tiêu chuẩn chung cho mọi sản phẩm PAM:

| Thuộc tính | Hợp đồng minh họa |
|---|---|
| Đối tượng | Một phiên SSH qua gateway, xác định bằng session ID và phiên ở đích |
| Trigger | Người vận hành được cấp quyền ngắt chủ động |
| Phạm vi | Chỉ phiên được chọn; các phiên khác tiếp tục hoạt động |
| Thời hạn chặn kênh | Không quá 5 giây tính từ khi hệ thống chấp nhận yêu cầu |
| Sau thời điểm chặn | Không thực thi được marker đặc quyền mới qua phiên cũ |
| Kết nối lại | Không phục hồi phiên cũ bằng reconnect hoặc resume |
| Phiên mới | Tuân theo chính sách truy cập hiện tại; đánh giá riêng |
| Tiến trình ở đích | Kiểm tra theo chính sách đã khai báo cho loại tiến trình |
| Bằng chứng | Actor, reason, session ID, target, các mốc thời gian và kết quả thực thi |
| Phiên không liên quan | Không bị ngắt hoặc thay đổi quyền ngoài phạm vi |

Nếu yêu cầu nghiệp vụ đo từ lúc người vận hành bấm nút, phải bao gồm cả thời gian gửi yêu cầu và thời gian hệ thống tiếp nhận. Không tự đổi điểm bắt đầu sang lúc API phản hồi để làm kết quả tốt hơn.

Trong môi trường phân tán, timeout của phía gọi không có nghĩa là thao tác đã thất bại. Yêu cầu có thể đã được xử lý dù phản hồi bị mất. Test cần có cách truy vấn kết quả theo session ID và request ID, thay vì gửi lại hàng loạt một cách không kiểm soát.

## 4. Các mốc thời gian cần thu thập

Có thể dùng các mốc sau:

- **T0:** phía kiểm thử phát yêu cầu terminate.
- **T1:** hệ thống tiếp nhận hoặc chấp nhận yêu cầu theo hợp đồng API.
- **T2:** điểm thực thi áp dụng việc chặn hoặc đóng phiên.
- **T3:** phép kiểm chứng xác nhận phiên cũ không còn thực hiện được thao tác.
- **T4:** sự kiện hoàn tất xuất hiện tại nơi thu thập bằng chứng.

Từ đó, phân biệt:

```text
Độ trễ tiếp nhận         = T1 - T0
Độ trễ thực thi          = T2 - T1
Độ trễ xác nhận quan sát = T3 - T1
Độ trễ tập hợp bằng chứng= T4 - T2
```

T2 không phải lúc nào cũng quan sát trực tiếp được. Khi chỉ có probe định kỳ, hãy báo một khoảng giới hạn thay vì gán T2 bằng thời điểm của một log đến muộn.

Ví dụ: probe thành công lần cuối tại giây 2,0; probe đầu tiên bị từ chối tại giây 2,5; các probe sau đều bị từ chối. Kết quả quan sát cho biết sự chuyển đổi nằm trong khoảng đó, với điều kiện probe không bị lỗi vì nguyên nhân khác. Không khẳng định hệ thống ngắt chính xác ở giây 2,5.

Các nguyên tắc đo:

1. Dùng đồng hồ đơn điệu để đo khoảng thời gian trong cùng tiến trình kiểm thử.
2. Dùng timestamp UTC và định danh tương quan để nối sự kiện giữa các máy.
3. Ghi nhận sai lệch đồng hồ nếu phải so sánh timestamp giữa các hệ thống.
4. Phân biệt thời gian sự kiện xảy ra với thời gian collector nhận được log.
5. Không lấy việc thiếu log trong vài giây đầu làm bằng chứng phiên vẫn hoạt động.
6. Với bài kiểm thử có ngưỡng, chọn tần suất probe đủ nhỏ so với ngưỡng và ghi rõ độ phân giải.

Nếu không chứng minh được điều kiện để đánh giá thời gian, kết quả nên là **INCONCLUSIVE** cho tiêu chí thời gian, không tự chuyển thành PASS.

## 5. Chuẩn bị phòng lab và dữ liệu kiểm thử

### 5.1. Thành phần tối thiểu

Chuẩn bị một môi trường được phép thử gồm:

- Một tài khoản vận hành có quyền terminate đúng phạm vi.
- Một tài khoản chỉ có quyền xem, dùng để thử từ chối thao tác.
- Một người dùng mở phiên được kiểm thử.
- Một tài khoản thử nghiệm khác để tạo phiên đối chứng.
- Một hoặc hai tài nguyên đích chứa dữ liệu giả lập.
- Kênh thu thập sự kiện PAM, gateway và log ở đích.
- Khả năng xác định phiên ở đích bằng thông tin có căn cứ, không chỉ bằng tên đăng nhập.
- Cơ chế phục hồi truy cập lab và thu hồi dữ liệu thử sau khi hoàn tất.

Cần phân biệt người yêu cầu ngắt, người sở hữu phiên và danh tính dùng để đăng nhập đích. Ba vai trò có thể khác nhau, đặc biệt khi PAM kết nối đích bằng một tài khoản dùng chung có quản lý.

### 5.2. Marker chứng minh khả năng thực thi

Chọn một thao tác vô hại nhưng đủ chứng minh quyền thực thi trên tài nguyên thử nghiệm. Ví dụ: ghi một marker có nonce vào thư mục lab chỉ tài khoản thử nghiệm được phép ghi; hoặc thực hiện một câu truy vấn đọc trên bảng giả lập.

Marker nên có các thuộc tính:

- Chứa test run ID và số thứ tự để chống nhầm với kết quả cũ.
- Không chứa mật khẩu, private key, token hoặc dữ liệu thật.
- Có thể kiểm chứng độc lập ở đích.
- Có tần suất thấp, được giới hạn thời gian và số lần thử.
- Không thay đổi quyền, xóa dữ liệu hay gây ảnh hưởng dịch vụ.

Nếu dùng marker đặc quyền, quyền đó chỉ được cấp trên tài nguyên lab tối thiểu. Một lệnh đọc thông tin công khai có thể chứng minh kênh vẫn hoạt động nhưng chưa chứng minh khả năng thực hiện thao tác đặc quyền; cần mô tả đúng điều được kiểm tra.

### 5.3. Phân biệt dữ liệu đang đệm với thực thi mới

Một terminal có thể còn hiển thị output sau khi kênh đã bị đóng do dữ liệu đệm. Ngược lại, client có thể trông như đã mất kết nối dù tác vụ ở đích vẫn chạy.

Dùng nonce mới được tạo sau mốc cần đánh giá, rồi kiểm chứng dấu vết ở đích để phân biệt:

- Output cũ được render muộn.
- Lệnh đã gửi trước khi terminate nhưng hoàn tất sau đó.
- Lệnh mới được tiếp nhận sau thời điểm cần chặn.
- Tác vụ độc lập đã tồn tại từ trước.

Không dùng ảnh chụp màn hình terminal đơn lẻ để kết luận về thứ tự thực thi.

## 6. Ca kiểm thử cơ sở: chủ động ngắt đúng một phiên

### 6.1. Điều kiện đầu vào

Tạo hai phiên khác nhau, A và B, qua cùng một hệ thống PAM. A là phiên sẽ bị ngắt; B là phiên đối chứng. Tốt nhất, hai phiên có định danh đích rõ ràng và có thể phân biệt ngay cả khi cùng dùng một tài khoản kỹ thuật.

Trước khi chạy, xác nhận:

- A và B đang hoạt động và thực hiện được marker ban đầu.
- Tài khoản vận hành có quyền ngắt A.
- Bộ thu thập bằng chứng đang hoạt động.
- Chưa có chính sách idle timeout hoặc expiry sắp tác động lên A/B trong cửa sổ thử.
- Test không phụ thuộc một kết nối quản trị duy nhất có thể bị ngắt nhầm.

### 6.2. Trình tự

1. Ghi lại test run ID, session ID A/B, đích, loại giao thức và chính sách hiệu lực.
2. Thực thi marker trước ngắt qua A và B; xác minh ở đích.
3. Phát yêu cầu ngắt A, kèm lý do và request ID; ghi T0.
4. Lưu phản hồi nhận được, phân biệt trạng thái accepted với completed; ghi T1 nếu có.
5. Theo dõi trạng thái A tại PAM, tại gateway và tại đích theo khả năng quan sát đã khai báo.
6. Dùng probe có giới hạn để kiểm tra phiên A trong cửa sổ thực thi cho phép.
7. Sau hạn chót, thử thao tác mới qua phiên A; kết quả phải phù hợp hợp đồng.
8. Thử reconnect/resume phiên A bằng chính cơ chế client được hỗ trợ.
9. Xác nhận phiên B vẫn thực hiện được marker và không bị thay đổi ngoài phạm vi.
10. Đối chiếu sự kiện, kiểm tra tác vụ phát sinh từ A, rồi thu hồi tài nguyên lab.

### 6.3. Điều kiện PASS

Ca cơ sở chỉ PASS khi tất cả tiêu chí bắt buộc đã có bằng chứng:

- Đúng phiên A bị kết thúc trong thời hạn.
- Phiên A không thực hiện được thao tác mới sau hạn chót.
- Không khôi phục được quyền của phiên A bằng resume ngoài chính sách.
- Phiên B không bị ngắt nhầm.
- Có thể truy vết người ngắt, lý do, đối tượng và kết quả.
- Phần việc còn tồn tại ở đích được xử lý đúng chính sách đã khai báo.

Nếu phiên A bị đóng nhưng B cũng bị ngắt do hệ thống dùng tên tài khoản thay cho session ID, ca kiểm thử phải FAIL về phạm vi tác động.

## 7. Thiết kế ma trận kiểm thử

Một ma trận tốt bao phủ các chiều rủi ro; không nhất thiết chạy mọi tổ hợp nếu nhiều tổ hợp tương đương. Chọn tổ hợp dựa vào kiến trúc và phạm vi triển khai thực tế.

| Nhóm | Trường hợp | Quan sát cần có |
|---|---|---|
| Giao thức | SSH, RDP, database, web admin qua PAM | Cách đóng phiên và bằng chứng phù hợp từng giao thức |
| Nguyên nhân | Chủ động, hết thời gian, vi phạm chính sách | Trigger đúng và kết quả đúng hợp đồng |
| Phạm vi | Một phiên, các phiên của một người dùng, một target | Tập phiên chịu tác động được xác định chính xác |
| Danh tính | Cá nhân, tài khoản kỹ thuật qua PAM, vendor | Liên kết được người thật với phiên và danh tính đích |
| Kết nối | Ổn định, độ trễ cao, mất phản hồi, partition | Không báo hoàn tất khi chưa có căn cứ |
| Vòng đời | Vừa tạo, hoạt động lâu, đang reconnect | Không có cửa sổ khôi phục quyền trái chính sách |
| HA | Phiên trên node khác, chuyển node, node hỏng | Lệnh ngắt tới đúng điểm thực thi |
| Tác vụ | Shell tương tác, tiến trình nền, giao dịch | Kết quả theo chính sách tác vụ ở đích |
| Bằng chứng | Collector chậm, tạm mất kết nối, recording chưa đóng | Truy vết được và không kết luận sai do log trễ |

### 7.1. Các ca chức năng và phân quyền tối thiểu

| ID | Thao tác | Kết quả mong đợi |
|---|---|---|
| ST-01 | Người được cấp quyền ngắt một phiên đang chạy | Đúng phiên bị ngắt theo thời hạn |
| ST-02 | Người chỉ có quyền xem gửi yêu cầu ngắt | Bị từ chối; phiên không đổi; có sự kiện theo chính sách |
| ST-03 | Người vận hành ngắt phiên ngoài phạm vi quản trị | Bị từ chối ở phía server |
| ST-04 | Gửi yêu cầu lặp cho phiên đã kết thúc | Không tạo tác động mới ngoài hợp đồng |
| ST-05 | Gửi session ID không tồn tại | Phản hồi phù hợp thiết kế, không ảnh hưởng phiên khác |
| ST-06 | Hai phiên cùng dùng một tài khoản đích | Ngắt đúng phiên được chọn |
| ST-07 | Session ID cũ sau khi mở phiên mới | Không ngắt nhầm phiên mới |
| ST-08 | Client tìm cách resume phiên vừa bị ngắt | Không khôi phục phiên cũ trái chính sách |
| ST-09 | Phiên mới được yêu cầu sau termination | Quyết định dựa trên quyền/chính sách hiện tại |
| ST-10 | Lý do ngắt hoặc audit context bắt buộc bị thiếu | Xử lý theo hợp đồng, không tạo kết quả nửa vời |

Với ST-03, cần kiểm tra cả API hoặc đường gọi thực tế mà môi trường hỗ trợ. Việc nút terminate bị ẩn trên giao diện không chứng minh kiểm soát phân quyền phía server.

Phản hồi cho session ID không tồn tại có thể khác giữa các thiết kế. Hãy kiểm tra hợp đồng truy cập và hạn chế lộ thông tin phiên, thay vì buộc mọi hệ thống trả cùng một mã lỗi.

## 8. Session termination và quyền truy cập JIT/JEA

Termination xử lý một phiên; thu hồi JIT hoặc thay đổi JEA xử lý điều kiện cấp quyền hoặc tập thao tác được phép. Hai luồng thường được phối hợp nhưng không tự động tương đương.

Xét bốn câu hỏi độc lập:

1. Phiên hiện tại có tiếp tục hoạt động sau khi quyền JIT hết hạn không?
2. Một phiên mới có được cấp sau thời điểm hết hạn không?
3. Phiên đang tồn tại có sử dụng được thao tác vừa bị loại khỏi chính sách JEA không?
4. Có cơ chế chủ động terminate khi cần thực thi thu hồi ngay không?

Ví dụ: một cửa sổ JIT cho phép bảo trì đến 14:00. Chính sách có thể yêu cầu chặn cấp phiên mới lúc 14:00 và ngắt mọi phiên đang chạy liên quan. Một hệ thống khác có thể cho phép phiên tồn tại đến session TTL riêng. Test phải dựa trên chính sách đã duyệt; nếu nghiệp vụ yêu cầu thu hồi ngay mà hệ thống chỉ chặn đăng nhập mới, đó là khoảng trống cần báo cáo.

Khi kiểm tra thay đổi JEA giữa phiên, hãy chọn thao tác lab đại diện cho quyền được bỏ và thao tác vẫn còn được phép. Nếu cần kết thúc phiên để chính sách mới có hiệu lực, đo cả thời gian nhận thay đổi và thời gian chặn phiên.

Không mặc định mọi loại token, chứng thư hoặc phiên database có thể bị thu hồi tức thì. Nếu có quyền còn hiệu lực ngoài phiên PAM, ghi rõ lớp thực thi nào chịu trách nhiệm và trường hợp nào cần phép thử riêng.

## 9. Kiểm thử những gì còn chạy ở đích

### 9.1. Tiến trình nền và tác vụ tách phiên

Một shell có thể khởi chạy tác vụ tồn tại sau khi kết nối bị đóng. Với mục tiêu kiểm thử phòng thủ, chỉ dùng một tác vụ lab có thời gian sống ngắn và heartbeat vào vùng giả lập.

Trình tự:

1. Khởi chạy tác vụ thử theo cách được phạm vi kiểm thử cho phép.
2. Ghi định danh tiến trình hoặc job cùng thời điểm tạo.
3. Ngắt phiên PAM theo ca cơ sở.
4. Quan sát heartbeat và trạng thái job từ kênh quản trị lab độc lập.
5. So sánh với chính sách: tác vụ được phép hoàn tất, bị dừng, hay cần bước ứng phó bổ sung.
6. Dừng và dọn tác vụ thử bằng cơ chế đã chuẩn bị.

Một heartbeat tiếp tục chạy là bằng chứng tác vụ còn hoạt động. Nó không tự chứng minh phiên tương tác vẫn sử dụng được; hai kết luận phải tách biệt.

Nếu hợp đồng yêu cầu dừng tác vụ do phiên khởi tạo nhưng cơ chế chỉ đóng proxy, test có thể bộc lộ thiếu hụt giữa yêu cầu và khả năng thực thi. Không khắc phục bằng cách tùy tiện dừng mọi tiến trình của tài khoản dùng chung, vì có thể tác động tới workload khác.

### 9.2. Giao dịch và thao tác đang thực hiện

Với database hoặc hệ thống quản trị có giao dịch, phân biệt:

- Yêu cầu đã nhận trước thời điểm ngắt.
- Yêu cầu mới sau thời điểm chặn.
- Giao dịch chưa commit.
- Thao tác đã commit hoặc đã gây tác động ở hệ thống khác.

Đóng kết nối không phải thao tác hoàn tác phổ quát. Một thay đổi đã commit hoặc một tác vụ đã gửi sang hệ thống khác có thể vẫn tồn tại.

Ca thử nên dùng dữ liệu giả lập có thể đối chiếu, ghi rõ chính sách commit/rollback của môi trường đang thử và xác nhận trạng thái cuối cùng tại đích. Không suy ra rollback chỉ từ việc client mất kết nối.

### 9.3. Kênh phụ và kết nối độc lập

Một phiên có thể mở các kênh con hoặc kết nối liên quan trong phạm vi kiến trúc được hỗ trợ. Test cần kiểm kê những kênh nào thuộc hợp đồng termination:

- Kênh shell, truyền tệp hoặc forwarding nếu được bật trong lab.
- Nhiều tab hoặc nhiều cửa sổ của cùng một phiên logic.
- Kết nối database phụ được client tạo.
- Phiên đăng nhập vào ứng dụng đích do cơ chế SSO sinh ra.

Chỉ thử các tính năng đã được phép và cấu hình cho môi trường. Kết nối trực tiếp ngoài PAM là một kiểm soát bao phủ truy cập khác; nó không thể được tuyên bố là đã kiểm thử chỉ nhờ ngắt thành công một phiên proxy.

## 10. Lỗi mạng, node hỏng và xử lý bất định

### 10.1. Mất phản hồi sau khi phát yêu cầu

Tình huống: phía kiểm thử gửi terminate nhưng hết thời gian chờ phản hồi.

Cần kiểm tra:

- Yêu cầu đã được hệ thống nhận chưa?
- Phiên có bị chặn thực tế không?
- Có thể truy vấn kết quả bằng request ID hoặc session ID không?
- Retry có giữ đúng phạm vi, theo hợp đồng về lặp yêu cầu không?
- Bằng chứng có phân biệt timeout phía gọi với lỗi thực thi không?

Không quy định retry mù vô hạn. Dùng số lần và tổng thời gian chờ có giới hạn; nếu không xác định được kết quả, báo INCONCLUSIVE hoặc trạng thái lỗi phù hợp.

### 10.2. Bộ điều khiển mất liên lạc với gateway

Giả lập partition trong lab theo kế hoạch được phép, rồi phát yêu cầu ngắt một phiên đang nằm trên gateway bị cô lập.

Test cần quan sát chính sách thực tế: phiên bị chặn nhờ lease/TTL cục bộ, bị đóng khi mất liên lạc, tiếp tục tới hạn nhất định, hay có đường điều khiển dự phòng. Chính sách nào được chọn phải được khai báo trước.

Một trạng thái “pending” hoặc “failed to enforce” có thể phản ánh đúng sự thật trong lúc mất liên lạc. Trạng thái “terminated” khi phiên vẫn thực thi được lệnh là lỗi đáng chú ý hơn vì làm sai quyết định ứng phó.

Nếu hệ thống có TTL cục bộ, đo thời gian còn hiệu lực và xác nhận các hành vi quanh thời điểm hết TTL. Không đánh đồng “cuối cùng tự hết hạn” với “đã đáp ứng hạn chót của lệnh ngắt”.

### 10.3. Chuyển node hoặc gateway

Tạo phiên trên một node, gửi yêu cầu từ đường điều khiển khác, rồi thử tình huống failover trong lab.

Các điểm cần kiểm tra:

- Bản ghi session ID có trỏ đúng gateway đang thực thi không?
- Node mới có biết phiên đã bị thu hồi trước đó không?
- Hàng đợi yêu cầu bị ngắt quãng có được xử lý theo hợp đồng không?
- Session resume có bị từ chối sau chuyển node không?
- Có phiên “mồ côi” ở đích hoặc proxy không?
- Các sự kiện trùng có khiến báo cáo đếm sai số phiên bị ngắt không?

Kết quả phải dựa trên quyền thực thi thực tế, không chỉ dựa trên dữ liệu replication của trạng thái.

## 11. Các tình huống đồng thời và ranh giới thời gian

Session termination có nhiều điểm tranh chấp giữa thao tác người dùng và thao tác quản trị.

### 11.1. Lệnh đang đi qua khi có yêu cầu ngắt

Ghi rõ chính sách đối với thao tác đang xử lý. Không thể mặc định một hành động đã được đích chấp nhận sẽ bị hủy chỉ vì lệnh terminate tới sau.

Thiết kế ca thử với nonce và mốc thời gian để phân biệt lệnh trước và sau ranh giới. Nếu không quan sát được thứ tự xử lý ở đích với độ chính xác cần thiết, báo hạn chế đó; không kết luận một cửa sổ bypass chỉ từ thứ tự log ở collector.

### 11.2. Mở phiên mới trong lúc ngắt phiên cũ

Nếu yêu cầu là ngắt **một phiên**, phiên mới có thể hợp lệ theo chính sách hiện tại. Nếu yêu cầu là thu hồi **mọi truy cập của một người dùng**, cần có cơ chế chặn cấp phiên mới cùng với việc xử lý các phiên hiện có.

Do đó, ca thử phải ghi rõ snapshot hay phạm vi liên tục:

- Snapshot: xử lý tập phiên đang tồn tại tại một thời điểm.
- Phạm vi liên tục: đồng thời ngăn cấp mới trong khi quyền bị thu hồi.

Kết luận phải phù hợp loại thao tác được triển khai.

### 11.3. Người dùng tự đăng xuất cùng lúc quản trị viên ngắt

Hệ thống cần đi đến một trạng thái cuối nhất quán và giữ được chuỗi sự kiện. Không nhất thiết buộc chỉ có một sự kiện, nhưng không được ghi rằng quản trị viên đã thành công ngắt một phiên không liên quan hoặc để lại quyền không kiểm soát.

### 11.4. Hai người cùng gửi yêu cầu

Kiểm tra tính an toàn khi lặp hoặc đồng thời theo hợp đồng:

- Không ngắt nhầm phiên khác.
- Không phát sinh lại phiên đã kết thúc.
- Phản hồi và audit phân biệt được từng yêu cầu.
- Trạng thái cuối cùng có thể giải thích được.
- Nếu dùng request key chống lặp, phạm vi và thời gian hiệu lực của key đúng thiết kế.

Không đòi hỏi mọi triển khai trả cùng một phản hồi cho yêu cầu thứ hai; cần nhất là kết quả và bằng chứng không mâu thuẫn.

## 12. Kiểm thử bằng chứng và recording

Một báo cáo termination có giá trị khi nối được **ý định → thực thi → kết quả quan sát**.

### 12.1. Trường bằng chứng cần xem xét

Tùy kiến trúc và chính sách, tập bằng chứng nên cho phép xác định:

| Nhóm | Nội dung |
|---|---|
| Yêu cầu | Test run ID, request ID, thời điểm gửi, lý do |
| Chủ thể | Người yêu cầu, vai trò/phạm vi được áp dụng |
| Phiên | Session ID, người sở hữu, danh tính đích, giao thức |
| Tài nguyên | Target ID, môi trường, gateway/node liên quan |
| Quyết định | Cho phép hoặc từ chối terminate, nguyên nhân |
| Thực thi | Đã nhận, đang xử lý, hoàn tất hoặc thất bại tại điểm thực thi |
| Quan sát | Kết quả probe, trạng thái ở đích, khả năng reconnect |
| Hậu xử lý | Trạng thái tác vụ, đóng recording, thu hồi dữ liệu thử |

Không cần mọi trường nằm trong một sự kiện duy nhất. Có thể ghép từ nhiều nguồn nếu định danh tương quan đủ mạnh và không dựa hoàn toàn vào phép đoán gần thời gian.

### 12.2. Recording được kết thúc thế nào?

Khi recording thuộc phạm vi, kiểm tra:

- Phần recording trước thời điểm kết thúc có truy cập được theo quyền không.
- Kết thúc đột ngột có làm mất toàn bộ nội dung đã ghi không.
- Sự kiện terminate có liên kết được với recording đúng phiên không.
- File hoặc đối tượng recording có trạng thái hoàn tất, lỗi hoặc chưa đầy đủ được biểu diễn đúng không.
- Sự chậm trễ khi finalize recording có bị nhầm với độ trễ ngắt phiên không.
- Người không có quyền có truy cập được recording sau khi phiên đóng không.

Nếu đã có cơ chế kiểm tra toàn vẹn hoặc bảo vệ lưu trữ, xác minh theo cơ chế đó. Một checksum tự tính trong báo cáo chỉ giúp so sánh bản thu thập; nó không tự chứng minh nguồn bằng chứng không từng bị sửa.

### 12.3. Log trễ và khoảng trống bằng chứng

Thử collector chậm hoặc tạm mất kết nối trong lab. Sau khi phục hồi, kiểm tra việc thu nhận lại, thứ tự và sự kiện trùng theo thiết kế.

Phân biệt hai tiêu chí:

- Phiên đã bị ngắt đúng thời hạn.
- Bằng chứng được tập hợp trong thời hạn quy định.

Tiêu chí thứ nhất PASS không tự làm tiêu chí thứ hai PASS. Ngược lại, bằng chứng tới muộn không tự chứng minh việc ngắt phiên tới muộn.

## 13. Phác thảo tự động hóa phép thử

Đoạn dưới đây là **pseudocode**, mô tả luồng kiểm thử chứ không phải API của một sản phẩm cụ thể. Các adapter phải được triển khai theo giao diện và điểm quan sát có thật trong lab.

```text
run_id = new_test_run_id()
session_a = open_lab_session(owner="user-a", target="lab-target")
session_b = open_lab_session(owner="user-b", target="lab-target")

assert marker_reaches_target(session_a, fresh_nonce(run_id))
assert marker_reaches_target(session_b, fresh_nonce(run_id))

request_id = fresh_request_id()
t0 = monotonic_now()
receipt = request_termination(session_a.id, request_id, "lab test")
t1 = receipt.accepted_at_in_test_clock

if receipt.outcome_is_unknown:
    reconcile_request(request_id, session_a.id, bounded_deadline)
    # Không coi timeout phía gọi là bằng chứng ngắt thất bại hay thành công.

deadline = t1 + enforcement_budget

while monotonic_now() < deadline:
    record_probe(session_a, fresh_nonce(run_id))
    collect_observations()
    wait_within_probe_interval()

for attempt in bounded_post_deadline_attempts:
    nonce = fresh_nonce(run_id)
    result = attempt_marker_through_old_session(session_a, nonce)
    record(result)
    assert independent_target_check(nonce) == "not executed"

assert old_session_resume_is_denied(session_a)
assert marker_reaches_target(session_b, fresh_nonce(run_id))
assert target_artifacts_follow_declared_policy(session_a)
assert audit_evidence_matches(request_id, session_a.id)

finally:
    close_remaining_lab_sessions()
    stop_test_jobs()
    remove_only_test_artifacts(run_id)
```

Khi triển khai, cần bổ sung xử lý ngoại lệ và cleanup bảo đảm ngay cả khi assertion thất bại. Không để một test FAIL tạo thêm phiên hoặc tác vụ không còn được theo dõi.

Một số lưu ý để tránh PASS giả:

- Probe lỗi mạng phải được phân loại riêng với việc điểm thực thi từ chối thao tác.
- Adapter không được tự tạo phiên mới để thay thế phiên A trong lúc đang kiểm tra phiên cũ.
- Kết quả marker phải đối chiếu nonce tại đích, không chỉ đọc dòng chữ client trả về.
- Thời gian chờ và retry đều có giới hạn.
- Việc quan sát đích sử dụng quyền lab riêng, không làm thay đổi phiên đang bị kiểm thử.
- Tần suất probe phải được phê duyệt cho lab và không tạo tải làm sai kết quả.

Không nhất thiết tự động hóa toàn bộ ngay từ đầu. Một phép thử thủ công có mốc thời gian, nonce và đối chứng rõ ràng vẫn tốt hơn một script chỉ chờ trạng thái giao diện rồi đánh dấu PASS.

## 14. Ví dụ phân tích kết quả

Giả sử phòng lab quy định thời hạn chặn phiên là 5 giây kể từ T1. Một lần chạy có quan sát:

| Mốc | Quan sát |
|---|---|
| T1 + 0,0 giây | Yêu cầu terminate A được chấp nhận |
| T1 + 0,7 giây | Giao diện hiển thị A đã kết thúc |
| T1 + 1,0 giây | Probe mới qua A vẫn tạo marker ở đích |
| T1 + 2,0 giây | Probe qua A thành công lần cuối |
| T1 + 2,5 giây | Probe qua A thất bại; nonce không xuất hiện tại đích |
| T1 + 5,5 giây | Probe sau hạn chót bị chặn; B vẫn hoạt động |
| T1 + 7,0 giây | Collector nhận sự kiện thực thi terminate |
| Sau đó | Reconnect A bị từ chối theo chính sách |

Cách đánh giá:

- Có bằng chứng hỗ trợ việc kênh A bị chặn trước hạn 5 giây, nếu các probe lỗi đã được xác minh đúng nguyên nhân và số lần quan sát đáp ứng kế hoạch thử.
- Thời điểm 0,7 giây trên giao diện không đại diện chính xác cho thời điểm thực thi; trạng thái có thể đang phản ánh yêu cầu điều khiển quá sớm.
- Sự kiện nhận ở giây 7 không chứng minh ngắt mất 7 giây; cần xem thời điểm phát sinh và chuỗi tương quan.
- Một lần thử thành công không chứng minh mọi gateway, giao thức hoặc tải đều đáp ứng cùng ngưỡng.

Nếu một tác vụ heartbeat tạo trước khi ngắt vẫn chạy, phải đánh giá theo chính sách tác vụ nền. Trường hợp chính sách chỉ đóng kênh tương tác, ghi nhận tác vụ còn hoạt động như một giới hạn đã biết. Trường hợp chính sách yêu cầu dừng tác vụ đó, đánh FAIL tiêu chí tương ứng dù kênh tương tác đã đóng đúng hạn.

## 15. Những sai lầm thường gặp

### 15.1. Dùng trạng thái control plane thay cho kết quả thực thi

Đánh dấu PASS ngay khi API trả accepted hoặc giao diện đổi trạng thái. Cách sửa là thêm probe và quan sát độc lập tại đích hoặc điểm thực thi thích hợp.

### 15.2. Chỉ thử từ một cửa sổ client

Client tự đóng không có nghĩa mọi kênh liên quan đều bị đóng. Phải xác định phiên logic, kênh con và cơ chế resume thuộc phạm vi.

### 15.3. Coi đổi mật khẩu là ngắt mọi phiên

Credential mới và phiên đã xác thực là hai đối tượng khác nhau. Kiểm thử việc ngắt phiên, việc từ chối credential cũ và việc cấp phiên mới bằng các tiêu chí riêng.

### 15.4. Không có phiên đối chứng

Một sự cố toàn gateway có thể làm phiên thử mất kết nối và tạo PASS giả. Phiên B cùng kiểm chứng sức khỏe đường quan sát giúp nhận diện tác động rộng hơn dự kiến.

### 15.5. Quên trạng thái ở đích

Chỉ kiểm tra proxy mà bỏ qua phiên đăng nhập, giao dịch và tác vụ nền. Cần kiểm tra theo hợp đồng; không tuyên bố đã dừng mọi hoạt động nếu không có bằng chứng.

### 15.6. Dùng timestamp log nhận được làm thời điểm thực thi

Collector có thể trễ, đồng hồ có thể lệch. Phải ghi rõ đồng hồ, loại timestamp và độ phân giải phép đo.

### 15.7. Gộp lỗi quan sát với thất bại kiểm soát

Không đọc được log hoặc mất kênh quản trị lab chưa đủ để kết luận PAM đã ngắt đúng hoặc sai. Dùng INCONCLUSIVE cho phần chưa chứng minh được và giữ phần kết quả đã có bằng chứng.

### 15.8. Cleanup làm mất bằng chứng hoặc tác động dữ liệu khác

Xóa sạch log để “dọn lab” có thể khiến không còn căn cứ phân tích. Chỉ thu hồi artifact mang run ID theo kế hoạch, giữ báo cáo và bằng chứng cần lưu; không dừng hoặc xóa tài nguyên ngoài test.

## 16. Mẫu báo cáo kết quả

```yaml
testCase: ST-01
testRunId: LAB-ST-2026-001
scope:
  protocol: SSH
  target: lab-target-01
  selectedSession: session-a
  controlSession: session-b
  terminationMode: selected-session
contract:
  startEvent: request-accepted
  enforcementBudgetSeconds: 5
  targetJobPolicy: declared-in-lab-plan
observations:
  requestAccepted: true
  lastSuccessfulProbeAfterAcceptanceSeconds: 2.0
  firstVerifiedBlockedProbeAfterAcceptanceSeconds: 2.5
  postDeadlineProbeBlocked: true
  oldSessionResumeDenied: true
  controlSessionUnaffected: true
  targetJobPolicySatisfied: true
evidence:
  correlationId: request-lab-001
  requestEvent: evidence-request-001
  enforcementEvent: evidence-enforce-001
  targetProbeResults: evidence-probes-001
  recordingState: finalized
result: PASS
limitations:
  - Chỉ đại diện cho tổ hợp giao thức và gateway của lần chạy này.
```

Các ID và số liệu trong mẫu là dữ liệu giả lập. Báo cáo thực tế cần kèm timestamp, vị trí bằng chứng có kiểm soát truy cập, phiên bản/cấu hình môi trường cần thiết để tái hiện và người chịu trách nhiệm phân tích.

Nếu tiêu chí nào không áp dụng, ghi lý do. Nếu thiếu bằng chứng, dùng trạng thái thể hiện đúng mức chắc chắn; không điền giá trị thuận lợi chỉ để hoàn thiện biểu mẫu.

Một lỗi có thể được mô tả cụ thể như sau:

> API chấp nhận yêu cầu ngắt phiên A tại T1 và giao diện hiển thị đã kết thúc sau 0,8 giây. Tuy nhiên, marker có nonce được tạo và gửi qua chính phiên A tại T1 + 6 giây vẫn xuất hiện ở đích. Thời hạn theo kế hoạch là 5 giây. Phiên đối chứng B hoạt động bình thường. Tiêu chí chặn thao tác mới của A không đạt.

Mô tả này hữu ích hơn câu “terminate bị chậm” vì gắn quan sát với phạm vi, mốc thời gian và yêu cầu.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### 17.1. Bài thực hành

Trong một lab được phép, thiết kế và thực hiện các bước sau:

1. Viết hợp đồng ngắt phiên cho một giao thức đang triển khai.
2. Tạo hai phiên A/B và xác định cách đối chiếu với đích.
3. Chọn marker có nonce, thời hạn chặn và độ phân giải phép đo.
4. Chạy ca ngắt A; kiểm tra B và thử resume A.
5. Kiểm tra một tác vụ ngắn đã khởi tạo từ A theo chính sách lab.
6. Chạy ca người không đủ quyền yêu cầu ngắt.
7. Nếu lab hỗ trợ, thử mất phản hồi yêu cầu rồi đối soát kết quả có giới hạn.
8. Nộp báo cáo có kết quả từng tiêu chí, bằng chứng và giới hạn quan sát.
9. Đóng phiên, dừng tác vụ và thu hồi artifact thử nghiệm theo run ID.

Sản phẩm cần nộp gồm hợp đồng chấp nhận, ma trận ca thử đã chọn, timeline, kết quả marker ở đích và báo cáo lỗi nếu có. Không đưa credential hoặc nội dung recording nhạy cảm vào bài nộp.

### 17.2. Câu hỏi tự kiểm tra

**1. Vì sao API trả accepted chưa đủ chứng minh phiên đã bị ngắt?**

Vì accepted có thể chỉ xác nhận hệ thống nhận yêu cầu. Điểm thực thi còn phải chặn kênh hoặc xử lý phiên ở đích; quá trình đó có thể trễ hoặc thất bại.

**2. Mật khẩu đã đổi nhưng phiên cũ vẫn chạy có luôn là lỗi termination không?**

Không thể kết luận chỉ từ hai thông tin đó. Cần xem có yêu cầu terminate hay cơ chế thu hồi phiên tương ứng không, và hợp đồng yêu cầu gì. Đổi credential tự nó không chứng minh đã kết thúc phiên.

**3. Sau disconnect RDP, ứng dụng trên desktop vẫn chạy thì đánh giá thế nào?**

Đánh giá theo hành động đã cam kết. Disconnect và logoff khác nhau. Nếu hợp đồng yêu cầu logoff hoặc dừng tác vụ cụ thể, phải kiểm chứng yêu cầu đó tại đích.

**4. Làm sao tránh nhầm output đệm với lệnh mới được thực thi?**

Dùng nonce được tạo tại mốc cần đánh giá và kiểm tra dấu vết độc lập tại đích, đồng thời phân biệt lệnh gửi trước và sau ranh giới.

**5. Log terminate tới collector sau 10 giây có nghĩa việc ngắt mất 10 giây không?**

Không. Phải phân biệt thời điểm thực thi với thời điểm nhận log, xem sai lệch đồng hồ và đối chiếu kết quả probe.

**6. Vì sao cần phiên B đối chứng?**

Để phát hiện ngắt nhầm phạm vi và sự cố chung khiến A mất kết nối. Phiên B giúp tránh kết luận thành công khi cả gateway gặp lỗi.

**7. Khi nào nên dùng INCONCLUSIVE?**

Khi thiếu bằng chứng cần thiết để kết luận, chẳng hạn mất kênh quan sát đích hoặc không xác định được kết quả yêu cầu sau timeout. Phần tiêu chí có bằng chứng vẫn cần được báo riêng.

Kết quả kiểm thử session termination có giá trị khi chứng minh đúng phiên đã mất khả năng truy cập theo hợp đồng, trong thời hạn quy định, với tác động tới hệ thống đích và chuỗi bằng chứng được giải thích rõ ràng.
