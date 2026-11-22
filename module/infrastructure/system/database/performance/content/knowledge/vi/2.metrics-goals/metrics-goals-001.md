# Độ trễ trung bình, trung vị và các phân vị p95, p99

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt độ trễ trung bình, trung vị và các phân vị p95, p99.
- Chọn chỉ số phù hợp để mô tả trải nghiệm điển hình và phần đuôi chậm của tải cơ sở dữ liệu.
- Đọc số liệu theo đúng phạm vi đo, cửa sổ thời gian và số lượng mẫu.
- Dùng các chỉ số độ trễ để xác định điểm cần điều tra và kiểm chứng hiệu quả của một thay đổi tối ưu.

## 1. Độ trễ là gì?

Độ trễ (latency) là khoảng thời gian từ một mốc bắt đầu đến một mốc kết thúc đã xác định. Với cơ sở dữ liệu, mốc đo có thể là thời gian một câu SQL chạy trong máy chủ, thời gian một giao dịch hoàn tất, hoặc thời gian ứng dụng chờ nhận kết quả từ cơ sở dữ liệu.

Trước khi đọc bất kỳ con số nào, cần xác định rõ phạm vi đo:

- **Độ trễ truy vấn tại máy chủ cơ sở dữ liệu** thường phản ánh thời gian thực thi và các khoảng chờ được bộ máy ghi nhận. Phạm vi cụ thể tùy hệ quản trị và công cụ đo.
- **Độ trễ giao dịch** bao gồm nhiều câu lệnh, thời gian chờ khóa, xử lý và commit hoặc rollback.
- **Độ trễ đầu cuối tại ứng dụng** có thể bao gồm thời gian chờ connection pool, hàng đợi trong ứng dụng, mạng, thực thi SQL và xử lý kết quả.

Ba loại số liệu này trả lời những câu hỏi khác nhau. Nếu người dùng phải chờ 800 ms nhưng truy vấn chỉ chạy 100 ms, tối ưu riêng câu SQL có thể không giải quyết được phần lớn thời gian chờ. Ngược lại, số liệu đầu cuối tăng chưa đủ chứng minh máy chủ cơ sở dữ liệu là nút thắt.

Độ trễ thường được ghi bằng mili giây (ms). Hãy dùng cùng đơn vị, cùng điểm bắt đầu và điểm kết thúc khi so sánh. Một phép đo chỉ có ý nghĩa khi biết nó đang đo điều gì.

## 2. Bốn chỉ số cần đọc

Giả sử ta thu thập thời gian hoàn tất của nhiều lần thực hiện cùng một loại thao tác. Mỗi lần thực hiện tạo ra một mẫu độ trễ. Từ tập mẫu đó, ta có thể tính trung bình, trung vị và các phân vị.

| Chỉ số | Ý nghĩa | Câu hỏi được trả lời |
| --- | --- | --- |
| Trung bình (mean, avg) | Tổng độ trễ của các mẫu chia cho số mẫu | Mỗi thao tác tốn bao nhiêu thời gian nếu lấy trung bình? |
| Trung vị (median, p50) | Giá trị ở giữa khi sắp xếp các mẫu tăng dần | Một thao tác điển hình mất bao lâu? |
| p95 | Ngưỡng mà ít nhất khoảng 95% mẫu không vượt quá | Phần lớn thao tác, kể cả nhóm chậm hơn thông thường, có đáp ứng tốt không? |
| p99 | Ngưỡng mà ít nhất khoảng 99% mẫu không vượt quá | Nhóm thao tác rất chậm có đang ảnh hưởng đến một phần nhỏ người dùng không? |

Trung bình là phép tính cộng tất cả độ trễ rồi chia cho số mẫu. Nó nhạy với các giá trị rất lớn. Một vài truy vấn mất nhiều giây có thể kéo trung bình lên đáng kể dù hầu hết truy vấn vẫn nhanh.

Trung vị là phân vị thứ 50, thường ký hiệu p50. Một nửa số mẫu nằm ở hoặc dưới giá trị này và một nửa nằm ở hoặc trên giá trị này, với khác biệt nhỏ tùy quy tắc xử lý khi số mẫu chẵn hoặc có nhiều giá trị bằng nhau. Trung vị mô tả trải nghiệm ở giữa phân phối và ít bị một số ngoại lệ chi phối hơn trung bình.

p95 là phân vị thứ 95. Nếu p95 bằng 180 ms, có thể hiểu rằng ít nhất khoảng 95% mẫu có độ trễ không quá 180 ms; phần còn lại nằm ở phía đuôi chậm hơn. p99 được hiểu tương tự ở mức 99%. Đây là các ngưỡng phân vị, không phải thời gian tối đa: luôn có thể tồn tại mẫu chậm hơn p99.

Do cách nội suy và quy tắc xếp hạng khác nhau giữa các thư viện, cơ sở dữ liệu và hệ thống giám sát, kết quả ở ranh giới phân vị có thể chênh nhẹ. Khi so sánh các hệ thống, hãy dùng cùng phương pháp tính hoặc cùng loại histogram.

## 3. Ví dụ: vì sao trung bình không kể hết câu chuyện?

Giả sử trong một cửa sổ đo có 1.000 lần thực hiện cùng một thao tác đọc dữ liệu:

| Số lần | Độ trễ mỗi lần |
| ---: | ---: |
| 940 | 20 ms |
| 40 | 80 ms |
| 15 | 250 ms |
| 5 | 2.000 ms |

Từ phân phối này:

- **Trung vị p50 = 20 ms** vì mẫu ở giữa nằm trong nhóm 940 lần chạy mất 20 ms.
- **p95 xấp xỉ 80 ms** vì vị trí quanh mẫu thứ 950 thuộc nhóm 80 ms.
- **p99 xấp xỉ 250 ms** vì vị trí quanh mẫu thứ 990 thuộc nhóm 250 ms.
- **p99.9 xấp xỉ 2.000 ms** vì các mẫu ở cuối phân phối thuộc nhóm mất 2 giây.
- **Trung bình = 35,75 ms**, tính bằng `(940 × 20 + 40 × 80 + 15 × 250 + 5 × 2000) / 1000`.

Phần lớn thao tác chỉ mất 20 ms, nhưng vẫn có một nhóm nhỏ phải chờ đến 2 giây. Trung bình 35,75 ms không cho biết rõ sự khác biệt đó. p50 cho thấy trải nghiệm điển hình, còn p95 và p99 giúp nhìn thấy phần đuôi chậm.

Ví dụ này cũng cho thấy p95 hoặc p99 không nhất thiết có đúng 5% hoặc 1% mẫu chậm hơn ngưỡng. Khi nhiều mẫu có cùng độ trễ, tỷ lệ thực tế ở phía trên ngưỡng có thể nhỏ hơn; cách nội suy cũng có thể làm giá trị phân vị khác nhau đôi chút.

## 4. Vì sao hiệu năng cơ sở dữ liệu cần theo dõi p95 và p99?

Thời gian truy vấn thường không phân bố đều. Một câu SQL có thể chạy rất nhanh khi dữ liệu nằm trong bộ nhớ đệm, nhưng chậm hơn khi phải đọc đĩa. Một giao dịch có thể hoàn tất ngay khi không tranh chấp, nhưng phải chờ khóa khi nhiều phiên cùng cập nhật một hàng. Một kế hoạch thực thi có thể hiệu quả với bộ lọc phổ biến nhưng rất tốn kém với một giá trị hiếm.

Những trường hợp này tạo ra phần đuôi chậm của phân phối. Nếu chỉ theo dõi trung bình hoặc trung vị, nhóm truy vấn chậm có thể bị che khuất. p95 và p99 giúp nhận ra các vấn đề như:

- Truy vấn thỉnh thoảng đọc nhiều trang dữ liệu do thiếu chỉ mục hoặc chọn kế hoạch thực thi không phù hợp.
- Tranh chấp khóa khiến một số giao dịch phải chờ lâu trong khi các giao dịch khác vẫn hoàn tất nhanh.
- Độ trễ I/O tăng khi bộ nhớ đệm không đáp ứng được tập dữ liệu hoạt động hoặc lưu trữ bị quá tải.
- Connection pool hoặc hàng đợi yêu cầu bị bão hòa khi tải đồng thời tăng.
- Thống kê dữ liệu cũ khiến bộ tối ưu chọn kế hoạch thực thi kém cho một nhóm tham số.
- Một truy vấn nền, tác vụ bảo trì hoặc đợt ghi dữ liệu lớn cạnh tranh CPU, bộ nhớ hay băng thông lưu trữ với truy vấn phục vụ ứng dụng.

Không nên kết luận nguyên nhân chỉ từ một phân vị. p99 tăng là tín hiệu để điều tra; cần đối chiếu với kế hoạch thực thi, thống kê truy vấn, sự kiện chờ, khóa, bộ nhớ đệm, CPU và độ trễ lưu trữ để xác định nguyên nhân.

## 5. Đọc các chỉ số cùng nhau

Đọc đồng thời trung bình, p50, p95 và p99 giúp phân biệt thay đổi trên toàn bộ tải với vấn đề chỉ xuất hiện ở một phần nhỏ yêu cầu.

| Hiện tượng | Cách diễn giải ban đầu | Hướng điều tra
| --- | --- | --- |
| Trung bình, p50, p95 và p99 cùng tăng | Nhiều thao tác đang chậm hơn; có thể tài nguyên hoặc toàn bộ đường xử lý bị quá tải | Kiểm tra thông lượng, CPU, I/O, hàng đợi, connection pool và tải đồng thời |
| p50 ổn định nhưng p95 hoặc p99 tăng | Một nhóm nhỏ thao tác đang chậm bất thường | Phân nhóm truy vấn; kiểm tra truy vấn chậm, khóa, cache miss và thay đổi kế hoạch thực thi |
| Trung bình cao hơn nhiều so với p50 | Một số mẫu rất chậm đang kéo trung bình lên | Tìm ngoại lệ và truy vấn có độ trễ cực lớn; xem p95, p99 và p99.9 |
| p95 cải thiện nhưng p99 xấu đi | Phần lớn mẫu tốt hơn nhưng đuôi rất chậm có thể nặng hơn | Kiểm tra mẫu cực chậm, timeout, tranh chấp và thay đổi phân bố tải |
| p50, p95 và p99 tăng cùng lúc với thông lượng | Hệ thống có thể tiến gần hoặc vượt giới hạn phục vụ | Kiểm tra điểm bão hòa, thời gian chờ tài nguyên và khả năng mở rộng |

Đây là các giả thuyết khởi đầu. Hãy xác nhận bằng dữ liệu theo từng loại thao tác và cùng cửa sổ thời gian. Một phân vị tăng trong lúc lưu lượng tăng mạnh có thể là hệ quả của tải, còn phân vị tăng khi tải không đổi có thể gợi ý một thay đổi về dữ liệu, kế hoạch thực thi hoặc môi trường.

## 6. Chọn phạm vi đo và cách thu thập

### Đo theo nhóm thao tác

Không nên gộp mọi truy vấn vào một phân phối duy nhất nếu chúng có mục đích và đặc tính khác nhau. Một truy vấn tra cứu theo khóa chính thường có độ trễ kỳ vọng khác truy vấn báo cáo quét hàng triệu dòng. Hãy phân nhóm theo endpoint, loại giao dịch hoặc mẫu truy vấn đã chuẩn hóa.

Với cơ sở dữ liệu, các nhóm hữu ích có thể là:

- Đọc một bản ghi theo khóa chính.
- Tra cứu danh sách có phân trang.
- Tìm kiếm theo nhiều điều kiện.
- Ghi hoặc cập nhật một bản ghi.
- Giao dịch gồm nhiều câu lệnh.
- Truy vấn báo cáo hoặc tác vụ nền.

Việc phân nhóm giúp so sánh các thao tác tương đương và tìm đúng nhóm gây ra độ trễ cao. Tránh gắn nhãn theo giá trị tham số, mã người dùng hoặc mã bản ghi tùy ý vì số lượng nhãn có thể tăng không kiểm soát và làm hệ thống giám sát tốn nhiều bộ nhớ.

### Ghi nhận đủ bối cảnh

Mỗi báo cáo độ trễ nên đi kèm ít nhất các thông tin sau:

- Cửa sổ thời gian và số lượng mẫu.
- Phạm vi đo: truy vấn, giao dịch hay yêu cầu đầu cuối.
- Loại thao tác hoặc nhóm truy vấn.
- Thông lượng trong cùng cửa sổ, chẳng hạn số truy vấn hoặc giao dịch mỗi giây.
- Tỷ lệ lỗi, timeout và yêu cầu bị hủy.
- Mức tải đồng thời, kích thước dữ liệu và trạng thái cache nếu có thể xác định.
- Phiên bản hệ quản trị, cấu hình quan trọng và dấu vân tay kế hoạch thực thi khi cần so sánh.

Không bỏ các yêu cầu timeout hoặc lỗi khỏi báo cáo mà không ghi nhận riêng. Nếu chỉ tính độ trễ của các yêu cầu thành công, hệ thống có thể trông nhanh hơn trong khi người dùng thực tế đang gặp nhiều lỗi hoặc phải chờ đến khi timeout.

### Dùng histogram để theo dõi phân vị

Trong hệ thống giám sát sản xuất, histogram thường phù hợp để lưu phân bố độ trễ theo các khoảng. Bộ thu thập tăng số mẫu trong từng khoảng; từ các số đếm này, hệ thống có thể ước lượng p50, p95 và p99 theo cửa sổ thời gian.

Khi tổng hợp nhiều máy chủ cơ sở dữ liệu hoặc nhiều tiến trình, hãy gộp số đếm của các bucket tương ứng rồi tính phân vị trên phân phối đã gộp. Không lấy trung bình p95 của từng máy chủ để gọi đó là p95 toàn hệ thống. Phân vị không phải phép tính có tính cộng gộp như tổng hoặc trung bình có trọng số.

Với dữ liệu mẫu thô, có thể tính phân vị trực tiếp. Ví dụ dưới đây dùng PostgreSQL và giả định bảng `query_latency_samples` lưu một mẫu cho mỗi lần thực hiện; đây là ví dụ minh họa, không phải bảng hệ thống có sẵn:

```sql
SELECT
    COUNT(*) AS sample_count,
    AVG(latency_ms) AS avg_ms,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_ms
FROM query_latency_samples
WHERE measured_at >= NOW() - INTERVAL '15 minutes'
  AND query_group = 'orders_by_customer';
```

`percentile_cont` tính phân vị liên tục và có thể nội suy giữa hai mẫu lân cận. Nếu dùng một hệ quản trị khác, hãy kiểm tra hàm phân vị và cách tính tương ứng. Việc lưu từng mẫu trong bảng phù hợp cho phân tích hoặc thử nghiệm có quy mô kiểm soát; hệ thống sản xuất thường dùng telemetry hoặc histogram chuyên dụng để tránh tạo thêm tải ghi không cần thiết.

## 7. Xây dựng mục tiêu độ trễ

Mục tiêu cần gắn với thao tác mà người dùng hoặc hệ thống thực sự quan tâm. Một mục tiêu chung cho toàn bộ cơ sở dữ liệu thường khó hành động vì các nhóm truy vấn có đặc tính khác nhau.

Ví dụ minh họa cho một thao tác tra cứu phục vụ giao diện:

- p95 không vượt quá 200 ms trong cửa sổ 15 phút.
- p99 không vượt quá 500 ms trong cùng cửa sổ.
- Tỷ lệ lỗi và timeout được theo dõi cùng với độ trễ.
- Các mục tiêu được đánh giá khi thông lượng và mức tải đồng thời đạt mức dự kiến.

Các con số trên chỉ là ví dụ. Mục tiêu thực tế phải dựa trên yêu cầu sản phẩm, ngân sách thời gian của toàn bộ request, đặc điểm dữ liệu, khả năng hạ tầng và đường cơ sở đã đo. Nếu ứng dụng có ngân sách 500 ms cho toàn bộ request, không thể mặc định dành toàn bộ 500 ms cho truy vấn cơ sở dữ liệu vì còn thời gian mạng, xử lý ứng dụng và các dịch vụ phụ thuộc.

Nên đặt mục tiêu riêng cho nhóm đọc, ghi và giao dịch quan trọng khi chúng có yêu cầu khác nhau. Đồng thời theo dõi thông lượng và tỷ lệ lỗi để tránh đạt độ trễ thấp bằng cách từ chối bớt yêu cầu hoặc giảm tải theo cách làm sai hành vi sản phẩm.

## 8. Quy trình đo và kiểm chứng sau tối ưu

1. **Chọn thao tác và phạm vi đo.** Xác định nhóm truy vấn hoặc giao dịch, điểm bắt đầu và kết thúc, đơn vị đo, cửa sổ thời gian và mục tiêu cần đạt.
2. **Thu thập đường cơ sở.** Ghi nhận số mẫu, avg, p50, p95, p99, thông lượng, lỗi, timeout và mức tải. Dùng dữ liệu đại diện cho kích thước dữ liệu và kiểu truy cập thực tế.
3. **Tìm thời điểm và nhóm gây chậm.** So sánh theo thời gian, nhóm truy vấn và máy chủ. Đối chiếu với thống kê truy vấn, kế hoạch thực thi, số dòng đọc, cache hit, I/O, CPU, sự kiện chờ và thời gian chờ khóa.
4. **Đặt giả thuyết có thể kiểm chứng.** Ví dụ: truy vấn tìm đơn hàng đang quét nhiều dòng; giao dịch cập nhật cùng một bản ghi gây tranh chấp; hoặc pool kết nối tạo hàng đợi trước khi truy vấn bắt đầu.
5. **Thực hiện thay đổi có kiểm soát.** Điều chỉnh câu SQL, chỉ mục, cách phân trang, kích thước batch hoặc mức đồng thời. Ghi lại thay đổi và chỉ thay một nhóm yếu tố mỗi lần nếu cần xác định quan hệ nguyên nhân.
6. **Đo lại trong điều kiện tương đương.** Dùng cùng nhóm thao tác, dữ liệu, thời lượng, thông lượng và mức đồng thời. Kiểm tra trạng thái cache và việc làm nóng hệ thống để tránh so sánh một lần chạy cache nóng với một lần chạy cache lạnh.
7. **Đánh giá cả lợi ích và chi phí.** Xác nhận p95, p99 và mục tiêu đã cải thiện; đồng thời kiểm tra throughput, tỷ lệ lỗi, thời gian ghi, dung lượng chỉ mục, tải I/O và các nhóm truy vấn khác.
8. **Theo dõi sau khi áp dụng.** Quan sát nhiều cửa sổ tải thực tế để phát hiện hồi quy do phân bố dữ liệu, tham số truy vấn hoặc mức đồng thời thay đổi.

Một thay đổi chỉ được xem là có hiệu quả khi cải thiện được xác nhận bằng phép đo tương đương và không tạo ra suy giảm không chấp nhận được ở các chỉ số liên quan. Ví dụ, thêm chỉ mục có thể giảm p99 của truy vấn đọc nhưng làm tăng thời gian ghi và dung lượng lưu trữ; cần đo cả hai phía.

## 9. Những sai lầm thường gặp

- **Chỉ nhìn trung bình.** Trung bình có thể che khuất nhóm truy vấn chậm. Hãy xem thêm p50, p95 và p99.
- **Coi p99 là độ trễ tối đa.** Một phần nhỏ mẫu vẫn có thể chậm hơn p99; hãy kiểm tra timeout và các mẫu cực trị.
- **Báo cáo phân vị mà không có số mẫu.** p99 từ vài chục quan sát không ổn định và có thể chỉ phản ánh một mẫu đơn lẻ.
- **So sánh hai cửa sổ tải khác nhau.** Lưu lượng, mức đồng thời, kích thước dữ liệu và cache có thể làm kết quả thay đổi.
- **Gộp các loại truy vấn không tương đương.** Một nhóm truy vấn nhanh có thể che lấp nhóm truy vấn quan trọng nhưng chậm.
- **Lấy trung bình các p95 theo máy chủ.** Cách này không tạo ra p95 của toàn hệ thống; cần gộp phân phối hoặc histogram.
- **Nhầm độ trễ truy vấn với độ trễ đầu cuối.** Hai số đo có phạm vi khác nhau và cần được đặt tên rõ ràng.
- **Bỏ qua lỗi và timeout.** Chỉ đo các yêu cầu thành công có thể làm báo cáo đẹp giả tạo.
- **Tối ưu một phân vị mà bỏ qua các chỉ số khác.** p95 giảm nhưng p99, lỗi, throughput hoặc thời gian ghi xấu đi vẫn là dấu hiệu cần điều tra.

## 10. Danh sách kiểm tra khi đọc một báo cáo độ trễ

- [ ] Đã xác định rõ phạm vi đo và điểm bắt đầu/kết thúc.
- [ ] Có avg, p50, p95 và p99 với cùng đơn vị.
- [ ] Có số lượng mẫu và cửa sổ thời gian.
- [ ] Đã phân nhóm các thao tác có đặc tính khác nhau.
- [ ] Có thông lượng, mức tải đồng thời, lỗi và timeout để đối chiếu.
- [ ] Phân vị được tính từ phân phối hoặc histogram phù hợp, không phải trung bình các phân vị con.
- [ ] Đã đối chiếu các đợt tăng độ trễ với kế hoạch thực thi, khóa, I/O, cache và tài nguyên.
- [ ] Phép đo trước và sau tối ưu được thực hiện trong điều kiện tương đương.

## Kết luận

Trung bình mô tả chi phí thời gian bình quân của các lần thực hiện; trung vị mô tả lần thực hiện ở giữa phân phối; p95 và p99 làm lộ rõ phần đuôi chậm. Khi tối ưu hiệu năng cơ sở dữ liệu, hãy đọc các chỉ số này cùng số mẫu, thông lượng, tỷ lệ lỗi và bối cảnh tải. Dùng chúng để tìm nhóm thao tác cần điều tra, sau đó xác nhận nguyên nhân bằng kế hoạch thực thi và số liệu tài nguyên. Cuối cùng, đo lại trong điều kiện tương đương để chứng minh thay đổi đã cải thiện trải nghiệm mà không chuyển chi phí sang phần khác của hệ thống.
