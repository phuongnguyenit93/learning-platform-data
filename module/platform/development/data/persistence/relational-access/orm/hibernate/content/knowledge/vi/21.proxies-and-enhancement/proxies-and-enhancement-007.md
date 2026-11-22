# Bytecode enhancement cho tải trì hoãn thuộc tính hoặc theo dõi thay đổi trong Hibernate

## 1. Khái niệm

Bytecode enhancement là bước biến đổi class entity đã biên dịch để thêm hook phục vụ Hibernate. Nó có thể hỗ trợ lazy basic attribute loading, inline dirty tracking và đồng bộ hai phía của association. Thường cấu hình build-time enhancer chạy sau compile, trước test/package.

```java
@Entity
public class Document {
    @Id
    private Long id;

    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("body")
    private String body;
}
```

## 2. Lazy basic attributes

Proxy thường được dùng cho association to-one và persistent wrapper cho collection. Bytecode enhancement mở rộng khả năng trì hoãn tới field cơ bản như String, byte array hoặc LOB. @Basic(fetch = LAZY) là fetch hint; với Hibernate cần bật lazy initialization enhancement để lazy basic field hoạt động theo mong đợi.

Khi entity được load, Hibernate có thể lấy id/title trước. Lần đầu gọi getBody() trong khi Session còn mở, nó có thể SELECT cột body riêng. Nếu field chưa tải mà Session đã đóng, truy cập vẫn có thể gây LazyInitializationException. Enhancement không vượt qua persistence-context boundary.

## 3. Lazy groups

@LazyGroup("body") đặt field vào nhóm tải riêng. Các lazy attribute cùng nhóm có thể được tải cùng nhau khi một thành viên được truy cập. Tách nội dung lớn khỏi metadata nếu use case thường chỉ cần metadata. Lazy group gom field trên một entity; batch fetching gom nhiều owner/entity và là cơ chế khác.

## 4. Inline dirty tracking

Snapshot-based dirty checking so sánh trạng thái managed entity với snapshot. Khi bật enableDirtyTracking, enhancer instrument field write để ghi nhận thuộc tính nào thay đổi. Điều này có thể giảm công việc so sánh trong workload phù hợp, nhưng không loại bỏ mọi snapshot cho mọi kiểu dữ liệu.

Mutable object có thể bị sửa bên trong mà không gán lại field, ví dụ Date.setTime(). Inline tracker có thể không nhận biết mutation đó qua field write. Ưu tiên value object bất biến như Instant hoặc gán instance mới. Persistent collections có cơ chế theo dõi riêng.

Dirty tracking không phải optimistic locking. @Version vẫn dùng để phát hiện stale update. @DynamicUpdate lại điều khiển cột trong SQL SET; nó khác với việc nhận diện field dirty.

## 5. Cấu hình và kiểm thử

Bật enableLazyInitialization, enableDirtyTracking và khi cần enableAssociationManagement trong enhancer Maven hoặc Gradle. Dùng plugin tương thích với Hibernate runtime. Clean build, xác nhận task chạy trên module chứa entity, và bảo đảm artifact runtime chứa class đã enhanced.

Kiểm tra lazy field bằng Hibernate.isPropertyInitialized(entity, "body") trước và sau getter; đồng thời quan sát SQL. Đo dirty tracking bằng integration test và SQL ở flush. Không dùng debugger, logger hoặc serializer truy cập field trước phép đo.

## 6. Giới hạn

Lazy field có thể tạo N+1 khi đọc trên nhiều entity. Fetch plan có thể yêu cầu field tải sớm. Association management enhancement không thay thế cascade, orphanRemoval, owning-side mapping hoặc database foreign key. Enhancement không thay thế fetch join, EntityGraph, projection, transaction isolation hay @Version.

```java
Document document = entityManager.find(Document.class, 100L);
assertFalse(Hibernate.isPropertyInitialized(document, "body"));

String body = document.getBody();

assertTrue(Hibernate.isPropertyInitialized(document, "body"));
```

```java
Product product = entityManager.find(Product.class, 10L);
product.changePrice(new BigDecimal("120.00"));
entityManager.flush();
```

## 7. Nguyên tắc

- Lazy basic attributes cần enhancement và Session còn khả năng tải.
- Lazy groups gom field cùng entity, không gom nhiều entity.
- Inline dirty tracking quan sát field write; mutation nội bộ của mutable object cần lưu ý.
- @DynamicUpdate, @Version và enhancement có trách nhiệm riêng.
- Kiểm tra build artifact và đo SQL trong integration test.


## 8. Cấu hình Maven enhancer

Với Maven, Hibernate cung cấp `hibernate-enhance-maven-plugin`. Plugin cần dùng version phù hợp với Hibernate ORM runtime.

Ví dụ cấu hình cho Hibernate 6.x:

```xml
<properties>
    <hibernate.version>6.6.0.Final</hibernate.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.hibernate.orm.tooling</groupId>
            <artifactId>hibernate-enhance-maven-plugin</artifactId>
            <version>6.6.0.Final</version>
            <executions>
                <execution>
                    <goals>
                        <goal>enhance</goal>
                    </goals>
                    <configuration>
                        <enableLazyInitialization>true</enableLazyInitialization>
                        <enableDirtyTracking>true</enableDirtyTracking>
                        <enableAssociationManagement>true</enableAssociationManagement>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là cấu hình minh họa. Khi áp dụng, dùng version đã được quản lý trong dự án và đối chiếu tên/khả năng cấu hình của plugin tương ứng. Tránh để enhancer và dependency Hibernate lệch version.

Mục tiêu enhancement phải chạy sau khi Java compiler tạo class và trước khi test/package sử dụng class cần enhanced. Sau khi cấu hình:

- Chạy build sạch để tránh dùng class cũ.
- Kiểm tra log cho thấy plugin đã xử lý entity.
- Chạy integration test trên class output đã enhanced.
- Đảm bảo artifact cuối cùng chứa class đã enhancement.

Không chỉ nhìn thấy plugin trong `pom.xml` rồi kết luận enhancer đã chạy.

## 9. Cấu hình Gradle enhancer

Hibernate có Gradle plugin hỗ trợ enhancement. Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.hibernate.orm' version '6.6.0.Final'
}

dependencies {
    implementation 'org.hibernate.orm:hibernate-core:6.6.0.Final'
}

hibernate {
    enhancement {
        enableLazyInitialization = true
        enableDirtyTracking = true
        enableAssociationManagement = true
    }
}
```

Nếu dự án dùng Kotlin DSL, cú pháp block có thể khác cách truy cập property nhưng các tùy chọn tương ứng giữ cùng ý nghĩa. Hãy theo tài liệu Gradle plugin của đúng Hibernate version.

### 9.1. Không để plugin và dependency lệch version

Ví dụ cấu hình có rủi ro:

- Dependency `hibernate-core` dùng một version.
- Enhancer plugin dùng version khác không tương thích.
- CI chạy plugin khác cấu hình local.
- Runtime artifact chứa class được enhanced bởi tool cũ.

Hãy quản lý version nhất quán qua version catalog, property hoặc dependency management của dự án. Khi nâng Hibernate, kiểm tra cả enhancer plugin và integration tests.

### 9.2. Build incremental và class cũ

Nếu build tool không re-enhance class sau một thay đổi cấu hình hoặc entity, output cũ có thể làm kết quả khó đoán. Trong quá trình bật enhancement lần đầu, nên chạy clean build và xác nhận task enhancement thực sự chạy.

Không sửa bytecode output bằng tay trong thư mục build. Hãy sửa source/config và để build tool tái tạo artifact.

## 10. Kiểm tra lazy attribute đã khởi tạo hay chưa

Hibernate cung cấp API:

```java
import org.hibernate.Hibernate;

Document document = entityManager.find(Document.class, 100L);

boolean bodyLoaded =
    Hibernate.isPropertyInitialized(document, "body");
```

Nếu field `body` chưa được tải, kết quả có thể là `false`. Sau khi đọc:

```java
String body = document.getBody();

boolean bodyLoadedAfter =
    Hibernate.isPropertyInitialized(document, "body");
```

kết quả thường chuyển thành `true`.

API JPA có thể kiểm tra trạng thái load:

```java
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil util =
    entityManager.getEntityManagerFactory()
                 .getPersistenceUnitUtil();

boolean loaded = util.isLoaded(document, "body");
```

`Hibernate.isPropertyInitialized` là API Hibernate-specific; `PersistenceUnitUtil.isLoaded` thuộc Jakarta Persistence. Chúng hữu ích cho integration test và chẩn đoán, nhưng không nên dùng trạng thái initialized làm điều kiện nghiệp vụ.

### 10.1. Kiểm tra SQL trước và sau khi truy cập

Một integration test nên:

1. Mở persistence context mới.
2. Load entity bằng query không yêu cầu lazy attribute.
3. Kiểm tra property chưa initialized.
4. Đọc field lazy.
5. Kiểm tra property đã initialized.
6. Quan sát SQL để xác nhận truy vấn bổ sung chỉ lấy nhóm thuộc tính cần thiết.

Test phải chạy với class đã enhanced và fixture phù hợp. Nếu test framework đã load field trước assertion hoặc entity nằm trong context dùng lại, kết quả sẽ không còn kiểm tra được lazy loading.

### 10.2. Kiểm tra lazy groups

Nếu có hai nhóm `content` và `metadata`, kiểm tra từng property:

- Load entity: cả hai nhóm chưa initialized nếu query không yêu cầu.
- Đọc `content`: nhóm content được tải.
- Kiểm tra metadata: vẫn chưa initialized nếu được tách nhóm và không có fetch plan khác.
- Đọc `checksum`: nhóm metadata được tải.

Quan sát SQL để xác nhận field nào xuất hiện trong từng SELECT. Không chỉ dựa vào số query vì cache và các thuộc tính khác có thể ảnh hưởng.

## 11. Kiểm tra inline dirty tracking

Không cần gọi trực tiếp interface/hook nội bộ do enhancer sinh ra để chứng minh tính năng hoạt động. Hãy quan sát hành vi qua integration test và SQL.

Có thể kiểm tra:

- Entity có phát sinh UPDATE khi field thay đổi không?
- Không thay đổi entity có tránh UPDATE không?
- Field nào được đánh dấu dirty khi thay đổi nhiều thuộc tính?
- Kiểu mutable có thay đổi nội bộ mà tracker không nhận biết không?
- `@DynamicUpdate` có làm SQL SET chỉ chứa cột cần thiết không?
- `@Version` có tăng đúng khi update không?

Đừng suy từ một câu UPDATE có một cột rằng inline dirty tracking chắc chắn đã bật; `@DynamicUpdate`, mapping và provider behavior cũng ảnh hưởng SQL shape.

### 11.1. Benchmark snapshot và inline dirty tracking

Một benchmark nên so sánh hai build khác nhau trên cùng dataset/workload. Đo:

- Thời gian flush.
- CPU trong dirty checking.
- Allocation và heap.
- Số lượng entity managed.
- Số thuộc tính trên entity.
- Tỷ lệ entity thực sự thay đổi.
- Loại value type, đặc biệt mutable types.
- SQL và số cột được update.

Inline tracking có thể có lợi khi persistence context lớn và entity có nhiều thuộc tính, nhưng không phải lúc nào cũng nhanh hơn. Một use case nhỏ với ít entity có thể không thấy lợi ích đáng kể.

## 12. Enhancement và @DynamicUpdate phối hợp ra sao?

```java
@Entity
@DynamicUpdate
public class InventoryItem {

    @Id
    private Long id;

    private String name;

    private Integer quantity;

    private BigDecimal unitPrice;
}
```

Khi ứng dụng chỉ đổi `quantity`, hai quyết định tách biệt:

1. Enhanced dirty tracking giúp xác định `quantity` đã thay đổi.
2. `@DynamicUpdate` cho phép câu UPDATE chỉ ghi cột dirty thay vì ghi nhiều cột hơn.

SQL minh họa:

```sql
UPDATE inventory_item
SET quantity = ?
WHERE id = ?;
```

Nếu bỏ `@DynamicUpdate`, Hibernate vẫn có thể biết field nào dirty nhưng SQL mặc định có thể chứa nhiều cột hơn theo update strategy. Ngược lại, `@DynamicUpdate` không đòi hỏi phải dùng inline dirty tracking; Hibernate có thể xác định dirty state bằng snapshot.

Nhiều tổ hợp field dirty có thể sinh nhiều hình dạng SQL. Điều này ảnh hưởng statement cache và batching. Không bật chỉ vì muốn SQL ngắn hơn; cần benchmark và kiểm tra execution plan.

## 13. Enhancement không loại bỏ proxy

Bytecode enhancement và proxy thường được nhắc cùng nhau nhưng không phải một cơ chế duy nhất.

- Proxy có thể đại diện entity association chưa được tải.
- Persistent collection wrapper trì hoãn tải collection.
- Enhanced entity có thể intercept truy cập thuộc tính và hỗ trợ lazy loading ở cấp field.
- Hibernate có thể phối hợp các cơ chế này tùy loại association, mapping và version.

Bật enhancement không có nghĩa toàn bộ proxy biến mất. Một entity vẫn có thể được tham chiếu qua proxy; collection vẫn có thể dùng wrapper.

### 13.1. Lazy to-one association

Enhancement có thể hỗ trợ lazy loading cho một số to-one association mà không phải dựa hoàn toàn vào subclass proxy truyền thống. Tuy nhiên, chi tiết yêu cầu mapping và annotation đã thay đổi giữa các phiên bản Hibernate.

Một số dự án cũ có thể gặp `@LazyToOne(LazyToOneOption.NO_PROXY)` trong cấu hình legacy. Trước khi thêm annotation này vào dự án mới, hãy kiểm tra tài liệu đúng major version; không sao chép cấu hình cũ một cách máy móc.

### 13.2. Runtime class không phải hợp đồng domain

Runtime class của entity có thể chịu ảnh hưởng proxy, enhancement, inheritance và classloader. Không viết logic domain phụ thuộc tên class được sinh hoặc kiểm tra class runtime để quyết định một field đã tải chưa.

Dùng API trạng thái load/initialized được hỗ trợ khi kiểm thử, và dùng entity API bình thường trong nghiệp vụ.

## 14. Enhancement không thay thế fetch plan

Lazy attribute loading cho phép trì hoãn field, nhưng một query vẫn có thể yêu cầu fetch sớm. Nếu use case cần `body`, có thể chủ động fetch qua query/projection hoặc đọc field trong transaction. Enhancement không tự biết use case nào cần nội dung.

Đối với association, vẫn dùng các công cụ fetch plan:

- `JOIN FETCH`.
- `@EntityGraph`.
- Batch fetching.
- Subselect fetching.
- DTO projection.
- Query phân trang cho collection lớn.

**Enhancement điều khiển cách entity hỗ trợ tải/tracking; fetch plan quyết định dữ liệu nào cần có trong use case.**

### 14.1. Lazy attribute có thể tạo N+1

```java
List<Document> documents = entityManager.createQuery(
    "select d from Document d",
    Document.class
).getResultList();

for (Document document : documents) {
    process(document.getBody());
}
```

Nếu `body` chưa tải và không có cơ chế batching phù hợp, truy cập từng entity có thể tạo một SELECT phụ cho mỗi document. Đây là N+1 ở cấp thuộc tính.

Nếu tất cả body đều cần, cân nhắc query lấy chúng theo use case hoặc projection/streaming thích hợp. Nếu chỉ một phần nhỏ cần body, lazy loading có thể tiết kiệm dữ liệu. Hãy đo cả số statement và tổng bytes.

## 15. Lazy attribute và DTO projection

Nếu endpoint chỉ cần tiêu đề và ngày tạo, không cần load entity body:

```java
public record DocumentRow(Long id, String title) {}
```

JPQL projection:

```java
List<DocumentRow> rows = entityManager.createQuery(
    "select new com.example.DocumentRow(d.id, d.title) " +
    "from Document d order by d.id",
    DocumentRow.class
).getResultList();
```

Projection chỉ chọn các giá trị cần thiết và không cần materialize entity đầy đủ. Nó thường là lựa chọn rõ ràng cho danh sách/report.

Lazy attribute hữu ích khi use case vẫn cần entity managed nhưng chỉ thỉnh thoảng truy cập field lớn. DTO projection hữu ích khi chỉ cần dữ liệu hiển thị và không cần lifecycle entity.

Không dùng lazy loading như lý do để trả entity trực tiếp qua API rồi để serializer tự quyết định field nào cần đọc.

## 16. Lazy loading và serialization/logging

Serializer đi qua mọi getter có thể kích hoạt lazy attribute:

```java
return objectMapper.writeValueAsString(document);
```

Nếu serializer đọc `body`, nó có thể gây SELECT bổ sung. Nếu Session đã đóng, có thể gặp `LazyInitializationException`.

Tương tự:

```java
log.debug("Document={}", document);
```

Nếu `toString()` in `body`, việc log sẽ tải nội dung. Hãy giữ `toString()` ngắn, chỉ in ID và field nhỏ được phép log.

API response nên dùng DTO và service tải đúng field trong transaction. Điều này làm ranh giới dữ liệu API rõ ràng và tránh serializer tùy tiện mở rộng entity graph.

## 17. Build enhancement trong multi-module project

Một cấu hình đúng trong local chưa đủ nếu CI hoặc production artifact không chạy enhancer.

Kiểm tra pipeline:

1. Dependency Hibernate và enhancer plugin cùng version phù hợp.
2. Enhancement được bật cho đúng tính năng cần dùng.
3. Task/plugin chạy sau compile và trước test/package.
4. Test sử dụng class output đã enhanced.
5. Artifact triển khai chứa class đã enhanced.
6. Không có module/entity nằm ngoài phạm vi enhancer.
7. Clean build cho kết quả nhất quán với incremental build.

Nếu entity nằm trong module `domain-persistence`, còn application nằm ở module `web-app`, phải bảo đảm enhancer chạy trên module tạo ra entity class. Chỉ cấu hình plugin ở module ứng dụng không nhất thiết biến đổi các class đã đóng gói trong dependency JAR khác.

Nếu thư viện chứa entity được build riêng, pipeline tạo thư viện đó cần thực hiện enhancement hoặc có quy trình enhancement được thiết kế rõ ràng.

## 18. Các giới hạn và chi phí cần cân nhắc

- **Thêm một bước vào build:** plugin/version mismatch hoặc cấu hình không đồng nhất giữa developer machine và CI có thể gây lỗi khó tái hiện.
- **Runtime phụ thuộc class đã enhanced:** nếu entity class không được enhancer xử lý, tính năng cần enhancement có thể không hoạt động như mong muốn.
- **Lazy loading có thể tạo query bổ sung:** đọc field lazy trong vòng lặp có thể tạo N+1; nếu hầu hết use case đều cần field đó, tải riêng có thể tốn hơn.
- **Mutable value có giới hạn:** mutation bên trong object mà không gán lại reference có thể không được inline tracker phát hiện theo cách đơn giản.
- **Không thay thế concurrency:** dirty tracker không tạo version column, không khóa database và không ngăn lost update.
- **Không thay thế association lifecycle:** association management enhancement không tự thêm cascade, orphan removal hoặc database FK.
- **Phụ thuộc Hibernate:** các annotation lazy group và plugin enhancer là phần mở rộng của Hibernate, không phải mọi JPA provider đều hỗ trợ giống nhau.

## 19. Chẩn đoán khi enhancement không hoạt động như mong đợi

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `@Basic(fetch = LAZY)` vẫn lấy cột ngay | Class chưa enhancement hoặc query yêu cầu field | Kiểm tra build log, artifact, fetch plan |
| Đọc field lazy gây `LazyInitializationException` | Context đã đóng trước khi field được tải | Đọc trong transaction hoặc query DTO |
| Đọc một lazy field làm nhiều field khác tải | Các field cùng lazy group | Kiểm tra `@LazyGroup` và SQL |
| Lazy field phát N+1 | Truy cập field lần lượt trên nhiều entity | Đo SQL, dùng query/projection phù hợp |
| Thay đổi object mutable không được ghi | Mutation nội bộ không tạo field write | Dùng immutable type hoặc gán instance mới |
| Entity không có UPDATE dù field đã sửa | Dirty tracking/build enhancement hoặc lifecycle có vấn đề | Kiểm tra managed state, flush và class output |
| SQL UPDATE có nhiều cột | Không bật `@DynamicUpdate` hoặc update strategy khác | Phân biệt dirty tracking với SQL shape |
| Thêm child nhưng phía inverse không cập nhật | Association management chưa bật hoặc helper/mapping không đúng | Kiểm tra enhancer và owning side |
| Đổi enhancement config nhưng test không đổi | Incremental build giữ class cũ | Clean build và kiểm tra classpath |
| Local chạy nhưng CI không chạy lazy | Plugin chỉ được cấu hình ở module khác | Kiểm tra module chứa entity và CI task |
| Proxy vẫn xuất hiện sau enhancement | Enhancement không loại bỏ mọi proxy | Kiểm tra association và fetch mechanism thực tế |

### 19.1. Trình tự điều tra lazy basic attribute

1. Kiểm tra annotation `@Basic(fetch = LAZY)` và tên property.
2. Kiểm tra enhancer bật `enableLazyInitialization`.
3. Chạy clean build và xem log task enhancement.
4. Xác nhận class runtime đến từ output/artifact đã enhanced.
5. Kiểm tra query không có entity graph/fetch plan yêu cầu field.
6. Tránh getter bị gọi bởi mapper, logger hoặc debugger.
7. Quan sát SQL và `Hibernate.isPropertyInitialized`.

### 19.2. Trình tự điều tra dirty tracking

1. Xác nhận `enableDirtyTracking` được bật.
2. Xác nhận entity đang managed.
3. Xác nhận transaction và flush xảy ra.
4. Kiểm tra code có gán field hay chỉ sửa object mutable bên trong.
5. Phân biệt việc entity được đánh dấu dirty với số cột trong SQL UPDATE.
6. Kiểm tra bulk DML, read-only transaction hoặc detached entity có làm thay đổi luồng xử lý không.

## 20. Bài thực hành A — Lazy loading nội dung tài liệu

Một bảng `document` có 100.000 bản ghi. Mỗi row có tiêu đề nhỏ và nội dung CLOB trung bình 200 KB. Màn hình danh sách chỉ cần ID và tiêu đề; màn hình chi tiết cần nội dung.

### Yêu cầu

1. Khai báo `body` với `@Basic(fetch = FetchType.LAZY)`.
2. Đặt `body` vào lazy group riêng.
3. Bật lazy initialization trong enhancer.
4. Viết test xác nhận sau `find()` field chưa initialized.
5. Đọc `body` khi Session còn mở và kiểm tra field đã initialized.
6. Đo số SQL và lượng dữ liệu cho màn hình danh sách so với màn hình chi tiết.

Mapping gợi ý:

```java
@Entity
@Table(name = "document")
public class Document {

    @Id
    private Long id;

    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("body")
    private String body;

    public String getTitle() { return title; }
    public String getBody() { return body; }
}
```

Màn hình danh sách không truy cập `body`, nên lazy loading có thể tránh đọc cột CLOB. Màn hình chi tiết truy cập field trong transaction, Hibernate mới tải nhóm body. Nếu endpoint danh sách serialize entity và vô tình gọi `getBody()`, lợi ích sẽ mất.

## 21. Bài thực hành B — Inline dirty tracking và mutable value

```java
@Entity
public class ScheduleEntry {

    @Id
    private Long id;

    private Date scheduledAt;

    public void postponeInPlace(long millis) {
        scheduledAt.setTime(millis);
    }

    public void reschedule(Date next) {
        scheduledAt = new Date(next.getTime());
    }
}
```

Câu hỏi:

1. Vì sao `postponeInPlace()` có thể không được inline tracker nhận biết như một field assignment?
2. Vì sao `reschedule()` dễ được enhancer quan sát hơn?
3. Có kiểu dữ liệu nào phù hợp hơn `Date` mutable cho thời điểm không?
4. Bật dirty tracking có thay thế `@Version` không?

Gợi ý trả lời:

- Reference `scheduledAt` không bị gán lại; chỉ object bên trong bị mutation.
- Method gán instance mới vào field, tạo thao tác field write có thể được instrument.
- `Instant` là value type bất biến, phù hợp hơn cho thời điểm.
- Không. Dirty tracking xác định field thay đổi; `@Version` phát hiện cập nhật đồng thời.

## 22. Bài thực hành C — Phân biệt enhancement, dynamic update và optimistic lock

```java
@Entity
@DynamicUpdate
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private long version;

    private String name;

    private int quantity;
}
```

Giả sử enhancer bật cả lazy initialization và dirty tracking.

### Yêu cầu

1. Nêu trách nhiệm của inline dirty tracking.
2. Nêu trách nhiệm của `@DynamicUpdate`.
3. Nêu trách nhiệm của `@Version`.
4. Nếu chỉ đổi quantity, mô tả SQL update có thể được tạo.
5. Nếu transaction khác đã cập nhật entity trước đó, cơ chế nào phát hiện stale update?

Gợi ý trả lời:

- Inline dirty tracking ghi nhận `quantity` đã thay đổi.
- `@DynamicUpdate` cho phép SQL SET chỉ chứa cột cần cập nhật.
- `@Version` thêm điều kiện version vào UPDATE và phát hiện xung đột.
- Ba cơ chế phối hợp nhưng không thay thế nhau.

## 23. Nguyên tắc ghi nhớ

- **Bytecode enhancement biến đổi class entity đã biên dịch** để bổ sung khả năng persistence như lazy attribute loading và inline dirty tracking.
- **`@Basic(fetch = LAZY)` cho phép trì hoãn thuộc tính cơ bản**, nhưng cần enhancement phù hợp trong Hibernate để thực hiện đúng mục tiêu.
- **`@LazyGroup` nhóm lazy attribute**; truy cập một thành viên có thể tải các thuộc tính cùng nhóm.
- **Lazy loading cần persistence context còn khả năng phục vụ truy vấn.** Enhancement không cho phép tải field sau khi Session đã đóng.
- **Lazy attribute không loại bỏ N+1.** Đọc field lazy trong vòng lặp có thể tạo query phụ cho từng entity.
- **Inline dirty tracking ghi nhận field write**, giúp Hibernate biết thuộc tính nào đã thay đổi.
- **Mutation bên trong object mutable có thể không tạo field write**; ưu tiên value object bất biến hoặc gán instance mới.
- **`@DynamicUpdate` và inline dirty tracking khác trách nhiệm.** Một bên theo dõi dirty state, một bên ảnh hưởng SQL SET.
- **Dirty tracking không thay thế `@Version` hoặc transaction isolation.** Nó không tự bảo vệ cập nhật đồng thời.
- **Association management enhancement không thay thế cascade, orphan removal hoặc foreign key constraint.**
- **Build phải chạy enhancer trên đúng module/entity classes** và artifact runtime phải chứa class đã enhanced.
- **Đo SQL, trạng thái property và hiệu năng trên workload thật.** Không kết luận tính năng hoạt động chỉ từ annotation hoặc file cấu hình.

Bytecode enhancement hữu ích khi cần trì hoãn các field lớn hoặc giảm công việc theo dõi thay đổi của entity nhiều thuộc tính. Hãy chọn nhóm lazy theo cách sử dụng dữ liệu, dùng inline tracking với hiểu biết về mutable value, và tách rõ enhancement khỏi fetch plan, dynamic update và optimistic locking. Khi build pipeline và transaction boundary được kiểm soát, những khả năng này giúp Hibernate làm việc hiệu quả hơn mà vẫn giữ được hành vi dữ liệu có thể dự đoán.
