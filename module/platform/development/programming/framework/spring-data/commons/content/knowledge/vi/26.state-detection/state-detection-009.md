# Ảnh hưởng đến save, auditing và optimistic locking

## 1. Một quyết định trạng thái, ba hệ quả

Khi nhận một entity để lưu, hạ tầng Spring Data cần xác định entity đó được xem là **mới** hay **không mới**. Kết quả này có thể ảnh hưởng đến đường ghi mà repository chọn, cách điền metadata auditing và cách áp dụng version cho lần ghi.

Ba trách nhiệm có liên quan nhưng không đồng nhất:

| Trách nhiệm | Câu hỏi cần trả lời |
|---|---|
| State detection | Entity hiện được xem là mới hay không? |
| Auditing | Ai tạo/sửa, vào lúc nào, theo lifecycle đang được áp dụng? |
| Optimistic locking | Lần ghi có dựa trên phiên bản còn hợp lệ không? |

Trong **SPRING_DATA_COMMONS**, các abstraction và metadata chung giúp nối những trách nhiệm này. Module lưu trữ quyết định cách sử dụng chúng trong pipeline thực tế. Không có một thứ tự callback, một câu SQL hay một semantics `save` dùng chung tuyệt đối cho mọi datastore.

Bài học tập trung vào hệ quả thực tế: phân loại sai có thể chọn sai đường ghi, làm metadata tạo/sửa không đúng kỳ vọng hoặc khiến cơ chế version bị áp dụng trên trạng thái không phù hợp. Ngược lại, phân loại đúng vẫn chưa tự bảo đảm giao dịch đã commit hoặc mọi xung đột đã được xử lý.

## 2. Nhắc lại đủ để đọc đúng luồng lưu

### 2.1. “Không mới” không phải là một query tồn tại

State detection thường dựa vào dữ liệu của object và metadata: ID, version, `Persistable` hoặc một chiến lược hạ tầng tùy chỉnh.

Ví dụ, trong mô hình chỉ kiểm tra ID, ID tham chiếu `null` thường làm entity được coi là mới. ID non-null làm entity được coi là không mới, dù ứng dụng có thể vừa tự cấp ID và chưa lưu lần nào.

Nếu module áp dụng chiến lược ưu tiên version tham chiếu, entity có ID non-null nhưng version `null` vẫn có thể được coi là mới.

Không đồng nhất các kết quả này với việc datastore đã xác nhận có hoặc không có bản ghi.

### 2.2. Bảng trạng thái phải gắn với chiến lược đang dùng

| Entity đầu vào | Giả định về chiến lược | Kết quả thường có |
|---|---|---|
| ID `null`, không có version | Kiểm tra ID | Mới |
| ID non-null, không có version | Kiểm tra ID | Không mới |
| ID non-null, version wrapper `null` | Ưu tiên version wrapper | Mới |
| ID non-null, version wrapper non-null | Ưu tiên version wrapper | Không mới |
| ID bất kỳ, `Persistable.isNew()` trả `true` | Module delegate cho `Persistable` | Mới |
| ID bất kỳ, `Persistable.isNew()` trả `false` | Module delegate cho `Persistable` | Không mới |

Wrapper và primitive cũng cần được phân biệt. Một version `Long` có giá trị `0L` là non-null; nó không tương đương version `null`. Với JPA, version primitive không được dùng như một tín hiệu mới tương đương version tham chiếu, vì `0` có thể là version ban đầu hợp lệ.

Không lấy quy tắc của một module rồi áp nguyên cho tất cả repository Commons.

## 3. Ảnh hưởng đến `save`

### 3.1. Kết quả phân loại giúp module chọn đường xử lý

Ở repository JPA thông thường, kết quả mới/không mới được dùng để chọn `EntityManager.persist` hoặc `EntityManager.merge`. Với các module khác, kết quả có thể tham gia chọn insert/update hoặc một quy trình lưu aggregate khác.

Những từ đó không thay thế được hợp đồng cụ thể của module:

- `merge` không phải một phép bảo đảm rằng trước đó đã có bản ghi.
- `save` không mặc nhiên có tính upsert ở mọi datastore.
- Một entity bị xem là không mới nhưng bản ghi đã mất có thể gây lỗi, được tạo lại hoặc được xử lý theo semantics khác tùy module/provider.
- Một entity bị xem là mới nhưng mang khóa đã tồn tại có thể gặp xung đột khóa.

Phân loại chỉ là một đầu vào của luồng ghi. Ràng buộc datastore, metadata mapping, transaction và concurrency tiếp tục quyết định kết quả.

### 3.2. Phân loại sai không phải lúc nào cũng gây cùng một exception

| Sai lệch | Hệ quả có thể xảy ra |
|---|---|
| Entity chưa lưu nhưng bị xem là không mới | Chọn đường cập nhật/merge hoặc cơ chế ghi khác không đúng ý định tạo mới |
| Entity đã lưu nhưng bị xem là mới | Thử tạo thêm bản ghi, xung đột khóa hoặc hành vi tạo mới ngoài ý muốn |
| Entity mất ID qua bản sao | Lần lưu sau tiếp tục mang tín hiệu mới |
| Entity mất version qua DTO | Có thể đổi cách nhận diện trạng thái hoặc mất thông tin concurrency |

Cần quan sát đường ghi thật của module, không chỉ đoán từ tên phương thức `save`.

### 3.3. Luôn giữ entity trả về

```java
Article saved = articleRepository.save(draft);
```

Entity kết quả có thể chứa ID, version và metadata auditing mới. Nó cũng có thể là một instance khác, đặc biệt với model immutable hoặc với cơ chế hợp nhất trạng thái của provider.

Nếu code tiếp tục dùng draft cũ, nó có thể giữ ID/version `null` hoặc metadata cũ. Lần lưu kế tiếp sẽ được phân loại từ snapshot cũ ấy.

Hợp đồng `save` yêu cầu phía gọi tiếp tục sử dụng instance trả về. Điều này liên quan đồng thời đến state detection, auditing và optimistic locking, không chỉ đến việc lấy ID cho response.

## 4. Auditing: metadata tạo và metadata sửa

### 4.1. Các thuộc tính có vai trò khác nhau

Spring Data có các annotation auditing phổ biến:

| Annotation | Ý nghĩa |
|---|---|
| `@CreatedDate` | Thời điểm tạo theo lifecycle auditing |
| `@LastModifiedDate` | Thời điểm sửa gần nhất theo lifecycle auditing |
| `@CreatedBy` | Chủ thể tạo |
| `@LastModifiedBy` | Chủ thể sửa gần nhất |

Đối với actor, `AuditorAware<T>` có thể cung cấp chủ thể hiện tại trong mô hình đồng bộ. Kiểu `T` phải phù hợp với property actor. Auditing chỉ theo thời gian không nhất thiết cần một auditor cho actor.

Các giá trị thời gian đến từ cơ chế cung cấp thời gian mà hạ tầng sử dụng. Khi kiểm thử, nguồn thời gian xác định giúp kiểm tra kết quả mà không cần chờ đồng hồ thực chạy.

Những annotation trên cần hạ tầng auditing của module được bật và cấu hình. Chỉ đặt annotation vào field không tự tạo toàn bộ lifecycle auditing.

### 4.2. Nhánh tạo và nhánh sửa không làm cùng việc

Trong một cấu hình auditing thông thường, có thể kỳ vọng:

| Ngữ cảnh auditing | Metadata tạo | Metadata sửa |
|---|---|---|
| Tạo mới | Điền thời gian/chủ thể tạo | Có thể điền cùng lúc, tùy cấu hình |
| Sửa entity hiện có | Giữ thông tin tạo | Cập nhật thời gian/chủ thể sửa |

Cấu hình như việc có cập nhật metadata sửa ngay lúc tạo hay không ảnh hưởng kết quả. Vì vậy, bản ghi vừa tạo đã có `lastModifiedAt` không tự chứng minh nó từng trải qua một lần cập nhật nghiệp vụ.

Trong bài, các ví dụ dùng giả định metadata sửa cũng được điền khi tạo. Nếu ứng dụng cấu hình khác, cần điều chỉnh kỳ vọng tương ứng.

### 4.3. State detection và auditing có thể nối với nhau theo nhiều cách

Hạ tầng Commons có handler auditing nhận biết trạng thái, chẳng hạn `IsNewAwareAuditingHandler`, để chọn thao tác đánh dấu tạo hoặc sửa dựa trên metadata của entity.

Một module hoặc adapter cũng có thể điều phối auditing bằng lifecycle của chính nó. Ví dụ, JPA auditing gắn với các callback lifecycle của JPA; không nên mô tả rằng mọi repository đều gọi cùng một handler `isNew` đúng một lần ở cùng thời điểm.

Điểm cần kiểm tra trong ứng dụng là:

1. Thành phần nào xác định entity mới cho thao tác lưu?
2. Thành phần nào chọn nhánh auditing tạo/sửa?
3. Những thành phần đó nhìn thấy trạng thái entity ở thời điểm nào?

Sự liên hệ là có thật, nhưng thứ tự và cơ chế kết nối thuộc module.

### 4.4. Phân loại sai có thể làm auditing sai kỳ vọng

Nếu entity đã tồn tại bị đưa vào nhánh tạo, metadata tạo có thể được điền lại khi lifecycle tương ứng chạy. Nếu thao tác ghi sau đó thất bại, những thay đổi này có thể chỉ nằm trong bộ nhớ và không được commit.

Ngược lại, entity chưa từng được lưu nhưng đi vào nhánh sửa có thể chỉ nhận metadata sửa, trong khi metadata tạo vẫn thiếu. Với một đường ghi có khả năng tạo bản ghi dù entity được xem là không mới, kết quả có thể là bản ghi mới nhưng không có metadata tạo như mong đợi.

Không thể kết luận chỉ từ `createdAt` hoặc `updatedAt` trong object rằng datastore đã thực hiện thành công một insert hay update.

## 5. Optimistic locking: kiểm tra phiên bản đã đọc

### 5.1. Version không chỉ là dấu hiệu mới

Trong module có hỗ trợ optimistic locking bằng property version, version có hai vai trò liên quan:

- Có thể tham gia nhận diện entity mới.
- Là thông tin để kiểm tra lần ghi có dựa trên phiên bản còn hợp lệ không.

Vai trò thứ hai xử lý tình huống nhiều tác nhân đọc cùng một trạng thái rồi ghi đè nhau.

Ví dụ khái niệm:

```text
Bản ghi hiện tại: id = A1, version = 7

Người A đọc snapshot version 7.
Người B đọc snapshot version 7.

A ghi thành công dựa trên version 7 -> datastore chuyển sang version 8.
B vẫn ghi dựa trên version 7 -> không còn khớp trạng thái hiện tại.
```

Nếu không có cơ chế concurrency phù hợp, lần ghi của B có thể làm mất thay đổi của A. Metadata auditing chỉ ghi người/thời điểm sửa không tự ngăn tình huống này.

### 5.2. Minh họa điều kiện ghi

Với mô hình relational có optimistic locking, có thể hình dung điều kiện như sau:

```sql
UPDATE article
SET title = :title,
    updated_at = :updatedAt,
    updated_by = :updatedBy,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
```

Đây là minh họa logic điều kiện, không phải cam kết mọi module/provider sinh đúng câu SQL này. Datastore khác có thể dùng một thao tác cập nhật có điều kiện tương đương.

Khi không có bản ghi khớp, hạ tầng có thể báo lỗi optimistic locking. Nguyên nhân có thể là version đã đổi hoặc bản ghi đã bị xóa; lỗi không tự chứng minh luôn có đúng hai người sửa cùng lúc.

Trong hệ sinh thái Spring, lỗi có thể được biểu diễn bằng `OptimisticLockingFailureException` hoặc một ngoại lệ cụ thể được tầng tích hợp dịch tương ứng. Thời điểm và dạng lỗi còn phụ thuộc module/provider.

### 5.3. Không có một version ban đầu chung cho mọi store

Không tự gán số version theo trí nhớ từ module khác. Kiểu version được hỗ trợ, giá trị khởi tạo, thời điểm tăng và cách phản ánh giá trị mới vào entity kết quả phụ thuộc module.

Các ví dụ sử dụng `v0`, `v1` khi nói về lần đầu và lần kế tiếp. Ví dụ số `7 -> 8` chỉ minh họa một chuỗi version, không quy định version đầu tiên phải bằng bao nhiêu.

Không tự tăng hoặc reset version để làm thao tác ghi “chạy được”. Làm vậy có thể phá ý nghĩa kiểm tra snapshot.

## 6. Domain minh họa: bài viết có version và auditing

### 6.1. Entity dùng annotation Commons

Ví dụ sau dành cho một module hỗ trợ các annotation và mapping tương ứng. Nó không phải cấu hình entity JPA hoàn chỉnh; nếu dùng JPA, metadata entity/ID/version phải theo JPA và cấu hình provider phù hợp.

```java
package com.example.articles;

import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;

public class Article {

    @Id
    private UUID id;

    @Version
    private Long version;

    private String title;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    @PersistenceCreator
    public Article(
            UUID id,
            Long version,
            String title,
            Instant createdAt,
            Instant updatedAt,
            String createdBy,
            String updatedBy) {
        this.id = id;
        this.version = version;
        rename(title);
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
        this.createdBy = createdBy;
        this.updatedBy = updatedBy;
    }

    public static Article draft(String title) {
        return new Article(
                UUID.randomUUID(), null, title,
                null, null, null, null);
    }

    public void rename(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
        this.title = title;
    }

    public UUID getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getUpdatedBy() {
        return updatedBy;
    }
}
```

Ở đây ID được ứng dụng cấp trước khi lưu, còn version ban đầu là `null`. Trong module áp dụng chiến lược ưu tiên version wrapper, draft vẫn được xem là mới dù UUID non-null.

Ví dụ giả định module hỗ trợ kiểu ID, mapping field, version và auditing đang dùng. Creator cũng cần metadata tên tham số phù hợp. Không có datastore hoặc auditing handler nào được tự bật chỉ nhờ lớp Java này.

### 6.2. Repository và nguồn actor

Repository dựa trên abstraction chung:

```java
package com.example.articles;

import java.util.UUID;
import org.springframework.data.repository.CrudRepository;

public interface ArticleRepository
        extends CrudRepository<Article, UUID> {
}
```

Để minh họa chủ thể auditing kiểu `String`, hình dạng của một nguồn actor có thể là:

```java
AuditorAware<String> exampleAuditor =
        () -> Optional.of("editor-01");
```

Đoạn trên minh họa hợp đồng và cần các import `AuditorAware`, `Optional` tương ứng. Trong ứng dụng, nguồn actor cần được đăng ký theo cấu hình auditing của module và lấy từ ngữ cảnh phù hợp. Chuỗi cố định chỉ thích hợp cho ví dụ hoặc một kiểm thử có kiểm soát.

Nếu không cung cấp actor ở một thời điểm, không mặc nhiên kỳ vọng property người tạo/sửa sẽ có một tên người dùng. Cần định nghĩa rõ cách xử lý thao tác hệ thống, không xác thực hoặc tác vụ nền.

## 7. Theo dõi một vòng tạo và sửa thành công

Giả định:

- Module nhận version wrapper `null` là dấu hiệu mới.
- Auditing đã bật, có nguồn thời gian và actor.
- Metadata sửa cũng được điền khi tạo.
- Các thao tác trong ví dụ hoàn tất và commit thành công.

### 7.1. Tạo bài viết

```java
Article draft = Article.draft("Spring Data Commons");
Article saved = articleRepository.save(draft);
```

Trạng thái khái niệm:

| Thời điểm | Version | Metadata tạo | Metadata sửa |
|---|---|---|---|
| Draft | `null` | Chưa có | Chưa có |
| Kết quả tạo đã commit | `v0` | `t1`, `editor-01` | `t1`, `editor-01` theo giả định cấu hình |

Giá trị version đầu tiên do module quản lý. Chỉ nhìn thấy các field được điền trong bộ nhớ trước commit chưa đủ để khẳng định dòng cuối đã xảy ra.

### 7.2. Sửa bài viết

```java
Article current = articleRepository.findById(saved.getId())
        .orElseThrow(() -> new IllegalArgumentException("Article not found"));

current.rename("State detection trong Spring Data");
Article updated = articleRepository.save(current);
```

Với actor sửa là `editor-02`, thời gian `t2` và lần ghi hợp lệ:

| Trạng thái sau commit | Giá trị mong đợi |
|---|---|
| ID | Giữ identity của bài viết |
| Version | Giá trị kế tiếp do module cấp |
| `createdAt`, `createdBy` | Vẫn là metadata tạo ban đầu |
| `updatedAt`, `updatedBy` | Phản ánh lần sửa thành công |
| `title` | Tiêu đề mới |

Bảng này mô tả kết quả mong muốn của một cấu hình đúng. Nó không quy định auditing phải chạy trước hay sau mọi bước khởi tạo version trong tất cả module.

## 8. Khi hai lần sửa cạnh tranh

### 8.1. Cùng version đầu vào, chỉ một lần ghi còn hợp lệ

Dùng hai snapshot độc lập của cùng bài viết:

```text
A: id = A1, version = 7, title = "Tiêu đề gốc"
B: id = A1, version = 7, title = "Tiêu đề gốc"

A đổi title -> "Bản A".
B đổi title -> "Bản B".

A lưu và commit thành công -> version 8.
B lưu với expectedVersion = 7 -> xung đột.
```

Nếu optimistic locking được module thực thi đúng, trạng thái thành công của A không bị B âm thầm ghi đè bằng một snapshot cũ.

### 8.2. Auditing của lần thất bại không phải lịch sử đã commit

Trước khi bước ghi phát hiện xung đột, pipeline có thể đã cập nhật `updatedAt` hoặc `updatedBy` trên snapshot B. Sau lỗi, B có thể giữ các giá trị đó trong bộ nhớ.

Điều đó không có nghĩa datastore đã ghi nhận một lần sửa thành công của B. Cần phân biệt:

- Metadata được chuẩn bị cho một lần thử ghi.
- Metadata của trạng thái thật sự được lưu và commit.

Auditing trên entity thường biểu diễn thông tin tạo/sửa của trạng thái hiện tại. Nó không tự tạo một lịch sử đầy đủ của mọi lần thử, mọi version cũ và mọi lần thất bại.

### 8.3. Không retry nguyên snapshot cũ một cách máy móc

Gọi lại `save(B)` với version cũ không tự giải quyết xung đột. Tùy nghiệp vụ, ứng dụng cần báo conflict, tải lại trạng thái hoặc tính lại thay đổi trên snapshot mới.

Retry chỉ phù hợp khi thao tác có semantics rõ ràng và có thể áp lại an toàn. Một lệnh đặt toàn bộ nội dung từ màn hình cũ khác với một thao tác cộng có quy tắc hợp nhất cụ thể.

Không reset version của B về `null` để buộc nó đi qua nhánh tạo mới. Cách đó thay đổi loại thao tác, không giải quyết sự cạnh tranh.

## 9. State detection sai làm ba cơ chế lệch nhau thế nào?

### 9.1. Entity hiện có nhưng `isNew` luôn trả `true`

Giả sử entity implement `Persistable` và cờ mới không được chuyển đúng sau khi đọc/lưu.

Các khả năng cần kiểm tra:

- Repository đi theo đường tạo thay vì đường dành cho entity hiện có.
- Nếu auditing dựa vào cùng tín hiệu mới, metadata tạo có thể được điền lại.
- Đường insert không thay thế được một lần cập nhật có điều kiện version.
- Datastore có thể chặn bằng khóa duy nhất trước khi có thay đổi được commit.

Không diễn giải việc không thấy lỗi optimistic locking là đã bảo vệ cập nhật: lần ghi có thể chưa hề đi vào đường cập nhật cần kiểm tra version.

### 9.2. Entity mới nhưng `isNew` trả `false`

Ví dụ thường gặp là ID do ứng dụng cấp trước, không có metadata version phù hợp và chiến lược chỉ nhìn ID.

Repository có thể chọn đường xử lý entity không mới. Auditing có thể chọn nhánh sửa hoặc được điều phối khác theo lifecycle module. Nếu đường ghi tạo được bản ghi, metadata tạo có thể không giống kỳ vọng; nếu đường ghi yêu cầu bản ghi hiện có, thao tác có thể thất bại.

Không có một kết quả duy nhất dùng chung cho mọi store. Điều cần sửa là chính sách trạng thái và cấu hình tương ứng với chiến lược ID của ứng dụng.

### 9.3. DTO cập nhật làm mất version

Một request chứa ID và tiêu đề mới. Mapper dựng `Article` mới với version `null` và toàn bộ metadata auditing `null`.

Với chiến lược ưu tiên version wrapper, object có thể bị coi là mới. Với đường ghi khác, thông tin tạo bị thiếu cũng có thể bị chép sang trạng thái lưu trữ nếu mapping cho phép.

Auditing không phải cơ chế tự truy vấn lại `createdAt`/`createdBy` bị DTO làm mất. Nhánh sửa thông thường không có nhiệm vụ khôi phục mọi field đã tồn tại trong datastore.

Luồng cập nhật nên xác định rõ nguồn ID, expected version và các field do hệ thống quản lý. Không sao chép toàn bộ request lên entity rồi kỳ vọng callback sửa lại mọi sai lệch.

### 9.4. Bản sao immutable làm rơi metadata

Một wither chỉ giữ ID và tiêu đề nhưng đặt version, thời điểm tạo và chủ thể tạo về mặc định có thể phá cả ba cơ chế:

1. Version bị mất làm thay đổi state detection.
2. Metadata tạo không được bảo toàn.
3. Expected version cho optimistic locking không còn đúng.

Với model immutable, mỗi bản sao phải giữ trạng thái không được thay đổi. Sau `save`, luôn dùng entity kết quả có ID/version/auditing mới nhất.

## 10. Cập nhật từ client: version mới đọc chưa chắc là version client đã thấy

### 10.1. Một lỗi nghiệp vụ dù locking ở datastore vẫn hoạt động

Client đọc version `4`. Trong lúc client sửa, người khác cập nhật lên version `5`.

Nếu service nhận request cũ, tải version `5`, bỏ qua việc client đang dựa trên version `4`, rồi áp toàn bộ nội dung cũ lên entity mới đọc, lần lưu có thể thành công với expected version `5`.

Optimistic locking ở datastore vẫn làm đúng: nó bảo vệ khoảng thời gian từ lần đọc version `5` đến lần ghi. Nhưng ứng dụng đã bỏ mất điều kiện rằng client chỉ đồng ý sửa trên version `4`.

Cần phân biệt snapshot của client với snapshot mà service vừa tải.

### 10.2. Kiểm tra expected version theo hợp đồng cập nhật

Một luồng minh họa tại service:

```java
public Article updateTitle(
        UUID id,
        Long expectedVersion,
        String title) {
    Objects.requireNonNull(expectedVersion, "expectedVersion");

    Article current = articleRepository.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException("Article not found"));

    if (!Objects.equals(current.getVersion(), expectedVersion)) {
        throw new IllegalStateException("Article has changed");
    }

    current.rename(title);
    return articleRepository.save(current);
}
```

Đoạn này là minh họa logic ứng dụng, cần các import Java tương ứng và transaction phù hợp với module. Ngoại lệ nghiệp vụ có thể được thay bằng loại conflict của ứng dụng.

Phép so sánh đầu tiên kiểm tra snapshot client. `@Version` ở datastore vẫn cần để bảo vệ thay đổi có thể xảy ra sau phép so sánh nhưng trước khi ghi.

Không coi việc kiểm tra version bằng Java là thay thế được một thao tác ghi có điều kiện tại datastore.

## 11. Transaction, flush và thời điểm nhận kết quả

### 11.1. `save` trả về chưa chắc là điểm commit cuối cùng

Một số module/provider trì hoãn thao tác ghi hoặc kiểm tra xung đột đến flush/commit. Với JPA, đây là một khác biệt đặc biệt cần chú ý khi đọc log hoặc bắt exception.

Một entity có ID/version/auditing trong bộ nhớ không chứng minh transaction đã commit. Nếu giao dịch rollback, trạng thái Java đó có thể không tự trở về giá trị trước khi thử ghi.

Vì thế, không lấy một timestamp vừa được callback điền làm xác nhận dữ liệu đã bền vững.

### 11.2. Bắt lỗi ở đúng ranh giới

Nếu exception chỉ phát sinh khi transaction hoàn tất, một khối `try` quanh riêng lời gọi `save` bên trong một method có transaction bên ngoài có thể chưa nhìn thấy lỗi tại đó.

Ứng dụng cần đặt việc ánh xạ lỗi và xử lý kết quả ở ranh giới phù hợp với cơ chế transaction thực tế. Không giả định mọi module đều phát lỗi optimistic locking đồng bộ ngay tại câu lệnh Java `save`.

### 11.3. Actor và thời gian cũng có ngữ cảnh

Auditing cần nguồn actor/thời gian phù hợp với lúc lifecycle chạy. Trong xử lý nền hoặc reactive, không mặc nhiên giả định ngữ cảnh người dùng của request được truyền qua mọi luồng.

Module reactive có thể sử dụng cơ chế actor reactive tương ứng. Việc dùng thread-local của một luồng khác không tự cung cấp đúng chủ thể auditing.

Đây là lý do cần kiểm chứng metadata actor trong pipeline thực tế, thay vì chỉ kiểm tra một bean auditor riêng lẻ trả đúng tên.

## 12. Không phải mọi đường ghi đều đi qua cùng lifecycle

Một custom repository fragment có thể gọi client datastore trực tiếp. Một bulk update hoặc lệnh cập nhật thủ công có thể không materialize entity và không đi qua cùng callback auditing/version như `save` thông thường.

Nếu chọn đường ghi như vậy, cần xác định rõ:

- Metadata sửa được cập nhật ở đâu?
- Metadata tạo có được bảo toàn không?
- Điều kiện expected version có được đưa vào thao tác ghi không?
- Version mới được cập nhật theo cơ chế nào?
- Kết quả không khớp bản ghi được xử lý thế nào?

Không kết luận chỉ cần đặt `@LastModifiedDate` và `@Version` trên class là mọi lệnh ghi tùy chỉnh đều tự có hai hành vi này.

Tương tự, một projection đọc chỉ có ID và tiêu đề không tự trở thành entity đầy đủ để lưu lại. Derived query, phân trang hoặc Query by Example giải quyết việc đọc/lựa chọn dữ liệu, không tự khôi phục metadata vòng đời cho object được dựng lại sau đó.

## 13. Quy trình chẩn đoán một lần lưu bất thường

Lần theo một entity cụ thể qua các điểm sau:

1. **Trước `save`:** ID, version, kết quả `Persistable.isNew()` nếu có, các field auditing và nguồn tạo object.
2. **Chiến lược của module:** thành phần nào phân loại mới/không mới, version có được ưu tiên không?
3. **Lifecycle auditing:** auditing đã bật chưa, nhánh nào được chọn, actor/thời gian đến từ đâu?
4. **Đường ghi:** persist/merge, insert/update, upsert hoặc thao tác tùy chỉnh nào thực sự được gọi?
5. **Kết quả ghi và transaction:** có xung đột khóa, version không khớp, bản ghi bị xóa hoặc rollback không?
6. **Entity được giữ lại:** code tiếp tục từ kết quả `save` hay từ snapshot cũ?

Bảng đối chiếu nhanh:

| Dấu hiệu | Câu hỏi ưu tiên |
|---|---|
| `createdAt` đổi sau mỗi lần sửa | Entity có bị xem là mới hoặc metadata có bị mapper ghi đè không? |
| Entity mới chỉ có `updatedAt` | Có đi vào nhánh sửa hoặc cấu hình auditing nào khác không? |
| `updatedAt` trong object đã đổi nhưng datastore chưa đổi | Ghi có thất bại, chưa flush hoặc rollback không? |
| Có ID nhưng vẫn thử tạo mới | Version wrapper đang `null` hay `Persistable` trả true? |
| Cập nhật từ request gây xung đột khóa | DTO có làm mất version và đổi state detection không? |
| Không phát hiện snapshot cũ của client | Service có kiểm tra expected version client không? |
| Có `@Version` nhưng custom update ghi đè dữ liệu | Đường ghi có thực sự dùng điều kiện version không? |
| Metadata actor rỗng | Nguồn actor có hoạt động đúng trong lifecycle/ngữ cảnh hiện tại không? |

Không sửa bằng cách bỏ `@Version`, luôn trả `false` từ `isNew` hoặc reset metadata trước mỗi lần lưu. Những thay đổi đó có thể che triệu chứng trong khi làm sai semantics.

## 14. Kiểm chứng có ý nghĩa

### 14.1. Kiểm tra tạo rồi sửa

Với module và datastore thử nghiệm phù hợp:

1. Tạo entity mới theo chính sách ID của ứng dụng.
2. Lưu và hoàn tất transaction.
3. Đọc lại để xác nhận ID/version/metadata tạo đúng.
4. Đổi actor và thời gian kiểm soát được, sửa dữ liệu.
5. Lưu, commit rồi đọc lại.
6. Xác nhận metadata tạo được giữ, metadata sửa phản ánh lần sửa và version chuyển theo hợp đồng module.

Không cần dùng sleep để tạo khoảng cách thời gian trong kiểm thử. Nếu hạ tầng cho phép cấu hình nguồn thời gian, cung cấp các giá trị xác định cho từng giai đoạn.

### 14.2. Kiểm tra xung đột bằng hai snapshot độc lập

Đọc cùng entity vào hai ngữ cảnh hoặc giao dịch độc lập phù hợp với module. Với JPA, tránh vô tình nhận cùng một managed instance từ một persistence context rồi tưởng đó là hai snapshot.

Cho snapshot thứ nhất ghi và commit thành công. Sau đó thử lưu snapshot thứ hai với version cũ. Xác nhận:

- Module báo kết quả xung đột theo hợp đồng của nó.
- Dữ liệu thành công của lần đầu không bị ghi đè.
- Metadata sửa đã commit vẫn tương ứng lần thành công.
- Snapshot thất bại trong bộ nhớ không bị nhầm là trạng thái đã lưu.

### 14.3. Kiểm tra các tín hiệu trạng thái dễ sai

| Trường hợp | Điều cần chứng minh |
|---|---|
| ID ứng dụng cấp, version `null` | Strategy của module nhận diện lần tạo đúng |
| DTO update mất version | Ứng dụng phát hiện hoặc tránh dựng sai trạng thái |
| `Persistable` có cờ lifecycle | Sau đọc/lưu, kết quả `isNew` đúng theo thiết kế |
| Entity immutable | Bản sao giữ ID, version và metadata cần thiết |
| Direct/bulk update | Auditing và concurrency được xử lý theo đường ghi đó |
| Rollback | Không nhầm metadata trong bộ nhớ với dữ liệu đã commit |

Mock repository hữu ích để kiểm tra service giữ kết quả `save` hoặc truyền expected version. Nó không chứng minh module thật chạy auditing callback, tăng version hoặc dịch lỗi tại commit đúng như mong đợi.

## 15. Bài tập tình huống

### Bài 1: `createdAt` liên tục bị đặt lại

Một entity implement `Persistable` nhưng `isNew()` luôn trả `true`. Sau khi sửa, object trong bộ nhớ có `createdAt` mới và thao tác ghi gặp lỗi khóa.

Hãy tách hai vấn đề: vì sao lifecycle có thể đi vào nhánh tạo, và vì sao timestamp vừa đổi không phải bằng chứng một bản ghi mới đã commit. Đề xuất cách quản lý trạng thái sau đọc/lưu theo module đang dùng.

### Bài 2: request sửa có ID nhưng version `null`

Ứng dụng dùng chiến lược ưu tiên version wrapper. Mapper nhận request sửa rồi tạo entity với ID đã có, version và metadata tạo đều `null`.

Giải thích vì sao ID non-null chưa đủ để đi vào luồng mong muốn. Thiết kế lại hợp đồng cập nhật để giữ expected version và metadata do hệ thống quản lý.

### Bài 3: timestamp cập nhật nhưng ghi bị từ chối

Hai snapshot version `7` cùng được sửa. Snapshot A thành công, snapshot B thất bại nhưng `updatedAt` trên B đã được thay đổi.

Xác định metadata nào phản ánh trạng thái đã commit. Giải thích vì sao auditing entity không phải lịch sử mọi lần thử sửa và vì sao reset version B không phải cách giải quyết xung đột.

### Bài 4: service đọc version mới rồi ghi nội dung từ màn hình cũ

Client gửi expected version `4`; datastore đã ở version `5`. Service tải version `5`, bỏ qua version client rồi áp nội dung cũ và lưu thành công.

Chỉ ra phạm vi mà optimistic locking ở datastore đã bảo vệ và điều kiện nghiệp vụ mà service đã bỏ mất. Thêm kiểm tra expected version nhưng vẫn giữ cơ chế version tại datastore để chống cạnh tranh sau bước kiểm tra.

## 16. Các điểm cần nhớ

- State detection ảnh hưởng đường `save`; semantics ghi cụ thể thuộc module lưu trữ.
- Auditing phân biệt tạo và sửa theo lifecycle, nhưng không phải mọi module đều dùng cùng một thứ tự callback hoặc cùng một handler.
- Metadata tạo thường cần được giữ khi sửa; auditing không tự khôi phục dữ liệu mà DTO hoặc bản sao đã làm mất.
- Version có thể vừa là tín hiệu mới vừa là điều kiện optimistic locking; không reset hoặc tự tăng để ép thao tác thành công.
- Một timestamp hoặc version đã đổi trong bộ nhớ không chứng minh giao dịch đã commit.
- Luôn tiếp tục từ entity trả về của `save` để giữ snapshot có metadata mới nhất.
- Expected version của client và version vừa đọc ở service là hai thông tin cần được phân biệt.
- Custom/bulk writes cần được kiểm tra riêng về auditing, điều kiện version và kết quả ghi.