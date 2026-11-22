# Quorum, mất liên lạc và phòng ngừa split-brain

Một hệ thống MySQL có nhiều node chỉ thực sự sẵn sàng cao khi các node có thể xác định ai đang được phép nhận ghi sau lỗi. Khi mạng bị chia cắt, hai nhóm máy chủ có thể cùng tin rằng nhóm còn lại đã chết. Nếu cả hai nhóm đều nhận ghi, dữ liệu sẽ phân nhánh và rất khó hợp nhất. Hiện tượng này gọi là **split-brain**.

Quorum là cơ chế yêu cầu một nhóm node có đủ phiếu để đưa ra quyết định chung. Trong MySQL Group Replication, quorum giúp nhóm thành viên xác định phân vùng nào còn quyền tiếp tục hoạt động. Với replication bất đồng bộ truyền thống, MySQL không tự cung cấp cơ chế bầu chọn primary theo quorum; hệ thống điều phối bên ngoài phải chọn node, ngăn primary cũ nhận ghi và cập nhật endpoint ứng dụng.

Bài học này thuộc phạm vi vận hành MySQL quan hệ: hiểu quorum, nhận diện mất liên lạc, phân biệt lỗi node với lỗi mạng, và xây dựng quy trình failover có fencing. Các ví dụ dùng MySQL 8.0, trong đó cú pháp `SOURCE`/`REPLICA` được dùng từ MySQL 8.0.23. Tên biến hoặc hành vi cụ thể có thể khác theo phiên bản và cách triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích quorum và tính số phiếu tối thiểu để một nhóm tiếp tục hoạt động.
- Phân biệt quorum của Group Replication với replication bất đồng bộ và bán đồng bộ.
- Mô tả cách network partition tạo ra nguy cơ split-brain.
- Kiểm tra membership và trạng thái của các thành viên Group Replication.
- Xây dựng quy trình xử lý mất quorum, phục hồi node và promote replica an toàn.
- Giải thích vai trò của fencing, `read_only`, `super_read_only` và endpoint ghi.

## 1. Quorum là gì?

Quorum là số phiếu tối thiểu mà một nhóm cần có để tiếp tục một hoạt động cần sự đồng thuận. Với hệ thống có `N` thành viên bỏ phiếu, quorum đa số được tính bằng:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Ví dụ:

| Số thành viên | Quorum | Số thành viên có thể mất mà nhóm vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Quorum đa số giúp hai phân vùng độc lập không thể đồng thời sở hữu đa số phiếu trong cùng một membership view. Ví dụ với ba node, chỉ một phân vùng có thể chứa hai node; node còn lại không có đủ phiếu để tự quyết định tiếp tục như một nhóm độc lập.

Trong thực tế, không chỉ đếm số máy đang bật. Cần biết node nào đang thuộc membership view hiện tại, node nào đã bị loại khỏi nhóm, node nào đang `RECOVERING`, và cơ chế nào xác định phiếu hợp lệ. Một máy chủ có tiến trình MySQL đang chạy nhưng không còn thuộc nhóm không tự động có quyền nhận ghi.

### 1.1. Vì sao thường chọn số node lẻ?

Với quorum đa số, ba node cần hai phiếu và có thể chịu một node lỗi. Bốn node vẫn cần ba phiếu nên cũng chỉ chịu được một node lỗi. Năm node cần ba phiếu và chịu được hai node lỗi. Vì vậy, số node lẻ thường cung cấp khả năng chịu lỗi tốt hơn trên mỗi node được bổ sung.

Ví dụ, cụm ba node đặt ở ba failure domain độc lập có thể tiếp tục khi một vùng gặp sự cố, miễn hai vùng còn lại vẫn liên lạc được. Nếu cả ba node cùng nằm trong một rack hoặc cùng phụ thuộc vào một switch, lỗi hạ tầng chung có thể làm mất cả quorum.

Quorum không thay thế dự phòng hạ tầng. Cần phân bố node theo vùng lỗi, bảo đảm kết nối mạng giữa các vùng và tính đến độ trễ, băng thông, nguồn điện, storage cùng các dịch vụ điều phối.

## 2. Quorum trong MySQL Group Replication

MySQL Group Replication sử dụng cơ chế truyền thông nhóm và membership để các thành viên thống nhất về tập node đang tham gia. Một nhóm cần đa số thành viên trong membership view để tiếp tục xử lý giao dịch theo cơ chế nhất quán của nhóm. Khi một phân vùng mất liên lạc với đa số, phân vùng đó mất quorum và không thể tiếp tục commit giao dịch như một nhóm độc lập.

Group Replication có hai chế độ chính:

- **Single-primary mode:** chỉ một thành viên được bầu làm primary nhận ghi; các thành viên còn lại thường phục vụ đọc và áp dụng giao dịch. Khi primary gặp sự cố, nhóm có quorum có thể bầu một primary mới.
- **Multi-primary mode:** nhiều thành viên có thể nhận ghi. Cơ chế certification kiểm tra xung đột giữa các giao dịch trước khi commit. Chế độ này cần thiết kế ứng dụng cẩn thận vì các cập nhật đồng thời trên cùng dữ liệu có thể bị từ chối do conflict.

Quorum bảo vệ quyền tiếp tục hoạt động của nhóm. Nó không bảo đảm mọi transaction mà client từng gửi đều đã commit, không thay thế backup, và không tự sửa dữ liệu được ghi ngoài nhóm. Trong multi-primary, quorum cũng không loại bỏ xung đột dữ liệu ở cấp nghiệp vụ.

### 2.1. Ví dụ cụm ba thành viên

Giả sử nhóm có `db-1`, `db-2`, `db-3` và quorum bằng hai:

| Tình huống | Membership/kết nối | Kết quả cần hiểu |
|---|---|---|
| `db-1` hỏng, `db-2` và `db-3` liên lạc được | Hai node còn lại giữ đa số | Nhóm có thể tiếp tục; single-primary có thể bầu primary mới |
| `db-1` bị cô lập, `db-2` và `db-3` liên lạc được | Phân vùng hai node có đa số | Phân vùng đa số tiếp tục; node cô lập không được tự nhận quyền ghi |
| `db-1` và `db-2` mất liên lạc với `db-3` nhưng vẫn liên lạc nhau | Phân vùng hai node giữ đa số | Hai node có thể tiếp tục theo membership hợp lệ |
| Cả ba node không thể tạo được đa số liên lạc | Không có phân vùng nào có quorum | Nhóm không thể tiếp tục commit bình thường cho đến khi quorum được khôi phục hoặc phục hồi có kiểm soát |

Với cụm hai node, quorum là hai. Khi một node mất liên lạc, node còn lại không có đa số và không thể tự tiếp tục như một cụm có khả năng chịu lỗi. Có thể bổ sung một thành viên bỏ phiếu thứ ba ở failure domain khác; MySQL Router không phải thành viên bỏ phiếu của Group Replication.

### 2.2. Phát hiện lỗi và loại thành viên

Group Replication theo dõi thông điệp giữa các thành viên để phát hiện node không phản hồi. Nếu node bị xem là không thể liên lạc, nhóm có thể loại node đó khỏi membership sau thời gian chờ được cấu hình. Các biến như `group_replication_member_expel_timeout` và `group_replication_autorejoin_tries` ảnh hưởng hành vi phát hiện/loại thành viên và tự tham gia lại ở các phiên bản hỗ trợ.

Thời gian phát hiện lỗi là một quyết định vận hành. Thời gian quá ngắn có thể khiến node bị loại khi mạng chỉ chập chờn; thời gian quá dài có thể kéo dài thời gian hệ thống ở trạng thái suy giảm. Hãy đo độ trễ mạng giữa các failure domain, xem log của Group Replication và kiểm tra biến thực tế thay vì sao chép một giá trị mẫu.

Một node có thể bị loại do mạng lỗi dù MySQL vẫn chạy và dữ liệu trên disk vẫn nguyên vẹn. Khi kết nối trở lại, node có thể rejoin và nhận phần giao dịch còn thiếu qua distributed recovery hoặc incremental state transfer nếu binary log cần thiết còn sẵn. Nếu không thể bắt kịp bằng log, cần provisioning lại từ một nguồn dữ liệu nhất quán.

## 3. Phân biệt lỗi node và network partition

Hai tình huống có biểu hiện gần giống nhau từ góc nhìn của client nhưng cách xử lý khác nhau:

| Tình huống | Dấu hiệu | Câu hỏi cần xác minh |
|---|---|---|
| MySQL process dừng | Kết nối tới node thất bại; error log có thể ghi crash/shutdown | Node có thể khởi động lại an toàn không? Dữ liệu và binary log có phục hồi được không? |
| Máy chủ hoặc storage hỏng | Node không phản hồi, hệ điều hành hoặc volume không truy cập được | Có thể phục hồi instance hay cần thay node? Có backup/clone nhất quán không? |
| Network partition | Các node vẫn chạy nhưng một số cặp không liên lạc được | Phân vùng nào có quorum? Có node nào vẫn nhận ghi từ client trực tiếp không? |
| Network latency hoặc packet loss | Node liên tục timeout, membership thay đổi hoặc rejoin | Ngưỡng timeout có phù hợp không? Có congestion, MTU, firewall hoặc lỗi routing không? |
| DNS/proxy/service discovery lỗi | Node nội bộ có thể liên lạc nhưng client kết nối sai endpoint | Endpoint ghi có trỏ đúng primary hiện tại không? Cache DNS hoặc route có còn stale không? |

Không nên kết luận node đã chết chỉ vì ứng dụng không kết nối được. Một node bị cô lập khỏi nhóm có thể vẫn truy cập được từ một số mạng client. Nếu client tiếp tục ghi trực tiếp vào node đó, split-brain có thể xảy ra dù phần còn lại của cụm vẫn giữ quorum.

## 4. Split-brain hình thành như thế nào?

Split-brain xảy ra khi hai node hoặc hai phân vùng cùng nhận ghi như thể mình là primary có thẩm quyền. Một kịch bản điển hình với asynchronous replication:

```text
                 Ứng dụng
                    |
               Proxy / DNS
                    |
          Primary cũ: db-a
             /          \
            / replication \
           v               v
       Replica db-b    Replica db-c

     Mạng giữa db-a và db-b/db-c bị chia cắt

       db-a vẫn nhận ghi từ client cũ
       db-b được promote và cũng nhận ghi

       Hai lịch sử dữ liệu bắt đầu phân nhánh
```

Replication bất đồng bộ chỉ chuyển giao dịch sau khi primary commit. Nếu primary cũ không liên lạc được với replica, nó vẫn có thể hoạt động độc lập. Một quy trình failover chỉ đổi DNS hoặc proxy sang replica mà không fence primary cũ sẽ để lại đường ghi thứ hai.

Group Replication dùng quorum để ngăn phân vùng thiểu số commit như một nhóm hợp lệ; thành viên mất quorum sẽ không thể commit giao dịch theo nhóm. Ứng dụng kết nối trực tiếp tới node đó có thể vẫn mở được TCP session nhưng thao tác ghi sẽ không thành công khi node không còn quorum. Rủi ro split-brain xuất hiện nếu quản trị viên cưỡng ép membership sai cách, bootstrap một nhóm mới trong khi nhóm cũ vẫn hoạt động, hoặc để node cũ nhận ghi sau khi đã chuyển sang một cơ chế replication/primary độc lập.

### 4.1. Tác động của split-brain

- Cùng một khóa chính có thể được tạo hoặc cập nhật khác nhau trên hai nhánh.
- Hai nhánh có thể sinh ra các giao dịch GTID khác nhau; GTID không tự hợp nhất dữ liệu.
- Khi nối lại replication, applier có thể gặp duplicate key, missing row hoặc xung đột nghiệp vụ.
- Một số giao dịch được xác nhận ở một nhánh có thể không tồn tại ở nhánh được chọn làm primary cuối cùng.
- Việc hợp nhất thủ công có thể cần đối chiếu dữ liệu, replay nghiệp vụ hoặc khôi phục từ backup.

Không có một lệnh `RESET REPLICA` hay thao tác đổi source nào có thể tự giải quyết hai lịch sử ghi độc lập. Trước khi nối lại, phải xác định nhánh dữ liệu nào là nguồn sự thật và xử lý phần giao dịch riêng của nhánh còn lại.

## 5. Replication thường và quorum là hai cơ chế khác nhau

MySQL có nhiều cách triển khai replication; không phải cách nào cũng có quorum tích hợp.

| Cơ chế | Cách chuyển giao dịch | Có quorum membership tích hợp? | Điều cần làm khi failover |
|---|---|---|---|
| Asynchronous replication | Source commit trước, replica nhận và áp dụng sau | Không | Dùng orchestrator/HA manager, so sánh GTID và fence source cũ |
| Semisynchronous replication | Source chờ ít nhất một replica xác nhận đã nhận và ghi log sự kiện theo cấu hình | Không phải quorum bầu chọn primary | Vẫn cần chọn candidate, kiểm tra giao dịch và fence source cũ |
| Group Replication | Thành viên trao đổi và certification giao dịch theo membership của nhóm | Có | Khôi phục quorum, theo dõi election và bảo đảm client chỉ ghi vào primary hợp lệ |
| InnoDB Cluster | Dùng Group Replication cùng metadata và MySQL Router/AdminAPI | Có, qua Group Replication | Dùng AdminAPI/Router theo trạng thái cụm và kiểm tra endpoint ghi |

Semisynchronous replication có thể giảm nguy cơ mất giao dịch so với asynchronous replication trong một số failure mode, nhưng ACK nhận log không đồng nghĩa replica đã apply transaction. Nó cũng không tạo cơ chế majority election hoặc ngăn primary cũ tiếp tục nhận ghi.

Với asynchronous replication, một HA manager có thể dùng GTID để xác định candidate cập nhật nhất. Tuy nhiên, GTID set chỉ thể hiện lịch sử mà node đã nhận/commit; cần kiểm tra cả relay log đã nhận nhưng chưa apply, giao dịch còn trong binlog của source và RPO được chấp nhận.

## 6. Quan sát trạng thái Group Replication

Trên MySQL Group Replication, kiểm tra membership bằng Performance Schema:

```sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Các trạng thái thường gặp gồm `ONLINE`, `RECOVERING`, `OFFLINE`, `ERROR` và `UNREACHABLE`. Diễn giải trạng thái cùng membership view và log của từng thành viên. `RECOVERING` nghĩa là node đang đồng bộ dữ liệu; không nên đưa node vào phục vụ đọc/ghi chỉ vì tiến trình MySQL đã chạy.

Xem thêm trạng thái nhóm và primary:

```sql
SHOW GLOBAL STATUS LIKE 'group_replication%';
```

Trong single-primary mode, có thể kiểm tra primary hiện tại qua status variable:

```sql
SHOW GLOBAL STATUS LIKE 'group_replication_primary_member';
```

Nếu dùng MySQL Shell InnoDB Cluster, `cluster.status({extended: 1})` cung cấp thêm thông tin về topology, trạng thái instance và các cảnh báo mà AdminAPI nhận biết. Luôn chạy lệnh trên đúng đối tượng cluster và đối chiếu với trạng thái thực tế của từng MySQL instance.

Kiểm tra biến liên quan đến quorum, timeout và read-only:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'group_replication_member_expel_timeout',
  'group_replication_autorejoin_tries',
  'group_replication_unreachable_majority_timeout',
  'group_replication_exit_state_action',
  'group_replication_single_primary_mode',
  'read_only',
  'super_read_only'
);
```

Một số biến không tồn tại ở phiên bản cũ hoặc có giới hạn thay đổi khác nhau. Nếu câu lệnh không trả về một biến, kiểm tra tài liệu đúng bản phát hành và trạng thái plugin.

Nên theo dõi thêm:

- Số thành viên `ONLINE`, `RECOVERING`, `UNREACHABLE` và số lần membership thay đổi.
- Thời gian rejoin, distributed recovery và lượng dữ liệu phải truyền.
- Lỗi certification, transaction conflict và queue apply.
- Độ trễ mạng giữa các node, packet loss và thời gian phản hồi của storage.
- Replica lag, GTID set và endpoint mà ứng dụng đang sử dụng.

## 7. Phòng ngừa split-brain bằng fencing

**Fencing** là hành động bảo đảm một node cũ không thể tiếp tục gây thay đổi khi hệ thống đã chuyển quyền ghi sang node khác. Đây là lớp bảo vệ quan trọng trong failover, đặc biệt với asynchronous replication.

Các phương án fencing có thể kết hợp:

| Cơ chế | Ví dụ | Điểm cần kiểm tra |
|---|---|---|
| Power fencing | Tắt hoặc cô lập VM/instance qua control plane | Có xác nhận thao tác thành công và node cũ không tự khởi động lại không? |
| Network fencing | Chặn đường client, replication và quản trị tới node cũ bằng firewall/security group | Có đường mạng phụ hoặc kết nối trực tiếp nào còn mở không? |
| Storage fencing | Thu hồi quyền ghi vào volume dùng chung hoặc dùng cơ chế reservation phù hợp | Có node nào vẫn giữ quyền ghi cache hoặc volume không? |
| Proxy/service fencing | Loại node cũ khỏi writer endpoint, thu hồi route và credential ghi | Ứng dụng có thể bypass proxy để kết nối trực tiếp không? |
| MySQL read-only guard | Bật `read_only=ON` và `super_read_only=ON` trên node cũ | Tài khoản quản trị hoặc quy trình tự động có thể tắt guard không? |

`read_only` và `super_read_only` hữu ích như lớp phòng vệ trong MySQL, nhưng không thay thế fencing ở hạ tầng khi node cũ có thể được quản trị viên mở lại hoặc vẫn nhận kết nối qua một đường khác. Với failover tự động, cơ chế fencing phải có kết quả xác nhận rõ ràng trước khi mở quyền ghi trên candidate.

### 7.1. Endpoint ghi phải có một chủ sở hữu

Ứng dụng thường kết nối qua MySQL Router, proxy hoặc tên DNS dịch vụ. Khi primary thay đổi, endpoint ghi phải được cập nhật tới primary mới. Tuy nhiên, việc Router đổi route không tự chặn kết nối trực tiếp tới primary cũ.

Thiết kế tốt cần:

- Giới hạn mạng để ứng dụng chỉ kết nối qua endpoint được quản lý.
- Không phát tán địa chỉ primary vật lý vào cấu hình từng service.
- Có health check phân biệt node đang chạy với node đang được phép nhận ghi.
- Cập nhật writer endpoint sau khi candidate được xác nhận và primary cũ đã bị fence.
- Kiểm tra connection pool, DNS cache và các job nền để tránh tiếp tục dùng kết nối cũ.

## 8. Xử lý mất quorum trong Group Replication

Khi nhóm mất quorum, không cố ép các node độc lập tiếp tục nhận ghi. Hãy xác định membership và phân vùng còn có thể liên lạc trước.

### 8.1. Quy trình xử lý

1. **Xác định phạm vi lỗi:** kiểm tra node nào còn sống, đường mạng nào bị gián đoạn và có lỗi storage/process hay không.
2. **Đọc membership từ các node còn truy cập được:** so sánh `replication_group_members`, status variable, error log và trạng thái cluster trong MySQL Shell.
3. **Xác định phân vùng có đa số:** xác nhận node nào còn thuộc membership hợp lệ và có quorum. Không suy luận từ một health check đơn lẻ.
4. **Bảo vệ writer:** bảo đảm node ngoài phân vùng đa số không nhận ghi từ ứng dụng. Kiểm tra direct connection và quyền quản trị.
5. **Khôi phục mạng hoặc node:** sửa routing, firewall, packet loss, storage hoặc tiến trình MySQL. Theo dõi node rejoin và distributed recovery.
6. **Xác nhận nhóm ổn định:** kiểm tra đủ thành viên, trạng thái `ONLINE`, primary đúng và không có lỗi replication trước khi mở rộng lưu lượng.
7. **Đối chiếu dữ liệu và backup:** xác minh giao dịch quan trọng, GTID set, binary log retention và khả năng phục hồi.

Nếu toàn bộ nhóm đã dừng, cần xác định thành viên nào có lịch sử dữ liệu đầy đủ nhất trước khi khởi động lại nhóm. Với InnoDB Cluster, dùng quy trình AdminAPI phù hợp với trạng thái outage; không bootstrap một nhóm mới trong khi chưa chứng minh nhóm cũ đã dừng hoàn toàn.

### 8.2. Cẩn trọng với thao tác ép quorum

MySQL Group Replication có biến nâng cao `group_replication_force_members` để người vận hành có thể ép một membership mới trong một số tình huống mất quorum. Đây là biện pháp phục hồi có rủi ro cao. `group_replication_exit_state_action` cũng quyết định hành động của member sau khi rời nhóm; tùy phiên bản và cấu hình, member có thể chuyển sang read-only hoặc offline mode. Kiểm tra giá trị hiện tại để hiểu node sẽ phản ứng thế nào khi bị loại.

Chỉ cân nhắc sau khi:

- Đã xác định chính xác các thành viên sẽ nằm trong membership mới.
- Đã chứng minh các phân vùng khác không thể tiếp tục hoạt động hoặc nhận ghi.
- Đã fence node không thuộc nhóm được chọn.
- Đã dừng hoặc cô lập các node không được đưa vào membership mới để chúng không thể tiếp tục hoạt động với membership cũ.
- Đã so sánh GTID và đánh giá dữ liệu có thể bị bỏ lại ở phân vùng khác.
- Có kế hoạch khôi phục các node bị loại và đối chiếu dữ liệu.

Nếu hai phân vùng cùng bị ép thành hai nhóm độc lập, split-brain có thể xảy ra. Không dùng `group_replication_force_members` như cách xử lý timeout thông thường hoặc như một lệnh thử xem nhóm có chạy lại không.

Tương tự, `group_replication_bootstrap_group=ON` chỉ được dùng có kiểm soát khi khởi tạo một nhóm mới theo quy trình phù hợp. Chỉ một node được bootstrap nhóm tại một thời điểm và cần tắt cờ ngay sau khi nhóm được tạo. Không bật bootstrap trên nhiều node cùng lúc.

## 9. Failover với asynchronous replication

Với replication truyền thống, HA manager cần thực hiện các bước rõ ràng để tránh hai primary cùng nhận ghi. Một quy trình tham khảo:

1. Phát hiện primary lỗi bằng nhiều tín hiệu: kết nối MySQL, health check ứng dụng, host và mạng.
2. Xác định primary cũ có thể vẫn nhận ghi hay không. Nếu không thể chứng minh nó đã dừng, thực hiện fencing.
3. Thu thập `gtid_executed`, `Retrieved_Gtid_Set`, `Executed_Gtid_Set` và trạng thái receiver/applier từ các replica còn sống.
4. Chọn candidate có lịch sử giao dịch đầy đủ nhất theo GTID và RPO. Không chỉ chọn node có `Seconds_Behind_Source` nhỏ nhất.
5. Nếu relay log còn giao dịch đã nhận nhưng chưa apply, chờ hoặc xử lý chúng theo quy trình đã kiểm thử trước khi promote. Không bỏ qua giao dịch chỉ để giảm thời gian failover.
6. Bảo đảm candidate không có errant transaction chưa được giải thích.
7. Promote candidate theo quy trình quản trị, mở quyền ghi và chuyển writer endpoint sau khi primary cũ đã được fence.
8. Repoint các replica còn lại tới primary mới bằng GTID auto-position nếu topology đáp ứng điều kiện.
9. Kiểm tra dữ liệu, error log, replication status, backup và khả năng PITR sau failover.

Nếu primary cũ chỉ bị phân vùng mạng và sau đó xuất hiện lại, hãy giữ nó ở trạng thái không nhận ghi. So sánh GTID set của nó với primary mới, xử lý giao dịch riêng của từng nhánh và chỉ cho rejoin khi dữ liệu đã nhất quán.

## 10. Kịch bản minh họa

Một cụm Group Replication có ba node ở ba vùng:

```text
Region A: db-a  <---->  Region B: db-b
                  \       /
                   \     /
                   Region C: db-c
```

Kết nối từ `db-a` tới `db-b` và `db-c` bị gián đoạn, nhưng `db-b` và `db-c` vẫn liên lạc được. Nhóm hai node có đa số. `db-a` không được phép tiếp tục commit như một nhóm độc lập. Khi mạng phục hồi, `db-a` cần rejoin và áp dụng các giao dịch còn thiếu.

Trong một topology asynchronous khác, `db-a` là primary và `db-b`, `db-c` là replica. Mạng từ `db-a` tới ứng dụng vẫn hoạt động nhưng replication tới hai replica bị đứt. Một HA manager có thể quan sát replica không cập nhật và chọn promote `db-b`. Nếu không fence `db-a`, ứng dụng đang giữ connection pool cũ vẫn có thể ghi vào `db-a` trong khi các request mới ghi vào `db-b`. Đây là split-brain dù `db-b` đã được promote thành công.

Hai ví dụ có cùng biểu hiện mất liên lạc nhưng cơ chế an toàn khác nhau: Group Replication dùng quorum membership; asynchronous replication cần HA manager, chọn candidate và fencing.

## 11. Bài thực hành

Một hệ thống MySQL có ba node `mysql-1`, `mysql-2`, `mysql-3` và ứng dụng kết nối qua proxy. Hệ thống đang dùng Group Replication single-primary. Sau sự cố mạng:

- `mysql-1` không liên lạc được với hai node còn lại nhưng vẫn nhận được kết nối từ một subnet ứng dụng cũ.
- `mysql-2` và `mysql-3` liên lạc được với nhau và báo trạng thái nhóm có quorum.
- Proxy đã chuyển writer endpoint sang primary mới trong nhóm.
- Một batch job vẫn dùng địa chỉ IP trực tiếp của `mysql-1`.

Hãy xây dựng phương án xử lý:

1. Vì sao `mysql-1` vẫn chạy và nhận TCP connection không chứng minh nó có quyền nhận ghi?
2. Bạn sẽ kiểm tra membership, primary hiện tại và trạng thái node bằng những câu lệnh nào?
3. Cần làm gì để ngăn batch job tiếp tục ghi vào `mysql-1`? Vì sao chỉ đổi proxy chưa đủ?
4. Khi mạng phục hồi, cần kiểm tra những điều kiện nào trước khi `mysql-1` rejoin?
5. Nếu `mysql-1` có GTID không tồn tại trên primary mới, bạn sẽ điều tra ra sao?
6. Nếu toàn bộ ba node mất quorum, vì sao không được bật bootstrap hoặc ép quorum trên nhiều node cùng lúc?
7. Hãy đề xuất cách phân bố node, giám sát network và diễn tập failover để giảm nguy cơ tái diễn.

Phương án cần xác định rõ node có thẩm quyền nhận ghi, hành động fencing, điều kiện rejoin và cách xác minh dữ liệu sau sự cố.

## 12. Những lỗi vận hành thường gặp

- **Đồng nhất quorum với số node đang ping được:** quorum dựa trên membership và cơ chế bỏ phiếu, không phải chỉ dựa vào ICMP hoặc TCP health check.
- **Cho rằng hai node trong cụm hai node vẫn đủ để chịu một lỗi:** quorum của cụm hai node là hai, nên mất một node sẽ mất quorum.
- **Dùng MySQL Router như một cơ chế fencing:** Router điều hướng kết nối; nó không ngăn client kết nối trực tiếp tới server cũ.
- **Promote replica trước khi fence primary:** primary cũ có thể tiếp tục nhận ghi từ connection pool hoặc job chưa được chuyển endpoint.
- **Ép quorum khi chưa biết phân vùng còn lại:** có thể tạo hai nhóm độc lập cùng nhận ghi.
- **Chỉ xem `Seconds_Behind_Source`:** giá trị này không thay thế so sánh GTID, kiểm tra relay log và đánh giá giao dịch đã commit.
- **Cho node vừa rejoin nhận traffic ngay:** node có thể vẫn ở `RECOVERING` hoặc chưa đồng bộ xong; cần xác nhận trạng thái và dữ liệu.
- **Không diễn tập mất mạng:** failover chưa từng thử trong điều kiện thực tế có thể thất bại do DNS cache, quyền, firewall hoặc script tự động.

## Kết luận

Quorum giúp một nhóm node xác định liệu nó còn đủ thành viên để tiếp tục hoạt động sau lỗi. MySQL Group Replication dùng membership và quorum để hạn chế phân vùng thiểu số tiếp tục commit; asynchronous và semisynchronous replication cần cơ chế HA bên ngoài để chọn primary và fence node cũ. Phòng ngừa split-brain đòi hỏi một writer có thẩm quyền, endpoint được quản lý, fencing có xác nhận, so sánh GTID và quy trình rejoin rõ ràng. Hãy diễn tập cả lỗi node lẫn network partition, vì hai tình huống có thể trông giống nhau với ứng dụng nhưng tạo ra rủi ro dữ liệu rất khác nhau.
