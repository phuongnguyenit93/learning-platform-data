# Đánh giá tổng dung lượng và tốc độ tăng trưởng

Khi thiết kế lưu trữ bền vững, câu hỏi “cơ sở dữ liệu cần bao nhiêu GB?” mới chỉ là điểm bắt đầu. Hệ thống còn cần biết **dung lượng sẽ tăng nhanh đến đâu**, có bao nhiêu bản sao, chỉ mục và dữ liệu trung gian, cần dự trữ bao nhiêu không gian để duy trì giao dịch, và khi nào phải mở rộng trước khi đạt giới hạn. Dự báo quá thấp gây lỗi ghi, chậm truy vấn và kéo dài khôi phục; dự báo quá cao làm tăng chi phí mà chưa giải quyết được nghẽn hiệu năng.

Bài học thuộc chương **Yêu cầu lưu trữ** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Trong quá trình thiết kế ranh giới persistence cho ứng dụng Java, người học sẽ lập mô hình dung lượng từ lược đồ và lưu lượng, đo thực tế bằng công cụ cơ sở dữ liệu, dự báo tăng trưởng, tính phần dự trữ cho chỉ mục, giao dịch, sao lưu và bản sao, rồi chuyển các con số thành ngưỡng giám sát và kế hoạch mở rộng. Phương pháp phù hợp với hệ quản trị quan hệ, đồng thời chỉ ra những phần cần tính riêng cho object storage, cache và hệ thống sự kiện.

## 1. Phải làm rõ “tổng dung lượng” là tổng của những gì

Một hệ thống có thể lưu cùng dữ liệu ở nhiều nơi. Nếu chỉ cộng kích thước các bảng nghiệp vụ, kết quả thường thấp hơn đáng kể dung lượng cần vận hành.

| Thành phần | Nội dung thường gặp | Cần tính ở đâu? |
| --- | --- | --- |
| Dữ liệu nghiệp vụ chính | Bảng khách hàng, đơn hàng, dòng hàng, lịch sử trạng thái | Dung lượng database chính |
| Chỉ mục và cấu trúc hỗ trợ | B-tree, chỉ mục tìm kiếm trong DB, dữ liệu phục vụ truy vấn | Cùng database nhưng chiếm chỗ riêng |
| Bảng dẫn xuất | Read model, bảng tổng hợp, materialized view, bảng denormalized | Database hoặc hệ chuyên dụng |
| Dữ liệu nội bộ và khoảng trống phát sinh | Page header, row metadata, free space, phiên bản hàng cũ, TOAST, bloat | Dung lượng vật lý của engine |
| Nhật ký giao dịch | WAL/redo/binlog, dữ liệu phục vụ recovery và replication | Đĩa/tầng lưu trữ theo cấu hình của engine |
| Dữ liệu tạm trên đĩa | Sort/hash spill, bảng tạm, tệp staging, thao tác index/rebuild | Dung lượng dự phòng vận hành |
| Replica | Bản sao nóng, bản sao đọc, hệ thống dự phòng | Tính theo từng nút/tầng lưu trữ |
| Sao lưu | Full backup, incremental, snapshot, lưu trữ ngoài site, archive log | Dung lượng backup riêng |
| Dữ liệu ngoài database | File đính kèm, hình ảnh, log ứng dụng, đối tượng phiên bản cũ | Object storage, file storage hoặc dịch vụ tương ứng |

Cần thống nhất **ranh giới đo** trước khi tính:

- **Logical payload:** lượng dữ liệu nghiệp vụ biểu diễn, ví dụ số bản ghi nhân kích thước dự kiến; chưa phản ánh đầy đủ chi phí engine.
- **Database footprint:** các bảng, chỉ mục, TOAST, metadata và khoảng trống bên trong database. Với PostgreSQL, nhiều API kích thước đã bao gồm một số thành phần này.
- **Allocated/used storage:** dung lượng thực tế phân bổ trên volume hoặc dịch vụ lưu trữ, có thể còn chứa WAL, temporary files và không gian được cấp phát.
- **Provisioned capacity:** tổng không gian đã đặt mua/cấp cho mỗi nút, bao gồm phần trống cần dự phòng.
- **Fleet/estate capacity:** tổng dung lượng của primary, standby, các replica, backup và kho dữ liệu khác. Phải nêu rõ đây là tổng phân bổ hay tổng dung lượng vật lý có tính hệ số nhân bản từ nhà cung cấp.

> **Không cộng trùng:** Nếu dùng `pg_total_relation_size` của PostgreSQL để đo một bảng thì số đó đã gồm bảng và chỉ mục tương ứng; không cộng thêm `pg_indexes_size` một lần nữa. Nếu nhà cung cấp báo dung lượng đã tính replication trong gói lưu trữ, không tự nhân hệ số bản sao lần thứ hai.

## 2. Quy đổi đơn vị để tránh sai số lớn

Hai hệ đơn vị dễ bị trộn:

| Đơn vị | Định nghĩa | Ghi chú |
| --- | ---: | --- |
| B | 1 byte | Độ dài thực trong mã hóa (UTF-8 có ký tự nhiều byte) |
| kB, MB, GB, TB | Bội số của 1.000 | Thường thấy trong thông số ổ đĩa, hóa đơn dịch vụ |
| KiB, MiB, GiB, TiB | Bội số của 1.024 | Thường dùng trong công cụ hệ điều hành và tính toán |
| 1 GiB | 1.073.741.824 B | Không bằng 1 GB |
| 1 TiB | 1.024 GiB | Dùng thống nhất trong bảng dự báo ở bài này |

Ví dụ, **100 GB** theo hệ thập phân chỉ bằng khoảng **93,13 GiB**. Khi so dự báo với dashboard nhà cung cấp, phải quy về một đơn vị trước khi kết luận còn bao nhiêu chỗ.

Dung lượng dữ liệu trên đĩa cũng không bằng kích thước chuỗi JSON truyền qua API: cấu trúc trang, kiểu cột, các index, MVCC, dữ liệu nén và bản sao có thể khiến giá trị thực khác nhiều.

## 3. Thu thập đầu vào trước khi lập mô hình

Tối thiểu cần khảo sát bốn nhóm thông tin.

### 3.1. Lược đồ và cách sử dụng dữ liệu

Với mỗi nhóm thực thể hoặc loại đối tượng, ghi:

- Số bản ghi hiện có và kích thước vật lý trung bình; lưu ý phân bố, bản ghi lớn và dữ liệu tùy chọn.
- Tần suất sinh mới, cập nhật, xóa hoặc archive; phân biệt thêm bản ghi với thay đổi cùng một bản ghi.
- Quan hệ 1–N: một đơn có bao nhiêu dòng hàng, bao nhiêu lần thay đổi trạng thái, bao nhiêu audit event?
- Chỉ mục, khóa ngoại, bảng tổng hợp và phiên bản dữ liệu được engine giữ lại.
- TTL, chính sách retention, partition, thời hạn lưu theo quy định và thời gian xóa thực sự.
- Tệp đính kèm, object versions, bản xuất, staging và lưu trữ bên ngoài DB.

Một bản ghi nghiệp vụ có thể tạo nhiều dòng phụ. Ví dụ mỗi đơn hàng chứa trung bình bốn `order_lines`, hai `status_events` và một thông điệp outbox. Ước tính chỉ dựa trên bảng `orders` sẽ bỏ sót phần đáng kể.

### 3.2. Tải ghi và biến động theo thời gian

Không chỉ lấy trung bình tháng. Thu thập theo ngày/tuần/quý, bao gồm:

- Số đối tượng mới mỗi ngày và các mùa cao điểm.
- Tỷ lệ cập nhật và kích thước dữ liệu phát sinh từ cập nhật: phiên bản hàng cũ, WAL, audit và CDC.
- Tăng trưởng số người dùng, tenant, sản phẩm, địa bàn hoặc nguồn dữ liệu.
- Các đợt import/backfill, migration hay khởi chạy dịch vụ mới làm tăng đột biến.
- Lượng dữ liệu thực sự hết hạn hoặc rời khỏi tầng lưu trữ nhanh.

**Tốc độ ghi** và **tăng trưởng dữ liệu ròng** là hai đại lượng khác nhau. Một hàng được cập nhật 1.000 lần có thể vẫn chỉ là một hàng nghiệp vụ ở trạng thái hiện tại, nhưng vẫn tạo nhiều WAL và phiên bản trung gian cần xử lý.

### 3.3. Vận hành và mức phục vụ yêu cầu

Cần biết topology, mức sẵn sàng và giới hạn:

- Bao nhiêu primary, standby, read replica; dữ liệu có nhân bản liên vùng không?
- Chính sách full/incremental backup, thời gian lưu backup, archived WAL, RPO/RTO.
- Dung lượng volume tối đa, ngưỡng cảnh báo, thời gian mua/cấp thêm storage.
- Thời gian thực hiện VACUUM, tạo chỉ mục, migration, backup, restore và chạy truy vấn nặng.
- Giới hạn IOPS, throughput, CPU, bộ nhớ, network, dung lượng và chi phí; không giả định có chỗ trống là hệ thống chạy nhanh.

### 3.4. Chất lượng dữ liệu đo

Gắn **thời điểm, nguồn, đơn vị và mức tin cậy** cho mọi con số. Kích thước dòng lấy từ 100 bản ghi thử nghiệm khác với kích thước đo trên hàng triệu bản ghi có TOAST và index. Một mô hình tốt hiển thị rõ đâu là số thực đo, đâu là giả định và khoảng bất định cần kiểm chứng.

## 4. Lập công thức dung lượng dữ liệu nguồn

Cho một nhóm bản ghi `i`:

- `N_i(t)`: số bản ghi đang được giữ tại thời điểm `t`.
- `s_i(t)`: số byte vật lý trung bình cho phần dữ liệu cơ sở của mỗi bản ghi, theo cách đo đã chọn.
- `A_i(t)`: số bản ghi thêm trong khoảng đo.
- `R_i(t)`: số bản ghi thực sự rời khỏi tầng lưu trữ trong khoảng đo, do xóa/retention/archive.
- `E_i(t)`: điều chỉnh do thay đổi kích thước bản ghi, schema hoặc nén.

Mô hình cấp bản ghi:

```text
N_i(t + Δt) = N_i(t) + A_i(t) - R_i(t)

D_base(t) ≈ Σ [N_i(t) × s_i(t)] + D_other_base(t)
```

Ở đây `D_other_base` có thể là dữ liệu không biểu diễn tốt bằng bản ghi cố định, chẳng hạn blob, file hoặc bảng ngoại lệ. Nếu một đối tượng tạo nhiều bản ghi liên quan, ước tính theo từng bảng hoặc định nghĩa **kích thước trung bình trên mỗi đối tượng nghiệp vụ** gồm tất cả các bản ghi con, tránh cộng hai lần.

Phần dữ liệu tăng ròng trong kỳ phải tính cả thay đổi kích thước:

```text
ΔD_base ≈ D_inserted - D_removed + ΔD_existing_rows + ΔD_schema
```

Công thức này dùng để suy luận ở mức dự báo. DB có MVCC, free space và cơ chế quản lý page: số byte vật lý thật trên đĩa không nhất thiết giảm ngay khi xóa hàng, vì các page có thể được tái sử dụng thay vì trả về hệ điều hành.

### Tính kích thước theo một đơn hàng

Giả sử phép đo/giả định ban đầu cho một đơn hoàn chỉnh:

| Phần dữ liệu | Số lượng trung bình/đơn | Kích thước ước tính | Đóng góp |
| --- | ---: | ---: | ---: |
| Bản ghi đơn và snapshot thuộc tính | 1 | 1,0 KiB | 1,0 KiB |
| Dòng hàng | 4 | 0,4 KiB/dòng | 1,6 KiB |
| Lịch sử trạng thái cần giữ trong tầng này | 2 | 0,2 KiB/sự kiện | 0,4 KiB |
| **Tổng dữ liệu cơ sở/đơn** | | | **3,0 KiB** |

Đây là **con số minh họa** để học cách tính, chưa gồm chỉ mục, WAL, replica, backup và phần trống vận hành. Kích thước thực tế phải đo lại trên lược đồ, dữ liệu và engine của hệ thống đang thiết kế.

Không cộng thêm một lần nữa bảng trạng thái hoặc audit nếu con số 3,0 KiB ở trên đã bao gồm chúng.

## 5. Từ dữ liệu cơ sở đến dung lượng cần cấp

Một mô hình đơn giản theo từng **nút database**:

```text
D_live       = D_base + D_indexes + D_projections

D_db         ≈ D_live × (1 + b)
               (b = tỷ lệ overhead/bloat dự báo chưa được tính trong D_live)

D_peak       = D_db + D_WAL_reserve + D_temp_reserve + D_maintenance

C_required   = D_peak / (1 - h)
               (h = tỷ lệ dung lượng TRỐNG tối thiểu muốn giữ)
```

Ví dụ, để bảo đảm **ít nhất 30% dung lượng trống**, dùng `h = 0,30` và chia cho `0,70`. Nhân với `1,30` chỉ tạo khoảng 23,1% không gian trống so với capacity được cấp. Nên tính theo **ngưỡng sử dụng tối đa**, không nhầm với phần trăm tăng thêm trên số đang dùng.

Mô hình trên là **phương pháp ước lượng**, không phải công thức cố định cho mọi hệ quản trị. Một số phép đo đã chứa bloat/metadata, một số nhà cung cấp cấp riêng WAL hoặc temp. Hãy loại bỏ hoặc điều chỉnh các số hạng đã được tính trong chỉ số đầu vào.

### Các thành phần thường bị bỏ sót

**Chỉ mục.** Index có thể chiếm tỷ lệ đáng kể so với dữ liệu bảng; kích thước phụ thuộc khóa, số hàng, độ chọn lọc, loại index và chiến lược truy vấn. Đo `pg_indexes_size` hoặc chỉ số tương đương trước khi giả định tỷ lệ.

**Bloat và khoảng trống bên trong DB.** Với engine MVCC, UPDATE/DELETE có thể giữ phiên bản cũ trước khi được thu hồi. VACUUM thông thường giúp tái sử dụng chỗ nhưng không luôn giảm kích thước file. Cần đo theo workload và trạng thái autovacuum, không mặc định mọi byte sẽ tự biến mất sau khi xóa.

**WAL và replication lag.** WAL có thể tăng vọt khi batch write, import hoặc tạo index; replica bị chậm/replication slot giữ log khiến đĩa đầy ngay cả khi bảng tăng chậm. Đặt ngân sách WAL theo **đỉnh phát sinh, tốc độ xử lý và thời gian giữ**.

**Sort/hash spill và thao tác bảo trì.** Truy vấn, tái tạo index hoặc thay đổi schema có thể cần thêm không gian tạm. Quy trình “tạo bảng mới rồi chuyển dữ liệu” có thể nhất thời cần gần một bản sao lớn của bảng liên quan.

**Dữ liệu dẫn xuất.** Materialized view và bảng tổng hợp tăng footprint nếu được lưu trong DB. Nếu nằm tại data warehouse/search engine, lập kế hoạch ở tầng đó thay vì cộng vào database chính.

**Replica.** Nếu một primary và một standby đều giữ bản copy đầy đủ, tổng dung lượng provisioned cho hai nút xấp xỉ gấp đôi phần tính trên mỗi nút, nhưng mỗi nút vẫn cần headroom riêng. Replica có kích thước thực khác primary do thời điểm, engine và cấu hình.

**Sao lưu.** Không cộng dung lượng backup vào filesystem primary nếu backup ở object storage riêng. Tính số full/incremental backup, WAL archive, retention, độ nén, phiên bản object và bản sao vùng; snapshot dùng block sharing có mô hình chi phí khác việc nhân kích thước full backup với số ngày.

## 6. Ví dụ đầy đủ: dự báo sau 12 tháng

Giả sử một hệ thống đặt hàng Java/PostgreSQL có các giả định:

| Thông số | Giá trị giả định |
| --- | ---: |
| Số đơn hiện tại trong tầng lưu trữ đang xét | 2.000.000 đơn |
| Đơn mới trung bình | 100.000 đơn/ngày |
| Dữ liệu cơ sở/đơn, gồm dòng hàng và lịch sử cần giữ | 3,0 KiB/đơn |
| Mô hình trong năm dự báo | Lưu các đơn hiện có và đơn mới; chưa archive hoặc xóa |
| Thời gian dự báo | 365 ngày |
| Chi phí chỉ mục thêm so với dữ liệu cơ sở | 40% |
| Phần bloat/overhead ước tính sau khi cộng chỉ mục | 20% |
| Dự phòng WAL và temp | Tính riêng theo workload thực tế |
| Mức dung lượng trống mục tiêu | 30% |
| Topology | 1 primary và 1 standby đầy đủ |

### Bước 1 — Dự báo số đơn

```text
N(365) = 2.000.000 + (100.000 × 365)
       = 38.500.000 đơn
```

### Bước 2 — Dự báo dữ liệu cơ sở

```text
D_base = 38.500.000 × 3,0 KiB
       = 115.500.000 KiB
       ≈ 110,15 GiB
```

So sánh: dữ liệu cơ sở ở hiện tại là khoảng **5,72 GiB**; mỗi ngày thêm khoảng **0,286 GiB** dữ liệu cơ sở nếu tốc độ 100.000 đơn/ngày không đổi.

### Bước 3 — Cộng chỉ mục và bloat

```text
D_indexes  ≈ 110,15 × 0,40 = 44,06 GiB
D_live     ≈ 110,15 + 44,06 = 154,21 GiB

D_db       ≈ 154,21 × 1,20 = 185,05 GiB
```

`185,05 GiB` là **ước lượng footprint database** trong phạm vi dữ liệu đã liệt kê, sau khi thêm chỉ mục và overhead/bloat giả định. Nó **chưa** bao gồm ngân sách cho WAL/temp/bảo trì nếu các thành phần đó nằm ngoài phép đo.

### Bước 4 — Giữ 30% dung lượng trống

Nếu tạm tính riêng phần footprint của DB và chưa cộng các khu vực dự phòng vận hành:

```text
C_base_node ≈ 185,05 / (1 - 0,30)
            ≈ 264,36 GiB / nút
```

Với primary và standby đều cần footprint tương tự, tổng dung lượng cấp cho **hai nút** tối thiểu khoảng **528,72 GiB** trước khi cộng dự phòng WAL/temp và các nhu cầu khác của từng nút. **Không** hiểu 528,72 GiB là một volume duy nhất, và **không** xem đây là tổng dung lượng của cả hệ thống khi còn backup, file đính kèm, log và search index.

Để vận hành, cần đo `D_WAL_reserve`, `D_temp_reserve` và `D_maintenance` theo đỉnh tải. Sau đó tính lại:

```text
C_required_node =
    (185,05 GiB + WAL_reserve + temp_reserve + maintenance) / 0,70
```

Nếu các vùng này nằm trên volume khác, lập ngân sách độc lập với ngưỡng sử dụng của chính chúng.

### Bước 5 — Dùng ba kịch bản thay vì một con số

| Kịch bản | Giả định cần khảo sát | Ảnh hưởng đến dự báo |
| --- | --- | --- |
| Cơ sở (*baseline*) | 100.000 đơn mới/ngày, kích thước 3 KiB/đơn | Khoảng 110,15 GiB dữ liệu cơ sở sau 365 ngày |
| Tăng trưởng mạnh | Khách hàng/đơn mới tăng theo tháng, tỷ lệ bảng con hoặc tệp đính kèm tăng | Dữ liệu có thể tăng phi tuyến theo thời gian |
| Tiết giảm/retention | Archive đơn cũ, phân vùng theo thời gian, xóa đúng thời hạn | Dung lượng tầng lưu trữ nhanh có thể tăng chậm lại hoặc ổn định |

Các giá trị 40% index và 20% bloat là **đầu vào để minh họa cách tính**, không phải hằng số ngành. Cần thay bằng phép đo trên workload và lược đồ thực.

## 7. Dự báo tốc độ tăng trưởng: tuyến tính, cộng dồn và retention

### 7.1. Tốc độ tăng ròng khác tốc độ thêm mới

Với một kho dữ liệu:

```text
Net growth/day ≈ bytes inserted/day
               + bytes added by schema/row-size changes
               - bytes actually released/archived per day
               + net change in indexes/metadata
```

Phân biệt **logic đã xóa** và **vật lý đã thu hồi**. Trong một DB có MVCC, xóa 100 GiB dữ liệu logic không bảo đảm hệ điều hành thấy 100 GiB đĩa trống ngay. Phải thử phương án partition drop, vacuum, rebuild hoặc di chuyển dữ liệu với engine thực tế.

### 7.2. Tăng trưởng tuyến tính

Khi mức thêm ròng trung bình ổn định:

```text
D(t) ≈ D_0 + g × t

D_0 = footprint tại thời điểm bắt đầu
g   = GiB tăng ròng/ngày hoặc GiB/tháng
t   = số ngày hoặc tháng cùng đơn vị với g
```

Đo `g` bằng cách lấy **chênh lệch kích thước giữa các thời điểm**, có điều chỉnh sự kiện bất thường: tạo chỉ mục, thay đổi nén, xóa partition, import lại, tăng số replica hoặc dịch chuyển dữ liệu giữa tầng lưu trữ.

Tính tăng trưởng theo tốc độ nhập là hữu ích khi lên kế hoạch trước khi có dữ liệu lớn; tính theo chênh lệch dung lượng thực cho thấy engine vận hành như thế nào. Nên so hai cách để phát hiện giả định sai.

### 7.3. Lưu lượng tăng theo tỷ lệ

Nếu số bản ghi mới trung bình tháng tăng `r` so với tháng trước, thêm mới của tháng thứ `k` (đánh số từ 0) là:

```text
A_k = A_0 × (1 + r)^k

Tổng thêm mới trong m tháng:
A_total = A_0 × Σ(k=0..m-1) (1 + r)^k
        = A_0 × ((1 + r)^m - 1) / r, nếu r ≠ 0
```

Với 100.000 đơn/ngày, **quy ước 30 ngày/tháng** và tốc độ tăng lượng đơn mới 5% mỗi tháng:

```text
A_0 = 100.000 × 30 = 3.000.000 đơn trong tháng đầu
m   = 12
r   = 0,05

A_total ≈ 3.000.000 × ((1,05^12 - 1) / 0,05)
        ≈ 47,75 triệu đơn mới trong 12 tháng
```

So với 36 triệu đơn nếu **12 tháng đều 30 ngày** và lưu lượng không tăng, kịch bản tăng 5%/tháng tạo thêm khoảng **11,75 triệu đơn**. Với 3 KiB/đơn, đây là chênh lệch hơn **33 GiB dữ liệu cơ sở**, chưa cộng index và overhead. Đừng lấy 12 tháng × 30 ngày ở kịch bản này so trực tiếp với kịch bản 365 ngày ở mục trước mà không điều chỉnh số ngày.

Tăng trưởng người dùng không nhất thiết làm số bản ghi tăng cùng tỷ lệ: thay đổi hành vi, giới hạn nghiệp vụ, chu kỳ sống hoặc tỉ lệ bỏ đơn có thể làm hai đường tăng trưởng khác nhau.

### 7.4. Retention làm thay đổi hình dạng đường tăng trưởng

Nếu hệ thống chỉ giữ dữ liệu online trong `R` ngày, lưu lượng ổn định `a` bản ghi/ngày và dữ liệu hết hạn thực sự được chuyển khỏi tầng đang đo, sau giai đoạn ổn định:

```text
N_online ≈ a × R
D_online ≈ a × R × s
```

Ví dụ 100.000 đơn/ngày, giữ 365 ngày online và 3 KiB dữ liệu cơ sở/đơn sẽ tạo khoảng **104,43 GiB** dữ liệu cơ sở ở trạng thái ổn định, **trước** chỉ mục, bloat và phần lưu trữ lịch sử ngoài tầng online.

Nhưng nếu chỉ đánh dấu `deleted = true`, dữ liệu có thể vẫn nằm trên đĩa. Nếu archive đơn sang object storage thì chỗ trên primary chỉ giảm sau khi xử lý vật lý hoàn tất, và dung lượng archive vẫn cần được tính ở kho đích.

Không áp dụng retention cho dữ liệu nghiệp vụ có yêu cầu lưu hồ sơ dài hạn nếu chưa xác định chính sách pháp lý và quyền riêng tư. Retention phải được xem theo **từng loại dữ liệu**, không một con số chung cho toàn bộ database.

## 8. Đo dung lượng thực tế trong PostgreSQL

Phần này dùng PostgreSQL làm ví dụ cụ thể. Đối với MySQL, SQL Server hoặc cloud database, tìm bộ đo tương đương và kiểm tra rõ số liệu bao gồm các thành phần nào.

### 8.1. Tổng dung lượng database

```sql
SELECT
    current_database() AS database_name,
    pg_database_size(current_database()) AS database_bytes,
    pg_size_pretty(pg_database_size(current_database())) AS readable_size;
```

`pg_database_size` cho biết dung lượng database theo cách PostgreSQL đo, bao gồm các đối tượng trong database như bảng và chỉ mục. Nó **không đại diện cho toàn bộ volume của host**, và không nên xem là phép đo WAL/backup/replica. Cần kiểm tra dashboard đĩa hoặc công cụ của dịch vụ quản lý để biết phần dung lượng còn trống.

### 8.2. Những bảng chiếm nhiều dung lượng nhất

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    pg_size_pretty(pg_table_size(c.oid)) AS table_and_toast,
    pg_size_pretty(pg_indexes_size(c.oid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 20;
```

Lưu ý:

- `pg_table_size` tính phần table cùng các cấu trúc như TOAST, không chỉ dữ liệu cột hữu hình.
- `pg_indexes_size` cho biết tổng dung lượng index của relation đó.
- `pg_total_relation_size` đã bao gồm table và index; không cộng lại các cột khi tổng hợp.
- Với bảng partitioned, truy vấn trên chỉ liệt kê **các relation vật lý** (`relkind = 'r'`), thường là từng partition. Parent partitioned không trực tiếp chứa dữ liệu; muốn tổng theo bảng logic cần nhóm các partition đúng cây phân vùng.
- Kích thước quan sát có thể bao gồm phần trống/bloat; nếu dùng làm đầu vào cho `D_db` thì không tự nhân thêm một tỷ lệ bloat cho phần **đã nằm trong số đo**, trừ khi dự báo phần tăng trong tương lai.

### 8.3. Ước lượng số hàng và hàng chết

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, hữu ích để phát hiện xu hướng nhưng không thay `COUNT(*)` chính xác khi thật sự cần tính số hàng. Số bản ghi nhỏ hoặc có nhiều phiên bản ngoài dòng (TOAST) khiến phép lấy tổng kích thước chia số hàng mang sai số; hãy đo trên dữ liệu thực và đối chiếu từng nhóm cỡ bản ghi.

### 8.4. Đo WAL và tốc độ tăng theo thời gian

Ở phiên bản PostgreSQL có `pg_stat_wal`, có thể quan sát thống kê WAL tích lũy:

```sql
SELECT
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
```

`wal_bytes` là bộ đếm, **không phải dung lượng WAL hiện đang nằm trên đĩa**. Lấy chênh lệch giữa hai thời điểm khi bộ đếm chưa reset rồi chia số giây/phút/ngày mới có được tốc độ WAL phát sinh. Dung lượng `pg_wal` có thể còn phụ thuộc replication slots, archive và tốc độ consumer/standby.

Ví dụ cách thu thập metric vận hành:

```text
Mỗi 1 giờ:
  - database_bytes
  - used_bytes / free_bytes của volume DB và WAL
  - size theo table/index quan trọng
  - wal_bytes tích lũy + stats_reset
  - số hàng mới/xóa, retry, import, backlog replication

Mỗi ngày:
  - tính delta GiB/ngày, xu hướng 7 ngày và 30 ngày
  - phát hiện đột biến do migration, batch hoặc index
  - cập nhật thời điểm dự báo chạm ngưỡng
```

Nếu bộ đếm reset, không được lấy chênh lệch âm như mức tăng âm. Khi dùng managed database, đối chiếu metric nhà cung cấp vì một số dịch vụ tách dung lượng WAL, tính I/O riêng hoặc cung cấp mức lưu trữ có khả năng tự mở rộng.

## 9. Cách đưa số liệu vào code Java mà không “đo bằng trực giác”

Một bộ dự báo có thể nhận dữ liệu đầu vào từ số liệu đã đo và xuất dự báo GiB. Đoạn Java thuần sau tính **dữ liệu cơ sở** trước khi cộng các thành phần vận hành:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class BaseStorageForecast {
    private static final BigDecimal BYTES_PER_GIB =
            BigDecimal.valueOf(1024L * 1024 * 1024);

    private BaseStorageForecast() {}

    public static BigDecimal projectedBaseGiB(
            long existingRecords,
            long newRecordsPerDay,
            int days,
            long averageBytesPerRecord) {

        if (existingRecords < 0 || newRecordsPerDay < 0 ||
                days < 0 || averageBytesPerRecord < 0) {
            throw new IllegalArgumentException("Inputs must be nonnegative");
        }

        BigDecimal totalRecords = BigDecimal.valueOf(existingRecords)
                .add(BigDecimal.valueOf(newRecordsPerDay)
                        .multiply(BigDecimal.valueOf(days)));

        return totalRecords
                .multiply(BigDecimal.valueOf(averageBytesPerRecord))
                .divide(BYTES_PER_GIB, 2, RoundingMode.HALF_UP);
    }

    public static void main(String[] args) {
        // Một đơn, gồm các bảng con đã tính vào trung bình, 3 KiB.
        BigDecimal gib = projectedBaseGiB(
                2_000_000, 100_000, 365, 3L * 1024
        );
        System.out.println(gib); // 110.15 GiB dữ liệu cơ sở
    }
}
```

Ưu điểm của việc tính bằng `BigDecimal` là tránh làm tròn sớm và tràn số ở phép nhân trung gian; tuy nhiên, **độ chính xác số học không bảo đảm độ đúng của giả định**. Giá trị `averageBytesPerRecord` phải phản ánh đúng các bản ghi liên quan, đơn vị và phạm vi đã chọn.

Để đưa mô hình này vào vận hành, có thể quản lý đầu vào theo các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `measuredAt` | Thời điểm lấy mẫu |
| `source` | SQL đo DB, dashboard storage, metric object storage hay ước lượng |
| `environment` | Production/staging, khu vực, tenant hoặc shard |
| `recordType` | Thực thể/bảng hoặc đơn vị nghiệp vụ |
| `existingCount`, `avgBytes` | Dữ liệu đầu kỳ và kích thước đo |
| `dailyInsert`, `dailyDelete` | Dòng dữ liệu vào/ra, cùng phạm vi đo |
| `indexRatio`, `bloatAssumption` | Chỉ áp dụng cho các phần chưa có trong kích thước nguồn |
| `retentionDays`, `forecastDate` | Chính sách lưu và chân trời dự báo |
| `confidence` | Mức tin cậy/phạm vi bất định, gắn với phép đo |

Tuyệt đối không để ứng dụng production chạy `COUNT(*)` trên mọi bảng lớn theo từng request chỉ để phục vụ dashboard dự báo. Thu thập theo lịch và dùng thống kê đã có khi đủ chính xác cho bài toán lập kế hoạch.

## 10. Từ tăng trưởng dung lượng đến yêu cầu hiệu năng

Hai hệ thống cùng chiếm 500 GiB có thể cần cấu hình rất khác:

- Hệ A có dữ liệu lịch sử chủ yếu chỉ đọc, ít truy vấn và ít cập nhật.
- Hệ B có hàng nghìn cập nhật/giây, index nhiều, truy vấn ngẫu nhiên và WAL lớn.

Vì vậy, dung lượng chỉ là **một trục** của thiết kế. Cần ước tính đồng thời:

| Trục | Chỉ số cần quan sát | Hệ quả thiết kế |
| --- | --- | --- |
| Không gian | GiB dùng, GiB trống, GiB tăng ròng/ngày | Cấp volume, retention, archive, phân vùng |
| Lượng thao tác | Insert/update/delete/s, TPS, retry, batch size | WAL, autovacuum, contention, throughput |
| Truy vấn | p95/p99 latency, rows scanned, cache hit, index use | Schema/index/partition, truy vấn tối ưu |
| I/O | IOPS, MB/s, độ trễ read/write, fsync | Chọn storage tier và giới hạn độ đồng thời |
| Khôi phục | Thời gian backup/restore, WAL replay, replication lag | RPO/RTO, topology, quy trình diễn tập |
| Chi phí | Chi phí lưu trữ, I/O, backup, traffic liên vùng | Dữ liệu nóng/lạnh, nén, lifecycle policy |

Dữ liệu tăng cũng khiến kế hoạch **tiến hóa schema** khó hơn. Tạo index đồng thời hoặc backfill trên bảng hàng trăm GiB có thể cần thêm I/O, CPU, WAL, không gian tạm và thời gian. Không giả định rằng “còn đủ GB” là “migration sẽ hoàn thành trong cửa sổ bảo trì”.

Đối với Java, nên thiết kế truy vấn phân trang/keyset, batch có kích thước giới hạn, timeout và retry có kiểm soát. Nếu ingest tăng trưởng mạnh, đo thời gian commit, pool connections và backlog để xác định nghẽn thực sự ở database hay ở tầng ứng dụng.

## 11. Ngưỡng cảnh báo và thời điểm phải mở rộng

Nếu chỉ lên kế hoạch khi volume đạt 95%, hệ thống có thể không còn chỗ cho WAL, index rebuild hoặc tăng trưởng bất thường. Cách lập kế hoạch thực tế là đặt **ngưỡng hành động** trước ngưỡng nguy hiểm.

Một công thức dự báo thời gian tới ngưỡng:

```text
time_to_threshold =
    (capacity × max_used_ratio - used_now) / net_growth_per_time

Điều kiện: net_growth_per_time > 0
```

Ví dụ một volume có **250 GiB**, đang dùng **120 GiB**, tăng ròng **8 GiB/tháng**; tổ chức đặt ngưỡng lập kế hoạch ở **70%** dung lượng:

```text
Ngưỡng 70%           = 250 × 0,70 = 175 GiB
Còn đến ngưỡng       = 175 - 120 = 55 GiB
Thời gian dự báo     = 55 / 8 ≈ 6,9 tháng
```

Nếu mở rộng cần hai tháng làm thủ tục và thêm một tháng dự phòng triển khai/kiểm thử, kế hoạch phải được kích hoạt **trước thời điểm chạm ngưỡng ít nhất ba tháng**, và cập nhật lại khi tốc độ thực tế đổi.

Ngưỡng 70% ở đây là lựa chọn minh họa theo bối cảnh; không có mức cố định cho mọi engine, cloud provider hay workload. Có hệ thống tự mở rộng volume nhưng giới hạn tăng vẫn có thể làm gián đoạn vận hành; có hệ thống cần nhiều không gian cho thao tác rebuild hơn thông thường.

Một dashboard hữu ích có thể hiển thị:

- Dung lượng đã sử dụng / đã cấp theo **từng volume, từng nút và từng tier**.
- Tăng trưởng ròng 7, 30, 90 ngày; ngày dự báo vượt ngưỡng.
- WAL phát sinh và WAL đang giữ; replication lag, archive failures.
- 10–20 bảng/index tăng nhanh nhất, số lượng đối tượng và kích thước trung bình.
- Tuổi dữ liệu theo retention, backlog xóa/archive và mức sử dụng kho lưu trữ lạnh.
- Chi phí dự báo theo tháng và mức biến động giữa kịch bản cơ sở/cao/thấp.

Nếu tốc độ tăng ròng bằng 0 hoặc âm, công thức thời gian chạm ngưỡng không dùng được theo cách trên; vẫn phải theo dõi **đỉnh dung lượng tạm** và sự kiện đột biến.

## 12. Sao lưu, bản sao và kế hoạch khôi phục

Dung lượng cho **backup** và **replication** là yêu cầu riêng:

1. **Primary/standby:** tính footprint dự báo của mỗi nút; cộng dự phòng riêng cho WAL, temp, index maintenance và thời điểm failover.
2. **Backup:** mô tả chiến lược full + incremental/differential + WAL archive, tần suất, retention và công nghệ nén/dedup. Dùng số liệu thực tế của các lần backup để dự báo.
3. **Restore:** kiểm tra nơi phục hồi có đủ dung lượng và thời gian; phục hồi một DB 1 TiB có thể yêu cầu không gian vừa cho bản restore vừa cho WAL replay và kiểm tra.
4. **Địa điểm dữ liệu:** backup khác vùng/khác tài khoản phục vụ mục tiêu khắc phục thảm họa; tránh nhầm dung lượng dự phòng với chính sách bảo vệ dữ liệu.
5. **Bảo mật và quyền riêng tư:** mã hóa, phân quyền, retention, yêu cầu xóa dữ liệu và bản sao của dữ liệu nhạy cảm phải được tính cả ở backup, staging và kho lưu trữ lạnh.

Đừng suy từ “DB hiện dùng 200 GiB” rằng “giữ 30 backup cần đúng 6.000 GiB”. Snapshot theo block, nén, incremental và tỷ lệ dữ liệu thay đổi quyết định dung lượng thực; ngược lại, giữ nhiều phiên bản đối tượng và WAL có thể khiến chi phí cao bất ngờ.

Các chỉ số mục tiêu nên được xác định rõ:

- **RPO:** mức mất dữ liệu tối đa chấp nhận được sau sự cố.
- **RTO:** thời gian tối đa chấp nhận được để dịch vụ hoạt động trở lại.
- **Backup/restore verification:** thử phục hồi định kỳ, kiểm tra tính toàn vẹn và quyền truy cập dữ liệu phục hồi.

Dung lượng lớn ảnh hưởng trực tiếp đến RTO: nhiều dữ liệu hơn thường cần thêm thời gian sao chép, kiểm tra và chạy lại log. Kế hoạch dung lượng vì thế phải đi cùng kế hoạch phục hồi.

## 13. Giảm tăng trưởng mà vẫn giữ đúng nghiệp vụ

Khi dự báo vượt ngưỡng, không chỉ có lựa chọn tăng dung lượng. Có thể cân nhắc:

| Giải pháp | Khi phù hợp | Rủi ro/đánh đổi |
| --- | --- | --- |
| Xóa dữ liệu tạm và staging theo TTL | File import, job trung gian, cache đã hết hạn | Phải không xóa công việc chưa hoàn tất; kiểm soát dữ liệu nhạy cảm |
| Partition theo thời gian | Dữ liệu lớn có truy vấn và retention theo kỳ | Khóa, partition pruning, số partition và thao tác vận hành phức tạp hơn |
| Archive dữ liệu lạnh | Lịch sử ít truy cập nhưng còn nghĩa vụ lưu | Truy vấn chậm hơn, cần quy trình tra cứu/phục hồi |
| Giảm index dư hoặc sửa index kém hiệu quả | Workload ghi cao, nhiều index ít được dùng | Có thể làm chậm truy vấn quan trọng; cần đo thật |
| Nén | Payload lớn hoặc dữ liệu lặp nhiều | Tốn CPU, thay đổi chi phí đọc và khả năng truy cập từng phần |
| Tách file lớn khỏi bảng giao dịch | Blob/ảnh/video làm DB tăng mạnh | Thêm quản lý tham chiếu, quyền truy cập và vòng đời object |
| Cải thiện schema và kiểu dữ liệu | Trường dư, payload lặp, lưu lịch sử không hợp lý | Migration cần kiểm soát, không làm mất thông tin lịch sử cần thiết |
| Scale storage / phân mảnh dữ liệu (*sharding*) | Khi giới hạn nút hoặc workload đã xác nhận | Chi phí và độ phức tạp vận hành, giao dịch và truy vấn phân tán |

Một index làm truy vấn nhanh hơn nhưng cũng tăng dung lượng và chi phí cập nhật. Thêm index vì “trống đĩa còn nhiều” có thể gây tác động đến tốc độ ghi, WAL và backup. Phải đánh giá chỉ mục theo workload, cấu trúc dữ liệu và giới hạn vận hành.

Không xóa dữ liệu nghiệp vụ có giá trị pháp lý chỉ để giải quyết áp lực dung lượng. Thiết kế retention cần xác định tầng lưu trữ phù hợp và trách nhiệm truy xuất lâu dài.

## 14. Mẫu quy trình đánh giá trước khi đưa hệ thống vào production

Có thể áp dụng quy trình gồm bảy bước:

1. **Khoanh phạm vi:** liệt kê các database, bảng, index, projection, file/object, queue, replica và backup cần dự báo; nêu rõ đơn vị.
2. **Đo hiện trạng:** lấy số bản ghi, kích thước vật lý, lịch sử 30–90 ngày, WAL, bloat, tệp đính kèm và chu kỳ backup. Ghi nguồn và thời điểm.
3. **Dự báo dữ liệu nghiệp vụ:** mô hình số bản ghi theo ingest, cập nhật, quan hệ 1–N, retention và thay đổi schema.
4. **Cộng phần vận hành:** index, projection, bloat dự kiến, WAL, temp, migration, replica và backup; kiểm tra không tính hai lần.
5. **Chạy kịch bản:** cơ sở, cao điểm và kịch bản có archive; đặt chân trời 3, 6, 12, 24 tháng theo nhu cầu.
6. **Chọn ngưỡng và hành động:** xác định headroom, dung lượng cần cấp cho từng nút, thời điểm mua thêm/scale, ngân sách và chủ sở hữu quyết định.
7. **Đối chiếu định kỳ:** so forecast với số đo thực, giải thích sai lệch, điều chỉnh giả định, kiểm tra kế hoạch backup/restore và cập nhật sau mỗi đợt migration lớn.

Đầu ra có thể là một bảng ngắn nhưng phải ghi đầy đủ phạm vi:

| Hạng mục | Hiện tại | Dự báo 12 tháng | Nguồn dữ liệu | Hành động |
| --- | --- | --- | --- | --- |
| Dữ liệu cơ sở | Kích thước đo/ước lượng | Theo ingest và retention | Bảng và sản lượng thực tế | Đối chiếu hàng tháng |
| Index, projection, bloat | Dung lượng hiện đo | Tỷ lệ theo tăng trưởng đã kiểm chứng | Thống kê DB | Tối ưu khi thay đổi workload |
| WAL/temp/maintenance | Đỉnh từng thành phần | Đỉnh theo tải và batch | Hệ thống giám sát | Giữ headroom theo workload |
| Primary và replica | Dung lượng cấp từng nút | Theo `C_required` từng nút | Hạ tầng | Scale trước ngưỡng |
| Backup và archive | Dung lượng theo chính sách | Theo full/incremental/retention | Backup service | Diễn tập phục hồi, theo dõi chi phí |

**Các câu hỏi tự kiểm tra**

1. Vì sao không thể lấy kích thước của một JSON rồi nhân số request để dự báo đầy đủ dung lượng DB?
2. Khi dùng `pg_total_relation_size`, tại sao không cộng thêm `pg_indexes_size`?
3. Vì sao cập nhật 1.000 lần lên cùng một hàng có thể phát sinh nhiều WAL nhưng không làm số hàng nghiệp vụ tăng 1.000?
4. Nếu cần giữ 30% chỗ trống, vì sao phải chia dung lượng dự kiến cho `0,70`?
5. Khi retention 365 ngày được áp dụng, điều kiện nào cần đúng để kích thước tầng online ổn định?
6. Hai hệ thống đều có 500 GiB dữ liệu nhưng một hệ cập nhật nhiều, một hệ chủ yếu đọc: ngoài GB, cần đo gì?
7. Dự báo lúc nào chạm ngưỡng cần kết hợp với thời gian cấp hạ tầng ra sao?
8. Vì sao việc có bản backup không tự chứng minh RTO/RPO sẽ được đáp ứng?
9. Làm thế nào phân biệt dữ liệu được xóa logic với dung lượng vật lý thực sự được giải phóng?
10. Khi database đã có số đo dung lượng vật lý thực, việc cộng thêm tỷ lệ bloat có thể tạo sai lệch kiểu gì?

Đánh giá tổng dung lượng và tốc độ tăng trưởng là một **quy trình đo lường và cập nhật giả định liên tục**, không phải phép tính một lần tại thời điểm tạo schema. Khi xác định rõ phạm vi, dùng số liệu có đơn vị nhất quán, mô hình hóa tốc độ phát sinh và retention, tách phần dữ liệu khỏi chi phí vận hành, rồi đối chiếu định kỳ với thực tế, nhóm phát triển Java có thể lựa chọn mô hình dữ liệu, truy vấn, chỉ mục, giao dịch, backup và kế hoạch mở rộng dựa trên bằng chứng thay vì phỏng đoán.
