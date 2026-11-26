# Khi nào trả projection thay cho entity đầy đủ?

Trong chương **Projection interface** của module **SPRING_DATA_COMMONS**, câu hỏi đầu tiên là: phía gọi thực sự cần dữ liệu và hành vi nào từ repository? Một màn hình danh sách có thể chỉ cần mã khách hàng, tên và email; một thao tác thay đổi thông tin khách hàng lại cần làm việc với mô hình nghiệp vụ và cơ chế lưu trữ tương ứng.

**Ưu tiên projection cho một nhu cầu đọc có tập thuộc tính rõ ràng. Ưu tiên entity khi cần thực hiện hành vi nghiệp vụ trên aggregate hoặc cập nhật trạng thái của nó.** Sau đó kiểm tra khả năng của module store và loại truy vấn đang dùng, vì Commons cung cấp abstraction chung còn cách truy xuất dữ liệu do từng store thực hiện.

## 1. Projection biểu đạt một góc nhìn có mục đích

Repository thường làm việc với một aggregate root, chẳng hạn `Customer`. Projection cho phép khai báo một kiểu kết quả chỉ bộc lộ các thuộc tính cần cho một nhu cầu đọc. Với interface projection, Spring Data tạo proxy lúc thực thi để cung cấp các accessor đã khai báo. Xem [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

Giả sử ứng dụng có domain type `Customer` với những property sau:

| Property | Kiểu Java | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh khách hàng |
| `fullName` | `String` | Tên hiển thị |
| `email` | `String` | Địa chỉ liên hệ |
| `phoneNumber` | `String` | Số điện thoại |
| `active` | `boolean` | Trạng thái hoạt động |
| `internalNote` | `String` | Ghi chú nội bộ |
| `createdAt` | `Instant` | Thời điểm tạo |

Một danh sách liên hệ chỉ cần ba thuộc tính đầu tiên. Có thể mô tả nhu cầu đó bằng một interface riêng:

```java
public interface CustomerContactView {

    Long getId();

    String getFullName();

    String getEmail();
}
```

Các getter biểu đạt các property `id`, `fullName` và `email` của domain type. Interface này không đại diện cho toàn bộ khách hàng: nó không cung cấp số điện thoại, ghi chú nội bộ hay hành vi đổi email.

Để giữ đúng ý nghĩa projection, `CustomerContactView` là kiểu nằm ngoài hệ thống kế thừa của entity. Không cho `Customer` triển khai interface này rồi mặc định rằng trả về interface sẽ biến việc đọc thành projection; trả về một interface vốn thuộc hệ kiểu của entity có thể vẫn trả về entity đã được materialize. Quy tắc này cũng được nêu trong [tài liệu projection của Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html).

### “Entity đầy đủ” không có nghĩa mọi quan hệ đều đã được tải

Trong bài này, “trả entity đầy đủ” nói đến việc trả kiểu domain entity thay vì một kiểu kết quả có phạm vi thuộc tính nhỏ hơn. Nó không cam kết mọi quan hệ, collection hay dữ liệu lazy đều được tải ngay.

Vì vậy, có hai câu hỏi khác nhau:

- **Hợp đồng trả về có gì?** Entity, projection interface hay DTO?
- **Store thực sự đọc gì và khi nào?** Thuộc tính, cột, field, quan hệ và các lượt truy vấn cụ thể.

Lựa chọn kiểu trả về giúp thiết kế hợp đồng. Muốn kết luận về lượng dữ liệu đọc, cần xem cách store thực thi hợp đồng đó.

## 2. Những trường hợp nên trả projection

### Danh sách, bảng tra cứu và kết quả tìm kiếm

Một bảng khách hàng hiển thị `id`, `fullName` và `email` không cần mang theo ghi chú nội bộ chỉ để bỏ qua khi render. `CustomerContactView` làm cho nhu cầu đọc thể hiện trực tiếp trong chữ ký repository.

Lợi ích về thiết kế là rõ ràng ngay cả trước khi đo hiệu năng: người gọi biết mình được dùng ba thuộc tính nào, và thay đổi mô hình khách hàng không tự động bổ sung thêm trường vào hợp đồng này.

### Một chức năng đọc dùng tập thuộc tính ổn định

Ví dụ xuất danh sách liên hệ cho một đợt chăm sóc khách hàng chỉ cần mã, tên và email. Nếu mỗi hàng đều có cùng cấu trúc, projection đặt tên theo mục đích giúp các bên thống nhất đầu ra.

Ngược lại, nếu một chức năng liên tục cần thêm thuộc tính để kiểm tra quy tắc nghiệp vụ, nên xem lại việc chọn projection quá hẹp. Tránh đọc projection rồi lập tức truy vấn entity cho từng hàng chỉ để bổ sung dữ liệu thiếu.

### Cần giảm sự phụ thuộc vào cấu trúc entity

Mô hình lưu trữ có thể chứa thông tin phục vụ nghiệp vụ, metadata và quan hệ không liên quan đến một màn hình. Một kiểu kết quả nhỏ giúp phần đọc ít phụ thuộc hơn vào toàn bộ mô hình đó.

Điều này đặc biệt hữu ích khi cùng một entity phục vụ nhiều chức năng: danh sách liên hệ cần email, màn hình giao nhận cần địa chỉ, còn màn hình quản trị có thể cần metadata tạo và cập nhật. Mỗi nhu cầu nên có tập thuộc tính được giải thích bằng chức năng sử dụng.

### Có cơ hội giảm lượng dữ liệu truy xuất

Projection có thể giúp store chọn ít dữ liệu hơn khi loại projection và loại query cho phép tối ưu. Đây là lý do đáng cân nhắc khi kết quả có nhiều hàng hoặc entity có các thuộc tính lớn ít được dùng.

Tuy nhiên, số getter ít hơn không tự chứng minh số cột hay field đọc từ nguồn cũng ít tương ứng. Cần tách lợi ích của hợp đồng nhỏ khỏi lợi ích hiệu năng phải được xác nhận trên cách thực thi thực tế.

## 3. Những trường hợp nên làm việc với entity

### Cần gọi hành vi nghiệp vụ hoặc cập nhật aggregate

Giả sử khách hàng đổi email. Ứng dụng cần xác thực yêu cầu, áp dụng quy tắc đổi email và lưu trạng thái mới. Một góc nhìn gồm ba getter không phải đối tượng thay thế cho aggregate thực hiện hành vi này.

Một luồng minh họa, giả sử `Customer` có phương thức nghiệp vụ `changeEmail`:

```java
Customer customer = repository.findById(customerId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Customer not found"));

customer.changeEmail(newEmail);

Customer saved = repository.save(customer);
```

`CrudRepository` định nghĩa `findById` để lấy entity và `save` để lưu một instance thuộc kiểu entity của repository. Khi lưu, sử dụng giá trị trả về nếu cần tiếp tục làm việc với trạng thái đã lưu. Xem [API CrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

Đoạn trên chỉ minh họa lựa chọn kiểu đối tượng. Ranh giới giao dịch, kiểm tra phiên bản và quy tắc cập nhật cần được thiết kế theo module store cùng nghiệp vụ của ứng dụng.

### Cần đánh giá một tập quy tắc sử dụng trạng thái aggregate

Một thao tác nghiệp vụ có thể cần nhiều dữ liệu liên quan, chứ không chỉ vài trường để hiển thị. Nếu việc cắt nhỏ thành nhiều projection khiến service phải ghép lại trạng thái để quyết định, làm việc với aggregate có thể diễn đạt yêu cầu rõ hơn.

Điều này không có nghĩa mọi phép kiểm tra đều phải tải entity. Một câu hỏi như “khách hàng này có tồn tại không?” có thể phù hợp hơn với `existsBy…`; chỉ cần số lượng thì cân nhắc `countBy…`. Chọn kiểu trả lời sát câu hỏi trước khi chọn entity hay projection.

### Dữ liệu cần thiết đã có sẵn trong cùng luồng xử lý

Nếu entity đã được tải để xử lý một nghiệp vụ hợp lệ, tạo thêm truy vấn projection chỉ để lấy lại ba giá trị đang có không nhất thiết mang lại lợi ích. Có thể ánh xạ phần dữ liệu cần trả từ entity hiện tại.

Ví dụ, sau khi đổi email thành công, service có thể tạo DTO phản hồi từ `saved`. Projection là một lựa chọn truy vấn; không cần biến mọi đoạn tạo dữ liệu phản hồi thành một truy vấn mới.

## 4. Ví dụ repository có cả đường đọc projection và đường dùng entity

Các kiểu dưới đây được đặt trong ứng dụng đã cấu hình Spring Data store và ánh xạ `Customer`. Ví dụ không lựa chọn annotation ánh xạ của một store cụ thể.

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<CustomerContactView> findByActiveTrueOrderByIdAsc();

    Optional<CustomerContactView> findContactById(Long id);
}
```

Repository có ba khả năng với ý nghĩa khác nhau:

| Phương thức | Kết quả | Mục đích |
| --- | --- | --- |
| `findByActiveTrueOrderByIdAsc()` | Danh sách góc nhìn liên hệ | Hiển thị khách hàng đang hoạt động |
| `findContactById(id)` | Một góc nhìn liên hệ nếu có | Đọc thông tin liên hệ của một khách hàng |
| `findById(id)` kế thừa từ `CrudRepository` | Entity nếu có | Làm việc với khách hàng theo hợp đồng CRUD |

`Optional<CustomerContactView>` biểu đạt trường hợp truy vấn một kết quả có thể không tìm thấy. Các dạng kết quả được hỗ trợ chung được mô tả trong [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html); cần đối chiếu thêm khả năng của store.

### Không đổi kiểu trả về của base method để tạo projection

Trong repository kế thừa `CrudRepository<Customer, Long>`, không khai báo lại `findById(Long)` với kiểu `Optional<CustomerContactView>`. Kiểu đó không tương thích với phương thức CRUD đã kế thừa; đây cũng không phải cách mặc định để biến base method thành projection query.

Ở ví dụ, `findContactById` là query method riêng: phần mô tả `Contact` nằm trước `By`, còn điều kiện vẫn là property `id`. Cách đặt tên giúp giữ rõ hai đường sử dụng mà không thay hợp đồng CRUD.

## 5. Sử dụng projection trong service đọc

Service có thể dùng projection trực tiếp trong nội bộ, rồi tạo một kiểu phản hồi ổn định cho bên ngoài. Ví dụ sau dùng Java 17 trở lên cho record và `Stream.toList()`.

```java
public record CustomerContactResponse(
        Long id,
        String fullName,
        String email) {

    public static CustomerContactResponse from(
            CustomerContactView view) {

        return new CustomerContactResponse(
                view.getId(),
                view.getFullName(),
                view.getEmail());
    }
}
```

```java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class CustomerContactService {

    private final CustomerRepository repository;

    public CustomerContactService(CustomerRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public List<CustomerContactResponse> listActiveContacts() {
        return repository.findByActiveTrueOrderByIdAsc()
                .stream()
                .map(CustomerContactResponse::from)
                .toList();
    }

    public Optional<CustomerContactResponse> getContact(Long id) {
        Objects.requireNonNull(id, "id");

        return repository.findContactById(id)
                .map(CustomerContactResponse::from);
    }
}
```

Luồng đọc trong ví dụ là:

```text
Yêu cầu danh sách liên hệ
    -> Query theo trạng thái active
    -> CustomerContactView: id, fullName, email
    -> CustomerContactResponse
    -> Bên sử dụng kết quả
```

Phép ánh xạ sang response không đọc thêm entity. Nó chỉ dùng ba getter đã có trong projection. Kiểu phản hồi cũng không mang theo proxy projection ra ngoài lớp ứng dụng.

Đây là một lựa chọn thiết kế, không phải yêu cầu bắt buộc rằng mọi projection đều phải được bọc thêm DTO. Nếu một tầng nội bộ chỉ cần đọc vài giá trị trong cùng ngữ cảnh, có thể sử dụng interface projection trực tiếp.

Hai phương thức đọc có điều kiện khác nhau: danh sách chỉ lấy khách hàng đang hoạt động, còn `findContactById` chỉ lọc theo mã. Nếu chức năng đọc chi tiết cũng chỉ được phép trả khách hàng đang hoạt động, phải bổ sung điều kiện tương ứng vào truy vấn và quy tắc sử dụng. Projection không tự bổ sung bộ lọc đó.

### Đổi hình dạng phản hồi khác với giảm dữ liệu tại nguồn

So sánh hai cách:

| Cách làm | Thời điểm thu hẹp dữ liệu |
| --- | --- |
| Đọc `Customer`, sau đó tạo DTO | Thu hẹp cách biểu diễn sau khi đã đọc entity |
| Truy vấn trả `CustomerContactView`, sau đó tạo DTO | Nêu tập thuộc tính cần đọc ngay tại hợp đồng query, rồi chọn cách biểu diễn phản hồi |

Cả hai cách đều có thể tạo ra phản hồi chỉ có ba trường. Chỉ nhìn JSON đầu ra không đủ biết cơ sở dữ liệu đã đọc gì.

Tương tự, `ProjectionFactory.createProjection(type, source)` tạo một góc nhìn từ đối tượng nguồn đã có; API này không thực hiện một truy vấn thay thế cho truy vấn trước đó. Do vậy, bọc entity đã tải bằng projection không làm giảm ngược lượng dữ liệu của lần đọc đã hoàn tất. Đây là hệ quả từ hợp đồng [ProjectionFactory](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/projection/ProjectionFactory.html).

## 6. Khả năng tối ưu phụ thuộc hình dạng projection và store

### Bắt đầu bằng một tập property rõ ràng

`CustomerContactView` chỉ khai báo các getter khớp property của `Customer`. Đây là dạng closed projection thuận lợi để xác định các giá trị đầu vào cần thiết. Nếu dùng biểu thức `@Value`/SpEL truy cập tùy ý vào đối tượng nguồn, projection trở thành dạng open và không còn cùng khả năng suy ra tập thuộc tính để tối ưu. Xem [Closed và Open Projections](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html#projections.interfaces.closed).

Ở mức abstraction, `ProjectionInformation` mô tả các input property và cho biết chỉ cung cấp các property đó có đủ để tạo proxy hoạt động hay không. Điều này giúp hiểu vì sao khai báo projection ảnh hưởng đến khả năng phân tích dữ liệu cần đọc. Xem [API ProjectionInformation](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/projection/ProjectionInformation.html).

Trong bài mở đầu này, nên giữ interface đơn giản. Một trường tính toán nhỏ có thể được tạo trong DTO từ những giá trị đã đọc; chưa cần đưa biểu thức động truy cập toàn bộ đối tượng nguồn vào projection.

### Với JPA, chú ý property lồng và quan hệ

Spring Data JPA thường dùng truy vấn `Tuple` để tạo proxy cho interface projection. Với derived query, khả năng giới hạn lựa chọn áp dụng đến property ở cấp cao nhất; property lồng dẫn đến join có thể khiến toàn bộ phần được join được materialize. Xem [Using Projections with JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa).

Vì vậy, mở rộng projection từ ba trường đơn giản sang địa chỉ, danh sách đơn hàng hoặc nhiều quan hệ không bảo đảm truy vấn vẫn nhẹ tương ứng với vài getter nhìn thấy trong interface. Cần xem truy vấn và dữ liệu thực nhận.

### Với store khác, đối chiếu đúng cơ chế hỗ trợ

Ở MongoDB, dữ liệu được tổ chức theo document; ở JPA, việc đọc thông qua mô hình ánh xạ quan hệ và provider. Không áp dụng cách giải thích bằng cột SQL cho mọi module Spring Data.

Điểm chung của bài là thiết kế kiểu kết quả theo nhu cầu đọc. Điểm cần xác nhận tại dự án là store có hỗ trợ dạng projection đó, loại query đang dùng có tận dụng được tập property hay không và các property lồng được đọc như thế nào.

Không giả định rằng một annotation `@Query`, một dạng truy vấn native hoặc một cơ chế alias của module này cũng có cùng hợp đồng ở module khác.

### Ít thuộc tính hơn vẫn cần kiểm soát số hàng

Một danh sách trả ba thuộc tính nhưng có hàng triệu phần tử vẫn có thể vượt khả năng xử lý của ứng dụng. Projection thu hẹp hình dạng mỗi kết quả; phân trang, slicing hoặc scrolling kiểm soát cách lấy nhiều kết quả. Đó là hai quyết định bổ sung cho nhau.

Phương thức trả `List` trong bài giúp ví dụ ngắn và phù hợp tập dữ liệu thực hành nhỏ. Với danh sách có thể tăng lớn, thiết kế thêm cơ chế lấy từng phần mà store hỗ trợ.

## 7. Chọn theo nhu cầu cụ thể

| Nhu cầu | Hướng lựa chọn | Lý do |
| --- | --- | --- |
| Bảng liên hệ chỉ hiện mã, tên, email | Interface projection | Tập thuộc tính nhỏ và rõ |
| Chi tiết chỉ đọc một số thông tin xác định | Projection hoặc DTO phù hợp | Màn hình chi tiết vẫn có thể dùng góc nhìn riêng |
| Đổi email theo quy tắc của khách hàng | Entity/aggregate cho luồng cập nhật | Cần hành vi và trạng thái phục vụ cập nhật |
| Kiểm tra có khách hàng phù hợp hay không | `existsBy…` khi được hỗ trợ | Không cần trả cả một đối tượng |
| Chỉ cần tổng số khách hàng | `countBy…` hoặc truy vấn đếm phù hợp | Câu trả lời là một giá trị số |
| Đã có entity sau một thao tác cập nhật | Ánh xạ dữ liệu phản hồi từ entity đó | Có thể tránh một lần đọc lại không cần thiết |
| Dữ liệu tổng hợp không khớp một entity | Kiểu kết quả báo cáo riêng | Không nên ép vào hình dạng entity đầy đủ |
| Muốn mọi màn hình dùng cùng một view nhiều getter | Xem lại nhu cầu của từng màn hình | Một view quá rộng làm mất mục đích của projection |

Một quy trình quyết định thực tế:

1. Viết ra các giá trị phía gọi cần dùng, kèm các hành vi cần thực hiện.
2. Nếu chỉ cần tồn tại hoặc số lượng, chọn kiểu câu trả lời tương ứng.
3. Nếu cần hành vi cập nhật aggregate, xác định cách làm việc với entity và giao dịch.
4. Nếu chỉ đọc tập thuộc tính rõ ràng, cân nhắc projection hoặc DTO.
5. Đối chiếu khả năng store và cách thực thi query trước khi đưa ra kết luận hiệu năng.

Đừng chọn entity chỉ vì repository quản lý entity đó; cũng đừng chọn projection chỉ vì interface ngắn hơn class. Kiểu kết quả cần giải thích được bằng yêu cầu sử dụng cụ thể.

## 8. Giới hạn cần hiểu khi thiết kế hợp đồng đọc

### Projection không phải một entity bị bỏ bớt dữ liệu để đem lưu

Không tạo một `Customer` mới từ ba trường projection rồi coi nó là bản thay thế đầy đủ cho khách hàng hiện có. Khi lưu một đối tượng thiếu trạng thái cần thiết, hậu quả phụ thuộc cơ chế insert/update, mapping và store; các thuộc tính không có trong view không được tự hiểu là “giữ nguyên”.

Nếu nhận yêu cầu đổi email, tải hoặc cập nhật theo một luồng nghiệp vụ được thiết kế rõ. Projection dùng cho phần đọc không nên trở thành đầu vào ngầm cho một thao tác ghi toàn bộ aggregate.

### Getter ít hơn không phải cơ chế phân quyền

Không đưa `internalNote` vào view giúp hợp đồng liên hệ chỉ bộc lộ các trường được chọn. Tuy nhiên, điều kiện người dùng được đọc khách hàng nào vẫn phải được áp dụng bằng quy tắc truy cập và truy vấn phù hợp.

Ví dụ, một ứng dụng nhiều tenant vẫn cần giới hạn dữ liệu theo tenant. View chỉ có tên và email không tự giới hạn khách hàng thuộc tenant nào.

### Không thêm getter “để phòng khi cần”

Mỗi getter nên gắn với một nhu cầu đọc hiện tại. Thêm điện thoại, ghi chú, metadata auditing và nhiều quan hệ vào một view liên hệ dùng chung có thể làm view dần trở lại thành hình dạng của entity.

Khi yêu cầu khác nhau rõ rệt, cân nhắc các góc nhìn có tên thể hiện mục đích. Đồng thời tránh tạo hàng loạt interface gần giống nhau nếu chúng không giúp diễn đạt một khác biệt sử dụng thực sự.

### Không công bố con số tối ưu khi chưa có bằng chứng

Khi chuyển query từ entity sang projection, những điểm đáng quan sát là:

- Thuộc tính, cột hoặc field thực sự được yêu cầu từ nguồn.
- Số lượt truy vấn phát sinh, nhất là khi có quan hệ lồng.
- Số hàng trả về và kích thước dữ liệu truyền.
- Chi phí ánh xạ và thời gian xử lý với dữ liệu đại diện.

Đây là các tiêu chí để đánh giá khi tích hợp, không phải kết quả đo của bài. Một projection có hợp đồng tốt vẫn cần được đánh giá trong truy vấn và tải sử dụng thực tế.

## 9. Bài thực hành: chọn đúng kiểu kết quả

Giả sử hệ thống có ba chức năng:

| Chức năng | Dữ liệu hoặc hành vi cần |
| --- | --- |
| Danh sách khách hàng đang hoạt động | Mã, tên, email |
| Màn hình giao nhận | Mã, tên, số điện thoại và địa chỉ giao nhận |
| Đổi email | Áp dụng quy tắc đổi email và lưu trạng thái mới |

Thực hiện các bước sau trong một dự án đã cấu hình store phù hợp:

1. Chọn kiểu kết quả cho từng chức năng và giải thích dựa trên dữ liệu hoặc hành vi cần dùng.
2. Khai báo `CustomerContactView` và query method cho danh sách khách hàng hoạt động.
3. Đọc kết quả bằng các getter, sau đó tạo response chỉ có các trường của chức năng liên hệ.
4. Giữ `findById` của CRUD cho luồng cần làm việc với entity; dùng query method có tên riêng cho projection theo mã.
5. Giải thích vì sao thêm địa chỉ lồng vào view cần xem lại cách store truy xuất dữ liệu.
6. So sánh đọc entity rồi ánh xạ DTO với đọc projection ngay từ query: cách nào chỉ đổi hình dạng đầu ra, cách nào có cơ hội thu hẹp dữ liệu tại nguồn?
7. Với màn hình giao nhận, xác định tập thuộc tính riêng thay vì thêm mọi trường vào view liên hệ.
8. Nêu dữ liệu cần quan sát trước khi khẳng định phương án projection giúp giảm thời gian hoặc lượng dữ liệu đọc.

Kết quả cần đạt là một quyết định có căn cứ cho từng nhu cầu: góc nhìn đọc đủ dữ liệu để hoàn thành chức năng, còn luồng nghiệp vụ dùng đúng đối tượng và cơ chế cập nhật của store. Các ví dụ trong bài minh họa cách thiết kế hợp đồng; chúng không phải báo cáo chạy thử hay kết quả đo hiệu năng.