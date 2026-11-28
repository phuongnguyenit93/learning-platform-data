# Nhận biết tối ưu hóa sớm và thời điểm cần đổi cách biểu diễn

Một nhóm phát triển quản lý 300 bản ghi bằng mảng và tìm kiếm tuyến tính. Một thành viên đề xuất thay ngay bằng cấu trúc cây nhiều tầng vì “`O(log n)` tốt hơn `O(n)`”. Nhóm khác quản lý 2 triệu bản ghi, liên tục quét toàn bộ mảng để tìm một khóa, nhưng vẫn từ chối lập chỉ mục vì “đừng tối ưu hóa sớm”. Cả hai quyết định đều có thể sai: trường hợp đầu chưa có bằng chứng rằng việc đổi cấu trúc mang lại lợi ích; trường hợp sau có thể đang bỏ qua một nút thắt cổ chai đã biết.

**Tối ưu hóa sớm** (*premature optimization*) không đồng nghĩa với “tránh mọi cấu trúc dữ liệu hiệu quả”. Nó là việc **tăng độ phức tạp hoặc trả chi phí đáng kể để giải quyết vấn đề hiệu năng chưa được chứng minh, chưa đáng kể hoặc chưa đúng mục tiêu**. Ngược lại, **đổi cách biểu diễn dữ liệu có căn cứ** là khi yêu cầu, kích thước hoặc phép đo cho thấy cách hiện tại không còn phù hợp và phương án mới tạo ra lợi ích ròng.

Trong chương **Lựa chọn và thiết kế**, bài này hướng dẫn đánh giá thời điểm chuyển giữa mảng, bảng băm, cây tìm kiếm, queue, heap, trie và các biểu diễn đồ thị; đồng thời giải thích cách đo, bảo toàn bất biến, chuyển đổi dữ liệu và kiểm thử để tối ưu mà không làm sai kết quả.

## 1. Cần phân biệt tối ưu hóa sớm với thiết kế đúng ngay từ đầu

Trước khi đo hay lập chỉ mục, phải xác định **ngữ nghĩa và tải công việc**.

Một giải pháp đơn giản là tốt khi nó **đúng, đủ nhanh, đủ bộ nhớ, dễ kiểm thử và có thể thay thế nếu yêu cầu đổi**. Nhưng “đơn giản” không bắt buộc là “dùng mảng cho mọi thứ”. Nếu đề bài ngay từ đầu cần lấy cực tiểu từ hàng triệu phần tử hàng nghìn lần, chọn heap là quyết định thuật toán thông thường, không phải tối ưu hóa sớm. Nếu đề bài chỉ có vài chục mục và rất ít truy vấn, xây một hệ chỉ mục nhiều tầng có thể chưa cần thiết.

| Quyết định | Có thể hợp lý khi | Có thể là tối ưu hóa sớm khi |
| --- | --- | --- |
| Dùng `dict` theo ID thay vì quét list | Tra ID là thao tác thường xuyên, kích thước lớn, tính duy nhất đã rõ | Dữ liệu chỉ vài mục, dùng một lần, chi phí duy trì map lớn hơn lợi ích |
| Dùng cây tự cân bằng theo khóa | Cần `lowerBound`, truy vấn khoảng và cập nhật thường xuyên | Chỉ cần tra khóa chính xác và không cần thứ tự |
| Dùng heap cho tác vụ ưu tiên | Liên tục thêm và lấy phần tử có ưu tiên cao nhất | Chỉ cần tìm cực trị một lần trong tập nhỏ |
| Dùng trie cho tiền tố | Truy vấn tiền tố lặp lại, số khóa lớn, cập nhật có thể chấp nhận | Chỉ có vài truy vấn tiền tố, có thể dùng mảng sắp |
| Dùng CSR cho đồ thị | Đồ thị thưa, gần như tĩnh, duyệt cạnh nhiều | Đồ thị thay đổi cạnh liên tục, mỗi cập nhật buộc xây lại |
| Viết cache hoặc bộ nhớ tùy chỉnh | Đã đo được chi phí hệ thống hiện tại và ràng buộc cụ thể | Chưa có tải đại diện, chưa xác định vấn đề thực tế |

Phân biệt quan trọng: **độ phức tạp tiệm cận là một tín hiệu về khả năng mở rộng, không phải phép đo tốc độ thực tế tại kích thước đang dùng**. Một thuật toán có độ phức tạp tốt hơn vẫn có thể chậm hơn trên dữ liệu nhỏ do hằng số, cấp phát bộ nhớ, truy cập cache hoặc chi phí bảo trì chỉ mục.

Tối ưu hóa còn cần xét các yêu cầu không phải tốc độ: dùng mảng trực tiếp theo ID có thể nhanh nhưng vượt ngân sách RAM; dùng một cache tự phát có thể gây trả dữ liệu cũ; bỏ bước kiểm tra hợp lệ để tăng tốc có thể vi phạm tính đúng đắn. **Đúng đắn, an toàn dữ liệu và hợp đồng API luôn là điều kiện tiên quyết**.

## 2. Xác định tiêu chí thành công trước khi thay cấu trúc

Thay vì mục tiêu mơ hồ “tìm kiếm phải nhanh hơn”, hãy ghi rõ:

1. **Khối lượng:** tối đa hoặc thường gặp có bao nhiêu phần tử `n`, và `n` tăng nhanh đến đâu?
2. **Tần suất:** có bao nhiêu thao tác đọc, ghi, xóa, cập nhật thứ tự trong một khoảng thời gian?
3. **Phép toán:** tra cứu chính xác, duyệt theo thứ tự, lấy cực trị, truy vấn khoảng, tổng đoạn hay duyệt hàng xóm?
4. **Độ trễ:** mục tiêu trung vị, p95/p99, độ trễ tối đa hoặc thông lượng?
5. **Bộ nhớ:** giới hạn RAM thường trực, bộ nhớ đỉnh khi xây lại chỉ mục và chi phí lưu trữ?
6. **Độ mới dữ liệu:** chỉ mục phụ có phải nhất quán ngay khi ghi xong hay cho phép chậm cập nhật?
7. **Độ ổn định:** ID, tham chiếu, iterator và thứ tự duyệt có được phép thay đổi không?
8. **Phân phối tải:** khóa truy cập đều hay tập trung, dữ liệu tĩnh hay động, có đầu vào đối kháng không?

Một **ngân sách đo được** có thể là: “Với 100.000 bản ghi, truy vấn theo ID phải đạt p99 dưới ngưỡng của hệ thống trên bộ dữ liệu đại diện, trong khi tổng bộ nhớ các chỉ mục không vượt ngân sách và việc cập nhật không phá thứ tự duyệt.” Ngưỡng cụ thể phải do ứng dụng và phép đo xác định, không nên sao chép từ một dự án khác.

### 2.1. Chọn thước đo đúng mục tiêu

| Mục tiêu | Thước đo phù hợp | Cách hiểu sai thường gặp |
| --- | --- | --- |
| Người dùng cảm thấy giao diện chậm | Độ trễ end-to-end và p95/p99 của luồng quan trọng | Chỉ đo một hàm nhỏ nhưng bỏ qua mạng, I/O và dựng giao diện |
| Máy chủ quá tải | CPU, thông lượng, hàng chờ, thời gian thao tác chủ đạo | Tối ưu hàm hiếm khi chạy |
| Vượt RAM | Dung lượng dữ liệu, chỉ mục, cấp phát tạm, bộ nhớ đỉnh | Chỉ đếm số phần tử mà bỏ qua overhead |
| Đọc theo khoảng chậm | Số kết quả `k`, thời gian tìm biên và xuất dữ liệu | Mong truy vấn trả `k` phần tử chỉ mất `O(log n)` |
| Cập nhật chậm sau khi thêm index | Thời gian ghi bao gồm toàn bộ các chỉ mục cần sửa | Chỉ đo thời gian tra cứu từ index |
| Hiệu năng không ổn định | Phân bố độ trễ, lần cấp phát lại, rehash, tranh chấp lock | Suy p99 từ độ phức tạp kỳ vọng `O(1)` |

**Quy tắc:** tối ưu cho **mục tiêu có thể quan sát**, không cho một ký hiệu `O(·)` đơn lẻ.

## 3. Nhận biết các dấu hiệu tối ưu hóa sớm

Một thay đổi có nguy cơ bị làm quá sớm khi có một hoặc nhiều dấu hiệu:

- **Chưa có bài toán bị vi phạm:** không có mục tiêu độ trễ/bộ nhớ hoặc chưa đo được hệ thống chậm ở đâu.
- **Tối ưu nhầm vị trí:** một hàm chỉ dùng 0,1% thời gian được tối ưu trong khi I/O hoặc thuật toán khác chiếm phần lớn.
- **Dựa hoàn toàn vào độ phức tạp:** chọn cây vì `O(log n)` mà không xét `n` nhỏ, tính liên tục của mảng và chi phí nút.
- **Đo bằng ví dụ quá nhỏ hoặc không đại diện:** benchmark một khóa, một kiểu truy vấn rồi kết luận cho mọi tải.
- **Tạo nhiều chỉ mục “phòng khi cần”:** không có API tiêu thụ, nhưng mọi lần ghi phải cập nhật chúng.
- **Hy sinh bất biến hoặc khả năng bảo trì:** xuất hiện hai nguồn dữ liệu có thẩm quyền, xử lý đồng thời phức tạp hoặc con trỏ dễ mất hiệu lực chỉ để giảm một ít thời gian.
- **Không có phép so sánh với bản đơn giản:** không thể chỉ ra mức cải thiện và chi phí đánh đổi.
- **Không có kế hoạch quay lại:** thay đổi làm hỏng hợp đồng API, format lưu trữ hoặc dữ liệu lâu dài mà không có phương án tương thích.

Điều ngược lại cũng đáng cảnh giác: nếu một thao tác `O(n)` đang được gọi trên hàng triệu mục, hoặc dữ liệu dự kiến chắc chắn vượt giới hạn bộ nhớ, yêu cầu đo thêm không phải lý do để trì hoãn vô hạn. Khi ràng buộc đã rõ, **dự báo từ độ phức tạp cùng benchmark đại diện** thường đủ để chủ động thiết kế.

### 3.1. Phân biệt ba kiểu thay đổi

**Tối ưu cục bộ:** thay một đoạn mã hoặc giảm cấp phát mà không đổi biểu diễn; thường có rủi ro nhỏ.

**Đổi cấu trúc dữ liệu:** từ list sang map/cây/heap, từ danh sách kề sang CSR; thay bất biến và chi phí của nhiều phép toán, có thể ảnh hưởng thứ tự, tham chiếu và bộ nhớ.

**Đổi kiến trúc lưu trữ:** tách chỉ mục sang dịch vụ khác, thêm cache phân tán hoặc đổi mô hình phiên bản; còn có rủi ro giao dịch, dữ liệu cũ, đồng bộ và vận hành.

Không nên sử dụng giải pháp của tầng thứ ba để xử lý một vấn đề có thể giải quyết an toàn ở tầng thứ nhất hoặc thứ hai.

## 4. Khi nào thực sự cần đổi cách biểu diễn?

Những tín hiệu đáng tin cậy bao gồm:

1. **Đã chạm ngưỡng hiệu năng:** độ trễ hoặc thông lượng của phép toán chủ đạo vi phạm mục tiêu ở tải đại diện.
2. **Xu hướng cho thấy sắp chạm ngưỡng:** `n` và tần suất thao tác tăng, trong khi độ phức tạp hiện tại không phù hợp với mức tăng dự báo.
3. **Nhu cầu truy vấn đã thay đổi:** trước đây chỉ lấy theo ID, nay cần tìm cận dưới hoặc khoảng theo thời gian.
4. **Tỷ lệ đọc/ghi đổi:** dữ liệu từng bất biến nay thường cập nhật, khiến prefix sum hoặc mảng sắp phải xây lại/dời phần tử liên tục.
5. **Hình dạng dữ liệu đổi:** đồ thị từ thưa sang dày, miền khóa từ nhỏ/dày sang lớn/thưa hoặc ngược lại.
6. **Bộ nhớ vượt khả năng:** biểu diễn đối tượng/nút hoặc ma trận quá tốn RAM, cần nén, bitset hoặc lưu thưa.
7. **Bảo đảm phải mạnh hơn:** trước đây chấp nhận chi phí kỳ vọng, nay cần chặn trường hợp xấu, thứ tự tất định hoặc xử lý đầu vào đối kháng.
8. **Chức năng mới đòi hỏi bất biến mới:** cập nhật ưu tiên theo ID, xóa phần tử trong heap, duy trì LRU hoặc snapshot đọc ổn định.

Một tín hiệu **không đủ** là “ngôn ngữ/thư viện khác nhanh hơn trong bài viết trên mạng”. Bối cảnh tải, kiểu dữ liệu, bộ nhớ và phiên bản triển khai phải tương ứng thì phép so sánh mới có giá trị.

### 4.1. Đổi biểu diễn khác với đổi kết quả

Có thể đổi từ mảng sang hash map nhưng vẫn giữ hợp đồng `getById(id)`. Tuy nhiên, nếu API đã hứa **duyệt theo thứ tự chèn**, hash map thông thường không tự đáp ứng hợp đồng đó. Nếu khách hàng đang lưu **chỉ số mảng** làm định danh, thay cấu trúc có thể làm các tham chiếu cũ sai.

Cần phân biệt:

- **Bất biến nghiệp vụ:** một ID tham chiếu đúng một thực thể, dữ liệu sau cập nhật là chính xác.
- **Bất biến nội bộ:** mảng đã sắp, heap có khóa cha không lớn hơn con, map vị trí trỏ đúng ô.
- **Hợp đồng kết quả:** thứ tự trả về, lỗi khi thiếu khóa, quy tắc trùng lặp, độ mới của dữ liệu.
- **Chi tiết tùy ý:** vị trí vật lý, cấu trúc nút, loại container.

Mục tiêu đổi biểu diễn là thay **chi tiết nội bộ** mà không âm thầm phá **hợp đồng bên ngoài**.

## 5. Tính điểm hòa vốn: lợi ích đọc phải bù chi phí xây và ghi

Giả sử cần tìm chính xác một mã trong `n` bản ghi.

**Cách A:** giữ mảng không sắp và quét để tìm khóa. Mỗi truy vấn mất tới `O(n)`, không có chỉ mục phụ.

**Cách B:** xây hash map `id → record`. Xây dựng thường kỳ vọng `O(n)`, mỗi lần tra cứu kỳ vọng `O(1)`, nhưng cần bộ nhớ thêm và duy trì map khi dữ liệu đổi.

Trong một phiên làm việc có `q` truy vấn và `u` cập nhật, có thể ước lượng:

```text
T_A = B_A(n) + q × L_A(n) + u × U_A(n)
T_B = B_B(n) + q × L_B(n) + u × U_B(n) + M_B

B = thời gian xây dựng
L = thời gian tra cứu
U = thời gian cập nhật
M = chi phí bảo trì bổ sung, tái băm, đồng bộ...
```

**Chú ý:** `M_B` trong biểu thức là **chi phí thời gian bảo trì**; bộ nhớ cần so riêng bằng ngân sách RAM. Đây là mô hình ước lượng cho một tải xác định, không có ý nghĩa như phép cộng giữa số byte và mili giây.

Nếu bỏ qua cập nhật trong một phiên tĩnh, giả sử B phải trả thêm thời gian xây map là `b`, còn mỗi truy vấn tiết kiệm khoảng `d`:

```text
T_B - T_A ≈ b - q × d

B nhanh hơn khi q × d > b
=> q > b / d
```

**Ví dụ minh họa có số giả định, không phải benchmark thực tế:** xây chỉ mục phụ tốn 6 ms; tra cứu tuyến tính mất trung bình 0,12 ms còn qua map mất 0,002 ms trong một môi trường cụ thể. Tiết kiệm `0,118 ms` mỗi truy vấn, nên lợi ích thời gian mới vượt chi phí xây khi số truy vấn lớn hơn khoảng `6 / 0,118 ≈ 50,85`. Nếu chỉ có 4 truy vấn, map vừa tạo có thể không đáng; nếu có hàng nghìn truy vấn, đáng xét hơn. Kết luận thực tế còn phải tính bộ nhớ, cập nhật, hash key và phân bố hit/miss.

Không có **một ngưỡng `n` cố định** mà tại đó phải đổi từ mảng sang hash map. Điểm hòa vốn phụ thuộc `q`, `u`, kích thước khóa, tỷ lệ miss, hằng số hệ thống, bộ nhớ và số lần tạo lại chỉ mục.

### 5.1. Chi phí xây một lần và nhiều lần

Nếu chương trình **tạo chỉ mục một lần rồi tra nhiều lần**, chi phí xây có thể được chia cho nhiều truy vấn. Nếu mỗi request lại tạo hash map từ đầu, phần `O(n)` xây dựng có thể lớn hơn phần tiết kiệm tra cứu, đặc biệt khi truy vấn ít.

Tương tự, sắp một mảng tĩnh một lần trong `O(n log n)` để thực hiện nhiều truy vấn khoảng `O(log n+k)` có thể rất hợp lý. Nhưng nếu mỗi lần sửa lại sắp toàn bộ mảng, chi phí vòng đời khác hẳn.

### 5.2. Đọc nhanh hơn chưa chắc tổng thể nhanh hơn

Một chỉ mục theo giá giúp `range(lo,hi)` nhanh, nhưng mỗi lần đổi giá phải xóa khóa cũ và chèn khóa mới. Thêm một chỉ mục theo tên, danh mục, trạng thái và thời gian có thể làm **khuếch đại ghi**.

Quy tắc quyết định:

> Chỉ giữ một chỉ mục khi lợi ích cho những phép đọc hoặc bảo đảm thực sự cần thiết đủ bù chi phí xây dựng, duy trì, bộ nhớ và rủi ro nhất quán của chỉ mục ấy.

## 6. Ví dụ lựa chọn: mảng, bảng băm và cây cho danh mục sản phẩm

Giả sử một hệ thống lúc đầu quản lý 500 sản phẩm, sau đó tăng lên 500.000. Tập thao tác cũng thay đổi theo thời gian.

### Giai đoạn 1 — Ít dữ liệu, chủ yếu duyệt

Người dùng mở danh sách 500 sản phẩm, lọc ở phía khách hoặc tìm ID vài lần mỗi ngày. Một mảng/list các bản ghi đơn giản có thể đáp ứng đủ và dễ kiểm chứng.

Độ phức tạp:

- Duyệt toàn bộ: `O(n)` — bản thân việc hiển thị `n` kết quả cũng không thể tránh `Ω(n)`.
- Tìm ID bằng quét: `O(n)` trường hợp xấu.
- Thêm cuối: `O(1)` khấu hao nếu list có mảng động.
- Xóa theo ID: cần tìm, có thể `O(n)`.

Nếu đo cho thấy các thao tác chỉ chiếm phần rất nhỏ thời gian và đáp ứng ngân sách, chưa cần thêm nhiều chỉ mục.

### Giai đoạn 2 — Tra ID tăng mạnh

Hệ thống tăng lên 500.000 sản phẩm, API `getById` chiếm phần lớn số lời gọi, và lần quét dài bắt đầu vượt ngưỡng. Lúc này xây `byId: HashMap<ID,Record>` là một thay đổi có căn cứ.

Có hai chiến lược:

1. **Thay mảng bằng map làm nguồn chuẩn:** đơn giản nếu không cần thứ tự duyệt hoặc có thể định nghĩa thứ tự bằng một truy vấn/sắp xếp riêng.
2. **Giữ mảng làm nguồn chuẩn và map là chỉ mục phụ:** phù hợp nếu duyệt mảng vẫn cần, nhưng phải đồng bộ mọi lần chèn/xóa/sắp xếp nếu map trỏ bằng chỉ số.

Nếu map giữ chỉ số mảng mà xóa ở giữa làm các phần tử sau dịch vị trí, cần cập nhật nhiều ánh xạ `O(n)`. Thay vào đó, lưu ID → tham chiếu đến bản ghi ổn định theo hợp đồng hoặc dùng cấu trúc có vị trí/handle phù hợp. Không đổi cách biểu diễn mà bỏ qua **ổn định danh tính**.

### Giai đoạn 3 — Cần lọc theo giá và thứ tự

Một API mới yêu cầu liệt kê `k` sản phẩm có giá trong `[lo,hi]` theo giá tăng dần. Hash map theo ID không tự giải quyết truy vấn này.

Các lựa chọn:

- **Quét map và lọc:** `O(n)` để tìm ứng viên, cộng chi phí sắp `O(k log k)` nếu cần kết quả tăng dần.
- **Mảng sắp theo `(price,id)`:** xây `O(n log n)`; truy vấn `O(log n+k)`; chèn/xóa thường `O(n)` do dời phần tử.
- **Cây tìm kiếm tự cân bằng theo `(price,id)`:** tìm cận `O(log n)`; xuất `k` kết quả `O(k)`; chèn/xóa và cập nhật giá `O(log n)` trong mô hình chuẩn.

Nếu giá hiếm đổi và truy vấn lặp lại, mảng sắp có thể tốt. Nếu giá liên tục cập nhật, cây cân bằng thường đáng xét. Trong cả hai trường hợp, cần xác định **nguồn dữ liệu chính** và cập nhật index giá cùng bản ghi giá khi có thay đổi.

### Đừng dùng một cấu trúc để giải quyết mọi thứ

Một hash map có thể nhanh cho tra ID nhưng không sắp theo giá. Một cây theo giá có thể trả khoảng tốt nhưng tìm ID cần thêm ánh xạ hoặc một khóa khác. **Nhiều cấu trúc nhỏ có trách nhiệm rõ** đôi khi tốt hơn một cấu trúc phức tạp cố bao mọi thao tác, miễn việc đồng bộ các chỉ mục được thiết kế đúng.

## 7. Ví dụ lựa chọn khác: queue, heap và biểu diễn đồ thị

### 7.1. Khi `list.pop(0)` trở thành nút thắt

Một queue viết bằng mảng động có thể dùng `append(x)` và `pop(0)`. Với biểu diễn mảng liên tiếp, xóa ở đầu phải dời các phần tử còn lại, chi phí `O(n)` mỗi lần. Nếu queue dài và dequeue liên tục, đây là nút thắt dễ dự báo.

Có thể chuyển sang:

- **Mảng vòng (circular buffer):** duy trì `head`/`tail`, enqueue/dequeue `O(1)` theo dung lượng cố định, hoặc `O(1)` khấu hao nếu tăng dung lượng.
- **Danh sách liên kết hai đầu:** thêm cuối/xóa đầu `O(1)` sau khi có con trỏ đầu/cuối, nhưng thêm overhead nút và cấp phát.
- **Deque chuẩn của ngôn ngữ/thư viện:** thường là lựa chọn đáng thử trước khi tự viết bộ cấp phát.

Đổi sang danh sách liên kết **không mặc định nhanh hơn mảng** cho mọi loại thao tác: quét liên tiếp trên mảng thường có locality tốt, còn danh sách liên kết thêm chi phí con trỏ. Hãy đổi vì phép toán *dequeue ở đầu* chi phối tải, không chỉ vì danh sách liên kết nghe có vẻ “động hơn”.

### 7.2. Khi quét tìm cực trị cần đổi thành heap

Giả sử bộ lập lịch có `n` tác vụ và mỗi lần nhận việc phải tìm mức ưu tiên nhỏ nhất. Nếu quét mảng mỗi lần, mất `O(n)`. Với `m` lần lấy cực trị, chi phí có thể tới `O(mn)` nếu kích thước duy trì xấp xỉ `n`.

Min-heap hỗ trợ:

- `peekMin`: `O(1)`.
- `push` và `popMin`: `O(log n)` bước điều chỉnh heap (chưa tính resize).
- Bộ nhớ: `O(n)`.

Nếu tác vụ còn được sửa mức ưu tiên theo ID, cần **indexed heap** với bảng `id → index` hoặc chèn bản ghi mới theo chiến lược lazy deletion. Thêm bảng vị trí khi chưa bao giờ sửa ưu tiên theo ID là chi phí bảo trì không cần thiết.

### 7.3. Đồ thị thưa và dày

Với `V` đỉnh và `E` cạnh:

| Cách biểu diễn | Bộ nhớ cơ bản | Duyệt hàng xóm | Kiểm tra có cạnh |
| --- | --- | --- | --- |
| Danh sách kề | `O(V+E)` | `O(deg(v))` | Thường `O(deg(v))` nếu không có chỉ mục con |
| Ma trận kề | `O(V²)` | `O(V)` để kiểm tra một hàng | `O(1)` |
| CSR cho đồ thị thưa, tĩnh | `O(V+E)` | `O(deg(v))` | Phụ thuộc đoạn hàng xóm, có thể tìm nhị phân nếu sắp |

Nếu đồ thị thưa và thường duyệt các cạnh, danh sách kề hoặc CSR hấp dẫn. Nếu `V` nhỏ, đồ thị dày và liên tục hỏi `hasEdge(u,v)`, ma trận kề hoặc bitset theo hàng có thể hợp lý.

Nhưng đổi sang CSR chỉ để tiết kiệm bộ nhớ có thể làm việc thêm/xóa cạnh trở nên tốn kém, vì CSR thường cần dịch hoặc xây lại vùng dữ liệu. Cần quan sát **mật độ `E/V²` và tỷ lệ đọc/ghi**, không chỉ số đỉnh.

### 7.4. Từ prefix sum sang Fenwick/segment tree

Một dãy tĩnh có nhiều truy vấn tổng đoạn thường phù hợp **prefix sum**: xây `O(n)`, hỏi `O(1)`. Nếu sau này phải cập nhật một phần tử thường xuyên, prefix sum có thể cần sửa `O(n)` tổng tiền tố.

Khi đó:

- **Fenwick tree:** cập nhật điểm/tổng đoạn `O(log n)`.
- **Segment tree:** cập nhật điểm/truy vấn tổng hợp đoạn `O(log n)`, có thể mở rộng cho các phép tổng hợp hoặc cập nhật đoạn phù hợp.

Đổi sang cây **trước khi có thao tác cập nhật** không tự có lợi; nhưng giữ prefix sum khi cập nhật trở thành thao tác chủ đạo có thể gây chi phí quá lớn. Đây là ví dụ rõ của việc **thay đổi tải công việc dẫn đến thay đổi cấu trúc hợp lý**.

## 8. Đo đúng trước khi quyết định: profiler, benchmark và dữ liệu đại diện

### 8.1. Phân biệt ba loại phép đo

**Profiling toàn luồng:** tìm hàm hoặc giai đoạn thực sự chiếm CPU, I/O, cấp phát hoặc độ trễ đầu-cuối. Đây là cách tìm đúng vị trí cần tối ưu.

**Microbenchmark cấu trúc dữ liệu:** cô lập chi phí của phương án A và B trên cùng tập thao tác để hiểu điểm hòa vốn. Nó hữu ích để so sánh, **không tự phản ánh toàn bộ hệ thống**.

**Benchmark tích hợp/tải thực:** chạy chức năng ở quy mô và mức đồng thời đại diện, đo p50/p95/p99, throughput, CPU, RAM, độ trễ GC/rehash và tính đúng đắn. Kết quả này mới gần mục tiêu vận hành.

Một microbenchmark cho thấy hash map nhanh gấp đôi trong một hàm nhỏ không có nghĩa độ trễ HTTP giảm một nửa nếu phần lớn thời gian nằm ở cơ sở dữ liệu, mạng hoặc kết xuất.

### 8.2. Dữ liệu thử phải đại diện

Cần chọn:

- **Quy mô:** nhỏ, điển hình, lớn gần ngưỡng, và trường hợp bất lợi trong phạm vi cho phép.
- **Tỷ lệ hit/miss:** tìm khóa tồn tại và không tồn tại; quét tuyến tính có chi phí khác tùy vị trí và miss.
- **Phân bố khóa:** số/chuỗi dài, khóa liên tiếp hoặc rải rác, có va chạm, trùng lặp, khóa ngoài mong đợi.
- **Phân bố thao tác:** tỉ lệ `get`, `insert`, `delete`, `range`, `scan` và thời điểm xây lại chỉ mục.
- **Trạng thái:** cache ấm/lạnh, kích thước bảng băm gần ngưỡng mở rộng, mức lấp đầy và phần tử đã bị xóa.
- **Mức đồng thời:** số luồng yêu cầu và xung đột ghi/đọc nếu ứng dụng có dùng.

Khi hai phương án trả **các kết quả khác nhau** (ví dụ một bên duyệt theo thứ tự chèn còn bên kia duyệt ngẫu nhiên), so thời gian không hợp lệ cho cùng một bài toán. Phải bảo đảm ngữ nghĩa đầu ra tương đương.

### 8.3. Một đoạn benchmark Python tự chứa

Đoạn mã sau so sánh **tra cứu theo ID** trên list và dict, đồng thời tách chi phí xây chỉ mục. Nó minh họa phương pháp, không cố định một ngưỡng chuyển đổi phổ quát.

```python
from statistics import median
from time import perf_counter
import random


def scan_by_id(rows, wanted):
    for row in rows:
        if row["id"] == wanted:
            return row
    return None


def make_data(n):
    return [
        {"id": f"item-{i}", "value": i * 3}
        for i in range(n)
    ]


def measure(work, repeats=7):
    times = []
    for _ in range(repeats):
        t0 = perf_counter()
        work()
        times.append(perf_counter() - t0)
    return median(times)


def compare(n=10_000, q=1_000, seed=1234):
    rows = make_data(n)
    rng = random.Random(seed)

    # Cả hit lẫn miss, theo một lịch truy vấn cố định.
    keys = [
        f"item-{rng.randrange(n)}" if i % 4 != 0
        else f"missing-{i}"
        for i in range(q)
    ]

    def build_index():
        return {row["id"]: row for row in rows}

    index = build_index()
    assert len(index) == len(rows)  # các ID trong ví dụ là duy nhất
    assert all(scan_by_id(rows, k) == index.get(k) for k in keys)

    def run_scan():
        checksum = 0
        for key in keys:
            row = scan_by_id(rows, key)
            if row is not None:
                checksum += row["value"]
        return checksum

    def run_index():
        checksum = 0
        for key in keys:
            row = index.get(key)
            if row is not None:
                checksum += row["value"]
        return checksum

    assert run_scan() == run_index()

    # Warm-up mức tối thiểu, không phải chuẩn hiệu năng tuyệt đối.
    run_scan()
    run_index()

    build_s = measure(build_index)
    scan_s = measure(run_scan)
    index_s = measure(run_index)

    print(f"n={n}, q={q}")
    print(f"build dict:  {build_s:.6f} s")
    print(f"scan q gets:{scan_s:.6f} s")
    print(f"dict q gets:{index_s:.6f} s")
    print(f"dict total: {build_s + index_s:.6f} s")


if __name__ == "__main__":
    compare(n=1_000, q=100)
    compare(n=10_000, q=1_000)
```

**Cách đọc:** `build dict` là thời gian xây chỉ mục; `dict q gets` chỉ là thời gian chạy truy vấn trên map đã tồn tại; `dict total` cộng cả hai để so một vòng đời **xây một lần + hỏi `q` lần**. Nếu cấu trúc được dùng lại nhiều phiên, nên đo theo vòng đời thực tế.

**Giới hạn của ví dụ:** đây là chương trình đơn luồng, dùng dữ liệu tổng hợp nhỏ, không đo bộ nhớ, độ trễ p99, cập nhật hoặc chi phí GC một cách đầy đủ. Thời gian có nhiễu từ môi trường; cần chạy trên dữ liệu đại diện, nhiều lần, ghi lại phiên bản Python/máy và không suy ra con số chung cho mọi hệ thống.

**Không chạy benchmark trong bước soạn nội dung này.** Đoạn mã được cung cấp để người học tự chạy khi có môi trường phù hợp.

### 8.4. Đo bộ nhớ độc lập với thời gian

Khi đổi từ list sang dict, bộ nhớ phụ của map thường là `O(n)`, nhưng con số byte thực tế phụ thuộc hệ thống, kích thước khóa, hệ số tải và kiểu đối tượng.

Trong Python, `sys.getsizeof(container)` không tự tính toàn bộ đối tượng tham chiếu bên trong. Có thể dùng công cụ theo dõi cấp phát như `tracemalloc` để quan sát vùng cấp phát Python trong một thí nghiệm được kiểm soát, nhưng nó cũng không phản ánh tất cả bộ nhớ hệ điều hành và cấp phát thư viện native.

Khi dữ liệu lớn hoặc phải tạo chỉ mục mới song song với chỉ mục cũ, cần đo **bộ nhớ đỉnh**, không chỉ dung lượng ở trạng thái ổn định.

## 9. Đổi cách biểu diễn mà vẫn giữ hợp đồng và bất biến

Tăng tốc bằng cấu trúc mới chỉ thành công nếu mọi phép toán vẫn trả đúng kết quả. Hãy xác định trước:

- **Nguồn dữ liệu có thẩm quyền:** list/map/cây nào là nơi quyết định giá trị cuối cùng?
- **Định danh bền vững:** khách hàng giữ `id` hay chỉ số/địa chỉ dễ đổi?
- **Quy tắc trùng lặp:** nhiều bản ghi có thể cùng khóa phụ hay không?
- **Thứ tự duyệt:** có phải thứ tự chèn, thứ tự khóa hoặc thứ tự truy cập?
- **Bất biến sau cập nhật:** những chỉ mục nào phải thêm, sửa, xóa cùng bản ghi?
- **Nhất quán đọc:** có cho phép người đọc nhìn thấy chỉ mục cũ và bản ghi mới cùng lúc?
- **Xử lý lỗi:** nếu cập nhật được một phần rồi lỗi, cách rollback hoặc từ chối công bố là gì?

Ví dụ, nếu danh mục cần `getById(id)` và `listByPrice(lo,hi)`:

```text
primary: byId[ID] -> Record
secondary: byPrice contains (price, ID)

Invariant:
    (record.price, id) ∈ byPrice
       ⇔ id ∈ byId and byId[id] == record
```

Phát biểu này cần đọc theo nghĩa mỗi bản ghi có **đúng một khóa giá**, và không có cặp khóa giá mồ côi. Nếu giá đổi, phải xóa khóa giá cũ, thêm khóa mới và cập nhật nguồn chính **như một đơn vị logic**.

### 9.1. Tách API khỏi biểu diễn

Một lớp giao diện rõ ràng giúp giảm chi phí thay đổi:

```text
interface Catalog {
    getById(id)
    insert(record)
    update(id, fields)
    remove(id)
    listByPrice(lo, hi)
}
```

Giai đoạn đầu, `getById` có thể quét list. Khi đo thấy cần thiết, thay nội bộ bằng map mà **không đổi ý nghĩa** của `getById`. Nếu thêm tính năng truy vấn khoảng, bổ sung chỉ mục thứ cấp ở phía sau giao diện.

Không nên đưa `arrayIndex` hoặc con trỏ tới nút nội bộ vào API công khai nếu sau này có khả năng sắp xếp, nén hoặc chuyển container. Sự ổn định của **định danh logic** giúp thay biểu diễn dễ hơn nhiều.

### 9.2. Bất biến phải được kiểm thử

Sau mọi `insert`, `update`, `remove`, hãy so kết quả của cấu trúc tối ưu với một **mô hình tham chiếu chậm nhưng đơn giản**. Mô hình có thể quét danh sách, tính lại kết quả từ nguồn chính và sắp khi cần.

Các bất biến phổ biến:

- Tập ID trong map bằng tập ID đang hoạt động.
- Mỗi khóa phụ trỏ tới đúng những ID thỏa điều kiện, theo cả hai chiều.
- Không còn ID đã xóa trong bất kỳ chỉ mục nào.
- Nếu dùng heap + bảng vị trí, `pos[heap[i].id] == i` sau mọi lần hoán đổi.
- Nếu dùng cây tổng hợp, metadata của mỗi nút đúng với cây con.
- Thứ tự kết quả theo hợp đồng, kể cả khi khóa phụ trùng nhau.

**Cải thiện hiệu năng nhưng thay đổi ngữ nghĩa là lỗi, không phải tối ưu hóa.**

## 10. Chiến lược chuyển đổi dữ liệu khi hệ thống đang chạy

Đổi biểu diễn trên một tập dữ liệu tĩnh và dừng ứng dụng có thể khá đơn giản: đọc bản cũ, xây bản mới, kiểm tra, rồi thay. Với hệ thống đang phục vụ nhiều người dùng và liên tục ghi, cần quy trình tránh mất cập nhật.

### 10.1. Bốn giai đoạn chuyển đổi an toàn

**Giai đoạn A — Chuẩn bị:** định nghĩa cấu trúc mới, bất biến, yêu cầu bộ nhớ đỉnh, kiểm thử độc lập và công tắc chuyển chế độ đọc. Chưa xóa cấu trúc cũ.

**Giai đoạn B — Xây chỉ mục mới (*backfill*):** lấy một snapshot nhất quán của nguồn tại phiên bản `v`, quét tất cả bản ghi để dựng chỉ mục mới. Nếu có ghi sau phiên bản `v`, phải ghi lại những thay đổi đó để áp dụng sau.

**Giai đoạn C — Bắt kịp và so sánh:** áp dụng các cập nhật từ sau `v` theo thứ tự/phiên bản phù hợp, rồi thực hiện *shadow read*: chạy truy vấn trên cả cấu trúc cũ và mới, so kết quả mà chưa thay đầu ra của người dùng.

**Giai đoạn D — Chuyển đọc (*cutover*):** chỉ khi chỉ mục mới đã bắt kịp mốc/phiên bản cần thiết và các bất biến được xác minh, chuyển đường đọc bằng cơ chế nguyên tử/nhất quán phù hợp. Giữ bản cũ một thời gian để quay lui nếu cần, rồi thu dọn theo chính sách.

```text
source v0  ---------- ghi 1 ---- ghi 2 ---- ghi 3 ---- ghi 4 --->
     |                     delta log                         |
     |                                                        |
     +-- snapshot v0 --> build new index --> replay deltas --> verify
                                                            |
                                                     atomic cutover
                                                            |
                                                  read from new index
```

**Điều kiện quan trọng:** nếu lấy snapshot ở `v0` rồi chỉ quét nguồn mà không thu thập cập nhật diễn ra sau `v0`, chỉ mục mới có thể thiếu dữ liệu. Việc xây lại một cách âm thầm như vậy không phải chuyển đổi an toàn.

### 10.2. Dual-write có rủi ro riêng

Một chiến lược khác là khi có ghi, cập nhật đồng thời cấu trúc cũ và mới:

```text
update(id, value):
    updateOldIndex(id, value)
    updateNewIndex(id, value)
```

Đoạn mã đơn giản này **chưa đảm bảo nguyên tử**. Nếu cập nhật cũ thành công nhưng cập nhật mới lỗi, hai chỉ mục lệch nhau. Nếu có nhiều luồng, người đọc có thể chen vào giữa hai bước.

Cần một cơ chế thực sự, chẳng hạn transaction bao cả hai cấu trúc, lock + rollback, copy-on-write hoặc sự kiện bền vững kèm retry/version. Trong hệ phân tán, dual-write trực tiếp sang hai dịch vụ không tự có giao dịch nguyên tử; có thể dùng outbox/CDC phù hợp và chấp nhận độ trễ hội tụ theo hợp đồng.

### 10.3. So sánh shadow read phải đúng ngữ nghĩa

Một hash map mới không bảo đảm thứ tự duyệt giống list cũ. Nếu API không hứa thứ tự, khi shadow read có thể so **tập ID** hoặc chuẩn hóa kết quả trước khi so. Nếu API đã hứa thứ tự, cần kiểm tra đúng **thứ tự ấy** chứ không được bỏ qua.

Ngoài dữ liệu trả về, nên so hành vi khi khóa thiếu, khi có khóa trùng, lỗi cập nhật, giá trị `null`, truy vấn khoảng rỗng và các trường hợp biên.

### 10.4. Khi nào dừng hoặc quay lui?

Hãy định trước **tiêu chí hủy chuyển đổi**:

- Số trường hợp kết quả khác nhau vượt ngưỡng cho phép (với dữ liệu chính xác có thể yêu cầu **bằng 0**).
- p95/p99 hoặc throughput của đường mới không đạt mục tiêu.
- Bộ nhớ đỉnh vượt ngân sách.
- Độ trễ áp dụng delta, số mục lỗi hoặc số lần retry vượt giới hạn.
- Bất biến chỉ mục bị phá hoặc không thể xác định trạng thái đồng bộ.

**Quay lui đường đọc** thường dễ hơn **quay lui thay đổi dữ liệu**. Nếu đã đổi cách ghi hoặc xóa format cũ, phải có kế hoạch duy trì bản tương thích và phục hồi trạng thái; không thể chỉ tắt một cờ là chắc chắn quay về được.

## 11. Đổi biểu diễn theo giai đoạn thay vì làm lại toàn bộ

Không nhất thiết thay mọi thành phần trong một lần. Một lộ trình an toàn thường gồm:

1. **Giữ nguồn chuẩn đơn giản:** ví dụ map theo ID.
2. **Bổ sung đúng một chỉ mục có giá trị cao:** ví dụ cây theo giá cho một API truy vấn khoảng hay dùng.
3. **Đo cả đọc lẫn ghi:** giảm thời gian truy vấn bao nhiêu, tăng thời gian cập nhật và bộ nhớ bao nhiêu?
4. **Viết kiểm tra bất biến:** map và cây phải chứa cùng tập ID theo khóa tương ứng.
5. **Dùng shadow reads/canary:** so đầu ra và đo ở tải thực.
6. **Mới cân nhắc chỉ mục tiếp theo:** khi có bằng chứng nó sẽ mang lợi ích ròng.

Thiết kế nhiều chỉ mục có thể rất tốt nhưng làm tăng số trạng thái và các đường cập nhật. Nếu hệ thống chưa đủ năng lực kiểm tra/giao dịch, một cấu trúc hơi chậm nhưng đơn giản và đúng có thể là lựa chọn tốt hơn — **miễn vẫn thỏa những ràng buộc thật**.

### 11.1. Khi một chỉ mục phụ không còn đáng giữ

Một cấu trúc được thêm vào ở quá khứ không nhất thiết phải tồn tại mãi:

- API sử dụng nó có thể ít được gọi hơn.
- Tần suất ghi có thể tăng mạnh, khiến duy trì chỉ mục tốn kém.
- Một hệ tìm kiếm/cơ sở dữ liệu mới có thể thay thế chức năng của nó.
- Dữ liệu thay đổi hình dạng, ví dụ từ thưa sang dày hoặc ngược lại.

Hãy đo định kỳ và cân nhắc **gỡ bỏ chỉ mục ít giá trị**. Mỗi chỉ mục không dùng đến là bộ nhớ và công sức bảo trì không cần thiết, thậm chí có thể tạo lỗi nhất quán.

## 12. Phân biệt bảo đảm hiệu năng: xấu nhất, kỳ vọng và khấu hao

Một thay đổi biểu diễn có thể đổi cả **loại bảo đảm**, không chỉ độ lớn của `O(·)`.

| Ví dụ | Bảo đảm thường gặp | Điều phải nhớ |
| --- | --- | --- |
| Truy cập mảng theo chỉ số hợp lệ | `O(1)` trường hợp xấu trong mô hình RAM | Bộ nhớ có thể lớn nếu dùng mảng trực tiếp theo miền khóa |
| Thêm cuối mảng động tăng dung lượng theo cấp số nhân | `O(1)` khấu hao | Một lần mở rộng có thể sao chép `Θ(n)` phần tử |
| Tìm trong hash map | Kỳ vọng `O(1)` dưới giả định băm thích hợp | Va chạm hoặc đầu vào bất lợi có thể làm lần tra cứu chậm hơn |
| Chèn vào hash map có resize | Thường kỳ vọng khấu hao `O(1)` | Một lần rehash có thể `Θ(n)` |
| Tìm/chèn/xóa trong cây tự cân bằng | `O(log n)` trường hợp xấu | Hằng số, cấp phát nút và locality có thể khác mảng |
| Lấy cực trị trong heap | `O(1)` xem đỉnh; `O(log n)` điều chỉnh khi lấy ra | Nếu mảng nền resize, cần cộng chi phí cấp phát |
| Duyệt đồ thị theo danh sách kề | `O(V+E)` cho một lượt BFS/DFS | Không tự nói gì về thời gian kiểm tra một cạnh ngẫu nhiên |

Một hệ thống cần **độ trễ từng yêu cầu dễ dự đoán** có thể chấp nhận chậm hơn chút ở trung bình để tránh các trường hợp xấu có ảnh hưởng lớn. Tuy nhiên, chặn thuật toán không tự đảm bảo thời gian thực tuyệt đối: hệ điều hành, lock, I/O, GC, CPU và bộ nhớ vẫn có thể ảnh hưởng.

Không được lấy **`O(1)` kỳ vọng** rồi suy ra “mọi yêu cầu luôn nhanh”; cũng không được lấy **`O(1)` khấu hao** rồi suy ra “mỗi lần gọi luôn chỉ một vài bước”.

## 13. Khung quyết định có thể áp dụng lặp lại

Khi cân nhắc một đề xuất tối ưu cấu trúc dữ liệu, hãy đi theo quy trình:

```text
1. Định nghĩa hợp đồng:
   - Kết quả đúng là gì?
   - Thứ tự, trùng lặp, ID, nhất quán và lỗi được quy định thế nào?

2. Nêu vấn đề có căn cứ:
   - Mục tiêu độ trễ/bộ nhớ/thông lượng?
   - Dữ liệu chứng minh vi phạm hoặc xu hướng dự báo?

3. Đo baseline:
   - Profiler chỉ ra phép toán nào thật sự tốn?
   - N, Q, U, phân bố khóa và đồng thời thực tế?

4. Liệt kê ứng viên:
   - Giữ nguyên + tối ưu cục bộ?
   - Mảng/list, hash map, cây, heap, trie, biểu diễn đồ thị?
   - Thêm chỉ mục phụ hay thay nguồn chính?

5. So chi phí toàn vòng đời:
   - Build, get, update, delete, scan, range, output k
   - Bộ nhớ thường trực, bộ nhớ đỉnh, migrate, sync, rollback

6. Xác minh:
   - Kết quả tương đương trên test và shadow reads?
   - Bất biến giữ sau mọi cập nhật và lỗi?

7. Triển khai từng bước:
   - Backfill + delta hoặc transaction phù hợp
   - Canary/cutover khi đạt tiêu chí

8. Đo sau chuyển đổi:
   - Mục tiêu có đạt không? Ghi có bị chậm? RAM tăng bao nhiêu?
   - Nếu không, quay lui an toàn
```

### 13.1. Bảng quyết định trước khi tối ưu

| Điều kiện quan sát | Hành động hợp lý |
| --- | --- |
| Chưa có vấn đề, `n` nhỏ, thao tác hiếm | Giữ giải pháp đúng và đơn giản; theo dõi tín hiệu tăng trưởng |
| Tác vụ bị chậm chủ yếu do I/O chứ không do tìm trên cấu trúc | Tập trung vào nút thắt thật, chưa cần đổi cấu trúc dữ liệu |
| Tra cứu ID chi phối CPU ở `n` lớn | Cân nhắc hash map hoặc mảng trực tiếp nếu miền khóa đủ nhỏ/dày |
| Cần duyệt khóa có thứ tự với cập nhật thường xuyên | Cân nhắc cây tự cân bằng thay vì quét/sắp lại mảng |
| Liên tục lấy phần tử cực tiểu | Cân nhắc heap; chỉ thêm map vị trí nếu cần sửa/xóa theo ID |
| Tìm tiền tố rất nhiều, tập khóa lớn | So trie/radix tree với mảng hoặc cây chuỗi sắp |
| Đồ thị thưa, ít cập nhật, BFS/DFS nhiều | So CSR và danh sách kề; tránh ma trận `V²` khi vượt RAM |
| Chỉ mục mới làm tốc độ ghi hoặc RAM vượt ngân sách | Xem lại tần suất truy vấn, chọn chỉ mục khác hoặc gỡ chỉ mục |
| Hành vi mới khác bản tham chiếu | Dừng tối ưu, sửa tính đúng đắn trước khi chuyển đọc |

## 14. Những ngộ nhận dẫn tới quyết định sai

**“Đừng tối ưu sớm” nghĩa là luôn chọn thuật toán đơn giản nhất về mã nguồn.** Không. Nếu bài toán đã đòi truy vấn cận dưới ở quy mô lớn, chọn cấu trúc phù hợp từ đầu có thể là thiết kế tối thiểu đúng đắn.

**“`O(log n)` luôn nhanh hơn `O(n)`.”** Không ở mọi kích thước và hệ thống. Hằng số, locality, kiểu dữ liệu và số lần chạy ảnh hưởng tốc độ thực.

**“Chuyển sang hash map thì mọi thao tác đều `O(1)`.”** Hash map không tự hỗ trợ duyệt có thứ tự, truy vấn khoảng và lấy cực trị; va chạm hoặc rehash còn tạo chi phí.

**“Có chỉ mục mới nên có thể bỏ ngay dữ liệu cũ.”** Nếu hệ thống đang ghi, backfill thiếu delta có thể bỏ sót dữ liệu. Phải có quy trình chuyển trạng thái nhất quán.

**“Chạy benchmark một lần và lấy số nhanh nhất.”** Đo có nhiễu. Cần lặp lại, xác nhận kết quả tương đương, xét tải đại diện, bộ nhớ và độ trễ phần đuôi.

**“Chỉ mục càng nhiều càng tốt.”** Thêm chỉ mục tăng chi phí cập nhật, bộ nhớ và số bất biến cần giữ; có thể làm hệ thống chậm hơn dưới tải ghi.

**“Nếu đã tối ưu, dữ liệu không còn cần kiểm chứng.”** Chính khi có nhiều biểu diễn, nguy cơ thiếu khóa, khóa mồ côi và cập nhật nửa chừng tăng lên.

**“Đổi container là việc nội bộ, không ảnh hưởng API.”** Có thể ảnh hưởng thứ tự duyệt, độ ổn định tham chiếu, cách xử lý khóa trùng và ngữ nghĩa đồng thời.

**“Đo thời gian trung bình là đủ.”** Nếu dịch vụ có mục tiêu p99 hoặc giới hạn bộ nhớ đỉnh, cần đo đúng các chỉ số đó.

**“Sau khi chuyển đổi xong thì không cần đo nữa.”** Tải công việc tiếp tục đổi; phải kiểm tra giả định ban đầu còn đúng và liệu chỉ mục mới có còn đáng giữ.

## 15. Bài tập tự kiểm tra

### Bài 1 — Khi nào không nên đổi sang hash map?

Một chương trình đọc 40 bản ghi một lần, tìm một ID rồi kết thúc. Người phát triển muốn xây hash map “để đạt `O(1)`”.

*Gợi ý đáp án:* cần so thời gian xây map với thời gian quét tối đa 40 mục. Với chỉ một lần tra cứu, quét có thể đủ nhanh và ít bộ nhớ hơn. Không có ngưỡng chung; đo hoặc đánh giá theo yêu cầu.

### Bài 2 — Khi nào bắt buộc xem lại biểu diễn?

API tìm ID thực hiện 15.000 lần/giây trên 500.000 bản ghi và profiling cho thấy quét mảng chiếm phần lớn CPU, làm p99 vượt ngân sách.

*Đáp án:* đây là tín hiệu rõ để cân nhắc chỉ mục theo ID. Cần thử hash map, kiểm chứng tính duy nhất, giữ đúng thứ tự duyệt nếu hợp đồng yêu cầu và đo lại CPU/p99/RAM.

### Bài 3 — Tính điểm hòa vốn

Một lần xây chỉ mục mất thêm 5 ms. Mỗi truy vấn sau đó tiết kiệm được 0,1 ms. Bỏ qua cập nhật và bộ nhớ, phải có khoảng bao nhiêu truy vấn mới bù chi phí xây?

*Đáp án:* cần `q×0,1 > 5`, tức `q > 50` để có lợi **rõ ràng về tổng thời gian** theo mô hình. Với đúng 50 truy vấn thì hòa vốn. Số liệu đo thật có thể thay đổi.

### Bài 4 — Đọc nhanh hơn nhưng ghi chậm hơn

Một cây giá giúp truy vấn khoảng nhanh hơn 3 lần nhưng khiến mỗi lần cập nhật giá chậm hơn đáng kể. Hệ thống hiện có 90% thao tác ghi, 10% đọc.

*Gợi ý:* phải tính trọng số theo tần suất và chi phí từng thao tác. Không đủ cơ sở nói cây tốt hơn vì riêng truy vấn nhanh hơn 3 lần.

### Bài 5 — Dữ liệu biến đổi

Ban đầu là 1 triệu số bất biến và rất nhiều truy vấn tổng đoạn. Sau này có hàng nghìn cập nhật điểm mỗi giây. Có nên giữ prefix sum chỉ vì truy vấn `O(1)`?

*Đáp án:* không nên mặc định. Prefix sum có thể tốn `O(n)` cho một cập nhật; Fenwick tree/segment tree cho cập nhật điểm và tổng đoạn `O(log n)`, là ứng viên đáng đánh giá.

### Bài 6 — Bảo toàn thứ tự duyệt

Một API trước đây trả danh sách theo thứ tự chèn từ mảng. Đội phát triển đổi nguồn sang hash map, kết quả trả về có thứ tự khác nhưng tập ID giống nhau. Có coi là tối ưu đúng không?

*Đáp án:* nếu thứ tự chèn là hợp đồng API, đó là thay đổi sai ngữ nghĩa. Cần duy trì chỉ mục thứ tự chèn hoặc sửa hợp đồng một cách có chủ đích, không tự bỏ qua yêu cầu.

### Bài 7 — Backfill đang có ghi

Đội phát triển lấy snapshot tại version 100, xây chỉ mục mới và chuyển đọc ngay khi quét xong, trong khi các ghi tới version 140 đã xảy ra.

*Đáp án:* có nguy cơ thiếu hoặc sai những cập nhật 101–140. Cần thu thập và áp dụng delta theo version, kiểm tra đồng bộ tại mốc cutover, rồi công bố chỉ mục mới bằng cơ chế phù hợp.

### Bài 8 — Chọn biểu diễn đồ thị

Một đồ thị có hàng chục nghìn đỉnh, số cạnh tỷ lệ tuyến tính với đỉnh và thay đổi cạnh liên tục. Có nên chuyển ngay sang ma trận kề để kiểm tra cạnh `O(1)`?

*Gợi ý:* ma trận dùng `O(V²)` bộ nhớ; với đồ thị thưa có thể quá lớn. Danh sách kề kết hợp hash set hàng xóm khi cần kiểm tra cạnh nhiều có thể phù hợp hơn. Cần đo nhu cầu và RAM.

### Bài 9 — Tối ưu sai chỗ

Profiling cho thấy 80% độ trễ từ gọi mạng, 5% từ thao tác trên cây tìm kiếm. Một thay đổi giúp thao tác cây nhanh gấp đôi. Độ trễ toàn luồng tối đa có thể giảm khoảng bao nhiêu nếu mọi phần khác giữ nguyên?

*Định hướng:* nếu thao tác cây chiếm đúng 5% thời gian, nhanh gấp đôi phần đó chỉ tiết kiệm tối đa khoảng 2,5% tổng thời gian, theo giả định không có tác động phụ. Đây là ví dụ của việc tối ưu phần ít chi phối không đem lại cải thiện lớn.

### Bài 10 — Quyết định bỏ chỉ mục

Trước đây `byTag` được dùng thường xuyên; hiện chức năng tìm theo tag gần như ngừng sử dụng nhưng mỗi sản phẩm thay tag liên tục, và map nhãn dùng nhiều RAM.

*Đáp án:* cân nhắc gỡ chỉ mục. Trước khi xóa cần xác nhận không còn API/phụ thuộc cần nó, đo lợi ích bộ nhớ/ghi, định nghĩa cách phục vụ truy vấn tag hiếm và có kế hoạch quay lui nếu cần.

## Kết luận

**Tránh tối ưu hóa sớm không có nghĩa tránh suy nghĩ về độ phức tạp.** Nó có nghĩa là chọn đúng mức phức tạp cho một bài toán có yêu cầu rõ, và không trả chi phí thiết kế/bộ nhớ/duy trì cho một lợi ích chưa được chứng minh. Khi quy mô, phân bố thao tác, mật độ dữ liệu hoặc yêu cầu nhất quán thay đổi, đổi biểu diễn từ mảng sang bảng băm, cây, heap, trie hay cấu trúc đồ thị phù hợp có thể mang lại lợi ích lớn.

Quy trình đáng tin cậy là **đặc tả hợp đồng → đo baseline → phân tích chi phí vòng đời → so phương án → kiểm chứng bất biến → chuyển đổi an toàn → đo lại**. Một phương án nhanh hơn nhưng làm sai kết quả, mất cập nhật khi backfill hoặc vượt RAM không phải là tối ưu thành công. Chọn cấu trúc dữ liệu tốt là biết **khi nào cần giữ sự đơn giản, khi nào cần đổi cách biểu diễn, và bằng chứng nào chứng minh quyết định ấy đúng**.
