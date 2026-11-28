# Time synchronization — Đặc tả yêu cầu đồng bộ thời gian cho giám sát và phát hiện

## 1. Vì sao đồng bộ thời gian là yêu cầu bảo mật?

Một hệ thống có thể ghi đủ log nhưng vẫn khó phát hiện tấn công nếu các máy ghi nhận thời gian khác nhau. Đồng bộ thời gian tạo mốc tham chiếu để đối chiếu đăng nhập, thay đổi quyền, truy cập dữ liệu và phản ứng sự cố. Trong thiết kế yêu cầu bảo mật, mục tiêu là chuyển rủi ro về thời gian thành điều kiện đo được và tiêu chí kiểm thử cụ thể.

Trong phạm vi module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, yêu cầu không dừng ở câu “các máy phải đồng bộ NTP”. Cần chỉ rõ thành phần nào phải đồng bộ, nguồn nào được tin cậy, sai lệch bao nhiêu là chấp nhận được, cách phát hiện mất đồng bộ và hành vi khi không thể tin thời gian của một thành phần.

Ví dụ, một cuộc tấn công diễn ra theo trình tự thực tế:

1. Kẻ tấn công đăng nhập vào tài khoản nhân viên.
2. Tài khoản đó được cấp thêm quyền.
3. Một lượng lớn hồ sơ được xuất ra ngoài.

Nếu máy cấp quyền chạy nhanh hơn máy xuất dữ liệu bốn phút, màn hình điều tra có thể hiển thị việc xuất hồ sơ trước khi quyền được cấp. Một rule chỉ ghép sự kiện trong cửa sổ hai phút có thể bỏ sót chuỗi này.

Sau bài học, người học cần có khả năng:

- Liên kết rủi ro lệch giờ với yêu cầu xác thực, logging, detection và phục hồi.
- Phân biệt thời điểm sự kiện, thời điểm tiếp nhận và thời gian dùng để đo khoảng kéo dài.
- Viết yêu cầu có phạm vi, ngưỡng, độ mới của phép đo, chủ sở hữu và bằng chứng nghiệm thu.
- Xây dựng kiểm thử lệch giờ, mất nguồn giờ, chỉnh đồng hồ và phục hồi.

Các giá trị số trong bài là giả định cho một hệ thống minh họa, không phải ngưỡng bắt buộc áp dụng cho mọi sản phẩm hoặc tiêu chuẩn.

## 2. Các khái niệm cần thống nhất

### 2.1. Giờ đồng hồ và đồng hồ đơn điệu

**Giờ đồng hồ — wall clock** thể hiện thời gian lịch, chẳng hạn `2026-11-27T08:15:30.250Z`. Giá trị này có thể thay đổi khi đồng bộ, khi quản trị viên chỉnh giờ hoặc khi môi trường ảo hóa điều chỉnh đồng hồ. Nó phù hợp để gắn thời điểm cho sự kiện và đối chiếu giữa các hệ thống.

**Đồng hồ đơn điệu — monotonic clock** phục vụ đo thời gian đã trôi qua trong phạm vi mà nền tảng bảo đảm. Nó thường phù hợp hơn cho timeout, thời lượng xử lý và backoff vì không phụ thuộc thao tác chỉnh giờ lịch. Cần xác nhận hành vi khi suspend, resume hoặc khởi động lại theo nền tảng cụ thể; không so trực tiếp một giá trị đơn điệu giữa hai máy hoặc qua hai lần khởi động.

Một yêu cầu có thể viết:

> Audit event phải có timestamp UTC để đối chiếu giữa các hệ thống. Việc đo thời lượng nội bộ phải dùng nguồn thời gian phù hợp với nền tảng, không bị kéo dài hoặc rút ngắn ngoài thiết kế bởi thao tác chỉnh giờ lịch.

### 2.2. Offset, drift và độ không chắc chắn

Trong bài này, **offset** là chênh lệch giữa giờ máy và giờ tham chiếu tại cùng thời điểm:

```text
offset = thời_gian_máy - thời_gian_tham_chiếu
```

Offset dương nghĩa là máy chạy trước; offset âm nghĩa là máy chạy sau. Nếu máy hiển thị `08:15:33` khi tham chiếu là `08:15:30`, offset là `+3 giây`.

**Drift** mô tả mức đồng hồ tự lệch thêm theo thời gian. Một máy vừa đồng bộ đúng vẫn có thể sai dần khi mất nguồn tham chiếu. Nếu tốc độ lệch được ước lượng là 40 phần triệu và được coi là ổn định, sau hai giờ mức lệch tăng thêm xấp xỉ:

```text
40 × 10^-6 × 7.200 giây = 0,288 giây
```

Đây là phép ước lượng minh họa, không phải bảo đảm cho phần cứng thực tế. Khởi động lại, thay đổi môi trường hoặc chỉnh giờ có thể làm mô hình mất hiệu lực.

Phép đo offset có **độ không chắc chắn**, do độ trễ mạng, bất đối xứng đường truyền và chất lượng tham chiếu. Một điều kiện nghiệm thu bảo thủ có thể là:

```text
|offset_ước_lượng| + biên_không_chắc_chắn ≤ ngân_sách_sai_lệch
```

Chỉ dùng điều kiện này khi phương pháp đo cung cấp biên sai số có ý nghĩa đã được xác định. Một đại lượng độ phân tán thống kê không tự động trở thành biên sai số bảo đảm. Nếu công cụ chỉ cung cấp ước lượng, yêu cầu phải ghi rõ mức tin cậy và giới hạn của bằng chứng.

### 2.3. Độ phân giải khác độ chính xác

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Độ phân giải | Timestamp biểu diễn đến mức nào? | Có ba chữ số phần giây |
| Độ chính xác | Timestamp gần thời gian tham chiếu đến đâu? | Nằm trong ngân sách sai lệch 1 giây |
| Định dạng và múi giờ | Hai bên có hiểu cùng một mốc không? | Chuỗi UTC có hậu tố `Z` |

Timestamp biểu diễn mili giây vẫn có thể sai vài phút. Hậu tố `Z` thể hiện cách biểu diễn theo UTC, không chứng minh máy đã đồng bộ.

Lưu UTC giúp tránh nhầm múi giờ trong pipeline. Giao diện có thể chuyển sang giờ địa phương nhưng cần hiển thị rõ múi giờ và giữ giá trị gốc để đối chiếu. Chuẩn hóa định dạng không sửa được một đồng hồ đang chạy sai.

## 3. Từ mô hình đe dọa đến yêu cầu

Các tài sản cần bảo vệ gồm tính đúng đắn của timeline, hiệu lực kiểm soát dựa trên thời gian, khả năng phát hiện tấn công và độ tin cậy của bằng chứng sự cố.

| Rủi ro hoặc tình huống | Hậu quả | Hướng đặc tả |
| --- | --- | --- |
| Máy ứng dụng lệch so với máy xác thực | Kiểm tra thời hạn thông tin xác thực không nhất quán | Ngân sách sai lệch cho thành phần quyết định thời hạn |
| Các nguồn log lệch nhau | Rule tương quan bỏ sót hoặc ghép nhầm | Ngưỡng sai lệch gắn với cửa sổ detection |
| Tác nhân trái quyền chỉnh giờ hoặc đổi nguồn | Timeline bị thao túng, kiểm soát thời gian suy yếu | Giới hạn quyền, audit và cảnh báo thay đổi |
| Nguồn tham chiếu sai hoặc bị can thiệp | Nhiều máy cùng đồng bộ một giờ sai | Bảo vệ nguồn và đối chiếu đủ độc lập |
| Mất kết nối nguồn giờ | Độ lệch tăng dần nhưng trạng thái vẫn xanh | Giới hạn tuổi phép đo, tuổi đồng bộ và trạng thái suy giảm |
| Khởi động, resume hoặc phục hồi snapshot | Timestamp nhảy, dữ liệu cũ xuất hiện lại | Kiểm tra sức khỏe thời gian trước tác vụ nhạy cảm |
| Pipeline giám sát mất metric | Không phân biệt được khỏe với không còn quan sát | TTL dữ liệu và kiểm tra mất tín hiệu ngoài pipeline |

**Các máy đồng ý với nhau chưa đủ để khẳng định giờ đúng.** Nếu chúng cùng phụ thuộc một nguồn sai, sai lệch nội bộ vẫn có thể rất nhỏ. Kiến trúc cần nêu nguồn gốc tin cậy và mức độc lập thực tế giữa các tham chiếu; nhiều địa chỉ máy chủ chưa chắc tương đương nhiều miền lỗi độc lập.

Đồng bộ giờ cũng không chứng minh một log là xác thực. Quyền ghi, đường truyền, nơi lưu trữ và khả năng phát hiện sửa đổi log vẫn cần yêu cầu riêng.

## 4. Phạm vi và trách nhiệm kiến trúc

Trước khi chọn ngưỡng, cần xác định các thành phần có quyết định bảo mật phụ thuộc thời gian:

- Dịch vụ danh tính, gateway và ứng dụng kiểm tra thời hạn thông tin xác thực.
- Máy ứng dụng, cơ sở dữ liệu và hàng đợi phát sinh audit event.
- Bộ thu log, pipeline, kho lưu trữ và engine tương quan.
- Máy quản trị, nền tảng ảo hóa và lớp cung cấp giờ cho workload.
- Công cụ điều tra, lịch chạy và hệ thống phục hồi sử dụng timestamp.

Mô hình trách nhiệm có thể mô tả như sau:

```text
Nguồn giờ được phê duyệt
          |
          v
Cơ chế phân phối / đồng bộ của nền tảng
          |
          v
Host hoặc môi trường chạy workload
          |
          +--> Ứng dụng ghi event_time và định danh nguồn
          |
          +--> Đo offset, độ mới và trạng thái nguồn
                              |
                              v
                   Giám sát sức khỏe thời gian
                              |
                              v
                   Cảnh báo + xử lý + phục hồi
```

Đây là kiến trúc logic, không bắt buộc phải có máy chủ thời gian nội bộ. Với hạ tầng được quản lý, phải xác định phần nhà cung cấp bảo đảm và phần đội ứng dụng tự quan sát.

Container thường nhận giờ từ host hoặc nền tảng. Cài thêm một tiến trình trong từng container không mặc nhiên tạo ra đồng hồ độc lập đáng tin hơn. Cần xác nhận cơ chế thực tế và giao trách nhiệm cho đúng lớp.

| Chủ thể | Trách nhiệm chính |
| --- | --- |
| Đội nền tảng | Nguồn giờ, cấu hình đồng bộ, sức khỏe host và quyền chỉnh giờ |
| Đội ứng dụng | Chọn loại đồng hồ, ghi timestamp/correlation ID, xử lý trạng thái suy giảm |
| Đội detection/SOC | Rule có xét độ lệch và đến muộn, cảnh báo chất lượng, điều tra timeline |
| Chủ sở hữu yêu cầu bảo mật | Phê duyệt ngân sách sai lệch, ngoại lệ và tiêu chí nghiệm thu |

Một yêu cầu cần có một đầu mối chịu trách nhiệm nghiệm thu, kể cả khi nhiều đội cùng triển khai.

## 5. Chọn ngân sách sai lệch theo rủi ro

### 5.1. Gắn với cửa sổ detection

Giả sử rule liên kết việc tăng quyền với xuất dữ liệu trong hai phút. Nếu chênh lệch đồng hồ giữa hai nguồn lên đến vài phút, rule không còn thực thi đúng ý định.

Nếu A và B đều có biên sai lệch tối đa 1 giây so với cùng tham chiếu đủ tin cậy, chênh lệch giữa hai máy có thể đến 2 giây:

```text
biên_sai_lệch_giữa_A_và_B ≤ biên_A + biên_B
```

Không dùng ngưỡng của một máy như ngưỡng giữa mọi cặp máy. Ngoài sai lệch đồng hồ, cần tính thời gian phát sinh log, vận chuyển, xử lý và chính sách đến muộn. Những đại lượng này không cùng bản chất và cần được quan sát riêng.

### 5.2. Gắn với xác thực và chống phát lại

Dung sai khi kiểm tra thời hạn thông tin xác thực cần xuất phát từ ngân sách sai lệch và yêu cầu nghiệp vụ. Tăng dung sai có thể kéo dài khoảng chấp nhận quá thời hạn danh nghĩa; nó không khắc phục nguyên nhân lệch giờ.

Yêu cầu phải nêu người quyết định dung sai, thành phần áp dụng và hành vi tại ranh giới. Không tự động tăng dung sai khi mất nguồn giờ.

Đồng hồ chính xác hỗ trợ kiểm soát chống phát lại dựa trên thời gian. Tùy giao thức, vẫn có thể cần nonce, định danh duy nhất hoặc trạng thái đã sử dụng; đồng bộ thời gian không thay thế chúng.

### 5.3. Phân biệt tỷ lệ vận hành với điều kiện an toàn

“99,9% mẫu nằm trong 1 giây” không tương đương “mọi thành phần nhạy cảm luôn nằm trong 1 giây”. Nếu dùng tỷ lệ, cần quy định mẫu số: số mẫu đo, số phút vận hành hay số workload.

Mẫu thiếu phải được báo riêng; không được loại bỏ rồi tuyên bố toàn hệ thống khỏe. Với tác vụ có giới hạn chặt, phải có điều kiện cho phép thực hiện và hành vi khi vi phạm. Kiểm tra định kỳ chỉ cung cấp bằng chứng tại thời điểm đo, không bảo đảm đồng hồ không thay đổi giữa hai mẫu.

## 6. Bộ yêu cầu minh họa có thể kiểm chứng

### 6.1. Bối cảnh và định nghĩa trạng thái khỏe

Xét cổng quản trị có đăng nhập, thay đổi quyền và xuất hồ sơ. Rule tương quan dùng cửa sổ hai phút. Host chạy xác thực, cổng quản trị và pipeline audit thuộc nhóm quan trọng.

Giả định thiết kế:

- Ngân sách sai lệch: 1 giây so với tham chiếu được phê duyệt, tính cả biên không chắc chắn.
- Chu kỳ lấy mẫu sức khỏe: 30 giây; tuổi mẫu tối đa: 60 giây.
- Biên không chắc chắn tối đa của phép đo: 100 mili giây.
- Tuổi lần đồng bộ thành công gần nhất: không quá 300 giây.
- Nguồn và phương pháp kiểm tra phải đáp ứng mức tin cậy đã được phê duyệt.

Một host chỉ được đánh giá `healthy` khi đồng thời đạt tất cả điều kiện. `Degraded` biểu thị đã có bằng chứng vi phạm. `Unknown` biểu thị thiếu hoặc không tin được bằng chứng hiện tại; nó không đủ điều kiện khỏe.

Các con số cần được xác nhận là khả thi trên hạ tầng thật và đủ cho rủi ro nghiệp vụ trước khi đưa vào đặc tả chính thức.

### 6.2. Yêu cầu, chủ sở hữu và bằng chứng

| ID | Yêu cầu minh họa | Chủ sở hữu | Nghiệm thu |
| --- | --- | --- | --- |
| TIME-01 | Mọi host quan trọng phải dùng nguồn và cơ chế đồng bộ được duyệt; chỉ chủ thể được phân quyền mới được đổi cấu hình hoặc chỉnh giờ. | Nền tảng | Đối chiếu danh mục với cấu hình hiệu lực; thử thay đổi trái quyền phải bị từ chối và ghi nhận. |
| TIME-02 | Mỗi host phải cung cấp mẫu sức khỏe mỗi 30 giây, gồm offset, biên không chắc chắn, thời điểm đo, nguồn tham chiếu và tuổi đồng bộ thành công. | Nền tảng | Kiểm tra từng host ở tải đại diện; đánh giá toàn bộ điều kiện mục 6.1, không chỉ trạng thái tiến trình. |
| TIME-03 | Khi mẫu mới vi phạm điều kiện khỏe, host phải chuyển degraded trong chu kỳ đánh giá không quá 30 giây; khi tuổi mẫu vượt 60 giây hoặc bằng chứng không tin được, chuyển unknown trong cùng giới hạn đánh giá. | Nền tảng | Tiêm lệch giờ, độ không chắc chắn quá mức và mất mẫu; đo chuyển trạng thái bằng quan sát độc lập. |
| TIME-04 | Hai mẫu liên tiếp vượt ngân sách 1 giây phải phát cảnh báo trong 120 giây từ lúc lỗi bắt đầu. Mẫu vượt 5 giây hoặc mất tín hiệu quá 60 giây phải phát cảnh báo trong 60 giây từ khi điều kiện tương ứng phát sinh. | Detection | Ghi nhận thời điểm tiêm lỗi, lấy mẫu, kích hoạt và nhận cảnh báo bằng tham chiếu độc lập. |
| TIME-05 | Audit đăng nhập, thay đổi quyền và xuất hồ sơ phải có event_time UTC, event_id, định danh nguồn và tham chiếu chất lượng thời gian. Bộ tiếp nhận phải thêm ingested_at. | Ứng dụng | Kiểm tra schema và mẫu từng loại; timestamp gốc được giữ khi có vấn đề thời gian. |
| TIME-06 | Thay đổi nguồn, cấu hình đồng bộ và thao tác chỉnh giờ được nền tảng quan sát phải có audit gửi ra ngoài host. | Nền tảng | Tìm được tác nhân, kết quả, cấu hình trước/sau khi có thể cung cấp và thời điểm tiếp nhận độc lập. |
| TIME-07 | Rule hai phút phải công bố cách xét sai lệch giữa nguồn, dung sai đến muộn và xử lý sự kiện không đáng tin; không âm thầm bỏ chúng. | Detection | Phát lại dữ liệu chuẩn với sai lệch và độ trễ; đối chiếu ghép chuỗi, cảnh báo chất lượng và nhánh đến muộn. |
| TIME-08 | Tác vụ nhạy cảm phải tuân theo chính sách đã duyệt khi degraded/unknown; không tự nới thời hạn xác thực hoặc tắt audit để tiếp tục. | Ứng dụng | Tiêm từng trạng thái; kiểm tra quyết định cho phép, chặn hoặc xếp hàng theo từng loại tác vụ. |
| TIME-09 | Sau khởi động, resume, phục hồi snapshot hoặc đồng bộ lại, cần ba mẫu liên tiếp đạt toàn bộ điều kiện để trở về healthy; mẫu lỗi hoặc thiếu phải đặt lại bộ đếm. | Nền tảng | Thử từng tình huống; có bằng chứng ba mẫu mới đạt trước khi khôi phục tác vụ phụ thuộc trạng thái. |
| TIME-10 | Việc pipeline giám sát ngừng hoạt động phải được phát hiện bởi cơ chế kiểm tra sống nằm ngoài miền lỗi của pipeline đó. | Nền tảng | Dừng thu thập/xử lý; cơ chế bên ngoài vẫn thông báo mất khả năng quan sát theo TIME-04. |

Với TIME-04, “lúc lỗi bắt đầu” trong kiểm thử là lúc bộ kiểm thử độc lập ghi nhận điều kiện vượt ngưỡng, không phải lúc dashboard hiển thị. Với mất tín hiệu, điều kiện kích hoạt là khi tuổi mẫu vượt 60 giây; thời hạn cảnh báo được tính từ mốc đó.

Ngân sách độ trễ cảnh báo phải tính cả chờ lấy mẫu, truyền metric, đánh giá và gửi thông báo. Các ngưỡng trên chỉ nhất quán nếu chu kỳ và độ trễ thực tế cho phép đạt thời hạn đầu cuối. Những vi phạm điều kiện khỏe khác, như tuổi đồng bộ quá 300 giây hoặc độ không chắc chắn quá mức, cần chính sách cảnh báo riêng trong triển khai chính thức; bảng này không mặc định chúng cùng thuộc nhánh vượt offset.

Nếu nền tảng không quan sát được thao tác chỉnh giờ hoặc không cung cấp phép đo đáp ứng yêu cầu, phải ghi nhận khoảng trống thiết kế. Không đánh dấu đạt bằng một trường có tên tương tự nhưng ý nghĩa khác.

### 6.3. Mẫu đặc tả cho một yêu cầu

```text
ID: TIME-03
Rủi ro: R-TIME-02 — tương quan sai do timestamp không đáng tin
Phạm vi: host xác thực, cổng quản trị, pipeline audit trong danh mục duyệt
Healthy:
  - Mẫu hợp lệ, tuổi mẫu không quá 60 giây
  - |offset| + uncertainty không quá 1 giây
  - uncertainty không quá 100 mili giây
  - Lần đồng bộ thành công gần nhất không quá 300 giây
Vi phạm:
  - Có bằng chứng không đạt: degraded
  - Thiếu hoặc không tin bằng chứng: unknown
  - Cập nhật trạng thái theo chu kỳ đánh giá không quá 30 giây
  - Truyền trạng thái cho detection và chính sách tác vụ nhạy cảm
  - Giữ log, đánh dấu chất lượng, không sửa timestamp gốc
Chủ sở hữu: đội nền tảng
Phối hợp: đội ứng dụng và detection
Kiểm thử: T-TIME-01, T-TIME-02, T-TIME-03, T-TIME-05
Bằng chứng: cấu hình hiệu lực, chuỗi metric, trạng thái và kết quả thử
```

Trong dự án thật, tên đội và danh mục host phải liên kết tới đối tượng thực tế có người chịu trách nhiệm.

## 7. Timestamp trong logging và detection

### 7.1. Tách thời điểm sự kiện và thời điểm tiếp nhận

Ví dụ audit event sau khi bộ tiếp nhận bổ sung dữ liệu:

```json
{
  "event_id": "audit-7f6b21",
  "event_type": "role.granted",
  "event_time": "2026-11-27T08:15:30.250Z",
  "ingested_at": "2026-11-27T08:15:31.100Z",
  "source_instance": "admin-api-03",
  "source_boot_id": "boot-c8d2",
  "source_sequence": 18452,
  "actor_id": "user-482",
  "target_id": "user-913",
  "correlation_id": "req-9ab1",
  "time_health_ref": "sample-605",
  "time_health": "healthy",
  "time_offset_estimate_ms": 120,
  "time_uncertainty_bound_ms": 80
}
```

`Event_time` do thành phần phát sự kiện ghi; `ingested_at` do bộ tiếp nhận bổ sung. Mẫu sức khỏe tham chiếu phải đủ mới. Các trường này cần kiểm soát nguồn gửi và quyền sửa; không tin nhãn `healthy` tùy ý do client cung cấp.

Chênh lệch giữa hai timestamp có thể gợi ý chậm vận chuyển, nhưng còn chịu ảnh hưởng sai lệch của cả máy phát và máy thu. Giá trị âm không có nghĩa sự kiện “đến trước khi xảy ra”; nó có thể là dấu hiệu lệch giờ hoặc lỗi dữ liệu.

Không ghi đè `event_time` bằng `ingested_at` để dashboard trông đúng thứ tự. Nếu cần thời điểm hiệu chỉnh, lưu thành trường dẫn xuất riêng với phương pháp, phiên bản và mức không chắc chắn; luôn giữ timestamp gốc.

### 7.2. Đồng bộ giờ không tạo thứ tự toàn cục

Hai sự kiện cách nhau 200 mili giây không thể được xếp thứ tự chắc chắn chỉ bằng timestamp nếu mỗi nguồn có thể sai tới 1 giây. Có thể hình dung mỗi thời điểm là một khoảng:

```text
Sự kiện A: [timestamp_A - biên_A, timestamp_A + biên_A]
Sự kiện B: [timestamp_B - biên_B, timestamp_B + biên_B]
```

Nếu hai khoảng chồng nhau, dữ liệu thời gian chưa đủ chứng minh thứ tự. Cần kết hợp correlation ID, quan hệ request/response, mã giao dịch và sequence theo nguồn.

Sequence cần ghép với định danh nguồn và phiên chạy nếu nó đặt lại sau khởi động; nó không tự tạo thứ tự giữa mọi máy. Timeline điều tra phải phân biệt thứ tự hiển thị theo timestamp với quan hệ nhân quả đã có bằng chứng.

### 7.3. Đặc tả sự kiện đến muộn

Giả sử rule có cửa sổ hành vi hai phút và chấp nhận sự kiện vận chuyển chậm thêm 60 giây:

- Cửa sổ hành vi xác định các sự kiện thuộc chuỗi cần phát hiện.
- Dung sai đến muộn xác định engine chờ hoặc cập nhật kết quả đến khi nào.

Khi mất mạng mười phút, dữ liệu phục hồi có thể vượt dung sai. Yêu cầu cần chỉ rõ sẽ tái xử lý, chuyển sang điều tra hồi cứu hay tạo cảnh báo chất lượng. Tăng cửa sổ hành vi chỉ để chứa log chậm có thể tạo ghép nhầm.

Rule dùng thời điểm tiếp nhận có thể hữu ích khi giờ nguồn không đáng tin, nhưng kết quả thể hiện hành vi quan sát tại bộ tiếp nhận. Không được trình bày như trình tự thực tế đã được chứng minh.

## 8. Bảo vệ nguồn giờ và quyền chỉnh thời gian

Đường phân phối thời gian là một phụ thuộc bảo mật. Thiết kế cần bao gồm:

1. **Nguồn và đường đi được phê duyệt:** xác định tham chiếu, cơ chế phân phối, miền lỗi và cách phát hiện nguồn bất thường.
2. **Quyền tối thiểu:** giới hạn người có thể đổi nguồn, chính sách đồng bộ hoặc giờ hệ thống; ghi audit cho thay đổi và kết quả.
3. **Bảo vệ tính xác thực của nguồn:** chọn cơ chế phù hợp với giao thức và nền tảng. Chỉ giới hạn địa chỉ mạng không tự chứng minh nguồn trả lời đáng tin.
4. **Quan sát sai lệch:** theo dõi offset tăng mạnh, thay nguồn, chỉnh nhảy giờ và host ngừng cung cấp mẫu.
5. **Đối chiếu đủ độc lập:** tránh để một nguồn hoặc một miền quản trị làm sai cả nguồn chính lẫn hệ thống kiểm tra.

Nhiều nguồn có thể tăng khả năng chịu lỗi, nhưng cần đặc tả cách chọn nguồn, xử lý bất đồng và hành vi khi không xác định được nguồn đáng tin.

Một nguồn được xác thực vẫn có thể báo giờ sai hoặc không còn truy cập được. Vì vậy bảo vệ đường truyền không thay thế giám sát độ chính xác, độ mới và độ sẵn sàng.

Audit thay đổi thời gian nên được chuyển ra ngoài host theo giới hạn truyền log đã định. Nếu host bị kiểm soát hoàn toàn, log tự báo có thể không đầy đủ; đối chiếu từ nền tảng hoặc nguồn độc lập giúp giảm điểm mù.

## 9. Suy giảm và phục hồi

### 9.1. Mất nguồn không đồng nghĩa lập tức sai giờ

Một máy có thể tiếp tục tương đối đúng sau khi mất nguồn. Khoảng thời gian này chỉ được chấp nhận nếu có mô hình lệch và bằng chứng còn đủ cho ngân sách yêu cầu. Không giữ trạng thái khỏe vô thời hạn dựa trên lần đồng bộ cũ.

| Trạng thái | Ý nghĩa | Cách sử dụng trong detection |
| --- | --- | --- |
| healthy | Bằng chứng mới và đạt mọi điều kiện | Dùng timestamp trong giới hạn đã đặc tả |
| degraded | Có bằng chứng vi phạm | Đánh dấu timeline, cảnh báo và áp dụng chính sách tác vụ |
| unknown | Thiếu hoặc không tin được bằng chứng | Xử lý điểm mù; không coi là khỏe; giữ dữ liệu để điều tra |

Nếu pipeline giám sát chết, chính nó không thể bảo đảm sẽ gửi cảnh báo. Cần cơ chế mất tín hiệu ngoài miền lỗi liên quan, với kênh thông báo còn hoạt động khi pipeline bị thử lỗi.

### 9.2. Quyết định theo loại tác vụ

Ví dụ chính sách cho cổng quản trị:

- Tạm chặn cấp quyền quản trị mới khi thành phần quyết định ở trạng thái degraded hoặc unknown.
- Tiếp tục ghi audit với nhãn chất lượng; nếu chưa chuyển được thì dùng cơ chế lưu đệm đã đặc tả.
- Cho phép một số tra cứu ít nhạy cảm theo ngoại lệ được duyệt, có giới hạn và giám sát.
- Nếu có truy cập khẩn cấp, đặc tả riêng người phê duyệt và audit; không ngầm bỏ kiểm tra thời hạn.

Đó là lựa chọn của ví dụ. Chính sách thực tế phải cân bằng rủi ro an ninh và rủi ro gián đoạn theo chức năng, rồi được kiểm thử như đã phê duyệt.

### 9.3. Khôi phục nhưng giữ dấu vết

Quy trình xử lý nên yêu cầu:

1. Xác định host, nguồn, phạm vi ảnh hưởng và khoảng thời gian nghi ngờ.
2. Lưu cấu hình, metric và audit trước khi can thiệp nếu tình huống cho phép.
3. Xác minh nguồn, chọn cách hiệu chỉnh phù hợp với nền tảng; đánh giá tác động chỉnh nhảy hoặc chỉnh dần.
4. Xác nhận mẫu mới đạt điều kiện phục hồi; không chỉ kiểm tra tiến trình đang chạy.
5. Đánh dấu dữ liệu trong khoảng ảnh hưởng, tái chạy detection cần thiết và ghi kết luận điều tra.

Chỉnh giờ lùi có thể khiến timestamp lặp lại hoặc đảo thứ tự nhìn thấy. Không dùng timestamp đơn độc làm định danh duy nhất của audit event. Cần kiểm thử cả ảnh hưởng tới cache, lịch chạy, timeout và kiểm soát thời hạn.

Hệ thống cũng cần quy định cách xử lý các điều chỉnh thời gian đặc biệt, chẳng hạn chính sách giây nhuận hoặc làm giãn hiệu chỉnh nếu nền tảng sử dụng. Các miền áp dụng chính sách khác nhau cần được đánh giá khả năng tạo chênh lệch tạm thời; không mặc định cùng biểu diễn UTC là đủ để loại rủi ro này.

## 10. Ma trận kiểm thử nghiệm thu

Thử thay đổi đồng hồ trong môi trường cô lập với dữ liệu giả và quyền hạ tầng phù hợp. Bộ kiểm thử phải có tham chiếu độc lập với đồng hồ bị tiêm lỗi; dùng chính đồng hồ đó để đo độ trễ cảnh báo sẽ làm sai bằng chứng.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-TIME-01 | Tạo offset dương và âm, ngay dưới/bằng/trên 1 giây sau khi cộng biên không chắc chắn. | Áp dụng đúng điều kiện ≤ 1 giây; vượt ngưỡng chuyển suy giảm; hai mẫu liên tiếp tạo cảnh báo đúng hạn. | TIME-02, 03, 04 |
| T-TIME-02 | Ngắt nguồn giờ nhưng giữ đường metric; chờ tuổi đồng bộ vượt 300 giây. | Tuổi đồng bộ được phản ánh; không còn healthy khi điều kiện mất hiệu lực dù offset còn nhỏ. | TIME-02, 03 |
| T-TIME-03 | Dừng gửi metric hoặc dừng pipeline giám sát trong các lượt riêng. | Quá tuổi mẫu chuyển unknown; cơ chế bên ngoài vẫn thông báo theo thời hạn. | TIME-03, 04, 10 |
| T-TIME-04 | Thử đổi nguồn/chỉnh giờ bằng tài khoản trái quyền rồi bằng tài khoản được phép. | Lần trái quyền bị từ chối; lần hợp lệ có audit ngoài host và đủ dấu vết. | TIME-01, 06 |
| T-TIME-05 | Khởi động, resume, phục hồi snapshot; chèn một mẫu lỗi giữa các mẫu đạt. | Bộ đếm đạt được đặt lại; chỉ khỏe sau ba mẫu mới liên tiếp; tác vụ theo đúng chính sách. | TIME-03, 08, 09 |
| T-TIME-06 | Phát chuỗi đăng nhập → tăng quyền → xuất hồ sơ với sai lệch và vận chuyển chậm trong giới hạn cho phép. | Rule phát hiện đúng chuỗi; không ghép sự kiện của chủ thể khác; giữ timestamp gốc. | TIME-05, 07 |
| T-TIME-07 | Cho event đến trễ vượt dung sai hoặc từ nguồn có chất lượng unknown. | Đi vào nhánh xử lý đến muộn/hồi cứu và thời gian không tin cậy; không bị bỏ im lặng. | TIME-05, 07 |
| T-TIME-08 | Tạo offset vượt 5 giây trong khi đường cảnh báo còn hoạt động. | Cảnh báo đến trong 60 giây từ lúc lỗi được bộ kiểm thử độc lập ghi nhận. | TIME-04 |
| T-TIME-09 | Cho nguồn chính và nguồn cùng phụ thuộc báo một giờ sai; tham chiếu kiểm tra độc lập vẫn đúng. | Phát hiện bất đồng hoặc hạ chất lượng; không kết luận khỏe chỉ vì nhiều nguồn đồng ý. | TIME-01, 02, 03 |
| T-TIME-10 | Chỉnh giờ lịch tiến/lùi khi tác vụ có timeout; ở lượt khác làm biên không chắc chắn vượt 100 mili giây. | Thời lượng đúng theo cơ chế nền tảng; giữ timestamp gốc; phép đo quá bất định không được coi là khỏe. | TIME-02, 03, 05, 08 |

Mỗi lượt thử cần giữ cấu hình, danh mục thành phần, phiên bản rule, thời điểm tiêm lỗi và kết quả. “Có log” chưa đủ để đạt; phải đúng trường dữ liệu, chuyển trạng thái, thời hạn và hành vi nghiệp vụ.

Kiểm thử ranh giới cần xét quy tắc làm tròn. Dashboard hiển thị `1,0 giây` không chứng minh mẫu gốc `1,04 giây` đạt giới hạn `1 giây`.

## 11. Truy vết qua vòng đời phát triển

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bảo mật
  → Rủi ro thời gian
  → Yêu cầu TIME-xx
  → Quyết định kiến trúc và trách nhiệm triển khai
  → Test T-TIME-xx
  → Bằng chứng nghiệm thu
  → Metric, cảnh báo và quy trình vận hành
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế và kiểm chứng |
| --- | --- | --- | --- |
| Phát hiện xuất hồ sơ sau tăng quyền | Lệch timestamp làm bỏ sót liên kết hai phút | TIME-02, 05, 07 | Đồng bộ host; hai timestamp; rule có độ lệch/đến muộn; T-TIME-01, 06, 07 |
| Giữ hiệu lực kiểm soát thời hạn | Đồng hồ sai nhưng tác vụ nhạy cảm tiếp tục | TIME-03, 08, 09 | Trạng thái sức khỏe đi vào quyết định nghiệp vụ; T-TIME-01, 05, 10 |
| Giữ khả năng điều tra | Chỉnh giờ hoặc đổi nguồn không có dấu vết | TIME-01, 05, 06 | Quyền hạn chế; audit ngoài host; timestamp gốc và sequence; T-TIME-04, 06 |
| Không mất quan sát âm thầm | Dashboard giữ màu xanh sau khi metric dừng | TIME-03, 04, 10 | TTL mẫu; unknown; kiểm tra ngoài miền lỗi; T-TIME-03 |

Khi đổi cửa sổ detection, cơ chế xác thực hoặc vùng triển khai, cần đánh giá lại ngân sách thời gian và test liên quan. Đồng bộ thời gian là yêu cầu cần được duy trì trong vận hành.

Ngoại lệ phải có phạm vi, lý do, biện pháp bù, người phê duyệt và ngày hết hạn. Không xóa host chưa đáp ứng khỏi mẫu số chỉ để tăng tỷ lệ đạt.

## 12. Những lỗi đặc tả thường gặp

| Cách viết hoặc cách làm | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Hệ thống phải dùng NTP.” | Nêu cơ chế, chưa nêu kết quả cần đạt | Thêm phạm vi, nguồn, ngân sách sai lệch, độ mới và kiểm thử |
| “Log dùng UTC là đủ.” | Múi giờ đúng không chứng minh đồng hồ đúng | Đo sức khỏe và truyền chất lượng vào pipeline |
| “Có ba nguồn nên tin cậy.” | Có thể cùng phụ thuộc một điểm sai | Nêu miền lỗi, cách đối chiếu và xử lý bất đồng |
| “Tiến trình chạy là đã đồng bộ.” | Có thể sống nhưng không nhận được giờ mới | Kiểm tra offset, độ không chắc chắn và tuổi đồng bộ |
| “Không có metric thì chưa có lỗi.” | Mất quan sát bị hiểu là khỏe | TTL, unknown và cảnh báo ngoài pipeline |
| “Timestamp nhỏ hơn nghĩa là xảy ra trước.” | Khoảng sai số có thể chồng lấn | Kết hợp nhân quả, correlation ID và sequence theo nguồn |
| “Tăng dung sai xác thực để hết lỗi.” | Mở rộng khoảng chấp nhận ngoài chủ đích | Sửa nguồn lệch giờ, phê duyệt dung sai theo rủi ro |
| “Sửa timestamp cũ cho đúng thứ tự.” | Làm mất bằng chứng gốc | Giữ gốc, thêm dữ liệu dẫn xuất có phương pháp truy vết |
| “Cảnh báo khi bất thường.” | Không thể nghiệm thu khách quan | Quy định ngưỡng, thời hạn đầu cuối và điều kiện phục hồi |

## 13. Bài tập áp dụng

Một hệ thống có dịch vụ đăng nhập, cấp quyền và xuất báo cáo. Rule cần phát hiện người dùng xuất hơn 1.000 hồ sơ trong hai phút sau khi được cấp quyền mới. Hiện mỗi dịch vụ chỉ ghi một trường `timestamp`; một số host không có metric đồng bộ.

Hãy thực hiện:

1. Nêu ba kịch bản rủi ro thời gian và ánh xạ tới mục tiêu detection hoặc xác thực.
2. Chọn ngân sách sai lệch cho từng nhóm thành phần; giải thích sai lệch một máy và giữa hai nguồn.
3. Viết năm yêu cầu có ID, phạm vi, ngưỡng, độ mới, hành vi suy giảm, chủ sở hữu và bằng chứng.
4. Đề xuất schema giữ thời điểm phát sinh, tiếp nhận và dữ liệu đủ để điều tra host lệch giờ.
5. Thiết kế test lệch dương/âm, mất metric, đến muộn và phục hồi snapshot.
6. Chỉ rõ tác vụ cần tạm chặn khi thời gian không đủ tin cậy và tác vụ có thể tiếp tục theo ngoại lệ.

Đáp án tốt cần giải thích vì sao ngưỡng phù hợp rủi ro, dữ liệu nào chứng minh đạt và ai xử lý khi bằng chứng không còn đáng tin. Chọn công cụ đồng bộ chỉ là một phần triển khai.

## 14. Checklist chấp nhận yêu cầu

- Đã bao quát thành phần tạo sự kiện, quyết định thời hạn và tương quan log chưa?
- Nguồn giờ, miền tin cậy, quyền cấu hình và đối chiếu có rõ ràng không?
- Ngưỡng có đơn vị, biên không chắc chắn, tuổi mẫu và tuổi đồng bộ không?
- Có phân biệt giờ lịch, thời lượng và thứ tự nhân quả không?
- Timestamp gốc, thời điểm tiếp nhận và dữ liệu dẫn xuất có được giữ riêng không?
- Rule có xử lý đến muộn, thời gian không tin cậy và tái xử lý không?
- Mất metric có dẫn tới unknown thay vì giữ trạng thái khỏe không?
- Cảnh báo có ngưỡng, thời hạn đầu cuối và tham chiếu độc lập khi thử không?
- Tác vụ nhạy cảm và điều kiện phục hồi có được đặc tả cụ thể không?
- Có liên kết rủi ro → yêu cầu → thiết kế → test → bằng chứng → chủ sở hữu không?

Đồng bộ thời gian có giá trị bảo mật khi hệ thống chứng minh được mức sai lệch chấp nhận, nhận biết lúc bằng chứng mất hiệu lực và xử lý nhất quán trong logging, detection, xác thực và phục hồi.
