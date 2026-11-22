# Release Update, OPatch, datapatch và kiểm tra sau vá

Vá Oracle Database gồm hai phần cần được quản lý như một quy trình thống nhất: cập nhật phần mềm trong Oracle Home và cập nhật các đối tượng SQL bên trong database. **OPatch** áp dụng hoặc hoàn tác patch ở lớp Oracle Home; **datapatch** đồng bộ các thay đổi SQL mà patch yêu cầu vào database. Hai bước có mục đích khác nhau, và việc chạy OPatch thành công chưa chứng minh database đã được vá hoàn chỉnh.

Một quy trình patch an toàn cần xác định đúng patch cho phiên bản/platform, đọc README đi kèm, kiểm tra inventory và xung đột, chuẩn bị backup/rollback, áp dụng binary patch, chạy datapatch khi database ở trạng thái phù hợp, rồi kiểm tra cả inventory lẫn SQL patch registry. Với RAC, Data Guard và CDB/PDB, cần tính thêm trạng thái từng node, role database và từng pluggable database.

## 1. Release Update và các loại patch Oracle

Oracle phát hành nhiều loại bản vá. Tên gọi và lịch phát hành có thể thay đổi theo release, nhưng các nhóm dưới đây thường gặp trong vận hành database.

### 1.1. Release Update (RU)

Release Update là gói cập nhật tích lũy cho một release line của Oracle Database. RU thường được phát hành định kỳ, tích hợp nhiều bản sửa lỗi và cập nhật bảo mật đã được chọn cho release đó.

Một RU thường chứa các thay đổi ở Oracle Home và có thể kèm SQL changes cần áp dụng vào database bằng datapatch. RU mới thường tích lũy nội dung của các RU trước trong cùng release line, nhưng phải xác nhận nội dung và khả năng áp dụng theo README của patch cụ thể.

RU là đơn vị cập nhật thông dụng cho nhiều môi trường Oracle Database hiện đại. Khi lập kế hoạch, cần chọn RU được hỗ trợ cho đúng release, platform, architecture và Oracle Home.

### 1.2. Release Update Revision (RUR) và các thuật ngữ lịch sử

Một số release từng có khái niệm Release Update Revision (RUR) hoặc các nhánh cập nhật khác. Chính sách và tên gọi phụ thuộc release line và thời kỳ phát hành. Không nên mặc định rằng mọi phiên bản hiện tại đều có cùng mô hình RU/RUR.

Hãy kiểm tra tài liệu Oracle cho release đang vận hành. Không chọn patch chỉ dựa trên tên gần giống hoặc dựa trên một hướng dẫn dành cho release khác.

### 1.3. Security patch và Critical Patch Update

Oracle công bố các cập nhật bảo mật theo lịch và có thể cung cấp nội dung bảo mật trong RU hoặc các gói patch tương ứng. Critical Patch Update (CPU) là thuật ngữ được sử dụng trong lịch cập nhật bảo mật của Oracle; trong nhiều release hiện đại, khách hàng áp dụng nội dung bảo mật thông qua RU phù hợp.

Cần đọc advisory và patch README để biết patch nào xử lý lỗ hổng, release nào bị ảnh hưởng, điều kiện áp dụng và liệu có cần cập nhật Java VM component hoặc middleware liên quan hay không.

### 1.4. One-off/interim patch

One-off hoặc interim patch là patch được cung cấp để xử lý một lỗi cụ thể hoặc một nhu cầu đặc thù. Nó có thể phụ thuộc vào RU hiện tại, platform, component và các patch đã cài.

Không tự cài một one-off lên Oracle Home có RU khác với điều kiện patch yêu cầu. Nếu patch conflict với RU hoặc one-off đang có, cần tìm merge patch hoặc hướng dẫn thay thế từ Oracle Support. Không xóa patch hiện tại khỏi inventory để ép cài patch mới.

### 1.5. Patch cho OJVM, Grid Infrastructure và các thành phần khác

OJVM patch, Grid Infrastructure patch, client patch và database RU có thể có yêu cầu riêng. Một Oracle Home có thể chứa nhiều thành phần và patch bundle khác nhau. Quy trình áp dụng cho Database Home không nhất thiết giống Grid Infrastructure Home.

Trong môi trường RAC hoặc cluster, patch có thể yêu cầu OPatchAuto hoặc một trình tự patch node cụ thể. Không thay opatch bằng opatchauto hay ngược lại theo phỏng đoán; làm theo README của patch và hướng dẫn cho đúng component.

### 1.6. So sánh nhanh

| Loại | Mục đích | Điểm cần kiểm tra |
|---|---|---|
| Release Update | Cập nhật tích lũy cho release line | Release/platform, RU level, prerequisites, SQL actions |
| Security update/CPU content | Xử lý lỗ hổng bảo mật | Advisory, mức độ ảnh hưởng, RU hoặc patch được khuyến nghị |
| One-off/interim | Sửa lỗi cụ thể | Bug number, conflict, merge patch và điều kiện RU |
| OJVM patch | Vá thành phần Oracle Java VM | Thành phần OJVM, trình tự và yêu cầu riêng |
| Grid Infrastructure patch | Vá clusterware/ASM/GI | OPatchAuto, rolling capability, node order |
| Client patch | Vá Oracle client home | Home đích, ứng dụng sử dụng client và tương thích driver |

## 2. Phân biệt OPatch và datapatch

Hai công cụ xử lý hai lớp khác nhau:

- **OPatch** quản lý patch ở Oracle Home: thay thế/cập nhật binary, thư viện, file cấu hình hoặc thành phần phần mềm theo nội dung patch.
- **datapatch** chạy các SQL action đi kèm patch để cập nhật database dictionary, package, component metadata và các đối tượng SQL liên quan.

Mô hình tổng quát:

    Patch archive / patch directory
                |
                v
       Read patch README
                |
                v
        OPatch apply
                |
                v
       Oracle Home binaries
                |
                v
       Start / open database
                |
                v
          datapatch
                |
                v
       SQL changes in database
                |
                v
       Post-patch verification

OPatch ghi nhận patch trong Oracle Home inventory. datapatch ghi nhận SQL patch action trong registry của database. Hai nguồn trạng thái phải được đối chiếu.

### 2.1. Vì sao OPatch thành công chưa đủ?

Một RU có thể gồm binary fixes và SQL changes. Nếu chỉ chạy OPatch mà chưa chạy datapatch khi patch yêu cầu, Oracle Home có thể đã ở RU mới nhưng database dictionary chưa được cập nhật tương ứng.

Hệ quả có thể là:

- SQL patch registry chưa có patch mới.
- Component hoặc package trong database chưa được cập nhật.
- Cảnh báo version mismatch khi khởi động hoặc chạy công cụ quản trị.
- Một số lỗi chỉ xuất hiện khi sử dụng tính năng liên quan đến SQL action của patch.

Ngược lại, chỉ chạy datapatch mà Oracle Home chưa có binary patch tương ứng cũng không tạo ra một bản vá hoàn chỉnh. datapatch phải chạy từ Oracle Home đã được patch và dùng đúng database/Oracle Home cần đồng bộ.

### 2.2. Inventory và SQL registry là hai nguồn khác nhau

| Nơi kiểm tra | Công cụ/view | Cho biết |
|---|---|---|
| Oracle Home inventory | opatch lsinventory | Patch binary đang được ghi nhận trong Home |
| SQL patch registry | DBA_REGISTRY_SQLPATCH | SQL patch action đã được áp dụng/rollback trong database |
| Component registry | DBA_REGISTRY | Trạng thái và version của database components |
| Database version banner | V$VERSION | Phiên bản Oracle Database đang chạy |
| CDB/PDB state | V$PDBS, CDB_* views | Trạng thái và thông tin từng container |

Không dùng một nguồn để thay thế nguồn còn lại. Kiểm tra sau vá cần xác nhận Oracle Home inventory đúng và SQL patch registry ở đúng container có trạng thái thành công.

## 3. Chuẩn bị trước khi vá

Patch production là thay đổi có ảnh hưởng lớn tới database availability và khả năng tương thích. Trước khi chạy lệnh, cần có một change plan được review và cửa sổ bảo trì phù hợp.

### 3.1. Xác định chính xác Oracle Home và database

Ghi nhận:

- Oracle Database release và RU hiện tại.
- Platform, architecture và edition.
- Oracle Home path của instance cần vá.
- SID, database name, DBID và DB_UNIQUE_NAME.
- CDB/PDB hay non-CDB.
- RAC hay single instance.
- Data Guard primary/standby nếu có.
- Grid Infrastructure Home và các Oracle Home khác trên máy.
- OJVM hoặc component đặc biệt có được cài không.

Không dựa riêng vào biến ORACLE_HOME trong shell nếu máy có nhiều Oracle Home. Kiểm tra environment và process đang chạy để xác định đúng Home. Một lỗi phổ biến là chạy OPatch ở Home của client hoặc Grid Infrastructure thay vì Database Home.

Có thể kiểm tra từ SQL:

    SELECT
        name,
        dbid,
        db_unique_name,
        open_mode,
        database_role,
        cdb
    FROM v$database;

Kiểm tra instance:

    SELECT
        instance_name,
        host_name,
        version,
        status
    FROM v$instance;

### 3.2. Đọc README của patch

README đi kèm patch là nguồn chỉ dẫn chính cho patch đó. Đọc toàn bộ các phần:

- Supported products/releases/platforms.
- Prerequisites và required OPatch version.
- Conflicting patches và superseded patches.
- Required component hoặc one-off patches.
- Apply/rollback procedure.
- Shutdown/startup requirements.
- Rolling hoặc non-rolling instructions.
- Datapatch instructions.
- Post-installation steps.
- Known issues và special notes.

Không dùng lệnh của một patch README cũ cho patch mới chỉ vì tên công cụ giống nhau. Cú pháp, thứ tự và prerequisite có thể thay đổi.

### 3.3. Kiểm tra patch download và checksum

Tải patch từ kênh Oracle được phép, xác minh patch number, platform và checksum theo hướng dẫn Oracle. Không dùng file patch lấy từ nguồn không đáng tin cậy.

Giữ nguyên cấu trúc thư mục patch sau khi giải nén. Không đổi tên hoặc di chuyển các file bên trong nếu README yêu cầu cấu trúc cụ thể.

### 3.4. Backup và khả năng rollback

Trước khi patch:

- Xác nhận RMAN backup gần nhất hoàn tất và có thể truy cập.
- Kiểm tra backup control file, SPFILE và archived redo log theo chính sách.
- Xác nhận có bản sao hoặc snapshot Oracle Home theo quy trình hỗ trợ của tổ chức.
- Ghi lại opatch lsinventory trước vá.
- Lưu cấu hình listener, tnsnames, sqlnet, password file và file cấu hình quan trọng.
- Ghi nhận trạng thái database, PDB, services, ASM, cluster và Data Guard.
- Xác định cách rollback binary patch và xử lý SQL patch.
- Xác định tiêu chí go/no-go và người chịu trách nhiệm.

Rollback patch không đồng nghĩa với restore database từ RMAN. OPatch rollback trả Oracle Home về trạng thái trước patch theo cơ chế patch; datapatch cần đồng bộ SQL registry theo trạng thái binary; RMAN restore/recovery là một phương án khôi phục database khác và có tác động lớn hơn.

### 3.5. Kiểm tra không gian và quyền

Kiểm tra dung lượng filesystem chứa Oracle Home, patch staging directory, temporary directory, log và FRA nếu có bước database liên quan. Xác nhận user thực hiện patch có quyền đọc/ghi đúng thư mục và có quyền vận hành cần thiết.

Không giải nén patch vào Oracle Home đang hoạt động nếu README yêu cầu staging ở nơi khác. Tránh để patch archive, log và backup lấp đầy filesystem trong lúc bảo trì.

## 4. Kiểm tra Oracle Home inventory bằng OPatch

OPatch là utility đi kèm Oracle Home, thường nằm ở:

    $ORACLE_HOME/OPatch/opatch

Trên Windows, executable thường là opatch.bat trong thư mục OPatch. Đường dẫn và tên file phụ thuộc platform.

### 4.1. Kiểm tra phiên bản OPatch

    $ORACLE_HOME/OPatch/opatch version

So sánh với phiên bản OPatch tối thiểu được README của patch yêu cầu. Nếu cần nâng cấp OPatch, lấy gói OPatch tương ứng từ Oracle Support, backup thư mục OPatch hiện tại theo quy trình, rồi cập nhật đúng Oracle Home.

Không giả định OPatch mới nhất luôn tương thích với mọi release/platform. Dùng phiên bản được Oracle hỗ trợ cho patch và Oracle Home cụ thể.

### 4.2. Liệt kê inventory

    $ORACLE_HOME/OPatch/opatch lsinventory

Chi tiết hơn:

    $ORACLE_HOME/OPatch/opatch lsinventory -detail

Lệnh này hiển thị thông tin Oracle Home và các patch được inventory ghi nhận. Lưu output trước khi vá để có baseline và dùng đối chiếu sau vá.

Nếu inventory báo lỗi, không tiếp tục apply patch. Trước hết xác định inventory pointer, quyền, Oracle Home path và tính nhất quán của oraInventory theo hướng dẫn Oracle.

### 4.3. Inventory không phải danh sách SQL patch trong database

lsinventory đọc inventory của Oracle Home. Nó không chứng minh mọi PDB đã chạy datapatch. Cần query DBA_REGISTRY_SQLPATCH sau bước datapatch.

### 4.4. Kiểm tra inventory qua SQL khi cần

Một số phiên bản hỗ trợ package/view DBMS_QOPATCH để truy vấn inventory từ database. Quyền và cách sử dụng phụ thuộc phiên bản. Đây là công cụ bổ sung; không thay thế lệnh OPatch trên Oracle Home khi cần xác minh patch binary.

## 5. Kiểm tra prerequisite và conflict

Trước khi apply, xác nhận patch phù hợp với Oracle Home và không có conflict chưa được xử lý.

### 5.1. Kiểm tra prerequisite

Patch README có thể yêu cầu:

- Một RU hoặc patch nền cụ thể.
- OPatch version tối thiểu.
- Oracle Home ở trạng thái phù hợp.
- Một số component hoặc option đã được cài.
- Patch cũ phải được rollback trước.
- Một số one-off phải được thay bằng merge patch.
- Các bước chuẩn bị riêng cho RAC/Data Guard/OJVM.

Không bỏ qua prerequisite chỉ vì lệnh apply có vẻ chạy được.

### 5.2. Kiểm tra conflict bằng OPatch

OPatch có lệnh prerequisite để kiểm tra conflict giữa patch mới và inventory hiện có. Ví dụ cú pháp thường gặp trên nhiều release:

    $ORACLE_HOME/OPatch/opatch prereq CheckConflictAgainstOHWithDetail \
      -phBaseDir /stage/patch_directory

Đường dẫn patch directory phải trỏ tới thư mục chứa metadata patch phù hợp. Cú pháp và prerequisite cụ thể cần xác nhận với README và phiên bản OPatch.

Nếu conflict xuất hiện:

1. Xác định patch ID đang gây conflict.
2. Kiểm tra patch nào superseded hoặc có merge patch.
3. Đọc README và tài liệu Oracle Support cho conflict đó.
4. Xác định có thể rollback one-off cũ hay phải dùng patch thay thế.
5. Thử lại trên Oracle Home clone hoặc môi trường staging.
6. Chỉ apply khi conflict được giải quyết theo hướng dẫn chính thức.

Không tự xóa record inventory, sửa XML inventory bằng tay hoặc xóa file patch để vượt conflict.

### 5.3. Kiểm tra patch đã cài

Nếu patch đã có trong inventory, xác định đó là đúng patch ID, đúng version và đúng Oracle Home. Tránh chạy lại apply mà không hiểu trạng thái. Nếu patch apply dở dang, xem log OPatch và xử lý theo hướng dẫn recovery của Oracle.

## 6. Áp dụng patch bằng OPatch

Quy trình apply phụ thuộc loại patch. Ví dụ dưới đây minh họa một patch được áp dụng thủ công bằng OPatch theo README; không dùng nguyên mẫu nếu patch yêu cầu OPatchAuto hoặc quy trình rolling khác.

### 6.1. Dừng các thành phần cần thiết

Với in-place patching, README có thể yêu cầu dừng database instance, listener, application connection hoặc các process sử dụng Oracle Home. Trong RAC, thứ tự dừng node và instance phụ thuộc rolling capability và hướng dẫn patch.

Xác nhận không còn process giữ file binary cần thay thế. Không tự kill process theo tên nếu chưa xác định owner và tác động.

### 6.2. Chạy OPatch apply

Ví dụ:

    cd /stage/patch_directory
    $ORACLE_HOME/OPatch/opatch apply

OPatch kiểm tra inventory, prerequisite và thực hiện cập nhật file trong Oracle Home. Đọc output và log để xác định trạng thái hoàn tất.

Không coi việc shell trả exit code 0 là đủ nếu output có warning hoặc yêu cầu post-installation step. Lưu log và patch ID.

### 6.3. Silent mode

Một số quy trình tự động có thể sử dụng silent mode nếu README hỗ trợ:

    $ORACLE_HOME/OPatch/opatch apply -silent

Silent mode không bỏ qua prerequisite hay thay thế review. Hệ thống tự động phải kiểm tra exit code, log và trạng thái inventory sau lệnh.

### 6.4. Kiểm tra sau OPatch

Sau khi apply:

    $ORACLE_HOME/OPatch/opatch lsinventory

Xác nhận patch ID và version xuất hiện trong đúng Oracle Home. Kiểm tra log OPatch để chắc chắn không có bước apply thất bại hoặc rollback một phần.

Nếu có nhiều Oracle Home, chạy inventory cho từng Home theo kế hoạch. Không suy luận rằng vá Database Home đồng nghĩa đã vá Grid Infrastructure Home hoặc client home.

## 7. datapatch: cập nhật SQL trong database

datapatch là công cụ chạy SQL patch actions để đồng bộ database với patch đã cài trong Oracle Home. Công cụ thường nằm trong Oracle Home, dưới thư mục OPatch/datapatch theo layout của release.

Ví dụ:

    $ORACLE_HOME/OPatch/datapatch -verbose

Cần chạy bằng môi trường Oracle Home đã được patch và kết nối tới database phù hợp. Quyền kết nối và trạng thái database phải đáp ứng yêu cầu của patch README.

### 7.1. Điều kiện trước khi chạy

Trước datapatch:

- Binary patch đã được áp dụng thành công trong Oracle Home.
- Database đã được khởi động bằng Oracle Home đã patch.
- Database ở trạng thái mở theo yêu cầu của datapatch/README.
- CDB root và các PDB cần patch đã được mở ở trạng thái phù hợp, thường là READ WRITE.
- Listener/service và kết nối local hoạt động.
- Không có thao tác DDL hoặc patch khác đang chạy xung đột.
- Có đủ dung lượng cho data dictionary, tablespace hệ thống và log.

Trong CDB, datapatch có thể áp dụng SQL patch cho root và các PDB đang mở phù hợp. PDB đóng hoặc không khả dụng có thể chưa được cập nhật trong lần chạy đó; cần mở PDB và chạy lại datapatch theo hướng dẫn của release để hoàn tất.

Không giả định một lần chạy ở CDB root tự động đồng nghĩa mọi PDB đều đã được vá. Kiểm tra registry ở từng container.

### 7.2. Chạy datapatch

Ví dụ:

    $ORACLE_HOME/OPatch/datapatch -verbose

verbose giúp hiển thị chi tiết tiến trình. Ghi lại output và đường dẫn log mà datapatch báo. Nếu lệnh fail, đọc log để xác định PDB, SQL action hoặc component gây lỗi.

Không chạy datapatch từ Oracle Home cũ hoặc Home khác với instance đang được patch. Kiểm tra ORACLE_HOME, PATH, ORACLE_SID và kết nối trước khi thực thi.

### 7.3. datapatch có thể chạy lại không?

Nếu lần chạy trước bị gián đoạn hoặc một PDB chưa mở, có thể cần chạy lại datapatch sau khi khắc phục nguyên nhân. Công cụ đọc trạng thái SQL patch registry và thực hiện các action cần thiết theo inventory/current state; chạy lại theo hướng dẫn Oracle thường là cách hoàn tất patching.

Không tự xóa dòng registry hoặc chỉnh sửa bảng nội bộ để làm datapatch nghĩ patch chưa chạy. Nếu registry ở trạng thái lỗi, hãy xem log và hướng dẫn xử lý cho đúng patch/release.

### 7.4. datapatch không thay OPatch

datapatch không cài binary patch. Nếu Oracle Home chưa được patch, datapatch không thể thay thế OPatch. Tương tự, OPatch không tự thực hiện tất cả SQL actions cần cho database dictionary.

## 8. CDB/PDB: kiểm tra và vá mọi container cần thiết

Trong multitenant architecture, root và PDB có registry riêng theo container. Một patch có thể yêu cầu SQL action trên CDB root, seed và một hoặc nhiều PDB.

### 8.1. Xem danh sách PDB và trạng thái

    SELECT
        con_id,
        name,
        open_mode,
        restricted
    FROM v$pdbs
    ORDER BY con_id;

Ghi nhận PDB nào cần được vá và PDB nào đang đóng vì maintenance hoặc chính sách vận hành.

### 8.2. Mở các PDB cần patch

Ví dụ:

    ALTER PLUGGABLE DATABASE ALL OPEN;

Lệnh này mở tất cả PDB mà tài khoản có quyền và môi trường cho phép. Trong production, không dùng ALL một cách máy móc nếu có PDB phải giữ đóng; mở đúng PDB theo change plan.

Một PDB cần ở trạng thái phù hợp để datapatch áp dụng SQL changes. Nếu PDB không mở trong lần chạy đầu, mở nó và chạy datapatch lại theo tài liệu Oracle.

### 8.3. Kiểm tra SQL patch registry trong từng container

Có thể chuyển container rồi query:

    ALTER SESSION SET CONTAINER = CDB$ROOT;

    SELECT
        patch_id,
        patch_uid,
        action,
        status,
        action_time,
        description,
        logfile
    FROM dba_registry_sqlpatch
    ORDER BY action_time DESC;

Sau đó kiểm tra từng PDB:

    ALTER SESSION SET CONTAINER = APP_PDB;

    SELECT
        patch_id,
        patch_uid,
        action,
        status,
        action_time,
        description,
        logfile
    FROM dba_registry_sqlpatch
    ORDER BY action_time DESC;

Tên APP_PDB chỉ là ví dụ. Cần kết nối bằng user có quyền xem data dictionary ở từng container. Có thể dùng CDB view nếu phiên bản hỗ trợ và user có quyền container data phù hợp.

### 8.4. PDB mới tạo hoặc clone sau khi patch

PDB được tạo, clone hoặc plug-in sau khi Oracle Home đã có RU cần được kiểm tra registry và trạng thái SQL patch theo hướng dẫn Oracle. Không giả định PDB mới luôn có đầy đủ SQL patch chỉ vì Oracle Home đã được vá.

Trong các môi trường tạo PDB tự động, đưa kiểm tra datapatch/registry vào quy trình provisioning và validation.

## 9. RAC và Data Guard

RAC và Data Guard làm thay đổi cách tổ chức patching. Một thao tác đúng trên single instance có thể không đủ cho cluster hoặc database có standby.

### 9.1. Oracle RAC

Trong RAC, mỗi node có Oracle Home riêng hoặc cấu trúc Home dùng chung tùy kiến trúc. Patch phải được áp dụng theo trình tự được hỗ trợ.

Một số patch hỗ trợ rolling patching, cho phép cập nhật từng node trong khi dịch vụ tiếp tục chạy trên node còn lại. Một số patch yêu cầu non-rolling patching và downtime toàn cluster. Không suy luận rolling capability chỉ từ việc patch là RU; kiểm tra README và tài liệu RAC patching.

Cần xác định:

- Patch có hỗ trợ rolling không.
- OPatch hay OPatchAuto được yêu cầu.
- Thứ tự node và instance.
- Service relocation và drain session.
- ASM/Grid Infrastructure dependency.
- Datapatch chạy ở thời điểm nào và trên node nào theo hướng dẫn.
- Kiểm tra inventory trên mọi node/Home.
- Kiểm tra SQL registry sau khi database services hoạt động.

Với Grid Infrastructure, OPatchAuto thường được dùng theo quy trình patch GI. Với Database Home, công cụ và trình tự có thể khác. Dùng đúng lệnh và README cho từng component.

### 9.2. Data Guard

Môi trường Data Guard có thể hỗ trợ chiến lược standby-first patching cho các patch được xác nhận tương thích. Ý tưởng chung là cập nhật software ở standby trước, kiểm tra, switchover theo quy trình rồi cập nhật database còn lại. Tuy nhiên, khả năng áp dụng phụ thuộc patch, release, Data Guard configuration và tài liệu Oracle.

Không tự áp dụng SQL patch/datapatch trên standby đang ở trạng thái mounted nếu quy trình patch không yêu cầu. Datapatch thường cần database mở theo trạng thái phù hợp để thực thi SQL actions. Trình tự trên primary/standby phải theo hướng dẫn patch cụ thể.

Trước và sau patch, kiểm tra:

- Transport lag và apply lag.
- Redo transport/apply status.
- Database role và open mode.
- Broker configuration nếu dùng Data Guard Broker.
- Services và client connect descriptor.
- Quy trình switchover/failback.
- SQL patch registry ở từng database sau khi patch hoàn tất.

Không coi việc standby apply redo bình thường là bằng chứng Oracle Home của standby đã có binary patch đúng.

## 10. Kiểm tra SQL patch registry

View quan trọng là DBA_REGISTRY_SQLPATCH, ghi nhận SQL patch actions đã thực hiện bởi datapatch.

### 10.1. Truy vấn patch history

    SELECT
        patch_id,
        patch_uid,
        action,
        status,
        action_time,
        description,
        source_version,
        target_version,
        logfile
    FROM dba_registry_sqlpatch
    ORDER BY action_time DESC;

Các cột phổ biến:

- PATCH_ID/PATCH_UID: định danh patch.
- ACTION: APPLY hoặc ROLLBACK.
- STATUS: SUCCESS hoặc WITH ERRORS.
- ACTION_TIME: thời điểm thực hiện action.
- DESCRIPTION: mô tả patch.
- SOURCE_VERSION/TARGET_VERSION: version liên quan đến action.
- LOGFILE: đường dẫn log datapatch.

Tên/cột có thể khác giữa các release; hãy xem data dictionary của phiên bản đang chạy.

### 10.2. Kiểm tra trạng thái mới nhất của patch

Ví dụ tìm một patch ID cụ thể:

    SELECT
        patch_id,
        action,
        status,
        action_time,
        description,
        logfile
    FROM dba_registry_sqlpatch
    WHERE patch_id = 12345678
    ORDER BY action_time DESC;

Thay 12345678 bằng patch ID thực tế. Nếu có nhiều action APPLY/ROLLBACK, đọc lịch sử theo thời gian và xác định action cuối cùng. Không chỉ kiểm tra có một dòng patch_id là kết luận patch đang được áp dụng.

### 10.3. Kiểm tra WITH ERRORS

Nếu STATUS là WITH ERRORS, patch SQL action không hoàn tất sạch. Mở log datapatch được ghi trong LOGFILE và xác định SQL statement/component/PDB gây lỗi.

Một số lỗi có thể do component invalid, object dependency, tablespace, quyền hoặc PDB không ở trạng thái phù hợp. Khắc phục theo log và tài liệu Oracle, sau đó chạy lại datapatch khi đã sẵn sàng. Không sửa trực tiếp registry để đổi WITH ERRORS thành SUCCESS.

### 10.4. Kiểm tra component registry

    SELECT
        comp_id,
        comp_name,
        version,
        status
    FROM dba_registry
    ORDER BY comp_id;

Kiểm tra component liên quan có trạng thái hợp lệ và version phù hợp. Một component INVALID hoặc LOADING có thể cần xử lý riêng trước/sau patch theo README.

### 10.5. Kiểm tra registry theo PDB

Trong CDB, query DBA_REGISTRY_SQLPATCH trong từng container để xác nhận SQL patch. Có thể dùng CDB_REGISTRY_SQLPATCH nếu release hỗ trợ và quyền cho phép, ví dụ:

    SELECT
        con_id,
        patch_id,
        action,
        status,
        action_time,
        description
    FROM cdb_registry_sqlpatch
    ORDER BY con_id, action_time DESC;

Nếu view không tồn tại hoặc user không có quyền, chuyển container và query DBA_REGISTRY_SQLPATCH. Kết quả phải được đối chiếu với danh sách PDB nằm trong phạm vi patch.

## 11. Kiểm tra sau vá ở lớp Oracle Home

Sau khi OPatch hoàn tất, cần xác minh binary inventory và version.

### 11.1. Chạy lsinventory lại

    $ORACLE_HOME/OPatch/opatch lsinventory -detail

Đối chiếu với output trước vá:

- Patch ID đúng.
- RU level đúng.
- Oracle Home đúng.
- Không có patch apply dở dang hoặc inventory error.
- Các one-off patch cần giữ vẫn tồn tại hoặc đã được thay bằng merge patch theo kế hoạch.
- Tất cả node/Home trong RAC có trạng thái phù hợp.

Lưu output sau vá cùng change record.

### 11.2. Kiểm tra binary version từ database

    SELECT banner_full
    FROM v$version;

Cột BANNER_FULL có ở các release hỗ trợ; nếu không có, dùng các cột/version view phù hợp với release. V$VERSION phản ánh version banner của database software, nhưng không thay thế lsinventory để kiểm tra patch ID.

### 11.3. Kiểm tra alert log và startup

Sau khi khởi động database từ Oracle Home đã vá, kiểm tra alert log để phát hiện:

- Lỗi load shared library hoặc binary.
- Lỗi startup/mount/open.
- Component không load.
- Warning về patch/SQL registry.
- Lỗi dictionary hoặc background process.
- Lỗi PDB open.

Không bỏ qua cảnh báo chỉ vì database mở thành công. Đối chiếu với known issues và README của patch.

## 12. Kiểm tra sau vá ở lớp database

Sau datapatch, xác nhận database hoạt động bình thường và SQL patch registry đúng.

### 12.1. Kiểm tra database và instance

    SELECT name, open_mode, database_role, cdb
    FROM v$database;

    SELECT instance_name, status, version
    FROM v$instance;

Xác nhận đúng database, role, trạng thái OPEN và version dự kiến. Với RAC, kiểm tra mọi instance và service.

### 12.2. Kiểm tra PDB

    SELECT name, open_mode, restricted
    FROM v$pdbs
    ORDER BY name;

Xác nhận PDB cần phục vụ đã mở đúng mode, không bị restricted ngoài dự kiến. Kiểm tra SQL registry trong từng PDB.

### 12.3. Kiểm tra object invalid

    SELECT
        owner,
        object_type,
        COUNT(*) AS invalid_count
    FROM dba_objects
    WHERE status = 'INVALID'
    GROUP BY owner, object_type
    ORDER BY owner, object_type;

So sánh với baseline trước patch. Một số object invalid có thể đã tồn tại trước patch hoặc cần compile theo quy trình release; không tự động kết luận mọi INVALID đều do patch.

Nếu cần recompile object invalid, dùng quy trình Oracle phù hợp, ví dụ utlrp.sql khi README/Oracle hướng dẫn. Không chạy compile script theo thói quen nếu database đang ở trạng thái không phù hợp hoặc có bước patch hậu kỳ khác.

### 12.4. Kiểm tra component status

    SELECT comp_id, comp_name, version, status
    FROM dba_registry
    ORDER BY comp_id;

Component status cần phù hợp với baseline và tài liệu patch. Nếu component đang INVALID/LOADING, kiểm tra log và bước hậu kỳ liên quan.

### 12.5. Kiểm tra application smoke test

Sau khi database mở:

- Ứng dụng đăng nhập được bằng service account.
- Query đọc quan trọng chạy thành công.
- Stored procedure/package được gọi thành công.
- Transaction commit/rollback hoạt động.
- Job/scheduler quan trọng chạy được.
- Connection pool tạo và tái sử dụng connection bình thường.
- Batch, reporting, replication và integration quan trọng hoạt động.
- Latency, CPU, I/O và wait event không có regression bất thường.

Smoke test cần có truy vấn/luồng nghiệp vụ đại diện, không chỉ kiểm tra SELECT 1 FROM dual.

## 13. Quy trình patch mẫu cho single-instance database

Ví dụ dưới đây mô tả trình tự tổng quát cho một RU áp dụng bằng OPatch và cần datapatch. README của patch có quyền ưu tiên nếu trình tự khác.

### Giai đoạn A: khảo sát

1. Ghi nhận Oracle release, platform, Oracle Home, SID và database role.
2. Lưu opatch version và opatch lsinventory.
3. Xác định RU/one-off hiện tại.
4. Đọc README và xác nhận prerequisites.
5. Kiểm tra conflict.
6. Xác nhận backup, rollback và cửa sổ bảo trì.
7. Chuẩn bị patch staging và kiểm tra dung lượng.

### Giai đoạn B: apply binary patch

1. Dừng database/listener/process theo README.
2. Đặt ORACLE_HOME và PATH đúng.
3. Chuyển tới patch directory.
4. Chạy OPatch apply.
5. Đọc output và log.
6. Chạy lsinventory để xác nhận binary patch.

Ví dụ:

    export ORACLE_HOME=/u01/app/oracle/product/db_home
    export PATH=$ORACLE_HOME/OPatch:$ORACLE_HOME/bin:$PATH

    cd /stage/patch_directory
    opatch apply

Đây là cú pháp shell Unix/Linux. Windows dùng cách thiết lập environment và executable tương ứng.

### Giai đoạn C: startup và datapatch

1. Khởi động database bằng Oracle Home đã vá.
2. Mở database theo yêu cầu patch.
3. Với CDB, mở các PDB thuộc phạm vi.
4. Chạy datapatch từ đúng Oracle Home.
5. Đọc log và xác nhận không có SQL action WITH ERRORS.

Ví dụ:

    $ORACLE_HOME/OPatch/datapatch -verbose

### Giai đoạn D: verify

1. Chạy lsinventory.
2. Query DBA_REGISTRY_SQLPATCH.
3. Kiểm tra CDB/PDB registry.
4. Kiểm tra DBA_REGISTRY và object invalid.
5. Xem alert log và datapatch log.
6. Chạy smoke test ứng dụng.
7. Lưu kết quả và đóng change record.

## 14. Rollback patch

Rollback cần được lên kế hoạch trước khi apply. Không phải patch nào cũng rollback theo cùng cách; một số patch có yêu cầu hoặc giới hạn riêng.

### 14.1. Rollback binary bằng OPatch

Với patch hỗ trợ rollback, ví dụ:

    cd /stage/patch_directory
    $ORACLE_HOME/OPatch/opatch rollback -id 12345678

Thay patch ID và thư mục theo đúng README. Một số patch yêu cầu rollback từ patch directory hoặc có trình tự riêng. Không tự chạy rollback cho RU hoặc one-off nếu chưa xác định dependency với các patch khác.

Sau rollback, kiểm tra lsinventory để xác nhận patch đã được gỡ khỏi Oracle Home.

### 14.2. Đồng bộ SQL sau rollback

Nếu patch đã chạy datapatch, sau khi rollback binary cần thực hiện các bước SQL patch tương ứng theo README. Trong các quy trình được hỗ trợ, chạy datapatch từ Oracle Home đã rollback có thể áp dụng SQL rollback action dựa trên inventory và registry hiện tại.

Ví dụ tổng quát:

    $ORACLE_HOME/OPatch/datapatch -verbose

Không giả định mọi patch có SQL rollback action hoặc mọi trường hợp rollback đều giống nhau. Đọc log và README để xác nhận action ROLLBACK được ghi nhận thành công. Không xóa thủ công registry row.

### 14.3. Rollback không giống restore database

OPatch rollback thay đổi Oracle Home. Nó không tự khôi phục dữ liệu ứng dụng đã thay đổi sau khi patch, cũng không quay database về SCN trước patch.

RMAN restore/recovery hoặc Flashback Database là quy trình khác, có thể gây mất các thay đổi sau điểm phục hồi. Chỉ sử dụng khi đã đánh giá RPO/RTO và có phê duyệt riêng.

### 14.4. Out-of-place patching

Một số môi trường chọn tạo Oracle Home mới, patch Home mới, kiểm thử rồi chuyển database/service sang Home đó. Đây là cách out-of-place patching, giúp giữ Home cũ làm phương án quay lại ở cấp software nếu kiến trúc và quy trình hỗ trợ.

Tuy nhiên, database dictionary có thể đã được cập nhật bởi datapatch khi chạy trên Home mới. Chuyển ngược về Home cũ không tự động rollback SQL changes; cần đảm bảo compatibility và rollback plan theo tài liệu Oracle. Không coi việc giữ Home cũ là toàn bộ kế hoạch rollback.

## 15. Những lỗi thường gặp

### 15.1. OPatch không đủ phiên bản

Thông báo prerequisite hoặc OPatch version không đáp ứng. Cập nhật OPatch theo README, đúng platform/release/Home, rồi kiểm tra opatch version và inventory trước khi apply lại.

### 15.2. Patch conflict

Patch mới xung đột với one-off hoặc patch hiện tại. Xác định patch ID, đọc conflict detail, tìm merge patch hoặc hướng dẫn từ Oracle Support. Không chỉnh inventory bằng tay.

### 15.3. Không gian staging hoặc Oracle Home không đủ

Giải phóng hoặc cấp thêm dung lượng theo quy trình, giữ log và patch archive ở nơi an toàn. Không xóa file trong Oracle Home tùy tiện để lấy chỗ.

### 15.4. OPatch apply thành công nhưng datapatch fail

Kiểm tra database open mode, PDB state, ORACLE_HOME, service connection, quyền, component status và datapatch log. Khắc phục nguyên nhân rồi chạy lại datapatch theo hướng dẫn. Không rollback binary ngay lập tức nếu chưa xác định lỗi SQL và phương án xử lý.

### 15.5. PDB bị bỏ sót

PDB đóng trong thời điểm datapatch có thể chưa nhận SQL patch. Mở PDB phù hợp rồi chạy datapatch lại; kiểm tra registry trong PDB đó. Không chỉ kiểm tra CDB root.

### 15.6. SQL patch registry có WITH ERRORS

Mở logfile theo cột LOGFILE và log datapatch. Xác định SQL statement lỗi, component, container và prerequisite. Dùng hướng dẫn patch hoặc Oracle Support để khắc phục. Không cập nhật bảng registry trực tiếp.

### 15.7. Binary inventory khác nhau giữa RAC nodes

Kiểm tra từng Oracle Home/node, patch ID và patch level. Một node chưa được patch có thể gây lỗi khi service chạy/failover sang node đó. Hoàn tất trình tự cluster trước khi đưa toàn bộ service về trạng thái bình thường.

### 15.8. Database mở được nhưng ứng dụng lỗi

Có thể do invalid object, privilege, SQL plan, driver/client compatibility, changed behavior hoặc lỗi trong application. Kiểm tra alert log, application log, SQL patch registry, component status và smoke test. Không kết luận patch thành công chỉ từ trạng thái database OPEN.

## 16. Lập kế hoạch patch cho RAC và Data Guard

Với kiến trúc HA, change plan cần ghi rõ thứ tự và tiêu chí tiếp tục.

### 16.1. RAC runbook

Một runbook RAC nên nêu:

- Patch có rolling hay non-rolling.
- Công cụ OPatch/OPatchAuto cần dùng.
- Node nào patch trước.
- Service nào relocate/drain.
- Điều kiện node được đưa lại vào cluster.
- Cách kiểm tra Oracle Home inventory trên từng node.
- Thời điểm chạy datapatch theo README.
- Kiểm tra registry, instance và service sau mỗi giai đoạn.
- Kịch bản rollback nếu một node thất bại.

Không tự chia RU thành rolling steps nếu patch không hỗ trợ. Một số patch cần patch toàn cluster theo non-rolling method.

### 16.2. Data Guard runbook

Runbook Data Guard nên nêu:

- Patch nào hỗ trợ standby-first.
- Oracle Home và database role ở từng site.
- Transport/apply lag trước và sau patch.
- Thứ tự patch standby, switchover và patch site còn lại.
- Thời điểm datapatch được yêu cầu.
- Kiểm tra broker, redo transport và apply.
- Kịch bản failback/rollback.
- Đối chiếu SQL registry và inventory ở cả primary/standby.

Không thực hiện switchover chỉ vì binary patch trên standby đã hoàn tất. Cần xác nhận database role, redo apply, patch compatibility và quy trình Oracle cho patch cụ thể.

## 17. Change record và bằng chứng sau vá

Một change record nên lưu bằng chứng để DBA hoặc auditor có thể xác nhận trạng thái trước/sau:

| Bằng chứng | Trước vá | Sau vá |
|---|---|---|
| Oracle Home path | Có | Có |
| opatch version | Có | Có |
| opatch lsinventory | Có | Có |
| Patch ID/RU level | Có | Có |
| Database version/banner | Có | Có |
| DBA_REGISTRY_SQLPATCH | Baseline | APPLY/ROLLBACK status |
| PDB open state | Có | Có |
| Component registry | Có | Có |
| Invalid objects | Baseline | Delta sau vá |
| Alert/datapatch/OPatch log | — | Lưu log |
| Application smoke test | Baseline | Kết quả |
| Performance baseline | Có | So sánh |

Bằng chứng cần chỉ rõ timestamp, database identity, Oracle Home, node và container. Một output không ghi rõ Home hoặc PDB có thể gây nhầm lẫn khi audit nhiều database.

## 18. Checklist trước, trong và sau patch

### Trước patch

- Xác nhận release, platform, Oracle Home và database identity.
- Chọn đúng RU/patch và đọc README đầy đủ.
- Kiểm tra OPatch version, inventory và patch conflict.
- Xác định prerequisite, superseded/one-off patch và component liên quan.
- Xác nhận backup, rollback và out-of-place option.
- Kiểm tra storage, quyền, staging và log location.
- Xác định trạng thái RAC/Data Guard/CDB/PDB và rolling capability.
- Lập runbook, downtime, owner và tiêu chí go/no-go.

### Trong patch

- Dừng/di chuyển service theo đúng trình tự.
- Chạy OPatch/OPatchAuto theo README.
- Kiểm tra output và log từng bước.
- Xác nhận binary inventory sau apply.
- Khởi động database bằng Home đã patch.
- Mở các container cần thiết.
- Chạy datapatch từ đúng Oracle Home.
- Theo dõi SQL action và log của từng PDB.

### Sau patch

- Xác nhận opatch lsinventory trên mọi Home/node.
- Xác nhận DBA_REGISTRY_SQLPATCH có action/status mong muốn.
- Kiểm tra từng PDB, không chỉ CDB root.
- Kiểm tra DBA_REGISTRY, invalid object và alert log.
- Kiểm tra database role, service, listener và cluster health.
- Chạy smoke test ứng dụng và kiểm tra transaction.
- Theo dõi error rate, latency, CPU, I/O và wait event.
- Lưu log/baseline và cập nhật change record.

## 19. Nguyên tắc cần nhớ

- RU là gói cập nhật tích lũy; chọn đúng release, platform và patch README.
- OPatch thay đổi Oracle Home inventory và binary; datapatch áp dụng SQL changes trong database.
- OPatch thành công không chứng minh datapatch đã hoàn tất.
- opatch lsinventory và DBA_REGISTRY_SQLPATCH là hai nguồn trạng thái khác nhau cần đối chiếu.
- Trong CDB, kiểm tra SQL patch registry ở root và mọi PDB thuộc phạm vi.
- PDB đóng khi datapatch chạy có thể cần được mở và patch bổ sung theo hướng dẫn.
- RAC rolling capability và Data Guard standby-first phải được xác nhận theo patch cụ thể.
- Không tự sửa inventory hoặc SQL patch registry bằng DML.
- Rollback binary và rollback SQL là hai phần cần phối hợp; restore database là một quy trình khác.
- Kiểm tra alert log, component registry, invalid object, services và application smoke test sau vá.
- README của patch và tài liệu Oracle đúng release là nguồn chỉ dẫn có thẩm quyền.

Quản lý patch Oracle là một quy trình xuyên suốt từ Oracle Home tới database dictionary và từng container. Khi inventory, datapatch registry, log và smoke test đều được xác nhận, nhóm vận hành mới có đủ bằng chứng rằng bản vá đã được triển khai hoàn chỉnh và database sẵn sàng phục vụ ứng dụng.
