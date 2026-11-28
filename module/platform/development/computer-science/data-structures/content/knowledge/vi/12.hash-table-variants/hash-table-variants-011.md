# Lựa chọn biến thể theo tải, cập nhật, bộ nhớ và độ trễ

Bảng băm (*hash table*) thường được giới thiệu bằng nhận định “tìm kiếm, chèn và xóa có thời gian trung bình \(O(1)\)”. Nhận định này hữu ích, nhưng **chưa đủ để chọn một cấu trúc dữ liệu cho hệ thống thực tế**. Hai bảng băm có cùng độ phức tạp kỳ vọng vẫn có thể khác xa về lượng RAM sử dụng, số lần truy cập bộ nhớ, chi phí chèn khi gần đầy và **độ trễ của những yêu cầu chậm nhất**.

Trong chương **Biến thể bảng băm** thuộc module **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài học này tổng hợp các tiêu chí chọn cấu trúc từ **mảng, bảng băm và các biến thể của bảng băm**: hệ số tải, tần suất cập nhật, ngân sách bộ nhớ, yêu cầu độ trễ, đặc điểm khóa và môi trường lưu trữ. Mục tiêu không phải tìm “bảng băm nhanh nhất” một cách tuyệt đối, mà là **biết khi nào một biến thể phù hợp hoặc không phù hợp** với một workload đã xác định.

> **Nguyên tắc thiết kế:** Đánh giá đúng cùng lúc **bất biến dữ liệu**, **thao tác cần tối ưu**, **giới hạn bộ nhớ** và **độ trễ tệ nhất được chấp nhận**. Không kết luận chỉ từ tốc độ trung bình hoặc nhãn \(O(1)\).

## 1. Bắt đầu từ workload, không phải tên thuật toán

Trước khi chọn cấu trúc, hãy làm rõ những câu hỏi:

| Nhóm câu hỏi | Điều cần xác định | Tại sao quan trọng? |
| --- | --- | --- |
| Quy mô | Có \(n\) khóa? Tăng đến bao nhiêu? | Quyết định số bucket, số lần resize, chi phí metadata |
| Tỷ lệ thao tác | Bao nhiêu % tìm, chèn, sửa giá trị, xóa? | Một cấu trúc đọc nhanh có thể chèn phức tạp |
| Tra cứu thành công | Truy vấn trúng khóa hay không trúng khóa nhiều hơn? | Chi phí hit và miss có thể rất khác |
| Mẫu truy cập | Phân bố đều, Zipf/hot key, hay nhiều khóa cùng tiền tố? | Ảnh hưởng cache, clustering và va chạm |
| Dữ liệu | Khóa số nguyên, chuỗi dài, object, bản ghi lớn? | Chi phí tính hash, so sánh và di chuyển bản ghi |
| Bộ nhớ | Giới hạn RAM, yêu cầu cache locality, GC? | Chaining có overhead khác bảng dạng mảng |
| Độ trễ | Mục tiêu trung bình hay p95/p99, có hard deadline? | Rehash hoặc chèn dài tạo độ trễ đột biến |
| Môi trường | Một luồng, nhiều luồng, disk page, hay nhiều nút? | Quyết định cần hash table cục bộ hay sharding |
| Đầu vào | Khóa tin cậy hay do người ngoài lựa chọn? | Có thể phát sinh tấn công hash flooding |
| Thứ tự | Có cần duyệt tăng dần hoặc truy vấn theo khoảng? | Hash table thuần túy không bảo toàn thứ tự khóa |

Nếu ứng dụng chủ yếu là **tra cứu tĩnh**, ta có thể chấp nhận xây dựng chỉ mục tốn công một lần. Nếu phải **chèn/xóa liên tục**, cấu trúc phù hợp lại khác. Nếu mỗi truy vấn phải đáp ứng **giới hạn tệ nhất**, việc một thuật toán có thời gian **kỳ vọng** thấp chưa phải là bảo đảm đủ mạnh.

### Phân biệt các yêu cầu độ trễ

- **Throughput:** số thao tác xử lý trong một giây; không nói trực tiếp từng yêu cầu mất bao lâu.
- **Mean latency:** độ trễ trung bình; dễ che giấu số ít yêu cầu rất chậm.
- **p95/p99 latency:** phân vị thứ 95/99 của độ trễ, phản ánh “đuôi” phân bố. p99 là giá trị mà khoảng 99% phép đo không vượt qua trong tập đo.
- **Worst-case complexity:** giới hạn tiệm cận trong trường hợp xấu nhất của thuật toán dưới giả thiết đã nêu; không tự quy đổi thành một số mili-giây cố định.
- **Hard real-time deadline:** đòi hỏi giới hạn thời gian thực thi chặt chẽ trong một môi trường cụ thể, gồm cả hệ điều hành, cấp phát và thiết bị. Không được suy ra chỉ từ việc trung bình là \(O(1)\).

## 2. Hiểu đúng hệ số tải và phạm vi áp dụng

Với bảng có \(m\) ô/bucket chính và \(n\) khóa phân biệt, hệ số tải thường được định nghĩa:

\[
\boxed{\alpha=\frac{n}{m}.}
\]

Tuy nhiên, ý nghĩa của \(\alpha\) phụ thuộc **cấu trúc lưu trữ**:

| Cấu trúc | Ý nghĩa mẫu số | Giới hạn hoặc lưu ý |
| --- | --- | --- |
| Separate chaining | Số bucket chính | \(\alpha\) **có thể lớn hơn 1** vì một bucket chứa nhiều khóa |
| Open addressing: linear probing, Robin Hood | Số ô trong mảng lưu khóa | Với phiên bản thông thường cần **\(\alpha<1\)** để có ô trống |
| Cuckoo hai bảng, mỗi bảng \(m\) ô | **\(2m\)** ô vật lý | Nên dùng \(\alpha=n/(2m)\), không phải \(n/m\) |
| Hopscotch | Số ô dữ liệu | Thêm ràng buộc vùng lân cận độ rộng \(H\) |
| Extendible/linear hashing theo trang | Số bucket chính nhân dung lượng \(B\) bản ghi/bucket | Có thể dùng \(\alpha=n/(NB)\); trang tràn phải được tính riêng |
| Băm hoàn hảo tĩnh | Tùy cấu trúc xây dựng và dạng bảng | “Không va chạm” không tương đương bảng đạt 100% sử dụng bộ nhớ |

**Không so sánh trực tiếp hai giá trị \(\alpha\)** nếu mẫu số khác nhau. Chẳng hạn, cuckoo hai bảng với \(\alpha=0{,}45\) nghĩa là đã sử dụng 45% tổng **hai mảng**; không nên diễn giải thành 45% số bucket trong **mỗi** mảng theo một định nghĩa khác.

### Càng đầy, chi phí có thể tăng phi tuyến

Trong **linear probing**, các cụm ô đã chiếm (*clusters*) có thể dài khi \(\alpha\) tăng cao. Với mô hình cổ điển giả định vị trí băm gốc độc lập và phân bố đều, bảng đủ lớn, không có xóa và không xét chi phí resize, số ô thăm dò kỳ vọng xấp xỉ:

\[
\begin{aligned}
E_{\mathrm{hit}}&\approx\frac12\left(1+\frac1{1-\alpha}\right),\\
E_{\mathrm{miss}}&\approx\frac12\left(1+\frac1{(1-\alpha)^2}\right).
\end{aligned}
\]

| Hệ số tải \(\alpha\) | Tìm thành công — kỳ vọng xấp xỉ | Tìm thất bại — kỳ vọng xấp xỉ |
| ---: | ---: | ---: |
| 0,50 | 1,5 ô | 2,5 ô |
| 0,75 | 2,5 ô | 8,5 ô |
| 0,90 | 5,5 ô | 50,5 ô |

**Cảnh báo về mô hình:** Đây là kết quả phân tích của **linear probing cổ điển** dưới giả thiết cụ thể, **không** phải số đo áp dụng chung cho Robin Hood, cuckoo, hopscotch, mọi hàm băm hay mọi CPU. Dữ liệu thực, cách resize, xóa, vector hóa và cấu trúc bucket đều làm thay đổi kết quả.

Điểm học thuật quan trọng: **chỉ tăng tải từ 0,75 lên 0,90 cũng có thể làm phép tìm thất bại tăng rất mạnh**. Do đó cần đo riêng tỷ lệ *miss*, không chỉ đo tốc độ tìm những khóa đã có.

## 3. Bản đồ so sánh các biến thể thông dụng

Bảng dưới đây dùng các **phiên bản điển hình**, không xem mọi biến thể cùng tên đều giống nhau. Mọi phát biểu \(O(1)\) về hash table đều giả định **tính hash và so sánh khóa tốn hằng số** hoặc đã tách riêng chi phí của chúng.

| Cấu trúc | Điểm mạnh chủ yếu | Đánh đổi của cập nhật | Bộ nhớ/độ trễ cần theo dõi |
| --- | --- | --- | --- |
| **Separate chaining** | Dễ chèn/xóa; xử lý bucket có nhiều phần tử | Chuỗi dài làm tra cứu chậm; cần cấp phát hoặc bucket động | Con trỏ, node, cache miss, độ dài chuỗi |
| **Linear probing** | Dữ liệu liên tiếp, cục bộ cache tốt; cài đặt đơn giản | Clustering, xóa cần tombstone/dịch chuyển, resize | Nhạy với tải cao, đặc biệt truy vấn miss |
| **Robin Hood hashing** | Cân bằng khoảng cách thăm dò, có thể dừng tìm sớm | Chèn đổi chỗ nhiều bản ghi; xóa có thể dịch lùi | DIB tối đa, p99 ghi, tính cục bộ của mảng |
| **Cuckoo hashing hai lựa chọn** | Tra cứu tối đa hai ô ứng viên khi giữ đúng bất biến | Chèn có chuỗi đẩy, có thể cần rehash | Dự phòng ô trống, đợt chèn thất bại, chi phí rebuild |
| **Hopscotch hashing** | Giới hạn số vị trí tra cứu trong vùng \(H\) | Chèn phải kéo ô trống và cập nhật metadata | Bitmap theo bucket, kích thước \(H\), khả năng không chèn được |
| **Băm hoàn hảo tĩnh** | Tra cứu không có va chạm trên **tập khóa cố định** | Thêm/xóa khóa thường đòi hỏi xây lại | Chi phí xây dựng và dữ liệu xác minh thành viên |
| **Minimal perfect hashing (MPHF)** | Ánh xạ \(n\) khóa tĩnh đến \(0,\ldots,n-1\) không trùng | Không tự hỗ trợ thêm/xóa; không tự xác minh khóa ngoài tập | Bits/key của cấu trúc + khóa/giá trị/fingerprint cần thiết |
| **Extendible hashing** | Tách bucket theo nhu cầu; hữu ích cho trang đĩa | Có thể nhân đôi directory và đổi con trỏ | Global/local depth, số trang I/O, \(2^g\) con trỏ |
| **Linear hashing** | Tăng từng bucket, dàn trải chi phí mở rộng | Bucket bị tràn có thể phải chờ lượt tách | Trang tràn, con trỏ split, số lần đọc trang |
| **Consistent hashing** | Phân chia khóa giữa **nhiều nút**, ít chuyển chủ khi thay đổi thành viên | Cần điều phối chuyển dữ liệu, replica và metadata | Độ lệch tải, mạng, số token/vnode, phục hồi sự cố |

**Phân biệt cấp độ:** consistent hashing ở hàng cuối là kỹ thuật **chọn nút lưu trữ**, không thay thế hash table dùng **bên trong nút**. Extendible/linear hashing thường hướng đến **bucket/trang lưu trữ động**, không phải lúc nào cũng cạnh tranh trực tiếp với các phương pháp open addressing trong RAM.

## 4. Tối ưu tra cứu: hit, miss và số vị trí phải đọc

Chi phí đọc không chỉ là số lần gọi hàm hash. Hai thuật toán đều có thể tính hash một lần nhưng khác số **địa chỉ bộ nhớ** và **cache line** cần truy cập.

### Separate chaining

Với giả thiết băm đều, mỗi bucket nhận xấp xỉ \(\alpha\) khóa theo kỳ vọng. Phép tìm phải duyệt những khóa trong bucket cho đến khi gặp khóa cần tìm hoặc hết chuỗi.

Ưu điểm: không cần giữ nhiều ô trống trong một mảng open addressing. Nhược điểm: nếu mỗi nút trong chuỗi nằm ở vị trí RAM khác nhau, tra cứu có thể phát sinh nhiều lần **cache miss** dù số phép so sánh không lớn.

### Linear probing

Các ô liên tiếp thường nằm gần nhau trong RAM nên **prefetch/cache locality** tốt. Tuy nhiên, tìm thất bại thường phải đi tới ô trống; khi tải cao, cụm dài có thể khiến p99 tăng mạnh.

### Robin Hood hashing

Quy tắc đổi chỗ khi chèn ưu tiên khóa đã thăm dò xa, làm phân bố DIB (*distance to initial bucket*) thường ít lệch hơn. Trong cấu hình duy trì bất biến Robin Hood và xử lý xóa đúng, **có thể dừng tìm sớm** khi DIB của phần tử tại ô nhỏ hơn khoảng cách thăm dò hiện tại của khóa truy vấn.

Điều này có thể cải thiện truy vấn miss, nhưng **không xóa bỏ clustering** và không biến mọi phép tìm thành \(O(1)\) trong trường hợp xấu nhất.

### Cuckoo hashing

Trong phiên bản **hai mảng, mỗi khóa có đúng hai ô ứng viên**, tra cứu chỉ kiểm tra tối đa **hai vị trí**, nên độ dài đường tra cứu có giới hạn rõ ràng. Đổi lại, chèn có thể kéo theo hàng loạt lần đẩy khóa và đôi lúc phải chọn lại hàm băm.

Một số biến thể có bucket nhiều ô, stash hoặc nhiều hơn hai hàm: số ô cần kiểm tra lúc tìm có thể thay đổi. Vì vậy, chỉ dùng bảo đảm “hai ô” khi thiết kế thực sự đúng là **phiên bản hai ô ứng viên**.

### Hopscotch hashing

Mỗi khóa bị giới hạn ở một trong \(H\) ô gần ô gốc; bitmap theo ô gốc giúp chỉ kiểm tra các vị trí có thể chứa khóa. Với **\(H\) cố định**, tìm kiểm tra tối đa \(H\) vị trí trong mô hình hằng số cho hash và so sánh.

Lưu ý: giới hạn vùng tra cứu **không giới hạn số bước chèn**, vì chèn có thể phải đi tìm ô trống xa hoặc dịch chuyển các phần tử khác.

### Băm hoàn hảo

Với tập khóa tĩnh, băm hoàn hảo loại va chạm trong **tập đã biết**. MPHF còn dùng đúng \(n\) chỉ số logic khác nhau cho \(n\) khóa, hữu ích cho các chỉ mục bất biến. Nhưng khi truy vấn khóa **không thuộc tập**, một MPHF thuần túy vẫn có thể trả về một chỉ số; cần **kiểm tra khóa**, fingerprint với xác suất sai chấp nhận được, hoặc cơ chế thành viên chính xác khác trước khi trả giá trị.

**Quy tắc đọc:** Nếu bài toán yêu cầu latency p99 cho **tra cứu âm tính**, hãy đo riêng miss; nếu đọc phần lớn trúng và khóa thường đã ở cache, kết quả lựa chọn có thể hoàn toàn khác.

## 5. Cập nhật: mỗi biến thể trả chi phí vào thời điểm nào?

Một phép chèn không đơn thuần là “ghi thêm một ô”. Trong nhiều biến thể, chèn và xóa phải **duy trì bất biến**; chính công việc đó quyết định độ trễ phần đuôi.

| Biến thể | Chèn | Xóa | Biến cố gây chi phí lớn |
| --- | --- | --- | --- |
| Chaining | Chèn vào bucket hoặc danh sách; có thể thêm nút | Xóa nút hoặc bản ghi trong bucket | Tăng bảng/rebuild; cấp phát bộ nhớ, bucket dài |
| Linear probing | Đi tìm ô trống trong chuỗi thăm dò | Tombstone hoặc lấp lỗ trống đúng quy tắc | Cluster dài, tích lũy tombstone, resize |
| Robin Hood | Có thể đổi chỗ nhiều khóa | Dịch lùi (*backward shift*) hoặc chiến lược xóa hợp lệ | Chuỗi dịch chuyển dài, resize |
| Cuckoo | Đẩy khóa cũ sang vị trí còn lại nhiều lần | Xóa trực tiếp một ô ứng viên trong phiên bản cơ bản | Chuỗi đẩy không tìm chỗ, rehash/resize |
| Hopscotch | Kéo ô trống về vùng \(H\), cập nhật hop bitmap | Xóa ô và bitmap của ô gốc | Không kéo được ô trống, rehash/resize |
| Perfect/MPHF tĩnh | Không có chèn tổng quát đơn giản | Không có xóa tổng quát đơn giản | Xây dựng lại hoặc dùng delta phụ |
| Extendible | Ghi vào bucket; tách khi đầy | Có thể gộp buddy và thu nhỏ directory | Nhân đôi directory, tách liên tiếp |
| Linear hashing | Thêm vào bucket/trang tràn rồi tách tuần tự | Có thể gộp ngược theo split pointer | Chuỗi tràn, đọc/ghi trang khi tách |

### Cập nhật giá trị không nhất thiết là thay đổi tập khóa

Với ánh xạ **khóa–giá trị**, sửa giá trị của một khóa đã tồn tại khác với **chèn một khóa mới**. Nhiều cấu trúc có thể cập nhật giá trị ngay tại bản ghi, không cần thay vị trí băm.

Nhưng nếu bản ghi có kích thước thay đổi, cập nhật có thể vẫn cần cấp phát lại vùng lưu trữ hoặc ghi nhiều trang. Do đó khi tính workload, nên tách riêng:

\[
\text{update-value}\neq\text{insert-new-key}\neq\text{delete-key}.
\]

Nếu tập khóa ổn định và chỉ giá trị thay đổi, **MPHF/tĩnh + mảng giá trị cập nhật được** có thể là lựa chọn tốt khi hệ thống hỗ trợ cập nhật phần dữ liệu đích. Nếu số khóa thường xuyên tăng giảm, chi phí xây lại mới là yếu tố quyết định.

### Resize và rehash là những thao tác hiếm nhưng đắt

Giả sử một bảng tăng gấp đôi dung lượng mỗi khi tải vượt ngưỡng. Phần lớn lần chèn có thể xử lý nhanh, nhưng một lần resize có thể phải **duyệt và phân phối lại \(n\) khóa**, gây \(O(n)\) công việc ngay tại thời điểm đó.

Nếu mở rộng theo cấp số nhân và có giả thiết chi phí mỗi lần chuyển khóa hợp lý, tổng số lần di chuyển qua nhiều lượt tăng trưởng có thể được **phân bổ** để đạt chi phí trung bình thấp cho mỗi chèn. Tuy vậy, **amortized \(O(1)\)** không có nghĩa **mọi lần chèn riêng lẻ đều đáp ứng deadline ngắn**.

Các biện pháp tùy hệ thống bao gồm **đặt trước dung lượng (*reserve*)**, **resize theo từng bước**, **tách bucket dần**, hoặc thực hiện rebuild trên cấu trúc mới rồi chuyển đổi phiên bản một cách an toàn. Chúng làm phức tạp triển khai nhưng có thể giảm đỉnh độ trễ.

## 6. Bộ nhớ: đếm byte thật, không chỉ số phần tử

Hai bảng băm có cùng \(n\) khóa và thời gian tra cứu kỳ vọng đều tốt nhưng tiêu tốn RAM khác nhau. Với một bảng mảng có **\(m\) ô**, kích thước mỗi ô giả định là \(S\) byte và bỏ qua metadata bổ sung:

\[
\boxed{\operatorname{memory}_{\mathrm{slots}}\approx mS
=\frac{nS}{\alpha}.}
\]

Đây là **mô hình sơ bộ**, không phải cam kết dung lượng của một container bất kỳ. Bản ghi chứa khóa/giá trị có thể lớn hơn hoặc nhỏ hơn \(S\), có padding căn chỉnh, metadata điều khiển, allocator overhead và dữ liệu nằm ngoài mảng.

### Ví dụ định lượng

Giả sử có **\(n=1\,000\,000\)** bản ghi; mỗi ô của bảng mảng chiếm **\(S=16\)** byte, gồm đủ thông tin cần lưu theo mô hình giả định và **chưa tính** bitmap, metadata phụ hoặc mảng ngoài:

| Hệ số tải dự kiến | Số ô cần xấp xỉ \(n/\alpha\) | Bộ nhớ riêng mảng ô |
| ---: | ---: | ---: |
| 0,50 | 2.000.000 | 32,00 MB |
| 0,70 | 1.428.572 | 22,86 MB |
| 0,80 | 1.250.000 | 20,00 MB |
| 0,90 | 1.111.112 | 17,78 MB |

Số liệu dùng **MB thập phân** (\(1\text{ MB}=10^6\) byte) và làm tròn. Nếu mảng thực tế phải có dung lượng lũy thừa của hai, số ô được cấp có thể **lớn hơn** các giá trị này; khi đó phải tính lại hệ số tải hiệu dụng.

Từ 0,70 lên 0,90 giúp giảm bộ nhớ mảng khoảng **5,08 MB** trong ví dụ, nhưng chi phí tìm/chèn có thể tăng mạnh tùy biến thể. **Tiết kiệm RAM không tự đồng nghĩa tiết kiệm tổng chi phí hệ thống**: bảng quá đầy có thể tăng CPU, độ trễ và lỗi timeout.

### Chaining và con trỏ

Với **separate chaining**, mỗi bucket chính thường có một con trỏ hoặc một cấu trúc đầu danh sách. Mỗi phần tử ở dạng node có thể mang theo:

- Khóa và giá trị (hoặc con trỏ tới chúng).
- Một hoặc nhiều con trỏ liên kết.
- Metadata căn chỉnh bộ nhớ, header cấp phát hoặc thông tin GC.

Nếu node nằm rải rác trong heap, việc theo con trỏ làm tăng cache miss và chi phí allocator. Tuy vậy, **không phải mọi triển khai chaining đều dùng một node cấp phát riêng**: có thể dùng bucket vector hoặc bố trí nhóm phần tử liên tiếp để cải thiện tính cục bộ.

### Open addressing và metadata

Linear probing và Robin Hood hashing thường lưu phần tử trong mảng liền nhau. Chúng có thể phải giữ **ô trống**, **tombstone**, fingerprint hoặc metadata DIB. Các triển khai tối ưu có thể tách **control bytes** khỏi mảng giá trị để tra cứu theo nhóm ô.

Cuckoo hashing cần ngân sách dung lượng cho các vị trí ứng viên. Hopscotch cần bitmap cho từng ô gốc, chi phí xấp xỉ \(mH\) bit nếu dùng \(H\) bit/ô gốc. MPHF có thể chỉ cần **vài bit mỗi khóa cho cấu trúc định vị**, nhưng **không đồng nghĩa** toàn bộ hệ thống chỉ cần vài bit mỗi khóa: bảng giá trị, khóa gốc hoặc cấu trúc xác minh thành viên vẫn cần lưu nếu bài toán yêu cầu.

### Chi phí tạm thời khi rebuild

Nếu xây bảng mới bên cạnh bảng cũ rồi **chuyển đổi nguyên tử**, mức RAM cao nhất trong quá trình chuyển đổi có thể chứa **cả hai bảng** cùng lúc, cộng bộ đệm và metadata. Một ứng dụng vận hành ở 95% ngân sách bộ nhớ sẽ khó chịu được kiểu rebuild này dù bảng ổn định sau rebuild vẫn vừa RAM.

Vì vậy, kế hoạch bộ nhớ nên phân biệt:

\[
\text{RAM ổn định}\quad\text{và}\quad\text{RAM đỉnh khi resize/rebuild}.
\]

## 7. Độ trễ p99 và rủi ro “một lần chậm”

Độ trễ của một phép toán thường phụ thuộc nhiều thành phần:

\[
\begin{aligned}
T_{\mathrm{op}}\approx
&\ T_{\mathrm{hash}}+T_{\mathrm{probe/compare}}\\
&+T_{\mathrm{allocate/move}}+T_{\mathrm{resize}}\\
&+T_{\mathrm{sync}}+T_{\mathrm{memory/IO}}.
\end{aligned}
\]

Đây là **mô hình chia thành phần**, không phải các khoản luôn độc lập hay cộng tuyến tính đúng tuyệt đối: cache, nhánh CPU và lịch luồng có thể tương tác. Nó giúp tránh nhận định “ít phép so sánh hơn chắc chắn nhanh hơn”.

| Nguồn đột biến độ trễ | Biến thể dễ gặp | Điều cần đo |
| --- | --- | --- |
| Cụm thăm dò dài | Linear probing, Robin Hood | Số probe p95/p99, hit vs miss |
| Chèn đẩy nhiều khóa | Cuckoo | Số kick, thất bại, tần suất rehash |
| Kéo ô trống không thành công | Hopscotch | Số lần dịch chuyển, tỷ lệ rebuild |
| Tranh chấp và cấp phát node | Chaining trong một số cài đặt | Cache miss, allocator, khóa đồng bộ |
| Resize toàn bảng | Nhiều bảng băm động | Thời gian resize, RAM đỉnh, số phần tử được dời |
| Tách bucket/nhân đôi directory | Extendible hashing | Số trang được đọc/ghi, số mục directory sao chép |
| Chuỗi trang tràn dài | Linear hashing | Số trang tràn truy cập mỗi truy vấn |
| Di chuyển shard/replica | Consistent hashing | Độ trễ mạng, băng thông, replica lag |
| Rebuild tập khóa tĩnh | Perfect/MPHF | Thời gian tạo chỉ mục, thời gian chuyển phiên bản |

### Ba mức bảo đảm cần tách rời

1. **Thời gian kỳ vọng thấp:** mô tả trung bình trên một phân bố ngẫu nhiên hoặc giả thiết về hàm băm. Ví dụ một số biến thể đạt \(O(1)\) kỳ vọng cho phép tra cứu.
2. **Chi phí phân bổ thấp:** nhiều thao tác cộng lại có tổng chi phí nhỏ dù có thao tác đơn lẻ phải resize \(O(n)\).
3. **Trường hợp xấu nhất có giới hạn rõ:** ví dụ cây tìm kiếm cân bằng có \(O(\log n)\) cho tra cứu/chèn/xóa; cuckoo hai ứng viên có **tra cứu** tối đa hai ô khi bất biến đúng, nhưng **chèn** không được bảo đảm tương tự.

Nếu hệ thống có deadline nghiêm ngặt cho **mọi thao tác chèn**, không thể lấy riêng bảo đảm tra cứu ngắn của cuckoo hay hopscotch làm bằng chứng. Có thể cần cấu trúc có bảo đảm cập nhật, cấp phát tĩnh, kỹ thuật cập nhật gia tăng hoặc thiết kế theo yêu cầu thời gian thực cụ thể.

## 8. Hàm băm, loại khóa và đầu vào đối kháng

Không có cấu trúc bảng băm nào hoạt động tốt nếu hàm băm dồn phần lớn khóa vào một vùng nhỏ. Chất lượng hàm băm phải phù hợp với:

- **Phân bố khóa:** số liên tiếp, chuỗi có tiền tố giống nhau, ID ngẫu nhiên, dữ liệu có quy luật.
- **Tính bằng nhau:** hai khóa mà ứng dụng coi là bằng nhau phải nhận cùng giá trị băm theo hợp đồng.
- **Chi phí băm:** chuỗi dài và bản ghi phức tạp có thể cần \(O(L)\) thời gian xử lý độ dài \(L\).
- **Tính ổn định:** khi lưu hash hoặc token qua nhiều lần chạy, cần quy định rõ thuật toán, seed và mã hóa dữ liệu; hash runtime có thể không ổn định giữa tiến trình.
- **Tính đối kháng:** khóa do người dùng không tin cậy chọn có thể được thiết kế để kích hoạt nhiều va chạm.

### Hash flooding

Với chaining dùng danh sách liên kết, nếu kẻ tấn công đưa \(n\) khóa vào cùng một bucket, tra cứu một khóa ở cuối chuỗi hoặc tìm miss có thể tốn \(O(n)\). Tình huống này có thể dẫn tới **từ chối dịch vụ dựa trên độ phức tạp thuật toán**.

Phòng vệ có thể dùng **keyed hashing** (ví dụ SipHash theo mô hình phù hợp), seed bí mật, hạn mức khóa/yêu cầu, hoặc bucket có cơ chế chống suy biến. Băm mật mã **không khóa** chỉ để lấy chỉ số bucket không tự ngăn được hash flooding; việc rút gọn về \(m\) bucket vẫn tạo va chạm.

**Đừng nhầm lựa chọn biến thể bảng băm với lựa chọn hàm băm mật mã.** Hash tra cứu chọn vị trí; hash mật mã như SHA-256 hướng đến chống các kiểu tấn công vào digest đầy đủ. Lưu mật khẩu còn cần cơ chế KDF chuyên dụng với salt, không nên dùng hash tra cứu hoặc SHA-256 nhanh đơn lẻ để thay thế.

### Khóa thay đổi sau khi chèn

Nếu khóa là object có những trường tham gia hash và phép so sánh bằng nhau, thay đổi các trường đó sau khi đưa object vào bảng có thể khiến truy vấn không tìm ra phần tử. Cách an toàn là dùng **khóa bất biến**, hoặc xóa bản ghi cũ rồi chèn lại với khóa mới.

## 9. Đồng thời, cache và phần cứng có thể đảo ngược lựa chọn

Phân tích tiệm cận cần được đối chiếu với môi trường triển khai:

**Trong RAM một luồng:** Open addressing có thể có lợi thế nhờ bố trí dữ liệu liên tiếp. Tuy nhiên, lợi ích này phụ thuộc kích thước khóa/giá trị, cache line và cách triển khai metadata.

**Trong hệ có nhiều luồng ghi:** Chèn kiểu Robin Hood hoặc cuckoo có thể di chuyển nhiều khóa, tạo ra trạng thái trung gian cần đồng bộ chính xác. Chaining có thể cho phép khóa riêng từng bucket nhưng cũng có thể gặp tranh chấp khi nhiều khóa nóng cùng bucket. **Không có biến thể nào mặc nhiên thread-safe** chỉ vì thuật toán tuần tự đúng.

**Trong môi trường có garbage collector:** Nhiều node nhỏ trong chaining có thể tăng áp lực GC. Mảng lớn của open addressing có thể giảm số object cấp phát, nhưng resize lại tạo mảng lớn mới và gây RAM đỉnh.

**Trên đĩa/SSD:** Chi phí I/O theo trang thường quan trọng hơn vài phép tính modulo. Extendible hashing và linear hashing được thiết kế thuận tiện cho việc tăng/tách bucket theo trang; nên đo số trang đọc/ghi và độ dài overflow.

**Trên nhiều máy:** Lựa chọn nút bằng consistent hashing giúp giảm thay đổi ánh xạ khi scale cluster. Nhưng nó không thay thế chỉ mục cục bộ hay cơ chế sao chép, quorum, chuyển giao dữ liệu, xử lý nút hỏng.

Một phép đánh giá có giá trị phải đo **trên cùng phần cứng và cùng cách cấp phát**, thay vì so một triển khai nhiều tối ưu SIMD với một ví dụ thuật toán thuần Python rồi quy mọi chênh lệch cho tên biến thể.

## 10. Quy trình chọn biến thể theo cây quyết định

Quy trình dưới đây là **heuristic lựa chọn ứng viên** chứ không phải thuật toán quyết định tuyệt đối.

~~~mermaid
flowchart TD
    A["Cần lưu và truy vấn khóa?"] --> B{"Cần thứ tự / range query?"}
    B -->|Có| C["Cân nhắc cây tìm kiếm, B-tree/B+ tree"]
    B -->|Không| D{"Phân phối giữa nhiều máy?"}
    D -->|Có| E["Consistent/rendezvous hashing để chọn nút và chỉ mục cục bộ"]
    D -->|Không| F{"Bucket dữ liệu nằm trên trang đĩa?"}
    F -->|Có| G["Cân nhắc extendible hoặc linear hashing"]
    F -->|Không| H{"Tập khóa gần như bất biến?"}
    H -->|Có| I["Perfect hashing hoặc MPHF kèm kiểm tra thành viên"]
    H -->|Không| J{"Đọc chiếm ưu thế và cần đường tra cứu ngắn?"}
    J -->|Có| K["Cuckoo hai lựa chọn hoặc hopscotch, đo chi phí ghi"]
    J -->|Không| L["Chaining, linear probing, Robin Hood, đo tải và p99"]
~~~

### Cách dùng cây quyết định

1. **Loại các cấu trúc không hỗ trợ chức năng bắt buộc.** Nếu cần range query, một hash table đơn thuần không phù hợp dù điểm benchmark tốt.
2. **Xác định ràng buộc cứng:** giới hạn RAM, cấm cấp phát trong đường xử lý quan trọng, thời gian tệ nhất, phân tán hay đồng thời.
3. **Chọn hai hoặc ba ứng viên gần mục tiêu nhất.** Không nên benchmark hàng chục biến thể chỉ để tối ưu một chỉ số không quan trọng.
4. **Thiết kế phép đo có cả workload thường và bất lợi.** Đo read-hit, read-miss, insert mới, overwrite, delete, resize và truy vấn theo độ dài khóa.
5. **Lấy quyết định bằng cả hiệu năng lẫn tính đúng và độ phức tạp vận hành.** Một cấu trúc đơn giản, phổ biến và dễ bảo trì có thể tốt hơn một cấu trúc tối ưu lý thuyết nhưng có chi phí vận hành cao.

Nếu chỉ cần một dictionary/set trong ứng dụng thông thường, **collection chuẩn của ngôn ngữ** thường là điểm xuất phát hợp lý. Các thư viện chuẩn đã xử lý nhiều chi tiết khó như equality, resize và quản lý bộ nhớ; hãy chứng minh nút thắt bằng đo đạc trước khi viết một hash table tùy biến.

## 11. Sáu kịch bản chọn cấu trúc cụ thể

### Kịch bản A — Từ điển bất biến, tra cứu rất nhiều

Một ứng dụng cần tra cứu một **tập 2 triệu mã phân loại**, xây dựng từ dữ liệu phát hành theo phiên bản. Trong suốt một phiên bản, tập khóa **không thay đổi**; mỗi bản ghi có một giá trị đi kèm.

**Ứng viên mạnh:** perfect hashing hoặc **MPHF** nếu ngân sách xây dựng chỉ mục cho phép, đặc biệt khi ưu tiên độ gọn và tra cứu nhiều lần. Nếu giá trị cần cập nhật thường xuyên nhưng **khóa không đổi**, có thể duy trì mảng giá trị theo chỉ số MPHF.

**Điều kiện bắt buộc:** MPHF chỉ định vị chính xác các khóa **thuộc tập xây dựng**. Truy vấn một khóa mới chưa có vẫn có thể trả chỉ số; ứng dụng phải dùng khóa gốc, fingerprint với mức sai số chấp nhận được, hoặc cơ chế xác nhận thành viên khác.

**Không nên chọn ngay:** MPHF cho một tập khóa thay đổi mỗi giây nếu việc xây lại sẽ vượt quá khả năng CPU và thời gian triển khai.

### Kịch bản B — Cache trong RAM, đọc nhiều nhưng thường xóa và ghi

Một bộ nhớ đệm có 300.000 khóa, 70% đọc, 20% ghi và 10% xóa; giá trị nhỏ, yêu cầu p99 tốt.

**Ứng viên:** collection chuẩn, **Robin Hood hashing** hoặc một bảng dạng mảng được tối ưu cache. Chaining cũng có thể phù hợp nếu dữ liệu thay đổi nhiều và triển khai sử dụng bucket/node hiệu quả.

**Cần đo:** tỷ lệ miss, chi phí dịch lùi sau xóa, tombstone nếu có, độ trễ resize, RAM đỉnh, hiệu ứng GC. Không nên quyết định Robin Hood “thắng” chỉ từ trung bình DIB thấp: với nhiều lần xóa hoặc chèn, số bản ghi dịch chuyển có thể ảnh hưởng p99.

**Cách bắt đầu:** dùng container chuẩn, reserve theo quy mô dự kiến, xây benchmark trước khi thay bằng cấu trúc tùy biến.

### Kịch bản C — Tra cứu p99 rất quan trọng, chèn hiếm

Một chỉ mục trong RAM phục vụ API đọc, phần lớn thời gian chỉ tìm kiếm; cập nhật khóa chủ yếu xảy ra trong các đợt triển khai dữ liệu.

**Ứng viên:** nếu tập khóa hoàn toàn tĩnh giữa các phiên bản, cân nhắc **perfect hashing/MPHF**. Nếu vẫn phải cập nhật online, **cuckoo hai lựa chọn** hoặc **hopscotch với \(H\) cố định** giúp giới hạn số ô cần đọc sau khi đã duy trì đúng bất biến.

**Đánh đổi:** chèn/rebuild có thể tốn thời gian lớn hơn. Nên thực hiện cập nhật ở phiên bản mới và chuyển đổi an toàn nếu yêu cầu hệ thống cho phép, đồng thời tính **RAM đỉnh**.

**Không suy diễn:** tra cứu bị giới hạn số ô không có nghĩa độ trễ mạng, cache miss hoặc chèn cũng có giới hạn thời gian thực.

### Kịch bản D — Bảng đạt tải cao vì RAM đắt

Một tiến trình có giới hạn RAM chặt và cần lưu 1 triệu bản ghi trong mảng. Chủ yếu là đọc, nhưng có 40% yêu cầu tìm thất bại. Nhóm thiết kế cân nhắc đẩy tải từ 0,70 lên 0,90.

**Ứng viên:** so sánh **Robin Hood**, open addressing có metadata và kỹ thuật probing phù hợp; thử các giá trị tải cụ thể. Cuckoo hai lựa chọn **cổ điển** thường đòi hỏi khoảng trống đáng kể nên không tự nhiên phù hợp nếu chỉ tiêu là **mức lấp đầy rất cao**. Các biến thể nhiều lựa chọn hoặc bucket hóa có ngưỡng khác, nhưng phải kiểm chứng độc lập.

**Cần đo:** p99 tìm thất bại, RAM metadata, throughput và số lần resize. Mô hình tuyến tính ở mục 2 cho thấy việc tiết kiệm khoảng 5 MB trong ví dụ có thể kéo theo tăng đáng kể số ô phải đọc lúc miss.

**Cảnh báo:** không nên áp ngưỡng tải 0,90 cho mọi cấu trúc mà bỏ qua cơ chế va chạm; một mức tải phù hợp với chaining có thể không phù hợp với cuckoo hai lựa chọn.

### Kịch bản E — Chỉ mục lưu trên SSD, tập dữ liệu tăng dần

Một hệ thống lưu hàng chục triệu bản ghi, mỗi bucket tương ứng trang đĩa. Khối lượng ghi tăng liên tục, muốn hạn chế việc viết lại toàn bộ tệp.

**Ứng viên:** **extendible hashing** hoặc **linear hashing**.

- Extendible hashing tách bucket đang đầy và tăng số bit của thư mục khi cần; hữu ích khi chấp nhận metadata directory.
- Linear hashing dùng **split pointer** để tách tuần tự, mỗi lần thêm một bucket chính; tránh nhân đôi toàn bộ directory, nhưng một bucket đang tràn có thể phải chờ đến lượt tách.

**Cần đo:** I/O theo trang, số trang tràn, chi phí flush/fsync, số lần nhân đôi directory, write amplification, khả năng phục hồi sau sự cố. Ở môi trường này, benchmark phép tính modulo trong RAM **không đủ** để đưa ra quyết định.

### Kịch bản F — Kho dữ liệu phân tán, thường thêm và loại nút

Một cụm có hàng chục máy lưu đối tượng theo khóa. Khi scale, hệ thống muốn chuyển ít dữ liệu và giảm thời gian phục hồi.

**Ứng viên:** **consistent hashing** với vnode hoặc **rendezvous hashing** để **phân chia khóa giữa các máy**. Sau khi khóa đã được định tuyến tới một máy, máy đó vẫn cần một bảng băm hoặc chỉ mục cục bộ.

**Cần đo:** tỷ lệ dữ liệu di chuyển khi thay đổi membership, phân bố byte và yêu cầu trên mỗi nút, hotspot, độ trễ replica, lỗi mạng và failover. Consistent hashing chỉ tạo **quy tắc chọn nơi lưu**, không tự di chuyển bản ghi hoặc bảo đảm tính nhất quán đọc–ghi.

### So sánh nhanh theo mục tiêu

| Mục tiêu chính | Ưu tiên khảo sát | Cần cảnh giác |
| --- | --- | --- |
| Tập khóa bất biến, dữ liệu gọn | MPHF/perfect hashing | Kiểm tra khóa ngoài tập, chi phí xây chỉ mục |
| Đọc p99 ngắn với cập nhật ít | Cuckoo/hopscotch hoặc chỉ mục tĩnh | Đợt chèn/rebuild tốn công |
| Ghi/xóa nhiều trong RAM | Chaining, Robin Hood, container chuẩn | Cấp phát, dịch chuyển, cache miss |
| Tiết kiệm ô dữ liệu, tải cao | Open addressing được đo cụ thể | Probe miss và p99 tăng ở tải cao |
| Mở rộng theo trang đĩa | Extendible/linear hashing | Directory hoặc overflow page |
| Thay đổi nút phân tán | Consistent/rendezvous hashing | Chuyển dữ liệu, replica, membership |
| Cần thứ tự và khoảng khóa | Cây cân bằng, B-tree/B+ tree | Hash table không sắp thứ tự khóa |

Các hàng là **điểm khởi đầu thử nghiệm**, không phải bảng xếp hạng hiệu năng tuyệt đối.

## 12. Đo hiệu năng đúng: kiểm tra cả tốc độ lẫn tính đúng

Một benchmark dùng để chọn biến thể phải trả lời được ba câu hỏi: **đo trên workload nào, đo chỉ số nào và điều kiện so sánh có công bằng không?**

### Bộ chỉ số tối thiểu

| Chỉ số | Lý do |
| --- | --- |
| Throughput đọc hit và miss riêng | Miss thường nhạy với cluster hoặc chuỗi dài |
| Throughput chèn khóa mới | Đo chi phí xử lý va chạm và cấp phát |
| Throughput cập nhật giá trị có sẵn | Khác với chèn làm tăng số khóa |
| Throughput xóa | Bộc lộ tombstone, backward shift hoặc quản lý node |
| p50, p95, p99 cho từng loại thao tác | Trung bình không thể hiện tail latency |
| Số probe, DIB, kick hoặc lần dời khóa | Giúp giải thích tại sao một biến thể nhanh/chậm |
| RAM ổn định và RAM đỉnh | Rehash/rebuild có thể tạm dùng cả bảng cũ và mới |
| Số lần resize/rehash và thời gian mỗi lần | Bộc lộ các thao tác hiếm nhưng tốn kém |
| CPU, cache miss, GC/allocator nếu có | Phân biệt chi phí thuật toán và đặc tính runtime |
| Số I/O trang hoặc byte di chuyển | Thiết yếu cho hash theo trang và hệ phân tán |

### Kiểm soát biến gây nhiễu

1. Dùng **cùng số phần tử**, cùng kiểu khóa và cùng phân bố truy vấn giữa các ứng viên.
2. Đo ở **nhiều mức tải**, không chỉ một trạng thái; chẳng hạn 0,5, 0,7, 0,85 và mức gần ngưỡng mà cấu trúc cho phép.
3. Tách workload **read-hit**, **read-miss**, **insert**, **update-value** và **delete**; sau đó đo thêm workload hỗn hợp đúng tỷ lệ sản phẩm.
4. Thử khóa ngẫu nhiên, khóa có cấu trúc, khóa dài, hot key và dữ liệu có khả năng gây collision; không chỉ dùng một tập khóa dễ.
5. Thực hiện warm-up nếu môi trường có JIT/cache, đo nhiều lần, ghi **phân bố** kết quả và công bố sai số/độ biến động.
6. Bảo đảm bảng đã ở trạng thái hợp lệ sau chèn/xóa; so sánh kết quả với một tập hợp/từ điển tham chiếu đáng tin cậy.
7. Ghi rõ **điều kiện bộ nhớ**: dung lượng mảng, chính sách reserve, allocator, metadata, phiên bản runtime và phần cứng.
8. Đếm chi phí resize riêng hoặc báo cáo cả khi resize xảy ra. Nếu benchmark chỉ đo lookup sau khi đã dựng xong bảng, phải ghi rõ **chưa đo chi phí xây dựng**.

## 13. Python minh họa phép đo số lần thăm dò theo tải

Đoạn mã sau xây một **tập hợp linear probing thuần túy để học** và đếm số ô được kiểm tra khi tìm khóa. Nó không phải thư viện hash table sản xuất và **không dùng để kết luận** biến thể nào nhanh hơn trên CPU. Mục tiêu là quan sát cùng một chỉ số — **số probe** — khi tăng hệ số tải và tách **hit/miss**.

~~~python
import math
import random


class LinearProbingProbeCounter:
    def __init__(self, capacity):
        if type(capacity) is not int or capacity < 2:
            raise ValueError("capacity phải là số nguyên >= 2")
        self.slots = [None] * capacity
        self.size = 0

    def _start(self, key):
        if type(key) is not int or key < 0:
            raise TypeError("Ví dụ chỉ hỗ trợ khóa nguyên không âm")
        return key % len(self.slots)

    def add(self, key):
        capacity = len(self.slots)
        start = self._start(key)
        for step in range(capacity):
            i = (start + step) % capacity
            if self.slots[i] == key:
                return False  # Khóa đã tồn tại.
            if self.slots[i] is None:
                self.slots[i] = key
                self.size += 1
                return True
        raise RuntimeError("Bảng đầy, cần resize")

    def find_with_probes(self, key):
        capacity = len(self.slots)
        start = self._start(key)
        for step in range(capacity):
            i = (start + step) % capacity
            if self.slots[i] is None:
                return False, step + 1
            if self.slots[i] == key:
                return True, step + 1
        return False, capacity


def percentile_nearest_rank(values, fraction):
    if not values or not (0 < fraction <= 1):
        raise ValueError("Cần dữ liệu và phân vị hợp lệ")
    data = sorted(values)
    return data[math.ceil(fraction * len(data)) - 1]


capacity = 4096

for target_load in (0.50, 0.75, 0.90):
    rng = random.Random(2026)
    n = int(capacity * target_load)
    keys = rng.sample(range(2_000_000_000), n)
    # Tập misses nằm ở một miền số nguyên không trùng tập keys.
    misses = rng.sample(range(2_000_000_000, 4_000_000_000), 1500)

    table = LinearProbingProbeCounter(capacity)
    for key in keys:
        table.add(key)

    hit_probes = [table.find_with_probes(k)[1] for k in keys[:1500]]
    miss_probes = [table.find_with_probes(k)[1] for k in misses]

    assert all(table.find_with_probes(k)[0] for k in keys)
    assert all(not table.find_with_probes(k)[0] for k in misses)

    print(
        f"alpha={table.size / capacity:.3f} | "
        f"hit_mean={sum(hit_probes) / len(hit_probes):.2f} | "
        f"hit_p99={percentile_nearest_rank(hit_probes, 0.99)} | "
        f"miss_mean={sum(miss_probes) / len(miss_probes):.2f} | "
        f"miss_p99={percentile_nearest_rank(miss_probes, 0.99)}"
    )
~~~

**Cách diễn giải khi tự chạy mã:**

- Số ô mảng cố định là **4096**, chỉ thay đổi số khóa để tạo các mức tải khác nhau.
- Khóa được lấy mẫu bằng bộ sinh ngẫu nhiên cố định để kết quả có thể tái lập trong ví dụ. Không có resize hoặc xóa trong phép mô phỏng này.
- Giá trị **hit_mean** và **miss_mean** là số probe trung bình; **hit_p99/miss_p99** là phân vị gần nhất theo số probe, **không phải số mili-giây độ trễ**.
- Kết quả ngẫu nhiên cụ thể không bắt buộc trùng các con số lý thuyết trong mục 2 vì kích thước hữu hạn, tập mẫu, hàm băm modulo và phương sai.
- Không lấy kết quả Python này để xếp hạng các thư viện C/C++/Java có cấu trúc ô, vector hóa, bộ nhớ và allocator khác nhau.

**Bài tập mở rộng:** Giữ nguyên số khóa và thêm một workload có **90% truy vấn miss**; so sánh tổng số probe với workload **90% truy vấn hit**. Tiếp tục thử các giá trị **capacity** khác, rồi vẽ đường p99 theo tải. Khi muốn so sánh Robin Hood và cuckoo, hãy hiện thực đúng bất biến của từng cấu trúc, dùng **cùng tập khóa và truy vấn**, và kiểm tra kết quả tìm kiếm trước khi đánh giá hiệu năng.

## 14. Sai lầm dễ mắc khi lựa chọn biến thể

1. **Chỉ nhìn \(O(1)\) rồi kết luận mọi hash table nhanh như nhau.** Các loại \(O(1)\) kỳ vọng, phân bổ và trường hợp xấu nhất không tương đương; bộ nhớ và cache ảnh hưởng thời gian thật.
2. **So sánh hệ số tải khi các cấu trúc dùng mẫu số khác nhau.** Với cuckoo hai mảng phải tính trên tổng số ô của cả hai mảng.
3. **Chỉ benchmark tìm thành công.** Ở tải cao, tìm thất bại có thể đắt hơn nhiều, đặc biệt với linear probing.
4. **Đo trung bình nhưng bỏ qua p95/p99.** Những lần resize, rehash, cấp phát hoặc di chuyển nhiều phần tử có thể phá mục tiêu độ trễ.
5. **Cho rằng ít ô phải tra cứu cũng nghĩa là chèn nhanh.** Cuckoo và hopscotch giữ đường tra cứu ngắn bằng các quy tắc cập nhật phức tạp hơn.
6. **Dùng MPHF như kiểm tra thành viên không cần xác minh.** MPHF thuần túy chỉ bảo đảm ánh xạ hoàn hảo đối với tập khóa tĩnh đã xây dựng.
7. **Ghi nhận chỉ RAM ổn định.** Rebuild có thể cần đồng thời bảng cũ và mới; RAM đỉnh có thể cao hơn rất nhiều.
8. **Không tính chi phí so sánh khóa dài.** Thời gian tính hash một chuỗi dài thường phụ thuộc độ dài chuỗi; ký hiệu \(O(1)\) theo số khóa không phủ nhận chi phí này.
9. **Không kiểm tra đầu vào đối kháng.** Hàm băm nhanh nhưng dễ đoán có thể bị dùng để tạo nhiều va chạm; cần thiết kế bảo vệ phù hợp.
10. **Sử dụng cấu trúc không bảo toàn thứ tự cho range query.** Nếu cần tìm các khóa trong khoảng, B-tree/B+ tree hoặc cấu trúc có thứ tự thường thích hợp hơn.
11. **Nhầm băm nhất quán với bảng băm cục bộ.** Một bên chọn máy, bên kia chọn ô/bucket trong máy; hệ thống phân tán có thể cần cả hai.
12. **Gộp chi phí I/O với số phép băm.** Trong hash theo trang, một lần đọc trang hoặc một lần ghi fsync có thể chi phối chi phí nhiều hơn phép modulo.
13. **Cho rằng resize không ảnh hưởng các phép đọc đang chạy.** Với nhiều luồng, cần bảo vệ con trỏ, phiên bản bảng và dữ liệu trong lúc chuyển đổi.
14. **Đánh giá từ mã mẫu rồi ngoại suy thành năng suất sản xuất.** Code giáo trình chủ yếu minh họa bất biến, thường chưa có tối ưu phần cứng, đồng bộ, xử lý lỗi và quan sát vận hành.
15. **Chọn biến thể độc đáo dù cấu trúc chuẩn đã đủ.** Độ phức tạp bảo trì, rủi ro lỗi và khả năng đào tạo nhóm cũng là chi phí thật.

## 15. Câu hỏi tự kiểm tra kèm lời giải

### Câu 1. Tính tải và phân biệt mẫu số

Một bảng open addressing có 100.000 ô, lưu 75.000 khóa. Một bảng cuckoo **hai mảng**, mỗi mảng 100.000 ô, cũng lưu 75.000 khóa. Hệ số tải của chúng là bao nhiêu?

**Lời giải:** Với open addressing một mảng:

\[
\alpha_{\mathrm{open}}=\frac{75\,000}{100\,000}=0{,}75.
\]

Với cuckoo hai mảng:

\[
\alpha_{\mathrm{cuckoo}}=\frac{75\,000}{200\,000}=0{,}375.
\]

Hai cấu trúc cùng lưu 75.000 khóa nhưng **khác số ô vật lý**, nên không được nhầm các hệ số tải.

### Câu 2. Chaining có thể vượt tải 1 không?

Một bảng separate chaining có 100.000 bucket và 250.000 khóa. Tải là bao nhiêu? Điều đó có chứng tỏ cấu trúc không hợp lệ không?

**Lời giải:**

\[
\alpha=\frac{250\,000}{100\,000}=2{,}5.
\]

Chaining cho phép một bucket chứa nhiều khóa, nên **tải lớn hơn 1 vẫn hợp lệ**. Nếu băm đều, độ dài bucket trung bình là khoảng 2,5 bản ghi; tuy nhiên có thể xuất hiện những bucket dài hơn. Cần đo chi phí tra cứu và bộ nhớ của node, không xem 2,5 là lỗi.

### Câu 3. Tính bộ nhớ ô dữ liệu

Một bảng mảng cần lưu \(n=1\,000\,000\) bản ghi, mỗi ô giả định 16 byte. Nếu giữ tải \(\alpha=0{,}80\) thì riêng mảng ô chiếm khoảng bao nhiêu? Nếu tăng tải lên 0,90, tiết kiệm được bao nhiêu?

**Lời giải:**

\[
\begin{aligned}
M_{0.80}&=\frac{1\,000\,000\cdot16}{0{,}8}=20\text{ MB},\\
M_{0.90}&\approx\frac{1\,000\,000\cdot16}{0{,}9}
=17{,}78\text{ MB}.
\end{aligned}
\]

Tiết kiệm khoảng **2,22 MB thập phân** trong mô hình bỏ qua metadata/cấp phát. Việc tăng tải có thể làm lookup miss hoặc chèn chậm hơn; cần kiểm chứng p99 trước khi tối ưu theo bộ nhớ.

### Câu 4. Chọn cho tập khóa tĩnh

Một hệ thống phân loại có 500.000 khóa cố định, hàng triệu lượt tra cứu mỗi ngày. Nguồn yêu cầu đôi khi truy vấn một khóa lạ chưa nằm trong tập. Có nên dùng MPHF không, và cần lưu ý gì?

**Lời giải:** **Có thể** dùng MPHF vì tập khóa tĩnh và lookup nhiều. Nhưng MPHF chỉ bảo đảm không trùng chỉ số **giữa các khóa thuộc tập xây dựng**; với khóa lạ nó vẫn có thể trả chỉ số. Phải bổ sung **kiểm tra thành viên chính xác** hoặc fingerprint với mức sai số được xác định rõ. Đồng thời tính cả chi phí xây chỉ mục và lưu giá trị.

### Câu 5. Chọn khi p99 chèn cực kỳ quan trọng

Một dịch vụ nhạy độ trễ đòi hỏi mỗi lần chèn kết thúc trong một deadline rất nhỏ, không cho phép thao tác đơn lẻ tốn \(O(n)\). Có thể chọn cuckoo cơ bản chỉ vì tìm kiếm tối đa hai ô không?

**Lời giải:** **Không.** Bảo đảm hai ô áp dụng cho **tra cứu** ở biến thể hai lựa chọn đã xây hợp lệ, còn chèn có thể đẩy nhiều khóa hoặc phải rehash. Cần phân tích giải pháp có bảo đảm cập nhật phù hợp, chiến lược reserve/rebuild ngoài đường quan trọng hoặc cấu trúc khác; với yêu cầu trường hợp xấu nhất, một cây cân bằng có giới hạn \(O(\log n)\) là ứng viên cần cân nhắc, dù cũng phải tính chi phí hệ thống.

### Câu 6. Vì sao hai loại truy vấn có kết quả khác nhau?

Một bộ máy tìm kiếm có bảng linear probing rất đầy, 80% câu hỏi là tìm **khóa không tồn tại**. Nhóm đã benchmark chỉ phép tìm thành công và thấy tốc độ tốt. Kết luận có đáng tin không?

**Lời giải:** **Chưa.** Trong linear probing, tìm thất bại có thể phải duyệt tới ô trống ở cuối cụm, thường dài hơn tìm thành công ở tải cao. Phải benchmark đúng **80% miss**, đo p95/p99 số probe và độ trễ, rồi so với cấu hình tải thấp hơn hoặc biến thể khác.

### Câu 7. Hash theo trang đĩa

Một hệ dữ liệu có bucket lưu theo trang SSD; số bản ghi tăng liên tục nhưng không muốn có lần rebuild toàn tệp. Nêu hai lựa chọn hợp lý và khác biệt chính.

**Lời giải:** Có thể khảo sát **extendible hashing** và **linear hashing**. Extendible tách bucket đầy, có thể phải nhân đôi **directory** khi local depth bằng global depth. Linear hashing thêm một bucket mỗi lần tách theo **split pointer**, không cần directory nhân đôi, nhưng có thể để bucket bị tràn chờ lượt. Quyết định phụ thuộc metadata và số lần I/O thực tế.

### Câu 8. Phân tán nhiều nút

Một dịch vụ đang lưu dữ liệu trên 12 nút và thường bổ sung hoặc rút nút. Nhóm muốn giảm lượng khóa đổi máy. Băm nhất quán có thay thế bảng băm trong từng nút không?

**Lời giải:** **Không.** Consistent hashing quyết định **nút vật lý sở hữu khóa**; bên trong nút vẫn cần chỉ mục như bảng băm hoặc cây. Ngoài ra, thay đổi vòng băm chỉ đổi **quy tắc định tuyến**, hệ thống còn phải chuyển dữ liệu thật và xử lý replica, failover, membership.

### Câu 9. Hash flooding

Một API nhận khóa do khách tự chọn. Nhóm dự định dùng hash nhanh không khóa và bảng chaining danh sách liên kết. Rủi ro là gì, và hướng xử lý?

**Lời giải:** Khách có thể cố tạo nhiều khóa cùng bucket, làm thao tác suy biến về \(O(n)\) và tăng CPU. Có thể cân nhắc **keyed hashing** được thiết kế cho mục đích này, giới hạn tài nguyên, chính sách kích thước bảng hoặc cơ chế bucket chống suy biến. Băm SHA-256 không khóa rồi lấy modulo không tự loại bỏ va chạm bucket.

### Câu 10. Đánh đổi bộ nhớ và độ trễ khi rebuild

Một bảng chiếm 1,2 GB RAM ổn định, máy chỉ còn 0,4 GB bộ nhớ trống. Việc xây bảng mới có kích thước tương đương cạnh bảng cũ có chắc chắn an toàn không?

**Lời giải:** **Không.** Xây song song có thể cần thêm xấp xỉ 1,2 GB hoặc hơn cho mảng mới và metadata, vượt 0,4 GB đang trống. Phải ước lượng **RAM đỉnh**, hoặc chọn resize tăng dần, tái sử dụng bộ nhớ, chuyển đổi theo từng bucket hay một quy trình rebuild ngoài máy/ngoài tiến trình phù hợp.

## 16. Quy trình chốt lựa chọn cho một dự án

Trước khi quyết định, hãy lập một hồ sơ ngắn với đủ bốn trục:

| Trục | Ví dụ yêu cầu có thể kiểm chứng |
| --- | --- |
| **Tải** | Phải chứa tối đa 2 triệu khóa; đo tại \(\alpha=0{,}6,0{,}75,0{,}85\) khi cấu trúc cho phép |
| **Cập nhật** | Workload 80% read, 10% insert mới, 5% update-value, 5% delete |
| **Bộ nhớ** | Tổng RAM ổn định dưới 300 MB, RAM đỉnh dưới 450 MB khi resize |
| **Độ trễ** | Báo cáo p50/p95/p99 riêng cho hit, miss, chèn, xóa; xác định ngưỡng chấp nhận |

Tiếp đó **loại biến thể không đáp ứng chức năng**, chọn một tập ứng viên nhỏ, chạy phép đo trên cùng workload, xác nhận tính đúng và đánh giá **cả chi phí vận hành**. Nếu kết quả tương đương, ưu tiên cấu trúc dễ bảo trì, được thư viện hỗ trợ tốt và dễ kiểm chứng hơn.

## 17. Ghi nhớ

**Không có một biến thể bảng băm luôn tối ưu.** Chaining linh hoạt với cập nhật nhưng có thể tốn node/con trỏ; linear probing có cục bộ bộ nhớ tốt nhưng nhạy với tải cao; Robin Hood cân bằng khoảng cách thăm dò; cuckoo và hopscotch ưu tiên giới hạn đường tra cứu bằng cách tăng độ phức tạp chèn; perfect/MPHF phù hợp với tập khóa tĩnh; extendible/linear hashing hướng đến tăng trưởng theo trang; consistent hashing giải quyết **phân phối khóa giữa các nút**.

Hãy chọn biến thể dựa trên **bốn trục**:

1. **Tải:** định nghĩa đúng hệ số \(\alpha\), đo ở tải thực và chú ý số ô trống hoặc trang tràn.
2. **Cập nhật:** tách riêng chèn khóa mới, sửa giá trị, xóa và rebuild; xem cả thao tác hiếm nhưng chậm.
3. **Bộ nhớ:** tính dữ liệu, con trỏ, bitmap, metadata và **RAM đỉnh khi mở rộng**.
4. **Độ trễ:** đo riêng hit/miss và p95/p99; đừng nhầm kỳ vọng, chi phí phân bổ với giới hạn tệ nhất.

Cuối cùng, **kiểm tra tính đúng, chất lượng hàm băm và yêu cầu về môi trường** (RAM, SSD, nhiều luồng, nhiều nút) trước khi tin một bảng benchmark. Lựa chọn tốt là cấu trúc đáp ứng được workload và ràng buộc cụ thể với độ phức tạp vận hành có thể chấp nhận, không phải cấu trúc có tên hấp dẫn nhất.
