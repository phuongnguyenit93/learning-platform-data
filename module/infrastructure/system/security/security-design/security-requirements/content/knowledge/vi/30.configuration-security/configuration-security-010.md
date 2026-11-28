# Dependency configuration — Đặc tả cấu hình bảo mật cho thành phần phụ thuộc

## 1. Khái niệm và mục tiêu của bài học

Một ứng dụng thường dựa vào thư viện, framework, SDK, driver và các dịch vụ như cơ sở dữ liệu, cache, hàng đợi hoặc API đối tác. **Dependency configuration** là tập quyết định cấu hình xác định ứng dụng lấy, nạp, kết nối và sử dụng những phụ thuộc đó như thế nào.

Một thư viện có phiên bản được phê duyệt vẫn có thể được cấu hình để bỏ xác minh chứng thư, ghi token vào log hoặc tự retry một thao tác không được phép lặp. Một dịch vụ có TLS đúng vẫn có thể được gọi bằng credential có quyền quá rộng hoặc qua endpoint do người dùng tùy ý thay đổi. Vì vậy, kiểm soát phiên bản và kiểm soát cấu hình giải quyết các phần khác nhau của rủi ro.

Trong chương **Configuration security**, thuộc module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, mục tiêu là chuyển phát biểu “cấu hình dependency an toàn” thành yêu cầu cụ thể, đo được và có thể kiểm chứng. Bài học liên kết cấu hình với xác thực, phân quyền, bảo vệ dữ liệu, logging, khả năng phục hồi và bằng chứng kiểm thử trong vòng đời phát triển.

Sau bài học, người học cần có khả năng:

- Xác định dependency nào ảnh hưởng tới một bất biến bảo mật và ai sở hữu cấu hình của nó.
- Phân biệt cấu hình khai báo với cấu hình thực sự có hiệu lực tại build/runtime.
- Đặc tả endpoint, danh tính, credential, quyền, TLS, timeout, retry và hành vi khi lỗi.
- Truy vết từ kịch bản đe dọa tới yêu cầu, thiết kế, kiểm thử và quan sát vận hành.
- Kiểm tra thay đổi mặc định, nguồn ghi đè, drift, rotation và rollback mà không mở đường xử lý thiếu bảo vệ.

Các tên endpoint, URI tham chiếu, ngưỡng và schema trong bài là ví dụ học tập, không phải cấu hình dùng chung cho mọi sản phẩm. Khi tích hợp một dependency thật, phải đối chiếu giao diện cấu hình và hành vi thực tế của thành phần đó.

## 2. Phạm vi: dependency ở build và ở runtime

| Nhóm | Ví dụ | Câu hỏi bảo mật của cấu hình |
| --- | --- | --- |
| Phụ thuộc được lấy lúc build | Thư viện, plugin build, bộ xử lý annotation, build extension | Được lấy từ nguồn nào, chọn phiên bản nào, bằng chứng toàn vẹn đến từ đâu, ai được đổi nguồn? |
| Thành phần được nạp lúc runtime | Driver, SDK, middleware, serializer | Mặc định nào có hiệu lực, property nào bị bỏ qua, cấu hình có bật tính năng nguy hiểm không? |
| Dịch vụ có trạng thái | Database, cache, broker | Danh tính server/client là gì, credential có quyền gì, có truyền plaintext hoặc dùng tài khoản dùng chung không? |
| API/dịch vụ bên ngoài | Thanh toán, lưu trữ, gửi thư | Endpoint và môi trường có đúng không, dữ liệu nào được gửi, redirect/retry có làm lộ credential hoặc lặp thao tác không? |
| Hạ tầng hỗ trợ dependency | DNS, proxy, trust store, secret store, service discovery | Thành phần nào được tin để chọn đích, cấp khóa và thay cấu hình; khi chúng lỗi thì ứng dụng hành xử ra sao? |

Một dependency có thể xuất hiện ở nhiều nhóm: SDK được lấy lúc build, được cấu hình lúc runtime rồi gọi API đối tác. Cần theo dõi toàn bộ chuỗi này.

**Quản lý dependency** trả lời ứng dụng dùng thành phần nào. **Cấu hình dependency** trả lời thành phần đó được phép hoạt động ra sao. SBOM, danh sách phiên bản hoặc lockfile hỗ trợ quản lý thành phần nhưng không tự chứng minh TLS, quyền truy cập hay chính sách retry đang đúng.

Không phải mọi dependency đều hỗ trợ cùng loại bảo vệ. Nếu không thể đáp ứng một yêu cầu bắt buộc, phải thay thiết kế, chọn biện pháp bù có kiểm chứng hoặc ghi nhận ngoại lệ có thời hạn. Không đổi cách đặt tên để coi yêu cầu đã đạt.

## 3. Tài sản, mô hình đe dọa và ranh giới tin cậy

### 3.1. Tài sản và giả định

Tài sản cần bảo vệ gồm mã được thực thi, dữ liệu được gửi tới dependency, credential, quyền của tài khoản dịch vụ, tính đúng đắn của giao dịch, tài nguyên xử lý và bằng chứng audit.

Giả định tác nhân tấn công có thể gửi đầu vào tới ứng dụng, tác động tới một nguồn cấu hình có quyền thấp hơn, cung cấp endpoint hoặc nội dung từ xa trong một luồng chưa được kiểm soát, hoặc khai thác mặc định thiếu an toàn. Không giả định tác nhân đã kiểm soát toàn bộ runtime cùng mọi nguồn phê duyệt chính sách. Nếu cả chính sách được duyệt lẫn cơ chế thực thi đều bị chiếm, cần cơ chế ứng phó và phục hồi ngoài phạm vi kiểm tra một file cấu hình.

```text
Nguồn artifact / kho cấu hình / secret store / danh mục tích hợp
        |                 các quyền và bằng chứng khác nhau
        v
Build và bootstrap ứng dụng
  → xác định thành phần, cấu hình hiệu lực và nguồn từng giá trị
  → kiểm tra với chính sách được phê duyệt
        |
        v
Client/driver/SDK thực sự được khởi tạo
  → TLS + danh tính + quyền + ngân sách tài nguyên
        |
        v
Proxy / DNS / mạng / service discovery
        |
        v
Dependency đích và tác dụng nghiệp vụ
```

Mỗi mũi tên là nơi cấu hình có thể bị thay, bị hiểu khác hoặc mất ràng buộc với quyết định đã được phê duyệt. Một lần validate URL ở ứng dụng chưa kiểm soát được toàn bộ đường mạng, DNS hay redirect của client.

### 3.2. Kịch bản đe dọa

| Risk ID | Kịch bản | Hậu quả cần ngăn | Hướng kiểm soát |
| --- | --- | --- | --- |
| DCR-01 | Override đổi host API sang đích do kẻ tấn công kiểm soát | Gửi credential/dữ liệu sai đích, SSRF | Danh mục đích được phép, kiểm soát nguồn ghi đè, chính sách egress |
| DCR-02 | SDK bỏ xác minh chain hoặc hostname để vượt lỗi kết nối | Chấp nhận server giả hoặc server sai danh tính | Chính sách TLS và kiểm thử handshake thật |
| DCR-03 | Credential production dùng ở test hoặc quyền rộng hơn nhu cầu | Đọc/ghi dữ liệu ngoài phạm vi, tăng phạm vi thiệt hại | Credential theo môi trường và principal có quyền tối thiểu |
| DCR-04 | Build lấy cùng tên package từ nguồn không được phê duyệt | Thực thi mã không được phép | Kiểm soát repository, danh tính artifact và bằng chứng nguồn gốc |
| DCR-05 | Nâng SDK làm property đổi tên, giá trị cũ bị bỏ qua | Hệ thống âm thầm dùng mặc định khác chính sách | Schema, cấu hình hiệu lực và kiểm thử sau thay đổi |
| DCR-06 | Timeout quá dài, pool không giới hạn hoặc retry chồng nhiều lớp | Cạn tài nguyên, gây gián đoạn lan truyền | Deadline tổng, giới hạn đồng thời và ngân sách retry |
| DCR-07 | Retry sau timeout một thao tác ghi đã xảy ra ở đích | Thu tiền/giao hàng/cập nhật nhiều lần | Idempotency phía đích hoặc đối soát kết quả chưa rõ |
| DCR-08 | Debug log ghi header, URL hoặc connection string có bí mật | Lộ token, mật khẩu hoặc dữ liệu cá nhân | Logging theo danh sách trường cho phép, lọc tại nguồn |
| DCR-09 | Secret store hoặc hệ thống xác thực lỗi, ứng dụng chuyển sang anonymous | Chạy nghiệp vụ thiếu xác thực/phân quyền | Hành vi suy giảm được đặc tả, chặn đường thiếu bảo vệ |
| DCR-10 | Rollback/restore mang lại trust bundle, khóa hoặc endpoint cũ đã bị thu hồi | Khôi phục một đường truy cập không còn được phép | Kiểm tra với chính sách hiện hành trước mở lưu lượng |
| DCR-11 | Redirect hoặc phân giải lại DNS làm đích cuối khác đích đã validate | Vượt danh sách đích và rò rỉ dữ liệu | Kiểm soát redirect, đường mạng và danh tính peer thực tế |
| DCR-12 | Cấu hình đổi giữa các replica nhưng monitoring chỉ đọc file nguồn | Một phần lưu lượng dùng chính sách sai mà không bị phát hiện | Theo dõi cấu hình hiệu lực từng instance và phát hiện drift |

### 3.3. Các bất biến bảo mật

1. Không gửi credential hoặc dữ liệu nghiệp vụ tới một đích ngoài phạm vi tích hợp đã được phê duyệt.
2. Không coi kết nối thành công là đủ: phải xác minh danh tính peer và danh tính/quyền của client theo hợp đồng.
3. Thiếu cấu hình, cấu hình sai hoặc lỗi phụ thuộc không được làm bật một đường thiếu bảo vệ.
4. Retry và phục hồi không được tạo thêm tác dụng nghiệp vụ bị cấm.
5. Cấu hình được kiểm chứng phải là cấu hình client thực sự sử dụng, với nguồn và phiên bản có thể truy vết.

## 4. Lập hồ sơ cấu hình cho từng dependency

Trước khi viết các giá trị timeout hay bật một cờ TLS, cần có hồ sơ tích hợp. Một bảng tối thiểu gồm:

| Trường | Nội dung cần đặc tả |
| --- | --- |
| Dependency ID và owner | Định danh ổn định, đội chịu trách nhiệm, kênh xử lý sự cố |
| Loại và mức quan trọng | Thư viện/dịch vụ, đường nghiệp vụ liên quan, hậu quả khi sai hoặc không sẵn sàng |
| Danh tính thành phần | Thành phần được resolve/nạp; với artifact có version, nguồn và bằng chứng toàn vẹn |
| Endpoint/audience | Scheme, host, port, đường dẫn hoặc tên dịch vụ; môi trường, tài khoản/tenant đích |
| Danh tính client | Principal/workload được phép, cách cấp credential, scope/role cần thiết |
| Dữ liệu | Field được gửi, độ nhạy, quy tắc giảm thiểu và dữ liệu không được gửi |
| TLS/trust | Xác minh chain và peer name, nguồn trust, yêu cầu mTLS nếu có |
| Nguồn cấu hình | Nguồn chuẩn, thứ tự ưu tiên, người được đổi và nhóm trường được phép ghi đè |
| Ngân sách | Deadline, timeout từng attempt, số attempt tối đa, giới hạn đồng thời/pool và queue |
| Retry và tác dụng | Lỗi nào được retry, idempotency do ai bảo đảm, cách xử lý kết quả chưa rõ |
| Hành vi khi lỗi | Chặn, degraded mode nào được phép, thời hạn cache và điều kiện phục hồi |
| Bằng chứng | Bộ test, cấu hình hiệu lực đã che dữ liệu, policy revision và metric/audit cần có |

Hồ sơ không được chứa secret thật. Một đường dẫn tham chiếu secret, phiên bản cấu hình hoặc ID chính sách cũng có thể là metadata nhạy cảm; chỉ hiển thị cho đối tượng cần biết.

### 4.1. Cấu hình khai báo và cấu hình hiệu lực

Giả sử file khai báo `verifyPeerName: true`, nhưng một biến môi trường ghi đè thành false, SDK không đọc property đó hoặc proxy chấm dứt TLS theo cách khác. File đúng chưa chứng minh kết nối cuối cùng đạt yêu cầu.

Cần đặc tả thứ tự ưu tiên của tham số dòng lệnh, biến môi trường, file, cấu hình từ xa, profile và mặc định của thư viện. Không có một thứ tự đúng chung cho mọi framework. Với trường nhạy cảm, phải kiểm soát cả giá trị lẫn nguồn được phép cung cấp giá trị đó.

Ở bootstrap, ứng dụng nên tạo bản mô tả cấu hình hiệu lực đã che dữ liệu, nêu policy revision, dependency ID, nguồn override và trạng thái kiểm tra. Không dump toàn bộ đối tượng client hoặc môi trường tiến trình để tạo bằng chứng.

## 5. Yêu cầu bảo mật có thể kiểm chứng

Các giá trị dưới đây là hợp đồng nghiệm thu minh họa cho API thanh toán, không phải mặc định chung. Mỗi yêu cầu cần được gắn với owner và bằng chứng của tích hợp cụ thể.

| ID | Yêu cầu | Rủi ro liên quan | Bằng chứng đạt |
| --- | --- | --- | --- |
| DCFG-01 | Mỗi dependency trên đường nghiệp vụ phải có ID, owner, môi trường, principal, endpoint/audience, nguồn cấu hình và hành vi khi lỗi được phê duyệt. | DCR-01, 03, 09 | Hồ sơ đầy đủ và kiểm thử không cho khởi tạo tích hợp bắt buộc khi thiếu trường thiết yếu |
| DCFG-02 | Artifact và thành phần được nạp phải khớp danh tính/phạm vi nguồn được duyệt; thay nguồn, version hoặc graph có hiệu lực phải được kiểm tra theo quy trình thay đổi. | DCR-04, 05 | Bản resolve thực tế gồm transitive dependency và thành phần build; nguồn không được phép bị chặn |
| DCFG-03 | Cấu hình phải được kiểm tra kiểu, miền giá trị, trường bắt buộc và quan hệ giữa các trường trước khi client nhận lưu lượng. Property nhạy cảm không được âm thầm bỏ qua. | DCR-05, 12 | Test sai tên property, giá trị thiếu/sai kiểu/ngoài miền và kiểm tra client thực sự dùng giá trị được duyệt |
| DCFG-04 | Chỉ nguồn có quyền mới được đổi cấu hình; override nhạy cảm phải qua cùng kiểm tra chính sách, được gắn phiên bản và audit. | DCR-01, 12 | Thử đổi qua nguồn quyền thấp; quyết định bị chặn và audit chỉ rõ nguồn, actor, revision |
| DCFG-05 | Với API ví dụ, đích là HTTPS, host/path/port đã đăng ký; redirect bị tắt. Egress phải ngăn đường tới đích không được duyệt kể cả qua phân giải hoặc proxy. | DCR-01, 11 | Test host khác, redirect, DNS/đường mạng thay đổi; không có credential/payload được gửi tới đích trái phép |
| DCFG-06 | Client phải xác minh chain và peer name theo trust policy; không cho bật chế độ trust-all hoặc fallback plaintext trong production. | DCR-02 | Chứng thư sai tên, hết hạn, không thuộc trust và server plaintext không được nhận dữ liệu nghiệp vụ |
| DCFG-07 | Principal và credential phải tách theo môi trường/phạm vi được duyệt, chỉ có quyền cần thiết; dùng secret reference hoặc cơ chế cấp danh tính được kiểm soát. | DCR-03 | Credential test không thực hiện được thao tác production; tài khoản dịch vụ không đọc/ghi tài nguyên ngoài quyền |
| DCFG-08 | Credential/trust thay đổi phải có quy tắc reload, cache, phiên đang mở và thu hồi. Chỉ cấu hình phiên bản mới không được coi là đã chấm dứt quyền của bản cũ. | DCR-03, 10 | Test rotation/thu hồi với pool, token còn hạn và các replica; ghi rõ thời hạn tác dụng thực tế |
| DCFG-09 | Theo ví dụ, một operation có deadline không quá 3.000 ms, connect timeout không quá 300 ms, attempt không quá 800 ms, tổng attempt không quá 3 và đồng thời không quá 40. Phải tính cả retry ẩn ở các lớp. | DCR-06 | Tiêm chậm ở DNS/connect/đọc/queue; quan sát ngân sách và số lần gửi thực tế, không chỉ cấu hình một SDK |
| DCFG-10 | Retry thao tác tạo tác dụng chỉ được bật khi hợp đồng idempotency hoặc cơ chế chứng minh chưa gửi/đối soát đáp ứng yêu cầu. Không tự tạo khóa idempotency mới cho mỗi attempt của cùng operation. | DCR-07 | Timeout sau commit phía đích, mất response và retry đồng thời không tạo thêm khoản thu bị cấm |
| DCFG-11 | Lỗi secret store, TLS, xác thực, phân quyền hoặc cấu hình không được kích hoạt anonymous/trust-all/plaintext hay credential của môi trường khác. | DCR-02, 03, 09 | Tiêm từng lỗi và kiểm tra không có fallback trái chính sách; degraded mode có phạm vi/thời hạn rõ |
| DCFG-12 | Chỉ gửi dữ liệu cần thiết tới dependency đúng phạm vi; không đưa token/mật khẩu vào URL, log, trace hoặc thông báo lỗi. | DCR-01, 08 | Kiểm tra request ở đích thử và các kênh log/trace/metrics; dữ liệu bị cấm không xuất hiện |
| DCFG-13 | Cấu hình hiệu lực phải gắn dependency ID và policy revision; audit thay đổi phải nêu actor, thời điểm, nguồn và kết quả, không chứa secret. | DCR-08, 12 | Đối chiếu từng replica với revision; audit đủ truy vết và che dữ liệu theo chính sách |
| DCFG-14 | Trong ví dụ, phát hiện drift trường nhạy cảm trong 60 giây; gửi cảnh báo trong 120 giây từ lúc phát hiện. Giá trị biết là sai bị chặn tại điểm thực thi, không đợi cảnh báo. | DCR-12 | Tiêm drift ở một replica và làm lỗi quan sát; cảnh báo đúng hạn, không có đường gọi trái policy đã biết |
| DCFG-15 | Nâng cấp, rollback, restore hoặc đổi proxy/trust phải kiểm tra lại cấu hình hiệu lực và các bất biến trước khi mở lưu lượng. | DCR-02, 05, 10 | Regression trên bản thay đổi và phục hồi; endpoint/credential/trust bị thu hồi không sống lại |
| DCFG-16 | Ngoại lệ phải có phạm vi dependency, môi trường, rủi ro còn lại, biện pháp bù, owner, người phê duyệt và ngày hết hạn; không tự gia hạn khi dependency lỗi. | Các rủi ro được miễn trừ | Ngoại lệ hết hạn bị xử lý đúng; không mở rộng sang dependency khác hoặc bỏ kiểm tra toàn cục |

### 5.1. Mẫu đặc tả chi tiết

```text
ID: DCFG-06
Mục tiêu: không gửi credential hoặc dữ liệu thanh toán tới server giả
Phạm vi: client payment-partner ở production
Rủi ro: DCR-02
Điều kiện bắt buộc:
  - TLS hoạt động theo chính sách được duyệt
  - Chuỗi chứng thư được xác minh với trust bundle được phép
  - Danh tính peer phù hợp hostname/danh tính dịch vụ mong đợi
  - Không có trust-all, bỏ peer verification hoặc fallback plaintext
Không đạt:
  - Không gửi request nghiệp vụ có credential/payload
  - Phân loại lỗi kết nối, audit đã che dữ liệu và cảnh báo theo chính sách
Owner: đội ứng dụng phối hợp đội nền tảng và bảo mật
Kiểm chứng: test handshake qua đúng client và tuyến triển khai
Bằng chứng: cấu hình hiệu lực, revision trust, kết quả handshake và quan sát đích thử
```

“Có TLS” hoặc “dependency dùng port 443” không đủ để nghiệm thu yêu cầu này. Cần kiểm tra chính hành vi xác minh và tác dụng khi xác minh không đạt.

## 6. Cấu hình dependency ở build và khi nạp thành phần

### 6.1. Kiểm soát nguồn và kết quả resolve

Danh sách dependency khai báo trực tiếp chưa mô tả toàn bộ mã có thể chạy. Plugin build, extension, bộ sinh mã, dependency bắc cầu và thành phần native cũng có thể ảnh hưởng tới kết quả.

Yêu cầu nên xác định repository được phép, danh tính artifact, chính sách version và bằng chứng nguồn gốc/toàn vẹn phù hợp. Nếu yêu cầu build có thể tái tạo, phải quản lý graph thực sự được resolve cùng các đầu vào liên quan; chỉ cố định một vài version trực tiếp chưa bảo đảm điều đó.

Checksum chỉ phát hiện sai lệch so với giá trị tham chiếu. Nếu artifact và checksum đều lấy từ cùng nguồn đã bị chiếm, chúng có thể cùng bị thay. Chữ ký, provenance hoặc digest cũng cần một gốc tin cậy và quy tắc xác minh được duyệt; không có bằng chứng nào tự hữu ích chỉ vì được ghi vào log.

### 6.2. Repository, mirror và credential của build

- Không cho cấu hình quyền thấp tùy ý thêm repository để ghi đè namespace nội bộ.
- Quy định mirror/repository nào được phục vụ nhóm artifact nào và kiểm tra resolution thực tế.
- Tách credential tải artifact với quyền xuất bản artifact, ưu tiên quyền đọc theo phạm vi cần thiết.
- Không ghi token repository vào file source, lệnh hiển thị công khai hoặc báo cáo build.
- Kiểm tra các profile, biến môi trường và cấu hình người dùng có thể thay repository hoặc plugin.

Một version bất biến trong kho được kiểm soát giúp giảm nhập nhằng, nhưng không chứng minh mã không có lỗ hổng. Quản lý lỗ hổng và nguồn gốc là yêu cầu liên quan; chúng không thay thế yêu cầu cấu hình runtime của bài này.

### 6.3. Kiểm tra tương thích sau nâng cấp

Khi dependency đổi version, phải xác nhận property bảo mật còn được hỗ trợ, mặc định có thay đổi không và lỗi parse có bị bỏ qua không. Thử xóa hoặc viết sai một property nhạy cảm để chứng minh cơ chế phát hiện hoạt động.

Một bản nâng cấp có thể đổi chính sách redirect, retry, pool, proxy hoặc logging mà không đổi API nghiệp vụ của ứng dụng. Cần kiểm thử các thuộc tính đó, không chỉ kiểm tra ứng dụng khởi động thành công.

## 7. Ví dụ cấu hình runtime cho API đối tác

Giả sử dịch vụ đơn hàng gọi API thanh toán để tạo một khoản thu. Đây là **schema chính sách minh họa do ứng dụng sở hữu**, không phải các property có thể sao chép trực tiếp vào một SDK bất kỳ.

```yaml
schemaVersion: 1
policyRevision: payment-partner-prod-r7
environment: production
dependencyId: payment-partner
owner: payments-platform
endpointUrl: https://payments.partner.example/v1/charges
allowedRedirects: 0
egressPolicyRef: network-policy://production/payment-partner

tls:
  verifyChain: true
  verifyPeerName: true
  trustBundleRef: trust://production/payment-partner/bundle-v4

auth:
  credentialRef: secret://prod/payments/partner-api
  expectedAudience: payment-partner-production
  requiredPermissions:
    - charge.create

budgets:
  operationDeadlineMs: 3000
  connectTimeoutMs: 300
  attemptTimeoutMs: 800
  totalAttempts: 3
  backoffMs: [100, 200]
  maxConcurrentCalls: 40

retry:
  requiresDestinationIdempotency: true
  stableOperationKeyRequired: true
  retryableStatuses: [503]
  unknownOutcome: reconcile

logging:
  allowedFields: [dependencyId, policyRevision, outcome, durationMs, attempt]
  requestBodyEnabled: false
  authorizationHeaderEnabled: false
```

Các URI tham chiếu chỉ biểu thị trách nhiệm tra cứu qua registry được kiểm soát. Chúng không phải cú pháp chuẩn của một secret manager, công cụ mạng hay trust store cụ thể. Quyền đọc các tham chiếu phải gắn với workload production tương ứng.

### 7.1. Giải thích các ràng buộc

- `endpointUrl` phải khớp tích hợp đã đăng ký; request nghiệp vụ không được ghi đè host, port, path hoặc môi trường.
- `trustBundleRef` xác định nguồn trust được duyệt. Trong ví dụ client xác minh cả chain và peer name; không dùng một custom verifier luôn trả true để khớp hai cờ trên giấy.
- `expectedAudience` và quyền phải phù hợp cơ chế xác thực mà đối tác hỗ trợ. Việc thêm một header tự khai audience không tự làm token có audience đúng.
- `credentialRef` trỏ tới credential có phạm vi hẹp; giá trị bí mật được cấp lúc cần theo cơ chế kiểm soát, không đóng gói trong artifact.
- `totalAttempts: 3` bao gồm lần đầu, không phải ba lần retry sau lần đầu.
- Retry mã 503 chỉ được phép khi hợp đồng idempotency của đích đã được kiểm chứng. Mã lỗi hoặc timeout không tự chứng minh phía đích chưa thu tiền.
- `unknownOutcome: reconcile` nghĩa là xử lý kết quả chưa rõ bằng tra cứu/đối soát có định danh, không coi đó là thất bại chắc chắn rồi tạo một khoản thu mới.

Các trường dùng để áp đặt chính sách không được cùng phụ thuộc vào một nguồn override quyền thấp. Nếu kẻ tấn công sửa được cả endpoint lẫn danh sách endpoint “được phép”, phép so sánh hai giá trị đó không còn tạo ranh giới bảo vệ.

### 7.2. Deadline tổng và retry nhiều lớp

Với các giá trị minh họa, ngân sách ba attempt và hai khoảng backoff là:

```text
3 × 800 ms + 100 ms + 200 ms = 2700 ms
operation deadline = 3000 ms
phần còn lại tối đa = 300 ms
```

Connect timeout nằm trong ngân sách attempt của hợp đồng này, không cộng thêm 300 ms cho mỗi attempt. Deadline tổng phải bao phủ các bước thuộc operation như chờ permit/pool, resolve đích, lấy credential nếu cần, kết nối, TLS, gửi, đọc và backoff. Trước mỗi attempt cần kiểm tra thời gian còn lại; không bắt đầu một attempt với ngân sách đầy đủ khi deadline sắp hết.

Cách một thư viện áp timeout cho DNS, connect hay read có thể khác hợp đồng tổng. Phải có cơ chế deadline/cancellation và đo qua đường triển khai thực; đặt một giá trị socket read timeout chưa bảo đảm toàn operation kết thúc đúng hạn.

Nếu SDK tự gửi ba lần còn ứng dụng cũng thử ba lần, có thể có tới chín lần gửi trước khi xét retry của proxy. Cần một ngân sách xuyên các lớp và quan sát số lần gửi thực tế. Hết deadline chỉ chấm dứt chờ/xử lý theo chính sách receiver; không hoàn tác được tác dụng đã xảy ra ở đối tác.

Giới hạn 40 cuộc gọi đồng thời cũng chưa đủ nếu trước nó có hàng chờ vô hạn. Cần giới hạn hoặc loại bỏ hàng chờ, tính thời gian chờ vào deadline và đặc tả kết quả quá tải. Nếu giới hạn là toàn dịch vụ, phải có cơ chế thực thi phù hợp giữa các replica; giới hạn cục bộ 40 trên mỗi replica không tự thành giới hạn toàn cục 40.

## 8. Triển khai kiểm tra và áp dụng cấu hình

### 8.1. Luồng từ bootstrap tới request

```text
1. Nạp policy revision từ nguồn được phép và xác minh quyền/nguồn theo thiết kế.
2. Nạp cấu hình theo thứ tự ưu tiên đã công bố; giữ provenance từng trường.
3. Kiểm tra schema, trường lạ, miền giá trị và các ràng buộc chéo.
4. Đối chiếu endpoint, môi trường, credential reference và quyền với policy.
5. Tra credential/trust theo workload identity được phép.
6. Tạo client với TLS, redirect, proxy, deadline, pool và retry rõ ràng.
7. Kiểm tra cấu hình có hiệu lực và probe không tạo tác dụng ngoài ý muốn.
8. Chỉ mở tuyến nghiệp vụ khi điều kiện bắt buộc đạt.
9. Với mỗi operation: ràng buộc đích/quyền/dữ liệu, thực thi ngân sách và idempotency.
10. Ghi kết quả đã che dữ liệu; theo dõi rotation, drift và sức khỏe dependency.
```

Với dependency bắt buộc cho một thao tác nhạy cảm, “readiness đạt” phải có ý nghĩa cụ thể. Ứng dụng có thể vẫn phục vụ health endpoint hoặc chức năng độc lập khi một dependency bị chặn; điều đó không cho phép tuyến nhạy cảm đi qua client chưa hợp lệ.

Probe cần dùng endpoint/credential và dữ liệu thử được phép. Không tạo khoản thu thật, gửi thư thật hay sửa dữ liệu chỉ để kiểm tra kết nối nếu chưa có hợp đồng riêng cho tác dụng đó.

### 8.2. Ví dụ Java kiểm tra policy trước khi khởi tạo client

Đoạn mã dùng các kiểu chuẩn của Java. Các hằng số đại diện cho hồ sơ tích hợp đã được phê duyệt độc lập; trong hệ thống thực, chúng có thể đến từ một nguồn policy được xác minh. Mã chỉ kiểm tra cấu hình khai báo trước khi tạo client, không thay thế TLS handshake, kiểm soát mạng hoặc kiểm tra quyền ở dependency đích.

```java
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class DependencyConfigurationExample {
    private static final String APPROVED_HOST = "payments.partner.example";
    private static final String APPROVED_PATH = "/v1/charges";
    private static final String APPROVED_CREDENTIAL_REF =
            "secret://prod/payments/partner-api";

    public record Config(
            URI endpoint,
            String credentialRef,
            boolean verifyChain,
            boolean verifyPeerName,
            boolean followRedirects,
            int connectTimeoutMs,
            int attemptTimeoutMs,
            int operationDeadlineMs,
            int totalAttempts,
            int maxConcurrentCalls) {}

    public static List<String> validate(Config config) {
        Objects.requireNonNull(config);
        List<String> errors = new ArrayList<>();
        URI endpoint = config.endpoint();
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())
                || !APPROVED_HOST.equalsIgnoreCase(endpoint.getHost())
                || (endpoint.getPort() != -1 && endpoint.getPort() != 443)
                || !APPROVED_PATH.equals(endpoint.getRawPath())
                || endpoint.getRawUserInfo() != null
                || endpoint.getRawQuery() != null
                || endpoint.getRawFragment() != null) {
            errors.add("endpoint_not_approved");
        }
        if (!APPROVED_CREDENTIAL_REF.equals(config.credentialRef())) {
            errors.add("credential_reference_not_approved");
        }
        if (!config.verifyChain() || !config.verifyPeerName()) {
            errors.add("tls_verification_required");
        }
        if (config.followRedirects()) {
            errors.add("redirects_not_allowed");
        }
        if (config.connectTimeoutMs() <= 0 || config.connectTimeoutMs() > 300
                || config.attemptTimeoutMs() <= 0 || config.attemptTimeoutMs() > 800
                || config.operationDeadlineMs() <= 0
                || config.operationDeadlineMs() > 3000) {
            errors.add("timeout_out_of_policy");
        }
        if (config.connectTimeoutMs() > config.attemptTimeoutMs()
                || config.attemptTimeoutMs() > config.operationDeadlineMs()) {
            errors.add("timeout_order_invalid");
        }
        if (config.totalAttempts() < 1 || config.totalAttempts() > 3) {
            errors.add("attempt_limit_invalid");
        }
        if (config.maxConcurrentCalls() < 1 || config.maxConcurrentCalls() > 40) {
            errors.add("concurrency_limit_invalid");
        }
        return List.copyOf(errors);
    }
}
```

Một URI có host `payments.partner.example.attacker.example` không khớp host được phép. URL có userinfo, query hoặc fragment cũng bị từ chối trong profile này; không gửi token trong query. Kiểm tra raw path chính xác tránh tự chấp nhận một path mã hóa/chuẩn hóa khác mà chưa có hợp đồng tương ứng.

Schema/binder đứng trước record phải từ chối trường nhạy cảm viết sai, trường bắt buộc thiếu và kiểu dữ liệu không đúng. `validate` không tự biết một property đã bị binder bỏ qua. Mọi lỗi parse hoặc lỗi validation phải ngăn khởi tạo tuyến tích hợp, không catch rồi tạo client bằng mặc định.

Khi danh sách lỗi rỗng, adapter vẫn phải ánh xạ rõ các giá trị sang API cấu hình thực của client và kiểm tra hành vi qua kết nối thật. Ví dụ này chưa cài TLS, deadline tổng, backoff, semaphore, secret reload hoặc idempotency; không được dùng việc `validate` đạt để tuyên bố đã hoàn thành các kiểm soát đó.

### 8.3. SSRF, DNS, redirect và proxy

Endpoint allowlist là một lớp bảo vệ. Cần xác định nơi nào thực sự phân giải và kết nối tới đích: ứng dụng, proxy hay service mesh. Nếu ứng dụng kiểm tra một kết quả DNS rồi client resolve lại ra địa chỉ khác, kiểm tra trước đó có thể không ràng buộc với kết nối thực tế.

Thiết kế phải kiểm soát đích cuối theo chính sách egress và danh tính peer, kể cả IPv4/IPv6, redirect và proxy. Không cấm chung mọi địa chỉ private nếu tích hợp hợp lệ dùng mạng private; cần quy định phạm vi đích được phép cho từng dependency. Đồng thời không cho một dependency công khai truy cập metadata, loopback hoặc dịch vụ nội bộ ngoài phạm vi đã duyệt.

Nếu có lý do cho phép redirect, phải quy định số hop, scheme/đích được phép và việc chuyển tiếp credential. Không mặc định Authorization hoặc payload được phép đi tới origin mới. Profile thanh toán của bài chọn không theo redirect để giữ hợp đồng đích rõ ràng.

### 8.4. Khả năng mở rộng theo loại dependency

| Loại dependency | Điều cần ánh xạ từ policy sang triển khai |
| --- | --- |
| Database | Danh tính server, trust, quyền tài khoản, database/schema được phép, pool, transaction/query timeout và xử lý phiên đang mở khi rotation |
| Cache | Xác thực, quyền theo key/namespace nếu hệ thống hỗ trợ, bảo vệ đường truyền, giới hạn dữ liệu và hành vi khi cache lỗi |
| Broker | Danh tính broker/client, quyền publish/consume theo topic/queue, bảo vệ metadata, retry/ack và quyền phát message vào luồng tin cậy |
| SDK API | Endpoint/audience, token/scope, redirect/proxy, retry ẩn, logging request/response và mô hình tác dụng ngoài |
| Parser/serializer | Chế độ xử lý dữ liệu không tin cậy, tính năng tải tài nguyên/khởi tạo kiểu theo dữ liệu, giới hạn kích thước/độ sâu theo khả năng sản phẩm |

Tên property và tính năng cụ thể phụ thuộc sản phẩm. Yêu cầu cần mô tả hành vi phải đạt; adapter cấu hình và test chứng minh dependency đã được cấu hình để tạo hành vi đó.

## 9. Credential, trust, rotation và hành vi suy giảm

### 9.1. Tách credential và quyền

Credential dùng để tải thư viện, quản lý cấu hình và gọi API nghiệp vụ có mục đích khác nhau. Không dùng chung một credential quyền quản trị để giải quyết cả ba việc. Không cho một workload test lấy credential production chỉ vì chúng dùng cùng tên dependency.

Tham chiếu secret cần được đối chiếu với dependency, môi trường và principal đã đăng ký. Không chấp nhận một đường dẫn secret bất kỳ từ request rồi dùng danh tính dịch vụ đặc quyền để đọc giúp. Quyền ở secret store và quyền ở dependency đích đều cần được kiểm chứng.

Nếu nền tảng hỗ trợ cấp danh tính/token ngắn hạn cho workload, cần đặc tả audience, scope, thời hạn và cơ chế làm mới. Nếu phải dùng secret dài hạn, cần nơi lưu, thời hạn thay, quyền đọc và quy trình thu hồi. Chuyển một secret sang biến môi trường không tự làm secret biến mất khỏi memory dump, tiến trình con hoặc công cụ chẩn đoán.

### 9.2. Rotation không đồng nghĩa thu hồi

Một luồng thay credential có thể gồm: cấp bản mới, xác nhận quyền, chuyển client, xử lý cache/pool, kiểm tra các replica, rồi vô hiệu hóa bản cũ theo lịch được duyệt. Trong giai đoạn chuyển tiếp, hai bản có thể cùng được phép nếu chính sách chấp nhận rủi ro đó.

Thu hồi khẩn cấp cần quy tắc riêng. Không duy trì grace period cho credential đã xác định bị lộ chỉ để tránh lỗi. Cần biết token đã phát, phiên database, connection pool hoặc request đang chạy có tiếp tục được chấp nhận không.

Ví dụ một tích hợp đặt mục tiêu sau quyết định thu hồi không quá 60 giây, các operation mới không còn dùng credential cũ và phía đích cũng từ chối quyền cũ theo phạm vi cam kết. Muốn nghiệm thu phải kiểm tra toàn chuỗi. Nếu token tự chứa còn hạn 15 phút và phía đích không hỗ trợ vô hiệu hóa sớm, chỉ reload client trong 60 giây không đáp ứng cam kết thu hồi quyền ở đích. Phải đổi thời hạn/cơ chế, bổ sung kiểm soát hoặc công bố ngoại lệ có phê duyệt.

Không gọi việc đổi reference thành công là rotation hoàn tất khi replica cũ hoặc pool cũ vẫn dùng quyền trái chính sách. Tác dụng đã được dependency chấp nhận trước thời điểm thu hồi cũng không tự bị hoàn tác.

### 9.3. Thay trust bundle và danh tính peer

Thay certificate hoặc CA có thể cần giai đoạn chuyển tiếp trust được phê duyệt và kiểm thử chuỗi chứng thư thực tế. Không khắc phục certificate renewal bằng cách tắt xác minh tên hoặc trust-all.

Nếu thiết kế dùng pinning, phải đặc tả điều gì được pin, phạm vi, cách thay pin và hành vi khi không khớp. Một fingerprint được đóng cứng nhưng không có kế hoạch thay có thể làm dịch vụ gián đoạn; bỏ pin lúc sự cố mà không có kiểm soát sẽ thay đổi bảo đảm ban đầu.

Trust cấu hình ở ứng dụng, proxy và hệ điều hành có thể khác nhau. Cần kiểm tra nơi nào thực sự thực hiện từng handshake và danh tính nào được xác minh ở mỗi hop. Chỉ quan sát TLS giữa ứng dụng và proxy chưa chứng minh tuyến proxy tới dependency đạt cùng chính sách.

### 9.4. Fail closed và degraded mode

Fail closed nghĩa là không cho một thao tác cần bảo vệ tiếp tục khi điều kiện bảo vệ bắt buộc không đạt. Nó không bắt buộc mọi chức năng của hệ thống đều ngừng.

| Tình huống | Hành vi minh họa được phép | Hành vi vi phạm |
| --- | --- | --- |
| Không lấy được credential | Chặn tạo khoản thu mới, báo lỗi tạm thời theo hợp đồng | Dùng tài khoản anonymous hoặc credential test |
| TLS không xác minh được | Chặn request nhạy cảm, cảnh báo và kiểm tra trust/peer | Thử lại bằng HTTP hoặc trust-all |
| Cache nghiệp vụ lỗi | Dùng đường đọc đã được phân quyền hoặc dữ liệu cache còn hợp lệ theo chính sách | Bỏ kiểm tra quyền vì cache quyền không sẵn sàng |
| API thanh toán timeout sau khi gửi | Giữ trạng thái kết quả chưa rõ, tra cứu/đối soát theo operation ID | Tự tạo khoản thu mới với ID khác |
| Cấu hình từ xa không sẵn sàng | Dùng bản đã xác minh còn hiệu lực nếu hợp đồng cho phép, có giới hạn tuổi và thu hồi | Dùng vô hạn cấu hình cũ hoặc tạo mặc định thiếu bảo vệ |

Last-known-good phải thực sự còn tốt theo chính sách hiện hành, có thời hạn và nguồn tin cậy. Một bản cũ chứa credential đã thu hồi không còn là phương án phục hồi hợp lệ dù trước đây từng chạy thành công.

## 10. Quản lý thay đổi, drift và rollback

Một thay đổi dependency cần được đánh giá bằng **sự khác biệt của hành vi có hiệu lực**, không chỉ bằng diff file. Cùng một file có thể cho kết quả khác khi SDK, môi trường, proxy hoặc mặc định thay đổi.

Quy trình minh họa:

1. Ghi rõ dependency, rủi ro và trường bị đổi; đối chiếu yêu cầu DCFG liên quan.
2. Resolve/nạp thành phần dự kiến và kiểm tra schema cùng nguồn override.
3. Chạy test cấu hình âm tính, TLS, quyền, timeout/retry và logging trên môi trường thử phù hợp.
4. Tạo bằng chứng cấu hình hiệu lực đã che dữ liệu; gắn revision của ứng dụng, dependency và policy.
5. Triển khai có giới hạn, theo dõi kết quả và chặn tuyến chưa đạt điều kiện.
6. Khi rollback, đối chiếu với danh mục endpoint, credential và trust hiện hành trước mở lại lưu lượng.

Với cập nhật nóng, nên validate một snapshot hoàn chỉnh rồi chuyển client theo cơ chế nhất quán. Tránh trạng thái nửa cũ nửa mới, chẳng hạn endpoint mới nhưng credential hoặc audience của môi trường cũ. Ghi rõ cách xử lý request đang chạy và thời hạn rút client cũ.

Drift cần được đánh giá ở từng replica hoặc đơn vị thực thi có thể nhận request. Dùng một fingerprint của các trường không bí mật để so sánh có thể hữu ích, nhưng không hash secret có miền giá trị nhỏ rồi công bố fingerprint. Các trường nhạy cảm nên có reference/version được kiểm soát thay vì phát tán giá trị.

Ngưỡng phát hiện 60 giây và cảnh báo 120 giây ở DCFG-14 là mục tiêu vận hành của ví dụ. Cơ chế validate tại lần nạp cấu hình phải chặn giá trị biết là sai ngay. Theo dõi drift không cho phép cố ý dùng cấu hình sai tới hết chu kỳ quét.

## 11. Logging, metric và bằng chứng vận hành

Thông tin hữu ích gồm dependency ID, policy revision, phiên bản client, loại kết quả, attempt, thời lượng, lỗi xác minh peer, lỗi xác thực/phân quyền, trạng thái refresh credential và drift. Nhãn metric phải có tập giá trị được kiểm soát; không dùng token, toàn bộ URL, operation ID hoặc payload làm nhãn không giới hạn.

Audit thay cấu hình nên ghi actor hoặc danh tính tiến trình, thời điểm, nguồn, trường đã đổi theo phạm vi được phép, revision trước/sau và quyết định phê duyệt/áp dụng. Không cần ghi secret cũ/mới để chứng minh secret đã thay.

Logging theo danh sách trường cho phép thường dễ kiểm soát hơn dump request rồi cố che một vài chuỗi. Cần kiểm tra cả SDK debug log, exception của driver, trace exporter và crash report. Một connection string có thể chứa mật khẩu; một URL lỗi có thể chứa query nhạy cảm. Masking ở màn hình không chứng minh dữ liệu gốc chưa được chuyển tới log backend.

Cảnh báo cần có owner và thời hạn cho ít nhất các tình trạng: drift nhạy cảm, lỗi TLS bất thường, lỗi quyền tăng, refresh credential thất bại, deadline/retry vượt ngân sách và mất quan sát cấu hình. Cảnh báo phải phân biệt dependency không sẵn sàng với việc policy đã chặn một cấu hình sai, để đội vận hành không vô tình tắt bảo vệ nhằm giảm số lỗi.

## 12. Ma trận kiểm thử nghiệm thu

Dùng endpoint thử, credential thử và dữ liệu tổng hợp. Không cần gọi dịch vụ thật để kiểm chứng một validator, nhưng phải có kiểm thử tích hợp qua đúng client, proxy và cơ chế cấp quyền trước khi kết luận hệ thống đáp ứng hành vi runtime.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-DCFG-01 | Thiếu owner/endpoint/credential reference bắt buộc; sai tên property bảo mật hoặc sai kiểu | Không mở tuyến tích hợp bắt buộc; báo lỗi trường, không lộ giá trị bí mật | DCFG-01, 03 |
| T-DCFG-02 | Thêm repository/override có quyền thấp; dependency bắc cầu hoặc plugin resolve từ nguồn ngoài phạm vi | Resolution hoặc áp dụng bị chặn; bằng chứng cho thấy nguồn thực, không chỉ cấu hình khai báo | DCFG-02, 04 |
| T-DCFG-03 | Đổi host sang tên có hậu tố giống, userinfo URL, port/path khác hoặc query chứa token | Profile ví dụ từ chối; không gửi credential/payload tới đích đó | DCFG-05, 12 |
| T-DCFG-04 | Đích trả redirect; đổi DNS hoặc tuyến proxy; thử địa chỉ/route ngoài phạm vi qua IPv4 và IPv6 | Đích cuối vẫn bị chính sách kiểm soát; redirect không được theo trong profile; không có dữ liệu nghiệp vụ ở đích trái phép | DCFG-05 |
| T-DCFG-05 | Chứng thư sai hostname, hết hạn, không thuộc trust; server plaintext hoặc verifier tùy biến bỏ kiểm tra | Kết nối nghiệp vụ không được thực hiện; không có fallback thiếu xác minh | DCFG-06, 11 |
| T-DCFG-06 | Credential test gọi production; principal hợp lệ thử quyền đọc/ghi ngoài scope | Phía đích từ chối quyền không được cấp; không chỉ dựa vào kiểm tra tên reference ở ứng dụng | DCFG-07 |
| T-DCFG-07 | Rotation khi có pool, cache token và hai replica; thu hồi bản cũ rồi thử operation mới | Hành vi đạt thời hạn đã cam kết; token/phiên chưa bị vô hiệu phải được phát hiện, không báo đạt chỉ vì reference đổi | DCFG-08 |
| T-DCFG-08 | Chậm lần lượt ở chờ permit/pool, DNS, connect, TLS và read; thử vượt 40 operation đồng thời | Deadline và giới hạn có hiệu lực theo phạm vi cam kết; hàng chờ không tăng vô hạn; đếm actual attempt không vượt 3 | DCFG-09 |
| T-DCFG-09 | SDK, ứng dụng và proxy cùng có retry; đáp ứng 503 rồi thành công hoặc giữ chậm tới deadline | Tổng ngân sách xuyên lớp không bị nhân ngoài hợp đồng; không khởi động attempt mới sau deadline | DCFG-09, 10 |
| T-DCFG-10 | Đích ghi nhận khoản thu nhưng response bị mất; gửi lại cùng operation và thử hai request đồng thời | Không có khoản thu thứ hai bị cấm; dùng cùng định danh idempotency hoặc đối soát khi kết quả chưa rõ | DCFG-10 |
| T-DCFG-11 | Secret store lỗi, token hết hạn, TLS lỗi hoặc dependency từ chối quyền | Chặn thao tác bắt buộc; không dùng anonymous, test credential, trust-all hoặc HTTP thay thế | DCFG-11 |
| T-DCFG-12 | Bật diagnostic/debug ở môi trường thử, tạo lỗi có URL/header/connection string nhạy cảm | Secret và field bị cấm không có trong log, trace, metric, exception hoặc báo cáo chẩn đoán thuộc phạm vi | DCFG-12, 13 |
| T-DCFG-13 | Một replica dùng revision cũ/sai; gây mất telemetry và thay nguồn override | Phát hiện/cảnh báo đúng hạn của ví dụ; biết được replica và revision, không lộ secret | DCFG-04, 13, 14 |
| T-DCFG-14 | Nâng SDK khiến một property bảo mật không còn được hỗ trợ hoặc mặc định retry thay đổi | Pipeline phát hiện cấu hình/hành vi không đạt trước mở lưu lượng; không chỉ dựa vào app khởi động | DCFG-02, 03, 15 |
| T-DCFG-15 | Rollback/restore tới bản có endpoint, credential hoặc trust không còn được phép | Kiểm tra với policy hiện hành và chặn đường trái quyền; không khôi phục cấu hình cũ một cách mù quáng | DCFG-08, 15 |
| T-DCFG-16 | Ngoại lệ hết hạn hoặc được đem dùng ở dependency/môi trường khác | Không áp dụng miễn trừ ngoài phạm vi; audit nêu quyết định và người chịu trách nhiệm | DCFG-16 |

### 12.1. Tiêu chí chấp nhận cụ thể

**AC-01 — Chặn cấu hình sai trước request đầu tiên.** Given hồ sơ production đã duyệt và credential thử có thể nhận diện ở đích thử. When cấu hình endpoint sang host ngoài danh mục hoặc tắt peer verification. Then tuyến tích hợp không trở thành ready; không có request nghiệp vụ mang credential/payload tới đích sai; audit ghi lý do và revision mà không ghi secret.

**AC-02 — Cấu hình đúng phải hoạt động.** Given endpoint thử có danh tính TLS đúng, credential đúng quyền và policy hợp lệ. When gọi một operation thử không tạo tác dụng ngoài ý muốn. Then request tới đúng đích, xác thực đúng principal và nhận kết quả mong đợi trong ngân sách. Một hệ thống chặn mọi kết nối không được coi là đạt yêu cầu tích hợp chỉ vì các test âm tính đều bị chặn.

**AC-03 — Retry không nhân tác dụng.** Given đích thử có idempotency theo hợp đồng và đã commit operation `charge-demo-001`. When response đầu bị mất và client retry với cùng khóa operation trong ngân sách. Then có một khoản thu hợp lệ ở đích; số lần gửi không vượt hợp đồng. Nếu trạng thái chưa xác định, ứng dụng giữ kết quả cần đối soát thay vì tự tạo operation mới.

**AC-04 — Rotation có hiệu lực thực tế.** Given hai replica và connection/token cache đang dùng credential cũ. When thực hiện quy trình thay/thu hồi đã phê duyệt. Then sau thời hạn cam kết không có operation mới trái policy qua bản cũ; bằng chứng có quan sát ở cả client lẫn phía đích. Nếu quyền cũ vẫn còn, kết quả là không đạt dù mọi file đã trỏ tới bản mới.

**AC-05 — Phục hồi không làm sống lại quyền cũ.** Given một revision trước đây hợp lệ nhưng endpoint hoặc credential của nó đã bị thu hồi. When rollback ứng dụng hoặc restore cấu hình. Then hệ thống đối chiếu policy hiện hành và không mở tuyến nhạy cảm bằng quyền đã thu hồi; vẫn phục vụ được các chức năng độc lập nếu thiết kế cho phép.

### 12.2. Bằng chứng và giới hạn của kiểm thử

Báo cáo nghiệm thu cần ghi revision ứng dụng, dependency và policy, topology thử, nguồn override, dữ liệu tổng hợp, kết quả trước/sau cùng trạng thái đích. Với timeout/retry, cần số lần gửi và thời gian đo thực tế. Với TLS, cần kết quả handshake và chứng cứ không gửi dữ liệu nghiệp vụ khi không đạt. Với rotation, cần phạm vi và thời hạn của token, session và các replica.

Một unit test của validator không chứng minh SDK đã áp đúng TLS/timeout. Một test từ chối request cũng không tự chứng minh không có tác dụng nếu đích đã nhận trước đó. Ngược lại, HTTP 2xx không tự chứng minh principal, môi trường hoặc dữ liệu gửi đã đúng phạm vi.

Đồng hồ đơn điệu phù hợp nên được dùng để đo thời lượng theo bảo đảm nền tảng. Không dùng chênh lệch giờ lịch có thể bị chỉnh để kết luận deadline đã đạt. Không ghi secret thật vào fixture hoặc báo cáo để chứng minh một phép kiểm tra.

## 13. Truy vết yêu cầu trong vòng đời phát triển

```text
Mục tiêu: chỉ dùng đúng dependency với đúng danh tính, dữ liệu và ngân sách
  → DCR-xx: kịch bản thay đích, bỏ TLS, quyền rộng, retry lặp, rollback sai
  → DCFG-xx: yêu cầu có phạm vi và bằng chứng
  → Hồ sơ tích hợp + schema + client/driver + chính sách mạng/quyền
  → T-DCFG-xx và AC-xx
  → Cấu hình hiệu lực, audit, metric, runbook và phục hồi
```

| Quyết định thiết kế | Yêu cầu | Kiểm chứng tiêu biểu |
| --- | --- | --- |
| Endpoint cố định theo tích hợp và kiểm soát egress | DCFG-04, 05 | T-DCFG-03, 04; AC-01, 02 |
| TLS xác minh đúng peer, không fallback | DCFG-06, 11 | T-DCFG-05, 11; AC-01, 02 |
| Quyền theo môi trường và rotation có thời hạn | DCFG-07, 08 | T-DCFG-06, 07; AC-04 |
| Ngân sách xuyên lớp và idempotency theo operation | DCFG-09, 10 | T-DCFG-08, 09, 10; AC-03 |
| Cấu hình hiệu lực có phiên bản, drift được quan sát | DCFG-03, 13, 14 | T-DCFG-01, 12, 13 |
| Upgrade/rollback kiểm tra với policy hiện hành | DCFG-02, 08, 15 | T-DCFG-14, 15; AC-05 |

Khi endpoint, principal, quyền, version SDK, trust, proxy, thứ tự override hoặc khả năng idempotency thay đổi, phải xem lại những yêu cầu và test liên quan. Chủ dịch vụ chịu trách nhiệm về hành vi nghiệp vụ; đội nền tảng chịu trách nhiệm các kiểm soát hạ tầng được giao; đội bảo mật hỗ trợ chính sách và đánh giá rủi ro. Việc chia trách nhiệm không được để một kiểm soát bắt buộc không có owner.

## 14. Lỗi đặc tả thường gặp

| Cách viết/triển khai | Vì sao chưa đủ | Cách sửa |
| --- | --- | --- |
| “Dependency đã là bản mới nên an toàn.” | Version không chứng minh cấu hình runtime hoặc quyền đúng | Kiểm tra danh tính thành phần, cấu hình hiệu lực và hành vi |
| “Có HTTPS trong URL.” | Chưa chứng minh chain, peer name hoặc hop cuối được xác minh | Test handshake qua đúng tuyến và chặn fallback |
| “Chỉ cho host có chứa tên đối tác.” | Host giả có thể chứa cùng chuỗi | Đối chiếu danh tính/đích đã đăng ký và egress |
| “Secret có trong biến môi trường nên không lộ.” | Có thể đi vào log, dump hoặc tiến trình con | Kiểm soát nguồn cấp, quyền, vòng đời và kênh chẩn đoán |
| “Retry ba lần ở mỗi lớp cho chắc.” | Có thể nhân số lần gửi và kéo dài operation | Một ngân sách xuyên lớp và kiểm tra actual attempt |
| “Timeout nghĩa là giao dịch thất bại.” | Đích có thể đã commit trước khi response mất | Idempotency ổn định và đối soát kết quả chưa rõ |
| “Đổi file là mọi replica đã áp dụng.” | Cache/client/pool cũ có thể vẫn hoạt động | Bằng chứng cấu hình hiệu lực và chuyển trạng thái nhất quán |
| “Rollback về bản từng chạy tốt.” | Quyền, endpoint hoặc trust cũ có thể đã bị thu hồi | Kiểm tra với policy hiện hành trước mở lưu lượng |
| “Log toàn bộ config để audit.” | Config có thể chứa secret hoặc metadata nhạy cảm | Audit trường cho phép, reference/revision và quyết định |
| “Có cảnh báo sau hai phút nên được chạy tạm cấu hình sai.” | Cảnh báo không thay điểm chặn | Chặn điều kiện đã biết là sai ngay tại thực thi |

## 15. Bài tập và checklist hoàn tất đặc tả

Một dịch vụ đơn hàng dùng SDK thanh toán. Endpoint lấy từ biến môi trường mà pipeline thử nghiệm cũng được phép sửa. Khi certificate lỗi, ứng dụng bật custom trust-all để duy trì dịch vụ. SDK retry ba lần, ứng dụng retry ba lần nữa; mỗi attempt tạo idempotency key mới. Token có quyền đọc và hoàn tiền dù ứng dụng chỉ cần tạo khoản thu. Khi restore, hệ thống dùng file cấu hình cũ nhưng không kiểm tra trạng thái thu hồi credential.

Hãy thực hiện:

1. Lập ít nhất sáu kịch bản đe dọa và chỉ ra tài sản/bất biến bị ảnh hưởng.
2. Viết hồ sơ dependency gồm endpoint, môi trường, principal, quyền, dữ liệu và nguồn cấu hình.
3. Đặc tả sáu yêu cầu có ID, owner, điều kiện đạt, hành vi khi không đạt và bằng chứng.
4. Thiết kế ngân sách deadline/retry xuyên lớp; giải thích cách xử lý khoản thu có kết quả chưa rõ.
5. Đề xuất kiểm thử cấu hình âm tính và một kiểm thử kết nối hợp lệ để tránh kết luận đạt do chặn tất cả.
6. Thiết kế rotation/rollback có xét token, pool, replica và trạng thái thu hồi hiện hành.
7. Chọn trường audit/metric đủ truy vết mà không ghi token hoặc payload thanh toán.

Trước khi chấp nhận đặc tả, kiểm tra:

- Dependency, owner, phạm vi dữ liệu, môi trường và principal đã rõ chưa?
- Thành phần được resolve/nạp và nguồn artifact có bằng chứng phù hợp chưa?
- Thứ tự override và nguồn được phép thay trường nhạy cảm đã được kiểm soát chưa?
- Schema, miền giá trị, property lạ và cấu hình hiệu lực có được kiểm chứng chưa?
- Đích cuối, TLS, audience và quyền có gắn với đúng tích hợp không?
- Secret/trust có quy tắc cấp, cache, rotation, thu hồi và xử lý phiên còn mở không?
- Deadline, pool, queue và retry có ngân sách xuyên các lớp và đúng phạm vi replica không?
- Tác dụng ngoài có idempotency/đối soát phù hợp với thao tác nghiệp vụ không?
- Hành vi suy giảm có tránh anonymous, plaintext hoặc bỏ xác minh không?
- Logging, drift, nâng cấp và rollback có owner, tiêu chí đạt và bằng chứng không?

Cấu hình dependency đạt yêu cầu khi các ràng buộc đã được phê duyệt có hiệu lực trong chính client và đường triển khai thực tế, đồng thời được giữ qua thay đổi, lỗi và phục hồi.
