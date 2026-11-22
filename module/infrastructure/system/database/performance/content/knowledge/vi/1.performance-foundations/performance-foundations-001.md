# Hiệu năng cơ sở dữ liệu là gì và ảnh hưởng đến thời gian đáp ứng ứng dụng

Hiệu năng cơ sở dữ liệu là khả năng xử lý khối lượng công việc cần thiết với thời gian đáp ứng phù hợp, thông lượng đủ lớn và mức sử dụng tài nguyên có thể kiểm soát. Một cơ sở dữ liệu được xem là hoạt động tốt khi vẫn phục vụ chính xác, ổn định và có thể dự đoán trong điều kiện tải thực tế, kể cả khi số người dùng, số giao dịch hoặc lượng dữ liệu tăng lên.

Hiệu năng không chỉ là tốc độ chạy của một câu SQL. Người dùng cảm nhận thời gian từ lúc gửi yêu cầu đến lúc nhận được kết quả; trong khoảng thời gian đó, ứng dụng có thể phải chờ lấy kết nối, truyền dữ liệu qua mạng, chờ khóa giao dịch, đọc dữ liệu từ bộ nhớ hoặc thiết bị lưu trữ, rồi mới tiếp tục xử lý. Vì vậy, muốn cải thiện thời gian đáp ứng ứng dụng, cần đo toàn bộ đường đi của yêu cầu và xác định chính xác phần công việc đang làm chậm nó.

## 1. Hiểu đúng về hiệu năng cơ sở dữ liệu

Hiệu năng cơ sở dữ liệu thường được đánh giá qua một số khía cạnh có liên hệ với nhau:

- **Độ trễ (latency):** khoảng thời gian cần để hoàn thành một truy vấn hoặc giao dịch. Độ trễ thấp giúp một yêu cầu riêng lẻ hoàn thành nhanh.
- **Thông lượng (throughput):** số truy vấn hoặc giao dịch mà hệ thống xử lý được trong một đơn vị thời gian, chẳng hạn truy vấn mỗi giây (QPS) hoặc giao dịch mỗi giây (TPS).
- **Khả năng chịu tải đồng thời:** khả năng phục vụ nhiều phiên làm việc cùng lúc mà độ trễ và tỷ lệ lỗi vẫn nằm trong giới hạn chấp nhận được.
- **Hiệu quả sử dụng tài nguyên:** mức CPU, bộ nhớ, dung lượng và tốc độ I/O, kết nối cùng các tài nguyên khác cần để xử lý khối lượng công việc.
- **Tính ổn định:** khả năng duy trì chất lượng phục vụ khi tải dao động, dữ liệu tăng hoặc xuất hiện các truy vấn có chi phí cao.

Các khía cạnh này không thể thay thế cho nhau. Một truy vấn chạy rất nhanh khi chỉ có một người dùng chưa chứng minh cơ sở dữ liệu có thể phục vụ hàng nghìn yêu cầu đồng thời. Ngược lại, thông lượng cao trong một bài kiểm tra cũng chưa đủ nếu một nhóm yêu cầu quan trọng thường xuyên có độ trễ quá lớn.

### Độ trễ và thông lượng

Độ trễ trả lời câu hỏi “một yêu cầu phải chờ bao lâu?”, còn thông lượng trả lời câu hỏi “trong một khoảng thời gian, hệ thống hoàn thành được bao nhiêu yêu cầu?”. Khi tải tăng, hai chỉ số có thể thay đổi theo những cách khác nhau. Hệ thống có thể tiếp tục nhận thêm yêu cầu, nhưng nếu CPU, I/O, khóa hoặc số kết nối đã gần bão hòa, yêu cầu sẽ phải xếp hàng và độ trễ tăng nhanh.

Ví dụ, một truy vấn mất 20 ms khi chạy riêng lẻ có vẻ nhanh. Nếu có nhiều phiên cùng cập nhật một nhóm bản ghi, chúng có thể phải chờ khóa của nhau. Khi đó, thời gian người gọi quan sát được có thể lên đến vài trăm mili giây dù phần thực thi SQL thực tế không thay đổi nhiều.

### Không chỉ nhìn vào giá trị trung bình

Thời gian đáp ứng thường được xem theo phân vị:

| Chỉ số | Cách hiểu | Câu hỏi giúp trả lời |
| --- | --- | --- |
| p50 | 50% yêu cầu hoàn thành trong thời gian này hoặc nhanh hơn | Trải nghiệm điển hình ra sao? |
| p95 | 95% yêu cầu hoàn thành trong thời gian này hoặc nhanh hơn | Phần lớn người dùng có gặp chậm trễ đáng kể không? |
| p99 | 99% yêu cầu hoàn thành trong thời gian này hoặc nhanh hơn | Những yêu cầu chậm nhất có đang gây ảnh hưởng không? |
| Trung bình | Tổng thời gian chia cho số yêu cầu | Mức tiêu tốn thời gian trung bình là bao nhiêu? |

Giả sử 95 yêu cầu hoàn thành trong 100 ms, nhưng 5 yêu cầu còn lại mất 2 giây. Giá trị trung bình có thể che khuất trải nghiệm rất chậm của nhóm yêu cầu cuối. Khi theo dõi dịch vụ, nên xem p50, p95, p99 cùng với thông lượng và tỷ lệ lỗi, đồng thời phân nhóm theo endpoint, loại truy vấn hoặc loại giao dịch. Phân vị cần được tính trên một tập mẫu đủ lớn và một khoảng thời gian có ý nghĩa; một mẫu quá nhỏ dễ tạo ra kết luận thiếu ổn định.

## 2. Cơ sở dữ liệu nằm ở đâu trong thời gian đáp ứng ứng dụng?

Một yêu cầu của người dùng thường đi qua nhiều bước: ứng dụng nhận yêu cầu, kiểm tra dữ liệu đầu vào, lấy kết nối từ connection pool, gửi câu lệnh đến cơ sở dữ liệu, chờ xử lý và nhận kết quả, sau đó tiếp tục tính toán và trả phản hồi. Nếu một bước tuần tự bị chậm, các bước phía sau cũng phải chờ.

Với một đường xử lý tuần tự đơn giản, có thể hình dung:

\[
T_{request} \approx T_{app\_before} + T_{pool\_wait}
 + \sum T_{database\_roundtrip} + T_{app\_after}
\]

Trong đó:

- T_app_before và T_app_after là thời gian ứng dụng xử lý trước và sau khi truy cập dữ liệu.
- T_pool_wait là thời gian chờ lấy được kết nối khả dụng.
- T_database_roundtrip là thời gian cho một lượt gọi cơ sở dữ liệu, gồm truyền yêu cầu, chờ xử lý và nhận kết quả.

Đây là mô hình đơn giản để phân tích một đường xử lý tuần tự. Nếu ứng dụng thực hiện nhiều công việc song song, thời gian tổng thể phụ thuộc vào nhánh chậm nhất trên đường găng, không phải lúc nào cũng bằng tổng thời gian của mọi nhánh. Một yêu cầu cũng có thể gọi cơ sở dữ liệu nhiều lần; khi đó, nhiều lượt truy vấn nhỏ cộng lại có thể tạo ra độ trễ đáng kể.

Trong một lượt xử lý ở cơ sở dữ liệu, thời gian có thể được dùng cho việc phân tích và lập kế hoạch truy vấn, thực thi toán tử, đọc dữ liệu từ bộ nhớ đệm hoặc lưu trữ, ghi dữ liệu, chờ khóa và hoàn tất giao dịch. Cách phân chia cụ thể tùy hệ quản trị cơ sở dữ liệu. Vì thế, thời gian ứng dụng chờ cơ sở dữ liệu phản hồi không phải lúc nào cũng đồng nhất với thời gian CPU thực thi câu lệnh.

### Ví dụ về ảnh hưởng đến người dùng

Một API hiển thị lịch sử đơn hàng có thời gian đáp ứng p95 là 900 ms. Khi phân rã một yêu cầu có tổng thời gian gần mức này, nhóm phát triển nhận thấy:

| Thành phần | Thời gian trong yêu cầu minh họa |
| --- | ---: |
| Ứng dụng xử lý trước và sau truy vấn | 80 ms |
| Chờ kết nối trong connection pool | 170 ms |
| Các lượt gọi cơ sở dữ liệu | 590 ms |
| Truyền dữ liệu và chi phí liên quan khác | 60 ms |
| **Tổng thời gian của yêu cầu** | **900 ms** |

Trong ví dụ này, chỉ tối ưu câu SQL có thể chưa giải quyết hết vấn đề. Connection pool wait cũng chiếm một phần đáng kể. Nếu truy vấn được cải thiện nhưng ứng dụng vẫn không có đủ kết nối hoặc vẫn phát sinh quá nhiều lượt gọi, người dùng có thể không nhận thấy mức cải thiện tương ứng. Các con số trên chỉ minh họa cách phân rã thời gian; cần lấy số liệu thực tế của hệ thống trước khi đưa ra kết luận.

## 3. Vì sao độ trễ cơ sở dữ liệu có thể làm chậm cả hệ thống?

Ứng dụng thường giữ một luồng xử lý, tác vụ hoặc yêu cầu đang hoạt động trong lúc chờ cơ sở dữ liệu. Khi mỗi yêu cầu phải chờ lâu hơn, số yêu cầu đang chờ đồng thời có xu hướng tăng. Connection pool, hàng đợi tác vụ và các giới hạn đồng thời có thể bị lấp đầy. Yêu cầu mới tiếp tục phải đợi, làm thời gian đáp ứng tăng thêm ngay cả khi bản thân câu SQL không chậm hơn.

Trong trạng thái ổn định, định luật Little mô tả quan hệ gần đúng giữa số công việc đang ở trong hệ thống, tốc độ đến và thời gian lưu lại:

\[
L = \lambda \times W
\]

Trong đó L là số công việc trung bình đang ở trong hệ thống, λ là tốc độ yêu cầu đến trung bình và W là thời gian trung bình một công việc ở trong hệ thống. Chẳng hạn, nếu có 100 lượt truy cập cơ sở dữ liệu mỗi giây và mỗi lượt mất trung bình 50 ms, số lượt đang được xử lý hoặc chờ trong hệ thống trung bình xấp xỉ 5. Nếu thời gian tăng lên 300 ms trong khi tốc độ yêu cầu giữ nguyên, con số này xấp xỉ 30. Đây là phép ước lượng cho trạng thái ổn định, không phải giới hạn kết nối cần cấu hình trực tiếp.

Khi độ trễ kéo dài, hệ thống có thể xuất hiện một chuỗi tác động:

1. Truy vấn hoặc giao dịch chậm làm yêu cầu giữ kết nối lâu hơn.
2. Connection pool hết kết nối khả dụng; yêu cầu mới phải chờ hoặc hết thời gian chờ.
3. Luồng xử lý và hàng đợi trong ứng dụng tăng, khiến bộ nhớ và tài nguyên ứng dụng chịu thêm áp lực.
4. Timeout có thể kích hoạt retry. Nếu retry không được giới hạn, tải gửi đến cơ sở dữ liệu còn tăng thêm.
5. Tỷ lệ lỗi tăng và các chức năng dùng chung cơ sở dữ liệu có thể cùng bị ảnh hưởng.

Đây là lý do một truy vấn chậm có thể trở thành vấn đề ở cấp dịch vụ. Cấu hình timeout, giới hạn kết nối và chính sách retry cần phù hợp với khả năng xử lý của hệ thống; tăng số kết nối vô hạn không làm tài nguyên cơ sở dữ liệu tăng theo và có thể khiến tranh chấp nặng hơn.

## 4. Những yếu tố thường quyết định hiệu năng

Hiệu năng là kết quả của cả cách truy cập dữ liệu lẫn tài nguyên mà hệ thống có thể cung cấp. Một số yếu tố thường gặp gồm:

### Câu SQL và kế hoạch thực thi

Cùng một kết quả có thể được tạo ra bằng nhiều cách thực thi. Bộ tối ưu hóa truy vấn chọn kế hoạch dựa trên cấu trúc câu lệnh, chỉ mục, thống kê và các đặc điểm của hệ thống. Kế hoạch có thể dùng quét tuần tự, quét chỉ mục, phép nối, sắp xếp hoặc các toán tử khác.

Một truy vấn lọc trên bảng lớn nhưng không có đường truy cập phù hợp có thể phải đọc nhiều bản ghi rồi mới loại bỏ phần lớn kết quả. Một phép nối có điều kiện không phù hợp hoặc một bước sắp xếp trên tập dữ liệu lớn cũng có thể tiêu tốn nhiều CPU và bộ nhớ. Đọc kế hoạch thực thi giúp kiểm tra cơ sở dữ liệu dự định làm gì; số liệu thực tế khi chạy giúp xác định phần nào đã tốn thời gian.

### Chỉ mục và cách truy cập dữ liệu

Chỉ mục giúp cơ sở dữ liệu tìm các bản ghi phù hợp mà không phải quét toàn bộ dữ liệu trong nhiều trường hợp. Tuy nhiên, chỉ mục có chi phí: nó chiếm dung lượng, cần bộ nhớ đệm và phải được cập nhật khi dữ liệu thay đổi. Tạo nhiều chỉ mục không cần thiết có thể làm chậm thao tác ghi và tăng chi phí bảo trì.

Chỉ mục cần phù hợp với điều kiện lọc, thứ tự sắp xếp, phép nối và kiểu truy vấn thực tế. Chỉ mục nhiều cột còn phụ thuộc vào thứ tự cột và khả năng chọn lọc của dữ liệu. Không nên tạo chỉ mục chỉ vì một cột xuất hiện trong câu SQL; cần kiểm tra kế hoạch thực thi và đo cả truy vấn đọc lẫn tải ghi sau thay đổi.

### Thống kê dữ liệu

Bộ tối ưu hóa thường dựa vào thống kê để ước lượng số dòng và chi phí của các phương án thực thi. Nếu thống kê cũ hoặc không phản ánh phân bố dữ liệu hiện tại, số dòng ước lượng có thể lệch đáng kể so với thực tế. Khi đó, hệ quản trị có thể chọn thứ tự nối hoặc phương pháp truy cập kém phù hợp. Cập nhật thống kê theo cơ chế của hệ quản trị và kiểm tra lại kế hoạch là một phần của quy trình xử lý truy vấn chậm.

### Giao dịch và tranh chấp

Giao dịch cần bảo đảm các quy tắc nhất quán của dữ liệu, nhưng giao dịch kéo dài có thể giữ khóa hoặc tài nguyên lâu hơn cần thiết. Nhiều giao dịch cùng cập nhật một bản ghi hoặc cùng truy cập một vùng dữ liệu có thể phải chờ nhau. Deadlock, thời gian giữ khóa dài và mức cô lập giao dịch đều có thể ảnh hưởng đến độ trễ. Cần phân biệt thời gian thực thi với thời gian chờ khóa để chọn hướng xử lý phù hợp.

### CPU, bộ nhớ và I/O

- **CPU:** các phép nối, lọc, sắp xếp, tính toán hoặc xử lý đồng thời có thể làm CPU bão hòa.
- **Bộ nhớ:** dữ liệu và chỉ mục thường xuyên truy cập nếu nằm trong bộ nhớ đệm có thể được phục vụ nhanh hơn. Thiếu bộ nhớ có thể làm tăng việc đọc từ lưu trữ hoặc gây tràn dữ liệu trung gian ra đĩa.
- **I/O:** đọc hoặc ghi vật lý có độ trễ cao có thể làm truy vấn phải chờ. Cần xem cả độ trễ, thông lượng và hàng đợi I/O, không chỉ tổng số thao tác.
- **Kết nối:** quá nhiều kết nối đồng thời có thể tiêu tốn bộ nhớ và làm tăng chi phí lập lịch, chuyển ngữ cảnh hoặc tranh chấp tài nguyên.

Không có một chỉ số đơn lẻ nào luôn chỉ ra nguyên nhân. CPU cao có thể do truy vấn tính toán nhiều, nhưng cũng có thể do quá nhiều truy vấn cùng chạy. I/O cao có thể là tải bình thường của một hệ thống ghi nhiều, hoặc là dấu hiệu truy vấn đang đọc lượng dữ liệu lớn. Cần đặt số liệu vào đúng loại tải và khoảng thời gian quan sát.

## 5. Đo lường để xác định vấn đề

Trước khi thay đổi SQL, chỉ mục hoặc cấu hình, cần xây dựng đường cơ sở (baseline) để biết hệ thống đang hoạt động ra sao. Một lần đo có ích nên gắn với loại yêu cầu, khoảng thời gian và mức tải cụ thể.

### Các nhóm số liệu nên quan sát

| Nhóm | Ví dụ số liệu | Dùng để nhận biết |
| --- | --- | --- |
| Ứng dụng | Thời gian đáp ứng p50/p95/p99, tỷ lệ lỗi, timeout | Mức ảnh hưởng người dùng và endpoint bị tác động |
| Truy vấn | Thời gian thực thi, số lần gọi, số dòng đọc/trả về, truy vấn tiêu tốn nhiều thời gian | Truy vấn có chi phí cao hoặc bị gọi quá thường xuyên |
| Kết nối | Số kết nối đang dùng, kết nối chờ, thời gian chờ pool | Thiếu kết nối hoặc cấu hình đồng thời không phù hợp |
| Giao dịch | Số giao dịch đang chạy, thời gian giữ giao dịch, thời gian chờ khóa, deadlock | Tranh chấp và giao dịch kéo dài |
| CPU và bộ nhớ | Mức sử dụng CPU, bộ nhớ khả dụng, tỷ lệ cache hit hoặc chỉ số cache tương đương | Áp lực tính toán và hiệu quả bộ nhớ đệm |
| Lưu trữ | Độ trễ đọc/ghi, IOPS, thông lượng, hàng đợi, dung lượng tạm | Nút thắt I/O hoặc thao tác trung gian lớn |
| Hệ thống | QPS/TPS, số phiên hoạt động, tải theo giờ, tăng trưởng dữ liệu | Mối quan hệ giữa khối lượng công việc và năng lực phục vụ |

Tên gọi và cách tính chỉ số khác nhau giữa các hệ quản trị. Cần dùng số liệu tương ứng của nền tảng đang vận hành và đối chiếu với số liệu ở tầng ứng dụng. Ví dụ, thời gian truy vấn trong log cơ sở dữ liệu không nhất thiết bao gồm thời gian chờ lấy kết nối trong ứng dụng.

### Kiểm tra kế hoạch thực thi

Với truy vấn chậm, hãy xem kế hoạch thực thi để tìm cách dữ liệu được truy cập, số dòng ước lượng, số dòng thực tế (nếu công cụ hỗ trợ), phép nối, sắp xếp và các thao tác đọc. Một số hệ quản trị có chế độ hiển thị kế hoạch dự kiến và chế độ đo kế hoạch khi thực thi. Cần đọc tài liệu của hệ quản trị trước khi dùng chế độ phân tích thực thi, vì một số lệnh có thể chạy truy vấn thật và tạo tải hoặc tác động dữ liệu.

Ví dụ câu truy vấn lấy 20 đơn hàng gần nhất của một khách hàng:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 20;
```

Ký hiệu ? minh họa tham số được truyền riêng; cú pháp tham số cụ thể phụ thuộc vào hệ quản trị và thư viện kết nối.

Khi bảng orders lớn, có thể kiểm tra liệu kế hoạch có phải quét nhiều dòng rồi sắp xếp hay không. Một chỉ mục kết hợp theo các cột lọc và sắp xếp có thể là giả thuyết cần thử, chẳng hạn:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC);
```

Đây chỉ là ví dụ về một phương án có thể kiểm chứng. Hiệu quả phụ thuộc vào hệ quản trị, phân bố dữ liệu, độ chọn lọc của điều kiện, kiểu sắp xếp và tỷ lệ đọc/ghi. Sau khi tạo chỉ mục, cần kiểm tra kế hoạch mới, thời gian truy vấn dưới tải đại diện, dung lượng chỉ mục và ảnh hưởng đến thao tác ghi. Không mặc định rằng chỉ mục mới chắc chắn làm truy vấn nhanh hơn.

### Phân biệt các loại thời gian chờ

Khi truy vấn chậm, hãy xác định phần thời gian đang nằm ở đâu:

- Nếu thời gian chờ connection pool cao, kiểm tra số lượt gọi, thời gian giữ kết nối, giới hạn pool và tải đồng thời.
- Nếu thời gian chờ khóa cao, xác định giao dịch giữ khóa, phạm vi cập nhật và thời lượng giao dịch.
- Nếu CPU cao cùng với nhiều phép nối hoặc sắp xếp tốn kém, xem lại câu SQL, kế hoạch và lượng dữ liệu phải xử lý.
- Nếu độ trễ đọc/ghi và hàng đợi lưu trữ tăng, kiểm tra mẫu truy cập, lượng dữ liệu đọc/ghi và giới hạn của thiết bị lưu trữ.
- Nếu truy vấn chạy nhanh trong cơ sở dữ liệu nhưng API vẫn chậm, kiểm tra số lượt round-trip, truyền dữ liệu, xử lý ở ứng dụng và thời gian chờ kết nối.

Các dấu hiệu trên là hướng điều tra, không phải kết luận tự động. Cần đối chiếu log, biểu đồ theo thời gian và mẫu yêu cầu có liên quan trước khi xác định nguyên nhân gốc.

## 6. Quy trình cải thiện và kiểm chứng

Một thay đổi hiệu năng chỉ có ý nghĩa khi đo được tác động trong điều kiện tương đương và không làm sai lệch kết quả nghiệp vụ. Có thể thực hiện theo quy trình sau:

1. **Xác định mục tiêu:** chọn endpoint, truy vấn hoặc giao dịch cần cải thiện; đặt mục tiêu về p95/p99, thông lượng, tỷ lệ lỗi hoặc mức sử dụng tài nguyên.
2. **Ghi nhận đường cơ sở:** đo trên dữ liệu và tải đại diện, ghi lại cấu hình, thời điểm, số lượng yêu cầu, phân vị độ trễ và các tài nguyên liên quan.
3. **Tìm nút thắt:** kết hợp số liệu ứng dụng, thống kê cơ sở dữ liệu, log truy vấn và kế hoạch thực thi để xác định bước đang tiêu tốn thời gian.
4. **Đưa ra giả thuyết:** nêu rõ vì sao thay đổi dự kiến có tác dụng, ví dụ giảm số dòng phải đọc, giảm số lượt gọi, rút ngắn thời gian giữ khóa hoặc tránh chờ I/O.
5. **Thử một thay đổi có kiểm soát:** điều chỉnh SQL, chỉ mục, cách phân trang, phạm vi giao dịch hoặc cấu hình phù hợp với nguyên nhân đã tìm thấy. Ghi lại thay đổi để có thể đối chiếu.
6. **Đo lại dưới tải tương đương:** so sánh cùng loại dữ liệu, mức tải và cách tạo tải. Theo dõi cả độ trễ, thông lượng, lỗi, CPU, bộ nhớ, I/O và thời gian chờ.
7. **Kiểm tra tính đúng đắn và tác động phụ:** xác nhận kết quả nghiệp vụ không đổi, giao dịch vẫn bảo đảm tính nhất quán, thao tác ghi không suy giảm quá mức và tài nguyên không bị đẩy sang một nút thắt khác.
8. **Theo dõi sau khi áp dụng:** quan sát trong điều kiện tải thực tế, lưu lại số liệu trước/sau và chuẩn bị cách hoàn nguyên nếu chỉ số quan trọng xấu đi.

Không nên kết luận một tối ưu hóa thành công chỉ vì một lần chạy đơn lẻ nhanh hơn. Bộ nhớ đệm có thể đã nóng lên, tải nền có thể đã giảm hoặc dữ liệu kiểm thử có thể không đại diện. Cần lặp lại phép đo đủ số lần và so sánh trong điều kiện tương đương. Nếu thay đổi cải thiện một truy vấn nhưng làm tăng thời gian ghi, dung lượng hoặc độ trễ của luồng khác, phải đánh giá tổng tác động lên workload.

## 7. Ví dụ điều tra một API chậm

Giả sử API lịch sử đơn hàng có p95 tăng từ 250 ms lên 900 ms sau khi dữ liệu tăng đáng kể. Tỷ lệ lỗi cũng bắt đầu tăng vào giờ cao điểm. Quy trình điều tra có thể diễn ra như sau:

**Bước 1 – Xác định phạm vi:** dashboard cho thấy vấn đề tập trung ở API lịch sử đơn hàng; các API ít truy cập cơ sở dữ liệu vẫn ổn định. Thông lượng yêu cầu tăng trong cùng khoảng thời gian.

**Bước 2 – Phân rã thời gian:** trace cho thấy API dành nhiều thời gian chờ kết nối và chờ các truy vấn lấy danh sách đơn hàng. Điều này cho thấy cần kiểm tra cả số lượt truy cập và hiệu năng truy vấn.

**Bước 3 – Đọc kế hoạch và thống kê:** truy vấn lọc theo khách hàng và trạng thái, sắp xếp theo ngày tạo. Kế hoạch cho thấy hệ quản trị đọc nhiều dòng hơn số dòng API trả về. Nhóm phát triển kiểm tra thống kê, phân bố trạng thái và khả năng sử dụng chỉ mục phù hợp.

**Bước 4 – Thử phương án:** nhóm thử một chỉ mục kết hợp trên môi trường kiểm thử có dữ liệu và tải gần với thực tế. Sau thay đổi, họ kiểm tra kế hoạch, thời gian đọc, số dòng được xử lý và chi phí ghi phát sinh.

**Bước 5 – Kiểm chứng ở cấp API:** chạy lại cùng kịch bản tải, so sánh p50/p95/p99, thông lượng, thời gian chờ pool, CPU và I/O. Đồng thời xác nhận thứ tự, số lượng và nội dung đơn hàng trả về vẫn chính xác.

Nếu truy vấn giảm thời gian nhưng pool wait vẫn cao, cần tiếp tục điều tra số lượt gọi trên mỗi yêu cầu, thời gian giữ kết nối và giới hạn đồng thời. Nếu pool wait giảm nhưng I/O tăng mạnh, phải xem lại lượng dữ liệu đọc hoặc ảnh hưởng của chỉ mục. Quy trình kết thúc khi mục tiêu dịch vụ được đáp ứng ổn định và không xuất hiện suy giảm đáng kể ở các luồng liên quan.

## 8. Nguyên tắc cần ghi nhớ

- Đánh giá hiệu năng theo workload và tải thực tế, không dựa riêng vào một truy vấn chạy thử.
- Đo thời gian đáp ứng ở cấp ứng dụng và đối chiếu với thời gian chờ, thực thi ở cấp cơ sở dữ liệu.
- Theo dõi phân vị độ trễ cùng thông lượng và tỷ lệ lỗi để nhận ra cả vấn đề phổ biến lẫn các trường hợp chậm kéo dài.
- Xem kế hoạch thực thi, thống kê, chỉ mục và cách tổ chức truy cập dữ liệu trước khi thay đổi.
- Phân biệt chờ khóa, chờ kết nối, chờ I/O và thời gian xử lý CPU; mỗi nguyên nhân cần cách khắc phục khác nhau.
- Đánh giá tác động của tối ưu hóa lên cả đọc, ghi, giao dịch, tài nguyên và các chức năng dùng chung cơ sở dữ liệu.
- Luôn đo lại trong điều kiện tương đương và xác nhận tính đúng đắn sau thay đổi.

Hiểu hiệu năng cơ sở dữ liệu là bước đầu để xây dựng ứng dụng có thời gian đáp ứng ổn định. Khi biết yêu cầu đang chờ ở đâu, cơ sở dữ liệu đang tiêu tốn tài nguyên nào và tải thay đổi ra sao, nhóm phát triển có thể chọn giải pháp dựa trên bằng chứng, rồi kiểm chứng rằng cải thiện ở tầng dữ liệu thực sự mang lại trải nghiệm tốt hơn cho người dùng.
