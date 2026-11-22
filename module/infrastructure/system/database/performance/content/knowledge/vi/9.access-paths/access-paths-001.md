# Trang dữ liệu, tổ chức lưu hàng và đường đi từ khóa đến bản ghi

## 1. Vì sao cần hiểu đường truy cập dữ liệu?

Khi một truy vấn SQL tìm một bản ghi, hệ quản trị cơ sở dữ liệu phải biến điều kiện logic như `user_id = 42` thành một chuỗi thao tác vật lý: tìm trang có khóa cần tra cứu, xác định vị trí bản ghi trong trang, đọc dữ liệu cần thiết và kiểm tra bản ghi có nhìn thấy được trong giao dịch hiện tại hay không. Chuỗi thao tác đó được gọi là đường truy cập dữ liệu (access path).

Hiệu năng phụ thuộc nhiều vào số trang phải chạm tới, khả năng các trang đã có trong bộ nhớ, mức độ liên tục của dữ liệu, số lần phải đi từ chỉ mục sang trang dữ liệu và lượng dữ liệu được đọc so với lượng dữ liệu truy vấn thực sự cần. Một truy vấn trả về vài dòng vẫn có thể chậm nếu mỗi dòng buộc hệ thống thực hiện một lần đọc ngẫu nhiên ở một trang khác nhau.

Trong tối ưu hiệu năng cơ sở dữ liệu, hiểu trang dữ liệu và cách tổ chức lưu hàng giúp giải thích vì sao cùng một câu SQL có thể chạy nhanh với một chỉ mục nhưng chậm với một chỉ mục khác; vì sao quét tuần tự đôi khi tốt hơn tra cứu chỉ mục; vì sao chỉ mục bao phủ giảm lượt truy cập bảng; và vì sao cập nhật dữ liệu có thể gây page split, phân mảnh hoặc tăng I/O.

Bài học này trình bày các khái niệm lưu trữ theo trang, bố cục bản ghi, heap và clustered organization, đường đi từ khóa qua B-tree hoặc hash đến bản ghi, buffer pool và các yếu tố cần đo khi chọn access path. Kích thước trang, cấu trúc byte, cách định vị bản ghi và thuật ngữ cụ thể khác nhau giữa các hệ quản trị; các sơ đồ dưới đây mô tả nguyên lý chung.

## 2. Trang dữ liệu là đơn vị lưu trữ và I/O

### 2.1. Từ bảng logic đến trang vật lý

Trong SQL, ta thao tác với bảng, hàng và cột. Ở tầng lưu trữ, hệ quản trị thường gom dữ liệu thành các trang (page hoặc block) có kích thước cố định hoặc được quản lý theo đơn vị trang. Một bảng lớn gồm nhiều trang; các trang có thể được nhóm thành extent, segment, partition hoặc đơn vị cấp phát tương đương tùy nền tảng.

Trang là đơn vị quan trọng vì hệ quản trị thường đọc, ghi, quản lý bộ nhớ đệm và đồng bộ dữ liệu theo trang. Khi truy vấn cần một hàng, hệ thống thường phải đưa trang chứa hàng đó vào buffer pool trước khi truy cập nội dung bản ghi. Vì vậy, chi phí không chỉ phụ thuộc số hàng trả về mà còn phụ thuộc số trang cần đọc và cách các trang được phân bố.

Kích thước trang là đặc tính của hệ quản trị và cấu hình. Không nên giả định mọi cơ sở dữ liệu đều dùng cùng kích thước, hoặc một trang luôn chứa một số lượng hàng cố định. Một trang có thể chứa nhiều hàng nhỏ, ít hàng rộng, hoặc dữ liệu ngoài hàng được lưu ở vùng khác.

### 2.2. Bố cục trang kiểu slotted page

Một cách tổ chức phổ biến cho trang lưu hàng là dùng header, vùng dữ liệu và một bảng khe (slot directory). Sơ đồ khái niệm:

```text
+--------------------------------------------------+
| Page header: loại trang, thông tin quản lý, ...   |
+--------------------------------------------------+
| Slot directory                                   |
| slot 0 -> offset của row A                       |
| slot 1 -> offset của row B                       |
| slot 2 -> offset của row C                       |
+--------------------------------------------------+
|                                                  |
| Free space                                       |
|                                                  |
+--------------------------------------------------+
| Row C                                            |
| Row B                                            |
| Row A                                            |
+--------------------------------------------------+
```

Bảng khe lưu vị trí hoặc thông tin định vị bản ghi trong trang. Nhờ có lớp gián tiếp này, hệ quản trị có thể di chuyển bản ghi bên trong trang để gom vùng trống mà vẫn giữ một định danh hàng ổn định ở mức trang và slot, tùy cơ chế của hệ thống.

Header có thể chứa thông tin quản lý trang, trạng thái, checksum hoặc dữ liệu phục vụ cơ chế giao dịch. Vùng trống được giữ lại để hỗ trợ chèn và cập nhật. Bản ghi thường được bố trí từ một phía, slot directory phát triển từ phía còn lại hoặc theo một bố cục tương đương.

Đây là mô hình phổ biến chứ không phải cam kết rằng mọi engine đều dùng đúng cấu trúc này. Một số hệ quản trị tổ chức record, slot, page header và vùng dữ liệu khác nhau; cần dùng tài liệu hoặc công cụ nội bộ của đúng engine để đọc byte-level layout.

### 2.3. Bản ghi có độ dài cố định và biến đổi

Hàng có thể chứa cột độ dài cố định như số nguyên, ngày giờ hoặc cột độ dài biến đổi như chuỗi, JSON và dữ liệu nhị phân. Hàng có nhiều cột biến đổi thường cần metadata để xác định offset hoặc độ dài của từng giá trị. NULL cũng có thể được biểu diễn bằng bitmap hoặc cấu trúc metadata riêng.

Một số loại dữ liệu lớn có thể được lưu ngoài phần bản ghi chính (out-of-row, overflow hoặc LOB storage). Khi truy vấn chỉ đọc các cột nhỏ, hệ quản trị có thể tránh tải toàn bộ dữ liệu lớn nếu cách lưu trữ và kế hoạch cho phép. Nếu truy vấn yêu cầu cột LOB, nó có thể cần thêm lần truy cập trang hoặc vùng lưu trữ khác.

Độ rộng hàng ảnh hưởng đến mật độ trang. Hàng càng rộng thì một trang thường chứa được càng ít hàng, làm tăng số trang cần đọc cho cùng một lượng bản ghi. Khi thiết kế bảng hoặc truy vấn, hãy cân nhắc chỉ đọc các cột cần thiết thay vì lấy mọi cột một cách mặc định.

## 3. Định danh bản ghi và cách tìm vị trí trong trang

### 3.1. Row locator

Khi chỉ mục trỏ đến một hàng trong heap, nó cần lưu thông tin định vị hàng (row locator hoặc bookmark). Định danh này có thể bao gồm số trang và số slot, row identifier (RID), tuple identifier (TID), địa chỉ logic hoặc khóa của cấu trúc clustered tùy hệ quản trị.

Một row locator thường không phải địa chỉ byte cố định của bản ghi. Nếu bản ghi được di chuyển trong trang, slot directory hoặc lớp ánh xạ có thể được cập nhật để định danh vẫn tìm đúng hàng. Cơ chế chính xác tùy engine và ảnh hưởng đến cách xử lý cập nhật, di chuyển hàng và bảo trì chỉ mục.

### 3.2. Từ page id đến row slot

Khi đã biết trang, hệ quản trị cần xác định bản ghi bên trong trang. Với mô hình slotted page, slot number dẫn đến offset của hàng. Sau đó engine đọc metadata của record để xác định ranh giới và diễn giải các cột cần thiết.

Có thể hình dung một row locator là cặp `(page_id, slot_id)`. Ví dụ, `(page 812, slot 6)` chỉ đến slot thứ 6 trong trang 812. Đây là ví dụ minh họa; định dạng row locator thực tế có thể khác và có thể chứa thêm thông tin kiểm tra phiên bản hoặc partition.

### 3.3. Tính nhìn thấy của bản ghi trong giao dịch

Trong hệ thống hỗ trợ MVCC (multi-version concurrency control), một vị trí vật lý có thể chứa phiên bản hàng được tạo hoặc cập nhật ở các thời điểm khác nhau. Khi đọc, hệ quản trị phải kiểm tra phiên bản nào nhìn thấy được theo snapshot và quy tắc cô lập của giao dịch hiện tại.

Vì vậy, tìm đúng trang và slot chưa đồng nghĩa hàng đó chắc chắn được trả về. Engine có thể cần kiểm tra metadata phiên bản, transaction id, trạng thái xóa hoặc visibility map tùy cơ chế. Một số chỉ mục bao phủ vẫn có thể cần bước kiểm tra khả năng nhìn thấy hàng trước khi trả kết quả.

## 4. Các cách tổ chức lưu hàng

### 4.1. Heap organization

Heap là cách lưu hàng mà thứ tự vật lý của hàng không được duy trì theo một khóa sắp xếp cụ thể. Hệ quản trị quản lý các trang còn chỗ hoặc dùng cấu trúc cấp phát để tìm vị trí chèn. Khi dữ liệu được chèn, hàng có thể nằm ở bất kỳ trang phù hợp nào theo chiến lược cấp phát.

Ưu điểm của heap là chèn hàng tương đối linh hoạt vì không cần duy trì thứ tự khóa trên toàn cấu trúc. Quét toàn bảng có thể đi qua các trang được cấp phát. Tuy nhiên, tìm một hàng theo khóa thường cần chỉ mục phụ trỏ đến row locator hoặc phải quét nhiều trang nếu không có access path phù hợp.

Heap không có nghĩa dữ liệu được xếp ngẫu nhiên hoàn toàn trên đĩa; engine vẫn có thể cấp phát theo extent, ghi theo vùng hoặc tận dụng cache. Khái niệm chỉ nói rằng không có thứ tự vật lý được duy trì theo một khóa clustered cụ thể.

### 4.2. Clustered organization

Trong một số hệ quản trị, clustered index hoặc clustered organization sắp xếp hoặc tổ chức các hàng theo khóa clustering. Các trang lá của cấu trúc có thể chứa trực tiếp hàng dữ liệu, hoặc cơ chế tương đương để dẫn đến hàng. Tìm kiếm theo khóa clustering và quét một khoảng khóa có thể có tính cục bộ tốt hơn vì các hàng gần nhau về khóa thường nằm gần nhau trong cấu trúc lưu trữ.

Clustered organization có thể giảm bước tra cứu từ chỉ mục phụ sang heap, nhưng nó có chi phí duy trì thứ tự. Chèn khóa nằm giữa vùng đã có dữ liệu có thể cần page split hoặc di chuyển dữ liệu. Cập nhật khóa clustering có thể làm hàng phải chuyển vị trí. Chỉ mục phụ trong một số engine còn phải mang khóa clustered làm row locator, khiến kích thước chỉ mục phụ tăng khi khóa clustered rộng.

Không phải hệ quản trị nào cũng có khái niệm clustered index giống nhau. Ví dụ, có engine tổ chức bảng theo clustered B-tree, có engine cho phép chỉ định clustering như một thuộc tính vật lý, trong khi một số hệ thống heap-oriented không duy trì clustered index liên tục như vậy. Cần hiểu chính xác hành vi của nền tảng đang dùng.

### 4.3. So sánh heap và clustered organization

| Khía cạnh | Heap | Clustered organization |
|---|---|---|
| Thứ tự hàng | Không duy trì theo khóa cụ thể | Được tổ chức theo khóa hoặc quy tắc clustering |
| Chèn hàng | Linh hoạt tại trang còn chỗ | Có thể phải duy trì vị trí theo khóa |
| Tìm theo khóa | Thường cần chỉ mục phụ hoặc quét | Có thể đi trực tiếp qua cấu trúc clustered |
| Quét khoảng khóa | Phụ thuộc chỉ mục phụ và vị trí hàng | Có thể tận dụng tính cục bộ theo khóa |
| Cập nhật khóa | Thường không đổi vị trí chỉ vì khóa thường | Có thể làm hàng chuyển vị trí hoặc gây split |
| Chi phí bảo trì | Tập trung vào heap và các chỉ mục phụ | Có thêm chi phí duy trì thứ tự và locator của chỉ mục phụ |

Không có lựa chọn tối ưu cho mọi workload. Hãy cân nhắc truy vấn đọc phổ biến, mẫu chèn/cập nhật, kích thước khóa, phạm vi quét và chi phí bảo trì.

## 5. Đường đi từ khóa qua B-tree đến bản ghi

### 5.1. Cấu trúc B-tree/B+ tree ở mức khái niệm

Chỉ mục B-tree hoặc B+ tree tổ chức khóa theo thứ tự để tìm kiếm, so sánh và quét khoảng hiệu quả. Cấu trúc thường có:

- **Root page:** điểm bắt đầu tìm kiếm.
- **Internal pages:** chứa separator key và con trỏ đến các trang con.
- **Leaf pages:** chứa khóa chỉ mục và thông tin dẫn đến hàng hoặc chứa dữ liệu hàng tùy loại chỉ mục.

Các trang lá của B+ tree thường liên kết với nhau để hỗ trợ quét tuần tự theo thứ tự khóa. Chiều cao cây tăng chậm theo số khóa nhờ mỗi trang nội bộ có thể dẫn đến nhiều trang con.

### 5.2. Tra cứu chỉ mục trên heap

Giả sử bảng `users` được lưu theo heap và có chỉ mục B-tree trên `user_id`. Truy vấn:

```sql
SELECT user_id, email
FROM users
WHERE user_id = 42;
```

Nếu chỉ mục không bao phủ cột `email`, đường đi khái niệm có thể là:

```text
SQL predicate: user_id = 42
          |
          v
       Root page
          |
          v
    Internal page(s)
          |
          v
        Leaf page
   key=42, row locator
          |
          v
   Heap data page
          |
          v
       Row slot
          |
          v
  Check visibility / return email
```

Đầu tiên engine đi từ root qua các trang nội bộ đến leaf page chứa khóa 42. Leaf entry cung cấp row locator. Sau đó engine truy cập trang heap, tìm slot tương ứng, kiểm tra phiên bản hàng có nhìn thấy được và đọc cột `email`.

Đường đi này có thể cần nhiều lần truy cập trang: các trang của B-tree và trang heap. Nếu trang heap chưa có trong buffer pool, engine có thể phải đọc từ storage. Nếu nhiều khóa được tìm kiếm nằm rải rác ở nhiều trang heap, truy cập có thể trở thành I/O ngẫu nhiên và tốn kém.

### 5.3. Tra cứu qua clustered index

Nếu cấu trúc clustered lưu hàng tại các trang lá theo khóa `user_id`, tìm khóa có thể dẫn đến trang lá chứa trực tiếp bản ghi. Khi đó không nhất thiết có bước tra cứu thêm sang heap riêng. Với truy vấn đọc nhiều hàng liên tiếp theo khóa, các hàng có thể có locality tốt hơn.

Tuy nhiên, điều này không có nghĩa mọi clustered index đều trả dữ liệu mà không cần truy cập trang bổ sung. Một số engine có cấu trúc locator hoặc overflow riêng; hàng rộng có thể chứa dữ liệu ngoài trang; MVCC có thể yêu cầu kiểm tra phiên bản. Luôn đọc execution plan và số liệu thực tế.

### 5.4. Quét một khoảng khóa

Với truy vấn:

```sql
SELECT user_id, email
FROM users
WHERE user_id >= 1000 AND user_id < 2000;
```

B-tree có thể tìm leaf đầu tiên phù hợp, sau đó đi qua các leaf page liên tiếp cho đến khi vượt biên trên. Nếu các hàng cần thiết có tính cục bộ tốt, quét khoảng có thể giảm số lần định vị và tận dụng đọc tuần tự hơn so với nhiều lần tra cứu độc lập.

Số dòng trong khoảng và các cột cần trả về quyết định liệu chỉ mục có còn là lựa chọn tốt. Nếu khoảng khóa trả về phần lớn bảng và cần nhiều cột không có trong chỉ mục, quét bảng có thể rẻ hơn hàng loạt lượt lookup.

## 6. Đường truy cập qua các loại chỉ mục khác

### 6.1. Hash index

Hash index dùng hàm băm để ánh xạ khóa đến bucket hoặc vùng lưu trữ tương ứng. Nó phù hợp về mặt khái niệm với phép so sánh bằng trên khóa, nhưng không cung cấp thứ tự khóa để hỗ trợ range scan như B-tree. Va chạm hash có thể khiến một bucket chứa nhiều mục cần kiểm tra thêm.

Khả năng hỗ trợ hash index, giới hạn kiểu dữ liệu, hành vi khi mở rộng và độ bền sau sự cố phụ thuộc hệ quản trị. Không nên chọn hash chỉ vì truy vấn có điều kiện bằng; B-tree cũng xử lý tốt equality và thường hỗ trợ thêm range, ordering và nhiều kiểu truy vấn khác.

### 6.2. Covering index và index-only access

Một chỉ mục bao phủ (covering index) chứa đủ các cột cần để lọc, nối hoặc trả kết quả của truy vấn. Khi đó, engine có thể lấy dữ liệu ngay từ index leaf mà không cần quay lại trang dữ liệu chính cho từng hàng.

Ví dụ, nếu truy vấn tìm theo `user_id` và chỉ trả `email`, một chỉ mục gồm khóa `user_id` và cột phụ `email` có thể bao phủ truy vấn. Tên cơ chế thêm cột phụ khác nhau theo hệ quản trị; có nền tảng dùng `INCLUDE`, có nền tảng lưu cột trong leaf theo cách khác.

Index-only access có thể giảm lượt đọc trang dữ liệu, nhưng chỉ mục rộng hơn sẽ chiếm thêm dung lượng, giảm mật độ khóa trên trang lá, tăng chi phí ghi và bảo trì cache. Một số engine vẫn cần kiểm tra visibility hoặc truy cập bảng trong một số trường hợp. Hãy đo số heap/table fetch thực tế thay vì chỉ nhìn tên kế hoạch.

### 6.3. Chỉ mục ghép (composite index)

Chỉ mục ghép chứa nhiều cột theo một thứ tự xác định. Thứ tự cột ảnh hưởng đến khả năng tìm kiếm theo tiền tố, quét khoảng và sắp xếp. Với chỉ mục `(tenant_id, created_at)`, truy vấn lọc theo `tenant_id` rồi giới hạn `created_at` thường có thể tận dụng cả hai phần của khóa. Truy vấn chỉ lọc theo `created_at` có thể không dùng cấu trúc này hiệu quả tùy engine và thống kê.

Chọn thứ tự cột cần xét điều kiện truy vấn thực tế, độ chọn lọc, kiểu truy cập, thứ tự sắp xếp và các truy vấn khác dùng cùng chỉ mục. Không nên chỉ sắp cột có NDV cao nhất lên đầu mà bỏ qua mẫu truy vấn, điều kiện bằng, điều kiện khoảng và yêu cầu ordering.

## 7. Buffer pool: trang đã ở trong bộ nhớ hay phải đọc từ storage?

### 7.1. Logical read và physical read

Buffer pool (hoặc buffer cache) giữ các trang dữ liệu và chỉ mục đã được đọc vào bộ nhớ. Khi truy vấn cần một trang, engine kiểm tra trang đó đã có trong cache hay chưa.

- **Logical read/buffer hit:** truy vấn lấy trang từ vùng đệm trong bộ nhớ. Đây vẫn là một lần truy cập trang và tiêu tốn CPU, nhưng không nhất thiết phát sinh I/O đọc storage.
- **Physical read/buffer miss:** trang chưa có trong cache nên hệ thống cần đọc từ tầng lưu trữ. Độ trễ phụ thuộc thiết bị, hàng đợi I/O, cache của hệ điều hành hoặc storage, mạng và nhiều yếu tố khác.

Một truy vấn có nhiều logical reads nhưng ít physical reads vẫn có thể tốn CPU do phải duyệt nhiều trang hoặc xử lý nhiều bản ghi. Ngược lại, một số ít physical reads ngẫu nhiên có thể tạo độ trễ lớn nếu storage chậm hoặc tải I/O cao.

Tên metric và cách đếm khác nhau giữa hệ quản trị. Có hệ thống tính logical reads theo lần lấy buffer, có hệ thống cung cấp buffer hits, page reads, read-ahead hoặc các chỉ số khác. Hãy đọc định nghĩa metric trước khi so sánh.

### 7.2. Locality và mẫu truy cập

Truy cập tuần tự (sequential access) đọc các trang theo thứ tự gần nhau hoặc theo chuỗi mà storage có thể phục vụ hiệu quả. Truy cập ngẫu nhiên (random access) nhảy giữa nhiều trang không liền kề. Thiết bị lưu trữ hiện đại có thể giảm chênh lệch so với đĩa quay truyền thống, nhưng locality vẫn ảnh hưởng đến cache, read-ahead, số lần định vị và chi phí quản lý I/O.

Nếu một truy vấn tìm 10 khóa nằm ở 10 trang khác nhau, nó có thể cần nhiều lần truy cập trang. Nếu một truy vấn quét 10.000 dòng liên tiếp nằm trong một vùng trang có locality tốt, hệ thống có thể đọc trước và xử lý theo luồng hiệu quả hơn. Số dòng trả về không đủ để dự đoán chi phí; số trang và mẫu truy cập rất quan trọng.

### 7.3. Read amplification

Read amplification là tình huống hệ thống phải đọc hoặc xử lý nhiều dữ liệu hơn đáng kể so với lượng dữ liệu truy vấn cần. Một ví dụ là truy vấn trả về 100 hàng nhưng phải duyệt hàng nghìn trang hoặc thực hiện nhiều lượt lookup. Nguyên nhân có thể là chỉ mục không phù hợp, điều kiện lọc không sargable, dữ liệu phân tán, hàng rộng hoặc truy vấn yêu cầu nhiều cột.

Để đánh giá, hãy so sánh số hàng trả về với số hàng được kiểm tra, số trang logical/physical reads, số lần key lookup/heap fetch và lượng dữ liệu trung gian. Một chỉ mục có thể làm giảm số trang quét nhưng lại gây hàng nghìn lượt truy cập heap; cần nhìn toàn bộ đường đi.

## 8. Chèn, cập nhật, page split và phân mảnh

### 8.1. Trang đầy và page split

Khi chèn một khóa vào B-tree, nếu leaf page còn chỗ, engine có thể đặt entry mới vào trang đó. Nếu trang không còn đủ chỗ, engine có thể phải chia trang (page split) hoặc dùng chiến lược phân bổ và liên kết trang khác. Split làm tăng công việc ghi, có thể tạo thêm trang và ảnh hưởng locality của các lần quét sau.

Với clustered organization, chèn khóa vào giữa dải khóa có thể cần split để giữ thứ tự. Với heap, chèn thường tìm trang còn chỗ theo cơ chế cấp phát; nhưng các chỉ mục phụ vẫn có thể split khi thêm entry.

### 8.2. Fill factor và khoảng trống dự phòng

Một số hệ quản trị cho phép để lại một tỷ lệ trống trên trang khi tạo hoặc xây dựng lại chỉ mục. Khoảng trống này giúp giảm split khi có insert hoặc update trong tương lai, đặc biệt với workload chèn khóa nằm giữa các trang.

Fill factor thấp hơn làm tăng số trang cần lưu và có thể tăng I/O khi đọc; fill factor cao hơn tiết kiệm dung lượng ban đầu nhưng có thể khiến split xảy ra thường xuyên hơn. Giá trị phù hợp phụ thuộc tính tuần tự của khóa, tỷ lệ ghi, mẫu cập nhật và mức độ tăng trưởng dữ liệu. Không nên chọn fill factor chỉ theo một con số mặc định cho mọi chỉ mục.

### 8.3. Fragmentation và locality

Phân mảnh có thể chỉ tình trạng các trang theo thứ tự khóa không còn được bố trí gần nhau về mặt vật lý hoặc có nhiều khoảng trống không hiệu quả. Ý nghĩa và metric fragmentation khác nhau giữa các hệ quản trị và loại storage.

Phân mảnh không phải lúc nào cũng làm truy vấn chậm đáng kể, đặc biệt trên storage có đặc tính truy cập khác nhau hoặc khi dữ liệu chủ yếu nằm trong cache. Trước khi rebuild/reorganize chỉ mục, hãy xác định loại phân mảnh, kích thước chỉ mục, tỷ lệ scan, số physical reads và chi phí ghi/bảo trì. Bảo trì chỉ mục cũng tiêu tốn I/O, CPU, log và có thể gây ảnh hưởng concurrency.

## 9. Khóa trang, latch và khóa giao dịch

Để đọc hoặc sửa trang trong buffer pool an toàn, engine cần cơ chế đồng bộ truy cập cấu trúc nội bộ. Một số hệ thống dùng latch hoặc page latch để bảo vệ trang trong khoảng thời gian ngắn khi đọc/ghi cấu trúc trong bộ nhớ. Khóa giao dịch (transaction lock) lại bảo vệ tính đúng đắn và cô lập của dữ liệu theo ngữ nghĩa giao dịch.

Hai cơ chế này có mục đích khác nhau. Một truy vấn có thể chờ lock vì giao dịch khác đang giữ khóa trên hàng hoặc phạm vi dữ liệu; nó cũng có thể chờ latch do nhiều luồng cùng truy cập hoặc thay đổi một trang nội bộ. Tên wait event và cách triển khai tùy engine.

Nếu thấy wait liên quan page latch hoặc buffer contention, hãy xác định trang hoặc cấu trúc nóng, mức độ đồng thời, mẫu insert/update và các chỉ mục tập trung ghi. Nếu thấy lock wait, hãy tìm giao dịch giữ khóa, thứ tự truy cập và thời gian giao dịch. Tăng số kết nối hoặc thay đổi access path mà không xác định loại tranh chấp có thể không giải quyết được nguyên nhân.

## 10. Ví dụ lần theo đường truy cập và đánh giá hiệu năng

Giả sử bảng `orders` có 50 triệu dòng. Ứng dụng thường chạy hai truy vấn:

```sql
-- Truy vấn A: lấy một đơn hàng theo khóa chính
SELECT order_id, customer_id, status
FROM orders
WHERE order_id = 900001;

-- Truy vấn B: lấy đơn hàng của một khách hàng trong một khoảng thời gian
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 1200
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
```

Truy vấn A là equality lookup theo một khóa duy nhất. Nếu `order_id` là clustered key hoặc chỉ mục B-tree phù hợp, engine có thể đi qua một số trang của cây để đến bản ghi. Nếu chỉ mục phụ trỏ đến heap, có thể cần thêm một lượt đọc trang dữ liệu. Nếu các trang đã nằm trong buffer pool, lượt truy cập có thể không cần physical read.

Truy vấn B lọc theo hai cột và có thể trả về nhiều hàng. Chỉ mục ghép `(customer_id, created_at)` có thể hỗ trợ tìm tiền tố khách hàng và quét khoảng thời gian. Nếu truy vấn trả về nhiều cột khác không có trong chỉ mục, engine có thể phải lookup từng hàng về bảng. Nếu một khách hàng có lượng đơn hàng rất lớn, số lookup có thể cao; một kế hoạch quét theo vùng hoặc quét bảng có thể rẻ hơn tùy tỷ lệ dữ liệu cần lấy.

Để chọn cách tối ưu, hãy thu thập:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Estimated/actual rows | Bộ tối ưu dự đoán số hàng có gần thực tế không? |
| Logical reads | Truy vấn đã chạm bao nhiêu trang trong buffer pool? |
| Physical reads | Có bao nhiêu trang phải lấy từ tầng lưu trữ? |
| Key lookup/heap fetch | Có bao nhiêu lần quay từ index leaf về trang dữ liệu? |
| Buffer hit ratio và cache state | Trang thường nằm trong bộ nhớ hay phải đọc storage? |
| Row width | Mỗi hàng rộng đến mức nào, có cột lớn hoặc overflow không? |
| Wait events | Truy vấn chờ I/O, lock, latch hay tài nguyên khác? |
| Actual elapsed/CPU time | Độ trễ và lượng CPU tiêu thụ thay đổi ra sao? |

Nếu truy vấn A cần rất ít trang nhưng vẫn chậm, hãy xem physical read latency, lock/latch wait và kiểm tra visibility. Nếu truy vấn B tạo nhiều heap fetch, hãy xem chỉ mục bao phủ có hợp lý không, độ rộng index tăng thêm bao nhiêu và chi phí ghi phát sinh. Nếu số logical reads cao, hãy xem có thể giảm số trang qua chỉ mục, lọc sớm hoặc đọc ít cột hơn không.

## 11. Quy trình điều tra access path

1. **Xác định workload.** Chọn truy vấn quan trọng, tần suất chạy, phân bố tham số, số dòng trả về và tỷ lệ đọc/ghi.
2. **Đọc execution plan.** Ghi nhận scan/seek, join, key lookup, heap fetch, index-only access, số hàng ước lượng/thực tế và số vòng lặp.
3. **Hiểu tổ chức lưu trữ.** Xác định bảng là heap, clustered organization, partition hay cấu trúc khác; hiểu row locator và loại chỉ mục được dùng.
4. **Đo trang và I/O.** Thu thập logical reads, physical reads, read-ahead, buffer hit, temp I/O và thời gian chờ storage nếu hệ quản trị cung cấp.
5. **Kiểm tra locality và mật độ.** Xem số trang, độ rộng hàng, phân mảnh, page split, fill factor và mức tập trung của khóa.
6. **Kiểm tra đồng bộ.** Phân biệt lock wait, latch/page contention và chờ I/O. Xác định tài nguyên hoặc trang nóng nếu có.
7. **Đặt giả thuyết.** Ví dụ: chỉ mục phụ tạo quá nhiều heap lookup; index quá rộng; truy vấn quét nhiều trang do thiếu điều kiện lọc; clustered key gây split thường xuyên; dữ liệu trung gian quá lớn.
8. **Thử một thay đổi có kiểm soát.** Có thể thay đổi chỉ mục, thêm cột bao phủ, điều chỉnh thứ tự khóa, viết lại điều kiện để có thể dùng access path phù hợp hoặc cải thiện locality.
9. **Đo lại và kiểm tra tác động ghi.** So sánh cùng kịch bản, dữ liệu và trạng thái tải; kiểm tra cả tốc độ insert/update, dung lượng chỉ mục, log, lock/latch và các truy vấn liên quan.

Không kết luận chỉ từ việc kế hoạch đổi từ table scan sang index seek. Hãy xem tổng số trang, số lần lookup và thời gian thực tế. Index seek có thể vẫn đắt nếu nó dẫn đến rất nhiều lượt đọc rời rạc.

## 12. Những lỗi thường gặp khi đọc đường truy cập

- **Cho rằng mỗi hàng là một lần I/O:** nhiều hàng có thể nằm chung trang; engine đọc trang vào buffer rồi xử lý nhiều hàng trong bộ nhớ.
- **Coi page size giống nhau ở mọi engine:** kích thước trang và bố cục vật lý phụ thuộc hệ quản trị, phiên bản và cấu hình.
- **Đồng nhất heap với dữ liệu hoàn toàn ngẫu nhiên:** heap không duy trì thứ tự theo khóa nhưng việc cấp phát và cache vẫn có thể tạo locality.
- **Cho rằng clustered index luôn nhanh hơn:** clustered organization có lợi cho một số mẫu truy vấn nhưng làm tăng chi phí duy trì thứ tự và ghi.
- **Bỏ qua lookup về bảng:** chỉ mục phụ có thể tìm khóa nhanh nhưng vẫn phải đọc trang heap cho từng hàng.
- **Cho rằng covering index miễn phí:** index rộng chiếm dung lượng, tăng chi phí ghi và có thể giảm mật độ trang lá.
- **Đánh đồng logical read và physical read:** logical read vẫn tốn CPU; physical read phụ thuộc cache và storage.
- **Nhầm lock với latch:** hai cơ chế bảo vệ khác nhau và cần điều tra theo loại wait thực tế.
- **Rebuild chỉ mục theo lịch mà không đo:** bảo trì có chi phí và chỉ hữu ích khi vấn đề phân mảnh thực sự ảnh hưởng workload.
- **Chỉ tối ưu truy vấn đọc:** access path và chỉ mục mới có thể làm insert, update, delete chậm hơn.

## 13. Bài tập tự kiểm tra

**Bài 1.** Một chỉ mục B-tree trên heap tìm được khóa cần thiết và trả về row locator. Vì sao truy vấn vẫn có thể phải đọc thêm trang dữ liệu?

*Gợi ý:* Vì leaf entry chỉ chứa khóa và row locator; nếu truy vấn cần cột không có trong chỉ mục, engine phải truy cập trang heap, tìm slot và kiểm tra khả năng nhìn thấy bản ghi.

**Bài 2.** Một truy vấn trả về 200 dòng qua index seek nhưng thực hiện 200 heap fetch ở 200 trang khác nhau. Những chỉ số nào cần kiểm tra để đánh giá liệu đây có phải nút thắt?

*Gợi ý:* Kiểm tra logical/physical reads, cache hit, thời gian mỗi lần đọc, row width, số cột cần trả về, locality và khả năng dùng covering index. Cũng cần tính chi phí ghi và kích thước nếu thêm cột vào chỉ mục.

**Bài 3.** Một bảng được tổ chức theo clustered key tăng dần. Một workload chèn ngẫu nhiên khóa vào giữa dải thường xuyên gặp page split. Vì sao điều này xảy ra và có thể điều tra gì?

*Gợi ý:* Trang đích có thể đã đầy; split tạo thêm trang và cập nhật cấu trúc cây. Kiểm tra phân bố khóa insert, page split rate, fill factor, fragmentation và chi phí ghi.

**Bài 4.** Một truy vấn có nhiều logical reads nhưng rất ít physical reads. Điều đó có chứng minh truy vấn hiệu quả không?

*Gợi ý:* Không. Cache giúp tránh đọc storage nhưng truy vấn vẫn có thể duyệt quá nhiều trang, tốn CPU và tạo read amplification. Hãy xem số trang, số hàng được kiểm tra, thời gian CPU và access path.

## 14. Ghi nhớ khi tối ưu

Trang dữ liệu là đơn vị quan trọng để hiểu lưu trữ, buffer pool và I/O. Bản ghi được định vị bên trong trang bằng cơ chế của hệ quản trị; chỉ mục có thể dẫn trực tiếp đến hàng, dẫn đến row locator trong heap hoặc cung cấp đủ cột để truy vấn không cần quay lại bảng. Heap và clustered organization tạo ra các đặc tính khác nhau về chèn, quét và locality.

Khi phân tích một truy vấn, hãy lần theo đường đi từ điều kiện khóa đến trang chỉ mục, row locator, trang dữ liệu và bước kiểm tra bản ghi. Sau đó đối chiếu số trang, logical/physical reads, lookup, thời gian, cache và wait events. Một access path tốt phải phù hợp với cả workload đọc lẫn ghi, giảm công việc thực tế và được xác nhận bằng phép đo trong điều kiện tương đương.
