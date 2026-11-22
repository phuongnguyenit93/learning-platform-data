# Cấu hình RMAN channel, device type và vị trí lưu backup

RMAN (Recovery Manager) là công cụ của Oracle Database dùng để sao lưu, phục hồi và quản lý các bản backup. Khi chạy một lệnh như **BACKUP DATABASE**, RMAN cần biết dữ liệu sẽ được đọc bằng cách nào, thiết bị đích thuộc loại nào, có bao nhiêu luồng xử lý đồng thời và backup piece sẽ được ghi ở đâu.

Ba khái niệm cần phân biệt:

- **Device type** xác định loại thiết bị mà RMAN sử dụng, phổ biến nhất là **DISK** và **SBT** (System Backup to Tape). DISK thường là filesystem, ASM hoặc vùng lưu trữ được cấu hình làm Fast Recovery Area (FRA). SBT thường kết nối với tape library hoặc hệ thống backup thông qua SBT media management library.
- **Channel** là kết nối/luồng làm việc mà RMAN cấp phát để một server session đọc dữ liệu và ghi backup hoặc đọc backup để restore. Mỗi channel có cấu hình riêng về device type, định dạng đích, tham số media manager và một số giới hạn tài nguyên.
- **Backup location** là vị trí lưu backup piece. Với DISK, đây thường là đường dẫn filesystem, ASM disk group hoặc FRA. Với SBT, việc lưu trữ và định danh media do media manager quản lý.

Cấu hình đúng giúp RMAN sử dụng đúng thiết bị, phân phối công việc hợp lý và lưu backup ở nơi có thể truy cập khi cần restore. Cấu hình sai có thể làm backup thất bại, tạo file ở vị trí không mong muốn, thiếu dung lượng, không truy cập được từ node khác hoặc không thể khôi phục khi xảy ra sự cố.

## 1. RMAN channel là gì?

Channel là tài nguyên thực thi mà RMAN sử dụng để thực hiện một thao tác backup, restore, copy hoặc một số tác vụ bảo trì. Khi RMAN cấp phát channel, Oracle tạo server session tương ứng để đọc hoặc ghi dữ liệu theo yêu cầu.

Một channel thường gắn với một device type. Ví dụ:

- Channel loại DISK ghi backup piece ra filesystem, ASM hoặc FRA.
- Channel loại SBT chuyển dữ liệu qua SBT interface đến media management software.
- Channel có thể có cấu hình riêng như FORMAT, PARMS, MAXPIECESIZE hoặc RATE.

RMAN có thể cấp phát channel tự động dựa trên cấu hình persistent được lưu trong control file hoặc recovery catalog. Người quản trị cũng có thể cấp phát channel thủ công trong một khối RUN để chỉ định rõ cách chạy cho một công việc cụ thể.

### Channel và backup piece

Khi RMAN tạo backupset, dữ liệu backup được ghi thành một hoặc nhiều backup piece. Channel thực hiện việc đọc các datafile, archive log hoặc thành phần cần backup rồi ghi các piece ra thiết bị đích.

Một backupset có thể có nhiều backup piece. Mỗi channel có thể tạo một hoặc nhiều piece tùy dữ liệu, cấu hình và lệnh backup. Vì thế, số channel không nhất thiết bằng số backup piece, số datafile hoặc số backupset.

Tên channel là tên logic dùng trong lệnh RMAN, ví dụ **ch1**, **ch2**. Tên này không phải tên file backup và cũng không phải tên OS process. Khi RMAN tự động cấp phát channel, RMAN đặt tên theo quy tắc nội bộ.

## 2. Device type: DISK và SBT

Device type mô tả phương tiện RMAN dùng để đọc/ghi backup. Lựa chọn device type ảnh hưởng đến channel được cấp phát, cách định danh backup piece và cách cấu hình vị trí lưu.

| Device type | Mục đích | Cách lưu trữ thường gặp |
|---|---|---|
| DISK | Sao lưu trực tiếp ra thiết bị dạng đĩa | Filesystem, ASM hoặc Fast Recovery Area |
| SBT | Sao lưu thông qua SBT media management layer | Tape library, virtual tape library hoặc hệ thống backup tích hợp qua SBT |

### DISK

DISK phù hợp khi backup được lưu trên filesystem, ASM hoặc FRA. Đây là lựa chọn thường gặp cho backup local, backup ra shared storage hoặc vùng recovery của Oracle.

Ví dụ cấu hình thiết bị mặc định:

~~~sql
CONFIGURE DEFAULT DEVICE TYPE TO DISK;
~~~

Khi lệnh BACKUP không chỉ định device type khác, RMAN sử dụng device type mặc định và cấu hình channel tương ứng.

DISK không đồng nghĩa với một thư mục cụ thể. Đường dẫn có thể được chỉ định bằng FORMAT; nếu không chỉ định FORMAT, Oracle có thể sử dụng FRA khi FRA được cấu hình, hoặc vị trí mặc định theo môi trường. Với ASM, đường dẫn có thể là tên disk group như **+FRA**.

### SBT

SBT được sử dụng khi RMAN tích hợp với phần mềm quản lý backup. Media manager cung cấp thư viện SBT và xử lý việc lưu, định danh, truy xuất backup piece trên tape hoặc hệ thống lưu trữ tương thích.

RMAN không tự biết cách ghi trực tiếp vào mọi sản phẩm backup. Cần cài đặt và cấu hình media management software theo hướng dẫn của nhà cung cấp, bao gồm thư viện SBT, biến môi trường và thông tin kết nối cần thiết.

Một cấu hình SBT minh họa:

~~~sql
CONFIGURE DEFAULT DEVICE TYPE TO SBT;

CONFIGURE DEVICE TYPE SBT PARALLELISM 2;

CONFIGURE CHANNEL DEVICE TYPE SBT
  PARMS 'SBT_LIBRARY=/path/to/libobk.so, ENV=(MEDIA_SERVER=backup01)';
~~~

Đường dẫn thư viện và biến môi trường trong ví dụ chỉ là placeholder. Phải thay bằng thông tin chính xác từ tài liệu của media manager đã cài đặt. Một số sản phẩm sử dụng cấu hình khác hoặc tự cung cấp thư viện mặc định.

Với SBT, backup piece được chuyển cho media manager. FORMAT, nếu được sử dụng, thường đóng vai trò tên/handle mà media manager nhận diện, không phải đường dẫn filesystem thông thường. Quy tắc đặt tên và truy xuất piece phụ thuộc sản phẩm backup.

### Chọn DISK hay SBT

Chọn DISK khi cần lưu trên storage mà Oracle có thể truy cập trực tiếp, ví dụ filesystem, ASM hoặc FRA. Chọn SBT khi tổ chức sử dụng hệ thống backup tập trung, tape hoặc giải pháp media management tích hợp.

Một database có thể sử dụng cả DISK và SBT. Ví dụ, backup gần nhất được lưu trên DISK để restore nhanh, sau đó backup được chuyển sang tape hoặc hệ thống SBT để lưu dài hạn. Khi dùng nhiều device type, cần cấu hình channel cho từng loại và chỉ rõ device type trong lệnh nếu muốn kiểm soát nơi backup được ghi.

## 3. Cấu hình channel tự động bằng CONFIGURE

Cấu hình CONFIGURE được lưu bền vững trong repository RMAN. Các lệnh backup sau đó có thể sử dụng các thiết lập này mà không cần viết lại ALLOCATE CHANNEL trong từng RUN block.

### Cấu hình số channel và parallelism

Ví dụ yêu cầu RMAN tự động cấp hai channel DISK:

~~~sql
CONFIGURE DEFAULT DEVICE TYPE TO DISK;

CONFIGURE DEVICE TYPE DISK
  PARALLELISM 2
  BACKUP TYPE TO BACKUPSET;
~~~

**PARALLELISM 2** yêu cầu RMAN cấp tối đa hai channel tự động cho device type DISK khi thực hiện công việc phù hợp. Đây là mức cấu hình song song của RMAN cho thiết bị đó, không phải cam kết rằng mọi lệnh đều luôn sử dụng đủ hai channel. Khối lượng công việc, số file, cấu trúc backup và tài nguyên thực tế có thể khiến số channel hoạt động khác nhau.

Với SBT, có thể cấu hình tương tự:

~~~sql
CONFIGURE DEVICE TYPE SBT PARALLELISM 2;
~~~

Đồng thời phải có cấu hình channel SBT phù hợp với media manager. Tăng parallelism quá cao có thể vượt số tape drive hoặc giới hạn kết nối của media manager, tăng tải CPU/I/O và làm các công việc backup khác cạnh tranh tài nguyên.

### Cấu hình FORMAT cho channel DISK

Có thể cấu hình một mẫu tên file dùng chung cho các channel DISK:

~~~sql
CONFIGURE CHANNEL DEVICE TYPE DISK
  FORMAT '/backup/rman/%d_%T_%U.bkp';
~~~

Trong đó:

- **%d**: database name.
- **%T**: ngày theo định dạng YYYYMMDD.
- **%U**: chuỗi duy nhất do RMAN tạo, thường được dùng để tránh trùng tên backup piece.

FORMAT cần tạo ra tên duy nhất cho các piece. Sử dụng **%U** là cách thuận tiện vì RMAN tự sinh thành phần định danh. Nếu tự ghép tên từ database name và ngày mà không có thành phần duy nhất, các lần backup hoặc nhiều channel có thể ghi đè hay va chạm tên.

Có thể cấu hình đường dẫn riêng cho từng channel tự động:

~~~sql
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;

CONFIGURE CHANNEL 1 DEVICE TYPE DISK
  FORMAT '/backup/disk1/%d_%T_%U.bkp';

CONFIGURE CHANNEL 2 DEVICE TYPE DISK
  FORMAT '/backup/disk2/%d_%T_%U.bkp';
~~~

Cách này cho phép phân bổ channel ra các filesystem hoặc mount point khác nhau. Cần bảo đảm cả hai đường dẫn đều tồn tại, Oracle OS user có quyền ghi và các vị trí có đủ dung lượng. Nếu channel 1 và channel 2 cùng trỏ đến một filesystem, việc cấu hình hai channel không tự tạo thêm năng lực lưu trữ.

### Các tham số channel thường dùng

| Tham số | Tác dụng |
|---|---|
| FORMAT | Mẫu tên hoặc vị trí backup piece; với DISK thường là đường dẫn file |
| PARMS | Tham số truyền cho media manager hoặc thiết bị; thường dùng với SBT |
| MAXPIECESIZE | Giới hạn kích thước tối đa của một backup piece |
| RATE | Giới hạn tốc độ đọc dữ liệu đầu vào của channel, hữu ích khi cần giảm tác động I/O |
| CONNECT | Dùng trong ALLOCATE CHANNEL để chỉ định kết nối server session trong các cấu hình đặc biệt |

Không phải mọi tham số đều áp dụng cho mọi device type. Ví dụ, PARMS thường quan trọng với SBT; FORMAT trên SBT có ý nghĩa theo cách media manager diễn giải handle. Hãy kiểm tra cú pháp theo phiên bản Oracle và sản phẩm media manager.

## 4. Cấp phát channel thủ công bằng ALLOCATE CHANNEL

Nếu cần cấu hình riêng cho một job, có thể cấp phát channel trong RUN block. Các channel thủ công chỉ tồn tại trong phạm vi công việc đó.

Ví dụ backup database bằng hai channel DISK:

~~~sql
RUN {
  ALLOCATE CHANNEL ch1 DEVICE TYPE DISK
    FORMAT '/backup/rman/%d_%T_%U.bkp';

  ALLOCATE CHANNEL ch2 DEVICE TYPE DISK
    FORMAT '/backup/rman/%d_%T_%U.bkp';

  BACKUP AS COMPRESSED BACKUPSET DATABASE
    PLUS ARCHIVELOG;
}
~~~

Ở đây, RMAN dùng hai channel đã cấp phát trong RUN block. Mỗi channel có thể xử lý một phần công việc, tùy cách RMAN phân phối datafile và backup set. Mẫu **%U** giúp tạo tên piece duy nhất ngay cả khi nhiều channel cùng ghi vào một thư mục.

Có thể chỉ định rõ thiết bị trong lệnh backup:

~~~sql
RUN {
  ALLOCATE CHANNEL disk_ch DEVICE TYPE DISK
    FORMAT '/backup/rman/%d_%T_%U.bkp';

  BACKUP DEVICE TYPE DISK DATABASE;
}
~~~

Nếu cấp phát channel thủ công cho một device type trong job, RMAN dùng các channel được cấp phát thủ công cho device type đó thay cho việc tự động cấp phát channel cùng loại cho job đó. Vì vậy, cần cấp đủ channel cần thiết trong RUN block. Cấu hình tự động vẫn có thể được sử dụng cho device type khác nếu job có sử dụng và cấu hình phù hợp.

### Khi nào dùng CONFIGURE, khi nào dùng ALLOCATE?

| Tiêu chí | CONFIGURE CHANNEL | ALLOCATE CHANNEL |
|---|---|---|
| Phạm vi | Cấu hình persistent trong RMAN repository | Một RUN block hoặc job |
| Mục đích | Thiết lập mặc định dùng lặp lại | Tùy biến cho một lần backup/restore |
| Quản lý | Dùng SHOW ALL để xem, CONFIGURE ... CLEAR để xóa thiết lập | Channel tự được giải phóng khi kết thúc RUN block |
| Ví dụ | Backup hàng ngày luôn dùng hai channel DISK | Một job đặc biệt cần ghi sang hai mount point riêng |

Thông thường nên dùng CONFIGURE cho chính sách chung đã được chuẩn hóa. Dùng ALLOCATE khi có yêu cầu riêng theo job, ví dụ backup thử nghiệm, backup vào vị trí tạm, dùng tham số SBT đặc biệt hoặc cần giới hạn tài nguyên cho một lần chạy.

## 5. Cấu hình vị trí lưu backup trên DISK

### Lưu trên filesystem

Filesystem là cách lưu backup trực tiếp vào thư mục trên máy chủ. Ví dụ:

~~~sql
CONFIGURE DEFAULT DEVICE TYPE TO DISK;
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;

CONFIGURE CHANNEL DEVICE TYPE DISK
  FORMAT '/u03/backup/rman/%d_%T_%U.bkp';

BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Trước khi chạy, cần kiểm tra:

- Thư mục đích đã được tạo.
- Oracle Database software owner có quyền tạo và ghi file.
- Filesystem được mount ổn định.
- Dung lượng trống đáp ứng kích thước backup và mức tăng dữ liệu.
- Có chính sách dọn dẹp và giám sát dung lượng.
- Nếu dùng RAC, đường dẫn có thể truy cập được từ các instance có khả năng thực thi channel.

Không nên lưu bản backup duy nhất trên cùng ổ đĩa vật lý với datafile nếu mục tiêu là bảo vệ trước sự cố mất ổ đĩa. Backup cần được bảo vệ độc lập với dữ liệu nguồn.

### Lưu trên ASM

Nếu hệ thống sử dụng ASM, RMAN có thể ghi backup vào disk group. Ví dụ:

~~~sql
CONFIGURE CHANNEL DEVICE TYPE DISK
  FORMAT '+FRA';

BACKUP DATABASE;
~~~

Trong thực tế, khi ghi vào ASM, có thể chỉ định disk group thay vì tên file cụ thể; ASM và Oracle quản lý tên file. Cần bảo đảm disk group tồn tại, có đủ dung lượng và được mount trên các instance cần dùng. Không dùng đường dẫn filesystem như **/backup/rman** khi mục tiêu là ghi trực tiếp vào ASM.

### Sử dụng Fast Recovery Area (FRA)

Fast Recovery Area là vùng lưu trữ do Oracle quản lý cho các file liên quan đến backup và recovery, chẳng hạn backup piece, archived redo log, flashback log và control file autobackup tùy cấu hình.

Có thể cấu hình FRA bằng tham số database:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 200G
  SCOPE = BOTH;

ALTER SYSTEM SET db_recovery_file_dest = '/u04/fra'
  SCOPE = BOTH;
~~~

Nếu dùng ASM, giá trị DB_RECOVERY_FILE_DEST có thể là disk group, ví dụ **+FRA**. Thứ tự cấu hình có thể được thực hiện theo quy trình quản trị phù hợp; cần xác nhận đường dẫn hoặc disk group hợp lệ và dung lượng thực tế.

Khi FRA được cấu hình và lệnh backup không chỉ định FORMAT ghi ra nơi khác, RMAN có thể sử dụng FRA làm đích mặc định cho backup trên DISK. FORMAT được chỉ định rõ trong lệnh BACKUP hoặc channel sẽ điều khiển vị trí/định dạng piece theo cấu hình đó.

FRA có lợi vì Oracle theo dõi việc sử dụng dung lượng và quản lý các file recovery theo chính sách retention, archived log deletion và các quy tắc reclaimable space. Tuy nhiên, FRA không tự động bảo đảm còn đủ dung lượng cho mọi lần backup. Cần đặt DB_RECOVERY_FILE_DEST_SIZE phù hợp, giám sát dung lượng và bảo đảm storage bên dưới còn chỗ.

Có thể kiểm tra FRA:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM   v$recovery_file_dest;
~~~

Kiểm tra mức sử dụng theo loại file:

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM   v$flash_recovery_area_usage
ORDER BY file_type;
~~~

Tên view và thông tin hiển thị có thể khác theo phiên bản; trên các phiên bản Oracle mới vẫn thường gặp các view tương thích có tên trên. Cần đối chiếu data dictionary của phiên bản đang vận hành.

### FORMAT ở đâu có hiệu lực?

RMAN có thể nhận FORMAT từ nhiều vị trí. Cần hiểu thứ tự ưu tiên khi muốn kiểm soát vị trí ghi:

1. FORMAT được chỉ định trực tiếp trong lệnh BACKUP áp dụng cho công việc đó.
2. FORMAT được cấu hình cho channel tương ứng.
3. Nếu không có FORMAT cụ thể, RMAN có thể sử dụng FRA khi FRA được cấu hình.
4. Nếu không có FRA phù hợp, RMAN sử dụng vị trí mặc định theo môi trường Oracle.

Ví dụ FORMAT trực tiếp trong lệnh:

~~~sql
BACKUP DATABASE
  FORMAT '/backup/monthly/%d_%T_%U.bkp';
~~~

Thiết lập trong lệnh chỉ tác động đến lần backup đó. Nó không thay đổi cấu hình channel persistent. Nếu backup dùng nhiều channel, FORMAT phải tạo được tên piece duy nhất cho tất cả channel.

Đối với control file autobackup, có cấu hình FORMAT riêng. Không nên giả định FORMAT của một lệnh BACKUP thông thường sẽ điều khiển tên và vị trí của control file autobackup.

## 6. Cấu hình control file autobackup

Control file chứa thông tin quan trọng về cấu trúc database và RMAN repository. Nếu control file bị mất, việc phục hồi có thể cần control file autobackup để RMAN nhận diện backup và tiến hành restore.

Có thể bật tự động backup control file:

~~~sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Có thể cấu hình FORMAT riêng cho control file autobackup trên DISK:

~~~sql
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT
  FOR DEVICE TYPE DISK
  TO '/backup/rman/cf_%F';
~~~

Placeholder **%F** là định dạng đặc biệt dành cho control file autobackup, chứa DBID và thông tin ngày/sequence theo quy tắc của RMAN. Khi đặt FORMAT riêng, cần bảo đảm đường dẫn tồn tại, có quyền ghi và vị trí backup được bảo vệ.

Nếu dùng SBT, có thể cấu hình control file autobackup cho device type SBT theo cơ chế và khả năng của media manager. Cần kiểm tra chính sách lưu trữ của sản phẩm backup.

Việc bật autobackup không thay thế backup database và archived redo log. Nó giúp bảo vệ control file và SPFILE trong các tình huống cần khôi phục metadata.

## 7. Cấu hình SBT channel và media manager

Khi backup ra tape hoặc hệ thống lưu trữ tích hợp, RMAN cần một SBT channel. Media manager phải được cài đặt đúng trên các máy chủ có thể chạy channel, thư viện phải được Oracle nạp được và các thông số môi trường phải khớp cấu hình của nhà cung cấp.

Ví dụ cấu hình mang tính minh họa:

~~~sql
CONFIGURE DEFAULT DEVICE TYPE TO SBT;

CONFIGURE DEVICE TYPE SBT PARALLELISM 2;

CONFIGURE CHANNEL DEVICE TYPE SBT
  PARMS 'SBT_LIBRARY=/opt/backup/lib/libobk.so, ENV=(SERVER=media01)';
~~~

Trong một số môi trường, thư viện được cài đặt ở đường dẫn khác hoặc được cung cấp thông qua cơ chế tích hợp riêng. Không sao chép nguyên đường dẫn mẫu vào production. Tham số PARMS phải theo hướng dẫn của nhà cung cấp media manager.

Có thể kiểm tra job SBT bằng lệnh backup:

~~~sql
BACKUP DEVICE TYPE SBT DATABASE PLUS ARCHIVELOG;
~~~

Nếu cần dùng cả DISK và SBT, có thể cấu hình channel cho hai device type rồi chỉ định thiết bị ở từng lệnh:

~~~sql
BACKUP DEVICE TYPE DISK DATABASE;
BACKUP DEVICE TYPE SBT ARCHIVELOG ALL;
~~~

Cách dùng hai lệnh là ví dụ cho hai job/hoạt động riêng. Nếu muốn copy backup từ DISK sang SBT, hãy sử dụng lệnh RMAN phù hợp như BACKUP BACKUPSET hoặc quy trình backup/copy mà media manager hỗ trợ; không giả định rằng một backup piece DISK tự động xuất hiện trên SBT.

## 8. Điều chỉnh parallelism và phân bổ channel

Tăng số channel có thể giúp RMAN đọc nhiều file hoặc ghi nhiều backup piece đồng thời. Tuy nhiên, số channel không nên được chọn chỉ theo số CPU core.

Các yếu tố cần cân nhắc:

- **Năng lực đọc nguồn:** datafile nằm trên storage có đủ băng thông để nhiều channel đọc đồng thời hay không.
- **Năng lực ghi đích:** filesystem, ASM hoặc media manager có đủ thông lượng và số kết nối không.
- **CPU:** compression và encryption có thể tiêu thụ CPU đáng kể.
- **Bộ nhớ và I/O:** nhiều channel cùng hoạt động làm tăng nhu cầu buffer và I/O đồng thời.
- **Số tape drive hoặc stream:** SBT có thể bị giới hạn bởi số thiết bị hoặc giới hạn song song của media manager.
- **Tải production:** backup không nên làm ảnh hưởng quá mức đến workload ứng dụng.

Ví dụ cấu hình hai channel:

~~~sql
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
~~~

Nếu hệ thống có đủ storage bandwidth và cần thử mức song song cao hơn, có thể tăng dần, đo elapsed time, CPU, I/O và ảnh hưởng đến workload. Không nên tăng từ 2 lên 16 mà không có phép đo hoặc kiểm tra giới hạn tài nguyên.

Có thể cấu hình channel riêng cho từng đích:

~~~sql
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;

CONFIGURE CHANNEL 1 DEVICE TYPE DISK
  FORMAT '/backup_a/%d_%T_%U.bkp';

CONFIGURE CHANNEL 2 DEVICE TYPE DISK
  FORMAT '/backup_b/%d_%T_%U.bkp';
~~~

Cấu hình này hữu ích khi hai mount point độc lập và có khả năng ghi đồng thời. Nếu một đích đầy hoặc không truy cập được, job có thể thất bại ở channel tương ứng. Cần theo dõi từng filesystem và kiểm tra khả năng phục hồi từ các piece được phân tán trên nhiều vị trí.

## 9. Kiểm tra cấu hình RMAN hiện tại

Trong RMAN, dùng SHOW ALL để xem các cấu hình persistent:

~~~rman
SHOW ALL;
~~~

Có thể xem riêng device type hoặc channel:

~~~rman
SHOW DEVICE TYPE;
SHOW CHANNEL;
~~~

Các thông tin nên kiểm tra:

- Default device type là DISK hay SBT.
- Parallelism của từng device type.
- Backup type mặc định.
- FORMAT của channel.
- PARMS của SBT channel.
- Control file autobackup có được bật không và FORMAT ở đâu.
- Retention policy và archived log deletion policy có phù hợp không.

Kiểm tra backup đã được RMAN ghi nhận:

~~~rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

Kiểm tra file backup có còn tồn tại và có thể truy cập theo repository:

~~~rman
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK đối chiếu repository RMAN với trạng thái thực tế của backup trên thiết bị. Nó không đọc toàn bộ nội dung backup để chứng minh mọi block đều có thể restore. Khi cần kiểm tra sâu hơn, có thể dùng VALIDATE.

Ví dụ kiểm tra backupset:

~~~rman
VALIDATE BACKUPSET 123;
~~~

Hoặc kiểm tra khả năng restore database mà không thực hiện restore thật:

~~~rman
RESTORE DATABASE VALIDATE;
~~~

Cần chọn đúng backup set hoặc database và bảo đảm lệnh kiểm tra không ảnh hưởng đáng kể đến tài nguyên production.

## 10. Thay đổi hoặc xóa cấu hình

Cấu hình persistent có thể thay đổi bằng CONFIGURE. Ví dụ chuyển default device type về DISK:

~~~rman
CONFIGURE DEFAULT DEVICE TYPE TO DISK;
~~~

Tăng parallelism:

~~~rman
CONFIGURE DEVICE TYPE DISK PARALLELISM 4;
~~~

Thay FORMAT:

~~~rman
CONFIGURE CHANNEL DEVICE TYPE DISK
  FORMAT '/backup/new_location/%d_%T_%U.bkp';
~~~

Xóa cấu hình FORMAT của channel để quay về hành vi mặc định:

~~~rman
CONFIGURE CHANNEL DEVICE TYPE DISK CLEAR;
~~~

Lệnh CLEAR loại bỏ cấu hình channel đã đặt cho device type đó và đưa các thuộc tính liên quan về mặc định. Cần đọc kết quả SHOW ALL sau khi thay đổi để xác nhận cấu hình cuối cùng.

Có thể xóa cấu hình device type để quay về mặc định:

~~~rman
CONFIGURE DEVICE TYPE DISK CLEAR;
~~~

Không nên chạy CLEAR hàng loạt trong production nếu chưa ghi lại cấu hình trước đó. Việc xóa có thể làm RMAN sử dụng số channel, vị trí hoặc chính sách mặc định khác với mong muốn.

## 11. Ví dụ cấu hình hoàn chỉnh cho backup ra filesystem

Giả sử database dùng DISK, backup được ghi vào **/u03/backup/rman**, cần hai channel và control file autobackup được bật.

~~~rman
CONFIGURE DEFAULT DEVICE TYPE TO DISK;

CONFIGURE DEVICE TYPE DISK
  PARALLELISM 2
  BACKUP TYPE TO BACKUPSET;

CONFIGURE CHANNEL DEVICE TYPE DISK
  FORMAT '/u03/backup/rman/%d_%T_%U.bkp';

CONFIGURE CONTROLFILE AUTOBACKUP ON;

CONFIGURE CONTROLFILE AUTOBACKUP FORMAT
  FOR DEVICE TYPE DISK
  TO '/u03/backup/rman/cf_%F';

SHOW ALL;

BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Trước khi chạy trong môi trường thật, cần tạo thư mục và cấp quyền cho Oracle OS user, kiểm tra dung lượng, xác nhận đường dẫn được mount ổn định và có phương án sao chép backup ra storage độc lập. Nếu dùng RAC, đường dẫn phải truy cập được từ mọi instance có thể thực hiện channel, hoặc phải cấu hình một storage dùng chung như ASM/shared filesystem.

Sau khi backup, kiểm tra repository:

~~~rman
LIST BACKUP SUMMARY;
CROSSCHECK BACKUP;
~~~

Có thể dùng VALIDATE để kiểm tra khả năng đọc backup:

~~~rman
RESTORE DATABASE VALIDATE;
~~~

Một job backup thành công chỉ chứng minh RMAN đã hoàn thành thao tác theo báo cáo của nó. Khả năng phục hồi cần được xác nhận định kỳ bằng validate và diễn tập restore/recover trên môi trường kiểm thử phù hợp.

## 12. Ví dụ cấu hình backup vào FRA

Nếu muốn RMAN quản lý backup trong FRA, cấu hình vị trí và dung lượng:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 300G
  SCOPE = BOTH;

ALTER SYSTEM SET db_recovery_file_dest = '+FRA'
  SCOPE = BOTH;
~~~

Sau đó cấu hình DISK và không đặt FORMAT ghi ra thư mục khác:

~~~rman
CONFIGURE DEFAULT DEVICE TYPE TO DISK;
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
CONFIGURE CONTROLFILE AUTOBACKUP ON;

BACKUP DATABASE PLUS ARCHIVELOG;
~~~

RMAN có thể tạo backup piece trong FRA. Theo dõi dung lượng FRA thường xuyên bằng V$RECOVERY_FILE_DEST và V$FLASH_RECOVERY_AREA_USAGE. Cần phối hợp DB_RECOVERY_FILE_DEST_SIZE, retention policy, archived log deletion policy và năng lực storage. Nếu FRA đầy và không có file nào đủ điều kiện reclaim, backup hoặc các hoạt động tạo archived log có thể gặp lỗi do thiếu không gian.

FRA không phải bản sao lưu độc lập khỏi storage chứa database nếu cả datafile và FRA nằm trên cùng một storage failure domain. Đối với yêu cầu disaster recovery, cần có bản backup ở vị trí độc lập hoặc hệ thống lưu trữ từ xa phù hợp.

## 13. Các lỗi cấu hình thường gặp

### RMAN không ghi được backup piece

Nguyên nhân thường gặp:

- Thư mục chưa tồn tại.
- Oracle OS user không có quyền ghi.
- Filesystem đầy hoặc read-only.
- Đường dẫn không được mount trên node đang chạy channel.
- Tên FORMAT bị trùng hoặc không có thành phần duy nhất.
- Disk group ASM chưa mount hoặc không đủ dung lượng.

Hãy kiểm tra lỗi RMAN/ORA đầu tiên trong output, quyền OS, dung lượng storage và FORMAT đang có hiệu lực.

### RMAN không tìm thấy SBT library

Nguyên nhân có thể là thư viện không được cài đặt, đường dẫn SBT_LIBRARY sai, quyền truy cập không đủ, thư viện không tương thích hoặc biến môi trường PARMS không đúng. Cần kiểm tra log media manager và hướng dẫn tích hợp của nhà cung cấp. Việc đổi device type sang SBT mà chưa cài đặt media manager sẽ không tự tạo ra khả năng ghi tape.

### Job không dùng đủ channel như mong muốn

Kiểm tra PARALLELISM, channel được cấu hình, channel thủ công trong RUN block, device type được chỉ định trong BACKUP và số file có thể xử lý đồng thời. Cũng cần kiểm tra giới hạn của Resource Manager, media manager, số tape drive và khả năng đọc/ghi storage.

### Backup nằm sai vị trí

Kiểm tra FORMAT trong lệnh BACKUP, FORMAT của channel, default device type và cấu hình FRA. FORMAT ở mức lệnh có thể ghi đè cấu hình channel cho job đó. Control file autobackup có FORMAT riêng, nên cần kiểm tra cấu hình autobackup độc lập.

### FRA đầy

Kiểm tra dung lượng giới hạn, dung lượng đã dùng, phần có thể reclaim và chính sách retention. Không xóa thủ công file trong FRA bằng lệnh hệ điều hành khi RMAN/Oracle đang quản lý chúng. Dùng RMAN để crosscheck, xóa backup hết hạn hoặc obsolete theo chính sách đã phê duyệt.

### Backup thành công nhưng không restore được

Nguyên nhân có thể là backup piece bị xóa ngoài RMAN, media manager không còn catalog hoặc media, thiếu archived log, thiếu control file/SPFILE hoặc backup chưa được kiểm tra. Dùng CROSSCHECK, VALIDATE và diễn tập restore/recover định kỳ. Bảo đảm thông tin kết nối media manager, mật khẩu hoặc khóa encryption cần thiết được lưu giữ an toàn.

## 14. Quy trình triển khai cấu hình RMAN channel

1. **Xác định mục tiêu lưu trữ.** Chọn DISK, SBT hoặc kết hợp. Xác định filesystem, ASM disk group, FRA hoặc media manager cụ thể.
2. **Kiểm tra khả năng truy cập.** Xác nhận đường dẫn tồn tại, quyền OS, mount, dung lượng và khả năng truy cập từ các node chạy channel.
3. **Chọn parallelism.** Bắt đầu với số channel phù hợp năng lực I/O và thiết bị đích. Với SBT, kiểm tra số stream/tape drive mà media manager cho phép.
4. **Cấu hình device type.** Đặt default device type và PARALLELISM phù hợp.
5. **Cấu hình channel.** Đặt FORMAT cho DISK hoặc PARMS cho SBT; cân nhắc channel riêng nếu cần phân tán qua nhiều đích.
6. **Cấu hình autobackup.** Bật control file autobackup và chỉ định vị trí phù hợp với chính sách lưu trữ.
7. **Kiểm tra cấu hình.** Dùng SHOW ALL, SHOW CHANNEL và SHOW DEVICE TYPE.
8. **Chạy backup thử.** Thực hiện backup có phạm vi phù hợp, theo dõi channel và output RMAN.
9. **Xác nhận khả năng đọc.** Dùng LIST, CROSSCHECK và VALIDATE; thực hiện restore/recover thử nghiệm theo lịch.
10. **Theo dõi và điều chỉnh.** Đo elapsed time, CPU, I/O, dung lượng, lỗi media manager và tác động đến workload. Chỉ tăng parallelism khi số liệu cho thấy có lợi.

## 15. Nguyên tắc vận hành quan trọng

- Giữ bản backup ở storage độc lập với nơi lưu datafile để bảo vệ trước lỗi thiết bị hoặc mất node.
- Với RAC, dùng ASM hoặc shared storage có thể truy cập từ các instance liên quan; không để channel ghi vào đường dẫn local chỉ một node nhìn thấy nếu RMAN có thể chạy channel trên node khác.
- Dùng FORMAT có thành phần duy nhất như **%U** để tránh trùng tên piece.
- Không tăng số channel vượt khả năng đọc/ghi của storage hoặc số stream mà media manager hỗ trợ.
- Kiểm tra FRA thường xuyên và đặt dung lượng phù hợp với database growth, archived log và retention.
- Bảo vệ thông tin cấu hình SBT, thông tin xác thực và khóa mã hóa theo chính sách bảo mật.
- Kiểm tra control file autobackup và lưu trữ bản sao control file/SPFILE phù hợp.
- Không xóa backup bằng hệ điều hành khi RMAN đang quản lý repository; dùng lệnh RMAN thích hợp và tuân thủ retention policy.
- Không coi thông báo backup hoàn tất là bằng chứng duy nhất về khả năng khôi phục. Phải kiểm tra và diễn tập restore/recover.

Cấu hình RMAN channel, device type và backup location quyết định RMAN thực hiện công việc trên thiết bị nào, với bao nhiêu luồng và ghi các backup piece vào đâu. Cần kết hợp cấu hình đúng với kiểm tra dung lượng, quyền truy cập, hiệu năng và diễn tập phục hồi để bảo đảm backup có thể sử dụng khi database gặp sự cố.
