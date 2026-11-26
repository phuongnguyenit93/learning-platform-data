# Projection đóng, projection mở và giới hạn tối ưu

Một API chỉ trả ID và họ tên không nhất thiết chỉ tải ID và họ tên từ kho dữ liệu. Ứng dụng có thể đã đọc toàn bộ entity, sau đó mới chuyển thành một đối tượng nhỏ trước khi trả kết quả. Projection giúp mô tả dữ liệu đọc cần thiết, nhưng mức tối ưu thực tế còn phụ thuộc loại projection, truy vấn, mapping và store.

Trong chương **Hiệu năng** của module **SPRING_DATA_COMMONS**, bài học này tập trung vào projection đóng, projection mở và những giới hạn của việc suy luận hiệu năng từ kiểu trả về. Repository, derived query, phân trang, sắp xếp và projection là các abstraction phối hợp với nhau; Spring Data Commons không tự cung cấp một kế hoạch thực thi giống nhau cho mọi kho dữ liệu.

## 1. Phân biệt dữ liệu cần dùng với dữ liệu thực sự được tải

Giả sử danh sách nhân sự cần:

```text
id
fullName
```

Trong khi entity `Person` còn có:

```text
firstName, lastName, tenantId, active, createdAt,
profileNotes, avatar, address và các thuộc tính khác
```

Có ít nhất bốn tầng chi phí cần phân biệt:

1. Store tìm những bản ghi nào: lọc, index, join và sort.
2. Store trả những trường nào: độ rộng dữ liệu và số bản ghi truyền đi.
3. Ứng dụng dựng những đối tượng nào: entity, tuple, DTO hoặc projection proxy.
4. Ứng dụng truy cập và chuyển đổi kết quả ra sao: getter, SpEL, quan hệ và serialization.

Một thay đổi chỉ làm response JSON nhỏ hơn có thể cải thiện tầng cuối nhưng chưa giảm được ba tầng trước. Ngược lại, một projection giới hạn select có thể giảm dữ liệu truyền và mapping nhưng không làm một bộ lọc thiếu index trở nên rẻ.

```text
Repository method
       |
       v
Store module phân tích query và kiểu kết quả
       |
       v
Kế hoạch truy vấn cùng dữ liệu được chọn
       |
       v
Mapping thành entity, DTO hoặc proxy
       |
       v
Gọi accessor, tính toán, tạo response
```

Muốn đánh giá tối ưu, cần quan sát cả chuỗi này thay vì chỉ đếm số getter trên interface.

## 2. Projection đóng: tập thuộc tính đầu vào có thể xác định

Projection đóng là interface có các accessor ánh xạ tới thuộc tính của aggregate mục tiêu. Ví dụ:

```java
public interface PersonNameView {

    Long getId();

    String getFirstName();

    String getLastName();
}
```

Giả định entity `Person` thực sự có các thuộc tính `id`, `firstName` và `lastName` tương ứng. Spring Data có thể biết tập dữ liệu cần thiết để dựng view này và store module có thể dùng thông tin đó để tối ưu truy vấn. Đây là cơ hội tối ưu được mô tả trong [projection của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.closed).

### 2.1. Ví dụ repository với derived query

Giả định phần minh họa dùng Spring Data JPA, mapping entity và hạ tầng repository đã được cấu hình:

```java
import org.springframework.data.repository.Repository;

import java.util.List;

public interface PersonRepository extends Repository<Person, Long> {

    List<PersonNameView> findNamesByTenantIdAndActiveTrue(Long tenantId);
}
```

Ý nghĩa cần giữ rõ:

- Điều kiện truy vấn là tenant và active.
- Kiểu phần tử trả về là projection đóng.
- Module JPA quyết định cách dựng truy vấn và projection tương ứng.

Một hình dạng SQL có thể kỳ vọng trong trường hợp đơn giản là:

```sql
SELECT p.id, p.first_name, p.last_name
FROM person p
WHERE p.tenant_id = ?
  AND p.active = true;
```

Đây là minh họa hình dạng truy vấn, không phải lời hứa rằng mọi provider hoặc mọi store sẽ sinh đúng câu lệnh này. Mapping, query được khai báo, phiên bản và kỹ thuật thực thi có thể làm khác đi.

### 2.2. Đóng không có nghĩa truy vấn chỉ được dùng các trường trả về

Trường `tenantId` hoặc `active` vẫn có thể tham gia điều kiện lọc dù không có getter trong projection. Cột phục vụ index, sort hoặc join cũng có thể ảnh hưởng kế hoạch thực thi.

Giới hạn dữ liệu trả về và giới hạn lượng công việc store phải thực hiện là hai việc liên quan nhưng không đồng nhất.

## 3. Giá trị tính toán đơn giản có thể dùng default method

Nếu họ tên chỉ được ghép từ hai thuộc tính đã có trong projection, có thể đặt một default method thuần tính toán:

```java
public interface PersonNameView {

    Long getId();

    String getFirstName();

    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Ví dụ giả định hai phần tên không null. Nếu domain cho phép null hoặc chuỗi trống, phải định nghĩa quy tắc định dạng tương ứng thay vì coi phép nối chuỗi này là quy tắc tên đầy đủ cho mọi ứng dụng.

Default method trên chỉ dựa vào các accessor đã được công bố, nên không yêu cầu một thuộc tính entity chưa được xác định. Đây là hướng phù hợp khi logic có thể thực hiện hoàn toàn từ tập đầu vào của projection.

Tuy nhiên:

- Không có bảo đảm rằng mọi lần gọi getter đều được memoize.
- Default method chứa công việc tốn CPU vẫn có thể làm bước đọc kết quả chậm.
- Nếu accessor trả một quan hệ phức tạp, truy cập quan hệ đó cần được đánh giá riêng.

Lợi ích đến từ việc giữ tập dữ liệu phụ thuộc rõ ràng và phép tính đơn giản, không đến từ từ khóa `default` một cách tự động.

## 4. Projection mở: SpEL có thể sử dụng trạng thái khó suy luận

Projection mở dùng biểu thức `@Value` để tính kết quả, chẳng hạn:

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplayView {

    Long getId();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
```

`target` đại diện cho đối tượng nguồn được dùng để tính projection. Biểu thức nhìn đơn giản trong ví dụ, nhưng SpEL còn có thể truy cập thuộc tính khác, điều hướng quan hệ hoặc gọi bean.

Spring Data không thể dựa vào tập accessor như với projection đóng để suy ra đầy đủ mọi thuộc tính mà biểu thức tùy ý sẽ cần. Vì vậy, không có cùng cơ hội tự động giới hạn dữ liệu dựa trên phân tích projection theo cách đó. Xem [projection mở và SpEL](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.open).

### 4.1. Điều không nên suy ra quá mức

Không nên biến nhận định trên thành các kết luận tuyệt đối như:

- Mọi projection mở luôn chạy chậm hơn mọi projection đóng.
- Mọi projection mở bắt buộc tạo đúng một kiểu `SELECT *` giống nhau.
- Projection mở làm mất toàn bộ tối ưu index hoặc điều kiện lọc.

Truy vấn có thể vẫn lọc tốt, dùng index và có một tập trường được chỉ định rõ bởi cơ chế khác. Điều bị hạn chế ở đây là khả năng suy luận tập thuộc tính cần tải chỉ từ projection chứa biểu thức tùy ý.

Nếu một query hoặc mapping đã chủ động chọn dữ liệu đầu vào, biểu thức vẫn phải tương thích với dữ liệu đó. Nó không thể đọc một thuộc tính không được cung cấp chỉ vì accessor có `@Value`.

### 4.2. Đưa SpEL sang bean không khôi phục khả năng suy luận tự động

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonLabelView {

    Long getId();

    @Value("#{@personLabelFormatter.format(target)}")
    String getLabel();
}
```

Cách này giúp tổ chức logic tốt hơn một chuỗi SpEL dài, nhưng không làm dependency dữ liệu của `format(target)` trở thành tập thuộc tính tĩnh mà projection tự công bố.

Nếu formatter đọc thêm quan hệ hoặc gọi repository, quá trình lấy label có thể tạo thêm I/O cho từng phần tử. Chuyển code vào bean cải thiện nơi đặt logic; chi phí truy cập dữ liệu vẫn phải được đo.

## 5. So sánh các lựa chọn theo dữ liệu và chi phí

| Lựa chọn | Cách xác định đầu vào | Cơ hội tối ưu dữ liệu đọc | Điều còn phải kiểm tra |
| --- | --- | --- | --- |
| Entity đầy đủ | Mapping entity và query | Phụ thuộc mapping, fetch plan và query | Entity nào được materialize, quan hệ và dirty tracking |
| Interface đóng | Các thuộc tính accessor | Store có thể giới hạn dữ liệu từ tập thuộc tính biết trước | Query thực tế, nested property và hỗ trợ module |
| Interface đóng có default method thuần | Accessor cùng logic chỉ dùng các accessor đó | Có thể giữ cơ hội tương tự tập thuộc tính gốc | CPU, số lần gọi và null handling |
| Interface mở dùng SpEL | Biểu thức có thể dùng target hoặc bean | Không suy ra đầy đủ dependency bằng cách đóng thông thường | Dữ liệu nguồn, I/O phát sinh và evaluation |
| DTO hoặc record projection | Constructor và truy vấn phù hợp | Có thể chọn tập trường cụ thể theo store | Constructor, kiểu cột, query và mapping |
| Map entity sang DTO sau khi đã đọc | Logic ứng dụng sau bước query | Không thu hồi được chi phí dữ liệu đã tải trước đó | Fetch plan ban đầu và số đối tượng tạo thêm |

Không có lựa chọn nào loại bỏ nhu cầu xác định số bản ghi, điều kiện và giới hạn kích thước kết quả.

### 5.1. Một ước lượng chỉ để nhận diện chi phí có thể giảm

Giả định minh họa, chưa phải kết quả benchmark:

```text
1.000 bản ghi

Dữ liệu truyền trung bình nếu tải rộng: khoảng 4 KiB/bản ghi
Dữ liệu truyền trung bình khi chỉ lấy trường cần: khoảng 128 byte/bản ghi

Phần dữ liệu bản ghi tương ứng:
- Khoảng 3,9 MiB
- Khoảng 0,12 MiB
```

Ước lượng này chỉ minh họa tác động của độ rộng dữ liệu. Nó chưa tính protocol, encoding, nén, index scan, bộ nhớ object hay thời gian truy vấn. Không dùng nó để tuyên bố một API sẽ nhanh hơn theo đúng tỷ lệ đó.

## 6. DTO và truy vấn tường minh khi cần kiểm soát tập trường

DTO dạng record có thể diễn đạt đầu vào rõ ràng:

```java
package com.example.readmodel;

public record PersonNameDto(
        Long id,
        String firstName,
        String lastName) {

    public String fullName() {
        return firstName + " " + lastName;
    }
}
```

Với Spring Data JPA, một constructor expression tường minh có thể dùng:

```java
import com.example.readmodel.PersonNameDto;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface PersonReadRepository extends Repository<Person, Long> {

    @Query("""
        select new com.example.readmodel.PersonNameDto(
            p.id, p.firstName, p.lastName)
        from Person p
        where p.tenantId = :tenantId
          and p.active = true
        """)
    List<PersonNameDto> findNameDtos(@Param("tenantId") Long tenantId);
}
```

Ví dụ giả định entity JPA có tên `Person` và các thuộc tính tương ứng. Đây là cách chọn cho ví dụ JPA, không phải cú pháp truy vấn dùng chung cho MongoDB, JDBC, R2DBC hoặc mọi module khác.

DTO không dùng interface proxy theo cùng cơ chế projection interface và không tự cung cấp recursive projection interface. Constructor phải phù hợp dữ liệu mà query trả về; với DTO nhiều constructor cần chỉ dẫn thích hợp theo API và module.

### 6.1. Interface projection với select và alias rõ ràng

Một lựa chọn JPA khác:

```java
@Query("""
    select p.id as id,
           p.firstName as firstName,
           p.lastName as lastName
    from Person p
    where p.tenantId = :tenantId
      and p.active = true
    """)
List<PersonNameView> findExplicitNames(@Param("tenantId") Long tenantId);
```

Đoạn này nằm trong một repository có các import JPA `Query` và `Param` tương ứng. Alias phải ánh xạ đúng tới accessor của interface.

Không chuyển nguyên xi alias dành cho interface vào một constructor expression rồi mặc định cú pháp và mapping vẫn giống nhau. Chi tiết cách JPA dựng tuple, DTO và query rewriting được mô tả trong [projection với Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa).

Cũng không nên dựa vào khả năng rewriting ở một phiên bản để khẳng định mọi query khai báo bằng chuỗi đều tự được thu hẹp theo DTO trên mọi stack. Khi cần kiểm soát, hãy đọc query thực tế và kiểm tra mapping của release đang dùng.

## 7. Nested projection không tự bảo đảm chỉ tải từng trường nhỏ

Ví dụ:

```java
public interface PersonWithCityView {

    Long getId();

    String getFirstName();

    AddressCityView getAddress();

    interface AddressCityView {
        String getCity();
    }
}
```

Nhìn vào Java, view chỉ cần một thuộc tính của address. Nhưng kết quả ở tầng lưu trữ còn phụ thuộc address là embedded value, document lồng nhau hay một quan hệ tới entity khác.

Trong JPA, giới hạn projection đặc biệt gắn với các thuộc tính top-level. Nested property phải giải quyết bằng join có thể làm phần quan hệ được materialize rộng hơn những gì số getter gợi ý. Tài liệu JPA nêu rõ giới hạn này; không coi `getCity()` là bằng chứng chắc chắn rằng chỉ một cột city của quan hệ được tải.

### 7.1. Quan sát cả số query sau khi gọi getter

Một phép đo chỉ gọi repository rồi dừng có thể bỏ sót I/O khi:

- Gọi nested getter.
- Đánh giá biểu thức SpEL điều hướng quan hệ.
- Formatter truy cập thêm dữ liệu.
- Serializer duyệt các accessor hoặc cấu trúc con.

Với N phần tử, nếu mỗi phần tử phát sinh một truy vấn phụ để lấy quan hệ, ứng dụng có thể gặp hình dạng N+1. Projection không tự chữa mọi vấn đề fetch plan.

Không phải mọi nested projection đều gây N+1; một query join hoặc cách mapping khác có thể xử lý trong cùng lượt truy cập. Cần kiểm tra đường thực thi thực tế trước khi kết luận.

### 7.2. Khi dữ liệu cần dùng là phẳng, cân nhắc query phẳng

Nếu màn hình chỉ cần ID, họ tên và city, một DTO phẳng với query chọn đúng các thành phần có thể dễ đánh giá hơn một chuỗi proxy lồng nhau. Với JPA, lựa chọn left join hay inner join còn quyết định bản ghi không có address có bị loại hay không.

Tối ưu phải giữ đúng ngữ nghĩa. Một câu query nhanh hơn vì vô tình bỏ mất người chưa có địa chỉ không phải cải thiện hợp lệ cho cùng hợp đồng.

## 8. Những giới hạn projection không giải quyết thay

### 8.1. Điều kiện lọc và index

Nếu truy vấn phải quét nhiều dữ liệu do điều kiện hoặc index chưa phù hợp, giảm số trường trả về có thể chưa tác động đáng kể tới thời gian tổng. Ngược lại, một query đã lọc tốt có thể hưởng lợi rõ khi tránh tải các trường lớn.

Không tự thêm index chỉ dựa trên số getter projection. Index cần được thiết kế theo workload, độ chọn lọc, điều kiện, thứ tự và đặc tính store.

### 8.2. Sort, join và tổng số phần tử

Projection hẹp không loại bỏ chi phí sort hoặc join. Sort theo một thuộc tính không trả ra vẫn có thể ảnh hưởng đáng kể kế hoạch thực thi.

Một phương thức trả `Page` có thể cần truy vấn count để biết tổng số phần tử. Nếu count là phần đắt nhất, đổi entity sang projection không tự loại bỏ chi phí đó. `Slice` hoặc một kiểu kết quả không cần tổng có thể phù hợp khi hợp đồng giao diện cho phép, nhưng đó là quyết định API riêng.

### 8.3. Số lượng kết quả và bộ nhớ

Tải hàng triệu projection nhỏ vào một `List` vẫn có thể gây áp lực bộ nhớ. Cần giới hạn số phần tử hoặc dùng cơ chế phân trang, scroll hay streaming được store hỗ trợ.

Publisher reactive cũng không bảo đảm toàn bộ đường dữ liệu luôn có bộ nhớ hữu hạn: thu gom tất cả phần tử thành một collection vẫn có chi phí tương ứng. Projection chỉ là một phần của thiết kế đọc dữ liệu.

### 8.4. Cache và trạng thái persistence

Cache có thể làm phép đo entity nhanh bất thường, hoặc làm một so sánh trước và sau không cùng điều kiện. Nếu benchmark projection khi cache lạnh nhưng benchmark entity khi cache nóng, kết luận khó phản ánh tác động riêng của projection.

Tách điều kiện cache lạnh và cache ấm theo mục tiêu đo; không dùng một con số thiếu ngữ cảnh để chọn kiểu kết quả cho mọi màn hình.

### 8.5. Trường không trả ra vẫn có thể đã được tải

Một interface chỉ công bố ID và label không chứng minh những trường khác chưa từng có mặt trong bộ nhớ. Nếu yêu cầu cần giới hạn dữ liệu thực sự được đọc, phải kiểm tra select hoặc projection document của store và toàn bộ đường truy cập dữ liệu.

Projection là công cụ mô hình hóa dữ liệu đọc; phân quyền theo dòng hoặc theo trường vẫn cần cơ chế phù hợp của ứng dụng và store.

## 9. Không tối ưu bằng cách chỉ đổi lớp bọc sau truy vấn

Ví dụ về bước chuyển đổi xảy ra sau khi đã yêu cầu entity:

```java
List<PersonNameDto> names = people
        .findByTenantIdAndActiveTrue(tenantId, Person.class)
        .stream()
        .map(person -> new PersonNameDto(
                person.getId(), person.getFirstName(), person.getLastName()))
        .toList();
```

Đoạn này giả định repository có dynamic projection method tương ứng. Đối tượng DTO nhỏ có thể hữu ích ở tầng ứng dụng, nhưng bước map không thu hồi được chi phí dữ liệu mà truy vấn entity đã tải trước đó.

Tương tự, tạo proxy projection từ một entity đã materialize chỉ thay cách nhìn đối tượng hiện có; nó không quay ngược thời gian để sửa query đã chạy.

### 9.1. Dynamic projection cần đo theo kiểu được chọn

Một repository có thể khai báo:

```java
<T> List<T> findByTenantIdAndActiveTrue(Long tenantId, Class<T> type);
```

Các lời gọi khác nhau:

```java
people.findByTenantIdAndActiveTrue(tenantId, Person.class);
people.findByTenantIdAndActiveTrue(tenantId, PersonNameView.class);
people.findByTenantIdAndActiveTrue(tenantId, PersonDisplayView.class);
people.findByTenantIdAndActiveTrue(tenantId, PersonNameDto.class);
```

Cùng điều kiện tìm kiếm không có nghĩa các kiểu được chọn tạo cùng cách materialize và cùng chi phí. Cần xác nhận hỗ trợ của module và query cho từng loại kết quả.

### 9.2. Không ép base CRUD method trở thành projection chỉ bằng kiểu trả về

Các phương thức base của repository không mặc định trở thành projection query khi được khai báo lại với một kiểu mong muốn. Chữ ký Java còn phải tương thích, và đường xử lý base method có thể vẫn được dùng.

Nên tạo query method riêng có ý nghĩa rõ, hoặc dùng cơ chế truy vấn tường minh mà module hỗ trợ. Không xem việc sửa kiểu trả về của `findById` hoặc một base method là một tối ưu chung được bảo đảm.

## 10. Đo projection bằng cùng một hợp đồng đầu ra

Một phép so sánh có ích cần giữ cùng:

- Tenant, bộ lọc, dữ liệu và số phần tử.
- Thứ tự, page size và vị trí trang.
- Mức cạnh tranh và cấu hình kết nối.
- Chính sách cache, transaction và fetch.
- Dữ liệu đầu ra mà bên gọi thực sự cần.

Ví dụ, nếu interface đóng công bố firstName, lastName và fullName, còn interface mở chỉ công bố fullName, việc serialize trực tiếp hai interface có thể tạo hai response khác nhau. Khi so sánh cho cùng API, có thể chuyển cả hai về một response chuẩn:

```java
public record PersonListRow(Long id, String fullName) {
}
```

Cần tính bước chuyển đổi tương ứng trong đường đo, đồng thời theo dõi dữ liệu đã tải ở phía trước.

### 10.1. Những đại lượng nên quan sát

| Đại lượng | Câu hỏi nó giúp trả lời |
| --- | --- |
| Câu lệnh hoặc yêu cầu gửi tới store | Có giới hạn tập trường như mong muốn không? |
| Số lượt truy cập dữ liệu | Có query phụ khi getter hoặc serializer chạy không? |
| Số bản ghi và độ rộng dữ liệu trả về | Có giảm tải truyền và mapping không? |
| Kế hoạch thực thi | Chi phí chính nằm ở scan, join hay sort? |
| Allocation và heap | Có tránh được object hoặc trường lớn không? |
| CPU phía ứng dụng | SpEL, formatter hoặc serialization có chiếm đáng kể không? |
| Độ trễ và phân vị dưới tải phù hợp | Tác động có còn thấy ở điều kiện thực tế không? |

Không cần biến mọi test chức năng thành benchmark. Khi có một giả thuyết hiệu năng cụ thể, hãy đo phần đường đi liên quan với dữ liệu đủ đại diện và điều kiện lặp lại được.

### 10.2. Một quy trình thử nghiệm có mục tiêu

1. Chọn một truy vấn đọc thường xuyên và ghi rõ dữ liệu đầu ra cần thiết.
2. Quan sát query và toàn bộ getter thực sự được tiêu thụ.
3. So sánh entity, projection đóng hoặc DTO trong cùng điều kiện.
4. Nếu đang dùng projection mở chỉ để nối chuỗi, thử default method thuần hoặc mapping DTO với cùng ngữ nghĩa.
5. Đọc kế hoạch và đo lại để xác định bottleneck còn lại.
6. Kiểm tra tính đúng đắn: số bản ghi, null, tenant, sort và page phải giữ nguyên.

Nếu query count hoặc join vẫn chiếm phần lớn độ trễ, bước tối ưu tiếp theo phải hướng vào chi phí đó. Không tiếp tục đổi tên interface chỉ vì nó đã được gọi là projection.

## 11. Chọn cách triển khai theo nhu cầu dữ liệu

| Nhu cầu | Điểm bắt đầu hợp lý | Điều cần xác nhận |
| --- | --- | --- |
| Danh sách chỉ cần vài thuộc tính gốc | Projection đóng hoặc DTO | Module có thu hẹp dữ liệu đọc không |
| Giá trị ghép từ các trường đã chọn | Default method thuần hoặc mapping DTO | Null handling và chi phí tính toán |
| Logic hiển thị cần dữ liệu hoặc bean ngoài tập trường | Cân nhắc projection mở hoặc tách dịch vụ tạo read model | Dependency, I/O và số lần gọi |
| Báo cáo phẳng qua nhiều quan hệ | Query và DTO tường minh phù hợp store | Join, cardinality, count và mapping |
| Cần sửa entity theo nghiệp vụ | Entity và ranh giới transaction thích hợp | Không dùng read projection để thay ngữ nghĩa cập nhật |
| Cần giảm trường lớn hoặc dữ liệu đọc ngoài nhu cầu | Tập trường truy vấn tường minh hoặc projection được xác minh | Dữ liệu thực sự được store trả về |

Projection đóng tạo cơ hội xác định trước dữ liệu cần cho view. Projection mở tăng tính linh hoạt của tính toán nhưng làm việc suy luận dependency khó hơn. Hiệu năng cuối cùng phải được đánh giá qua truy vấn, mapping và cách kết quả được sử dụng trên từng store; kiểu Java nhỏ chỉ là điểm bắt đầu của việc tối ưu.
