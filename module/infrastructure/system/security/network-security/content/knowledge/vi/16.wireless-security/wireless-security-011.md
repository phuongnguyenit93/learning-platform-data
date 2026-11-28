# Site survey và signal leakage: khảo sát vùng phủ Wi-Fi gắn với an ninh mạng

Một văn phòng có Wi-Fi mạnh ở mọi bàn làm việc nhưng tín hiệu của mạng nhân viên cũng có thể thu được ở sảnh chung, bãi đỗ xe hoặc bên ngoài cửa kính. Có phải dữ liệu đã bị lộ? **Chưa chắc.** Tín hiệu vô tuyến vượt ranh giới vật lý là hiện tượng truyền sóng bình thường; **rò rỉ tín hiệu (signal leakage)** không đồng nghĩa một người bên ngoài đã giải mã được lưu lượng, xác thực thành công hoặc truy cập tài nguyên nội bộ. Tuy nhiên, vùng phủ không được quản lý có thể mở rộng nơi kẻ tấn công có cơ hội quan sát khung Wi-Fi, thử kết nối, gây nhiễu hoặc tìm điểm cấu hình yếu.

**Site survey** là hoạt động khảo sát thực tế và/hoặc mô phỏng để hiểu vùng phủ, chất lượng tín hiệu, nhiễu, khả năng chuyển vùng và năng lực phục vụ của mạng không dây. Trong ngữ cảnh an ninh, khảo sát phải trả lời đồng thời hai câu hỏi: **người dùng hợp lệ có kết nối tốt ở nơi họ cần không?** và **mạng đang phát sóng ra những vùng, kênh và thiết bị ngoài dự kiến nào?**

Trong mô-đun **SECURITY_NETWORK_SECURITY**, site survey kết nối thiết kế Wi-Fi với phân đoạn mạng, firewall, NAC/802.1X, IDS/IPS, xác thực kết nối, DNS, VPN và kiến trúc cloud. Bài học tập trung vào **khảo sát được ủy quyền, cách diễn giải dữ liệu RF, thiết kế bảo vệ nhiều lớp và giám sát sau triển khai**, thay vì giả định có thể dùng một chỉ số sóng để kết luận an toàn.

> **Nguyên tắc:** Tối ưu vùng phủ không thay thế mã hóa, xác thực và phân quyền. Không có thiết kế Wi-Fi thực tế nào bảo đảm sóng dừng chính xác ở ranh giới tường, cửa hay đất sở hữu. Chỉ khảo sát nơi được phép và không phát tín hiệu gây nhiễu, giả mạo AP hoặc chủ động ngắt kết nối thiết bị.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **coverage, capacity, roaming, interference, signal leakage** và rủi ro truy cập mạng không được phép.
2. Giải thích các chỉ số **RSSI/dBm, SNR, noise floor, channel utilization, retry, packet loss và throughput** cùng giới hạn đo lường.
3. So sánh **predictive survey, passive survey, active survey và spectrum analysis**; chọn phương pháp phù hợp với nhiệm vụ.
4. Thiết kế khảo sát trong nhà và **vành đai bên ngoài được phép tiếp cận**, gồm sơ đồ vị trí, thiết bị đo, tiêu chí đạt và cách lưu bằng chứng.
5. Phân tích ảnh hưởng của **AP placement, antenna, công suất phát, kênh, bề rộng kênh, vật liệu công trình và client uplink** tới vùng phủ/rò sóng.
6. Liên kết kết quả RF với **WPA2/WPA3-Enterprise, 802.1X, PMF, NAC, VLAN/VRF, firewall và WIDS/WIPS**.
7. Điều tra trường hợp có SSID công ty xuất hiện ngoài phạm vi, AP giả mạo, cấu hình công suất sai hoặc thay đổi tòa nhà.
8. Xây dựng **ma trận kiểm thử, báo cáo khảo sát và kế hoạch giám sát/khảo sát lại** có thể kiểm chứng.

## 2. Site survey giải quyết những vấn đề nào?

Không nên đánh đồng “thiết bị thấy SSID” với “mạng đã sẵn sàng và an toàn”. Wi-Fi có thể quảng bá SSID nhưng không đủ chất lượng cho cuộc gọi, không cấp được IP, không xác thực được 802.1X hoặc không đi tới DNS/gateway theo chính sách.

| Khía cạnh | Câu hỏi khảo sát | Hệ quả nếu bỏ qua |
|---|---|---|
| **Coverage** | Ở những vị trí cần phục vụ, thiết bị có tín hiệu đủ để làm việc không? | Điểm chết, kết nối không ổn định |
| **Capacity** | Số client và lượng traffic đồng thời có được phục vụ không? | Bão hòa airtime, latency và retry tăng |
| **Roaming** | Khi di chuyển giữa các AP, ứng dụng có duy trì chất lượng không? | Cuộc gọi/video hoặc phiên giao dịch gián đoạn |
| **Interference** | Có nhiễu từ mạng cùng/khác kênh hoặc thiết bị phi Wi-Fi không? | Giảm tốc độ hữu dụng và tăng mất gói |
| **Signal leakage** | Ở đâu ngoài vùng mục tiêu còn nhận được tín hiệu AP? | Bề mặt tiếp cận RF rộng hơn dự kiến |
| **Security posture** | Các AP, SSID, cơ chế mã hóa và vùng truy cập có đúng thiết kế không? | Rogue AP, cấu hình yếu, phân đoạn sai |
| **Operational observability** | Có biết AP nào phục vụ client và tại thời điểm nào không? | Khó truy vết sự cố hoặc phát hiện thay đổi bất thường |

**Khảo sát vùng phủ** là tập hợp phép đo vô tuyến. **Đánh giá bảo mật Wi-Fi** còn phải xác minh xác thực, quyền truy cập, đường mạng, quản lý AP và ứng dụng. Hai hoạt động bổ trợ nhưng không thay thế nhau.

### Phân biệt signal leakage và data leakage

| Thuật ngữ | Điều được quan sát | Có thể kết luận gì? |
|---|---|---|
| **RF/signal leakage** | Một SSID/BSSID hoặc năng lượng RF của AP được nhận ngoài vùng cần phục vụ | Sóng tới vùng đó; **chưa chứng minh** người ngoài đã vào mạng |
| **Information disclosure qua quản lý Wi-Fi** | Ví dụ tên SSID, loại bảo vệ hoặc metadata khung được quảng bá | Có thể lộ thông tin cấu hình/định danh môi trường |
| **Unauthorized association** | Thiết bị không được phép hoàn tất bước liên kết với AP | Cần xác minh tiếp kết quả xác thực, VLAN và quyền mạng |
| **Unauthorized access** | Thiết bị hoặc tài khoản không được phép truy cập được tài nguyên | Sự cố kiểm soát truy cập, cần bằng chứng từ NAC/firewall/app |
| **Data exfiltration** | Thông tin không được phép thật sự bị chuyển ra ngoài | Cần chứng cứ dữ liệu, đường truyền, tài sản và ngữ cảnh; không suy chỉ từ RSSI |

**Wi-Fi là môi trường vô tuyến chia sẻ.** Phòng thủ không nên dựa vào kỳ vọng tín hiệu không bao giờ lọt ra ngoài mà cần bảo đảm thiết bị/tài khoản không được phép **không thể xác thực hoặc truy cập tài nguyên** dù thu được tín hiệu.

## 3. Những khái niệm RF cần có trước khi khảo sát

### 3.1. Băng tần 2,4 GHz, 5 GHz và 6 GHz

| Băng tần | Đặc điểm thường gặp | Hệ quả cho survey |
|---|---|---|
| **2,4 GHz** | Phổ biến, khả năng xuyên một số vật cản thường tốt hơn tần số cao, số kênh không chồng lấn hạn chế | Có thể thu được xa hơn ngoài tòa nhà; dễ gặp nhiễu/đông client |
| **5 GHz** | Nhiều lựa chọn kênh hơn 2,4 GHz trong phạm vi quy định, có thể hỗ trợ băng thông cao | Khảo sát kỹ tường/kính, channel utilization và DFS nếu kênh sử dụng chịu yêu cầu này |
| **6 GHz** | Hỗ trợ các triển khai Wi-Fi mới trên những thiết bị/quốc gia cho phép | Kiểm tra client compatibility, giới hạn công suất/kiểu AP, quy định địa phương và tổn hao vật liệu |

Đặc điểm truyền sóng không chỉ phụ thuộc tần số: **vật liệu tường, kính phủ kim loại, trần, ống kỹ thuật, vị trí antenna, phản xạ, công suất, nhiễu và thiết bị client** đều ảnh hưởng. Không thể kết luận rằng băng tần cao chắc chắn “không lọt ra ngoài”.

**Quy định về kênh, công suất EIRP, DFS và vận hành trong/ngoài nhà khác nhau theo quốc gia và loại thiết bị.** Trên một số dải/tình huống 6 GHz còn có cơ chế kiểm soát phổ phù hợp. Không chuyển nguyên thông số kênh và công suất từ tài liệu của nước khác sang triển khai thực tế nếu chưa kiểm tra quy định hiện hành.

### 3.2. RSSI và dBm

**Received Signal Strength Indicator (RSSI)** là ước lượng mức tín hiệu nhận được do thiết bị đo cung cấp. Trong nhiều công cụ khảo sát, mức thu được hiển thị bằng **dBm** (đơn vị công suất theo thang logarit).

Ví dụ:

~~~text
-50 dBm : Tín hiệu thu mạnh hơn
-67 dBm : Tín hiệu yếu hơn -50 dBm
-80 dBm : Tín hiệu yếu hơn -67 dBm
~~~

Với các số âm, **-50 dBm mạnh hơn -70 dBm**. Tuy nhiên, RSSI không phải số đo tuyệt đối nhất quán giữa mọi chipset/driver, và **tín hiệu mạnh không bảo đảm chất lượng** khi có nhiễu, contention, lỗi cấu hình hoặc hệ thống backend bị nghẽn.

### 3.3. Noise floor và SNR

**Noise floor** là mức năng lượng nền mà bộ thu quan sát trong băng/kênh tương ứng, theo cách đo của thiết bị. **Signal-to-Noise Ratio (SNR)** là mức chênh lệch giữa tín hiệu mong muốn và nhiễu, thường tính bằng **dB**.

~~~text
Ví dụ minh họa, cùng điểm đo:

Signal level: -62 dBm
Noise floor:  -92 dBm
SNR xấp xỉ:   30 dB
~~~

Phép trừ dBm như trên là minh họa cho **chênh lệch mức công suất** trong điều kiện phép đo tương thích. SNR công cụ hiển thị có thể khác tùy phương pháp, và không phản ánh đầy đủ nhiễu đồng kênh/collision do thiết bị Wi-Fi khác.

### 3.4. Airtime, utilization và retry

- **Channel utilization:** tỷ lệ thời gian một kênh bị bận theo cách thiết bị đo định nghĩa; cần phân biệt Wi-Fi traffic và năng lượng phi Wi-Fi.
- **Airtime:** tài nguyên thời gian phát trên môi trường vô tuyến; nhiều client yếu có thể dùng nhiều airtime cho cùng lượng dữ liệu.
- **Retry/retransmission:** các khung phải gửi lại, có thể tăng do nhiễu, đụng độ truyền, client di chuyển hoặc vấn đề radio.
- **Data rate/MCS:** tốc độ PHY tại thời điểm đo; **không đồng nghĩa application throughput**.
- **Packet loss, latency, jitter:** kết quả end-to-end quan trọng với thoại, video và ứng dụng tương tác.

**Không có một ngưỡng dBm hay SNR duy nhất bảo đảm mọi ứng dụng hoạt động tốt.** Phải xác định yêu cầu trước, sau đó đo từ những loại client thực tế.

## 4. Bốn dạng khảo sát thường gặp

### 4.1. Predictive survey: mô phỏng trước triển khai

Người thiết kế nhập mặt bằng, vật liệu, vị trí AP dự kiến, antenna, băng tần và công suất vào công cụ RF planning để **ước lượng vùng phủ**.

**Ưu điểm:** so sánh phương án nhanh, hữu ích khi xây công trình mới và trước khi lắp thiết bị.

**Giới hạn:** bản vẽ có thể không phản ánh chính xác kính phủ kim loại, cửa, kệ hàng, đồ nội thất, số người, thiết bị điện hoặc nguồn nhiễu. **Mô phỏng không thay thế khảo sát sau lắp đặt**.

### 4.2. Passive survey: quan sát beacon và môi trường

Thiết bị khảo sát nghe các beacon/khung quản lý và những tín hiệu sẵn có trong phạm vi được phép để thống kê **SSID, BSSID, kênh, băng tần, RSSI và mật độ AP**; thông tin chính xác phụ thuộc adapter và công cụ.

**Ưu điểm:** giảm tác động lên mạng và có ích để quan sát nhiều AP, cả AP không thuộc tổ chức.

**Giới hạn:** không tự chứng minh DHCP, DNS, 802.1X, throughput hoặc ứng dụng hoạt động. BSSID/SSID quan sát được cũng có thể bị giả mạo; không nên tự gán quyền sở hữu dựa vào tên SSID.

### 4.3. Active survey: thử dùng mạng được ủy quyền

Thiết bị khảo sát **kết nối với SSID do tổ chức sở hữu và cấp quyền thử**, thực hiện các phép đo được phê duyệt như association/authentication, latency, loss, throughput tải thấp và roaming.

**Ưu điểm:** phản ánh hiệu quả sử dụng thật của một client/app.

**Giới hạn:** kết quả phụ thuộc adapter, driver, OS, phiên bản phần mềm, server đo và tải nền; một lần speed test không đại diện toàn bộ khách hàng. Phải giới hạn lưu lượng thử và tránh làm gián đoạn dịch vụ production.

### 4.4. Spectrum analysis: quan sát năng lượng RF

Thiết bị phân tích phổ phù hợp có thể tìm hoạt động **không theo chuẩn Wi-Fi** gây nhiễu, ví dụ thiết bị không dây khác, nguồn phát công nghiệp hoặc năng lượng bất thường trong dải. Một adapter Wi-Fi thông thường **không thay thế hoàn toàn spectrum analyzer chuyên dụng**.

**Không được phát nhiễu, jamming hoặc thử gây gián đoạn để “kiểm tra khả năng chống nhiễu”.** Phân tích phổ trong bài là quan sát thụ động tại những vị trí được phép.

### Bảng lựa chọn phương pháp

| Mục tiêu | Phương pháp phù hợp | Bằng chứng chính |
|---|---|---|
| Lên phương án đặt AP trước thi công | Predictive + kiểm tra bản vẽ | Mô hình coverage/capacity dự kiến |
| Đánh giá vùng phủ và AP cạnh tranh | Passive | RSSI/SSID/BSSID/channel theo vị trí |
| Chứng minh ứng dụng hoạt động trên Wi-Fi | Active có phép | Latency/loss/throughput/roam/application success |
| Tìm nguồn nhiễu phi Wi-Fi | Spectrum analysis | RF spectrum/occupancy theo thời gian |
| Xác định tín hiệu công ty ra ngoài tòa nhà | Passive khảo sát perimeter được phép | RSSI theo điểm và AP identity đã xác minh |
| Xác minh phân đoạn Guest/Employee | Active network-security test có phép | 802.1X/VLAN/IP/firewall/DNS/app logs |

## 5. Chuẩn bị site survey: điều gì phải được thống nhất?

Trước khi đi đo, cần có **phạm vi, mục tiêu, người phê duyệt và tiêu chí nghiệm thu**.

1. **Ranh giới:** các tầng, khu vực làm việc, thang máy, sảnh, khu công cộng, bãi xe và những điểm ngoài nhà mà nhóm khảo sát **được phép tiếp cận**.
2. **Bản vẽ:** mặt bằng, độ cao trần, tường, cửa kính, vách kim loại, thang máy, kho và những vật cản lớn.
3. **Inventory:** AP ID, serial, vị trí, switch port, controller/site, SSID, BSSID, radio band, antenna, công suất và kênh hiện hành.
4. **Loại client:** laptop, điện thoại, máy quét kho, IoT, thiết bị hỗ trợ 2,4/5/6 GHz; chính sách BYOD/Guest.
5. **Nhu cầu nghiệp vụ:** gọi thoại, hội nghị video, barcode scan, API, truy cập VPN, ứng dụng realtime.
6. **Mục tiêu bảo mật:** vùng nào không muốn tạo vùng phủ mạnh; SSID nào chứa tài nguyên nhạy cảm; mạng guest phải tách khỏi internal.
7. **Điều kiện đo:** giờ cao điểm/thấp điểm, số người, trạng thái cửa, kệ hàng, triển lãm, thiết bị công nghiệp.
8. **Nguồn số liệu:** survey adapter, controller/WLAN analytics, RADIUS/NAC, firewall, packet capture đã được cấp phép và log ứng dụng.
9. **Quyền truy cập dữ liệu:** không lưu mật khẩu, tài liệu riêng tư hoặc payload người dùng chỉ để đo tín hiệu.
10. **Kế hoạch khôi phục:** mọi điều chỉnh AP/radio sau khảo sát phải có thay đổi được phê duyệt, baseline và rollback.

### Xây nhóm tiêu chí nghiệm thu theo từng khu

Ví dụ một công ty có thể đặt mục tiêu tham khảo cho khu thoại/video là **RSSI ít nhất khoảng -67 dBm**, **SNR khoảng 25 dB trở lên**, và roaming không gây lỗi ứng dụng. Đây **chỉ là mốc minh họa hay dùng trong thiết kế**, không phải tiêu chuẩn bắt buộc: thiết bị, PHY, băng tần, density và yêu cầu ứng dụng quyết định ngưỡng thực.

Với hành lang/vùng chuyển tiếp, quan trọng có thể là **không đứt phiên trong lúc di chuyển**. Với kho nhiều kệ kim loại, cần đo trực tiếp ở cao độ thiết bị quét thực tế. Với vùng ngoài ranh giới, điều kiện cần đo là **mức tín hiệu và khả năng truy cập theo góc nhìn security**, không mặc định yêu cầu “RSSI bằng 0”.

## 6. Thiết kế tuyến khảo sát và điểm đo

Khảo sát tốt cần tránh những phép đo tùy hứng chỉ tại một vài bàn gần AP. Nên dùng **đường khảo sát đã định, tọa độ hoặc điểm tham chiếu rõ ràng, chiều cao và hướng cầm thiết bị nhất quán**.

~~~text
                TÒA NHÀ VĂN PHÒNG (sơ đồ minh họa)

          +--------------------------------------+
          | Phòng họp      Hành lang      Kho    |
          |     P1          P2            P3     |
          |    [AP-A]                     [AP-B]  |
          |                                      |
          |  Khu nhân viên        Sảnh kính      |
          |    P4      P5            P6          |
          +--------------------+-----------------+
                               |
                        Cửa ra / lối chung
                               |
                        P7: phía ngoài
                               |
                        P8: bãi xe có phép

   P1–P6: đo coverage/capacity bên trong
   P7–P8: đo signal leakage ở perimeter hợp pháp
~~~

### Tại từng điểm ghi gì?

| Nhóm | Trường cần lưu |
|---|---|
| Vị trí | Site, tầng, khu, point ID, tọa độ tương đối, độ cao thiết bị, indoor/outdoor |
| Thời gian | Timestamp, timezone, giờ cao/thấp điểm, điều kiện sử dụng |
| Thiết bị đo | Model, OS, adapter/driver, phiên bản công cụ, hướng/độ cao antenna |
| RF | Băng tần, channel, channel width, RSSI, noise/SNR nếu công cụ hỗ trợ |
| AP | SSID, BSSID, AP ID đã xác minh, radio band, policy/zone |
| Chất lượng | Retry, utilization, latency, loss, throughput hoặc application success nếu có đo |
| Security | Loại bảo vệ được công bố, BSSID chưa rõ, SSID giống công ty, khu ngoài ranh giới |
| Kết luận | Mức tin cậy, sai khác so với baseline, người rà soát, đề xuất |

**Một thiết bị hoặc phép đo khác nhau có thể cho RSSI khác nhau tại cùng vị trí.** Nếu cần so sánh trước/sau khi chỉnh công suất, dùng thiết bị đo/điều kiện nhất quán và ghi rõ các nguồn sai lệch.

### Sai lầm thường gặp trong khảo sát thực địa

- Chỉ đo khi văn phòng trống và cửa luôn mở, không phản ánh giờ sử dụng thật.
- Cầm máy sát người hoặc xoay hướng antenna khác nhau nhưng không ghi chú.
- Dùng laptop công suất anten tốt làm đại diện cho điện thoại hoặc máy quét cầm tay.
- Chỉ đo RSSI của AP đang kết nối, không xem các AP cạnh tranh và nhiễu.
- Không kiểm tra xem khách hàng hợp lệ có nhận **IP, DNS, default route và quyền truy cập** đúng sau liên kết hay không.
- Gắn tọa độ sai trên bản vẽ, dẫn đến heatmap khó giải thích hoặc quyết định đổi vị trí AP nhầm.

## 7. Signal leakage: đo đúng hiện tượng và ranh giới

**Signal leakage** trong ngữ cảnh Wi-Fi thường chỉ việc năng lượng RF/khung phát của AP được thu ở những khu vực **ngoài vùng phục vụ dự kiến**. Nó có thể xảy ra qua kính, cửa, tường mỏng, hành lang, mái, bãi xe hoặc không gian mở.

### Những nguyên nhân phổ biến

1. AP đặt gần cửa sổ, vách kính hoặc lối ra hơn mức cần thiết.
2. Antenna omnidirectional phát năng lượng ra hướng không phục vụ client.
3. Công suất phát quá cao so với mật độ AP, khiến cell mở rộng ra bên ngoài.
4. Vật liệu tường/cửa giảm suy hao ít hơn mô hình dự đoán.
5. Antenna định hướng sai góc hoặc thiết bị được lắp khác với thiết kế.
6. AP mới xuất hiện hoặc radio tự điều chỉnh channel/power sau tối ưu tự động.
7. Băng tần 2,4 GHz đi xa hơn kỳ vọng trong một số khu vực và điều kiện.
8. Một AP hoặc repeater không nằm trong inventory phát lại SSID/cell ở vị trí ngoài dự kiến.

**Không được kết luận “có leakage là có tấn công”**. Một người đứng ở khu công cộng vẫn có thể nhìn thấy tên mạng của hàng chục tổ chức; đó là đặc tính RF. Rủi ro cần được đánh giá theo **mức tín hiệu, phạm vi, loại SSID, phương thức xác thực, danh tính AP và đường truy cập phía sau**.

### Vùng quan sát và vùng thực thi quyền

~~~text
              BÊN TRONG TÒA NHÀ             BÊN NGOÀI

   [Corporate AP] ------ RF signal -----> [Điểm P7]
          |                                Thấy SSID/RSSI
          |                                     |
          |                              Chưa xác thực
          v                                     |
 [802.1X / RADIUS] <---- chỉ khi client được phép tham gia ----
          |
    [Policy / VLAN]
          |
    [Firewall / NAC]
          |
   [Ứng dụng có IAM]

 Thu được sóng ≠ có khóa mạng ≠ được vào VLAN ≠ được dùng ứng dụng.
~~~

Signal leakage là **điều kiện phơi bày vùng tiếp cận RF**, không phải bằng chứng chứng minh các lớp bảo vệ phía sau đã thất bại.

## 8. Các biện pháp giảm signal leakage có cân nhắc

### 8.1. AP placement và antenna pattern

- Đặt AP để **phục vụ khu có người dùng**, tránh hướng antenna chính trực tiếp ra cửa kính/bãi xe nếu không cần.
- Dùng antenna có **hướng phát phù hợp** ở hành lang, nhà kho hoặc vùng biên nếu được thiết kế cho thiết bị đó.
- Kiểm tra **antenna gain, hướng lắp, vật cản và quy định EIRP**; không được tự tăng gain vượt giới hạn pháp lý.
- Đo cả **vùng trong cần phục vụ** trước khi điều chỉnh; giảm leakage bằng cách làm mất phủ sóng phòng họp không phải kết quả tốt.

### 8.2. Công suất phát và cell size

Giảm công suất phát có thể thu hẹp phạm vi thu được tín hiệu từ AP, nhưng:

- **Wi-Fi là liên lạc hai chiều.** AP phát rất mạnh vẫn không giúp client có công suất phát yếu gửi trở lại tốt.
- Giảm công suất quá nhiều gây **coverage hole, roaming bất ổn và retry**.
- Quản lý công suất tự động (RRM) có thể thay đổi cấu hình sau thời gian; phải theo dõi cả chính sách và mức đang hoạt động.
- Cell nhỏ quá mức có thể làm nhiều AP/chuyển vùng cùng lúc và tăng chi phí vận hành.

**Thiết kế đúng phải kiểm tra đường xuống AP → client và đường lên client → AP**, đồng thời xem SNR, retries và ứng dụng thật.

### 8.3. Kênh, bề rộng kênh và co-channel interference

Kênh rộng có thể tăng tốc độ PHY trong điều kiện phù hợp, nhưng sử dụng nhiều phổ hơn và có thể tạo contention trong môi trường đông AP. Ở khu mật độ cao, chọn bề rộng kênh hẹp hơn trong phạm vi quy định đôi khi cải thiện năng lực dùng chung.

- **Co-channel interference/contention:** nhiều mạng sử dụng cùng kênh và tranh airtime; không phải mọi trường hợp là tín hiệu điện tử “phá” gói.
- **Adjacent-channel interference:** hoạt động từ kênh lân cận chồng lấn ảnh hưởng khả năng thu; đặc biệt cần chú ý kế hoạch 2,4 GHz.
- **DFS/radar response:** trên những kênh chịu yêu cầu DFS, AP có thể phải thay đổi hoạt động khi phát hiện tín hiệu radar theo quy định.
- **Channel plan:** phải xét các AP cùng tổ chức và môi trường lân cận; channel đẹp trên bản vẽ chưa chắc đẹp vào giờ đông.

Chỉ số kênh và công suất là **biến tối ưu có ràng buộc**, không phải “càng thấp càng an toàn” hoặc “càng cao càng tốt”.

### 8.4. Không dùng biện pháp can thiệp trái phép

**Không sử dụng jammer, phát deauthentication hàng loạt, giả mạo AP hoặc can thiệp thiết bị lân cận** để kiểm tra leakage. Những hành động ấy có thể gây gián đoạn người dùng, ảnh hưởng tổ chức khác và vi phạm quy định. Khảo sát được phép là đo đạc và kiểm chứng chính sách, không phải tấn công vào người sử dụng Wi-Fi.

## 9. Mã hóa và xác thực quan trọng hơn “giấu sóng”

Dù giảm công suất và tối ưu vị trí, tín hiệu Wi-Fi vẫn có thể đi ra ngoài. Kiểm soát truy cập cần được thiết kế **như thể người ngoài có thể thu các khung quản lý và nhìn thấy tên mạng**.

### So sánh cơ chế bảo vệ

| Cơ chế | Vai trò | Điều không nên nhầm |
|---|---|---|
| **WPA2-Enterprise / WPA3-Enterprise** | Xác thực mạng qua 802.1X/EAP trong thiết kế phù hợp, hỗ trợ chính sách danh tính | Cần cấu hình phương thức EAP và xác minh máy chủ đúng; không chỉ bật chữ “Enterprise” |
| **802.1X / RADIUS** | Xác thực và áp chính sách truy cập cho thiết bị/người dùng | Không thay thế quyền ở ứng dụng; chính sách phụ thuộc hệ thống IAM/NAC |
| **EAP-TLS** | Sử dụng chứng chỉ để xác thực phù hợp chính sách triển khai | Vẫn cần kiểm soát PKI, cấp/thu hồi chứng chỉ và trust anchors |
| **Protected Management Frames (PMF, 802.11w)** | Bảo vệ những khung quản lý robust được chuẩn hỗ trợ sau khi thiết lập bảo mật phù hợp | Không che beacon/SSID, không ngăn toàn bộ gây nhiễu RF |
| **WPA-Personal / PSK hoặc SAE** | Có thể phù hợp mạng nhỏ/khách/thiết bị theo yêu cầu | Chia sẻ bí mật rộng gây khó thu hồi theo từng user; cần đánh giá khả năng WPA3 |
| **OWE / Enhanced Open** | Bảo vệ mật mã trên liên kết không dùng xác thực danh tính như Enterprise | Không chứng thực tổ chức sở hữu AP, không cấp quyền truy cập tài nguyên riêng |
| **Hidden SSID** | Hạn chế quảng bá tên trong một số cách hiển thị | Không phải cơ chế bảo mật mạnh; tên vẫn có thể bị suy ra trong tương tác |
| **MAC allowlist** | Hỗ trợ một số quy trình vận hành | MAC có thể giả mạo và không phải danh tính an toàn |

Với mạng doanh nghiệp có dữ liệu nhạy cảm, **WPA2/WPA3-Enterprise kết hợp phương thức EAP và validation được cấu hình chuẩn**, quản lý chứng chỉ/danh tính và phân đoạn là nền tảng. Phải kiểm thử khả năng hỗ trợ của client (đặc biệt IoT/thiết bị cũ), không chuyển bảo mật toàn hệ thống sang chế độ yếu chỉ để một nhóm client hoạt động.

### Không để tên SSID trở thành thông tin nhạy cảm

SSID thường có thể quan sát được từ môi trường vô tuyến. Không nên đưa **tên dự án mật, mật khẩu, sơ đồ tổ chức chi tiết hoặc vị trí máy chủ nhạy cảm** vào SSID với kỳ vọng người ngoài không nhìn thấy. Đổi hoặc ẩn SSID không phải cách thay thế 802.1X, WPA và phân quyền.

## 10. Rogue AP, Evil Twin và thiết bị không được quản lý

**Rogue AP** là điểm truy cập không được tổ chức phê duyệt trong phạm vi chính sách của mạng mình. Nó có thể là:

- Router cá nhân cắm trái phép vào mạng nội bộ.
- Thiết bị phát hotspot theo thói quen của nhân viên.
- AP được lắp hợp lệ nhưng chưa ghi vào inventory.
- Thiết bị giả mạo SSID hoặc hình thức bên ngoài của mạng doanh nghiệp (**Evil Twin**) để dụ client kết nối.

Một AP có **cùng SSID** hoặc BSSID giống một AP công ty **không tự chứng minh** nó thuộc hệ thống quản lý: SSID/BSSID có thể bị giả mạo. Ngược lại, một SSID lạ gần tòa nhà có thể là của hàng xóm hợp pháp, không phải rogue AP của tổ chức.

### Cách điều tra an toàn

1. So sánh SSID/BSSID và thông số radio với **WLAN controller inventory**.
2. Xác định AP có thật sự **nối vào hạ tầng dây nội bộ** hay chỉ phát sóng lân cận.
3. Đối chiếu switch MAC/port, NAC/RADIUS, cấu hình controller và change ticket.
4. Kiểm tra EAP/server certificate validation trên client được quản lý; tránh cho client tự động tin AP chỉ vì SSID trùng.
5. Chỉ định chủ sở hữu xác minh vị trí và mục đích sử dụng.
6. Nếu nghi phishing/cấp thông tin xác thực, xử lý qua quy trình security incident, hỗ trợ user và thu hồi chứng chỉ/tài khoản khi cần.

**Không nên tự phát deauth, gây nhiễu hoặc đánh sập AP lạ** chỉ vì nó hiện trong danh sách quét. Việc xử lý thiết bị ngoài quyền quản lý phải tuân theo quy trình pháp lý và liên hệ chủ sở hữu.

### WIDS và WIPS hỗ trợ ra sao?

**Wireless IDS (WIDS)** có thể phân tích các sự kiện RF/WLAN và tạo cảnh báo như AP không rõ, cấu hình bảo mật thay đổi hoặc liên kết bất thường. **Wireless IPS (WIPS)** có thể có cơ chế giảm thiểu trong những sản phẩm/hệ thống được phép vận hành. Tuy nhiên, tính năng chặn chủ động bằng radio cần được **đánh giá pháp lý, tương thích và rủi ro gián đoạn**, không mặc định kích hoạt đối với mọi SSID lạ.

## 11. Phân đoạn mạng Wi-Fi và NAC

Một thiết bị hoàn tất kết nối radio chưa nên mặc nhiên được truy cập toàn bộ LAN. Chính sách nên tách **Employee, Guest, BYOD, IoT, Management** bằng VLAN/VRF, role-based ACL, firewall hoặc microsegmentation phù hợp.

~~~text
                 [Managed Access Points]
                          |
                  [WLAN Controller]
                          |
                  [802.1X / NAC / RADIUS]
                          |
             +------------+-------------+
             |            |             |
          Employee       Guest          IoT
             |            |             |
        [Corp VLAN]   [Guest Zone]   [IoT Zone]
             |            |             |
        [Firewall / Identity-aware policy]
             |
          App / DNS / VPN / Cloud
~~~

### Một ma trận truy cập tham khảo

| Client/SSID | Phương thức cấp quyền | Vùng đích được phép | Vùng nên chặn |
|---|---|---|---|
| **Employee** | 802.1X, thiết bị/tài khoản đủ điều kiện | API nội bộ và dịch vụ theo vai trò | DB trực tiếp, management ngoài quyền |
| **Guest** | Mô hình truy cập khách đã phê duyệt | Internet và dịch vụ công khai theo chính sách | Internal subnets, NAC/RADIUS admin, DB |
| **BYOD** | Onboarding hoặc quyền giới hạn | App đã công bố, thường qua gateway/VPN phù hợp | Truy cập ngang tài sản nội bộ |
| **IoT** | Danh tính thiết bị/quy tắc đặc thù | Chỉ broker/controller/dịch vụ quản lý thiết bị | Employee/Guest/DB không liên quan |
| **Management AP** | Tài khoản/chứng chỉ quản trị, MFA theo nền tảng | Controller, giám sát, update service | Kết nối trực tiếp từ Guest hoặc client không tin cậy |

**Captive portal không phải thay thế mã hóa Wi-Fi, xác thực mạnh hoặc firewall.** Nó có thể là bước tiếp nhận/điều khoản cho khách theo thiết kế, nhưng quyền mạng phải tiếp tục được thực thi ở gateway/ACL/segmentation. Một client được cấp IPv4/IPv6 qua DHCP/SLAAC vẫn có thể bị firewall từ chối tài nguyên ngoài quyền.

## 12. IPv4, IPv6, DHCP, DNS và đường đi sau khi vào Wi-Fi

Site survey thường tập trung vào radio, nhưng lỗi “Wi-Fi kết nối mà không có Internet” có thể do Layer 3 trở lên.

| Triệu chứng | Nguyên nhân khả dĩ | Cần kiểm tra |
|---|---|---|
| Có SSID nhưng không join được | 802.1X/EAP, PSK/SAE, radio compatibility, client profile | NAC/RADIUS, AP association log, client event |
| Join được nhưng không có IP | DHCP relay/scope, DHCPv6/RA, VLAN mapping, firewall | IP lease, VLAN/role, RA, DHCP logs |
| Có IP nhưng không có DNS | DNS resolver policy, captive portal, DNS server lỗi | Resolver, gateway và query logs |
| Có DNS nhưng không vào app | Firewall, TLS, route, proxy/VPN, app IAM | Flow logs, route, certificate/app log |
| Ứng dụng chỉ lỗi khi di chuyển | Roaming, AP handoff, 802.1X reauth, IP mobility | Association timeline, client roam events, jitter |
| IPv4 hoạt động nhưng IPv6 lỗi | RA, firewall IPv6, default route, DNS AAAA, VPN | Test dual-stack và IPv6 logs |
| Chỉ một vùng có độ trễ cao | RF interference, airtime, AP backhaul hoặc backend | SNR/retry, channel utilization, wired uplink |

**Wireless signal leakage không chứng minh L3 reachability.** Thử kết nối từ một điểm ngoài nhà, nếu được phép, vẫn phải đo đúng 802.1X/NAC, VLAN, IPv4/IPv6, DNS và firewall mới đánh giá được đường truy cập tới hệ thống.

### Chuyển vùng Wi-Fi và các cơ chế hỗ trợ

Các tính năng như **802.11k/v/r** có thể giúp khám phá neighbor, gợi ý chuyển AP hoặc giảm độ trễ một số bước chuyển vùng tùy thiết bị và cấu hình. Chúng **không tự bảo đảm** mọi client roaming tốt. Cần kiểm thử với ứng dụng thật, cấu hình xác thực đang dùng, cùng chính sách mạng và thiết bị đại diện.

## 13. Ví dụ thiết kế survey cho một tầng văn phòng

**Bối cảnh giả định:** Một doanh nghiệp đặt hai AP phục vụ khu làm việc, phòng họp và hành lang. Phòng họp dùng video call, khu kho có máy quét, phía sảnh là cửa kính hướng ra lối chung. Đội an ninh muốn giữ chất lượng tốt bên trong nhưng hạn chế vùng có tín hiệu mạng nhân viên mạnh bên ngoài.

### Các vùng và mục tiêu

| Zone | Nhu cầu | Tiêu chí quan sát |
|---|---|---|
| P1 – Phòng họp | Video call, họp đông người | SNR/RSSI phù hợp, p95 latency/jitter và retry dưới mức chấp nhận |
| P2 – Hành lang | Roaming khi di chuyển | Không rớt phiên bất thường khi chuyển AP |
| P3 – Kho | Máy quét di động, kệ kim loại | Coverage theo đúng độ cao và vị trí thiết bị |
| P4/P5 – Văn phòng | Laptop, điện thoại, VPN và API | Kết nối ổn định lúc đông client |
| P6 – Sảnh kính | Nơi giáp ranh giới | Đủ cho người dùng trong sảnh nhưng không hướng quá nhiều năng lượng ra ngoài |
| P7 – Lối chung | Ngoài vùng phục vụ Employee | Ghi mức tín hiệu thu được; không thử vào mạng nếu thiếu quyền |
| P8 – Bãi xe | Đánh giá mở rộng RF có phép | Đánh giá leakage và xác thực AP identity, không thu dữ liệu cá nhân |

### Dữ liệu đo mẫu

**Bảng dưới đây hoàn toàn giả định**, dùng chung một thiết bị đo để minh họa cách đọc:

| Điểm | RSSI của AP gần nhất | Noise floor | SNR xấp xỉ | Bối cảnh | Kết luận sơ bộ |
|---|---:|---:|---:|---|---|
| P1 | -55 dBm | -92 dBm | 37 dB | Phòng họp | RF có vẻ thuận lợi; vẫn cần active test |
| P2 | -67 dBm | -92 dBm | 25 dB | Hành lang | Có thể phù hợp mục tiêu mẫu; cần test roaming |
| P3 | -76 dBm | -92 dBm | 16 dB | Kho có kệ kim loại | Ưu tiên khảo sát thêm theo thiết bị quét |
| P4 | -60 dBm | -92 dBm | 32 dB | Khu văn phòng | Khả quan; cần đo utilization giờ cao điểm |
| P6 | -51 dBm | -92 dBm | 41 dB | Sảnh sát kính | Rất mạnh; xem hướng phát gần cửa |
| P7 | -63 dBm | -92 dBm | 29 dB | Bên ngoài có phép | Leakage đáng chú ý; chưa phải data breach |
| P8 | -81 dBm | -92 dBm | 11 dB | Bãi xe có phép | Vẫn có thể nhìn thấy beacon; đo lại và đánh giá |

**Không nên chỉ dựa vào số RSSI này để tuyên bố “P1–P8 đạt/không đạt chuẩn an ninh”.** Phải xem ứng dụng, thiết bị, góc đo, thay đổi giờ cao điểm và cơ chế xác thực/segmentation.

### Phân tích thay đổi đề xuất

Giả sử RSSI ở P6 và P7 rất mạnh trong khi P3 yếu:

1. **Xem bản đồ và mounting:** AP gần kính có hướng antenna ra ngoài hay không? AP phục vụ kho có kệ/vách cản trở?
2. **Kiểm tra hệ thống radio:** băng tần, công suất hiện hành, kênh, bề rộng kênh, client uplink, RRM.
3. **Xem phương án dịch AP hoặc antenna:** đưa năng lượng về vùng cần dùng thay vì chỉ tăng/giảm đồng loạt.
4. **Đề xuất tuning trong lab/chính sách change:** chỉ áp dụng trên AP liên quan, có rollback và phê duyệt.
5. **Khảo sát lại:** đo P1–P8 cùng thời điểm/điều kiện, thêm active test ở P3 và P6.
6. **Kiểm thử quyền:** mạng Employee vẫn yêu cầu 802.1X và đúng vùng; Guest/IoT không truy cập tài sản không được cấp quyền.
7. **Theo dõi hậu thay đổi:** kiểm tra coverage hole, roaming, channel utilization, AP clients và radio tự động điều chỉnh lại công suất.

Nếu kết quả chỉ giảm RSSI P7 nhưng làm P6 mất Wi-Fi hoặc P3 không cải thiện, phương án **chưa đáp ứng đầy đủ** mục tiêu. Một thay đổi thành công phải tối ưu **chất lượng phục vụ và rủi ro RF** cùng lúc.

## 14. Kiểm tra AP và mạng không dây bất thường

Trong khảo sát, người đo có thể thấy:

~~~text
SSID: CORP-EMP
BSSID: aa:bb:cc:dd:ee:01
Band: 5 GHz
Security shown by scanner: WPA2/WPA3-Enterprise
RSSI at P7: -63 dBm
Inventory: AP-A (needs verification)

SSID: CORP-EMP
BSSID: aa:bb:cc:dd:ee:99
Band: 2.4 GHz
Security shown by scanner: Different from approved profile
RSSI at P7: -57 dBm
Inventory: Not found
~~~

Đây là **số liệu giả lập**. Khác BSSID hoặc chế độ bảo vệ là dấu hiệu cần điều tra, **không phải chứng cứ Evil Twin**. Một AP mới thay phần cứng, một cấu hình chuyển đổi bảo mật hoặc thiết bị phát Wi-Fi của đơn vị kế bên có thể tạo hiện tượng tương tự.

### Quy trình xác minh

1. Đối chiếu WLAN controller, inventory, change ticket và chính sách SSID.
2. Xác minh AP hợp lệ có thể quảng bá **nhiều BSSID** trên mỗi radio/SSID theo thiết kế.
3. Nếu có nghi ngờ AP cắm vào mạng nội bộ, kiểm tra switch port/NAC và sự kiện cấp địa chỉ.
4. Nếu là SSID giả mạo ngoài phạm vi quản lý, cập nhật giám sát và cảnh báo người dùng về **EAP server certificate validation**.
5. Nếu phát hiện cấu hình bảo mật yếu trên AP thực sự thuộc tổ chức, đưa vào change quản lý có kiểm thử client.
6. Không kết luận “đã mất dữ liệu” chỉ vì nhìn thấy AP có cùng tên.

**BSSID thường có dạng địa chỉ MAC nhưng không phải bằng chứng chủ quyền không thể giả mạo.** Các công cụ báo danh tính AP cần đối chiếu controller/chứng chỉ/quản lý thiết bị và các dấu hiệu khác.

## 15. Các chỉ số nghiệm thu survey và mức độ tin cậy

| Nhóm chỉ số | Cách đo hợp lý | Bẫy diễn giải |
|---|---|---|
| **Coverage compliance** | Tỷ lệ điểm cần phục vụ đạt mục tiêu theo application/client | RSSI một thiết bị không đại diện mọi client |
| **SNR/Noise** | Phân bố SNR theo khu, băng tần và thời gian | SNR không phản ánh hết contention từ Wi-Fi khác |
| **Airtime/channel utilization** | Phân bố giờ cao điểm theo radio/channel | Một snapshot ban đêm có thể bỏ qua tải thật |
| **Packet retry / loss** | Retry trên radio và packet loss end-to-end | Retry phụ thuộc chipset, tải và phương pháp thu |
| **Throughput goodput** | Dữ liệu ứng dụng thực nhận theo điều kiện được kiểm soát | PHY link speed không phải throughput |
| **Roaming success** | Tỷ lệ chuyển AP không làm lỗi hành trình đã chọn | Roam phụ thuộc chính sách client và ứng dụng |
| **Outside signal observations** | Tập điểm ngoài ranh giới đo được SSID/BSSID và RSSI | Không xem có beacon bên ngoài là data exfil |
| **AP inventory coverage** | AP/BSSID quan sát được và khớp inventory/controller | Cần phân biệt AP lân cận hợp pháp |
| **802.1X/authentication success** | Tỷ lệ xác thực từ client được phép, thời gian join | RSSI tốt không chứng minh RADIUS hoạt động |
| **Security zone enforcement** | Test Guest/IoT/Employee theo ma trận truy cập | Có địa chỉ IP không nghĩa được truy cập DB |

**Ngưỡng nghiệm thu** phải được xác định trước theo nghiệp vụ, loại thiết bị, pháp lý RF và mục tiêu bảo mật; không đặt “RSSI ngoài nhà phải luôn thấp hơn -X dBm” như một tiêu chuẩn chung. Đánh giá leakage ưu tiên **xu hướng theo thời gian, so sánh trước/sau và mức ảnh hưởng tới bề mặt tiếp cận**, đồng thời kiểm chứng lớp bảo vệ truy cập.

### Cách báo cáo không vượt quá bằng chứng

- **Observed:** “Ở P7 thu được beacon của AP-A, mức khoảng -63 dBm với adapter đo X.”
- **Hypothesis:** “AP gần cửa kính có thể phát quá mạnh ra hành lang ngoài.”
- **Verified:** “Sau chỉnh vị trí antenna được phê duyệt, cùng thiết bị/điều kiện, RSSI tại P7 giảm trong khi P6 và roaming vẫn đạt mục tiêu đã đặt.”
- **Not proven:** “Không có ai có thể truy cập hoặc quan sát mạng từ bên ngoài.”

**Khảo sát an ninh phải phân biệt dữ liệu quan sát, giả thuyết và kết luận đã được xác minh.**

## 16. Theo dõi sau triển khai và chu kỳ khảo sát lại

RF không phải môi trường bất biến. Thay đổi của tòa nhà, đồ nội thất, nhà mạng lân cận, AP mới hoặc firmware đều có thể làm bản đồ vùng phủ cũ không còn đúng.

### Nguồn telemetry vận hành

- **WLAN controller/cloud management:** radio power/channel/width, AP health, SSID/BSSID inventory, client association, roaming failures, retries.
- **NAC/RADIUS/802.1X:** authentication attempts, EAP failures, certificate issues, role/VLAN assignments.
- **WIDS/WIPS:** AP không rõ, thay đổi security capability hoặc sự kiện RF đáng ngờ theo chính sách.
- **Firewall/DNS/DHCP/IPv6 RA:** truy cập giữa các zone, DNS resolver, cấp phát và default route của client.
- **Application/Synthetic testing:** login, video call, API, VPN quality và user-reported incidents.
- **Change management:** AP di chuyển, đổi antenna, firmware, controller config, mở rộng tòa nhà, thiết bị IoT mới.

### Trigger khảo sát lại

1. Thêm hoặc dời AP, đổi antenna hoặc công suất.
2. Thay tường/kính, dựng phòng họp, kệ kho, thiết bị máy móc.
3. Bật băng tần mới hoặc thay đổi chính sách channel width/DFS.
4. Tăng mật độ nhân viên, chuyển sang hội nghị video hoặc triển khai thiết bị quét/IoT.
5. Xuất hiện nhiều client auth failure, roam failure hoặc retry bất thường.
6. WIDS thấy AP/SSID giống tổ chức hoặc nguồn beacon mới trong vùng bảo vệ.
7. Sau sự cố thông tin xác thực/Wi-Fi, thay đổi NAC hoặc ranh giới Guest/Employee.
8. Đánh giá theo lịch cho những vị trí gần cửa kính, bãi xe, phòng thiết bị nhạy cảm.

**Đừng chỉ khảo sát lại khi người dùng phàn nàn.** Những thay đổi RF có thể làm tăng leakage hoặc giảm năng lực mà chưa gây lỗi rõ rệt trong ngắn hạn.

## 17. Quy trình xử lý khi phát hiện signal leakage quá mức mong muốn

### Giai đoạn 1 — Xác minh tín hiệu

1. Xác nhận khu vực đo **được phép tiếp cận**, thời gian và thiết bị đo.
2. Ghi SSID, BSSID, channel, band, RSSI và tọa độ của những điểm ngoài ranh giới.
3. Đối chiếu BSSID với AP inventory/controller và cấu hình radio hiện hành.
4. Kiểm tra có nhiều AP, repeater, thiết bị cá nhân hoặc phát Wi-Fi lân cận gây nhầm lẫn không.
5. Không gọi đó là data breach nếu chưa có bằng chứng vượt kiểm soát truy cập.

### Giai đoạn 2 — Phân tích nguyên nhân

- Vị trí AP và antenna so với kính/tường, chiều cao lắp và hướng phát.
- Radio transmit power, channel, band, channel width và RRM.
- Điều kiện tại giờ cao điểm, vật liệu thực tế và sự kiện thay đổi tòa nhà.
- Mức tín hiệu/roaming/throughput ở những điểm bên trong cần phục vụ.
- WLAN security profile, EAP server validation, PMF và các đường segment sau khi kết nối.

### Giai đoạn 3 — Đề xuất và thực hiện thay đổi

1. Thử phương án **di chuyển AP/đổi hướng antenna**, tối ưu cell coverage và quản lý công suất theo từng AP.
2. Xác định những điểm đo bên trong có nguy cơ mất dịch vụ và kế hoạch regression test.
3. Phê duyệt thay đổi, lưu cấu hình trước/sau, chỉ áp dụng trong cửa sổ phù hợp.
4. Tránh thay đổi toàn bộ controller/radio policy để xử lý một điểm đo nếu chưa đánh giá tác động.
5. Không tắt 802.1X, bỏ PMF hay chuyển mạng sang open chỉ để giải quyết một vấn đề roaming hoặc client lỗi.

### Giai đoạn 4 — Kiểm thử và hậu kiểm

- Đo lại cùng các điểm trong/ngoài ranh giới và đối chiếu mức sai khác.
- Kiểm tra video call, ứng dụng, roaming, throughput và client yếu.
- Xác nhận Guest, Employee, BYOD và IoT tiếp tục được gán đúng zone/quyền.
- Theo dõi WIDS, authentication failure, client retry và channel utilization.
- Đánh dấu **PASS/FAIL/INCONCLUSIVE**, cập nhật heatmap, inventory và lịch kiểm tra.

**Nếu leakage không thể giảm hơn mà vẫn đáp ứng coverage, đó không nhất thiết là thất bại bảo mật** khi xác thực, phân quyền, mã hóa và giám sát đã phù hợp mức rủi ro được phê duyệt. Điều quan trọng là đánh giá minh bạch rủi ro còn lại.

## 18. Bài thực hành quan sát an toàn

Mục tiêu bài lab: quan sát RF trên thiết bị thuộc quyền kiểm soát, ghi nhận SSID/BSSID và độ mạnh tín hiệu tại các điểm đã được phép khảo sát, so sánh với trải nghiệm thực tế. **Không thu mật khẩu, không bắt nội dung người dùng, không gửi deauthentication và không thử đăng nhập mạng bên thứ ba.**

### Trên Windows được phép quản trị

~~~powershell
netsh wlan show interfaces
netsh wlan show networks mode=bssid
ipconfig /all
~~~

Đây là những lệnh đọc trạng thái mạng/WLAN; output và thông tin RSSI dưới dạng phần trăm hoặc giá trị khác tùy adapter/driver. Không tự coi tỷ lệ phần trăm signal trong Windows tương đương dBm khi chưa có phương pháp hiệu chuẩn.

### Trên Linux được phép quản trị

~~~bash
nmcli device status
nmcli -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY device wifi list
ip route
ip -6 route
~~~

Các lệnh giả định máy dùng **NetworkManager/nmcli**. Một số bản phân phối hoặc thiết bị không hỗ trợ cùng các field, và lệnh liệt kê Wi-Fi có thể hiển thị kết quả scan/cache tùy driver; không phải phương án đo chính xác thay thiết bị survey.

Nếu muốn xem kết nối Wi-Fi hiện tại và có công cụ tương ứng:

~~~bash
iw dev
iw dev wlan0 link
~~~

Thay **wlan0** bằng tên interface thật đã đọc được. Dữ liệu từ các công cụ hệ điều hành là quan sát hữu ích, nhưng độ tin cậy/độ phân giải không nhất thiết bằng survey adapter được hiệu chuẩn.

### Những gì cần ghi vào phiếu lab

~~~text
Survey ID:          WLAN-RF-01
Date/timezone:      [giờ đo và múi giờ]
Site/floor/point:   [vị trí được phép khảo sát]
Inside/perimeter:   [bên trong / ngoài trong phạm vi cho phép]
Device/adapter:     [model + OS + driver]
SSID/BSSID:         [đã đối chiếu inventory hay chưa]
Band/channel:       [kết quả quan sát]
RSSI/SNR:           [giá trị và nguồn đo]
Noise/utilization:  [giá trị nếu công cụ có hỗ trợ]
Association:        [chỉ thử với SSID được cấp phép]
802.1X/role:        [kết quả log được cấp quyền]
Client app result:  [nếu có active test]
Security boundary:  [SSID/zone/firewall mong muốn]
Observation:        [điều đo được]
Hypothesis:         [nguyên nhân có thể]
Assessment:         [PASS / FAIL / INCONCLUSIVE]
Change/owner:       [ticket / người rà soát]
~~~

**INCONCLUSIVE** dùng khi thiếu inventory, không chứng minh được AP thuộc tổ chức, thiết bị đo không báo RSSI đáng tin hoặc không có dữ liệu kiểm tra phân đoạn. Không đánh dấu PASS chỉ vì thiết bị có thể nhìn thấy SSID.

## 19. Kiểm thử nghiệm thu từ RF đến mạng và ứng dụng

| Test ID | Trường hợp | Kỳ vọng |
|---|---|---|
| **WLAN-01** | Người dùng Employee trong phòng họp | RSSI/SNR phù hợp, video call/app đáp ứng mục tiêu |
| **WLAN-02** | Máy quét di chuyển trong kho | Không có điểm chết gây lỗi tác vụ quan trọng |
| **WLAN-03** | Client đi từ P1 qua P2 tới P4 | Roaming không làm hỏng hành trình đã chọn |
| **WLAN-04** | Đo tại P7/P8 trong phạm vi được phép | Ghi leakage định lượng, không tự suy data breach |
| **WLAN-05** | Client được cấp quyền kết nối Employee SSID | 802.1X xác thực đúng, gán role/VLAN và policy |
| **WLAN-06** | Thiết bị Guest thử truy cập dịch vụ nội bộ trong lab được phép | Bị từ chối bởi đúng security boundary |
| **WLAN-07** | Client dùng IPv6/dual-stack trên Wi-Fi | Có RA/DNS/route và firewall policy phù hợp |
| **WLAN-08** | BSSID/SSID chưa rõ xuất hiện ở survey | Được phân loại qua inventory, không tự động gán là malicious |
| **WLAN-09** | Kiểm tra vào giờ cao điểm | Airtime/retry/latency vẫn trong mục tiêu nghiệp vụ |
| **WLAN-10** | Đổi hướng anten/công suất có phê duyệt | Leakage mục tiêu giảm mà coverage và roaming không xấu quá mức |
| **WLAN-11** | API machine-to-machine/IoT hợp lệ dùng Wi-Fi | Hoạt động theo chính sách thiết bị, không bị yêu cầu xác thực sai kiểu |
| **WLAN-12** | Client mất Wi-Fi nhưng Ethernet/ứng dụng vẫn hoạt động | Điều tra đúng điểm lỗi, không vội sửa firewall hoặc DNS |

**Khi testing Guest/Employee segmentation**, chỉ truy cập các đích thuộc lab/phạm vi được cấp phép; không quét hoặc thử đăng nhập hệ thống ngoài quyền để “xác minh” an ninh.

## 20. Tình huống điều tra: phát hiện SSID công ty ở bãi đỗ xe

**Bối cảnh giả định:** Một thành viên IT đứng ở bãi đỗ xe được phép khảo sát và thấy **CORP-EMP** với tín hiệu tương đối mạnh. Đồng thời SOC nhận cảnh báo có một BSSID chưa nằm trong inventory phát SSID tương tự. Một số người dùng báo Wi-Fi không ổn định gần sảnh kính.

### Các giả thuyết có thể

1. **AP hợp lệ phát quá xa:** vị trí gần kính/công suất cao tạo leakage.
2. **AP hợp lệ chưa đồng bộ inventory:** thay thiết bị gần đây hoặc controller cập nhật chậm.
3. **AP trái phép trên mạng nội bộ:** có thiết bị không được phê duyệt kết nối switch.
4. **SSID giả mạo/Evil Twin:** một thiết bị gần đó cố tạo SSID giống công ty, cần xác minh thêm.
5. **Cấu hình RF bị thay đổi:** RRM, firmware, channel/antenna hoặc vật cản mới.
6. **Nhiễu/co-channel contention:** lỗi chất lượng gần sảnh có thể không đến từ leakage.

### Chuỗi phân tích theo thứ tự

1. **Bảo toàn thông tin quan sát:** vị trí, thời điểm, adapter, SSID/BSSID, kênh, RSSI.
2. **Đối chiếu inventory:** xác định những AP nào được controller quản lý, radio security profile và thay đổi gần đây.
3. **Xem wired/network logs:** nếu nghi rogue AP nội bộ, kiểm tra switch port/NAC và thiết bị được kết nối; không tự can thiệp AP của bên khác.
4. **Đánh giá bảo mật client:** đảm bảo EAP server certificate validation và chính sách onboarding, không khuyến khích người dùng bấm chấp nhận chứng chỉ bất kỳ.
5. **Khảo sát RF phía trong và perimeter:** so sánh vùng phủ, interference, throughput và roaming bằng thiết bị/điều kiện nhất quán.
6. **Xác định nguyên nhân:** AP power/placement, thiết bị không quản lý, hiệu năng radio hay cấu hình khác.
7. **Áp dụng sửa chữa được phê duyệt:** chỉnh antenna/power/placement hoặc đưa AP chưa phê duyệt về đúng quy trình quản lý; có rollback.
8. **Kiểm tra end-to-end:** Wi-Fi của người dùng hợp lệ hoạt động, đúng 802.1X/VLAN/IPv6/firewall, signal leakage được đánh giá lại.

**Kết luận ban đầu hợp lệ:** “Tín hiệu của một hoặc nhiều thiết bị phát SSID giống mạng công ty có thể thu được ở bãi xe; cần xác minh ownership và tác động.” **Chưa đủ căn cứ** tuyên bố đã có dữ liệu bị nghe lén, kẻ tấn công đã tham gia mạng hoặc nhân viên bị đánh cắp mật khẩu.

## 21. Những hiểu nhầm thường gặp

| Nhận định sai | Vì sao sai hoặc thiếu | Cách tiếp cận đúng |
|---|---|---|
| “Thấy SSID ngoài tường nghĩa là dữ liệu đã bị lộ” | RF vượt ranh giới không chứng minh truy cập hay giải mã | Kiểm chứng lớp xác thực, mã hóa, phân đoạn và sự kiện thật |
| “Giấu SSID sẽ không ai phát hiện Wi-Fi” | SSID ẩn không phải cơ chế bảo mật mạnh | 802.1X/WPA, kiểm soát client và quyền mạng |
| “RSSI mạnh đồng nghĩa Wi-Fi nhanh” | Nhiễu, airtime, retry, backhaul và ứng dụng còn ảnh hưởng | Đo SNR, utilization, loss và real app |
| “Một thiết bị đo cho kết quả tuyệt đối” | Adapter, orientation, driver và client khác nhau | Chuẩn hóa phương pháp và thử thiết bị đại diện |
| “Giảm mọi AP xuống công suất thấp nhất là an toàn” | Có thể tạo coverage hole và client uplink lỗi | Điều chỉnh theo vùng phục vụ và khảo sát lại |
| “Tăng công suất AP sẽ giải quyết mọi dead spot” | Client uplink yếu hoặc nhiễu không biến mất | Xem antenna/placement/SNR và hai chiều |
| “BSSID giống inventory chắc chắn là AP thật” | BSSID có thể bị giả mạo | Ghép controller, switch, NAC và bảo mật EAP |
| “SSID lạ đều là rogue của công ty” | Mạng hàng xóm/khách có thể hợp pháp | Xác minh sở hữu và liên kết mạng dây |
| “WIPS nên tự động ngắt AP nghi ngờ” | Có thể làm gián đoạn người khác và gây vấn đề pháp lý | Phân loại, phê duyệt và hành động trong phạm vi quản trị |
| “Captive portal là đủ bảo mật cho Guest” | Portal không tự mã hóa/giới hạn lateral access | Phân đoạn, firewall và kiểm soát phiên |
| “Có WPA3 thì không cần survey” | Mã hóa không cải thiện coverage, roaming, interference | Khảo sát RF và kiểm thử ứng dụng riêng |
| “WPA Enterprise tự xác thực đúng server” | Client/EAP có thể cấu hình xác minh server sai | PKI, profile được quản lý và certificate validation |
| “IPv4 policy cũng bảo vệ IPv6” | Dual-stack có thể đi đường khác | Kiểm tra RA, IPv6 routes, DNS và ACL |
| “Một heatmap tốt là đủ mãi mãi” | Tòa nhà, tải, AP, firmware và môi trường thay đổi | Theo dõi và khảo sát lại theo trigger |
| “Không thấy beacon trong một lần đo là hết leakage” | Mất gói, orientation và công cụ đo có giới hạn | Lặp đo, dùng nhiều điểm/điều kiện và nêu uncertainty |

## 22. Câu hỏi tự kiểm tra

1. **Site survey** khác **security assessment** của mạng không dây ở những nội dung nào?
2. Vì sao thu được beacon của SSID công ty ngoài bãi xe không tự chứng minh đã có **data exfiltration**?
3. RSSI **-55 dBm** và **-75 dBm**, mức nào mạnh hơn? Có thể từ đó kết luận throughput không?
4. Nếu tín hiệu là **-60 dBm**, noise floor **-90 dBm**, SNR xấp xỉ bao nhiêu dB? Cần lưu ý điều gì khi dùng số này?
5. Predictive, passive, active survey và spectrum analysis có những lợi ích/giới hạn khác nhau thế nào?
6. Vì sao chỉ dùng RSSI làm KPI có thể bỏ qua **co-channel interference** và airtime congestion?
7. Những thành phần nào cần đo tại một điểm trong nhà và một điểm ngoài perimeter để đối chiếu?
8. Những thay đổi AP/antenna/công suất nào có thể giảm leakage nhưng làm xấu trải nghiệm người dùng?
9. Vì sao giảm công suất AP phải kiểm tra cả **client uplink**?
10. 802.1X/EAP, WPA3-Enterprise và PMF bảo vệ những khía cạnh nào? PMF có làm beacon vô hình không?
11. Nếu hai BSSID phát cùng SSID, có đủ căn cứ nói một AP là Evil Twin không?
12. WIDS khác WIPS như thế nào và vì sao chặn chủ động qua radio cần kiểm soát đặc biệt?
13. Vì sao Guest Wi-Fi cần phân đoạn và firewall ngay cả khi đã có captive portal?
14. Một client có sóng tốt nhưng không có IPv6 default route: site survey radio sẽ giúp và không giúp gì?
15. Hãy thiết kế phép kiểm thử chứng minh giảm RSSI ngoài cửa kính **mà không làm hỏng video call trong phòng họp**.
16. Trong case study, cần những bằng chứng nào trước khi xử lý một SSID chưa có trong inventory?
17. Khi nào nên khảo sát lại: sau thay firmware AP, thay tường kính, thêm IoT hay chỉ khi có sự cố?
18. Vì sao báo cáo nên tách **observed, hypothesis, verified và not proven**?

## 23. Ghi nhớ trọng tâm

**Site survey và signal leakage** là việc hiểu và kiểm soát vùng phủ vô tuyến **theo nhu cầu sử dụng và ranh giới rủi ro**. Khảo sát cần kết hợp **predictive, passive, active và spectrum analysis** đúng mục tiêu, sử dụng RSSI, SNR, noise, channel utilization, retry, roaming và kiểm thử ứng dụng với phương pháp đo nhất quán. Vùng phủ tốt phải giúp client hợp lệ hoạt động ở nơi cần thiết; leakage cần được **ghi nhận tại ranh giới được phép khảo sát** chứ không suy ngay thành mất dữ liệu.

**Tín hiệu ra ngoài tường không đồng nghĩa vượt qua xác thực.** Biện pháp nền tảng vẫn là **WPA2/WPA3-Enterprise, 802.1X/EAP với xác minh server đúng, PMF phù hợp, NAC, phân đoạn Guest/Employee/IoT, firewall và giám sát WIDS/EDR/controller**. Tối ưu AP placement, antenna, channel và công suất có thể giảm mức tín hiệu không cần thiết ở bên ngoài, nhưng phải kiểm chứng hai chiều radio, capacity, roaming và nhu cầu thật của người dùng. Mọi thay đổi nên có **baseline, quyền phê duyệt, kết quả đo trước–sau, test ma trận truy cập và rollback**, đồng thời tránh can thiệp RF trái phép hoặc tự kết luận sự cố bảo mật từ một SSID/BSSID đơn lẻ.
