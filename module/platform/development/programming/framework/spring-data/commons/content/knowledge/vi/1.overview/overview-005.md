# Phân biệt hợp đồng dùng chung với hành vi do từng store triển khai

Spring Data Commons cung cấp các abstraction dùng chung để làm việc với dữ liệu: repository, CRUD, mô tả truy vấn, phân trang, sắp xếp, projection, Query by Example và metadata phục vụ auditing. Những abstraction này tạo ra một cách diễn đạt quen thuộc giữa các module Spring Data. Tuy nhiên, cách lưu dữ liệu, tập toán tử truy vấn, cơ chế giao dịch và thời điểm thấy được thay đổi vẫn phụ thuộc module tích hợp và hệ quản trị phía dưới.

Ví dụ, hai repository có thể cùng khai báo `save`, `findById` và nhận `Pageable`, nhưng một repository làm việc với thực thể trong cơ sở dữ liệu quan hệ, repository còn lại làm việc với document. Sự giống nhau ở API giúp giảm công học lại; nó không tự biến hai mô hình lưu trữ thành tương đương.

Bài học thuộc phần **Tổng quan** của Spring Data Commons, tập trung vào cách đọc đúng hợp đồng chung, nhận diện phần do từng store quyết định và đặt ranh giới phù hợp khi xây dựng ứng dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt vai trò của Spring Data Commons, module Spring Data cho từng store và hệ quản trị dữ liệu.
- Đọc một interface repository mà không suy diễn thêm về SQL, hiệu năng, giao dịch hoặc tính nhất quán.
- Giải thích vì sao một derived query, projection hoặc Example dùng được ở module này chưa chắc dùng được ở module khác.
- Nhận ra những cấu hình và metadata cần có để auditing, định danh và kiểm soát cập nhật hoạt động.
- Thiết kế hợp đồng nghiệp vụ rõ ràng, đồng thời sử dụng khả năng đặc thù của store tại đúng nơi.

## 2. Ba tầng cần tách khi suy luận

Trong bài này, **store** là loại kho dữ liệu được một module Spring Data tích hợp, chẳng hạn JPA với cơ sở dữ liệu quan hệ, MongoDB, Redis hoặc Elasticsearch. Khả năng thực tế còn phụ thuộc phiên bản module, driver, cấu hình và phiên bản hệ quản trị.

| Tầng | Vai trò | Ví dụ câu hỏi thuộc tầng này |
| --- | --- | --- |
| Spring Data Commons | Định nghĩa API, mô hình và hạ tầng dùng chung cho các module Spring Data | `Pageable` mang những thông tin nào? `Optional<T>` biểu diễn kết quả ra sao? |
| Module tích hợp store | Tạo repository implementation, xử lý mapping, diễn giải truy vấn và nối với công nghệ lưu trữ | Tên phương thức này có được hỗ trợ không? Thuộc tính Java được ánh xạ ra trường nào? |
| Hệ quản trị và môi trường chạy | Thực thi thao tác, quản lý chỉ mục, ràng buộc, giao dịch và khả năng nhìn thấy dữ liệu | Có chỉ mục phù hợp không? Truy vấn chịu isolation nào? Bản ghi vừa lưu đã xuất hiện trong tìm kiếm chưa? |

Ngoài ba tầng trên, ứng dụng còn có **hợp đồng nghiệp vụ** của riêng mình: email có duy nhất không, đơn hàng có được tạo hai lần không, người dùng nào được sửa dữ liệu, những bước nào phải thành công cùng nhau. Repository không tự suy ra các yêu cầu đó từ tên phương thức.

Một cách kiểm tra suy luận hữu ích là đặt câu hỏi: “Điều này được hứa bởi API nào, được triển khai bởi module nào và được bảo đảm ở đâu?”. Nếu không chỉ ra được nơi bảo đảm, bạn đang dựa vào một giả định.

## 3. Hợp đồng dùng chung thực sự cho biết điều gì?

### 3.1. Kiểu generic xác định miền thao tác

Xét một ứng dụng quản lý khách hàng. Mô hình có `Customer`, kiểu định danh `String`, thuộc tính `email`, `status` và enum `CustomerStatus`.

```java
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String>,
                PagingAndSortingRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);

    Page<Customer> findByStatus(
            CustomerStatus status,
            Pageable pageable);
}
```

Đây là phần khai báo repository minh họa. `Customer` và `CustomerStatus` là các kiểu miền của ứng dụng; mapping của `Customer` phải được bổ sung theo module thực sự sử dụng. Đoạn mã cũng giả định module đó hỗ trợ repository, các truy vấn và kiểu trả về tương ứng.

Từ interface trên, có thể đọc được:

- Repository làm việc với `Customer` và định danh kiểu `String`.
- Ứng dụng yêu cầu các thao tác CRUD và các thao tác sắp xếp, phân trang qua hai interface tương ứng.
- `findByEmail` diễn đạt truy vấn đơn kết quả hoặc không có kết quả.
- `findByStatus` yêu cầu kết quả dạng trang và nhận mô tả phân trang từ bên gọi.

Chưa thể kết luận dữ liệu nằm trong bảng nào, email đã có unique index hay chưa, truy vấn sẽ dùng chỉ mục nào hoặc các lời gọi liên tiếp có chung giao dịch hay không. Việc tạo bean repository cũng cần module tích hợp và cấu hình repository phù hợp; chỉ đưa Spring Data Commons vào classpath chưa tạo ra kết nối tới một kho dữ liệu.

### 3.2. CRUD diễn đạt thao tác, không ấn định câu lệnh lưu trữ

| API chung | Ý nghĩa có thể dựa vào | Điều cần xem ở module hoặc store |
| --- | --- | --- |
| `save(entity)` | Lưu thực thể và trả về thực thể đã lưu; mã gọi nên dùng giá trị trả về | Cách nhận biết thực thể mới, phát sinh ID, insert/update/merge, phạm vi cập nhật và thời điểm gửi thay đổi |
| `saveAll(entities)` | Lưu các thực thể được cung cấp theo hợp đồng API | Có tối ưu batch không, có bao nhiêu lượt giao tiếp và lỗi giữa chừng ảnh hưởng ra sao |
| `findById(id)` | Tra cứu theo định danh, có thể không tìm thấy | Mapping ID, chuyển đổi kiểu, đường truy cập và khả năng nhìn thấy dữ liệu |
| `existsById(id)` | Kiểm tra sự tồn tại theo định danh | Truy vấn thực tế, chi phí và dữ liệu có thể thay đổi ngay sau khi kiểm tra hay không |
| `count()` | Lấy số lượng thực thể theo phạm vi repository | Chi phí đếm và cách hệ quản trị thực thi |
| `deleteById(id)` | Yêu cầu xóa theo định danh trong phạm vi hợp đồng của API | Ràng buộc liên quan, callback, cascade và xử lý cạnh tranh |

Không suy ra `saveAll` là “một câu lệnh batch, thành công hoặc thất bại toàn bộ”. Đây là hai thuộc tính độc lập: tối ưu batch và tính nguyên tử. Cả hai đều cần xem xét riêng.

Với `save`, cách dùng an toàn về mặt hợp đồng là nhận lại kết quả:

```java
Customer persisted = customerRepository.save(customer);
String customerId = persisted.getId();
```

Giá trị trả về có thể mang ID, version hoặc trạng thái đã được xử lý khi lưu. Không nên mặc định instance đầu vào luôn chính là instance chứa đầy đủ trạng thái sau thao tác.

Cũng không nên hiểu `save` là cập nhật một phần chỉ những field bạn vừa sửa. Nếu nghiệp vụ cần một thao tác cập nhật nguyên tử trên một số trường, phải chọn API hoặc truy vấn cập nhật mà module hỗ trợ, rồi xác định rõ điều kiện cạnh tranh.

### 3.3. Kiểu kết quả không tạo ràng buộc dữ liệu

`Optional<Customer> findByEmail(...)` diễn đạt kỳ vọng có tối đa một kết quả. Nó không tạo unique index cho email. Nếu dữ liệu thực tế có nhiều kết quả, cách xử lý phải tuân theo hợp đồng truy vấn đơn kết quả của module; ứng dụng không được mặc định hệ thống sẽ tự chọn một bản ghi bất kỳ.

Nếu email phải duy nhất, cần xác định quy tắc chuẩn hóa, phạm vi duy nhất và cơ chế ràng buộc tương ứng. Ví dụ, “duy nhất trong từng tổ chức sau khi chuẩn hóa chữ hoa, chữ thường” khác với “duy nhất trên chuỗi email được lưu nguyên trạng”.

## 4. Từ lời gọi phương thức đến hành vi của store

Một luồng xử lý khái quát của truy vấn repository là:

```text
Lời gọi từ ứng dụng
        |
        v
Repository proxy do module Spring Data tạo
        |
        v
Xác định implementation hoặc truy vấn cần thực thi
        |
        v
Đọc metadata miền và mapping của module
        |
        v
Chuyển thành thao tác mà store hỗ trợ
        |
        v
Driver / công nghệ truy cập dữ liệu / hệ quản trị
        |
        v
Chuyển kết quả về kiểu trả về đã khai báo
```

Luồng này giúp giải thích hai giới hạn quan trọng.

Thứ nhất, một interface hợp lệ về mặt Java chưa chắc là một repository hợp lệ đối với module đang dùng. Module có thể không hỗ trợ một toán tử, kiểu kết quả hoặc cách ánh xạ nhất định. Lỗi có thể được phát hiện khi khởi tạo repository hoặc khi thực thi, tùy trường hợp.

Thứ hai, cùng một khai báo không kéo theo cùng một kế hoạch thực thi. Store có thể biểu diễn điều kiện theo SQL, truy vấn document hoặc một cơ chế khác. Chỉ mục và phân bố dữ liệu tiếp tục quyết định chi phí thực tế.

Commons cung cấp các thành phần dùng chung cho cơ chế này; phần triển khai cụ thể và giới hạn hỗ trợ thuộc từng module. Không nên hình dung Commons là một bộ máy có thể tự chuyển mọi truy vấn thành mọi ngôn ngữ lưu trữ.

## 5. Những khác biệt điển hình giữa các store

| Khía cạnh | Ví dụ khác biệt | Ý nghĩa khi thiết kế |
| --- | --- | --- |
| Mô hình dữ liệu | JPA làm việc với thực thể và mapping quan hệ; MongoDB làm việc với document; Redis có các cấu trúc dữ liệu riêng | Mô hình miền và cách biểu diễn quan hệ có thể phải thay đổi |
| Trạng thái thực thể | JPA có ngữ cảnh persistence và khái niệm thực thể được quản lý; document repository không cung cấp cùng vòng đời đó | Không dựa vào dirty checking như một đặc tính chung của mọi repository |
| Lưu và cập nhật | Cách phân biệt mới/cũ, merge, ghi document hoặc cập nhật trường phụ thuộc module và API | Kiểm tra phạm vi dữ liệu bị ghi và cách xử lý ghi đè |
| Truy vấn | Tập toán tử, biểu thức đặc thù, tìm kiếm toàn văn hoặc địa lý khác nhau | Tách phần truy vấn đặc thù và xác nhận khả năng hỗ trợ |
| Quan hệ | Join, tham chiếu, nhúng document và tải dữ liệu liên quan có cơ chế khác nhau | Không coi một đường dẫn thuộc tính là bảo đảm có join hiệu quả |
| Giao dịch | Hỗ trợ và cấu hình phụ thuộc công nghệ, topology và transaction manager | Xác định rõ ranh giới giao dịch của nghiệp vụ |
| Khả năng thấy thay đổi | Ví dụ, kết quả tìm kiếm Elasticsearch có thể phụ thuộc chu kỳ refresh | Định nghĩa yêu cầu đọc sau ghi theo API và cấu hình cụ thể |
| Chỉ mục và ràng buộc | Cách khai báo, tạo và duy trì chỉ mục hoặc unique constraint khác nhau | Đưa ràng buộc vào thiết kế dữ liệu và quy trình vận hành |

Các khác biệt này không có nghĩa là module nào “đầy đủ hơn” một cách tuyệt đối. Mỗi loại store tối ưu cho những mô hình truy cập khác nhau. Repository chung giúp tổ chức mã; việc chọn store vẫn bắt đầu từ nhu cầu dữ liệu và hành vi ứng dụng.

Một repository kế thừa `JpaRepository` hoặc `MongoRepository` đã thể hiện sự phụ thuộc vào module tương ứng. Điều đó phù hợp khi ứng dụng cần khả năng của module. Chỉ nên đặt ra yêu cầu độc lập store nếu yêu cầu này có giá trị thực tế và có thể mô tả được hành vi cần giữ nguyên.

## 6. Derived queries: chung cách diễn đạt, có giới hạn hỗ trợ

Tên phương thức như `findByStatus` diễn đạt điều kiện dựa trên thuộc tính miền. Cơ chế suy diễn truy vấn dùng các quy ước chung, nhưng từng module quyết định phần nào có thể chuyển thành truy vấn phù hợp.

Cần kiểm tra bốn điểm khi đọc một derived query:

1. **Thuộc tính miền có tồn tại không?** Tên trong phương thức được diễn giải theo mô hình Java, không đơn giản là chép tên cột hoặc tên field lưu trữ.
2. **Toán tử có được module hỗ trợ không?** Không suy ra một từ khóa dùng được trong module này cũng dùng được ở tất cả module khác.
3. **Kiểu trả về có phù hợp không?** Truy vấn đơn kết quả, danh sách, `Page` và `Slice` có yêu cầu khác nhau.
4. **Store thực thi điều kiện đó như thế nào?** Phân biệt hoa thường, đối chiếu chuỗi, xử lý `null` và chi phí truy vấn cần được xem theo ngữ cảnh cụ thể.

Ví dụ, thêm điều kiện bỏ qua hoa thường vào một truy vấn email chưa đủ để bảo đảm truy vấn dùng chỉ mục sẵn có hoặc thống nhất với quy tắc duy nhất của email. Cần kiểm tra cả cách chuẩn hóa dữ liệu lẫn khả năng truy vấn của store.

### Tên phương thức không thay thế được ràng buộc và kiểm soát cạnh tranh

Luồng sau chứa một khoảng cạnh tranh:

```text
Yêu cầu A: kiểm tra email chưa tồn tại
Yêu cầu B: kiểm tra email chưa tồn tại
Yêu cầu A: lưu khách hàng
Yêu cầu B: lưu khách hàng
```

Một phương thức `existsByEmail` chỉ cho biết kết quả của lần kiểm tra đó. Nó không khóa quyền sử dụng email cho lời gọi kế tiếp. Nếu yêu cầu nghiệp vụ là không được trùng, cần cơ chế ràng buộc hoặc đồng bộ phù hợp ở nơi lưu dữ liệu, cùng cách chuyển lỗi thành phản hồi nghiệp vụ.

### Truy vấn khai báo cũng có thể mang tính đặc thù

Một annotation có tên `@Query` ở hai module không có nghĩa là hai annotation đó dùng chung ngôn ngữ. Trong JPA, truy vấn có thể dùng JPQL hoặc SQL native theo cấu hình; trong MongoDB, biểu thức truy vấn theo mô hình MongoDB. Cần đọc đúng package của annotation và tài liệu của module.

Các khả năng như `JpaSpecificationExecutor` cũng thuộc phạm vi JPA. Không gán chúng thành năng lực bắt buộc của mọi repository Spring Data chỉ vì đều xuất hiện trong hệ sinh thái Spring Data.

## 7. Phân trang và sắp xếp: mô tả yêu cầu chưa phải bảo đảm hiệu năng

### 7.1. `Pageable`, `Page` và `Slice` có vai trò khác nhau

`Pageable` mô tả yêu cầu phân trang, thường gồm số trang, kích thước trang và sắp xếp. `Page` và `Slice` mô tả kết quả với mức thông tin khác nhau.

| Kiểu | Thông tin chính | Điều cần cân nhắc |
| --- | --- | --- |
| `Pageable` | Vị trí trang, kích thước và `Sort` | Module và phương thức truy vấn có hỗ trợ không; giới hạn kích thước phù hợp |
| `Page<T>` | Nội dung trang và thông tin tổng số phần tử, tổng số trang | Việc có tổng số thường cần thêm công việc đếm; không mặc định mọi lần gọi luôn phát đúng hai truy vấn |
| `Slice<T>` | Một phần kết quả và thông tin còn phần tiếp theo hay không | Thích hợp khi giao diện không cần tổng số; cách lấy thêm dữ liệu phụ thuộc implementation |

Ví dụ tạo yêu cầu trang đầu tiên, tối đa 20 khách hàng:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(Sort.Order.asc("email"))
        .and(Sort.by(Sort.Order.asc("id")));

Pageable request = PageRequest.of(0, 20, sort);
```

Số trang của `PageRequest` bắt đầu từ `0`. Ví dụ giả định `email` và `id` là những thuộc tính hợp lệ, được module hỗ trợ để sắp xếp.

Thêm khóa duy nhất như `id` làm tiêu chí cuối giúp thứ tự xác định hơn khi nhiều bản ghi có cùng email. Tuy nhiên, điều này không tạo một ảnh chụp dữ liệu xuyên suốt nhiều lần lấy trang. Nếu dữ liệu thay đổi giữa các lần gọi, phân trang theo offset vẫn có thể gặp dịch chuyển vị trí.

Trang có offset lớn cũng không được bảo đảm truy xuất nhanh chỉ vì dùng `Pageable`. Với tập dữ liệu lớn, cần xem xét kế hoạch truy vấn và các cách cuộn hoặc phân trang theo khóa mà module hỗ trợ.

### 7.2. `Sort` không tạo chỉ mục

`Sort` diễn đạt thứ tự mong muốn theo thuộc tính và hướng sắp xếp. Nó không tự tạo chỉ mục phù hợp, không ấn định cùng cách đối chiếu chuỗi ở mọi store và không bảo đảm mọi cách xử lý `null` đều được tôn trọng như nhau.

Ví dụ, các tùy chọn xử lý `null` trong mô hình sắp xếp có thể là gợi ý cho tầng thực thi. Trước khi đưa hành vi này vào yêu cầu sản phẩm, cần xác nhận module và store thực sự hỗ trợ.

Nếu nhận tên trường sắp xếp từ API công khai, nên ánh xạ qua một danh sách trường được phép. Đây vừa là ranh giới hợp đồng của API, vừa giúp tránh cho người dùng phụ thuộc trực tiếp vào toàn bộ mô hình persistence.

## 8. Projection và Query by Example

### 8.1. Projection mô tả hình dạng kết quả

Giả sử danh sách khách hàng chỉ cần ID và email:

```java
public interface CustomerSummary {
    String getId();
    String getEmail();
}
```

Nếu module hỗ trợ loại projection này, repository có thể khai báo phương thức trả về `CustomerSummary` để diễn đạt hình dạng kết quả mong muốn.

Điều có thể dựa vào là hợp đồng của kiểu kết quả. Điều cần kiểm tra là cách module tạo projection, các thuộc tính được hỗ trợ và việc truy vấn thực tế có giảm dữ liệu đọc hay không. Không được suy ra “trả về ít field” luôn đồng nghĩa “chỉ đọc đúng từng ấy field từ store”.

Projection dạng interface, DTO, projection động và projection có biểu thức không có cùng điều kiện hỗ trợ hoặc khả năng tối ưu. Projection lồng nhau cũng cần được xem xét cùng mapping và cách tải dữ liệu liên quan.

Projection còn khác với phân quyền. Nếu một endpoint không được phép trả trường nhạy cảm, hãy thể hiện điều đó trong thiết kế API và kiểm soát truy cập, thay vì chỉ dựa vào hy vọng rằng tầng persistence sẽ không tải trường đó.

### 8.2. Query by Example dùng mô hình chung, còn khả năng truy vấn có giới hạn

Query by Example thường sử dụng ba thành phần:

- **Probe:** một đối tượng chứa các giá trị mẫu.
- **`ExampleMatcher`:** mô tả cách so khớp, các thuộc tính bỏ qua và quy tắc liên quan.
- **`Example`:** kết hợp probe với matcher để chuyển cho API truy vấn được hỗ trợ.

Một module có thể tích hợp các abstraction này qua `QueryByExampleExecutor`. Việc các kiểu đó thuộc phần dùng chung không có nghĩa là mọi repository đều tự hỗ trợ Query by Example hoặc mọi kiểu so khớp đều khả dụng ở mọi store.

Khi dùng Example cho biểu mẫu tìm kiếm khách hàng, cần quyết định rõ:

- Trường nào thực sự tham gia điều kiện và trường nào phải bỏ qua.
- Giá trị `null` được bỏ qua hay được dùng làm điều kiện theo matcher.
- Trường kiểu nguyên thủy có vô tình mang giá trị mặc định vào probe hay không.
- So khớp chuỗi theo chính xác, tiền tố hoặc chứa được module hỗ trợ đến đâu.
- Điều kiện nghiệp vụ có vượt khỏi khả năng biểu đạt của Example không.

Không nên ép một truy vấn có nhiều nhóm điều kiện, quan hệ phức tạp hoặc tổng hợp dữ liệu vào Example chỉ để giữ một API có vẻ dùng chung. Chọn cách truy vấn phù hợp với yêu cầu trước, sau đó đánh giá mức phụ thuộc store chấp nhận được.

## 9. Metadata và auditing: annotation cần cơ chế thực thi

Spring Data có các abstraction và annotation dùng chung để mô tả định danh, phiên bản hoặc thông tin auditing. Metadata cho biết ý nghĩa của thuộc tính; module và cấu hình quyết định việc đọc, cập nhật và sử dụng metadata đó.

Đối với auditing, các annotation thường gặp gồm:

- `@CreatedDate`: thông tin thời điểm tạo.
- `@LastModifiedDate`: thông tin thời điểm sửa gần nhất.
- `@CreatedBy`: thông tin chủ thể tạo.
- `@LastModifiedBy`: thông tin chủ thể sửa gần nhất.

Để các trường này được xử lý, cần bật và cấu hình auditing theo module, bảo đảm mapping phù hợp và cung cấp nguồn chủ thể khi sử dụng auditing người dùng. Với luồng imperative, nguồn chủ thể thường được thể hiện qua `AuditorAware`; luồng reactive có abstraction tương ứng để phù hợp cách thực thi reactive.

Các điểm cần giữ rõ ràng:

1. Có annotation chưa đủ để kết luận auditing đã hoạt động.
2. Ghi qua repository, ghi qua truy vấn cập nhật trực tiếp và ghi từ ứng dụng khác có thể đi qua những cơ chế khác nhau. Cần xác định đường ghi nào kích hoạt auditing.
3. Ghi lại người sửa không đồng nghĩa đã kiểm tra người đó có quyền sửa.
4. Các trường thời gian và người sửa trên bản ghi không tự tạo lịch sử đầy đủ của mọi phiên bản dữ liệu.

Tương tự, metadata phiên bản chỉ có ý nghĩa kiểm soát cập nhật khi module hỗ trợ và đường ghi thực sự tham gia cơ chế đó. Chỉ thêm một trường tên `version` không tự ngăn việc hai yêu cầu ghi đè nhau.

## 10. Giao dịch, khóa và tính nhất quán không thể suy từ tên interface

### 10.1. Ranh giới một phương thức khác với ranh giới một nghiệp vụ

Một nghiệp vụ có thể cần đồng thời tạo khách hàng và tạo một bản ghi đăng ký nhận tin. Hai lời gọi `save` liên tiếp chưa chứng minh hai thay đổi có tính nguyên tử.

```text
Tạo khách hàng thành công
        |
        v
Tạo đăng ký nhận tin thất bại
        |
        v
Cần biết: hệ thống giữ thay đổi đầu, rollback hay xử lý bù?
```

Câu trả lời phụ thuộc các thành phần có cùng tham gia một giao dịch được hỗ trợ hay không, cách cấu hình transaction manager và cách lời gọi đi qua ranh giới giao dịch. Một số implementation cung cấp cấu hình giao dịch mặc định cho các phương thức nhất định; điều đó vẫn không xác định toàn bộ nghiệp vụ nhiều bước.

Ngay cả khi đều dùng `@Transactional`, hai cấu hình có thể điều phối tài nguyên khác nhau. Với nghiệp vụ qua nhiều loại store hoặc hệ thống ngoài, không được mặc định annotation này tạo một giao dịch nguyên tử bao trùm tất cả.

### 10.2. Khóa và kiểm soát cạnh tranh là lựa chọn cụ thể

Khóa bi quan, optimistic locking và thao tác cập nhật nguyên tử có yêu cầu và phạm vi hỗ trợ riêng. Không thể chuyển nguyên cơ chế khóa hàng của hệ quản trị quan hệ sang mọi store chỉ bằng cách giữ tên repository.

Khi nghiệp vụ cần chống ghi đè, hãy mô tả kết quả mong muốn trước: “Nếu bản ghi đã bị sửa từ sau lúc người dùng đọc, cập nhật phải thất bại và yêu cầu tải lại dữ liệu”. Sau đó chọn cơ chế của store để thực hiện hợp đồng đó, bao gồm cả cách ánh xạ lỗi về ứng dụng.

### 10.3. Reactive là một mô hình thực thi riêng

Các abstraction như `ReactiveCrudRepository` biểu diễn kết quả theo kiểu reactive, khác với repository imperative trả về trực tiếp hoặc qua `Optional`. Đây không phải chỉ là thay tên interface: module phải hỗ trợ reactive, nguồn chủ thể auditing và ranh giới giao dịch cũng cần phù hợp.

Không suy ra một API là non-blocking trên toàn bộ đường thực thi chỉ vì ứng dụng bọc lời gọi đồng bộ trong một kiểu reactive. Khả năng thực thi thực tế phải được xem xuyên suốt các thành phần liên quan.

## 11. Tổ chức mã để phần dùng chung có ý nghĩa

Có hai nhu cầu thường gặp, cần lựa chọn theo mục tiêu thực tế.

### 11.1. Dùng trực tiếp repository theo store

Nếu ứng dụng đã chọn JPA và cần truy vấn hoặc cơ chế JPA, một repository dựa trên API JPA là lựa chọn rõ ràng. Phần mã đó công khai sự phụ thuộc công nghệ, giúp người bảo trì biết tài liệu và cơ chế nào cần xem.

Không cần tạo thêm nhiều lớp chỉ để che mọi tên công nghệ. Một lớp trung gian hữu ích khi nó bảo vệ một hợp đồng ứng dụng cụ thể, gom logic chuyển đổi có ý nghĩa hoặc tạo ranh giới thay đổi thực tế.

### 11.2. Đặt hợp đồng nghiệp vụ trước repository khi cần thay implementation

Giả sử tính năng tra cứu khách hàng phải có thể dùng nhiều cách lưu trữ. Ứng dụng có thể định nghĩa một hợp đồng riêng, không kế thừa repository:

```java
import java.util.Optional;

public interface CustomerLookup {
    Optional<CustomerView> findByNormalizedEmail(String normalizedEmail);
}
```

`CustomerView` là kiểu kết quả của ứng dụng. Để hợp đồng này có ý nghĩa, cần quy định thêm:

- Email được chuẩn hóa theo quy tắc nào và trong phạm vi khách hàng nào.
- Một email được phép ánh xạ tới bao nhiêu khách hàng.
- Trường hợp không tồn tại trả về rỗng như thế nào.
- Yêu cầu đọc sau ghi và cách biểu diễn lỗi truy cập dữ liệu.

Implementation dùng JPA và implementation dùng MongoDB có thể sử dụng các repository riêng, miễn là cùng đáp ứng hợp đồng trên. Những chi tiết như mapping, biểu thức truy vấn và chỉ mục nằm ở adapter tương ứng.

Việc dùng chung một interface không chứng minh hai adapter có hành vi tương đương. Cần đối chiếu cả kết quả và các yêu cầu có ý nghĩa với nghiệp vụ: tính duy nhất, phân biệt hoa thường, thời điểm thấy dữ liệu và xử lý cập nhật đồng thời.

### 11.3. Mở rộng repository với phạm vi rõ ràng

Khi nhiều repository trong cùng hệ thống cần một nhóm phương thức chung, có thể thiết kế base interface hoặc repository fragment theo cơ chế module hỗ trợ. Với base repository interface chỉ dùng để kế thừa, `@NoRepositoryBean` giúp thể hiện rằng không tạo repository bean trực tiếp từ interface trung gian đó.

Tuy nhiên, thêm phương thức vào interface chưa tự cung cấp thuật toán cho mọi store. Nếu phương thức yêu cầu hành vi mới, cần implementation hoặc cơ chế truy vấn thích hợp. Một fragment dùng API riêng của MongoDB vẫn là implementation phụ thuộc MongoDB dù được gắn vào một interface có tên tổng quát.

## 12. Tình huống thực hành: chuyển danh sách khách hàng sang store khác

Nhóm phát triển đang có màn hình liệt kê khách hàng với tìm theo trạng thái, sắp xếp theo email, hiển thị tổng số và các trường auditing. Một đề xuất cho rằng chỉ cần đổi dependency vì interface đã dùng các kiểu của Commons.

Hãy phân tích đề xuất theo từng yêu cầu:

| Yêu cầu | Phần có thể tái sử dụng về ý tưởng | Phần phải xác nhận hoặc triển khai lại |
| --- | --- | --- |
| Tìm theo trạng thái | Ý nghĩa bộ lọc và đầu vào của ứng dụng | Mapping enum, khả năng truy vấn và chỉ mục |
| Sắp xếp theo email | Yêu cầu tăng/giảm và quy tắc thứ tự nghiệp vụ | Cách đối chiếu chuỗi, xử lý `null`, khóa phụ và chi phí |
| Hiển thị tổng số | Giao diện cần thông tin tổng để điều hướng | Khả năng trả tổng, chi phí đếm và kỳ vọng nhất quán khi dữ liệu đổi |
| Chỉ trả ID và email | Hình dạng dữ liệu phục vụ màn hình | Loại projection được hỗ trợ và dữ liệu thực tế được đọc |
| Có thời điểm, người tạo/sửa | Ý nghĩa các trường auditing | Cấu hình, callback, nguồn thời gian/chủ thể và các đường ghi được bao phủ |
| Email không trùng | Quy tắc nghiệp vụ | Cơ chế ràng buộc, chuẩn hóa và xử lý lỗi cạnh tranh |

Một kế hoạch phù hợp sẽ giữ lại hợp đồng API và hành vi nghiệp vụ đã xác định, sau đó triển khai mapping, repository và cấu hình cho store mới. Trước khi thay thế, cần kiểm tra trên store thực tế những tình huống có khả năng làm thay đổi hành vi.

Ví dụ, thử hai yêu cầu tạo cùng email đồng thời có giá trị hơn việc chỉ xác nhận cả hai repository đều có phương thức `save`. Thử danh sách có email trùng giá trị sắp xếp hoặc có `null` giúp phát hiện khác biệt mà kiểm tra với vài bản ghi đơn giản có thể bỏ qua.

## 13. Những suy luận dễ sai

| Suy luận | Cách hiểu chính xác hơn |
| --- | --- |
| “Cùng kế thừa `CrudRepository` nên mọi hành vi lưu đều giống nhau.” | Hợp đồng thao tác có phần chung; vòng đời thực thể, mapping và cách lưu cần xem theo module. |
| “Có từ khóa truy vấn trong cơ chế chung thì mọi store phải chạy được.” | Phải kiểm tra tập tính năng mà module đang dùng hỗ trợ. |
| “`Optional` bảo đảm email là duy nhất.” | Kiểu kết quả diễn đạt kỳ vọng; ràng buộc duy nhất cần được bảo đảm riêng. |
| “`Page` lúc nào cũng rẻ và luôn dùng đúng hai truy vấn.” | Việc lấy tổng có chi phí; chiến lược thực thi có thể khác tùy trường hợp. |
| “Đổi sang projection chắc chắn tránh đọc mọi trường còn lại.” | Khả năng tối ưu phụ thuộc loại projection, mapping và implementation. |
| “Gắn auditing là đã có lịch sử thay đổi đầy đủ.” | Các trường auditing và lịch sử phiên bản là những yêu cầu khác nhau. |
| “`saveAll` là giao dịch batch nguyên tử.” | API không tự hứa cả tối ưu batch lẫn tính nguyên tử cho mọi store. |
| “Giữ nguyên interface là có thể đổi store mà không kiểm tra hành vi.” | Cần đối chiếu hợp đồng nghiệp vụ, truy vấn, dữ liệu, giao dịch và yêu cầu nhất quán. |

## 14. Tự kiểm tra khả năng phân biệt hợp đồng

### Câu 1

Một phương thức trả về `Page<CustomerSummary>`. Có thể khẳng định truy vấn chỉ đọc hai trường của projection và luôn thực hiện đúng một lệnh đếm không?

**Gợi ý trả lời:** Không. Kiểu kết quả cho biết hình dạng dữ liệu và thông tin trang cần cung cấp. Tối ưu projection và chiến lược lấy tổng thuộc implementation, module và truy vấn cụ thể.

### Câu 2

Hai module cùng chấp nhận `Sort.by("email")`. Có đủ cơ sở để hứa với người dùng rằng chuỗi có dấu, chữ hoa và giá trị `null` sẽ có thứ tự hoàn toàn giống nhau không?

**Gợi ý trả lời:** Chưa đủ. Cần xác định quy tắc thứ tự nghiệp vụ, khả năng đối chiếu chuỗi và xử lý `null` của từng store, rồi bảo đảm implementation đáp ứng yêu cầu đó.

### Câu 3

Repository có `existsByEmail` và `save`. Làm thế nào đánh giá yêu cầu “không bao giờ tạo hai khách hàng cùng email”?

**Gợi ý trả lời:** Không chỉ ghép hai lời gọi. Phải xem phạm vi duy nhất, chuẩn hóa email, ràng buộc hoặc cơ chế đồng bộ phù hợp, cùng xử lý lỗi khi các yêu cầu diễn ra đồng thời.

### Câu 4

Một nhóm muốn dùng chung base repository với phương thức cập nhật số dư nguyên tử. Chỉ khai báo phương thức trong interface đã đủ chưa?

**Gợi ý trả lời:** Chưa. Phải định nghĩa điều kiện thành công/thất bại và cơ chế cập nhật nguyên tử cho từng store, cung cấp implementation tương ứng và xác nhận giới hạn giao dịch, cạnh tranh.

### Câu 5

Ứng dụng đã có `@LastModifiedBy` nhưng một đường cập nhật trực tiếp không thay đổi người sửa. Nên kiểm tra tầng nào?

**Gợi ý trả lời:** Kiểm tra cấu hình auditing của module, nguồn chủ thể và đường thực thi của thao tác cập nhật. Cần xác định thao tác đó có đi qua cơ chế kích hoạt auditing hay phải xử lý metadata theo cách khác.

Khi đọc hoặc thiết kế một repository, hãy luôn gắn từng lời hứa với nơi chịu trách nhiệm thực hiện nó: Commons định nghĩa abstraction, module diễn giải và tích hợp, store cung cấp cơ chế lưu trữ, còn ứng dụng quyết định hợp đồng nghiệp vụ cần bảo đảm.