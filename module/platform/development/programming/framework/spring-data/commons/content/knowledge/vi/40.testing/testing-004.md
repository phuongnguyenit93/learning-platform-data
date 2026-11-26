# Kiểm thử hợp đồng CRUD, ID và kiểu trả về

Một repository có thể được inject thành công nhưng vẫn lưu sai ID, đọc sai bản ghi hoặc khiến tầng dịch vụ hiểu nhầm một kết quả rỗng. Kiểm thử hợp đồng giúp xác nhận rằng ứng dụng và repository thực sự thống nhất về đầu vào, kết quả và trạng thái dữ liệu sau mỗi thao tác.

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, bài học này xây dựng cách kiểm thử CRUD, định danh và kiểu trả về của repository. Trọng tâm là các abstraction dùng chung của Spring Data; những điều phụ thuộc mapping, transaction, driver và store phải được nêu thành giả định riêng. Không lấy hành vi của một kho dữ liệu để áp thành quy tắc cho tất cả kho khác.

## 1. Kiểm thử hợp đồng là kiểm tra điều gì?

Hợp đồng của một thao tác gồm ít nhất bốn phần:

1. Đầu vào hợp lệ và không hợp lệ.
2. Ý nghĩa của kết quả trả về, bao gồm trường hợp không có dữ liệu.
3. Trạng thái lưu trữ sau thao tác.
4. Cách báo thất bại ở ranh giới API đang kiểm thử.

Ví dụ, kiểm thử `save` không nên chỉ xác nhận rằng đối tượng trả về khác `null`. Nếu mục tiêu là chứng minh một khách hàng được lưu đúng, cần lấy ID từ kết quả lưu rồi đọc lại dữ liệu và so sánh những thuộc tính có ý nghĩa.

```text
Tạo fixture hợp lệ
        |
        v
Gọi repository thật
        |
        v
Quan sát kết quả API
        |
        v
Đọc lại qua ranh giới persistence phù hợp
        |
        v
So sánh ID, thuộc tính và trạng thái mong muốn
```

### 1.1. Mock không chứng minh hợp đồng của store

Đoạn mock sau chỉ quy định một câu trả lời do chính người viết test tạo ra:

```java
when(repository.findById(id)).thenReturn(Optional.of(customer));
```

Nó có ích khi kiểm thử cách một service xử lý `Optional`, nhưng không chứng minh mapping ID, việc tạo câu truy vấn, generated ID hoặc hành vi lưu của repository thật.

Để kiểm thử tích hợp repository, cần dùng implementation do Spring Data tạo và một môi trường lưu trữ phù hợp. Một cơ sở dữ liệu thay thế có thể hữu ích cho một số trường hợp, nhưng không tự tái hiện mọi ràng buộc, kiểu dữ liệu hay cơ chế sinh ID của môi trường triển khai.

## 2. Lập ma trận từ interface đang sử dụng

Đừng bắt đầu bằng câu hỏi “có bao nhiêu phương thức cần gọi?”. Hãy bắt đầu từ các trạng thái quan sát được.

| Nhóm | Trạng thái đầu vào | Điều cần xác nhận |
| --- | --- | --- |
| Create | Entity mới hợp lệ | Dùng được đối tượng trả về; ID hợp lệ theo mapping; đọc lại đúng dữ liệu |
| Read | ID tồn tại | Trả đúng entity theo ID thực |
| Read | ID hợp lệ nhưng không tồn tại | Biểu diễn vắng mặt đúng kiểu API |
| Update | Entity hiện hữu được thay đổi | Giữ đúng định danh, lưu thuộc tính mới, không tạo thêm bản ghi ngoài ý muốn |
| Delete | ID tồn tại | Sau xóa không còn tìm thấy entity đó |
| Delete | ID không tồn tại | Đối chiếu hợp đồng của phương thức và phiên bản đang dùng |
| Bulk | Nhiều entity hoặc ID | Đủ dữ liệu mong muốn; không giả định thứ tự khi chưa có bảo đảm |
| Empty | Tập đầu vào hoặc kết quả rỗng | Kết quả rỗng đúng nghĩa, không nhầm với `null` |
| Invalid | Entity, ID hoặc phần tử không hợp lệ | Báo lỗi đúng tại ranh giới API đã chọn |

Cần đọc API của đúng abstraction. Chẳng hạn, `CrudRepository` trả `Iterable` cho một số thao tác, còn `ListCrudRepository` khai báo `List` tại các vị trí tương ứng. Sự khác biệt đó là hợp đồng kiểu dữ liệu, không phải quyền mặc định ép kiểu implementation.

## 3. Kiểm thử `save`: dùng kết quả trả về và đọc lại

Chữ ký cơ bản:

```java
<S extends T> S save(S entity);
```

Điểm quan trọng là phải sử dụng đối tượng mà `save` trả về. Implementation có thể trả một instance khác với đối tượng đầu vào; không đặt assertion bắt buộc chúng phải là cùng một reference. Xem [hợp đồng `save` của CrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html#save(S)).

### 3.1. Những assertion có ý nghĩa

Với fixture dùng generated ID, có thể kiểm tra:

```java
Customer saved = repository.save(Customer.newCustomer("Lan"));

assertNotNull(saved);
assertNotNull(saved.getId());

Long savedId = saved.getId();
```

Sau đó, đồng bộ và loại bỏ ảnh hưởng của persistence context khi store yêu cầu, đọc lại theo `savedId`, kiểm tra tên và ID.

Cần phân biệt rõ:

- “Generated ID không được rỗng sau khi lưu thành công” là kỳ vọng của mapping đã chọn trong ví dụ.
- “Mọi entity của Spring Data đều phải có ID kiểu `Long` do database sinh” không phải hợp đồng chung.

Một store có thể sử dụng UUID, chuỗi, ID được ứng dụng gán hoặc một loại định danh khác. Fixture và assertion phải phản ánh chiến lược thực tế đó.

### 3.2. Những assertion dễ tạo sai lệch

Không nên mặc định:

```java
assertSame(input, saved);
assertEquals(1L, saved.getId());
```

Assertion đầu áp một lựa chọn instance cụ thể lên abstraction. Assertion sau phụ thuộc trạng thái bộ sinh ID và môi trường; rollback hoặc cleanup dữ liệu cũng không nhất thiết đặt lại sequence.

Nên kiểm tra ID của entity đã lưu có thể dùng để truy xuất đúng entity đó, thay vì kiểm tra giá trị khởi đầu hoặc tính liên tục của dãy ID.

### 3.3. `save` không phải tên gọi chung cho upsert vô điều kiện

Cách phát hiện entity mới có thể dựa trên ID, version hoặc chiến lược của store. Một entity có ID khác `null` không luôn có cùng ý nghĩa ở mọi module.

Nếu ứng dụng dùng ID do mình gán, hãy kiểm thử riêng việc lưu lần đầu và cập nhật lần sau. Không giả định rằng gọi `save` với bất kỳ ID nào cũng luôn tạo mới nếu chưa tồn tại, hoặc luôn cập nhật mà không xét version.

## 4. ID cần được kiểm thử theo vai trò định danh

### 4.1. ID lưu trữ khác mã nghiệp vụ

Một khách hàng có thể có:

```text
pk = 101                 <- định danh persistence
customerCode = KH-2026   <- mã nghiệp vụ
```

`findById` là phương thức dành cho định danh repository. Nếu muốn tìm theo mã nghiệp vụ, ứng dụng phải khai báo một phương thức truy vấn phù hợp, ví dụ `findByCustomerCode`, và kiểm thử nó như một hợp đồng khác.

Đây cũng là lý do nên kiểm tra entity có nhiều thuộc tính dễ bị nhầm là ID. Một test chỉ dùng fixture có các giá trị giống nhau có thể bỏ sót lỗi nhầm trường định danh.

### 4.2. Có ID không đồng nghĩa bản ghi tồn tại

Một đối tượng có thể mang ID nhưng chưa được lưu, đã bị xóa hoặc là bản sao cũ. Assertion về `getId()` không thay được assertion về `findById` và `existsById`.

Khi cần một ID chắc chắn không tồn tại trong bài kiểm thử, có thể:

1. Tạo một entity hợp lệ bằng repository.
2. Giữ ID trả về.
3. Xóa entity đó và đồng bộ thay đổi.
4. Dùng ID vừa xóa để kiểm thử trường hợp vắng mặt.

Cách này tránh đoán rằng một hằng số như `999999L` chắc chắn không có trong dữ liệu test.

### 4.3. ID phải ổn định khi cập nhật entity hiện hữu

Với entity trong ví dụ, sau khi đổi tên và lưu lại, ID phải vẫn là ID của khách hàng cũ. Đồng thời, số entity không được tăng từ một thành hai chỉ vì thao tác cập nhật.

Nếu entity hoặc store có mô hình định danh đặc biệt, cần nêu rõ hợp đồng đó thay vì áp dụng máy móc fixture generated ID của ví dụ.

## 5. Một bộ kiểm thử CRUD có thể tái sử dụng

Ví dụ dưới đây dùng JUnit Jupiter và `CrudRepository<Customer, Long>`. Đây là mã minh họa cấu trúc kiểm thử; dự án cần cung cấp entity `Customer`, repository thật và cấu hình store.

Fixture domain được giả định như sau:

- `Customer.newCustomer(name)` tạo entity mới hợp lệ, chưa có generated ID.
- `getId()` trả `Long` và `getName()` trả tên đã lưu.
- `rename(name)` thay đổi tên.
- Hai customer mới trong ví dụ được phép có các tên tương ứng, không vi phạm ràng buộc khác.

Bộ test chỉ chạy trên kho dữ liệu kiểm thử riêng. Hook `synchronizeAndForget` do adapter của từng store cài đặt; với JPA, nó có thể flush rồi clear persistence context. Với store không có persistence context tương tự, hook phải phản ánh cơ chế quan sát dữ liệu thực tế, không giả lập một API JPA không tồn tại.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.repository.CrudRepository;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

abstract class CustomerCrudContract {

    protected abstract CrudRepository<Customer, Long> repository();

    protected abstract void synchronizeAndForget();

    @BeforeEach
    void resetStore() {
        repository().deleteAll();
        synchronizeAndForget();
    }

    @Test
    void savesAndReadsUsingReturnedId() {
        Customer saved = repository().save(
                Customer.newCustomer("Lan"));
        assertNotNull(saved);
        assertNotNull(saved.getId());
        Long id = saved.getId();

        synchronizeAndForget();

        Customer loaded = repository().findById(id).orElseThrow();
        assertEquals(id, loaded.getId());
        assertEquals("Lan", loaded.getName());
        assertTrue(repository().existsById(id));
    }

    @Test
    void updatesSameIdentityWithoutAddingAnotherCustomer() {
        Customer created = repository().save(
                Customer.newCustomer("Tên ban đầu"));
        Long id = created.getId();
        synchronizeAndForget();

        Customer detached = repository().findById(id).orElseThrow();
        synchronizeAndForget();
        detached.rename("Tên sau cập nhật");

        Customer updated = repository().save(detached);
        assertEquals(id, updated.getId());
        synchronizeAndForget();

        Customer reloaded = repository().findById(id).orElseThrow();
        assertEquals("Tên sau cập nhật", reloaded.getName());
        assertEquals(1L, repository().count());
    }

    @Test
    void deletingMakesIdAbsent() {
        Customer saved = repository().save(
                Customer.newCustomer("Khách sẽ xóa"));
        Long id = saved.getId();
        synchronizeAndForget();

        repository().deleteById(id);
        synchronizeAndForget();

        assertTrue(repository().findById(id).isEmpty());
        assertFalse(repository().existsById(id));
        assertEquals(0L, repository().count());
    }

    @Test
    void findsRequestedExistingIdsWithoutAssumingOrder() {
        List<Customer> saved = materialize(repository().saveAll(List.of(
                Customer.newCustomer("Khách A"),
                Customer.newCustomer("Khách B"))));
        assertEquals(2, saved.size());
        Long idA = saved.get(0).getId();
        Long idB = saved.get(1).getId();
        assertNotNull(idA);
        assertNotNull(idB);
        assertNotEquals(idA, idB);

        Customer removed = repository().save(
                Customer.newCustomer("Khách đã xóa"));
        Long missingId = removed.getId();
        synchronizeAndForget();
        repository().deleteById(missingId);
        synchronizeAndForget();

        List<Customer> found = materialize(repository().findAllById(
                List.of(idB, missingId, idA)));
        Set<Long> foundIds = found.stream()
                .map(Customer::getId)
                .collect(Collectors.toSet());

        assertEquals(2, found.size());
        assertEquals(Set.of(idA, idB), foundIds);
    }

    @Test
    void emptyStoreAndEmptyBulkInputProduceEmptyResults() {
        assertFalse(repository().findAll().iterator().hasNext());
        assertFalse(repository().findAllById(List.of())
                .iterator().hasNext());
        assertFalse(repository().saveAll(List.<Customer>of())
                .iterator().hasNext());
        assertEquals(0L, repository().count());
    }

    private static <E> List<E> materialize(Iterable<E> values) {
        List<E> result = new ArrayList<>();
        values.forEach(result::add);
        return result;
    }
}
```

### 5.1. Vì sao test cập nhật lại bỏ persistence context trước khi sửa?

Trong JPA, thay đổi một entity đang managed có thể được lưu nhờ dirty checking dù tác giả test vô tình bỏ lời gọi `save` mà mình định kiểm tra.

Ở test cập nhật, hook chạy sau khi tải entity và trước khi gọi `rename`. Với adapter JPA có `clear`, đối tượng trở thành detached trước khi được sửa. Việc đọc lại sau lần lưu tiếp theo vì vậy giảm nguy cơ chỉ nhìn thấy trạng thái còn nằm trong persistence context.

Điều này không có nghĩa mọi store đều có managed entity hoặc cần cùng một hook. Đó là chỗ adapter theo store phải diễn đạt khác biệt thực sự.

### 5.2. Một adapter JPA minh họa

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.repository.CrudRepository;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

@SpringJUnitConfig(JpaContractTestConfiguration.class)
@Transactional
class JpaCustomerCrudTest extends CustomerCrudContract {

    @Autowired
    private CustomerRepository customers;

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    protected CrudRepository<Customer, Long> repository() {
        return customers;
    }

    @Override
    protected void synchronizeAndForget() {
        entityManager.flush();
        entityManager.clear();
    }
}
```

`CustomerRepository` ở đây kế thừa `CrudRepository<Customer, Long>`. `JpaContractTestConfiguration` là cấu hình kiểm thử do dự án cung cấp, bao gồm datasource, entity manager, transaction manager, entity và repository scanning phù hợp. Không phải chỉ có tên lớp cấu hình là đủ để ví dụ tự chạy.

`flush` và `clear` giúp quan sát persistence chính xác hơn, nhưng test vẫn có thể chạy trong cùng một transaction được rollback sau mỗi ca. Nó chưa chứng minh commit cuối cùng hoặc khả năng quan sát từ transaction khác. Nếu yêu cầu cần kiểm tra những điều đó, phải có ca riêng với ranh giới transaction và cleanup tương ứng.

## 6. Kiểm thử kiểu trả về mà không khóa chặt implementation

### 6.1. `Optional<T>` biểu diễn vắng mặt

Với `CrudRepository.findById`, khi ID hợp lệ nhưng không có entity, kỳ vọng là `Optional.empty()`, không phải `null`.

```java
assertTrue(repository.findById(missingId).isEmpty());
```

Khi tồn tại, lấy entity rồi so sánh ID và thuộc tính cần thiết. Không so sánh toàn bộ entity chỉ để thay thế việc xác định điều gì cần đúng: `equals` có thể phụ thuộc ID, proxy, tập quan hệ hoặc cách domain định nghĩa bình đẳng.

### 6.2. `Iterable<T>` không phải cam kết `ArrayList<T>`

Đối với `CrudRepository`, dùng phép duyệt hoặc materialize sang danh sách do test tạo. Không kiểm thử bằng cách ép implementation của kết quả:

```java
// Không dựa vào kiểu collection cụ thể như thế này:
ArrayList<Customer> customers =
        (ArrayList<Customer>) repository.findAll();
```

Nếu API ứng dụng cần `List`, có thể chọn `ListCrudRepository` khi stack và store hỗ trợ, hoặc chuyển đổi tại tầng thích hợp. Theo [ListCrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/ListCrudRepository.html), các phương thức tương ứng khai báo `List`; điều đó vẫn không cam kết một lớp implementation cụ thể hay một thứ tự truy vấn mặc định.

### 6.3. Collection rỗng khác một collection chứa `null`

Một truy vấn không tìm thấy entity phải được phân biệt với kết quả có phần tử không hợp lệ. Đừng chỉ kiểm tra kích thước rồi bỏ qua nội dung, đặc biệt khi mapping qua projection hoặc DTO.

Với tập kết quả không có bảo đảm thứ tự, nên so sánh ID hoặc thuộc tính theo tập hợp, đồng thời kiểm tra số phần tử để không vô tình bỏ qua dữ liệu trùng. Chỉ so sánh `Set` có thể che mất việc một kết quả xuất hiện hai lần.

### 6.4. `List` không tự có thứ tự nghiệp vụ

`findAllById` không bảo đảm kết quả đi theo thứ tự của danh sách ID đầu vào. Nếu đưa vào `[idB, missingId, idA]`, không được mặc định phần tử đầu phải là B hay có một vị trí trống dành cho ID thiếu.

Nếu ứng dụng yêu cầu thứ tự cụ thể, hãy tạo hợp đồng sắp xếp rõ ràng bằng API được store hỗ trợ hoặc sắp xếp lại kết quả dựa trên yêu cầu. Khi kiểm thử phân trang hoặc truy vấn có sort, cần thêm khóa phụ ổn định nếu các giá trị sort chính có thể bằng nhau.

## 7. Bulk CRUD: đủ kết quả không đồng nghĩa một câu lệnh hoặc một transaction

Với `saveAll` của `CrudRepository`, kiểm thử có thể xác nhận số entity trả về phù hợp đầu vào hợp lệ, rồi đọc lại theo các ID trả về. Với `findAllById`, ID không tồn tại không tạo entity kết quả và thứ tự không được bảo đảm; xem [hợp đồng bulk và truy xuất ID](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

Những điều không nên tự suy ra từ tên `saveAll`:

- Chắc chắn chỉ có một câu SQL.
- Chắc chắn dùng một bulk API vật lý của store.
- Chắc chắn mọi store commit nguyên tử toàn bộ tập đầu vào.
- Chắc chắn callback hoặc auditing không được gọi cho từng entity.

Nếu ứng dụng cần tính nguyên tử khi một phần tử giữa tập thất bại, đó là ca kiểm thử transaction theo store và cấu hình cụ thể. Nếu cần giới hạn số truy vấn, đó là hợp đồng hiệu năng hoặc truy vấn riêng, không phải assertion CRUD chung mặc định.

Khi kiểm thử ID trùng trong đầu vào bulk, cần xác định hành vi được API và store bảo đảm. Không nhân bản kỳ vọng từ một trường hợp thử nghiệm tình cờ rồi coi nó là quy tắc phổ quát.

## 8. Xóa, đầu vào không hợp lệ và lỗi version

### 8.1. Xóa một ID không tồn tại

API `CrudRepository.deleteById` được dẫn ở bài này mô tả rằng entity không được tìm thấy sẽ được bỏ qua. Nếu phiên bản triển khai của ứng dụng có hợp đồng đó, có thể bổ sung ca xóa lại ID đã xóa:

```java
assertDoesNotThrow(() -> {
    repository.deleteById(missingId);
    synchronizeAndForget();
});
```

Đoạn trên được hiểu trong ngữ cảnh lớp test có hook tương ứng. Không mở rộng assertion này thành “mọi lời gọi xóa đều không thể lỗi”. Xóa entity có version, xung đột cạnh tranh, ràng buộc tham chiếu hoặc lỗi driver là những tình huống khác.

Nếu dùng release cũ hoặc API xóa riêng của module, phải đối chiếu đúng hợp đồng release đó thay vì sao chép kỳ vọng từ một phiên bản khác.

### 8.2. Đừng để thư viện tạo collection ném lỗi trước repository

Một sai sót khi tạo ca đầu vào chứa `null`:

```java
List<Customer> invalid = List.of(customer, null);
```

`List.of` đã từ chối `null`, nên test có thể thất bại trước khi gọi repository. Muốn kiểm tra hành vi của repository với một phần tử `null`, cần tạo fixture cho phép chứa giá trị đó, chẳng hạn:

```java
List<Customer> invalid = Arrays.asList(customer, null);
```

Sau đó mới đặt assertion quanh lời gọi repository. Cần phân biệt các trường hợp entity là `null`, ID là `null`, collection là `null` và collection có phần tử `null`; chúng không phải cùng một đầu vào.

Javadoc có thể khai báo `IllegalArgumentException` cho đầu vào sai, trong khi lớp proxy hoặc exception translation của module có thể làm kiểu lỗi quan sát ở ranh giới tích hợp khác đi. Hãy xác định ranh giới đang kiểm thử và assertion đúng theo hạ tầng đó. Tránh assertion quá rộng như “ném bất kỳ RuntimeException nào cũng được”, vì lỗi kết nối không chứng minh validation hoạt động.

### 8.3. Version là một phần của hợp đồng khi mapping sử dụng nó

Với optimistic locking được hỗ trợ và đã cấu hình, một kịch bản có ý nghĩa là:

1. Tải entity để giữ một bản sao version cũ.
2. Cập nhật entity trong một đơn vị công việc khác và hoàn tất thay đổi.
3. Thử lưu bản sao cũ.
4. Xác nhận lỗi cạnh tranh theo abstraction lỗi của module và ranh giới API.
5. Đọc lại để bảo đảm thay đổi thành công trước đó không bị ghi đè.

Không chỉ gán một giá trị version tùy ý rồi suy ra đã mô phỏng đầy đủ hai người dùng cạnh tranh. Đồng thời, lỗi có thể xuất hiện khi flush hoặc commit thay vì ngay tại `save`; vị trí assertion phải bao được thời điểm thực tế.

Sau lỗi persistence làm transaction không còn dùng được, không tiếp tục xác minh bằng cách ghi thêm trong cùng transaction rồi coi kết quả đó đáng tin cậy. Thiết kế ca kiểm thử cần có ranh giới phục hồi phù hợp.

## 9. Chuyển hợp đồng sang repository reactive

Với `ReactiveCrudRepository`, khác biệt không chỉ là thay kiểu khai báo. Kết quả được quan sát bằng tín hiệu của publisher:

| Thao tác | Kiểu cơ bản | Điều cần quan sát |
| --- | --- | --- |
| `save` | `Mono<T>` | Entity đã lưu được phát ra rồi hoàn tất, hoặc báo lỗi |
| `findById` | `Mono<T>` | Có một entity, hoặc hoàn tất rỗng khi không tìm thấy |
| `findAll`, `saveAll` | `Flux<T>` | Các entity và tín hiệu kết thúc |
| `existsById` | `Mono<Boolean>` | Giá trị boolean được phát ra |
| `count` | `Mono<Long>` | Số lượng được phát ra |
| `deleteById` | `Mono<Void>` | Hoàn tất hoặc báo lỗi; không chờ một giá trị `Void` |

Đối chiếu chữ ký và tín hiệu với [ReactiveCrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/ReactiveCrudRepository.html).

### 9.1. Dùng StepVerifier để quan sát cả giá trị và hoàn tất

Giả sử `reactiveRepository` là repository thật của store reactive được chọn, kho test đã được cô lập và fixture `Customer` phù hợp mapping của store đó:

```java
Mono<String> savedName = reactiveRepository
        .save(Customer.newCustomer("Khách reactive"))
        .flatMap(saved -> {
            assertNotNull(saved.getId());
            return reactiveRepository.findById(saved.getId());
        })
        .map(Customer::getName);

StepVerifier.create(savedName)
        .expectNext("Khách reactive")
        .verifyComplete();
```

Đoạn test dùng `reactor.core.publisher.Mono`, `reactor.test.StepVerifier` và assertion của JUnit Jupiter. `expectNext` giúp ca test thất bại nếu bước tìm theo ID chỉ hoàn tất rỗng thay vì trả entity.

Không chỉ kiểm tra publisher khác `null` rồi kết luận đã kiểm thử lưu dữ liệu. Với pipeline lazy thông thường, chưa subscribe thì công việc có thể chưa thực thi.

### 9.2. Kiểm thử xóa bằng completion và truy vấn lại

```java
Mono<Customer> afterDelete = reactiveRepository
        .save(Customer.newCustomer("Khách sẽ xóa"))
        .switchIfEmpty(Mono.error(new AssertionError(
                "save phải phát ra entity đã lưu")))
        .flatMap(saved -> {
            assertNotNull(saved.getId());
            return reactiveRepository.deleteById(saved.getId())
                    .then(reactiveRepository.findById(saved.getId()));
        });

StepVerifier.create(afterDelete)
        .verifyComplete();
```

Ca này mong pipeline không phát entity sau xóa và hoàn tất thành công. Nếu entity vẫn còn, StepVerifier nhận một giá trị ngoài kỳ vọng và test thất bại.

Không dùng `.subscribe()` rồi assertion ngay ở dòng tiếp theo, vì công việc có thể chưa hoàn tất. Cũng không đặt `expectNext(null)` cho `Mono<Void>`: reactive không biểu diễn thành công bằng một phần tử `null`.

Đầu vào không hợp lệ có thể gây lỗi ngay khi gọi API hoặc được quan sát khi subscribe, tùy phương thức và implementation. Khi cần kiểm tra lỗi trong một luồng tín hiệu thống nhất, có thể trì hoãn lời gọi bằng `Mono.defer`, rồi assertion loại lỗi thích hợp; tránh bỏ sót việc chưa subscribe.

## 10. Chọn những assertion thực sự giúp phát hiện lỗi

| Assertion hoặc cách làm | Vấn đề | Cách diễn đạt tốt hơn |
| --- | --- | --- |
| Chỉ verify mock đã được gọi | Không quan sát store | Kiểm thử repository thật khi mục tiêu là persistence |
| ID đầu tiên phải bằng 1 | Phụ thuộc generator và trạng thái môi trường | ID hợp lệ, đọc lại đúng entity |
| Entity đầu vào và trả về phải cùng reference | Khóa vào implementation | Dùng entity trả về và so sánh thuộc tính cần thiết |
| Collection phải là ArrayList | Không thuộc hợp đồng abstraction | Duyệt Iterable hoặc dùng kiểu API khai báo |
| `findAllById` phải theo thứ tự input | Không có bảo đảm đó | So sánh nội dung không phụ thuộc thứ tự |
| Chỉ so sánh Set ID | Có thể che dữ liệu trùng | Kiểm tra thêm số phần tử |
| Chỉ thấy entity trong persistence context | Có thể chưa chứng minh mapping hoặc câu ghi | Đồng bộ, bỏ context khi phù hợp rồi đọc lại |
| `saveAll` phải tạo một câu SQL | Trộn hợp đồng CRUD với hiệu năng | Tách ca hiệu năng theo store nếu có yêu cầu |
| Publisher khác null là đủ | Chưa quan sát thực thi | Subscribe bằng công cụ test và xác nhận terminal signal |
| Mọi lỗi đều được coi là validation đúng | Che lỗi hạ tầng hoặc mapping | Assertion đúng loại lỗi tại ranh giới đã chọn |

Auditing, projection, derived queries và phân trang có thể mở rộng bộ kiểm thử theo nhu cầu ứng dụng. Tuy nhiên, nên giữ mục tiêu mỗi ca rõ ràng: CRUD kiểm tra vòng đời dữ liệu và ID; truy vấn kiểm tra điều kiện và cardinality; auditing kiểm tra metadata; transaction kiểm tra phạm vi commit hoặc rollback.

Một bộ kiểm thử hợp đồng tốt giúp đổi cấu hình hoặc nâng cấp module mà vẫn phát hiện được những thay đổi tác động tới ứng dụng. Nó làm rõ điều repository hứa bảo đảm, điều mapping của dự án yêu cầu và điều phải kiểm chứng riêng trên từng store, thay vì biến các hành vi tình cờ của một lần chạy thành luật chung.
