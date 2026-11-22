# Cluster health, shard allocation và ngưỡng dung lượng đĩa

Một cluster Elasticsearch có thể vẫn phản hồi request nhưng không ở trạng thái vận hành tốt. Ví dụ, cluster có thể ở trạng thái yellow vì replica chưa được phân bổ; một số shard có thể unassigned do thiếu node hoặc allocation rule; disk gần đầy có thể khiến Elasticsearch từ chối phân bổ shard mới và cuối cùng đặt index vào chế độ read-only. Nếu chỉ kiểm tra endpoint có trả HTTP 200 hay không, ứng dụng sẽ bỏ lỡ những dấu hiệu quan trọng trước khi sự cố ảnh hưởng tới người dùng.

Cluster health, shard allocation và disk watermark là ba phần liên quan chặt chẽ. Cluster health cho biết trạng thái tổng quát của shard; allocation giải thích shard copy đang nằm ở đâu hoặc vì sao chưa được gán; disk watermark đặt các ngưỡng bảo vệ để Elasticsearch tránh làm đầy ổ đĩa. Bài học này trình bày cách đọc các trạng thái, chẩn đoán nguyên nhân, theo dõi từ Spring Boot và xử lý an toàn khi cluster thiếu tài nguyên.

## 1. Cluster health biểu thị điều gì?

Elasticsearch cung cấp Cluster Health API để báo trạng thái của cluster hoặc một index. Trạng thái dựa trên việc primary shard và replica shard có được phân bổ hay không.

Có ba trạng thái chính:

| Trạng thái | Ý nghĩa | Tác động thường gặp |
|---|---|---|
| green | Tất cả primary và replica shard được phân bổ | Cluster có đầy đủ shard copies theo cấu hình hiện tại |
| yellow | Tất cả primary shard được phân bổ, nhưng ít nhất một replica chưa được phân bổ | Dữ liệu chính vẫn có thể phục vụ, nhưng mức dự phòng giảm |
| red | Ít nhất một primary shard chưa được phân bổ | Một phần dữ liệu của index có thể không đọc/ghi được bình thường |

### Green

Green cho biết mọi primary và replica shard được cấu hình đều đang active. Đây là trạng thái đầy đủ về mặt allocation, nhưng không bảo đảm mọi truy vấn đều nhanh hoặc mọi node đều khỏe mạnh. Một cluster green vẫn có thể có hot shard, CPU cao, search latency tăng, thread pool queue lớn hoặc disk sắp chạm watermark.

Vì vậy, green là một tín hiệu quan trọng chứ không phải chứng nhận rằng mọi workload đều hoạt động tốt.

### Yellow

Yellow có nghĩa primary shard đã được phân bổ, còn ít nhất một replica shard chưa được gán. Thao tác đọc/ghi vẫn có thể hoạt động trên primary shard tương ứng, nhưng cluster có ít bản sao hơn cấu hình mong muốn.

Nguyên nhân phổ biến:

- Cluster chỉ có một node nhưng index đặt replica count lớn hơn 0.
- Không đủ node phù hợp để đặt replica.
- Allocation awareness yêu cầu replica ở zone khác nhưng zone đó chưa có node.
- Disk watermark hoặc allocation filter ngăn shard copy được gán.
- Replica đang trong quá trình recovery hoặc relocation.

Trong môi trường development một node, yellow có thể là trạng thái dự kiến. Trong production, yellow kéo dài cần được điều tra vì khả năng chịu lỗi đã giảm.

### Red

Red có nghĩa ít nhất một primary shard chưa được phân bổ. Một phần dữ liệu của index tương ứng có thể không khả dụng. Một số request có thể vẫn thành công nếu chúng chỉ truy cập shard đang active, nhưng không nên xem cluster red là trạng thái chấp nhận được cho hệ thống production thông thường.

Nguyên nhân có thể gồm:

- Node chứa primary shard bị mất và không có replica có thể promote.
- Shard copy bị lỗi hoặc dữ liệu shard không thể khôi phục.
- Disk hoặc allocation rule khiến shard không thể được phân bổ.
- Index bị đóng hoặc có vấn đề về metadata.
- Cluster vừa trải qua sự cố node hoặc storage.

Cluster red cần được xử lý theo từng shard và từng index. Không nên xóa index hoặc ép allocate shard một cách tùy tiện để làm màu trạng thái chuyển sang green.

## 2. Gọi Cluster Health API

Kiểm tra toàn cluster:

~~~http
GET /_cluster/health
~~~

Kiểm tra một index:

~~~http
GET /_cluster/health/orders?level=indices
~~~

Kết quả có thể chứa các trường:

~~~json
{
  "cluster_name": "search-cluster",
  "status": "yellow",
  "number_of_nodes": 3,
  "number_of_data_nodes": 3,
  "active_primary_shards": 12,
  "active_shards": 20,
  "relocating_shards": 0,
  "initializing_shards": 0,
  "unassigned_shards": 4,
  "delayed_unassigned_shards": 0,
  "number_of_pending_tasks": 0,
  "task_max_waiting_in_queue_millis": 0,
  "active_shards_percent_as_number": 83.3
}
~~~

Đây là ví dụ minh họa, không phải số liệu từ một cluster cụ thể. Cấu trúc response có thể bổ sung trường theo phiên bản Elasticsearch.

Các trường đáng chú ý:

- status: green, yellow hoặc red.
- number_of_nodes: tổng số node trong cluster.
- number_of_data_nodes: số node có role data.
- active_primary_shards: số primary shard đang active.
- active_shards: tổng số shard copies đang active.
- relocating_shards: số shard đang di chuyển giữa các node.
- initializing_shards: số shard đang khởi tạo/recover.
- unassigned_shards: số shard chưa được phân bổ.
- number_of_pending_tasks: số cluster state task đang chờ.
- task_max_waiting_in_queue_millis: thời gian chờ lớn nhất của task trong queue.

### Chọn level phù hợp

- level=cluster: trạng thái tổng thể.
- level=indices: thêm chi tiết theo index.
- level=shards: thêm chi tiết theo shard.

Không cần gọi level=shards liên tục trong mọi health probe nếu cluster có rất nhiều shard. Dữ liệu chi tiết hữu ích khi điều tra, nhưng request nặng hơn và response lớn hơn.

### Timeout và wait_for_status

Health API hỗ trợ các tùy chọn chờ trạng thái hoặc điều kiện shard nhất định. Ví dụ:

~~~http
GET /_cluster/health/orders?wait_for_status=yellow&timeout=5s
~~~

Request có thể chờ cluster đạt trạng thái ít nhất yellow hoặc hết timeout. Đây là cách hữu ích trong provisioning/test, nhưng không nên đặt timeout dài cho health probe được gọi liên tục.

Không dùng wait_for_status=green để làm cho một ứng dụng chỉ khởi động khi mọi replica đã active nếu môi trường development một node vốn được thiết kế yellow. Điều kiện readiness cần phù hợp với topology thực tế.

## 3. Health của cluster khác health của ứng dụng

Cluster health phản ánh allocation shard ở Elasticsearch. Nó không trực tiếp đo:

- Thời gian phản hồi API của ứng dụng.
- Tỷ lệ lỗi của repository method.
- Mapping có đúng với dữ liệu nghiệp vụ không.
- Query có sử dụng filter/sort hiệu quả không.
- Disk latency, CPU saturation hoặc GC pause ở mức chi tiết.
- Service account có đủ quyền trên index mà ứng dụng dùng không.

Một ứng dụng có thể trả lỗi dù cluster green vì credential sai, alias không tồn tại hoặc index bị block ghi. Ngược lại, cluster yellow có thể vẫn đáp ứng đầy đủ các request cần primary shard nếu replica unassigned không ảnh hưởng đường truy cập đó.

Nên kết hợp cluster health với các metric allocation, disk, node, thread pool, indexing/search latency và error rate ở tầng ứng dụng.

## 4. Shard allocation là gì?

Allocation là quá trình Elasticsearch quyết định shard copy nào được đặt trên node nào. Một primary shard và các replica của nó là những shard copy thuộc cùng shard group.

Ví dụ index có hai primary và một replica:

~~~text
Shard group 0:
  Primary 0 -> Node A
  Replica 0 -> Node B

Shard group 1:
  Primary 1 -> Node B
  Replica 1 -> Node C
~~~

Elasticsearch phải tuân thủ các ràng buộc như:

- Không đặt hai bản sao của cùng shard group trên cùng một node.
- Node phải có role phù hợp để chứa shard.
- Disk phải đáp ứng allocation policy.
- Allocation awareness và filtering phải được thỏa mãn.
- Cluster phải còn shard capacity theo giới hạn cấu hình.
- Node và shard phải ở trạng thái cho phép recovery/relocation.

Allocation không chỉ là phép chia đều số lượng shard. Elasticsearch còn cân nhắc dung lượng, node attributes, disk watermark và các quy tắc vận hành.

### Shard unassigned

Một shard unassigned là shard copy chưa được đặt trên node nào. Với replica unassigned, cluster thường yellow nếu mọi primary vẫn active. Với primary unassigned, cluster red.

Unassigned không nhất thiết có nghĩa dữ liệu đã mất. Có thể cluster chưa có node phù hợp hoặc đang chờ một điều kiện allocation. Cần xem allocation explanation để xác định nguyên nhân.

### Initializing và relocating

- INITIALIZING: shard đang được khởi tạo hoặc recover trên node đích.
- RELOCATING: shard đang chuyển từ node nguồn sang node đích.
- STARTED: shard copy đã active trên node.

Một cluster có thể tạm thời có relocating/initializing shards trong quá trình node join, rolling restart hoặc cân bằng allocation. Cần theo dõi thời gian và tiến độ. Nếu trạng thái kéo dài, kiểm tra recovery, disk throughput và network.

## 5. Xem shard đang nằm trên node nào

Cat Shards API:

~~~http
GET /_cat/shards?v
~~~

Lọc theo index:

~~~http
GET /_cat/shards/orders?v
~~~

Có thể chọn các cột quan trọng:

~~~http
GET /_cat/shards/orders?v&h=index,shard,prirep,state,docs,store,node,unassigned.reason
~~~

Các cột thường hữu ích:

- index: tên index.
- shard: số shard.
- prirep: p cho primary, r cho replica.
- state: trạng thái shard.
- docs: số document.
- store: dung lượng shard.
- node: node chứa shard copy.
- unassigned.reason: lý do được ghi nhận khi shard chưa được phân bổ, nếu có.

Cat API phù hợp để điều tra nhanh. Với automation, ưu tiên API có cấu trúc JSON thay vì parse bảng text nếu có endpoint phù hợp.

### So sánh primary và replica

Kiểm tra một shard group có primary và replica nằm trên node khác nhau không. Nếu replica unassigned, tìm nguyên nhân trước khi thay đổi replica count hoặc allocation rule.

Không cố đặt replica lên cùng node với primary. Elasticsearch chủ động ngăn cách này để bản sao không mất cùng primary khi node gặp sự cố.

## 6. Dùng Allocation Explain để tìm nguyên nhân

Cluster Allocation Explain API trả lời vì sao một shard chưa được phân bổ hoặc vì sao shard được phân bổ lên node cụ thể.

Ví dụ hỏi về replica shard 0 của index orders:

~~~http
GET /_cluster/allocation/explain
{
  "index": "orders",
  "shard": 0,
  "primary": false
}
~~~

Nếu không chỉ định shard cụ thể, API có thể chọn một shard cần giải thích theo mặc định. Khi điều tra, nên chỉ rõ index, shard và primary/replica để kết quả có mục tiêu.

Response có thể gồm:

- current_state: trạng thái hiện tại.
- unassigned_info: thông tin vì sao shard unassigned.
- can_allocate: yes, no hoặc throttled.
- allocate_explanation: mô tả tổng quát.
- node_allocation_decisions: quyết định của từng node.
- deciders: các allocation decider cho phép hoặc từ chối node.

Ví dụ minh họa một quyết định:

~~~json
{
  "index": "orders",
  "shard": 0,
  "primary": false,
  "current_state": "unassigned",
  "can_allocate": "no",
  "allocate_explanation": "cannot allocate because disk usage exceeds the high watermark",
  "node_allocation_decisions": [
    {
      "node_name": "data-1",
      "node_decision": "no",
      "deciders": [
        {
          "decider": "disk_threshold",
          "decision": "NO",
          "explanation": "the node is above the high watermark"
        }
      ]
    }
  ]
}
~~~

Nội dung chính xác thay đổi theo phiên bản và trạng thái cluster. Đọc các decider để tìm điều kiện đang chặn, không chỉ dựa vào một dòng allocate_explanation.

### Những decider thường gặp

| Decider | Ý nghĩa có thể gặp |
|---|---|
| disk_threshold | Disk watermark ngăn allocation |
| filter | Node không thỏa allocation include/exclude/require |
| awareness | Không đủ node ở failure domain cần thiết |
| same_shard | Không thể đặt hai copy của cùng shard trên một node |
| max_retry | Shard đã vượt số lần allocation retry tự động |
| throttling | Cluster đang giới hạn số recovery/relocation đồng thời |
| enable | Allocation bị tắt cho loại thao tác đó |
| replica_after_primary_active | Replica chờ primary active |

Tên decider và chi tiết response phụ thuộc Elasticsearch version. Hãy dùng allocation explain thay vì đoán từ trạng thái yellow/red.

## 7. Disk watermark là gì?

Disk watermark là ngưỡng dung lượng sử dụng mà Elasticsearch dùng để điều khiển shard allocation và bảo vệ node khỏi hết disk.

Các ngưỡng thường gồm:

- low watermark: hạn chế phân bổ shard mới lên node có disk quá đầy.
- high watermark: hạn chế thêm shard và có thể kích hoạt việc di chuyển shard khỏi node.
- flood-stage watermark: ngưỡng nghiêm trọng, Elasticsearch có thể đặt index read-only-allow-delete để ngăn disk tiếp tục đầy.

Watermark có thể được cấu hình theo tỷ lệ phần trăm dung lượng đã sử dụng hoặc theo lượng disk trống tối thiểu. Khi cấu hình theo tỷ lệ phần trăm, mức sử dụng càng cao thì càng gần ngưỡng. Khi cấu hình theo free space, node phải còn tối thiểu một lượng dung lượng nhất định.

Giá trị mặc định và cách tính headroom có thể thay đổi theo Elasticsearch version. Đừng ghi nhớ một con số rồi áp dụng cho mọi cluster; hãy đọc effective cluster settings của phiên bản đang chạy.

### Low watermark

Khi node vượt low watermark, Elasticsearch thường tránh phân bổ thêm shard lên node đó. Shard hiện có không nhất thiết bị di chuyển ngay chỉ vì low watermark bị vượt.

Điều này giúp ngăn node tiếp tục nhận thêm dữ liệu trong khi dung lượng trống giảm.

### High watermark

Khi node vượt high watermark, Elasticsearch có thể tìm cách di chuyển shard khỏi node để giảm disk usage. Việc di chuyển chỉ thành công nếu có node đích phù hợp và còn đủ disk.

Nếu toàn bộ data node đều vượt high watermark, cluster không có nơi để di chuyển shard. Allocation explain sẽ cho thấy các node đích bị disk decider từ chối.

### Flood-stage watermark

Flood-stage là ngưỡng bảo vệ cuối cùng. Khi vượt ngưỡng, Elasticsearch có thể đặt index.blocks.read_only_allow_delete trên các index có shard nằm trên node bị ảnh hưởng.

Điều này khiến thao tác ghi bị từ chối. Search vẫn có thể hoạt động nếu shard và index không có block đọc tương ứng.

Sau khi disk usage giảm xuống dưới ngưỡng phù hợp, Elasticsearch có cơ chế tự xử lý block flood-stage theo version và trạng thái cluster. Operator cần kiểm tra setting thực tế và nguyên nhân trước khi tự gỡ block.

Không chỉ gửi lệnh gỡ block trong khi disk vẫn đầy. Block có thể được đặt lại hoặc node tiếp tục rơi vào tình trạng nguy hiểm.

## 8. Kiểm tra disk usage của node

Cat Nodes API:

~~~http
GET /_cat/nodes?v&h=name,roles,cpu,heap.percent,ram.percent,disk.used_percent,disk.avail,disk.total
~~~

Cat Allocation API:

~~~http
GET /_cat/allocation?v
~~~

Các API này giúp xem:

- Node nào đang dùng disk nhiều.
- Disk còn trống bao nhiêu.
- Số shard được phân bổ trên mỗi node.
- Disk usage có chênh lệch giữa các node không.

Cat Allocation hữu ích để quan sát dung lượng và shard count. Nó không thay thế allocation explain khi cần biết vì sao một shard cụ thể bị từ chối.

### Kiểm tra disk từ hệ điều hành

Monitoring hạ tầng cũng cần theo dõi filesystem chứa data path của Elasticsearch. Chú ý:

- Disk partition thực sự chứa data path.
- Disk quota hoặc container volume limit.
- Filesystem inode nếu môi trường có giới hạn.
- Dung lượng log, snapshot cache và file tạm.
- Disk latency và throughput.
- Tốc độ tăng dữ liệu theo thời gian.

Disk còn trống ở host không bảo đảm volume bên trong container còn trống nếu dùng quota hoặc volume riêng.

Không xóa thủ công file trong data directory của Elasticsearch. Thao tác đó có thể làm hỏng shard data. Giải phóng disk bằng cách xóa index qua API theo retention policy, mở rộng volume hoặc xử lý dữ liệu/log nằm ngoài data path theo quy trình vận hành.

## 9. Đọc effective disk watermark settings

Xem cluster settings:

~~~http
GET /_cluster/settings?include_defaults=true&flat_settings=true
~~~

Tìm các setting liên quan:

- cluster.routing.allocation.disk.threshold_enabled
- cluster.routing.allocation.disk.watermark.low
- cluster.routing.allocation.disk.watermark.high
- cluster.routing.allocation.disk.watermark.flood_stage
- cluster.routing.allocation.disk.watermark.*.max_headroom

Một số setting có thể xuất hiện ở persistent, transient hoặc defaults. Giá trị có hiệu lực cần được xác định theo precedence của cluster settings.

### Phần trăm và free-space

Ví dụ cấu hình theo phần trăm:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.disk.watermark.low": "85%",
    "cluster.routing.allocation.disk.watermark.high": "90%",
    "cluster.routing.allocation.disk.watermark.flood_stage": "95%"
  }
}
~~~

Ví dụ cấu hình theo dung lượng trống:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.disk.watermark.low": "50gb",
    "cluster.routing.allocation.disk.watermark.high": "30gb",
    "cluster.routing.allocation.disk.watermark.flood_stage": "10gb"
  }
}
~~~

Đây chỉ là ví dụ cú pháp, không phải khuyến nghị giá trị cho mọi cluster. Khi dùng free-space threshold, ngưỡng phải giảm dần theo mức độ nghiêm trọng: low yêu cầu nhiều dung lượng trống hơn high, và flood-stage yêu cầu ít dung lượng trống nhất.

### Max headroom

Một số version hỗ trợ max headroom cho watermark dạng percentage để giới hạn lượng dung lượng trống tối đa được yêu cầu trên disk rất lớn. Nếu cấu hình percentage và không hiểu headroom, có thể diễn giải sai ngưỡng thực tế.

Kiểm tra tài liệu và effective settings đúng version đang chạy trước khi thay đổi. Không sao chép watermark từ một cluster khác mà không xét dung lượng node, data growth và recovery requirements.

## 10. Tại sao disk watermark có thể làm cluster yellow hoặc red?

Giả sử một node gần đầy disk:

1. Low watermark khiến Elasticsearch không muốn phân bổ shard mới lên node đó.
2. High watermark có thể khiến shard cần được di chuyển khỏi node.
3. Nếu không có node đích đủ dung lượng, replica hoặc primary recovery có thể bị chặn.
4. Shard copy chưa được phân bổ khiến cluster yellow hoặc red tùy primary/replica.
5. Nếu vượt flood-stage, index có thể bị đặt read-only-allow-delete và write request thất bại.

Một cluster có thể yellow vì replica không có chỗ đặt dù primary vẫn active. Nếu node chứa primary mất đi trong khi replica chưa được phân bổ, dữ liệu có thể chuyển sang trạng thái red.

Vì vậy, yellow do thiếu disk không chỉ là vấn đề redundancy. Nó có thể là cảnh báo sớm trước khi một node failure làm mất khả năng phục vụ một phần dữ liệu.

## 11. Các nguyên nhân khác khiến shard unassigned

Disk là một nguyên nhân phổ biến, nhưng không phải nguyên nhân duy nhất.

### Không đủ node

Một node duy nhất không thể giữ cả primary và replica copy của cùng shard group. Nếu index có replica count lớn hơn 0, replica sẽ unassigned và cluster thường yellow.

Cách xử lý tùy mục tiêu:

- Thêm data node phù hợp.
- Giảm replica count trong môi trường không cần redundancy.
- Giữ yellow có chủ đích trong development, đồng thời ghi rõ trạng thái mong đợi.

Không giảm replica trong production chỉ để chuyển health sang green nếu hệ thống cần khả năng chịu lỗi.

### Allocation awareness

Cluster có thể được cấu hình để đặt shard copies qua các zone hoặc rack khác nhau. Nếu zone cần thiết không có node hoặc node không đủ dung lượng, replica có thể unassigned.

Kiểm tra node attributes và setting awareness trước khi thay đổi policy.

### Allocation filtering

Index hoặc cluster có thể có include, exclude hoặc require rules. Nếu tất cả node phù hợp bị loại, shard không thể được gán.

Kiểm tra index settings và cluster settings có chứa allocation filters. Không xóa filter tùy tiện nếu nó được dùng để giữ dữ liệu trên loại node hoặc vùng cụ thể.

### Shard limit

Cluster có giới hạn số shard có thể được mở/phân bổ theo node hoặc cấu hình. Khi vượt giới hạn, tạo index mới hoặc phân bổ shard có thể thất bại.

Kiểm tra các giới hạn shard phù hợp với version và license. Cách giải quyết thường là giảm số shard/index không cần thiết, tăng node capacity hợp lý hoặc điều chỉnh thiết kế index.

### Allocation bị tắt hoặc recovery bị throttled

Một thao tác bảo trì có thể tạm thời disable allocation. Cluster cũng có thể throttle recovery khi có nhiều shard cần di chuyển cùng lúc.

Kiểm tra cluster settings và trạng thái recovery trước khi bật lại allocation. Không bật allocation trong khi một quy trình bảo trì đang cố ý tắt nó mà chưa hiểu mục đích.

## 12. Theo dõi shard recovery và relocation

Khi node quay lại hoặc shard được chuyển sang node khác, Elasticsearch thực hiện recovery. Recovery có thể tiêu thụ disk I/O, network bandwidth và CPU.

Xem recovery:

~~~http
GET /_cat/recovery?v
~~~

Xem chi tiết recovery của index:

~~~http
GET /orders/_recovery?human=true&detailed=true
~~~

Theo dõi relocation:

~~~http
GET /_cat/shards/orders?v
~~~

Các trường có thể cho biết:

- shard đang ở trạng thái nào.
- node nguồn và node đích.
- file/byte đã phục hồi.
- phần trăm recovery.
- thời gian recovery.
- stage hiện tại.

Recovery chậm không nhất thiết là lỗi. Với shard lớn, disk chậm hoặc network giới hạn, recovery có thể kéo dài. Cần so sánh tiến độ theo thời gian và kiểm tra tài nguyên.

### Không gây thêm tải khi cluster đang phục hồi

Tránh đồng thời chạy reindex lớn, force merge, snapshot nặng hoặc bulk ingest không giới hạn khi cluster đang recovery vì disk và network có thể bị tranh chấp.

Nếu cần thay đổi recovery concurrency hoặc bandwidth, đo tác động và điều chỉnh theo capacity. Thay đổi quá cao có thể làm workload chính chậm hơn.

## 13. Cluster health và index lifecycle

Index lifecycle ảnh hưởng số shard, dung lượng và allocation.

Với dữ liệu append theo thời gian, rollover giúp giới hạn kích thước mỗi backing index. ILM có thể chuyển index qua hot, warm, cold và delete phase theo policy.

Một số lưu ý:

- Mỗi backing index có primary và replica settings riêng.
- Rollover tạo index mới theo template phù hợp.
- Shard quá nhiều có thể tăng cluster overhead.
- Index quá lớn có thể làm recovery lâu.
- Shrink cần điều kiện và quy trình cụ thể.
- Force merge có thể tiêu thụ disk/CPU mạnh.
- Retention cần xóa index theo policy thay vì xóa file thủ công.

Cluster health nên được theo dõi theo từng index quan trọng, không chỉ toàn cluster. Một index ít quan trọng có thể làm health tổng thể yellow trong khi index phục vụ giao dịch vẫn green, hoặc ngược lại.

## 14. Theo dõi cluster health từ Spring Boot

Ứng dụng Spring Boot có thể dùng Spring Boot Actuator và health indicator Elasticsearch nếu dependency/version hỗ trợ. Health indicator thường kiểm tra khả năng kết nối, nhưng không nhất thiết kiểm tra mọi điều kiện nghiệp vụ như alias write target hoặc shard allocation theo policy.

Có thể tạo custom health indicator cho yêu cầu cụ thể, ví dụ index bắt buộc phải tồn tại và cluster không red.

Pseudocode minh họa:

~~~java
@Component
public class ElasticsearchClusterHealthIndicator
        implements HealthIndicator {

    private final ElasticsearchClient client;

    public ElasticsearchClusterHealthIndicator(
            ElasticsearchClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            ClusterHealthResponse response =
                client.cluster().health();

            String status = response.status().jsonValue();

            if ("red".equals(status)) {
                return Health.down()
                    .withDetail("clusterStatus", status)
                    .build();
            }

            return Health.up()
                .withDetail("clusterStatus", status)
                .withDetail(
                    "unassignedShards",
                    response.unassignedShards()
                )
                .build();

        } catch (Exception ex) {
            return Health.down(ex).build();
        }
    }
}
~~~

Tên method, response type và API client builder cần khớp version Elasticsearch Java API Client. Đây là cấu trúc minh họa cho custom indicator; nếu đã có health indicator mặc định, tránh đăng ký thêm một indicator trùng chức năng mà không có lý do.

### Readiness và liveness

Readiness trả lời instance có nên nhận traffic hay không. Liveness trả lời process có còn sống hay không.

Một số chính sách có thể là:

- Cluster red: readiness của chức năng phụ thuộc Elasticsearch có thể down.
- Cluster yellow: readiness có thể vẫn up nếu primary shard cần thiết hoạt động và hệ thống chấp nhận giảm redundancy.
- Cluster không kết nối được: readiness down cho service phụ thuộc Elasticsearch.
- Disk warning nhưng chưa có write block: readiness có thể vẫn up nhưng phát cảnh báo/metric.
- Alias ghi sai: readiness của service ghi nên down hoặc degraded.

Không nên tự động restart ứng dụng bằng liveness chỉ vì Elasticsearch tạm thời red hoặc không kết nối được. Điều đó không sửa cluster và có thể tạo restart storm.

### Health indicator không nên quá nặng

Không gọi nhiều API chi tiết trên mỗi probe nếu probe được Kubernetes gọi liên tục. Có thể dùng cluster health gọn cho probe và chạy allocation/disk diagnostics ở monitoring job với tần suất thấp hơn.

Không thực hiện thao tác ghi thật trên mỗi health check. Nếu cần xác nhận write path, dùng canary có kiểm soát và tách khỏi readiness probe thường xuyên.

## 15. Metric cần theo dõi

Cluster health là một metric tổng hợp. Để phát hiện vấn đề trước khi cluster red, cần theo dõi nhiều chỉ số.

| Nhóm | Metric hoặc tín hiệu |
|---|---|
| Cluster | health status, active primary, active shard, unassigned shard |
| Allocation | unassigned reason, relocating, initializing, recovery duration |
| Disk | used percent, free bytes, watermark proximity, disk latency |
| Node | CPU, heap, GC, memory, network, filesystem |
| Indexing | indexing rate, bulk latency, rejected writes |
| Search | search latency p50/p95/p99, query rate, failed searches |
| Thread pool | queue size, rejected count cho write/search |
| Cluster state | pending tasks, task wait time |
| Application | repository error rate, timeout, retry count, target index/alias |

### Cảnh báo nên có

Một số alert có thể cấu hình:

- Cluster status red ngay lập tức.
- Yellow kéo dài quá khoảng thời gian vận hành cho phép.
- Unassigned primary lớn hơn 0.
- Unassigned replica kéo dài.
- Disk tiến gần low/high/flood-stage watermark.
- Node disk vượt ngưỡng dự báo.
- Write rejection hoặc 429 tăng đột biến.
- Recovery không có tiến triển.
- Pending cluster tasks tăng và chờ lâu.
- Alias hoặc index bắt buộc không resolve được.

Ngưỡng và thời gian cảnh báo phải dựa trên baseline của cluster. Không dùng một ngưỡng duy nhất cho mọi môi trường hoặc workload.

## 16. Phân biệt cluster health với disk pressure và write block

Một cluster có thể yellow nhưng không có write block. Ngược lại, index có thể bị write block dù health green.

Ví dụ:

| Health | Disk/block | Diễn giải |
|---|---|---|
| green | Disk bình thường, không block | Allocation đầy đủ; vẫn cần theo dõi latency và tải |
| yellow | Replica unassigned do một node | Primary hoạt động nhưng redundancy giảm |
| yellow | Disk watermark ngăn replica allocation | Cần xử lý dung lượng hoặc node placement |
| green | Một index bị operator write block | Shard copies có thể active nhưng index không ghi được |
| red | Primary unassigned | Một phần dữ liệu có thể không khả dụng |
| yellow | Cluster một node, replica count 1 | Có thể là trạng thái dự kiến của development |

Không dùng health status đơn lẻ để kết luận có thể ghi hay không. Đọc block settings và error response của operation.

## 17. Xử lý disk watermark theo trình tự an toàn

Khi node gần đầy disk:

**Bước 1: Xác định node và filesystem.** Dùng Cat Nodes, Cat Allocation và monitoring hệ điều hành để biết disk nào gần đầy.

**Bước 2: Xác định shard chiếm dung lượng.** Dùng Cat Shards và index stats để biết index/shard lớn nhất trên node.

**Bước 3: Kiểm tra tăng trưởng.** Xác định dữ liệu tăng do ingest bình thường, rollover chưa chạy, retention lỗi hay log/snapshot chiếm disk.

**Bước 4: Tạo capacity.** Mở rộng volume hoặc bổ sung node phù hợp; xóa index cũ chỉ khi retention policy cho phép.

**Bước 5: Kiểm tra allocation.** Dùng Allocation Explain để xác nhận node đích có thể nhận shard và disk decider không còn từ chối.

**Bước 6: Xác nhận block.** Kiểm tra index settings xem read_only_allow_delete hoặc block khác còn bật không.

**Bước 7: Khôi phục write.** Chỉ gỡ block theo đúng nguyên nhân và policy; thử ghi có kiểm soát.

**Bước 8: Theo dõi recovery.** Theo dõi shard relocation, recovery, disk và write rejection sau khi phục hồi.

Không xóa file segment hoặc shard data trực tiếp trong filesystem. Không giảm watermark để ép allocation lên node đã đầy. Các hành động đó có thể gây hỏng dữ liệu hoặc làm cluster mất khả năng hoạt động.

## 18. Khôi phục shard unassigned

Khi allocation explain đã chỉ ra nguyên nhân, chọn hành động phù hợp:

| Nguyên nhân | Hướng xử lý |
|---|---|
| Không đủ node cho replica | Thêm node phù hợp hoặc giảm replica trong môi trường chấp nhận được |
| Disk watermark | Giải phóng/mở rộng disk và xác nhận allocation |
| Allocation filter | Sửa filter hoặc bổ sung node thỏa điều kiện |
| Awareness | Bổ sung node đúng zone/rack hoặc xem lại policy |
| Allocation disabled | Bật lại theo quy trình sau khi bảo trì kết thúc |
| Recovery throttled | Theo dõi tiến độ và điều chỉnh capacity/concurrency có kiểm soát |
| Max retry | Tìm root cause, sau đó yêu cầu retry allocation nếu phù hợp |
| Primary mất và không có replica | Khôi phục từ snapshot hoặc đánh giá phương án shard recovery chuyên biệt |

### Reroute không phải công cụ sửa mọi lỗi

Cluster Reroute API cho phép operator yêu cầu một số thao tác allocation thủ công. Nhưng reroute có thể bị allocation decider từ chối hoặc làm thay đổi redundancy.

Chỉ dùng reroute sau khi hiểu allocation explanation và có kế hoạch rõ ràng. Không dùng allocate_stale_primary hoặc allocate_empty_primary để làm cluster green nếu chưa chấp nhận rủi ro mất dữ liệu. Các thao tác force recovery primary có thể bỏ qua dữ liệu mới nhất hoặc tạo shard rỗng.

Nếu primary không thể phục hồi, ưu tiên khôi phục từ snapshot đã xác nhận. Chỉ dùng phương án recovery có rủi ro khi quy trình incident đã đánh giá và chấp thuận.

## 19. Cấu hình replica trong các môi trường

Development một node thường không thể đặt replica trên node khác. Có thể dùng replica count 0 cho index dev/test nếu mục tiêu không yêu cầu redundancy:

~~~http
PUT /orders-dev/_settings
{
  "number_of_replicas": 0
}
~~~

Production nên chọn replica count theo:

- Số data node và failure domain.
- SLO availability.
- Read throughput.
- Disk capacity.
- Recovery time.
- Chi phí replication và network.

Không đặt replica count lớn hơn số node/failure domain có thể đáp ứng nếu không có mục tiêu rõ ràng. Tuy nhiên, số node nhiều hơn replica count cũng không bảo đảm shard copies phân bố qua mọi zone nếu awareness chưa được cấu hình.

## 20. Cấu hình allocation awareness

Nếu cluster chạy qua nhiều availability zone, có thể cấu hình node attribute và awareness để primary/replica copies được phân bố qua các failure domain.

Ví dụ node config:

~~~yaml
node.attr.zone: zone-a
~~~

Trên node ở zone khác:

~~~yaml
node.attr.zone: zone-b
~~~

Cluster setting:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.awareness.attributes": "zone"
  }
}
~~~

Nếu cần strict awareness để tránh đặt replica khi thiếu zone, xem xét setting forced awareness theo tài liệu Elasticsearch version. Forced awareness có thể khiến replica unassigned khi zone bị mất; đó là trade-off có chủ đích để tránh đặt cả primary và replica vào cùng failure domain.

Awareness không thay thế backup. Replica bảo vệ khỏi một số node failures nhưng không thay thế snapshot khi có xóa nhầm, corruption hoặc lỗi nghiệp vụ.

## 21. Integration test cho health và allocation

Có thể dùng Testcontainers để chạy Elasticsearch tương thích trong integration test. Một số tình huống:

- Tạo index có một primary và một replica trên một node; xác nhận health yellow do replica không thể được gán.
- Tạo index với replica count 0; xác nhận health green khi primary active.
- Kiểm tra Cat Shards hoặc Cluster Health API để xác nhận unassigned shard count.
- Kiểm tra allocation explain trả decider tương ứng trong môi trường có thể tái tạo.
- Bật index.blocks.write và xác nhận write thất bại dù cluster có thể vẫn green.
- Kiểm tra service health indicator phân biệt red, yellow và lỗi kết nối.

Testcontainers một node không thể tái hiện mọi trường hợp allocation giữa nhiều node hoặc nhiều zone. Để kiểm tra awareness, relocation và node loss, cần test cluster nhiều node hoặc môi trường chuyên dụng.

### Không test flood-stage bằng cách làm đầy CI disk

Không nên cố ghi dữ liệu đến khi container làm đầy filesystem của CI. Việc này có thể ảnh hưởng runner và tạo test không ổn định. Có thể:

- Unit test việc phân loại error response flood-stage.
- Integration test bật write block trên index test để xác nhận ứng dụng xử lý block.
- Dùng cluster test chuyên biệt để kiểm tra disk watermark thật với giới hạn tài nguyên an toàn.

## 22. Runbook khi cluster chuyển yellow hoặc red

Khi nhận cảnh báo:

1. Gọi Cluster Health API ở cấp cluster và index.
2. Xác định unassigned shard là primary hay replica.
3. Dùng Cat Shards để biết index, shard, node và state.
4. Gọi Allocation Explain cho shard chưa được phân bổ.
5. Kiểm tra disk watermark và allocation settings.
6. Kiểm tra node có mất kết nối, restart hoặc thiếu capacity không.
7. Kiểm tra allocation awareness, filter và shard limit.
8. Chọn hành động sửa theo decider.
9. Theo dõi recovery/relocation.
10. Xác nhận health và dữ liệu sau khi phục hồi.

Với red, xác định chính xác primary shard và dữ liệu bị ảnh hưởng trước khi thao tác. Nếu primary không có bản sao có thể phục hồi, đánh giá snapshot và quy trình disaster recovery. Không ép allocate primary rỗng chỉ để loại bỏ cảnh báo red.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Cluster yellow trên một node | Replica không thể nằm cùng node với primary | Chấp nhận cho dev hoặc thêm node/điều chỉnh replica |
| Cluster red sau khi node mất | Primary shard không có bản sao active | Khôi phục node/replica hoặc snapshot |
| Replica unassigned dù disk còn trống | Awareness/filter/shard limit | Dùng allocation explain |
| Shard không di chuyển khỏi node đầy | Không có node đích đủ disk hoặc phù hợp | Bổ sung capacity và kiểm tra decider |
| Write bị từ chối dù health green | Index block hoặc security privilege | Kiểm tra index settings và error type |
| Index read-only sau disk pressure | Flood-stage watermark | Xử lý disk rồi xác nhận/gỡ block |
| Recovery kéo dài | Shard lớn, disk/network chậm hoặc nhiều recovery | Theo dõi recovery và capacity |
| Cluster health xanh nhưng search chậm | Hot shard, query nặng hoặc node saturation | Xem latency, shard/node stats và thread pool |
| Pending tasks tăng | Cluster state update bị chậm hoặc nhiều thay đổi | Kiểm tra master node và thay đổi allocation |
| Allocation explain báo throttled | Recovery concurrency đang bị giới hạn | Theo dõi tiến độ, tránh tăng tải đột ngột |
| Replica dồn cùng zone | Awareness chưa cấu hình hoặc node attributes sai | Cấu hình và xác minh failure-domain placement |
| Test yellow không ổn định | Test không kiểm soát replica/node topology | Dùng topology cố định và assertion phù hợp |

## 24. Checklist giám sát và vận hành

- [ ] Theo dõi cluster health green/yellow/red.
- [ ] Theo dõi riêng health của index quan trọng.
- [ ] Cảnh báo khi có unassigned primary.
- [ ] Theo dõi unassigned replica kéo dài.
- [ ] Theo dõi initializing và relocating shard.
- [ ] Dùng Cat Shards để kiểm tra node placement.
- [ ] Dùng Allocation Explain cho shard unassigned.
- [ ] Theo dõi disk used/free trên từng data node.
- [ ] Theo dõi low, high và flood-stage watermark.
- [ ] Đọc effective cluster settings thay vì giả định default.
- [ ] Theo dõi read-only-allow-delete và write block.
- [ ] Theo dõi recovery progress, disk latency và network.
- [ ] Kiểm tra allocation awareness/filter và shard limits.
- [ ] Không xóa thủ công file trong Elasticsearch data path.
- [ ] Không hạ watermark để che giấu thiếu capacity.
- [ ] Không ép allocate stale/empty primary khi chưa đánh giá mất dữ liệu.
- [ ] Tách readiness và liveness.
- [ ] Không gọi API chẩn đoán nặng trong health probe quá thường xuyên.
- [ ] Có Testcontainers test cho health, replica và write block.
- [ ] Có runbook xử lý yellow/red và disk pressure.

Cluster health cho biết mức độ sẵn sàng của shard copies, allocation explain chỉ ra vì sao shard chưa được gán, còn disk watermark bảo vệ cluster khi dung lượng node giảm. Ba tín hiệu cần được đọc cùng nhau: yellow có thể là thiếu replica do topology, red có thể là primary mất, và write block có thể xuất hiện ngay cả khi health green. Theo dõi disk theo node, unassigned shard, recovery và allocation decider giúp phát hiện sự cố sớm. Khi xử lý, hãy sửa nguyên nhân về capacity, node placement hoặc policy trước khi thay đổi allocation/block, rồi xác nhận shard recovery và khả năng đọc/ghi sau phục hồi.

