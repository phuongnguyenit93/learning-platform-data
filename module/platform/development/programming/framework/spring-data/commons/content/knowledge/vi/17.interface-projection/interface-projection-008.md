# Giới hạn tối ưu truy vấn của projection mở

## Mục tiêu bài học

Một projection chỉ công khai hai getter chưa chắc khiến cơ sở dữ liệu chỉ đọc hai trường. Với projection mở, biểu thức SpEL có thể cần nhiều dữ liệu hơn những gì chữ ký interface thể hiện, nên Spring Data không thể áp dụng cùng cách suy ra tập thuộc tính cần lấy như với projection đóng.

Sau bài học, bạn có thể:

- Giải thích giới hạn tối ưu xuất phát từ metadata của projection mở.
- Phân biệt kích thước phản hồi API, dữ liệu query lấy và chi phí xử lý getter.
- Nhận diện ảnh hưởng của quan hệ, helper bean và thời điểm đánh giá biểu thức.
- Chọn closed projection, default method, DTO hoặc query khai báo phù hợp.
- Xác định những bằng chứng cần quan sát khi đánh giá hiệu năng trên một store cụ thể.

Bài thuộc chương **Projection interface** của module **SPRING_DATA_COMMONS**. Commons cung cấp abstraction và metadata cho repository/projection; module lưu trữ quyết định cách tạo truy vấn, chọn trường và ánh xạ kết quả. Các ví dụ chỉ áp dụng khi module hỗ trợ dạng projection và query tương ứng.

## 1. Giới hạn nằm ở việc suy ra dữ liệu đầu vào

Xét aggregate đã được mapping hợp lệ:

```text
Customer
├── id: Long
├── tenantId: String
├── active: boolean
├── givenName: String
├── familyName: String
├── biography: String
└── address: Address
```

Màn hình danh sách cần id và tên hiển thị. Giả sử hai thuộc tính tên đều khác null để tập trung vào vấn đề tối ưu.

### 1.1. Projection đóng cho biết rõ các thuộc tính cần đọc

```java
public interface CustomerNameFields {

    Long getId();

    String getGivenName();

    String getFamilyName();
}
```

Các accessor khớp thuộc tính domain. Hạ tầng biết những giá trị cần có để phục vụ interface này.

Module có thể dùng thông tin đó để giới hạn dữ liệu được lấy. “Có thể” không phải cam kết rằng mọi query, mapping và store đều tạo đúng một dạng truy vấn tối thiểu.

### 1.2. Projection mở mô tả một phép tính

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerOpenLabel {

    Long getId();

    @Value("#{target.givenName + ' ' + target.familyName}")
    String getLabel();
}
```

`label` không phải property có sẵn trong domain. Nó được tính bằng SpEL khi phương thức projection được gọi.

Người đọc biểu thức này thấy cần hai thuộc tính tên. Tuy nhiên, hợp đồng của open projection không phải một trình phân tích dependency đầy đủ cho mọi biểu thức SpEL. Biểu thức còn có thể gọi method, đi qua quan hệ hoặc chuyển toàn bộ nguồn cho một bean.

Tài liệu Spring Data Commons nêu rõ projection mở không nhận được tối ưu truy vấn dựa trên việc biết đầy đủ các thuộc tính cần cho proxy, vì biểu thức có thể dùng bất kỳ thuộc tính nào của aggregate. Xem [closed và open projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

### 1.3. Một biểu thức đơn giản vẫn là open projection

Ví dụ sau trông giống một getter thông thường:

```java
@Value("#{target.givenName}")
String getLabel();
```

Nhưng nó vẫn là một phương thức dùng `@Value`. Không dựa vào việc biểu thức ngắn hoặc chỉ nhắc một property để khẳng định Spring Data sẽ xử lý nó như closed projection.

Tương tự, bỏ các getter khác khỏi interface không chứng minh dữ liệu nguồn được tải ít hơn.

## 2. Hiểu metadata thay vì đếm getter

Trong Commons, `ProjectionInformation` mô tả projection. Hai khái niệm quan trọng là:

- `getInputProperties()`: thông tin về các property đầu vào được nhận diện.
- `isClosed()`: việc cung cấp các property đầu vào đó có đủ để tạo một proxy hoạt động hay không.

Với projection mở, danh sách accessor thông thường không biểu diễn toàn bộ dependency tiềm năng của các phương thức tính bằng biểu thức.

Có thể minh họa metadata mà không chạy query:

```java
import org.springframework.data.projection.SpelAwareProxyProjectionFactory;

SpelAwareProxyProjectionFactory factory =
        new SpelAwareProxyProjectionFactory();

boolean closed = factory
        .getProjectionInformation(CustomerNameFields.class)
        .isClosed();

boolean open = factory
        .getProjectionInformation(CustomerOpenLabel.class)
        .isClosed();

System.out.println(closed); // true
System.out.println(open);   // false
```

Đoạn mã minh họa sự phân loại interface, không xác minh câu SQL hay số trường MongoDB thực tế được trả.

Ý nghĩa của `isClosed()` được mô tả trong [API ProjectionInformation](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/projection/ProjectionInformation.html). Metadata là đầu vào để module ra quyết định; nó không phải bản kế hoạch thực thi của database.

## 3. Ba tập dữ liệu thường bị nhầm thành một

Với `CustomerOpenLabel`, cần phân biệt:

| Tập dữ liệu | Ví dụ |
| --- | --- |
| Những giá trị biểu thức cần để tính kết quả | `givenName`, `familyName` |
| Những giá trị query thực sự lấy và ánh xạ | Phụ thuộc query, store và fetch behavior |
| Những giá trị phản hồi API công khai | Có thể chỉ gồm `id`, `label` |

Một phản hồi JSON ngắn chỉ nói về đầu ra ở cuối luồng.

```text
Database/store
    → dữ liệu query trả về
    → đối tượng nguồn của projection
    → getter tính toán
    → DTO hoặc serializer
    → phản hồi API
```

Giảm field ở bước cuối không tự làm những bước trước ít công việc hơn.

### 3.1. Mô hình chi phí theo độ rộng kết quả

Giả sử, chỉ để tính minh họa:

- Một kết quả nguồn rộng có khoảng 6.000 byte dữ liệu cho mỗi khách hàng.
- Một kết quả chỉ chứa id và hai thành phần tên có khoảng 120 byte.
- Cả hai cùng trả 50 khách hàng.

Lượng dữ liệu thô tương ứng khoảng 300.000 byte và 6.000 byte. Đây là phép tính theo giả định, không phải benchmark hoặc số liệu đo từ một database.

Ví dụ cho thấy giảm số field của response có thể chưa xử lý được chi phí truyền và ánh xạ dữ liệu nguồn. Tuy nhiên, cũng không được kết luận tốc độ tăng đúng theo tỷ lệ byte: còn chi phí đọc, sort, mạng, mapping, cache và xử lý ứng dụng.

### 3.2. Mất cơ hội tối ưu không có nghĩa luôn select toàn bộ mọi thứ

Cần diễn đạt chính xác hai điều:

1. Không thể trông cậy vào khả năng suy ra đầy đủ tập thuộc tính cần lấy từ open projection.
2. Query thực tế vẫn chịu ảnh hưởng của kiểu query, mapping, provider và cấu hình store.

Không khẳng định mọi open projection luôn tải toàn bộ bảng, mọi cột, mọi quan hệ và mọi dữ liệu nhị phân. Đó là những kết luận về implementation cụ thể, phải được kiểm chứng riêng.

Ngược lại, khi một query chỉ lấy một số field do được khai báo rõ, không coi đó là bằng chứng open projection đã tự tối ưu dependency của SpEL.

## 4. So sánh hai truy vấn có cùng yêu cầu nghiệp vụ

Trong ứng dụng đã cấu hình repository:

```java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    List<CustomerOpenLabel>
    findOpenByTenantIdAndActiveTrueOrderByIdAsc(
            String tenantId,
            Pageable pageable);

    List<CustomerNameFields>
    findNamesByTenantIdAndActiveTrueOrderByIdAsc(
            String tenantId,
            Pageable pageable);
}
```

`Open` và `Names` trong phần trước `By` là phần mô tả của tên phương thức. Điều kiện của cả hai ví dụ đều là tenant tương ứng và `active = true`; thứ tự là id tăng dần.

Dùng cùng tenant và cùng kích thước trang khi so sánh:

```java
Pageable firstPage = PageRequest.of(0, 50);

List<CustomerOpenLabel> openRows =
        repository.findOpenByTenantIdAndActiveTrueOrderByIdAsc(
                tenantId, firstPage);

List<CustomerNameFields> nameRows =
        repository.findNamesByTenantIdAndActiveTrueOrderByIdAsc(
                tenantId, firstPage);
```

Đoạn gọi dùng `PageRequest` và `Pageable` từ `org.springframework.data.domain`. Hai phương thức trả `List` có giới hạn trang, không yêu cầu trả tổng số phần tử như một `Page`.

### 4.1. Những điều cần giữ như nhau

Một phép so sánh có ích cần cùng:

- Bộ lọc và phạm vi tenant.
- Thứ tự, kích thước trang và vị trí trang.
- Tập dữ liệu hoặc trạng thái dữ liệu đủ tương đương.
- Nhu cầu đầu ra cuối cùng.
- Cấu hình quan hệ và môi trường đo có liên quan.

Nếu một phía nhận 50 phần tử còn phía kia nhận toàn bộ khách hàng, kết quả không còn cho biết riêng tác động của kiểu projection.

### 4.2. So sánh cả quá trình sử dụng kết quả

Không chỉ đo thời gian trả về từ repository. Cần bao gồm việc tạo tên hiển thị, ánh xạ DTO và truy cập những getter mà ứng dụng thực sự dùng.

Nếu `getLabel()` được gọi sau khi đồng hồ đo đã dừng, chi phí biểu thức hoặc query phụ có thể chưa nằm trong số đo.

Mục tiêu là so sánh hai cách hoàn thành cùng chức năng, không chỉ hai thời điểm nhận proxy.

## 5. Những tối ưu vẫn có thể hoạt động

Open projection không vô hiệu hóa mọi cơ chế tối ưu của database.

| Cơ chế | Cần hiểu thế nào? |
| --- | --- |
| Bộ lọc query | Vẫn được thực thi theo query và store |
| Index cho điều kiện tìm kiếm | Có thể vẫn được dùng theo kế hoạch thực thi |
| Sort ở database | Vẫn tuân theo query và khả năng store |
| Limit hoặc phân trang | Vẫn có thể giới hạn số kết quả theo hợp đồng module |
| Select/field list khai báo rõ | Vẫn là một phần của query, cần đủ dữ liệu để ánh xạ |
| Suy ra tập field từ projection mở | Không có cùng cơ sở như closed projection |

Ví dụ, query theo tenant và trạng thái có thể vẫn dùng index phù hợp. Vấn đề là mỗi phần tử được chọn có thể đòi hỏi lượng dữ liệu hoặc công việc ánh xạ khác với dự kiến khi chỉ nhìn interface.

### 5.1. Ít field chưa chắc là covering query

Closed projection có thể tạo cơ hội chọn ít trường hơn. Nó không tự tạo index, không tự bảo đảm query được bao phủ hoàn toàn bởi index và không quyết định database có chọn index đó hay không.

Cần xem cả điều kiện lọc, thuộc tính sort, những giá trị được chọn, mapping và kế hoạch thực thi.

### 5.2. Phân trang không biến field tính ở Java thành field của query

`@Value` tạo `label` ở projection, không tự tạo property `label` cho derived query hoặc câu sort.

Lấy 50 khách hàng rồi sort theo `getLabel()` chỉ sắp lại 50 khách hàng đó. Nó không tạo đúng 50 khách hàng đầu của toàn bộ tập được sort theo cùng quy tắc.

Nếu cần lọc hoặc sort toàn tập theo giá trị dẫn xuất, cần biểu diễn phép tính tại query/store hoặc thiết kế thuộc tính đọc phù hợp.

## 6. Helper bean giúp tổ chức mã, không phục hồi tối ưu field

Có thể chuyển logic tính tên sang bean:

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerBeanLabel {

    Long getId();

    @Value("#{@customerLabelFormatter.format(target.givenName, target.familyName)}")
    String getLabel();
}
```

Giả sử bean `customerLabelFormatter` có phương thức public `format(String, String)`.

Cách này giữ biểu thức ngắn và cho phép kiểm tra logic định dạng bằng Java. Nhưng phương thức vẫn dùng `@Value`, nên projection vẫn mở.

Một helper còn có thể phụ thuộc:

- Quy tắc chọn tên ưu tiên.
- Locale hoặc cấu hình định dạng.
- Thuộc tính khác của nguồn.
- Một nguồn dữ liệu khác nếu helper được thiết kế như vậy.

Spring Data không phân tích toàn bộ Java method cùng mọi nhánh mà nó gọi để suy ra danh sách trường tối thiểu.

### 6.1. Việc tính giá trị và việc lấy dữ liệu là hai bài toán

Đưa phép ghép tên vào bean giải quyết vị trí đặt logic. Để kiểm soát dữ liệu query lấy, vẫn phải chọn projection/query phù hợp.

Nếu helper chỉ cần hai chuỗi, một hướng khác là lấy hai chuỗi bằng closed projection rồi chủ động gọi helper ở service. Khi đó, dependency dữ liệu và vị trí thực hiện logic đều rõ.

### 6.2. Chi phí ẩn trong getter

Nếu helper thực hiện thêm truy vấn hoặc gọi mạng cho mỗi khách hàng, một getter có thể tạo ra I/O lặp lại.

Không giả định giá trị getter được memoize chỉ vì biểu thức có thể được parse hoặc cache ở một lớp hạ tầng. Mapper và serializer có thể cùng đọc một getter nhiều lần.

Ví dụ, 50 phần tử, mỗi phần tử được gọi getter hai lần và helper gọi dịch vụ ngoài một lần cho mỗi lượt đánh giá có thể tạo 100 lời gọi. Cần thiết kế chi phí thực tế của helper, không chỉ rút ngắn biểu thức.

## 7. Quan hệ lồng nhau làm chi phí khó suy từ interface

Giả sử `address` là quan hệ được mapping trong JPA và một biểu thức đọc thành phố:

```java
@Value("#{target.address.city}")
String getCity();
```

Ngay cả khi kết quả chỉ là một chuỗi, việc lấy chuỗi đó có thể liên quan tới đối tượng quan hệ và trạng thái tải của nó.

Các khả năng cần xem theo mapping:

- Query ban đầu đã tải dữ liệu cần thiết.
- Một phép join làm tăng lượng dữ liệu được chọn hoặc ánh xạ.
- Getter truy cập quan hệ lazy và gây thêm query.
- Việc đọc xảy ra ngoài phạm vi persistence context cần thiết và thất bại.

Không khẳng định mọi trường hợp đều phát sinh N+1. Chỉ khi từng phần tử dẫn tới các lượt tải bổ sung tương ứng thì mô hình đó mới xuất hiện.

Tài liệu Spring Data JPA cũng lưu ý giới hạn lựa chọn thuộc tính ở mức top-level và tác động của nested property dẫn tới join. Xem [projections với JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa).

### 7.1. Closed projection lồng nhau cũng cần quan sát

Chuyển biểu thức thành một nested interface không bảo đảm mọi join chỉ chọn đúng một cột ở phía quan hệ.

Closed/open là một chiều phân loại. Độ sâu đường dẫn, fetch plan và dạng query là những chiều khác.

Vì vậy, kết luận “đã closed nên chắc chắn chỉ lấy ba cột” vẫn có thể sai khi projection chứa quan hệ.

### 7.2. Giữ ít getter không đồng nghĩa giữ ít entity trong bộ nhớ

Nếu cách thực thi query tạo nguồn projection từ các entity được quản lý, persistence context có thể giữ chúng và thông tin liên quan.

Một DTO nhỏ ở phản hồi không tự làm chi phí vật hóa entity trước đó biến mất.

Ngược lại, không giả định mọi interface projection đều tạo đầy đủ managed entity. Một kết quả tuple hoặc một cấu trúc ánh xạ khác có thể có hành vi khác. Cần xác định dạng kết quả mà query cụ thể sử dụng.

## 8. Phương án 1: closed projection với default method

Với logic chỉ ghép những thuộc tính đã biết, có thể kế thừa interface đầu vào:

```java
import java.util.Objects;

public interface CustomerDefaultLabel extends CustomerNameFields {

    default String getLabel() {
        String given =
                Objects.toString(getGivenName(), "").trim();
        String family =
                Objects.toString(getFamilyName(), "").trim();

        String label = (given + " " + family).trim();
        return label.isEmpty() ? "Chưa cập nhật" : label;
    }
}
```

Default method chỉ sử dụng accessor đã có. Không có `@Value` cần dependency được đánh giá động.

Với các accessor kế thừa đều khớp domain, cách này giữ đặc tính closed. Nó cung cấp cơ sở để module biết id và hai thành phần tên là dữ liệu cần cho projection.

### 8.1. Điều phương án này cải thiện

- Dependency dữ liệu được thể hiện qua getter rõ ràng.
- Logic đơn giản nằm trong Java, dễ đổi tên và kiểm tra.
- Không cần SpEL cho phép ghép tên.
- Có cơ hội dùng tối ưu lấy field của closed projection trong module hỗ trợ.

### 8.2. Điều vẫn cần quyết định

Các getter `getGivenName()`, `getFamilyName()` cũng công khai trên interface. Nếu phản hồi API chỉ được có id và nhãn, không tự đưa cả projection cho serializer mà bỏ qua hợp đồng đầu ra.

Có thể ánh xạ sang DTO:

```java
public record CustomerListItem(Long id, String label) {

    public static CustomerListItem from(CustomerDefaultLabel row) {
        return new CustomerListItem(row.getId(), row.getLabel());
    }
}
```

Ví dụ record dùng mức ngôn ngữ Java 17. DTO giữ đúng hai giá trị của API, trong khi projection nội bộ giữ những thuộc tính cần để tính.

Một DTO nhỏ được tạo **sau khi đã tải entity rộng** không sửa ngược chi phí query. Cải thiện cần bắt đầu từ kiểu dữ liệu được query và ánh xạ ngay từ nguồn.

## 9. Phương án 2: khai báo rõ select trong query của store

Nếu cần kiểm soát rõ dữ liệu trả về, có thể viết query phù hợp với module.

Ví dụ dưới đây thuộc **Spring Data JPA**, giả định entity tên `Customer` có các property đã nêu:

```java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface CustomerQueryRepository
        extends Repository<Customer, Long> {

    @Query("""
            select c.id as id,
                   c.givenName as givenName,
                   c.familyName as familyName
            from Customer c
            where c.tenantId = :tenantId
              and c.active = true
            order by c.id asc
            """)
    List<CustomerNameFields> findActiveNameFields(
            @Param("tenantId") String tenantId,
            Pageable pageable);
}
```

Các alias khớp accessor của `CustomerNameFields`. Phép tính nhãn có thể được thực hiện sau khi đọc các giá trị này.

Đoạn mã dùng text block của Java 17. Nó không phải query dùng chung cho mọi store.

### 9.1. Select ít giá trị không giới hạn mọi công việc phía database

Dù chỉ trả id và hai thành phần tên, database vẫn phải đánh giá bộ lọc tenant, trạng thái và thứ tự.

Câu query hẹp hơn về kết quả không đồng nghĩa số hàng phải khảo sát cũng giảm tương ứng. Index và kế hoạch thực thi vẫn cần được xem riêng.

### 9.2. Không dùng open projection để bù một select thiếu trường

Giả sử query chỉ trả id, nhưng projection còn dùng:

```java
@Value("#{target.givenName + ' ' + target.familyName}")
String getLabel();
```

Không được suy luận hạ tầng sẽ tự bổ sung hai trường tên vào query đã khai báo.

Thiếu dependency có thể biểu hiện khác nhau theo nguồn và mapping: lỗi đọc property, giá trị không mong đợi hoặc lỗi chuyển đổi. Cách sửa là làm cho query và projection thống nhất, không phải chỉ thêm getter tính toán.

### 9.3. Có thể tính ở database khi yêu cầu thuộc query

Nếu nghiệp vụ cần lọc, sort hoặc nhóm theo tên dẫn xuất, một query tính toán ở store có thể phù hợp hơn.

Nhưng cần xác định rõ:

- Hàm nối chuỗi và quy tắc null.
- Quy tắc chuẩn hóa, collation và ngôn ngữ.
- Alias, kiểu kết quả và cách mapping.
- Khả năng dùng index hoặc expression index của backend.

Một giá trị được database trả qua alias và một getter dùng SpEL là hai cơ chế khác nhau. Không coi SpEL của projection là cú pháp để Spring Data tự dịch thành biểu thức database.

## 10. Phương án 3: DTO/query model có đầu vào rõ

Một class-based projection hoặc record có thể biểu diễn tập dữ liệu cần lấy:

```java
public record CustomerNameData(
        Long id,
        String givenName,
        String familyName) {
}
```

Module có hỗ trợ DTO projection có thể dùng thông tin constructor để ánh xạ dữ liệu; cách tạo query cụ thể vẫn theo hợp đồng của module.

Sau đó service hoặc mapper tạo `CustomerListItem`. Phép ghép tên diễn ra rõ trong mã ứng dụng thay vì ẩn sau getter SpEL.

### 10.1. DTO không tự làm mọi query hiệu quả

Chỉ đổi kiểu trả về không thay thế việc kiểm tra:

- Query có được viết hoặc suy ra đúng cho DTO hay không.
- Constructor, kiểu dữ liệu và tên/alias có khớp không.
- Query có đang lấy entity rồi mới chuyển đổi ở bước sau không.
- Có những quan hệ hoặc trường khác bị tải kèm hay không.

DTO được thiết kế tốt giúp biểu đạt nhu cầu. Việc lấy đúng dữ liệu là công việc của cả query, mapping và module.

### 10.2. Khi nào giữ open projection vẫn hợp lý?

Open projection có thể phù hợp khi:

- Tập kết quả nhỏ và chi phí nguồn đã được kiểm chứng là chấp nhận được.
- Dữ liệu cần thiết vốn đã có cho đơn vị công việc hiện tại.
- Biểu thức hoặc helper cung cấp giá trị đọc tiện lợi, có chi phí dễ dự đoán.
- Mức đơn giản của cách sử dụng có ý nghĩa với chức năng đó.

Không cần chuyển mọi open projection sang một kiểu khác chỉ vì nhãn “open”. Cần xác định chi phí thực tế và yêu cầu của luồng đọc.

Ngược lại, với danh sách lớn hoặc nguồn có thuộc tính rộng, không dùng số getter ít làm bằng chứng rằng query đã đủ nhẹ.

## 11. Khác biệt giữa các store

| Khía cạnh | Abstraction chung | Điều phải xác định ở module cụ thể |
| --- | --- | --- |
| Interface projection | Proxy cung cấp các phương thức đọc | Dạng nguồn, mapping và hỗ trợ return type |
| Open projection | Giá trị có thể tính bằng biểu thức | Những dữ liệu được lấy để phục vụ nguồn |
| Closed projection | Có tập thuộc tính đầu vào nhận diện được | Cách biến tập đó thành select/field list |
| Quan hệ lồng nhau | Có thể biểu diễn đường dẫn dữ liệu | Join, reference, embedded document và fetch behavior |
| DTO | Tập dữ liệu đầu vào được mô hình hóa bằng constructor | Cơ chế constructor query và quy tắc ánh xạ |
| Hiệu năng | Cần cùng yêu cầu nghiệp vụ để so sánh | Index, planner, driver, provider và cache |

Với JPA, câu hỏi có thể là select list, join, tuple, managed entity và lazy loading.

Với MongoDB, cần xem query filter, field projection, dữ liệu document được trả và cách mapping. Tài liệu module trình bày interface projection và sự phân biệt closed/open trong [projections của Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html).

Không lấy một SQL quan sát được trong JPA làm kết luận cho document store. Cũng không mặc định mọi module đều có cùng mức hỗ trợ projection hoặc cùng thuật toán tối ưu.

## 12. Đánh giá hiệu năng bằng bằng chứng nào?

Có thể tách việc quan sát thành bốn lớp:

| Lớp | Bằng chứng hữu ích |
| --- | --- |
| Query | Điều kiện, select/field list, sort, limit, join |
| Store | Kế hoạch thực thi, số hàng/document khảo sát, dữ liệu được trả |
| Mapping | Entity/DTO/proxy được tạo, bộ nhớ và trạng thái quản lý |
| Sử dụng kết quả | Lần gọi getter, query phụ, I/O của helper, serialization |

### 12.1. Quan sát đúng luồng sử dụng

Một quy trình đánh giá có thể gồm:

1. Chuẩn bị dữ liệu đại diện cho số lượng và độ rộng bản ghi.
2. Chạy cùng bộ lọc, sort và kích thước trang.
3. Gọi tất cả getter mà mapper hoặc API thật sự dùng.
4. Ghi nhận query ban đầu và những query phát sinh sau đó.
5. So sánh lượng dữ liệu, thời gian và bộ nhớ cho cùng đầu ra.
6. Kiểm tra lại hành vi sau khi thay projection/query.

Đây là hướng thực hành cho ứng dụng, không phải các phép đo đã được chạy trong bài.

### 12.2. Những yếu tố dễ làm sai kết luận

- **Cache:** lần chạy sau có thể nhanh hơn do cache thay vì do projection.
- **Count query:** khi so sánh `Page` với `List`, số query có thể khác vì nhu cầu metadata.
- **Lazy getter:** chi phí xảy ra sau thời điểm lời gọi repository kết thúc.
- **Kích thước trang khác nhau:** làm thay đổi số phần tử xử lý.
- **Helper khác nhau:** một phía chỉ ghép chuỗi, phía kia gọi dịch vụ ngoài.
- **Khác phạm vi dữ liệu:** hai bộ lọc không còn cùng yêu cầu nghiệp vụ.

Không chỉ nhìn một con số thời gian rồi quy toàn bộ khác biệt cho closed/open.

### 12.3. Nhìn cả tính đúng đắn

Một phương án nhanh hơn vì bỏ qua property cần thiết chưa phải cải thiện hợp lệ.

Với chức năng danh sách khách hàng, vẫn phải kiểm tra:

- Không lẫn tenant.
- Thứ tự và ranh giới trang đúng.
- Nhãn hiển thị theo đúng quy tắc.
- Null và dữ liệu cũ được xử lý theo chính sách.
- DTO phản hồi giữ đúng hợp đồng.

Tối ưu phải giữ nguyên yêu cầu của tính năng.

## 13. Ví dụ ra quyết định cho danh sách khách hàng

Yêu cầu: mỗi trang tối đa 50 khách hàng đang hoạt động của một tenant; API trả id và nhãn tên. Domain có thêm biography dài.

### Lựa chọn A: open projection ghép tên

Ưu điểm là interface ngắn và caller lấy được nhãn trực tiếp.

Câu hỏi còn phải trả lời là query lấy những gì, nguồn được materialize ra sao và lúc đọc nhãn có thêm công việc nào không. Không thể chỉ từ hai getter mà kết luận biography chắc chắn không được lấy.

### Lựa chọn B: closed projection có default method

Các getter đầu vào thể hiện id và hai thành phần tên. Default method ghép nhãn; DTO bên ngoài chỉ giữ id và nhãn.

Đây là ứng viên đơn giản khi logic chỉ phụ thuộc ba thuộc tính nguồn. Vẫn cần xác nhận query của module dùng lợi thế đó như mong đợi.

### Lựa chọn C: query chọn rõ các trường

Query quy định id và hai thành phần tên; mapper tạo DTO.

Cách này giúp đọc rõ select nhưng tăng mức phụ thuộc vào dạng query của store. Cần giữ alias, kiểu dữ liệu và bộ lọc đồng bộ với mapping.

### Cách chọn

Nếu closed projection đã tạo query phù hợp, không cần thêm query khai báo chỉ để biểu diễn lại cùng điều đó. Nếu query thực tế không đáp ứng nhu cầu hoặc cần phép tính tại store, query rõ ràng hoặc một query model riêng có thể phù hợp hơn.

Giữ open projection khi lợi ích sử dụng và chi phí đã quan sát đáp ứng chức năng. Quyết định dựa trên luồng cụ thể, không dựa vào kết luận rằng một nhãn loại projection luôn tốt hoặc luôn xấu.

## 14. Câu hỏi tự kiểm tra

### Câu 1: Hai getter có nghĩa hai cột?

Một open projection có `getId()` và `getLabel()` dùng SpEL. Có thể khẳng định query chỉ chọn hai cột không?

**Trả lời:** Không. Một getter là phép tính, còn dữ liệu nguồn được lấy phụ thuộc query và module. Số getter không phải số cột.

### Câu 2: Biểu thức chỉ đọc một property

`@Value("#{target.givenName}")` có tự được tối ưu như accessor của closed projection không?

**Trả lời:** Không có hợp đồng như vậy. Nó vẫn là phương thức dùng biểu thức trong open projection.

### Câu 3: Index có ngừng hoạt động?

Dùng open projection có đồng nghĩa database không dùng được index theo tenant và trạng thái không?

**Trả lời:** Không. Giới hạn đang xét là suy ra dữ liệu đầu vào của projection; database vẫn chọn kế hoạch cho query theo điều kiện và cấu trúc thực tế.

### Câu 4: Helper bean có khôi phục tối ưu?

Đưa phép ghép tên vào bean rồi gọi bean từ `@Value` có khiến projection thành closed không?

**Trả lời:** Không. Cách tổ chức logic thay đổi, nhưng hạ tầng vẫn không suy ra đầy đủ dependency từ một lời gọi Java tùy ý.

### Câu 5: Default method có lợi gì?

Một default method chỉ ghép `getGivenName()` và `getFamilyName()` giúp gì so với SpEL?

**Trả lời:** Nó biểu diễn logic bằng Java dựa trên accessor đã biết, giữ đặc tính closed khi những accessor nguồn hợp lệ, nên module có cơ sở tối ưu tập dữ liệu đầu vào.

### Câu 6: Query trả thiếu field

Select chỉ trả id nhưng biểu thức cần tên và họ. Có thể kỳ vọng `@Value` tự mở rộng query không?

**Trả lời:** Không. Query và projection phải thống nhất dữ liệu cần có.

### Câu 7: DTO nhỏ có sửa query rộng không?

Ứng dụng tải entity rộng rồi mới chuyển thành DTO hai field. Có thể kết luận chi phí tải đã giảm không?

**Trả lời:** Không. Bước chuyển DTO không xóa chi phí query và materialization đã xảy ra trước đó.

### Câu 8: Đo repository là đủ chưa?

Repository trả nhanh nhưng getter sau đó đọc quan hệ và gọi helper. Số đo quanh lời gọi repository có đại diện toàn bộ chức năng không?

**Trả lời:** Chưa. Cần bao gồm quá trình sử dụng projection, ánh xạ và những truy vấn hoặc I/O phát sinh tiếp theo.

## Những điểm cần nhớ

- Projection mở hạn chế khả năng suy ra đầy đủ tập thuộc tính cần cho query.
- Ít getter hoặc ít field JSON không chứng minh ít dữ liệu được đọc.
- Mất cơ hội tối ưu projection không đồng nghĩa database mất mọi tối ưu.
- Default method dựa trên accessor đã biết là lựa chọn tốt cho phép tính đơn giản.
- Query chọn trường rõ hoặc DTO là những phương án khi cần biểu đạt đầu vào cụ thể.
- Quan hệ, helper bean và thời điểm gọi getter có thể bổ sung chi phí ngoài query ban đầu.
- Kết luận hiệu năng phải gắn với query thực tế, store cụ thể và cùng đầu ra nghiệp vụ.
