# Đối tượng nhúng, entity bất biến và giới hạn ánh xạ metadata

## 1. Bài toán: gom audit fields mà vẫn lưu đúng dữ liệu

Một ứng dụng ghi chú cần lưu người tạo, thời điểm tạo, người sửa và thời điểm sửa. Thay vì đặt bốn thuộc tính trực tiếp trên mọi entity, nhóm phát triển muốn gom chúng vào `AuditMetadata`. Đồng thời, entity được viết bằng Java record để các thay đổi nghiệp vụ tạo ra giá trị mới.

Thiết kế mong muốn có dạng:

```text
Note
├── id
├── content
├── audit
│   ├── createdBy
│   ├── createdAt
│   ├── lastModifiedBy
│   └── lastModifiedAt
└── version
```

Ba câu hỏi cần giải quyết trước khi triển khai:

1. Hạ tầng có nhận ra annotation bên trong `audit` hay không?
2. Khi `audit` hoặc `Note` bất biến, instance nào nhận giá trị mới?
3. Cấu trúc Java này được module lưu trữ ánh xạ thành document, cột hay quan hệ nào?

Bài thuộc chương **Auditing** của module **SPRING_DATA_COMMONS**. Sau bài học, bạn cần giải thích được đường đi của metadata từ annotation đến dữ liệu được lưu, thiết kế được một đối tượng audit nhúng và nhận diện các giới hạn khi chuyển thiết kế giữa những store khác nhau.

## 2. Phân biệt auditing metadata và persistence mapping

Spring Data Commons cung cấp `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate` và `@LastModifiedDate`. Metadata có thể nằm trong một đối tượng nhúng, nhưng khả năng này phụ thuộc store. Việc kích hoạt auditing cũng theo từng module. [Spring Data Commons: Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

Trong thiết kế của bài, hai nhóm metadata trả lời những câu hỏi khác nhau:

| Nhóm | Ví dụ | Câu hỏi được trả lời |
| --- | --- | --- |
| Vai trò auditing | `@CreatedDate` trên `createdAt` | Thuộc tính nào cần nhận thời điểm tạo? |
| Ánh xạ lưu trữ | Document nhúng, embedded columns | Thuộc tính được biểu diễn ở đâu trong store? |
| Nhận biết entity mới | ID, version, chính sách của module | Lần lưu này được xử lý như tạo hay cập nhật? |
| Nguồn giá trị | Auditor provider, nguồn thời gian | Người thao tác và thời điểm đến từ đâu? |

Ví dụ, `@CreatedDate` không tự khai báo một cột SQL. Đặt một object vào property Java cũng chưa thể hiện rằng nó phải được lưu cùng hàng với entity cha. Cần chọn mapping phù hợp trước, rồi kiểm tra auditing trên mapping đó.

Hãy dùng hai khái niệm tách bạch khi chẩn đoán: **audit metadata của entity** là các giá trị như người tạo và thời điểm tạo; **mapping metadata của framework** là mô hình mô tả các persistent properties và cách truy cập chúng.

## 3. Đường dẫn thuộc tính quan trọng hơn tên trường trong database

Với mô hình trên, các đường dẫn Java cần quan tâm là:

```text
audit.createdBy
audit.createdAt
audit.lastModifiedBy
audit.lastModifiedAt
```

Trong implementation tham chiếu, `MappingAuditableBeanWrapperFactory` dùng mapping context để tìm persistent property paths có annotation auditing. Các đường dẫn đi qua collection hoặc map được loại; việc gán sử dụng tùy chọn bỏ qua đoạn trung gian null. Đây là chi tiết implementation cần đối chiếu với phiên bản dự án, không phải lời hứa cho mọi module. [Mã nguồn MappingAuditableBeanWrapperFactory](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/auditing/MappingAuditableBeanWrapperFactory.java).

Với ứng dụng ghi chú, có thể kiểm tra mô hình bằng ba bước:

1. Tìm annotation trên thuộc tính lá, chẳng hạn `createdAt`.
2. Kiểm tra đường dẫn từ `Note` đến thuộc tính đó có thuộc mô hình persistent của module hay không.
3. Kiểm tra các object nằm trên đường dẫn có tồn tại và có thể được thay đổi hoặc thay thế không.

Không nên gắn `@CreatedDate` lên property `AuditMetadata audit`. Kiểu của property ấy là cả một đối tượng chứa nhiều giá trị, trong khi dữ liệu cần nhận thời điểm nằm ở `audit.createdAt`.

Tên BSON field hoặc tên cột có thể được tùy biến riêng. Khi điều tra lỗi, hãy ghi rõ cả đường dẫn Java và vị trí lưu trữ dự kiến để tránh nhầm tên field trong document với tên property mà accessor sử dụng.

## 4. Ví dụ: metadata nhúng bất biến trong MongoDB

Các ví dụ dùng Java 17 và một ứng dụng Spring Data MongoDB đồng bộ có phiên bản tương thích. Mỗi public type nằm trong tệp Java riêng, cùng package `example.audit`; các đoạn mã lược dòng khai báo package. Ứng dụng cần có cấu hình kết nối MongoDB và quét repository phù hợp.

MongoDB được chọn để minh họa một trường hợp cụ thể. Không áp dụng nguyên cấu hình này cho JPA hoặc JDBC.

### 4.1. Record chứa audit fields

```java
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

public record AuditMetadata(
        @CreatedBy String createdBy,
        @CreatedDate Instant createdAt,
        @LastModifiedBy String lastModifiedBy,
        @LastModifiedDate Instant lastModifiedAt) {

    public static AuditMetadata empty() {
        return new AuditMetadata(null, null, null, null);
    }
}
```

`empty()` tạo một object tồn tại nhưng chưa có giá trị audit. Điều này khác với việc property `audit` bằng null.

Trong thiết kế này, constructor của `AuditMetadata` chấp nhận các thành phần null. Factory tạo entity chạy trước auditing, nên chưa thể đòi hỏi mọi audit field đều có giá trị. Nếu muốn kiểm tra metadata đầy đủ, hãy xác định điểm kiểm tra sau khi hạ tầng đã điền dữ liệu và phân biệt luồng tạo với cập nhật.

Không dùng một instance mutable của audit metadata làm giá trị mặc định dùng chung cho nhiều entity. Với record trong ví dụ, các thành phần là `String` và `Instant`; phương thức `empty()` vẫn tạo một giá trị rõ ràng cho lần khởi tạo đó.

### 4.2. Entity gốc cũng bất biến

```java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("notes")
public record Note(
        @Id String id,
        String content,
        AuditMetadata audit,
        @Version Long version) {

    public Note {
        Objects.requireNonNull(content, "content bắt buộc");
        Objects.requireNonNull(audit, "audit container bắt buộc");
    }

    public static Note draft(String content) {
        return new Note(null, content, AuditMetadata.empty(), null);
    }

    public Note withContent(String nextContent) {
        return new Note(id, nextContent, audit, version);
    }
}
```

Factory `draft` tạo đủ cấu trúc object để đi đến các thuộc tính audit. Phương thức `withContent` giữ lại ID, version và metadata hiện có khi thay nội dung.

Hai giá trị `id` và `version` được để null cho bản nháp này. Không tự sao chép giá trị version của một entity khác vào bản nháp, cũng không xóa version khi tạo bản sao dùng để cập nhật.

Quy tắc `audit` khác null là chủ ý của ví dụ. Nó cũng có nghĩa dữ liệu cũ không có audit container có thể không đọc được thành `Note` này. Trước khi áp dụng cho collection đang có dữ liệu, cần chọn cách chuyển đổi dữ liệu hoặc thiết kế constructor đọc dữ liệu cũ phù hợp.

### 4.3. Repository và cấu hình dành cho một job

```java
import org.springframework.data.repository.CrudRepository;

public interface NoteRepository extends CrudRepository<Note, String> {
}
```

Ứng dụng minh họa là một tiến trình import đã được định danh, nên dùng actor cố định của job:

```java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration(proxyBeanMethods = false)
@EnableMongoAuditing(
        auditorAwareRef = "noteImportAuditor",
        modifyOnCreate = true)
public class NoteAuditConfiguration {

    @Bean
    AuditorAware<String> noteImportAuditor() {
        return () -> Optional.of("system:note-import");
    }
}
```

MongoDB có cấu hình auditing đồng bộ và reactive riêng; khi có nhiều auditor provider, có thể chọn bean qua `auditorAwareRef`. [Spring Data MongoDB: Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html).

Provider của ví dụ phù hợp với tiến trình import này. Với ứng dụng phục vụ nhiều người dùng, cần thay bằng nguồn actor của lần thực thi hiện hành; không dùng tên job cố định để đại diện mọi request.

### 4.4. Lưu và đọc lại instance được trả về

```java
Note draft = Note.draft("Ghi chú ban đầu");
Note saved = repository.save(draft);

Note changed = saved.withContent("Ghi chú đã cập nhật");
Note updated = repository.save(changed);

Note reloaded = repository.findById(updated.id()).orElseThrow();
```

Đoạn sử dụng này giả định `repository` là bean `NoteRepository` đã được ứng dụng cung cấp.

Hợp đồng `CrudRepository.save` yêu cầu dùng instance trả về cho xử lý tiếp theo, vì thao tác lưu có thể thay đổi hoàn toàn instance entity. [API CrudRepository.save](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html#save(S)).

Với ví dụ đang xét, hãy kiểm tra `saved.audit()` sau lần tạo và `reloaded.audit()` sau lần cập nhật. Không dùng việc `draft.audit()` vẫn rỗng làm bằng chứng rằng auditing thất bại: đó là giá trị đầu vào của một thiết kế bất biến.

Các điều kiện mong muốn của bài thực hành:

| Sau thao tác | Điều cần kiểm tra |
| --- | --- |
| Tạo | Có ID, có audit container, actor tạo đúng job |
| Tạo với `modifyOnCreate=true` | Có metadata sửa ngay trong lần tạo |
| Cập nhật nội dung | Người tạo và thời điểm tạo được giữ lại |
| Đọc lại từ store | Metadata vẫn tồn tại sau khi mapping ngược về Java |
| Thay đổi tiếp | Dùng ID và version từ kết quả lưu gần nhất |

## 5. Bất biến không loại bỏ nhu cầu điền metadata

Trong các module sử dụng object mapping của Spring Data, property bất biến có thể được cập nhật thông qua wither hoặc việc dựng lại object bằng persistence constructor. Record được dựng qua canonical constructor. Cơ chế object mapping này không áp dụng nguyên dạng cho JPA, vốn giao mapping cho JPA provider. [Spring Data Commons: Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html).

Với mô hình `Note`, có thể hình dung quá trình điền một trường theo dạng:

```text
Note đầu vào
  -> AuditMetadata mang thêm giá trị mới
  -> Note giữ AuditMetadata mới
  -> instance cuối được chuyển sang bước ghi
```

Đây là cách hình dung về giá trị, không phải cam kết số lần cấp phát hay thứ tự gán từng field.

Accessor đường dẫn tham chiếu có xử lý việc gán ngược một object con mới lên property của object cha. Vì vậy, cần xem cả chuỗi cha-con khi thiết kế object bất biến. [Mã nguồn SimplePersistentPropertyPathAccessor](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/mapping/model/SimplePersistentPropertyPathAccessor.java).

Nếu chuyển từ record sang class có trường final, hãy kiểm tra riêng:

- Constructor mà persistence dùng có nhận đủ các giá trị cần bảo toàn không?
- Một wither có giữ lại các property khác khi trả instance mới không?
- Object cha có thể nhận object con mới không?
- Quy tắc kiểm tra trong constructor có cho phép trạng thái trước khi auditing hoàn tất không?

Ví dụ một phương thức sao chép sai về nghiệp vụ:

```java
public Note withContent(String nextContent) {
    return new Note(id, nextContent, AuditMetadata.empty(), version);
}
```

Đoạn này tự xóa metadata cũ trước khi lưu. Đó là hành vi do ứng dụng viết ra, nên cần sửa ngay tại phương thức tạo bản sao thay vì kỳ vọng auditing khôi phục mọi giá trị đã mất.

Một thiết kế chỉ giữ object gốc sau khi gọi `save`, hoặc callback tự tạo instance mới rồi trả lại instance cũ, cũng làm luồng dữ liệu khó kiểm soát. Hãy theo dõi giá trị trả về ở từng bước có quyền thay entity.

## 6. Container null, giá trị lá null và dữ liệu cũ

Hai trạng thái dưới đây có ý nghĩa khác nhau:

```java
// Có container, chưa có giá trị lá.
AuditMetadata metadata = AuditMetadata.empty();

// Chưa có container để đi tiếp đến thuộc tính lá.
AuditMetadata missing = null;
```

Với accessor tham chiếu, khi gặp object trung gian null và tùy chọn bỏ qua null, đường dẫn dừng mà không tạo object trung gian. Từ đó, không thể suy rằng thêm annotation vào lớp con sẽ tự khởi tạo lớp con ấy. [Mã nguồn SimplePersistentPropertyPathAccessor](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/mapping/model/SimplePersistentPropertyPathAccessor.java).

Trong record `Note`, factory và constructor đã ngăn trạng thái thiếu container. Với một mô hình cũ cho phép null, có thể cần quyết định rõ tại ranh giới đọc hoặc cập nhật:

| Tình huống | Lựa chọn thiết kế |
| --- | --- |
| Entity mới | Factory tạo audit container rỗng |
| Bản ghi cũ chưa có audit | Backfill hoặc chuẩn hóa khi đọc theo chính sách đã chọn |
| Container bắt buộc trong domain | Kiểm tra invariant và xử lý dữ liệu cũ trước khi bật quy tắc |
| Container chỉ tùy chọn | Chấp nhận thiếu metadata và mô tả rõ ý nghĩa |

Không điền thời điểm hiện tại vào `createdAt` chỉ để dữ liệu cũ trông đầy đủ. Nếu không biết thời điểm tạo thật, cần thể hiện sự thiếu thông tin hoặc lưu nguồn gốc giá trị backfill. Một thời điểm được suy đoán khác với thời điểm được ghi nhận khi tạo.

Việc dựng một `AuditMetadata.empty()` trong lúc cập nhật bản ghi cũ cũng chưa khôi phục được lịch sử. Trong handler tham chiếu, các trường tạo được điền khi entity được xử lý như mới; nhánh sửa không mặc nhiên sửa lại chúng. [Mã nguồn AuditingHandlerSupport](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/auditing/AuditingHandlerSupport.java).

## 7. Collection, map và tham chiếu là những ranh giới riêng

Một audit container đơn không tương đương với danh sách các phần tử đều có annotation audit:

```text
Note.audit.createdAt          # Một container đơn
Notebook.items[*].createdAt   # Metadata của từng phần tử
Workspace.byKey[*].createdAt  # Đường đi qua map
```

Như giới hạn implementation đã nêu ở phần 3, không thiết kế việc audit từng phần tử dựa vào giả định save object gốc sẽ tự điền toàn bộ collection hoặc map. [Mã nguồn MappingAuditableBeanWrapperFactory](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/auditing/MappingAuditableBeanWrapperFactory.java).

Trước hết cần định nghĩa ý nghĩa nghiệp vụ:

- Nếu thêm một item, metadata nào mô tả việc sửa notebook và metadata nào mô tả việc tạo item?
- Nếu xóa item, dữ liệu nào còn giữ được bằng chứng về thao tác đó?
- Nếu item có vòng đời độc lập, nó có nên là aggregate hoặc bản ghi được lưu riêng không?

Một property chứa tham chiếu tới entity khác cũng cần được đánh giá riêng. Việc gán một ID tham chiếu không chứng minh entity đích đã được cập nhật, nên không thể dùng nó làm bằng chứng metadata bên entity đích đã thay đổi.

Nếu cần lịch sử từng thay đổi trong danh sách, hãy thiết kế bản ghi sự kiện hoặc lịch sử phù hợp. Bốn trường tạo/sửa ở aggregate root chỉ mô tả metadata đầu và gần nhất của root theo luồng được audit.

## 8. Cùng cấu trúc Java, mapping của mỗi store có thể khác

### 8.1. MongoDB: theo dõi callback của entity gốc

Spring Data MongoDB sử dụng EntityCallback cho auditing; `AuditingEntityCallback` chạy trước bước chuyển entity sang `Document`, với order 100. Tài liệu cũng phân biệt lifecycle events của root với các object phức hợp nằm bên trong document. [Spring Data MongoDB: Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html).

Với ví dụ `Note`, hãy điều tra từ root được truyền vào thao tác lưu. Không cần giả định `AuditMetadata` nhận một vòng đời lưu độc lập chỉ vì nó chứa annotation.

Nếu bổ sung callback để chuẩn hóa dữ liệu, cần xét thứ tự so với auditing và trả đúng instance mới. Callback tạo container sau khi auditing đã chạy không giúp lần chạy trước đó nhìn thấy container ấy.

### 8.2. JDBC: embedded columns và chính sách khi dữ liệu rỗng

Trong Spring Data JDBC, `@Embedded` ánh xạ các thuộc tính con vào các cột của cùng hàng. Thuộc tính `prefix` giúp phân biệt tên cột; `onEmpty` quyết định cách dựng embedded object khi các giá trị con đều null. `USE_EMPTY` yêu cầu một constructor có thể tạo object từ các giá trị tương ứng. [Spring Data JDBC: Embedded entities](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.entity-persistence.embedded-entities).

Ví dụ mapping dành riêng cho JDBC:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("notes")
public record JdbcNote(
        @Id Long id,
        String content,
        @Embedded(onEmpty = Embedded.OnEmpty.USE_EMPTY, prefix = "audit_")
        AuditMetadata audit) {
}
```

Ví dụ này chỉ minh họa mapping. Muốn thực hành cần schema, kiểu cột, cấu hình JDBC auditing và nguồn actor phù hợp. `onEmpty` ở đây nói về cách đọc dữ liệu; factory tạo entity mới vẫn nên truyền `AuditMetadata.empty()` nếu ứng dụng cần container tồn tại ngay trước khi ghi.

Đừng thêm `jakarta.persistence.Embedded` vào ví dụ JDBC này: hai annotation có cùng ý tưởng tên gọi nhưng thuộc hai hệ mapping khác nhau.

### 8.3. JPA: xét quy tắc của JPA provider

Spring Data JPA có `AuditingEntityListener` và cấu hình kích hoạt auditing riêng. Metadata nhúng phải đi cùng mapping JPA tương ứng; không dùng `@EnableMongoAuditing` để bật nó. [Spring Data JPA: Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html).

Khi chuyển thiết kế sang JPA, cần kiểm tra entity, embeddable, constructor, access strategy và khả năng của provider đang dùng. Khả năng dùng Java record cho một value object hoặc projection không tự chứng minh record ấy hợp lệ làm entity JPA.

Một mẫu dùng chung chỉ nên khẳng định những phần đã kiểm tra được trên các module mục tiêu. Việc các class cùng import annotation auditing từ Commons chưa đủ chứng minh mọi mapping đều tương thích.

## 9. Những giới hạn annotation không tự giải quyết

### 9.1. Thuộc tính phải tham gia đúng mô hình lưu trữ

Nếu audit property bị loại khỏi persistence mapping, hoặc cả container được converter biểu diễn thành một giá trị đơn, hãy kiểm tra lại các đường dẫn persistent mà module thực sự nhận biết. Không suy rằng mọi lớp Java bên trong một object đã có metadata riêng trong mapping context.

Tương tự, một getter tính toán dữ liệu để hiển thị không tự tạo nơi lưu dữ liệu đó. Cần xác định audit value thuộc property persistent nào và được ghi thành gì.

### 9.2. Kiểu auditor và kiểu thời gian cần khớp hợp đồng

Trong ví dụ, actor được lưu bằng `String`, thời gian bằng `Instant`. Nếu đổi actor sang domain `User`, cần thiết kế biểu diễn lưu trữ và khả năng mapping của store. Nếu đổi kiểu thời gian, cần kiểm tra cả bước cung cấp giá trị audit lẫn bước chuyển đổi sang kiểu của database.

Không lưu security token hoặc toàn bộ principal chỉ để tránh bước chọn ID actor. Chọn một định danh phục vụ nhu cầu tra cứu lâu dài và mô tả rõ giá trị đó đại diện cho người dùng, job hay service nào.

### 9.3. Bản sao cập nhật phải giữ dữ liệu không được thay đổi

Giả sử DTO chỉ có `content`. Hãy nạp entity hiện có rồi tạo bản sao thay phần nội dung được phép sửa. Dựng một entity khác từ ID và DTO, bỏ toàn bộ metadata và version, có thể thay đổi cả ngữ nghĩa lưu lẫn dữ liệu được ghi.

Trong thiết kế của bài, không đưa `createdBy` hoặc `createdAt` vào dữ liệu cập nhật tùy ý từ client. Đây là các giá trị do ứng dụng quản lý, nên cần có quy tắc bảo toàn riêng.

### 9.4. Audit fields không thay thế kiểm soát ghi dữ liệu

Audit chỉ có ý nghĩa khi đường ghi thực sự gọi hạ tầng liên quan. Với raw driver, update trực tiếp hoặc thao tác bulk, cần kiểm tra API và tài liệu module trước khi kỳ vọng có cùng hành vi với save entity.

Các field tạo/sửa cũng không tự cung cấp phân quyền, transaction hoặc lịch sử đầy đủ. Nếu cần chứng minh ai đổi từng giá trị, phải có thiết kế ghi nhận thay đổi phù hợp với yêu cầu đó.

## 10. Cách kiểm tra thiết kế bằng dữ liệu được đọc lại

Các ví dụ trong bài là hướng dẫn thực hành, không phải báo cáo đã chạy kiểm thử trên dự án. Khi triển khai, dùng đúng module và phiên bản mà ứng dụng đang dùng.

Một bộ tình huống có giá trị hơn việc chỉ kiểm tra annotation bằng reflection:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Tạo `Note.draft(...)` | Container có sẵn trước khi save |
| Lưu entity mới | Instance trả về có ID và metadata theo cấu hình |
| Đọc lại sau tạo | Metadata đã được lưu, không chỉ tồn tại trong bộ nhớ |
| Đổi nội dung từ instance đã lưu | `createdBy`, `createdAt` được bảo toàn |
| Đổi actor khi cập nhật | `lastModifiedBy` theo actor của lần cập nhật |
| Dùng record cho cả cha và con | Kết quả cuối chứa giá trị được điền vào các object mới |
| Đọc bản ghi cũ thiếu audit | Có hành vi rõ: chuyển đổi, chấp nhận hoặc từ chối theo thiết kế |
| Model khác cho phép container null | Xác định trường nào được bỏ qua trong phiên bản đang dùng |
| Đặt audit trong collection/map | Kiểm tra giới hạn, tránh kỳ vọng lan truyền tự động |
| Đường update trực tiếp | Xác định callback có chạy và metadata được cập nhật bằng cách nào |

Với kiểm thử thời gian, có thể thay nguồn thời gian bằng giá trị kiểm soát được rồi đổi giá trị giữa hai thao tác. Cách đó giúp kiểm tra chính xác rằng thời điểm tạo được giữ lại và thời điểm sửa phản ánh lần ghi tiếp theo, thay vì dựa vào việc hai thao tác có chạy đủ cách xa nhau hay không.

Nếu dữ liệu sai, hãy điều tra theo thứ tự:

1. Xác định entity gốc và API ghi cụ thể.
2. Kiểm tra auditing đã được bật cho đúng module.
3. Xác định đường dẫn Java đến thuộc tính lá.
4. Kiểm tra container có tồn tại ở thời điểm auditing chạy.
5. Kiểm tra khả năng thay property con và trả instance cha mới.
6. Xem kết quả `save`, rồi đọc lại từ store.
7. Đối chiếu mapping, converter và dữ liệu cũ nếu kết quả khác kỳ vọng.

## 11. Bài tập áp dụng

Triển khai mô hình `Note` và `AuditMetadata` trong một ứng dụng MongoDB thử nghiệm. Tạo một ghi chú, lưu lại, sửa nội dung từ kết quả lưu và đọc lại lần cuối.

Ghi lại các giá trị `id`, `version`, `createdBy`, `createdAt`, `lastModifiedBy`, `lastModifiedAt` sau mỗi thao tác. Sau đó trả lời:

1. Vì sao factory tạo `AuditMetadata.empty()` thay vì để `audit` null?
2. Vì sao cần lấy `saved` và `updated` từ kết quả `save`?
3. Nếu `withContent` tạo audit container rỗng, dữ liệu nào bị mất trước khi auditing chạy?
4. Nếu dữ liệu cũ không có audit container, constructor hiện tại sẽ xử lý thế nào?
5. Phần nào phải thiết kế lại khi chuyển sang JDBC hoặc JPA?

Một lời giải tốt chỉ ra được object tồn tại trước khi ghi, instance được dùng sau khi ghi, đường dẫn persistent đến audit fields và bằng chứng từ dữ liệu được đọc lại. Đó là cơ sở để dùng metadata nhúng và entity bất biến mà vẫn hiểu rõ giới hạn của từng module Spring Data.
