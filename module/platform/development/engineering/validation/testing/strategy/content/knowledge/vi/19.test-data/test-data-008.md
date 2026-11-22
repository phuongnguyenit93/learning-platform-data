# Quản lý phiên bản dữ liệu cùng schema và ứng dụng

Một hệ thống có thể triển khai nhiều phiên bản ứng dụng cùng lúc trong khi schema cơ sở dữ liệu, dữ liệu đã lưu và hợp đồng trao đổi giữa các dịch vụ đang ở những phiên bản khác nhau. Điều này thường xảy ra khi triển khai cuốn chiếu, cập nhật dịch vụ độc lập, chạy tác vụ nền, di chuyển dữ liệu hoặc duy trì khả năng tương thích với ứng dụng cũ.

Nếu nhóm chỉ quản lý phiên bản mã nguồn mà không quản lý phiên bản schema và dữ liệu, một bản phát hành có thể hoạt động ở môi trường kiểm thử nhưng thất bại khi triển khai. Ứng dụng mới có thể yêu cầu một cột chưa tồn tại; ứng dụng cũ có thể không hiểu giá trị enum mới; dữ liệu được tạo bởi phiên bản trước có thể thiếu trường bắt buộc; hoặc một migration có thể làm cho bản ứng dụng cũ không còn chạy được trong giai đoạn chuyển tiếp.

Quản lý phiên bản dữ liệu cùng schema và ứng dụng giúp nhóm biết mỗi thành phần đang hiểu dữ liệu theo hợp đồng nào, những tổ hợp phiên bản nào được hỗ trợ và thứ tự thay đổi nào an toàn. Công việc này bao gồm thiết kế schema có khả năng tiến hóa, quản lý migration, tạo dữ liệu kiểm thử tương thích, xác minh ứng dụng cũ và mới cùng hoạt động, cũng như chuẩn bị phương án khôi phục khi triển khai gặp sự cố.

Mục tiêu không phải buộc mọi thành phần có cùng một số phiên bản. Mục tiêu là xác định và kiểm chứng quan hệ tương thích giữa các phiên bản, để thay đổi có thể được triển khai, kiểm thử và vận hành một cách có kiểm soát.

## 1. Phân biệt phiên bản ứng dụng, schema và dữ liệu

Ba loại phiên bản liên quan chặt chẽ nhưng mô tả những thứ khác nhau.

- **Phiên bản ứng dụng:** phiên bản mã thực thi, dịch vụ, worker, ứng dụng di động hoặc thành phần xử lý nghiệp vụ.
- **Phiên bản schema:** cấu trúc và quy tắc dữ liệu mà một thành phần đọc hoặc ghi, gồm bảng, cột, kiểu dữ liệu, ràng buộc, chỉ mục, định dạng API và schema sự kiện.
- **Phiên bản dữ liệu:** trạng thái, cấu trúc hoặc quy ước của dữ liệu đã lưu hay bộ dữ liệu kiểm thử tại một thời điểm. Nó có thể phản ánh dữ liệu được tạo bởi ứng dụng cũ, đã qua migration hoặc được chuẩn bị theo một bộ quy tắc cụ thể.

Ví dụ, ứng dụng đơn hàng phiên bản 3.4 có thể chạy trên schema cơ sở dữ liệu phiên bản 12 và đọc các bản ghi được tạo từ nhiều phiên bản ứng dụng trước đó. Bộ dữ liệu kiểm thử có thể có phiên bản riêng vì nó chứa trạng thái và cấu trúc phục vụ cho các kịch bản cụ thể.

Không nên suy ra phiên bản schema chỉ từ phiên bản ứng dụng. Một schema có thể được nâng cấp trước khi triển khai ứng dụng mới; nhiều phiên bản ứng dụng có thể cùng dùng một schema trong giai đoạn chuyển tiếp; và một ứng dụng có thể hỗ trợ nhiều phiên bản schema hoặc hợp đồng bên ngoài.

### Mô hình phiên bản cần ghi nhận

| Thành phần | Thông tin phiên bản cần quản lý | Ví dụ |
|---|---|---|
| Ứng dụng | Build, release, commit hoặc image | orders-service 3.4.0 |
| Cơ sở dữ liệu | Migration cuối cùng đã áp dụng hoặc schema revision | db revision 012 |
| API | Phiên bản endpoint hoặc hợp đồng | Orders API v2 |
| Sự kiện | Schema và phiên bản payload | OrderCreated v3 |
| Bộ dữ liệu kiểm thử | Phiên bản fixture, seed hoặc snapshot | order-fixtures 5 |
| Tác vụ chuyển đổi | Phiên bản script, quy tắc và lần chạy | customer-backfill 2 |
| Cấu hình | Phiên bản cấu hình hoặc bộ feature flag | config revision 18 |

Các mã phiên bản là ví dụ. Tổ chức có thể dùng số migration, hash, tag hoặc định danh khác. Điều quan trọng là có thể xác định chính xác thành phần, schema và dữ liệu được dùng trong một lần chạy kiểm thử hoặc một lần triển khai.

## 2. Hiểu quan hệ tương thích giữa các phiên bản

Một tổ hợp phiên bản chỉ an toàn khi các thành phần có thể trao đổi và diễn giải dữ liệu theo hợp đồng đã thống nhất.

Có hai khái niệm thường dùng:

- **Tương thích ngược (backward compatibility):** phiên bản mới của thành phần hoặc schema vẫn có thể làm việc với dữ liệu hay hợp đồng được tạo bởi phiên bản cũ trong phạm vi đã xác định.
- **Tương thích xuôi (forward compatibility):** phiên bản cũ có thể tiếp tục hoạt động khi gặp dữ liệu hoặc hợp đồng mới, trong giới hạn mà nó được thiết kế để bỏ qua hoặc xử lý.

Hai khái niệm này phụ thuộc vào vai trò của thành phần và hướng thay đổi. Ví dụ, thêm một trường tùy chọn vào response API thường dễ tương thích với consumer cũ nếu consumer bỏ qua trường không biết. Nhưng đổi kiểu của trường hiện có hoặc thay đổi ý nghĩa của một trạng thái có thể phá vỡ consumer.

### Tương thích không chỉ là cấu trúc

Hai schema có thể có cùng tên trường nhưng khác ý nghĩa. Một trường amount trước đây biểu diễn đơn vị đồng, sau đó được đổi sang đơn vị nhỏ hơn mà không đổi tên; dữ liệu vẫn hợp lệ về cú pháp nhưng ứng dụng tính toán sai.

Khi đánh giá tương thích, cần xem:

- Tên, kiểu và định dạng trường.
- Trường bắt buộc, tùy chọn và giá trị mặc định.
- Ý nghĩa nghiệp vụ, đơn vị và quy tắc làm tròn.
- Các giá trị enum hoặc trạng thái được phép.
- Quy tắc null, giá trị thiếu và giá trị rỗng.
- Quan hệ khóa, ràng buộc và tính duy nhất.
- Thứ tự, thời gian và ngữ nghĩa của sự kiện.
- Quyền truy cập và cách bảo vệ dữ liệu.
- Khả năng đọc dữ liệu cũ sau khi chuyển đổi.

Một thay đổi có vẻ tương thích về cấu trúc vẫn có thể phá vỡ hành vi. Vì vậy, kiểm thử cần xác minh cả cấu trúc lẫn ý nghĩa dữ liệu.

### Lập bảng tương thích

Có thể lập bảng cho những tổ hợp phiên bản được hỗ trợ:

| Ứng dụng | Schema cũ | Schema mới | Quyết định |
|---|---|---|---|
| Ứng dụng cũ | Được hỗ trợ | Chỉ hỗ trợ nếu đã xác minh | Ghi rõ trong kế hoạch chuyển đổi |
| Ứng dụng mới | Chỉ hỗ trợ nếu có cơ chế tương thích | Được hỗ trợ | Tổ hợp mục tiêu |
| Worker cũ | Cần xác minh | Cần xác minh | Không giả định tương thích |
| Worker mới | Cần xác minh | Cần xác minh | Kiểm tra riêng nếu triển khai độc lập |

Không cần kiểm tra mọi tổ hợp lý thuyết. Hãy xác định tổ hợp thực sự có thể tồn tại trong quá trình triển khai, rollback, tác vụ nền và vận hành. Với triển khai cuốn chiếu, ít nhất cần xem xét thời gian ứng dụng cũ và mới cùng chạy trên cùng schema.

## 3. Quản lý thay đổi schema theo từng bước

Thay đổi schema có thể ảnh hưởng đến nhiều phiên bản ứng dụng cùng lúc. Một quy tắc an toàn phổ biến là tách thay đổi phá vỡ tương thích thành các bước mở rộng, chuyển đổi và thu hẹp (expand–migrate–contract).

### Giai đoạn mở rộng (expand)

Thêm cấu trúc mới theo cách không làm ứng dụng hiện tại ngừng hoạt động. Ví dụ:

- Thêm cột mới có thể null.
- Thêm bảng mới.
- Thêm trường tùy chọn vào payload.
- Tạo chỉ mục theo cách phù hợp với hệ quản trị cơ sở dữ liệu.
- Thêm khả năng đọc dữ liệu mới nhưng vẫn giữ đường đọc cũ.

Ở giai đoạn này, ứng dụng cũ cần tiếp tục hoạt động với schema đã mở rộng. Không nên xóa hoặc đổi tên cấu trúc cũ ngay.

### Giai đoạn chuyển đổi (migrate)

Chuyển dữ liệu và ứng dụng sang cách biểu diễn mới:

- Backfill dữ liệu cũ vào trường hoặc bảng mới.
- Triển khai ứng dụng có thể đọc dữ liệu cũ và mới.
- Bắt đầu ghi dữ liệu mới theo cấu trúc mới.
- Kiểm tra sự nhất quán giữa biểu diễn cũ và mới trong thời gian chuyển tiếp.
- Theo dõi số lượng bản ghi chưa được chuyển đổi và lỗi migration.

Tác vụ backfill cần có khả năng tiếp tục sau khi bị gián đoạn, tránh xử lý trùng và ghi lại số liệu đã xử lý. Với dữ liệu lớn, nên chia lô và kiểm soát tải thay vì khóa hoặc cập nhật toàn bộ bảng trong một thao tác dài.

### Giai đoạn thu hẹp (contract)

Chỉ loại bỏ cấu trúc cũ sau khi xác nhận không còn ứng dụng, worker, báo cáo hoặc tiến trình nào sử dụng nó.

Các bước có thể gồm:

- Xác nhận mọi phiên bản đang chạy đã chuyển sang cấu trúc mới.
- Dừng ghi vào trường cũ.
- Theo dõi để xác nhận không còn lượt đọc.
- Lưu bằng chứng và bản sao lưu cần thiết.
- Xóa trường, bảng hoặc hợp đồng cũ trong một thay đổi riêng.
- Chạy kiểm thử xác nhận ứng dụng và tác vụ nền vẫn hoạt động.

Giai đoạn contract thường là thay đổi phá vỡ tương thích. Cần được triển khai sau khi giai đoạn chuyển đổi hoàn tất và đã xác nhận không còn consumer cũ.

## 4. Ví dụ: đổi cách lưu tên khách hàng

Giả sử schema hiện tại lưu tên khách hàng trong một trường full_name. Sản phẩm muốn tách thành given_name và family_name để hỗ trợ tìm kiếm và hiển thị linh hoạt hơn.

Một thay đổi trực tiếp xóa full_name và thêm hai trường mới có thể khiến ứng dụng đang chạy thất bại. Thay vào đó, có thể thực hiện theo các bước:

### Bước 1: Mở rộng schema

Thêm given_name và family_name, ban đầu cho phép null hoặc có quy tắc mặc định phù hợp. Giữ full_name để ứng dụng cũ tiếp tục đọc và ghi.

### Bước 2: Triển khai ứng dụng tương thích

Triển khai phiên bản có thể đọc dữ liệu mới khi có, đồng thời có cách xử lý bản ghi cũ. Trong giai đoạn chuyển tiếp, cần quyết định cách ghi để dữ liệu cũ và mới không lệch nhau. Nếu ghi cả hai dạng, quy tắc đồng bộ phải được xác định rõ và kiểm thử.

### Bước 3: Chuyển dữ liệu cũ

Backfill given_name và family_name từ full_name theo quy tắc đã thống nhất. Tên có thể có nhiều thành phần hoặc không theo quy tắc phân tách đơn giản, vì vậy cần xử lý những trường hợp không thể suy ra chắc chắn và ghi nhận dữ liệu cần rà soát.

### Bước 4: Xác minh và chuyển hoàn toàn

So sánh số bản ghi, kiểm tra dữ liệu thiếu, lấy mẫu những trường hợp phức tạp và xác nhận ứng dụng mới chỉ còn phụ thuộc vào cách biểu diễn mới. Theo dõi log hoặc metric để phát hiện truy cập vào full_name.

### Bước 5: Thu hẹp schema

Sau khi xác nhận không còn ứng dụng hoặc tác vụ đọc/ghi full_name, mới xem xét bỏ trường cũ. Thao tác này cần một migration riêng và kế hoạch khôi phục phù hợp.

Ví dụ cho thấy migration không chỉ là câu lệnh ALTER TABLE. Nó là một quá trình phối hợp giữa schema, ứng dụng, dữ liệu, consumer và kế hoạch triển khai.

## 5. Quản lý migration như một phần của vòng đời ứng dụng

Migration là thay đổi có phiên bản đối với cấu trúc hoặc dữ liệu. Mỗi migration cần được quản lý như một tạo tác phát hành, có định danh, thứ tự, nội dung, điều kiện chạy và bằng chứng đã áp dụng.

Một migration có thể:

- Tạo hoặc thay đổi bảng, cột, chỉ mục và ràng buộc.
- Chuyển đổi hoặc chuẩn hóa dữ liệu.
- Tạo dữ liệu tham chiếu cần thiết.
- Thay đổi kiểu, đơn vị hoặc cách biểu diễn.
- Loại bỏ cấu trúc không còn sử dụng.

### Nguyên tắc thiết kế migration

- Có định danh duy nhất và thứ tự rõ ràng.
- Có thể xác định migration đã chạy hay chưa.
- Có thể chạy lại an toàn hoặc phát hiện trạng thái đã áp dụng.
- Tránh thao tác phá hủy dữ liệu khi chưa có kế hoạch.
- Được kiểm tra trên dữ liệu có quy mô và hình dạng đại diện.
- Có log, số liệu và cách phát hiện lỗi.
- Có ước lượng thời gian và ảnh hưởng đến khóa, tải hoặc dung lượng.
- Có kế hoạch phục hồi hoặc roll-forward.
- Được gắn với phiên bản ứng dụng và schema tương thích.

Không phải migration nào cũng có thể rollback bằng một migration ngược. Khi đã chuyển đổi dữ liệu mất thông tin hoặc xóa trường, việc khôi phục có thể cần bản sao lưu, nhật ký thay đổi hoặc chuyển tiếp sửa chữa. Cần xác định khả năng phục hồi trước khi chạy migration trên môi trường quan trọng.

### Migration có tính lặp an toàn

Một tác vụ có thể bị dừng giữa chừng. Nếu chạy lại, nó không nên làm sai dữ liệu hoặc tạo bản ghi trùng. Có thể dùng khóa định danh, điều kiện cập nhật, bảng theo dõi tiến độ hoặc checkpoint.

Ví dụ SQL minh họa:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE normalized_email IS NULL
  AND email IS NOT NULL;
~~~

Điều kiện WHERE giúp các lần chạy tiếp theo chỉ xử lý bản ghi chưa được chuyển đổi. Trong hệ thống thực tế, cần xem xét cập nhật đồng thời, trigger, transaction, khóa và cách ứng dụng ghi dữ liệu trong khi backfill đang chạy.

### Migration dữ liệu lớn

Với bảng lớn, cần cân nhắc:

- Chia lô theo khóa hoặc phạm vi dữ liệu.
- Giới hạn tốc độ để giảm tải hệ thống.
- Ghi checkpoint sau mỗi lô.
- Theo dõi số bản ghi thành công và thất bại.
- Xử lý bản ghi lỗi riêng thay vì dừng toàn bộ nếu chính sách cho phép.
- Kiểm tra dữ liệu mới được tạo trong lúc migration chạy.
- Đảm bảo tác vụ có thể tiếp tục sau khi bị dừng.

Một migration chạy thành công về mặt kỹ thuật chưa chứng minh dữ liệu đã được chuyển đúng. Cần có kiểm tra hậu điều kiện như số lượng, tổng giá trị, quan hệ, giá trị null và các bất biến nghiệp vụ.

## 6. Quản lý phiên bản schema API và sự kiện

Schema không chỉ tồn tại trong cơ sở dữ liệu. API, message broker, tệp trao đổi và sự kiện đều có hợp đồng dữ liệu cần được tiến hóa.

### Thêm trường mới

Thêm trường tùy chọn thường ít rủi ro hơn thay đổi hoặc xóa trường hiện có. Consumer cũ có thể bỏ qua trường mới nếu parser và hợp đồng cho phép. Tuy nhiên, nếu trường mới trở thành bắt buộc ngay lập tức, consumer cũ có thể không gửi nó và bị từ chối.

### Thay đổi kiểu hoặc ý nghĩa trường

Đổi chuỗi thành số, thay đơn vị, đổi múi giờ hoặc đổi ý nghĩa trạng thái có thể phá vỡ consumer dù tên trường không đổi. Cách an toàn thường là thêm trường mới hoặc phiên bản hợp đồng mới, chuyển đổi consumer theo lộ trình rồi loại bỏ trường cũ.

### Giá trị enum mới

Consumer có thể giả định enum chỉ chứa một tập giá trị cố định. Khi producer thêm trạng thái mới, consumer cũ có thể lỗi hoặc xử lý sai. Cần quy định cách consumer xử lý giá trị không nhận biết, ví dụ ghi nhận và đưa vào trạng thái chưa hỗ trợ thay vì làm hỏng toàn bộ luồng.

### Xóa hoặc đổi tên trường

Chỉ thực hiện sau khi xác nhận mọi consumer đã chuyển đổi. Với hệ thống nhiều consumer, cần danh sách người sở hữu, phiên bản đang dùng và bằng chứng không còn truy cập trường cũ.

### Quản lý schema sự kiện

Với sự kiện bất đồng bộ, cần quản lý:

- Tên và phiên bản sự kiện.
- Producer và các consumer.
- Schema payload và ý nghĩa trường.
- Mã định danh sự kiện và khóa tương quan.
- Thời điểm phát, thứ tự và khả năng phát lại.
- Quy tắc tương thích và thời gian hỗ trợ phiên bản cũ.
- Hành vi với trường không biết hoặc giá trị enum mới.

Sự kiện đã được lưu trong hàng đợi hoặc kho lịch sử có thể được phát lại sau nhiều tháng. Vì vậy, việc xóa schema cũ có thể ảnh hưởng đến consumer mới khi xử lý thông điệp lịch sử.

## 7. Quản lý phiên bản bộ dữ liệu kiểm thử

Dữ liệu kiểm thử cũng cần được quản lý phiên bản. Một fixture có thể phụ thuộc vào schema, quy tắc nghiệp vụ và trạng thái ứng dụng tại thời điểm tạo.

Nếu cấu trúc dữ liệu thay đổi nhưng fixture không được cập nhật, kiểm thử có thể thất bại trước khi chạm đến hành vi cần xác minh. Ngược lại, nếu fixture tự động biến đổi mà không ghi nhận, kết quả kiểm thử có thể khó tái hiện.

### Thông tin nên gắn với một bộ dữ liệu

- Tên và định danh phiên bản.
- Mục đích và nhóm kịch bản sử dụng.
- Phiên bản schema tương thích.
- Phiên bản ứng dụng hoặc hợp đồng liên quan.
- Cách tạo hoặc seed dữ liệu.
- Migration hoặc bước chuyển đổi cần chạy.
- Dữ liệu đầu vào và quan hệ giữa các bản ghi.
- Quy tắc cleanup hoặc khôi phục.
- Nguồn gốc và giới hạn dữ liệu.
- Chủ sở hữu và thời điểm cập nhật.

Có thể lưu metadata cạnh fixture:

~~~yaml
dataset: order-lifecycle
version: 5
schema_revision: 12
application_compatibility:
  minimum: 3.3
  maximum: 3.x
purpose:
  - order-payment-flow
  - cancellation-regression
created_by: test-data-builder
notes:
  - Uses synthetic customer and payment records
  - Requires the payment sandbox stub
~~~

Đây là ví dụ định dạng minh họa. Cấu trúc thực tế cần theo quy ước của dự án. Không nên ghi bí mật, token hoặc dữ liệu cá nhân thật vào metadata hay fixture.

### Thay đổi fixture có kiểm soát

Khi schema thay đổi:

1. Xác định fixture nào sử dụng cấu trúc cũ.
2. Đánh giá kịch bản nào phụ thuộc vào trường hoặc trạng thái bị thay đổi.
3. Tạo phiên bản fixture mới hoặc migration dữ liệu có thể tái hiện.
4. Giữ lại phiên bản cũ nếu vẫn cần kiểm tra tương thích.
5. Chạy kiểm thử với cả dữ liệu cũ và mới trong giai đoạn chuyển tiếp.
6. Cập nhật metadata, tài liệu và chủ sở hữu.
7. Loại bỏ fixture cũ khi không còn kịch bản được hỗ trợ cần dùng nó.

Không nên sửa fixture dùng chung mà không đánh giá ảnh hưởng đến mọi test sử dụng nó. Một thay đổi giá trị mặc định có thể làm thay đổi hàng trăm kịch bản mà không có thay đổi trong mã test.

## 8. Kiểm tra ứng dụng cũ và mới cùng dùng một schema

Trong triển khai cuốn chiếu, nhiều phiên bản ứng dụng có thể cùng chạy trong một khoảng thời gian. Schema phải hỗ trợ tất cả phiên bản đang hoạt động trong thời gian đó.

Các câu hỏi cần trả lời:

- Ứng dụng cũ có thể đọc schema sau khi mở rộng không?
- Ứng dụng mới có thể chạy trước hay chỉ sau migration?
- Worker nền cũ có tiếp tục ghi dữ liệu theo định dạng cũ không?
- Có nhiều phiên bản mobile hoặc desktop cùng kết nối không?
- Tác vụ batch có chạy trong lúc chuyển đổi không?
- Rollback ứng dụng có còn tương thích với schema mới không?
- Có thể tồn tại thông điệp cũ trong hàng đợi sau khi consumer mới triển khai không?

### Ma trận kiểm thử phiên bản

Có thể lập ma trận những tổ hợp có khả năng xuất hiện:

| Tổ hợp | Câu hỏi cần xác minh |
|---|---|
| Ứng dụng cũ + schema cũ | Hành vi hiện tại có còn đạt trước khi migration không? |
| Ứng dụng cũ + schema mở rộng | Ứng dụng cũ có bỏ qua cấu trúc mới và tiếp tục hoạt động không? |
| Ứng dụng mới + schema mở rộng | Ứng dụng mới có đọc/ghi đúng dữ liệu mới không? |
| Ứng dụng mới + dữ liệu cũ | Ứng dụng mới có xử lý bản ghi chưa backfill không? |
| Ứng dụng cũ + dữ liệu đã chuyển đổi | Ứng dụng cũ có còn đọc được trong giai đoạn chuyển tiếp không? |
| Worker cũ + sự kiện mới | Worker có xử lý hoặc bỏ qua trường mới an toàn không? |
| Worker mới + sự kiện lịch sử | Consumer mới có đọc được payload cũ không? |
| Phiên bản rollback + schema hiện tại | Ứng dụng quay lui có tiếp tục hoạt động an toàn không? |

Chỉ kiểm tra các tổ hợp phù hợp với chiến lược triển khai. Nếu tổ hợp nào không được hỗ trợ, phải ngăn nó xuất hiện trong vận hành hoặc ghi rõ điều kiện loại trừ.

## 9. Thiết kế kiểm thử migration và chuyển đổi dữ liệu

Migration cần được kiểm tra trước khi áp dụng lên dữ liệu quan trọng. Kiểm thử nên bao gồm cả cấu trúc sau migration, dữ liệu đã chuyển đổi và khả năng ứng dụng hoạt động trong giai đoạn chuyển tiếp.

### Kiểm tra trước migration

- Xác nhận schema đầu vào đúng phiên bản dự kiến.
- Kiểm tra dữ liệu có vi phạm ràng buộc mới không.
- Đếm bản ghi và xác định dữ liệu thiếu hoặc bất thường.
- Kiểm tra dung lượng, thời gian và ảnh hưởng khóa.
- Xác nhận backup hoặc phương án phục hồi.
- Kiểm tra migration có thể chạy trong môi trường tương đương.

### Kiểm tra trong migration

- Theo dõi tiến độ và số bản ghi đã xử lý.
- Kiểm tra hành vi khi tác vụ bị dừng.
- Xác minh chạy lại không tạo dữ liệu trùng.
- Kiểm tra tác động khi ứng dụng tiếp tục đọc/ghi.
- Theo dõi lỗi, thời gian xử lý và tải hệ thống.

### Kiểm tra sau migration

- Schema có đúng cấu trúc và ràng buộc mong đợi không?
- Số lượng bản ghi có hợp lý không?
- Các quan hệ và khóa ngoại có còn hợp lệ không?
- Giá trị được chuyển đổi có đúng quy tắc không?
- Tổng tiền, số lượng hoặc chỉ số đối soát có thay đổi ngoài dự kiến không?
- Ứng dụng cũ và mới có hoạt động theo ma trận tương thích không?
- Các truy vấn quan trọng có hiệu năng chấp nhận được không?

### Kiểm tra migration trên dữ liệu đại diện

Dữ liệu thử nghiệm nên bao gồm:

- Bản ghi bình thường.
- Trường null hoặc thiếu.
- Giá trị biên và giá trị lớn.
- Dữ liệu lịch sử từ nhiều phiên bản.
- Bản ghi trùng hoặc không nhất quán nếu hệ thống có thể chứa chúng.
- Ký tự Unicode, định dạng ngày và múi giờ.
- Quan hệ giữa các bảng hoặc đối tượng.
- Bản ghi được tạo hoặc cập nhật trong lúc migration chạy.

Dữ liệu đại diện giúp phát hiện những giả định sai mà một bộ fixture nhỏ chỉ có dữ liệu sạch có thể bỏ qua.

## 10. Quản lý thứ tự triển khai ứng dụng và schema

Thứ tự triển khai là một phần của thiết kế tương thích. Một migration đúng nhưng chạy sai thời điểm vẫn có thể làm hệ thống ngừng hoạt động.

Một trình tự thường dùng cho thay đổi schema có tính mở rộng:

1. Triển khai migration mở rộng, giữ cấu trúc cũ.
2. Xác minh ứng dụng hiện tại vẫn hoạt động.
3. Triển khai phiên bản ứng dụng có thể đọc dữ liệu cũ và mới.
4. Chuyển đổi dữ liệu theo lô và theo dõi tiến độ.
5. Chuyển toàn bộ ghi/đọc sang cấu trúc mới.
6. Xác nhận không còn consumer sử dụng cấu trúc cũ.
7. Triển khai migration contract để loại bỏ cấu trúc cũ.
8. Chạy kiểm thử hồi quy và xác minh sau triển khai.

Không phải thay đổi nào cũng cần đủ tám bước. Với thay đổi bổ sung đơn giản, có thể ít bước hơn. Với dữ liệu lớn hoặc nhiều consumer, có thể cần nhiều giai đoạn và khoảng thời gian quan sát dài hơn.

### Kiểm tra khi triển khai cuốn chiếu

Trong lúc rollout, cần theo dõi:

- Phiên bản ứng dụng đang chạy trên từng instance.
- Phiên bản schema đã áp dụng.
- Tỷ lệ request hoặc tác vụ từ mỗi phiên bản.
- Lỗi đọc/ghi và lỗi parse dữ liệu.
- Số bản ghi chưa chuyển đổi.
- Consumer còn đọc trường hoặc sự kiện cũ.
- Thông điệp đang chờ trong hàng đợi.
- Tác vụ nền chạy theo phiên bản nào.

Nếu không có khả năng quan sát phiên bản đang hoạt động, nhóm khó biết khi nào an toàn để contract schema cũ.

## 11. Lập kế hoạch rollback và roll-forward

Rollback ứng dụng không nhất thiết đồng nghĩa rollback schema. Một migration có thể không đảo ngược an toàn, đặc biệt khi dữ liệu đã bị chuyển đổi hoặc thông tin cũ đã bị xóa.

Cần phân biệt:

- **Rollback ứng dụng:** đưa mã thực thi về phiên bản trước.
- **Rollback schema:** hoàn nguyên cấu trúc cơ sở dữ liệu.
- **Khôi phục dữ liệu:** phục hồi bản ghi từ backup, log hoặc bản sao.
- **Roll-forward:** triển khai một thay đổi mới để sửa trạng thái hiện tại mà không quay ngược toàn bộ dữ liệu.

### Kiểm tra khả năng rollback

Trước khi phát hành, hãy xác định:

- Ứng dụng cũ có chạy được với schema hiện tại không?
- Ứng dụng mới có ghi dữ liệu mà ứng dụng cũ không hiểu không?
- Migration có thể đảo ngược mà không mất thông tin không?
- Backup được tạo khi nào và đã kiểm tra khôi phục chưa?
- Có thể dừng backfill và tiếp tục sau đó không?
- Nếu schema không thể rollback, phương án roll-forward là gì?
- Ai có quyền quyết định và thực hiện khôi phục?

### Không mặc định migration ngược là an toàn

Ví dụ, khi gộp given_name và family_name thành full_name, có thể không còn cách khôi phục chính xác ranh giới ban đầu nếu quy tắc tách tên không rõ. Một migration ngược có thể tạo giá trị gần đúng nhưng làm mất thông tin.

Với thay đổi phá hủy, nên lưu dữ liệu cũ trong giai đoạn chuyển tiếp hoặc backup đã được xác minh. Cần xác định thời hạn giữ và cách bảo vệ dữ liệu đó.

## 12. Quản lý dữ liệu tham chiếu và dữ liệu seed

Dữ liệu seed thường tạo ra các giá trị cần thiết để ứng dụng hoạt động, chẳng hạn vai trò, loại trạng thái, danh mục, đơn vị tiền hoặc cấu hình mặc định.

Nếu dữ liệu seed không được quản lý phiên bản, môi trường kiểm thử và sản xuất có thể có các giá trị khác nhau. Ứng dụng mới có thể yêu cầu một mã trạng thái chưa tồn tại hoặc hiểu sai ý nghĩa của dữ liệu tham chiếu cũ.

Cần:

- Ghi rõ dữ liệu seed thuộc phiên bản hoặc migration nào.
- Dùng khóa ổn định thay vì phụ thuộc tên hiển thị có thể thay đổi.
- Tạo seed theo cách có thể chạy lại an toàn.
- Phân biệt dữ liệu tham chiếu bắt buộc với dữ liệu mẫu.
- Không ghi đè tùy tiện dữ liệu đã được người dùng chỉnh sửa.
- Kiểm tra ứng dụng cũ khi có giá trị tham chiếu mới.
- Xác minh dữ liệu seed sau migration.

Ví dụ, thêm trạng thái ORDER_REVIEW có thể ảnh hưởng consumer cũ giả định chỉ có CREATED, PAID và CANCELLED. Cần kiểm tra cả nơi tạo trạng thái và tất cả nơi đọc hoặc hiển thị trạng thái đó.

## 13. Quản lý schema và dữ liệu trong môi trường kiểm thử

Mỗi môi trường có thể có schema và dữ liệu ở thời điểm khác nhau. Điều này dễ xảy ra khi một nhóm chạy migration trên staging nhưng môi trường tích hợp hoặc môi trường kiểm thử khác chưa được cập nhật.

Một môi trường kiểm thử đáng tin cậy cần biết:

- Ứng dụng nào đang được triển khai.
- Schema revision nào đã áp dụng.
- Bộ fixture nào đang được nạp.
- Migration seed nào đã chạy.
- Dịch vụ nào được mock hoặc thay bằng sandbox.
- Dữ liệu có được tạo từ đầu hay giữ lại từ lần chạy trước.
- Cách reset và khôi phục trạng thái.
- Người sở hữu môi trường và dữ liệu.

### Tạo môi trường có thể tái tạo

Có thể dùng migration tự động, seed script có phiên bản, container hoặc môi trường tạm thời để tạo trạng thái kiểm thử. Quy trình tạo môi trường cần cho kết quả có thể dự đoán và có thể chạy lại.

Nếu dùng snapshot, hãy ghi phiên bản schema, thời điểm tạo và những thay đổi đã áp dụng sau snapshot. Không nên dùng snapshot cũ mà không biết nó tương thích với ứng dụng hiện tại hay không.

### Không để môi trường trôi phiên bản

Schema drift xảy ra khi các môi trường có cấu trúc khác nhau ngoài dự kiến. Có thể phát hiện bằng cách so sánh migration đã áp dụng, metadata schema hoặc kiểm tra cấu trúc tự động.

Khi phát hiện drift, cần xác định nguồn gốc và đưa môi trường về trạng thái đã quản lý. Tránh sửa trực tiếp schema trên một môi trường mà không ghi nhận migration tương ứng.

## 14. Thiết kế ma trận kiểm thử tương thích

Ma trận tương thích giúp nhóm chọn những tổ hợp phiên bản cần xác minh. Nó nên dựa trên thời điểm triển khai thực tế, không phải mọi tổ hợp có thể tưởng tượng.

Ví dụ:

| Ứng dụng | Schema | Dataset | Mục tiêu |
|---|---|---|---|
| Phiên bản hiện tại | Schema hiện tại | Fixture hiện tại | Đường cơ sở trước thay đổi |
| Phiên bản hiện tại | Schema mở rộng | Fixture hiện tại | Xác nhận ứng dụng cũ vẫn chạy |
| Phiên bản mới | Schema mở rộng | Fixture cũ | Xác nhận đọc dữ liệu lịch sử |
| Phiên bản mới | Schema mở rộng | Fixture mới | Xác nhận hành vi mục tiêu |
| Phiên bản rollback | Schema sau migration | Dữ liệu sau backfill | Xác nhận khả năng quay lui ứng dụng |
| Worker cũ | Schema sự kiện mới | Sự kiện mới | Xác nhận consumer cũ xử lý an toàn |
| Worker mới | Schema sự kiện cũ | Sự kiện lịch sử | Xác nhận consumer mới đọc được dữ liệu cũ |

Có thể bổ sung API, broker, phiên bản mobile, cấu hình và nhà cung cấp bên ngoài. Với số tổ hợp lớn, ưu tiên các tổ hợp tồn tại trong rollout, rollback và xử lý dữ liệu lịch sử.

### Các tầng kiểm thử trong ma trận

- Kiểm thử đơn vị xác minh quy tắc chuyển đổi và xử lý dữ liệu.
- Kiểm thử migration xác minh cấu trúc và hậu điều kiện.
- Kiểm thử hợp đồng xác minh producer và consumer tương thích.
- Kiểm thử tích hợp xác minh ứng dụng hoạt động với schema và dữ liệu thật.
- Kiểm thử hệ thống xác minh hành trình xuyên nhiều phiên bản nếu rollout cho phép.
- Kiểm thử vận hành xác minh giám sát, phục hồi và khả năng tiếp tục migration.

Không cần lặp cùng một assertion ở mọi tầng. Mỗi tầng nên cung cấp loại bằng chứng phù hợp.

## 15. Ví dụ tổng hợp: đổi trường tổng tiền của đơn hàng

Giả sử hệ thống hiện có trường total_amount lưu giá trị dạng số thực. Nhóm muốn chuyển sang cấu trúc gồm amount_minor (số nguyên theo đơn vị nhỏ nhất) và currency_code để tránh mơ hồ về đơn vị và tiền tệ.

### Rủi ro cần xem xét

- Ứng dụng cũ vẫn đọc total_amount.
- Ứng dụng mới cần amount_minor và currency_code.
- Dữ liệu lịch sử có thể đã làm tròn khác nhau.
- Consumer API có thể hiểu amount theo đơn vị cũ.
- Báo cáo và tác vụ đối soát có thể tiếp tục đọc trường cũ.
- Rollback ứng dụng có thể cần total_amount được duy trì.
- Các đơn hàng nhiều loại tiền không thể gộp tổng một cách tùy tiện.

### Kế hoạch chuyển đổi

1. Thêm amount_minor và currency_code, giữ total_amount.
2. Triển khai ứng dụng tương thích có thể đọc dạng mới nếu có và xử lý bản ghi cũ.
3. Backfill dữ liệu từ total_amount theo quy tắc làm tròn và tiền tệ đã thống nhất.
4. Đối soát số lượng, tổng giá trị và các trường hợp có sai số.
5. Chuyển ứng dụng mới sang ghi và đọc cấu trúc mới.
6. Theo dõi consumer, báo cáo và tác vụ còn sử dụng total_amount.
7. Xác nhận khả năng rollback ứng dụng trong thời gian chuyển tiếp.
8. Chỉ loại bỏ total_amount sau khi không còn consumer và đã có quyết định về dữ liệu lịch sử.

### Kiểm thử cần có

| Kiểm thử | Bằng chứng |
|---|---|
| Chuyển đổi số tiền thông thường | amount_minor và currency_code đúng |
| Giá trị biên và làm tròn | Quy tắc làm tròn được áp dụng nhất quán |
| Bản ghi thiếu currency | Có quy tắc xử lý hoặc được đưa vào danh sách điều tra |
| Dữ liệu lịch sử | Ứng dụng mới đọc được bản ghi cũ |
| Ứng dụng cũ trên schema mở rộng | Không lỗi khi có cột mới |
| Ứng dụng mới trên schema mở rộng | Đọc và ghi đúng cấu trúc mới |
| Báo cáo và đối soát | Tổng số liệu không lệch ngoài ngưỡng đã định |
| Rollback ứng dụng | Phiên bản cũ vẫn đọc được dữ liệu trong giai đoạn hỗ trợ |

Ví dụ minh họa vì sao thay đổi kiểu dữ liệu cần cả kiểm thử schema, dữ liệu, ứng dụng và consumer. Một migration thành công không đủ để xác nhận kết quả nghiệp vụ đúng.

## 16. Theo dõi tiến độ và bằng chứng tương thích

Trong quá trình chuyển đổi, nhóm cần biết phần nào đã hoàn thành và phần nào còn phụ thuộc. Có thể theo dõi bằng một bảng:

| Hạng mục | Trạng thái | Bằng chứng hoặc điều kiện hoàn tất |
|---|---|---|
| Migration mở rộng | Hoàn tất | Schema mới được áp dụng và ứng dụng cũ vẫn chạy |
| Ứng dụng tương thích | Hoàn tất | Kiểm thử với schema mở rộng đạt |
| Backfill | Đang chạy | Tiến độ, lỗi và checkpoint được theo dõi |
| Đối soát dữ liệu | Chờ xác minh | Số lượng và giá trị khớp quy tắc |
| Consumer mới | Đang triển khai | Hợp đồng và sự kiện lịch sử được kiểm tra |
| Loại bỏ trường cũ | Chưa bắt đầu | Chờ xác nhận không còn consumer |
| Kế hoạch rollback | Đã thử nghiệm | Có bằng chứng phục hồi hoặc roll-forward |

Trạng thái cần phản ánh kết quả thực tế. Không nên đánh dấu migration hoàn tất chỉ vì tiến trình kết thúc; phải xác minh dữ liệu. Không nên đánh dấu consumer đã chuyển đổi chỉ vì mã mới được triển khai; cần xác nhận phiên bản đang hoạt động và không còn truy cập hợp đồng cũ.

### Gắn bằng chứng với lần triển khai

Mỗi lần triển khai hoặc migration quan trọng nên ghi:

- Phiên bản ứng dụng.
- Schema revision.
- Bộ dữ liệu hoặc seed version.
- Migration đã chạy.
- Kết quả kiểm thử tương thích.
- Số liệu đối soát.
- Ngoại lệ hoặc rủi ro còn lại.
- Người phê duyệt và thời điểm.

Thông tin này giúp điều tra sự cố sau phát hành và tái tạo môi trường khi cần.

## 17. Những sai lầm thường gặp

- **Đồng nhất phiên bản ứng dụng và schema:** dẫn đến giả định sai về thời điểm và khả năng tương thích.
- **Đổi tên hoặc xóa cột ngay:** ứng dụng cũ có thể còn đọc hoặc ghi cấu trúc cũ.
- **Chỉ kiểm tra migration chạy thành công:** dữ liệu có thể bị chuyển sai dù câu lệnh không lỗi.
- **Không kiểm tra dữ liệu cũ:** ứng dụng mới có thể chỉ hoạt động với dữ liệu vừa tạo.
- **Không xét worker và tác vụ nền:** chúng có thể tiếp tục dùng schema hoặc sự kiện cũ sau khi ứng dụng web đã cập nhật.
- **Không quản lý phiên bản fixture:** dữ liệu kiểm thử không còn tương thích nhưng không rõ nguyên nhân.
- **Backfill không thể tiếp tục an toàn:** tác vụ bị gián đoạn có thể tạo trùng hoặc bỏ sót.
- **Không kiểm tra rollout cuốn chiếu:** phiên bản cũ và mới có thể cùng chạy và ghi dữ liệu khác nhau.
- **Giả định rollback ứng dụng đồng nghĩa rollback schema:** dữ liệu đã chuyển đổi có thể không thể hoàn nguyên.
- **Xóa schema cũ quá sớm:** consumer lịch sử, báo cáo hoặc tiến trình chậm vẫn có thể phụ thuộc.
- **Không theo dõi schema drift:** các môi trường có cấu trúc khác nhau làm kết quả kiểm thử không đáng tin cậy.
- **Không lưu bằng chứng phiên bản:** khó tái hiện sự cố và xác định tổ hợp đã chạy.
- **Bỏ qua ý nghĩa nghiệp vụ:** schema có thể tương thích về kiểu nhưng không tương thích về đơn vị hoặc ngữ nghĩa.

## 18. Danh sách rà soát trước khi thay đổi schema hoặc dữ liệu

Trước một thay đổi có ảnh hưởng đến schema, dữ liệu hoặc ứng dụng, có thể rà soát:

| Khía cạnh | Câu hỏi |
|---|---|
| Phạm vi | Thành phần, ứng dụng và consumer nào sử dụng dữ liệu này? |
| Phiên bản | Phiên bản ứng dụng, schema, API, sự kiện và fixture hiện tại là gì? |
| Tương thích | Tổ hợp phiên bản nào cần cùng hoạt động trong rollout? |
| Migration | Thay đổi có mở rộng trước, chuyển đổi và thu hẹp sau không? |
| Dữ liệu cũ | Bản ghi lịch sử được đọc và chuyển đổi như thế nào? |
| Dữ liệu mới | Ứng dụng cũ có thể gặp bản ghi mới không? |
| Tác vụ nền | Worker, batch và consumer có dùng hợp đồng cũ không? |
| Backfill | Có thể chia lô, tiếp tục và đối soát không? |
| Kiểm thử | Có kiểm thử migration, hợp đồng và ứng dụng cũ/mới không? |
| Rollback | Có thể rollback ứng dụng? Schema và dữ liệu có phục hồi được không? |
| Quan sát | Có metric, log và số liệu để biết chuyển đổi đã hoàn tất không? |
| Quyền sở hữu | Ai chịu trách nhiệm migration, dữ liệu, ứng dụng và quyết định contract? |

Nếu câu trả lời cho một rủi ro quan trọng chưa rõ, cần làm rõ trước khi triển khai thay đổi phá vỡ tương thích.

## 19. Mẫu kế hoạch quản lý phiên bản

Có thể dùng mẫu sau cho một thay đổi dữ liệu:

~~~text
TÊN THAY ĐỔI:
MỤC TIÊU NGHIỆP VỤ:
PHẠM VI THÀNH PHẦN:

PHIÊN BẢN HIỆN TẠI:
- Ứng dụng:
- Schema:
- API / sự kiện:
- Dataset / seed:
- Worker / batch:

PHIÊN BẢN MỤC TIÊU:
- Ứng dụng:
- Schema:
- API / sự kiện:
- Dataset / seed:

TƯƠNG THÍCH:
- Ứng dụng cũ với schema mở rộng:
- Ứng dụng mới với dữ liệu cũ:
- Consumer cũ với payload mới:
- Consumer mới với dữ liệu lịch sử:
- Tổ hợp không hỗ trợ:

KẾ HOẠCH:
1. Expand:
2. Deploy ứng dụng tương thích:
3. Backfill / migrate:
4. Đối soát:
5. Chuyển consumer:
6. Contract:

KIỂM THỬ:
- Migration:
- Dữ liệu cũ và mới:
- Hợp đồng:
- Rollout cuốn chiếu:
- Rollback / roll-forward:
- Kiểm thử sau triển khai:

QUAN SÁT:
- Số bản ghi đã chuyển:
- Số bản ghi còn lại:
- Lỗi đọc / ghi:
- Consumer còn dùng cấu trúc cũ:

TRÁCH NHIỆM:
- Chủ sở hữu schema:
- Chủ sở hữu dữ liệu:
- Chủ sở hữu ứng dụng:
- Chủ sở hữu consumer:
- Người phê duyệt:

RỦI RO CÒN LẠI:
ĐIỀU KIỆN HOÀN TẤT:
THỜI ĐIỂM XEM XÉT LẠI:
~~~

Mẫu cần được điều chỉnh theo kiến trúc. Với thay đổi nhỏ, có thể ghi trong pull request hoặc tài liệu migration. Với thay đổi lớn, nhiều consumer hoặc dữ liệu quan trọng, nên có kế hoạch chuyển đổi riêng và bằng chứng cho từng giai đoạn.

## Kết luận

Quản lý phiên bản dữ liệu cùng schema và ứng dụng là việc kiểm soát quan hệ tương thích trong suốt quá trình phát triển, triển khai và vận hành. Nhóm cần phân biệt phiên bản ứng dụng, schema, hợp đồng và bộ dữ liệu; xác định tổ hợp phiên bản được hỗ trợ; thiết kế migration theo từng bước; và kiểm tra cả dữ liệu lịch sử lẫn dữ liệu mới.

Khi fixture, seed, schema và migration đều có phiên bản cùng chủ sở hữu rõ ràng, nhóm có thể tái tạo môi trường, xác minh ứng dụng cũ và mới, phát hiện sớm lỗi chuyển đổi và đưa ra quyết định rollback hoặc roll-forward có căn cứ. Bằng chứng tương thích cần được ghi lại cùng phiên bản ứng dụng, schema và dữ liệu của mỗi lần chạy để kết quả kiểm thử có thể giải thích và tái hiện được.
