# Kiểm thử chặn lệnh đặc quyền — Test command blocking

## 1. Mục tiêu của bài học

Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), một phiên đăng nhập được phê duyệt không có nghĩa là người dùng được phép thực hiện mọi lệnh. Người vận hành có thể được xem trạng thái dịch vụ nhưng không được thay đổi cấu hình, xuất bí mật hoặc chạy chương trình ngoài phạm vi công việc.

Command blocking là cơ chế từ chối một thao tác lệnh theo chính sách tại một điểm thực thi cụ thể. Kiểm thử command blocking cần trả lời đồng thời ba câu hỏi:

1. Hệ thống có nhận diện đúng người dùng, máy đích, quyền và ngữ cảnh của lệnh không?
2. Lệnh bị cấm có bị ngăn trước khi thực thi hành vi mà chính sách muốn bảo vệ không?
3. Có đủ bằng chứng để phân biệt một lần chặn thật với lỗi kết nối, lỗi chương trình hoặc một cảnh báo xuất hiện sau khi lệnh đã chạy không?

Bài học đặt command blocking trong phạm vi PAM cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Nội dung kết nối least privilege, quyền truy cập vừa đủ và đúng thời điểm, quản lý credential trong vault, giám sát phiên và bằng chứng kiểm toán.

Sau bài học, người học có thể thiết kế một bộ kiểm thử gồm ca được phép, ca bị cấm, ca ranh giới và ca lỗi; đối chiếu quyết định PAM với quan sát tại máy đích; đưa ra kết luận PASS, FAIL hoặc INCONCLUSIVE có căn cứ.

## 2. Phân biệt chặn, cảnh báo và kết thúc phiên

Ba hành vi dưới đây có thể cùng xuất hiện trong một sản phẩm nhưng không tương đương về hiệu lực.

| Hành vi | Thời điểm tác động cần xác định | Bằng chứng cần tìm | Điều chưa thể tự suy ra |
|---|---|---|---|
| Chặn trước thực thi | Trước khi hành vi được bảo vệ xảy ra | Quyết định từ chối và quan sát tại điểm thực thi | Mọi đường truy cập khác đều được bảo vệ |
| Cảnh báo lệnh | Có thể trước, trong hoặc sau thực thi tùy thiết kế | Sự kiện phát hiện và trạng thái xử lý | Lệnh chưa chạy |
| Kết thúc phiên | Sau một điều kiện vi phạm hoặc quyết định điều khiển phiên | Thời điểm đóng phiên, tiến trình và tác động còn lại | Tiến trình con đã bị dừng hoặc thay đổi đã được hoàn tác |
| Ghi hình, ghi log phiên | Quan sát hoạt động trong phạm vi thu thập | Bản ghi, transcript, dấu thời gian | Có cơ chế ngăn chặn |
| Từ chối tạo phiên | Trước khi có phiên truy cập | Lỗi cấp phiên và quyết định kiểm soát truy cập | Bộ chặn lệnh bên trong phiên đang hoạt động đúng |

Ví dụ, người dùng gửi một thao tác bị cấm lúc 10:00:00. Máy đích ghi nhận thao tác lúc 10:00:01, còn phiên bị đóng lúc 10:00:02. Chuỗi này cho thấy có phản ứng với vi phạm, nhưng không chứng minh yêu cầu “chặn thao tác trước thực thi” đã đạt.

Ngược lại, thông báo “access denied” trên màn hình cũng chưa đủ. Chương trình trên máy đích có thể tự trả lỗi quyền sau khi đã được khởi chạy. Muốn đánh giá cơ chế chặn lệnh, phải biết lỗi đến từ lớp nào.

## 3. Xác định chính xác đối tượng bị chặn

### 3.1. Chuỗi ký tự và hành vi thực thi là hai đối tượng khác nhau

Một bộ lọc có thể nhận diện dòng văn bản người dùng nhập. Một cơ chế khác có thể ra quyết định trên đường dẫn chương trình và danh sách đối số. Một mô hình truy cập giới hạn chỉ công bố các thao tác được định nghĩa trước, không cấp shell tổng quát.

Vì vậy, trước khi viết ca kiểm thử, cần ghi rõ hợp đồng mà hệ thống cam kết:

- Bộ chặn nhìn thấy văn bản terminal, yêu cầu mở kênh thực thi hay sự kiện tạo tiến trình?
- Quyết định dựa trên tên hiển thị, đường dẫn chương trình, đối số đã phân tách hay danh tính một thao tác?
- Việc kiểm tra xảy ra trên gateway, máy đích hay cả hai?
- Cơ chế có kiểm soát tiến trình con, script, kênh không tương tác hoặc tác vụ được lập lịch không?
- Lệnh ngoài danh sách có mặc định bị từ chối hay mặc định được phép?

Không mặc định rằng kiểm soát được một dòng nhập trong terminal đồng nghĩa kiểm soát được mọi cách tạo cùng một hành vi. Phạm vi bảo vệ phải được kiểm chứng theo kiến trúc đã triển khai.

### 3.2. Gắn yêu cầu với một điểm thực thi

Một luồng minh họa:

~~~text
Người dùng
    |
    v
Xác thực và cấp phiên PAM
    |
    v
Nhận yêu cầu thao tác
    |
    v
Quyết định chính sách ---- DENY ----> Trả kết quả và lưu bằng chứng
    |
   ALLOW
    |
    v
Điểm thực thi trên máy đích
    |
    v
Tiến trình / thao tác nghiệp vụ
    |
    v
Quan sát tác động và đối chiếu bằng chứng
~~~

Sơ đồ là mô hình kiểm thử, không mô tả mọi sản phẩm PAM. Khi dùng cơ chế lọc terminal, điểm kiểm tra có thể khác với khi dùng tác nhân trên máy đích hoặc một endpoint quản trị giới hạn.

Nếu yêu cầu ghi “không được khởi chạy chương trình X”, tiêu chí phải kiểm tra việc khởi chạy. Nếu yêu cầu ghi “không được thay đổi tài nguyên Y”, chỉ quan sát việc có hay không có tiến trình là chưa đủ: cần kiểm tra trạng thái tài nguyên Y.

## 4. Viết yêu cầu kiểm thử có thể đo được

Yêu cầu mơ hồ:

> Chặn các lệnh nguy hiểm cho tài khoản vận hành.

Yêu cầu cụ thể hơn:

> Với vai trò operations-readonly, trên máy lab-pam-01, trong phiên đi qua tuyến PAM được chỉ định, chỉ cho phép thao tác xem trạng thái của demo-service. Mọi yêu cầu gọi fixture tạo marker đều phải bị từ chối trước khi fixture thực hiện; sự kiện phải liên kết được với phiên, máy đích và phiên bản chính sách.

Một yêu cầu đủ kiểm thử thường có các thành phần sau:

| Thành phần | Ví dụ trong phòng lab |
|---|---|
| Chủ thể | Danh tính thử nghiệm thuộc vai trò operations-readonly |
| Tài khoản thực thi | Tài khoản quản trị lab do PAM môi giới |
| Tài nguyên | lab-pam-01, dịch vụ demo-service |
| Tuyến truy cập | Một tuyến gateway và một loại phiên đã xác định |
| Hành vi được phép | Đọc trạng thái qua fixture lab-inspect |
| Hành vi bị cấm | Gọi fixture lab-mark dưới quyền đặc quyền |
| Điều kiện | Phiên còn hiệu lực, quyền JIT chưa hết hạn, đúng phạm vi máy |
| Thời điểm kiểm soát | Trước khi fixture bị cấm được thực thi |
| Bằng chứng | Quyết định chính sách, sự kiện phiên, quan sát độc lập tại máy đích |
| Hành vi sau từ chối | Phiên tiếp tục hoặc kết thúc theo hợp đồng đã xác định |

Cần tách danh tính con người khỏi tài khoản dùng trên máy đích. Nhiều người có thể truy cập qua cùng một tài khoản được vault quản lý; kết quả kiểm thử vẫn phải truy ngược được ai đã yêu cầu thao tác trong phiên nào.

## 5. Thiết kế môi trường lab và dữ liệu kiểm thử

### 5.1. Dùng fixture vô hại thay cho thao tác phá hủy

Không cần xóa dữ liệu thật hoặc dừng dịch vụ sản xuất để chứng minh bộ chặn hoạt động. Có thể dựng các fixture chỉ dùng trong phòng lab:

- `lab-inspect`: trả trạng thái giả lập của `demo-service`, đồng thời ghi sự kiện chứng minh fixture được gọi.
- `lab-mark`: nếu được thực thi, ghi một marker vô hại vào vùng lab do bộ kiểm thử quan sát.
- `lab-wrapper`: fixture kiểm tra đường gọi gián tiếp tới `lab-mark`, chỉ dùng khi phạm vi yêu cầu có bao gồm trường hợp này.

Các tên trên là tên minh họa, không phải tiện ích có sẵn của hệ điều hành hoặc sản phẩm PAM. Đội kiểm thử tự xây dựng, kiểm soát nội dung và xác minh hành vi của fixture trước khi dùng.

Fixture bị cấm cần được thiết kế sao cho việc gọi nó không làm thay đổi hệ thống ngoài vùng lab. Nếu cơ chế chặn lỗi, tác động quan sát được vẫn chỉ là một bằng chứng thử nghiệm.

### 5.2. Bảo vệ tính tin cậy của quan sát

Một marker đáng tin cần đáp ứng các điều kiện:

1. Mỗi lần chạy dùng một `run_id` duy nhất.
2. Người quan sát biết chính xác trạng thái ban đầu và vị trí marker.
3. Marker chỉ xuất hiện khi fixture thực sự thực hiện hành vi đã thiết kế.
4. Người dùng thử nghiệm không thể tự sửa hoặc xóa bằng chứng quan sát độc lập.
5. Bộ kiểm thử có thể phát hiện fixture hoặc nguồn quan sát đang hỏng.

Không nên đặt toàn bộ kết luận vào một file mà chính người dùng bị kiểm soát có thể sửa. Nếu tài khoản thực thi có quyền quản trị rộng, cần chọn nguồn quan sát có mức tin cậy phù hợp, chẳng hạn thu thập ra hệ thống tách biệt do nhóm kiểm thử quản lý.

Dùng một lần chạy đối chứng được phê duyệt để chứng minh rằng fixture có thể hoạt động và bộ quan sát nhìn thấy marker khi nó được phép chạy. Việc đối chứng thực hiện qua tài khoản hoặc chính sách lab được cấp riêng; không tắt kiểm soát của tuyến đang được đánh giá rồi coi đó là cùng một ca.

### 5.3. Chốt điều kiện nền trước mỗi lần chạy

Bản ghi chuẩn bị nên chứa:

~~~yaml
# Đặc tả kiểm thử minh họa, không phải cấu hình của sản phẩm PAM.
run_id: cb-run-042
target: lab-pam-01
route: approved-pam-route
human_identity: operator-test-01
execution_identity: privileged-lab-account
role: operations-readonly
policy_version: cb-lab-v3
expected_session_state: active
jit_state: valid
fixture_version: fixture-lab-v2
observer_state: healthy
baseline_marker: absent
~~~

Không ghi mật khẩu, private key hoặc token phiên vào đặc tả hay báo cáo. Khi cần chứng minh credential được vault cấp đúng, dùng mã tham chiếu và sự kiện cấp phát phù hợp thay vì giá trị bí mật.

Đồng bộ thời gian giữa nguồn log giúp dựng lại trình tự. Tuy nhiên, dấu thời gian trên nhiều máy có thể có sai lệch; ưu tiên thêm ID tương quan và thứ tự sự kiện từ cùng nguồn khi phân tích tính trước/sau.

## 6. Xây dựng ma trận kiểm thử

Một bộ kiểm thử chỉ có ca bị cấm có thể bỏ sót trường hợp hệ thống chặn mọi thứ. Cần cả ca được phép để kiểm tra chức năng vận hành.

| ID | Tình huống | Kỳ vọng theo hợp đồng lab | Bằng chứng trọng tâm |
|---|---|---|---|
| CB-01 | operations-readonly gọi lab-inspect đúng phạm vi | ALLOW | Fixture đọc được gọi, kết quả hợp lệ, có tương quan phiên |
| CB-02 | Cùng người dùng gọi lab-mark | DENY | Quyết định từ chối, fixture bị cấm không thực hiện |
| CB-03 | Đổi đối số lab-inspect sang phạm vi ngoài demo-service | DENY | Lý do từ chối gắn với phạm vi đối số |
| CB-04 | Nhập một yêu cầu không khớp thao tác được công bố | DENY nếu chính sách mặc định từ chối | Áp dụng đúng quy tắc mặc định |
| CB-05 | Vai trò khác gọi thao tác có quyền riêng | Theo quyền được cấp riêng | Phân biệt đúng chủ thể, không kế thừa nhầm quyền |
| CB-06 | lab-inspect chứa từ gần giống tên lệnh bị cấm trong dữ liệu hợp lệ | Theo hợp đồng phân tích đầu vào | Không nhầm dữ liệu với thao tác |
| CB-07 | Gọi qua kênh không tương tác đã nằm trong phạm vi | DENY đối với lab-mark | Chặn tại đúng kênh, quan sát trên máy đích |
| CB-08 | Fixture được phép thử tạo tiến trình con bị cấm | Theo phạm vi kiểm soát tiến trình con đã công bố | Quyết định và tác động của tiến trình con |
| CB-09 | Quyền JIT hết hạn hoặc bị thu hồi | Theo chính sách thu hồi đã quy định | Không tiếp tục sử dụng quyền ngoài thời hạn cam kết |
| CB-10 | Một nút PAM còn chính sách cũ | Không chấp nhận lệch phiên bản trong đợt nghiệm thu | Xác minh phiên bản thực tế trên từng tuyến |
| CB-11 | Thành phần đánh giá chính sách không khả dụng | Theo thiết kế lỗi đã phê duyệt | Có hoặc không thực thi đúng với chế độ lỗi |
| CB-12 | Lệnh bị từ chối rồi người dùng gửi lệnh hợp lệ | Tiếp tục hoặc từ chối phiên theo hợp đồng | Trạng thái phiên nhất quán sau vi phạm |

Các kỳ vọng trong bảng phải được chốt trước khi chạy. Không đổi kỳ vọng để phù hợp với kết quả quan sát được.

Với ca CB-06, một bộ lọc văn bản có thể cố ý từ chối bất kỳ dòng chứa mẫu nhất định. Khi đó, bài kiểm thử phải đánh giá đúng hợp đồng đó và ghi rõ giới hạn sử dụng. Không áp đặt kỳ vọng của bộ phân tích chương trình/đối số lên một cơ chế chỉ cam kết lọc văn bản.

Ca CB-08 cũng cần phân biệt: cho phép chương trình cha chạy không đồng nghĩa cho phép mọi thao tác mà chương trình cha có thể thực hiện. Nếu sản phẩm không kiểm soát tiến trình con, kết quả này là một giới hạn cần xử lý trong thiết kế quyền, không phải bằng chứng rằng chức năng được hỗ trợ nhưng hoạt động đúng.

## 7. Kiểm thử ca được phép trước

Bắt đầu bằng thao tác đọc hợp lệ để xác nhận các điều kiện nền: kết nối, cấp phiên, tài khoản đích, nguồn quan sát và fixture.

Ví dụ yêu cầu thao tác dưới dạng cấu trúc:

~~~yaml
# Yêu cầu minh họa cho bộ chuyển tiếp kiểm thử trong lab.
operation:
  executable: /opt/pam-lab/bin/lab-inspect
  arguments:
    - --scope
    - demo-service
expected:
  decision: ALLOW
  fixture_observed: true
  protected_state_changed: false
~~~

Khi triển khai trên sản phẩm thật, bộ chuyển tiếp phải gửi thao tác bằng đúng loại kênh đang được đánh giá. Nếu kiểm thử terminal, thao tác phải đi qua terminal; nếu kiểm thử API môi giới lệnh, phải đi qua API đó. Gọi thẳng fixture từ một đường quản trị khác chỉ có giá trị đối chứng và không chứng minh tuyến PAM đang hoạt động.

Một ca được phép đạt yêu cầu khi:

- Đúng danh tính và đúng phiên gửi yêu cầu.
- Quyết định hoặc kết quả thực thi phù hợp với chính sách đã chốt.
- Fixture đọc thực sự chạy và trả dữ liệu mong đợi.
- Không phát sinh thay đổi tài nguyên ngoài tác dụng phụ lab đã dự kiến.
- Bằng chứng tương quan được với chính phiên và máy đích.

Nếu ca này thất bại vì fixture không tồn tại, chưa đủ điều kiện kết luận về bộ chặn. Cần sửa điều kiện lab hoặc đánh dấu INCONCLUSIVE cho các ca phụ thuộc.

## 8. Kiểm thử ca bị cấm theo trình tự đầy đủ

### 8.1. Chuẩn bị

Ghi lại policy version, quyền hiện tại, session ID, target ID và baseline marker. Xác nhận nguồn thu thập bằng chứng đang hoạt động. Chuẩn bị một `run_id` mới và xác định giới hạn thời gian quan sát phù hợp với độ trễ thực tế của pipeline log.

Lệnh thử nghiệm phải được xây dựng trước, chẳng hạn:

~~~yaml
# Đặc tả ca thử minh họa, không phải cú pháp policy PAM.
test_case:
  id: CB-02
  run_id: cb-run-043
  subject_role: operations-readonly
  operation:
    executable: /opt/pam-lab/bin/lab-mark
    arguments:
      - --run-id
      - cb-run-043
  expected:
    decision: DENY
    forbidden_fixture_executed: false
    marker_created: false
    session_after_denial: active
~~~

Trong ví dụ này, chính sách lab phải từ chối fixture theo đối tượng thao tác phù hợp, không chỉ theo một giá trị `run_id` cố định. Nếu cấu trúc đối số thay đổi, cần kiểm tra rằng yêu cầu thử vẫn nằm trong điều kiện chính sách muốn đánh giá.

### 8.2. Gửi yêu cầu qua tuyến được kiểm thử

Gửi đúng một lần, ghi lại thời điểm và request ID nếu có. Không tự động gửi lại khi chưa biết lần đầu đã được tiếp nhận hay chưa: retry có thể tạo nhiều yêu cầu và làm khó đối chiếu.

Ghi riêng các tín hiệu:

- Phản hồi hiển thị cho người dùng.
- Quyết định từ lớp kiểm soát PAM.
- Sự kiện thực thi hoặc từ chối tại máy đích, nếu kiến trúc cung cấp.
- Quan sát fixture và marker.
- Trạng thái phiên sau yêu cầu.

Phản hồi giao diện là một nguồn dữ liệu trong tập bằng chứng, không phải kết luận cuối cùng.

### 8.3. Đợi đủ bằng chứng

Pipeline log có thể chuyển sự kiện bất đồng bộ. “Chưa thấy marker sau một giây” không tự động tương đương “fixture không chạy”.

Bộ kiểm thử cần có cách xác nhận khoảng quan sát đã được thu thập đủ: ví dụ tiến độ thu nhận từ nguồn, tín hiệu kết thúc lượt thu hoặc cơ chế xác nhận tương đương đã được thiết kế. Nếu nguồn không cung cấp được bảo đảm đó, kết luận phải phản ánh giới hạn quan sát.

Giới hạn thời gian chờ nên dựa trên đặc điểm đo được của môi trường. Hết thời gian mà không có bằng chứng đầy đủ thì trả INCONCLUSIVE; không chuyển thành PASS vì không thấy sự kiện.

### 8.4. Đối chiếu

Một kết quả chặn đạt yêu cầu theo hợp đồng ví dụ cần có:

1. Yêu cầu được nhận trên đúng tuyến, đúng phiên và đúng tài khoản đích.
2. Chính sách đúng phiên bản ra quyết định DENY trước hành vi được bảo vệ.
3. Nguồn quan sát đủ phạm vi không ghi nhận fixture thực hiện hay marker xuất hiện.
4. Bằng chứng cho quyết định và bằng chứng tại đích cùng liên kết tới lượt thử.
5. Trạng thái phiên sau từ chối đúng như đặc tả.

Nếu marker xuất hiện dù quyết định là DENY, yêu cầu phòng ngừa đã thất bại. Cần giữ cả hai bằng chứng để điều tra thứ tự thực thi, điểm chặn và khả năng gắn nhầm phiên.

## 9. Kiểm tra các ranh giới của chính sách

### 9.1. Đường dẫn và tên chương trình

Hai chương trình có cùng tên ngắn có thể nằm ở các vị trí khác nhau. Một đường dẫn có thể trỏ tới nội dung thay đổi nếu quyền trên file hoặc thư mục không được bảo vệ.

Tùy cách triển khai, bộ kiểm thử cần xác minh:

- Chính sách so khớp tên, đường dẫn hay danh tính chương trình được quản lý.
- Người dùng có thể thay thế chương trình hoặc thay đổi thành phần đường dẫn hay không.
- Kết quả có phụ thuộc vào môi trường tìm kiếm chương trình không.
- Nếu có cơ chế xác thực nội dung chương trình, trạng thái kiểm tra đó có được quan sát không.

Dùng các bản fixture vô hại được tạo sẵn để kiểm tra ranh giới. Không tự kết luận một phép biến đổi đường dẫn luôn tương đương trên mọi hệ điều hành và mọi bộ phân tích.

### 9.2. Đối số và phạm vi tài nguyên

Cho phép một chương trình không có nghĩa là mọi đối số đều an toàn. Một công cụ có thể hỗ trợ cả xem và sửa, hoặc lựa chọn nhiều tài nguyên có mức nhạy cảm khác nhau.

Trong lab, có thể kiểm tra các nhóm:

- Đúng đối số và đúng tài nguyên được cấp.
- Thiếu đối số bắt buộc.
- Tài nguyên ngoài phạm vi được cấp.
- Đối số lặp hoặc tổ hợp mâu thuẫn.
- Giá trị rỗng, độ dài lớn và ký tự được parser chấp nhận.
- Dữ liệu đầu vào có chứa tên gần giống thao tác bị cấm.

Kỳ vọng phải xuất phát từ cách phân tích đầu vào thực tế và yêu cầu nghiệp vụ. Không tự chuẩn hóa dữ liệu theo một quy tắc khác với lớp thực thi, vì hai bên có thể hiểu thành hai thao tác khác nhau.

### 9.3. Shell, script và tiến trình con

Nếu người dùng được cấp shell hoặc chương trình có khả năng thực thi thao tác khác, một danh sách tên lệnh ở lớp nhập liệu có thể không bao phủ được toàn bộ hành vi phía sau.

Bộ kiểm thử nên dùng fixture được kiểm soát để xác định liệu hành vi bị cấm qua chương trình cha có nằm trong phạm vi kiểm soát hay không. Không cần dùng chuỗi lệnh phá hủy hoặc tải mã ngoài để chứng minh điểm này.

Nếu yêu cầu là chỉ cấp vài thao tác quản trị cụ thể, có thể cân nhắc thiết kế endpoint hoặc wrapper được bảo vệ chỉ công bố đúng các thao tác đó. Khi thay đổi thiết kế, cần kiểm thử lại cả quyền của wrapper, đối số, tài nguyên và cách tạo tiến trình; bản thân wrapper không tự tạo ra một ranh giới quyền đáng tin.

### 9.4. Kênh truy cập và tài khoản dịch vụ

Liệt kê riêng các tuyến có thể thực hiện công việc:

- Phiên terminal tương tác.
- Kênh thực thi một thao tác không tương tác.
- Tác vụ tự động dùng danh tính dịch vụ.
- API quản trị hoặc công cụ môi giới thao tác.
- Đường truy cập trực tiếp tới máy đích.
- Tuyến khẩn cấp được cấp theo quy trình break-glass.

Chỉ đánh dấu phạm vi đã kiểm chứng cho tuyến thực sự được thử. Nếu tuyến trực tiếp nằm ngoài cơ chế command blocking, phải ghi rõ ranh giới đó và cơ chế nào bảo vệ tuyến trực tiếp.

Đối với tài khoản dịch vụ, cần thử bằng đúng danh tính workload hoặc tác vụ thực tế trong lab. Quyền của người vận hành không đại diện cho quyền của pipeline tự động.

## 10. Quyền JIT, thu hồi và thay đổi chính sách

### 10.1. Khi quyền hết hạn

Chính sách có thể đánh giá quyền tại lúc mở phiên, tại từng thao tác hoặc theo một cơ chế làm mới khác. Hãy chốt hành vi mong đợi cho phiên đang mở khi quyền JIT hết hạn.

Các ca cần tách riêng:

1. Mở phiên mới sau khi quyền hết hạn.
2. Gửi thao tác mới trong phiên đã tồn tại.
3. Tiến trình đã khởi chạy trước khi quyền hết hạn vẫn đang chạy.
4. Yêu cầu nằm trong hàng đợi khi quyền bị thu hồi.

Từ chối thao tác mới không chứng minh tiến trình cũ đã bị dừng. Nếu yêu cầu có bao gồm kết thúc tiến trình đang chạy, phải có ca kiểm thử riêng và bằng chứng tại máy đích.

### 10.2. Khi cập nhật chính sách

Một bản policy mới xuất hiện ở giao diện quản trị chưa chứng minh mọi nút thực thi đang dùng bản đó. Ghi lại phiên bản mà mỗi nút hoặc mỗi phiên thực tế sử dụng, theo khả năng quan sát của hệ thống.

Kiểm tra tối thiểu:

- Phiên mới sau thời điểm triển khai.
- Phiên đang mở trước thời điểm triển khai.
- Các tuyến đi qua nút gateway hoặc điểm thực thi khác nhau.
- Tình huống cập nhật chưa hoàn thành trên toàn bộ phạm vi lab.

Nếu không truy xuất được phiên bản thực tế, ghi giới hạn bằng chứng. Không điền phiên bản mong muốn vào báo cáo như thể đó là phiên bản quan sát được.

## 11. Kiểm thử khi thành phần kiểm soát gặp lỗi

Một hệ thống có thể từ chối thao tác khi không đánh giá được chính sách, hoặc dùng một chính sách cục bộ đã được phê duyệt với thời hạn xác định. Hành vi được chấp nhận phụ thuộc thiết kế và yêu cầu vận hành.

Cần chốt cách xử lý trước khi mô phỏng lỗi:

| Sự cố lab | Câu hỏi cần kiểm chứng |
|---|---|
| Dịch vụ quyết định chính sách không phản hồi | Thao tác bị từ chối, chờ hay tiếp tục theo cơ chế nào? |
| Policy cục bộ đã quá hạn | Hệ thống có nhận biết và xử lý đúng điều kiện hết hạn không? |
| Mất kết nối giữa gateway và máy đích | Yêu cầu đã đến đích chưa, và có nguy cơ gửi lặp không? |
| Nguồn audit gián đoạn | Kiểm soát thực thi còn hoạt động không, và kết luận kiểm thử có đủ bằng chứng không? |
| Điểm thực thi khởi động lại | Chính sách được nạp trước khi nhận thao tác mới hay không? |

Phân biệt hai kết luận: “hành vi điều khiển đúng thiết kế” và “bằng chứng kiểm thử đầy đủ”. Cơ chế thực thi có thể vẫn chặn đúng khi audit bị gián đoạn, nhưng đội kiểm thử chưa chắc có đủ dữ liệu để nghiệm thu lần chạy đó.

Chỉ mô phỏng sự cố trong phạm vi lab đã chuẩn bị. Ghi rõ thời điểm bắt đầu, điều kiện khôi phục và các nguồn quan sát bị ảnh hưởng để tránh nhầm lỗi hạ tầng với lỗi quyết định chính sách.

## 12. Tự động hóa kiểm chứng với kết quả ba trạng thái

Bộ kiểm thử không nên chuyển mọi lỗi thành “đã chặn”. Ví dụ, lỗi timeout trước khi mở phiên không phải thành công của ca kiểm thử chặn lệnh trong phiên.

Mã giả sau mô tả cách phân loại; các hàm là giao diện giả định của bộ kiểm thử, không phải API của sản phẩm PAM:

~~~text
function verifyBlocked(testCase):
    baseline = observer.captureBaseline(testCase.runId)
    if not baseline.isHealthy:
        return INCONCLUSIVE("Nguồn quan sát chưa sẵn sàng")

    session = access.openApprovedLabSession(testCase.context)
    if not session.isReady:
        return INCONCLUSIVE("Chưa tạo được phiên đúng điều kiện")

    submission = route.submitOnce(session, testCase.operation)
    if not submission.acceptanceKnown:
        return INCONCLUSIVE("Chưa xác định yêu cầu đã được tiếp nhận")

    evidence = collector.awaitCompleteWindow(
        sessionId = session.id,
        requestId = submission.requestId,
        runId = testCase.runId
    )

    if evidence.provesForbiddenAction:
        return FAIL("Hành vi bị cấm đã xảy ra")

    if not evidence.coverageComplete:
        return INCONCLUSIVE("Khoảng quan sát chưa đầy đủ")

    if not evidence.identityAndPolicyMatch:
        return INCONCLUSIVE("Không xác nhận được điều kiện thử")

    if evidence.decision == ALLOW:
        return FAIL("Quyết định trái với kỳ vọng DENY")

    if evidence.decision != DENY:
        return INCONCLUSIVE("Thiếu quyết định có thể đối chiếu")

    if not evidence.preExecutionDenialEstablished:
        return INCONCLUSIVE("Chưa chứng minh từ chối trước thực thi")

    if not evidence.sessionStateMatchesContract:
        return FAIL("Trạng thái phiên sau từ chối không đúng")

    return PASS("Từ chối đúng và không có hành vi bị cấm")
~~~

Điều kiện `coverageComplete` cần được hiện thực bằng cơ chế quan sát có căn cứ trong môi trường cụ thể. Không đặt giá trị này thành true chỉ vì đã chờ một khoảng thời gian cố định.

Nếu nguồn chứng minh hành vi bị cấm đã xảy ra, ca phòng ngừa phải FAIL dù các nguồn khác còn thiếu. Thiếu dữ liệu chỉ cản trở việc chứng minh thành công, không xóa bỏ bằng chứng thất bại đã xác thực.

Bộ tự động hóa cũng cần chạy các ca ALLOW. Một hệ thống luôn trả DENY có thể vượt qua toàn bộ ca âm tính nhưng không đáp ứng quyền vận hành hợp lệ.

## 13. Thiết kế bằng chứng phục vụ kiểm toán và điều tra

Một gói bằng chứng cho mỗi ca nên bao gồm:

- Mã ca, `run_id`, mục tiêu và kỳ vọng đã chốt.
- Danh tính người yêu cầu, tài khoản thực thi, vai trò và phạm vi JIT.
- Mã phiên, mã yêu cầu, máy đích và tuyến truy cập.
- Phiên bản chính sách mong đợi và phiên bản quan sát được.
- Thao tác thử ở dạng đủ nhận diện nhưng đã che dữ liệu nhạy cảm.
- Quyết định, mã quy tắc hoặc lý do từ chối nếu hệ thống cung cấp.
- Bằng chứng tại máy đích và tình trạng nguồn quan sát.
- Trạng thái phiên, kết luận và giới hạn của lần chạy.

Một bản ghi rút gọn có thể có dạng:

~~~json
{
  "caseId": "CB-02",
  "runId": "cb-run-043",
  "sessionId": "session-lab-218",
  "requestId": "request-lab-663",
  "target": "lab-pam-01",
  "humanIdentity": "operator-test-01",
  "executionIdentity": "privileged-lab-account",
  "role": "operations-readonly",
  "policyVersionObserved": "cb-lab-v3",
  "decision": "DENY",
  "reason": "operation-not-permitted",
  "forbiddenFixtureObserved": false,
  "markerObserved": false,
  "observerCoverage": "complete-for-test-scope",
  "preExecutionDenialEstablished": true,
  "sessionAfterDenial": "active",
  "result": "PASS"
}
~~~

Bản ghi JSON là bản tổng hợp. Các trường `false`, `complete-for-test-scope` và `true` phải truy được về bằng chứng nguồn; chúng không tự chứng minh điều gì nếu chỉ do bộ kiểm thử điền theo kỳ vọng.

Không lưu nguyên token phiên hoặc credential vault vào log. Dòng lệnh và đối số cũng có thể chứa bí mật; chọn dữ liệu giả trong lab và áp dụng cách che dữ liệu phù hợp khi xuất báo cáo. Giữ đủ định danh thao tác để đối chiếu mà không phát tán bí mật.

## 14. Phân loại kết quả và lỗi thường gặp

| Quan sát | Kết luận hợp lý | Hành động tiếp theo |
|---|---|---|
| DENY, đúng điều kiện, nguồn quan sát đầy đủ, không có hành vi bị cấm | PASS theo phạm vi đã thử | Lưu bằng chứng và tiếp tục ca khác |
| Giao diện báo chặn nhưng marker đã xuất hiện | FAIL yêu cầu phòng ngừa | Đối chiếu điểm chặn, thứ tự và tương quan |
| Không có marker nhưng fixture đối chứng cũng không chạy được | INCONCLUSIVE | Sửa fixture hoặc điều kiện lab rồi chạy lượt mới |
| Không tạo được phiên | INCONCLUSIVE cho ca chặn lệnh trong phiên | Kiểm tra cấp phiên và điều kiện đầu vào |
| Quyết định ALLOW cho thao tác phải bị cấm | FAIL quyết định chính sách | Kiểm tra phạm vi rule, ưu tiên và policy version |
| Tất cả ca đều bị từ chối, kể cả thao tác hợp lệ | FAIL bộ yêu cầu chức năng | Xác định lỗi cấp quyền hoặc rule quá rộng |
| Chỉ thấy audit không có thao tác, nhưng pipeline đang mất dữ liệu | INCONCLUSIVE | Khôi phục quan sát, không suy ra “không thực thi” |
| Terminal chặn đúng nhưng kênh thuộc phạm vi khác vẫn thực hiện được | FAIL yêu cầu bao phủ tuyến đó | Xác định lớp kiểm soát còn thiếu |
| Phiên đóng đúng nhưng tiến trình bị cấm đã chạy trước đó | FAIL yêu cầu chặn trước thực thi | Tách phản ứng kết thúc phiên khỏi ngăn chặn |

Những sai lầm phổ biến gồm:

1. Chỉ chụp màn hình thông báo từ chối và bỏ qua máy đích.
2. Dùng mã thoát khác không làm bằng chứng duy nhất.
3. Không có ca được phép nên không phát hiện chặn quá mức.
4. Không ghi tài khoản đích nên nhầm quyền của người dùng với quyền tài khoản dùng chung.
5. Thử trên một nút rồi suy rộng sang mọi nút.
6. Gắn kết quả retry vào yêu cầu ban đầu.
7. Dùng marker cũ hoặc xóa baseline không có kiểm soát.
8. Gọi phản ứng sau thực thi là chặn trước thực thi.
9. Coi nguồn audit không có sự kiện là chứng minh chắc chắn không có hành vi.
10. Cho phép công cụ tổng quát nhưng không đánh giá các khả năng ngoài thao tác được dự kiến.

## 15. Tình huống thực hành: quyền xem trạng thái cho đội vận hành

### Bối cảnh

Đội vận hành được cấp JIT để xem trạng thái `demo-service` qua PAM. Credential của tài khoản máy đích do vault quản lý; người dùng không cần biết giá trị credential. Chính sách lab cho phép fixture đọc và từ chối fixture tạo marker.

### Lượt chạy thứ nhất

- Ca ALLOW gọi `lab-inspect` thành công.
- Ca DENY nhận thông báo “operation blocked”.
- Marker của ca DENY vẫn xuất hiện.
- Log quyết định được phát sinh sau sự kiện fixture tại cùng nguồn quan sát đáng tin.

Kết luận: FAIL đối với yêu cầu ngăn hành vi trước thực thi. Việc có log chặn không bù được tác động đã xảy ra.

Nhóm kỹ thuật cần kiểm tra điểm thực thi chính sách, chế độ cấu hình thực tế và cách yêu cầu được chuyển tiếp. Chưa được tự kết luận nguyên nhân chỉ từ một trường trạng thái trong log.

### Lượt chạy thứ hai sau khi điều chỉnh

- Policy version thực tế được xác nhận là `cb-lab-v4`.
- Ca ALLOW vẫn hoạt động.
- Ca DENY có quyết định đúng phiên bản.
- Nguồn quan sát xác nhận khoảng kiểm thử đầy đủ và không có fixture bị cấm thực hiện.
- Trạng thái phiên sau từ chối đúng đặc tả.

Kết luận: PASS cho các ca, tuyến và điều kiện đã thử ở lượt thứ hai. Kết quả không tự bao phủ tác vụ tự động, truy cập trực tiếp hoặc tuyến khẩn cấp chưa được đưa vào ma trận.

### Bài tập

Thiết kế thêm ba ca cho tình huống trên:

1. Quyền JIT hết hạn trong lúc phiên đang mở.
2. Một tác vụ dịch vụ gọi thao tác tương tự qua tuyến tự động.
3. Một nút gateway chưa nhận bản chính sách mới.

Với mỗi ca, ghi điều kiện đầu vào, kỳ vọng, bằng chứng cần có và điều kiện khiến kết quả là INCONCLUSIVE.

Gợi ý tự kiểm tra: ca thứ nhất cần chốt cách xử lý phiên tồn tại; ca thứ hai cần dùng đúng danh tính dịch vụ; ca thứ ba cần quan sát policy version thực tế thay vì chỉ xem bản cấu hình trung tâm.

## 16. Điều kiện hoàn thành bộ kiểm thử

Một bộ kiểm thử command blocking đủ cơ sở nghiệm thu khi:

- Các hành vi được phép và bị cấm đã được định nghĩa thành ca cụ thể.
- Phạm vi tuyến, tài khoản, máy đích, đối số và thời điểm quyết định được ghi rõ.
- Fixture và nguồn quan sát đã được kiểm chứng bằng đối chứng phù hợp.
- Có cả ca ALLOW, DENY, ranh giới và lỗi theo phạm vi yêu cầu.
- Kết luận về chặn trước thực thi dựa trên quyết định cùng quan sát hành vi.
- Mọi kết quả PASS có bằng chứng tương quan và không còn khoảng trống quan sát quan trọng.
- Ca FAIL và INCONCLUSIVE được giữ lại với nguyên nhân hoặc bước xử lý tiếp theo.
- Các tuyến và khả năng chưa hỗ trợ được ghi rõ để phục vụ thiết kế kiểm soát bổ sung.
- Báo cáo không chứa credential và có thể truy ngược tới bằng chứng nguồn.

Kiểm thử đạt yêu cầu không chỉ chứng minh một mẫu lệnh bị nhận diện. Nó chứng minh trong điều kiện được mô tả, đúng chủ thể bị giới hạn ở đúng thao tác, tại đúng điểm thực thi, và kết luận đó có thể được kiểm tra lại bằng bằng chứng.
