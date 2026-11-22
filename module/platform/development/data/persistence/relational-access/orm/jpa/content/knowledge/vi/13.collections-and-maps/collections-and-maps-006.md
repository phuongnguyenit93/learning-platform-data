# Xử lý phần tử trùng và ảnh hưởng của equals(), hashCode() trong tập hợp và Map của JPA

## 1. Vì sao phần tử trùng là vấn đề quan trọng?

Trong Java, **List**, **Set** và **Map** có các quy tắc khác nhau về phần tử trùng. Khi đưa chúng vào entity Jakarta Persistence (JPA), chúng còn gắn với **persistence context**, ánh xạ **@ElementCollection**, **@OneToMany**, **@ManyToMany**, bảng trung gian, khóa ngoại và các ràng buộc cơ sở dữ liệu.

Giả sử một bài viết có nhiều thẻ (Tag):

~~~text
Article #10
  └── tags = [Tag("java"), Tag("jpa"), Tag("java")]
~~~

Ta phải phân biệt ít nhất ba câu hỏi:

1. **Java có coi hai Tag là cùng một phần tử không?** Câu trả lời phụ thuộc loại collection và cách định nghĩa equals(), hashCode().
2. **Database có cho phép hai hàng liên kết Article–Tag giống nhau không?** Câu trả lời phụ thuộc PRIMARY KEY/UNIQUE constraint, không chỉ loại collection Java.
3. **Một câu truy vấn JOIN có thể trả lặp entity gốc không?** Điều này liên quan số hàng SQL, phép JOIN và kết quả JPQL, khác với việc thêm hai phần tử trùng vào Set.

Một lỗi thường gặp là chọn **Set** và kết luận mọi kiểu trùng lặp đều được loại bỏ. Set chỉ áp dụng quy tắc duy nhất **trong tập hợp Java theo equality**, không tự động tạo UNIQUE constraint, không đảm bảo dữ liệu tồn tại trong DB hợp lệ và không tự sửa hiệu năng của JOIN trả quá nhiều hàng.

> **Nguyên tắc:** xác định rõ “trùng” theo **giá trị**, **khóa chính entity**, **khóa nghiệp vụ**, **khóa Map**, hay **hàng liên kết trong database** trước khi chọn cấu trúc dữ liệu và triển khai equals()/hashCode().

## 2. Phân biệt List, Set, Collection và Map

| Cấu trúc Java | Có phần tử trùng không? | Có thứ tự không? | Cách nhận diện trùng |
|---|---|---|---|
| **List<E>** | Có | Có thứ tự theo chỉ số Java | List không loại trùng khi add(); contains()/remove(Object) dùng equals() |
| **Set<E>** | Không theo quy tắc của Set | Tùy implementation; HashSet không cam kết thứ tự | HashSet thường dùng hashCode() và equals(); TreeSet dùng comparator/natural ordering |
| **Collection<E>** | Tùy implementation | Tùy implementation | Interface chung, không tự cam kết uniqueness |
| **Map<K,V>** | Không có hai entry riêng với cùng key | Tùy implementation | HashMap thường dùng hashCode() và equals() trên key |
| **Map values** | Có thể trùng | Tùy Map | Giá trị V không phải khóa và có thể lặp |

Ví dụ Java thuần:

~~~java
List<String> names = new ArrayList<>();
names.add("JPA");
names.add("JPA");
System.out.println(names.size()); // 2

Set<String> uniqueNames = new HashSet<>();
uniqueNames.add("JPA");
uniqueNames.add("JPA");
System.out.println(uniqueNames.size()); // 1

Map<String, Integer> quantityBySku = new HashMap<>();
quantityBySku.put("SKU-1", 5);
quantityBySku.put("SKU-1", 8);
System.out.println(quantityBySku.size());       // 1
System.out.println(quantityBySku.get("SKU-1")); // 8
~~~

**HashMap.put()** với key được xem là trùng sẽ **thay thế giá trị** của entry cũ, không bổ sung entry thứ hai. Trong khi đó, hai key khác nhau vẫn có thể trỏ tới cùng một value.

### 2.1. Loại collection và cách JPA lưu dữ liệu

JPA cho phép dùng những kiểu collection thích hợp để ánh xạ quan hệ hay tập giá trị. Tuy nhiên:

- **List** trong Java luôn có chỉ số, nhưng cách JPA lưu/thứ tự trả ra DB cần mapping rõ ràng nếu muốn thứ tự bền vững.
- **Set** tránh thêm hai phần tử được Java coi là bằng nhau trong cùng tập, nhưng database cần constraint riêng nếu muốn bảo đảm không có hai hàng liên kết trùng.
- **Map** biểu diễn tra cứu bằng khóa; giá trị Map có thể là basic value, embeddable hoặc entity tùy mapping, và cách ánh xạ key cũng phải xác định.
- Provider thường dùng collection wrapper riêng để theo dõi thay đổi của persistent collection. Vì vậy code không nên giả định một field khai báo Set luôn là HashSet nguyên bản sau khi entity được tải.

## 3. Cơ chế equals() và hashCode() trong HashSet, HashMap

Trong Java, **equals()** là phép kiểm tra bằng nhau theo định nghĩa của class. **hashCode()** cung cấp mã băm để các cấu trúc dựa trên hash phân phối phần tử/khóa vào các bucket.

Hai quy tắc hợp đồng quan trọng:

1. Nếu **a.equals(b) == true**, thì **a.hashCode() == b.hashCode()** phải đúng.
2. Nếu a và b có cùng hashCode, **không bắt buộc** chúng phải equals(). Trùng hash là bình thường; cấu trúc hash sẽ dùng equals() để phân biệt.

Với một object không override equals() hoặc hashCode(), implementation của **Object** dùng equality theo tham chiếu trong trường hợp thông thường. Hai instance Java mới có cùng dữ liệu có thể vẫn khác nhau.

~~~java
final class Label {
    final String text;

    Label(String text) {
        this.text = text;
    }
}

Set<Label> labels = new HashSet<>();
labels.add(new Label("java"));
labels.add(new Label("java"));
System.out.println(labels.size()); // 2: hai instance khác nhau
~~~

Nếu Label được xem là một **kiểu giá trị**, cần định nghĩa equality theo giá trị:

~~~java
import java.util.Objects;

final class Label {
    private final String text;

    Label(String text) {
        this.text = Objects.requireNonNull(text);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Label)) return false;
        Label that = (Label) other;
        return text.equals(that.text);
    }

    @Override
    public int hashCode() {
        return text.hashCode();
    }
}
~~~

Lúc đó, hai Label có cùng text được HashSet xem là trùng. **Đây là quyết định về semantics của giá trị**, không phải hành vi JPA tự cung cấp cho mọi class.

### 3.1. Tại sao chỉ override equals() là chưa đủ?

~~~java
@Override
public boolean equals(Object other) {
    return other instanceof Label
        && text.equals(((Label) other).text);
}

// Nếu không override hashCode(), vẫn dùng Object.hashCode().
~~~

Hai instance cùng text có thể equals() trả true nhưng hashCode khác, vi phạm contract. HashSet/HashMap có thể đặt chúng vào những bucket khác nhau, gây việc chứa phần tử trùng hoặc không tìm được key dù equals() nói hai object bằng nhau.

**Luôn thiết kế equals() và hashCode() cùng nhau**, và dùng những thành phần không thay đổi khi object đang nằm trong hash collection.

### 3.2. Tại sao field mutable gây lỗi?

~~~java
class MutableCode {
    String code;

    MutableCode(String code) { this.code = code; }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableCode
            && Objects.equals(code, ((MutableCode) other).code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}

MutableCode value = new MutableCode("OLD");
Set<MutableCode> values = new HashSet<>();
values.add(value);

value.code = "NEW";
System.out.println(values.contains(value)); // Có thể false
~~~

Khi thêm vào HashSet, vị trí lưu phụ thuộc hash của **OLD**. Sửa code thành **NEW** khiến hashCode thay đổi; contains()/remove() có thể tìm sai bucket. Điều này đặc biệt nguy hiểm với một **@Embeddable** được dùng trong Set hoặc một entity có equals/hashCode dựa trên mã nghiệp vụ thay đổi được.

Giải pháp thường là **giữ thành phần equality bất biến**, hoặc bỏ phần tử cũ khỏi collection trước khi tạo và thêm giá trị thay thế. Không tự sửa object đã dùng làm Map key hoặc phần tử HashSet rồi hy vọng Map/Set tự tái lập chỉ mục.

## 4. Trùng ở tầng Java khác trùng ở tầng database

Giả sử bảng:

~~~sql
CREATE TABLE articles (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE tags (
    id BIGINT PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE article_tags (
    article_id BIGINT NOT NULL REFERENCES articles(id),
    tag_id BIGINT NOT NULL REFERENCES tags(id)
);
~~~

Nếu **article_tags** không có PRIMARY KEY hoặc UNIQUE(article_id, tag_id), database có thể cho phép:

~~~text
article_id | tag_id
-----------+-------
10         | 5
10         | 5
~~~

Một Set<Tag> có thể chỉ biểu diễn một Tag có ID 5 trong bộ nhớ, nhưng **sự thật trong DB vẫn có hai hàng liên kết** nếu dữ liệu được chèn bởi SQL, script migration, ứng dụng khác hoặc cơ chế mapping không bảo vệ uniqueness.

Để bảo vệ bất biến “một article gắn một tag nhiều nhất một lần”, nên cấu hình constraint ở DB:

~~~sql
ALTER TABLE article_tags
ADD CONSTRAINT uq_article_tag UNIQUE (article_id, tag_id);
~~~

Hoặc thiết kế PRIMARY KEY ghép (article_id, tag_id) cho bảng liên kết. Nếu đang có dữ liệu trùng, cần xử lý dữ liệu trước khi thêm constraint.

**Set ở Java và UNIQUE ở database bổ sung cho nhau**:

- Java Set tránh trùng theo logic equality tại thời điểm thao tác trong một collection.
- DB UNIQUE ngăn hai transaction, ứng dụng hoặc câu SQL độc lập ghi cặp khóa trùng, bất kể chúng sử dụng loại collection nào.

Nếu nghiệp vụ **cho phép** cùng một quan hệ nhiều lần, ví dụ một khách hàng có thể đăng ký lại nhiều đợt, không nên cưỡng ép một UNIQUE không phù hợp. Thay vào đó, mỗi lượt tham gia cần có định danh hoặc thuộc tính phân biệt như session_id, enrollment_id, period.

## 5. @ElementCollection: Set của các giá trị cơ bản

Khi một entity giữ tập các giá trị đơn giản như từ khóa, có thể dùng **@ElementCollection** với **Set<String>**:

~~~java
package com.example.blog;

import jakarta.persistence.*;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "articles")
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "article_keywords",
        joinColumns = @JoinColumn(name = "article_id"),
        uniqueConstraints = @UniqueConstraint(
            name = "uq_article_keyword",
            columnNames = {"article_id", "keyword"}
        )
    )
    @Column(name = "keyword", nullable = false, length = 80)
    private Set<String> keywords = new HashSet<>();

    protected Article() {}

    public Article(String title) {
        this.title = title;
    }

    public boolean addKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("Invalid keyword");
        }
        return keywords.add(keyword);
    }
}
~~~

Đối với **String**, equals/hashCode đã được Java định nghĩa theo nội dung, nên:

~~~java
article.addKeyword("jpa"); // true
article.addKeyword("jpa"); // false: Set đã có "jpa"
~~~

Nhưng **"JPA"** và **"jpa"** là hai chuỗi khác nhau theo String.equals(). Nếu nghiệp vụ muốn so sánh không phân biệt chữ hoa/thường, cần một quy tắc **chuẩn hóa dữ liệu** thống nhất, chẳng hạn đưa về chữ thường với Locale.ROOT và bỏ khoảng trắng theo chính sách:

~~~java
String normalized = keyword.trim().toLowerCase(Locale.ROOT);
keywords.add(normalized);
~~~

Các import cần thiết như **java.util.Locale** phải được khai báo trong class triển khai. Quy tắc chuẩn hóa còn phải khớp với collations/index của database; String.equals() không tự tuân theo so sánh không phân biệt dấu hoặc chữ của DB.

### 5.1. @ElementCollection không tạo entity có identity riêng

Một phần tử keyword là một **giá trị**, không có @Id riêng như Tag entity. Khi thay đổi collection, JPA sẽ đồng bộ collection table theo chiến lược của provider. Nếu giá trị keyword cần metadata riêng như người tạo, ngày tạo, số lần dùng hoặc quyền chia sẻ giữa nhiều bài viết, có thể phù hợp hơn khi tạo **Tag entity** độc lập thay vì chỉ dùng Set<String>.

### 5.2. Set của @Embeddable

Đối với **Set<Embeddable>**, phải xác định equality theo giá trị của embeddable. Ví dụ một cặp nhãn và ngôn ngữ:

~~~java
@Embeddable
public class LocalizedLabel {

    @Column(name = "language_code", nullable = false, length = 8)
    private String languageCode;

    @Column(name = "label_text", nullable = false, length = 120)
    private String text;

    protected LocalizedLabel() {}

    public LocalizedLabel(String languageCode, String text) {
        this.languageCode = Objects.requireNonNull(languageCode);
        this.text = Objects.requireNonNull(text);
    }

    public String getLanguageCode() { return languageCode; }
    public String getText() { return text; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof LocalizedLabel)) return false;
        LocalizedLabel that = (LocalizedLabel) other;
        return languageCode.equals(that.languageCode)
            && text.equals(that.text);
    }

    @Override
    public int hashCode() {
        return Objects.hash(languageCode, text);
    }
}
~~~

Ở đây một LocalizedLabel là giá trị gồm **cả languageCode và text**. Hai bản có cùng ngôn ngữ nhưng khác text **không trùng** theo equals(). Nếu nghiệp vụ đòi một ngôn ngữ chỉ có một nhãn cho mỗi bài viết, chỉ dùng Set<LocalizedLabel> với equality như trên **không bảo đảm** yêu cầu đó. Có thể cần **Map<String,String>** khóa theo ngôn ngữ hoặc UNIQUE(owner_id, language_code) ở database.

Một khi LocalizedLabel nằm trong HashSet, **không nên sửa trực tiếp languageCode hoặc text** vì hashCode sẽ đổi. Thiết kế embeddable theo kiểu giá trị bất biến về mặt API và thay thế phần tử khi cần cập nhật. JPA có thể cần constructor không tham số cùng cơ chế truy cập field/property, nhưng điều đó không buộc phải mở setter công khai cho client.

## 6. Set<Entity>: equality theo ID hay khóa nghiệp vụ?

Trường hợp khó hơn Set<String> là **Set của JPA entity**. Entity có vòng đời gồm transient, managed, detached và removed; khóa chính có thể được cấp sau khi persist. Hai instance Java khác nhau cũng có thể đại diện **cùng một hàng DB** nếu được tải qua hai persistence context khác nhau.

Xét:

~~~java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

Tag left = em1.find(Tag.class, 5L);
Tag right = em2.find(Tag.class, 5L);

// Hai tham chiếu có thể là hai instance Java khác nhau.
// Nhưng cả hai đều đại diện hàng tags.id = 5.
~~~

Trong **cùng một persistence context**, JPA duy trì tính đồng nhất của managed entity theo primary key: việc find cùng loại entity và cùng ID thường trả cùng managed instance. Nhưng giữa hai context, không được dựa vào **left == right** để nhận diện cùng bản ghi.

### 6.1. Nếu không override equals()/hashCode()

Với equality mặc định theo tham chiếu, hai instance biểu diễn cùng hàng database nhưng thuộc hai context có thể được HashSet xem là hai phần tử khác nhau:

~~~java
Set<Tag> tags = new HashSet<>();
tags.add(left);
tags.add(right);

// Có thể có size = 2 nếu Tag dùng Object.equals/hashCode.
~~~

Đây là lý do phải quyết định **ngữ nghĩa equality của entity** nếu entity có thể được thêm vào Set, dùng làm Map key, so sánh giữa các context hoặc tồn tại ở trạng thái detached.

### 6.2. Cách tiếp cận 1: khóa nghiệp vụ thật sự bất biến

Nếu Tag có một mã **code** duy nhất toàn cục, được gán từ đầu và không bao giờ đổi, có thể dùng code cho equals/hashCode.

~~~java
package com.example.blog;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(
    name = "tags",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_tag_code",
        columnNames = "code"
    )
)
public class Tag {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "code", nullable = false, updatable = false, length = 40)
    private String code;

    protected Tag() {}

    public Tag(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        this.code = code;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Tag)) return false;
        Tag that = (Tag) other;
        return code != null && code.equals(that.getCode());
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
~~~

Ví dụ dùng **Tag** như một entity không có subclass với business key toàn cục ổn định. Hai Tag có cùng code được Java coi là bằng nhau, cả khi ID chưa được cấp. Database cũng phải có UNIQUE(code) thực sự, vì Java Set không ngăn một câu INSERT riêng tạo dữ liệu trùng.

~~~java
Set<Tag> tags = new HashSet<>();
tags.add(new Tag("jpa")); // true
tags.add(new Tag("jpa")); // false
~~~

Nhược điểm: nếu **code có thể đổi**, hashCode đổi khiến HashSet/HashMap có thể hoạt động sai. Đặt @Column(updatable=false) chỉ giúp ngăn ORM cập nhật cột theo mapping thông thường; để mã thật sự bất biến cần quy tắc domain và database phù hợp. Nếu code chỉ duy nhất trong tenant, equality phải phản ánh đúng phạm vi, ví dụ cả tenantId và code, hoặc dùng ID ổn định.

### 6.3. Cách tiếp cận 2: so sánh theo primary key đã được cấp

Khi business key có thể thay đổi, lựa chọn phổ biến là so sánh **ID khác null**:

~~~java
@Entity
public class InventoryItem {

    @Id
    @GeneratedValue
    private Long id;

    private String mutableName;

    protected InventoryItem() {}

    public Long getId() { return id; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof InventoryItem)) return false;

        InventoryItem that = (InventoryItem) other;
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return InventoryItem.class.hashCode();
    }
}
~~~

**Vì sao không tính hash từ id?** Nếu @GeneratedValue cấp id sau khi entity được thêm vào HashSet, hashCode dựa trên id sẽ thay đổi và phần tử có thể không còn được tìm đúng. Giá trị hash cố định theo loại giúp giữ hashCode ổn định trong vòng đời. Đổi lại, nhiều entity cùng loại có thể chung bucket, làm giảm hiệu năng HashSet/HashMap khi tập quá lớn.

Các giới hạn quan trọng:

- Hai entity mới có **id = null** không được xem là bằng nhau chỉ vì cùng null; chúng chỉ bằng nhau nếu là cùng tham chiếu Java.
- Khi đã có ID, hai instance cùng loại/cùng ID có thể equals() bằng nhau dù được tải từ những context khác nhau.
- Công thức với **instanceof** phù hợp nhất khi loại entity không tham gia kế thừa equality phức tạp. Với inheritance và proxy, cần đảm bảo đối xứng, bắc cầu và tính tương thích của class check.
- ORM provider có thể dùng proxy cho lazy association. So sánh bằng **getClass()** chính xác có thể xem proxy và entity thật là hai loại khác nhau; nhưng cách xử lý proxy là chi tiết cần xem xét theo provider.
- Không có **một công thức equals/hashCode duy nhất phù hợp mọi mô hình entity, mọi inheritance hierarchy và mọi provider**.

Một cấu trúc khác là hashCode theo business key bất biến. Lựa chọn nào đúng phụ thuộc **đặc tính bất biến, thời điểm cấp ID và cách entity được dùng trong collection**.

### 6.4. Cách tiếp cận thường gây lỗi: id.hashCode() với ID sinh sau

~~~java
// Không nên dùng trực tiếp nếu entity được đặt trong HashSet trước khi có ID.
@Override
public int hashCode() {
    return id == null ? 0 : id.hashCode();
}
~~~

Trước persist, hashCode có thể bằng 0; sau persist, id được cấp và hashCode khác 0. HashSet không tự di chuyển object tới bucket mới. Trường hợp này có thể khiến **set.contains(entity)** hoặc **set.remove(entity)** thất bại dù object vẫn nằm trong tập.

Ngay cả khi hashCode cố định, việc equality của hai instance thay đổi do được cấp ID cũng cần được hiểu khi đưa các entity transient vào collection; không nên tùy tiện dùng cùng một identity cho nhiều object chưa đồng bộ.

## 7. @ManyToMany với Set<Tag>

Từ ví dụ Article và Tag, nếu Tag là entity dùng chung giữa nhiều bài viết thì ánh xạ **@ManyToMany** phù hợp hơn @ElementCollection.

~~~java
package com.example.blog;

import jakarta.persistence.*;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "articles")
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @ManyToMany
    @JoinTable(
        name = "article_tags",
        joinColumns = @JoinColumn(name = "article_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id"),
        uniqueConstraints = @UniqueConstraint(
            name = "uq_article_tag",
            columnNames = {"article_id", "tag_id"}
        )
    )
    private Set<Tag> tags = new HashSet<>();

    protected Article() {}

    public Article(String title) {
        this.title = title;
    }

    public boolean addTag(Tag tag) {
        if (tag == null) throw new IllegalArgumentException("tag required");
        return tags.add(tag);
    }

    public boolean removeTag(Tag tag) {
        return tags.remove(tag);
    }

    public Set<Tag> getTags() {
        return Collections.unmodifiableSet(tags);
    }
}
~~~

Trong mô hình trên:

- **Article.tags** là một Set, do đó **addTag** trả false nếu Tag mới được Set coi là trùng.
- **@JoinTable** mô tả các cột trong bảng liên kết. UNIQUE(article_id, tag_id) nên được triển khai thực sự ở database.
- **@ManyToMany** không tự cho phép cascade remove Tag khi xóa Article. Tag là entity có thể được dùng bởi nhiều Article, vì vậy **CascadeType.REMOVE** trên quan hệ dùng chung thường nguy hiểm.
- Hai Tag cùng code nhưng khác hàng DB (khác id) sẽ bị Java Set coi là bằng nhau trong ví dụ equals theo immutable code; DB UNIQUE(code) còn ngăn hai hàng Tag như vậy từ nguồn ghi độc lập.

Nếu Tag có code mutable, cần chọn equality khác và điều chỉnh thiết kế domain. Không nên sửa code trên đối tượng đang là phần tử HashSet; điều đó có thể làm bộ sưu tập không tìm hoặc xóa được Tag.

### 7.1. Vì sao vừa cần Set vừa cần unique constraint?

Giả sử hai transaction độc lập đều:

1. Đọc một Article.
2. Không thấy liên kết Article #10 với Tag #5.
3. Thêm Tag #5.
4. Commit.

Không có ràng buộc UNIQUE ở DB, hai transaction có thể tạo hai hàng liên kết trùng khi được xử lý độc lập. Set trong mỗi transaction **không bảo vệ toàn cục**. UNIQUE constraint sẽ khiến ít nhất một thao tác ghi xung đột bị từ chối thay vì chấp nhận dữ liệu sai.

Ứng dụng nên xử lý lỗi vi phạm constraint ở tầng nghiệp vụ và có chính sách retry/idempotency phù hợp. Việc chỉ truy vấn kiểm tra trùng trước INSERT không loại bỏ race condition.

### 7.2. Khi nào không dùng Set?

Nếu quan hệ cần **nhiều lượt xuất hiện có ý nghĩa độc lập**, ví dụ cùng user tham gia cùng khóa học ở hai kỳ khác nhau, thay vì Set<User> có thể thiết kế một entity **Enrollment**:

~~~text
Enrollment
  ├── id
  ├── user_id
  ├── course_id
  ├── term_code
  └── enrolled_at
~~~

Mỗi Enrollment có danh tính riêng. Có thể tạo constraint UNIQUE(user_id, course_id, term_code) nếu một người chỉ được đăng ký một lần mỗi kỳ. Đây là **trùng lặp có ý nghĩa nghiệp vụ**, không phải lỗi cần HashSet loại bỏ tùy ý.

## 8. @OneToMany: List hay Set?

Trong quan hệ một-nhiều, chọn collection dựa vào **ngữ nghĩa domain**, không chỉ dựa vào thói quen.

| Nhu cầu | Gợi ý |
|---|---|
| Các phần tử không được trùng theo identity hoặc khóa nghiệp vụ | Set, kết hợp ràng buộc DB nếu cần |
| Các phần tử có thứ tự và thứ tự phải lưu bền vững | List với @OrderColumn khi phù hợp |
| Cần biểu diễn các bản ghi riêng dù nội dung giống nhau | Mỗi phần tử có ID, List hoặc collection phù hợp |
| Chỉ cần đọc tập không quan tâm thứ tự | Set hoặc Collection theo mapping và semantics |
| Truy cập theo khóa tra cứu của phần tử | Map với @MapKey hoặc @MapKeyColumn |

### 8.1. List chấp nhận phần tử giống nhau

Ví dụ một mẫu khảo sát có nhiều lựa chọn theo vị trí; hai nhãn giống nhau vẫn có thể xuất hiện:

~~~java
@ElementCollection
@CollectionTable(
    name = "survey_options",
    joinColumns = @JoinColumn(name = "survey_id")
)
@OrderColumn(name = "position")
@Column(name = "option_text", nullable = false, length = 120)
private List<String> options = new ArrayList<>();
~~~

~~~java
options.add("Khác");
options.add("Khác");
System.out.println(options.size()); // 2
~~~

Với **@OrderColumn**, JPA có một cột lưu vị trí của List, giúp duy trì thứ tự qua các lần tải theo mapping. Hai mục cùng text vẫn khác nhau nhờ vị trí, nếu đó là yêu cầu nghiệp vụ.

Chỉ khai báo **List** không luôn có nghĩa database duy trì thứ tự như Java sau khi tải lại. Nếu cần thứ tự bền vững, phải cấu hình quy tắc lưu hoặc sắp xếp phù hợp. **@OrderBy** sắp xếp theo thuộc tính/giá trị, khác với **@OrderColumn** lưu chỉ số vị trí.

### 8.2. List.remove(Object) và Set.remove(Object)

- **List.remove(Object)** tìm một phần tử bằng equals() và xóa lần xuất hiện đầu tiên phù hợp, nên trong List có nhiều giá trị trùng, chỉ một lần xuất hiện bị xóa.
- **Set.remove(Object)** dựa vào quy tắc equality và, với HashSet, cả hashCode; nếu hashCode của phần tử thay đổi sau khi add, remove có thể không tìm được.
- **List.remove(int index)** xóa theo vị trí, không theo equals(). Cần phân biệt overload khi List chứa các wrapper số như Integer.

Nếu ứng dụng cần xóa một entity con cụ thể, nên thao tác với **định danh con ổn định** thay vì chỉ dựa vào nội dung có thể trùng hoặc thay đổi.

### 8.3. orphanRemoval và Set

Một aggregate như Order với **@OneToMany(mappedBy = "order", orphanRemoval = true)** có thể xóa bản ghi con khi bị bỏ khỏi collection theo quy tắc JPA. Nếu equality/hashCode của con không ổn định, lệnh remove() có thể không tìm được phần tử:

~~~java
boolean removed = order.getLinesInternal().remove(targetLine);
// Nếu removed == false, không nên giả định JPA đã được thông báo xóa con.
~~~

Ví dụ giả định phương thức getLinesInternal() là API nội bộ được thiết kế để quản lý collection, không nhất thiết có trong entity nào khác. Trong ứng dụng thực tế, hãy tạo helper **removeLine** thay vì để code bên ngoài chỉnh tùy tiện.

Với quan hệ hai hướng, khi bỏ con khỏi tập của cha cần đồng bộ **child.parent** theo mô hình; equality dùng để xóa và mapping sở hữu dùng để cập nhật khóa ngoại là hai trách nhiệm liên quan nhưng khác nhau.

## 9. Duplicate root entity từ JOIN không phải duplicate collection

Một truy vấn SQL JOIN có thể tạo nhiều hàng cho cùng entity cha:

~~~sql
SELECT a.id, a.title, t.id AS tag_id
FROM articles a
JOIN article_tags at ON at.article_id = a.id
JOIN tags t ON t.id = at.tag_id
WHERE a.id = 10;
~~~

Nếu Article #10 có ba Tag, truy vấn trả **ba hàng SQL** mang id Article bằng 10. Điều đó không chứng minh database có ba bài viết hay một Set đã chứa trùng.

Trong JPQL, khi muốn danh sách các article duy nhất:

~~~java
List<Article> result = em.createQuery(
    "select distinct a from Article a join a.tags t " +
    "where t.code in :codes",
    Article.class
).setParameter("codes", List.of("java", "jpa"))
 .getResultList();
~~~

**DISTINCT** trong JPQL có ngữ nghĩa tránh lặp kết quả entity gốc khi query chọn distinct. Cách provider đẩy DISTINCT xuống SQL hoặc lọc trong bộ nhớ có thể thay đổi theo phiên bản. Điều này **khác với việc** Set<Tag> có bảo vệ trùng quan hệ ở bộ nhớ hay không.

Đối với truy vấn **join fetch** collection, số hàng SQL vẫn có thể tăng theo số phần tử con; nếu join fetch nhiều collection cùng lúc có thể gặp kết quả nhân theo tích số phần tử hoặc hạn chế provider. Dùng Set không phải cách xóa chi phí Cartesian product. Khi dữ liệu lớn, xem xét tách query, projection, fetch plan và pagination thích hợp.

### 9.1. DISTINCT không làm sạch dữ liệu trùng trong DB

Một truy vấn SELECT DISTINCT chỉ thay đổi kết quả được trả về theo ngữ nghĩa query. Nó không xóa hai hàng liên kết giống nhau đã được ghi trong bảng. Khi sự trùng lặp là vi phạm bất biến dữ liệu, phải xử lý dữ liệu và thêm constraint ở DB.

### 9.2. Không đồng nhất Java equals với SQL equality

SQL có **collation**, quy tắc NULL và kiểu dữ liệu riêng. Java **String.equals()** phân biệt chữ hoa/thường, trong khi một database/cột có collation không phân biệt case có thể xem "JAVA" và "java" là bằng nhau cho UNIQUE constraint.

Do đó một Set<String> có thể chấp nhận cả hai chuỗi nhưng DB từ chối INSERT thứ hai. Ngược lại, hai object entity có thể equals nhau theo ID trong Java nhưng DB có dữ liệu trùng về business key vì chưa có UNIQUE constraint.

Để nhất quán, thiết kế chuẩn hóa business key và constraint ở DB theo cùng quy tắc với ứng dụng. Không phụ thuộc vào một kiểu so sánh ngầm định mà chưa được xác định.

## 10. Map: trùng key, trùng value và mapping JPA

Map giải quyết bài toán “tra cứu một giá trị theo một khóa”. Trong HashMap, khi hai key được xem là bằng nhau theo **equals/hashCode**, entry mới sẽ ghi đè value của entry cũ:

~~~java
Map<String, Integer> stock = new HashMap<>();
stock.put("HCM", 5);
stock.put("HCM", 9);

System.out.println(stock.size());       // 1
System.out.println(stock.get("HCM"));   // 9
~~~

Đây không phải cơ chế báo lỗi trùng. Nếu nghiệp vụ yêu cầu **không được thay thế giá trị cũ**, cần kiểm tra trước hoặc dùng thao tác phù hợp:

~~~java
Integer old = stock.putIfAbsent("HCM", 5);
if (old != null) {
    throw new IllegalStateException("Warehouse already registered");
}
~~~

**putIfAbsent()** có ngữ nghĩa riêng khi value đã gắn với key là null; nếu Map cho phép null và ứng dụng cần phân biệt “chưa có key” với “key đang có value null”, phải xét **containsKey()** hoặc thiết kế không dùng null value. Đồng thời, kiểm tra trong một HashMap của một process không tạo ràng buộc đồng thời cho các bản ghi DB.

### 10.1. Trùng value được phép

~~~java
Map<String, String> countryByOffice = new HashMap<>();
countryByOffice.put("office-a", "VN");
countryByOffice.put("office-b", "VN");

System.out.println(countryByOffice.size()); // 2
~~~

Hai entry có value **"VN"** là hợp lệ vì key khác nhau. Nếu nghiệp vụ muốn value cũng phải duy nhất, Map một chiều không đáp ứng đủ: cần logic và ràng buộc bổ sung, hoặc một mô hình dữ liệu hai chiều có kiểm soát.

## 11. @ElementCollection Map với @MapKeyColumn

Ví dụ mỗi sản phẩm có số tồn kho theo mã kho, và mỗi mã kho chỉ có **một số lượng** trong phạm vi sản phẩm:

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.util.HashMap;
import java.util.Map;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "product_stock_by_warehouse",
        joinColumns = @JoinColumn(name = "product_id"),
        uniqueConstraints = @UniqueConstraint(
            name = "uq_product_warehouse",
            columnNames = {"product_id", "warehouse_code"}
        )
    )
    @MapKeyColumn(name = "warehouse_code", length = 32)
    @Column(name = "quantity", nullable = false)
    private Map<String, Integer> stockByWarehouse = new HashMap<>();

    protected Product() {}

    public void setQuantity(String warehouseCode, int quantity) {
        if (warehouseCode == null || warehouseCode.isBlank()) {
            throw new IllegalArgumentException("warehouseCode required");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be non-negative");
        }
        stockByWarehouse.put(warehouseCode, quantity);
    }

    public Integer quantityAt(String warehouseCode) {
        return stockByWarehouse.get(warehouseCode);
    }
}
~~~

Trong mapping này:

- **@ElementCollection** lưu các entry Map trong collection table.
- **@CollectionTable** chỉ định bảng và khóa ngoại về Product.
- **@MapKeyColumn** đặt tên cột lưu **key** String, tức warehouse_code.
- **@Column** trên Map mô tả cột **value** Integer, tức quantity.
- **UNIQUE(product_id, warehouse_code)** bảo vệ một sản phẩm chỉ có một entry cho mỗi kho ở DB.

Schema minh họa:

~~~sql
CREATE TABLE product_stock_by_warehouse (
    product_id BIGINT NOT NULL REFERENCES products(id),
    warehouse_code VARCHAR(32) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT uq_product_warehouse
        UNIQUE (product_id, warehouse_code)
);
~~~

Các ràng buộc khác như CHECK(quantity >= 0) có thể bổ sung ở database. Việc Map.put() thay value không có nghĩa provider phải phát chính xác một SQL UPDATE duy nhất; cách đồng bộ collection table phụ thuộc ORM và trạng thái của persistent collection.

### 11.1. Vì sao unique constraint vẫn cần?

Một HashMap đang quản lý không thể chứa hai entry với cùng key theo equals/hashCode. Nhưng nếu DB đã có hai hàng cùng **(product_id, warehouse_code)** do SQL ngoài ứng dụng, Map không biểu diễn được hai hàng đó như hai key phân biệt. Provider có thể xử lý dữ liệu mâu thuẫn theo cách riêng và không nên dựa vào thứ tự đọc để chọn value nào thắng.

Chỉ **UNIQUE constraint thực tế trong DB** mới là chốt chặn đáng tin cậy cho việc trùng key qua nhiều transaction và nguồn ghi.

### 11.2. Chuẩn hóa key của Map

Các mã kho như "hcm", "HCM" hoặc "HCM " có thể được xem là cùng kho theo domain. Nếu vậy, chuẩn hóa key trước khi put() và thiết kế collation/index DB cho đúng ngữ nghĩa:

~~~java
String normalized = warehouseCode.trim().toUpperCase(Locale.ROOT);
stockByWarehouse.put(normalized, quantity);
~~~

Không để key mutable hoặc cùng kho mang nhiều biểu diễn không tương thích; điều đó sẽ dẫn tới hiện tượng “trùng theo nghiệp vụ nhưng không trùng theo Java”.

## 12. @MapKey và key dựa trên thuộc tính entity

Với một Map có **value là entity**, JPA có thể lấy key từ một thuộc tính của value bằng **@MapKey(name = "...")**.

Giả sử một sản phẩm có nhiều bản dịch, mỗi bản dịch là entity riêng:

~~~java
@Entity
@Table(
    name = "product_translations",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_product_locale",
        columnNames = {"product_id", "locale_code"}
    )
)
public class ProductTranslation {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "locale_code", nullable = false, length = 16)
    private String localeCode;

    @Column(name = "display_name", nullable = false, length = 200)
    private String displayName;

    protected ProductTranslation() {}
}
~~~

Phía Product có thể dùng:

~~~java
@OneToMany(mappedBy = "product", cascade = CascadeType.ALL, orphanRemoval = true)
@MapKey(name = "localeCode")
private Map<String, ProductTranslation> translations = new HashMap<>();
~~~

**@MapKey(name = "localeCode")** nói rằng key của Map lấy từ thuộc tính Java localeCode của ProductTranslation. Nó khác với **@MapKeyColumn**: @MapKeyColumn thường ánh xạ key bằng một cột riêng của collection mapping, còn @MapKey(name = ...)** dùng thuộc tính đã ánh xạ của entity value.

Một lưu ý quan trọng: với key được suy ra từ thuộc tính entity, **đổi localeCode sau khi Map đã được tải không bảo đảm Map trong bộ nhớ tự chuyển entry sang key mới**. Trong ngữ nghĩa JPA, quan hệ giữa key Map và thuộc tính value cần được quản lý nhất quán bởi ứng dụng. Cách dễ bảo trì là coi localeCode bất biến sau khi tạo bản dịch; nếu phải đổi, remove entry cũ và tạo/chèn entry mới theo quy tắc nghiệp vụ và collection helper.

### 12.1. Giữ hai phía quan hệ nhất quán

Khi ProductTranslation.product là phía sở hữu FK, helper có thể thiết kế:

~~~java
public void addTranslation(ProductTranslation translation) {
    String locale = translation.getLocaleCode();
    if (translations.containsKey(locale)) {
        throw new IllegalArgumentException("Duplicate locale: " + locale);
    }
    translation.attachToProduct(this);
    translations.put(locale, translation);
}
~~~

Đoạn code giả định ProductTranslation có phương thức getLocaleCode() và attachToProduct(Product) được thiết kế để quản lý quan hệ; mục đích là minh họa **cập nhật cả entity value và key của Map**. Trong implementation thực tế cần xác định vòng đời entity, xử lý trường hợp chuyển một translation giữa hai Product và bảo đảm thao tác remove cũng cập nhật quan hệ.

**Map.put() không tự đồng bộ một quan hệ bidirectional** nếu code không cập nhật phía sở hữu. Tương tự, gán ProductTranslation.product không tự thay key trong Map của parent đang nằm trong bộ nhớ.

## 13. Entity làm khóa Map: các rủi ro giống HashSet

Map có thể dùng một object làm key:

~~~java
Map<InventoryItem, String> statusByItem = new HashMap<>();
statusByItem.put(item, "AVAILABLE");
~~~

Nếu InventoryItem.hashCode() dựa trên một ID được cấp sau khi Map.put(), việc tra cứu bằng cùng item sau persist có thể thất bại vì hash đã đổi. Nếu equals() dựa vào tên sản phẩm và tên bị sửa, key cũng không còn ổn định.

Đối với cấu trúc dữ liệu ứng dụng, thường đơn giản hơn khi dùng **ID bất biến** làm key sau khi ID đã có:

~~~java
Map<Long, String> statusByItemId = new HashMap<>();
statusByItemId.put(item.getId(), "AVAILABLE");
~~~

Nhưng điều này chỉ phù hợp khi ID không null và đúng phạm vi duy nhất. Với composite ID, class key cần equals/hashCode nhất quán, Serializable theo yêu cầu JPA và không sửa các thành phần sau khi được dùng làm key.

Nếu domain thật sự cần Map có key là một **value object**, nên thiết kế key immutable và so sánh theo giá trị thay vì đặt một entity có vòng đời phức tạp vào Map key.

### 13.1. HashMap và TreeMap không cùng quy tắc

**HashMap** dùng hashCode/equals để xác định key trùng. **TreeMap** và **TreeSet** dựa vào natural ordering hoặc Comparator. Với TreeSet, hai phần tử có compare(a,b) == 0 thường được xem là trùng theo quy tắc của sorted set, ngay cả khi equals() nói chúng khác nhau. Vì vậy không thể áp dụng mọi kết luận về HashSet y nguyên cho TreeSet.

Nếu sử dụng sorted collections với entity, comparator cần ổn định khi phần tử đã nằm trong collection và nhất quán với semantics mong muốn. Không so sánh theo một field mutable như displayName rồi sửa tên khi object vẫn nằm trong TreeSet.

## 14. Vòng đời entity và hệ quả lên Set

| Trạng thái JPA | ID thường ở trạng thái nào? | Rủi ro với Set/Map |
|---|---|---|
| **Transient** | Có thể null nếu ID do DB/provider sinh | Hai object khác nhau nhưng cùng trường dữ liệu; equality theo ID null cần xử lý đúng |
| **Managed** | ID được provider gán theo chiến lược và thời điểm phù hợp | Không đổi primary key; dirty checking theo dõi trạng thái |
| **Detached** | ID thường vẫn còn | Có thể tồn tại nhiều instance biểu diễn cùng hàng DB |
| **Removed** | Object có thể vẫn tồn tại trong Java | Collection trong bộ nhớ không tự biến mất chỉ vì entity bị đánh dấu remove |

Một ví dụ khiến equals/hashCode theo id chưa ổn định:

~~~java
Set<InventoryItem> items = new HashSet<>();
InventoryItem item = new InventoryItem();

items.add(item);      // id chưa được cấp
em.persist(item);     // provider có thể cấp id ở giai đoạn này hoặc khi INSERT
em.flush();

// Nếu hashCode dựa trực tiếp vào id, bucket cũ có thể không khớp.
boolean found = items.contains(item);
~~~

Khi dùng generated ID, nên thiết kế equality theo vòng đời entity và kiểm chứng tình huống trước/sau persist. Không đánh đồng **transient entity** với **record đã có ID**. Nếu code có Set chứa hàng ngàn entity với hashCode hằng, cần cân nhắc hiệu năng và lựa chọn cấu trúc khác.

### 14.1. Proxy và getClass()

Quan hệ **@ManyToOne(fetch = LAZY)** có thể trả về proxy đại diện entity. Một số provider dùng class proxy khác class thật:

~~~java
// Ví dụ so sánh có thể không phù hợp với proxy.
if (getClass() != other.getClass()) return false;
~~~

Kiểm tra class chính xác có thể khiến hai object đại diện cùng row nhưng một bên là proxy bị đánh giá không bằng nhau. Dùng **instanceof** có thể tương thích hơn trong một hierarchy đơn giản, nhưng nếu có các entity subtype với quy tắc equality khác nhau cần giữ đối xứng, tính bắc cầu và sự nhất quán.

Không nên copy một công thức equals/hashCode “chuẩn cho mọi JPA entity” mà không xét provider, inheritance, proxy và chiến lược cấp ID. Việc duy trì equality có thể là trách nhiệm domain lâu dài.

## 15. Vì sao không dùng mọi trường của entity trong equals/hashCode?

Một cách tự sinh equality dễ gây vấn đề:

~~~java
// Ví dụ nguy hiểm nếu được áp dụng cho entity có association.
@Override
public int hashCode() {
    return Objects.hash(id, name, price, tags, parent);
}
~~~

Rủi ro:

- **name, price** thay đổi liên tục: hashCode đổi khi entity đang ở HashSet/Map.
- **tags, parent** có thể là association lazy, làm equals/hashCode kích hoạt SQL hoặc lỗi khi detached.
- Quan hệ hai hướng **parent -> children -> parent** có thể tạo vòng đệ quy trong equals/hashCode và dẫn tới StackOverflowError.
- Collection so sánh toàn bộ phần tử tốn chi phí và có thể gọi equals của nhiều entity khác.
- Đối tượng nhận ID sau persist có thể làm hashCode thay đổi nếu hash dựa trên ID.

Khi dùng Lombok, cần cẩn trọng với **@Data**, **@EqualsAndHashCode** hoặc **@ToString** sinh từ tất cả field. Nếu entity có quan hệ hai hướng, nhiều collection và các thuộc tính mutable, thường nên chủ động chọn những trường nào tham gia equality, hoặc viết phương thức theo chiến lược domain đã xác định.

Ví dụ Lombok:

~~~java
@ToString.Exclude
@EqualsAndHashCode.Exclude
@OneToMany(mappedBy = "parent")
private Set<Child> children = new HashSet<>();
~~~

Đoạn này chỉ minh họa việc loại association khỏi các phương thức Lombok tự sinh; các annotation cần import từ Lombok và JPA. Loại association là cần thiết trong nhiều mô hình, nhưng **không tự làm equality entity đúng** nếu các trường còn lại cũng mutable hoặc ID được cấp muộn.

## 16. Khi hai bản ghi khác ID nhưng cùng business key

Giả sử Tag có:

~~~text
Tag A: id = 10, code = "java"
Tag B: id = 21, code = "java"
~~~

Nếu equals/hashCode của Tag dựa trên id, A và B **không trùng theo Java**. Nếu dựa trên code bất biến, chúng **trùng theo Java**. Nhưng trong database, đây vẫn là **hai hàng khác nhau** có ID riêng.

Cần phân biệt hai quy tắc:

1. **Cùng entity identity:** so sánh theo ID và loại entity.
2. **Vi phạm business uniqueness:** hai row khác nhau nhưng không được phép cùng code theo nghiệp vụ.

Nếu code phải duy nhất, cần UNIQUE(code) thật sự ở database. Không được dùng equals() của Tag thay thế constraint và hy vọng ORM không bao giờ ghi trùng. Cũng không nên dùng Set để “giấu” hai hàng trùng business key mà không xử lý dữ liệu gốc.

Khi deduplicate dữ liệu nhập, có thể tra theo business key, chuẩn hóa, dùng upsert/constraint phù hợp và xử lý race condition. Cần quyết định một bản ghi có thể gộp với bản ghi nào và xử lý toàn bộ quan hệ FK trước khi xóa bản ghi trùng.

## 17. Những lỗi thường gặp và cách xử lý

### 17.1. Set<Entity> vẫn chứa hai object đại diện cùng hàng DB

Nguyên nhân có thể do entity dùng equality theo tham chiếu và hai object đến từ hai EntityManager khác nhau. Cần xác định equality mong muốn, rồi triển khai equals/hashCode đúng theo ID hoặc business key bất biến.

### 17.2. HashSet.contains() trả false sau persist

HashCode được tính từ ID do JPA sinh, thay đổi từ null sang giá trị thật. Không đưa field mutable vào hashCode khi object được dùng trong hash collection; xem xét hash ổn định hoặc trì hoãn đưa entity vào tập cho tới khi ID đã được cấp.

### 17.3. HashSet.remove() không xóa được embeddable đã sửa

Một @Embeddable được dùng làm giá trị trong Set nhưng code sửa trường tham gia hashCode. Hãy thiết kế value object bất biến, thay thế phần tử qua remove/add theo giá trị cũ, hoặc sử dụng collection có semantics phù hợp.

### 17.4. Map.put() ghi đè mất entry

Map chỉ có một value cho mỗi key. Nếu muốn lưu nhiều giá trị cho cùng một mã, phải thiết kế **Map<K,List<V>>**, **Map<K,Set<V>>** ở tầng Java hoặc entity liên kết có identity riêng ở JPA, thay vì cố thêm entry trùng key.

### 17.5. Đặt Set nhưng bảng liên kết vẫn có dữ liệu trùng

Set không bảo vệ database khỏi SQL ngoài ORM hoặc race condition. Thêm UNIQUE/PRIMARY KEY phù hợp trên các cột liên kết, xử lý dữ liệu trùng hiện có và kiểm soát concurrent write.

### 17.6. Java String.equals() khác UNIQUE ở DB

Các collation khác nhau có thể so sánh chữ hoa/thường hoặc dấu khác nhau. Cần thống nhất chuẩn hóa mã giữa Java, DB index và giao thức ngoài.

### 17.7. Dùng List rồi nghĩ thứ tự tự bền vững

List có thứ tự trong Java, nhưng muốn lưu vị trí cần @OrderColumn hoặc một cơ chế sắp xếp phù hợp. @OrderBy sắp xếp theo thuộc tính, không lưu chỉ số List.

### 17.8. Tưởng DISTINCT sửa mọi dữ liệu trùng

JPQL DISTINCT giải quyết duplicate trong **kết quả truy vấn** theo ngữ nghĩa query, không xóa những hàng join table trùng trong DB và không thay thế UNIQUE constraint.

### 17.9. Map có @MapKey nhưng sửa key property sau khi load

Key của Map có thể vẫn là giá trị cũ trong bộ nhớ khi thuộc tính entity thay đổi. Cần bất biến hóa key property hoặc quản lý remove/reinsert đúng cách trong collection.

### 17.10. equals/hashCode duyệt association hai hướng

Có thể gây recursion, LazyInitializationException hoặc N+1 query. Không tính hash từ quan hệ/collection, tránh Lombok @Data trực tiếp trên entity phức tạp nếu chưa kiểm soát.

### 17.11. Dùng Set để tránh duplicate JOIN và tưởng tối ưu SQL

Set có thể giúp biểu diễn một collection không chứa trùng logic ở Java, nhưng không xóa việc SQL JOIN trả nhiều hàng hoặc nhân kết quả từ nhiều collection. Cần tối ưu fetch strategy, query, pagination và index.

### 17.12. Sửa child trong orphanRemoval Set rồi mong xóa đúng

Nếu hash của child đổi sau khi thêm, remove có thể không tìm thấy. Cần helper quản lý quan hệ, equality ổn định và xác minh đúng entity bị loại khỏi collection.

## 18. Bài tập thực hành

### Bài 1: String và Map

~~~java
Set<String> a = new HashSet<>();
a.add("jpa");
a.add("jpa");
a.add("JPA");

Map<String, Integer> b = new HashMap<>();
b.put("HCM", 5);
b.put("HCM", 10);
~~~

**Câu hỏi:** a.size(), b.size() và b.get("HCM") bằng bao nhiêu?

**Đáp án:** a.size() = 2 vì "jpa" và "JPA" khác nhau theo String.equals(); b.size() = 1; b.get("HCM") = 10 vì put thứ hai thay thế value theo key cũ.

### Bài 2: Equality của value object

Một Set<LocalizedLabel> cần xem hai phần tử trùng khi cả languageCode và text giống nhau.

**Yêu cầu:** triển khai equals/hashCode nhất quán và giải thích vì sao không nên sửa hai trường sau khi add vào HashSet.

**Gợi ý:** so sánh cả hai trường trong equals(), tính hash từ cùng hai trường. Nếu sửa một trường, vị trí bucket có thể không còn khớp.

### Bài 3: Entity có generated ID

~~~java
Set<InventoryItem> items = new HashSet<>();
InventoryItem item = new InventoryItem();
items.add(item);
em.persist(item);
em.flush();
~~~

**Câu hỏi:** Vì sao hashCode dựa trực tiếp trên id có thể gây lỗi contains()?

**Đáp án:** ID có thể chuyển từ null sang giá trị đã sinh, khiến hashCode đổi sau khi phần tử được lưu trong HashSet. Cần thiết kế hash ổn định hoặc thay thời điểm đưa entity vào Set.

### Bài 4: Duplicate join table

~~~text
article_tags
article_id | tag_id
10         | 5
10         | 5
~~~

**Câu hỏi:** Chuyển List<Tag> thành Set<Tag> có bảo đảm DB không bao giờ chứa hai hàng này nữa không?

**Đáp án:** Không. Set điều khiển equality trong Java; cần UNIQUE(article_id, tag_id) hoặc PRIMARY KEY tương ứng ở DB, xử lý dữ liệu cũ và ghi đồng thời.

### Bài 5: @MapKeyColumn

Một Product có stockByWarehouse: Map<String,Integer>. Mỗi kho chỉ có một số lượng cho mỗi sản phẩm.

**Yêu cầu:** nêu vai trò của @CollectionTable, @MapKeyColumn, @Column và unique constraint.

**Gợi ý:** collection table lưu các entry, map key column lưu warehouse_code, value column lưu quantity; UNIQUE(product_id, warehouse_code) bảo vệ trùng key trong DB.

### Bài 6: Đổi key thuộc tính entity

Map<String,ProductTranslation> được ánh xạ @MapKey(name="localeCode"). Một ProductTranslation đổi localeCode từ "vi" sang "en" sau khi Map đã tải.

**Câu hỏi:** Map.get("en") có chắc trả translation đó ngay không?

**Đáp án:** Không. Key trong Map đang quản lý có thể vẫn là "vi". Cần quản lý key như bất biến hoặc có helper cập nhật Map và entity nhất quán, đồng thời tuân thủ unique constraint.

### Bài 7: List trùng có ý nghĩa

Một cuộc khảo sát cho phép hai tùy chọn đều hiển thị "Khác" ở các vị trí khác nhau.

**Câu hỏi:** Nên dùng Set<String> hay List<String>?

**Gợi ý:** List và lưu vị trí phù hợp hơn nếu hai lần xuất hiện có ý nghĩa độc lập. Dùng @OrderColumn nếu cần bền vững thứ tự theo index JPA.

### Bài 8: JOIN tạo hàng lặp

Truy vấn join Article với Tag trả ba hàng SQL cho cùng Article. Bảng articles chỉ có một hàng id = 10.

**Câu hỏi:** Đây có phải ba entity Article được lưu trong DB không?

**Đáp án:** Không. JOIN nhân hàng kết quả theo số Tag. Nếu cần danh sách Article duy nhất trong JPQL, dùng SELECT DISTINCT ở vị trí phù hợp; nếu cần tối ưu tải, xem query/fetch plan.

### Bài 9: Lombok và quan hệ hai hướng

Parent có Set<Child>; Child có Parent parent; cả hai dùng Lombok @Data.

**Câu hỏi:** Vì sao chỉ gọi hashCode hoặc log đối tượng có thể gây vấn đề?

**Gợi ý:** equals/hashCode/toString có thể duyệt association hai hướng, tạo vòng đệ quy, tải lazy hoặc tốn nhiều query. Cần kiểm soát phương thức sinh và loại association khỏi equality/hash.

### Bài 10: Trùng theo nghiệp vụ khác trùng theo PK

Có Tag A(id=10, code="jpa") và Tag B(id=20, code="jpa"). Code được yêu cầu duy nhất.

**Câu hỏi:** Thay equals của Tag sang so sánh code có tự sửa dữ liệu không?

**Đáp án:** Không. Java có thể xem hai instance bằng nhau trong Set, nhưng database vẫn có hai hàng. Cần phát hiện/gộp dữ liệu một cách có kiểm soát và thêm UNIQUE(code) thực tế.

## 19. Gợi ý quy trình ra quyết định cho Collection và Map JPA

Khi chuẩn bị một field trong entity, hãy tự trả lời theo thứ tự:

1. **Phần tử là value hay entity?** Một String/embeddable thường có equality theo giá trị; entity có identity riêng và vòng đời persistence.
2. **Trùng có được phép theo nghiệp vụ không?** Nếu không, định nghĩa chính xác trường nào quyết định uniqueness.
3. **Có cần thứ tự không?** List có thể dùng @OrderColumn; Set không đảm bảo order theo HashSet; nếu chỉ cần sắp xếp, xem @OrderBy.
4. **Có cần tra theo khóa không?** Map với @MapKeyColumn hoặc @MapKey thích hợp, nhưng key phải ổn định và có quy tắc nhất quán.
5. **equals/hashCode có thể thay đổi không?** Tránh dùng mutable field, collection/association; cẩn trọng generated ID và proxy.
6. **Dữ liệu trùng bị ngăn ở đâu?** Dùng DB UNIQUE/PRIMARY KEY cho bất biến dữ liệu, không thay bằng Set/Map trong JVM.
7. **Sự trùng do query hay do dữ liệu?** JOIN có thể trả nhiều hàng; SELECT DISTINCT không phải migration dọn dữ liệu.
8. **Quan hệ có vòng đời như thế nào?** Xem cascade/orphanRemoval, phía sở hữu FK và helper giữ hai hướng nhất quán.
9. **Có nhiều transaction/nhiều node không?** Chỉ constraint/transaction ở DB phù hợp mới chặn ghi trùng xuyên process.
10. **Đã rõ chính sách khóa nghiệp vụ chưa?** Mã có thể đổi, chuẩn hóa khác Java hay tái sử dụng theo thời gian sẽ tác động equality.

## 20. Tổng kết

Xử lý phần tử trùng trong JPA phải kết hợp ba lớp suy nghĩ:

- **Java collection semantics:** List cho phép lặp; Set dùng equality để tránh phần tử trùng; Map có một value cho mỗi key và put() có thể thay value cũ.
- **Identity và equality:** equals()/hashCode() của value object và entity phải nhất quán, ổn định theo vòng đời và không duyệt association ngoài ý muốn. Generated ID, detached entity, proxy và business key mutable là những tình huống cần cân nhắc riêng.
- **Database và truy vấn:** UNIQUE/PRIMARY KEY bảo vệ dữ liệu trước ghi trùng xuyên transaction; phép JOIN có thể nhân hàng kết quả; DISTINCT ở query không thay thế constraint hay làm sạch dữ liệu.

Chọn **Set**, **List** hoặc **Map** theo đúng ngữ nghĩa nghiệp vụ, khai báo mapping JPA tương ứng, thiết kế equality phù hợp và đặt ràng buộc tính duy nhất ở nơi database có thể thực thi. Khi làm vậy, ứng dụng vừa tránh trùng không mong muốn, vừa không làm mất những lần xuất hiện hoặc bản ghi trùng **có ý nghĩa** đối với domain.
