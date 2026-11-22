# Bytecode enhancement, tải lười thuộc tính và dirty tracking trong Hibernate

## 1. Vấn đề và mục tiêu

Trong Spring Data JPA, Hibernate thường là *JPA provider* chịu trách nhiệm chuyển đối tượng Java thành dữ liệu quan hệ. Một entity có thể chứa vài cột nhỏ dùng ở hầu hết màn hình và vài cột lớn chỉ cần khi mở trang chi tiết. Đồng thời, trong một transaction có nhiều entity đang được quản lý, Hibernate phải biết entity nào đã bị thay đổi để phát `UPDATE` phù hợp.

**Hibernate bytecode enhancement** là cơ chế biến đổi bytecode của class entity để bổ sung khả năng nhận biết khi ứng dụng **đọc** hoặc **ghi** một thuộc tính. Hai ứng dụng quan trọng của nó:

1. **Tải lười theo thuộc tính (*lazy attribute loading*)**: chỉ tải các thuộc tính đắt đỏ khi chúng thật sự được truy cập, thay vì luôn tải cùng phần cơ bản của entity.
2. **Theo dõi thay đổi ngay trong entity (*inline/enhanced dirty tracking*)**: ghi nhận việc gán giá trị cho thuộc tính, từ đó giảm nhu cầu so sánh toàn bộ trạng thái từng entity với snapshot khi flush.

Đây là tính năng mở rộng của **Hibernate ORM**, không phải annotation hoặc proxy AOP của Spring Data JPA. Cách hoạt động cụ thể phụ thuộc phiên bản Hibernate và cấu hình enhancement. Các API JPA như `EntityManager`, `@Basic` và `FetchType` vẫn được sử dụng bình thường.

Sau bài này, người học cần phân biệt enhancement với proxy/dirty checking truyền thống, bật và xác minh enhancement, sử dụng `@Basic(fetch = LAZY)` và `@LazyGroup`, hiểu giới hạn đối với dữ liệu mutable, kiểm thử câu SQL/tải thuộc tính, và tránh nhầm dirty tracking với lệnh SQL `UPDATE`.

## 2. Bytecode enhancement là gì?

Bytecode là mã trung gian trong file `.class` mà JVM thực thi. Hibernate có thể xử lý class entity đã biên dịch để thêm *điểm chặn* khi đọc/ghi thuộc tính và một số hợp đồng nội bộ của ORM. Lập trình viên vẫn viết một class Java như bình thường, còn class được đưa vào runtime có thêm khả năng do Hibernate cung cấp.

Ví dụ ý tưởng:

```java
@Entity
class Article {
    @Id
    Long id;

    String title;

    @Basic(fetch = FetchType.LAZY)
    String fullText;
}
```

Đoạn trên là **mã ý tưởng, không phải file độc lập có import/constructor**. Nếu enhancement hỗ trợ thuộc tính `fullText`, Hibernate có thể trả về entity đã có `id` và `title` mà chưa tải `fullText`. Khi ứng dụng đọc `fullText`, interceptor có thể phát thêm truy vấn để nạp dữ liệu. Không có enhancement phù hợp, `LAZY` trên basic property chỉ là ý định và Hibernate có thể tải luôn cột đó lúc đầu.

**Lưu ý:** enhancement khác với viết subclass proxy tại runtime. Hibernate vốn có thể dùng proxy để trì hoãn tải *toàn bộ entity liên quan* qua `@ManyToOne(fetch = LAZY)`. Bytecode enhancement cho phép intercept *thuộc tính bên trong chính entity*, kể cả kiểu cơ bản như `String` hoặc `byte[]` theo mapping. Với quan hệ đa hình, proxy vẫn có thể cần thiết; enhancement không thay thế tất cả proxy.

### 2.1. So sánh các cơ chế dễ nhầm

| Cơ chế | Tác động chính | Cần enhancement? |
| --- | --- | --- |
| JPA persistence context (L1) | Quản lý identity, trạng thái và thay đổi của entity trong một `EntityManager` | Không bắt buộc |
| Snapshot-based dirty checking | So sánh trạng thái hiện tại với snapshot khi flush | Không bắt buộc |
| Hibernate enhanced dirty tracking | Entity ghi nhận những thuộc tính đã được gán/thay đổi | Có |
| Entity proxy | Trì hoãn nạp entity ở đầu kia của association | Không nhất thiết |
| Lazy basic attribute | Trì hoãn nạp cột cơ bản/LOB của chính entity | Với Hibernate, cần enhancement thích hợp |
| `@EntityGraph` / `JOIN FETCH` | Chọn dữ liệu liên quan cần nạp cho từng truy vấn | Không phải enhancement |
| Spring `@Transactional` | Tạo ranh giới transaction theo advice/proxy của Spring | Không phải enhancement |
| Spring `@Cacheable` | Cache kết quả method | Không phải enhancement |

Enhancement chỉ thêm **khả năng**. Nó không tự biến một thuộc tính `EAGER` thành `LAZY`, không tự mở transaction và không khiến Hibernate bỏ qua mọi quyết định fetch của mapping/query.

### 2.2. Build-time hay runtime?

- **Build-time enhancement:** plugin Hibernate xử lý bytecode sau biên dịch, trước khi đóng gói hoặc chạy test. Đây là hướng dễ xác minh và tái lập trong quy trình CI.
- **Runtime enhancement:** class được xử lý khi nạp bởi môi trường/agent tích hợp hỗ trợ. Khả năng và cách bật phụ thuộc runtime, class loader và phiên bản Hibernate; không giả định rằng thêm một property vào `application.yml` sẽ thay thế build plugin ở mọi dự án.
- **Không enhancement:** Hibernate vẫn làm được phần lớn công việc JPA bằng proxy và snapshot-based dirty checking. Đừng gọi ứng dụng là sai chỉ vì chưa enhancement; lợi ích phải được đo theo workload.

Tính năng *extended bytecode enhancement* nhằm tự quản lý thêm một số tương tác với các đối tượng liên quan đã bị deprecate trong các nhánh Hibernate mới. Điều đó không đồng nghĩa mọi bytecode enhancement đều bị deprecate. Nên ưu tiên cập nhật cả hai phía quan hệ bằng helper Java rõ ràng và chỉ bật tính năng đúng nhu cầu.

## 3. Tải lười theo thuộc tính (*lazy attribute loading*)

Một entity `Document` có các thuộc tính:

- `id` và `title`: thường được hiển thị trong danh sách.
- `body`: nội dung dài, chỉ cần khi mở chi tiết.
- `internalNotes`: ghi chú nội bộ có thể rất dài, chỉ đọc bởi chức năng kiểm tra riêng.

Nếu ba nhóm dữ liệu luôn được lấy cùng một query, API danh sách có thể truyền và khởi tạo dữ liệu không dùng đến. Với enhancement và `@Basic(fetch = FetchType.LAZY)`, Hibernate có thể trì hoãn phần lớn dữ liệu của các trường nặng.

### 3.1. Mapping Java 17+: ví dụ class đầy đủ

Các file Java trong các ví dụ nằm ở package `demo.enhancement` của **một ứng dụng Spring Boot có Spring Data JPA và Hibernate được cấu hình**. Vì cần các dependency bên ngoài, chúng không được thiết kế để chạy chỉ bằng `javac Document.java`.

**`Document.java`**

```java
package demo.enhancement;

import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.LazyGroup;

@Entity
@Table(name = "documents")
public class Document {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("body")
    private String body;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("notes")
    private String internalNotes;

    @Version
    private long version;

    protected Document() {
        // JPA cần constructor không tham số.
    }

    public Document(String title, String body, String internalNotes) {
        this.title = title;
        this.body = body;
        this.internalNotes = internalNotes;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getBody() {
        return body;
    }

    public String getInternalNotes() {
        return internalNotes;
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        this.title = newTitle;
    }

    public void replaceBody(String newBody) {
        this.body = newBody;
    }
}
```

**Giải thích từng nhóm annotation:**

- `@Basic(fetch = FetchType.LAZY)` là yêu cầu/hint về cách fetch **basic attribute** theo JPA. Với Hibernate, phải có enhancement phù hợp mới mong đợi việc trì hoãn nạp cột basic.
- `@Lob` đánh dấu dữ liệu lớn; có thể map sang CLOB/text tùy dialect. `@Lob` **không tự bật lazy loading**.
- `@LazyGroup("body")` và `@LazyGroup("notes")` là annotation riêng của Hibernate: hai trường thuộc hai nhóm tải lười khác nhau. Nếu cả hai nằm chung nhóm mặc định, chạm một trường có thể kích hoạt tải cả nhóm.
- `@Version` là khóa lạc quan để phát hiện cập nhật cạnh tranh phù hợp với JPA. Nó **không phải** cấu hình dirty tracking, nhưng hữu ích để bảo vệ bản ghi khi thay đổi.
- Các getter không chứa câu SQL, nhưng trên class đã enhanced, **truy cập** một trường lazy có thể khiến Hibernate thực hiện SQL để nạp nhóm tương ứng.
- Không đặt logic ngoài ý muốn trong getter, `toString()`, `equals()`, serializer hoặc logger: việc gọi các method đó có thể vô tình truy cập `body`/`internalNotes` và kích hoạt tải dữ liệu.

### 3.2. SQL minh họa: tải ở thời điểm nào?

Giả sử `id = 7`. Đoạn service trong một transaction:

```java
Document document = entityManager.find(Document.class, 7L);
String title = document.getTitle();
String body = document.getBody();
```

Với enhancement hoạt động và mapping như phần trên, luồng SQL **có thể có ý nghĩa** như sau:

```sql
-- Lấy các cột cần cho nhóm eager:
SELECT id, title, version
FROM documents
WHERE id = 7;

-- Khi lần đầu đọc nhóm body:
SELECT body
FROM documents
WHERE id = 7;
```

SQL chỉ minh họa, **không phải output cam kết**: provider, dialect, mapping phụ, fetch plan, cache và version có thể thay đổi cột/query thực tế. Quan trọng là lúc `find` có thể chưa tải `body`, còn lúc gọi `getBody()` mới có thể nạp thêm nhóm `body`. Nếu sau đó đọc `getInternalNotes()` thì nhóm `notes` có thể cần một lần tải riêng.

**Không hiểu nhầm:** một query dùng `JOIN FETCH`, entity graph hoặc projection trực tiếp chọn cột cần dùng có thể thay đổi kế hoạch nạp; `@LazyGroup` cũng không phải công cụ giải quyết N+1 query. Đọc một thuộc tính lazy của 100 entity có thể tạo tới 100 lần tải bổ sung trong trường hợp không batching/caching phù hợp.

### 3.3. Nhóm lazy và chi phí round-trip

Hibernate có khái niệm *lazy group*: nhiều thuộc tính lazy trong một nhóm có thể được nạp cùng nhau khi một thuộc tính thuộc nhóm đó được truy cập.

| Mapping | Đọc `body` | Đọc `internalNotes` |
| --- | --- | --- |
| Cả hai lazy nhưng cùng nhóm mặc định | Có thể nạp cả hai cùng lần | Thường đã có dữ liệu sau lần đầu |
| Hai `@LazyGroup` khác nhau | Nạp nhóm `body` | Nạp nhóm `notes` khi được dùng |
| Cả hai eager hoặc enhancement không có tác dụng | Có thể đã được nạp ngay từ query ban đầu | Không cần tải riêng, nhưng đã trả phí từ đầu |

Tách nhóm khi tần suất truy cập hai trường độc lập. Nếu cả hai luôn được dùng cùng nhau, quá nhiều nhóm có thể tăng round-trip. **Tối ưu bằng số byte tải thực tế, số query và thời gian response**, không phải cứ nhiều lazy group là nhanh hơn.

### 3.4. Kiểm tra đã tải thuộc tính hay chưa

Jakarta Persistence hỗ trợ API chuẩn:

```java
jakarta.persistence.PersistenceUnitUtil loadUtil =
        entityManager.getEntityManagerFactory()
                .getPersistenceUnitUtil();

boolean bodyLoaded = loadUtil.isLoaded(document, "body");
```

Đây là đoạn mã chạy trong môi trường JPA có `entityManager` và `document`, không phải chương trình độc lập. Với mapping và enhancement phù hợp, ngay sau `find` mà chưa đọc `body`, `bodyLoaded` được kỳ vọng là `false`; sau `getBody()`, thường là `true`.

Với Hibernate có thể dùng `Hibernate.isPropertyInitialized(document, "body")` để chẩn đoán, nhưng API chuẩn `PersistenceUnitUtil` phù hợp hơn nếu chỉ cần biết trạng thái loaded. **Kết quả isLoaded là trạng thái của object đang xét**, không khẳng định tất cả repository queries hoặc mọi phiên chạy đều có cùng số câu SQL.

### 3.5. Lazy và ranh giới transaction/session

Giả sử một transaction đã đóng và entity trở thành detached:

```java
Document doc = documentService.loadDocument(id);  // Transaction kết thúc.
String body = doc.getBody();                        // Có thể thất bại.
```

Nếu `body` vẫn chưa được khởi tạo và Hibernate cần session để tải, truy cập có thể ném `LazyInitializationException`. Enhancement **không** mang theo kết nối database hoặc transaction vào object.

Cách thiết kế service tốt hơn là nạp dữ liệu cần thiết **khi session còn hoạt động**, rồi trả DTO rõ ràng:

```java
package demo.enhancement;

public record DocumentDetail(Long id, String title, String body) {
}
```

```java
package demo.enhancement;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;

    public DocumentQueryService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public DocumentDetail getDetail(Long id) {
        Document d = repository.findById(id).orElseThrow();
        return new DocumentDetail(d.getId(), d.getTitle(), d.getBody());
    }
}
```

Trong `getDetail`, đọc `getBody()` khi session còn mở, DTO `DocumentDetail` không còn lazy field. Ví dụ này nạp nội dung vì endpoint chi tiết thực sự cần nó; endpoint danh sách nên chọn projection hoặc query chỉ lấy các cột hiển thị thay vì gọi getter không cần thiết.

### 3.6. Lazy basic khác lazy association

- `@OneToMany`, `@ManyToMany` được khai báo `LAZY` theo mặc định JPA; Hibernate thường dùng collection wrapper để trì hoãn truy vấn.
- `@ManyToOne` và `@OneToOne` mặc định `EAGER` theo JPA, trừ khi chọn `fetch = LAZY`. Hibernate có thể dùng proxy, enhancement hoặc chiến lược khác tùy quan hệ và khả năng xác định target.
- `@Basic(fetch = LAZY)` nhắm **thuộc tính cơ bản của chính entity**, ví dụ `String body`. Muốn Hibernate thực hiện việc này đáng tin cậy, phải xác minh entity đã enhanced.
- Enhancement có thể hỗ trợ *no-proxy lazy to-one* trong trường hợp phù hợp; **không bảo đảm mọi quan hệ đa hình/one-to-one đều không cần proxy**. Đừng đổi toàn bộ mapping chỉ vì đã bật plugin.
- L2 cache hoặc query cache nếu được bật có thể thay đổi quan sát SQL mà không thay đổi ý nghĩa fetch. Khi benchmark, phân biệt cache hit với behavior của enhancement.

## 4. Bật enhancement ở giai đoạn build

Cách cụ thể phụ thuộc công cụ build và **phiên bản Hibernate ORM thực sự được ứng dụng sử dụng**. Trong Spring Boot, dependency management thường chọn phiên bản Hibernate. Không lấy một phiên bản plugin trên mạng rồi ép runtime Hibernate khác dòng tương thích.

### 4.1. Gradle (Groovy DSL) — ví dụ một dự án dùng Hibernate ORM 7.2

Ví dụ trong `build.gradle` cho một dự án Hibernate 7.2.x tương thích:

```groovy
plugins {
    id 'java'
    id 'org.hibernate.orm' version '7.2.25.Final'
}

hibernate {
    enhancement {}
}
```

Khối cấu hình trên được tài liệu Hibernate 7.2 sử dụng để kích hoạt enhancement. **Dấu `{}` sau `enhancement` là quan trọng**: một số ví dụ cũ viết `hibernate { enhancement }` có thể chỉ gọi getter trong Groovy mà không thực sự bật enhancement. Khi dự án dùng Hibernate 6.x hoặc 7.4.x, dùng plugin cùng dòng/phiên bản được hỗ trợ cho runtime đó; đoạn trên chỉ minh họa cú pháp Hibernate 7.2, không phải chỉ dẫn thay đổi phiên bản cho mọi Spring Boot application.

Quy trình kiểm tra một dự án Gradle đã thiết lập:

```bash
./gradlew clean test
```

Trên Windows, dùng:

```powershell
.\gradlew.bat clean test
```

Dự án cần có Java plugin, source sets và dependency Hibernate/Spring Data JPA phù hợp. Nếu dùng Maven, Hibernate cung cấp `hibernate-enhance-maven-plugin` cho build-time enhancement; hãy đối chiếu cấu hình plugin và goal chính xác với dòng Hibernate đang dùng. Không gọi chung một property của Spring Boot là bằng chứng chắc chắn rằng bytecode đã enhanced.

### 4.2. Cơ chế triển khai trong CI và IDE

1. Biên dịch class entity theo Java 17+ và chạy task enhancement bằng build pipeline.
2. Dùng artifact **đã enhanced** cho test, ứng dụng chạy thật, Docker image hoặc JAR. Không để bước IDE run sử dụng bản `.class` chưa qua task enhancement trong khi CI sử dụng bản enhanced.
3. Chạy test xác nhận `@Basic(LAZY)` có hiệu lực. Test nên fail nếu bỏ plugin, nhờ vậy không âm thầm mất tối ưu khi đổi cấu hình build.
4. Với dự án nhiều module, kiểm tra module **chứa entity classes** được enhancement; chỉ bật plugin ở ứng dụng tầng trên không đảm bảo các class đã đóng gói trong thư viện riêng cũng được biến đổi.
5. Với framework có enhancement riêng (ví dụ môi trường build-time augmentation), theo hướng dẫn tích hợp của framework và tránh xử lý trùng không kiểm soát.

### 4.3. Có thể kiểm tra enhancement bằng dấu hiệu nào?

- **Hành vi JPA:** sau khi `find`, `PersistenceUnitUtil.isLoaded(entity, "body")` là `false`, truy cập getter thì thành `true`. Đây là kiểm tra quan trọng nhất nếu mục tiêu là attribute lazy.
- **Contract nội bộ Hibernate:** enhanced entity có thể triển khai `org.hibernate.engine.spi.PersistentAttributeInterceptable`; entity dùng inline tracking có thể triển khai `org.hibernate.engine.spi.SelfDirtinessTracker`. Chỉ dùng để chẩn đoán hoặc test tích hợp theo phiên bản; không thiết kế domain code phụ thuộc các interface nội bộ này.
- **SQL log/statement inspector:** query đầu không chọn cột lazy, truy cập getter mới có SELECT khác khi cần.
- **Artifact thực tế:** kiểm tra bytecode trong class đã đóng gói, thay vì chỉ kiểm tra source file hoặc setting trong IDE.
- **Regression test:** bỏ enhancement trong một nhánh thử nghiệm thì test về lazy attribute phải phát hiện thay đổi, nếu dữ liệu/dialect thỏa điều kiện.

Không lấy việc ứng dụng khởi động thành công làm bằng chứng. Hibernate vẫn chạy tốt khi không có enhancement nên tính năng tối ưu có thể mất mà không có exception.

## 5. Dirty checking truyền thống và enhanced dirty tracking

### 5.1. Snapshot-based dirty checking

Khi entity `Document` được tải vào persistence context, Hibernate có thể giữ snapshot trạng thái lúc nạp. Nếu đổi `title`, trong đợt `flush` nó đối chiếu giá trị hiện tại với snapshot để quyết định có cần `UPDATE` không.

```text
SELECT document -> managed entity + snapshot
                          |
                    rename("Tên mới")
                          |
                   transaction flush
                          |
           so sánh thuộc tính với snapshot
                          |
           nếu có thay đổi: SQL UPDATE
```

Cách này mạnh vì có thể phát hiện nhiều thay đổi giá trị dù ứng dụng không gán lại reference của thuộc tính, tùy chiến lược xử lý mutability của kiểu dữ liệu. Đổi lại, với hàng nghìn managed entities hoặc nhiều thuộc tính, việc so sánh có chi phí CPU/bộ nhớ.

### 5.2. Enhanced dirty tracking (inline)

Khi enhancement bật khả năng theo dõi thay đổi, bytecode có thể đánh dấu thuộc tính mỗi lần nó được ghi. Khi flush, Hibernate có thể hỏi entity “những thuộc tính nào đã thay đổi?” thay vì phải so sánh mọi property của mọi entity.

```text
SELECT document -> enhanced managed entity
                          |
                    rename("Tên mới")
                          |
                 ghi nhận field "title"
                          |
                   transaction flush
                          |
                 truy vấn dirty state
                          |
           nếu có thay đổi: SQL UPDATE
```

**Đây là tối ưu cách *phát hiện* thay đổi, không phải việc bật/tắt mọi lệnh `UPDATE`.** Dirty tracking không tự quyết định Hibernate sẽ đưa bao nhiêu cột vào câu SQL. Theo cấu hình mặc định, Hibernate có thể tạo UPDATE gồm nhiều cột; `@DynamicUpdate` là một cơ chế riêng để sinh SQL dựa trên các cột thay đổi (cần cân nhắc cache prepared statements và tính nhất quán). Enhancement cũng không thay `@Version` hoặc transaction.

### 5.3. Ví dụ update managed entity qua Spring Data JPA

**`DocumentRepository.java`**

```java
package demo.enhancement;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {
}
```

**`DocumentCommandService.java`**

```java
package demo.enhancement;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository repository;

    public DocumentCommandService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(Long id, String newTitle) {
        Document document = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Document not found"));
        document.rename(newTitle);
        // Managed entity: Hibernate tự phát hiện thay đổi lúc flush/commit.
    }
}
```

Với entity managed trong transaction, không bắt buộc gọi `repository.save(document)` sau `rename` chỉ để dirty checking chạy. Điều kiện nền tảng vẫn là **entity còn managed, transaction cho phép ghi, và thao tác thực sự sửa trạng thái lưu trữ**. Nếu entity detached, sửa object ngoài transaction không tự ghi vào DB.

### 5.4. Vì sao dirty tracking không đồng nghĩa `@DynamicUpdate`?

Giả sử row có các cột `title`, `body`, `internal_notes`, `version`. Khi ứng dụng chỉ đổi `title`:

- **Dirty detection:** quyết định `title` có được xem là thay đổi hay không và có cần update entity hay không.
- **SQL update shape:** quyết định SQL có những cột nào trong `SET`; mặc định provider có thể cập nhật nhiều cột được ánh xạ.
- **Optimistic locking:** `@Version` thêm kiểm tra phiên bản để tránh ghi đè cập nhật cạnh tranh theo quy ước.
- **Flush/transaction:** quyết định lúc nào SQL được gửi và khi nào commit có hiệu lực.

Khi cần cân nhắc chỉ update cột đã đổi, Hibernate có `@DynamicUpdate`:

```java
// Đây là annotation Hibernate-specific có thể đặt trên class Document:
// @org.hibernate.annotations.DynamicUpdate
```

Đoạn trên là **dòng minh họa**, không được tự chèn vào entity nếu chưa benchmark. `@DynamicUpdate` có thể làm tăng số biến thể câu SQL cần chuẩn bị, tương tác với optimistic locking và mapping update. Nếu không có `@Version`, cập nhật chọn lọc các cột cũng cần được đánh giá kỹ về lost update và invariant của bản ghi.

### 5.5. Giới hạn với dữ liệu mutable

Enhanced tracking dựa nhiều vào việc nhận biết **gán lại thuộc tính**. Một object có thể đổi **bên trong** mà reference của thuộc tính không đổi. Ví dụ:

```java
byte[] bytes = document.getAttachmentBytes();
bytes[0] = 9;        // Đổi phần tử trong mảng, không gán lại field.
```

Đây là đoạn mã minh họa cho một entity giả định có getter `getAttachmentBytes()`, **không phải method của class `Document` ở phần 3**. Interceptor chỉ nhìn thao tác ghi field có thể không thấy thay đổi `bytes[0]`. Tùy kiểu, Hibernate có thể dùng mutability plan/snapshot bổ sung, nhưng không nên mặc định mọi sửa đổi *in-place* đều được phát hiện an toàn bởi inline tracking.

Cách thiết kế an toàn hơn:

```java
public void replaceAttachment(byte[] newBytes) {
    this.attachmentBytes = newBytes.clone();
}
```

Đây là **method minh họa cho entity có field `attachmentBytes`**. Nó thay reference/giá trị của field bằng dữ liệu mới và không giữ mảng có thể bị caller sửa tiếp. Với kiểu dữ liệu mutable khác như `Date`, `Calendar`, `byte[]`, document JSON, embeddable chứa state hoặc custom user type, cần xem mutability plan và test thực tế. Không áp dụng `@Immutable` cho dữ liệu mà ứng dụng vẫn sửa nội bộ.

**Mẹo thiết kế:** ưu tiên value object bất biến, setter/domain method thay toàn bộ value khi cần, và integration test xác minh DB đã thay đổi. Khi cần sửa cấu trúc lồng nhau trong embeddable hoặc collection, xem riêng cơ chế theo dõi của mapping đó.

### 5.6. Dirty checking có thể không chạy hoặc không ghi dù entity đổi

- Entity đang **detached** ngoài persistence context: thay đổi không được tự đồng bộ.
- Query được cấu hình read-only, entity được đặt read-only hoặc transaction/session có trạng thái read-only theo chính sách Hibernate: không nên kỳ vọng flush update thuộc tính thông thường.
- Gọi `@Modifying` với JPQL bulk update/delete: truy vấn thao tác trực tiếp trên database và **bỏ qua dirty checking, lifecycle callbacks của từng entity**; persistence context đang giữ entity cũ có thể stale.
- Dữ liệu được sửa qua JDBC/hệ thống khác: Hibernate không nhận được thao tác ghi của entity.
- Chưa đến thời điểm flush/commit: đổi field trong bộ nhớ không đồng nghĩa SQL đã chạy.
- Gán giá trị trùng hoặc logic mapping không xem là dirty: không tự tạo nhu cầu UPDATE.
- Transaction rollback: dù SQL đã gửi trong flush, thay đổi không được commit.

Đừng kích hoạt enhancement với kỳ vọng nó sẽ nhận diện mọi SQL từ bên ngoài hoặc thay thế việc clear/refresh persistence context.

## 6. Ví dụ kiểm thử tích hợp chính xác hành vi

Các file ở phần 3 và 5 có thể dùng trong dự án Spring Boot đã có `spring-boot-starter-data-jpa`. Để chạy test dưới đây, cần thêm test dependencies (`spring-boot-starter-test`, H2 test runtime), build-time enhancement đã bật cho entity module, và Spring Boot configuration quét package `demo.enhancement`. **Hãy dùng phiên bản plugin Hibernate tương thích với phiên bản Hibernate mà Spring Boot đang dùng**, thay vì sao chép mù phiên bản minh họa 7.2 của phần 4.

**`DocumentEnhancementJpaTest.java`** tại `src/test/java/demo/enhancement/`:

```java
package demo.enhancement;

import jakarta.persistence.PersistenceUnitUtil;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class DocumentEnhancementJpaTest {
    @Autowired
    TestEntityManager testEntityManager;

    @Test
    void lazyGroupsLoadIndependently() {
        Document original = new Document(
                "Hướng dẫn", "Nội dung dài", "Ghi chú riêng");
        testEntityManager.persistAndFlush(original);
        Long id = original.getId();

        testEntityManager.clear(); // Đảm bảo lấy lại từ persistence context mới.
        Document loaded = testEntityManager.find(Document.class, id);

        PersistenceUnitUtil util = testEntityManager
                .getEntityManager()
                .getEntityManagerFactory()
                .getPersistenceUnitUtil();

        assertThat(util.isLoaded(loaded, "body")).isFalse();
        assertThat(util.isLoaded(loaded, "internalNotes")).isFalse();

        assertThat(loaded.getBody()).isEqualTo("Nội dung dài");
        assertThat(util.isLoaded(loaded, "body")).isTrue();
        assertThat(util.isLoaded(loaded, "internalNotes")).isFalse();

        assertThat(loaded.getInternalNotes()).isEqualTo("Ghi chú riêng");
        assertThat(util.isLoaded(loaded, "internalNotes")).isTrue();
    }

    @Test
    void managedChangeSurvivesFlushAndReload() {
        Document original = new Document(
                "Bản cũ", "Nội dung", "Ghi chú");
        testEntityManager.persistAndFlush(original);
        Long id = original.getId();

        testEntityManager.clear();
        Document loaded = testEntityManager.find(Document.class, id);
        loaded.rename("Bản mới");

        testEntityManager.flush();
        testEntityManager.clear();

        Document reloaded = testEntityManager.find(Document.class, id);
        assertThat(reloaded.getTitle()).isEqualTo("Bản mới");
    }
}
```

Test 1 kiểm tra phần **lazy attribute/`@LazyGroup`**, và sẽ giúp phát hiện việc thiếu enhancement nếu provider tải ngay các trường. Test 2 kiểm chứng **managed entity changes được ghi qua flush và đọc lại**. Tuy nhiên test 2 tự nó *không chứng minh* enhanced inline tracking: snapshot-based dirty checking cũng tạo kết quả đúng. Muốn xác minh interceptor thật sự được cài, có thể thêm kiểm tra chẩn đoán riêng:

```java
assertThat(loaded)
        .isInstanceOf(org.hibernate.engine.spi.SelfDirtinessTracker.class);
```

Đây là assertion tùy chọn cho cấu hình bật **enhanced dirty tracking** (đặt sau khi `loaded` được nạp), dựa vào API nội bộ Hibernate; nếu một cấu hình chỉ enhancement để lazy loading mà không bật inline tracking thì không áp dụng assertion này. Nên pin test tương thích theo version, tránh dùng type nội bộ trong code nghiệp vụ.

Lệnh chạy nếu dự án có Gradle Wrapper:

```bash
./gradlew test --tests "demo.enhancement.DocumentEnhancementJpaTest"
```

Trên Windows: `.\gradlew.bat test --tests "demo.enhancement.DocumentEnhancementJpaTest"`. Không được giả định có thể chạy những file trên độc lập mà không cấu hình ứng dụng/database. Nếu dự án dùng Spring Boot 4, một số package test auto-configuration đã thay đổi; điều chỉnh annotation/import của test theo đúng tài liệu phiên bản đang dùng.

### 6.1. Cách đọc kết quả test

| Quan sát | Cách diễn giải |
| --- | --- |
| `isLoaded(loaded, "body") == false` trước getter | Field chưa được coi là loaded trong entity hiện tại |
| Đọc `getBody()` rồi trạng thái thành `true` | Nhóm body được khởi tạo theo mapping |
| `internalNotes` còn false sau đọc `body` | Hai lazy group độc lập đúng dự định |
| Sau đổi `title`, flush/clear và nạp lại thấy tên mới | Managed entity thay đổi được đồng bộ vào database |
| Có SELECT cột `body` ngay ở query đầu | Enhancement không hoạt động, mapping/fetch plan yêu cầu eager, hoặc nguyên nhân khác cần kiểm tra |
| Có nhiều SELECT cho các getter của nhiều entity | Rủi ro N+1 ở cấp thuộc tính; cân nhắc projection/fetch phù hợp |
| Chỉ test update pass, không có test loaded-state | Chưa đủ bằng chứng enhancement có hiệu lực |

**Đối với SQL timing**, bật logging có kiểm soát trong test hoặc dùng Hibernate `StatementInspector`/statistics để xác định câu query thực tế. Các câu SQL minh họa trong bài không phải stdout hoặc SQL được bảo đảm ở mọi dialect.

## 7. Bật enhancement không xóa các bài toán Hibernate khác

### 7.1. N+1 query vẫn có thể xảy ra

Khi một endpoint nạp 100 `Document` với `body` chưa loaded rồi sau đó tuần tự gọi `getBody()` cho từng entity, Hibernate có thể phát nhiều SELECT bổ sung. Enhancement giúp tránh tải khi **không cần nội dung**, nhưng nếu thực sự cần body cho cả 100, projection/DTO query hoặc phương án fetch thích hợp có thể tốt hơn.

Chọn chiến lược theo use case:

- **Danh sách:** trả `id`, `title`, `updatedAt` bằng projection hoặc DTO. Tránh gọi getter body trong mapper/logger.
- **Chi tiết:** chủ động tải body trong transaction, trả DTO có nội dung. Không đẩy entity lazy ra ngoài transaction để serializer tự xử lý.
- **Báo cáo hàng loạt:** thiết kế query đọc nhiều cột cần dùng theo một lần truy vấn thay vì lazy-load từng entity.
- **Thao tác ghi:** chỉ nạp những trạng thái cần áp dụng invariant/locking; vẫn giữ optimistic locking và transaction.

### 7.2. Không nhầm với Open Session in View (OSIV)

Nếu OSIV được bật, việc serializer vô tình truy cập lazy attribute sau khi controller/service transaction đã kết thúc có thể vẫn gây SQL vì session còn mở ở request. Điều này dễ che giấu query ngoài dự kiến và khó đo số lượng truy vấn.

Đừng dựa vào OSIV để hợp thức hóa mọi getter lazy ở view. Hãy định nghĩa ranh giới truy cập dữ liệu ngay trong service/query, build DTO, và đo số query trên endpoint thật.

### 7.3. Dirty tracking không giải quyết concurrency

Hai transaction có thể cùng đọc một entity rồi cùng cập nhật. Enhanced tracking chỉ nhận biết thay đổi **trên từng entity local**. Nó không tự ngăn lost update, phantom read hoặc conflict giữa các hệ thống. Dùng `@Version`, transaction isolation, khóa bi quan khi thực sự cần, và test cạnh tranh.

Ví dụ `@Version` trong `Document` làm Hibernate kiểm tra version khi update theo mapping phù hợp. Nếu một hệ thống ngoài thực hiện SQL trực tiếp nhưng bỏ qua quy ước tăng `version`, bảo vệ này có thể mất hiệu lực. Enhancement không thay thế hợp đồng ghi chung đó.

### 7.4. Không nhầm dirty tracking với audit/history

Enhanced tracking có thể nói thuộc tính nào đã đổi trong một persistence context, nhưng không tự lưu **lịch sử phiên bản bản ghi** hoặc nhật ký ai đã chỉnh sửa. Muốn audit, sử dụng Envers, domain event/outbox hoặc audit log được thiết kế riêng. Nếu có auditing annotation của Spring Data như `@LastModifiedDate`, đó là tính năng khác với enhancement và vẫn cần cấu hình auditing thích hợp.

### 7.5. Entity serialization và các method tiện ích

Một lỗi rất thường gặp:

```java
@Override
public String toString() {
    return "Document{title='" + title
            + "', body='" + body + "'}";
}
```

Trong entity enhanced, `toString()` đọc `body` có thể kích hoạt load cột nặng, gây SQL trong logging hoặc exception khi detached. Tương tự, `equals()/hashCode()` dựa trên lazy field, Lombok `@Data` sinh getter/toString/equality mặc định, JSON serializer hoặc mapper tự động có thể tải ngoài ý muốn. Nên tránh đưa lazy-heavy fields vào các method này và sử dụng DTO xác định rõ dữ liệu cần xuất ra.

## 8. Khi nào nên dùng?

| Tình huống | Nhận định |
| --- | --- |
| Entity chứa LOB/text/blob lớn, chỉ một số endpoint cần | Attribute lazy + enhancement có thể giảm I/O đáng kể |
| Persistence context có rất nhiều entity được quản lý, flush thường xuyên | Enhanced dirty tracking có thể giảm chi phí snapshot/diff |
| Entity nhỏ, hầu như tất cả field luôn được đọc | Lazy từng field có thể tăng round-trip mà không lợi ích |
| Ứng dụng đọc bằng projection và update qua JPQL bulk | Enhancement entity có thể ít ảnh hưởng tới đường truy vấn chính |
| Mutable arrays/JSON/custom types được sửa in-place thường xuyên | Cần kiểm thử kỹ hoặc dùng immutable/replacement pattern; đừng tin tracking mù |
| Hệ thống cần portable giữa nhiều JPA provider | `@LazyGroup` và cơ chế plugin là Hibernate-specific; ưu tiên JPA query/projection nơi phù hợp |
| Endpoint có nhiều associations chéo | Đánh giá entity graph/batch fetch và N+1; enhancement một mình chưa đủ |

Điểm đo thực tế có thể gồm: response time p50/p95, kích thước hàng/cột trả về, số SELECT trên request, thời gian flush, bộ nhớ heap của persistence context và tính đúng của kết quả sau commit. Tối ưu phải có test đối chiếu **bật/tắt enhancement với cùng workload**; benchmark entity microtest đơn lẻ dễ bỏ qua chi phí mạng và truy vấn.

## 9. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `@Basic(fetch=LAZY)` nhưng field đã loaded ngay sau find | Không enhancement; plugin chưa chạy; entity module chưa enhanced; query fetch plan lấy trường đó | Kiểm tra artifact thực tế, test `isLoaded` và SQL; cấu hình build đúng dòng Hibernate |
| Chỉ bật property Hibernate nhưng lazy basic vẫn không hoạt động | Property runtime không thay được bước enhancement của class trong môi trường hiện tại | Dùng build-time enhancement được hỗ trợ và test |
| Lazy field bị truy cập ngoài transaction ném `LazyInitializationException` | Entity detached, session đã đóng | Nạp dữ liệu trước khi tạo DTO trong transaction |
| Đọc danh sách có hàng chục/hàng trăm SQL phụ | Nhiều getter lazy được truy cập theo vòng lặp | Dùng DTO/projection/fetch plan cho tác vụ đọc hàng loạt |
| `@LazyGroup` không tách được hai field | Cùng nhóm, enhancement thiếu hoặc query đã eager-load | Kiểm tra tên nhóm, loaded state, SQL và mapping |
| Đổi phần tử của `byte[]` nhưng DB không cập nhật | Thay đổi nội bộ mà interceptor không nhận thấy | Gán lại array/value mới và test flush/clear |
| Đã sửa entity nhưng không có `UPDATE` | Detached, read-only, chưa flush, rollback hoặc không có dirty change | Xác minh managed state, transaction, flush và query path |
| Bật enhanced dirty tracking nhưng SQL vẫn cập nhật nhiều cột | Dirty detection khác SQL update shape | Đánh giá `@DynamicUpdate` độc lập; kiểm thử concurrency |
| `@Modifying` bulk query không kích hoạt entity listener | Bulk update bỏ qua chu trình entity-level | Xử lý clear/refresh, auditing và cache invalidation riêng |
| IDE chạy khác CI về số SELECT | IDE dùng class chưa enhanced, CI có task enhancement | Căn chỉnh build/run classpath và artifact được đóng gói |
| Bật enhancement khiến mapper/logging có SQL bất ngờ | Getter/toString/serializer đọc field lazy | Tránh serialize entity trực tiếp, dùng DTO |

## 10. Quy trình áp dụng cho một module Spring Data JPA

1. **Xác nhận vấn đề cần cải thiện:** cột rất lớn bị fetch không cần, hoặc chi phí dirty checking của persistence context đã được đo là đáng kể.
2. **Kiểm tra phiên bản:** ghi nhận Hibernate runtime từ dependency graph/BOM và plugin enhancement tương thích; không tự upgrade Hibernate phá hợp đồng Spring Boot.
3. **Thiết kế mapping:** chọn thuộc tính `@Basic(fetch=LAZY)`; nhóm độc lập bằng `@LazyGroup` nếu cần. Tránh lazy theo thói quen ở mọi cột nhỏ.
4. **Bật enhancement trong build pipeline**, bảo đảm mọi entity module thật sự được xử lý trước test/package.
5. **Test trước/sau đọc field:** flush, clear, nạp entity lại; dùng `PersistenceUnitUtil.isLoaded` và quan sát SQL. Test trong transaction và test behavior khi detached.
6. **Kiểm tra dirty tracking:** sửa thuộc tính managed, flush/clear/reload; nếu cần xác nhận inline tracker, dùng assertion chẩn đoán tương thích Hibernate version.
7. **Rà soát dữ liệu mutable:** không dựa vào mutation nội bộ của `byte[]`/JSON/custom object nếu chưa test; ưu tiên thay bằng value object mới và custom mutability plan đúng khi cần.
8. **Rà soát endpoint và transaction:** DTO/projection, xử lý N+1, OSIV, serialization, giới hạn số query.
9. **Benchmark workload thật** và quan sát regression sau thay đổi build, framework, plugin hoặc cách map entity.
10. **Giữ kiểm thử CI** cho semantics lazy và cập nhật DB; không đánh đổi tính đúng dữ liệu lấy lợi ích CPU dự kiến.

### Bài tập tự kiểm tra

**Bài 1.** Một entity có `@Lob @Basic(fetch=LAZY) String body`, nhưng sau `find`, `isLoaded(entity, "body")` trả `true`. Có phải JPA vi phạm hợp đồng? **Đáp án:** Không nhất thiết. `FetchType.LAZY` cho basic là hint; với Hibernate cần enhancement và còn phụ thuộc fetch plan. Kiểm tra plugin, class artifact và query thực tế.

**Bài 2.** Có hai field lazy `body` và `internalNotes`. Làm sao để đọc `body` không kéo luôn ghi chú? **Đáp án:** Dùng hai `@LazyGroup` khác nhau và kiểm chứng bằng `isLoaded`/SQL khi enhancement hoạt động.

**Bài 3.** Enhanced dirty tracking bật, nhưng app thay `image[0]` trên `byte[] image` mà không gán lại field. Có chắc thay đổi xuống DB? **Đáp án:** Không. Mutation in-place có thể vượt khỏi intercept ghi field; cần kiểm thử hoặc thay bằng value mới.

**Bài 4.** Đổi `document.rename("A")` trong một `@Transactional`, có bắt buộc gọi `repository.save(document)` để Hibernate biết entity thay đổi? **Đáp án:** Không, nếu entity đang managed. Hibernate có dirty checking và xử lý khi flush/commit, có hoặc không có enhancement.

**Bài 5.** Enhanced tracking làm SQL `UPDATE` chỉ chứa một cột đã đổi? **Đáp án:** Không mặc nhiên; nó giúp biết thuộc tính dirty. SQL update shape là quyết định khác, có thể liên quan `@DynamicUpdate`.

**Bài 6.** Bật enhancement có loại bỏ `LazyInitializationException` ngoài transaction không? **Đáp án:** Không. Khi field chưa loaded mà object detached, Hibernate vẫn cần session để tải. Hãy lấy dữ liệu cần thiết trước khi trả DTO.

## 11. Ghi nhớ và tài liệu tham khảo

- Bytecode enhancement thêm logic interception vào **bytecode entity**, khác với proxy AOP của Spring.
- `@Basic(fetch = LAZY)` trên basic field thường cần enhancement để Hibernate thực sự trì hoãn tải. `@LazyGroup` nhóm các thuộc tính được tải cùng nhau.
- Enhanced dirty tracking ghi nhận các field thay đổi và có thể giảm chi phí flush, nhưng **không đảm bảo** nhận biết mọi mutation nội bộ của giá trị mutable, không thay transaction/version và không tự tạo partial SQL update.
- Muốn chứng minh chức năng đúng, hãy **nạp lại entity sau flush/clear**, dùng `PersistenceUnitUtil.isLoaded`, xem SQL và bảo đảm artifact chạy thực sự đã enhanced.
- Chỉ bật tối ưu sau khi đã hiểu mục tiêu đọc/ghi; khi dữ liệu cần cho một danh sách/query, projection và fetch plan rõ ràng thường dễ kiểm soát hơn.

Tài liệu chính thức để đối chiếu theo phiên bản Hibernate thực tế:

- Hibernate ORM 7.2 — User Guide, mục Bytecode Enhancement: https://docs.hibernate.org/orm/7.2/userguide/html_single/#BytecodeEnhancement
- Hibernate ORM 7.2 — Introduction, mục Using the bytecode enhancer (cú pháp Gradle): https://docs.hibernate.org/orm/7.2/introduction/html_single/#bytecode-enhancement
- Hibernate ORM 7.4 — User Guide (nhánh ổn định mới hơn, cần đối chiếu thay đổi): https://docs.hibernate.org/stable/orm/userguide/html_single/
- Hibernate Tooling — Gradle/Maven plugin: https://hibernate.org/orm/tooling/
- Jakarta Persistence — `@Basic`, `FetchType`, `PersistenceUnitUtil`: https://jakarta.ee/specifications/persistence/
- Spring Data JPA — Reference Documentation: https://docs.spring.io/spring-data/jpa/reference/
