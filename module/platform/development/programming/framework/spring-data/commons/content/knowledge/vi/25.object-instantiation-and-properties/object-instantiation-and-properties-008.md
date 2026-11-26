# Kế thừa, thuộc tính bị che khuất và xung đột kiểu

Trong chương **Khởi tạo và gán thuộc tính** của Spring Data Commons, kế thừa không chỉ là chuyện tái sử dụng constructor và getter. Một đối tượng lớp con có thể chứa hai field cùng tên nhưng thuộc hai lớp khai báo khác nhau. Nếu bộ ánh xạ không có một mô hình thuộc tính rõ ràng, việc đọc dữ liệu có thể tạo ra hai trạng thái khác nhau trong cùng một đối tượng hoặc làm mất một thuộc tính khỏi mapping dự kiến.

Bài học giải thích ba lớp vấn đề: quy tắc kế thừa của Java, cách Spring Data nhận diện thuộc tính persistent và cách module lưu trữ ánh xạ chúng xuống trường hoặc cột. Phân biệt ba lớp này giúp tránh dùng annotation như một cách che lỗi thiết kế.

Phạm vi chính là mô hình đối tượng Java và cơ chế mapping dùng chung trong Spring Data. Ví dụ dùng annotation của Commons phù hợp với các module trực tiếp sử dụng hạ tầng đó. Quy tắc entity inheritance, field access và property access của JPA vẫn phải được đánh giá theo JPA provider.

## 1. Field hiding khác với method overriding

Xét ví dụ Java thuần sau, chưa có annotation mapping:

```java
class BaseDocument {

    private CharSequence label;

    BaseDocument(CharSequence label) {
        this.label = label;
    }

    public CharSequence getLabel() {
        return label;
    }

    public void setLabel(CharSequence label) {
        this.label = label;
    }

    public CharSequence baseLabelSnapshot() {
        return label;
    }
}

class Article extends BaseDocument {

    private String label;

    Article(String label) {
        super(label);
        this.label = label;
    }

    @Override
    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }
}
```

Bên trong một instance `Article` tồn tại hai vùng lưu trạng thái:

```text
Phần BaseDocument của đối tượng:
    BaseDocument.label : CharSequence

Phần Article của đối tượng:
    Article.label      : String
```

Field ở lớp con không thay thế vùng lưu của field lớp cha. Đối với field `private`, lớp con không truy cập trực tiếp field của cha, nhưng field đó vẫn tồn tại trong trạng thái của đối tượng. Đây là kiểu tình huống thường được mô tả là field hiding hoặc shadowing khi bàn về mapping.

Ngược lại, phương thức instance có thể được override. `Article.getLabel()` override `BaseDocument.getLabel()` và dùng kiểu trả về hiệp biến: `String` là một kiểu con của `CharSequence`.

Còn hai setter có chữ ký khác nhau:

```java
setLabel(CharSequence label)
setLabel(String label)
```

Setter nhận `String` là một overload, không phải override setter nhận `CharSequence`. Nếu thêm `@Override` vào setter nhận `String` trong ví dụ, compiler sẽ báo nó không override phương thức cha tương ứng.

| Thành phần | Điều thực sự xảy ra |
| --- | --- |
| Hai field cùng tên | Có thể là hai vùng trạng thái độc lập |
| Getter cùng chữ ký, trả về kiểu con hợp lệ | Có thể là method overriding |
| Setter có kiểu tham số khác | Là overload, không tự đồng bộ hai field |
| Constructor lớp con gọi `super(...)` | Khởi tạo phần trạng thái lớp cha tại thời điểm tạo đối tượng |

## 2. Một đối tượng có thể cho hai câu trả lời khác nhau

Với các lớp trên, xét các lời gọi:

```java
Article article = new Article("initial");
BaseDocument baseReference = article;

baseReference.setLabel(new StringBuilder("base-only"));

System.out.println(article.getLabel());
System.out.println(baseReference.getLabel());
System.out.println(article.baseLabelSnapshot());
```

Các giá trị quan sát được là:

```text
initial
initial
base-only
```

Lý do:

1. `baseReference.setLabel(...)` gọi phương thức có tham số `CharSequence`, phương thức đó gán field trong `BaseDocument`.
2. `getLabel()` được override, nên lời gọi qua cả hai biến tham chiếu đều đi tới getter của `Article`.
3. `baseLabelSnapshot()` đọc trực tiếp field riêng của `BaseDocument`, nên thấy giá trị khác.

Bây giờ gọi tiếp:

```java
article.setLabel("child-only");
```

Setter nhận `String` cập nhật field của `Article`; nó không tự cập nhật field của cha. Từ thời điểm này, hai field tiếp tục giữ hai giá trị khác nhau.

Vấn đề đã xuất hiện ở mức Java, trước khi Spring Data đọc hoặc ghi bất kỳ bản ghi nào. Mapping chỉ làm việc với mô hình đã tồn tại; nó không tự suy ra rằng hai field phải luôn đồng bộ.

Đây cũng là lý do không nên chỉ kiểm tra một getter để kết luận toàn bộ trạng thái đối tượng đã được tái tạo đúng.

## 3. Từ field Java đến persistent property

Spring Data xây dựng metadata về persistent entity và persistent property. Metadata mô tả những thuộc tính được xem xét để lưu, kiểu của chúng và cách truy cập tương ứng.

Không nên đồng nhất các khái niệm sau:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Field Java | `BaseDocument.label` | Vùng trạng thái ở một lớp khai báo cụ thể |
| Phương thức truy cập | `Article.getLabel()` | Hành vi đọc hoặc ghi thông qua method |
| Persistent property | Thuộc tính `label` trong metadata | Đơn vị mà mapping infrastructure xử lý |
| Tên trong kho dữ liệu | Trường hoặc cột `article_label` | Biểu diễn vật lý do module lưu trữ quyết định |

Hai field Java khác nhau nhưng cùng tên không tự tạo ra hai tên lưu trữ khác nhau. Ngược lại, đổi tên trường trong kho dữ liệu không làm hai field Java trở thành một vùng trạng thái.

Khi có khai báo trùng tên trong hierarchy, cần giải quyết cả hai câu hỏi:

- Hạ tầng nhận diện quan hệ giữa các thuộc tính này như thế nào?
- Nếu chúng đều có ý nghĩa cần lưu, module có phân biệt được tên lưu trữ và đường truy cập của từng thuộc tính hay không?

## 4. Tính tương thích kiểu quyết định cách hiểu override

Trong việc nhận diện thuộc tính bị ghi đè, Spring Data xem xét khả năng gán của kiểu thuộc tính ở lớp con vào kiểu thuộc tính tương ứng ở lớp cha.

Hướng kiểm tra cần nhớ là:

```java
superPropertyType.isAssignableFrom(subPropertyType)
```

Ví dụ:

```java
CharSequence.class.isAssignableFrom(String.class); // true
Number.class.isAssignableFrom(Integer.class);     // true
Integer.class.isAssignableFrom(String.class);    // false
```

| Kiểu ở cha | Kiểu ở con | Có thể gán giá trị kiểu con vào kiểu cha? |
| --- | --- | --- |
| `String` | `String` | Có |
| `CharSequence` | `String` | Có |
| `Number` | `Integer` | Có |
| `Integer` | `String` | Không |

Khi các kiểu không tương thích theo hướng này, Spring Data không đăng ký chúng như một quan hệ override hợp lệ; thuộc tính ở lớp cha được xem là transient trong việc xác định mapping cho trường hợp lớp con đó.

“Được xem là transient” ở đây là kết quả xử lý metadata, không có nghĩa framework đã thêm annotation `@Transient` vào mã nguồn hoặc xóa field Java. Field lớp cha vẫn tồn tại và các phương thức của lớp cha vẫn có thể đọc nó.

Khi các kiểu tương thích, quan hệ override có thể được nhận diện. Điều đó không có nghĩa hai field vật lý tự hợp nhất, cũng không bảo đảm mọi module sẽ lưu hai giá trị độc lập dưới cùng một tên mà không xung đột.

Do vậy, tương thích kiểu là một điều kiện để hiểu metadata, không phải lời khuyên thiết kế rằng cứ dùng kiểu cha rộng như `Object` thì mọi vấn đề đã được giải quyết.

## 5. Xung đột kiểu: mã Java hợp lệ nhưng mapping khác ý định

Xét ví dụ chỉ dùng field để làm rõ xung đột:

```java
class NumericBase {
    protected Integer value;
}

class TextChild extends NumericBase {
    protected String value;
}
```

Java cho phép hai khai báo field này. Tuy nhiên, `String` không thể gán cho `Integer`, nên chúng không tạo thành quan hệ override tương thích về kiểu theo quy tắc mapping vừa nêu.

Nếu bạn mong cả giá trị số ở cha lẫn giá trị chữ ở con được giữ lại khi đọc `TextChild`, việc chỉ đặt cùng tên `value` là không đủ. Thuộc tính ở cha có thể đã bị loại khỏi mapping persistent của lớp con theo quy tắc xung đột kiểu.

Thêm hai getter cùng tên cũng không phải cách sửa hợp lệ:

```text
NumericBase.getValue() trả Integer
TextChild.getValue() trả String
```

Hai kiểu trả về không có quan hệ hiệp biến phù hợp, nên một khai báo override như vậy không hợp lệ trong Java. Cần phân biệt điều Java cho phép ở field với điều Java cho phép ở method.

Cách sửa dễ hiểu hơn là dùng tên theo ý nghĩa:

```java
class NumericBase {
    protected Integer numericValue;
}

class TextChild extends NumericBase {
    protected String textValue;
}
```

Lúc này mô hình biểu đạt rõ hai thuộc tính khác nhau. Bộ ánh xạ không còn phải giải thích việc cùng một tên lại đại diện cho hai khái niệm và hai kiểu không tương thích.

## 6. Trùng tên lưu trữ có thể gây mất hoặc nhầm dữ liệu

Ngay cả khi kiểu Java tương thích, vẫn có vấn đề nếu hai giá trị độc lập cùng được gắn vào một tên lưu trữ.

Ví dụ ý định nghiệp vụ là:

```text
Nhãn nguồn       = "Imported catalogue"
Nhãn hiển thị    = "Danh mục sách"
```

Nếu cả hai được ánh xạ vào cùng một trường hoặc cột `label`, một giá trị lưu đơn lẻ không tự biểu diễn được cả hai ý nghĩa. Việc ghi đè, báo lỗi mapping hay cách giải quyết trùng lặp cụ thể phụ thuộc module và cấu hình; không nên dựa vào một thứ tự ghi ngầm.

Cần quyết định trước:

1. Đây thực sự là một thuộc tính chung, chỉ nên có một nơi lưu trạng thái?
2. Hay đây là hai thuộc tính độc lập cần hai tên và hai giá trị lưu?
3. Hay một thuộc tính chỉ là dữ liệu tính toán hoặc trạng thái tạm, không cần persistence?

Từ quyết định đó mới chọn cách sửa. Chỉ thêm annotation tên cột khác mà không hiểu hai vùng trạng thái trong Java có thể giữ lại một mô hình khó kiểm soát.

## 7. Phương án ưu tiên: tên thuộc tính phản ánh hai ý nghĩa

Ví dụ dưới đây mô tả một bản ghi có nhãn nguồn và một bản địa hóa có nhãn hiển thị. Hai thuộc tính được đặt tên khác nhau ngay trong mô hình Java.

Ví dụ tập trung vào đường đọc đối tượng bằng cơ chế mapping Spring Data. Nó không phải một cấu hình entity inheritance cho JPA.

### 7.1. Lớp cha giữ trạng thái chung

```java
package com.example.catalog;

import org.springframework.data.annotation.Id;

import java.util.Objects;

public abstract class SourceEntry {

    @Id
    private final String id;

    private final String sourceLabel;

    protected SourceEntry(String id, String sourceLabel) {
        this.id = id;
        this.sourceLabel = Objects.requireNonNull(
                sourceLabel, "sourceLabel must not be null");
    }

    public String getId() {
        return id;
    }

    public String getSourceLabel() {
        return sourceLabel;
    }
}
```

### 7.2. Lớp con thêm thuộc tính riêng

```java
package com.example.catalog;

import org.springframework.data.annotation.PersistenceCreator;

import java.util.Objects;

public final class LocalizedEntry extends SourceEntry {

    private final String displayLabel;

    // Tạo mới trong ứng dụng.
    public LocalizedEntry(String sourceLabel, String displayLabel) {
        this(null, sourceLabel, displayLabel);
    }

    // Khôi phục trạng thái từ dữ liệu đã lưu.
    @PersistenceCreator
    public LocalizedEntry(
            String id,
            String sourceLabel,
            String displayLabel) {
        super(id, sourceLabel);
        this.displayLabel = Objects.requireNonNull(
                displayLabel, "displayLabel must not be null");
    }

    public String getDisplayLabel() {
        return displayLabel;
    }
}
```

Constructor được chọn nhận cả thuộc tính kế thừa lẫn thuộc tính riêng và chuyển giá trị cho constructor cha một cách tường minh. Không có tham số `label` mơ hồ cần đại diện cho hai field cùng tên.

Dữ liệu logic cần khôi phục là:

```text
id           = "entry-42"
sourceLabel  = "Imported catalogue"
displayLabel = "Danh mục sách"
```

Đây là mô tả giá trị thuộc tính, không bắt buộc là tên trường vật lý của một kho dữ liệu cụ thể.

Các tên tham số constructor cần được giữ trong metadata biên dịch hoặc được cung cấp bằng cơ chế hỗ trợ phù hợp. `@PersistenceCreator` chọn creator; nó không tự sửa tên tham số thiếu hoặc mapping xung đột.

Ví dụ cũng không khẳng định rằng mọi module tự hỗ trợ toàn bộ thao tác ghi ID cho một object immutable. Đường ghi và việc cập nhật ID cần được đánh giá riêng theo module sử dụng.

## 8. Nếu chỉ nên có một thuộc tính, đừng khai báo lại field

Không phải mọi trường hợp đều cần hai thuộc tính. Nếu nhãn ở lớp cha và lớp con có cùng ý nghĩa, hãy giữ một nguồn trạng thái duy nhất:

```java
class LabeledDocument {

    private final String label;

    protected LabeledDocument(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}

class ArticleDocument extends LabeledDocument {

    private final String body;

    ArticleDocument(String label, String body) {
        super(label);
        this.body = body;
    }

    public String getBody() {
        return body;
    }
}
```

Lớp con có thể bổ sung hành vi hoặc thuộc tính khác mà không tạo một field `label` thứ hai.

Nếu lớp con cần trình bày nhãn theo cách khác, cân nhắc một phương thức tính toán có tên riêng. Không dùng cùng tên persistent property cho dữ liệu gốc và dữ liệu hiển thị nếu chúng có hợp đồng khác nhau.

Ví dụ, có thể dùng `formatLabelForDisplay()` ở tầng trình bày hoặc một DTO projection. Việc định dạng kết quả đọc không nhất thiết yêu cầu thay đổi mô hình lưu trữ bằng field hiding.

## 9. Dùng @Transient có chủ đích

Khi một field chỉ là trạng thái tạm hoặc thực sự không cần lưu, annotation của Commons có thể được dùng trong cơ chế mapping có hỗ trợ nó:

```java
import org.springframework.data.annotation.Transient;

class ImportedBase {

    @Transient
    protected String label;
}

class DisplayEntry extends ImportedBase {

    protected String label;
}
```

Đoạn này minh họa ý định loại khai báo ở cha khỏi persistence; nó không làm hai field trở thành một. Nếu phương thức lớp cha vẫn đọc field bị loại, bạn vẫn phải xác định field đó nhận giá trị nào sau khi tạo đối tượng.

Đặt annotation ở đúng khai báo và kiểm tra metadata thực tế của module. Không giả định rằng đánh dấu một field cùng tên sẽ tự loại hoặc đồng bộ mọi field ở cả hierarchy.

Cần phân biệt:

| Cơ chế | Ý nghĩa cần kiểm tra |
| --- | --- |
| `org.springframework.data.annotation.Transient` | Loại thuộc tính khỏi mapping của hạ tầng Spring Data có hỗ trợ |
| `jakarta.persistence.Transient` | Quy tắc persistence thuộc phạm vi JPA |
| Từ khóa Java `transient` | Có ý nghĩa với Java serialization; cách một framework mapping xử lý cần kiểm tra riêng |

Không dùng annotation của module hoặc framework này rồi mặc định mọi framework khác sẽ có cùng kết quả.

## 10. Tên trường và cột riêng theo module

Nếu hai thuộc tính đều cần lưu, module lưu trữ có thể cung cấp annotation đặt tên vật lý riêng. Ví dụ về mặt ý tưởng:

```text
Thuộc tính Java sourceLabel  → trường/cột source_label
Thuộc tính Java displayLabel → trường/cột display_label
```

Trong MongoDB, có thể gặp annotation:

```java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("source_label")
private String sourceLabel;
```

Trong mapping relational của Spring Data JDBC, có thể gặp:

```java
import org.springframework.data.relational.core.mapping.Column;

@Column("display_label")
private String displayLabel;
```

Hai đoạn trên thuộc hai ngữ cảnh module khác nhau. Chúng không phải yêu cầu gắn cả hai annotation lên một mô hình để làm cho nó tự tương thích mọi kho dữ liệu.

Việc đặt tên lưu trữ riêng giúp tránh va chạm ở kho dữ liệu. Việc đặt tên Java riêng còn giúp constructor, getter, setter và mã nghiệp vụ biểu đạt đúng ý nghĩa. Trong nhiều tình huống, cần cả hai quyết định.

Nếu schema hiện đã có dữ liệu, đổi tên field hoặc cột còn liên quan đến migration và tương thích với các phiên bản ứng dụng đang chạy. Không coi đây chỉ là đổi tên biến trong mã nguồn.

## 11. Property access không tự giải quyết hai trạng thái bị che khuất

Spring Data có metadata điều khiển truy cập thuộc tính, chẳng hạn:

```java
import org.springframework.data.annotation.AccessType;

@AccessType(AccessType.Type.PROPERTY)
class SomeMappedType {
    // Getter và setter tương ứng.
}
```

Chọn property access không tự tạo một đường độc lập để gán hai field cùng tên ở hai lớp. Getter có thể bị override; setter có thể bị override hoặc chỉ là overload như ví dụ đầu bài.

Không thể kỳ vọng hạ tầng chỉ nhìn tên `label` rồi biết lúc nào phải gọi setter lớp cha và lúc nào phải gọi setter lớp con để lưu hai giá trị khác nhau. Đặc biệt, property access không cung cấp một cách chung để đặt riêng giá trị super-property đang bị che khuất qua một hợp đồng accessor trùng tên.

Nếu thật sự chỉ có một trạng thái, một setter có thể chủ động duy trì nó theo hợp đồng đã thiết kế. Nếu có hai trạng thái độc lập, dùng hai tên thuộc tính và hai đường truy cập rõ ràng sẽ dễ kiểm soát hơn.

Tương tự, chuyển sang field access không làm hai ý nghĩa cùng tên trở nên rõ ràng một cách tự động. Field access chỉ đổi đường truy cập; nó không thay quyết định về tên, kiểu và số lượng giá trị cần lưu.

## 12. ID, auditing và metadata kế thừa

Lớp cha thường được dùng để chứa các thuộc tính chung như ID, thời điểm tạo và người cập nhật. Đây là nơi đặc biệt cần tránh redeclare cùng tên ở lớp con.

Ví dụ ý định đáng nghi ngờ:

```text
BaseEntity.id : Long
SpecialEntity.id : String
```

Bạn cần quyết định loại định danh thật sự của entity, không trông chờ hai khai báo `id` sẽ tự hợp nhất. Sự khác biệt kiểu còn có thể tương tác với quy tắc nhận diện override và annotation định danh của module.

Tương tự, nếu `createdAt` ở cha và `createdAt` ở con là hai field, cơ chế auditing không có trách nhiệm tự đồng bộ hai vùng trạng thái chỉ vì chúng trùng tên.

Các câu hỏi cần trả lời là:

- Metadata persistent cuối cùng nhận diện thuộc tính ID nào?
- Auditing cập nhật khai báo nào theo cấu hình module?
- Constructor đọc giá trị của thuộc tính nào?
- Getter mà service hoặc projection sử dụng nhìn vào vùng trạng thái nào?

Giải pháp thường rõ ràng hơn là định nghĩa thuộc tính chung một lần, cho lớp con sử dụng nó và chỉ thêm tên mới khi có một ý nghĩa nghiệp vụ mới.

Kế thừa trong Java cũng không tự cấu hình việc lưu nhiều subtype chung một collection, bảng hay hierarchy đa hình. Type discriminator, chiến lược kế thừa và cách materialize subtype là một nhóm quyết định khác, phụ thuộc kho dữ liệu.

## 13. Quy trình phân tích một hierarchy đang có lỗi

### Bước 1: Liệt kê từng khai báo, không chỉ từng tên

Với tên `label`, lập danh sách dạng:

```text
BaseDocument.label : CharSequence
Article.label      : String
```

Ghi rõ field thuộc lớp nào và annotation nào đặt tại đó. Một kết quả tìm kiếm chỉ có tên `label` chưa đủ để hiểu số lượng vùng trạng thái.

### Bước 2: Liệt kê accessor và chữ ký đầy đủ

Phân biệt:

```text
getLabel() : CharSequence / String
setLabel(CharSequence)
setLabel(String)
```

Dùng `@Override` khi có ý định override method để compiler kiểm tra giả định. Không thêm annotation đó vào một setter overload rồi bỏ qua lỗi compiler.

### Bước 3: Kiểm tra hướng tương thích kiểu

Đặt câu hỏi liệu kiểu ở con có thể gán vào kiểu ở cha hay không. Nếu không, thuộc tính cha không được coi là override persistent tương thích trong trường hợp đó.

Đừng sửa bằng cách mở rộng mọi kiểu thành `Object` chỉ để vượt qua kiểm tra. Kiểu rộng hơn có thể làm mất hợp đồng miền và đẩy vấn đề sang chuyển đổi dữ liệu.

### Bước 4: Xác định một hay hai ý nghĩa

- Một ý nghĩa: giữ một nguồn trạng thái.
- Hai ý nghĩa đều cần lưu: dùng tên Java và tên lưu trữ phân biệt.
- Một ý nghĩa là tạm thời: loại khỏi persistence có chủ đích và định nghĩa cách tạo lại nó nếu cần.

### Bước 5: Kiểm tra creator và đường gán còn lại

Constructor được chọn cần nhận đủ dữ liệu bất biến và gọi constructor cha phù hợp. Các thuộc tính còn lại phải có đường gán hợp lệ cho module.

Một `@PersistenceCreator` không thể dùng cùng một tham số `label` để tự biểu đạt hai thuộc tính độc lập mà mô hình metadata chưa phân biệt được.

### Bước 6: Kiểm tra bằng đường đọc thực tế

Dùng repository hoặc converter của module để đọc dữ liệu có các giá trị khác nhau rõ rệt. Quan sát cả dữ liệu đã lưu lẫn trạng thái mà hành vi ở cha và con sử dụng.

## 14. Những tình huống cần kiểm chứng khi tích hợp

Bảng dưới là định hướng kiểm chứng cho mô hình đang dùng, không thay thế quy tắc cụ thể của module.

| Tình huống | Điều cần quan sát |
| --- | --- |
| Thuộc tính chỉ khai báo ở cha | Lớp con nhận đúng giá trị kế thừa khi đọc |
| Hai field cùng tên, kiểu tương thích | Metadata và đường truy cập đúng ý định; không suy ra hai field tự đồng bộ |
| Hai field cùng tên, kiểu không tương thích | Không vô tình mất dữ liệu của thuộc tính cha mà ứng dụng vẫn cần |
| Hai ý nghĩa đều cần lưu | Có hai tên thuộc tính và tên lưu trữ phân biệt |
| Thuộc tính cha bị loại bằng `@Transient` | Hành vi lớp cha không dựa vào một giá trị tưởng đã được khôi phục |
| Object immutable có trạng thái kế thừa | Creator truyền đủ dữ liệu cho constructor cha |
| Getter override và setter overload | Đọc và ghi không chạm hai vùng trạng thái ngoài dự kiến |
| ID hoặc auditing nằm trong hierarchy | Metadata và trạng thái quan sát được thống nhất |

Nên dùng dữ liệu như `sourceLabel = "SOURCE"` và `displayLabel = "DISPLAY"`, thay vì cho cả hai cùng bằng `"same"`. Hai giá trị giống nhau có thể che giấu lỗi ánh xạ hoặc việc một giá trị đang bị dùng cho cả hai thuộc tính.

Một lần round-trip có ích, nhưng nếu chỉ ghi bằng cùng một mapping sai rồi đọc bằng mapping đó, kết quả vẫn có thể trông nhất quán. Vì vậy, khi bảo trì schema có sẵn, cần kiểm tra cả bản ghi có giá trị đã biết và biểu diễn thực tế trong kho dữ liệu.

## 15. Bài tập áp dụng

Một hệ thống có lớp cha `AuditRecord` chứa `String status`, còn lớp con `ShipmentRecord` khai báo thêm `Integer status`. Lớp cha dùng trạng thái để biểu thị kết quả kiểm tra dữ liệu; lớp con dùng số để biểu thị giai đoạn vận chuyển.

Hãy phân tích:

1. Hai thuộc tính có thực sự cùng một ý nghĩa không?
2. Kiểu ở con có gán được vào kiểu ở cha không?
3. Vì sao việc khai báo hai field có thể hợp lệ ở Java nhưng không mang lại mapping mong muốn?
4. Nên đổi tên thuộc tính và tên lưu trữ như thế nào?
5. Constructor tái tạo cần nhận những giá trị nào?

Một hướng thiết kế rõ ràng là đổi thành `auditStatus` và `shipmentStage`, ánh xạ vào hai trường hoặc cột riêng, rồi truyền cả hai giá trị qua creator của lớp con và constructor cha tương ứng.

Nếu hai trạng thái có tập giá trị cố định, có thể dùng hai enum riêng và cấu hình chuyển đổi theo module. Không nên giữ cùng tên `status` chỉ để tận dụng quan hệ kế thừa, vì đó là hai khái niệm khác nhau.

Khi đánh giá một hierarchy, hãy kiểm tra đồng thời **nơi trạng thái được lưu trong Java, thuộc tính có mặt trong metadata và tên giá trị được lưu trong kho dữ liệu**. Ba lớp thông tin phải cùng thể hiện một ý định; một getter chạy đúng chưa đủ chứng minh việc khởi tạo và gán thuộc tính đã đúng.