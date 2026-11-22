# Truy vấn xuyên phân vùng, giao dịch phân tán và chi phí phối hợp

## 1. Bài toán: một yêu cầu nghiệp vụ có thể đi qua bao nhiêu nơi giữ dữ liệu?

Giả sử nền tảng thương mại điện tử có hàng trăm triệu đơn hàng. Doanh nghiệp muốn phân vùng dữ liệu để quản lý dung lượng và tăng khả năng mở rộng. Nhưng một yêu cầu như “cho biết đơn của khách”, “tính doanh thu toàn hệ thống” hoặc “chuyển một khoản tiền giữa hai ví” có thể chạm tới **nhiều phân vùng hoặc nhiều máy chủ**.

Ba câu hỏi phải được tách ra trước khi chọn thiết kế:

1. **Dữ liệu nằm ở đâu?** Một cơ sở dữ liệu có nhiều partition vật lý, hay nhiều shard/cluster do các máy khác nhau nắm quyền ghi?
2. **Phép đọc cần ghé bao nhiêu nơi?** Truy vấn được định tuyến đến một partition, hay phải phân tán, trao đổi dữ liệu và hợp nhất kết quả?
3. **Phép ghi cần nhất quán ở phạm vi nào?** Các thay đổi cùng nằm trong một transaction của một database, hay liên quan đến nhiều nguồn sự thật với transaction và thời gian phản hồi độc lập?

Một hệ thống có thể **partition rất nhiều** nhưng vẫn xử lý giao dịch trong **một database**. Ngược lại, hai shard có thể nằm cùng trung tâm dữ liệu nhưng vẫn đòi hỏi phối hợp phân tán vì chúng có transaction log và quyền commit độc lập.

Trong mô hình hóa dữ liệu, phân vùng không chỉ là quyết định vận hành. Nó ảnh hưởng đến **khóa, foreign key, uniqueness, phạm vi aggregate, JOIN, độ trễ, cách khôi phục và cách người dùng hiểu kết quả**.

### Ví dụ xuyên suốt

Nền tảng quản lý:

- `Order`: đơn đặt hàng, dòng hàng và trạng thái giao.
- `SeatInventory` hoặc `StockReservation`: nguồn duy nhất có quyền xác nhận còn hàng/ghế.
- `Payment`: các lần thu và hoàn tiền đã được provider xác nhận.
- `Customer`: thông tin khách theo tenant và khu vực.
- Báo cáo: doanh số theo ngày, tenant, sản phẩm, kênh bán.

Nếu một đơn và dòng hàng luôn đi cùng một partition, truy vấn đơn có thể rất rẻ. Nếu đơn nằm ở shard A, hàng dự trữ ở shard B và thanh toán ở shard C, thao tác “đặt hàng thành công” không thể coi là một `UPDATE` duy nhất.

## 2. Phân vùng trong một database khác với sharding nhiều nguồn ghi

| Khái niệm | Cách tổ chức | Phạm vi transaction/ràng buộc | Hệ quả thường gặp |
| --- | --- | --- | --- |
| **Partitioning trong một DBMS** | Một bảng logic chia nhiều partition theo ngày, tenant, hash… dưới cùng hệ quản trị. | Nhiều hệ hỗ trợ transaction giữa các partition của **cùng database**; quy tắc khóa/index/unique phụ thuộc DBMS. | Quản trị dữ liệu lớn, partition pruning, dễ lưu trữ/xóa theo kỳ. |
| **Sharding nhiều node** | Các phần dữ liệu nằm ở các máy/cluster hoặc database độc lập; ứng dụng/router phân tuyến. | Transaction cục bộ trong từng shard; xuyên shard cần cơ chế phối hợp riêng nếu đòi atomicity. | Tăng thông lượng và dung lượng phân tán, nhưng thêm độ trễ mạng, lỗi từng node và độ phức tạp. |
| **Replication** | Nhiều bản sao của cùng dữ liệu để đọc/sẵn sàng cao. | Phụ thuộc leader/quorum, đồng bộ hay bất đồng bộ. | Không đồng nghĩa dữ liệu đã được chia nhỏ; đọc replica có thể stale. |
| **Federation/distributed query** | Bộ máy truy vấn đi đến nhiều kho hoặc dịch vụ dữ liệu. | Thường chủ yếu phục vụ đọc; không tự đảm bảo snapshot nhất quán giữa mọi nguồn. | JOIN và tổng hợp có thể phải chuyển dữ liệu qua mạng. |
| **Co-location** | Các hàng hay thao tác có quan hệ thường xuyên được đặt cùng phân vùng/shard. | Giảm các thao tác phải đi xuyên node. | Tăng hiệu quả workload được chọn, có thể gây lệch tải/hot shard. |

**Phân biệt quan trọng:** PostgreSQL declarative partitioning trong **một instance** không tự biến PostgreSQL thành hệ transaction phân tán. Khi một transaction cập nhật hai partition trong cùng database PostgreSQL, đó vẫn là một transaction database bình thường. Chỉ khi thao tác đi tới **nhiều database/cluster độc lập**, vấn đề atomic commit xuyên nguồn mới phát sinh.

Mô hình dữ liệu phải mô tả rõ từ “partition” đang dùng ở tầng nào: bảng, node, cluster, tenant hay miền nghiệp vụ. Không dựa vào số bảng con để kết luận cần Saga hay Two-Phase Commit.

## 3. Vì sao một truy vấn xuyên phân vùng đắt hơn?

Một truy vấn như “xem tất cả đơn của tenant T trong tháng 11” có thể được định tuyến tới một tập partition nhỏ nếu điều kiện lọc khớp khóa phân vùng. Nhưng “tìm đơn có ID bất kỳ, không biết tháng đặt” có thể cần quét nhiều partition nếu không có bảng định tuyến hay chỉ mục toàn cục thích hợp.

Ba khoản chi phí cần đánh giá:

- **Khối lượng đọc:** bao nhiêu partition được mở, bao nhiêu hàng/trang dữ liệu được quét, có tận dụng chỉ mục không?
- **Chi phí phối hợp:** router/coordinator phải lập kế hoạch, gửi yêu cầu đến bao nhiêu shard, đợi kết quả, retry và hợp nhất.
- **Chi phí trao đổi dữ liệu:** số byte được gửi qua mạng để JOIN, SORT, DISTINCT hoặc GROUP BY; có cần shuffle/repartition không?

Với các shard chạy song song, có thể xấp xỉ:

~~~text
T_truy_vấn ≈ T_định_tuyến
          + MAX(T_xử_lý_shard_i + T_truyền_shard_i)
          + T_hợp_nhất_kết_quả
          + T_chờ_phối_hợp_phát_sinh
~~~

Công thức chỉ giúp suy nghĩ về cấu phần, **không** mô tả mọi engine hoặc mọi trường hợp pipeline. Nếu coordinator xử lý tuần tự hoặc mạng nghẽn, tổng chi phí còn cao hơn. Mở rộng từ một shard sang 20 shard có thể làm tăng khả năng gặp **một shard chậm**: truy vấn fan-out thường bị chi phối bởi đuôi độ trễ.

### Partition pruning

**Partition pruning** là việc optimizer bỏ qua các partition chắc chắn không thể chứa hàng khớp điều kiện, dựa trên khóa phân vùng và biểu thức lọc.

- Nếu bảng partition theo `placed_at` theo tháng, điều kiện khoảng ngày cụ thể thường giúp bỏ các tháng khác.
- Nếu bảng sharding theo `tenant_id`, điều kiện đúng `tenant_id` giúp router chọn đúng shard.
- Nếu chỉ lọc `customer_name` mà không có ánh xạ đến shard key, bộ máy có thể phải fan-out.
- Viết `WHERE date(placed_at) = :day` có thể làm một số hệ khó suy ra khoảng partition hơn so với điều kiện nửa mở trên cột gốc; phải kiểm tra kế hoạch thực thi thực tế.

### Ví dụ truy vấn

~~~sql
-- Thường thuận lợi cho bảng phân vùng RANGE theo placed_at.
SELECT tenant_id, order_id, placed_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND placed_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND placed_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';

-- Không có placed_at: cần chiến lược định tuyến theo order_id
-- hoặc có thể phải tìm trên nhiều partition.
SELECT *
FROM orders
WHERE tenant_id = :tenant_id
  AND order_id = :order_id;
~~~

Không khẳng định truy vấn thứ hai **luôn full scan**: nó có thể dùng chỉ mục cục bộ trên nhiều partition, directory lookup, index toàn cục nếu DBMS hỗ trợ, hoặc metadata định tuyến riêng. Vấn đề là **phạm vi phải tìm** và chi phí hợp nhất, không chỉ có dùng index hay không.

## 4. Chọn khóa phân vùng/shard từ các truy vấn và bất biến

Một khóa phân vùng tốt phải cân bằng **định tuyến, phân bố tải, độ ổn định và phạm vi dữ liệu cần giao dịch cùng nhau**.

| Khóa ứng viên | Có ích cho | Rủi ro |
| --- | --- | --- |
| `tenant_id` | Cách ly tenant, đọc/ghi phần lớn trong tenant, co-locate dữ liệu tenant. | Một tenant quá lớn thành hot shard; báo cáo toàn hệ thống vẫn fan-out. |
| `order_id` hash | Phân bố lượng đơn khá đều, tra cứu order theo ID. | Truy vấn mọi đơn của một tenant hoặc mọi dòng hàng tháng có thể rải nhiều shard. |
| `placed_at` theo tháng | Pruning theo kỳ, retention/archive theo tháng, scan thời gian. | Đơn mới dồn vào partition mới nhất; tìm theo order ID thiếu tháng gây scatter. |
| `region_id` | Quy định lưu trú dữ liệu theo vùng, workload địa phương. | Region không đồng đều, giao dịch xuyên vùng và dữ liệu di chuyển vùng. |
| Khóa tổng hợp `tenant_id + entity_id` | Tạo phạm vi định tuyến rõ và chống trùng ID giữa tenant. | Phải có quy ước hash/canonicalization; không tự giải quyết các truy vấn trên nhiều entity. |

Đặt **Order và OrderLine cùng shard** thường có ích vì tạo đơn và dòng hàng là một phạm vi nhất quán cục bộ. Nhưng một ghế hay đơn vị tồn kho có thể được tranh bởi **nhiều Order**: không thể bảo đảm không bán trùng chỉ bằng cách khóa riêng stream/order row.

### Quy tắc co-location

~~~mermaid
flowchart LR
    R["Router theo tenant_id / order_id"] --> A["Shard A: Order + OrderLine liên quan"]
    R --> B["Shard B: các Order khác"]
    A --> PA["Đọc đơn, dòng hàng, cập nhật cục bộ"]
    B --> PB["Đọc đơn khác"]
    A -. "Đặt hàng cần giữ tồn kho" .-> I["Stock owner / inventory shard"]
    B -. "Đặt hàng cần giữ tồn kho" .-> I
~~~

Sơ đồ cho thấy việc đặt dữ liệu cùng nhau giải quyết **một số** thao tác phổ biến, không phải mọi bất biến. Cần chỉ rõ aggregate nào sở hữu số lượng tồn kho hoặc seat inventory; tất cả booking cạnh tranh phải đến cùng điểm quyết định tài nguyên đó.

### Hot shard và độ lệch

Hash đều trên ID khách không bảo đảm đều tải nếu một khách rất lớn. Partition theo thời gian cũng không luôn tốt cho ghi vì dữ liệu mới đổ vào một khoảng gần nhất. Chọn khóa dựa trên phân phối **lưu lượng đọc/ghi**, kích thước tenant, access pattern và khả năng đổi khóa.

**Đừng đổi shard key sau khi đã vận hành mà không có kế hoạch migration**: việc đổi key có thể đòi di chuyển hàng, sửa route, xử lý request đến trong lúc chuyển và đảm bảo không hai shard cùng được ghi như nguồn sự thật.

## 5. JOIN xuyên phân vùng: colocated, broadcast hay shuffle?

JOIN là phép dễ gây chi phí mạng cao khi dữ liệu nằm ở các nơi khác nhau.

| Chiến lược | Cơ chế | Dùng khi | Rủi ro |
| --- | --- | --- | --- |
| **Co-located JOIN** | Các hàng có cùng khóa JOIN nằm cùng shard, JOIN thực hiện cục bộ. | Hai bảng được shard theo cùng khóa, cùng phân bố. | Mất hiệu quả nếu đường JOIN không trùng shard key. |
| **Broadcast JOIN** | Gửi một bảng nhỏ đến nhiều worker để JOIN tại chỗ. | Dimension/reference data thực sự nhỏ và thay đổi theo policy. | Bảng “nhỏ” thành lớn; sao chép nhiều lần, stale reference. |
| **Repartition/shuffle JOIN** | Chuyển cả một hoặc hai phía theo hash của khóa JOIN để gặp nhau. | Bảng lớn nhưng không co-located và không thể broadcast. | Trao đổi dữ liệu lớn, spill, network bottleneck và skew. |
| **Lookup/remote JOIN** | Tra dữ liệu tham chiếu qua service/index theo khóa. | Truy cập chọn lọc, ít khóa, có cache hợp lệ. | Mẫu N+1 requests; timeout và tính mới của cache. |
| **Precomputed mart/materialized view** | Tích hợp trước những quan hệ thường dùng. | Dashboard lặp lại, chấp nhận lag đã định nghĩa. | Rebuild, invalidation và độ trễ khi nguồn đổi. |

Giả sử `orders` và `order_lines` đều phân bố theo `order_id`. Có thể JOIN cục bộ trong shard. Nhưng `dim_product` phân bố theo `product_id` có thể nằm nơi khác. Với dashboard doanh số theo nhóm sản phẩm, có thể broadcast **dimension sản phẩm nhỏ** hoặc dựng fact/mart đã được enrich từ luồng sự kiện có lineage rõ.

**Không phân vùng theo mọi khóa JOIN đồng thời** trên cùng một bản dữ liệu. Chọn workload chủ đạo, dùng index, materialization, bản sao đọc hoặc dịch vụ chuyên biệt cho những câu hỏi khác.

### Tránh fan-out do sai grain

Một order có 3 dòng hàng và 2 lần thanh toán; nếu JOIN trực tiếp hai bảng `order_line` và `payment_movement` theo `order_id`, có thể tạo **6 hàng** và nhân đôi số tiền. Sai số này xảy ra ngay cả khi tất cả dữ liệu ở cùng partition. Phân vùng chỉ làm vấn đề khó phát hiện hơn khi tổng hợp cục bộ và tổng hợp toàn cục bị trộn.

Cần định nghĩa grain:

- `fact_order_line`: một dòng hàng của một đơn.
- `fact_payment_movement`: một giao dịch đã được xác nhận của nguồn thanh toán.
- `dim_product`: một sản phẩm/phiên bản thông tin sản phẩm theo quy tắc thời gian.

Muốn báo cáo tổng thu và doanh số dòng hàng theo ngày, hãy **tổng hợp từng fact về grain so sánh thích hợp trước khi JOIN**, hoặc dùng metric riêng. Không lấy SUM sau JOIN nhiều-nhiều làm kết quả chuẩn.

## 6. GROUP BY, DISTINCT, TOP-K và phân trang toàn cục

Các phép tổng hợp phân tán thường gồm hai chặng:

1. **Partial aggregation** trong mỗi shard để giảm số dòng truyền.
2. **Global merge** tại coordinator hoặc một tầng xử lý tiếp theo để hợp nhất.

Ví dụ SUM tiền theo ngày và tiền tệ:

~~~text
Shard A: 2026-11-20 / VND -> 120.000.000
Shard B: 2026-11-20 / VND ->  80.000.000
Shard C: 2026-11-20 / USD ->       9.000

Global:
2026-11-20 / VND -> 200.000.000
2026-11-20 / USD ->       9.000
~~~

Không cộng 200 triệu VND với 9.000 USD trừ khi có một quy tắc tỷ giá được chấp thuận, gồm thời điểm và nguồn tỷ giá.

| Toán tử | Có thể gộp cục bộ thế nào? | Điểm cần lưu ý |
| --- | --- | --- |
| `SUM`, `COUNT` | Tổng cục bộ rồi cộng tổng. | Cùng grain, đơn vị, không đếm lặp. |
| `AVG` | Gộp `SUM` và `COUNT`, rồi chia. | Không `AVG(AVG(...))` không trọng số. |
| `MIN`, `MAX` | Min/max các giá trị cục bộ. | Null, filter và ngữ nghĩa thời gian phải nhất quán. |
| `COUNT(DISTINCT customer_id)` | Cần khử trùng toàn cục hoặc sketch có sai số được công bố. | Cùng khách xuất hiện nhiều shard; SUM distinct count cục bộ có thể sai. |
| `TOP K` | Mỗi shard trả candidate, coordinator gộp/sắp thứ tự. | Tie-breaker và filter chung phải đúng; cần cơ chế chọn candidate đủ. |
| `ORDER BY ... LIMIT/OFFSET` | Có thể sort cục bộ và merge. | OFFSET lớn tốn tài nguyên; dữ liệu thay đổi làm trang chập chờn. |

### Phân trang nhất quán

Với danh sách đơn toàn hệ thống, `ORDER BY placed_at DESC` không xác định thứ tự ổn định nếu nhiều đơn có cùng timestamp. Nên thêm tie-breaker duy nhất theo phạm vi:

~~~sql
ORDER BY placed_at DESC, tenant_id DESC, order_id DESC
~~~

Dùng **keyset pagination** với cursor gồm đủ các cột thứ tự thường tốt hơn OFFSET lớn. Nhưng nếu dữ liệu thay đổi giữa hai request, ngay cả keyset cũng **không cung cấp snapshot toàn cục bất biến** trừ khi có mốc nhất quán hoặc chính sách chấp nhận sự thay đổi.

Trong dashboard cần kiểm toán, hãy ghi rõ **as-of/watermark/snapshot version** của dữ liệu được công bố, thay vì chỉ xuất số mà không nói các shard đã cập nhật đến đâu.

## 7. Nhất quán khi đọc nhiều shard

Một truy vấn đọc qua 10 shard có thể thu được các ảnh dữ liệu ở 10 thời điểm khác nhau:

- Shard A đã ghi nhận `PaymentCaptured`.
- Shard B chưa nhận event cập nhật trạng thái giao hàng.
- Replica của shard C còn trễ so với leader.
- Một shard đang failover và trả dữ liệu ở vị trí log cũ hơn.

Khi đó, “truy vấn chạy xong” không đồng nghĩa kết quả là **một ảnh chụp nhất quán toàn hệ thống**.

### Các mức kỳ vọng cần mô tả

| Nhu cầu đọc | Mức có thể chấp nhận | Cơ chế xem xét |
| --- | --- | --- |
| Dashboard vận hành theo phút | Eventual consistency với độ trễ đo được. | Per-shard lag, watermark, ghi rõ số liệu sơ bộ. |
| Người dùng xem đơn vừa tạo | **Read-your-writes** sau khi command thành công. | Đọc leader, session token/version hoặc chờ projection cho đúng đơn. |
| Báo cáo tài chính chốt kỳ | Mốc nguồn nhất quán/đã đối soát theo quy tắc. | Barrier/checkpoint nguồn, khóa kỳ báo cáo, restatement có version. |
| Chuyển tiền hoặc ghi số dư | Ràng buộc atomicity/serializability theo nguồn có thẩm quyền. | Transaction và giao thức xử lý cụ thể; không dựa trên truy vấn replica stale. |
| Truy vấn điều tra tại thời điểm X | Cần định nghĩa “đã biết lúc X” hay “có hiệu lực lúc X”. | Thời gian nguồn và thời gian ghi nhận, bitemporal nếu cần. |

Một nguồn phân tán có thể hỗ trợ snapshot toàn cục/transaction phân tán, nhưng **không được tự suy** rằng mọi federated query đều làm được. Khi dùng nhiều hệ quản trị không chia sẻ transaction clock và commit protocol, cần nói rõ giới hạn snapshot; đôi khi một bản báo cáo có watermark nguồn/đối soát riêng đáng tin hơn lời hứa “mọi thứ realtime”.

### Truy vấn song song có thể bị thiếu hoặc đếm lặp khi dữ liệu di chuyển

Trong lúc resharding, một hàng có thể được sao chép từ A sang B hoặc route đổi. Nếu truy vấn fan-out cả A và B mà không có định danh/cutover hợp lệ, một đơn có thể bị đếm hai lần; nếu router chuyển quá sớm, có thể mất hàng đang chuyển.

Cần mô hình **routing epoch/version**, cơ chế cutover, điều kiện read ownership của từng shard và đối soát bằng business key/record version. Chỉ đặt `DISTINCT` ở cuối không sửa được mọi lỗi nếu hai bản sao có status/amount khác nhau.

## 8. Ràng buộc toàn cục khó hơn ràng buộc cục bộ

Một trong các đánh đổi lớn nhất của sharding là **PK, FK, UNIQUE, CHECK và giao dịch** có thể chỉ được DBMS bảo vệ trong **một shard**.

| Bất biến | Khi dữ liệu nằm cùng database/shard | Khi dữ liệu phân tán |
| --- | --- | --- |
| Một đơn có khóa duy nhất trong tenant | Unique key/PK có thể thực thi trực tiếp. | Cần routing/namespace duy nhất, registry toàn cục hoặc ID scheme có bảo đảm. |
| Một ghế chỉ thuộc một booking đang hiệu lực | Unique/lock trên bảng seat/reservation cùng chủ sở hữu. | Các booking ở nhiều shard phải gọi đúng **seat owner** để quyết định. |
| Dòng hàng tham chiếu đơn tồn tại | FK khi nằm trong cùng DBMS có hỗ trợ. | Cross-shard FK thường không được DBMS kiểm tra trực tiếp; cần workflow/kiểm chứng. |
| Không trừ số dư vượt hạn mức | Khóa và transaction trên owner của số dư. | Nếu hạn mức trải nhiều shard, cần một điểm giữ/đặt chỗ hoặc cơ chế nhất quán toàn cục. |
| Tổng một ngày đúng | Query cùng snapshot, cùng grain và đơn vị. | Cần partial aggregate đủ nguồn, dedup, watermark và đối soát. |

**Định nghĩa lại ranh giới aggregate khi cần.** Nếu “không bán quá một ghế” là bất biến mạnh, khóa `Booking` theo booking_id không giúp khi hai booking khác nhau trên hai shard cùng chọn một ghế. Nguồn xác nhận cuối cùng phải là `SeatInventory`, `SeatReservation` hoặc một kho/transaction có thể tuần tự hóa việc giữ ghế đó.

### Global uniqueness

Một ID được sinh bằng UUID có xác suất trùng rất thấp, nhưng điều đó khác với **ràng buộc unique có thể kiểm chứng ở mức nghiệp vụ**. Email, mã ưu đãi hoặc số ghế thường đòi tính duy nhất theo phạm vi cụ thể. Có thể:

- **Định tuyến tất cả bản ghi có cùng unique key đến cùng owner** để database cục bộ thực thi constraint.
- Dùng **registry/uniqueness service** có quy trình reserve/commit/release, định danh request và xử lý timeout.
- Dùng **khóa có namespace** (`tenant_id + external_id`) nếu unique chỉ cần trong tenant.
- Thiết kế lại nghiệp vụ để unique không phải toàn hệ thống nếu không có lý do thật.

Registry toàn cục tạo một **điểm phối hợp** mới và có thể là hotspot, không miễn phí. Không dùng kiểm tra trước `SELECT NOT EXISTS` trên nhiều shard rồi ghi độc lập như một giải pháp unique an toàn khi có cạnh tranh.

## 9. Ví dụ PostgreSQL: phân vùng theo tháng vẫn nằm trong một transaction

Ví dụ dưới đây mô hình hóa đơn hàng và dòng hàng trong **một PostgreSQL database**, phân vùng theo `placed_at`. Mục tiêu là giúp phân biệt partition pruning với transaction xuyên nhiều máy.

~~~sql
CREATE TABLE orders (
    tenant_id       UUID NOT NULL,
    placed_at       TIMESTAMPTZ NOT NULL,
    order_id        UUID NOT NULL,
    customer_id     UUID NOT NULL,
    status          VARCHAR(24) NOT NULL
                    CHECK (status IN
                        ('PLACED', 'CANCELLED', 'FULFILLED')),
    total_minor     BIGINT NOT NULL CHECK (total_minor >= 0),
    currency        CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, placed_at, order_id)
) PARTITION BY RANGE (placed_at);

CREATE TABLE orders_2026_11 PARTITION OF orders
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE TABLE orders_2026_12 PARTITION OF orders
    FOR VALUES FROM ('2026-12-01 00:00:00+00')
               TO   ('2027-01-01 00:00:00+00');

CREATE INDEX ix_orders_tenant_date
    ON orders (tenant_id, placed_at DESC);

CREATE TABLE order_lines (
    tenant_id       UUID NOT NULL,
    placed_at       TIMESTAMPTZ NOT NULL,
    order_id        UUID NOT NULL,
    line_no         INTEGER NOT NULL CHECK (line_no > 0),
    product_id      UUID NOT NULL,
    quantity        NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    line_minor      BIGINT NOT NULL CHECK (line_minor >= 0),
    PRIMARY KEY (tenant_id, placed_at, order_id, line_no),
    FOREIGN KEY (tenant_id, placed_at, order_id)
        REFERENCES orders (tenant_id, placed_at, order_id)
) PARTITION BY RANGE (placed_at);

CREATE TABLE order_lines_2026_11 PARTITION OF order_lines
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE TABLE order_lines_2026_12 PARTITION OF order_lines
    FOR VALUES FROM ('2026-12-01 00:00:00+00')
               TO   ('2027-01-01 00:00:00+00');
~~~

**Ý nghĩa và giới hạn:**

1. PostgreSQL yêu cầu PK/UNIQUE trên bảng partitioned phải chứa **khóa partition** theo các quy tắc được hỗ trợ. Do đó PK của `orders` chứa `placed_at`.
2. Với PK này, database **không tự bảo đảm** `(tenant_id, order_id)` duy nhất trên mọi tháng. Một order ID có thể được chèn thêm vào tháng khác nếu không có cơ chế bảo vệ nghiệp vụ riêng.
3. Foreign key từ `order_lines` sang `orders` có cùng `placed_at` nên xác định được hàng cha theo khóa vật lý đã chọn. Đối với hệ quản trị khác hoặc sharding nhiều cluster, khả năng FK cần được đánh giá riêng.
4. Bảng ví dụ chỉ tạo hai tháng; production cần quản lý tạo partition trước, ranh giới thời gian, partition chưa có, index, retention và migration.
5. Dùng `TIMESTAMPTZ` và khoảng nửa mở theo UTC để tránh chồng ranh giới. “Tháng theo ngày nghiệp vụ địa phương” là một yêu cầu khác, có thể cần khóa partition là `business_day` đã chuẩn hóa.
6. Nếu ứng dụng thay đổi `placed_at` sau khi ghi, hàng có thể phải chuyển partition và làm phức tạp FK. Với đơn hàng, nên coi thời điểm đặt có thẩm quyền là bất biến; correction theo quy trình riêng.

### Giao dịch nhiều partition nhưng một database

~~~sql
BEGIN;

INSERT INTO orders (
    tenant_id, placed_at, order_id,
    customer_id, status, total_minor, currency
) VALUES (
    :tenant_id, :placed_at, :order_id,
    :customer_id, 'PLACED', :total_minor, :currency
);

INSERT INTO order_lines (
    tenant_id, placed_at, order_id,
    line_no, product_id, quantity, line_minor
) VALUES (
    :tenant_id, :placed_at, :order_id,
    :line_no, :product_id, :quantity, :line_minor
);

COMMIT;
~~~

Dù hai bảng partitioned, hai phép ghi ở đây được commit/rollback bằng **một transaction PostgreSQL**. Đây **không phải 2PC xuyên các shard độc lập**.

Nếu `order_id` phải unique theo tenant trên toàn thời gian, có thể dùng một bảng `order_id_registry(tenant_id, order_id, placed_at)` **không partitioned** với `PRIMARY KEY (tenant_id, order_id)` và đăng ký ID trong cùng transaction. Nhưng bảng registry có thể thành điểm nóng/dung lượng lớn; nếu chuyển sang nhiều cluster, unique toàn cục lại cần một chiến lược có owner/cơ chế phối hợp. Không tùy tiện coi registry trong một DB là giải pháp tự động xuyên mọi cluster.

### Kiểm tra pruning bằng kế hoạch thực thi

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_minor
FROM orders
WHERE tenant_id = :tenant_id
  AND placed_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND placed_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Ở môi trường thử nghiệm phù hợp, kiểm tra partition nào được quét, số hàng, thời gian, buffer và tính hiệu quả của chỉ mục. `EXPLAIN ANALYZE` **thực thi câu truy vấn**; tránh dùng tùy tiện với lệnh ghi thật. Không kết luận mọi PostgreSQL/distributed SQL engine có cùng kế hoạch cho cùng câu SQL.

## 10. Khi một command phải thay đổi hai shard: những yêu cầu cần xác định

Ví dụ chuyển 100.000 VND từ ví trên shard A sang ví trên shard B. Từ góc nhìn nghiệp vụ, không được khẳng định “đã chuyển thành công” nếu tiền bị trừ ở A nhưng chưa được ghi có ở B.

Cần đặt câu hỏi:

- **Atomicity:** phải commit cả hai nơi hoặc không nơi nào không?
- **Isolation:** trong khi chuyển, các giao dịch khác được phép quan sát trạng thái nào?
- **Durability:** khi node crash, trạng thái đã commit/ý định chuyển có còn khôi phục được?
- **Timeout/unknown outcome:** nếu nhận timeout, làm sao biết ghi có đã xảy ra hay chưa?
- **Idempotency:** retry command có thể chuyển tiền hai lần không?
- **Invariant:** tổng nghĩa vụ và khả năng chi tiêu được kiểm soát ở đâu? Có hệ ledger làm nguồn sự thật không?

Không nhầm **atomic commit** với **nghiệp vụ hoàn tất**. Một hệ thanh toán ngoài có thể chưa trả kết quả ngay dù transaction trong database đã commit một bản ghi `TRANSFER_PENDING`.

## 11. Two-Phase Commit (2PC): atomic commit với chi phí phối hợp

**Two-Phase Commit** phối hợp nhiều transaction participant để quyết định **cùng commit hoặc cùng abort**, khi tất cả các bên hỗ trợ giao thức và các log cần thiết bền vững.

### Pha 1 — Prepare

Coordinator yêu cầu từng participant kiểm tra và chuẩn bị phần transaction của mình. Participant ghi nhận trạng thái prepared bền vững theo khả năng hệ quản trị, giữ tài nguyên/khóa cần thiết và trả lời có thể commit hay không.

### Pha 2 — Commit hoặc Abort

- Nếu tất cả trả lời chuẩn bị được, coordinator ghi quyết định commit bền vững rồi yêu cầu các participant commit.
- Nếu có một bên không thể prepare, coordinator quyết định abort và yêu cầu rollback.
- Khi coordinator hoặc mạng gặp lỗi sau prepare, participant có thể phải **giữ trạng thái chưa ngã ngũ** cho tới khi quyết định được khôi phục.

~~~mermaid
sequenceDiagram
    participant App as Service
    participant C as Coordinator
    participant A as Shard A
    participant B as Shard B
    App->>C: Begin distributed transaction
    C->>A: PREPARE
    C->>B: PREPARE
    A-->>C: PREPARED
    B-->>C: PREPARED
    Note over C: Ghi quyết định durable
    C->>A: COMMIT
    C->>B: COMMIT
    A-->>C: ACK
    B-->>C: ACK
    C-->>App: Committed
~~~

Sơ đồ là **trường hợp thành công**. Khi coordinator crash sau prepare, việc khôi phục quyết định và xử lý participant treo là một phần bắt buộc của thiết kế; không thể bỏ vì demo chỉ có luồng happy path.

### Đánh đổi của 2PC

| Lợi ích | Chi phí/rủi ro cần xem xét |
| --- | --- |
| Atomic commit ở nhiều participant hỗ trợ giao thức. | Thêm round trips, durable logging, coordinator và quá trình phục hồi. |
| Dễ giữ cách suy nghĩ “một transaction” ở tầng commit. | Prepared transaction có thể giữ khóa/tài nguyên; tắc nghẽn khi node/coordinator lỗi. |
| Phù hợp khi không chấp nhận trạng thái commit một phần. | Không phù hợp nếu một “participant” là API bên ngoài không hỗ trợ prepare/rollback. |
| Có thể dùng trong distributed SQL/transaction coordinator chuyên dụng. | Phải đánh giá isolation xuyên node và khả năng chịu lỗi thực tế, không chỉ có tên tính năng. |

**2PC không tự bảo đảm serializability toàn cục.** Atomic commit chỉ quyết định số phận commit của các phần; cách các transaction giao nhau và quan sát dữ liệu còn phụ thuộc isolation/concurrency control của toàn hệ. Cũng không tự tạo “exactly once” đối với email, message broker hay ngân hàng ngoài transaction.

Trong PostgreSQL, chức năng prepared transaction như `PREPARE TRANSACTION` cần cấu hình và quản trị riêng; không nên bật chỉ để “giải quyết” một nghiệp vụ nếu chưa có coordinator đáng tin, giám sát transaction treo và quy trình recovery.

## 12. Saga và hành động bù trừ: phối hợp nghiệp vụ thay vì một commit chung

Nếu các dịch vụ độc lập không tham gia một transaction phân tán, **Saga** có thể tổ chức chuỗi các **local transactions** và các hành động xử lý thất bại/bù trừ.

Ví dụ quy trình đặt vé:

1. Booking tạo trạng thái `PENDING` trong nguồn của mình.
2. SeatInventory giữ ghế có thời hạn, xác nhận reservation.
3. Payment tạo yêu cầu thu tiền với idempotency key.
4. Khi Payment xác nhận capture, Booking chuyển `CONFIRMED`.
5. Nếu không thể giữ ghế hoặc capture bị từ chối, các bước thích hợp được hủy/bù trừ theo trạng thái thực tế.

~~~mermaid
flowchart TD
    B["Booking PENDING"] --> S["Seat: reserve bằng idempotency key"]
    S --> OK{"Giữ ghế được?"}
    OK -->|"Không"| X["Booking REJECTED"]
    OK -->|"Có"| P["Payment: request capture"]
    P --> C{"Kết quả đã xác minh?"}
    C -->|"Captured"| F["Booking CONFIRMED"]
    C -->|"Failed"| R["Release seat nếu còn reservation hợp lệ"]
    R --> Z["Booking FAILED"]
    C -->|"Unknown / timeout"| U["Payment PENDING_RECONCILIATION"]
    U --> Q["Query provider / chờ callback / đối soát"]
    Q --> C
~~~

**Điểm khó:**

- “Gửi lệnh hoàn tiền” là `RefundRequested`, không phải `RefundConfirmed`. Hành động bù trừ không thể đảm bảo đảo ngay một khoản capture đã thực hiện.
- Một email đã gửi hoặc hàng vật lý đã giao **không thể rollback như dữ liệu SQL**; compensation phải mô tả một sự việc mới (xin lỗi, thu hồi, hoàn tiền) và các giới hạn.
- Nếu Payment timeout, **không được mặc định capture thất bại** rồi gửi lệnh thu mới với ID khác. Cần đối soát theo transaction ID/idempotency key.
- Saga chấp nhận **trạng thái trung gian**. API và dashboard phải cho thấy `PENDING`, `FAILED`, `COMPENSATING` hoặc `NEEDS_REVIEW` thay vì ép về nhị phân thành công/thất bại.
- Saga **không tương đương atomicity ACID trên tất cả các hệ**; nó là cách quản lý workflow và nhất quán theo thời gian.

### Thiết kế tối thiểu cho trạng thái điều phối

Một bảng tác vụ Saga có thể giữ `saga_id`, `business_request_id`, `step`, `state`, `expected_entity_version`, `retry_count`, `last_error_code` và thời hạn xử lý. Các bước cần có **idempotency key ổn định**, không tạo request mới ngẫu nhiên cho mỗi lần retry.

Khi chọn Saga, cần giải thích rõ **khi nào hệ thống được phép hiển thị nghiệp vụ thành công** và những bước nào có thể bù trừ khi đã có side effect thực.

## 13. Transactional outbox: giao dịch cục bộ và truyền thông tin đáng tin

**Transactional outbox** xử lý khoảng trống nguy hiểm giữa “đã commit trong DB” và “đã phát message”. Trong cùng transaction **cục bộ**, ứng dụng ghi bản ghi nghiệp vụ và một dòng outbox.

~~~sql
CREATE TABLE booking_outbox (
    message_id       UUID PRIMARY KEY,
    booking_id       UUID NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);

CREATE INDEX ix_booking_outbox_pending
    ON booking_outbox (created_at, message_id)
    WHERE published_at IS NULL;
~~~

Cùng transaction cập nhật `booking.state` và `booking_outbox` giúp không mất **ý định thông báo** sau commit. Relay gửi message qua broker; nếu relay chết sau gửi nhưng trước khi đánh dấu, message có thể được phát lại. Consumer phải dedup theo `message_id` và/hoặc business operation key.

**Outbox không làm một transaction xuyên shard trở nên nguyên tử.** Nó tạo một đường chuyển giao đáng tin từ transaction cục bộ sang các bước tiếp theo. Nếu SeatInventory và Booking mỗi bên là một nguồn sự thật độc lập, quy trình tương tác vẫn cần xác nhận, timeout, idempotency và compensation.

### Chống xử lý lặp ở consumer

Một consumer có thể có bảng `processed_message(consumer_name, message_id)` với PK tổ hợp, chèn dấu và cập nhật read model **trong cùng transaction**. Nếu dấu đã tồn tại, bỏ qua lần lặp. Nếu update target rồi mới ghi dấu trong transaction khác, crash giữa hai bước có thể làm cộng số liệu hai lần.

Cần phân biệt:

- `message_id`: xác định bản thông báo để chống phát lại.
- `business_request_id`: xác định thao tác nghiệp vụ để chống lệnh trùng.
- `entity_version`: giúp phát hiện trạng thái cũ/sai thứ tự.
- `event_id`: định danh sự việc đã chấp nhận ở nguồn.

Không giả định một ID thay thế hợp lệ tất cả ID còn lại trong mọi kiến trúc.

## 14. Chọn giữa local transaction, 2PC, Saga và thiết kế lại ranh giới

| Phương án | Cam kết chính | Nên chọn khi | Điều không tự giải quyết |
| --- | --- | --- | --- |
| **Một transaction trên cùng DB/shard** | Atomicity/isolation trong phạm vi DBMS. | Các bất biến chính có thể co-locate. | Tác động ra API/broker và các nguồn khác. |
| **2PC/distributed transaction** | Atomic commit giữa participant hỗ trợ. | Không chấp nhận commit một phần; hạ tầng có coordinator và isolation phù hợp. | Side effect không hỗ trợ prepare, global serializability nếu không được đảm bảo. |
| **Saga** | Điều phối nhiều local transaction và bù trừ. | Dịch vụ độc lập; chấp nhận trạng thái trung gian có quản trị. | Không có rollback vật lý tức thì hoặc atomicity toàn hệ. |
| **Reservation/escrow/owner** | Biến một bất biến toàn cục thành quyết định tại một owner. | Tranh tài nguyên, tồn kho, hạn mức cần điểm kiểm soát rõ. | Độ trễ đến owner, hotspot và tính sẵn sàng của owner. |
| **Async read model/ETL** | Truy vấn tổng hợp hoặc hiện thị được xây từ nhiều nguồn. | Không cần quyết định ghi tức thời trên nhiều shard. | Độ trễ/nhất quán và lỗi đối soát nguồn. |

**Ưu tiên giảm phạm vi phải phối hợp** trước khi chọn giao thức đắt tiền:

- Co-locate những bản ghi có invariant chặt.
- Chọn owner cho tồn kho/ghế/số dư.
- Tránh một transaction đòi sửa đồng thời Catalog, Order, CRM và Analytics chỉ vì một API muốn trả dữ liệu đầy đủ.
- Tách dữ liệu quyết định giao dịch khỏi dữ liệu phục vụ báo cáo.
- Biến các bước không cần đồng bộ thành outbox + projection với SLO rõ.

2PC hay Saga là **hệ quả của yêu cầu nhất quán và ranh giới nguồn sự thật**, không phải điểm bắt đầu của mô hình dữ liệu.

## 15. Resharding: di chuyển dữ liệu làm tăng chi phí phối hợp

Khi một shard quá lớn, hệ thống có thể phải tách shard, thêm node hoặc di chuyển một tenant. Bài toán không chỉ là copy hàng.

Quy trình mức cao:

1. **Lập bản đồ ownership hiện tại** của từng partition/shard và phiên bản định tuyến `routing_epoch`.
2. **Tạo đích và copy dữ liệu lịch sử** với checksum, số hàng và ranh giới truy cập.
3. **Theo dõi thay đổi đang diễn ra** bằng CDC/log/cơ chế đồng bộ có bảo đảm không mất commit; không dùng `MAX(id)` được cấp trước commit làm watermark chắc chắn.
4. **Bắt kịp phần đuôi**, kiểm tra row count, khóa nghiệp vụ, version, tổng tiền và dữ liệu xóa/correction.
5. **Chuyển quyền ghi** theo quy trình có fencing token/lease hoặc lock phù hợp; không cho hai shard cùng commit như owner hợp lệ.
6. **Chuyển định tuyến đọc** và quan sát dữ liệu chậm/trùng; xác định khi nào đích đủ tin cậy.
7. **Thu hồi bản nguồn cũ** theo retention và kế hoạch rollback đã được phê duyệt.

Nếu router A chưa biết routing epoch mới trong khi router B đã biết, hai request có thể đi hai nơi. Có thể dùng redirect/lookup directory có version, fencing hoặc cơ chế tương đương. Cần lựa chọn phù hợp khả năng chịu lỗi và mô hình nhất quán của hệ đang dùng.

### Cân bằng tải không chỉ dựa trên số hàng

Một shard lưu 1 triệu đơn cũ ít truy vấn có thể nhẹ hơn một shard lưu 50.000 đơn đang bị tranh ghi liên tục. Theo dõi cả **CPU, write QPS, lock contention, network, storage, IO, replication lag và hotspot per key**, không chỉ số row.

Thêm node có thể giúp phân bố dữ liệu, nhưng **không làm mất chi phí query fan-out**. Một báo cáo truy vấn tất cả tenant có thể cần đi qua nhiều node hơn sau khi mở rộng.

## 16. Khác biệt theo kiểu lưu trữ và mô hình dữ liệu

| Loại dữ liệu/hệ | Chiến lược phân phối thường xem xét | Cạm bẫy đặc trưng |
| --- | --- | --- |
| **Quan hệ OLTP** | Tenant/order key, index, partition theo thời gian; FK/unique trong phạm vi bảo đảm. | JOIN xuyên shard, transaction/constraint toàn cục, hot key. |
| **Document database** | Shard key theo tenant/document owner, nhúng aggregate hay tham chiếu. | Query thiếu shard key gây scatter, transaction đa document/shard đắt hơn đơn document. |
| **Graph** | Partition theo cộng đồng/đỉnh, replicate cạnh hoặc dữ liệu lân cận có chọn lọc. | Truy vấn đường đi qua biên partition có nhiều network hops, fan-out theo bậc đỉnh. |
| **Kho phân tích/MPP** | Hash/range distribution, clustering, broadcast nhỏ, shuffle joins. | Data skew, shuffle lớn, distinct toàn cục, thời gian merge và chi phí scan. |
| **Time-series** | Theo thời gian + cảm biến/tenant, rollup và retention theo kỳ. | Dữ liệu mới hotspot, late correction vào partition cũ, unique theo measurement ID. |

**Không bê nguyên một quy tắc giữa các engine.** “Shard key bắt buộc nằm trong unique index” phụ thuộc hệ và phương án phân vùng; “transaction hỗ trợ nhiều partition” cũng phụ thuộc DBMS. Khi chọn cấu trúc, đọc hợp đồng thực tế của công nghệ và kiểm chứng bằng workload cùng failure mode.

Điểm chung là **định danh, grain, thời gian và quyền sở hữu bất biến** phải rõ để hệ thống biết truy vấn hoặc cập nhật phần nào của dữ liệu.

## 17. Đo chi phí phối hợp và quan sát lỗi trong vận hành

Một benchmark chỉ đo latency một truy vấn khi không lỗi là chưa đủ. Cần đo cả **tail latency, fan-out, dữ liệu truyền qua mạng và trạng thái khi một shard chậm hoặc mất kết nối**.

| Chỉ số | Phản ánh | Cách dùng |
| --- | --- | --- |
| **Partitions/shards touched per query** | Mức fan-out. | So sánh truy vấn có/không có routing key. |
| **Partition pruning ratio** | Số partition tránh quét được. | Phát hiện query predicate không khớp partition key. |
| **Rows/bytes shuffled** | Chi phí JOIN/GROUP BY xuyên node. | Quyết định colocate, broadcast hay materialization. |
| **P50/P95/P99 latency** | Độ trễ người dùng và tail. | Kiểm tra tác động tăng số shard/slow shard. |
| **Coordinator CPU/memory/queue** | Nút cổ chai khi merge kết quả. | Cân nhắc partial aggregate, pushdown, giới hạn query. |
| **Lock wait/transaction duration** | Phối hợp ghi/khóa. | Phát hiện transaction lâu, prepared transaction tồn đọng. |
| **Distributed commit failure/unknown outcome** | Transaction bị treo, timeout hoặc phải phục hồi. | Thiết lập runbook recovery/idempotency. |
| **Saga pending/compensating age** | Workflow chưa hoàn tất. | Cảnh báo và đối soát từng bước. |
| **Outbox lag/duplicate count** | Độ trễ relay và retry. | Đánh giá read-your-writes/consumer correctness. |
| **Replica/CDC lag và watermark** | Độ mới của dữ liệu báo cáo. | Công bố mức sơ bộ/chốt và kiểm tra mất record. |
| **Hot shard/key skew** | Lệch tải theo tenant/ID. | Cân nhắc split/move/routing và rate limiting. |
| **Rebalance drift** | Mất/trùng hàng khi di chuyển. | Đối chiếu source/target và routing epoch. |

### Kịch bản lỗi cần diễn tập

- Một shard đang chạy query global bị chậm 10 giây; coordinator timeout hay trả kết quả thiếu? **Không âm thầm trả thiếu như đủ**.
- Coordinator 2PC chết sau khi cả hai shard đã prepare; ai khôi phục quyết định và giải phóng khóa?
- Payment API trả timeout sau khi provider đã capture; retry với ID nào để không thu tiền lần hai?
- Outbox relay phát message rồi crash trước khi ghi `published_at`; consumer xử lý bản lặp ra sao?
- Resharding copy dữ liệu nhưng có một bản cập nhật commit trong lúc chuyển; cursor nào chứng minh không bỏ sót?
- Một replica mất kết nối rồi được đọc trong truy vấn báo cáo cuối kỳ; hệ thống công bố độ trễ thế nào?

Bảng đo và kịch bản lỗi phải gắn với **SLO thực tế**; không có mục tiêu số cụ thể thì không thể tuyên bố một kiến trúc là “tối ưu” chỉ nhờ tăng số shard.

## 18. An toàn, riêng tư và khả năng kiểm chứng

Phân tán dữ liệu còn tạo ra rủi ro quản trị:

- **Tenant isolation:** routing key phải có tenant scope, không để query thiếu `tenant_id` vô tình đi qua tenant khác khi không có quyền. Cần kiểm tra ở authorization và tầng dữ liệu, không chỉ trong router.
- **Residency:** dữ liệu bị yêu cầu lưu tại vùng địa lý cụ thể phải được kiểm soát cả ở replica, backup, cache, export và job rebuild.
- **Retention/xóa:** purge theo partition thời gian có thể rất hiệu quả nhưng **không tự hợp pháp hóa** việc xóa toàn bộ dữ liệu của một kỳ; có thể có hold và nghĩa vụ giữ khác nhau.
- **Lineage:** mart toàn cục phải truy được nguồn shard, version/cursor và quy tắc biến đổi, nhất là khi có correction.
- **Backup/restore:** snapshot ở các shard tại các thời điểm khác nhau không tự là một backup giao dịch toàn cục; cần quy trình recovery với mốc nhất quán hoặc điểm chốt được xác nhận.
- **Rebalancing:** bản sao trung gian vẫn có thể chứa dữ liệu cá nhân; cần quản lý quyền, mã hóa và thu hồi sau khi chuyển.
- **Global IDs:** namespace và định danh tham chiếu không được tái sử dụng nhầm sau khi di chuyển, xóa mềm hoặc mở tenant mới.

Dữ liệu từ nhiều vùng hoặc hệ thống có thể chịu các chính sách quyền riêng tư khác nhau. Không dùng replication như lý do “có thể đọc mọi bản ở bất kỳ nơi nào”.

## 19. Quy trình ra quyết định thiết kế phân vùng

Một **Architecture Decision Record (ADR)** về phân phối nên trả lời được:

1. **Dữ liệu và grain:** Order, OrderLine, PaymentMovement, Inventory, Customer có business key/PK gì?
2. **Đường truy vấn:** 10 truy vấn có tần suất và chi phí cao nhất là gì; có đủ shard key trong predicate không?
3. **Bất biến:** những thao tác nào phải atomic/serializable ngay; liệu có co-locate hoặc chỉ định owner được không?
4. **Khóa phân vùng:** tenant, order, region hay thời gian? Kiểm tra phân phối thật và hotspot.
5. **Phạm vi transaction:** cùng một DB, nhiều DB độc lập, hay nhiều dịch vụ với side effect ngoài?
6. **Phương án JOIN/aggregate:** colocated, broadcast, shuffle, precomputed mart, hoặc chuyển thành truy vấn hai chặng?
7. **Nhất quán đọc:** eventual, read-your-writes hay snapshot chốt kỳ; cần watermark nào?
8. **Phương án ghi:** local transaction, 2PC, Saga, outbox, reservation/ledger owner?
9. **Khả năng tiến hóa:** thêm shard, đổi key, resharding, schema migration, xử lý lịch sử và xóa dữ liệu?
10. **Kiểm chứng:** SQL/constraints, chaos/failure test, đo tail latency, đối soát và tiêu chí rollback?

### Ma trận quyết định rút gọn

| Yêu cầu chủ đạo | Thiết kế nên thử đầu tiên |
| --- | --- |
| Truy vấn theo tenant là chính, ít cross-tenant | Co-locate theo tenant, xem xét hot tenants. |
| Dữ liệu theo kỳ rất lớn, retention theo tháng | Range partition theo ngày/tháng, index và quản trị partition. |
| Một order và dòng hàng phải commit cùng nhau | Cùng database/shard và transaction cục bộ. |
| Một ghế chỉ được bán một lần dù booking ở nhiều shard | Seat owner/reservation service có concurrency control. |
| Chuyển tiền yêu cầu commit đồng thời hai nguồn có transaction support | Đánh giá distributed transaction/2PC hoặc thay ranh giới ledger, cần kiểm tra isolation. |
| Workflow có provider ngoài, hỗ trợ refund/release với trạng thái trung gian | Saga + outbox + idempotency + đối soát. |
| Báo cáo toàn doanh nghiệp theo ngày | Partial aggregates/materialized analytical mart, watermark và kiểm chứng. |
| Người dùng vừa ghi xong phải thấy dữ liệu | Read leader/session version hoặc projection await theo đúng entity. |

Không nhất thiết dùng mọi giải pháp cùng lúc. Thiết kế ít đường phối hợp hơn thường dễ đúng, dễ quan sát và dễ khôi phục hơn.

## 20. Bài tập thực hành: tối ưu đơn hàng, tồn kho và báo cáo toàn hệ thống

**Bối cảnh:** nền tảng bán vé sự kiện phục vụ nhiều tenant, mỗi tenant có nhiều địa điểm và mỗi show có hàng nghìn ghế. Các đơn và dòng vé được ghi tại các shard theo tenant/order; danh mục ghế thuộc một dịch vụ Inventory riêng. Cổng thanh toán trả callback có thể chậm hoặc lặp. Đội tài chính cần báo cáo dòng tiền theo ngày và loại tiền; bộ phận hỗ trợ cần tra cứu order ID bất kỳ.

### Yêu cầu thiết kế

1. **Vẽ sơ đồ nguồn sự thật:** Order, SeatInventory, Payment, Customer và Analytics; chỉ rõ mỗi miền có DB/shard và owner nào.
2. **Chọn shard key:** so sánh `tenant_id`, `order_id`, `show_id`, `placed_at` cho từng miền; phân tích truy vấn nhanh nhất và hotspot lớn nhất của từng lựa chọn.
3. **Định nghĩa grain:** một order, một order line/ticket, một reservation cho một ghế, một payment movement đã xác nhận; tránh JOIN hai fact khác grain.
4. **Unique/constraint:** làm sao bảo vệ một ghế không bán hai lần dù hai Booking ở hai shard khác nhau? Cần quy tắc atomic/lock tại đâu?
5. **Truy vấn đơn:** một khách chỉ có `order_id`, không biết thời gian đặt; thiết kế global lookup/directory để tránh tìm mọi partition. Nêu cách chống stale routing và yêu cầu unique ID.
6. **Phân vùng thời gian:** thiết kế bảng `orders` theo tháng và chỉ rõ tại sao PK phải chứa partition key trong PostgreSQL; nếu cần unique `tenant + order_id` toàn lịch sử, nêu chiến lược registry hoặc thay khóa phân vùng.
7. **JOIN:** giải thích khi nào Order–OrderLine colocated, còn Order–Product phải broadcast/shuffle hoặc dùng bản dữ liệu đã enrich.
8. **Tổng hợp:** viết công thức `gross_captured`, `refunded`, `net_cash` và phân biệt với `booked_sales`; không cộng tiền của các currency khác nhau.
9. **Truy vấn toàn cục:** giải thích chi phí fan-out, partial aggregate, COUNT DISTINCT và TOP-K; thiết kế tie-breaker cho phân trang.
10. **Đặt vé:** mô tả local transaction trong SeatInventory, idempotency của reservation, timeout và TTL; không để đặt chỗ không được xác nhận thành vé đã bán.
11. **Thanh toán:** nêu khi nào dùng Saga, bước release seat/hoàn tiền, trạng thái `PENDING_RECONCILIATION` và lý do không được coi timeout là thất bại.
12. **2PC:** trong một giao dịch giả định giữa hai DB hỗ trợ prepare, vẽ hai pha và mô tả coordinator chết sau prepare. Liệt kê giới hạn về isolation và external API.
13. **Đọc nhất quán:** chọn mức chấp nhận cho trang khách, dashboard vận hành và báo cáo tài chính chốt kỳ; định nghĩa mốc dữ liệu/watermark.
14. **Resharding:** chuyển một tenant lớn từ shard A sang B khi vẫn phát sinh đơn; thiết kế copy, CDC catch-up, fencing, cutover và đối soát.
15. **Chất lượng:** nêu ít nhất 8 metric để đo partition pruning, fan-out, network shuffle, P99, lock wait, saga lag, outbox lag và drift khi chuyển shard.
16. **ADR:** chọn phương án thử nghiệm với workload, SLO, kiểm thử lỗi, quyền riêng tư và kế hoạch rollback; nêu trường hợp khiến bạn thay quyết định.

### Tự kiểm chứng

| Tiêu chí | Thiết kế đạt khi |
| --- | --- |
| **Thuật ngữ** | Không nhầm partition trong một DB với shard có transaction độc lập. |
| **Khóa** | Partition key, PK/FK/unique và routing key phù hợp workload thực tế. |
| **Đường đọc** | Có query pruning/lookup và phân tích chi phí fan-out, JOIN, aggregate. |
| **Bất biến** | Seat không bán trùng; charge/refund không được khẳng định khi provider chưa xác nhận. |
| **Giao dịch** | Hiểu local transaction, 2PC atomic commit và Saga với trạng thái trung gian khác nhau. |
| **Đúng số liệu** | Không nhân tiền do JOIN, không gộp currency, có watermark/snapshot policy rõ. |
| **Failure handling** | Retry/idempotency, coordinator recovery, unknown outcome và compensation có thiết kế. |
| **Di chuyển** | Có owner/fencing và đối soát khi reshard, không vừa mất vừa nhân dữ liệu. |
| **Vận hành** | Đo P95/P99, skew, queue/lock, lag, network và kiểm thử các kịch bản lỗi. |
| **An toàn** | Tenant isolation, retention, replica/backup và lineage được kiểm soát. |

**Kết luận:** chọn phân vùng và phân tán không chỉ để chia dữ liệu cho nhiều máy. Thiết kế đúng phải giữ được **đường truy vấn hiệu quả** và **bất biến nghiệp vụ có phạm vi rõ**. Pruning, co-location và partial aggregation giảm chi phí đọc; owner/transaction cục bộ giảm nhu cầu phối hợp; 2PC đổi lấy atomic commit với chi phí khóa, log và recovery; Saga xử lý quy trình nhiều dịch vụ bằng trạng thái trung gian và bù trừ; outbox/idempotency bảo vệ việc truyền thông tin. Khi chọn khóa, grain, ràng buộc và cơ chế giao dịch từ yêu cầu thực tế rồi đo fan-out, tail latency và khả năng khôi phục, hệ thống mới mở rộng mà vẫn giải thích và kiểm chứng được dữ liệu.
