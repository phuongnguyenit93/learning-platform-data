# Quy trình tái hiện tối thiểu và đọc stack trace qua các lớp hạ tầng

Một lỗi repository thường xuất hiện bên ngoài dưới dạng lỗi tạo bean, lỗi thực thi request hoặc lỗi transaction. Phần gây lỗi trực tiếp có thể nằm sâu hơn: kiểu generic chưa xác định, property trong derived query không tồn tại, fragment chưa được ghép, dữ liệu vi phạm ràng buộc hoặc driver không thực hiện được thao tác.

Trong chương **Lỗi và chẩn đoán** của module **SPRING_DATA_COMMONS**, bài học này xây dựng quy trình đi từ lỗi quan sát được tới một ca tái hiện nhỏ, đọc được và có thể kiểm chứng. Repository, CRUD, truy vấn, phân trang, projection và auditing đều đi qua nhiều lớp hạ tầng; mục tiêu không phải bỏ qua các lớp đó, mà là xác định lớp nào đang phát hiện lỗi và điều kiện nào đã đưa hệ thống tới đó.

## 1. Ghi nhận đúng hiện tượng trước khi rút gọn

Trước khi thay code, cần mô tả lỗi bằng một thao tác có thể lặp lại.

Một mô tả như “Spring Data không chạy” chưa cho biết đủ điều kiện. Một mô tả tốt hơn:

```text
Khi khởi tạo CustomerRepository của module JPA,
query method findByEmali(String) không được tạo.
Ứng dụng báo lỗi tạo bean customerService,
nhưng trong chuỗi nguyên nhân có lỗi property emali của Customer.
```

Cần giữ ít nhất:

- Thao tác hoặc bước khởi tạo gây lỗi.
- Repository, method và domain type liên quan.
- Thời điểm: bootstrap, lời gọi đầu tiên, truy vấn, mapping, flush hay commit.
- Loại exception bên ngoài cùng nguyên nhân liên quan bên trong.
- Phiên bản runtime, Spring Data, store module, driver và hệ lưu trữ.
- Dữ liệu, cấu hình hoặc thứ tự thao tác cần thiết để lỗi xuất hiện.

Đừng lập tức đổi dependency, xóa dữ liệu và đổi query cùng một lượt. Khi nhiều biến thay đổi đồng thời, rất khó biết điều gì đã làm lỗi biến mất hoặc chỉ bị che đi.

### 1.1. Giữ dấu hiệu nhận diện lỗi, không khóa vào mọi ký tự

Khi rút gọn, thông báo có thể đổi tên bean hoặc số dòng. Điều cần giữ là hiện tượng có ý nghĩa: cùng method, cùng loại điều kiện sai và cùng giai đoạn phát hiện.

Một lỗi kết nối mới xuất hiện thay cho lỗi parse query không phải bằng chứng rằng đã tái hiện được lỗi cũ trong một cấu hình nhỏ hơn.

## 2. Vẽ đường đi qua hạ tầng

Một đường thực thi imperative điển hình có thể gồm:

```text
Controller hoặc adapter
        |
        v
Service và transaction proxy
        |
        v
Repository proxy
        |
        +-- Query method
        +-- Custom fragment
        +-- CRUD nền hoặc repository aspect
        |
        v
Store module và mapping
        |
        v
Provider hoặc template truy cập dữ liệu
        |
        v
Driver -> hệ lưu trữ
```

Lỗi khởi tạo có thể xuất hiện trước khi có request hoặc dữ liệu nghiệp vụ. Lỗi reactive lại có thể chỉ xuất hiện khi publisher được subscribe. Vì vậy, sơ đồ trên là công cụ suy luận, không phải lời hứa rằng mọi lỗi đều đi qua đầy đủ các ô theo cùng một stack.

### 2.1. Lớp phát hiện lỗi không luôn là nơi cần sửa

Parser của Spring Data phát hiện property không tồn tại, nhưng nơi cần sửa có thể là tên method trong repository. Database phát hiện unique violation, nhưng nguyên nhân nghiệp vụ có thể là thao tác lặp hoặc thiếu ràng buộc trong thiết kế xử lý yêu cầu.

Ngược lại, không phải mọi lỗi bên trong thư viện đều do code ứng dụng. Muốn phân biệt, cần một ca tái hiện giữ đúng hợp đồng và bộ phiên bản, thay vì kết luận chỉ dựa vào package của frame đầu tiên.

## 3. Đọc cấu trúc stack trace

Một exception Java có thể chứa message, các frame, cause và những exception suppressed. Chúng có vai trò khác nhau, được mô tả trong [Throwable API của Java](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html).

| Thành phần | Ý nghĩa khi chẩn đoán |
| --- | --- |
| Exception ngoài cùng | Điều mà tầng gọi cuối cùng quan sát được |
| Message | Tên bean, method, property, mã lỗi hoặc ngữ cảnh khác |
| Các dòng `at` | Vị trí thực thi tại thời điểm ghi nhận stack của throwable |
| `Caused by` | Quan hệ nguyên nhân được lớp bọc giữ lại |
| `Suppressed` | Exception hoặc thông tin bổ sung không được đưa lên làm lỗi chính |
| `... N more` | Phần frame chung được rút gọn, không phải N lỗi bị giấu |

### 3.1. Đọc theo hai lượt

**Lượt một: từ ngoài vào trong.** Xác định tác động ở tầng ngoài, lần theo cause và ghi những tên liên quan. Không dừng ở `BeanCreationException` hoặc một wrapper tương tự nếu còn nguyên nhân cụ thể hơn.

**Lượt hai: từ nguyên nhân liên quan quay ra thao tác ứng dụng.** Tìm khai báo hoặc lời gọi đã đưa dữ liệu và cấu hình vào đường lỗi đó. Xác định một thay đổi có thể kiểm chứng.

Frame ứng dụng gần thư viện giúp tìm điểm vào, nhưng không tự chứng minh dòng đó sai. Nó có thể chỉ là nơi gọi một API đúng để hạ tầng phát hiện lỗi dữ liệu ở dưới.

### 3.2. Không chỉ lấy dòng cuối của log

Throwable tạo thành một cấu trúc có nhánh suppressed và cause, không phải lúc nào cũng là một cột duy nhất. Dòng cuối văn bản có thể là thông tin đóng tài nguyên, một frame chung hoặc một nhánh bổ sung.

Nguyên nhân sâu nhất cũng có thể chỉ cho biết hiện tượng kỹ thuật, chưa giải thích đầy đủ quyết định nghiệp vụ dẫn tới nó. Cần đọc message và ngữ cảnh của cả chuỗi có liên quan.

## 4. Ví dụ: lỗi tạo service che lỗi derived query

Đây là chuỗi **minh họa rút gọn**, không phải stack trace thu được từ một lần chạy trong bài:

```text
UnsatisfiedDependencyException: không tạo được customerService
  Caused by: BeanCreationException: không tạo được customerRepository
    Caused by: QueryCreationException: không tạo được query cho findByEmali
      Caused by: PropertyReferenceException: property emali của Customer không hợp lệ
```

Có thể đọc thành:

1. Service không được tạo vì dependency repository thất bại.
2. Repository thất bại khi hạ tầng tạo query method.
3. Parser không tìm được property được diễn đạt trong method.
4. Cần đối chiếu `findByEmali` với domain type thật, không chỉ sửa service injection.

Giả sử domain có thuộc tính email:

```java
public class Customer {

    private String email;

    public String getEmail() {
        return email;
    }
}
```

Khai báo có lỗi:

```java
Optional<Customer> findByEmali(String email);
```

Ý định đúng:

```java
Optional<Customer> findByEmail(String email);
```

Derived query phân tích các property của domain theo cơ chế query lookup và store tương ứng. Cách xác định tên và đường dẫn property được mô tả trong [định nghĩa query methods của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html).

### 4.1. Đối chiếu property Java với tên cột lưu trữ

Nếu JPA mapping dùng:

```java
@Column(name = "email_address")
private String email;
```

property domain vẫn là email. Không đổi method thành một tên dựa hoàn toàn vào cột SQL rồi mặc định parser hiểu cùng một điều. Cần xác định đang viết derived method theo property hay native query theo schema.

### 4.2. Cùng một loại lỗi có thể dẫn tới hướng điều tra khác

Nếu method là `searchByCriteria(CustomerCriteria)` và ý định ban đầu là dùng custom fragment, property criteria không tồn tại có thể là dấu hiệu fragment chưa được ghép, khiến method đi vào query lookup ngoài ý định.

Trước khi đổi tên method hoặc thêm field, hãy xác định method đó vốn là derived query, query khai báo hay custom fragment. Không sửa cùng một loại exception bằng một công thức duy nhất.

## 5. Xây dựng ca tái hiện tối thiểu nhưng vẫn đúng lỗi

**Tối thiểu** nghĩa là bỏ phần không cần để tái hiện hiện tượng, không phải bỏ hết hạ tầng có liên quan rồi tạo một lỗi khác nhỏ hơn.

Một chu trình rút gọn:

```text
Có ca lỗi lặp lại được
        |
        v
Đưa ra giả thuyết một yếu tố không cần thiết
        |
        v
Bỏ hoặc thay đúng yếu tố đó
        |
        v
Chạy lại cùng bước kích hoạt
        |
        +-- Còn đúng lỗi -> giữ bản rút gọn
        |
        +-- Mất lỗi hoặc đổi lỗi -> khôi phục và xét yếu tố khác
```

### 5.1. Giữ những gì theo loại lỗi

| Loại lỗi | Thành phần thường cần giữ |
| --- | --- |
| Parse tên query | Method, domain property, kiểu tham số và parser hoặc store cần thiết |
| Generic repository | Chuỗi kế thừa interface và metadata của repository cuối |
| Fragment discovery | Interface, implementation, package, postfix và cấu hình đăng ký |
| Mapping entity hoặc DTO | Các thuộc tính, constructor và query shape liên quan |
| Transaction hoặc commit | Proxy, manager, propagation và thời điểm kết thúc transaction |
| Driver hoặc database | Store thật hoặc môi trường tái hiện tương thích, schema và kiểu dữ liệu |
| Cạnh tranh | Ít nhất các đơn vị công việc và thứ tự đồng bộ cần thiết |
| Reactive | Pipeline, subscription, context và các operator ảnh hưởng lỗi |

Một controller thường có thể bỏ khỏi ca lỗi parse repository, nhưng không được bỏ service proxy nếu lỗi đang điều tra là self-invocation khiến transaction không mở.

Một database thay thế có thể làm bản thử nghiệm dễ dựng hơn, nhưng không phù hợp nếu lỗi phụ thuộc kiểu UUID, collation, isolation hoặc cú pháp riêng của database ban đầu.

### 5.2. Fixture nhỏ nhất đủ chứng minh điều kiện

- Lỗi property khi khởi tạo query có thể không cần bản ghi nghiệp vụ nào.
- Lỗi kết quả đơn nhưng có nhiều bản ghi cần ít nhất hai kết quả khớp.
- Lỗi unique cần dữ liệu hoặc thao tác tạo xung đột thực sự.
- Lỗi phân trang có thể cần các giá trị sort bằng nhau để lộ sự thiếu khóa phụ.
- Lỗi tenant cần ít nhất dữ liệu đúng phạm vi và một đối chứng ngoài phạm vi.

Không nạp cả một bộ dữ liệu lớn nếu chỉ hai bản ghi đã biểu hiện được điều kiện. Đồng thời, không giảm tới một bản ghi rồi làm mất chính lỗi cardinality cần điều tra.

## 6. Thu hẹp giả thuyết bằng một phép thử parser

Với ví dụ typo emali, có thể kiểm tra riêng cơ chế phân tích property mà chưa khởi động JPA hoặc database:

```java
import org.junit.jupiter.api.Test;
import org.springframework.data.mapping.PropertyReferenceException;
import org.springframework.data.repository.query.parser.PartTree;

import static org.junit.jupiter.api.Assertions.*;

class CustomerQueryParsingTest {

    @Test
    void misspelledPropertyCannotBeParsed() {
        assertThrows(PropertyReferenceException.class, () ->
                new PartTree("findByEmali", Customer.class));
    }

    @Test
    void existingPropertyCanBeParsed() {
        assertDoesNotThrow(() ->
                new PartTree("findByEmail", Customer.class));
    }

    static class Customer {
        private String email;

        public String getEmail() {
            return email;
        }
    }
}
```

Phép thử này hỗ trợ giả thuyết lỗi ở property parsing trong ví dụ. Nó không chứng minh repository thật đã dùng đúng domain, fragment đã được ghép hay một database cụ thể hỗ trợ toàn bộ query.

Sau khi kiểm tra phần hẹp, phải quay lại đường khởi tạo hoặc gọi repository thật để xác nhận lỗi gốc được giải quyết. Nếu repository production đang dùng một Customer khác package, test với lớp Customer đơn giản trên không tự phát hiện import sai đó.

### 6.1. Từ phép thử hẹp tới bản tái hiện tích hợp

Bản tái hiện tích hợp có thể chỉ giữ:

```text
Một cấu hình test cho store đang dùng
Một domain type với các thuộc tính liên quan
Một repository chứa method gây lỗi
Một bước khởi tạo context hoặc gọi method kích hoạt lỗi
Dữ liệu tối thiểu nếu lỗi cần dữ liệu
```

Với lỗi tạo repository, sự kiện cần quan sát có thể là khởi tạo thất bại; không nhất thiết có một phương thức test chạy được tới thân bài. Với bootstrap lazy, cần lời gọi sử dụng để đi tới bước khởi tạo thực sự.

Không coi việc mock repository rồi trả kết quả mong muốn là tái hiện lỗi tạo query của repository thật.

## 7. Xác định chính xác thời điểm lỗi persistence xuất hiện

Một thao tác ghi có thể có các mốc khác nhau:

```text
save
    -> thực hiện hoặc lên lịch thao tác persistence
flush
    -> đồng bộ thay đổi theo cơ chế provider
commit
    -> hoàn tất transaction và kiểm tra các điều kiện còn lại
```

Đây là mô hình cần đối chiếu theo store; không phải mọi module đều có một API flush giống JPA.

### 7.1. Vì sao catch quanh save có thể không bắt được lỗi commit?

Nếu transaction proxy quản lý ranh giới quanh service method, phần commit có thể xảy ra sau khi thân method đã trả về bình thường. Khi đó, một try/catch chỉ ở trong thân method quanh `save` không bao trọn bước commit bên ngoài.

Khi tái hiện lỗi chỉ phát sinh lúc commit, thao tác kết thúc transaction phải nằm trong phạm vi quan sát của ca test. Một test mặc định rollback có thể không đi qua đúng giai đoạn gây lỗi.

### 7.2. Flush giúp thấy một số lỗi, nhưng không thay commit

Với JPA, thêm một lần flush có chủ đích có thể giúp xác định lỗi ràng buộc xuất hiện khi đồng bộ dữ liệu. Tuy nhiên, flush thành công không chứng minh commit sẽ thành công, và dữ liệu vẫn có thể rollback sau flush.

Không thêm flush vào mọi repository như một cách chữa lỗi chung. Hãy dùng nó để kiểm tra một giả thuyết có liên quan tới thời điểm thực thi, rồi chọn ranh giới nghiệp vụ phù hợp.

### 7.3. Lỗi được báo sau commit cần kiểm tra trạng thái cuối

Callback hoặc tác vụ sau commit có thể lỗi trong khi transaction ghi đã hoàn tất. Bên gọi nhận exception không luôn đồng nghĩa mọi thay đổi đã rollback.

Nếu cần biết trạng thái cuối, đọc lại bằng một đơn vị quan sát phù hợp sau khi transaction trước kết thúc, và xác định có transaction độc lập hay tài nguyên ngoài nào tham gia không.

## 8. Giữ nguyên cause và thông tin có thể đối chiếu

Một lớp bọc exception đúng cách nên giữ throwable gốc:

```java
public class CustomerLookupException extends RuntimeException {

    public CustomerLookupException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Khi chuyển ngữ nghĩa lỗi ở ranh giới ứng dụng, có thể dùng constructor đó thay vì tạo exception mới chỉ từ `ex.getMessage()`.

### 8.1. Ghi log với throwable thật

Ví dụ dùng API logging theo phong cách SLF4J:

```java
log.error("Customer lookup failed; requestId={} method={}",
        requestId, "findByEmail", exception);
```

Throwable ở đối số cuối giữ được stack trace và cause theo cơ chế logging tương ứng. Chỉ ghi `exception.getMessage()` thường mất phần thông tin cần lần qua các lớp hạ tầng.

Nên giữ context đủ để nối sự kiện: request ID, repository hoặc method, giai đoạn và hình dạng đầu vào cần thiết. Khi dữ liệu cụ thể không cần cho việc tái hiện, có thể dùng fixture thay thế nhưng giữ nguyên kiểu, trạng thái null, độ dài hoặc tính trùng lặp có liên quan.

### 8.2. Tránh log cùng lỗi ở mọi tầng

Nếu mỗi lớp đều log rồi ném lại cùng exception, một lần thất bại có thể tạo nhiều bản trace trông như nhiều sự cố. Chọn ranh giới ghi nhận phù hợp, giữ cause khi chuyển exception và nối các sự kiện bằng context.

Không biến mọi lỗi thành một chuỗi “không tìm thấy dữ liệu”. Kết quả vắng mặt, lỗi mapping và lỗi kết nối là những hiện tượng khác nhau, cần hợp đồng xử lý khác nhau.

### 8.3. Cause không thay thế mọi nguồn thông tin

Ngoài chuỗi exception, có thể cần query, kiểu tham số, mã lỗi driver hoặc tên ràng buộc. Những thông tin này giúp phân biệt lỗi dữ liệu, mapping và hạ tầng.

Một helper chỉ trả về cause sâu nhất không thay cho việc lưu đầy đủ throwable. Nó có thể bỏ ngữ cảnh bean hoặc method được các wrapper giữ lại, cùng các nhánh suppressed quan trọng.

## 9. Đọc lỗi reactive theo assembly và execution

Trong reactive, nơi tạo pipeline và nơi thực thi có thể khác nhau. Stack tại thời điểm subscribe thường chứa nhiều operator hoặc frame driver mà chưa chỉ ra đoạn ứng dụng đã lắp ghép đường gây lỗi.

Có thể bổ sung checkpoint có ý nghĩa:

```java
Mono<Customer> result = reactiveRepository.findByEmail(email)
        .checkpoint("customer lookup: findByEmail");
```

Đoạn này giả định repository reactive trả `Mono<Customer>` và store hỗ trợ method tương ứng. Checkpoint là dấu mốc quan sát, không tự sửa query, mở transaction hoặc kích hoạt subscription.

Tài liệu [Debugging Reactor](https://projectreactor.io/docs/core/release/reference/debugging.html) giải thích assembly traceback, thông tin suppressed và checkpoint. Các chế độ ghi lại stack toàn cục có chi phí riêng; nên chọn cách thu thập thông tin theo mục tiêu chẩn đoán thay vì bật mọi cơ chế mặc định.

### 9.1. Không tái hiện lỗi lazy bằng cách chỉ tạo publisher

Một ca test reactive phải subscribe và quan sát tín hiệu kết thúc hoặc lỗi, chẳng hạn bằng công cụ test reactive thích hợp. Chỉ assertion publisher khác null chưa làm công việc dữ liệu thực thi.

Đừng gọi `.subscribe()` rồi assertion ngay ở dòng sau, vì lỗi có thể xuất hiện sau khi test đã đi qua assertion. Cần để công cụ test chờ và kiểm tra đúng tín hiệu.

### 9.2. Không quy lỗi theo tên luồng

Lỗi chạy trên một luồng driver khác không tự chứng minh transaction hoặc context bị mất. Với transaction reactive, phải xét pipeline, Reactor Context và thành phần truy cập dữ liệu thực sự tham gia.

Khi rút gọn, giữ lại operator có thể thay đổi hình dạng lỗi hoặc vòng đời như retry, timeout, take, single và các nhánh subscription riêng, nếu chúng liên quan hiện tượng.

### 9.3. Suppressed có thể chứa thông tin lắp ghép hữu ích

Trong traceback của Reactor, suppressed có thể chứa dấu vết nơi lắp ghép hoặc nơi lỗi được quan sát, không chỉ một lỗi đóng tài nguyên. Đọc tên và nội dung nhánh trước khi quyết định bỏ nó khỏi bản chẩn đoán.

## 10. Phân loại theo giai đoạn để tránh sửa sai tầng

| Giai đoạn hoặc dấu hiệu | Hướng điều tra thường phù hợp |
| --- | --- |
| Tạo repository metadata | Domain, ID generic, base interface và NoRepositoryBean |
| Gắn repository với store | Module factory, phạm vi discovery và annotation mapping |
| Tạo query | Tên property, lookup strategy, query khai báo và custom fragment |
| Bind tham số hoặc gọi method | Kiểu ID, kiểu tham số, null và overload thực sự được gọi |
| Mapping kết quả | DTO constructor, alias, kiểu cột, null và projection |
| Thực thi driver | Query thật, schema, connection và lỗi hệ lưu trữ |
| Flush hoặc commit | Ràng buộc, version, transaction manager và trạng thái transaction |
| Kết quả đơn nhưng dữ liệu nhiều | Cardinality của query và dữ liệu fixture |
| Reactive chỉ lỗi khi subscribe | Pipeline, terminal signal, context và assembly site |
| Sau commit hoặc bất đồng bộ | Callback, outbox, tác vụ nền và trạng thái đã lưu |

Bảng này tạo hướng kiểm tra, không dùng tên exception để suy đoán chắc chắn mọi nguyên nhân. Ví dụ lỗi mapping có thể bị bọc trong một lỗi tạo bean hoặc lỗi thực thi tùy thời điểm framework phát hiện.

## 11. Kiểm chứng giả thuyết bằng một thay đổi có mục tiêu

Mỗi lần sửa nên gắn với một dự đoán:

```text
Giả thuyết:
    Method dùng property emali không tồn tại.

Thay đổi:
    Đổi sang email, giữ nguyên phần còn lại liên quan.

Dự đoán:
    Lỗi PropertyReferenceException tại bước tạo query không còn.
    Repository thật khởi tạo được và query tìm đúng fixture.
```

Nếu lỗi chuyển thành sai cardinality vì dữ liệu có hai email giống nhau, đó là bước tiếp theo cần giải thích. Không coi một loại lỗi mới là cùng nguyên nhân đã được chứng minh.

### 11.1. Sau sửa, kiểm tra cả hành vi thành công

Một ca chỉ xác nhận không còn exception có thể bỏ sót việc query bị bỏ qua hoặc một bean bị loại khỏi discovery. Cần thêm quan sát theo hợp đồng: đúng bản ghi, đúng trạng thái sau commit hoặc đúng fragment được gọi.

Ví dụ loại bỏ repository khỏi scan làm ứng dụng không còn lỗi parse ở startup nhưng cũng không còn bean cần dùng; đó không phải kết quả thành công cho cùng yêu cầu.

### 11.2. Giữ ca hồi quy ở phạm vi phù hợp

Nếu lỗi là cấu trúc generic, một kiểm tra metadata nhỏ có thể giữ bài học ở đúng tầng. Nếu lỗi phụ thuộc database hoặc commit, cần ca tích hợp giữ các điều kiện đó.

Không đưa toàn bộ ứng dụng trở lại vào mọi test chỉ để bảo đảm “đủ thật”, và cũng không dùng một unit test thuần Java để tuyên bố đã kiểm chứng một tính năng riêng của store.

## 12. Một báo cáo tái hiện người khác có thể dùng

Một báo cáo ngắn nhưng đủ context có thể gồm:

```text
Mục tiêu:
    Repository cần tìm khách hàng theo email.

Kỳ vọng:
    Context khởi tạo, method truy vấn theo property email.

Thực tế:
    Tạo repository thất bại; cause liên quan là lỗi property emali.

Bước kích hoạt:
    Khởi tạo cấu hình store chứa đúng repository đó.

Thành phần tối thiểu:
    Domain Customer có email, repository có findByEmali,
    cấu hình store và bộ phiên bản đang tái hiện.

Dữ liệu cần thiết:
    Không cần bản ghi nghiệp vụ để biểu hiện lỗi parse này.

Đã loại trừ:
    Controller và tác vụ nền không ảnh hưởng hiện tượng trong bản rút gọn.

Bằng chứng:
    Chuỗi cause đầy đủ liên quan, repository method và domain thật.

Thay đổi đã thử:
    Đổi emali thành email; kiểm tra lại khởi tạo và kết quả query.
```

Với lỗi khác, thay thông tin theo đúng hiện tượng thay vì dùng nguyên mẫu rồi bỏ qua transaction, dữ liệu hoặc operator cần thiết.

Một quy trình chẩn đoán hiệu quả giữ được ba mối liên hệ: thao tác nào gây lỗi, hạ tầng nào phát hiện lỗi và cấu hình hoặc dữ liệu nào tạo ra điều kiện đó. Stack trace giúp lần qua các lớp; ca tái hiện tối thiểu giúp kiểm chứng suy luận. Khi hai phần hỗ trợ nhau, việc sửa repository trở nên có bằng chứng và ít phụ thuộc vào phỏng đoán hơn.
