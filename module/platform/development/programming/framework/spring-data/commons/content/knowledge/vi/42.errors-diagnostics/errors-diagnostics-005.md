# PropertyReferenceException và tên phương thức bị phân tích sai

## 1. Lỗi này cho biết điều gì?

Trong chương **Lỗi và chẩn đoán** của **SPRING_DATA_COMMONS**, PropertyReferenceException thường xuất hiện khi hạ tầng phân giải một đường dẫn property nhưng không tìm thấy một thành phần trên kiểu domain đang xét.

Với derived query, tên phương thức repository là một phần của hợp đồng truy vấn. Một identifier hợp lệ trong Java chưa chắc là một tên truy vấn hợp lệ đối với Spring Data.

Ví dụ:

~~~java
List<Customer> findByEmailAdress(String email);
~~~

Nếu domain chỉ có property emailAddress, phần EmailAdress bị viết thiếu một chữ d. Code vẫn có thể biên dịch, nhưng khi hạ tầng tạo query từ tên phương thức, việc phân giải property sẽ thất bại.

Thông báo có thể có dạng minh họa:

~~~text
No property 'emailAdress' found for type 'Customer'
~~~

Lỗi có thể được bọc trong QueryCreationException, lỗi tạo bean hoặc lỗi dependency. Cần đọc cả phương thức repository liên quan và chuỗi nguyên nhân, thay vì chỉ nhìn exception ở ngoài cùng.

Tuy nhiên, không phải mọi PropertyReferenceException đều bắt nguồn trực tiếp từ tên method. Property path trong Sort hoặc cơ chế truy vấn động cũng có thể là nguồn lỗi.

## 2. Tên method được xử lý theo nhiều bước

Có thể hình dung quá trình tạo derived query:

~~~text
Xác định repository và kiểu domain gốc
  → Nhận diện subject và predicate của tên method
    → Tách điều kiện, toán tử và sort tĩnh
      → Phân giải đường dẫn property
        → Tạo truy vấn theo module
          → Bind tham số và thực thi trên store
~~~

Commons cung cấp những thành phần phân tích dùng chung; module store thực hiện các phần tích hợp và tạo query cụ thể.

PropertyReferenceException thuộc nhóm lỗi phân giải property. Nó không tự chứng minh database mất kết nối hoặc thiếu index.

Cũng không được suy ra rằng phân tích property thành công thì query chắc chắn chạy được. Mapping, kiểu tham số, khả năng hỗ trợ toán tử và cấu trúc store vẫn có thể gây lỗi ở bước sau.

### Ví dụ tên hợp lệ

~~~java
List<Customer> findByEmailAddressAndActiveTrue(String emailAddress);
~~~

Có thể đọc ý định:

| Thành phần | Vai trò |
| --- | --- |
| find | Dạng tìm kiếm |
| By | Bắt đầu phần điều kiện |
| EmailAddress | Property emailAddress |
| And | Nối điều kiện |
| Active | Property active |
| True | Điều kiện boolean, không cần tham số cho active |

Khả năng hỗ trợ kiểu query và từ khóa cần được kiểm tra trong module cụ thể. Không coi mọi store hỗ trợ cùng một tập phép toán chỉ vì dùng chung tên repository abstraction.

## 3. Bắt đầu từ domain gốc thực sự

Xét:

~~~java
import org.springframework.data.repository.Repository;

public interface CustomerRepository
        extends Repository<Customer, Long> {

    List<CustomerView> findByEmailAddress(String emailAddress);
}
~~~

Đường dẫn emailAddress được phân giải theo domain Customer, không phải mặc định theo kiểu projection CustomerView.

Nếu repository vô tình được khai báo với domain khác, một method trông đúng đối với Customer vẫn có thể sai đối với kiểu thực tế.

Cần đối chiếu:

1. Generic domain của repository.
2. Kiểu ID.
3. Base interface mà repository kế thừa.
4. Kiểu domain được module nhận diện.
5. Property tồn tại và được mapping theo mô hình nào.

Đừng đổi tên method nhiều lần khi lỗi thực sự là repository đang trỏ đến nhầm domain.

### Property Java khác tên cột hoặc field lưu trữ

Ví dụ domain có:

~~~text
Java property: emailAddress
Tên cột: email_address
~~~

Derived query thông thường sử dụng property Java:

~~~java
List<Customer> findByEmailAddress(String emailAddress);
~~~

Không đổi thành Email_address chỉ vì database dùng snake_case. Dấu gạch dưới còn có vai trò đặc biệt trong đường dẫn property, nên có thể tạo ra cách phân tích khác.

Điều tương tự áp dụng cho field được đổi tên bằng mapping annotation trong document store. Derived property path và tên lưu trữ vật lý thuộc hai tầng khác nhau.

Với query khai báo tường minh, quy tắc đặt tên còn phụ thuộc ngôn ngữ query: query trên entity có thể dùng property domain, còn native query có thể dùng tên vật lý. Không trộn các quy tắc đó với query derivation.

## 4. Camel case có thể khiến một đường dẫn bị hiểu khác ý định

Giả sử domain có cấu trúc:

~~~java
class Customer {
    String emailAddress;
    Address address;
    String addressZip;
}

class Address {
    String zipCode;
}
~~~

Ý định là tìm theo address.zipCode:

~~~java
List<Customer> findByAddressZipCode(String zipCode);
~~~

Người đọc có thể hiểu Address + ZipCode. Nhưng thuật toán phân giải property cần tìm đường dẫn theo cấu trúc tên thực tế.

Một cách hình dung quá trình:

1. Thử property trực tiếp addressZipCode.
2. Nếu không có, thử tách theo ranh giới camel case từ phía phải.
3. Có thể tìm thấy addressZip rồi tiếp tục tìm code trên kiểu của addressZip.
4. Vì addressZip là String, phần code không tồn tại theo ý định này.

Thông báo lúc đó có thể nói không tìm thấy code trên String, dù người viết đang nghĩ đến zipCode của Address.

Điểm cần đọc trong lỗi là **đường dẫn đã được đi qua**, không chỉ từ khóa cuối cùng bị báo thiếu.

### Dùng dấu gạch dưới để chỉ ranh giới traversal

Có thể diễn đạt rõ:

~~~java
List<Customer> findByAddress_ZipCode(String zipCode);
~~~

Ở đây, dấu gạch dưới chỉ ra ranh giới giữa address và zipCode.

Đây là cách phân định property path, không phải yêu cầu đổi tên field Java thành address_zipCode. Nên dùng tên property Java theo quy ước camel case để tránh nhập nhằng không cần thiết.

Module vẫn phải hỗ trợ query trên đường dẫn được phân giải đó. Việc Commons hiểu address.zipCode không tự tạo ra một quan hệ join hoặc kiểu tham chiếu mà store không hỗ trợ.

## 5. Có trường hợp phân tích sai ý định nhưng không ném exception

Nếu Customer còn có property trực tiếp:

~~~java
String addressZipCode;
~~~

thì tên AddressZipCode có thể được phân giải thành property trực tiếp này, thay vì đi qua address.zipCode.

Lúc đó query có thể được tạo thành công nhưng lọc sai trường so với yêu cầu nghiệp vụ.

Do vậy:

~~~text
Không có PropertyReferenceException
không đồng nghĩa tên method đang biểu đạt đúng ý định.
~~~

Một test tốt cần fixture phân biệt hai đường dẫn:

| Customer | address.zipCode | addressZipCode |
| --- | --- | --- |
| A | 70000 | 10000 |
| B | 10000 | 70000 |

Nếu yêu cầu tìm theo address.zipCode bằng 70000, kết quả phải là A. Một test chỉ có hai field mang cùng giá trị sẽ không phát hiện việc query đang dùng nhầm property.

Dấu phân định rõ và integration test có dữ liệu đối chứng giúp phát hiện cả lỗi không khởi tạo được query lẫn lỗi query hợp lệ nhưng sai nghĩa.

## 6. Toán tử ở cuối tên cũng có thể tạo nhập nhằng

Spring Data nhận diện những hậu tố như In, Between, LessThan, IsNull, True hoặc IgnoreCase theo ngữ pháp hỗ trợ.

Ví dụ thông thường:

~~~java
List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);
~~~

Trong trường hợp này, Status là property và In là toán tử.

Nhưng nếu domain có property tên checkIn, tên sau có thể gây hiểu nhầm với toán tử In trong bộ phân tích dựa trên PartTree:

~~~java
List<Visit> findByCheckIn(String value);
~~~

Người viết có thể muốn so sánh bằng property checkIn, còn parser có thể đọc Check + In và đi tìm property check.

Một cách biểu đạt điều kiện bằng rõ hơn là:

~~~java
List<Visit> findByCheckInIs(String value);
~~~

Hậu tố Is diễn đạt phép so sánh đơn giản, để phần property là CheckIn. Cần xác nhận với mô hình và module đang dùng.

Bài học không phải là mọi tên kết thúc giống keyword đều sai. Cần đọc phần predicate thành property và toán tử, rồi xác nhận parser thực sự tạo ra cấu trúc mong đợi.

### Casing và thứ tự keyword

IgnoreCase, OrderBy và các keyword khác cần được viết theo ngữ pháp được hỗ trợ. Một lỗi casing có thể khiến đoạn tưởng là keyword trở thành một phần tên property.

Ví dụ, nếu IgnoreCase không được nhận diện đúng, parser có thể tìm một property dài hơn dự kiến thay vì báo “keyword viết sai”.

Khi method trở nên khó đọc hoặc khó phân định, nên cân nhắc query tường minh hoặc repository fragment thay vì tiếp tục kéo dài tên.

## 7. Đừng nhầm method dành riêng với derived query thông thường

Một số method kế thừa từ repository có ý nghĩa dành riêng, chẳng hạn findById. Chúng nhắm đến identifier của entity theo mapping, không đơn giản là một property bất kỳ có tên id.

Giả sử:

~~~text
Account.pk: identifier theo mapping của store.
Account.id: một mã nghiệp vụ kiểu String.
~~~

Repository:

~~~java
public interface AccountRepository
        extends CrudRepository<Account, Long> {

    Optional<Account> findAccountById(String businessId);
}
~~~

Với mô hình đó:

- findById(Long) kế thừa nhắm đến identifier pk.
- findAccountById(String) có phần mô tả Account trong subject, để truy vấn được dẫn xuất theo property id trong ví dụ này.

Cần khai báo mapping identifier bằng cơ chế phù hợp với module cụ thể. Không có một annotation identifier áp dụng theo cùng cách cho mọi store.

Đây có thể là lỗi hành vi không gây PropertyReferenceException: query chạy được nhưng tìm theo identifier khác với điều người viết nghĩ.

Đừng sửa bằng cách đổi bừa kiểu ID của repository. Trước hết cần xác định identifier thật và property nghiệp vụ cần truy vấn.

## 8. Method tùy biến bị đưa vào query derivation

Không phải mọi method khai báo trong repository đều nên được hiểu là một derived query.

Giả sử ứng dụng muốn một tìm kiếm tùy biến:

~~~java
public interface CustomerLookup {
    List<Customer> searchForDashboard(SearchCriteria criteria);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerLookup {
}
~~~

Nếu fragment implementation không được tìm thấy hoặc không được ghép đúng, hạ tầng có thể cố xử lý method đó như query method. Phần tên không có ý nghĩa property phù hợp có thể dẫn đến lỗi tạo query, trong đó có PropertyReferenceException.

Những điểm cần kiểm tra:

- Fragment interface có được repository kế thừa không?
- Implementation có được phát hiện hoặc cấu hình đúng không?
- Tên implementation có khớp quy ước postfix đang dùng không?
- Package scan và dependency injection có đưa đúng implementation vào không?
- Có nhầm tên class hoặc signature giữa interface và implementation không?

Với quy ước fragment phổ biến dùng hậu tố Impl, một class mang tên Adapter không tự chắc chắn được phát hiện như implementation tương ứng. Cần đối chiếu cấu hình thực tế.

Không sửa method tùy biến thành một tên derived query dài chỉ để tránh lỗi, nếu yêu cầu thực sự cần logic riêng.

## 9. Query khai báo tường minh không được nhận diện

Spring Data có các query lookup strategy với ý nghĩa khác nhau:

| Strategy | Ý nghĩa khái quát |
| --- | --- |
| CREATE | Tạo query từ tên method |
| USE_DECLARED_QUERY | Tìm query đã được khai báo và báo lỗi nếu không có |
| CREATE_IF_NOT_FOUND | Ưu tiên query khai báo, nếu không có thì thử tạo từ tên |

Khả năng và cấu hình cụ thể thuộc module đang sử dụng.

Một method có tên không phù hợp để derivation có thể gây lỗi property nếu người viết tưởng query tường minh đã được nhận diện, nhưng hạ tầng lại rơi vào nhánh tạo query từ tên.

Cần kiểm tra:

1. Annotation Query được import từ module nào.
2. Query đã gắn đúng method chưa.
3. Named query có đúng tên và được nạp không.
4. Lookup strategy đang áp dụng.
5. Repository có thuộc module mà người viết dự kiến không.

Annotation Query của Spring Data JPA và annotation Query của Spring Data MongoDB không phải cùng một annotation. Không chỉ nhìn tên ngắn trong IDE rồi cho rằng chúng có thể thay nhau.

Không đổi lookup strategy chỉ để che lỗi wiring. Strategy mới có thể đổi cách toàn bộ repository chọn query.

## 10. Sort cũng có thể là nguồn lỗi property

Xét method có tên đúng:

~~~java
List<Customer> findByActiveTrue(Sort sort);
~~~

Nếu caller truyền:

~~~java
Sort.by("email_address");
~~~

trong khi domain chỉ có property emailAddress, lỗi có thể xuất hiện khi phân giải sort.

Với derived query thông thường, nên diễn đạt:

~~~java
Sort.by("emailAddress");
~~~

Sau đó module chuyển property path sang biểu diễn phù hợp của store.

Query tùy biến, alias hoặc native query có thể có quy tắc khác; cần xem đúng API đang dùng. Không áp dụng một kết luận về Sort cho mọi dạng query.

Khi lỗi chỉ xuất hiện ở một request thay vì lúc khởi động, hãy kiểm tra cả sort động từ Pageable hoặc tham số truy vấn, không chỉ tên method.

### Sort tĩnh trong tên method

Tên như:

~~~java
List<Customer> findByActiveTrueOrderByCreatedAtDesc();
~~~

vẫn cần property createdAt hợp lệ. Viết sai trong phần OrderBy có thể gây lỗi property tương tự sai phần filter.

Nên phân biệt rõ lỗi thuộc:

~~~text
Predicate
Traversal
Sort tĩnh
Sort động
~~~

## 11. Đọc exception từ ngoài vào trong rồi quay lại method

Một chuỗi lỗi minh họa:

~~~text
BeanCreationException
  → QueryCreationException
    → PropertyReferenceException
~~~

Quy trình đọc hiệu quả:

1. Tìm repository và method được nêu trong thông báo tạo query.
2. Xác định property bị báo thiếu.
3. Xác định type mà parser đang tìm property đó.
4. Đọc đường dẫn đã traverse nếu có.
5. Đối chiếu với domain thật và cách tách tên.
6. Kiểm tra nguồn property có đến từ Sort hoặc cơ chế động không.

Không phải lúc nào chỉ đọc dòng cuối cùng cũng đủ. Dòng cuối có thể nói về một type lồng nhau, còn method gây ra nó nằm ở phần wrapper phía trên.

### Ví dụ diễn giải

~~~text
Property bị thiếu: code.
Type đang xét: String.
Đường dẫn đã đi qua: Customer.addressZip.
Method: findByAddressZipCode.
~~~

Dữ liệu này hướng tới nhập nhằng AddressZip + Code, thay vì lỗi field zipCode trong Address.

Nếu chỉ sửa Address.zipCode vì nhìn thấy chữ Code, bạn có thể sửa sai tầng mà không thay đổi nguyên nhân.

## 12. Quy trình chẩn đoán có thứ tự

### Bước 1: Xác định lời gọi đang thất bại

Lỗi xảy ra khi tạo repository, lần gọi query đầu tiên hay khi truyền sort động? Bootstrap mode và cơ chế tạo query có thể làm thời điểm lỗi khác nhau.

Không giả định mọi derived query sai đều phải làm ứng dụng dừng ngay ở cùng một thời điểm.

### Bước 2: Xác nhận domain và property

Đọc kiểu domain thật, generic repository và property path cần truy vấn. Kiểm tra spelling, casing và các kiểu lồng nhau.

Property tồn tại trong Java chưa chứng minh nó là thuộc tính truy vấn hợp lệ theo mapping. Một field không persistent hoặc quan hệ không được hỗ trợ có thể tạo lỗi ở tầng khác.

### Bước 3: Tách method bằng tay

Ghi rõ:

~~~text
Subject: findCustomer
Predicate: EmailAddressAndActiveTrue
Sort: OrderByCreatedAtDesc
~~~

Sau đó đối chiếu từng phần với ngữ pháp của module, thay vì nhìn tên như một câu tiếng Anh.

### Bước 4: Kiểm tra nhập nhằng

Tìm property trực tiếp có thể được ưu tiên hoặc đoạn camel case có thể đi vào nhánh khác. Dùng dấu phân định traversal khi phù hợp.

### Bước 5: Kiểm tra việc chọn implementation/query

Nếu method không định dùng derivation, kiểm tra fragment, query annotation, named query và lookup strategy.

### Bước 6: Kiểm tra nguồn tên động

Đối chiếu Sort, Pageable và các property string được truyền từ caller.

### Bước 7: Tái hiện bằng trường hợp nhỏ

Giữ method và phần domain liên quan, rồi xác nhận lỗi thuộc parser, mapping hay store. Không cần thử thay đổi đồng thời nhiều cấu hình.

### Bước 8: Kiểm chứng cả khởi tạo và kết quả

Sau khi hết exception, gọi query thật với fixture phân biệt các trường có thể bị nhầm. Khởi động được chưa đủ chứng minh query đúng nghĩa.

## 13. Unit test cho cấu trúc phân tích bằng Commons

Có thể dùng PartTree để kiểm tra một tên method được tách thành property path nào. Đây là kiểm tra parser, không cần khởi động store.

Ví dụ JUnit Jupiter và AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.data.mapping.PropertyReferenceException;
import org.springframework.data.repository.query.parser.Part;
import org.springframework.data.repository.query.parser.PartTree;

class DerivedPropertyPathTest {

    static class Customer {
        String emailAddress;
        Address address;
        String addressZip;
    }

    static class Address {
        String zipCode;
    }

    @Test
    void underscoreMakesTheNestedPathExplicit() {
        PartTree tree = new PartTree(
                "findByAddress_ZipCode", Customer.class);

        Part part = tree.getParts().iterator().next();

        assertThat(part.getProperty().toDotPath())
                .isEqualTo("address.zipCode");
    }

    @Test
    void typoDoesNotResolveToAnExistingProperty() {
        assertThatThrownBy(() ->
                new PartTree("findByEmailAdress", Customer.class))
                .isInstanceOf(PropertyReferenceException.class);
    }

    @Test
    void ambiguousCamelCaseCanChooseTheWrongPrefix() {
        assertThatThrownBy(() ->
                new PartTree("findByAddressZipCode", Customer.class))
                .isInstanceOf(PropertyReferenceException.class);
    }
}
~~~

Các model lồng trong test chỉ nhằm minh họa cấu trúc property cho parser, không phải entity đã có mapping store hoàn chỉnh.

Test parser giúp kiểm tra cách tách method, nhưng chưa chứng minh:

- Toán tử được store hỗ trợ.
- Mapping và tên cột/field đúng.
- Tham số được bind đúng.
- Query trả đúng dữ liệu.
- Fragment hoặc declared query được chọn như dự kiến.

Vì vậy, không dùng nó thay cho mọi integration test repository.

## 14. Integration test cần có dữ liệu đối chứng

Một phép kiểm chứng tốt nên:

1. Tạo repository thật của module.
2. Nạp domain mapping thật.
3. Có fixture phân biệt property trực tiếp và đường dẫn lồng.
4. Gọi đúng method với tham số cụ thể.
5. Assertion chính xác ID hoặc tập kết quả mong muốn.

Ví dụ với hai customer A và B ở phần trước:

~~~text
Query theo address.zipCode = 70000 → chỉ A.
Query theo addressZipCode = 70000 → chỉ B.
~~~

Nếu test chỉ assert kết quả không rỗng, cả hai query đều có thể vượt qua. Assertion cần phân biệt hành vi.

Mock repository không phân tích tên method. Stub một method viết sai vẫn có thể trả kết quả do test cấu hình, nên không xác minh được query derivation.

Cần có thêm ca cho sort động nếu ứng dụng cho caller lựa chọn sort. Một method đúng không bảo vệ mọi chuỗi property được truyền vào lúc chạy.

## 15. Chọn cách sửa theo nguyên nhân

| Nguyên nhân | Cách sửa phù hợp |
| --- | --- |
| Sai spelling hoặc casing | Đồng bộ tên method với property domain |
| Dùng tên cột thay property | Dùng property Java trong derived query |
| Sai domain generic | Sửa repository trỏ đúng domain và ID |
| Traversal nhập nhằng | Phân định path rõ hoặc viết query tường minh |
| Property trùng với đoạn keyword | Diễn đạt toán tử rõ và kiểm tra parser |
| Fragment chưa được ghép | Sửa implementation discovery hoặc wiring |
| Query annotation sai module | Dùng annotation và cấu hình đúng module |
| Named query không được tìm thấy | Sửa tên, nơi khai báo và cấu hình nạp |
| Sort động sai property | Chuẩn hóa tên sort theo hợp đồng được hỗ trợ |
| Query hợp lệ nhưng sai nghĩa | Sửa ý định truy vấn và thêm fixture đối chứng |

Không thêm một property giả vào domain chỉ để làm parser hết lỗi nếu nghiệp vụ không cần property đó. Cách này có thể biến lỗi cấu hình rõ ràng thành query chạy được nhưng trả sai dữ liệu.

Không bắt PropertyReferenceException rồi trả danh sách rỗng như thể “không có kết quả”. Lỗi cấu trúc truy vấn khác với một truy vấn hợp lệ không tìm thấy dữ liệu.

Retry cùng tên method và cùng metadata thường không giải quyết một lỗi phân giải property mang tính cấu hình. Cần sửa cấu trúc hoặc nguồn metadata gây lỗi.

## 16. Những điều không nên suy ra từ exception

- Không phải cứ có PropertyReferenceException là thiếu cột trong database.
- Không phải kiểu được nêu trong lỗi luôn là root entity.
- Không phải hết exception là query đã đúng ý định.
- Không phải thêm underscore vào mọi tên method đều tốt hơn.
- Không phải một tên hợp lệ trong PartTree được mọi module thực thi.
- Không phải repository mock xanh là derived query hợp lệ.
- Không phải mọi lỗi tạo query đều là lỗi property.

Lỗi từ ngôn ngữ query, constraint, conversion hoặc binding có thể có exception khác. Cần phân loại theo nguyên nhân thực tế, tránh sửa tên method khi vấn đề nằm ở tầng khác.

## 17. Bài tập áp dụng

1. Tạo một method viết sai emailAddress và đọc chuỗi nguyên nhân đến property bị thiếu.
2. Dựng domain có address cùng addressZip và kiểm tra cách phân tích AddressZipCode.
3. Viết lại method với Address_ZipCode, xác nhận path bằng PartTree.
4. Thêm property trực tiếp addressZipCode và dùng fixture phân biệt để phát hiện query sai nghĩa.
5. Mô phỏng một Sort dùng tên cột thay property rồi sửa đúng hợp đồng.
6. Kiểm tra một method tùy biến: nó được fragment xử lý hay đang rơi vào query derivation?
7. Phân biệt findById kế thừa với một derived method tìm theo property nghiệp vụ id.
8. Gọi repository thật để kiểm chứng kết quả sau khi đã sửa lỗi parser.

Chẩn đoán hiệu quả cần xác định parser đang tìm property nào, trên kiểu nào và từ nguồn tên nào. Khi đường dẫn đã đúng, vẫn cần kiểm chứng query với mapping, khả năng của store và dữ liệu thể hiện rõ ý định nghiệp vụ.
