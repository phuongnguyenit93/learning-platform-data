# Quản lý thành viên quorum theo khả năng của phiên bản

## Mục tiêu

KRaft lưu metadata của Kafka trong một metadata log được sao chép giữa các controller. Các controller tham gia một quorum Raft; để quorum tiếp tục bầu leader và ghi metadata, đa số voter phải còn hoạt động. Vì vậy, thêm hoặc loại bỏ controller là thay đổi membership của một hệ thống đồng thuận, không đơn giản là bật hoặc tắt một tiến trình.

Khả năng quản lý membership phụ thuộc phiên bản Kafka và loại quorum mà cluster đã được khởi tạo. Bài học này phân biệt static quorum và dynamic quorum, trình bày mốc phiên bản quan trọng từ Kafka 3.9 đến 4.1, sau đó hướng dẫn kiểm tra, thêm và loại bỏ controller an toàn.

Sau bài học, bạn có thể:

- Nhận biết cluster đang dùng static hay dynamic KRaft quorum.
- Giải thích khác biệt giữa `controller.quorum.voters` và `controller.quorum.bootstrap.servers`.
- Xác định khả năng thay đổi membership theo phiên bản và `kraft.version`.
- Khởi tạo dynamic quorum, thêm controller mới và theo dõi metadata replication.
- Loại bỏ controller theo đúng quy trình của phiên bản đang chạy.
- Lập kế hoạch nâng cấp static quorum lên dynamic quorum khi cluster đã đạt Kafka 4.1 trở lên.

## 1. Controller quorum và nguyên tắc đa số

Trong KRaft, controller quản lý metadata như topic, partition, broker registration và cấu hình cluster. Các controller cùng duy trì metadata log. Một controller là leader của metadata quorum; những controller còn lại là follower/standby và sao chép metadata log.

Quorum cần đa số voter để tiếp tục hoạt động. Với N controller voter, số lỗi đồng thời có thể chịu được là:

`f = floor((N - 1) / 2)`

| Số controller voter | Số voter cần để có đa số | Số controller có thể lỗi mà quorum vẫn hoạt động |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |

Vì vậy, production thường dùng 3 hoặc 5 controller voter. Số lẻ giúp tăng khả năng chịu lỗi hiệu quả hơn so với thêm một voter để tạo số chẵn. Một controller đơn lẻ phù hợp cho development hoặc lab, nhưng không có khả năng chịu lỗi controller.

Controller nên chạy trên các node riêng biệt với broker trong hệ thống quan trọng. Chế độ combined (`process.roles=broker,controller`) tiện cho môi trường nhỏ, nhưng không thể scale hoặc rolling controller độc lập với broker; nó làm giảm mức độ cô lập tài nguyên và vận hành.

## 2. Static quorum và dynamic quorum

KRaft có hai cách xác định tập controller voter:

| Thuộc tính | Static quorum | Dynamic quorum |
|---|---|---|
| Cấu hình nhận diện | `controller.quorum.voters` | `controller.quorum.bootstrap.servers` và feature `kraft.version=1` |
| Thành viên voter | Khai báo tĩnh trong cấu hình của các node | Được lưu và thay đổi trong metadata quorum |
| Thêm/xóa voter | Cần quy trình reconfiguration tĩnh theo phiên bản; không dùng lệnh dynamic membership | Có lệnh `add-controller` và `remove-controller` |
| Ý nghĩa danh sách cấu hình | ID, host và port của toàn bộ controller voter | Các endpoint bootstrap để node tìm quorum; không phải danh sách membership chuẩn |
| Khả năng di chuyển static sang dynamic | Chưa hỗ trợ ở Kafka 3.9 và 4.0 | Kafka 4.1 bổ sung quy trình nâng cấp feature và cấu hình |

### 2.1. Static quorum

Static quorum sử dụng `controller.quorum.voters`. Mỗi broker và controller phải khai báo cùng danh sách controller với ID, hostname và port:

```properties
process.roles=controller
node.id=1
listeners=CONTROLLER://controller-1.example.com:9093
controller.listener.names=CONTROLLER
controller.quorum.voters=1@controller-1.example.com:9093,2@controller-2.example.com:9093,3@controller-3.example.com:9093
```

Trong static quorum, danh sách voter được định nghĩa khi format storage và cấu hình cluster. Khi cần thay đổi tập controller, không thể chỉ chạy `add-controller` hoặc `remove-controller` như dynamic quorum. Phải dùng quy trình reconfiguration/rolling restart phù hợp với phiên bản và bảo đảm tất cả node có cấu hình nhất quán.

### 2.2. Dynamic quorum

Dynamic quorum dùng `controller.quorum.bootstrap.servers`:

```properties
process.roles=controller
node.id=1
listeners=CONTROLLER://controller-1.example.com:9093
controller.listener.names=CONTROLLER
controller.quorum.bootstrap.servers=controller-1.example.com:9093,controller-2.example.com:9093,controller-3.example.com:9093
```

Thuộc tính này cung cấp địa chỉ để broker/controller tìm metadata quorum, tương tự `bootstrap.servers` của Kafka client. Danh sách này nên bao gồm nhiều endpoint controller đang hoạt động để tăng khả năng discovery, nhưng không phải nguồn chuẩn xác định voter membership. Dynamic quorum lưu tập voter trong metadata; các lệnh quản trị membership cập nhật tập đó.

Khi dùng dynamic quorum, không cấu hình đồng thời `controller.quorum.voters`. Mỗi broker và controller cần có `controller.quorum.bootstrap.servers` để tìm controller quorum.

## 3. Khả năng theo phiên bản Kafka

Dynamic quorum được giới thiệu qua KIP-853 trong Kafka 3.9. Tuy nhiên, có dynamic quorum cho cluster mới và khả năng chuyển một cluster static đang chạy sang dynamic là hai việc khác nhau.

| Phiên bản | Khả năng liên quan đến membership |
|---|---|
| Kafka 3.8 trở xuống | KRaft dùng static quorum với `controller.quorum.voters`; chưa có KIP-853 dynamic membership |
| Kafka 3.9 | Có thể tạo cluster mới với dynamic quorum và dùng lệnh thêm/xóa controller; cluster static hiện hữu chưa thể chuyển sang dynamic |
| Kafka 4.0 | KRaft là chế độ metadata duy nhất; dynamic quorum vẫn dùng được cho cluster được tạo theo cấu hình dynamic, nhưng chuyển cluster static sang dynamic vẫn chưa được hỗ trợ |
| Kafka 4.1 trở lên | Bổ sung nâng cấp cluster static sang dynamic bằng `kraft.version=1` và thay đổi cấu hình node; sau đó có thể quản lý membership động |

Hai mốc cần nhớ:

- **Kafka 3.9:** bắt đầu có dynamic quorum cho cluster được khởi tạo đúng cách.
- **Kafka 4.1:** bổ sung đường nâng cấp cluster static đã tồn tại sang dynamic quorum.

Không suy ra cluster đang dynamic chỉ từ việc binary Kafka đã được nâng lên 4.1 hoặc mới hơn. Loại quorum phụ thuộc feature level đã finalized và cách storage/cluster được khởi tạo hoặc nâng cấp.

## 4. Kiểm tra loại quorum và feature level

Trước khi thay đổi controller, xác định loại quorum hiện tại. Dùng `kafka-features.sh` kết nối tới controller endpoint:

```bash
bin/kafka-features.sh --bootstrap-controller controller-1.example.com:9093 describe
```

Đọc dòng `Feature: kraft.version`:

- Nếu `FinalizedVersionLevel` là `0`, cluster đang dùng static quorum.
- Nếu feature `kraft.version` không xuất hiện, cluster cũng đang ở trạng thái static theo cách nhận diện này.
- Nếu `FinalizedVersionLevel` là `1` hoặc cao hơn, cluster dùng dynamic quorum.

Ví dụ output static:

```text
Feature: kraft.version  SupportedMinVersion: 0  SupportedMaxVersion: 1  FinalizedVersionLevel: 0  Epoch: 7
Feature: metadata.version  SupportedMinVersion: ...  SupportedMaxVersion: ...  FinalizedVersionLevel: ...
```

Ví dụ output dynamic:

```text
Feature: kraft.version  SupportedMinVersion: 0  SupportedMaxVersion: 1  FinalizedVersionLevel: 1  Epoch: 8
Feature: metadata.version  SupportedMinVersion: ...  SupportedMaxVersion: ...  FinalizedVersionLevel: ...
```

`kraft.version` là feature level điều khiển khả năng KRaft quorum. `metadata.version` là feature level cho các thay đổi metadata khác. Hai giá trị có liên quan đến khả năng tương thích nhưng không thể dùng thay thế cho nhau.

Tiếp theo, kiểm tra trạng thái quorum:

```bash
bin/kafka-metadata-quorum.sh --bootstrap-controller controller-1.example.com:9093 describe --status
bin/kafka-metadata-quorum.sh --bootstrap-controller controller-1.example.com:9093 describe --replication
```

`describe --status` cho biết leader metadata quorum, high watermark, current voters và observers theo phiên bản. `describe --replication` cho biết tiến độ sao chép metadata log của các thành viên. Đây là hai kiểm tra quan trọng trước và sau thay đổi membership.

## 5. Khởi tạo dynamic quorum cho cluster mới

Với Kafka 3.9 trở lên, dynamic quorum được xác định khi format storage mà không cấu hình `controller.quorum.voters` và sử dụng một trong các lựa chọn bootstrap dynamic như `--standalone`, `--initial-controllers` hoặc `--no-initial-controllers`.

### 5.1. Khởi tạo một controller đầu tiên

Tạo cluster ID và format controller đầu tiên:

```bash
CLUSTER_ID=$(bin/kafka-storage.sh random-uuid)

bin/kafka-storage.sh format \
  --cluster-id "$CLUSTER_ID" \
  --standalone \
  --config config/controller-1.properties
```

`--standalone` tạo metadata quorum ban đầu với controller này là voter duy nhất. Sau đó khởi động controller. Khi quorum đã sẵn sàng, các controller tiếp theo có thể được thêm bằng dynamic membership.

### 5.2. Khởi tạo nhiều controller ngay từ đầu

Có thể format nhiều controller với `--initial-controllers`. Mỗi controller cần dùng cùng cluster ID và cùng danh sách initial controllers. Mỗi controller có node ID, host, port và directory ID riêng:

```bash
CLUSTER_ID=$(bin/kafka-storage.sh random-uuid)
C1_UUID=$(bin/kafka-storage.sh random-uuid)
C2_UUID=$(bin/kafka-storage.sh random-uuid)
C3_UUID=$(bin/kafka-storage.sh random-uuid)

bin/kafka-storage.sh format \
  --cluster-id "$CLUSTER_ID" \
  --initial-controllers "1@controller-1:9093:$C1_UUID,2@controller-2:9093:$C2_UUID,3@controller-3:9093:$C3_UUID" \
  --config config/controller.properties
```

Thực hiện lệnh format trên từng controller với cùng cluster ID và cùng chuỗi `--initial-controllers`. Ví dụ trên minh họa cú pháp; trong thực tế, lưu các UUID đã sinh và dùng nhất quán trên cả ba node. Không tự tạo UUID khác nhau cho cùng một controller ở các lần format.

Khởi tạo một voter trước rồi thêm controller sau thường dễ mở rộng và quan sát hơn. Nếu dùng `--initial-controllers`, hãy bảo đảm tất cả controller được format và khởi động theo kế hoạch bootstrap đã chọn.

## 6. Thêm controller vào dynamic quorum

Quy trình thêm controller gồm ba giai đoạn: provision storage, để node đồng bộ metadata, rồi mới promote node thành voter.

### 6.1. Chuẩn bị cấu hình controller mới

Ví dụ controller mới có node ID `4`:

```properties
process.roles=controller
node.id=4
listeners=CONTROLLER://controller-4.example.com:9093
controller.listener.names=CONTROLLER
controller.quorum.bootstrap.servers=controller-1.example.com:9093,controller-2.example.com:9093,controller-3.example.com:9093
log.dirs=/var/lib/kafka/controller-4
```

Điểm cần chú ý:

- Dùng cùng cluster ID với cluster hiện tại.
- Chọn `node.id` chưa được dùng trong cluster.
- Dùng storage directory mới và bền vững cho controller mới.
- `controller.quorum.bootstrap.servers` phải chứa ít nhất một controller đang thuộc quorum; nên liệt kê nhiều endpoint hiện có.
- Không khai báo `controller.quorum.voters` trong dynamic quorum.

Format storage của controller mới:

```bash
bin/kafka-storage.sh format \
  --cluster-id <CLUSTER_ID> \
  --config config/controller-4.properties \
  --no-initial-controllers
```

`--no-initial-controllers` dùng khi thêm node vào một cluster đã tồn tại. Nó ngăn storage của controller mới tự khởi tạo một voter set mới độc lập với cluster hiện tại.

### 6.2. Khởi động và đợi metadata replication

Khởi động controller mới bằng quy trình service/orchestrator của môi trường. Sau đó kiểm tra replication từ controller hiện có:

```bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-controller controller-1.example.com:9093 \
  describe --replication
```

Controller mới cần bắt kịp metadata log của active controller trước khi được thêm vào voter set. Trong thời gian này, controller mới có thể xuất hiện như observer. Chờ đến khi lag bằng 0 hoặc đạt trạng thái bắt kịp theo chỉ số của phiên bản đang chạy.

### 6.3. Thêm controller vào voter set

Khi controller mới đã bắt kịp, chạy `add-controller`. `--command-config` trỏ đến cấu hình của controller sắp được thêm; file đó chứa cấu hình kết nối và xác thực AdminClient cần thiết:

```bash
bin/kafka-metadata-quorum.sh \
  --command-config config/controller-4.properties \
  --bootstrap-controller controller-1.example.com:9093 \
  add-controller
```

Có thể dùng `--bootstrap-server broker-1.example.com:9092` thay cho `--bootstrap-controller` nếu thao tác qua broker endpoint. Với SASL/SSL hoặc cấu hình AdminClient khác, bảo đảm `controller-4.properties` có đầy đủ thông tin bảo mật.

Sau khi lệnh thành công, đọc lại quorum:

```bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-controller controller-1.example.com:9093 \
  describe --status
```

Xác nhận controller ID mới xuất hiện trong `CurrentVoters`, quorum vẫn có đa số voter khỏe mạnh và replication lag không tăng bất thường.

## 7. Loại bỏ controller khỏi dynamic quorum

Trước khi loại bỏ, xác định chính xác controller ID và directory ID. Có thể lấy chúng từ `CurrentVoters` trong kết quả:

```bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-controller controller-1.example.com:9093 \
  describe --status
```

Ví dụ một voter có thể xuất hiện như sau:

```text
CurrentVoters: [{"id": 1, "directoryId": "...", "endpoints": ["CONTROLLER://controller-1:9093"]}, ...]
```

`controller-id` là node ID của controller; `controller-directory-id` là directory ID được tạo khi format storage. Không đoán hoặc dùng directory ID của controller khác.

### 7.1. Trình tự remove phụ thuộc phiên bản

Tài liệu Kafka 4.1 lưu ý rằng trước khi KIP-996 pre-vote được triển khai, nên shutdown controller cần loại bỏ trước khi chạy `remove-controller`. Tài liệu Kafka mới hơn (ví dụ Kafka 4.4) hướng dẫn loại controller khỏi voter set trước rồi mới shutdown. Vì vậy, không sao chép thứ tự thao tác từ một phiên bản khác; kiểm tra đúng tài liệu/CLI của phiên bản cluster đang chạy.

Ví dụ cú pháp remove controller trong dynamic quorum:

```bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-controller controller-1.example.com:9093 \
  remove-controller \
  --controller-id 4 \
  --controller-directory-id <DIRECTORY_ID>
```

Trên các phiên bản có hỗ trợ, có thể dùng thêm `--unregister` để vừa remove voter vừa unregister controller khỏi cluster metadata. Nếu không dùng tùy chọn này, controller đã remove khỏi voter set có thể được unregister riêng bằng `kafka-cluster.sh unregister-controller` sau khi controller đã dừng. Kiểm tra `kafka-metadata-quorum.sh remove-controller --help` và `kafka-cluster.sh unregister-controller --help` của đúng binary trước khi thực hiện.

### 7.2. Kiểm tra sau khi remove

Sau khi remove và shutdown controller theo trình tự của phiên bản:

1. Chạy `describe --status` và xác nhận controller không còn trong `CurrentVoters`.
2. Xác nhận số voter còn lại vẫn đủ đa số và phù hợp mục tiêu chịu lỗi.
3. Kiểm tra `describe --replication` để xác nhận các controller còn lại đồng bộ metadata log.
4. Kiểm tra log controller và broker để phát hiện election bất thường hoặc lỗi kết nối.
5. Chỉ decommission host/storage cũ sau khi đã xác nhận cluster ổn định và quy trình unregister (nếu cần) hoàn tất.

Không xóa metadata directory của controller trước khi hoàn thành thao tác membership. Nếu quorum đã mất đa số, khôi phục đủ controller để có quorum trước khi thực hiện thay đổi membership; không thể trông chờ lệnh remove để sửa một quorum đã không thể bầu leader.

## 8. Nâng cấp static quorum lên dynamic quorum bằng Kafka 4.1+

Kafka 3.9 và 4.0 cho phép tạo dynamic quorum mới nhưng chưa có quy trình chuyển static quorum hiện hữu sang dynamic. Kafka 4.1 bổ sung khả năng này thông qua nâng cấp `kraft.version` và thay đổi cấu hình trên toàn bộ node.

Đây là nâng cấp feature của cluster, không chỉ là thay đổi một dòng cấu hình. Thực hiện sau khi phần mềm Kafka trên cluster đã được nâng lên phiên bản hỗ trợ (4.1 trở lên), theo quy trình nâng cấp của cluster.

### 8.1. Kiểm tra trạng thái hiện tại

```bash
bin/kafka-features.sh \
  --bootstrap-controller controller-1.example.com:9093 \
  describe
```

Nếu `kraft.version` có `FinalizedVersionLevel: 0` hoặc không xuất hiện, cluster hiện vẫn là static quorum. Ghi lại `metadata.version`, phiên bản binary, controller voter list và cấu hình hiện tại trước khi thay đổi.

### 8.2. Nâng feature level

Với cluster đã chạy Kafka 4.1 trở lên, nâng riêng KRaft feature:

```bash
bin/kafka-features.sh \
  --bootstrap-server broker-1.example.com:9092 \
  upgrade --feature kraft.version=1
```

Có thể nâng toàn bộ feature theo release bằng `--release-version 4.1`, nhưng thao tác đó cũng cập nhật các feature version khác theo release. Nếu mục tiêu chỉ là dynamic controller quorum, nâng riêng `kraft.version=1` sẽ thể hiện rõ phạm vi thay đổi hơn.

Đọc lại feature state và xác nhận `FinalizedVersionLevel: 1` trước khi thay đổi cấu hình node.

### 8.3. Cập nhật cấu hình tất cả broker và controller

Sau khi feature version đã được nâng thành công, cập nhật mọi broker và controller:

```properties
# Xóa cấu hình static cũ:
# controller.quorum.voters=1@controller-1:9093,2@controller-2:9093,3@controller-3:9093

# Thêm danh sách endpoint dùng để bootstrap/discovery:
controller.quorum.bootstrap.servers=controller-1:9093,controller-2:9093,controller-3:9093
```

`controller.quorum.voters` được deprecated trong KRaft version 1. Không giữ cấu hình static đó trong khi chuyển sang dynamic. Mọi node cần được cập nhật nhất quán; áp dụng thay đổi bằng quy trình rolling restart/reconfiguration đã được kiểm chứng cho phiên bản triển khai.

### 8.4. Xác minh sau nâng cấp

Kiểm tra lại feature level:

```bash
bin/kafka-features.sh --bootstrap-controller controller-1:9093 describe
```

Kiểm tra cấu hình node và metadata quorum:

```bash
bin/kafka-metadata-quorum.sh --bootstrap-controller controller-1:9093 describe --status
bin/kafka-metadata-quorum.sh --bootstrap-controller controller-1:9093 describe --replication
```

Chỉ khi `kraft.version` đã finalized ở level 1, các node dùng `controller.quorum.bootstrap.servers` và quorum khỏe mạnh mới bắt đầu quản lý membership bằng `add-controller`/`remove-controller`.

## 9. Những nguyên tắc an toàn khi thay đổi membership

- Thay đổi một controller tại một thời điểm; chờ replication và quorum ổn định trước bước tiếp theo.
- Không giảm voter count xuống dưới đa số cần thiết. Ví dụ, khi quorum có 3 voter, không remove thêm controller nếu một voter khác đang lỗi.
- Ưu tiên giữ số voter lẻ (3 hoặc 5) để có khả năng chịu lỗi hợp lý.
- Thêm controller mới cần đồng bộ metadata trước khi promote thành voter.
- Dùng `node.id` duy nhất và directory ID đúng với storage của controller.
- Không copy nguyên metadata directory từ controller khác để tạo controller mới.
- Đảm bảo network, DNS, listener và TLS/SASL cho controller endpoint hoạt động trước khi thay đổi.
- Lưu lại trạng thái `describe --status`, `describe --replication` và feature level trước/sau thao tác để có bằng chứng kiểm tra.
- Không nhầm `controller.quorum.bootstrap.servers` với voter list: sửa bootstrap list không tự thêm hoặc xóa voter khỏi quorum.
- Không chạy lệnh dynamic membership trên static quorum; xác minh `kraft.version` trước.
- Trong combined mode, controller và broker nằm cùng node; thay đổi controller membership cũng tác động trực tiếp đến năng lực broker. Production nên dùng dedicated controller khi cần scale độc lập.

## 10. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `add-controller` không được hỗ trợ | Cluster đang static quorum hoặc `kraft.version` chưa finalized ở level 1 | Kiểm tra `kafka-features.sh describe`; chỉ chuyển static sang dynamic trên Kafka 4.1+ theo quy trình nâng cấp |
| Controller mới không bắt kịp | Sai cluster ID, sai bootstrap endpoint, listener/firewall/DNS hoặc metadata replication bị gián đoạn | Kiểm tra storage format, cấu hình listener và `describe --replication`; xem log controller |
| `add-controller` từ chối request | `--command-config` không trỏ tới controller mới hoặc không có endpoint quorum hiện tại | Dùng đúng config của controller được thêm và bảo đảm `controller.quorum.bootstrap.servers` có controller hiện hữu |
| `remove-controller` thất bại | Sai controller ID/directory ID, quorum không khỏe hoặc trình tự shutdown không đúng phiên bản | Đọc `describe --status`, xác minh ID và directory ID, kiểm tra tài liệu đúng phiên bản |
| Quorum không có leader sau khi remove | Số voter còn lại không đạt đa số hoặc nhiều controller đồng thời lỗi | Khôi phục controller cần thiết để có đa số; không tiếp tục thay đổi membership khi quorum chưa ổn định |
| Broker không kết nối được controller sau khi đổi config | Một số node còn `controller.quorum.voters` hoặc bootstrap endpoint sai | Đối chiếu cấu hình trên toàn bộ broker/controller và rolling restart theo kế hoạch |
| Controller cũ xuất hiện lại sau decommission | Chưa unregister hoặc tiến trình cũ vẫn chạy và tự đăng ký lại | Dừng đúng tiến trình, xác nhận đã remove khỏi voter set, rồi unregister theo khả năng của phiên bản |

## 11. Bài thực hành và tự kiểm tra

### Thực hành A — Nhận diện static và dynamic quorum

1. Dùng `kafka-features.sh describe` để đọc `kraft.version`.
2. Chạy `kafka-metadata-quorum.sh describe --status` và ghi lại `CurrentVoters`.
3. Kiểm tra cấu hình node có `controller.quorum.voters` hay `controller.quorum.bootstrap.servers`.
4. Kết luận loại quorum và giải thích vì sao không thể chỉ dựa vào tên file cấu hình.

### Thực hành B — Thêm controller vào dynamic quorum

1. Dựng dynamic quorum với một controller đầu tiên bằng `--standalone`.
2. Chuẩn bị controller thứ hai với node ID và storage riêng.
3. Format controller mới bằng `--no-initial-controllers` và cùng cluster ID.
4. Khởi động controller mới và theo dõi `describe --replication`.
5. Khi controller mới bắt kịp, chạy `add-controller` với `--command-config` đúng file.
6. Đọc `describe --status` và xác nhận controller mới trong `CurrentVoters`.

### Thực hành C — Phân tích kế hoạch nâng cấp

Một cluster KRaft static hiện chạy Kafka 3.8 với ba controller. Hãy lập kế hoạch chuyển sang dynamic quorum, trả lời:

- Vì sao không thể chạy `add-controller` ngay trên cluster 3.8?
- Cần nâng binary lên phiên bản nào trước khi nâng `kraft.version`?
- Lệnh nào kiểm tra feature level và lệnh nào nâng `kraft.version`?
- Những cấu hình nào phải thay đổi trên tất cả broker/controller?
- Cần kiểm tra gì trước và sau rolling restart?

### Câu hỏi tự kiểm tra

1. Quorum ba controller có thể chịu được bao nhiêu controller lỗi? Vì sao?
2. `controller.quorum.voters` khác `controller.quorum.bootstrap.servers` ở ý nghĩa nào?
3. Kafka 3.9 hỗ trợ dynamic quorum trong trường hợp nào? Hạn chế gì với static cluster cũ?
4. Kafka 4.1 bổ sung khả năng nâng cấp nào liên quan đến membership?
5. Vì sao controller mới cần đồng bộ metadata trước khi chạy `add-controller`?
6. Tại sao phải lấy cả controller ID và directory ID khi remove?
7. Vì sao trình tự shutdown/remove có thể khác giữa Kafka 4.1 và tài liệu Kafka mới hơn?
8. Nếu quorum đã mất đa số, vì sao không nên tiếp tục thay đổi membership?

## Kết luận

Khả năng quản lý thành viên KRaft quorum được quyết định bởi loại quorum và feature version của cluster. Kafka 3.9 giới thiệu dynamic quorum cho cluster mới; Kafka 4.1 bổ sung đường nâng cấp static quorum sang dynamic bằng `kraft.version=1`. Trong dynamic quorum, controller mới cần được format, đồng bộ metadata rồi mới promote thành voter; khi loại bỏ controller, phải dùng đúng ID, directory ID và trình tự theo phiên bản. Luôn xác minh feature level, voter set và replication state trước/sau mỗi thay đổi để giữ quorum có đa số và tránh mất khả năng quản lý metadata.

## Tài liệu tham khảo

- [Apache Kafka 3.9 — KRaft operations](https://kafka.apache.org/39/operations/kraft/)
- [Apache Kafka 4.0 — KRaft operations](https://kafka.apache.org/40/operations/kraft/)
- [Apache Kafka 4.1 — KRaft operations and static-to-dynamic upgrade](https://kafka.apache.org/41/operations/kraft/)
- [Apache Kafka 4.4 — KRaft operations and controller membership changes](https://kafka.apache.org/44/operations/kraft/)
- [Apache Kafka 3.9 release announcement — Dynamic KRaft Quorums](https://kafka.apache.org/blog/2024/11/06/apache-kafka-3.9.0-release-announcement/)
