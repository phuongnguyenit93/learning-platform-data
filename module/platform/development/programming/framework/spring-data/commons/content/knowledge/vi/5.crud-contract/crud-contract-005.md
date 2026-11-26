# existsById, count và chi phí kiểm tra trước khi ghi

Hai phương thức `existsById` và `count` thường được dùng trước một thao tác ghi: kiểm tra bản ghi có tồn tại rồi cập nhật, kiểm tra chưa có rồi tạo mới, hoặc đếm số bản ghi để quyết định còn được thêm hay không. Những cách viết này dễ đọc, nhưng một kết quả kiểm tra không tự giữ nguyên trạng thái dữ liệu cho thao tác kế tiếp.

Trong hợp đồng CRUD của Spring Data Commons, `existsById` trả lời câu hỏi tồn tại theo định danh; `count` trả lời câu hỏi số lượng thực thể. Cả hai là thao tác đọc. Chúng không tự tạo khóa, đặt chỗ, ràng buộc duy nhất hoặc giao dịch nguyên tử cho một chuỗi đọc rồi ghi.

Bài học thuộc chương **Hợp đồng CRUD**, trình bày cách sử dụng đúng hai phương thức, đánh giá chi phí của kiểm tra trước khi ghi và lựa chọn cơ chế bảo đảm phù hợp với từng yêu cầu nghiệp vụ. Các chi tiết truy vấn, giao dịch và tính nhất quán phải được đối chiếu với module store thực sự sử dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Đọc đúng hợp đồng `existsById(ID)` và `count()`.
- Chọn `existsById`, `findById` hoặc `count` theo thông tin thật sự cần.
- Phân biệt số lần gọi repository với số lượt giao tiếp tới store.
- Giải thích khoảng đua giữa kiểm tra và ghi bằng một lịch thực thi cụ thể.
- Nhận ra vì sao kiểm tra tồn tại không thay thế unique constraint, optimistic locking hoặc cập nhật nguyên tử.
- Thiết kế kiểm tra theo lô và kiểm tra cạnh tranh có ý nghĩa.

## 2. Hợp đồng chung nói gì?

Các chữ ký tương ứng trong `CrudRepository<T, ID>` là:

```java
boolean existsById(ID id);

long count();
```

### 2.1. `existsById` kiểm tra theo metadata định danh

`existsById(id)` trả về việc một thực thể mang định danh đó có tồn tại theo repository hay không. Đối số ID không được là `null`; hợp đồng API quy định lỗi đối với đối số không hợp lệ này.

Câu trả lời có kiểu boolean, không chứa trạng thái thực thể. Nó không cho biết email, trạng thái, version hoặc quyền truy cập nghiệp vụ của bản ghi.

Tên phương thức dành cho thao tác định danh của repository, vì vậy cần hiểu nó theo metadata ID của mô hình. Nó không phải truy vấn tùy ý lên một field thông thường chỉ vì field đó có tên `id`.

Những điều không thể suy ra chỉ từ giá trị `true`:

- Bản ghi sẽ còn tồn tại khi lời gọi kế tiếp chạy.
- Bản ghi chưa bị sửa từ sau lần kiểm tra.
- Bản ghi thuộc tổ chức hoặc người dùng đang thao tác.
- Một email, mã nghiệp vụ hoặc trường khác là duy nhất.
- Bên gọi đã giành quyền cập nhật bản ghi.

Giá trị `false` cũng không phải giấy phép độc quyền để tạo mới. Một yêu cầu khác có thể thêm dữ liệu trước thao tác ghi của bạn.

### 2.2. `count` trả số lượng, không cấp quyền thêm bản ghi

`count()` trả về `long`, biểu diễn số thực thể theo phạm vi và mapping của repository. Nó không mặc định có nghĩa là số khách hàng đang hoạt động, số bản ghi của tổ chức hiện tại hoặc số bản ghi thỏa một bộ lọc tùy ý.

Nếu cần đếm theo điều kiện, ứng dụng phải có truy vấn tương ứng, chẳng hạn một derived query được module hỗ trợ:

```java
long countByActiveTrue();
```

Không lấy `count()` toàn repository để kiểm tra một giới hạn vốn áp dụng cho từng tổ chức hoặc từng sự kiện. Trước khi bàn về hiệu năng, phải xác định đúng tập dữ liệu cần đếm.

Hợp đồng đếm không nên được tự thay bằng một ước lượng chỉ vì ước lượng rẻ hơn. Nếu tính năng chấp nhận số gần đúng hoặc số liệu cập nhật trễ, hãy thể hiện điều đó bằng một hợp đồng và API phù hợp, tách khỏi giả định đếm chính xác của nơi gọi.

Một kết quả đếm cũng không hứa rằng nhiều lần gọi đọc khác nhau đang cùng nhìn một ảnh chụp dữ liệu. Khả năng thấy thay đổi phụ thuộc store, nguồn đọc và ranh giới giao dịch thực tế.

## 3. Chọn phương thức theo thông tin cần dùng

Giả sử repository quản lý `Customer` có ID kiểu `UUID`, thuộc tính `email` và `active`:

```java
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {

    boolean existsByEmail(String email);

    long countByActiveTrue();
}
```

Các derived query trong ví dụ cần module hỗ trợ và mô hình được mapping phù hợp. Chúng không tự tạo ràng buộc cho dữ liệu.

| Câu hỏi của nghiệp vụ | API nên cân nhắc | Lý do |
| --- | --- | --- |
| Có bản ghi theo ID không? | `existsById` | Chỉ cần boolean |
| Cần đọc trạng thái để xử lý tiếp? | `findById` | Cần chính đối tượng hoặc dữ liệu của nó |
| Có bao nhiêu thực thể trong phạm vi repository? | `count` | Cần số lượng |
| Có bao nhiêu thực thể thỏa điều kiện? | Truy vấn đếm theo điều kiện | Phạm vi đếm phải đúng yêu cầu |
| Có ít nhất một thực thể thỏa điều kiện? | Truy vấn exists theo điều kiện nếu module hỗ trợ | Không cần toàn bộ số lượng |
| Email phải không bao giờ trùng? | Ràng buộc hoặc cơ chế ghi bảo đảm tính duy nhất | Boolean kiểm tra trước không đủ trước cạnh tranh |
| Cập nhật chỉ thành công nếu version còn khớp? | Optimistic locking hoặc cập nhật có điều kiện | Cần kiểm tra và ghi phối hợp tại nơi có cơ chế bảo đảm |

Không nên đọc toàn bộ dữ liệu rồi kiểm tra `.isEmpty()` hoặc đếm trong bộ nhớ chỉ để trả lời một câu hỏi mà store có thể xử lý trực tiếp. Nhưng cũng không mặc định mọi API có tên `exists` đều được triển khai bằng cùng một câu lệnh tối ưu.

## 4. Chi phí của một lần kiểm tra không chỉ là phép so sánh

Một lời gọi repository có thể kéo theo:

```text
Lấy tài nguyên truy cập dữ liệu
    -> chuyển đổi ID và tạo thao tác
    -> gửi yêu cầu tới store
    -> chờ thực thi và dữ liệu phản hồi
    -> chuyển kết quả về kiểu Java
```

Chi phí thực tế có thể gồm thời gian đợi connection pool, độ trễ mạng, đọc chỉ mục hoặc dữ liệu, xử lý điều kiện, giao dịch và chuyển đổi kết quả.

### 4.1. `existsById` thường có cơ hội làm ít việc hơn đọc entity

Vì kết quả chỉ là boolean, implementation có thể dùng cách kiểm tra tồn tại hoặc truy vấn chỉ cần đủ thông tin để kết luận. Điều đó có thể tránh việc tải và mapping toàn bộ thực thể.

Tuy nhiên, câu lệnh cụ thể, số lượt giao tiếp và khả năng tối ưu thuộc module, driver và store. Không nên viết tài liệu ứng dụng dựa trên giả định “mọi `existsById` đều là một câu SQL `SELECT 1`” hoặc “luôn chỉ tốn đúng một round trip”.

Nếu sau đó vẫn cần entity, lợi ích của việc tránh tải entity không còn giữ nguyên: ứng dụng lại phải gọi `findById`.

### 4.2. `count` có thể phải xử lý một tập dữ liệu lớn

Đếm toàn bộ thực thể hoặc đếm theo điều kiện có thể yêu cầu xử lý nhiều mục dữ liệu. Chỉ mục có thể giúp, nhưng không biến mọi phép đếm thành một phép đọc hằng số.

Chi phí còn phụ thuộc điều kiện lọc, phân bố dữ liệu, phiên bản dữ liệu phải nhìn thấy và khả năng tối ưu của hệ quản trị. Kết quả trả về chỉ là một số `long` không có nghĩa công việc phía store nhỏ.

Nếu câu hỏi chỉ là “có ít nhất một bản ghi không?”, tính toàn bộ số lượng có thể làm nhiều việc hơn cần thiết. Chọn một truy vấn tồn tại thích hợp khi module hỗ trợ và phép đo cho thấy nó phù hợp.

### 4.3. Thêm kiểm tra trước nghĩa là thêm công việc

Có thể mô hình hóa một cách khái quát:

```text
Không kiểm tra trước:
    thời gian đường ghi + xử lý kết quả/lỗi

Có kiểm tra trước:
    thời gian đường kiểm tra + thời gian đường ghi + xử lý kết quả/lỗi
```

Đây không phải công thức dự đoán số truy vấn chính xác. Một thao tác `save` có thể tự thực hiện thêm bước đọc hoặc ghi theo metadata và module. Số lần gọi repository không đồng nhất với số câu lệnh hay số yêu cầu mạng.

Kiểm tra trước có thể đáng giá nếu nó giúp từ chối sớm một yêu cầu phổ biến, tránh một bước tiếp theo rất đắt hoặc phục vụ phản hồi của giao diện. Cần so sánh lợi ích đó với chi phí và vẫn giữ cơ chế bảo đảm ở đường ghi.

## 5. Tránh `existsById` rồi lại `findById` khi cần đối tượng

Một cách viết thường gặp:

```java
if (!repository.existsById(customerId)) {
    throw new CustomerNotFoundException(customerId);
}

Customer customer = repository.findById(customerId)
        .orElseThrow(() -> new CustomerNotFoundException(customerId));

customer.changeEmail(newEmail);
return repository.save(customer);
```

`CustomerNotFoundException` ở đây là exception nghiệp vụ của ứng dụng. Đoạn mã giả định mô hình có phương thức `changeEmail` và được store mapping phù hợp.

Nếu cần `Customer` để kiểm tra và thay đổi trạng thái, có thể đọc trực tiếp:

```java
Customer customer = repository.findById(customerId)
        .orElseThrow(() -> new CustomerNotFoundException(customerId));

customer.changeEmail(newEmail);
return repository.save(customer);
```

Thay đổi này loại bỏ một lời gọi repository không cung cấp thêm dữ liệu cần dùng. Nó cũng tránh tạo cảm giác rằng kết quả tồn tại ở bước trước đã bảo đảm lần đọc sau thành công.

Nhưng đọc trực tiếp rồi lưu vẫn có khoảng thời gian cho cập nhật cạnh tranh. Nếu nghiệp vụ cần chống ghi đè, phải xem thêm version, khóa hoặc cập nhật có điều kiện. Việc bỏ một precheck không tự giải quyết toàn bộ vấn đề cạnh tranh.

## 6. Khoảng đua giữa kiểm tra và ghi

Khoảng đua này thường được gọi là **time-of-check to time-of-use**: trạng thái quan sát lúc kiểm tra có thể khác trạng thái khi sử dụng kết quả.

### 6.1. Kiểm tra chưa tồn tại rồi tạo

Hai yêu cầu cùng muốn tạo một bản ghi có cùng định danh:

| Thứ tự | Yêu cầu A | Yêu cầu B |
| --- | --- | --- |
| 1 | `existsById(id)` trả `false` | |
| 2 | | `existsById(id)` trả `false` |
| 3 | Thực hiện ghi | |
| 4 | | Thực hiện ghi |

Cả hai đã đi qua kiểm tra. Kết quả cuối phụ thuộc ràng buộc và semantics của thao tác ghi: có thể xảy ra lỗi trùng khóa hoặc hành vi khác theo store và API được dùng.

Không được mặc định `save` luôn có ý nghĩa “chỉ thêm nếu chưa tồn tại”. Hợp đồng lưu chung không phải một API create-only phổ quát.

### 6.2. Kiểm tra có tồn tại rồi cập nhật

```text
A: existsById(id) -> true
B: xóa hoặc thay đổi bản ghi
A: thực hiện cập nhật dựa trên kết quả cũ
```

Lần kiểm tra của A không khóa bản ghi cho đến khi A ghi. Nếu luồng cập nhật yêu cầu “chỉ cập nhật bản ghi vẫn tồn tại và chưa bị sửa”, điều kiện đó phải được thực thi bằng cơ chế thích hợp trong đường ghi.

### 6.3. Đếm rồi tạo dưới một giới hạn

Một workshop có tối đa 100 lượt đăng ký. Hai yêu cầu cùng thấy 99 lượt:

```text
A: count đăng ký của workshop -> 99
B: count đăng ký của workshop -> 99
A: tạo đăng ký mới
B: tạo đăng ký mới
```

Nếu không có cơ chế phối hợp, giới hạn có thể bị vượt. Ngay cả khi phép đếm trả đúng 99 ở thời điểm đọc, quy tắc “không vượt 100” vẫn không được bảo đảm.

Bài toán không nằm ở việc đổi `count` thành một phương thức có tên dài hơn. Nó nằm ở việc quyết định khả năng thêm và thực hiện thêm phải được phối hợp trước cạnh tranh.

## 7. Có giao dịch chưa chắc đã loại bỏ khoảng đua

Đặt kiểm tra và ghi trong một giao dịch có thể là điều kiện cần cho một thiết kế, nhưng không tự chứng minh thiết kế đó đúng.

Cần xem:

- Store có hỗ trợ giao dịch cần dùng không?
- Những thao tác nào cùng tham gia một transaction manager và tài nguyên?
- Isolation đang áp dụng cung cấp những bảo đảm nào?
- Có khóa hoặc cơ chế kiểm soát xung đột nào thật sự bảo vệ điều kiện nghiệp vụ?
- Nếu giao dịch bị hủy do xung đột, ứng dụng xử lý hoặc thử lại như thế nào?

Không mặc định `@Transactional` có nghĩa serializable hoặc mọi truy vấn đọc đều khóa phạm vi dữ liệu liên quan. Các mức isolation và cơ chế khóa cũng không đồng nhất trên mọi store.

Với giới hạn dựa trên số lượng nhiều bản ghi, chỉ khóa một bản ghi khách hàng bất kỳ không đương nhiên bảo vệ được toàn bộ điều kiện đếm. Cần xác định đúng tài nguyên hoặc điều kiện phải được tuần tự hóa.

Nếu đọc và ghi ở hai loại store khác nhau, càng không được suy ra một annotation giao dịch sẽ tự tạo tính nguyên tử bao trùm cả hai.

## 8. Chọn cơ chế bảo đảm theo quy tắc nghiệp vụ

### 8.1. Tính duy nhất: ràng buộc tại nơi ghi

Nếu email phải duy nhất, thường cần cơ chế unique constraint hoặc unique index phù hợp với store và mô hình dữ liệu.

Quy tắc phải xác định rõ:

- Duy nhất toàn hệ thống hay trong từng tổ chức.
- Email có được chuẩn hóa chữ hoa/chữ thường không.
- Dữ liệu bị xóa mềm có tiếp tục chiếm giá trị duy nhất không.
- Những đường ghi nào phải tuân theo ràng buộc.

`existsById` không kiểm tra duy nhất email. `existsByEmail` cũng chỉ là một quan sát trước thời điểm ghi. Ràng buộc ở đường ghi mới có thể phân xử các yêu cầu đồng thời theo cơ chế store hỗ trợ.

Một precheck có thể được giữ để phản hồi sớm cho người dùng. Dù vậy, đường ghi vẫn phải xử lý lỗi vi phạm ràng buộc vì trạng thái có thể đổi sau precheck.

Khi chuyển lỗi thành phản hồi nghiệp vụ, cần nhận diện đúng loại xung đột hoặc ràng buộc liên quan. Không biến mọi lỗi toàn vẹn dữ liệu thành “email đã tồn tại”: lỗi có thể xuất phát từ ràng buộc khác.

### 8.2. Chống ghi đè: version hoặc cập nhật có điều kiện

Nếu người dùng đọc một bản ghi rồi sửa, yêu cầu có thể là: cập nhật chỉ thành công nếu bản ghi vẫn ở version đã đọc.

Cơ chế optimistic locking của module, khi được cấu hình và sử dụng đúng đường ghi, có thể phát hiện version không còn khớp. Metadata version phải phù hợp store; chỉ có một field tên `version` không tự tạo bảo đảm.

Một lựa chọn khác là adapter thực hiện cập nhật có điều kiện, với ý tưởng:

```text
UPDATE nếu:
    ID đúng
    phạm vi dữ liệu đúng
    version vẫn bằng expectedVersion

Sau đó:
    kiểm tra kết quả cập nhật theo hợp đồng adapter
```

Đây là mô tả hành vi, không phải phương thức mà Commons tự sinh cho mọi store. Implementation phải dùng API hoặc truy vấn thích hợp.

Kết quả không cập nhật được có thể biểu thị bản ghi không tồn tại, ngoài phạm vi hoặc version đã đổi. Cần định nghĩa cách ánh xạ kết quả thay vì mặc định mọi trường hợp đều là cùng một lỗi.

### 8.3. Giới hạn số lượng: phối hợp điều kiện và thao tác

Với workshop, một thiết kế trên cơ sở dữ liệu quan hệ có thể dùng bản ghi quản lý sức chứa:

```sql
UPDATE workshop_capacity
SET reserved = reserved + 1
WHERE workshop_id = :workshopId
  AND reserved < capacity;
```

Đây là ví dụ SQL đặc thù, không phải API CRUD chung. Giả định mỗi workshop có một bản ghi sức chứa được định danh rõ ràng, các cột liên quan hợp lệ và hệ quản trị cung cấp semantics cập nhật cần thiết.

Ứng dụng kiểm tra số bản ghi bị cập nhật:

- Một bản ghi: giành được một suất theo điều kiện cập nhật.
- Không có bản ghi: không giành được suất; có thể do đầy hoặc không có workshop, theo hợp đồng được thiết kế.

Nếu việc tăng bộ đếm và tạo bản ghi đăng ký phải thành công cùng nhau, cần đặt chúng trong một giao dịch được hỗ trợ. Khi tạo đăng ký thất bại, không được để bộ đếm tăng vĩnh viễn ngoài ý muốn.

Nếu cấm một người đăng ký hai lần, còn cần ràng buộc phù hợp trên cặp workshop và người đăng ký. Các đường hủy đăng ký cũng phải giữ bộ đếm nhất quán.

Một document store có thể cung cấp cập nhật có điều kiện trên cùng document. Nếu nghiệp vụ trải qua nhiều document hoặc tài nguyên, phải xem lại phạm vi nguyên tử và hỗ trợ giao dịch.

Bộ đếm chung cũng có thể trở thành điểm tranh chấp khi tải lớn. Thiết kế này cần được đánh giá theo nhu cầu thực tế; nó không phải thay thế mặc định cho mọi phép `count`.

## 9. Khi nào kiểm tra trước vẫn có ích?

Không phải mọi precheck đều nên bị loại bỏ. Vấn đề là gán đúng vai trò cho nó.

| Trường hợp | Vai trò hợp lý của kiểm tra | Bảo đảm vẫn cần ở đường ghi |
| --- | --- | --- |
| Giao diện báo email có thể đã được dùng | Phản hồi sớm, có thể thay đổi sau đó | Ràng buộc duy nhất và xử lý xung đột |
| Cần tránh một bước xử lý tốn kém khi ID không có | Từ chối sớm nếu tỷ lệ không tồn tại đủ lớn | Xử lý bản ghi biến mất hoặc thay đổi về sau |
| Endpoint chỉ trả tình trạng tồn tại | Kết quả của chính thao tác đọc | Hợp đồng về phạm vi và khả năng thấy dữ liệu |
| Hiển thị tổng số khách hàng | Cung cấp số liệu theo phạm vi đã định | Không dùng số hiển thị làm quyền ghi độc quyền |
| Cảnh báo gần đạt hạn mức | Hỗ trợ trải nghiệm hoặc vận hành | Cơ chế chặn vượt hạn mức khi thật sự ghi |

Nếu giữ precheck, nên làm rõ trong mã và thiết kế rằng nó hỗ trợ phản hồi hoặc tối ưu đường xử lý. Bước ghi không được dựa hoàn toàn vào một kết quả cũ để bảo đảm bất biến.

Cũng cần xem nguồn đọc. Nếu kiểm tra từ cache hoặc nguồn có độ trễ so với nơi ghi, kết quả có thể không phản ánh trạng thái mới nhất. Không dùng một kết quả quan sát như vậy làm bộ phân xử duy nhất cho tính duy nhất hoặc sức chứa.

## 10. `count` trong đường ghi: xác định đúng nhu cầu

Có ba nhu cầu dễ bị trộn:

1. **Số liệu để hiển thị:** người dùng muốn biết tổng số.
2. **Điều kiện tham khảo:** hệ thống muốn cảnh báo sắp đầy.
3. **Bất biến bắt buộc:** hệ thống tuyệt đối không được vượt giới hạn.

Cùng một phép đếm có thể phục vụ hai nhu cầu đầu theo hợp đồng phù hợp, nhưng nhu cầu thứ ba còn đòi hỏi kiểm soát cạnh tranh.

### 10.1. Tránh đếm toàn bộ chỉ để kiểm tra rỗng

Nếu code chỉ cần biết có khách hàng đang hoạt động hay không, một truy vấn tồn tại theo điều kiện có thể phù hợp hơn `countByActiveTrue() > 0`.

Không kết luận hiệu năng chỉ từ tên API. Hãy xem implementation và đo trên dữ liệu, chỉ mục và môi trường tương ứng. Store có thể tối ưu một số dạng truy vấn theo cách khác nhau.

### 10.2. Không dùng số đếm để tự tạo ID liên tiếp

Cách tạo ID theo `count() + 1` có nhiều vấn đề:

- Hai yêu cầu có thể tạo cùng ID.
- Xóa dữ liệu làm số lượng không còn tương ứng với ID lớn nhất.
- Số lượng thực thể không phải cơ chế cấp số thứ tự.

Nếu cần định danh hoặc số thứ tự nghiệp vụ, sử dụng cơ chế được thiết kế cho mục tiêu đó, theo khả năng store và yêu cầu miền. Một truy vấn đếm không giữ chỗ cho giá trị kế tiếp.

### 10.3. Không mặc định số đếm và danh sách cùng snapshot

Nếu giao diện lấy `count()` rồi gọi một truy vấn danh sách riêng, dữ liệu có thể thay đổi giữa hai thao tác. Tổng và nội dung không nhất thiết phản ánh cùng một thời điểm.

Ngay cả kết quả phân trang có tổng số cũng phải được hiểu theo implementation và ranh giới nhất quán cụ thể. Nếu nghiệp vụ cần snapshot ổn định, đó là yêu cầu cần được thiết kế và xác nhận riêng.

## 11. Kiểm tra theo lô để tránh nhiều lần gọi độc lập

Giả sử một tiến trình nhận nhiều ID và muốn biết ID nào không có. Gọi `existsById` cho từng phần tử tạo ra nhiều lời gọi repository:

```java
for (UUID id : ids) {
    boolean exists = repository.existsById(id);
    // xử lý kết quả kiểm tra
}
```

Nếu số lượng lớn, tổng chi phí giao tiếp có thể đáng kể. Một hướng khác là lấy tập bản ghi hiện có theo nhóm, rồi so sánh ID:

```java
Set<UUID> requested = new HashSet<>(ids);
Set<UUID> missing = new HashSet<>(requested);

for (Customer customer : repository.findAllById(requested)) {
    missing.remove(customer.getId());
}
```

Ví dụ cần các kiểu `Set`, `HashSet`, `UUID` và mô hình có getter ID phù hợp. Đầu vào phải được kiểm tra để không chứa ID `null` trước khi gọi repository.

Những giới hạn cần giữ rõ:

- `findAllById` không bảo đảm thứ tự kết quả giống thứ tự ID đầu vào.
- ID không tồn tại không tạo một phần tử kết quả tương ứng.
- Không suy ra một lời gọi `findAllById` luôn chỉ phát một yêu cầu tới store.
- Đọc cả thực thể có thể đắt nếu chỉ cần ID; một truy vấn hoặc projection phù hợp có thể tốt hơn khi module hỗ trợ.
- Tập ID lớn có thể cần chia nhóm theo giới hạn store, kích thước request và bộ nhớ.

Đây là tối ưu cách quan sát dữ liệu, không phải khóa tập ID. Nếu sau đó thực hiện ghi, dữ liệu vẫn có thể đổi giữa hai bước.

## 12. Xử lý lỗi và thử lại theo ý nghĩa nghiệp vụ

Sau khi bỏ hoặc giữ precheck, đường ghi vẫn phải xử lý kết quả có thể xảy ra:

| Kết quả | Cách suy luận |
| --- | --- |
| Không tìm thấy khi cần sửa | Ánh xạ theo hợp đồng không tồn tại hoặc ngoài phạm vi |
| Vi phạm ràng buộc duy nhất | Nhận diện đúng ràng buộc, trả xung đột hoặc kết quả phù hợp |
| Version không khớp | Báo dữ liệu đã đổi hoặc thử lại sau khi đọc và đánh giá lại |
| Lỗi kết nối hoặc lỗi tạm thời | Không tự kết luận dữ liệu trùng hay không tồn tại |
| Không chắc thao tác ghi đã thành công chưa | Cần chiến lược idempotency hoặc đối soát phù hợp |

Không thử lại mọi lỗi ghi bằng cách tạo một ID mới. Nếu lần ghi đầu có thể đã thành công nhưng phản hồi bị mất, lần thử lại có thể tạo dữ liệu nghiệp vụ trùng.

Nếu một yêu cầu cần idempotency, phải thiết kế khóa hoặc cơ chế nhận diện yêu cầu lặp. `existsById` trước khi ghi không tự cung cấp semantics xử lý yêu cầu đúng một lần.

Với optimistic locking, thử lại cũng không chỉ là gọi lại `save` trên trạng thái cũ. Thường cần đọc lại và đánh giá quy tắc nghiệp vụ theo dữ liệu mới, với chính sách giới hạn phù hợp.

## 13. Đo chi phí trước khi tối ưu

Một đánh giá có ích cần xem cả tỷ lệ đường đi:

- Bao nhiêu yêu cầu bị từ chối ở precheck?
- Sau precheck có cần đọc entity không?
- Đường ghi có tự thực hiện thêm thao tác đọc không?
- Store đang dùng chỉ mục nào?
- Thời gian chờ tài nguyên có chiếm phần lớn độ trễ không?
- Bao nhiêu lần ghi vẫn bị xung đột sau precheck?

Có thể quan sát log truy vấn, tracing, số yêu cầu tới driver, thời gian connection pool và kế hoạch truy vấn theo công nghệ đang dùng. Phân biệt môi trường thử nhỏ với dữ liệu có kích thước và phân bố gần thực tế.

Một kết luận tốt có dạng: “Trong đường cập nhật này, ứng dụng cần entity để áp dụng quy tắc; bỏ `existsById` loại được một lần gọi repository, và kiểm tra trên store cho thấy số lượt đọc giảm như dự kiến”.

Một kết luận thiếu căn cứ là: “Mọi `existsById` đều chậm” hoặc “`count` luôn nhanh vì chỉ trả một số”. Chi phí gắn với đường thực thi, không chỉ với kiểu trả về.

## 14. Kiểm tra đúng các giả định về cạnh tranh

Kiểm thử tuần tự với mock repository có thể xác nhận cách service rẽ nhánh, nhưng không xác nhận unique constraint hoặc isolation của store.

Các tình huống có giá trị khi ứng dụng phụ thuộc vào bảo đảm tương ứng:

1. **Cùng tạo một giá trị duy nhất:** hai yêu cầu cùng vượt qua precheck, nhưng ràng buộc vẫn chỉ cho kết quả hợp lệ theo quy tắc.
2. **Cùng sửa một version:** hai bên đọc cùng version; cơ chế được chọn phát hiện xung đột thay vì âm thầm ghi đè.
3. **Cùng giành suất cuối:** chỉ một yêu cầu giành được suất, tổng không vượt giới hạn.
4. **Bản ghi biến mất sau kiểm tra:** đường ghi trả kết quả được định nghĩa, không dựa vào giả định bản ghi còn tồn tại.
5. **Lỗi giữa cập nhật bộ đếm và tạo đăng ký:** giao dịch hoặc cơ chế nhất quán không để lại trạng thái sai ngoài ý muốn.

Để tạo lịch cạnh tranh có kiểm soát, có thể dùng barrier hoặc latch tại những điểm thích hợp trong kiểm thử và các giao dịch độc lập. Chỉ thêm thời gian chờ tùy ý thường không bảo đảm hai yêu cầu thật sự đi qua cùng khoảng đua.

Kết quả cần được đánh giá theo bất biến và phản hồi nghiệp vụ, không theo việc mọi thread đều thành công. Với một giá trị phải duy nhất, một yêu cầu bị từ chối đúng cách có thể chính là kết quả mong muốn.

## 15. Tình huống thực hành

Một service hiện làm ba việc trước khi lưu khách hàng:

```text
existsById(customerId)
    -> findById(customerId)
    -> count() để kiểm tra hạn mức tổ chức
    -> save(customer)
```

Hãy đánh giá từng bước:

| Bước | Câu hỏi cần đặt | Hướng điều chỉnh |
| --- | --- | --- |
| `existsById` | Có cần entity ở bước sau không? | Nếu có, thường đọc trực tiếp bằng `findById` |
| `findById` | Đã kiểm tra phạm vi tổ chức và trạng thái chưa? | Dùng truy vấn hoặc service phù hợp phạm vi nghiệp vụ |
| `count` | Đang đếm toàn repository hay đúng tổ chức? Có phải điều kiện bắt buộc không? | Chọn phạm vi đúng; nếu là hạn mức bắt buộc thì thêm cơ chế cạnh tranh phù hợp |
| `save` | Có chống ghi đè hoặc ràng buộc cần thiết không? | Dùng version, ràng buộc hoặc cập nhật có điều kiện theo yêu cầu |

Nếu thao tác chỉ sửa email của một khách hàng đã tồn tại, hãy xem hạn mức số khách hàng có thật sự liên quan không. Một kiểm tra được sao chép từ đường tạo mới sang mọi đường ghi có thể làm tăng chi phí mà không phục vụ quy tắc nào.

Sau khi điều chỉnh, service nên thể hiện trực tiếp các điều kiện nghiệp vụ cần thiết. Mỗi kiểm tra phải có lý do, còn mỗi bất biến phải có nơi chịu trách nhiệm bảo đảm trước cạnh tranh.

## 16. Câu hỏi tự kiểm tra

### Câu 1

`existsById(id)` trả `true`. Có thể chắc chắn lần `findById(id)` kế tiếp tìm được bản ghi không?

**Gợi ý trả lời:** Không có bảo đảm chung như vậy. Dữ liệu có thể đổi giữa hai thao tác; phải xem ranh giới giao dịch và cơ chế nhất quán thực tế.

### Câu 2

Nếu cần đọc khách hàng để đổi trạng thái, vì sao thường không cần gọi `existsById` trước?

**Gợi ý trả lời:** `findById` vừa cho biết có tìm thấy hay không vừa cung cấp dữ liệu cần dùng. Một lần kiểm tra boolean trước đó thường không bổ sung thông tin cho đường xử lý này.

### Câu 3

Hai yêu cầu cùng thấy số đăng ký là 99 trong giới hạn 100. Vì sao phép đếm đúng vẫn chưa bảo đảm không vượt giới hạn?

**Gợi ý trả lời:** Mỗi kết quả chỉ là quan sát. Quyết định cho thêm và thao tác thêm chưa được phối hợp; hai yêu cầu có thể cùng tạo thêm một bản ghi.

### Câu 4

Có thể thay unique constraint bằng `existsByEmail` không?

**Gợi ý trả lời:** Không. Precheck có thể giúp phản hồi sớm nhưng vẫn có khoảng đua. Cần cơ chế duy nhất ở đường ghi và xử lý xung đột phù hợp.

### Câu 5

Một lời gọi `findAllById` có chắc chỉ tạo một truy vấn và giữ nguyên thứ tự ID đầu vào không?

**Gợi ý trả lời:** Không có bảo đảm chung như vậy. Cần đọc hợp đồng về kết quả và xem implementation của module nếu muốn kết luận số thao tác thực tế.

### Câu 6

Thêm `@Transactional` quanh `count` rồi `save` có đủ chứng minh giới hạn số lượng được giữ không?

**Gợi ý trả lời:** Chưa đủ. Phải biết isolation, tài nguyên tham gia và cơ chế thật sự bảo vệ điều kiện trước cạnh tranh.

### Câu 7

Khi nào nên giữ một precheck trước khi ghi?

**Gợi ý trả lời:** Khi nó có lợi ích cụ thể như phản hồi sớm hoặc tránh bước xử lý đắt, chi phí đã được đánh giá và đường ghi vẫn có cơ chế bảo đảm các bất biến cần thiết.