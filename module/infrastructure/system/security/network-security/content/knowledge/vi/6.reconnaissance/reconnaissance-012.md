# Phân biệt kiểm tra được phép với hành vi tấn công

Trong giai đoạn **reconnaissance** (trinh sát, tìm hiểu hệ thống), người kiểm thử bảo mật và người có ý định xâm nhập có thể sử dụng những kỹ thuật quan sát tương tự: tra cứu thông tin công khai, xác định tài sản Internet, phân tích phản hồi dịch vụ hoặc tìm dấu hiệu cấu hình sai. Nhìn vào một gói tin hay tên công cụ thường **không đủ** để kết luận đó là hoạt động kiểm thử hợp lệ hay tấn công.

Điểm quyết định là **quyền thực hiện, phạm vi, mục đích được thỏa thuận, cách kiểm soát tác động và hành vi thực tế**. Một cuộc kiểm thử có giấy chấp thuận vẫn có thể vượt quyền khi nhắm sai tài sản, vượt khung thời gian hoặc thực hiện kỹ thuật bị cấm. Ngược lại, một cảnh báo IDS/IPS về quét cổng có thể phản ánh bài kiểm thử đã được phê duyệt. Đội bảo vệ cần kiểm tra bằng chứng thay vì suy đoán ý định từ lưu lượng đơn lẻ.

Trong module **SECURITY_NETWORK_SECURITY**, khả năng phân biệt này giúp lập kế hoạch đánh giá bảo mật mạng, thực thi phân đoạn/firewall/VPN, hiểu cảnh báo IDS/IPS, bảo vệ DNS và mạng không dây, kiểm soát quyền trên đám mây, đồng thời thiết kế quy trình giám sát và ứng phó phù hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích thế nào là kiểm tra bảo mật được phép và thế nào là hành vi vượt phạm vi hoặc không được cho phép.
- Xác định các yếu tố quan trọng trong văn bản ủy quyền, **scope** (phạm vi) và **Rules of Engagement** (quy tắc thực hiện).
- Phân biệt hành vi thụ động với chủ động, và hiểu vì sao mức tác động kỹ thuật không quyết định tính hợp lệ.
- Phân tích các tình huống liên quan đến quét dịch vụ, kiểm thử xác thực, DNS, VPN, ứng dụng web, mạng không dây và môi trường cloud.
- Đánh giá tín hiệu từ firewall, IDS/IPS, VPN, nhật ký ứng dụng và các hệ thống giám sát để xác minh hoạt động kiểm thử.
- Mô tả cách dừng kiểm thử, bảo toàn bằng chứng, báo cáo và xử lý phát hiện ngoài phạm vi.

## 2. Hai khái niệm cần phân biệt

### 2.1. Kiểm tra bảo mật được phép

**Kiểm tra bảo mật được phép** là hoạt động đánh giá hoặc xác minh an toàn thông tin được **chủ thể có thẩm quyền đối với tài sản** chấp thuận, trong một phạm vi và điều kiện đã xác định. Tùy trường hợp, hoạt động này có thể là kiểm kê bề mặt tấn công, vulnerability assessment, penetration test, kiểm thử cấu hình, đánh giá phân đoạn mạng hoặc diễn tập phối hợp giữa đội tấn công mô phỏng và đội phòng thủ.

Một hoạt động chỉ được xem là **nằm trong sự cho phép** khi thỏa mãn đồng thời các điều kiện cần thiết:

1. **Chủ thể chấp thuận có thẩm quyền:** người hoặc đơn vị thực sự có quyền cho phép kiểm thử những tài nguyên liên quan.
2. **Tài sản thuộc phạm vi:** tên miền, IP, subnet, ứng dụng, thiết bị, tài khoản cloud hoặc vị trí vật lý phải được xác định đủ rõ.
3. **Phương pháp nằm trong phạm vi:** những bước chủ động như quét cổng, kiểm thử xác thực, đánh giá cấu hình hoặc thực hiện khai thác có kiểm soát phải được chấp thuận phù hợp.
4. **Thời gian và điều kiện phù hợp:** tôn trọng cửa sổ kiểm thử, giới hạn tải, dữ liệu được sử dụng, điều kiện dừng và kênh liên lạc.
5. **Mục tiêu và hành vi nhất quán:** kiểm chứng rủi ro và đưa ra khuyến nghị trong giới hạn đã đồng ý, không tự mở rộng sang hệ thống hoặc dữ liệu khác.

Ví dụ, đội bảo mật được phép kiểm tra phân đoạn giữa **DMZ** và **application zone** bằng các luồng kết nối đã định nghĩa. Hoạt động sẽ không tự động bao gồm quyền đăng nhập tài khoản quản trị thiết bị mạng, truy cập dữ liệu khách hàng hoặc mở rộng sang dịch vụ của đối tác.

### 2.2. Hành vi tấn công hoặc vượt quá sự cho phép

**Hành vi tấn công** trong bối cảnh bảo mật là những hành động nhằm xâm nhập, làm gián đoạn, chiếm quyền, thao túng hoặc truy xuất trái phép hệ thống và dữ liệu. Khi đánh giá một tình huống thực tế, phải phân biệt **tín hiệu kỹ thuật**, **quyền được cấp** và **ý định**; một log kết nối riêng lẻ không thể chứng minh toàn bộ các yếu tố đó.

Ngay cả người được thuê kiểm thử cũng có thể tạo hành vi **ngoài phạm vi được ủy quyền** nếu:

- Chuyển sang quét IP hoặc tên miền chưa được phê duyệt.
- Thử nghiệm cơ chế xác thực trên tài khoản thật mà quy tắc thực hiện không cho phép.
- Tiếp tục tác động dù đã chạm ngưỡng dừng do vận hành yêu cầu.
- Thu thập hoặc sao chép dữ liệu nhạy cảm vượt quá mức tối thiểu đã được thống nhất.
- Thử tác động đến hạ tầng của nhà cung cấp hoặc khách hàng thứ ba mà họ không có quyền cho phép.

Việc vượt phạm vi cần được **dừng và xử lý theo quy trình**. Đánh giá trách nhiệm pháp lý cụ thể phải dựa trên hợp đồng, quyền sở hữu, quy định áp dụng và chứng cứ đầy đủ; không tự động kết luận một cá nhân phạm tội chỉ vì xuất hiện cảnh báo kỹ thuật.

### 2.3. So sánh các tiêu chí thực tế

| Khía cạnh | Kiểm tra nằm trong phạm vi cho phép | Hoạt động đáng ngờ hoặc ngoài phạm vi |
| --- | --- | --- |
| Ủy quyền | Có xác nhận hợp lệ từ bên có thẩm quyền | Thiếu bằng chứng chấp thuận hoặc đã bị thu hồi |
| Tài sản | Đúng danh sách IP/domain/tài khoản được giao | Mở rộng sang hệ thống không được cấp quyền |
| Kỹ thuật | Thuộc danh mục được phép, có giới hạn | Sử dụng phương pháp bị loại trừ hoặc chưa duyệt |
| Khung thời gian | Đúng cửa sổ kiểm thử | Ngoài lịch hoặc sau yêu cầu dừng |
| Kiểm soát tác động | Có giới hạn tải, người liên hệ và phương án khôi phục | Bỏ qua ảnh hưởng đến dịch vụ và dữ liệu |
| Dữ liệu | Chỉ tiếp cận và lưu bằng chứng được cho phép | Truy cập, sao chép, tiết lộ dữ liệu vượt quyền |
| Ghi nhận | Có nhật ký tác vụ, báo cáo và đầu mối chịu trách nhiệm | Thiếu dấu vết đối soát hoặc hành động cố tình che giấu |

**Không có một dấu hiệu đơn lẻ nào thay thế được việc đối chiếu đầy đủ.** Hoạt động có giấy phép nhưng gây gián đoạn ngoài ngưỡng chấp thuận phải dừng, trong khi một gói tin trông giống quét từ địa chỉ chưa biết vẫn cần điều tra trước khi gán động cơ.

## 3. Reconnaissance thụ động và chủ động: hai trục độc lập với quyền

Trinh sát có thể chia thành:

- **Passive reconnaissance:** khai thác dữ liệu có sẵn từ bên thứ ba hoặc thông tin đã công bố, không chủ động gửi thăm dò trực tiếp đến hạ tầng mục tiêu. Ví dụ: đọc dữ liệu Certificate Transparency, đăng ký miền, passive DNS hoặc chỉ mục công khai.
- **Active reconnaissance:** chủ động tương tác với hệ thống hoặc đường kết nối của mục tiêu nhằm khám phá hoặc xác minh. Ví dụ: gửi yêu cầu tới máy chủ, kiểm tra khả năng kết nối dịch vụ hoặc thực hiện khảo sát mạng bằng công cụ đã được duyệt.

Đây là cách phân biệt theo **phương thức kỹ thuật**, không phải phán quyết về quyền thực hiện. Một phép thử chủ động có thể hoàn toàn hợp lệ trong phạm vi; một hoạt động thu thập thụ động vẫn có thể vi phạm chính sách dữ liệu, điều khoản nguồn thông tin hoặc giới hạn thỏa thuận.

| Tình huống | Mức tương tác | Câu hỏi về tính hợp lệ |
| --- | --- | --- |
| Đọc kết quả CT log có sẵn từ nhà cung cấp dữ liệu | Thụ động đối với mục tiêu | Nguồn và dữ liệu có được sử dụng trong phạm vi công việc không? |
| Kiểm tra dịch vụ TCP trên máy chủ thử nghiệm được chỉ định | Chủ động | IP, cổng, thời gian và loại kiểm thử có được duyệt không? |
| Truy cập một trang web công khai để xem nội dung | Chủ động với máy chủ web | Việc truy cập thuộc hoạt động thông thường hay một kịch bản kiểm thử có giới hạn? |
| Đọc tài liệu công khai rồi thử các tài khoản tìm thấy | Đọc tài liệu có thể thụ động; thử tài khoản là chủ động | Việc sử dụng thông tin xác thực có được phép rõ ràng không? |
| Thu thập tín hiệu Wi-Fi tại cơ sở của đơn vị khác | Có thể chỉ quan sát tín hiệu | Có quyền hiện diện, thu thập và xử lý dữ liệu vô tuyến hay không? |

Một hành động có thể có **tác động nhỏ** nhưng vẫn ngoài quyền. Ngược lại, một hoạt động tải cao được cấp phép vẫn phải tuân thủ giới hạn tác động; “có quyền kiểm thử” không phải quyền thực hiện mọi phương pháp.

## 4. Ai có thể cấp phép và cấp phép cho điều gì?

### 4.1. Phải xác định đúng chủ thể có thẩm quyền

Người đề nghị kiểm thử cần phân biệt **đơn vị sử dụng**, **đơn vị vận hành**, **chủ sở hữu dữ liệu** và **bên sở hữu hạ tầng**. Ví dụ:

- Doanh nghiệp có thể quản lý ứng dụng của mình nhưng hạ tầng chạy trên dịch vụ cloud của nhà cung cấp.
- Một website thuộc doanh nghiệp có thể sử dụng CDN, cổng thanh toán hoặc dịch vụ xác thực của bên thứ ba.
- Phân hệ mạng tại văn phòng có thể được vận hành bởi nhà cung cấp dịch vụ quản trị.
- Nhóm phát triển có thể quản lý repository nhưng không được tự phê duyệt kiểm thử xâm nhập toàn bộ hệ thống sản xuất.

Quyền của một người quản trị tài khoản **không đương nhiên bao trùm** tất cả đối tác, người dùng, dữ liệu và nền tảng liên quan. Cần đọc hợp đồng, phạm vi trách nhiệm và chính sách kiểm thử của các nhà cung cấp. Khi không chắc, đưa tài sản vào danh sách **chờ làm rõ** và chưa thực hiện thao tác chủ động.

### 4.2. Bug bounty và chương trình công bố lỗ hổng

Chương trình bug bounty hoặc Vulnerability Disclosure Program (VDP) có thể cho phép người tham gia kiểm tra một số tài sản theo điều kiện công bố. Tuy nhiên, trang công khai của chương trình là **phạm vi ủy quyền có điều kiện**, không phải sự đồng ý cho mọi hệ thống mang thương hiệu đó.

Cần xác minh phiên bản chính sách hiện hành, các tài sản **in scope**, mục tiêu **out of scope**, kỹ thuật cấm, giới hạn dữ liệu, yêu cầu báo cáo và điều kiện dừng. Một tên miền con xuất hiện trong Certificate Transparency không tự động nằm trong phạm vi chương trình.

### 4.3. Đường ranh giữa hợp đồng, quyền kỹ thuật và quyền thực hiện

**Có thông tin đăng nhập** chỉ chứng minh có khả năng xác thực; nó không tự cấp quyền kiểm thử. **Có thể định tuyến tới một địa chỉ** cũng không đồng nghĩa được phép quét. **Có công cụ trong máy** không đồng nghĩa công cụ được dùng với mọi mục tiêu.

Chỉ nên coi hoạt động đã được phê duyệt khi phạm vi, phương pháp và thẩm quyền được ghi nhận đủ rõ để cả người kiểm thử lẫn người vận hành cùng hiểu.

## 5. Rules of Engagement (ROE): biến sự cho phép thành quy tắc có thể thực thi

**ROE** (*Rules of Engagement*) mô tả cách tiến hành kiểm thử để bảo vệ mục tiêu và giúp hai bên kiểm chứng xem hoạt động có đúng phạm vi hay không. ROE nên cụ thể hơn một câu “cho phép kiểm thử hệ thống”.

| Trường cần có | Nội dung cần làm rõ |
| --- | --- |
| Chủ thể cấp phép | Tổ chức, người phê duyệt, tư cách và phương thức xác nhận |
| Mục tiêu | Ví dụ: kiểm tra cấu hình firewall, phân đoạn hoặc mức phơi lộ dịch vụ |
| Danh sách tài sản | Domain, IP/CIDR, subnet, ứng dụng, account/project cloud, môi trường được phép |
| Ngoại lệ | IP/host, tenant bên thứ ba, dữ liệu hoặc dịch vụ nhạy cảm bị loại trừ |
| Kỹ thuật cho phép | Khảo sát cấu hình, đánh giá thụ động, kiểm tra kết nối, quét lỗ hổng có giới hạn nếu được duyệt |
| Kỹ thuật cấm | Ví dụ: DoS, phá hoại dữ liệu, phát tán mã độc, khai thác ngoài nhu cầu kiểm chứng |
| Thời gian | Múi giờ, khung thử nghiệm, lịch bảo trì và ngày hết hiệu lực |
| Giới hạn tác động | Ngưỡng tải/giới hạn thực hiện, dữ liệu thử nghiệm, trạng thái hệ thống cần giám sát |
| Liên hệ | Người kiểm thử, chủ tài sản, SOC/NOC, liên hệ khẩn cấp, kênh thông báo |
| Điều kiện dừng | Suy giảm dịch vụ, chạm dữ liệu ngoài phạm vi, phát hiện tuyến ra bên thứ ba, lệnh dừng từ chủ tài sản |
| Xử lý dữ liệu | Cách giữ bằng chứng, che thông tin nhạy cảm, nơi lưu, thời gian lưu và xóa |
| Kết thúc | Báo cáo, xác nhận hoàn thành, xử lý ngoại lệ và phê duyệt kiểm thử lại |

### 5.1. Mẫu ROE minh họa

Ví dụ sau dùng tên miền **example.org** và dải địa chỉ **192.0.2.0/24**, đều là dữ liệu dành cho tài liệu minh họa. Các tên vai trò và lịch trình chỉ là giả định. Đây là mẫu để học cách khai báo giới hạn, **không phải giấy phép kiểm thử** bất kỳ hệ thống nào.

~~~yaml
engagement:
  id: TRAINING-ROE-012
  purpose: "Xác minh phân đoạn mạng và dịch vụ được công bố"
  approval:
    authorizedByRole: "Chủ hệ thống thử nghiệm"
    approvalRecord: "Hồ sơ chấp thuận nội bộ đã ký"
  scope:
    included:
      - "app-test.example.org"
      - "192.0.2.10/32"
    excluded:
      - "Hệ thống sản xuất và mọi tài sản không liệt kê"
      - "Dịch vụ, tài khoản và dữ liệu của bên thứ ba"
  window:
    start: "2026-12-02T09:00:00+07:00"
    end: "2026-12-02T12:00:00+07:00"
  permitted:
    - "Rà soát cấu hình với chủ tài sản"
    - "Xác minh các kết nối đã duyệt ở mức tải thấp"
    - "Kiểm tra luồng bị từ chối bằng tài khoản thử nghiệm"
  prohibited:
    - "Tấn công làm gián đoạn dịch vụ"
    - "Truy cập hoặc xuất dữ liệu thật ngoài phạm vi"
    - "Kiểm tra tài sản và tài khoản không liệt kê"
  stopConditions:
    - "Người phụ trách yêu cầu dừng"
    - "Hệ thống có dấu hiệu suy giảm bất thường"
    - "Phát hiện tài nguyên nằm ngoài danh sách đã duyệt"
  communication:
    primaryRole: "Trưởng nhóm kiểm thử"
    incidentRole: "SOC/NOC trực ca"
  evidenceHandling:
    classification: "Nội bộ - giới hạn người đọc"
    useSyntheticData: true
    retention: "Theo chính sách lưu giữ đã được thỏa thuận"
~~~

Phần **included** có thể ghi IP cụ thể hoặc tài nguyên định danh rõ ràng. Nếu muốn phép thử bao gồm toàn bộ các miền con, phải nêu cách xác định miền con và cách loại trừ các host thuộc nhà cung cấp khác; việc ghi một tên miền gốc **không tự động** cấp quyền với mọi tài sản liên quan. Với cloud, account/project, vùng triển khai, tài nguyên và chính sách nhà cung cấp cần được xem xét song song.

### 5.2. Quyền luôn gắn với thời gian và bối cảnh

Thư phê duyệt của một đợt kiểm thử đã kết thúc không tự kéo dài cho đợt tiếp theo. Khi quy mô, danh sách đích hoặc phương pháp thay đổi, phải cập nhật và nhận chấp thuận theo quy trình trước khi thực hiện phần phát sinh.

## 6. Sơ đồ quyết định trước một thao tác kiểm thử

~~~mermaid
flowchart TD
    A["Đề xuất thao tác reconnaissance / kiểm thử"] --> B{"Có chấp thuận hợp lệ?"}
    B -->|Không hoặc chưa rõ| X["Không thực hiện; làm rõ thẩm quyền"]
    B -->|Có| C{"Tài sản, danh tính, kỹ thuật nằm trong phạm vi?"}
    C -->|Không| Y["Dừng thao tác; yêu cầu điều chỉnh phạm vi"]
    C -->|Có| D{"Đúng thời gian và điều kiện an toàn?"}
    D -->|Không| Z["Hoãn hoặc xin phê duyệt thay đổi"]
    D -->|Có| E["Thực hiện trong giới hạn, ghi nhật ký"]
    E --> F{"Xuất hiện điều kiện dừng / tác động bất thường?"}
    F -->|Có| G["Dừng; thông báo đầu mối; giữ bằng chứng"]
    F -->|Không| H["Đối soát kết quả; báo cáo; kết thúc"]
~~~

Sơ đồ có hai ý quan trọng. Thứ nhất, **có quyền ban đầu không loại bỏ việc kiểm tra trước từng bước**. Thứ hai, khi xuất hiện điều kiện dừng, ưu tiên ngừng hoạt động gây tác động và thông báo người có trách nhiệm; không tiếp tục chỉ để hoàn thành mục tiêu kỹ thuật.

## 7. Các tình huống ranh giới thường gặp

### 7.1. Quét cổng và khám phá dịch vụ

**Được phép:** đội đánh giá được giao kiểm tra nhóm máy thử nghiệm cụ thể, trong giờ bảo trì và theo phương pháp đã duyệt. Họ ghi nhận nguồn, đích, thời điểm và kết quả, sau đó báo cáo cấu hình firewall có đúng chính sách không.

**Ngoài phạm vi:** đội quét thêm dải IP của đối tác vì thấy chúng đi qua cùng VPN, mặc dù hợp đồng không liệt kê. Kỹ thuật có thể tương tự nhưng quyền thực hiện khác nhau.

**Nhận diện từ bên phòng thủ:** luồng quét liên tiếp có thể kích hoạt IDS. SOC cần kiểm tra ticket, danh sách IP nguồn, đích, phương pháp và lịch. Không chỉ dựa vào sự xuất hiện của công cụ quét để phân loại.

### 7.2. Kiểm thử đăng nhập và xác thực

**Được phép:** kiểm thử quy tắc MFA hoặc khóa tài khoản bằng **tài khoản thử nghiệm** và số lần thử đã thống nhất, dưới sự giám sát của người phụ trách.

**Ngoài phạm vi:** lấy danh sách nhân viên từ nguồn công khai rồi thử đăng nhập tài khoản thật khi kế hoạch chỉ cho phép kiểm tra cấu hình MFA bằng tài khoản giả lập. Không nên biến kết quả reconnaissance thành quyền thử xác thực.

**Rủi ro:** tài khoản có thể bị khóa, gây gián đoạn nghiệp vụ hoặc tạo sự kiện an ninh giả. Kịch bản cần quy định giới hạn, đối tượng, kênh thông báo và điều kiện dừng.

### 7.3. Website và API nghiệp vụ

**Được phép:** kiểm chứng phân quyền ở một endpoint API thử nghiệm với dữ liệu giả lập, dùng các tài khoản được cấp.

**Ngoài phạm vi:** chuyển sang API sản xuất hoặc truy xuất dữ liệu khách hàng thật vì cùng dùng hostname, reverse proxy hoặc công nghệ.

**Nguyên tắc:** khả năng kết nối HTTPS không phải quyền truy cập nội dung; việc có tài khoản thường không cấp quyền thực hiện các hành động kiểm thử đặc quyền.

### 7.4. VPN và vùng quản trị

**Được phép:** đo sự phân cách giữa VPN nhân viên và management zone qua các luồng kết nối đã được duyệt, không truy cập thiết bị quản trị ngoài danh sách.

**Ngoài phạm vi:** dùng kết nối VPN hợp lệ để khảo sát mọi subnet nội bộ mà không được chủ hệ thống phê duyệt. **Kết nối VPN thành công không tự tạo quyền kiểm thử toàn mạng**.

### 7.5. DNS và bản ghi công khai

**Được phép:** phân tích bản ghi DNS do tổ chức quản lý hoặc đọc dữ liệu lịch sử bên thứ ba nhằm lập inventory, theo phạm vi và điều khoản nguồn dữ liệu.

**Cần xem xét thêm:** các hoạt động gửi khối lượng lớn truy vấn trực tiếp tới authoritative DNS, kiểm tra khả năng chuyển vùng, tải bất thường hoặc ảnh hưởng tới tên miền của bên thứ ba có thể là bước chủ động vượt quá hoạt động passive được giao.

**Nguyên tắc:** dữ liệu công khai giúp lập giả thuyết về tài sản; nó không đồng nghĩa được phép kiểm thử các dịch vụ xuất hiện trong dữ liệu đó.

### 7.6. Mạng không dây

**Được phép:** đội phụ trách kiểm tra mạng Wi-Fi tại địa điểm xác định, trong khung thời gian đã duyệt và chỉ đối với các SSID/thiết bị được liệt kê.

**Ngoài phạm vi:** thử tác động lên mạng của khách thuê khác hoặc mạng lân cận chỉ vì tín hiệu vô tuyến nằm trong phạm vi thu nhận của thiết bị. SSID nhìn thấy được không đồng nghĩa là tài sản được phép kiểm thử.

### 7.7. Cloud, SaaS và nhà cung cấp

**Được phép:** rà soát quyền IAM, security group và cấu hình dịch vụ trong cloud account/project đã được chủ sở hữu phê duyệt, bằng tài khoản đánh giá được cấp quyền.

**Ngoài phạm vi:** tác động sang account khác, hạ tầng dùng chung của nhà cung cấp hoặc tenant của khách hàng khác khi chưa có chấp thuận tương ứng.

Nhiều nền tảng có **chính sách kiểm thử riêng**. Hãy kiểm tra điều kiện của nhà cung cấp và giới hạn của hợp đồng; việc tổ chức sở hữu một workload chưa chắc đồng nghĩa có quyền thử nghiệm mọi lớp nền tảng bên dưới.

## 8. Nhìn từ SOC: phân biệt bằng chứng vận hành với suy đoán

Trong giám sát xâm nhập, firewall, IDS/IPS và hệ thống phát hiện thường nhận biết **mẫu hành vi**: nhiều kết nối bị từ chối, nhiều đích hoặc cổng trong thời gian ngắn, nhiều lần xác thực thất bại, thay đổi lưu lượng bất thường. Những tín hiệu này có thể xuất hiện ở cả hoạt động kiểm thử được phép và hành vi đáng ngờ.

Một SOC hiệu quả cần **đối chiếu bối cảnh và hồ sơ phê duyệt**, không tắt cảnh báo chỉ vì nguồn giống một công cụ kiểm thử, cũng không khẳng định có xâm nhập chỉ vì một chữ ký IDS khớp.

### 8.1. Những trường dữ liệu nên đối chiếu

| Nguồn | Thông tin hữu ích | Giới hạn |
| --- | --- | --- |
| Firewall / flow log | IP nguồn/đích, cổng, giao thức, thời điểm, kết quả allow/deny, lượng dữ liệu | Không luôn cho biết danh tính người điều khiển hoặc lệnh ứng dụng |
| IDS/IPS | Chữ ký, kiểu bất thường, tài sản liên quan, mức cảnh báo | Có thể báo sai hoặc bỏ sót; chữ ký không chứng minh quyền hay ý định |
| VPN / ZTNA | Người dùng, thiết bị, phiên, chính sách truy cập | IP bên trong có thể được NAT, thay đổi theo phiên |
| IAM / cloud audit | Principal, API/action, tài nguyên và thời điểm thực hiện | Một quyền hợp lệ có thể vẫn bị lạm dụng; cần đối chiếu phê duyệt |
| DNS logs | Truy vấn, thời điểm, resolver, tên được phân giải | Không chứng minh đã kết nối tới host được phân giải |
| WAF / API logs | Endpoint, phương thức, kết quả xác thực, mã phản hồi | Có thể thiếu dữ liệu về hành động phía sau hoặc bị ẩn qua proxy |
| Ticket / ROE | Tài sản, nguồn kiểm thử, thời gian, mục đích, người liên hệ | Hồ sơ có thể hết hạn hoặc không phản ánh thay đổi phát sinh |

### 8.2. Ví dụ sự kiện giám sát giả lập

~~~json
{
  "event_time": "2026-12-02T09:42:00+07:00",
  "event_type": "connection_pattern_alert",
  "source_ip": "198.51.100.20",
  "destination_ip": "192.0.2.10",
  "destination_zone": "test-dmz",
  "observed_behavior": "several service connection attempts",
  "sensor": "network-ids",
  "ticket_candidate": "TRAINING-ROE-012",
  "authorization_verified": false,
  "triage_state": "pending-correlation"
}
~~~

Các địa chỉ **198.51.100.0/24** và **192.0.2.0/24** được dành cho ví dụ. Sự kiện minh họa vẫn ở trạng thái **chưa xác minh ủy quyền**. Chỉ khi đối chiếu ticket, IP nguồn được cấp, tài sản đích, thời gian và phương pháp, SOC mới có thể xác nhận hoạt động khớp ROE.

Lưu ý: cùng một IP nguồn có thể được nhiều người dùng chung qua NAT, proxy, VPN hoặc hạ tầng kiểm thử. Do đó, cần đối chiếu thêm danh tính phiên, host, dấu thời gian và log tương ứng; **danh sách cho phép IP không phải bằng chứng tuyệt đối** về danh tính.

### 8.3. Quy trình triage một cảnh báo reconnaissance

1. **Tiếp nhận và bảo toàn dữ kiện ban đầu:** thời điểm, nguồn/đích, cổng, rule, dấu hiệu bất thường, mức ảnh hưởng.
2. **Đối chiếu hồ sơ kiểm thử:** có ticket hợp lệ và đầu mối phụ trách không? Tài sản, lịch, công cụ/phương pháp có khớp không?
3. **Xác minh bằng kênh đã đăng ký:** kiểm tra với đầu mối kiểm thử hoặc chủ tài sản, không chấp nhận một lời tự nhận “đang kiểm thử” như bằng chứng đủ.
4. **Đánh giá ảnh hưởng:** có gián đoạn, khóa tài khoản, truy xuất dữ liệu bất thường, thay đổi cấu hình hoặc dấu hiệu lan rộng không?
5. **Phân loại và xử lý:** khớp ROE → ghi nhận sự kiện kiểm thử; chưa rõ hoặc vượt phạm vi → làm rõ, tạm dừng hoạt động kiểm thử liên quan; có dấu hiệu xâm nhập → áp dụng quy trình ứng phó sự cố.
6. **Cập nhật phát hiện và bài học:** cải thiện kế hoạch thông báo, phát hiện sai lệch, điều kiện dừng và các biện pháp phòng vệ.

Một hoạt động có ticket hợp lệ vẫn có thể cần **can thiệp ngay** nếu vượt giới hạn hoặc ảnh hưởng sản xuất. Ngược lại, việc gắn nhãn “pentest” cho một log mà chưa có kiểm chứng cũng làm suy yếu khả năng giám sát thực.

## 9. Phát hiện hoạt động vượt phạm vi và xử lý tình huống

### 9.1. Những tín hiệu cần rà soát

- Kết nối nhắm đến tài sản **không nằm trong danh sách scope**, đặc biệt là vùng quản trị và dữ liệu.
- Hoạt động diễn ra ngoài cửa sổ kiểm thử hoặc từ nguồn không được khai báo.
- Số lượng yêu cầu hoặc lỗi xác thực cao hơn giới hạn được thống nhất.
- Có dấu hiệu thay đổi cấu hình, xóa dữ liệu hoặc di chuyển sang tài khoản/hệ thống khác khi chưa được duyệt.
- Có luồng chuyển dữ liệu, lưu lượng đi ra ngoài hoặc hành vi gây suy giảm dịch vụ không phù hợp mục tiêu.
- Nhóm kiểm thử không liên lạc được với đầu mối trực ca trong khi xuất hiện điều kiện dừng.

Đây là **tín hiệu điều tra**, không phải bằng chứng đầy đủ về động cơ của một chủ thể.

### 9.2. Khi người kiểm thử gặp tài sản hoặc dữ liệu ngoài phạm vi

Trình tự phù hợp là: **dừng bước phát sinh**, tránh mở rộng tác động, ghi nhận thông tin tối thiểu để xác định tình huống, bảo vệ dữ liệu đã vô tình quan sát, thông báo đầu mối được quy định và chờ quyết định về thay đổi phạm vi. Không tự sử dụng tài khoản, sao chép dữ liệu hoặc tiếp tục thử nghiệm để “xác nhận thêm” ngoài quyền.

Nếu phát hiện một bí mật truy cập đã lộ, chỉ nên ghi vị trí và loại thông tin đủ để chủ sở hữu xử lý; không thử sử dụng bí mật đó nhằm chứng minh khả năng truy cập khi chưa được ủy quyền.

### 9.3. Khi hệ thống có dấu hiệu suy giảm

Dừng hoạt động có khả năng gây tác động, thông báo NOC/SOC và chủ hệ thống, lưu thời điểm và thao tác vừa thực hiện, phối hợp đánh giá sức khỏe dịch vụ. Tùy ROE, việc khôi phục hoặc dừng toàn bộ phiên có thể do chủ hệ thống quyết định. Không tiếp tục tác động để thu thập thêm bằng chứng khi đã có điều kiện dừng.

## 10. Kiểm soát trong hệ thống bảo mật mạng

Phân biệt kiểm tra được phép và hoạt động đáng ngờ không chỉ là quy trình nhân sự; nó gắn trực tiếp với các lớp phòng vệ mạng.

### 10.1. Phân đoạn và firewall

Firewall bảo vệ **ranh giới kết nối**. Một nhóm pentest được phép kiểm tra DMZ không được tự động có đường đến data zone. Ma trận rule cần dựa trên nghiệp vụ và các ngoại lệ kiểm thử đã duyệt phải có chủ sở hữu, thời gian hết hạn, phạm vi nguồn–đích rõ ràng.

**Không nên mở toàn bộ mạng** hoặc tắt kiểm soát trong thời gian kiểm thử chỉ để giảm cảnh báo. Nếu cần điều chỉnh cho một kịch bản cụ thể, phải được phê duyệt và khôi phục cấu hình sau khi hoàn thành.

### 10.2. VPN, ZTNA và xác thực kết nối

VPN cung cấp đường kết nối được bảo vệ; ZTNA hoặc hệ thống kiểm soát truy cập có thể đưa ra quyết định dựa trên danh tính và ngữ cảnh. Tuy nhiên, **được kết nối** không đồng nghĩa **được phép kiểm thử mọi máy**. Phải kiểm soát cả quyền mạng lẫn quyền thực hiện tác vụ.

### 10.3. IDS/IPS và SIEM

IDS/IPS phản ánh tín hiệu kỹ thuật, SIEM giúp liên kết với ticket và nhật ký xác thực. Với kiểm thử hợp lệ, cần có cách đánh dấu hoặc tương quan sự kiện để phân biệt khi phân tích. Tuy nhiên, không nên tạo ngoại lệ cố định làm hệ thống bỏ qua mọi cảnh báo từ cùng nguồn, nhất là khi nguồn dùng chung.

### 10.4. DNS và mạng không dây

Hồ sơ DNS công khai hay SSID nhìn thấy được chỉ giúp xác định **ứng viên tài sản**. Muốn thử hành vi trực tiếp với authoritative DNS, điểm truy cập Wi-Fi hoặc thiết bị điều khiển, cần có quyền cụ thể. Biện pháp bảo vệ thường bao gồm phân quyền quản trị DNS, giám sát thay đổi zone, tách mạng khách và quản trị Wi-Fi, và quản lý các thiết bị truy cập được phép.

### 10.5. Cloud và API quản trị

Trên đám mây, ranh giới không chỉ là subnet: IAM, account/project, chính sách tổ chức, quyền API và log quản trị đều quan trọng. Một tài khoản đánh giá được cấp quyền **read-only** không có quyền thay đổi security group hoặc tạo tài nguyên chỉ để xác minh một giả thuyết; các hành động ghi phải có phê duyệt riêng.

## 11. Phân biệt kiểm thử, diễn tập và ứng phó sự cố

| Hoạt động | Mục đích | Điểm cần làm rõ về quyền |
| --- | --- | --- |
| Kiểm kê bề mặt tấn công | Biết tài sản và dấu vết công khai | Nguồn dữ liệu, phạm vi tổ chức, cách xác minh tài sản |
| Vulnerability assessment | Xác định điểm yếu tiềm ẩn | Đối tượng, phương pháp và mức tác động của scanner |
| Penetration test | Đánh giá khả năng khai thác trong phạm vi | Mức kiểm chứng cho phép, tài khoản thử nghiệm, giới hạn dữ liệu |
| Red team / adversary emulation | Mô phỏng hành vi đối thủ để kiểm tra phòng vệ | Mục tiêu, kỹ thuật, giám sát, điều kiện dừng, vai trò người được biết |
| Purple team | Phối hợp kiểm tra và cải thiện phát hiện/ứng phó | Quyền thực hiện kịch bản, trao đổi dữ liệu giữa đội |
| Ứng phó sự cố | Khoanh vùng, xác định và xử lý một sự kiện bảo mật | Quyền điều tra, quyền truy xuất bằng chứng, quy trình xử lý dữ liệu |

Không nên đánh đồng tất cả hoạt động này thành “đã được phép tấn công mọi thứ”. Mỗi loại có **phạm vi hành động và dữ liệu khác nhau**, thậm chí trong cùng một tổ chức. Một đội có quyền xem log trong ứng phó sự cố không mặc nhiên có quyền thử khai thác mọi ứng dụng.

## 12. Tình huống tổng hợp: cảnh báo quét trong cửa sổ bảo trì

Giả sử SOC nhận cảnh báo từ IDS lúc **09:42 (UTC+7)**: một nguồn đang tạo nhiều kết nối tới máy thử nghiệm **192.0.2.10**. Đội kiểm thử có ticket hoạt động từ **09:00–12:00**, nhưng SOC chưa xác minh nguồn phát thực tế.

### 12.1. Thu thập thông tin cần đối chiếu

- Ticket có còn hiệu lực và được phê duyệt bởi chủ hệ thống không?
- Nguồn lưu lượng hiện tại có trùng danh sách nguồn hoặc danh tính phiên kiểm thử không?
- Đích **192.0.2.10** có nằm trong phạm vi và có được duyệt kiểm tra những dịch vụ đang bị báo cáo không?
- Mẫu kết nối có thuộc loại kiểm tra đã cho phép, nằm trong giới hạn tải và đúng cửa sổ không?
- Có sự kiện đi kèm như khóa tài khoản, lỗi ứng dụng, tăng độ trễ hoặc truy cập dữ liệu nhạy cảm không?

### 12.2. Ba khả năng kết luận

**Trường hợp A – Khớp hoàn toàn:** có xác minh đầu mối, danh tính, đích, kỹ thuật, thời điểm và giới hạn phù hợp. SOC ghi nhận đây là hoạt động kiểm thử được phép và giữ dữ liệu để đánh giá khả năng phát hiện.

**Trường hợp B – Có ticket nhưng vượt phạm vi:** ví dụ nguồn đã chuyển sang subnet khác chưa được duyệt. SOC báo đầu mối, yêu cầu dừng phần hoạt động vượt phạm vi, lưu bằng chứng và cập nhật chủ hệ thống.

**Trường hợp C – Không có bằng chứng ủy quyền:** chưa thể gắn nhãn pentest. SOC tiếp tục xử lý như sự kiện đáng ngờ theo mức độ rủi ro, xác minh tài sản và cân nhắc biện pháp ứng phó phù hợp quy trình. Không suy luận danh tính hay trách nhiệm pháp lý từ một IP đơn lẻ.

**Điểm học được:** dữ kiện kỹ thuật cho biết “điều gì đang xảy ra”; hồ sơ ủy quyền và bằng chứng vận hành cho biết “hoạt động đó có phù hợp phạm vi cho phép hay không”.

## 13. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1: Phân tích quyền

Một nhân viên có quyền quản trị firewall nội bộ nhưng muốn quét toàn bộ mạng đối tác được kết nối qua VPN. Việc này đã được phép chưa?

**Gợi ý:** Chưa thể coi là được phép. Quyền quản trị một hệ thống không tự tạo quyền kiểm thử tài sản của đối tác; cần xác định chủ thể có thẩm quyền và phạm vi được chấp thuận.

### Câu hỏi 2: Phân tích kỹ thuật

Một nhà cung cấp Internet indexing đã quét dịch vụ từ trước. Hôm nay, đội bảo mật chỉ đọc kết quả đã được lập chỉ mục. Hành động đọc kết quả có phải active reconnaissance đối với máy chủ đích không?

**Gợi ý:** Không trực tiếp thăm dò hệ thống đích khi chỉ đọc dữ liệu có sẵn; nhưng nền tảng tạo dữ liệu có thể đã dùng kỹ thuật chủ động. Việc đọc vẫn tạo yêu cầu tới nhà cung cấp dữ liệu.

### Câu hỏi 3: Cảnh báo giám sát

IDS ghi nhận hàng loạt kết nối đến nhiều cổng từ một IP đã xuất hiện trong ticket pentest. SOC có thể đóng sự kiện ngay không?

**Gợi ý:** Cần kiểm tra IP thực tế thuộc phiên nào, đích, thời gian, kỹ thuật và giới hạn. Ticket cũ hoặc IP dùng chung chưa đủ chứng minh toàn bộ hành vi hợp lệ.

### Câu hỏi 4: Điều kiện dừng

Trong bài kiểm thử API sản xuất đã duyệt, hệ thống bắt đầu tăng lỗi 5xx và nhóm vận hành báo dịch vụ suy giảm. Người kiểm thử nên làm gì?

**Gợi ý:** Dừng những thao tác có thể gây tác động, liên hệ đầu mối và giữ nhật ký; không tiếp tục để hoàn tất bộ ca kiểm thử khi đã chạm điều kiện dừng.

### Câu hỏi 5: Mở rộng phạm vi

Khi kiểm tra một ứng dụng được duyệt, đội pentest thấy URL chuyển hướng tới dịch vụ thanh toán của bên thứ ba. Có thể tiếp tục kiểm thử dịch vụ thanh toán không?

**Gợi ý:** Không tự mở rộng. Xác định ranh giới hệ thống và xin phê duyệt phù hợp từ bên có thẩm quyền; dịch vụ thứ ba thường cần xem xét riêng.

### Bài tập thực hành trên giấy

Hãy soạn **ROE rút gọn** cho tình huống đánh giá phân đoạn giữa hai subnet thử nghiệm: điền chủ thể phê duyệt, tài sản, phương pháp, thời gian, nguồn kiểm thử, luồng cho phép, luồng từ chối, điều kiện dừng, cách liên hệ và cách lưu bằng chứng. Sau đó tạo ba sự kiện log giả lập: một sự kiện khớp ROE, một sự kiện ngoài phạm vi và một sự kiện chưa đủ dữ kiện. Với mỗi sự kiện, ghi rõ **bằng chứng nào còn thiếu trước khi kết luận**.

## 14. Những điều cần ghi nhớ

- **Quyền thực hiện và phạm vi là tiêu chí cốt lõi.** Không phân loại một hành vi chỉ bằng tên công cụ, cổng mạng hay số lượng kết nối.
- **Phương thức thụ động hoặc chủ động không tự quyết định sự cho phép.** Mọi hoạt động phải tuân thủ giới hạn dữ liệu, tài sản và điều kiện áp dụng.
- **Ủy quyền phải đủ cụ thể và còn hiệu lực.** Cần xác định chủ thể phê duyệt, tài sản, kỹ thuật, khung thời gian, bên thứ ba và điều kiện dừng.
- **Có quyền vào mạng không có nghĩa có quyền kiểm thử mạng.** VPN, tài khoản cloud, thông tin đăng nhập hoặc truy cập một API không thay thế ROE.
- **SOC cần đối chiếu lưu lượng với hồ sơ và danh tính thực tế.** Một cảnh báo IDS là tín hiệu cần phân tích; một ticket pentest không phải lý do tự động bỏ qua mọi bất thường.
- **Khi vượt phạm vi hoặc có tác động bất thường, phải dừng và thông báo.** Giữ bằng chứng tối thiểu, bảo vệ dữ liệu và chỉ tiếp tục sau khi điều kiện được làm rõ.
- **Kiểm thử đúng quy trình giúp cải thiện bảo mật thực tế:** kiểm chứng phân đoạn, firewall, VPN, IAM, DNS, mạng không dây, cloud và khả năng phát hiện/ứng phó của tổ chức.
