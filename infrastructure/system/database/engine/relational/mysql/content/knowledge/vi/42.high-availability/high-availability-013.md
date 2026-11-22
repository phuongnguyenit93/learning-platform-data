# Đổi topology, bảo trì thành viên và điều kiện mất quorum

MySQL InnoDB Cluster dùng Group Replication để duy trì một nhóm máy chủ có cùng lịch sử transaction đã được xác nhận theo giao thức nhóm. Khi thêm hoặc gỡ thành viên, đổi chế độ single-primary/multi-primary hoặc đưa một máy chủ đi bảo trì, membership của nhóm thay đổi. Các thay đổi đó tác động trực tiếp đến quorum, khả năng commit transaction và khả năng chịu lỗi.

Quorum là điều kiện để một nhóm thành viên có thể thống nhất membership view và tiếp tục xử lý transaction theo giao thức Group Replication. Nếu một phân vùng mạng không còn đa số thành viên của view hiện tại, phân vùng đó mất quorum và không thể tiếp tục commit transaction như một nhóm hoạt động bình thường. Vì vậy, đổi topology cần được lên lịch theo số thành viên còn khỏe, kiểm tra trạng thái sau từng bước và có kế hoạch khôi phục khi mất quorum.

Bài học này thuộc phạm vi làm chủ MySQL từ thiết kế dữ liệu, transaction, kiểm soát đồng thời đến replication và vận hành sẵn sàng cao. Các ví dụ tập trung vào MySQL Group Replication và InnoDB Cluster được quản lý bằng MySQL Shell AdminAPI.

## 1. Membership view và quorum

Group Replication duy trì một danh sách thành viên đang tham gia nhóm, gọi là membership view. Khi thành viên tham gia, rời nhóm hoặc bị loại sau khi mất liên lạc, nhóm cập nhật view. Các thành viên cần thống nhất view để phối hợp thứ tự transaction và trạng thái nhóm.

Quorum yêu cầu số thành viên có thể giao tiếp và thống nhất phải lớn hơn một nửa số thành viên trong view. Với nhóm có N thành viên, số phiếu tối thiểu là:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Số thành viên có thể mất mà nhóm vẫn còn đa số là:

\[
F = \left\lfloor \frac{N-1}{2} \right\rfloor
\]

Một số cấu hình minh họa:

| Số thành viên trong view | Quorum cần có | Số lỗi thành viên có thể chịu |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |

Nhóm có ba thành viên chịu được một thành viên lỗi. Nếu còn hai thành viên giao tiếp với nhau, chúng vẫn tạo thành đa số. Khi chỉ còn một thành viên trong view ba nút, thành viên đó không thể tự quyết định thay cả nhóm.

Nhóm bốn thành viên vẫn chỉ chịu được một lỗi, giống nhóm ba thành viên, vì cần ba phiếu để đạt đa số. Vì vậy, thêm một nút vào nhóm ba không tự động tăng số lỗi có thể chịu. Muốn chịu được hai lỗi độc lập, cần ít nhất năm thành viên trong cùng nhóm.

### 1.1. Phân vùng mạng và thành phần đa số

Giả sử nhóm ba thành viên A, B và C bị chia thành hai phân vùng: A và B vẫn giao tiếp được với nhau, còn C bị cô lập.

~~~mermaid
flowchart TB
    subgraph Majority["Phân vùng có đa số: 2/3"]
      A["A - ONLINE"]
      B["B - ONLINE"]
      A --- B
      W["Có quorum"]
    end
    subgraph Minority["Phân vùng thiểu số: 1/3"]
      C["C - UNREACHABLE"]
      X["Mất quorum"]
    end
~~~

Phân vùng có hai thành viên giữ được đa số và có thể tiếp tục xử lý theo trạng thái nhóm. Thành viên đơn lẻ ở phân vùng còn lại không được phép tiếp tục commit như một nhóm độc lập. Khi mạng phục hồi, thành viên bị cô lập phải đồng bộ lại theo membership view và lịch sử transaction của nhóm hợp lệ.

Điểm quan trọng là quorum được tính theo membership view của nhóm, không phải số máy chủ mà người vận hành nhìn thấy đang bật nguồn. Một thành viên chưa được loại khỏi view có thể vẫn ảnh hưởng đến số phiếu cần thiết. Trong thời gian phát hiện lỗi và loại thành viên, trạng thái có thể khác với trạng thái sau khi view mới được hình thành.

### 1.2. Quorum khác với primary

Quorum là điều kiện về đa số thành viên; primary là vai trò ghi trong chế độ single-primary. Hai khái niệm liên quan nhưng không giống nhau:

- Nhóm có quorum và primary đang hoạt động: nhóm có thể xử lý ghi bình thường nếu các điều kiện khác đều đạt.
- Primary lỗi nhưng nhóm vẫn còn quorum: nhóm single-primary có thể bầu một primary mới.
- Primary còn chạy nhưng bị cô lập khỏi đa số: primary đó không thể tiếp tục ghi như thể nhóm vẫn khỏe mạnh.
- Nhóm mất quorum: các thành viên không thể tiếp tục commit transaction theo cơ chế nhóm, dù tiến trình MySQL trên từng máy vẫn còn chạy.

Không được khắc phục mất quorum bằng cách tùy tiện mở quyền ghi trên một thành viên thiểu số. Làm vậy có thể tạo hai nhánh dữ liệu và dẫn đến split-brain.

## 2. Single-primary và multi-primary ảnh hưởng đến topology

InnoDB Cluster thường sử dụng chế độ single-primary. Một thành viên giữ vai trò PRIMARY và nhận transaction ghi; các thành viên còn lại là SECONDARY, thường ở chế độ chỉ đọc. Khi primary lỗi, nhóm có quorum có thể bầu primary mới.

Trong chế độ multi-primary, nhiều thành viên có thể nhận ghi. Group Replication kiểm tra xung đột transaction thông qua cơ chế certification; transaction xung đột có thể bị rollback trên một hoặc nhiều thành viên. Multi-primary không có nghĩa là mọi loại workload đều mở rộng ghi tuyến tính.

| Tiêu chí | Single-primary | Multi-primary |
|---|---|---|
| Điểm nhận ghi | Một primary tại một thời điểm | Nhiều thành viên có thể nhận ghi |
| Chuyển vai trò | Có bầu primary mới khi primary lỗi và nhóm còn quorum | Không cần bầu một primary duy nhất |
| Xung đột ghi | Tập trung ghi giúp giảm xung đột giữa các node | Có thể phát sinh xung đột certification khi nhiều node sửa cùng dữ liệu |
| Định tuyến ứng dụng | Ghi đến primary; đọc có thể đến secondary nếu nghiệp vụ chấp nhận lag | Ứng dụng có thể ghi ở nhiều node nhưng phải thiết kế tránh xung đột |
| Trường hợp sử dụng | Phù hợp với đa số ứng dụng giao dịch thông thường | Chỉ phù hợp khi workload và dữ liệu được thiết kế để hạn chế xung đột |

Với multi-primary, nên thiết kế khóa chính duy nhất trên toàn nhóm, phân vùng quyền sở hữu dữ liệu hoặc định tuyến các nhóm bản ghi về node phù hợp. Cần kiểm tra tác động của auto-increment, thứ tự transaction, DDL và các transaction dài. Nếu nhiều node thường xuyên cập nhật cùng một hàng, tỷ lệ rollback do conflict có thể cao và hiệu năng giảm.

Có thể chuyển chế độ bằng MySQL Shell AdminAPI. Các lệnh sau được chạy trong MySQL Shell ở JavaScript mode với đối tượng cluster đã lấy từ metadata:

~~~javascript
var cluster = dba.getCluster();

cluster.switchToSinglePrimaryMode();
cluster.status({extended: 1});
~~~

Hoặc chuyển sang multi-primary khi ứng dụng đã sẵn sàng:

~~~javascript
cluster.switchToMultiPrimaryMode();
cluster.status({extended: 1});
~~~

Trước khi đổi mode, kiểm tra phiên bản, trạng thái các thành viên và tương thích workload. Không thay đổi biến nội bộ của Group Replication trực tiếp để thay thế AdminAPI. Sau khi chuyển, xác minh primary/secondary role, trạng thái read-only và cách MySQL Router hoặc ứng dụng định tuyến ghi.

## 3. Thêm và gỡ thành viên trong nhóm

Thêm thành viên có thể tăng năng lực đọc và khả năng chịu lỗi nếu thiết kế đúng số lượng. Gỡ thành viên có thể cần thiết khi thay máy chủ, nâng cấp hệ điều hành, thay đổi vùng triển khai hoặc loại một instance không còn an toàn.

Với InnoDB Cluster, nên sử dụng MySQL Shell AdminAPI để cập nhật membership và metadata. Một quy trình thêm instance thường gồm:

1. Chuẩn bị máy chủ mới với phiên bản MySQL tương thích, cấu hình mạng và TLS phù hợp.
2. Đặt server_id duy nhất; cấu hình Group Replication theo yêu cầu của AdminAPI.
3. Kiểm tra dung lượng đĩa, tài khoản quản trị, tài khoản recovery và các quyền cần thiết.
4. Xác định phương pháp recovery phù hợp: incremental từ binary log hay clone từ một thành viên donor.
5. Thêm instance bằng AdminAPI và theo dõi đến khi thành viên đạt trạng thái ONLINE.

Ví dụ trong MySQL Shell:

~~~javascript
var cluster = dba.getCluster();

cluster.addInstance("icadmin@db4.internal:3306", {
  recoveryMethod: "clone"
});

cluster.status({extended: 1});
~~~

Chuỗi kết nối chỉ là ví dụ, không chứa mật khẩu. Clone có thể thay thế dữ liệu trên instance mới, vì vậy cần xác nhận đúng máy đích và bảo đảm instance đó không chứa dữ liệu cần giữ lại. Nếu chọn incremental recovery, source phải còn giữ đầy đủ binary log cần thiết cho thành viên mới.

Khi gỡ một instance theo kế hoạch, hãy kiểm tra trước nhóm còn đủ quorum và đủ thành viên khỏe sau khi gỡ. Có thể dùng:

~~~javascript
cluster.removeInstance("icadmin@db3.internal:3306");
cluster.status({extended: 1});
~~~

Sau khi gỡ, xác minh thành viên không còn trong membership view và metadata cluster đã phản ánh đúng topology. Khi cần đưa lại instance đã bảo trì, kiểm tra dữ liệu và cấu hình trước, sau đó dùng addInstance hoặc rejoinInstance theo trạng thái thực tế.

Không gỡ một thành viên khi chưa xác định rõ nó là primary hay secondary, có đang nhận lưu lượng ứng dụng hay không, và số thành viên còn lại sẽ tạo quorum như thế nào. Nếu thành viên không thể liên lạc được, thao tác force removal cần được đánh giá riêng; không dùng force như lựa chọn mặc định để xử lý một lỗi kết nối chưa rõ nguyên nhân.

## 4. Lập kế hoạch bảo trì theo từng thành viên

Bảo trì rolling là thực hiện thay đổi lần lượt trên từng thành viên để nhóm tiếp tục hoạt động. Ví dụ, nâng cấp hệ điều hành, thay ổ đĩa, cập nhật MySQL hoặc đổi cấu hình mạng trên một cụm ba node.

~~~mermaid
flowchart TD
    S["Kiểm tra cluster khỏe mạnh"] --> P["Chọn một secondary"]
    P --> D["Drain lưu lượng và bảo trì"]
    D --> R["Khởi động và rejoin"]
    R --> V{"Thành viên ONLINE và dữ liệu bắt kịp?"}
    V -->|Có| N["Chọn thành viên kế tiếp"]
    V -->|Không| H["Dừng rollout, điều tra"]
    N --> C{"Còn thành viên cần bảo trì?"}
    C -->|Có| P
    C -->|Không| F["Kiểm tra toàn cụm và kết thúc"]
~~~

Quy trình đề xuất:

1. **Kiểm tra trước bảo trì:** dùng cluster.status({extended: 1}), xác nhận tất cả thành viên dự kiến hoạt động đều ONLINE, không có recovery kéo dài, lỗi certification hoặc lag bất thường.
2. **Đánh giá ngân sách lỗi:** tính quorum theo membership view và xác định nếu thêm một lỗi trong lúc bảo trì thì nhóm có mất quorum không.
3. **Chọn node:** ưu tiên secondary trong chế độ single-primary để giảm ảnh hưởng đến luồng ghi. Nếu phải bảo trì primary, chuyển primary theo quy trình phù hợp và xác nhận primary mới khỏe mạnh.
4. **Drain lưu lượng:** chuyển truy vấn đọc khỏi node, kiểm tra kết nối đang mở và bảo đảm ứng dụng không còn phụ thuộc vào instance sắp bảo trì.
5. **Đưa node ra khỏi nhóm khi cần:** với bảo trì dài hoặc thay đổi cấu hình lớn, dùng AdminAPI để removeInstance trước khi dừng máy.
6. **Thực hiện bảo trì:** nâng cấp, sửa phần cứng hoặc thay cấu hình trên một node.
7. **Khởi động và đưa node trở lại:** kiểm tra cấu hình, TLS, server_id, kết nối và recovery; dùng addInstance hoặc rejoinInstance theo trạng thái.
8. **Xác minh:** chờ node ONLINE, kiểm tra GTID, hàng đợi transaction và trạng thái ứng dụng trước khi chuyển sang node tiếp theo.

Ví dụ kiểm tra cluster trong MySQL Shell:

~~~javascript
var cluster = dba.getCluster();
cluster.status({extended: 1});
~~~

Trên máy chủ MySQL, có thể xem membership qua Performance Schema:

~~~sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Các trạng thái thường gặp gồm ONLINE, RECOVERING, OFFLINE, ERROR và UNREACHABLE. Chỉ đưa thành viên vào pool ứng dụng khi nó đã ONLINE và dữ liệu đã bắt kịp yêu cầu của workload. RECOVERING cho biết thành viên đang đồng bộ dữ liệu; không nên xem nó là một node sẵn sàng phục vụ đọc.

Trong cụm ba node, khi một node đã được gỡ hoặc bị loại khỏi view, hai node còn lại tạo thành nhóm hai thành viên và không còn chịu được thêm lỗi nào. Vì vậy, không bắt đầu bảo trì node thứ hai trước khi node thứ nhất đã trở lại khỏe mạnh hoặc topology đã được mở rộng phù hợp.

## 5. Thay đổi topology mà không làm mất quorum

Mỗi thao tác thêm hoặc gỡ thành viên làm thay đổi số phiếu của membership view. Cần đánh giá quorum ở cả trạng thái trước, trong và sau thay đổi.

Ví dụ cụm ba thành viên:

| Giai đoạn | Thành viên trong view | Quorum | Nhận xét |
|---|---:|---:|---|
| Ban đầu | 3 | 2 | Chịu được một lỗi |
| Gỡ một node để bảo trì | 2 | 2 | Không chịu được thêm lỗi |
| Node bảo trì rejoin và ONLINE | 3 | 2 | Khả năng chịu một lỗi được khôi phục |

Với cụm năm thành viên:

| Giai đoạn | Thành viên trong view | Quorum | Nhận xét |
|---|---:|---:|---|
| Ban đầu | 5 | 3 | Chịu được hai lỗi |
| Gỡ một node để bảo trì | 4 | 3 | Vẫn chịu được một lỗi |
| Gỡ thêm một node | 3 | 2 | Chỉ còn chịu được một lỗi |
| Gỡ tiếp một node | 2 | 2 | Không chịu được lỗi bổ sung |

Khi thiết kế topology, nên tính đến việc bảo trì đồng thời với sự cố bất ngờ. Nếu hệ thống cần duy trì khả năng chịu thêm một lỗi trong lúc bảo trì, số node và vùng lỗi phải được bố trí đủ. Năm node cùng một vùng nguồn điện hoặc cùng một miền lỗi mạng không nhất thiết tạo ra khả năng chịu lỗi hạ tầng tương ứng; cần phân tán failure domain.

Không chỉ đếm số node. Hãy kiểm tra:

- Các thành viên có nằm ở các host, rack, availability zone hoặc failure domain độc lập không?
- Network latency và độ ổn định có đáp ứng yêu cầu Group Replication không?
- Có đủ CPU, RAM, IOPS và dung lượng để thành viên còn lại nhận thêm tải khi một node bảo trì không?
- Thành viên donor có đủ binary log hoặc dung lượng để clone/recovery node mới không?
- MySQL Router và ứng dụng có định tuyến đúng khi thành viên rời hoặc quay lại không?

## 6. Điều kiện mất quorum và dấu hiệu nhận biết

Nhóm mất quorum khi thành phần còn liên lạc không có đa số thành viên trong membership view. Nguyên nhân thường gặp là:

- Nhiều thành viên cùng lỗi phần cứng, mất điện hoặc dừng dịch vụ.
- Phân vùng mạng khiến các node không thể hình thành thành phần đa số.
- Bảo trì nhiều node đồng thời vượt quá ngân sách lỗi của topology.
- Timeout hoặc cấu hình mạng khiến các thành viên bị loại khỏi view.
- Khởi động lại một phần nhóm sau sự cố mà không có kế hoạch bootstrap/reboot nhất quán.

Khi mất quorum, các thành viên không thể tiếp tục commit transaction theo giao thức nhóm. Ứng dụng có thể nhận lỗi ghi hoặc mất kết nối đến primary. Tùy cấu hình exit-state action và trạng thái instance, máy chủ có thể chuyển sang chế độ chỉ đọc, offline hoặc dừng. Cần kiểm tra cấu hình và trạng thái thực tế thay vì giả định mọi phiên bản đều có cùng phản ứng.

Có thể kiểm tra membership và trạng thái nhóm bằng:

~~~sql
SELECT
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;

SHOW STATUS LIKE 'group_replication%';
~~~

Trong MySQL Shell, cluster.status({extended: 1}) cung cấp góc nhìn cấp cluster, gồm trạng thái các instance và cảnh báo. Hãy thu thập log MySQL, log mạng và trạng thái từng node trước khi quyết định phục hồi.

### 6.1. Mất quorum không đồng nghĩa mất dữ liệu ngay lập tức

Mất quorum ngăn nhóm tiếp tục commit transaction mới theo cơ chế nhất quán của Group Replication. Các transaction đã được commit trước đó vẫn tồn tại trên các thành viên đã áp dụng chúng. Tuy nhiên, các node có thể có GTID set khác nhau nếu đã có sự cố hoặc transaction đang trong quá trình áp dụng. Cần xác định thành viên có lịch sử dữ liệu đầy đủ nhất trước khi phục hồi.

Không thể kết luận một node là mới nhất chỉ dựa vào timestamp hệ điều hành hoặc tên máy. Hãy so sánh GTID đã thực thi, transaction đã nhận, log và trạng thái recovery. Với topology nhiều kênh hoặc có transaction ngoài luồng, việc lựa chọn cần được chuyên gia vận hành đánh giá.

## 7. Phục hồi khi nhóm mất quorum

Phục hồi cần tránh tạo hai nhóm cùng nhận ghi. Có hai tình huống khác nhau:

**Một thành phần đa số vẫn tồn tại:** ưu tiên khôi phục kết nối mạng hoặc đưa thành viên cần thiết trở lại thành phần đa số. Không ép thành phần thiểu số tự thành lập nhóm mới trong khi đa số cũ vẫn có thể hoạt động.

**Toàn bộ cluster đã dừng hoặc không còn thành phần đa số có thể phục hồi:** xác minh toàn bộ node đã dừng hoặc được fence, chọn thành viên có transaction history đầy đủ nhất và dùng quy trình reboot cluster từ complete outage.

Với InnoDB Cluster, MySQL Shell có AdminAPI để reboot sau complete outage:

~~~javascript
dba.rebootClusterFromCompleteOutage();
~~~

Chỉ chạy khi cluster thực sự ở trạng thái complete outage và đã đánh giá các instance. Nếu cần chỉ định instance khởi tạo, chọn máy có GTID history đầy đủ nhất theo quy trình khôi phục. Sau khi cluster khởi động lại, kiểm tra từng member và đưa các node còn lại rejoin/recover theo trạng thái thực tế.

Không sử dụng dba.rebootClusterFromCompleteOutage() để thay thế việc xử lý một phân vùng mạng trong đó thành phần đa số vẫn đang hoạt động. Trước khi reboot, phải ngăn các node cũ tự khởi động và nhận ghi ngoài kế hoạch.

### 7.1. group_replication_force_members là biện pháp ngoại lệ

MySQL có biến cấu hình group_replication_force_members cho phép can thiệp vào membership trong tình huống mất quorum đặc biệt. Đây là cơ chế rủi ro cao vì có thể buộc một tập thành viên tạo view mới mà không có quy trình đồng thuận bình thường.

Chỉ cân nhắc khi:

1. Đã xác định chính xác mọi thành viên trong nhóm và tình trạng kết nối của chúng.
2. Đã xác nhận không còn thành phần đa số nào khác đang tiếp tục hoạt động.
3. Các node ngoài tập sẽ được force đã bị cô lập hoặc fence, không thể nhận ghi.
4. Tập thành viên được chọn có dữ liệu và transaction history đã được đánh giá.
5. Có runbook được phê duyệt, kế hoạch khôi phục và người chịu trách nhiệm rõ ràng.

Nếu force một phân vùng thiểu số trong khi phân vùng đa số cũ vẫn hoạt động, hai nhóm có thể cùng nhận ghi. Đây là split-brain và có thể dẫn đến mất hoặc xung đột dữ liệu khó khắc phục. Không dùng biến này như cách tăng quorum, không đưa một địa chỉ tùy ý vào danh sách và không dùng để thay cho kiểm tra GTID.

### 7.2. Bootstrap group chỉ dùng để tạo nhóm mới

group_replication_bootstrap_group là tùy chọn phục vụ khởi tạo một group mới. Nó không phải công tắc phục hồi chung để bật trên mọi node khi cluster mất quorum. Nếu bật bootstrap đồng thời trên nhiều thành viên, có thể tạo các nhóm độc lập và gây split-brain.

Với InnoDB Cluster, ưu tiên AdminAPI và runbook reboot từ complete outage. Nếu thao tác bootstrap thủ công trong một triển khai Group Replication không dùng AdminAPI, chỉ thực hiện trên một thành viên đã được chọn và tắt tùy chọn ngay sau khi bootstrap theo hướng dẫn đúng phiên bản.

## 8. Bảo trì, nâng cấp và thay đổi cấu hình

Một số thay đổi có thể tác động đến tính tương thích hoặc membership:

| Thay đổi | Cách chuẩn bị |
|---|---|
| Nâng cấp MySQL | Kiểm tra đường nâng cấp được hỗ trợ, tương thích phiên bản trong group và nâng từng node theo thứ tự được tài liệu phiên bản cho phép |
| Thay IP hoặc hostname | Cập nhật DNS, allowlist, local address và cấu hình kết nối; kiểm tra tất cả thành viên có thể liên lạc |
| Thay chứng chỉ TLS | Cài chứng chỉ và CA tương thích trên các node, kiểm tra hạn dùng và xác minh trước khi reload/restart |
| Thay phần cứng hoặc storage | Xác nhận backup, dung lượng recovery và năng lực các node còn lại |
| Thay đổi số lượng thành viên | Tính lại quorum và failure budget trước khi add/remove |
| Đổi single-primary/multi-primary | Đánh giá xung đột, ứng dụng, auto-increment và cách định tuyến trước khi đổi mode |

Với rolling upgrade, chỉ nâng một node tại một thời điểm và chờ node trở lại ONLINE, bắt kịp transaction rồi mới tiếp tục. Không tự ý trộn các phiên bản MySQL ngoài ma trận tương thích Group Replication của phiên bản đích.

Sau thay đổi cấu hình, kiểm tra các biến liên quan đến Group Replication, TLS, network address, group name và recovery channel. Cần lưu cấu hình trước thay đổi và biết cách rollback nếu node không thể rejoin.

## 9. Runbook kiểm tra trước và sau bảo trì

Trước khi bắt đầu:

1. Lấy trạng thái cluster bằng MySQL Shell và lưu kết quả.
2. Kiểm tra membership view, số member ONLINE và vai trò PRIMARY/SECONDARY.
3. Xác nhận quorum hiện tại và tính số node tối đa có thể mất trong giai đoạn bảo trì.
4. Kiểm tra GTID, hàng đợi applier, lỗi replication và tình trạng backup.
5. Xác định node sẽ bảo trì, luồng ứng dụng cần drain và cách quay lại cluster.
6. Xác nhận người vận hành có quyền truy cập các node còn lại nếu node bảo trì không khởi động.

Sau mỗi node:

1. Xác nhận node khởi động với server_id và địa chỉ đúng.
2. Kiểm tra Group Replication đã tham gia đúng group.
3. Chờ member state đạt ONLINE.
4. Kiểm tra transaction queue và GTID đã bắt kịp.
5. Chạy truy vấn đọc thử, kiểm tra Router và ứng dụng.
6. Chỉ khi mọi điều kiện đạt mới tiếp tục node kế tiếp.

Kết thúc:

- Xác nhận đủ thành viên dự kiến và quorum theo topology cuối cùng.
- Kiểm tra primary đúng vai trò và chỉ có endpoint ghi hợp lệ.
- Kiểm tra MySQL Router, connection pool và cảnh báo.
- Lưu phiên bản, cấu hình, thời gian bảo trì và kết quả kiểm tra.
- Cập nhật sơ đồ topology, danh sách thành viên và runbook nếu có thay đổi.

## 10. Tình huống thực hành

Một InnoDB Cluster có ba thành viên: db-a, db-b và db-c. db-a đang là primary. Nhóm vận hành cần nâng cấp hệ điều hành cho db-c, sau đó db-b. Trong lúc db-c đã được gỡ khỏi nhóm để bảo trì, đường mạng đến db-b gặp sự cố.

Hãy phân tích:

1. Sau khi db-c được gỡ khỏi membership view, còn bao nhiêu thành viên và quorum cần bao nhiêu phiếu?
2. Nếu db-a và db-b không thể giao tiếp, db-a có thể tiếp tục nhận ghi như một thành viên đơn lẻ không?
3. Vì sao không nên force db-a thành một nhóm một node nếu chưa xác minh db-b đã bị fence?
4. Nên khôi phục kết nối db-a/db-b hay reboot cluster từ complete outage trong tình huống này?
5. Điều kiện nào phải đạt trước khi tiếp tục bảo trì db-b?

Với membership view chỉ còn db-a và db-b, quorum là hai. Nếu chúng mất liên lạc, cả hai không có đa số. Vì db-c đang ngoài nhóm để bảo trì, cluster không có thành phần đa số. Cách xử lý ưu tiên là khôi phục liên lạc giữa db-a và db-b, xác minh membership và primary, sau đó chờ db-c rejoin. Không force một node riêng lẻ thành nhóm mới trong khi node kia có thể còn hoạt động và nhận ghi.

## 11. Câu hỏi tự kiểm tra

1. Quorum được tính như thế nào với nhóm ba, bốn và năm thành viên?
2. Vì sao nhóm bốn thành viên không chịu được nhiều lỗi hơn nhóm ba thành viên?
3. Quorum và primary khác nhau như thế nào trong single-primary mode?
4. Vì sao phải chờ một thành viên ONLINE và bắt kịp trước khi bảo trì node tiếp theo?
5. Trong phân vùng mạng 2/1 của nhóm ba node, thành phần nào có thể tiếp tục xử lý transaction?
6. Khi nào nên dùng dba.rebootClusterFromCompleteOutage()?
7. Rủi ro khi dùng group_replication_force_members trong khi thành phần đa số cũ vẫn hoạt động là gì?
8. Vì sao group_replication_bootstrap_group không được bật đồng thời trên nhiều node?

Đổi topology và bảo trì thành viên là công việc quản lý ngân sách lỗi của cluster. Cần biết membership view hiện tại, số phiếu cần để có quorum, vai trò primary, mức độ đồng bộ dữ liệu và trạng thái định tuyến ứng dụng. Khi mất quorum, phải khôi phục thành phần đa số hoặc xử lý complete outage theo runbook đã kiểm chứng; không tạo nhóm mới từ một phân vùng chưa được cô lập.
