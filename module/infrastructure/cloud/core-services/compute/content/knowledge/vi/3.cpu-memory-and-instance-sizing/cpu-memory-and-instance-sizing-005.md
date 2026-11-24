# NUMA, CPU pinning và tính cục bộ của bộ nhớ

## Mục tiêu bài học

Trong máy chủ nhiều bộ xử lý, hiệu năng của ứng dụng phụ thuộc vào vị trí CPU thực thi và vị trí dữ liệu được lưu trong bộ nhớ. Nếu một luồng chạy trên một NUMA node nhưng liên tục truy cập RAM thuộc node khác, nó có thể phải đi qua liên kết liên bộ xử lý. Độ trễ tăng và băng thông bộ nhớ khả dụng có thể giảm.

Sau bài học này, bạn có thể:

- Giải thích NUMA, NUMA node, bộ nhớ cục bộ và bộ nhớ từ xa.
- Phân biệt CPU affinity, CPU pinning và chính sách cấp phát bộ nhớ.
- Kiểm tra topology CPU và bộ nhớ trên Linux.
- Căn chỉnh CPU và bộ nhớ cho một tiến trình hoặc workload trong giới hạn mà máy ảo, container và nền tảng đám mây cho phép.
- Đánh giá khi nào nên cố định vị trí thực thi và khi nào nên để hệ điều hành tự điều phối.

## 1. NUMA là gì?

NUMA (Non-Uniform Memory Access) là kiến trúc truy cập bộ nhớ trong đó thời gian truy cập phụ thuộc vào vị trí của CPU so với vùng RAM. Một hệ thống NUMA được chia thành các **NUMA node**. Mỗi node có một nhóm CPU và thường có vùng bộ nhớ được kết nối trực tiếp với nhóm CPU đó.

Khi CPU truy cập RAM thuộc cùng node, đó là truy cập bộ nhớ cục bộ (local memory access). Khi CPU truy cập RAM thuộc node khác, đó là truy cập bộ nhớ từ xa (remote memory access). Yêu cầu từ xa phải đi qua liên kết kết nối các node, chẳng hạn liên kết giữa các socket hoặc fabric nội bộ của bộ xử lý.

Kiến trúc này khác với UMA (Uniform Memory Access), nơi các bộ xử lý có đặc tính truy cập bộ nhớ tương đối đồng nhất. NUMA cho phép hệ thống mở rộng số CPU và dung lượng bộ nhớ, nhưng phần mềm cần chú ý đến vị trí dữ liệu để tránh lưu lượng truy cập từ xa không cần thiết.

Một socket không nhất thiết tương ứng với đúng một NUMA node. Một socket hiện đại có thể được chia thành nhiều node theo cấu hình firmware hoặc thiết kế bộ xử lý. Trong môi trường ảo hóa, hypervisor còn có thể trình bày topology ảo (vNUMA) cho máy khách. Vì vậy, hãy kiểm tra topology mà hệ điều hành khách thực sự nhìn thấy thay vì suy luận từ số socket được quảng cáo.

### Ví dụ topology hai node

Giả sử một máy chủ có hai NUMA node:

- Node 0 có các CPU logic 0–15 và vùng RAM cục bộ 64 GiB.
- Node 1 có các CPU logic 16–31 và vùng RAM cục bộ 64 GiB.

Nếu một luồng chạy trên CPU thuộc node 0 và dữ liệu của nó nằm ở RAM node 0, phần lớn truy cập bộ nhớ có thể đi theo đường cục bộ. Nếu dữ liệu nằm ở node 1, luồng phải truy cập RAM từ xa. Đây là ví dụ minh họa; số CPU, dung lượng RAM và topology thực tế phụ thuộc vào máy chủ hoặc cấu hình máy ảo.

~~~mermaid
flowchart LR
    subgraph N0["NUMA node 0"]
        C0["CPU 0–15"]
        M0["RAM cục bộ 64 GiB"]
        C0 <--> M0
    end
    subgraph N1["NUMA node 1"]
        C1["CPU 16–31"]
        M1["RAM cục bộ 64 GiB"]
        C1 <--> M1
    end
    C0 <-->|"Truy cập từ xa qua interconnect"| M1
    C1 <-->|"Truy cập từ xa qua interconnect"| M0
    N0 <-->|"Liên kết giữa các node"| N1
~~~

Sơ đồ chỉ mô tả quan hệ khái niệm. Trên phần cứng thật, đường truyền và độ trễ còn phụ thuộc bộ điều khiển bộ nhớ, cache, fabric, số node và cấu hình firmware.

## 2. Vì sao tính cục bộ của bộ nhớ quan trọng?

CPU có thể thực thi lệnh rất nhanh, nhưng ứng dụng vẫn phải chờ nếu dữ liệu chưa sẵn sàng. Truy cập RAM từ xa thường có độ trễ cao hơn và tiêu thụ băng thông trên liên kết giữa các node. Nếu nhiều luồng cùng truy cập bộ nhớ từ xa, chúng có thể tranh chấp tài nguyên liên kết.

Tác động thường thấy gồm:

- **Độ trễ tăng:** các thao tác phụ thuộc dữ liệu có thể phải chờ lâu hơn.
- **Băng thông bộ nhớ giảm:** một node có thể không tận dụng hết băng thông RAM cục bộ trong khi liên kết liên node trở thành điểm nghẽn.
- **Hiệu năng thiếu ổn định:** vị trí luồng hoặc trang bộ nhớ thay đổi theo thời gian có thể làm thời gian phản hồi biến động.
- **Tranh chấp tài nguyên:** nhiều workload cùng dùng một node có thể gây nghẽn CPU, bộ điều khiển RAM hoặc liên kết liên node.

NUMA không đồng nghĩa với hiệu năng kém. Nếu luồng và dữ liệu được phân bố hợp lý, hệ thống có thể tận dụng nhiều bộ điều khiển bộ nhớ và mở rộng băng thông tổng thể. Vấn đề xuất hiện khi vị trí CPU và vị trí dữ liệu không phù hợp với mẫu truy cập của ứng dụng.

Các workload nhạy với vị trí bộ nhớ thường gồm cơ sở dữ liệu trong bộ nhớ, hệ thống phân tích dữ liệu lớn, ứng dụng HPC, cache dung lượng lớn, xử lý gói mạng và dịch vụ có yêu cầu độ trễ thấp. Ứng dụng nhỏ hoặc workload có thời gian chạy ngắn thường không hưởng lợi nhiều từ việc cấu hình NUMA thủ công.

## 3. CPU affinity và CPU pinning

**CPU affinity** là tập CPU logic mà một tiến trình hoặc luồng được phép chạy. **CPU pinning** là cách cấu hình affinity để giữ tiến trình hoặc luồng trong một tập CPU đã chọn. Có thể cấu hình affinity cho cả tiến trình hoặc riêng từng luồng.

Pinning có thể giúp:

- Giảm việc luồng di chuyển liên tục giữa các CPU, nhờ đó tận dụng cache tốt hơn.
- Giữ các luồng liên quan trong cùng NUMA node.
- Làm cho kết quả đo hiệu năng dễ lặp lại hơn trong một số workload.
- Phân chia CPU cho các workload có yêu cầu độ trễ hoặc tính dự đoán cao.

Tuy nhiên, pinning không tự động làm ứng dụng nhanh hơn. Nếu chọn quá ít CPU, các luồng có thể phải chờ dù những CPU khác đang rảnh. Nếu nhiều tiến trình bị ghim vào cùng một CPU, chúng sẽ tranh chấp thời gian xử lý. Pinning sai node còn có thể làm tăng truy cập bộ nhớ từ xa.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Điều không được đảm bảo |
|---|---|---|
| CPU affinity | Giới hạn tập CPU mà tiến trình hoặc luồng được phép chạy | Không đảm bảo CPU đó dành riêng cho tiến trình |
| CPU pinning | Chủ động đặt affinity vào một tập CPU cụ thể | Không tự động đặt dữ liệu vào RAM cục bộ |
| CPU độc quyền | Nền tảng cấp CPU cho workload theo chính sách độc quyền | Không phải môi trường nào cũng hỗ trợ; vẫn cần xem xét vị trí bộ nhớ |

Trong máy ảo, CPU logic mà hệ điều hành khách nhìn thấy thường là vCPU. Affinity bên trong máy khách chỉ điều khiển lịch chạy trong phạm vi máy khách; nó không cho phép ứng dụng tự chọn CPU vật lý của máy chủ. Hypervisor vẫn quyết định cách ánh xạ và lập lịch vCPU trên host.

## 4. Chính sách đặt bộ nhớ

CPU affinity quyết định luồng có thể chạy ở đâu. Chính sách NUMA memory policy quyết định hệ điều hành nên cấp phát trang RAM từ node nào. Hai cấu hình này cần được xem xét cùng nhau.

Các chính sách phổ biến trên Linux gồm:

| Chính sách | Cách hoạt động | Trường hợp cân nhắc |
|---|---|---|
| Default / local allocation | Hệ điều hành ưu tiên cấp phát theo vị trí thực thi và các quy tắc mặc định | Phần lớn ứng dụng thông thường |
| Preferred | Ưu tiên một node; hệ thống có thể dùng node khác khi cần theo chính sách | Muốn ưu tiên locality nhưng vẫn cần khả năng dự phòng |
| Bind | Giới hạn cấp phát vào một hoặc một nhóm node được chỉ định | Workload đã đo đạc và có đủ dung lượng trên node mục tiêu |
| Interleave | Phân bố trang bộ nhớ luân phiên trên nhiều node | Một số workload quét dữ liệu lớn, truy cập tương đối đồng đều |

Một chi tiết quan trọng là **first-touch allocation**. Trên nhiều cấu hình Linux, trang bộ nhớ thường được cấp phát tại node của CPU thực hiện lần chạm đầu tiên vào trang đó, theo memory policy đang áp dụng. Vì vậy, nếu luồng khởi tạo dữ liệu chạy trên node 0 nhưng các luồng xử lý sau đó chạy trên node 1, dữ liệu có thể nằm ở node 0 và tạo ra nhiều truy cập từ xa.

Linux còn có cơ chế tự cân bằng NUMA (automatic NUMA balancing) trên các hệ thống hỗ trợ. Cơ chế này có thể theo dõi mẫu truy cập và di chuyển task hoặc trang bộ nhớ để cải thiện locality. Khi cấu hình thủ công, cần quan sát hành vi thực tế và hiểu các chính sách đang có hiệu lực; không nên tắt cơ chế tự động chỉ dựa trên giả định.

## 5. Kiểm tra NUMA trên Linux

Trước khi pin CPU hoặc bind bộ nhớ, hãy xác định topology mà môi trường đang hiển thị. Các lệnh sau cần có quyền truy cập phù hợp và một số lệnh yêu cầu cài gói numactl.

~~~bash
# Tổng quan CPU, socket, core và topology
lscpu

# Ánh xạ CPU logic với socket, core và NUMA node
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE

# Số node, CPU và dung lượng bộ nhớ từng node
numactl --hardware

# Thống kê cấp phát NUMA toàn hệ thống
numastat

# Thống kê NUMA của một tiến trình
numastat -p <PID>

# Xem CPU affinity của tiến trình
taskset -pc <PID>

# Với cgroup v2: xem CPU và memory node được phép sử dụng
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpuset.mems.effective
~~~

Cách đọc kết quả:

- Đối chiếu cột NODE trong lscpu với danh sách node từ numactl --hardware để biết CPU nào thuộc node nào.
- Xem dung lượng RAM từng node. Một node có ít RAM khả dụng có thể trở thành giới hạn nếu workload bị bind vào node đó.
- numactl --hardware thường hiển thị khoảng cách tương đối giữa các node. Đây là chỉ số tương đối do nền tảng cung cấp, không phải thời gian truy cập tính bằng nano giây.
- numastat -p giúp quan sát phân bố cấp phát của tiến trình. Các bộ đếm như numa_miss, numa_foreign, local_node và other_node cần được đọc trong bối cảnh workload và phiên bản công cụ.
- Trong container, topology và danh sách CPU/node có thể đã bị giới hạn bởi runtime hoặc cgroup. Kết quả bên trong container có thể khác với topology đầy đủ trên host.

Không nên kết luận chỉ từ một lần lấy mẫu. Hãy so sánh thống kê trong lúc ứng dụng chạy với tải đại diện, đồng thời theo dõi độ trễ và thông lượng.

## 6. Thực hành căn chỉnh CPU và bộ nhớ

Giả sử kiểm tra cho thấy CPU 0–15 thuộc node 0 và CPU 16–31 thuộc node 1. Một dịch vụ có tập luồng làm việc vừa phải, dữ liệu chủ yếu được truy cập bởi các luồng trên node 0. Sau khi đo baseline, có thể thử chạy dịch vụ với CPU và RAM cùng node:

~~~bash
numactl --cpunodebind=0 --membind=0 ./service
~~~

Lệnh trên yêu cầu tiến trình chạy trên CPU thuộc node 0 và cấp phát bộ nhớ từ node 0 theo chính sách bind. Hãy chắc chắn node 0 có đủ CPU và RAM cho tiến trình. Chính sách bind nghiêm ngặt có thể khiến cấp phát thất bại khi node được chỉ định không còn đủ bộ nhớ.

Nếu chỉ muốn giới hạn tập CPU, có thể dùng taskset:

~~~bash
taskset -c 0-7 ./service
~~~

taskset chỉ thiết lập CPU affinity; lệnh này không tự đặt chính sách bộ nhớ. Để kiểm soát cả hai, dùng công cụ và chính sách NUMA phù hợp.

Với workload đọc tuần tự tập dữ liệu lớn và có thể hưởng lợi từ băng thông tổng hợp, có thể thử interleave trên các node:

~~~bash
numactl --interleave=all ./batch-job
~~~

Interleave không phải lựa chọn mặc định cho mọi ứng dụng. Với workload có dữ liệu và luồng tập trung theo từng node, phân bố trang trên tất cả node có thể làm tăng truy cập từ xa. Cần benchmark trên đúng dữ liệu và mô hình tải.

Quy trình thử nghiệm nên diễn ra như sau:

1. Đo baseline khi chưa thay đổi affinity hoặc memory policy.
2. Ghi lại topology, CPU được phép dùng, dung lượng RAM từng node và chính sách hiện tại.
3. Kiểm tra vị trí thực thi và phân bố bộ nhớ trong lúc ứng dụng hoạt động.
4. Thử một thay đổi tại một thời điểm, chẳng hạn giới hạn CPU vào một node trước.
5. Đo lại thông lượng, độ trễ p50/p95/p99, mức sử dụng CPU, context switch, áp lực bộ nhớ và thống kê NUMA.
6. Giữ cấu hình mới khi kết quả cải thiện ổn định dưới tải đại diện; quay lại cấu hình trước nếu hiệu năng giảm hoặc tài nguyên bị mất cân bằng.

## 7. NUMA trong container và Kubernetes

Container chia sẻ kernel với host. CPU và memory node mà container được phép sử dụng thường được giới hạn bằng cgroup và cấu hình của container runtime.

Ví dụ Docker trên một host có topology phù hợp:

~~~bash
docker run --rm \
  --cpuset-cpus="0-7" \
  --cpuset-mems="0" \
  my-service:latest
~~~

Trong ví dụ này, container được giới hạn vào CPU 0–7 và memory node 0 theo topology host. Chỉ dùng các chỉ số sau khi kiểm tra host và xác nhận runtime cho phép cấu hình đó. Cấu hình CPU quota hoặc CPU shares có ý nghĩa khác: chúng điều tiết thời gian CPU nhưng không nhất thiết ghim container vào một nhóm CPU cụ thể.

Trên Kubernetes:

- CPU Manager với chính sách static có thể cấp CPU độc quyền cho container thuộc Pod đáp ứng điều kiện QoS Guaranteed và yêu cầu CPU là số nguyên, theo cấu hình và phiên bản Kubernetes.
- Topology Manager có thể phối hợp gợi ý topology từ CPU Manager, Device Manager và các nguồn tài nguyên khác để cải thiện việc căn chỉnh tài nguyên.
- CPU request và limit thông thường không đồng nghĩa với CPU pinning.
- Khả năng căn chỉnh NUMA phụ thuộc cấu hình kubelet, runtime, plugin thiết bị, topology node và phiên bản Kubernetes.

Với workload nhạy độ trễ, cần kiểm tra cấu hình node và trạng thái cấp phát thực tế sau khi Pod được lập lịch. Không nên giả định rằng khai báo request/limit đã đảm bảo CPU và RAM nằm cùng NUMA node.

## 8. Các giới hạn trong môi trường điện toán đám mây

Trong máy ảo đám mây, hypervisor quản lý host vật lý và ánh xạ vCPU, bộ nhớ của máy khách lên tài nguyên thật. Do đó:

- Máy khách có thể chỉ nhìn thấy một NUMA node dù host có nhiều node.
- Máy khách có thể nhìn thấy vNUMA, nhưng topology đó do nền tảng trình bày và không nhất thiết phản ánh đầy đủ cách host đang đặt dữ liệu.
- CPU pinning trong máy khách chỉ giới hạn scheduler của hệ điều hành khách; không thay thế chính sách pinning ở hypervisor.
- Khả năng điều khiển topology thường khác nhau giữa máy ảo thông thường, máy ảo tối ưu hiệu năng, dedicated host và bare-metal instance.

Nếu ứng dụng cần kiểm soát NUMA chặt chẽ, hãy chọn loại instance có tài liệu công bố topology và khả năng phù hợp. Với máy ảo thông thường, bắt đầu bằng topology nhìn thấy bên trong guest và benchmark ứng dụng. Với bare-metal hoặc môi trường có quyền quản trị host, đội vận hành có thể kiểm soát sâu hơn CPU affinity, cpuset, memory policy và phân bố workload.

Không nên suy ra số NUMA node vật lý chỉ từ số vCPU, tên instance hoặc số socket hiển thị. Hãy xác minh bằng công cụ trong môi trường chạy và tài liệu của nhà cung cấp.

## 9. Khi nào nên dùng CPU pinning và NUMA binding?

| Loại workload | Hướng tiếp cận ban đầu | Lý do |
|---|---|---|
| Web service thông thường, tải thay đổi | Để scheduler và memory policy mặc định quản lý | Linh hoạt khi tải tăng giảm; chi phí tinh chỉnh có thể lớn hơn lợi ích |
| Cơ sở dữ liệu lớn, cache trong bộ nhớ | Đo locality, sau đó thử căn chỉnh nhóm luồng và bộ nhớ theo node | Truy cập RAM thường xuyên nên vị trí dữ liệu có thể ảnh hưởng rõ |
| HPC, phân tích dữ liệu, xử lý ma trận | Benchmark phân vùng theo node và interleave | Có thể tận dụng nhiều kênh bộ nhớ và băng thông tổng thể |
| Xử lý gói mạng hoặc dịch vụ độ trễ thấp | Cân nhắc pinning luồng, IRQ và bộ nhớ theo node | Giảm di chuyển luồng và cải thiện tính dự đoán khi cấu hình đúng |
| Serverless hoặc dịch vụ được quản lý | Tối ưu ở cấp ứng dụng và cấu hình dịch vụ được cung cấp | Người dùng thường không kiểm soát topology CPU/RAM bên dưới |

CPU pinning và NUMA binding phù hợp khi đã có bằng chứng về chi phí di chuyển luồng hoặc truy cập bộ nhớ từ xa. Với workload chưa có dấu hiệu nghẽn, hãy giữ cấu hình đơn giản và dùng số liệu để quyết định.

## 10. Lỗi thường gặp và cách tránh

**Ghim tất cả luồng vào một node:** node đó có thể hết CPU hoặc băng thông RAM trong khi node khác còn rảnh. Hãy phân tích số luồng, mức song song và dung lượng bộ nhớ trước khi giới hạn.

**Ghim CPU nhưng bỏ qua bộ nhớ:** luồng có thể chạy ổn định trên node 0 nhưng dữ liệu lại nằm trên node 1. Cần xem cả CPU affinity và memory policy.

**Bind vào node không đủ RAM:** cấp phát có thể thất bại hoặc workload bị thiếu tài nguyên. Theo dõi dung lượng từng node và để lại khoảng dự phòng cho hệ điều hành cùng tiến trình khác.

**Nhầm CPU quota với pinning:** quota giới hạn thời gian CPU trong một khoảng đo; affinity giới hạn CPU được phép chạy. Hai cơ chế giải quyết vấn đề khác nhau.

**Dựa vào topology của host khi đang ở trong VM/container:** guest hoặc container có thể chỉ nhìn thấy một phần tài nguyên. Kiểm tra các giới hạn thực tế của môi trường hiện tại.

**Chỉ đo một lần hoặc chỉ nhìn mức sử dụng CPU:** mức CPU thấp không chứng minh ứng dụng đang bị NUMA. Hãy so sánh độ trễ, thông lượng, thống kê NUMA và áp lực bộ nhớ trong cùng điều kiện tải.

**Áp dụng interleave cho mọi workload:** interleave có thể giúp một số tác vụ quét dữ liệu nhưng làm giảm locality của ứng dụng có truy cập tập trung. Chọn chính sách dựa trên mẫu truy cập thực tế.

## 11. Checklist trước khi đưa cấu hình vào vận hành

- [ ] Đã xác định topology CPU và NUMA node mà workload thực sự nhìn thấy.
- [ ] Đã kiểm tra giới hạn CPU và memory node của VM, container hoặc Pod.
- [ ] Đã đo baseline dưới tải đại diện.
- [ ] Đã xác định bằng chứng về truy cập bộ nhớ từ xa hoặc di chuyển luồng.
- [ ] CPU affinity và memory policy phù hợp với nhau.
- [ ] Node được chọn có đủ CPU, RAM và khoảng dự phòng.
- [ ] Đã kiểm tra hành vi khi tải tăng, giảm và khi tiến trình khởi động lại.
- [ ] Đã so sánh p95/p99, thông lượng và thống kê NUMA sau thay đổi.
- [ ] Có phương án quay lại cấu hình trước nếu kết quả không ổn định.

NUMA, CPU pinning và memory binding là các công cụ điều khiển vị trí thực thi và dữ liệu. Hiệu quả đến từ việc hiểu topology đang được cung cấp, đo đúng workload và căn chỉnh CPU với nơi dữ liệu được truy cập. Trong môi trường đám mây, mức kiểm soát phụ thuộc loại instance và lớp ảo hóa; hãy tối ưu trong phạm vi topology mà hệ điều hành thực sự nhìn thấy.
