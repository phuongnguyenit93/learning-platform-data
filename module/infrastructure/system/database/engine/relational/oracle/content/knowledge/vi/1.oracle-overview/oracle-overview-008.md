# Phiên bản, bản phát hành, Release Update và tham số `COMPATIBLE` trong Oracle Database

Trong vận hành Oracle Database, câu hỏi “đang dùng phiên bản nào?” có thể có nhiều đáp án: **dòng sản phẩm** (19c, 21c, 26ai), **mức cập nhật phần mềm** (chẳng hạn RU 19.31), **bản vá đã áp dụng** và **mức tương thích dữ liệu** (`COMPATIBLE=19.0.0`). Các thông tin này liên quan nhưng không đồng nhất. Hiểu sự khác biệt giúp lên kế hoạch nâng cấp, vá bảo mật và đánh giá khả năng quay về phiên bản cũ.

Bài học này tập trung vào Oracle Database quan hệ, đặc biệt các hệ thống 19c và Oracle AI Database 26ai. Cú pháp, ví dụ vận hành có thể khác theo nền tảng, cấu hình RAC/Data Guard và dịch vụ Oracle Cloud; khi thực hiện trên hệ thống thật, cần đối chiếu tài liệu của đúng bản phát hành.

## 1. Bốn khái niệm cần tách bạch

| Khái niệm | Ví dụ | Trả lời câu hỏi | Ý nghĩa vận hành |
| --- | --- | --- | --- |
| **Release / dòng phát hành** | Oracle Database **19c**, **21c**, Oracle AI Database **26ai** | Đang sử dụng thế hệ sản phẩm nào? | Quyết định tập tính năng, đường nâng cấp và chính sách hỗ trợ. |
| **Release Update (RU)** | **19.31**, **23.26.4** | Dòng sản phẩm được cập nhật đến đợt nào? | Đưa vào các sửa lỗi, bản vá bảo mật và một số cải tiến trong cùng dòng phát hành. |
| **Patch cụ thể** | RU, Monthly Recommended Patch (MRP), one-off patch | Trên Oracle Home/cơ sở dữ liệu đã áp dụng những bản vá nào? | Cần kiểm tra cả phần mềm lẫn các bước SQL sau cập nhật. |
| **`COMPATIBLE`** | `19.0.0`, `21.0.0`, `23.9.0` | Định dạng dữ liệu trên đĩa được phép sử dụng đến mức tương thích nào? | Có thể giới hạn một số tính năng và ảnh hưởng trực tiếp đến khả năng downgrade. |

Ví dụ: một cơ sở dữ liệu có thể **chạy phần mềm Oracle Database 19c RU 19.31** và vẫn đặt **`COMPATIBLE=19.0.0`**. Đây là tình huống bình thường: số RU không phải giá trị cần gán cho `COMPATIBLE`.

### 1.1. Release khác edition và nền tảng

Tên release như **19c** chỉ một thế hệ Oracle Database. **Enterprise Edition**, **Standard Edition 2** hay các gói Free là phân loại sản phẩm/giấy phép; **Linux**, **Windows** và kiến trúc triển khai là các yếu tố khác. Hai hệ thống cùng “19c” có thể khác edition, patch level, tùy chọn tính năng và lịch hỗ trợ.

Không nên suy ra mức bản vá hoặc điều kiện được phép sử dụng một tính năng chỉ từ chuỗi “19c”.

### 1.2. Long Term Support và Innovation Release

Oracle phân biệt các dòng được thiết kế cho vòng đời hỗ trợ dài (**Long Term Support Release**) và các dòng thiên về đưa tính năng mới ra sớm (**Innovation Release**).

- **19c**: dòng hỗ trợ dài, phổ biến trong hệ thống doanh nghiệp.
- **21c**: dòng Innovation Release.
- **23ai → 26ai**: Oracle AI Database **26ai** thay thế tên/phát hành **23ai** bằng RU tháng 10/2025, là dòng hỗ trợ dài tiếp theo. Theo Oracle, chuyển từ 23ai sang 26ai ở mốc này thực hiện bằng RU, không đòi hỏi một lần major database upgrade hay tái chứng nhận ứng dụng chỉ vì đổi tên sản phẩm.

Vì vậy, **26ai không đồng nghĩa mọi nơi đều hiển thị số nội bộ bắt đầu bằng `26`**. Tài liệu và các công cụ có thể tiếp tục hiển thị phiên bản kỹ thuật bắt đầu bằng `23`; cần đọc tên sản phẩm và số phiên bản trong đúng ngữ cảnh.

> Chính sách hỗ trợ và phạm vi nền tảng thay đổi theo thời gian. Khi chọn release cho hệ thống mới, xác nhận lịch hỗ trợ hiện hành, chứng nhận của ứng dụng và đường nâng cấp chính thức; không suy từ việc một release có số lớn hơn.

## 2. Đọc số phiên bản và phân biệt các kiểu hiển thị

### 2.1. Ví dụ với Oracle Database 19c

Có thể bắt gặp các chuỗi sau:

- `19c`: tên dòng phát hành.
- `19.3.0.0.0`: một mức phát hành phần mềm của 19c.
- `19.31.0.0.0`: ví dụ một bản 19c đã lên **RU 19.31**.
- `19.0.0.0.0`: số **base version** có thể được trả về ở trường `VERSION`, dù `VERSION_FULL` đã chỉ tới RU cao hơn.

Ở 19c, cách gọi RU thường là **19.x** (ví dụ 19.30, 19.31). Không được đọc “19.31” thành “Oracle 31c” hoặc gán `COMPATIBLE=19.31.0` chỉ vì đã cài RU.

Từ Oracle Database 18c, các view có thể cung cấp cả `VERSION` và `VERSION_FULL`. Muốn biết đầy đủ mức phần mềm thì cần quan sát trường phù hợp, đồng thời đối chiếu patch inventory.

### 2.2. Điểm đặc biệt với Oracle AI Database 26ai

Oracle chuyển từ nhãn 23ai sang **Oracle AI Database 26ai** qua RU tháng 10/2025, được thể hiện ở các bản như **23.26.0**. Các RU trong năm 2026 tiếp tục có dạng **23.26.1**, **23.26.2**, **23.26.3**, **23.26.4** cho các đợt theo quý.

Với quy ước `VERSION_FULL` của 26ai, năm trường số có ý nghĩa khác với cách đọc truyền thống của 19c:

```text
23 . 26 . 4 . 0 . 0
│    │    │   │   └─ recut
│    │    │   └───── mức Monthly Recommended Patch (MRP)
│    │    └───────── RU theo kỳ trong năm
│    └────────────── năm RU (2026)
└─────────────────── base release kỹ thuật
```

Đây là ví dụ giải thích cấu trúc, không phải cam kết mọi bản vá có đúng chuỗi năm trường như trên. Trường hợp 26ai có thể có tên sản phẩm là “26ai” nhưng `VERSION` hoặc `VERSION_FULL` bắt đầu bằng “23”. **Đừng áp dụng máy móc cùng một cách diễn giải từng trường số cho mọi thế hệ Oracle.**

### 2.3. Lệnh SQL kiểm tra trên máy đang chạy

Kết nối bằng tài khoản có quyền đọc các dynamic performance view, rồi chạy:

```sql
-- Base version và chuỗi phiên bản đầy đủ của instance (18c trở lên).
SELECT instance_name, version, version_full
FROM   v$instance;

-- Banner hiển thị tên sản phẩm và bản phát hành.
SELECT banner_full
FROM   v$version;

-- Mức tương thích định dạng dữ liệu đang có hiệu lực.
SELECT name, value
FROM   v$parameter
WHERE  name = 'compatible';
```

Trong SQL*Plus hoặc SQLcl, có thể dùng thêm:

```sql
SHOW PARAMETER compatible;
```

Ví dụ kết quả **minh họa** cho một hệ thống 19c:

```text
VERSION          VERSION_FULL
---------------  -----------------
19.0.0.0.0       19.31.0.0.0

NAME             VALUE
---------------  -------
compatible       19.0.0
```

Đọc đúng: phần mềm thuộc dòng 19c, đã cập nhật đến RU 19.31, còn định dạng dữ liệu sử dụng mức tương thích 19.0.0.

## 3. Release Update (RU) và hệ sinh thái bản vá

### 3.1. RU là gì?

**Release Update** là gói cập nhật định kỳ trong một dòng Oracle Database, phục vụ sửa lỗi, cập nhật bảo mật, cải thiện độ ổn định và đôi khi bổ sung hoặc mở rộng tính năng. Oracle phát hành các RU theo quý, thường vào **tháng 1, 4, 7 và 10**. RU có tính **tích lũy**: đợt mới chứa các sửa lỗi thuộc những đợt trước trên cùng nhánh theo quy định của Oracle.

Hình dung một hệ thống 19c:

```text
Oracle Database 19c
     │
     ├── RU 19.29 (10/2025)
     ├── RU 19.30 (01/2026)
     ├── RU 19.31 (04/2026)
     └── RU 19.32 (07/2026)
```

Chuyển **19.30 → 19.31** là **patch/update trong cùng dòng 19c**. Chuyển **19c → 26ai** là **nâng cấp sang dòng release khác**, đòi hỏi đánh giá tính tương thích và quy trình database upgrade tương ứng.

Đừng đánh đồng **RU** với một **major upgrade**: hai thao tác có điều kiện tiền đề, mức thay đổi và phương án khôi phục khác nhau.

### 3.2. RU, MRP và one-off patch

| Loại cập nhật | Đặc điểm | Cách suy nghĩ khi vận hành |
| --- | --- | --- |
| **RU** | Gói cập nhật theo quý, tích lũy trong một dòng release. | Nền tảng chính của chiến lược vá định kỳ. |
| **MRP (Monthly Recommended Patch)** | Nhóm bản sửa đề xuất theo tháng, tích lũy trên **một RU cụ thể**; không tự đổi số RU. | Có thể bổ sung sau RU khi nền tảng và bản RU đáp ứng điều kiện. |
| **One-off / interim patch** | Sửa một lỗi hoặc nhóm lỗi cụ thể, có điều kiện phụ thuộc/xung đột. | Cần kiểm tra tính phù hợp với RU đang chạy và hướng dẫn từ Oracle Support. |
| **RUR (Release Update Revision)** | Cơ chế trước đây; Oracle đã chuyển sang MRP cho chính sách cập nhật hiện hành. | Có thể vẫn thấy trong tài liệu/lịch sử bản vá cũ. |

MRP không sẵn có giống nhau cho mọi hệ điều hành; tài liệu Oracle xác định chương trình MRP cho **Linux**. Không giả định bản vá cho Linux áp dụng được lên Windows hoặc các nền tảng khác.

### 3.3. Cập nhật phần mềm và cập nhật SQL là hai mặt của việc patch

Với nhiều bản vá Oracle Database tự quản lý, quá trình có hai lớp:

1. **Oracle Home (binary/inventory):** các file phần mềm được cập nhật bằng công cụ phù hợp (chẳng hạn OPatch hoặc OPatchAuto tùy môi trường).
2. **Database SQL registry:** các thay đổi SQL cần thiết được áp dụng bằng **`datapatch`** hoặc cơ chế tự động tương đương và được ghi trong **`DBA_REGISTRY_SQLPATCH`**.

Chỉ nhìn `V$VERSION` hoặc chỉ nhìn thư mục cài đặt **không đủ** để kết luận tất cả thành phần đã được vá thành công. Nếu phần binary lên RU nhưng SQL patch chưa hoàn tất, hệ thống có thể ở trạng thái cập nhật dở dang.

Để kiểm tra phần mềm trên môi trường Unix/Linux tự quản lý:

```bash
$ORACLE_HOME/OPatch/opatch lsinventory
```

Lệnh trên chạy ở hệ điều hành, với đúng `ORACLE_HOME` của instance cần kiểm tra. Đối với Grid Infrastructure, RAC hoặc nhiều Oracle Home, cần kiểm tra từng thành phần liên quan theo hướng dẫn của gói patch.

Để kiểm tra lịch sử SQL patch:

```sql
SELECT action_time,
       patch_id,
       patch_type,
       action,
       status,
       description
FROM   dba_registry_sqlpatch
ORDER  BY action_time DESC;
```

Các điểm cần đọc:

- `PATCH_TYPE='RU'` cho biết bản ghi thuộc loại Release Update.
- `ACTION` là `APPLY` hoặc `ROLLBACK`; `STATUS='SUCCESS'` thể hiện lần thực hiện đó thành công.
- Một patch có thể có nhiều bản ghi do apply, rollback hoặc thử lại. **Không được coi dòng mới nhất bất kỳ là toàn bộ trạng thái patch hiện tại**.
- `DBA_REGISTRY_SQLPATCH` phản ánh SQL patches; `opatch lsinventory` phản ánh Oracle Home. Hai nguồn bổ trợ nhau.

> Trên dịch vụ Oracle Cloud được quản lý, người dùng có thể không có quyền tự chạy các bước hệ điều hành. Khi đó dùng công cụ/console và tài liệu bảo trì của dịch vụ tương ứng.

### 3.4. Quy trình tư duy khi lên lịch RU

Một quy trình hợp lý gồm: xác định release, edition, hệ điều hành và Oracle Home; lấy đúng gói RU cùng README; đọc điều kiện tiên quyết và xung đột patch; thử trên môi trường tương đồng; lập phương án backup/khôi phục; áp dụng theo hướng dẫn cho môi trường đơn, RAC hay Data Guard; kiểm tra cả binary lẫn SQL patch, trạng thái PDB và ứng dụng; cuối cùng ghi lại mức phiên bản mới.

Không dùng một lệnh OPatch chung cho tất cả trường hợp. Thứ tự thao tác khi có RAC, Grid Infrastructure, standby database hoặc Autonomous Database khác với máy đơn, và phải tuân theo README của gói được sử dụng.

## 4. Tham số `COMPATIBLE` kiểm soát điều gì?

### 4.1. Tác dụng thực sự

`COMPATIBLE` là **initialization parameter** xác định mức phiên bản Oracle mà **định dạng và cấu trúc dữ liệu trên đĩa** phải tương thích. Khi được giữ ở mức cũ sau khi nâng cấp phần mềm, Oracle hạn chế những thay đổi trên đĩa hoặc tính năng không tương thích với mức đó. Một số chức năng mới vẫn hoạt động nếu không gây thay đổi định dạng không tương thích; các tính năng khác yêu cầu nâng `COMPATIBLE` mới sử dụng được.

Ví dụ về hai chiều độc lập:

```text
Phần mềm Oracle Database:  19c RU 19.31
Định dạng tương thích:      COMPATIBLE = 19.0.0
                             ↑
                        Không phải số RU
```

`COMPATIBLE` **không** phải là phiên bản của Oracle JDBC, chế độ tương thích SQL cho ứng dụng, mức vá bảo mật, hay phép bảo đảm rằng bất kỳ phần mềm client cũ nào cũng chạy được. Các vấn đề đó cần kiểm tra bằng tài liệu interoperability, driver và chứng nhận ứng dụng.

### 4.2. Các giá trị đáng nhớ

Các giá trị sau mang tính định hướng cho những dòng phổ biến; phạm vi được phép phụ thuộc chính xác bản release và phương thức cài mới/nâng cấp.

| Dòng Oracle | `COMPATIBLE` mặc định thường gặp | Mức tối thiểu cho phép theo hướng dẫn upgrade |
| --- | --- | --- |
| Oracle Database **19c** | `19.0.0` | `11.2.0` |
| Oracle Database **21c** | `21.0.0` | `12.2.0` |
| Oracle AI Database **26ai** | `23.9.0` cho cài đặt mới ở các RU tương ứng từ 23.9 trở đi | `19.0.0` |

**Lưu ý quan trọng với 26ai:** các bản được phát hành trước đây có default khác nhau, bao gồm các mức `23.4.0`, `23.5.0`, `23.6.0`; từ RU 23.9, tài liệu nâng cấp xác định default cho cài đặt mới là `23.9.0`. Nếu **nâng cấp từ cơ sở dữ liệu cũ**, giá trị `COMPATIBLE` có thể **giữ nguyên** sau database upgrade thay vì tự nhảy lên default của một database cài mới. Vì vậy phải **truy vấn tham số thực tế**, không suy đoán chỉ từ tên release.

Một điểm khác cần phân biệt: **mức COMPATIBLE tối thiểu của release đích** không đồng nghĩa “mọi release nguồn đều được phép nâng cấp trực tiếp”. Với 26ai, Oracle công bố đường **direct upgrade từ 19c hoặc 21c**; các phiên bản cũ hơn cần lộ trình trung gian phù hợp. Kiểm tra điều kiện direct upgrade riêng với điều kiện `COMPATIBLE`.

### 4.3. Tại sao tăng `COMPATIBLE` là quyết định lớn?

Giả sử doanh nghiệp nâng database từ 19c sang 26ai. Có thể thực hiện database upgrade trước và tạm **giữ `COMPATIBLE=19.0.0`**, nếu trường hợp đó được tài liệu hỗ trợ, để có thời gian đánh giá ứng dụng và đường downgrade.

Khi sau đó nâng `COMPATIBLE` lên một mức mới như `23.9.0`, hệ thống có thể cho phép các cấu trúc dữ liệu mới. **Không thể đơn giản đổi tham số về `19.0.0` để quay lại trạng thái cũ.** Oracle cảnh báo rằng sau khi tăng `COMPATIBLE`, downgrade cơ sở dữ liệu về release trước không còn được hỗ trợ. Muốn phục hồi thời điểm trước đó phải dựa vào chiến lược backup/restore hoặc phương án phục hồi đã thiết kế **trước khi tăng** tham số, với sự đánh giá tác động dữ liệu phát sinh sau mốc phục hồi.

Đó là lý do không nên gắn việc tăng `COMPATIBLE` như một bước mặc định trong mọi lần cài RU.

### 4.4. Khi nào cần thay đổi?

**Trong Oracle Database 19c/21c:**

- Khi áp dụng RU, **giữ nguyên `COMPATIBLE`**; ví dụ từ `19.30` lên `19.31` không có nghĩa phải đặt `COMPATIBLE=19.31.0`.
- Khi nâng cấp sang dòng release mới, cân nhắc giữ mức cũ trong khoảng thời gian kiểm thử và chỉ tăng khi đã chấp nhận mất đường downgrade, hoặc cần tính năng yêu cầu mức mới.

**Trong Oracle AI Database 26ai:**

- Nguyên tắc chung vẫn là không tăng `COMPATIBLE` chỉ vì có RU.
- Có ngoại lệ theo mức tính năng. Ví dụ, một số khả năng **AI Vector Search** ở các RU 23.x cần `COMPATIBLE` ít nhất **`23.6.0`**. Việc tăng tham số ở đây để **mở tính năng có yêu cầu cụ thể**, không đơn thuần “cho khớp số RU”.
- Khi 26ai chạy các RU cho phép, Oracle hỗ trợ thay đổi tăng `COMPATIBLE` theo cách động với hạn chế riêng; không nên suy rộng cơ chế đó sang 19c.

### 4.5. Cách xem và thay đổi: phân biệt release

Truy vấn read-only:

```sql
SELECT value
FROM   v$parameter
WHERE  name = 'compatible';
```

Ở các bản như **19c**, khi đã đủ điều kiện để tăng lên mức được hỗ trợ, quản trị viên có thể đặt trong **SPFILE** và khởi động lại database:

```sql
-- CHỈ LÀ VÍ DỤ CÚ PHÁP CHO MÔI TRƯỜNG 19c
-- Giả sử mức hiện tại thấp hơn và muốn nâng lên 19.0.0.
ALTER SYSTEM SET compatible = '19.0.0' SCOPE=SPFILE;

-- Việc thay đổi có hiệu lực sau một lần restart có kiểm soát.
```

Không chạy câu lệnh trên khi chưa đối chiếu trạng thái thực tế, điều kiện downgrade, phương án phục hồi và runbook của hệ thống. Với môi trường RAC, các instance phải có cùng mức `COMPATIBLE`; với CDB/PDB, không đặt giá trị tùy ý riêng cho từng PDB (giá trị PDB phải phù hợp với `CDB$ROOT`).

**Ghi chú nâng cao dành riêng cho 26ai:** từ RU 23.9, Oracle tài liệu hóa cách nâng `COMPATIBLE` động (trong những điều kiện nhất định) bằng cú pháp sau:

```sql
-- Ví dụ từ hướng dẫn 26ai: chỉ tăng từ 23.4.0 lên 23.6.0.
ALTER DATABASE SET DOWNGRADE COMPATIBILITY TO '23.6.0';
```

Tên lệnh có từ `DOWNGRADE` nhưng thao tác minh họa là **tăng mức COMPATIBLE**. Sau thay đổi động, vẫn phải đồng bộ giá trị mới trong file tham số/SPFILE để tránh lỗi khi restart. Trong Data Guard, Oracle yêu cầu thực hiện trên standby trước primary; cùng một mức phải được duy trì trên primary/standby. Đây **không phải** cú pháp thay thế phổ quát cho `ALTER SYSTEM ... SCOPE=SPFILE` ở mọi đời Oracle.

## 5. Các kịch bản vận hành thường gặp

### Kịch bản A — Vá bảo mật mà không đổi định dạng dữ liệu

Hệ thống hiện tại:

```text
Release:             Oracle Database 19c
RU:                  19.30
COMPATIBLE:          19.0.0
Mục tiêu:            áp dụng RU 19.31
```

Sau khi cập nhật RU thành công, mức mong đợi là:

```text
Release:             Oracle Database 19c
RU:                  19.31
COMPATIBLE:          19.0.0
```

Điều thay đổi là **mức vá của phần mềm** và có thể các SQL patches; `COMPATIBLE` vẫn giữ nguyên. Cần xác nhận qua inventory, registry và hoạt động ứng dụng.

### Kịch bản B — Nâng cấp 19c lên Oracle AI Database 26ai

Một trình tự quyết định ở mức khái niệm:

1. Kiểm tra đường direct upgrade được hỗ trợ, mức RU tối thiểu, kiểu database, nền tảng, driver và ứng dụng.
2. Ghi nhận `COMPATIBLE` hiện tại và thử quy trình upgrade trong môi trường kiểm thử.
3. Thực hiện database upgrade theo hướng dẫn Oracle; sau đó truy vấn thực tế `VERSION_FULL` và `COMPATIBLE`, không giả định chúng phải giống nhau.
4. Chạy kiểm thử hồi quy, hiệu năng, backup/restore và các nghiệp vụ chính; xác định khoảng thời gian còn cần phương án downgrade.
5. Chỉ khi được chấp thuận mới **tăng `COMPATIBLE`** lên mức cần thiết cho tính năng muốn dùng, chấp nhận ràng buộc không thể downgrade như trước.

Nếu yêu cầu là tính năng cần `COMPATIBLE ≥ 23.6.0`, phải cân nhắc riêng thời điểm bật tính năng thay vì chỉ quyết định theo tên “26ai”.

### Kịch bản C — Tên “26ai”, SQL trả về “23.x”

Giả sử banner ghi **Oracle AI Database 26ai**, còn `VERSION_FULL` hiển thị `23.26.4.0.0`. Đây là mô hình đặt số có thể gặp trong 26ai, không tự động chỉ ra database “bị kẹt ở 23ai”. Xác nhận bằng tài liệu version numbering và `DBA_REGISTRY_SQLPATCH`, tránh kết luận chỉ từ hai chữ số đầu.

### Kịch bản D — Sau patch, trạng thái có vẻ mâu thuẫn

`opatch lsinventory` cho biết Oracle Home đã có RU mới nhưng `DBA_REGISTRY_SQLPATCH` chưa ghi `APPLY/SUCCESS` tương ứng ở database. Cần xem log và quy trình `datapatch` của bản vá; không kết luận “xong” dựa trên mỗi binary. Ngược lại, một dòng `SUCCESS` trong lịch sử SQL patch chưa bảo đảm mọi Oracle Home/instance liên quan đã ở đúng mức cần thiết.

## 6. Câu hỏi thường gặp và tự kiểm tra

**“Tăng RU có làm thay đổi `COMPATIBLE` tự động không?”**  
Không nên giả định. Trong 19c/21c, RU thông thường không yêu cầu đổi `COMPATIBLE`. Ở 26ai, default khi **cài mới** và yêu cầu của một số tính năng có thể phụ thuộc RU; một database **đã nâng cấp** có thể tiếp tục giữ giá trị cũ.

**“Có thể giảm `COMPATIBLE` nếu gặp lỗi không?”**  
Không thể coi đó là phương án rollback. Sau khi tăng mức tương thích, Oracle không cho giảm lại trên cùng dữ liệu theo cách thông thường; cần chiến lược phục hồi đã chuẩn bị từ trước.

**“`COMPATIBLE=19.0.0` thì database không có các bản vá RU mới?”**  
Sai. `COMPATIBLE` nói về mức định dạng dữ liệu; mức RU và patch đã cài được xác định qua version/inventory/registry.

**“Có nên tự đặt `COMPATIBLE` bằng số RU mới nhất?”**  
Không. Phải dùng giá trị được hỗ trợ bởi release cụ thể, theo hướng dẫn Oracle, và chỉ thay đổi khi có lý do rõ ràng.

**“Tất cả tính năng mới đều bị khóa nếu để `COMPATIBLE` thấp?”**  
Không. Tham số chủ yếu kiểm soát tính năng liên quan tới định dạng/cấu trúc trên đĩa không tương thích; mỗi tính năng có điều kiện riêng cần tra cứu.

### Bài tập đọc trạng thái

1. Một database có `VERSION=19.0.0.0.0`, `VERSION_FULL=19.31.0.0.0`, `COMPATIBLE=19.0.0`. Hỏi release, RU và compatibility hiện tại?
2. Sau khi cài RU 19.32, quản trị viên đề nghị tăng `COMPATIBLE` lên `19.32.0` “để đồng bộ”. Nhận định này có phù hợp không?
3. Một ứng dụng đã được kiểm thử trên Oracle AI Database 26ai, nhưng doanh nghiệp còn cần phương án downgrade về release trước trong một thời gian. Có nên tăng `COMPATIBLE` ngay không?
4. Một hệ thống có SQL patch registry thành công nhưng chưa kiểm tra inventory của Grid Infrastructure và các node RAC. Có thể tuyên bố toàn bộ cụm đã được cập nhật chưa?

**Gợi ý trả lời:** (1) 19c, RU 19.31, compatibility 19.0.0; (2) không, số RU không quyết định giá trị `COMPATIBLE`; (3) cần cân nhắc giữ mức cũ đến khi kết thúc giai đoạn cần downgrade; (4) chưa, phải xác thực mọi thành phần liên quan.

## 7. Tài liệu Oracle để tra cứu tiếp

- [Oracle AI Database — About Oracle Database Release Numbers](https://docs.oracle.com/en/database/oracle/oracle-database/26/upgrd/oracle-database-release-numbers.html): cấu trúc `VERSION`/`VERSION_FULL`, RU và MRP.
- [Oracle Database — Patch Maintenance, 19c and Later Releases](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbptc/index.html): phương thức cập nhật, inventory và quy trình bảo trì.
- [Oracle AI Database — What Is Oracle Database Compatibility?](https://docs.oracle.com/en/database/oracle/oracle-database/26/upgrd/what-is-oracle-database-compatibility.html): đường upgrade, default/minimum `COMPATIBLE` và rủi ro downgrade.
- [Oracle AI Database — COMPATIBLE Initialization Parameter](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/COMPATIBLE.html): giá trị, giới hạn và phương thức thay đổi động trong 26ai.
- [Oracle Database 19c — DBA_REGISTRY_SQLPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_REGISTRY_SQLPATCH.html): ý nghĩa các cột lịch sử SQL patch.
- [Oracle Database 19c — V$INSTANCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INSTANCE.html): `VERSION` và `VERSION_FULL`.
- [Oracle AI Database FAQ](https://www.oracle.com/database/faq/): quan hệ giữa 23ai, 26ai và các lựa chọn nâng cấp.

Khi vận hành, luôn lưu riêng **release**, **mức RU**, **patch inventory/SQL patch**, **giá trị `COMPATIBLE`** và **đường khôi phục**. Năm thông tin này mới cho biết đầy đủ trạng thái và các lựa chọn bảo trì của một Oracle Database.
