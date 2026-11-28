# Tampering audit trail: phát hiện can thiệp dấu vết kiểm toán trong PAM

Một hệ thống PAM có thể ghi nhận đầy đủ thao tác quản trị nhưng vẫn để lại khoảng trống điều tra nếu người có quyền cao có thể sửa, xóa hoặc làm gián đoạn chính các bản ghi đó. Khi nguồn log bị can thiệp, dashboard yên lặng không còn đồng nghĩa với hệ thống an toàn.

Trong chương Threat detection, bài học này tập trung vào việc nhận diện hành vi can thiệp audit trail và phân biệt nó với lỗi thu thập thông thường. Phạm vi gồm tài khoản quản trị, tài khoản dịch vụ, vault, cơ chế JIT/JEA, phiên đặc quyền và các hệ thống đích nhạy cảm. Mục tiêu là giữ được bằng chứng đủ tin cậy để xác định quyền nào đã được sử dụng, bởi ai, trong điều kiện nào và có khoảng trống nào chưa giải thích được.

## 1. Audit trail là gì và tampering bao gồm những gì?

**Audit trail** là chuỗi bằng chứng giúp tái dựng một hoạt động. Trong PAM, chuỗi đó thường bắt đầu trước khi người dùng đăng nhập vào máy đích và kết thúc sau khi quyền được thu hồi:

1. Người dùng yêu cầu quyền đặc biệt và cung cấp lý do.
2. Chính sách hoặc người phê duyệt cho phép một phạm vi và thời hạn.
3. PAM phát hành quyền JIT, cấp phiên hoặc cho phép truy xuất credential.
4. Người dùng thực hiện thao tác trên hệ thống đích.
5. PAM và hệ thống đích ghi nhận diễn biến.
6. Quyền hết hạn hoặc bị thu hồi; credential được xử lý theo chính sách.
7. Bằng chứng được chuyển tới nơi lưu trữ và hệ thống phát hiện.

Một bản ghi đăng nhập đơn lẻ không thể thay thế toàn bộ chuỗi trên. Nó có thể cho biết tài khoản nào đăng nhập, nhưng chưa chắc cho biết người thực tế đứng sau tài khoản dùng chung, phê duyệt liên quan hoặc thao tác trong phiên.

**Tampering audit trail** là hành vi làm thay đổi giá trị chứng minh của chuỗi bằng chứng. Hành vi này rộng hơn việc sửa nội dung một dòng log.

| Dạng can thiệp | Ví dụ trong PAM | Giá trị bằng chứng bị ảnh hưởng |
|---|---|---|
| Sửa nội dung | Thay danh tính người yêu cầu hoặc kết quả thực thi | Độ chính xác, khả năng quy trách nhiệm |
| Xóa hoặc cắt đuôi | Một đoạn recording hoặc phần cuối chuỗi sự kiện biến mất | Tính đầy đủ |
| Ngừng tạo log | Tắt cấu hình ghi sự kiện quản trị | Khả năng quan sát tại nguồn |
| Chặn vận chuyển | Ngắt forwarder hoặc thay tuyến gửi log | Khả năng quan sát ở trung tâm |
| Chèn hoặc phát lại | Gửi lại sự kiện cũ như một sự kiện mới | Tính mới, thứ tự, số lượng |
| Làm sai thời gian | Thời gian máy đích lệch mạnh so với bộ thu | Khả năng ghép timeline |
| Đổi chính sách lưu trữ | Rút ngắn retention hoặc cấp quyền xóa cho người vận hành | Khả năng bảo tồn |
| Can thiệp bộ phát hiện | Tắt rule hoặc tạo ngoại lệ bao trùm tài khoản quản trị | Khả năng phát cảnh báo |

Không phải mọi tình huống trên đều chứng minh có tấn công. Forwarder có thể dừng vì lỗi đĩa, recording có thể thiếu vì gián đoạn mạng và thời gian có thể lệch do cấu hình. Phát hiện phải chỉ ra điều quan sát được, sau đó dùng bằng chứng bổ sung để xác định nguyên nhân.

### Phân biệt “không có sự kiện” với “không có hoạt động”

Giả sử SIEM không nhận được thao tác từ một máy chủ trong 20 phút. Có ít nhất ba khả năng:

- Không có thao tác nào thuộc phạm vi cần ghi.
- Có thao tác, nhưng cơ chế tạo hoặc chuyển log bị lỗi.
- Có thao tác, và một chủ thể cố tình làm mất dấu vết.

Chỉ nhìn vào số lượng log bằng không không phân biệt được ba khả năng này. Cần biết máy có còn hoạt động, phiên PAM có còn mở, nguồn log có phát heartbeat và bộ thu có đang nhận dữ liệu từ các nguồn khác hay không.

## 2. Xác định điều cần bảo vệ trước khi xây rule

Một audit trail đáng tin phải đáp ứng nhiều thuộc tính riêng biệt.

| Thuộc tính | Câu hỏi cần trả lời | Giới hạn cần nhớ |
|---|---|---|
| Tính toàn vẹn | Bản ghi có bị thay đổi sau mốc bảo vệ không? | Không chứng minh nội dung ban đầu là đúng |
| Tính xác thực nguồn | Bằng chứng đến từ chủ thể hoặc thiết bị nào? | Nguồn đã bị chiếm quyền có thể tạo dữ liệu sai |
| Tính đầy đủ | Những sự kiện bắt buộc có bị thiếu không? | Log tự nó khó chứng minh sự kiện chưa từng được tạo |
| Tính thứ tự | Có thể xác định thứ tự trong một luồng không? | Nhiều nguồn không tự nhiên có một thứ tự toàn cục |
| Tính mới | Sự kiện có bị phát lại hoặc gửi quá muộn không? | Dữ liệu đến trễ có thể là backfill hợp lệ |
| Khả năng bảo tồn | Bằng chứng có còn đọc được trong thời gian cần thiết không? | Hash hợp lệ không giúp khôi phục một file đã mất |
| Khả năng quy trách nhiệm | Tài khoản kỹ thuật có gắn được với người và yêu cầu quyền không? | Tài khoản dùng chung cần lớp liên kết danh tính |

Ví dụ, một file log có hash trùng khớp với hash vừa được tính lại chỉ cho thấy hai phép tính đang nhìn cùng một nội dung. Nếu kẻ can thiệp có thể sửa cả file và nơi lưu hash, phép so sánh đó không tạo ra một mốc tin cậy độc lập.

Ngược lại, hash của file đã được ghi nhận trước đó tại một nơi độc lập, được bảo vệ tốt, có thể giúp phát hiện thay đổi về sau. Nó vẫn không chứng minh hệ thống đích đã ghi đủ mọi hành động trước thời điểm tạo hash.

## 3. Threat model: ai có thể tác động tới bằng chứng?

Trong PAM, tài khoản có đặc quyền thường có khả năng ảnh hưởng tới hệ điều hành, dịch vụ nền hoặc cấu hình mạng. Vì vậy không nên đặt toàn bộ niềm tin vào log nằm trên chính máy mà tài khoản đó quản trị.

Các chủ thể cần xem xét gồm:

- Người dùng có quyền quản trị máy đích.
- Người quản trị nền tảng PAM hoặc vault.
- Tài khoản dịch vụ của agent, forwarder và connector.
- Người vận hành collector, SIEM và kho recording.
- Người quản lý khóa ký, khóa mã hóa và chính sách retention.
- Một kẻ tấn công đã chiếm được một trong các danh tính trên.

Mỗi chủ thể có phạm vi tác động khác nhau. Người quản trị máy đích có thể thay đổi log cục bộ nhưng chưa chắc sửa được bản sao đã gửi sang kho độc lập. Người vận hành kho tập trung có thể tác động tới bản sao trung tâm nhưng chưa chắc sửa được checkpoint đã gửi tới một miền quản trị khác.

### Những ranh giới tin cậy quan trọng

~~~text
Người dùng / tài khoản dịch vụ
             |
             v
PAM: yêu cầu quyền -> phê duyệt -> cấp quyền / mở phiên
             |                          |
             |                          v
             |                    Hệ thống đích
             |                          |
             v                          v
      Audit của PAM              Log tại nguồn
             \                          /
              \                        /
               v                      v
                 Collector / pipeline
                         |
                  +------+------+
                  |             |
                  v             v
             SIEM / rule   Kho bằng chứng
                                |
                                v
                    Checkpoint độc lập
~~~

Sơ đồ thể hiện các đường bằng chứng, không khẳng định mọi hệ thống PAM đều có cùng cơ chế recording hoặc cùng mức bảo vệ. Khi triển khai, cần chỉ rõ thành phần nào do ai quản trị và tài khoản nào có thể thay đổi từng thành phần.

### Phân tách nhiệm vụ để giảm điểm mù

Một thiết kế có ích là tách quyền quản trị máy đích, quyền cấu hình thu thập, quyền sửa rule và quyền quản lý retention. Tài khoản ghi log chỉ cần quyền ghi phù hợp; tài khoản đọc phục vụ điều tra không cần quyền xóa.

Tuy nhiên, phân tách vai trò trên giấy không đủ nếu cùng một tài khoản quản trị cấp cao có thể tự cấp lại mọi quyền. Cần xem cả đường nâng quyền, cơ chế break-glass, quyền quản trị khóa và nhật ký thay đổi quyền ở lớp điều khiển.

## 4. Thu thập bằng chứng để có thể phát hiện sự can thiệp

### 4.1. Đừng chỉ thu log hành động của người dùng

Ngoài sự kiện truy cập đặc quyền, cần thu cả các sự kiện cho biết hệ thống ghi nhận có đang hoạt động đúng hay không:

| Nhóm bằng chứng | Trường hợp sử dụng |
|---|---|
| Yêu cầu quyền, phê duyệt, cấp và thu hồi JIT | Đối chiếu phạm vi quyền với hoạt động thực tế |
| Mở, đóng và trạng thái phiên PAM | Xác định lúc nào đáng lẽ phải có dữ liệu phiên |
| Metadata recording và manifest | Kiểm tra sự tồn tại, số đoạn và hash của recording |
| Truy xuất, thay đổi và luân chuyển credential | Ghép vòng đời bí mật với phiên hoặc ứng dụng |
| Khởi động, dừng, lỗi và heartbeat của agent | Phân biệt khoảng yên lặng với mất khả năng quan sát |
| Thay đổi cấu hình audit, route, filter và rule | Phát hiện can thiệp vào đường thu thập hoặc phát hiện |
| Hoạt động quản trị kho lưu trữ và khóa | Theo dõi khả năng thay đổi hoặc xóa bằng chứng |
| Mốc thời gian tiếp nhận ở collector | Nhận diện độ trễ và chênh lệch thời gian nguồn |

Heartbeat chỉ chứng minh thành phần phát heartbeat đang gửi được tín hiệu đó. Một agent vẫn có thể gửi heartbeat trong khi bộ thu sự kiện nghiệp vụ bên trong nó bị lỗi. Do đó cần theo dõi thêm checkpoint xử lý, độ dài hàng đợi và sự kiện kiểm thử khi phù hợp.

### 4.2. Chuẩn hóa danh tính mà không đánh mất nguồn gốc

Các trường hữu ích thường gồm:

~~~json
{
  "event_id": "evt-lab-9201",
  "source_id": "srv-ledger-01",
  "stream_id": "audit-admin",
  "stream_epoch": "epoch-lab-07",
  "sequence": 9201,
  "event_time": "2026-11-27T03:00:12Z",
  "ingest_time": "2026-11-27T03:00:14Z",
  "actor_id": "user-lab-a",
  "effective_account": "admin-ledger",
  "pam_session_id": "ps-lab-0042",
  "access_request_id": "req-lab-0042",
  "action": "audit.configuration.changed",
  "result": "success",
  "change_reference": null,
  "collector_id": "collector-lab-02",
  "schema_version": "lab-1"
}
~~~

Đây là schema minh họa, không phải định dạng chuẩn của một sản phẩm cụ thể. Trong hệ thống thật, cần quy định rõ đơn vị sinh từng trường và mức tin cậy của nó.

- **actor_id** biểu diễn người hoặc workload gốc nếu xác định được.
- **effective_account** là tài khoản được dùng trên hệ thống đích.
- **pam_session_id** nối tới phiên đặc quyền, nếu hoạt động đi qua phiên.
- **access_request_id** nối tới yêu cầu và phạm vi cấp quyền.
- **stream_epoch** phân biệt các vòng đời của cùng một luồng, chẳng hạn sau khi bộ sinh sequence khởi tạo lại.

Không phải mọi hành động quản trị đều có phiên tương tác. Một job tự động luân chuyển credential có thể cần identity của workload, job ID và deployment ID thay cho session ID.

Giữ bản ghi nguồn cùng metadata chuẩn hóa hoặc tham chiếu tới bản gốc. Nếu pipeline chỉ giữ dữ liệu đã biến đổi, lỗi parser có thể làm mất chi tiết cần thiết để điều tra.

## 5. Ba lớp phát hiện cần phối hợp

### 5.1. Phát hiện thay đổi cơ chế ghi và bảo vệ log

Các thay đổi đáng quan sát gồm:

- Tắt một nguồn audit hoặc giảm phạm vi sự kiện được ghi.
- Thêm filter loại bỏ hoạt động của tài khoản đặc quyền.
- Đổi đích gửi log sang một địa chỉ không nằm trong danh sách cho phép.
- Dừng agent hoặc đổi identity chạy dịch vụ thu thập.
- Sửa retention, chính sách bất biến hoặc quyền xóa của kho bằng chứng.
- Thay đổi cấu hình ký, khóa ký hoặc quyền sử dụng khóa.
- Tắt rule giám sát chính các thay đổi trên.

Cần theo dõi cả **ý định thay đổi** và **trạng thái có hiệu lực**. Một yêu cầu bị từ chối có giá trị khác với thay đổi thành công. Một bản ghi “configuration updated” cũng chưa bảo đảm đường thu thập đã hoạt động sau thay đổi.

Đối với thay đổi có kế hoạch, đối chiếu người thực hiện, tài nguyên, loại thay đổi và thời gian với change reference. Một mã ticket xuất hiện trong log không tự động chứng minh ticket hợp lệ hoặc đã phê duyệt đúng phạm vi.

### 5.2. Phát hiện khoảng trống, gián đoạn và bất thường vận chuyển

Một số tín hiệu thường gặp:

- Nguồn đang hoạt động nhưng heartbeat quá hạn.
- Phiên đặc quyền vẫn mở, nhưng recording không có checkpoint mới.
- Log nghiệp vụ vẫn đến từ máy đích, trong khi log audit đặc quyền ngừng.
- Có khoảng thiếu sequence sau khi đã hết thời gian chờ dữ liệu đến trễ.
- Hàng đợi gửi log tăng liên tục, nhưng không có tiến triển ở checkpoint.
- Lưu lượng tiếp nhận giảm đồng thời với thay đổi firewall hoặc cấu hình agent.
- Tỷ lệ sự kiện bị parser loại bỏ tăng ngay sau một phiên quản trị.

Một ngưỡng im lặng phải phù hợp với nguồn. Máy ít hoạt động không thể dùng chung ngưỡng số sự kiện với máy chủ đang có hàng trăm phiên. Heartbeat có chu kỳ rõ thường giúp xác định kỳ vọng tốt hơn chỉ dùng lưu lượng nghiệp vụ.

**Sequence chỉ có ý nghĩa trong hợp đồng của luồng.** Nếu nhà sản xuất cho phép bỏ số, dùng một bộ đếm chung cho nhiều loại sự kiện rồi lọc bớt, hoặc chỉ xuất mẫu, khoảng nhảy số không tự động là mất log. Rule phải biết số nào đáng lẽ phải xuất hiện trong tập đang kiểm tra.

Khi collector nhận sự kiện không đúng thứ tự, nên giữ một cửa sổ chờ. Trong cửa sổ đó, trạng thái là “chưa thấy” thay vì khẳng định “đã bị xóa”. Hết cửa sổ mà không có dữ liệu bổ sung thì nâng thành khoảng thiếu chưa giải thích được.

### 5.3. Phát hiện sai lệch toàn vẹn và mâu thuẫn giữa các nguồn

Các tín hiệu mạnh hơn về sự thay đổi bằng chứng gồm:

- Cùng một event ID hoặc cùng vị trí trong luồng nhưng có hai payload khác nhau.
- Hash recording khác với hash đã được ghi nhận tại mốc tin cậy.
- Chữ ký không hợp lệ, khóa ký không được chấp nhận hoặc checkpoint không nối được.
- Kho bằng chứng ghi nhận thao tác xóa đối với đối tượng còn thuộc phạm vi cần giữ.
- PAM ghi phiên kéo dài 30 phút nhưng manifest recording chỉ bao phủ phần đầu, không có giải thích kỹ thuật.
- Hệ thống đích xác nhận một thao tác quản trị, nhưng chuỗi PAM liên quan thiếu sự kiện vốn được yêu cầu phải có.

Một sự kiện trùng hoàn toàn có thể do retry hợp lệ. Cùng ID nhưng nội dung khác là tình huống khác, cần phân biệt rõ. Đồng thời, xung đột vẫn có thể do lỗi cấp ID hoặc lỗi chuyển đổi; cảnh báo toàn vẹn chưa đồng nghĩa đã xác định được thủ phạm.

## 6. Hash, chữ ký và checkpoint giúp được gì?

### 6.1. Hash từng đối tượng

Với một recording hoặc batch log, tính hash trên đúng dãy byte được lưu và ghi lại định danh đối tượng, kích thước, thuật toán cùng mốc tạo. Khi đối tượng được đọc lại, so sánh với giá trị hash đã được bảo vệ.

Nếu file được nén hoặc mã hóa lại, byte thay đổi dù nội dung diễn giải có thể tương đương. Thiết kế phải quy định hash áp dụng cho lớp nào: bản gốc, bản nén, bản mã hay một biểu diễn chuẩn hóa.

Không tùy tiện bỏ trường, đổi encoding hoặc sắp xếp lại JSON sau khi đã định nghĩa đối tượng được băm. Nếu dùng canonicalization, quy tắc phải cố định và có phiên bản.

### 6.2. Chuỗi hash

Một mô hình minh họa có thể biểu diễn bằng:

~~~text
H_i = HASH(ENCODE(
    domain_tag,
    stream_id,
    stream_epoch,
    sequence_i,
    H_previous,
    canonical_event_i
))
~~~

ENCODE phải là cách mã hóa không nhập nhằng, chẳng hạn dùng độ dài trường hoặc một định dạng cấu trúc đã xác định. Không ghép chuỗi tùy ý bằng dấu phân cách có thể xuất hiện trong dữ liệu.

Nếu sửa một sự kiện trong đoạn đã được bảo vệ, quan hệ chuỗi có thể không còn khớp. Nhưng nếu kẻ can thiệp kiểm soát toàn bộ đoạn chưa được neo và có thể tính lại tất cả hash, chuỗi hash riêng lẻ không ngăn được việc viết lại lịch sử.

Cắt bỏ phần cuối cũng có thể để lại một chuỗi ngắn hơn nhưng vẫn tự nhất quán. Muốn nhận biết, cần biết trước một mốc cuối hoặc một checkpoint mới hơn đáng lẽ phải tồn tại.

### 6.3. Chữ ký và checkpoint độc lập

Checkpoint có thể chứa định danh luồng, epoch, sequence cuối, hash cuối và thời điểm. Nó được ký hoặc được ghi nhận ở một nơi có ranh giới quản trị khác.

Cơ chế này hữu ích khi:

- Bộ xác minh biết checkpoint hoặc khóa công khai nào là đáng tin.
- Khóa ký được quản lý tách khỏi tác nhân có thể sửa log.
- Việc xoay khóa và thu hồi khóa có lịch sử rõ ràng.
- Có quy trình phát hiện checkpoint bị thiếu hoặc không còn cập nhật.
- Bản thân nơi lưu checkpoint được bảo vệ và giám sát.

Chữ ký hợp lệ cho biết dữ liệu phù hợp với chữ ký dưới khóa được kiểm tra. Nó không chứng minh nguồn đã quan sát đúng thực tế, cũng không bảo đảm khóa chưa bị lạm dụng. Nếu một máy bị chiếm quyền vẫn có quyền yêu cầu ký dữ liệu giả, chữ ký không khắc phục được sự thiếu tin cậy của dữ liệu tại nguồn.

### 6.4. Lưu trữ bất biến và bản sao độc lập

Một cơ chế bất biến hoặc write-once có thể hạn chế sửa, xóa đối tượng sau khi ghi, tùy cấu hình và phạm vi bảo vệ thực tế. Cần kiểm tra cả dữ liệu, metadata, chính sách retention và các quyền ở lớp quản trị.

Bản sao độc lập giúp so sánh và phục hồi khi một miền bị ảnh hưởng. Tuy nhiên, hai bản sao cùng lấy dữ liệu đã bị lược bỏ tại nguồn đều có thể thiếu giống nhau. Bảo vệ sau khi nhận và phát hiện mất sự kiện trước khi nhận là hai bài toán cần giải quyết riêng.

## 7. Xây một rule tương quan cho phiên đặc quyền

Xét tình huống một phiên quản trị mở tới máy chủ thanh toán. Trong phiên xuất hiện thay đổi cấu hình audit, sau đó nguồn ngừng gửi dữ liệu, trong khi các tín hiệu khác cho thấy máy vẫn đang phục vụ.

Rule nên mô tả rõ điều kiện thay vì chỉ tìm một từ khóa “log cleared”.

### 7.1. Điều kiện và bằng chứng

Một rule có thể sử dụng các dữ kiện:

1. Có phiên PAM đang hoạt động tới một tài sản nhạy cảm.
2. Có thay đổi thành công liên quan tới cơ chế audit hoặc đường chuyển log.
3. Thay đổi không khớp một phê duyệt đang có hiệu lực sau khi đối chiếu phạm vi.
4. Trong khoảng thời gian tiếp theo, nguồn vi phạm kỳ vọng về heartbeat hoặc checkpoint.
5. Một nguồn độc lập cho thấy tài sản vẫn hoạt động.

Các khoảng thời gian và mức nghiêm trọng phải được chọn theo chu kỳ heartbeat, độ trễ pipeline, mức độ nhạy cảm của tài sản và khả năng gián đoạn hợp lệ. Những con số trong bài tập phía sau chỉ là tham số mô phỏng.

### 7.2. Pseudocode phát hiện

~~~text
ON successful_audit_configuration_change(change):
    session = lookup_session(change.pam_session_id)

    IF session is absent:
        emit finding("audit-change-without-session-context", change)
        continue investigation through workload and break-glass context

    approval = find_matching_approved_change(
        actor = change.actor_id,
        target = change.source_id,
        action_scope = change.action,
        change_time = change.event_time
    )

    open observation for:
        target = change.source_id
        session = session.id
        configuration_change = change.event_id
        approval_result = approval
        deadline = configured_observation_deadline

ON observation_deadline(observation):
    source_state = evaluate_collection_health(observation.target)
    activity = read_independent_activity(observation.target)

    IF source_state violates expected collection behavior:
        emit finding(
            "privileged-audit-observation-gap",
            session = observation.session,
            evidence = configuration_change + source_state + activity,
            approval_result = observation.approval_result,
            confidence = assessed_from_available_evidence
        )
~~~

Đây là logic minh họa, không phải cú pháp chạy trực tiếp trên SIEM. Tra cứu phê duyệt thất bại vì dịch vụ phê duyệt không truy cập được phải được biểu diễn là **chưa xác định**, không tự coi là “không có phê duyệt”.

Không nên bỏ mọi cảnh báo chỉ vì thay đổi đã được phê duyệt. Một thay đổi hợp lệ vẫn có thể gây mất dữ liệu ngoài phạm vi dự kiến. Phê duyệt là ngữ cảnh để đánh giá, còn sức khỏe thu thập cần được kiểm tra riêng.

### 7.3. Dữ liệu cần gắn vào cảnh báo

Một cảnh báo có ích cho người điều tra cần chứa:

- Tài sản, mức độ nhạy cảm và chủ sở hữu.
- Người dùng gốc, tài khoản hiệu lực, session ID hoặc job ID.
- Yêu cầu quyền, thời hạn JIT và phạm vi phê duyệt.
- Sự kiện thay đổi cấu hình và kết quả thực thi.
- Mốc dữ liệu tốt cuối cùng, mốc đầu tiên phát hiện thiếu và thời gian tiếp nhận.
- Tình trạng collector, hàng đợi, parser và các nguồn độc lập.
- Checkpoint hoặc tham chiếu đối tượng bằng chứng liên quan.
- Điều đã xác minh, điều còn suy luận và những dữ liệu chưa có.

Tránh đưa credential, token hoặc nội dung bí mật từ phiên vào cảnh báo. Cảnh báo nên dùng tham chiếu có kiểm soát tới bằng chứng gốc; quyền đọc recording vẫn cần được giới hạn.

## 8. Ví dụ timeline và cách diễn giải

Các thời điểm dưới đây dùng UTC và thuộc một tình huống giả lập:

| Thời điểm | Quan sát | Diễn giải ban đầu |
|---|---|---|
| 03:00:00 | PAM mở phiên ps-lab-0042 với JIT còn hiệu lực | Có hoạt động đặc quyền được phép trong một phạm vi |
| 03:02:10 | Máy đích ghi thay đổi audit thành công | Cơ chế quan sát đã bị thay đổi |
| 03:02:13 | Collector nhận được bản ghi thay đổi | Bản ghi đã rời máy đích trước khi có khoảng trống |
| 03:03:00 | Đây là heartbeat cuối cùng được nhận | Mốc tốt cuối cùng của tín hiệu sức khỏe này |
| 03:06:00 | Heartbeat vượt thời gian chờ đã cấu hình | Có khoảng thiếu quan sát cần kiểm tra |
| 03:06:20 | Tín hiệu ứng dụng độc lập vẫn xác nhận hoạt động | Không thể giải thích ngay bằng việc máy đã tắt |
| 03:08:00 | Phiên PAM vẫn còn mở | Khoảng thiếu trùng với thời gian có quyền quản trị |
| 03:12:00 | Agent hoạt động trở lại và gửi dữ liệu tồn | Cần kiểm tra mức bao phủ, không đóng cảnh báo ngay |

Từ timeline này có thể kết luận rằng có thay đổi audit và một khoảng thiếu quan sát liên quan về thời gian. Chưa thể kết luận người dùng đã xóa log hoặc thực hiện hành vi trái phép khác.

Khi dữ liệu tồn được gửi lại, cần kiểm tra xem nó bao phủ toàn bộ khoảng thiếu không, có sequence xung đột không và các mốc thời gian có nhất quán không. Việc collector nhận log trở lại không tự khôi phục những sự kiện chưa từng được tạo.

Nếu còn thiếu dữ liệu, báo cáo phải ghi rõ phạm vi chưa quan sát được thay vì suy đoán rằng không có thao tác trong khoảng đó.

## 9. Quy trình triage và phản ứng

### Bước 1: xác minh đường thu thập

Kiểm tra tình trạng collector, hàng đợi, lỗi parser, lưu lượng từ các nguồn khác và sự cố mạng đã biết. Xác định sự gián đoạn chỉ ảnh hưởng một nguồn hay cả một nhóm.

Nếu một collector bị lỗi trên diện rộng, đó vẫn là vấn đề cần xử lý, nhưng bằng chứng chưa chỉ ra một người dùng đặc quyền cụ thể đã can thiệp. Không gắn kết luận danh tính chỉ từ việc họ có phiên mở cùng thời điểm.

### Bước 2: bảo tồn bằng chứng đang có

Ghi lại các bản sao, checkpoint, metadata và trạng thái cấu hình liên quan bằng quy trình thu thập được kiểm soát. Tính hash cho bản thu thập và lưu lịch sử người truy cập, thời điểm, nguồn cùng phép biến đổi đã thực hiện.

Ưu tiên dữ liệu dễ mất như hàng đợi đang tồn, trạng thái agent, metadata phiên và thông tin phiên đang hoạt động. Không tùy tiện khởi động lại toàn bộ thành phần trước khi đánh giá ảnh hưởng tới dữ liệu chưa được gửi.

Một hash được tạo lúc thu thập chỉ giúp chứng minh bản thu thập không đổi từ mốc đó; nó không chứng minh dữ liệu chưa bị sửa trước khi thu thập.

### Bước 3: đối chiếu quyền, thay đổi và hoạt động

Kiểm tra yêu cầu quyền JIT, phê duyệt, change reference, break-glass, hoạt động tự động và sự kiện từ hệ thống đích. Xác định ai có khả năng sửa từng lớp bằng chứng.

Đối chiếu cả thời gian nguồn và thời gian tiếp nhận. Khi có độ lệch thời gian, biểu diễn timeline bằng khoảng bất định hoặc quan hệ trước/sau đáng tin, thay vì ép mọi sự kiện vào một thứ tự chính xác giả tạo.

### Bước 4: giới hạn quyền theo mức độ tin cậy

Nếu bằng chứng cho thấy nguy cơ đang tiếp diễn, có thể cần kết thúc phiên, thu hồi JIT, tạm dừng identity bị ảnh hưởng hoặc chặn một đường quản trị theo thẩm quyền vận hành đã xác định.

Việc thay credential hoặc vô hiệu hóa tài khoản dịch vụ phải tính đến phụ thuộc ứng dụng và khả năng giữ dịch vụ. Không mặc định một thao tác luân chuyển credential sẽ tự chấm dứt mọi phiên đã mở hoặc mọi token đã cấp.

### Bước 5: phục hồi quan sát và kiểm tra mức bao phủ

Khôi phục cấu hình thu thập đáng tin, kiểm tra quyền ghi và quyền đọc ở kho bằng chứng, xác nhận heartbeat lẫn luồng sự kiện thực tế đã hoạt động. Nếu có dữ liệu tồn, nhập lại với provenance rõ và giữ nguyên thời gian nguồn.

Không tạo các bản ghi giả để lấp khoảng thiếu. Nếu bổ sung một chú thích điều tra, đánh dấu nó là dữ liệu bổ sung, không trộn thành sự kiện gốc của hệ thống đích.

### Bước 6: kết luận với giới hạn bằng chứng

Có thể phân loại kết quả thành lỗi vận hành, thay đổi được phê duyệt, can thiệp đáng ngờ chưa đủ chứng cứ hoặc can thiệp đã được xác minh. Kèm phạm vi dữ liệu thiếu và những giả thuyết đã được kiểm tra.

Điều kiện đóng cảnh báo không chỉ là “log đã chạy lại”. Cần biết nguyên nhân đã được giải thích tới mức nào, khoảng thiếu đã được đánh giá ra sao và quyền gây ra rủi ro có còn tồn tại không.

## 10. Thiết kế ngoại lệ và giảm false positive

Các tình huống hợp lệ thường gây tín hiệu giống tampering:

| Tình huống | Tín hiệu dễ nhầm | Cách phân biệt |
|---|---|---|
| Bảo trì agent | Dừng dịch vụ và thiếu heartbeat | Phạm vi bảo trì, thời lượng thực tế, phiên bản và kiểm tra sau khôi phục |
| Nghẽn mạng | Dữ liệu đến trễ, sequence đảo thứ tự | Hàng đợi, độ trễ tiếp nhận, dữ liệu backfill |
| Máy được tạo lại | Sequence về giá trị ban đầu | Identity tài sản và epoch mới có bằng chứng vòng đời |
| Retry vận chuyển | Event ID lặp | Nội dung và định danh sự kiện giống nhau |
| Xoay file hoặc tách batch | Tên file thay đổi | Manifest và tính liên tục logic của luồng |
| Đồng bộ thời gian | Timestamp có bước nhảy | Log thay đổi thời gian và mốc tiếp nhận độc lập |
| Thay parser | Số sự kiện hợp lệ giảm | Lỗi phân tích, schema version và bản nguồn còn giữ |

Ngoại lệ nên có chủ sở hữu, tài sản, hành động, thời gian hết hạn và lý do. Không dùng một ngoại lệ vô thời hạn cho toàn bộ nhóm quản trị hoặc toàn bộ tài khoản break-glass.

Một thiết kế thực tế có thể hạ mức cảnh báo do bảo trì đã xác nhận nhưng vẫn giữ sự kiện, tiếp tục đo khoảng thiếu và phát cảnh báo nếu vượt cửa sổ cho phép. Việc im cảnh báo không nên xóa bằng chứng nền.

## 11. Bài thực hành bằng dữ liệu tổng hợp

Bài thực hành này dùng bản ghi giả lập. Không cần tắt audit, xóa log, sửa recording thật hoặc tác động tới máy đang vận hành.

### 11.1. Hợp đồng luồng của phòng lab

Giả sử một luồng có định danh:

~~~text
source_id = srv-lab-01
stream_id = privileged-audit
stream_epoch = epoch-lab-a
~~~

Trong lab, mỗi sự kiện của luồng được đánh số liên tiếp, không lọc bớt, không lấy mẫu và không dùng chung bộ đếm với luồng khác. Collector chấp nhận sự kiện đến trễ trong cửa sổ đã định nghĩa. Đây là các giả định phục vụ bài tập; không được mang nguyên sang một nguồn sản xuất chưa xác minh hợp đồng.

Có một checkpoint cuối sequence 103 được giữ ở nơi độc lập. Lab không cung cấp hash hoặc chữ ký thật, vì vậy chỉ kiểm tra logic phát hiện, không đánh giá một cơ chế mật mã.

### 11.2. Tập dữ liệu gốc

~~~json
[
  {"event_id":"e101","sequence":101,"action":"session.opened","session":"s-lab-1","result":"success"},
  {"event_id":"e102","sequence":102,"action":"configuration.read","session":"s-lab-1","result":"success"},
  {"event_id":"e103","sequence":103,"action":"session.closed","session":"s-lab-1","result":"success"}
]
~~~

Tạo các biến thể trên bản sao dữ liệu tổng hợp khi triển khai bài tập:

| Biến thể | Dữ liệu quan sát | Kết quả mong đợi |
|---|---|---|
| A: thiếu giữa | Nhận 101 và 103; hết cửa sổ chờ vẫn không có 102 | Khoảng thiếu 102 theo hợp đồng lab |
| B: retry | Nhận 101, 102, 102, 103; hai bản 102 giống hệt | Trùng do vận chuyển; không suy ra sửa nội dung |
| C: xung đột | Có hai e102 với action khác nhau | Xung đột nội dung ở cùng vị trí sự kiện |
| D: cắt đuôi | Chỉ còn 101, 102; có checkpoint độc lập đã xác nhận tới 103 | Thiếu phần cuối so với mốc đã biết |
| E: đến trễ | Nhận 101, 103 rồi 102 trong cửa sổ chờ | Khoảng thiếu tạm thời đã được dữ liệu đến trễ bù |
| F: epoch mới | Sequence khởi tạo lại với epoch mới được xác minh | Luồng mới; không nối tùy tiện vào epoch cũ |

Ở biến thể D, nếu không có checkpoint hoặc kỳ vọng độc lập, việc chỉ nhìn tập 101 và 102 không đủ chứng minh sự kiện 103 từng tồn tại. Đây là giới hạn quan trọng của mọi kiểm tra tự nhất quán.

### 11.3. Logic kiểm tra mẫu

~~~text
FOR each incoming event:
    key = (source_id, stream_id, stream_epoch, sequence)

    IF key was seen:
        compare the protected source representation
        IF representation differs:
            report CONTENT_CONFLICT
        ELSE:
            record DUPLICATE_DELIVERY
    ELSE:
        store event and update observed sequence set

AFTER allowed lateness window:
    compare observed positions with expected positions
    derived from the verified stream contract and trusted checkpoints

    report unresolved missing positions
    keep late arrivals as backfill with provenance
    update finding state when evidence changes
~~~

Nếu hai bản ghi có thời gian tiếp nhận khác nhau nhưng cùng payload nguồn, không nên coi khác biệt về metadata tiếp nhận là sửa nội dung. Phép so sánh cần tách phần sự kiện nguồn khỏi phần metadata do collector thêm vào.

Ngược lại, cũng không được bỏ một trường nguồn có ý nghĩa chỉ để làm hai bản ghi trông giống nhau. Quy tắc chuẩn hóa là một phần của hợp đồng kiểm tra.

### 11.4. Kết quả cần trình bày

Sau bài tập, người học nên lập được một báo cáo ngắn gồm:

- Những bất thường thực sự quan sát được trong mỗi biến thể.
- Giả định nào làm cho kiểm tra sequence có giá trị.
- Bằng chứng nào cho phép nhận ra cắt đuôi.
- Vì sao retry và đến trễ không tự động là tampering.
- Thông tin còn thiếu để xác định nguyên nhân và danh tính chịu trách nhiệm.

Kết quả tốt không phải là biến mọi biến thể thành cảnh báo nghiêm trọng. Kết quả tốt là nêu đúng điều dữ liệu cho phép kết luận và giữ lại những điểm chưa biết.

## 12. Đo hiệu quả phát hiện

Đừng chỉ đo số lượng cảnh báo. Một hệ thống có rất ít cảnh báo có thể đang hoạt động tốt hoặc đang mất khả năng quan sát.

Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa vận hành |
|---|---|
| Tỷ lệ nguồn đặc quyền có giám sát sức khỏe | Bao nhiêu nguồn có kỳ vọng và phép kiểm tra hoạt động |
| Độ trễ tiếp nhận theo từng nguồn | Cơ sở đặt cửa sổ chờ và nhận diện backfill |
| Thời gian từ thay đổi audit tới phát hiện | Mức độ nhanh của rule đối với thay đổi nhạy cảm |
| Thời lượng khoảng thiếu chưa giải thích | Quy mô điểm mù còn tồn tại |
| Tỷ lệ phiên có manifest và đối tượng recording khớp | Mức bao phủ của bằng chứng phiên thuộc phạm vi recording |
| Tỷ lệ kiểm tra toàn vẹn thành công trên tập được kiểm tra | Sức khỏe của cơ chế bảo vệ trên đúng mẫu hoặc toàn bộ tập |
| Tỷ lệ ngoại lệ quá hạn | Kỷ luật quản lý các trường hợp tạm miễn cảnh báo |
| Thời gian phục hồi luồng quan sát đáng tin | Khả năng khôi phục sau lỗi hoặc can thiệp |

Nêu rõ mẫu số. “100% hash hợp lệ” trên 10 recording được kiểm tra không có nghĩa toàn bộ 10.000 recording còn lại cũng đã được xác minh. Tương tự, tỷ lệ phiên có recording chỉ nên áp dụng cho những loại phiên mà chính sách và sản phẩm thực sự hỗ trợ ghi.

Có thể kiểm thử định kỳ bằng sự kiện tổng hợp có kiểm soát, trong phạm vi được phép. Việc sự kiện kiểm thử tới được collector cho biết một đường thu thập đang hoạt động tại thời điểm thử; không thay thế việc theo dõi liên tục toàn bộ nguồn và mọi loại sự kiện.

## 13. Những sai lầm cần tránh

**Chỉ dựa vào log cục bộ của máy bị quản trị.** Một người có toàn quyền trên máy có thể tác động tới cả hoạt động lẫn bản ghi. Cần bản sao sớm và bằng chứng từ ranh giới độc lập.

**Coi SIEM là bằng chứng bất biến mặc định.** SIEM là thành phần phân tích; mức bảo vệ dữ liệu phụ thuộc quyền quản trị, retention, pipeline và kho lưu thực tế.

**Coi hash hoặc chữ ký hợp lệ là chứng minh mọi hành động đã được ghi.** Chúng bảo vệ những gì được đưa vào phạm vi kiểm tra, không tạo bằng chứng cho sự kiện bị bỏ qua từ đầu.

**Kết luận xóa log từ một khoảng nhảy sequence.** Cần xác minh hợp đồng bộ đếm, phân vùng, lọc, epoch và độ trễ trước.

**Tin mọi ticket được ghi trong log.** Phải đối chiếu trạng thái phê duyệt và phạm vi; nguồn ticket không truy cập được là một trạng thái chưa biết.

**Đóng cảnh báo khi agent hoạt động lại.** Phục hồi luồng mới không bảo đảm khoảng trống cũ đã được bù.

**Đồng nhất quyền hợp lệ với mọi thao tác đều hợp lệ.** Một phiên đã được phê duyệt vẫn có thể thay đổi audit ngoài phạm vi được phép.

**Đặt quyền quản trị bằng chứng dưới cùng danh tính đang được giám sát.** Khi tài khoản đó bị chiếm quyền, nhiều lớp kiểm chứng có thể bị vô hiệu hóa cùng lúc.

**Thu thập bí mật không cần thiết.** Mở rộng dữ liệu audit mà không kiểm soát nội dung có thể làm lộ credential hoặc dữ liệu nhạy cảm qua chính công cụ điều tra.

## 14. Điểm cần ghi nhớ

Tampering audit trail làm suy yếu khả năng xác định điều gì đã xảy ra trong hoạt động đặc quyền. Phát hiện hiệu quả kết hợp ba nhóm tín hiệu: thay đổi cơ chế audit, gián đoạn hoặc thiếu dữ liệu và sai lệch giữa các nguồn bằng chứng.

Trong PAM, danh tính người dùng, tài khoản hiệu lực, phạm vi JIT/JEA, yêu cầu phê duyệt và vòng đời phiên phải nối được với nhau. Hash, chữ ký, checkpoint độc lập và lưu trữ được bảo vệ giúp kiểm tra những thuộc tính khác nhau; không cơ chế đơn lẻ nào chứng minh mọi hành động đã được quan sát đúng và đủ.

Khi xử lý cảnh báo, hãy bảo tồn dữ liệu đang có, phân biệt sự kiện với suy luận, khôi phục luồng quan sát và ghi rõ khoảng thiếu chưa thể giải thích. Sự minh bạch về giới hạn bằng chứng là một phần thiết yếu của một audit trail đáng tin.
