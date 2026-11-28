# Khôi phục kết nối theo thứ tự an toàn

## 1. Vì sao thứ tự khôi phục quan trọng?

Khi một sự cố mạng đã được khoanh vùng, mục tiêu tiếp theo là đưa người dùng và dịch vụ trở lại hoạt động. Tuy nhiên, **khôi phục kết nối không đồng nghĩa với bật lại toàn bộ cổng mạng, tuyến định tuyến, VPN và quy tắc firewall**. Nếu điểm xâm nhập, tài khoản bị chiếm quyền hoặc thiết bị bị nhiễm mã độc vẫn còn, việc mở kết nối quá sớm có thể khiến kẻ tấn công tiếp tục di chuyển ngang, đánh cắp dữ liệu hoặc tái lây nhiễm.

Trong ứng phó sự cố mạng, **khôi phục theo thứ tự an toàn** là quá trình mở lại từng đường kết nối và từng nhóm dịch vụ theo quan hệ phụ thuộc, sau khi đáp ứng các điều kiện bảo mật, rồi kiểm chứng trước khi mở rộng phạm vi. Cách tiếp cận này áp dụng cho sự cố tại mạng văn phòng, trung tâm dữ liệu, kết nối chi nhánh, hạ tầng đám mây, VPN, hệ thống DNS và các vùng mạng được phân đoạn.

Sau bài học, người học có thể:

- Phân biệt **containment** (cô lập/kiềm chế sự cố), **eradication** (loại bỏ nguyên nhân và dấu vết xâm nhập) và **recovery** (khôi phục có kiểm soát).
- Xây dựng thứ tự khôi phục dựa trên **phụ thuộc dịch vụ, mức độ tin cậy và phạm vi ảnh hưởng**, thay vì chỉ dựa trên thiết bị nào bật lên trước.
- Đặt tiêu chí **go/no-go** tại từng cổng kiểm soát, kiểm chứng cả tính sẵn sàng lẫn tính an toàn.
- Thực hiện mở lại kết nối từng đợt, theo dõi dấu hiệu bất thường và quay lui khi kiểm chứng thất bại.

> **Nguyên tắc cốt lõi:** Chỉ khôi phục đường kết nối mà ta hiểu rõ nguồn, đích, mục đích, chủ sở hữu, biện pháp bảo vệ và phương pháp xác nhận. Mỗi lần mở lại kết nối đều là một thay đổi bảo mật cần được ghi nhận.

## 2. Điều kiện cần có trước khi khôi phục

**Không chuyển từ cô lập sang khôi phục chỉ vì lưu lượng đã giảm hoặc hệ thống đã truy cập được.** Người chỉ huy ứng phó sự cố (Incident Commander, IC) cần phối hợp với nhóm an ninh, mạng, hệ thống và chủ dịch vụ để xác nhận mức độ kiểm soát.

| Điều kiện | Cần xác minh | Nếu chưa đạt |
| --- | --- | --- |
| Phạm vi sự cố | Các tài sản, tài khoản, VLAN/VRF, subnet, đường VPN và dịch vụ bị ảnh hưởng đã được nhận diện ở mức đủ để triển khai an toàn | Tiếp tục cô lập vùng chưa rõ; không mở kết nối đại trà |
| Nguyên nhân xâm nhập | Cửa vào ban đầu đã được chặn, lỗ hổng liên quan đã xử lý hoặc có biện pháp bù trừ được phê duyệt | Chưa mở lại đường khai thác tương ứng |
| Độ tin cậy của tài sản | Thiết bị sẽ được kết nối đã được kiểm tra, làm sạch hoặc dựng lại từ bản chuẩn đáng tin cậy | Giữ trong mạng cách ly/quarantine |
| Danh tính và bí mật | Tài khoản, khóa API, mật khẩu quản trị, chứng thư, khóa VPN bị nghi lộ đã được xử lý và cấp lại khi cần | Chặn phiên và thông tin xác thực cũ |
| Chứng cứ và nhật ký | Bằng chứng cần thiết đã được bảo toàn; nguồn log/telemetry và dấu thời gian hoạt động | Bảo toàn và khôi phục khả năng quan sát trước |
| Bản khôi phục | Cấu hình, ảnh hệ thống, bản sao lưu và dữ liệu đã được kiểm tra tính toàn vẹn và thời điểm tạo | Không khôi phục từ bản nghi đã bị sửa đổi |
| Kế hoạch vận hành | Có người phê duyệt, người thực hiện, người giám sát, mức ưu tiên, tiêu chí thành công và phương án rollback | Hoàn thiện kế hoạch trước thay đổi |

**RTO** (Recovery Time Objective) cho biết thời gian gián đoạn tối đa chấp nhận được; **RPO** (Recovery Point Objective) cho biết mức mất dữ liệu tối đa chấp nhận được. Hai mục tiêu này giúp ưu tiên dịch vụ kinh doanh, nhưng **không thay thế điều kiện an toàn**. Nếu không đạt điều kiện khôi phục, nhóm ứng phó phải ghi nhận rủi ro và trình người có thẩm quyền quyết định phương án phù hợp.

Thông tin đầu vào tối thiểu của một kế hoạch khôi phục gồm sơ đồ kết nối hiện tại và mong muốn, danh sách các vùng tin cậy, ma trận nguồn–đích–cổng được phép, chuỗi phụ thuộc ứng dụng, danh sách tài sản sạch, điểm khôi phục dữ liệu, người phụ trách và kênh liên lạc ngoài hệ thống đang gặp sự cố.

## 3. Xây dựng thứ tự từ quan hệ phụ thuộc

Đừng dùng một thứ tự cố định cho mọi tổ chức. Ví dụ, dịch vụ xác thực có thể cần DNS và đồng bộ thời gian, trong khi hệ thống DNS được quản lý thông qua tài khoản thuộc dịch vụ xác thực. Khi xuất hiện phụ thuộc vòng, phải chuẩn bị một **đường quản trị độc lập** (out-of-band), tài khoản khẩn cấp được kiểm soát và một tập dịch vụ nền tảng tối thiểu để phá vòng phụ thuộc.

Sơ đồ tham khảo:

~~~mermaid
flowchart TD
    A["Quyết định khôi phục và bảo toàn chứng cứ"] --> B["Quản trị độc lập + giám sát"]
    B --> C["Lõi mạng và phân đoạn an toàn"]
    C --> D["Dịch vụ nền tảng: NTP, DNS, PKI, định danh, DHCP"]
    D --> E["Dữ liệu và ứng dụng nội bộ sạch"]
    E --> F["Kết nối biên/đối tác/VPN được giới hạn"]
    F --> G["Mở rộng người dùng theo đợt"]
    G --> H["Giám sát ổn định và bàn giao"]
    C -. "Duy trì ACL, route, giám sát" .-> F
    B -. "Quan sát ở mọi giai đoạn" .-> H
~~~

Đây là **thứ tự logic**; một tổ chức có thể đảo vị trí hai nhóm dịch vụ độc lập sau khi phân tích phụ thuộc. Tuy nhiên, **không bỏ qua kiểm soát phân đoạn, xác thực và quan sát** chỉ để rút ngắn thời gian khôi phục.

| Giai đoạn | Phạm vi kết nối | Điều kiện qua cổng kiểm soát |
| --- | --- | --- |
| G0 — Cho phép khôi phục | Chưa mở rộng kết nối | Có đánh giá rủi ro, chủ sở hữu, chứng cứ, tài sản sạch và kế hoạch rollback |
| G1 — Kênh quản trị và quan sát | Mạng quản trị độc lập, log, SIEM/NDR/IDS, truy cập cứu hộ | Chỉ quản trị viên được xác thực truy cập; đồng bộ thời gian và log đến nơi lưu trữ tin cậy |
| G2 — Lõi mạng được phân đoạn | Liên kết vật lý, L2/L3, định tuyến, firewall, VRF/VLAN cần thiết | Tuyến và chính sách đúng thiết kế; đường giữa các vùng chưa được phép vẫn bị chặn |
| G3 — Nền tảng thiết yếu | DNS, NTP, PKI, dịch vụ định danh, DHCP, kho cấu hình | Dịch vụ nền tảng đúng nguồn, đúng danh tính; chỉ các luồng phụ thuộc bắt buộc hoạt động |
| G4 — Dữ liệu và ứng dụng nội bộ | Cơ sở dữ liệu, hàng đợi, API, ứng dụng được làm sạch | Kiểm tra chức năng, dữ liệu, quyền truy cập và log ứng dụng đạt yêu cầu |
| G5 — Kết nối qua biên | Reverse proxy, Internet ingress/egress, kết nối đối tác, VPN/ZTNA | Kiểm soát danh tính, MFA, giới hạn đích và chính sách biên được kiểm chứng |
| G6 — Người dùng theo đợt | Nhóm pilot, các subnet/chi nhánh và thiết bị đầu cuối | Thiết bị đạt kiểm tra sức khỏe; không có cảnh báo tái xâm nhập chưa xử lý |
| G7 — Ổn định và kết thúc | Hoạt động sản xuất ở phạm vi được phê duyệt | SLI ổn định, nhật ký đầy đủ, ca trực tiếp nhận và có kế hoạch theo dõi hậu sự cố |

### G0 — Chốt quyền và phạm vi khôi phục

Lập danh sách **được phép mở** và **tiếp tục cách ly**. Nêu rõ tài sản nào đã được điều tra, hệ thống nào phải dựng lại và kết nối nào sẽ bị chặn cho đến khi có chứng cứ bổ sung. Ghi lại cấu hình hiện hành và trạng thái các chính sách firewall/ACL trước mọi thay đổi. Ước lượng tác động tới người dùng, khả năng mất dữ liệu, cửa sổ thay đổi và người quyết định quay lui.

**Gate G0:** IC hoặc người được ủy quyền chấp thuận kế hoạch; an ninh xác nhận mức độ kiểm soát; chủ dịch vụ chấp nhận trình tự và tiêu chí dừng.

### G1 — Khôi phục kênh quản trị và khả năng quan sát

Ưu tiên đường **out-of-band** hoặc mạng quản trị tách biệt, máy quản trị sạch, xác thực mạnh, nguyên tắc quyền tối thiểu và ghi log tập trung. Kiểm tra khả năng liên lạc tới hệ thống giám sát, nơi lưu bằng chứng, nguồn thời gian tin cậy và kênh phối hợp sự cố. Nếu cần sử dụng tài khoản khẩn cấp, phải hạn chế người sử dụng, ghi nhận đầy đủ và thu hồi sau tình huống.

Không mở quyền quản trị từ toàn Internet hoặc dùng lại thông tin xác thực bị nghi lộ. Để tránh điểm mù, xác nhận log từ firewall, VPN, DNS, định danh và thiết bị mạng có thể thu nhận **trước** khi tăng lưu lượng sản xuất.

**Gate G1:** Quản trị qua kênh tin cậy thành công; sự kiện kiểm thử xuất hiện tại nơi giám sát với thời gian chính xác; các đường quản trị ngoài phạm vi vẫn bị chặn.

### G2 — Lõi kết nối, định tuyến và phân đoạn

Khôi phục từng liên kết vật lý, VLAN/VRF, mạng overlay/underlay và tuyến động hoặc tĩnh theo thiết kế đã rà soát. Kiểm tra trạng thái link, lỗi giao diện, bảng MAC/ARP/ND, định tuyến hai chiều, kiểm soát chống loop và các đường dự phòng. Với firewall, đảm bảo các chính sách **deny by default** còn hiệu lực và chỉ khôi phục các luồng thực sự cần. Giám sát việc thay đổi đường đi có thể vô tình đưa lưu lượng qua vùng kém tin cậy hoặc vượt hệ thống kiểm soát.

Nên xác minh theo cặp **nguồn → đích** và cả chiều trả lời, bởi một phiên kết nối có thể thất bại do route bất đối xứng, NAT, security group, ACL hoặc bộ lọc trên host. Không xóa hàng loạt rule, mở toàn bộ east–west traffic hoặc cho phép mọi cổng để “thử cho nhanh”.

**Gate G2:** Đường đi hợp lệ thông suốt; những đường không được cho phép vẫn không thông; không có loop, route leak, flapping, thay đổi bất thường trong firewall hay IDS.

### G3 — Dịch vụ nền tảng và chuỗi tin cậy

Khôi phục các dịch vụ có nhiều phụ thuộc phía trên, theo thứ tự phù hợp kiến trúc thực tế:

1. **Thời gian/NTP:** bảo đảm đồng hồ của thiết bị, hệ thống giám sát, máy chủ và dịch vụ xác thực đủ đồng bộ để kiểm tra chứng thư và đối chiếu sự kiện.
2. **DNS:** xác minh DNS nội bộ, bản ghi thiết yếu, phân giải thuận/ngược khi cần, DNSSEC hoặc quy tắc bảo vệ DNS đang dùng. Đề phòng bản ghi bị đầu độc hoặc cấu hình chuyển tiếp bị sửa.
3. **PKI và quản lý khóa:** xác nhận chứng thư, chain of trust, hiệu lực, vòng đời khóa, CRL/OCSP nếu được sử dụng. Thay các khóa và chứng thư có nguy cơ lộ.
4. **Định danh và phân quyền:** kiểm tra IdP/AD/LDAP, MFA, nhóm quyền, tài khoản dịch vụ, token phiên và quyền truy cập khẩn cấp; thu hồi các phiên/tài khoản đã bị chiếm.
5. **DHCP, bí mật và kho cấu hình:** chỉ mở cho mạng và máy sạch có nhu cầu; kiểm tra máy cấp phát, địa chỉ, gateway, DNS được cấp và tính toàn vẹn cấu hình.

Một dịch vụ có thể phụ thuộc ngược lại dịch vụ khác. Khi đó dùng cấu hình cứu hộ đã phê duyệt hoặc thành phần nền tảng tối thiểu, rồi quay về kiến trúc bình thường và kiểm chứng lại. Không “chữa” lỗi DNS bằng cách vô hiệu hóa kiểm tra chứng thư hay bỏ MFA.

**Gate G3:** Phân giải tên, thời gian, chứng thư và đăng nhập của tài khoản thử nghiệm hợp lệ; người dùng/thiết bị không đủ điều kiện vẫn bị từ chối.

### G4 — Khôi phục dịch vụ nội bộ theo ưu tiên kinh doanh

Với ứng dụng có cơ sở dữ liệu, cache và hàng đợi, xác định thứ tự bật thành phần theo **tài liệu phụ thuộc**: lưu trữ dữ liệu đã kiểm tra → dịch vụ backend → API → giao diện hoặc tác vụ nền. Kiểm tra bản sao lưu không chứa cấu hình, tài khoản hay mã độc của giai đoạn bị xâm nhập; rà soát đồng bộ và khả năng nhất quán dữ liệu trước khi nhận ghi mới.

Mở quy tắc firewall theo luồng tối thiểu. Ví dụ: nhóm ứng dụng chỉ cần kết nối TCP tới một endpoint cơ sở dữ liệu xác định, không cần quyền truy cập toàn bộ subnet dữ liệu. Sau khi chức năng chạy được, kiểm tra cả **ủy quyền**: một người dùng hợp lệ vẫn không được đọc dữ liệu của người khác.

**Gate G4:** Các giao dịch nghiệp vụ mẫu thành công; giới hạn quyền và log đúng; không có luồng bất thường tới máy bị cách ly hoặc địa chỉ không được phép.

### G5 — Kiểm soát biên, kết nối đối tác và truy cập từ xa

Chỉ mở các dịch vụ hướng Internet sau khi hoàn tất kiểm tra ứng dụng, định danh, WAF/reverse proxy, rule NAT, security group, egress filtering và giám sát. Với VPN hoặc Zero Trust Network Access (ZTNA), yêu cầu xác thực mạnh, đánh giá tư thế thiết bị và quyền truy cập theo ứng dụng, phiên và người dùng; tránh khôi phục mô hình “vào VPN là thấy toàn bộ LAN”.

Với kết nối đối tác, xác minh cả chính sách hai phía và giới hạn nguồn/đích đã thỏa thuận. Nếu cắt chuyển DNS hoặc chứng thư, kiểm tra bản ghi, TTL, cache và đường trở về; chuẩn bị khả năng khôi phục cấu hình cũ nếu có thể quay lui an toàn.

**Gate G5:** Chỉ endpoint được công bố hoạt động; truy cập không xác thực hoặc không đúng quyền bị chặn; luồng ra Internet tuân thủ chính sách.

### G6 — Mở rộng theo vòng và khôi phục người dùng

Khôi phục bằng một **nhóm pilot nhỏ** gồm các thiết bị đã kiểm tra, sau đó tăng phạm vi theo bộ phận, subnet, chi nhánh hoặc tỷ lệ lưu lượng. Có thể dùng các vòng 5% → 25% → 100% làm ví dụ lập kế hoạch, nhưng tỷ lệ và thời gian quan sát phải tùy năng lực giám sát và mức rủi ro. Trong mỗi vòng, xác nhận xác thực, DNS, truy cập ứng dụng, độ trễ, tỷ lệ lỗi và tín hiệu IDS/EDR/NDR trước khi mở rộng.

Giữ thiết bị chưa sạch ở mạng quarantine với tập đích hỗ trợ khắc phục riêng. Mở kết nối diện rộng chỉ sau khi có bằng chứng pilot thành công; tránh dỡ bỏ cách ly hàng loạt bằng một lệnh.

**Gate G6:** Người dùng pilot thực hiện được nghiệp vụ đã chọn, không xuất hiện dấu hiệu tấn công lặp lại hoặc truy cập trái phép, các chỉ số ổn định trong cửa sổ giám sát đã định.

### G7 — Ổn định, đối soát và bàn giao

Theo dõi trong một khoảng thời gian phù hợp với đặc tính sự cố và chu kỳ sử dụng thực tế, kể cả các tác vụ định kỳ và ca làm việc khác. Kiểm tra không còn cấu hình cứu hộ, rule tạm hoặc quyền đặc biệt quá hạn. Chuyển quyền giám sát cho nhóm vận hành với dashboard, danh sách cảnh báo, ngưỡng và đầu mối xử lý cụ thể.

**Gate G7:** Chủ dịch vụ xác nhận đáp ứng SLO/SLI đã chọn; nhóm an ninh xác nhận không còn cảnh báo nghiêm trọng chưa được giải thích trong phạm vi theo dõi; nhật ký thay đổi và kế hoạch hành động sau sự cố được lưu.

## 4. Kiểm chứng cả kết nối lẫn an toàn

Một kết quả **ping thành công không chứng minh dịch vụ đã hồi phục**, và một lần HTTP 200 không chứng minh đường truy cập an toàn. Kiểm thử phải đi từ kết nối mạng đến danh tính, quyền và chức năng nghiệp vụ.

| Lớp/khía cạnh | Câu hỏi kiểm chứng | Bằng chứng điển hình |
| --- | --- | --- |
| L1/L2 | Interface ổn định? VLAN, trunk, MAC học đúng? Có loop hoặc lỗi giao diện? | Interface counters, trạng thái STP, bảng MAC |
| L3 | Route/VRF, next hop, ARP/ND đúng? Đường đi hai chiều có nhất quán? | Bảng route, traceroute theo nguồn đã chọn, flow logs |
| L4 | Đúng TCP/UDP port được phép? Timeout do ACL, firewall, NAT hay host? | Kết quả kết nối, firewall logs, state table |
| Dịch vụ nền tảng | DNS trả bản ghi tin cậy? Đồng hồ đúng? Chứng thư hợp lệ? | Kết quả DNS, NTP offset, kiểm tra TLS |
| L7/nghiệp vụ | API và thao tác người dùng có chạy được? Tỷ lệ lỗi và độ trễ đạt mục tiêu? | Synthetic transaction, HTTP status, APM |
| Xác thực/ủy quyền | Người đúng quyền truy cập được; người sai quyền bị từ chối? | Login test, access log, kiểm tra policy |
| An ninh | Có kết nối tới IOC, lưu lượng di chuyển ngang, egress lạ, phiên VPN bất thường? | IDS/IPS, EDR/NDR, DNS logs, SIEM correlation |

Một số lệnh **quan sát** trên máy Linux đã được cấp quyền, có thể thay bằng công cụ tương đương trong môi trường khác:

~~~bash
# Trạng thái interface và địa chỉ.
ip -br link
ip -br address

# Tuyến thực tế tới một đích nội bộ đã được phê duyệt.
ip route get 10.20.30.20

# Dịch vụ đang lắng nghe TCP trên máy kiểm tra.
ss -lnt

# Phân giải bản ghi từ DNS nội bộ tin cậy.
dig @10.20.10.53 app.corp.example A +time=2 +tries=1

# Kiểm tra ứng dụng qua HTTPS, giới hạn thời gian kết nối.
curl --silent --show-error --output /dev/null \
  --write-out 'HTTP %{http_code} in %{time_total}s\n' \
  --connect-timeout 3 --max-time 8 https://app.corp.example/health
~~~

Các địa chỉ **10.20.0.0/16** và tên miền **corp.example** chỉ là dữ liệu minh họa; cần thay bằng đích thật đã được phê duyệt. Kết quả kiểm thử phải được so với **baseline** trước sự cố hoặc tiêu chí được thống nhất. Nếu cần bắt gói để làm rõ lỗi, hạn chế giao diện, bộ lọc và thời lượng, bảo vệ dữ liệu nhạy cảm trong bản ghi và tuân thủ quy trình lưu chứng cứ.

### Ma trận truy cập phải đạt cả kiểm thử dương và âm

Ví dụ chính sách kết nối sau khôi phục:

| Nguồn | Đích | Mục đích | Kết quả mong đợi |
| --- | --- | --- | --- |
| VLAN ứng dụng sạch | DNS nội bộ, cổng 53 theo chính sách | Phân giải tên | **Allow**, có log theo quy định |
| VLAN ứng dụng sạch | API nội bộ, TCP 443 | Gọi dịch vụ | **Allow**, TLS hợp lệ |
| VLAN ứng dụng sạch | Cơ sở dữ liệu, cổng được chỉ định | Kết nối ứng dụng có xác thực | **Allow** cho đúng host/service identity |
| VLAN người dùng | Cơ sở dữ liệu trực tiếp | Không có nhu cầu nghiệp vụ | **Deny**, có thể điều tra từ log |
| Thiết bị quarantine | VLAN sản xuất | Ngăn tái xâm nhập | **Deny** |
| Tài khoản VPN bị thu hồi | Dịch vụ nội bộ | Chặn phiên nguy cơ | **Deny**, phiên cũ bị vô hiệu hóa |

Thử nghiệm âm (đường **phải bị chặn**) đặc biệt quan trọng: một hệ thống có thể “hết lỗi mạng” chính vì firewall vô tình cho phép quá rộng.

## 5. Quy tắc dừng và quay lui (rollback)

Trước khi mở mỗi nhóm kết nối, lưu lại phiên bản cấu hình đang áp dụng và phiên bản đã biết là an toàn; xác định người có quyền dừng, thao tác quay lui có thể thực hiện và bằng chứng cần giữ. Nếu thay đổi liên quan nhiều thành phần như firewall, BGP, DNS và load balancer, thứ tự rollback phải xét phụ thuộc tương ứng.

Ví dụ về điều kiện **no-go/rollback**:

| Tín hiệu | Phản ứng ưu tiên |
| --- | --- |
| IDS/NDR/EDR xuất hiện lại IOC hoặc hành vi di chuyển ngang có độ tin cậy cao | Dừng vòng triển khai; cô lập nhóm mới mở; kích hoạt điều tra |
| Có truy cập trái phép tới vùng dữ liệu hoặc luồng egress ngoài chính sách | Khôi phục rule/segment chặn; bảo toàn flow logs |
| DNS trả bản ghi sai hoặc chứng thư/định danh không hợp lệ | Rút dịch vụ liên quan khỏi lưu lượng; sửa chuỗi tin cậy trước khi mở lại |
| Route leak, loop, flap, rớt gói hoặc lỗi dịch vụ vượt ngưỡng đã định | Dừng mở rộng; quay về cấu hình mạng ổn định đã xác minh |
| Không còn thu nhận được log hoặc không xác định được tác động | Dừng tăng phạm vi; phục hồi telemetry rồi đánh giá lại |

**Quay lui an toàn** không nhất thiết là bật lại toàn bộ trạng thái trước sự cố: chính trạng thái cũ có thể chứa lỗ hổng. Có thể quay về cấu hình **đã cô lập và kiểm chứng**, giảm lưu lượng, rút route, vô hiệu một phiên hoặc chuyển endpoint sang mạng cách ly. Chỉ khôi phục tiếp sau khi nguyên nhân của lần thất bại đã được xác định và tiêu chí kiểm chứng được cập nhật.

Một mẫu tiêu chí cho mỗi vòng:

~~~text
Change: Mở kết nối [nguồn] -> [đích] : [giao thức/cổng]
Lý do nghiệp vụ: [...]
Chủ dịch vụ / người phê duyệt / người thao tác: [...]
Điều kiện trước thay đổi: tài sản sạch, rule hiện tại, bản sao cấu hình, log
Kiểm thử dương: hành động hợp lệ phải thành công
Kiểm thử âm: hành động không được phép phải bị chặn
Quan sát: độ trễ, tỷ lệ lỗi, flow logs, IDS/EDR/NDR, xác thực
Ngưỡng dừng: [...]     Cửa sổ quan sát: [...]
Rollback: đưa [route/rule/endpoint] về trạng thái an toàn [...]
Bằng chứng và thời điểm kết luận: [...]
~~~

Các ngưỡng như **tỷ lệ lỗi dưới 1% trong 20 phút** hoặc **không có cảnh báo mức nghiêm trọng cao chưa xử lý** chỉ là ví dụ; không phải ngưỡng mặc định cho mọi hệ thống. Cần xác định ngưỡng dựa trên đặc điểm tải, baseline, SLO và năng lực phát hiện của tổ chức.

## 6. Tình huống thực hành: khôi phục sau khi VPN bị lạm dụng

**Bối cảnh.** SOC phát hiện một tài khoản VPN bị chiếm quyền truy cập tới nhiều máy chủ nội bộ qua SMB. Nhóm ứng phó đã ngắt các phiên liên quan, cách ly các máy có dấu hiệu bị ảnh hưởng và chặn kết nối SMB giữa các vùng không có nhu cầu. Một ứng dụng nội bộ cần được phục hồi cho bộ phận vận hành.

**Mục tiêu.** Cho phép người dùng đã xác thực truy cập ứng dụng qua HTTPS, giữ khả năng quan sát và không tái mở đường di chuyển ngang.

| Bước | Thao tác trong phạm vi được phê duyệt | Bằng chứng để chuyển tiếp |
| --- | --- | --- |
| 1. Chuẩn bị | Kiểm tra danh sách máy bị ảnh hưởng, bảo toàn log VPN/firewall/IdP; thu hồi tài khoản/phiên nghi lộ; xác nhận ứng dụng và backend sạch | Chủ sự cố duyệt G0; tài khoản nguy cơ không còn đăng nhập được |
| 2. Quản trị | Kết nối qua mạng quản trị riêng, kiểm tra log và thời gian của hệ thống giám sát | Sự kiện kiểm thử hiển thị đúng trong SIEM |
| 3. Phân đoạn | Khôi phục route từ VLAN ứng dụng tới đúng backend; giữ ACL chặn SMB ngoài các luồng cần thiết | API cần thiết thông; kết nối SMB trái phép vẫn bị chặn |
| 4. Nền tảng | Kiểm tra DNS, chứng thư TLS, IdP và MFA cho tài khoản thử nghiệm | DNS đúng; TLS hợp lệ; người không đủ quyền bị từ chối |
| 5. Ứng dụng | Mở đường HTTPS từ một nhóm người dùng pilot tới ứng dụng sạch; chạy thao tác nghiệp vụ mẫu | Giao dịch thành công, không phát sinh egress hoặc hành vi bất thường |
| 6. Từ xa | Khôi phục truy cập từ xa theo danh tính, trạng thái thiết bị và phạm vi ứng dụng; chưa cho phép truy cập LAN rộng | VPN/ZTNA chỉ tới ứng dụng cho phép; tài khoản cũ bị chặn |
| 7. Mở rộng | Thêm từng nhóm người dùng và theo dõi flow, lỗi ứng dụng, thông báo EDR/NDR | Mỗi vòng đạt ngưỡng; SOC và chủ dịch vụ đồng ý tiếp tục |

Giả sử ở bước 5, NDR phát hiện một máy trong nhóm pilot cố kết nối tới nhiều host qua SMB. Nhóm vận hành **dừng mở rộng**, cách ly máy đó, đối chiếu log và kiểm tra lại sức khỏe các thiết bị khác. Sau khi phân tích và làm sạch, nhóm chạy lại các kiểm thử dương/âm rồi mới xét mở vòng tiếp theo. Đây là cách duy trì tính sẵn sàng từng phần mà không làm mất kiểm soát sự cố.

**Một điểm cần phân biệt:** Nếu sự cố bắt nguồn từ cấu hình sai thông thường, chưa có dấu hiệu xâm nhập, bước xử lý có thể đơn giản hơn; tuy vậy vẫn cần xác nhận nguyên nhân, phạm vi và rollback. Nếu có khả năng kẻ tấn công còn duy trì quyền truy cập, không coi phục hồi connectivity là bằng chứng sự cố đã kết thúc.

## 7. Playbook triển khai ngắn gọn

~~~text
INPUT:
    danh sách tài sản và vùng mạng
    sơ đồ phụ thuộc, RTO/RPO, ma trận kết nối được phép
    bằng chứng điều tra, trạng thái sạch, baseline và chính sách

FOR mỗi giai đoạn theo sơ đồ phụ thuộc:
    1. Xác nhận điều kiện bảo mật và người phê duyệt.
    2. Chốt chính xác nguồn, đích, port, danh tính và quy mô mở.
    3. Lưu cấu hình, nhật ký và kế hoạch rollback.
    4. Áp dụng thay đổi nhỏ, có kiểm soát và ghi thời điểm.
    5. Kiểm thử dương, kiểm thử âm, kiểm thử nghiệp vụ.
    6. Quan sát telemetry và đối chiếu ngưỡng.
    7. IF thất bại hoặc có dấu hiệu tái xâm nhập:
           dừng triển khai, quay về trạng thái an toàn,
           bảo toàn chứng cứ, điều tra và đánh giá lại.
       ELSE:
           ghi nhận PASS và mới mở giai đoạn tiếp theo.

OUTPUT:
    trạng thái từng dịch vụ/vùng, bằng chứng kiểm chứng,
    nhật ký thay đổi, rủi ro tồn dư, người chịu trách nhiệm.
~~~

Khi bàn giao, cần trả lời được các câu hỏi: **Ai** đã phê duyệt? **Kết nối nào** được mở lại và vì sao? **Thiết bị nào** còn bị cách ly? **Kiểm thử nào** chứng minh hệ thống hoạt động và chính sách vẫn đúng? **Tín hiệu nào** sẽ buộc dừng hoặc tái cô lập? Những câu trả lời này giúp ca trực sau tiếp tục xử lý mà không phải suy đoán.

## 8. Lỗi thường gặp và cách tránh

- **Mở hết VLAN, VPN hoặc firewall rule cùng lúc:** khó khoanh vùng lỗi và có thể tái mở đường tấn công. Hãy khôi phục từng luồng theo phụ thuộc, kiểm tra chính sách âm.
- **Dựa hoàn toàn vào ping hoặc HTTP 200:** không phát hiện sai quyền, sai DNS, luồng rò rỉ dữ liệu hoặc chức năng nghiệp vụ lỗi. Hãy kiểm thử theo nhiều lớp, gồm xác thực và ủy quyền.
- **Khôi phục bản sao lưu chưa kiểm tra:** có thể đưa trở lại tài khoản, cấu hình độc hại hoặc dữ liệu hỏng. Hãy xác minh nguồn, thời điểm, tính toàn vẹn và thực hiện phục hồi có giám sát.
- **Bỏ qua đồng bộ thời gian và DNS:** làm lỗi chứng thư, đăng nhập và sai lệch dòng thời gian điều tra. Hãy xác nhận các dịch vụ nền tảng trước khi cho ứng dụng nhận tải.
- **Dỡ bỏ cách ly khi EDR báo “healthy” một lần:** trạng thái thiết bị có thể chưa phản ánh toàn bộ nguyên nhân sự cố. Kết hợp kiểm tra hiện trạng, dấu vết điều tra và xác nhận từ nhóm an ninh.
- **Không có điểm dừng:** khi xuất hiện bất thường, nhóm vận hành không biết ai quyết định hay quay về cấu hình nào. Gắn mọi vòng khôi phục với chủ sở hữu, ngưỡng và rollback rõ ràng.

## 9. Tự kiểm tra kiến thức

1. Vì sao cần khôi phục kênh quản trị tin cậy và telemetry trước khi mở lại nhiều luồng sản xuất?
2. Nếu ứng dụng cần DNS, NTP và IdP, nhưng IdP lại cần DNS, bạn sẽ xác định chuỗi phụ thuộc và phương án khôi phục tối thiểu ra sao?
3. Hãy nêu một phép kiểm thử **được phép** và một phép kiểm thử **phải bị chặn** khi mở kết nối từ VLAN người dùng đến ứng dụng.
4. Khi VPN đã kết nối thành công nhưng máy khách chưa truy cập được ứng dụng, cần kiểm tra những lớp nào trước khi thay firewall rule?
5. Nếu hệ thống hoạt động ổn nhưng mất log firewall ngay sau khi mở rộng 25% người dùng, nên chuyển ngay sang 100% hay kích hoạt tiêu chí dừng? Vì sao?

**Gợi ý trả lời:** (1) Để có quyền quản trị tin cậy, theo dõi kết quả thay đổi và phát hiện tái xâm nhập; (2) dựng đường quản trị/tập dịch vụ nền tảng độc lập, giải quyết vòng phụ thuộc rồi kiểm chứng lại; (3) cho người hợp lệ qua HTTPS, chặn truy cập cơ sở dữ liệu trực tiếp; (4) kiểm tra endpoint, DNS, route, NAT, TCP, TLS, danh tính và ứng dụng; (5) dừng tăng phạm vi cho đến khi phục hồi quan sát vì không đủ bằng chứng khôi phục an toàn.

**Ghi nhớ:** Kết nối được phục hồi theo thứ tự an toàn khi **nền tảng tin cậy → mạng phân đoạn → dịch vụ phụ thuộc → kết nối biên → người dùng** đều được đưa vào hoạt động theo từng cổng kiểm soát, với khả năng quan sát và quay lui xuyên suốt. Thứ tự chi tiết phụ thuộc kiến trúc; yêu cầu chứng minh **đúng chức năng, đúng quyền và không tái mở đường xâm nhập** luôn được giữ nguyên.
