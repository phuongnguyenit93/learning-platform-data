# Tổng quan ASM, disk group, redundancy và ranh giới với filesystem

Trong Oracle Database, một bảng như `SALES.ORDERS` là đối tượng logic, còn dữ liệu của bảng cuối cùng nằm trong những **datafile** trên thiết bị lưu trữ. Oracle cần biết cách cấp phát dung lượng, phân bố các file ra nhiều đĩa, xử lý khi một đĩa gặp sự cố và mở các file đó khi database chạy. Có hai cách tổ chức quen thuộc:

- **Filesystem truyền thống:** Oracle lưu datafile, control file, redo log... dưới những đường dẫn do hệ điều hành quản lý, chẳng hạn `/u02/oradata/SALES/users01.dbf`.
- **Oracle Automatic Storage Management (ASM):** Oracle dùng một lớp quản lý lưu trữ chuyên dụng để tổ chức các thiết bị thành **ASM disk group** và lưu các Oracle file qua tên như `+DATA/SALES/DATAFILE/users.257.123456789`.

**ASM không phải một database SQL mới, cũng không phải một thư mục thông thường của Linux.** Nó là thành phần quản lý storage dành cho Oracle, cung cấp cơ chế phân bố dữ liệu và redundancy ở cấp disk group. Hiểu ASM giúp đọc đúng tên file có dấu `+`, lập kế hoạch dung lượng, phân biệt hỏng đĩa với hỏng database, và biết khi nào dùng filesystem hoặc ASM.

## 1. Đặt ASM vào đúng vị trí kiến trúc

Một ứng dụng không cần biết từng block của bảng đang nằm ở ổ đĩa nào. Nó gửi SQL đến **Oracle Database instance**; instance dùng thông tin lưu trữ để đọc/ghi các file của database.

### Khi dùng filesystem

```text
Ứng dụng / SQL client
        |
        v
Oracle Database Instance (SGA + background processes)
        |
        v
Datafile /u02/oradata/SALES/users01.dbf
        |
        v
Filesystem của OS (ví dụ XFS/ext4)
        |
        v
Volume/LVM/RAID/SAN hoặc thiết bị block
        |
        v
Đĩa vật lý hay storage được cấp phát
```

Hệ điều hành và lớp volume/filesystem quản lý đường dẫn file. DBA vẫn phải bố trí datafile vào các filesystem/mount point phù hợp, theo dõi dung lượng và phối hợp với quản trị storage khi mở rộng.

### Khi dùng ASM

```text
Ứng dụng / SQL client
        |
        v
Oracle Database Instance
        |       (tra metadata, thực hiện database I/O)
        |
        +---------> Oracle ASM Instance
        |            - quản lý metadata ASM
        |            - mount các disk group
        |            - điều phối rebalance
        |              (không chuyển tiếp mọi block I/O)
        v
ASM file: +DATA/SALES/DATAFILE/users.257....
        |
        v
ASM Disk Group +DATA
        |               |
        v               v
ASM disk A          ASM disk B ... (thiết bị block/LUN)
        \               /
         \--- storage vật lý ---/
```

**Điểm dễ nhầm:** Oracle Database instance và Oracle ASM instance là **hai loại instance khác nhau**. ASM instance quản lý metadata/việc phân bố và hoạt động của disk group; database instance chịu trách nhiệm SQL, transaction, cache dữ liệu và database recovery. Khi đọc/ghi dữ liệu thông thường, database instance có thể thực hiện I/O **trực tiếp tới các thiết bị ASM**, dựa vào metadata đã nhận từ ASM. Không có quy tắc “mọi câu `SELECT` phải gửi toàn bộ block qua tiến trình ASM”.

ASM thường được triển khai qua **Oracle Grid Infrastructure** với cấu hình và quyền quản trị riêng. Nó dùng được cho single-instance database và là lựa chọn lưu trữ phổ biến cho Oracle RAC; **có ASM không có nghĩa mặc nhiên chạy RAC**.

## 2. Từ thiết bị lưu trữ đến ASM disk group

Các tầng cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| **Physical disk / LUN / block device** | Thiết bị dung lượng mà hệ điều hành nhìn thấy; có thể là đĩa thật hoặc LUN do SAN/RAID cung cấp | `/dev/mapper/asm-data01` |
| **ASM disk** | Thiết bị đủ điều kiện được ASM nhận diện và đưa vào một disk group | `DATA_0001` |
| **Failure group** | Nhóm các ASM disk được xem là cùng miền lỗi; ASM tránh đặt các bản sao mirror vào cùng miền lỗi khi có thể | `RACK_A`, `RACK_B` |
| **ASM disk group** | Tập ASM disk được quản lý như một pool lưu trữ, có quy tắc redundancy và các thuộc tính riêng | `+DATA`, `+RECO` |
| **ASM file** | File do ASM quản lý trong disk group; database có thể dùng làm datafile, redo log, control file... | `+DATA/SALES/DATAFILE/...` |
| **ASM allocation unit (AU)** | Đơn vị cấp phát cơ sở của ASM trên thiết bị | Ví dụ một disk group cấu hình AU 4 MiB |
| **ASM file extent** | Phần của file được ASM ánh xạ vào vùng cấp phát trên ASM disk | Các extent phân bố trên nhiều đĩa |

**ASM disk group không phải tablespace.** Tablespace là cấu trúc logic của Oracle Database, gồm các datafile hoặc tempfile; disk group là nơi **các file đó được ASM bố trí vật lý**. Một disk group có thể chứa file của nhiều database hoặc nhiều tablespace; một database có thể dùng nhiều disk group.

### 2.1. Disk discovery và disk membership

Trước khi ASM dùng thiết bị, quản trị viên storage/OS phải cung cấp block device/LUN với danh tính và quyền truy cập ổn định. ASM tìm các thiết bị ứng viên qua cơ chế cấu hình khám phá đĩa (*disk discovery*). Tùy nền tảng có thể dùng cơ chế như udev, Oracle ASMLib hoặc cơ chế lọc/ghi nhãn đĩa tương thích với phiên bản triển khai.

Một thiết bị được thêm vào disk group sẽ mang thông tin thành viên trong **ASM disk header**. Không nên tự ý:

- Chạy `mkfs` để tạo filesystem thông thường lên thiết bị đang thuộc ASM disk group.
- Mount đĩa ASM như một volume XFS/ext4 bình thường.
- Copy file trực tiếp vào block device hoặc sửa disk header bằng công cụ OS.
- Đổi đường dẫn thiết bị mà không phối hợp cấu hình ASM/cluster.

Những thao tác đó có thể làm hỏng dữ liệu. Việc tạo, thêm, xóa, thay hoặc format thiết bị phải theo quy trình quản trị storage, có kiểm tra ownership và trạng thái cluster.

### 2.2. Tổ chức file theo allocation unit và extent

ASM chia không gian lưu trữ thành các **allocation unit** và dùng chúng để cấp phát **ASM file extents**. Một extent có thể gồm một hoặc nhiều AU tùy quy tắc cấp phát và kích thước file. ASM quản lý metadata ánh xạ những extent của một file tới các disk cụ thể.

```text
ASM file: +DATA/SALES/DATAFILE/users...
        |
        +-- File extent 1 ---> ASM disk A: các AU
        |
        +-- File extent 2 ---> ASM disk B: các AU
        |
        +-- File extent 3 ---> ASM disk C: các AU
        |
        +-- File extent 4 ---> ASM disk A/B/... tùy phân bố
```

Đây là mô hình minh họa, không phải cam kết extent nào nằm ở đĩa nào. **Oracle data block** là đơn vị logic của Oracle Database; **ASM AU và ASM file extent** là đơn vị quản lý lưu trữ của ASM. Không được nhầm chúng với extent/segment trong tablespace: hai lớp có chức năng khác nhau.

ASM có thể **stripe** các extent trên nhiều disk để phân bố tải I/O và tăng tính cân bằng. Đặc điểm striping (*fine/coarse*) và template áp dụng khác nhau theo loại ASM file, release và cấu hình. Không suy diễn rằng “một file ASM” đồng nghĩa “một đĩa vật lý”.

## 3. ASM instance quản lý điều gì?

Một ASM instance có vùng nhớ, background processes và các tham số riêng của nó. ASM instance không chứa các bảng nghiệp vụ và không thực thi transaction SQL cho ứng dụng. Nhiệm vụ chính bao gồm:

1. **Khám phá và mount disk group:** xác nhận tập disk thuộc nhóm và cung cấp metadata cần thiết cho database instance.
2. **Quản lý không gian:** cấp phát và ánh xạ các extent của ASM file.
3. **Quản lý redundancy:** xác định các bản sao mirror theo failure group và thuộc tính disk group/file.
4. **Rebalance:** khi thêm, xóa, resize hoặc thay disk, phân bố lại các extent để cân bằng dung lượng và đáp ứng quy tắc redundancy.
5. **Cung cấp metadata cho database instance:** hỗ trợ định vị file và cập nhật mapping khi cấu trúc storage thay đổi.

Database instance tiếp tục đảm nhiệm DBWn, LGWR, SGA, transaction, undo, redo và phục hồi dữ liệu ở cấp database. Dùng ASM **không làm redo log, RMAN hay database backup trở nên không cần thiết**.

### 3.1. ASM trong một máy và trong cụm RAC

```text
SINGLE INSTANCE
  Máy A:
    Database Instance A
    ASM Instance A --------> Disk Group +DATA

RAC / CLUSTER (sơ đồ đơn giản hóa)
  Node A: Database Instance A ---+
                                  +---- shared +DATA
  Node B: Database Instance B ---+     ASM Disk Group
      Các ASM instance/dịch vụ ASM quản lý
      metadata theo kiến trúc Grid Infrastructure
```

Trong RAC, các database instance của cùng database truy cập storage dùng chung có cơ chế phối hợp truy cập dữ liệu. Chi tiết có thể khác nếu dùng **Flex ASM**, nơi database instance không nhất thiết phải nằm cùng node với ASM instance phục vụ nó. Không được mô phỏng RAC bằng cách cho hai database instance độc lập trên hai máy tùy ý mở chung một thư mục datafile.

### 3.2. File nào có thể nằm trong ASM?

Các loại file Oracle thường có thể đặt trong disk group được hỗ trợ:

- **Datafiles** và **tempfiles** của tablespace.
- **Control files** và **online redo log files**.
- **Archived redo logs**, backup pieces, image copies và file thuộc **Fast Recovery Area (FRA)** theo cấu hình.
- **SPFILE** và các file quản trị khác mà Oracle/Oracle Grid Infrastructure hỗ trợ ở ASM.

Đường dẫn ASM được Oracle cấp và quản lý theo loại file. Một số file hệ điều hành như mã nguồn Java, ảnh tải về, script shell, binary hệ thống và log ứng dụng thông thường vẫn thuộc phạm vi filesystem, object storage hoặc nền tảng lưu trữ thích hợp khác.

## 4. Disk group: một pool lưu trữ có chính sách riêng

Disk group thường được đặt tên ngắn, dễ hiểu theo mục đích:

| Tên thường gặp | Mục đích | Ghi chú |
| --- | --- | --- |
| `+DATA` | Datafiles, control files và một số redo files | Không bắt buộc mỗi bảng/tablespace có group riêng |
| `+RECO` hoặc `+FRA` | Fast Recovery Area, archived redo và backup/recovery files | FRA có quota/quy trình dọn riêng; không tự là backup ngoài hệ thống |
| `+OCR` / disk group dùng cho Grid Infrastructure | Một số file phục vụ cluster theo mô hình được Oracle hỗ trợ | Yêu cầu riêng về tương thích, quorum và quản trị cluster |

Các tên trên là **quy ước**, không phải tên đặc biệt bắt buộc. Disk group còn có **redundancy type**, **AU size**, **compatibility attributes**, trạng thái mount, số disk và dung lượng. Việc một disk group có tên `+RECO` không tự động khiến database ghi archived redo vào đó: phải cấu hình đường dẫn/đích recovery đúng.

### 4.1. Oracle Managed Files (OMF) và ASM là hai khái niệm khác nhau

**OMF (Oracle Managed Files)** là cơ chế Oracle Database đặt tên và quản lý vòng đời file theo các đích được cấu hình, ví dụ:

```text
db_create_file_dest    = +DATA
db_recovery_file_dest  = +RECO
```

Khi cấu hình phù hợp, Oracle có thể tự tạo tên file ASM dạng:

```text
+DATA/SALES/DATAFILE/users.257.123456789
+DATA/SALES/CONTROLFILE/current.258.123456790
+RECO/SALES/ARCHIVELOG/...
```

OMF **không đồng nghĩa ASM**: Oracle Managed Files cũng có thể được sử dụng với một filesystem thông thường, và ASM có cơ chế **alias** cho file bên cạnh tên fully qualified do Oracle quản lý. Đừng cố sửa tên, di chuyển hoặc xóa datafile trực tiếp như một file văn bản trong thư mục OS; hãy dùng lệnh/database procedure hoặc công cụ ASM/Oracle được hỗ trợ cho từng loại thao tác.

### 4.2. Một database có thể đi qua nhiều disk group

```text
Database SALES_CDB
  +-- Tablespace SYSTEM -> datafile trong +DATA
  +-- Tablespace APP    -> datafile trong +DATA
  +-- Online redo logs  -> có thể đặt trong +DATA và/hoặc vị trí phù hợp
  +-- Archived redo     -> +RECO nếu cấu hình FRA
  +-- RMAN backup       -> +RECO hoặc đích backup khác

Database REPORT_CDB
  +-- Datafiles         -> cũng có thể dùng +DATA
```

**Ranh giới tenant/schema/PDB không tự bằng ranh giới disk group.** Hai PDB thuộc cùng CDB có thể có datafiles trên cùng disk group; hai database khác nhau cũng có thể chia sẻ pool ASM tùy thiết kế dung lượng và cô lập. Quyền truy cập dữ liệu SQL vẫn do Oracle Database kiểm soát, không dựa vào việc hai file nằm cùng group.

## 5. Redundancy: ASM bảo vệ trước những loại lỗi nào?

**Redundancy** ở đây là cơ chế tạo **bản sao vật lý của ASM file extents** theo chính sách để duy trì khả năng truy cập dữ liệu khi một disk hoặc failure group hỏng. Mức bảo vệ phụ thuộc thiết kế failure group, loại redundancy, placement, file templates và lượng không gian còn lại.

### 5.1. Các loại redundancy thường gặp

| Loại disk group | Nguyên tắc cơ bản | Mức bảo vệ cần hiểu |
| --- | --- | --- |
| **EXTERNAL redundancy** (view thường hiển thị `EXTERN`) | ASM không tự mirror extents thông thường; kỳ vọng lớp storage bên dưới như RAID/SAN đảm nhiệm bảo vệ nếu cần | Mất block device/LUN mà storage không bảo vệ có thể làm mất file |
| **NORMAL redundancy** | Thường dùng **two-way mirroring**: hai bản sao extent thuộc các failure group khác nhau | Có thể chịu mất một failure group theo thiết kế phù hợp; cần không gian để phục hồi redundancy |
| **HIGH redundancy** | Thường dùng **three-way mirroring** qua các failure group khác nhau | Có thể chịu mất hai failure group khi topology và chính sách phù hợp; tốn nhiều dung lượng |
| **FLEX redundancy** | Quản lý redundancy chi tiết theo **file group** và khả năng quản trị của release hỗ trợ | Không thể suy ra mọi file đều hai hoặc ba bản sao chỉ từ tên loại group |
| **EXTENDED / EXTEND redundancy** | Mô hình mở rộng cho các miền vị trí/site theo cấu hình được hỗ trợ | Cần thiết kế site/failure group/quorum và khả năng chịu lỗi đặc thù |

**NORMAL không đồng nghĩa đơn giản với “có hai đĩa”, HIGH cũng không chỉ là “có ba đĩa”.** Số và sự phân bố failure group mới giúp ASM đặt các mirror copies ngoài cùng một miền rủi ro. Ví dụ mất nguồn của một khay đĩa có thể làm hỏng nhiều disk cùng lúc dù tổng số disk còn lớn.

Mức bảo vệ thực tế của một file cũng có thể khác mức mặc định trong một số cấu hình: có **ASM file templates**, thuộc tính file group, file đặc biệt và quy tắc từng release. Bảng này mô tả nguyên tắc tổng quan để lựa chọn kiến trúc, không thay thế tài liệu cấu hình chi tiết.

### 5.2. Failure group quyết định các bản sao nên cách ly thế nào

Hãy hình dung một disk group NORMAL có hai miền lỗi:

```text
                      ASM DISK GROUP +DATA

        FAILURE GROUP FG_A          FAILURE GROUP FG_B
        (tủ/khay/nguồn A)           (tủ/khay/nguồn B)
          Disk A1, A2                  Disk B1, B2
             |                            |
       extent X, copy 1             extent X, copy 2
       extent Y, copy 2             extent Y, copy 1

Một hỏng hóc chỉ ở FG_A -> FG_B còn bản sao của extent X/Y.
```

Với HIGH redundancy, nguyên tắc khái niệm là cần ba miền lỗi độc lập để đặt ba bản sao cho mỗi extent. Với NORMAL thường cần tối thiểu hai failure group; HIGH cần tối thiểu ba, và các yêu cầu chi tiết về disk/failure group thay đổi theo phiên bản, loại group và cách triển khai.

**Failure group là “những disk có khả năng hỏng cùng nhau”, không phải “những disk chắc chắn an toàn khi ở cạnh nhau”.** Nếu hai failure group đều cùng nguồn điện, SAN controller hoặc storage array không có sự độc lập thực sự, mất thiết bị chung vẫn có thể tác động cả hai. Người thiết kế phải lấy sơ đồ phần cứng và failure domain thực tế làm căn cứ.

### 5.3. EXTERNAL redundancy không có nghĩa “không an toàn”

EXTERNAL cho phép ASM tập trung vào striping/placement trong khi storage bên dưới (ví dụ RAID được quản lý) đảm nhận bảo vệ theo thiết kế. Ngược lại, nếu gán nhiều LUN từ một array không có protection và chọn EXTERNAL, ASM sẽ **không tự bổ sung các mirror copies** để cứu dữ liệu khi mất LUN.

Có thể dùng RAID bên dưới ASM và vẫn chọn ASM mirroring trong một thiết kế có chủ đích, nhưng kết hợp nhiều lớp redundancy có chi phí dung lượng, hiệu năng và vận hành. Hãy xác định rõ **lớp nào chịu trách nhiệm cho loại lỗi nào**, tránh vừa tưởng RAID đã đủ vừa mặc định ASM sẽ bảo vệ thêm.

### 5.4. Redundancy không thay cho backup

ASM mirroring giúp duy trì khả năng truy cập khi một số thành phần storage hỏng. Nó **không hoàn tác** được:

- Lệnh `DELETE`/`DROP TABLE` bị thực thi nhầm và commit.
- Dữ liệu bị thay đổi sai do bug ứng dụng.
- Logic corruption được ghi hợp lệ lên mọi bản sao.
- Sự cố lan toàn site, mất tài khoản/quyền truy cập hoặc phá hủy cả hệ thống lưu trữ.
- Nhu cầu phục hồi database về một **thời điểm quá khứ**.

Vì vậy vẫn cần **RMAN backup**, chiến lược archived redo/recovery, kiểm tra khả năng restore và bản sao độc lập theo yêu cầu RPO/RTO. FRA trên `+RECO` là nơi tập trung tài nguyên recovery; **FRA đặt cùng hệ thống hạ tầng không tự là bản sao ngoài site**.

## 6. Đọc dung lượng đúng: RAW, FREE và USABLE

Một trong những sai lầm phổ biến nhất là nhìn thấy `FREE_MB` rồi cho rằng có thể tạo thêm đúng chừng đó MB dữ liệu ứng dụng.

Các trường thường được DBA quan sát trong `V$ASM_DISKGROUP_STAT`:

| Trường | Ý nghĩa |
| --- | --- |
| `TOTAL_MB` | Tổng dung lượng các ASM disk trong group (giá trị thô), theo đơn vị MB của view |
| `FREE_MB` | Dung lượng chưa cấp phát ở cấp ASM; **chưa khấu trừ yêu cầu mirroring và dự phòng khôi phục** |
| `REQUIRED_MIRROR_FREE_MB` | Lượng không gian ước tính cần để khôi phục mức mirror được yêu cầu sau sự cố mất failure group phù hợp với loại redundancy |
| `USABLE_FILE_MB` | Dung lượng ước tính còn có thể sử dụng cho file mới khi xét redundancy và yêu cầu dự phòng |
| `TYPE` | Loại redundancy như `EXTERN`, `NORMAL`, `HIGH`, `FLEX` hoặc `EXTEND` tùy release |
| `OFFLINE_DISKS` | Số disk đang offline trong group |
| `STATE` | Trạng thái mount/quản lý của disk group |

Ở group NORMAL hoặc HIGH thông thường, phép tính khái niệm thường được diễn đạt:

```text
NORMAL: usable ≈ (free - required_mirror_free) / 2
HIGH:   usable ≈ (free - required_mirror_free) / 3
EXTERNAL: thường không có overhead mirror cấp ASM
```

Ví dụ chỉ để đọc ý nghĩa: một group NORMAL có `FREE_MB = 200000` và `REQUIRED_MIRROR_FREE_MB = 40000` thì lượng còn khả dụng theo công thức cơ bản xấp xỉ **80.000 MB**. Không thể kết luận còn đủ chỗ cho 200.000 MB file mới, vì mỗi dữ liệu có thể cần hai bản sao và cần dung lượng để khôi phục redundancy.

**`REQUIRED_MIRROR_FREE_MB` không nhất thiết là một phân vùng trống được khóa vật lý**. Đây là đại lượng quản trị phản ánh khả năng khôi phục sau mất failure group. Trong các disk group FLEX/EXTENDED, cách diễn giải dung lượng còn phức tạp hơn do chính sách theo file group/site: ưu tiên các view, quy tắc tính và hướng dẫn **đúng release**. `USABLE_FILE_MB` có thể âm nếu mức dư địa không đáp ứng nhu cầu dự phòng; âm không tự đồng nghĩa rằng database đã ngừng hoạt động ngay lập tức.

Ngoài các cột ASM còn phải theo dõi dung lượng thực của tablespace/datafile, FRA quota, backup retention và giới hạn tự mở rộng file. **Còn chỗ trong disk group** không có nghĩa mọi tablespace đều autoextend được mà không vướng quota, maxsize hoặc chính sách riêng.

## 7. Rebalance: khi thêm, thay hoặc bỏ ASM disk

ASM không gắn cứng tất cả file vào một disk duy nhất. Khi tài nguyên disk group thay đổi, ASM có thể phải **rebalance** để phân phối lại các extent:

```text
Ban đầu +DATA:       Disk A + Disk B
                       |       |
                       +-------+
                           |
       Thêm Disk C, ASM xác nhận membership
                           |
                      REBALANCE
                           |
       Phân bố lại một số file extents trên A/B/C
```

Rebalance giúp cân bằng việc sử dụng các disk theo cơ chế ASM, và khi một disk bị bỏ/đưa ra khỏi cấu hình, Oracle cần bố trí lại dữ liệu còn lại. Trong hệ thống có mirroring, các bản sao vẫn phải tuân thủ yêu cầu failure group.

Các thao tác thường gặp ở lớp quản trị:

- Thêm disk mới đủ điều kiện vào group.
- Thay disk bị lỗi hoặc đưa một disk ra khỏi group theo phương án được hỗ trợ.
- Tăng dung lượng LUN/resize disk và thông báo để ASM nhận diện.
- Quan sát tiến trình rebalance và mức độ ưu tiên/nguồn lực dành cho nó.

**Rebalance có chi phí I/O.** Database có thể tiếp tục hoạt động trong nhiều thao tác online được hỗ trợ, nhưng throughput và latency của workload có thể bị ảnh hưởng. Không được suy ra rằng add/drop disk luôn không có downtime bất kể sự cố, loại storage hay lượng dung lượng còn lại.

Tham số/cơ chế điều khiển **rebalance power** giúp quản trị đánh đổi giữa thời gian di chuyển dữ liệu và tài nguyên dành cho workload. Các view như `V$ASM_OPERATION` phản ánh công việc rebalance đang diễn ra, nhưng tên cột, trạng thái và cách điều khiển cụ thể phải theo release. **Không thực hiện `ALTER DISKGROUP ... DROP DISK` để “thử” trên hệ thống thật**: đó là thay đổi trực tiếp membership của storage.

## 8. Ranh giới ASM với filesystem, RAID và ACFS

### 8.1. ASM disk group không phải một mount point thông thường

So sánh hai đường dẫn:

```text
Filesystem:
  /u02/oradata/SALES/users01.dbf

ASM:
  +DATA/SALES/DATAFILE/users.257.123456789
```

Với filesystem, công cụ `ls`, `df`, `mount` và quyền OS giúp quan sát path/dung lượng. Với ASM, dấu `+DATA` nhận diện một **disk group** trong namespace ASM; không phải một thư mục `/DATA` được mount bình thường. Muốn xem cấu trúc ASM file, sử dụng **ASMCMD** hoặc các view/công cụ Oracle phù hợp quyền quản trị.

Một ASM file có thể gồm extents trên nhiều disk. Không thể xem `+DATA/SALES/...` như một pathname để copy bằng lệnh `cp` của shell thông thường. Các thao tác chuyển file Oracle giữa ASM và filesystem cần công cụ và trình tự đúng với loại file, ví dụ phương pháp database/RMAN/ASMCMD được Oracle hỗ trợ.

### 8.2. Filesystem vẫn tồn tại bên cạnh ASM

ASM không thay thế toàn bộ filesystem của máy chủ. Hệ điều hành và Oracle Grid/Database software thường vẫn nằm trên filesystem phù hợp, cùng với các file cấu hình, script, chương trình Java, audit/trace logs và nhiều file khác theo triển khai.

Một máy chủ có thể đồng thời có:

```text
/u01/app/oracle/...    -> Oracle software, công cụ, một số log
/var/log/...           -> OS logs
+DATA                  -> datafile/online redo do ASM quản lý
+RECO                  -> recovery/backup files do ASM quản lý
```

Không dùng công cụ `df -h` để đo trực tiếp `USABLE_FILE_MB` của `+DATA`, cũng không dùng `V$ASM_DISKGROUP` để biết ổ chứa source code Java còn trống bao nhiêu.

### 8.3. RAID/LVM/SAN nằm ở tầng nào?

RAID, volume manager, SAN và cloud block storage thuộc các tầng cung cấp hoặc bảo vệ **block devices**. ASM nằm ở phía Oracle, dùng các thiết bị đã được OS/hạ tầng cung cấp và quản lý chúng thành pool dành cho Oracle file.

```text
Đĩa vật lý / cloud volumes
          |
       RAID / SAN / LUN (tùy thiết kế)
          |
 OS nhìn thấy block device(s)
       /                 \
    Filesystem       ASM disk group
        |                 |
    /u02/...         +DATA/...
        \                 /
          Oracle Database
```

Nhiều lớp có thể phối hợp; sơ đồ không bắt buộc mọi hệ thống đều phải có RAID hay LVM. Việc chọn ASM EXTERNAL redundancy dựa vào lớp bảo vệ bên dưới cần được **xác minh** bằng cấu hình storage và thử nghiệm failure scenario, không đoán theo tên LUN.

### 8.4. Oracle ACFS có phải ASM không?

**Oracle ACFS (ASM Cluster File System)** là một **filesystem** được xây trên các thành phần Oracle ASM Dynamic Volume Manager (ADVM) trong cấu hình hỗ trợ. Nó có thể được OS mount thành đường dẫn thông thường để lưu những loại file phù hợp. Vì vậy:

| Hình thức | Namespace nhìn thấy | Cơ chế chính |
| --- | --- | --- |
| File Oracle trực tiếp trong ASM | `+DATA/...` | ASM quản lý file extents, không phải path OS bình thường |
| File trong XFS/ext4 hoặc filesystem OS khác | `/u02/...` | OS filesystem quản lý file trên volume/block device |
| File trong ACFS | Mount point dạng `/acfs/...` | ACFS/ADVM chạy trên hạ tầng ASM theo cấu hình được hỗ trợ |

**ACFS không đồng nghĩa một disk group được mount như XFS.** ACFS là một lớp filesystem bổ sung, có phạm vi hỗ trợ riêng về hệ điều hành, phiên bản Oracle và loại file. Không mặc định mọi Oracle Free/container hoặc dịch vụ cloud đều cho phép tạo ACFS.

## 9. Kiểm tra read-only trên môi trường có ASM

Các ví dụ sau cần một môi trường **đã được quản trị viên cài Oracle Grid Infrastructure/ASM**, cùng quyền quan sát phù hợp. Chúng không tạo, format, add hay drop disk. Nếu lab dùng Oracle Free trên filesystem thông thường, có thể **không có ASM instance/disk group**; đó là một khác biệt triển khai bình thường, không phải lỗi của bài học.

### 9.1. Xem disk group qua ASMCMD

Tại máy quản trị ASM có môi trường Oracle Grid Infrastructure/đặc quyền phù hợp:

```bash
asmcmd lsdg
asmcmd ls +DATA/
```

`lsdg` hiển thị các nhóm đã mount, type, tổng/free/usable space và các chỉ số liên quan tùy phiên bản. `ls +DATA/` duyệt namespace của disk group `DATA` nếu nó tồn tại và tài khoản có quyền. Tên các disk group phải lấy từ môi trường thật; không mặc định phòng lab nào cũng có `+DATA`.

### 9.2. Xem dung lượng từ ASM instance

Đăng nhập vào **ASM instance** bằng tài khoản được cấp quyền ASM phù hợp (đối với quản trị đầy đủ thường dùng quyền `SYSASM`), rồi chạy truy vấn **chỉ đọc**:

```sql
SELECT
    name,
    state,
    type,
    total_mb,
    free_mb,
    required_mirror_free_mb,
    usable_file_mb,
    offline_disks
FROM v$asm_diskgroup_stat
ORDER BY name;
```

View `V$ASM_DISKGROUP_STAT` cung cấp thông tin thống kê đã được ASM duy trì, thường phù hợp hơn cho truy vấn theo dõi lặp lại so với những thao tác yêu cầu disk discovery. Ví dụ kiểu kết quả:

```text
NAME   STATE    TYPE     TOTAL_MB FREE_MB REQ_MIR_FREE_MB USABLE_FILE_MB
DATA   MOUNTED  NORMAL     ...      ...         ...             ...
RECO   MOUNTED  EXTERN     ...      ...         ...             ...
```

Đây là kết quả **minh họa cấu trúc**, không có giá trị dung lượng giả định áp vào môi trường thật. `EXTERN` trong view biểu thị chế độ **EXTERNAL redundancy**.

### 9.3. Xem disk và failure group

```sql
SELECT
    g.name AS diskgroup_name,
    d.name AS asm_disk_name,
    d.failgroup,
    d.path,
    d.mount_status,
    d.header_status,
    d.state,
    d.total_mb,
    d.free_mb
FROM v$asm_disk_stat d
JOIN v$asm_diskgroup_stat g
  ON g.group_number = d.group_number
ORDER BY g.name, d.failgroup, d.name;
```

Từ đây, người học cần phân biệt:

- `PATH` là tên/đường dẫn nhận diện **block device/LUN** mà ASM thấy, không phải path của một bảng SQL.
- `FAILGROUP` cho biết nhóm miền lỗi mà disk được gán vào.
- `HEADER_STATUS` và `MOUNT_STATUS` giúp quan sát tình trạng disk theo ASM, nhưng **không tự là kết luận an toàn để đưa disk ra khỏi group**.
- `TOTAL_MB`/`FREE_MB` từng disk giúp xem phân bố không gian; cần đối chiếu toàn nhóm và hoạt động rebalance.

Đối với RAC/Flex ASM, cần biết mình đang kết nối tới ASM instance nào và phạm vi các view trả về. Không nên tự diễn giải trạng thái một node như trạng thái tuyệt đối của toàn cluster.

### 9.4. Database instance đang dùng file ở ASM hay filesystem?

Trên **Oracle Database instance**, tài khoản có quyền đọc dictionary/dynamic views có thể xem:

```sql
-- Các datafile của database/container hiện tại theo quyền đang có
SELECT tablespace_name, file_name
FROM dba_data_files
ORDER BY tablespace_name, file_name;

-- Online redo log members
SELECT group#, member
FROM v$logfile
ORDER BY group#, member;

-- Cấu hình đích OMF/FRA
SELECT name, value
FROM v$parameter
WHERE name IN ('db_create_file_dest', 'db_recovery_file_dest')
ORDER BY name;
```

Nếu `FILE_NAME` bắt đầu bằng `+DATA/...`, đó là **ASM-managed file**. Nếu thấy `/u02/oradata/...`, file được đặt theo đường dẫn filesystem. Một database cũng có thể sử dụng **cả hai kiểu** trong một giai đoạn hoặc cấu hình được hỗ trợ; không kết luận dựa vào một file đơn lẻ.

Trong CDB/PDB, `DBA_DATA_FILES` có phạm vi phụ thuộc **container hiện tại**; DBA có thể cần các `CDB_*` views và quyền tương ứng để xem nhiều PDB. Không nhầm trường `TABLESPACE_NAME` với tên ASM disk group.

### 9.5. Quan sát rebalance khi có thay đổi storage

Đối với quản trị viên đã có quyền và đang có một hoạt động rebalance thực sự:

```sql
SELECT group_number, operation, state, power, actual, sofar, est_work
FROM v$asm_operation;
```

Các cột và nội dung phụ thuộc version/cơ chế rebalance. Nếu view không trả dòng, có thể chỉ là **không có operation phù hợp đang được theo dõi**. Bài thực hành ở đây chỉ quan sát, không chủ động tạo một đợt thay đổi disk để sinh số liệu.

## 10. Chọn ASM hay filesystem cho từng tình huống

| Tình huống | Hướng lựa chọn hợp lý | Lý do |
| --- | --- | --- |
| Học SQL/JDBC trên laptop, Oracle Free container có sẵn volume | **Filesystem/volume do môi trường cung cấp** | Đủ mục tiêu SQL, giảm độ phức tạp triển khai Grid Infrastructure |
| Lab chuyên về ASM disk group, mirroring và rebalance | **Môi trường ASM do DBA/giảng viên cấp** | Cần thiết bị, quyền quản trị storage và topology lỗi kiểm soát được |
| Single-instance Oracle có storage SAN/RAID quản lý tốt | **ASM hoặc filesystem** theo yêu cầu vận hành | Đánh giá toolchain, redundancy, backup và đội ngũ quản trị |
| Oracle RAC với shared storage | **ASM trong kiến trúc được Oracle hỗ trợ**, thường qua Grid Infrastructure | Quản lý shared database storage và phối hợp với cluster |
| Dịch vụ Autonomous Database/cloud được quản lý | **Theo storage interface dịch vụ cung cấp** | Nhà cung cấp có thể ẩn ASM và không cấp quyền SYSASM |
| Muốn lưu source code, script triển khai, tập tin OS tùy ý | **Filesystem/object storage thích hợp** | ASM disk group trực tiếp không phải filesystem tổng quát |
| Cần filesystem do OS mount nhưng dùng hạ tầng Oracle ASM | **Đánh giá ACFS/ADVM nếu platform hỗ trợ** | ACFS là filesystem riêng, có yêu cầu triển khai và licensing/support cần xác minh |

### Bốn câu hỏi trước khi quyết định

1. **Workload cần lưu gì?** Datafile/redo/backup của Oracle hay file tùy ý cho hệ điều hành/ứng dụng?
2. **Ai quản lý failure domain?** ASM failure group, RAID/SAN, cloud block storage hay kết hợp có chủ đích?
3. **Cần đặc tính nào?** Share storage giữa nhiều instance RAC, online rebalance, tách DATA/RECO, tự tạo file OMF, hoặc chỉ cần mount filesystem đơn giản?
4. **Môi trường có hỗ trợ và quyền quản trị không?** Grid Infrastructure, release/edition, OS, disk discovery, SYSASM, quy trình thay disk và chính sách backup?

Chọn ASM chỉ vì nghe “tối ưu hơn filesystem” là thiếu cơ sở. Hiệu năng phụ thuộc workload I/O, số lượng và chất lượng thiết bị, cache, network/storage fabric, cách striping và mirroring, độ trễ cũng như vận hành; không thể gán một kết quả benchmark phổ quát cho mọi hệ thống.

## 11. Các lỗi nhận thức thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`+DATA` là thư mục trong `/` của Linux.” | `+DATA` là namespace của ASM disk group, không phải mount point filesystem thông thường. |
| “ASM disk group tương đương Oracle tablespace.” | Disk group chứa file; tablespace là đối tượng logic của database và dùng datafile/tempfile. |
| “ASM instance là instance thực thi SQL của ứng dụng.” | ASM instance quản lý storage metadata; database instance xử lý SQL, transaction và database recovery. |
| “Mỗi database phải có ASM disk group riêng.” | Nhiều database có thể chia sẻ disk group theo thiết kế; một database có thể dùng nhiều group. |
| “NORMAL có hai bản sao nên bất kỳ hai disk nào đều đủ.” | Mirror phải nằm trong những **failure group** thích hợp; miền lỗi phần cứng quyết định khả năng chịu sự cố. |
| “ASM EXTERNAL redundancy nghĩa là chắc chắn không có bản sao.” | ASM không tự mirror nhưng storage bên dưới có thể có RAID/mirroring hoặc cơ chế bảo vệ khác. |
| “`FREE_MB` chính là dung lượng user data có thể ghi thêm.” | Phải xét mirroring, `REQUIRED_MIRROR_FREE_MB`, `USABLE_FILE_MB` và quota/file limits riêng. |
| “ASM mirroring thay thế backup.” | Backup/recovery vẫn cần cho logical error, corruption, yêu cầu point-in-time và sự cố toàn hệ thống. |
| “Khi ASM rebalance, database luôn không bị ảnh hưởng.” | Rebalance dùng I/O và tài nguyên; thời gian, latency và rủi ro phụ thuộc workload, topology và thay đổi. |
| “ACFS là cách mount trực tiếp `+DATA` như XFS.” | ACFS là lớp filesystem trên ADVM/ASM trong cấu hình hỗ trợ; không biến ASM disk group thành thư mục OS thông thường. |
| “Oracle Database Free luôn có sẵn ASM cho lab.” | Nhiều cài đặt Free/container dùng filesystem; ASM cần môi trường và quyền cấu hình riêng được hỗ trợ. |

## 12. Bài thực hành và bài tập tư duy

### Bài 1 — Phân loại thành phần

Cho các tên sau:

```text
/u02/oradata/SALES/system01.dbf
+DATA
+DATA/SALES/DATAFILE/system.257.123456789
ASM instance
Oracle Database instance
ASM disk DATA_0001
Failure group RACK_B
Tablespace USERS
RMAN backup
ACFS mount /acfs/reports
```

Hãy phân loại chúng theo **filesystem path**, **ASM disk group**, **ASM file**, **ASM disk**, **fault domain**, **database logic**, **instance** hoặc **backup/filesystem layer**. Giải thích vì sao `Tablespace USERS` không xác định ngay một disk hay path OS cụ thể.

### Bài 2 — Thiết kế failure group

Một nhóm được cấp 6 disk từ hai tủ lưu trữ vật lý. Mỗi tủ có cùng nguồn và cùng controller; mỗi tủ chứa 3 disk.

1. Nếu cấu hình ASM NORMAL redundancy, nên định nghĩa failure group theo **tủ/controller** như thế nào?
2. Nếu để mỗi disk thành một failure group mà không tính chuyện cả tủ mất điện, giả định mirror nào có thể sai?
3. Nếu cần HIGH redundancy, việc chỉ có **hai tủ độc lập** có đáp ứng ý tưởng ba miền lỗi không?
4. Backup nên đặt ở đâu để không cùng hỏng khi hai tủ và máy chủ mất hoàn toàn?

**Gợi ý:** failure group phải phản ánh phạm vi sự cố chung; không đơn thuần đếm số disk. HIGH redundancy về nguyên tắc cần ba failure domain phù hợp. Backup độc lập về vị trí/quyền truy cập là yêu cầu khác mirroring.

### Bài 3 — Đọc một báo cáo dung lượng

Quản trị viên thấy một ASM group NORMAL có các chỉ số **minh họa**:

```text
FREE_MB                 = 200000
REQUIRED_MIRROR_FREE_MB = 40000
```

Theo công thức cơ bản cho NORMAL, dung lượng file hữu dụng mới xấp xỉ:

```text
(200000 - 40000) / 2 = 80000 MB
```

Trả lời:

- Vì sao không thể tạo thêm ngay 200.000 MB dữ liệu ứng dụng chỉ dựa trên `FREE_MB`?
- Tại sao việc sử dụng gần hết `USABLE_FILE_MB` vẫn cần được quản trị viên cân nhắc về ngưỡng cảnh báo và khả năng phục hồi?
- Khi dữ liệu nằm trong một tablespace với `MAXSIZE` hoặc user quota riêng, số ASM usable có tự bảo đảm lệnh ghi sẽ thành công không?

**Gợi ý:** dung lượng ASM, dung lượng file/tablespace và quyền sử dụng là các ranh giới khác nhau.

### Bài 4 — Lab quan sát read-only

Trên hệ thống do giảng viên cấp có ASM và tài khoản phù hợp:

1. Chạy `asmcmd lsdg` và ghi lại **NAME**, **TYPE**, **FREE_MB**, **USABLE_FILE_MB** của một disk group.
2. Dùng `V$ASM_DISKGROUP_STAT` đối chiếu trạng thái mount, số disk offline và redundancy.
3. Dùng `V$ASM_DISK_STAT` liệt kê failure group. Vẽ sơ đồ mỗi failure group và các ASM disk thuộc nó.
4. Từ database instance, đọc `DBA_DATA_FILES.FILE_NAME` và ghi rõ file nào dùng namespace `+GROUP/...`, file nào dùng path filesystem.
5. Viết một đoạn giải thích: khi ứng dụng cập nhật bảng, database instance và ASM instance mỗi bên thực hiện vai trò gì?

**Đầu ra mong đợi:** bảng quan sát và sơ đồ có tên thực của môi trường; không cần add/drop disk hay thay đổi cấu hình.

### Bài 5 — Chọn storage cho một dự án

Dự án A là bài JDBC CRUD trên laptop cá nhân có Docker và dung lượng hạn chế. Dự án B là hệ thống RAC ba node cần dung lượng lớn, quản trị online và có team storage chuyên trách. Dự án C là ứng dụng xuất PDF cần thư mục được service Java và nhiều tiến trình OS dùng chung.

Với mỗi dự án, đề xuất **filesystem, ASM hoặc ACFS theo platform hỗ trợ**, nêu ranh giới dữ liệu sẽ lưu ở đâu và cách quản trị backup. Trong giải thích, phải phân biệt redundancy do storage với tính bền vững của transaction và khả năng restore.

## 13. Kết luận kiến trúc

**Oracle ASM** tổ chức các **ASM disk** thành **disk group**, bố trí **ASM file extents** trên những thiết bị và tùy cấu hình thực hiện **striping, mirroring, rebalance**. **Failure group** mô tả miền lỗi để các bản sao không phụ thuộc cùng một thành phần vật lý. **EXTERNAL**, **NORMAL**, **HIGH** và các dạng redundancy mở rộng quyết định chiến lược bảo vệ/dung lượng; việc đánh giá capacity phải nhìn **`USABLE_FILE_MB`** cùng các giới hạn khác thay vì chỉ nhìn `FREE_MB`.

Tại ranh giới phần mềm, **database instance** xử lý SQL và I/O database, **ASM instance** quản lý storage metadata và disk groups, còn **filesystem của hệ điều hành** tiếp tục đảm nhiệm các file OS/ứng dụng phù hợp. Dấu `+DATA` là một đường dẫn ASM logic, không phải thư mục thường. Hiểu rành mạch các lớp này giúp thiết kế storage có khả năng chịu lỗi, đọc thông tin quản trị chính xác và tránh nhầm ASM mirroring với backup.

## Tài liệu tham khảo

- [Oracle Automatic Storage Management Administrator's Guide — Oracle Database 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/ostmg/) — khái niệm ASM instance, disk group, failure group, redundancy, file và rebalance.
- [Oracle Database Concepts — Oracle Database Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — phân biệt database files, tablespace/segment và lưu trữ logic.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — mô tả `V$ASM_DISKGROUP_STAT`, `V$ASM_DISK_STAT`, `V$ASM_OPERATION` và các chỉ số dung lượng.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — lý do vẫn cần chiến lược backup, restore và archived redo khi đã có mirroring.

Các thủ tục quản trị disk group, khả năng hỗ trợ ACFS/ADVM, Flex/Extended redundancy và quyền sử dụng phụ thuộc **Oracle release, edition, Grid Infrastructure, OS và platform cloud**. Khi triển khai thật, tra lại tài liệu chính xác của môi trường và dùng quy trình thay đổi storage được phê duyệt.
