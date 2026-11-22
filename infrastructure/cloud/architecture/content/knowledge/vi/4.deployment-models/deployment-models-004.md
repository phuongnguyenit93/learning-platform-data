# Kiến trúc tại biên và phân chia xử lý giữa biên với đám mây

Trong thiết kế kiến trúc ứng dụng đám mây (**Cloud Architecture**), không phải mọi dữ liệu đều cần đi đến một trung tâm dữ liệu từ xa trước khi tạo ra giá trị. Một máy quét tại nhà kho cần phản hồi tức thì; camera giám sát nhà máy có thể phát sinh lượng video rất lớn; thiết bị ở vùng kết nối yếu vẫn phải hoạt động khi đường truyền Internet gián đoạn. **Kiến trúc tại biên (edge architecture)** đưa một phần xử lý đến gần nơi dữ liệu được tạo hoặc hành động được thực hiện, đồng thời sử dụng đám mây để tổng hợp, phối hợp, lưu trữ lâu dài, phân tích và quản trị tập trung.

Trong chương **Mô hình triển khai**, bài này giải thích cách phân chia chức năng giữa **thiết bị, nút biên, vùng mạng cục bộ và đám mây**. Quyết định này phải dựa trên yêu cầu nghiệp vụ, hạn mức độ trễ, băng thông, khả năng chạy ngoại tuyến, đặc tính dữ liệu và mức độ rủi ro. Kết quả cần là một sơ đồ luồng dữ liệu và một tập quyết định kiến trúc có thể kiểm chứng, với đánh đổi rõ ràng về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt xử lý trên thiết bị, tại biên, tại vùng mạng cận biên và trên đám mây.
- Chọn vị trí thực thi cho từng tác vụ theo yêu cầu độ trễ, tài nguyên, dữ liệu và kết nối.
- Thiết kế luồng dữ liệu và điều khiển giữa biên và cloud, kể cả khi mạng mất kết nối.
- Xử lý các vấn đề hàng đợi, đồng bộ, xung đột, tính nhất quán và điều khiển an toàn.
- Xây dựng chiến lược bảo mật, triển khai phiên bản, quan sát và quản lý đội thiết bị phân tán.
- Đánh giá một phương án edge–cloud bằng thước đo cụ thể thay vì chỉ dựa vào khẩu hiệu “đưa xử lý về gần người dùng”.

## 1. Edge computing là gì và nằm ở đâu?

**Edge computing** là việc đặt khả năng tính toán, lưu trữ hoặc xử lý dữ liệu gần nguồn dữ liệu hay nơi cần phản hồi. “Gần” có thể là khoảng cách vật lý, số chặng mạng hoặc miền vận hành có độ trễ thấp. Biên không nhất thiết là một máy chủ đặt trong nhà máy; nó cũng có thể là điện thoại, gateway tại cửa hàng, cụm máy ở trạm viễn thông hoặc hệ thống xử lý tại điểm hiện diện của nhà cung cấp.

| Tầng | Vị trí điển hình | Năng lực và ràng buộc | Vai trò thường gặp |
| --- | --- | --- | --- |
| **Thiết bị (device/on-device)** | Cảm biến, camera, điện thoại, máy công nghiệp | CPU/RAM/điện hạn chế; phụ thuộc phần cứng | Thu thập tín hiệu, kiểm tra đơn giản, phản hồi rất nhanh |
| **Biên cục bộ (local edge)** | Gateway, máy chủ tại cửa hàng, nhà máy, trạm | Tài nguyên tốt hơn thiết bị; có thể hoạt động trong LAN | Lọc dữ liệu, suy luận AI, hàng đợi ngoại tuyến, điều phối tại chỗ |
| **Biên mạng/cận biên (network edge)** | Điểm hiện diện mạng, cụm gần người dùng, MEC | Độ trễ mạng có thể thấp; quản trị phụ thuộc nhà cung cấp | Cache, xử lý gần thuê bao, API độ trễ thấp |
| **Cloud region** | Trung tâm dữ liệu của nhà cung cấp | Năng lực co giãn lớn, dịch vụ quản lý phong phú | Nguồn dữ liệu tập trung, phân tích lớn, huấn luyện mô hình, điều phối fleet |
| **Vùng dự phòng/DR** | Region hoặc cơ sở dự phòng được phê duyệt | Thêm chi phí và yêu cầu đồng bộ | Phục hồi thảm họa, dự phòng các hệ thống tập trung |

Edge và cloud **không loại trừ nhau**. Phổ biến nhất là kiến trúc phân tán theo mức độ phù hợp của tác vụ: phần cần phản hồi tại chỗ chạy ở biên; phần cần tầm nhìn toàn hệ thống, tài nguyên lớn hoặc lưu trữ lâu dài chạy ở cloud.

### 1.1. Những khái niệm dễ nhầm

- **Edge computing:** nơi đặt và thực thi xử lý gần nguồn dữ liệu.
- **IoT:** tập hợp thiết bị kết nối, giao thức và ứng dụng; IoT có thể dùng edge nhưng không bắt buộc.
- **Fog computing:** khái niệm về các tầng xử lý trung gian phân tán giữa thiết bị và cloud; có phần giao nhau với edge.
- **Content Delivery Network (CDN):** hệ thống điểm hiện diện chuyên lưu cache/phân phối nội dung; một số nền tảng có thể chạy xử lý tại edge, nhưng CDN không đồng nghĩa với toàn bộ kiến trúc edge.
- **Multi-access Edge Computing (MEC):** tài nguyên tính toán gần mạng truy cập, thường liên quan hạ tầng viễn thông.
- **Hybrid cloud:** kết hợp hạ tầng tại chỗ và cloud theo một kiến trúc vận hành; một hệ thống hybrid có thể có edge, nhưng không phải mọi hệ thống hybrid đều phục vụ xử lý thời gian thực tại biên.

Một gateway có nhiệm vụ chuyển tiếp gói tin đơn thuần chưa chắc giải quyết được bài toán edge computing. Giá trị kiến trúc xuất hiện khi nút đó có trách nhiệm xử lý cụ thể và có khả năng hoạt động phù hợp với SLA/SLO của nghiệp vụ.

## 2. Khi nào cần đặt xử lý tại biên?

Bắt đầu từ **yêu cầu có thể đo**, không bắt đầu từ danh sách sản phẩm hoặc công nghệ. Sáu nhóm câu hỏi chính:

1. **Độ trễ:** tổng thời gian từ cảm nhận sự kiện đến phản hồi tối đa bao nhiêu? Giá trị là trung bình, p95, p99 hay giới hạn cứng? Có cần phản hồi ngay cả khi WAN gián đoạn không?
2. **Lưu lượng:** dữ liệu tạo ra bao nhiêu theo thời gian, tính cả giờ cao điểm? Phần nào cần bản thô, phần nào có thể lọc, nén hoặc tổng hợp?
3. **Khả dụng:** khi Internet chập chờn hoặc cloud không truy cập được, thiết bị cần tiếp tục hoạt động thế nào, trong bao lâu?
4. **Vị trí và bảo mật dữ liệu:** có dữ liệu cá nhân, bí mật sản xuất, hình ảnh nhạy cảm hoặc quy định giới hạn nơi truyền/đặt dữ liệu không?
5. **Tài nguyên:** thiết bị/edge có đủ CPU, RAM, GPU/NPU, đĩa, điện, tản nhiệt và khả năng bảo trì không?
6. **Mức độ phối hợp:** quyết định cần dữ liệu từ một thiết bị, từ cả một địa điểm hay từ toàn mạng lưới?

### 2.1. Phân loại tác vụ bằng đặc tính

| Đặc tính tác vụ | Ưu tiên edge khi… | Ưu tiên cloud khi… |
| --- | --- | --- |
| Độ trễ phản hồi | Phải phản hồi trong vài mili giây đến hàng chục mili giây; WAN biến động nhiều | Cho phép thời gian phản hồi lớn hơn, có thể xử lý không đồng bộ |
| Khối lượng dữ liệu thô | Dữ liệu lớn, phần lớn không có giá trị khi truyền nguyên bản | Dữ liệu nhỏ hoặc thực sự cần tập trung để xử lý |
| Kết nối | Cần hoàn thành thao tác cục bộ khi WAN mất | Tác vụ phụ thuộc nguồn dữ liệu, dịch vụ hoặc danh tính tập trung |
| Phạm vi quyết định | Dựa chủ yếu vào tín hiệu tại một vị trí | Cần tối ưu và đối chiếu toàn hệ thống |
| Quy mô tính toán | Mô hình nhỏ, xử lý gần cảm biến, ngân sách phần cứng phù hợp | Huấn luyện mô hình lớn, xử lý batch, cần tài nguyên co giãn |
| Dữ liệu nhạy cảm | Có thể chỉ gửi đặc trưng/sự kiện đã giảm thông tin | Phải tập trung dữ liệu theo mục đích được phép và kiểm soát phù hợp |
| Quản trị phiên bản | Có thể đóng gói, kiểm soát và cập nhật theo lô thiết bị | Muốn triển khai thường xuyên trên hạ tầng tập trung |

Đây là chỉ dẫn ban đầu, không phải luật tuyệt đối. Một mô hình AI nhỏ vẫn có thể cần cloud nếu thiết bị không đáp ứng bộ nhớ; một tác vụ tổng hợp toàn hệ thống có thể có một phần tính toán trước tại edge để giảm dữ liệu truyền.

### 2.2. Độ trễ phải tính từ đầu đến cuối

Một tác vụ thường trải qua chuỗi:

~~~text
Thu nhận tín hiệu
  -> Tiền xử lý
  -> Truyền tới nơi xử lý
  -> Xếp hàng
  -> Thực thi nghiệp vụ / suy luận
  -> Trả kết quả
  -> Thực hiện hành động
~~~

Tổng thời gian xấp xỉ:

**Tổng độ trễ = thu nhận + tiền xử lý + truyền mạng + chờ hàng đợi + xử lý + truyền phản hồi + thực thi hành động.**

Ví dụ minh họa, một dây chuyền cần phản hồi trong **50 ms**. Nếu các phần cục bộ gồm thu nhận 8 ms, truyền LAN 4 ms, tiền xử lý 6 ms, suy luận 12 ms, kiểm tra chính sách 5 ms và kích hoạt cơ cấu 10 ms, tổng là **45 ms** trước khi tính thêm dao động và dự phòng. Nếu chỉ riêng vòng đi–về cloud đã lớn hơn ngân sách này, đặt bước quyết định thời gian thực tại cloud không thể đáp ứng. Cần kiểm chứng bằng phân bố p95/p99 tại môi trường thật, vì độ trễ trung bình thường che khuất các lần phản hồi chậm.

Không nên suy ra mọi vòng cloud đều chậm hoặc mọi edge đều nhanh. Một edge yếu, quá tải CPU hoặc thẻ nhớ chậm có thể cho kết quả tệ hơn một hệ thống cloud được tối ưu. Điều cần đo là **độ trễ đầu cuối khi tải bình thường, khi cao điểm và khi có lỗi**.

## 3. Quy tắc phân chia xử lý giữa biên và cloud

Có thể quyết định theo ba hướng: **xử lý tại biên, xử lý trên cloud hoặc chia tác vụ thành nhiều bước ở cả hai nơi**. Với mỗi bước, cần xác định ai sở hữu trạng thái chính thức, dữ liệu được sao chép hay chỉ truyền sự kiện, và khi mất kết nối thì hành vi nào được phép.

### 3.1. Ma trận phân chia tham khảo

| Tác vụ | Vị trí đề xuất | Lý do |
| --- | --- | --- |
| Đọc cảm biến, xử lý chống nhiễu đơn giản | Device/edge | Tần suất cao, gần nguồn |
| Dừng máy hoặc phản hồi điều khiển có yêu cầu an toàn | Bộ điều khiển cục bộ chuyên dụng | Phải độc lập với WAN và ứng dụng không bảo đảm thời gian thực |
| Suy luận hình ảnh tại dây chuyền | Edge có GPU/NPU nếu phù hợp | Giảm độ trễ và lưu lượng video |
| Lọc, khử trùng lặp, tổng hợp sự kiện | Edge | Tránh gửi dữ liệu thô dư thừa |
| Cache dữ liệu tham chiếu dùng tại điểm bán | Edge | Giảm phụ thuộc WAN |
| Xác thực một thao tác đã được cấp quyền ngoại tuyến | Edge với chính sách và thời hạn rõ | Duy trì hoạt động có giới hạn khi mất mạng |
| Huấn luyện mô hình lớn | Cloud hoặc cụm tính toán chuyên dụng | Cần dữ liệu tổng hợp và tài nguyên lớn |
| Quản lý danh tính tập trung | Cloud/trung tâm | Định danh và chính sách nhất quán, phân phối bản sao cần thiết |
| Tổng hợp doanh thu nhiều chi nhánh | Cloud | Cần dữ liệu đa địa điểm |
| Lưu trữ lâu dài, báo cáo, BI | Cloud hoặc nền tảng dữ liệu được duyệt | Co giãn lưu trữ, truy vấn và quản trị |
| Phân phối cấu hình và phiên bản mô hình | Cloud điều phối, edge thực thi | Có quản trị chung nhưng hoạt động cục bộ |
| Kiểm toán và phân tích xu hướng toàn đội thiết bị | Cloud | Cần góc nhìn tập trung; edge có thể đệm sự kiện |

**Ngoại lệ quan trọng:** nếu một hành động liên quan đến an toàn máy móc hoặc con người, vòng điều khiển cần được thiết kế, thẩm định và triển khai bằng hệ thống bảo đảm an toàn phù hợp. Ứng dụng edge thông thường không tự động đủ điều kiện thay thế PLC, safety controller hoặc cơ chế liên động an toàn.

### 3.2. Hai hướng phân chia phổ biến

**Cloud quản trị, edge thực thi:** cloud xác định cấu hình, phân phối phiên bản và tổng hợp trạng thái; edge xử lý yêu cầu cục bộ. Cách này hợp với hàng nghìn cửa hàng, trạm hoặc gateway cần quản trị thống nhất.

**Edge xử lý sơ cấp, cloud phân tích sâu:** edge trích xuất đặc trưng, phát hiện sự kiện và lọc dữ liệu; cloud kết hợp nhiều nguồn để phân tích dài hạn. Cách này hợp với video, dữ liệu công nghiệp và mạng cảm biến có lưu lượng lớn.

Hai hướng thường được kết hợp trong một kiến trúc. Để tránh mâu thuẫn, phải nêu rõ **đường đi của dữ liệu (data plane)** và **đường điều khiển/quản trị (control plane)**.

## 4. Kiến trúc tham chiếu: đường dữ liệu và đường điều khiển

Sơ đồ giả định một địa điểm sản xuất có nhiều cảm biến/camera, một cụm edge và dịch vụ cloud:

~~~mermaid
flowchart TB
    subgraph SITE["Tại địa điểm: miền hoạt động cục bộ"]
        S["Cảm biến / Camera"] --> GW["Gateway thu thập"]
        GW --> P["Tiền xử lý, lọc và suy luận"]
        P --> A["Quyết định cục bộ"]
        A --> ACT["Cơ cấu chấp hành / hệ thống nghiệp vụ"]
        P --> Q[("Hàng đợi và vùng đệm bền vững")]
        P --> EDB[("Dữ liệu cục bộ cần thiết")]
        CM["Agent quản trị thiết bị"] --> P
    end

    subgraph CLOUD["Cloud / nền tảng tập trung"]
        MQ["Dịch vụ nhận sự kiện"]
        STORE[("Data lake / kho sự kiện")]
        ANALYTICS["Phân tích và báo cáo"]
        REG["Kho cấu hình, phiên bản ứng dụng / mô hình"]
        FLEET["Quản trị fleet, quan sát, kiểm toán"]
    end

    Q -- "Đồng bộ sự kiện khi có mạng" --> MQ
    MQ --> STORE
    STORE --> ANALYTICS
    FLEET --> REG
    REG -- "Cập nhật có ký xác nhận" --> CM
    CM -- "Trạng thái, phiên bản, sức khỏe" --> FLEET
~~~

Trong sơ đồ:

- **Luồng vận hành cục bộ:** cảm biến → tiền xử lý → quyết định → hành động. Những bước có yêu cầu chạy ngoại tuyến không phụ thuộc vào cloud trong đường xử lý bắt buộc.
- **Luồng dữ liệu lên cloud:** sự kiện hoặc dữ liệu đã chọn → bộ đệm → nền tảng nhận → lưu trữ và phân tích. Mất WAN làm chậm đồng bộ, không nhất thiết dừng công việc cục bộ.
- **Luồng quản trị từ cloud:** cấu hình, mô hình hoặc phiên bản ứng dụng → cơ chế phân phối được xác thực → agent tại edge → áp dụng có kiểm soát. Edge cần giữ phiên bản ổn định khi không nhận được cấu hình mới.

Sơ đồ là một mẫu để thảo luận, không phải lời khẳng định rằng một dịch vụ riêng lẻ có thể tự cung cấp toàn bộ tính năng. Mỗi mũi tên còn cần giao thức, dữ liệu, quyền truy cập, cơ chế retry và cách quan sát.

### 4.1. Chọn giao thức dựa vào ngữ nghĩa

| Cơ chế | Thích hợp cho | Lưu ý |
| --- | --- | --- |
| HTTP/HTTPS API | Yêu cầu–phản hồi, đăng ký thiết bị, tải cấu hình | Không nên ép thao tác ngoại tuyến phụ thuộc request đồng bộ |
| MQTT hoặc giao thức pub/sub tương tự | Telemetry, sự kiện, thiết bị kết nối không ổn định | Phải thiết kế QoS, phiên, xác thực, chủ đề và giới hạn buffer |
| AMQP, queue hoặc event streaming | Luồng sự kiện cần kiểm soát nhận/trả, lưu trữ, replay | Chọn retention, thứ tự trong phân vùng và cơ chế idempotency |
| gRPC hoặc RPC nhị phân | Liên lạc giữa dịch vụ có hợp đồng mạnh, hiệu quả payload | Cần kiểm soát deadline, retry và phiên bản |
| OPC UA/giao thức công nghiệp phù hợp | Tích hợp hệ thống thiết bị công nghiệp | Cần gateway bảo mật, vùng mạng OT/IT và hiểu giới hạn hệ thống hiện hữu |

Giao thức chỉ là một phần. Chẳng hạn, “gửi MQTT QoS 1” không chứng minh nghiệp vụ sẽ xử lý một lần duy nhất. Cần xác định **ý nghĩa hoàn tất**: sự kiện đã tới broker, được ghi bền vững, đã xử lý hay đã phản ánh trong hệ thống nghiệp vụ.

## 5. Mẫu thiết kế dữ liệu giữa edge và cloud

### 5.1. Lọc, tổng hợp và suy luận tại nguồn

Ví dụ video giám sát dây chuyền có thể tạo dữ liệu liên tục, trong khi bộ phận vận hành chỉ cần biết **thời điểm xuất hiện lỗi, vị trí lỗi, mức tin cậy và một đoạn ảnh minh chứng được phê duyệt**. Edge có thể:

1. Nhận luồng video tại LAN.
2. Tiền xử lý và chạy mô hình phát hiện lỗi.
3. Tạo sự kiện nhỏ với thời gian, ID thiết bị, loại lỗi và phiên bản mô hình.
4. Lưu bản gốc trong thời gian ngắn khi cần xử lý lại hoặc điều tra; hạn chế quyền truy cập.
5. Gửi sự kiện hoặc đoạn dữ liệu được chọn lên cloud theo chính sách lưu giữ và bảo mật.

Lợi ích là giảm băng thông và tiếp xúc với dữ liệu thô. Đánh đổi là cần quản lý mô hình trên nhiều nút, phát hiện drift và lưu đủ dấu vết để kiểm chứng kết quả.

### 5.2. Store-and-forward khi mất mạng

**Store-and-forward** là cơ chế giữ sự kiện tại chỗ cho đến khi có thể gửi lên cloud. Chuỗi vận hành:

~~~mermaid
sequenceDiagram
    participant D as Thiết bị
    participant E as Edge
    participant Q as Bộ đệm bền vững
    participant C as Cloud

    D->>E: Sự kiện mới
    E->>Q: Ghi bền vững (eventId, sequence, payload)
    Q-->>E: Đã ghi
    Note over E,C: WAN gián đoạn
    D->>E: Sự kiện tiếp theo
    E->>Q: Tiếp tục ghi trong giới hạn dung lượng
    Note over E,C: WAN khôi phục
    loop Gửi các sự kiện chưa xác nhận
        E->>C: Gửi lô có giới hạn tốc độ
        C->>C: Kiểm tra idempotency, ghi nhận xử lý
        C-->>E: Xác nhận mức xử lý đã cam kết
        E->>Q: Đánh dấu đã đồng bộ
    end
~~~

Để làm đúng, cần thiết kế **độ bền của buffer, giới hạn dung lượng, hạn mức ghi, tốc độ đồng bộ bù, retry, cách xác nhận và trường hợp đĩa đầy**.

- Dùng **eventId** hoặc khóa nghiệp vụ để cloud loại bỏ sự kiện được gửi lại.
- Dùng **sequence number** theo thiết bị hoặc luồng để nhận biết sự kiện thiếu, trùng hoặc sai thứ tự.
- Ghi **event time** và **ingestion time** riêng; đồng bộ giờ thiết bị và có phương án khi đồng hồ bị lệch.
- Lưu trạng thái checkpoint một cách bền vững nếu ứng dụng cần tiếp tục sau khi edge khởi động lại.
- Dùng retry có **exponential backoff kèm jitter**, giới hạn tốc độ và cảnh báo backlog để tránh nghẽn khi hàng loạt thiết bị cùng kết nối lại.
- Làm rõ hành vi khi hàng đợi đầy: ưu tiên sự kiện quan trọng, tạm ngừng thu dữ liệu có thể bỏ, tăng vùng đệm hợp lệ hoặc báo lỗi. Không được âm thầm làm mất dữ liệu đã cam kết phải giữ.

Trong hệ thống phân tán, retry thường dẫn đến **at-least-once delivery**; vì vậy downstream cần xử lý **idempotent**. Không nên mặc định có exactly-once từ đầu đến cuối chỉ vì một dịch vụ broker có tính năng giao nhận đặc biệt.

### 5.3. Đồng bộ trạng thái và tính nhất quán

Khó khăn hơn gửi telemetry là đồng bộ dữ liệu **có thể sửa ở cả hai phía**, ví dụ giá hàng tại chi nhánh và bảng giá trung tâm, hoặc trạng thái đơn hàng khi cửa hàng ngoại tuyến.

| Loại dữ liệu | Nguồn có thẩm quyền đề xuất | Phương án đồng bộ |
| --- | --- | --- |
| Telemetry từ cảm biến | Thiết bị/edge tạo sự kiện | Append-only, truyền bù, dedup |
| Quy tắc, cấu hình, phiên bản mô hình | Hệ thống quản trị tập trung | Phiên bản rõ ràng, edge áp dụng có xác nhận |
| Số dư, quyền truy cập hoặc giao dịch cần tính nhất quán mạnh | Dịch vụ nghiệp vụ được chỉ định | Hạn chế thao tác ngoại tuyến; dùng cơ chế giao dịch được thiết kế riêng |
| Kết quả tác vụ tại địa điểm | Hệ thống thực thi tại edge | Sự kiện bất biến, đồng bộ lên cloud, xử lý xung đột theo nghiệp vụ |
| Dữ liệu tham chiếu ít đổi | Cloud phát hành | Cache theo phiên bản, TTL và cơ chế vô hiệu hóa |

**Một nguyên tắc quan trọng:** chỉ định **một nguồn có thẩm quyền cho từng trường hoặc loại lệnh** nếu có thể. Nếu cả edge và cloud đều được sửa cùng bản ghi, cần chính sách xung đột xác định trước: phiên bản tăng dần, miền sở hữu, hợp nhất theo trường hoặc quy trình hòa giải nghiệp vụ. Chọn bản ghi có timestamp mới nhất có thể sai khi đồng hồ lệch, nhất là với giao dịch tài chính.

Trong thời gian mạng đứt, hai phía không thể đồng thời có mọi cập nhật tức thời và vẫn bảo đảm vận hành độc lập. Kiến trúc phải chọn rõ thao tác nào có thể **eventual consistency**, thao tác nào phải chờ xác nhận từ nguồn có thẩm quyền, và thao tác nào bị khóa để tránh sai nghiệp vụ.

### 5.4. Trạng thái ngoại tuyến không đồng nghĩa “mọi thứ vẫn chạy”

Nên phân loại chức năng theo mức chấp nhận khi mất WAN:

| Nhóm thao tác | Khi mất WAN | Ví dụ |
| --- | --- | --- |
| **Tiếp tục đầy đủ tại chỗ** | Hoàn thành cục bộ, đồng bộ về sau | Phân loại hình ảnh, đo cảm biến, cảnh báo tại thiết bị |
| **Tiếp tục có điều kiện** | Dùng quyền/cấu hình được cấp trước, có TTL hoặc hạn mức | Quét hàng đã cấp quyền, kiểm tra điều kiện bảo trì |
| **Chỉ ghi nhận chờ xử lý** | Xếp hàng yêu cầu, chưa tuyên bố thành công nghiệp vụ | Đề nghị thay đổi cấu hình cần phê duyệt trung tâm |
| **Tạm dừng an toàn** | Từ chối hoặc chuyển quy trình dự phòng | Thanh toán trực tuyến cần xác thực, hành động vượt thẩm quyền |

Không hiển thị “thành công” nếu hệ thống mới chỉ ghi yêu cầu chờ đồng bộ mà nghiệp vụ yêu cầu xác nhận từ cloud. UI và API cần mô tả các trạng thái như **đã xử lý cục bộ, đang chờ đồng bộ, đã được chấp nhận tập trung, bị từ chối**.

## 6. Tính toán năng lực: băng thông, compute và lưu trữ

Giải pháp edge chỉ có lợi nếu tài nguyên tại biên đủ cho tải cao điểm và chi phí sở hữu có thể chấp nhận.

### 6.1. Ước tính lưu lượng

Ví dụ minh họa: một nhà kho có **40 camera**, mỗi camera phát sinh luồng trung bình **2 Mbps** sau nén.

- Lưu lượng thô tổng cộng: **40 × 2 = 80 Mbps**, tương đương khoảng **10 MB/giây**.
- Nếu chuyển liên tục 24 giờ, lượng dữ liệu xấp xỉ **864 GB/ngày** theo đơn vị thập phân, chưa tính overhead giao thức và biến động bitrate.
- Nếu edge chỉ cần gửi dữ liệu chiếm **5%** so với đầu vào, lưu lượng truyền còn khoảng **43,2 GB/ngày**, tương ứng mức giảm 95% trong giả định này.

Số liệu là phép tính minh họa, **không phải cam kết** rằng mọi mô hình phân tích sẽ nén được 95% dữ liệu. Nếu bài toán yêu cầu điều tra từ video gốc, phải tính thêm chính sách lưu video, số lượng clip sự kiện và luồng tải lại khi cần.

Với buffer ngoại tuyến, ước tính cơ bản:

**Dung lượng tối thiểu ≈ tốc độ dữ liệu cần giữ × thời gian mất kết nối thiết kế.**

Nếu buộc lưu nguyên video ở mức **10 MB/giây** khi WAN mất **2 giờ**, riêng dữ liệu đầu vào cần khoảng **72 GB**. Thực tế phải cộng headroom cho biến động lưu lượng, metadata, cơ chế ghi đĩa, backlog đồng bộ và thời gian phát hiện sự cố. Nếu chỉ giữ sự kiện đã lọc, dung lượng có thể nhỏ hơn đáng kể. Cần xác định rõ dữ liệu nào **bắt buộc** được giữ.

### 6.2. Ước tính năng lực xử lý

Khi chạy suy luận ở edge, không chỉ chọn CPU/GPU theo thông số tối đa của nhà sản xuất. Phải đo:

- Throughput, FPS hoặc số sự kiện/giây khi tất cả camera hoạt động đồng thời.
- Độ trễ p95/p99 qua toàn bộ pipeline, kể cả tiền xử lý và I/O.
- Giới hạn RAM, dung lượng cache, khả năng ghi đĩa và băng thông LAN.
- Nhiệt độ, điện năng và hành vi giảm xung khi thiết bị chạy liên tục.
- Khả năng chạy song song phiên bản cũ/mới trong lúc cập nhật mô hình.
- Phần dự phòng khi một nút trong cụm edge lỗi hoặc khi phải đồng bộ backlog.

Một phép thử throughput chỉ chạy một camera không chứng minh cụm xử lý được 40 camera đồng thời. Cần thử **tải cực đại, burst và thời gian chạy dài**.

### 6.3. Chi phí toàn vòng đời

So sánh **TCO (Total Cost of Ownership)** thay vì chỉ hóa đơn cloud:

| Hạng mục | Xử lý nhiều trên cloud | Xử lý nhiều tại edge |
| --- | --- | --- |
| Băng thông WAN/egress | Có thể cao nếu đưa dữ liệu thô lên | Có thể giảm nhờ lọc và tổng hợp |
| Compute | Trả theo tài nguyên cloud; co giãn tốt | Mua/thuê phần cứng phân tán; giới hạn theo thiết bị |
| Lưu trữ | Dễ tăng dung lượng tập trung | Cần đĩa tại chỗ, kiểm tra độ bền và thay thế |
| Vận hành | Ít địa điểm phần cứng hơn | Cần quản trị fleet, cập nhật, hỗ trợ từ xa, xử lý mất điện |
| Khả dụng ngoại tuyến | Phụ thuộc kết nối nếu mọi tác vụ ở cloud | Có thể độc lập hơn nếu thiết kế đúng |
| Bảo mật | Quản trị tập trung nhưng dữ liệu truyền nhiều | Giảm dữ liệu rời địa điểm nhưng tăng số điểm cần bảo vệ |
| Nâng cấp | Triển khai dịch vụ tập trung nhanh | Phải tính vòng đời phần cứng, tương thích và rollback |

Chi phí kết nối, điện, thay linh kiện, đường đến địa điểm và thời gian hỗ trợ kỹ thuật có thể lớn hơn phần chênh lệch chi phí compute. Đánh giá edge nên có **phân tích độ nhạy** khi số địa điểm, lưu lượng và tần suất hỏng thiết bị thay đổi.

## 7. Độ tin cậy và quản lý lỗi phân tán

Kiến trúc edge có nhiều miền lỗi hơn hệ thống tập trung: cảm biến, gateway, LAN, WAN, cloud, dịch vụ nhận sự kiện, ổ đĩa và nguồn điện có thể lỗi độc lập. Cần mô tả điều gì còn hoạt động khi từng phần lỗi.

### 7.1. Failure mode và cách xử lý

| Sự cố | Tác động | Hành vi/kiểm soát mong muốn |
| --- | --- | --- |
| WAN đứt | Không liên lạc với cloud, backlog tăng | Tiếp tục tác vụ cục bộ được phép, buffer bền vững, cảnh báo và đồng bộ bù |
| Edge process lỗi | Gián đoạn xử lý tại địa điểm | Supervisor restart, health check, giới hạn retry, phục hồi checkpoint |
| Gateway mất điện | Thiết bị mất khả năng xử lý trung gian | UPS khi cần, cơ chế local fallback, xác định phạm vi downtime được chấp nhận |
| Đĩa edge đầy hoặc hỏng | Không thể ghi sự kiện, nguy cơ mất dữ liệu | Giám sát dung lượng, retention, chống ghi tràn, báo lỗi có ưu tiên |
| Cloud nhận sự kiện chậm | Hàng đợi edge tăng | Backpressure, retry có giới hạn, ưu tiên sự kiện cần thiết |
| Cloud gửi cấu hình lỗi | Nhiều edge có thể bị ảnh hưởng đồng loạt | Canary rollout, kiểm tra chữ ký/cấu trúc, pin phiên bản, rollback |
| Edge dùng mô hình quá cũ | Chất lượng dự đoán giảm | Theo dõi phiên bản, hạn sử dụng/chính sách cho phép tiếp tục chạy |
| Sai đồng hồ | Dữ liệu sai thứ tự và phân tích lệch | Đồng bộ thời gian, giữ sequence, phân biệt event time với ingest time |

Không thể đo độ tin cậy edge chỉ bằng uptime của cloud. Phải đo **tỷ lệ tác vụ địa điểm hoàn tất đúng hạn** và **mức mất dữ liệu thực tế khi các thành phần lỗi**.

### 7.2. RTO/RPO và sự cố mất kết nối

- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục chức năng sau một loại sự cố đã xác định.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, diễn đạt theo thời gian hoặc điểm khôi phục thích hợp.
- **Độ trễ đồng bộ (sync lag):** thời gian chênh giữa sự kiện tại edge và lúc có thể truy vấn trong cloud.

Các chỉ số này không thay thế nhau. Edge có thể xử lý ổn khi WAN mất nhưng **sync lag** lên tới vài giờ; nếu ổ đĩa bị hỏng trước khi đẩy dữ liệu lên, RPO thực tế có thể kém dù ứng dụng chưa từng ngừng xử lý.

Nếu đặt mục tiêu “không mất sự kiện khi WAN đứt 4 giờ”, cần kiểm tra khả năng chịu lỗi của **bộ đệm cục bộ**, không chỉ lượng ổ đĩa. Nếu yêu cầu chịu đồng thời hỏng một ổ đĩa hoặc một nút, cần thiết kế cơ chế nhân bản hoặc ghi nhận phù hợp và kiểm tra cách hoạt động khi các lỗi chồng nhau.

## 8. Bảo mật biên đến đám mây

Một nút edge có thể nằm tại cửa hàng, nhà máy, trụ điện hoặc khu vực ít được bảo vệ vật lý hơn trung tâm dữ liệu. Việc đưa xử lý về gần nguồn mở ra lợi ích giảm truyền dữ liệu, nhưng cũng tạo thêm **điểm quản trị, nơi lưu khóa và bề mặt tấn công**.

### 8.1. Xác thực và danh tính thiết bị

Mỗi thiết bị/gateway cần **danh tính riêng**, không chia sẻ một khóa bí mật chung cho mọi thiết bị. Một mô hình hợp lý gồm:

1. Cấp phát danh tính ban đầu qua quy trình onboarding tin cậy.
2. Dùng chứng chỉ/khóa hoặc cơ chế xác thực mạnh phù hợp với thiết bị; xem xét **mTLS** cho kết nối hai chiều.
3. Giới hạn quyền theo thiết bị, tenant, địa điểm và loại tác vụ: thiết bị tại chi nhánh A không được đọc dữ liệu hoặc nhận lệnh của chi nhánh B.
4. Xoay vòng và thu hồi danh tính khi thay thiết bị, mất thiết bị hoặc phát hiện xâm nhập.
5. Theo dõi danh mục phần cứng, firmware, phiên bản agent và chủ sở hữu.

Phải thiết kế rõ trường hợp edge không liên hệ được dịch vụ cấp quyền: quyền nào có thể dùng ngoại tuyến, trong bao lâu và khi nào buộc dừng. Một token không giới hạn thời hạn giúp ngoại tuyến dễ hơn nhưng làm tăng rủi ro bị lạm dụng.

### 8.2. Bảo vệ phần mềm và dữ liệu

- Bật cơ chế khởi động tin cậy/secure boot, bảo vệ khóa bằng TPM, phần cứng bảo mật hoặc cơ chế tương đương nếu thiết bị hỗ trợ và mức rủi ro yêu cầu.
- Phân phối **ứng dụng, firmware, container image và mô hình AI có xác minh nguồn gốc/chữ ký**; ghi lại phiên bản đã áp dụng.
- Mã hóa dữ liệu trên đường truyền và dữ liệu lưu tại biên nếu phù hợp; quản lý khóa có khả năng phục hồi khi mất mạng.
- Tách mạng thiết bị/OT khỏi mạng văn phòng và Internet bằng phân đoạn và chỉ cho phép luồng cần thiết.
- Hạn chế đăng nhập quản trị từ xa; ghi log thao tác đặc quyền, sử dụng quyền có thời hạn và cơ chế thu hồi.
- Lọc dữ liệu nhạy cảm trước khi ghi log, gửi metrics hoặc truyền sang bên thứ ba.
- Giới hạn việc edge thực thi lệnh từ cloud bằng xác thực, kiểm tra quyền, kiểm tra phiên bản và quy tắc an toàn cục bộ.

**Zero Trust** ở đây có nghĩa là mỗi kết nối và tác vụ đều cần kiểm tra danh tính, quyền và ngữ cảnh; không mặc định thiết bị an toàn chỉ vì nó ở trong LAN của nhà máy.

### 8.3. Vị trí và tuân thủ dữ liệu

Một quyết định “giữ video tại edge, chỉ truyền metadata lên cloud” có thể giúp giảm việc chuyển dữ liệu nhạy cảm, nhưng metadata như ID thiết bị, vị trí, thời điểm, hình ảnh cắt hoặc user ID vẫn có thể là dữ liệu cá nhân.

Khi thiết kế cần kiểm kê:

- Nơi lưu bản gốc, cache, snapshot, backup, log và vùng đồng bộ tạm.
- Nơi cloud tiếp nhận và xử lý, bao gồm dịch vụ quan sát, phân tích hoặc hỗ trợ.
- Ai có thể truy cập từ xa và dữ liệu nào được phép xuất ra ngoài địa điểm/quốc gia.
- Thời gian giữ dữ liệu tại edge, cách xóa khi kết thúc mục đích sử dụng, khi thiết bị mất hoặc bị loại bỏ.
- Hợp đồng, quy định và chính sách vị trí áp dụng cho từng loại dữ liệu.

Đặt dữ liệu tại chỗ **không tự động bảo đảm** tuân thủ. Phạm vi nghĩa vụ cần được đối chiếu với pháp chế, an toàn thông tin và chủ sở hữu dữ liệu theo từng hệ thống.

## 9. Quản trị và cập nhật hàng nghìn nút edge

Ở cloud, có thể cập nhật một dịch vụ tập trung; ở edge, hệ thống phải xử lý thiết bị không đồng nhất, phiên bản lệch nhau, mất nguồn và nhiều địa điểm. Do đó, **fleet management** là thành phần kiến trúc cốt lõi, không phải việc bổ sung khi triển khai xong.

### 9.1. Chu trình quản lý thiết bị

~~~mermaid
flowchart LR
    A["Đăng ký thiết bị"] --> B["Cấp danh tính và chính sách"]
    B --> C["Phân phối ứng dụng / mô hình"]
    C --> D["Chạy và gửi trạng thái"]
    D --> E["Theo dõi, cảnh báo, vá lỗi"]
    E --> F["Nâng cấp theo đợt / canary"]
    F --> D
    D --> G["Thu hồi, xóa dữ liệu, ngừng sử dụng"]
~~~

Một bản triển khai edge nên có:

- **Desired state:** phiên bản phần mềm, cấu hình và mô hình được phê duyệt cho từng nhóm thiết bị.
- **Reported state:** phiên bản và tình trạng thực tế mà edge đang chạy; phân biệt thiết bị **không báo về** với thiết bị **đang lỗi**.
- **Canary rollout:** triển khai thử ở một tỷ lệ nhỏ địa điểm, theo dõi chỉ số trước khi mở rộng.
- **Rollback:** quay về phiên bản đã biết tốt nếu bản mới làm tăng lỗi, độ trễ hoặc giảm độ chính xác.
- **Quy tắc tương thích:** phiên bản edge cũ vẫn giao tiếp an toàn với cloud mới trong một khoảng thời gian xác định.
- **Quy trình thu hồi thiết bị:** hủy chứng chỉ/khóa, xóa dữ liệu, xác nhận bàn giao hoặc tiêu hủy.

Khi không có mạng, edge nên duy trì **last known good configuration** đã được xác thực và thuộc phạm vi còn hiệu lực. Nhưng không nên chạy vô thời hạn cấu hình quan trọng đã hết hạn nếu điều đó vi phạm yêu cầu an toàn hoặc chính sách quyền.

### 9.2. Quan sát hoạt động và gỡ lỗi từ xa

Cloud cần nhận tín hiệu sức khỏe của từng địa điểm, nhưng không cần gửi toàn bộ dữ liệu thô. Các chỉ số có ích:

| Nhóm | Chỉ số gợi ý |
| --- | --- |
| Tác vụ nghiệp vụ | Số sự kiện xử lý, tỷ lệ thành công, độ trễ p95/p99 đầu cuối |
| Thiết bị | CPU/GPU, RAM, nhiệt độ, đĩa, năng lượng, phiên bản firmware |
| Kết nối | Thời gian WAN gián đoạn, RTT, tỉ lệ lỗi gửi, chất lượng đường truyền |
| Đồng bộ | Kích thước backlog, tuổi sự kiện cũ nhất, tốc độ catch-up, sự kiện bị loại |
| Mô hình AI | Phiên bản, thời gian suy luận, drift, độ tin cậy, tỷ lệ dự đoán bất thường |
| Bảo mật | Xác thực thất bại, lỗi kiểm tra chữ ký, thay quyền, thiết bị không đạt chính sách |

Khi offline, edge vẫn cần lưu một lượng log và metrics **có giới hạn**, sau đó đồng bộ các tín hiệu cần điều tra. Phải lập ngân sách cho dữ liệu quan sát để không làm đầy đĩa dành cho sự kiện nghiệp vụ.

## 10. Ví dụ thiết kế: phát hiện lỗi sản phẩm tại nhà máy

Giả sử một dây chuyền có camera kiểm tra sản phẩm. Nghiệp vụ cần phát hiện sản phẩm lỗi đủ nhanh để kích hoạt cơ cấu loại bỏ trên băng chuyền; quản lý cần thống kê tỷ lệ lỗi theo ca và so sánh nhiều nhà máy.

### 10.1. Yêu cầu giả định

| Yêu cầu | Giá trị minh họa | Ý nghĩa kiến trúc |
| --- | --- | --- |
| Phản hồi xử lý ảnh | p99 nhỏ hơn 100 ms trong điều kiện tải đã định nghĩa | Pipeline quyết định ở tại chỗ |
| Mất WAN | Tiếp tục kiểm tra sản phẩm 4 giờ | Không đặt cloud trên đường quyết định cốt lõi |
| Dữ liệu video | Mặc định xử lý tại nhà máy; chỉ tải clip được phê duyệt | Giảm băng thông và giới hạn phân phối dữ liệu |
| Báo cáo tập trung | Có thể chậm tối đa 30 phút khi mạng ổn định | Đồng bộ sự kiện bất đồng bộ |
| Cập nhật mô hình | Phải biết phiên bản và có thể rollback | Fleet manager và model registry |
| Điều khiển loại bỏ sản phẩm | Phải đi qua hệ thống điều khiển được thẩm định | Phân tách AI detection khỏi cơ chế an toàn vật lý |

Các mốc trên là giả định để thực hành, không phải chỉ tiêu chung cho mọi nhà máy. Trước khi thiết kế cần xác định độ trễ từ lúc camera nhìn thấy sản phẩm đến thời điểm cơ cấu cần tác động, kể cả tốc độ băng chuyền và vị trí cảm biến.

### 10.2. Phân chia chức năng

**Tại dây chuyền:** camera tạo ảnh; gateway đưa ảnh vào inference service; dịch vụ phát hiện lỗi trả kết quả; ứng dụng local kết hợp vị trí sản phẩm với thời điểm để yêu cầu controller xử lý. Controller vẫn áp dụng cơ chế liên động và quy tắc an toàn riêng. Các sự kiện lỗi được gán ID và ghi bền vững.

**Tại nhà máy:** cluster edge hoặc máy chủ công nghiệp lưu trữ sự kiện, quản lý hàng đợi, áp dụng cấu hình cục bộ và cho người vận hành xem trạng thái. Hệ thống có thể tiếp tục ghi nhận và xử lý trong phạm vi được phê duyệt khi WAN đứt.

**Trên cloud:** message broker nhận sự kiện; data platform tổng hợp tỷ lệ lỗi theo nhà máy; nhóm dữ liệu đánh giá mô hình và huấn luyện phiên bản mới từ dữ liệu được phép; hệ thống quản lý fleet phân phối mô hình đã phê duyệt theo từng nhóm thiết bị.

### 10.3. Luồng sự kiện mẫu

Ví dụ cấu trúc sự kiện ở lớp ứng dụng:

~~~json
{
  "eventId": "site-07-line-2-camera-3-0005412",
  "siteId": "site-07",
  "deviceId": "camera-3",
  "sequence": 5412,
  "eventTime": "2026-11-18T08:23:14.211Z",
  "eventType": "PRODUCT_DEFECT_DETECTED",
  "modelVersion": "vision-3.2.1",
  "confidence": 0.96,
  "productTraceId": "batch-17-item-982",
  "evidenceRef": "edge://site-07/evidence/0005412",
  "schemaVersion": 1
}
~~~

Các giá trị chỉ minh họa. **evidenceRef** là tham chiếu nội bộ tại edge, không phải URL mà cloud hoặc người dùng ngoài mạng có thể truy cập mặc định. Cần quyết định riêng xem có tải ảnh lên cloud hay không, ai phê duyệt, quyền xem và thời gian giữ.

### 10.4. Đường dữ liệu khi WAN gián đoạn

1. Edge vẫn suy luận và gửi yêu cầu đến bộ điều khiển tại chỗ trong giới hạn được thiết kế.
2. Hệ thống ghi sự kiện có ID vào bộ đệm bền vững; UI cho biết dữ liệu đang chờ đồng bộ.
3. Giám sát tại chỗ cảnh báo khi buffer đạt ngưỡng; chính sách ưu tiên bảo toàn các sự kiện quan trọng.
4. Khi mạng khôi phục, sự kiện được gửi lại theo lô; cloud xác nhận sau khi ghi nhận ở mức đã định nghĩa.
5. Cloud xử lý idempotent, dùng **eventTime** để phân tích thời gian diễn ra và **ingestionTime** để đo độ trễ nhận.
6. Nhân sự vận hành kiểm tra backlog đã về 0, không có sequence bị thiếu và thời gian báo cáo đã trở lại mức mục tiêu.

### 10.5. Điểm phải thử trước khi nghiệm thu

- Chạy toàn bộ số camera đồng thời và đo p99 từ lúc nhận ảnh đến tín hiệu điều khiển.
- Ngắt WAN đủ 4 giờ; xác nhận vận hành cục bộ và thời gian backlog tối đa.
- Khởi động lại gateway giữa lúc chưa đồng bộ; kiểm tra sự kiện không mất và không bị nhân đôi trong kết quả nghiệp vụ.
- Cố ý gửi sự kiện trùng hoặc sai thứ tự; xác nhận logic dedup và xử lý sequence.
- Triển khai mô hình mới cho một dây chuyền; chủ động đưa mô hình lỗi và thử rollback.
- Giả lập đĩa gần đầy, dịch vụ cloud chậm và khóa/cert hết hạn để xem hệ thống cảnh báo và chuyển trạng thái an toàn.
- Đánh giá dữ liệu trong event, log, clip và quyền truy cập từ xa so với chính sách bảo mật đã phê duyệt.

Đây là các bài kiểm tra hệ thống cụ thể, không thể thay bằng một bài benchmark GPU hoặc tuyên bố rằng broker “hỗ trợ retry”.

## 11. Các lỗi kiến trúc thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đặt mọi quyết định ở cloud vì triển khai đơn giản | Độ trễ biến động, mất WAN làm dừng nghiệp vụ | Tách đường xử lý bắt buộc cục bộ khỏi đồng bộ bất đồng bộ |
| Đẩy toàn bộ dữ liệu thô lên cloud | Tốn băng thông, tăng độ trễ và rủi ro dữ liệu | Lọc/tổng hợp tại nguồn; chỉ lưu bản gốc khi có mục đích |
| Dùng edge mà không có quản lý fleet | Version drift, không biết thiết bị nào lỗi hoặc chưa vá | Thiết kế onboarding, desired/reported state, canary và rollback |
| Tin rằng nhận sự kiện một lần là đủ | Retry gây dữ liệu trùng, thống kê sai | Dùng eventId, idempotency, checkpoint và đo mất/trùng sự kiện |
| Cho edge và cloud sửa cùng dữ liệu không có quyền sở hữu | Xung đột khi mạng nối lại, mất tính nhất quán | Định nghĩa nguồn có thẩm quyền và quy tắc hòa giải theo nghiệp vụ |
| Coi offline là “cứ dùng cache” | Dữ liệu/quyền hết hạn vẫn được sử dụng | Chia chức năng thành tiếp tục, tiếp tục có điều kiện, chờ hoặc tạm dừng |
| Không tính buffer cho thời gian mất WAN | Đĩa đầy và mất dữ liệu ngay lúc cần nhất | Dự toán lưu lượng cao điểm, khoảng offline, headroom và chính sách ưu tiên |
| Không kiểm soát lệnh điều khiển từ cloud | Lệnh sai/giả có thể gây hậu quả vật lý | Xác thực, phân quyền, giới hạn và kiểm tra an toàn tại chỗ |
| Chỉ theo dõi uptime cloud | Không thấy lỗi dây chuyền, backlog và thiết bị | Đo SLO nghiệp vụ đầu cuối và sức khỏe từng edge |
| Đặt dữ liệu gần nguồn rồi coi là đã tuân thủ | Log, support và hệ thống phân tích vẫn có thể chuyển dữ liệu | Kiểm kê toàn bộ luồng, nơi lưu và bên có quyền truy cập |

## 12. Quy trình thiết kế kiến trúc edge–cloud

Đối với dự án mới, có thể triển khai theo các bước:

1. **Thu thập yêu cầu:** ghi các thao tác cần thực hiện tại địa điểm; xác định độ trễ p95/p99, thời gian mất WAN dự kiến, lượng dữ liệu và nghĩa vụ bảo mật/tuân thủ.
2. **Phân rã nghiệp vụ:** chia ứng dụng thành thu thập, lọc, suy luận, quyết định, điều khiển, lưu tạm, đồng bộ, tổng hợp và quản trị.
3. **Quyết định placement:** gán mỗi tác vụ cho device, local edge, network edge hoặc cloud; chỉ rõ phụ thuộc giữa các bước và giới hạn tài nguyên.
4. **Vẽ đường dữ liệu:** mô tả sự kiện, quyền, vùng lưu trữ, trạng thái chính thức, checkpoint, retention, luồng ra/vào đối tác.
5. **Thiết kế offline:** xác định chức năng tiếp tục/chờ/dừng, khả năng buffer, retry, đồng bộ bù, trùng sự kiện và quy tắc xung đột.
6. **Thiết kế vận hành và bảo mật:** định danh thiết bị, phân quyền, vòng đời khóa, ký bản cập nhật, rollout, rollback, audit và quan sát.
7. **Lập ngân sách:** đo latency p99, tài nguyên CPU/GPU, đĩa, điện, lưu lượng WAN, chi phí sở hữu và dự phòng.
8. **Kiểm chứng thực tế:** benchmark tải cao điểm, thử đứt mạng, khởi động lại, lỗi ổ đĩa, cập nhật thất bại và xâm nhập giả định; điều chỉnh thiết kế theo kết quả.
9. **Ghi quyết định:** lưu Architecture Decision Record (ADR) cho những đánh đổi lớn và người phê duyệt ngoại lệ.

### 12.1. Biểu mẫu quyết định vị trí xử lý

Đoạn YAML sau là **bản ghi quyết định minh họa**, không phải cấu hình của một nền tảng thực thi:

~~~yaml
workload: visual_defect_detection
business_owner: manufacturing_quality
classification: confidential
critical_path:
  input: camera_frame
  output: reject_recommendation
  latency_slo_p99_ms: 100
placement:
  capture: device
  preprocess: local_edge
  inference: local_edge
  local_policy_decision: local_edge
  physical_actuation: validated_local_controller
  aggregate_analytics: cloud
network:
  offline_target_hours: 4
  cloud_on_critical_path: false
data:
  cloud_payload: approved_defect_metadata
  source_of_truth_for_observations: edge_event_log
  delivery: at_least_once
  deduplication_key: eventId
  evidence_retention: approved_schedule
operations:
  update_strategy: staged_rollout
  rollback_required: true
  fleet_health_reporting: required
verification:
  - p99_under_peak_load
  - four_hour_wan_outage
  - power_restart_with_backlog
  - duplicate_event_replay
  - failed_model_rollout
~~~

Những giá trị như **approved_schedule** là chỗ giữ chỗ. Khi dùng thực tế, cần gắn lịch lưu giữ được duyệt, phương thức đo và kết quả thử nghiệm; một tệp YAML không tự bảo đảm rằng các kiểm soát đã được thực thi.

## 13. Đánh giá theo Well-Architected

Đưa edge vào kiến trúc không tự làm hệ thống tốt hơn. Hãy đánh giá mỗi phương án dựa trên năm góc nhìn thường gặp:

| Góc đánh giá | Câu hỏi cần trả lời |
| --- | --- |
| **Độ tin cậy** | Khi WAN hoặc cloud lỗi, chức năng nào còn chạy? Sự kiện có thể mất khi đĩa edge hỏng không? Có đo sync lag, RTO/RPO và diễn tập phục hồi không? |
| **Bảo mật** | Thiết bị được cấp danh tính thế nào? Ai có thể gửi lệnh từ cloud? Dữ liệu nào rời địa điểm? Có kiểm soát cập nhật và thu hồi khóa không? |
| **Hiệu quả hiệu năng** | Pipeline có đạt p95/p99 tại tải thực? CPU/GPU và mạng có còn headroom? Việc phân chia tác vụ có thực sự giảm thời gian phản hồi không? |
| **Tối ưu chi phí** | Tổng chi phí cloud, WAN, phần cứng biên, thay thế, điện và vận hành là bao nhiêu? Kết quả có thay đổi khi số địa điểm tăng? |
| **Khả năng vận hành** | Có biết phiên bản, sức khỏe và backlog của từng thiết bị? Có thể rollout/rollback an toàn khi một số điểm đang offline không? |

### Checklist trước khi chốt thiết kế

- [ ] Mỗi bước xử lý có vị trí thực thi và lý do được ghi thành quyết định kiến trúc.
- [ ] Đường xử lý cần phản hồi thời gian thực không phụ thuộc ngoài ý muốn vào cloud/WAN.
- [ ] Độ trễ p95/p99 và throughput đã được thử trong tải tương đương môi trường thực.
- [ ] Các chế độ mất kết nối, đồng bộ lại, dữ liệu trùng/sai thứ tự và xung đột có quy tắc rõ.
- [ ] Bộ đệm được tính theo thời gian mất mạng, tốc độ dữ liệu và giới hạn dung lượng thực tế.
- [ ] Danh tính, quyền, mã hóa, cập nhật có xác minh, rollback và thu hồi thiết bị được thiết kế.
- [ ] Dữ liệu thô, sự kiện, log, bản sao và đối tác có vị trí, quyền truy cập, thời gian lưu phù hợp.
- [ ] Có SLO cho chức năng tại địa điểm, độ trễ đồng bộ và trạng thái fleet.
- [ ] Kịch bản lỗi quan trọng đã được diễn tập, đo kết quả và lưu bằng chứng.

## 14. Bài tập áp dụng

Một chuỗi cửa hàng có 150 điểm bán. Mỗi cửa hàng tạo giao dịch và dùng cache danh mục sản phẩm. Đường Internet có thể ngắt 30 phút; bộ phận tài chính yêu cầu báo cáo doanh thu toàn chuỗi trong vòng 15 phút khi mạng ổn định. Khách hàng phải được thông báo rõ giao dịch nào hoàn tất và giao dịch nào chờ đối soát.

Hãy phác thảo thiết kế theo các câu hỏi:

1. Những thao tác nào tiếp tục ở cửa hàng khi mất WAN? Những thao tác nào phải chờ nguồn dữ liệu có thẩm quyền?
2. Danh mục hàng hóa, tồn kho, lịch sử giao dịch và số dư nên có nguồn có thẩm quyền ở đâu? Dữ liệu nào được cache hoặc ghi tạm?
3. Làm thế nào để cửa hàng không gửi trùng giao dịch sau khi kết nối lại? Nếu giá đổi trong lúc cửa hàng offline thì xử lý theo quy tắc nào?
4. Cần đo những chỉ số nào để biết cửa hàng đang vận hành đúng, dữ liệu không thất lạc và báo cáo tài chính không quá trễ?
5. So sánh chi phí và độ tin cậy giữa mô hình xử lý hoàn toàn trên cloud với mô hình có gateway tại mỗi cửa hàng.

Không có một đáp án chung cho mọi chuỗi bán lẻ. Điều cần thể hiện là **quy tắc nghiệp vụ, trách nhiệm dữ liệu, trạng thái ngoại tuyến và điều kiện kiểm chứng** nhất quán với nhau.

Kiến trúc tại biên phát huy giá trị khi ranh giới giữa **xử lý cục bộ** và **xử lý tập trung** được thiết kế rõ ràng. Edge giúp phản hồi nhanh, giảm lưu lượng và duy trì một phần vận hành khi mạng lỗi; cloud giúp tổng hợp thông tin, quản trị và mở rộng tài nguyên. Chất lượng kiến trúc nằm ở khả năng giải thích vì sao từng tác vụ được đặt ở một tầng, dữ liệu di chuyển và đồng bộ như thế nào, và hệ thống có chứng minh được các cam kết về hiệu năng, an toàn, chi phí và vận hành hay không.
