# Thứ tự ưu tiên và xử lý phương thức trùng chữ ký

Khi một repository ghép nhiều fragment, hai fragment có thể cùng khai báo một phương thức. Một fragment cũng có thể khai báo phương thức trùng với API có sẵn như `save(...)`. Lúc đó cần trả lời hai câu hỏi riêng: Java có cho phép interface repository kế thừa các khai báo ấy không, và nếu có thì Spring Data sẽ gọi implementation nào?

Bài học này thuộc chương **Repository fragment** của **Spring Data Commons**. Trọng tâm là cơ chế ghép repository và giải quyết phương thức trùng nhau. API lưu trữ, giao dịch và hành vi truy vấn cụ thể vẫn phụ thuộc module đang dùng, chẳng hạn Spring Data JPA hoặc Spring Data MongoDB.

Sau bài học, bạn có thể dự đoán fragment nào được gọi, phân biệt xung đột biên dịch với xung đột lựa chọn implementation, và thiết kế repository sao cho thay đổi thứ tự interface không vô tình đổi hành vi nghiệp vụ.

## 1. Repository là một tập hợp các phần thực thi

Một repository Spring Data có thể kết hợp:

- **Implementation nền** do module lưu trữ cung cấp, đảm nhận những thao tác repository cơ bản được module đó hỗ trợ.
- **Các phần mở rộng do hạ tầng cung cấp**, thường được tài liệu gọi là repository aspects; một ví dụ là khả năng Querydsl khi module và cấu hình hỗ trợ.
- **Custom fragment** do ứng dụng định nghĩa, gồm interface mô tả hợp đồng và implementation thực thi hợp đồng đó.

Ví dụ, một interface có thể ghép nhiều fragment như sau:

```java
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                AdministrativeLabel,
                CustomerLabel {
}
```

Đây không phải một lớp Java kế thừa trực tiếp từ ba lớp implementation. Spring Data xây dựng repository proxy và ghép các thành phần thực thi phía sau proxy đó.

Với những phương thức thuộc cơ chế ghép fragment, thứ tự ghép có ý nghĩa. Không nên coi danh sách interface trong `extends` chỉ là cách trình bày mã nguồn.

## 2. Quy tắc ưu tiên cần nhớ

Với custom fragment được khai báo hợp lệ và có implementation được Spring Data tìm thấy:

1. Các custom fragment được đưa vào composition theo thứ tự khai báo ở repository.
2. Nếu nhiều custom fragment cùng cung cấp một phương thức phù hợp, fragment đứng trước được ưu tiên.
3. Custom fragment có độ ưu tiên cao hơn implementation nền và các repository aspects. Nhờ vậy, một fragment có thể thay thế một phương thức có sẵn như `save(...)`.

| Tình huống | Kết quả cần dự đoán |
| --- | --- |
| Chỉ một custom fragment cung cấp phương thức | Phương thức được chuyển đến fragment đó |
| Hai custom fragment cùng cung cấp phương thức | Fragment xuất hiện trước trong thứ tự khai báo được ưu tiên |
| Custom fragment trùng phương thức với implementation nền | Custom fragment được ưu tiên |
| Custom fragment trùng phương thức với một repository aspect | Custom fragment được ưu tiên |
| Hai khai báo không tương thích theo luật Java | Không tạo được interface hợp lệ để Spring Data xử lý |

Bảng trên không đặt ra một thứ tự chung giữa mọi loại thành phần hạ tầng. Điều quan trọng trong bài này là ưu tiên của custom fragment và thứ tự giữa các custom fragment.

Các quy tắc này cũng không có nghĩa rằng mọi lời gọi qua proxy đều đi vào cùng một bộ chọn. Ví dụ, default method trên interface có cơ chế thực thi riêng. Những ví dụ về ưu tiên fragment dưới đây sử dụng các khai báo phương thức trừu tượng có implementation trong fragment.

## 3. Phân biệt hai tầng xung đột

### 3.1. Tầng Java: khai báo có hợp lệ không?

Ở mức Java, chữ ký phương thức liên quan đến tên và kiểu tham số, cùng các quy tắc áp dụng cho phương thức generic. Chỉ đổi kiểu trả về không tạo ra một overload mới.

Ví dụ không hợp lệ:

```java
interface TextLookup {
    String lookup(Long id);
}

interface NumericLookup {
    Integer lookup(Long id);
}

// Không biên dịch: cùng lookup(Long) nhưng kiểu trả về không tương thích.
interface BrokenRepository extends TextLookup, NumericLookup {
}
```

Đưa `TextLookup` lên trước không làm ví dụ này hợp lệ. Quy tắc ưu tiên fragment chỉ có thể áp dụng sau khi mã Java đã đáp ứng các quy tắc kế thừa.

Ngược lại, hai interface cùng khai báo `String labelFor(Long id)` có thể được kế thừa cùng nhau. Java nhìn thấy các hợp đồng tương thích; Spring Data mới là nơi cần chọn implementation để thực hiện hợp đồng ấy.

Các điểm cần phân biệt:

- **Kiểu trả về hiệp biến:** một kiểu trả về có thể chuyên biệt hóa kiểu kia nếu thỏa luật Java, nhưng không vì thế mà trở thành overload.
- **Generic và type erasure:** `accept(List<String>)` và `accept(List<Long>)` không phải cách tạo hai overload hợp lệ vì cùng bị xóa kiểu thành `accept(List)`.
- **Default method:** kế thừa hai default method không có quan hệ ưu tiên hợp lệ theo luật Java có thể buộc interface con khai báo cách giải quyết. Không dùng thứ tự fragment để chữa lỗi đó.
- **Tên tham số:** đổi `id` thành `productId` không thay đổi chữ ký.

### 3.2. Tầng Spring Data: implementation nào được gọi?

Giả sử cả hai fragment đều khai báo:

```java
String labelFor(Long id);
```

Nếu repository kế thừa hai fragment này và Spring Data đã nhận diện được cả hai implementation, lời gọi `repository.labelFor(7L)` phải được chuyển đến một implementation. Lúc này thứ tự khai báo fragment là thông tin quyết định.

Không nên suy luận rằng Spring Data sẽ chọn implementation dựa trên tên bean có thứ tự chữ cái, tên lớp nghe phù hợp hơn, hoặc giá trị `id` được truyền vào.

## 4. Ví dụ: hai fragment cùng cung cấp nhãn sản phẩm

Giả sử ứng dụng đã có entity `Product` và cấu hình repository phù hợp với kho dữ liệu. Ví dụ chỉ tập trung vào những kiểu liên quan đến composition. Mỗi public type được đặt trong một tệp Java riêng; các kiểu nằm trong package phù hợp để cơ chế dò tìm fragment nhận diện được chúng.

### 4.1. Khai báo hai hợp đồng tương thích

```java
public interface AdministrativeLabel {
    String labelFor(Long id);
}
```

```java
public interface CustomerLabel {
    String labelFor(Long id);
}
```

Hai hợp đồng có cùng chữ ký và cùng kiểu trả về, nên có thể cùng xuất hiện trên một repository.

### 4.2. Tạo implementation cho từng fragment

```java
public class AdministrativeLabelImpl implements AdministrativeLabel {

    @Override
    public String labelFor(Long id) {
        return "admin:" + id;
    }
}
```

```java
public class CustomerLabelImpl implements CustomerLabel {

    @Override
    public String labelFor(Long id) {
        return "customer:" + id;
    }
}
```

Các tên lớp dùng hậu tố `Impl`, là quy ước mặc định để tìm implementation của fragment. Nếu ứng dụng đổi hậu tố hoặc tự đăng ký implementation, cần tuân theo cấu hình thực tế của ứng dụng đó.

### 4.3. Đặt fragment quản trị trước

```java
import org.springframework.data.repository.Repository;

public interface ProductRepository
        extends Repository<Product, Long>,
                AdministrativeLabel,
                CustomerLabel {
}
```

Khi composition đã được thiết lập đúng:

```java
String label = productRepository.labelFor(7L);
// label là "admin:7"
```

Ở đây dùng `Repository` làm marker vì ví dụ không cần CRUD. Việc repository có hai fragment không làm phát sinh hai phương thức để người gọi lựa chọn: ở phía người gọi vẫn chỉ có một `labelFor(Long)`.

### 4.4. Đổi thứ tự fragment

Nếu sửa chính repository trên thành:

```java
public interface ProductRepository
        extends Repository<Product, Long>,
                CustomerLabel,
                AdministrativeLabel {
}
```

thì lời gọi tương tự được chuyển đến `CustomerLabelImpl`, cho kết quả `"customer:7"`.

Đây là một thay đổi hành vi dù tên phương thức, tham số và kiểu trả về đều giữ nguyên. Vì vậy, sắp xếp lại các interface trong `extends` có thể là thay đổi nghiệp vụ và cần được review tương ứng.

### 4.5. Ép kiểu không tạo một đường gọi khác

Với repository có `AdministrativeLabel` đứng trước, không nên viết:

```java
CustomerLabel labels = productRepository;
String label = labels.labelFor(7L);
```

rồi kỳ vọng chắc chắn nhận `"customer:7"`. Việc ép kiểu hoặc gán sang một superinterface không phải cơ chế chọn implementation cho những phương thức trùng chữ ký trong composition. Đối tượng vẫn là cùng repository proxy và lời gọi vẫn chịu cơ chế phân giải phương thức của proxy.

Nếu ứng dụng cần gọi được cả hai hành vi, hãy thiết kế hai phương thức có tên khác nhau hoặc hai collaborator riêng.

## 5. Ưu tiên không phải chuỗi fallback

Giả sử fragment đứng trước kiểm tra dữ liệu và ném ngoại lệ:

```java
@Override
public String labelFor(Long id) {
    if (id == null) {
        throw new IllegalArgumentException("id must not be null");
    }
    return "admin:" + id;
}
```

Spring Data không vì ngoại lệ này mà tự gọi `CustomerLabelImpl.labelFor(...)`. Tương tự, trả về `null` không có nghĩa là chuyển quyền xử lý cho fragment tiếp theo.

Thứ tự composition dùng để chọn implementation. Nó không tự mang những ý nghĩa sau:

- Gọi tất cả fragment rồi ghép kết quả.
- Thử fragment đầu, thất bại thì thử fragment sau.
- Bọc fragment sau bằng logic của fragment trước.
- Chọn fragment theo quyền người dùng hoặc dữ liệu đầu vào.

Nếu nghiệp vụ cần chuỗi xử lý, hãy viết chuỗi đó một cách tường minh trong một service hoặc một fragment điều phối. Ví dụ, service kiểm tra quyền truy cập rồi gọi collaborator quản trị hay khách hàng tương ứng. Như vậy, điều kiện lựa chọn có thể đọc, kiểm thử và thay đổi độc lập với thứ tự interface.

## 6. Ghi đè phương thức CRUD bằng fragment

Một ứng dụng có thể muốn kiểm tra điều kiện trước khi lưu entity. Spring Data hỗ trợ dùng custom fragment để thay thế phương thức nền tương ứng.

Hợp đồng generic thường dùng cho `save` là:

```java
public interface CustomizedSave<T> {
    <S extends T> S save(S entity);
}
```

Repository ghép hợp đồng này với CRUD:

```java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>,
                CustomizedSave<Product> {
}
```

Dù `CrudRepository` được viết trước trong danh sách, custom fragment vẫn có độ ưu tiên cao hơn implementation nền. Không áp dụng quy tắc “interface nào đứng trước thắng” một cách máy móc cho toàn bộ danh sách; quy tắc thứ tự ở phần trước nói về các custom fragment cạnh tranh với nhau.

Giữ khai báo `<S extends T> S save(S entity)` giúp hợp đồng của fragment phù hợp với API generic của CRUD. Không nên tùy tiện thay bằng `Object save(Object entity)` hoặc một khai báo gây xung đột sau type erasure.

### 6.1. Cần một đường ghi dữ liệu thực sự

Fragment thay thế `save` phải thực hiện đầy đủ công việc mà hợp đồng của nó yêu cầu. Nó không tự động gọi tiếp phương thức nền sau khi chạy xong.

Một cách mô tả ranh giới phụ thuộc là dùng collaborator riêng:

```java
public interface EntityWriter<T> {
    <S extends T> S persist(S entity);
}
```

```java
import java.util.Objects;

public class CustomizedSaveImpl<T> implements CustomizedSave<T> {

    private final EntityWriter<T> writer;

    public CustomizedSaveImpl(EntityWriter<T> writer) {
        this.writer = writer;
    }

    @Override
    public <S extends T> S save(S entity) {
        Objects.requireNonNull(entity, "entity must not be null");
        return writer.persist(entity);
    }
}
```

`EntityWriter` ở đây là abstraction minh họa do ứng dụng tự định nghĩa, không phải API có sẵn của Spring Data Commons. Ứng dụng phải cung cấp bean phù hợp và implementation ghi dữ liệu theo đúng kho đang dùng. Nếu có nhiều writer, cấu hình dependency injection phải xác định rõ writer dành cho fragment; chỉ chép các interface trên chưa tạo ra đường lưu dữ liệu.

Implementation thực tế phải xem xét các quy tắc của module lưu trữ: cách xác định entity mới, insert hay update, giá trị trả về, giao dịch, callback và auditing. Không thể suy ra những quy tắc ấy chỉ từ cơ chế ưu tiên của Commons.

### 6.2. Không gọi lại chính repository để “đi xuống lớp nền”

Một thiết kế nguy hiểm là inject `ProductRepository` vào `CustomizedSaveImpl` rồi gọi:

```java
// Không phải cách gọi implementation nền:
return productRepository.save(entity);
```

Lời gọi quay lại cùng repository proxy có thể lại được chuyển đến chính fragment đang xử lý `save`, gây đệ quy. Tùy cách wiring, việc inject ngược repository còn có thể tạo vòng phụ thuộc khi khởi tạo bean.

Nếu cần mở rộng implementation nền cho nhiều repository, hãy xem cơ chế tùy chỉnh base repository của module lưu trữ, chẳng hạn cấu hình `repositoryBaseClass` ở những module hỗ trợ. Nếu cần một thao tác riêng, dùng collaborator hoặc API lưu trữ cụ thể trong fragment. Cả hai hướng đều cần đường delegate rõ ràng; thứ tự fragment không cung cấp lệnh “gọi implementation kế tiếp”.

### 6.3. Ghi đè một phương thức không bao phủ mọi thao tác ghi

Thay thế `save(...)` không đồng nghĩa mọi phương thức ghi khác đều sẽ đi qua phần kiểm tra đó. Chẳng hạn, không được mặc định rằng `saveAll(...)` của implementation nền sẽ gọi ngược qua proxy để đến custom `save(...)`.

Nếu quy tắc phải áp dụng cho mọi đường ghi, hãy liệt kê các API cần bao phủ và chọn tầng triển khai phù hợp. Với auditing hoặc callback của entity, cần xem khả năng thực tế của module lưu trữ và cấu hình tương ứng.

## 7. Tìm implementation và chọn phương thức là hai việc khác nhau

Có hai nhóm vấn đề dễ bị nhầm:

| Nhóm vấn đề | Ví dụ | Cách xử lý phù hợp |
| --- | --- | --- |
| Dò tìm hoặc đăng ký implementation | Fragment không được nhận diện do sai tên hoặc sai phạm vi dò tìm | Kiểm tra quy ước hậu tố, package và cấu hình repository |
| Nhiều ứng viên cho cùng một fragment | Có nhiều lớp hoặc bean implementation có thể được chọn khi khởi tạo | Làm rõ tên bean hoặc đăng ký implementation theo cấu hình hỗ trợ |
| Nhiều fragment đã được ghép cùng cung cấp một phương thức | Hai fragment đều có `labelFor(Long)` | Kiểm tra thứ tự khai báo hoặc thiết kế lại API |
| Khai báo Java không tương thích | Cùng chữ ký nhưng kiểu trả về không tương thích | Sửa hợp đồng phương thức để mã biên dịch được |

Không dùng `@Primary` hoặc `@Order` như cơ chế thay đổi thứ tự phân giải phương thức giữa các fragment đã được ghép. Những annotation đó có vai trò trong những ngữ cảnh Spring khác; chúng không thay thế quy tắc composition đang xét.

Tương tự, đổi tên lớp implementation thành `AFirstImpl` không tự đưa nó lên đầu composition. Tên implementation chủ yếu liên quan đến việc tìm và đăng ký fragment, còn thứ tự các fragment đã nhận diện gắn với khai báo repository.

Không gắn `@Query` chỉ để chọn giữa hai custom fragment trùng phương thức. Hãy làm rõ hợp đồng fragment và cách ghép trước; khả năng truy vấn có annotation lại phụ thuộc module lưu trữ và đường thực thi truy vấn tương ứng.

## 8. Thiết kế để giảm phụ thuộc vào thứ tự

### 8.1. Hai ý nghĩa nghiệp vụ khác nhau: dùng hai tên

Nếu cả nhãn quản trị và nhãn khách hàng đều cần được sử dụng, thiết kế hợp đồng rõ ràng hơn:

```java
public interface AdministrativeLabel {
    String administrativeLabelFor(Long id);
}

public interface CustomerLabel {
    String customerLabelFor(Long id);
}
```

Người gọi chọn trực tiếp ý nghĩa cần dùng:

```java
String internal = productRepository.administrativeLabelFor(7L);
String external = productRepository.customerLabelFor(7L);
```

Repository lúc này thể hiện hai khả năng riêng. Việc sắp xếp lại hai interface không đổi cách chọn giữa chúng vì chúng không cạnh tranh cùng một phương thức nữa.

### 8.2. Cùng một hợp đồng, nhiều chiến lược: ghép chiến lược cần dùng

Nếu hai implementation là hai cách thực hiện thay thế cho cùng một hợp đồng, mỗi repository nên nhận chiến lược mong muốn qua cấu hình hoặc composition rõ ràng. Không cần đưa mọi chiến lược vào cùng repository rồi dựa vào thứ tự để che các implementation còn lại.

Ví dụ, repository dành cho một ngữ cảnh chỉ ghép fragment nhãn khách hàng; repository cho ngữ cảnh quản trị dùng fragment còn lại. Cách chia cụ thể phụ thuộc kiến trúc ứng dụng, nhưng sự lựa chọn cần có chủ đích.

### 8.3. Cố ý thay thế phương thức nền: ghi rõ hợp đồng

Nếu việc trùng chữ ký là chủ đích, chẳng hạn thay thế `save`, hãy mô tả:

- Điều kiện đầu vào và ngoại lệ có thể ném.
- Đường ghi dữ liệu thực sự được sử dụng.
- Giá trị trả về và hành vi với entity mới hoặc đã tồn tại.
- Những phương thức liên quan được bao phủ, ví dụ có xử lý cả `saveAll` hay không.
- Giới hạn theo loại repository và module lưu trữ.

Việc này giúp người bảo trì phân biệt một customization có chủ ý với hai fragment vô tình dùng cùng tên.

## 9. Kiểm chứng ở đúng mức repository proxy

Một unit test tạo trực tiếp `new AdministrativeLabelImpl()` chỉ xác nhận logic của lớp đó. Nó không xác nhận Spring Data đã tìm thấy fragment, ghép đúng thứ tự và dispatch lời gọi như mong muốn.

Với ví dụ `AdministrativeLabel` đứng trước, cần một kiểm thử có repository proxy thật trong cấu hình phù hợp. Đoạn sau minh họa điều cần xác nhận trong một dự án Spring Boot đã cấu hình domain và kho dữ liệu:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class ProductRepositoryCompositionTest {

    @Autowired
    ProductRepository repository;

    @Test
    void usesAdministrativeFragmentForDuplicateMethod() {
        assertEquals("admin:7", repository.labelFor(7L));
    }
}
```

Đây là ví dụ kiểm thử composition trong môi trường ứng dụng, không phải kiểm thử độc lập chỉ cần Spring Data Commons. Dự án phải có dependency và cấu hình của module lưu trữ thực tế. Có thể dùng test slice tương ứng thay cho `@SpringBootTest` nếu slice đó nạp đúng repository và các fragment cần kiểm tra.

Khi kiểm chứng một trường hợp trùng chữ ký, nên xác nhận các hành vi có ý nghĩa:

1. Repository được khởi tạo thành công và fragment được nhận diện.
2. Lời gọi qua repository proxy đến fragment được ưu tiên.
3. Fragment đứng sau không bị gọi như một fallback ngầm.
4. Nếu cố ý đổi thứ tự, kỳ vọng hành vi được cập nhật tương ứng.
5. Nếu override CRUD, thao tác dữ liệu và hợp đồng trả về vẫn đúng với module đang dùng.

Không cần kiểm thử thứ tự bằng cách quan sát tên bean hay thứ tự log khởi tạo. Những dấu hiệu đó không chứng minh được implementation nào xử lý lời gọi qua proxy.

## 10. Cách chẩn đoán khi kết quả khác kỳ vọng

Đi từ lỗi gần nhất với hợp đồng, thay vì đổi thứ tự interface liên tục:

1. **Mã có biên dịch không?** Nếu lỗi ở kiểu trả về, generic hoặc default method, giải quyết luật Java trước.
2. **Repository có khởi tạo được không?** Nếu không, kiểm tra fragment implementation, quy ước tên và dependency injection. Không giả định Spring Data đã nhận diện một phương thức là custom chỉ vì interface có khai báo nó.
3. **Các phương thức có thực sự cùng hợp đồng không?** So sánh tên, kiểu tham số, generic và tính tương thích của kiểu trả về. `labelFor(Long)` và `labelFor(String)` là hai overload khác nhau.
4. **Những custom fragment nào cùng cung cấp phương thức?** Đọc thứ tự khai báo tại repository, kể cả khi repository kế thừa qua các interface trung gian. Với cấu trúc trung gian phức tạp, làm phẳng trường hợp tối thiểu để kiểm chứng thay vì suy luận theo tên lớp.
5. **Có đang nhầm override với delegate không?** Fragment được ưu tiên không tự gọi implementation nền hay fragment tiếp theo.
6. **Lời gọi có đi qua proxy không?** Gọi trực tiếp implementation hoặc gọi nội bộ trong một đối tượng có thể không đi qua đường dispatch đang kiểm tra.
7. **Kỳ vọng có thuộc khả năng của module lưu trữ không?** Commons cung cấp abstraction và composition; không biến mọi store thành JPA hay làm đồng nhất mọi hành vi lưu dữ liệu.

Ví dụ, nếu dự kiến nhận `"customer:7"` nhưng lại nhận `"admin:7"`, trước hết xem `AdministrativeLabel` có đứng trước `CustomerLabel` không. Nếu dự kiến có hai nhãn khác nhau tùy superinterface được ép kiểu, vấn đề nằm ở thiết kế hợp đồng: cần hai tên phương thức hoặc hai collaborator riêng.

## 11. Bài tập tự thực hành

Dùng một ứng dụng Spring Data đã cấu hình kho dữ liệu, tạo hai fragment có cùng phương thức `String labelFor(Long id)` như ví dụ:

1. Đặt fragment quản trị trước và xác nhận kết quả `"admin:7"` qua repository proxy.
2. Đổi thứ tự để fragment khách hàng đứng trước và xác nhận kết quả `"customer:7"`.
3. Cho fragment đứng trước ném ngoại lệ khi `id` là `null`; quan sát rằng fragment sau không tự tiếp quản.
4. Đổi hai hợp đồng thành `administrativeLabelFor` và `customerLabelFor`; xác nhận người gọi có thể chọn cả hai hành vi một cách tường minh.
5. Nếu thử override `save`, xác định rõ đường ghi dữ liệu và kiểm tra riêng `saveAll`; không suy luận rằng một customization đã bao phủ mọi API ghi.

Kết quả cần đạt là giải thích được cả ba lớp quyết định: **Java cho phép hợp đồng nào**, **Spring Data chọn fragment nào**, và **implementation được chọn thực hiện thao tác dữ liệu bằng cách nào**. Nắm rõ ba lớp này giúp dùng repository fragment có chủ đích và tránh để thứ tự interface trở thành một quy tắc nghiệp vụ vô tình.
