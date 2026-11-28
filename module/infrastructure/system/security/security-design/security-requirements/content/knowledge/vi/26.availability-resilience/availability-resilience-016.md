# Recovery point objective

## 1. RPO chuyển mức chịu mất dữ liệu thành yêu cầu gì?

Trong chương **Availability và resilience**, recovery point objective, viết tắt là **RPO**, là mục tiêu về khoảng dữ liệu có thể bị mất khi hệ thống phải phục hồi sau một kịch bản sự cố đã xác định. RPO thường biểu diễn bằng thời gian: dữ liệu sau mốc phục hồi có thể không còn, nhưng khoảng lùi so với mốc sự cố không được vượt mục tiêu đã cam kết.

Ví dụ, yêu cầu “RPO không quá 5 phút khi mất toàn bộ vùng triển khai chính” có nghĩa là thiết kế phục hồi phải bảo toàn dữ liệu trong phạm vi đã định nghĩa tới một mốc cách điểm cắt của sự cố không quá 5 phút. Nó không nói hệ thống sẽ hoạt động lại trong 5 phút.

Đối với đặc tả yêu cầu bảo mật, RPO giúp nối liền:

**Tác động nghiệp vụ do mất dữ liệu → kịch bản đe dọa → phạm vi dữ liệu → kiến trúc bảo vệ → phép kiểm chứng phục hồi.**

Một cấu hình backup không tự chứng minh RPO. Cần biết bản sao có nằm ngoài phạm vi sự cố không, có đọc được không, có đủ log và khóa giải mã không, và có khôi phục thành trạng thái nhất quán không.

Sau bài học, người học cần có khả năng:

- Đặt RPO theo loại dữ liệu và kịch bản sự cố thay vì dùng một con số chung thiếu phạm vi.
- Phân biệt RPO với thời gian khôi phục, chu kỳ backup, thời hạn lưu và độ trễ replication.
- Chuyển mục tiêu RPO thành yêu cầu đo được về dữ liệu, kiến trúc, logging và kiểm thử.
- Đánh giá bằng chứng mất dữ liệu thực tế, kể cả khi bản sao bị hỏng hoặc chứa dữ liệu đã bị xâm phạm.

Các mốc thời gian, ngưỡng và tên hệ thống trong bài là **ví dụ thiết kế**, không phải mức mặc định cho mọi tổ chức.

## 2. Phân biệt RPO với các đại lượng gần nhau

| Đại lượng | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| RPO | Có thể phải lùi dữ liệu bao xa so với mốc sự cố? | Không quá 5 phút dữ liệu của luồng tạo đơn |
| RTO — recovery time objective | Trong bao lâu phải khôi phục mức phục vụ đã định nghĩa? | Phục vụ lại luồng tạo đơn trong 60 phút |
| Chu kỳ backup | Bao lâu tạo một bản sao hoặc điểm chụp? | Snapshot mỗi 30 phút |
| Backup retention | Giữ các bản sao hoặc log trong bao lâu? | Giữ các điểm cần thiết để khôi phục trong 14 ngày |
| Replication lag | Bản sao đang chậm hơn nguồn bao nhiêu theo cách đo đã chọn? | Replica chậm 20 giây trong điều kiện hiện tại |
| Availability target | Dịch vụ được kỳ vọng phục vụ thành công ở mức nào? | Mục tiêu tỷ lệ phục vụ trong một kỳ đo |

Một hệ thống có thể đạt RTO nhưng trượt RPO: phục vụ lại rất nhanh từ bản sao cũ. Ngược lại, có thể phục hồi gần như đầy đủ dữ liệu nhưng mất nhiều giờ để dựng hạ tầng và kiểm tra, nên đạt RPO mà trượt RTO.

Retention dài giúp có nhiều lựa chọn khi sự cố được phát hiện muộn, nhưng không tự làm dữ liệu gần sự cố hơn. Replication lag thấp cũng không chứng minh có điểm phục hồi sạch nếu lỗi xóa nhầm hoặc sửa dữ liệu độc hại đã được đồng bộ sang replica.

### 2.1. Không suy RPO trực tiếp từ tần suất backup

Giả sử snapshot ghi nhận trạng thái nhất quán ở 10:00, hoàn thành sao chép lúc 10:12 và kiểm tra xong lúc 10:15. Điểm dữ liệu của snapshot vẫn là 10:00, không phải 10:15.

Nếu sự cố xảy ra lúc 10:20 và chỉ bản snapshot đó dùng được, khoảng lùi dữ liệu là 20 phút. Việc tác vụ backup vừa báo thành công 5 phút trước không làm RPO đạt 5 phút.

Nếu có thêm transaction log liên tục, đủ điều kiện replay tới 10:18, điểm phục hồi có thể mới hơn snapshot. Khi đó phải kiểm tra toàn bộ chuỗi snapshot, log, metadata và khả năng giải mã, không chỉ nhìn tuổi của snapshot.

## 3. Định nghĩa cách đo trước khi đặt ngưỡng

### 3.1. Các mốc cần thống nhất

Đặt:

- `t_f`: mốc cắt sự cố trong kịch bản đang kiểm chứng, được quy định rõ trong kế hoạch thử.
- `t_p`: mốc dữ liệu nhất quán mới nhất có thể phục hồi đầy đủ bằng các thành phần còn sử dụng được.
- `D_loss = t_f - t_p`: khoảng lùi dữ liệu được quan sát, với điều kiện hai mốc cùng cơ sở thời gian và `t_p <= t_f`.

Tiêu chí về thời gian:

```text
D_loss <= RPO_target
```

Trong sự cố thực tế, `t_f` có thể là thời điểm mất nguồn ghi hoặc điểm cắt ghi đã được kiểm soát. Nếu failover có khoảng tiếp tục nhận ghi, phải xác định những ghi nào đã được xác nhận và nằm trong phạm vi trách nhiệm phục hồi. Không tùy ý chọn mốc sớm hơn để bỏ qua các ghi đã được chấp nhận về sau.

Thời điểm phát hiện, thời điểm bắt đầu restore và thời điểm phục vụ lại là các mốc khác. Không dùng thời gian hoàn tất restore thay cho `t_f` khi tính khoảng mất dữ liệu.

### 3.2. Điểm phục hồi phải có tính đầy đủ

`t_p` không đơn giản là timestamp lớn nhất tìm thấy trong một bảng. Nó phải biểu diễn một mốc có thể chứng minh dữ liệu thuộc phạm vi đã được bảo toàn đầy đủ tới đó.

Ví dụ, còn một đơn hàng có timestamp 10:29 không chứng minh toàn bộ đơn hàng tới 10:29 đều tồn tại. Nếu một phân vùng bị thiếu dữ liệu từ 10:10, mốc toàn bộ hệ thống không thể lấy theo bản ghi mới nhất ở phân vùng khác.

Trong khoảng không có ghi, thời điểm của bản ghi cuối cũng không tự chứng minh có mất dữ liệu. Cần phân biệt:

- Khoảng thời gian chưa có bằng chứng bảo toàn đầy đủ.
- Số giao dịch hoặc bản ghi thực sự bị mất.
- Tính nhất quán của trạng thái sau phục hồi.

Có thể dùng sequence, commit position, checkpoint hoặc watermark phù hợp với công nghệ để chứng minh độ bao phủ. Với nhiều nguồn dữ liệu, cần một quan hệ nhất quán giữa các mốc; không ghép tùy ý các timestamp trên các máy có đồng hồ lệch.

### 3.3. Phân biệt mục tiêu và kết quả

RPO là mục tiêu đã chấp thuận. `D_loss` trong một lần diễn tập hoặc sự cố là kết quả quan sát được. Một lần đạt 2 phút không tự chứng minh mọi kịch bản đều đạt 2 phút.

Báo cáo nên ghi đồng thời:

```text
scenario_id
data_scope
RPO_target
failure_cutoff
recovered_consistency_point
observed_loss_window
acknowledged_operations_missing
consistency_check_result
evidence_reference
```

Nếu không xác định được điểm phục hồi hoặc bằng chứng không đầy đủ, kết quả cần là “chưa chứng minh được”, không tự ghi đạt.

## 4. Đặt RPO từ rủi ro và tác động nghiệp vụ

### 4.1. Bắt đầu bằng câu hỏi mất gì, hậu quả gì

Đối với từng luồng, hãy xác định:

1. Dữ liệu nào có thể mất: đơn hàng, thanh toán, tệp tải lên, cấu hình quyền hay sự kiện kiểm toán.
2. Điểm nào được xem là đã chấp nhận dữ liệu: commit bền vững, xác nhận message hay response thành công.
3. Mất dữ liệu có phát hiện và đối soát được không.
4. Có nguồn tin cậy để tạo lại không, thời gian và công sức bao nhiêu.
5. Những ràng buộc nhất quán nào phải giữ: đơn hàng và dòng hàng, số dư và bút toán, metadata và tệp.
6. Ai chấp thuận phần rủi ro còn lại và điều kiện của cam kết.

Một phút dữ liệu không phải lúc nào cũng có cùng giá trị. Luồng ghi nhận giao dịch có thể không chấp nhận mất bất kỳ giao dịch đã xác nhận nào; chỉ mục tìm kiếm có thể dựng lại từ nguồn chính, miễn thời gian dựng lại vẫn đáp ứng mục tiêu phục vụ.

### 4.2. RPO phải gắn với kịch bản

| Kịch bản | Vì sao cùng một bản sao có thể chưa đủ? | Nội dung cần đưa vào yêu cầu |
|---|---|---|
| Mất một process hoặc máy chủ | Ghi trong bộ nhớ hoặc đĩa cục bộ chưa chắc còn | Điểm xác nhận bền vững, cơ chế chuyển quyền ghi |
| Mất một vùng triển khai | Bản sao trong cùng vùng có thể cùng biến mất | Bản sao và thành phần phục hồi ngoài vùng bị mất |
| Xóa nhầm hoặc cập nhật sai | Replica có thể đã nhận đúng thao tác sai đó | Point-in-time recovery, lịch sử và khả năng đối soát |
| Mã độc hoặc tài khoản quản trị bị chiếm | Bản sao trực tuyến và quyền xóa backup có thể bị kiểm soát | Phân tách quyền, bản sao được bảo vệ, điểm sạch và quy trình xác minh |
| Khóa giải mã không sử dụng được | Có đủ byte backup nhưng không đọc được dữ liệu | Vòng đời khóa, phiên bản khóa và khả năng phục hồi phụ thuộc |
| Nhiều thành phần dữ liệu hỏng lệch nhau | Mỗi kho có điểm phục hồi riêng | Mốc nhất quán chung và quy tắc đối soát xuyên kho |

Ví dụ, “RPO 5 phút khi mất vùng chính” không bao hàm mặc nhiên “RPO 5 phút khi cả tài khoản backup và dữ liệu lịch sử đều bị chiếm quyền trong nhiều ngày”.

Nếu một kịch bản chưa có kiến trúc hoặc bằng chứng đủ để cam kết mục tiêu, phải ghi nhận khoảng thiếu đó để xử lý hoặc chấp thuận rủi ro. Không che bằng một con số RPO chung cho toàn bộ hệ thống.

### 4.3. Mẫu yêu cầu có thể triển khai và kiểm thử

> Đối với **tập dữ liệu D** của **luồng X**, khi xảy ra **kịch bản S** trong **phạm vi sự cố F**, hệ thống phải phục hồi tới **mốc nhất quán P** sao cho khoảng lùi dữ liệu không vượt **RPO T**, tính theo **quy tắc M**. Những ghi đã xác nhận, điều kiện phụ thuộc, phần dữ liệu được phép dựng lại và bằng chứng kiểm thử phải được định nghĩa rõ.

Một con số nhỏ hơn thường đòi hỏi đồng bộ nhiều hơn, truyền log nhanh hơn, bảo vệ trạng thái nhiều hơn hoặc vận hành phức tạp hơn. Lựa chọn cần dựa trên tác động mất dữ liệu và bằng chứng, không mặc định mọi kho dữ liệu đều cần cùng mức.

## 5. RPO bằng 0 có ý nghĩa gì?

Trong phạm vi đã cam kết, **RPO bằng 0** cần được diễn đạt thành: không mất các thao tác đã được hệ thống xác nhận theo hợp đồng khi xảy ra kịch bản đang xét. Câu “có replica đồng bộ” chưa đủ làm tiêu chí chấp nhận.

Cần xác định:

- Điều kiện nào mới trả thành công cho caller.
- Dữ liệu đã bền vững ở bao nhiêu nơi và những nơi đó thuộc miền sự cố nào.
- Khi mất liên lạc, phía nào còn quyền ghi.
- Làm sao ngăn hai phía cùng nhận ghi và tạo lịch sử xung đột.
- Những trạng thái nào chưa được xác nhận và cần đối soát khi caller không nhận response.
- Phụ thuộc nào nằm trong cam kết, gồm log, metadata, khóa và các thao tác liên kho.

### 5.1. Ví dụ về xác nhận ghi và miền sự cố

Nếu trả thành công ngay sau ghi tại vùng A, rồi mới sao chép bất đồng bộ sang B, mất A đúng lúc chưa sao chép có thể làm mất ghi đã xác nhận. Không thể kết luận RPO bằng 0 cho kịch bản mất A chỉ vì bình thường độ trễ sao chép rất thấp.

Một thiết kế chỉ xác nhận sau khi đã ghi bền vững tới các thành phần cần thiết ngoài miền mất A có thể hỗ trợ mục tiêu không mất ghi trong kịch bản đó. Tuy nhiên, vẫn phải kiểm chứng chuyển quyền ghi, tính nhất quán và hành vi khi phân vùng mạng.

Chấp nhận ngừng nhận ghi khi không bảo đảm điều kiện bền vững có thể là một phần của thiết kế. Không hứa vừa nhận ghi ở mọi phía khi mất kết nối, vừa giữ mọi cam kết nhất quán mà không phân tích cơ chế giải quyết.

### 5.2. RPO bằng 0 không có nghĩa không cần backup

Replication có thể đồng bộ cả lỗi xóa, cập nhật sai hoặc hành vi độc hại. Một bản sao mới nhất chưa chắc là bản sao đúng.

Đối với sự cố mất dữ liệu vật lý, bản sao đồng bộ có thể bảo toàn dữ liệu đã xác nhận. Đối với sự cố toàn vẹn, có thể cần lùi về điểm sạch, rồi khôi phục hoặc tái áp dụng các giao dịch hợp lệ sau đó từ nguồn tin cậy.

Nếu chỉ có bản sao sạch cũ và không có cách tái tạo các giao dịch hợp lệ đã xác nhận về sau, không thể tuyên bố không mất dữ liệu. Cam kết RPO bằng 0 cho kịch bản này cần bằng chứng riêng, không được suy từ thiết kế replication.

## 6. Từ RPO tới kiến trúc bảo vệ dữ liệu

### 6.1. Backup định kỳ, log và khôi phục theo thời điểm

Một chuỗi phục hồi thường gồm:

```text
Bản nền nhất quán
  + Các đoạn log liên tục cần thiết
  + Metadata về thứ tự và điểm kết thúc
  + Khóa và cấu hình đọc dữ liệu
  -> Trạng thái có thể phục hồi tại một mốc xác định
```

Với point-in-time recovery, bản nền có thể tương đối cũ nhưng log cho phép tiến tới gần mốc sự cố. Ngược lại, mất một đoạn log bắt buộc có thể làm các đoạn mới hơn không còn đủ để khôi phục liên tục.

Yêu cầu cần nêu:

- Những thành phần nào bắt buộc trong mỗi chuỗi phục hồi.
- Khi nào một đoạn log được xem là bền vững ngoài miền sự cố.
- Cách phát hiện thiếu đoạn, sai thứ tự, dữ liệu hỏng hoặc khóa không phù hợp.
- Chính sách giữ bản nền và log để không xóa mất phần còn cần dùng.
- Thời gian truyền và tồn đọng tối đa, kể cả khi tải tăng hoặc kết nối gián đoạn.
- Hành vi cảnh báo và ứng phó khi không còn đáp ứng khoảng bảo vệ yêu cầu.

Không chỉ ghi “upload log mỗi phút”. Nếu log nằm chờ truyền 20 phút trong vùng chính, mất vùng vẫn có thể làm mất khoảng đó.

### 6.2. Replication và bản sao phục hồi

Replication phù hợp để duy trì một bản sao cập nhật, nhưng cần biết bản sao có thể được dùng thế nào:

- Có thể chuyển quyền ghi an toàn hay chỉ đọc được?
- Độ trễ đo ở lúc nhận log, ghi bền vững hay áp dụng hoàn tất?
- Log chưa áp dụng có còn đủ và có thể replay không?
- Replica có cùng tài khoản quản trị, vùng, khóa và quyền xóa với nguồn không?
- Điều gì xảy ra nếu lịch sử đã chứa thao tác sai?

Một bản sao nhận đủ log nhưng chưa áp dụng có thể vẫn đáp ứng RPO nếu log bền vững và replay được, nhưng làm tăng thời gian phục hồi. Chỉ số apply lag và độ bao phủ dữ liệu phục hồi vì vậy có quan hệ với nhau nhưng không đồng nhất.

### 6.3. Các phụ thuộc phải nằm trong kế hoạch phục hồi

| Thành phần | Thiếu thành phần này có thể gây gì? | Yêu cầu cần có |
|---|---|---|
| Khóa giải mã và phiên bản khóa | Không đọc được bản sao cũ | Giữ khả năng sử dụng khóa cần thiết, phân quyền và diễn tập phục hồi |
| Catalog hoặc manifest | Không biết chuỗi nào đầy đủ hoặc thuộc phiên bản nào | Metadata được bảo vệ và có cách phục hồi |
| Schema và công cụ restore tương thích | Không replay hoặc đọc đúng dữ liệu | Quản lý phiên bản, kiểm tra tương thích |
| Danh tính dịch vụ và cấu hình mạng | Không truy cập được kho phục hồi | Quy trình cấp quyền phục hồi có kiểm soát |
| Object và metadata liên quan | Bản ghi tồn tại nhưng nội dung bị thiếu | Điểm nhất quán hoặc cơ chế đối soát xuyên kho |
| Journal đối soát giao dịch | Không xác định được ghi đã xác nhận nhưng bị mất | Nguồn đối chiếu phù hợp, nằm ngoài miền lỗi đang thử |

Khôi phục quyền truy cập không đồng nghĩa với lưu khóa hoặc mật khẩu dạng rõ cạnh mọi bản backup. Thiết kế cần bảo đảm vừa có thể phục hồi vừa giới hạn người có thể đọc, xóa hoặc thay đổi dữ liệu phục hồi.

## 7. Tính nhất quán khi có nhiều kho dữ liệu

### 7.1. Chọn một ranh giới nghiệp vụ

Giả sử một đơn hàng gồm bản ghi trong database, ảnh hóa đơn trong object storage và sự kiện trong queue. Nếu database phục hồi tới 10:27 nhưng object storage chỉ tới 10:10, đơn hàng mới có thể trỏ tới tệp không tồn tại.

Không thể báo RPO cho toàn bộ nghiệp vụ bằng timestamp mới nhất của database mà bỏ qua thành phần bắt buộc còn thiếu.

Các lựa chọn có thể gồm:

- Checkpoint phối hợp nếu công nghệ và nghiệp vụ hỗ trợ.
- Ranh giới giao dịch và journal đủ để tái tạo các thành phần.
- Cơ chế outbox, replay và idempotency được kiểm chứng.
- Quy tắc đối soát và cách xử lý bản ghi thiếu phụ thuộc trước khi mở phục vụ.

Lựa chọn nào cũng cần tiêu chí kết quả: dữ liệu nào phải tồn tại cùng nhau, bản ghi nào được phép chờ hoàn thiện, và trạng thái nào không được công bố cho người dùng.

### 7.2. Dữ liệu có thể dựng lại và dữ liệu nguồn

Cache và chỉ mục tìm kiếm thường có thể dựng lại từ nguồn chính nếu nguồn còn đủ và thao tác dựng lại đáp ứng mục tiêu phục vụ. Khi đó cần ghi rõ chúng là dữ liệu dẫn xuất, không đưa việc thiếu cache thành mất giao dịch gốc.

Ngược lại, một “cache” chứa giá trị duy nhất chưa được ghi bền vững thực chất đang giữ dữ liệu nguồn đối với luồng đó. Tên công nghệ không thay thế được phân tích vòng đời dữ liệu.

Với queue, cần xác định ý nghĩa của việc đã xác nhận message, thời điểm tạo tác dụng phụ và khả năng xử lý lại. Khôi phục database về trước nhưng giữ vị trí consumer ở sau có thể bỏ qua công việc; khôi phục consumer về trước có thể phát sinh xử lý trùng.

### 7.3. Các bất biến sau phục hồi

Ví dụ các kiểm tra cần đặc tả:

```text
Mỗi dòng đơn hàng phải thuộc một đơn hàng hợp lệ.
Không có hai kết quả nghiệp vụ cho cùng một khóa idempotency còn hiệu lực.
Mỗi tham chiếu tệp bắt buộc phải trỏ tới nội dung khôi phục được.
Các sự kiện đã xác nhận phải có kết quả hoặc trạng thái chờ có thể đối soát.
Không công bố số dư từ một tập bút toán bị thiếu.
```

Các bất biến phải phù hợp nghiệp vụ cụ thể. Một hệ thống “mở được database” nhưng vi phạm các ràng buộc này chưa đủ điều kiện được xem là phục hồi thành công.

## 8. RPO khi sự cố liên quan tới toàn vẹn và quyền truy cập

### 8.1. Điểm mới nhất khác điểm sạch mới nhất

Giả sử lúc 14:00 mới phát hiện dữ liệu bị sửa sai từ 09:00. Bản sao ở 13:59 có thể rất mới nhưng đã chứa sai lệch. Điểm sạch có thể phải lùi về trước 09:00.

Nếu chỉ restore điểm sạch, các thay đổi hợp lệ sau điểm đó cũng có thể mất. Muốn giảm khoảng mất dữ liệu phải có nguồn tin cậy để xác định và tái áp dụng phần hợp lệ. Không replay nguyên mọi log nếu log đó cũng chứa thao tác độc hại.

Đặc tả cho kịch bản này cần nêu:

- Giả định về thời gian phát hiện và thời gian giữ lịch sử.
- Cách xác định điểm sạch và mức độ tin cậy của kết luận.
- Nguồn dữ liệu dùng để phân biệt giao dịch hợp lệ với thay đổi sai.
- Tiêu chí mở phục vụ khi còn phần dữ liệu cần đối soát.
- RPO mục tiêu, giới hạn chưa chứng minh và người chấp thuận rủi ro.

Thời gian phát hiện không tự được trừ khỏi khoảng mất dữ liệu để làm báo cáo đẹp hơn. Nếu chưa thể bảo toàn các ghi hợp lệ tới gần sự cố, phải ghi nhận đúng phần chưa đáp ứng.

### 8.2. Không khôi phục mù quáng trạng thái bảo mật cũ

Restore có thể làm xuất hiện lại tài khoản đã bị khóa, quyền đã bị thu hồi hoặc token lẽ ra không còn hiệu lực. Vì thế, phục hồi dữ liệu nghiệp vụ phải đi cùng quy tắc khôi phục trạng thái bảo mật.

Có thể cần đối soát với nguồn tin cậy về thu hồi quyền, cấp lại credential cho môi trường phục hồi và xác minh cấu hình truy cập trước khi mở dịch vụ. Nếu nhật ký bảo mật dùng để đối soát cùng bị ảnh hưởng, không được mặc nhiên xem nó là nguồn độc lập.

Thành công của RPO không cho phép bỏ qua phân quyền, logging và kiểm tra toàn vẹn. Môi trường restore phải kiểm soát người truy cập, tránh gửi thông báo hoặc gọi tích hợp thật trong lúc diễn tập, và quản lý vòng đời bản sao dữ liệu tạo ra.

## 9. Ví dụ đặc tả: mất vùng chính của dịch vụ đơn hàng

### 9.1. Bối cảnh và phạm vi

Dịch vụ đơn hàng lưu đơn, dòng hàng, trạng thái nghiệp vụ, khóa idempotency và outbox trong một phạm vi dữ liệu giao dịch được thiết kế để khôi phục nhất quán. Chỉ mục tìm kiếm là dữ liệu dẫn xuất, có thể dựng lại.

Rủi ro `R-RPO-01` là mất toàn bộ vùng A sau khi hệ thống đã xác nhận tạo đơn cho khách hàng. Vùng B và quyền sử dụng các thành phần phục hồi tại B vẫn hoạt động, nằm ngoài phạm vi mất vùng A trong kịch bản này.

Mục tiêu minh họa là **RPO không quá 5 phút** và **RTO không quá 60 phút** cho mức phục vụ đã định nghĩa. Kịch bản này không tự bao gồm việc cả hai vùng cùng bị chiếm quyền hoặc lịch sử bị sửa sai từ nhiều ngày trước.

### 9.2. Tập yêu cầu có thể kiểm chứng

| ID | Yêu cầu |
|---|---|
| SEC-RPO-01 | Phạm vi RPO gồm toàn bộ dữ liệu giao dịch cần để đọc và xử lý đơn đã xác nhận, bao gồm ràng buộc liên quan, idempotency và outbox. Dữ liệu dẫn xuất phải được liệt kê riêng. |
| SEC-RPO-02 | Khi mất vùng A theo kịch bản đã định nghĩa, hệ thống phải phục hồi ở B tới mốc nhất quán có khoảng lùi không quá 300 giây so với mốc cắt sự cố. |
| SEC-RPO-03 | Mốc phục hồi phải được chứng minh bằng checkpoint hoặc commit position phù hợp và kiểm tra độ đầy đủ, không lấy timestamp bản ghi mới nhất làm bằng chứng duy nhất. |
| SEC-RPO-04 | Bản nền, chuỗi log, metadata và khả năng dùng khóa bắt buộc để đạt mục tiêu phải còn sử dụng được ngoài vùng A. Một thành phần hỏng hoặc thiếu phải được phát hiện và phản ánh vào điểm phục hồi khả dụng. |
| SEC-RPO-05 | Theo dõi độ bao phủ phục hồi ngoài vùng A ít nhất mỗi 60 giây. Phát cảnh báo khi khoảng chưa được bảo vệ vượt 180 giây, khi thiếu đoạn log hoặc khi không xác định được độ bao phủ. |
| SEC-RPO-06 | Duy trì chuỗi thành phần cần để phục hồi theo thời điểm trong ít nhất 72 giờ của ví dụ này; việc xóa bản nền hoặc log không được làm đứt các chuỗi còn nằm trong phạm vi giữ lại. |
| SEC-RPO-07 | Chuyển quyền ghi phải ngăn vùng A cũ tiếp tục nhận ghi sau khi B được chọn làm nguồn ghi. Không mở phục vụ ghi nếu chưa bảo đảm quyền sở hữu và các điều kiện nhất quán. |
| SEC-RPO-08 | Trước khi mở phục vụ, kiểm tra các bất biến dữ liệu đã định nghĩa, khả năng dùng khóa, quyền truy cập và cơ chế chống xử lý trùng. |
| SEC-RPO-09 | Diễn tập phải đối chiếu các thao tác đã xác nhận trước mốc sự cố với trạng thái phục hồi bằng bằng chứng nằm ngoài miền mất A, và báo cả khoảng lùi lẫn số thao tác thiếu. |
| SEC-RPO-10 | Thay đổi schema, nơi lưu bản sao, khóa, retention, topology hoặc cơ chế xác nhận ghi phải được đánh giá tác động tới RPO và kiểm chứng lại các phần chịu ảnh hưởng. |

Ngưỡng cảnh báo 180 giây tạo khoảng đệm trước mục tiêu 300 giây trong ví dụ, nhưng không tự bảo đảm đội vận hành sửa kịp. Cần quy trình ứng phó, đo thời gian phát hiện và đánh giá khả năng giữ cam kết trong các điều kiện tải đã chọn.

Dừng nhận ghi mới có thể hạn chế phát sinh thêm rủi ro, nhưng không tự bảo vệ phần dữ liệu đã xác nhận mà chưa ra ngoài vùng A. Khi độ bao phủ đã trượt mục tiêu, phải ghi nhận đúng trạng thái thay vì coi cảnh báo hoặc việc dừng ghi là bằng chứng đạt RPO.

Retention 72 giờ cũng chỉ áp dụng cho ví dụ. Muốn phục hồi trước một sai lệch phát hiện sau nhiều ngày phải có phân tích và mục tiêu riêng; không suy ra khả năng đó từ bài kiểm thử mất vùng.

### 9.3. Ví dụ kết quả phục hồi

```text
10:00:00  Mốc nhất quán của bản nền
10:27:00  Mốc cuối có chuỗi log đầy đủ, sử dụng được ở vùng B
10:30:00  Mốc cắt sự cố mất vùng A
11:05:00  Phục vụ lại ở vùng B sau khi kiểm tra

Khoảng lùi dữ liệu: 10:30 - 10:27 = 3 phút
Thời gian phục hồi: 11:05 - 10:30 = 35 phút
```

Nếu các mốc và kiểm tra đầy đủ, kết quả đạt cả RPO 5 phút và RTO 60 phút của ví dụ. Khoảng 3 phút không có nghĩa chắc chắn mất mọi giao dịch trong khoảng đó hoặc mất đúng một số lượng cố định; phải đối chiếu các thao tác thực tế.

Nếu thiếu một đoạn log khiến chỉ phục hồi được tới 10:20, khoảng lùi thành 10 phút và trượt RPO, dù dịch vụ vẫn mở lại lúc 11:05.

## 10. Tiêu chí kiểm thử và bằng chứng

### 10.1. Tạo nguồn đối chiếu đáng tin

Bài diễn tập cần một tập thao tác có định danh và bằng chứng xác nhận được lưu ngoài miền lỗi đang thử. Có thể dùng công cụ phát tải kiểm soát được, ghi nhận operation ID, kết quả xác nhận và mốc hoặc thứ tự commit khi công nghệ hỗ trợ.

Sau restore, đối chiếu:

- Những thao tác nào đã được xác nhận trước mốc cắt sự cố.
- Tập dữ liệu tới mốc phục hồi đã đầy đủ và nhất quán chưa.
- Những thao tác nào thiếu, trùng hoặc ở trạng thái chưa xác định.
- Thiếu dữ liệu có nằm trong khoảng được chấp nhận hay xảy ra từ trước mốc phục hồi đã công bố.
- Có tác dụng phụ bên ngoài cần đối soát không.

Không chỉ đối chiếu với một bản log cũng bị mất cùng vùng A. Đồng thời, không tạo kho đối chiếu chứa dữ liệu nhạy cảm dư thừa; chỉ thu thập thông tin cần thiết và bảo vệ nó.

### 10.2. Ma trận kiểm chứng minh họa

| Ca kiểm thử | Thiết lập và kích thích | Kết quả cần quan sát |
|---|---|---|
| T01 — Mất vùng | Phát tải có ghi nhận xác nhận, cắt vùng A tại mốc đã kiểm soát, restore từ B | Khoảng lùi không quá 300 giây; dữ liệu tới mốc phục hồi đầy đủ; bất biến đạt |
| T02 — Sát biên backup | Gây sự cố ngay trước hoặc trong lần tạo bản nền tiếp theo | Không suy RPO từ lịch backup; log và bản nền còn lại vẫn đáp ứng hoặc báo trượt đúng |
| T03 — Tồn đọng truyền log | Làm tăng tải hoặc gián đoạn đường truyền sang B | Phát hiện độ bao phủ suy giảm và cảnh báo theo ngưỡng; không báo an toàn từ chỉ số ở A |
| T04 — Thiếu đoạn log | Làm một đoạn bắt buộc không sử dụng được trong môi trường thử | Phát hiện chuỗi đứt; không công bố mốc sau đoạn thiếu là phục hồi đầy đủ |
| T05 — Khóa và phiên bản | Restore bản sao còn dùng phiên bản khóa cũ đang trong hạn sử dụng | Đọc được theo quyền được cấp; thiếu khóa bị báo lỗi và không đánh dấu thành công |
| T06 — Dữ liệu thiếu có timestamp mới | Cố ý bỏ một phần dữ liệu cũ nhưng giữ bản ghi mới | Kiểm tra độ đầy đủ thất bại; không dùng timestamp lớn nhất để kết luận đạt |
| T07 — Khoảng không có ghi | Dừng phát ghi một thời gian trước sự cố | Phân biệt thời gian không có bằng chứng với số thao tác thực mất; không suy mất dữ liệu chỉ từ bản ghi cuối cũ |
| T08 — Nhất quán nghiệp vụ | Kiểm tra đơn, dòng hàng, idempotency và outbox sau restore | Không có tham chiếu bắt buộc bị đứt hoặc kết quả trùng trái hợp đồng |
| T09 — Chuyển quyền ghi | Cho vùng A cũ xuất hiện lại sau khi B nhận quyền ghi | A không nhận ghi trái phép; không hình thành hai nguồn ghi độc lập |
| T10 — Hỏng toàn vẹn | Mô phỏng sửa sai được phát hiện muộn trong môi trường thử | Chọn điểm sạch, đối soát phần hợp lệ và báo kết quả theo kịch bản riêng |
| T11 — Retention | Kiểm thử vòng đời bản nền và log tới ranh giới giữ lại | Không xóa thành phần còn cần cho các điểm phục hồi đã cam kết |
| T12 — Thay đổi hệ thống | Đổi schema hoặc cơ chế mã hóa rồi diễn tập restore | Công cụ, dữ liệu và khóa tương thích; bằng chứng được cập nhật |

Với T10, không lấy kết quả của kịch bản toàn vẹn để đánh đồng với cam kết mất vùng. Nếu chưa đủ bằng chứng để đặt RPO tương ứng, cần báo rõ khoảng thiếu và xử lý yêu cầu đó riêng.

Restore diễn tập phải đọc dữ liệu từ chính đường lưu trữ và quyền dự kiến dùng khi có sự cố. Một bản copy thủ công đặc biệt không có trong kế hoạch không chứng minh khả năng phục hồi thực tế.

## 11. Liên kết rủi ro, kiến trúc và bằng chứng

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng kiểm chứng |
|---|---|---|---|
| Mất ghi đã xác nhận khi mất vùng A | SEC-RPO-01, 02, 04 | Bản nền và log ngoài miền sự cố, hợp đồng xác nhận rõ | T01, T02 và tập thao tác thiếu sau restore |
| Báo sai điểm phục hồi do chỉ nhìn dữ liệu mới nhất | SEC-RPO-03, 09 | Checkpoint hoặc commit position, đối chiếu độ đầy đủ | T06, T07 và báo cáo đối chiếu |
| Có backup nhưng thiếu khóa hoặc chuỗi log | SEC-RPO-04, 06 | Quản lý vòng đời phụ thuộc và kiểm tra chuỗi | T04, T05, T11 |
| Hai vùng cùng nhận ghi sau failover | SEC-RPO-07 | Cơ chế quyền sở hữu và ngăn nguồn ghi cũ | T09 và lịch sử chuyển quyền |
| Phục hồi dữ liệu nhưng sai nghiệp vụ hoặc quyền | SEC-RPO-08 | Kiểm tra bất biến và trạng thái bảo mật trước mở phục vụ | T08 và bằng chứng kiểm tra quyền |
| Thay đổi schema hoặc hạ tầng làm mất khả năng restore | SEC-RPO-10 | Quản lý thay đổi và kiểm chứng phục hồi tương thích | T12 và kết quả restore theo phiên bản |

Chuỗi truy vết này cần đi cùng yêu cầu trong vòng đời phát triển. Khi thay đổi nơi lưu dữ liệu, cơ chế commit hoặc phụ thuộc mã hóa, nhóm triển khai phải biết mục tiêu nào có thể bị ảnh hưởng và cần kiểm chứng gì.

Không chỉ ghi một tên công cụ backup trong tài liệu yêu cầu. Yêu cầu phải giữ được ý nghĩa khi thay công cụ: dữ liệu nào cần bảo toàn, dưới sự cố nào, tới mốc nào và với bằng chứng gì.

## 12. Logging, giám sát và quy trình vận hành

Các chỉ số hữu ích gồm:

- Độ bao phủ dữ liệu phục hồi ngoài miền sự cố, theo nguồn đo và phạm vi đã định nghĩa.
- Thời gian tồn đọng log, số đoạn thiếu hoặc kiểm tra thất bại.
- Tuổi bản nền phù hợp gần nhất và trạng thái chuỗi phụ thuộc.
- Kết quả kiểm tra khả năng đọc dữ liệu và sử dụng khóa.
- Ngày diễn tập restore gần nhất, mốc phục hồi thực tế và các lỗi còn mở.
- Số lần thay đổi retention, quyền truy cập, cấu hình backup hoặc chính sách khóa.

Cần phân biệt chỉ số suy ra từ pipeline với bằng chứng restore. Một dashboard xanh có thể cho biết luồng sao chép đang chạy, nhưng không thay thế việc chứng minh dữ liệu thực sự khôi phục được.

Checksum giúp phát hiện một số lỗi ở mức byte; nó không tự chứng minh dữ liệu nghiệp vụ đúng, chuỗi log đầy đủ hoặc điểm phục hồi sạch. Kiểm tra truy cập được kho backup cũng chưa chứng minh có thể dựng lại toàn bộ hệ thống.

Mỗi lần diễn tập nên có hồ sơ:

```text
Scenario và phạm vi lỗi
RPO/RTO mục tiêu cùng phiên bản yêu cầu
Mốc cắt, mốc phục hồi và cơ sở thời gian
Danh sách thành phần phục hồi đã dùng
Kết quả kiểm tra độ đầy đủ, toàn vẹn và quyền
Các thao tác thiếu, trùng hoặc cần đối soát
Khoảng lùi dữ liệu và thời gian phục hồi thực tế
Sai lệch, người chịu trách nhiệm và hành động tiếp theo
```

Nếu không đo được độ bao phủ hoặc mất nguồn giám sát, phải báo trạng thái không xác định. Không giữ nguyên giá trị cũ rồi coi nó là mức bảo vệ hiện tại.

Quy trình ứng phó cần chỉ rõ người tuyên bố sự cố, người chọn điểm phục hồi, người cho phép chuyển quyền ghi và điều kiện mở phục vụ. Thay đổi quyền xóa bản sao, thời hạn lưu hoặc reset lịch sử phải có dấu vết kiểm toán.

Diễn tập cần được lên kế hoạch theo mức rủi ro và sau các thay đổi ảnh hưởng tới đường phục hồi. Việc xác định lịch cụ thể là một phần của yêu cầu vận hành; không chỉ ghi “kiểm tra định kỳ” mà thiếu chủ thể, phạm vi và bằng chứng hoàn thành.

## 13. Các lỗi đặc tả thường gặp

| Phát biểu | Vấn đề | Cách viết rõ hơn |
|---|---|---|
| “RPO 5 phút cho hệ thống” | Không có dữ liệu, kịch bản và mốc tính | Nêu phạm vi dữ liệu, miền sự cố, cách đo và giới hạn cam kết |
| “Backup mỗi 5 phút nên RPO là 5 phút” | Bỏ qua mốc dữ liệu, thời gian sao chép và bản sao lỗi | Kiểm chứng mốc phục hồi sử dụng được ở miền an toàn |
| “Backup vừa xong lúc 10:15” | Chưa biết dữ liệu phản ánh thời điểm nào | Ghi cả mốc nhất quán của bản sao và thời điểm hoàn thành |
| “Có replica nên không mất dữ liệu” | Chưa rõ xác nhận ghi, độ bền và loại sự cố | Nêu điều kiện commit, miền lỗi và hành vi failover |
| “Mở được database là restore thành công” | Có thể thiếu dữ liệu hoặc sai quan hệ nghiệp vụ | Kiểm tra độ đầy đủ, bất biến và đối chiếu thao tác đã xác nhận |
| “Bản mới nhất luôn là bản tốt nhất” | Bản mới có thể chứa thay đổi sai hoặc độc hại | Xác minh điểm sạch theo kịch bản toàn vẹn |
| “RPO bằng 0 cho mọi tình huống” | Không có giả định và miền sự cố hữu hạn | Cam kết không mất ghi đã xác nhận cho từng kịch bản có bằng chứng |
| “RTO đạt nên RPO cũng đạt” | Lẫn thời gian phục vụ lại với mất dữ liệu | Đo hai mục tiêu và báo cáo độc lập |
| “Có dữ liệu mã hóa là an toàn để restore” | Có thể thiếu khóa hoặc quyền dùng khóa | Kiểm chứng phục hồi cả dữ liệu, phiên bản khóa và quyền |
| “Timestamp mới nhất là điểm phục hồi” | Không phát hiện lỗ hổng ở dữ liệu cũ hoặc phân vùng khác | Chứng minh mốc bao phủ nhất quán, không chỉ độ mới |

## 14. Bài tập áp dụng

Bạn thiết kế một nền tảng gồm database giao dịch, object storage lưu tệp và queue xử lý công việc. Hãy xây dựng một tập yêu cầu RPO gồm:

1. Hai kịch bản: mất vùng chính và xóa nhầm được phát hiện muộn.
2. Phạm vi dữ liệu nguồn, dữ liệu dẫn xuất và các bất biến xuyên kho.
3. RPO cho từng kịch bản, mốc cắt và định nghĩa thao tác đã xác nhận.
4. Thành phần cần bảo toàn: bản nền, log, metadata, khóa và nguồn đối chiếu.
5. Cách chọn mốc phục hồi nhất quán và phát hiện dữ liệu bị thiếu.
6. Hành vi khi replica chậm, chuỗi log đứt hoặc khóa không sử dụng được.
7. Ca kiểm thử thể hiện một lần đạt RPO, một lần trượt RPO và một lần chưa đủ bằng chứng.
8. Chuỗi truy vết từ rủi ro tới yêu cầu, kiến trúc và kết quả kiểm chứng.

Tự kiểm tra bản đặc tả bằng hai câu hỏi: **Một nhóm triển khai độc lập có biết cần bảo vệ chính xác những gì không? Một nhóm kiểm thử độc lập có xác định được mốc dữ liệu phục hồi và kết luận đạt hay trượt mà không phải đoán không?**
