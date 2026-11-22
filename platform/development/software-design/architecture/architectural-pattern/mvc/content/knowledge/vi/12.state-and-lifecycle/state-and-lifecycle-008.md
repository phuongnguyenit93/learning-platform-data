# Xung đột cập nhật và kiểm soát phiên bản dữ liệu

Trong ứng dụng MVC, nhiều người dùng hoặc nhiều request có thể cùng đọc và cập nhật một bản ghi. Một nhân viên mở hồ sơ ở trạng thái “Đang chờ”, người khác duyệt hồ sơ đó, rồi request đầu tiên vẫn gửi dữ liệu dựa trên màn hình cũ. Nếu máy chủ ghi mà không kiểm tra phiên bản, thay đổi mới có thể bị mất hoặc trạng thái nghiệp vụ trở nên không hợp lệ.

Xung đột cập nhật xảy ra khi một thao tác ghi dựa trên dữ liệu đã lỗi thời hoặc cạnh tranh với một thao tác khác. Kiểm soát phiên bản dữ liệu giúp ứng dụng phát hiện những trường hợp này và quyết định cách xử lý. Trong MVC, Controller nhận yêu cầu cập nhật, Service điều phối nghiệp vụ và transaction, Model bảo vệ quy tắc, Repository thực hiện thao tác lưu; cơ sở dữ liệu hoặc giao thức HTTP hỗ trợ phát hiện xung đột.

## 1. Vì sao xảy ra xung đột cập nhật?

Một luồng cập nhật thông thường gồm các bước:

1. Người dùng đọc dữ liệu hiện tại.
2. Giao diện hiển thị dữ liệu và cho phép chỉnh sửa.
3. Người dùng thay đổi một hoặc nhiều trường.
4. Trình duyệt gửi request cập nhật.
5. Máy chủ kiểm tra điều kiện và ghi dữ liệu.

Vấn đề xuất hiện khi dữ liệu thay đổi giữa bước 1 và bước 5. Người dùng có thể vẫn đang nhìn thấy một phiên bản cũ dù cơ sở dữ liệu đã có phiên bản mới.

### 1.1. Ví dụ mất cập nhật (lost update)

Giả sử một tài khoản có số dư 1.000.000 đồng. Hai request cùng đọc số dư:

| Thời điểm | Request A | Request B | Số dư trong DB |
|---|---|---|---:|
| T1 | Đọc 1.000.000 | | 1.000.000 |
| T2 | | Đọc 1.000.000 | 1.000.000 |
| T3 | Tính số dư mới 900.000 | | 1.000.000 |
| T4 | | Tính số dư mới 800.000 | 1.000.000 |
| T5 | Ghi 900.000 | | 900.000 |
| T6 | | Ghi 800.000 | 800.000 |

Nếu hai request đại diện cho hai khoản chi 100.000 và 200.000 đồng, số dư đúng phải là 700.000 đồng. Nhưng thao tác ghi cuối đã ghi đè kết quả của request A. Một cập nhật bị mất.

Với biểu mẫu chỉnh sửa hồ sơ, vấn đề tương tự có thể xảy ra khi A thay đổi số điện thoại còn B thay đổi địa chỉ. Nếu mỗi request gửi toàn bộ đối tượng dựa trên bản cũ, request đến sau có thể ghi lại số điện thoại cũ và làm mất thay đổi của A.

### 1.2. Xung đột nghiệp vụ

Không phải mọi xung đột đều là mất dữ liệu. Một số thao tác không thể đồng thời thành công theo quy tắc nghiệp vụ:

- Hai nhân viên cùng duyệt một yêu cầu chỉ được duyệt một lần.
- Hai khách hàng cùng đặt chỗ cuối cùng của một chuyến đi.
- Hai request cùng giữ một sản phẩm khi chỉ còn một đơn vị tồn kho.
- Một người sửa hồ sơ trong lúc quản trị viên khóa hồ sơ.
- Một đơn hàng bị hủy trong khi request khác đang xác nhận thanh toán.

Trong các tình huống này, hệ thống cần quyết định thao tác nào được chấp nhận và phản hồi rõ ràng cho thao tác còn lại.

## 2. Kiểm soát phiên bản dữ liệu là gì?

Kiểm soát phiên bản (version control hoặc concurrency control ở cấp bản ghi) gắn với dữ liệu một thông tin giúp máy chủ xác định request đang cập nhật dựa trên phiên bản nào.

Một phiên bản có thể là:

- Số nguyên tăng sau mỗi lần cập nhật.
- Timestamp cập nhật, nếu độ chính xác và cách ghi đủ tin cậy.
- ETag hoặc hash đại diện cho biểu diễn tài nguyên.
- Một token phiên bản do máy chủ tạo.

Cách phổ biến trong ứng dụng dùng JPA là trường version tăng tự động. Request đọc dữ liệu phiên bản 7; nếu trước khi ghi đã có request khác cập nhật thành phiên bản 8, thao tác dựa trên phiên bản 7 sẽ bị từ chối.

Ví dụ bản ghi:

| id | name | status | version |
|---|---|---|---:|
| 42 | Hồ sơ A | PENDING | 7 |

Sau khi cập nhật thành công, version tăng lên 8. Giá trị version là metadata kỹ thuật để phát hiện cạnh tranh, không phải mã trạng thái nghiệp vụ.

### 2.1. Mục tiêu của kiểm soát phiên bản

- Phát hiện dữ liệu đã thay đổi kể từ lúc client đọc.
- Ngăn một request cũ ghi đè thay đổi mới.
- Giữ các bất biến và chuyển trạng thái nghiệp vụ hợp lệ.
- Cho phép ứng dụng thông báo xung đột thay vì âm thầm chấp nhận dữ liệu cũ.
- Hỗ trợ nhiều người dùng và nhiều instance máy chủ cùng làm việc trên dữ liệu.

Kiểm soát phiên bản không tự giải quyết mọi quy tắc nghiệp vụ. Ứng dụng vẫn cần xác thực, phân quyền, kiểm tra trạng thái, transaction và các ràng buộc dữ liệu phù hợp.

## 3. Hai chiến lược chính: Optimistic Locking và Pessimistic Locking

Hai chiến lược phổ biến là khóa lạc quan và khóa bi quan. Chúng giải quyết cạnh tranh theo cách khác nhau.

| Tiêu chí | Optimistic Locking | Pessimistic Locking |
|---|---|---|
| Giả định | Xung đột không thường xuyên | Có khả năng cạnh tranh cao |
| Cách làm | Cho phép nhiều request đọc; kiểm tra version khi ghi | Khóa bản ghi khi đọc/chuẩn bị cập nhật |
| Khi có xung đột | Một thao tác ghi thất bại | Request khác phải chờ hoặc không lấy được khóa |
| Hiệu năng | Tốt khi xung đột hiếm | Có chi phí chờ và giữ khóa |
| Phù hợp | Biểu mẫu chỉnh sửa, hồ sơ, nội dung | Tài nguyên khan hiếm, thao tác cạnh tranh cao |
| Rủi ro cần quản lý | Retry, thông báo dữ liệu lỗi thời | Deadlock, timeout, thời gian giữ khóa |

Không có chiến lược tốt nhất cho mọi thao tác. Chọn theo tần suất cạnh tranh, thời gian xử lý, mức độ quan trọng của dữ liệu và khả năng người dùng giải quyết xung đột.

## 4. Optimistic Locking với trường version

Optimistic Locking cho phép các request đọc cùng một bản ghi mà không khóa nó trong suốt thời gian người dùng chỉnh sửa. Khi ghi, cơ sở dữ liệu chỉ chấp nhận cập nhật nếu version vẫn bằng giá trị mà request đã đọc.

### 4.1. Cách hoạt động

Giả sử một hồ sơ có version = 7:

1. Request A đọc hồ sơ cùng version 7.
2. Request B cũng đọc version 7.
3. A cập nhật thành công; version tăng lên 8.
4. B cố cập nhật với version 7.
5. Cơ sở dữ liệu không tìm thấy bản ghi nào còn version 7 để cập nhật; ORM phát hiện xung đột và rollback thao tác B.

Câu lệnh SQL khái niệm:

~~~sql
UPDATE employee_profile
SET phone = :phone,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu số dòng được cập nhật là 0, version không còn khớp hoặc bản ghi không tồn tại. Ứng dụng cần phân biệt các trường hợp theo chính sách và trả kết quả phù hợp.

### 4.2. Dùng @Version với JPA

JPA hỗ trợ optimistic locking thông qua annotation @Version:

~~~java
@Entity
public class EmployeeProfile {

    @Id
    private UUID id;

    private String displayName;
    private String phone;

    @Version
    private long version;

    public long getVersion() {
        return version;
    }

    public void updateContact(String displayName, String phone) {
        this.displayName = displayName;
        this.phone = phone;
    }
}
~~~

Khi Entity được tải và cập nhật trong transaction, JPA provider dùng version để bảo vệ thao tác ghi. Nếu một transaction khác đã cập nhật cùng Entity, thao tác flush hoặc commit có thể phát sinh OptimisticLockException hoặc ngoại lệ được framework chuyển đổi.

Không tự tăng trường version trong mã nghiệp vụ khi JPA đã quản lý nó. Hãy để persistence provider thực hiện việc kiểm tra và tăng version theo cơ chế của nó.

### 4.3. Truyền version qua biểu mẫu MVC

Với SSR, trang chỉnh sửa có thể đưa version vào một hidden field:

~~~html
<form method="post" action="/profiles/42">
  <input type="hidden" name="version" value="7" />

  <label for="displayName">Tên hiển thị</label>
  <input id="displayName" name="displayName" value="Nguyen An" />

  <label for="phone">Điện thoại</label>
  <input id="phone" name="phone" value="0900000000" />

  <button type="submit">Lưu</button>
</form>
~~~

Hidden field vẫn là dữ liệu do client gửi và có thể bị sửa. Máy chủ phải so sánh version được gửi với version hiện tại hoặc dùng cơ chế persistence tương đương; không được tin version từ client như một bằng chứng xác thực.

Một cách khác là giữ version trong DTO hoặc token được ký. Dù dùng cách nào, máy chủ vẫn cần kiểm tra tính hợp lệ và quyền cập nhật.

### 4.4. DTO cập nhật có version

~~~java
public record UpdateProfileRequest(
    @NotBlank String displayName,
    @NotBlank String phone,
    @NotNull Long version
) {}
~~~

Service có thể kiểm tra version rõ ràng trước khi thay đổi:

~~~java
@Transactional
public void updateProfile(
        UUID profileId,
        UpdateProfileRequest request,
        UserId actor) {

    EmployeeProfile profile = repository.findById(profileId)
        .orElseThrow(ProfileNotFoundException::new);

    accessPolicy.requireCanEdit(actor, profile);

    if (profile.getVersion() != request.version()) {
        throw new StaleDataException();
    }

    profile.updateContact(
        request.displayName(),
        request.phone()
    );
}
~~~

So sánh trong Service giúp phát hiện dữ liệu cũ sớm và trả lỗi có ý nghĩa. Tuy nhiên, chỉ so sánh trong Java là chưa đủ để chống race condition: một request khác vẫn có thể cập nhật sau lần so sánh nhưng trước lúc lưu. @Version hoặc cập nhật có điều kiện ở cơ sở dữ liệu vẫn cần để bảo vệ thời điểm ghi thực tế.

Trong ví dụ này, có thể dùng cả kiểm tra sớm để cải thiện thông báo và optimistic locking của JPA để bảo vệ thao tác lưu.

## 5. Pessimistic Locking với khóa cơ sở dữ liệu

Pessimistic Locking giả định có thể xảy ra cạnh tranh và khóa bản ghi để các transaction khác không thể cập nhật cùng dữ liệu cho đến khi khóa được giải phóng.

### 5.1. Cách hoạt động

Một transaction bắt đầu, đọc bản ghi với khóa ghi, thực hiện kiểm tra và cập nhật. Transaction cạnh tranh phải chờ khóa hoặc nhận timeout/deadlock tùy cấu hình.

SQL khái niệm:

~~~sql
SELECT *
FROM inventory
WHERE product_id = :productId
FOR UPDATE;
~~~

Khóa thường được giữ đến khi transaction commit hoặc rollback. Request không nên giữ khóa trong khi chờ người dùng nhập liệu hoặc gọi dịch vụ bên ngoài chậm.

### 5.2. Dùng @Lock trong Spring Data JPA

Repository có thể khai báo chế độ khóa:

~~~java
public interface InventoryRepository
        extends JpaRepository<Inventory, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.productId = :productId")
    Optional<Inventory> findForUpdate(
        @Param("productId") UUID productId
    );
}
~~~

Service gọi phương thức trong transaction:

~~~java
@Transactional
public void reserve(UUID productId, int quantity) {
    Inventory inventory = repository.findForUpdate(productId)
        .orElseThrow(InventoryNotFoundException::new);

    inventory.reserve(quantity);
}
~~~

Phương thức repository cần được gọi trong transaction đang hoạt động. Cú pháp khóa và hành vi cụ thể phụ thuộc database, JPA provider và isolation level.

### 5.3. Khi nào nên dùng khóa bi quan?

Có thể cân nhắc khi:

- Nhiều request thường xuyên tranh chấp cùng một tài nguyên.
- Tài nguyên có số lượng nhỏ và không thể phân bổ vượt giới hạn.
- Một quy trình gồm nhiều bước cần tuần tự hóa trên cùng bản ghi.
- Chi phí retry do optimistic conflict quá cao.

Cần giữ transaction ngắn, truy cập bản ghi theo thứ tự nhất quán và đặt timeout hợp lý. Nếu các transaction khóa nhiều bản ghi theo thứ tự khác nhau, có thể xảy ra deadlock.

## 6. Cập nhật có điều kiện (compare-and-set)

Một cách khác là thực hiện cập nhật nguyên tử với điều kiện version hoặc trạng thái hiện tại. Đây là kiểu compare-and-set: chỉ cập nhật nếu giá trị hiện tại vẫn bằng giá trị mong đợi.

Ví dụ giảm tồn kho:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE product_id = :productId
  AND available >= :quantity
  AND version = :expectedVersion;
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng:

- 1 dòng: cập nhật thành công.
- 0 dòng: tồn kho không đủ, version đã thay đổi hoặc sản phẩm không còn phù hợp.

Nếu cần phân biệt chính xác nguyên nhân, có thể đọc lại trạng thái trong transaction hoặc dùng kết quả truy vấn phù hợp. Không nên giả định mọi trường hợp 0 dòng đều là hết hàng.

Cập nhật có điều kiện rất hữu ích khi quy tắc có thể biểu diễn trực tiếp trong câu lệnh SQL. Nó giảm khoảng thời gian giữa kiểm tra và ghi. Tuy nhiên, cần bảo đảm câu lệnh thực sự nguyên tử theo database và transaction đang dùng.

## 7. Transaction và mức cô lập

Transaction giúp nhóm các thao tác đọc/ghi thành một đơn vị commit hoặc rollback. Nhưng chỉ thêm @Transactional không tự ngăn mọi xung đột cập nhật.

### 7.1. Atomicity không đồng nghĩa với không có xung đột

Một transaction bảo đảm các thay đổi của chính nó được commit cùng nhau hoặc rollback cùng nhau. Nó không mặc nhiên bảo đảm request đang thao tác trên dữ liệu mới nhất hoặc không ghi đè thay đổi của transaction khác.

Cần chọn isolation level, khóa, version hoặc cập nhật có điều kiện phù hợp với quy tắc nghiệp vụ.

### 7.2. Các mức cô lập phổ biến

| Isolation level | Hiện tượng có thể gặp (tùy DB) | Ghi chú |
|---|---|---|
| READ UNCOMMITTED | Dirty read | Có thể đọc dữ liệu chưa commit |
| READ COMMITTED | Non-repeatable read; một số phantom read | Mỗi câu SELECT có thể thấy snapshot khác nhau |
| REPEATABLE READ | Ngăn một số thay đổi đọc lặp; phantom phụ thuộc DB | Hành vi cụ thể khác nhau giữa các hệ quản trị |
| SERIALIZABLE | Mức cô lập cao nhất theo mô hình chuẩn | Có thể giảm đồng thời và phát sinh serialization failure cần retry |

Không nên chọn isolation level chỉ theo tên. Cần hiểu cách database cụ thể triển khai, loại truy vấn và bất biến cần bảo vệ. SERIALIZABLE cũng không có nghĩa ứng dụng không cần xử lý lỗi; database có thể từ chối một transaction để duy trì tính tương đương tuần tự.

### 7.3. Giữ transaction ngắn

Trong ứng dụng web, transaction nên bao quanh phần đọc/kiểm tra/ghi cần tính nguyên tử. Không giữ transaction mở trong lúc:

- Chờ người dùng xác nhận trên giao diện.
- Gửi email hoặc gọi API bên ngoài chậm.
- Chờ thao tác nhập liệu.
- Thực hiện công việc nền kéo dài không cần cùng một transaction.

Đối với quy trình kéo dài, hãy lưu trạng thái trung gian và thiết kế bước tiếp theo thành một command riêng. Nếu cần phối hợp nhiều hệ thống, cân nhắc outbox, saga hoặc cơ chế bù trừ phù hợp.

## 8. Ánh xạ xung đột thành phản hồi HTTP

Khi request dựa trên phiên bản cũ, ứng dụng cần trả phản hồi để client biết dữ liệu đã thay đổi và có thể tải lại hoặc giải quyết xung đột.

Hai status code thường gặp:

- **409 Conflict:** request không thể hoàn tất do xung đột với trạng thái hiện tại của tài nguyên hoặc quy tắc nghiệp vụ.
- **412 Precondition Failed:** một điều kiện HTTP được gửi kèm request, ví dụ If-Match, không còn đúng.

Với API dùng version trong body, 409 thường là lựa chọn dễ hiểu. Với HTTP conditional request sử dụng ETag và If-Match, 412 biểu đạt điều kiện không thỏa mãn.

Ví dụ response 409:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://example.test/problems/stale-version",
  "title": "Dữ liệu đã thay đổi",
  "status": 409,
  "detail": "Hồ sơ đã được cập nhật bởi một thao tác khác. Hãy tải lại dữ liệu trước khi lưu.",
  "code": "STALE_VERSION"
}
~~~

Không trả stack trace, SQL hoặc thông tin nội bộ. Mã lỗi ổn định giúp frontend phân biệt xung đột với lỗi validation hoặc lỗi máy chủ.

### 8.1. ETag và If-Match

HTTP hỗ trợ conditional request. Máy chủ có thể trả ETag đại diện cho phiên bản biểu diễn:

~~~http
HTTP/1.1 200 OK
ETag: "profile-42-v7"
Content-Type: application/json
~~~

Client gửi lại ETag khi cập nhật:

~~~http
PUT /api/profiles/42
If-Match: "profile-42-v7"
Content-Type: application/json
~~~

Nếu tài nguyên đã đổi và ETag hiện tại không còn khớp, máy chủ từ chối cập nhật với 412. Nếu API yêu cầu điều kiện nhưng client không gửi If-Match, có thể dùng 428 Precondition Required theo hợp đồng.

ETag phải được tạo từ phiên bản hoặc biểu diễn có ý nghĩa. Không dùng một ETag yếu cho điều kiện If-Match, vì If-Match dùng strong comparison. Với tài nguyên có nhiều dạng biểu diễn theo Locale hoặc content negotiation, cần xác định ETag áp dụng cho representation hay version nghiệp vụ.

## 9. Luồng MVC xử lý cập nhật có xung đột

Luồng cập nhật có kiểm soát phiên bản có thể mô tả như sau:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant V as View
    participant C as Controller
    participant S as Service
    participant R as Repository
    participant DB as Database

    U->>V: Mở biểu mẫu
    V->>C: GET /profiles/42
    C->>S: Đọc hồ sơ
    S->>R: findById
    R->>DB: SELECT
    DB-->>R: Hồ sơ, version=7
    R-->>S: Entity
    S-->>C: ViewModel + version=7
    C-->>V: Render form

    U->>V: Chỉnh sửa và lưu
    V->>C: POST + version=7
    C->>S: update(command)
    S->>R: Load và cập nhật
    R->>DB: UPDATE ... WHERE version=7
    alt Version vẫn là 7
        DB-->>R: 1 row, version=8
        R-->>S: Thành công
        S-->>C: Success
        C-->>V: Redirect / success
    else Version đã đổi
        DB-->>R: 0 row / optimistic lock exception
        R-->>S: Conflict
        S-->>C: StaleData
        C-->>V: 409 / trang xung đột
    end
~~~

### 9.1. Trách nhiệm của từng tầng

- **View:** hiển thị dữ liệu cùng version hoặc ETag; khi lưu, gửi lại token phiên bản.
- **Controller:** bind request, kiểm tra định dạng, xác thực người dùng và chuyển command cho Service.
- **Service:** kiểm tra quyền, điều phối transaction, áp dụng chính sách xử lý xung đột và chuyển lỗi thành kết quả phù hợp.
- **Model:** bảo vệ bất biến và các chuyển trạng thái hợp lệ.
- **Repository/database:** thực hiện optimistic/pessimistic lock hoặc compare-and-set tại thời điểm ghi.
- **Exception handler:** ánh xạ xung đột thành 409/412 và thông báo phù hợp.

Không nên giải quyết xung đột bằng cách để View tự quyết định dữ liệu nào đúng. Máy chủ phải cung cấp phiên bản có thẩm quyền và quy tắc hợp nhất rõ ràng.

## 10. Người dùng nên làm gì khi xảy ra xung đột?

Phát hiện xung đột mới chỉ là một nửa của giải pháp. Giao diện cần giúp người dùng hiểu điều gì đã xảy ra và chọn cách tiếp tục.

### 10.1. Tải lại và nhập lại

Phù hợp với biểu mẫu đơn giản. Khi phát hiện version cũ, ứng dụng thông báo dữ liệu đã thay đổi và tải phiên bản mới. Người dùng xem lại rồi nhập lại thay đổi.

Ưu điểm là dễ hiểu và an toàn. Nhược điểm là người dùng có thể mất nội dung vừa nhập nếu ứng dụng không giữ bản nháp.

### 10.2. Hiển thị khác biệt

Với tài liệu hoặc biểu mẫu nhiều trường, có thể hiển thị:

- Giá trị người dùng đã đọc.
- Giá trị người dùng vừa nhập.
- Giá trị mới nhất trên máy chủ.

Người dùng chọn trường cần giữ hoặc kết hợp thay đổi. Việc hợp nhất phải được gửi lại dưới dạng một request mới với version mới nhất; không bỏ qua kiểm tra version.

### 10.3. Tự động hợp nhất các trường độc lập

Một số hệ thống có thể hợp nhất thay đổi nếu hai request sửa các trường khác nhau và quy tắc miền cho phép. Ví dụ A sửa số điện thoại, B sửa ảnh đại diện.

Tuy nhiên, không thể giả định các trường độc lập chỉ vì chúng là cột riêng. Chúng có thể cùng tham gia một bất biến hoặc quy tắc nghiệp vụ. Tự động hợp nhất chỉ nên được triển khai khi có chính sách rõ, kiểm thử đầy đủ và người dùng được thông báo.

### 10.4. Thử lại có kiểm soát

Một số lỗi cạnh tranh tạm thời có thể được retry tự động, đặc biệt với thao tác nền có thể tính lại từ dữ liệu mới. Nhưng không nên tự động gửi lại nguyên payload cũ, vì điều đó có thể lặp lại xung đột hoặc làm sai ý định người dùng.

Retry cần:

- Đọc lại trạng thái mới nhất.
- Tính lại quyết định dựa trên dữ liệu mới.
- Giới hạn số lần thử và có backoff khi cần.
- Chỉ áp dụng cho thao tác có thể lặp an toàn.
- Không bỏ qua điều kiện nghiệp vụ hoặc quyền.

Với biểu mẫu do con người chỉnh sửa, thường nên yêu cầu người dùng xác nhận sau khi tải dữ liệu mới.

## 11. Phân biệt optimistic locking với idempotency

Hai cơ chế này giải quyết hai vấn đề khác nhau:

- **Optimistic locking** ngăn request dựa trên phiên bản cũ ghi đè cập nhật mới.
- **Idempotency key** giúp một command bị gửi lặp không tạo ra nhiều hiệu ứng nghiệp vụ.

Ví dụ, người dùng nhấn nút thanh toán hai lần do mạng chậm. Idempotency key giúp máy chủ nhận diện hai request thuộc cùng một thao tác logic. Nếu hai nhân viên cùng cập nhật một hồ sơ từ version 7, optimistic locking giúp phát hiện request thứ hai đã lỗi thời.

Một thao tác quan trọng có thể cần cả hai: idempotency để chống gửi lặp và version/locking để chống cạnh tranh với thao tác khác.

## 12. Những lỗi thiết kế thường gặp

### Chỉ kiểm tra version ở giao diện

Client có thể bị sửa hoặc gửi request trực tiếp. Kiểm tra phía giao diện giúp trải nghiệm tốt hơn nhưng không bảo vệ dữ liệu. Máy chủ và cơ sở dữ liệu phải xác minh phiên bản.

### Chỉ so sánh version trước khi gọi save

Một request khác có thể cập nhật sau lần so sánh nhưng trước khi ghi. Cần optimistic lock ở persistence layer hoặc câu lệnh cập nhật có điều kiện để kiểm tra nguyên tử.

### Cho phép ghi đè khi gặp conflict

Tự động tải lại rồi ghi payload cũ có thể tiếp tục làm mất thay đổi. Cần xác định chính sách hợp nhất hoặc yêu cầu người dùng xem lại.

### Nghĩ rằng @Transactional tự giải quyết lost update

Transaction bảo đảm nhóm thao tác commit/rollback, nhưng isolation mặc định không nhất thiết phát hiện mọi lost update. Cần chọn locking hoặc điều kiện ghi phù hợp.

### Giữ khóa trong lúc chờ người dùng

Không khóa bản ghi khi render form rồi giữ khóa đến lúc người dùng nhấn lưu. Thời gian tương tác có thể kéo dài và làm nghẽn các request khác. Dùng optimistic version cho khoảng thời gian chỉnh sửa của con người.

### Retry vô hạn

Retry liên tục có thể làm tải hệ thống tăng và gây starvation. Giới hạn số lần thử, backoff và đưa ra phản hồi cuối cùng rõ ràng.

### Dùng timestamp làm version mà không xem xét độ chính xác

Hai cập nhật có thể xảy ra trong cùng đơn vị độ chính xác của timestamp, hoặc đồng hồ hệ thống có thể lệch. Số version tăng đơn điệu thường dễ kiểm soát hơn cho optimistic locking ở cấp bản ghi.

### Không xử lý exception tại ranh giới HTTP

Ngoại lệ optimistic lock không nên biến thành 500 chung chung nếu đó là xung đột dự kiến. Ánh xạ sang 409/412 và thông báo phù hợp; log chi tiết kỹ thuật ở phía máy chủ.

## 13. Kiểm thử xung đột cập nhật

Kiểm thử cần xác nhận cả đường thành công, đường xung đột và trạng thái dữ liệu sau cùng.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Cập nhật với version hiện tại | Thành công, version tăng |
| Cập nhật với version cũ | Bị từ chối, dữ liệu mới không bị ghi đè |
| Hai request cùng đọc version 7 | Chỉ một request cập nhật thành công |
| Người dùng không có quyền | Không thay đổi dữ liệu |
| Trạng thái không cho phép | Không thay đổi dữ liệu và không phát sinh hiệu ứng phụ |
| Pessimistic lock timeout | Trả lỗi có kiểm soát, transaction rollback |
| Deadlock hoặc serialization failure | Xử lý theo chính sách retry có giới hạn |
| If-Match khớp ETag | Cập nhật được chấp nhận |
| If-Match không khớp | Trả 412 |
| Request lặp cùng idempotency key | Không tạo hiệu ứng nghiệp vụ trùng |

### 13.1. Kiểm thử optimistic locking

Một bài kiểm thử tích hợp có thể:

1. Tạo một hồ sơ với version ban đầu.
2. Mở hai transaction hoặc hai persistence context độc lập.
3. Cả hai cùng đọc hồ sơ.
4. Transaction A cập nhật và commit.
5. Transaction B cập nhật từ bản đã đọc cũ và flush/commit.
6. Xác nhận B nhận optimistic lock exception.
7. Đọc lại từ transaction mới và xác nhận dữ liệu của A vẫn còn.

Dùng hai EntityManager hoặc transaction độc lập để mô phỏng hai request thật. Một unit test chỉ gọi hai lần phương thức trên cùng một đối tượng trong bộ nhớ không kiểm chứng được cơ chế khóa của database.

### 13.2. Kiểm thử pessimistic locking

Có thể dùng hai transaction đồng thời:

- Transaction A lấy khóa và giữ transaction mở trong thời gian kiểm thử.
- Transaction B cố lấy cùng khóa.
- Xác nhận B phải chờ hoặc nhận timeout theo cấu hình.
- A commit/rollback rồi xác nhận B có thể tiếp tục hoặc kết thúc theo chính sách.

Kiểm thử concurrency cần đồng bộ bằng latch/barrier hoặc cơ chế tương đương để tạo thứ tự xác định. Tránh dùng sleep tùy tiện vì có thể làm test chập chờn.

## 14. Checklist thiết kế cập nhật an toàn

1. Xác định dữ liệu có thể được nhiều người hoặc request cập nhật đồng thời.
2. Xác định hậu quả của lost update hoặc chuyển trạng thái cạnh tranh.
3. Chọn optimistic locking, pessimistic locking hoặc conditional update theo đặc điểm truy cập.
4. Nếu dùng version, truyền version/ETag từ lần đọc đến request cập nhật.
5. Kiểm tra version tại thời điểm ghi ở persistence layer.
6. Giữ transaction ngắn và chọn isolation level phù hợp.
7. Áp dụng lại xác thực, phân quyền và bất biến nghiệp vụ cho mỗi request.
8. Ánh xạ conflict thành 409 hoặc 412 theo hợp đồng HTTP.
9. Hướng dẫn người dùng tải lại, xem khác biệt hoặc hợp nhất có kiểm soát.
10. Retry có giới hạn và chỉ cho thao tác an toàn để thử lại.
11. Phân biệt version control với idempotency.
12. Có integration test với transaction độc lập và request cạnh tranh.

## Kết luận

Xung đột cập nhật là vấn đề tự nhiên khi nhiều request cùng làm việc trên một dữ liệu. Optimistic Locking dùng version để phát hiện request cũ; Pessimistic Locking dùng khóa cơ sở dữ liệu để tuần tự hóa thao tác; compare-and-set kiểm tra điều kiện ngay trong câu lệnh ghi. Trong MVC, View gửi lại version hoặc ETag, Controller tiếp nhận command, Service điều phối transaction và quy tắc, Model bảo vệ bất biến, còn Repository/database xác nhận tính hợp lệ tại thời điểm lưu. Khi xung đột được phát hiện và phản hồi rõ ràng, ứng dụng tránh mất cập nhật và giúp người dùng tiếp tục thao tác an toàn.

