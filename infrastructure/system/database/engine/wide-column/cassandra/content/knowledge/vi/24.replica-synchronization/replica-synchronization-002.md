# Hinted handoff và giới hạn thời gian lưu/phát lại hint

## Mục tiêu bài học

Apache Cassandra sao chép một partition tới nhiều **replica** để tiếp tục phục vụ khi node hoặc đường mạng gặp lỗi. Nhưng khi một replica tạm thời không nhận được mutation, làm thế nào nó bắt kịp sau khi hoạt động trở lại? Một cơ chế hỗ trợ quan trọng là **hinted handoff**: những node đang xử lý request có thể tạm ghi lại mutation dành cho replica vắng mặt dưới dạng **hint**, rồi chuyển lại khi replica đó sẵn sàng.

Điểm cần hiểu đúng: **hint không phải bản sao thứ tư, không phải hàng đợi bền vững vô hạn và không thay thế anti-entropy repair**. Cassandra có giới hạn về **cửa sổ tạo/lưu hint cho node bị down**, lượng dữ liệu hint, tốc độ phát lại và điều kiện node đích có thể nhận. Khi một node vắng mặt quá lâu hoặc hệ thống chịu nhiều lỗi đồng thời, các replica có thể vẫn chưa đồng bộ dù hinted handoff được bật.

Bài học thuộc chương **Đồng bộ bản sao** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung nối cơ chế hint với replication factor (RF), consistency level (CL), đường đọc/ghi, CQL, tombstone, TTL, repair, compaction, xử lý sự cố và mã Java Driver 4.x.

Sau bài học, bạn có thể:

1. Giải thích **khi nào hint được tạo**, được lưu ở đâu, được gửi lại cho replica nào và khi nào hint không được tạo.
2. Phân biệt **cửa sổ tạo hint** với **thời gian phát lại**, **TTL dữ liệu**, `gc_grace_seconds` và lịch repair.
3. Tính tải hint ước lượng từ tốc độ mutation, thời gian replica vắng mặt, kích thước mutation và phần overhead.
4. Đánh giá tác động của `ONE`, `LOCAL_QUORUM` và đặc biệt **write `ANY`** đối với sự thành công của request và khả năng đọc lại dữ liệu.
5. Đọc chỉ số và log liên quan, thiết kế thí nghiệm CQL/Java có kiểm soát, tránh suy đoán từ một lần `SELECT`.
6. Lập runbook cho node down ngắn, down dài vượt hint window, backlog phát lại, xóa dữ liệu và thay đổi topology.

## 1. Bối cảnh: một replica bỏ lỡ mutation

Giả sử một datacenter có các node A, B, C. Keyspace dùng `NetworkTopologyStrategy` với **RF = 3**; một partition của bảng `orders_by_id` có ba replica này.

```text
              Client Java
                  |
                  v
             Coordinator
                  |
        +---------+---------+
        |         |         |
        v         v         v
     Replica A Replica B Replica C
        UP        UP        DOWN
        |         |          X
        +-- ACK --+          |
                  |          |
           Client có thể     |
           nhận success      |
           nếu đạt CL        |
                             |
                  Hint lưu trên node
                  phối hợp phù hợp
                  (nếu đủ điều kiện)
```

Nếu client ghi `status = PAID` với `LOCAL_QUORUM`, hai replica A và B có thể xác nhận đủ quorum local trong cấu hình RF=3. C chưa nhận được mutation. Trong một số điều kiện, coordinator lưu **hint dành cho C** và sau đó chuyển cho C khi nó quay lại.

Sau khi ghi hoàn tất, các replica có thể tạm ở trạng thái:

| Replica | Trạng thái | Phiên bản dữ liệu |
| --- | --- | --- |
| A | Đã nhận mutation | `PAID` |
| B | Đã nhận mutation | `PAID` |
| C | Vắng mặt lúc ghi | `PENDING` |

**Đó là replica divergence:** cùng một partition/cell trên các replica khác nhau có thể chưa cùng trạng thái. Nó khác với tình huống ứng dụng ghi bảng `orders_by_id` nhưng bỏ quên bảng `orders_by_status_day`: trường hợp sau là **lệch giữa các projection nghiệp vụ**, không phải việc một replica chưa nhận một mutation đã gửi tới bảng đó.

### 1.1. Các khái niệm cần phân biệt

| Thuật ngữ | Vai trò |
| --- | --- |
| **Replication factor (RF)** | Số bản sao dự kiến của dữ liệu trong topology đã cấu hình |
| **Consistency level (CL)** | Số hoặc tập replica phải đáp ứng điều kiện xác nhận để thao tác báo thành công |
| **Coordinator** | Node tiếp nhận request, xác định replica và điều phối thao tác |
| **Hint** | Bản ghi mutation cần gửi lại cho một replica đang không nhận được ghi |
| **Hinted handoff** | Cơ chế lưu và phát lại những hint đủ điều kiện |
| **Hint window** | Khoảng thời gian giới hạn việc **tiếp tục tạo hint** cho một replica được coi là down |
| **Read repair** | Đối chiếu/sửa dữ liệu có liên quan khi một lần đọc phát hiện sai khác, tùy phiên bản/cấu hình |
| **Anti-entropy repair** | Quá trình so sánh và đồng bộ dữ liệu giữa các replica trên phạm vi token ranges |
| **Streaming** | Chuyển dữ liệu trong các thao tác topology/repair/rebuild thích hợp |

Không có cơ chế đơn lẻ nào bên trên cam kết **mọi replica luôn bằng nhau tại mọi thời điểm**.

## 2. Vòng đời của một hint

Một vòng đời khái niệm gồm các bước sau:

1. Coordinator tiếp nhận một mutation, xác định replica sở hữu partition.
2. Hệ thống nhận biết một replica tạm **không sẵn sàng nhận ghi** theo cơ chế failure detection/điều phối.
3. Nếu hinted handoff được bật và replica nằm trong phạm vi được phép, coordinator có thể **ghi một hint** dành cho replica đó.
4. Hint được lưu trong **kho hint cục bộ** của node đã tạo, thường được flush thành file trên ổ đĩa theo cơ chế Cassandra; chưa có nghĩa replica đích đã nhận.
5. Khi replica đích trở lại và có thể nhận, dịch vụ giao hint phát lại những mutation đã lưu, có điều tiết tốc độ/tài nguyên.
6. Sau khi được xử lý thành công theo cơ chế delivery, file/bản ghi hint liên quan có thể được thu dọn.
7. Nếu vẫn có khoảng mất mutation, cần **repair** hoặc quy trình phục hồi phù hợp.

```text
Tạo mutation
    |
    v
Replica đích có nhận được?
    | Có                         | Không
    v                            v
Ghi bình thường          Hinted handoff có bật?
                                  | Không -> không có hint
                                  | Có
                                  v
                          Trong cửa sổ cho phép?
                                  | Không -> ngừng tạo hint
                                  | Có
                                  v
                           Lưu hint tại node giữ hint
                                  |
                         Replica đích trở lại?
                                  | Chưa -> còn chờ/đánh giá giới hạn
                                  | Có
                                  v
                          Phát lại có điều tiết
                                  |
                             Xử lý thành công?
                                  | Không -> lỗi/backlog,
                                  |          cần can thiệp phù hợp
                                  | Có
                                  v
                          Theo dõi hội tụ, thu dọn hint
```

**Hint không phải dữ liệu đã xuất hiện tại replica đích.** Một file hint tồn tại trên coordinator chỉ cho thấy đã lưu công việc cần phát lại; dữ liệu trên đích có thể còn cũ cho đến khi delivery hoàn tất.

### 2.1. Hint gắn với replica đích, không phải API đọc

Hint thường mang mutation và thông tin định tuyến tới **host đích** từng bỏ lỡ ghi. Nó không phải document phục vụ truy vấn và không được đọc thông qua `SELECT` như một row trong bảng nghiệp vụ.

Khi nhiều coordinator đều xử lý ghi cho cùng replica bị down, **hint có thể phân tán trên nhiều node tạo hint**, không chỉ tập trung trong một node duy nhất. Vì thế việc theo dõi dung lượng hint cần xem **từng node** và toàn cụm.

### 2.2. Khi replica trở lại

Hệ thống cần xác định đích đã có thể nhận và gửi hint theo cơ chế giao hàng của phiên bản đang dùng. Tốc độ phát lại có thể thấp hơn tốc độ các mutation từng tích lũy, nhất là khi backlog lớn hoặc node mới phục hồi đang xử lý traffic bình thường.

Một node hiển thị `UN`/“up” trong công cụ trạng thái **không tự chứng minh backlog hint đã phát xong**. Cần quan sát số hint đang chờ, tốc độ phát, lỗi phát và xác minh dữ liệu sau đó.

### 2.3. Khi hint không được tạo

Không nên giả định mọi thao tác viết vào replica vắng mặt chắc chắn tạo hint. Các tình huống đáng kiểm:

- Hinted handoff bị tắt toàn cục hoặc không bật cho loại replica/DC liên quan theo phiên bản/cấu hình.
- Replica đã bị coi là down **quá cửa sổ tạo hint**.
- Coordinator không có đủ tài nguyên/ổ đĩa hoặc gặp lỗi khi lưu hint.
- Mutation/loại thao tác không thuộc điều kiện được ghi hint theo triển khai.
- Trạng thái thất bại của request không đảm bảo coordinator đã tạo hint, nhất là khi lỗi xảy ra trước khi có đủ thông tin để lưu.
- Thay đổi topology/host ID khiến không còn đường phát hint cũ tới đúng đích như trước.

Vì vậy, **trạng thái write timeout không đủ để kết luận “có hint” hoặc “không có hint”**. Phải kiểm tra log/metric và khả năng đọc lại theo giao thức phù hợp.

## 3. Hiểu đúng giới hạn thời gian: hint window không phải TTL của hàng

Đây là điểm dễ nhầm nhất trong chủ đề.

**Hint window** giới hạn khoảng thời gian Cassandra tiếp tục tạo/lưu **các hint mới** cho một replica đã được phát hiện down. Tham số thường được gọi là `max_hint_window` hoặc `max_hint_window_in_ms` tùy phiên bản/cấu hình. Khi node down quá khoảng cho phép, coordinator **ngừng tạo hint mới** cho replica ấy, nhằm tránh tăng backlog vô hạn.

**Không nên hiểu** đây là một cam kết rằng mọi hint được phát lại đúng trước thời điểm đó, hay sau đúng ngần ấy thời gian mọi file hint chắc chắn bị xóa. Hành vi lưu giữ và delivery của **hint đã tạo trước đó** còn phụ thuộc phiên bản, tình trạng node đích, tài nguyên và cơ chế dọn/loại bỏ hint; kiểm tra thực tế thay vì coi thời gian cấu hình là deadline delivery.

### 3.1. Ví dụ cửa sổ ba giờ

Giả sử tại lab:

```text
Hint window = 3 giờ (giả định cấu hình)

00:00  Replica C bị coi là DOWN
00:15  Mutation M1 -> đủ điều kiện tạo hint cho C
01:30  Mutation M2 -> đủ điều kiện tạo hint cho C
02:59  Mutation M3 -> còn có thể tạo hint cho C
03:10  Mutation M4 -> C vẫn DOWN, đã vượt hint window;
                     không được mặc định có hint mới cho M4
05:00  C trở lại, các hint có thể được phát lại theo
       điều kiện/version, nhưng M4 có thể cần repair
```

Mốc thực tế tính từ lúc Cassandra **phát hiện/ghi nhận replica down** theo cơ chế của phiên bản, không nhất thiết trùng hoàn toàn với giây hệ điều hành ngắt kết nối. Vì vậy các mốc 00:00–03:00 chỉ là mô hình giúp lập kế hoạch.

**Kết luận vận hành:** một node down **năm giờ** trong khi hint window **ba giờ** cần được coi là tình huống **có thể mất một phần mutation ở replica đó**, kể cả khi những hint đã lưu trước đó được phát lại đầy đủ. Phải đánh giá repair, không chỉ chờ hết backlog hint.

### 3.2. Ba khoảng thời gian độc lập

| Khoảng thời gian | Điều khiển cái gì? | Có thay thế các khoảng khác không? |
| --- | --- | --- |
| **Hint window** | Có tiếp tục tạo hint cho replica down không? | Không |
| **Thời gian thực tế để phát hết backlog** | Bao lâu delivery hoàn tất sau khi đích trở lại | Không mặc nhiên bằng hint window |
| **Retention/TTL của cell** | Dữ liệu nghiệp vụ còn sống trong bao lâu | Không; TTL tính theo ngữ nghĩa dữ liệu |
| **`gc_grace_seconds` và an toàn dọn tombstone** | Cửa sổ bảo vệ xóa, cùng repair/compaction và trạng thái replica | Không; không phải bộ đếm delivery của hint |
| **Lịch anti-entropy repair** | Mức bao phủ đồng bộ các token ranges qua thời gian | Không; cần có kế hoạch riêng |

Ví dụ nếu dữ liệu telemetry chỉ sống **bốn giờ**, hint được lưu khi replica down nhưng chỉ có thể được gửi muộn sau thời điểm dữ liệu đã hết hạn logic. Không nên kỳ vọng việc phát hint sẽ **kéo dài tuổi sống dữ liệu** để bù cho thời gian node down; việc replay phải tuân theo timestamp/TTL và ngữ nghĩa mutation thực tế.

### 3.3. Vì sao không tăng hint window lên vô hạn?

Một node vắng mặt lâu vẫn có thể có hàng nghìn mutation mỗi giây. Cứ lưu hint mãi sẽ tạo:

- Backlog lớn tiêu thụ ổ đĩa của các coordinator khác.
- I/O ghi file hint cạnh tranh với commit log, SSTable và compaction.
- Áp lực CPU/network khi node đích trở lại và được phát lại hàng triệu mutation.
- Nguy cơ hết disk ở các node **không hỏng**, khiến sự cố một node lan rộng.
- Thời gian hội tụ khó dự đoán, đặc biệt nếu tốc độ phát lại thấp hơn tốc độ ghi mới.

Giới hạn hint window là một công cụ **kiểm soát tài nguyên và phạm vi phục hồi nhanh**, chứ không phải một giới hạn tùy tiện có thể nâng mà không đánh đổi.

## 4. Consistency level và trường hợp đặc biệt của write ANY

Hinted handoff có liên quan tới đường ghi, nhưng không làm mọi consistency level có ngữ nghĩa như nhau.

### 4.1. RF=3, ONE và LOCAL_QUORUM

Với một DC có RF=3:

| Write CL | Điều kiện xác nhận cấp cao | Khi C down |
| --- | --- | --- |
| `ONE` | Một replica xác nhận | A hoặc B có thể đủ nếu hoạt động |
| `LOCAL_QUORUM` | Quorum local, với RF=3 thường là 2 | A+B có thể đủ |
| `ALL` | Cần mọi replica theo yêu cầu | Ghi có thể không đạt CL khi C down |
| `ANY` | Trường hợp write đặc biệt có thể chấp nhận một hint thay cho ACK replica khi điều kiện cho phép | Có thể báo thành công dù chưa có replica sở hữu dữ liệu ghi nhận |

**Không nhầm:** một ghi `ONE` thành công không có nghĩa coordinator chỉ gửi mutation tới một replica. Nó có thể gửi tới những replica liên quan, nhưng client chỉ phải chờ số ACK của `ONE`.

Với `LOCAL_QUORUM`, A và B có thể ACK thành công; C có thể nhận mutation sau hoặc được hỗ trợ bằng hinted handoff khi đủ điều kiện. Điều này không bảo đảm C đã đồng bộ ngay khi client thấy success.

### 4.2. Write ANY có thể thành công nhờ hint

`ANY` là **consistency level dành cho ghi**: nếu không có replica dữ liệu nào nhận được mutation, nhưng coordinator có thể lưu một hint đủ điều kiện theo cơ chế Cassandra, write vẫn có thể được xác nhận. Điều này tăng khả năng chấp nhận write trong một số tình huống outage, nhưng có hệ quả quan trọng:

```text
Client write CL=ANY
       |
Không có replica dữ liệu nhận mutation lúc đó
       |
Coordinator lưu hint được chấp nhận
       |
Client có thể nhận SUCCESS
       |
Ngay sau đó SELECT từ bảng ở CL đọc thông thường
có thể CHƯA thấy hàng vì hint chưa đến replica đích
```

Không có **read CL=ANY** tương ứng để đọc row ngay từ hint. Một hint không phải hàng dữ liệu truy vấn được. Tình huống này đặc biệt nguy hiểm nếu API cam kết read-after-write lập tức nhìn thấy dữ liệu.

**Điều kiện “có thể” là quan trọng:** nếu coordinator không thể lưu hint, node hoặc cấu hình không đáp ứng điều kiện, write `ANY` cũng có thể thất bại. Đừng quảng bá `ANY` là khả năng ghi vô điều kiện khi cluster không hoạt động.

### 4.3. Trường hợp all replicas đều không đáp ứng

Khi tất cả replica của partition đang không khả dụng:

- `ONE` hoặc `LOCAL_QUORUM` không thể nhận đủ ACK replica như yêu cầu.
- `ANY` có thể có đường thành công nhờ hint trong hoàn cảnh cụ thể.
- Một kết quả write `ANY` thành công **không cam kết** rằng một lần đọc ngay lập tức sẽ tìm thấy hàng.
- Nếu hint bị mất hoặc không được giao sau đó, kết quả nhận dữ liệu có thể không đạt yêu cầu của hệ thống nếu không có nguồn phục hồi.

Đối với dữ liệu nghiệp vụ quan trọng, chọn CL trên cơ sở SLA, topology, quy trình khôi phục, durability và mức độ chấp nhận đọc chậm, không đơn thuần vì “ANY có tính sẵn sàng cao nhất”.

## 5. Hints được lưu ở đâu và chi phí trên coordinator

Theo kiến trúc thông thường, hint được lưu trên **node Cassandra đã tạo hint**, trong thư mục/file hint cục bộ theo cấu hình. Nó không nằm trong CQL table mà application có thể trực tiếp `SELECT`.

Một số hậu quả vận hành:

1. **Một replica down có thể tạo backlog trên nhiều coordinator**, không chỉ trên một ổ đĩa.
2. Dữ liệu hint chiếm **dung lượng local** cạnh tranh với các hoạt động khác của node.
3. Khi một coordinator restart hoặc lỗi disk, trạng thái hint phải được đánh giá theo cơ chế lưu bền vững thực tế; không suy rằng mọi hint vẫn an toàn chỉ vì một mutation từng được gửi.
4. File hint được flush/phát/xóa theo cơ chế riêng; trạng thái “node đích UP” không đồng nghĩa mọi file hint đã hết.
5. Hints phụ thuộc thông tin host đích, nên thay node hoặc đổi topology cần quy trình repair/rebuild/streaming thích hợp, không chỉ sao chép file hint tùy ý.

### 5.1. Ước tính lượng hint phát sinh

Một mô hình thô:

```text
R = tốc độ mutation nhắm tới replica đang down (mutation/giây)
T = thời gian nằm trong cửa sổ còn tạo hint (giây)
S = số byte trung bình để lưu một hint, gồm mutation + overhead

hint_count ≈ R × T
hint_bytes ≈ R × T × S
```

Giả sử C down **15 phút**, có **500 mutation/giây** hướng tới C và kích thước hint trung bình **350 B** (giả định):

```text
T = 15 × 60 = 900 giây
Số hint ≈ 500 × 900 = 450.000
Byte giả định ≈ 450.000 × 350
             = 157.500.000 B = 157,5 MB
```

**157,5 MB không phải số đo trên disk thật.** Encoding, grouping/file header, compression, flush, loại mutation, coordinator phân tán và metadata khiến kết quả khác. Không được dùng “350 B mỗi hint” như hằng số cố định cho mọi schema.

### 5.2. Số lượng hint không bằng số request người dùng

Một request có thể:

- Ghi vào một hoặc nhiều partition/bảng nghiệp vụ.
- Phát sinh mutation trên nhiều replica.
- Có thể cần hint cho **nhiều replica down**.
- Bị retry do timeout, tạo thêm mutation/hint tùy tính idempotent và đường ghi.

Vì thế công thức `requests/s × duration` chỉ là gần đúng khi đã xác nhận quan hệ một request → một mutation → một replica thiếu, không phải công thức đúng cho mọi bảng.

### 5.3. Tính backlog phát lại

Nếu backlog đang có `B` byte, tốc độ phát hiệu dụng tới node đích là `D` byte/giây, và node tiếp tục nhận traffic mới:

```text
minimum_replay_time ≈ B / D
```

Đây là **cận dưới lý tưởng** chỉ khi tốc độ ổn định và không có retry, ngắt quãng hoặc cạnh tranh tài nguyên. Trên thực tế, node mới phục hồi phải xử lý cả write/read hiện tại, streaming/repair và hint replay.

Nếu tốc độ hint phát hiệu dụng chỉ ngang tốc độ backlog tiếp tục tăng, hệ thống có thể không bắt kịp. Cần tách **lượng hint đã lưu**, **lượng đang được tạo**, **lượng phát thành công** và **lượng lỗi/dropped** trong số liệu vận hành.

## 6. Cấu hình Cassandra liên quan và các giới hạn cần xác minh theo phiên bản

Cấu hình cụ thể nằm ở cấu hình node Cassandra (thường là `cassandra.yaml`), không phải tùy chọn CQL của một bảng. **Tên và đơn vị tham số có thể thay đổi theo phiên bản**; hãy đối chiếu file cấu hình và tài liệu của đúng bản Cassandra triển khai, thay vì chép một block giữa các release.

| Nhóm tùy chọn | Mục đích | Câu hỏi vận hành |
| --- | --- | --- |
| **Bật/tắt hinted handoff** | Có cho phép tạo/phát hint không? | Có thay đổi theo DC hoặc chính sách cụm? |
| **Maximum hint window** | Giới hạn thời gian tiếp tục tạo hint cho host down | Mất node quá lâu có đường repair nào? |
| **Hints directory** | Vị trí lưu file hint | Còn disk headroom? Cùng ổ với dữ liệu nào? |
| **Flush period / file size** | Cách tích lũy và ghi file hint | Có backlog I/O hoặc quá nhiều file? |
| **Delivery threads / throttle** | Giới hạn tốc độ và mức song song khi phát lại | Node mới phục hồi có bị quá tải? |
| **Compression** | Giảm dung lượng hint tùy cấu hình | CPU tăng bao nhiêu, tiết kiệm disk bao nhiêu? |
| **DC/host restrictions** | Phạm vi áp dụng hint | Có DC nào không nhận hint theo chính sách? |

### 6.1. Tên cấu hình thường gặp

Ở một số phiên bản Cassandra 4.x có thể gặp những tên như:

```yaml
# DANH MỤC TÊN THAM KHẢO, KHÔNG PHẢI BLOCK CẤU HÌNH
# DÁN NGUYÊN KHỐI ĐỂ ÁP DỤNG CHO MỌI VERSION.
hinted_handoff_enabled: true
max_hint_window_in_ms: 10800000  # Ví dụ 3 giờ ở những bản dùng đơn vị ms
hints_directory: /var/lib/cassandra/hints
max_hints_delivery_threads: 2
```

**Lưu ý quan trọng:** Một số bản Cassandra mới sử dụng tên/định dạng **duration có đơn vị** thay vì hậu tố `_in_ms`; tham số throttle, flush, max file size và giá trị mặc định cũng có thể khác. Hãy xác nhận cú pháp **ngay trên bản đang vận hành** trước khi sửa. Đường dẫn và các con số trong block trên **chỉ là ví dụ**, không phải khuyến nghị tuning.

### 6.2. Không tăng throughput bằng cách tắt hint tùy tiện

Vô hiệu hóa hinted handoff có thể làm giảm một phần công việc lúc ghi/khôi phục, nhưng cũng bỏ mất cơ chế bắt kịp nhanh cho replica đã down ngắn. Khi ấy độ lệch có thể kéo dài đến khi cơ chế khác khôi phục dữ liệu, làm tăng vai trò của repair.

Ngược lại, bật hint và kéo dài hint window quá nhiều có thể làm những node khỏe mạnh cạn disk. Quyết định cần được đánh giá với:

- Thời gian node thường down thực tế.
- Mutation rate cao nhất hướng tới một replica.
- Dung lượng hint directory và headroom.
- Tốc độ phát lại và khả năng nhận của node vừa phục hồi.
- Lịch anti-entropy repair và chính sách an toàn xóa.
- Yêu cầu sẵn sàng của API ở các consistency level đã chọn.

### 6.3. Đừng đồng nhất cấu hình theo từng node với toàn cụm

Thông số hinted handoff thường được triển khai trên các node. Nếu các node có giá trị lệch nhau vì cấu hình chưa đồng bộ, cùng một sự cố có thể tạo backlog rất khác nhau tùy coordinator nhận request.

Khi điều tra, ghi rõ **node tạo hint**, phiên bản, giá trị cấu hình và timestamp thay đổi. Không chỉ nhìn file cấu hình của replica đích: những node đang giữ hint có thể là nơi cần kiểm tra disk và delivery.

## 7. Hinted handoff, read repair, anti-entropy repair và streaming khác nhau thế nào?

| Cơ chế | Khi nào phát huy | Phạm vi | Giới hạn |
| --- | --- | --- | --- |
| **Hinted handoff** | Replica bỏ lỡ ghi trong một khoảng down ngắn, có hint đủ điều kiện | Những mutation được lưu cho đích | Best effort, giới hạn cửa sổ/tài nguyên; không thay repair |
| **Read repair** | Một read phát hiện khác biệt theo logic/cấu hình phiên bản | Dữ liệu liên quan đến read và replica tham gia | Dữ liệu không được đọc có thể vẫn lệch |
| **Anti-entropy repair** | Job chủ động kiểm tra đồng bộ các token ranges | Các replica liên quan trong phạm vi repair | Tốn network/I/O/CPU; cần lịch và theo dõi hoàn thành |
| **Streaming/rebuild** | Thêm/thay node, bootstrap, rebuild hoặc tác vụ phục hồi phù hợp | Dữ liệu/token ranges cần chuyển | Không tự giải quyết sai phiên bản nghiệp vụ |
| **Compaction** | Hợp nhất/tổ chức SSTables và xử lý tombstone trên node | Dữ liệu lưu cục bộ | Không tự đối chiếu các replica khác |

**Tình huống trọng tâm:** Node C down năm giờ, hint window ba giờ. Khi C trở lại, hinted handoff có thể phát những hint đã lưu, nhưng mutation thuộc giai đoạn vượt cửa sổ **có thể không nằm trong backlog**. Anti-entropy repair là lớp bổ sung để phát hiện/sửa dữ liệu thiếu, với lịch chạy phù hợp.

Một `SELECT` quorum có thể giúp phát hiện sai khác đối với key được đọc và trong điều kiện hỗ trợ read repair, nhưng **không đủ để kết luận mọi partition đã đúng**. Repair trên token ranges mới phù hợp cho mục tiêu bao phủ rộng hơn.

## 8. Hint replay khi có TTL, DELETE và tombstone

Hint không nên được xem như “ghi lại một lần nữa từ đầu” với logic mới tùy ý. Nó đại diện cho **mutation gốc cần chuyển tới replica đích**. Timestamp, TTL và tombstone làm cho việc phát muộn có những hậu quả quan trọng.

### 8.1. Dữ liệu có TTL

Giả sử ứng dụng ghi telemetry với TTL **một giờ**. Replica C bị down hai giờ; coordinator đã lưu hint của một số mutation.

```text
09:00  Event E được ghi với TTL = 3.600 giây
09:00  C đang down, hint E được tạo nếu đủ điều kiện
10:00  Event E đã hết hạn theo chính sách dữ liệu
11:00  C quay lại, hệ thống xem xét phát hint E
```

Không được suy rằng E sẽ sống thêm một giờ tại C chỉ vì hint được gửi lúc 11:00. TTL/metadata của mutation phải được xử lý theo ngữ nghĩa lưu trữ của Cassandra; việc một hint cũ còn được giao hay bị bỏ theo điều kiện của phiên bản **không phải cách kéo dài retention**.

Để kiểm chứng, cần kiểm tra **giá trị đọc được sau thời điểm hết hạn**, `TTL(column)` khi còn sống và log/metric delivery, thay vì chỉ nhìn file hint có biến mất hay không.

### 8.2. DELETE và nguy cơ resurrection

Kịch bản:

```text
t0   A/B/C đều chứa hàng X
t1   C down
t2   Client DELETE X; A/B lưu tombstone, C chưa nhận
t3   C down quá lâu, một phần hint có thể thiếu
t4   Tombstone ở A/B trở nên đủ điều kiện dọn theo
     cơ chế/điều kiện compaction và repair
t5   C quay lại vẫn còn dữ liệu X cũ
```

Nếu replica bỏ lỡ delete chưa được đồng bộ an toàn trước khi tombstone bị dọn, có nguy cơ **zombie/resurrection**. Việc hinted handoff bật hay không **không cho phép** bỏ qua kế hoạch repair và an toàn xóa.

**`gc_grace_seconds` không phải hint window.** Nó liên quan đến thời gian bảo vệ tombstone, nhưng còn có điều kiện khác của phiên bản, compaction và tình trạng replica. Không tự giảm `gc_grace_seconds` để giải phóng đĩa/hints nhanh hơn; điều đó có thể làm tăng nguy cơ dữ liệu bị xóa xuất hiện lại.

### 8.3. Timestamp xung đột và nghiệp vụ sai thứ tự

Giả sử:

```text
Revision 10: order = PENDING
Revision 11: order = PAID

Mutation revision 11 đến A/B/C.
Một retry revision 10 tới sau nhưng gán write timestamp lớn hơn.
```

Cassandra giải quyết xung đột cell thông thường theo timestamp ghi và quy tắc xử lý tombstone. Nếu revision 10 có timestamp lớn hơn, các replica cuối cùng **có thể cùng hội tụ về PENDING sai nghiệp vụ**.

Hinted handoff không tự so sánh `revision` nghiệp vụ để giữ “phiên bản đúng”. Cần thiết kế nguồn chấp nhận transition, ordering/dedupe hoặc LWT/CAS phù hợp ở phạm vi có điều kiện. **Replica hội tụ không đồng nghĩa business state đúng.**

### 8.4. Collection, counter và retry

Một mutation có thể được phát lại trong tình huống lỗi không có nghĩa mọi thao tác ứng dụng đều idempotent. Đặc biệt:

- Ghi cùng row key với giá trị xác định thường dễ thiết kế retry hơn tạo event ID mới.
- Thao tác collection phụ thuộc loại và dạng cập nhật, có thể có chi phí/đặc tính idempotency riêng.
- Counter có ngữ nghĩa khác regular column; retry mù sau timeout có thể làm số đếm sai.
- Ghi lại với TTL mới có thể làm thay đổi thời hạn sống của giá trị; chính sách retention phải được giữ nhất quán.

Hinted handoff **không phải hệ thống deduplication nghiệp vụ** cho các request bị gửi nhiều lần.

## 9. Multi-datacenter: một hint không phải lời hứa dữ liệu ở mọi vùng đã mới

Với `NetworkTopologyStrategy`, các DC có thể có RF khác nhau. Ví dụ:

```sql
CREATE KEYSPACE replica_hint_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_primary': 3,
    'dc_backup': 2
};
```

Đây chỉ là cấu hình minh họa; tên DC phải khớp topology thật, và mỗi DC phải có đủ node để đáp ứng RF.

Nếu client ghi `LOCAL_QUORUM` tại `dc_primary`, success dựa trên quorum tại **DC local của coordinator**, không phải cam kết tất cả replica `dc_backup` đã nhận mutation. Trong thời gian network cross-DC kém hoặc replica remote chậm, một read `LOCAL_ONE` tại backup DC có thể vẫn nhìn dữ liệu cũ.

Đừng kết luận “hinted handoff sẽ bảo đảm mọi DC luôn đồng bộ ngay”:

- Những replica có thể đủ điều kiện nhận hint theo cấu hình/phiên bản, hoặc có hạn chế cho cross-DC.
- Việc ghi local thành công không tạo tính đồng bộ tức thời ở remote DC.
- Quá trình phục hồi diện rộng có thể cần anti-entropy repair/streaming ngoài hinted handoff.
- Khi ứng dụng cần read-after-write xuyên DC, phải thiết kế **hợp đồng nhất quán và định tuyến DC** rõ ràng, không dựa vào một danh sách hint đang chờ.

## 10. Thí nghiệm CQL: quan sát trường hợp mất replica

**Chỉ thực hiện trên cluster lab** đã được phép mô phỏng node down. Tắt node/mạng để kiểm thử trên production mà không có kế hoạch có thể làm gián đoạn dịch vụ hoặc gây mất dữ liệu.

### 10.1. Chuẩn bị keyspace RF=3 và bảng

Giả sử cluster lab có một DC tên `dc1`, ít nhất ba node. Cấu hình ví dụ:

```sql
CREATE KEYSPACE replica_hint_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE replica_hint_lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    status text,
    revision bigint,
    changed_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Hai ví dụ `CREATE KEYSPACE replica_hint_lab` ở các phần trước dùng **topology giả định khác nhau**; chỉ chọn **một** cấu hình phù hợp lab thực tế. Không dán liên tiếp cả hai vào cùng cluster vì keyspace cùng tên sẽ báo đã tồn tại. Nếu lab chỉ có một DC, dùng ví dụ `dc1` ở phần này.

### 10.2. Seed một hàng với CL rõ ràng

Trong `cqlsh`, `CONSISTENCY` là **lệnh của shell**, không phải cú pháp chèn vào prepared statement Java.

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO replica_hint_lab.orders_by_id (
    tenant_id, order_id, status, revision, changed_at
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    'PENDING',
    1,
    '2026-11-21T09:00:00Z'
);

SELECT status, revision, WRITETIME(status) AS status_write_time
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;
```

Đảm bảo các replica ban đầu ổn định và lưu lại kết quả. `WRITETIME(status)` biểu diễn timestamp ghi của **cell status**, không phải `changed_at` nghiệp vụ.

### 10.3. Mô phỏng một replica down ngắn

Quy trình có kiểm soát:

1. Xác định **tập replica thật** của partition thí nghiệm bằng công cụ phù hợp với phiên bản và topology; đừng chọn ngẫu nhiên một node.
2. Lưu cấu hình hint window, CL, RF, trạng thái cluster, dung lượng thư mục hint và metric baseline.
3. Trong lab, làm một replica của partition **tạm thời không đáp ứng** đủ lâu để failure detection ghi nhận, nhưng **ngắn hơn cửa sổ hint** giả định.
4. Ghi một phiên bản mới với `LOCAL_QUORUM` khi hai replica còn lại vẫn hoạt động.
5. Kiểm tra client success, sự kiện ghi hint bằng log/metric nếu có, và kết quả `SELECT` ở các thời điểm phù hợp.
6. Cho node trở lại, quan sát backlog hint và delivery, kiểm chứng dữ liệu sau khi hệ ổn định.
7. Ghi lại thời gian tạo hint, thời gian node up và thời gian backlog phát xong; so với giá trị cấu hình.

CQL cập nhật:

```sql
CONSISTENCY LOCAL_QUORUM;

UPDATE replica_hint_lab.orders_by_id
SET status = 'PAID',
    revision = 2,
    changed_at = '2026-11-21T10:00:00Z'
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;

CONSISTENCY ONE;

SELECT status, revision
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;

CONSISTENCY LOCAL_QUORUM;

SELECT status, revision
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000001;
```

**Không kỳ vọng `ONE` nhất định thấy PENDING**: coordinator có thể chọn một replica đã nhận write hoặc node down không được chọn để trả dữ liệu. Cũng không chứng minh C đã hội tụ chỉ vì `LOCAL_QUORUM` trả `PAID`. Muốn chứng minh hinted handoff đã chạy, phải có **bằng chứng từ metric/log và kiểm tra trạng thái replica**, không suy từ một `SELECT`.

### 10.4. Thử vượt hint window

Trong một kịch bản lab tách biệt, giữ replica down lâu hơn cửa sổ cấu hình và tiếp tục ghi **một số mutation có ID ổn định** trong cả giai đoạn trước/sau cửa sổ.

Mục tiêu kiểm thử:

- Các mutation trước hạn có thể đã tạo hint.
- Những mutation sau khi vượt cửa sổ **không được mặc định** có hint.
- Khi node up, backlog có thể phát xong mà vẫn còn dữ liệu replica thiếu ở một số token ranges.
- Quy trình repair được thử đúng phạm vi có thể phát hiện/sửa sai khác.

Thí nghiệm có thể tốn thời gian và tài nguyên nếu dùng cửa sổ mặc định nhiều giờ. Trong lab có thể cấu hình theo quy trình thử nghiệm của phiên bản, nhưng **không nên đổi cấu hình production chỉ để thử cho nhanh**.

### 10.5. Thử write ANY riêng

Đối với `ANY`, thí nghiệm chỉ nên thực hiện nếu lab có đủ node để coordinator vẫn tiếp nhận request trong khi replica của partition không sẵn sàng, và hệ thống đã được cấu hình/được phép dùng điều kiện hint tương ứng.

```sql
-- Chỉ thử trong lab và ghi lại topology/khả năng tạo hint.
CONSISTENCY ANY;

INSERT INTO replica_hint_lab.orders_by_id (
    tenant_id, order_id, status, revision, changed_at
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000002,
    'PENDING',
    1,
    '2026-11-21T10:05:00Z'
);

-- ANY không phải mức consistency đọc; đổi sang CL đọc hợp lệ.
CONSISTENCY ONE;

SELECT status, revision
FROM replica_hint_lab.orders_by_id
WHERE tenant_id = 'tenant-A'
  AND order_id = 00000000-0000-4000-8000-000000000002;
```

Nếu write thành công chỉ nhờ hint, đọc sau đó có thể chưa thấy hàng. **Không có kết quả bắt buộc** khi lab không được cấu hình để tất cả replica dữ liệu thật sự không khả dụng: write cũng có thể đã đến replica, hoặc request có thể lỗi vì không lưu được hint.

## 11. Java Driver 4.x: ghi với CL rõ ràng, nhận diện unknown outcome

Ví dụ Java dùng **DataStax Java Driver 4.x** và `CqlSession` được quản lý theo vòng đời ứng dụng. Mục tiêu là minh họa **mức consistency của statement** và cách không kết luận sai từ timeout. Nó không phải thư viện tự sửa dữ liệu.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class HintedHandoffLabRepository {
    private final CqlSession session;
    private final PreparedStatement upsert;
    private final PreparedStatement read;

    public HintedHandoffLabRepository(CqlSession session) {
        this.session = session;
        this.upsert = session.prepare(
            "INSERT INTO replica_hint_lab.orders_by_id " +
            "(tenant_id, order_id, status, revision, changed_at) " +
            "VALUES (?, ?, ?, ?, ?)"
        );
        this.read = session.prepare(
            "SELECT status, revision, changed_at, " +
            "WRITETIME(status) AS status_write_time " +
            "FROM replica_hint_lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public void writeQuorum(
        String tenantId, UUID orderId,
        String status, long revision, Instant changedAt
    ) {
        try {
            session.execute(
                upsert.bind(tenantId, orderId, status, revision, changedAt)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM
                    )
            );
        } catch (WriteTimeoutException | WriteFailureException ex) {
            // Kết quả của mutation là chưa rõ ở từng replica.
            // Không tự cấp một event_id/revision mới rồi retry vô hạn.
            // Ghi nhận context và đưa sang quy trình readback/retry an toàn.
            throw new IllegalStateException(
                "Write outcome requires verification", ex
            );
        }
    }

    public Row readOne(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
        ).one();
    }

    public Row readLocalQuorum(String tenantId, UUID orderId) {
        return session.execute(
            read.bind(tenantId, orderId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM
                )
        ).one();
    }
}
```

Lưu ý vận hành:

- Các exception khác (client timeout, unavailable, connection error) cũng có thể xảy ra và cần phân loại theo contract của service; ví dụ chỉ minh họa hai lỗi server-side phổ biến.
- `WriteTimeoutException` không chứng minh mutation **chưa** được một replica nào áp dụng. Ngược lại, write thành công ở CL cũng không chứng minh **mọi replica** đã nhận.
- Giữ cùng `tenant_id`/`order_id` và revision khi retry **nếu nghiệp vụ cho phép**, nhưng không cho một revision cũ ghi lùi trạng thái mới đã được chấp nhận.
- Java driver **không cung cấp một API để client SELECT trực tiếp file hint** trên coordinator. Muốn kiểm tra cơ chế hinted handoff phải dùng metric/log vận hành.
- `Row` có thể là `null` khi partition chưa có dữ liệu đọc được ở CL đã chọn. Không tự kết luận một `null` duy nhất là “database đã mất dữ liệu”.
- Đừng dùng `LOCAL_QUORUM` như một công tắc sửa lỗi của các bảng projection khác nhau; đó là vấn đề đồng bộ mutation nghiệp vụ.

### 11.1. Vì sao không tự động retry mọi write?

Một timeout ở đường ghi có thể xảy ra **sau khi mutation đã đến một phần replica**, thậm chí trước lúc client nhận ACK. Retry cùng primary key và cùng giá trị thường dễ kiểm soát hơn retry sinh ID mới, nhưng vẫn phải xét write timestamp, TTL, counter và thứ tự nghiệp vụ.

Ví dụ:

```text
Request #1: revision 10 -> PENDING, timeout nhưng một số replica đã ghi
Request #2: revision 11 -> PAID, thành công
Retry #1:  revision 10 -> PENDING với timestamp ghi mới

Nếu retry không kiểm tra version, các replica có thể cùng hội tụ
về PENDING sai dù hinted handoff/repair hoạt động đúng.
```

Hệ thống cần **idempotency key**, nguồn xác nhận revision, thứ tự per entity hoặc LWT/CAS phù hợp. Hinted handoff là cơ chế dưới tầng ứng dụng, không phải bộ tuần tự hóa transition nghiệp vụ.

## 12. Quan sát hint backlog và trạng thái khôi phục

Không thể đánh giá hinted handoff chỉ bằng “node đã up”. Hãy theo dõi các nhóm tín hiệu:

| Nhóm | Quan sát cần có | Rủi ro được phát hiện |
| --- | --- | --- |
| Số lượng hint | Hints created/pending/delivered/dropped/failed theo phạm vi công cụ hỗ trợ | Backlog không giảm, hint không được tạo hoặc bị loại |
| Disk | Dung lượng hints directory trên từng node tạo hint, tốc độ tăng | Hết disk trên coordinator khỏe |
| Delivery | Tốc độ phát hiệu dụng, số lần thử lại, thời gian còn tồn | Replica trở lại nhưng không bắt kịp |
| Replica state | Node UP/DOWN, host ID, topology/DC, streaming | Node/đích có thực sự sẵn sàng? |
| Read/write | Latency p95/p99, timeout, CL, số ACK | Node hồi phục gây quá tải hoặc đọc còn cũ |
| Repair | Lịch, phạm vi token ranges, job hoàn thành/lỗi | Hints không đủ cho outage dài |
| Tombstone/TTL | Delete chưa đến replica, tuổi dữ liệu, compaction | Nguy cơ resurrection/hết retention |
| App invariant | Version đúng, mapping bảng phụ hội tụ | Phân biệt replica lag với projection lag |

Tên metric/JMX/table trong dashboard tùy Cassandra version và stack giám sát. Không nên viết cảnh báo phụ thuộc một metric **không có trong cụm**. Dùng tên chính xác từ hệ đang chạy và ghi phạm vi: **per host**, **per DC** hoặc **per keyspace**.

### 12.1. Công cụ vận hành tham khảo

Các thao tác kiểm tra thường dùng:

```text
nodetool status
nodetool tpstats
nodetool netstats
nodetool compactionstats
```

Khi phiên bản hỗ trợ, có thể có những thao tác riêng cho hinted handoff như liệt kê hint đang chờ, tạm dừng/tiếp tục delivery hoặc xóa hint. **Không suy đoán lệnh có sẵn trên mọi version** và tuyệt đối không xóa/truncate hint chỉ để hết cảnh báo khi chưa có phương án repair/khôi phục.

Vì hinted handoff có thư mục lưu riêng, nên theo dõi trực tiếp dung lượng trên ổ phù hợp với chính sách quyền truy cập, đồng thời dùng metric/log của Cassandra. Không dùng `SELECT COUNT(*)` trên bảng nghiệp vụ như một cách “đếm hint”.

### 12.2. Ngưỡng cảnh báo nên thiết kế thế nào?

Không có một ngưỡng MB/hint window phổ quát. Nên đặt cảnh báo từ:

1. **Tốc độ tăng backlog** khi replica down.
2. **Dung lượng còn trống của node tạo hint**, cùng nhu cầu compaction và các thành phần khác.
3. **Tuổi hint lớn nhất** hoặc thời gian replica down so với cửa sổ đã cấu hình.
4. **Tỷ lệ phát lại** sau khi replica trở lại và mức chậm cải thiện.
5. **Lịch repair** trước khi tombstone mất khả năng bảo vệ delete.
6. **Tác động tới request người dùng**: timeout/p99/khả năng đáp ứng CL.

Những mức cụ thể như “alert khi hints directory chiếm 10 GB” chỉ hợp lý nếu đã đo schema, throughput, topology và disk headroom của cluster đó. Không áp trực tiếp cho mọi hệ Cassandra.

## 13. Runbook: node down ngắn, down dài và replay bị nghẽn

### 13.1. Trước khi tác động lên cluster

Ghi lại:

```text
Cluster/version:
DC/RF:
Time node was considered DOWN:
max hint window and config version:
Current node status:
Coordinator nodes holding hints:
Disk usage on those nodes:
Pending/delivery/failed hints:
Current read/write CL and timeouts:
Repair history and coverage:
TTL/delete policy and gc_grace:
Business source/replay options:
```

Nếu thiếu bằng chứng về node nào chứa hint hoặc replica nào sở hữu key, không vội “sửa” bằng cách thay timestamp, truncate bảng hoặc chuyển mọi read sang `ALL`.

### 13.2. Kịch bản A — outage ngắn hơn hint window

1. Xác định replica đã bị coi là down vào lúc nào.
2. Kiểm tra hinted handoff bật và các coordinator có đủ disk/resources.
3. Kiểm tra ghi/đọc còn đáp ứng CL đã chốt; không tự hạ CL để giấu lỗi nếu SLA không cho phép.
4. Phục hồi node theo quy trình hệ thống.
5. Quan sát tốc độ phát hint, lỗi delivery và áp lực lên node vừa trở lại.
6. Sau khi backlog ổn định, kiểm tra mẫu partition/row có ghi trong outage.
7. Vẫn tiếp tục lịch repair bình thường; hinted handoff không xóa nhu cầu anti-entropy repair.

Đừng hứa “node up là mọi hint đã phát xong”. Cần bằng chứng từ metric/log.

### 13.3. Kịch bản B — outage vượt hint window

1. Xem outage đã vượt cửa sổ bao lâu và những mutation nào có thể **không có hint**.
2. Phục hồi node và theo dõi những hint còn khả năng phát lại.
3. **Lập repair theo quy trình của phiên bản/topology**, đủ bao phủ những token ranges cần đồng bộ.
4. Kiểm tra an toàn tombstone/`gc_grace_seconds` và dữ liệu đã xóa; không tự ép compaction.
5. Nếu node cần replace/rebuild, lập kế hoạch streaming và kiểm tra đủ dung lượng/tài nguyên.
6. Kiểm chứng dữ liệu sau khôi phục, bao gồm các mutation trong phần **vượt cửa sổ**.

**Không đánh dấu hoàn thành chỉ vì hint backlog bằng 0.** Backlog bằng 0 có thể vì không tạo hint sau một mốc; điều đó **không chứng minh dữ liệu của replica đã đủ**.

### 13.4. Kịch bản C — node UP nhưng backlog không giảm

Các hướng điều tra:

- Host ID/topology/target có còn phù hợp không?
- Node đích có đủ CPU, disk, network và không đang nghẽn compaction/streaming?
- Có lỗi delivery, lỗi kết nối, throttle thấp hoặc quá nhiều request thường xuyên?
- Coordinator giữ hint có thiếu disk/I/O hoặc đang backlog rất lớn?
- Hint files có bị lỗi/hết điều kiện phát theo cơ chế phiên bản?
- Có cần chuyển sang repair/rebuild khi hints không thể đảm bảo hội tụ?

Chỉ tăng thread/throttle sau khi biết nút nghẽn. Nâng delivery quá mạnh có thể **làm quá tải node vừa hồi phục**, khiến tình hình tệ hơn.

### 13.5. Kịch bản D — dữ liệu đã xóa xuất hiện lại

Ưu tiên bảo toàn chứng cứ:

1. Ghi đầy đủ keyspace/table/partition/clustering key và giá trị quan sát.
2. Thu thời điểm xóa/TTL, `WRITETIME` khi còn có giá trị, node offline và lịch repair.
3. Kiểm tra tombstone/grace, compaction và phạm vi replica bỏ lỡ delete.
4. Không giảm grace hoặc ép dọn SSTable khi chưa hiểu khả năng resurrection.
5. Phục hồi theo runbook tương ứng với Cassandra version, có xác minh an toàn dữ liệu.

Đừng gán mọi dữ liệu “xuất hiện lại” cho hint; đôi khi nguyên nhân là producer replay event cũ với timestamp mới hoặc một bảng projection chưa xóa. Hai lớp lỗi đó cần quy trình riêng.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách hiểu/giải quyết |
| --- | --- | --- |
| “RF=3 thì không cần hint/repair” | Replica bỏ lỡ mutation có thể giữ dữ liệu cũ | RF là số bản sao, không phải cam kết đồng bộ tức thời |
| “Ghi ONE chỉ gửi tới một replica” | Hiểu sai đường ghi | ONE là số ACK cần chờ, không giới hạn coordinator gửi |
| “Hint window 3h = mọi hint được phát xong sau 3h” | Sai SLO phục hồi | Window giới hạn việc tạo hint cho host down, không phải deadline delivery |
| “Node UP = dữ liệu chắc chắn đồng nhất” | Backlog còn hoặc có mutation quá cửa sổ | Quan sát delivery và repair |
| “Cứ tăng window lên 7 ngày” | Hints có thể chiếm hết disk và phục hồi quá chậm | Tính R×T×S, giới hạn và repair |
| “Hints bảo đảm không mất mutation trong mọi lỗi” | Best effort bị hiểu thành giao dịch bền vững tuyệt đối | Có nguồn phục hồi, repair và monitoring |
| “ANY success = read sau đó chắc chắn thấy row” | Read có thể chưa thấy vì chỉ có hint | ANY là write CL, không phải read CL |
| “Đọc LOCAL_QUORUM sẽ luôn chữa node down” | Quorum không đòi mọi replica đã nhận mutation | Hints/repair và giám sát riêng |
| “Hinted handoff thay anti-entropy repair” | Outage dài vẫn thiếu dữ liệu | Repair token ranges theo kế hoạch |
| “Hint window là TTL của dữ liệu” | Đưa ra kỳ vọng retention sai | Phân biệt mutation TTL, window, grace |
| “Giảm gc_grace_seconds để dọn hint” | Không tác động đúng mục tiêu, tăng rủi ro dữ liệu xóa xuất hiện lại | Quản lý hints, tombstone và repair riêng |
| “Hint từ source tự sửa bảng projection khác” | Mutation nghiệp vụ chưa phát sẽ không được tạo | Durable event, retry, reconciliation nghiệp vụ |
| “Retry timeout luôn an toàn” | Sinh ID trùng, timestamp ghi lùi trạng thái | Idempotency/ordering và readback |
| “Backlog = 0 nghĩa là đủ dữ liệu” | Hints có thể chưa từng tạo sau window | Kiểm tra repair và nguồn dữ liệu |
| “Tăng throttle luôn giúp nhanh hơn” | Node mới trở lại bị bão I/O/network | Tuning theo bottleneck và đo thật |

## 15. Bài tập thực hành

Một cụm lab một DC, **RF=3**, lưu trạng thái đơn tại bảng `orders_by_id`. Ba replica A/B/C ban đầu cùng có `status=PENDING`, revision 7. C bị coi là down lúc 09:00. Cụm đặt **hint window = 2 giờ** cho tình huống minh họa. Trong thời gian down, các coordinator nhận trung bình **300 mutation/giây** nhắm tới C; giả định mỗi hint chiếm **400 B trên disk** (chỉ để làm phép tính).

Timeline:

```text
09:00  C được coi là DOWN
09:10  Ghi revision 8, status=PAID tại CL=LOCAL_QUORUM
10:30  Ghi revision 9, status=SHIPPED tại CL=LOCAL_QUORUM
11:20  Ghi revision 10, status=DELIVERED tại CL=LOCAL_QUORUM
12:00  C trở lại
```

**Yêu cầu:**

1. Với RF=3 tại một DC, `LOCAL_QUORUM` cần tối thiểu bao nhiêu ACK? Vì sao write ở 09:10 có thể thành công khi C down?
2. Hai mutation lúc 09:10 và 10:30 có thể được tạo hint không? Còn mutation 11:20 sau khi C đã down hơn hai giờ thì sao?
3. Ước tính **số hint và byte** có thể được tạo trong **hai giờ còn tạo hint**, giả định R/S giữ nguyên và mọi mutation đều đủ điều kiện. Nêu ít nhất ba yếu tố khiến disk thực tế khác phép tính.
4. C trở lại lúc 12:00: có được kết luận đến 12:01 tất cả revision đều tồn tại trên C không? Nếu không, cần đo gì?
5. Backlog hint phát hết nhưng C vẫn chưa có revision 10. Cơ chế nào thích hợp để kiểm tra/sửa phần không được hint bao phủ?
6. Nếu một `DELETE` ở 11:20 cũng bị C bỏ lỡ và tombstone được dọn trước khi dữ liệu cũ tại C được đồng bộ, rủi ro gì xuất hiện? Vai trò của `gc_grace_seconds` và repair?
7. Giả sử client ghi `ANY` và chỉ hint được lưu: ngay sau đó đọc `ONE` có thể thấy gì? Vì sao không có `READ ANY`?
8. Trong Java Driver 4.x, viết một prepared statement cập nhật status với `LOCAL_QUORUM` và một readback `ONE`; mô tả cách xử lý timeout mà không làm revision 8 ghi lùi sau revision 10.
9. Nếu bảng `orders_by_id` đã ở revision 10 nhưng bảng `orders_by_status_day` còn trạng thái revision 8, hinted handoff có tự sửa hai bảng khác nhau không? Cần cơ chế gì?

**Gợi ý đối chiếu:**

```text
RF=3 -> LOCAL_QUORUM = floor(3/2)+1 = 2 replica ACK.

Hint window = 2 giờ:
  09:10 và 10:30 nằm trong cửa sổ giả định.
  11:20 đã vượt cửa sổ; không được mặc định có hint mới.

Số hint ≈ 300 mutation/s × (2 × 3.600 s)
        = 2.160.000 hint

Disk giả định ≈ 2.160.000 × 400 B
              = 864.000.000 B = 864 MB thập phân.
```

Những con số này **không bao gồm** compression, metadata/file, biến động mutation, phân phối coordinator, lỗi ghi hint và các loại mutation không đủ điều kiện. Sau 12:00, cần quan sát delivery thực tế và lên lịch **repair** vì có mutation sau hint window. `ANY` là mức ghi có thể được xác nhận chỉ nhờ hint; một read từ replica không có dữ liệu vẫn có thể không thấy row. Sai khác giữa các projection phải giải bằng **nguồn thay đổi bền vững, retry/idempotency và reconciliation ở tầng ứng dụng**, không chỉ hinted handoff.

## Kết luận

**Hinted handoff giúp một replica tạm vắng bắt kịp những mutation đã được lưu dưới dạng hint**, nhưng nó có ranh giới rõ ràng: **chỉ những hint được tạo trong điều kiện và cửa sổ cho phép mới có cơ hội được phát lại**, còn delivery phụ thuộc node đích, tài nguyên và tình trạng cụm. Hint window không phải TTL dữ liệu, không phải deadline phát hết backlog và không thể thay thế repair. Khi node down dài, backlog lớn, tombstone sắp mất tác dụng bảo vệ hoặc thay đổi topology, cần **anti-entropy repair/streaming cùng runbook được kiểm chứng**. Khi thao tác ứng dụng bị timeout, hãy giữ khóa/phiên bản ổn định, tránh retry ghi lùi và phân biệt **replica divergence** với **projection consistency**. Sự tin cậy của Cassandra đến từ việc kết hợp RF, CL, hints, repair, quan sát vận hành và kiểm soát nghiệp vụ — không đến từ một tham số đơn lẻ.
