# sortBy, limit, as và project

Fluent query cho phép cấu hình cách thực thi một truy vấn ngay tại nơi gọi repository. Khi đã có điều kiện tìm kiếm, ứng dụng còn cần quyết định thứ tự kết quả, số bản ghi cần lấy, kiểu dữ liệu trả về và những thuộc tính cần dùng. Bốn phương thức `sortBy`, `limit`, `as` và `project` phục vụ các quyết định đó.

Trong Spring Data Commons, các phương thức này thuộc abstraction `FluentQuery` và các biến thể thực thi của nó. Store module cụ thể chịu trách nhiệm chuyển cấu hình thành truy vấn, ánh xạ kết quả và triển khai những thao tác được hỗ trợ. Không suy luận rằng mọi kho dữ liệu có cùng mức hỗ trợ chỉ vì cùng sử dụng interface Commons.

Bài học sử dụng luồng QBE đồng bộ thông qua `QueryByExampleExecutor.findBy`. Các ví dụ giả định phiên bản dependency có các phương thức được minh họa và store đang dùng hỗ trợ chúng. Khi một thao tác chưa được triển khai, chẳng hạn giới hạn kết quả trong một tổ hợp API cụ thể, có thể gặp `UnsupportedOperationException`; không giải quyết bằng cách bỏ qua cấu hình một cách âm thầm.

## 1. Tách điều kiện tìm kiếm khỏi cách lấy kết quả

Với Query by Example, probe và `ExampleMatcher` xác định điều kiện. Callback của `findBy` xác định cách lấy kết quả cho điều kiện đó:

```java
List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName"))
                .limit(10)
                .all());
```

Có thể đọc chuỗi trên theo ba bước:

1. Dùng `example` để chọn những khách hàng thỏa điều kiện.
2. Cấu hình thứ tự và giới hạn trên fluent query.
3. Gọi `all()` để thực thi thao tác lấy danh sách theo cấu hình đó.

Tên `all()` không có nghĩa là bỏ qua giới hạn đã được cấu hình. Trong tổ hợp `limit(10).all()` được store hỗ trợ, kết quả là danh sách tối đa 10 phần tử, có thể ít hơn nếu không có đủ bản ghi khớp.

Bốn phương thức có vai trò khác nhau:

| Phương thức | Câu hỏi được giải quyết | Có tự thực thi truy vấn không? |
| --- | --- | --- |
| `sortBy(Sort)` | Kết quả cần có thứ tự nào? | Không |
| `limit(int)` | Cần lấy tối đa bao nhiêu kết quả cho thao tác phù hợp? | Không |
| `as(Class<R>)` | Cần ánh xạ kết quả sang kiểu nào? | Không |
| `project(...)` | Cần đưa những thuộc tính hoặc đường dẫn nào vào phép chiếu? | Không |

Một phương thức kết thúc như `all()`, `first()`, `one()` hoặc `page(...)` mới chọn cách lấy kết quả. Các thao tác đếm và kiểm tra tồn tại có mục tiêu khác với việc lấy một danh sách đã được giới hạn.

## 2. Mô hình và repository dùng trong ví dụ

Giả sử mô hình khách hàng có các thuộc tính Java:

| Thuộc tính | Kiểu | Mục đích |
| --- | --- | --- |
| `id` | `Long` | Định danh |
| `fullName` | `String` | Họ tên |
| `email` | `String` | Email |
| `city` | `String` | Thành phố |
| `status` | `String` | Trạng thái nghiệp vụ |
| `active` | `Boolean` | Đang hoạt động hay không |
| `createdAt` | `Instant` | Metadata thời gian tạo |
| `version` | `Long` | Metadata phiên bản |

`Customer` có constructor không tham số cùng getter/setter tương ứng. Mapping lưu trữ phải được bổ sung theo store, chẳng hạn entity JPA hoặc document MongoDB; bảng trên không phải một mapping dùng nguyên trạng cho mọi kho dữ liệu.

Repository công bố khả năng QBE:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Tạo điều kiện tìm khách hàng đang hoạt động tại Huế:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCity("Huế");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withIgnorePaths("id", "createdAt", "version");

Example<Customer> example = Example.of(probe, matcher);
```

Các ví dụ tiếp theo sử dụng biến `example` này và một `repository` được Spring cung cấp. Kiểu `Boolean` cho phép các yêu cầu khác dùng `null` để biểu diễn không lọc theo `active`. Các trường metadata được bỏ qua vì không phải tiêu chí của bài toán tìm kiếm đang xét.

## 3. sortBy: cấu hình thứ tự theo thuộc tính miền

`sortBy` nhận một đối tượng `Sort`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;

List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").ascending())
                .all());
```

Thứ tự tăng hay giảm có thể được chỉ định theo từng thuộc tính:

```java
Sort order = Sort.by(
        Sort.Order.asc("fullName"),
        Sort.Order.asc("id"));

List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(order).all());
```

Trong ví dụ, `fullName` là khóa sắp xếp chính. `id` phân định thứ tự giữa các khách hàng có cùng tên.

### Vì sao cần khóa phân định khi dùng limit?

Giả sử nhiều người có cùng `fullName` và ứng dụng lấy 10 người đầu. Nếu chỉ sắp xếp theo tên, cơ sở dữ liệu có thể trả các bản ghi cùng tên theo thứ tự không được xác định đầy đủ. Khi các bản ghi nằm ở ranh giới thứ 10, tập kết quả có thể thay đổi giữa các lần thực thi ngay cả khi ứng dụng không yêu cầu thay đổi thứ tự.

Thêm một thuộc tính duy nhất như `id` giúp xác định thứ tự đầy đủ trong tập dữ liệu đang xét. Điều đó không bảo đảm kết quả bất biến khi dữ liệu bị thêm, sửa hoặc xóa đồng thời; nó giải quyết trường hợp các khóa sắp xếp bằng nhau.

### Các lần gọi sortBy được nối thêm

Các thuộc tính sắp xếp được bổ sung vào cấu hình thứ tự đã có:

```java
List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName"))
                .sortBy(Sort.by("id"))
                .all());
```

Có thể đọc thứ tự là `fullName` trước, sau đó `id`. Không dùng một lần gọi `sortBy` mới với kỳ vọng nó luôn xóa toàn bộ thứ tự trước đó. Khi cần thứ tự rõ ràng, thường nên dựng một `Sort` hoàn chỉnh rồi truyền vào một lần.

Tên dùng trong `Sort` là thuộc tính miền như `fullName`, không phải tên cột SQL như `full_name`, cũng không mặc nhiên là tên thuộc tính trong một DTO đầu ra khác. Đường dẫn lồng nhau, cách so sánh chuỗi, vị trí của null và hỗ trợ các gợi ý sắp xếp cần được đối chiếu với store và mapping.

Nếu nhận yêu cầu sắp xếp từ giao diện, nên ánh xạ các lựa chọn được hỗ trợ sang thuộc tính miền đã xác định. Việc cho người dùng chọn sắp xếp không đồng nghĩa mọi chuỗi tên field đều là đường dẫn hợp lệ hoặc hợp lý về chi phí truy vấn.

## 4. limit: lấy một tập kết quả có kích thước tối đa

`limit` cấu hình số lượng kết quả tối đa cho thao tác lấy dữ liệu hỗ trợ giới hạn:

```java
List<Customer> topTen = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").and(Sort.by("id")))
                .limit(10)
                .all());
```

Kỳ vọng của ví dụ là:

```text
Lọc theo Example
-> sắp xếp theo fullName, id
-> lấy tối đa 10 bản ghi
-> trả về List<Customer>
```

Thứ tự logic này khác với việc đọc toàn bộ danh sách rồi mới gọi `subList`. Cấu hình fluent query cho phép store áp dụng giới hạn trong quá trình thực thi truy vấn phù hợp, thay vì buộc ứng dụng tải tất cả bản ghi chỉ để cắt lấy một đoạn.

### Giới hạn không đồng nghĩa với phân trang

`limit(10)` không tự tạo page number, offset, `totalElements` hoặc tổng số trang. Nó phù hợp với yêu cầu như danh sách gợi ý, những bản ghi đầu theo thứ tự đã chọn hoặc một màn hình chỉ cần tối đa N phần tử.

Nếu giao diện cần trang thứ ba và tổng số bản ghi khớp, cần một thao tác phân trang thích hợp. Không cộng dồn các lần gọi `limit` để tạo offset.

### Kiểm tra giới hạn từ đầu vào

Các ví dụ trong bài sử dụng số nguyên dương. Một tầng service có thể quy định phạm vi nghiệp vụ:

```java
static int validateLimit(int requestedLimit) {
    if (requestedLimit < 1 || requestedLimit > 100) {
        throw new IllegalArgumentException(
                "Giới hạn phải nằm trong khoảng 1 đến 100");
    }
    return requestedLimit;
}
```

Không dùng số âm. Cũng không dùng `0` như một cách mặc định để yêu cầu danh sách rỗng mà chưa kiểm tra hợp đồng API và store đang dùng. Nếu nghiệp vụ cần trả rỗng mà không truy vấn, tầng service có thể quyết định trực tiếp điều đó.

Nếu ứng dụng xác định giới hạn bằng nhiều nguồn cấu hình, nên tính ra một giá trị cuối cùng trước khi gọi `limit`, thay vì dựa vào việc gọi phương thức nhiều lần để giải thích quy tắc nghiệp vụ.

## 5. as: chọn kiểu biểu diễn kết quả

`as` thay đổi kiểu kết quả của fluent query. Ví dụ một interface projection cho thẻ khách hàng:

```java
public interface CustomerCard {
    Long getId();
    String getFullName();
    String getEmail();
}
```

Với store hỗ trợ loại projection này:

```java
List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.as(CustomerCard.class)
                .all());
```

Sau `as(CustomerCard.class)`, kiểu phần tử kết quả trong chuỗi là `CustomerCard`, nên `all()` trả danh sách tương ứng. Điều kiện tìm kiếm vẫn xuất phát từ `Example<Customer>`; không chuyển sang tìm một collection hoặc bảng có tên `CustomerCard`.

### as không phải phép ép kiểu Java

Không nên hiểu `as(CustomerCard.class)` là thực hiện `(CustomerCard) customer` trên một entity đã tải. Store và hạ tầng projection quyết định cách tạo kết quả theo kiểu được yêu cầu.

Tương tự, `as(String.class)` không mặc nhiên có nghĩa “chỉ lấy email”. Muốn một kiểu biểu diễn được hỗ trợ, cần định nghĩa projection hoặc DTO phù hợp và bảo đảm store có khả năng ánh xạ sang nó.

Kiểu DTO dựa trên constructor, record, interface projection và các projection lồng nhau không có cùng mức hỗ trợ trong mọi tổ hợp store và phiên bản. Việc Java chấp nhận một `Class<R>` ở thời điểm biên dịch chưa chứng minh kiểu đó có thể được ánh xạ khi truy vấn chạy.

Nếu dùng DTO hoặc record, cần kiểm tra tên tham số, constructor, kiểu dữ liệu và quy tắc ánh xạ mà store yêu cầu. Bài học sử dụng interface projection để minh họa ý định; không đưa ra một quy tắc tạo DTO chung cho mọi module.

## 6. project: chọn thuộc tính tham gia phép chiếu

`project` nhận tên thuộc tính hoặc đường dẫn thuộc tính cần dùng trong phép chiếu:

```java
List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.as(CustomerCard.class)
                .project("id", "fullName", "email")
                .all());
```

Có thể dùng dạng collection khi danh sách thuộc tính được dựng từ trước:

```java
List<String> fields = List.of("id", "fullName", "email");

List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.as(CustomerCard.class)
                .project(fields)
                .all());
```

Các chuỗi là đường dẫn trên mô hình miền. `project("email")` không khai báo một alias, một biểu thức SQL hoặc một phép tính tổng hợp.

### project không đổi generic result type

Xét ví dụ:

```java
List<Customer> customers = repository.findBy(
        example,
        q -> q.project("fullName", "email")
                .all());
```

Về kiểu khai báo của fluent query, kết quả vẫn là `Customer`, vì chưa gọi `as` sang kiểu khác. `project` không tự sinh lớp mới có đúng hai thuộc tính và cũng không chuyển kết quả thành `Map`.

Trong khi đó:

```java
List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.as(CustomerCard.class)
                .project("id", "fullName", "email")
                .all());
```

mới đồng thời biểu diễn hai ý định: dùng kiểu đầu ra `CustomerCard` và chọn các thuộc tính phù hợp với kiểu đó.

### Phép chiếu và lượng dữ liệu thực sự được đọc

Hỗ trợ phép chiếu và khả năng tối ưu truy vấn phụ thuộc store cùng loại projection. Không nên kết luận rằng thêm `project("email")` luôn tạo câu SQL chỉ có một cột hoặc một thao tác đọc tài liệu chỉ có đúng một field.

Store có thể cần thêm định danh, khóa sắp xếp hoặc dữ liệu phục vụ ánh xạ. Một kiểu projection phức tạp cũng có thể cần nhiều dữ liệu hơn một projection đơn giản. Cần xem truy vấn thực tế nếu mục tiêu là giảm lượng dữ liệu đọc và truyền.

Không đặt các thuộc tính bắt buộc của projection ra ngoài danh sách lựa chọn rồi dựa vào một giả định chung rằng getter sẽ trả null, tự được nạp bổ sung hoặc luôn gây lỗi. Cách ánh xạ cần được xác minh theo store. Trong ví dụ `CustomerCard`, danh sách lựa chọn bao gồm đầy đủ ba thuộc tính mà interface công bố.

Một kết quả có thể chỉ chứa một phần dữ liệu không phải nền tảng an toàn để gọi `save` và kỳ vọng cập nhật đầy đủ entity. Với màn hình chỉ đọc một phần thông tin, nên dùng một kiểu đầu ra phản ánh rõ nhu cầu đó và tách luồng cập nhật theo quy tắc ứng dụng.

## 7. So sánh as và project

| Khía cạnh | `as(CustomerCard.class)` | `project("id", "fullName", "email")` |
| --- | --- | --- |
| Trọng tâm | Kiểu biểu diễn đầu ra | Các thuộc tính trong phép chiếu |
| Thay đổi generic result type | Có, sang kiểu `CustomerCard` | Không |
| Định nghĩa điều kiện lọc mới | Không | Không |
| Định nghĩa thứ tự mới | Không | Không |
| Tự cung cấp phép chuyển đổi tùy ý | Không; cần khả năng ánh xạ được hỗ trợ | Không |
| Tự bảo đảm chỉ đọc đúng một tập cột/field | Không phải bảo đảm chung | Cần kiểm tra triển khai và truy vấn thực tế |

Hai phương thức bổ sung cho nhau. `as` trả lời câu hỏi ứng dụng nhận kiểu gì; `project` thể hiện các thuộc tính muốn đưa vào phép chiếu. Cả hai đều cần được hiểu cùng mapping và store.

Nếu mục tiêu là API chỉ công bố ba thuộc tính, kiểu response hoặc projection cần thể hiện đúng ba thuộc tính đó. Không dùng `project` trên một entity đầy đủ như cơ chế duy nhất để quyết định field nào được phép trả cho người dùng.

## 8. Kết hợp cả bốn phương thức

Yêu cầu thực tế:

> Tìm khách hàng đang hoạt động tại Huế, sắp xếp theo tên rồi id, lấy tối đa 10 người và trả các thẻ gồm id, tên, email.

Với `example` và `CustomerCard` đã định nghĩa:

```java
Sort order = Sort.by(
        Sort.Order.asc("fullName"),
        Sort.Order.asc("id"));

List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.sortBy(order)
                .limit(10)
                .as(CustomerCard.class)
                .project("id", "fullName", "email")
                .all());
```

Đọc cấu hình theo vai trò:

```text
Example<Customer>
    Điều kiện: city = Huế AND active = true

sortBy(order)
    Thứ tự: fullName tăng, id tăng

limit(10)
    Tối đa 10 kết quả cho thao tác lấy danh sách

as(CustomerCard.class)
    Kiểu phần tử đầu ra: CustomerCard

project(id, fullName, email)
    Các thuộc tính yêu cầu trong phép chiếu

all()
    Thực thi lấy danh sách theo cấu hình
```

Không có lời gọi nào trong bốn lời gọi cấu hình thêm một predicate mới vào `Example`. Ví dụ, chọn `email` trong `project` không làm loại các khách hàng có email null. Nếu nghiệp vụ yêu cầu email phải có giá trị, cần cơ chế lọc thích hợp; không gán ý nghĩa đó cho phép chiếu.

Thứ tự các phương thức trong chuỗi không phải thứ tự các vòng lặp Java trên một danh sách đã tải. Đây là quá trình tích lũy cấu hình cho store thực thi khi gặp phương thức kết thúc. Việc sắp xếp cần áp dụng trên tập bản ghi khớp trước khi chọn tập đầu theo giới hạn.

## 9. Dùng giá trị trả về của các phương thức cấu hình

Các phương thức fluent trả về đối tượng cấu hình kết quả. Cần tiếp tục chuỗi hoặc gán lại giá trị; không dựa vào tác dụng sửa đổi tại chỗ.

Ví dụ dễ sai:

```java
List<Customer> customers = repository.findBy(example, q -> {
    q.sortBy(Sort.by("fullName"));
    q.limit(10);
    return q.all();
});
```

Hai giá trị trả về bị bỏ đi. Không được kỳ vọng `q.all()` ở cuối sử dụng các cấu hình vừa gọi.

Cách viết rõ ràng:

```java
List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").and(Sort.by("id")))
                .limit(10)
                .all());
```

Nếu cần chia bước, giữ cấu hình trả về trong biến cục bộ và thực thi trong callback. Không trả đối tượng fluent query ra khỏi callback để thực thi sau. `findBy` yêu cầu hàm truy vấn trả về kết quả của thao tác; nó không phải một factory phát ra query builder độc lập để lưu và dùng ở nơi khác.

Khi `as` thay đổi kiểu kết quả, tiếp tục dùng đối tượng fluent query có kiểu mới. Không giữ biến kiểu cũ rồi kỳ vọng compiler tự thay đổi kiểu phần tử của biến đó.

## 10. Chọn phương thức kết thúc phù hợp

Bốn phương thức cấu hình cần được đọc cùng thao tác kết thúc:

| Nhu cầu | Thao tác thường dùng | Điểm cần chú ý |
| --- | --- | --- |
| Lấy danh sách tối đa N phần tử | `limit(N).all()` | Cần store hỗ trợ giới hạn; nên xác định thứ tự |
| Lấy phần tử đầu theo thứ tự | `sortBy(...).first()` | Phần tử đầu không phải lời khẳng định điều kiện là duy nhất |
| Yêu cầu tối đa một kết quả khớp | `one()` | Nhiều kết quả là lỗi về kích thước kết quả theo hợp đồng thao tác |
| Lấy một trang có metadata | `page(Pageable)` | Dùng cấu hình phân trang thích hợp |
| Đếm số bản ghi khớp | `count()` | Không suy ra từ kích thước một danh sách top N |
| Kiểm tra có kết quả | `exists()` | Không cần lấy danh sách chỉ để kiểm tra rỗng |

Nếu nghiệp vụ cần xác minh email là duy nhất, không dùng `limit(1).all()` rồi diễn giải “đã lấy được một người” thành “chỉ có một người khớp”. Giới hạn số phần tử trả về và tính duy nhất của tập bản ghi là hai câu hỏi khác nhau. Ràng buộc duy nhất quan trọng ở tầng dữ liệu cũng cần được thiết kế bằng cơ chế phù hợp của store.

Tương tự, khi cần người đứng đầu theo một thứ tự, nên diễn đạt bằng `first()` và một thứ tự rõ ràng. Không chọn `one()` nếu nhiều bản ghi khớp là tình huống hợp lệ.

### Đếm tổng và đếm số phần tử đã lấy

```java
List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").and(Sort.by("id")))
                .limit(10)
                .as(CustomerCard.class)
                .project("id", "fullName", "email")
                .all());

long totalMatches = repository.findBy(example, q -> q.count());
int returnedCount = cards.size();
```

`returnedCount` là kích thước danh sách đã lấy, còn `totalMatches` được lấy bằng một thao tác đếm riêng trên điều kiện không gắn giới hạn trong callback. Không dùng một chuỗi `limit(...).count()` với giả định rằng mọi store đều đếm đúng N phần tử giống `all()`.

Hai lời gọi repository là hai thao tác riêng. Nếu dữ liệu thay đổi giữa chúng, tổng đếm và danh sách có thể phản ánh các thời điểm khác nhau. Mức nhất quán cần được thiết kế theo transaction và kho dữ liệu, không được bảo đảm bởi cú pháp fluent.

## 11. Khi cần page, đặt cấu hình phân trang rõ ràng

Nếu yêu cầu là một trang 10 khách hàng cùng thông tin tổng số phần tử, có thể dùng:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

Page<CustomerCard> page = repository.findBy(
        example,
        q -> q.as(CustomerCard.class)
                .project("id", "fullName", "email")
                .page(PageRequest.of(
                        0,
                        10,
                        Sort.by("fullName").and(Sort.by("id")))));
```

Ở đây số trang, kích thước và thứ tự được thể hiện trong `PageRequest`. Ví dụ không chồng thêm một `limit` riêng hoặc một thứ tự khác trên fluent query.

Không mặc định `limit(5).page(pageableSize20)` có một quy tắc kết hợp portable trên mọi phiên bản và store. `page(...)` có hợp đồng riêng về offset, kích thước trang, thứ tự và metadata; cần kiểm tra triển khai nếu buộc phải phối hợp các cấu hình chồng chéo.

Cũng không đọc một page entity rồi lọc thêm bằng Java mà vẫn giữ nguyên `totalElements`. Khi có thêm điều kiện nghiệp vụ, đưa điều kiện đó vào truy vấn phù hợp để metadata được tính trên tập kết quả đúng.

## 12. Đường dẫn, phép chiếu và khả năng của store

Trong ứng dụng thực tế, cần kiểm tra các điểm sau theo đúng store đang dùng:

| Vấn đề | Điều cần xác nhận |
| --- | --- |
| `sortBy` trên thuộc tính thường | Tên đường dẫn hợp lệ và thứ tự thực tế |
| `sortBy` trên quan hệ hoặc thuộc tính lồng nhau | Khả năng duyệt đường dẫn, join, null và chi phí |
| `limit` | API tồn tại trong dependency và thao tác kết thúc có hỗ trợ |
| Interface projection | Quy tắc ánh xạ getter, thuộc tính và kiểu trả về |
| DTO hoặc record qua `as` | Khả năng hỗ trợ kiểu kết quả và constructor |
| `project` với đường dẫn lồng nhau | Cấu trúc dữ liệu được chọn và dữ liệu phụ store cần đọc |
| Sắp xếp theo field không công bố ở đầu ra | Store có thể cần field đó để thực thi hoặc ánh xạ |
| Projection kết hợp metadata | Định danh, version hoặc thuộc tính kỹ thuật có cần thiết không |

Ví dụ một kiểu đầu ra chỉ công bố tên và email vẫn có thể cần sắp xếp theo id ở tầng truy vấn. Điều đó không đồng nghĩa id phải được công bố trong response, và cũng không chứng minh rằng store không cần đọc id.

Với mô hình quan hệ, phép chiếu không tự chỉ định fetch join hay chiến lược nạp association. Với mô hình tài liệu, một đường dẫn nhúng trong cùng tài liệu khác với tham chiếu tới tài liệu khác. Các cấu hình Commons phải được đối chiếu với cách dữ liệu thực sự được lưu.

Nếu mục tiêu là tối ưu, cần quan sát truy vấn được sinh, số bản ghi đọc, lượng dữ liệu truyền và chỉ mục phù hợp với điều kiện cùng thứ tự. Không kết luận hiệu năng chỉ từ độ ngắn của chuỗi phương thức.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Đã gọi sortBy nhưng kết quả không theo thứ tự mong đợi | Bỏ giá trị trả về hoặc khóa sắp xếp chưa phân định hết | Dùng chuỗi cấu hình và thêm khóa phân định |
| Danh sách top N thay đổi ở các bản ghi trùng tên | Chỉ sắp xếp theo một thuộc tính không duy nhất | Thêm id hoặc khóa duy nhất phù hợp |
| Lấy tối đa 10 nhưng giao diện cần trang thứ ba | Nhầm limit với phân trang | Dùng API page và Pageable phù hợp |
| project hai field nhưng kiểu kết quả vẫn là Customer | project không đổi generic result type | Chọn projection bằng as nếu cần kiểu đầu ra khác |
| Gọi as một DTO bất kỳ rồi lỗi lúc chạy | Store không ánh xạ được kiểu hoặc constructor đó | Dùng kiểu được hỗ trợ và cấu hình ánh xạ hợp lệ |
| Getter projection không có dữ liệu như dự kiến | Danh sách project thiếu thuộc tính hoặc mapping không phù hợp | Đồng bộ kiểu đầu ra với danh sách thuộc tính |
| Dùng tên cột trong sort hoặc project | Nhầm tên lưu trữ với tên thuộc tính miền | Dùng đường dẫn miền theo hợp đồng API |
| Gọi limit nhưng store báo không hỗ trợ | Tổ hợp dependency, store và thao tác chưa hỗ trợ | Chọn API giới hạn hoặc phân trang được triển khai |
| Lấy một bản ghi rồi cho rằng dữ liệu là duy nhất | Giới hạn đã che các bản ghi khớp khác | Phân biệt yêu cầu first với kiểm tra duy nhất |
| Dùng project như cơ chế kiểm soát toàn bộ response | Kiểu entity và lớp serialize vẫn có thể công bố thuộc tính khác | Thiết kế kiểu response và quyền truy cập rõ ràng |

## 14. Tự diễn giải một chuỗi fluent query

Với một chuỗi như sau:

```java
List<CustomerCard> cards = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").and(Sort.by("id")))
                .limit(10)
                .as(CustomerCard.class)
                .project("id", "fullName", "email")
                .all());
```

Cần trả lời được năm câu hỏi:

1. `example` đang lọc theo những thuộc tính nào và có điều kiện ngoài ý muốn từ metadata hay giá trị mặc định không?
2. Thứ tự có phân định các bản ghi trùng khóa và có được store hỗ trợ không?
3. Số 10 là giới hạn danh sách hay một yêu cầu phân trang có metadata?
4. `CustomerCard` có phải kiểu kết quả mà store ánh xạ được không?
5. Danh sách project có phù hợp với kiểu đầu ra, và truy vấn thực tế có đạt mục tiêu đọc dữ liệu không?

Khi các câu trả lời đã rõ, chuỗi fluent query trở thành một mô tả có thể kiểm tra: điều kiện tìm kiếm, thứ tự, quy mô kết quả và hình dạng đầu ra. Giữ riêng từng vai trò này giúp mở rộng repository mà không gán cho `sortBy`, `limit`, `as` hoặc `project` những khả năng vượt quá hợp đồng của chúng.
