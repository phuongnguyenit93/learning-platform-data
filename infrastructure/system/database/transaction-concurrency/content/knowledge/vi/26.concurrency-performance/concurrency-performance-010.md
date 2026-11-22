# So sánh phương án bằng tải đại diện và cùng điều kiện đo

Khi chọn giữa hai cách triển khai database, chẳng hạn `SELECT ... FOR UPDATE` và cập nhật có điều kiện, batch nhỏ và batch lớn, hoặc hai phương án index, cảm nhận từ một lần chạy thử không đủ để kết luận phương án nào tốt hơn. Một so sánh có giá trị phải giữ nguyên workload, dữ liệu, môi trường và cách đo; chỉ thay đổi yếu tố đang được đánh giá. Đồng thời, hai phương án phải tạo ra kết quả nghiệp vụ tương đương. Nếu một phương án bỏ bớt kiểm tra hoặc giảm mức bảo đảm transaction, TPS cao hơn không có nghĩa nó tốt hơn.

Tải đại diện giúp kết quả phản ánh cách hệ thống được sử dụng thật. Điều kiện đo nhất quán giúp phân biệt tác động của thay đổi với nhiễu do cache, tải nền, cấu hình hoặc máy phát tải. Cuối cùng, cần đo cả throughput, latency, tỷ lệ thành công, retry và tính đúng đắn để chọn phương án đáp ứng mục tiêu vận hành.

## 1. Bắt đầu bằng câu hỏi so sánh cụ thể

Trước khi chạy benchmark, hãy viết rõ quyết định cần đưa ra và giả thuyết cho từng phương án. Tránh câu hỏi mơ hồ như “cách nào nhanh hơn?”. Một câu hỏi tốt xác định workload, điều kiện và chỉ số thành công.

Ví dụ:

> Với workload tạo đơn hàng gồm 70% đọc và 30% ghi, 100 client đồng thời, dữ liệu có phân phối sản phẩm nóng giống production, phương án cập nhật tồn kho bằng một câu `UPDATE ... WHERE available >= quantity` có đạt p99 thấp hơn phương án đọc khóa hàng rồi cập nhật hay không, trong khi giữ cùng invariant không bán vượt tồn?

Một giả thuyết nên bao gồm cả lợi ích và chi phí có thể phát sinh:

- Phương án A giảm round trip nhưng có thể tăng số hàng bị khóa trong một câu lệnh lớn.
- Phương án B dùng index mới có thể giảm số hàng quét nhưng làm tăng chi phí insert/update.
- Phương án C chia batch nhỏ có thể rút ngắn transaction nhưng tăng số lần commit.
- Phương án D dùng `SKIP LOCKED` có thể tăng khả năng phân phối job nhưng không đảm bảo FIFO tuyệt đối.

Hãy ghi trước chỉ số chính (primary metric), các chỉ số bảo vệ (guardrail metrics) và điều kiện chấp nhận. Điều này tránh việc sau khi có kết quả mới chọn metric có lợi cho phương án mình thích.

## 2. Bảo đảm hai phương án thực hiện cùng một công việc

So sánh hiệu năng chỉ công bằng khi các phương án có ngữ nghĩa nghiệp vụ tương đương. Nếu một phương án thực hiện ít công việc hơn, bỏ qua kiểm tra hoặc commit ở ranh giới khác, kết quả không thể so sánh trực tiếp.

Ví dụ với thao tác trừ tồn kho:

### Phương án A: khóa hàng rồi kiểm tra

```sql
BEGIN;

SELECT available_quantity
FROM inventory
WHERE product_id = :product_id
FOR UPDATE;

-- Ứng dụng xác nhận số lượng còn đủ.

UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id;

COMMIT;
```

### Phương án B: cập nhật nguyên tử có điều kiện

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
```

Phương án B có thể giảm round trip, nhưng chỉ tương đương nếu ứng dụng xử lý đúng số hàng bị ảnh hưởng, ghi audit hoặc reservation cần thiết và giữ cùng quy tắc nghiệp vụ. Nếu A kiểm tra thêm trạng thái sản phẩm hoặc quyền mua còn B không kiểm tra, benchmark đang so sánh hai chức năng khác nhau.

Trước khi đo, hãy xác định:

- Cùng điều kiện đầu vào và cùng kết quả đầu ra.
- Cùng invariant phải bảo vệ.
- Cùng mức isolation và durability cần thiết.
- Cùng ranh giới transaction và các thay đổi phụ thuộc.
- Cùng chính sách retry, timeout và idempotency.
- Cùng cách xử lý lỗi nghiệp vụ và lỗi cạnh tranh.

Nếu một phương án cố ý thay đổi semantics, hãy coi đó là một lựa chọn kiến trúc khác. Báo cáo rõ sự khác biệt và đánh giá rủi ro nghiệp vụ riêng, không chỉ đặt hai con số TPS cạnh nhau.

## 3. Xây dựng tải đại diện

Workload đại diện (representative workload) mô tả cách hệ thống thật đọc, ghi và tranh chấp tài nguyên. Chỉ dùng một câu `UPDATE` lặp trên một hàng có thể hữu ích để đo giới hạn hot-row, nhưng không đại diện cho một dịch vụ có nhiều loại transaction.

Hãy thu thập hoặc ước lượng các đặc điểm sau từ hệ thống mục tiêu:

- Tỷ lệ transaction đọc, ghi và đọc-ghi hỗn hợp.
- Tỷ lệ từng loại thao tác nghiệp vụ.
- Số câu SQL và số hàng đọc/ghi trong mỗi transaction.
- Kích thước dữ liệu, số hàng mỗi bảng và số index.
- Phân phối khóa được truy cập: đồng đều, lệch (skewed) hay có hot key.
- Mức độ trùng lặp giữa các transaction đồng thời.
- Kích thước batch, payload và số quan hệ FK/trigger liên quan.
- Isolation level, thời gian transaction và tần suất retry thực tế.
- Tỷ lệ lỗi nghiệp vụ dự kiến, ví dụ hết hàng hoặc trạng thái không hợp lệ.

Ví dụ một workload hỗn hợp:

| Loại transaction | Tỷ trọng | Đặc điểm cạnh tranh |
|---|---:|---|
| Xem sản phẩm | 35% | Chủ yếu đọc, có thể cùng đọc sản phẩm phổ biến. |
| Đọc đơn hàng | 20% | Đọc một đơn và các dòng chi tiết. |
| Tạo đơn | 20% | Ghi đơn, dòng đơn và reservation; có thể tranh chấp tồn kho. |
| Trừ/hoàn tồn | 15% | Cập nhật hàng inventory, có hot key. |
| Hủy đơn | 10% | Cập nhật nhiều hàng liên quan và ghi audit. |

Các tỷ trọng chỉ là ví dụ. Hãy dùng số liệu production đã được tổng hợp và loại bỏ thông tin nhạy cảm nếu có. Nếu chưa có telemetry, hãy phỏng vấn chủ hệ thống, đọc luồng nghiệp vụ và ghi rõ các giả định của benchmark.

### 3.1. Mô phỏng phân phối dữ liệu

Phân phối khóa ảnh hưởng rất lớn đến contention. Với phân phối đồng đều, mỗi worker thường truy cập các hàng khác nhau. Với phân phối lệch, một số sản phẩm, tài khoản hoặc tenant được truy cập thường xuyên hơn nhiều.

Ví dụ:

```text
Phân phối đồng đều:
P1  P2  P3  P4  P5  P6  P7  P8
 |   |   |   |   |   |   |   |
W1  W2  W3  W4  W5  W6  W7  W8

Phân phối có hot key:
P1 (hot)  P2  P3  P4  P5
  ^^^^
  W1 W2 W3 W4 W5 W6 cùng truy cập P1 thường xuyên
```

Nếu production có một nhóm tài nguyên nóng, benchmark cần tái hiện tỷ lệ đó. Ngược lại, nếu muốn cô lập hiệu năng khi không có contention, có thể thêm một kịch bản phân phối đều và công bố đây là kịch bản riêng.

### 3.2. Quy mô dữ liệu phải đủ đại diện

Dataset quá nhỏ có thể nằm hoàn toàn trong cache và không thể hiện chi phí I/O hoặc index ở quy mô thật. Dataset quá lớn nhưng không được nạp đủ có thể làm benchmark đo chi phí khởi tạo thay vì steady-state. Ghi lại:

- Số hàng từng bảng chính.
- Kích thước bảng và index.
- Tỷ lệ dữ liệu nằm trong buffer/cache nếu có thể quan sát.
- Phân phối số hàng mỗi tenant hoặc mỗi nhóm nghiệp vụ.
- Tốc độ tăng dữ liệu trong lúc chạy.

Hai phương án phải bắt đầu từ cùng trạng thái dữ liệu logic. Nếu workload thay đổi dữ liệu, hãy reset về cùng seed hoặc dùng snapshot/clone độc lập trước mỗi lượt đo.

## 4. Kiểm soát các điều kiện đo

Khi so sánh A và B, các yếu tố không thuộc biến đang thử nghiệm phải được giữ giống nhau hoặc được ghi lại rõ ràng.

| Nhóm | Điều kiện cần cố định hoặc ghi nhận |
|---|---|
| Database | DBMS và phiên bản, extension, schema, constraint, trigger, index không thuộc thử nghiệm. |
| Transaction | Isolation level, autocommit, ranh giới commit, durability và retry policy. |
| Server | CPU, RAM, storage, filesystem, network, cấu hình DB và giới hạn tài nguyên. |
| Client | JVM/runtime, driver, connection pool, số worker, timeout và máy phát tải. |
| Dữ liệu | Cùng seed, kích thước, phân phối khóa, trạng thái ban đầu và độ nóng cache. |
| Workload | Cùng tỷ lệ thao tác, payload, tốc độ đến, thời gian chạy và thứ tự pha. |
| Đo lường | Cùng ranh giới latency, histogram, cách đếm success, retry, dropped request. |
| Nền hệ thống | Backup, vacuum/purge, checkpoint, replication, batch khác và tải người dùng nền. |

Không nhất thiết phải tắt mọi hoạt động nền. Nếu production luôn có autovacuum, replication hoặc batch định kỳ, benchmark vận hành nên phản ánh điều đó. Điều quan trọng là hai phương án phải chịu điều kiện tương đương và báo cáo nói rõ hoạt động nền nào có mặt.

### 4.1. Không thay nhiều yếu tố cùng lúc

Nếu A dùng index mới, batch size nhỏ hơn và isolation level khác B, bạn không thể biết thay đổi nào tạo ra kết quả. Hãy thay một yếu tố mỗi lần hoặc dùng thiết kế thí nghiệm có ma trận nhân tố được định nghĩa trước.

Ví dụ so sánh index:

- A: index hiện tại.
- B: thêm đúng một index ứng viên.
- Giữ nguyên query, dữ liệu, workload, cấu hình và concurrency.
- Đo cả truy vấn đọc lẫn chi phí ghi do index bổ sung.

Nếu muốn thử tương tác giữa index và batch size, hãy chạy đủ các tổ hợp trong một ma trận, không suy ra từ hai lần chạy chỉ thay cả hai cùng lúc.

## 5. Cùng một load model và offered load

Hai phương án phải nhận cùng mô hình tải. Closed-loop và open-loop có thể tạo kết quả khác nhau, vì vậy không so sánh một phương án chạy 100 worker chờ phản hồi với phương án khác nhận 500 request/giây cố định mà không điều chỉnh ranh giới.

### Closed-loop

Mỗi worker gửi một transaction rồi đợi kết quả trước khi gửi transaction tiếp theo. Mô hình này phù hợp khi số người dùng đồng thời hoặc số worker ứng dụng là điều kiện cần tái hiện.

Khi hệ thống chậm, tốc độ gửi tự giảm. Vì thế, closed-loop có thể che bớt hàng đợi và không phản ánh đầy đủ một luồng request đến liên tục.

### Open-loop

Load generator phát yêu cầu theo tốc độ mục tiêu độc lập với thời gian phản hồi. Mô hình này giúp đo khả năng đáp ứng offered load, backlog, timeout và dropped request.

Khi dùng open-loop, phải ghi số request được lên lịch, thực sự gửi, hoàn tất, thất bại, bị drop và còn in-flight. Nếu generator không đủ tài nguyên để phát tải mục tiêu, phép đo không hợp lệ.

### Tránh coordinated omission

Trong closed-loop, worker chậm sẽ gửi ít request mới hơn, khiến các khoảng thời gian server bị chậm có ít mẫu latency. Đây là coordinated omission. Với open-loop, ghi thời điểm request dự kiến được gửi và thời điểm thực sự gửi để có thể nhận diện độ trễ bị che khuất. Nếu công cụ có cơ chế hiệu chỉnh coordinated omission, hãy ghi rõ cách cấu hình.

## 6. Cố định concurrency và connection pool

Khi mục tiêu là so sánh hai cách triển khai ở cùng tải, giữ cùng số worker, số connection tối đa và chính sách pool. Nếu một phương án dùng pool 20 connection còn phương án kia dùng 100, kết quả đồng thời phản ánh cấu hình pool chứ không chỉ code database.

Nên chạy nhiều mức concurrency thay vì chỉ một điểm:

| Mức | Ví dụ số worker | Mục tiêu |
|---|---:|---|
| Thấp | 5–10 | Quan sát overhead cơ bản khi ít contention. |
| Trung bình | 25–50 | Đại diện tải thường ngày. |
| Cao | 100–150 | Tìm điểm throughput bắt đầu bão hòa. |
| Đỉnh | 200 trở lên | Quan sát hành vi khi gần hoặc vượt capacity, nếu đây là tình huống cần kiểm tra. |

Các mức chỉ mang tính minh họa; hãy chọn theo số client và tải mục tiêu. Ở mỗi mức, chạy A và B với cùng cấu hình worker/pool. Nếu cần đánh giá khả năng scale, biểu diễn kết quả theo cả concurrency và offered load.

## 7. Chuẩn bị trạng thái trước mỗi lượt chạy

Benchmark có thể bị sai lệch nếu phương án đầu chạy trên cache lạnh còn phương án sau chạy trên cache ấm, hoặc nếu lượt trước đã làm thay đổi phân phối dữ liệu.

Một quy trình chuẩn bị:

1. Tạo database clone hoặc snapshot từ cùng trạng thái dữ liệu gốc.
2. Áp dụng đúng schema và index của biến thể đang thử.
3. Xác nhận số hàng, constraint và thống kê dữ liệu.
4. Khởi tạo cache theo kịch bản đã chọn: warm-cache hoặc cold-cache.
5. Chạy warm-up workload giống nhau.
6. Xác nhận hệ thống đã đạt trạng thái ổn định trước khi bắt đầu cửa sổ đo.
7. Sau lượt chạy, lưu kết quả và reset về snapshot/seed trước khi thử biến thể kế tiếp.

Không cố xóa cache bằng một cách không được hỗ trợ trên production. Nếu cần đo cold-cache, thực hiện trên môi trường thử nghiệm có quy trình kiểm soát. Nếu mục tiêu là steady-state production, warm-cache thường gần thực tế hơn; hãy công bố rõ.

## 8. Warm-up, ramp-up và thời gian đo

Một lần chạy nên có các pha tách biệt:

```text
Khởi tạo
   |
   v
Warm-up: nạp code, connection, prepared statement và cache
   |
   v
Ramp-up: tăng dần concurrency/offered load
   |
   v
Steady-state: giữ tải và thu số liệu chính
   |
   v
Cool-down: ngừng phát tải, chờ in-flight kết thúc
   |
   v
Kiểm tra dữ liệu, lỗi, backlog và tài nguyên
```

Không tính warm-up vào số liệu steady-state nếu mục tiêu là hiệu năng ổn định. Ramp-up giúp tránh một đợt tăng tải đột ngột không đại diện. Thời gian steady-state cần đủ dài để có nhiều mẫu và bao phủ các chu kỳ hoạt động liên quan như checkpoint, vacuum/purge hoặc log flush.

Hai phương án phải dùng cùng thời lượng hoặc cùng tiêu chí kết thúc. Nếu A chạy 30 giây và B chạy 10 phút, không thể so sánh trực tiếp p99 và throughput mà không xét số mẫu và trạng thái ổn định.

## 9. Thứ tự chạy và số lần lặp

Chạy A trước rồi B sau trong mọi lần có thể tạo thiên lệch do nhiệt độ CPU, cache, tải nền hoặc thay đổi trạng thái hệ thống theo thời gian. Có thể luân phiên hoặc ngẫu nhiên thứ tự chạy:

```text
Lần 1: A -> B
Lần 2: B -> A
Lần 3: B -> A
Lần 4: A -> B
Lần 5: A -> B
Lần 6: B -> A
```

Mỗi lượt phải bắt đầu từ trạng thái dữ liệu tương đương. Nếu thứ tự chạy làm thay đổi cache, hãy áp dụng cùng warm-up hoặc reset cache theo kịch bản định trước.

Lặp lại đủ số lần để quan sát biến động giữa các lượt. Ba lần có thể hữu ích cho một kiểm tra ban đầu, nhưng benchmark quyết định kiến trúc thường cần nhiều lần hơn và khoảng đo đủ dài. Không chọn riêng lần tốt nhất; báo cáo median, khoảng biến động hoặc phân phối kết quả giữa các lần chạy.

## 10. Đo cùng bộ chỉ số

Một bảng so sánh nên có ít nhất các chỉ số sau:

| Chỉ số | Cách hiểu | Vì sao cần |
|---|---|---|
| Successful TPS | Transaction logic hoặc attempt commit thành công mỗi giây, định nghĩa rõ. | Đo năng lực hoàn tất. |
| Offered load | Số yêu cầu được lên lịch/gửi mỗi giây. | Biết hệ thống đã nhận tải mục tiêu hay chưa. |
| p50/p95/p99 latency | Phân phối thời gian hoàn tất. | Thấy trải nghiệm điển hình và đuôi chậm. |
| Success rate | Tỷ lệ yêu cầu logic hoàn tất đúng. | Bảo vệ chất lượng kết quả. |
| Retry rate | Tỷ lệ request/attempt phải chạy lại. | Phản ánh chi phí contention và lỗi tạm thời. |
| Deadlock/serialization count | Số lỗi concurrency theo loại. | Giúp hiểu vì sao retry và throughput thay đổi. |
| Lock wait | Thời gian/số lần chờ khóa. | Xác định contention. |
| Pool wait | Thời gian chờ connection. | Phân biệt nghẽn pool với nghẽn DB. |
| CPU, I/O, log flush | Tài nguyên tiêu thụ. | Phát hiện bottleneck và chi phí phụ. |
| Backlog/in-flight | Công việc đang chờ hoặc đang chạy. | Nhận diện hệ thống chưa ổn định. |

Không chỉ báo cáo latency của các request thành công nếu các request timeout hoặc bị drop không được tính ở nơi khác. Phải nêu rõ mẫu số của success rate và cách xử lý request chưa hoàn tất khi cửa sổ đo kết thúc.

## 11. Định nghĩa latency và cách tính percentile nhất quán

Chọn cùng mốc bắt đầu/kết thúc cho mọi biến thể. Với transaction qua pool, nên đo riêng:

- End-to-end request latency.
- Pool acquisition latency.
- Transaction attempt latency từ lúc bắt đầu transaction đến khi commit/rollback được xác nhận.
- Commit latency.
- Backoff/retry time.

Dùng đồng hồ đơn điệu như `System.nanoTime()` để đo duration trong JVM. Không dùng timestamp tường có thể bị điều chỉnh để trừ trực tiếp tính thời gian.

Lưu histogram hoặc mẫu độ trễ đủ chi tiết để tính p50, p95 và p99. Không lấy trung bình các p99 theo từng phút để tạo p99 toàn giờ. Nếu cần gộp nhiều instance, dùng histogram có thể tổng hợp hoặc hệ thống lưu trữ percentile hỗ trợ merge đúng cách.

Khi so sánh hai phương án, percentile phải được tính trên cùng tập loại transaction và cùng quy tắc lọc. Nếu A có nhiều request thất bại bị loại khỏi histogram còn B ghi mọi request, kết quả không công bằng.

## 12. Phân loại success, failure và retry

Một transaction attempt có thể kết thúc bằng commit, rollback, deadlock, serialization failure, timeout, cancellation hoặc lỗi nghiệp vụ. Hãy giữ các nhóm riêng:

| Kết quả | Phân loại gợi ý |
|---|---|
| Commit và invariant được giữ | Thành công kỹ thuật và nghiệp vụ. |
| Từ chối hợp lệ, ví dụ hết hàng | Kết quả nghiệp vụ dự kiến; không tính là lỗi hạ tầng. |
| Deadlock hoặc serialization failure rồi retry thành công | Request logic thành công, nhưng có retry cost. |
| Hết retry và request thất bại | Final failure. |
| Lock timeout hoặc NOWAIT | Busy/temporary conflict theo policy; báo riêng. |
| Connection loss trong lúc commit | Outcome unknown cho đến khi đối soát. |
| Lỗi constraint do dữ liệu không hợp lệ | Data/business error, không retry mù. |

Đo cả tỷ lệ thành công theo logical request và attempt success rate. Một phương án có 99,9% request cuối cùng thành công nhưng trung bình 1,8 attempt/request vẫn có thể tiêu tốn tài nguyên gấp nhiều lần và giảm capacity cho workload khác.

## 13. Kiểm tra tính đúng đắn sau mỗi lượt

Benchmark hiệu năng không được bỏ qua tính đúng đắn. Sau khi tải dừng, xác minh dữ liệu cuối và invariant của nghiệp vụ.

Ví dụ với tồn kho:

```sql
-- Không sản phẩm nào có tồn kho âm.
SELECT product_id, available_quantity
FROM inventory
WHERE available_quantity < 0;

-- Mỗi yêu cầu đã hoàn tất phải có reservation tương ứng.
SELECT o.order_id
FROM orders o
LEFT JOIN reservation r ON r.order_id = o.order_id
WHERE o.status = 'CONFIRMED'
  AND r.order_id IS NULL;
```

Truy vấn cụ thể cần phù hợp schema. Ngoài invariant, so sánh:

- Số yêu cầu được tạo, hoàn tất, hủy và còn chờ.
- Tổng số hàng được thêm/cập nhật/xóa.
- Tổng tiền, số lượng hoặc bộ đếm đối chiếu.
- Số event/outbox và tác dụng phụ được phát.
- Không có bản ghi trùng do retry.
- Không có transaction hoặc job bị kẹt ngoài dự kiến.

Nếu một phương án nhanh hơn vì bỏ sót một phần công việc hoặc làm sai dữ liệu, phương án đó không đạt yêu cầu. Chỉ số đúng đắn là guardrail bắt buộc, không phải metric phụ có thể bỏ qua.

## 14. Đo chi phí tổng thể, không chỉ thời gian câu SQL

Một thay đổi có thể giảm latency một truy vấn nhưng làm tăng chi phí ghi hoặc vận hành:

- Thêm index giảm read latency nhưng làm insert/update/delete tốn hơn và tăng dung lượng lưu trữ.
- Batch lớn giảm số lần commit nhưng tăng transaction age, log volume và rollback cost.
- Batch nhỏ giảm lock duration nhưng tăng commit overhead và số lần round trip.
- Khóa tường minh làm rõ thứ tự nhưng có thể làm nhiều request chờ.
- Cập nhật nguyên tử giảm round trip nhưng có thể tăng contention trên một hàng nóng.
- Cache giảm đọc database nhưng cần invalidation và có thể thay đổi freshness semantics.

Vì vậy, hãy đo toàn bộ workload mix. Nếu một index làm truy vấn đọc nhanh hơn 20% nhưng làm transaction ghi chậm hơn 30%, kết quả tổng thể phụ thuộc tỷ trọng đọc/ghi. Benchmark chỉ đọc không đủ để quyết định index cho hệ thống có nhiều ghi.

## 15. Phân tích kết quả bằng ví dụ

Giả sử hai phương án được chạy với cùng workload và cùng điều kiện:

| Chỉ số | Phương án A | Phương án B |
|---|---:|---:|
| Successful TPS | 720 | 760 |
| p50 transaction latency | 18 ms | 17 ms |
| p95 transaction latency | 85 ms | 105 ms |
| p99 transaction latency | 310 ms | 620 ms |
| Logical success rate | 99,95% | 99,70% |
| Retry rate | 0,8% | 3,9% |
| Deadlock/serialization errors | 35 | 170 |
| CPU utilization | 68% | 82% |

Các số liệu chỉ minh họa. B có TPS cao hơn khoảng 5,6%, nhưng p99 gấp đôi, success rate thấp hơn, retry và lỗi concurrency cao hơn. Nếu SLO yêu cầu p99 dưới 400 ms và success rate ít nhất 99,9%, A đáp ứng còn B không đáp ứng. Chọn B chỉ vì TPS cao hơn sẽ bỏ qua chất lượng dịch vụ.

Một trường hợp khác: B có TPS thấp hơn nhưng p99 tốt hơn và CPU thấp hơn đáng kể. Nếu mục tiêu là giảm chi phí hạ tầng trong khi vẫn đáp ứng SLA, B có thể là lựa chọn tốt hơn. Kết luận phụ thuộc mục tiêu đã công bố trước khi thử nghiệm.

## 16. Đánh giá mức cải thiện và độ biến động

Với một metric như throughput, phần trăm thay đổi có thể tính:

\[
Improvement(\%) = \frac{B - A}{A} \times 100\%
\]

Nếu A đạt 720 TPS và B đạt 760 TPS:

\[
\frac{760 - 720}{720} \times 100\% \approx 5,56\%
\]

Với latency, giá trị thấp hơn thường tốt hơn; có thể báo phần trăm giảm:

\[
Latency\ Reduction(\%) = \frac{A - B}{A} \times 100\%
\]

Không chỉ báo một con số phần trăm. Hãy lưu kết quả từng lần chạy, median và khoảng biến động. Nếu A dao động 700–770 TPS còn B dao động 710–780 TPS, chênh lệch median nhỏ có thể nằm trong nhiễu đo. Cần thêm lần chạy hoặc kiểm soát môi trường tốt hơn trước khi kết luận.

Với nhiều lần chạy độc lập, có thể dùng bootstrap để ước lượng khoảng tin cậy cho median hoặc percentile. Với throughput theo các cửa sổ thời gian, cần chú ý tính tự tương quan giữa các mẫu; không coi mọi giây liên tiếp là mẫu độc lập. Nếu dùng kiểm định thống kê, chọn phương pháp phù hợp với phân phối và thiết kế thí nghiệm, đồng thời báo kích thước mẫu và khoảng tin cậy.

## 17. Chọn thiết kế thí nghiệm: một biến hay ma trận nhiều biến

### Thử một biến tại một thời điểm

Phù hợp khi cần hiểu tác động trực tiếp của một thay đổi:

| Lượt | Lock strategy | Batch size | Index |
|---|---|---:|---|
| Baseline | A | 100 | I1 |
| Variant | B | 100 | I1 |

Chỉ thay lock strategy; các yếu tố khác giữ nguyên.

### Thử nhiều yếu tố bằng ma trận

Khi muốn hiểu tương tác giữa nhiều yếu tố, định nghĩa ma trận trước:

| Biến thể | Lock strategy | Batch size | Index |
|---|---|---:|---|
| V1 | A | 50 | I1 |
| V2 | A | 200 | I1 |
| V3 | B | 50 | I1 |
| V4 | B | 200 | I1 |
| V5 | A | 50 | I2 |
| V6 | B | 50 | I2 |

Ma trận lớn cần nhiều thời gian và lượt chạy. Có thể dùng fractional factorial hoặc thiết kế thí nghiệm khác nếu có người hiểu phương pháp thống kê, nhưng phải ghi rõ yếu tố nào được thay đổi và tương tác nào có thể bị bỏ sót.

## 18. Tìm bottleneck và giải thích nguyên nhân

Kết quả benchmark cho biết điều gì xảy ra; metric hệ thống giúp giải thích vì sao. Đối chiếu timeline của:

- CPU, runnable queue và memory pressure.
- Storage latency, IOPS, log flush và checkpoint.
- Lock wait, deadlock, serialization failure và blocker.
- Active connection, pool wait và số request in-flight.
- Query plan, rows scanned, rows returned và index usage.
- WAL/redo/undo, vacuum/purge và replication lag.
- JVM GC, thread pool và CPU/network của load generator.

Ví dụ:

- TPS chững, CPU thấp, lock wait cao: có thể đang bị contention trên hàng hoặc tài nguyên nóng.
- TPS chững, CPU gần 100%, lock wait thấp: có thể CPU hoặc query plan là bottleneck.
- Latency tăng nhưng DB CPU thấp, pool wait cao: có thể connection pool thiếu hoặc connection bị giữ lâu.
- Commit latency tăng cùng log flush/storage latency: có thể bottleneck ở durability/log I/O.
- Load generator CPU cao và offered load thực tế thấp hơn mục tiêu: phép đo chưa tạo đủ tải để đánh giá database.

Không suy luận nguyên nhân chỉ từ một biểu đồ. Dùng query plan, wait events, lock graph và trace ứng dụng để xác nhận.

## 19. So sánh qua nhiều DBMS hoặc nhiều môi trường

Nếu so sánh PostgreSQL, MySQL InnoDB, SQL Server hoặc Oracle, giữ nguyên semantics và workload nhưng cần ghi rõ khác biệt cấu hình:

- Phiên bản DBMS và driver.
- Isolation level và hành vi mặc định.
- Durability, synchronous commit/redo và replication.
- Kiểu dữ liệu, index, constraint, trigger và execution plan.
- Connection pool và cách quản lý transaction.
- Cấu hình memory, parallelism, checkpoint và storage.

Không nên ép mọi DBMS dùng một cú pháp khóa rồi cho rằng lock footprint giống nhau. Hãy triển khai phương án tương đương về ngữ nghĩa trên từng engine, xác nhận correctness trước, sau đó đo. Nếu một engine dùng row lock còn engine khác dùng key-range lock cho cùng truy vấn, đó là một phần khác biệt cần ghi trong báo cáo.

Nếu môi trường phần cứng không giống nhau, kết quả không phải phép so sánh trực tiếp hiệu năng engine. Có thể chuẩn hóa theo chi phí hoặc tài nguyên, nhưng phải nêu phương pháp và giới hạn. Tốt nhất dùng cùng cấu hình phần cứng hoặc các máy tương đương đã được xác minh.

## 20. Mẫu kế hoạch benchmark

Trước khi chạy, lưu một bản kế hoạch ngắn:

```text
Mục tiêu:
  So sánh phương án A và B cho thao tác reserve inventory.

Giả thuyết:
  B giảm round trip nhưng có thể tăng contention trên hot product.

Correctness contract:
  Không tồn kho âm; mỗi order chỉ có một reservation đang hiệu lực.

Workload:
  35% đọc sản phẩm, 20% đọc đơn, 20% tạo đơn,
  15% reserve/release inventory, 10% hủy đơn.

Data:
  10 triệu inventory/order rows; phân phối hot-key theo production.

Environment:
  DB version, CPU/RAM/storage, schema, index, driver, JVM,
  pool size, isolation level và durability được ghi rõ.

Load:
  Closed-loop 25/50/100 workers và open-loop 300/500 req/s.

Measurement:
  Warm-up 5 phút, ramp-up 2 phút, steady-state 10 phút,
  cool-down và correctness checks.

Primary metric:
  Successful logical transactions per second.

Guardrails:
  p95/p99, success rate, retry/deadlock, invariant,
  CPU, lock wait và pool wait.

Repetitions:
  6 lượt độc lập, luân phiên thứ tự A/B, cùng seed dữ liệu.

Decision rule:
  Chỉ chấp nhận phương án đáp ứng correctness và SLO;
  trong các phương án đạt chuẩn, chọn phương án có trade-off tốt nhất.
```

Các con số là ví dụ để minh họa cách viết kế hoạch, không phải cấu hình chuẩn cho mọi hệ thống.

## 21. Mẫu bảng kết quả

Ghi từng lần chạy thay vì chỉ lưu kết quả tổng hợp:

| Run | Variant | Workers | Offered req/s | Successful TPS | p50 | p95 | p99 | Success | Retry | CPU |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | A | 100 | 500 | 720 | 18 ms | 85 ms | 310 ms | 99,95% | 0,8% | 68% |
| 2 | B | 100 | 500 | 760 | 17 ms | 105 ms | 620 ms | 99,70% | 3,9% | 82% |

Trong báo cáo thực tế, mỗi lượt cần thêm timestamp, build/commit ID, database version, seed ID, thời lượng đo và ghi chú về sự kiện nền. Bảng rút gọn ở đây chỉ minh họa các cột chính.

## 22. Những sai lầm làm kết quả không công bằng

1. **Workload khác nhau:** A nhận ít ghi hoặc ít hot key hơn B.
2. **Semantics khác nhau:** một phương án bỏ constraint, validation hoặc audit.
3. **Dữ liệu ban đầu khác nhau:** số hàng, phân phối và trạng thái cache không tương đương.
4. **Cấu hình pool khác nhau:** số connection hoặc timeout khác làm thay đổi concurrency.
5. **Chỉ đo một mức tải:** không thấy điểm bão hòa và tail latency.
6. **Chạy A luôn trước B:** tạo thiên lệch do cache và tải nền.
7. **Không warm-up hoặc warm-up khác nhau:** một phương án chịu chi phí khởi tạo nhiều hơn.
8. **Cửa sổ đo quá ngắn:** thiếu mẫu p99 và bỏ lỡ chu kỳ database.
9. **Chỉ tính request thành công:** bỏ qua dropped request và timeout.
10. **Không tính retry:** TPS cuối cùng che giấu số lần thử và tài nguyên bị tiêu tốn.
11. **Load generator bão hòa:** offered load không đạt mục tiêu.
12. **Không kiểm tra correctness:** phương án nhanh hơn có thể làm sai dữ liệu.
13. **Chỉ chọn lần chạy tốt nhất:** bỏ qua biến động và độ không chắc chắn.
14. **Thay nhiều yếu tố cùng lúc:** không xác định được nguyên nhân cải thiện.
15. **Không lưu cấu hình:** kết quả không thể tái hiện hoặc giải thích.

## 23. Quy tắc ra quyết định

Không nên chọn phương án chỉ dựa trên một metric. Có thể dùng quy trình:

1. Loại phương án không giữ đúng invariant hoặc có hành vi nghiệp vụ khác yêu cầu.
2. Loại phương án vi phạm SLO bắt buộc về p95/p99, success rate hoặc lỗi.
3. So sánh successful TPS và latency trong cùng mức offered load.
4. Xem retry, lock wait, deadlock và tài nguyên để hiểu chi phí ẩn.
5. Đánh giá chi phí vận hành như index storage, log, CPU, connection và độ phức tạp triển khai.
6. Xem xét độ biến động giữa các lần chạy và khoảng tin cậy.
7. Chọn phương án có trade-off tốt nhất cho mục tiêu sản phẩm và ghi lại lý do.

Ví dụ, nếu A đạt 720 TPS với p99 310 ms và B đạt 760 TPS với p99 620 ms, nhưng SLO p99 là 400 ms, B không đạt tiêu chí dù TPS cao hơn. Nếu cả hai cùng đáp ứng SLO, có thể cân nhắc thêm chi phí CPU, retry và khả năng duy trì tải dài hạn.

## 24. Checklist trước khi kết luận phương án tốt hơn

- [ ] Câu hỏi benchmark và giả thuyết được viết trước khi chạy.
- [ ] Hai phương án thực hiện cùng semantics và bảo vệ cùng invariant.
- [ ] Workload mix, dữ liệu, hot-key distribution và kích thước payload đại diện.
- [ ] DBMS, schema, isolation, durability, pool và phần cứng được giữ tương đương.
- [ ] Chỉ thay đổi biến đang được đánh giá hoặc dùng ma trận thí nghiệm đã định nghĩa.
- [ ] Cùng load model, offered load, concurrency và thời lượng đo.
- [ ] Có warm-up, ramp-up, steady-state và cool-down.
- [ ] Thứ tự chạy được luân phiên/ngẫu nhiên và có đủ lần lặp.
- [ ] Đo successful TPS, p50/p95/p99, success, retry và lỗi concurrency.
- [ ] Ghi dropped request, in-flight, pool wait, lock wait và tài nguyên.
- [ ] Load generator không phải bottleneck.
- [ ] Kiểm tra invariant, dữ liệu và tác dụng phụ sau mỗi lượt.
- [ ] Báo median/độ biến động hoặc khoảng tin cậy, không chọn riêng lần tốt nhất.
- [ ] Lưu cấu hình, phiên bản, seed, build ID và dữ liệu thô để tái hiện.
- [ ] Quyết định dựa trên SLO và chi phí tổng thể, không chỉ TPS đỉnh.

So sánh phương án bằng tải đại diện và cùng điều kiện đo giúp biến lựa chọn kỹ thuật thành quyết định có bằng chứng. Giữ nguyên semantics, dữ liệu, load model và môi trường; thay đổi có kiểm soát; đo throughput, latency, success, retry và tài nguyên; sau đó xác minh invariant. Một phương án chỉ thực sự tốt hơn khi cải thiện chỉ số mục tiêu mà vẫn đáp ứng chất lượng nghiệp vụ và SLO trong điều kiện gần với vận hành thật.
