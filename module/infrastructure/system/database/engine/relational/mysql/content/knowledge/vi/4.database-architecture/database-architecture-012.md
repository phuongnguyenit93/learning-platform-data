# Cơ chế query cache của phiên bản cũ và giới hạn khi chuyển phiên bản

Bài học thuộc chương **Kiến trúc** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Query Cache là một cơ chế tối ưu truy vấn lịch sử của MySQL, có ý nghĩa khi đọc và bảo trì hệ thống cũ hoặc lập kế hoạch nâng cấp.

Sau bài này, bạn có thể giải thích Query Cache từng hoạt động ra sao, nhận diện workload phù hợp và các nguyên nhân làm cache mất hiệu quả, phân biệt Query Cache với những loại cache khác, đồng thời chuẩn bị ứng dụng và cấu hình khi chuyển từ MySQL 5.7 sang MySQL 8.0 trở lên.

## 1. Query Cache là gì?

**MySQL Query Cache** là bộ nhớ đệm kết quả truy vấn. Trong các phiên bản MySQL cũ có hỗ trợ, máy chủ lưu văn bản của câu lệnh SELECT cùng tập kết quả đã trả về. Khi nhận một câu SELECT giống hệt và đủ điều kiện cache, máy chủ có thể trả lại tập kết quả đã lưu mà không phải phân tích và thực thi lại truy vấn.

Query Cache được chia sẻ giữa các session. Ví dụ, session A thực thi một câu SELECT đủ điều kiện và tạo kết quả cache; session B có thể nhận chính kết quả đó khi gửi cùng câu truy vấn với cùng ngữ cảnh cache.

Mục tiêu của cơ chế này là giảm thời gian và công việc xử lý lặp lại trong những hệ thống có nhiều truy vấn đọc giống nhau trên dữ liệu ít thay đổi. Một ví dụ là danh sách loại sản phẩm hoặc danh mục cấu hình được nhiều request đọc liên tục.

Query Cache không phải là bộ nhớ đệm dữ liệu duy nhất trong MySQL. Cần phân biệt:

| Cơ chế | Lưu gì? | Tác dụng |
|---|---|---|
| Query Cache cũ | Văn bản SELECT và toàn bộ tập kết quả | Trả kết quả truy vấn đã có mà không thực thi lại SELECT |
| InnoDB Buffer Pool | Các trang dữ liệu và index của InnoDB | Giảm việc đọc dữ liệu và index từ thiết bị lưu trữ |
| Prepared Statement | Cấu trúc câu lệnh đã chuẩn bị để tái sử dụng | Giảm chi phí chuẩn bị/phân tích câu lệnh trong các lần thực thi |
| Cache tại ứng dụng hoặc proxy | Dữ liệu hoặc kết quả theo khóa do hệ thống xác định | Giảm số lần ứng dụng phải truy vấn database |

Khi Query Cache bị loại bỏ, InnoDB Buffer Pool vẫn tồn tại. MySQL vẫn có cơ chế cache trang dữ liệu và index; chỉ cơ chế lưu trọn kết quả SELECT ở cấp Query Cache của máy chủ bị loại bỏ.

## 2. Lịch sử phiên bản và mốc loại bỏ

Cần nắm đúng ranh giới phiên bản khi đọc cấu hình cũ:

| Phiên bản | Trạng thái Query Cache |
|---|---|
| MySQL 5.5 và các phiên bản cũ hơn có hỗ trợ | Có Query Cache |
| MySQL 5.6 | Có, nhưng mặc định đã tắt |
| MySQL 5.7 đến trước 5.7.20 | Có thể sử dụng; mặc định tắt |
| MySQL 5.7.20 trở đi | Query Cache bị đánh dấu deprecated; vẫn tồn tại trong nhánh 5.7 |
| MySQL 8.0 trở đi | Query Cache đã bị loại bỏ |

Từ MySQL 5.7.20, các thành phần liên quan Query Cache được đánh dấu deprecated. Nhánh MySQL 8.0 không còn hỗ trợ cơ chế này. Các phiên bản MySQL mới hơn tiếp tục không có Query Cache.

Điều đó có nghĩa là:

- Không thể bật Query Cache bằng cách tăng kích thước bộ nhớ trên MySQL 8.0 trở lên.
- Các biến như `query_cache_size`, `query_cache_type`, `query_cache_limit` và `query_cache_min_res_unit` không còn là cấu hình hợp lệ của Query Cache trong MySQL 8.0.
- Các bộ đếm trạng thái `Qcache_*` và câu lệnh quản trị `FLUSH QUERY CACHE`, `RESET QUERY CACHE` đã bị loại bỏ.
- Modifier `SQL_CACHE` không còn được hỗ trợ. Trong tài liệu MySQL 8.0, `SQL_NO_CACHE` được giữ ở trạng thái deprecated và không còn tác dụng; không nên dựa vào modifier này trong mã mới.

Vì vậy, khi đọc một file cấu hình MySQL cũ, cần xác định phiên bản đích trước khi sao chép các tham số Query Cache.

## 3. Query Cache hoạt động như thế nào trong MySQL 5.7?

Có thể hình dung vòng đời của một câu truy vấn như sau:

~~~mermaid
flowchart TD
    A[Client gửi SELECT] --> B{Query Cache có bật?}
    B -- Không --> C[Parse, optimize và execute]
    B -- Có --> D[So khớp query và ngữ cảnh]
    D --> E{Có entry hợp lệ?}
    E -- Có --> F[Kiểm tra quyền SELECT]
    F --> G[Trả kết quả đã cache]
    E -- Không --> C
    C --> H[Trả kết quả cho client]
    H --> I{Câu truy vấn đủ điều kiện cache?}
    I -- Có --> J[Lưu query và result]
    I -- Không --> K[Kết thúc]
    J --> K
~~~

Các bước chính:

1. Máy chủ nhận câu SELECT và kiểm tra Query Cache trước khi phân tích câu lệnh.
2. Nếu tìm thấy entry phù hợp, máy chủ kiểm tra quyền SELECT của tài khoản hiện tại trên các database và bảng liên quan.
3. Nếu quyền hợp lệ và entry còn hiệu lực, máy chủ gửi kết quả đã lưu về client.
4. Nếu không có entry phù hợp, câu lệnh đi qua quá trình phân tích, tối ưu và thực thi bình thường.
5. Với câu truy vấn đủ điều kiện, kết quả được lưu trong Query Cache khi gửi dữ liệu về client.
6. Khi một bảng liên quan bị thay đổi, các entry cache phụ thuộc vào bảng đó bị đánh dấu không hợp lệ và loại bỏ.

Query Cache không được thiết kế để trả dữ liệu cũ. Nó chủ động loại bỏ các kết quả có liên quan khi bảng thay đổi. Tuy nhiên, chính cách vô hiệu hóa theo bảng này có thể làm giảm đáng kể tỷ lệ cache hit trong hệ thống ghi nhiều.

### So khớp câu truy vấn chính xác

Query Cache cũ so sánh câu truy vấn trước khi parse. Hai câu sau được xem là khác nhau:

~~~sql
SELECT * FROM products;
select * from products;
~~~

Chỉ khác chữ hoa/thường cũng đã tạo ra hai văn bản truy vấn khác nhau. Khác khoảng trắng, comment hoặc cách định dạng cũng có thể tạo entry riêng.

Ngoài văn bản câu truy vấn, các ngữ cảnh khác nhau cũng có thể làm entry không dùng chung được, ví dụ:

- Database mặc định khác nhau.
- Phiên bản giao thức khác nhau.
- Bộ ký tự mặc định khác nhau.

Do đó, ứng dụng sinh SQL với nhiều cách định dạng không nhất quán có thể làm cache hit thấp dù về mặt logic các câu truy vấn tương đương.

Với prepared statement sử dụng binary protocol, MySQL 5.7 có quy tắc so khớp riêng: nội dung được xét sau khi mở rộng các dấu tham số, và chỉ so với các statement cache bằng binary protocol. Không nên giả định mọi prepared statement đều tự động dùng chung một entry với câu SQL gửi qua text protocol.

### Quyền truy cập vẫn được kiểm tra

Query Cache không bỏ qua kiểm soát quyền. Trước khi trả kết quả đã cache, MySQL kiểm tra user có quyền SELECT trên tất cả database và bảng liên quan hay không. Nếu không đủ quyền, kết quả cache không được sử dụng.

Điều này cho phép Query Cache dùng chung kết quả giữa nhiều session nhưng vẫn giữ quy tắc phân quyền của MySQL.

## 4. Điều kiện và giới hạn của truy vấn có thể cache

Không phải mọi SELECT đều được đưa vào Query Cache. Ngoài việc Query Cache phải được bật, câu truy vấn còn phải đáp ứng các điều kiện của phiên bản đang chạy.

Một số nhóm truy vấn không được cache trong MySQL 5.7:

- Truy vấn là subquery nằm trong một truy vấn bên ngoài.
- Truy vấn được thực thi bên trong stored function, trigger hoặc event.
- Truy vấn sử dụng temporary table.
- Truy vấn tham chiếu các bảng hệ thống như `mysql`, `INFORMATION_SCHEMA` hoặc `performance_schema`.
- Truy vấn sử dụng bảng partitioned.
- Truy vấn không đọc bảng nào.
- Truy vấn sử dụng user variable, local stored-program variable hoặc loadable/stored function.
- Truy vấn dùng các hàm phụ thuộc vào trạng thái hoặc thời gian, chẳng hạn `NOW()`, `RAND()`, `UUID()`, `CONNECTION_ID()`, `CURRENT_USER()`.
- Truy vấn yêu cầu khóa như `FOR UPDATE` hoặc `LOCK IN SHARE MODE`.
- Truy vấn dùng `SELECT ... INTO OUTFILE` hoặc `INTO DUMPFILE`.
- Truy vấn phát sinh warning hoặc liên quan đến quyền ở cấp cột trong các trường hợp bị giới hạn.

Đây là các ví dụ tiêu biểu, không phải danh sách thay thế cho tài liệu đúng phiên bản. Khi đánh giá một truy vấn cụ thể, hãy kiểm tra phần Query Cache trong Reference Manual của phiên bản MySQL 5.7 đang sử dụng.

Một lưu ý khác: Query Cache có thể hoạt động với bảng InnoDB và trong một số ngữ cảnh transaction, nhưng vẫn phải tuân theo các điều kiện cache và yêu cầu về tính nhất quán của transaction. Không nên suy luận rằng mọi SELECT InnoDB đều được cache.

## 5. Vô hiệu hóa cache và vấn đề đồng thời

Một hạn chế quan trọng của Query Cache là cơ chế vô hiệu hóa theo bảng.

Giả sử có ba câu SELECT cùng đọc bảng `products`:

~~~sql
SELECT id, name FROM products WHERE active = 1;
SELECT COUNT(*) FROM products WHERE active = 1;
SELECT category, COUNT(*) FROM products GROUP BY category;
~~~

Nếu cả ba câu được cache, một thao tác thay đổi bảng `products` như INSERT, UPDATE, DELETE, TRUNCATE, ALTER hoặc DROP có thể làm tất cả các entry phụ thuộc vào bảng này mất hiệu lực.

Điều này có thể xảy ra dù thao tác ghi chỉ thay đổi một hàng. Query Cache không giữ một bản đồ phụ thuộc đủ chi tiết để chỉ cập nhật một phần kết quả của từng câu SELECT.

### Tại sao write workload làm cache kém hiệu quả?

Ví dụ một hệ thống bán hàng có:

- 10.000 SELECT lặp lại mỗi giây.
- 2.000 câu SELECT khác nhau về văn bản hoặc tham số.
- Các thao tác INSERT và UPDATE liên tục trên bảng sản phẩm, tồn kho và đơn hàng.

Dù số lượng SELECT lớn, các thao tác ghi liên tục có thể làm nhiều entry bị xóa trước khi được tái sử dụng. Máy chủ phải tính lại kết quả và lưu lại, trong khi vẫn phải chịu chi phí kiểm tra và duy trì cache.

### Global mutex và lock contention

Query Cache cũ dùng cơ chế khóa đồng bộ chung để quản lý cấu trúc cache. Các session cần tra cứu, lưu kết quả hoặc vô hiệu hóa entry có thể phải chờ khóa.

Trong môi trường có nhiều CPU và nhiều kết nối đồng thời, khóa chung này có thể trở thành điểm nghẽn. Khi đó, thời gian chờ cache có thể lớn hơn phần thời gian tiết kiệm được nhờ cache hit.

Trong Process List của MySQL 5.7, trạng thái `Waiting for query cache lock` là một dấu hiệu cần kiểm tra. Các trạng thái khác như `checking query cache for query`, `invalidating query cache entries` hoặc `sending cached result to client` cũng giúp nhận diện hoạt động liên quan.

MySQL đã tắt Query Cache mặc định từ MySQL 5.6 vì các vấn đề mở rộng hiệu năng trong workload thông lượng cao. Nếu không có ý định dùng cache, đặt cả `query_cache_size=0` và `query_cache_type=0` ngay khi khởi động giúp máy chủ không phải lấy mutex Query Cache.

## 6. Các tham số Query Cache trong MySQL 5.7

Phần này chỉ áp dụng cho máy chủ MySQL 5.7 còn hỗ trợ Query Cache. Không chạy các câu lệnh này trên MySQL 8.0 trở lên.

| Tham số | Ý nghĩa |
|---|---|
| `query_cache_size` | Dung lượng bộ nhớ dành cho Query Cache; đặt 0 để vô hiệu hóa |
| `query_cache_type` | Chế độ bật/tắt hoặc chỉ cache truy vấn được chỉ định |
| `query_cache_limit` | Kích thước tối đa của kết quả đơn lẻ được phép cache |
| `query_cache_min_res_unit` | Kích thước block tối thiểu dùng để cấp phát bộ nhớ cho kết quả |
| `query_cache_wlock_invalidate` | Điều khiển việc vô hiệu hóa kết quả cache khi có write lock |

### query_cache_type

Ba giá trị chính:

| Giá trị | Hành vi |
|---|---|
| `OFF` hoặc `0` | Không lưu hoặc đọc kết quả từ Query Cache |
| `ON` hoặc `1` | Cache các truy vấn đủ điều kiện, trừ câu bắt đầu bằng `SELECT SQL_NO_CACHE` |
| `DEMAND` hoặc `2` | Chỉ cache truy vấn đủ điều kiện khi có modifier `SQL_CACHE` |

Trong MySQL 5.7, mặc định Query Cache đã tắt thông qua `query_cache_type=OFF`. Giá trị mặc định của `query_cache_size` là 1 MB nhưng điều đó không có nghĩa cache đang hoạt động.

### Cấu hình thử nghiệm trong MySQL 5.7

Ví dụ chỉ cache các truy vấn được đánh dấu rõ ràng:

~~~ini
[mysqld]
query_cache_type=DEMAND
query_cache_size=64M
query_cache_limit=1M
query_cache_min_res_unit=4096
~~~

Sau khi khởi động lại máy chủ, kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'query_cache%';
SHOW VARIABLES LIKE 'have_query_cache';
~~~

Với `DEMAND`, một câu SELECT phải có modifier `SQL_CACHE` mới được lưu nếu đủ điều kiện:

~~~sql
SELECT SQL_CACHE id, name
FROM products
WHERE active = 1;
~~~

Muốn bỏ qua Query Cache cho một câu lệnh trong MySQL 5.7:

~~~sql
SELECT SQL_NO_CACHE id, name
FROM products
WHERE active = 1;
~~~

Không dùng các ví dụ cấu hình này làm mẫu cho MySQL mới. Các tham số Query Cache đã bị loại bỏ từ MySQL 8.0.

## 7. Theo dõi hiệu quả Query Cache trong MySQL 5.7

Không nên chỉ bật Query Cache rồi kết luận hiệu năng tốt hơn. Cần đo tỷ lệ hit, lượng entry bị loại bỏ và thời gian chờ khóa trong cùng một khoảng workload.

Một số bộ đếm quan trọng:

| Bộ đếm | Ý nghĩa |
|---|---|
| `Qcache_hits` | Số lần truy vấn được trả từ cache |
| `Qcache_inserts` | Số kết quả được đưa vào cache |
| `Qcache_not_cached` | Số truy vấn không được cache |
| `Qcache_lowmem_prunes` | Số entry bị loại bỏ để giải phóng bộ nhớ |
| `Qcache_queries_in_cache` | Số truy vấn hiện còn trong cache |
| `Qcache_free_memory` | Bộ nhớ cache còn trống |
| `Qcache_free_blocks` | Số block trống; có thể giúp phát hiện phân mảnh |

Đọc các bộ đếm:

~~~sql
SHOW GLOBAL STATUS LIKE 'Qcache%';
SHOW GLOBAL STATUS LIKE 'Com_select';
~~~

Nên ghi lại giá trị trước và sau một khoảng thời gian đo, sau đó tính chênh lệch. Không nên chỉ nhìn số tích lũy từ lúc server khởi động.

Có thể dùng tỷ lệ hit gần đúng:

```
Hit ratio ≈ ΔQcache_hits / (ΔQcache_hits + ΔCom_select)
```

Đây là chỉ số tham khảo để so sánh trong cùng một cửa sổ đo; cần xem thêm truy vấn lỗi, workload và các bộ đếm khác để kết luận chính xác.

Một vài cách diễn giải:

- `Qcache_hits` tăng nhanh trong khi `Qcache_inserts` tăng vừa phải: có thể có nhiều truy vấn lặp lại được phục vụ từ cache.
- `Qcache_lowmem_prunes` tăng nhanh: cache đang phải loại bỏ entry để lấy chỗ cho kết quả mới; cần xem dung lượng và mức độ tái sử dụng.
- `Qcache_not_cached` tăng nhiều: có nhiều truy vấn không đủ điều kiện hoặc không được cấu hình để cache.
- `Qcache_free_blocks` cao có thể cho thấy bộ nhớ bị phân mảnh.
- Nhiều session ở trạng thái `Waiting for query cache lock`: có thể cache đang gây tranh chấp khóa.

Các lệnh bảo trì cũ:

~~~sql
-- Sắp xếp lại các block; không xóa toàn bộ kết quả
FLUSH QUERY CACHE;

-- Xóa tất cả kết quả đang được cache
RESET QUERY CACHE;
~~~

`FLUSH QUERY CACHE` và `RESET QUERY CACHE` không còn tồn tại trong MySQL 8.0 trở lên.

## 8. Vì sao MySQL loại bỏ Query Cache?

Query Cache có thể đem lại lợi ích rõ rệt trong workload đọc nhiều, ít thay đổi và có số lượng câu SELECT lặp lại rất cao. Nhưng nó cũng có những giới hạn khó giải quyết ở cấp độ máy chủ:

1. **Phụ thuộc vào văn bản SQL chính xác:** thay đổi khoảng trắng, chữ hoa/thường, comment hoặc ngữ cảnh có thể tạo cache key khác.
2. **Vô hiệu hóa theo bảng:** một thay đổi nhỏ có thể xóa nhiều kết quả cache liên quan đến cùng bảng.
3. **Khó mở rộng khi đồng thời cao:** nhiều session cùng truy cập cấu trúc cache chung có thể tranh chấp mutex.
4. **Lợi ích chỉ đến với cache hit:** các truy vấn không lặp lại, không đủ điều kiện hoặc bị invalidation liên tục vẫn phải thực thi bình thường.
5. **Không cải thiện mọi workload:** hệ thống ghi nhiều hoặc có nhiều câu SQL động có thể chịu thêm chi phí quản lý cache.
6. **Không thay thế tối ưu truy vấn:** một câu SQL thiếu index vẫn có thể rất chậm khi cache miss hoặc bị invalidation.

Oracle đã quyết định loại bỏ Query Cache trong MySQL 8.0 để tập trung cải thiện hiệu năng có lợi cho nhiều loại workload hơn. Hướng khuyến nghị khi nâng cấp là đưa cache tới gần client hơn, ví dụ cache trong ứng dụng hoặc sử dụng proxy có khả năng cache kết quả.

## 9. Những thay đổi cần xử lý khi nâng cấp MySQL 5.7 lên 8.0 trở lên

Khi nâng cấp một hệ thống có sử dụng Query Cache, cần rà soát cả cấu hình server và mã ứng dụng.

### Rà soát file cấu hình

Tìm các tham số cũ trong `my.cnf`, `my.ini`, file include và cấu hình triển khai:

~~~ini
query_cache_type=ON
query_cache_size=64M
query_cache_limit=1M
query_cache_min_res_unit=4096
query_cache_wlock_invalidate=OFF
~~~

Loại bỏ các tham số này khỏi cấu hình đích. MySQL 8.0 không nhận các biến Query Cache đã bị loại bỏ; giữ chúng trong file cấu hình có thể khiến server báo unknown variable và không khởi động được.

### Rà soát mã SQL và thư viện

Tìm các dấu hiệu:

- `SQL_CACHE` hoặc `SQL_NO_CACHE` trong câu SELECT.
- `FLUSH QUERY CACHE` hoặc `RESET QUERY CACHE`.
- Các lệnh đọc biến `query_cache_*`.
- Các báo cáo hoặc dashboard phụ thuộc vào bộ đếm `Qcache_*`.
- Script triển khai tự động thiết lập Query Cache.
- Logic ứng dụng giả định SELECT lặp lại sẽ được trả từ cache của server.

Xóa hoặc thay thế phần phụ thuộc. Không chỉ đổi cấu hình mà quên các script giám sát hoặc câu SQL quản trị được gọi trong quá trình deploy.

### Kiểm tra hành vi và hiệu năng sau nâng cấp

Sau khi loại bỏ cấu hình cũ:

1. Khởi động MySQL đích và kiểm tra error log.
2. Chạy các luồng đọc/ghi quan trọng của ứng dụng.
3. Đo độ trễ SELECT và tải CPU/I/O khi không có Query Cache.
4. Tìm các truy vấn tốn thời gian bằng slow query log hoặc Performance Schema.
5. Dùng EXPLAIN để kiểm tra kế hoạch thực thi; với MySQL 8.0.18 trở lên, có thể dùng EXPLAIN ANALYZE để so sánh ước lượng với thời gian và số hàng thực tế.
6. Chỉ bổ sung cache bên ngoài khi có bằng chứng về truy vấn lặp lại và yêu cầu độ mới dữ liệu rõ ràng.

Đừng dùng một lần chạy nóng cache ở MySQL 5.7 để so sánh với lần chạy lạnh ở MySQL 8.0. Hãy kiểm tra nhiều vòng, cùng bộ dữ liệu, cùng concurrency và cùng tỷ lệ đọc/ghi.

## 10. Các hướng thay thế Query Cache

Không có một tham số trong MySQL 8.0 thay thế trực tiếp cho Query Cache cũ. Hãy chọn cách phù hợp với tầng hệ thống và yêu cầu nhất quán.

### Cache tại ứng dụng

Mô hình cache-aside thường được dùng:

1. Ứng dụng kiểm tra cache theo một khóa xác định.
2. Nếu có dữ liệu còn hiệu lực, trả về từ cache.
3. Nếu không có, truy vấn MySQL, sau đó lưu kết quả vào cache.
4. Khi cập nhật dữ liệu, commit transaction thành công rồi cập nhật hoặc vô hiệu hóa các khóa cache liên quan.

Ví dụ giả mã:

~~~text
function getProductCatalog():
    value = cache.get("catalog:active:v1")

    if value exists:
        return value

    value = database.query(
        "SELECT id, name FROM products WHERE active = 1"
    )

    cache.set("catalog:active:v1", value, ttl = 60 seconds)
    return value
~~~

TTL giúp giới hạn thời gian một entry có thể tồn tại. Tuy nhiên, TTL không bảo đảm dữ liệu mới ngay sau khi transaction commit. Nếu nghiệp vụ yêu cầu đọc thấy ngay dữ liệu vừa ghi, cần invalidation/update có kiểm soát hoặc đọc trực tiếp từ database trên đường xử lý đó.

Khóa cache phải bao gồm mọi yếu tố làm thay đổi kết quả như tham số truy vấn, tenant, ngôn ngữ, quyền người dùng và phiên bản dữ liệu. Không dùng chung cache key giữa các người dùng nếu kết quả có thể khác nhau theo quyền hoặc dữ liệu riêng tư.

### Cache tại proxy

Một proxy như ProxySQL có thể lưu kết quả SELECT ở giữa ứng dụng và MySQL. Quy tắc cache có thể chọn nhóm truy vấn và đặt TTL.

Ưu điểm là có thể triển khai cache ở tầng trung gian mà không phải thay đổi mọi đoạn code ứng dụng. Tuy nhiên, phải hiểu chính sách invalidation của proxy. Ví dụ, Query Cache của ProxySQL sử dụng TTL; thao tác ghi ở MySQL không tự động xóa mọi entry tương ứng. Kết quả cũ có thể tiếp tục được trả cho tới khi TTL hết hoặc cache được xóa.

Vì vậy, chỉ cache qua proxy những truy vấn chấp nhận được độ trễ dữ liệu. Các luồng cần đọc sau ghi ngay lập tức nên bỏ qua cache hoặc có cơ chế đồng bộ invalidation phù hợp.

### Tối ưu truy vấn và dữ liệu

Trước khi thêm cache, hãy kiểm tra liệu truy vấn có thể được cải thiện ngay trong MySQL:

- Tạo index phù hợp với điều kiện lọc, join và sắp xếp.
- Chỉ chọn những cột thực sự cần dùng thay vì SELECT *.
- Kiểm tra số hàng được đọc và số hàng trả về.
- Dùng EXPLAIN hoặc EXPLAIN ANALYZE để tìm full table scan không cần thiết, join kém hiệu quả và ước lượng cardinality sai.
- Tối ưu cách phân trang và tránh truy vấn lặp lại không cần thiết.
- Với báo cáo nặng và dữ liệu ít thay đổi, cân nhắc bảng tổng hợp được cập nhật theo lịch hoặc theo sự kiện.

### Phân biệt các cơ chế thường bị nhầm

| Cơ chế | Có lưu kết quả SELECT không? | Vai trò sau khi Query Cache bị loại bỏ |
|---|---|---|
| InnoDB Buffer Pool | Không | Vẫn lưu trang dữ liệu/index trong RAM, giảm I/O |
| Prepared Statement | Không | Tái sử dụng cấu trúc câu lệnh, giảm chi phí chuẩn bị |
| Performance Schema | Không | Thu thập số liệu truy vấn, thời gian và digest để phân tích |
| Slow Query Log | Không | Ghi lại truy vấn chậm để tìm điểm cần tối ưu |
| Application Cache | Có | Có thể thay thế chức năng lưu kết quả theo logic nghiệp vụ |
| ProxySQL Query Cache | Có | Cache ở tầng proxy theo quy tắc và TTL |
| Query Rewrite Plugin | Không | Viết lại câu SQL theo quy tắc, không lưu kết quả truy vấn |

## 11. Bài thực hành: quan sát Query Cache trong MySQL 5.7

Bài thực hành này chỉ dành cho MySQL 5.7 còn Query Cache. Không chạy trên MySQL 8.0 trở lên.

### Chuẩn bị database thử nghiệm

Dùng tài khoản quản trị trên một instance lab riêng:

~~~sql
CREATE DATABASE IF NOT EXISTS query_cache_lab;
USE query_cache_lab;

CREATE TABLE products (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    active TINYINT NOT NULL
) ENGINE=InnoDB;

INSERT INTO products (id, name, category, active) VALUES
    (1, 'Keyboard', 'Accessories', 1),
    (2, 'Mouse', 'Accessories', 1),
    (3, 'Monitor', 'Display', 1),
    (4, 'Old Cable', 'Accessories', 0);
~~~

### Bật chế độ DEMAND

Thực hiện trên MySQL 5.7:

~~~sql
SET GLOBAL query_cache_size = 1048576;
SET GLOBAL query_cache_type = DEMAND;
SET SESSION query_cache_type = DEMAND;

SHOW VARIABLES LIKE 'query_cache%';
~~~

Nếu vừa thay đổi giá trị GLOBAL, các session khác đã mở không nhất thiết nhận giá trị SESSION mới. Trong bài thực hành, hãy đặt SESSION rõ ràng trên chính kết nối sẽ chạy câu SELECT.

### Chạy một truy vấn lặp lại

Chạy truy vấn sau hai lần, giữ nguyên văn bản câu lệnh:

~~~sql
SELECT SQL_CACHE category, COUNT(*) AS total
FROM products
WHERE active = 1
GROUP BY category;
~~~

Trước và sau hai lần chạy, kiểm tra bộ đếm:

~~~sql
SHOW GLOBAL STATUS LIKE 'Qcache_hits';
SHOW GLOBAL STATUS LIKE 'Qcache_inserts';
~~~

Lần đầu thường là cache miss và có thể tạo entry; lần tiếp theo có thể là cache hit nếu truy vấn đủ điều kiện và entry chưa bị invalidation hoặc loại bỏ.

Thử thay đổi chữ hoa/thường hoặc khoảng trắng trong câu SELECT rồi quan sát. Query Cache có thể tạo một entry khác vì văn bản không còn giống hệt.

### Quan sát invalidation

Thực hiện thay đổi dữ liệu:

~~~sql
UPDATE products
SET active = 0
WHERE id = 3;
~~~

Chạy lại đúng câu SELECT đã cache. Do bảng products đã thay đổi, entry cũ bị vô hiệu hóa; truy vấn phải được thực thi và có thể tạo entry mới. Chạy lần nữa để quan sát khả năng cache hit.

Thử truy vấn bỏ qua cache:

~~~sql
SELECT SQL_NO_CACHE category, COUNT(*) AS total
FROM products
WHERE active = 1
GROUP BY category;
~~~

### Dọn dẹp

Sau khi hoàn thành:

~~~sql
DROP DATABASE query_cache_lab;
~~~

Nếu cần trả lại cấu hình ban đầu của instance lab, đặt Query Cache về trạng thái tắt:

~~~sql
SET GLOBAL query_cache_type = OFF;
SET GLOBAL query_cache_size = 0;
~~~

Các biến này chỉ tồn tại ở phiên bản có Query Cache. Không đưa chúng vào script chạy chung cho MySQL 8.0 trở lên.

## 12. Checklist khi bảo trì hoặc nâng cấp hệ thống cũ

- [ ] Đã xác định chính xác phiên bản MySQL nguồn và đích.
- [ ] Đã kiểm tra Query Cache có thực sự được bật trong phiên bản nguồn hay không.
- [ ] Đã ghi nhận hit, insert, prune, not-cached và trạng thái chờ khóa trong workload đại diện.
- [ ] Đã tìm mọi tham số `query_cache_*` trong file cấu hình và script triển khai.
- [ ] Đã tìm `SQL_CACHE`, `SQL_NO_CACHE`, `FLUSH QUERY CACHE` và `RESET QUERY CACHE` trong mã ứng dụng.
- [ ] Đã cập nhật dashboard và cảnh báo đang đọc các bộ đếm `Qcache_*`.
- [ ] Đã chạy kiểm thử tích hợp trên MySQL đích sau khi bỏ cấu hình cũ.
- [ ] Đã đo hiệu năng trong điều kiện concurrency và tỷ lệ đọc/ghi giống thực tế.
- [ ] Đã chọn giải pháp thay thế nếu có truy vấn lặp lại cần cache.
- [ ] Đã định nghĩa TTL, invalidation và yêu cầu nhất quán cho cache mới.
- [ ] Đã xác nhận các luồng đọc sau ghi, quyền truy cập và dữ liệu theo tenant/người dùng không bị trả nhầm.

Query Cache là một phần của lịch sử tối ưu MySQL và vẫn cần hiểu khi làm việc với hệ thống 5.7 cũ. Khi chuyển sang MySQL 8.0 trở lên, hãy thay đổi cách tiếp cận: đo workload, tối ưu truy vấn và chọn cache ở tầng phù hợp với yêu cầu dữ liệu.

## Tài liệu tham khảo chính thức

Các hành vi lịch sử trong bài được đối chiếu với MySQL 5.7 Reference Manual; ranh giới loại bỏ được đối chiếu với tài liệu MySQL 8.0 và thông báo của nhóm MySQL. Tình trạng phiên bản được ghi nhận tại ngày **19-11-2026**.

1. [MySQL 5.7 Reference Manual — The MySQL Query Cache](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache.html): vai trò, hành vi tổng quát và mốc deprecated/removal.
2. [How the Query Cache Operates](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache-operation.html): so khớp văn bản, điều kiện cache, kiểm tra quyền và invalidation.
3. [Query Cache Configuration](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache-configuration.html): các biến cấu hình, chế độ ON/OFF/DEMAND, giới hạn và lock contention.
4. [Query Cache Status and Maintenance](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache-status-and-maintenance.html): các bộ đếm Qcache, FLUSH và RESET.
5. [MySQL 5.7 Release Notes — Changes in MySQL 5.7.20](https://dev.mysql.com/doc/relnotes/mysql/5.7/en/news-5-7-20.html): đánh dấu Query Cache deprecated.
6. [MySQL 8.0 Reference Manual — What Is New in MySQL 8.0](https://dev.mysql.com/doc/refman/8.0/en/mysql-nutshell.html): các thành phần Query Cache đã bị loại bỏ.
7. [MySQL 8.0: Retiring Support for the Query Cache](https://dev.mysql.com/blog-archive/mysql-8-0-retiring-support-for-the-query-cache/): lý do loại bỏ và hướng thay thế bằng cache ở phía client/proxy.
8. [InnoDB Buffer Pool](https://dev.mysql.com/doc/refman/8.0/en/innodb-buffer-pool.html): phân biệt cache trang dữ liệu/index với cache kết quả truy vấn.
9. [ProxySQL — Query Cache](https://proxysql.com/documentation/query-cache/): cache kết quả ở tầng proxy, cấu hình TTL và giới hạn invalidation.
10. [MySQL 8.0 — EXPLAIN Statement](https://dev.mysql.com/doc/refman/8.0/en/explain.html): đọc kế hoạch thực thi và sử dụng EXPLAIN ANALYZE.
11. [MySQL 8.0 — The Slow Query Log](https://dev.mysql.com/doc/refman/8.0/en/slow-query-log.html): tìm truy vấn tốn thời gian để tối ưu sau khi bỏ Query Cache.

