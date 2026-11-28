# Session timeout

## Mục tiêu bài học

Trong chương **Session management**, session timeout là cơ chế giới hạn thời gian một phiên được phép tiếp tục tồn tại hoặc thực hiện hành động theo chính sách. Với phiên đặc quyền, mục tiêu là giảm khoảng thời gian quyền mạnh còn sử dụng được khi người dùng không còn hoạt động, nhiệm vụ đã hết hạn hoặc điều kiện truy cập không còn đáp ứng.

Trong **Privileged Access Management (PAM)**, cơ chế này áp dụng cho đường truy cập của người quản trị và những phiên liên quan đến hạ tầng nhạy cảm. Nó cần phối hợp với least privilege, JIT/JEA, vault, vòng đời credential, giám sát phiên và bằng chứng phục vụ kiểm toán, ứng phó sự cố.

**Thông báo “phiên đã hết hạn” trên cổng PAM chưa chứng minh phiên ở hệ thống đích đã kết thúc.** Cần xác định lớp nào thực thi timeout, điều gì bị dừng và kết quả nào đã được xác minh.

Sau bài học, bạn có thể:

- Phân biệt idle timeout, absolute timeout và các thời hạn liên quan.
- Xác định hoạt động nào được dùng để gia hạn trạng thái nhàn rỗi.
- Thiết kế thời hạn theo phiên, quyền và nhiệm vụ.
- Phân biệt ngắt kết nối, đăng xuất, kết thúc phiên và dừng tác vụ.
- Xử lý reconnect, gia hạn, failover và kết quả thu hồi chưa rõ.
- Xác minh timeout bằng bằng chứng từ PAM, broker và hệ thống đích.

## 1. Vì sao phiên đặc quyền cần timeout?

Một phiên quản trị đang mở là một khả năng truy cập còn tồn tại. Người khác có thể tiếp cận máy trạm, người dùng có thể rời công việc hoặc quyền được cấp tạm thời đã không còn cần thiết.

Timeout giúp giới hạn khả năng đó theo thời gian, nhưng không thay thế:

- Xác thực danh tính và điều kiện thiết bị.
- Phân quyền tối thiểu trên hệ thống đích.
- Giới hạn tác vụ bằng JEA hoặc cơ chế tương ứng.
- Kiểm soát truy xuất credential.
- Thu hồi token, credential hoặc quyền theo sự kiện.
- Điều tra những hành động đã xảy ra.

Một phiên ngắn vẫn có thể gây tác động lớn nếu tài khoản có quyền rất rộng. Ngược lại, một nhiệm vụ hợp lệ kéo dài không nên bị xử lý bằng cách bỏ timeout cho mọi phiên.

Thiết kế cần gắn thời hạn với mục đích, phạm vi quyền và khả năng kiểm soát thực tế.

## 2. Những thời hạn dễ bị nhầm

| Cơ chế | Điều kiện kích hoạt | Ý nghĩa chính |
| --- | --- | --- |
| Idle timeout | Không có hoạt động được chấp nhận trong một khoảng thời gian | Giới hạn phiên không còn tương tác phù hợp |
| Absolute timeout | Đạt thời lượng tối đa tính từ mốc bắt đầu được định nghĩa | Giới hạn tổng thời gian của phiên |
| Thời hạn quyền JIT | Hết khoảng được cấp quyền hoặc điều kiện kích hoạt | Giới hạn quyền theo nhiệm vụ hoặc phê duyệt |
| Thời hạn xác thực | Cần xác thực lại hoặc ngữ cảnh xác thực không còn hợp lệ | Đánh giá lại danh tính và điều kiện |
| Thời hạn token hoặc credential | Vật liệu xác thực hết hiệu lực theo cơ chế liên quan | Giới hạn khả năng dùng vật liệu đó |
| Timeout kết nối mạng | Không nhận được tín hiệu hoặc phản hồi theo quy tắc giao thức | Phát hiện hoặc xử lý kết nối không đáp ứng |

Những thời hạn này không tự có cùng giá trị hoặc cùng tác động.

### Idle timeout không phải giới hạn tổng thời gian

Nếu hoạt động hợp lệ tiếp tục được ghi nhận, idle timeout có thể liên tục được dời. Vì vậy cần absolute timeout nếu mục tiêu là giới hạn tổng thời gian của một phiên.

### Token hết hạn không tự kết thúc mọi phiên

Một token có thể chỉ được kiểm tra lúc thiết lập kết nối. Phiên đã mở có thể có vòng đời khác, tùy nền tảng.

Nếu chính sách yêu cầu chấm dứt sử dụng khi token hoặc quyền JIT hết hạn, phải có cơ chế thực thi và xác minh tương ứng. Không chỉ dựa vào trường thời gian trong token.

### Timeout mạng không chứng minh người dùng vắng mặt

Keepalive có thể giữ kết nối mạng sống dù không có thao tác của người dùng. Ngược lại, một tác vụ hợp lệ có thể mất thời gian mà không tạo thêm tương tác.

Không dùng số byte hoặc tín hiệu giữ kết nối làm đại diện mặc định cho hoạt động của con người.

## 3. Xác định các lớp phiên

Một người có thể đồng thời có nhiều trạng thái phiên:

~~~text
Phiên đăng nhập nguồn danh tính
              |
              v
Phiên trên cổng PAM
              |
              v
Phiên hoặc kênh do broker quản lý
              |
              v
Phiên đăng nhập tại hệ thống đích
              |
              v
Tiến trình, tác vụ hoặc giao dịch liên quan
~~~

Đây là các lớp logic. Một số hệ thống có thể gộp hoặc bổ sung lớp khác.

Ví dụ, cổng PAM hết hạn đăng nhập nhưng một phiên quản trị do broker mở trước đó vẫn có thể đang chạy nếu không có ràng buộc chấm dứt tương ứng.

Ngược lại, đóng kênh từ người dùng đến broker có thể không làm hệ thống đích đăng xuất tài khoản. Cần kiểm tra hành vi cụ thể của đường truy cập.

### Hợp đồng của một chính sách timeout

Mỗi chính sách cần trả lời:

1. Nó áp dụng cho phiên nào?
2. Mốc bắt đầu và nguồn thời gian là gì?
3. Hoạt động nào được tính?
4. Thành phần nào quyết định hết hạn?
5. Thành phần nào thực thi ở đích?
6. Kết quả được coi là hoàn tất là gì?
7. Nếu không xác minh được thì ai tiếp nhận?

Không nên dùng một cấu hình chung tên “session timeout” mà không biết những câu trả lời này.

## 4. Hoạt động nào được tính cho idle timeout?

Idle timeout cần một định nghĩa hoạt động có ý nghĩa đối với loại phiên.

| Tín hiệu | Cách đánh giá |
| --- | --- |
| Thao tác nhập được nhận qua kênh phiên đã xác thực | Có thể là hoạt động theo chính sách của giao thức |
| Hành động quản trị hợp lệ qua API | Có thể được tính nếu gắn đúng phiên và principal |
| Keepalive của giao thức | Không tự chứng minh có hoạt động người dùng |
| Dữ liệu đầu ra liên tục từ tác vụ | Không tự chứng minh người dùng đang tương tác |
| Trang web tự tải lại hoặc polling | Không nên mặc định giữ phiên đặc quyền sống |
| Tín hiệu “đang hoạt động” do client tự khai báo | Cần cơ chế xác minh, không tin tùy ý |
| Di chuyển hoặc thao tác đầu vào trong phiên đồ họa | Chỉ có ý nghĩa theo khả năng quan sát và chính sách cụ thể |

Không có một loại tín hiệu phù hợp cho mọi giao thức. Cần kiểm tra thành phần thực thi thực sự nhìn thấy gì.

### Nguồn hoạt động phải đáng tin cậy

Thời điểm hoạt động nên được ghi nhận tại thành phần tin cậy xử lý phiên, theo quy tắc đã định nghĩa. Không cho client tự gửi một timestamp tương lai để kéo dài phiên.

Một tín hiệu từ phiên khác hoặc người khác không được vô tình cập nhật idle timer của phiên hiện tại.

### Không dùng thao tác giả để duy trì quyền

Nếu một công việc cần chạy lâu, giải pháp không nên là tự phát thao tác vô nghĩa để tránh idle timeout.

Cần thiết kế luồng phù hợp: tác vụ được quản lý riêng, danh tính dịch vụ có quyền hẹp hoặc một profile phiên được chấp nhận cho nhiệm vụ đó.

## 5. Kết hợp idle, absolute và thời hạn quyền

Giả sử:

- Mốc bắt đầu phiên là S.
- Thời lượng tối đa là A.
- Thời điểm hoạt động hợp lệ gần nhất là L.
- Giới hạn nhàn rỗi là I.
- Quyền cho nhiệm vụ kết thúc tại G.

Nếu chính sách đã ràng buộc những điều kiện này với việc tiếp tục phiên, hạn tiếp tục có thể được mô tả:

~~~text
Hạn absolute = S + A
Hạn idle     = L + I

Hạn tiếp tục theo các điều kiện thời gian
    = thời điểm sớm nhất giữa các hạn đang áp dụng
~~~

Điều kiện thu hồi, rủi ro hoặc thay đổi trạng thái có thể làm phiên phải dừng sớm hơn.

Công thức mô tả quyết định chính sách, không tự tạo cơ chế cắt kết nối. Các thành phần phải thực thi điều kiện trên đường thao tác và vòng đời phiên.

### Ví dụ minh họa

Một phiên bắt đầu lúc 10:00:

- Absolute timeout là 30 phút.
- Quyền JIT kết thúc lúc 10:25.
- Idle timeout là 5 phút.
- Hoạt động hợp lệ cuối cùng lúc 10:12.

Nếu không có hoạt động tiếp theo và không có điều kiện dừng sớm hơn, hạn idle là 10:17. Đây là thời điểm sớm nhất trong các hạn đang xét.

Keepalive lúc 10:15 không làm thay đổi kết quả nếu policy không tính keepalive là hoạt động.

Các con số chỉ phục vụ minh họa, không phải giá trị khuyến nghị chung.

### Hoạt động mới không vượt hạn quyền

Nếu có hoạt động hợp lệ lúc 10:24, hạn idle mới có thể là 10:29, nhưng quyền JIT vẫn kết thúc lúc 10:25.

Không để cập nhật idle timer vô tình kéo phiên qua phạm vi đã được cấp.

## 6. Timeout phải được thực thi ở đâu?

~~~mermaid
flowchart TD
    User[Người vận hành] --> Portal[Cổng PAM]
    Portal --> Policy[Chính sách và thời hạn]
    Policy --> Broker[Broker quản lý phiên]
    Broker --> Target[Hệ thống đích]
    Policy --> Timer[Bộ theo dõi thời hạn]
    Timer --> Block[Chặn tiếp tục hoặc tái sử dụng]
    Timer --> Terminate[Yêu cầu kết thúc tại lớp cần thiết]
    Terminate --> Broker
    Terminate --> Target
    Broker --> Evidence[Bằng chứng và đối soát]
    Target --> Evidence
~~~

### Tại cổng PAM

Cổng cần quản lý phiên truy cập giao diện hoặc API của chính nó. Đây là một lớp, không đủ thay thế toàn bộ kiểm soát phiên đích.

### Tại broker hoặc cổng thực thi

Thành phần trên đường truy cập cần ngăn thao tác tiếp tục khi phiên không còn được phép theo hợp đồng thực thi.

Nếu chỉ có một job chạy định kỳ kiểm tra quá hạn, cần hiểu độ trễ xử lý. Không tuyên bố chấm dứt ngay tại một timestamp khi thiết kế thực tế chỉ phát hiện sau đó.

### Tại hệ thống đích

Nếu mục tiêu yêu cầu đăng xuất hoặc kết thúc phiên đích, cần cơ chế tương ứng: tích hợp quản lý phiên, chính sách tại đích hoặc phương án được hỗ trợ khác.

Không mặc định mọi broker đều có khả năng kết thúc mọi loại phiên tại đích.

### Hành động đang chờ hoặc đang chạy

Cần định nghĩa khi nào quyền được kiểm tra:

- Trước khi tiếp nhận.
- Trước khi bắt đầu thực thi.
- Tại các điểm kiểm soát trong một tác vụ.
- Khi tiếp tục hoặc tái gắn kết nối.

Một hành động được xếp hàng trước thời điểm hết hạn nhưng thực thi sau đó cần được xử lý theo quy tắc rõ ràng.

Timeout không tự hoàn tác những thay đổi đã thực hiện.

## 7. Phân biệt ngắt kết nối, đăng xuất và kết thúc tác vụ

| Hành động | Điều có thể đạt | Điều chưa tự chứng minh |
| --- | --- | --- |
| Đóng tab hoặc client | Người dùng không còn giao diện đó | Broker và đích đã kết thúc phiên |
| Ngắt kênh tới broker | Kênh hiện tại không còn truyền thao tác | Phiên đích đã đăng xuất |
| Chặn reconnect | Không cho nối lại theo đường đó | Phiên cũ hoặc tiến trình đã dừng |
| Kết thúc phiên đích | Phiên đã được xử lý theo cơ chế đích | Mọi tác vụ tách rời hoặc credential phát sinh đã mất |
| Dừng một tác vụ | Tác vụ đó kết thúc theo kết quả xác minh | Mọi tác động trước đó đã được hoàn tác |

Ví dụ, một tác vụ nền có thể có vòng đời riêng sau khi kênh tương tác đã đóng, tùy cách hệ thống hoạt động.

Nếu mục tiêu là không cho phép công việc tiếp tục ngoài thời hạn, phải quản lý chính tác vụ đó. Chỉ cắt màn hình người dùng có thể không đáp ứng mục tiêu.

### Tác động đến dữ liệu

Kết thúc một phiên có thể ảnh hưởng giao dịch, công việc đang xử lý hoặc tính sẵn sàng. Hành vi rollback, hoàn tất hoặc tiếp tục phụ thuộc hệ thống.

Cần chuẩn bị cách xử lý phù hợp. Không giả định mọi thao tác đang chạy sẽ tự dừng an toàn hoặc tự hoàn tác.

## 8. Cảnh báo và trải nghiệm hết hạn

Cảnh báo giúp người dùng biết phiên sắp hết và xử lý công việc theo quy trình.

Thông tin hữu ích gồm:

- Lý do hoặc loại hạn sắp đạt.
- Thời điểm kết thúc dự kiến.
- Khả năng lưu công việc hoặc dừng tác vụ theo cách phù hợp.
- Cách yêu cầu tiếp nếu chính sách cho phép.
- Trạng thái khi phiên đã hết.

Cảnh báo không nên chứa credential, token hoặc dữ liệu nhạy cảm không cần thiết.

### Cảnh báo không tự gia hạn

Hiển thị cảnh báo hoặc client nhận thông báo không phải hoạt động hợp lệ của người dùng.

Một hành động tiếp tục được xác thực có thể cập nhật idle timer nếu policy cho phép, nhưng không tự vượt absolute timeout hoặc thời hạn quyền.

### Không yêu cầu phản hồi để thực thi hết hạn

Nếu người dùng không nhìn thấy cảnh báo, phiên vẫn phải được xử lý theo chính sách. Không để một hộp thoại chưa được xác nhận làm trì hoãn việc chấm dứt vô thời hạn.

Khi mất liên lạc với client, thành phần tin cậy vẫn phải quản lý thời hạn mà nó có trách nhiệm thực thi.

## 9. Gia hạn, xác thực lại và phiên mới

Cần phân biệt ba việc:

| Việc | Ý nghĩa |
| --- | --- |
| Có hoạt động mới | Có thể dời hạn idle theo policy |
| Xác thực lại | Đánh giá lại danh tính hoặc điều kiện xác thực |
| Gia hạn quyền hoặc cấp phiên mới | Một quyết định về khả năng tiếp tục sử dụng đặc quyền |

Xác thực lại thành công không tự chứng minh nhiệm vụ vẫn được phê duyệt. Một phiên nguồn danh tính được làm mới cũng không tự gia hạn quyền JIT tại đích.

### Gia hạn cần phạm vi

Nếu được phép, cần xác định:

- Ai có thể yêu cầu và ai quyết định.
- Tài nguyên, hành động và khoảng thời gian bổ sung.
- Điều kiện xác thực hoặc phê duyệt.
- Giới hạn tổng thể nếu có.
- Cách ghi nhận và thực thi tại đích.
- Cách xử lý nếu yêu cầu chưa xong khi phiên hết hạn.

Không tiếp tục cho quyền hoạt động chỉ vì yêu cầu gia hạn đang chờ.

### Không âm thầm đặt lại absolute timer

Nếu absolute timeout được định nghĩa là giới hạn của một phiên, hoạt động hoặc reconnect không nên âm thầm tạo lại mốc bắt đầu.

Nếu chính sách cho phép một phiên mới sau xác thực và cấp quyền mới, phải thể hiện đó là quyết định mới, có ID và bằng chứng liên kết phù hợp.

## 10. Reconnect và các kết nối đồng thời

### Reconnect không phải đường vượt timeout

Khi client kết nối lại, cần kiểm tra:

- Phiên còn hiệu lực không?
- Quyền và điều kiện còn đáp ứng không?
- Đây là tiếp tục phiên cũ hay yêu cầu mới?
- Hạn absolute và thời hạn quyền còn bao lâu?
- Có yêu cầu kết thúc đang chờ xác nhận không?

Không đặt idle và absolute về trạng thái ban đầu chỉ vì tạo một kết nối TCP mới.

### Nhiều tab hoặc nhiều client

Cần định nghĩa hoạt động được theo dõi theo phiên, theo người dùng hay theo một nhóm phiên.

Nếu một tab tự polling làm sống tất cả phiên đặc quyền của người dùng, giới hạn có thể khác hẳn ý định.

Với chia sẻ hoặc quan sát phiên, phải biết thao tác của ai được tính và danh tính nào đang thực thi quyền. Không dùng danh tính chung làm mất dấu người chịu trách nhiệm.

### Phiên đã kết thúc không được hồi sinh bởi sự kiện muộn

Một tín hiệu hoạt động đến trễ hoặc một gói reconnect cũ không được chuyển phiên đã đóng trở lại đang hoạt động.

Có thể cần ID, thế hệ và kiểm tra trạng thái để loại cập nhật đã cũ theo thiết kế.

## 11. Đồng hồ, failover và trạng thái phân tán

### Nguồn thời gian

Không dựa vào đồng hồ client để quyết định thời hạn. Cần nguồn thời gian tin cậy trong phạm vi hệ thống thực thi.

Đồng hồ đơn điệu có thể phù hợp cho đo khoảng trong một tiến trình, còn deadline bền vững và audit cần ngữ cảnh thời gian có thể đối chiếu. Hai nhu cầu phải được thiết kế cùng nhau.

Một giá trị đồng hồ đơn điệu của node này không tự có ý nghĩa trên node khác hoặc sau khởi động lại.

### Failover không được vô tình kéo dài phiên

Khi chuyển broker hoặc phục hồi trạng thái, cần biết:

- Mốc bắt đầu gốc.
- Deadline absolute và quyền.
- Hoạt động hợp lệ gần nhất có thể tin cậy.
- Trạng thái chấm dứt hoặc đối soát đang mở.
- Phiên tại đích đang thuộc node hoặc cơ chế nào quản lý.

Không coi thời điểm node mới tiếp nhận là lúc phiên bắt đầu lại.

Nếu trạng thái không đầy đủ, phải áp dụng quy tắc suy giảm đã xác định. Không tự giả định một khoảng thời gian mới dài hơn để thuận tiện.

### Cache và thông tin thu hồi

Một node có thể giữ policy hoặc trạng thái quyền cũ. Cần xác định thời gian hiệu lực của cache, cách nhận thu hồi và hành vi khi không kiểm tra được nguồn có thẩm quyền.

Không để mất liên lạc trở thành quyền tiếp tục vô thời hạn. Với thao tác nhạy cảm, có thể cần chặn thực thi mới khi không chứng minh được điều kiện theo profile đã chấp nhận.

Đường khẩn cấp phải có cơ chế riêng và bằng chứng, thay vì lặng lẽ bỏ kiểm soát timeout.

## 12. Tác vụ dài và tài khoản dịch vụ

Một phiên tương tác không phải lúc nào cũng là nơi phù hợp để chạy công việc dài.

Cần xem:

- Có cần con người giữ quyền trong toàn bộ thời gian không?
- Có thể chuyển thành một job có danh tính riêng và quyền hẹp không?
- Ai chịu trách nhiệm kết quả và khả năng dừng?
- Công việc có cần tiếp tục sau khi người dùng rời phiên không?
- Có kiểm soát thời lượng, đầu vào và đích riêng cho job không?

Nếu job được phép tiếp tục độc lập, cần ghi rõ rằng kết thúc phiên người dùng không đồng nghĩa kết thúc job. Ngược lại, nếu công việc phải dừng cùng phiên, cần cơ chế thực thi được xác minh.

### Không áp dụng máy móc idle của người dùng cho workload

Workload có chu kỳ hoạt động khác với con người. Các kết nối dịch vụ có thể cần timeout kết nối, thời hạn credential hoặc cơ chế tái xác thực khác.

Không coi việc không có thao tác bàn phím là lý do đủ để dừng mọi workload. Cũng không dùng tài khoản dịch vụ làm cách giữ phiên quản trị cá nhân tồn tại vô hạn.

## 13. Hồ sơ chính sách timeout

Ví dụ sau là **mô tả thiết kế minh họa, không phải cấu hình có thể chạy trực tiếp của một sản phẩm**. Các thời lượng chỉ phục vụ giải thích.

~~~yaml
session_policy:
  reference: privileged-maintenance-example
  applies_to: approved-interactive-maintenance
  owner_reference: production-resource-owner

time_limits:
  idle:
    duration: illustrative-five-minutes
    activity_source: trusted-session-input
    keepalive_counts_as_activity: false
    output_only_counts_as_activity: false
  absolute:
    duration: illustrative-thirty-minutes
    start_reference: original-session-start
    reset_on_reconnect: false
  entitlement:
    enforce_approved_end_time: true

renewal:
  requires_new_authorization: true
  authentication_alone_extends_entitlement: false

expiration:
  block_new_privileged_actions: required
  target_session_handling: supported-termination-process
  uncertain_result: reconcile-and-escalate

evidence:
  record_secret_values: false
  correlate:
    - requester
    - authorization-reference
    - pam-session-reference
    - target-session-reference
    - policy-version
~~~

Những trường trong hồ sơ là ý định thiết kế. Cần kiểm tra thành phần thực thi có thực sự hỗ trợ và áp dụng từng ý định không.

Nếu không hỗ trợ kết thúc phiên đích theo mục tiêu, phải nêu khoảng trống và phương án xử lý, không đánh dấu đã đạt chỉ vì cấu hình đã được lưu.

## 14. Ví dụ xuyên suốt: phiên bảo trì production

Một người vận hành được cấp phiên bảo trì qua broker. Theo ví dụ:

- Bắt đầu lúc 10:00.
- Absolute timeout là 30 phút.
- Quyền JIT kết thúc lúc 10:25.
- Idle timeout là 5 phút.
- Hoạt động hợp lệ cuối cùng lúc 10:12.

### Trường hợp không có thao tác tiếp

Broker vẫn gửi keepalive và nhận đầu ra của một tác vụ. Theo policy minh họa, hai tín hiệu này không cập nhật hoạt động của người dùng.

Đến 10:17, phiên đạt hạn idle. Hệ thống chặn thao tác mới, yêu cầu xử lý phiên tại đích và ghi bằng chứng.

Nếu chưa nhận được xác nhận từ đích, trạng thái đúng là đã hết quyền tiếp tục tại lớp thực thi và đang đối soát kết thúc phiên, chưa phải mọi khả năng ở đích đã hết.

### Trường hợp có thao tác trước hạn

Nếu một thao tác hợp lệ được nhận lúc 10:16, hạn idle mới có thể là 10:21. Absolute và thời hạn JIT vẫn giữ nguyên.

Nếu người dùng tiếp tục hoạt động đến sau 10:20, phiên vẫn phải tuân theo hạn JIT lúc 10:25. Hoạt động không tự gia hạn quyết định cấp quyền.

### Trường hợp reconnect

Nếu client mất kết nối rồi nối lại, cần dùng trạng thái phiên gốc và hạn còn hiệu lực. Không tạo một khoảng 30 phút mới chỉ vì client mở lại cửa sổ.

Nếu phiên đã bị kết thúc, cần một yêu cầu mới theo chính sách, không hồi sinh phiên bằng sự kiện hoạt động cũ.

### Trường hợp tác vụ vẫn chạy

Nếu một tiến trình tại đích tiếp tục sau khi phiên bị đóng, cần xác định nó có được phép tồn tại độc lập không.

Đây là vấn đề quản lý tác vụ và tác động, không thể suy ra chỉ từ thông báo timeout của broker.

## 15. Bằng chứng cho timeout

Những sự kiện hữu ích có thể gồm:

| Sự kiện | Nội dung cần giải thích |
| --- | --- |
| Phiên bắt đầu | Danh tính, quyền, đích, policy và các hạn áp dụng |
| Hoạt động được chấp nhận | Nguồn và quy tắc cập nhật trạng thái, không cần ghi bí mật |
| Cảnh báo | Loại hạn, thời điểm và kênh gửi |
| Đạt điều kiện hết hạn | Lý do, deadline và trạng thái liên quan |
| Chặn thao tác hoặc reconnect | Quyết định thực thi tại lớp nào |
| Yêu cầu kết thúc | Thành phần thực hiện và phiên đích |
| Xác nhận kết thúc | Kết quả được quan sát tại đích |
| Kết quả chưa rõ | Nguyên nhân, việc đối soát và người tiếp nhận |
| Gia hạn hoặc phiên mới | Thẩm quyền, phạm vi và thời hạn mới |

Không nên chỉ ghi một sự kiện “closed” mà không định nghĩa nó nói về kênh, phiên broker hay phiên đích.

### Liên kết danh tính và thời gian

Cần liên kết người yêu cầu, tài khoản đích, ID phiên PAM, ID phiên đích nếu có và quyết định cấp quyền.

Thời điểm policy yêu cầu hết hạn, thời điểm bắt đầu xử lý và thời điểm xác minh kết thúc có thể khác nhau. Những mốc này giúp thấy độ trễ thực thi.

Không có sự kiện xác nhận chưa tự chứng minh đích vẫn còn phiên; có thể là mất bằng chứng. Cần giữ trạng thái chưa xác định cho tới khi đối soát được.

### Bảo vệ dữ liệu

Bản ghi phiên có thể chứa dữ liệu nhạy cảm. Quyền xem, xuất và lưu giữ phải phù hợp.

Không ghi token, mật khẩu hoặc dữ liệu xác thực vào thông báo timeout hay log chẩn đoán.

## 16. Kiểm tra cơ chế timeout

Một ma trận xác minh nên bao phủ những điều kiện thực sự áp dụng:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có hoạt động hợp lệ | Idle timeout được kích hoạt theo policy |
| Chỉ có keepalive hoặc polling | Không vô tình kéo dài phiên nếu policy không tính |
| Có hoạt động hợp lệ | Chỉ cập nhật hạn idle trong phạm vi cho phép |
| Người dùng hoạt động liên tục | Absolute timeout vẫn được thực thi |
| Quyền JIT kết thúc sớm hơn | Không tiếp tục đặc quyền ngoài hạn đã cấp |
| Reconnect trước hạn | Giữ giới hạn gốc và kiểm tra điều kiện |
| Reconnect sau khi đã kết thúc | Không hồi sinh phiên cũ |
| Xác thực lại nhưng chưa gia hạn quyền | Không tự kéo dài quyền ở đích |
| Failover broker | Không đặt lại thời hạn như một phiên mới |
| Mất xác nhận từ đích | Có trạng thái đối soát và escalation |
| Tác vụ dài | Hành vi tiếp tục hoặc dừng đúng hợp đồng đã định nghĩa |

Các phép thử phải phù hợp mức tác động. Có thể dùng môi trường đại diện hoặc phiên kiểm tra được kiểm soát; không tự ngắt hàng loạt phiên vận hành.

### Kiểm tra tại ranh giới

Cần xác minh hành vi của thao tác đến sát thời điểm hết hạn hoặc đang chờ thực thi. Một bộ đếm trên giao diện không đủ chứng minh chặng thực thi ngăn hành động sau hạn.

Phải kiểm tra theo ngữ nghĩa đã cam kết: chặn yêu cầu mới, chặn thực thi mới hay kết thúc cả tác vụ đang chạy. Không đánh giá một kết quả theo một cam kết chưa được thiết kế.

### Chỉ kết luận theo bằng chứng

Cấu hình lưu thành công chưa chứng minh timeout hoạt động. Client bị ngắt chưa chứng minh phiên đích đã kết thúc.

Nếu chỉ xác minh được một phần, báo rõ phần đó cùng giới hạn còn lại.

## 17. Ngoại lệ và quản trị chính sách

Một số công việc có thể cần profile thời gian khác, nhưng ngoại lệ cần cụ thể:

- Nhiệm vụ và tài nguyên.
- Người hoặc nhóm được áp dụng.
- Thời gian hiệu lực.
- Lý do không dùng profile thông thường.
- Phạm vi quyền và biện pháp bù đắp.
- Người có thẩm quyền chấp nhận.
- Cách kết thúc và review sau sử dụng.

Không tạo ngoại lệ “không timeout” cho toàn bộ quản trị viên chỉ vì một công việc dài.

### Phân công

Resource owner và chủ sở hữu công việc xác nhận nhu cầu. Nhóm bảo mật hỗ trợ đánh giá rủi ro. Đội PAM và hệ thống đích triển khai khả năng thực thi được giao.

Cần có người chịu trách nhiệm khi phiên hết hạn trên PAM nhưng kết quả tại đích chưa rõ. Việc chỉ gửi một thông báo không thay thế tiếp nhận và xử lý.

### Khi chính sách thay đổi

Cần xác định thay đổi tác động đến phiên đang chạy hay chỉ phiên mới. Nếu mục tiêu là thu hồi khẩn cấp, chờ mọi phiên tự hết theo cấu hình cũ có thể không đáp ứng.

Hành vi phải được công bố và xác minh theo khả năng nền tảng.

## 18. Theo dõi chất lượng thực thi

Những chỉ số hữu ích có thể gồm:

- Số phiên được bao phủ bởi profile đã xác nhận.
- Phiên đạt hạn nhưng chưa có kết quả xử lý rõ.
- Độ trễ từ deadline đến chặn thao tác.
- Độ trễ đến xác minh kết thúc tại đích.
- Reconnect hoặc thao tác bị từ chối sau hết hạn.
- Gia hạn và ngoại lệ theo nhiệm vụ.
- Phiên kéo dài do thiếu trạng thái hoặc lỗi failover.
- Khoảng trống audit và lỗi ánh xạ phiên đích.

Cần tách số phiên, số kết nối và số tác vụ. Một phiên có thể có nhiều kết nối hoặc nhiều hành động.

Không dùng tỷ lệ “có thông báo timeout” làm đại diện cho tỷ lệ phiên đã kết thúc thực tế.

Nếu dữ liệu thiếu, cần ghi mức bao phủ. Không có cảnh báo không chứng minh không tồn tại phiên quá hạn.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ cấu hình timeout trên cổng PAM | Phiên đích có thể tiếp tục | Xác định lớp thực thi và xác minh tại đích |
| Dùng keepalive làm hoạt động người dùng | Idle timeout không đạt mục tiêu | Định nghĩa tín hiệu hoạt động theo giao thức |
| Reconnect đặt lại mọi bộ đếm | Có thể vượt absolute hoặc JIT | Giữ trạng thái phiên và deadline gốc |
| Xác thực lại là tự gia hạn quyền | Vượt phạm vi quyết định truy cập | Tách xác thực và cấp quyền |
| Đóng client rồi coi đã logout | Phiên broker hoặc đích còn tồn tại | Kiểm tra từng lớp phiên |
| Đổi password để kết thúc mọi phiên | Một số phiên có vòng đời độc lập | Dùng cơ chế xử lý phiên phù hợp |
| Cắt phiên là coi tác vụ đã dừng | Có thể còn công việc nền | Quản lý tác vụ và kết quả riêng |
| Failover tạo thời hạn mới | Vô tình kéo dài quyền | Khôi phục trạng thái và đối soát |
| Kết quả chưa rõ vẫn ghi hoàn tất | Che khoảng trống containment | Giữ việc mở và escalation |
| Bỏ timeout chung cho công việc dài | Tăng phạm vi rủi ro | Profile hoặc luồng tác vụ có giới hạn |

## 20. Bài tập tự đánh giá

Một hệ thống đặt idle timeout cho phiên quản trị. Client gửi keepalive định kỳ nên phiên không bao giờ bị coi là nhàn rỗi. Cổng PAM hết hạn đăng nhập nhưng phiên đích vẫn hoạt động. Khi người dùng reconnect, broker tính lại absolute timeout từ đầu. Nhóm vận hành kết luận không có vấn đề vì mật khẩu đã được rotation sau phiên.

Hãy trả lời:

1. Keepalive có đủ chứng minh người dùng đang hoạt động không?
2. Những lớp phiên nào đang bị đánh đồng?
3. Reconnect đặt lại absolute timer tạo khả năng gì?
4. Rotation có tự kết thúc phiên hiện hữu không?
5. Cần bằng chứng nào để xác nhận timeout đã được thực thi?
6. Tác vụ nền còn chạy sau khi ngắt phiên cần được xử lý thế nào?

### Gợi ý phân tích

**Hoạt động:** phải theo policy và nguồn tin cậy; giữ kết nối mạng không tự chứng minh tương tác con người.

**Các lớp:** phiên cổng PAM, broker, hệ thống đích và tác vụ có vòng đời khác nhau.

**Reconnect:** có thể cho phép kéo dài một phiên vượt giới hạn tổng thể nếu không giữ mốc gốc và kiểm tra quyền.

**Rotation:** ảnh hưởng credential theo cơ chế đích; không tự bảo đảm mọi phiên cũ mất hiệu lực.

**Bằng chứng:** cần deadline, quyết định, hành động chặn hoặc kết thúc, xác nhận ở lớp đích và trạng thái chưa rõ nếu có.

**Tác vụ:** xác định nó có được phép tiếp tục độc lập không, ai chịu trách nhiệm và cơ chế thực thi. Không suy ra tác vụ đã dừng chỉ từ việc client bị ngắt.

## 21. Những điểm cần ghi nhớ

- Idle, absolute, thời hạn quyền và thời hạn credential là những cơ chế khác nhau.
- Hoạt động phải được định nghĩa theo giao thức và nguồn tin cậy; keepalive không tự là hoạt động người dùng.
- Timeout cần có thành phần quyết định, thực thi và xác minh rõ ràng.
- Hết hạn giao diện hoặc ngắt kết nối không tự chứng minh phiên đích và tác vụ đã kết thúc.
- Gia hạn, xác thực lại, reconnect và failover không nên âm thầm mở rộng quyền.
- Cần quản lý tác vụ dài và ngoại lệ bằng phạm vi cụ thể thay vì bỏ timeout chung.
- Chỉ báo hoàn tất theo kết quả đã xác minh; phần chưa rõ phải có owner, đối soát và bằng chứng.
