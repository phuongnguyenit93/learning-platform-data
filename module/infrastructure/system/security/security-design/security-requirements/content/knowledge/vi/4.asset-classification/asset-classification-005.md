# Tài sản cấu hình

## 1. Tài sản cấu hình là gì?

**Tài sản cấu hình** là các giá trị, quy tắc, tham chiếu và tập thiết lập điều khiển cách hệ thống được triển khai, kết nối, vận hành hoặc áp dụng chính sách. Chúng cần được nhận diện và bảo vệ vì thay đổi cấu hình có thể thay đổi hành vi bảo mật mà không cần sửa mã nguồn.

Ví dụ, cùng một phiên bản ứng dụng có thể bảo vệ hoặc làm lộ tài liệu tùy theo cấu hình kho tệp là riêng tư hay công khai. Cùng một dịch vụ xác thực có thể tin đúng hoặc sai nguồn danh tính tùy cấu hình nguồn phát hành và đối tượng nhận được chấp nhận. Tắt một nhóm sự kiện kiểm toán có thể làm mất khả năng giải thích các thao tác đặc quyền.

Tài sản cấu hình có thể nằm trong tệp, cơ sở dữ liệu, dịch vụ quản lý cấu hình, biến môi trường, tham số khởi động, giao diện quản trị hoặc nền tảng triển khai. Việc không nhìn thấy một tệp có đuôi `.yml` hay `.properties` không có nghĩa hệ thống không có tài sản cấu hình ở nơi khác.

Trong phân loại tài sản, cần trả lời ba câu hỏi:

1. Cấu hình nào ảnh hưởng đến tài sản và chức năng nào?
2. Ai có thể đọc, sửa, phê duyệt, áp dụng hoặc phục hồi cấu hình đó?
3. Hậu quả là gì nếu cấu hình bị lộ, bị sửa sai, bị mất hoặc không được áp dụng nhất quán?

Kết quả phải giúp hình thành yêu cầu bảo mật cụ thể cho xác thực, phân quyền, dữ liệu, logging và phục hồi. Một danh sách tên tệp chưa đủ để thể hiện vai trò và rủi ro của tài sản cấu hình.

## 2. Phạm vi: cấu hình rộng hơn thiết lập ứng dụng

| Nhóm cấu hình | Ví dụ | Khả năng tác động bảo mật |
|---|---|---|
| Danh tính và quan hệ tin cậy | Nguồn định danh được tin, điều kiện chấp nhận bằng chứng xác thực, thời hạn phiên. | Tin sai chủ thể hoặc kéo dài quyền truy cập ngoài chính sách. |
| Phân quyền và cách ly | Chính sách quyền, phạm vi vai trò, điều kiện tenant, cấu hình cache quyết định. | Mở rộng quyền, truy cập chéo tenant hoặc thu hồi không đúng hạn. |
| Bảo vệ dữ liệu | Quyền công khai của kho tệp, chính sách mã hóa, tham chiếu khóa, nơi xuất dữ liệu. | Lộ dữ liệu, không dùng được khóa hoặc ghi dữ liệu sang nơi không được phép. |
| Mạng và kết nối | Tuyến gọi dịch vụ, cổng quản trị, endpoint phụ thuộc, danh sách nguồn được chấp nhận. | Mở đường vào mới, gửi dữ liệu sai đích hoặc bỏ qua điểm kiểm soát. |
| Vận hành ứng dụng | Chế độ debug, feature flag, timeout, retry, giới hạn hàng đợi và tài nguyên. | Lộ thông tin chẩn đoán, bỏ nhánh kiểm tra hoặc làm cạn tài nguyên. |
| Logging và giám sát | Loại sự kiện, trường được ghi, nơi nhận log, quyền đọc, thời hạn lưu, ngưỡng cảnh báo. | Mất dấu vết, rò rỉ dữ liệu qua log hoặc không phát hiện sự cố. |
| Triển khai và chuỗi cung ứng | Workflow phát hành, tham số môi trường, manifest, cấu hình danh tính runtime. | Đưa mã hoặc quyền không phù hợp vào môi trường có dữ liệu nhạy cảm. |
| Sao lưu và phục hồi | Lịch sao lưu, phạm vi dữ liệu, nơi lưu, quyền phục hồi và tham chiếu khóa. | Mất khả năng phục hồi, lộ bản sao hoặc khôi phục trạng thái quyền cũ. |

Một số tài sản có thể thuộc nhiều nhóm. Chính sách quyền có thể được lưu như mã; workflow triển khai cũng là tài sản của chuỗi phát hành. Phân loại chéo giúp thấy trách nhiệm liên quan, không cần ép mỗi tài sản chỉ có một nhãn.

### 2.1. Cấu hình, dữ liệu nghiệp vụ và bí mật có quan hệ khác nhau

Mã khách hàng trong một hồ sơ thường là dữ liệu nghiệp vụ. Quy tắc xác định khách hàng nào thuộc tenant nào có thể là chính sách hoặc cấu hình điều khiển truy cập. Một giá trị trong bảng cơ sở dữ liệu có thể trở thành tài sản cấu hình nếu hệ thống dùng nó để quyết định hành vi.

Mật khẩu, token và khóa bí mật có thể xuất hiện trong một nguồn cấu hình nhưng phải được quản lý theo yêu cầu dành cho **bí mật**. Gọi chúng là “tham số cấu hình” không làm giảm mức bảo vệ cần thiết.

Nên phân biệt giá trị bí mật với tham chiếu tới bí mật. Một ứng dụng có thể nhận mã tham chiếu và lấy bí mật bằng danh tính workload được cấp quyền. Tham chiếu vẫn có thể tiết lộ cấu trúc hoặc mục đích hệ thống, nhưng quyền đọc tham chiếu không được tự động trở thành quyền lấy giá trị bí mật.

Không nên ghi bí mật vào kho mã hoặc ví dụ cấu hình chỉ để tiện triển khai. Nếu đã có sự cố lộ bí mật, xóa giá trị khỏi bản cấu hình hiện tại chưa làm các bản sao cũ mất hiệu lực; cần xử lý thông tin xác thực theo quy trình sự cố và vòng đời tương ứng.

## 3. Phân biệt cấu hình khai báo với cấu hình đang có hiệu lực

Một tệp trong kho mã thể hiện cấu hình được khai báo, nhưng hành vi thực tế có thể còn chịu tác động của giá trị mặc định, cấu hình theo môi trường, biến môi trường, tham số khởi động và thay đổi động.

```text
Giá trị mặc định
      + cấu hình nền
      + cấu hình môi trường/tenant
      + các nguồn ghi đè được phép
                     |
                     v
           Hợp nhất và kiểm tra
                     |
                     v
        Cấu hình có hiệu lực tại runtime
                     |
                     v
          Hành vi thực tế của hệ thống
```

Thứ tự trong sơ đồ là mô hình khái niệm. Mỗi hệ thống phải công bố thứ tự ưu tiên thực tế của mình; không có một thứ tự chung đúng cho mọi framework hoặc nền tảng.

### 3.1. Ba trạng thái cần theo dõi

| Trạng thái | Nội dung | Ví dụ câu hỏi kiểm tra |
|---|---|---|
| Được khai báo | Giá trị trong nguồn dự kiến làm căn cứ. | Phiên bản cấu hình nào đã được phê duyệt? |
| Được phân phối | Giá trị hoặc gói đã gửi đến môi trường và đối tượng đích. | Gói nào đến những instance nào? |
| Có hiệu lực | Giá trị mà thành phần thực sự dùng để ra quyết định. | Instance đang dùng chính sách và tham số nào? |

Một lần triển khai báo thành công không chứng minh mọi instance đã nạp cùng cấu hình. Một tệp đúng trong kho mã không chứng minh biến môi trường không ghi đè nó. Ngược lại, khác biệt có chủ đích giữa tenant hoặc môi trường không nhất thiết là sai lệch.

**Configuration drift**, hay sai lệch cấu hình, là khác biệt cần được đánh giá giữa trạng thái được quản lý và trạng thái thực tế. Muốn phát hiện đúng phải biết phần nào được phép khác, nguồn nào có thẩm quyền và quy tắc hợp nhất nào đang áp dụng.

### 3.2. Giá trị mặc định cũng là quyết định bảo mật

Nếu thiếu một trường chính sách, hệ thống sẽ dừng, dùng cấu hình đã xác nhận trước đó hay cho phép hành động? Nếu một phiên bản cũ không hiểu khóa mới, nó sẽ từ chối, bỏ qua hay đổi nghĩa cấu hình?

Đây là yêu cầu cần đặc tả, không chỉ là chi tiết của bộ đọc tệp. Với thiết lập bảo vệ quan trọng, cấu hình thiếu hoặc không xác minh được không nên tự tạo một chế độ quyền rộng. Việc tiếp tục dùng phiên bản cũ chỉ phù hợp khi phiên bản đó vẫn đáp ứng điều kiện bảo vệ và giới hạn hiệu lực đã chấp nhận.

## 4. Phân loại theo bí mật, toàn vẹn và sẵn sàng

Không phải mọi cấu hình đều cần bí mật như nhau, nhưng nhiều cấu hình có yêu cầu toàn vẹn rất cao. Một danh sách endpoint công khai có thể không cần giữ kín, trong khi quyền sửa nó có thể cho phép chuyển dữ liệu sang đích khác.

| Ví dụ tài sản | Tác động khi bị lộ | Tác động khi bị sửa | Tác động khi không dùng được |
|---|---|---|---|
| Cấu hình quan hệ tin cậy xác thực | Có thể lộ cấu trúc định danh và điểm quản trị. | Có thể chấp nhận sai nguồn danh tính hoặc sai điều kiện. | Người dùng hợp lệ không đăng nhập được hoặc chức năng phải ngừng phục vụ. |
| Chính sách cách ly tenant | Có thể lộ mô hình quyền và phạm vi dữ liệu. | Có thể làm dữ liệu tenant này truy cập được từ tenant khác. | Không đánh giá được quyền theo yêu cầu. |
| Quy tắc công khai kho tệp xuất | Giá trị có thể ít bí mật hơn nội dung tệp. | Có thể mở đường đọc dữ liệu hàng loạt. | Luồng xuất/tải có thể không hoạt động đúng. |
| Endpoint nhận log | Có thể lộ cấu trúc hạ tầng. | Có thể làm mất hoặc chuyển dấu vết sang nơi không được phép. | Điều tra và phát hiện sự cố bị ảnh hưởng. |
| Cấu hình sao lưu và tham chiếu khóa | Có thể lộ vị trí bản sao và thông tin vận hành. | Có thể sao lưu sai dữ liệu, sai đích hoặc tạo bản sao không phục hồi được. | Không tạo được bản sao hoặc không phục hồi được khi cần. |

Mức độ cụ thể phải do bối cảnh xác định: dữ liệu được điều khiển, phạm vi ảnh hưởng, khả năng khai thác, giới hạn kỹ thuật và tác động nghiệp vụ. Không nên đánh dấu mọi cấu hình là công khai, cũng không cần tự động gán tất cả mức bí mật cao nhất.

### 4.1. Xem xét phạm vi ảnh hưởng

Một thiết lập chỉ ảnh hưởng một tài liệu khác với một chính sách dùng chung toàn hệ thống. Một feature flag có thể tác động mọi tenant nếu được áp ở cấp toàn cục. Một timeout có thể làm lỗi sẵn sàng, nhưng nếu nhánh fallback cho phép truy cập khi timeout thì còn ảnh hưởng bí mật và toàn vẹn.

Cần hỏi cấu hình có thể:

- Thay đổi ai được tin, ai được cấp quyền hoặc cách kiểm tra quyền không?
- Đưa dữ liệu, log hoặc bản sao lưu sang đích mới không?
- Bỏ ghi nhận, giảm thời hạn lưu hoặc vô hiệu hóa cảnh báo không?
- Thay đổi danh tính runtime hoặc quyền sử dụng khóa không?
- Làm mất khả năng phục hồi hoặc khôi phục trạng thái không còn hợp lệ không?

Một cấu hình có giá trị văn bản rất ngắn vẫn có thể là tài sản có tác động lớn. Kích thước tệp và số lượng tham số không phản ánh mức độ quan trọng.

### 4.2. Phân loại cả tổ hợp thiết lập

Các thiết lập riêng lẻ có thể hợp lệ nhưng kết hợp lại không đáp ứng yêu cầu. Ví dụ, tuổi tối đa của cache quyền, độ trễ phân phối thu hồi và tuổi của liên kết tải cùng ảnh hưởng thời gian người bị thu hồi còn truy cập được.

Chỉ kiểm tra `cacheAge <= revocationDeadline` chưa chứng minh toàn bộ đường truy cập đáp ứng thời hạn thu hồi. Cần xem các độ trễ, nhánh xử lý, thời điểm bắt đầu yêu cầu và đường tải thực tế.

Vì vậy, danh mục nên nhận diện các nhóm cấu hình phải thay đổi và kiểm tra cùng nhau, thay vì coi từng khóa là hoàn toàn độc lập.

## 5. Lập danh mục tài sản cấu hình

### 5.1. Chọn đơn vị kiểm kê phù hợp

Có thể kiểm kê theo gói cấu hình có chung chủ sở hữu, vòng đời và phạm vi, đồng thời tách riêng những khóa ảnh hưởng trực tiếp đến kiểm soát bảo mật. Không cần tạo một hồ sơ quản trị cho mọi giá trị nhỏ nếu việc đó không giúp đánh giá rủi ro.

Ví dụ, gói cấu hình dịch vụ tài liệu có thể là một tài sản; bên trong cần nhận diện riêng thiết lập cách ly tenant, đường xuất dữ liệu, chính sách khi lỗi và trường logging. Nếu cùng gói chứa bí mật, phải ghi rõ cơ chế tách và quản lý bí mật.

### 5.2. Các trường cần có

| Trường | Nội dung cần ghi |
|---|---|
| Mã và mục đích | Định danh ổn định, hành vi nào được điều khiển. |
| Phạm vi | Môi trường, tenant, dịch vụ, instance hoặc nhóm tài nguyên chịu tác động. |
| Nguồn có thẩm quyền | Nơi quản lý bản khai báo được chấp nhận và bằng chứng phê duyệt. |
| Các nguồn ghi đè | Biến môi trường, tham số khởi động, bảng cấu hình hoặc giao diện động nào được phép. |
| Quy tắc ưu tiên và hợp nhất | Nguồn nào thắng, khóa nào không được ghi đè, xử lý thiếu hoặc mâu thuẫn. |
| Chủ sở hữu | Ai xác định ý nghĩa nghiệp vụ/bảo mật; ai triển khai và vận hành. |
| Quyền đọc/sửa/áp dụng | Danh tính nào được thực hiện từng loại hành động và trong phạm vi nào. |
| Phân loại tác động | Bí mật, toàn vẹn, sẵn sàng cùng lý do và phạm vi ảnh hưởng. |
| Phụ thuộc | Chính sách, schema, phiên bản ứng dụng, khóa, danh tính và tài sản liên quan. |
| Vòng đời và phiên bản | Tạo, duyệt, phân phối, nạp, đổi, rollback, phục hồi và kết thúc sử dụng. |
| Bằng chứng runtime | Cách xác định phiên bản và giá trị có hiệu lực mà không lộ dữ liệu bị cấm. |
| Trạng thái xác minh | Đã xác minh, đề xuất hoặc chưa xác minh; căn cứ và câu hỏi còn mở. |

Không đưa giá trị bí mật vào bảng kiểm kê. Có thể lưu tham chiếu quản lý phù hợp và nêu rõ nơi cần quyền để tra cứu. Bản danh mục cũng cần được bảo vệ vì nó có thể mô tả các đường điều khiển quan trọng của hệ thống.

## 6. Ví dụ phân loại trong dịch vụ quản lý tài liệu

Giả sử dịch vụ phục vụ nhiều tenant, có tác vụ xuất tài liệu và kho tệp kết quả riêng tư. Một mô hình cấu hình khái niệm có thể là:

```yaml
configVersion: CFG-17
environment: production
identity:
  trustProfileRef: IDENTITY-TRUST-3
authorization:
  policyRef: DOCUMENT-POLICY-9
  tenantIsolation: enforced
  onUnknownDecision: rejectProtectedAction
  decisionCacheMaxAgeSeconds: 30
  revocationDeadlineSeconds: 60
exports:
  storageProfileRef: PRIVATE-EXPORT-STORAGE
  allowPublicAccess: false
  retentionHours: 24
audit:
  profileRef: DOCUMENT-AUDIT-4
storage:
  credentialRef: SECRET-DOC-WRITER
recovery:
  profileRef: DOCUMENT-RECOVERY-2
```

Đây là schema giả định để giải thích tài sản, không phải cấu hình của một sản phẩm hay thư viện cụ thể. Các giá trị 30 giây, 60 giây và 24 giờ chỉ phục vụ ví dụ; dự án phải chọn chúng theo rủi ro, nhu cầu nghiệp vụ và khả năng vận hành.

Các nhóm tài sản bên trong có thể được phân loại như sau:

| Mã | Tài sản cấu hình | Tác động nổi bật | Chủ sở hữu và điểm cần xác minh |
|---|---|---|---|
| CFG-ID-01 | Quan hệ tin cậy định danh | Toàn vẹn cao vì điều khiển ai được chấp nhận là chủ thể hợp lệ. | Chủ hệ thống định danh phối hợp ứng dụng; kiểm tra nguồn được tin và điều kiện chấp nhận. |
| CFG-AZ-01 | Chính sách quyền và cách ly tenant | Bí mật và toàn vẹn dữ liệu phụ thuộc trực tiếp; sẵn sàng bị ảnh hưởng khi không đánh giá được quyền. | Chủ chính sách nghiệp vụ và nhóm thực thi; kiểm tra các đường đọc, xuất và tải. |
| CFG-EX-01 | Kho tệp, quyền công khai và thời hạn lưu | Có thể làm lộ dữ liệu hàng loạt hoặc giữ dữ liệu lâu hơn mục đích. | Chủ dữ liệu cùng nhóm lưu trữ; đối chiếu cấu hình ứng dụng và quyền thực tế của kho. |
| CFG-AU-01 | Hồ sơ kiểm toán | Ảnh hưởng khả năng quy trách nhiệm; có nguy cơ lộ dữ liệu qua sự kiện. | Chủ sự kiện và nền tảng logging; xác minh trường, đích nhận và quyền truy vấn. |
| CFG-SC-01 | Tham chiếu thông tin xác thực lưu trữ | Có thể mở đường tới dữ liệu nếu bị thay sang danh tính quá rộng. | Chủ workload và kho bí mật; kiểm tra ai đổi tham chiếu và ai lấy giá trị. |
| CFG-RC-01 | Hồ sơ phục hồi | Ảnh hưởng khả năng dùng lại dữ liệu, khóa và trạng thái quyền đúng chính sách. | Chủ dữ liệu và vận hành; xác minh bằng diễn tập. |

Mức tác động trong bảng là nhận định cho hệ thống giả định. Hồ sơ thực tế phải nêu căn cứ, quy mô dữ liệu và giới hạn kiểm soát hiện có. “Tham chiếu đã tồn tại” không chứng minh đối tượng được tham chiếu an toàn; cấu hình còn phụ thuộc nội dung của chính sách, hồ sơ và tài nguyên đích.

### 6.1. Một thay đổi nhỏ có thể chuyển mức rủi ro

Đổi `allowPublicAccess` thành `true` có thể tạo đường đọc không còn đi qua API tải kiểm tra quyền. Đổi `credentialRef` sang một danh tính có quyền toàn hệ thống có thể mở rộng phạm vi của worker. Đổi endpoint log sang nơi nhận khác có thể làm mất hoặc tiết lộ bằng chứng.

Không nên chỉ kiểm tra rằng YAML có thể đọc được hoặc giá trị đúng kiểu Boolean. Cần kiểm tra ý nghĩa: với tệp xuất chứa tài liệu riêng tư, chính sách nào cho phép công khai, ai được thay đổi và đường tải thực tế sẽ bị tác động ra sao?

Trong ví dụ, mục tiêu thu hồi là giới hạn 60 giây cho các request mới theo hợp đồng. Cache 30 giây chỉ là một yếu tố. Cần kiểm chứng thêm độ trễ cập nhật quyền, cache khác, liên kết tải và các thành phần thực thi; không suy từ hai con số rằng mục tiêu chắc chắn đạt.

## 7. Vòng đời và các bề mặt tác động

| Giai đoạn | Rủi ro cần xét | Nghĩa vụ bảo vệ cần phân công |
|---|---|---|
| Tạo giá trị và mẫu cấu hình | Mặc định quá rộng, chép bí mật, thiếu chủ sở hữu. | Xác định schema, mặc định, phân loại và nguồn có thẩm quyền. |
| Lưu và đề xuất thay đổi | Sửa trái phép, khó biết ai thay đổi hoặc thay đổi vì sao. | Giới hạn quyền, quản lý phiên bản, lưu ý định và phạm vi thay đổi. |
| Phê duyệt | Người đề xuất tự thông qua thay đổi tác động cao bằng tài khoản khác. | Kiểm tra vai trò và tính độc lập theo chính sách, ghi căn cứ quyết định. |
| Đóng gói và phân phối | Thay gói, sai môi trường, mất nguồn gốc hoặc trộn phiên bản. | Kiểm tra nguồn, tính toàn vẹn, đích áp dụng và tính tương thích. |
| Hợp nhất và nạp | Nguồn ghi đè không được phép, khóa thiếu, phiên bản không hiểu giá trị. | Xác minh nguồn, schema, ngữ nghĩa và hành vi khi lỗi. |
| Chạy và reload | Một số instance dùng giá trị cũ, thay đổi động vượt quy trình. | Theo dõi phiên bản hiệu lực, kết quả nạp và sai lệch. |
| Rollback hoặc phục hồi | Đưa lại chính sách lỗi, bí mật hết hiệu lực hoặc quyền đã thu hồi. | Đánh giá lại theo các điều kiện bảo vệ hiện hành trước khi áp dụng. |
| Kết thúc sử dụng | Bản sao cấu hình, quyền chỉnh sửa hoặc bí mật vẫn tồn tại. | Gỡ quyền, xử lý tham chiếu, bản sao và thời hạn lưu theo chính sách. |

Chủ thể có thể tác động gồm người quản trị ứng dụng, người quản lý nền tảng, người sửa workflow, danh tính triển khai, nhà cung cấp dịch vụ cấu hình và người có quyền phục hồi. Vì vậy, quyền chỉnh cấu hình thường là một dạng đặc quyền cần xuất hiện trong mô hình đe dọa.

Mã hóa tệp cấu hình giúp trong những điều kiện nhất định nhưng không thay thế kiểm soát ai được tạo, phân phối hoặc nạp giá trị. Một ứng dụng có quyền giải mã vẫn có thể bị điều khiển sai nếu nó tin một nguồn cấu hình không được phép.

## 8. Chuyển phân loại thành yêu cầu bảo mật

### CFG-01 — Xác định được nguồn và phiên bản cấu hình có hiệu lực

> Với các nhóm cấu hình ảnh hưởng xác thực, phân quyền, dữ liệu, logging và phục hồi, hệ thống phải xác định được nguồn có thẩm quyền, các nguồn ghi đè được phép, quy tắc ưu tiên, phiên bản đã phê duyệt và phiên bản có hiệu lực trên từng đối tượng đích thuộc phạm vi. Việc quan sát không được đưa giá trị bí mật ra giao diện, log hoặc API chẩn đoán không được phép.

**Tiêu chí chấp nhận:** dùng các giá trị khác nhau ở những nguồn được phép để kiểm tra thứ tự ưu tiên; thử nguồn ghi đè không được phép; đối chiếu bản được duyệt với giá trị runtime đã che dữ liệu nhạy cảm. Thiếu bằng chứng của một instance phải được thể hiện là chưa xác định, không tự coi là đã nạp đúng.

Có thể dùng mã phiên bản hoặc dấu vân tay cho phần cấu hình không chứa bí mật theo thiết kế. Không công bố hash của bí mật có không gian giá trị dễ đoán như một cách che dữ liệu; nên dùng tham chiếu phiên bản bí mật và quyền quan sát phù hợp.

### CFG-02 — Thay đổi cấu hình theo đúng quyền và phê duyệt

> Chỉ danh tính được ủy nhiệm mới được đề xuất, phê duyệt hoặc áp dụng cấu hình trong môi trường, tenant và tập khóa được giao. Các thay đổi tác động cao được liệt kê phải tuân thủ điều kiện xác thực và phê duyệt độc lập theo chính sách. Đường giao diện quản trị, API, pipeline và sửa trực tiếp hạ tầng không được tạo ngoại lệ ngầm cho cùng một nghĩa vụ.

**Tiêu chí chấp nhận:** người chỉ có quyền đọc không sửa được; quyền tenant A không thay cấu hình tenant B hoặc toàn cục; người đề xuất không tự vượt điều kiện độc lập bằng tài khoản liên kết khác. Thử cả đường thay đổi thông thường và đường vận hành được cho phép.

Không cần cùng một quy trình cho mọi tham số. Danh sách thay đổi tác động cao nên xuất phát từ phân loại tài sản: ví dụ nguồn tin cậy xác thực, cách ly tenant, quyền công khai, danh tính runtime, nơi nhận log và chính sách phục hồi.

### CFG-03 — Kiểm tra cấu trúc, ngữ nghĩa và tổ hợp trước khi áp dụng

> Cấu hình bảo mật phải được kiểm tra nguồn, tính toàn vẹn phù hợp, schema, phạm vi môi trường và các ràng buộc ngữ nghĩa trước khi có hiệu lực. Giá trị thiếu, không nhận diện được hoặc không xác minh được không được tự chuyển thành quyền rộng hay đường truyền/lưu bản rõ. Các nhóm thiết lập liên quan phải được đánh giá cùng nhau theo yêu cầu bảo vệ.

**Tiêu chí chấp nhận:** thử tệp đúng cú pháp nhưng sai phạm vi, bật công khai cho dữ liệu không được phép, tham chiếu chính sách không tồn tại, phiên bản không tương thích và tổ hợp không đáp ứng thu hồi. Hệ thống từ chối áp dụng hoặc giữ phiên bản đã xác nhận còn hợp lệ theo chính sách; phản hồi và trạng thái phải chỉ rõ kết quả thực tế.

Checksum đơn thuần chỉ hỗ trợ so sánh với bản tham chiếu. Muốn dựa vào nó để phát hiện thay gói, bản tham chiếu và đường kiểm tra phải đáng tin. Cơ chế xác thực nguồn hoặc phê duyệt cũng phải xét ai điều khiển khóa, pipeline và tài khoản áp dụng.

### CFG-04 — Theo dõi áp dụng và phát hiện sai lệch

> Mỗi lần áp dụng phải ghi nhận phiên bản đích, đối tượng đích và kết quả nạp thực tế. Không báo hoàn tất cho phạm vi chưa có bằng chứng đáp ứng điều kiện triển khai. Với các khóa bảo mật được chỉ định, chênh lệch không được phép giữa trạng thái quản lý và trạng thái có hiệu lực phải được phát hiện, cảnh báo trong tối đa 10 phút ở điều kiện vận hành đã thống nhất.

**Tiêu chí chấp nhận:** sửa trực tiếp một giá trị ngoài quy trình, làm một instance không nhận bản mới và tạo một nguồn ghi đè trái phép. Quan sát được đối tượng bị ảnh hưởng, phiên bản và cảnh báo trong thời hạn. Khác biệt được cho phép theo môi trường/tenant không bị đánh đồng với sai lệch trái phép.

Mốc 10 phút chỉ là giả định trong bài. Phép đo cần chỉ rõ điểm bắt đầu, nơi quan sát, chu kỳ kiểm tra và trường hợp mất kết nối. Một thay đổi nguy hiểm vẫn có thể gây tác động trước khi được phát hiện; cảnh báo không thay thế việc chặn các đường sửa không được phép.

### CFG-05 — Bảo vệ bí mật và bằng chứng thay đổi

> Giá trị bí mật phải được quản lý theo vòng đời và chính sách riêng, với quyền lấy giá trị tách khỏi quyền xem tài liệu cấu hình khi có thể. Nhật ký thay đổi cấu hình phải liên kết được chủ thể, người phê duyệt nếu có, nguồn, môi trường, tài sản, phiên bản trước/sau và kết quả áp dụng. Không ghi bí mật hoặc toàn bộ bản cấu hình chưa được che vào log này.

**Tiêu chí chấp nhận:** đối chiếu quyền xem tham chiếu với quyền lấy bí mật; dùng dữ liệu đánh dấu để kiểm tra log, giao diện diff, chẩn đoán, bản xuất và hàng đợi lỗi thuộc phạm vi. Thay đổi hợp lệ và bị từ chối đều có bằng chứng theo tập sự kiện đã định, không nhầm “đã phê duyệt” với “đã có hiệu lực”.

Độ trễ truy xuất và thời hạn lưu bằng chứng cần được chốt theo mục đích điều tra. Các trường giá trị trước/sau chỉ được ghi khi phù hợp chính sách dữ liệu; có thể cần lưu diff đã che hoặc tham chiếu đến phiên bản được bảo vệ.

### CFG-06 — Rollback và phục hồi phải giữ điều kiện bảo vệ hiện hành

> Trước khi áp lại cấu hình cũ hoặc khôi phục từ bản sao, hệ thống phải kiểm tra tính tương thích, nguồn được chấp nhận và các ràng buộc bảo mật còn hiệu lực. Không tái kích hoạt bí mật đã thu hồi, nguồn tin cậy đã loại bỏ hoặc quyền công khai không còn được phép chỉ vì chúng có mặt trong phiên bản trước. Chức năng nhạy cảm chỉ được mở lại sau khi điều kiện cần thiết được xác nhận.

**Tiêu chí chấp nhận:** diễn tập phục hồi với cấu hình có tham chiếu bí mật đã ngừng dùng, chính sách quyền cũ và ứng dụng phiên bản khác. Kết quả phải phản ánh trạng thái áp dụng thực tế, không mở đường ngoài chính sách và đạt mục tiêu phục hồi đã chốt cho phạm vi sự cố.

RTO là mục tiêu thời gian phục hồi; RPO là mục tiêu về khoảng mất dữ liệu tối đa tính theo thời gian. Với cấu hình, cần xác định riêng phần lịch sử thay đổi, trạng thái đã phê duyệt và trạng thái runtime nào phải phục hồi. Có bản sao tệp chưa chứng minh khôi phục được hành vi an toàn.

## 9. Kiểm tra thay đổi theo một kịch bản xuyên suốt

Giả sử một kỹ sư muốn giảm thời gian xử lý xuất tài liệu. Trong cùng đề xuất, người đó tăng thời hạn cache quyền và bật quyền công khai cho kho tệp để tải trực tiếp.

### 9.1. Phân tích trước khi quyết định

Thay đổi này tác động ít nhất CFG-AZ-01 và CFG-EX-01. Cần xem mục tiêu thu hồi, phạm vi dữ liệu trong tệp, các đường tải hiện có và cách thay đổi được ghi đè ở runtime. Không chỉ xét lợi ích độ trễ.

Câu hỏi cần làm rõ gồm:

1. Cache mới còn đáp ứng giới hạn thu hồi trên toàn bộ đường truy cập không?
2. Tải trực tiếp có còn kiểm tra quyền, hay việc có URL đã trở thành khả năng tải?
3. Quyền công khai có áp cho tệp tạm, tệp cũ hoặc mọi tenant không?
4. Những danh tính nào có thể thay thiết lập tương đương ở kho lưu trữ hoặc pipeline?
5. Nếu chỉ một phần instance nhận cấu hình mới, các bất biến có còn được duy trì không?
6. Có thể quay lại trạng thái bảo vệ mà không tái dùng bí mật hoặc chính sách đã hết hiệu lực không?

Nếu một tổ hợp vi phạm yêu cầu, cần từ chối hoặc thiết kế lại. Việc thay đổi được đề xuất để cải thiện hiệu năng không tự tạo ngoại lệ cho mục tiêu bảo vệ dữ liệu.

### 9.2. Ca chấp nhận minh họa

```text
Cho trước:
  Tệp xuất chứa tài liệu riêng tư của từng tenant.
  Chính sách không cho kho tệp phục vụ công khai.
  CFG-17 là phiên bản đã được chấp nhận.

Khi:
  Một thay đổi hoặc nguồn ghi đè đặt allowPublicAccess thành true.

Thì:
  Đường áp dụng được quản lý không đưa giá trị trái chính sách vào hiệu lực.
  Nếu có sai lệch ở hạ tầng ngoài đường đó, hệ thống phát hiện theo hợp đồng.
  Người không có quyền không tải được tệp qua các đường thuộc phạm vi kiểm chứng.
  Có bằng chứng về nguồn thay đổi, đối tượng, phiên bản và kết quả xử lý.
```

Ca này phải được bổ sung bằng thay đổi hợp lệ để chứng minh cơ chế quản lý không chỉ chặn mọi thay đổi. Cũng cần kiểm tra đường kho lưu trữ thực tế, không chỉ giá trị trong ứng dụng: một khóa `false` không bảo vệ được dữ liệu nếu hạ tầng vẫn công khai.

## 10. Truy vết từ rủi ro đến yêu cầu và bằng chứng

| Rủi ro | Tài sản liên quan | Yêu cầu | Bằng chứng phù hợp |
|---|---|---|---|
| Tin sai nguồn danh tính | CFG-ID-01 | CFG-02, CFG-03 | Kiểm thử quyền đổi cấu hình, điều kiện chấp nhận nguồn và hành vi khi thiếu/sai thiết lập. |
| Truy cập chéo tenant hoặc thu hồi chậm | CFG-AZ-01 | CFG-01, CFG-03, CFG-04 | Đối chiếu cấu hình runtime, kiểm thử các đường quyền và sai lệch. |
| Công khai tệp hoặc gửi dữ liệu sai đích | CFG-EX-01 | CFG-02, CFG-03, CFG-04 | Kiểm tra cấu hình ứng dụng, quyền hạ tầng và truy cập thực tế. |
| Lộ bí mật hoặc mất dấu vết | CFG-SC-01, CFG-AU-01 | CFG-05 | Kiểm thử quyền lấy bí mật, dữ liệu bị cấm và liên kết sự kiện thay đổi. |
| Khôi phục trạng thái bảo vệ không còn hợp lệ | CFG-RC-01 và các nhóm cấu hình được phục hồi | CFG-06 | Diễn tập có phiên bản, bí mật, quyền và nguồn tin cậy đã thay đổi. |

Mỗi dòng cần gắn chủ sở hữu, phạm vi và trạng thái bằng chứng. Chưa xác minh giá trị đang chạy phải được giữ là khoảng trống cần xử lý, không suy từ tài liệu rằng mọi instance đều đúng.

Bằng chứng cần ghi phiên bản ứng dụng, schema, cấu hình, nguồn ghi đè và môi trường. Kiểm tra đúng cú pháp, có quản lý bằng kho mã hoặc có mã hóa chưa đủ chứng minh hành vi đáp ứng yêu cầu. Kết quả một tập kiểm thử hữu hạn cũng không bao phủ mọi đường thay đổi có thể tồn tại.

## 11. Những lỗi phân loại và quản lý thường gặp

| Nhận định hoặc cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| “Cấu hình chỉ là dữ liệu kỹ thuật.” | Bỏ qua khả năng điều khiển quyền, dữ liệu và phục hồi. | Gắn mỗi nhóm cấu hình với hành vi, tài sản và tác động CIA. |
| “Không có mật khẩu nên cấu hình không nhạy cảm.” | Có thể lộ cấu trúc hoặc cho phép tác động lớn khi bị sửa. | Đánh giá bí mật, toàn vẹn và sẵn sàng riêng theo bối cảnh. |
| “Có trong kho mã là biết chính xác đang chạy gì.” | Bỏ sót giá trị mặc định, nguồn ghi đè và reload động. | Theo dõi khai báo, phân phối và hiệu lực cùng quy tắc ưu tiên. |
| “Đúng YAML nên có thể triển khai.” | Chưa kiểm tra ngữ nghĩa, tham chiếu và tổ hợp thiết lập. | Xác minh các ràng buộc bảo mật trước khi áp dụng. |
| “Ứng dụng ghi false nên kho chắc chắn riêng tư.” | Cấu hình hạ tầng thực tế có thể khác hoặc có đường công khai khác. | Đối chiếu các lớp và quan sát đường truy cập thực tế. |
| “Rollback luôn đưa về trạng thái an toàn.” | Phiên bản cũ có thể chứa lỗi đã sửa, nguồn tin cậy hoặc bí mật đã thu hồi. | Kiểm tra lại theo điều kiện hiện hành trước khi áp lại. |
| “In toàn bộ cấu hình để dễ hỗ trợ.” | Có thể lộ bí mật, endpoint, chính sách và thông tin khách hàng. | Cung cấp quan sát có quyền, che dữ liệu và nêu nguồn/phiên bản cần thiết. |
| “Cảnh báo drift thay thế được kiểm soát thay đổi.” | Thiết lập nguy hiểm có thể có hiệu lực trước khi cảnh báo. | Kết hợp ngăn thay đổi trái phép, phát hiện và xử lý. |

## 12. Bài tập áp dụng

Một nền tảng bổ sung tính năng tải tệp từ đối tác và lập chỉ mục tìm kiếm. Cấu hình gồm nguồn đối tác được tin, danh tính worker, nơi lưu tệp, chính sách quyền chỉ mục, mức logging và hồ sơ phục hồi. Một số giá trị được thay động qua trang quản trị, một số được đưa vào qua pipeline.

Hãy thực hiện các bước sau:

1. Nhận diện ít nhất sáu tài sản hoặc nhóm cấu hình, nêu hành vi mà chúng điều khiển.
2. Tách giá trị thông thường, tham chiếu bí mật và giá trị bí mật; ghi quyền đọc/sửa/lấy giá trị tương ứng.
3. Phân loại tác động bí mật, toàn vẹn và sẵn sàng cùng căn cứ; xác định nhóm có phạm vi ảnh hưởng lớn.
4. Liệt kê nguồn có thẩm quyền, các nguồn ghi đè, thứ tự ưu tiên và cách quan sát giá trị có hiệu lực.
5. Viết yêu cầu cho thay đổi nguồn tin cậy, quyền chỉ mục, lỗi nạp cấu hình và phục hồi bản cũ.
6. Chọn một tổ hợp giá trị riêng lẻ hợp lệ nhưng có thể vi phạm yêu cầu; đề xuất kiểm chứng ở cả ứng dụng và hạ tầng.
7. Lập ma trận nối rủi ro, tài sản, yêu cầu, chủ sở hữu và bằng chứng; ghi rõ những điểm chưa xác minh.

Một danh mục tốt không dừng ở nơi đặt tệp. Nó giải thích được cấu hình điều khiển điều gì, ai có thể tác động, giá trị nào thực sự có hiệu lực và bằng cách nào hệ thống giữ các điều kiện bảo vệ trong thay đổi, vận hành và phục hồi.
