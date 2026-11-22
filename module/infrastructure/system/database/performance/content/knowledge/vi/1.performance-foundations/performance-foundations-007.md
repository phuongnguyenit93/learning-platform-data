# Tư duy tối ưu theo bằng chứng và giới hạn của việc áp dụng mẹo chung

Tối ưu hiệu năng cơ sở dữ liệu là quá trình tìm ra nguyên nhân khiến một khối lượng công việc cụ thể không đáp ứng mục tiêu, thử một thay đổi có cơ sở, rồi đo lại để xác nhận tác động. Một câu lệnh SQL chậm, CPU cao hay tỷ lệ cache hit thấp chỉ là dấu hiệu ban đầu; mỗi dấu hiệu có thể xuất phát từ nhiều nguyên nhân khác nhau.

Trong module **DATABASE_PERFORMANCE**, bạn rèn phương pháp tối ưu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Phương pháp này được dùng khi thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, tìm nút thắt I/O và bộ nhớ, cũng như kiểm chứng kết quả sau điều chỉnh. Mục tiêu không phải làm cho một truy vấn riêng lẻ có vẻ nhanh hơn trong một lần chạy, mà là cải thiện hành vi của hệ thống dưới tải thực tế mà vẫn giữ đúng dữ liệu và độ ổn định.

## 1. Bắt đầu từ mục tiêu và khối lượng công việc

Trước khi thay đổi chỉ mục hay viết lại SQL, hãy xác định hệ thống cần đạt điều gì. Các mục tiêu thường gặp gồm:

- Độ trễ: thời gian hoàn tất một thao tác, thường theo dõi p50, p95 và p99.
- Thông lượng: số truy vấn hoặc giao dịch hoàn tất trong một đơn vị thời gian.
- Độ ổn định: tỷ lệ lỗi, timeout, deadlock và mức dao động độ trễ khi tải tăng.
- Hiệu quả tài nguyên: mức sử dụng CPU, bộ nhớ, I/O, dung lượng lưu trữ và số kết nối.
- Tính đúng đắn: kết quả truy vấn, thứ tự, ràng buộc và tính nhất quán vẫn phải được bảo toàn.

Không có một chỉ số đơn lẻ đại diện cho toàn bộ hiệu năng. Độ trễ trung bình có thể giảm trong khi p99 tăng mạnh; thông lượng có thể tăng vì hệ thống chấp nhận nhiều truy vấn hơn nhưng hàng đợi và timeout cũng tăng. Hãy chọn các chỉ số phản ánh trải nghiệm và mục tiêu vận hành của ứng dụng.

Tiếp theo, mô tả tải mà hệ thống thực sự phục vụ:

| Đặc điểm | Câu hỏi cần trả lời |
|---|---|
| Tỷ lệ đọc và ghi | Bao nhiêu phần trăm thao tác là SELECT, INSERT, UPDATE hoặc DELETE? |
| Mẫu truy vấn | Những nhóm truy vấn nào xuất hiện thường xuyên và nhóm nào tiêu tốn nhiều thời gian nhất? |
| Quy mô dữ liệu | Bảng có bao nhiêu hàng, dữ liệu tăng nhanh đến đâu, chỉ mục chiếm bao nhiêu dung lượng? |
| Phân bố dữ liệu | Giá trị có đồng đều hay tập trung ở một số tenant, trạng thái hoặc khoảng thời gian? |
| Mức đồng thời | Có bao nhiêu giao dịch hoạt động cùng lúc? Có thời điểm tải tăng đột biến không? |
| Tính thời gian | Tải cao nhất xảy ra vào giờ nào? Có khác biệt giữa ngày thường và cuối tuần không? |

Một truy vấn chạy nhanh trên vài nghìn hàng có thể chậm khi bảng tăng lên hàng trăm triệu hàng. Một chỉ mục hữu ích với tải đọc nhiều có thể làm hệ thống ghi chậm đi nếu mỗi giao dịch phải cập nhật thêm nhiều cấu trúc chỉ mục. Vì vậy, phải đánh giá thay đổi trong bối cảnh dữ liệu, tần suất và mức đồng thời cụ thể.

## 2. Thiết lập đường cơ sở trước khi tối ưu

Đường cơ sở (baseline) là tập số liệu mô tả hành vi hiện tại trong một khoảng thời gian và điều kiện tải xác định. Nếu không có baseline, bạn không thể phân biệt cải thiện thật với dao động tự nhiên.

Một baseline hữu ích thường ghi nhận:

1. Thời điểm và khoảng đo, môi trường, phiên bản cấu hình và mức tải.
2. Thông lượng, p50, p95, p99, tỷ lệ lỗi và timeout.
3. Các nhóm truy vấn theo mẫu hoặc fingerprint, số lần chạy và tổng thời gian tiêu thụ.
4. CPU, bộ nhớ, độ trễ đọc/ghi đĩa, lượng dữ liệu đọc từ bộ nhớ đệm và từ thiết bị lưu trữ.
5. Thời gian chờ khóa, giao dịch kéo dài, deadlock, hàng đợi kết nối và truy vấn chờ tài nguyên.
6. Kế hoạch thực thi của các truy vấn quan trọng cùng số hàng ước lượng và số hàng thực tế nếu hệ quản trị cung cấp.

Nên phân biệt thời gian truy vấn trong cơ sở dữ liệu với thời gian ứng dụng chờ lấy kết nối, truyền dữ liệu qua mạng hoặc xử lý kết quả. Nếu ứng dụng mất hai giây nhưng cơ sở dữ liệu chỉ thực thi truy vấn trong vài chục mili giây, việc thêm chỉ mục có thể không giải quyết đúng điểm nghẽn.

Khi chọn truy vấn để điều tra, đừng chỉ nhìn truy vấn có thời gian chạy dài nhất. Một truy vấn mất 500 ms nhưng chạy một lần mỗi ngày có thể ít ảnh hưởng hơn truy vấn mất 20 ms nhưng chạy hàng nghìn lần mỗi phút. Hãy xem cả độ trễ mỗi lần, tần suất, tổng thời gian tiêu thụ và tác động đến các thao tác quan trọng.

Đo ở điều kiện đại diện: dữ liệu có kích thước và phân bố gần thực tế, tham số truy vấn đa dạng, mức đồng thời tương đương và cả giai đoạn tải cao. Một lần chạy đơn lẻ với cache đã nóng không thể đại diện cho mọi tình huống.

## 3. Chuyển dấu hiệu thành giả thuyết có thể kiểm chứng

Một dấu hiệu chỉ có giá trị khi được chuyển thành giả thuyết cụ thể. Ví dụ:

| Dấu hiệu | Giả thuyết cần kiểm tra | Bằng chứng phù hợp |
|---|---|---|
| Một truy vấn tăng độ trễ khi bảng lớn dần | Truy vấn đọc quá nhiều hàng hoặc thiếu đường truy cập phù hợp | Kế hoạch thực thi, số hàng đọc và trả về, chỉ mục hiện có |
| CPU tăng cao trong khi I/O thấp | Có thể tốn CPU cho phép nối, sắp xếp, biểu thức hoặc xử lý quá nhiều hàng | Kế hoạch thực thi, thời gian từng bước, hồ sơ CPU |
| Độ trễ tăng theo mức đồng thời | Có thể xảy ra tranh chấp khóa, bão hòa CPU hoặc hàng đợi kết nối | Lock wait, wait event, số kết nối, hàng đợi và thông lượng |
| Đọc đĩa tăng và truy vấn chậm | Working set không vừa bộ nhớ, truy vấn quét rộng hoặc cache bị cạnh tranh | Buffer read, I/O latency, dung lượng working set, kế hoạch |
| Ghi chậm sau khi thêm chỉ mục | Chi phí duy trì chỉ mục có thể lớn hơn lợi ích đọc | Thông lượng ghi, thời gian giao dịch, kích thước và số lần cập nhật chỉ mục |

Giả thuyết tốt phải nêu được nguyên nhân dự kiến, truy vấn hoặc nhóm thao tác chịu ảnh hưởng, chỉ số sẽ thay đổi nếu giả thuyết đúng và cách kiểm tra. Chẳng hạn: “Truy vấn lọc theo tenant, trạng thái và thời gian đang đọc nhiều hàng vì chưa có chỉ mục phù hợp; nếu thêm chỉ mục đúng thứ tự cột, số hàng phải đọc và p95 sẽ giảm mà thông lượng ghi vẫn nằm trong giới hạn.”

Hãy kiểm tra từng giả thuyết bằng dữ liệu. Tránh đổi đồng thời nhiều tham số, thêm nhiều chỉ mục và viết lại SQL trong cùng một lần thử. Khi có nhiều thay đổi, bạn sẽ khó biết yếu tố nào tạo ra kết quả hoặc gây ra hồi quy.

## 4. Đọc kế hoạch thực thi thay vì đoán cách truy vấn chạy

Kế hoạch thực thi cho biết hệ quản trị dự định hoặc đã thực hiện cách truy cập dữ liệu nào: quét bảng, quét chỉ mục, tìm kiếm theo khóa, nối bảng, sắp xếp, gom nhóm hay tạo bảng tạm. Tên toán tử và cách hiển thị phụ thuộc hệ quản trị cơ sở dữ liệu.

Khi đọc một kế hoạch, hãy lần lượt xem:

- **Đường truy cập:** hệ quản trị quét toàn bảng, quét một phần chỉ mục hay tìm kiếm theo khóa?
- **Số hàng:** số hàng ước lượng có gần số hàng thực tế không? Sai lệch lớn có thể làm bộ tối ưu chọn kế hoạch kém.
- **Lọc dữ liệu:** điều kiện được áp dụng ngay tại bước truy cập hay chỉ sau khi đọc nhiều hàng?
- **Phép nối:** thuật toán nối có phù hợp với kích thước hai phía và số hàng đầu vào không?
- **Sắp xếp và gom nhóm:** có phải sắp xếp lượng dữ liệu lớn hoặc ghi dữ liệu tạm ra đĩa không?
- **Chi phí và thời gian:** số liệu ước lượng, số vòng lặp, thời gian thực tế và lượng I/O cho biết bước nào đáng điều tra.

Ví dụ cú pháp minh họa, có thể khác giữa các hệ quản trị:

~~~sql
EXPLAIN
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
ORDER BY created_at DESC
FETCH FIRST 50 ROWS ONLY;
~~~

EXPLAIN thường cho biết kế hoạch được ước lượng. Một số hệ quản trị hỗ trợ EXPLAIN ANALYZE hoặc tùy chọn tương đương để chạy câu lệnh và ghi nhận số liệu thực tế. Hãy đọc tài liệu của hệ quản trị đang dùng trước khi thực hiện: chế độ phân tích thực tế có thể thực thi câu lệnh; với INSERT, UPDATE hoặc DELETE, điều này có thể tạo thay đổi dữ liệu nếu không được kiểm soát. Chỉ chạy trên dữ liệu và môi trường an toàn, hoặc trong cơ chế giao dịch phù hợp với hệ quản trị.

Không kết luận rằng quét toàn bảng luôn sai. Nếu truy vấn cần phần lớn hàng trong bảng, quét tuần tự có thể rẻ hơn nhiều lần truy cập chỉ mục rời rạc. Tương tự, một phép nối dạng hash không mặc nhiên kém hơn nested loop; hiệu quả phụ thuộc số hàng, phân bố dữ liệu, bộ nhớ và mức đồng thời.

## 5. Dùng thống kê để hiểu quyết định của bộ tối ưu

Bộ tối ưu truy vấn dựa vào thống kê để ước lượng số hàng thỏa điều kiện và chi phí của các phương án. Thống kê có thể bao gồm số hàng, số giá trị phân biệt, histogram, giá trị phổ biến và tương quan giữa các cột. Chi tiết và lệnh cập nhật thống kê khác nhau theo hệ quản trị.

Khi số hàng thực tế lệch xa số hàng ước lượng, hãy xem xét:

- Thống kê đã cũ sau khi dữ liệu thay đổi đáng kể chưa?
- Dữ liệu có phân bố lệch, chẳng hạn một trạng thái chiếm gần hết bảng còn trạng thái khác rất hiếm không?
- Hai cột lọc có tương quan với nhau khiến giả định độc lập không còn đúng không?
- Tham số truy vấn hiện tại có đại diện cho các lần chạy khác không?
- Cơ chế cache kế hoạch hoặc tối ưu theo tham số có làm một kế hoạch phù hợp với giá trị này nhưng kém với giá trị khác không?

Ví dụ, cột status có ba giá trị nhưng phần lớn hàng đều mang trạng thái COMPLETED. Chỉ nhìn số giá trị phân biệt có thể khiến người đọc nghĩ rằng lọc theo status luôn chọn lọc tốt. Trên thực tế, điều kiện status = COMPLETED có thể trả về phần lớn bảng, trong khi status = PENDING chỉ trả về một tỷ lệ rất nhỏ.

Cập nhật thống kê có thể giúp bộ tối ưu ước lượng tốt hơn, nhưng không bảo đảm mọi truy vấn sẽ nhanh hơn. Sau khi cập nhật, hãy so sánh kế hoạch và số liệu thực tế trên nhiều giá trị tham số đại diện. Nếu hệ quản trị hỗ trợ thống kê mở rộng hoặc thống kê theo biểu thức, chỉ sử dụng khi bằng chứng cho thấy tương quan hoặc phân bố cụ thể đang làm sai lệch ước lượng.

## 6. Đánh giá chỉ mục theo cả chi phí đọc và chi phí ghi

Chỉ mục tạo thêm đường truy cập để tìm hàng mà không phải quét toàn bộ bảng. Tuy nhiên, mỗi chỉ mục cần dung lượng lưu trữ, bộ nhớ đệm và công sức duy trì khi dữ liệu được thêm, sửa hoặc xóa.

Một chỉ mục đáng cân nhắc khi:

- Điều kiện lọc thường xuyên chọn ra một phần nhỏ dữ liệu.
- Truy vấn nối bảng cần tìm nhanh các hàng theo khóa nối.
- Thứ tự sắp xếp hoặc phân trang có thể tận dụng thứ tự trong chỉ mục.
- Truy vấn lặp lại đủ thường xuyên để lợi ích đọc bù được chi phí duy trì.

Khi thiết kế chỉ mục nhiều cột, thứ tự cột phải dựa trên mẫu truy vấn. Các cột được so sánh bằng điều kiện bằng thường có thể đứng trước cột dùng cho khoảng giá trị hoặc thứ tự sắp xếp, nhưng đây chỉ là điểm xuất phát để đánh giá. Độ chọn lọc, điều kiện truy vấn, thứ tự sắp xếp, khả năng tận dụng tiền tố chỉ mục và quy tắc của từng hệ quản trị đều có ảnh hưởng.

Với truy vấn ví dụ ở phần trên, chỉ mục ứng viên có thể là:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Đây là giả thuyết thiết kế, không phải công thức áp dụng cho mọi bảng. Cần kiểm tra kế hoạch trước và sau, số hàng được đọc, mức sử dụng chỉ mục, dung lượng tăng thêm và tác động đến INSERT/UPDATE/DELETE. Một số hệ quản trị hỗ trợ chỉ mục có cột bao phủ hoặc chỉ mục có điều kiện; cú pháp và lợi ích phụ thuộc nền tảng.

Các giới hạn thường bị bỏ qua:

- Chỉ mục trên cột có độ chọn lọc thấp có thể ít hữu ích nếu truy vấn vẫn cần phần lớn hàng.
- Nhiều chỉ mục tương tự nhau làm tăng dung lượng và chi phí ghi, đồng thời gây khó khăn cho bảo trì.
- Chỉ mục có thể không được dùng nếu biểu thức hoặc chuyển đổi kiểu trên cột khiến điều kiện không còn phù hợp với đường truy cập đó.
- Chỉ mục mới có thể cạnh tranh bộ nhớ đệm với dữ liệu và chỉ mục khác.
- Một kế hoạch dùng chỉ mục có thể chậm hơn quét tuần tự trong một số phân bố dữ liệu hoặc mức tải.

Không thêm chỉ mục chỉ vì một cột xuất hiện trong WHERE. Hãy bắt đầu từ truy vấn quan trọng, đọc kế hoạch, xác định số hàng cần đọc và kiểm chứng lợi ích trên cả tải đọc lẫn tải ghi.

## 7. Cải thiện SQL dựa trên cách dữ liệu được truy cập

Viết SQL rõ ràng giúp người đọc hiểu ý định và giúp việc đo lường, bảo trì dễ hơn. Tuy nhiên, một cách viết ngắn hơn không nhất thiết chạy nhanh hơn; nhiều hệ quản trị có thể biến đổi các biểu thức tương đương thành cùng một kế hoạch.

Một số hướng điều tra thường hữu ích:

**Chỉ lấy dữ liệu cần dùng.** Tránh lấy mọi cột khi ứng dụng chỉ cần vài trường. Điều này giảm dữ liệu truyền, bộ nhớ ở ứng dụng và đôi khi giúp truy vấn tận dụng chỉ mục bao phủ. Nhưng không cần máy móc loại bỏ cột nếu nó không tạo ra chi phí đáng kể.

**Giữ điều kiện lọc phù hợp với chỉ mục.** Một biểu thức áp dụng hàm lên cột có thể khiến chỉ mục thông thường khó được sử dụng. Ví dụ, thay vì biến đổi cột ngày trong điều kiện, hãy cân nhắc lọc theo khoảng thời gian:

~~~sql
-- Cách biểu đạt có thể cản trở chỉ mục thông thường trên created_at
WHERE DATE(created_at) = :target_date

-- Cách biểu đạt theo khoảng, với mốc thời gian đã được tính trước
WHERE created_at >= :day_start
  AND created_at < :next_day_start
~~~

Cách thứ hai vẫn cần được kiểm tra theo kiểu dữ liệu, múi giờ và ngữ nghĩa ngày của ứng dụng. Nếu cần tìm theo biểu thức, một số hệ quản trị hỗ trợ chỉ mục biểu thức hoặc cột tính toán.

**Tránh đọc thừa do phân trang.** OFFSET lớn có thể khiến hệ quản trị phải đi qua nhiều hàng trước khi trả về trang cần thiết. Với tập dữ liệu lớn và thứ tự ổn định, phân trang theo khóa (keyset pagination) có thể hiệu quả hơn. Điều kiện tiếp trang phải dùng khóa sắp xếp phù hợp và có tiêu chí phụ để thứ tự không bị mơ hồ khi nhiều hàng trùng giá trị.

**Kiểm tra truy vấn lặp kiểu N+1.** Nếu ứng dụng đọc một danh sách rồi phát sinh thêm một truy vấn cho từng phần tử, tổng số lần gọi có thể tăng theo số hàng. Có thể cân nhắc JOIN, truy vấn theo lô hoặc cơ chế tải trước, nhưng phải kiểm tra kích thước kết quả, dữ liệu trùng lặp và mức tiêu thụ bộ nhớ.

**Không thay JOIN bằng subquery hoặc ngược lại theo mẹo truyền miệng.** Bộ tối ưu thường có thể biến đổi nhiều dạng SQL tương đương. Chỉ viết lại khi kế hoạch, số liệu hoặc khả năng đọc hiểu cho thấy có vấn đề cụ thể; sau đó xác nhận kết quả vẫn tương đương về ngữ nghĩa.

## 8. Nhận diện tranh chấp giao dịch và khóa

Khi nhiều giao dịch cùng truy cập dữ liệu, thời gian chờ có thể lớn hơn thời gian thực thi câu lệnh. Một truy vấn nhìn riêng lẻ rất nhanh vẫn có thể nằm trong giao dịch chậm vì phải chờ khóa.

Các dấu hiệu cần quan sát gồm thời gian chờ khóa tăng, giao dịch mở lâu, deadlock, nhiều thao tác cập nhật cùng một hàng hoặc một nhóm hàng, và độ trễ tăng mạnh khi số phiên đồng thời tăng.

Một số nguyên nhân phổ biến:

- Giao dịch giữ khóa lâu do thực hiện thêm công việc ở ứng dụng trước khi commit.
- Nhiều giao dịch cập nhật cùng một bản ghi nóng hoặc cùng một bộ đếm.
- Thứ tự cập nhật tài nguyên không nhất quán làm tăng nguy cơ deadlock.
- Giao dịch đọc và ghi có mức cô lập hoặc phạm vi khóa không phù hợp với yêu cầu.
- Một thao tác quét rộng giữ khóa hoặc chiếm tài nguyên lâu hơn dự kiến.

Các hướng xử lý cần đánh giá theo ngữ nghĩa dữ liệu:

- Giữ giao dịch ngắn và commit sớm sau khi hoàn tất phần công việc cần bảo vệ.
- Tránh chờ người dùng hoặc gọi dịch vụ bên ngoài trong khi đang giữ giao dịch mở.
- Dùng thứ tự truy cập tài nguyên nhất quán giữa các luồng xử lý.
- Chia lô cập nhật lớn khi điều đó không phá vỡ tính nguyên tử mà nghiệp vụ yêu cầu.
- Với thao tác cập nhật có thể xung đột, cân nhắc kiểm soát lạc quan và xử lý retry có giới hạn.
- Thiết kế xử lý retry sao cho thao tác có tính lặp an toàn (idempotent) hoặc có cơ chế chống ghi nhận trùng.

Không nên hạ mức cô lập hoặc bỏ khóa chỉ để giảm thời gian chờ mà chưa đánh giá khả năng đọc dữ liệu chưa commit, mất cập nhật, đọc không nhất quán hay vi phạm quy tắc nghiệp vụ. Hiệu năng giao dịch phải được cân bằng với tính đúng đắn.

## 9. Phân biệt nút thắt I/O, bộ nhớ và CPU

Hiệu năng cơ sở dữ liệu thường chịu tác động đồng thời của nhiều tài nguyên. Một chỉ số tăng chưa đủ để kết luận tài nguyên đó là nguyên nhân gốc.

**I/O và working set.** Nếu dữ liệu mà workload truy cập thường xuyên lớn hơn vùng dữ liệu có thể giữ trong bộ nhớ, hệ thống có thể phải đọc đĩa nhiều. Hãy xem độ trễ thiết bị, lượng đọc vật lý, mẫu đọc ngẫu nhiên hay tuần tự, số lần quét rộng và mức cạnh tranh giữa các truy vấn. Giảm lượng dữ liệu phải đọc hoặc cải thiện đường truy cập thường bền vững hơn việc chỉ tăng bộ nhớ mà không hiểu working set.

**Bộ nhớ.** Bộ nhớ được dùng cho cache dữ liệu, cache kế hoạch, phép nối, sắp xếp và các thao tác trung gian. Thiếu bộ nhớ có thể khiến thao tác tràn ra vùng lưu trữ tạm; cấp quá nhiều cho mỗi thao tác có thể làm tổng nhu cầu vượt giới hạn khi nhiều truy vấn chạy đồng thời. Cần quan sát spill, bộ nhớ thực tế, mức đồng thời và cấu hình của hệ quản trị trước khi điều chỉnh.

**CPU.** CPU cao có thể đến từ số hàng xử lý quá lớn, biểu thức tốn kém, phép nối, sắp xếp, mã hóa, nén hoặc quá nhiều truy vấn nhỏ. Hãy ghép số liệu CPU với kế hoạch và tần suất truy vấn. Tăng số lõi không giải quyết được một truy vấn xử lý dữ liệu thừa hoặc một luồng bị tuần tự hóa bởi tranh chấp.

**Cache hit ratio.** Tỷ lệ cache hit cao không chứng minh truy vấn hiệu quả: hệ thống vẫn có thể đọc hàng triệu trang từ cache để trả về vài hàng. Tỷ lệ thấp cũng không luôn là vấn đề nếu workload chủ yếu quét tuần tự hoặc dữ liệu được đọc một lần. Hãy kết hợp tỷ lệ này với số lượng trang, I/O vật lý, độ trễ, kích thước working set và kế hoạch thực thi.

**Kết nối và hàng đợi.** Quá nhiều kết nối đồng thời có thể làm tăng bộ nhớ, chuyển ngữ cảnh và tranh chấp. Pool kết nối giúp giới hạn số phiên, nhưng giới hạn quá thấp có thể tạo hàng đợi ở ứng dụng. Đo cả thời gian chờ lấy kết nối và tải bên trong cơ sở dữ liệu trước khi thay đổi kích thước pool.

## 10. Vì sao các mẹo chung có thể gây tác dụng ngược

Mẹo tối ưu thường được đúc kết từ một bối cảnh cụ thể. Khi dữ liệu, hệ quản trị, phần cứng, workload hoặc yêu cầu nhất quán thay đổi, điều kiện để mẹo đó có ích cũng thay đổi.

| Mẹo thường nghe | Khi có thể hữu ích | Giới hạn và chi phí cần kiểm tra |
|---|---|---|
| “Thêm chỉ mục cho mọi cột trong WHERE” | Truy vấn lọc chọn lọc và có mẫu truy cập ổn định | Tăng chi phí ghi, dung lượng; chỉ mục có thể không được chọn hoặc đọc quá nhiều hàng |
| “Quét bảng luôn chậm” | Quét bảng đáng điều tra khi chỉ cần một phần nhỏ dữ liệu | Quét tuần tự có thể rẻ hơn khi cần phần lớn bảng hoặc dữ liệu nằm liên tục |
| “SELECT * luôn phải bỏ” | Lấy ít cột giúp giảm truyền dữ liệu và có thể tận dụng chỉ mục bao phủ | Lợi ích phụ thuộc độ rộng hàng, số hàng và nhu cầu thực tế của ứng dụng |
| “JOIN luôn chậm hơn nhiều truy vấn” | Truy vấn theo lô có thể giảm số lần gọi lặp kiểu N+1 | JOIN có thể tạo tập kết quả lớn; nhiều truy vấn riêng lẻ có thể làm tăng round trip |
| “Tăng bộ nhớ sẽ làm mọi truy vấn nhanh” | Working set hoặc thao tác trung gian đang thiếu bộ nhớ | Bộ nhớ cấp theo thao tác có thể nhân lên theo mức đồng thời; nút thắt có thể nằm ở CPU, khóa hoặc I/O |
| “Cache càng nhiều càng tốt” | Dữ liệu đọc lặp lại, ít thay đổi và có chiến lược vô hiệu hóa rõ ràng | Dữ liệu cũ, chi phí đồng bộ, áp lực bộ nhớ và tỷ lệ truy cập thấp có thể làm cache phản tác dụng |
| “Giảm mức cô lập để hết chờ khóa” | Có thể phù hợp nếu nghiệp vụ cho phép mức nhất quán thấp hơn | Có nguy cơ đọc sai hoặc cập nhật mất; phải đánh giá ngữ nghĩa giao dịch |
| “Tối ưu truy vấn chậm nhất trước” | Truy vấn đó nằm trên luồng nghiệp vụ quan trọng hoặc gây timeout | Truy vấn ít chạy có thể có tác động tổng thể thấp hơn truy vấn vừa chậm vừa rất thường xuyên |

Cách dùng mẹo đúng là coi chúng như nguồn ý tưởng để hình thành giả thuyết. Trước khi áp dụng, hãy trả lời: điều kiện nào khiến mẹo có ích, bằng chứng nào cho thấy điều kiện đó đang tồn tại, chi phí phụ nào có thể phát sinh và chỉ số nào sẽ xác nhận kết quả.

## 11. Ví dụ: điều tra một truy vấn danh sách đơn hàng

Giả sử API cần lấy 50 đơn hàng mới nhất của một tenant theo trạng thái. Khi dữ liệu còn nhỏ, truy vấn phản hồi nhanh; sau khi bảng tăng trưởng, p95 tăng và I/O đọc cũng tăng.

Truy vấn minh họa:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
ORDER BY created_at DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Quy trình điều tra:

1. **Xác định phạm vi:** đo p50, p95, p99 và tần suất của truy vấn; chọn tenant và trạng thái đại diện, bao gồm cả trường hợp phổ biến và hiếm.
2. **Lấy kế hoạch:** xem hệ quản trị quét bảng hay chỉ mục, ước lượng số hàng, số hàng thực tế, số vòng lặp và bước sắp xếp.
3. **Kiểm tra thống kê:** xác định thống kê có cập nhật không, phân bố status có lệch không và số hàng của từng tenant có chênh lệch lớn không.
4. **Đưa ra giả thuyết:** nếu truy vấn đọc nhiều hàng trước khi lấy 50 hàng, một chỉ mục kết hợp theo tenant, status và thời gian có thể giảm lượng dữ liệu cần đọc.
5. **Thử một thay đổi:** tạo chỉ mục ứng viên trong môi trường phù hợp, kiểm tra kế hoạch mới và đo lại với cùng bộ tham số.
6. **Đo tác động phụ:** kiểm tra thời gian và thông lượng ghi vào orders, dung lượng chỉ mục, hoạt động bảo trì và các truy vấn khác dùng cùng bảng.
7. **Quyết định:** giữ thay đổi khi lợi ích trên workload quan trọng lớn hơn chi phí và không vi phạm mục tiêu vận hành; nếu không, quay lại baseline và thử giả thuyết khác.

Nếu kế hoạch mới vẫn quét nhiều hàng, hãy xem lại độ chọn lọc, thứ tự cột, thống kê và việc truy vấn có thực sự cần nhiều dữ liệu hay không. Nếu truy vấn nhanh hơn nhưng ghi chậm đi đáng kể, cần đánh giá tổng tải đọc/ghi thay vì chỉ nhìn thời gian API. Nếu độ trễ chỉ tăng khi nhiều giao dịch cùng chạy, nguyên nhân có thể là tranh chấp hoặc bão hòa tài nguyên chứ không phải thiếu chỉ mục.

## 12. Kiểm chứng thay đổi như một thí nghiệm

Một lần tối ưu chỉ được xem là thành công khi kết quả được đo trong điều kiện so sánh hợp lý và không tạo hồi quy quan trọng.

Quy trình kiểm chứng nên gồm:

1. Ghi lại baseline và giả thuyết trước khi thay đổi.
2. Chỉ thay đổi một yếu tố chính trong mỗi lượt thử, chẳng hạn một chỉ mục, một cách viết SQL hoặc một cấu hình.
3. Dùng cùng tập dữ liệu, tham số đại diện, mức đồng thời và khoảng đo. Ghi rõ khác biệt về cache nóng/lạnh và thời điểm đo.
4. So sánh p50, p95, p99, thông lượng, lỗi, timeout, CPU, bộ nhớ, I/O, thời gian chờ khóa và chi phí ghi.
5. Kiểm tra tính đúng đắn của kết quả, ràng buộc, thứ tự và hành vi giao dịch.
6. Quan sát đủ lâu để thấy tác động đến tải nền, tác vụ bảo trì và các truy vấn liên quan.
7. Lưu lại kế hoạch thực thi và cấu hình trước/sau để có thể giải thích kết quả và tái hiện phép thử.

Có thể dùng triển khai theo giai đoạn hoặc tỷ lệ tải nhỏ để giảm phạm vi ảnh hưởng khi môi trường hỗ trợ. Đặt trước ngưỡng dừng và cách quay lui, ví dụ p99 tăng vượt ngưỡng, tỷ lệ lỗi tăng, thông lượng ghi giảm mạnh hoặc xuất hiện deadlock mới. Với chỉ mục và cấu hình, hãy biết rõ thao tác hoàn tác, thời gian thực hiện và ảnh hưởng đến tải trước khi triển khai diện rộng.

Không so sánh một lần chạy cache lạnh với một lần chạy cache nóng rồi kết luận thay đổi đã cải thiện. Hãy đo nhiều lần, dùng cùng điều kiện, tách riêng các trạng thái cache nếu cả hai đều quan trọng và xem phân vị thay vì chỉ dựa vào trung bình. Nếu workload biến động theo thời gian, cần so sánh các khoảng có đặc điểm tải tương đương hoặc dùng thử nghiệm có đối chứng.

## 13. Checklist khi bắt đầu một nhiệm vụ tối ưu

- [ ] Mục tiêu hiệu năng và giới hạn chấp nhận được đã rõ ràng.
- [ ] Workload, dữ liệu, tham số và mức đồng thời đại diện đã được mô tả.
- [ ] Có baseline gồm độ trễ phân vị, thông lượng, lỗi và tài nguyên.
- [ ] Đã xác định truy vấn hoặc nhóm thao tác gây tác động đáng kể.
- [ ] Kế hoạch thực thi, thống kê và số liệu thực tế đã được kiểm tra.
- [ ] Giả thuyết nêu rõ nguyên nhân, bằng chứng và kết quả mong đợi.
- [ ] Lợi ích của chỉ mục hoặc thay đổi SQL được cân nhắc cùng chi phí ghi, bộ nhớ và lưu trữ.
- [ ] Tranh chấp khóa, I/O, CPU, bộ nhớ và hàng đợi kết nối đã được phân biệt.
- [ ] Thay đổi được kiểm tra trên tải đại diện và kết quả dữ liệu vẫn đúng.
- [ ] Có số liệu sau thay đổi, ngưỡng dừng và phương án quay lui.

## 14. Nguyên tắc cần ghi nhớ

Tối ưu hiệu năng cơ sở dữ liệu là công việc dựa trên bằng chứng và luôn gắn với workload cụ thể. Đo trước để biết vấn đề nằm ở đâu; đọc kế hoạch và thống kê để hiểu hệ quản trị đang làm gì; xem xét cơ chế truy cập, khóa và tài nguyên để tìm nguyên nhân; thử một thay đổi có giả thuyết; rồi đo lại cả lợi ích lẫn chi phí phụ.

Không có chỉ mục, cách viết SQL, mức bộ nhớ hay mẹo cấu hình nào luôn đúng cho mọi hệ thống. Một lựa chọn tốt phải cải thiện mục tiêu đã xác định, giữ nguyên tính đúng đắn và hoạt động ổn định dưới tải thực tế.
