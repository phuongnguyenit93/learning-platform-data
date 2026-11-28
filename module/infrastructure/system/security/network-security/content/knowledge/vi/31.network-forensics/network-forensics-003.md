# Phân tích flow để dựng communication graph

## 1. Communication graph giải quyết câu hỏi nào?

Trong **điều tra số trên mạng (network forensics)**, một câu hỏi thường gặp là: *thiết bị nào đã liên lạc với thiết bị nào, vào lúc nào, bằng giao thức nào và với lượng lưu lượng bao nhiêu?* Trả lời câu hỏi này giúp khoanh vùng tài sản liên quan, dựng lại trình tự sự kiện, phát hiện kết nối xuyên phân đoạn và xác định phần chứng cứ cần kiểm tra sâu hơn.

**Flow** là bản ghi tóm tắt lưu lượng đã quan sát. Tùy công nghệ, nó mô tả các gói cùng tập thuộc tính như địa chỉ IP nguồn và đích, giao thức, cổng, thời gian, số gói, số byte, trạng thái TCP hoặc hành động firewall. Một bản ghi có thể biểu diễn **một chiều** hoặc **hai chiều**, và nhiều bản ghi có thể thuộc cùng một phiên do exporter chia theo thời gian. Flow chủ yếu chứa **metadata**, không tiết lộ toàn bộ nội dung ứng dụng.

**Communication graph (đồ thị liên lạc)** dùng các **đỉnh (nodes)** biểu diễn thực thể và **cạnh có hướng (directed edges)** biểu diễn lưu lượng giữa các thực thể trong một khoảng thời gian. Chuyển flow thành graph giúp nhìn thấy nhóm kết nối mà từng dòng log riêng lẻ khó thể hiện, chẳng hạn một máy lần lượt kết nối nhiều đích TCP/445, nhiều thiết bị cùng gọi một máy chủ mới, hoặc luồng ra ngoài Internet tăng bất thường.

Bài học thuộc module **SECURITY_NETWORK_SECURITY**, gắn việc phân tích lưu lượng với phân đoạn mạng, firewall, VPN, IDS/IPS, DNS và hạ tầng đám mây. Mục tiêu của đồ thị là tạo **bản đồ quan hệ liên lạc có thể kiểm chứng**, từ đó hỗ trợ giám sát xâm nhập và điều tra. Bản thân một cạnh trên graph chưa chứng minh có hành vi tấn công.

Sau bài học, người học có thể:

- Đọc và phân biệt NetFlow/IPFIX, sFlow, Zeek và cloud flow logs.
- Chuẩn hóa dữ liệu, khắc phục các sai lệch do thời gian, NAT, lấy mẫu và nhiều điểm thu.
- Chọn kiểu đỉnh, cạnh, trọng số và cửa sổ thời gian phù hợp với câu hỏi điều tra.
- Tự dựng graph có hướng từ các flow mẫu bằng Python và xuất Graphviz DOT.
- Phân tích fan-out, các đích mới, cạnh giữa vùng bảo mật và sự biến đổi theo thời gian.
- Từ graph hình thành giả thuyết, tìm chứng cứ đối chiếu và báo cáo giới hạn kết luận.

## 2. Những nguồn flow có thể sử dụng

| Nguồn | Đặc điểm | Lưu ý khi phân tích |
| --- | --- | --- |
| **NetFlow** | Exporter trên router/switch/thiết bị mạng xuất bản ghi tổng hợp luồng | Version và cách cấu hình quyết định số trường; cache timeout có thể chia một kết nối thành nhiều record |
| **IPFIX** | Truyền bản ghi với information elements và template | Lưu template, exporter, observation domain và ý nghĩa từng bộ đếm; trường mở rộng có thể khác nhau |
| **sFlow** | Lấy mẫu gói kèm bộ đếm giao diện | Thường không phải toàn bộ phiên; thiếu quan sát không có nghĩa là không có liên lạc |
| **Zeek conn.log** | Tóm tắt kết nối, hướng orig/resp, trạng thái, thời lượng, byte và gói | Phải hiểu các trường orig/resp và ý nghĩa byte của Zeek trước khi so sánh với exporter khác |
| **Cloud flow logs** | Thống kê lưu lượng ở các tài nguyên mạng đám mây | Khoảng tổng hợp, dữ liệu bị bỏ qua, action và vị trí thu khác nhau theo nền tảng |
| **Firewall, VPN và proxy logs** | Có thể cung cấp rule, action, NAT, user, phiên và ứng dụng | Là nguồn đối chiếu bổ trợ, không nhất thiết có cùng ngữ nghĩa với flow thô |

Ví dụ, trường **orig_bytes** và **resp_bytes** của Zeek không mặc nhiên tương ứng trực tiếp với hai bộ đếm byte từ NetFlow. Cần hiểu đơn vị, chiều và phạm vi byte của **từng nguồn** trước khi cộng số liệu hoặc vẽ độ dày cạnh.

Thông thường, flow không thể tự trả lời: nội dung tệp đã truyền là gì, ai trực tiếp vận hành thiết bị, dữ liệu có nhạy cảm hay không, hoặc một yêu cầu HTTPS có thành công ở mức nghiệp vụ hay không. Muốn trả lời phải kết hợp PCAP được thu thập hợp lệ, proxy/DNS logs, log xác thực, EDR, hệ thống quản lý tài sản và nhật ký ứng dụng.

### 2.1. Schema chuẩn hóa đề xuất

| Field | Mục đích |
| --- | --- |
| **start_time**, **end_time** | Xác định thời điểm và khoảng hoạt động; quy về UTC khi tổng hợp nhiều nguồn |
| **src_ip**, **dst_ip** | Hai đầu lưu lượng tại điểm quan sát, chưa chắc là danh tính thiết bị cuối cùng |
| **src_port**, **dst_port**, **protocol** | Phân biệt dịch vụ/giao thức, định danh flow TCP/UDP |
| **bytes**, **packets** | Trọng số cạnh; phải ghi định nghĩa chiều và cách đếm |
| **tcp_flags**, **conn_state** | Dấu hiệu thiết lập hoặc kết thúc kết nối khi nguồn hỗ trợ |
| **exporter_id**, **observation_point** | Truy ngược nơi đo và xử lý record quan sát trùng |
| **sampling_rate**, **record_type** | Nhận diện dữ liệu lấy mẫu, mức độ đầy đủ và kiểu bản ghi |
| **ingress_if**, **egress_if**, **action** | Hỗ trợ xác định đường đi/chính sách nếu được thu thập |
| **asset_id**, **src_zone**, **dst_zone** | Thông tin làm giàu từ kiểm kê/CMDB, DHCP, inventory |
| **source_record_id**, **case_id** | Liên kết cạnh với chứng cứ gốc và vụ điều tra |

Nếu giao thức là ICMP hoặc giao thức không dùng TCP/UDP port, cần dùng các trường tương ứng (như ICMP type/code), không tự tạo cổng ảo rồi coi như giao thức TCP.

### 2.2. Hiểu đúng chiều của bản ghi

Với **flow một chiều**, mũi tên nguồn → đích phản ánh chiều lưu lượng tại điểm thu. Với bản ghi hai chiều, cần xác định rõ bên khởi tạo (*originator*) và bên phản hồi (*responder*); không mặc định có hai record riêng. Các đếm byte theo hướng phản hồi không nên tự động cộng vào chiều đi nếu mục tiêu điều tra là xác định nguồn phát sinh lưu lượng.

**Nguồn trong flow không đồng nghĩa kẻ tấn công.** DNS resolver, hệ thống cập nhật, bộ giám sát hoặc ứng dụng backend có thể tự chủ động kết nối tới nhiều dịch vụ hợp lệ. Ngược lại, hệ thống đã bị xâm nhập có thể xuất hiện ở phía đích nếu đang bị điều khiển từ bên ngoài.

## 3. Quy trình từ bản ghi đến đồ thị

~~~mermaid
flowchart LR
    A["Thu NetFlow / IPFIX / sFlow / Zeek / Cloud"] --> B["Bảo toàn dữ liệu gốc"]
    B --> C["Chuẩn hóa field và thời gian"]
    C --> D["Đánh dấu thiếu, sampling, record trùng"]
    D --> E["Làm giàu NAT, DHCP, DNS, tài sản, zone"]
    E --> F["Chọn node, edge, thời gian, trọng số"]
    F --> G["Tổng hợp communication graph"]
    G --> H["So baseline, tìm thay đổi đáng chú ý"]
    H --> I["Kiểm chứng bằng log, PCAP, EDR và chính sách"]
~~~

### Bước 1 — Chọn câu hỏi điều tra

Một graph IP → IP phù hợp khi muốn biết máy trạm có liên lạc với những đích nào. Một graph **zone → zone** hữu ích để phát hiện luồng vượt phân đoạn; graph **service → service** thích hợp để hiểu phụ thuộc ứng dụng. Nếu cần dựng trình tự di chuyển ngang, giữ các cạnh với timestamp hoặc tách thành nhiều graph theo cửa sổ nhỏ.

Đừng chọn graph chỉ vì dễ vẽ. Hãy xác định trước **đỉnh là gì, cạnh biểu diễn điều gì, thời điểm nào, nguồn nào và trọng số tính ra sao**. Với các nguồn khác nhau, cần lập bảng ánh xạ field rõ ràng.

### Bước 2 — Bảo toàn và chuẩn hóa

1. **Giữ raw logs**: ghi nguồn, thời gian thu, phương pháp xuất, định danh tệp, giá trị hash và người thực hiện; tạo bản dẫn xuất riêng để phân tích.
2. **Đồng nhất thời gian**: chuẩn hóa múi giờ về UTC, kiểm tra NTP, clock skew, độ trễ export và khoảng log bị mất. Lưu cả event time và collection time nếu có.
3. **Đồng nhất giao thức và địa chỉ**: xử lý IPv4/IPv6, cách biểu diễn protocol, cổng, byte và packet; không gộp TCP/53 và UDP/53 chỉ vì cùng số cổng.
4. **Xử lý trùng có căn cứ**: một gói có thể được nhiều exporter quan sát. Dựa trên observation point, interface, thời gian, bộ đếm và record ID. **Không xóa một flow chỉ vì trùng 5-tuple**: nhiều kết nối khác nhau có thể dùng lại cùng tổ hợp địa chỉ/cổng.
5. **Giữ dấu hiệu không chắc chắn**: sampling, record thiếu trường, phiên chưa hoàn chỉnh, các đếm không xác định và hướng quan sát phải được gắn cờ.
6. **Làm giàu theo thời gian**: ánh xạ IP với thiết bị, VLAN/zone, chủ hệ thống, DHCP lease, NAT và lịch sử DNS tại **thời điểm xảy ra sự kiện**, tránh dùng thông tin hiện tại để suy ngược sai.

**NAT và điểm thu:** một IP công cộng có thể biểu diễn hàng trăm thiết bị, một load balancer có thể ẩn nhiều backend và một máy có thể có nhiều địa chỉ. Muốn gán flow cho người dùng hoặc máy cụ thể phải đối chiếu NAT translation, timestamp, port, VPN/IdP log và inventory. Kết luận gắn danh tính cần có mức tin cậy tương ứng.

**Sampling:** nếu dữ liệu đến từ sFlow, không xem số record hay tổng byte quan sát như giá trị đầy đủ. Có thể ước lượng theo thông số lấy mẫu khi phương pháp cho phép, nhưng phải chú thích sai số. Dùng nguồn lấy mẫu để xác định khu vực cần đào sâu, rồi kiểm tra nguồn khác trước khi kết luận.

## 4. Thiết kế đồ thị

Ta ký hiệu đồ thị có hướng trong cửa sổ thời gian W:

\[
G_W=(V_W,E_W),\qquad W=[t_0,t_1)
\]

Ở đây, **V** là tập node (IP, asset, service hoặc zone theo quyết định phân tích), còn **E** là tập cạnh phát sinh từ flow được quan sát trong W. Nếu hai node giao tiếp qua nhiều dịch vụ, nên giữ nhiều cạnh hoặc một cạnh kèm cấu trúc tách biệt theo giao thức/cổng.

Ví dụ, khóa tổng hợp một cạnh:

\[
e=(src,\ dst,\ protocol,\ dstPort,\ W)
\]

Các thuộc tính thường gặp:

\[
\begin{aligned}
records_e &= \operatorname{count}(flow\ records)\\
bytes_e &= \sum_{f \in e} bytes(f)\\
packets_e &= \sum_{f \in e} packets(f)\\
first_e &= \min_f(start(f)),\quad last_e=\max_f(end(f))
\end{aligned}
\]

**records_e là số bản ghi flow, không nhất thiết là số phiên TCP.** Exporter có thể chia một phiên thành nhiều record do active timeout. Tổng byte chỉ có ý nghĩa khi các nguồn đã dùng cùng cách đếm và đã tránh đếm trùng.

| Lựa chọn | Hữu ích cho | Điều cần tránh |
| --- | --- | --- |
| Có hướng A → B | Quan hệ nguồn–đích và vai trò trong kết nối | Dùng graph vô hướng rồi suy ra bên khởi tạo |
| Cạnh theo protocol/port | Phân biệt SMB, SSH, HTTPS, DNS | Gộp mọi dịch vụ vào một cạnh rồi mất ngữ cảnh |
| Trọng số byte hoặc packet | Đo mức độ lưu lượng | Đánh đồng traffic lớn với tấn công; cộng byte khác ngữ nghĩa |
| Trọng số record | Nhìn cường độ bản ghi quan sát | Coi số record bằng số kết nối thành công |
| Cửa sổ 5–15 phút | Dựng diễn biến một sự cố ngắn | Kết luận dựa trên cửa sổ quá thưa |
| Cửa sổ ngày/tuần | Xây baseline, cấu trúc liên lạc dài hạn | Che khuất trình tự thời gian |
| Đỉnh theo zone/VPC/VLAN | Kiểm tra chính sách phân đoạn | Đồng nhất IP với zone dù đã thay đổi tại thời điểm sự cố |

Flow kéo dài qua nhiều cửa sổ có thể được **gán cho cửa sổ bắt đầu**, hoặc giữ interval và truy vấn các cửa sổ giao nhau. Cần nêu quy tắc nhất quán; không chia đều byte theo thời gian nếu không biết phân bố lưu lượng thực tế.

## 5. Ví dụ: từ flow đến communication graph

Giả sử thu được các record một chiều đã chuẩn hóa, không trùng, từ cùng một điểm quan sát, dùng cùng ngữ nghĩa byte. Các IP 10.10.x.x là địa chỉ riêng và 198.51.100.42 là địa chỉ dành cho tài liệu. Khoảng điều tra là **09:00–09:15 ngày 28/11/2026, UTC+07**.

| Giờ | IP nguồn | IP đích | Dịch vụ | Byte quan sát |
| --- | --- | --- | --- | ---: |
| 09:00 | 10.10.10.21 | 10.10.20.11 | TCP/443 | 12.288 |
| 09:02 | 10.10.10.21 | 10.10.20.21 | TCP/443 | 102.400 |
| 09:04 | 10.10.10.21 | 10.10.30.11 | TCP/445 | 3.072 |
| 09:05 | 10.10.10.21 | 10.10.30.12 | TCP/445 | 4.096 |
| 09:07 | 10.10.10.21 | 10.10.30.13 | TCP/445 | 5.120 |
| 09:08 | 10.10.10.21 | 198.51.100.42 | TCP/443 | 83.886.080 |
| 09:09 | 10.10.20.21 | 10.10.30.21 | TCP/5432 | 2.097.152 |

Graph tương ứng:

~~~mermaid
flowchart LR
    W["10.10.10.21 | Máy trạm"]
    IDP["10.10.20.11 | Dịch vụ xác thực"]
    APP["10.10.20.21 | Ứng dụng"]
    DB["10.10.30.21 | Database"]
    H1["10.10.30.11"]
    H2["10.10.30.12"]
    H3["10.10.30.13"]
    EXT["198.51.100.42 | Bên ngoài"]
    W -->|"443"| IDP
    W -->|"443"| APP
    W -->|"445"| H1
    W -->|"445"| H2
    W -->|"445"| H3
    W -->|"443, 80 MiB"| EXT
    APP -->|"5432"| DB
~~~

Trong cửa sổ này, máy 10.10.10.21 có **6 đích khác nhau** (*out-degree = 6*), trong đó **3 đích TCP/445**. Nó cũng tạo flow tới một địa chỉ bên ngoài với khoảng 80 MiB byte được quan sát. Đó là tín hiệu đáng chú ý nếu máy này bình thường chỉ truy cập vài ứng dụng; **chưa đủ để kết luận quét mạng, di chuyển ngang hay rò rỉ dữ liệu**.

### 5.1. Ví dụ Python chuẩn thư viện

Đoạn Python 3 dưới đây nhận CSV minh họa và tạo cạnh có hướng với trọng số tổng byte và số record. Mỗi record được gán vào cửa sổ 15 phút theo thời điểm bắt đầu. Kết quả được in dạng bảng và Graphviz DOT để có thể vẽ bằng công cụ tương ứng.

~~~python
import csv
from collections import defaultdict
from datetime import datetime, timezone
from io import StringIO

sample_csv = """start_time,src_ip,dst_ip,protocol,dst_port,bytes
2026-11-28T09:00:00+07:00,10.10.10.21,10.10.20.11,TCP,443,12288
2026-11-28T09:02:00+07:00,10.10.10.21,10.10.20.21,TCP,443,102400
2026-11-28T09:04:00+07:00,10.10.10.21,10.10.30.11,TCP,445,3072
2026-11-28T09:05:00+07:00,10.10.10.21,10.10.30.12,TCP,445,4096
2026-11-28T09:07:00+07:00,10.10.10.21,10.10.30.13,TCP,445,5120
2026-11-28T09:08:00+07:00,10.10.10.21,198.51.100.42,TCP,443,83886080
2026-11-28T09:09:00+07:00,10.10.20.21,10.10.30.21,TCP,5432,2097152
"""

def time_bucket(iso_value):
    dt = datetime.fromisoformat(iso_value)
    if dt.tzinfo is None:
        raise ValueError("Timestamp phải có thông tin múi giờ")
    dt = dt.astimezone(timezone.utc)
    return dt.replace(
        minute=(dt.minute // 15) * 15,
        second=0, microsecond=0
    ).isoformat()

edges = defaultdict(lambda: {"records": 0, "bytes": 0})
for row in csv.DictReader(StringIO(sample_csv)):
    byte_count = int(row["bytes"])
    port = int(row["dst_port"])
    if byte_count < 0 or not 0 <= port <= 65535:
        raise ValueError("Flow có dữ liệu không hợp lệ")
    edge = (
        time_bucket(row["start_time"]),
        row["src_ip"], row["dst_ip"],
        row["protocol"].upper(), port,
    )
    edges[edge]["records"] += 1
    edges[edge]["bytes"] += byte_count

for (window, src, dst, proto, port), metrics in sorted(edges.items()):
    print(f"{window} {src} -> {dst} {proto}/{port} "
          f"records={metrics['records']} bytes={metrics['bytes']}")

print("digraph communications {")
print('  graph [rankdir="LR"];')
for (window, src, dst, proto, port), metrics in sorted(edges.items()):
    label = (f"{proto}/{port}\\n"
             f"{metrics['records']} records, {metrics['bytes']} B")
    print(f'  "{src}" -> "{dst}" [label="{label}"];')
print("}")
~~~

Mẫu trên minh họa cách tổng hợp, **không phải một parser NetFlow/Zeek đầy đủ**. Với dữ liệu thật phải thêm xác thực địa chỉ IPv4/IPv6, nhận diện exporter, NAT, sampling, luồng vượt cửa sổ, trường hợp record không có port và cơ chế truy vết từng cạnh về record gốc. Graphviz DOT là định dạng mô tả graph; có thể xuất sang ảnh hoặc dùng thư viện/graph database để truy vấn.

## 6. Phân tích graph phục vụ network forensics

### 6.1. Chỉ số quan trọng

- **Out-degree(u)**: số đích khác nhau mà node u có cạnh đi tới, hữu ích để xem một máy giao tiếp rộng đến đâu.
- **In-degree(u)**: số nguồn khác nhau có cạnh tới u, hữu ích để tìm máy chủ hoặc dịch vụ có nhiều client.
- **Fan-out theo port/protocol**: số đích mà một nguồn truy cập qua dịch vụ cụ thể, ví dụ TCP/445, TCP/22 hoặc UDP/53.
- **Edge weight**: tổng byte/gói hoặc số record theo định nghĩa đã thống nhất.
- **New peers**: đích mới so với baseline cho cùng máy/vai trò và khung giờ tương đương.
- **Cross-zone edges**: lưu lượng giữa các phân đoạn; phải đối chiếu với danh sách luồng được phép.
- **Community/connected component**: nhóm node liên kết với nhau; hữu ích để thấy cụm dịch vụ hoặc thay đổi cấu trúc.
- **Betweenness**: vị trí trung gian trong *đồ thị liên lạc*, **không tự chứng minh node đó đã chuyển tiếp gói tin** nếu cạnh chỉ biểu diễn phiên giữa các host.

Các chỉ số phụ thuộc cách dựng graph. Một DNS resolver hoặc proxy có degree cao là đặc điểm bình thường theo chức năng; trong khi máy người dùng bất ngờ kết nối nhiều máy quản trị có thể cần xem lại. Baseline nên so theo **loại thiết bị, giờ làm việc, ngày trong tuần, tác vụ batch, lịch backup và đợt triển khai**.

### 6.2. Các mẫu hình và giả thuyết

| Mẫu trên graph | Giả thuyết cần kiểm tra | Nguồn xác minh |
| --- | --- | --- |
| Một máy nối nhiều đích mới qua TCP/445/22 | Hoạt động quản trị, khảo sát máy khác hoặc di chuyển ngang | EDR, SMB/SSH logs, firewall, danh sách tác vụ được phê duyệt |
| Nhiều máy cùng kết nối một IP ngoài mới | C2, dịch vụ cập nhật hay API mới | DNS lịch sử, proxy, TLS metadata, danh mục nhà cung cấp |
| Cạnh tới cùng đích xuất hiện rất đều | Health check, đồng bộ hoặc beacon | Chuỗi thời gian, lịch tác vụ, log endpoint và ứng dụng |
| Byte egress tăng đột ngột | Backup, cập nhật hay khả năng rò rỉ dữ liệu | DLP/proxy, audit log, lịch backup, chủ dịch vụ |
| Cạnh giữa hai zone vốn bị chặn | Cấu hình policy sai, điểm thu nằm trước firewall hoặc vi phạm phân đoạn | Firewall action, route/ACL, NAT, sơ đồ điểm đo |
| In-degree một máy tăng mạnh | Dịch vụ mới, tăng tải hoặc dò quét | Log máy chủ, thao tác rollout, trạng thái TCP, metrics |

Không quy kết ý định dựa trên một cổng hoặc lượng byte. Một flow chỉ có SYN và không có phản hồi có thể là thử kết nối thất bại, nhưng cũng có thể do đường đi bất đối xứng khiến điểm đo không thấy gói trả lời. Phải kiểm tra topology, nơi quan sát và nguồn bổ sung.

### 6.3. Giữ trật tự thời gian

Nếu gộp cả ngày thành một graph, hai kết nối cách nhau 12 giờ sẽ trông như đồng thời. Để dựng lại sự cố, cần:

1. Chọn thời điểm bắt đầu, kết thúc và sai số đồng hồ cho sự kiện.
2. Dựng các graph liên tiếp theo cửa sổ 5 hoặc 15 phút.
3. So cạnh **mới xuất hiện**, biến mất, tăng trọng số, vượt zone.
4. Truy vết một đường liên lạc theo thứ tự timestamp; tránh suy luận nguyên nhân nếu trình tự không phù hợp.
5. Đối chiếu thời điểm login, thay đổi quyền, IDS alert, DNS request, chính sách firewall và sự kiện EDR.

Hãy giữ khả năng mở từ cạnh tổng hợp về **từng record gốc**, vì graph là công cụ chỉ đường để điều tra, không thay thế chứng cứ chi tiết.

## 7. Ca điều tra minh họa

**Tình huống:** SOC nhận cảnh báo endpoint 10.10.10.21 có hoạt động lệch baseline. Nhóm cần đánh giá các liên lạc tại 09:00–09:15 và xác định hệ thống nào phải được rà soát tiếp.

**Bước 1 — Khóa phạm vi:** Xác định mốc thời gian, timezone, điểm thu và loại flow; kiểm kê log còn thiếu hoặc có sampling. Bảo toàn dữ liệu gốc, ghi hash và metadata nguồn.

**Bước 2 — Gắn danh tính:** Tra DHCP/asset inventory và lịch sử VPN/NAT để biết 10.10.10.21 tương ứng thiết bị nào tại thời điểm sự cố. Không coi địa chỉ IP là định danh người dùng.

**Bước 3 — Dựng graph:** Từ ví dụ, máy có 6 peer, trong đó có 3 host qua TCP/445, sau đó liên lạc tới một IP ngoài với lượng byte quan sát tương đối lớn.

**Bước 4 — Đặt giả thuyết:** (A) máy thực hiện tác vụ quản trị/backup hợp lệ; (B) máy bị lợi dụng để kết nối ngang và truyền dữ liệu ra ngoài. Chưa đủ chứng cứ để chọn một trong hai.

**Bước 5 — Kiểm chứng:** Kiểm tra EDR để biết process mở kết nối; đối chiếu SMB/server logs và chứng cứ đăng nhập, DNS/proxy logs của IP bên ngoài, lịch job backup và rule firewall. Kiểm tra TLS/ứng dụng nếu dữ liệu hợp lệ có sẵn. Không gắn nhãn “đánh cắp dữ liệu” chỉ vì TCP/443 có 80 MiB.

**Bước 6 — Hành động và ghi nhận:** Nếu là tác vụ hợp lệ, bổ sung baseline và ghi rõ chứng cứ. Nếu có dấu hiệu xâm nhập đủ mạnh, chuyển sang quy trình ứng phó sự cố, cô lập theo phạm vi được phê duyệt và bảo toàn dấu vết. Nêu rõ phát hiện nào đã xác nhận và điểm nào vẫn chưa giải thích.

Mẫu kết quả báo cáo:

~~~text
Case ID: NF-2026-EXAMPLE
Khoảng thời gian: 2026-11-28 09:00–09:15 +07:00
Nguồn: flow exporter A, collector B, EDR, firewall (mã record gốc)
Node trọng tâm: 10.10.10.21 (asset mapping theo timestamp)
Quan sát: ba đích TCP/445; 80 MiB tới 198.51.100.42
Baseline: chờ xác minh theo nhóm thiết bị
Giả thuyết: job hợp lệ hoặc hành vi cần điều tra
Xác minh tiếp: EDR, SMB, DNS/proxy, IdP/VPN, lịch công việc
Giới hạn: flow không chứng minh nội dung dữ liệu hoặc ý định
Trạng thái: đang xác minh
~~~

## 8. Chất lượng dữ liệu và giới hạn kết luận

| Vấn đề | Sai lệch có thể xảy ra | Cách giảm thiểu |
| --- | --- | --- |
| Cache timeout / record chia nhỏ | Đếm record thành nhiều kết nối giả | Phân biệt records và sessions; kiểm tra thời gian/5-tuple/TCP |
| Nhiều điểm thu cùng flow | Byte/cạnh bị tính hai lần | Theo dõi observation point và phương pháp loại trùng |
| Lấy mẫu, mất log | Thiếu cạnh và sai trọng số | Đánh dấu chất lượng, đối chiếu nguồn chi tiết hơn |
| NAT, proxy, VPN, load balancer | Không xác định được host hoặc client gốc | Tra NAT translations, IdP, inventory, log phiên theo thời gian |
| IP động hoặc dùng lại | Đồ thị gán sai tài sản | Tra lịch DHCP lease và thay đổi IP |
| Đồng hồ lệch, timezone sai | Đảo thứ tự sự kiện | Quy đổi UTC và ghi bất định timestamp |
| Đường đi bất đối xứng | Thiếu chiều trả lời | Kiểm tra topology, exporter và các điểm quan sát bổ sung |
| Gán ứng dụng từ port | Nhầm HTTPS/DNS với phần mềm cụ thể | Xác minh bằng DNS, proxy, ứng dụng hoặc TLS metadata |
| Chỉ có allowed flows | Không thấy kết nối bị chặn | Dùng thêm firewall deny logs và security events |
| Gộp sớm theo subnet/ngày | Mất định danh và chuỗi sự kiện | Giữ dữ liệu record, tạo graph nhiều mức chi tiết |

**Bảo toàn chứng cứ:** Flow, graph và báo cáo có thể chứa địa chỉ nội bộ, cấu trúc kết nối và thông tin cá nhân. Giữ bản gốc có hash, lịch sử xử lý, quyền truy cập hạn chế, thời hạn lưu phù hợp và khả năng truy ngược từ cạnh về record. Khi có sai số hoặc lỗ hổng dữ liệu, ghi rõ chúng thay vì trình bày graph như bức tranh hoàn chỉnh của mọi trao đổi trên mạng.

## 9. Playbook áp dụng lại

~~~text
INPUT:
  Khoảng điều tra, IP/asset/zone trọng tâm, nguồn flow và baseline
  Thông tin exporter, sampling, NAT, DHCP, chính sách phân đoạn

1. Thu và bảo toàn dữ liệu gốc; ghi provenance.
2. Chuẩn hóa field, thời gian, chiều và bộ đếm.
3. Kiểm tra trùng, thiếu, lấy mẫu và mức độ tin cậy.
4. Chọn node/edge, window và cách tính trọng số.
5. Dựng graph; giữ đường truy vết về từng flow.
6. Tính degree, fan-out theo port, new peers và cross-zone.
7. So baseline phù hợp với vai trò và lịch công việc.
8. Điều tra cạnh đáng chú ý qua firewall, DNS, EDR, PCAP,
   log xác thực và tài liệu chủ dịch vụ.
9. Phân biệt sự kiện đã thấy, giả thuyết và kết luận đã xác minh.
10. Lưu graph, bằng chứng, giới hạn và quyết định xử lý.

OUTPUT:
  Communication graph có định nghĩa rõ; danh sách cạnh ưu tiên
  và báo cáo phát hiện có thể kiểm chứng, truy vết.
~~~

## 10. Câu hỏi tự kiểm tra

1. Vì sao out-degree của một DNS resolver có thể cao mà không phải dấu hiệu dò quét?
2. Một exporter ghi hai record cùng 5-tuple cách nhau vài phút. Vì sao không thể khẳng định đó là hai phiên TCP độc lập?
3. Nếu IP bên ngoài là NAT gateway, cần nguồn dữ liệu nào để xác định máy gốc?
4. Làm sao xác minh một cạnh từ VLAN người dùng tới VLAN database có thật sự vượt chính sách?
5. Graph thể hiện 80 MiB ra Internet. Từ flow, ta **chưa thể** kết luận những điều gì?
6. Vì sao cần tách graph thành nhiều cửa sổ khi điều tra khả năng di chuyển ngang?

**Gợi ý:** (1) Vai trò DNS cần liên lạc với nhiều đích, hãy so baseline. (2) Exporter có thể chia phiên vì timeout. (3) NAT translation, session/VPN/IdP logs theo timestamp và asset inventory. (4) Kiểm tra điểm thu, route, ACL, firewall action và rule được phê duyệt. (5) Không biết nội dung, loại dữ liệu, ý định hoặc danh tính người điều khiển. (6) Phải giữ thứ tự sự kiện để nhận diện kết nối mới và kiểm chứng chuỗi hành vi.

**Ghi nhớ:** Một communication graph chỉ đáng tin khi node, edge, thời gian, trọng số, chất lượng nguồn và đường truy vết chứng cứ đều được định nghĩa rõ. Phân tích graph giúp **ưu tiên câu hỏi điều tra**; kết luận xâm nhập phải dựa trên chứng cứ đối chiếu từ nhiều nguồn và bối cảnh vận hành.
