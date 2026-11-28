# Yêu cầu configuration

## 1. Cấu hình là một phần của hợp đồng bảo mật

Một hệ thống có thể dùng thư viện xác thực đúng cách nhưng vẫn cho phép đăng nhập thiếu bước xác minh vì một cờ cấu hình bị tắt. Cơ chế phân quyền có thể được thiết kế cẩn thận nhưng bị vô hiệu hóa bởi chế độ phát triển được bật trong môi trường sản xuất. Khi đó, lỗi nằm ở trạng thái triển khai thực tế, dù mã nguồn đã vượt qua nhiều bài kiểm thử.

Trong chương **Verification framework**, yêu cầu configuration là yêu cầu bảo mật đối với cách hệ thống định nghĩa, cung cấp, kiểm tra, thay đổi và vận hành cấu hình. Mục tiêu là biến các mục tiêu an toàn thông tin và kết quả mô hình đe dọa thành điều kiện cụ thể, đo được và có bằng chứng kiểm chứng.

Một yêu cầu tốt phải trả lời được:

- Giá trị hoặc ràng buộc nào bắt buộc tại từng môi trường?
- Ai được thay đổi, qua kênh nào và với quyền gì?
- Hệ thống xử lý thế nào khi giá trị thiếu, sai, hết hạn hoặc không đáng tin?
- Làm sao xác định cấu hình thực sự đang có hiệu lực?
- Kiểm thử nào chứng minh yêu cầu được đáp ứng, trên phiên bản nào?

Bài học sử dụng ví dụ một dịch vụ quản lý hồ sơ đa khách hàng, có API, cổng quản trị, kho secret, dịch vụ phân quyền và pipeline triển khai. Các mã yêu cầu, ngưỡng thời gian và quy trình dưới đây là **đặc tả minh họa cho hệ thống giả định**, cần được điều chỉnh theo rủi ro và mục tiêu vận hành của sản phẩm thực tế. Chúng không phải các mức bắt buộc chung cho mọi hệ thống.

## 2. Xác định phạm vi và các loại cấu hình

Configuration bao gồm nhiều thứ hơn một tệp YAML. Cấu hình có thể được tạo từ manifest triển khai, biến môi trường, tham số khởi động, cờ tính năng, chính sách của nền tảng và dữ liệu quản trị được nạp khi chạy.

| Nhóm cấu hình | Ví dụ | Rủi ro cần chuyển thành yêu cầu |
| --- | --- | --- |
| Xác thực và phiên | Bước xác minh bổ sung, thời hạn phiên, danh sách bên phát hành token | Giảm mức xác thực, chấp nhận phiên ngoài chính sách |
| Phân quyền | Chế độ kiểm tra quyền, chính sách tenant, quyền quản trị | Bỏ qua kiểm tra quyền, truy cập chéo tenant |
| Bảo vệ dữ liệu | Bật mã hóa, tham chiếu khóa, thời hạn lưu dữ liệu | Dữ liệu không được bảo vệ hoặc lưu quá thời hạn đã duyệt |
| Kết nối | Đích kết nối, kiểm tra chứng thư, danh sách nguồn truy cập | Kết nối đến đích giả, lộ dữ liệu qua kênh không được phép |
| Logging và giám sát | Loại sự kiện, che dữ liệu, đích nhận log | Mất dấu thay đổi hoặc ghi lộ secret |
| Chế độ vận hành | Debug, endpoint chẩn đoán, cờ thử nghiệm | Lộ thông tin nội bộ, xuất hiện đường truy cập ngoài dự kiến |
| Khả dụng và phục hồi | Timeout, retry, giới hạn tài nguyên, nguồn cấu hình dự phòng | Cạn tài nguyên, phục hồi bằng cấu hình không còn an toàn |

Cần phân biệt:

**Cấu hình mong muốn** là trạng thái đã được phê duyệt trong nguồn chuẩn.

**Cấu hình có hiệu lực** là kết quả sau khi áp dụng giá trị mặc định, thứ tự ưu tiên nguồn, nội suy và chuyển đổi kiểu, tại một tiến trình cụ thể.

**Baseline bảo mật** là tập ràng buộc mà cấu hình có hiệu lực phải tuân thủ. Baseline có thể quy định một giá trị chính xác hoặc quan hệ giữa nhiều giá trị, chẳng hạn thời hạn chờ không vượt quá thời hạn phiên.

**Drift** là sai lệch giữa trạng thái mong muốn và trạng thái thực tế, hoặc giữa trạng thái thực tế và baseline. Một cấu hình đúng với tệp triển khai vẫn có thể vi phạm baseline nếu chính tệp đó chứa giá trị không an toàn.

Verification phải kiểm tra cả bốn khía cạnh. Chỉ so sánh tệp trong repository không chứng minh được trạng thái đang chạy.

## 3. Đi từ mô hình đe dọa đến yêu cầu cấu hình

### 3.1. Xác định tài sản và ranh giới tin cậy

Trong ví dụ này, các tài sản cần bảo vệ gồm hồ sơ khách hàng, khóa truy cập dịch vụ, phiên quản trị, chính sách phân quyền và lịch sử thay đổi.

Những ranh giới cần xét gồm:

1. Người sửa cấu hình với người phê duyệt và phát hành cấu hình.
2. Pipeline triển khai với hệ thống cấu hình của môi trường sản xuất.
3. Kho secret với tiến trình sử dụng secret.
4. Cổng quản trị với API quản lý cấu hình.
5. Cấu hình toàn hệ thống với cấu hình dành riêng cho từng tenant.

Mỗi ranh giới phải có cách xác thực chủ thể, giới hạn quyền và ghi nhận hoạt động phù hợp. Không mặc định rằng người có quyền sửa một biến môi trường cũng được phép tắt kiểm tra phân quyền.

### 3.2. Lập chuỗi truy vết

Một chuỗi truy vết có thể bắt đầu như sau:

> Mục tiêu: bảo vệ hồ sơ giữa các tenant → rủi ro: người vận hành tắt kiểm tra tenant bằng cờ cấu hình → yêu cầu: cấu hình sản xuất không có khả năng bỏ qua kiểm tra tenant → kiểm thử: mọi cách đưa cờ bỏ qua vào cấu hình đều bị từ chối trước kích hoạt.

| Rủi ro | Kịch bản lạm dụng | Yêu cầu liên quan | Bằng chứng cần có |
| --- | --- | --- | --- |
| R-01: giảm mức bảo vệ | Thay cấu hình sản xuất để bật debug hoặc tắt kiểm tra quyền | CFG-02, CFG-03, CFG-04 | Kết quả kiểm tra baseline và thử kích hoạt cấu hình sai |
| R-02: thay đổi trái phép | Người chỉ có quyền xem gọi API cập nhật cấu hình | CFG-01, CFG-06 | Kiểm thử phân quyền và sự kiện từ chối |
| R-03: lộ secret | Giá trị bí mật xuất hiện trong biến cấu hình, log hoặc bằng chứng kiểm thử | CFG-05, CFG-09 | Kết quả kiểm tra luồng secret và bản log đã che dữ liệu |
| R-04: trạng thái không nhất quán | Một số instance giữ chính sách cũ sau khi thay đổi | CFG-07, CFG-08 | Bằng chứng hội tụ, kiểm tra readiness và drift |
| R-05: phục hồi làm tái xuất hiện lỗ hổng | Rollback đưa về cấu hình đã bị thu hồi | CFG-10 | Kết quả diễn tập rollback và kiểm tra phiên bản được phép |
| R-06: vượt ranh giới tenant | Quản trị viên tenant sửa tham số bảo mật toàn hệ thống | CFG-01, CFG-04 | Kiểm thử chéo tenant và kiểm tra schema theo phạm vi |

Đường truy vết phải đi được cả hai chiều: từ một yêu cầu tìm ra rủi ro mà nó xử lý, và từ rủi ro tìm ra các yêu cầu cùng bằng chứng kiểm chứng. Một rủi ro có thể cần nhiều yêu cầu; một yêu cầu cũng có thể giảm nhiều rủi ro.

## 4. Cấu trúc của một yêu cầu có thể kiểm chứng

Không nên viết: “Hệ thống phải hỗ trợ cấu hình an toàn”. Người triển khai và người kiểm thử không có cơ sở thống nhất để quyết định đạt hay không đạt.

Một yêu cầu configuration nên có các thành phần sau:

| Thành phần | Nội dung cần đặc tả |
| --- | --- |
| Định danh và mục tiêu | Mã duy nhất, tài sản được bảo vệ, rủi ro liên quan |
| Phạm vi | Môi trường, dịch vụ, tenant, instance và loại cấu hình áp dụng |
| Chủ thể | Người hoặc thành phần được phép thực hiện hành động |
| Điều kiện kích hoạt | Khởi động, triển khai, reload, thay đổi secret hoặc phục hồi |
| Quy tắc | Giá trị, miền giá trị, quan hệ giữa các trường và nguồn được phép |
| Hành vi lỗi | Từ chối, tiếp tục dùng bản đã xác minh, rút instance khỏi lưu lượng hoặc hành động cụ thể khác |
| Chỉ số | Mốc bắt đầu, mốc kết thúc, giới hạn và cách quan sát |
| Kiểm chứng | Ca dương, ca âm, thử lỗi phụ thuộc và bằng chứng cần lưu |
| Trách nhiệm | Người sở hữu yêu cầu, người triển khai và người xác nhận |

Ví dụ cụ thể:

> **CFG-03:** Trong môi trường sản xuất, trước khi một instance nhận lưu lượng hoặc kích hoạt cấu hình mới, hệ thống phải xác minh rằng chế độ debug bị tắt, endpoint quản trị không được công khai và kiểm tra quyền luôn được thực hiện. Nếu bất kỳ điều kiện nào không đạt, cấu hình mới không được kích hoạt. Instance chưa có cấu hình hợp lệ không được báo sẵn sàng phục vụ. Kết quả kiểm tra phải ghi mã yêu cầu, phiên bản baseline và phiên bản cấu hình, không ghi giá trị secret.

Câu này xác định rõ thời điểm kiểm tra, điều kiện đạt, hành vi khi lỗi và bằng chứng. Chi tiết về cơ chế kiểm tra nằm trong thiết kế triển khai nhưng phải đủ để thực hiện đúng hợp đồng đó.

Không gộp tất cả yêu cầu vào một câu dài như ví dụ trên khi quản lý trong công cụ thực tế. Có thể chia thành các tiêu chí chấp nhận để từng điều kiện có kết quả riêng.

## 5. Baseline và hợp đồng nguồn cấu hình

### 5.1. Định nghĩa baseline theo môi trường

Môi trường phát triển, kiểm thử và sản xuất có thể cần các giá trị khác nhau. Điều đó không có nghĩa môi trường kiểm thử được phép dùng secret thật của sản xuất hoặc được phép tùy ý bỏ qua phân quyền.

| Thuộc tính | Phát triển cục bộ | Kiểm thử tích hợp | Sản xuất |
| --- | --- | --- | --- |
| Danh tính truy cập dịch vụ | Danh tính riêng cho môi trường | Danh tính kiểm thử được giới hạn | Danh tính vận hành được phê duyệt |
| Dữ liệu | Dữ liệu giả | Dữ liệu tổng hợp hoặc đã xử lý theo chính sách | Dữ liệu trong phạm vi được cấp quyền |
| Debug | Có thể bật trong phạm vi cục bộ được quy định | Chỉ bật theo profile kiểm thử đã duyệt | Tắt |
| Secret | Không dùng secret sản xuất | Không dùng secret sản xuất | Lấy từ nguồn secret được cho phép |
| Kiểm tra phân quyền | Luôn thực hiện trong luồng cần kiểm chứng | Luôn thực hiện | Luôn thực hiện |
| Ngoại lệ | Có giới hạn và không được phát hành sang môi trường khác | Có giới hạn và có thời hạn | Theo cơ chế ngoại lệ được phê duyệt |

Nếu cần mô phỏng cơ chế xác thực trong kiểm thử, phải coi đó là một profile riêng, dùng danh tính và hạ tầng riêng. Cần có kiểm tra ngăn profile này đi vào sản xuất.

Baseline cũng cần được quản lý phiên bản. Khi baseline thay đổi, kết quả “PASS” của phiên bản cũ không tự chứng minh bản phát hành mới đã đáp ứng baseline mới.

### 5.2. Đặc tả thứ tự ưu tiên nguồn

Cùng một khóa có thể xuất hiện trong tệp, biến môi trường và cổng quản trị. Nếu không quy định thứ tự ưu tiên, người vận hành có thể tưởng rằng đã tắt debug trong manifest nhưng tiến trình vẫn nhận giá trị bật từ nguồn khác.

Trong thiết kế minh họa:

- Giá trị mặc định trong mã chỉ là đầu vào ban đầu; mọi trường bắt buộc vẫn phải được kiểm tra.
- Các trường bảo mật lấy từ bundle cấu hình đã được phê duyệt và xác minh nguồn gốc.
- Biến môi trường chỉ được cung cấp các trường có trong danh sách cho phép, chẳng hạn tham chiếu tới bundle hoặc secret.
- Cổng quản trị chỉ được sửa các trường vận hành đã được phân quyền; không được tạo đường ghi trực tiếp vượt baseline.
- Giá trị có hiệu lực sau hợp nhất phải tiếp tục vượt qua kiểm tra schema và chính sách.

Không nhất thiết mọi hệ thống phải chọn thứ tự như trên. Yêu cầu cốt lõi là có một thứ tự rõ ràng, có thể kiểm thử và không để nguồn ưu tiên cao hơn âm thầm làm yếu kiểm soát.

Với nguồn cấu hình từ xa, hợp đồng còn phải nêu cách xác thực nguồn, bảo vệ tính toàn vẹn, kiểm tra phiên bản và xử lý replay. Một bản cấu hình có chữ ký hợp lệ vẫn có thể đã hết hạn hoặc bị thu hồi. Kiểm tra chữ ký không thay thế kiểm tra trạng thái được phép sử dụng.

### 5.3. Schema hợp lệ chưa đủ

Ví dụ cấu hình dưới đây dùng tham chiếu thay cho giá trị secret:

~~~yaml
environment: production
configVersion: cfg-prod-1042
baselineVersion: security-baseline-7

security:
  debug: false
  authorizationMode: enforced
  tenantIsolation: enforced

management:
  exposure: private
  requireAdditionalVerification: true

session:
  idleTimeoutSeconds: 900
  absoluteLifetimeSeconds: 28800

dependencies:
  identityProvider:
    verifyServerIdentity: true
    clientSecretRef: secret-store://production/identity/client

logging:
  securityAuditEnabled: true
  redactSensitiveFields: true
~~~

Đây là cấu hình ứng dụng minh họa, không phải định dạng bắt buộc hoặc tệp metadata bài học. Tham chiếu secret là ký hiệu giả; không chứa thông tin đăng nhập thật.

Schema có thể xác nhận `debug` là boolean và thời hạn phiên là số nguyên dương. Chính sách ngữ nghĩa phải kiểm tra thêm:

- Với `environment: production`, `debug` bắt buộc bằng `false`.
- Thời hạn chờ không được lớn hơn thời hạn phiên tuyệt đối.
- `authorizationMode` và `tenantIsolation` phải thuộc chế độ được phép.
- Tham chiếu secret phải thuộc môi trường và phạm vi dịch vụ được cấp quyền.
- Các trường không được hỗ trợ không được âm thầm bị bỏ qua.
- Không chấp nhận các khóa trùng tên trong định dạng cấu hình nếu chúng có thể gây cách diễn giải khác nhau giữa các thành phần.

Các con số trong ví dụ chỉ minh họa quan hệ giữa các trường. Khi viết yêu cầu thực tế, phải xác định lý do chọn ngưỡng, tác động đến người dùng và cách kiểm thử thời hạn.

## 6. Bộ yêu cầu minh họa và tiêu chí chấp nhận

### CFG-01 — Phân quyền truy cập và quản lý cấu hình

**Yêu cầu:** Hệ thống phải phân biệt quyền xem cấu hình đã che dữ liệu, đề xuất thay đổi, phê duyệt và kích hoạt. Mỗi hành động phải được kiểm tra quyền ở phía xử lý yêu cầu, trong đúng phạm vi môi trường và tenant.

**Tiêu chí chấp nhận:**

- Người chỉ có quyền xem không thể cập nhật qua giao diện, API hoặc lời gọi trực tiếp tới kênh quản lý cấu hình.
- Quản trị viên của tenant A không thể đọc hoặc thay đổi cấu hình riêng của tenant B, kể cả khi biết định danh tài nguyên.
- Vai trò quản trị tenant không có quyền sửa chính sách bảo mật toàn hệ thống.
- Kênh máy với máy dùng danh tính riêng và quyền tối thiểu; không dùng chung thông tin xác thực của người vận hành.
- Thao tác được chấp nhận hoặc bị từ chối đều có bằng chứng đủ để quy về chủ thể và hành động, theo chính sách logging.

**Kiểm chứng:** Kiểm thử ma trận vai trò × hành động × tài nguyên, bao gồm yêu cầu sửa định danh tenant và lời gọi bỏ qua giao diện.

### CFG-02 — Kiểm tra kiểu, miền giá trị và ngữ nghĩa

**Yêu cầu:** Mọi cấu hình phải được kiểm tra trước kích hoạt theo schema cùng phiên bản và các quy tắc liên trường. Cấu hình sai không được áp dụng một phần.

**Tiêu chí chấp nhận:**

- Từ chối trường bắt buộc bị thiếu, sai kiểu, ngoài miền giá trị, khóa trùng và khóa không được hỗ trợ.
- Từ chối quan hệ không hợp lệ, chẳng hạn thời hạn chờ lớn hơn thời hạn phiên tuyệt đối.
- Trường bắt buộc không được nhận chuỗi rỗng rồi tự chuyển thành giá trị làm yếu bảo vệ.
- Thông báo lỗi chỉ rõ đường dẫn trường và mã quy tắc, không trả về secret.
- Các bộ phân tích cấu hình ở pipeline và runtime diễn giải thống nhất các giá trị có ý nghĩa bảo mật.

**Kiểm chứng:** Các bộ dữ liệu hợp lệ, không hợp lệ và sát biên; ca kiểm thử khác biệt cách diễn giải giữa kiểm tra trước triển khai và runtime.

### CFG-03 — Baseline sản xuất và chế độ khởi động

**Yêu cầu:** Mỗi instance chỉ được nhận lưu lượng sau khi cấu hình có hiệu lực đáp ứng baseline sản xuất. Quy tắc này áp dụng cả lúc khởi động và reload.

**Tiêu chí chấp nhận:**

- Từ chối debug, profile mô phỏng xác thực và chế độ bỏ qua kiểm tra quyền trong sản xuất.
- Không công khai endpoint quản trị trái với chính sách tiếp cận đã định.
- Không cho phép tắt kiểm tra danh tính máy chủ đối với kết nối thuộc phạm vi phải xác thực bên nhận.
- Instance chưa có cấu hình hợp lệ không báo sẵn sàng phục vụ lưu lượng nghiệp vụ.
- Bản cập nhật không hợp lệ không làm mất cấu hình hợp lệ đang hoạt động. Việc tiếp tục dùng bản cũ còn phụ thuộc vào điều kiện hiệu lực của CFG-04.

**Kiểm chứng:** Khởi động với cấu hình sai; reload cấu hình sai khi có lưu lượng; kiểm tra trạng thái readiness và hành vi truy cập thực tế.

### CFG-04 — Nguồn đáng tin, hiệu lực và chống hạ mức bảo vệ

**Yêu cầu:** Chỉ được kích hoạt cấu hình đến từ nguồn đã xác thực, bảo đảm toàn vẹn và còn được phép sử dụng. Không nguồn ghi đè nào được vượt các ràng buộc tối thiểu của baseline.

**Tiêu chí chấp nhận:**

- Từ chối bundle bị sửa, có dấu xác minh không hợp lệ, không đúng môi trường, đã hết hạn hoặc nằm trong danh sách bị thu hồi.
- Không chọn một bản cũ chỉ vì bản đó từng được ký hoặc từng chạy thành công.
- Thứ tự ưu tiên nguồn được mô tả và kiểm thử cho từng nhóm tham số bảo mật.
- Khi không lấy được cấu hình mới, bản đang chạy chỉ được tiếp tục sử dụng trong giới hạn đã đặc tả cho từng nhóm tham số.
- Nếu không còn bản được phép sử dụng, hệ thống chuyển sang trạng thái đã quy định, chẳng hạn ngừng nhận yêu cầu cần chính sách đó; không tự tạo cấu hình dễ dãi.

**Kiểm chứng:** Giả lập nguồn không truy cập được, bundle bị thay đổi, replay bản bị thu hồi và biến môi trường cố ghi đè trường bị cấm.

Cần nêu rõ giới hạn của việc tiếp tục sử dụng bản đã xác minh. Ví dụ, chính sách phân quyền có thể cần cập nhật nhanh hơn cấu hình giao diện. Không dùng một thời hạn cache chung nếu các nhóm có rủi ro khác nhau.

### CFG-05 — Tách secret khỏi cấu hình thông thường

**Yêu cầu:** Tệp cấu hình, bản xem trước thay đổi và bằng chứng kiểm chứng chỉ được chứa tham chiếu secret hoặc dữ liệu đã được che theo chính sách. Giá trị secret chỉ được cấp cho danh tính runtime được phép.

**Tiêu chí chấp nhận:**

- Không đưa secret dưới dạng rõ vào repository, artifact triển khai hoặc đầu ra pipeline.
- Hệ thống không ghi giá trị secret vào thông báo lỗi, log khởi động, endpoint chẩn đoán và báo cáo cấu hình có hiệu lực.
- Quyền đọc secret được giới hạn theo dịch vụ và môi trường; biết tham chiếu không đồng nghĩa có quyền lấy giá trị.
- Quá trình xoay secret có bước xác nhận dịch vụ sử dụng được bản mới, sau đó thu hồi bản cũ theo kế hoạch.
- Khi không lấy được secret, hành vi được đặc tả rõ. Không thay secret thiếu bằng chuỗi rỗng, giá trị mẫu hoặc tài khoản dùng chung.

**Kiểm chứng:** Dùng secret giả có dấu nhận diện trong môi trường kiểm thử, gây lỗi tại các bước nạp và kết nối, rồi kiểm tra các đầu ra trong phạm vi thử nghiệm. Kết quả này cần kết hợp rà soát các đường xuất dữ liệu; một lần tìm không thấy dấu nhận diện chưa chứng minh mọi đường lỗi đều an toàn.

Việc che dữ liệu phải dựa trên phân loại trường và cấu trúc dữ liệu. Chỉ tìm tên có chữ “password” hoặc “token” dễ bỏ sót khóa API, chuỗi kết nối và dữ liệu nhạy cảm mang tên khác.

### CFG-06 — Phê duyệt và ghi nhận thay đổi nhạy cảm

**Yêu cầu:** Các thay đổi thuộc danh sách nhạy cảm, như giảm yêu cầu xác thực, sửa quyền, thay đích truyền dữ liệu hoặc thay chính sách logging bảo mật, phải có phê duyệt độc lập trước kích hoạt.

**Tiêu chí chấp nhận:**

- Trong quy trình thông thường của ví dụ này, người đề xuất không được tự phê duyệt thay đổi nhạy cảm của mình.
- Quy tắc phê duyệt được cưỡng chế tại kênh kích hoạt; bỏ qua giao diện không bỏ qua được quy tắc.
- Sự kiện thay đổi chứa chủ thể, lý do, môi trường, định danh yêu cầu thay đổi, phiên bản trước/sau và kết quả.
- Bản so sánh trước/sau không lộ secret hoặc dữ liệu nhạy cảm.
- Đường xử lý khẩn cấp có quyền tạm thời, phạm vi hẹp, thời hạn kết thúc, logging và trách nhiệm rà soát được xác định trước.

**Kiểm chứng:** Thử tự phê duyệt, dùng phê duyệt của phiên bản khác, gọi trực tiếp API kích hoạt và dùng quyền khẩn cấp đã hết hạn.

Phê duyệt phải gắn với nội dung hoặc định danh bất biến của thay đổi. Nếu nội dung được sửa sau phê duyệt, trạng thái phê duyệt cũ không còn đủ để kích hoạt bản mới.

### CFG-07 — Kích hoạt nhất quán và hội tụ các instance

**Yêu cầu:** Một instance chỉ được chuyển sang thế hệ cấu hình mới sau khi toàn bộ cấu hình cần thiết đã được kiểm tra và chuẩn bị thành công. Các instance phục vụ lưu lượng phải hội tụ trong thời gian đã đặc tả.

**Tiêu chí chấp nhận trong ví dụ:**

- Không có trạng thái mà một yêu cầu nghiệp vụ dùng một phần chính sách cũ và một phần chính sách mới ngoài thiết kế chuyển tiếp đã được chấp nhận.
- Mỗi instance công bố được định danh thế hệ cấu hình có hiệu lực qua kênh giám sát được phân quyền.
- Trong vòng 5 phút kể từ khi bộ điều phối chấp nhận kích hoạt, mọi instance còn được phép phục vụ lưu lượng phải dùng bản mục tiêu hoặc bản tương thích được chỉ rõ trong kế hoạch chuyển tiếp.
- Instance không đạt điều kiện hội tụ phải bị rút khỏi lưu lượng theo chính sách và sinh cảnh báo.
- Quy tắc xử lý yêu cầu đang chạy, session và cache được xác định khi thay đổi có ảnh hưởng đến chúng.

**Kiểm chứng:** Cập nhật khi có lưu lượng, làm chậm một instance, làm lỗi bước chuẩn bị và kiểm tra kết quả theo từng instance.

Tính nguyên tử trong một tiến trình không đồng nghĩa toàn cụm đổi cấu hình đồng thời. Nếu hai thế hệ được phép cùng tồn tại trong quá trình chuyển tiếp, phải chứng minh chúng tương thích tại ranh giới giữa các dịch vụ. Đối với thay đổi thu hồi quyền, không được dùng cửa sổ chuyển tiếp như lý do để vượt thời hạn thu hồi đã cam kết.

### CFG-08 — Phát hiện và xử lý configuration drift

**Yêu cầu:** Hệ thống phải phát hiện sai lệch tại runtime đối với các trường bảo mật trong phạm vi, đối chiếu cả cấu hình mong muốn lẫn baseline.

**Tiêu chí chấp nhận trong ví dụ:**

- Với các trường bảo mật trọng yếu đã liệt kê, cảnh báo phải được hệ thống giám sát ghi nhận không muộn hơn 5 phút kể từ lúc sai lệch có hiệu lực.
- Cảnh báo nêu instance, môi trường, mã trường hoặc mã quy tắc, phiên bản mong muốn và phiên bản quan sát được; không chứa secret.
- Không được có trạng thái chung “đúng cấu hình” nếu một phần instance chưa được quan sát.
- Trạng thái không thu thập được dữ liệu phải được biểu diễn là chưa xác định và có cách xử lý, không tự tính là đạt.
- Phản ứng với drift có trong chính sách: chặn lần phát hành tiếp theo, rút instance, đưa về bản được duyệt hoặc chuyển xử lý sự cố tùy mức độ.

**Kiểm chứng:** Tạo drift có chủ đích, đo thời gian từ lúc thay đổi có hiệu lực đến khi cảnh báo được ghi nhận, đồng thời kiểm tra thông tin cảnh báo và phản ứng đã định.

Tự động hoàn nguyên mọi drift có thể gây vòng lặp hoặc gián đoạn khi nguyên nhân chưa được xử lý. Yêu cầu phải chỉ rõ khi nào tự động khắc phục được phép và khi nào cần người chịu trách nhiệm quyết định.

### CFG-09 — Bằng chứng và nhật ký bảo vệ được

**Yêu cầu:** Mỗi lần kiểm tra và thay đổi cấu hình phải tạo được bằng chứng gắn với bản phát hành, baseline và đối tượng thực tế đã kiểm tra.

**Tiêu chí chấp nhận:**

- Bằng chứng chứa mã yêu cầu, mã kiểm thử, thời điểm, môi trường, bản ứng dụng, phiên bản cấu hình và baseline, kết quả cùng phạm vi quan sát.
- Nhật ký phân biệt đề xuất, phê duyệt, từ chối, kích hoạt thành công, kích hoạt thất bại và rollback.
- Người có quyền thay đổi cấu hình không mặc nhiên có quyền xóa hoặc sửa lịch sử bằng chứng.
- Lỗi gửi log hoặc ghi bằng chứng không được âm thầm bị bỏ qua; có chỉ báo và hành vi theo chính sách.
- Quyền truy cập và thời hạn lưu bằng chứng được xác định theo nhu cầu điều tra, quyền riêng tư và yêu cầu áp dụng cho hệ thống.

**Kiểm chứng:** Đối chiếu một thay đổi từ yêu cầu đến sự kiện runtime; thử sửa/xóa lịch sử bằng danh tính không có quyền; mô phỏng gián đoạn đường gửi log.

Không nên cam kết “mọi lỗi logging đều dừng toàn bộ hệ thống” nếu chưa phân tích tác động khả dụng. Với một thao tác quản trị nhạy cảm, có thể yêu cầu ghi được sự kiện bền vững trước khi thực hiện. Với luồng nghiệp vụ khác, có thể dùng bộ đệm bền vững có giới hạn và cảnh báo. Đặc tả phải nêu rõ dung lượng, điều kiện đầy bộ đệm, hành vi khi mất dữ liệu và phạm vi thao tác bị chặn.

### CFG-10 — Rollback và phục hồi giữ nguyên ràng buộc an toàn

**Yêu cầu:** Cơ chế phục hồi chỉ được kích hoạt một phiên bản cấu hình vẫn còn được phép sử dụng và đáp ứng các ràng buộc bảo mật bắt buộc tại thời điểm phục hồi.

**Tiêu chí chấp nhận trong ví dụ:**

- Mỗi bản phát hành có ít nhất một phương án phục hồi đã xác minh hoặc một phương án sửa tiến được chấp nhận nếu không thể rollback an toàn.
- Từ chối phục hồi về phiên bản chứa khóa đã thu hồi, chế độ bị cấm hoặc chính sách không còn đáp ứng mức bảo vệ bắt buộc.
- Việc rollback vẫn phải kiểm tra tương thích schema, secret và các phụ thuộc có liên quan.
- Mục tiêu phục hồi là khôi phục lưu lượng nghiệp vụ đạt kiểm tra sức khỏe và kiểm tra bảo mật tối thiểu trong 10 phút từ quyết định bắt đầu rollback, ở điều kiện diễn tập đã công bố.
- Bằng chứng ghi rõ thời điểm quyết định, bắt đầu kích hoạt, hội tụ và xác nhận dịch vụ phục hồi.

**Kiểm chứng:** Diễn tập với bản hiện tại lỗi, bản cũ hợp lệ, bản cũ đã thu hồi và nguồn cấu hình không truy cập được.

“Có bản sao cấu hình” chưa đủ để chứng minh phục hồi. Phải kiểm tra cả khả năng truy cập bản sao khi sự cố xảy ra, quyền kích hoạt, khả năng lấy secret và tính tương thích với trạng thái hệ thống hiện tại.

## 7. Tổ chức verification qua vòng đời phát triển

### 7.1. Đặt điểm kiểm chứng đúng nơi

~~~mermaid
flowchart TD
    A["Mục tiêu và mô hình đe dọa"] --> B["Yêu cầu CFG và tiêu chí chấp nhận"]
    B --> C["Baseline, schema, hợp đồng nguồn"]
    C --> D["Kiểm tra trước khi hợp nhất"]
    D --> E["Kiểm tra artifact và kế hoạch triển khai"]
    E --> F["Kiểm tra cấu hình có hiệu lực trước nhận lưu lượng"]
    F --> G["Giám sát drift và thay đổi khi chạy"]
    G --> H["Diễn tập phục hồi và cập nhật bằng chứng"]
    H --> B
~~~

Các điểm kiểm tra bổ sung cho nhau:

| Thời điểm | Đối tượng kiểm tra | Điều kiện chặn hoặc hành động | Giới hạn bằng chứng |
| --- | --- | --- | --- |
| Khi thiết kế | Rủi ro, nguồn cấu hình, quyền và hành vi lỗi | Chưa chấp nhận thiết kế nếu rủi ro trọng yếu chưa có yêu cầu | Chưa chứng minh triển khai thực tế |
| Khi hợp nhất thay đổi | Schema, baseline, cấu hình mẫu và logic hợp nhất | Chặn thay đổi sai quy tắc | Chưa chứng minh giá trị được cung cấp lúc triển khai |
| Khi tạo artifact | Profile, tham chiếu cấu hình, đường nạp secret | Chặn artifact sai môi trường hoặc chứa dữ liệu bị cấm | Chưa chứng minh trạng thái runtime |
| Trước nhận lưu lượng | Cấu hình có hiệu lực, phiên bản, readiness | Không đưa instance không đạt vào phục vụ | Cần tiếp tục theo dõi sau khởi động |
| Khi vận hành | Drift, quyền quản trị, thời hạn và đường gửi log | Cảnh báo, rút lưu lượng hoặc xử lý sự cố theo chính sách | Chỉ bao phủ những instance và thuộc tính được quan sát |
| Khi phục hồi | Bản được phép dùng, tương thích và thời gian khôi phục | Từ chối bản không an toàn | Kết quả phụ thuộc điều kiện diễn tập |

Không sao chép một bộ kiểm tra nguyên xi rồi coi mọi giai đoạn đã được bao phủ. Ví dụ, kiểm tra schema trong pipeline và runtime có thể dùng chung quy tắc, nhưng runtime vẫn phải kiểm tra giá trị sau khi hợp nhất mọi nguồn.

### 7.2. Ma trận kiểm thử tối thiểu theo hành vi

| Mã kiểm thử | Thiết lập hoặc hành động | Kết quả mong đợi | Liên kết |
| --- | --- | --- | --- |
| T-CFG-01 | Người chỉ có quyền xem gọi API sửa cấu hình | Từ chối, không thay đổi trạng thái, có sự kiện phù hợp | CFG-01 |
| T-CFG-02 | Cung cấp chuỗi thay boolean; khóa trùng; quan hệ thời hạn sai | Từ chối từng trường hợp, không áp dụng một phần | CFG-02 |
| T-CFG-03 | Bật debug bằng nguồn có mức ưu tiên cao nhất | Không kích hoạt trong sản xuất, chỉ rõ quy tắc vi phạm | CFG-03, CFG-04 |
| T-CFG-04 | Nạp bundle bị sửa hoặc bản từng hợp lệ nhưng đã thu hồi | Từ chối cả hai; không chỉ dựa vào lịch sử sử dụng | CFG-04 |
| T-CFG-05 | Nguồn cấu hình mất kết nối; bản đang dùng vượt thời hạn cho phép | Chuyển đúng trạng thái đã đặc tả; không tự giảm bảo vệ | CFG-04 |
| T-CFG-06 | Nạp secret giả rồi gây lỗi kết nối phụ thuộc | Các đầu ra trong phạm vi thử nghiệm không lộ giá trị; hành vi lỗi đúng yêu cầu | CFG-05 |
| T-CFG-07 | Sửa nội dung sau khi đã có phê duyệt | Phê duyệt cũ không kích hoạt được nội dung mới | CFG-06 |
| T-CFG-08 | Làm một instance không nhận cấu hình mới | Phát hiện và loại khỏi phạm vi phục vụ nếu vượt ngưỡng | CFG-07, CFG-08 |
| T-CFG-09 | Thay trực tiếp giá trị có hiệu lực, giữ nguyên tệp nguồn | Phát hiện drift và ghi nhận cảnh báo trong thời hạn | CFG-08 |
| T-CFG-10 | Gián đoạn đường gửi log khi thay đổi nhạy cảm | Áp dụng hành vi đã quy định; không mất dấu âm thầm | CFG-09 |
| T-CFG-11 | Rollback về bản có tham chiếu khóa bị thu hồi | Từ chối bản đó và thực hiện phương án phục hồi hợp lệ | CFG-10 |
| T-CFG-12 | Đăng nhập bằng quản trị tenant A rồi sửa cấu hình tenant B | Không đọc hoặc ghi được tài nguyên của B | CFG-01 |

Mỗi dòng là một nhóm hành vi cần tách thành các ca kiểm thử độc lập khi triển khai. Kết quả phải phân biệt **PASS**, **FAIL**, **NOT_RUN** và **INCONCLUSIVE**. Thiếu môi trường, thiếu quan sát hoặc phụ thuộc hỏng không tự trở thành PASS.

### 7.3. Đo chỉ số theo cùng một hợp đồng

Ví dụ đo giới hạn phát hiện drift:

1. Tạo một thay đổi được phép trong môi trường thử nghiệm và ghi `t0` tại thời điểm thay đổi có hiệu lực.
2. Ghi `t1` khi hệ thống giám sát thực sự ghi nhận cảnh báo tương ứng.
3. Tính `driftAlertLatency = t1 - t0`.
4. Kiểm tra giá trị không vượt 5 phút, với bằng chứng đối chiếu cùng instance và cùng sai lệch.
5. Xác nhận các nguồn thời gian có thể so sánh được hoặc dùng một nguồn đo chung. Nếu độ lệch thời gian chưa được kiểm soát, kết quả đo không đủ tin cậy.

Không đo từ lúc job quét bắt đầu vì cách đó bỏ qua thời gian chờ trước lần quét. Cũng không chỉ đo thời gian đẩy sự kiện từ bộ phát hiện sang hệ thống giám sát, vì như vậy chưa bao phủ độ trễ phát hiện.

Khi đặc tả chỉ số, phải nói rõ dùng giới hạn tối đa hay phân vị. Yêu cầu “không quá 5 phút cho mọi đối tượng trong phạm vi” không thể được chứng minh chỉ bằng số trung bình hoặc p95 đạt ngưỡng. Báo cáo cần nêu điều kiện thử, số lần thử, các instance được quan sát và giới hạn của kết luận.

## 8. Hai tình huống xuyên suốt

### 8.1. Tệp nguồn đúng nhưng cấu hình có hiệu lực sai

Giả sử manifest sản xuất có `debug: false`. Tuy nhiên, nền tảng cho phép một biến môi trường cũ ghi đè thành `true`.

Nếu chỉ kiểm tra repository, pipeline có thể báo đạt. Nếu chỉ kiểm tra sau sự cố, hệ thống đã có một khoảng thời gian chạy sai baseline.

Quy trình kiểm chứng cần bao phủ:

1. **Liệt kê đường nạp:** tệp mặc định, bundle, biến môi trường, tham số khởi động và thay đổi khi chạy.
2. **Xác định ưu tiên:** ghi rõ nguồn nào có thể ghi đè trường nào.
3. **Tạo cấu hình có hiệu lực:** dùng cùng quy tắc hợp nhất và chuyển kiểu với ứng dụng.
4. **Kiểm tra bất biến:** sản xuất luôn có `debug = false` bất kể nguồn đầu vào.
5. **Kiểm tra hành vi:** cấu hình sai bị từ chối trước nhận lưu lượng; thông tin chẩn đoán bị hạn chế đúng yêu cầu.
6. **Quan sát sau kích hoạt:** phát hiện nếu đường quản trị khác làm thay đổi trạng thái runtime.

Từ tình huống này có thể suy ra một nguyên tắc thiết kế: ràng buộc bảo mật phải được kiểm tra sau bước hợp nhất cuối cùng và tại các đường thay đổi có thể ảnh hưởng trạng thái có hiệu lực.

Nếu báo cáo cấu hình runtime chỉ che giá trị debug hoặc không cho biết trường đó có được quan sát hay không, bằng chứng không đủ để kết luận. Che dữ liệu cần bảo vệ secret nhưng vẫn phải cho phép đánh giá những bất biến không nhạy cảm.

### 8.2. Xoay secret và rollback ứng dụng

Giả sử cấu hình `cfg-prod-1042` dùng tham chiếu secret đang trỏ đến phiên bản `s17`. Đội vận hành xoay sang `s18`, xác nhận các instance kết nối thành công rồi thu hồi `s17`.

Sau đó, một lỗi ứng dụng khiến đội vận hành cần rollback. Bản ứng dụng cũ không chắc sẽ phục hồi được chỉ bằng cách khôi phục nguyên trạng cấu hình cũ.

Cần kiểm tra:

- Bản ứng dụng cũ có hiểu schema cấu hình hiện tại không?
- Tham chiếu là bí danh có thể trỏ sang phiên bản mới hay định danh phiên bản bất biến?
- Có instance nào vẫn cache `s17` không, và thời điểm cache hết hiệu lực là khi nào?
- Bản cấu hình dự kiến rollback có đang trỏ tới secret bị thu hồi không?
- Nếu không rollback được, phương án sửa tiến hoặc phát hành cấu hình tương thích là gì?

Verification có thể thực hiện trong môi trường thử nghiệm như sau:

1. Chạy bản ứng dụng A với secret giả phiên bản 17.
2. Kích hoạt phiên bản 18 theo quy trình xoay; xác nhận các instance chuyển sang bản mới.
3. Thu hồi phiên bản 17.
4. Kích hoạt bản ứng dụng B rồi gây lỗi theo kịch bản diễn tập.
5. Thực hiện phương án phục hồi đã định mà không khôi phục quyền sử dụng secret 17.
6. Xác nhận kết nối, chức năng cần secret, trạng thái cấu hình và thời gian phục hồi.
7. Kiểm tra rằng log và bằng chứng không chứa giá trị secret giả.

Kết quả cần chứng minh hai điều riêng biệt: dịch vụ đã phục hồi và việc phục hồi vẫn giữ ràng buộc bảo mật. Một trong hai đạt không thay thế cho điều còn lại.

## 9. Thiết kế bằng chứng đủ để quyết định

### 9.1. Một bản ghi kết quả minh họa

~~~yaml
requirementId: CFG-08
testId: T-CFG-09
riskIds:
  - R-04
environment: verification
applicationBuild: app-build-208
baselineVersion: security-baseline-7
desiredConfigVersion: cfg-verification-1042
observedInstances:
  - api-test-01
mutation:
  field: security.debug
  effectiveAt: "2026-01-12T10:00:00Z"
observation:
  alertRecordedAt: "2026-01-12T10:01:12Z"
  latencySeconds: 72
acceptance:
  maximumLatencySeconds: 300
result: PASS
evidenceRefs:
  - evidence://verification-run-42/config-observation
  - evidence://verification-run-42/alert-event
~~~

Định danh và mốc thời gian ở đây là dữ liệu giả. URI bằng chứng chỉ minh họa cách tham chiếu artifact, không đại diện cho tài nguyên thật.

Bản ghi này chứng minh một ca thử trên một instance trong điều kiện đã ghi nhận. Nó chưa đủ để kết luận mọi instance sản xuất luôn phát hiện drift trong 5 phút. Muốn có kết luận rộng hơn, phải có kế hoạch bao phủ và dữ liệu quan sát tương ứng.

### 9.2. Bằng chứng cần bảo vệ những gì?

Một gói bằng chứng hữu ích thường gồm:

- Đặc tả yêu cầu và baseline đúng phiên bản.
- Dữ liệu đầu vào đã xử lý để không chứa secret.
- Định danh bản ứng dụng, cấu hình và môi trường.
- Kịch bản kiểm thử, kết quả mong đợi, kết quả thực tế và lỗi nếu có.
- Tham chiếu tới sự kiện kích hoạt, runtime và cảnh báo tương ứng.
- Người hoặc hệ thống thực hiện, thời điểm thực hiện và phạm vi kiểm tra.
- Trạng thái ngoại lệ hoặc giới hạn khiến kết luận chưa đầy đủ.

Cần kiểm soát quyền đọc, quyền ghi và việc lưu giữ bằng chứng. Bằng chứng chứa thông tin hạ tầng hoặc định danh cá nhân cũng cần được phân loại và bảo vệ.

Có thể dùng digest để đối chiếu tính toàn vẹn của cấu hình công khai hoặc phần cấu hình đã chuẩn hóa. Không đưa giá trị secret vào digest công khai: giá trị có không gian dự đoán nhỏ có thể bị suy đoán bằng cách thử các đầu vào rồi so sánh digest.

Nếu che secret trước khi tính digest, kết quả chỉ chứng minh tính toàn vẹn của phần dữ liệu đã che theo quy tắc đó. Nó không chứng minh giá trị secret thực tế không thay đổi. Với secret, nên lưu định danh phiên bản không nhạy cảm theo quyền được phép thay vì cố công bố dấu vết của nội dung.

Digest cũng không tự chứng minh nguồn gốc hoặc sự phê duyệt. Cần gắn nó với kênh tin cậy, danh tính và sự kiện phê duyệt phù hợp.

### 9.3. Quy tắc ra quyết định

Một bản phát hành chỉ nên được coi là đạt nhóm yêu cầu configuration khi:

1. Mọi yêu cầu áp dụng có kết quả kiểm chứng đáp ứng tiêu chí chấp nhận.
2. Kết quả gắn đúng bản phát hành, baseline, cấu hình và môi trường trong phạm vi quyết định.
3. Các ca chưa chạy hoặc chưa kết luận được được nhận diện rõ và xử lý theo quy tắc phát hành.
4. Ngoại lệ còn hiệu lực được phê duyệt đúng thẩm quyền, với rủi ro còn lại được ghi nhận.
5. Không có điều kiện bắt buộc bị vi phạm mà quy trình cho phép bỏ qua bằng một ô đánh dấu chung.

“Đạt có ngoại lệ” phải được biểu diễn khác với “đáp ứng đầy đủ”. Phê duyệt chấp nhận rủi ro không biến một kiểm thử thất bại thành kiểm thử thành công.

## 10. Quản lý ngoại lệ và thay đổi baseline

Có những tình huống chưa thể đáp ứng ngay yêu cầu, chẳng hạn một hệ thống phụ thuộc chưa hỗ trợ cơ chế xác thực mới. Khi đó cần quản lý ngoại lệ như một đối tượng có vòng đời.

Một ngoại lệ cần có:

| Nội dung | Câu hỏi phải trả lời |
| --- | --- |
| Yêu cầu bị ảnh hưởng | Chính xác tiêu chí nào chưa đáp ứng? |
| Phạm vi | Dịch vụ, môi trường, tenant và phiên bản nào được áp dụng? |
| Rủi ro còn lại | Tài sản nào có thể bị ảnh hưởng và qua kịch bản nào? |
| Kiểm soát bù | Giảm rủi ro bằng biện pháp nào, kiểm chứng ra sao? |
| Người chịu trách nhiệm | Ai sở hữu rủi ro và ai có quyền chấp nhận? |
| Hiệu lực | Khi nào bắt đầu, khi nào hết hạn và điều kiện chấm dứt sớm? |
| Khắc phục | Công việc, người thực hiện và mốc hoàn thành? |
| Bằng chứng | Liên kết tới quyết định và kết quả kiểm tra kiểm soát bù? |

Không lưu ngoại lệ dưới dạng một cờ `skipSecurityChecks: true` áp dụng cho toàn hệ thống. Cơ chế thực thi phải giới hạn đúng mã yêu cầu, đúng phạm vi và đúng thời hạn. Các kiểm tra khác vẫn phải hoạt động.

Thay đổi baseline cũng cần đánh giá tác động. Nếu một giá trị trước đây được chấp nhận nay bị cấm, phải xác định cấu hình nào bị ảnh hưởng, cách chuyển tiếp, thời hạn hoàn thành và điều kiện thu hồi bản cũ. Không tự động chấp nhận mọi cấu hình hiện hữu chỉ vì chúng đang chạy.

Quyền khẩn cấp cần được tách khỏi ngoại lệ dài hạn. Hết phiên khẩn cấp không có nghĩa cấu hình đã tự trở về an toàn; phải kiểm tra trạng thái có hiệu lực, thu hồi quyền tạm thời và hoàn tất việc xử lý sau thay đổi.

## 11. Các lỗi đặc tả thường gặp

| Cách viết hoặc cách làm | Vấn đề khi kiểm chứng | Cách làm rõ |
| --- | --- | --- |
| “Cấu hình phải an toàn” | Không có điều kiện đạt | Nêu trường, ràng buộc, phạm vi, thời điểm và hành vi lỗi |
| “Hỗ trợ logging thay đổi” | Có thể bị tắt hoặc không áp dụng cho API | Nêu sự kiện bắt buộc và mọi kênh thay đổi cần bao phủ |
| “Mọi cấu hình đều phải giống nhau” | Bỏ qua khác biệt hợp lệ giữa môi trường và instance | Phân biệt phần bất biến, phần được phép khác và điều kiện chuyển tiếp |
| “Luôn dùng mặc định khi lỗi” | Mặc định có thể làm yếu bảo vệ hoặc dùng sai môi trường | Đặc tả giá trị mặc định và hành vi lỗi cho từng nhóm tham số |
| “Đã dùng kho secret nên đạt” | Chưa xét quyền đọc, cache, log và xoay secret | Kiểm tra toàn bộ vòng đời secret và các đường xuất dữ liệu |
| “Pipeline đã PASS” | Chưa chứng minh trạng thái có hiệu lực | Kiểm tra trước nhận lưu lượng và tiếp tục quan sát runtime |
| “Rollback về bản trước” | Bản trước có thể đã bị thu hồi hoặc không tương thích | Kiểm tra điều kiện được phép sử dụng tại thời điểm phục hồi |
| “Không thấy cảnh báo nghĩa là không có drift” | Có thể mất dữ liệu giám sát | Phân biệt trạng thái đạt, sai lệch và chưa quan sát được |
| “Tự phê duyệt bằng một tài khoản khác” | Tách tài khoản chưa chắc tách trách nhiệm | Xác định chủ thể thực và quy tắc phê duyệt độc lập |
| “PASS theo ngưỡng trung bình” | Không chứng minh giới hạn tối đa đã cam kết | Chọn phép đo và tiêu chí đúng với nội dung yêu cầu |

## 12. Bài tập áp dụng

Giả sử dịch vụ có ba instance, một cổng quản trị và một nguồn cấu hình từ xa. Cấu hình có cờ bật kiểm tra tenant, tham chiếu secret và đích gửi security audit log.

Hãy thực hiện:

1. Chọn ba kịch bản đe dọa: thay đổi trái phép, cấu hình không đồng nhất và phục hồi về bản không còn an toàn.
2. Với mỗi kịch bản, viết một yêu cầu có mã định danh, phạm vi, điều kiện kích hoạt, ràng buộc, hành vi lỗi và chủ thể chịu trách nhiệm.
3. Mỗi yêu cầu phải có ít nhất một ca đạt, một ca từ chối và một ca lỗi phụ thuộc phù hợp.
4. Thiết kế phép đo giới hạn phát hiện drift 5 phút và phục hồi 10 phút, nêu rõ hai mốc thời gian của từng chỉ số.
5. Xác định bằng chứng cần lưu nhưng không đưa secret vào đầu vào công khai, log hoặc báo cáo.
6. Mô tả cách xử lý một instance không thể quan sát và một bản cấu hình rollback đã bị thu hồi.

Một câu trả lời đạt cần cho phép người khác thực hiện kiểm chứng và đi đến cùng kết luận từ cùng bằng chứng. Nếu còn phải đoán “an toàn là thế nào”, “áp dụng ở đâu” hoặc “lỗi thì làm gì”, yêu cầu vẫn cần được cụ thể hóa.
