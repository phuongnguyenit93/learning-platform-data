# Load testing, fault injection và kiểm chứng khả năng chịu lỗi

Một kiến trúc sẵn sàng cao chỉ có giá trị khi ứng dụng vẫn hoàn thành công việc trong lúc thành phần gặp sự cố. Trên Oracle Cloud Infrastructure (OCI), có nhiều Compute instance, đặt chúng ở các fault domain khác nhau và đưa chúng vào Load Balancer mới tạo ra điều kiện cho khả năng chịu lỗi. Để biết thiết kế thực sự hoạt động, cần đưa tải đại diện vào hệ thống, gây ra một lỗi có giới hạn, rồi đối chiếu hành vi quan sát được với tiêu chí đã đặt trước.

Bài học thuộc chủ đề **Kiến trúc sẵn sàng cao**, tập trung vào cách kiểm chứng ứng dụng chạy trên OCI có phân quyền, quan sát được, phục hồi được và có chi phí thử nghiệm kiểm soát được. Ví dụ xuyên suốt là một API danh mục sản phẩm chạy trên hai Compute instance sau OCI Load Balancer. Những phần về cơ sở dữ liệu Oracle và lưu trữ mở rộng cách kiểm chứng sang tính đúng đắn của dữ liệu, không giả định rằng kiểm thử tầng ứng dụng đã chứng minh được toàn bộ hệ thống.

Sau bài học, người học có thể:

- Phân biệt đo tải, tìm giới hạn và tiêm lỗi để chọn đúng thí nghiệm.
- Viết giả thuyết chịu lỗi bằng các chỉ số đo được từ phía người dùng.
- Phát tải ổn định, quan sát cơ chế loại backend lỗi và kiểm tra năng lực khi mất một instance.
- Thiết kế phạm vi ảnh hưởng, điều kiện dừng và phương án hoàn tác.
- Thu thập bằng chứng để kết luận chính xác điều gì đã được kiểm chứng.

## 1. Ba câu hỏi cần trả lời riêng

**Load testing** trả lời: với một mức tải xác định, hệ thống có đáp ứng yêu cầu về thông lượng, độ trễ và tính đúng đắn không?

**Fault injection** trả lời: khi một lỗi cụ thể xuất hiện, cơ chế phát hiện, cô lập và phục hồi có hoạt động như dự kiến không?

**Kiểm chứng khả năng chịu lỗi** kết hợp hai phần trên: trong lúc tiếp tục nhận tải đại diện, hệ thống có duy trì được kết quả nghiệp vụ và phục hồi trong giới hạn cho phép không?

| Loại thử nghiệm | Cách tạo điều kiện | Kết quả cần tìm |
| --- | --- | --- |
| Smoke test | Tải rất nhỏ trong thời gian ngắn | Script, dữ liệu, xác thực và đường mạng có hoạt động |
| Load test | Tải đại diện hoặc tải đỉnh dự kiến | Có đạt mục tiêu dịch vụ ở mức tải đó |
| Stress test | Tăng tải vượt năng lực dự kiến theo từng bước | Điểm bắt đầu vi phạm mục tiêu và cách hệ thống suy giảm |
| Spike test | Tăng tải nhanh rồi giảm | Khả năng hấp thụ đột biến, xếp hàng và mở rộng |
| Soak test | Duy trì tải đủ lâu | Rò rỉ bộ nhớ, cạn kết nối, tích tụ hàng đợi hoặc tăng chi phí |
| Thử nghiệm chịu lỗi | Giữ tải và làm hỏng một thành phần đã chọn | Ảnh hưởng tới người dùng, dữ liệu, phát hiện và phục hồi |

Không bắt đầu bằng việc vừa tăng tải mạnh, vừa chặn mạng, vừa chuyển đổi cơ sở dữ liệu. Khi nhiều biến cùng thay đổi, rất khó biết yếu tố nào gây ra lỗi. Trước hết cần có một lần chạy đối chứng không tiêm lỗi ở cùng mức tải, sau đó thay đổi một điều kiện.

Một lần chạy không thấy lỗi cũng chưa đủ để kết luận: có thể tải chưa tới hệ thống, bộ phát tải tự chậm lại, hoặc toàn bộ yêu cầu chỉ chạm cache mà không đi qua thành phần cần kiểm chứng.

## 2. Kiến trúc thử nghiệm trên OCI và giới hạn của nó

Sử dụng một compartment dành cho lab trong tenancy, chẳng hạn `ha-lab`. Ví dụ giả định:

- Một VCN với đường truy cập quản trị được kiểm soát.
- Một OCI Load Balancer có listener HTTPS và một backend set.
- Hai Compute instance A và B trong subnet riêng, cùng chạy `catalog-api.service` ở cổng 8080.
- API không lưu phiên bắt buộc trong bộ nhớ của riêng một instance.
- Dữ liệu danh mục thử nghiệm nằm trong một cơ sở dữ liệu Oracle đã chuẩn bị sẵn.
- Một máy phát tải độc lập truy cập đúng địa chỉ mà người dùng sẽ truy cập.
- Log và metric đủ để đối chiếu yêu cầu, backend và sự kiện lỗi.

~~~mermaid
flowchart LR
    G["Máy phát tải độc lập"] --> LB["OCI Load Balancer - HTTPS"]
    LB --> A["Compute A - catalog-api"]
    LB --> B["Compute B - catalog-api"]
    A --> DB["Cơ sở dữ liệu Oracle của lab"]
    B --> DB
    C["Người điều phối thí nghiệm"] -. "Dừng dịch vụ có hoàn tác" .-> A
    A -. "Log và metric" .-> O["Quan sát và dòng thời gian"]
    B -. "Log và metric" .-> O
    LB -. "Health và metric" .-> O
    G -. "Kết quả từ phía client" .-> O
~~~

OCI có các region với một hoặc nhiều availability domain (AD); mỗi AD có ba fault domain (FD). Phân bố instance qua FD giúp giảm ảnh hưởng của lỗi phần cứng hoặc bảo trì trong một AD. Cần kiểm tra placement thực tế của A và B; không suy từ tên instance. Kiến trúc nhiều FD trong cùng AD vẫn cần phương án khác nếu muốn chịu được sự cố toàn AD. Các khái niệm placement này được mô tả trong [tài liệu Regions and Availability Domains của Oracle](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

Trong lab, có thể đặt A và B ở hai FD khác nhau trong cùng AD. Nếu dùng nhiều AD, phải ghi lại phân bố thực tế và bảo đảm các phụ thuộc cũng phù hợp với mục tiêu đó.

**Dừng dịch vụ trên A chỉ mô phỏng việc mất một backend ứng dụng.** Nó không tạo ra mất điện của FD, mất mạng của AD hay sự cố region. Ngay cả khi A nằm ở AD khác B, dừng A vẫn không kiểm chứng những phụ thuộc dùng chung của cả AD.

Cơ sở dữ liệu trong sơ đồ là một phụ thuộc của ứng dụng, không phải bằng chứng rằng tầng dữ liệu đã có HA. Nếu database vẫn là điểm lỗi đơn, kết quả tốt ở tầng Compute không loại bỏ điểm lỗi đơn đó.

## 3. Từ mục tiêu dịch vụ tới giả thuyết kiểm chứng

### 3.1. Định nghĩa thành công theo nghiệp vụ

Giả sử API lab cung cấp:

~~~http
GET /api/catalog
~~~

Với bộ dữ liệu cố định của lab, phản hồi hợp lệ phải có HTTP 200, JSON chứa mảng `items`, trong đó có sản phẩm `SKU-001`.

~~~json
{
  "items": [
    {
      "id": "SKU-001",
      "name": "Sản phẩm mẫu"
    }
  ]
}
~~~

Đây là hợp đồng minh họa cần được triển khai hoặc điều chỉnh theo API thật trước khi chạy script. HTTP 200 với trang lỗi HTML, JSON sai cấu trúc hoặc thiếu dữ liệu chuẩn bị trước đều không được tính là yêu cầu thành công.

Định nghĩa:

~~~text
Tỷ lệ thành công nghiệp vụ
  = số yêu cầu nhận được kết quả đúng hợp đồng
    / tổng số yêu cầu đã thực sự gửi
~~~

Mẫu số phải bao gồm timeout và lỗi kết nối của yêu cầu đã gửi. Những lượt không được bộ phát tải khởi chạy phải được theo dõi riêng, vì chúng làm thay đổi mức tải thực tế.

### 3.2. Ví dụ tiêu chí cho lab

Các con số dưới đây là **mục tiêu của thí nghiệm minh họa**, không phải SLA hay cam kết thời gian phục hồi của OCI.

| Khía cạnh | Tiêu chí minh họa |
| --- | --- |
| Tải đầu vào | 200 lượt bắt đầu mỗi giây, mỗi lượt đúng một GET, không retry |
| Trạng thái ổn định | Thành công nghiệp vụ ít nhất 99,9% trong mỗi cửa sổ trượt 60 giây |
| Độ trễ ổn định | p95 không quá 500 ms và p99 không quá 1.000 ms trong cùng cửa sổ |
| Chuyển tiếp sau tiêm lỗi | Chỉ trong 30 giây đầu sau lỗi, tỷ lệ thất bại không quá 1% trong mỗi cửa sổ trượt 10 giây |
| Độ trễ khi chuyển tiếp | p99 không quá 2.000 ms trong các cửa sổ chuyển tiếp |
| Phát hiện backend lỗi | Quan sát được backend A bị đánh dấu unhealthy trong tối đa 20 giây |
| Phục hồi dịch vụ | Bắt đầu có một khoảng 30 giây liên tục đạt điều kiện ổn định trong tối đa 60 giây sau lỗi |
| Khôi phục dự phòng | A trở lại healthy và hai backend phục vụ ổn định trong tối đa 180 giây sau lỗi |
| Tính hợp lệ của tải | Không có `dropped_iterations`; máy phát tải không bão hòa |
| Toàn bộ lần chạy | Tỷ lệ thành công nghiệp vụ ít nhất 99,9%; các ngưỡng tổng hợp cũng phải đạt |

Đánh giá các cửa sổ với bước trượt đã thống nhất, chẳng hạn 1 giây, và lưu bước trượt đó trong báo cáo. Cửa sổ ổn định phải nằm trọn trong pha tương ứng. Cửa sổ vắt qua ranh giới pha cần được đánh dấu riêng; không trộn chúng vào nhóm ổn định để làm sai kết quả.

Sau 30 giây chuyển tiếp, hệ thống phải đáp ứng trở lại tiêu chí ổn định dù A còn dừng. Không được kéo dài pha chuyển tiếp sau khi thấy kết quả xấu. Điều kiện trên toàn bộ lần chạy là một ràng buộc bổ sung; các ngưỡng riêng theo pha không tự động bảo đảm đạt ngưỡng tổng hợp.

Độ trễ ở đây đo từ ngay trước khi client gửi yêu cầu đến khi client nhận và kiểm tra xong kết quả. Theo dõi cả yêu cầu thành công lẫn thất bại; nếu chỉ tính phản hồi thành công, nhiều timeout có thể biến mất khỏi biểu đồ độ trễ.

### 3.3. Tách phát hiện, phục hồi và khôi phục dự phòng

Đặt các mốc:

- `t0`: lúc lỗi thực sự bắt đầu có hiệu lực.
- `t_detect`: lúc cơ chế sức khỏe ghi nhận backend A lỗi.
- `t_good`: đầu khoảng 30 giây liên tục đầu tiên đạt điều kiện ổn định.
- `t_redundant`: lúc cả A và B đã trở lại phục vụ bình thường.

Khi đó:

~~~text
Thời gian phát hiện = t_detect - t0
Thời gian phục hồi dịch vụ quan sát được = t_good - t0
Thời gian khôi phục dự phòng = t_redundant - t0
~~~

Chỉ xác nhận được `t_good` sau khi đã quan sát hết khoảng 30 giây. Báo cáo cả thời điểm bắt đầu khoảng tốt và thời điểm hoàn tất việc xác nhận, tránh nhầm sự phục hồi với thời điểm người vận hành nhận biết nó.

RTO là mục tiêu phục hồi đặt trước; thời gian đo được dùng để đối chiếu với mục tiêu đó. RPO liên quan đến lượng dữ liệu có thể mất khi phục hồi. Bài thử GET này không tạo giao dịch ghi, do đó **không đo được RPO**.

Giả thuyết hoàn chỉnh có thể viết như sau:

> Khi dịch vụ trên một backend dừng trong lúc hệ thống nhận 200 yêu cầu/giây, Load Balancer sẽ loại backend đó trong giới hạn phát hiện đã đặt, backend còn lại đáp ứng mục tiêu ổn định, và backend được phục hồi có thể nhận tải trở lại mà không tạo một đợt lỗi mới.

## 4. Kiểm tra năng lực khi mất một thành phần

Hai instance đủ chạy bình thường chưa chắc đủ chạy khi mất một instance.

Giả sử mỗi instance đã được đo riêng và có năng lực bền vững `C` yêu cầu/giây tại mục tiêu độ trễ. Với `N` instance tương đương, điều kiện sơ bộ để chịu mất một instance là:

~~~text
(N - 1) × C >= tải đỉnh cần phục vụ
~~~

Nếu muốn giữ tỷ lệ dự phòng năng lực `h` trên phần còn sống:

~~~text
tải đỉnh <= (N - 1) × C × (1 - h)
~~~

Ví dụ, hai instance, mỗi instance đạt 300 yêu cầu/giây và cần để dư 20% năng lực:

~~~text
Năng lực còn lại có dự phòng
  = (2 - 1) × 300 × (1 - 0,2)
  = 240 yêu cầu/giây
~~~

Tải 200 yêu cầu/giây nằm dưới mức tính sơ bộ này. Tuy nhiên, công thức giả định backend tương đương và không có nút thắt dùng chung. Vẫn phải kiểm tra pool kết nối database, giới hạn kết nối của Load Balancer, băng thông, thời gian GC, hàng đợi và dung lượng lưu trữ.

Nếu một AD chứa nhiều backend, kiểm tra mất AD cần trừ toàn bộ năng lực trong AD đó, không chỉ trừ một instance. Tương tự, hệ thống có nhiều replica nhưng mọi replica truy cập cùng một phụ thuộc lỗi vẫn có thể ngừng phục vụ cùng lúc.

Autoscaling có thể bổ sung năng lực nhưng không thay thế phần dự phòng cần có ngay khi lỗi xảy ra. Cần đo cả thời gian phát hiện thiếu tải, tạo instance, khởi động ứng dụng và đưa backend vào phục vụ. Với thí nghiệm đầu tiên, giữ số instance cố định để quan sát rõ năng lực N-1; ghi lại và khôi phục cấu hình autoscaling nếu lab có thay đổi.

## 5. Chuẩn bị thí nghiệm có phạm vi rõ ràng

### 5.1. Danh tính, tài nguyên và đường hoàn tác

Trước khi chạy, ghi lại tenancy, region, compartment OCID, Load Balancer OCID, backend set, hai instance OCID và IP riêng. Tên hiển thị chỉ hỗ trợ nhận diện; tài nguyên đích cần được xác nhận bằng định danh cụ thể.

Tách quyền phát tải, xem quan sát và thực hiện lỗi. Tài khoản lab chỉ cần quyền trên phạm vi tài nguyên thử nghiệm; không cần cấp quyền quản trị toàn tenancy để dừng một dịch vụ qua phiên quản trị được cho phép.

Nếu tự động hóa dùng OCI API, ưu tiên cơ chế danh tính của workload phù hợp với nơi chạy. Quyền IAM trên OCI và quyền `sudo` trong hệ điều hành là hai lớp khác nhau: có quyền quản lý Compute không mặc nhiên có quyền chạy lệnh trong guest OS, và ngược lại.

Chuẩn bị thêm:

- Dữ liệu tổng hợp có thể đối soát, không sử dụng giao dịch thật.
- Bản cấu hình trước thí nghiệm và đường khôi phục đã kiểm tra.
- Người có trách nhiệm dừng thí nghiệm và một đường quản trị còn sử dụng được khi dịch vụ lỗi.
- Đồng bộ thời gian; sử dụng UTC cho sự kiện và có số đo thời gian trôi qua.
- Kiểm tra máy phát tải không nằm trên backend sẽ bị dừng.
- Xác nhận mọi backend healthy, cấu hình đúng và không có sự cố nền.
- Giới hạn thời lượng, lưu lượng, số máy phát tải và lượng log được lưu.

### 5.2. Giả thuyết, điều kiện dừng và hoàn tác

Một bản mô tả ngắn, trước khi chạy, nên có:

~~~yaml
experiment_id: oci-ha-001
scope: compartment ha-lab, backend A đã xác nhận bằng instance OCID
hypothesis: mất một backend vẫn duy trì API catalog ở tải 200 yêu cầu/giây
fault: dừng catalog-api.service trên đúng backend A
maximum_fault_duration: 120 giây theo lịch, có giám sát độc lập
stop_conditions:
  - backend B không còn healthy
  - thất bại nghiệp vụ trên 5% ở hai cửa sổ 10 giây liên tiếp
  - p99 trên 2000 ms ở hai cửa sổ 10 giây liên tiếp
  - phát hiện dữ liệu sai hoặc ảnh hưởng ra ngoài lab
rollback: khởi động lại dịch vụ A và xác minh readiness, health, kết quả client
evidence: dòng thời gian, dữ liệu client, backend health, metric và log
~~~

Ngưỡng dừng bảo vệ thí nghiệm và ngưỡng đạt bài kiểm chứng có vai trò khác nhau. Vi phạm tiêu chí đạt có thể khiến kết quả là FAIL ngay cả khi chưa chạm ngưỡng buộc dừng khẩn cấp.

Khi chạm điều kiện dừng, chấm dứt việc gây lỗi, khôi phục thành phần và giảm hoặc ngừng tải nếu cần. Dừng bộ phát tải không tự khôi phục backend. Một quy trình hoàn tác đầy đủ phải xác minh cả dịch vụ, đường mạng, trạng thái Load Balancer và kết quả từ client.

Không dùng thao tác xóa instance, xóa volume hoặc thay đổi một security list dùng chung cho thí nghiệm đầu tiên. Các thao tác đó làm tăng phạm vi ảnh hưởng và có thể cắt cả đường phục hồi.

## 6. Chọn ma trận lỗi theo mục tiêu kiến trúc

| Lỗi cần kiểm chứng | Cách mô phỏng có giới hạn | Bằng chứng quan trọng | Giới hạn của kết luận |
| --- | --- | --- | --- |
| Mất một backend ứng dụng | Dừng đúng dịch vụ trên A | Health chuyển trạng thái, lỗi client, năng lực B | Không đại diện toàn bộ lỗi host |
| Mất một Compute instance | Dừng một instance lab có kế hoạch khởi động lại | Ảnh hưởng các kết nối, phục hồi guest và backend | Không mô phỏng mất toàn AD |
| Phụ thuộc phản hồi chậm | Dùng stub hoặc proxy thử nghiệm chỉ trên đường phụ thuộc đã chọn | Timeout, retry, circuit breaker, hàng đợi | Không đổi mạng dùng chung để tạo độ trễ |
| Không tới được database từ một backend | Cô lập đường kết nối thử nghiệm của riêng backend đó | Readiness, lỗi nghiệp vụ, pool kết nối | Phải còn đường quản trị và hoàn tác riêng |
| Chuyển vai trò database | Dùng thao tác được dịch vụ database hỗ trợ trong lab riêng | Kết nối lại, vai trò mới, đối soát giao dịch | Kết quả phụ thuộc loại dịch vụ và chế độ bảo vệ |
| Suy giảm đường lưu trữ | Stub lỗi hoặc đường thử nghiệm dành riêng cho Object Storage/File Storage | Hành vi timeout, retry, dữ liệu còn nhất quán | Không chứng minh dịch vụ lưu trữ bị mất thật |
| Mất nhóm backend của một FD/AD | Cô lập toàn bộ nhóm ứng dụng đã xác định | Năng lực còn lại, các phụ thuộc dùng chung | Chỉ mô phỏng nhóm tài nguyên đã cô lập |
| Chuyển sang region dự phòng | Diễn tập runbook DR với endpoint và dữ liệu dự phòng | RTO, RPO, định tuyến client, tính đúng đắn | Là thí nghiệm riêng, không suy từ bài mất backend |

Mỗi dòng nên được thực hiện độc lập trước khi thử tổ hợp lỗi. Chẳng hạn, kiểm tra database chậm trước, đo tác dụng giới hạn retry, rồi mới cân nhắc tổ hợp database chậm và mất một backend.

Với lỗi mạng, lưu ý một VNIC có thể chịu nhiều NSG và cả security list của subnet. Không được giả định xóa một rule allow trong một NSG sẽ chặn được lưu lượng khi vẫn có rule cho phép khác. Ưu tiên proxy hoặc đường thử nghiệm tách biệt khi mục tiêu chỉ là tạo timeout có kiểm soát.

## 7. Thiết kế tải không che giấu sự suy giảm

### 7.1. Chọn mô hình phát tải

Trong mô hình đóng với số người dùng ảo cố định, mỗi người dùng thường đợi phản hồi trước khi gửi tiếp. Khi hệ thống chậm, chính bộ phát tải có thể gửi ít yêu cầu hơn. Kết quả dễ tạo cảm giác hệ thống còn ổn dù thông lượng đã giảm.

Để kiểm tra một mức yêu cầu đến gần cố định, dùng mô hình mở. k6 cung cấp `constant-arrival-rate`: bắt đầu các iteration theo tốc độ đã cấu hình, độc lập với thời gian phản hồi nếu còn đủ virtual user (VU). Không thêm `sleep()` để điều tiết cuối mỗi iteration của executor này. Xem [tài liệu constant-arrival-rate của Grafana k6](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/).

Một iteration chỉ tương ứng một yêu cầu nếu script thực sự chỉ gửi một yêu cầu. Retry, redirect hoặc nhiều bước trong một iteration sẽ làm số request/giây khác số iteration/giây.

Ước lượng số lượt đang xử lý đồng thời:

~~~text
Số lượt đồng thời xấp xỉ tốc độ đến × thời gian một lượt

200 lượt/giây × 0,5 giây ≈ 100 lượt đồng thời
~~~

Đây là ước lượng để chuẩn bị VU, không phải cấu hình tối ưu mặc định. Cần đủ VU để duy trì tải cả khi timeout kéo dài, đồng thời máy phát tải phải có đủ CPU, bộ nhớ, socket và băng thông.

Nếu không còn VU khả dụng, executor có thể không khởi chạy đủ iteration. k6 ghi nhận trường hợp này bằng `dropped_iterations`; nguyên nhân có thể là cấu hình bộ phát hoặc thời gian xử lý của hệ thống tăng. Vì vậy phải kiểm tra đồng thời chỉ số này, tài nguyên máy phát và dữ liệu từ hệ thống đích. Xem [tài liệu Dropped iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/).

### 7.2. Script đọc danh mục bằng k6

Script dưới đây dành cho lab có hợp đồng API ở phần 3. Lưu script thành `ha-read.js` trong môi trường thực hành. Khi soạn bài học này, các lệnh chỉ là ví dụ cho người học; chúng không phải kết quả một lần chạy thực tế.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const requestOk = new Rate('request_ok');
const clientElapsed = new Trend('client_elapsed_ms', true);

const baseUrl = (__ENV.BASE_URL || '').replace(/\/$/, '');
const runId = __ENV.RUN_ID;
const rate = Number(__ENV.RATE || 200);
const duration = __ENV.DURATION || '10m';

if (!baseUrl || !runId) {
  throw new Error('Cần đặt BASE_URL và RUN_ID cho đúng môi trường lab.');
}
if (!Number.isInteger(rate) || rate <= 0) {
  throw new Error('RATE phải là số nguyên dương.');
}

http.setResponseCallback(http.expectedStatuses(200));

export const options = {
  maxRedirects: 0,
  tags: {
    run_id: runId,
  },
  scenarios: {
    catalog: {
      executor: 'constant-arrival-rate',
      rate: rate,
      timeUnit: '1s',
      duration: duration,
      preAllocatedVUs: 300,
      maxVUs: 1000,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    request_ok: ['rate>=0.999'],
    http_req_failed: ['rate<=0.001'],
    client_elapsed_ms: ['p(95)<=500', 'p(99)<=1000'],
    dropped_iterations: ['count==0'],
  },
  summaryTrendStats: ['avg', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const startedAt = Date.now();
  const response = http.get(baseUrl + '/api/catalog', {
    timeout: '3s',
    headers: {
      Accept: 'application/json',
      'X-Test-Run': runId,
    },
    tags: {
      name: 'GET /api/catalog',
    },
  });

  let validBody = false;
  if (response.status === 200) {
    try {
      const body = response.json();
      validBody =
        body !== null &&
        Array.isArray(body.items) &&
        body.items.some((item) => item && item.id === 'SKU-001');
    } catch (_) {
      validBody = false;
    }
  }

  const ok = response.status === 200 && validBody;
  clientElapsed.add(Date.now() - startedAt);
  requestOk.add(ok);

  check(response, {
    'HTTP 200 và catalog đúng dữ liệu lab': () => ok,
  });
}
~~~

`request_ok` ghi đúng một kết quả cho mỗi lượt, nên dễ dùng làm tỷ lệ thành công nghiệp vụ. `http_req_failed` hỗ trợ nhìn lỗi HTTP hoặc giao vận; nó không thay cho kiểm tra nội dung JSON. Các built-in metric và cách xác định yêu cầu thất bại được mô tả trong [tài liệu metric của k6](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/).

`client_elapsed_ms` đo khoảng thời gian bao quanh thao tác client và kiểm tra dữ liệu. Nó rộng hơn `http_req_duration`, vốn không đại diện cho toàn bộ thời gian phía client bao gồm các bước thiết lập kết nối. Đơn vị của các ngưỡng độ trễ trong script là mili giây.

Các ngưỡng trong `options.thresholds` đánh giá dữ liệu tổng hợp của lần chạy. Chúng là một phần tiêu chí, không tự kiểm tra các cửa sổ trượt hoặc thời điểm phục hồi trong phần 3. `check()` cũng cần threshold phù hợp nếu muốn dùng kết quả để quyết định đạt hay không đạt. Xem [tài liệu Thresholds của k6](https://grafana.com/docs/k6/latest/using-k6/thresholds/).

Script không đặt `abortOnFail` và không điều khiển hoàn tác backend. Cần người giám sát hoặc bộ điều phối riêng kiểm tra điều kiện dừng theo cửa sổ thời gian. Không được dựa vào việc k6 kết thúc để cho rằng lỗi đã được gỡ bỏ.

### 7.3. Chạy smoke, đối chứng và lần có lỗi

Ví dụ các lệnh dưới đây dùng Bash trên máy phát tải Linux đã cài k6. Thay địa chỉ thuộc miền `.invalid` bằng endpoint lab có chứng chỉ hợp lệ; không bỏ xác minh TLS để làm bài thử đạt.

~~~bash
export BASE_URL='https://catalog-ha-lab.example.invalid'
export RUN_ID='oci-ha-001-smoke'
export RATE='2'
export DURATION='30s'
k6 run ha-read.js
~~~

Sau smoke, chạy đối chứng tại tải mục tiêu:

~~~bash
export RUN_ID='oci-ha-001-baseline'
export RATE='200'
export DURATION='5m'
k6 run --out json=oci-ha-001-baseline.json ha-read.js
~~~

Chỉ chạy lần tiêm lỗi khi đối chứng đạt, tải thực tế phù hợp và không có vấn đề chưa giải thích được:

~~~bash
export RUN_ID='oci-ha-001-fault'
export RATE='200'
export DURATION='10m'
k6 run --out json=oci-ha-001-fault.json ha-read.js
~~~

Dùng `X-Test-Run` trong access log để phân biệt các lần chạy; tag `run_id` trong k6 phục vụ nhóm dữ liệu client. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào header phục vụ đối chiếu.

Đầu ra JSON có thể lớn. Chuẩn bị dung lượng, thời gian giữ dữ liệu và nơi lưu bằng chứng trước khi chạy. Ghi lại phiên bản k6, phiên bản script và cấu hình; khi tăng RATE đáng kể phải đánh giá lại số VU và khả năng của máy phát.

## 8. Quan sát đồng thời từ client, Load Balancer và backend

Một màn hình CPU không đủ để đánh giá khả năng chịu lỗi. Cần ít nhất ba góc nhìn:

| Nguồn | Cần thu thập | Câu hỏi trả lời |
| --- | --- | --- |
| Client phát tải | Yêu cầu bắt đầu, thành công nghiệp vụ, lỗi, độ trễ, dropped iteration | Người dùng có bị ảnh hưởng và tải có được duy trì |
| Load Balancer | Backend health, timeout, mã phản hồi, số kết nối | Backend lỗi được loại và đưa lại vào phục vụ ra sao |
| Compute và ứng dụng | CPU, bộ nhớ, GC, thread, pool kết nối, log lỗi | Backend còn lại có bão hòa hoặc phát sinh lỗi dây chuyền |
| Database/lưu trữ | Kết nối, độ trễ, lỗi, hàng đợi, lag nếu có replication | Phụ thuộc dùng chung có trở thành nút thắt |
| Điều phối | Thời điểm gây lỗi, hoàn tác, nhận cảnh báo | Cơ chế vận hành có đáp ứng thời gian yêu cầu |

Với OCI Load Balancer, namespace metric là `oci_lbaas`. Các metric liên quan gồm `unhealthyBackendServers`, `backendTimeouts` và `httpResponses5xx`; khi truy vấn phải chọn đúng resource, backend set và thành phần phù hợp. Oracle công bố chu kỳ phát các metric Load Balancer là 60 giây. Do đó, một biểu đồ tổng hợp một phút không đủ chứng minh chính xác một gián đoạn chỉ vài giây; cần bổ sung dữ liệu client và log có timestamp. Xem [tài liệu Load Balancer Metrics](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/loadbalancermetrics.htm).

OCI Monitoring cho phép truy vấn metric và tạo alarm; alarm có thể gửi tới đích như topic của Notifications. Các metric tài nguyên, metric tùy chỉnh và điều kiện alarm cần được chuẩn bị trước. Kiểm tra cả nơi nhận thông báo, không chỉ trạng thái alarm trong Console. Xem [tài liệu Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

Phân biệt ba thời điểm: backend bắt đầu lỗi, health checker phát hiện, và người vận hành nhận cảnh báo. Một alarm có cửa sổ đánh giá dài có thể gửi muộn hơn cơ chế định tuyến mà không có nghĩa Load Balancer phát hiện chậm.

Ở ứng dụng, ghi định danh backend, mã yêu cầu và mã lần thử nghiệm vào log. API điều khiển OCI và lệnh `systemctl` trong guest OS không có cùng nguồn nhật ký; lệnh trong guest cần dấu vết vận hành riêng. Không giả định mọi thao tác trong guest tự xuất hiện như một hành động OCI API.

## 9. Tiêm lỗi có hoàn tác: dừng một dịch vụ trên backend A

### 9.1. Kiểm tra health check trước khi gây lỗi

OCI Load Balancer kiểm tra backend theo chính sách của backend set và có thể dùng TCP hoặc HTTP. Với HTTP, nó có thể kiểm tra URI, mã phản hồi và nội dung. Backend không đạt kiểm tra bị tạm loại khỏi luồng phân phối; backend vượt qua kiểm tra trở lại có thể được đưa vào phục vụ. Xem [tài liệu Health Check Policies for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

Trong lab, cấu hình kiểm tra HTTP `/ready` trên cổng ứng dụng. Endpoint này phải phản ánh khả năng phục vụ tối thiểu cần thiết, thay vì luôn trả 200 từ một trang tĩnh.

Không nhồi mọi kiểm tra phụ thuộc tùy chọn vào readiness. Nếu một phụ thuộc phụ chậm khiến tất cả backend đồng loạt mất readiness, cơ chế kiểm tra sức khỏe có thể khuếch đại sự cố. Tách kiểm tra tiến trình còn sống với kiểm tra sẵn sàng phục vụ và kiểm tra nghiệp vụ từ ngoài.

Ghi lại interval, timeout và số lần thất bại cần thiết. Không coi interval nhân số lần retry là thời gian failover được bảo đảm: thời điểm lỗi so với lần probe kế tiếp, timeout và các kết nối đang tồn tại đều ảnh hưởng kết quả đo.

### 9.2. Lịch của lần chạy minh họa

Lần phát tải có lỗi kéo dài 10 phút:

| Thời gian từ đầu lần chạy | Hoạt động |
| --- | --- |
| 0–120 giây | Duy trì 200 yêu cầu/giây, xác nhận cả hai backend ổn định |
| Khoảng giây 120 | Đặt lịch hoàn tác, xác nhận lịch hoạt động, rồi dừng dịch vụ A |
| Từ lúc lỗi có hiệu lực | Ghi `t0`, quan sát phát hiện, chuyển tiếp và khả năng B phục vụ |
| Khoảng 120 giây sau khi đặt lịch | Lịch khởi động lại dịch vụ A; người vận hành có thể hoàn tác sớm |
| Sau khi A hoạt động | Xác nhận readiness, backend health, phân phối tải và kết quả client |
| Đến giây 600 | Tiếp tục quan sát trạng thái sau phục hồi, rồi kết thúc tải |

Khoảng lỗi 120 giây dùng để đo năng lực khi chỉ còn B; nó không phải thời gian cho phép dịch vụ ngừng phục vụ. Phục hồi nghiệp vụ có thể diễn ra trong khi A vẫn đang dừng.

### 9.3. Ví dụ lệnh trên đúng backend A

Các lệnh sau giả định guest Linux dùng systemd, service tên `catalog-api.service` và `systemctl` nằm ở `/usr/bin/systemctl`. Xác nhận các giả định này trong lab. Thực hiện qua phiên quản trị của **đúng instance A**, đã đối chiếu với OCID và IP riêng.

Đặt lịch khôi phục trước khi dừng dịch vụ. Tên unit cần duy nhất cho lần chạy để tránh nhầm với lịch cũ.

~~~bash
set -eu

date -u '+%Y-%m-%dT%H:%M:%SZ'
hostname
sudo systemctl is-active catalog-api.service
curl --fail --max-time 3 http://127.0.0.1:8080/ready

sudo systemd-run --unit=oci-ha-001-rollback --on-active=120s --timer-property=AccuracySec=1s /usr/bin/systemctl start catalog-api.service
sudo systemctl is-active --quiet oci-ha-001-rollback.timer

date -u '+%Y-%m-%dT%H:%M:%SZ'
sudo systemctl stop catalog-api.service
date -u '+%Y-%m-%dT%H:%M:%SZ'
~~~

Nếu việc tạo hoặc xác nhận timer thất bại, `set -e` khiến script dừng trước lệnh dừng dịch vụ. Cần xác nhận riêng đường quản trị và lệnh start có thể phục hồi ứng dụng; sự tồn tại của timer chưa chứng minh hoàn tác sẽ thành công.

`systemd-run` có thể tạo timer tạm thời để gọi một service khi hết thời gian, như mô tả trong [tài liệu systemd-run](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html). Lịch trên chạy ở máy A nên có thể hoạt động dù phiên SSH đóng, nhưng không bảo vệ được trường hợp máy A hoặc systemd không còn hoạt động. Đó là lý do ví dụ chỉ dừng dịch vụ, không dừng cả host.

Thời điểm timer chạy còn phụ thuộc scheduler và tình trạng máy; người giám sát phải xử lý nếu quá hạn mà dịch vụ chưa phục hồi. Nếu kiểm thử dừng instance, cần cơ chế hoàn tác ở ngoài instance thay cho timer trong guest.

`systemctl stop` thường cho ứng dụng cơ hội dừng theo cấu hình service. Vì vậy bài thử này kiểm chứng mất một dịch vụ có kiểm soát, chưa chứng minh hành vi của crash đột ngột hoặc kernel treo. Muốn kiểm tra các kiểu lỗi đó phải có thí nghiệm và cơ chế hoàn tác riêng.

Ghi thời điểm thực tế service ngừng phục vụ bằng log hoặc probe; hai dòng timestamp bao quanh lệnh chỉ tạo khoảng giới hạn cho sự kiện. Đừng lấy thời điểm người vận hành bấm Enter làm thời điểm lỗi chính xác khi lệnh dừng có thể cần chờ.

### 9.4. Hoàn tác và xác minh sau phục hồi

Nếu chạm điều kiện dừng hoặc muốn khôi phục trước timer, chạy trên A:

~~~bash
sudo systemctl start catalog-api.service
sudo systemctl is-active catalog-api.service
curl --fail --max-time 3 http://127.0.0.1:8080/ready
~~~

Tiếp theo, xác nhận qua Load Balancer rằng A trở lại healthy, log cho thấy A nhận yêu cầu và client vẫn đạt các ngưỡng. `systemctl` báo active không thay thế việc xác minh readiness hoặc kết quả nghiệp vụ.

Khi đã chắc chắn hoàn tác hoàn tất và timer chưa chạy, có thể hủy lịch còn chờ:

~~~bash
sudo systemctl stop oci-ha-001-rollback.timer
~~~

Nếu timer đã chạy, kiểm tra trạng thái và journal của unit tương ứng thay vì tạo lại lịch cùng tên một cách mù quáng. Chỉ kết thúc thí nghiệm khi cấu hình, số backend, khả năng dự phòng và đường quản trị đã trở về trạng thái dự kiến.

## 10. Đọc kết quả bằng dòng thời gian và cửa sổ

### 10.1. Một ví dụ kết quả minh họa

Bảng sau là dữ liệu giả định để luyện cách diễn giải, không phải số đo của OCI hay kết quả thực thi các lệnh trong bài.

| Mốc theo giây của lần chạy | Quan sát giả định |
| --- | --- |
| 120 | Dịch vụ A thực sự ngừng phục vụ, lấy làm `t0` |
| 131 | Backend A chuyển unhealthy |
| 139 | Bắt đầu khoảng đầu tiên mà chỉ số client đạt lại điều kiện ổn định |
| 169 | Đủ 30 giây liên tục để xác nhận khoảng tốt bắt đầu tại giây 139 |
| 240 | Lịch hoàn tác gọi start dịch vụ A |
| 247 | Readiness tại A đạt |
| 253 | A healthy và nhận tải trở lại; lấy làm `t_redundant` |
| 600 | Kết thúc thời gian phát tải; đợi các yêu cầu còn lại hoàn tất |

Kết quả suy ra:

~~~text
Phát hiện backend lỗi: 131 - 120 = 11 giây
Phục hồi dịch vụ: 139 - 120 = 19 giây
Xác nhận khoảng phục hồi: 169 - 120 = 49 giây sau lỗi
Khôi phục dự phòng: 253 - 120 = 133 giây
~~~

Giả sử phát đủ 120.000 yêu cầu, 18 yêu cầu không đạt nghiệp vụ, không có dropped iteration:

~~~text
Tỷ lệ thất bại = 18 / 120.000 = 0,015%
Tỷ lệ thành công = 99,985%
~~~

Con số toàn lần chạy đạt 99,9%, nhưng chưa đủ kết luận PASS. Cần tiếp tục kiểm tra:

- Cửa sổ 10 giây tệ nhất trong pha chuyển tiếp có nằm trong ngưỡng 1% hay không.
- Các cửa sổ ổn định khi chỉ B phục vụ có đạt thành công, p95 và p99 hay không.
- A trở lại có tạo thêm lỗi, bùng kết nối hoặc kéo chậm database hay không.
- Các ngưỡng tổng hợp của script có đạt và tải thực tế có đúng 200 lượt/giây hay không.

Ví dụ, nếu 12 trong 2.000 yêu cầu của cửa sổ chuyển tiếp tệ nhất bị lỗi thì tỷ lệ là 0,6%, nằm trong ngưỡng minh họa. Nếu thay vào đó có 40 lỗi trong cửa sổ đó, tỷ lệ 2% làm bài thử FAIL dù trung bình cả lần chạy trông tốt.

### 10.2. Xử lý dữ liệu thô

Từ dữ liệu timestamp của client, nhóm kết quả theo cửa sổ và pha đã định nghĩa. Với mỗi cửa sổ, tính ít nhất:

~~~text
số lượt bắt đầu
số yêu cầu hoàn tất và số thất bại
tỷ lệ thành công nghiệp vụ
p95 và p99 độ trễ
số iteration không được khởi chạy
~~~

Với timeout, request chỉ có kết quả khi hết timeout. Cần thống nhất dùng thời điểm bắt đầu hay kết thúc để gán kết quả vào cửa sổ và ghi rõ lựa chọn. Dùng thời điểm bắt đầu giúp gắn yêu cầu với pha nó gặp lỗi, nhưng phải đợi các yêu cầu đang chạy hoàn tất trước khi kết luận về cửa sổ đó.

Đầu ra metric k6 chủ yếu phản ánh thời điểm ghi metric. Nếu cần gán theo thời điểm bắt đầu chính xác, phải bổ sung cách ghi nhận phù hợp hoặc đối chiếu log yêu cầu; không giả định mọi timestamp metric là thời điểm request được gửi.

Không tính p95 của một pha bằng cách lấy trung bình các p95 nhỏ hơn. Cần tính percentile từ các quan sát thuộc đúng tập dữ liệu, hoặc dùng histogram có phương pháp tổng hợp phù hợp.

Nếu thiếu bằng chứng thời gian, máy phát tải bão hòa hoặc tải thực tế hụt, đánh dấu **INCONCLUSIVE** cho kết luận cần các bằng chứng đó. Không đổi thành PASS chỉ vì không quan sát thấy nhiều lỗi.

### 10.3. Những mẫu kết quả thường gặp

| Dấu hiệu | Khả năng cần điều tra | Hướng xử lý |
| --- | --- | --- |
| Backend A lỗi nhưng vẫn nhận nhiều request | Health check chưa phát hiện hoặc cấu hình kiểm tra không phản ánh service | Đối chiếu probe, cổng, URI, timeout và log backend |
| A bị loại nhưng B tăng latency mạnh | Thiếu năng lực N-1 hoặc nghẽn phụ thuộc chung | Đo B và database, điều chỉnh năng lực hoặc giới hạn tài nguyên |
| Tải client giảm khi lỗi xuất hiện | Mô hình tải đóng hoặc thiếu VU/tài nguyên bộ phát | Kiểm tra số lượt bắt đầu, dropped iteration và tài nguyên máy phát |
| HTTP 200 nhưng nghiệp vụ sai | Health hoặc kiểm tra kết quả quá nông | Thêm đối soát hợp đồng và dữ liệu |
| A healthy trở lại rồi flapping | Khởi động chưa hoàn tất, cache lạnh hoặc phụ thuộc chưa ổn định | Cải thiện readiness và quá trình nhận tải trở lại |
| Retry tăng đột biến, database nghẽn | Các tầng retry khuếch đại lưu lượng | Đặt ngân sách retry, timeout và giới hạn đồng thời |
| Không nhận được cảnh báo | Sai đích Notifications, alarm hoặc quyền truy cập | Kiểm tra đường thông báo từ điều kiện đến người nhận |
| Lỗi chỉ xảy ra ở kết nối lâu | Kết nối đang tồn tại không được bảo vệ bởi việc định tuyến request mới | Thử riêng WebSocket, streaming hoặc phiên dài |

## 11. Mở rộng sang giao dịch ghi và cơ sở dữ liệu Oracle

API GET cho biết khả năng đọc danh mục khi mất backend. Nó không chứng minh rằng đơn hàng, thanh toán hoặc cập nhật tồn kho còn đúng khi timeout hoặc database chuyển vai trò.

Với giao dịch ghi, cần bổ sung một hợp đồng riêng:

1. Mỗi thao tác có mã nghiệp vụ và idempotency key duy nhất.
2. Bộ phát lưu sổ đối chiếu ở ngoài thành phần đang bị gây lỗi.
3. Phân biệt giao dịch đã được xác nhận thành công, đã thất bại rõ ràng và chưa biết kết quả.
4. Sau phục hồi, truy vấn theo mã nghiệp vụ để đối chiếu trạng thái thực tế.
5. Kiểm tra bản ghi trùng, bản ghi thiếu và các bất biến nghiệp vụ, chẳng hạn tồn kho không âm.

Timeout ở client không đồng nghĩa database đã rollback. Giao dịch có thể commit nhưng phản hồi bị mất. Nếu cứ gửi lại với mã mới, bài kiểm thử có thể tự tạo trùng giao dịch. Retry cần giữ cùng định danh và ứng dụng phải có cơ chế xử lý idempotent phù hợp.

Để đánh giá mất dữ liệu, đối chiếu những giao dịch đã được xác nhận trước sự cố với trạng thái sau phục hồi, kèm thời điểm hoặc thứ tự giao dịch đáng tin cậy. Số lượng bản ghi tổng bằng nhau vẫn chưa đủ: thiếu một đơn và trùng một đơn khác có thể giữ nguyên tổng số.

Nếu dùng Oracle Data Guard hoặc Autonomous Data Guard, cần phân biệt **switchover có kế hoạch** với **failover khi primary gặp sự cố**. Tài liệu Autonomous Data Guard mô tả switchover đổi vai trò primary/standby không mất dữ liệu. Trong khi đó, tài liệu thao tác failover của Base Database cảnh báo khả năng mất dữ liệu phụ thuộc chế độ bảo vệ. Không suy từ một lần switchover thành công sang cam kết RPO bằng 0 cho mọi failover. Tham khảo [Autonomous Data Guard Switchover and Failover](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-data-guard-switchover-failover.html) và [OCI CLI: failover-data-guard](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/database/failover-data-guard.html).

Trong thí nghiệm database riêng, ghi rõ loại dịch vụ, cấu hình replication, lag quan sát được, thao tác chuyển vai trò và hành vi kết nối lại của ứng dụng. Không đưa vào một lệnh failover dùng chung cho mọi dịch vụ Oracle.

Khôi phục database cũ sau failover cũng không đơn giản là bật nó trở lại làm primary. Phải theo runbook của cấu hình đó để kiểm tra vai trò, tránh hai phía cùng nhận ghi và xác minh quan hệ replication trước khi khôi phục dự phòng.

Với Object Storage hoặc File Storage, kiểm tra tình huống upload bị gián đoạn, retry và việc database đã ghi tham chiếu nhưng đối tượng chưa hoàn tất. Sự tồn tại của một bản sao dữ liệu không tự chứng minh thao tác nhiều hệ thống là nguyên tử.

## 12. Tự động hóa thí nghiệm và kiểm soát chi phí

Khi thí nghiệm thủ công đã rõ ràng, có thể chuyển thành một workflow có điều kiện:

~~~text
Xác nhận tài nguyên và quyền
  -> Xác nhận trạng thái ổn định
  -> Chạy đối chứng
  -> Đặt cơ chế hoàn tác độc lập
  -> Phát tải và tiêm đúng một lỗi
  -> Giám sát điều kiện dừng
  -> Hoàn tác trong nhánh finally
  -> Xác minh ứng dụng và dự phòng
  -> Thu thập bằng chứng
  -> Đánh giá và dọn tài nguyên lab
~~~

Trong triển khai tự động, nhánh `finally` cần chạy cả khi công cụ tải báo lỗi hoặc bước đánh giá thất bại. Tuy vậy, một runner bị tắt có thể không chạy được `finally`; cơ chế hoàn tác độc lập vẫn cần tồn tại. Với tài nguyên OCI, dùng danh sách đích được phép và kiểm tra OCID thay vì chọn tài nguyên chỉ bằng chuỗi tên gần giống.

Đặt giới hạn cứng cho thời lượng, RATE, số máy phát, số VU và số tài nguyên có thể mở rộng. Những giới hạn này hỗ trợ bảo vệ cả chất lượng thí nghiệm lẫn ngân sách.

Các nguồn chi phí cần tính gồm Compute của ứng dụng và bộ phát tải, Load Balancer, database hoặc standby, lưu trữ, log/metric, bản sao phục hồi và lưu lượng qua các đường mạng liên quan. Không giả định tài nguyên dùng cho bài HA đều thuộc phần miễn phí.

Giữ cấu hình hạ tầng có thể tái tạo, gắn nhãn chủ sở hữu và mã thí nghiệm để đối chiếu chi phí. Khi kết thúc, kiểm tra cả volume, backup, log và tài nguyên phụ còn lại; dừng một instance không có nghĩa toàn bộ tài nguyên liên quan đã ngừng tính phí.

Tự động hóa phải lưu cấu hình trước thử nghiệm và xác minh trạng thái sau hoàn tác. Một pipeline chỉ nhìn exit code của k6 sẽ bỏ sót trường hợp bài kiểm thử đạt nhưng backend A vẫn chưa được phục hồi.

## 13. Báo cáo kết quả đủ để người khác kiểm tra

Một báo cáo thí nghiệm cần nêu rõ:

- **Mục tiêu:** giả thuyết, loại lỗi và phạm vi ảnh hưởng thực tế.
- **Môi trường:** region, placement AD/FD, định danh tài nguyên, phiên bản ứng dụng và cấu hình liên quan.
- **Tải:** mô hình, số lượt/giây, thời lượng, dữ liệu, retry, timeout và nguồn phát tải.
- **Tiêu chí:** ngưỡng từng pha, cửa sổ, bước trượt, điều kiện dừng và mục tiêu phục hồi.
- **Dòng thời gian:** lỗi có hiệu lực, phát hiện, khoảng phục hồi, hoàn tác và khôi phục dự phòng.
- **Bằng chứng:** dữ liệu client, truy vấn metric, log, trạng thái backend và đối soát dữ liệu nếu có ghi.
- **Kết quả:** PASS, FAIL hoặc INCONCLUSIVE cho từng giả thuyết, kèm lý do và giới hạn.
- **Trạng thái kết thúc:** backend và cấu hình đã phục hồi, tài nguyên còn tồn tại và việc cần xử lý.

Ví dụ kết luận phù hợp với phạm vi bài:

> Ở tải 200 yêu cầu/giây và bộ dữ liệu đã mô tả, hệ thống đạt các tiêu chí khi dịch vụ trên một backend dừng có kiểm soát. Backend còn lại duy trì được tải, và backend được khôi phục nhận tải trở lại trong giới hạn đặt trước. Kết quả chưa bao gồm crash host, mất AD, sự cố region hoặc tính toàn vẹn của giao dịch ghi.

Nếu một tiêu chí thất bại, liên kết trực tiếp số đo với giả thuyết: chẳng hạn năng lực B không đủ ở tải N-1, health check không phản ánh readiness, hoặc retry khiến database bão hòa. Nếu không phát đủ tải, thiếu dữ liệu hoặc không xác nhận được lỗi đã xảy ra, cần nêu rõ điều kiện nào chưa được chứng minh.

Giá trị của bài kiểm chứng nằm ở việc nối được **lỗi cụ thể → phản ứng của kiến trúc → ảnh hưởng nghiệp vụ → bằng chứng phục hồi**. Lặp lại khi có thay đổi đáng kể về ứng dụng, cấu hình, placement hoặc phụ thuộc; giữ cùng điều kiện đối chứng để nhận ra hồi quy.
