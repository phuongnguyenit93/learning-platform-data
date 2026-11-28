# PCAP retention và bảo vệ dữ liệu nhạy cảm

## 1. Vì sao phải quản lý vòng đời file PCAP?

Trong điều tra sự cố mạng, file packet capture (PCAP) giúp tái hiện gói tin tại một thời điểm: ai giao tiếp với ai, sử dụng giao thức nào, phiên kết nối diễn ra ra sao và có dấu hiệu bất thường hay không. Tuy nhiên, cùng một file hữu ích cho phân tích kỹ thuật có thể chứa dữ liệu khách hàng, nội dung công việc, thông tin xác thực hoặc dữ liệu vận hành quan trọng. Việc lưu trữ quá lâu hay chia sẻ sai nơi có thể biến công cụ phòng vệ thành nguồn rò rỉ dữ liệu.

**PCAP retention** là chính sách và cơ chế quyết định **thu thập gì, lưu ở đâu, ai được sử dụng, giữ đến khi nào và xóa bằng cách nào**. Đây là một phần của kiến trúc bảo mật mạng: phải kết hợp phân đoạn mạng, kiểm soát truy cập, mã hóa, giám sát, ứng cứu sự cố và các yêu cầu bảo vệ dữ liệu của tổ chức.

Kết thúc bài học, người học có thể:

- Nhận diện thông tin nhạy cảm trong PCAP/PCAPNG, kể cả khi phần lớn lưu lượng dùng TLS.
- Chọn mức thu thập đủ để xử lý câu hỏi kỹ thuật, giảm rủi ro bằng phạm vi, thời gian và độ dài gói tin.
- Thiết kế retention theo loại dữ liệu, mục đích xử lý và yêu cầu pháp lý/hợp đồng.
- Kiểm soát truy cập, mã hóa, chia sẻ, ghi nhật ký kiểm toán và lưu giữ chứng cứ.
- Triển khai cơ chế hết hạn/xóa có xác minh, xử lý ngoại lệ **legal hold**, bản sao và bản sao lưu.

> **Nguyên tắc xuyên suốt:** Chỉ thu thập dữ liệu có mục đích rõ ràng; giữ trong thời gian cần thiết; bảo vệ suốt vòng đời và có bằng chứng về việc xử lý/xóa.

## 2. PCAP thực sự chứa những gì?

Một PCAP thông thường lưu bản ghi thời gian và các byte đã được bắt tại điểm quan sát. **Bản thân định dạng PCAP không tự mã hóa hoặc ẩn danh nội dung.** PCAPNG có thể lưu thêm thông tin giao diện, tên thiết bị, comment, ánh xạ phân giải tên, thống kê và metadata khác. Điểm đặt cảm biến (SPAN/TAP, host, gateway, proxy hoặc cloud sensor) quyết định lưu lượng nào có mặt.

| Loại thông tin | Ví dụ có thể xuất hiện | Rủi ro khi bị lộ |
|---|---|---|
| Định danh và quan hệ mạng | IP, MAC, VLAN, cổng, thời gian, DNS query, SNI khi hiển thị | Dựng bản đồ hạ tầng, suy ra người dùng/dịch vụ và lịch hoạt động |
| Nội dung giao thức chưa mã hóa | HTTP, FTP, Telnet, một số DNS và giao thức nội bộ | Lộ nội dung trao đổi, tên tệp, dữ liệu cá nhân và dữ liệu kinh doanh |
| Thông tin xác thực hoặc phiên | HTTP Authorization, cookie, API token, mật khẩu truyền rõ | Chiếm quyền tài khoản hoặc phiên đăng nhập |
| Dữ liệu ứng dụng | Nội dung biểu mẫu, yêu cầu API, log truyền trên mạng, tệp đính kèm | Lộ dữ liệu cá nhân, tài chính, y tế hoặc bí mật kinh doanh |
| Nội dung mã hóa và metadata TLS | Ciphertext, địa chỉ đích, thời gian, kích thước, đặc điểm bắt tay; đôi khi có tên máy chủ | Suy luận mẫu truy cập; dữ liệu có thể giải mã nếu kẻ khác lấy được khóa thích hợp |
| Metadata của PCAPNG và công cụ | Interface name, chú thích, name-resolution blocks, đường dẫn xuất | Rò rỉ tên nội bộ, địa chỉ và chi tiết điều tra |

Những điểm dễ nhầm:

1. **“Đã dùng HTTPS nên PCAP không nhạy cảm” là sai.** TLS bảo vệ payload khi truyền nhưng nhiều metadata còn quan sát được; nếu ghi thêm khóa phiên TLS hoặc capture ở điểm sau giải mã, nội dung có thể được đọc. Tên miền không luôn hiện diện (ví dụ khi có ECH), nhưng không nên coi metadata còn lại là vô hại.
2. **“Chỉ bắt header là an toàn tuyệt đối” là sai.** Header vẫn tiết lộ địa chỉ, giao tiếp và thời gian. Với gói nhỏ, giới hạn số byte có thể vẫn giữ một phần payload.
3. **“Đổi tên file hoặc nén ZIP là đã bảo vệ” là sai.** Nén và đổi đuôi không phải mã hóa.
4. **“Xóa IP là ẩn danh hoàn toàn” là sai.** Timestamp, tổ hợp dịch vụ, DNS và mẫu hành vi có thể cho phép tái nhận dạng.

Vì vậy, hãy **phân loại theo dữ liệu nhạy cảm có thể chứa**, không chỉ theo phần mở rộng `.pcap` hay `.pcapng`. Bản dump được giải mã cùng khóa giải mã, báo cáo trích xuất và ảnh chụp màn hình phân tích đều cần quản lý như dữ liệu điều tra tương ứng.

## 3. Quyết định có cần bắt gói hay không

Trước khi tạo PCAP, xác định câu hỏi cần trả lời. Ví dụ: “SYN retransmission xuất hiện ở đoạn mạng nào?” có thể chỉ cần thống kê TCP và header; “payload ứng dụng có sai cấu trúc?” có thể cần dữ liệu chi tiết hơn trong phạm vi phiên cụ thể.

Có thể dùng thứ tự ưu tiên sau:

1. **Metric và flow telemetry** (NetFlow/IPFIX, thống kê firewall, IDS/IPS): phù hợp để đo lưu lượng, endpoint, lưu lượng bất thường và xu hướng dài hạn; thường ít lộ nội dung hơn nhưng metadata vẫn nhạy cảm.
2. **Header-only hoặc truncated PCAP**: phù hợp với TCP flags, handshake, retransmission, fragmentation và một số sự cố định tuyến/giao thức.
3. **Full-packet PCAP**: chỉ dùng khi vấn đề không thể giải quyết bằng dữ liệu ít chi tiết hơn, với thời gian và phạm vi được phê duyệt.

| Biện pháp | Tác dụng | Giới hạn |
|---|---|---|
| Bắt theo IP/port/VLAN và vị trí | Thu hẹp số phiên quan sát | Bộ lọc không nhận biết danh tính người dùng hoặc nội dung nhạy cảm |
| Giới hạn thời gian, số packet, dung lượng | Giảm tập dữ liệu và thời gian lộ dữ liệu | Có thể bỏ sót sự kiện ngoài khoảng bắt |
| Giới hạn snaplen (`-s`) | Cắt bớt số byte mỗi packet được lưu | Không bảo đảm “chỉ header”; header IPv6 mở rộng/VLAN có độ dài khác nhau |
| Lọc hoặc tổng hợp ở cảm biến | Chỉ giữ trường phục vụ phân tích | Cần kiểm tra logic; có thể đánh mất giá trị pháp chứng |
| Chỉ xuất kết quả phân tích đã rà soát | Hạn chế lan truyền bản gốc | Báo cáo vẫn có thể chứa dữ liệu nhận dạng hoặc bí mật |

**Capture filter** (BPF, ví dụ `host 192.0.2.10 and port 443`) thường quyết định gói nào được ghi. **Display filter** (ví dụ lọc trong Wireshark sau khi mở file) chỉ giới hạn phần được hiển thị và **không xóa** gói khỏi file gốc. Cả hai không tự phát hiện hay loại bỏ cookie, token, thông tin cá nhân trong mọi giao thức.

Cần thiết kế điểm bắt phù hợp. Bắt tại backbone có thể ghi hàng nghìn người dùng; một capture ngắn tại máy thử nghiệm hoặc interface chuyên biệt có thể đủ để tái hiện lỗi. Việc bắt lưu lượng phải dựa trên thẩm quyền, quy định nội bộ, hợp đồng và pháp luật áp dụng; tránh thu thập vượt phạm vi đã được cho phép.

## 4. Xây dựng chính sách retention

Một chính sách có khả năng vận hành phải xác định ít nhất: **mục đích**, **loại dữ liệu**, **chủ sở hữu**, **mốc bắt đầu**, **thời hạn**, **nơi lưu**, **người được cấp quyền**, **quy tắc ngoại lệ** và **cách xác nhận xóa**.

### 4.1. Ma trận lưu giữ tham khảo

Các khoảng thời gian dưới đây là **ví dụ minh họa cho môi trường giả định**, không phải thời hạn pháp lý, tiêu chuẩn bắt buộc hay đề xuất mặc định cho mọi tổ chức. Phải điều chỉnh theo chính sách, phân loại dữ liệu, hợp đồng, quy định hiện hành và nhu cầu điều tra thực tế.

| Loại dữ liệu | Mục đích | Thời hạn ví dụ | Bảo vệ/điều kiện |
|---|---|---|---|
| Thống kê flow đã giảm trường | Theo dõi xu hướng và phát hiện bất thường | 30 ngày | IAM, TLS, mã hóa lưu trữ, hạn chế truy vấn theo cá nhân |
| PCAP chỉ giữ header | Chẩn đoán sự cố thông thường | 72 giờ | Thư mục/bucket hạn chế, tự động xóa |
| PCAP đầy đủ theo yêu cầu | Xử lý một sự cố kỹ thuật cụ thể | 24 giờ sau khi kết thúc capture | Phê duyệt có thời hạn, lưu mã hóa, kiểm soát xuất file |
| PCAP điều tra an ninh được lập hồ sơ | Bảo tồn chứng cứ cho vụ việc đang mở | 30 ngày, gia hạn có xét duyệt | Case ID, custodian, access log, bằng chứng toàn vẹn |
| Dữ liệu thuộc yêu cầu giữ lại hợp lệ | Đáp ứng yêu cầu điều tra/pháp lý cụ thể | Theo yêu cầu và rà soát định kỳ | Legal hold, giới hạn người truy cập, quy trình gỡ hold |

Mốc tính hạn nên được định nghĩa rõ, ví dụ `capture_end_utc` đối với tập PCAP. Không tính lại hạn từ đầu mỗi lần người dùng tải xuống, mở file hoặc chuyển tầng lưu trữ. Nếu phát sinh bản sao phân tích, bản sao đó có **mã định danh và ngày hết hạn riêng**, đồng thời không được vượt quá quyền và hạn được phép nếu không có căn cứ mới.

**Retention** khác với **thời gian sao lưu**: backup, bản sao đa vùng, phiên bản object và snapshot có thể giữ lại byte đã xóa ở hệ thống chính. Phải đưa chúng vào quy trình hết hạn, hoặc chỉ rõ thời điểm backup sẽ tự hết hạn theo lịch đã phê duyệt.

### 4.2. Metadata tối thiểu cho một capture

Mỗi job hoặc hồ sơ điều tra nên có thông tin sau:

~~~yaml
case_id: INC-2026-042           # Mã vụ việc ví dụ
purpose: "Xác minh TCP retransmission tới dịch vụ thử nghiệm"
requester: "network-ops"
approver: "security-owner"
data_owner: "service-owner"
capture_point: "sensor-seg-a"
scope: "192.0.2.10:443"         # Địa chỉ TEST-NET minh họa
mode: "headers-truncated"
snaplen_bytes: 96
capture_start_utc: "2026-11-28T03:00:00Z"
capture_end_utc: "2026-11-28T03:05:00Z"
classification: "restricted"
storage_reference: "secure-evidence/INC-2026-042"
retention_until_utc: "2026-12-01T03:05:00Z"
legal_hold: false
custodian: "secops"
~~~

Mẫu trên là **metadata quản trị**, không phải cấu hình áp dụng tự động cho một hệ thống cụ thể. Trong thực tế cần kiểm tra: thời hạn có phù hợp quy định không, snapshot có đủ trường để phân tích không, ai được chuyển từ “headers-truncated” sang “full-packet”, và quyền đối với dữ liệu gốc được xác định ở đâu.

Nếu một capture tạo nhiều file, quản lý cả bộ bằng manifest (`case_id`, danh sách file, thời gian, kích thước, hash, trạng thái, nơi lưu), tránh file “mồ côi” nằm ngoài lịch xóa.

## 5. Kiến trúc bảo vệ dữ liệu PCAP từ lúc thu thập

~~~mermaid
flowchart TD
    A["Yêu cầu có mục đích, phạm vi và hạn lưu"] --> B["Phê duyệt và chọn mức capture tối thiểu"]
    B --> C["Capture giới hạn trên vùng lưu mã hóa"]
    C --> D["Niêm phong file gốc, hash, phân loại, ghi manifest"]
    D --> E["Kho bảo vệ: IAM + KMS + audit + retention"]
    E --> F{"Còn nhu cầu hợp lệ?"}
    F -->|"Có, người dùng được phép"| G["Phân tích trong môi trường kiểm soát"]
    G --> H["Xuất báo cáo đã rà soát; quản lý bản sao"]
    H --> F
    F -->|"Hết hạn, không có hold"| I["Xóa các phiên bản/bản sao theo chính sách"]
    F -->|"Legal hold hợp lệ"| J["Hạn chế truy cập và rà soát hold"]
    J --> F
    I --> K["Ghi nhật ký và xác minh xóa"]
~~~

### 5.1. Bảo vệ ngay tại cảm biến

- Chỉ bật capture theo yêu cầu có thời điểm bắt đầu/kết thúc; áp dụng allowlist interface, BPF filter và hạn mức dung lượng, số gói, tốc độ ghi.
- Ghi vào phân vùng/ổ đã mã hóa, dùng quyền file chặt chẽ. **Nếu ghi plaintext rồi mới mã hóa**, bản tạm, swap, snapshot hoặc vùng lưu bị bỏ quên vẫn có thể tồn tại.
- Tách mạng quản trị của sensor khỏi mạng theo dõi; hạn chế truy cập SSH, cập nhật bản vá, đồng bộ thời gian đáng tin cậy để phục vụ tương quan và pháp chứng.
- Không đưa PCAP thô vào log tập trung, ứng dụng chat, ticket hoặc kho mã nguồn để “tiện chia sẻ”. Dùng mã tham chiếu và đường dẫn truy cập đã được kiểm soát.
- Không bật giải mã TLS, thu khóa phiên hoặc thu payload đầy đủ khi mục đích không đòi hỏi; **khóa giải mã là bí mật có độ nhạy cao** và cần quản lý riêng.

### 5.2. Bảo vệ khi lưu trữ và truyền tải

**Mã hóa khi lưu:** sử dụng mã hóa filesystem/volume và/hoặc object storage phù hợp; trong kiến trúc yêu cầu phân tách quyền, có thể dùng envelope encryption với khóa dữ liệu được bảo vệ bởi KMS/HSM. Hạn chế người có thể giải mã và người quản lý khóa; quản lý vòng đời, xoay vòng, thu hồi và nhật ký sử dụng khóa. Lưu ý: mã hóa ổ đĩa không ngăn được tài khoản đang đăng nhập và được cấp quyền đọc plaintext.

**Mã hóa khi truyền:** dùng kênh bảo mật đã xác thực (chẳng hạn TLS hoặc kết nối quản trị phù hợp), xác minh điểm cuối; tránh truyền qua FTP/HTTP không mã hóa hoặc liên kết chia sẻ công khai.

**Quyền truy cập:** nguyên tắc ít quyền nhất và tách nhiệm vụ:

| Vai trò | Quyền điển hình | Giới hạn |
|---|---|---|
| Capture operator | Khởi tạo/dừng job theo phạm vi được duyệt | Không tự cấp quyền xem mọi PCAP |
| Evidence custodian | Nhận file, niêm phong, gắn retention, xử lý xóa | Không tùy ý thay đổi bản gốc |
| Incident analyst | Truy cập các case được phân công; tạo bản phân tích | Không có quyền duyệt lưu vô hạn hoặc chia sẻ công khai |
| Security/privacy reviewer | Duyệt xuất dữ liệu, gia hạn, thay đổi phạm vi | Có nhật ký quyết định |
| Auditor | Xem manifest và lịch sử hành động | Không cần quyền đọc payload mặc định |

Dùng RBAC/ABAC theo case, nhóm, mức phân loại và thời hạn; xác thực mạnh (MFA), truy cập theo phiên và cấp quyền tạm thời khi khả thi. Các quyền kiểu `read-all`, quyền tải hàng loạt và token truy cập dài hạn cần được kiểm soát đặc biệt. “Break-glass” phục vụ sự cố nghiêm trọng phải có lý do, giới hạn thời gian và kiểm tra sau sử dụng.

Ghi nhật ký **ai truy cập**, **vào lúc nào**, **trên case/file nào**, **hành động gì** (đọc, tải xuống, giải mã, xuất, đổi quyền, gia hạn, áp hold, xóa), **kết quả** và **mã yêu cầu phê duyệt**. Nhật ký kiểm toán phải được bảo vệ khỏi việc sửa/xóa bởi chính người đang sử dụng PCAP; bản thân audit log cũng có thể chứa dữ liệu cá nhân.

## 6. Ví dụ thu thập PCAP có giới hạn

Giả sử cần quan sát lỗi kết nối TCP tới máy thử nghiệm `192.0.2.10` trên cổng `443` trong tối đa 5 phút. Đây là IP tài liệu thuộc dải TEST-NET, không đại diện cho hệ thống thật.

~~~bash
# Ví dụ cho Linux có tcpdump, timeout và quyền quản trị phù hợp.
# /var/secure-pcap phải nằm trên vùng lưu được mã hóa, quản lý truy cập.
sudo install -d -m 0700 /var/secure-pcap

# Giới hạn thời gian, số gói, IP/port và số byte ghi trên mỗi packet.
sudo timeout --signal=INT 300s tcpdump \
  -i eth0 -nn -s 96 -c 100000 \
  -w /var/secure-pcap/INC-2026-042.pcap \
  'host 192.0.2.10 and port 443'

# Tính hash để theo dõi tính toàn vẹn của bản gốc.
sudo sha256sum /var/secure-pcap/INC-2026-042.pcap
~~~

**Giải thích quan trọng:**

- `-i eth0` là interface ví dụ, cần xác định theo điểm capture được phép; `-nn` tránh phân giải hostname/service trong output.
- `-s 96` lưu tối đa 96 byte **tính từ đầu packet được bắt**, không phải bảo đảm giữ chính xác 96 byte header. Tùy lớp liên kết, VLAN, IPv6 extension headers và giao thức encapsulation, byte được giữ có thể thiếu thông tin cần thiết hoặc chứa một phần payload. Cần kiểm thử trên traffic mẫu trước khi vận hành.
- `-c 100000` dừng khi đủ 100.000 gói; `timeout` gửi tín hiệu dừng sau 300 giây. Khi chạm ngưỡng thời gian, `timeout` có thể trả mã 124 dù file đã được ghi; đọc thông điệp kết thúc và kiểm tra file trước khi xử lý tiếp.
- Bộ lọc bắt chỉ chọn traffic. Nó không kiểm tra nội dung để tự loại bỏ secrets. Nếu phân tích yêu cầu chiều sâu hơn, phải phê duyệt thay đổi trước khi bỏ giới hạn.
- Lệnh hash chỉ in giá trị băm. Muốn phục vụ **chain of custody**, cần lưu hash vào manifest được bảo vệ, gắn danh tính người thực hiện và thời điểm. SHA-256 giúp phát hiện thay đổi **khi so với hash tin cậy ban đầu**, nhưng chỉ một hash không chứng minh ai đã thu thập dữ liệu.

Để tránh dữ liệu plaintext còn sót lại, hệ thống thực tế nên thực thi việc capture bằng service account/cơ chế quản lý chuẩn, trực tiếp trên ổ mã hóa, đồng thời có quy trình đưa file vào kho an toàn và dọn bản tạm. Không chạy ví dụ trên lưu lượng thực khi chưa có phạm vi và quyền phù hợp.

### 6.1. Ước lượng dung lượng để không giữ quá nhiều

Với PCAP định dạng cổ điển, có thể ước lượng gần đúng:

~~~text
dung_lượng_byte ≈ packet_mỗi_giây × (byte_được_lưu_mỗi_packet + 16) × thời_gian_giây + 24
~~~

Số `16` là độ dài record header cho mỗi gói và `24` là global header của định dạng PCAP cổ điển; PCAPNG, metadata, cơ chế nén và thực tế bắt gói có overhead khác. Nếu 8.000 gói/giây, trung bình lưu 96 byte/gói trong 3.600 giây, ước tính khoảng **3,23 GB** (khoảng **3,00 GiB**) trước khi tính các yếu tố bổ sung. Mức “header-only” vẫn có thể chiếm hàng gigabyte và chứa dữ liệu nhạy cảm khi chạy lâu.

Hệ thống nên đặt trần đồng thời cho **thời lượng**, **dung lượng**, **tốc độ ghi**, **số file** và **quota kho**; cảnh báo sớm khi gần ngưỡng để không gây đầy đĩa hoặc ảnh hưởng các dịch vụ được giám sát. Rotation chỉ giới hạn kích thước file; **không tự thay thế chính sách retention và xóa an toàn**.

## 7. Xử lý, che giấu và chia sẻ kết quả phân tích

### 7.1. Phân biệt bản gốc và bản dùng để chia sẻ

- **Bản gốc:** giữ nguyên byte và metadata cần thiết, lưu mã hóa trong kho chứng cứ với quyền hạn chế, hash và manifest. Không sửa trực tiếp để “xóa tên người dùng”.
- **Bản làm việc:** bản sao thuộc cùng case, có người phụ trách và ngày hết hạn; có thể lọc luồng, tách phần phân tích, nhưng vẫn phân loại nhạy cảm.
- **Bản xuất ra:** ưu tiên bảng flow, thống kê, biểu đồ, timeline và mô tả đã lược bỏ trường không cần thiết. Việc phát hành phải qua kiểm tra đối tượng nhận, mục đích và dữ liệu còn nhận dạng được.

Khi cần ẩn bớt nội dung, có thể giảm độ chính xác timestamp, bỏ payload, thay địa chỉ bằng mã định danh tạm thời hoặc tổng hợp theo nhóm. Nếu phải liên kết cùng một endpoint qua nhiều bản ghi, dùng ánh xạ có kiểm soát hoặc pseudonymization (ví dụ HMAC có khóa được bảo vệ, theo từng vụ việc); **pseudonymization không đồng nghĩa anonymization**.

Cẩn trọng khi chỉnh sửa từng byte trong PCAP: thay đổi payload, độ dài, checksum, TCP sequence hoặc cấu trúc giao thức có thể làm sai kết luận hoặc làm công cụ phân tích diễn giải nhầm. Công cụ sanitization phải được kiểm thử theo giao thức; luôn gắn nhãn bản đã biến đổi, giữ bản gốc có kiểm soát khi cần pháp chứng, và không tuyên bố “đã vô danh” chỉ dựa trên việc thay vài địa chỉ.

### 7.2. Các đường rò rỉ thường bị bỏ sót

- File mở bằng Wireshark trên laptop cá nhân, thư mục Downloads, desktop backup hoặc thư mục đồng bộ đám mây tự động.
- Tệp tạm khi giải nén, giải mã, trích HTTP objects, xuất CSV/JSON hoặc tạo screenshot.
- PCAP đính kèm ticket, email hay link object storage có quyền truy cập mặc định quá rộng.
- `SSLKEYLOGFILE`, file chứa khóa giải mã, chứng chỉ private key hoặc mật khẩu đi kèm tài liệu phân tích.
- Tên file hoặc comment PCAPNG ghi trực tiếp tên khách hàng, email, địa chỉ tài sản.
- Dataset để demo, đào tạo hoặc phát triển bị sao chép từ capture sản xuất mà chưa rà soát.

Một báo cáo đã giảm trường vẫn cần giới hạn đối tượng nhận và thời gian lưu phù hợp vì DNS, IP, timestamp và tên máy có thể là dữ liệu nhạy cảm trong ngữ cảnh tổ chức.

## 8. Hết hạn, xóa dữ liệu và ngoại lệ legal hold

Tại thời điểm `retention_until_utc`, bộ quản lý vòng đời phải kiểm tra tình trạng vụ việc và ngoại lệ hợp lệ trước khi xử lý:

1. **Không còn căn cứ giữ:** ngừng cấp quyền, xóa file trên kho chính theo cơ chế phù hợp, xử lý các phiên bản/bản sao liên quan, ghi trạng thái xóa và xác minh bằng thao tác kiểm tra độc lập.
2. **Vẫn cần giữ cho điều tra:** người có thẩm quyền phê duyệt gia hạn có lý do, phạm vi, người chịu trách nhiệm và ngày đánh giá tiếp theo. Không để ghi chú “đang điều tra” trở thành retention vô hạn.
3. **Legal hold hợp lệ:** đóng băng quá trình xóa đúng những đối tượng nằm trong phạm vi hold, ghi căn cứ và người phê duyệt; hạn chế truy cập, rà soát định kỳ và giải phóng hold khi không còn hiệu lực.

**Xóa logic không chắc chắn là xóa toàn bộ byte.** Kho object có versioning, bản sao liên vùng, snapshot, backup, cache, endpoint tải về và file tạm. Quy trình phải xác định những nơi này được giữ bao lâu, cách xóa hoặc để chúng tự hết hạn, và cách kiểm chứng. Tùy loại phương tiện lưu trữ và tiêu chuẩn tổ chức, có thể áp dụng secure erase hoặc **crypto-erasure** bằng cách hủy khóa mã hóa; crypto-erasure chỉ có hiệu lực khi khóa đó thực sự là con đường cần thiết để giải mã mọi bản sao liên quan và không còn bản plaintext độc lập.

**WORM/immutable storage** giúp ngăn thay đổi chứng cứ trong thời gian đã khóa, nhưng có thể ngăn xóa sớm. Vì vậy phải cấu hình thời hạn phù hợp ngay từ đầu và thiết kế legal hold, retention lock, luật xóa cùng nhau; không đặt chính sách “giữ mãi” như cách tránh quyết định.

### 8.1. Quy trình dọn dẹp có thể kiểm toán

~~~text
Hằng ngày:
  1. Liệt kê manifest có retention_until_utc đã qua.
  2. Đối chiếu tình trạng case, legal hold và phê duyệt gia hạn.
  3. Tìm mọi object version, replica, bản sao làm việc và bản xuất gắn case.
  4. Xóa theo chính sách hoặc ghi nhận đối tượng chờ chu kỳ backup hết hạn.
  5. Kiểm tra lại khả năng truy cập/định danh, tạo deletion record.
  6. Cảnh báo custodian nếu xóa lỗi, metadata thiếu hoặc file không có manifest.
~~~

Deletion record nên có `case_id`, định danh object/bản sao, lớp lưu trữ, chính sách áp dụng, thời điểm, actor/job, kết quả và mã lỗi nếu có. Nhật ký xóa được giữ theo chính sách audit riêng, chỉ chứa thông tin tối thiểu để chứng minh việc thực hiện, không lưu lại payload đã hết hạn.

## 9. Tình huống thực tế: nghi ngờ DNS tunneling

Một hệ thống IDS/IPS cảnh báo máy trạm gửi nhiều DNS query bất thường. Nhóm ứng cứu muốn kiểm tra xem có việc đưa dữ liệu ra ngoài qua DNS hay không.

**Bước 1 — Dựa trên telemetry trước.** Xem DNS log, thống kê tần suất truy vấn, độ dài nhãn, loại bản ghi và đích resolver. Nhiều trường hợp có thể xác định pattern mà không cần PCAP đầy đủ.

**Bước 2 — Nếu phải bắt gói:** tạo case, khoanh vùng IP máy trạm/resolver, giới hạn thời gian và nội dung cần kiểm tra; cân nhắc rằng tên DNS có thể chứa định danh hoặc chính phần dữ liệu nghi bị exfiltration. Chỉ cấp quyền cho nhóm điều tra.

**Bước 3 — Bảo quản:** capture vào kho mã hóa, ghi hash và phạm vi, đánh dấu restricted, áp hạn lưu theo loại vụ việc. Khi phân tích, tránh sao chép nguyên bộ truy vấn vào slide hoặc ticket phổ thông.

**Bước 4 — Báo cáo:** chia sẻ số lượng truy vấn bất thường, tốc độ, loại bản ghi, các khoảng thời gian và tên miền đã được rà soát; chỉ cung cấp các chuỗi truy vấn nguyên bản cho người thật sự cần chứng cứ.

**Bước 5 — Kết thúc:** đánh giá có cần legal hold hay gia hạn hợp lệ không; nếu không, hết hạn thì xóa cả bản gốc, bản làm việc và bản đã xuất theo lịch áp dụng, kiểm tra các bản sao còn tồn tại.

Bài học của tình huống: **phạm vi và mục đích capture** quyết định rủi ro bảo mật lớn hơn nhiều so với việc chọn `.pcap` hay `.pcapng`. Cùng một sự cố có thể dùng telemetry dài hạn và full PCAP rất ngắn, với mức quyền và hạn lưu khác nhau.

## 10. Kiểm tra thiết kế và xử lý sự cố lộ PCAP

Một pipeline retention chỉ đáng tin khi có bài kiểm tra từ đầu đến cuối. Những trường hợp cần diễn tập:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Job capture vượt thời gian/dung lượng | Tự dừng; báo trạng thái và không làm đầy đĩa |
| Người không thuộc case cố đọc/tải PCAP | Bị từ chối; log ghi đầy đủ actor, tài nguyên và kết quả |
| Analyst tạo bản xuất/derived file | Có mã case, nhãn dữ liệu, chủ sở hữu và thời hạn rõ ràng |
| PCAP hết hạn, không có hold | Bị xóa theo chính sách; có record và xác minh |
| PCAP có legal hold hợp lệ | Không bị xóa; có phạm vi, phê duyệt, lịch rà soát |
| Kho có versioning, replica và backup | Quy trình phát hiện và quản lý tuổi thọ của các bản sao |
| Cảm biến tạm mất kết nối với kho | Không ghi plaintext ra vị trí thiếu bảo vệ; có cảnh báo |
| Restore từ backup | Bản được khôi phục vẫn áp dụng phân loại, IAM và chính sách hết hạn |

Nếu nghi ngờ PCAP hoặc khóa giải mã bị lộ:

1. **Khoanh vùng:** thu hồi link và session/token liên quan, tạm ngừng quyền chia sẻ, bảo toàn log truy cập. Không phá hủy chứng cứ cần cho điều tra.
2. **Xác định phạm vi:** liệt kê file, phiên bản, bản xuất, người đã truy cập, dữ liệu/credentials có thể bị ảnh hưởng, cửa sổ thời gian và hệ thống liên quan.
3. **Giảm thiểu tác động:** thu hồi hoặc xoay vòng token, mật khẩu/khóa bị lộ theo đánh giá thực tế; ngăn tải tiếp và giám sát dấu hiệu lạm dụng.
4. **Phối hợp xử lý:** chuyển tới nhóm ứng cứu, an toàn thông tin, pháp chế/bảo vệ dữ liệu và chủ sở hữu liên quan; xác định nghĩa vụ thông báo theo quy định áp dụng.
5. **Khắc phục:** sửa lỗi IAM/lifecycle/điểm xuất dữ liệu, kiểm tra các đường sao chép ngoài dự kiến và cập nhật quy trình, cảnh báo, bài diễn tập.

Không tự động xóa vật chứng của vụ rò rỉ khi chưa xác định yêu cầu bảo toàn; đồng thời không giữ dữ liệu vô hạn sau khi mục đích điều tra đã kết thúc.

## 11. Checklist vận hành trước khi đóng một capture

- [ ] Có mã yêu cầu/case, mục đích cụ thể, chủ dữ liệu và người phê duyệt.
- [ ] Đã thử dùng flow, metric hoặc log trước; nếu cần PCAP, đã chọn scope, interface, filter, snaplen và trần thời gian/dung lượng hợp lý.
- [ ] Đã kiểm tra điểm ghi được mã hóa và giới hạn người có quyền truy cập; không tạo bản plaintext ngoài kiểm soát.
- [ ] Đã ghi manifest, timestamp UTC, phân loại, hash bản gốc và retention deadline.
- [ ] Đã bảo vệ việc truyền, lưu, giải mã, tải xuống và ghi audit; khóa giải mã được quản lý riêng.
- [ ] Đã phân biệt bản gốc, bản làm việc và bản xuất; dữ liệu chia sẻ đã được rà soát.
- [ ] Đã xác định quy trình xóa với object version, replica, backup, snapshot và các bản sao tạm.
- [ ] Đã xác nhận yêu cầu gia hạn hoặc legal hold (nếu có), người chịu trách nhiệm và thời điểm rà soát.
- [ ] Đã kiểm tra job hết hạn, cảnh báo lỗi và lưu bằng chứng xóa.

## 12. Câu hỏi tự kiểm tra

**1. Tại sao filter `port 443` chưa đủ để bảo vệ dữ liệu riêng tư?** Vì nó chỉ chọn lưu lượng; IP, timing, metadata TLS và các trường khác vẫn có thể nhạy cảm, và payload có thể được giải mã trong một số điều kiện.

**2. Một file PCAP đã hết hạn trên bucket chính nhưng vẫn còn trong snapshot thì đã hoàn tất xóa chưa?** Chưa thể kết luận. Phải đối chiếu chính sách và lịch hết hạn snapshot, replica, backup cùng các bản đã tải hoặc xuất.

**3. Có nên sửa trực tiếp bản gốc để xóa cookie trước khi điều tra?** Không. Bảo quản bản gốc nguyên trạng trong kho được kiểm soát; tạo bản làm việc/phiên bản xuất đã giảm dữ liệu và đánh dấu rõ phép biến đổi.

**4. Khi nào được giữ PCAP vượt thời hạn mặc định?** Khi có căn cứ hợp lệ đã được phê duyệt như nhu cầu điều tra cụ thể, yêu cầu pháp lý hoặc legal hold; phải xác định phạm vi, chủ sở hữu và cơ chế rà soát.

**5. Vì sao hash SHA-256 không thay thế kiểm soát truy cập?** Hash chỉ giúp kiểm tra biến đổi so với giá trị tin cậy. Nó không mã hóa nội dung, không ngăn ai đó đọc hoặc tải file, cũng không xác thực độc lập người đã tạo file.

---

**Ghi nhớ:** Giá trị điều tra của PCAP đến từ khả năng quan sát chính xác ở đúng phạm vi và thời điểm. Muốn dùng an toàn trong hệ thống phòng vệ mạng, phải quản trị **thu thập tối thiểu → lưu mã hóa → cấp quyền theo case → phân tích có kiểm soát → hết hạn/xóa có xác minh** trên cả dữ liệu gốc lẫn bản sao.

