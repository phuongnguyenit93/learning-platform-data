# Kiểm thử failover trong hệ thống PAM

## 1. Mục tiêu của kiểm thử failover

Failover là quá trình chuyển vai trò phục vụ sang thành phần dự phòng khi thành phần đang phục vụ không còn đáp ứng được yêu cầu. Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), kiểm thử failover phải trả lời đồng thời hai câu hỏi:

- Người dùng và ứng dụng có lấy lại được dịch vụ trong thời gian chấp nhận được không?
- Trong quá trình chuyển đổi, quyền truy cập, credential và bằng chứng kiểm toán có còn đúng với chính sách không?

Một giao diện đăng nhập hoạt động trở lại chưa đủ để kết luận PAM đã phục hồi. Có thể người dùng đăng nhập được nhưng không lấy được mật khẩu, yêu cầu JIT không hết hạn, phiên SSH đi sai gateway hoặc bản ghi phiên chưa được lưu bền vững. Thậm chí hệ thống có thể phục hồi khả dụng bằng cách bỏ qua MFA hoặc cho phép một tài khoản đã bị thu hồi tiếp tục hoạt động. Những trường hợp đó không đạt mục tiêu kiểm thử.

Bài học này hướng dẫn thiết kế và thực hiện kiểm thử failover theo hướng độc lập nhà cung cấp. Các ngưỡng thời gian, tên node và dữ liệu trong ví dụ là giả định phục vụ học tập; cần thay bằng hợp đồng dịch vụ và khả năng đã được xác minh của hệ thống thực tế.

### Kết quả cần tạo ra

Sau một lần kiểm thử, nhóm vận hành phải có bằng chứng để kết luận về:

1. Thời gian gián đoạn và phục hồi của từng luồng truy cập quan trọng.
2. Credential, chính sách, approval và quyền tạm thời trước, trong, sau chuyển đổi.
3. Số phận của phiên đặc quyền đang mở và khả năng truy nguyên bản ghi phiên.
4. Tình trạng node cũ, node mới, hàng đợi và dữ liệu sau khi lỗi được gỡ.
5. Điều kiện tiếp tục phục vụ, rollback, khôi phục dự phòng hoặc chuyển sang quy trình sự cố.

## 2. Phân biệt failover, failback và disaster recovery

| Khái niệm | Ý nghĩa | Câu hỏi kiểm thử |
|---|---|---|
| Failover | Chuyển dịch vụ hoặc vai trò sang thành phần dự phòng | Thành phần mới có phục vụ đúng và an toàn không? |
| Failback | Chuyển về vị trí hoặc cấu hình vận hành mong muốn sau khi ổn định | Có đồng bộ đủ trạng thái trước khi chuyển về không? |
| Disaster recovery — DR | Khôi phục sau sự cố vượt khả năng chịu lỗi của kiến trúc đang chạy | Có khôi phục được dịch vụ và dữ liệu trong phạm vi RTO/RPO đã cam kết không? |
| Restart | Khởi động lại một tiến trình hoặc node | Dịch vụ có thể trở lại, nhưng có thực sự sử dụng thành phần dự phòng không? |

Một bài kiểm thử dừng node rồi chờ chính node đó khởi động lại chỉ chứng minh khả năng restart nếu không có bằng chứng chuyển vai trò. Tương tự, chuyển lưu lượng sang một cụm khác không tự động chứng minh DR nếu cụm mới chưa được kiểm tra tính nhất quán dữ liệu và quyền quản trị.

Failback không phải bước bắt buộc phải thực hiện ngay khi node cũ hoạt động trở lại. Chuyển về quá sớm có thể gây thêm một lần gián đoạn hoặc đưa dữ liệu cũ trở lại đường phục vụ. Bài kiểm thử cần tách rõ giai đoạn ổn định sau failover và một lần chuyển về có điều kiện.

## 3. Xác định thành phần nào thực sự chuyển đổi

PAM thường là một chuỗi dịch vụ, không phải một cặp máy chủ duy nhất. Cần mô tả đường đi của một giao dịch đặc quyền trước khi chọn lỗi để tiêm vào.

```text
Người quản trị / ứng dụng
          |
          v
DNS / Load balancer / điểm truy cập
          |
          v
API PAM + xác thực + quyết định chính sách
          |                  |
          v                  v
Vault / kho trạng thái   Gateway phiên
          |                  |
          v                  v
Credential / lease       Máy chủ hoặc DB đích
          \                  /
           v                v
          Audit / recording / hệ thống giám sát
```

Đây là sơ đồ khái niệm. Một sản phẩm có thể gộp hoặc tách các vai trò trên, sử dụng nhiều leader độc lập, hoặc có cơ chế chuyển đổi khác nhau cho từng dịch vụ.

### 3.1. Control plane và data plane

**Control plane** xử lý các hoạt động như đăng nhập, duyệt yêu cầu, đánh giá chính sách, cấp quyền JIT, checkout secret và điều phối luân chuyển credential.

**Data plane** mang lưu lượng của phiên SSH, RDP, kết nối cơ sở dữ liệu hoặc luồng truy cập qua proxy.

Control plane hoạt động trở lại không có nghĩa phiên đang mở được chuyển sang gateway mới. Nhiều kiến trúc có thể cho phép phiên cũ tiếp tục trên gateway còn sống nhưng không di chuyển được một kết nối TCP khi gateway đó mất. Khi đó, yêu cầu đúng có thể là đóng phiên rõ ràng và cho phép kết nối lại theo chính sách, thay vì hứa chuyển phiên trong suốt.

### 3.2. Lập bảng phụ thuộc

| Phụ thuộc | Lỗi có thể quan sát | Điều cần kiểm tra |
|---|---|---|
| IdP/MFA | Không xác thực được hoặc token mới bị từ chối | Chính sách xác thực và truy cập khẩn cấp vẫn được áp dụng |
| Storage/quorum | Không ghi trạng thái hoặc không bầu được leader | Không có hai bên cùng sửa dữ liệu trái thẩm quyền |
| KMS/HSM | Node dự phòng không sử dụng được khóa cần thiết | Node mới có thực sự sẵn sàng trước khi nhận lưu lượng |
| DNS/load balancer | Client còn đi tới node cũ | Đường truy cập thực tế chuyển đổi đúng |
| Gateway phiên | Phiên cũ ngắt hoặc phiên mới không mở được | Hành vi phiên khớp hợp đồng, không tạo đường truy cập ngoài kiểm soát |
| Kho recording/audit | Mất upload, tồn đọng hoặc đầy hàng đợi | Có cảnh báo, bảo toàn dữ liệu và hành vi từ chối theo chính sách |
| Hệ thống đích | Credential không khớp hoặc đích bị cô lập | Phân biệt lỗi PAM với lỗi dịch vụ đích |

Một dependency dùng chung có thể làm cả node chính và dự phòng cùng mất khả năng phục vụ. Vì vậy, danh sách node dự phòng phải đi kèm failure domain của nguồn điện, mạng, storage và dịch vụ khóa.

### 3.3. Không suy rộng cơ chế của một sản phẩm

Ví dụ, tài liệu HA của HashiCorp Vault mô tả việc node đang active giữ HA lock và node mới nhận vai trò theo cơ chế của storage backend. Chi tiết này giúp đặt câu hỏi kiểm thử về quyền sở hữu vai trò; nó không có nghĩa mọi thành phần PAM đều dùng cùng một cơ chế. Xem [High Availability của HashiCorp Vault](https://developer.hashicorp.com/vault/docs/internals/high-availability).

## 4. Xây dựng các bất biến an toàn trước khi gây lỗi

Bất biến là điều kiện phải luôn đúng, kể cả khi dịch vụ tạm thời không khả dụng. Chỉ đo thời gian chuyển đổi mà không kiểm tra các bất biến sẽ bỏ sót lỗi nguy hiểm nhất.

### 4.1. Quyết định cấp quyền không được nới lỏng

- Tài khoản không có quyền vẫn bị từ chối.
- Yêu cầu cần approval vẫn cần approval theo chính sách.
- MFA không bị bỏ qua vì node chính lỗi.
- Quyền JIT/JEA không tự kéo dài ngoài khoảng thời gian được cấp.
- Yêu cầu thu hồi đã được hệ thống xác nhận thành công không bị đảo ngược khi đổi node.

Trường hợp mất dịch vụ xác thực phải có hành vi đã định trước. Không coi việc dùng một phiên đăng nhập mới mà không xác thực đầy đủ là thành công của failover.

### 4.2. Thay đổi credential phải có một trạng thái có thẩm quyền

Một rotation thường liên quan ít nhất hai nơi: hệ thống PAM và hệ thống đích. Credential có thể đã đổi ở máy đích trong khi kết quả chưa được ghi về vault; hoặc vault đã ghi một trạng thái trung gian nhưng worker chưa hoàn thành.

Bài kiểm thử phải tìm được câu trả lời cho từng giao dịch:

- Thao tác chưa được thực hiện.
- Thao tác đã hoàn thành và đã xác nhận.
- Kết quả chưa xác định, cần đối soát.
- Thao tác bị lỗi và có quy trình phục hồi được kiểm soát.

Timeout của client không chứng minh thao tác đã thất bại. Không phát lại một lệnh rotation có tác dụng phụ chỉ vì chưa nhận được phản hồi.

### 4.3. Node cũ không được tiếp tục tạo thay đổi trái thẩm quyền

Trong kiến trúc có một bên ghi chính, cần chứng minh chỉ thành phần có quyền hợp lệ mới thực hiện được thay đổi. Việc node cũ còn hiển thị giao diện không tự chứng minh split-brain; bằng chứng cần liên quan đến khả năng cấp quyền, ghi trạng thái hoặc thay đổi credential.

Fencing là cách ngăn thành phần mất thẩm quyền tiếp tục tác động lên tài nguyên. Tùy kiến trúc, cơ chế có thể nằm ở storage, token thế hệ, khóa, proxy, mạng hoặc hệ thống quản lý hạ tầng. Kiểm thử phải xác minh hiệu quả của cơ chế thực tế, đặc biệt khi node cũ quay lại.

Trong các cụm quorum, không nên suy luận rằng bên còn chạy tiến trình luôn được phép ghi. Tài liệu failure modes của etcd minh họa rằng phía đa số có thể tiếp tục phục vụ còn phía thiểu số không có cùng thẩm quyền. Đây là ví dụ của một hệ thống cụ thể; áp dụng cho PAM cần kiểm tra backend thực tế. Xem [Failure modes của etcd](https://etcd.io/docs/v3.6/op-guide/failures/).

### 4.4. Bằng chứng kiểm toán phải truy nguyên được

Một phiên có thể sinh nhiều đoạn recording trước và sau chuyển đổi. Điều quan trọng là nối được chúng với cùng yêu cầu, người dùng, tài khoản đích và mốc thời gian; không bắt buộc mọi sản phẩm phải tạo một file duy nhất.

Cần phân biệt:

- Dữ liệu đã tạo ở gateway.
- Dữ liệu đã ghi bền vững tại nơi lưu được thiết kế.
- Dữ liệu đã tới hệ thống phân tích hoặc SIEM.
- Dữ liệu người kiểm toán thực sự truy xuất được.

Trễ tới SIEM không nhất thiết đồng nghĩa mất audit. Ngược lại, một màn hình có tên phiên chưa chứng minh recording đã được lưu đầy đủ.

## 5. Định nghĩa thước đo và tiêu chí đạt

### 5.1. RTO phải gắn với luồng nghiệp vụ

Định nghĩa trước hai mốc:

```text
t_impact: thời điểm đầu tiên luồng kiểm thử không còn đạt hợp đồng dịch vụ.
t_stable: thời điểm bắt đầu khoảng phục hồi ổn định đã quy định.

Observed recovery time = t_stable - t_impact
```

Trong bài này, `t_stable` là mốc đầu của một cửa sổ ổn định chỉ được xác nhận sau khi quan sát đủ cửa sổ đó. Ví dụ, yêu cầu thành công liên tục trong 60 giây: chỉ sau 60 giây mới được kết luận cửa sổ bắt đầu tại mốc nào. Không lấy lần trả về HTTP thành công đầu tiên làm mốc phục hồi ổn định nếu ngay sau đó vẫn xuất hiện lỗi.

Mốc tiêm lỗi có thể khác `t_impact`. Một hệ thống có thể tiếp tục phục vụ qua cache hoặc phiên hiện hữu một thời gian sau khi lỗi bắt đầu. Báo cáo cần lưu cả hai để không che giấu khoảng trễ phát hiện.

Nên đo riêng:

- Đăng nhập và kiểm tra MFA.
- Checkout credential hoặc cấp lease mới.
- Cấp quyền JIT mới.
- Khởi tạo phiên đặc quyền mới.
- Thu hồi quyền và chấm dứt phiên theo chính sách.
- Luân chuyển credential và đối soát.
- Truy xuất recording/audit.

### 5.2. RPO phải xác định loại dữ liệu

RPO mô tả mức mất dữ liệu chấp nhận được, thường biểu diễn theo thời gian. Với PAM, nên bổ sung cả số lượng và tính chất của bản ghi có thể thiếu:

| Loại dữ liệu | Bằng chứng cần đối soát |
|---|---|
| Chính sách/approval | Phiên bản đã được xác nhận, trạng thái được áp dụng sau failover |
| Credential/rotation | ID giao dịch, phiên bản secret và kết quả tại hệ thống đích |
| Lease/JIT | Thời điểm cấp, thời điểm hết hạn, trạng thái thu hồi |
| Audit | Event ID, đối tượng, kết quả và liên kết giao dịch |
| Recording | Session ID, các đoạn dữ liệu, khoảng thời gian bao phủ và khả năng phát lại |

Không thể kết luận RPO bằng 0 chỉ vì replication lag báo 0. Cần đối soát các thay đổi đã được hệ thống xác nhận với trạng thái thực tế sau chuyển đổi.

Nếu hợp đồng yêu cầu không mất giao dịch đã xác nhận, bài kiểm thử phải kiểm tra đúng tập đó. Các yêu cầu đang bay tại thời điểm lỗi cần được phân loại riêng; trạng thái chưa xác định không được tự gộp thành thành công hoặc mất dữ liệu.

### 5.3. Bộ tiêu chí minh họa

Các con số dưới đây là mục tiêu giả định cho một môi trường lab:

| Luồng/thuộc tính | Tiêu chí minh họa |
|---|---|
| Checkout secret thử nghiệm | Phục hồi ổn định trong 60 giây |
| Tạo phiên mới | Phục hồi ổn định trong 90 giây |
| Giao dịch đã xác nhận | Không thiếu giao dịch trong tập đối soát |
| Yêu cầu không được cấp quyền | Luôn bị từ chối |
| JIT hết hạn | Không tạo được thao tác mới ngoài thời hạn theo hợp đồng thu hồi |
| Phiên đang mở | Tiếp tục hoặc đóng có kiểm soát đúng thiết kế được công bố |
| Audit/recording | Không có khoảng trống không giải thích được; backlog về ngưỡng cho phép |
| Node cũ quay lại | Gia nhập đúng vai trò, không phục vụ bằng trạng thái cũ trái thẩm quyền |

Hợp đồng thu hồi phải nói rõ phạm vi: từ chối yêu cầu mới, đóng phiên hiện hữu, hết hạn credential hay tất cả các hành vi đó. Thu hồi ở PAM không tự động bảo đảm mọi phiên đã xác thực trực tiếp tại đích đều bị chấm dứt.

## 6. Thiết kế ma trận kịch bản

Không cần gây mọi lỗi cùng một lúc. Mỗi ca nên có một giả thuyết chính và một phạm vi ảnh hưởng đủ nhỏ để kết luận được nguyên nhân.

| Ca | Lỗi được mô phỏng | Trọng tâm quan sát |
|---|---|---|
| F01 | Chuyển vai trò có kế hoạch | Chuỗi chuyển đổi bình thường, thông báo và drain |
| F02 | Node active dừng đột ngột | Phát hiện lỗi, bầu/chuyển vai trò, client retry |
| F03 | Mất kết nối của node active với backend | Thẩm quyền ghi và xử lý node còn sống nhưng bị cô lập |
| F04 | Phân vùng mạng giữa các node | Quorum, fencing và hành vi phía thiểu số |
| F05 | Backend mất khả năng ghi | Từ chối an toàn, cảnh báo, không báo thành công giả |
| F06 | Load balancer còn giữ node lỗi | Readiness, độ trễ loại node và client còn kết nối cũ |
| F07 | Gateway đang giữ phiên bị mất | Phiên hiện hữu, reconnect và recording |
| F08 | Gián đoạn trong lúc rotation | Trạng thái chưa xác định và đối soát credential |
| F09 | Gián đoạn trong lúc cấp/thu hồi JIT | Hết hạn, thu hồi và chống thực thi trùng |
| F10 | Kho audit/recording không nhận dữ liệu | Buffer bền vững, backpressure và chính sách tiếp tục |
| F11 | Node cũ trở lại với trạng thái chậm | Đồng bộ, admission vào đường phục vụ và chống ghi cũ |
| F12 | Chuyển về sau khi ổn định | Failback, drain, sức tải và tránh lặp chuyển vai trò |

### Các trục bổ sung

Một ca failover cần được lặp lại ở các thời điểm có ý nghĩa:

- Khi hệ thống rảnh và khi tải gần mức dự kiến.
- Trước, trong và sau một giao dịch có tác dụng phụ.
- Với client mới và client đang giữ connection pool.
- Với phiên mới và phiên đã chạy lâu.
- Với dependency còn khỏe và với dependency bị suy giảm có kiểm soát.

Không nhân số tổ hợp một cách máy móc. Ưu tiên đường truy cập quan trọng, thành phần có lịch sử lỗi và tình huống có thể gây cấp quyền sai hoặc mất bằng chứng.

Ca mất toàn bộ quorum có thể có kết quả mong đợi là dừng ghi an toàn, không phải tự động phục hồi. Phải ghi rõ đây là ca kiểm chứng giới hạn chịu lỗi hoặc kích hoạt DR; không ép hệ thống phục vụ bằng cách vô hiệu hóa cơ chế bảo vệ.

## 7. Chuẩn bị môi trường, dữ liệu và khả năng quan sát

### 7.1. Chọn phạm vi kiểm thử

Bắt đầu với lab hoặc staging có cấu hình và dependency đại diện cho kiến trúc cần đánh giá. Một ca staging thiếu IdP, kho recording hoặc cơ chế mã hóa của production chỉ chứng minh được phạm vi đang có.

Trước khi thực hiện trên hệ thống phục vụ thật, ca kiểm thử cần nằm trong kế hoạch thay đổi hoặc chương trình diễn tập đã được tổ chức cho phép, có người điều phối và đường phục hồi phù hợp. Quyền gây lỗi phải giới hạn vào các thành phần được ghi trong ca.

### 7.2. Dữ liệu thử có nhận diện rõ

Chuẩn bị tối thiểu:

- Một người dùng có quyền đúng cho tác vụ thử.
- Một người dùng không có quyền để kiểm tra từ chối.
- Một tài khoản đích và secret dùng riêng cho ca.
- Một approval đã duyệt và một approval chưa duyệt.
- Một quyền JIT sẽ hết hạn trong cửa sổ diễn tập.
- Một phiên tương tác tạo dấu mốc vô hại trên đích thử nghiệm.
- Một rotation job có ID truy nguyên và cách đối soát được định trước.

Không dùng mật khẩu thật trong log kiểm thử. Thu thập ID, phiên bản metadata hoặc kết quả đối soát; tránh ghi nội dung secret. Khi cần chứng minh credential mới dùng được, thực hiện xác thực vào tài nguyên thử nghiệm qua đường truy cập đã kiểm soát và chỉ lưu kết quả đã che dữ liệu nhạy cảm.

### 7.3. Xác nhận đường quản trị khẩn cấp

Phải kiểm tra đường phục hồi trước khi gây lỗi vào chính hệ thống đang quản lý quyền truy cập. Nếu thao tác gỡ lỗi mạng cũng phụ thuộc hoàn toàn vào gateway bị tắt, nhóm có thể tự khóa khả năng rollback.

Break-glass là quy trình khẩn cấp được kiểm soát riêng, có danh tính, phạm vi, thời hạn và kiểm toán. Việc phải kích hoạt break-glass không tự động làm bài kiểm thử thất bại, nhưng phải được phân loại đúng: luồng thông thường đã không đáp ứng mục tiêu, còn luồng khẩn cấp có thể được đánh giá riêng.

Sau diễn tập, mọi quyền khẩn cấp phải được thu hồi và credential liên quan được xử lý theo chính sách.

### 7.4. Thu thập quan sát từ nhiều phía

| Góc nhìn | Dữ liệu nên thu |
|---|---|
| Client | Request ID, operation ID, kết quả, độ trễ, số retry và timeout |
| Load balancer | Backend được chọn, trạng thái pool và lỗi kết nối |
| PAM | Vai trò node, lỗi policy, giao dịch cấp quyền và hàng đợi |
| Backend | Vai trò có thẩm quyền, replication lag, khả năng ghi và thời điểm chuyển vai trò |
| Gateway | Session ID, kết nối đích và trạng thái recording |
| Hệ thống đích | Kết quả xác thực, phiên mở và thay đổi credential thử nghiệm |
| Audit/recording | Event ID, dữ liệu tới nơi lưu, tồn đọng và khả năng truy xuất |

Dùng đồng hồ được đồng bộ để đối chiếu sự kiện giữa các máy. Khi đo một khoảng thời gian trong cùng một tiến trình, ưu tiên đồng hồ đơn điệu nếu công cụ hỗ trợ; đồng hồ thời gian thực có thể bị hiệu chỉnh.

Tần suất probe ảnh hưởng độ chính xác của phép đo. Nếu probe mỗi 5 giây, không nên báo thời gian phục hồi với độ chính xác đến mili giây. Ghi khoảng sai số và vị trí đặt probe.

## 8. Quy trình thực hiện một ca kiểm thử

### Bước 1 — Chốt giả thuyết và tiêu chí

Ví dụ:

> Khi node A đang giữ vai trò phục vụ chính bị mất, luồng checkout và tạo phiên mới chuyển qua thành phần dự phòng trong ngưỡng đã đặt; quyền chưa được duyệt vẫn bị từ chối, và mọi giao dịch đã xác nhận đều đối soát được.

Ghi rõ node, dependency, loại lỗi, thời lượng tối đa, đường truy cập và dữ liệu thử. Các mục tiêu hiệu năng phải gắn với mức tải và vị trí client.

### Bước 2 — Ghi baseline trước lỗi

Chạy các luồng thử trong một khoảng đủ để xác nhận hệ thống ổn định:

- Người có quyền thực hiện thành công.
- Người không có quyền bị từ chối.
- Approval chưa duyệt không mở được phiên.
- Quyền JIT đang hoạt động và có mốc hết hạn rõ ràng.
- Recording tạo và truy xuất được.
- Không có backlog hoặc lỗi tồn tại chưa được giải thích.

Lưu cấu hình hiệu lực và phiên bản triển khai cần thiết để tái hiện ca. Nếu baseline đã lỗi, dừng ca hoặc ghi rõ mục tiêu đang đổi thành chẩn đoán lỗi có sẵn.

### Bước 3 — Tạo giao dịch và phiên xuyên qua thời điểm lỗi

Khởi động các probe liên tục trước khi gây lỗi. Tạo một số phiên dùng riêng cho diễn tập, gắn nhãn và operation ID để đối soát.

Đối với rotation hoặc cấp quyền, nên có một ca diễn ra sát thời điểm lỗi để bộc lộ cửa sổ trạng thái trung gian. Công cụ phải giữ được ID của thao tác ngay cả khi phản hồi timeout.

### Bước 4 — Tiêm đúng một lỗi đã định vị

Thực hiện cơ chế gây lỗi được nền tảng và kế hoạch hỗ trợ. Ghi lại thời điểm thực tế, người thực hiện và bằng chứng lỗi đã có hiệu lực.

Không coi thao tác bấm nút thành công là đủ: cần chứng minh lỗi đã đánh vào đúng đường phục vụ. Ví dụ, phải biết A đang giữ vai trò gì ngay trước khi cô lập A, và client đang đi qua đường nào.

Giới hạn thời gian tồn tại của lỗi và có người quan sát điều kiện dừng. Không đồng thời tắt thêm thành phần chỉ vì chưa thấy kết quả mong muốn.

### Bước 5 — Quan sát quá trình chuyển đổi

Theo dõi độc lập:

1. Lúc nào hệ thống phát hiện lỗi?
2. Khi nào thành phần dự phòng nhận quyền phục vụ?
3. Khi nào load balancer hoặc client sử dụng được đường mới?
4. Khi nào từng luồng nghiệp vụ phục hồi ổn định?
5. Có giao dịch nào đang ở trạng thái chưa xác định?
6. Phiên hiện hữu, recording và quyền sắp hết hạn có hành vi gì?

Không dùng thao tác sửa tay để làm probe xanh rồi vẫn báo failover tự động thành công. Mọi can thiệp phải được ghi trong timeline và đưa vào đánh giá.

### Bước 6 — Kiểm tra bất biến sau phục hồi

Lặp lại các kiểm tra âm tính và đối soát dữ liệu:

- Tài khoản không có quyền vẫn bị từ chối.
- Approval chưa duyệt vẫn không mở được quyền.
- Quyền đã hết hạn hoặc đã thu hồi không được tái cấp từ trạng thái cũ.
- Credential tại PAM và đích có trạng thái được giải thích.
- Không có giao dịch có tác dụng phụ bị lặp ngoài dự kiến.
- Recording và audit truy xuất được sau khi hàng đợi được xử lý.

Dịch vụ phục hồi nhanh nhưng vi phạm một bất biến an toàn phải được đánh giá là không đạt.

### Bước 7 — Gỡ lỗi và quan sát node cũ trở lại

Sau khi đường phục vụ mới ổn định, gỡ lỗi theo kế hoạch. Xác minh node cũ đồng bộ đúng, không tự giữ vai trò cũ ngoài thẩm quyền và chỉ được đưa vào pool khi đạt điều kiện sẵn sàng.

Theo dõi xem có chuyển vai trò qua lại, tải tăng đột biến, replay job hoặc tăng backlog không. Chưa kết thúc ca chỉ vì lỗi mạng đã được gỡ.

### Bước 8 — Khép ca và phục hồi môi trường

Chốt đối soát, đóng phiên thử, thu hồi quyền tạm và xác nhận lịch rotation không còn bị tạm dừng. Nếu failback là một ca riêng, chỉ thực hiện sau khi đủ điều kiện của ca đó.

Lưu kết luận theo từng tiêu chí. Thiếu bằng chứng thì ghi chưa kết luận, không tự đổi thành đạt.

## 9. Mẫu đặc tả ca kiểm thử

Khối YAML dưới đây chỉ là mẫu tài liệu kiểm thử, không phải cấu hình để nạp vào bất kỳ sản phẩm PAM nào:

```yaml
testCase:
  id: PAM-HA-F02
  title: Mat node active trong khi co checkout va phien thu nghiem
  environment: staging
  scope:
    faultTarget: pam-node-a
    fault: abrupt_node_loss
    maximumFaultDurationSeconds: 180
    excludedTargets:
      - production_targets
      - shared_identity_provider

  preconditions:
    - baseline_pass
    - recovery_access_verified
    - test_identity_and_target_ready
    - observability_ready

  workload:
    checkoutProbeIntervalSeconds: 2
    newSessionProbeIntervalSeconds: 5
    deniedRequestProbeIntervalSeconds: 2
    existingSessionCount: 2

  acceptance:
    checkoutRecoverySeconds: 60
    newSessionRecoverySeconds: 90
    stableWindowSeconds: 60
    acknowledgedOperationsMissing: 0
    unauthorizedGrants: 0
    unexplainedAuditGaps: 0
    existingSessionBehavior: controlled_disconnect_or_documented_continuity

  abortConditions:
    - unauthorized_grant_observed
    - suspected_conflicting_writers
    - impact_outside_test_scope
    - recovery_access_unavailable
    - fault_duration_limit_reached

  evidence:
    - client_probe_results
    - role_transition_timeline
    - operation_reconciliation
    - session_and_recording_manifest
    - cleanup_readback
```

Điều kiện phiên trong ví dụ chỉ hợp lệ khi đã chọn chính xác hành vi mong đợi trước khi chạy ca. Không dùng chữ “hoặc” để chấp nhận bất kỳ kết quả nào sau khi sự cố đã xảy ra.

## 10. Probe nghiệp vụ và retry an toàn

### 10.1. Probe phải kiểm tra kết quả nghiệp vụ

Một probe checkout không chỉ kiểm tra HTTP thành công. Nó cần xác nhận:

- Phản hồi thuộc đúng tài khoản thử và đúng phạm vi quyền.
- Credential hoặc lease có metadata hợp lệ theo hợp đồng.
- Kết quả sử dụng tại tài nguyên thử nghiệm phù hợp.
- Audit liên kết được với giao dịch.
- Secret không bị in vào báo cáo.

Tương tự, probe tạo phiên phải xác nhận mở được phiên tới đúng đích và có cơ chế recording đúng chính sách. Probe từ chối phải kiểm tra lý do từ chối; lỗi mạng không phải bằng chứng chính sách đang chặn.

Mã giả sau diễn tả ý tưởng thu thập, không phải chương trình có thể chạy trực tiếp:

```text
while test_window_is_open:
    logical_operation_id = new_test_operation_id()
    start = monotonic_time()

    result = perform_documented_probe(
        operation_id = logical_operation_id,
        test_identity = dedicated_test_identity,
        test_target = dedicated_test_target
    )

    save_redacted_observation(
        operation_id = logical_operation_id,
        elapsed = monotonic_time() - start,
        transport_result = result.transport,
        business_result = result.business,
        audit_reference = result.audit_reference
    )

    wait_until_next_probe_slot()
```

Các lần retry của cùng một thao tác logic phải liên kết về cùng operation ID trong công cụ đo. Một giao thức có thể yêu cầu request ID khác cho mỗi lần gửi; cần giữ cả hai loại ID để phân biệt một tác vụ với nhiều lần thử vận chuyển.

### 10.2. Không retry mù thao tác có tác dụng phụ

Với lệnh đọc, retry có thể tương đối đơn giản theo hợp đồng API. Với rotation, cấp quyền hoặc tạo phiên, gửi lại có thể tạo một lần thực thi mới nếu API không hỗ trợ chống trùng.

Cách xử lý cần dựa vào khả năng của sản phẩm:

1. Dùng idempotency key nếu API có hỗ trợ với ngữ nghĩa đã được xác minh.
2. Tra cứu trạng thái bằng ID giao dịch khi có thể.
3. Đối soát trạng thái vault và đích khi kết quả chưa xác định.
4. Chỉ thử lại hoặc bù trừ theo quy trình xử lý của thao tác đó.

Việc client gắn một header tự đặt không tạo ra tính idempotent nếu server không thực thi cơ chế tương ứng.

### 10.3. Kiểm tra connection pool, cache và backoff

Một lần thử từ trình duyệt mới có thể thành công trong khi một ứng dụng giữ connection pool vẫn gọi node lỗi. Cần thử cả client mới lẫn client đang chạy lâu, quan sát DNS cache, kết nối keep-alive và cách chọn endpoint.

Retry quá dồn dập có thể tạo tải đột biến ngay khi node dự phòng vừa nhận vai trò. Kiểm thử nên quan sát giới hạn retry, backoff và độ lệch ngẫu nhiên nếu client có hỗ trợ; chọn giá trị theo hợp đồng dịch vụ thay vì một công thức chung cho mọi hệ thống.

## 11. Đối soát các tình huống nhạy cảm của PAM

### 11.1. Rotation bị gián đoạn giữa hai hệ thống

Giả sử job R-17 bắt đầu đổi mật khẩu của tài khoản thử. Sau khi đích đã đổi nhưng trước khi kết quả quay về, node điều phối mất.

Kết quả client là timeout, nhưng không được kết luận mật khẩu cũ vẫn có hiệu lực. Nhóm kiểm thử cần đối chiếu job ID, trạng thái tại đích, phiên bản secret và kết quả khôi phục theo cơ chế sản phẩm.

Tiêu chí đạt có thể bao gồm:

- Hệ thống phát hiện giao dịch chưa xác định.
- Không có worker thứ hai tự tạo một rotation xung đột.
- Đối soát đưa về một trạng thái có thẩm quyền.
- Credential cuối cùng dùng được tại tài nguyên thử.
- Trạng thái thành công chỉ xuất hiện khi có bằng chứng phù hợp.
- Mọi bước can thiệp đều được audit.

Không thử hàng loạt mật khẩu để đoán trạng thái. Việc xác minh phải dùng phương thức được thiết kế, tránh khóa tài khoản hoặc làm lộ secret.

### 11.2. Quyền JIT hết hạn trong lúc control plane lỗi

Chuẩn bị quyền có thời hạn ngắn phù hợp môi trường thử, ghi lại mốc cấp và hết hạn. Gây lỗi sao cho cửa sổ gián đoạn bao trùm mốc hết hạn.

Cần phân biệt ba trạng thái:

- PAM có còn cấp thao tác mới bằng quyền đó không?
- Credential đã phát hành còn được đích chấp nhận trong bao lâu?
- Phiên hiện hữu có bị chấm dứt theo chính sách không?

Một credential còn TTL tại đích có thể tiếp tục hoạt động dù control plane đã thu hồi bản ghi. Đây là đặc tính cần được ghi rõ và đánh giá theo thiết kế; không tự coi một nhãn “revoked” trên giao diện là bằng chứng thu hồi hiệu lực ở mọi nơi.

### 11.3. Gateway phiên mất trước khi upload recording xong

Tạo dấu mốc vô hại ở đầu, trước lỗi và sau khi kết nối lại để đối chiếu recording. Sau phục hồi, kiểm tra phần đã được lưu, phần còn ở buffer và cách nối các đoạn.

Nếu gateway mất cùng dữ liệu chỉ nằm trong bộ nhớ, bài kiểm thử phải ghi đúng khoảng mất và đánh giá theo hợp đồng. Không che khoảng trống bằng một file recording mới có cùng tên phiên.

Nếu chính sách yêu cầu dừng truy cập khi không bảo đảm recording, cần kiểm chứng điểm chặn và độ trễ chặn. Nếu được phép buffer trong một giới hạn, cần kiểm tra giới hạn đó, cảnh báo và hành vi khi buffer đầy.

### 11.4. Node cũ quay lại và chạy job trễ

Sau khi gỡ lỗi, node cũ có thể còn hàng đợi, lịch tác vụ hoặc bản sao trạng thái chưa cập nhật. Kiểm tra các job cũ có được nhận lại đúng thẩm quyền hay vô tình thực thi lần hai.

Dấu hiệu cần điều tra gồm rotation lặp, approval bị thực thi lại, quyền đã hết hạn được tạo lại, hoặc audit xuất hiện thao tác có thời điểm thực thi không khớp trạng thái hiện tại.

## 12. Ví dụ đọc timeline và đưa ra kết luận

Giả sử ca F02 có mục tiêu checkout phục hồi trong 60 giây và tạo phiên mới trong 90 giây:

| Thời điểm | Quan sát |
|---|---|
| 10:00:00 | Lỗi mất node A có hiệu lực |
| 10:00:02 | Probe checkout đầu tiên thất bại |
| 10:00:04 | Probe tạo phiên đầu tiên thất bại |
| 10:00:11 | Backend xác nhận vai trò phục vụ mới |
| 10:00:18 | Có một checkout thành công |
| 10:00:21 | Checkout lại xuất hiện lỗi |
| 10:00:26 | Bắt đầu cửa sổ checkout ổn định |
| 10:00:43 | Bắt đầu cửa sổ tạo phiên ổn định |
| 10:01:26 | Xác nhận đủ 60 giây ổn định của checkout |
| 10:01:43 | Xác nhận đủ 60 giây ổn định của tạo phiên |
| 10:03:00 | Gỡ lỗi, node A bắt đầu gia nhập lại |
| 10:04:10 | Đối soát hoàn tất, backlog về ngưỡng |

Theo định nghĩa của ca:

```text
Checkout recovery = 10:00:26 - 10:00:02 = 24 giay
New-session recovery = 10:00:43 - 10:00:04 = 39 giay
```

Hai ngưỡng thời gian đều đạt. Tuy nhiên, giả sử đối soát phát hiện một quyền JIT đã hết hạn vẫn cho phép mở phiên mới, ca vẫn không đạt về an toàn truy cập.

Báo cáo cũng cần ghi cửa sổ sai số do chu kỳ probe, thời điểm xác nhận cửa sổ ổn định và việc có hay không can thiệp thủ công. Không dùng mốc checkout thành công đơn lẻ lúc 10:00:18 để báo thời gian phục hồi thấp hơn thực tế.

## 13. Điều kiện dừng và xử lý khi ca không đạt

Dừng việc gây lỗi mới khi xuất hiện một trong các điều kiện đã chốt, chẳng hạn:

- Có cấp quyền trái chính sách.
- Nghi có hai thành phần cùng thực hiện thay đổi xung đột.
- Ảnh hưởng lan ra ngoài đích hoặc người dùng của ca.
- Không còn đường phục hồi đã kiểm tra.
- Gần chạm giới hạn buffer/recording đã đặt.
- Hết thời lượng lỗi hoặc vượt ngưỡng gián đoạn tối đa.

Dừng ca không đồng nghĩa tắt hết hệ thống hay chuyển ngược ngay lập tức. Người điều phối cần bảo toàn bằng chứng, đưa hệ thống về trạng thái an toàn theo runbook và xác định đường phục hồi phù hợp với trạng thái hiện tại.

Nếu dữ liệu giữa hai bên chưa rõ bên nào có thẩm quyền, không nối chúng lại hoặc ép promote chỉ để khôi phục nhanh. Giữ nguyên bằng chứng và dùng quy trình đối soát/DR của kiến trúc. Việc reset dữ liệu hoặc thay thành viên cụm là một thao tác phục hồi riêng, không phải cách “sửa” kết quả bài kiểm thử.

Một ca không đạt nên tạo ra hành động cụ thể: sửa readiness, bổ sung đối soát rotation, cải thiện retry, thay failure domain hoặc điều chỉnh hợp đồng phiên. Chạy lại đúng ca sau thay đổi, rồi mới mở rộng sang tổ hợp lỗi khác.

## 14. Những lỗi thiết kế kiểm thử thường gặp

| Cách làm | Vì sao kết luận không đủ | Cách cải thiện |
|---|---|---|
| Chỉ mở được trang đăng nhập | Chưa kiểm tra cấp quyền và đích thực tế | Dùng probe nghiệp vụ qua đường truy cập chuẩn |
| Chỉ kiểm tra dừng có kế hoạch | Bỏ sót trạng thái chưa ghi xong hoặc kết nối đứt đột ngột | Bổ sung ca lỗi đột ngột riêng |
| Chỉ kiểm tra tài khoản có quyền | Bỏ sót fail-open | Chạy kiểm tra từ chối xuyên suốt ca |
| Chỉ nhìn nhãn active/standby | Vai trò hiển thị chưa chứng minh đường phục vụ và thẩm quyền | Đối chiếu client, backend và hệ thống đích |
| Gửi lại rotation sau mọi timeout | Có thể đổi credential thêm lần nữa | Tra cứu hoặc đối soát giao dịch chưa xác định |
| Chỉ đo API sau chuyển đổi | Phiên và recording có thể đã mất | Đánh giá control plane và data plane riêng |
| Mất log thì coi là không có thao tác | Thiếu quan sát không chứng minh không xảy ra sự kiện | Đối chiếu nhiều nguồn, ghi chưa kết luận |
| Chạy tải rất thấp rồi suy rộng | Chưa biết node dự phòng chịu được tải phục hồi hay không | Thử tải đại diện và quan sát backlog |
| Tự giảm quorum để ca xanh | Thay đổi mô hình an toàn của hệ thống | Kiểm tra đúng giới hạn chịu lỗi đã thiết kế |
| Kết thúc ngay khi node cũ lên | Bỏ sót job lặp và trạng thái cũ | Theo dõi giai đoạn gia nhập lại và đối soát cuối |
| Tự động failback ngay | Có thể gây dao động và thêm gián đoạn | Failback theo ca có điều kiện riêng |

## 15. Mẫu báo cáo kết quả

Một báo cáo hữu ích phải cho phép người khác kiểm tra kết luận mà không cần hỏi lại người chạy ca.

```text
TEST_ID:
ENVIRONMENT:
CONFIGURATION_VERSION:
FAULT_TARGET_AND_METHOD:
EXECUTION_WINDOW:
WORKLOAD_AND_PROBE_INTERVALS:

BASELINE_RESULT:
IMPACT_TIME_PER_FLOW:
STABLE_RECOVERY_TIME_PER_FLOW:
RECOVERY_DURATION_PER_FLOW:
MEASUREMENT_UNCERTAINTY:
MANUAL_INTERVENTIONS:

ROLE_AND_FENCING_EVIDENCE:
AUTHORIZATION_INVARIANTS:
CREDENTIAL_RECONCILIATION:
JIT_AND_REVOCATION_RESULT:
EXISTING_SESSION_RESULT:
AUDIT_AND_RECORDING_RESULT:
OLD_NODE_REJOIN_RESULT:

ABORT_OR_ROLLBACK_ACTIONS:
CLEANUP_RESULT:
EVIDENCE_REFERENCES:
RESULT_PER_ACCEPTANCE_CRITERION:
UNRESOLVED_ITEMS:
OVERALL_RESULT:
```

Tham chiếu bằng chứng nên trỏ tới dữ liệu đã che thông tin nhạy cảm và có quyền truy cập phù hợp. Với audit/recording, lưu các định danh và cách chứng minh tính toàn vẹn nếu hệ thống hỗ trợ. Không đưa secret, token truy cập hoặc credential khẩn cấp vào báo cáo.

Phân biệt ba loại kết luận:

- **Đạt:** đủ bằng chứng cho mọi tiêu chí bắt buộc trong phạm vi ca.
- **Không đạt:** quan sát được ít nhất một vi phạm tiêu chí.
- **Chưa kết luận:** thiếu dữ liệu, lỗi tiêm chưa có hiệu lực hoặc baseline không hợp lệ.

“Chưa kết luận” không phải “đạt có điều kiện”. Nó chỉ ra cần bổ sung phép đo hoặc chạy lại ca.

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

Thiết kế một ca trên môi trường thử có một endpoint truy cập, cụm PAM dự phòng và một tài nguyên đích dành riêng:

1. Xác định thành phần nào có thể chuyển vai trò và dependency nào dùng chung.
2. Viết bốn bất biến: từ chối truy cập sai quyền, bảo toàn trạng thái credential, hết hạn JIT và truy nguyên audit.
3. Chọn một lỗi đột ngột vào thành phần đang phục vụ, kèm giới hạn thời gian.
4. Chạy đồng thời một probe được phép, một probe bị từ chối và một phiên hiện hữu.
5. Ghi timeline từ phía client, PAM và đích.
6. Đối soát giao dịch đã xác nhận và những giao dịch đang bay lúc lỗi.
7. Gỡ lỗi, kiểm tra node quay lại và hoàn tất cleanup.
8. Đánh giá từng tiêu chí bằng bằng chứng cụ thể.

Không cần bắt đầu bằng ca nhiều lỗi. Một ca đơn giản nhưng đo đủ quyền, credential, phiên và audit có giá trị hơn một diễn tập lớn không đối soát được.

### Câu hỏi tự kiểm tra

**1. Vì sao một lần checkout thành công sau lỗi chưa chứng minh đã phục hồi?**

Vì thành công đơn lẻ có thể xen kẽ lỗi; ca cần một cửa sổ ổn định và phải kiểm tra đúng luồng nghiệp vụ, quyền truy cập và trạng thái dữ liệu.

**2. Rotation timeout có thể được phát lại ngay không?**

Không thể kết luận chỉ từ timeout. Thao tác có thể đã đổi credential ở đích. Cần tra cứu hoặc đối soát theo ID và cơ chế chống trùng được hỗ trợ.

**3. Mất gateway nhưng phiên bị ngắt có luôn là failover thất bại không?**

Không. Kết quả phụ thuộc hợp đồng của kiến trúc. Nếu thiết kế yêu cầu đóng có kiểm soát, truy nguyên recording và kết nối lại theo chính sách, phải đánh giá các điều kiện đó.

**4. Dịch vụ phục hồi trong RTO nhưng cấp quyền sai có đạt không?**

Không. Khả dụng và các bất biến an toàn là những tiêu chí độc lập, đều phải đạt.

**5. Tại sao cần kiểm tra sau khi node cũ quay lại?**

Vì node cũ có thể mang trạng thái, kết nối và job trễ. Giai đoạn gia nhập lại có thể gây thực thi trùng, phục vụ dữ liệu cũ hoặc chuyển vai trò qua lại.

**6. Bài kiểm thử mất toàn bộ quorum có nhất thiết phải tự phục hồi không?**

Không. Nếu vượt giới hạn chịu lỗi, kết quả mong đợi có thể là dừng ghi an toàn và chuyển sang quy trình phục hồi được thiết kế. Không sửa quorum tùy tiện để biến ca đó thành một lần failover thành công.

