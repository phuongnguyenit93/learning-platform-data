# Chọn bản Oracle, edition và tham số tương thích cho bộ kiểm thử

Khi xây dựng bộ kiểm thử cho một ứng dụng Oracle, việc chọn đúng phiên bản database và cấu hình chạy thử quyết định trực tiếp mức độ tin cậy của kết quả. Một bộ test chạy thành công trên Oracle Database Free hoặc một bản Enterprise Edition mới nhất chưa chắc chứng minh ứng dụng sẽ hoạt động đúng trên môi trường production đang dùng một release, Release Update (RU), edition và bộ tham số khác.

Trong chủ đề kiểm thử của Database Engine Relational Oracle, cần xem cấu hình database là một phần của điều kiện kiểm thử. Hãy xác định phiên bản và edition mục tiêu, ghi lại mức patch, tham số tương thích, cấu hình NLS, kiến trúc CDB/PDB và các tùy chọn liên quan. Sau đó xây dựng ma trận kiểm thử phản ánh môi trường triển khai và những thay đổi mà hệ thống sắp thực hiện.

## 1. Phân biệt release, edition, patch level và compatibility

Các khái niệm sau có liên quan nhưng không thay thế cho nhau:

| Khái niệm | Ví dụ minh họa | Ý nghĩa đối với kiểm thử |
|---|---|---|
| Database release | Oracle Database 19c, 21c hoặc 23ai | Xác định dòng sản phẩm, hành vi và tập tính năng theo release |
| Edition | Enterprise Edition, Standard Edition 2, Express Edition hoặc Oracle Database Free | Xác định tập tính năng và giới hạn theo edition |
| Patch level | Release Update (RU), one-off patch và SQL patch đã áp dụng | Xác định chính xác mức sửa lỗi và hành vi của database đang chạy |
| `COMPATIBLE` | Một giá trị phiên bản được hỗ trợ bởi release đang cài | Kiểm soát mức tương thích của cấu trúc database và khả năng sử dụng một số tính năng |
| `OPTIMIZER_FEATURES_ENABLE` | Giá trị tương ứng với một release optimizer | Điều khiển tập hành vi optimizer theo release để kiểm tra kế hoạch thực thi |
| Cấu hình database | CDB/PDB, character set, timezone file, NLS và tham số khởi tạo | Ảnh hưởng đến dữ liệu, câu lệnh, session và kết quả kiểm thử |

**Release không phải edition.** Hai máy chủ có thể cùng chạy Oracle Database 19c nhưng một máy là Enterprise Edition và máy kia là Standard Edition 2. Chúng có thể khác nhau về tính năng được hỗ trợ, giới hạn và điều kiện cấp phép.

**Edition không phải patch level.** Hai database cùng Enterprise Edition vẫn có thể chạy hai RU khác nhau. Một lỗi đã được sửa trong RU mới có thể còn xuất hiện ở môi trường chạy RU cũ.

**`COMPATIBLE` không phải phiên bản phần mềm.** Database có thể chạy binary của một release mới trong khi giá trị `COMPATIBLE` vẫn được giữ ở mức thấp hơn để trì hoãn việc sử dụng định dạng hoặc tính năng mới. Không dùng riêng tham số này để kết luận release thực tế của máy chủ.

**`OPTIMIZER_FEATURES_ENABLE` cũng không phải `COMPATIBLE`.** Tham số optimizer điều khiển hành vi tối ưu hóa truy vấn; nó không đưa data dictionary hay định dạng tệp database về một release cũ.

## 2. Chọn release Oracle làm nền cho bộ kiểm thử

### 2.1. Bắt đầu từ môi trường triển khai

Nếu bộ kiểm thử phục vụ một ứng dụng đang vận hành, release production là mốc đầu tiên. Thu thập ít nhất:

- Release Oracle Database và phiên bản đầy đủ được cài đặt.
- Edition của database.
- RU, one-off patch và SQL patch đã áp dụng.
- Hệ điều hành, kiến trúc phần cứng và kiểu triển khai (máy chủ vật lý, máy ảo, container hoặc dịch vụ cloud).
- Cấu hình CDB/PDB và cách ứng dụng kết nối vào service.
- Character set, NCHAR character set, timezone file và các thiết lập NLS.
- Phiên bản client/driver mà ứng dụng dùng, chẳng hạn JDBC, OCI hoặc ODP.NET.
- Các tham số khởi tạo có ảnh hưởng đến SQL, bộ nhớ, concurrency và tính năng ứng dụng.

Nếu chưa có production, xác định release thấp nhất mà sản phẩm cam kết hỗ trợ. Đây là mốc quan trọng cho kiểm thử tương thích. Một ứng dụng được tuyên bố hỗ trợ nhiều release cần được chạy trên từng release trong ma trận hỗ trợ, hoặc ít nhất trên những mốc đại diện đã được nhóm sản phẩm phê duyệt.

Không chọn release chỉ vì đó là bản mới nhất mà công cụ CI tải được. Release mới có thể thay đổi hành vi optimizer, từ chối cú pháp cũ, thay đổi mặc định hoặc không còn cung cấp một edition mà dự án đang sử dụng. Trước khi quyết định, kiểm tra vòng đời hỗ trợ, nền tảng được chứng nhận và yêu cầu của ứng dụng.

### 2.2. Khớp RU và bản vá

Tên release giống nhau không đảm bảo hai database có hành vi giống nhau. RU có thể chứa sửa lỗi optimizer, SQL engine, PL/SQL, bảo mật và các thành phần khác. One-off patch có thể sửa một lỗi cụ thể mà RU chuẩn chưa chứa.

Với kiểm thử hồi quy, nên dùng cùng RU và các bản vá quan trọng như production. Khi kiểm thử trước khi nâng cấp, tạo thêm môi trường chạy RU đích để so sánh kết quả trước và sau thay đổi. Ghi lại patch inventory để người khác có thể dựng lại môi trường.

Có thể kiểm tra lịch sử SQL patch bằng truy vấn sau trên những release có view này:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

View này ghi nhận các thao tác SQL patch được áp dụng trong database. Để xác nhận đầy đủ binary patch và one-off patch ở Oracle Home, nhóm vận hành còn cần lưu kết quả inventory của công cụ patch trên máy chủ. Không suy ra toàn bộ patch level chỉ từ tên release trong banner.

### 2.3. Khớp nền tảng và cấu hình dữ liệu

Nếu ứng dụng sẽ triển khai trên Linux nhưng bộ test chỉ chạy trên Windows, kết quả vẫn hữu ích cho logic SQL nhưng chưa đủ để xác nhận các hành vi phụ thuộc hệ điều hành, filesystem, đường dẫn, quyền truy cập hoặc công cụ vận hành.

Tương tự, kiểm thử trên một database có character set khác production có thể bỏ sót lỗi chuyển đổi ký tự, độ dài chuỗi và sắp xếp. Với ứng dụng có dữ liệu đa ngôn ngữ, cần dùng character set và NCHAR character set gần với môi trường đích. Kiểm tra thêm timezone file và dữ liệu thời gian có daylight saving nếu nghiệp vụ phụ thuộc thời điểm địa phương.

Đối với ứng dụng chạy trong PDB, hãy kiểm thử qua đúng loại service và container mà ứng dụng sẽ sử dụng. Quyền, tham số có thể sửa ở cấp PDB, dịch vụ kết nối và cấu hình resource manager có thể làm kết quả khác với phiên kiểm thử trong CDB root.

## 3. Chọn edition phù hợp

Edition quyết định tập tính năng mà database hỗ trợ và các giới hạn sử dụng. Chọn edition theo môi trường đích và tính năng mà ứng dụng thực sự cần.

| Edition hoặc bản phân phối | Khi nào có thể phù hợp | Điểm cần kiểm tra |
|---|---|---|
| Enterprise Edition (EE) | Production hoặc kiểm thử cần mô phỏng các tính năng Enterprise | Kiểm tra quyền sử dụng các option và management pack; không mặc định mọi tính năng đều nằm trong license cơ bản |
| Standard Edition 2 (SE2) | Hệ thống triển khai theo phạm vi tính năng và giới hạn của SE2 | Xác minh release có cung cấp edition này, giới hạn phần cứng và các tính năng bị giới hạn theo tài liệu của release |
| Express Edition (XE) | Một số bài học, thử nghiệm cục bộ hoặc kiểm thử cơ bản trên các release có cung cấp XE | Có giới hạn tài nguyên và tính năng; không dùng kết quả để thay thế kiểm thử trên edition production nếu có khác biệt |
| Oracle Database Free | Học tập, phát triển và thử nghiệm trong phạm vi điều khoản của bản Free | Kiểm tra giới hạn tài nguyên, tính năng, nền tảng và release; không giả định môi trường Free tương đương EE hoặc SE2 |

Tên, phạm vi và mức sẵn có của edition thay đổi theo release và cách phân phối. Không phải mọi edition đều có trên mọi release, hệ điều hành hoặc dịch vụ cloud. Trước khi dựng ma trận, xác minh edition thực tế có thể cài đặt và được hỗ trợ cho nền tảng mục tiêu.

### 3.1. Không lấy kết quả từ Free/XE làm bằng chứng đầy đủ cho EE hoặc SE2

Free hoặc XE hữu ích cho vòng phát triển nhanh, kiểm thử logic SQL và thử nghiệm cục bộ. Tuy nhiên, chúng có thể có giới hạn về CPU, bộ nhớ, dung lượng dữ liệu, tính năng và cấu hình. Một bài test chạy tốt ở bản Free không chứng minh truy vấn sẽ có cùng kế hoạch hoặc ứng dụng sẽ có cùng hành vi trên Enterprise Edition.

Nếu production chạy SE2, cần có ít nhất một lượt kiểm thử trên SE2 để phát hiện việc sử dụng tính năng không được edition đó hỗ trợ. Nếu production chạy EE và ứng dụng phụ thuộc một tính năng hoặc option của EE, cần kiểm thử trên cấu hình EE tương ứng. Với những tính năng cần license riêng, phải xác nhận entitlement trước khi đưa chúng vào môi trường test.

### 3.2. Phân biệt tính năng có trong binary và quyền sử dụng

Một số view có thể cho biết tùy chọn hoặc thành phần có mặt trong bản cài đặt. Ví dụ, `V$OPTION` phản ánh thông tin về các option được cài đặt trong database. Kết quả này không phải bằng chứng rằng tổ chức đã mua hoặc có quyền sử dụng option đó.

Các tính năng và gói như Partitioning, Advanced Compression, Real Application Clusters, Active Data Guard, Diagnostics Pack hoặc Tuning Pack có điều kiện hỗ trợ và cấp phép riêng tùy release, sản phẩm và hợp đồng. Không bật một tính năng chỉ vì nó xuất hiện trong giao diện hoặc view hệ thống. Nhóm dự án cần đối chiếu tài liệu licensing hiện hành và hợp đồng trước khi sử dụng trong production hoặc test.

`DBA_FEATURE_USAGE_STATISTICS` có thể hỗ trợ kiểm kê việc sử dụng một số tính năng, nhưng không thay thế việc xác định entitlement. Việc một tính năng được báo cáo là đã dùng, chưa dùng hoặc được cài đặt không tự kết luận trạng thái cấp phép.

Với database cloud, kiểm tra cả edition/service tier và mô hình tính phí: license included hay Bring Your Own License (BYOL). Môi trường test được tạo từ một dịch vụ cloud khác có thể có quyền và giới hạn khác với database on-premises.

## 4. Hiểu đúng tham số COMPATIBLE

### 4.1. Vai trò của COMPATIBLE

`COMPATIBLE` là tham số khởi tạo điều khiển mức tương thích của database với một phiên bản Oracle. Nó ảnh hưởng đến việc database có thể sử dụng một số tính năng và cấu trúc lưu trữ được giới thiệu trong release mới hay không. Giá trị này giúp quản trị viên kiểm soát thời điểm database bắt đầu dựa vào những thay đổi có thể ảnh hưởng đến khả năng hạ cấp.

Tham số này không làm binary của database biến thành release cũ. Nó cũng không bảo đảm mọi câu lệnh SQL, execution plan, package PL/SQL hoặc ứng dụng sẽ hoạt động giống hệt release cũ. Muốn kiểm thử tương thích ứng dụng, vẫn cần chạy bộ test trên release và cấu hình thực tế.

### 4.2. Chọn giá trị cho môi trường kiểm thử

Không sao chép một giá trị `COMPATIBLE` từ ví dụ trên Internet rồi áp dụng cho mọi hệ thống. Giá trị hợp lệ phụ thuộc release đang cài, lịch sử nâng cấp, yêu cầu tương thích và tài liệu Oracle của phiên bản đó.

Đối với kiểm thử hồi quy production, dùng giá trị hiện tại của môi trường production làm baseline. Khi chuẩn bị nâng cấp, tạo một nhánh kiểm thử riêng để đánh giá giá trị `COMPATIBLE` dự kiến sau nâng cấp. Chỉ tăng giá trị khi release đích hỗ trợ, các bước nâng cấp đã hoàn tất và nhóm vận hành chấp nhận hệ quả đối với kế hoạch downgrade.

`COMPATIBLE` là tham số tĩnh: thay đổi giá trị có hiệu lực khi database khởi động lại. Ví dụ về hình thức thay đổi trong SPFILE:

```sql
ALTER SYSTEM SET compatible = '<gia_tri_duoc_phe_duyet>'
  SCOPE = SPFILE;
```

Giá trị trong ví dụ là chỗ giữ chỗ, không phải một giá trị cấu hình để sao chép. Trước khi thay đổi, xác nhận giá trị được release hỗ trợ và quy trình restart đã được lên lịch.

### 4.3. Vì sao phải thận trọng khi tăng COMPATIBLE

Khi nâng `COMPATIBLE`, database có thể bắt đầu sử dụng cấu trúc hoặc tính năng mới. Sau khi đã dựa vào các cấu trúc đó, hạ giá trị về mức cũ có thể không được hỗ trợ. Việc khôi phục về release cũ có thể đòi hỏi phương án restore hoặc migration đã được chuẩn bị, thay vì chỉ sửa lại tham số.

Vì vậy:

- Không tăng `COMPATIBLE` chỉ để làm cho con số trùng với release mới.
- Không dùng một database test đã tăng `COMPATIBLE` để giả lập môi trường production vẫn giữ giá trị thấp hơn.
- Thử nâng cấp trên bản clone có thể khôi phục, sau đó chạy kiểm thử ứng dụng và kiểm thử downgrade/restore theo quy trình được hỗ trợ.
- Lưu giá trị trước và sau thay đổi cùng thời điểm, người thực hiện, lý do và kết quả kiểm thử.

Nếu mục tiêu là kiểm tra ứng dụng có chạy được trên release mới hay không, tạo database mới hoặc clone phù hợp với release đích và cấu hình `COMPATIBLE` theo kế hoạch nâng cấp. Không thay đổi tham số trên production chỉ để phục vụ một bài kiểm thử.

## 5. Các tham số tương thích và tham số ảnh hưởng đến kết quả test

### 5.1. OPTIMIZER_FEATURES_ENABLE

`OPTIMIZER_FEATURES_ENABLE` điều khiển tập tính năng optimizer tương ứng với một release Oracle. Nó thường được dùng để đánh giá tác động của thay đổi optimizer khi nâng cấp. Chẳng hạn, nhóm có thể so sánh execution plan trên cấu hình optimizer hiện tại với cấu hình release đích trong môi trường thử nghiệm được kiểm soát.

Tham số này không thay thế việc kiểm thử trên release đích và không biến database mới thành database cũ. Kết quả còn phụ thuộc statistics, bind variable, dữ liệu, schema, index, system statistics, parameter khác và trạng thái cache. Nếu thay đổi tham số ở cấp session hoặc system để chạy A/B, hãy ghi lại giá trị và hoàn nguyên đúng cách sau bài test.

Khi kiểm thử hiệu năng, lưu cả SQL text, bind values, execution plan, cardinality ước tính và thực tế, thời gian chạy, logical reads, physical reads và trạng thái cache. So sánh trên cùng bộ dữ liệu và điều kiện chạy để tránh kết luận sai do môi trường khác nhau.

### 5.2. Tham số ảnh hưởng đến ngữ nghĩa dữ liệu

Một số tham số có thể làm thay đổi kết quả hoặc cách ứng dụng diễn giải dữ liệu:

| Tham số hoặc cấu hình | Ảnh hưởng cần kiểm thử |
|---|---|
| `NLS_CHARACTERSET` | Khả năng lưu trữ và chuyển đổi ký tự trong database |
| `NLS_NCHAR_CHARACTERSET` | Kiểu dữ liệu NCHAR, NVARCHAR2 và NCLOB |
| `NLS_LENGTH_SEMANTICS` | Cách khai báo độ dài CHAR/VARCHAR2 theo BYTE hoặc CHAR khi tạo đối tượng |
| `NLS_COMP`, `NLS_SORT` | So sánh và sắp xếp chuỗi trong các ngữ cảnh chịu ảnh hưởng của NLS |
| `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT` | Cách biểu diễn và chuyển đổi ngày giờ nếu ứng dụng dựa vào chuyển đổi ngầm |
| `TIME_ZONE` và timezone file | Chuyển đổi timestamp có múi giờ và quy tắc thời gian địa phương |
| `MAX_STRING_SIZE` | Giới hạn kiểu chuỗi SQL và yêu cầu chuyển đổi cấu hình |
| Character set của client | Chuyển đổi dữ liệu giữa ứng dụng, driver và database |

Ứng dụng nên dùng bind variable có kiểu dữ liệu rõ ràng và chuyển đổi ngày giờ tường minh thay vì phụ thuộc định dạng mặc định của session. Dù vậy, bộ test vẫn cần ghi lại NLS để phát hiện khác biệt môi trường và kiểm tra những đoạn mã cũ đang dựa vào implicit conversion.

`MAX_STRING_SIZE` cần được xử lý đặc biệt. Chuyển từ `STANDARD` sang `EXTENDED` có yêu cầu và bước chuyển đổi riêng, ảnh hưởng đến khả năng tương thích và phương án quay lui. Không tự đổi tham số này trong pipeline kiểm thử dùng chung; hãy tạo môi trường riêng và tuân thủ đúng quy trình được hỗ trợ cho release đó.

### 5.3. Tham số ảnh hưởng đến tải và tài nguyên

Các tham số như `PROCESSES`, `SESSIONS`, `OPEN_CURSORS`, `SGA_TARGET`, `PGA_AGGREGATE_TARGET`, `MEMORY_TARGET`, `UNDO_RETENTION`, `PARALLEL_DEGREE_POLICY` và `STATISTICS_LEVEL` có thể ảnh hưởng đến khả năng chịu tải, concurrency, bộ nhớ, thời gian chạy hoặc cách thu thập số liệu.

Không cần sao chép mọi giá trị từ production vào môi trường test nhỏ. Tuy nhiên, cần biết khác biệt nào có thể làm sai kết luận. Ví dụ, test concurrency trên database chỉ cho phép ít session sẽ không phản ánh tải production; test hiệu năng trên máy có bộ nhớ lớn hơn nhiều có thể che giấu vấn đề tài nguyên.

Đối với kiểm thử chức năng, ưu tiên cấu hình ổn định và đủ tài nguyên để test có kết quả lặp lại. Đối với kiểm thử tải, xác định rõ mục tiêu, tải đồng thời, giới hạn session, bộ nhớ và I/O. Ghi lại giới hạn thực tế thay vì chỉ lưu giá trị tham số.

### 5.4. Phân biệt tham số ở system, PDB và session

Một số tham số có thể sửa ở cấp system, một số có thể đặt riêng ở PDB hoặc session; phạm vi và khả năng sửa phụ thuộc tham số cùng release. Khi ứng dụng kết nối qua service vào một PDB, cần kiểm tra giá trị mà session thực sự nhìn thấy.

Không chỉ đọc cấu hình từ một file init parameter rồi kết luận mọi session đều dùng giá trị đó. SPFILE, giá trị runtime, tham số PDB, tham số session và cấu hình do connection pool thiết lập có thể khác nhau. Bộ test cần ghi lại cấu hình tại đúng container và session mà ứng dụng sử dụng.

## 6. Thu thập cấu hình database trước khi chạy test

### 6.1. Kiểm tra release và edition

Truy vấn sau hiển thị banner của database:

```sql
SELECT banner
FROM v$version
ORDER BY banner;
```

Banner thường thể hiện release và edition trong chuỗi mô tả sản phẩm. Có thể xem thêm thông tin thành phần:

```sql
SELECT product, version, status
FROM product_component_version
ORDER BY product;
```

Hãy lưu nguyên văn kết quả cùng thông tin Oracle Home và patch inventory do nhóm vận hành cung cấp. Không suy ra edition chỉ từ phiên bản SQL client hoặc từ tên service.

### 6.2. Kiểm tra tham số đang có hiệu lực

Ví dụ sau lấy một nhóm tham số thường cần ghi nhận:

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name IN (
  'compatible',
  'optimizer_features_enable',
  'optimizer_mode',
  'cursor_sharing',
  'statistics_level',
  'max_string_size',
  'processes',
  'sessions',
  'open_cursors',
  'parallel_degree_policy'
)
ORDER BY name;
```

Các cột cho biết giá trị hiện tại và một phần thông tin về khả năng sửa tham số. Quyền truy cập view động có thể cần quyền từ điển dữ liệu phù hợp. Trong môi trường multitenant, chạy truy vấn trong đúng container hoặc kiểm tra thêm view tương ứng ở cấp CDB theo quyền được cấp.

### 6.3. Kiểm tra NLS

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
  'NLS_CHARACTERSET',
  'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;

SELECT name, value
FROM v$parameter
WHERE name = 'nls_length_semantics';

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
  'NLS_DATE_FORMAT',
  'NLS_TIMESTAMP_FORMAT',
  'NLS_COMP',
  'NLS_SORT',
  'NLS_LANGUAGE',
  'NLS_TERRITORY'
)
ORDER BY parameter;
```

Truy vấn thứ nhất ghi nhận character set ở cấp database, truy vấn thứ hai ghi nhận giá trị mặc định `NLS_LENGTH_SEMANTICS`, và truy vấn thứ ba ghi nhận thiết lập NLS của session hiện tại. Kết quả session rất quan trọng khi ứng dụng dùng connection pool vì mỗi connection có thể được khởi tạo hoặc cấu hình khác nhau.

### 6.4. Ghi nhận container và service

Trong môi trường multitenant, có thể kiểm tra container hiện tại:

```sql
SELECT sys_context('USERENV', 'DB_NAME')       AS db_name,
       sys_context('USERENV', 'CON_NAME')       AS container_name,
       sys_context('USERENV', 'SERVICE_NAME')   AS service_name,
       sys_context('USERENV', 'INSTANCE_NAME')  AS instance_name
FROM dual;
```

Lưu kết quả này cùng log test để xác định test đã chạy vào database, PDB, service và instance nào. Với RAC hoặc môi trường có nhiều service, kiểm tra việc phân phối kết nối và tính nhất quán cấu hình giữa các instance.

## 7. Thiết kế ma trận kiểm thử theo mục tiêu

Không phải mọi lần chạy test đều cần dựng toàn bộ tổ hợp release, edition và tham số. Hãy phân nhóm theo rủi ro và mục tiêu.

| Mục tiêu | Cấu hình nên ưu tiên | Điều cần chứng minh |
|---|---|---|
| Kiểm thử chức năng thường xuyên | Release, edition, RU và cấu hình gần production | Các luồng nghiệp vụ và SQL chính hoạt động trên môi trường mục tiêu |
| Tương thích nhiều release | Mỗi release nằm trong phạm vi hỗ trợ | Không dùng cú pháp, kiểu dữ liệu hoặc tính năng vượt quá baseline hỗ trợ |
| Kiểm thử edition | Edition production và edition có giới hạn hơn nếu sản phẩm hỗ trợ | Ứng dụng không phụ thuộc tính năng không có quyền hoặc không được hỗ trợ |
| Kiểm thử nâng cấp | Clone nguồn và môi trường release đích | Dữ liệu, schema, PL/SQL, job và ứng dụng hoạt động sau nâng cấp |
| Kiểm thử thay đổi COMPATIBLE | Bản clone có thể khôi phục, theo kế hoạch nâng cấp | Tính năng mới, khả năng vận hành và phương án phục hồi được xác nhận |
| Kiểm thử optimizer | Cùng release và dữ liệu, so sánh cấu hình optimizer | Kế hoạch thực thi và hiệu năng thay đổi trong giới hạn chấp nhận |
| Kiểm thử tải | Cấu hình tài nguyên và concurrency được định nghĩa | Database đáp ứng mục tiêu tải, độ trễ và tài nguyên |

Một ma trận mẫu cho ứng dụng đang chạy trên một release production:

| Môi trường | Release/edition | RU | COMPATIBLE | Mục đích |
|---|---|---|---|---|
| CI nhanh | Bản Free hoặc edition test được phê duyệt | Mức patch đã khóa | Theo cấu hình hợp lệ của bản phân phối | Phản hồi nhanh cho unit/integration test cơ bản |
| Regression | Cùng release và edition production | Cùng RU production | Bằng production | Xác nhận hành vi hiện tại |
| Upgrade candidate | Release và edition dự kiến triển khai | RU mục tiêu | Giá trị theo kế hoạch nâng cấp | Phát hiện lỗi tương thích trước khi phát hành |
| Edition boundary | Edition giới hạn hơn, nếu nằm trong phạm vi sản phẩm hỗ trợ | Patch đã khóa | Hợp lệ với release | Phát hiện phụ thuộc tính năng edition |

Đây là cấu trúc tham khảo, không phải yêu cầu phải có bốn database vật lý. Có thể dùng database clone, PDB riêng hoặc môi trường tạm thời nếu phương án đó đáp ứng điều kiện cô lập dữ liệu và khả năng tái tạo. Không dùng một PDB chung cho các test có thể làm thay đổi tham số, schema hoặc dữ liệu của nhau.

## 8. Quy trình dựng và khóa môi trường test

### Bước 1: Xác định phạm vi hỗ trợ

Ghi rõ release thấp nhất, release production và release đích dự kiến. Xác định edition, nền tảng, loại triển khai và driver ứng dụng. Nếu sản phẩm hỗ trợ nhiều cấu hình, ghi rõ cấu hình nào là bắt buộc và cấu hình nào chỉ là thử nghiệm bổ sung.

### Bước 2: Chọn edition và xác nhận quyền sử dụng

Chọn edition theo tính năng ứng dụng cần và môi trường triển khai. Kiểm tra các option, pack và điều khoản của dịch vụ cloud nếu có. Đưa kết quả xác nhận vào hồ sơ môi trường để nhóm phát triển không vô tình dựa vào một tính năng chưa được phê duyệt.

### Bước 3: Khóa release và patch level

Chọn release và RU cụ thể. Lưu banner, patch inventory, SQL patch history, Oracle Home và nền tảng. Không tự động cập nhật image hoặc Oracle Home giữa hai lần chạy test mà không ghi nhận thay đổi.

### Bước 4: Thiết lập COMPATIBLE và tham số

Lấy cấu hình production làm baseline khi mục tiêu là regression. Với môi trường upgrade, dùng cấu hình được phê duyệt cho release đích. Lưu các tham số optimizer, NLS, memory, concurrency và tham số đặc thù ứng dụng. Những thay đổi có thể ảnh hưởng đến khả năng downgrade hoặc cấu trúc dữ liệu cần được kiểm soát riêng.

### Bước 5: Chuẩn hóa dữ liệu và schema

Dùng cùng phiên bản DDL, PL/SQL, index, constraint, statistics và dữ liệu kiểm thử khi so sánh hai cấu hình. Với test nâng cấp, tạo bản sao dữ liệu đại diện, bao gồm dữ liệu biên và dung lượng gần với thực tế. Ẩn danh dữ liệu nhạy cảm theo chính sách của tổ chức.

### Bước 6: Chạy test và lưu bằng chứng

Lưu kết quả test, log kết nối, cấu hình database, lỗi Oracle, execution plan và số liệu hiệu năng cần thiết. Gắn mỗi kết quả với một mã môi trường hoặc mã cấu hình để có thể truy xuất chính xác release, edition, patch và tham số đã dùng.

### Bước 7: Dọn dẹp và tái tạo

Sau test, hủy môi trường tạm hoặc phục hồi từ snapshot theo quy trình đã định. Đối với test cần giữ dữ liệu để điều tra, lưu bản clone và cấu hình liên quan trong thời hạn được phê duyệt. Không để một môi trường đã bị thay đổi `COMPATIBLE`, `MAX_STRING_SIZE` hoặc schema trở thành baseline dùng chung mà không cập nhật hồ sơ.

## 9. Kiểm thử nâng cấp release và thay đổi tham số

Kiểm thử nâng cấp cần tách các thay đổi để có thể xác định nguyên nhân khi phát sinh lỗi:

1. Chạy bộ test trên release nguồn với cấu hình hiện tại và lưu baseline.
2. Clone database nguồn để có dữ liệu và schema tương đương.
3. Nâng cấp clone theo quy trình được hỗ trợ cho release đích.
4. Ghi nhận edition, RU, SQL patch, `COMPATIBLE`, NLS, timezone file và các tham số sau nâng cấp.
5. Chạy kiểm tra thành phần database, invalid object, job, database link, quyền và dịch vụ kết nối.
6. Chạy lại cùng bộ test chức năng và so sánh kết quả.
7. Chạy test hiệu năng với dữ liệu, bind values và điều kiện tải có thể so sánh.
8. Thử quy trình backup/restore hoặc downgrade trong môi trường riêng nếu kế hoạch phát hành yêu cầu.

Không thay đổi đồng thời release, edition, RU, `COMPATIBLE`, `OPTIMIZER_FEATURES_ENABLE` và dữ liệu rồi chỉ so sánh kết quả cuối. Khi nhiều biến thay đổi cùng lúc, rất khó xác định yếu tố gây ra khác biệt. Có thể dùng các nhánh test riêng để đánh giá từng thay đổi và một lượt kiểm thử tổng hợp sau khi đã hiểu từng tác động.

Nếu test thất bại, phân loại trước khi sửa:

- Lỗi không tương thích cú pháp, package, kiểu dữ liệu hoặc tính năng.
- Lỗi do edition hoặc option không có trong môi trường.
- Lỗi do patch level hoặc regression của release.
- Lỗi do tham số optimizer, statistics hoặc execution plan.
- Lỗi do NLS, character set, timezone hoặc implicit conversion.
- Lỗi do quyền, cấu hình PDB/service, tài nguyên hoặc khác biệt hệ điều hành.
- Lỗi do dữ liệu test không tương đương hoặc trạng thái môi trường bị thay đổi.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ ghi “Oracle 19c” mà không ghi edition và RU | Không thể tái tạo đúng môi trường | Lưu release, edition, patch inventory và SQL patch history |
| Dùng Free/XE làm môi trường duy nhất cho ứng dụng production EE | Bỏ sót tính năng, giới hạn hoặc khác biệt optimizer | Bổ sung test trên edition production hoặc môi trường có cấu hình tương đương |
| Cho rằng `V$OPTION` chứng minh đã có license | Có thể sử dụng option vượt quyền | Đối chiếu licensing guide và hợp đồng |
| Tăng `COMPATIBLE` để “khớp” release mới | Có thể làm mất khả năng quay lại trạng thái cũ | Thực hiện trên clone theo kế hoạch nâng cấp và restore |
| Dùng `OPTIMIZER_FEATURES_ENABLE` để giả lập toàn bộ release cũ | Bỏ qua khác biệt engine, data dictionary và tính năng | Kiểm thử trực tiếp trên release mục tiêu |
| Không ghi NLS và timezone | Kết quả phụ thuộc session hoặc máy chủ | Thu thập NLS database/session và timezone |
| Chạy test trên image tự động cập nhật | Kết quả thay đổi giữa các lần chạy | Khóa image, RU và patch inventory |
| Dùng chung database giữa các test phá hủy dữ liệu | Test ảnh hưởng lẫn nhau | Cô lập bằng schema, PDB hoặc database riêng tùy mức rủi ro |
| So sánh hiệu năng với dữ liệu hoặc statistics khác nhau | Kết luận optimizer thiếu tin cậy | Chuẩn hóa dữ liệu, statistics, bind values và tải |

## 11. Checklist trước khi chấp nhận kết quả kiểm thử

- [ ] Đã xác định release mục tiêu và phạm vi release mà sản phẩm hỗ trợ.
- [ ] Đã ghi nhận edition và xác minh các option/pack được phép sử dụng.
- [ ] Đã khóa RU, one-off patch và SQL patch cần thiết.
- [ ] Đã ghi lại `COMPATIBLE` và xác nhận giá trị phù hợp với kế hoạch nâng cấp.
- [ ] Đã ghi lại `OPTIMIZER_FEATURES_ENABLE` và các tham số optimizer liên quan.
- [ ] Đã kiểm tra character set, NCHAR character set, NLS và timezone.
- [ ] Đã xác nhận CDB/PDB, service và instance mà ứng dụng thực sự kết nối.
- [ ] Đã ghi nhận phiên bản driver/client và cấu hình connection pool.
- [ ] Đã xác định khác biệt tài nguyên giữa môi trường test và production.
- [ ] Đã chuẩn hóa schema, dữ liệu, statistics và điều kiện chạy khi so sánh.
- [ ] Đã lưu log cấu hình cùng kết quả test để có thể tái tạo.
- [ ] Đã có phương án clone, backup/restore hoặc phục hồi cho test nâng cấp và thay đổi tham số rủi ro cao.

## 12. Nguyên tắc lựa chọn thực tế

Với kiểm thử thường xuyên, hãy dùng một môi trường được khóa phiên bản và gần production nhất có thể. Nếu cần chạy nhanh bằng Oracle Database Free hoặc XE, xem đó là một lớp phản hồi sớm và vẫn giữ một lượt regression trên edition mục tiêu. Khi kiểm thử nâng cấp, tạo clone riêng cho release đích và quản lý `COMPATIBLE` theo kế hoạch đã được duyệt. Khi kiểm thử hiệu năng, cố định RU, dữ liệu, statistics, bind values và tham số optimizer để so sánh có ý nghĩa.

Một kết quả kiểm thử chỉ có giá trị trong phạm vi cấu hình đã chạy. Ghi rõ release, edition, patch level, `COMPATIBLE`, tham số quan trọng, NLS, container/service và driver giúp nhóm biết chính xác điều gì đã được chứng minh, đồng thời tránh dùng một kết quả từ môi trường khác biệt để kết luận quá rộng về khả năng tương thích của ứng dụng Oracle.
