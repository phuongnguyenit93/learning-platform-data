# GoldenGate và sao chép dữ liệu theo cơ chế CDC

## 1. Mục tiêu và bối cảnh sử dụng

Trong chương **Dữ liệu và phân tích** của module **CLOUD_PROVIDERS_ORACLE**, GoldenGate cung cấp một cách đưa thay đổi từ hệ thống giao dịch sang hệ thống đích mà không phải liên tục chép lại toàn bộ bảng. Trên Oracle Cloud Infrastructure, cơ chế này có thể phục vụ kho dữ liệu, báo cáo vận hành, tích hợp dữ liệu và di chuyển cơ sở dữ liệu.

Sau bài học, người học có thể:

- Giải thích CDC dựa trên transaction log và phân biệt với truy vấn tăng dần theo timestamp.
- Mô tả vai trò của Extract, trail, Distribution/Receiver và Replicat.
- Chuẩn bị nguồn, đích, kết nối và quyền cần thiết cho một luồng Oracle-to-Oracle.
- Phân biệt dữ liệu nền ban đầu với các thay đổi được áp dụng sau đó.
- Thực hành kiểm tra insert, update, delete, rollback và khôi phục sau khi dừng tiến trình.
- Đánh giá độ trễ, backlog, retention, tính đúng đắn và chi phí vận hành.

Bài học dùng mô hình **một nguồn ghi → một đích sao chép** làm nền tảng. Các kiến trúc hai chiều, đa nguồn hoặc gửi sự kiện sang nền tảng streaming cần thêm thiết kế riêng về định danh, thứ tự, xung đột và khả năng xử lý lại.

## 2. CDC là gì và vì sao cần transaction log?

### 2.1. Phân biệt trạng thái hiện tại và lịch sử thay đổi

Giả sử bảng `ORDERS` có một triệu dòng nhưng mỗi phút chỉ có vài nghìn thay đổi. Chép cả bảng thường xuyên gây tốn I/O, CPU, băng thông và thời gian đồng bộ. CDC, viết tắt của **Change Data Capture**, tập trung vào phần dữ liệu đã thay đổi.

Một cơ chế CDC dựa trên log đọc thông tin giao dịch từ nguồn, xác định các thay đổi thuộc phạm vi đã cấu hình và chuyển chúng tới đích. Với Oracle Database, GoldenGate sử dụng redo và các cơ chế capture phù hợp với cấu hình, phiên bản của nguồn.

Oracle GoldenGate là công cụ tích hợp và sao chép thay đổi giao dịch; OCI GoldenGate cung cấp khả năng này dưới dạng dịch vụ cloud được quản lý. Việc quản lý dịch vụ không thay thế trách nhiệm của khách hàng đối với mapping, quyền, khởi tạo dữ liệu và đối soát. [Giới thiệu OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/about-oracle-cloud-infrastructure-goldengate.html).

### 2.2. So sánh với cách đọc theo timestamp

| Cách tiếp cận | Đặc điểm cần cân nhắc |
| --- | --- |
| Chép toàn bộ bảng | Dễ hiểu nhưng phải xử lý nhất quán khi nguồn vẫn thay đổi |
| Đọc `WHERE updated_at > ...` | Phụ thuộc ứng dụng cập nhật timestamp đúng, khó phát hiện hard delete |
| Trigger ghi bảng thay đổi | Có thể bổ sung ngữ nghĩa nghiệp vụ nhưng làm tăng logic tại nguồn |
| CDC dựa trên transaction log | Theo dấu thay đổi giao dịch, cần cấu hình log và giữ được lịch sử cần đọc |

Ví dụ, một đơn hàng có thể đi từ `NEW` sang `PAID` rồi `CANCELLED` giữa hai lần polling. Đọc trạng thái hiện tại chỉ thấy `CANCELLED`; không tự tái tạo được hai lần chuyển trạng thái trước đó. Nếu dòng bị xóa hẳn, truy vấn theo timestamp trên bảng gốc cũng không còn dòng để trả về.

CDC không tự biến mọi thay đổi bảng thành một sự kiện nghiệp vụ. Một bản ghi `UPDATE` có thể là sửa thông tin, ghi nhận thanh toán hoặc tác vụ bảo trì. Khi bên nhận cần sự kiện như “thanh toán đã được chấp nhận”, ứng dụng có thể cần hợp đồng sự kiện hoặc mô hình outbox phù hợp, thay vì suy diễn chỉ từ tên bảng và cột.

### 2.3. “Gần thời gian thực” vẫn có độ trễ

Thay đổi phải đi qua capture, lưu trail, truyền tải và apply. Độ trễ phụ thuộc giao dịch nguồn, tải hệ thống, mạng và năng lực đích.

Một database đích dùng cho báo cáo có thể chậm hơn nguồn vài giây hoặc lâu hơn khi có backlog. Ứng dụng không nên mặc định một giao dịch vừa commit ở nguồn lập tức đọc được tại đích. Nếu nghiệp vụ cần đọc ngay dữ liệu vừa ghi, phải thiết kế đường đọc và cam kết nhất quán tương ứng.

## 3. Các thành phần của luồng GoldenGate

### 3.1. Luồng dữ liệu cơ bản

~~~mermaid
flowchart LR
    S["Oracle Database nguồn"] --> L["Redo / archived redo"]
    L --> E["Extract"]
    E --> T1["Trail nguồn"]
    T1 --> D["Distribution Path"]
    D --> R["Receiver"]
    R --> T2["Trail tại deployment đích"]
    T2 --> A["Replicat"]
    A --> T["Database đích"]
~~~

Sơ đồ mô tả mô hình có hai deployment. Với một deployment phục vụ cả capture và apply, Replicat có thể đọc trail trong cùng môi trường và không cần một đường Distribution/Receiver giữa hai deployment.

### 3.2. Vai trò của từng thành phần

| Thành phần | Vai trò |
| --- | --- |
| Extract | Capture thay đổi thuộc phạm vi nguồn |
| Trail | Lưu luồng thay đổi để bên sau đọc tiếp |
| Distribution Path | Chuyển trail giữa các deployment |
| Receiver | Nhận trail tại deployment đích |
| Replicat | Đọc trail và áp dụng vào đích |
| Checkpoint | Ghi nhận tiến độ phục vụ xử lý tiếp và khôi phục |

Distribution Path được dùng trong mô hình phân tán; phía nhận tiếp nhận dữ liệu qua Receiver Service. Không cần thêm đường này chỉ vì nguồn và đích là hai database khác nhau. [Distribution Path trong OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/replicate/add-a-distribution-path.html).

Trail tạo vùng đệm giữa các công đoạn. Nếu đích tạm ngừng, nguồn vẫn có thể được capture trong giới hạn năng lực và dung lượng còn lại. Vùng đệm này hữu hạn: nếu sự cố kéo dài, cần tính đến dung lượng trail và retention của log nguồn.

### 3.3. Deployment và connection trong OCI

Trong OCI GoldenGate, deployment là môi trường chạy các thành phần được chọn. Connection chứa thông tin kết nối đến nguồn hoặc đích. Connection cần được gán cho deployment trước khi sử dụng.

Loại deployment, công nghệ và phiên bản quyết định connection nào được hỗ trợ, cũng như vai trò source/target tương ứng. Không suy ra rằng mọi công nghệ có thể vừa capture vừa apply bằng cùng một deployment. [Connection của OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/explore-connections.html), [Các công nghệ được hỗ trợ](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/whats-supported.html).

Phân biệt hai giao diện:

- **Oracle Cloud Console:** quản lý tài nguyên deployment, connection, mạng, cấu hình dịch vụ và quan sát tài nguyên cloud.
- **Deployment Console:** quản lý quy trình capture/apply, mapping, trail và thông tin vận hành của GoldenGate.

Cách đăng nhập và vị trí các mục có thể khác giữa các phiên bản, loại deployment và chế độ xác thực. Khi thực hành, theo tài liệu của đúng deployment đang sử dụng.

## 4. Giao dịch, checkpoint và phạm vi bảo đảm

### 4.1. Commit và rollback

Với luồng transactional Oracle-to-Oracle được cấu hình phù hợp, đích nhận hiệu ứng của các giao dịch nguồn đã commit. Những thay đổi bị rollback không được biến thành dữ liệu nghiệp vụ đã commit ở đích.

Ví dụ:

~~~sql
UPDATE app_src.orders
SET status = 'PAID'
WHERE order_id = 1001;

ROLLBACK;
~~~

Sau khi nguồn rollback và luồng xử lý bắt kịp, đích không được đổi đơn `1001` thành `PAID` do giao dịch này.

Capture có thể đọc và lưu trạng thái xử lý liên quan đến giao dịch đang mở. Điều đó không đồng nghĩa người dùng tại đích được nhìn thấy một giao dịch chưa commit ở nguồn.

### 4.2. Thứ tự và tính nhất quán có phạm vi

Một giao dịch có thể sửa nhiều dòng và nhiều bảng. Nếu chỉ capture một phần bảng, kết quả đích chỉ phản ánh phần đã chọn, không phải toàn bộ hệ thống nghiệp vụ.

Tương tự, nếu chia dữ liệu sang nhiều Extract, trail hoặc Replicat độc lập, không tự giả định người đọc đích luôn quan sát một thứ tự toàn cục giữa mọi luồng. Cần xác định những bảng nào có phụ thuộc và chế độ apply nào phù hợp.

Các trường hợp cần xem xét riêng gồm:

- Bảng cha và bảng con nằm ở các luồng khác nhau.
- Một giao dịch lớn chứa rất nhiều thay đổi.
- Nhiều nguồn cùng ghi vào cùng khóa ở đích.
- Đích là message broker hoặc object store thay vì database giao dịch.
- Bên nhận gọi thêm API hoặc tạo tác dụng phụ ngoài transaction apply.

### 4.3. Checkpoint và khôi phục

GoldenGate dùng checkpoint file, checkpoint table và thông tin trong trail để quản lý tiến độ và phục hồi. Cấu hình checkpoint và khả năng giao dịch của đích là nền tảng để tránh áp dụng lại dữ liệu đã xử lý khi tiến trình restart. Không sửa tay checkpoint hoặc nội dung trail để làm tiến trình “chạy tiếp”. [Thành phần replication và checkpoint](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/overview-components-data-replication-oracle-goldengate.html).

Không mở rộng bảo đảm của một đường replication được hỗ trợ thành lời hứa rằng mọi tác dụng phụ bên ngoài đều xảy ra đúng một lần. Nếu sự kiện được đưa đến consumer riêng, bên đó vẫn cần thiết kế ghi nhận tiến độ, idempotency và xử lý retry theo giao thức của đích.

Các thao tác như đổi vị trí đọc thủ công, bỏ qua lỗi, thay đổi mapping hoặc nạp lại bảng cũng có thể làm dữ liệu khác với trạng thái mà cơ chế recovery thông thường dự kiến.

## 5. Chuẩn bị nguồn, đích và kết nối

### 5.1. Xác nhận cặp công nghệ trước khi triển khai

Trước khi tạo tiến trình, chốt một bảng thông tin:

| Hạng mục | Thông tin cần xác nhận |
| --- | --- |
| Nguồn | Loại database, phiên bản, cách triển khai, container/PDB |
| Đích | Loại database hoặc công nghệ nhận dữ liệu, phiên bản |
| GoldenGate | Loại deployment, công nghệ và phiên bản build |
| Dữ liệu | Danh sách bảng, khóa, kiểu dữ liệu, LOB và DDL liên quan |
| Topology | Một chiều, số nguồn/đích, số deployment và region |
| Mục tiêu | Độ trễ, khối lượng thay đổi, thời gian gián đoạn chịu được |
| Khởi tạo | Cách nạp dữ liệu nền và mốc nhất quán |
| Vận hành | Retention, checkpoint, cảnh báo và phương án đối soát |

Một hệ thống “kết nối được” chưa chắc hỗ trợ đầy đủ mọi kiểu dữ liệu hoặc thao tác mà ứng dụng dùng. Kiểm tra cả capture, apply, DDL và tính năng đặc biệt của bảng.

### 5.2. Logging và quyền tại Oracle Database nguồn

Với Oracle Database thông thường, cần đánh giá `ARCHIVELOG`, supplemental logging, cấu hình GoldenGate và quyền của tài khoản capture. Supplemental logging bổ sung thông tin giúp xác định đúng dòng và giá trị cần thiết để replicate. Ngoài mức tối thiểu của database, cần logging phù hợp tại schema hoặc bảng.

`FORCE LOGGING` là biện pháp quan trọng để tránh hoạt động `NOLOGGING` tạo khoảng trống dữ liệu cần capture. Mức logging phải theo đúng tính năng và phiên bản; tăng logging cũng có thể làm tăng redo. [Chuẩn bị Oracle Database cho GoldenGate](https://docs.oracle.com/en/middleware/goldengate/core/21.3/oracle-db/preparing-database-oracle-goldengate.html).

Một truy vấn kiểm tra tham khảo, do DBA chạy với quyền phù hợp trên Oracle Database thông thường:

~~~sql
SELECT log_mode,
       supplemental_log_data_min,
       force_logging
FROM v$database;
~~~

Truy vấn này không kiểm tra đầy đủ logging của từng bảng, quyền capture hay toàn bộ khả năng tương thích. Không cấp quyền DBA cho tài khoản GoldenGate chỉ để truy vấn chạy được.

Cần kiểm tra thêm:

- Tài khoản capture/apply theo hướng dẫn của đúng loại database.
- Phạm vi CDB/PDB và cách định danh object.
- Supplemental logging thực tế của các bảng được chọn.
- Khả năng truy cập redo/archived redo còn cần dùng.
- Các giao dịch đang mở lâu và dung lượng phục vụ mining.
- Thao tác DDL hoặc tính năng ứng dụng có thể ảnh hưởng capture.

Với Autonomous Database và các dịch vụ quản lý khác, quy trình chuẩn bị có thể khác Oracle Database tự quản lý. Không sao chép nguyên các câu `ALTER DATABASE` hoặc script cấp quyền giữa các mô hình. [Điều kiện capture từ Autonomous Database](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/adb-prerequisites-capturing-autonomous-database.html).

### 5.3. Khóa định danh và schema đích

Primary key hoặc một định danh ổn định giúp apply update/delete đúng dòng. Nếu không có khóa phù hợp, việc xác định dòng có thể tốn kém hoặc không đáp ứng cách xử lý mong muốn. Chọn `KEYCOLS` khi cần phải đi cùng thiết kế uniqueness và logging phù hợp; nó không tự tạo tính duy nhất cho dữ liệu.

Tại đích, chuẩn bị cấu trúc và kiểu dữ liệu tương thích. Xem xét index, constraint, trigger, sequence, identity và giá trị mặc định theo mô hình replication. Không mặc định một trigger ở đích sẽ có cùng vai trò như khi ứng dụng ghi trực tiếp.

Trong mô hình một chiều, nên kiểm soát để ứng dụng không tự sửa dữ liệu được Replicat quản lý. Nếu đích bị chỉnh độc lập, lỗi trùng khóa hoặc không tìm thấy dòng có thể là dấu hiệu dữ liệu đã lệch.

### 5.4. Mạng và các lớp xác thực

Tách ba lớp kiểm tra:

1. Quyền OCI để quản lý hoặc quan sát deployment và connection.
2. Quyền truy cập Deployment Console và quản lý tiến trình.
3. Tài khoản cùng quyền trong database nguồn/đích.

Có quyền trên tài nguyên OCI không tự cấp quyền đọc redo hoặc ghi bảng trong database.

Về mạng, phân biệt đường vào Deployment Console với đường từ connection tới database. OCI GoldenGate có các lựa chọn routing của connection như shared endpoint và dedicated endpoint; địa chỉ nguồn, DNS, route và NSG/security rule phải khớp cấu hình được chọn. [Kết nối mạng của OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/oci-goldengate-connectivity.html).

Nên kiểm tra theo thứ tự DNS → route → cổng listener → TLS/wallet → dịch vụ database → thông tin xác thực → quyền. Một lần kết nối TCP thành công chưa chứng minh tài khoản có đủ quyền capture hoặc apply.

Giữ mật khẩu và wallet trong cơ chế credential/secret phù hợp. Không đưa chúng vào ví dụ parameter file, log chia sẻ hoặc kho mã nguồn. Khi thay connection, đối chiếu cả việc đồng bộ cấu hình tới deployment và thay đổi mạng phát sinh.

## 6. Dữ liệu nền ban đầu và mốc nhất quán

### 6.1. CDC không tự bổ sung mọi dòng đã tồn tại

Nếu nguồn đã có dữ liệu trước thời điểm capture và đích đang rỗng, chỉ bắt đầu đọc thay đổi từ hiện tại sẽ bỏ lại các dòng không được thay đổi sau đó.

Ví dụ, nguồn có đơn `1001` trước khi Extract chạy. Nếu đơn này không còn cập nhật, CDC bắt đầu từ hiện tại không tự tạo nó ở đích. Nếu đơn được cập nhật trong khi đích chưa có dòng, apply có thể gặp lỗi không tìm thấy bản ghi.

**Initial load/instantiation** tạo trạng thái nền tại đích. CDC tiếp tục đưa các thay đổi cần thiết từ mốc nhất quán đó. Hai phần phải được phối hợp thành một phương pháp đã kiểm chứng. [Khái niệm instantiation](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/instantiate-instantiating.html).

### 6.2. Mô hình snapshot tại mốc S

Giả sử snapshot nguồn phản ánh các giao dịch đã commit tới mốc nhất quán `S`. Khi nạp snapshot này, đích đã có hiệu ứng của những giao dịch đó. Phần CDC cần tiếp tục từ ranh giới đúng để không bỏ sót hoặc apply trùng.

~~~text
T0: Chuẩn bị logging và capture theo phương pháp được chọn
T1: Ghi nhận mốc nhất quán S cho bản dữ liệu nền
T2: Nạp bản dữ liệu nền vào đích
T3: Bắt đầu apply phần CDC chưa nằm trong dữ liệu nền
T4: Đối soát, xử lý backlog và cho phép bên nhận sử dụng dữ liệu
~~~

Đây là mô hình logic. Cách lấy SCN, đăng ký Extract, lọc instantiation và đặt điểm bắt đầu phụ thuộc phương pháp nạp cùng phiên bản. Không thay toàn bộ quy trình bằng thao tác chọn “Now”.

Một giao dịch có thể bắt đầu trước `S` nhưng commit sau `S`. Capture phải có lịch sử đủ để xử lý giao dịch đó, dù snapshot chưa có hiệu ứng của nó. Đây là lý do phải xét registration SCN, giao dịch đang mở và retention, thay vì chỉ so sánh thời gian xuất file.

Hướng dẫn precise instantiation của Oracle phối hợp CDC Extract, mốc instantiation và tiến trình nạp ban đầu; phải dùng trọn phương pháp phù hợp, không ghép rời các bước từ nhiều hướng dẫn. [Precise instantiation với Initial Load Extract](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/instantiate-add-initial-load-extract-using-admin-client.html).

### 6.3. Chọn cách khởi tạo theo điều kiện vận hành

| Điều kiện | Hướng thiết kế |
| --- | --- |
| Hai bảng đều rỗng, chưa có giao dịch | Khởi động luồng trước mọi DML, phù hợp lab cơ bản |
| Có thể dừng ghi trong cửa sổ kiểm soát | Tạo bản nền và ranh giới CDC khi nguồn đã ổn định |
| Nguồn cần tiếp tục giao dịch | Dùng snapshot/export/initial load phối hợp với CDC và mốc nhất quán |
| Cần nạp lại một phần dữ liệu | Thiết kế resync theo bảng/phạm vi, đồng bộ với tiến trình đang chạy |

Không dùng tùy chọn xử lý collision để che mọi lỗi khởi tạo. Nếu một phương pháp cần cơ chế xử lý overlap, phải biết rõ phạm vi, điều kiện dùng và thời điểm ngừng. Sau khi nạp, vẫn phải đối soát dữ liệu.

## 7. Cấu hình luồng Oracle-to-Oracle trên OCI

### 7.1. Trình tự triển khai

Một trình tự tham khảo là:

1. Xác nhận hỗ trợ, nguồn/đích và phương pháp khởi tạo.
2. Chuẩn bị IAM, mạng, tài khoản database và logging.
3. Tạo deployment phù hợp với công nghệ.
4. Tạo connection nguồn và đích trong Oracle Cloud Console.
5. Gán connection cho deployment sử dụng chúng.
6. Kiểm tra kết nối và chuẩn bị checkpoint.
7. Tạo Extract với phạm vi capture rõ ràng.
8. Tạo Distribution Path nếu topology dùng deployment tách biệt.
9. Hoàn thành dữ liệu nền và cấu hình Replicat đúng ranh giới.
10. Khởi chạy, theo dõi và đối soát trước khi bàn giao.

Luồng tác vụ của OCI GoldenGate phân biệt tài nguyên cloud, gán connection và các tiến trình replication. [Các tác vụ cơ bản của OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/basic-taskflows.html).

### 7.2. Chọn bảng cho Extract

Trong Deployment Console, chọn loại Extract phù hợp với nguồn, credential, vị trí bắt đầu và trail. Đối với Oracle, Integrated Extract là một lựa chọn capture được cung cấp; cần theo đúng hướng dẫn của phiên bản deployment. [Tạo Extract cho Oracle Database](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/replicate/add-an-extract-for-oracle-ai-database.html).

Một **đoạn phạm vi capture** tối giản:

~~~text
TABLE APP_SRC.ORDERS;
~~~

Đoạn này không phải parameter file đầy đủ. Credential, trail, registration, encryption và các trường do giao diện sinh ra vẫn cần được cấu hình.

Nếu Extract làm việc trong phạm vi multitenant yêu cầu định danh container, tên nguồn có thể phải dùng dạng `PDB.SCHEMA.TABLE`. Dùng đúng phạm vi kết nối và định danh object theo capture mode, không đổi tên bảng theo suy đoán.

### 7.3. Mapping của Replicat

Đoạn mapping một bảng nguồn sang bảng đích:

~~~text
MAP APP_SRC.ORDERS, TARGET APP_DST.ORDERS;
~~~

`TABLE` chọn object cho capture; `MAP ... TARGET ...` chỉ định quan hệ nguồn–đích cho apply. Các phần lọc hoặc chuyển đổi cột phải được thiết kế thêm nếu schema khác nhau. [Tham chiếu TABLE và MAP](https://docs.oracle.com/en/database/goldengate/core/26/reference/table-map.html).

Bắt đầu bằng một bảng có khóa chính và kiểu dữ liệu đơn giản giúp nhìn rõ hành vi CDC. Chỉ mở rộng wildcard sau khi biết những bảng nào sẽ được capture, logging đã đáp ứng chưa và có vô tình đưa bảng quản trị vào luồng không.

### 7.4. Checkpoint và trạng thái tiến trình

Tạo hoặc chọn checkpoint table phù hợp cho Replicat theo hướng dẫn. Chọn đúng trail và vị trí bắt đầu, đặc biệt nếu đã có initial load hoặc trail cũ. [Tạo Replicat cho Oracle Database](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/replicate/add-a-replicat-for-oracle-ai-database.html).

Tên tiến trình phải đáp ứng giới hạn của loại process và phiên bản. Trong ví dụ, có thể dùng tên ngắn như `EORD` và `RORD` để dễ phân biệt.

Sau khi khởi chạy, kiểm tra report, checkpoint và thống kê capture/apply. Trạng thái `RUNNING` cho biết tiến trình đang hoạt động; nó không tự chứng minh không có dữ liệu thiếu, mapping sai hoặc một phần thay đổi đã bị cấu hình bỏ qua.

## 8. Thực hành CDC với một bảng đơn hàng

### 8.1. Điều kiện và mục tiêu

Dùng hai Oracle Database hoặc hai môi trường nguồn/đích phù hợp đã được cấp cho lab. Giả định schema nguồn là `APP_SRC` và schema đích là `APP_DST`. DBA đã chuẩn bị logging, tài khoản GoldenGate và quyền theo đúng loại database.

Bài thực hành dùng dữ liệu tổng hợp. Không cần mở cấu hình hai chiều hoặc dùng bảng sản xuất.

Mục tiêu là chứng minh:

- DML đã commit tại nguồn được phản ánh ở đích.
- Giao dịch rollback không thay đổi trạng thái đích.
- Dừng Replicat làm đích chậm lại và có thể tiếp tục từ checkpoint.
- Trạng thái cuối cùng được đối chiếu theo khóa và nội dung.

### 8.2. Tạo hai bảng rỗng

Chạy DDL sau trong schema nguồn và schema đích, mỗi bên một lần:

~~~sql
CREATE TABLE orders (
    order_id    NUMBER(12)       PRIMARY KEY,
    customer_id NUMBER(12)       NOT NULL,
    status      VARCHAR2(20 CHAR) NOT NULL,
    amount      NUMBER(12, 2)    NOT NULL,
    changed_at  TIMESTAMP(6)     DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Trong schema nguồn, bảng là `APP_SRC.ORDERS`; trong schema đích, bảng là `APP_DST.ORDERS`. Bài lab tạo cấu trúc riêng ở hai bên, không dựa vào DDL replication.

Xác nhận cả hai bảng chưa có dòng, không có phiên ứng dụng ghi vào bảng và mọi bước chuẩn bị đã hoàn tất. Tắt auto-commit trong SQL client cho các phần cần kiểm tra giao dịch.

Khởi động Extract và Replicat với phạm vi đúng bảng, đúng trail và điểm bắt đầu phù hợp khi nguồn vẫn rỗng. Chỉ tạo DML sau khi tiến trình đã sẵn sàng.

Cách này loại bỏ nhu cầu nạp dữ liệu nền trong lab. Với bảng đã có dữ liệu, phải áp dụng phương pháp initial load ở phần trước, không dùng thiết kế rỗng này để bỏ qua bước khởi tạo.

### 8.3. Insert và commit

Tất cả DML dưới đây chạy tại **nguồn**:

~~~sql
INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1001, 501, 'NEW', 125.00);

INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1002, 502, 'NEW', 80.00);

COMMIT;
~~~

Sau khi luồng bắt kịp, truy vấn tại đích:

~~~sql
SELECT order_id, customer_id, status, amount
FROM app_dst.orders
ORDER BY order_id;
~~~

Kết quả mong đợi là hai dòng `1001` và `1002` với nội dung tương ứng. Đối chiếu thống kê tiến trình và các lỗi nếu có, không chỉ nhìn một chỉ số lag.

Tiếp tục tạo một dòng:

~~~sql
INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1003, 503, 'NEW', 30.00);

COMMIT;
~~~

Đích phải xuất hiện đơn `1003` sau khi apply, trong giới hạn độ trễ của môi trường lab.

### 8.4. Update đã commit

~~~sql
UPDATE app_src.orders
SET status = 'PAID',
    changed_at = SYSTIMESTAMP
WHERE order_id = 1001;

COMMIT;
~~~

Tại đích, đơn `1001` phải chuyển từ `NEW` sang `PAID`, còn `amount` vẫn là `125.00`.

DML này cho thấy CDC chuyển thay đổi lên trạng thái đã tồn tại. Đích phải có dữ liệu nền đúng; nếu không có đơn `1001` từ trước, một cập nhật đơn lẻ không phải lúc nào cũng tạo được đúng trạng thái mong muốn.

### 8.5. Thay đổi rồi rollback

~~~sql
UPDATE app_src.orders
SET amount = 999.00,
    changed_at = SYSTIMESTAMP
WHERE order_id = 1002;

ROLLBACK;
~~~

Sau khi xác nhận nguồn rollback, kiểm tra đơn `1002` tại đích. Giá trị phải vẫn là `80.00`.

Nếu công cụ SQL đã tự commit, bài kiểm tra không còn kiểm tra rollback. Vì vậy, cần ghi rõ chế độ giao dịch của client và không trộn DDL vào giữa phép thử này.

### 8.6. Delete đã commit

~~~sql
DELETE FROM app_src.orders
WHERE order_id = 1002;

COMMIT;
~~~

Khi luồng bắt kịp, đơn `1002` phải không còn ở đích trong mapping replication thông thường đang dùng.

Đây là một khác biệt dễ quan sát với cách polling chỉ dựa trên timestamp của bảng gốc: sau hard delete, dòng không còn trong bảng nguồn để một truy vấn tăng dần trả về.

### 8.7. Giao dịch có nhiều thay đổi

~~~sql
INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1004, 504, 'NEW', 50.00);

UPDATE app_src.orders
SET status = 'PAID',
    amount = 31.00,
    changed_at = SYSTIMESTAMP
WHERE order_id = 1003;

COMMIT;
~~~

Đối chiếu sau khi apply hoàn tất: đơn `1004` tồn tại và đơn `1003` có `status='PAID'`, `amount=31.00`.

Bài lab này kiểm tra một transaction trên một luồng và một bảng. Không mở rộng kết quả thành bảo đảm quan sát nguyên tử giữa nhiều target hoặc nhiều Replicat độc lập.

### 8.8. Tạm dừng apply và khởi chạy lại

Trong Deployment Console, dừng Replicat theo thao tác vận hành được hỗ trợ; giữ Extract tiếp tục chạy nếu môi trường còn đủ tài nguyên và dung lượng.

Tại nguồn, thực hiện:

~~~sql
UPDATE app_src.orders
SET status = 'PAID',
    changed_at = SYSTIMESTAMP
WHERE order_id = 1004;

COMMIT;
~~~

Khi Replicat vẫn dừng, đích chưa nhận cập nhật này. Kiểm tra Extract, trail và vị trí apply để nhận diện nơi luồng đang chờ.

Khởi động lại Replicat từ checkpoint hiện tại theo quy trình bình thường. Không chọn bắt đầu từ “Now” hoặc đặt lại vị trí chỉ để giảm lag hiển thị.

Sau khi backlog được xử lý, đơn `1004` tại đích phải có `status='PAID'`. Dữ liệu trước đó vẫn phải đúng và không xuất hiện dòng trùng khóa.

### 8.9. Đối soát trạng thái cuối

Tạm ngừng tạo DML cho phạm vi lab, chờ luồng xử lý hết những thay đổi đã tạo rồi chạy truy vấn chi tiết ở cả nguồn và đích:

~~~sql
SELECT order_id, customer_id, status, amount
FROM orders
ORDER BY order_id;
~~~

Kết quả mong đợi:

| order_id | customer_id | status | amount |
| --- | --- | --- | --- |
| 1001 | 501 | PAID | 125.00 |
| 1003 | 503 | PAID | 31.00 |
| 1004 | 504 | PAID | 50.00 |

Đơn `1002` đã bị xóa; thay đổi `999.00` bị rollback không xuất hiện trong trạng thái cuối.

Có thể kiểm tra thêm:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM orders;
~~~

Kết quả là `3` dòng và tổng `206.00`. Count và sum chỉ là kiểm tra nhanh: hai tập dữ liệu khác nhau vẫn có thể có cùng số dòng và tổng tiền. Khi nghiệm thu, phải đối chiếu khóa và các trường cần thiết tại mốc nhất quán.

`changed_at` là thời điểm do ứng dụng ghi, không phải đồng hồ đo commit/apply chính xác. Đừng dùng một mình nó để chứng minh cam kết độ trễ.

### 8.10. Bàn giao kết quả và kết thúc lab

Ghi lại phiên bản deployment, phạm vi bảng, tên tiến trình, checkpoint/lag quan sát được, thời gian thực hiện và kết quả từng phép thử.

Nếu phải giải phóng môi trường, lưu kết quả cần thiết rồi dừng/xóa đúng tài nguyên lab theo trách nhiệm được giao. Không xóa connection, checkpoint, logging hoặc database dùng chung mà chưa xác định các luồng còn phụ thuộc.

## 9. Giám sát độ trễ, backlog và tính đúng đắn

### 9.1. Quan sát từng công đoạn

| Câu hỏi | Dấu hiệu cần xem |
| --- | --- |
| Capture có theo kịp nguồn không? | Tiến độ Extract, capture lag, giao dịch mở lâu |
| Trail có được truyền không? | Trạng thái path/receiver, vị trí đọc/ghi, lỗi mạng |
| Apply có theo kịp không? | Replicat lag, checkpoint, thông lượng và lỗi đích |
| Có nguy cơ hết vùng đệm không? | Tốc độ tăng trail, dung lượng và retention |
| Đích có dữ liệu đúng không? | Đối soát nội dung, lỗi bỏ qua, phạm vi mapping |
| Bên dùng dữ liệu có thấy đủ mới không? | Đo thời gian đầu cuối bằng cơ chế phù hợp |

OCI GoldenGate tích hợp metric trong namespace `oci_goldengate`. Metric và dimension có thể khác giữa deployment/process/pipeline và phiên bản; chọn đúng tài nguyên thay vì sao chép tên metric từ một loại triển khai khác. [Metric của OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/oracle-cloud-infrastructure-goldengate-metrics.html).

Nếu cần đo độ trễ đầu cuối, đánh giá heartbeat được hỗ trợ cho đường replication. Metric capture hoặc apply cục bộ không tự đại diện cho toàn thời gian từ commit tại nguồn đến dữ liệu sẵn sàng cho ứng dụng đích.

Đồng thời cần theo dõi thời gian cập nhật metric và tình trạng thiếu dữ liệu. Một bảng điều khiển không có điểm đo mới không có nghĩa lag bằng không.

### 9.2. Thiết kế ngưỡng theo mục tiêu thực tế

Ví dụ, đội dữ liệu giả định muốn dữ liệu đơn hàng thường chậm dưới 30 giây. Cần xác định ngưỡng cảnh báo, khoảng thời gian đánh giá và cách xử lý đợt tải cao; không chỉ đặt một con số duy nhất trên dashboard.

Cảnh báo nên xem cả:

- Tiến trình dừng hoặc abend.
- Lag tăng liên tục trong khi nguồn có thay đổi.
- Checkpoint không tiến lên.
- Trail tăng nhanh hoặc tiến gần giới hạn dung lượng.
- Lỗi kết nối, quyền, schema hoặc apply.
- Đối soát phát hiện thiếu/khác dữ liệu dù lag thấp.

Ngưỡng 30 giây ở đây là điều kiện minh họa, không phải SLA hoặc khả năng mặc định của dịch vụ.

### 9.3. Backlog chỉ giảm khi năng lực xử lý vượt lượng mới

Giả sử backlog đang có `B` thay đổi, nguồn tiếp tục tạo `λ` thay đổi mỗi giây và apply xử lý `μ` thay đổi mỗi giây. Với tốc độ ổn định và cùng cách đếm, có thể ước lượng:

~~~text
Nếu μ > λ:
    Thời gian bắt kịp ≈ B / (μ - λ)

Nếu μ <= λ:
    Không bắt kịp được khi tải mới vẫn tiếp tục ở mức đó
~~~

Ví dụ, `B=2.000.000`, `λ=1.000/giây` và `μ=1.600/giây` cho thời gian gần `3.333` giây, khoảng `55,6` phút.

Đây là mô hình đơn giản. Giao dịch lớn, lock, độ phức tạp từng dòng, index và phụ thuộc giữa transaction có thể làm tốc độ thay đổi đáng kể. Không dùng phép tính này như cam kết vận hành khi chưa đo workload thực tế.

### 9.4. Đối soát tại mốc có ý nghĩa

Nếu nguồn vẫn đang ghi, hai truy vấn count chạy ở hai thời điểm khác nhau có thể lệch dù replication không lỗi. Chọn phương pháp so sánh phù hợp:

- Dừng ghi có kiểm soát trong một phạm vi nhỏ khi thực hành.
- Dùng snapshot hoặc mốc giao dịch tương ứng khi công nghệ hỗ trợ.
- Chia theo phạm vi khóa hoặc thời gian đã ổn định.
- So sánh checksum/nội dung với cùng quy tắc chuẩn hóa.
- Ghi rõ các dòng đang thay đổi và phạm vi chưa thể kết luận.

Khi mapping có filter hoặc transformation, đích được kỳ vọng phản ánh kết quả của mapping, không nhất thiết giống byte với nguồn. Đối soát phải dựa trên hợp đồng dữ liệu đó.

## 10. Retention, hiệu năng và chi phí

### 10.1. Giữ đủ lịch sử cho từng công đoạn

Có ít nhất hai loại lịch sử cần quản lý:

- Redo/archived redo mà capture còn cần đọc hoặc cần để phục hồi.
- Trail mà các tiến trình phía sau còn cần đọc hoặc cần để tiếp tục.

Nếu Extract đã dừng lâu và log nguồn cần thiết bị xóa, thêm OCPU cho deployment không tái tạo được lịch sử đã mất. Nếu Replicat cần một trail đã bị purge, phải xử lý như sự cố phục hồi dữ liệu.

Một mô hình dự trù trail tham khảo:

~~~text
Dung lượng tối thiểu dự trù
≈ Tốc độ trail đo được × Thời gian gián đoạn dự kiến × Hệ số dự phòng
~~~

Với `5 MiB/giây`, `2 giờ` và hệ số `1,5`:

~~~text
5 × 7.200 × 1,5 = 54.000 MiB ≈ 52,7 GiB
~~~

Đây là tính toán cho một vùng đệm minh họa, chưa gồm các bản trail ở deployment khác, overhead, nhiều consumer hoặc thời gian bắt kịp sau khi khôi phục. Tốc độ trail phải được đo từ workload; không đồng nhất nó với kích thước bảng hay toàn bộ redo.

Retention nên bao gồm thời gian phát hiện, phản ứng, sửa lỗi và xử lý backlog. Nếu chỉ dự trù thời gian tiến trình dừng, hệ thống vẫn có thể thiếu lịch sử trong lúc bắt kịp.

### 10.2. Xác định nút nghẽn trước khi tăng tài nguyên

Nếu capture chậm, kiểm tra nguồn, mining, giao dịch dài và cấu hình logging. Nếu truyền trail chậm, kiểm tra path, băng thông, độ trễ và lượng dữ liệu cần fan-out. Nếu apply chậm, kiểm tra target CPU/I/O, lock, index và chế độ Replicat.

Parallelism có thể tăng thông lượng nhưng phải phù hợp chế độ apply và phụ thuộc dữ liệu. Tách mọi bảng thành nhiều luồng chỉ để tăng số tiến trình có thể làm phức tạp tính nhất quán và phục hồi.

Hướng dẫn sizing của OCI GoldenGate yêu cầu xét workload, số nguồn/đích, loại tiến trình và năng lực đã đo. Không có một số OCPU cố định phù hợp mọi luồng CDC. [Sizing và capacity planning](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/oci-goldengate-sizing-and-capacity-planning-guide.html).

Autoscaling hoặc nâng năng lực deployment cũng không sửa được một target bị lock lâu, thiếu index cần thiết hay bị giới hạn kết nối.

### 10.3. Các khoản cần dự trù

Khi lập ngân sách, xem cả tài nguyên GoldenGate, vùng lưu trail, database nguồn/đích, backup, kết nối mạng, log và vận hành. Topology nhiều deployment hoặc nhiều đích làm tăng số đường dữ liệu và phạm vi giám sát.

Supplemental logging và capture vẫn có chi phí tài nguyên ở nguồn. Thay đổi nhỏ ở bảng lớn chưa chắc nhẹ nếu row rất rộng, có LOB hoặc giao dịch chứa số lượng thay đổi lớn.

Đối với lab, ưu tiên phạm vi nhỏ và giải phóng tài nguyên theo trách nhiệm sau khi giữ kết quả. Đối với sản xuất, đặt cảnh báo dung lượng và sử dụng tài nguyên để có thời gian phản ứng trước khi vùng đệm cạn.

## 11. Xử lý sự cố theo đường đi dữ liệu

### 11.1. Khoanh vùng trước khi thay đổi vị trí

Khi đích thiếu dữ liệu, ghi lại:

1. Bảng, khóa và giao dịch cụ thể.
2. Nguồn đã commit hay chưa, thời điểm và mốc giao dịch nếu có.
3. Bảng có nằm trong phạm vi `TABLE`/`MAP` không.
4. Extract đã đọc qua vị trí liên quan chưa.
5. Trail đã tới nơi Replicat đọc chưa.
6. Replicat có lỗi, bị filter hoặc đang chờ gì không.
7. Dữ liệu có bị người hoặc ứng dụng sửa lại tại đích không.

Sau đó mới quyết định biện pháp. Đổi checkpoint hoặc chọn một điểm bắt đầu mới trước khi hiểu vị trí mất dữ liệu có thể phá khả năng đối chiếu.

### 11.2. Một số hiện tượng thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Không tạo được connection | DNS, route, endpoint, listener, TLS/wallet, tài khoản |
| Connection hoạt động nhưng Extract không chạy | Capture mode, quyền, logging, registration và phạm vi container |
| Không có thay đổi mới ở đích | Commit, phạm vi bảng, Extract, path, Replicat và filter |
| Trùng khóa khi apply | Initial load overlap, dữ liệu đích bị ghi riêng, replay hoặc mapping |
| Update/delete không tìm thấy dòng | Thiếu dữ liệu nền, dòng bị sửa/xóa ở đích, lệch khóa |
| Capture lag tăng | Nguồn, mining, giao dịch lâu, năng lực capture |
| Apply lag tăng | Lock, I/O, index, tài nguyên đích và chế độ apply |
| Tiến trình chạy nhưng nội dung sai | Mapping, chuyển đổi, lỗi đã bỏ qua, thay đổi schema |
| Restart yêu cầu trail/log đã mất | Retention, purge, lịch sử gián đoạn và phương án resync |
| Lỗi sau DDL | Khả năng hỗ trợ, metadata, schema đích và kế hoạch nâng cấp |

Report và log có thể chứa SQL, tên schema hoặc dữ liệu nhạy cảm. Khi chia sẻ để điều tra, dùng nơi lưu được kiểm soát và giữ đủ bản gốc cần thiết.

### 11.3. Không xử lý lỗi dữ liệu bằng cách bỏ qua hàng loạt

Một lỗi trùng khóa hoặc không tìm thấy dòng có thể cho biết nguồn–đích đã lệch. Bỏ qua lỗi giúp tiến trình chạy tiếp nhưng có thể để lại dữ liệu không đúng.

Khi cần resync:

- Xác định bảng/phạm vi bị ảnh hưởng.
- Lưu bằng chứng và mốc xử lý hiện tại.
- Xác định nguyên nhân trước khi nạp lại.
- Chọn phương pháp tạo dữ liệu nền và ranh giới CDC mới.
- Thực hiện theo quy trình đã kiểm chứng cho topology đó.
- Đối soát sau phục hồi và ghi rõ phần còn chưa xác minh.

Không truncate bảng đích đang được dùng rồi khởi động lại từ checkpoint cũ với giả định CDC sẽ tự dựng lại mọi dòng.

## 12. DDL, hai chiều và sử dụng dữ liệu đích

### 12.1. Thay đổi schema cần được điều phối

Thêm cột, đổi kiểu dữ liệu, thay khóa hoặc rename bảng có thể ảnh hưởng capture và apply. Kiểm tra khả năng DDL replication theo đúng cặp source/target, phiên bản và loại object.

Nếu không dùng DDL replication, phối hợp thay đổi nguồn và đích để Replicat không gặp schema không tương thích. Ngay cả khi hỗ trợ DDL replication, các script ứng dụng, quyền, job và đối tượng ngoài phạm vi vẫn cần được quản lý.

Không coi việc thêm `TABLE schema.*` là đã tự hoàn thành mọi khía cạnh schema evolution.

### 12.2. Hai chiều cần thêm thiết kế xung đột

Trong cấu hình hai chiều, cùng một khóa có thể được sửa ở hai phía. Cần giải quyết định danh, chống vòng lặp, ownership, conflict detection/resolution và ảnh hưởng của đồng hồ nếu dùng chính sách dựa trên thời gian.

Một lab một chiều chạy đúng không chứng minh active-active sẽ đúng. Nên có quy tắc nghiệp vụ rõ về nơi được quyền sửa từng loại dữ liệu, thay vì chỉ nối thêm một luồng ngược.

### 12.3. Phân biệt replication với backup và physical standby

| Nhu cầu | Điều cần đánh giá |
| --- | --- |
| Sao chép bảng, chọn lọc và tích hợp dị thể | GoldenGate với mapping/capture/apply được hỗ trợ |
| Khôi phục về một thời điểm trước lỗi hoặc xóa nhầm | Backup và cơ chế phục hồi phù hợp |
| Database standby và chuyển vai trò | Kiến trúc HA/DR như Data Guard theo yêu cầu cụ thể |
| Lưu mọi chuyển trạng thái cho phân tích lịch sử | Thiết kế lưu lịch sử hoặc sự kiện, không chỉ bảng hiện tại |

Một lệnh xóa nhầm hợp lệ ở nguồn có thể được sao chép sang đích. Vì vậy, một bảng đích luôn giống nguồn không tự thay thế bản backup có thể phục hồi trước thao tác đó.

Tương tự, bảng đích được apply theo kiểu trạng thái hiện tại không tự trở thành kho lưu mọi phiên bản lịch sử. Muốn phân tích từng thay đổi phải thiết kế cách lưu nhận và mô hình dữ liệu tương ứng.

### 12.4. Dùng trong di chuyển database

GoldenGate có thể hỗ trợ giảm thời gian dừng ghi bằng cách nạp nền trước rồi bắt kịp thay đổi. Khi cutover, cần kiểm soát ghi nguồn, đợi các giao dịch liên quan hoàn tất, xác nhận apply tới mốc cần thiết và đối soát trước khi đổi ứng dụng.

Cần chuẩn bị thêm đối tượng và cấu hình ngoài phạm vi replicate như sequence, quyền, job, trigger, kết nối và tích hợp. Sau khi đích đã nhận ghi mới từ ứng dụng, việc quay lại nguồn cũ không còn là thao tác đổi endpoint đơn giản; phải có phương án dữ liệu cho rollback.

Một luồng CDC vận hành tốt cần đồng thời có **ranh giới khởi tạo đúng, tiến độ có thể phục hồi, khả năng giữ đủ lịch sử và bằng chứng đối soát**. Những yếu tố này giúp dùng OCI GoldenGate để cấp dữ liệu phân tích hoặc di chuyển hệ thống mà vẫn đánh giá được độ mới và độ tin cậy của dữ liệu đích.
