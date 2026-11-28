# RTO của PAM

## 1. RTO trả lời câu hỏi gì?

Khi hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM) gặp sự cố, đội vận hành cần biết sau bao lâu họ có thể quản trị lại những hệ thống quan trọng bằng một luồng truy cập được kiểm soát. Đó là vấn đề mà Recovery Time Objective (RTO) giúp làm rõ.

**RTO là mục tiêu thời gian khôi phục một dịch vụ hoặc năng lực đã xác định sau gián đoạn.** Với PAM, năng lực ấy có thể là mở một phiên quản trị qua bastion, cấp quyền JIT, lấy credential từ vault cho một workload hoặc thu hồi một quyền đặc biệt đang tồn tại.

Một phát biểu như “RTO của PAM là 10 phút” chỉ hữu ích khi có thêm phạm vi và điều kiện:

> Trong kịch bản mất một vùng phục vụ, luồng mở phiên SSH quản trị mới đến nhóm máy chủ trọng yếu phải được khôi phục trong 10 phút kể từ khi luồng đó bắt đầu không đáp ứng tiêu chí dịch vụ. Luồng phục hồi phải xác thực người dùng, áp dụng chính sách quyền, ghi bằng chứng phiên và phục vụ được tải tối thiểu đã thỏa thuận.

Các con số trong bài là ví dụ để thực hành, không phải mức RTO mặc định cho mọi tổ chức. Mục tiêu thực tế phải xuất phát từ tác động nghiệp vụ, khả năng vận hành và năng lực phục hồi đã được kiểm chứng.

Trong chương High availability, RTO là cầu nối giữa kiến trúc dự phòng và nhu cầu sử dụng. Có nhiều node hoặc nhiều vùng là đặc tính của thiết kế; phục hồi đúng thời gian, đúng năng lực và đúng kiểm soát mới là kết quả cần đo.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Xác định điểm bắt đầu và điều kiện kết thúc của phép đo RTO cho một luồng PAM.
- Phân biệt RTO với thời gian phục hồi thực tế, RPO và chỉ tiêu availability.
- Lập ngân sách thời gian phục hồi dựa trên chuỗi phụ thuộc.
- Phân biệt khôi phục dịch vụ chuẩn với truy cập khẩn cấp có giới hạn.
- Thiết kế diễn tập và lưu bằng chứng đủ để kết luận đạt hoặc chưa đạt RTO.

## 2. Phân biệt các chỉ tiêu dễ bị nhầm

| Khái niệm | Câu hỏi chính | Ví dụ trong PAM |
|---|---|---|
| RTO | Cần khôi phục năng lực đã định trong bao lâu? | Mở phiên quản trị Tier 0 trong tối đa 10 phút sau gián đoạn thuộc phạm vi |
| Thời gian phục hồi thực tế | Lần sự cố hoặc diễn tập này mất bao lâu? | Luồng mở phiên đạt đủ tiêu chí sau 8 phút 20 giây |
| RPO — Recovery Point Objective | Có thể chấp nhận mất dữ liệu đến mức nào, diễn đạt theo khoảng thời gian? | Mục tiêu mất không quá một phút cập nhật đối với loại dữ liệu đã xác định |
| Availability | Dịch vụ đáp ứng tiêu chí sẵn sàng trong bao nhiêu phần thời gian đo? | Tỷ lệ khoảng thời gian luồng mở phiên thành công trong tháng |
| Thời gian phát hiện | Sau khi gián đoạn bắt đầu, mất bao lâu để nhận biết? | Cảnh báo phát hiện luồng truy cập lỗi sau 25 giây |
| Thời gian phục hồi thành phần | Một thành phần trở lại hoạt động sau bao lâu? | Vault trả lời health check sau bốn phút |

RTO là mục tiêu; thời gian phục hồi thực tế là kết quả quan sát. Việc một lần diễn tập đạt 8 phút không tự biến RTO đã phê duyệt thành 8 phút.

RTO và RPO tác động lẫn nhau nhưng không thay thế cho nhau. Một vault có thể phục hồi rất nhanh từ bản sao cũ, trong khi credential tại máy đích đã được rotation. Vault mở được không đồng nghĩa credential đọc ra còn sử dụng được. Nếu policy thu hồi mới nhất chưa có trên bản sao phục hồi, hệ thống còn có nguy cơ cho phép quyền vốn đã bị thu hồi.

Availability cũng không suy ra trực tiếp RTO. Hai hệ thống có tổng thời gian gián đoạn bằng nhau trong một kỳ có thể khác hẳn: một hệ thống bị nhiều lần ngắn, hệ thống còn lại có một lần kéo dài. Muốn biết có đáp ứng nhu cầu phục hồi hay không, phải nhìn từng kịch bản và thời gian của từng luồng.

Nếu tổ chức sử dụng giới hạn gián đoạn tối đa có thể chịu đựng, cần làm rõ giới hạn ấy bao gồm những gì. Ngân sách phục hồi PAM thường chỉ là một phần của thời gian mà dịch vụ nghiệp vụ cần để trở lại hoạt động.

## 3. Đặt RTO theo năng lực, không theo màn hình đăng nhập

PAM không phải một ứng dụng đơn lẻ. Một người dùng có thể đăng nhập portal thành công nhưng không được mở phiên đến máy đích. Một workload có thể kết nối vault nhưng không lấy được credential hợp lệ. Một phiên có thể mở được nhưng thiếu ghi bằng chứng bắt buộc.

Vì vậy, cần chọn đơn vị đo gắn với công việc thật.

| Năng lực | Điều kiện phục hồi có ý nghĩa |
|---|---|
| Mở phiên quản trị mới | Người đúng quyền xác thực được, policy được áp dụng, phiên tới đích thành công, bằng chứng được lưu theo yêu cầu |
| Cấp quyền JIT | Yêu cầu được xét duyệt đúng, quyền xuất hiện tại hệ đích, TTL và cơ chế hết hạn hoạt động |
| Lấy secret cho workload | Workload xác thực được, nhận secret đúng phiên bản, dùng được tại đích trong phạm vi quyền đã định |
| Thu hồi quyền hoặc kết thúc phiên | Yêu cầu thu hồi có hiệu lực tại điểm thực thi, có bằng chứng xác nhận kết quả |
| Rotation credential | Đổi credential tại đích và cập nhật trạng thái liên quan nhất quán, kiểm tra sử dụng lại thành công |
| Tra cứu bằng chứng | Người có quyền truy xuất được dữ liệu cần cho điều tra hoặc vận hành theo thời gian yêu cầu |

Những năng lực này có thể có RTO khác nhau. Không nên tự đặt cùng một mục tiêu cho portal báo cáo, cấp quyền mới và thu hồi quyền đang bị lạm dụng.

Ví dụ, trong một sự cố an ninh, khả năng **ngăn tiếp tục sử dụng quyền** có thể khẩn cấp hơn khả năng cấp một phiên mới. Nếu chỉ đo mở phiên, báo cáo “PAM đã phục hồi” có thể che khuất việc đội ứng phó vẫn chưa thu hồi được phiên nghi vấn.

### 3.1. Phiên đang chạy và phiên mới là hai đối tượng khác nhau

Khi control plane bị gián đoạn, một số phiên đang mở có thể tiếp tục chạy. Điều đó không chứng minh rằng:

- Người quản trị khác có thể tạo phiên mới.
- Phiên đang chạy vẫn bị kết thúc được khi cần.
- Bằng chứng phiên vẫn được ghi đầy đủ.
- Quyền tạm thời sẽ được thu hồi đúng hạn.
- Credential hết hạn có thể được gia hạn hoặc thay thế hợp lệ.

Nên theo dõi riêng tính liên tục của phiên hiện hữu, thời gian khôi phục mở phiên mới và thời gian khôi phục thu hồi quyền. Kết luận phục hồi cần nêu rõ năng lực nào đã đạt.

### 3.2. Tải tối thiểu cũng là một phần của định nghĩa

Một phiên kiểm thử thành công chưa đủ nếu đội vận hành cần 30 phiên đồng thời để xử lý sự cố hạ tầng.

Ví dụ tiêu chí có thể yêu cầu:

- Phục vụ tối thiểu 20 phiên quản trị đồng thời đến tập đích trọng yếu.
- Thời gian mở phiên nằm trong ngưỡng được thỏa thuận.
- Tài khoản thiếu quyền vẫn bị từ chối.
- Đường thu hồi và bằng chứng hoạt động.
- Hệ thống duy trì trạng thái đạt yêu cầu trong một khoảng quan sát đã định trước.

Giá trị tải và khoảng quan sát phải được quyết định trước phép thử. Nếu thay tiêu chí sau khi đã thấy kết quả, phép đo không còn chứng minh được mục tiêu ban đầu.

## 4. Chọn mốc thời gian để không đo thiếu

Trong bài này, sử dụng hai mốc:

- `t0`: thời điểm luồng thuộc phạm vi bắt đầu không đáp ứng tiêu chí dịch vụ.
- `tR`: thời điểm hoàn tất xác nhận rằng luồng đã trở lại trạng thái phục hồi được chấp nhận, bao gồm khoảng quan sát nếu tiêu chí yêu cầu.

Khi đó:

```text
Thời gian phục hồi thực tế = tR - t0

Đạt mục tiêu thời gian khi:
    (tR - t0) <= RTO đã phê duyệt

Đạt toàn bộ mục tiêu phục hồi khi:
    đạt mục tiêu thời gian
    và đạt điều kiện chức năng, kiểm soát, dữ liệu, tải đã định
```

Nếu tổ chức dùng quy ước bắt đầu khác, chẳng hạn từ lúc tuyên bố sự cố, cần ghi rõ quy ước và đo thêm thời gian từ gián đoạn đến tuyên bố. Không được dùng con số nhỏ hơn để thay thế thời gian gián đoạn người dùng thực sự trải qua.

### 4.1. Những mốc thường bị bỏ sót

**Phát hiện:** Người dùng đã không mở được phiên từ 09:00 nhưng cảnh báo xuất hiện lúc 09:02. Hai phút đó vẫn thuộc thời gian phục hồi nếu `t0` là lúc gián đoạn bắt đầu.

**Ra quyết định:** Cần người có thẩm quyền xác nhận chuyển vùng, mở khóa phục hồi hoặc kích hoạt quy trình khẩn cấp. Khoảng chờ này phải có trong ngân sách.

**Đường truy cập đến hệ đích:** Vault và portal đã lên nhưng DNS, tuyến mạng, connector hoặc bastion vẫn hỏng. Luồng quản trị chưa được phục hồi.

**Khôi phục kiểm soát:** Đăng nhập được nhưng policy hoặc bằng chứng chưa đạt yêu cầu. Chưa thể kết thúc phép đo của dịch vụ chuẩn nếu các kiểm soát ấy là điều kiện bắt buộc.

**Ổn định và tải:** Một lần thử thành công ngay sau promote có thể là thành công ngẫu nhiên. Khoảng xác nhận ổn định phải được tính theo tiêu chí đã đặt.

### 4.2. Đồng bộ thời gian và độ không chắc chắn

Các mốc có thể đến từ synthetic probe, hệ thống giám sát, log của vault, bastion và máy đích. Nếu đồng hồ lệch nhau, phép trừ timestamp dễ cho kết quả sai.

Khi thu thập bằng chứng:

- Lưu timezone hoặc chuẩn hóa timestamp về cùng một chuẩn.
- Ghi nguồn phát sinh của từng mốc.
- Lưu chu kỳ chạy probe và độ trễ ghi nhận cảnh báo.
- Phân biệt thời điểm sự kiện xảy ra với thời điểm log đến hệ thống tập trung.
- Trong một tiến trình đo, có thể dùng đồng hồ đơn điệu để tính elapsed time; vẫn cần timestamp có thể đối chiếu giữa các hệ thống.

Nếu probe chạy mỗi 30 giây, thời điểm phát hiện lỗi đầu tiên không nhất thiết là thời điểm lỗi bắt đầu chính xác. Báo cáo phải nêu sai số hoặc khoảng ước lượng, thay vì tuyên bố độ chính xác đến mili giây.

## 5. Từ tác động nghiệp vụ đến mục tiêu PAM

RTO cần bắt đầu từ câu hỏi: công việc nào sẽ không thể hoàn tất nếu PAM bị gián đoạn?

Giả sử một dịch vụ thanh toán phải phục hồi trong 30 phút. Đội cơ sở dữ liệu cần tối đa 12 phút thao tác sau khi đã có quyền quản trị, còn kiểm tra nghiệp vụ cần 5 phút. Nếu các công việc này thực sự nối tiếp nhau, chỉ còn tối đa 13 phút cho việc phục hồi đường truy cập và các phụ thuộc đi trước, chưa tính dự phòng.

Không thể đặt PAM RTO bằng đúng 30 phút rồi kết luận đã hỗ trợ mục tiêu nghiệp vụ. Đội sửa dịch vụ cần quyền truy cập đủ sớm để còn thời gian thực hiện công việc.

Cách làm thực tế:

1. Xác định dịch vụ nghiệp vụ và giới hạn gián đoạn có thể chịu đựng.
2. Liệt kê thao tác đặc quyền bắt buộc để khôi phục dịch vụ đó.
3. Xác định nhóm người, workload và tập đích cần phục vụ trước.
4. Vẽ quan hệ trước–sau giữa truy cập PAM và thao tác sửa chữa.
5. Phân bổ ngân sách phục hồi cho từng đường đi.
6. Kiểm tra khả năng đáp ứng bằng diễn tập.
7. Phê duyệt mục tiêu cùng giới hạn và phần rủi ro còn lại.

### Ví dụ phân tầng mục tiêu

| Phạm vi minh họa | Mục tiêu minh họa | Điều kiện đáng chú ý |
|---|---|---|
| Truy cập sửa hạ tầng định danh và mạng trọng yếu | 10 phút | Tập người và đích được định danh trước; có bằng chứng và thu hồi |
| Secret cho workload nghiệp vụ ưu tiên | 15 phút | Secret khớp trạng thái tại đích; tải tối thiểu được kiểm tra |
| Truy cập quản trị hệ thống hỗ trợ | 60 phút | Khôi phục sau luồng trọng yếu |
| Báo cáo quản trị không khẩn cấp | 4 giờ | Có thể phục hồi sau các năng lực điều khiển quyền |

Bảng chỉ minh họa phương pháp phân tầng. Cùng một portal có thể phục vụ nhiều nhóm luồng với độ ưu tiên khác nhau; việc phân tầng không nhất thiết đồng nghĩa phải triển khai nhiều sản phẩm PAM.

Mục tiêu cũng nên chỉ rõ kịch bản: mất node, mất vùng, mất dịch vụ định danh, hỏng dữ liệu và xâm nhập hệ thống có thể cần phương án phục hồi khác nhau.

## 6. RTO phụ thuộc cả chuỗi truy cập

Một luồng truy cập đặc quyền có thể đi qua:

```text
Người quản trị
  -> thiết bị quản trị được phép
  -> định danh / MFA
  -> đánh giá policy / phê duyệt
  -> vault / cấp credential hoặc chứng thư ngắn hạn
  -> connector / bastion / session proxy
  -> hệ thống đích

Phụ thuộc đi kèm:
  DNS, đồng bộ thời gian, mạng, khóa giải mã,
  dữ liệu policy, bằng chứng, đội trực và kênh điều phối
```

Không phải hệ thống nào cũng có đầy đủ các thành phần trên. Cần vẽ đúng đường đi đang triển khai, bao gồm các phụ thuộc do tổ chức hoặc nhà cung cấp khác sở hữu.

### 6.1. Những vòng phụ thuộc làm hỏng kế hoạch

Một số vòng phụ thuộc điển hình:

- Muốn sửa dịch vụ định danh phải mở phiên qua PAM, nhưng PAM chỉ chấp nhận đăng nhập qua dịch vụ định danh đang hỏng.
- Muốn khôi phục vault phải lấy credential từ chính vault đó.
- Muốn chuyển tuyến mạng phải dùng tài khoản quản trị mà credential chỉ có ở vùng đã mất.
- Muốn phê duyệt break-glass phải dùng hệ thống ticket nằm trong phạm vi sự cố.
- Muốn mở khóa bản phục hồi cần người giữ khóa chưa có trong lịch trực hoặc không có kênh liên lạc độc lập.

Các vòng này không được giải quyết chỉ bằng thêm một node dự phòng. Cần thiết kế trước đường bootstrap có phạm vi nhỏ, được quản lý riêng và được diễn tập.

Một đường bootstrap hợp lệ cần xác định người được dùng, điều kiện kích hoạt, cơ chế bảo vệ credential, TTL nếu có, bằng chứng sử dụng và công việc thu hồi hoặc rotation sau đó. Đường này phải đủ độc lập với thành phần có thể hỏng nhưng vẫn chịu kiểm soát.

### 6.2. Quorum và fencing có thể chiếm thời gian

Chuyển sang node khác không chỉ là bật dịch vụ. Hệ thống có trạng thái cần bảo đảm node cũ không tiếp tục ghi trái với node mới.

Nếu mạng phân vùng, việc không liên lạc được với node cũ không chứng minh node đó đã ngừng phục vụ. Quá trình cô lập quyền ghi hoặc bảo đảm chỉ còn một bên có thẩm quyền thường được gọi là fencing.

Trong kế hoạch RTO, cần tính cả thời gian xác nhận điều kiện chuyển vai trò an toàn. Không được cắt bước này chỉ để giảm số phút báo cáo, vì hai bên cùng cấp hoặc thay đổi credential có thể tạo trạng thái không nhất quán.

### 6.3. Khóa giải mã và dữ liệu khôi phục là hai phụ thuộc riêng

Có bản sao dữ liệu vault chưa đủ nếu không thể truy cập khóa cần thiết để mở dữ liệu đó. Ngược lại, có khóa nhưng dữ liệu không hợp lệ cũng không phục hồi được.

Kế hoạch cần kiểm chứng:

- Bản sao và phiên bản dữ liệu nào sẽ được sử dụng.
- Ai hoặc thành phần nào có thể cung cấp vật liệu mở khóa.
- Khóa có sử dụng được trong địa điểm hoặc vùng phục hồi hay không.
- Các bước phê duyệt và phân tách nhiệm vụ cần bao lâu.
- Dữ liệu, policy và credential có còn nhất quán với hệ đích hay không.

Không ghi khóa hoặc secret thực vào tài liệu diễn tập và bằng chứng đo RTO.

## 7. Lập ngân sách thời gian phục hồi

Một ngân sách mẫu cho mục tiêu 10 phút có thể như sau:

| Công đoạn trên đường đi găng minh họa | Ngân sách |
|---|---:|
| Phát hiện và nhận cảnh báo | 40 giây |
| Phân loại, nhận trách nhiệm và quyết định phục hồi | 60 giây |
| Cô lập bên lỗi, xác nhận điều kiện chuyển vai trò | 100 giây |
| Khôi phục vault và thành phần phục vụ cần thiết | 120 giây |
| Xác minh luồng truy cập cùng các kiểm soát | 100 giây |
| Đạt tải tối thiểu và hoàn tất quan sát ổn định | 120 giây |
| Tổng công đoạn | 540 giây |
| Dự phòng trong mục tiêu 600 giây | 60 giây |

Đây là ví dụ các công đoạn được mô hình hóa nối tiếp để dễ theo dõi. Trong thực tế, một số việc có thể diễn ra đồng thời.

```text
Nếu các bước nối tiếp:
    T = T1 + T2 + ... + Tn

Nếu hai nhánh độc lập thực sự chạy song song
và cả hai đều phải xong trước bước tiếp theo:
    T_nhanh = max(T_A, T_B)

Tổng thời gian đến phục hồi:
    thời gian của đường phụ thuộc dài nhất
    cộng các bước chung trước và sau đường đó
```

Không lấy tổng thời gian của mọi đội cộng lại nếu họ làm song song. Cũng không lấy giá trị lớn nhất nếu đội B thực tế phải đợi kết quả từ đội A.

Ví dụ, chuẩn bị máy đích kiểm thử và kiểm tra kênh điều phối có thể chạy đồng thời. Nhưng mở dữ liệu vault rồi kiểm tra credential lấy từ dữ liệu đó có quan hệ trước–sau.

### 7.1. Tìm nút thắt từ bằng chứng

Nếu ngân sách dự kiến cho mở khóa là 2 phút nhưng ba lần diễn tập đều mất khoảng 7 phút vì chờ hai người giữ khóa, nút thắt nằm ở quy trình và khả năng sẵn sàng của con người.

Hướng cải thiện có thể là bố trí lịch trực phù hợp, chuẩn bị kênh phê duyệt độc lập hoặc điều chỉnh cơ chế phục hồi đã được phê duyệt. Không tự loại bỏ yêu cầu hai người chỉ để đạt chỉ tiêu.

Tương tự, thêm CPU cho vault không giải quyết được 5 phút chờ DNS hoặc 8 phút chờ người có quyền chuyển vùng.

### 7.2. RTO phải có phần dự phòng

Một kế hoạch sử dụng hết 600 giây trong điều kiện thuận lợi sẽ dễ trượt khi có độ trễ mạng, người trực nhận việc muộn hoặc tải cao.

Dự phòng phải dựa trên độ biến thiên quan sát được và mức rủi ro được chấp nhận. Không có một tỷ lệ dự phòng chung áp dụng cho mọi hệ thống PAM.

## 8. Ví dụ đo một lần phục hồi đầu cuối

Một tổ chức đặt mục tiêu 10 phút cho luồng mở phiên quản trị mới đến nhóm máy chủ Tier 0 khi mất vùng phục vụ chính.

Điều kiện phục hồi đã được thống nhất trước diễn tập:

- Người dùng hợp lệ xác thực bằng cơ chế được phê duyệt.
- Policy cấp đúng quyền cho đúng tập đích.
- Một phép thử thiếu quyền bị từ chối.
- Phiên quản trị mở thành công; lệnh kiểm tra vô hại trả kết quả mong đợi.
- Bằng chứng phiên được lưu hoặc được đệm bền vững theo chính sách đã phê duyệt.
- Thử kết thúc phiên thành công.
- Đạt 20 phiên đồng thời trong khoảng quan sát 60 giây đã định.
- Không phát hiện hai bên cùng có thẩm quyền ghi trạng thái.

Nếu chính sách không chấp nhận đệm bằng chứng tại chỗ, phải xác nhận nơi lưu tập trung hoạt động. Không dùng khả năng đệm như một giả định tự phát.

### Dòng thời gian quan sát

| Mốc | Sự kiện | Thời gian từ t0 |
|---|---|---:|
| 09:00:00 | Luồng bắt đầu không đáp ứng tiêu chí; đây là t0 | 0 giây |
| 09:00:25 | Giám sát nhận biết và phát cảnh báo | 25 giây |
| 09:01:10 | Đội trực nhận việc và quyết định phục hồi | 70 giây |
| 09:02:10 | Hoàn tất cô lập quyền ghi của bên lỗi | 130 giây |
| 09:04:20 | Thành phần phục vụ tại vùng phục hồi sẵn sàng | 260 giây |
| 09:06:40 | Kiểm tra chức năng, policy, bằng chứng và kết thúc phiên đạt | 400 giây |
| 09:08:20 | Đạt tải yêu cầu và hoàn tất quan sát ổn định; đây là tR | 500 giây |

Kết quả:

```text
Thời gian phục hồi thực tế = 500 giây = 8 phút 20 giây
RTO mục tiêu               = 600 giây = 10 phút
Phần thời gian còn lại     = 100 giây

Kết luận:
  Đạt mục tiêu của kịch bản và phạm vi đã thử,
  với điều kiện toàn bộ tiêu chí chức năng và kiểm soát đều có bằng chứng.
```

Không lấy mốc 09:04:20 để tuyên bố RTO đạt 4 phút 20 giây: lúc đó mới có thành phần phục vụ sẵn sàng, chưa xác nhận năng lực đầu cuối.

Kết quả này cũng không chứng minh hệ thống có thể phục hồi trong 10 phút khi toàn bộ nền tảng định danh bị mất hoặc khi dữ liệu vault bị phá hoại. Đó là những kịch bản khác cần phép thử riêng.

## 9. Khôi phục nhanh vẫn phải giữ tính đúng đắn của quyền

### 9.1. Kiểm tra trạng thái quyền và credential sau phục hồi

Sau khi chuyển sang bản sao hoặc khôi phục backup, cần đánh giá các trạng thái có thể đã thay đổi:

- Credential đã rotation tại máy đích nhưng chưa được cập nhật vào bản phục hồi.
- Quyền JIT còn xuất hiện trong dữ liệu cũ dù đã hết hạn hoặc bị thu hồi.
- Một yêu cầu phê duyệt chưa hoàn tất bị hiểu nhầm thành đã được duyệt.
- Lease đã hết hạn trong thời gian gián đoạn.
- Lệnh kết thúc phiên chưa tới điểm thực thi.
- Job rotation hoặc thu hồi bị chạy lại do retry.
- Phiên tại proxy cũ vẫn tồn tại ngoài khả năng quan sát của control plane mới.

Các kiểm tra này phải có tiêu chí rõ. Nếu chưa xác nhận được trạng thái, nên giới hạn năng lực theo chính sách đã phê duyệt và ghi rõ dịch vụ chưa phục hồi hoàn toàn.

Không có cơ sở để mặc định mọi job đều có thể replay an toàn. Khả năng xử lý lặp phải được thiết kế theo từng thao tác và điểm thực thi.

### 9.2. TTL hỗ trợ giới hạn quyền, nhưng không thay thế thu hồi

Quyền hoặc credential có thời hạn có thể hạn chế thời gian tồn tại của một số quyền trong lúc control plane gián đoạn. Hiệu quả thực tế tùy thuộc điểm thực thi có kiểm tra hết hạn hay không.

Ví dụ, một chứng thư hết hạn có thể ngăn phiên đăng nhập mới nhưng không nhất thiết tự kết thúc phiên đã mở. Vì vậy, “credential chỉ sống 5 phút” chưa chứng minh mọi quyền đều biến mất sau 5 phút.

Bài kiểm tra phục hồi phải đánh giá hành vi thật của hệ đích và session proxy thay vì chỉ nhìn TTL trong cấu hình.

### 9.3. Khi sự cố có dấu hiệu xâm nhập

Sự cố mất nguồn và sự cố bị chiếm quyền có thể cần quy trình khác nhau. Nếu hệ thống PAM bị nghi xâm nhập, node dự phòng đồng bộ hoàn hảo vẫn có thể chứa policy hoặc dữ liệu đã bị thay đổi trái phép.

Phục hồi trong trường hợp này cần xác nhận độ tin cậy của môi trường, khóa, dữ liệu và quyền quản trị liên quan. Có thể phải thu hồi phiên, rotation credential bị ảnh hưởng hoặc khôi phục từ điểm dữ liệu đã được xác minh.

Nếu việc bảo đảm độ tin cậy làm vượt RTO, báo cáo phải ghi nhận trượt mục tiêu và nguyên nhân. Không được bỏ qua dấu hiệu xâm nhập để đánh dấu “đã phục hồi đúng hạn”.

## 10. Break-glass và chế độ suy giảm được đo thế nào?

Break-glass là đường truy cập khẩn cấp dành cho hoàn cảnh được định nghĩa trước. Nó có thể giúp đội ứng phó bắt đầu sửa hệ thống khi luồng PAM chuẩn chưa phục hồi.

Cần tách hai phép đo:

```text
T_khan_cap:
    từ gián đoạn đến khi người được phép sử dụng được
    đường khẩn cấp theo điều kiện riêng

T_chuan:
    từ gián đoạn đến khi luồng PAM chuẩn đạt đầy đủ tiêu chí

Có T_khan_cap ngắn không tự chứng minh T_chuan đạt RTO.
```

Ví dụ, đội hạ tầng có thể dùng đường khẩn cấp sau 3 phút, nhưng PAM chuẩn cần 18 phút mới phục hồi. Với mục tiêu chuẩn 10 phút, lần này vẫn chưa đạt, dù đường khẩn cấp đã giảm tác động nghiệp vụ.

### Điều kiện cần ghi cho đường khẩn cấp

| Nội dung | Ví dụ điều kiện |
|---|---|
| Người sử dụng | Danh sách trực đã được phê duyệt, xác minh danh tính bằng kênh độc lập |
| Phạm vi | Chỉ tập đích cần để khôi phục dịch vụ, quyền tối thiểu đủ thao tác |
| Kích hoạt | Có sự cố phù hợp, ghi nhận người kích hoạt và người chấp thuận theo chính sách |
| Thời hạn | Hạn sử dụng hoặc thời điểm rà soát bắt buộc |
| Bằng chứng | Phương thức ghi nhận vẫn khả dụng khi hệ thống chính hỏng |
| Kết thúc | Thu hồi quyền, kiểm tra phiên, rotation credential khi cần và đối soát hành động |

Không thể định nghĩa thành công là “bất kỳ ai cũng đăng nhập được”. Chế độ suy giảm phải có tiêu chí riêng, giới hạn rõ và thẩm quyền chấp nhận.

Một số tổ chức cho phép lưu bằng chứng bền vững tại vùng phục hồi rồi chuyển lên hệ thống tập trung sau. Nếu được phê duyệt, cần đo cả khả năng đệm, giới hạn dung lượng và thời gian đối soát. Nếu chưa có cơ chế này, không coi mất ghi bằng chứng là một ngoại lệ mặc nhiên.

## 11. Thiết kế diễn tập để kiểm chứng RTO

Phép thử cần tái hiện đường phục hồi thực tế trong phạm vi được phép. Môi trường lab có thể giúp tìm lỗi sớm; để dùng kết quả cho cam kết vận hành, phải đánh giá độ tương đồng về dữ liệu, tải, mạng, nhân sự và các phụ thuộc.

### 11.1. Xác định hợp đồng của phép thử

Trước khi bắt đầu, ghi rõ:

1. Kịch bản lỗi và ranh giới ảnh hưởng.
2. Luồng PAM, người dùng thử và hệ đích thử.
3. RTO, t0, tR và cách xác định từng mốc.
4. Điều kiện chức năng, quyền, dữ liệu, bằng chứng và tải.
5. Người chỉ huy, người phục hồi và người xác nhận kết quả.
6. Giới hạn tác động, điều kiện dừng và phương án đưa hệ thống về trạng thái đã biết.
7. Nguồn log, định danh phép thử và cách bảo vệ dữ liệu thu thập.

Tài khoản thử nên có phạm vi tối thiểu, dùng đích chuyên dụng và thực hiện thao tác vô hại. Không dùng credential thật trong bản ghi công khai, không tạo quyền quản trị thường trực chỉ để probe dễ chạy.

### 11.2. Ma trận kịch bản minh họa

| Kịch bản | Câu hỏi phép thử phải trả lời |
|---|---|
| Mất một node phục vụ | Phát hiện, chuyển tải và giữ khả năng thực thi policy mất bao lâu? |
| Mất một vùng | Dữ liệu, khóa, tuyến mạng và công suất vùng còn lại có đủ không? |
| Mất IdP hoặc MFA chính | Đường khôi phục hạ tầng định danh có vòng phụ thuộc không? |
| Đứt kết nối giữa các thành phần | Hệ thống phân biệt mất kết nối với mất node thế nào; có tránh hai bên cùng ghi không? |
| Không truy cập được nơi lưu bằng chứng | Luồng có bị chặn theo policy hay vào chế độ suy giảm đã duyệt? |
| Khôi phục dữ liệu cũ trong lab | Credential, policy, lease và trạng thái thu hồi được đối soát ra sao? |
| Thiếu một người có thẩm quyền mở khóa | Lịch trực và cơ chế thay thế có đáp ứng ngân sách không? |
| Tải tăng khi đang phục hồi | Tập luồng ưu tiên có đạt công suất tối thiểu không? |

Không thực hiện hành vi phá hoại dữ liệu hoặc làm gián đoạn sản xuất chỉ vì muốn có phép đo. Chọn cơ chế mô phỏng, cô lập hoặc diễn tập đã được chủ hệ thống cho phép.

### 11.3. Thực hiện theo runbook, ghi cả thao tác ngoài dự kiến

Runbook cần mô tả:

- Dấu hiệu nhận biết và phân loại sự cố.
- Điều kiện được chuyển vai trò hoặc chuyển vùng.
- Cách cô lập bên lỗi.
- Thứ tự phục hồi phụ thuộc.
- Luồng kiểm tra hợp lệ và kiểm tra từ chối.
- Điều kiện công bố phục hồi.
- Cách xử lý khi không đạt tiêu chí.
- Các việc hoàn nguyên và đối soát sau diễn tập.

Nếu người trực phải gọi một chuyên gia không nằm trong runbook hoặc tự tìm một khóa chưa được chuẩn bị, ghi lại cả thời gian lẫn nguyên nhân. Không loại những đoạn đó khỏi phép đo chỉ vì “lần sau sẽ biết”.

### 11.4. Hoàn nguyên là một giai đoạn riêng

Phục hồi sang vùng dự phòng và đưa hệ thống trở lại cấu hình vận hành mong muốn là hai việc khác nhau.

Sau khi luồng đã đạt tiêu chí tại vùng phục hồi, có thể kết thúc phép đo RTO theo hợp đồng đã đặt. Sau đó vẫn cần:

- Đối soát dữ liệu và bằng chứng còn tồn.
- Kiểm tra phiên, lease và quyền phát sinh trong chế độ suy giảm.
- Khôi phục mức dự phòng.
- Thu hồi hoặc rotation credential khẩn cấp theo quy trình.
- Lên kế hoạch chuyển lại nếu cần, với điều kiện kiểm tra riêng.

Một lần chuyển lại gây gián đoạn mới phải được ghi nhận theo quy tắc đo sự cố đã thống nhất; không giấu trong kết quả phục hồi trước đó.

## 12. Lưu bằng chứng để kết luận có thể kiểm tra lại

Báo cáo tốt phải cho người khác tái dựng được phép đo mà không cần xem secret hoặc nội dung nhạy cảm của phiên.

Một cấu trúc báo cáo minh họa:

```yaml
exerciseId: pam-rto-zone-loss-01
scope:
  capability: new-privileged-ssh-session
  targetGroup: dedicated-critical-test-targets
  scenario: serving-zone-unavailable
objectiveSeconds: 600
measurement:
  startEvent: capability-became-unavailable
  recoveredEvent: all-acceptance-criteria-completed
  elapsedSeconds: 500
  probeIntervalSeconds: 10
acceptance:
  authentication: PASS
  authorizationAllow: PASS
  authorizationDeny: PASS
  targetConnection: PASS
  sessionEvidence: PASS
  sessionTermination: PASS
  minimumCapacity: PASS
  stableObservation: PASS
  singleWriterAuthority: PASS
result: PASS
limitations:
  - does-not-cover-identity-provider-total-outage
  - does-not-cover-compromised-vault-recovery
```

Đây là mẫu mô tả học tập, không phải cấu hình để nạp vào một sản phẩm PAM cụ thể. Mốc thời gian chi tiết và các định danh log liên quan phải được lưu trong bằng chứng của lần chạy; ví dụ trên chỉ thể hiện các trường chính.

### Bằng chứng nên có

- Timestamp cùng nguồn chứng minh t0 và tR.
- Log phát hiện, nhận trách nhiệm và quyết định phục hồi.
- Bằng chứng cô lập hoặc bảo đảm quyền ghi.
- Kết quả kiểm tra xác thực, cấp quyền và từ chối.
- Kết quả mở và kết thúc phiên đến đích thử.
- Bằng chứng secret hoặc credential sử dụng được mà không tiết lộ giá trị.
- Kết quả tải và khoảng quan sát.
- Tình trạng dữ liệu và các ngoại lệ.
- Danh sách bước thực hiện khác runbook.
- Người xác nhận kết quả và phạm vi kết luận.

Áp dụng quyền truy cập phù hợp cho bằng chứng. Log có thể chứa thông tin hệ đích, danh tính quản trị hoặc metadata nhạy cảm dù không có mật khẩu.

### Không suy luận quá mức từ số lần thử ít

Một lần đạt mục tiêu là bằng chứng cho lần đó, chưa chứng minh hệ thống luôn đạt trong mọi điều kiện.

Nếu mới có ba lần diễn tập, hãy báo từng kết quả, phạm vi, điều kiện và độ biến thiên. Một con số p95 từ lượng mẫu quá ít dễ tạo cảm giác chắc chắn không có cơ sở.

Các lần thử trượt mục tiêu hoặc dừng do điều kiện kiểm soát không đạt vẫn thuộc lịch sử kiểm chứng. Chúng không được xóa khỏi báo cáo để làm đẹp kết quả.

## 13. Cách giảm thời gian phục hồi có kiểm soát

Cải thiện nên nhắm vào công đoạn đã được đo là nút thắt.

| Nút thắt quan sát | Hướng cải thiện | Điều phải kiểm chứng lại |
|---|---|---|
| Phát hiện muộn | Probe đầu cuối và điều chỉnh đường cảnh báo | Probe đo đúng luồng, cảnh báo tới đúng người |
| Chờ người ra quyết định | Làm rõ thẩm quyền, lịch trực và điều kiện kích hoạt | Người thay thế có thể thực hiện theo quy trình |
| Thiếu vật liệu mở khóa | Chuẩn bị khả năng truy cập khóa tại vùng phục hồi | Giữ phân tách nhiệm vụ và bằng chứng |
| Vùng dự phòng thiếu công suất | Dự trù tải hoặc bố trí công suất phù hợp | Đạt tải tối thiểu trong sự cố thật sự |
| DNS hoặc tuyến mạng chậm | Chuẩn bị cách chuyển hướng và kiểm tra phụ thuộc | Client và connector sử dụng đường mới đúng |
| Xác minh thủ công kéo dài | Tự động hóa kiểm tra chức năng và kiểm soát | Không bỏ phép thử từ chối, thu hồi và bằng chứng |
| Runbook thiếu bước | Bổ sung hướng dẫn từ các lần diễn tập | Người trực khác vẫn thực hiện được |
| Dữ liệu phục hồi không khớp đích | Làm rõ cơ chế nhất quán và đối soát | Credential, policy và trạng thái thu hồi đúng |

Tự động hóa có thể rút ngắn thời gian nhưng cũng làm lỗi lan nhanh hơn. Một quy trình tự chuyển vùng cần điều kiện kích hoạt rõ, bảo đảm quyền ghi và cơ chế dừng khi bằng chứng không đủ.

Đổi kiến trúc, thay nhà cung cấp định danh, thêm loại secret, đổi đường mạng hoặc thay cơ chế lưu bằng chứng đều có thể làm phép đo cũ không còn đại diện. Cần kiểm chứng lại những luồng bị ảnh hưởng.

## 14. Những sai lầm thường gặp

### “Vault đã xanh nên PAM đã phục hồi”

Health check chứng minh được điều mà nó thực sự kiểm tra. Nếu chỉ kiểm tra tiến trình trả lời HTTP, nó không chứng minh người quản trị tới được máy đích hoặc hệ thống thu hồi được quyền.

**Cách xử lý:** bổ sung kiểm tra đầu cuối và xác định rõ điều kiện kết thúc phép đo.

### “Chỉ tính từ lúc bắt đầu thao tác khôi phục”

Cách tính này bỏ mất thời gian người dùng bị gián đoạn trước khi đội trực hành động.

**Cách xử lý:** lưu t0 theo hợp đồng dịch vụ, giữ các mốc phát hiện và nhận việc để phân tích từng đoạn.

### “Có backup là bảo đảm đạt RTO”

Backup phải được tìm thấy, truy cập được, giải mã được, khôi phục được và dùng được với trạng thái hệ đích. Mỗi việc đều có thời gian và phụ thuộc.

**Cách xử lý:** thử toàn bộ quy trình phục hồi, gồm cả khóa, policy và kiểm tra credential.

### “Có break-glass thì có thể đánh dấu dịch vụ chuẩn đã phục hồi”

Đường khẩn cấp có phạm vi và rủi ro riêng.

**Cách xử lý:** báo riêng thời gian đến truy cập khẩn cấp, thời gian đến dịch vụ chuẩn và các công việc thu hồi sau đó.

### “Giảm kiểm soát để đạt RTO rồi bổ sung sau”

Nếu các kiểm soát là điều kiện phục hồi đã cam kết, bỏ chúng đi nghĩa là chưa đạt điều kiện đó.

**Cách xử lý:** chỉ dùng chế độ suy giảm đã được định nghĩa và phê duyệt; ghi rõ giới hạn cùng trạng thái phục hồi thực tế.

### “Một lần diễn tập tốt đủ cho mọi kịch bản”

Mất node không tương đương mất vùng, mất IdP hoặc xâm nhập vault.

**Cách xử lý:** duy trì ma trận kịch bản và giới hạn kết luận theo phạm vi đã kiểm chứng.

## 15. Bài tập tình huống

### Tình huống A — Đạt thời gian nhưng thiếu bằng chứng

PAM có RTO 10 phút cho luồng quản trị máy chủ trọng yếu. Sau sự cố, người dùng mở được phiên ở phút thứ 7. Đường ghi bằng chứng bắt buộc chỉ hoạt động ở phút thứ 13. Chính sách hiện tại không chấp nhận phiên không có bằng chứng hoặc phương án đệm thay thế.

**Câu hỏi:** Có đạt RTO của luồng đã định không?

**Gợi ý phân tích:** Không. Mốc phục hồi không thể là phút thứ 7 vì còn thiếu điều kiện bắt buộc. Nếu đến phút thứ 13 mới đạt toàn bộ tiêu chí và không còn vấn đề khác, thời gian phục hồi thực tế là 13 phút, vượt mục tiêu 10 phút. Cần lưu cả việc phiên đã được mở trước khi điều kiện bằng chứng đạt để xử lý theo quy trình.

### Tình huống B — Thành phần nhanh, luồng chậm

Vault dự phòng phục vụ sau 3 phút. Tuy nhiên, connector còn dùng tuyến mạng cũ đến phút thứ 8, còn máy đích chỉ chấp nhận credential mới sau đối soát ở phút thứ 11. Mục tiêu đầu cuối là 10 phút.

**Câu hỏi:** Nên báo kết quả nào?

**Gợi ý phân tích:** Có thể báo thời gian vault sẵn sàng là 3 phút, nhưng thời gian phục hồi luồng chưa thể dưới 11 phút. Nếu các tiêu chí còn lại chỉ hoàn tất muộn hơn, phải dùng mốc muộn hơn đó. Nút thắt cần xử lý nằm ở đường kết nối và nhất quán credential, không chỉ ở tốc độ khởi động vault.

### Tình huống C — Ngân sách nghiệp vụ không đủ

Dịch vụ nghiệp vụ cần trở lại trong 25 phút. Sau khi có quyền quản trị, đội trực cần 10 phút sửa chữa và 5 phút xác minh. Kế hoạch PAM đặt RTO là 20 phút.

**Câu hỏi:** Kế hoạch đã hỗ trợ mục tiêu nghiệp vụ chưa?

**Gợi ý phân tích:** Nếu các giai đoạn nối tiếp, tổng dự kiến là 35 phút nên chưa hỗ trợ mục tiêu 25 phút. Cần làm rõ phần nào có thể chạy song song và giảm thời gian trên đường đi găng. Với giả định nối tiếp hoàn toàn, phần thời gian còn lại cho phục hồi truy cập chỉ là 10 phút trước khi tính dự phòng.

### Tình huống D — Phiên còn chạy nhưng không thu hồi được

Trong lúc control plane gián đoạn, các phiên quản trị hiện hữu vẫn tiếp tục. Có dấu hiệu một phiên đang bị lạm dụng nhưng cơ chế kết thúc phiên không khả dụng.

**Câu hỏi:** Có thể báo “PAM không bị ảnh hưởng” không?

**Gợi ý phân tích:** Không. Tính liên tục của phiên không đại diện cho toàn bộ năng lực PAM. Phải ghi nhận gián đoạn của khả năng thu hồi, kích hoạt phương án ứng phó đã định và đo thời gian khôi phục thực thi thu hồi riêng.

## 16. Tự kiểm tra kiến thức

1. RTO của một luồng mở phiên khác thời gian khởi động lại vault ở điểm nào?
2. Vì sao cần ghi rõ t0 và tR trước khi diễn tập?
3. Khi nào phải đưa thời gian phê duyệt hoặc mở khóa vào ngân sách phục hồi?
4. Vì sao một bản sao dữ liệu mới không tự bảo đảm mọi credential dùng được tại máy đích?
5. Một phiên quản trị còn sống có chứng minh cơ chế thu hồi quyền vẫn hoạt động không?
6. Nếu hai công việc phục hồi chạy song song, cần tính thời gian thế nào?
7. Khi nào truy cập break-glass được tính là một năng lực phục hồi riêng?
8. Những bằng chứng nào giúp phân biệt “thành phần đã lên” với “luồng đã khôi phục”?
9. Vì sao kết quả diễn tập mất node không đủ để cam kết RTO khi vault bị xâm nhập?
10. Sau khi đạt RTO tại vùng dự phòng, còn những công việc đối soát nào cần hoàn tất?

Điểm cần nắm vững là cách phát biểu một mục tiêu có thể đo: **khôi phục năng lực nào, cho ai, đến tập đích nào, trong kịch bản nào, với những kiểm soát và tải tối thiểu nào**. Khi các điều kiện này rõ ràng, RTO trở thành cơ sở để thiết kế, diễn tập và cải thiện khả năng phục hồi truy cập đặc quyền.
