# Mô phỏng exfiltration an toàn

**Exfiltration** là hành vi chuyển dữ liệu từ phạm vi mà một tổ chức quản lý sang một vị trí, tài khoản hoặc hệ thống ngoài phạm vi cho phép. Trong tấn công mạng, dữ liệu có thể bị đưa ra ngoài thông qua HTTP(S), dịch vụ lưu trữ, email, DNS, kết nối điều khiển từ xa, công cụ đồng bộ hoặc thiết bị trung gian. Việc chuyển dữ liệu thành công có thể gây mất bí mật kinh doanh, dữ liệu cá nhân, thông tin xác thực và khả năng kiểm soát vận hành.

Trong hoạt động **red team và mô phỏng tấn công mạng**, mô phỏng exfiltration an toàn được dùng để kiểm tra liệu hệ thống bảo vệ có nhận biết, ngăn chặn, ghi nhận và ứng cứu khi xuất hiện hành vi truyền dữ liệu giống với một cuộc tấn công hay không. Bài học thuộc module **SECURITY_NETWORK_SECURITY**: kết hợp phân đoạn, firewall/VPN, DNS, giám sát IDS/IPS, chính sách truy cập cloud và phân tích lưu lượng để đánh giá khả năng bảo vệ dữ liệu ở lớp mạng.

**Nguyên tắc bắt buộc:** chỉ dùng dữ liệu tổng hợp không nhạy cảm và các điểm nhận do nhóm kiểm thử kiểm soát trong phạm vi được phê duyệt. Không thu thập dữ liệu thật, không gửi dữ liệu tới máy chủ ngoài phạm vi, không vô hiệu hóa biện pháp bảo vệ và không cố che giấu phép thử khỏi nhóm chịu trách nhiệm vận hành.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, người học có thể:

1. Giải thích exfiltration trong chuỗi tấn công và phân biệt nó với trao đổi dữ liệu hợp lệ.
2. Thiết kế một cuộc mô phỏng có phạm vi, dữ liệu giả lập, điểm nhận an toàn, ngân sách lưu lượng và điều kiện dừng.
3. Đối chiếu một luồng thử nghiệm với kiểm soát mạng: egress firewall, DNS policy, proxy, VPN, DLP và phân đoạn.
4. Xây dựng bằng chứng từ log nguồn, log đích, NetFlow, firewall, DNS và SIEM mà không lưu dữ liệu nhạy cảm.
5. Đánh giá đồng thời khả năng **phát hiện**, **ngăn chặn**, **phân loại**, **điều tra** và **ứng cứu**.
6. Đề xuất cách sửa và thực hiện retest để chứng minh kiểm soát đã cải thiện.

## 2. Đặt exfiltration trong mô hình đe dọa

Một sự kiện exfiltration thường xuất hiện sau các giai đoạn khác của cuộc tấn công: đối tượng đã có đường truy cập, biết nơi lưu dữ liệu hoặc có khả năng sử dụng một tiến trình gửi mạng. Tuy nhiên, mô phỏng exfiltration **không cần tái hiện xâm nhập ban đầu**. Nhóm kiểm thử có thể tạo một tín hiệu mạng được gắn nhãn rõ ràng từ máy kiểm thử hợp lệ để đánh giá lớp phòng vệ phía sau.

Các mô hình đường đi thường gặp ở cấp độ nhận diện:

| Đường truyền | Bề mặt cần quan sát | Tín hiệu phòng vệ phù hợp |
| --- | --- | --- |
| HTTP/HTTPS ra ngoài | Kết nối tới đích không nằm trong danh sách được phép, POST bất thường, dung lượng outbound | Egress firewall, proxy, DNS, DLP endpoint, SIEM |
| Đồng bộ lên dịch vụ cloud | Tài khoản/tenant lạ, ứng dụng không được duyệt, lượng upload bất thường | CASB/SSE, IAM, audit log và chính sách ứng dụng |
| DNS | Số lượng truy vấn, độ dài tên miền, tỷ lệ lỗi và đích truy vấn bất thường | DNS resolver log, DNS firewall, phân tích hành vi |
| Email/attachment | Gửi ra người nhận bên ngoài, nhãn dữ liệu, loại và kích thước tệp | Email DLP, mail gateway, audit log |
| Kết nối tới mạng đối tác/VPN | Đường liên miền hoặc subnet nguồn không được phép xuất dữ liệu | Segmentation, route policy, VPN log, NDR |
| Lưu lượng mã hóa | Lượng byte, đích, TLS metadata và dữ liệu tại endpoint được bảo vệ | Flow telemetry, proxy, EDR và DLP hợp lệ |

Bảng trên dùng để **lập giả thuyết phát hiện**. Nó không phải hướng dẫn né tránh biện pháp phòng thủ. Khi thiết kế bài kiểm thử, chọn tối đa một hoặc vài luồng đại diện với dữ liệu mẫu và đích kiểm soát được; không thử mọi đường một cách vô hạn.

## 3. Phân biệt các kết quả cần đo

Một gói tin thử nghiệm được gửi đi không đồng nghĩa dữ liệu đã thoát khỏi kiểm soát. Cần định nghĩa rõ bốn mốc:

- **Attempted:** máy kiểm thử đã tạo yêu cầu truyền dữ liệu giả lập.
- **Reached boundary:** yêu cầu đã đi tới firewall, proxy, gateway hoặc policy enforcement point.
- **Delivered:** điểm nhận trong phạm vi kiểm thử đã nhận đủ payload tổng hợp và đối chiếu được request ID.
- **Observed/responded:** thiết bị bảo mật tạo log/alert, con người hoặc playbook xử lý theo mục tiêu đã thỏa thuận.

Một bài kiểm thử tốt có thể **đạt mục tiêu phòng thủ dù việc truyền bị chặn**: ví dụ, firewall từ chối đúng luồng, SIEM nhận sự kiện và SOC phân loại đúng là mô phỏng trong thời gian dự kiến. Ngược lại, việc đích lab nhận dữ liệu không tự chứng minh đã có sự cố bảo mật; phải so sánh kết quả với chính sách cho luồng đó.

## 4. Điều kiện an toàn trước khi bắt đầu

Thiết kế cuộc diễn tập bằng một bản **Rules of Engagement (RoE)** ngắn:

| Quy tắc | Yêu cầu cụ thể |
| --- | --- |
| Phạm vi | Danh sách host nguồn, subnet, điểm nhận, giao thức, khung giờ và môi trường được phép |
| Phê duyệt | Chủ hệ thống, nhóm bảo mật và vận hành xác nhận mục tiêu và quyền kiểm thử |
| Dữ liệu | Chỉ dữ liệu tổng hợp; không dùng hồ sơ khách hàng, token, khóa riêng, backup hay secret |
| Điểm nhận | Loopback hoặc máy chủ thuộc lab; địa chỉ và người quản lý được ghi trong RoE |
| Ngân sách | Số request, kích thước payload, băng thông và thời gian tối đa được giới hạn trước |
| Quan sát | Có thời gian đồng bộ, ID thử nghiệm, log nguồn/đích và luồng SIEM/EDR/DLP thích hợp |
| Dừng khẩn | Có người liên hệ và dấu hiệu dừng: lỗi dịch vụ, tăng tải bất thường, lệch phạm vi hoặc dữ liệu thật |
| Dọn dẹp | Xóa dữ liệu mẫu, thu hồi quyền lab, xác nhận không còn tiến trình/phần mềm thử nghiệm |
| Báo cáo | Ghi chính xác phát hiện, giới hạn kiểm thử và bằng chứng, không suy diễn khả năng của kẻ tấn công |

Với các môi trường có hệ thống sản xuất, cân nhắc một buổi **purple-team exercise**: red team tạo tín hiệu đã phê duyệt, blue team đánh giá telemetry và playbook. Có thể không báo trước thời điểm chính xác cho người phân tích nếu được cấp có thẩm quyền đồng ý, nhưng bộ phận vận hành chịu trách nhiệm an toàn và người có quyền dừng kiểm thử phải biết phạm vi.

Nếu chưa có phê duyệt cho việc gửi lưu lượng giữa các vùng, chỉ dùng **lab loopback** hoặc dữ liệu log giả lập. Chúng vẫn đủ để dạy cơ chế thu thập, phân tích và xác minh tương quan sự kiện.

## 5. Kiến trúc kiểm thử đề xuất

Chia hệ thống thành bốn phần:

1. **Máy phát sinh (emitter):** tạo đúng một thông điệp hoặc tệp giả lập với mã kịch bản.
2. **Đường kiểm soát:** firewall, segment gateway, proxy, DNS resolver hoặc DLP cần đánh giá.
3. **Điểm nhận (collector):** chỉ chấp nhận payload thử nghiệm, thuộc quyền kiểm soát của nhóm vận hành, có giới hạn dung lượng.
4. **Quan sát viên (observer):** thu log nguồn/đích và sự kiện của thiết bị mạng, gửi tới SIEM hoặc nơi lưu bằng chứng đã phê duyệt.

~~~mermaid
flowchart LR
    E["Emitter - dữ liệu giả lập"] --> F["Firewall / proxy / DNS policy"]
    F -->|"ALLOW chỉ khi chính sách cho phép"| C["Collector do tổ chức kiểm soát"]
    F -->|"DENY theo chính sách"| B["Blocked event"]
    E --> L["Endpoint logs"]
    F --> N["Network logs"]
    C --> R["Receipt metadata"]
    B --> S["SIEM / SOC"]
    L --> S
    N --> S
    R --> S
~~~

Mô hình này có thể triển khai thành các tầng kiểm thử:

| Tầng | Môi trường | Mục tiêu |
| --- | --- | --- |
| 0 — tabletop | Mô tả kịch bản và log giả lập | Kiểm tra quyết định phân loại, escalation và playbook |
| 1 — local | Emitter và collector trên 127.0.0.1 | Xác nhận format dữ liệu, request ID, kết quả nhận, không ra khỏi máy |
| 2 — isolated lab | Hai host trong mạng lab không có tuyến Internet | Xác minh log mạng, firewall rule và detection trong điều kiện có luồng thật |
| 3 — approved test segment | Tài sản và điểm nhận được phê duyệt, giới hạn egress | Đánh giá chính sách phân đoạn/egress và quy trình SOC |

Chỉ nâng tầng khi tất cả điều kiện RoE của tầng tiếp theo đã đáp ứng. Ở tầng local, kết quả không thể dùng để kết luận firewall biên, DLP trên Internet hoặc toàn bộ SOC đang hoạt động.

## 6. Thiết kế dữ liệu giả lập

Dữ liệu mẫu phải giúp kiểm tra phát hiện mà không đặt dữ liệu thật vào nguy cơ. Có thể dùng một bản ghi JSON cố định:

~~~json
{
  "simulation": true,
  "exercise_id": "NET-EXFIL-007",
  "record_type": "SYNTHETIC_ONLY",
  "sample_id": "SAMPLE-0001",
  "content": "TRAINING_DATA_NO_REAL_CUSTOMER_INFO"
}
~~~

**Nguyên tắc cấu tạo dữ liệu:**

- Sử dụng tên và giá trị giả định, không sao chép văn bản thật từ CRM, database, thư mục người dùng hoặc email.
- Gắn nhãn dễ nhận biết: exercise ID, record type và sample ID; không trộn với bản ghi sản xuất.
- Nếu cần kiểm tra DLP dựa trên mẫu định dạng (chẳng hạn thẻ thanh toán), dùng **mẫu kiểm thử được nhà cung cấp DLP công bố** hoặc nhãn dữ liệu thử nghiệm; không dùng số thẻ hay PII thật.
- Không đưa secret thật vào URL, HTTP header, query string, filename hoặc console log.
- Ghi nhận **hash** và kích thước của dữ liệu tổng hợp thay vì giữ bản sao payload ở nhiều hệ thống nếu không cần.
- Thiết kế collector từ chối mọi payload không có nhãn lab và giới hạn kích thước nhận.

Với bài kiểm thử chính sách mạng, **không cần nội dung giống dữ liệu bí mật**. Một payload vài trăm byte là đủ để xác nhận khả năng truyền, log, block và tính tương quan giữa các thiết bị.

## 7. Lab an toàn: mô phỏng HTTP POST tới loopback

Lab sau chỉ truyền dữ liệu giả lập qua địa chỉ **127.0.0.1** trên cùng máy. Mục đích là minh họa ba quan sát: yêu cầu được phát sinh, collector có nhận không và bằng chứng xác minh dựa vào request ID. **Không thay địa chỉ loopback thành máy chủ công khai** khi chạy bài tập này.

### 7.1. Bộ thu dữ liệu trong lab

Tạo tệp receiver.py trong thư mục lab và chạy bằng Python 3. Bộ thu chỉ chấp nhận POST ở đường dẫn /ingest, giới hạn body tối đa 4096 byte, kiểm tra JSON và in metadata; không lưu payload xuống đĩa.

~~~python
# receiver.py - lab loopback, chỉ nhận dữ liệu tổng hợp.
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST, PORT = "127.0.0.1", 8765
MAX_BODY = 4096

class LabReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/ingest":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return

        if not (0 < length <= MAX_BODY):
            self.send_error(413)
            return

        if self.headers.get("Content-Type") != "application/json":
            self.send_error(415)
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return

        if not isinstance(payload, dict):
            self.send_error(400)
            return
        if (payload.get("simulation") is not True
                or payload.get("exercise_id") != "NET-EXFIL-007"
                or payload.get("record_type") != "SYNTHETIC_ONLY"):
            self.send_error(403)
            return

        # Chỉ log metadata, không ghi content của payload.
        print("ACCEPTED", payload.get("exercise_id"),
              payload.get("sample_id"), "bytes=", length, flush=True)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Ẩn log request chung để tránh ghi body và thông tin không cần.
        pass

HTTPServer((HOST, PORT), LabReceiver).serve_forever()
~~~

Bộ thu này phù hợp với lab đơn giản trên máy cá nhân. Nó **không** phải dịch vụ tiếp nhận dữ liệu được thiết kế để triển khai trong mạng thực tế: không có xác thực mạnh, TLS, quản lý vòng đời hay hệ thống cấp quyền. Cơ chế ràng buộc loopback và nhãn synthetic nhằm làm rõ giới hạn bài tập.

### 7.2. Bộ phát dữ liệu mẫu

Mở terminal khác trên cùng máy, tạo emitter.py. Bộ phát có địa chỉ và dữ liệu cố định; không quét ổ đĩa, không mở tệp người dùng, không nhận tham số thay đích đến.

~~~python
# emitter.py - một thông điệp synthetic đến loopback duy nhất.
import json
from urllib.request import Request, ProxyHandler, build_opener

message = {
    "simulation": True,
    "exercise_id": "NET-EXFIL-007",
    "record_type": "SYNTHETIC_ONLY",
    "sample_id": "SAMPLE-0001",
    "content": "TRAINING_DATA_NO_REAL_CUSTOMER_INFO",
}
body = json.dumps(message, separators=(",", ":")).encode("utf-8")

request = Request(
    "http://127.0.0.1:8765/ingest",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
# Không dùng proxy hệ thống; lab này chỉ nhắm loopback.
opener = build_opener(ProxyHandler({}))
with opener.open(request, timeout=3) as response:
    print("HTTP status:", response.status)
    print("Sample ID:", message["sample_id"], "bytes:", len(body))
~~~

Kết quả dự kiến: bộ phát nhận HTTP 204; bộ thu in mã **NET-EXFIL-007**, **SAMPLE-0001** và kích thước. Đây là ví dụ về **đã nhận payload tổng hợp trong loopback**, chưa chứng minh dữ liệu đi qua firewall hay ra ngoài tổ chức.

Để minh họa trường hợp chặn, có thể dừng collector rồi chạy emitter lại. Lần này bộ phát nhận lỗi kết nối, nhưng **không nên gọi đó là firewall block**: dịch vụ đích đơn giản là không lắng nghe. Trong kiểm thử thật, phải đối chiếu firewall log/rule để xác nhận lớp nào đã chặn.

### 7.3. Bằng chứng lab nên lưu

| Thành phần | Bằng chứng | Cách diễn giải |
| --- | --- | --- |
| Emitter | Sample ID, thời điểm, số byte, HTTP status/error | Có yêu cầu thử nghiệm tại nguồn |
| Collector | Sample ID nhận và thời điểm | Payload giả lập đến đúng điểm nhận |
| Host | Loopback 127.0.0.1:8765, tiến trình lab | Không có đường gửi tới mạng bên ngoài |
| Network control | Không có bằng chứng firewall biên trong lab local | Chưa đánh giá năng lực ngăn chặn egress thực tế |

Kết thúc lab bằng cách dừng tiến trình receiver, đóng terminal, xóa tệp thử nghiệm nếu không cần lưu và xác nhận không có listener còn hoạt động trên cổng lab.

## 8. Xây dựng các kịch bản kiểm thử phòng thủ

Khi chuyển sang test segment được phê duyệt, mỗi kịch bản cần một **giả thuyết kiểm soát** và kết quả mong đợi. Có thể dùng các kịch bản sau mà không cần gửi dữ liệu nhạy cảm:

| Kịch bản | Hành vi mô phỏng được duyệt | Mong đợi từ blue team | Bằng chứng |
| --- | --- | --- | --- |
| EGRESS-01: đích ngoài danh sách | Một request nhỏ chứa synthetic marker tới collector lab bị policy từ chối | Firewall/proxy chặn và ghi log | Rule ID, source/destination, disposition |
| EGRESS-02: đích đã phê duyệt | Một request tương tự tới collector nội bộ được phép | Truyền thành công, log đúng luồng | Source/collector receipts, flow log |
| DLP-01: nhãn dữ liệu | Tệp synthetic mang nhãn thử nghiệm đi qua kênh DLP được hãng hỗ trợ | DLP tạo alert hoặc block theo chính sách | DLP incident ID, policy name |
| SEG-01: vùng khách | Thiết bị lab trong VLAN khách thử kết nối tới dịch vụ nhận quản trị/nội bộ không cho phép | Phân đoạn chặn | ACL/firewall log, phép đo từ VLAN |
| DNS-01: chính sách phân giải | Truy vấn domain thử nghiệm do tổ chức sở hữu, được định nghĩa trước trong policy | Resolver ghi nhận, block/allow đúng rule | DNS log và verdict |
| SOC-01: diễn tập ứng cứu | Phát lại một tập sự kiện giả lập qua môi trường test của SIEM | Rule, alert, triage và escalation đúng | Detection ID, ticket, timeline |

Đối với kịch bản DNS, **không cần nhúng dữ liệu vào tên truy vấn**, không thử truyền từng phần dữ liệu theo chuỗi DNS và không vượt hạn mức query. Chỉ dùng domain lab được cấp quyền cùng mẫu truy vấn đơn giản để kiểm tra logging, giải quyết tên và chính sách.

**Kiểm soát kỳ vọng có thể khác nhau:** luồng synthetic tới collector được phê duyệt nên được allow, còn luồng tới điểm nhận không được phê duyệt nên bị deny. Không đánh đồng “chặn mọi thứ” với bảo mật tốt: rule quá rộng có thể làm gián đoạn hoạt động hợp lệ.

## 9. Phương pháp thu thập telemetry

Không thể kết luận exfiltration được phát hiện chỉ từ thông báo “blocked” trên máy phát. Cần ghép các nguồn chứng cứ:

| Nguồn | Trường cần quan sát | Ý nghĩa |
| --- | --- | --- |
| Endpoint/EDR | Host ID, process name, user, timestamp, network connection | Tiến trình tạo kết nối và ngữ cảnh trên máy nguồn |
| Firewall/NAT | Source/destination, port, bytes, session ID, rule ID, action | Đường kết nối đã qua lớp kiểm soát nào; bị chặn hay cho phép |
| Proxy/SWG | URL host, method, policy, verdict, transferred bytes | Nhận biết kênh HTTP(S) ở nơi có visibility phù hợp |
| DNS resolver | Client, query, response code, domain, policy verdict | Phân giải tên, domain bị từ chối, hành vi khác thường |
| NDR/NetFlow/IPFIX | Five-tuple, bytes in/out, duration, timestamps | Lượng dữ liệu và đường truyền; thường không có nội dung payload |
| DLP/CASB | Policy, nhãn dữ liệu, kênh, decision, incident ID | Kiểm tra dữ liệu theo phân loại và luồng kinh doanh |
| Collector lab | Exercise ID, sample ID, receipt status, bytes | Xác nhận có nhận được đúng thông điệp tổng hợp |
| SIEM/SOAR | Rule ID, alert, người xử lý, thời gian, ticket | Khả năng phát hiện, phân loại và phản ứng |

Lưu ý kỹ thuật:

- **Flow log không phải packet capture:** biết kích thước, hướng và thời gian không có nghĩa đã đọc được nội dung.
- **TLS được mã hóa:** firewall thuần túy có thể chỉ thấy metadata; để đánh giá nội dung cần công cụ ở endpoint hoặc điểm inspection được cho phép.
- **NAT thay đổi địa chỉ:** phải tương quan pre-NAT, post-NAT và các ID phiên để không gán sai host.
- **Clock drift:** nếu timestamp không đồng bộ, thứ tự sự kiện có thể bị hiểu sai. Dùng NTP và ghi timezone.
- **Dữ liệu DLP nhạy cảm:** chỉ lưu nhãn/phát hiện tối thiểu, áp dụng retention và phân quyền cho hệ thống logging.

## 10. Thiết kế quy tắc phát hiện

Mục tiêu bài tập là đánh giá xem tín hiệu có được nhận diện đúng không, không phải tạo mọi loại lưu lượng có thể bị nghi ngờ.

### 10.1. Phát hiện theo chính sách

Một phương án là quy tắc **host thuộc management VLAN chỉ được upload ra một tập đích được phép**. Khi có phiên tới đích khác, firewall chặn và SIEM ghi sự kiện.

~~~text
PSEUDOCODE DETECTION

WHEN
  network.action == "deny"
  AND network.source_zone == "MGMT"
  AND network.reason == "EGRESS_NOT_APPROVED"
THEN
  create_event(
    category="potential_exfiltration_attempt",
    exercise_id=extract_if_present("NET-EXFIL-007"),
    include=["src_host", "dst_host", "dst_port", "bytes", "rule_id", "time"]
  )
~~~

Đây là **mã giả**, không dùng trực tiếp để cấu hình firewall hoặc SIEM. Rule thật phụ thuộc schema log và có thể phải kết hợp inventory, proxy và danh sách ngoại lệ.

### 10.2. Phát hiện bất thường theo lượng dữ liệu

Một số tình huống không vi phạm allowlist nhưng có lưu lượng upload bất thường. Có thể so sánh outbound bytes trong cửa sổ thời gian với baseline cùng nhóm thiết bị và giờ làm việc.

~~~text
PSEUDOCODE

group by host, destination_category, 15_min_window
outbound_total = sum(bytes_sent)
baseline = historical_distribution(host_role, destination_category, time_of_day)

if outbound_total significantly exceeds baseline
   and destination is not an approved data-transfer workflow:
    create_anomaly_for_triage()
~~~

Không thiết lập ngưỡng ngẫu nhiên và kết luận đã exfiltrate: hệ thống backup, log shipping, cập nhật firmware hoặc replication cũng tạo lượng dữ liệu lớn. Để tránh false positive, dùng baseline theo vai trò, loại ứng dụng, thời gian và nhãn chính sách. Trong lab với một payload nhỏ, mục tiêu thích hợp hơn là xác minh **telemetry và rule chính sách**; nó không đủ để đánh giá độ nhạy của thuật toán phát hiện volumetric exfiltration.

### 10.3. Tương quan nhiều nguồn

Giả sử firewall ghi DENY cùng thời điểm endpoint ghi thao tác upload và collector không có receipt. Khi đó, kết luận có cơ sở là **luồng mô phỏng bị chặn theo rule**. Nếu collector có receipt nhưng firewall log không xuất hiện, cần kiểm tra đường khác, NAT, bypass qua proxy hợp lệ hoặc khoảng trống telemetry trước khi kết luận đã có đường tấn công.

## 11. Đánh giá bằng ma trận mục tiêu và kết quả

Mỗi scenario nên có các trường:

| Trường | Ví dụ |
| --- | --- |
| Exercise ID | NET-EXFIL-007 |
| Scenario ID | EGRESS-01 |
| Đích thử nghiệm | Collector lab thuộc quyền quản lý của tổ chức |
| Vùng nguồn | Test VLAN hoặc host được phê duyệt |
| Dữ liệu | JSON synthetic vài trăm byte, có sample ID |
| Chính sách mong đợi | DENY bởi firewall rule EGRESS_RESTRICT |
| Quan sát tại nguồn | Có request ID và lỗi kết nối hoặc status |
| Quan sát tại boundary | Log DENY với rule ID |
| Quan sát tại đích | Không nhận được sample ID |
| SOC detection | Tạo alert với host, đích và verdict |
| Quyết định | PASS nếu cả hành vi chặn và bằng chứng đều phù hợp |
| Sai lệch | Nếu collector nhận được, kiểm tra tuyến, rule và phạm vi |

Nên chấm riêng từng tiêu chí:

- **Prevent:** kiểm soát có chặn đường trái phép hay không?
- **Detect:** có event/alert đúng với request ID và bối cảnh không?
- **Respond:** SOC có nhận diện, triage và chuyển xử lý theo SLA mục tiêu không?
- **Contain:** có hướng xử lý phù hợp khi mô phỏng tình huống thật không?
- **Recover:** có duy trì luồng hợp lệ và đưa hệ thống về trạng thái bình thường không?

Các mức PASS/FAIL cần định nghĩa **trước khi** phát lưu lượng. Nếu scenario không có telemetry bắt buộc, phải ghi là **INCONCLUSIVE** thay vì tự suy ra đã có hoặc không có exfiltration.

## 12. An toàn vận hành và ngưỡng dừng

Trong mô phỏng mạng, rủi ro thường đến từ thao tác thử không kiểm soát, không chỉ từ dữ liệu. Cần áp dụng:

1. **Giới hạn thể tích:** ví dụ một thông điệp synthetic nhỏ mỗi kịch bản, số request và tốc độ xác định trong RoE.
2. **Không mở rộng nguồn:** không tự lan sang host mới, không lấy dữ liệu từ ổ đĩa hoặc tài khoản khác.
3. **Không thay đổi chính sách để ép lưu lượng đi qua:** nếu bị chặn, ghi nhận là kết quả; mọi điều chỉnh firewall/proxy cần quy trình change riêng.
4. **Không tạo hành vi ẩn danh hoặc né giám sát:** bài tập phải phục vụ đánh giá kiểm soát, không sử dụng kỹ thuật làm mờ danh tính hoặc qua mặt DLP/IDS/IPS.
5. **Không đưa tài sản thật vào lab:** bản sao dữ liệu có thông tin thật vẫn là dữ liệu nhạy cảm, kể cả khi nằm trong môi trường test.
6. **Có điều kiện dừng:** ứng dụng chậm bất thường, IDS/IPS báo ảnh hưởng diện rộng, lỗi route/HA, lệch scope hoặc phát hiện dữ liệu thật trong payload.
7. **Dọn trạng thái:** dừng emitter/collector, xóa dữ liệu mẫu, thu hồi tạm quyền, đối chiếu log và biên bản thay đổi.

## 13. Các sai lầm thường gặp

| Sai lầm | Vì sao gây sai lệch | Cách sửa |
| --- | --- | --- |
| Gửi dữ liệu thật để “đánh giá thực tế” | Có thể tạo sự cố bảo mật trong chính buổi diễn tập | Dùng synthetic marker và mẫu thử đã được phê duyệt |
| Dùng điểm nhận tùy tiện ngoài Internet | Tạo đường thoát dữ liệu ngoài quyền kiểm soát | Dùng collector do tổ chức quản lý, không có tuyến Internet ở lab cơ bản |
| Chỉ nhìn thấy HTTP 200 rồi kết luận “bị exfil” | Chưa biết đường mạng, đích và chính sách | Đối chiếu collector receipt, hash/sample ID và rule |
| Không có phép thử allow hợp lệ | Rule có thể chặn cả tác vụ kinh doanh thiết yếu | Kiểm tra đồng thời luồng được phép và luồng bị cấm |
| Không gắn exercise ID | Khó tìm sự kiện giữa log thật | Dùng ID nhất quán ở emitter, collector và ticket |
| Dựa vào một log duy nhất | Có thể sai thời gian, bị NAT hoặc mất log | Correlate endpoint, network, collector và SIEM |
| Cho rằng TLS làm mất mọi khả năng giám sát | Vẫn có metadata và telemetry endpoint | Phối hợp flow, proxy, EDR và DLP được cho phép |
| Đánh đồng alert với incident | Alert có thể là false positive hoặc bài tập | Quy trình xác minh bối cảnh và phân loại |
| Tắt DLP/IPS để bài tập “thành công” | Vô hiệu hóa mục tiêu kiểm soát và tăng rủi ro | Giữ chính sách; ghi nhận kết quả bị chặn |
| Không retest sau khi sửa | Không xác nhận được hiệu quả lâu dài | Chạy lại cùng nguồn/đích và các phép kiểm tra âm/dương |

## 14. Tình huống diễn tập có phân tích

### Tình huống A — Chính sách egress chặn đúng

Emitter trong test VLAN thử gửi JSON synthetic tới collector lab nằm ở mạng không được phép theo ma trận. Firewall trả DENY, collector không có receipt, SIEM nhận log và SOC mở ticket.

**Kết luận phù hợp:** đường dữ liệu thử nghiệm đã bị chặn theo chính sách; phát hiện và quy trình ghi nhận có hoạt động trong phạm vi kịch bản. **Chưa thể kết luận:** mọi dạng exfiltration đều bị chặn hoặc IDS/IPS có thể phát hiện payload mã hóa.

### Tình huống B — Collector nhận được dù policy dự kiến DENY

Collector trong test segment ghi nhận sample ID hợp lệ. Firewall log ở đường dự kiến không có event tương ứng.

**Hướng điều tra:** kiểm tra route và NAT, proxy, security group, policy áp trên đúng interface, tunnel/site-to-site VPN và tính đồng bộ thời gian. Ghi finding về sai lệch đường egress hoặc thiếu quan sát nếu xác nhận được. Không mở rộng sang đích ngoài phạm vi để “chứng minh thêm”.

### Tình huống C — DLP không phát cảnh báo với marker tổng hợp

Upload synthetic được phép, collector nhận đúng dữ liệu, nhưng DLP không báo.

**Phân tích:** nếu marker không nằm trong chính sách nhận diện của DLP, đây chưa phải thất bại của DLP. Cần xác nhận yêu cầu rule, phạm vi ứng dụng, vị trí điểm enforcement, nhãn và kiểu dữ liệu. Dùng mẫu kiểm thử do chính sách DLP định nghĩa rồi lặp lại có kiểm soát.

### Tình huống D — Firewall chặn nhưng SOC không thấy alert

Firewall có log DENY, collector không nhận dữ liệu nhưng SIEM không có alert hoặc log bị trễ vượt SLA.

**Kết luận:** khả năng chặn mạng đạt yêu cầu, còn **khả năng giám sát/ứng cứu** chưa đạt mục tiêu của kịch bản. Cần kiểm tra đường chuyển log, parser, mapping field, detection rule và mức ưu tiên alert.

### Tình huống E — Luồng hợp lệ bị chặn sau hardening

Sau khi siết egress, request synthetic không được phép đã bị chặn. Nhưng một ứng dụng backup được phê duyệt cũng mất kết nối tới kho nội bộ.

**Kết luận:** remediation chưa hoàn tất do làm gián đoạn luồng hợp lệ. Cần xác minh rule theo đúng nguồn, đích, ứng dụng và quyền; retest cả phép thử từ chối và phép thử cho phép.

## 15. Báo cáo phát hiện và hướng khắc phục

Mẫu báo cáo giả lập:

~~~text
EXERCISE: NET-EXFIL-007
SCENARIO: EGRESS-01
STATUS: FAIL (theo tiêu chí kiểm soát đã thỏa thuận)
SCOPE: host kiểm thử và collector lab do tổ chức quản lý
DATA: synthetic JSON, SAMPLE-0001, 188 bytes (ví dụ)
EXPECTED: DENY vì đích không được phê duyệt
OBSERVED:
  - Emitter: request created at 14:00:00 +07:00
  - Firewall: no matching DENY event at expected boundary
  - Collector: received SAMPLE-0001 at 14:00:01 +07:00
FINDING: chính sách egress chưa được áp trên đường thử nghiệm
EVIDENCE: source event, collector receipt, route/rule snapshot, log IDs
LIMIT: chỉ đánh giá một luồng tổng hợp; chưa kiểm thử các đường khác
OWNER: nhóm quản trị mạng / security engineering
ACTION: sửa policy tại boundary và retest cả allow/deny scenarios
~~~

**Các trường bắt buộc trong báo cáo thật:** phạm vi và phê duyệt, phương pháp, thời gian và timezone, danh tính nguồn/đích, dữ liệu synthetic, kết quả mong đợi/thực tế, evidence ID, hạn chế, mức ưu tiên, owner, hành động khắc phục và kết quả retest.

Không đưa token, dữ liệu cá nhân, credential, bản dump cấu hình chứa bí mật hoặc payload thật vào ticket. Nếu phải chia sẻ log, thực hiện phân quyền và che trường nhạy cảm theo quy định.

### Các nhóm khắc phục thường gặp

- **Mạng:** egress deny mặc định theo vùng phù hợp, allowlist nguồn/đích cần thiết, segmentation cho dữ liệu và quản trị.
- **DNS:** resolver được kiểm soát, chặn phân giải theo chính sách, log truy vấn, phát hiện sử dụng resolver ngoài quy định.
- **Endpoint:** EDR và DLP với danh mục dữ liệu, nhãn phân loại và giám sát tác vụ upload.
- **Cloud/SaaS:** kiểm soát tenant, ứng dụng được phê duyệt, IAM, audit log và policy chia sẻ.
- **Quan sát:** chuẩn hóa timestamp, parser, flow logs, correlation ID, SIEM rule và playbook.
- **Quy trình:** review ngoại lệ có thời hạn, thay đổi được phê duyệt, quản lý owner và lịch retest.

## 16. Xác minh sau khắc phục

Chạy lại **cùng ma trận** và thêm phép thử hợp lệ để bảo đảm thay đổi có hiệu lực:

| Tiêu chí | Trước sửa giả định | Sau sửa mong đợi |
| --- | --- | --- |
| Egress ngoài allowlist | Collector nhận synthetic | Không nhận, log DENY đúng rule |
| Egress hợp lệ | Collector nội bộ nhận | Vẫn nhận đầy đủ |
| Telemetry mạng | Thiếu log hoặc thiếu field | Có source, destination, action, timestamp |
| Tương quan SIEM | Không tạo event liên quan | Có event/alert với scenario ID |
| Triage SOC | Chậm hoặc sai phân loại | Đúng mức và trong SLA đã thống nhất |
| Tác động vận hành | Chưa rõ | Không gián đoạn tác vụ hợp lệ |

Nếu firewall DENY nhưng không có log, cần đánh dấu kết quả **ngăn chặn đạt / quan sát chưa đạt**, không gộp thành PASS toàn phần. Nếu SIEM alert nhưng collector vẫn nhận dữ liệu trái phép, **phát hiện đạt / ngăn chặn chưa đạt**.

## 17. Checklist trước, trong và sau cuộc diễn tập

### Trước khi chạy

- [ ] Phạm vi, owner, thời gian, điểm dừng và người liên hệ đã được phê duyệt.
- [ ] Dữ liệu synthetic được kiểm tra, gắn exercise ID và sample ID.
- [ ] Điểm nhận thuộc quyền kiểm soát của tổ chức; không có dữ liệu sản xuất.
- [ ] Đã định nghĩa ALLOW/DENY mong đợi theo vùng nguồn và điểm đích.
- [ ] Ngưỡng số request, kích thước và băng thông đã chốt.
- [ ] Bật log cần thiết, đồng bộ giờ và xác nhận đường ingest SIEM.

### Trong khi chạy

- [ ] Thực hiện đúng scenario, không mở rộng phạm vi.
- [ ] Lưu timestamp, ID, số byte và kết quả tại máy phát.
- [ ] Đối chiếu network control và receipt ở collector.
- [ ] Ghi nhận alert, người triage, quyết định và thời gian phản ứng.
- [ ] Dừng ngay nếu có lệch scope, ảnh hưởng vận hành hoặc dữ liệu thật.

### Sau khi chạy

- [ ] Dừng emitter/collector, dọn dữ liệu và quyền tạm thời.
- [ ] Tương quan chứng cứ nhiều nguồn; phân loại PASS/FAIL/INCONCLUSIVE.
- [ ] Ghi finding cụ thể, owner, remediation và ngày retest.
- [ ] Kiểm tra luồng hợp lệ còn hoạt động sau khắc phục.
- [ ] Lưu báo cáo và bài học kinh nghiệm theo chính sách bảo mật.

## 18. Câu hỏi ôn tập

1. Vì sao nên dùng dữ liệu tổng hợp ngay cả khi cuộc kiểm thử đã được ban quản trị cho phép?
2. Một request HTTP được tạo nhưng collector không nhận được: còn thiếu những bằng chứng nào để nói firewall đã chặn?
3. Điều gì khác nhau giữa **ngăn chặn exfiltration** và **phát hiện nỗ lực exfiltration**?
4. Trong môi trường TLS, nguồn dữ liệu giám sát nào có thể bổ sung cho flow logs?
5. Khi DLP không báo trên một chuỗi synthetic không có rule nhận diện, có thể kết luận DLP lỗi không?
6. Vì sao kiểm thử sau khắc phục phải có cả kịch bản ALLOW và DENY?
7. Cần quy định điều kiện dừng nào để tránh biến buổi diễn tập thành sự cố mạng?
8. Trong báo cáo, vì sao phải ghi rõ giới hạn phạm vi và không suy từ một luồng thành kết luận cho toàn hệ thống?

**Ghi nhớ:** mô phỏng exfiltration an toàn tạo **tín hiệu giả lập có kiểm soát** để kiểm nghiệm các lớp phòng vệ mạng và năng lực SOC. Giá trị của buổi diễn tập nằm ở việc đo chính xác đường truyền, chính sách ngăn chặn, telemetry và phản ứng; mọi thử nghiệm phải dùng dữ liệu synthetic, điểm nhận đáng tin, giới hạn lưu lượng và bằng chứng tái lập được.

