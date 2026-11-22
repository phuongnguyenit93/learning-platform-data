# Chọn ma trận cho sản phẩm web hoặc di động có nhiều môi trường sử dụng

## 1. Vì sao sản phẩm web và di động cần ma trận kiểm thử?

Một sản phẩm web hoặc di động có thể được sử dụng trên nhiều thiết bị, hệ điều hành, trình duyệt, kích thước màn hình, phiên bản ứng dụng, loại mạng, ngôn ngữ, múi giờ, vai trò người dùng và cấu hình dịch vụ. Mỗi tổ hợp tạo ra một điều kiện sử dụng khác nhau. Một luồng hoạt động tốt trên máy tính dùng Chrome và mạng ổn định có thể gặp lỗi trên Safari, màn hình nhỏ, thiết bị cũ, mạng chập chờn hoặc khi ứng dụng chuyển từ nền trở lại.

Kiểm thử mọi tổ hợp là không khả thi. Nếu có 5 trình duyệt, 6 hệ điều hành/phiên bản, 8 kích thước thiết bị, 3 loại mạng, 4 ngôn ngữ và 3 vai trò người dùng, số tổ hợp lý thuyết đã lên tới 8.640 trước khi tính các yếu tố khác. Một ma trận đầy đủ như vậy thường vượt quá thời gian, thiết bị, môi trường và chi phí có sẵn.

**Ma trận kiểm thử (test matrix)** là cách mô tả có cấu trúc các chiều môi trường sử dụng, các giá trị của từng chiều, những tổ hợp được chọn, lý do lựa chọn và bằng chứng cần thu thập. Ma trận giúp nhóm biết:

- Người dùng thực tế sử dụng sản phẩm trong những điều kiện nào.
- Tổ hợp nào cần kiểm thử bắt buộc, tổ hợp nào có thể lấy mẫu.
- Rủi ro nào được bao phủ bởi từng tổ hợp.
- Test chạy trên thiết bị thật, simulator, emulator hay môi trường ảo nào.
- Khi nào cần chạy lại ma trận do thay đổi nền tảng hoặc dữ liệu sử dụng.
- Phần nào chưa được kiểm tra và rủi ro còn lại là gì.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, ma trận cho sản phẩm web hoặc di động phải phản ánh cả kiến trúc sản phẩm lẫn điều kiện sử dụng thực tế. Mục tiêu là chọn tập tổ hợp có giá trị phát hiện lỗi cao, có thể duy trì và truy vết được, thay vì tạo một danh sách thiết bị dài nhưng không biết vì sao cần kiểm tra.

## 2. Phân biệt các loại môi trường và chiều ma trận

Từ “môi trường” có thể chỉ nhiều khái niệm khác nhau. Trước khi lập ma trận, cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Deployment environment | Nơi phiên bản dịch vụ được triển khai | Development, staging, production |
| Client platform | Nền tảng chạy giao diện hoặc ứng dụng | Web browser, Android, iOS |
| Device profile | Đặc tính thiết bị | Điện thoại màn hình nhỏ, tablet, laptop |
| Runtime version | Phiên bản runtime hoặc nền tảng | Android 15, iOS 18, browser version |
| Network profile | Điều kiện kết nối | Wi-Fi ổn định, 4G yếu, latency cao, offline |
| User context | Vai trò, quyền và trạng thái người dùng | Guest, member, admin, tài khoản bị khóa |
| Data/locale context | Ngôn ngữ, múi giờ, định dạng và dữ liệu | Tiếng Việt, timezone UTC+7, số thập phân |
| Service/dependency version | Phiên bản backend hoặc dịch vụ tích hợp | API v2, payment sandbox, identity provider |

Một test có thể chạy trong staging nhưng cần nhiều client platform và network profile. Ngược lại, cùng một thiết bị có thể kết nối tới nhiều deployment environment. Không gộp các chiều này thành một trường “environment” duy nhất vì sẽ khó phân tích phạm vi và nguyên nhân lỗi.

### 2.1. Các chiều thường dùng cho sản phẩm web

- Trình duyệt và phiên bản: Chrome, Edge, Firefox, Safari.
- Browser engine: Chromium/Blink, WebKit, Gecko.
- Hệ điều hành: Windows, macOS, Linux, ChromeOS.
- Thiết bị: desktop, laptop, tablet, điện thoại.
- Viewport: chiều rộng/chiều cao, mật độ điểm ảnh và zoom.
- Input: chuột, bàn phím, touch, bút.
- Hỗ trợ: screen reader, keyboard-only, high contrast, reduced motion.
- Ngôn ngữ, locale, timezone và định dạng vùng.
- Network: latency, bandwidth, packet loss, offline.
- Trạng thái người dùng: guest, đăng nhập, quyền khác nhau, session hết hạn.
- Backend/API version, feature flag và cấu hình tenant.

### 2.2. Các chiều thường dùng cho sản phẩm di động

- Nền tảng và phiên bản: Android/iOS cùng phiên bản hỗ trợ.
- Thiết bị và nhà sản xuất: model, chipset, bộ nhớ, kích thước màn hình.
- Form factor: phone, tablet, foldable, thiết bị có màn hình ngoài.
- Kiến trúc CPU và khả năng phần cứng: camera, GPS, biometric, NFC.
- App version, build variant và trạng thái cài đặt/nâng cấp.
- Permission: granted, denied, denied permanently, limited access.
- Lifecycle: foreground, background, process killed, resume.
- Network: Wi-Fi, cellular, roaming, chuyển mạng, offline.
- Battery saver, low memory, storage pressure và nhiệt độ.
- Locale, timezone, font scale, orientation và accessibility settings.
- Push notification, deep link, app link và tích hợp hệ điều hành.

### 2.3. Các chiều dùng chung

Một số chiều ảnh hưởng cả web và mobile:

- Vai trò và quyền người dùng.
- Tenant, subscription, account state và feature flag.
- Backend/API version và trạng thái dependency.
- Dataset, dữ liệu biên và dữ liệu có lịch sử.
- Ngôn ngữ, timezone, định dạng ngày/tiền tệ.
- Network latency, timeout, retry và mất kết nối.
- Tích hợp thanh toán, identity, analytics hoặc notification.
- Điều kiện bảo mật, session, token và thiết bị đáng tin cậy.

Không phải chiều nào cũng cần nhân với tất cả chiều khác. Chỉ đưa một chiều vào ma trận nếu nó có khả năng làm thay đổi hành vi, độ tương thích hoặc rủi ro cần xác nhận.

## 3. Xác định mục tiêu và phạm vi hỗ trợ

### 3.1. Bắt đầu từ chính sách hỗ trợ sản phẩm

Ma trận phải dựa trên phạm vi nền tảng mà sản phẩm cam kết hỗ trợ. Thu thập:

- Danh sách browser/OS/device version được hỗ trợ.
- Phiên bản tối thiểu và phiên bản khuyến nghị.
- Thời gian hỗ trợ sau khi nền tảng phát hành phiên bản mới.
- Thiết bị hoặc browser đã ngừng hỗ trợ.
- Yêu cầu hợp đồng, pháp lý, accessibility và bảo mật.
- Hành trình quan trọng và nhóm người dùng mục tiêu.

Không suy ra phạm vi hỗ trợ chỉ từ các thiết bị hiện có trong phòng lab. Một thiết bị chưa được nhóm mua có thể chiếm tỷ trọng lớn trong người dùng; ngược lại, một thiết bị có trong lab chưa chắc còn nằm trong chính sách hỗ trợ.

### 3.2. Phân biệt supported, compatible và best-effort

Có thể phân loại:

- **Supported:** nền tảng được cam kết hỗ trợ và cần có bằng chứng kiểm thử theo policy.
- **Compatible:** sản phẩm dự kiến hoạt động nhưng có thể dùng tập kiểm tra giới hạn hoặc theo mức ưu tiên thấp hơn.
- **Best-effort:** không cam kết đầy đủ; vấn đề được xử lý theo năng lực và tác động.
- **Unsupported:** không nằm trong phạm vi hỗ trợ; cần thông báo rõ và không dùng kết quả test ở nền tảng khác để tuyên bố tương thích.

Các nhãn phải được công bố nhất quán trong tài liệu sản phẩm và support policy. Không dùng “best-effort” để né yêu cầu bảo mật, an toàn hoặc nghĩa vụ hợp đồng.

### 3.3. Xác định hành trình và rủi ro trọng yếu

Chọn hành trình cần bảo vệ, ví dụ:

- Đăng ký, đăng nhập, xác thực nhiều yếu tố và khôi phục tài khoản.
- Tìm kiếm, xem nội dung và lọc dữ liệu.
- Tạo đơn, thanh toán, hoàn tiền hoặc đặt lịch.
- Tải lên/tải xuống tệp và đồng bộ dữ liệu.
- Nhận push notification, email hoặc deep link.
- Thực hiện thao tác có quyền cao hoặc truy cập dữ liệu nhạy cảm.
- Khôi phục sau mất mạng, app bị đóng hoặc session hết hạn.

Một ma trận chỉ có danh sách thiết bị nhưng không liên kết với hành trình và rủi ro sẽ khó ưu tiên. Ví dụ, biometric cần kiểm tra trên thiết bị có phần cứng phù hợp; camera upload cần kiểm tra permission, định dạng và lifecycle; thanh toán cần kiểm tra cả client lẫn trạng thái backend.

## 4. Xây dựng các chiều và giá trị của ma trận

### 4.1. Tạo danh sách chiều có kiểm soát

Với mỗi chiều, ghi:

- Tên và định nghĩa.
- Các giá trị được hỗ trợ.
- Nguồn dữ liệu hoặc chính sách xác định giá trị.
- Giá trị bắt buộc, phổ biến, biên và ít gặp.
- Quan hệ hoặc ràng buộc với chiều khác.
- Owner cập nhật khi nền tảng thay đổi.

Ví dụ, chiều “browser” không chỉ là tên Chrome mà cần ghi major version, engine và hệ điều hành chạy browser. Chiều “màn hình” nên dùng viewport và pixel density khi chúng ảnh hưởng layout, thay vì chỉ ghi tên model thiết bị.

### 4.2. Tránh tạo giá trị trùng nghĩa

Không tạo các mục như “mobile”, “phone”, “small screen” trong cùng một chiều nếu chúng mô tả các khái niệm khác nhau. Hãy tách form factor, viewport và thiết bị. Chuẩn hóa cách ghi version để có thể lọc và so sánh.

### 4.3. Ghi các ràng buộc thực tế

Không phải tổ hợp nào cũng hợp lệ:

- Safari chỉ chạy trên các nền tảng tương ứng.
- Một API phần cứng chỉ có trên một số thiết bị.
- Một permission state có thể khác giữa Android và iOS.
- Một app build có thể yêu cầu phiên bản OS tối thiểu.
- Một browser version có thể không hỗ trợ một API mới.
- Một số tính năng chỉ bật cho tenant hoặc subscription nhất định.

Ghi constraint để không lãng phí lượt chạy trên tổ hợp không thể tồn tại. Đồng thời, constraint cần được xác minh khi nền tảng hoặc chính sách thay đổi.

## 5. Chọn tổ hợp kiểm thử theo rủi ro

### 5.1. Không kiểm thử Cartesian product một cách máy móc

Nếu nhân mọi giá trị của mọi chiều, số tổ hợp tăng rất nhanh. Nhiều tổ hợp không hợp lệ hoặc không mang thêm bằng chứng. Cần chọn tập tổ hợp dựa trên:

- Tỷ lệ người dùng hoặc traffic thực tế.
- Hành trình và chức năng quan trọng.
- Severity nếu lỗi xảy ra.
- Khả năng thay đổi của code và dependency.
- Lịch sử defect theo browser/device/version.
- Khác biệt kỹ thuật giữa các platform.
- Yêu cầu bảo mật, accessibility và tuân thủ.
- Chi phí và khả năng thực thi.

### 5.2. Nhóm mức ưu tiên

Một mô hình thực tế có thể chia:

| Mức | Tiêu chí chọn | Cách kiểm thử |
|---|---|---|
| P0 – Bắt buộc | Nền tảng chiếm phần lớn người dùng, hành trình cốt lõi, yêu cầu hợp đồng hoặc rủi ro cao | Chạy đầy đủ smoke và regression trọng yếu trên mỗi release cần thiết |
| P1 – Quan trọng | Nền tảng được hỗ trợ, nhóm người dùng đáng kể hoặc có khác biệt runtime đáng kể | Chạy regression chọn lọc và kiểm tra các hành trình liên quan |
| P2 – Mở rộng | Nền tảng ít phổ biến hơn nhưng vẫn được hỗ trợ hoặc có rủi ro đặc thù | Chạy theo lịch, trước release lớn hoặc khi thay đổi liên quan |
| P3 – Thăm dò | Nền tảng mới, phiên bản preview hoặc cấu hình chưa đủ dữ liệu | Exploratory/compatibility check, ghi rõ trạng thái hỗ trợ |

P0–P3 là ví dụ. Tổ chức cần đặt tiêu chí cụ thể theo dữ liệu người dùng và policy. Một nền tảng ít người dùng vẫn có thể P0 nếu phục vụ nhóm có yêu cầu pháp lý hoặc nghiệp vụ đặc biệt.

### 5.3. Bao phủ các giá trị biên

Ngoài tổ hợp phổ biến, cần chọn các giá trị biên:

- OS/browser ở phiên bản tối thiểu được hỗ trợ.
- Màn hình nhỏ nhất và lớn nhất trong phạm vi.
- Font scale lớn, zoom cao và orientation thay đổi.
- Network chậm, mất gói, timeout và offline.
- Thiết bị bộ nhớ thấp hoặc storage gần đầy.
- Permission bị từ chối hoặc chỉ cấp một phần.
- Session hết hạn, token refresh và clock lệch.
- Locale có định dạng ngày, số và tiền tệ khác biệt.

Lỗi thường xuất hiện ở ranh giới phiên bản hoặc điều kiện tài nguyên, vì vậy không nên chỉ chọn cấu hình mới nhất và mạnh nhất.

## 6. Kỹ thuật giảm số tổ hợp

### 6.1. Pairwise testing

Pairwise testing chọn một tập tổ hợp sao cho mọi cặp giá trị của hai chiều được bao phủ ít nhất một lần, trong phạm vi các ràng buộc đã khai báo. Cách tiếp cận này hữu ích vì nhiều lỗi tương tác xuất hiện do hai yếu tố kết hợp, ví dụ browser và OS, permission và lifecycle hoặc network và app version.

Pairwise không bảo đảm phát hiện mọi lỗi. Lỗi cần tương tác ba hoặc nhiều chiều, lỗi đặc thù thiết bị hoặc yêu cầu bao phủ một tổ hợp bắt buộc vẫn cần test riêng.

### 6.2. T-way testing

Với khu vực có rủi ro cao, có thể chọn 3-way hoặc mức tương tác lớn hơn cho một tập chiều cụ thể. Ví dụ, một lỗi có thể chỉ xảy ra khi iOS version mới, app resume sau background và mạng chuyển từ Wi-Fi sang cellular. Pairwise có thể không chứa đúng tổ hợp ba chiều này.

Không cần áp dụng t-way cao cho toàn bộ ma trận. Dùng nó có mục tiêu ở những rủi ro có căn cứ.

### 6.3. Equivalence partitioning và representative selection

Chia các giá trị có hành vi tương đương thành nhóm rồi chọn đại diện. Ví dụ, một số viewport có thể cùng kích hoạt breakpoint layout; một nhóm browser version có cùng engine và mức hỗ trợ API. Đại diện cần được chọn theo khác biệt kỹ thuật và dữ liệu sử dụng.

Không gom các phiên bản chỉ vì tên gần nhau. Nếu có thay đổi engine, permission model hoặc rendering behavior, cần cân nhắc tách nhóm.

### 6.4. Risk-based combination

Ưu tiên các tổ hợp có:

- Hành trình quan trọng và người dùng phơi nhiễm cao.
- Khác biệt kỹ thuật lớn.
- Lịch sử defect hoặc incident.
- Tương tác giữa nhiều chiều.
- Khả năng phát hiện lỗi thấp trong vận hành.
- Hậu quả cao nếu lỗi lọt.

### 6.5. Giữ lại các tổ hợp bắt buộc

Pairwise hoặc thuật toán sinh ma trận không được loại các tổ hợp bắt buộc do policy, hợp đồng, security hoặc support commitment. Có thể thêm các tổ hợp này vào tập pairwise như fixed rows rồi sinh phần còn lại quanh chúng.

## 7. Ví dụ ma trận cho sản phẩm web

Giả sử sản phẩm web hỗ trợ người dùng desktop và mobile browser. Các chiều được chọn:

| Chiều | Giá trị ví dụ | Lý do |
|---|---|---|
| Browser | Chrome, Edge, Firefox, Safari | Khác biệt engine và hành vi |
| OS | Windows, macOS, Android, iOS | Runtime và API nền tảng |
| Viewport | Desktop wide, laptop, tablet, phone narrow | Responsive layout |
| Input | Mouse/keyboard, touch, keyboard-only | Tương tác và accessibility |
| Locale | vi-VN, en-US, ar-SA | Nội dung, định dạng và RTL |
| Network | Stable, high latency, intermittent | Timeout và tải nội dung |
| User role | Guest, member, admin | Quyền và luồng chức năng |

### 7.1. Tập tổ hợp đại diện minh họa

| Case | Browser/OS | Viewport/input | Locale/network | Role | Trọng tâm |
|---|---|---|---|---|---|
| WEB-01 | Chrome/Windows | Desktop wide, mouse+keyboard | vi-VN/stable | Member | Luồng chính và baseline |
| WEB-02 | Edge/Windows | Laptop, keyboard-only | en-US/stable | Admin | Quyền và accessibility |
| WEB-03 | Firefox/Windows | Laptop, mouse+keyboard | vi-VN/high latency | Guest | Rendering và tải chậm |
| WEB-04 | Safari/macOS | Desktop wide, keyboard | en-US/stable | Member | WebKit compatibility |
| WEB-05 | Safari/iOS | Phone narrow, touch | vi-VN/intermittent | Member | Responsive và session |
| WEB-06 | Chrome/Android | Phone narrow, touch | en-US/high latency | Guest | Mobile browser và network |
| WEB-07 | Safari/iOS | Tablet, touch + keyboard | ar-SA/stable | Admin | RTL, quyền và layout |

Đây là tập đại diện để minh họa cách ghi ma trận, không phải danh sách đủ cho mọi sản phẩm. Tập thực tế cần được sinh hoặc review theo browser support policy, analytics và rủi ro. Các tổ hợp bắt buộc như browser tối thiểu hoặc accessibility target cần được bổ sung dù pairwise không tự chọn.

### 7.2. Kiểm tra responsive và accessibility

Với web, không nên chỉ kiểm tra một viewport cho mỗi thiết bị. Cần kiểm tra breakpoint, zoom, font scaling, reflow, keyboard navigation, focus order, contrast và screen reader theo mức hỗ trợ cam kết.

Một số lỗi chỉ xuất hiện ở chiều rộng nằm ngay trước/sau breakpoint. Vì vậy, thêm các viewport sát ngưỡng CSS quan trọng, không chỉ dùng preset phổ biến như desktop/tablet/phone.

## 8. Ví dụ ma trận cho ứng dụng di động

Giả sử một ứng dụng mobile hỗ trợ Android và iOS. Các chiều quan trọng:

| Chiều | Giá trị ví dụ | Rủi ro cần xem xét |
|---|---|---|
| OS/version | Android tối thiểu, phiên bản phổ biến, mới nhất; iOS tối thiểu, phổ biến, mới nhất | API, permission và lifecycle thay đổi |
| Device tier | Low, mid, high | Memory, CPU và hiệu năng |
| Form factor | Phone, tablet, foldable | Layout và state continuity |
| App state | Fresh install, upgrade, foreground, background, killed | Migration, session và resume |
| Permission | Granted, denied, limited, revoked | Quyền truy cập phần cứng/dữ liệu |
| Network | Wi-Fi, cellular, switching, offline | Retry, cache và đồng bộ |
| Hardware | Camera, GPS, biometric, push | Tích hợp phần cứng |
| Locale | vi-VN, en-US, timezone khác nhau | Định dạng và nội dung |

### 8.1. Tập tổ hợp đại diện minh họa

| Case | Platform/device | App state/permission | Network | Trọng tâm |
|---|---|---|---|---|
| MOB-01 | Android phổ biến, mid-tier phone | Fresh install, permission granted | Wi-Fi | Onboarding và luồng chính |
| MOB-02 | Android tối thiểu, low-tier phone | Upgrade, permission denied | Cellular chậm | Tương thích và tài nguyên |
| MOB-03 | Android mới, foldable | Background/resume, permission limited | Network switching | Lifecycle và layout |
| MOB-04 | iOS tối thiểu, phone | Fresh install, notification denied | Wi-Fi | Hỗ trợ OS và notification |
| MOB-05 | iOS phổ biến, phone | App killed rồi resume, biometric enabled | Intermittent | Session và biometric |
| MOB-06 | iOS mới, tablet | Upgrade, camera permission revoked | Offline rồi online | Migration và đồng bộ |

Ma trận thực tế cần dùng model/version cụ thể theo support policy. “Android phổ biến” hoặc “iOS mới” chỉ là nhãn mô tả trong ví dụ; registry vận hành cần ghi version, model, build và cách tái tạo.

### 8.2. Kiểm tra lifecycle

Ứng dụng di động cần kiểm tra các chuyển trạng thái:

- App chuyển background khi đang nhập dữ liệu.
- OS thu hồi process vì thiếu bộ nhớ.
- Người dùng quay lại sau thời gian dài.
- Token hết hạn khi app ở nền.
- Notification mở app qua deep link.
- Mạng đổi từ Wi-Fi sang cellular trong request.
- Permission bị thu hồi trong Settings.
- Thiết bị khởi động lại hoặc ứng dụng được nâng cấp.

Các tình huống này thường khó bao phủ bằng một lần chạy smoke test đơn giản. Cần xác định kịch bản theo rủi ro và sử dụng automation hoặc thiết bị thật phù hợp.

## 9. Chọn thiết bị thật, emulator, simulator và browser automation

### 9.1. Thiết bị thật

Thiết bị thật phù hợp để xác nhận:

- Phần cứng và driver thực tế.
- Camera, GPS, biometric, NFC, push và sensor.
- Hiệu năng, pin, nhiệt độ và bộ nhớ.
- Hành vi mạng di động và chuyển mạng.
- Khác biệt OEM hoặc cấu hình hệ điều hành.

Hạn chế gồm chi phí, số lượng thiết bị, khả năng tự động hóa và thời gian bảo trì lab.

### 9.2. Emulator và simulator

Emulator/simulator hữu ích để:

- Bao phủ nhiều OS version và cấu hình.
- Chạy regression tự động với khả năng tái lập tốt.
- Kiểm tra viewport, locale, permission và lifecycle ở mức mô phỏng.
- Mở rộng song song với chi phí thấp hơn thiết bị thật.

Chúng không mô phỏng hoàn hảo phần cứng, modem, driver, hiệu năng hoặc hành vi OEM. Không dùng kết quả simulator để tuyên bố đã xác nhận một tính năng phụ thuộc phần cứng nếu chưa có bằng chứng trên thiết bị thật.

### 9.3. Browser automation

Browser automation phù hợp cho regression web trên browser/version đã chọn. Cần kiểm tra browser thực thi, headless/headed mode, viewport, font, locale, permission và cách cài extension. Một test chạy trên Chromium không tự động đại diện cho mọi browser dùng engine khác.

### 9.4. Chiến lược kết hợp

Một cách phân bổ thường dùng:

- Automation trên emulator/simulator cho nhiều tổ hợp và hồi quy thường xuyên.
- Thiết bị thật cho P0, phần cứng, network và rủi ro đặc thù.
- Exploratory testing trên thiết bị mới hoặc tổ hợp ít dữ liệu.
- Browser automation cho regression web.
- Kiểm tra thủ công có cấu trúc cho accessibility hoặc hành vi khó tự động hóa.

Ghi rõ loại môi trường đã dùng trong report để người đọc hiểu giới hạn bằng chứng.

## 10. Phân bổ ma trận vào các giai đoạn kiểm thử

Không cần chạy toàn bộ ma trận ở mọi pull request. Có thể chia tầng:

| Giai đoạn | Phạm vi ma trận | Mục tiêu |
|---|---|---|
| Pull request | Một vài cấu hình đại diện ổn định, test nhanh | Phản hồi sớm cho thay đổi |
| Nightly/integration | Pairwise hoặc tập rộng hơn trên browser/device phổ biến | Phát hiện tương tác và regression |
| Pre-release | P0, P1, tổ hợp bắt buộc, giá trị biên và test chuyên biệt | Bằng chứng readiness |
| Release candidate | Tổ hợp gắn với thay đổi và platform trọng yếu | Xác nhận đúng artifact |
| Production canary | Synthetic/smoke an toàn trên cohort nhỏ | Kiểm tra cấu hình thật và rollout |
| Exploratory/periodic | Thiết bị mới, platform ít gặp, preview version | Khám phá rủi ro mới |

Quy tắc phải bảo đảm mọi tổ hợp bắt buộc hoàn tất trước gate tương ứng. Việc chuyển một test từ PR sang nightly không có nghĩa có thể bỏ test trước release.

## 11. Thiết kế dữ liệu và điều kiện cho từng tổ hợp

Một tổ hợp platform chỉ hữu ích khi dữ liệu và trạng thái đầu vào phù hợp. Với mỗi case, ghi:

- Account/role và permission.
- Dataset, locale và timezone.
- Feature flag và tenant configuration.
- Backend/API version.
- App/browser build và cache state.
- Network profile và timeout.
- Trạng thái trước khi chạy.
- Expected result và cleanup.

Ví dụ, test đổi timezone cần dữ liệu có mốc thời gian gần nửa đêm hoặc thời điểm chuyển ngày. Test locale RTL cần nội dung đủ dài và component có căn chỉnh. Test offline cần xác định dữ liệu nào được phép đọc, ghi và đồng bộ lại.

Không tái sử dụng cùng một tài khoản hoặc dữ liệu mutable giữa nhiều test song song nếu có thể gây race condition. Dùng dữ liệu cô lập hoặc quy tắc cleanup rõ ràng.

## 12. Quản lý phiên bản và cập nhật ma trận

### 12.1. Theo dõi thay đổi nền tảng

Ma trận cần được review khi:

- Browser hoặc OS phát hành phiên bản mới.
- Nhà sản xuất thay đổi permission/lifecycle/API.
- Sản phẩm đổi framework hoặc rendering engine.
- Support policy thêm/bỏ nền tảng.
- Analytics cho thấy cơ cấu thiết bị thay đổi.
- Incident hoặc defect mới xuất hiện trên một tổ hợp.
- Thay đổi phần cứng, network hoặc dependency.

### 12.2. Chính sách version window

Có thể quy định hỗ trợ phiên bản hiện tại và một số phiên bản trước, nhưng phải phù hợp dữ liệu người dùng, vòng đời OS/browser và cam kết sản phẩm. Ghi rõ:

- Phiên bản tối thiểu được hỗ trợ.
- Phiên bản mới nhất được kiểm thử.
- Phiên bản nằm trong best-effort.
- Ngày ngừng hỗ trợ hoặc thời gian chuyển tiếp.
- Điều kiện nâng mức ưu tiên khi người dùng còn sử dụng phiên bản cũ.

Không cập nhật ma trận theo cảm tính hoặc chỉ theo phiên bản mới nhất của nhà cung cấp. Cần đánh giá người dùng bị ảnh hưởng và rủi ro tương thích.

### 12.3. Deprecate tổ hợp cũ

Trước khi bỏ một tổ hợp, kiểm tra analytics, support ticket, hợp đồng, người dùng đặc biệt và dependency. Thông báo thay đổi theo quy trình sản phẩm. Giữ lịch sử ma trận để giải thích tại sao một phiên bản được hoặc không được hỗ trợ ở release cũ.

### 12.4. Quản lý ma trận như tài sản có owner

Chỉ định owner cho:

- Support policy và danh sách platform.
- Browser/device inventory.
- Test selection và pairwise generation.
- Device lab, emulator/simulator và automation.
- Dữ liệu, account và network profile.
- Báo cáo kết quả và risk acceptance.

Khi owner thay đổi, cần bàn giao cách cập nhật version, thiết bị và nguồn dữ liệu sử dụng.

## 13. Theo dõi hiệu quả của ma trận

Không đánh giá ma trận chỉ bằng số lượng tổ hợp hoặc thiết bị đã chạy. Các chỉ số có thể gồm:

| Chỉ số | Ý nghĩa | Giới hạn cần lưu ý |
|---|---|---|
| Supported platform coverage | Tỷ lệ nền tảng hỗ trợ có bằng chứng trong kỳ | Không phản ánh độ sâu của test |
| Risk coverage | Tỷ lệ rủi ro quan trọng được liên kết với tổ hợp/test | Phụ thuộc chất lượng risk mapping |
| Pairwise coverage | Mức bao phủ các cặp giá trị trong phạm vi | Không chứng minh bao phủ tương tác 3-way trở lên |
| Real-device coverage | Tỷ lệ nhóm thiết bị trọng yếu được kiểm tra trên phần cứng thật | Không đồng nghĩa mọi model đã được xác nhận |
| Defect distribution | Lỗi theo browser, OS, device, locale hoặc network | Phụ thuộc cách gắn nhãn và báo cáo |
| Matrix execution time | Thời gian chạy các tổ hợp | Cần đọc cùng số test và giá trị bằng chứng |
| Flaky rate by platform | Độ ổn định theo nền tảng | Phải phân biệt test flaky và môi trường lỗi |
| User exposure | Tỷ lệ người dùng/traffic nằm trong các tổ hợp đã kiểm tra | Dữ liệu analytics có thể thiếu hoặc thiên lệch |
| Unsupported usage | Mức sử dụng nền tảng ngoài phạm vi hỗ trợ | Không tự động là lý do mở rộng support |

Các chỉ số cần có định nghĩa, mẫu số, cửa sổ thời gian và nguồn dữ liệu. Pairwise coverage cao không chứng minh sản phẩm không có lỗi; nó chỉ cho biết các cặp giá trị trong mô hình đã được bao phủ theo quy tắc sinh.

## 14. Ví dụ quy trình chọn ma trận

Giả sử một ứng dụng đặt lịch có web và mobile, hỗ trợ nhiều vai trò và gửi thông báo.

**Bước 1 – Xác định hành trình:** đăng nhập, tìm lịch, đặt lịch, hủy lịch và nhận notification.

**Bước 2 – Xác định chiều:** browser/OS, device tier, viewport, app version, permission, network, locale, role và backend version.

**Bước 3 – Thu thập dữ liệu sử dụng:** analytics cho thấy phần lớn người dùng web dùng Chrome/Edge trên desktop, người dùng mobile chia giữa Android và iOS; một nhóm dùng thiết bị cấu hình thấp.

**Bước 4 – Xác định rủi ro:** đặt lịch trùng, timezone sai, notification không đến, session hết hạn và layout vỡ trên màn hình nhỏ.

**Bước 5 – Chọn P0:** browser phổ biến, OS tối thiểu và mới nhất, Android/iOS phổ biến, luồng đặt/hủy lịch, timezone chính, permission notification và network ổn định.

**Bước 6 – Chọn tổ hợp bổ sung:** pairwise giữa platform, locale, network và role; thêm test riêng cho timezone, notification permission và app resume vì các rủi ro này có tương tác đặc thù.

**Bước 7 – Chọn phương tiện:** browser automation cho web, emulator cho regression mobile rộng, thiết bị thật cho notification, lifecycle và thiết bị cấu hình thấp.

**Bước 8 – Phân bổ thời điểm:** smoke trên P0 ở PR/release candidate; pairwise nightly; full P0/P1 trước release lớn; canary và monitoring sau deploy.

**Bước 9 – Review:** sau incident hoặc thay đổi OS/browser, cập nhật risk register, ma trận và test selection.

## 15. Mẫu đặc tả ma trận

~~~yaml
test_matrix:
  product: "booking-web-and-mobile"
  reviewed_at: "2026-11-16"
  owner: "quality-engineering"

support_policy:
  web:
    browsers:
      - name: chrome
        versions: "current-and-previous-supported"
        priority: P0
      - name: safari
        versions: "supported-major-versions"
        priority: P0
      - name: firefox
        versions: "supported-major-versions"
        priority: P1
  mobile:
    android:
      minimum_version: "defined-by-product-policy"
      priority: P0
    ios:
      minimum_version: "defined-by-product-policy"
      priority: P0

dimensions:
  - id: platform
    values: [web, android, ios]
  - id: device_tier
    values: [low, mid, high]
  - id: viewport
    values: [phone_narrow, tablet, desktop]
  - id: network
    values: [stable, high_latency, intermittent, offline]
  - id: locale
    values: [vi_VN, en_US, ar_SA]
  - id: user_role
    values: [guest, member, admin]
  - id: app_state
    values: [fresh_install, foreground, background_resume, upgraded]

constraints:
  - "Safari requires a supported Apple platform"
  - "app_state applies only to native mobile clients"
  - "hardware-dependent tests require a real device"

selection:
  strategy: "risk-based-plus-pairwise"
  mandatory:
    - "minimum-supported-platform"
    - "critical-booking-journey"
    - "timezone-boundary"
  additional:
    - "permission-denied"
    - "network-switch"
    - "background-resume"

execution:
  pull_request: "small-stable-p0-subset"
  nightly: "pairwise-regression"
  pre_release: "all-mandatory-p0-and-selected-p1"
  production_canary: "safe-synthetic-checks"

evidence:
  required:
    - platform_version
    - device_or_browser
    - app_or_build_version
    - environment_id
    - network_profile
    - locale
    - test_run_id
    - result_and_artifact
~~~

Đây là mẫu cấu trúc. Danh sách version, tổ hợp, priority và lịch chạy phải được thay bằng support policy và dữ liệu của sản phẩm. Không dùng các nhãn ví dụ như “current” thay cho version cụ thể trong báo cáo thực thi.

## 16. Những sai lầm thường gặp

- **Nhân tất cả chiều thành Cartesian product:** tạo số tổ hợp lớn nhưng nhiều tổ hợp không hợp lệ hoặc ít giá trị.
- **Chọn chỉ thiết bị mới nhất:** bỏ sót phiên bản tối thiểu, thiết bị cũ và điều kiện tài nguyên thấp.
- **Dựa vào thị phần tổng thể:** bỏ qua nhóm người dùng nhỏ nhưng có rủi ro hoặc nghĩa vụ đặc biệt.
- **Coi pairwise là đủ:** bỏ sót lỗi cần tương tác ba chiều hoặc điều kiện đặc thù.
- **Không ghi constraint:** sinh test cho tổ hợp không thể xảy ra hoặc bỏ qua tổ hợp hợp lệ.
- **Dùng emulator thay cho mọi thiết bị thật:** không phát hiện được lỗi phần cứng, driver, modem hoặc OEM.
- **Chỉ ghi tên model:** không biết OS version, build, cấu hình và điều kiện thực thi.
- **Gộp deployment environment với client platform:** khó phân tích lỗi đến từ server hay client.
- **Không kiểm tra viewport sát breakpoint:** bỏ sót lỗi responsive.
- **Bỏ qua permission và lifecycle trên mobile:** không kiểm tra trạng thái thực tế của ứng dụng.
- **Không đưa locale/timezone vào ma trận:** lỗi ngày, tiền tệ, RTL hoặc chuyển ngày bị bỏ qua.
- **Không liên kết tổ hợp với risk:** ma trận trở thành danh sách thiết bị không có mục tiêu.
- **Không cập nhật khi support policy đổi:** test trên nền tảng không còn dùng hoặc thiếu nền tảng mới.
- **Không lưu evidence theo tổ hợp:** không thể tái hiện lỗi và xác định phạm vi đã kiểm tra.
- **Chạy toàn bộ ma trận ở mọi commit:** feedback chậm và tốn tài nguyên.

## 17. Checklist lựa chọn và duy trì ma trận

### Trước khi lập ma trận

- [ ] Support policy và phiên bản tối thiểu/tối đa được xác định.
- [ ] Hành trình nghiệp vụ và rủi ro trọng yếu được liệt kê.
- [ ] Deployment environment được phân biệt với client platform và device profile.
- [ ] Các chiều có ảnh hưởng thực sự đến hành vi được chọn.
- [ ] Giá trị, version, constraint và owner của từng chiều được ghi.
- [ ] Analytics, support data và lịch sử defect được dùng để xác định mức phổ biến.

### Khi chọn tổ hợp

- [ ] Tổ hợp P0/P1 và tổ hợp bắt buộc được xác định.
- [ ] Giá trị biên và phiên bản tối thiểu được bao phủ.
- [ ] Pairwise/t-way được dùng phù hợp với rủi ro và constraint.
- [ ] Các tương tác đặc thù có test riêng khi cần.
- [ ] Có phân biệt tổ hợp chạy trên thiết bị thật và môi trường mô phỏng.
- [ ] Mỗi tổ hợp được liên kết với hành trình, risk hoặc mục tiêu kiểm thử.

### Khi thực thi

- [ ] Browser/OS/device/app version và build được ghi chính xác.
- [ ] Viewport, locale, timezone, permission và network profile được xác định.
- [ ] Dữ liệu, tài khoản, feature flag và backend version phù hợp.
- [ ] Expected result, timeout, cleanup và artifact được định nghĩa.
- [ ] Test bắt buộc hoàn tất trước gate tương ứng.
- [ ] Blocked, skipped và not run được ghi riêng, không coi là pass.

### Khi duy trì

- [ ] Ma trận được review khi OS/browser/device hoặc support policy thay đổi.
- [ ] Defect và incident được phân tích theo platform/dimension.
- [ ] Tổ hợp cũ chỉ được retire sau impact analysis và review consumer.
- [ ] Pairwise coverage, risk coverage và execution cost được theo dõi.
- [ ] Registry có owner, version và lịch review.
- [ ] Khoảng trống và rủi ro còn lại được công khai.

## Kết luận

Ma trận kiểm thử cho sản phẩm web hoặc di động giúp lựa chọn có căn cứ giữa nhiều browser, OS, thiết bị, viewport, network, locale, quyền và trạng thái ứng dụng. Bắt đầu từ support policy, hành trình và rủi ro; định nghĩa các chiều cùng constraint; chọn tổ hợp theo mức sử dụng, giá trị biên và mức rủi ro; dùng pairwise hoặc t-way để giảm số lượt chạy nhưng vẫn giữ các tổ hợp bắt buộc. Kết hợp browser automation, emulator/simulator, thiết bị thật và exploratory testing theo đúng giới hạn của từng phương tiện. Khi mỗi tổ hợp có owner, mục tiêu, bằng chứng và chu kỳ review, ma trận sẽ giúp kiểm thử hiệu quả mà vẫn minh bạch về phạm vi chưa được xác nhận.
