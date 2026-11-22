# Định luật Little: liên hệ thông lượng, độ trễ và số yêu cầu đang xử lý

## 1. Vì sao cần hiểu định luật Little?

Khi đánh giá hiệu năng cơ sở dữ liệu, ta thường theo dõi ba nhóm số liệu: thông lượng (throughput), độ trễ (latency) và số yêu cầu đang nằm trong hệ thống (concurrency hoặc số yêu cầu đồng thời). Ba đại lượng này liên hệ chặt chẽ với nhau. Nếu chỉ nhìn một đại lượng, ta dễ kết luận sai về khả năng phục vụ của cơ sở dữ liệu.

Ví dụ, một dịch vụ xử lý được nhiều truy vấn hơn mỗi giây nhưng thời gian chờ của mỗi truy vấn tăng mạnh. Thông lượng có thể đang tăng vì tải tăng, trong khi hàng đợi cũng dài hơn và người dùng phải chờ lâu hơn. Ngược lại, số truy vấn đang hoạt động thấp không nhất thiết chứng minh hệ thống còn dư năng lực: có thể ứng dụng đang gửi ít yêu cầu hoặc nhiều yêu cầu bị chặn trước khi đến cơ sở dữ liệu.

Định luật Little cung cấp một quan hệ định lượng để kiểm tra tính nhất quán giữa các số đo đó. Trong tối ưu hiệu năng cơ sở dữ liệu, ta dùng quan hệ này để ước lượng mức đồng thời trung bình, nhận biết hàng đợi tăng, đánh giá tải trên connection pool và xác định nơi cần đo sâu hơn.

## 2. Phát biểu và công thức

Định luật Little phát biểu rằng, trong một hệ thống ổn định, số phần tử trung bình bên trong hệ thống bằng tốc độ đi vào hệ thống nhân với thời gian trung bình một phần tử lưu lại trong hệ thống.

\[
L = \lambda W
\]

Trong đó:

- **\(L\)** là số yêu cầu trung bình đang ở trong phạm vi hệ thống được xét. Đại lượng này có đơn vị là yêu cầu, giao dịch hoặc kết nối.
- **\(\lambda\)** là thông lượng trung bình: số yêu cầu hoàn tất trong một đơn vị thời gian. Đơn vị thường là yêu cầu/giây hoặc giao dịch/giây.
- **\(W\)** là thời gian trung bình một yêu cầu ở trong phạm vi đó, tính cả thời gian chờ và thời gian được phục vụ nếu cả hai đều thuộc phạm vi đo. Đơn vị thường là giây.

Có thể biến đổi công thức để tìm đại lượng còn thiếu:

\[
W = \frac{L}{\lambda}, \qquad \lambda = \frac{L}{W}
\]

Điều kiện quan trọng là ba đại lượng phải mô tả **cùng một hệ thống, cùng một loại đơn vị công việc và cùng khoảng thời gian đo**. Không thể lấy thông lượng giao dịch mỗi giây, nhân với độ trễ của một câu SQL riêng lẻ, rồi so sánh với số kết nối đang mở nếu mỗi giao dịch phát sinh nhiều câu SQL và kết nối còn phục vụ các công việc khác.

### Ví dụ tính nhanh

Một dịch vụ gửi trung bình 240 truy vấn cơ sở dữ liệu mỗi giây. Thời gian trung bình từ lúc truy vấn đi vào phạm vi đo đến lúc hoàn tất là 50 ms, tức 0,05 giây.

\[
L = 240 \times 0{,}05 = 12
\]

Như vậy, trung bình có khoảng **12 truy vấn** đang nằm trong phạm vi đo tại một thời điểm. Đây là giá trị trung bình theo thời gian, không có nghĩa mọi thời điểm đều có đúng 12 truy vấn.

Nếu cùng hệ thống tăng lên 300 truy vấn/giây nhưng độ trễ trung bình tăng thành 200 ms (0,2 giây), ta có:

\[
L = 300 \times 0{,}2 = 60
\]

Thông lượng tăng 25%, nhưng số truy vấn trung bình trong hệ thống tăng từ 12 lên 60, tức gấp 5 lần. Sự gia tăng đồng thời này có thể làm tăng tranh chấp CPU, I/O, khóa giao dịch và bộ nhớ. Chỉ nhìn thông lượng sẽ bỏ qua tín hiệu quan trọng về độ trễ và hàng đợi.

## 3. Xác định đúng phạm vi đo trong hệ thống cơ sở dữ liệu

Định luật Little đúng với một phạm vi được định nghĩa rõ ràng. Một yêu cầu có thể đi qua nhiều chặng trước khi hoàn tất:

1. Ứng dụng tạo yêu cầu và chờ lấy kết nối từ connection pool.
2. Yêu cầu được gửi qua mạng đến máy chủ cơ sở dữ liệu.
3. Máy chủ phân tích, lập kế hoạch và thực thi câu lệnh.
4. Giao dịch có thể phải chờ khóa, đọc dữ liệu từ bộ nhớ hoặc đĩa, ghi log và đồng bộ dữ liệu.
5. Kết quả được trả về ứng dụng, sau đó kết nối được giải phóng.

Ta có thể áp dụng công thức cho toàn bộ hành trình hoặc cho từng chặng. Nhưng khi chọn một chặng, phải đo cả ba đại lượng trong chính chặng đó.

| Phạm vi | Thông lượng \(\lambda\) | Thời gian \(W\) | Số lượng trung bình \(L\) |
|---|---|---|---|
| Toàn bộ yêu cầu tại ứng dụng | Yêu cầu hoàn tất mỗi giây | Từ lúc ứng dụng nhận yêu cầu đến lúc trả kết quả | Yêu cầu đang xử lý hoặc chờ trong ứng dụng |
| Hàng đợi connection pool | Yêu cầu được cấp kết nối mỗi giây | Thời gian chờ lấy kết nối | Yêu cầu đang chờ cấp kết nối |
| Phần thực thi tại cơ sở dữ liệu | Câu lệnh hoặc giao dịch hoàn tất mỗi giây | Thời gian từ khi vào đến khi rời phạm vi thực thi | Câu lệnh hoặc giao dịch đang thực thi/chờ bên trong phạm vi |
| Kết nối đang được mượn | Lượt mượn kết nối hoàn tất mỗi giây | Thời gian một lượt mượn giữ kết nối | Số kết nối trung bình đang được sử dụng |

Một số hệ thống có thể ghi nhận truy vấn đang chạy nhưng không ghi nhận yêu cầu chờ ở connection pool. Khi đó số truy vấn đang chạy chỉ mô tả phần bên trong máy chủ cơ sở dữ liệu, không đại diện cho toàn bộ yêu cầu mà người dùng đang chờ. Cần đo hàng đợi ở ứng dụng riêng.

Tương tự, số kết nối TCP đang mở không đồng nghĩa với số kết nối đang bận. Kết nối nhàn rỗi trong pool không phải là một truy vấn đang thực thi. Khi dùng \(L\) để phân tích tải, hãy chọn đúng đại lượng: số yêu cầu đang chờ, số truy vấn đang chạy, số giao dịch đang mở hay số kết nối đang được mượn.

## 4. Điều kiện áp dụng và cách hiểu số trung bình

Định luật Little áp dụng cho hệ thống có hành vi ổn định trong khoảng quan sát đủ dài: tốc độ công việc đi vào và đi ra cân bằng về trung bình, hàng đợi không tăng vô hạn và các đại lượng trung bình có ý nghĩa hữu hạn. Trong thực tế, tải cơ sở dữ liệu dao động theo thời gian nên ta thường chọn cửa sổ đo đại diện, chẳng hạn vài phút trong một giai đoạn tải tương đối ổn định.

Nếu lượng yêu cầu đến liên tục cao hơn lượng hệ thống xử lý được, hàng đợi sẽ tích lũy. Khi đó hệ thống chưa ở trạng thái ổn định; lấy tốc độ đến nhân với độ trễ trên một cửa sổ ngắn có thể cho kết quả khó diễn giải. Hãy quan sát riêng tốc độ đến, tốc độ hoàn tất và độ dài hàng đợi. Nếu hàng đợi vẫn tăng qua các cửa sổ liên tiếp, đó là dấu hiệu tải đang vượt khả năng phục vụ trong giai đoạn ấy.

Các đại lượng trong công thức là **giá trị trung bình**, không phải phân vị. Định luật dùng độ trễ trung bình \(W\), không dùng p95 hoặc p99 thay thế trực tiếp. Phân vị vẫn rất cần thiết để hiểu trải nghiệm của các yêu cầu chậm, nhưng phải phân tích song song với công thức trung bình.

Một điểm đo tức thời cũng không đủ để đại diện cho \(L\). Số truy vấn đang chạy có thể tăng giảm mạnh theo từng mili giây. Nên dùng trung bình theo thời gian hoặc công cụ giám sát có khả năng tổng hợp số lượng đồng thời trong cả cửa sổ đo.

## 5. Áp dụng để đọc tải connection pool

Giả sử ứng dụng hoàn tất trung bình 180 giao dịch mỗi giây. Mỗi giao dịch giữ một kết nối trong trung bình 120 ms, tương đương 0,12 giây. Nếu phạm vi đo chỉ là thời gian kết nối được mượn, số kết nối bận trung bình ước tính là:

\[
L_{busy} = 180 \times 0{,}12 = 21{,}6
\]

Với pool có 30 kết nối, mức sử dụng trung bình theo phép tính này là:

\[
U \approx \frac{21{,}6}{30} = 0{,}72 = 72\%
\]

Con số 72% là mức trung bình trong cửa sổ đo, không bảo đảm pool luôn còn 8 kết nối trống. Tải đến theo đợt, thời gian giữ kết nối biến động, truy vấn chậm hoặc giao dịch chờ khóa có thể khiến pool đầy trong một số thời điểm.

Giả sử mỗi giao dịch còn chờ trung bình 40 ms trong hàng đợi pool trước khi được cấp kết nối. Khi xét toàn bộ phạm vi từ lúc vào hàng đợi đến khi trả kết nối, thời gian trung bình là 160 ms. Khi đó:

\[
L_{total} = 180 \times 0{,}16 = 28{,}8
\]

Có thể diễn giải gần đúng thành 21,6 lượt đang giữ kết nối và 7,2 lượt đang chờ cấp kết nối, nếu hai giai đoạn được đo nhất quán và không chồng lấn. Ví dụ này cho thấy chỉ xem số kết nối bận có thể bỏ sót hàng đợi ở ứng dụng.

Nếu pool thường xuyên chạm giới hạn và thời gian chờ cấp kết nối tăng, hãy tìm nguyên nhân khiến kết nối bị giữ lâu: câu SQL chậm, giao dịch kéo dài, khóa bị tranh chấp, thao tác mạng trong khi vẫn giữ giao dịch hoặc kết nối không được trả về đúng lúc. Tăng kích thước pool ngay lập tức có thể đẩy nhiều truy vấn hơn vào cơ sở dữ liệu và làm CPU, I/O hoặc tranh chấp khóa nặng thêm.

## 6. Dùng ba đại lượng để nhận diện nút thắt

Hãy đọc thông lượng, độ trễ và số lượng đồng thời cùng nhau. Một số mẫu hình thường gặp:

| Quan sát theo thời gian | Cách diễn giải cần kiểm chứng |
|---|---|
| Thông lượng tăng, độ trễ ổn định, số yêu cầu đồng thời tăng tương ứng | Hệ thống đang phục vụ thêm tải mà chưa thấy độ trễ trung bình xấu đi rõ rệt |
| Thông lượng gần như đi ngang, độ trễ tăng, số yêu cầu đồng thời tăng | Có thể đã chạm giới hạn tài nguyên hoặc xuất hiện hàng đợi; kiểm tra CPU, I/O, khóa và pool |
| Thông lượng giảm, độ trễ tăng, hàng đợi tiếp tục dài ra | Khả năng phục vụ suy giảm hoặc một nhóm yêu cầu chậm đang giữ tài nguyên lâu |
| Thông lượng thấp, độ trễ thấp, số yêu cầu đồng thời thấp | Có thể đơn giản là tải đến thấp; chưa đủ bằng chứng kết luận hệ thống còn dư công suất |
| Số kết nối mở cao nhưng số kết nối đang dùng thấp | Pool đang giữ nhiều kết nối nhàn rỗi; không nên xem toàn bộ kết nối mở là tải thực thi |

Định luật Little giúp đặt câu hỏi đúng, nhưng không tự chỉ ra nguyên nhân gốc. Khi thấy \(L\) tăng do \(W\) tăng, hãy chia độ trễ thành các thành phần phù hợp: chờ pool, chờ mạng, lập kế hoạch, thực thi, chờ khóa, đọc/ghi I/O và trả kết quả. Sau đó đối chiếu với kế hoạch thực thi, thống kê truy cập, mức sử dụng bộ nhớ, CPU, I/O và số liệu giao dịch.

Ví dụ, nếu thời gian chờ khóa tăng thì thêm chỉ mục chưa chắc giải quyết được vấn đề; cần xác định giao dịch nào giữ khóa lâu và thứ tự truy cập dữ liệu. Nếu thời gian đọc đĩa tăng cùng với độ trễ truy vấn, cần xem lại kế hoạch thực thi, tính chọn lọc của chỉ mục, kích thước working set và áp lực bộ nhớ. Nếu hàng đợi pool tăng trong khi máy chủ cơ sở dữ liệu còn ít hoạt động, hãy kiểm tra giới hạn pool, rò rỉ kết nối và cách ứng dụng quản lý giao dịch.

## 7. Quy trình đo và kiểm chứng khi tối ưu

Có thể áp dụng quy trình sau trong một lần điều tra hiệu năng:

1. **Chọn đơn vị công việc.** Quyết định đang đo yêu cầu HTTP, giao dịch, câu SQL hay lượt mượn kết nối. Ghi rõ một giao dịch có thể phát sinh bao nhiêu câu SQL.
2. **Vẽ ranh giới đo.** Xác định điểm bắt đầu, điểm kết thúc và các hàng đợi nằm bên trong phạm vi. Tách riêng thời gian chờ pool khỏi thời gian thực thi trong cơ sở dữ liệu nếu cần.
3. **Thu thập cùng cửa sổ thời gian.** Đo thông lượng hoàn tất, độ trễ trung bình và số lượng đang ở trong phạm vi. Ghi thêm tốc độ yêu cầu đến để nhận biết hàng đợi đang tăng.
4. **Đồng bộ đơn vị.** Chuyển mili giây sang giây nếu thông lượng tính theo giây. Ví dụ, 75 ms phải đổi thành 0,075 giây trước khi tính.
5. **Tính và đối chiếu.** Tính \(L = \lambda W\), rồi so sánh với số lượng đồng thời đo được. Chênh lệch lớn có thể báo hiệu phạm vi đo không giống nhau, đơn vị không khớp, cửa sổ chưa ổn định hoặc số liệu được lấy mẫu khác cách.
6. **Tìm nguyên nhân ở đúng chặng.** Dùng log truy vấn, kế hoạch thực thi, thống kê, wait events, số liệu khóa, CPU, bộ nhớ, I/O và pool để xác định thời gian đang bị tiêu tốn ở đâu.
7. **Thay đổi có kiểm soát.** Chỉ điều chỉnh một nhóm yếu tố có giả thuyết rõ ràng, chẳng hạn sửa truy vấn, bổ sung hoặc thay đổi chỉ mục, rút ngắn giao dịch hay điều chỉnh pool.
8. **Đo lại với tải tương đương.** Giữ cùng kịch bản, dữ liệu, mức tải và cửa sổ đo. So sánh thông lượng, độ trễ trung bình, p95/p99, số yêu cầu đồng thời, hàng đợi và tài nguyên trước/sau thay đổi.

Một bảng ghi nhận ngắn giúp tránh kết luận dựa trên một con số riêng lẻ:

| Chỉ số | Trước điều chỉnh | Sau điều chỉnh | Ý nghĩa cần xem xét |
|---|---:|---:|---|
| Thông lượng hoàn tất (yêu cầu/giây) | 240 | 250 | Năng lực hoàn tất thay đổi bao nhiêu? |
| Độ trễ trung bình (ms) | 100 | 70 | Thời gian lưu lại trong phạm vi đo có giảm không? |
| \(L = \lambda W\) (yêu cầu) | 24 | 17,5 | Mức đồng thời trung bình ước tính thay đổi thế nào? |
| p95 (ms) | 280 | 190 | Nhóm yêu cầu chậm có cải thiện không? |
| Thời gian chờ pool (ms) | 35 | 12 | Phần chờ trước khi vào cơ sở dữ liệu thay đổi ra sao? |

Trong ví dụ, độ trễ trung bình sau điều chỉnh là 70 ms, tức 0,07 giây; do đó \(250 \times 0{,}07 = 17{,}5\) yêu cầu. Kết quả gợi ý số yêu cầu trung bình trong phạm vi đã giảm dù thông lượng tăng nhẹ. Tuy nhiên, cần xác nhận các số liệu dùng cùng phạm vi và cùng tải thử trước khi quy kết cải thiện cho thay đổi vừa thực hiện.

## 8. Những sai lầm thường gặp

- **Trộn đơn vị hoặc phạm vi:** nhân giao dịch/giây với thời gian của một câu SQL, rồi so với số kết nối. Hãy thống nhất đơn vị công việc và ranh giới đo trước khi tính.
- **Dùng p95 thay cho trung bình:** công thức sử dụng thời gian trung bình. Theo dõi p95/p99 riêng để đánh giá đuôi phân phối độ trễ.
- **Đồng nhất kết nối mở với truy vấn đồng thời:** kết nối có thể đang nhàn rỗi. Phân biệt kết nối mở, kết nối đang được mượn, truy vấn đang chạy và yêu cầu đang chờ.
- **Chỉ đo một thời điểm:** số lượng truy vấn tức thời biến động mạnh. Dùng trung bình theo thời gian trên cửa sổ có ý nghĩa.
- **Bỏ qua yêu cầu đang chờ:** nếu chỉ đo truy vấn đã vào máy chủ, hàng đợi ở ứng dụng hoặc proxy có thể bị bỏ sót.
- **Coi công thức là bằng chứng nguyên nhân:** \(L = \lambda W\) mô tả quan hệ giữa các trung bình; nó không xác định truy vấn nào chậm hay tài nguyên nào đang nghẽn.
- **Tăng pool chỉ vì pool đầy:** cần xác định thời gian giữ kết nối và năng lực phục vụ của máy chủ. Thêm kết nối có thể làm mức đồng thời tăng và khuếch đại tranh chấp.
- **So sánh hai cửa sổ tải khác nhau:** kết quả trước/sau chỉ có ý nghĩa khi điều kiện tải và cách đo tương đương.

## 9. Bài tập tự kiểm tra

**Bài 1.** Một hệ thống hoàn tất 400 truy vấn mỗi giây, độ trễ trung bình là 25 ms. Số truy vấn trung bình trong phạm vi đo là bao nhiêu?

*Gợi ý:* Đổi 25 ms thành 0,025 giây rồi tính \(L = \lambda W\). Kết quả là 10 truy vấn.

**Bài 2.** Một connection pool có 40 kết nối. Ở tải ổn định, ứng dụng hoàn tất 200 giao dịch mỗi giây và mỗi giao dịch giữ kết nối trung bình 100 ms. Số kết nối bận trung bình ước tính là bao nhiêu, và mức sử dụng trung bình theo phép tính này là bao nhiêu?

*Gợi ý:* \(L_{busy} = 200 \times 0{,}1 = 20\) kết nối; tỷ lệ so với pool là \(20/40 = 50\%\). Đây không phải cam kết rằng pool sẽ không bao giờ đầy trong các đợt tải cao.

**Bài 3.** Thông lượng gần như không đổi, độ trễ trung bình tăng gấp đôi và số yêu cầu đồng thời cũng tăng gần gấp đôi. Bạn nên kiểm tra những dữ liệu nào tiếp theo?

*Gợi ý:* Kiểm tra hàng đợi và thời gian chờ pool, thời gian thực thi truy vấn, wait events/khóa, CPU, I/O, bộ nhớ và các truy vấn có thời gian giữ kết nối dài. Dùng kế hoạch thực thi và thống kê để tìm nhóm truy vấn gây ra thay đổi.

## 10. Ghi nhớ khi vận hành

Định luật Little là phép kiểm tra nền tảng để nối ba câu hỏi: hệ thống hoàn tất bao nhiêu công việc mỗi giây, mỗi công việc ở trong hệ thống bao lâu và trung bình có bao nhiêu công việc đang chờ hoặc được xử lý. Trong phân tích hiệu năng cơ sở dữ liệu, giá trị của nó phụ thuộc vào việc định nghĩa đúng phạm vi, đo cùng cửa sổ thời gian và phân biệt rõ hàng đợi với phần thực thi.

Khi thông lượng, độ trễ và mức đồng thời được đọc cùng nhau, ta có cơ sở tốt hơn để nhận biết dấu hiệu bão hòa, xác định chặng cần điều tra và kiểm chứng tác động của một điều chỉnh. Hãy dùng công thức như một công cụ định lượng để định hướng việc đo đạc; kết luận nguyên nhân vẫn cần dựa trên kế hoạch thực thi, thống kê, khóa, bộ nhớ, I/O và dữ liệu vận hành thực tế.
